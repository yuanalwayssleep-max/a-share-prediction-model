#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from lightgbm import LGBMClassifier
except Exception:  # pragma: no cover - depends on local environment
    LGBMClassifier = None


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_STOCK_FEATURE_FILE = SKILL_DIR / "data" / "个股k线特征数据.csv"
DEFAULT_STOCK_LIST_FILE = SKILL_DIR / "data" / "00_股票清单.csv"
DEFAULT_OUTPUT_DIR = SKILL_DIR / "outputs" / "stock_direction_predictions"

DATE_COL = "trade_date"
RETURN_LABEL_COL = "future_5_return"
MODEL_LABEL_COL = "model_up_label"
SAMPLE_WEIGHT_COL = "sample_weight"

CANDIDATE_TOP_N = 20
LABEL_UP_THRESHOLD = 0.20
PREDICTION_THRESHOLD = 0.50
FEATURE_SET_NAME = "compact60"

FEATURE_COLUMNS = [
    "amp_mean_5",
    "turnover_pct",
    "dist_high_60",
    "industry_index_ret_5_xrank",
    "dist_high_20",
    "market_up_ratio_xrank",
    "amp_mean_3",
    "industry_ret_20_xrank",
    "dist_low_60",
    "dist_low_20",
    "industry_index_volatility_5",
    "industry_avg_turnover_pct",
    "market_ret_5_ge05_ratio",
    "ret_3_xrank",
    "ret_3_minus_ret_10",
    "industry_index_ret_20_xrank",
    "stock_vs_industry_range_pos_20",
    "stock_industry_range_pos_20_rank",
    "industry_index_amount_ratio_5",
    "volatility_5_xrank",
    "stock_vs_industry_index_ret_20",
    "industry_index_ret_20",
    "volatility_10_xrank",
    "range_pos_60",
    "volatility_10",
    "pullback_setup_score",
    "industry_index_ret_5",
    "industry_avg_range_pos_20",
    "stock_vs_industry_ret_5",
    "stock_vs_industry_turnover_pct",
    "range_pos_60_xrank",
    "industry_index_range_pos_20",
    "ret_10",
    "ret_10_xrank",
    "volatility_5",
    "stock_industry_ret_20_rank",
    "stock_market_ret_5_minus_ret_20_rank",
    "turnover_amount_strength_5",
    "stock_market_turnover_rank",
    "volatility_3",
    "stock_industry_turnover_rank",
    "industry_avg_ret_20",
    "stock_vs_industry_ret_20",
    "industry_ret_5_xrank",
    "strong_pullback_failure_score",
    "market_ret_5_le_neg05_ratio",
    "industry_up_ratio_xrank",
    "industry_ret_20_mean",
    "ret_5_minus_ret_20",
    "close_ma_ratio_5",
    "stock_industry_amount_ratio_5_rank",
    "industry_index_close_ma_ratio_5",
    "stock_vs_industry_index_ret_5",
    "stock_market_range_pos_20_rank",
    "pullback_setup_score_xrank",
    "stock_industry_momentum_improve_rank",
    "ret_1_minus_ret_5",
    "close_position_in_day",
    "stock_market_momentum_improve_rank",
    "ret_2_minus_ret_5",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="个股未来5日强收益预测：每日输出Top20候选池")
    parser.add_argument("--stock-list", default=str(DEFAULT_STOCK_LIST_FILE), help="股票清单路径")
    parser.add_argument("--stock-file", default=str(DEFAULT_STOCK_FEATURE_FILE), help="个股特征数据路径")
    parser.add_argument("--start-date", required=True, help="预测起始锚点日，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="预测结束锚点日，格式 YYYY-MM-DD")
    parser.add_argument("--lookback-days", type=int, default=730, help="每个锚点日前向训练窗口自然日数")
    parser.add_argument("--train-start-date", default="", help="显式训练起始日期，格式 YYYY-MM-DD")
    parser.add_argument("--train-end-date", default="", help="显式特征结束日期，格式 YYYY-MM-DD")
    parser.add_argument("--min-anchor-coverage", type=float, default=0.9, help="锚点日最低股票覆盖率")
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
    df["future_5_trade_date"] = pd.to_datetime(df["future_5_trade_date"], errors="coerce")
    return df.dropna(subset=[DATE_COL, "symbol"]).copy()


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


def add_cross_section_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    rank_cols = [
        "pct_chg",
        "turnover_pct",
        "ret_1",
        "ret_2",
        "ret_3",
        "ret_5",
        "ret_10",
        "ret_20",
        "volatility_5",
        "volatility_10",
        "range_pos_20",
        "range_pos_60",
        "amount_ratio_3",
        "amount_ratio_5",
        "vol_ratio_3",
        "pullback_setup_score",
        "momentum_continuation_score",
        "overextended_momentum_score",
        "terminal_chase_risk_score",
        "strong_pullback_failure_score",
        "stock_vs_market_pct_chg",
        "stock_vs_industry_pct_chg",
        "industry_up_ratio",
        "industry_avg_pct_chg",
        "market_up_ratio",
        "market_avg_pct_chg",
    ]
    for col in rank_cols:
        if col in df.columns:
            df[f"{col}_xrank"] = df.groupby(DATE_COL)[col].rank(method="average", pct=True)

    if {"industry", "ret_5"}.issubset(df.columns):
        df["industry_ret_5_mean"] = df.groupby([DATE_COL, "industry"])["ret_5"].transform("mean")
        df["industry_ret_5_xrank"] = df.groupby(DATE_COL)["industry_ret_5_mean"].rank(method="average", pct=True)
    if {"industry", "ret_20"}.issubset(df.columns):
        df["industry_ret_20_mean"] = df.groupby([DATE_COL, "industry"])["ret_20"].transform("mean")
        df["industry_ret_20_xrank"] = df.groupby(DATE_COL)["industry_ret_20_mean"].rank(method="average", pct=True)
    return neutralize_small_industry_ranks(df)


def neutralize_small_industry_ranks(df: pd.DataFrame, min_industry_count: int = 5) -> pd.DataFrame:
    if "industry_stock_count" not in df.columns:
        return df
    rank_fallback = {
        "stock_industry_pct_chg_rank": "stock_market_pct_chg_rank",
        "stock_industry_ret_5_rank": "stock_market_ret_5_rank",
        "stock_industry_ret_20_rank": "stock_market_ret_20_rank",
        "stock_industry_turnover_rank": "stock_market_turnover_rank",
        "stock_industry_amount_ratio_5_rank": "stock_market_amount_ratio_5_rank",
        "stock_industry_range_pos_20_rank": "stock_market_range_pos_20_rank",
    }
    small_industry = df["industry_stock_count"].fillna(0) < min_industry_count
    for industry_rank_col, market_rank_col in rank_fallback.items():
        if industry_rank_col not in df.columns:
            continue
        if market_rank_col in df.columns:
            df.loc[small_industry, industry_rank_col] = df.loc[small_industry, market_rank_col]
        else:
            df.loc[small_industry, industry_rank_col] = 0.5
    if {"stock_industry_ret_5_rank", "stock_industry_ret_20_rank"}.issubset(df.columns):
        df["stock_industry_momentum_improve_rank"] = (
            df["stock_industry_ret_5_rank"] - df["stock_industry_ret_20_rank"]
        )
    return df


def select_feature_columns(df: pd.DataFrame) -> list[str]:
    missing = [col for col in FEATURE_COLUMNS if col not in df.columns]
    if missing:
        raise RuntimeError(f"当前最优特征缺失: {','.join(missing)}")
    selected = set(FEATURE_COLUMNS)
    return [col for col in df.select_dtypes(include=[np.number]).columns if col in selected]


def build_sample_weight(train_df: pd.DataFrame) -> pd.Series:
    returns = train_df[RETURN_LABEL_COL].astype(float)
    weights = pd.Series(1.0, index=train_df.index)

    positive = returns >= LABEL_UP_THRESHOLD
    upside_extra = ((returns - LABEL_UP_THRESHOLD) / 0.10).clip(lower=0, upper=3)
    weights.loc[positive] = 1.0 + upside_extra.loc[positive]
    weights.loc[returns >= 0.15] = np.maximum(weights.loc[returns >= 0.15], 3.0)
    weights.loc[returns >= 0.20] = np.maximum(weights.loc[returns >= 0.20], 4.0)

    bad_loss = returns <= -0.05
    fake_strong_loss = pd.Series(False, index=train_df.index)
    if "ret_5" in train_df.columns:
        fake_strong_loss |= bad_loss & (train_df["ret_5"] >= 0.05)
    if "ret_20" in train_df.columns:
        fake_strong_loss |= bad_loss & (train_df["ret_20"] >= 0.10)
    if "range_pos_20" in train_df.columns:
        fake_strong_loss |= bad_loss & (train_df["range_pos_20"] >= 0.80)
    if "stock_market_ret_5_rank" in train_df.columns:
        fake_strong_loss |= bad_loss & (train_df["stock_market_ret_5_rank"] >= 0.80)

    terminal_loss = pd.Series(False, index=train_df.index)
    if "terminal_chase_risk_score" in train_df.columns:
        terminal_loss |= bad_loss & (train_df["terminal_chase_risk_score"] >= 0.70)
    if "overextended_momentum_score" in train_df.columns:
        terminal_loss |= bad_loss & (train_df["overextended_momentum_score"] >= 0.70)
    if "strong_pullback_failure_score" in train_df.columns:
        terminal_loss |= bad_loss & (train_df["strong_pullback_failure_score"] >= 0.65)
    if "is_overextended_momentum" in train_df.columns:
        terminal_loss |= bad_loss & train_df["is_overextended_momentum"].eq(1)
    if "is_strong_pullback_failure" in train_df.columns:
        terminal_loss |= bad_loss & train_df["is_strong_pullback_failure"].eq(1)
    if "near_limit_after_runup_risk" in train_df.columns:
        terminal_loss |= bad_loss & train_df["near_limit_after_runup_risk"].eq(1)

    weak_loss = bad_loss.copy()
    if "ret_1" in train_df.columns:
        weak_loss &= train_df["ret_1"] <= -0.03
    if "ret_5" in train_df.columns:
        weak_loss |= bad_loss & (train_df["ret_5"] <= -0.03)
    if "ret_10" in train_df.columns:
        weak_loss |= bad_loss & (train_df["ret_10"] <= -0.03)

    weights.loc[bad_loss] = np.maximum(weights.loc[bad_loss], 2.5)
    weights.loc[weak_loss] = np.maximum(weights.loc[weak_loss], 5.0)
    weights.loc[fake_strong_loss] = np.maximum(weights.loc[fake_strong_loss], 4.0)
    weights.loc[terminal_loss] = np.maximum(weights.loc[terminal_loss], 6.0)
    return weights


def make_train_predict_sets(
    df: pd.DataFrame,
    anchor_date: pd.Timestamp,
    train_start: str,
    train_end: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_mask = df[DATE_COL] <= anchor_date
    if train_start:
        train_mask &= df[DATE_COL] >= pd.to_datetime(train_start)
    if train_end:
        train_mask &= df[DATE_COL] <= pd.to_datetime(train_end)

    train_df = df.loc[
        train_mask
        & df["is_training_eligible"].eq(1)
        & df[RETURN_LABEL_COL].notna()
        & df["future_5_trade_date"].notna()
        & (df["future_5_trade_date"] <= anchor_date)
    ].copy()
    if "is_st" in train_df.columns:
        train_df = train_df.loc[train_df["is_st"].fillna(0).eq(0)].copy()
    train_df[MODEL_LABEL_COL] = (train_df[RETURN_LABEL_COL] >= LABEL_UP_THRESHOLD).astype(int)
    train_df[SAMPLE_WEIGHT_COL] = build_sample_weight(train_df)

    predict_df = df.loc[df[DATE_COL].eq(anchor_date)].copy()
    if "is_st" in predict_df.columns:
        predict_df = predict_df.loc[predict_df["is_st"].fillna(0).eq(0)].copy()

    if train_df.empty:
        raise RuntimeError("训练样本为空：请检查锚点日、训练日期范围和标签列")
    if train_df[MODEL_LABEL_COL].nunique() < 2:
        raise RuntimeError("训练样本只有单一标签，无法训练分类模型")
    if predict_df.empty:
        raise RuntimeError(f"预测样本为空: {anchor_date:%Y-%m-%d}")
    return train_df, predict_df


def fit_model(train_df: pd.DataFrame, feature_cols: list[str]) -> LGBMClassifier:
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
    model.fit(
        train_df[feature_cols],
        train_df[MODEL_LABEL_COL].astype(int),
        sample_weight=train_df[SAMPLE_WEIGHT_COL],
    )
    return model


def build_terminal_risk_penalty(predict_df: pd.DataFrame) -> pd.DataFrame:
    penalty = pd.DataFrame(index=predict_df.index)

    def feature(name: str, default: float = 0.0) -> pd.Series:
        if name in predict_df.columns:
            return pd.to_numeric(predict_df[name], errors="coerce").fillna(default).clip(lower=0, upper=1)
        return pd.Series(default, index=predict_df.index, dtype=float)

    def raw_feature(name: str, default: float = 0.0) -> pd.Series:
        if name in predict_df.columns:
            return pd.to_numeric(predict_df[name], errors="coerce").fillna(default)
        return pd.Series(default, index=predict_df.index, dtype=float)

    overextended = feature("overextended_momentum_score")
    terminal = feature("terminal_chase_risk_score")
    pullback_failure = feature("strong_pullback_failure_score")
    ret_5_rank = feature("stock_market_ret_5_rank")
    ret_20_rank = feature("stock_market_ret_20_rank")
    turnover_rank = feature("stock_market_turnover_rank")
    range_pos_20 = feature("range_pos_20")
    turnover_pct = raw_feature("turnover_pct")
    close_position = raw_feature("close_position_in_day")
    ret_3 = raw_feature("ret_3")
    ret_5 = raw_feature("ret_5")
    ret_20 = raw_feature("ret_20")

    hot_trend_turnover = (ret_20_rank >= 0.90) & (range_pos_20 >= 0.75) & (turnover_rank >= 0.80)
    extreme_hot = (ret_5_rank >= 0.85) & (ret_20_rank >= 0.85) & (range_pos_20 >= 0.80)
    terminal_shape = (overextended >= 0.60) | (terminal >= 0.65) | (pullback_failure >= 0.60)
    extreme_turnover_chase = (
        (turnover_rank >= 0.95)
        & (turnover_pct >= 12)
        & (range_pos_20 >= 0.75)
        & (close_position >= 0.55)
    )
    ultra_turnover_high_position = (
        (turnover_pct >= 20)
        & (range_pos_20 >= 0.80)
        & (close_position >= 0.50)
    )
    weak_base_short_pop = (
        (ret_20 <= 0.02)
        & (ret_3 >= 0.06)
        & (ret_5 >= 0.05)
        & (ret_5_rank >= 0.70)
        & (close_position >= 0.60)
    )

    penalty["terminal_risk_penalty"] = 0.15 * overextended
    penalty.loc[hot_trend_turnover, "terminal_risk_penalty"] += 0.12
    penalty.loc[extreme_hot, "terminal_risk_penalty"] += 0.10
    penalty.loc[terminal_shape, "terminal_risk_penalty"] += 0.08
    penalty.loc[extreme_turnover_chase, "terminal_risk_penalty"] += 0.16
    penalty.loc[ultra_turnover_high_position, "terminal_risk_penalty"] += 0.14
    penalty.loc[weak_base_short_pop, "terminal_risk_penalty"] += 0.24
    penalty["terminal_risk_penalty"] = penalty["terminal_risk_penalty"].clip(upper=0.70)

    reasons: list[str] = []
    for idx in predict_df.index:
        row_reasons: list[str] = []
        if bool(hot_trend_turnover.loc[idx]):
            row_reasons.append("高位趋势+高换手")
        if bool(extreme_hot.loc[idx]):
            row_reasons.append("短中期极热")
        if bool(terminal_shape.loc[idx]):
            row_reasons.append("末端追高形态")
        if bool(extreme_turnover_chase.loc[idx]):
            row_reasons.append("极端换手高位收盘")
        if bool(ultra_turnover_high_position.loc[idx]):
            row_reasons.append("超高换手高位")
        if bool(weak_base_short_pop.loc[idx]):
            row_reasons.append("弱中期短线急拉")
        reasons.append(";".join(row_reasons))
    penalty["terminal_risk_reason"] = reasons
    return penalty


def build_prediction_output(model, predict_df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
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
        "label_5d_ge10",
        "label_5d_ge05",
        "label_5d_loss05",
        "daily_future_return_rank",
        "daily_future_return_top3_label",
    ]
    output = predict_df[[col for col in out_cols if col in predict_df.columns]].copy()
    prob = model.predict_proba(predict_df[feature_cols])[:, 1]
    output["predicted_return_threshold_prob"] = prob
    output["predicted_below_return_threshold_prob"] = 1 - prob
    output["probability_threshold"] = PREDICTION_THRESHOLD
    output["return_label_threshold"] = LABEL_UP_THRESHOLD
    output["actual_return_threshold_label"] = np.where(
        output[RETURN_LABEL_COL].notna(),
        (output[RETURN_LABEL_COL] >= LABEL_UP_THRESHOLD).astype(int),
        np.nan,
    )
    output["rank_by_return_threshold_prob"] = output["predicted_return_threshold_prob"].rank(
        method="first",
        ascending=False,
    ).astype(int)

    output = output.join(build_terminal_risk_penalty(predict_df))
    output["final_return_signal_score"] = output["predicted_return_threshold_prob"] - output["terminal_risk_penalty"]
    output = output.sort_values(
        ["final_return_signal_score", "predicted_return_threshold_prob", "symbol"],
        ascending=[False, False, True],
    ).head(CANDIDATE_TOP_N).reset_index(drop=True)
    output["rank_by_final_return_signal_score"] = np.arange(1, len(output) + 1)
    output["model_type"] = "LightGBM"
    output["trade_date"] = pd.to_datetime(output["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    if "future_5_trade_date" in output.columns:
        output["future_5_trade_date"] = pd.to_datetime(output["future_5_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return output


def format_date_or_empty(value: pd.Timestamp | str | None) -> str:
    if value is None or pd.isna(value):
        return ""
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def append_metadata(
    prediction: pd.DataFrame,
    train_df: pd.DataFrame,
    predict_df: pd.DataFrame,
    anchor_date: pd.Timestamp,
    requested_train_start: str,
    requested_train_end: str,
    feature_count: int,
) -> None:
    labeled_train_start = format_date_or_empty(train_df[DATE_COL].min())
    labeled_train_end = format_date_or_empty(train_df[DATE_COL].max())
    requested_end = requested_train_end or anchor_date.strftime("%Y-%m-%d")

    prediction["anchor_date"] = anchor_date.strftime("%Y-%m-%d")
    prediction["prediction_feature_date"] = anchor_date.strftime("%Y-%m-%d")
    prediction["prediction_feature_rows"] = len(predict_df)
    prediction["requested_train_start"] = requested_train_start
    prediction["requested_train_end"] = requested_end
    prediction["effective_labeled_train_start"] = labeled_train_start
    prediction["effective_labeled_train_end"] = labeled_train_end
    prediction["label_known_by_date"] = anchor_date.strftime("%Y-%m-%d")
    prediction["train_rows"] = len(train_df)
    prediction["train_dates"] = train_df[DATE_COL].nunique()
    prediction["train_label_up_threshold"] = LABEL_UP_THRESHOLD
    prediction["train_exclude_st"] = 1
    prediction["prediction_exclude_st"] = 1
    prediction["feature_set"] = FEATURE_SET_NAME
    prediction["feature_count"] = feature_count
    prediction["terminal_risk_penalty_enabled"] = 1


def summarize_top_pick_metrics(prediction: pd.DataFrame) -> str:
    returns = pd.to_numeric(prediction[RETURN_LABEL_COL], errors="coerce")
    top3_returns = returns.head(3)
    ge10 = int((top3_returns >= 0.10).sum())
    ge05 = int((top3_returns >= 0.05).sum())
    loss05 = int((top3_returns <= -0.05).sum())
    avg_return = top3_returns.mean()
    avg_text = "None" if pd.isna(avg_return) else f"{avg_return:.2%}"
    return (
        f"candidates={len(prediction)}, "
        f"raw_top3_ge10={ge10}/3, raw_top3_ge05={ge05}/3, "
        f"raw_top3_loss05={loss05}/3, raw_top3_avg_return={avg_text}"
    )


def predict_one_anchor(
    df: pd.DataFrame,
    feature_cols: list[str],
    anchor_date: pd.Timestamp,
    train_start: str,
    train_end: str,
) -> pd.DataFrame:
    train_df, predict_df = make_train_predict_sets(df, anchor_date, train_start, train_end)
    model = fit_model(train_df, feature_cols)
    prediction = build_prediction_output(model, predict_df, feature_cols)
    append_metadata(
        prediction,
        train_df,
        predict_df,
        anchor_date,
        train_start,
        train_end,
        len(feature_cols),
    )
    return prediction


def safe_date_tag(value: str) -> str:
    return value.replace("-", "") if value else "all"


def output_name(range_tag: str) -> str:
    return f"个股5日收益20pct预测_LightGBM_{FEATURE_SET_NAME}_Top{CANDIDATE_TOP_N}候选_{range_tag}_系统日期{date.today():%Y%m%d}.csv"


def main() -> None:
    args = parse_args()
    stock_file = Path(args.stock_file).resolve()
    stock_list_file = Path(args.stock_list).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    start_date = normalize_date(args.start_date)
    end_date = normalize_date(args.end_date)

    stock_list = load_stock_list(stock_list_file)
    df = load_stock_features(stock_file)
    df = df[df["symbol"].isin(set(stock_list["symbol"]))].copy()
    if df.empty:
        raise RuntimeError("股票清单中的代码在个股特征数据中都不存在")
    df = add_cross_section_features(df)

    feature_cols = select_feature_columns(df)
    print(
        f"fixed_config: label_up_threshold={LABEL_UP_THRESHOLD:.0%}, "
        f"feature_set={FEATURE_SET_NAME}, feature_count={len(feature_cols)}, candidate_top_n={CANDIDATE_TOP_N}"
    )

    anchors = anchor_dates_for_range(df, start_date, end_date, args.min_anchor_coverage)
    frames: list[pd.DataFrame] = []
    for _, anchor_row in anchors.iterrows():
        anchor_date = anchor_row[DATE_COL]
        train_start = normalize_date(args.train_start_date) if args.train_start_date else (anchor_date - pd.Timedelta(days=args.lookback_days)).strftime("%Y-%m-%d")
        train_end = normalize_date(args.train_end_date) if args.train_end_date else ""
        prediction = predict_one_anchor(df, feature_cols, anchor_date, train_start, train_end)
        prediction["anchor_stock_count"] = int(anchor_row["stock_count"])
        prediction["anchor_coverage_ratio"] = float(anchor_row["coverage_ratio"])
        frames.append(prediction)
        print(f"{anchor_date:%Y-%m-%d} done: rows={len(prediction)}, {summarize_top_pick_metrics(prediction)}")

    result = pd.concat(frames, ignore_index=True)
    range_tag = f"{safe_date_tag(start_date)}_{safe_date_tag(end_date)}"
    prediction_path = output_dir / output_name(range_tag)
    result.to_csv(prediction_path, index=False, encoding="utf-8-sig")
    print(f"预测结果: {prediction_path}")


if __name__ == "__main__":
    main()
