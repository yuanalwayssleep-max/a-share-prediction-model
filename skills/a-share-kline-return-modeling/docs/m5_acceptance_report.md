# M5 出手数量与仓位调节验收报告

状态：草案
更新时间：2026-05-30 GMT+8

## 1. 验收目标

验证是否需要在固定 Top3 基础上引入动态出手数量、no-trade gate 或仓位调节，以改善风险收益、弱月表现和最大回撤。

## 2. 当前结论

```text
M5 初筛已完成，但尚未完成正式验收。
当前 Gate 结论：简单 Top1/Top2/Top3 切换暂不进入主线；仓位调节 combined_size_v2 可继续复核。
```

初版结果来自：

```text
outputs/evaluation/m5_signal_count/m5_signal_count_report.md
outputs/evaluation/m5_signal_count_portfolio/m5_signal_count_portfolio_report.md
outputs/evaluation/m5_position_sizing/m5_position_sizing_report.md
outputs/evaluation/m5_position_sizing_grid/m5_position_sizing_grid_report.md
```

## 3. 当前对照策略

| 策略 | 说明 | 当前状态 |
|---|---|---|
| fixed_top3 | 每日固定选 Top3 | 当前默认 |
| fixed_top2 | 每日固定选 Top2 | 对照，不入主线 |
| fixed_top1 | 每日固定选 Top1 | 对照，不入主线 |
| lag_density_tier | 基于滞后市场密度动态选数量 | 初筛不优 |
| combined_opportunity_tier | 多指标机会分层动态选数量 | 初筛不优 |
| full_size | 固定满额新仓 | 当前组合基线 |
| combined_size_v2 | 低/中/高机会日调整新仓规模 | 候选，待复核 |

## 4. 已知结果

### 出手数量组合回测

| 策略 | 最终资金曲线 | 最大回撤 | 当前判断 |
|---|---:|---:|---|
| fixed_top3 | 2.8183 | -9.91% | 暂时保留默认 |
| lag_density_tier | 2.7204 | -19.15% | 不优 |
| combined_opportunity_tier | 2.6627 | -10.75% | 不优 |
| fixed_top2 | 2.4351 | -16.09% | 不优 |
| fixed_top1 | 2.3954 | -22.18% | 不优 |

### 仓位调节初筛

| 策略 | 最终资金曲线 | 最大回撤 | 平均仓位系数 | 当前判断 |
|---|---:|---:|---:|---|
| full_size | 2.8183 | -9.91% | 1.0000 | 基线 |
| combined_size_v2 | 2.8345 | -9.71% | 0.9566 | 候选，待复核 |

`combined_size_v2` 初版规则：

```text
低机会日新仓 50%，中机会日新仓 90%，高机会日新仓 100%。
高机会：market_up_ratio <= 0.40，或 market_volatility_5 >= 0.027，或 market_10pct_density_ma5_lag1 >= 0.064。
中机会：market_up_ratio <= 0.60，或 market_volatility_5 >= 0.024，或 market_10pct_density_ma5_lag1 >= 0.042。
```

## 5. 待补验收项

| 验收项 | 状态 | 说明 |
|---|---|---|
| 弱月表现对比 | 待补 | 重点看 2025-09、2025-11 等弱月份是否改善 |
| 强月收益保留度 | 待补 | 确认风控没有明显牺牲强月收益 |
| 回撤期间表现 | 待补 | 聚焦 2025-09-05 至 2026-01-07 回撤区间 |
| 行业/个股重复暴露 | 待补 | 判断仓位调节是否实际降低集中风险 |
| 参数稳定性 | 待补 | 检查阈值是否依赖当前验证窗口 |
| 新窗口复核 | 待补 | 防止在 12 个月验证窗口上过拟合 |
| 主线接入成本 | 待补 | 明确是否影响最终信号文件和执行规则 |

## 6. 风险

- `combined_size_v2` 增益幅度较小，可能是窗口内噪声。
- 使用市场指标做机会分层时，必须确认全部字段在 T 日可获得，不能引入未来信息。
- 若把仓位调节接入最终信号层，需要额外定义信号字段 contract 和执行口径。

## 7. Gate 结论

```text
当前 M5 Gate：简单出手数量切换不通过；仓位调节方向允许继续实验，不进入主信号层。
```

正式通过条件：

1. `combined_size_v2` 或其他候选策略在弱月、回撤和新窗口上有稳定改善。
2. 不显著牺牲强月收益。
3. 所用字段全部满足 T 日可得和防泄漏要求。
4. 明确最终信号层是否输出仓位系数，以及字段 contract。
5. 由 PM 在 Gate Review 中记录采纳/拒绝结论。

## 8. 下一步

1. RD：复核 `combined_size_v2` 的弱月、回撤和参数稳定性。
2. RD：补行业/个股重复暴露检查。
3. PM：若策略准备进入主线，先组织 CR 或 Gate Review。
4. User/UAT：确认动态仓位是否符合“可理解、可执行、不频繁变脸”的使用要求。
