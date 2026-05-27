#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, roc_auc_score

try:
    from lightgbm import LGBMClassifier
except Exception:  # pragma: no cover - depends on local environment
    LGBMClassifier = None


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_STOCK_FEATURE_FILE = SKILL_DIR / "data" / "个股k线特征数据.csv"
DEFAULT_STOCK_LIST_FILE = SKILL_DIR / "data" / "00_股票清单.csv"
DEFAULT_OUTPUT_DIR = SKILL_DIR / "outputs" / "stock_direction_predictions"

LABEL_COL = "future_5_up_label"
RETURN_LABEL_COL = "future_5_return"
DATE_COL = "trade_date"
MODEL_LABEL_COL = "model_up_label"

FORBIDDEN_EXACT_COLUMNS = {
    "日期",
    DATE_COL,
    "future_5_trade_date",
    "future_5_close",
    "future_5_return",
    "future_5_direction",
    "future_5_up_label",
    "name",
    "name_from_file",
    "source_file",
    "exchange",
    "board",
    "industry",
    "region",
    "themes",
    "quality_issues",
    "quality_issue_count",
    "has_hard_issue",
    "has_soft_issue",
    "is_training_eligible",
}

FORBIDDEN_PREFIXES = ("future_",)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="个股5日Top股票池预测：按股票清单和日期范围逐日锚点预测")
    parser.add_argument("--stock-list", default=str(DEFAULT_STOCK_LIST_FILE), help="股票清单路径，默认 data/00_股票清单.csv")
    parser.add_argument("--stock-file", default=str(DEFAULT_STOCK_FEATURE_FILE), help="内部特征数据路径，默认 data/个股k线特征数据.csv")
    parser.add_argument("--start-date", required=True, help="预测起始锚点日，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="预测结束锚点日，格式 YYYY-MM-DD")
    parser.add_argument("--lookback-days", type=int, default=365, help="每个锚点日前向训练窗口自然日数；单日未指定训练区间时也使用此窗口")
    parser.add_argument("--min-anchor-coverage", type=float, default=0.9, help="默认锚点日最低股票覆盖率；按历史最大股票数计算")
    parser.add_argument("--target-mode", choices=["direction", "top_quantile"], default="top_quantile", help="训练目标：默认同日收益前N分位；direction仅用于研究")
    parser.add_argument("--top-quantile", type=float, default=0.2, help="target-mode=top_quantile 时，未来5日收益排名前多少比例标为1")
    parser.add_argument("--threshold", type=float, default=0.5, help="上涨方向判定阈值")
    parser.add_argument("--label-up-threshold", type=float, default=0.01, help="训练上涨标签阈值，默认未来5日收益 >= 1%%")
    parser.add_argument("--label-down-threshold", type=float, default=-0.01, help="训练下跌标签阈值，默认未来5日收益 <= -1%%")
    parser.add_argument("--exclude-st", action="store_true", default=True, help="训练时剔除 ST 股票，默认开启")
    parser.add_argument("--include-st", dest="exclude_st", action="store_false", help="训练时保留 ST 股票")
    parser.add_argument("--exclude-st-prediction", action="store_true", default=True, help="预测股票池剔除 ST 股票，默认开启")
    parser.add_argument("--include-st-prediction", dest="exclude_st_prediction", action="store_false", help="预测股票池保留 ST 股票")
    parser.add_argument("--top-n", type=int, default=3, help="只输出概率最高的N只；默认3；0表示输出全部")
    parser.add_argument("--enable-overheat-penalty", action="store_true", help="开启Top分位模式的高换手高波动过热惩罚；默认关闭")
    parser.add_argument("--disable-overheat-penalty", action="store_false", dest="enable_overheat_penalty", help=argparse.SUPPRESS)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="预测结果输出目录")
    return parser.parse_args()


