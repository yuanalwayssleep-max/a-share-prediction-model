#!/usr/bin/env python3
"""Evaluate approved second-stage reranking strategies inside model candidates."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


DEFAULT_PRED_ROOT = Path("skills/a-share-kline-return-modeling/outputs/stock_rank_predictions")
DEFAULT_FEATURES = Path("skills/a-share-kline-return-modeling/data/clean_stock_features.csv")
DEFAULT_OUTPUT_DIR = Path("skills/a-share-kline-return-modeling/outputs/evaluation")


RERANK_FEATURES = [
    "rank_strength_score",
    "rank_secondary_score",
    "amount_ratio_5",
    "ret_5",
    "ret_20",
    "turnover_pct",
    "industry_strength_score",
    "range_pos_20",
]


def load_candidates(
    pred_root: Path,
    features_path: Path,
    start_period: str | None = None,
    end_period: str | None = None,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(pred_root.glob("20??-??/predictions_with_truth.csv")):
        period = path.parent.name
        if start_period and period < start_period:
            continue
        if end_period and period > end_period:
            continue
        df = pd.read_csv(path, encoding="utf-8-sig", parse_dates=["trade_date"])
        df["period"] = period
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No monthly predictions found under {pred_root}")
    pred = pd.concat(frames, ignore_index=True)

    feature_cols = ["trade_date", "symbol"] + [c for c in RERANK_FEATURES if c != "rank_strength_score"]
    features = pd.read_csv(features_path, encoding="utf-8-sig", usecols=lambda c: c in set(feature_cols), parse_dates=["trade_date"])
    out = pred.merge(features, on=["trade_date", "symbol"], how="left", suffixes=("", "_feature"))
    if "industry_strength_score_feature" in out.columns:
        out["industry_strength_score"] = out["industry_strength_score"].fillna(out["industry_strength_score_feature"])
        out = out.drop(columns=["industry_strength_score_feature"])
    return out


def add_rank_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    group = ["period", "trade_date"]
    for col in RERANK_FEATURES:
        if col in out.columns:
            out[f"{col}_candidate_rank_pct"] = out.groupby(group)[col].rank(pct=True)
    out["blend_model_amount"] = (
        0.50 * out["rank_strength_score_candidate_rank_pct"]
        + 0.30 * out["amount_ratio_5_candidate_rank_pct"]
        + 0.20 * out["industry_strength_score_candidate_rank_pct"]
    )
    out["blend_model_low_overheat"] = (
        0.55 * out["rank_strength_score_candidate_rank_pct"]
        + 0.30 * out["amount_ratio_5_candidate_rank_pct"]
        - 0.15 * out["range_pos_20_candidate_rank_pct"]
    )
    return out


def evaluate_strategy(df: pd.DataFrame, score_col: str, strategy: str, top_n: int) -> pd.DataFrame:
    picked = (
        df.dropna(subset=[score_col])
        .sort_values(["period", "trade_date", score_col, "symbol"], ascending=[True, True, False, True])
        .groupby(["period", "trade_date"], group_keys=False)
        .head(top_n)
        .copy()
    )
    picked["strategy"] = strategy
    return picked


def summarize(picks: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = (
        picks.groupby(["strategy", "period", "trade_date"])
        .agg(
            pick_count=("symbol", "count"),
            avg_return=("future_5_return", "mean"),
            hit_top10=("label_top10", "sum"),
            hit_top30=("label_top30", "sum"),
            strong_10pct=("future_5_return", lambda s: (s >= 0.10).mean()),
            best_true_rank=("future_5_return_rank", "min"),
        )
        .reset_index()
    )
    monthly = (
        daily.groupby(["strategy", "period"])
        .agg(
            trade_days=("trade_date", "count"),
            avg_return=("avg_return", "mean"),
            avg_hit_top10=("hit_top10", "mean"),
            avg_hit_top30=("hit_top30", "mean"),
            hit_at_least_one=("hit_top30", lambda s: (s > 0).mean()),
            avg_strong_10pct=("strong_10pct", "mean"),
            avg_best_true_rank=("best_true_rank", "mean"),
        )
        .reset_index()
    )
    return daily, monthly


def overall(monthly: pd.DataFrame) -> pd.DataFrame:
    return (
        monthly.groupby("strategy")
        .agg(
            months=("period", "count"),
            avg_monthly_return=("avg_return", "mean"),
            avg_hit_top10=("avg_hit_top10", "mean"),
            avg_hit_top30=("avg_hit_top30", "mean"),
            avg_hit_at_least_one=("hit_at_least_one", "mean"),
            positive_month_ratio=("avg_return", lambda s: (s > 0).mean()),
        )
        .reset_index()
        .sort_values(["avg_monthly_return", "avg_hit_top30"], ascending=False)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pred-root", type=Path, default=DEFAULT_PRED_ROOT)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--start-period")
    parser.add_argument("--end-period")
    args = parser.parse_args()

    candidates = add_rank_columns(
        load_candidates(
            args.pred_root,
            args.features,
            start_period=args.start_period,
            end_period=args.end_period,
        )
    )
    score_map = {
        # Raw model Top3 baseline. This must remain in every M3 rerank evaluation.
        "model_score": "rank_strength_score",
        # Approved by CR-20260529-001.
        "ret_20": "ret_20",
        "blend_model_amount": "blend_model_amount",
        "blend_model_low_overheat": "blend_model_low_overheat",
    }
    picks = pd.concat(
        [evaluate_strategy(candidates, score_col, strategy, args.top_n) for strategy, score_col in score_map.items()],
        ignore_index=True,
    )
    daily, monthly = summarize(picks)
    summary = overall(monthly)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    candidates.to_csv(args.output_dir / "rerank_candidates.csv", index=False, encoding="utf-8-sig")
    daily.to_csv(args.output_dir / "rerank_daily_summary.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(args.output_dir / "rerank_monthly_summary.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(args.output_dir / "rerank_overall_summary.csv", index=False, encoding="utf-8-sig")
    md = [
        "# Rerank Strategy Summary",
        "",
        "Scope: raw model Top3 baseline plus CR-20260529-001 approved rule reranks only.",
        "",
        summary.to_markdown(index=False),
        "",
    ]
    md.append("## Monthly")
    md.append("")
    md.append(monthly.to_markdown(index=False))
    (args.output_dir / "rerank_strategy_summary.md").write_text("\n".join(md), encoding="utf-8")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
