# 小时周报：多 Agent 团队项目周报

记录时间：2026-05-30 09:02 GMT+8
记录人：default
参与角色：pm / rd / user
项目阶段：M3 -> M4/M5
报告类型：团队小时周报 / 周期进度汇总 / Gate Review 输入

## 1. 本小时目标

组织 `pm`、`rd`、`user` 三个角色分别从项目治理、工程实现、用户验收角度检查 `/Users/cocoon/Documents/code/a-share-prediction-model`，并整合成本次团队小时周报。

## 2. 输入材料

本次团队周报基于各角色只读检查结论整合，未要求任何角色修改文件。参考材料包括：

- `skills/a-share-kline-return-modeling/STATUS.md`
- `skills/a-share-kline-return-modeling/docs/development_milestones.md`
- `skills/a-share-kline-return-modeling/docs/implementation_plan.md`
- `skills/a-share-kline-return-modeling/docs/m3_acceptance_report.md`
- `skills/a-share-kline-return-modeling/docs/hourly_report_process.md`
- `skills/a-share-kline-return-modeling/docs/hourly_reports/2026-05-30-0856-pm-progress-review.md`
- `skills/a-share-kline-return-modeling/docs/change_request_process.md`
- `skills/a-share-kline-return-modeling/docs/change_requests/CR-20260529-001-adjust-m3-target-to-top50-recall-rerank.md`
- `skills/a-share-kline-return-modeling/docs/change_requests/CR-20260529-002-adjust-m3a-to-top30-recall-oriented-training.md`
- `skills/a-share-kline-return-modeling/scripts/01_train_stock_rank_model.py`
- `skills/a-share-kline-return-modeling/scripts/05_run_walk_forward.py`
- `skills/a-share-kline-return-modeling/scripts/07_evaluate_rerank_strategies.py`
- `skills/a-share-kline-return-modeling/scripts/13_evaluate_market_opportunity_gating.py`
- `skills/a-share-kline-return-modeling/scripts/14_backtest_portfolio_curve.py`
- `skills/a-share-kline-return-modeling/outputs/evaluation/` 下的 walk-forward、组合回测、recall、rerank、weak-month、market-gating 相关报告
- `git status --short` 的工作区状态摘要

未记录 `.env`、token、密钥或完整敏感日志。

## 3. 当前团队结论

团队一致判断：**M3 个股排序模型已具备有条件通过基础，允许进入 M4 组合级资金曲线验收与 M5 动态出手数量调节；但 M3 默认主线治理、组合级正式验收包、测试固化和工作区归档必须尽快收口。**

当前主线：

```text
LightGBMClassifier / label_top50
Top50 候选池召回
candidate_score 二次排序选 Top3
```

M3 核心验证结果：

```text
验证范围：2025-05 至 2026-04
平均 Top3 收益：约 2.77%
平均 Top30 命中：约 0.81 / 3
正收益月份：10 / 12
收益优于随机月份：10 / 12
Top30 命中优于随机月份：10 / 12
```

M4 初版组合级结果：

```text
交易数：726
最终资金曲线：2.8183
累计收益：181.83%
最大回撤：-9.91%
单笔平均收益：2.48%
单笔胜率：52.48%
```

## 4. 角色周报

### 4.1 PM/PMO：项目治理与阶段状态

PM 判断本周项目已从 M3 个股排序模型推进到 M4 组合级验证和 M5 出手数量调节准备阶段。M3 在信号级指标上已经满足阶段验收基础，但需要按“有条件通过”收口。

| 治理项 | 当前状态 | PM 判断 | 后续动作 |
|---|---|---|---|
| 阶段计划 | M0-M3 主体完成，M4 初版跑通，M5 已有初筛 | 进度正常，但阶段收口需加强 | 以 M4 组合级验收包作为下一阶段主交付 |
| CR 流程 | 已有 CR-20260529-001、CR-20260529-002 | 默认主线升级仍需复核 | 确认 `top50_classifier + candidate_score Top3` 是否正式批准为默认主线 |
| 验收口径 | T+1 open 买入、T+6 open 卖出、成本滑点、future/label 黑名单已固定 | 口径基本清晰 | 后续变更必须走 CR |
| 工作区状态 | 存在多项已修改和未跟踪文件 | 阶段交付边界不够清晰 | 做一次归档、审查和提交计划 |
| 小时报机制 | 已有规范与 PM 进度检查记录 | 机制可用 | gate review、关键实验、风险变化继续沉淀小时报 |

PM Gate 结论：

```text
M3：通过 / 有条件通过。
M4：初版跑通，暂不建议直接最终通过。
M5：简单 no-trade gate 不作为默认主线。
```

PM 下一阶段优先级：

1. 完成 M3 主线治理收口，确认 `top50_classifier + candidate_score Top3` 的正式默认主线身份。
2. 推动 RD 生成 M4 组合级验收包。
3. 组织当前工作区变更归档和提交计划。
4. 明确 M5 动态出手数量调节实验边界。

### 4.2 RD：工程实现与验证证据

