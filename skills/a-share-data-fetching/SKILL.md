---
name: a-share-data-fetching
description: Use this skill when fetching A-share market data for the project, including batch stock daily K lines, core index daily K lines, and single-stock intraday or 5-minute K-line data. Use it before cleaning/modeling when raw data needs to be refreshed.
---

# A股行情数据抓取

这个 skill 只负责抓取原始行情数据，不做模型训练、不做数据清洗、不做信号判断。

## 脚本

- `scripts/fetch_stock_daily_k_batch.py`：批量抓取股票日 K。
- `scripts/fetch_core_index_daily_k.py`：抓取核心指数日 K。
- `scripts/fetch_single_stock_5m_intraday.py`：抓取单只股票当日分时、1 分钟 K、5 分钟 K。

## 常用命令

批量更新股票日 K：

```bash
python3 skills/a-share-data-fetching/scripts/fetch_stock_daily_k_batch.py \
  --symbols-csv skills/a-share-kline-return-modeling/data/00_股票清单.csv \
  --start-date 2025-01-01 \
  --end-date 2026-05-27 \
  --mode stale
```

抓取核心指数日 K：

```bash
python3 skills/a-share-data-fetching/scripts/fetch_core_index_daily_k.py \
  --start-date 2025-01-01 \
  --end-date 2026-05-27
```

抓取单只股票分时和 5 分钟 K：

```bash
python3 skills/a-share-data-fetching/scripts/fetch_single_stock_5m_intraday.py \
  --symbol 002396 \
  --ndays 1
```

## 输出约定

- 股票日 K 默认输出到仓库根目录 `outputs/stock_daily_k/日K线目录/`。
- 核心指数日 K 默认输出到仓库根目录 `data/指数日K文件/00_核心指数日K.csv`。
- 单只股票分时和 5 分钟 K 默认输出到仓库根目录 `outputs/single_stock_intraday/`。

抓取完成后，如需进入 5 日预测流程，再使用 `skills/a-share-kline-return-modeling/` 下的清洗和建模脚本。
