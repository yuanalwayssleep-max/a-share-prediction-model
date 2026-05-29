#!/usr/bin/env python3
"""Train V1 stock cross-sectional strength model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


DEFAULT_FEATURES = Path("skills/a-share-kline-return-modeling/data/clean_stock_features.csv")
DEFAULT_OUTPUT_DIR = Path("skills/a-share-kline-return-modeling/outputs/stock_rank_predictions")

FORBIDDEN_PREFIXES = ("future_", "label_", "entry_", "exit_", "actual_")
FORBIDDEN_SUFFIXES = ("_label",)
FORBIDDEN_COLUMNS = {
    "trade_date",
    "symbol",
    "name",
    "industry",
    "board",
    "source_duplicate_row",
    "gross_future_5_return",
    "buy_cost_rate",
    "sell_cost_rate",
    "buy_slippage_rate",
    "sell_slippage_rate",
    "tradable_at_entry",
    "tradable_at_exit",
    "limit_up_at_entry",
    "limit_down_during_holding",
    "suspended_during_holding",
    "forced_exit_delay_days",
    "daily_stock_count",
    "strong_rank_level",
    "absolute_strong_level",
}

SAFE_PREDICTION_FEATURES = [
    "ret_5",
    "ret_20",
    "amount_ratio_5",
    "turnover_pct",
    "range_pos_20",
    "volatility_5",
    "near_limit_up",
    "overheat_flag",
    "low_liquidity_flag",
]


def load_features(path: Path) -> pd.DataFrame:
    date_cols = ["trade_date", "entry_trade_date", "exit_trade_date", "actual_exit_trade_date"]
    return pd.read_csv(path, encoding="utf-8-sig", parse_dates=[c for c in date_cols if c])


def select_feature_columns(df: pd.DataFrame) -> list[str]:
    cols: list[str] = []
    for col in df.columns:
        if col in FORBIDDEN_COLUMNS:
            continue
        if col.startswith(FORBIDDEN_PREFIXES):
            continue
        if col.endswith(FORBIDDEN_SUFFIXES):
            continue
        if pd.api.types.is_bool_dtype(df[col]) or pd.api.types.is_numeric_dtype(df[col]):
            cols.append(col)
    return cols


def make_model():
    try:
        from lightgbm import LGBMRegressor

        return LGBMRegressor(
            objective="regression",
            n_estimators=120,
            learning_rate=0.05,
            num_leaves=31,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=20260529,
            verbosity=-1,
        ), "LightGBMRegressor"
    except Exception:
        from sklearn.ensemble import HistGradientBoostingRegressor

        return HistGradientBoostingRegressor(max_iter=120, learning_rate=0.05, random_state=20260529), "HistGradientBoostingRegressor"


def eligible_rows(df: pd.DataFrame) -> pd.Series:
    mask = df["future_5_return_rank_pct"].notna()
    if "is_st" in df.columns:
        mask &= df["is_st"].fillna(0).astype(int) == 0
    if "listing_days" in df.columns:
        mask &= df["listing_days"].fillna(0) >= 60
    if "low_liquidity_flag" in df.columns:
        mask &= df["low_liquidity_flag"].fillna(1).astype(int) == 0
    return mask


def train_and_predict(
    df: pd.DataFrame,
    start_date: str,
    end_date: str,
    top_n: int,
    train_window_days: int,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    df = df.sort_values(["trade_date", "symbol"]).copy()
    feature_cols = select_feature_columns(df)
    anchors = pd.date_range(start=start_date, end=end_date, freq="D")
    trade_dates = set(df["trade_date"].dropna())
    predictions: list[pd.DataFrame] = []
    truth_predictions: list[pd.DataFrame] = []
    model_name = ""
    diagnostics: list[dict[str, object]] = []

    for anchor in anchors:
        if anchor not in trade_dates:
            continue
        train_start = anchor - pd.Timedelta(days=train_window_days)
        train_mask = (
            eligible_rows(df)
            & (df["trade_date"] >= train_start)
            & (df["trade_date"] < anchor)
            & (df["exit_trade_date"] < anchor)
        )
        predict_mask = (df["trade_date"] == anchor)
        predict_df = df[predict_mask].copy()
        if "is_st" in predict_df.columns:
            predict_df = predict_df[predict_df["is_st"].fillna(0).astype(int) == 0]
        if "listing_days" in predict_df.columns:
            predict_df = predict_df[predict_df["listing_days"].fillna(0) >= 60]
        if "low_liquidity_flag" in predict_df.columns:
            predict_df = predict_df[predict_df["low_liquidity_flag"].fillna(1).astype(int) == 0]
        train_df = df[train_mask].dropna(subset=feature_cols + ["future_5_return_rank_pct"])
        predict_df = predict_df.dropna(subset=feature_cols)
        if len(train_df) < 200 or predict_df.empty:
            continue

        model, model_name = make_model()
        model.fit(train_df[feature_cols], train_df["future_5_return_rank_pct"])
        predict_df["rank_strength_score"] = model.predict(predict_df[feature_cols])
        predict_df["rank_strength_rank"] = predict_df["rank_strength_score"].rank(method="first", ascending=False)
        top = predict_df.sort_values(["rank_strength_score", "symbol"], ascending=[False, True]).head(top_n).copy()
        top["model_name"] = model_name
        top["anchor_date"] = anchor
        predictions.append(
            top[
                [
                    "trade_date",
                    "symbol",
                    "name",
                    "industry",
                    "rank_strength_score",
                    "rank_strength_rank",
                    "industry_strength_score",
                    "model_name",
                ]
                + [col for col in SAFE_PREDICTION_FEATURES if col in top.columns]
            ]
        )
        truth_predictions.append(
            top[
                [
                    "trade_date",
                    "symbol",
                    "name",
                    "industry",
                    "rank_strength_score",
                    "rank_strength_rank",
                    "industry_strength_score",
                    "model_name",
                    "future_5_return",
                    "future_5_return_rank",
                    "future_5_return_rank_pct",
                    "label_top10",
                    "label_top30",
                    "label_top50",
                ]
                + [col for col in SAFE_PREDICTION_FEATURES if col in top.columns]
            ]
        )
        diagnostics.append(
            {
                "trade_date": anchor.strftime("%Y-%m-%d"),
                "train_rows": len(train_df),
                "predict_rows": len(predict_df),
                "feature_count": len(feature_cols),
                "train_start": train_df["trade_date"].min().strftime("%Y-%m-%d"),
                "train_end": train_df["trade_date"].max().strftime("%Y-%m-%d"),
                "max_train_exit_trade_date": train_df["exit_trade_date"].max().strftime("%Y-%m-%d"),
            }
        )

    if not predictions:
        raise ValueError("No predictions generated. Check date range and data availability.")
    safe_predictions = pd.concat(predictions, ignore_index=True)
    with_truth = pd.concat(truth_predictions, ignore_index=True)
    metrics = {
        "model_name": model_name,
        "start_date": start_date,
        "end_date": end_date,
        "top_n": top_n,
        "train_window_days": train_window_days,
        "feature_count": len(feature_cols),
        "feature_columns": feature_cols,
        "prediction_days": int(safe_predictions["trade_date"].nunique()),
        "avg_future_5_return_topn": float(with_truth["future_5_return"].mean()),
        "avg_hit_top10_count": float(with_truth.groupby("trade_date")["label_top10"].sum().mean()),
        "avg_hit_top30_count": float(with_truth.groupby("trade_date")["label_top30"].sum().mean()),
        "diagnostics": diagnostics,
    }
    return safe_predictions, with_truth, metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--start-date", default="2025-05-01")
    parser.add_argument("--end-date", default="2025-05-31")
    parser.add_argument("--top-n", type=int, default=30)
    parser.add_argument("--train-window-days", type=int, default=365)
    args = parser.parse_args()

    df = load_features(args.features)
    predictions, with_truth, metrics = train_and_predict(
        df,
        start_date=args.start_date,
        end_date=args.end_date,
        top_n=args.top_n,
        train_window_days=args.train_window_days,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pred_path = args.output_dir / "predictions.csv"
    truth_path = args.output_dir / "predictions_with_truth.csv"
    metrics_path = Path("skills/a-share-kline-return-modeling/outputs/evaluation/stock_rank_model_metrics.json")
    predictions.to_csv(pred_path, index=False, encoding="utf-8-sig")
    with_truth.to_csv(truth_path, index=False, encoding="utf-8-sig")
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in metrics.items() if k not in {"feature_columns", "diagnostics"}}, ensure_ascii=False, indent=2))
    print(f"wrote {pred_path}")
    print(f"wrote {truth_path}")


if __name__ == "__main__":
    main()
