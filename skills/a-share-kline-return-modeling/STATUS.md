# Status

## 2026-05-26

- Rebuilt the skill workspace from scratch.
- Step 1 is data cleaning and data model design.
- Raw input source is `skills/a-share-data-fetching/data/`.
- All 5-day modeling scripts live under `skills/a-share-kline-return-modeling/scripts/`.
- Clean outputs will be written directly to `skills/a-share-kline-return-modeling/data/`.
- Cleaning output is intentionally limited to two tables: `个股k线特征数据.csv` and `指数k线特征数据.csv`.
- Added the first stock-level 5-day direction prediction script: `scripts/01_predict_stock_direction.py`.
- Stock prediction now uses `00_股票清单.csv` plus a date range and writes one result CSV.
- Added the market-level 5-day risk prediction script: `scripts/02_predict_market_risk.py`.
- Removed the standalone holiday-window core script; holiday features remain in cleaning and are used by the final signal layer.
