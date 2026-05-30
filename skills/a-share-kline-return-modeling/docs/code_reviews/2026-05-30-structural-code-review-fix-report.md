# 结构性代码审查修复报告

日期：2026-05-30 GMT+8

对应审查报告：

```text
docs/code_reviews/2026-05-30-structural-code-review.md
```

## 修复范围

本次优先处理 P0/P1 和低风险 P2 防护项，目标是先把执行链路的数据边界和回测口径收紧。

已处理：

```text
P0-001 市场 signal/truth 拆分
P0-002 最终信号禁止 truth 输入
P1-001 组合回测只读 truth-free predictions
P1-002 月度收益使用上月末权益口径
P1-003 最终信号回测按每日实际 pick 数计仓
P1-004 二分类单类别训练保护
P2-003 配置解析和模型 fallback 收窄异常捕获
```

暂未处理：

```text
P2-001 抽 src/a_share_kline 公共包
P2-002 统一路径策略
P2-004 小样本 fixture 测试和 CI
```

## 关键实现

### 市场特征拆分

`00_build_features.py` 现在同时输出：

```text
data/clean_market_features.csv       兼容旧报告/实验的混合文件
data/market_signal_features.csv      执行链路使用的 truth-free 市场信号
data/market_truth_labels.csv         判卷/分析使用的市场 truth
```

同时修正 `market_10pct_density_ma5_lag1` / `market_10pct_density_ma10_lag1` 的可知性：

```text
label_known_lag = holding_trade_days + 1
```

含义：5日未来标签只有持有窗口结束后才可知，不能用 `shift(1)` 当作 T 日信号。

### 最终信号防泄漏

`21_generate_final_signals.py`：

```text
删除 --use-truth-input
只读取 predictions.csv
默认市场输入改为 data/market_signal_features.csv
预测输入、市场输入、最终输出均校验 forbidden truth columns
```

禁止字段包括：

```text
future_* / label_* / actual_* / entry_price / exit_price / gross_future_5_return
```

### 回测口径修复

`14_backtest_portfolio_curve.py`：

```text
默认读取 predictions.csv
truth 只从 clean_stock_features.csv 合并
月收益使用 previous month end / current month end
每日仓位按实际 pick 数计算
```

`22_backtest_final_signals.py`：

```text
按信号文件每日实际 pick 数回测
月收益复用修正后的 summarize_monthly
兼容 position_size_multiplier -> size_multiplier
```

### 训练健壮性

`01_train_stock_rank_model.py`：

```text
top30_classifier / top50_classifier / rank-pct classifiers 统一做单类别检查
单类别 anchor 跳过并写入 diagnostics
```

## 重跑结果

### M3 Walk-forward

范围：2025-05 至 2026-04

```text
平均 Top3 5日收益：2.75%
平均 Top30 命中数：0.801 / 3
收益优于随机月份：10 / 12
Top30 命中优于随机月份：10 / 12
```

2025-05 因单类别保护，预测交易日从 19 天变为 15 天。

### M5/M6 回测

防泄漏修复后重新验证：

```text
full_size final equity：2.7561
full_size max drawdown：-9.91%

combined_size_v2 final equity：2.6792
combined_size_v2 max drawdown：-9.75%
```

结论：

```text
combined_size_v2 在修正 market lag 后不再优于 full_size。
当前执行基准恢复为 full_size；combined_size_v2 仅保留为候选风险开关。
```

## 验证命令

```bash
python3 skills/a-share-kline-return-modeling/scripts/00_build_features.py
python3 skills/a-share-kline-return-modeling/scripts/05_run_walk_forward.py --start-month 2025-05 --end-month 2026-04 --top-n-train 50 --top-n-eval 3 --model-mode top50_classifier
python3 skills/a-share-kline-return-modeling/scripts/18_backtest_position_sizing_policies.py
python3 skills/a-share-kline-return-modeling/scripts/19_grid_position_sizing_policies.py
python3 skills/a-share-kline-return-modeling/scripts/20_review_m5_sizing_robustness.py
python3 skills/a-share-kline-return-modeling/scripts/21_generate_final_signals.py --start-period 2025-05 --end-period 2026-04 --position-policy combined_size_v2
python3 skills/a-share-kline-return-modeling/scripts/21_generate_final_signals.py --start-period 2025-05 --end-period 2026-04 --position-policy full_size
python3 skills/a-share-kline-return-modeling/scripts/22_backtest_final_signals.py skills/a-share-kline-return-modeling/outputs/final_signals/final_signals_combined_size_v2_2025-05_2026-04.csv skills/a-share-kline-return-modeling/outputs/final_signals/final_signals_full_size_2025-05_2026-04.csv
python3 -m py_compile skills/a-share-kline-return-modeling/scripts/*.py skills/a-share-kline-return-modeling/tests/*.py
python3 skills/a-share-kline-return-modeling/tests/test_build_features_contract.py
python3 skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py
```

验证结果：通过。
