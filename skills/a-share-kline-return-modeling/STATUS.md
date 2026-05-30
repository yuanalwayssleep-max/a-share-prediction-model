# A股5日预测模型状态

更新时间：2026-05-30 GMT+8

## 当前阶段

```text
M3 个股排序模型：已通过阶段验收。
M4 现金约束组合回测：已跑通并完成 P1 回测口径修正。
M5 仓位/出手策略：重新验证后，full_size 暂作为执行基准，combined_size_v2 降为候选。
M6 最终信号层：已完成 truth-free 输入/输出防护。
M7 测试固化：已通过编译、特征契约、最终信号契约测试。
M8 工程固化：已新增主流程一键化入口，下一步继续做 P2 结构清理和小样本 fixture 测试。
```

## 当前主线

```text
脚本：scripts/01_train_stock_rank_model.py
默认模式：--model-mode top50_classifier
模型：LightGBMClassifier；缺少 lightgbm 时才回退 sklearn HistGradientBoostingClassifier
目标：label_top50
输出：rank_strength_score
候选池：Top50
最终排序：candidate_score Top3
```

回退/实验模式：

```text
--model-mode raw_rank_pct_regression
--model-mode top30_classifier
--model-mode weighted_rank_pct_regression
--model-mode top10pct_classifier / top15pct_classifier / top20pct_classifier / top25pct_classifier
```

## 2026-05-30 结构审查修复

来源：

```text
docs/code_reviews/2026-05-30-structural-code-review.md
```

已完成：

```text
P0-001：市场信号/市场 truth 拆分。
新增 data/market_signal_features.csv，仅包含 T 日可知或已滞后可知字段。
新增 data/market_truth_labels.csv，保存 future_* / label_* / actual_* 等判卷字段。

P0-002：最终信号脚本禁止 truth 输入。
scripts/21_generate_final_signals.py 删除 --use-truth-input，只读取 predictions.csv。
预测输入、市场输入、最终输出均加入 truth/future/label schema guard。

P1-001：组合回测默认改读 truth-free predictions.csv。
判卷 truth 唯一来源固定为 clean_stock_features.csv。

P1-002：月度收益改为 previous month end 口径。
首月使用 initial capital，后续月份使用上月末权益。

P1-003：最终信号回测不再硬编码固定 Top3 仓位。
按每日实际 pick 数分配目标仓位。

P1-004：top30/top50 二分类加入单类别保护。
训练窗口只有单一类别时跳过该交易日，并写入 diagnostics。

P2-003：配置解析和模型 fallback 收窄异常捕获。
YAML 格式错误 fail fast；模型仅在缺少 lightgbm 时回退。
```

仍待后续处理：

```text
P2-001：抽 src/a_share_kline 公共包，减少脚本重复。
P2-002：统一 repo root 和默认路径策略。
P2-004：增加小样本 fixture 测试与 CI。
```

## M3 最新结果

```text
验证范围：2025-05 至 2026-04
模式：top50_classifier
TopN：训练输出 Top50，评估 Top3
平均 Top3 5日收益：2.75%
平均 Top30 命中数：0.801 / 3
收益优于随机月份：10 / 12
Top30 命中优于随机月份：10 / 12
```

逐月摘要：

```text
2025-05：交易日 15，Top3收益 1.90%，Top30命中 0.733 / 3
2025-06：交易日 20，Top3收益 0.57%，Top30命中 0.500 / 3
2025-07：交易日 23，Top3收益 0.30%，Top30命中 0.391 / 3
2025-08：交易日 21，Top3收益 1.71%，Top30命中 0.762 / 3
2025-09：交易日 22，Top3收益 -0.48%，Top30命中 0.364 / 3
2025-10：交易日 17，Top3收益 0.74%，Top30命中 0.647 / 3
2025-11：交易日 20，Top3收益 -0.78%，Top30命中 0.600 / 3
2025-12：交易日 23，Top3收益 2.29%，Top30命中 0.652 / 3
2026-01：交易日 20，Top3收益 3.01%，Top30命中 0.850 / 3
2026-02：交易日 14，Top3收益 10.07%，Top30命中 1.500 / 3
2026-03：交易日 22，Top3收益 2.08%，Top30命中 1.136 / 3
2026-04：交易日 21，Top3收益 11.58%，Top30命中 1.476 / 3
```

