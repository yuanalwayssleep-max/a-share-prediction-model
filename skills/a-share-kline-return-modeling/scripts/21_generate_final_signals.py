#!/usr/bin/env python3
"""Generate final executable Top3 signals with optional M5 sizing switch."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_PRED_ROOT = Path("skills/a-share-kline-return-modeling/outputs/stock_rank_predictions")
DEFAULT_MARKET = Path("skills/a-share-kline-return-modeling/data/market_signal_features.csv")
DEFAULT_OUTPUT_DIR = Path("skills/a-share-kline-return-modeling/outputs/final_signals")

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

SAFE_SIGNAL_COLS = [
    "trade_date",
    "symbol",
    "name",
    "industry",
    "pick_rank",
    "rank_strength_score",
    "industry_strength_score",
    "model_mode",
    "model_name",
    "position_policy",
    "opportunity_tier",
    "position_size_multiplier",
    "suggested_new_sleeve_weight",
    "suggested_position_weight",
    "market_up_ratio",
    "market_avg_pct_chg",
    "market_volatility_5",
    "market_10pct_density_ma5_lag1",
    "market_10pct_density_ma10_lag1",
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

FORBIDDEN_OUTPUT_PREFIXES = ("future_", "label_", "actual_")
FORBIDDEN_OUTPUT_COLUMNS = {
    "entry_price",
    "exit_price",
    "gross_future_5_return",
    "future_5_return",
    "future_5_return_rank",
    "future_5_return_rank_pct",
}


def forbidden_truth_columns(columns: list[str]) -> list[str]:
    return [
        col
        for col in columns
        if col in FORBIDDEN_OUTPUT_COLUMNS or col.startswith(FORBIDDEN_OUTPUT_PREFIXES)
    ]


def load_predictions(pred_root: Path, start_period: str, end_period: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    filename = "predictions.csv"
    for path in sorted(pred_root.glob(f"20??-??/{filename}")):
        period = path.parent.name
        if period < start_period or period > end_period:
            continue
        df = pd.read_csv(path, encoding="utf-8-sig", parse_dates=["trade_date"])
        forbidden = forbidden_truth_columns(list(df.columns))
        if forbidden:
            raise ValueError(f"Prediction input contains forbidden truth columns in {path}: {forbidden}")
        df["period"] = period
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No monthly {filename} files found under {pred_root}")
    out = pd.concat(frames, ignore_index=True)
    out["symbol"] = out["symbol"].astype(str).str.zfill(6)
    return out


def load_market(path: Path) -> pd.DataFrame:
    available = pd.read_csv(path, encoding="utf-8-sig", nrows=0).columns
    forbidden = forbidden_truth_columns(list(available))
    if forbidden:
        raise ValueError(f"Market signal input contains forbidden truth columns in {path}: {forbidden}")
    usecols = [col for col in MARKET_COLS if col in available]
    return pd.read_csv(path, encoding="utf-8-sig", usecols=usecols, parse_dates=["trade_date"])


def opportunity_tier(row: pd.Series) -> str:
    high = (
        (row.get("market_up_ratio", 1.0) <= 0.40)
        or (row.get("market_volatility_5", 0.0) >= 0.027)
        or (row.get("market_10pct_density_ma5_lag1", 0.0) >= 0.064)
    )
    if high:
        return "high"
    mid = (
        (row.get("market_up_ratio", 1.0) <= 0.60)
        or (row.get("market_volatility_5", 0.0) >= 0.024)
        or (row.get("market_10pct_density_ma5_lag1", 0.0) >= 0.042)
    )
    if mid:
        return "mid"
    return "low"


def size_multiplier_for_tier(tier: str, policy: str) -> float:
    if policy == "full_size":
        return 1.0
    if policy == "combined_size_v2":
        return {"low": 0.50, "mid": 0.90, "high": 1.00}[tier]
    raise ValueError(f"Unknown position policy: {policy}")


def build_final_signals(
    predictions: pd.DataFrame,
    market: pd.DataFrame,
    top_n: int,
    hold_sleeves: int,
    position_policy: str,
) -> pd.DataFrame:
    top = (
        predictions.sort_values(["trade_date", "rank_strength_score", "symbol"], ascending=[True, False, True])
        .groupby("trade_date", group_keys=False)
        .head(top_n)
        .copy()
    )
    top["pick_rank"] = top.groupby("trade_date").cumcount() + 1
    out = top.merge(market, on="trade_date", how="left")
    daily_tier = (
        out[["trade_date"] + [c for c in MARKET_COLS if c != "trade_date" and c in out.columns]]
        .drop_duplicates("trade_date")
        .copy()
    )
    daily_tier["opportunity_tier"] = daily_tier.apply(opportunity_tier, axis=1)
    daily_tier["position_policy"] = position_policy
    daily_tier["position_size_multiplier"] = daily_tier["opportunity_tier"].map(
        lambda tier: size_multiplier_for_tier(tier, position_policy)
    )
    out = out.merge(
        daily_tier[["trade_date", "opportunity_tier", "position_policy", "position_size_multiplier"]],
        on="trade_date",
        how="left",
    )
    out["suggested_new_sleeve_weight"] = out["position_size_multiplier"] / hold_sleeves
    daily_pick_count = out.groupby("trade_date")["symbol"].transform("count")
    out["suggested_position_weight"] = out["suggested_new_sleeve_weight"] / daily_pick_count
    safe_cols = [col for col in SAFE_SIGNAL_COLS if col in out.columns]
    safe = out[safe_cols].copy()
    forbidden = [
        col
        for col in safe.columns
        if col in FORBIDDEN_OUTPUT_COLUMNS or col.startswith(FORBIDDEN_OUTPUT_PREFIXES)
    ]
    if forbidden:
        raise ValueError(f"Final signal output contains forbidden truth columns: {forbidden}")
    return safe


def summarize(signals: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = (
        signals.groupby(["trade_date", "position_policy", "opportunity_tier", "position_size_multiplier"])
        .agg(
            picks=("symbol", "count"),
            suggested_new_sleeve_weight=("suggested_new_sleeve_weight", "max"),
            suggested_total_position_weight=("suggested_position_weight", "sum"),
            industries=("industry", lambda s: ",".join(sorted(set(map(str, s))))),
        )
        .reset_index()
    )
    daily["month"] = daily["trade_date"].dt.to_period("M").astype(str)
    monthly = (
        daily.groupby(["month", "position_policy"])
        .agg(
            trade_days=("trade_date", "count"),
            avg_size_multiplier=("position_size_multiplier", "mean"),
            low_days=("opportunity_tier", lambda s: int((s == "low").sum())),
            mid_days=("opportunity_tier", lambda s: int((s == "mid").sum())),
            high_days=("opportunity_tier", lambda s: int((s == "high").sum())),
            avg_total_position_weight=("suggested_total_position_weight", "mean"),
        )
        .reset_index()
    )
    return daily, monthly


def write_report(path: Path, signals: pd.DataFrame, daily: pd.DataFrame, monthly: pd.DataFrame) -> None:
    lines = [
        "# Final Signal Generation Report",
        "",
        "Scope: executable signal file only; no truth or future columns are written.",
        "",
        "## Summary",
        "",
        f"- signal rows: {len(signals)}",
        f"- signal days: {signals['trade_date'].nunique()}",
        f"- policy: {signals['position_policy'].iloc[0] if not signals.empty else ''}",
        f"- average size multiplier: {daily['position_size_multiplier'].mean():.4f}",
        "",
        "## Monthly",
        "",
        monthly.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Daily Sample",
        "",
        daily.head(20).to_markdown(index=False, floatfmt=".4f"),
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
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--hold-sleeves", type=int, default=5)
    parser.add_argument("--position-policy", choices=["full_size", "combined_size_v2"], default="full_size")
    args = parser.parse_args()

    predictions = load_predictions(args.pred_root, args.start_period, args.end_period)
    market = load_market(args.market)
    signals = build_final_signals(
        predictions,
        market,
        top_n=args.top_n,
        hold_sleeves=args.hold_sleeves,
        position_policy=args.position_policy,
    )
    daily, monthly = summarize(signals)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"{args.position_policy}_{args.start_period}_{args.end_period}"
    signal_path = args.output_dir / f"final_signals_{suffix}.csv"
    daily_path = args.output_dir / f"final_signals_daily_{suffix}.csv"
    monthly_path = args.output_dir / f"final_signals_monthly_{suffix}.csv"
    report_path = args.output_dir / f"final_signals_report_{suffix}.md"
    signals.to_csv(signal_path, index=False, encoding="utf-8-sig")
    daily.to_csv(daily_path, index=False, encoding="utf-8-sig")
    monthly.to_csv(monthly_path, index=False, encoding="utf-8-sig")
    write_report(report_path, signals, daily, monthly)
    print(report_path.read_text(encoding="utf-8"))
    print(f"wrote {signal_path}")


if __name__ == "__main__":
    main()
