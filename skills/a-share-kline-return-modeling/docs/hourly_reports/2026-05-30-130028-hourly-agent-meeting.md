# PMP-lite 多 Agent 小时报会议

记录时间：2026-05-30 13:00:28 GMT+8
记录人：default
参与角色：pm / rd / qa / user / default
项目路径：/Users/cocoon/Documents/code/a-share-prediction-model
报告类型：小时会 / Gate Review / 会后最小闭环推进

## 本小时目标

组织 pm、rd、qa、user 进行 PMP-lite 小时报会议，检查项目进度、风险、卡点和解决方案；会后只推进 1 个最小闭环工作项。本小时按上一份小时报关注点，优先做 `22_backtest_final_signals.py` / portfolio ledger 的每日实际 pick 数离线契约验证，不修改交易口径文档。

## 输入材料

- `git status --short` 当前工作区状态。
- 最近小时报：`skills/a-share-kline-return-modeling/docs/hourly_reports/2026-05-30-121154-hourly-agent-meeting.md`。
- 最近小时报：`skills/a-share-kline-return-modeling/docs/hourly_reports/2026-05-30-110318-hourly-agent-meeting.md`。
- `skills/a-share-kline-return-modeling/STATUS.md`。
- `skills/a-share-kline-return-modeling/scripts/21_generate_final_signals.py`。
- `skills/a-share-kline-return-modeling/scripts/22_backtest_final_signals.py`。
- `skills/a-share-kline-return-modeling/scripts/14_backtest_portfolio_curve.py`。
- `skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py`。
- pm / rd / qa 子角色检查结果。

未读取或记录 `.env`、token、密钥或完整敏感日志。

## 当前进度

- 当前分支：`main`。
- 工作区已有大量 modified/untracked 文件；本次不执行 git commit/push/reset/checkout。
- 当前主线仍为：`top50_classifier + Top50 候选池 + candidate_score Top3 + full_size`。
- 上一小时已完成 P2-004 的一个小样本 fixture：final signal 生成按每日实际 pick 数分配 `suggested_position_weight`，并通过相关测试。
- 本小时进一步检查回测侧：`22_backtest_final_signals.py` 传入 `top_n=int(daily_pick_count.max())`，但 `14_backtest_portfolio_curve.py::build_ledger` 当前实际按每日 ledger 条数计算 `target_weight`。

## 风险/卡点

| 风险/卡点 | 等级 | Owner | 影响 |
|---|---|---|---|
| M3 默认主线 CR/审批记录仍需正式收口 | 高 | pm / user | 影响主线治理闭环和后续验收口径 |
| 验证窗口已被多轮实验使用 | 高 | pm / rd | 继续调参会污染 12 个月验证结论 |
| 工作区大量 modified/untracked 文件 | 中 | pm / rd | 阶段交付边界和提交归档计划不清晰 |
| 测试仍部分依赖全量现有产物 | 中 | qa / rd | CI 友好度和干净环境复现性不足 |
| 回测侧 `top_n` 参数语义噪音 | 中 | rd / qa | 未来若 `build_ledger` 重新使用 `top_n`，可能引入少量候选日仓位偏差 |

## 解决方案

- 冻结当前主线模型与交易口径，不在本验证窗口继续调参。
- 不修改技术方案、开发计划、标签设计等受保护文档；主线 CR/审批继续等待用户确认。
- 本小时只推进 1 个最小闭环：为 portfolio ledger 增加纯内存契约测试，证明回测侧 `target_weight` 按每日实际 pick 数计算。
- 若测试失败，仅做最小普通代码修复；若测试通过，不扩大范围为重构或文档改版。

## 角色分工

