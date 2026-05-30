#!/usr/bin/env python3
"""Small grid search around the M5 combined position-sizing policy."""

from __future__ import annotations

import argparse
import importlib.util
from itertools import product
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
BACKTEST_SCRIPT = ROOT / "skills/a-share-kline-return-modeling/scripts/14_backtest_portfolio_curve.py"
SIZING_SCRIPT = ROOT / "skills/a-share-kline-return-modeling/scripts/18_backtest_position_sizing_policies.py"
DEFAULT_PRED_ROOT = Path("skills/a-share-kline-return-modeling/outputs/stock_rank_predictions")
DEFAULT_FEATURES = Path("skills/a-share-kline-return-modeling/data/clean_stock_features.csv")
DEFAULT_MARKET = Path("skills/a-share-kline-return-modeling/data/market_signal_features.csv")
DEFAULT_OUTPUT_DIR = Path("skills/a-share-kline-return-modeling/outputs/evaluation/m5_position_sizing_grid")


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_policy_predictions(
    predictions: pd.DataFrame,
    market: pd.DataFrame,
    *,
    base_size: float,
    mid_size: float,
    breadth_high: float,
    breadth_mid: float,
    vol_high: float,
    vol_mid: float,
    lag_high: float,
    lag_mid: float,
) -> pd.DataFrame:
    signal_days = predictions[["trade_date"]].drop_duplicates().merge(market, on="trade_date", how="left")
    signal_days["size_multiplier"] = base_size
    mid = (
        (signal_days["market_up_ratio"] <= breadth_mid)
        | (signal_days["market_volatility_5"] >= vol_mid)
        | (signal_days["market_10pct_density_ma5_lag1"] >= lag_mid)
    )
    high = (
        (signal_days["market_up_ratio"] <= breadth_high)
        | (signal_days["market_volatility_5"] >= vol_high)
        | (signal_days["market_10pct_density_ma5_lag1"] >= lag_high)
    )
    signal_days.loc[mid, "size_multiplier"] = mid_size
    signal_days.loc[high, "size_multiplier"] = 1.0
    out = predictions.copy()
    out["size_multiplier"] = out["trade_date"].map(signal_days.set_index("trade_date")["size_multiplier"]).fillna(1.0)
    return out


def score_monthly(curve: pd.DataFrame) -> tuple[float, float]:
    monthly = curve.copy()
    monthly["month"] = monthly["date"].dt.to_period("M").astype(str)
    month_end = monthly.groupby("month").tail(1)[["month", "equity_curve"]]
    month_start = monthly.groupby("month").head(1)[["month", "equity_curve"]].rename(
        columns={"equity_curve": "start_equity_curve"}
    )
    month_ret = month_end.merge(month_start, on="month", how="left")
    month_ret["month_return"] = month_ret["equity_curve"] / month_ret["start_equity_curve"] - 1
    return float((month_ret["month_return"] > 0).mean()), float(month_ret["month_return"].min())


def write_report(path: Path, summary: pd.DataFrame) -> None:
    lines = [
        "# M5 Position Sizing Grid",
        "",
        "Scope: small diagnostic grid around `combined_size`; fixed Top3 selection is unchanged.",
        "",
        "## Top By Risk-Adjusted Score",
        "",
        summary.head(30).to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Notes",
        "",
        "- `risk_score = total_return + 2 * max_drawdown`; max_drawdown is negative, so this penalizes drawdown.",
        "- A candidate should be compared with full-size Top3 before adoption.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred-root", type=Path, default=DEFAULT_PRED_ROOT)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--market", type=Path, default=DEFAULT_MARKET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--start-period", default="2025-05")
    parser.add_argument("--end-period", default="2026-04")
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--hold-sleeves", type=int, default=5)
    parser.add_argument("--initial-capital", type=float, default=1_000_000.0)
    args = parser.parse_args()

    backtest = load_module(BACKTEST_SCRIPT, "portfolio_backtest")
    sizing = load_module(SIZING_SCRIPT, "position_sizing")
    predictions = backtest.load_predictions(args.pred_root, args.start_period, args.end_period, args.top_n)
    market = sizing.load_market(args.market)
    truth = backtest.load_truth(args.features)
    rows: list[dict[str, object]] = []

    grid = product(
        [0.50, 0.60, 0.70],
        [0.75, 0.85, 0.90],
        [0.40],
        [0.60],
        [0.027],
        [0.024],
        [0.060, 0.064, 0.070],
        [0.042],
    )
    for i, values in enumerate(grid, start=1):
        (
            base_size,
            mid_size,
            breadth_high,
            breadth_mid,
            vol_high,
            vol_mid,
            lag_high,
            lag_mid,
        ) = values
        if breadth_high >= breadth_mid or vol_mid >= vol_high or lag_mid >= lag_high:
            continue
        policy_predictions = make_policy_predictions(
            predictions,
            market,
            base_size=base_size,
            mid_size=mid_size,
            breadth_high=breadth_high,
            breadth_mid=breadth_mid,
            vol_high=vol_high,
            vol_mid=vol_mid,
            lag_high=lag_high,
            lag_mid=lag_mid,
        )
        ledger = backtest.build_ledger(policy_predictions, truth, top_n=args.top_n, hold_sleeves=args.hold_sleeves)
        ledger, curve = sizing.simulate_with_sizing(ledger, args.initial_capital, args.hold_sleeves)
        positive_month_ratio, worst_month_return = score_monthly(curve)
        total_return = float(curve["equity_curve"].iloc[-1] - 1)
        max_drawdown = float(curve["drawdown"].min())
        exposure = curve["open_capital"] / curve["equity"]
        rows.append(
            {
                "grid_id": i,
                "base_size": base_size,
                "mid_size": mid_size,
                "breadth_high": breadth_high,
                "breadth_mid": breadth_mid,
                "vol_high": vol_high,
                "vol_mid": vol_mid,
                "lag_high": lag_high,
                "lag_mid": lag_mid,
                "avg_size_multiplier": float(policy_predictions["size_multiplier"].mean()),
                "final_equity_curve": float(curve["equity_curve"].iloc[-1]),
                "total_return": total_return,
                "max_drawdown": max_drawdown,
                "risk_score": total_return + 2 * max_drawdown,
                "positive_month_ratio": positive_month_ratio,
                "worst_month_return": worst_month_return,
                "avg_exposure": float(exposure.mean()),
            }
        )

    summary = pd.DataFrame(rows).sort_values(["risk_score", "total_return"], ascending=False)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(args.output_dir / "m5_position_sizing_grid.csv", index=False, encoding="utf-8-sig")
    write_report(args.output_dir / "m5_position_sizing_grid_report.md", summary)
    print(summary.head(30).to_string(index=False))
    print(f"wrote {args.output_dir / 'm5_position_sizing_grid_report.md'}")


if __name__ == "__main__":
    main()
