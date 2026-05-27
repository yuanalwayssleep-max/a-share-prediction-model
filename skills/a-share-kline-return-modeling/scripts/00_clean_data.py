#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = Path(__file__).resolve().parents[1]

DEFAULT_DATA_DIR = ROOT / "skills" / "a-share-data-fetching" / "data"
DEFAULT_STOCK_DIR = DEFAULT_DATA_DIR / "单只股票日k"
DEFAULT_INDEX_FILE = DEFAULT_DATA_DIR / "指数日K文件" / "00_核心指数日K.csv"
DEFAULT_OUTPUT_DIR = SKILL_DIR / "data"

STOCK_NUMERIC_COLUMNS = ["开盘", "收盘", "最高", "最低", "成交量", "成交额", "振幅", "涨跌幅", "涨跌额", "换手率"]
STOCK_FEATURE_OUTPUT = "个股k线特征数据.csv"
INDEX_OUTPUT = "指数k线特征数据.csv"
GENERATED_OUTPUT_NAMES = {
    STOCK_FEATURE_OUTPUT,
    INDEX_OUTPUT,
    "01_stock_daily_features.csv",
    "01_index_daily_clean.csv",
}
STOCK_OUTPUT_COLUMNS = [
    "trade_date",
    "symbol",
    "name",
    "board",
    "industry",
    "close",
    "pct_chg",
    "turnover_pct",
    "is_st",
    "is_training_eligible",
    "ret_1",
    "ret_3",
    "ret_5",
    "ret_10",
    "ret_20",
    "close_ma_ratio_5",
    "close_ma_ratio_10",
    "close_ma_ratio_20",
    "vol_ratio_5",
    "amount_ratio_5",
    "volatility_5",
    "amp_mean_5",
    "vol_ratio_10",
    "amount_ratio_10",
    "volatility_10",
    "body_pct",
    "close_position_in_day",
    "range_pos_20",
    "dist_high_20",
    "dist_low_20",
    "is_pre_holiday_3",
    "is_post_holiday_3",
    "pre_holiday_tday",
    "post_holiday_tday",
    "holiday_gap_days",
    "market_up_ratio",
    "market_down_ratio",
    "market_avg_pct_chg",
    "industry_up_ratio",
    "industry_avg_pct_chg",
    "stock_vs_market_pct_chg",
    "stock_vs_industry_pct_chg",
    "hs300_ret_5",
    "zz500_ret_5",
    "zz1000_ret_5",
    "future_5_trade_date",
    "future_5_close",
    "future_5_return",
    "future_5_direction",
    "future_5_up_label",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="清洗原始日K并生成股票特征表和指数日K表")
    parser.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR), help="原始data目录")
    parser.add_argument("--stock-dir", default=str(DEFAULT_STOCK_DIR), help="单只股票日K目录")
    parser.add_argument("--index-file", default=str(DEFAULT_INDEX_FILE), help="核心指数日K文件")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="清洗输出目录")
    parser.add_argument("--future-horizon", type=int, default=5, help="写入标签列时使用的未来交易日数")
    parser.add_argument("--pct-diff-tolerance", type=float, default=0.75, help="涨跌幅复核软异常阈值，单位百分点")
    return parser.parse_args()


def read_csv(path: Path, **kwargs) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", **kwargs)


def normalize_symbol(value: object) -> str:
    match = re.search(r"(\d{6})", str(value).strip())
    return match.group(1) if match else ""


def parse_symbol_name(path: Path) -> tuple[str, str]:
    stem = path.stem
    if stem.endswith("_daily_k"):
        stem = stem[: -len("_daily_k")]
    parts = stem.split("_", 1)
    return normalize_symbol(parts[0]), parts[1] if len(parts) > 1 else ""


def infer_exchange(symbol: str) -> str:
    if symbol.startswith(("4", "8", "9")):
        return "北交所"
    if symbol.startswith(("5", "6")):
        return "上交所"
    if symbol.startswith(("0", "2", "3")):
        return "深交所"
    return ""


def infer_board(symbol: str) -> str:
    if symbol.startswith(("4", "8", "9")):
        return "北交所"
    if symbol.startswith(("688", "689")):
        return "科创板"
    if symbol.startswith(("300", "301")):
        return "创业板"
    if symbol.startswith(("000", "001", "002", "003")):
        return "深市主板"
    if symbol.startswith(("600", "601", "603", "605")):
        return "沪市主板"
    return ""


def is_st_name(name: object) -> bool:
    return "ST" in str(name).upper()


