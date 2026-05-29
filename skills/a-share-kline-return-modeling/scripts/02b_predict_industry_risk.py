#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score

try:
    from lightgbm import LGBMClassifier
except Exception:  # pragma: no cover - depends on local environment
    LGBMClassifier = None


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INDUSTRY_FEATURE_FILE = SKILL_DIR / "data" / "行业指数特征数据.csv"
DEFAULT_OUTPUT_DIR = SKILL_DIR / "outputs" / "industry_risk_predictions"

DATE_COL = "trade_date"
LABEL_COL = "future_5_up_label"
RETURN_LABEL_COL = "future_5_return"
MODEL_LABEL_COL = "model_up_label"

FORBIDDEN_EXACT_COLUMNS = {
    DATE_COL,
    "future_5_trade_date",
    "future_5_close",
    "future_5_return",
    "future_5_direction",
    "future_5_up_label",
}
FORBIDDEN_PREFIXES = ("future_",)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="未来5日行业风险预测：按日期范围逐日锚点预测申万行业")
    parser.add_argument("--industry-file", default=str(DEFAULT_INDUSTRY_FEATURE_FILE), help="行业指数特征数据.csv 路径")
    parser.add_argument("--start-date", required=True, help="预测起始锚点日，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="预测结束锚点日，格式 YYYY-MM-DD")
    parser.add_argument("--lookback-days", type=int, default=365, help="每个锚点日前向训练窗口自然日数")
    parser.add_argument("--label-up-threshold", type=float, default=0.01, help="训练上涨标签阈值，默认未来5日收益 >= 1%%")
    parser.add_argument("--label-down-threshold", type=float, default=-0.01, help="训练下跌标签阈值，默认未来5日收益 <= -1%%")
    parser.add_argument("--threshold", type=float, default=0.5, help="上涨方向判定阈值")
    parser.add_argument("--high-risk-down-prob", type=float, default=0.62, help="高风险下跌概率阈值")
    parser.add_argument("--low-risk-down-prob", type=float, default=0.45, help="低风险下跌概率阈值")
    parser.add_argument("--levels", default="L1,L2,L3", help="预测行业级别，逗号分隔；默认 L1,L2,L3")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="输出目录")
    return parser.parse_args()


def normalize_date(value: str) -> str:
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def safe_date_tag(value: str) -> str:
    return value.replace("-", "")


def load_industry_features(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"未找到行业指数特征表: {path}")
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"industry_index_code": str, "industry_index_name": str})
    df[DATE_COL] = pd.to_datetime(df[DATE_COL], errors="coerce")
    df["future_5_trade_date"] = pd.to_datetime(df["future_5_trade_date"], errors="coerce")
    df = df.dropna(subset=[DATE_COL, "industry_index_code", "industry_index_name"]).copy()
    return df


def select_feature_columns(df: pd.DataFrame) -> list[str]:
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    features = [
        col
        for col in numeric_cols
        if col not in FORBIDDEN_EXACT_COLUMNS
        and not any(col.startswith(prefix) for prefix in FORBIDDEN_PREFIXES)
    ]
    if not features:
        raise RuntimeError("没有可用行业特征列，请检查行业指数特征表")
    return features


def anchor_dates_for_range(df: pd.DataFrame, start_date: str, end_date: str) -> list[pd.Timestamp]:
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    if start > end:
        raise ValueError("start-date 不能晚于 end-date")
    dates = df.loc[df[DATE_COL].between(start, end), DATE_COL].drop_duplicates().sort_values().tolist()
    if not dates:
        raise RuntimeError(f"{start:%Y-%m-%d} 到 {end:%Y-%m-%d} 没有可用行业锚点日")
    return dates