说明：

```text
2025-05 因 label_top50 在早期小股票池窗口出现单类别，4 个交易日被跳过。
这是防止退化模型输出伪概率的必要保护，不视为预测失败样本。
```

详细报告：

```text
outputs/evaluation/walk_forward_summary.md
outputs/evaluation/stock_rank_model_metrics.json
docs/m3_acceptance_report.md
```

## M4/M5/M6 最新回测

组合回测与最终信号已在防泄漏口径下重跑：

```text
full_size：
交易数：714
信号日：238
最终资金曲线：2.7561
累计收益：175.61%
最大回撤：-9.91%
正收益月份：84.62%
平均暴露：96.31%

combined_size_v2：
交易数：714
信号日：238
平均仓位系数：0.9340
最终资金曲线：2.6792
累计收益：167.92%
最大回撤：-9.75%
正收益月份：76.92%
平均暴露：90.88%
```

当前判断：

```text
修正 market_10pct_density 的可知性滞后后，combined_size_v2 不再优于 full_size。
combined_size_v2 只小幅改善回撤，但牺牲收益和正收益月份。
因此执行基准恢复为 full_size，combined_size_v2 保留为候选风险开关，不作为默认最终策略。
```

报告：

```text
outputs/evaluation/m5_position_sizing/m5_position_sizing_report.md
outputs/evaluation/m5_position_sizing_grid/m5_position_sizing_grid_report.md
outputs/evaluation/m5_sizing_robustness/m5_sizing_robustness_report.md
outputs/evaluation/final_signal_backtest/final_signal_backtest_report.md
```

## 最终信号层

```text
脚本：scripts/21_generate_final_signals.py
回测脚本：scripts/22_backtest_final_signals.py
输出目录：outputs/final_signals/
默认仓位策略：full_size

最终信号输入：
outputs/stock_rank_predictions/YYYY-MM/predictions.csv
data/market_signal_features.csv

最终信号输出字段不包含：
future_* / label_* / actual_* / entry_price / exit_price / gross_future_5_return
```

当前生成文件：

```text
outputs/final_signals/final_signals_full_size_2025-05_2026-04.csv
outputs/final_signals/final_signals_combined_size_v2_2025-05_2026-04.csv
```

## M8 主流程一键化

```text
脚本：scripts/23_run_main_pipeline.py
默认范围：2025-05 至 2026-04
默认模型：top50_classifier
默认执行策略：full_size
可选候选策略：--include-candidate-policy 追加 combined_size_v2 对照
```

完整重跑：

```bash
python3 skills/a-share-kline-return-modeling/scripts/23_run_main_pipeline.py
```

复用已有 walk-forward 结果，只刷新最终信号、最终信号回测和测试：

```bash
python3 skills/a-share-kline-return-modeling/scripts/23_run_main_pipeline.py \
  --skip-build-features \
  --skip-walk-forward \
  --skip-portfolio-backtest
```

输出：

```text
outputs/evaluation/main_pipeline_summary.md
outputs/evaluation/main_pipeline_summary.json
```

## 验证

已通过：

```bash
python3 -m py_compile skills/a-share-kline-return-modeling/scripts/*.py skills/a-share-kline-return-modeling/tests/*.py
python3 skills/a-share-kline-return-modeling/tests/test_build_features_contract.py
python3 skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py
```

## 开发规范

```text
正常试错、诊断、离线实验、模型替换和工程修复不需要 CR。
只有修改既定项目方案、开发计划、验收口径、交易口径或标签定义时才提 CR。
```