def limit_pct(symbol: str, name: object, board: object, exchange: object) -> float:
    if is_st_name(name):
        return 5.0
    if "北交所" in str(board) or "北交所" in str(exchange) or symbol.startswith(("4", "8", "9")):
        return 30.0
    if "创业板" in str(board) or "科创" in str(board) or symbol.startswith(("300", "301", "688", "689")):
        return 20.0
    return 10.0


def snapshot_date(path: Path) -> str:
    match = re.search(r"(\d{8})", path.name)
    if not match:
        return ""
    return pd.to_datetime(match.group(1), format="%Y%m%d").strftime("%Y-%m-%d")


def load_metadata(data_dir: Path) -> pd.DataFrame:
    snapshot_paths = sorted(data_dir.glob("a股快照_*.csv")) + sorted((data_dir / "a股快照历史").glob("a股快照_*.csv"))
    frames: list[pd.DataFrame] = []
    for path in snapshot_paths:
        try:
            df = read_csv(path, dtype=str)
        except Exception:
            continue
        if "代码" not in df.columns:
            continue
        out = pd.DataFrame()
        out["symbol"] = df["代码"].map(normalize_symbol)
        out["name"] = df.get("名称", "")
        out["exchange"] = df.get("交易所", "")
        out["board"] = df.get("板块", "")
        out["industry"] = df.get("行业", "")
        out["region"] = df.get("地域板块", "")
        out["themes"] = df.get("概念题材", "")
        out["snapshot_date"] = snapshot_date(path)
        out = out[out["symbol"].str.fullmatch(r"\d{6}", na=False)]
        frames.append(out)
    if not frames:
        return pd.DataFrame(columns=["symbol", "name", "exchange", "board", "industry", "region", "themes"])
    meta = pd.concat(frames, ignore_index=True)
    meta["_snapshot_date"] = pd.to_datetime(meta["snapshot_date"], errors="coerce")
    meta = meta.sort_values(["symbol", "_snapshot_date"]).drop_duplicates("symbol", keep="last")
    return meta.drop(columns=["_snapshot_date"]).reset_index(drop=True)


