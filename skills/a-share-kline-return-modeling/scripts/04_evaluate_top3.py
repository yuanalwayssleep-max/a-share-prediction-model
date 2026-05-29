#!/usr/bin/env python3
"""Evaluate TopK signals and simple baselines for the V1 pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import pandas as pd


DEFAULT_FEATURES = Path("skills/a-share-kline-return-modeling/data/clean_stock_features.csv")
DEFAULT_OUTPUT_DIR = Path("skills/a-share-kline-return-modeling/outputs/evaluation")


BASELINES = {
    "random": None,
    "ret_5": "ret_5",
    "ret_20": "ret_20",
    "amount_ratio_5": "amount_ratio_5",
    "turnover_pct": "turnover_pct",
    "industry_strength": "industry_strength_score",
}


def load_features(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig", parse_dates=["trade_date"])
    required = {
        "trade_date",
        "symbol",
        "name",
        "industry",
        "future_5_return",
        "future_5_return_rank",
        "label_top10",
        "label_top30",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    return df


def candidate_pool(df: pd.DataFrame) -> pd.DataFrame:
    pool = df[df["future_5_return"].notna()].copy()
    if "is_st" in pool.columns:
        pool = pool[pool["is_st"].fillna(0).astype(int) == 0]
    if "listing_days" in pool.columns:
        pool = pool[pool["listing_days"].fillna(0) >= 60]
    if "low_liquidity_flag" in pool.columns:
        pool = pool[pool["low_liquidity_flag"].fillna(1).astype(int) == 0]
    return pool


def make_baseline_predictions(df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for strategy, score_col in BASELINES.items():
        work = df.copy()
        if strategy == "random":
            work["strategy_score"] = (
                pd.util.hash_pandas_object(work[["trade_date", "symbol"]].astype(str), index=False).astype("uint64")
                % 1_000_000
            )
        else:
            if score_col not in work.columns:
                continue
            work["strategy_score"] = pd.to_numeric(work[score_col], errors="coerce")
        work = work.dropna(subset=["strategy_score"])
        picked = (
            work.sort_values(["trade_date", "strategy_score", "symbol"], ascending=[True, False, True])
            .groupby("trade_date", group_keys=False)
            .head(top_n)
            .copy()
        )
        picked["strategy"] = strategy
        picked["pick_rank"] = picked.groupby("trade_date").cumcount() + 1
        frames.append(picked)
    if not frames:
        raise ValueError("No baseline predictions could be generated.")
    return pd.concat(frames, ignore_index=True)


def load_model_predictions(path: Path, top_n: int) -> pd.DataFrame:
    preds = pd.read_csv(path, encoding="utf-8-sig", parse_dates=["trade_date"])
    required = {
        "trade_date",
        "symbol",
        "name",
        "industry",
        "rank_strength_score",
        "future_5_return",
        "future_5_return_rank",
        "label_top10",
        "label_top30",
    }
    missing = sorted(required - set(preds.columns))
    if missing:
        raise ValueError(f"Model prediction file missing columns: {missing}")
    preds = (
        preds.sort_values(["trade_date", "rank_strength_score", "symbol"], ascending=[True, False, True])
        .groupby("trade_date", group_keys=False)
        .head(top_n)
        .copy()
    )
    preds["strategy"] = "model_rank"
    preds["strategy_score"] = preds["rank_strength_score"]
    preds["pick_rank"] = preds.groupby("trade_date").cumcount() + 1
    return preds


def summarize_daily(predictions: pd.DataFrame) -> pd.DataFrame:
    daily = (
        predictions.groupby(["strategy", "trade_date"])
        .agg(
            pick_count=("symbol", "count"),
            avg_future_5_return=("future_5_return", "mean"),
            median_future_5_return=("future_5_return", "median"),
            hit_top10_count=("label_top10", "sum"),
            hit_top30_count=("label_top30", "sum"),
            strong_10pct_count=("future_5_return", lambda s: (s >= 0.10).sum()),
            best_true_rank=("future_5_return_rank", "min"),
            industries=("industry", lambda s: ",".join(sorted(set(map(str, s))))),
        )
        .reset_index()
    )
    daily["hit_top30_at_least_one"] = daily["hit_top30_count"] > 0
    daily["strong_10pct_ratio"] = daily["strong_10pct_count"] / daily["pick_count"]
    daily["month"] = daily["trade_date"].dt.to_period("M").astype(str)
    return daily


def summarize_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    return (
        daily.groupby(["strategy", "month"])
        .agg(
            trade_days=("trade_date", "count"),
            avg_pick_count=("pick_count", "mean"),
            avg_future_5_return=("avg_future_5_return", "mean"),
            median_daily_return=("avg_future_5_return", "median"),
            avg_hit_top10_count=("hit_top10_count", "mean"),
            avg_hit_top30_count=("hit_top30_count", "mean"),
            hit_at_least_one_ratio=("hit_top30_at_least_one", "mean"),
            avg_strong_10pct_ratio=("strong_10pct_ratio", "mean"),
            avg_best_true_rank=("best_true_rank", "mean"),
        )
        .reset_index()
    )


def summarize_overall(daily: pd.DataFrame) -> pd.DataFrame:
    return (
        daily.groupby("strategy")
        .agg(
            trade_days=("trade_date", "count"),
            avg_future_5_return=("avg_future_5_return", "mean"),
            median_daily_return=("avg_future_5_return", "median"),
            avg_hit_top10_count=("hit_top10_count", "mean"),
            avg_hit_top30_count=("hit_top30_count", "mean"),
            hit_at_least_one_ratio=("hit_top30_at_least_one", "mean"),
            avg_strong_10pct_ratio=("strong_10pct_ratio", "mean"),
            avg_best_true_rank=("best_true_rank", "mean"),
        )
        .reset_index()
        .sort_values("avg_future_5_return", ascending=False)
    )


def bootstrap_ci(daily: pd.DataFrame, iterations: int = 500) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for strategy, group in daily.groupby("strategy"):
        returns = group["avg_future_5_return"].dropna().reset_index(drop=True)
        if returns.empty:
            continue
        samples = []
        for i in range(iterations):
            sample = returns.sample(n=len(returns), replace=True, random_state=20260529 + i)
            samples.append(sample.mean())
        series = pd.Series(samples)
        rows.append(
            {
                "strategy": strategy,
                "mean": returns.mean(),
                "ci_low": series.quantile(0.025),
                "ci_high": series.quantile(0.975),
                "iterations": iterations,
            }
        )
    return pd.DataFrame(rows)


def portfolio_curve(daily: pd.DataFrame) -> pd.DataFrame:
    curves: list[pd.DataFrame] = []
    for strategy, group in daily.sort_values("trade_date").groupby("strategy"):
        curve = group[["trade_date", "avg_future_5_return"]].copy()
        curve["strategy"] = strategy
        # Signal-level proxy: one fifth of capital is exposed to each daily basket.
        curve["daily_portfolio_return_proxy"] = curve["avg_future_5_return"].fillna(0) * 0.2
        curve["equity_curve_proxy"] = (1 + curve["daily_portfolio_return_proxy"]).cumprod()
        curve["running_max"] = curve["equity_curve_proxy"].cummax()
        curve["drawdown_proxy"] = curve["equity_curve_proxy"] / curve["running_max"] - 1
        curves.append(curve)
    return pd.concat(curves, ignore_index=True)


def write_markdown_summary(overall: pd.DataFrame, output_path: Path) -> None:
    lines = ["# Baseline Evaluation Summary", ""]
    lines.append(overall.to_markdown(index=False))
    lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--model-predictions-with-truth", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-n", type=int, default=3)
    args = parser.parse_args()

    features = load_features(args.features)
    pool = candidate_pool(features)
    if args.model_predictions_with_truth:
        model_predictions = load_model_predictions(args.model_predictions_with_truth, args.top_n)
        pool = pool[pool["trade_date"].isin(set(model_predictions["trade_date"]))]
        predictions = pd.concat(
            [make_baseline_predictions(pool, args.top_n), model_predictions],
            ignore_index=True,
        )
    else:
        predictions = make_baseline_predictions(pool, args.top_n)
    daily = summarize_daily(predictions)
    monthly = summarize_monthly(daily)
    overall = summarize_overall(daily)
    ci = bootstrap_ci(daily)
    curve = portfolio_curve(daily)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(args.output_dir / "baseline_predictions.csv", index=False, encoding="utf-8-sig")
    daily.to_csv(args.output_dir / "daily_detail.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(args.output_dir / "monthly_summary.csv", index=False, encoding="utf-8-sig")
    overall.to_csv(args.output_dir / "baseline_compare.csv", index=False, encoding="utf-8-sig")
    ci.to_csv(args.output_dir / "bootstrap_confidence_interval.csv", index=False, encoding="utf-8-sig")
    curve.to_csv(args.output_dir / "portfolio_curve.csv", index=False, encoding="utf-8-sig")
    write_markdown_summary(overall, args.output_dir / "baseline_summary.md")

    print(overall.to_string(index=False))


if __name__ == "__main__":
    main()
