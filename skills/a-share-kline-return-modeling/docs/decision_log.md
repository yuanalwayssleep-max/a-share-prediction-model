# 决策记录

更新时间：2026-05-30 GMT+8

## 用途

集中记录项目中已经确认、待确认和被拒绝的重要决策。小时报和 CR 可以记录过程，本文件负责给新参与的 agent 一个“当前应该按什么口径执行”的入口。

## 状态定义

```text
已确认：可以作为当前执行口径。
待确认：已有实验或讨论，但还需要用户、CR 或 Gate Review 确认。
已拒绝：不进入当前主线，但可保留为历史实验依据。
```

## 当前决策

| ID | 决策 | 状态 | 影响范围 | 依据 | 后续动作 |
|---|---|---|---|---|---|
| D-001 | M3 当前执行主线采用 `top50_classifier + candidate_score Top3` | 待确认 | M3/M4/M5 | `STATUS.md`、`docs/m3_acceptance_report.md`、`outputs/evaluation/m3_recall_model_compare.md`、`outputs/evaluation/m3_candidate_rerank_report.md` | 补 CR 或审批记录，治理收口 |
| D-002 | M3 不继续基于同一 12 个月验证窗口硬调复杂 Top3 排序 | 已确认 | M3/M5 | 小时报、M3 验收结论、验证窗口污染风险 | 后续只做组合验证、新窗口复核和稳健性分析 |
| D-003 | 保留 `raw_rank_pct_regression`、`top30_classifier` 等作为回退/对照模式 | 已确认 | M3 | `STATUS.md`、walk-forward 报告 | 不作为默认主线，继续用于对照 |
| D-004 | 简单 no-trade gate 不作为当前默认方向 | 已确认 | M5 | `outputs/evaluation/m5_market_gate_report.md`、小时报结论 | 后续关注风险减仓、弱月识别和仓位调节 |
| D-005 | 固定 Top3 暂时仍是默认出手数量 | 已确认 | M5 | `outputs/evaluation/m5_signal_count/m5_signal_count_report.md`、`outputs/evaluation/m5_signal_count_portfolio/m5_signal_count_portfolio_report.md` | M5 继续比较动态 Top1/2/3 与仓位调节 |
| D-006 | `combined_size_v2` 可作为 M5 候选风控开关继续复核 | 待确认 | M5 | `outputs/evaluation/m5_position_sizing/m5_position_sizing_report.md`、`outputs/evaluation/m5_position_sizing_grid/m5_position_sizing_grid_report.md` | 补稳健性复核、弱月复盘、行业/个股暴露检查 |
| D-007 | 小时报会议采用 PMP-lite 多 agent 模式 | 已确认 | 项目治理 | `docs/hourly_report_process.md`、`docs/hourly_reports/` | 每小时会议记录进度、风险、卡点、方案、执行结果和下一小时关注点 |

## 决策更新规则

- 修改技术方案、开发计划、标签设计文档前，需要用户确认。
- 正常离线实验、报告整理、普通代码修复和测试完善，可以按当前授权自动推进。
- 若决策影响主线模型、验收口径、交易口径、标签定义或输出结构，应补 CR 或 Gate Review 记录。
- 决策关闭时，应补充依据路径，避免“聊天里说过”变成项目考古题。
