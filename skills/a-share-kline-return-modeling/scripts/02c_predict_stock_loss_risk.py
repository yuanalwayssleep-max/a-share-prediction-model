#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from lightgbm import LGBMClassifier
except Exception:  # pragma: no cover - depends on local environment
    LGBMClassifier = None


SKILL_DIR = Path(__file__).resolve().parents[1]
STOCK_MODEL_SCRIPT = SKILL_DIR / "scripts" / "01_predict_stock_direction.py"
DEFAULT_STOCK_FEATURE_FILE = SKILL_DIR / "data" / "个股k线特征数据.csv"
DEFAULT_STOCK_LIST_FILE = SKILL_DIR / "data" / "00_股票清单.csv"
DEFAULT_OUTPUT_DIR = SKILL_DIR / "outputs" / "stock_loss_risk_predictions"

DATE_COL = "trade_date"
RETURN_LABEL_COL = "future_5_return"
LOSS_LABEL_COL = "label_5d_loss05"
MODEL_LABEL_COL = "model_loss05_label"


def load_stock_model_module():
    spec = importlib.util.spec_from_file_location("stock_direction_model", STOCK_MODEL_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载脚本: {STOCK_MODEL_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stock_model = load_stock_model_module()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="个股未来5日亏损风险预测：预测 future_5_return <= -5% 的概率")
    parser.add_argument("--stock-list", default=str(DEFAULT_STOCK_LIST_FILE), help="股票清单路径")
    parser.add_argument("--stock-file", default=str(DEFAULT_STOCK_FEATURE_FILE), help="个股特征数据路径")
    parser.add_argument("--start-date", required=True, help="预测起始锚点日，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="预测结束锚点日，格式 YYYY-MM-DD")
    parser.add_argument("--lookback-days", type=int, default=730, help="每个锚点日前向训练窗口自然日数；默认730天")
    parser.add_argument("--min-anchor-coverage", type=float, default=0.9, help="锚点日最低股票覆盖率")
    parser.add_argument("--loss-threshold", type=float, default=-0.05, help="亏损风险标签阈值，默认 future_5_return <= -5%%")
    parser.add_argument("--top-n", type=int, default=0, help="输出风险最低的前N只；0表示输出全部")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="输出目录")
    return parser.parse_args()


def normalize_date(value: str) -> str:
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def safe_date_tag(value: str) -> str:
    return value.replace("-", "") if value else "all"


def make_train_predict_sets(
    df: pd.DataFrame,
    anchor_date: pd.Timestamp,
    train_start: str,
    loss_threshold: float,
    exclude_st: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    train_df = df.loc[
        (df[DATE_COL] < anchor_date)
        & (df[DATE_COL] >= pd.to_datetime(train_start))
        & df["is_training_eligible"].eq(1)
        & df[RETURN_LABEL_COL].notna()
        & df["future_5_trade_date"].notna()
        & (df["future_5_trade_date"] < anchor_date)
    ].copy()
    predict_df = df.loc[df[DATE_COL].eq(anchor_date)].copy()
    if exclude_st and "is_st" in train_df.columns:
        train_df = train_df.loc[train_df["is_st"].fillna(0).eq(0)].copy()
    if exclude_st and "is_st" in predict_df.columns:
        predict_df = predict_df.loc[predict_df["is_st"].fillna(0).eq(0)].copy()

    if LOSS_LABEL_COL in train_df.columns:
        train_df[MODEL_LABEL_COL] = train_df[LOSS_LABEL_COL].astype(float)
    else:
        train_df[MODEL_LABEL_COL] = (train_df[RETURN_LABEL_COL] <= loss_threshold).astype(int)
    train_df = train_df.loc[train_df[MODEL_LABEL_COL].notna()].copy()
    train_df[MODEL_LABEL_COL] = train_df[MODEL_LABEL_COL].astype(int)

    if train_df.empty:
        raise RuntimeError(f"{anchor_date:%Y-%m-%d} 训练样本为空")
    if train_df[MODEL_LABEL_COL].nunique() < 2:
        raise RuntimeError(f"{anchor_date:%Y-%m-%d} 训练样本只有单一亏损标签")
    if predict_df.empty:
        raise RuntimeError(f"{anchor_date:%Y-%m-%d} 预测样本为空")
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
        reg_lambda=1.5,
        objective="binary",
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
        verbosity=-1,
    )
    model.fit(train_df[feature_cols], train_df[MODEL_LABEL_COL])
    return model


def predict_one_anchor(
    df: pd.DataFrame,
    feature_cols: list[str],
    anchor_date: pd.Timestamp,
    lookback_days: int,
    loss_threshold: float,
    top_n: int,
) -> pd.DataFrame:
    train_start = (anchor_date - pd.Timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    train_df, predict_df = make_train_predict_sets(df, anchor_date, train_start, loss_threshold)
    model = fit_model(train_df, feature_cols)
    loss_prob = model.predict_proba(predict_df[feature_cols])[:, 1]

    output_cols = [
        "trade_date",
        "symbol",
        "name",
        "board",
        "industry",
        "close",
        "pct_chg",
        "turnover_pct",
        "future_5_trade_date",
        "future_5_return",
        "label_5d_loss05",
    ]
    out = predict_df[[col for col in output_cols if col in predict_df.columns]].copy()
    out["risk_5d_loss05_prob"] = loss_prob
    out["rank_by_loss05_risk"] = out["risk_5d_loss05_prob"].rank(method="first", ascending=True).astype(int)
    out["loss_label_threshold"] = loss_threshold
    out["train_start"] = train_df[DATE_COL].min().strftime("%Y-%m-%d")
    out["train_end"] = train_df[DATE_COL].max().strftime("%Y-%m-%d")
    out["train_rows"] = len(train_df)
    out["train_dates"] = train_df[DATE_COL].nunique()
    out["train_loss05_rate"] = float(train_df[MODEL_LABEL_COL].mean())
    out["model_type"] = "LightGBM_LossRisk"
    out = out.sort_values(["risk_5d_loss05_prob", "symbol"], ascending=[True, True]).reset_index(drop=True)
    if top_n > 0:
        out = out.head(top_n).copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    if "future_5_trade_date" in out.columns:
        out["future_5_trade_date"] = pd.to_datetime(out["future_5_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    return out


def output_name(start_date: str, end_date: str) -> str:
    return f"个股5日亏损风险预测_LightGBM_{safe_date_tag(start_date)}_{safe_date_tag(end_date)}_系统日期{date.today():%Y%m%d}.csv"


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    stock_list = stock_model.load_stock_list(Path(args.stock_list).resolve())
    df = stock_model.load_stock_features(Path(args.stock_file).resolve())
    df = df[df["symbol"].isin(set(stock_list["symbol"]))].copy()
    if df.empty:
        raise RuntimeError("股票清单中的代码在个股特征数据中都不存在")
    start_date = normalize_date(args.start_date)
    end_date = normalize_date(args.end_date)
    df = stock_model.add_cross_section_features(df)
    feature_cols = stock_model.select_feature_columns(df)
    anchors = stock_model.anchor_dates_for_range(
        df,
        start_date,
        end_date,
        args.min_anchor_coverage,
    )

    frames = []
    for _, anchor_row in anchors.iterrows():
        anchor_date = anchor_row[DATE_COL]
        prediction = predict_one_anchor(
            df,
            feature_cols,
            anchor_date,
            args.lookback_days,
            args.loss_threshold,
            args.top_n,
        )
        prediction["anchor_stock_count"] = int(anchor_row["stock_count"])
        prediction["anchor_coverage_ratio"] = float(anchor_row["coverage_ratio"])
        frames.append(prediction)
        print(f"{anchor_date:%Y-%m-%d} done: rows={len(prediction)}")

    result = pd.concat(frames, ignore_index=True)
    output_path = output_dir / output_name(start_date, end_date)
    result.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"亏损风险预测结果: {output_path}")


if __name__ == "__main__":
    main()
