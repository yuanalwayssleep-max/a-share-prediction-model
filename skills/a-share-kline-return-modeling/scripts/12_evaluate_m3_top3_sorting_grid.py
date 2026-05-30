#!/usr/bin/env python3
"""Evaluate Top3 sorting formulas inside the top50_classifier candidate pool.

Offline experiment only. It searches simple, interpretable score formulas and
industry caps without changing labels, backtest rules, or the main signal chain.
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
    "ret_5",
    "ret_20",
    "amount_ratio_5",
    "amount_ratio_20",
    "turnover_pct",
    "range_pos_20",
    "volatility_5",
    "industry_strength_score",
    "stock_vs_industry_ret_5",
]

WEAK_MONTHS = {"2025-06", "2025-07", "2025-09", "2025-11"}


FORMULAS: dict[str, dict[str, float]] = {
    "score": {"recall_score": 1.00},
    "score_amount": {"recall_score": 0.70, "amount_ratio_5": 0.30},
    "score_industry": {"recall_score": 0.70, "industry_strength_score": 0.30},
    "score_amount_industry": {"recall_score": 0.60, "amount_ratio_5": 0.25, "industry_strength_score": 0.15},
    "score_ret20_amount": {"recall_score": 0.55, "ret_20": 0.25, "amount_ratio_5": 0.20},
    "score_ret5_amount": {"recall_score": 0.55, "ret_5": 0.25, "amount_ratio_5": 0.20},
    "score_amount_low_range": {"recall_score": 0.60, "amount_ratio_5": 0.30, "range_pos_20": -0.10},
    "score_industry_low_range": {"recall_score": 0.65, "industry_strength_score": 0.25, "range_pos_20": -0.10},
    "score_amount_industry_low_range": {
        "recall_score": 0.55,
        "amount_ratio_5": 0.25,
        "industry_strength_score": 0.20,
        "range_pos_20": -0.10,
    },
    "score_vs_industry": {"recall_score": 0.65, "stock_vs_industry_ret_5": 0.20, "industry_strength_score": 0.15},
    "score_penalty_overheat": {"recall_score": 1.00, "overheat_flag": -0.20, "near_limit_up": -0.10},
    "score_amount_penalty_overheat": {
        "recall_score": 0.70,
        "amount_ratio_5": 0.30,
        "overheat_flag": -0.20,
        "near_limit_up": -0.10,
    },
}


def load_candidates(candidates_path: Path, features_path: Path) -> pd.DataFrame:
    candidates = pd.read_csv(candidates_path, encoding="utf-8-sig", parse_dates=["trade_date"])
    candidates = candidates[candidates["experiment"] == "top50_classifier"].copy()
    candidates["symbol"] = candidates["symbol"].astype(str).str.zfill(6)
    features = pd.read_csv(
        features_path,
        encoding="utf-8-sig",
        usecols=lambda c: c in set(FEATURE_COLS),
        parse_dates=["trade_date"],
    )
    features["symbol"] = features["symbol"].astype(str).str.zfill(6)
    out = candidates.merge(features, on=["trade_date", "symbol"], how="left")
    return add_rank_features(out)


def add_rank_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    group = ["period", "trade_date"]
    for col in [
        "recall_score",
        "ret_5",
        "ret_20",
        "amount_ratio_5",
        "amount_ratio_20",
        "turnover_pct",
        "range_pos_20",
        "volatility_5",
        "industry_strength_score",
        "stock_vs_industry_ret_5",
    ]:
        if col in out.columns:
            out[f"{col}_rank_pct"] = out.groupby(group)[col].rank(pct=True)
    out["near_limit_up_rank_pct"] = out["near_limit_up"].fillna(0).astype(float)
    out["overheat_flag_rank_pct"] = out["overheat_flag"].fillna(0).astype(float)
    return out


def add_formula_scores(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for name, weights in FORMULAS.items():
        score = pd.Series(0.0, index=out.index)
        for feature, weight in weights.items():
            rank_col = f"{feature}_rank_pct"
            if rank_col not in out.columns:
                continue
            score = score + weight * out[rank_col].fillna(0.5)
        out[name] = score
    return out


def select_top_n(df: pd.DataFrame, formula: str, top_n: int, max_per_industry: int | None) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for (period, trade_date), group in df.groupby(["period", "trade_date"]):
        sorted_group = group.sort_values([formula, "symbol"], ascending=[False, True])
        picks = []
        industry_counts: dict[str, int] = {}
        for _, row in sorted_group.iterrows():
            industry = str(row.get("industry", ""))
            if max_per_industry is not None and industry_counts.get(industry, 0) >= max_per_industry:
                continue
            picks.append(row)
            industry_counts[industry] = industry_counts.get(industry, 0) + 1
            if len(picks) >= top_n:
                break
        picked = pd.DataFrame(picks)
        picked["formula"] = formula if max_per_industry is None else f"{formula}_max_industry_{max_per_industry}"
        picked["period"] = period
        picked["trade_date"] = trade_date
        picked["topn_rank"] = range(1, len(picked) + 1)
        frames.append(picked)
    return pd.concat(frames, ignore_index=True)


def summarize_daily(picks: pd.DataFrame) -> pd.DataFrame:
    daily = (
        picks.groupby(["formula", "period", "trade_date"])
        .agg(
            pick_count=("symbol", "count"),
            avg_return=("future_5_return", "mean"),
            hit_top10=("label_top10", "sum"),
            hit_top30=("label_top30", "sum"),
            strong_10pct=("future_5_return", lambda s: (s >= 0.10).mean()),
            best_true_rank=("future_5_return_rank", "min"),
            near_limit_up_ratio=("near_limit_up", "mean"),
            overheat_ratio=("overheat_flag", "mean"),
            industry_count=("industry", lambda s: len(set(map(str, s)))),
        )
        .reset_index()
    )
    daily["hit_at_least_one"] = daily["hit_top30"] > 0
    daily["is_weak_month"] = daily["period"].isin(WEAK_MONTHS)
    return daily


def summarize_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    return (
        daily.groupby(["formula", "period"])
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
            avg_industry_count=("industry_count", "mean"),
        )
        .reset_index()
    )


def summarize_overall(monthly: pd.DataFrame) -> pd.DataFrame:
    baseline = monthly[monthly["formula"] == "score"][["period", "avg_return", "avg_hit_top30"]].rename(
        columns={"avg_return": "baseline_return", "avg_hit_top30": "baseline_hit_top30"}
    )
    compare = monthly.merge(baseline, on="period", how="left")
    compare["return_delta_vs_score"] = compare["avg_return"] - compare["baseline_return"]
    compare["hit30_delta_vs_score"] = compare["avg_hit_top30"] - compare["baseline_hit_top30"]
    weak = compare[compare["period"].isin(WEAK_MONTHS)]
    weak_summary = (
        weak.groupby("formula")
        .agg(
            weak_avg_return=("avg_return", "mean"),
            weak_avg_hit_top30=("avg_hit_top30", "mean"),
            weak_return_delta_vs_score=("return_delta_vs_score", "mean"),
            weak_hit30_delta_vs_score=("hit30_delta_vs_score", "mean"),
        )
        .reset_index()
    )
    overall = (
        compare.groupby("formula")
        .agg(
            months=("period", "count"),
            avg_return=("avg_return", "mean"),
            avg_hit_top10=("avg_hit_top10", "mean"),
            avg_hit_top30=("avg_hit_top30", "mean"),
            avg_hit_at_least_one=("hit_at_least_one", "mean"),
            positive_month_ratio=("avg_return", lambda s: (s > 0).mean()),
            avg_near_limit_up_ratio=("avg_near_limit_up_ratio", "mean"),
            avg_overheat_ratio=("avg_overheat_ratio", "mean"),
            avg_industry_count=("avg_industry_count", "mean"),
            avg_return_delta_vs_score=("return_delta_vs_score", "mean"),
            avg_hit30_delta_vs_score=("hit30_delta_vs_score", "mean"),
            months_return_gt_score=("return_delta_vs_score", lambda s: int((s > 0).sum())),
            months_hit30_gt_score=("hit30_delta_vs_score", lambda s: int((s > 0).sum())),
        )
        .reset_index()
        .merge(weak_summary, on="formula", how="left")
        .sort_values(["weak_avg_return", "avg_return", "avg_hit_top30"], ascending=False)
    )
    return overall, compare


def write_report(path: Path, overall: pd.DataFrame, monthly_compare: pd.DataFrame) -> None:
    lines = [
        "# M3 Top3 Sorting Grid",
        "",
        "Scope: top50_classifier candidate pool; offline formula search focused on weak months.",
        "",
        "## Overall",
        "",
        overall.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Monthly Compare",
        "",
    ]
    month_cols = [
        "formula",
        "period",
        "avg_return",
        "avg_hit_top30",
        "return_delta_vs_score",
        "hit30_delta_vs_score",
        "avg_near_limit_up_ratio",
        "avg_overheat_ratio",
    ]
    lines.append(monthly_compare[month_cols].to_markdown(index=False, floatfmt=".4f"))
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- `score` is the top50_classifier candidate_score baseline.")
    lines.append("- Weak months are 2025-06, 2025-07, 2025-09, and 2025-11.")
    lines.append("- This grid is exploratory and does not change labels or trading rules.")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-n", type=int, default=3)
    args = parser.parse_args()

    candidates = add_formula_scores(load_candidates(args.candidates, args.features))
    picks = []
    for formula in FORMULAS:
        picks.append(select_top_n(candidates, formula, args.top_n, None))
        picks.append(select_top_n(candidates, formula, args.top_n, 1))
    picks_df = pd.concat(picks, ignore_index=True)
    daily = summarize_daily(picks_df)
    monthly = summarize_monthly(daily)
    overall, monthly_compare = summarize_overall(monthly)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    picks_df.to_csv(args.output_dir / "m3_top3_sorting_grid_picks.csv", index=False, encoding="utf-8-sig")
    daily.to_csv(args.output_dir / "m3_top3_sorting_grid_daily.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(args.output_dir / "m3_top3_sorting_grid_monthly.csv", index=False, encoding="utf-8-sig")
    monthly_compare.to_csv(args.output_dir / "m3_top3_sorting_grid_monthly_compare.csv", index=False, encoding="utf-8-sig")
    overall.to_csv(args.output_dir / "m3_top3_sorting_grid_overall.csv", index=False, encoding="utf-8-sig")
    write_report(args.output_dir / "m3_top3_sorting_grid_report.md", overall, monthly_compare)
    print(overall.head(20).to_string(index=False))
    print(f"wrote {args.output_dir / 'm3_top3_sorting_grid_report.md'}")


if __name__ == "__main__":
    main()