def load_stock_raw(stock_dir: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for path in sorted(stock_dir.glob("*.csv")):
        symbol, name = parse_symbol_name(path)
        if not symbol:
            continue
        df = read_csv(path, dtype=str)
        if df.empty:
            continue
        df["symbol"] = symbol
        df["name_from_file"] = name
        df["source_file"] = str(path)
        df["trade_date"] = pd.to_datetime(df.get("日期"), errors="coerce")
        for col in STOCK_NUMERIC_COLUMNS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        frames.append(df)
    if not frames:
        raise RuntimeError(f"未找到股票日K文件: {stock_dir}")
    return pd.concat(frames, ignore_index=True)


def build_holiday_calendar_features(trade_dates: pd.Series, window: int = 3, min_gap_days: int = 4) -> pd.DataFrame:
    dates = pd.Series(pd.to_datetime(trade_dates, errors="coerce").dropna().unique()).sort_values().reset_index(drop=True)
    calendar = pd.DataFrame({"trade_date": dates})
    calendar["is_pre_holiday_3"] = 0
    calendar["is_post_holiday_3"] = 0
    calendar["pre_holiday_tday"] = 0
    calendar["post_holiday_tday"] = 0
    calendar["holiday_gap_days"] = 0
    if calendar.empty:
        return calendar

    next_dates = calendar["trade_date"].shift(-1)
    gaps = (next_dates - calendar["trade_date"]).dt.days
    break_indices = calendar.index[gaps >= min_gap_days].tolist()
    for break_idx in break_indices:
        gap_days = int(gaps.loc[break_idx])
        for offset in range(window):
            pre_idx = break_idx - offset
            if pre_idx >= 0:
                calendar.loc[pre_idx, "is_pre_holiday_3"] = 1
                calendar.loc[pre_idx, "pre_holiday_tday"] = offset + 1
                calendar.loc[pre_idx, "holiday_gap_days"] = max(calendar.loc[pre_idx, "holiday_gap_days"], gap_days)
            post_idx = break_idx + 1 + offset
            if post_idx < len(calendar):
                calendar.loc[post_idx, "is_post_holiday_3"] = 1
                calendar.loc[post_idx, "post_holiday_tday"] = offset + 1
                calendar.loc[post_idx, "holiday_gap_days"] = max(calendar.loc[post_idx, "holiday_gap_days"], gap_days)
    return calendar


def add_holiday_features(out: pd.DataFrame) -> pd.DataFrame:
    calendar = build_holiday_calendar_features(out["trade_date"])
    return out.merge(calendar, on="trade_date", how="left")


def clean_index_daily(index_file: Path, future_horizon: int) -> pd.DataFrame:
    if not index_file.exists():
        return pd.DataFrame(columns=["trade_date", "index_code", "index_name", "open", "high", "low", "close", "preclose", "volume", "amount", "pct_chg"])
    raw = read_csv(index_file, dtype=str)
    rename = {
        "指数名称": "index_name",
        "date": "trade_date",
        "code": "index_code",
        "pctChg": "pct_chg",
    }
    out = raw.rename(columns=rename)
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce")
    for col in ["open", "high", "low", "close", "preclose", "volume", "amount", "pct_chg"]:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["trade_date", "index_code", "close"]).copy()
    out = out.sort_values(["index_code", "trade_date"]).drop_duplicates(["index_code", "trade_date"], keep="last")
    out = add_holiday_features(out)

    group = out.groupby("index_code", group_keys=False)
    out["index_ret_1"] = group["close"].pct_change(1, fill_method=None)
    out["index_ret_5"] = group["close"].pct_change(5, fill_method=None)
    out["index_ret_10"] = group["close"].pct_change(10, fill_method=None)
    out["index_ret_20"] = group["close"].pct_change(20, fill_method=None)
    high20 = group["high"].rolling(20, min_periods=5).max().reset_index(level=0, drop=True)
    low20 = group["low"].rolling(20, min_periods=5).min().reset_index(level=0, drop=True)
    out["index_range_pos_20"] = (out["close"] - low20) / (high20 - low20 + 1e-9)
    for window in (5, 10, 20):
        ma = group["close"].rolling(window, min_periods=max(2, window // 2)).mean().reset_index(level=0, drop=True)
        amount_ma = group["amount"].rolling(window, min_periods=max(2, window // 2)).mean().reset_index(level=0, drop=True)
        out[f"index_close_ma_ratio_{window}"] = out["close"] / ma.replace(0, np.nan) - 1
        out[f"index_amount_ratio_{window}"] = out["amount"] / amount_ma.replace(0, np.nan)
        out[f"index_volatility_{window}"] = group["index_ret_1"].rolling(window, min_periods=max(2, window // 2)).std().reset_index(level=0, drop=True)
    day_range = (out["high"] - out["low"]).replace(0, np.nan)
    out["index_body_pct"] = (out["close"] - out["open"]) / out["open"].replace(0, np.nan)
    out["index_close_position_in_day"] = (out["close"] - out["low"]) / day_range
    out["index_amount_change_1"] = group["amount"].pct_change(1, fill_method=None)
    out["future_5_trade_date"] = group["trade_date"].shift(-future_horizon)
    out["future_5_close"] = group["close"].shift(-future_horizon)
    out["future_5_return"] = out["future_5_close"] / out["close"].replace(0, np.nan) - 1
    out["future_5_direction"] = np.where(out["future_5_return"].notna(), np.where(out["future_5_return"] > 0, "上涨", "下跌"), "")
    out["future_5_up_label"] = np.where(out["future_5_return"].notna(), (out["future_5_return"] > 0).astype(int), np.nan)
    out["trade_date"] = out["trade_date"].dt.strftime("%Y-%m-%d")
    out["future_5_trade_date"] = pd.to_datetime(out["future_5_trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out = out.replace([np.inf, -np.inf], np.nan)
    return out[
        [
            "trade_date",
            "index_code",
            "index_name",
            "open",
            "high",
            "low",
            "close",
            "preclose",
            "volume",
            "amount",
            "pct_chg",
            "is_pre_holiday_3",
            "is_post_holiday_3",
            "pre_holiday_tday",
            "post_holiday_tday",
            "holiday_gap_days",
            "index_ret_1",
            "index_ret_5",
            "index_ret_10",
            "index_ret_20",
            "index_range_pos_20",
            "index_close_ma_ratio_5",
            "index_amount_ratio_5",
            "index_volatility_5",
            "index_close_ma_ratio_10",
            "index_amount_ratio_10",
            "index_volatility_10",
            "index_close_ma_ratio_20",
            "index_amount_ratio_20",
            "index_volatility_20",
            "index_body_pct",
            "index_close_position_in_day",
            "index_amount_change_1",
            "future_5_trade_date",
            "future_5_close",
            "future_5_return",
            "future_5_direction",
            "future_5_up_label",
        ]
    ]


def pivot_index_features(index_daily: pd.DataFrame) -> pd.DataFrame:
    if index_daily.empty:
        return pd.DataFrame(columns=["trade_date"])
    name_map = {
        "上证指数": "sh",
        "沪深300": "hs300",
        "中证500": "zz500",
        "中证1000": "zz1000",
        "创业板指": "cyb",
    }
    frames: list[pd.DataFrame] = []
    for name, prefix in name_map.items():
        part = index_daily[index_daily["index_name"].eq(name)].copy()
        if part.empty:
            continue
        cols = ["trade_date", "index_ret_1", "index_ret_5", "index_range_pos_20"]
        part = part[cols].rename(
            columns={
                "index_ret_1": f"{prefix}_ret_1",
                "index_ret_5": f"{prefix}_ret_5",
                "index_range_pos_20": f"{prefix}_range_pos_20",
            }
        )
        frames.append(part)
    if not frames:
        return pd.DataFrame(columns=["trade_date"])
    out = frames[0]
    for frame in frames[1:]:
        out = out.merge(frame, on="trade_date", how="outer")
    return out


def add_quality_flags(out: pd.DataFrame, pct_diff_tolerance: float) -> pd.DataFrame:
    out = out.copy()
    out["is_st"] = out["name"].map(is_st_name).astype(int)
    out["limit_pct"] = out.apply(lambda row: limit_pct(row["symbol"], row["name"], row["board"], row["exchange"]), axis=1)
    out["near_limit_up"] = (out["pct_chg"] >= out["limit_pct"] * 0.95).astype(int)
    out["near_limit_down"] = (out["pct_chg"] <= -out["limit_pct"] * 0.95).astype(int)
    out["natural_day_gap"] = out.groupby("symbol")["trade_date"].diff().dt.days

    prev_close = out.groupby("symbol")["close"].shift(1)
    expected_pct = (out["close"] / prev_close.replace(0, np.nan) - 1) * 100
    out["pct_chg_check_diff"] = (expected_pct - out["pct_chg"]).abs()

    issues: list[list[str]] = [[] for _ in range(len(out))]

    def add_issue(mask: pd.Series, name: str) -> None:
        for i in np.flatnonzero(mask.fillna(False).to_numpy()):
            issues[i].append(name)

    hard_issue_names = {
        "invalid_key",
        "duplicate_trade_date_symbol",
        "missing_core_ohlcv",
        "non_positive_price",
        "non_positive_volume_amount",
        "invalid_ohlc_logic",
    }
    add_issue(out["trade_date"].isna() | ~out["symbol"].str.fullmatch(r"\d{6}", na=False), "invalid_key")
    add_issue(out.duplicated(["trade_date", "symbol"], keep=False), "duplicate_trade_date_symbol")
    add_issue(out[["open", "close", "high", "low", "volume", "amount"]].isna().any(axis=1), "missing_core_ohlcv")
    add_issue((out[["open", "close", "high", "low"]] <= 0).any(axis=1), "non_positive_price")
    add_issue((out["volume"] <= 0) | (out["amount"] <= 0), "non_positive_volume_amount")
    add_issue(
        (out["high"] < out[["open", "close", "low"]].max(axis=1))
        | (out["low"] > out[["open", "close", "high"]].min(axis=1))
        | (out["high"] < out["low"]),
        "invalid_ohlc_logic",
    )
    add_issue(out["near_limit_up"].eq(1), "near_limit_up")
    add_issue(out["near_limit_down"].eq(1), "near_limit_down")
    add_issue(out["pct_chg"].abs() > out["limit_pct"] + 1.0, "pct_chg_beyond_limit")
    add_issue(out["amplitude_pct"] > 40, "extreme_amplitude")
    add_issue(out["turnover_pct"] > 80, "extreme_turnover")
    add_issue(out["pct_chg_check_diff"] > pct_diff_tolerance, "pct_chg_check_diff_large")

    out["quality_issues"] = [";".join(item) for item in issues]
    out["quality_issue_count"] = [len(item) for item in issues]
    out["has_hard_issue"] = [int(any(issue in hard_issue_names for issue in item)) for item in issues]
    out["has_soft_issue"] = ((out["quality_issue_count"] > 0) & out["has_hard_issue"].eq(0)).astype(int)
    out["is_training_eligible"] = (out["has_hard_issue"].eq(0) & out["has_soft_issue"].eq(0)).astype(int)
    return out


def add_stock_features(out: pd.DataFrame, future_horizon: int) -> pd.DataFrame:
    out = out.sort_values(["symbol", "trade_date"]).reset_index(drop=True).copy()
    group = out.groupby("symbol", group_keys=False)
    out["ret_1"] = group["close"].pct_change(1, fill_method=None)
    out["ret_3"] = group["close"].pct_change(3, fill_method=None)
    out["ret_5"] = group["close"].pct_change(5, fill_method=None)
    out["ret_10"] = group["close"].pct_change(10, fill_method=None)
    out["ret_20"] = group["close"].pct_change(20, fill_method=None)

    for window in (5, 10, 20):
        ma = group["close"].rolling(window, min_periods=max(2, window // 2)).mean().reset_index(level=0, drop=True)
        out[f"close_ma_ratio_{window}"] = out["close"] / ma - 1
    for window in (5, 10):
        vol_ma = group["volume"].rolling(window, min_periods=max(2, window // 2)).mean().reset_index(level=0, drop=True)
        amount_ma = group["amount"].rolling(window, min_periods=max(2, window // 2)).mean().reset_index(level=0, drop=True)
        out[f"vol_ratio_{window}"] = out["volume"] / vol_ma.replace(0, np.nan)
        out[f"amount_ratio_{window}"] = out["amount"] / amount_ma.replace(0, np.nan)
        out[f"volatility_{window}"] = group["ret_1"].rolling(window, min_periods=max(2, window // 2)).std().reset_index(level=0, drop=True)
        out[f"amp_mean_{window}"] = group["amplitude_pct"].rolling(window, min_periods=max(2, window // 2)).mean().reset_index(level=0, drop=True)

    out["vol_change_1"] = group["volume"].pct_change(1, fill_method=None)
    out["amount_change_1"] = group["amount"].pct_change(1, fill_method=None)
    day_range = (out["high"] - out["low"]).replace(0, np.nan)
    out["body_pct"] = (out["close"] - out["open"]) / out["open"].replace(0, np.nan)
    out["upper_shadow_pct"] = (out["high"] - out[["open", "close"]].max(axis=1)) / day_range
    out["lower_shadow_pct"] = (out[["open", "close"]].min(axis=1) - out["low"]) / day_range
    out["close_position_in_day"] = (out["close"] - out["low"]) / day_range

    high20 = group["high"].rolling(20, min_periods=5).max().reset_index(level=0, drop=True)
    low20 = group["low"].rolling(20, min_periods=5).min().reset_index(level=0, drop=True)
    out["range_pos_20"] = (out["close"] - low20) / (high20 - low20 + 1e-9)
    out["dist_high_20"] = out["close"] / high20.replace(0, np.nan) - 1
    out["dist_low_20"] = out["close"] / low20.replace(0, np.nan) - 1
    out["future_5_trade_date"] = group["trade_date"].shift(-future_horizon)
    out["future_5_close"] = group["close"].shift(-future_horizon)
    out["future_5_return"] = out["future_5_close"] / out["close"].replace(0, np.nan) - 1
    out["future_5_direction"] = np.where(out["future_5_return"].notna(), np.where(out["future_5_return"] > 0, "上涨", "下跌"), "")
    out["future_5_up_label"] = np.where(out["future_5_return"].notna(), (out["future_5_return"] > 0).astype(int), np.nan)

    return out


def add_market_industry_features(out: pd.DataFrame) -> pd.DataFrame:
    out = out.copy()
    by_date = out.groupby("trade_date", dropna=False)
    market = by_date.agg(
        market_stock_count=("symbol", "nunique"),
        market_up_ratio=("pct_chg", lambda s: float((s > 0).mean())),
        market_down_ratio=("pct_chg", lambda s: float((s < 0).mean())),
        market_avg_pct_chg=("pct_chg", "mean"),
        market_median_pct_chg=("pct_chg", "median"),
        market_amount=("amount", "sum"),
        market_near_limit_up_ratio=("near_limit_up", "mean"),
        market_near_limit_down_ratio=("near_limit_down", "mean"),
    ).reset_index()
    out = out.merge(market, on="trade_date", how="left")

    industry = (
        out.groupby(["trade_date", "industry"], dropna=False)
        .agg(
            industry_stock_count=("symbol", "nunique"),
            industry_up_ratio=("pct_chg", lambda s: float((s > 0).mean())),
            industry_avg_pct_chg=("pct_chg", "mean"),
            industry_amount=("amount", "sum"),
        )
        .reset_index()
    )
    out = out.merge(industry, on=["trade_date", "industry"], how="left")
    out["stock_vs_market_pct_chg"] = out["pct_chg"] - out["market_avg_pct_chg"]
    out["stock_vs_industry_pct_chg"] = out["pct_chg"] - out["industry_avg_pct_chg"]
    return out


def build_stock_features(stock_dir: Path, meta: pd.DataFrame, index_features: pd.DataFrame, future_horizon: int, pct_diff_tolerance: float) -> pd.DataFrame:
    raw = load_stock_raw(stock_dir)
    raw["symbol"] = raw["symbol"].map(normalize_symbol)
    raw = raw[raw["symbol"].str.fullmatch(r"\d{6}", na=False)].copy()

    meta_cols = ["symbol", "name", "exchange", "board", "industry", "region", "themes"]
    meta_for_merge = meta[[col for col in meta_cols if col in meta.columns]].copy() if not meta.empty else pd.DataFrame(columns=meta_cols)
    out = raw.merge(meta_for_merge, on="symbol", how="left")
    out["name"] = out["name"].fillna("").replace("", np.nan).fillna(out["name_from_file"])
    out["exchange"] = out["exchange"].fillna("").replace("", np.nan).fillna(out["symbol"].map(infer_exchange))
    out["board"] = out["board"].fillna("").replace("", np.nan).fillna(out["symbol"].map(infer_board))
    out["industry"] = out["industry"].fillna("未知")

    out = out.rename(
        columns={
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "振幅": "amplitude_pct",
            "涨跌幅": "pct_chg",
            "涨跌额": "chg_amount",
            "换手率": "turnover_pct",
        }
    )
    out = out.sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    out = add_quality_flags(out, pct_diff_tolerance)
    out = add_stock_features(out, future_horizon)
    out = add_holiday_features(out)
    out = add_market_industry_features(out)
    if not index_features.empty:
        out["trade_date_text"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        out = out.merge(index_features, left_on="trade_date_text", right_on="trade_date", how="left", suffixes=("", "_index"))
        out = out.drop(columns=["trade_date_index", "trade_date_text"], errors="ignore")
        if "hs300_ret_5" in out.columns:
            out["stock_vs_hs300_ret_5"] = out["ret_5"] - out["hs300_ret_5"]
        if "zz500_ret_5" in out.columns:
            out["stock_vs_zz500_ret_5"] = out["ret_5"] - out["zz500_ret_5"]
        if "zz1000_ret_5" in out.columns:
            out["stock_vs_zz1000_ret_5"] = out["ret_5"] - out["zz1000_ret_5"]

    out = out[out["has_hard_issue"].eq(0)].copy()
    for col in ["trade_date", "future_5_trade_date"]:
        out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%Y-%m-%d")
    out = out.replace([np.inf, -np.inf], np.nan)
    return out[[col for col in STOCK_OUTPUT_COLUMNS if col in out.columns]].copy()


def clean_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in GENERATED_OUTPUT_NAMES:
        path = output_dir / name
        if path.exists():
            path.unlink()


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir).resolve()
    stock_dir = Path(args.stock_dir).resolve()
    index_file = Path(args.index_file).resolve()
    output_dir = Path(args.output_dir).resolve()

    index_daily = clean_index_daily(index_file, args.future_horizon)
    index_features = pivot_index_features(index_daily)
    meta = load_metadata(data_dir)
    stock_features = build_stock_features(stock_dir, meta, index_features, args.future_horizon, args.pct_diff_tolerance)

    clean_output_dir(output_dir)
    stock_path = output_dir / STOCK_FEATURE_OUTPUT
    index_path = output_dir / INDEX_OUTPUT
    stock_features.to_csv(stock_path, index=False, encoding="utf-8-sig")
    index_daily.to_csv(index_path, index=False, encoding="utf-8-sig")

    print(f"股票特征表: {stock_path}")
    print(f"  rows={len(stock_features)}, stocks={stock_features['symbol'].nunique()}, columns={len(stock_features.columns)}")
    print(f"  training_eligible={int(stock_features['is_training_eligible'].sum())} ({stock_features['is_training_eligible'].mean():.2%})")
    print(f"指数日K表: {index_path}")
    print(f"  rows={len(index_daily)}, indexes={index_daily['index_code'].nunique() if not index_daily.empty else 0}")


if __name__ == "__main__":
    main()
