#!/usr/bin/env python3
"""Evaluate Top3 rerank results on M3-A experimental candidate pools.

This is an offline experiment. It reads outputs from
08_evaluate_m3a_recall_experiments.py and does not replace the main model or
final signal chain.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_CANDIDATES = Path("skills/a-share-kline-return-modeling/outputs/evaluation/m3_recall_model_predictions.csv")
DEFAULT_FEATURES = Path("skills/a-share-kline-return-modeling/data/clean_stock_features.csv")
DEFAULT_OUTPUT_DIR = Path("skills/a-share-kline-return-modeling/outputs/evaluation")

FEATURE_COLS = [
    "trade_date",
    "symbol",
    "ret_20",
    "amount_ratio_5",
    "industry_strength_score",
    "range_pos_20",
]

RERANK_SCORE_MAP = {
    "candidate_score": "recall_score",
    "ret_20": "ret_20",
    "blend_model_low_overheat": "blend_model_low_overheat",
    "blend_model_amount": "blend_model_amount",
}


def load_candidates(candidates_path: Path, features_path: Path) -> pd.DataFrame:
    candidates = pd.read_csv(candidates_path, encoding="utf-8-sig", parse_dates=["trade_date"])
    candidates["symbol"] = candidates["symbol"].astype(str).str.zfill(6)
    features = pd.read_csv(
        features_path,
        encoding="utf-8-sig",
        usecols=lambda c: c in set(FEATURE_COLS),
        parse_dates=["trade_date"],
    )
    features["symbol"] = features["symbol"].astype(str).str.zfill(6)
    out = candidates.merge(features, on=["trade_date", "symbol"], how="left")
    return add_blend_scores(out)


def add_blend_scores(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    group = ["experiment", "period", "trade_date"]
    for col in ["recall_score", "ret_20", "amount_ratio_5", "industry_strength_score", "range_pos_20"]:
        out[f"{col}_candidate_rank_pct"] = out.groupby(group)[col].rank(pct=True)
    out["blend_model_amount"] = (
        0.50 * out["recall_score_candidate_rank_pct"]
        + 0.30 * out["amount_ratio_5_candidate_rank_pct"]
        + 0.20 * out["industry_strength_score_candidate_rank_pct"]
    )
    out["blend_model_low_overheat"] = (
        0.55 * out["recall_score_candidate_rank_pct"]
        + 0.30 * out["amount_ratio_5_candidate_rank_pct"]
        - 0.15 * out["range_pos_20_candidate_rank_pct"]
    )
    return out


def pick_top3(df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    picks: list[pd.DataFrame] = []
    for strategy, score_col in RERANK_SCORE_MAP.items():
        picked = (
            df.dropna(subset=[score_col])
            .sort_values(
                ["experiment", "period", "trade_date", score_col, "symbol"],
                ascending=[True, True, True, False, True],
            )
            .groupby(["experiment", "period", "trade_date"], group_keys=False)
            .head(top_n)
            .copy()
        )
        picked["rerank_strategy"] = strategy
        picked["topn_rank"] = picked.groupby(["experiment", "period", "trade_date"]).cumcount() + 1
        picks.append(picked)
    return pd.concat(picks, ignore_index=True)


def summarize_daily(picks: pd.DataFrame) -> pd.DataFrame:
    daily = (
        picks.groupby(["experiment", "rerank_strategy", "period", "trade_date"])
        .agg(
            pick_count=("symbol", "count"),
            avg_return=("future_5_return", "mean"),
            hit_top10=("label_top10", "sum"),
            hit_top30=("label_top30", "sum"),
            strong_10pct=("future_5_return", lambda s: (s >= 0.10).mean()),
            best_true_rank=("future_5_return_rank", "min"),
            near_limit_up_ratio=("near_limit_up", "mean"),
            overheat_ratio=("overheat_flag", "mean"),
        )
        .reset_index()
    )
    daily["hit_at_least_one"] = daily["hit_top30"] > 0
    return daily


def summarize_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    return (
        daily.groupby(["experiment", "rerank_strategy", "period"])
        .agg(
            trade_days=("trade_date", "count"),
            avg_return=("avg_return", "mean"),
            avg_hit_top10=("hit_top10", "mean"),
            avg_hit_top30=("hit_top30", "mean"),
            hit_at_least_one=("hit_at_least_one", "mean"),
            avg_strong_10pct=("strong_10pct", "mean"),
            avg_best_true_rank=("best_true_rank", "mean"),
            avg_near_limit_up_ratio=("near_limit_up_ratio", "mean"),
            avg_overheat_ratio=("overheat_ratio", "mean"),
        )
        .reset_index()
    )


def summarize_overall(monthly: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    baseline = monthly[
        (monthly["experiment"] == "raw_rank_pct_regression")
        & (monthly["rerank_strategy"] == "candidate_score")
    ][["period", "avg_return", "avg_hit_top30", "hit_at_least_one"]].rename(
        columns={
            "avg_return": "baseline_return",
            "avg_hit_top30": "baseline_hit_top30",
            "hit_at_least_one": "baseline_hit_at_least_one",
        }
    )
    compare = monthly.merge(baseline, on="period", how="left")
    compare["return_delta_vs_raw_candidate_score"] = compare["avg_return"] - compare["baseline_return"]
    compare["hit30_delta_vs_raw_candidate_score"] = compare["avg_hit_top30"] - compare["baseline_hit_top30"]
    overall = (
        compare.groupby(["experiment", "rerank_strategy"])
        .agg(
            months=("period", "count"),
            avg_return=("avg_return", "mean"),
            avg_hit_top10=("avg_hit_top10", "mean"),
            avg_hit_top30=("avg_hit_top30", "mean"),
            avg_hit_at_least_one=("hit_at_least_one", "mean"),
            positive_month_ratio=("avg_return", lambda s: (s > 0).mean()),
            avg_near_limit_up_ratio=("avg_near_limit_up_ratio", "mean"),
            avg_overheat_ratio=("avg_overheat_ratio", "mean"),
            avg_return_delta_vs_raw=("return_delta_vs_raw_candidate_score", "mean"),
            avg_hit30_delta_vs_raw=("hit30_delta_vs_raw_candidate_score", "mean"),
            months_hit30_gt_raw=("hit30_delta_vs_raw_candidate_score", lambda s: int((s > 0).sum())),
            months_return_gt_raw=("return_delta_vs_raw_candidate_score", lambda s: int((s > 0).sum())),
        )
        .reset_index()
        .sort_values(["avg_hit_top30", "avg_return"], ascending=False)
    )
    return overall, compare


def write_report(path: Path, overall: pd.DataFrame, monthly_compare: pd.DataFrame) -> None:
    lines = [
        "# M3 Candidate Pool Rerank Experiment",
        "",
        "Scope: offline experiment only. No main model or final signal chain is replaced.",
        "",
        "## Overall",
        "",
        overall.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Monthly Compare",
        "",
    ]
    month_cols = [
        "experiment",
        "rerank_strategy",
        "period",
        "avg_return",
        "avg_hit_top30",
        "hit30_delta_vs_raw_candidate_score",
        "return_delta_vs_raw_candidate_score",
        "avg_near_limit_up_ratio",
        "avg_overheat_ratio",
    ]
    lines.append(monthly_compare[month_cols].to_markdown(index=False, floatfmt=".4f"))
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- `candidate_score` uses each candidate pool's own recall score.")
    lines.append("- Other strategies are the currently approved rule reranks used for comparison.")
    lines.append("- This report is not sufficient to replace the main model; it is evidence for review.")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-n", type=int, default=3)
    args = parser.parse_args()

    candidates = load_candidates(args.candidates, args.features)
    picks = pick_top3(candidates, args.top_n)
    daily = summarize_daily(picks)
    monthly = summarize_monthly(daily)
    overall, monthly_compare = summarize_overall(monthly)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    picks.to_csv(args.output_dir / "m3_candidate_rerank_picks.csv", index=False, encoding="utf-8-sig")
    daily.to_csv(args.output_dir / "m3_candidate_rerank_daily.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(args.output_dir / "m3_candidate_rerank_monthly.csv", index=False, encoding="utf-8-sig")
    monthly_compare.to_csv(
        args.output_dir / "m3_candidate_rerank_monthly_compare.csv",
        index=False,
        encoding="utf-8-sig",
    )
    overall.to_csv(args.output_dir / "m3_candidate_rerank_overall.csv", index=False, encoding="utf-8-sig")
    write_report(args.output_dir / "m3_candidate_rerank_report.md", overall, monthly_compare)
    print(overall.to_string(index=False))
    print(f"wrote {args.output_dir / 'm3_candidate_rerank_report.md'}")


if __name__ == "__main__":
    main()
