#!/usr/bin/env python3
"""Analyze why the V1 stock rank model misses Top30."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_PRED_ROOT = Path("skills/a-share-kline-return-modeling/outputs/stock_rank_predictions")
DEFAULT_EVAL_DIR = Path("skills/a-share-kline-return-modeling/outputs/evaluation")


def load_month_predictions(pred_root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(pred_root.glob("20??-??/predictions_with_truth.csv")):
        period = path.parent.name
        df = pd.read_csv(path, encoding="utf-8-sig", parse_dates=["trade_date"])
        df["period"] = period
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No monthly predictions found under {pred_root}")
    out = pd.concat(frames, ignore_index=True)
    out["pick_rank"] = out.groupby(["period", "trade_date"])["rank_strength_score"].rank(
        method="first", ascending=False
    )
    out["rank_bucket"] = pd.cut(
        out["pick_rank"],
        bins=[0, 3, 10, 30],
        labels=["top1_3", "top4_10", "top11_30"],
        include_lowest=True,
    )
    return out


def bucket_summary(pred: pd.DataFrame) -> pd.DataFrame:
    return (
        pred.groupby(["period", "rank_bucket"], observed=False)
        .agg(
            picks=("symbol", "count"),
            avg_return=("future_5_return", "mean"),
            median_return=("future_5_return", "median"),
            hit_top10_ratio=("label_top10", "mean"),
            hit_top30_ratio=("label_top30", "mean"),
            avg_true_rank=("future_5_return_rank", "mean"),
            strong_10pct_ratio=("future_5_return", lambda s: (s >= 0.10).mean()),
        )
        .reset_index()
    )


def daily_failure_summary(pred: pd.DataFrame) -> pd.DataFrame:
    daily = (
        pred.groupby(["period", "trade_date"])
        .agg(
            top3_hit_top30=("label_top30", lambda s: s.iloc[:3].sum()),
            top10_hit_top30=("label_top30", lambda s: s.iloc[:10].sum()),
            top30_hit_top30=("label_top30", "sum"),
            top3_avg_return=("future_5_return", lambda s: s.iloc[:3].mean()),
            top30_avg_return=("future_5_return", "mean"),
            top3_best_true_rank=("future_5_return_rank", lambda s: s.iloc[:3].min()),
            top30_best_true_rank=("future_5_return_rank", "min"),
        )
        .reset_index()
    )
    daily["candidate_has_hit_but_top3_missed"] = (daily["top30_hit_top30"] > 0) & (daily["top3_hit_top30"] == 0)
    daily["top3_capture_ratio"] = daily["top3_hit_top30"] / daily["top30_hit_top30"].replace(0, pd.NA)
    return daily


def monthly_failure_summary(daily: pd.DataFrame) -> pd.DataFrame:
    return (
        daily.groupby("period")
        .agg(
            trade_days=("trade_date", "count"),
            avg_top3_hit_top30=("top3_hit_top30", "mean"),
            avg_top10_hit_top30=("top10_hit_top30", "mean"),
            avg_top30_hit_top30=("top30_hit_top30", "mean"),
            candidate_has_hit_but_top3_missed_ratio=("candidate_has_hit_but_top3_missed", "mean"),
            avg_top3_return=("top3_avg_return", "mean"),
            avg_top30_return=("top30_avg_return", "mean"),
            avg_top3_capture_ratio=("top3_capture_ratio", "mean"),
        )
        .reset_index()
    )


def worst_days(daily: pd.DataFrame, limit: int = 30) -> pd.DataFrame:
    return daily.sort_values(["top3_hit_top30", "top3_avg_return", "top30_hit_top30"]).head(limit)


def write_markdown(
    path: Path,
    monthly: pd.DataFrame,
    buckets: pd.DataFrame,
    worst: pd.DataFrame,
) -> None:
    lines = ["# Rank Failure Analysis", ""]
    lines.append("## Monthly Candidate Funnel")
    lines.append("")
    lines.append(monthly.to_markdown(index=False))
    lines.append("")
    lines.append("## Score Bucket Quality")
    lines.append("")
    lines.append(buckets.to_markdown(index=False))
    lines.append("")
    lines.append("## Worst Daily Cases")
    lines.append("")
    lines.append(worst.to_markdown(index=False))
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred-root", type=Path, default=DEFAULT_PRED_ROOT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_EVAL_DIR)
    args = parser.parse_args()

    pred = load_month_predictions(args.pred_root)
    buckets = bucket_summary(pred)
    daily = daily_failure_summary(pred)
    monthly = monthly_failure_summary(daily)
    worst = worst_days(daily)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    pred.to_csv(args.output_dir / "rank_failure_predictions.csv", index=False, encoding="utf-8-sig")
    buckets.to_csv(args.output_dir / "rank_failure_bucket_summary.csv", index=False, encoding="utf-8-sig")
    daily.to_csv(args.output_dir / "rank_failure_daily_summary.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(args.output_dir / "rank_failure_monthly_summary.csv", index=False, encoding="utf-8-sig")
    write_markdown(args.output_dir / "rank_failure_analysis.md", monthly, buckets, worst)
    print(monthly.to_string(index=False))
    print(f"wrote {args.output_dir / 'rank_failure_analysis.md'}")


if __name__ == "__main__":
    main()