| 角色 | 本次结论 |
|---|---|
| pm | M3-M8 主链路基本闭环；Build-complete 维持通过，Acceptance 有条件通过；治理风险仍集中在主线 CR/审批、验证窗口过拟合和工作区交付边界。 |
| rd | final signal 生成侧已按每日实际 pick 数修复；回测侧 `build_ledger` 实际也按每日实际条数算 `target_weight`，但 `top_n=max()` 是语义噪音，建议用契约测试固化。 |
| qa | 当前测试目录覆盖 final signal 和 build features 基本契约；缺口仍是更多纯小样本 fixture、CI 友好度，以及回测侧少量候选日仓位契约。 |
| user | 业务侧仍将系统定位为研究验证中的短线候选与交易纪律辅助，不表述为自动实盘执行系统；关注可解释性、风险边界和可复现报告。 |
| default | 归档会议文档，执行 1 个最小闭环测试固化项，并把剩余事项写入下一小时关注点。 |

## Gate 结论

```text
Requirements Gate：有条件通过。业务目标和 UAT 边界清晰，但主线 CR/审批仍待确认。
Solution Gate：通过。本小时只补回测侧小样本契约，不触碰受保护方案文档。
Build-complete Gate：通过。本小时新增 portfolio ledger 每日实际 pick 数仓位契约后，相关测试通过。
Acceptance Gate：有条件通过。工程质量证据继续增强；业务默认主线和受保护治理文档仍需用户确认。
Closure Gate：本小时闭环完成，剩余治理、CI/fixture 和语义清理进入下一小时关注点。
```

## 会后工作计划

本次只推进 1 个最小闭环工作项：P2-004 回测侧每日实际 pick 数仓位契约。

验收标准：

- 新增纯内存测试，不依赖全量 final signal 或全量特征文件。
- 构造 2 个交易日，其中 1 天实际 pick 数少于 `top_n`。
- 验证 `build_ledger` 每日 `target_weight` 总和等于 `1 / hold_sleeves`。
- 验证单 pick 日单笔 `target_weight` 等于 `0.2`，双 pick 日每笔等于 `0.1`。
- 运行 final signal 契约测试和当前测试目录验证。

## 实际执行结果

- 已在 `skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py` 新增纯内存测试：`test_backtest_ledger_uses_actual_daily_pick_count_for_target_weight`。
- 新测试构造 2 个交易日，其中 1 天只有 1 个 pick、1 天有 2 个 pick，并以 `top_n=3` 调用 `14_backtest_portfolio_curve.py::build_ledger`。
- 验证结果：单 pick 日 `target_weight` 为 `0.2`；双 pick 日每笔 `target_weight` 为 `0.1`；每日 `target_weight` 总和均为 `0.2`，证明回测侧当前按每日实际 pick 数分配目标仓位。
- 同步更新 plain python 入口测试列表，避免非 pytest 执行漏跑新增契约。
- 验证命令 `python3 -m pytest skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py -q` 通过：`6 passed in 0.60s`。
- 验证命令 `python3 skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py` 通过，输出 `all final signal contract checks passed`。
- 验证命令 `python3 -m pytest skills/a-share-kline-return-modeling/tests -q` 通过：`10 passed in 1.40s`。

## 下一小时关注点

1. 继续 P2-004：补 `build_features` 更小样本 fixture 或 CI 执行说明。
2. 评估是否清理 `22_backtest_final_signals.py` 中 `top_n=max(daily_pick_count)` 的语义噪音；若涉及交易口径或方案文档，先形成 CR 草案，不直接改受保护文档。
3. 继续梳理大量 modified/untracked 文件，形成提交/归档计划；不自动 commit。
4. 主线 CR/审批仍需用户确认后再改受保护治理文档。

## 需要用户确认的事项

- 是否正式批准 `top50_classifier + candidate_score Top3 + full_size` 作为当前 M3/M6 默认主线，并允许补齐对应 CR/审批记录。
- 是否允许修改技术方案、开发计划、标签设计等受保护文档；未确认前只做离线验证、普通报告和普通代码/测试工作。
- 是否需要将当前大量工作区变更整理为一次或多次 git commit；提交动作需用户明确批准。