def make_train_predict_sets(
    df: pd.DataFrame,
    anchor_date: pd.Timestamp,
    train_start: str,
    label_up_threshold: float,
    label_down_threshold: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if label_down_threshold >= label_up_threshold:
        raise ValueError("label-down-threshold 必须小于 label-up-threshold")
    train_df = df.loc[
        (df[DATE_COL] < anchor_date)
        & (df[DATE_COL] >= pd.to_datetime(train_start))
        & df[RETURN_LABEL_COL].notna()
        & df[LABEL_COL].notna()
        & df["future_5_trade_date"].notna()
        & (df["future_5_trade_date"] < anchor_date)
    ].copy()
    train_df = train_df.loc[
        (train_df[RETURN_LABEL_COL] >= label_up_threshold)
        | (train_df[RETURN_LABEL_COL] <= label_down_threshold)
    ].copy()
    train_df[MODEL_LABEL_COL] = (train_df[RETURN_LABEL_COL] >= label_up_threshold).astype(int)
    predict_df = df.loc[df[DATE_COL].eq(anchor_date)].copy()
    if train_df.empty:
        raise RuntimeError(f"{anchor_date:%Y-%m-%d} 训练样本为空")
    if predict_df.empty:
        raise RuntimeError(f"{anchor_date:%Y-%m-%d} 预测样本为空")
    return train_df, predict_df


def fit_model(train_df: pd.DataFrame, feature_cols: list[str]):
    if LGBMClassifier is None:
        raise RuntimeError("当前环境未安装或无法加载 lightgbm，请先安装 lightgbm 和 libomp")
    model = LGBMClassifier(
        n_estimators=180,
        learning_rate=0.03,
        num_leaves=15,
        min_child_samples=20,
        subsample=0.9,
        colsample_bytree=0.9,
        reg_lambda=1.0,
        objective="binary",
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
        verbosity=-1,
    )
    model.fit(train_df[feature_cols], train_df[MODEL_LABEL_COL].astype(int))
    return model


def risk_level(down_prob: float, high_threshold: float, low_threshold: float) -> str:
    if down_prob >= high_threshold:
        return "高风险"
    if down_prob >= low_threshold:
        return "中风险"
    return "低风险"


def industry_regime(row: pd.Series) -> str:
    ret5 = row.get("industry_index_ret_5", np.nan)
    ret20 = row.get("industry_index_ret_20", np.nan)
    range_pos = row.get("industry_index_range_pos_20", np.nan)
    ret5_rank = row.get("industry_index_ret_5_xrank", np.nan)
    down_prob = row.get("predicted_industry_down_prob", np.nan)
    if down_prob >= 0.62 and ret5 < 0 and ret20 < 0:
        return "行业弱势延续"
    if down_prob >= 0.58 and range_pos >= 0.70 and ret5 >= 0:
        return "行业高位回落风险"
    if down_prob <= 0.45 and ret5 > 0 and (pd.isna(ret5_rank) or ret5_rank >= 0.50):
        return "行业顺风"
    if ret5 < 0 and range_pos <= 0.35:
        return "行业超跌修复"
    return "行业中性"


def predict_one_anchor(
    df: pd.DataFrame,
    feature_cols: list[str],
    anchor_date: pd.Timestamp,
    lookback_days: int,
    threshold: float,
    label_up_threshold: float,
    label_down_threshold: float,
    high_risk_down_prob: float,
    low_risk_down_prob: float,
) -> pd.DataFrame:
    train_start = (anchor_date - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    train_df, predict_df = make_train_predict_sets(df, anchor_date, train_start, label_up_threshold, label_down_threshold)
    model = fit_model(train_df, feature_cols)
    up_prob = model.predict_proba(predict_df[feature_cols])[:, 1]
    output_cols = [
        "trade_date",
        "industry_index_code",
        "industry_index_name",
        "industry_index_level",
        "industry_index_close",
        "industry_index_pct_chg",
        "industry_index_ret_5",
        "industry_index_ret_20",
        "industry_index_range_pos_20",
        "industry_index_ret_5_xrank",
        "future_5_trade_date",
        "future_5_return",
        "future_5_direction",
        "future_5_up_label",
    ]
    out = predict_df[[col for col in output_cols if col in predict_df.columns]].copy()
    out["predicted_industry_up_prob"] = up_prob
    out["predicted_industry_down_prob"] = 1 - up_prob
    out["predicted_industry_direction"] = np.where(out["predicted_industry_up_prob"] >= threshold, "上涨", "下跌")
    out["industry_risk_level"] = [
        risk_level(prob, high_risk_down_prob, low_risk_down_prob)
        for prob in out["predicted_industry_down_prob"]
    ]
    out["industry_regime"] = out.apply(industry_regime, axis=1)
    out["direction_threshold"] = threshold
    out["train_start"] = train_df[DATE_COL].min().strftime("%Y-%m-%d")
    out["train_end"] = train_df[DATE_COL].max().strftime("%Y-%m-%d")
    out["train_rows"] = len(train_df)
    out["train_dates"] = train_df[DATE_COL].nunique()
    out["model_type"] = "LightGBM"
    out["train_label_up_threshold"] = label_up_threshold
    out["train_label_down_threshold"] = label_down_threshold
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["future_5_trade_date"] = pd.to_datetime(out["future_5_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    if out["future_5_up_label"].notna().any():
        labeled = out[out["future_5_up_label"].notna()].copy()
        out["anchor_accuracy"] = accuracy_score(
            labeled["future_5_up_label"].astype(int),
            (labeled["predicted_industry_up_prob"] >= threshold).astype(int),
        )
    else:
        out["anchor_accuracy"] = np.nan
    return out


def output_name(start_date: str, end_date: str) -> str:
    return f"行业5日风险预测_LightGBM_{safe_date_tag(start_date)}_{safe_date_tag(end_date)}_系统日期{date.today():%Y%m%d}.csv"


def main() -> None:
    args = parse_args()
    industry_file = Path(args.industry_file).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    df = load_industry_features(industry_file)
    levels = {item.strip().upper() for item in args.levels.split(",") if item.strip()}
    if levels:
        df = df[df["industry_index_level"].astype(str).str.upper().isin(levels)].copy()
    if df.empty:
        raise RuntimeError("行业特征表在指定级别下为空")

    feature_cols = select_feature_columns(df)
    start_date = normalize_date(args.start_date)
    end_date = normalize_date(args.end_date)
    anchors = anchor_dates_for_range(df, start_date, end_date)

    frames: list[pd.DataFrame] = []
    for anchor_date in anchors:
        prediction = predict_one_anchor(
            df,
            feature_cols,
            anchor_date,
            args.lookback_days,
            args.threshold,
            args.label_up_threshold,
            args.label_down_threshold,
            args.high_risk_down_prob,
            args.low_risk_down_prob,
        )
        frames.append(prediction)
        print(f"{anchor_date:%Y-%m-%d} done: rows={len(prediction)}, accuracy={prediction['anchor_accuracy'].iloc[0]}")

    result = pd.concat(frames, ignore_index=True)
    output_path = output_dir / output_name(start_date, end_date)
    result.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"预测结果: {output_path}")


if __name__ == "__main__":
    main()
