# A股5日预测模型 Skill

这是 A 股日 K 5 日强势排序模型的主工作区，负责从原始日 K 数据生成特征、训练个股排序模型、做信号级评估、组合级回测和阶段验收报告。

## 当前状态

权威状态入口：`STATUS.md`

当前阶段：

```text
M3 个股排序模型：已通过阶段验收。
M7 测试固化初版已通过。
当前阶段：M8 工程固化 / 主流程一键化 / 结构清理。
```

当前默认主线：

```text
模型脚本：scripts/01_train_stock_rank_model.py
默认模式：--model-mode top50_classifier
模型：LightGBMClassifier
目标：label_top50
候选池：Top50
最终排序：candidate_score Top3
```

注意：结构审查后，执行基准恢复为 `full_size`；`combined_size_v2` 只保留为候选风险开关。执行前优先查看 `STATUS.md`、`docs/risk_register.md` 和 `docs/decision_log.md`。

## 关键目录

```text
configs/                  回测、交易、成本、流动性配置
data/                     股票清单、clean 特征和标签数据
scripts/                  特征、训练、评估、组合回测和实验脚本
tests/                    合约测试和小样本回归测试
outputs/evaluation/       评估、验收、实验和组合回测产物
docs/                     方案、里程碑、CR、小时报、验收报告和治理文档
```

## 关键文档

- `STATUS.md`：当前项目状态快照。
- `docs/development_milestones.md`：V1 里程碑与验收目标。
- `docs/implementation_plan.md`：技术实施方案与脚本规划。
- `docs/label_design.md`：标签设计和防泄漏口径。
- `docs/change_request_process.md`：变更请求规范。
- `docs/business_acceptance_criteria.md`：业务目标、用户验收标准和 UAT 场景。
- `docs/hourly_report_process.md`：小时报会议规范。
- `docs/decision_log.md`：已确认和待确认决策索引。
- `docs/risk_register.md`：风险台账。
- `docs/report_index.md`：报告索引，区分正式依据、实验产物和历史产物。
- `docs/m3_acceptance_report.md`：M3 验收报告。
- `docs/m4_acceptance_report.md`：M4 验收模板/报告。
- `docs/m5_acceptance_report.md`：M5 验收模板/报告。
- `docs/m7_acceptance_report.md`：M7 测试固化验收报告。

## 当前主流程

### 一键主流程

默认主流程会串联特征构建、walk-forward、组合回测、最终信号、最终信号回测和契约测试：

```bash
python3 skills/a-share-kline-return-modeling/scripts/23_run_main_pipeline.py
```

如果只想复用已有 walk-forward 结果，重新生成最终信号和测试：

```bash
python3 skills/a-share-kline-return-modeling/scripts/23_run_main_pipeline.py \
  --skip-build-features \
  --skip-walk-forward \
  --skip-portfolio-backtest
```

同时输出候选仓位策略对比：

```bash
python3 skills/a-share-kline-return-modeling/scripts/23_run_main_pipeline.py \
  --include-candidate-policy
```

主流程摘要：

```text
outputs/evaluation/main_pipeline_summary.md
outputs/evaluation/main_pipeline_summary.json
```

### 1. 构建特征与标签

```bash
python3 skills/a-share-kline-return-modeling/scripts/00_build_features.py
```

主要输出：

```text
skills/a-share-kline-return-modeling/data/clean_stock_features.csv
skills/a-share-kline-return-modeling/data/clean_market_features.csv
skills/a-share-kline-return-modeling/data/market_signal_features.csv
skills/a-share-kline-return-modeling/data/market_truth_labels.csv
skills/a-share-kline-return-modeling/outputs/evaluation/data_quality_report.md
```

### 2. 训练当前主线模型

```bash
python3 skills/a-share-kline-return-modeling/scripts/01_train_stock_rank_model.py \
  --model-mode top50_classifier
```

常见回退/实验模式：

```text
raw_rank_pct_regression
top30_classifier
weighted_rank_pct_regression
top10pct_classifier / top15pct_classifier / top20pct_classifier / top25pct_classifier
```

