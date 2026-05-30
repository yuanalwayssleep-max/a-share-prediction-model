#!/usr/bin/env python3
"""Analyze stability and attribution of the portfolio backtest."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_BACKTEST_DIR = Path("skills/a-share-kline-return-modeling/outputs/evaluation/portfolio_backtest")


def load_inputs(backtest_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    ledger = pd.read_csv(
        backtest_dir / "portfolio_ledger.csv",
        encoding="utf-8-sig",
        parse_dates=["trade_date", "entry_date", "realized_exit_date"],
    )
    curve = pd.read_csv(backtest_dir / "portfolio_curve.csv", encoding="utf-8-sig", parse_dates=["date"])
    ledger["pnl"] = pd.to_numeric(ledger["pnl"], errors="coerce").fillna(0)
    ledger["capital"] = pd.to_numeric(ledger["capital"], errors="coerce").fillna(0)
    ledger["realized_return"] = pd.to_numeric(ledger["realized_return"], errors="coerce")
    return ledger, curve


def summarize_monthly(ledger: pd.DataFrame, curve: pd.DataFrame) -> pd.DataFrame:
    trades = ledger.copy()
    trades["entry_month"] = trades["entry_date"].dt.to_period("M").astype(str)
    monthly_trades = (
        trades.groupby("entry_month")
        .agg(
            trades=("symbol", "count"),
            pnl=("pnl", "sum"),
            capital=("capital", "sum"),
            avg_return=("realized_return", "mean"),
            win_rate=("realized_return", lambda s: (s > 0).mean()),
            hit_top30=("label_top30", "mean"),
            hit_top10=("label_top10", "mean"),
            strong_10pct=("realized_return", lambda s: (s >= 0.10).mean()),
            loss_5pct=("realized_return", lambda s: (s <= -0.05).mean()),
            forced_exit_ratio=("forced_exit_delay_days", lambda s: (pd.to_numeric(s, errors="coerce").fillna(0) > 0).mean()),
        )
        .reset_index()
        .rename(columns={"entry_month": "month"})
    )

    month_curve = curve.copy()
    month_curve["month"] = month_curve["date"].dt.to_period("M").astype(str)
    curve_summary = (
        month_curve.groupby("month")
        .agg(
            start_equity=("equity", "first"),
            end_equity=("equity", "last"),
            min_drawdown=("drawdown", "min"),
            avg_exposure=("open_capital", lambda s: float((s / month_curve.loc[s.index, "equity"]).mean())),
            min_cash=("cash", "min"),
        )
        .reset_index()
    )
    curve_summary["equity_return"] = curve_summary["end_equity"] / curve_summary["start_equity"] - 1
    return monthly_trades.merge(curve_summary, on="month", how="outer").sort_values("month")


def summarize_industry(ledger: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    by_industry = (
        ledger.groupby("industry")
        .agg(
            trades=("symbol", "count"),
            pnl=("pnl", "sum"),
            capital=("capital", "sum"),
            avg_return=("realized_return", "mean"),
            win_rate=("realized_return", lambda s: (s > 0).mean()),
            hit_top30=("label_top30", "mean"),
        )
        .reset_index()
    )
    by_industry["pnl_per_capital"] = by_industry["pnl"] / by_industry["capital"].replace(0, pd.NA)
    by_industry = by_industry.sort_values("pnl", ascending=False)

    daily = (
        ledger.groupby(["trade_date", "industry"])
        .size()
        .rename("picks")
        .reset_index()
    )
    daily["total_picks"] = daily.groupby("trade_date")["picks"].transform("sum")
    daily["weight"] = daily["picks"] / daily["total_picks"]
    concentration = (
        daily.groupby("trade_date")
        .agg(
            industry_count=("industry", "count"),
            max_industry_weight=("weight", "max"),
            industry_hhi=("weight", lambda s: float((s * s).sum())),
        )
        .reset_index()
    )
    concentration["month"] = concentration["trade_date"].dt.to_period("M").astype(str)
    concentration_monthly = (
        concentration.groupby("month")
        .agg(
            avg_industry_count=("industry_count", "mean"),
            avg_max_industry_weight=("max_industry_weight", "mean"),
            avg_industry_hhi=("industry_hhi", "mean"),
            same_industry_top3_days=("max_industry_weight", lambda s: int((s >= 0.999).sum())),
        )
        .reset_index()
    )
    return by_industry, concentration_monthly


def find_drawdown_periods(curve: pd.DataFrame) -> pd.DataFrame:
    work = curve.sort_values("date").copy()
    work["is_drawdown"] = work["drawdown"] < 0
    periods: list[dict[str, object]] = []
    current: list[pd.Series] = []
    for _, row in work.iterrows():
        if row["is_drawdown"]:
            current.append(row)
        elif current:
            block = pd.DataFrame(current)
            trough = block.loc[block["drawdown"].idxmin()]
            periods.append(
                {
                    "start_date": block["date"].iloc[0],
                    "end_date": block["date"].iloc[-1],
                    "trough_date": trough["date"],
                    "min_drawdown": trough["drawdown"],
                    "days": len(block),
                }
            )
            current = []
    if current:
        block = pd.DataFrame(current)
        trough = block.loc[block["drawdown"].idxmin()]
        periods.append(
            {
                "start_date": block["date"].iloc[0],
                "end_date": block["date"].iloc[-1],
                "trough_date": trough["date"],
                "min_drawdown": trough["drawdown"],
                "days": len(block),
            }
        )
    return pd.DataFrame(periods).sort_values("min_drawdown") if periods else pd.DataFrame()


def contribution_summary(ledger: pd.DataFrame, initial_capital: float) -> dict[str, float]:
    total_pnl = float(ledger["pnl"].sum())
    winners = ledger[ledger["pnl"] > 0].sort_values("pnl", ascending=False)
    losers = ledger[ledger["pnl"] < 0].sort_values("pnl")
    top_5_pnl = float(winners.head(5)["pnl"].sum())
    top_10_pnl = float(winners.head(10)["pnl"].sum())
    top_20_pnl = float(winners.head(20)["pnl"].sum())
    return {
        "total_pnl": total_pnl,
        "top_5_winner_pnl_share": float(top_5_pnl / total_pnl) if total_pnl else 0.0,
        "top_10_winner_pnl_share": float(top_10_pnl / total_pnl) if total_pnl else 0.0,
        "top_20_winner_pnl_share": float(top_20_pnl / total_pnl) if total_pnl else 0.0,
        "return_without_top_5_winners": float((total_pnl - top_5_pnl) / initial_capital),
        "return_without_top_10_winners": float((total_pnl - top_10_pnl) / initial_capital),
        "return_without_top_20_winners": float((total_pnl - top_20_pnl) / initial_capital),
        "bottom_10_loser_drag_share": float(losers.head(10)["pnl"].sum() / total_pnl) if total_pnl else 0.0,
        "winner_pnl": float(winners["pnl"].sum()),
        "loser_pnl": float(losers["pnl"].sum()),
        "win_loss_pnl_multiple": float(winners["pnl"].sum() / abs(losers["pnl"].sum())) if not losers.empty else 0.0,
    }


def select_trade_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "trade_date",
        "entry_date",
        "realized_exit_date",
        "symbol",
        "name",
        "industry",
        "pick_rank",
        "realized_return",
        "pnl",
        "capital",
        "label_top10",
        "label_top30",
        "rank_strength_score",
    ]
    return df[[col for col in cols if col in df.columns]]


def write_report(
    path: Path,
    monthly: pd.DataFrame,
    industry: pd.DataFrame,
    concentration: pd.DataFrame,
    drawdowns: pd.DataFrame,
    top_winners: pd.DataFrame,
    top_losers: pd.DataFrame,
    contribution: dict[str, float],
) -> None:
    lines = [
        "# M4 Portfolio Stability Analysis",
        "",
        "Scope: cash-constrained Top3 portfolio backtest from monthly stock-rank predictions.",
        "",
        "## Contribution Concentration",
        "",
    ]
    for key, value in contribution.items():
        if key.endswith("share") or key.startswith("return_without"):
            lines.append(f"- {key}: {value:.2%}")
        elif key.endswith("multiple"):
            lines.append(f"- {key}: {value:.2f}x")
        else:
            lines.append(f"- {key}: {value:.2f}")
    lines.extend(
        [
            "",
            "## Monthly Attribution",
            "",
            monthly.to_markdown(index=False, floatfmt=".4f"),
            "",
            "## Worst Drawdowns",
            "",
            drawdowns.head(10).to_markdown(index=False, floatfmt=".4f") if not drawdowns.empty else "No drawdowns.",
            "",
            "## Top Industry Contribution",
            "",
            industry.head(15).to_markdown(index=False, floatfmt=".4f"),
            "",
            "## Industry Concentration By Month",
            "",
            concentration.to_markdown(index=False, floatfmt=".4f"),
            "",
            "## Top Winning Trades",
            "",
            top_winners.to_markdown(index=False, floatfmt=".4f"),
            "",
            "## Top Losing Trades",
            "",
            top_losers.to_markdown(index=False, floatfmt=".4f"),
            "",
            "## Notes",
            "",
            "- Months after the last signal month can appear because April positions exit in May.",
            "- Contribution shares use realized PnL, so late-period trades naturally carry larger capital after compounding.",
            "- This report is diagnostic; it does not change the model or trading rules.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backtest-dir", type=Path, default=DEFAULT_BACKTEST_DIR)
    args = parser.parse_args()

    ledger, curve = load_inputs(args.backtest_dir)
    monthly = summarize_monthly(ledger, curve)
    industry, concentration = summarize_industry(ledger)
    drawdowns = find_drawdown_periods(curve)
    top_winners = select_trade_columns(ledger.sort_values("pnl", ascending=False).head(20))
    top_losers = select_trade_columns(ledger.sort_values("pnl", ascending=True).head(20))
    initial_capital = float(curve["equity"].iloc[0])
    contribution = contribution_summary(ledger, initial_capital)

    args.backtest_dir.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(args.backtest_dir / "m4_monthly_attribution.csv", index=False, encoding="utf-8-sig")
    industry.to_csv(args.backtest_dir / "m4_industry_attribution.csv", index=False, encoding="utf-8-sig")
    concentration.to_csv(args.backtest_dir / "m4_industry_concentration.csv", index=False, encoding="utf-8-sig")
    drawdowns.to_csv(args.backtest_dir / "m4_drawdown_periods.csv", index=False, encoding="utf-8-sig")
    top_winners.to_csv(args.backtest_dir / "m4_top_winning_trades.csv", index=False, encoding="utf-8-sig")
    top_losers.to_csv(args.backtest_dir / "m4_top_losing_trades.csv", index=False, encoding="utf-8-sig")
    write_report(
        args.backtest_dir / "m4_stability_report.md",
        monthly,
        industry,
        concentration,
        drawdowns,
        top_winners,
        top_losers,
        contribution,
    )
    print((args.backtest_dir / "m4_stability_report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
