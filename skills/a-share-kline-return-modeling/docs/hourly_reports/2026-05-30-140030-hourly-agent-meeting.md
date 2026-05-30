# PMP-lite 多 Agent 小时报会议

记录时间：2026-05-30 14:00:30 GMT+8
记录人：default
参与角色：pm / rd / qa / UA / default
项目路径：/Users/cocoon/Documents/code/a-share-prediction-model
报告类型：小时会 / Gate Review / 会后最小闭环推进

## 本小时目标

组织 pm、rd、qa、UA 进行 PMP-lite 小时报会议，检查项目进度、风险、卡点和解决方案；会后只推进 1 个最小闭环工作项。本小时按上一份小时报关注点，继续 P2-004，补一个 `build_features` 纯内存小样本 fixture，减少对全量数据产物的测试依赖。

## 输入材料

- `git status --short` 当前工作区状态。
- 最近小时报：`skills/a-share-kline-return-modeling/docs/hourly_reports/2026-05-30-130028-hourly-agent-meeting.md`。
- `skills/a-share-kline-return-modeling/STATUS.md`。
- `skills/a-share-kline-return-modeling/docs/risk_register.md`。
- `skills/a-share-kline-return-modeling/docs/report_index.md`。
- `skills/a-share-kline-return-modeling/docs/qa_reports/` 最近 QA 报告列表。
- `skills/a-share-kline-return-modeling/tests/test_build_features_contract.py`。
- `skills/a-share-kline-return-modeling/scripts/00_build_features.py`。

未读取或记录 `.env`、token、密钥或完整敏感日志。

## 当前进度

- 当前分支：`main`。
- 工作区仍有大量 modified/untracked 文件；本次不执行 commit/push/reset/checkout。
- 当前主线仍为：`top50_classifier + Top50 候选池 + candidate_score Top3 + full_size`。
- M3-M7 主链路基本闭环，M8 工程固化继续推进。
- 上一小时已完成 final signal 与 backtest ledger 两个每日实际 pick 数仓位契约；当前测试目录此前为 `10 passed`。
- 本小时选定 P2-004 的下一个最小项：`build_features` 的日期/收益标签逻辑增加纯内存 fixture，避免只靠全量 `clean_stock_features.csv` 做契约检查。

## 风险/卡点

| 风险/卡点 | 等级 | Owner | 影响 |
|---|---|---|---|
| M3 默认主线 CR/审批记录仍需正式收口 | 高 | pm / UA | 影响主线治理闭环和后续验收口径 |
| 验证窗口已被多轮实验使用 | 高 | pm / rd | 继续调参会污染 12 个月验证结论 |
| 依赖与运行环境不可复现 | 高 | rd / qa | 测试、CI 和新环境复现仍需继续固化 |
| 工作区大量 modified/untracked 文件 | 中 | pm / rd | 阶段交付边界和提交归档计划不清晰 |
| 测试仍部分依赖全量现有产物 | 中 | qa / rd | CI 友好度和干净环境复现性不足 |

## 解决方案

- 继续冻结当前模型/交易口径，不在验证窗口继续做调参。
- 本小时只推进一个纯测试侧小样本 fixture，不修改受保护技术方案、开发计划、标签设计或交易口径文档。
- 通过 `importlib` 直接加载 `00_build_features.py`，构造 2 只股票、6 个交易日的内存数据，验证 `add_future_labels` 的 T+1 入场、持有期退出、毛收益、日内排序百分位和尾部不可判卷行为。
- 将新增 fixture 加入 plain python 入口列表，保证非 pytest 执行也不会漏跑。

## 角色分工

| 角色 | 本次结论 |
|---|---|
| pm | M8 进入工程固化阶段；本小时继续收敛 P2-004，不扩大到公共包抽取或 repo root 重构。 |
| rd | `00_build_features.py::add_future_labels` 可直接用纯内存 DataFrame 做契约验证；无需重跑全量特征构建。 |
| qa | 测试缺口从最终信号侧转向 build_features 小样本 fixture；新增测试后需跑 focused pytest、plain python 和 tests 目录。 |
| UA | 业务侧继续定位为研究验证中的短线候选与交易纪律辅助；本小时新增质量证据，不改变业务承诺和 UAT 口径。 |
| default | 归档小时会，执行一个最小测试固化项，并把剩余治理/CI/工作区事项带到下一小时。 |

## Gate 结论

```text
Requirements Gate：有条件通过。业务目标和 UAT 边界清晰，但主线 CR/审批仍待确认。
Solution Gate：通过。本小时只补 build_features 纯内存 fixture，不触碰受保护方案文档。
Build-complete Gate：通过。新增测试后 focused、plain python、全测试目录均通过。
Acceptance Gate：有条件通过。工程质量证据继续增强；主线治理和正式审批仍需后续收口。
Closure Gate：本小时闭环完成，剩余 CI/fixture、依赖复现和工作区归档进入下一小时关注点。
```

## 会后工作计划

本次只推进 1 个最小闭环工作项：P2-004 build_features 纯内存 fixture。

验收标准：

- 新增测试不依赖全量 `clean_stock_features.csv` 或输出目录。
- 构造 2 只股票、6 个交易日，验证 T 日信号对应 T+1 入场和持有期退出。
- 验证毛收益计算、`future_5_return_rank_pct` 日内方向、尾部交易日不可形成完整未来收益。
- 新测试加入 `__main__` 手工执行列表。
- 运行 focused pytest、plain python 入口和当前测试目录。

## 实际执行结果

- 已修改 `skills/a-share-kline-return-modeling/tests/test_build_features_contract.py`。
- 新增 `load_build_features_module()`，用 `importlib.util.spec_from_file_location` 加载脚本模块，避免把脚本改造成包或扩大重构。
- 新增测试：`test_add_future_labels_uses_next_trade_day_entry_and_hold_day_exit_fixture`。
- 测试覆盖：T+1 入场日期、持有 2 个交易日退出日期、入/出场可交易标志、`daily_stock_count`、日内 `future_5_return_rank_pct`、两只股票毛收益、尾部样本 `future_5_return` 为空。
- 同步更新 plain python 入口测试列表。
- 验证命令 `python3 -m pytest skills/a-share-kline-return-modeling/tests/test_build_features_contract.py -q` 通过：`5 passed in 1.10s`。
- 验证命令 `python3 skills/a-share-kline-return-modeling/tests/test_build_features_contract.py` 通过：`all build feature contract checks passed`。
- 验证命令 `python3 -m pytest skills/a-share-kline-return-modeling/tests -q` 通过：`11 passed in 1.42s`。

## 下一小时关注点

1. 继续 P2-004：补 CI 执行说明或将更多 truth-free guard 迁移到纯小样本 fixture。
2. 评估是否形成 `22_backtest_final_signals.py` 中 `top_n=max(daily_pick_count)` 语义噪音的普通清理计划；若涉及交易口径，先形成 CR 草案。
3. 梳理大量 modified/untracked 文件，形成提交/归档分组计划；不自动 commit。
4. 更新风险台账中 R-005/R-007 的最新测试证据和交付边界状态。

## 需要用户确认的事项

- 无本小时新增用户决策事项。
- 仍有历史待确认项：是否正式批准 `top50_classifier + candidate_score Top3 + full_size` 作为当前 M3/M6 默认主线，并允许补齐对应 CR/审批记录。
