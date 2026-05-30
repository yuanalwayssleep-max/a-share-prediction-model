# 评估报告索引

更新时间：2026-05-30 GMT+8

## 用途

`outputs/evaluation/` 下同时包含正式验收依据、候选实验、烟测结果和历史产物。本索引用于标记每份报告的用途，避免把实验结果误当阶段结论。

## 分类

```text
正式依据：可用于 STATUS、验收报告和 Gate Review。
候选依据：有价值，但仍需复核或补验收包。
实验产物：用于分析和方向筛选，不直接作为主线结论。
历史/烟测：仅用于排查或回溯，不作为当前判断。
```

## 正式依据

| 报告 | 阶段 | 用途 |
|---|---|---|
| `docs/m3_acceptance_report.md` | M3 | M3 阶段验收结论 |
| `outputs/evaluation/walk_forward_summary.md` | M3 | 12 个月 walk-forward 总结 |
| `outputs/evaluation/m3_recall_model_compare.md` | M3 | 召回导向模型对比 |
| `outputs/evaluation/m3_candidate_rerank_report.md` | M3 | candidate_score 二次排序结果 |
| `outputs/evaluation/m3_weak_month_analysis.md` | M3 | 弱月份分析 |
| `outputs/evaluation/m3_top3_sorting_grid_report.md` | M3 | Top3 排序增强实验汇总 |
| `docs/m7_acceptance_report.md` | M7 | 最终信号契约测试验收结论 |
| `docs/v1_development_report_2026-05-30.md` | V1 | V1 功能闭环开发报告 |
| `outputs/evaluation/main_pipeline_summary.md` | M8 | 主流程一键化摘要 |
| `outputs/evaluation/final_signal_backtest/final_signal_backtest_report.md` | M6/M7 | truth-free final signal 回测依据 |
| `docs/qa_reports/qa_report_20260530_134457_timeout_fix_revalidation.md` | M7/M8 | GNU timeout 修复复验和 bounded contract tests 证据 |

## 候选依据

| 报告 | 阶段 | 用途 | 状态 |
|---|---|---|---|
| `outputs/evaluation/portfolio_backtest/portfolio_backtest_report.md` | M4 | 组合级资金曲线初版 | 待纳入 M4 验收包 |
| `outputs/evaluation/portfolio_backtest/m4_stability_report.md` | M4 | 组合稳定性和贡献归因 | 待纳入 M4 验收包 |
| `outputs/evaluation/m5_signal_count/m5_signal_count_report.md` | M5 | Top1/Top2/Top3 出手数量比较 | 已支持“简单切换不入主线”结论 |
| `outputs/evaluation/m5_signal_count_portfolio/m5_signal_count_portfolio_report.md` | M5 | 出手数量策略组合回测 | 已支持固定 Top3 暂时保留 |
| `outputs/evaluation/m5_position_sizing/m5_position_sizing_report.md` | M5 | 仓位调节初筛 | `combined_size_v2` 待复核 |
| `outputs/evaluation/m5_position_sizing_grid/m5_position_sizing_grid_report.md` | M5 | 仓位调节网格 | `combined_size_v2` 待复核 |
| `outputs/evaluation/m5_sizing_robustness/m5_sizing_robustness_report.md` | M5 | `combined_size_v2` 稳健性复核 | 支持作为候选风控开关，正式默认仍待审批 |
| `outputs/final_signals/final_signals_report_combined_size_v2_2025-05_2026-04.md` | M6 | combined_size_v2 最终信号报告 | 候选默认执行信号 |
| `outputs/final_signals/final_signals_report_full_size_2025-05_2026-04.md` | M6 | full_size 最终信号对照报告 | 对照执行信号 |

## 实验产物

| 报告 | 用途 |
|---|---|
| `outputs/evaluation/m3_risk_control_report.md` | M3 风险控制实验 |
| `outputs/evaluation/m5_market_gate_report.md` | M5 市场 gate/no-trade 实验 |
| `outputs/evaluation/rank_failure_analysis.md` | 排序失败样本分析 |
| `outputs/evaluation/rerank_strategy_summary.md` | 旧 rerank 策略汇总 |
| `outputs/evaluation/rerank_walk_forward/rerank_strategy_summary.md` | walk-forward rerank 策略汇总 |
| `outputs/evaluation/m3_recall_feature_gap_report.md` | 特征缺口分析 |
| `outputs/evaluation/m3_top50_diagnostic_report.md` | Top50 诊断 |
| `outputs/evaluation/data_quality_report.md` | 数据质量检查 |
| `outputs/evaluation/baseline_summary.md` | 单次 baseline 汇总 |

## 历史/烟测

| 报告 | 用途 |
|---|---|
| `outputs/evaluation/smoke_old_2025_05/baseline_summary.md` | 历史烟测 |
| `outputs/evaluation/smoke_tiebreak_2025_05/baseline_summary.md` | tiebreak 烟测 |
| `outputs/evaluation/smoke_top50_classifier_eval/baseline_summary.md` | top50 classifier 烟测 |
| `outputs/evaluation/walk_forward/*/baseline_summary.md` | 月度 walk-forward 明细，需结合 `walk_forward_summary.md` 使用 |
| `outputs/evaluation/portfolio_backtest_top1/portfolio_backtest_report.md` | Top1 组合对照 |
| `outputs/evaluation/portfolio_backtest_top2/portfolio_backtest_report.md` | Top2 组合对照 |
| `outputs/evaluation/portfolio_backtest_top3/portfolio_backtest_report.md` | Top3 组合对照 |

## 维护规则

- 新增正式报告时，必须补到本索引。
- 实验报告升格为正式依据前，需要 Gate Review 或 CR/审批记录。
- 验收报告引用 `outputs/evaluation/` 产物时，应优先引用本索引中的正式依据或候选依据。
