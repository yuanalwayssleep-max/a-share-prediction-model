#!/usr/bin/env python3
"""Evaluate lightweight risk controls for promising M3 experimental signals.

Offline experiment only. It does not change the main model or final signal
chain.
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
    "range_pos_20",
    "industry_strength_score",
    "turnover_pct",
]


def load_candidates(candidates_path: Path, features_path: Path, experiment: str) -> pd.DataFrame:
    candidates = pd.read_csv(candidates_path, encoding="utf-8-sig", parse_dates=["trade_date"])
    candidates = candidates[candidates["experiment"] == experiment].copy()
    candidates["symbol"] = candidates["symbol"].astype(str).str.zfill(6)
    features = pd.read_csv(
        features_path,
        encoding="utf-8-sig",
        usecols=lambda c: c in set(FEATURE_COLS),
        parse_dates=["trade_date"],
    )
    features["symbol"] = features["symbol"].astype(str).str.zfill(6)
    return candidates.merge(features, on=["trade_date", "symbol"], how="left")


def apply_policy(df: pd.DataFrame, policy: str) -> pd.DataFrame:
    out = df.copy()
    if policy == "baseline_candidate_score":
        return out
    if policy == "exclude_near_limit":
        return out[out["near_limit_up"].fillna(0).astype(int) == 0]
    if policy == "exclude_overheat":
        return out[out["overheat_flag"].fillna(0).astype(int) == 0]
    if policy == "exclude_near_limit_or_overheat":
        return out[
            (out["near_limit_up"].fillna(0).astype(int) == 0)
            & (out["overheat_flag"].fillna(0).astype(int) == 0)
        ]
    if policy == "range_pos_le_090":
        return out[out["range_pos_20"].fillna(1) <= 0.90]
    if policy == "range_pos_le_085":
        return out[out["range_pos_20"].fillna(1) <= 0.85]
    if policy == "range_pos_le_080":
        return out[out["range_pos_20"].fillna(1) <= 0.80]
    if policy == "exclude_overheat_range_pos_le_090":
        return out[(out["overheat_flag"].fillna(0).astype(int) == 0) & (out["range_pos_20"].fillna(1) <= 0.90)]
    if policy == "exclude_near_limit_range_pos_le_090":
        return out[(out["near_limit_up"].fillna(0).astype(int) == 0) & (out["range_pos_20"].fillna(1) <= 0.90)]
    raise ValueError(f"Unknown policy: {policy}")


def select_top_n(df: pd.DataFrame, policy: str, top_n: int, max_per_industry: int | None = None) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for (_, _, trade_date), group in df.groupby(["experiment", "period", "trade_date"]):
        filtered = apply_policy(group, policy).sort_values(["recall_score", "symbol"], ascending=[False, True])
        picks = []
        industry_counts: dict[str, int] = {}
        for _, row in filtered.iterrows():
            industry = str(row.get("industry", ""))
            if max_per_industry is not None and industry_counts.get(industry, 0) >= max_per_industry:
                continue
            picks.append(row)
            industry_counts[industry] = industry_counts.get(industry, 0) + 1
            if len(picks) >= top_n:
                break
        if picks:
            picked = pd.DataFrame(picks)
            picked["policy"] = policy if max_per_industry is None else f"{policy}_max_industry_{max_per_industry}"
            picked["topn_rank"] = range(1, len(picked) + 1)
            frames.append(picked)
    if not frames:
        raise ValueError(f"No picks generated for policy={policy}")
    return pd.concat(frames, ignore_index=True)


def summarize(picks: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = (
        picks.groupby(["policy", "period", "trade_date"])
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
    monthly = (
        daily.groupby(["policy", "period"])
        .agg(
            trade_days=("trade_date", "count"),
            avg_pick_count=("pick_count", "mean"),
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
    return daily, monthly


def summarize_overall(monthly: pd.DataFrame) -> pd.DataFrame:
    baseline = monthly[monthly["policy"] == "baseline_candidate_score"][
        ["period", "avg_return", "avg_hit_top30"]
    ].rename(columns={"avg_return": "baseline_return", "avg_hit_top30": "baseline_hit_top30"})
    compare = monthly.merge(baseline, on="period", how="left")
    compare["return_delta_vs_baseline"] = compare["avg_return"] - compare["baseline_return"]
    compare["hit30_delta_vs_baseline"] = compare["avg_hit_top30"] - compare["baseline_hit_top30"]
    overall = (
        compare.groupby("policy")
        .agg(
            months=("period", "count"),
            avg_pick_count=("avg_pick_count", "mean"),
            avg_return=("avg_return", "mean"),
            avg_hit_top10=("avg_hit_top10", "mean"),
            avg_hit_top30=("avg_hit_top30", "mean"),
            avg_hit_at_least_one=("hit_at_least_one", "mean"),
            positive_month_ratio=("avg_return", lambda s: (s > 0).mean()),
            avg_near_limit_up_ratio=("avg_near_limit_up_ratio", "mean"),
            avg_overheat_ratio=("avg_overheat_ratio", "mean"),
            avg_industry_count=("avg_industry_count", "mean"),
            avg_return_delta_vs_baseline=("return_delta_vs_baseline", "mean"),
            avg_hit30_delta_vs_baseline=("hit30_delta_vs_baseline", "mean"),
            months_return_gt_baseline=("return_delta_vs_baseline", lambda s: int((s > 0).sum())),
            months_hit30_gt_baseline=("hit30_delta_vs_baseline", lambda s: int((s > 0).sum())),
        )
        .reset_index()
        .sort_values(["avg_return", "avg_hit_top30"], ascending=False)
    )
    return overall, compare


def write_report(path: Path, overall: pd.DataFrame, compare: pd.DataFrame) -> None:
    lines = [
        "# M3 Risk Control Experiment",
        "",
        "Scope: top50_classifier candidate_score offline policy experiment only.",
        "",
        "## Overall",
        "",
        overall.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Monthly",
        "",
    ]
    month_cols = [
        "policy",
        "period",
        "avg_return",
        "avg_hit_top30",
        "avg_near_limit_up_ratio",
        "avg_overheat_ratio",
        "return_delta_vs_baseline",
        "hit30_delta_vs_baseline",
    ]
    lines.append(compare[month_cols].to_markdown(index=False, floatfmt=".4f"))
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- Baseline is top50_classifier candidate_score Top3 without extra filters.")
    lines.append("- These policies are offline experiments; none are in the main signal chain.")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--experiment", default="top50_classifier")
    parser.add_argument("--top-n", type=int, default=3)
    args = parser.parse_args()

    candidates = load_candidates(args.candidates, args.features, args.experiment)
    policies = [
        ("baseline_candidate_score", None),
        ("exclude_near_limit", None),
        ("exclude_overheat", None),
        ("exclude_near_limit_or_overheat", None),
        ("range_pos_le_090", None),
        ("range_pos_le_085", None),
        ("range_pos_le_080", None),
        ("exclude_overheat_range_pos_le_090", None),
        ("exclude_near_limit_range_pos_le_090", None),
        ("baseline_candidate_score", 1),
        ("exclude_near_limit_or_overheat", 1),
        ("range_pos_le_090", 1),
    ]
    picks = pd.concat(
        [select_top_n(candidates, policy, args.top_n, max_per_industry=max_industry) for policy, max_industry in policies],
        ignore_index=True,
    )
    daily, monthly = summarize(picks)
    overall, compare = summarize_overall(monthly)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    picks.to_csv(args.output_dir / "m3_risk_control_picks.csv", index=False, encoding="utf-8-sig")
    daily.to_csv(args.output_dir / "m3_risk_control_daily.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(args.output_dir / "m3_risk_control_monthly.csv", index=False, encoding="utf-8-sig")
    compare.to_csv(args.output_dir / "m3_risk_control_monthly_compare.csv", index=False, encoding="utf-8-sig")
    overall.to_csv(args.output_dir / "m3_risk_control_overall.csv", index=False, encoding="utf-8-sig")
    write_report(args.output_dir / "m3_risk_control_report.md", overall, compare)
    print(overall.to_string(index=False))
    print(f"wrote {args.output_dir / 'm3_risk_control_report.md'}")


if __name__ == "__main__":
    main()
