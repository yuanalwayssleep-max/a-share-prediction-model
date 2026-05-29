# Top3可出手模型训练方案

## 目标

每日从股票池中选出最多 3 只可出手股票，目标是未来 5 个交易日收益率达到 `10%` 及以上。

主标签：

```text
label_5d_ge10 = future_5_return >= 0.10
```

辅助标签：

```text
label_5d_ge05 = future_5_return >= 0.05
label_5d_loss05 = future_5_return <= -0.05
daily_future_return_rank
daily_future_return_top3_label
```

所有 `future_*`、`label_*`、`target_*`、`daily_future_*` 字段只能作为训练标签或回测答案，禁止进入模型特征 `X`。

## 整体训练结构

模型拆成三层。

### 第一层：5%候选模型

目标：判断股票未来 5 日收益率是否可能达到 5% 及以上，用来扩大候选池。最终业务目标仍然评价 `label_5d_ge10`。

训练标签：

```text
y = label_5d_ge05
```

输出：

```text
prob_5d_ge05
```

用途：筛出可能涨 5% 以上的股票候选池，再交给强度排序和风险层筛选可出手 Top3。

样本权重：

```text
真实未来涨幅越高，正样本权重越大。
future_5_return <= -5% 的负样本提高权重。
如果 <=-5% 的票同时表现为高位、强动量或相对强势，则作为“假强票”进一步提高负样本权重。
```

### 第二层：强度排序模型

目标：在候选池中判断谁更可能成为当天收益最强的 Top3。

训练标签：

```text
daily_future_return_rank
daily_future_return_top3_label
```

输出：

```text
strength_score_5d
```

用途：在可能上涨的票里找最强的 3 只。

### 第三层：可出手风控模型

目标：过滤未来 5 日可能亏损超过 5% 的票。

训练标签：

```text
y = label_5d_loss05
```

输出：

```text
risk_5d_loss05_prob
```

最终分数：

```text
final_score = prob_5d_ge05 * strength_score_5d * (1 - risk_5d_loss05_prob)
```

最终动作：

```text
Top3 / Top2 / Top1 / 不出手
```

如果候选不足、10%概率不足、风险过高或市场/行业环境不支持，则减少出手数量或不出手。

## 历史窗口

默认使用滚动 2 年历史数据。

对每个预测日 `T`：

```text
候选训练历史 = T 之前 730 天
```

每条训练样本必须满足：

```text
future_5_trade_date < 当前训练/验证截止日
```

原因：

- 1 年窗口对 `5日涨幅 >=10%` 这类稀有标签来说正样本偏少。
- 3 年以上容易混入过旧市场风格。
- 2 年在样本数量和市场风格有效性之间比较平衡。

后续可对比：

```text
365天
540天
730天
900天
```

第一版默认：

```text
lookback_days = 730
```

## 训练集、验证集、测试集切分

不能随机切分，必须按时间切分。

### 单日滚动预测

对每个预测日 `T`：

```text
训练集 train:
trade_date >= T - 730天
trade_date <  T - 90天
future_5_trade_date < T - 90天

验证集 valid:
trade_date >= T - 90天
trade_date <  T - 10天
future_5_trade_date < T

预测集 predict:
trade_date = T
```

说明：

- 训练集和验证集都只能使用标签已经完整落地的样本。
- 验证集不能使用 `future_5_trade_date >= T` 的样本。
- 预测集 `trade_date = T` 只使用当天及以前已知特征，不使用任何未来标签。

### 月度回测

例如测试 2026 年 3 月：

```text
测试区间:
2026-03-01 到 2026-03-31
```

对 3 月每个交易日逐日滚动：

```text
2026-03-02 预测：只用 2026-03-02 以前且标签已落地的数据
2026-03-03 预测：只用 2026-03-03 以前且标签已落地的数据
...
2026-03-31 预测：只用 2026-03-31 以前且标签已落地的数据
```

## 参数选择流程

不能拿测试月份调参。

推荐第一版：

```text
验证月份：2026年1月、2026年2月
测试月份：2026年3月
```

流程：

1. 在 2026 年 1 月、2 月上调特征、阈值和模型结构。
2. 固定方案。
3. 只跑一次 2026 年 3 月测试。
4. 3 月测试结果只用于评价，不用于继续调参。

如果后续要继续优化，需要重新定义新的验证/测试月份，避免反复使用同一个测试月导致样本内过拟合。

## 评估指标

主指标：

```text
Top3 中 label_5d_ge10 命中数量
Top3 命中率 = 命中 label_5d_ge10 的票数 / 出手票数
每日是否至少命中 1 只 >=10%
```

收益指标：

```text
Top1 / Top2 / Top3 平均 future_5_return
Top1 / Top2 / Top3 中位 future_5_return
Top3 最佳票收益
Top3 最差票收益
```

风控指标：

```text
future_5_return <= -5% 的票数
future_5_return <= -3% 的票数
最大单笔亏损
不出手天数
```

业务目标优先级：

1. 找到未来 5 日收益率 `>=10%` 的票。
2. 在这些票中选出最强的 3 只。
3. 避免未来 5 日亏损超过 5% 的票。
4. 候选不足时允许少出手或不出手。

## 禁止事项

以下字段禁止进入模型特征 `X`：

```text
future_5_trade_date
future_5_close
future_5_return
future_5_direction
future_5_up_label
label_5d_ge10
label_5d_ge05
label_5d_loss05
target_*
daily_future_return_rank
daily_future_return_top3_label
```

禁止随机切分训练/测试。

禁止在测试月份调参后再报告该月份效果。

禁止把普通上涨概率当作最终 Top3 可出手概率。
