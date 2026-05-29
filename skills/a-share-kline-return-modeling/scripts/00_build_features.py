#!/usr/bin/env python3
"""Build V1 stock/market features and tradeable 5-day labels."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd


DEFAULT_CONFIG = {
    "commission_rate": 0.0003,
    "stamp_tax_rate": 0.001,
    "transfer_fee_rate": 0.00001,
    "buy_slippage_rate": 0.0005,
    "sell_slippage_rate": 0.0005,
    "min_listing_days": 60,
    "min_amount": 30_000_000,
    "min_avg_amount_5": 30_000_000,
    "holding_trade_days": 5,
    "replace_unfilled_entry": False,
    "allow_exit_delay": True,
}

MODEL_FORBIDDEN_PREFIXES = ("future_", "label_", "entry_", "exit_", "actual_")
MODEL_FORBIDDEN_COLUMNS = {
    "gross_future_5_return",
    "buy_cost_rate",
    "sell_cost_rate",
    "buy_slippage_rate",
    "sell_slippage_rate",
    "tradable_at_entry",
    "tradable_at_exit",
    "limit_up_at_entry",
    "limit_down_during_holding",
    "suspended_during_holding",
    "forced_exit_delay_days",
    "daily_stock_count",
    "strong_rank_level",
    "absolute_strong_level",
    "trade_date",
    "symbol",
    "name",
    "industry",
    "board",
    "source_duplicate_row",
}


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        if re.search(r"[.eE]", value):
            return float(value)
        return int(value)
    except ValueError:
        return value.strip("\"'")


def load_config(path: Path) -> dict[str, Any]:
    config = dict(DEFAULT_CONFIG)
    if not path.exists():
        return config

    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            config.update(loaded)
        return config
    except Exception:
        pass

    current_parent: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" ") and line.endswith(":"):
            current_parent = line[:-1].strip()
            config.setdefault(current_parent, {})
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        parsed = parse_scalar(value)
        if raw_line.startswith(" ") and current_parent and isinstance(config.get(current_parent), dict):
            config[current_parent][key] = parsed
        else:
            current_parent = None
            config[key] = parsed
    return config


def normalize_symbol(value: Any) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = re.sub(r"\D", "", text)
    return digits.zfill(6)[-6:]


def read_stock_list(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"代码": str}, encoding="utf-8-sig")
    df = df.rename(
        columns={
            "代码": "symbol",
            "名称": "name",
            "行业": "industry",
            "板块": "board",
            "是否ST": "is_st",
        }
    )
    df["symbol"] = df["symbol"].map(normalize_symbol)
    df["name"] = df["name"].astype(str)
    df["industry"] = df.get("industry", "UNKNOWN").fillna("UNKNOWN").astype(str)
    df["is_st"] = pd.to_numeric(df.get("is_st", 0), errors="coerce").fillna(0).astype(int)
    return df[["symbol", "name", "industry", "board", "is_st"]]


def read_daily_k(path: Path, meta: dict[str, Any]) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")
    rename = {
        "日期": "trade_date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "涨跌幅": "pct_chg",
        "换手率": "turnover_pct",
    }
    df = df.rename(columns=rename)
    keep = ["trade_date", "open", "close", "high", "low", "volume", "amount", "pct_chg", "turnover_pct"]
    missing = [col for col in keep if col not in df.columns]
    if missing:
        raise ValueError(f"{path} missing columns: {missing}")
    df = df[keep].copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    for col in keep[1:]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["symbol"] = meta["symbol"]
    df["name"] = meta["name"]
    df["industry"] = meta["industry"]
    df["board"] = meta.get("board", "")
    df["is_st"] = int(meta.get("is_st", 0))
    return df.sort_values("trade_date")


def load_all_daily_k(source_dir: Path, stock_list: pd.DataFrame) -> pd.DataFrame:
    meta_by_symbol = stock_list.set_index("symbol").to_dict("index")
    frames: list[pd.DataFrame] = []
    for path in sorted(source_dir.glob("*_daily_k.csv")):
        symbol = normalize_symbol(path.name.split("_", 1)[0])
        if symbol not in meta_by_symbol:
            continue
        frames.append(read_daily_k(path, {"symbol": symbol, **meta_by_symbol[symbol]}))
    if not frames:
        raise FileNotFoundError(f"No daily k files matched stock list in {source_dir}")
    data = pd.concat(frames, ignore_index=True).sort_values(["symbol", "trade_date"])
    data["source_duplicate_row"] = data.duplicated(["symbol", "trade_date"], keep=False)
    return data.drop_duplicates(["symbol", "trade_date"], keep="last")


def add_stock_features(df: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    df = df.sort_values(["symbol", "trade_date"]).copy()
    grouped = df.groupby("symbol", group_keys=False)

    for window in [1, 3, 5, 10, 20]:
        df[f"ret_{window}"] = grouped["close"].pct_change(window)
    df["volatility_5"] = grouped["ret_1"].rolling(5).std().reset_index(level=0, drop=True)
    df["volatility_10"] = grouped["ret_1"].rolling(10).std().reset_index(level=0, drop=True)
    df["amount_ma5"] = grouped["amount"].rolling(5).mean().reset_index(level=0, drop=True)
    df["amount_ma20"] = grouped["amount"].rolling(20).mean().reset_index(level=0, drop=True)
    df["amount_ratio_5"] = df["amount"] / df["amount_ma5"]
    df["amount_ratio_20"] = df["amount"] / df["amount_ma20"]
    df["turnover_ma5"] = grouped["turnover_pct"].rolling(5).mean().reset_index(level=0, drop=True)
    df["turnover_ratio_5"] = df["turnover_pct"] / df["turnover_ma5"]
    high20 = grouped["high"].rolling(20).max().reset_index(level=0, drop=True)
    low20 = grouped["low"].rolling(20).min().reset_index(level=0, drop=True)
    spread20 = (high20 - low20).replace(0, pd.NA)
    df["range_pos_20"] = (df["close"] - low20) / spread20
    df["dist_high_20"] = df["close"] / high20 - 1
    df["dist_low_20"] = df["close"] / low20 - 1
    df["close_ma5"] = grouped["close"].rolling(5).mean().reset_index(level=0, drop=True)
    df["close_ma20"] = grouped["close"].rolling(20).mean().reset_index(level=0, drop=True)
    df["close_ma_ratio_5"] = df["close"] / df["close_ma5"]
    df["close_ma_ratio_20"] = df["close"] / df["close_ma20"]
    df["listing_days"] = grouped.cumcount() + 1
    df["low_liquidity_flag"] = (
        (df["amount"] < float(config["min_amount"]))
        | (df["amount_ma5"] < float(config["min_avg_amount_5"]))
    ).astype(int)
    df["near_limit_up"] = (df["pct_chg"] >= 9.5).astype(int)
    df["overheat_flag"] = ((df["ret_5"] > 0.15) & (df["range_pos_20"] > 0.9)).astype(int)
    return df


def add_cross_section_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ["ret_5", "ret_20", "amount_ratio_5", "turnover_pct", "volatility_5", "range_pos_20"]:
        df[f"{col}_xrank"] = df.groupby("trade_date")[col].rank(pct=True)

    industry_daily = (
        df.groupby(["trade_date", "industry"])
        .agg(
            industry_avg_ret_5=("ret_5", "mean"),
            industry_avg_ret_20=("ret_20", "mean"),
            industry_up_ratio=("ret_1", lambda s: (s > 0).mean()),
            industry_strong_5pct_ratio=("ret_5", lambda s: (s >= 0.05).mean()),
            industry_amount_ratio_5=("amount_ratio_5", "mean"),
            industry_stock_count=("symbol", "count"),
        )
        .reset_index()
    )
    for col in ["industry_avg_ret_5", "industry_up_ratio", "industry_amount_ratio_5"]:
        industry_daily[f"{col}_xrank"] = industry_daily.groupby("trade_date")[col].rank(pct=True)
    industry_daily["industry_strength_score"] = industry_daily[
        ["industry_avg_ret_5_xrank", "industry_up_ratio_xrank", "industry_amount_ratio_5_xrank"]
    ].mean(axis=1)
    df = df.merge(industry_daily, on=["trade_date", "industry"], how="left")
    df["stock_vs_industry_ret_5"] = df["ret_5"] - df["industry_avg_ret_5"]
    df["industry_sample_too_small"] = (df["industry_stock_count"] < 3).astype(int)
    return df


def build_trade_calendar(df: pd.DataFrame) -> list[pd.Timestamp]:
    return sorted(df["trade_date"].dropna().unique())


def add_future_labels(df: pd.DataFrame, calendar: list[pd.Timestamp], config: dict[str, Any]) -> pd.DataFrame:
    df = df.sort_values(["symbol", "trade_date"]).copy()
    cal_index = {date: idx for idx, date in enumerate(calendar)}
    lookup = df.set_index(["symbol", "trade_date"])[["open", "high", "low", "close", "pct_chg"]].to_dict("index")

    buy_cost = float(config["commission_rate"]) + float(config.get("transfer_fee_rate", 0))
    sell_cost = float(config["commission_rate"]) + float(config.get("transfer_fee_rate", 0)) + float(config["stamp_tax_rate"])
    buy_slippage = float(config["buy_slippage_rate"])
    sell_slippage = float(config["sell_slippage_rate"])
    holding_days = int(config["holding_trade_days"])
    allow_exit_delay = bool(config.get("allow_exit_delay", True))

    records: list[dict[str, Any]] = []
    for row in df[["symbol", "trade_date"]].itertuples(index=False):
        symbol = row.symbol
        trade_date = row.trade_date
        idx = cal_index.get(trade_date)
        result: dict[str, Any] = {
            "entry_trade_date": pd.NaT,
            "exit_trade_date": pd.NaT,
            "actual_exit_trade_date": pd.NaT,
            "entry_price": math.nan,
            "exit_price": math.nan,
            "gross_future_5_return": math.nan,
            "future_5_return": math.nan,
            "actual_future_5_return": math.nan,
            "tradable_at_entry": False,
            "tradable_at_exit": False,
            "limit_up_at_entry": False,
            "limit_down_during_holding": False,
            "suspended_during_holding": False,
            "forced_exit_delay_days": 0,
            "buy_cost_rate": buy_cost,
            "sell_cost_rate": sell_cost,
            "buy_slippage_rate": buy_slippage,
            "sell_slippage_rate": sell_slippage,
        }
        if idx is None or idx + holding_days + 1 >= len(calendar):
            records.append(result)
            continue
        entry_date = calendar[idx + 1]
        exit_date = calendar[idx + holding_days + 1]
        result["entry_trade_date"] = entry_date
        result["exit_trade_date"] = exit_date
        entry_bar = lookup.get((symbol, entry_date))
        if not entry_bar:
            result["suspended_during_holding"] = True
            records.append(result)
            continue
        limit_up_at_entry = bool(entry_bar.get("pct_chg", 0) >= 9.5)
        result["limit_up_at_entry"] = limit_up_at_entry
        result["entry_price"] = entry_bar["open"]
        if pd.isna(entry_bar["open"]) or limit_up_at_entry:
            records.append(result)
            continue
        result["tradable_at_entry"] = True

        exit_bar = lookup.get((symbol, exit_date))
        actual_exit_date = exit_date
        delay = 0
        if exit_bar and exit_bar.get("pct_chg", 0) <= -9.5:
            result["limit_down_during_holding"] = True
            exit_bar = None
        if exit_bar is None and allow_exit_delay:
            for next_idx in range(idx + holding_days + 2, len(calendar)):
                candidate_date = calendar[next_idx]
                candidate_bar = lookup.get((symbol, candidate_date))
                if candidate_bar and candidate_bar.get("pct_chg", 0) > -9.5 and pd.notna(candidate_bar.get("open")):
                    exit_bar = candidate_bar
                    actual_exit_date = candidate_date
                    delay = next_idx - (idx + holding_days + 1)
                    break
        if exit_bar is None or pd.isna(exit_bar.get("open")):
            result["suspended_during_holding"] = True
            records.append(result)
            continue
        result["tradable_at_exit"] = True
        result["actual_exit_trade_date"] = actual_exit_date
        result["forced_exit_delay_days"] = delay
        result["exit_price"] = exit_bar["open"]
        gross = result["exit_price"] / result["entry_price"] - 1
        net = gross - buy_cost - sell_cost - buy_slippage - sell_slippage
        result["gross_future_5_return"] = gross
        result["future_5_return"] = net
        result["actual_future_5_return"] = net
        records.append(result)

    label_df = pd.DataFrame(records)
    out = pd.concat([df.reset_index(drop=True), label_df], axis=1)
    valid = out["future_5_return"].notna()
    out["daily_stock_count"] = out.groupby("trade_date")["future_5_return"].transform("count")
    out["future_5_return_rank"] = pd.NA
    out.loc[valid, "future_5_return_rank"] = out[valid].groupby("trade_date")["future_5_return"].rank(
        method="first", ascending=False
    )
    rank_numeric = pd.to_numeric(out["future_5_return_rank"], errors="coerce")
    denominator = (out["daily_stock_count"] - 1).replace(0, pd.NA)
    out["future_5_return_rank_pct"] = 1 - (rank_numeric - 1) / denominator
    out["label_top10"] = (rank_numeric <= 10).astype("Int64")
    out["label_top30"] = (rank_numeric <= 30).astype("Int64")
    out["label_top50"] = (rank_numeric <= 50).astype("Int64")
    out["label_top1pct"] = (out["future_5_return_rank_pct"] >= 0.99).astype("Int64")
    out["label_top2pct"] = (out["future_5_return_rank_pct"] >= 0.98).astype("Int64")
    out["label_top5pct"] = (out["future_5_return_rank_pct"] >= 0.95).astype("Int64")
    out["relative_strong_label"] = out["label_top5pct"]
    out["absolute_strong_label"] = (out["future_5_return"] >= 0.10).astype("Int64")
    out["label_direction"] = (out["future_5_return"] > 0).astype("Int64")
    return out


def build_market_features(stock_df: pd.DataFrame) -> pd.DataFrame:
    market = (
        stock_df.groupby("trade_date")
        .agg(
            market_up_ratio=("ret_1", lambda s: (s > 0).mean()),
            market_avg_pct_chg=("pct_chg", "mean"),
            market_median_pct_chg=("pct_chg", "median"),
            market_strong_5pct_ratio=("ret_5", lambda s: (s >= 0.05).mean()),
            market_amount_ratio_5=("amount_ratio_5", "mean"),
            market_volatility_5=("ret_1", "std"),
            future_market_10pct_density=("future_5_return", lambda s: (s >= 0.10).mean()),
            market_top5pct_avg_return=("future_5_return_rank_pct", lambda s: stock_df.loc[s.index, "future_5_return"][s >= 0.95].mean()),
            market_top30_avg_return=("label_top30", lambda s: stock_df.loc[s.index, "future_5_return"][s.astype(bool)].mean()),
            market_positive_ratio=("future_5_return", lambda s: (s > 0).mean()),
            market_extreme_return_density_5pct=("future_5_return", lambda s: (s >= 0.05).mean()),
            market_extreme_return_density_10pct=("future_5_return", lambda s: (s >= 0.10).mean()),
        )
        .reset_index()
        .sort_values("trade_date")
    )
    market["market_10pct_density_ma5_lag1"] = market["future_market_10pct_density"].shift(1).rolling(5).mean()
    market["market_10pct_density_ma10_lag1"] = market["future_market_10pct_density"].shift(1).rolling(10).mean()
    q40 = market["future_market_10pct_density"].expanding().quantile(0.4).shift(1)
    q70 = market["future_market_10pct_density"].expanding().quantile(0.7).shift(1)
    market["market_opportunity_label"] = 1
    market.loc[market["future_market_10pct_density"] < q40, "market_opportunity_label"] = 0
    market.loc[market["future_market_10pct_density"] >= q70, "market_opportunity_label"] = 2
    return market


def write_quality_report(stock_df: pd.DataFrame, market_df: pd.DataFrame, path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    valid = stock_df["future_5_return"].notna()
    daily_counts = stock_df.groupby("trade_date")["symbol"].count()
    rank_min = stock_df[valid].groupby("trade_date")["future_5_return_rank_pct"].min()
    rank_max = stock_df[valid].groupby("trade_date")["future_5_return_rank_pct"].max()
    top30_counts = stock_df[valid].groupby("trade_date")["label_top30"].sum()
    lines = [
        "# Data Quality Report",
        "",
        f"- stocks: {stock_df['symbol'].nunique()}",
        f"- trade_days: {stock_df['trade_date'].nunique()}",
        f"- rows: {len(stock_df)}",
        f"- date_range: {stock_df['trade_date'].min().date()} -> {stock_df['trade_date'].max().date()}",
        f"- future_5_return_missing_ratio: {stock_df['future_5_return'].isna().mean():.4f}",
        f"- untradable_entry_ratio: {(~stock_df['tradable_at_entry'].astype(bool)).mean():.4f}",
        f"- delayed_exit_count: {int((stock_df['forced_exit_delay_days'] > 0).sum())}",
        f"- limit_up_at_entry_ratio: {stock_df['limit_up_at_entry'].mean():.4f}",
        f"- suspended_or_missing_holding_ratio: {stock_df['suspended_during_holding'].mean():.4f}",
        f"- future_5_return_min: {stock_df['future_5_return'].min():.4f}",
        f"- future_5_return_max: {stock_df['future_5_return'].max():.4f}",
        f"- rank_pct_min_min: {rank_min.min():.4f}",
        f"- rank_pct_max_max: {rank_max.max():.4f}",
        f"- top30_count_median: {top30_counts.median():.1f}",
        f"- daily_sample_count_min: {daily_counts.min()}",
        f"- daily_sample_count_median: {daily_counts.median():.1f}",
        f"- daily_sample_count_max: {daily_counts.max()}",
        f"- market_rows: {len(market_df)}",
        "",
        "## Config",
        "",
        "```json",
        json.dumps(config, ensure_ascii=False, indent=2, default=str),
        "```",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def get_signal_known_features(df: pd.DataFrame) -> list[str]:
    features: list[str] = []
    for col in df.columns:
        if col in MODEL_FORBIDDEN_COLUMNS:
            continue
        if col.startswith(MODEL_FORBIDDEN_PREFIXES):
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            features.append(col)
    return features


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-list", type=Path)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--backtest-config", type=Path, default=Path("skills/a-share-kline-return-modeling/configs/backtest.yaml"))
    args = parser.parse_args()

    config = load_config(args.backtest_config)
    stock_list_path = args.stock_list or Path(config["stock_list_path"])
    source_dir = args.source_dir or Path(config["stock_daily_k_dir"])
    output_dir = args.output_dir or Path("skills/a-share-kline-return-modeling/data")

    stock_list = read_stock_list(stock_list_path)
    raw = load_all_daily_k(source_dir, stock_list)
    featured = add_stock_features(raw, config)
    featured = add_cross_section_features(featured)
    calendar = build_trade_calendar(featured)
    stock_features = add_future_labels(featured, calendar, config)
    market_features = build_market_features(stock_features)

    output_dir.mkdir(parents=True, exist_ok=True)
    stock_output = Path(config.get("stock_features_output_path", output_dir / "clean_stock_features.csv"))
    market_output = Path(config.get("market_features_output_path", output_dir / "clean_market_features.csv"))
    stock_features.to_csv(stock_output, index=False, encoding="utf-8-sig")
    market_features.to_csv(market_output, index=False, encoding="utf-8-sig")

    report_path = Path(config.get("data_quality_report_path", "skills/a-share-kline-return-modeling/outputs/evaluation/data_quality_report.md"))
    write_quality_report(stock_features, market_features, report_path, config)
    summary_path = Path(config.get("build_summary_output_path", "skills/a-share-kline-return-modeling/outputs/evaluation/build_features_summary.json"))
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "stock_rows": len(stock_features),
                "market_rows": len(market_features),
                "stock_output": str(stock_output),
                "market_output": str(market_output),
                "data_quality_report": str(report_path),
                "signal_known_features": get_signal_known_features(stock_features),
                "forbidden_prefixes": MODEL_FORBIDDEN_PREFIXES,
                "forbidden_columns": sorted(MODEL_FORBIDDEN_COLUMNS),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"wrote {stock_output}")
    print(f"wrote {market_output}")
    print(f"wrote {report_path}")


if __name__ == "__main__":
    main()
