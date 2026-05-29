# A股5日预测标签设计方案

## 目标

最终目标不是单纯预测涨跌，也不是单纯预测 10% 涨幅，而是：

> 每天从股票池中选出 Top3，尽量让这 3 只股票落入未来 5 日真实收益排名 Top30。

这个任务本质上是：

```text
每日截面排序 + 高弹性识别 + 市场机会过滤 + 出手数量控制
```

所以模型核心不应该只学习“涨不涨”，而应该学习：

```text
这只股票未来 5 日是否会在当天股票池里相对靠前。
```

## 一、核心结论

### 1. 主模型学习相对排名

方向模型可以保留，但不作为核心主模型。最终目标是 Top3 进入真实 Top30，因此主模型应优先学习未来 5 日截面强弱。

推荐主标签：

```text
future_5_return_rank_pct
```

含义：

```text
同一交易日内，按 future_5_return 从弱到强做百分位排名
越接近 1，未来 5 日相对越强
越接近 0，未来 5 日相对越弱
```

示例：

```text
当日第 1 名      -> 1.00
当日第 30 名     -> 接近高分位
当日中位数       -> 0.50
当日最差         -> 0.00
```

### 2. Top30 标签只做业务评估和辅助

固定 Top30 很贴近业务目标，但不适合作为唯一主标签。

原因：

```text
第 30 名：future_5_return = 8.10%，label = 1
第 31 名：future_5_return = 8.00%，label = 0
```

实际收益差距很小，但训练标签差异很大，容易制造边界噪声。

因此：

```text
label_top30 = future_5_return_rank <= 30
```

保留为：

```text
业务评估指标
辅助模型标签
信号层校准参考
```

不作为第一优先主模型。

### 3. 方向模型降级为辅助模型

方向标签：

```text
label_direction = future_5_return > 0
```

它的作用是：

```text
过滤弱票
提高胜率底线
辅助降低明显下跌风险
```

但它不能主导排序。原因是：

```text
股票A：未来5日 +1%
股票B：未来5日 +12%
```

在方向标签里二者都是正样本，但对 Top3 目标来说价值完全不同。

### 4. 标签必须使用可交易口径

`future_5_return` 不能只写成“未来第5日收盘价 / 当日收盘价 - 1”。这个口径容易高估实盘效果，因为信号通常是在 T 日收盘后才能生成，T 日收盘价未必能成交。

第一版统一采用下面的交易协议：

```text
signal_time：T 日收盘后
feature_cutoff_time：T 日收盘及以前
entry_price_type：V1 主回测使用 T+1 open；VWAP 只做对照回测
exit_price_type：V1 主回测使用 T+6 open；VWAP 只做对照回测
label_window：T+1 买入，持有 T+1、T+2、T+3、T+4、T+5，T+6 卖出
future_5_return：扣除滑点、佣金、印花税等成本后的净收益
```

原因：

```text
VWAP 是整日成交后的统计价格，离线回测可作为算法成交近似，但实盘盘前无法提前知道。
```

因此 V1 同时保留两套回测：

```text
主口径：T+1 open -> T+6 open，偏保守，作为验收口径
对照口径：T+1 VWAP -> T+6 VWAP，作为执行能力参考
```

如果两套口径都有效，模型可信度更高；如果只有 VWAP 口径有效，则不能直接认为策略可实盘。

### 5. T+1 执行字段不能提前用于 T 日信号

V1 交易协议是 T 日收盘后生成信号，T+1 开盘执行。因此 T+1 开盘后才知道的字段不能进入 T 日模型、排序或信号层。

字段分两类：

```text
signal_known_features：
  T 日收盘后已知，可进入模型和信号排序。

execution_known_filters：
  T+1 开盘或执行时才知道，只能用于成交模拟、执行过滤和评估归因。
```

典型禁止提前使用的字段：

```text
tradable_at_entry
limit_up_at_entry
entry_price
T+1 open 是否缺失
T+1 是否停牌
```

如果后续改成 T+1 开盘后再确认信号，必须定义为另一套交易协议，不能混在 V1 里。

### 6. 评估优先级调整

Top30 命中是业务目标，但不能单独作为最终验收。更合理的优先级是：

