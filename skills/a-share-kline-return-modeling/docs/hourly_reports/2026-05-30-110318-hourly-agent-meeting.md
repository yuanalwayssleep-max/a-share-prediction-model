# PMP-lite 多 Agent 小时报会议

记录时间：2026-05-30 11:03:18 GMT+8
记录人：default
参与角色：pm / rd / qa / user / default
项目路径：/Users/cocoon/Documents/code/a-share-prediction-model
报告类型：小时会 / Gate Review / 会后最小闭环推进

## 本小时目标

组织 pm、rd、qa、user 进行 PMP-lite 小时报会议，检查当前项目进度、风险、卡点与解决方案；会议后只推进 1 个最小闭环工作项，避免无边界展开。

## 输入材料

- `git status --short` 当前工作区状态。
- 最近小时报：`docs/hourly_reports/2026-05-30-0902-team-weekly-hourly-report.md`。
- 最近小时报：`docs/hourly_reports/2026-05-30-0856-pm-progress-review.md`。
- `skills/a-share-kline-return-modeling/STATUS.md`。
- `skills/a-share-kline-return-modeling/docs/report_index.md`。
- `skills/a-share-kline-return-modeling/docs/business_acceptance_criteria.md`。
- `skills/a-share-kline-return-modeling/docs/risk_register.md`。
- `skills/a-share-kline-return-modeling/scripts/23_run_main_pipeline.py`。
- `skills/a-share-kline-return-modeling/tests/test_build_features_contract.py`。
- `skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py`。
- 会后验证命令输出：`python3 skills/a-share-kline-return-modeling/scripts/23_run_main_pipeline.py --skip-build-features --skip-walk-forward --skip-portfolio-backtest`。

未读取或记录 `.env`、token、密钥或完整敏感日志。

## 当前进度

- 当前分支：`main`。
- 工作区存在较多 modified/untracked 文件，包含 README、配置、治理文档、脚本、数据拆分产物、验收报告、测试和输出索引；本次未执行 git commit/push/reset/checkout。
- `STATUS.md` 显示：M3 已通过阶段验收，M4 现金约束组合回测已跑通并完成 P1 口径修正，M5 重新验证后 `full_size` 暂作为执行基准，M6 final signal 已完成 truth-free 防护，M7 已通过编译/特征契约/最终信号契约，M8 已新增主流程一键化入口。
- 当前主线：`top50_classifier + Top50 候选池 + candidate_score Top3 + full_size`。
- 仍待后续处理：P2-001 抽公共包、P2-002 统一 repo root 和默认路径策略、P2-004 增加小样本 fixture 测试与 CI。

## 风险/卡点

| 风险/卡点 | 等级 | Owner | 影响 |
|---|---|---|---|
| M3 默认主线 CR/审批记录仍需正式收口 | 高 | pm / user | 影响主线治理闭环和后续验收口径 |
| 验证窗口已被多轮实验使用 | 高 | pm / rd | 继续调参会污染 12 个月验证结论 |
| 工作区大量 modified/untracked 文件 | 中 | pm / rd | 阶段交付边界和提交归档计划不清晰 |
| 测试仍偏依赖全量现有产物 | 中 | qa / rd | CI 友好度和小样本复现性不足 |
| P2 路径/公共逻辑尚未结构化 | 中 | rd | 后续维护成本和脚本重复风险较高 |

## 解决方案

- 冻结当前 M3/M6/M7 主线口径，不在本验证窗口继续调参。
- 本小时优先做 QA 建议的最小闭环：在跳过重型特征构建、walk-forward、组合回测的前提下运行主流程轻量验证，确认 final signal 生成、最终信号回测、编译检查和两个契约测试仍可通过。
- 下一小时优先考虑 P2-004：新增小样本 fixture 测试或形成 fixture 设计草案；避免直接大规模抽公共包。
- 主线 CR、技术方案、开发计划、标签设计文档修改保持待用户确认，不在本次自动修改。

## 角色分工

| 角色 | 本次结论 |
|---|---|
| pm | V1 主流程已闭环，M3-M7 多数完成；治理风险集中在主线 CR/审批、验证窗口过拟合、工作区交付边界。 |
| rd | 工程主链路已由 `23_run_main_pipeline.py` 串起；防泄漏实现较好；主要技术卡点是公共包、路径策略和小样本 fixture/CI。 |
| qa | 质量门禁已包含编译、特征契约、最终信号契约；建议本小时执行轻量主流程验证，确认质量证据仍可复现。 |
| user | 当前更适合作为研究验证中的短线候选与交易纪律辅助系统；暂接受 `full_size` 为执行基准，`combined_size_v2` 为候选风控开关。 |
| default | 归档会议文档，执行 1 个最小闭环验证项，并把剩余工作写入下一小时关注点。 |

## Gate 结论

```text
Requirements Gate：有条件通过。业务目标和 UAT 边界清晰，但主线 CR/审批仍待确认。
Solution Gate：通过。当前主线和一键化流程可支撑继续工程固化。
Build-complete Gate：本小时轻量验证通过；M8 仍需 P2 小样本 fixture/路径治理。
Acceptance Gate：有条件通过。可作为研究验证/辅助决策，不应表述为可直接实盘自动执行。
Closure Gate：本小时闭环完成，剩余治理和 P2 工程化进入下一小时关注点。
```

## 会后工作计划

本次只推进 1 个最小闭环工作项：运行主流程轻量验证。

命令：

```bash
python3 skills/a-share-kline-return-modeling/scripts/23_run_main_pipeline.py --skip-build-features --skip-walk-forward --skip-portfolio-backtest
```

验收标准：

- final signal 生成完成。
- final signal backtest 完成。
- `py_compile` 覆盖脚本和测试通过。
- `test_build_features_contract.py` 通过。
- `test_final_signal_contract.py` 通过。
- `outputs/evaluation/main_pipeline_summary.json` 和 `outputs/evaluation/main_pipeline_summary.md` 更新生成。

## 实际执行结果

- 已执行轻量主流程验证，退出码 0。
- `test_build_features_contract.py` 输出：`all build feature contract checks passed`。
- `test_final_signal_contract.py` 输出：`all final signal contract checks passed`。
- final signal 回测 smoke 输出 `full_size`：交易数 714，信号日 238，最终资金曲线 2.756132，累计收益 1.756132，最大回撤 -0.099143，正收益月份比例 0.846154，平均暴露 0.963122。
- 已写入/更新：`skills/a-share-kline-return-modeling/outputs/evaluation/main_pipeline_summary.json`。
- 已写入/更新：`skills/a-share-kline-return-modeling/outputs/evaluation/main_pipeline_summary.md`。

## 下一小时关注点

1. 优先推进 P2-004：新增或设计不依赖全量数据的小样本 fixture 测试，覆盖 final signal schema、truth-free guard 和每日实际 pick 数仓位计算。
2. 继续梳理工作区 modified/untracked 文件，形成提交/归档计划；不自动 commit。
3. 评估 P2-002 统一 repo root/默认路径策略的最小安全切入点。
4. 主线 CR/审批仍需用户确认后再改受保护治理文档。

## 需要用户确认的事项

- 是否正式批准 `top50_classifier + candidate_score Top3 + full_size` 作为当前 M3/M6 默认主线，并允许补齐对应 CR/审批记录。
- 是否允许下一步修改受保护的技术方案/开发计划/标签设计相关文档；未确认前只做离线验证、普通报告和普通代码/测试工作。
- 是否需要将当前大量工作区变更整理为一次或多次 git commit；提交动作需用户明确批准。