### 3. 信号级评估

```bash
python3 skills/a-share-kline-return-modeling/scripts/04_evaluate_top3.py
```

### 4. Walk-forward 验证

```bash
python3 skills/a-share-kline-return-modeling/scripts/05_run_walk_forward.py \
  --model-mode top50_classifier
```

核心报告：

```text
outputs/evaluation/walk_forward_summary.md
outputs/evaluation/walk_forward/*/baseline_summary.md
```

### 5. M3 召回、二次排序和弱月分析

```bash
python3 skills/a-share-kline-return-modeling/scripts/08_evaluate_m3a_recall_experiments.py
python3 skills/a-share-kline-return-modeling/scripts/09_evaluate_m3_candidate_rerank_experiments.py
python3 skills/a-share-kline-return-modeling/scripts/11_analyze_m3_weak_months.py
python3 skills/a-share-kline-return-modeling/scripts/12_evaluate_m3_top3_sorting_grid.py
```

核心报告见 `docs/report_index.md`。

### 6. M4 组合级资金曲线

```bash
python3 skills/a-share-kline-return-modeling/scripts/14_backtest_portfolio_curve.py
python3 skills/a-share-kline-return-modeling/scripts/15_analyze_portfolio_stability.py
```

核心报告：

```text
outputs/evaluation/portfolio_backtest/portfolio_backtest_report.md
outputs/evaluation/portfolio_backtest/m4_stability_report.md
```

### 7. M5 出手数量和仓位调节

```bash
python3 skills/a-share-kline-return-modeling/scripts/16_evaluate_signal_count_policies.py
python3 skills/a-share-kline-return-modeling/scripts/17_backtest_signal_count_policies.py
python3 skills/a-share-kline-return-modeling/scripts/18_backtest_position_sizing_policies.py
python3 skills/a-share-kline-return-modeling/scripts/19_grid_position_sizing_policies.py
```

核心报告：

```text
outputs/evaluation/m5_signal_count/m5_signal_count_report.md
outputs/evaluation/m5_signal_count_portfolio/m5_signal_count_portfolio_report.md
outputs/evaluation/m5_position_sizing/m5_position_sizing_report.md
outputs/evaluation/m5_position_sizing_grid/m5_position_sizing_grid_report.md
```

### 8. M6 最终信号与 M7 测试固化

```bash
python3 skills/a-share-kline-return-modeling/scripts/21_generate_final_signals.py \
  --position-policy full_size
python3 skills/a-share-kline-return-modeling/scripts/22_backtest_final_signals.py
python3 skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py
```

核心产物：

```text
outputs/final_signals/
outputs/evaluation/final_signal_backtest/final_signal_backtest_report.md
docs/m7_acceptance_report.md
```

## 依赖与验证

```bash
python3 -m pip install -r requirements.txt
python3 -m py_compile skills/a-share-kline-return-modeling/scripts/*.py skills/a-share-kline-return-modeling/tests/*.py
python3 skills/a-share-kline-return-modeling/tests/test_build_features_contract.py
python3 skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py
```

## 治理规则

- 正常试错、诊断、离线实验不需要 CR。
- 修改需求、验收口径、交易口径、标签定义、开发计划或主线实现，需要 CR 或审批记录。
- `future_*`、`label_*`、truth 字段、T+1 后才可知字段不得进入 T 日模型特征或最终信号文件。
- M3 当前默认主线需要治理收口；在收口前不要继续用同一 12 个月窗口硬调排序。
- 小时报会议输出统一放在 `docs/hourly_reports/`。

## 当前优先级

1. 补齐 M3 默认主线和 `combined_size_v2` 默认策略的 CR 或审批记录。
2. 完成 M8 文档入口整理，确保 STATUS、README、报告索引一致。
3. 建立主流程一键化入口，串联最终信号生成、回测和契约测试。
4. 继续固化依赖声明和测试，保证项目可复现。
5. 保持正式报告索引更新，避免实验产物和验收依据混用。
