# Top3 10%收益模型训练流程

## 目标

每日选出最多 3 只可出手股票，目标是未来 5 个交易日收益率 `>= 10%`。

最终输出不是普通预测列表，而是交易信号：

```text
Top3 / Top2 / Top1 / 不出手
```

## 训练流程总览

```text
原始日K数据
  -> 清洗与特征生成
  -> 标签生成
  -> 时间切分
  -> 第一层：10%收益候选模型
  -> 第二层：强度排序模型
  -> 第三层：5%亏损风险模型
  -> 信号层融合
  -> 验证集调参
  -> 冻结方案
  -> 测试集回测
```

## 第一步：数据准备

输入原始数据：

```text
skills/a-share-data-fetching/data/单只股票日k/
skills/a-share-data-fetching/data/指数日K文件/00_核心指数日K.csv
skills/a-share-data-fetching/data/行业日K文件/申万行业日K/
skills/a-share-data-fetching/data/a股快照历史/
```

清洗输出：

```text
data/个股Top3_10pct特征数据.csv
data/指数k线特征数据.csv
data/行业指数特征数据.csv
```

第一版如果还没有单独生成 `个股Top3_10pct特征数据.csv`，可以先在现有 `个股k线特征数据.csv` 基础上追加新标签和新特征。

## 第二步：标签生成

必须生成以下标签字段。

主标签：

```text
label_5d_ge10 = future_5_return >= 0.10
```

辅助标签：

```text
label_5d_ge05 = future_5_return >= 0.05
label_5d_loss05 = future_5_return <= -0.05
daily_future_return_rank = 当日股票按 future_5_return 从高到低排名
daily_future_return_top3_label = daily_future_return_rank <= 3
```

这些字段只允许作为 `y` 或回测答案，禁止进入模型特征 `X`。

## 第三步：时间切分

禁止随机切分。

对每个预测日 `T`：

```text
训练集:
trade_date >= T - 730天
trade_date <  T - 90天
future_5_trade_date < T - 90天

验证集:
trade_date >= T - 90天
trade_date <  T - 10天
future_5_trade_date < T

预测集:
trade_date = T
```

说明：

- 训练集用于拟合模型。
- 验证集用于阈值、候选池大小、模型参数和信号层参数选择。
- 预测集只用于当天预测，不允许用未来标签。

## 第四步：第一层模型，5%收益候选

目标：

```text
y = label_5d_ge05
```

模型：

```text
LightGBM binary classifier
```

输入：

```text
当前推荐：compact60 合法特征 X
```

输出：

```text
prob_5d_ge20
rank_by_prob_5d_ge20
```

作用：

```text
先用未来5日 >=20% 的爆发目标学习强上涨信号，再用 Top3 实际 >=10% 命中率验收。
```

样本权重：

```text
真实未来涨幅越高，正样本权重越大。
future_5_return <= -5% 的负样本提高权重。
如果 <=-5% 的票同时具备强动量、高位、市场/行业相对强等“假强”特征，则进一步提高负样本权重。
```

主脚本输出：

```text
每日 final_return_signal_score 排名前 3
```

当前小闭环记录：

```text
2026-04-15 到 2026-04-30 样本内：
compact40 参数调优后仍明显弱于全量特征。
compact60 + baseline 暂时最好，Top3 >=10% 命中 19/36，<=-5% 亏损 2/36，平均收益 10.41%。
主脚本已收敛为这一套，不继续保留多套研究参数。
下一步必须用其他月份验证，不能直接把这段结果当作样本外结论。
```

## 第五步：第二层模型，强度排序

目标：

```text
在候选池里找未来5日收益最强的股票
```

训练样本：

```text
历史每日第一层候选池
```

训练标签可选：

```text
daily_future_return_top3_label
daily_future_return_rank
future_5_return
```

第一版建议：

```text
LightGBM LambdaRank 或 LightGBM binary classifier
y = daily_future_return_top3_label
```

输出：

```text
strength_score_5d
rank_by_strength_score
```

## 第六步：第三层模型，亏损风险

目标：

```text
避免未来5日亏损超过5%的票
```

训练标签：

```text
y = label_5d_loss05
```

模型：

```text
LightGBM binary classifier
```

输出：

```text
risk_5d_loss05_prob
```

第一版硬规则：

```text
risk_5d_loss05_prob >= 风险阈值，则不能出手
```

风险阈值只允许在验证集上确定。

## 第七步：信号层融合

最终分数：

```text
final_top3_score =
    prob_5d_ge05
  * strength_score_5d
  * (1 - risk_5d_loss05_prob)
```

候选过滤：

```text
prob_5d_ge05 >= ge05_prob_threshold
risk_5d_loss05_prob <= loss05_risk_threshold
市场风险允许
行业风险允许
非ST
流动性达标
```

最终动作：

```text
如果合格候选 >= 3：Top3
如果合格候选 = 2：Top2
如果合格候选 = 1：Top1
如果合格候选 = 0：不出手
```

## 第八步：验证集调参

只用验证集调这些参数：

```text
ge05_prob_threshold
loss05_risk_threshold
candidate_pool_size
final_top3_score_threshold
市场风险阈值
行业风险阈值
```

验证目标优先级：

1. Top3 中 `label_5d_ge10` 命中数量。
2. 每日是否至少命中 1 只 `>=10%`。
3. 平均收益和中位收益。
4. `future_5_return <= -5%` 数量必须可控。
5. 出手天数不能过低。

## 第九步：冻结方案

验证集确定参数后，必须冻结：

```text
特征列表
模型类型
模型参数
候选池大小
概率阈值
风险阈值
信号层规则
```

冻结后才能跑测试集。

禁止一边看测试集结果一边调参数。

## 第十步：测试集回测

例如测试 2026 年 3 月：

```text
测试集 = 2026-03-01 到 2026-03-31
```

逐日滚动预测：

```text
每天只用该日以前且标签已经落地的数据训练
每天输出 Top3 / Top2 / Top1 / 不出手
```

测试集只评价，不调参。

## 输出产物

训练产物：

```text
outputs/training_runs/<run_id>/config.json
outputs/training_runs/<run_id>/feature_columns.json
outputs/training_runs/<run_id>/validation_metrics.csv
outputs/training_runs/<run_id>/test_metrics.csv
```

预测产物：

```text
outputs/stock_10pct_predictions/
outputs/final_signals/
```

核心输出字段：

```text
trade_date
symbol
name
industry
prob_5d_ge10
strength_score_5d
risk_5d_loss05_prob
final_top3_score
signal_rank
signal_action
is_final_signal
future_5_trade_date
future_5_return
label_5d_ge10
label_5d_loss05
```

## 第一版落地顺序

第一阶段只做最小闭环：

1. 在清洗表中增加 `label_5d_ge10`、`label_5d_ge05`、`label_5d_loss05`、`daily_future_return_rank`、`daily_future_return_top3_label`。
2. 写第一层 `prob_5d_ge05` 模型，并加入样本权重。
3. 写第三层 `risk_5d_loss05_prob` 模型。
4. 先用简单强度分：

```text
strength_score_5d = prob_5d_ge05
```

5. 验证集确定阈值。
6. 固定方案跑测试月。

第二阶段再加入真正的强度排序模型。
