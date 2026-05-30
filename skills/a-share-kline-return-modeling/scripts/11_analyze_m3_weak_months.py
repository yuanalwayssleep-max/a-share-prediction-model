#!/usr/bin/env python3
"""Analyze weak months after M3 main model walk-forward.

Offline diagnostic only. It explains whether weak periods come from market
opportunity, Top50 recall, Top3 sorting, or risk exposure.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


EVAL_DIR = Path("skills/a-share-kline-return-modeling/outputs/evaluation")
MARKET_FEATURES = Path("skills/a-share-kline-return-modeling/data/clean_market_features.csv")


def load_daily_details() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted((EVAL_DIR / "walk_forward").glob("20??-??/daily_detail.csv")):
        df = pd.read_csv(path, encoding="utf-8-sig", parse_dates=["trade_date"])
        df["period"] = path.parent.name
        frames.append(df)
    if not frames:
        raise FileNotFoundError("No walk_forward/*/daily_detail.csv files found.")
    return pd.concat(frames, ignore_index=True)


def load_recall_monthly() -> pd.DataFrame:
    path = EVAL_DIR / "m3_recall_model_monthly_compare.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    return df[df["experiment"] == "top50_classifier"].copy()


def load_market() -> pd.DataFrame:
    df = pd.read_csv(MARKET_FEATURES, encoding="utf-8-sig", parse_dates=["trade_date"])
    df["period"] = df["trade_date"].dt.to_period("M").astype(str)
    return df


def summarize_market(market: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "future_market_10pct_density",
        "market_top5pct_avg_return",
        "market_top30_avg_return",
        "market_positive_ratio",
        "market_extreme_return_density_5pct",
        "market_extreme_return_density_10pct",
        "market_10pct_density_ma5_lag1",
        "market_10pct_density_ma10_lag1",
    ]
    keep = [c for c in cols if c in market.columns]
    return market.groupby("period")[keep].mean().reset_index()


def summarize_strategy_months(daily: pd.DataFrame) -> pd.DataFrame:
    monthly = (
        daily.groupby(["strategy", "period"])
        .agg(
            trade_days=("trade_date", "count"),
            avg_return=("avg_future_5_return", "mean"),
            avg_hit_top10=("hit_top10_count", "mean"),
            avg_hit_top30=("hit_top30_count", "mean"),
            hit_at_least_one=("hit_top30_at_least_one", "mean"),
            strong_10pct_ratio=("strong_10pct_ratio", "mean"),
            avg_best_true_rank=("best_true_rank", "mean"),
        )
        .reset_index()
    )
    return monthly


def summarize_bad_days(daily: pd.DataFrame) -> pd.DataFrame:
    model = daily[daily["strategy"] == "model_rank"].copy()
    weak = model[(model["avg_future_5_return"] < 0) | (model["hit_top30_count"] == 0)].copy()
    return weak.sort_values(["period", "avg_future_5_return", "hit_top30_count"])[
        [
            "period",
            "trade_date",
            "avg_future_5_return",
            "hit_top10_count",
            "hit_top30_count",
            "best_true_rank",
            "industries",
        ]
    ]


def classify_months(joined: pd.DataFrame) -> pd.DataFrame:
    out = joined.copy()
    labels: list[str] = []
    for _, row in out.iterrows():
        reasons = []
        if row.get("model_avg_return", 0) < 0:
            reasons.append("Top3收益为负")
        if row.get("model_hit_top30", 0) < 0.6:
            reasons.append("Top3命中偏低")
        if row.get("avg_top50_hit_top30", 999) < 7:
            reasons.append("Top50召回偏弱")
        if row.get("market_top30_avg_return", 0) < 0:
            reasons.append("市场真实Top30平均收益弱")
        if row.get("future_market_10pct_density", 0) < 0.02:
            reasons.append("10%机会密度低")
        if row.get("model_avg_return", 0) < row.get("random_avg_return", 0):
            reasons.append("弱于随机")
        labels.append("；".join(reasons) if reasons else "正常")
    out["diagnosis"] = labels
    return out


def write_report(path: Path, joined: pd.DataFrame, strategy_monthly: pd.DataFrame, bad_days: pd.DataFrame) -> None:
    weak = joined[joined["diagnosis"] != "正常"].copy()
    lines = ["# M3 Weak Month Analysis", ""]
    lines.append("## Weak Month Diagnosis")
    lines.append("")
    cols = [
        "period",
        "model_avg_return",
        "model_hit_top30",
        "random_avg_return",
        "random_hit_top30",
        "avg_top50_hit_top30",
        "market_top30_avg_return",
        "future_market_10pct_density",
        "market_positive_ratio",
        "diagnosis",
    ]
    lines.append(weak[[c for c in cols if c in weak.columns]].to_markdown(index=False, floatfmt=".4f"))
    lines.append("")
    lines.append("## All Months")
    lines.append("")
    lines.append(joined[[c for c in cols if c in joined.columns]].to_markdown(index=False, floatfmt=".4f"))
    lines.append("")
    lines.append("## Strategy Monthly Comparison")
    lines.append("")
    strategy_cols = ["strategy", "period", "avg_return", "avg_hit_top30", "hit_at_least_one", "avg_best_true_rank"]
    lines.append(strategy_monthly[strategy_cols].to_markdown(index=False, floatfmt=".4f"))
    lines.append("")
    lines.append("## Bad Model Days")
    lines.append("")
    lines.append(bad_days.head(60).to_markdown(index=False, floatfmt=".4f"))
    lines.append("")
    lines.append("## Initial Takeaways")
    lines.append("")
    lines.append("- 2025-06 is not a pure market-opportunity problem: random performed very well, while model Top3 under-selected the available winners.")
    lines.append("- 2025-09 is primarily a Top3 sorting problem: Top50 recall was strong, but candidate_score ranked poor names at the very top.")
    lines.append("- 2025-11 is mixed: market return was weak, but ret_20 rerank improved hit count, suggesting the main score was too defensive or misordered.")
    lines.append("- 2025-07 is a recall and sorting weak month; it remains the hardest M3 month.")
    lines.append("- M5 market opportunity can reduce bad exposure, but it will not fix months where opportunity exists and model sorting misses it.")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    wf = pd.read_csv(EVAL_DIR / "walk_forward_summary.csv")
    daily = load_daily_details()
    strategy_monthly = summarize_strategy_months(daily)
    recall = load_recall_monthly()
    market = summarize_market(load_market())
    joined = wf.merge(
        recall[["period", "avg_top50_hit_top30", "avg_recall_lift_vs_random", "avg_top50_return"]],
        on="period",
        how="left",
    ).merge(market, on="period", how="left")
    joined = classify_months(joined)
    bad_days = summarize_bad_days(daily)

    joined.to_csv(EVAL_DIR / "m3_weak_month_analysis.csv", index=False, encoding="utf-8-sig")
    strategy_monthly.to_csv(EVAL_DIR / "m3_strategy_monthly_analysis.csv", index=False, encoding="utf-8-sig")
    bad_days.to_csv(EVAL_DIR / "m3_bad_model_days.csv", index=False, encoding="utf-8-sig")
    write_report(EVAL_DIR / "m3_weak_month_analysis.md", joined, strategy_monthly, bad_days)
    print(joined[["period", "model_avg_return", "model_hit_top30", "avg_top50_hit_top30", "diagnosis"]].to_string(index=False))
    print(f"wrote {EVAL_DIR / 'm3_weak_month_analysis.md'}")


if __name__ == "__main__":
    main()
