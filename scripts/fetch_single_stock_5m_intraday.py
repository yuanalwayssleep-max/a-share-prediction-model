#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = ROOT / "outputs" / "single_stock_intraday"

KLINE_FIELDS = ["时间", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "振幅", "涨跌幅", "涨跌额", "换手率"]
INTRADAY_FIELDS = ["时间", "最新价", "均价", "最高", "最低", "成交量", "成交额", "最新价_格式化"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="爬取单个股票的5分钟K线，并生成兼容分时线")
    parser.add_argument("--symbol", required=True, help="股票代码，支持 600111 / sh600111 / sz000001 / bj430047")
    parser.add_argument("--start-date", default="2025-01-01", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", default="2099-12-31", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--five-min-limit", type=int, default=500, help="5分钟K条数，默认500")
    parser.add_argument("--intraday-days", type=int, default=1, help="分时兼容输出天数，默认1")
    parser.add_argument("--ndays", type=int, default=1, help="东方财富分时天数：1=当日，5=最近5日；默认1")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT_DIR), help="输出目录")
    return parser.parse_args()


def normalize_symbol(symbol: str) -> tuple[str, str]:
    value = symbol.strip().lower()
    if value.startswith(("sh", "sz", "bj")):
        prefix = value[:2]
        code = value[2:]
    else:
        code = value
        if code.startswith(("5", "6", "9")):
            prefix = "sh"
        elif code.startswith(("0", "2", "3")):
            prefix = "sz"
        elif code.startswith(("4", "8")) or code.startswith("92"):
            prefix = "bj"
        else:
            raise ValueError(f"无法从代码推断市场前缀: {symbol}")
    if not code.isdigit():
        raise ValueError(f"股票代码必须为数字: {symbol}")
    return prefix, code.zfill(6)


def to_baostock_symbol(symbol: str) -> tuple[str, str]:
    prefix, code = normalize_symbol(symbol)
    return f"{prefix}.{code}", f"{prefix}{code}"


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def eastmoney_secid(prefix: str, code: str) -> str:
    if prefix == "sh":
        market = "1"
    elif prefix == "sz":
        market = "0"
    elif prefix == "bj":
        market = "0"
    else:
        raise ValueError(f"不支持的市场前缀: {prefix}")
    return f"{market}.{code}"


