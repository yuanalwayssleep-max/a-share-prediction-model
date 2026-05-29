#!/usr/bin/env python3
"""Run monthly walk-forward evaluation for V1 stock rank model."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = ROOT / "skills/a-share-kline-return-modeling/scripts"
EVAL_DIR = ROOT / "skills/a-share-kline-return-modeling/outputs/evaluation"
PRED_DIR = ROOT / "skills/a-share-kline-return-modeling/outputs/stock_rank_predictions"


def run_command(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def month_ranges(start: str, end: str) -> list[tuple[str, str, str]]:
    periods = pd.period_range(start=start, end=end, freq="M")
    ranges: list[tuple[str, str, str]] = []
    for period in periods:
        month_start = period.start_time.strftime("%Y-%m-%d")
        month_end = period.end_time.strftime("%Y-%m-%d")
        ranges.append((str(period), month_start, month_end))
    return ranges


def read_strategy_row(path: Path, strategy: str) -> dict[str, object]:
    df = pd.read_csv(path)
    row = df[df["strategy"] == strategy]
    if row.empty:
        raise ValueError(f"Missing strategy={strategy} in {path}")
    return row.iloc[0].to_dict()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-month", default="2025-05")
    parser.add_argument("--end-month", default="2026-04")
    parser.add_argument("--top-n-train", type=int, default=50)
    parser.add_argument("--top-n-eval", type=int, default=3)
    parser.add_argument("--train-window-days", type=int, default=365)
    args = parser.parse_args()

    rows: list[dict[str, object]] = []
    for period, start_date, end_date in month_ranges(args.start_month, args.end_month):
        print(f"\n=== walk-forward {period} ===")
        run_command(
            [
                sys.executable,
                str(SCRIPT_DIR / "01_train_stock_rank_model.py"),
                "--start-date",
                start_date,
                "--end-date",
                end_date,
                "--top-n",
                str(args.top_n_train),
                "--train-window-days",
                str(args.train_window_days),
            ]
        )
        month_pred_dir = PRED_DIR / period
        month_pred_dir.mkdir(parents=True, exist_ok=True)
        pred_with_truth = PRED_DIR / "predictions_with_truth.csv"
        pred_safe = PRED_DIR / "predictions.csv"
        pred_with_truth_month = month_pred_dir / "predictions_with_truth.csv"
        pred_safe_month = month_pred_dir / "predictions.csv"
        pred_with_truth_month.write_bytes(pred_with_truth.read_bytes())
        pred_safe_month.write_bytes(pred_safe.read_bytes())

        month_eval_dir = EVAL_DIR / "walk_forward" / period
        run_command(
            [
                sys.executable,
                str(SCRIPT_DIR / "04_evaluate_top3.py"),
                "--model-predictions-with-truth",
                str(pred_with_truth_month),
                "--top-n",
                str(args.top_n_eval),
                "--output-dir",
                str(month_eval_dir),
            ]
        )
        compare_path = month_eval_dir / "baseline_compare.csv"
        model = read_strategy_row(compare_path, "model_rank")
        random = read_strategy_row(compare_path, "random")
        amount = read_strategy_row(compare_path, "amount_ratio_5")
        ret5 = read_strategy_row(compare_path, "ret_5")
        rows.append(
            {
                "period": period,
                "start_date": start_date,
                "end_date": end_date,
                "trade_days": model["trade_days"],
                "model_avg_return": model["avg_future_5_return"],
                "model_hit_top10": model["avg_hit_top10_count"],
                "model_hit_top30": model["avg_hit_top30_count"],
                "model_hit_at_least_one": model["hit_at_least_one_ratio"],
                "random_avg_return": random["avg_future_5_return"],
                "random_hit_top30": random["avg_hit_top30_count"],
                "amount_avg_return": amount["avg_future_5_return"],
                "amount_hit_top30": amount["avg_hit_top30_count"],
                "ret5_avg_return": ret5["avg_future_5_return"],
                "ret5_hit_top30": ret5["avg_hit_top30_count"],
                "return_vs_random": model["avg_future_5_return"] - random["avg_future_5_return"],
                "return_vs_amount": model["avg_future_5_return"] - amount["avg_future_5_return"],
                "hit30_vs_random": model["avg_hit_top30_count"] - random["avg_hit_top30_count"],
            }
        )

    summary = pd.DataFrame(rows)
    out_path = EVAL_DIR / "walk_forward_summary.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(out_path, index=False, encoding="utf-8-sig")

    md_path = EVAL_DIR / "walk_forward_summary.md"
    lines = ["# Walk-forward Summary", "", summary.to_markdown(index=False), ""]
    lines.append("## Aggregate")
    lines.append("")
    aggregate = {
        "months": len(summary),
        "avg_model_return": summary["model_avg_return"].mean(),
        "avg_model_hit_top30": summary["model_hit_top30"].mean(),
        "win_return_vs_random_ratio": (summary["return_vs_random"] > 0).mean(),
        "win_return_vs_amount_ratio": (summary["return_vs_amount"] > 0).mean(),
        "win_hit30_vs_random_ratio": (summary["hit30_vs_random"] > 0).mean(),
    }
    lines.append("```json")
    lines.append(json.dumps(aggregate, ensure_ascii=False, indent=2))
    lines.append("```")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(summary.to_string(index=False))
    print(f"wrote {out_path}")
    print(f"wrote {md_path}")


if __name__ == "__main__":
    main()
