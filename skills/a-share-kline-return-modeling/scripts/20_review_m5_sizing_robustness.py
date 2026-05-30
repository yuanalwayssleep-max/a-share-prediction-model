#!/usr/bin/env python3
"""Review robustness of the M5 combined_size_v2 sizing candidate."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_SIZING_DIR = Path("skills/a-share-kline-return-modeling/outputs/evaluation/m5_position_sizing")
DEFAULT_GRID_PATH = Path("skills/a-share-kline-return-modeling/outputs/evaluation/m5_position_sizing_grid/m5_position_sizing_grid.csv")
DEFAULT_OUTPUT_DIR = Path("skills/a-share-kline-return-modeling/outputs/evaluation/m5_sizing_robustness")


def load_policy(sizing_dir: Path, policy: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    policy_dir = sizing_dir / policy
    ledger = pd.read_csv(
        policy_dir / "portfolio_ledger.csv",
        encoding="utf-8-sig",
        parse_dates=["trade_date", "entry_date", "realized_exit_date"],
    )
    curve = pd.read_csv(policy_dir / "portfolio_curve.csv", encoding="utf-8-sig", parse_dates=["date"])
    monthly = pd.read_csv(policy_dir / "portfolio_monthly_summary.csv", encoding="utf-8-sig")
    ledger["pnl"] = pd.to_numeric(ledger["pnl"], errors="coerce").fillna(0)
    ledger["capital"] = pd.to_numeric(ledger["capital"], errors="coerce").fillna(0)
    ledger["realized_return"] = pd.to_numeric(ledger["realized_return"], errors="coerce")
    return ledger, curve, monthly


def monthly_compare(full_monthly: pd.DataFrame, candidate_monthly: pd.DataFrame) -> pd.DataFrame:
    cols = ["month", "month_return", "drawdown", "avg_trade_return", "win_rate", "trades"]
    out = full_monthly[cols].merge(candidate_monthly[cols], on="month", suffixes=("_full", "_candidate"))
    out["month_return_delta"] = out["month_return_candidate"] - out["month_return_full"]
    out["drawdown_delta"] = out["drawdown_candidate"] - out["drawdown_full"]
    out["candidate_better_return"] = out["month_return_delta"] > 0
    out["candidate_better_drawdown"] = out["drawdown_delta"] > 0
    return out


def contribution_without_top_winners(ledger: pd.DataFrame, initial_capital: float, cuts: list[int]) -> pd.DataFrame:
    winners = ledger[ledger["pnl"] > 0].sort_values("pnl", ascending=False)
    rows: list[dict[str, object]] = []
    total_pnl = float(ledger["pnl"].sum())
    for cut in cuts:
        removed = float(winners.head(cut)["pnl"].sum())
        remain = total_pnl - removed
        rows.append(
            {
                "remove_top_winners": cut,
                "removed_pnl": removed,
                "remaining_pnl": remain,
                "remaining_return_on_initial": remain / initial_capital,
                "removed_share_of_total_pnl": removed / total_pnl if total_pnl else 0.0,
            }
        )
    return pd.DataFrame(rows)


def compare_without_top_winners(
    full_ledger: pd.DataFrame,
    candidate_ledger: pd.DataFrame,
    initial_capital: float,
) -> pd.DataFrame:
    cuts = [0, 5, 10, 20, 30]
    full = contribution_without_top_winners(full_ledger, initial_capital, cuts).rename(
        columns={
            "remaining_pnl": "remaining_pnl_full",
            "remaining_return_on_initial": "remaining_return_full",
            "removed_share_of_total_pnl": "removed_share_full",
        }
    )
    candidate = contribution_without_top_winners(candidate_ledger, initial_capital, cuts).rename(
        columns={
            "remaining_pnl": "remaining_pnl_candidate",
            "remaining_return_on_initial": "remaining_return_candidate",
            "removed_share_of_total_pnl": "removed_share_candidate",
        }
    )
    out = full[
        ["remove_top_winners", "remaining_pnl_full", "remaining_return_full", "removed_share_full"]
    ].merge(
        candidate[
            ["remove_top_winners", "remaining_pnl_candidate", "remaining_return_candidate", "removed_share_candidate"]
        ],
        on="remove_top_winners",
    )
    out["remaining_return_delta"] = out["remaining_return_candidate"] - out["remaining_return_full"]
    return out


def grid_sensitivity(grid_path: Path, candidate_params: dict[str, float]) -> pd.DataFrame:
    grid = pd.read_csv(grid_path, encoding="utf-8-sig")
    if grid.empty:
        return grid
    # Keep the neighborhood used by combined_size_v2 and sort by risk score.
    mask = (
        (grid["breadth_high"] == candidate_params["breadth_high"])
        & (grid["breadth_mid"] == candidate_params["breadth_mid"])
        & (grid["vol_high"] == candidate_params["vol_high"])
        & (grid["vol_mid"] == candidate_params["vol_mid"])
        & (grid["lag_mid"] == candidate_params["lag_mid"])
    )
    neighborhood = grid[mask].copy()
    neighborhood["is_candidate"] = (
        (neighborhood["base_size"] == candidate_params["base_size"])
        & (neighborhood["mid_size"] == candidate_params["mid_size"])
        & (neighborhood["lag_high"] == candidate_params["lag_high"])
    )
    return neighborhood.sort_values(["risk_score", "total_return"], ascending=False)


def worst_trade_overlap(full_ledger: pd.DataFrame, candidate_ledger: pd.DataFrame) -> pd.DataFrame:
    key_cols = ["trade_date", "symbol"]
    full = full_ledger[key_cols + ["name", "industry", "pnl", "realized_return"]].rename(
        columns={"pnl": "pnl_full", "realized_return": "return_full"}
    )
    candidate = candidate_ledger[key_cols + ["pnl", "realized_return", "size_multiplier"]].rename(
        columns={"pnl": "pnl_candidate", "realized_return": "return_candidate"}
    )
    out = full.merge(candidate, on=key_cols, how="inner")
    out["pnl_delta"] = out["pnl_candidate"] - out["pnl_full"]
    return out.sort_values("pnl_delta").head(20)


def write_report(
    path: Path,
    monthly: pd.DataFrame,
    tail_compare: pd.DataFrame,
    sensitivity: pd.DataFrame,
    worst_overlap: pd.DataFrame,
    full_curve: pd.DataFrame,
    candidate_curve: pd.DataFrame,
) -> None:
    full_final = float(full_curve["equity_curve"].iloc[-1])
    candidate_final = float(candidate_curve["equity_curve"].iloc[-1])
    full_dd = float(full_curve["drawdown"].min())
    candidate_dd = float(candidate_curve["drawdown"].min())
    lines = [
        "# M5 Sizing Robustness Review",
        "",
        "Candidate: `combined_size_v2`; baseline: `full_size`.",
        "",
        "## Overall",
        "",
        f"- full_size final equity: {full_final:.4f}",
        f"- combined_size_v2 final equity: {candidate_final:.4f}",
        f"- equity delta: {candidate_final - full_final:.4f}",
        f"- full_size max drawdown: {full_dd:.2%}",
        f"- combined_size_v2 max drawdown: {candidate_dd:.2%}",
        f"- drawdown improvement: {candidate_dd - full_dd:.2%}",
        "",
        "## Monthly Delta",
        "",
        monthly.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Remove Top Winners",
        "",
        tail_compare.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Parameter Neighborhood",
        "",
        sensitivity.head(30).to_markdown(index=False, floatfmt=".4f") if not sensitivity.empty else "No grid results.",
        "",
        "## Biggest PnL Reductions vs Full Size",
        "",
        worst_overlap.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Verdict",
        "",
    ]
    monthly_return_wins = int(monthly["candidate_better_return"].sum())
    monthly_drawdown_wins = int(monthly["candidate_better_drawdown"].sum())
    tail_positive = bool((tail_compare["remaining_return_delta"] >= 0).all())
    sensitivity_top = bool(not sensitivity.empty and bool(sensitivity.iloc[0].get("is_candidate", False)))
    if monthly_return_wins >= 6 and monthly_drawdown_wins >= 6 and tail_positive and sensitivity_top:
        lines.append("`combined_size_v2` passes this robustness review as a candidate M5 risk switch.")
    else:
        lines.append("`combined_size_v2` remains promising but does not fully pass robustness review yet.")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizing-dir", type=Path, default=DEFAULT_SIZING_DIR)
    parser.add_argument("--grid-path", type=Path, default=DEFAULT_GRID_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--initial-capital", type=float, default=1_000_000.0)
    args = parser.parse_args()

    full_ledger, full_curve, full_monthly = load_policy(args.sizing_dir, "full_size")
    candidate_ledger, candidate_curve, candidate_monthly = load_policy(args.sizing_dir, "combined_size_v2")
    monthly = monthly_compare(full_monthly, candidate_monthly)
    tail_compare = compare_without_top_winners(full_ledger, candidate_ledger, args.initial_capital)
    candidate_params = {
        "base_size": 0.50,
        "mid_size": 0.90,
        "breadth_high": 0.40,
        "breadth_mid": 0.60,
        "vol_high": 0.027,
        "vol_mid": 0.024,
        "lag_high": 0.064,
        "lag_mid": 0.042,
    }
    sensitivity = grid_sensitivity(args.grid_path, candidate_params)
    worst_overlap = worst_trade_overlap(full_ledger, candidate_ledger)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    monthly.to_csv(args.output_dir / "m5_sizing_monthly_delta.csv", index=False, encoding="utf-8-sig")
    tail_compare.to_csv(args.output_dir / "m5_sizing_remove_top_winners.csv", index=False, encoding="utf-8-sig")
    sensitivity.to_csv(args.output_dir / "m5_sizing_parameter_neighborhood.csv", index=False, encoding="utf-8-sig")
    worst_overlap.to_csv(args.output_dir / "m5_sizing_biggest_pnl_reductions.csv", index=False, encoding="utf-8-sig")
    write_report(
        args.output_dir / "m5_sizing_robustness_report.md",
        monthly,
        tail_compare,
        sensitivity,
        worst_overlap,
        full_curve,
        candidate_curve,
    )
    print((args.output_dir / "m5_sizing_robustness_report.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