def normalize_date(value: str) -> str:
    if not value:
        return ""
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def load_stock_features(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"未找到个股特征表: {path}")
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"symbol": str})
    df["symbol"] = df["symbol"].str.extract(r"(\d{1,6})", expand=False).str.zfill(6)
    df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")
    if "future_5_trade_date" in df.columns:
        df["future_5_trade_date"] = pd.to_datetime(df["future_5_trade_date"], errors="coerce")
    df = df.dropna(subset=[DATE_COL, "symbol"]).copy()
    return df


def load_stock_list(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"未找到股票清单: {path}")
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    if "代码" not in df.columns:
        raise RuntimeError(f"股票清单缺少 `代码` 列: {path}")
    out = pd.DataFrame()
    out["symbol"] = df["代码"].str.extract(r"(\d{1,6})", expand=False).str.zfill(6)
    out = out[out["symbol"].str.fullmatch(r"\d{6}", na=False)].drop_duplicates("symbol")
    if out.empty:
        raise RuntimeError(f"股票清单为空: {path}")
    return out


def date_coverage(df: pd.DataFrame) -> pd.DataFrame:
    counts = df.groupby(DATE_COL)["symbol"].nunique().sort_index()
    max_count = int(counts.max()) if not counts.empty else 0
    out = counts.rename("stock_count").reset_index()
    out["coverage_ratio"] = out["stock_count"] / max_count if max_count else 0.0
    return out


def choose_anchor_date(df: pd.DataFrame, requested: str, min_coverage: float, allow_partial: bool) -> pd.Timestamp:
    coverage = date_coverage(df)
    if coverage.empty:
        raise RuntimeError("个股特征表没有可用交易日")

    if requested:
        anchor = pd.to_datetime(requested)
        if df[DATE_COL].eq(anchor).sum() == 0:
            available = df.loc[df[DATE_COL] <= anchor, DATE_COL].drop_duplicates().sort_values()
            hint = available.iloc[-1].strftime("%Y-%m-%d") if not available.empty else "无"
            raise ValueError(f"锚点日 {anchor:%Y-%m-%d} 没有个股样本；最近可用交易日: {hint}")
        row = coverage.loc[coverage[DATE_COL].eq(anchor)].iloc[0]
        if row["coverage_ratio"] < min_coverage and not allow_partial:
            latest_full = coverage.loc[coverage["coverage_ratio"] >= min_coverage, DATE_COL].max()
            hint = latest_full.strftime("%Y-%m-%d") if pd.notna(latest_full) else "无"
            raise ValueError(
                f"锚点日 {anchor:%Y-%m-%d} 覆盖率不足: "
                f"{int(row['stock_count'])} 只, 覆盖率 {row['coverage_ratio']:.2%}; "
                f"最近覆盖率达标交易日: {hint}。如仍要预测，添加 --allow-partial-anchor。"
            )
        return anchor

    eligible = coverage.loc[coverage["coverage_ratio"] >= min_coverage]
    if eligible.empty:
        latest = coverage.iloc[-1]
        raise RuntimeError(
            f"没有覆盖率达到 {min_coverage:.0%} 的交易日；"
            f"最新交易日 {latest[DATE_COL]:%Y-%m-%d} 只有 {int(latest['stock_count'])} 只。"
        )
    return eligible[DATE_COL].max()


def anchor_dates_for_range(df: pd.DataFrame, start_date: str, end_date: str, min_coverage: float) -> pd.DataFrame:
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    if start > end:
        raise ValueError("start-date 不能晚于 end-date")
    coverage = date_coverage(df)
    anchors = coverage.loc[
        coverage[DATE_COL].between(start, end)
        & (coverage["coverage_ratio"] >= min_coverage)
    ].copy()
    if anchors.empty:
        raise RuntimeError(f"{start:%Y-%m-%d} 到 {end:%Y-%m-%d} 没有覆盖率达标的锚点日")
    return anchors.sort_values(DATE_COL)


def select_feature_columns(df: pd.DataFrame) -> list[str]:
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    features: list[str] = []
    for col in numeric_cols:
        if col in FORBIDDEN_EXACT_COLUMNS:
            continue
        if any(col.startswith(prefix) for prefix in FORBIDDEN_PREFIXES):
            continue
        features.append(col)
    if not features:
        raise RuntimeError("没有可用特征列，请检查个股特征表")
    return features


