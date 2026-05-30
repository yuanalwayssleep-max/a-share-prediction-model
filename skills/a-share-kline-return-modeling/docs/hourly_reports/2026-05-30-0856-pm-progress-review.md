# 小时报：PM 项目进度检查

记录时间：2026-05-30 08:56 GMT+8
记录人：pm
项目阶段：M3 -> M4/M5
报告类型：进度检查 / Gate Review

## 1. 本小时目标

根据用户要求，由 PM 检查 `/Users/cocoon/Documents/code/a-share-prediction-model` 当前项目进度，并将阶段判断、风险和下一步建议沉淀到小时报。

## 2. 输入材料

本次检查为只读进度评估，未修改代码或实验产物。参考材料包括：

- `skills/a-share-kline-return-modeling/STATUS.md`
- `skills/a-share-kline-return-modeling/docs/development_milestones.md`
- `skills/a-share-kline-return-modeling/docs/implementation_plan.md`
- `skills/a-share-kline-return-modeling/docs/m3_acceptance_report.md`
- `skills/a-share-kline-return-modeling/docs/change_request_process.md`
- `skills/a-share-kline-return-modeling/docs/change_requests/CR-20260529-001-adjust-m3-target-to-top50-recall-rerank.md`
- `skills/a-share-kline-return-modeling/docs/change_requests/CR-20260529-002-adjust-m3a-to-top30-recall-oriented-training.md`
- `skills/a-share-kline-return-modeling/outputs/evaluation/` 下的 walk-forward、recall、rerank、weak-month、market-gating 相关报告
- `git status --short` 的工作区状态摘要

未读取或记录 `.env`、token、密钥或敏感日志。

## 3. 当前结论

项目已完成 M0-M3 主体建设，并完成 12 个月 walk-forward 初验；当前 PM 建议为：**M3 有条件通过，准备进入 M4 组合级资金曲线 / M5 出手数量调节 Gate Review**。

当前主线为：

```text
LightGBMClassifier / label_top50
Top50 候选池召回
candidate_score 二次排序选 Top3
```

核心结果摘要：

```text
验证范围：2025-05 至 2026-04
平均 Top3 收益：约 2.77%
平均 Top30 命中：约 0.81 / 3
正收益月份：10 / 12
收益优于随机月份：10 / 12
Top30 命中优于随机月份：10 / 12
```

## 4. WBS 进度

| 工作包 | 状态 | 证据/说明 | 下一步 |
|---|---|---|---|
| M0 项目基线 | 基本完成 | `configs/backtest.yaml` 已固定 T 日信号、T+1 open 买入、T+6 open 卖出、5 日持有、成本/滑点/流动性等口径 | 保持冻结，后续变更走 CR |
| M1 特征与标签 | 完成度较高 | 数据质量报告显示约 228 只股票、725 个交易日、72,800 行，覆盖 2023-05-26 至 2026-05-26 | 保持标签和 rank 方向防回归检查 |
| M2 评估与基准 | 已跑通 | 已有 Top3 评估、walk-forward、baseline compare、bootstrap、monthly/daily/portfolio curve 等评估产物 | 将组合级指标纳入正式 gate |
| M3 个股排序模型 | 有条件通过 | `top50_classifier + candidate_score Top3` 在 12 个月验证中显著优于随机 | 补主线变更审批记录，冻结 M3 默认口径 |
| M4 Walk-forward / 组合级回测 | 初验完成，正式验收未闭环 | 已完成 2025-05 至 2026-04 12 个月 walk-forward；组合级资金曲线、仓位占用、回撤等尚需正式确认 | 生成 M4 组合级验收包 |
| M5 市场机会 / 出手控制 | 已有初筛，未通过简单 no-trade gate | 简单 gating 提高 active day 收益，但按跳过日现金收益计整体低于 no_gate | 改做 Top3/Top2/Top1 动态出手数量调节 |
| M6 信号层 | 未正式启动 | 已有信号链路基础，但最终信号字段和风控开关未收口 | 明确最终信号文件字段，禁止 truth/future/label 泄漏 |
| M7 测试固化 | 不足 | 当前测试覆盖偏少，主要只有 contract 类测试 | 补 walk-forward、防泄漏、成本、组合回测小样本测试 |

