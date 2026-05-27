---
name: a-share-kline-return-modeling
description: Build and run A-share 5-trading-day stock-pool prediction from raw data cleaning through stock Top-quantile model, market risk model, and final Top3/Top2/Top1/no-trade signal decisions.
---

# A-share 5-Day Prediction Skill

## Directory Rules

- Raw input data stays under the repository `data/` directory.
- All cleaned/model-ready data produced by this skill goes under `skills/a-share-kline-return-modeling/data/`.
- All 5-day stock prediction scripts live under `skills/a-share-kline-return-modeling/scripts/`.
- Root-level `scripts/fetch_*.py` remain data collection utilities, not model pipeline scripts.
- Cleaning should output only `个股k线特征数据.csv` and `指数k线特征数据.csv`.
- The two cleaned tables may contain `future_5_*` label columns for training/backtesting, but these columns are labels only.

## Current Pipeline

1. Clean raw data:

```bash
python3 skills/a-share-kline-return-modeling/scripts/clean_data.py
```

2. Train/predict single-stock 5-day Top stock pool.

```bash
python3 skills/a-share-kline-return-modeling/scripts/predict_stock_direction.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD --target-mode top_quantile --top-quantile 0.2 --top-n 3
```

Prediction output excludes ST stocks by default. Keep `--enable-overheat-penalty` as an explicit research switch instead of a default signal rule until it proves stable across more months.

3. Train/predict market 5-day direction/risk.

```bash
python3 skills/a-share-kline-return-modeling/scripts/predict_market_risk.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

4. Apply final signal layer. It reads stock-pool prediction and market prediction, then outputs `Top3`, `Top2`, `Top1`, or `不出手`.

```bash
python3 skills/a-share-kline-return-modeling/scripts/apply_signal_decision_layer.py --stock-prediction <stock_prediction.csv> --market-prediction <market_prediction.csv>
```

## First Principle

Do not train directly on raw files under `data/`. Build `个股k线特征数据.csv` first, keep quality flags in that same table, and only use `is_training_eligible == 1` rows for historical model training.

Never use future data as model input. Any column matching `future_*` is a forbidden feature and must be excluded from model `X`; it can only be used as training/backtest label `y`.
