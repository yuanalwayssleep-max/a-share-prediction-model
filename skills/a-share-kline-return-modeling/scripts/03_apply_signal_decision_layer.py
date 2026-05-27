#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_STOCK_FEATURE_FILE = SKILL_DIR / "data" / "个股k线特征数据.csv"
DEFAULT_OUTPUT_DIR = SKILL_DIR / "outputs" / "final_signals"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="最终信号层：输出 Top3 / Top2 / Top1 / 不出手")
    parser.add_argument("--stock-prediction", required=True, help="个股Top股票池预测CSV")
    parser.add_argument("--market-prediction", required=True, help="市场风险预测CSV")
    parser.add_argument("--stock-feature-file", default=str(DEFAULT_STOCK_FEATURE_FILE), help="个股k线特征数据.csv路径")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="输出目录")
    parser.add_argument("--max-top-n", type=int, default=3, help="最多输出几只股票，默认3")
    parser.add_argument("--min-top1-score", type=float, default=0.62, help="Top1最低信号分，低于则不出手")
    parser.add_argument("--min-top2-score", type=float, default=0.68, help="Top2最低信号分")
    parser.add_argument("--min-top3-score", type=float, default=0.65, help="Top3最低信号分")
    return parser.parse_args()


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path, encoding="utf-8-sig", dtype={"symbol": str})


def normalize_symbol(series: pd.Series) -> pd.Series:
    return series.astype(str).str.extract(r"(\d{1,6})", expand=False).str.zfill(6)


def date_range_tag(path: Path) -> str:
    match = re.search(r"(\d{8})_(\d{8})", path.name)
    if match:
        model_match = re.search(r"(LightGBM)", path.name)
        model_prefix = f"{model_match.group(1)}_" if model_match else ""
        return f"{model_prefix}{match.group(1)}_{match.group(2)}"
    return "unknown_range"


def output_name(range_tag: str) -> str:
    return f"最终出手信号_{range_tag}_系统日期{date.today():%Y%m%d}.csv"


