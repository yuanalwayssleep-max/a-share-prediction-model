#!/usr/bin/env python3
"""Contract checks for M6 final signal generation.

This file intentionally works with plain python3 as well as pytest.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = ROOT / "skills/a-share-kline-return-modeling/scripts"
FINAL_SIGNAL_DIR = ROOT / "skills/a-share-kline-return-modeling/outputs/final_signals"
PRIMARY_SIGNAL = FINAL_SIGNAL_DIR / "final_signals_full_size_2025-05_2026-04.csv"

FORBIDDEN_PREFIXES = ("future_", "label_", "actual_")
FORBIDDEN_COLUMNS = {"entry_price", "exit_price", "gross_future_5_return"}


def load_module(filename: str, module_name: str):
    path = SCRIPT_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader, f"Cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def forbidden_columns(columns: list[str]) -> list[str]:
    return [col for col in columns if col in FORBIDDEN_COLUMNS or col.startswith(FORBIDDEN_PREFIXES)]


def test_combined_size_v2_tier_rules() -> None:
    final_signals = load_module("21_generate_final_signals.py", "final_signals")

    low = pd.Series(
        {
            "market_up_ratio": 0.80,
            "market_volatility_5": 0.020,
            "market_10pct_density_ma5_lag1": 0.020,
        }
    )
    mid = pd.Series(
        {
            "market_up_ratio": 0.55,
            "market_volatility_5": 0.020,
            "market_10pct_density_ma5_lag1": 0.020,
        }
    )
    high = pd.Series(
        {
            "market_up_ratio": 0.80,
            "market_volatility_5": 0.028,
            "market_10pct_density_ma5_lag1": 0.020,
        }
    )

    assert final_signals.opportunity_tier(low) == "low"
    assert final_signals.opportunity_tier(mid) == "mid"
    assert final_signals.opportunity_tier(high) == "high"
    assert final_signals.size_multiplier_for_tier("low", "combined_size_v2") == 0.50
    assert final_signals.size_multiplier_for_tier("mid", "combined_size_v2") == 0.90
    assert final_signals.size_multiplier_for_tier("high", "combined_size_v2") == 1.00
    assert final_signals.size_multiplier_for_tier("low", "full_size") == 1.00


def test_build_final_signals_excludes_truth_columns() -> None:
    final_signals = load_module("21_generate_final_signals.py", "final_signals")
    predictions = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "symbol": "000001",
                "name": "A",
                "industry": "银行",
                "rank_strength_score": 0.9,
                "industry_strength_score": 0.1,
                "model_mode": "top50_classifier",
                "model_name": "LightGBMClassifier",
                "future_5_return": 0.5,
                "label_top30": 1,
                "actual_future_5_return": 0.5,
            },
            {
                "trade_date": "2026-01-02",
                "symbol": "000002",
                "name": "B",
                "industry": "地产",
                "rank_strength_score": 0.8,
                "industry_strength_score": 0.2,
                "model_mode": "top50_classifier",
                "model_name": "LightGBMClassifier",
                "future_5_return": -0.1,
                "label_top30": 0,
                "actual_future_5_return": -0.1,
            },
        ]
    )
    predictions["trade_date"] = pd.to_datetime(predictions["trade_date"])
    market = pd.DataFrame(
        [
            {
                "trade_date": pd.Timestamp("2026-01-02"),
                "market_up_ratio": 0.50,
                "market_avg_pct_chg": 0.1,
                "market_volatility_5": 0.020,
                "market_10pct_density_ma5_lag1": 0.020,
                "market_10pct_density_ma10_lag1": 0.030,
            }
        ]
    )

    signals = final_signals.build_final_signals(
        predictions,
        market,
        top_n=2,
        hold_sleeves=5,
        position_policy="combined_size_v2",
    )

    assert forbidden_columns(list(signals.columns)) == []
    assert signals["pick_rank"].tolist() == [1, 2]
    assert signals["opportunity_tier"].unique().tolist() == ["mid"]
    assert signals["position_size_multiplier"].unique().tolist() == [0.9]
    assert signals["suggested_new_sleeve_weight"].unique().round(12).tolist() == [0.18]
    assert signals["suggested_position_weight"].unique().round(12).tolist() == [0.09]


def test_build_final_signals_uses_actual_daily_pick_count_for_weights() -> None:
    final_signals = load_module("21_generate_final_signals.py", "final_signals_actual_pick_count")
    predictions = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "symbol": "000001",
                "name": "A",
                "industry": "银行",
                "rank_strength_score": 0.9,
                "industry_strength_score": 0.1,
                "model_mode": "top50_classifier",
                "model_name": "LightGBMClassifier",
            },
            {
                "trade_date": "2026-01-03",
                "symbol": "000002",
                "name": "B",
                "industry": "地产",
                "rank_strength_score": 0.8,
                "industry_strength_score": 0.2,
                "model_mode": "top50_classifier",
                "model_name": "LightGBMClassifier",
            },
            {
                "trade_date": "2026-01-03",
                "symbol": "000003",
                "name": "C",
                "industry": "电子",
                "rank_strength_score": 0.7,
                "industry_strength_score": 0.3,
                "model_mode": "top50_classifier",
                "model_name": "LightGBMClassifier",
            },
        ]
    )
    predictions["trade_date"] = pd.to_datetime(predictions["trade_date"])
    market = pd.DataFrame(
        [
            {
                "trade_date": pd.Timestamp("2026-01-02"),
                "market_up_ratio": 0.50,
                "market_avg_pct_chg": 0.1,
                "market_volatility_5": 0.020,
                "market_10pct_density_ma5_lag1": 0.020,
                "market_10pct_density_ma10_lag1": 0.030,
            },
            {
                "trade_date": pd.Timestamp("2026-01-03"),
                "market_up_ratio": 0.50,
                "market_avg_pct_chg": 0.1,
                "market_volatility_5": 0.020,
                "market_10pct_density_ma5_lag1": 0.020,
                "market_10pct_density_ma10_lag1": 0.030,
            },
        ]
    )

    signals = final_signals.build_final_signals(
        predictions,
        market,
        top_n=3,
        hold_sleeves=5,
        position_policy="full_size",
    )
    daily_total = signals.groupby("trade_date")["suggested_position_weight"].sum().round(12)

    assert daily_total.loc[pd.Timestamp("2026-01-02")] == 0.2
    assert daily_total.loc[pd.Timestamp("2026-01-03")] == 0.2
    assert signals.loc[signals["trade_date"] == pd.Timestamp("2026-01-02"), "suggested_position_weight"].tolist() == [0.2]
    assert signals.loc[signals["trade_date"] == pd.Timestamp("2026-01-03"), "suggested_position_weight"].round(12).tolist() == [0.1, 0.1]


def test_existing_final_signal_file_is_truth_free() -> None:
    assert PRIMARY_SIGNAL.exists(), f"Missing final signal file: {PRIMARY_SIGNAL}"
    df = pd.read_csv(PRIMARY_SIGNAL, encoding="utf-8-sig", nrows=5)
    assert forbidden_columns(list(df.columns)) == []
    required = {
        "trade_date",
        "symbol",
        "pick_rank",
        "position_policy",
        "opportunity_tier",
        "position_size_multiplier",
        "suggested_position_weight",
    }
    assert sorted(required - set(df.columns)) == []


def test_backtest_ledger_uses_actual_daily_pick_count_for_target_weight() -> None:
    backtest = load_module("14_backtest_portfolio_curve.py", "portfolio_backtest_actual_pick_count")
    predictions = pd.DataFrame(
        [
            {"trade_date": "2026-01-02", "symbol": "000001", "rank_strength_score": 0.9, "pick_rank": 1},
            {"trade_date": "2026-01-03", "symbol": "000002", "rank_strength_score": 0.8, "pick_rank": 1},
            {"trade_date": "2026-01-03", "symbol": "000003", "rank_strength_score": 0.7, "pick_rank": 2},
        ]
    )
    predictions["trade_date"] = pd.to_datetime(predictions["trade_date"])
    truth = pd.DataFrame(
        [
            {
                "trade_date": "2026-01-02",
                "symbol": "000001",
                "entry_trade_date": "2026-01-02",
                "exit_trade_date": "2026-01-07",
                "future_5_return": 0.01,
            },
            {
                "trade_date": "2026-01-03",
                "symbol": "000002",
                "entry_trade_date": "2026-01-03",
                "exit_trade_date": "2026-01-08",
                "future_5_return": 0.02,
            },
            {
                "trade_date": "2026-01-03",
                "symbol": "000003",
                "entry_trade_date": "2026-01-03",
                "exit_trade_date": "2026-01-08",
                "future_5_return": -0.01,
            },
        ]
    )
    truth["trade_date"] = pd.to_datetime(truth["trade_date"])
    truth["entry_trade_date"] = pd.to_datetime(truth["entry_trade_date"])
    truth["exit_trade_date"] = pd.to_datetime(truth["exit_trade_date"])

    ledger = backtest.build_ledger(predictions, truth, top_n=3, hold_sleeves=5)
    daily_total = ledger.groupby("trade_date")["target_weight"].sum().round(12)

    assert daily_total.loc[pd.Timestamp("2026-01-02")] == 0.2
    assert daily_total.loc[pd.Timestamp("2026-01-03")] == 0.2
    assert ledger.loc[ledger["trade_date"] == pd.Timestamp("2026-01-02"), "target_weight"].tolist() == [0.2]
    assert ledger.loc[ledger["trade_date"] == pd.Timestamp("2026-01-03"), "target_weight"].round(12).tolist() == [0.1, 0.1]


def test_final_signal_backtest_smoke() -> None:
    assert PRIMARY_SIGNAL.exists(), f"Missing final signal file: {PRIMARY_SIGNAL}"
    output_dir = ROOT / "skills/a-share-kline-return-modeling/outputs/evaluation/test_final_signal_backtest"
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "22_backtest_final_signals.py"),
        str(PRIMARY_SIGNAL),
        "--output-dir",
        str(output_dir),
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)
    summary_path = output_dir / "final_signal_backtest_summary.csv"
    assert summary_path.exists()
    summary = pd.read_csv(summary_path)
    assert summary.loc[0, "trades"] > 0
    assert summary.loc[0, "final_equity_curve"] > 0
    assert summary.loc[0, "max_exposure"] <= 1.0000001


if __name__ == "__main__":
    for test in [
        test_combined_size_v2_tier_rules,
        test_build_final_signals_excludes_truth_columns,
        test_build_final_signals_uses_actual_daily_pick_count_for_weights,
        test_existing_final_signal_file_is_truth_free,
        test_backtest_ledger_uses_actual_daily_pick_count_for_target_weight,
        test_final_signal_backtest_smoke,
    ]:
        test()
    print("all final signal contract checks passed")
