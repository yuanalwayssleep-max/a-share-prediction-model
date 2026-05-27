---
name: a-share-kline-return-modeling
description: Build and run A-share 5-trading-day stock-pool prediction from raw data cleaning through stock Top-quantile model, market risk model, and final Top3/Top2/Top1/no-trade signal decisions.
---

# A-share 5-Day Prediction Skill

## Directory Rules

- Raw input data stays under `skills/a-share-data-fetching/data/`.
- All cleaned/model-ready data produced by this skill goes under `skills/a-share-kline-return-modeling/data/`.
- All 5-day stock prediction scripts live under `skills/a-share-kline-return-modeling/scripts/`.
- Data collection scripts live under `skills/a-share-data-fetching/scripts/`, not the model pipeline skill.
- Cleaning should output only `个股k线特征数据.csv` and `指数k线特征数据.csv`.
- The two cleaned tables may contain `future_5_*` label columns for training/backtesting, but these columns are labels only.
- Holiday features are generated in `00_clean_data.py` and consumed by `03_apply_signal_decision_layer.py` as signal context; do not keep a separate holiday production script.

## Current Pipeline

1. Clean raw data:

```bash
python3 skills/a-share-kline-return-modeling/scripts/00_clean_data.py
```

2. Train/predict single-stock 5-day Top stock pool.

```bash
python3 skills/a-share-kline-return-modeling/scripts/01_predict_stock_direction.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD --target-mode top_quantile --top-quantile 0.2 --top-n 3
```

Prediction output excludes ST stocks by default. Keep `--enable-overheat-penalty` as an explicit research switch instead of a default signal rule until it proves stable across more months.

3. Train/predict market 5-day direction/risk.

```bash
python3 skills/a-share-kline-return-modeling/scripts/02_predict_market_risk.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD
```

4. Apply final signal layer. It reads stock-pool prediction and market prediction, then outputs `Top3`, `Top2`, `Top1`, or `不出手`.

```bash
python3 skills/a-share-kline-return-modeling/scripts/03_apply_signal_decision_layer.py --stock-prediction <stock_prediction.csv> --market-prediction <market_prediction.csv>
```

## First Principle

Do not train directly on raw files under `skills/a-share-data-fetching/data/`. Build `个股k线特征数据.csv` first, keep quality flags in that same table, and only use `is_training_eligible == 1` rows for historical model training.

Never use future data as model input. Any column matching `future_*` is a forbidden feature and must be excluded from model `X`; it can only be used as training/backtest label `y`.
