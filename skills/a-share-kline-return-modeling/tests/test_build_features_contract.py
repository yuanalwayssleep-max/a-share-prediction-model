#!/usr/bin/env python3
"""Lightweight contract checks for V1 build feature outputs.

Run after scripts/00_build_features.py has generated clean_stock_features.csv.
This file avoids pytest-only syntax so it can run with plain python3 too.
"""

from __future__ import annotations

from pathlib import Path
import importlib.util

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
STOCK_FEATURES = ROOT / "skills/a-share-kline-return-modeling/data/clean_stock_features.csv"
SUMMARY = ROOT / "skills/a-share-kline-return-modeling/outputs/evaluation/build_features_summary.json"
SCRIPT_DIR = ROOT / "skills/a-share-kline-return-modeling/scripts"

FORBIDDEN_MODEL_PREFIXES = ("future_", "entry_", "exit_", "actual_")
FORBIDDEN_MODEL_SUFFIXES = ("_label",)


def load_build_features_module():
    spec = importlib.util.spec_from_file_location("build_features", SCRIPT_DIR / "00_build_features.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_stock_features() -> pd.DataFrame:
    assert STOCK_FEATURES.exists(), f"Missing output: {STOCK_FEATURES}"
    return pd.read_csv(STOCK_FEATURES, encoding="utf-8-sig", parse_dates=["trade_date", "entry_trade_date", "exit_trade_date"])


def test_future_5_trade_date_filter() -> None:
    df = load_stock_features().dropna(subset=["entry_trade_date", "exit_trade_date"])
    market_calendar = sorted(df["trade_date"].dropna().unique())
    cal_index = {date: idx for idx, date in enumerate(market_calendar)}
    sample = df.groupby("symbol", group_keys=False).head(20)
    for _, row in sample.iterrows():
        pos = cal_index.get(row["trade_date"])
        if pos is None or pos + 6 >= len(market_calendar):
            continue
        assert row["entry_trade_date"] == market_calendar[pos + 1]
        assert row["exit_trade_date"] == market_calendar[pos + 6]


def test_backtest_cost_calculation() -> None:
    df = load_stock_features().dropna(subset=["future_5_return", "gross_future_5_return"])
    sample = df.head(100)
    expected = (
        sample["gross_future_5_return"]
        - sample["buy_cost_rate"]
        - sample["sell_cost_rate"]
        - sample["buy_slippage_rate"]
        - sample["sell_slippage_rate"]
    )
    assert (sample["future_5_return"] - expected).abs().max() < 1e-12


def test_label_rank_direction() -> None:
    df = load_stock_features().dropna(subset=["future_5_return_rank_pct"])
    daily = df.groupby("trade_date")["future_5_return_rank_pct"]
    assert daily.max().round(12).eq(1.0).all()
    multi_stock_days = df.groupby("trade_date")["symbol"].nunique()
    check_days = multi_stock_days[multi_stock_days > 1].index
    assert daily.min().loc[check_days].round(12).eq(0.0).all()


def test_no_future_feature_leakage_summary() -> None:
    assert SUMMARY.exists(), f"Missing output: {SUMMARY}"
    import json

    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    signal_features = summary["signal_known_features"]
    forbidden = [c for c in signal_features if c.startswith(FORBIDDEN_MODEL_PREFIXES)]
    forbidden += [c for c in signal_features if c.endswith(FORBIDDEN_MODEL_SUFFIXES)]
    assert forbidden == []


def test_add_future_labels_uses_next_trade_day_entry_and_hold_day_exit_fixture() -> None:
    build_features = load_build_features_module()
    dates = pd.to_datetime(
        [
            "2026-01-02",
            "2026-01-05",
            "2026-01-06",
            "2026-01-07",
            "2026-01-08",
            "2026-01-09",
        ]
    )
    rows = []
    for symbol, closes in {"000001": [10, 11, 12, 13, 14, 15], "000002": [20, 19, 18, 17, 16, 15]}.items():
        for trade_date, close in zip(dates, closes):
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "open": float(close),
                    "high": float(close) + 0.1,
                    "low": float(close) - 0.1,
                    "close": float(close),
                    "pct_chg": 0.0,
                }
            )
    source = pd.DataFrame(rows)
    config = {
        "commission_rate": 0.001,
        "transfer_fee_rate": 0.0,
        "stamp_tax_rate": 0.001,
        "buy_slippage_rate": 0.0005,
        "sell_slippage_rate": 0.0005,
        "holding_trade_days": 2,
        "allow_exit_delay": True,
    }

    out = build_features.add_future_labels(source, list(dates), config)
    first_day = out[out["trade_date"].eq(dates[0])].sort_values("symbol")

    assert first_day["entry_trade_date"].tolist() == [dates[1], dates[1]]
    assert first_day["exit_trade_date"].tolist() == [dates[3], dates[3]]
    assert first_day["tradable_at_entry"].tolist() == [True, True]
    assert first_day["tradable_at_exit"].tolist() == [True, True]
    assert first_day["daily_stock_count"].tolist() == [2, 2]
    assert first_day["future_5_return_rank_pct"].tolist() == [1.0, 0.0]

    gross = first_day.set_index("symbol")["gross_future_5_return"].to_dict()
    assert abs(gross["000001"] - (13 / 11 - 1)) < 1e-12
    assert abs(gross["000002"] - (17 / 19 - 1)) < 1e-12
    assert out[out["trade_date"].eq(dates[-3])]["future_5_return"].isna().all()


if __name__ == "__main__":
    for test in [
        test_future_5_trade_date_filter,
        test_backtest_cost_calculation,
        test_label_rank_direction,
        test_no_future_feature_leakage_summary,
        test_add_future_labels_uses_next_trade_day_entry_and_hold_day_exit_fixture,
    ]:
        test()
    print("all build feature contract checks passed")