RD 判断当前工程已具备 M3 主线和 M4 初版组合回测能力，但依赖可复现、测试覆盖、CR 治理和组合级验收仍需补强。

关键实现状态：

- `scripts/01_train_stock_rank_model.py` 已支持多模型模式，默认主线为 `top50_classifier`。
- `scripts/05_run_walk_forward.py` 已透传 `--model-mode`，可批量生成月度预测与评估。
- `scripts/07_evaluate_rerank_strategies.py` 支持候选池内二次排序实验。
- `scripts/13_evaluate_market_opportunity_gating.py` 已用于 M5 简单机会过滤初筛，但不建议采纳为默认策略。
- `scripts/14_backtest_portfolio_curve.py` 提供组合级资金曲线模拟能力，输出交易流水、资金曲线、月度汇总和组合回测报告。

RD 验证证据：

- M3 12 个月 walk-forward 主线信号级表现优于随机。
- M4 初版组合级回测已跑通，交易数 726，最终资金曲线 2.8183，累计收益 181.83%，最大回撤 -9.91%。
- `portfolio_curve.csv` 约 247 行，`portfolio_ledger.csv` 约 726 行，`walk_forward_summary.csv` 约 12 行月度数据。
- 当前测试存在 `tests/test_build_features_contract.py`，覆盖 T+1/T+6 日期、成本计算、rank_pct 方向和未来字段泄漏摘要检查。
- 本地 `pytest` 检查因当前 Python 环境缺少 `pandas` 失败，不是业务断言失败。

RD 风险：

| 风险 | 等级 | 说明 | 建议 |
|---|---|---|---|
| 环境可复现不足 | 高 | 未发现标准依赖声明文件，pytest 因缺少 `pandas` 失败 | 增加依赖声明并验证测试环境 |
| 组合级验收不足 | 高 | 初版回测缺少仓位、现金、未成交、延迟卖出、月度回撤归因 | 补 M4 验收包 |
| 测试固化不足 | 中 | 缺少 walk-forward、组合回测、信号文件 contract 测试 | 提前补 M7 测试 |
| 验证窗口污染 | 高 | 12 个月窗口已被多轮实验使用 | 冻结 M3 口径，避免继续硬调 |

RD 下一阶段优先级：

1. 冻结 M3 默认口径，不再基于当前验证窗口继续调参。
2. 补齐 M4 组合级验收包。
3. 推进 M5 Top3/Top2/Top1 动态出手数量实验。
4. 增加依赖声明和核心测试，先保证环境能复现。
5. 对脚本、报告、输出产物分组归档。

### 4.3 User/UAT：用户验收与接受条件

UAT 判断当前项目已经从“模型能不能选出强势个股”推进到“信号能否转化为可执行、可复盘、可控风险的组合收益”。用户侧最关注的是可解释性、稳定性、可执行性、防泄漏和输出清晰度。

UAT 阶段状态：

| 阶段 | UAT 状态 | 用户侧结论 |
|---|---|---|
| M3 个股排序模型 | 有条件接受 | 指标满足进入下一阶段基础，但需冻结口径并补齐主线变更确认 |
| M4 Walk-forward / 组合级回测 | 初步可验，未最终接受 | 组合回测已跑通，但稳定性、现金占用、回撤归因、弱月份解释需补齐 |
| M5 市场机会 / 出手数量 | 暂不接受简单 no-trade gate | 用户更关心动态 Top3/Top2/Top1/不出手是否能减少无效出手 |

UAT 接受前条件：

- M3 必须明确 `top50_classifier + candidate_score Top3` 是否正式成为默认主线。
- M3 必须保留 raw model Top3 基线，避免覆盖后无法比较。
- M4 必须展示组合级资金曲线、累计收益、最大回撤、月度收益、月度回撤、现金约束、仓位占用、未成交率和延迟卖出影响。
- M4 必须解释弱月份和极端贡献日期，证明收益不是单月或少数交易日贡献。
- M5 必须验证 Top3/Top2/Top1/不出手动态机制，而不是简单少交易制造高胜率。
- 最终信号文件不得包含 `future_*`、`label_*`、truth 字段或 T+1 后才可知字段。

UAT 结论：

```text
M3：有条件接受，允许进入 M4/M5。
M4：初版结果可进入验收准备，不建议立即最终通过。
M5：简单 no-trade gate 不接受为默认方案，应改验 Top3/Top2/Top1 动态出手数量。
```

## 5. WBS 综合进度

| 工作包 | 综合状态 | 主要证据 | 下一步 |
|---|---|---|---|
| M0 项目基线 | 已完成 | 回测配置、交易口径、字段黑名单和目录结构已固定 | 保持冻结，变更走 CR |
| M1 特征与标签 | 已完成 | clean 特征、标签、rank_pct、TopK 标签、可交易收益链路已具备 | 继续防止标签方向和未来字段回归 |
| M2 评估与基准 | 已完成 | Top3 评估、baseline compare、bootstrap、monthly/daily 明细已具备 | 将组合级指标纳入正式 gate |
| M3 个股排序模型 | 有条件通过 | 12 个月 walk-forward 显著优于随机和旧 raw 基线 | 冻结口径，补主线治理记录 |
| M4 组合级回测 | 初版跑通，待正式验收 | 组合回测交易数 726，最终资金曲线 2.8183，最大回撤 -9.91% | 生成正式 M4 验收包 |
| M5 市场机会 / 出手控制 | 初筛完成，未入默认主线 | 简单 no-trade gate 全日现金口径不优 | 改做动态出手数量实验 |
| M6 信号层 | 未正式启动 | 最终信号字段和风控开关未收口 | 明确最终信号产物与执行过滤规则 |
| M7 测试固化 | 不足 | 当前测试主要集中在特征构建 contract | 补 walk-forward、防泄漏、成本、组合回测测试 |

