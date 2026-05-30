# M7 测试固化验收报告

更新时间：2026-05-30 GMT+8

## 结论

M7 初版测试固化通过。

本阶段新增最终信号层契约测试，覆盖：

```text
最终信号不能输出 truth / future / label 字段
combined_size_v2 仓位规则不能被误改
最终信号文件必须包含执行所需核心字段
truth-free final signal 可以完成回测 smoke
```

## 新增测试

```text
tests/test_final_signal_contract.py
```

测试项：

```text
test_combined_size_v2_tier_rules
test_build_final_signals_excludes_truth_columns
test_existing_final_signal_file_is_truth_free
test_final_signal_backtest_smoke
```

## 已有测试

```text
tests/test_build_features_contract.py
```

继续覆盖：

```text
T+1 / T+6 交易日窗口
成本扣减
rank_pct 方向
signal_known_features 无未来字段
```

## 验证命令

```bash
python3 -m py_compile skills/a-share-kline-return-modeling/scripts/*.py skills/a-share-kline-return-modeling/tests/*.py
python3 skills/a-share-kline-return-modeling/tests/test_build_features_contract.py
python3 skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py
```

## 验证结果

```text
all build feature contract checks passed
all final signal contract checks passed
```

final signal 回测 smoke 结果：

```text
policy: combined_size_v2
trades: 726
signal_days: 242
avg_size_multiplier: 0.956612
final_equity_curve: 2.834496
max_drawdown: -0.097098
max_exposure: 1.0
```

## 当前判断

```text
M7 达到初版阶段目标。
后续如果新增信号字段、仓位规则或回测口径，需要同步补测试。
```
