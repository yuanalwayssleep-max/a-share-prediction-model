---
name: a-share-kline-return-modeling
description: Build and run A-share 5-trading-day actionable stock prediction, targeting stocks with future 5-day return >=10%, with stock loss-risk, market risk, industry risk, and final fixed daily Top3 ranking.
---

# A-share 5-Day Prediction Skill

## Directory Rules

- Raw input data stays under `skills/a-share-data-fetching/data/`.
- All cleaned/model-ready data produced by this skill goes under `skills/a-share-kline-return-modeling/data/`.
- All 5-day stock prediction scripts live under `skills/a-share-kline-return-modeling/scripts/`.
- Data collection scripts live under `skills/a-share-data-fetching/scripts/`, not the model pipeline skill.
- Cleaning outputs `个股k线特征数据.csv`, `指数k线特征数据.csv`, and `行业指数特征数据.csv`.
- The two cleaned tables may contain `future_5_*` label columns for training/backtesting, but these columns are labels only.
- Holiday features are generated in `00_clean_data.py` and consumed by `03_apply_signal_decision_layer.py` as signal context; do not keep a separate holiday production script.

## Current Pipeline

1. Clean raw data:

```bash
python3 skills/a-share-kline-return-modeling/scripts/00_clean_data.py
```

2. Train/predict single-stock 5-day return-threshold candidates. The current main loop uses a `>=20%` explosive-return label to rank a daily Top20 candidate pool for the business goal of final Top3 future 5-day return `>=10%`.

```bash
python3 skills/a-share-kline-return-modeling/scripts/01_predict_stock_direction.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

Prediction output excludes ST stocks by default.
The main script keeps one production path: compact60 features, LightGBM baseline, terminal-risk ranking penalty, and daily Top20 candidate-pool output.

3. Train/predict stock 5-day loss risk.

```bash
python3 skills/a-share-kline-return-modeling/scripts/02c_predict_stock_loss_risk.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

4. Train/predict market 5-day direction/risk.

```bash
python3 skills/a-share-kline-return-modeling/scripts/02_predict_market_risk.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

5. Apply final signal layer. It reads strong-return candidate prediction, stock loss-risk prediction, market prediction, and optionally industry prediction, then fixed-outputs daily Top3. Market prediction is kept as diagnostics in this layer. Direct leakage-safe market-risk feature variants have been tested but are not the production path until they beat the compact60 baseline.

```bash
python3 skills/a-share-kline-return-modeling/scripts/03_apply_signal_decision_layer.py --stock-prediction <stock_prediction.csv> --stock-loss-risk-prediction <loss_risk.csv> --market-prediction <market_prediction.csv>
```

## First Principle

Do not train directly on raw files under `skills/a-share-data-fetching/data/`. Build `个股k线特征数据.csv` first, keep quality flags in that same table, and only use `is_training_eligible == 1` rows for historical model training.

Never use future data as model input. Any column matching `future_*` is a forbidden feature and must be excluded from model `X`; it can only be used as training/backtest label `y`.
