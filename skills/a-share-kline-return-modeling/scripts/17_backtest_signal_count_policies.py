#!/usr/bin/env python3
"""Portfolio backtest for M5 signal-count policy picks."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
BACKTEST_SCRIPT = ROOT / "skills/a-share-kline-return-modeling/scripts/14_backtest_portfolio_curve.py"
DEFAULT_PICKS = Path("skills/a-share-kline-return-modeling/outputs/evaluation/m5_signal_count/m5_signal_count_picks.csv")
DEFAULT_FEATURES = Path("skills/a-share-kline-return-modeling/data/clean_stock_features.csv")
DEFAULT_OUTPUT_DIR = Path("skills/a-share-kline-return-modeling/outputs/evaluation/m5_signal_count_portfolio")


def load_backtest_module():
    spec = importlib.util.spec_from_file_location("portfolio_backtest", BACKTEST_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {BACKTEST_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def summarize_policy(policy: str, ledger: pd.DataFrame, curve: pd.DataFrame) -> dict[str, object]:
    monthly = curve.copy()
    monthly["month"] = monthly["date"].dt.to_period("M").astype(str)
    month_end = monthly.groupby("month").tail(1)[["month", "equity_curve"]]
    month_start = monthly.groupby("month").head(1)[["month", "equity_curve"]].rename(
        columns={"equity_curve": "start_equity_curve"}
    )
    month_ret = month_end.merge(month_start, on="month", how="left")
    month_ret["month_return"] = month_ret["equity_curve"] / month_ret["start_equity_curve"] - 1
    exposure = curve["open_capital"] / curve["equity"]
    return {
        "policy": policy,
        "trades": len(ledger),
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
        "# M5 Signal Count Portfolio Backtest",
        "",
        "Scope: cash-constrained portfolio backtest for fixed and rule-based Top1/Top2/Top3 policies.",
        "",
        summary.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Current Read",
        "",
        "- `fixed_top3` remains the default unless a dynamic policy improves both return and drawdown stability.",
        "- Dynamic policies are diagnostic and are not yet adopted into the final signal layer.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--picks", type=Path, default=DEFAULT_PICKS)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--hold-sleeves", type=int, default=5)
    parser.add_argument("--initial-capital", type=float, default=1_000_000.0)
    args = parser.parse_args()

    backtest = load_backtest_module()
    picks = pd.read_csv(args.picks, encoding="utf-8-sig", parse_dates=["trade_date"])
    truth = backtest.load_truth(args.features)
    rows: list[dict[str, object]] = []
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for policy, group in picks.groupby("policy"):
        policy_dir = args.output_dir / policy
        policy_dir.mkdir(parents=True, exist_ok=True)
        ledger = backtest.build_ledger(group, truth, top_n=3, hold_sleeves=args.hold_sleeves)
        ledger, curve = backtest.simulate_curve(ledger, args.initial_capital, args.hold_sleeves)
        monthly = backtest.summarize_monthly(curve, ledger)
        ledger.to_csv(policy_dir / "portfolio_ledger.csv", index=False, encoding="utf-8-sig")
        curve.to_csv(policy_dir / "portfolio_curve.csv", index=False, encoding="utf-8-sig")
        monthly.to_csv(policy_dir / "portfolio_monthly_summary.csv", index=False, encoding="utf-8-sig")
        rows.append(summarize_policy(policy, ledger, curve))

    summary = pd.DataFrame(rows).sort_values(["final_equity_curve", "max_drawdown"], ascending=[False, False])
    summary.to_csv(args.output_dir / "m5_signal_count_portfolio_summary.csv", index=False, encoding="utf-8-sig")
    write_report(args.output_dir / "m5_signal_count_portfolio_report.md", summary)
    print(summary.to_string(index=False))
    print(f"wrote {args.output_dir / 'm5_signal_count_portfolio_report.md'}")


if __name__ == "__main__":
    main()