def build_market_daily(market: pd.DataFrame) -> pd.DataFrame:
    market = market.copy()
    market["trade_date"] = pd.to_datetime(market["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    for col in ["predicted_up_prob", "predicted_down_prob"]:
        market[col] = pd.to_numeric(market[col], errors="coerce")
    if "market_regime" not in market.columns:
        market["market_regime"] = market.get("market_risk_level", "中性")
    market["is_high_risk"] = market["market_risk_level"].eq("高风险").astype(int)
    if "is_high_position_reversal_risk" not in market.columns:
        market["is_high_position_reversal_risk"] = 0
    if "is_exhausted_rebound_risk" not in market.columns:
        market["is_exhausted_rebound_risk"] = 0
    for regime in ["弱势延续", "超跌反弹", "高位回落", "低风险", "中性"]:
        market[f"is_{regime}"] = market["market_regime"].eq(regime).astype(int)
    out = (
        market.groupby("trade_date", as_index=False)
        .agg(
            market_index_count=("index_name", "nunique"),
            market_avg_up_prob=("predicted_up_prob", "mean"),
            market_avg_down_prob=("predicted_down_prob", "mean"),
            market_high_risk_count=("is_high_risk", "sum"),
            weak_trend_count=("is_弱势延续", "sum"),
            rebound_count=("is_超跌反弹", "sum"),
            pullback_count=("is_高位回落", "sum"),
            low_risk_count=("is_低风险", "sum"),
            neutral_count=("is_中性", "sum"),
            high_position_reversal_risk_count=("is_high_position_reversal_risk", "sum"),
            exhausted_rebound_risk_count=("is_exhausted_rebound_risk", "sum"),
        )
    )
    out["aggregate_market_regime"] = out.apply(classify_market_regime, axis=1)
    out["aggregate_market_risk_level"] = out.apply(classify_market_risk, axis=1)
    return out


def classify_market_regime(row: pd.Series) -> str:
    if row["weak_trend_count"] >= 2:
        return "弱势延续"
    if row["pullback_count"] >= 2:
        return "高位回落"
    if row["rebound_count"] >= 2:
        return "超跌反弹"
    if row["low_risk_count"] >= 2:
        return "低风险"
    return "中性"


def classify_market_risk(row: pd.Series) -> str:
    if row["market_high_risk_count"] >= 4 or row["aggregate_market_regime"] in {"弱势延续", "高位回落"}:
        return "高风险"
    if row["market_high_risk_count"] >= 2 or row["market_avg_down_prob"] >= 0.55:
        return "中风险"
    return "低风险"


def enrich_with_feature_percentiles(stock: pd.DataFrame, feature: pd.DataFrame) -> pd.DataFrame:
    stock = stock.copy()
    stock["trade_date"] = pd.to_datetime(stock["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    stock["symbol"] = normalize_symbol(stock["symbol"])
    feature = feature.copy()
    feature["trade_date"] = pd.to_datetime(feature["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    feature["symbol"] = normalize_symbol(feature["symbol"])

    enrich_cols = [
        "trade_date",
        "symbol",
        "turnover_pct",
        "ret_5",
        "ret_20",
        "volatility_5",
        "range_pos_20",
        "market_up_ratio",
        "market_avg_pct_chg",
        "industry_up_ratio",
        "industry_avg_pct_chg",
        "is_pre_holiday_3",
        "is_post_holiday_3",
        "pre_holiday_tday",
        "post_holiday_tday",
        "holiday_gap_days",
    ]
    feature = feature[[col for col in enrich_cols if col in feature.columns]].copy()
    for col in ["turnover_pct", "ret_5", "ret_20", "volatility_5", "range_pos_20"]:
        if col in feature.columns:
            feature[f"{col}_pctile"] = feature.groupby("trade_date")[col].rank(method="average", pct=True)
    return stock.merge(feature, on=["trade_date", "symbol"], how="left", suffixes=("", "_feature"))


def candidate_flags(day: pd.DataFrame) -> pd.DataFrame:
    day = day.copy()
    strong_momentum = (day["ret_5_pctile"] >= 0.9) | (day["ret_20_pctile"] >= 0.9)
    high_position = day["range_pos_20"] >= 0.8
    high_turnover = day["turnover_pct_pctile"] >= 0.9
    high_volatility = day["volatility_5_pctile"] >= 0.9
    industry_support = (
        (day["industry_up_ratio"] >= 0.8)
        & (day["industry_avg_pct_chg"] >= day["market_avg_pct_chg"])
    )
    weak_industry = (
        (day["industry_up_ratio"] < 0.35)
        & (day["industry_avg_pct_chg"] < 0)
        & (day["pct_chg"] <= 0)
    )
    volatility_with_industry_drag = (
        (day["volatility_5_pctile"] >= 0.95)
        & (day["industry_avg_pct_chg"] < 0)
        & ~industry_support
    )
    medium_hot_short_broken = (
        (day["turnover_pct_pctile"] >= 0.9)
        & (day["volatility_5_pctile"] >= 0.9)
        & (day["ret_20_pctile"] >= 0.9)
        & (day["ret_5_pctile"] <= 0.2)
        & (day["market_avg_pct_chg"] < 0)
        & (day["industry_avg_pct_chg"] < 0)
    )
    high_risk_intraday_break = (
        day.get("aggregate_market_risk_level", pd.Series(index=day.index, dtype=object)).eq("高风险")
        & (day["pct_chg"] <= -5)
        & (day["turnover_pct_pctile"] >= 0.9)
        & (day["ret_5_pctile"] >= 0.9)
        & (day["volatility_5_pctile"] >= 0.9)
    )
    high_risk_limit_up_chase = (
        day.get("aggregate_market_risk_level", pd.Series(index=day.index, dtype=object)).eq("高风险")
        & (day["pct_chg"] >= 9.8)
        & (day["range_pos_20"] >= 0.9)
    )
    breadth_divergence_chase = (
        (day["market_up_ratio"] < 0.35)
        & (day["market_avg_pct_chg"] < 0)
        & (day["pct_chg"] >= 8)
        & (day["ret_5_pctile"] >= 0.95)
        & (day["range_pos_20_pctile"] >= 0.9)
    )
    medium_risk_crowded_momentum = (
        day.get("aggregate_market_risk_level", pd.Series(index=day.index, dtype=object)).isin(["中风险", "高风险"])
        & (day["turnover_pct_pctile"] >= 0.95)
        & (day["ret_5_pctile"] >= 0.95)
        & (day["ret_20_pctile"] >= 0.95)
        & (day["range_pos_20"] >= 0.85)
    )
    medium_risk_late_trend = (
        day.get("aggregate_market_risk_level", pd.Series(index=day.index, dtype=object)).eq("中风险")
        & (day["ret_20_pctile"] >= 0.98)
        & (day["ret_5_pctile"] < 0.85)
        & (day["range_pos_20"] >= 0.9)
    )
    crowded_intraday_break = (
        (day["pct_chg"] <= -5)
        & (day["turnover_pct_pctile"] >= 0.95)
        & (day["ret_20_pctile"] >= 0.95)
        & (day["volatility_5_pctile"] >= 0.9)
    )
    late_high_position_weakening = (
        (day["ret_20_pctile"] >= 0.95)
        & (day["range_pos_20_pctile"] >= 0.90)
        & (day["ret_5_pctile"].between(0.75, 0.90))
        & (day["volatility_5_pctile"] >= 0.75)
        & (day["industry_avg_pct_chg"] < 2.0)
    )
    extreme_momentum_extension = (
        (day["ret_5_pctile"] >= 0.98)
        & (day["ret_20_pctile"] >= 0.98)
        & (day["range_pos_20_pctile"] >= 0.98)
        & (day["market_avg_pct_chg"] < 2.0)
    )
    extreme_weak_market_extension = (
        (day["market_up_ratio"] < 0.30)
        & (day["market_avg_pct_chg"] < -1.0)
        & (day["ret_5_pctile"] >= 0.95)
        & (day["ret_20_pctile"] >= 0.90)
        & (day["range_pos_20_pctile"] >= 0.90)
    )
    rebound_crowded_chase = (
        day.get("aggregate_market_regime", pd.Series(index=day.index, dtype=object)).eq("超跌反弹")
        & (day["ret_5_pctile"] >= 0.95)
        & (day["turnover_pct_pctile"] >= 0.95)
        & (day["range_pos_20_pctile"] >= 0.90)
    )
    rebound_limit_up_volatility = (
        day.get("aggregate_market_regime", pd.Series(index=day.index, dtype=object)).eq("超跌反弹")
        & (day["pct_chg"] >= 9.8)
        & (day["volatility_5_pctile"] >= 0.95)
        & (day["ret_5_pctile"] >= 0.85)
    )
    weak_breadth_sideways = (
        (day["market_up_ratio"] < 0.40)
        & (day["market_avg_pct_chg"].abs() < 0.20)
        & (day["industry_up_ratio"] <= 0.45)
    )
    high_risk_pullback_short_weak = (
        day.get("aggregate_market_risk_level", pd.Series(index=day.index, dtype=object)).eq("高风险")
        & day.get("aggregate_market_regime", pd.Series(index=day.index, dtype=object)).eq("高位回落")
        & (day["ret_5_pctile"] < 0.10)
        & (day["ret_20_pctile"] >= 0.90)
    )
    high_risk_pullback_crowded = (
        day.get("aggregate_market_risk_level", pd.Series(index=day.index, dtype=object)).eq("高风险")
        & day.get("aggregate_market_regime", pd.Series(index=day.index, dtype=object)).eq("高位回落")
        & (day["ret_5_pctile"] >= 0.95)
        & (day["range_pos_20_pctile"] >= 0.85)
        & (day["volatility_5_pctile"] >= 0.90)
    )
    trend_break_candidate = (
        (day["ret_20_pctile"] >= 0.90)
        & (day["ret_5_pctile"] < 0.20)
    )
    weak_market_low_position_candidate = (
        (day["market_up_ratio"] < 0.55)
        & (day["market_avg_pct_chg"] < 0.50)
        & (day["range_pos_20_pctile"] < 0.30)
        & (day["top_quantile_signal_score"] < 0.70)
    )
    high_risk_tail_chase_candidate = (
        day.get("aggregate_market_risk_level", pd.Series(index=day.index, dtype=object)).eq("高风险")
        & (day["market_high_risk_count"] >= 4)
        & (day["rank_by_top_quantile_prob"] >= 3)
        & (day["pct_chg"] >= 5)
        & (day["range_pos_20_pctile"] >= 0.85)
        & (day["ret_5_pctile"] >= 0.95)
    )
    weak_market_weak_industry_down_candidate = (
        (day["market_up_ratio"] < 0.45)
        & (day["market_avg_pct_chg"] < 0)
        & (day["industry_up_ratio"] < 0.25)
        & (day["pct_chg"] < 0)
    )
    backup_low_elastic_candidate = (
        (day["rank_by_top_quantile_prob"] > 1)
        & day["top_quantile_signal_score"].between(0.70, 0.705)
        & (day["market_up_ratio"] < 0.58)
        & (day["range_pos_20_pctile"] > 0.70)
    )
    low_turnover_spike_fade_candidate = (
        (day["rank_by_top_quantile_prob"] > 1)
        & (day["top_quantile_signal_score"] < 0.70)
        & (day["ret_5_pctile"] < 0.75)
        & (day["pct_chg"] > 5)
        & (day["turnover_pct_pctile"] < 0.40)
    )
    sharp_drop_rebound_candidate = (
        (day["pct_chg"] < -4)
        & ~(
            day.get("aggregate_market_risk_level", pd.Series(index=day.index, dtype=object)).eq("低风险")
            & (day["market_up_ratio"] >= 0.55)
            & (day["industry_up_ratio"] >= 0.65)
            & (day["industry_avg_pct_chg"] >= 0)
        )
    )
    day["is_overheat_candidate"] = ((high_turnover | high_volatility) & strong_momentum & high_position & ~industry_support).astype(int)
    day["is_weak_industry_candidate"] = weak_industry.astype(int)
    day["is_volatility_industry_drag_candidate"] = volatility_with_industry_drag.astype(int)
    day["is_medium_hot_short_broken_candidate"] = medium_hot_short_broken.astype(int)
    day["is_high_risk_intraday_break_candidate"] = high_risk_intraday_break.astype(int)
    day["is_high_risk_limit_up_chase_candidate"] = high_risk_limit_up_chase.astype(int)
    day["is_breadth_divergence_chase_candidate"] = breadth_divergence_chase.astype(int)
    day["is_medium_risk_crowded_momentum_candidate"] = medium_risk_crowded_momentum.astype(int)
    day["is_medium_risk_late_trend_candidate"] = medium_risk_late_trend.astype(int)
    day["is_crowded_intraday_break_candidate"] = crowded_intraday_break.astype(int)
    day["is_late_high_position_weakening_candidate"] = late_high_position_weakening.astype(int)
    day["is_extreme_momentum_extension_candidate"] = extreme_momentum_extension.astype(int)
    day["is_extreme_weak_market_extension_candidate"] = extreme_weak_market_extension.astype(int)
    day["is_rebound_crowded_chase_candidate"] = rebound_crowded_chase.astype(int)
    day["is_rebound_limit_up_volatility_candidate"] = rebound_limit_up_volatility.astype(int)
    day["is_weak_breadth_sideways_candidate"] = weak_breadth_sideways.astype(int)
    day["is_high_risk_pullback_short_weak_candidate"] = high_risk_pullback_short_weak.astype(int)
    day["is_high_risk_pullback_crowded_candidate"] = high_risk_pullback_crowded.astype(int)
    day["is_trend_break_candidate"] = trend_break_candidate.astype(int)
    day["is_weak_market_low_position_candidate"] = weak_market_low_position_candidate.astype(int)
    day["is_high_risk_tail_chase_candidate"] = high_risk_tail_chase_candidate.astype(int)
    day["is_weak_market_weak_industry_down_candidate"] = weak_market_weak_industry_down_candidate.astype(int)
    day["is_backup_low_elastic_candidate"] = backup_low_elastic_candidate.astype(int)
    day["is_low_turnover_spike_fade_candidate"] = low_turnover_spike_fade_candidate.astype(int)
    day["is_sharp_drop_rebound_candidate"] = sharp_drop_rebound_candidate.astype(int)
    day["is_fragile_candidate"] = (
        day["is_overheat_candidate"].eq(1)
        | day["is_weak_industry_candidate"].eq(1)
        | day["is_volatility_industry_drag_candidate"].eq(1)
        | day["is_medium_hot_short_broken_candidate"].eq(1)
        | day["is_high_risk_intraday_break_candidate"].eq(1)
        | day["is_high_risk_limit_up_chase_candidate"].eq(1)
        | day["is_breadth_divergence_chase_candidate"].eq(1)
        | day["is_medium_risk_crowded_momentum_candidate"].eq(1)
        | day["is_medium_risk_late_trend_candidate"].eq(1)
        | day["is_crowded_intraday_break_candidate"].eq(1)
        | day["is_late_high_position_weakening_candidate"].eq(1)
        | day["is_extreme_momentum_extension_candidate"].eq(1)
        | day["is_extreme_weak_market_extension_candidate"].eq(1)
        | day["is_rebound_crowded_chase_candidate"].eq(1)
        | day["is_rebound_limit_up_volatility_candidate"].eq(1)
        | day["is_weak_breadth_sideways_candidate"].eq(1)
        | day["is_high_risk_pullback_short_weak_candidate"].eq(1)
        | day["is_high_risk_pullback_crowded_candidate"].eq(1)
        | day["is_trend_break_candidate"].eq(1)
        | day["is_weak_market_low_position_candidate"].eq(1)
        | day["is_high_risk_tail_chase_candidate"].eq(1)
        | day["is_weak_market_weak_industry_down_candidate"].eq(1)
        | day["is_backup_low_elastic_candidate"].eq(1)
        | day["is_low_turnover_spike_fade_candidate"].eq(1)
        | day["is_sharp_drop_rebound_candidate"].eq(1)
    ).astype(int)
    return day


def decide_action(day: pd.DataFrame, args: argparse.Namespace) -> tuple[str, int, str]:
    top = day.sort_values("rank_by_top_quantile_prob").head(args.max_top_n).copy()
    scores = top["top_quantile_signal_score"].tolist()
    if not scores or scores[0] < args.min_top1_score:
        return "不出手", 0, "Top1分数不足"

    market_up_ratio = float(top["market_up_ratio"].iloc[0]) if "market_up_ratio" in top else np.nan
    market_avg_pct_chg = float(top["market_avg_pct_chg"].iloc[0]) if "market_avg_pct_chg" in top else np.nan
    market_avg_up_prob = float(top["market_avg_up_prob"].iloc[0]) if "market_avg_up_prob" in top else np.nan
    market_regime = top["aggregate_market_regime"].iloc[0]
    market_risk_level = top["aggregate_market_risk_level"].iloc[0]
    market_fragile = (
        market_regime == "弱势延续"
        or (market_regime == "高位回落" and pd.notna(market_up_ratio) and market_up_ratio < 0.35)
        or (pd.notna(market_up_ratio) and market_up_ratio < 0.30)
        or (pd.notna(market_avg_pct_chg) and market_avg_pct_chg < -1.0)
    )
    fragile_count = int(top["is_fragile_candidate"].sum())
    weak_industry_count = int(top["is_weak_industry_candidate"].sum())
    eligible = top.loc[top["is_fragile_candidate"].eq(0)].copy()
    is_pre_holiday = int(top.get("is_pre_holiday_3", pd.Series([0])).iloc[0] or 0) == 1
    is_post_holiday = int(top.get("is_post_holiday_3", pd.Series([0])).iloc[0] or 0) == 1
    holiday_gap_days = float(top.get("holiday_gap_days", pd.Series([0])).iloc[0] or 0)

    if eligible.empty:
        return "不出手", 0, "Top候选全部脆弱"
    if is_post_holiday and holiday_gap_days >= 7 and pd.notna(market_up_ratio) and market_up_ratio < 0.65:
        return "不出手", 0, "长假节后市场宽度不足"
    if is_pre_holiday and top["aggregate_market_risk_level"].iloc[0] == "高风险" and market_regime == "超跌反弹":
        return "不出手", 0, "节前高风险超跌反弹不追"
    eligible_scores = eligible["top_quantile_signal_score"].tolist()
    if (
        market_risk_level == "高风险"
        and market_regime == "高位回落"
        and int(top["high_position_reversal_risk_count"].iloc[0]) >= 5
    ):
        return "不出手", 0, "全市场高位回落风险"
    if (
        market_risk_level == "高风险"
        and market_regime == "超跌反弹"
        and int(top["exhausted_rebound_risk_count"].iloc[0]) >= 6
    ):
        return "不出手", 0, "全市场超跌反弹衰竭风险"
    if (
        market_risk_level == "高风险"
        and market_regime == "高位回落"
        and pd.notna(market_up_ratio)
        and market_up_ratio < 0.60
    ):
        return "不出手", 0, "高风险高位回落且市场宽度不足"
    if market_risk_level == "高风险" and market_regime == "超跌反弹":
        return "Top1", 1, "高风险超跌反弹，只保留最强Top1"
    if (
        market_risk_level == "中风险"
        and float(top["market_avg_down_prob"].iloc[0]) >= 0.58
        and pd.notna(market_avg_pct_chg)
        and market_avg_pct_chg < 0
    ):
        return "不出手", 0, "中风险且市场下跌概率偏高"
    if (
        market_risk_level == "中风险"
        and pd.notna(market_up_ratio)
        and pd.notna(market_avg_pct_chg)
        and market_up_ratio < 0.50
        and market_avg_pct_chg < 0.50
    ):
        return "不出手", 0, "中风险且市场宽度不足"
    if (
        int(top["anchor_stock_count"].iloc[0]) < 215
        and int(top["market_high_risk_count"].iloc[0]) >= 2
        and pd.notna(market_avg_pct_chg)
        and market_avg_pct_chg > 0
    ):
        return "不出手", 0, "低覆盖股票池下高风险假强反弹"
    if (
        is_post_holiday
        and pd.notna(market_up_ratio)
        and pd.notna(market_avg_pct_chg)
        and market_up_ratio >= 0.70
        and market_avg_pct_chg >= 1.0
        and len(eligible_scores) >= 2
        and eligible_scores[1] >= 0.63
    ):
        return "Top2", min(2, args.max_top_n), "节后强修复允许Top2"
    if fragile_count >= 2 and market_fragile:
        return "不出手", 0, "市场脆弱且候选股风险过多"
    if weak_industry_count >= 2:
        return "不出手", 0, "候选股行业弱势过多"
    if market_fragile:
        return "Top1", 1, "市场风险偏高，只保留Top1"
    if market_risk_level == "高风险":
        return "Top1", 1, "高风险市场，只保留最强合格Top1"
    if pd.notna(market_avg_up_prob) and market_avg_up_prob < 0.45:
        return "Top1", 1, "市场上涨概率不足，不放Top2"

    if len(eligible_scores) >= 3 and eligible_scores[2] >= args.min_top3_score:
        return "Top3", min(3, args.max_top_n), "合格候选允许Top3"
    if len(eligible_scores) >= 2 and eligible_scores[1] >= args.min_top2_score:
        return "Top2", min(2, args.max_top_n), "合格候选Top2分数达标"
    if len(eligible_scores) >= 2 and scores[0] - scores[min(len(scores), 3) - 1] <= 0.03:
        return "Top2", min(2, args.max_top_n), "Top分数接近，分散到Top2"
    return "Top1", 1, "只保留Top1"


def build_signals(stock: pd.DataFrame, market_daily: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    out = stock.merge(market_daily, on="trade_date", how="left")
    if out["aggregate_market_risk_level"].isna().any():
        missing = sorted(out.loc[out["aggregate_market_risk_level"].isna(), "trade_date"].dropna().unique())
        raise RuntimeError(f"市场预测缺少这些日期: {missing[:10]}")

    frames: list[pd.DataFrame] = []
    for trade_date, day in out.groupby("trade_date", sort=True):
        day = candidate_flags(day)
        action, signal_count, reason = decide_action(day, args)
        day = day.sort_values("rank_by_top_quantile_prob").copy()
        day["signal_eligible_rank"] = np.nan
        eligible_index = day.loc[day["is_fragile_candidate"].eq(0)].index
        day.loc[eligible_index, "signal_eligible_rank"] = np.arange(1, len(eligible_index) + 1)
        day["signal_action"] = action
        day["signal_count"] = signal_count
        day["signal_reason"] = reason
        day["final_signal_rank"] = day["rank_by_top_quantile_prob"]
        day["is_final_signal"] = (
            day["signal_eligible_rank"].notna()
            & (day["signal_eligible_rank"] <= signal_count)
        ).astype(int)
        frames.append(day)
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    args = parse_args()
    stock_path = Path(args.stock_prediction).resolve()
    market_path = Path(args.market_prediction).resolve()
    feature_path = Path(args.stock_feature_file).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    stock = read_csv(stock_path)
    market = read_csv(market_path)
    feature = read_csv(feature_path)

    if "top_quantile_signal_score" not in stock.columns:
        if "predicted_top_quantile_prob" in stock.columns:
            stock["top_quantile_signal_score"] = pd.to_numeric(stock["predicted_top_quantile_prob"], errors="coerce")
        else:
            raise RuntimeError("个股预测表缺少 top_quantile_signal_score 或 predicted_top_quantile_prob")

    stock = enrich_with_feature_percentiles(stock, feature)
    market_daily = build_market_daily(market)
    result = build_signals(stock, market_daily, args)

    range_tag = date_range_tag(stock_path)
    output_path = output_dir / output_name(range_tag)
    result.to_csv(output_path, index=False, encoding="utf-8-sig")

    final = result[result["is_final_signal"].eq(1)].copy()
    if final.empty:
        print("最终信号: 全部不出手")
    else:
        known = final.loc[final["future_5_return"].notna()].copy() if "future_5_return" in final.columns else final.iloc[0:0].copy()
        avg_return = known["future_5_return"].mean() if not known.empty else np.nan
        up_rate = (known["future_5_return"] > 0).mean() if not known.empty else np.nan
        print(
            f"最终信号: rows={len(final)}, dates={final['trade_date'].nunique()}, "
            f"verified_rows={len(known)}, verified_up_rate={up_rate:.4f}, verified_avg_return={avg_return:.4f}"
        )
    print(f"输出文件: {output_path}")


if __name__ == "__main__":
    main()