def make_train_predict_sets(
    df: pd.DataFrame,
    anchor_date: pd.Timestamp,
    train_start: str,
    train_end: str,
    label_up_threshold: float,
    label_down_threshold: float,
    exclude_st: bool,
    exclude_st_prediction: bool,
    target_mode: str,
    top_quantile: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if label_down_threshold >= label_up_threshold:
        raise ValueError("label-down-threshold 必须小于 label-up-threshold")
    if not 0 < top_quantile < 1:
        raise ValueError("top-quantile 必须在 0 到 1 之间")
    train_mask = df[DATE_COL] < anchor_date
    if train_start:
        train_mask &= df[DATE_COL] >= pd.to_datetime(train_start)
    if train_end:
        train_mask &= df[DATE_COL] <= pd.to_datetime(train_end)

    train_df = df.loc[
        train_mask
        & df["is_training_eligible"].eq(1)
        & df[LABEL_COL].notna()
        & df[RETURN_LABEL_COL].notna()
        & df["future_5_trade_date"].notna()
        & (df["future_5_trade_date"] < anchor_date)
    ].copy()
    if exclude_st and "is_st" in train_df.columns:
        train_df = train_df.loc[train_df["is_st"].fillna(0).eq(0)].copy()
    if target_mode == "direction":
        train_df = train_df.loc[
            (train_df[RETURN_LABEL_COL] >= label_up_threshold)
            | (train_df[RETURN_LABEL_COL] <= label_down_threshold)
        ].copy()
        train_df[MODEL_LABEL_COL] = (train_df[RETURN_LABEL_COL] >= label_up_threshold).astype(int)
    else:
        train_df["daily_return_rank"] = train_df.groupby(DATE_COL)[RETURN_LABEL_COL].rank(method="first", ascending=False)
        train_df["daily_stock_count"] = train_df.groupby(DATE_COL)["symbol"].transform("count")
        train_df["daily_top_cutoff"] = np.ceil(train_df["daily_stock_count"] * top_quantile).clip(lower=1)
        train_df[MODEL_LABEL_COL] = (train_df["daily_return_rank"] <= train_df["daily_top_cutoff"]).astype(int)
    predict_df = df.loc[df[DATE_COL].eq(anchor_date)].copy()
    if exclude_st_prediction and "is_st" in predict_df.columns:
        predict_df = predict_df.loc[predict_df["is_st"].fillna(0).eq(0)].copy()

    if train_df.empty:
        raise RuntimeError("训练样本为空：请检查锚点日、训练日期范围和标签列")
    if train_df[MODEL_LABEL_COL].nunique() < 2:
        raise RuntimeError("训练样本只有单一标签，无法训练分类模型")
    if predict_df.empty:
        raise RuntimeError("预测样本为空：请检查锚点日")
    return train_df, predict_df


def fit_model(train_df: pd.DataFrame, feature_cols: list[str]):
    if LGBMClassifier is None:
        raise RuntimeError("当前环境未安装或无法加载 lightgbm，请先安装 lightgbm 和 libomp")
    model = LGBMClassifier(
        n_estimators=320,
        learning_rate=0.03,
        num_leaves=31,
        min_child_samples=40,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_lambda=1.0,
        objective="binary",
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
        verbosity=-1,
    )
    label_col = MODEL_LABEL_COL if MODEL_LABEL_COL in train_df.columns else LABEL_COL
    model.fit(train_df[feature_cols], train_df[label_col].astype(int))
    return model


def score_prediction(prediction: pd.DataFrame, threshold: float) -> dict[str, object]:
    labeled = prediction.loc[prediction[LABEL_COL].notna()].copy()
    if labeled.empty:
        return {"accuracy": None, "actual_up_rate": None, "predicted_up_rate": None}
    y_true = labeled[LABEL_COL].astype(int)
    y_pred = (labeled["predicted_up_prob"] >= threshold).astype(int)
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "actual_up_rate": float(y_true.mean()),
        "predicted_up_rate": float(y_pred.mean()),
    }