```text
第一目标：Top3 扣费后平均收益
第二目标：Top3 命中真实 Top30 的平均数量
第三目标：最大回撤和月度稳定性
第四目标：出手频率不过度稀疏
```

也就是说，模型不能靠“少数几天出手”或“命中 Top30 但收益很薄”通过验收。

## 二、标签体系

### 0. 交易协议字段

每一行训练样本必须保留下面字段，确保标签和实盘动作一致：

```text
signal_time
feature_cutoff_time
entry_trade_date
entry_price_type
entry_price
exit_trade_date
exit_price_type
exit_price
holding_trade_days
gross_future_5_return
future_5_return
buy_cost_rate
sell_cost_rate
buy_slippage_rate
sell_slippage_rate
```

默认定义：

```text
signal_time = T close 后
feature_cutoff_time = T close
entry_trade_date = T+1
exit_trade_date = T+6
holding_trade_days = 5
gross_future_5_return = exit_price / entry_price - 1
future_5_return = gross_future_5_return - buy_cost_rate - sell_cost_rate - buy_slippage_rate - sell_slippage_rate
```

成本参数不写死在标签里，统一从配置读取；标签表中保存本次运行实际使用的成本口径。

成本拆分规则：

```text
buy_cost_rate：买入佣金和其他买入侧费用
sell_cost_rate：卖出佣金、印花税和其他卖出侧费用
buy_slippage_rate：买入滑点
sell_slippage_rate：卖出滑点
```

如果暂不考虑最低佣金，也必须在配置中显式记录为关闭，避免复盘时误解收益来源。

### 1. 排名分位标签

主标签：

```text
future_5_return_rank_pct
```

生成方式：

```text
同一 trade_date 内：
future_5_return 越高，rank_pct 越接近 1
future_5_return 越低，rank_pct 越接近 0
```

工程固定公式：

```text
future_5_return_rank 使用同一 trade_date 内按 future_5_return 降序排名，第1名为1。
daily_stock_count 为当日有效样本数。
future_5_return_rank_pct = 1 - (future_5_return_rank - 1) / (daily_stock_count - 1)
```

因此：

```text
当日最高收益 = 1.0
当日最低收益 = 0.0
```

ties 处理第一版固定为：

```text
rank(method="first", ascending=False)
```

如果后续改为 `average` 或其他方式，必须作为新版本实验记录。

用途：

```text
训练个股强势排序模型
每天对股票池进行截面排序
```

可训练目标：

```text
回归 future_5_return_rank_pct
排序学习 learning-to-rank
```

### 2. 相对强势等级标签

为了降低连续回归的噪声，可以额外生成离散等级：

```text
strong_rank_level = 0：未来5日收益处于后50%
strong_rank_level = 1：未来5日收益处于50%-80%
strong_rank_level = 2：未来5日收益处于80%-95%
strong_rank_level = 3：未来5日收益处于Top5%
```

用途：

```text
训练多分类强势等级模型
辅助排序模型识别强票层次
```

### 3. 绝对强势标签

绝对弹性标签：

```text
absolute_strong_label = future_5_return >= 10%
```

也可以做成收益分级：

```text
absolute_strong_level = 0：future_5_return <= 0
absolute_strong_level = 1：0% < future_5_return < 5%
absolute_strong_level = 2：5% <= future_5_return < 10%
absolute_strong_level = 3：future_5_return >= 10%
```

注意：

```text
10% 标签正样本较少，不适合作为唯一主模型。
```

它适合作为：

```text
高弹性辅助模型
信号层加分项
机会密度统计基础
```

### 4. Top30 业务标签

业务标签：

```text
label_top10 = future_5_return_rank <= 10
label_top30 = future_5_return_rank <= 30
label_top50 = future_5_return_rank <= 50
```

用途：

```text
评估最终 Top3 是否命中真实 Top30
观察模型是否能抓到更强的 Top10
观察模型是否只是在 Top30 边缘命中
训练 Top30 辅助模型
验证排序模型是否贴近最终目标
```

如果股票池规模未来变化较大，需要同时记录：

```text
daily_stock_count
future_5_return_rank_pct
```

