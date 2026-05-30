#!/usr/bin/env python3
"""Backtest truth-free final signal files by merging execution truth only inside evaluation."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
BACKTEST_SCRIPT = ROOT / "skills/a-share-kline-return-modeling/scripts/14_backtest_portfolio_curve.py"
SIZING_SCRIPT = ROOT / "skills/a-share-kline-return-modeling/scripts/18_backtest_position_sizing_policies.py"
DEFAULT_FEATURES = Path("skills/a-share-kline-return-modeling/data/clean_stock_features.csv")
DEFAULT_OUTPUT_DIR = Path("skills/a-share-kline-return-modeling/outputs/evaluation/final_signal_backtest")

FORBIDDEN_SIGNAL_PREFIXES = ("future_", "label_", "actual_")
FORBIDDEN_SIGNAL_COLUMNS = {"entry_price", "exit_price", "gross_future_5_return"}


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_final_signals(path: Path) -> pd.DataFrame:
    signals = pd.read_csv(path, encoding="utf-8-sig", parse_dates=["trade_date"])
    forbidden = [
        col
        for col in signals.columns
        if col in FORBIDDEN_SIGNAL_COLUMNS or col.startswith(FORBIDDEN_SIGNAL_PREFIXES)
    ]
    if forbidden:
        raise ValueError(f"Final signal file contains forbidden truth columns: {forbidden}")
    required = {"trade_date", "symbol", "position_size_multiplier", "rank_strength_score"}
    missing = sorted(required - set(signals.columns))
    if missing:
        raise ValueError(f"Final signal file missing required columns: {missing}")
    signals["symbol"] = signals["symbol"].astype(str).str.zfill(6)
    signals["pick_rank"] = signals.get("pick_rank", signals.groupby("trade_date").cumcount() + 1)
    signals["size_multiplier"] = signals["position_size_multiplier"]
    return signals


def summarize(signal_path: Path, ledger: pd.DataFrame, curve: pd.DataFrame) -> dict[str, object]:
    monthly = curve.copy()
    monthly["month"] = monthly["date"].dt.to_period("M").astype(str)
    month_end = monthly.groupby("month").tail(1)[["month", "equity_curve"]]
    month_end["start_equity_curve"] = month_end["equity_curve"].shift(1).fillna(1.0)
    month_ret = month_end
    month_ret["month_return"] = month_ret["equity_curve"] / month_ret["start_equity_curve"] - 1
    exposure = curve["open_capital"] / curve["equity"]
    return {
        "signal_file": signal_path.name,
        "policy": ledger["position_policy"].iloc[0] if "position_policy" in ledger.columns and not ledger.empty else "",
        "trades": len(ledger),
        "signal_days": int(ledger["trade_date"].nunique()),
        "avg_size_multiplier": float(ledger["position_size_multiplier"].mean()),
        "final_equity_curve": float(curve["equity_curve"].iloc[-1]),
        "total_return": float(curve["equity_curve"].iloc[-1] - 1),
        "max_drawdown": float(curve["drawdown"].min()),
        "avg_trade_return": float(ledger["realized_return"].mean()),
        "trade_win_rate": float((ledger["realized_return"] > 0).mean()),
        "positive_month_ratio": float((month_ret["month_return"] > 0).mean()),
        "worst_month_return": float(month_ret["month_return"].min()),
        "avg_exposure": float(exposure.mean()),
        "max_exposure": float(exposure.max()),
    }


def write_report(path: Path, summary: pd.DataFrame) -> None:
    lines = [
        "# Final Signal Backtest",
        "",
        "Scope: reads truth-free final signal files and merges execution truth only inside evaluation.",
        "",
        summary.to_markdown(index=False, floatfmt=".4f"),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("signals", nargs="+", type=Path)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--hold-sleeves", type=int, default=5)
    parser.add_argument("--initial-capital", type=float, default=1_000_000.0)
    args = parser.parse_args()

    backtest = load_module(BACKTEST_SCRIPT, "portfolio_backtest")
    sizing = load_module(SIZING_SCRIPT, "position_sizing")
    truth = backtest.load_truth(args.features)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []

    for signal_path in args.signals:
        signals = load_final_signals(signal_path)
        policy = signals["position_policy"].iloc[0] if "position_policy" in signals.columns and not signals.empty else signal_path.stem
        policy_dir = args.output_dir / policy
        policy_dir.mkdir(parents=True, exist_ok=True)
        daily_pick_count = signals.groupby("trade_date")["symbol"].count()
        if (daily_pick_count <= 0).any():
            raise ValueError(f"Signal file contains empty daily picks: {signal_path}")
        ledger = backtest.build_ledger(signals, truth, top_n=int(daily_pick_count.max()), hold_sleeves=args.hold_sleeves)
        ledger, curve = sizing.simulate_with_sizing(ledger, args.initial_capital, args.hold_sleeves)
        monthly = backtest.summarize_monthly(curve, ledger, args.initial_capital)
        ledger.to_csv(policy_dir / "portfolio_ledger.csv", index=False, encoding="utf-8-sig")
        curve.to_csv(policy_dir / "portfolio_curve.csv", index=False, encoding="utf-8-sig")
        monthly.to_csv(policy_dir / "portfolio_monthly_summary.csv", index=False, encoding="utf-8-sig")
        rows.append(summarize(signal_path, ledger, curve))

    summary = pd.DataFrame(rows).sort_values(["final_equity_curve", "max_drawdown"], ascending=[False, False])
    summary.to_csv(args.output_dir / "final_signal_backtest_summary.csv", index=False, encoding="utf-8-sig")
    write_report(args.output_dir / "final_signal_backtest_report.md", summary)
    print(summary.to_string(index=False))
    print(f"wrote {args.output_dir / 'final_signal_backtest_report.md'}")


if __name__ == "__main__":
    main()
