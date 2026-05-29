#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import os
import random
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = SKILL_DIR / "data" / "行业日K文件" / "申万行业日K"
DEFAULT_INDUSTRY_LIST_OUTPUT = SKILL_DIR / "data" / "行业日K文件" / "申万行业清单.csv"

DAILY_FIELDS = [
    "trade_date",
    "ts_code",
    "name",
    "level",
    "open",
    "low",
    "high",
    "close",
    "change",
    "pct_change",
    "vol",
    "amount",
    "pe",
    "pb",
    "float_mv",
    "total_mv",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="使用 Tushare 抓取申万行业指数历史日K")
    parser.add_argument("--start-date", default="2023-01-01", help="开始日期 YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--end-date", default=date.today().isoformat(), help="结束日期 YYYY-MM-DD 或 YYYYMMDD")
    parser.add_argument("--src", default="SW2021", help="行业分类来源，默认 SW2021")
    parser.add_argument(
        "--levels",
        default="L1",
        help="行业级别，逗号分隔；默认 L1，可用 L1,L2,L3",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="行业日K输出目录")
    parser.add_argument("--industry-list-output", default=str(DEFAULT_INDUSTRY_LIST_OUTPUT), help="行业清单快照输出路径")
    parser.add_argument("--mode", choices=["missing", "stale", "all"], default="stale", help="更新模式")
    parser.add_argument("--stale-before", default="", help="本地最后日期早于该日期才更新；默认等于 end-date")
    parser.add_argument("--max-industries", type=int, default=0, help="最多处理多少个行业；0表示不限制")
    parser.add_argument("--retries", type=int, default=3, help="单个行业失败重试次数")
    parser.add_argument("--sleep-seconds", type=float, default=0.35, help="每个行业之间停顿秒数")
    parser.add_argument("--retry-sleep-seconds", type=float, default=2.0, help="失败重试基础停顿秒数")
    parser.add_argument("--limit", type=int, default=0, help="每个行业最多保留多少根日K；0表示不截断")
    parser.add_argument("--token", default="", help="Tushare token；建议改用环境变量 TUSHARE_TOKEN")
    parser.add_argument(
        "--http-url",
        default=os.environ.get("TUSHARE_HTTP_URL", "http://jiaoch.site"),
        help="Tushare API 地址；默认读取 TUSHARE_HTTP_URL，否则使用 http://jiaoch.site",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印待抓取行业，不写文件")
    return parser.parse_args()


def compact_date(value: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError("日期不能为空")
    parsed = datetime.strptime(text.replace("-", ""), "%Y%m%d")
    return parsed.strftime("%Y%m%d")


def display_date(value: str) -> str:
    return datetime.strptime(compact_date(value), "%Y%m%d").strftime("%Y-%m-%d")


def sanitize_filename(value: str) -> str:
    banned = '\\/:*?"<>|'
    return "".join("_" if ch in banned else ch for ch in str(value).strip()) or "未命名"


def output_path(output_dir: Path, ts_code: str, name: str, level: str) -> Path:
    return output_dir / f"{ts_code}_{sanitize_filename(name)}_{level}_daily_k.csv"


def init_tushare(token: str, http_url: str) -> Any:
    try:
        import tushare as ts
    except Exception as exc:
        raise SystemExit(f"缺少 tushare，先安装依赖: {exc}") from exc

    token = token or os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise SystemExit("缺少 Tushare token，请通过 --token 或环境变量 TUSHARE_TOKEN 传入。")
    if not http_url:
        raise SystemExit("缺少 Tushare API 地址，请通过 --http-url 或环境变量 TUSHARE_HTTP_URL 传入。")
    pro = ts.pro_api(token)
    pro._DataApi__token = token
    pro._DataApi__http_url = http_url
    return pro


def is_token_error(exc: Exception) -> bool:
    message = str(exc)
    return "token" in message.lower() or "TOKEN" in message or "token不对" in message


def fetch_industries(pro: Any, src: str, levels: list[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for level in levels:
        df = pro.index_classify(src=src, level=level)
        if df is None or df.empty:
            continue
        df = df.copy()
        df["level"] = level
        frames.append(df)
    if not frames:
        raise RuntimeError(f"没有取到行业分类: src={src} levels={','.join(levels)}")

    industries = pd.concat(frames, ignore_index=True)
    code_col = "index_code" if "index_code" in industries.columns else "ts_code"
    name_col = "industry_name" if "industry_name" in industries.columns else "name"
    industries = industries.rename(columns={code_col: "ts_code", name_col: "name"})
    required = ["ts_code", "name", "level"]
    missing = [col for col in required if col not in industries.columns]
    if missing:
        raise RuntimeError(f"行业分类缺少字段: {','.join(missing)}")
    industries = industries[industries["ts_code"].notna()].copy()
    industries["ts_code"] = industries["ts_code"].astype(str).str.strip()
    industries["name"] = industries["name"].astype(str).str.strip()
    industries["level"] = industries["level"].astype(str).str.strip()
    industries = industries.drop_duplicates(["ts_code", "level"]).sort_values(["level", "ts_code"])
    return industries.reset_index(drop=True)


def write_industry_list(path: Path, industries: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    industries.to_csv(tmp_path, index=False, encoding="utf-8-sig")
    tmp_path.replace(path)


def read_last_trade_date(path: Path) -> str:
    if not path.exists() or path.stat().st_size <= 64:
        return ""
    try:
        df = pd.read_csv(path, usecols=["trade_date"], encoding="utf-8-sig")
    except Exception:
        return ""
    if df.empty:
        return ""
    dates = pd.to_datetime(df["trade_date"], errors="coerce").dropna()
    if dates.empty:
        return ""
    return dates.max().strftime("%Y%m%d")


def should_update(path: Path, mode: str, stale_before: str) -> bool:
    if mode == "all":
        return True
    if not path.exists() or path.stat().st_size <= 64:
        return True
    if mode == "missing":
        return False
    last_date = read_last_trade_date(path)
    return not last_date or last_date < stale_before


def fetch_daily(pro: Any, ts_code: str, level: str, start_date: str, end_date: str, limit: int) -> pd.DataFrame:
    df = pro.sw_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
    if df is None or df.empty:
        raise RuntimeError("empty sw_daily rows")
    df = df.copy()
    for col in DAILY_FIELDS:
        if col not in df.columns:
            df[col] = ""
    df["level"] = df["level"].replace("", pd.NA).fillna(level)
    df = df[DAILY_FIELDS]
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["trade_date"]).sort_values("trade_date")
    if limit > 0:
        df = df.tail(limit)
    df["trade_date"] = df["trade_date"].dt.strftime("%Y-%m-%d")
    return df.reset_index(drop=True)


def validate_daily(df: pd.DataFrame) -> None:
    if df.empty:
        raise RuntimeError("empty daily rows")
    required = ["trade_date", "ts_code", "name", "open", "low", "high", "close", "pct_change"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise RuntimeError(f"missing columns: {','.join(missing)}")
    empty_required = [col for col in required if df[col].astype(str).str.strip().eq("").any()]
    if empty_required:
        raise RuntimeError(f"empty required fields: {','.join(empty_required)}")


def write_daily_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    tmp_path.replace(path)


def retry_sleep(base_seconds: float, attempt: int) -> None:
    time.sleep(base_seconds * attempt + random.uniform(0, min(1.0, base_seconds)))


def main() -> None:
    args = parse_args()
    start_date = compact_date(args.start_date)
    end_date = compact_date(args.end_date)
    stale_before = compact_date(args.stale_before or args.end_date)
    levels = [item.strip().upper() for item in args.levels.split(",") if item.strip()]
    if not levels:
        raise SystemExit("--levels 不能为空")
    if start_date > end_date:
        raise SystemExit("--start-date 不能晚于 --end-date")

    pro = init_tushare(args.token, args.http_url)
    try:
        industries = fetch_industries(pro, args.src, levels)
    except Exception as exc:
        if is_token_error(exc):
            raise SystemExit("Tushare token 校验失败，请确认 TUSHARE_TOKEN 是否正确且账号有对应接口权限。") from exc
        raise
    if args.max_industries > 0:
        industries = industries.head(args.max_industries).copy()

    output_dir = Path(args.output_dir).resolve()
    industry_list_output = Path(args.industry_list_output).resolve()
    write_industry_list(industry_list_output, industries)

    tasks: list[dict[str, str]] = []
    skipped = 0
    for item in industries.to_dict("records"):
        path = output_path(output_dir, item["ts_code"], item["name"], item["level"])
        if should_update(path, args.mode, stale_before):
            tasks.append({**item, "path": str(path), "last_trade_date": read_last_trade_date(path)})
        else:
            skipped += 1

    print(
        f"industries={len(industries)} src={args.src} levels={','.join(levels)} "
        f"range={display_date(start_date)}..{display_date(end_date)} mode={args.mode} "
        f"tasks={len(tasks)} skipped={skipped} output_dir={output_dir}"
    )
    print(f"saved industry_list={industry_list_output}")
    if args.dry_run:
        for item in tasks[:50]:
            print(f"dry-run update {item['ts_code']} {item['name']} {item['level']} last={item['last_trade_date'] or '-'}")
        if len(tasks) > 50:
            print(f"dry-run omitted={len(tasks) - 50}")
        return

    fetched = 0
    failures: list[dict[str, str]] = []
    for idx, item in enumerate(tasks, 1):
        ts_code = item["ts_code"]
        name = item["name"]
        level = item["level"]
        path = Path(item["path"])
        last_error = ""
        print(f"[{idx}/{len(tasks)}] {ts_code} {name} {level}", flush=True)
        for attempt in range(1, args.retries + 1):
            try:
                daily = fetch_daily(pro, ts_code, level, start_date, end_date, args.limit)
                validate_daily(daily)
                write_daily_csv(path, daily)
                fetched += 1
                break
            except Exception as exc:
                last_error = str(exc)
                if attempt < args.retries:
                    retry_sleep(args.retry_sleep_seconds, attempt)
        else:
            failures.append({"ts_code": ts_code, "name": name, "level": level, "error": last_error[:500]})

        if idx % 20 == 0 or idx == len(tasks):
            print(f"progress {idx}/{len(tasks)} fetched={fetched} failed={len(failures)}", flush=True)
        time.sleep(args.sleep_seconds)

    failed_path = output_dir.parent / "failed_industries_申万日K.csv"
    failed_path.parent.mkdir(parents=True, exist_ok=True)
    with failed_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["ts_code", "name", "level", "error"])
        writer.writeheader()
        writer.writerows(failures)

    print(
        f"done total={len(industries)} tasks={len(tasks)} fetched={fetched} skipped={skipped} "
        f"failed={len(failures)} failed_csv={failed_path}"
    )


if __name__ == "__main__":
    main()