避免固定 Top30 在不同股票池规模下含义漂移。

同时保留分位标签：

```text
label_top1pct = future_5_return_rank_pct >= 0.99
label_top2pct = future_5_return_rank_pct >= 0.98
label_top5pct = future_5_return_rank_pct >= 0.95
relative_strong_label = future_5_return_rank_pct >= 0.95
```

用途：

```text
跨股票池规模比较
识别真正相对强势样本
辅助判断 Top30 命中质量
```

### 5. 方向标签

方向标签：

```text
label_direction = future_5_return > 0
```

用途：

```text
辅助过滤弱票
提升胜率底线
作为综合分中的低权重因子
```

### 6. 市场机会密度标签

市场机会密度用于判断当天是否适合积极出手。

连续标签：

```text
market_opportunity_density =
当天股票池中 future_5_return >= 10% 的样本占比
```

分类标签：

```text
market_opportunity_label =
market_opportunity_density 是否高于历史中位数或滚动分位阈值
```

注意：

```text
market_opportunity_density 是标签，可以用未来5日收益计算。
预测时的输入特征只能使用当天及以前的数据。
```

用途：

```text
判断市场是否容易出现 5 日涨幅超过 10% 的股票
决定 Top3 / Top2 / Top1 / 不出手
```

### 7. 收益风险调整标签

未来 5 日收益高，但中间回撤很大，实盘未必拿得住。因此增加风险调整字段：

```text
future_5_best_return
future_5_max_drawdown
future_5_return_to_drawdown
```

建议定义：

```text
future_5_best_return：持有期内最高可得收益
future_5_max_drawdown：从 entry_price 到持有期最低价的最大回撤
future_5_return_to_drawdown：future_5_return / abs(future_5_max_drawdown)
```

这些字段第一版不作为主标签，但必须进入评估，用于识别“收益高但路径很差”的样本。

### 8. 可交易标签

为防止回测收益不可执行，必须生成：

```text
tradable_at_entry
tradable_at_exit
limit_up_at_entry
limit_down_during_holding
suspended_during_holding
new_stock_flag
low_liquidity_flag
one_word_limit_up_recent
```

用途：

```text
训练样本过滤
回测成交模拟
最终信号过滤
失败样本归因
```

默认规则：

```text
买入日一字涨停或开盘涨停且无法成交：不能买入
卖出日跌停且无法成交：不能按理想价格卖出
停牌：不能买入或卖出
ST / *ST：剔除
上市不足 N 日：剔除，N 从配置读取
成交额低于阈值：剔除或降级
```

V1 成交失败处理：

```text
买入日无法成交：该信号未成交，默认不顺延到该股票下一个可交易日
是否递补下一候选由 replace_unfilled_entry 控制，默认不递补
卖出日无法成交：顺延到下一可卖出交易日
forced_exit_delay_days：记录卖出顺延天数
actual_exit_trade_date：记录实际卖出日期
actual_future_5_return：记录顺延后的实际收益
```

这样可以避免热门票因为“涨停买不进”、弱票因为“跌停卖不出”而虚增回测收益。

### 9. 价格与复权口径

A 股日 K 必须明确价格口径，否则除权除息、涨跌停和收益计算容易混乱。

V1 固定规则：

```text
技术特征：优先使用前复权价格，保证历史走势连续。
收益标签：使用与 entry/exit 可成交价一致的价格口径，主回测为真实 open-to-open 或等价还原口径。
涨跌停判断：使用未复权真实交易价或数据源提供的涨跌停字段。
成交额/成交量：使用原始成交额和成交量，不做复权。
除权除息日：必须在 data_quality_report 中检查异常收益和价格跳变。
```

如果数据源只能提供一种复权口径，必须在运行元数据中记录，并输出疑似复权异常日期。

## 三、推荐模型结构

### 第一阶段：先跑通两个核心模型

不建议一开始同时训练四个模型。先跑通最核心的两个模型，方便定位问题。

#### 模型A：个股强势排序模型

目标：

```text
future_5_return_rank_pct
```

或：

```text
strong_rank_level
```

输出：

```text
rank_strength_score
```

作用：