## 5. 风险与阻塞

| 风险/阻塞 | 等级 | 影响 | Owner | 建议动作 |
|---|---|---|---|---|
| 主线变更治理不一致 | 高 | CR 曾注明不替换主模型，但当前 `top50_classifier` 已成为默认主线，流程和实现存在口径冲突 | pm | 补 CR 或审批记录，确认是否正式批准为 M3 主线 |
| 验证集过拟合 | 高 | 12 个月窗口已被多轮实验反复使用，继续硬调会污染评估 | pm / rd | 冻结 M3 口径，不再用当前窗口反向调参 |
| 组合级风险未闭环 | 高 | 当前结论偏信号级，资金曲线、回撤、仓位占用等未正式 gate | rd / pm | 生成 M4 组合级验收包 |
| 收益分布依赖强月份 | 中 | 2026-02/04 等强月份对均值贡献较大，弱月份仍需复盘 | rd | 针对 2025-06、2025-07、2025-09、2025-11 做月度归因 |
| 工程测试固化不足 | 中 | 后续容易出现口径回归、泄漏字段混入或评估不可复现 | rd | 提前补 M7 小样本测试和 contract 测试 |
| 工作区未提交变更较多 | 中 | 阶段交付物边界不清，后续难以复盘 | pm / rd | 做一次变更归档、审查和提交计划 |

## 6. Gate 结论

```text
建议结论：M3 有条件通过，允许进入 M4/M5。

通过条件：
1. 补齐 top50_classifier 成为默认主线的 CR 或审批记录。
2. 冻结 M3 默认口径，不继续在当前 12 个月验证窗口上硬调 Top3 排序。
3. 归档并提交当前阶段相关变更。
4. 用组合级报告验证 M3 信号转组合后仍具备风险收益优势。

下一阶段准入条件：
1. M4 必须输出组合级资金曲线、累计/年化收益、最大回撤、仓位占用、现金比例、未成交率、延迟卖出影响、月度归因。
2. M5 不采用简单 no-trade gate 作为默认主线，优先评估 Top3/Top2/Top1 动态出手数量调节。
```

## 7. 决策与变更

- 已确认决策：M3 当前不继续硬调复杂 Top3 排序。
- 已确认决策：简单 M5 no-trade gate 当前不作为默认主线。
- 待确认决策：是否正式批准 `top50_classifier + candidate_score Top3` 替代/升级为 M3 默认主线。
- 是否需要 CR：是。
- CR 编号：建议复核并补充 `CR-20260529-002-adjust-m3a-to-top30-recall-oriented-training.md`，或新建一份专门确认 M3 主线升级的 CR。

## 8. 下一小时/下一阶段动作

1. PM：补齐 M3 主线变更审批记录，明确 `top50_classifier + candidate_score Top3` 是否正式成为主线。
2. RD：生成 M4 组合级验收包，覆盖资金曲线、回撤、仓位、现金、成交失败和月度归因。
3. RD：设计 M5 Top3/Top2/Top1 动态出手数量调节实验，不继续押注简单 no-trade gate。
4. PM/RD：整理当前未提交变更，区分文档、脚本、输出产物和临时实验，制定提交/归档计划。
5. RD：提前补 M7 测试，尤其是 walk-forward 切分、防泄漏、成本计算、信号文件和组合回测小样本测试。

## 9. 备注

本次 PM 检查未创建或修改代码；本小时报由 default 根据 PM 检查结论写入。项目当前不是缺进度，而是需要把已完成的实验成果正式收口成阶段交付物，避免继续进入无边界炼丹。