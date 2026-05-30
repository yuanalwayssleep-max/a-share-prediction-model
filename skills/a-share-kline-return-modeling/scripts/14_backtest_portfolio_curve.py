#!/usr/bin/env python3
"""Build a simple overlapping 5-day portfolio curve from stock-rank predictions."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_PRED_ROOT = Path("skills/a-share-kline-return-modeling/outputs/stock_rank_predictions")
DEFAULT_FEATURES = Path("skills/a-share-kline-return-modeling/data/clean_stock_features.csv")
DEFAULT_OUTPUT_DIR = Path("skills/a-share-kline-return-modeling/outputs/evaluation/portfolio_backtest")
FORBIDDEN_PREDICTION_PREFIXES = ("future_", "label_", "actual_")
FORBIDDEN_PREDICTION_COLUMNS = {"entry_price", "exit_price", "gross_future_5_return"}


def forbidden_prediction_columns(columns: list[str]) -> list[str]:
    return [
        col
        for col in columns
        if col in FORBIDDEN_PREDICTION_COLUMNS or col.startswith(FORBIDDEN_PREDICTION_PREFIXES)
    ]


def load_predictions(pred_root: Path, start_period: str, end_period: str, top_n: int) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(pred_root.glob("20??-??/predictions.csv")):
        period = path.parent.name
        if period < start_period or period > end_period:
            continue
        df = pd.read_csv(path, encoding="utf-8-sig", parse_dates=["trade_date"])
        forbidden = forbidden_prediction_columns(list(df.columns))
        if forbidden:
            raise ValueError(f"Prediction input contains forbidden truth columns in {path}: {forbidden}")
        df["period"] = period
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No monthly predictions found under {pred_root}")
    pred = pd.concat(frames, ignore_index=True)
    pred = (
        pred.sort_values(["trade_date", "rank_strength_score", "symbol"], ascending=[True, False, True])
        .groupby("trade_date", group_keys=False)
        .head(top_n)
        .copy()
    )
    pred["pick_rank"] = pred.groupby("trade_date").cumcount() + 1
    return pred


def load_truth(features_path: Path) -> pd.DataFrame:
    cols = [
        "trade_date",
        "symbol",
        "entry_trade_date",
        "exit_trade_date",
        "actual_exit_trade_date",
        "entry_price",
        "exit_price",
        "future_5_return",
        "actual_future_5_return",
        "tradable_at_entry",
        "tradable_at_exit",
        "limit_up_at_entry",
        "limit_down_during_holding",
        "suspended_during_holding",
        "forced_exit_delay_days",
    ]
    available = pd.read_csv(features_path, encoding="utf-8-sig", nrows=0).columns
    usecols = [col for col in cols if col in available]
    date_cols = [col for col in ["trade_date", "entry_trade_date", "exit_trade_date", "actual_exit_trade_date"] if col in usecols]
    truth = pd.read_csv(features_path, encoding="utf-8-sig", usecols=usecols, parse_dates=date_cols)
    truth["symbol"] = truth["symbol"].astype(str).str.zfill(6)
    return truth


def build_ledger(predictions: pd.DataFrame, truth: pd.DataFrame, top_n: int, hold_sleeves: int) -> pd.DataFrame:
    pred = predictions.copy()
    forbidden = forbidden_prediction_columns(list(pred.columns))
    if forbidden:
        raise ValueError(f"Prediction input contains forbidden truth columns: {forbidden}")
    pred["symbol"] = pred["symbol"].astype(str).str.zfill(6)
    merge_cols = ["trade_date", "symbol"]
    extra_cols = [col for col in truth.columns if col not in merge_cols]
    ledger = pred.merge(truth[merge_cols + extra_cols], on=merge_cols, how="left", suffixes=("", "_truth"))
    if "actual_future_5_return" in ledger.columns:
        ledger["realized_return"] = ledger["actual_future_5_return"].fillna(ledger["future_5_return"])
    else:
        ledger["realized_return"] = ledger["future_5_return"]
    if "actual_exit_trade_date" in ledger.columns:
        ledger["realized_exit_date"] = ledger["actual_exit_trade_date"].fillna(ledger["exit_trade_date"])
    else:
        ledger["realized_exit_date"] = ledger["exit_trade_date"]
    ledger["entry_date"] = ledger["entry_trade_date"].fillna(ledger["trade_date"])
    if "pick_rank" not in ledger.columns:
        ledger["pick_rank"] = ledger.groupby("trade_date").cumcount() + 1
    daily_pick_count = ledger.groupby("trade_date")["symbol"].transform("count").clip(lower=1)
    ledger["target_weight"] = 1.0 / hold_sleeves / daily_pick_count
    return ledger.sort_values(["entry_date", "pick_rank", "symbol"]).reset_index(drop=True)


def simulate_curve(ledger: pd.DataFrame, initial_capital: float, hold_sleeves: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    work = ledger.copy()
    work["entry_date"] = pd.to_datetime(work["entry_date"])
    work["realized_exit_date"] = pd.to_datetime(work["realized_exit_date"])
    dates = sorted(set(work["entry_date"].dropna()) | set(work["realized_exit_date"].dropna()))
    cash = initial_capital
    curve_rows: list[dict[str, object]] = []
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
        sleeve_capital = min(equity_before_entry / hold_sleeves, cash)
        per_position_capital = sleeve_capital / pick_count if pick_count else 0.0
        if pick_count:
            pending.loc[entry_mask, "entry_equity"] = equity_before_entry
            pending.loc[entry_mask, "capital"] = per_position_capital
            pending.loc[entry_mask, "pnl"] = per_position_capital * pending.loc[entry_mask, "realized_return"].astype(float)
            cash -= sleeve_capital

        open_mask = (pending["entry_date"] <= current_date) & (pending["realized_exit_date"] > current_date)
        open_capital = float(pd.to_numeric(pending.loc[open_mask, "capital"], errors="coerce").fillna(0).sum())
        equity = cash + open_capital
        curve_rows.append(
            {
                "date": current_date,
                "equity": equity,
                "realized_pnl": realized_pnl,
                "returned_capital": returned_capital,
                "new_positions": pick_count,
                "open_positions": int(open_mask.sum()),
                "open_capital": open_capital,
                "cash": cash,
            }
        )

    curve = pd.DataFrame(curve_rows)
    curve["equity_curve"] = curve["equity"] / initial_capital
    curve["running_max"] = curve["equity_curve"].cummax()
    curve["drawdown"] = curve["equity_curve"] / curve["running_max"] - 1
    return pending, curve


def summarize_monthly(curve: pd.DataFrame, ledger: pd.DataFrame, initial_capital: float = 1_000_000.0) -> pd.DataFrame:
    month_curve = curve.copy()
    month_curve["month"] = month_curve["date"].dt.to_period("M").astype(str)
    month_end = month_curve.groupby("month").tail(1)[["month", "equity_curve", "drawdown"]].copy()
    month_end["month_start_equity_curve"] = month_end["equity_curve"].shift(1)
    month_end["month_start_equity_curve"] = month_end["month_start_equity_curve"].fillna(initial_capital / initial_capital)
    out = month_end.copy()
    out["month_return"] = out["equity_curve"] / out["month_start_equity_curve"] - 1
    trade = ledger.copy()
    trade["month"] = trade["entry_date"].dt.to_period("M").astype(str)
    trade_summary = (
        trade.groupby("month")
        .agg(
            trades=("symbol", "count"),
            avg_trade_return=("realized_return", "mean"),
            win_rate=("realized_return", lambda s: (s > 0).mean()),
            avg_hit_top30=("label_top30", "mean") if "label_top30" in trade.columns else ("symbol", "size"),
        )
        .reset_index()
    )
    return out.merge(trade_summary, on="month", how="left")


def write_report(path: Path, curve: pd.DataFrame, monthly: pd.DataFrame, ledger: pd.DataFrame) -> None:
    total_return = curve["equity_curve"].iloc[-1] - 1
    max_drawdown = curve["drawdown"].min()
    lines = [
        "# Portfolio Backtest",
        "",
        "Method: every signal day opens an equal-weight TopN basket, using one holding-period sleeve of capital. PnL is realized on `actual_exit_trade_date` when available.",
        "",
        "## Overall",
        "",
        f"- trades: {len(ledger)}",
        f"- final equity curve: {curve['equity_curve'].iloc[-1]:.4f}",
        f"- total return: {total_return:.2%}",
        f"- max drawdown: {max_drawdown:.2%}",
        f"- avg trade return: {ledger['realized_return'].mean():.2%}",
        f"- trade win rate: {(ledger['realized_return'] > 0).mean():.2%}",
        "",
        "## Monthly",
        "",
        monthly.to_markdown(index=False, floatfmt=".4f"),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred-root", type=Path, default=DEFAULT_PRED_ROOT)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--start-period", default="2025-05")
    parser.add_argument("--end-period", default="2026-04")
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--hold-sleeves", type=int, default=5)
    parser.add_argument("--initial-capital", type=float, default=1_000_000.0)
    args = parser.parse_args()

    predictions = load_predictions(args.pred_root, args.start_period, args.end_period, args.top_n)
    truth = load_truth(args.features)
    ledger = build_ledger(predictions, truth, args.top_n, args.hold_sleeves)
    ledger, curve = simulate_curve(ledger, args.initial_capital, args.hold_sleeves)
    monthly = summarize_monthly(curve, ledger, args.initial_capital)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(args.output_dir / "portfolio_ledger.csv", index=False, encoding="utf-8-sig")
    curve.to_csv(args.output_dir / "portfolio_curve.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(args.output_dir / "portfolio_monthly_summary.csv", index=False, encoding="utf-8-sig")
    write_report(args.output_dir / "portfolio_backtest_report.md", curve, monthly, ledger)
    print((args.output_dir / "portfolio_backtest_report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