```text
每天对股票池进行排序，选出最可能进入未来 5 日收益前列的股票。
```

优先评估：

```text
Top3 命中真实 Top30 数量
Top3 未来 5 日平均收益
Top3 是否显著优于随机 Top3
Top3 是否显著优于近5日收益率Top3
```

#### 模型B：市场机会密度模型

目标：

```text
market_opportunity_density
```

或：

```text
market_opportunity_label
```

输出：

```text
market_opportunity_score
```

作用：

```text
判断当前市场是否适合积极出手，决定 Top3 / Top2 / Top1 / 不出手。
```

### 第二阶段：逐步加入辅助模型

在第一阶段跑通后，再逐个加入：

```text
方向模型：过滤弱票，提高胜率底线
强势10%模型：识别高弹性票
Top30辅助模型：贴近最终业务目标
行业强度因子：加入行业共振
风险模型/规则层：过滤高风险交易日和不可交易股票
```

每加入一个模块，都必须做消融实验。

## 四、最终综合分

初版综合分建议：

```text
stock_score =
  0.70 * rank_strength_score
+ 0.20 * industry_strength_score
```

含义：

```text
rank_strength_score：未来5日收益相对排名能力
industry_strength_score：行业热度、行业排名、行业扩散
```

V1 暂不把 `risk_penalty` 作为连续扣分揉进综合分。第一版风险处理分成两类：

```text
硬过滤：ST、新股、停牌、低流动性、买入不可成交
报表归因/轻量降级：近涨停、高位高换手、过热、弱行业
```

等主排序模型确认有 alpha 后，再在第二阶段评估是否加入连续 `risk_penalty`。

V1 行业强度固定公式：

```text
industry_strength_score = mean(
  industry_ret_5_xrank,
  industry_up_ratio_xrank,
  industry_amount_ratio_5_xrank
)
```

要求：

```text
三个分量均为当日行业横截面分位，越大越强。
行业样本数过少的行业单独标记。
缺失行业不参与行业加分，默认行业分为中性。
行业因子必须单独做消融。
```

注意：

```text
market_opportunity_score 不参与同一天个股排序，只决定 Top3 / Top2 / Top1 / 不出手。
strong_10pct_prob、direction_up_prob、top30_prob 第二阶段再加入。
```

多模型融合规则：

```text
所有模型输出先做分位归一化或概率校准
权重搜索只能使用滚动验证集
最终测试集只评估一次，不能反复调参
辅助模型优先作为过滤器或二级排序，不急着直接加权
```

## 五、信号层决策

信号层不再只看个股分数，还要看市场机会密度和市场风险。

### 机会密度高

```text
允许 Top3
```

条件示例：

```text
market_opportunity_score 高
market_risk_level 低或中性
Top3 个股分数都达标
```

### 机会密度中等

```text
Top1 或 Top2
```

条件示例：

```text
rank_strength_score 较高
direction_up_prob 较高
strong_10pct_prob 一般
market_risk_level 中性
```

### 机会密度低

```text
不出手 或 只出 Top1
```

条件示例：

