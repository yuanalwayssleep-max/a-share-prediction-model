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
    parser = argparse.ArgumentParser(description="最终信号层：市场纠正后判断每日是否出手")
    parser.add_argument("--stock-prediction", required=True, help="个股5日方向预测CSV")
    parser.add_argument("--market-prediction", required=True, help="市场风险预测CSV")
    parser.add_argument("--industry-prediction", default="", help="行业风险预测CSV；可选，提供后用于第二阶段行业风险矫正")
    parser.add_argument("--stock-loss-risk-prediction", default="", help="个股5日亏损风险预测CSV；可选，提供后用于过滤5日亏损风险")
    parser.add_argument("--stock-feature-file", default=str(DEFAULT_STOCK_FEATURE_FILE), help="个股k线特征数据.csv路径")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="输出目录")
    parser.add_argument("--max-top-n", type=int, default=3, help="最多输出几只股票，默认3")
    parser.add_argument("--max-loss05-risk", type=float, default=0.35, help="未来5日亏损超过5%的最大允许概率")
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


def build_industry_daily(industry: pd.DataFrame) -> pd.DataFrame:
    industry = industry.copy()
    industry["trade_date"] = pd.to_datetime(industry["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    rename = {
        "industry_index_name": "industry",
        "industry_index_code": "industry_risk_index_code",
        "industry_index_level": "industry_risk_index_level",
    }
    industry = industry.rename(columns=rename)
    for col in ["predicted_industry_up_prob", "predicted_industry_down_prob", "industry_index_ret_5", "industry_index_ret_20"]:
        if col in industry.columns:
            industry[col] = pd.to_numeric(industry[col], errors="coerce")
    keep_cols = [
        "trade_date",
        "industry",
        "industry_risk_index_code",
        "industry_risk_index_level",
        "predicted_industry_up_prob",
        "predicted_industry_down_prob",
        "predicted_industry_direction",
        "industry_risk_level",
        "industry_regime",
        "industry_index_ret_5",
        "industry_index_ret_20",
        "industry_index_range_pos_20",
        "industry_index_ret_5_xrank",
    ]
    industry = industry[[col for col in keep_cols if col in industry.columns]].copy()
    industry = industry.dropna(subset=["trade_date", "industry"]).drop_duplicates(["trade_date", "industry"], keep="last")
    return industry


def normalize_stock_signal_columns(stock: pd.DataFrame) -> pd.DataFrame:
    stock = stock.copy()
    if "final_return_signal_score" in stock.columns:
        stock["signal_score"] = pd.to_numeric(stock["final_return_signal_score"], errors="coerce")
        if "rank_by_final_return_signal_score" in stock.columns:
            stock["signal_rank"] = pd.to_numeric(stock["rank_by_final_return_signal_score"], errors="coerce")
        else:
            stock["signal_rank"] = stock.groupby("trade_date")["signal_score"].rank(method="first", ascending=False)
        stock["signal_source"] = "final_return_signal_score"
        return stock

    if "predicted_return_threshold_prob" in stock.columns:
        stock["signal_score"] = pd.to_numeric(stock["predicted_return_threshold_prob"], errors="coerce")
        if "rank_by_return_threshold_prob" in stock.columns:
            stock["signal_rank"] = pd.to_numeric(stock["rank_by_return_threshold_prob"], errors="coerce")
        else:
            stock["signal_rank"] = stock.groupby("trade_date")["signal_score"].rank(method="first", ascending=False)
        stock["signal_source"] = "predicted_return_threshold_prob"
        return stock

    if "predicted_up_prob" in stock.columns:
        stock["signal_score"] = pd.to_numeric(stock["predicted_up_prob"], errors="coerce")
        if "rank_by_up_prob" in stock.columns:
            stock["signal_rank"] = pd.to_numeric(stock["rank_by_up_prob"], errors="coerce")
        else:
            stock["signal_rank"] = stock.groupby("trade_date")["signal_score"].rank(method="first", ascending=False)
        stock["signal_source"] = "direction_up_prob"
        return stock

    if "top_quantile_signal_score" in stock.columns:
        stock["signal_score"] = pd.to_numeric(stock["top_quantile_signal_score"], errors="coerce")
        stock["signal_rank"] = pd.to_numeric(stock.get("rank_by_top_quantile_prob"), errors="coerce")
        if stock["signal_rank"].isna().any():
            stock["signal_rank"] = stock.groupby("trade_date")["signal_score"].rank(method="first", ascending=False)
        stock["signal_source"] = "top_quantile_signal_score"
        return stock

    if "predicted_top_quantile_prob" in stock.columns:
        stock["signal_score"] = pd.to_numeric(stock["predicted_top_quantile_prob"], errors="coerce")
        stock["signal_rank"] = stock.groupby("trade_date")["signal_score"].rank(method="first", ascending=False)
        stock["signal_source"] = "predicted_top_quantile_prob"
        return stock

    raise RuntimeError("个股预测表缺少 predicted_return_threshold_prob / predicted_up_prob / top_quantile_signal_score / predicted_top_quantile_prob")


def build_stock_loss_risk_daily(loss_risk: pd.DataFrame) -> pd.DataFrame:
    if loss_risk.empty:
        return loss_risk
    out = loss_risk.copy()
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["symbol"] = normalize_symbol(out["symbol"])
    keep_cols = ["trade_date", "symbol", "risk_5d_loss05_prob", "rank_by_loss05_risk", "loss_label_threshold"]
    return out[[col for col in keep_cols if col in out.columns]].copy()


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
        "market_ret_5_ge05_ratio",
        "market_ret_5_le_neg05_ratio",
        "market_near_limit_up_count",
        "industry_up_ratio",
        "industry_avg_pct_chg",
        "industry_index_code",
        "industry_index_level",
        "industry_index_ret_5",
        "industry_index_ret_20",
        "industry_index_range_pos_20",
        "industry_index_ret_5_xrank",
        "stock_vs_industry_index_ret_5",
        "stock_vs_industry_index_ret_20",
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


def apply_industry_risk_adjustment(stock: pd.DataFrame) -> pd.DataFrame:
    stock = stock.copy()
    stock["industry_risk_adjustment"] = 0.0
    stock["industry_risk_adjustment_reason"] = ""
    if "predicted_industry_up_prob" not in stock.columns:
        stock["industry_adjusted_signal_score"] = stock["signal_score"]
        return stock

    up_prob = pd.to_numeric(stock["predicted_industry_up_prob"], errors="coerce")
    down_prob = pd.to_numeric(stock["predicted_industry_down_prob"], errors="coerce")
    risk_level = stock.get("industry_risk_level", pd.Series(index=stock.index, dtype=object)).fillna("")
    regime = stock.get("industry_regime", pd.Series(index=stock.index, dtype=object)).fillna("")
    ret5_rank = pd.to_numeric(stock.get("industry_index_ret_5_xrank", pd.Series(index=stock.index)), errors="coerce")
    stock_vs_ind5 = pd.to_numeric(stock.get("stock_vs_industry_index_ret_5", pd.Series(index=stock.index)), errors="coerce")

    positive = (
        (risk_level.eq("低风险") | regime.eq("行业顺风"))
        & (up_prob >= 0.56)
        & (ret5_rank.isna() | (ret5_rank >= 0.50))
    )
    negative = (
        risk_level.eq("高风险")
        | regime.isin(["行业弱势延续", "行业高位回落风险"])
        | (down_prob >= 0.62)
    )
    isolated_strength = negative & (stock_vs_ind5 >= 0.08) & (stock["signal_score"] >= 0.62)

    stock.loc[positive, "industry_risk_adjustment"] += 0.025
    stock.loc[positive, "industry_risk_adjustment_reason"] = "行业顺风加分"
    stock.loc[negative, "industry_risk_adjustment"] -= 0.045
    stock.loc[negative, "industry_risk_adjustment_reason"] = "行业高风险扣分"
    stock.loc[isolated_strength, "industry_risk_adjustment"] += 0.020
    stock.loc[isolated_strength, "industry_risk_adjustment_reason"] = "弱行业中个股相对强，减轻扣分"

    stock["industry_adjusted_signal_score"] = (stock["signal_score"] + stock["industry_risk_adjustment"]).clip(0, 1)
    stock["raw_signal_score"] = stock["signal_score"]
    stock["signal_score"] = stock["industry_adjusted_signal_score"]
    stock["signal_rank"] = stock.groupby("trade_date")["signal_score"].rank(method="first", ascending=False)
    return stock


def candidate_flags(day: pd.DataFrame) -> pd.DataFrame:
    day = day.copy()
    loss05_risk_prob = pd.to_numeric(day.get("risk_5d_loss05_prob", pd.Series(np.nan, index=day.index)), errors="coerce")
    loss05_threshold = pd.to_numeric(day.get("loss05_risk_threshold", pd.Series(0.35, index=day.index)), errors="coerce").fillna(0.35)
    loss05_high_risk = loss05_risk_prob.notna() & (loss05_risk_prob >= loss05_threshold)
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
    official_industry_high_risk = (
        day.get("industry_risk_level", pd.Series(index=day.index, dtype=object)).eq("高风险")
        | day.get("industry_regime", pd.Series(index=day.index, dtype=object)).isin(["行业弱势延续", "行业高位回落风险"])
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
        & (day["signal_score"] < 0.58)
    )
    high_risk_tail_chase_candidate = (
        day.get("aggregate_market_risk_level", pd.Series(index=day.index, dtype=object)).eq("高风险")
        & (day["market_high_risk_count"] >= 4)
        & (day["signal_rank"] >= 3)
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
        (day["signal_rank"] > 1)
        & day["signal_score"].between(0.56, 0.58)
        & (day["market_up_ratio"] < 0.58)
        & (day["range_pos_20_pctile"] > 0.70)
    )
    low_turnover_spike_fade_candidate = (
        (day["signal_rank"] > 1)
        & (day["signal_score"] < 0.58)
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
    day["is_official_industry_high_risk_candidate"] = official_industry_high_risk.astype(int)
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
    day["is_loss05_high_risk_candidate"] = loss05_high_risk.astype(int)
    day["is_fragile_candidate"] = (
        day["is_overheat_candidate"].eq(1)
        | day["is_weak_industry_candidate"].eq(1)
        | day["is_official_industry_high_risk_candidate"].eq(1)
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
        | day["is_loss05_high_risk_candidate"].eq(1)
    ).astype(int)
    if day.get("signal_source", pd.Series(index=day.index, dtype=object)).eq("direction_up_prob").any():
        direction_fragile_cols = [
            "is_high_risk_intraday_break_candidate",
            "is_high_risk_limit_up_chase_candidate",
            "is_breadth_divergence_chase_candidate",
            "is_extreme_weak_market_extension_candidate",
            "is_rebound_limit_up_volatility_candidate",
            "is_high_risk_pullback_crowded_candidate",
            "is_weak_market_weak_industry_down_candidate",
            "is_sharp_drop_rebound_candidate",
            "is_loss05_high_risk_candidate",
        ]
        day["is_fragile_candidate"] = day[direction_fragile_cols].any(axis=1).astype(int)
    return day


def _day_float(day: pd.DataFrame, col: str) -> float:
    if col not in day.columns or day.empty:
        return np.nan
    return float(pd.to_numeric(day[col].iloc[0], errors="coerce"))


def classify_market_opportunity(day: pd.DataFrame) -> tuple[str, str]:
    market_up_ratio = _day_float(day, "market_up_ratio")
    market_avg_pct_chg = _day_float(day, "market_avg_pct_chg")
    market_ret_5_ge05_ratio = _day_float(day, "market_ret_5_ge05_ratio")
    market_ret_5_le_neg05_ratio = _day_float(day, "market_ret_5_le_neg05_ratio")
    market_avg_up_prob = _day_float(day, "market_avg_up_prob")
    market_avg_down_prob = _day_float(day, "market_avg_down_prob")
    market_high_risk_count = int(_day_float(day, "market_high_risk_count") or 0)
    regime = day["aggregate_market_regime"].iloc[0] if "aggregate_market_regime" in day.columns and not day.empty else "中性"
    risk_level = day["aggregate_market_risk_level"].iloc[0] if "aggregate_market_risk_level" in day.columns and not day.empty else "中风险"

    breadth_crash = (
        (pd.notna(market_up_ratio) and market_up_ratio < 0.28)
        or (pd.notna(market_avg_pct_chg) and market_avg_pct_chg <= -1.00)
    )
    model_high_risk_confirmed = (
        (risk_level == "高风险" or regime in {"弱势延续", "高位回落"} or market_high_risk_count >= 4)
        and (
            (pd.notna(market_up_ratio) and market_up_ratio < 0.45)
            or (pd.notna(market_avg_pct_chg) and market_avg_pct_chg < 0)
            or (pd.notna(market_ret_5_le_neg05_ratio) and market_ret_5_le_neg05_ratio >= 0.28)
        )
    )
    if (
        breadth_crash
        or model_high_risk_confirmed
        or (pd.notna(market_avg_down_prob) and market_avg_down_prob >= 0.65 and pd.notna(market_avg_pct_chg) and market_avg_pct_chg < 0)
    ):
        return "E高风险", "市场高风险"

    if (
        (risk_level == "中风险" and pd.notna(market_up_ratio) and market_up_ratio < 0.55)
        or (risk_level == "高风险" and regime == "高位回落")
        or (market_high_risk_count >= 2 and pd.notna(market_avg_pct_chg) and market_avg_pct_chg < 0.30)
        or (pd.notna(market_up_ratio) and market_up_ratio < 0.40)
        or (pd.notna(market_avg_pct_chg) and market_avg_pct_chg < -0.20)
        or (pd.notna(market_ret_5_le_neg05_ratio) and market_ret_5_le_neg05_ratio >= 0.25)
        or (pd.notna(market_avg_down_prob) and market_avg_down_prob >= 0.58 and pd.notna(market_avg_pct_chg) and market_avg_pct_chg < 0.30)
    ):
        return "D偏弱", "市场偏弱"

    strong_market = (
        risk_level == "低风险"
        and pd.notna(market_up_ratio)
        and pd.notna(market_avg_pct_chg)
        and market_up_ratio >= 0.65
        and market_avg_pct_chg >= 0.80
        and (pd.isna(market_ret_5_le_neg05_ratio) or market_ret_5_le_neg05_ratio <= 0.18)
        and (pd.isna(market_avg_up_prob) or market_avg_up_prob >= 0.50)
    )
    if strong_market:
        return "A强机会", "市场强机会"

    positive_market = (
        (
            (pd.notna(market_up_ratio) and market_up_ratio >= 0.55 and pd.notna(market_avg_pct_chg) and market_avg_pct_chg >= -0.10)
            or (pd.notna(market_avg_up_prob) and market_avg_up_prob >= 0.52)
            or (pd.notna(market_ret_5_ge05_ratio) and market_ret_5_ge05_ratio >= 0.18)
        )
        and regime != "高位回落"
        and not (risk_level == "高风险" and pd.notna(market_up_ratio) and market_up_ratio < 0.50)
    )
    if positive_market:
        return "B偏强", "市场偏强"

    return "C中性", "市场中性"


def add_market_opportunity_diagnostics(day: pd.DataFrame) -> pd.DataFrame:
    day = day.copy()
    market_level, market_reason = classify_market_opportunity(day)
    day["market_opportunity_level"] = market_level
    day["market_opportunity_reason"] = market_reason
    market_adjustment = {
        "A强机会": 0.030,
        "B偏强": 0.015,
        "C中性": 0.000,
        "D偏弱": -0.040,
        "E高风险": -0.090,
    }.get(market_level, 0.0)
    day["market_style_adjustment"] = market_adjustment
    return day


def apply_market_signal_correction(day: pd.DataFrame) -> pd.DataFrame:
    day = day.copy()
    day["candidate_risk_adjustment"] = 0.0
    day["candidate_risk_reason"] = ""

    risk_rules = [
        ("is_fragile_candidate", -0.060, "脆弱候选"),
        ("is_overheat_candidate", -0.035, "过热"),
        ("is_high_risk_intraday_break_candidate", -0.050, "高风险日破位"),
        ("is_breadth_divergence_chase_candidate", -0.050, "弱宽度追高"),
        ("is_crowded_intraday_break_candidate", -0.045, "拥挤破位"),
        ("is_extreme_momentum_extension_candidate", -0.040, "极端动量延伸"),
        ("is_rebound_crowded_chase_candidate", -0.040, "反弹拥挤追高"),
        ("is_sharp_drop_rebound_candidate", -0.035, "急跌反弹不确认"),
        ("is_loss05_high_risk_candidate", -0.050, "亏损风险高"),
    ]
    for col, penalty, reason in risk_rules:
        if col not in day.columns:
            continue
        mask = day[col].eq(1)
        day.loc[mask, "candidate_risk_adjustment"] += penalty
        day.loc[mask, "candidate_risk_reason"] = day.loc[mask, "candidate_risk_reason"].map(
            lambda value: f"{value};{reason}" if value else reason
        )

    day["market_corrected_signal_score"] = (
        pd.to_numeric(day["signal_score"], errors="coerce").fillna(0)
        + day["market_style_adjustment"]
        + day["candidate_risk_adjustment"]
    ).clip(lower=0, upper=1)
    day["market_corrected_rank"] = day["market_corrected_signal_score"].rank(method="first", ascending=False)
    day["signal_score_before_market_correction"] = day["signal_score"]
    day["signal_score"] = day["market_corrected_signal_score"]
    day["signal_rank"] = day["market_corrected_rank"]
    return day


def decide_action(day: pd.DataFrame, args: argparse.Namespace) -> tuple[str, int, str, str, int, str]:
    top = day.sort_values("signal_rank").head(args.max_top_n).copy()
    market_level = top["market_opportunity_level"].iloc[0] if "market_opportunity_level" in top and not top.empty else "C中性"
    market_reason = top["market_opportunity_reason"].iloc[0] if "market_opportunity_reason" in top and not top.empty else "市场中性"
    if top.empty:
        return "不出手", 0, "无候选股票", market_level, args.max_top_n, market_reason

    best_score = float(pd.to_numeric(top["market_corrected_signal_score"].iloc[0], errors="coerce"))
    fragile_top = int(top.head(3)["is_fragile_candidate"].sum()) if "is_fragile_candidate" in top.columns else 0

    if market_level == "E高风险":
        return "不出手", 0, f"{market_level}：市场风险过高", market_level, 0, market_reason
    if market_level == "D偏弱":
        if best_score >= 0.30 and fragile_top < 3:
            return "Top1", 1, f"{market_level}：只允许最强1只", market_level, 1, market_reason
        return "不出手", 0, f"{market_level}：无足够强候选", market_level, 0, market_reason
    if market_level == "C中性":
        signal_count = min(2, len(top))
        return f"Top{signal_count}", signal_count, f"{market_level}：中性市场降为Top{signal_count}", market_level, signal_count, market_reason

    signal_count = min(args.max_top_n, len(top))
    action = f"Top{signal_count}" if signal_count < 3 else "Top3"
    return action, signal_count, f"{market_level}：允许{action}", market_level, signal_count, market_reason


def build_signals(
    stock: pd.DataFrame,
    market_daily: pd.DataFrame,
    industry_daily: pd.DataFrame | None,
    loss_risk_daily: pd.DataFrame | None,
    args: argparse.Namespace,
) -> pd.DataFrame:
    out = stock.merge(market_daily, on="trade_date", how="left")
    if out["aggregate_market_risk_level"].isna().any():
        missing = sorted(out.loc[out["aggregate_market_risk_level"].isna(), "trade_date"].dropna().unique())
        raise RuntimeError(f"市场预测缺少这些日期: {missing[:10]}")
    if industry_daily is not None and not industry_daily.empty:
        out = out.merge(industry_daily, on=["trade_date", "industry"], how="left")
    if loss_risk_daily is not None and not loss_risk_daily.empty:
        out = out.merge(loss_risk_daily, on=["trade_date", "symbol"], how="left")
    out = apply_industry_risk_adjustment(out)
    out["risk_5d_loss05_prob"] = pd.to_numeric(out.get("risk_5d_loss05_prob", np.nan), errors="coerce")
    out["loss05_risk_threshold"] = args.max_loss05_risk
    out["final_top3_score"] = out["signal_score"] * (1 - out["risk_5d_loss05_prob"].fillna(0)).clip(lower=0, upper=1)
    has_loss_risk = out["risk_5d_loss05_prob"].notna()
    out.loc[has_loss_risk, "signal_score"] = out.loc[has_loss_risk, "final_top3_score"]
    out["signal_rank"] = out.groupby("trade_date")["signal_score"].rank(method="first", ascending=False)

    frames: list[pd.DataFrame] = []
    for trade_date, day in out.groupby("trade_date", sort=True):
        day = candidate_flags(day)
        day = add_market_opportunity_diagnostics(day)
        day = apply_market_signal_correction(day)
        action, signal_count, reason, market_level, market_limit, market_reason = decide_action(day, args)
        day = day.sort_values("signal_rank").copy()
        day["signal_eligible_rank"] = np.arange(1, len(day) + 1)
        day["signal_action"] = action
        day["signal_count"] = signal_count
        day["signal_reason"] = reason
        day["market_opportunity_level"] = market_level
        day["market_action_limit"] = market_limit
        day["market_opportunity_reason"] = market_reason
        day["final_signal_rank"] = day["signal_rank"]
        day["is_final_signal"] = (day["signal_eligible_rank"] <= signal_count).astype(int)
        frames.append(day)
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    args = parse_args()
    stock_path = Path(args.stock_prediction).resolve()
    market_path = Path(args.market_prediction).resolve()
    industry_path = Path(args.industry_prediction).resolve() if args.industry_prediction else None
    loss_risk_path = Path(args.stock_loss_risk_prediction).resolve() if args.stock_loss_risk_prediction else None
    feature_path = Path(args.stock_feature_file).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    stock = read_csv(stock_path)
    market = read_csv(market_path)
    industry = read_csv(industry_path) if industry_path else pd.DataFrame()
    loss_risk = read_csv(loss_risk_path) if loss_risk_path else pd.DataFrame()
    feature = read_csv(feature_path)

    stock = normalize_stock_signal_columns(stock)

    stock = enrich_with_feature_percentiles(stock, feature)
    market_daily = build_market_daily(market)
    industry_daily = build_industry_daily(industry) if not industry.empty else None
    loss_risk_daily = build_stock_loss_risk_daily(loss_risk) if not loss_risk.empty else None
    result = build_signals(stock, market_daily, industry_daily, loss_risk_daily, args)

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
