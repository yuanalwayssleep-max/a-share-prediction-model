# A股预测模型

这个仓库用于 A 股行情数据抓取、日 K 特征清洗、5 个交易日股票池预测、市场风险预测和最终出手信号判断。

## 目录

- `skills/a-share-data-fetching/`：行情数据抓取 skill，原始行情数据也放在这里。
- `skills/a-share-data-fetching/data/`：原始行情快照、股票日 K、指数日 K、单股分时和 5 分钟 K。
- `skills/a-share-kline-return-modeling/`：5 日预测模型 skill，包含清洗、个股模型、市场风险模型和最终信号层。

根目录不再保留通用 `scripts/` 业务脚本，避免和 skill 内脚本混用。

## 数据抓取

抓取脚本统一放在：

```text
skills/a-share-data-fetching/scripts/
```

保留的抓取入口：

- `fetch_stock_daily_k_batch.py`：批量抓取股票日 K。
- `fetch_core_index_daily_k.py`：抓取核心指数日 K。
- `fetch_single_stock_5m_intraday.py`：抓取单只股票分时、1 分钟 K、5 分钟 K。

示例：

```bash
python3 skills/a-share-data-fetching/scripts/fetch_stock_daily_k_batch.py \
  --symbols-csv skills/a-share-kline-return-modeling/data/00_股票清单.csv \
  --start-date 2025-01-01 \
  --end-date 2026-05-27 \
  --mode stale
```

## 模型流程

模型脚本统一放在：

```text
skills/a-share-kline-return-modeling/scripts/
```

核心流程：

1. `00_clean_data.py`：从 `skills/a-share-data-fetching/data/` 读取原始日 K，生成两张模型输入表。
2. `01_predict_stock_direction.py`：个股 Top 股票池预测。
3. `02_predict_market_risk.py`：未来 5 日市场风险预测。
4. `03_apply_signal_decision_layer.py`：根据个股预测和市场风险输出 `Top3 / Top2 / Top1 / 不出手`。

详细命令见：

```text
skills/a-share-kline-return-modeling/README.md
```

## 注意

模型输出只用于研究和交易纪律辅助，不是收益保证，也不是投资建议。所有带 `future_5_*` 前缀的字段只能作为训练标签或回测判卷使用，不能进入预测特征。
