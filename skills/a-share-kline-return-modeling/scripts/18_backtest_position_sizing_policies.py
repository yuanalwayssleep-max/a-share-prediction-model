#!/usr/bin/env python3
"""Backtest M5 position sizing policies while keeping Top3 stock selection."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
BACKTEST_SCRIPT = ROOT / "skills/a-share-kline-return-modeling/scripts/14_backtest_portfolio_curve.py"
DEFAULT_PRED_ROOT = Path("skills/a-share-kline-return-modeling/outputs/stock_rank_predictions")
DEFAULT_FEATURES = Path("skills/a-share-kline-return-modeling/data/clean_stock_features.csv")
DEFAULT_MARKET = Path("skills/a-share-kline-return-modeling/data/market_signal_features.csv")
DEFAULT_OUTPUT_DIR = Path("skills/a-share-kline-return-modeling/outputs/evaluation/m5_position_sizing")


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


def load_backtest_module():
    spec = importlib.util.spec_from_file_location("portfolio_backtest", BACKTEST_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {BACKTEST_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_market(path: Path) -> pd.DataFrame:
    available = pd.read_csv(path, encoding="utf-8-sig", nrows=0).columns
    usecols = [col for col in MARKET_COLS if col in available]
    return pd.read_csv(path, encoding="utf-8-sig", usecols=usecols, parse_dates=["trade_date"])


def add_sizing_multipliers(signal_days: pd.DataFrame) -> pd.DataFrame:
    out = signal_days.copy()
    out["full_size"] = 1.0

    out["contra_breadth_size"] = 0.50
    out.loc[out["market_up_ratio"] <= 0.60, "contra_breadth_size"] = 0.75
    out.loc[out["market_up_ratio"] <= 0.40, "contra_breadth_size"] = 1.00

    out["volatility_size"] = 0.50
    out.loc[out["market_volatility_5"] >= 0.024, "volatility_size"] = 0.75
    out.loc[out["market_volatility_5"] >= 0.027, "volatility_size"] = 1.00

    out["lag_density_size"] = 0.50
    out.loc[out["market_10pct_density_ma5_lag1"] >= 0.042, "lag_density_size"] = 0.75
    out.loc[out["market_10pct_density_ma5_lag1"] >= 0.064, "lag_density_size"] = 1.00

    out["combined_size"] = 0.50
    mid = (
        (out["market_up_ratio"] <= 0.60)
        | (out["market_volatility_5"] >= 0.024)
        | (out["market_10pct_density_ma5_lag1"] >= 0.042)
    )
    high = (
        (out["market_up_ratio"] <= 0.40)
        | (out["market_volatility_5"] >= 0.027)
        | (out["market_10pct_density_ma5_lag1"] >= 0.064)
    )
    out.loc[mid, "combined_size"] = 0.75
    out.loc[high, "combined_size"] = 1.00

    out["combined_size_v2"] = 0.50
    out.loc[mid, "combined_size_v2"] = 0.90
    out.loc[high, "combined_size_v2"] = 1.00

    out["overheat_reduce_size"] = 1.00
    overheat = (out["market_up_ratio"] >= 0.70) & (out["market_avg_pct_chg"] >= 1.00)
    out.loc[overheat, "overheat_reduce_size"] = 0.50

    out["weak_breadth_cut_size"] = 1.00
    weak = (out["market_up_ratio"] <= 0.25) & (out["market_avg_pct_chg"] <= -1.00)
    out.loc[weak, "weak_breadth_cut_size"] = 0.50
    return out


def attach_policy_multiplier(predictions: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    signal_days = predictions[["trade_date"]].drop_duplicates().merge(market, on="trade_date", how="left")
    signal_days = add_sizing_multipliers(signal_days)
    policy_cols = [
        "full_size",
        "contra_breadth_size",
        "volatility_size",
        "lag_density_size",
        "combined_size",
        "combined_size_v2",
        "overheat_reduce_size",
        "weak_breadth_cut_size",
    ]
    frames: list[pd.DataFrame] = []
    for policy in policy_cols:
        multiplier = signal_days.set_index("trade_date")[policy]
        work = predictions.copy()
        work["policy"] = policy
        work["size_multiplier"] = work["trade_date"].map(multiplier).fillna(1.0).astype(float)
        frames.append(work)
    return pd.concat(frames, ignore_index=True)


def simulate_with_sizing(
    ledger: pd.DataFrame,
    initial_capital: float,
    hold_sleeves: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = ledger.copy()
    work["entry_date"] = pd.to_datetime(work["entry_date"])
    work["realized_exit_date"] = pd.to_datetime(work["realized_exit_date"])
    dates = sorted(set(work["entry_date"].dropna()) | set(work["realized_exit_date"].dropna()))
    cash = initial_capital
    rows: list[dict[str, object]] = []
    pending = work.copy()
    pending["entry_equity"] = pd.NA
    pending["capital"] = pd.NA
    pending["pnl"] = pd.NA

    for current_date in dates:
        exit_mask = pending["realized_exit_date"] == current_date
        realized_pnl = float(pd.to_numeric(pending.loc[exit_mask, "pnl"], errors="coerce").fillna(0).sum())
        returned_capital = float(pd.to_numeric(pending.loc[exit_mask, "capital"], errors="coerce").fillna(0).sum())
        cash += returned_capital + realized_pnl

        open_mask_before_entry = (pending["entry_date"] < current_date) & (pending["realized_exit_date"] > current_date)
        open_capital_before_entry = float(
            pd.to_numeric(pending.loc[open_mask_before_entry, "capital"], errors="coerce").fillna(0).sum()
        )
        equity_before_entry = cash + open_capital_before_entry

        entry_mask = pending["entry_date"] == current_date
        pick_count = int(entry_mask.sum())
        size_multiplier = (
            float(pd.to_numeric(pending.loc[entry_mask, "size_multiplier"], errors="coerce").fillna(1.0).max())
            if pick_count
            else 0.0
        )
        sleeve_capital = min(equity_before_entry / hold_sleeves * size_multiplier, cash)
        per_position_capital = sleeve_capital / pick_count if pick_count else 0.0
        if pick_count:
            pending.loc[entry_mask, "entry_equity"] = equity_before_entry
            pending.loc[entry_mask, "capital"] = per_position_capital
            pending.loc[entry_mask, "pnl"] = per_position_capital * pending.loc[entry_mask, "realized_return"].astype(float)
            cash -= sleeve_capital

        open_mask = (pending["entry_date"] <= current_date) & (pending["realized_exit_date"] > current_date)
        open_capital = float(pd.to_numeric(pending.loc[open_mask, "capital"], errors="coerce").fillna(0).sum())
        equity = cash + open_capital
        rows.append(
            {
                "date": current_date,
                "equity": equity,
                "realized_pnl": realized_pnl,
                "returned_capital": returned_capital,
                "new_positions": pick_count,
                "size_multiplier": size_multiplier,
                "open_positions": int(open_mask.sum()),
                "open_capital": open_capital,
                "cash": cash,
            }
        )

    curve = pd.DataFrame(rows)
    curve["equity_curve"] = curve["equity"] / initial_capital
    curve["running_max"] = curve["equity_curve"].cummax()
    curve["drawdown"] = curve["equity_curve"] / curve["running_max"] - 1
    return pending, curve


def summarize_policy(policy: str, ledger: pd.DataFrame, curve: pd.DataFrame) -> dict[str, object]:
    month_curve = curve.copy()
    month_curve["month"] = month_curve["date"].dt.to_period("M").astype(str)
    month_end = month_curve.groupby("month").tail(1)[["month", "equity_curve"]]
    month_start = month_curve.groupby("month").head(1)[["month", "equity_curve"]].rename(
        columns={"equity_curve": "start_equity_curve"}
    )
    month_ret = month_end.merge(month_start, on="month", how="left")
    month_ret["month_return"] = month_ret["equity_curve"] / month_ret["start_equity_curve"] - 1
    exposure = curve["open_capital"] / curve["equity"]
    return {
        "policy": policy,
        "trades": len(ledger),
        "avg_size_multiplier": float(ledger["size_multiplier"].mean()),
        "final_equity_curve": float(curve["equity_curve"].iloc[-1]),
        "total_return": float(curve["equity_curve"].iloc[-1] - 1),
        "max_drawdown": float(curve["drawdown"].min()),
        "avg_trade_return": float(ledger["realized_return"].mean()),
        "weighted_trade_return": float(ledger["pnl"].sum() / ledger["capital"].sum()),
        "trade_win_rate": float((ledger["realized_return"] > 0).mean()),
        "positive_month_ratio": float((month_ret["month_return"] > 0).mean()),
        "worst_month_return": float(month_ret["month_return"].min()),
        "avg_exposure": float(exposure.mean()),
        "max_exposure": float(exposure.max()),
    }


def write_report(path: Path, summary: pd.DataFrame) -> None:
    lines = [
        "# M5 Position Sizing Policy Backtest",
        "",
        "Scope: fixed Top3 selection, dynamic new-sleeve capital multiplier.",
        "",
        summary.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Current Read",
        "",
        "- A sizing policy must improve drawdown without materially reducing total return before it can replace full-size Top3.",
        "- These policies are diagnostic only and are not part of the final signal layer yet.",
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

    backtest = load_backtest_module()
    predictions = backtest.load_predictions(args.pred_root, args.start_period, args.end_period, args.top_n)
    market = load_market(args.market)
    policy_predictions = attach_policy_multiplier(predictions, market)
    truth = backtest.load_truth(args.features)
    rows: list[dict[str, object]] = []

    args.output_dir.mkdir(parents=True, exist_ok=True)
    policy_predictions.to_csv(args.output_dir / "m5_position_sizing_policy_predictions.csv", index=False, encoding="utf-8-sig")
    for policy, group in policy_predictions.groupby("policy"):
        policy_dir = args.output_dir / policy
        policy_dir.mkdir(parents=True, exist_ok=True)
        ledger = backtest.build_ledger(group, truth, top_n=args.top_n, hold_sleeves=args.hold_sleeves)
        ledger, curve = simulate_with_sizing(ledger, args.initial_capital, args.hold_sleeves)
        monthly = backtest.summarize_monthly(curve, ledger)
        ledger.to_csv(policy_dir / "portfolio_ledger.csv", index=False, encoding="utf-8-sig")
        curve.to_csv(policy_dir / "portfolio_curve.csv", index=False, encoding="utf-8-sig")
        monthly.to_csv(policy_dir / "portfolio_monthly_summary.csv", index=False, encoding="utf-8-sig")
        rows.append(summarize_policy(policy, ledger, curve))

    summary = pd.DataFrame(rows).sort_values(["final_equity_curve", "max_drawdown"], ascending=[False, False])
    summary.to_csv(args.output_dir / "m5_position_sizing_summary.csv", index=False, encoding="utf-8-sig")
    write_report(args.output_dir / "m5_position_sizing_report.md", summary)
    print(summary.to_string(index=False))
    print(f"wrote {args.output_dir / 'm5_position_sizing_report.md'}")


if __name__ == "__main__":
    main()
