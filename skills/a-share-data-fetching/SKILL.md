---
name: a-share-data-fetching
description: Use this skill when fetching A-share market data for the project, including batch stock daily K lines, core index daily K lines, and single-stock intraday or 5-minute K-line data. Use it before cleaning/modeling when raw data needs to be refreshed.
---

# A股行情数据抓取

这个 skill 只负责抓取原始行情数据，不做模型训练、不做数据清洗、不做信号判断。

## 脚本

- `scripts/fetch_stock_daily_k_batch.py`：批量抓取股票日 K。
- `scripts/fetch_core_index_daily_k.py`：抓取核心指数日 K。
- `scripts/fetch_industry_daily_k_tushare.py`：使用 Tushare 抓取申万行业指数历史日 K。
- `scripts/fetch_single_stock_5m_intraday.py`：抓取单只股票当日分时、1 分钟 K、5 分钟 K。

## Tushare 初始化硬约束

本项目使用 Tushare 时必须走项目指定 API 地址，不能使用默认 Tushare API 地址。

所有 Tushare 脚本必须按下面方式初始化：

```python
import tushare as ts

token = "XXX"
pro = ts.pro_api(token)
pro._DataApi__token = token
pro._DataApi__http_url = "http://jiaoch.site"
```

规则：

- 禁止使用默认 Tushare API 地址。
- 所有接口调用必须基于配置后的 `pro` 对象。
- 如果使用 `ts.pro_bar`，必须传入 `api=pro`。
- 不按此方式初始化会导致 token 无效。

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

抓取申万一级行业历史日 K：

```bash
TUSHARE_TOKEN="$TUSHARE_TOKEN" \
python3 skills/a-share-data-fetching/scripts/fetch_industry_daily_k_tushare.py \
  --start-date 2025-01-01 \
  --end-date 2026-05-27 \
  --levels L1 \
  --mode stale
```

抓取单只股票分时和 5 分钟 K：

```bash
python3 skills/a-share-data-fetching/scripts/fetch_single_stock_5m_intraday.py \
  --symbol 002396 \
  --ndays 1
```

## 输出约定

- 股票日 K 默认输出到 `skills/a-share-data-fetching/data/单只股票日k/`。
- 核心指数日 K 默认输出到 `skills/a-share-data-fetching/data/指数日K文件/00_核心指数日K.csv`。
- 申万行业日 K 默认输出到 `skills/a-share-data-fetching/data/行业日K文件/申万行业日K/`，行业清单快照输出到 `skills/a-share-data-fetching/data/行业日K文件/申万行业清单.csv`。
- 单只股票分时、1 分钟 K、5 分钟 K 默认输出到 `skills/a-share-data-fetching/data/single_stock_intraday/`。

抓取完成后，如需进入 5 日预测流程，再使用 `skills/a-share-kline-return-modeling/` 下的清洗和建模脚本。
