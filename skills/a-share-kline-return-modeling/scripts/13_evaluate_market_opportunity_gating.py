#!/usr/bin/env python3
"""Evaluate simple market opportunity gates for M5.

Offline experiment only. Uses T-day known market features and model_rank daily
results to test whether fewer/zero picks on low-opportunity days improves the
signal profile.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


EVAL_DIR = Path("skills/a-share-kline-return-modeling/outputs/evaluation")
MARKET_FEATURES = Path("skills/a-share-kline-return-modeling/data/clean_market_features.csv")

GATE_FEATURES = [
    "market_up_ratio",
    "market_avg_pct_chg",
    "market_strong_5pct_ratio",
    "market_amount_ratio_5",
    "market_10pct_density_ma5_lag1",
    "market_10pct_density_ma10_lag1",
]


def load_model_daily() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted((EVAL_DIR / "walk_forward").glob("20??-??/daily_detail.csv")):
        df = pd.read_csv(path, encoding="utf-8-sig", parse_dates=["trade_date"])
        df = df[df["strategy"] == "model_rank"].copy()
        df["period"] = path.parent.name
        frames.append(df)
    if not frames:
        raise FileNotFoundError("No walk_forward daily details found.")
    return pd.concat(frames, ignore_index=True)


def load_market() -> pd.DataFrame:
    cols = ["trade_date"] + GATE_FEATURES + [
        "future_market_10pct_density",
        "market_top30_avg_return",
        "market_positive_ratio",
    ]
    market = pd.read_csv(
        MARKET_FEATURES,
        encoding="utf-8-sig",
        usecols=lambda c: c in set(cols),
        parse_dates=["trade_date"],
    )
    return market


def add_gate_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for feature in GATE_FEATURES:
        if feature not in out.columns:
            continue
        for q in [0.2, 0.3, 0.4, 0.5, 0.6]:
            threshold = out[feature].quantile(q)
            out[f"{feature}_ge_q{int(q * 100)}"] = out[feature] >= threshold
    out["combo_lag_density_or_breadth"] = (
        out["market_10pct_density_ma5_lag1_ge_q40"].fillna(False)
        | out["market_up_ratio_ge_q40"].fillna(False)
    )
    out["combo_lag_density_and_breadth"] = (
        out["market_10pct_density_ma5_lag1_ge_q30"].fillna(False)
        & out["market_up_ratio_ge_q30"].fillna(False)
    )
    out["combo_amount_and_breadth"] = (
        out["market_amount_ratio_5_ge_q40"].fillna(False)
        & out["market_up_ratio_ge_q40"].fillna(False)
    )
    return out


def evaluate_policy(df: pd.DataFrame, policy: str) -> dict[str, object]:
    if policy == "no_gate":
        active = pd.Series(True, index=df.index)
    else:
        active = df[policy].fillna(False).astype(bool)
    active_df = df[active].copy()
    inactive_df = df[~active].copy()
    active_return = active_df["avg_future_5_return"].mean() if not active_df.empty else 0.0
    # Signal-level capital proxy: skipped days earn 0 instead of opening the daily basket.
    gated_daily_return_proxy = df["avg_future_5_return"].where(active, 0.0)
    return {
        "policy": policy,
        "total_days": len(df),
        "active_days": int(active.sum()),
        "active_ratio": float(active.mean()),
        "avg_return_active_days": float(active_return),
        "avg_return_all_days_with_cash": float(gated_daily_return_proxy.mean()),
        "avg_hit_top30_active_days": float(active_df["hit_top30_count"].mean()) if not active_df.empty else 0.0,
        "hit_at_least_one_active_days": float(active_df["hit_top30_at_least_one"].mean()) if not active_df.empty else 0.0,
        "skipped_days_avg_return": float(inactive_df["avg_future_5_return"].mean()) if not inactive_df.empty else 0.0,
        "skipped_bad_day_ratio": float((inactive_df["avg_future_5_return"] < 0).mean()) if not inactive_df.empty else 0.0,
        "positive_active_month_ratio": float((active_df.groupby("period")["avg_future_5_return"].mean() > 0).mean())
        if not active_df.empty
        else 0.0,
    }


def evaluate_monthly(df: pd.DataFrame, policy: str) -> pd.DataFrame:
    if policy == "no_gate":
        active = pd.Series(True, index=df.index)
    else:
        active = df[policy].fillna(False).astype(bool)
    work = df.copy()
    work["active"] = active
    work["gated_return"] = work["avg_future_5_return"].where(work["active"], 0.0)
    return (
        work.groupby("period")
        .agg(
            total_days=("trade_date", "count"),
            active_days=("active", "sum"),
            active_ratio=("active", "mean"),
            avg_return_all_days_with_cash=("gated_return", "mean"),
            avg_return_active_days=("avg_future_5_return", lambda s: s[work.loc[s.index, "active"]].mean()),
            skipped_days=("active", lambda s: int((~s).sum())),
        )
        .reset_index()
        .assign(policy=policy)
    )


def write_report(path: Path, overall: pd.DataFrame, monthly: pd.DataFrame) -> None:
    lines = [
        "# M5 Market Opportunity Gate Experiment",
        "",
        "Scope: offline gate experiment using current M3 model_rank daily results.",
        "",
        "## Overall",
        "",
        overall.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Monthly",
        "",
        monthly.to_markdown(index=False, floatfmt=".4f"),
        "",
        "## Notes",
        "",
        "- `avg_return_all_days_with_cash` treats skipped days as 0 return.",
        "- Gate features are T-day known or lagged market features from clean_market_features.",
        "- This is a first M5 diagnostic, not a final signal layer.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    daily = load_model_daily().merge(load_market(), on="trade_date", how="left")
    daily = add_gate_columns(daily)
    policy_cols = [
        "no_gate",
        *[c for c in daily.columns if c.endswith(("_ge_q20", "_ge_q30", "_ge_q40", "_ge_q50", "_ge_q60"))],
        "combo_lag_density_or_breadth",
        "combo_lag_density_and_breadth",
        "combo_amount_and_breadth",
    ]
    overall = pd.DataFrame([evaluate_policy(daily, p) for p in policy_cols]).sort_values(
        ["avg_return_all_days_with_cash", "avg_return_active_days"],
        ascending=False,
    )
    monthly = pd.concat([evaluate_monthly(daily, p) for p in policy_cols], ignore_index=True)
    overall.to_csv(EVAL_DIR / "m5_market_gate_overall.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(EVAL_DIR / "m5_market_gate_monthly.csv", index=False, encoding="utf-8-sig")
    write_report(EVAL_DIR / "m5_market_gate_report.md", overall, monthly)
    print(overall.head(20).to_string(index=False))
    print(f"wrote {EVAL_DIR / 'm5_market_gate_report.md'}")


if __name__ == "__main__":
    main()
