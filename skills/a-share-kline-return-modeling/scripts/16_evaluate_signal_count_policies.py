#!/usr/bin/env python3
"""Evaluate Top1/Top2/Top3 signal-count policies for M5."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_PRED_ROOT = Path("skills/a-share-kline-return-modeling/outputs/stock_rank_predictions")
DEFAULT_MARKET = Path("skills/a-share-kline-return-modeling/data/market_signal_features.csv")
DEFAULT_OUTPUT_DIR = Path("skills/a-share-kline-return-modeling/outputs/evaluation/m5_signal_count")


MARKET_COLS = [
    "trade_date",
    "market_up_ratio",
    "market_avg_pct_chg",
    "market_strong_5pct_ratio",
    "market_amount_ratio_5",
    "market_volatility_5",
    "market_10pct_density_ma5_lag1",
    "market_10pct_density_ma10_lag1",
]


def load_candidates(pred_root: Path, start_period: str, end_period: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(pred_root.glob("20??-??/predictions_with_truth.csv")):
        period = path.parent.name
        if period < start_period or period > end_period:
            continue
        df = pd.read_csv(path, encoding="utf-8-sig", parse_dates=["trade_date"])
        df["period"] = period
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No monthly predictions found under {pred_root}")
    out = pd.concat(frames, ignore_index=True)
    out["symbol"] = out["symbol"].astype(str).str.zfill(6)
    out = out.sort_values(["trade_date", "rank_strength_score", "symbol"], ascending=[True, False, True]).copy()
    out["pick_rank"] = out.groupby("trade_date").cumcount() + 1
    return out


def load_market(path: Path) -> pd.DataFrame:
    available = pd.read_csv(path, encoding="utf-8-sig", nrows=0).columns
    usecols = [col for col in MARKET_COLS if col in available]
    return pd.read_csv(path, encoding="utf-8-sig", usecols=usecols, parse_dates=["trade_date"])


def add_policy_counts(daily: pd.DataFrame) -> pd.DataFrame:
    out = daily.copy()
    out["fixed_top1"] = 1
    out["fixed_top2"] = 2
    out["fixed_top3"] = 3
    out["contra_breadth_tier"] = 1
    out.loc[out["market_up_ratio"] <= 0.60, "contra_breadth_tier"] = 2
    out.loc[out["market_up_ratio"] <= 0.40, "contra_breadth_tier"] = 3
    out["volatility_tier"] = 1
    out.loc[out["market_volatility_5"] >= 0.024, "volatility_tier"] = 2
    out.loc[out["market_volatility_5"] >= 0.027, "volatility_tier"] = 3
    out["lag_density_tier"] = 1
    out.loc[out["market_10pct_density_ma5_lag1"] >= 0.042, "lag_density_tier"] = 2
    out.loc[out["market_10pct_density_ma5_lag1"] >= 0.064, "lag_density_tier"] = 3
    out["combined_opportunity_tier"] = 1
    top3_mask = (
        (out["market_up_ratio"] <= 0.40)
        | (out["market_volatility_5"] >= 0.027)
        | (out["market_10pct_density_ma5_lag1"] >= 0.064)
    )
    top2_mask = (
        (out["market_up_ratio"] <= 0.60)
        | (out["market_volatility_5"] >= 0.024)
        | (out["market_10pct_density_ma5_lag1"] >= 0.042)
    )
    out.loc[top2_mask, "combined_opportunity_tier"] = 2
    out.loc[top3_mask, "combined_opportunity_tier"] = 3
    return out


def build_policy_picks(candidates: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    daily = candidates.groupby("trade_date").head(1)[["trade_date"]].merge(market, on="trade_date", how="left")
    daily = add_policy_counts(daily)
    policies = [
        "fixed_top1",
        "fixed_top2",
        "fixed_top3",
        "contra_breadth_tier",
        "volatility_tier",
        "lag_density_tier",
        "combined_opportunity_tier",
    ]
    picks: list[pd.DataFrame] = []
    for policy in policies:
        count_map = daily.set_index("trade_date")[policy]
        work = candidates.copy()
        work["policy"] = policy
        work["policy_pick_count"] = work["trade_date"].map(count_map).fillna(1).astype(int)
        picked = work[work["pick_rank"] <= work["policy_pick_count"]].copy()
        picks.append(picked)
    return pd.concat(picks, ignore_index=True)


def summarize_daily(picks: pd.DataFrame) -> pd.DataFrame:
    daily = (
        picks.groupby(["policy", "trade_date"])
        .agg(
            pick_count=("symbol", "count"),
            avg_return=("future_5_return", "mean"),
            hit_top10=("label_top10", "sum"),
            hit_top30=("label_top30", "sum"),
            strong_10pct=("future_5_return", lambda s: (s >= 0.10).mean()),
            loss_5pct=("future_5_return", lambda s: (s <= -0.05).mean()),
            best_true_rank=("future_5_return_rank", "min"),
        )
        .reset_index()
    )
    daily["month"] = daily["trade_date"].dt.to_period("M").astype(str)
    daily["hit_at_least_one"] = daily["hit_top30"] > 0
    return daily


def summarize_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    return (
        daily.groupby(["policy", "month"])
        .agg(
            trade_days=("trade_date", "count"),
            avg_pick_count=("pick_count", "mean"),
            avg_return=("avg_return", "mean"),
            avg_hit_top10=("hit_top10", "mean"),
            avg_hit_top30=("hit_top30", "mean"),
            hit_at_least_one=("hit_at_least_one", "mean"),
            avg_strong_10pct=("strong_10pct", "mean"),
            avg_loss_5pct=("loss_5pct", "mean"),
            avg_best_true_rank=("best_true_rank", "mean"),
        )
        .reset_index()
    )


def summarize_overall(monthly: pd.DataFrame) -> pd.DataFrame:
    return (
        monthly.groupby("policy")
        .agg(
            months=("month", "count"),
            avg_pick_count=("avg_pick_count", "mean"),
            avg_monthly_return=("avg_return", "mean"),
            avg_hit_top10=("avg_hit_top10", "mean"),
            avg_hit_top30=("avg_hit_top30", "mean"),
            avg_hit_at_least_one=("hit_at_least_one", "mean"),
            positive_month_ratio=("avg_return", lambda s: (s > 0).mean()),
            min_monthly_return=("avg_return", "min"),
            avg_loss_5pct=("avg_loss_5pct", "mean"),
        )
        .reset_index()
        .sort_values(["avg_monthly_return", "positive_month_ratio"], ascending=False)
    )


def write_report(path: Path, overall: pd.DataFrame, monthly: pd.DataFrame) -> None:
    lines = [
        "# M5 Signal Count Policy Experiment",
        "",
        "Scope: diagnostic only. Policies choose Top1/Top2/Top3 using same M3 ranking output.",
        "",
        "## Overall",
        "",
        overall.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Monthly",
        "",
        monthly.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Policy Definitions",
        "",
        "- `fixed_top1/2/3`: always pick the first N names.",
        "- `contra_breadth_tier`: market_up_ratio <= 0.40 uses Top3, <= 0.60 uses Top2, otherwise Top1.",
        "- `volatility_tier`: market_volatility_5 >= 0.027 uses Top3, >= 0.024 uses Top2, otherwise Top1.",
        "- `lag_density_tier`: lagged 10% density ma5 >= 0.064 uses Top3, >= 0.042 uses Top2, otherwise Top1.",
        "- `combined_opportunity_tier`: Top3 if any high-opportunity condition is met, Top2 if any mid condition is met, otherwise Top1.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred-root", type=Path, default=DEFAULT_PRED_ROOT)
    parser.add_argument("--market", type=Path, default=DEFAULT_MARKET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--start-period", default="2025-05")
    parser.add_argument("--end-period", default="2026-04")
    args = parser.parse_args()

    candidates = load_candidates(args.pred_root, args.start_period, args.end_period)
    market = load_market(args.market)
    picks = build_policy_picks(candidates, market)
    daily = summarize_daily(picks)
    monthly = summarize_monthly(daily)
    overall = summarize_overall(monthly)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    picks.to_csv(args.output_dir / "m5_signal_count_picks.csv", index=False, encoding="utf-8-sig")
    daily.to_csv(args.output_dir / "m5_signal_count_daily.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(args.output_dir / "m5_signal_count_monthly.csv", index=False, encoding="utf-8-sig")
    overall.to_csv(args.output_dir / "m5_signal_count_overall.csv", index=False, encoding="utf-8-sig")
    write_report(args.output_dir / "m5_signal_count_report.md", overall, monthly)
    print(overall.to_string(index=False))
    print(f"wrote {args.output_dir / 'm5_signal_count_report.md'}")


if __name__ == "__main__":
    main()