```text
market_opportunity_score 低
strong_10pct_prob 低
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

## 六、评估指标

主评估指标必须围绕最终目标，而不是普通 accuracy。

### 1. 主指标

```text
Top3 扣费后平均收益率
Top3 命中 Top30 的平均数量
```

示例：

```text
每天选3只，如果其中2只进入真实Top30，则当天命中数量为2。
```

### 2. 辅助指标

```text
Top3至少命中1只Top30的交易日比例
Top3未来5日平均收益率
Top3未来5日中位收益率
Top3未来5日收益为正的比例
Top3未来5日涨超10%的比例
Top3最大回撤
Top3命中Top10的平均数量
Top3最高排名股票的平均真实名次
按年份/月度统计Top3表现稳定性
出手天数比例
扣费后收益的 Bootstrap 置信区间
```

### 3. 必须对比的基准

至少比较：

```text
随机Top3
近5日收益率Top3
近20日收益率Top3
近5日成交额增幅Top3
近5日换手率Top3
行业强度Top3
大盘指数择时 + 动量Top3
简单 LightGBM 回归 future_5_return
```

如果模型打不过这些基准，说明模型没有增量价值。

### 4. 统计显著性

每次评估必须增加：

```text
按 trade_date 做 bootstrap 重采样
模型与基准的收益差异置信区间
模型在不同月份胜出基准的比例
极端贡献日期列表
```

如果整体收益只靠少数日期贡献，不能认为模型稳定有效。

## 七、消融实验顺序

推荐逐步加入模块：

```text
1. 只用 rank_strength_score
2. rank_strength_score + industry_strength_score
3. rank_strength_score + industry_strength_score + 固定风险过滤
4. 加入 market_opportunity_score，只控制出手数量
5. 加入 strong_10pct_prob，作为二级排序或过滤
6. 加入 direction_up_prob，作为弱票过滤
7. 加入 top30_prob 和最终出手降级规则
```

每一步都记录：

```text
Top3命中Top30数量
Top3平均收益
Top3扣费后收益
Top3涨超10%比例
Top3命中Top10数量
出手天数
低命中日期
误伤日期
相对基准收益差异
```

## 八、关键风险点

### 1. 多模型融合后难以定位问题

如果多个模型一起上线，收益没提升，很难判断问题来自哪里。

解决方法：

```text
逐个模块加入，每加入一个模块都做消融测试。
```

### 2. 方向模型可能偏向稳涨小票

方向模型容易选择：

```text
未来5日涨一点点，但没有弹性的股票
```

这可能提高胜率，但拉低平均收益，也不利于进入真实收益 Top30。

解决方法：

```text
方向模型只做辅助，不做核心权重。
```

### 3. 固定 Top30 受股票池大小影响

如果每天股票池数量不同，Top30 的含义也不同。

解决方法：

```text
业务评估保留固定 Top30
训练主标签优先使用排名分位
```

### 4. 行业强度可能重复计数

行业强度合理，但它往往由收益、成交额、换手等同源行情数据聚合而来，可能和个股动量重复。

解决方法：

```text
行业因子必须单独消融
观察是否只在强势行情有效
限制 Top3 单行业集中度
输出 Top3 行业分布
```

### 5. 市场机会密度不能作为特征泄漏

`market_opportunity_density` 是标签，不是预测日可用特征。

预测时只能使用：

```text
当天及以前的行情、行业、宽度、资金、波动特征
```

### 6. 时间切分不能随机

股票预测必须使用时间序列验证，不能随机切分。

推荐：

```text
训练集：过去 N 个月
验证集：之后 1 个月
窗口向前滚动
最终独立测试集只评估一次
```

冻结测试集规则：

```text
最终测试集在特征、标签、权重、过滤规则、交易成本全部确定后只评估一次。
如果根据测试集结果调整方案，必须重新划分新的测试集，或进入下一版本实验。
```

V1 验证范围：

```text
冒烟验证：至少 3 个月，用于快速发现实现错误。
正式 walk-forward：至少 12 个月。
独立测试集：最近 3-6 个月，冻结不反复调参。
```

## 九、最终推荐主线

```text
主模型：未来5日收益排名分位 / 强势等级
辅助模型：未来5日涨超10%
辅助模型：未来5日上涨方向
市场模型：机会密度
信号层：决定 Top3 / Top2 / Top1 / 不出手
```

最终流程：

```text
清洗数据
  ↓
定义 signal_time / feature_cutoff_time / entry / exit / 成本
  ↓
生成可交易口径 future_5_return
  ↓
生成 future_5_return_rank_pct
  ↓
生成 label_top10 / label_top30 / label_top50 / top_quantile_label
  ↓
生成 strong_rank_level
  ↓
生成 absolute_strong_label / absolute_strong_level
  ↓
生成 label_direction
  ↓
生成可交易标签和收益风险调整标签
  ↓
生成 market_opportunity_density / market_opportunity_label
  ↓
训练个股强势排序模型
  ↓
用扣费回测验证是否打败基准
  ↓
训练市场机会密度模型
  ↓
逐步加入强势10%、方向、Top30、行业、风险模块
  ↓
验证集权重搜索和消融实验
  ↓
信号层输出 Top3 / Top2 / Top1 / 不出手
```
