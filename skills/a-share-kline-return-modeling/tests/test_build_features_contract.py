#!/usr/bin/env python3
"""Lightweight contract checks for V1 build feature outputs.

Run after scripts/00_build_features.py has generated clean_stock_features.csv.
This file avoids pytest-only syntax so it can run with plain python3 too.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
STOCK_FEATURES = ROOT / "skills/a-share-kline-return-modeling/data/clean_stock_features.csv"
SUMMARY = ROOT / "skills/a-share-kline-return-modeling/outputs/evaluation/build_features_summary.json"

FORBIDDEN_MODEL_PREFIXES = ("future_", "entry_", "exit_", "actual_")
FORBIDDEN_MODEL_SUFFIXES = ("_label",)


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


if __name__ == "__main__":
    for test in [
        test_future_5_trade_date_filter,
        test_backtest_cost_calculation,
        test_label_rank_direction,
        test_no_future_feature_leakage_summary,
    ]:
        test()
    print("all build feature contract checks passed")