def score_top_quantile_prediction(prediction: pd.DataFrame, threshold: float) -> dict[str, object]:
    labeled = prediction.loc[prediction["actual_top_quantile_label"].notna()].copy()
    if labeled.empty:
        return {"top_quantile_accuracy": None, "actual_top_quantile_rate": None, "predicted_top_quantile_rate": None}
    y_true = labeled["actual_top_quantile_label"].astype(int)
    score_col = "top_quantile_signal_score" if "top_quantile_signal_score" in labeled.columns else "predicted_top_quantile_prob"
    y_pred = (labeled[score_col] >= threshold).astype(int)
    return {
        "top_quantile_accuracy": float(accuracy_score(y_true, y_pred)),
        "actual_top_quantile_rate": float(y_true.mean()),
        "predicted_top_quantile_rate": float(y_pred.mean()),
    }


def _percentile_rank(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return df[col].rank(method="average", pct=True)


def build_overheat_penalty(predict_df: pd.DataFrame) -> pd.DataFrame:
    penalty = pd.DataFrame(index=predict_df.index)
    penalty["turnover_pctile"] = _percentile_rank(predict_df, "turnover_pct")
    penalty["ret_5_pctile"] = _percentile_rank(predict_df, "ret_5")
    penalty["ret_20_pctile"] = _percentile_rank(predict_df, "ret_20")
    penalty["volatility_5_pctile"] = _percentile_rank(predict_df, "volatility_5")
    penalty["range_pos_20_pctile"] = _percentile_rank(predict_df, "range_pos_20")

    strong_momentum = (penalty["ret_5_pctile"] >= 0.9) | (penalty["ret_20_pctile"] >= 0.9)
    high_position = predict_df.get("range_pos_20", pd.Series(np.nan, index=predict_df.index)) >= 0.8
    high_turnover = penalty["turnover_pctile"] >= 0.9
    extreme_turnover = penalty["turnover_pctile"] >= 0.98
    high_volatility = penalty["volatility_5_pctile"] >= 0.9
    extreme_volatility = penalty["volatility_5_pctile"] >= 0.95

    core_overheat = high_turnover & strong_momentum & high_position
    volatile_overheat = high_volatility & strong_momentum & high_position
    extreme_hot = (extreme_turnover | extreme_volatility) & strong_momentum

    penalty["overheat_penalty"] = 0.0
    penalty.loc[core_overheat, "overheat_penalty"] += 0.10
    penalty.loc[volatile_overheat, "overheat_penalty"] += 0.06
    penalty.loc[extreme_hot, "overheat_penalty"] += 0.04

    industry_support = (
        (predict_df.get("industry_up_ratio", pd.Series(np.nan, index=predict_df.index)) >= 0.8)
        & (
            predict_df.get("industry_avg_pct_chg", pd.Series(np.nan, index=predict_df.index))
            >= predict_df.get("market_avg_pct_chg", pd.Series(np.nan, index=predict_df.index))
        )
    )
    penalty.loc[industry_support, "overheat_penalty"] *= 0.35
    penalty["overheat_penalty"] = penalty["overheat_penalty"].clip(upper=0.18)

    reasons: list[str] = []
    for idx in penalty.index:
        row_reasons: list[str] = []
        if bool(core_overheat.loc[idx]):
            row_reasons.append("高换手+强动量+高位")
        if bool(volatile_overheat.loc[idx]):
            row_reasons.append("高波动+强动量+高位")
        if bool(extreme_hot.loc[idx]):
            row_reasons.append("极端换手/波动+强动量")
        reasons.append(";".join(row_reasons))
    penalty["overheat_penalty_reason"] = reasons
    return penalty


def build_prediction_output(
    model,
    predict_df: pd.DataFrame,
    feature_cols: list[str],
    threshold: float,
    top_n: int,
    target_mode: str,
    top_quantile: float,
    apply_overheat_penalty: bool,
) -> pd.DataFrame:
    out_cols = [
        "trade_date",
        "symbol",
        "name",
        "exchange",
        "board",
        "industry",
        "close",
        "pct_chg",
        "turnover_pct",
        "future_5_trade_date",
        "future_5_return",
        "future_5_direction",
        "future_5_up_label",
    ]
    output = predict_df[[col for col in out_cols if col in predict_df.columns]].copy()
    prob = model.predict_proba(predict_df[feature_cols])[:, 1]
    if target_mode == "direction":
        output["predicted_up_prob"] = prob
        output["predicted_down_prob"] = 1 - prob
        output["predicted_direction"] = np.where(output["predicted_up_prob"] >= threshold, "上涨", "下跌")
        output["direction_threshold"] = threshold
        output["rank_by_up_prob"] = output["predicted_up_prob"].rank(method="first", ascending=False).astype(int)
        output = output.sort_values(["predicted_up_prob", "symbol"], ascending=[False, True]).reset_index(drop=True)
    else:
        output["predicted_top_quantile_prob"] = prob
        output["predicted_non_top_quantile_prob"] = 1 - prob
        output["top_quantile_threshold"] = top_quantile
        output["target_threshold"] = threshold
        output["rank_by_raw_top_quantile_prob"] = output["predicted_top_quantile_prob"].rank(method="first", ascending=False).astype(int)
        if apply_overheat_penalty:
            penalty = build_overheat_penalty(predict_df)
            output = output.join(penalty)
        else:
            output["overheat_penalty"] = 0.0
            output["overheat_penalty_reason"] = ""
        output["top_quantile_signal_score"] = (output["predicted_top_quantile_prob"] - output["overheat_penalty"]).clip(lower=0, upper=1)
        output["predicted_top_quantile"] = np.where(output["top_quantile_signal_score"] >= threshold, 1, 0)
        output["rank_by_top_quantile_prob"] = output["top_quantile_signal_score"].rank(method="first", ascending=False).astype(int)
        output["actual_future_5_return_rank"] = output[RETURN_LABEL_COL].rank(method="first", ascending=False)
        actual_count = output[RETURN_LABEL_COL].notna().sum()
        if actual_count > 0:
            cutoff = max(1, int(np.ceil(actual_count * top_quantile)))
            output["actual_top_quantile_label"] = np.where(output["actual_future_5_return_rank"] <= cutoff, 1, 0)
            output.loc[output[RETURN_LABEL_COL].isna(), "actual_top_quantile_label"] = np.nan
        else:
            output["actual_top_quantile_label"] = np.nan
        output = output.sort_values(["top_quantile_signal_score", "symbol"], ascending=[False, True]).reset_index(drop=True)
    if top_n > 0:
        output = output.head(top_n).copy()
    output["model_type"] = "LightGBM"
    output["trade_date"] = pd.to_datetime(output["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    if "future_5_trade_date" in output.columns:
        output["future_5_trade_date"] = pd.to_datetime(output["future_5_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return output


def predict_one_anchor(
    df: pd.DataFrame,
    feature_cols: list[str],
    anchor_date: pd.Timestamp,
    train_start: str,
    train_end: str,
    threshold: float,
    top_n: int,
    label_up_threshold: float,
    label_down_threshold: float,
    exclude_st: bool,
    exclude_st_prediction: bool,
    target_mode: str,
    top_quantile: float,
    apply_overheat_penalty: bool,
) -> pd.DataFrame:
    train_df, predict_df = make_train_predict_sets(
        df,
        anchor_date,
        train_start,
        train_end,
        label_up_threshold,
        label_down_threshold,
        exclude_st,
        exclude_st_prediction,
        target_mode,
        top_quantile,
    )
    model = fit_model(train_df, feature_cols)
    prediction = build_prediction_output(
        model,
        predict_df,
        feature_cols,
        threshold,
        top_n,
        target_mode,
        top_quantile,
        apply_overheat_penalty,
    )
    prediction["anchor_date"] = anchor_date.strftime("%Y-%m-%d")
    prediction["train_start"] = train_df[DATE_COL].min().strftime("%Y-%m-%d")
    prediction["train_end"] = train_df[DATE_COL].max().strftime("%Y-%m-%d")
    prediction["train_rows"] = len(train_df)
    prediction["train_dates"] = train_df[DATE_COL].nunique()
    prediction["train_label_up_threshold"] = label_up_threshold
    prediction["train_label_down_threshold"] = label_down_threshold
    prediction["train_exclude_st"] = int(exclude_st)
    prediction["prediction_exclude_st"] = int(exclude_st_prediction)
    prediction["target_mode"] = target_mode
    prediction["top_quantile"] = top_quantile
    prediction["overheat_penalty_enabled"] = int(apply_overheat_penalty)
    return prediction


def safe_date_tag(value: str) -> str:
    return value.replace("-", "") if value else "all"


def output_name(range_tag: str, target_mode: str, top_quantile: float, top_n: int) -> str:
    scope_tag = f"_Top{top_n}输出" if top_n > 0 else ""
    if target_mode == "top_quantile":
        quantile_tag = f"Top{int(round(top_quantile * 100))}"
        return f"个股5日{quantile_tag}预测_LightGBM{scope_tag}_{range_tag}_系统日期{date.today():%Y%m%d}.csv"
    return f"个股5日方向预测_LightGBM{scope_tag}_{range_tag}_系统日期{date.today():%Y%m%d}.csv"


def main() -> None:
    args = parse_args()
    stock_file = Path(args.stock_file).resolve()
    stock_list_file = Path(args.stock_list).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    stock_list = load_stock_list(stock_list_file)
    df = load_stock_features(stock_file)
    df = df[df["symbol"].isin(set(stock_list["symbol"]))].copy()
    if df.empty:
        raise RuntimeError("股票清单中的代码在个股特征数据中都不存在")

    feature_cols = select_feature_columns(df)
    anchors = anchor_dates_for_range(df, normalize_date(args.start_date), normalize_date(args.end_date), args.min_anchor_coverage)
    frames: list[pd.DataFrame] = []
    for _, anchor_row in anchors.iterrows():
        anchor_date = anchor_row[DATE_COL]
        train_start = (anchor_date - pd.Timedelta(days=args.lookback_days)).strftime("%Y-%m-%d")
        prediction = predict_one_anchor(
            df,
            feature_cols,
            anchor_date,
            train_start,
            "",
            args.threshold,
            args.top_n,
            args.label_up_threshold,
            args.label_down_threshold,
            args.exclude_st,
            args.exclude_st_prediction,
            args.target_mode,
            args.top_quantile,
            args.enable_overheat_penalty,
        )
        prediction["anchor_stock_count"] = int(anchor_row["stock_count"])
        prediction["anchor_coverage_ratio"] = float(anchor_row["coverage_ratio"])
        frames.append(prediction)
        if args.target_mode == "top_quantile":
            metrics = score_top_quantile_prediction(prediction, args.threshold)
            print(f"{anchor_date:%Y-%m-%d} done: rows={len(prediction)}, top_quantile_accuracy={metrics['top_quantile_accuracy']}")
        else:
            metrics = score_prediction(prediction, args.threshold)
            print(f"{anchor_date:%Y-%m-%d} done: rows={len(prediction)}, accuracy={metrics['accuracy']}")

    result = pd.concat(frames, ignore_index=True)
    range_tag = f"{safe_date_tag(normalize_date(args.start_date))}_{safe_date_tag(normalize_date(args.end_date))}"
    prediction_path = output_dir / output_name(range_tag, args.target_mode, args.top_quantile, args.top_n)

    result.to_csv(prediction_path, index=False, encoding="utf-8-sig")
    print(f"预测结果: {prediction_path}")


if __name__ == "__main__":
    main()
