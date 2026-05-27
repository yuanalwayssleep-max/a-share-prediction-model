#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import random
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SYMBOLS_CSV = ROOT / "skills" / "a-share-kline-return-modeling" / "data" / "00_股票清单.csv"
DEFAULT_DAILY_DIR = SKILL_DIR / "data" / "单只股票日k"

DAILY_FIELDS = ["日期", "开盘", "收盘", "最高", "最低", "成交量", "成交额", "振幅", "涨跌幅", "涨跌额", "换手率"]
BAOSTOCK_FIELDS = "date,open,close,high,low,volume,amount,turn,pctChg"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量爬取多个股票的日K线")
    parser.add_argument("--symbols-csv", default=str(DEFAULT_SYMBOLS_CSV), help="股票清单CSV，至少包含 代码、名称")
    parser.add_argument("--output-dir", default=str(DEFAULT_DAILY_DIR), help="日K输出目录")
    parser.add_argument("--start-date", default="2025-01-01", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", default=date.today().isoformat(), help="结束日期 YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=260, help="每只股票最多保留多少根日K，默认260")
    parser.add_argument(
        "--provider",
        choices=["auto", "baostock", "efinance"],
        default="auto",
        help="数据源：auto=沪深用baostock、北交所用efinance；默认auto",
    )
    parser.add_argument("--mode", choices=["missing", "stale", "all"], default="stale", help="更新模式")
    parser.add_argument("--stale-before", default="", help="本地最后日期早于该日期才更新；默认等于end-date")
    parser.add_argument("--max-symbols", type=int, default=0, help="最多处理多少只；0表示不限制")
    parser.add_argument("--retries", type=int, default=5, help="单只股票失败重试次数")
    parser.add_argument("--efinance-extra-retries", type=int, default=4, help="efinance 额外重试次数，默认4")
    parser.add_argument("--efinance-batch-size", type=int, default=20, help="efinance 每批处理股票数，默认20；0表示不分批")
    parser.add_argument("--efinance-batch-sleep-seconds", type=float, default=10.0, help="efinance 每批之间冷却秒数，默认10")
    parser.add_argument("--efinance-min-sleep-seconds", type=float, default=2.0, help="efinance 单只之间最短随机停顿秒数")
    parser.add_argument("--efinance-max-sleep-seconds", type=float, default=3.0, help="efinance 单只之间最长随机停顿秒数")
    parser.add_argument("--sleep-seconds", type=float, default=0.8, help="每只股票之间停顿秒数")
    parser.add_argument("--retry-sleep-seconds", type=float, default=3.0, help="失败重试前基础停顿秒数，会随重试次数递增")
    parser.add_argument("--require-complete-fields", action="store_true", default=True, help="要求成交额和换手率等关键字段完整")
    parser.add_argument("--no-require-complete-fields", dest="require_complete_fields", action="store_false", help="允许关键字段为空")
    parser.add_argument("--dry-run", action="store_true", help="只打印任务，不实际抓取")
    return parser.parse_args()


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def safe_float(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def normalize_code(value: str) -> str:
    code = str(value).strip()
    if code.lower().startswith(("sh", "sz", "bj")):
        code = code[2:]
    return code.zfill(6)


def market_prefix(code: str) -> str:
    if code.startswith(("4", "8")) or code.startswith("92"):
        return "bj"
    if code.startswith(("5", "6", "9")):
        return "sh"
    if code.startswith(("0", "2", "3")):
        return "sz"
    raise ValueError(f"无法识别市场: {code}")


def is_beijing_stock(code: str) -> bool:
    return code.startswith(("4", "8")) or code.startswith("92")


def to_baostock_symbol(code: str) -> str:
    return f"{market_prefix(code)}.{code}"


def sanitize_filename(value: str) -> str:
    banned = '\\/:*?"<>|'
    return "".join("_" if ch in banned else ch for ch in value.strip()) or "未命名"


def output_path(output_dir: Path, code: str, name: str) -> Path:
    return output_dir / f"{code}_{sanitize_filename(name)}_daily_k.csv"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_daily_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=DAILY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    tmp_path.replace(path)


def load_symbols(path: Path) -> list[dict[str, str]]:
    symbols: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in read_csv_rows(path):
        code = normalize_code(row.get("代码", ""))
        name = str(row.get("名称", "")).strip()
        if not code.isdigit() or code in seen:
            continue
        seen.add(code)
        symbols.append({"代码": code, "名称": name})
    return symbols


def last_daily_date(path: Path) -> str:
    if not path.exists() or path.stat().st_size <= 64:
        return ""
    last = ""
    try:
        for row in read_csv_rows(path):
            value = str(row.get("日期", "")).strip()
            if value:
                last = value
    except Exception:
        return ""
    return last


def should_update(path: Path, mode: str, stale_before: str) -> bool:
    if mode == "all":
        return True
    if not path.exists() or path.stat().st_size <= 64:
        return True
    if mode == "missing":
        return False
    last_date = last_daily_date(path)
    return not last_date or last_date < stale_before


def build_rows_from_baostock(raw_rows: list[list[str]], limit: int) -> list[dict[str, str]]:
    raw_rows = raw_rows[-limit:]
    rows: list[dict[str, str]] = []
    prev_close: float | None = None
    for item in raw_rows:
        trade_date, open_, close, high, low, volume, amount, turn, pct_chg = item
        high_f = safe_float(high)
        low_f = safe_float(low)
        close_f = safe_float(close)
        amplitude = ((high_f - low_f) / prev_close * 100) if prev_close else 0.0
        change = close_f - prev_close if prev_close else 0.0
        rows.append(
            {
                "日期": trade_date,
                "开盘": open_,
                "收盘": close,
                "最高": high,
                "最低": low,
                "成交量": volume,
                "成交额": amount,
                "振幅": f"{amplitude:.2f}",
                "涨跌幅": pct_chg or "0",
                "涨跌额": f"{change:.2f}",
                "换手率": turn or "0",
            }
        )
        prev_close = close_f
    return rows


def build_rows_from_efinance(df: Any, limit: int) -> list[dict[str, str]]:
    df = df.tail(limit)
    rows: list[dict[str, str]] = []
    for _, item in df.iterrows():
        rows.append(
            {
                "日期": str(item.get("日期", "")),
                "开盘": format_number(item.get("开盘"), 4),
                "收盘": format_number(item.get("收盘"), 4),
                "最高": format_number(item.get("最高"), 4),
                "最低": format_number(item.get("最低"), 4),
                "成交量": format_number(item.get("成交量"), 0),
                "成交额": format_number(item.get("成交额"), 2),
                "振幅": format_number(item.get("振幅"), 2),
                "涨跌幅": format_number(item.get("涨跌幅"), 4),
                "涨跌额": format_number(item.get("涨跌额"), 4),
                "换手率": format_number(item.get("换手率"), 4),
            }
        )
    return rows


def format_number(value: Any, digits: int) -> str:
    try:
        numeric = float(value)
        if math.isnan(numeric) or math.isinf(numeric):
            return ""
        return f"{numeric:.{digits}f}"
    except Exception:
        return ""


def compact_date(value: str) -> str:
    return value.replace("-", "")


def validate_daily_rows(rows: list[dict[str, str]], require_complete_fields: bool) -> None:
    if not rows:
        raise RuntimeError("empty daily rows")
    required = ["日期", "开盘", "收盘", "最高", "最低", "成交量"]
    if require_complete_fields:
        required.extend(["成交额", "振幅", "涨跌幅", "涨跌额", "换手率"])
    for idx, row in enumerate(rows, 1):
        missing = [field for field in required if str(row.get(field, "")).strip() == ""]
        if missing:
            raise RuntimeError(f"row {idx} missing fields: {','.join(missing)}")
        numeric_fields = [field for field in required if field != "日期"]
        invalid_numeric = []
        for field in numeric_fields:
            try:
                numeric = float(row.get(field, ""))
                if math.isnan(numeric) or math.isinf(numeric):
                    invalid_numeric.append(field)
            except Exception:
                invalid_numeric.append(field)
        if invalid_numeric:
            raise RuntimeError(f"row {idx} invalid numeric fields: {','.join(invalid_numeric)}")


def retry_sleep(base_seconds: float, attempt: int) -> None:
    delay = base_seconds * attempt + random.uniform(0, min(1.5, base_seconds))
    time.sleep(delay)


def provider_sleep(provider: str, args: argparse.Namespace) -> None:
    if provider == "efinance":
        time.sleep(random.uniform(args.efinance_min_sleep_seconds, args.efinance_max_sleep_seconds))
    else:
        time.sleep(args.sleep_seconds)


def pct(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.00%"
    return f"{numerator / denominator:.2%}"


def fetch_daily_rows_baostock(bs: Any, code: str, start_date: str, end_date: str, limit: int) -> list[dict[str, str]]:
    rs = bs.query_history_k_data_plus(
        to_baostock_symbol(code),
        BAOSTOCK_FIELDS,
        start_date=start_date,
        end_date=end_date,
        frequency="d",
        adjustflag="2",
    )
    if rs.error_code != "0":
        raise RuntimeError(f"{rs.error_code} {rs.error_msg}")
    raw_rows: list[list[str]] = []
    while rs.next():
        raw_rows.append(rs.get_row_data())
    rows = build_rows_from_baostock(raw_rows, limit)
    return rows


def fetch_daily_rows_efinance(ef: Any, code: str, start_date: str, end_date: str, limit: int) -> list[dict[str, str]]:
    df = ef.stock.get_quote_history(
        code,
        beg=compact_date(start_date),
        end=compact_date(end_date),
        klt=101,
        fqt=1,
    )
    if df.empty:
        raise RuntimeError("efinance empty daily rows")
    return build_rows_from_efinance(df, limit)


def main() -> None:
    args = parse_args()
    parse_date(args.start_date)
    parse_date(args.end_date)
    stale_before = args.stale_before or args.end_date
    parse_date(stale_before)
    if args.efinance_min_sleep_seconds > args.efinance_max_sleep_seconds:
        raise SystemExit("--efinance-min-sleep-seconds 不能大于 --efinance-max-sleep-seconds")

    symbols = load_symbols(Path(args.symbols_csv).resolve())
    if args.max_symbols > 0:
        symbols = symbols[: args.max_symbols]
    output_dir = Path(args.output_dir).resolve()

    tasks: list[dict[str, str]] = []
    skipped = 0
    for item in symbols:
        path = output_path(output_dir, item["代码"], item["名称"])
        if should_update(path, args.mode, stale_before):
            tasks.append({**item, "路径": str(path), "本地最后日期": last_daily_date(path)})
        else:
            skipped += 1

    print(
        f"symbols={len(symbols)} provider={args.provider} mode={args.mode} tasks={len(tasks)} "
        f"skipped={skipped} output_dir={output_dir}"
    )
    if args.dry_run:
        for item in tasks[:50]:
            print(f"dry-run update {item['代码']} {item['名称']} last={item['本地最后日期'] or '-'}")
        if len(tasks) > 50:
            print(f"dry-run omitted={len(tasks) - 50}")
        return

    bs = None
    ef = None
    needs_baostock = args.provider in {"auto", "baostock"} and any(
        args.provider == "baostock" or not is_beijing_stock(item["代码"]) for item in tasks
    )
    needs_efinance = args.provider in {"auto", "efinance"} and any(
        args.provider == "efinance" or is_beijing_stock(item["代码"]) for item in tasks
    )

    if needs_baostock:
        try:
            import baostock as bs_module
        except Exception as exc:
            raise SystemExit(f"缺少 baostock，先安装依赖: {exc}") from exc
        bs = bs_module
        login = bs.login()
        if login.error_code != "0":
            raise SystemExit(f"baostock login failed: {login.error_code} {login.error_msg}")
    if needs_efinance:
        try:
            import efinance as ef_module
        except Exception as exc:
            raise SystemExit(f"缺少 efinance，先安装依赖: {exc}") from exc
        ef = ef_module

    fetched = 0
    failures: list[dict[str, str]] = []
    incomplete: list[dict[str, str]] = []
    provider_stats: dict[str, dict[str, int]] = {
        "baostock": {"stocks": 0, "success": 0, "final_failed": 0, "attempts": 0, "attempt_failed": 0},
        "efinance": {"stocks": 0, "success": 0, "final_failed": 0, "attempts": 0, "attempt_failed": 0},
    }
    provider_batch_counts = {"baostock": 0, "efinance": 0}
    try:
        for idx, item in enumerate(tasks, 1):
            code = item["代码"]
            name = item["名称"]
            path = Path(item["路径"])
            last_error = ""
            item_provider = "efinance" if (args.provider == "efinance" or (args.provider == "auto" and is_beijing_stock(code))) else "baostock"
            provider_stats[item_provider]["stocks"] += 1
            print(f"[{idx}/{len(tasks)}] {code} {name} provider={item_provider}", flush=True)
            max_attempts = args.retries + (args.efinance_extra_retries if item_provider == "efinance" else 0)
            for attempt in range(1, max_attempts + 1):
                provider_stats[item_provider]["attempts"] += 1
                try:
                    if item_provider == "baostock":
                        rows = fetch_daily_rows_baostock(bs, code, args.start_date, args.end_date, args.limit)
                    else:
                        rows = fetch_daily_rows_efinance(ef, code, args.start_date, args.end_date, args.limit)
                    try:
                        validate_daily_rows(rows, args.require_complete_fields)
                    except Exception as exc:
                        incomplete.append({"代码": code, "名称": name, "错误": str(exc)[:500]})
                        raise
                    write_daily_csv(path, rows)
                    fetched += 1
                    provider_stats[item_provider]["success"] += 1
                    break
                except Exception as exc:
                    provider_stats[item_provider]["attempt_failed"] += 1
                    last_error = str(exc)
                    if attempt < max_attempts:
                        retry_sleep(args.retry_sleep_seconds, attempt)
            else:
                failures.append({"代码": code, "名称": name, "错误": last_error[:500]})
                provider_stats[item_provider]["final_failed"] += 1

            if idx % 20 == 0 or idx == len(tasks):
                print(f"progress {idx}/{len(tasks)} fetched={fetched} failed={len(failures)}", flush=True)
            provider_sleep(item_provider, args)

            provider_batch_counts[item_provider] += 1
            if (
                item_provider == "efinance"
                and args.efinance_batch_size > 0
                and provider_batch_counts[item_provider] % args.efinance_batch_size == 0
                and idx < len(tasks)
            ):
                print(
                    f"efinance batch cooldown processed={provider_batch_counts[item_provider]} "
                    f"sleep={args.efinance_batch_sleep_seconds}s",
                    flush=True,
                )
                time.sleep(args.efinance_batch_sleep_seconds)
    finally:
        if bs is not None:
            bs.logout()

    failed_path = output_dir.parent / "failed_symbols_日K.csv"
    incomplete_path = output_dir.parent / "incomplete_symbols_日K.csv"
    failed_path.parent.mkdir(parents=True, exist_ok=True)
    with failed_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["代码", "名称", "错误"])
        writer.writeheader()
        writer.writerows(failures)
    with incomplete_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["代码", "名称", "错误"])
        writer.writeheader()
        writer.writerows(incomplete)

    print(
        f"done provider={args.provider} total={len(symbols)} tasks={len(tasks)} fetched={fetched} "
        f"skipped={skipped} failed={len(failures)} failed_csv={failed_path} incomplete_csv={incomplete_path}"
    )
    for provider, stats in provider_stats.items():
        if stats["stocks"] == 0:
            continue
        print(
            f"provider_stats provider={provider} stocks={stats['stocks']} success={stats['success']} "
            f"final_failed={stats['final_failed']} final_failure_rate={pct(stats['final_failed'], stats['stocks'])} "
            f"attempts={stats['attempts']} transient_failures={stats['attempt_failed']} "
            f"transient_failure_rate={pct(stats['attempt_failed'], stats['attempts'])}"
        )


if __name__ == "__main__":
    main()
