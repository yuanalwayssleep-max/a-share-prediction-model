# M4 组合级资金曲线验收报告

状态：草案
更新时间：2026-05-30 GMT+8

## 1. 验收目标

验证 M3 个股排序信号在组合级资金约束下是否仍具备可交易性和风险收益优势，而不是只在单笔或信号级指标上好看。

## 2. 当前结论

```text
M4 初版已跑通，但尚未完成正式验收。
当前 Gate 结论：有条件推进，不作为最终通过。
```

初版结果来自：

```text
outputs/evaluation/portfolio_backtest/portfolio_backtest_report.md
outputs/evaluation/portfolio_backtest/m4_stability_report.md
```

## 3. 当前基线

```text
信号范围：2025-05 至 2026-04
信号策略：Top3
买入：T+1 open
卖出：T+6 open
持有期：5 个交易日
资金约束：每日最多 1/5 资金新开仓，总暴露不超过 100%
资金复用：卖出资金实际退出后复用
成本/滑点/流动性：以 configs/backtest.yaml 为准
```

## 4. 已知结果

| 指标 | 结果 | 来源 |
|---|---:|---|
| 交易数 | 726 | `portfolio_backtest_report.md` |
| 最终资金曲线 | 2.8183 | `portfolio_backtest_report.md` |
| 累计收益 | 181.83% | `portfolio_backtest_report.md` |
| 最大回撤 | -9.91% | `portfolio_backtest_report.md` |
| 单笔平均收益 | 2.48% | `portfolio_backtest_report.md` |
| 单笔胜率 | 52.48% | `portfolio_backtest_report.md` |
| Top5 盈利交易贡献 | 17.79% | `m4_stability_report.md` |
| Top10 盈利交易贡献 | 31.17% | `m4_stability_report.md` |
| Top20 盈利交易贡献 | 50.91% | `m4_stability_report.md` |
| 剔除 Top20 盈利交易后线性收益 | 89.26% | `m4_stability_report.md` |
| 最大回撤区间 | 2025-09-05 至 2026-01-07 | `m4_stability_report.md` |

## 5. 待补验收项

| 验收项 | 状态 | 说明 |
|---|---|---|
| 资金曲线图/表 | 待补 | 需要明确每日权益、现金、持仓市值、总暴露 |
| 月度收益归因 | 待补 | 需要识别弱月、强月、极端贡献 |
| 最大回撤归因 | 待补 | 需要拆解回撤期间行业、个股、信号质量 |
| 仓位占用 | 待补 | 需要统计平均暴露、最大暴露、现金比例 |
| 未成交/延迟卖出影响 | 待补 | 若存在流动性或停牌约束，需要单列 |
| 与信号级 Top3 对齐 | 待补 | 确认组合约束没有改变信号判卷口径 |
| 与固定 Top1/Top2/Top3 对照 | 待补 | 用于 M5 策略比较 |

## 6. 风险

- 当前 M4 结论高度依赖 M3 12 个月验证窗口，需避免继续针对同窗口过拟合。
- 组合曲线初版结果较强，但必须确认不是由少数极端交易贡献。
- 若未来引入仓位调节，需要重新评估最大回撤、现金占用和交易数。

## 7. Gate 结论

```text
当前 M4 Gate：初版通过技术可行性；正式验收暂未通过。
```

通过条件：

1. 补齐资金曲线、月度归因、回撤归因、仓位占用和现金比例。
2. 明确正式引用的输出报告和数据文件。
3. 与 M5 出手数量/仓位调节对照结果形成一致结论。
4. 由 PM 在小时报或 Gate Review 中记录通过结论。

## 8. 下一步

1. RD：补 M4 正式验收包指标。
2. PM：将正式引用报告纳入 `docs/report_index.md`。
3. User/UAT：确认组合级结果是否满足“可交易、可解释、可复核”的接受条件。