## 6. 风险与阻塞

| 风险/阻塞 | 等级 | 影响 | Owner | 建议动作 |
|---|---|---|---|---|
| 主线变更治理不完全闭环 | 高 | CR-002 初始约束与当前默认主线存在不一致风险 | pm | 补审批记录或新建 CR |
| 验证窗口过拟合 | 高 | 12 个月窗口已被多轮实验使用，继续调参会污染结论 | pm / rd | 冻结 M3 口径，后续只做组合验证和新窗口复核 |
| 组合级风险未正式 gate | 高 | 信号级收益不能代表真实可执行组合收益 | rd / pm | 输出 M4 组合级验收包 |
| 环境可复现不足 | 高 | pytest 因缺少 `pandas` 失败，依赖声明不完整 | rd | 增加依赖声明并验证测试环境 |
| 收益贡献可能集中于强月份 | 中 | 2026-02/04 等强月份贡献较明显 | rd | 做月度归因和极端贡献日分析 |
| M5 简单 gate 不适合上线 | 中 | 简单跳过交易日可能牺牲正收益日 | rd / user | 设计动态 Top3/Top2/Top1 策略 |
| 工作区未提交变更多 | 中 | 阶段交付物和临时实验边界不清 | pm / rd | 制定提交、归档、清理计划 |

## 7. Gate 结论

```text
M3 Gate：有条件通过。
M4 Gate：初版通过技术可行性，不通过最终验收；需要正式验收包。
M5 Gate：简单 no-trade 方向暂不通过；动态出手数量方向允许进入设计。

M3 通过条件：
1. 补齐 top50_classifier 成为默认主线的 CR 或审批记录。
2. 冻结 M3 默认口径。
3. 保留 raw baseline 对照。
4. 不再用当前 12 个月窗口继续硬调模型。

M4 下一阶段准入条件：
1. 输出组合级资金曲线、累计/年化收益、最大回撤。
2. 输出仓位占用、现金比例、未成交率、延迟卖出影响。
3. 输出月度归因、弱月份解释、极端贡献日分析。
4. 明确成本、滑点、流动性和现金约束口径。
```

## 8. 决策与变更

已确认决策：

- M3 不继续硬调复杂 Top3 排序。
- `raw_rank_pct_regression` 保留为回退基线。
- 风控过滤暂不进入默认主流程，可作为信号层执行过滤或风控开关。
- 简单 M5 no-trade gate 暂不作为默认主线。
- M5 下一步优先做 Top3/Top2/Top1 动态出手数量调节。

待确认决策：

- 是否正式批准 `top50_classifier + candidate_score Top3` 作为 M3 默认主线。
- M4 组合级验收是否以 `scripts/14_backtest_portfolio_curve.py` 输出为基础。
- 是否加入更严格的成交、滑点、资金占用和行业集中约束。
- 当前未提交变更如何拆分为文档、脚本、输出产物和实验归档。

是否需要 CR：需要复核。若默认主线升级尚未被现有 CR 完整覆盖，建议补一份“确认 M3 默认主线升级”的 CR，或补充 `CR-20260529-002-adjust-m3a-to-top30-recall-oriented-training.md` 的审批记录。

## 9. 下一阶段行动计划

1. PM：完成 M3 主线治理收口，确认 `top50_classifier + candidate_score Top3` 的正式默认主线身份。
2. PM/RD：整理当前工作区变更，拆分为文档、脚本、输出产物和实验归档，制定提交计划。
3. RD：生成 M4 组合级验收包，覆盖资金曲线、回撤、仓位、现金、成交失败、延迟卖出和月度归因。
4. RD：对 2025-06、2025-07、2025-09、2025-11 等弱月份做归因，区分召回弱、排序弱、市场弱。
5. RD：设计 M5 Top3/Top2/Top1 动态出手数量实验，对比 no-gate、简单 no-trade、动态出手数量三类方案。
6. RD：补依赖声明，修复测试环境不可复现问题，并补 M7 核心测试。
7. User/UAT：定义 M4/M5 最终用户验收摘要格式，确保报告能回答“能不能用、风险在哪、亏损月份为什么亏”。

## 10. 备注

本次团队周报由 `default` 组织 `pm`、`rd`、`user` 三个角色完成，各角色均按只读方式检查并提交周报输入。项目当前不是缺实验，而是缺阶段收口。下一轮工作重点应从“继续炼模型”切换到“治理收口、组合验收、测试固化、可复盘交付”。
