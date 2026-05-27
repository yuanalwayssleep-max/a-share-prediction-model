#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = SKILL_DIR / "data" / "指数日K文件" / "00_核心指数日K.csv"
DEFAULT_FEATURE_OUTPUT = ROOT / "skills" / "a-share-kline-return-modeling" / "outputs" / "00_核心指数特征.csv"

INDEX_CODES = {
    "上证指数": "sh.000001",
    "深证成指": "sz.399001",
    "沪深300": "sh.000300",
    "中证500": "sh.000905",
    "中证1000": "sh.000852",
    "创业板指": "sz.399006",
}

OUTPUT_FIELDS = ["指数名称", "date", "code", "open", "high", "low", "close", "preclose", "volume", "amount", "pctChg"]
BAOSTOCK_FIELDS = "date,code,open,high,low,close,preclose,volume,amount,pctChg"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="爬取核心指数日K，并可生成5日模型指数特征")
    parser.add_argument("--start-date", default="2025-01-01", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", default=date.today().isoformat(), help="结束日期 YYYY-MM-DD")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="输出CSV路径")
    parser.add_argument("--build-features", action="store_true", help="同步生成模型所需指数特征")
    parser.add_argument("--feature-output", default=str(DEFAULT_FEATURE_OUTPUT), help="指数特征输出CSV")
    return parser.parse_args()


def fetch_one_index(bs: Any, name: str, code: str, start_date: str, end_date: str) -> list[dict[str, str]]:
    rs = bs.query_history_k_data_plus(
        code,
        BAOSTOCK_FIELDS,
        start_date=start_date,
        end_date=end_date,
        frequency="d",
        adjustflag="3",
    )
    if rs.error_code != "0":
        raise RuntimeError(f"{name} {code} 抓取失败: {rs.error_code} {rs.error_msg}")
    rows: list[dict[str, str]] = []
    fields = BAOSTOCK_FIELDS.split(",")
    while rs.next():
        row = dict(zip(fields, rs.get_row_data()))
        rows.append({"指数名称": name, **row})
    if not rows:
        raise RuntimeError(f"{name} {code} 无日K数据")
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    tmp_path.replace(path)


def safe_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def build_index_features(daily_df: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for name, group in daily_df.groupby("指数名称", sort=False):
        g = group.copy()
        g["日期"] = pd.to_datetime(g["date"], errors="coerce")
        for col in ["open", "high", "low", "close", "preclose", "volume", "amount", "pctChg"]:
            g[col] = safe_num(g[col])
        g = g.sort_values("日期").reset_index(drop=True)
        close = g["close"]
        amount = g["amount"]
        ret = close.pct_change()
        prefix = f"{name}_"

        feature = pd.DataFrame({"日期": g["日期"]})
        feature[f"{prefix}1日涨跌幅"] = g["pctChg"] / 100.0
        for n in [3, 5, 10, 20]:
            feature[f"{prefix}{n}日涨跌幅"] = close.pct_change(n)
        for n in [5, 10, 20]:
            ma = close.rolling(n).mean()
            feature[f"{prefix}收盘均线比_{n}"] = close / ma - 1
            feature[f"{prefix}成交额比_{n}"] = amount / amount.rolling(n).mean() - 1
            feature[f"{prefix}波动率_{n}"] = ret.rolling(n).std()
        feature[f"{prefix}20日位置"] = (close - close.rolling(20).min()) / (
            close.rolling(20).max() - close.rolling(20).min()
        ).replace(0, np.nan)
        frames.append(feature)

    if not frames:
        raise RuntimeError("指数日K为空，无法生成指数特征")

    out = frames[0]
    for frame in frames[1:]:
        out = out.merge(frame, on="日期", how="outer")
    out = out.sort_values("日期").reset_index(drop=True)

    if {"沪深300_5日涨跌幅", "中证1000_5日涨跌幅"}.issubset(out.columns):
        out["中证1000强于沪深300_5日"] = out["中证1000_5日涨跌幅"] - out["沪深300_5日涨跌幅"]
    if {"中证500_5日涨跌幅", "沪深300_5日涨跌幅"}.issubset(out.columns):
        out["中证500强于沪深300_5日"] = out["中证500_5日涨跌幅"] - out["沪深300_5日涨跌幅"]
    if {"创业板指_5日涨跌幅", "沪深300_5日涨跌幅"}.issubset(out.columns):
        out["创业板强于沪深300_5日"] = out["创业板指_5日涨跌幅"] - out["沪深300_5日涨跌幅"]
    return out


def write_feature_csv(path: Path, daily_rows: list[dict[str, str]]) -> None:
    daily_df = pd.DataFrame(daily_rows)
    feature_df = build_index_features(daily_df)
    feature_df["日期"] = pd.to_datetime(feature_df["日期"], errors="coerce").dt.strftime("%Y-%m-%d")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    feature_df.to_csv(tmp_path, index=False, encoding="utf-8-sig")
    tmp_path.replace(path)
    print(f"saved core_index_features={len(feature_df)} cols={len(feature_df.columns)} output={path}")


def main() -> None:
    args = parse_args()
    try:
        import baostock as bs
    except Exception as exc:
        raise SystemExit(f"缺少 baostock，先安装依赖: {exc}") from exc

    login = bs.login()
    if login.error_code != "0":
        raise SystemExit(f"baostock login failed: {login.error_code} {login.error_msg}")
    try:
        rows: list[dict[str, str]] = []
        for name, code in INDEX_CODES.items():
            rows.extend(fetch_one_index(bs, name, code, args.start_date, args.end_date))
    finally:
        bs.logout()

    output = Path(args.output).resolve()
    write_csv(output, rows)
    print(f"saved core_index_daily_k={len(rows)} output={output}")
    if args.build_features:
        write_feature_csv(Path(args.feature_output).resolve(), rows)


if __name__ == "__main__":
    main()
