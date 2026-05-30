# PMP-lite 多 Agent 小时报会议

记录时间：2026-05-30 12:11:54 GMT+8
记录人：default
参与角色：pm / rd / qa / user / default
项目路径：/Users/cocoon/Documents/code/a-share-prediction-model
报告类型：小时会 / Gate Review / 会后最小闭环推进

## 本小时目标

组织 pm、rd、qa、user 进行 PMP-lite 小时报会议，检查项目进度、风险、卡点和解决方案；会后只推进 1 个最小闭环工作项。本小时按上一份小时报关注点，优先处理 P2-004 小样本 fixture 测试。

## 输入材料

- `git status --short` 当前工作区状态。
- 最近小时报：`skills/a-share-kline-return-modeling/docs/hourly_reports/2026-05-30-110318-hourly-agent-meeting.md`。
- `skills/a-share-kline-return-modeling/STATUS.md`。
- `skills/a-share-kline-return-modeling/docs/report_index.md`。
- `skills/a-share-kline-return-modeling/docs/risk_register.md`。
- `skills/a-share-kline-return-modeling/docs/decision_log.md`。
- `skills/a-share-kline-return-modeling/scripts/21_generate_final_signals.py`。
- `skills/a-share-kline-return-modeling/scripts/22_backtest_final_signals.py`。
- `skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py`。
- `skills/a-share-kline-return-modeling/tests/test_build_features_contract.py`。

未读取或记录 `.env`、token、密钥或完整敏感日志。

## 当前进度

- 当前分支：`main`。
- 工作区已有大量 modified/untracked 文件；本次未执行 git commit/push/reset/checkout。
- 上一小时轻量主流程验证通过，M8 一键化入口已可复用既有 walk-forward 产物刷新 final signal、回测与测试摘要。
- 当前主线仍为：`top50_classifier + Top50 候选池 + candidate_score Top3 + full_size`。
- P2 待办仍集中在公共包抽取、repo root/默认路径策略、小样本 fixture 与 CI；本小时优先推进 P2-004。

## 风险/卡点

| 风险/卡点 | 等级 | Owner | 影响 |
|---|---|---|---|
| M3 默认主线 CR/审批记录仍需正式收口 | 高 | pm / user | 影响主线治理闭环和后续验收口径 |
| 验证窗口已被多轮实验使用 | 高 | pm / rd | 继续调参会污染 12 个月验证结论 |
| 工作区大量 modified/untracked 文件 | 中 | pm / rd | 阶段交付边界和提交归档计划不清晰 |
| 测试仍部分依赖全量现有产物 | 中 | qa / rd | CI 友好度和干净环境复现性不足 |
| 最终信号实际 pick 数不足 TopN 的仓位契约此前未被显式覆盖 | 中 | qa / rd | 少量候选日可能低估当日目标暴露 |

## 解决方案

- 冻结当前主线模型与交易口径，不在本验证窗口继续调参。
- 不修改技术方案、开发计划、标签设计等受保护文档；主线 CR/审批继续等待用户确认。
- 本小时只推进 P2-004 的一个最小闭环：补一个纯内存小样本契约测试，覆盖 final signal 在每日实际 pick 数小于 `top_n` 时的仓位分配。
- 若测试暴露缺陷，则只做对应最小修复，不扩展为大规模重构。

## 角色分工

| 角色 | 本次结论 |
|---|---|
| pm | M3-M7 主链路基本闭环，M8 轻量验证已通过；治理风险集中在主线 CR/审批、验证窗口过拟合、工作区交付边界。 |
| rd | `21_generate_final_signals.py` 已有 truth-free guard 和白名单输出；此前 `suggested_position_weight` 按固定 `top_n` 分配，缺少实际 pick 数不足时的显式契约。 |
| qa | 当前测试门禁 `python3 -m pytest skills/a-share-kline-return-modeling/tests -q` 通过过一次，结果 `8 passed in 1.51s`；主要缺口是小样本 fixture/CI 和少量候选日仓位契约。 |
| user | 业务侧仍将系统定位为研究验证中的短线候选与交易纪律辅助，不应表述为自动实盘执行系统；关注可解释性、风险边界和可复现报告。 |
| default | 归档会议文档，执行 1 个最小闭环测试/修复项，并把剩余事项写入下一小时关注点。 |

## Gate 结论

```text
Requirements Gate：有条件通过。业务目标和 UAT 边界清晰，但主线 CR/审批仍待确认。
Solution Gate：通过。本小时 P2-004 最小闭环不触碰受保护方案文档。
Build-complete Gate：通过。本小时新增小样本契约并修复实际 pick 数仓位计算后，相关测试通过。
Acceptance Gate：有条件通过。工程质量证据增强；业务默认主线和受保护治理文档仍需用户确认。
Closure Gate：本小时闭环完成，剩余治理和 CI/路径治理进入下一小时关注点。
```

## 会后工作计划

本次只推进 1 个最小闭环工作项：P2-004 final signal 小样本 fixture 契约。

验收标准：

- 新增纯内存测试，不依赖全量最终信号文件来覆盖该边界。
- 构造 2 个交易日，其中 1 天实际 pick 数少于 `top_n`。
- 验证每日 `suggested_position_weight` 总和等于当日 `suggested_new_sleeve_weight`。
- 如发现实现不符合“每日实际 pick 数”口径，做最小代码修复。
- 运行 final signal 契约测试和全量当前测试目录验证。

## 实际执行结果

- 已在 `skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py` 新增小样本测试：`test_build_final_signals_uses_actual_daily_pick_count_for_weights`。
- 新测试首次运行失败，暴露 `skills/a-share-kline-return-modeling/scripts/21_generate_final_signals.py` 仍按固定 `top_n` 分配 `suggested_position_weight`：单 pick 日总仓位为 `0.066666666667`，期望为 `0.2`。
- 已做最小修复：`build_final_signals` 改为按 `out.groupby("trade_date")["symbol"].transform("count")` 得到每日实际 pick 数，再分配 `suggested_position_weight`。
- 验证命令 `python3 -m pytest skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py -q` 通过：`5 passed in 0.59s`。
- 验证命令 `python3 -m pytest skills/a-share-kline-return-modeling/tests -q` 通过：`9 passed in 1.40s`。
- 兼容 plain python 入口验证 `python3 skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py` 通过，输出 `all final signal contract checks passed`。

## 下一小时关注点

1. 继续 P2-004：将更多 truth-free guard / build features 关键逻辑迁移到不依赖全量产物的小样本 fixture，或补 CI 执行说明。
2. 检查 `22_backtest_final_signals.py` 与 portfolio ledger 中 `top_n=int(daily_pick_count.max())` 的影响，确认是否也需要按每日实际 pick 数传递；先做离线测试/报告，不直接改交易口径文档。
3. 继续梳理大量 modified/untracked 文件，形成提交/归档计划；不自动 commit。
4. 主线 CR/审批仍需用户确认后再改受保护治理文档。

## 需要用户确认的事项

- 是否正式批准 `top50_classifier + candidate_score Top3 + full_size` 作为当前 M3/M6 默认主线，并允许补齐对应 CR/审批记录。
- 是否允许修改技术方案、开发计划、标签设计等受保护文档；未确认前只做离线验证、普通报告和普通代码/测试工作。
- 是否需要将当前大量工作区变更整理为一次或多次 git commit；提交动作需用户明确批准。
