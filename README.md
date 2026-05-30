# A股预测模型

这个仓库用于 A 股行情数据抓取、日 K 特征清洗、5 个交易日强势股票排序、组合级回测和最终信号纪律辅助。

## 目录

- `skills/a-share-data-fetching/`：行情数据抓取 skill，原始行情数据也放在这里。
- `skills/a-share-data-fetching/data/`：原始行情快照、股票日 K、指数日 K、单股分时和 5 分钟 K。
- `skills/a-share-kline-return-modeling/`：5 日预测模型 skill，包含特征/标签、排序模型、walk-forward、组合回测、M4/M5 评估和项目治理文档。

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

当前主线入口：

1. `00_build_features.py`：从原始日 K 构建模型特征、标签和数据质量报告。
2. `01_train_stock_rank_model.py --model-mode top50_classifier`：训练当前 M3 主线排序模型。
3. `04_evaluate_top3.py`：评估 Top3 信号级结果。
4. `05_run_walk_forward.py --model-mode top50_classifier`：运行 walk-forward 验证。
5. `14_backtest_portfolio_curve.py`：运行 M4 组合级资金曲线回测。
6. `15_analyze_portfolio_stability.py`：分析组合稳定性、贡献和回撤。
7. `16_evaluate_signal_count_policies.py` / `17_backtest_signal_count_policies.py`：评估 M5 出手数量策略。
8. `18_backtest_position_sizing_policies.py` / `19_grid_position_sizing_policies.py`：评估 M5 仓位调节策略。

一键主流程：

```bash
python3 skills/a-share-kline-return-modeling/scripts/23_run_main_pipeline.py
```

复用已有 walk-forward 结果、只刷新最终信号和测试：

```bash
python3 skills/a-share-kline-return-modeling/scripts/23_run_main_pipeline.py \
  --skip-build-features \
  --skip-walk-forward \
  --skip-portfolio-backtest
```

详细命令和治理入口见：

```text
skills/a-share-kline-return-modeling/README.md
skills/a-share-kline-return-modeling/STATUS.md
skills/a-share-kline-return-modeling/docs/business_acceptance_criteria.md
skills/a-share-kline-return-modeling/docs/report_index.md
skills/a-share-kline-return-modeling/docs/risk_register.md
skills/a-share-kline-return-modeling/docs/decision_log.md
```

## 当前阶段

```text
M3 个股排序模型：已通过阶段验收。
M7 测试固化初版已通过。
当前阶段：M8 工程固化 / 主流程一键化 / 结构清理。
当前默认主线：top50_classifier + candidate_score Top3。
当前执行基准：full_size。
候选风险开关：combined_size_v2，仅作为对照，不再作为默认策略。
```

进入主线变更前应先查看 `STATUS.md`、`decision_log.md`、`risk_register.md` 和变更请求文档。

## 依赖与验证

```bash
python3 -m pip install -r requirements.txt
python3 -m py_compile skills/a-share-kline-return-modeling/scripts/*.py skills/a-share-kline-return-modeling/tests/*.py
python3 skills/a-share-kline-return-modeling/tests/test_build_features_contract.py
python3 skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py
```

## 注意

模型输出只用于研究和交易纪律辅助，不是收益保证，也不是投资建议。所有带 `future_5_*` 前缀的字段、`label_*` 字段和 T+1 后才可知的 truth 字段，只能作为训练标签或回测判卷使用，不能进入预测特征或最终执行信号。
