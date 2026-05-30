#!/usr/bin/env python3
"""Evaluate CR-20260529-002 M3-A Top50 recall-oriented model experiments.

This script is intentionally isolated from the main stock-rank training flow.
It does not replace the raw rank_pct regression model and does not write to
outputs/stock_rank_predictions.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


DEFAULT_FEATURES = Path("skills/a-share-kline-return-modeling/data/clean_stock_features.csv")
DEFAULT_OUTPUT_DIR = Path("skills/a-share-kline-return-modeling/outputs/evaluation")

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

EXPERIMENTS = [
    "raw_rank_pct_regression",
    "top30_classifier",
    "top50_classifier",
    "weighted_rank_pct_regression",
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


def eligible_rows(df: pd.DataFrame) -> pd.Series:
    mask = df["future_5_return_rank_pct"].notna()
    if "is_st" in df.columns:
        mask &= df["is_st"].fillna(0).astype(int) == 0
    if "listing_days" in df.columns:
        mask &= df["listing_days"].fillna(0) >= 60
    if "low_liquidity_flag" in df.columns:
        mask &= df["low_liquidity_flag"].fillna(1).astype(int) == 0
    return mask


def make_regressor():
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
        )
    except Exception:
        from sklearn.ensemble import HistGradientBoostingRegressor

        return HistGradientBoostingRegressor(max_iter=120, learning_rate=0.05, random_state=20260529)


def make_classifier():
    try:
        from lightgbm import LGBMClassifier

        return LGBMClassifier(
            objective="binary",
            n_estimators=120,
            learning_rate=0.05,
            num_leaves=31,
            subsample=0.9,
            colsample_bytree=0.9,
            class_weight="balanced",
            random_state=20260529,
            verbosity=-1,
        )
    except Exception:
        from sklearn.ensemble import HistGradientBoostingClassifier

        return HistGradientBoostingClassifier(max_iter=120, learning_rate=0.05, random_state=20260529)


def weighted_rank_sample_weight(train_df: pd.DataFrame) -> pd.Series:
    weight = pd.Series(1.0, index=train_df.index)
    weight.loc[train_df["label_top50"].fillna(0).astype(int) == 1] = 1.5
    weight.loc[train_df["label_top30"].fillna(0).astype(int) == 1] = 3.0
    weight.loc[train_df["label_top10"].fillna(0).astype(int) == 1] = 5.0
    return weight


def predict_scores(experiment: str, train_df: pd.DataFrame, predict_df: pd.DataFrame, feature_cols: list[str]) -> pd.Series:
    if experiment == "raw_rank_pct_regression":
        model = make_regressor()
        model.fit(train_df[feature_cols], train_df["future_5_return_rank_pct"])
        return pd.Series(model.predict(predict_df[feature_cols]), index=predict_df.index)
    if experiment == "weighted_rank_pct_regression":
        model = make_regressor()
        model.fit(
            train_df[feature_cols],
            train_df["future_5_return_rank_pct"],
            sample_weight=weighted_rank_sample_weight(train_df),
        )
        return pd.Series(model.predict(predict_df[feature_cols]), index=predict_df.index)
    if experiment == "top30_classifier":
        model = make_classifier()
        model.fit(train_df[feature_cols], train_df["label_top30"].astype(int))
        return pd.Series(model.predict_proba(predict_df[feature_cols])[:, 1], index=predict_df.index)
    if experiment == "top50_classifier":
        model = make_classifier()
        model.fit(train_df[feature_cols], train_df["label_top50"].astype(int))
        return pd.Series(model.predict_proba(predict_df[feature_cols])[:, 1], index=predict_df.index)
    raise ValueError(f"Unknown experiment: {experiment}")


def month_ranges(start: str, end: str) -> list[tuple[str, str, str]]:
    periods = pd.period_range(start=start, end=end, freq="M")
    return [
        (
            str(period),
            period.start_time.strftime("%Y-%m-%d"),
            period.end_time.strftime("%Y-%m-%d"),
        )
        for period in periods
    ]


def run_experiments(
    df: pd.DataFrame,
    start_month: str,
    end_month: str,
    top_n: int,
    train_window_days: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = df.sort_values(["trade_date", "symbol"]).copy()
    feature_cols = select_feature_columns(df)
    trade_dates = set(df["trade_date"].dropna())
    prediction_frames: list[pd.DataFrame] = []
    diagnostics: list[dict[str, object]] = []

    for period, start_date, end_date in month_ranges(start_month, end_month):
        anchors = pd.date_range(start=start_date, end=end_date, freq="D")
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
            predict_mask = df["trade_date"] == anchor
            train_df = df[train_mask].dropna(subset=feature_cols + ["future_5_return_rank_pct"])
            predict_df = df[predict_mask].copy()
            predict_df = predict_df[eligible_rows(predict_df)].dropna(subset=feature_cols)
            if len(train_df) < 200 or predict_df.empty:
                continue

            diagnostics.append(
                {
                    "period": period,
                    "trade_date": anchor.strftime("%Y-%m-%d"),
                    "train_rows": len(train_df),
                    "predict_rows": len(predict_df),
                    "feature_count": len(feature_cols),
                    "train_start": train_df["trade_date"].min().strftime("%Y-%m-%d"),
                    "train_end": train_df["trade_date"].max().strftime("%Y-%m-%d"),
                    "max_train_exit_trade_date": train_df["exit_trade_date"].max().strftime("%Y-%m-%d"),
                }
            )

            for experiment in EXPERIMENTS:
                scored = predict_df.copy()
                scored["experiment"] = experiment
                scored["period"] = period
                scored["recall_score"] = predict_scores(experiment, train_df, predict_df, feature_cols)
                top = (
                    scored.sort_values(["recall_score", "symbol"], ascending=[False, True])
                    .head(top_n)
                    .copy()
                )
                top["candidate_rank"] = range(1, len(top) + 1)
                prediction_frames.append(
                    top[
                        [
                            "experiment",
                            "period",
                            "trade_date",
                            "symbol",
                            "name",
                            "industry",
                            "recall_score",
                            "candidate_rank",
                            "future_5_return",
                            "future_5_return_rank",
                            "future_5_return_rank_pct",
                            "label_top10",
                            "label_top30",
                            "label_top50",
                            "daily_stock_count",
                            "near_limit_up",
                            "overheat_flag",
                            "low_liquidity_flag",
                        ]
                    ]
                )

    if not prediction_frames:
        raise ValueError("No experiment predictions generated. Check date range and data availability.")
    return pd.concat(prediction_frames, ignore_index=True), pd.DataFrame(diagnostics)


def summarize_daily(predictions: pd.DataFrame, top_n: int) -> pd.DataFrame:
    daily = (
        predictions.groupby(["experiment", "period", "trade_date"])
        .agg(
            candidate_size=("symbol", "count"),
            daily_stock_count=("daily_stock_count", "max"),
            top50_hit_top10=("label_top10", "sum"),
            top50_hit_top30=("label_top30", "sum"),
            top50_hit_top50=("label_top50", "sum"),
            top50_avg_return=("future_5_return", "mean"),
            top50_best_true_rank=("future_5_return_rank", "min"),
            near_limit_up_ratio=("near_limit_up", "mean"),
            overheat_ratio=("overheat_flag", "mean"),
            low_liquidity_ratio=("low_liquidity_flag", "mean"),
        )
        .reset_index()
    )
    daily["random_expected_top30"] = daily["candidate_size"] * 30 / daily["daily_stock_count"]
    daily["top30_recall_ratio"] = daily["top50_hit_top30"] / 30
    daily["recall_lift_vs_random"] = daily["top50_hit_top30"] / daily["random_expected_top30"]
    daily["candidate_size_target"] = top_n
    return daily


def summarize_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    return (
        daily.groupby(["experiment", "period"])
        .agg(
            trade_days=("trade_date", "count"),
            avg_top50_hit_top10=("top50_hit_top10", "mean"),
            avg_top50_hit_top30=("top50_hit_top30", "mean"),
            avg_top50_hit_top50=("top50_hit_top50", "mean"),
            avg_random_expected_top30=("random_expected_top30", "mean"),
            avg_top30_recall_ratio=("top30_recall_ratio", "mean"),
            avg_recall_lift_vs_random=("recall_lift_vs_random", "mean"),
            avg_top50_return=("top50_avg_return", "mean"),
            avg_best_true_rank=("top50_best_true_rank", "mean"),
            avg_near_limit_up_ratio=("near_limit_up_ratio", "mean"),
            avg_overheat_ratio=("overheat_ratio", "mean"),
            avg_low_liquidity_ratio=("low_liquidity_ratio", "mean"),
        )
        .reset_index()
    )


def summarize_overall(monthly: pd.DataFrame) -> pd.DataFrame:
    baseline = monthly[monthly["experiment"] == "raw_rank_pct_regression"][
        ["period", "avg_top50_hit_top30", "avg_near_limit_up_ratio", "avg_overheat_ratio"]
    ].rename(
        columns={
            "avg_top50_hit_top30": "baseline_hit_top30",
            "avg_near_limit_up_ratio": "baseline_near_limit_up_ratio",
            "avg_overheat_ratio": "baseline_overheat_ratio",
        }
    )
    joined = monthly.merge(baseline, on="period", how="left")
    joined["hit30_delta_vs_baseline"] = joined["avg_top50_hit_top30"] - joined["baseline_hit_top30"]
    joined["near_limit_delta_vs_baseline"] = (
        joined["avg_near_limit_up_ratio"] - joined["baseline_near_limit_up_ratio"]
    )
    joined["overheat_delta_vs_baseline"] = joined["avg_overheat_ratio"] - joined["baseline_overheat_ratio"]
    overall = (
        joined.groupby("experiment")
        .agg(
            months=("period", "count"),
            avg_top50_hit_top30=("avg_top50_hit_top30", "mean"),
            avg_random_expected_top30=("avg_random_expected_top30", "mean"),
            avg_top30_recall_ratio=("avg_top30_recall_ratio", "mean"),
            avg_recall_lift_vs_random=("avg_recall_lift_vs_random", "mean"),
            avg_top50_hit_top10=("avg_top50_hit_top10", "mean"),
            avg_top50_return=("avg_top50_return", "mean"),
            avg_near_limit_up_ratio=("avg_near_limit_up_ratio", "mean"),
            avg_overheat_ratio=("avg_overheat_ratio", "mean"),
            avg_hit30_delta_vs_baseline=("hit30_delta_vs_baseline", "mean"),
            months_hit30_gt_baseline=("hit30_delta_vs_baseline", lambda s: int((s > 0).sum())),
            max_single_month_hit30_delta=("hit30_delta_vs_baseline", "max"),
            min_single_month_hit30_delta=("hit30_delta_vs_baseline", "min"),
            avg_near_limit_delta_vs_baseline=("near_limit_delta_vs_baseline", "mean"),
            avg_overheat_delta_vs_baseline=("overheat_delta_vs_baseline", "mean"),
        )
        .reset_index()
        .sort_values(["avg_top50_hit_top30", "months_hit30_gt_baseline"], ascending=False)
    )
    return overall, joined


def write_report(path: Path, overall: pd.DataFrame, monthly_compare: pd.DataFrame, diagnostics: pd.DataFrame) -> None:
    approved_note = (
        "Scope: CR-20260529-002 approved M3-A recall-oriented comparison only. "
        "The raw rank_pct regression main model is not replaced."
    )
    lines = ["# M3-A Recall Model Comparison", "", approved_note, ""]
    lines.append("## Overall")
    lines.append("")
    lines.append(overall.to_markdown(index=False, floatfmt=".4f"))
    lines.append("")
    lines.append("## Monthly")
    lines.append("")
    month_cols = [
        "experiment",
        "period",
        "avg_top50_hit_top30",
        "baseline_hit_top30",
        "hit30_delta_vs_baseline",
        "avg_recall_lift_vs_random",
        "avg_near_limit_up_ratio",
        "near_limit_delta_vs_baseline",
        "avg_overheat_ratio",
        "overheat_delta_vs_baseline",
    ]
    lines.append(monthly_compare[month_cols].to_markdown(index=False, floatfmt=".4f"))
    lines.append("")
    lines.append("## Diagnostics")
    lines.append("")
    if diagnostics.empty:
        lines.append("No diagnostics generated.")
    else:
        diag_summary = {
            "prediction_days": int(diagnostics["trade_date"].nunique()),
            "avg_train_rows": float(diagnostics["train_rows"].mean()),
            "avg_predict_rows": float(diagnostics["predict_rows"].mean()),
            "feature_count": int(diagnostics["feature_count"].max()),
            "max_train_exit_trade_date_rule": "exit_trade_date < anchor_date",
        }
        lines.append("```json")
        lines.append(json.dumps(diag_summary, ensure_ascii=False, indent=2))
        lines.append("```")
    lines.append("")
    lines.append("## Review Notes")
    lines.append("")
    lines.append("- This report evaluates Top50 recall of real Top30 only.")
    lines.append("- It must not be used to select a model by final Top3 return.")
    lines.append("- Formal replacement of the M3-A main model requires a separate change request.")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--start-month", default="2025-05")
    parser.add_argument("--end-month", default="2026-04")
    parser.add_argument("--top-n", type=int, default=50)
    parser.add_argument("--train-window-days", type=int, default=365)
    args = parser.parse_args()

    df = load_features(args.features)
    predictions, diagnostics = run_experiments(
        df,
        start_month=args.start_month,
        end_month=args.end_month,
        top_n=args.top_n,
        train_window_days=args.train_window_days,
    )
    daily = summarize_daily(predictions, args.top_n)
    monthly = summarize_monthly(daily)
    overall, monthly_compare = summarize_overall(monthly)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(args.output_dir / "m3_recall_model_predictions.csv", index=False, encoding="utf-8-sig")
    daily.to_csv(args.output_dir / "m3_recall_model_daily.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(args.output_dir / "m3_recall_model_monthly.csv", index=False, encoding="utf-8-sig")
    monthly_compare.to_csv(args.output_dir / "m3_recall_model_monthly_compare.csv", index=False, encoding="utf-8-sig")
    overall.to_csv(args.output_dir / "m3_recall_model_compare.csv", index=False, encoding="utf-8-sig")
    diagnostics.to_csv(args.output_dir / "m3_recall_model_diagnostics.csv", index=False, encoding="utf-8-sig")
    write_report(args.output_dir / "m3_recall_model_compare.md", overall, monthly_compare, diagnostics)
    print(overall.to_string(index=False))
    print(f"wrote {args.output_dir / 'm3_recall_model_compare.md'}")


if __name__ == "__main__":
    main()