EASTMONEY_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json,text/plain,*/*",
    "Connection": "close",
}


def eastmoney_sleep() -> None:
    time.sleep(random.uniform(2.0, 3.0))


def rest_after_batch(index: int, batch_size: int = 20, sleep_seconds: float = 10.0) -> None:
    if index > 0 and index % batch_size == 0:
        time.sleep(sleep_seconds)


def request_json(url: str, params: dict[str, str], retries: int = 10) -> dict[str, Any]:
    urls = candidate_urls(url)
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        for current_url in urls:
            try:
                import requests

                response = requests.get(
                    current_url,
                    params=params,
                    headers=EASTMONEY_HEADERS,
                    timeout=15,
                )
                response.raise_for_status()
                return response.json()
            except Exception as exc:
                last_error = exc
                try:
                    return curl_json(current_url, params)
                except Exception as curl_exc:
                    last_error = curl_exc
        if attempt < retries:
            eastmoney_sleep()
    raise RuntimeError(f"东方财富接口请求失败: {last_error}")


def candidate_urls(url: str) -> list[str]:
    urls = [url]
    replacements = [
        ("push2.eastmoney.com", "push2delay.eastmoney.com"),
        ("push2.eastmoney.com", "push2his.eastmoney.com"),
        ("push2his.eastmoney.com", "push2delay.eastmoney.com"),
        ("push2his.eastmoney.com", "push2.eastmoney.com"),
    ]
    for old, new in replacements:
        if old in url:
            candidate = url.replace(old, new)
            if candidate not in urls:
                urls.append(candidate)
    return urls


def curl_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    query = urlencode(params)
    completed = subprocess.run(
        [
            "curl",
            "-sS",
            "-L",
            "--http1.1",
            "--connect-timeout",
            "10",
            "--max-time",
            "20",
            "-H",
            f"User-Agent: {EASTMONEY_HEADERS['User-Agent']}",
            "-H",
            f"Referer: {EASTMONEY_HEADERS['Referer']}",
            "-H",
            f"Accept: {EASTMONEY_HEADERS['Accept']}",
            f"{url}?{query}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def fetch_eastmoney_minute_k(prefix: str, code: str, start_date: str, end_date: str, klt: int) -> list[dict[str, str]]:
    payload = request_json(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        {
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "beg": start_date.replace("-", ""),
            "end": end_date.replace("-", ""),
            "rtntype": "6",
            "secid": eastmoney_secid(prefix, code),
            "klt": str(klt),
            "fqt": "0",
            "_": str(int(time.time() * 1000)),
        },
    )
    data = payload.get("data") or {}
    klines = data.get("klines") or []
    rows: list[dict[str, str]] = []
    for item in klines:
        parts = str(item).split(",")
        if len(parts) < 11:
            continue
        rows.append(
            {
                "时间": parts[0],
                "开盘": parts[1],
                "收盘": parts[2],
                "最高": parts[3],
                "最低": parts[4],
                "成交量": parts[5],
                "成交额": parts[6],
                "振幅": parts[7],
                "涨跌幅": parts[8],
                "涨跌额": parts[9],
                "换手率": parts[10],
            }
        )
    return rows


def fetch_eastmoney_intraday(prefix: str, code: str, ndays: int) -> list[dict[str, str]]:
    trends = fetch_eastmoney_trends(prefix, code, ndays)
    rows: list[dict[str, str]] = []
    for item in trends:
        parts = str(item).split(",")
        if len(parts) < 8:
            continue
        rows.append(
            {
                "时间": parts[0],
                "最新价": parts[2],
                "均价": parts[7],
                "最高": parts[3],
                "最低": parts[4],
                "成交量": parts[5],
                "成交额": parts[6],
                "最新价_格式化": parts[2],
            }
        )
    return rows


def fetch_eastmoney_trends(prefix: str, code: str, ndays: int) -> list[str]:
    payload = request_json(
        "https://push2.eastmoney.com/api/qt/stock/trends2/get",
        {
            "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "secid": eastmoney_secid(prefix, code),
            "ndays": str(ndays),
            "iscr": "0",
            "iscca": "0",
            "_": str(int(time.time() * 1000)),
        },
    )
    data = payload.get("data") or {}
    return data.get("trends") or []


def trends_as_1m(trends: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in trends:
        parts = str(item).split(",")
        if len(parts) < 8:
            continue
        rows.append(
            {
                "时间": parts[0],
                "开盘": parts[1],
                "收盘": parts[2],
                "最高": parts[3],
                "最低": parts[4],
                "成交量": parts[5],
                "成交额": parts[6],
                "振幅": "0",
                "涨跌幅": "0",
                "涨跌额": "0",
                "换手率": "0",
            }
        )
    return rows


def trends_as_intraday(trends: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in trends:
        parts = str(item).split(",")
        if len(parts) < 8:
            continue
        rows.append(
            {
                "时间": parts[0],
                "最新价": parts[2],
                "均价": parts[7],
                "最高": parts[3],
                "最低": parts[4],
                "成交量": parts[5],
                "成交额": parts[6],
                "最新价_格式化": parts[2],
            }
        )
    return rows


def aggregate_5m_from_1m(rows_1m: list[dict[str, str]]) -> list[dict[str, str]]:
    if not rows_1m:
        return []

    df = pd.DataFrame(rows_1m)
    df["时间_dt"] = pd.to_datetime(df["时间"], errors="coerce")
    for col in ["开盘", "收盘", "最高", "最低", "成交量", "成交额"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["时间_dt", "开盘", "收盘", "最高", "最低"]).copy()
    if df.empty:
        return []

    df["bucket"] = df["时间_dt"].dt.floor("5min")
    grouped = df.groupby("bucket", sort=True)
    agg = grouped.agg(
        开盘=("开盘", "first"),
        收盘=("收盘", "last"),
        最高=("最高", "max"),
        最低=("最低", "min"),
        成交量=("成交量", "sum"),
        成交额=("成交额", "sum"),
    ).reset_index()
    agg["prev_close"] = agg["收盘"].shift(1)
    agg["振幅"] = (agg["最高"] - agg["最低"]) / agg["prev_close"] * 100
    agg["涨跌幅"] = (agg["收盘"] / agg["prev_close"] - 1) * 100
    agg["涨跌额"] = agg["收盘"] - agg["prev_close"]
    agg[["振幅", "涨跌幅", "涨跌额"]] = agg[["振幅", "涨跌幅", "涨跌额"]].fillna(0)

    rows: list[dict[str, str]] = []
    for _, row in agg.iterrows():
        rows.append(
            {
                "时间": row["bucket"].strftime("%Y-%m-%d %H:%M"),
                "开盘": f"{row['开盘']:.2f}",
                "收盘": f"{row['收盘']:.2f}",
                "最高": f"{row['最高']:.2f}",
                "最低": f"{row['最低']:.2f}",
                "成交量": f"{row['成交量']:.0f}",
                "成交额": f"{row['成交额']:.2f}",
                "振幅": f"{row['振幅']:.2f}",
                "涨跌幅": f"{row['涨跌幅']:.2f}",
                "涨跌额": f"{row['涨跌额']:.2f}",
                "换手率": "0",
            }
        )
    return rows


def fetch_5m_k(bs: Any, bs_symbol: str, start_date: str, end_date: str, limit: int) -> list[dict[str, str]]:
    rs = bs.query_history_k_data_plus(
        bs_symbol,
        "date,time,open,close,high,low,volume,amount",
        start_date=start_date,
        end_date=end_date,
        frequency="5",
        adjustflag="2",
    )
    if rs.error_code != "0":
        raise RuntimeError(f"baostock 5min query failed: {rs.error_code} {rs.error_msg}")

    raw_rows: list[list[str]] = []
    while rs.next():
        raw_rows.append(rs.get_row_data())
    raw_rows = raw_rows[-limit:]

    rows: list[dict[str, str]] = []
    prev_close: float | None = None
    for item in raw_rows:
        trade_date, time_code, open_, close, high, low, volume, amount = item
        ts = f"{trade_date} {time_code[8:10]}:{time_code[10:12]}"
        high_f = safe_float(high)
        low_f = safe_float(low)
        close_f = safe_float(close)
        amplitude = ((high_f - low_f) / prev_close * 100) if prev_close else 0.0
        pct_chg = ((close_f / prev_close - 1) * 100) if prev_close else 0.0
        change = close_f - prev_close if prev_close else 0.0
        rows.append(
            {
                "时间": ts,
                "开盘": open_,
                "收盘": close,
                "最高": high,
                "最低": low,
                "成交量": volume,
                "成交额": amount,
                "振幅": f"{amplitude:.2f}",
                "涨跌幅": f"{pct_chg:.2f}",
                "涨跌额": f"{change:.2f}",
                "换手率": "0",
            }
        )
        prev_close = close_f
    return rows


def build_intraday_from_5m(rows_5m: list[dict[str, str]], intraday_days: int) -> list[dict[str, str]]:
    selected = rows_5m[-48 * intraday_days :]
    intraday_rows: list[dict[str, str]] = []
    cumulative_amount = 0.0
    cumulative_volume = 0.0
    for row in selected:
        amount = safe_float(row["成交额"])
        volume = safe_float(row["成交量"])
        close = safe_float(row["收盘"])
        cumulative_amount += amount
        cumulative_volume += volume
        avg_price = (cumulative_amount / cumulative_volume) if cumulative_volume else close
        intraday_rows.append(
            {
                "时间": row["时间"],
                "最新价": row["收盘"],
                "均价": f"{avg_price:.3f}",
                "最高": row["最高"],
                "最低": row["最低"],
                "成交量": row["成交量"],
                "成交额": row["成交额"],
                "最新价_格式化": row["收盘"],
            }
        )
    return intraday_rows


def main() -> None:
    args = parse_args()
    prefix, code = normalize_symbol(args.symbol)
    bs_symbol, slug = f"{prefix}.{code}", f"{prefix}{code}"
    out_dir = Path(args.output_dir).resolve()

    trends = fetch_eastmoney_trends(prefix, code, args.ndays)
    rows_1m = trends_as_1m(trends)
    rows_5m = aggregate_5m_from_1m(rows_1m)[-args.five_min_limit :]
    intraday_rows = trends_as_intraday(trends)

    if not rows_5m:
        try:
            import baostock as bs

            login = bs.login()
            if login.error_code != "0":
                raise RuntimeError(f"baostock login failed: {login.error_code} {login.error_msg}")
            try:
                rows_5m = fetch_5m_k(bs, bs_symbol, args.start_date, args.end_date, args.five_min_limit)
            finally:
                bs.logout()
        except Exception as exc:
            print(f"baostock 5分钟K失败，继续尝试东方财富历史分钟: {exc}")

    if not rows_5m:
        rows_5m = fetch_eastmoney_minute_k(prefix, code, args.start_date, args.end_date, 5)[-args.five_min_limit :]
    if not rows_1m:
        raise SystemExit(f"东方财富分时无数据: {slug}")
    if not rows_5m:
        raise SystemExit(f"5分钟K无数据: {slug}")
    if not intraday_rows:
        intraday_rows = build_intraday_from_5m(rows_5m, args.intraday_days)

    five_min_path = out_dir / f"eastmoney_{slug}_5min_k.csv"
    intraday_path = out_dir / f"eastmoney_{slug}_intraday.csv"
    one_min_path = out_dir / f"eastmoney_{slug}_1min_k.csv"
    write_csv(five_min_path, KLINE_FIELDS, rows_5m)
    write_csv(one_min_path, KLINE_FIELDS, rows_1m)
    write_csv(intraday_path, INTRADAY_FIELDS, intraday_rows)

    print(
        f"saved symbol={slug} 5min_k={len(rows_5m)} 1min_k={len(rows_1m)} "
        f"intraday={len(intraday_rows)} output_dir={out_dir}"
    )


if __name__ == "__main__":
    main()
