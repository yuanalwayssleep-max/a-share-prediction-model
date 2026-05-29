# A股5日预测标签设计方案

## 目标

最终目标不是单纯预测涨跌，也不是单纯预测收益率，而是：

> 每天从股票池中选出 Top3，最终这 3 只尽量落入未来 5 日真实收益排名 Top30。

因此标签设计不能只用一个目标，需要分层学习。

## 一、标签分层设计

### 1. 个股方向标签

```text
label_direction = future_5_return > 0
```

用途：

```text
判断股票未来 5 日上涨概率
```

特点：

```text
最稳定
最好学
适合作为主模型
```

### 2. 强势收益标签

用于判断股票是否具备较强弹性。

基础标签：

```text
label_strong_5d = future_5_return >= 10%
```

但由于 `>=10%` 样本较少，不建议单独硬学，可以改成分级标签：

```text
strong_level = 0：future_5_return <= 0
strong_level = 1：0% < future_5_return < 5%
strong_level = 2：5% <= future_5_return < 10%
strong_level = 3：future_5_return >= 10%
```

用途：

```text
判断个股弹性
识别是否有成为强票的可能
```

### 3. Top30 目标标签

贴近最终目标：

```text
label_top30 = future_5_return_rank <= 30
```

用途：

```text
判断股票未来 5 日是否可能进入真实收益排名前 30
```

注意：

```text
不建议单独作为主模型
适合作为辅助模型或信号层校准
```

原因：

```text
Top30 标签边界太硬
第 30 名和第 31 名可能只差 0.1%
但训练时一个是 1，一个是 0
容易产生标签噪声
```

### 4. 市场机会密度标签

用于判断当前环境是否适合积极出手。

```text
market_opportunity_label =
当天之后 5 日内，股票池中 future_5_return >= 10% 的比例
是否高于历史中位数
```

也可以做成连续值：

```text
market_opportunity_density =
当天股票池中 future_5_return >= 10% 的样本占比
```

实际训练时不能直接使用未来值作为特征，只能作为标签。预测时用过去窗口特征去预测它。

用途：

```text
判断当前市场是否容易出现 5 日涨幅超过 10% 的股票
决定当天是 Top3 / Top2 / Top1 / 不出手
```

## 二、推荐模型结构

### 模型A：方向模型

```text
目标：label_direction
```

学习内容：

```text
未来 5 日是否上涨
```

输出：

```text
direction_up_prob
```

### 模型B：强势模型

```text
目标：label_strong_5d 或 strong_level
```

学习内容：

```text
未来 5 日是否有较强弹性
```

输出：

```text
strong_prob
strong_level_score
```

### 模型C：Top30模型

```text
目标：label_top30
```

学习内容：

```text
未来 5 日是否可能进入真实收益排名前 30
```

输出：

```text
top30_prob
```

### 模型D：市场机会密度模型

```text
目标：market_opportunity_label
```

学习内容：

```text
当前市场是否容易出现 5 日大涨机会
```

输出：

```text
market_opportunity_prob
market_opportunity_density_pred
```

## 三、最终个股综合分

建议不要只依赖单一模型，而是融合多个分数：

```text
stock_score =
  0.45 * direction_up_prob
+ 0.30 * strong_prob
+ 0.15 * top30_prob
+ 0.10 * industry_strength_score
- risk_penalty
```

各部分含义：

```text
direction_up_prob：保证胜率
strong_prob：寻找弹性
top30_prob：贴近最终目标
industry_strength_score：加入行业共振
risk_penalty：过滤高位、过热、弱行业、市场风险
```

## 四、信号层决策

信号层不再只看个股分数，还要看市场机会密度和市场风险。

### 机会密度高

```text
允许 Top3
```

条件示例：

```text
market_opportunity_prob 高
market_risk_level 低
Top3 个股分数都达标
```

### 机会密度中等

```text
Top1 或 Top2
```

条件示例：

```text
direction_up_prob 高
strong_prob 一般
market_risk_level 中性
```

### 机会密度低

```text
不出手 或 只出 Top1
```

条件示例：

```text
market_opportunity_prob 低
strong_prob 低
市场缺少 10% 弹性机会
```

### 市场风险高

```text
降级 或 不出手
```

规则示例：

```text
Top3 -> Top1
Top2 -> Top1
Top1 -> 不出手
```

## 五、为什么不只学 Top30

```text
Top30 标签太硬
排名边界噪声大
容易把第 30 名和第 31 名过度区分
```

示例：

```text
第 30 名：future_5_return = 8.10%，标签 = 1
第 31 名：future_5_return = 8.00%，标签 = 0
```

实际差距很小，但模型训练时差异很大。

## 六、为什么不只学涨10%

```text
future_5_return >= 10% 正样本太少
```

例如：

```text
2025-05：4.64%
2026-03：4.83%
2026-05：7.04%
```

如果只学这个标签，模型容易：

```text
过拟合少数强势票
预测概率不稳定
错过普通稳涨票
```

所以 `>=10%` 更适合作为弹性模型，而不是唯一主模型。

## 七、最终推荐主线

```text
方向模型：负责胜率
强势模型：负责弹性
Top30模型：负责目标贴合
市场机会密度模型：负责判断出手环境
信号层：负责 Top3 / Top2 / Top1 / 不出手
```

最终流程：

```text
清洗数据
  ↓
生成方向标签、强势标签、Top30标签、机会密度标签
  ↓
训练个股方向模型
  ↓
训练强势收益模型
  ↓
训练Top30辅助模型
  ↓
训练市场机会密度模型
  ↓
融合个股综合分
  ↓
结合市场风险模型
  ↓
信号层输出 Top3 / Top2 / Top1 / 不出手
```
