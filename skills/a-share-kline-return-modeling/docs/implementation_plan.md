# A股5日预测技术实现方案

## 目标

基于新的标签设计，重建一条可验证、可迭代的建模流水线：

```text
原始日K数据
  ↓
生成特征与标签
  ↓
训练个股强势排序模型，先召回 Top50 候选池
  ↓
训练市场机会密度模型
  ↓
在候选池内用批准规则二次排序
  ↓
用市场机会密度决定 Top3 / Top2 / Top1 / 不出手
```

最终验收指标：

```text
Top3 扣费后未来5日平均收益
Top3 命中真实未来 Top30 的平均数量
Top3 命中真实未来 Top10 的平均数量
Top3 未来5日涨超10%比例
最大回撤和月度稳定性
出手天数和低命中日期
```

## 一、目录结构

当前建模 skill 重新收敛为以下结构：

```text
skills/a-share-kline-return-modeling/
  data/
    00_股票清单.csv
    clean_stock_features.csv
    clean_market_features.csv
    industry_features.csv
  docs/
    label_design.md
    implementation_plan.md
  configs/
    backtest.yaml
  tests/
    test_label_rank_direction.py
    test_no_future_feature_leakage.py
    test_market_density_lag.py
    test_future_5_trade_date_filter.py
    test_backtest_cost_calculation.py
    test_signal_file_has_no_truth_columns.py
  samples/
    small_stock_daily_k.csv
    small_stock_list.csv
  outputs/
    stock_rank_predictions/
    market_opportunity_predictions/
    final_signals/
    evaluation/
  scripts/
    00_build_features.py
    01_train_stock_rank_model.py
    02_train_market_opportunity_model.py
    03_generate_final_signals.py
    04_evaluate_top3.py
```

说明：

```text
data/00_股票清单.csv 是固定股票池。
clean_*.csv 是建模输入表。
outputs/ 是运行产物，不作为核心源码长期依赖。
```

长期建议：

```text
skill 内只保留 docs / scripts / configs / tests / samples。
完整 data 和 outputs 如果体积较大，后续迁移到仓库根目录 data/ 与 outputs/，或纳入 .gitignore / Git LFS。
```

## 二、数据输入

### 1. 个股日K

来源：

```text
skills/a-share-data-fetching/data/单只股票日k/
```

需要字段：

```text
trade_date
symbol
name
open
close
high
low
volume
amount
pct_chg
turnover_pct
```

### 2. 股票清单

来源：

```text
skills/a-share-kline-return-modeling/data/00_股票清单.csv
```

用途：

```text
固定建模股票池
过滤无关股票
保证回测口径一致
```

### 3. 行业数据

第一版先使用股票清单中的行业字段或从个股文件名/清单补齐。

后续可接入：

```text
申万行业日K
东方财富行业板块日K
行业资金流
```

### 4. 指数/市场数据

第一版可从已有核心指数日K或个股池内部聚合生成：

```text
market_up_ratio
market_avg_pct_chg
market_strong_5pct_ratio
market_limit_like_ratio
market_amount_ratio_5
```

如果指数数据暂时缺失，先用股票池内部宽度替代。

## 三、回测协议与可交易收益口径

第一版统一使用收盘后选股协议：

```text
signal_time：T 日收盘后
feature_cutoff_time：T 日收盘及以前
entry_price_type：V1 主回测使用 T+1 open
exit_price_type：V1 主回测使用 T+6 open
holding_trade_days：5
label_window：T+1 买入，持有 5 个交易日，T+6 卖出
future_5_return：扣除交易成本和滑点后的净收益
```

禁止第一版使用：

```text
T close -> T+5 close
```

作为主回测口径。这个口径可以保留为研究对照，但不能作为最终验收收益。

同时保留一套对照口径：

```text
主口径：open-to-open，T+1 open -> T+6 open
对照口径：VWAP-to-VWAP，T+1 VWAP -> T+6 VWAP
```

说明：

```text
VWAP 是整日成交后的统计价格，离线回测可以作为算法成交近似，但不能作为唯一验收口径。
如果模型只在 VWAP 口径有效，在 open-to-open 口径失效，则暂不能进入准实盘。
```

新增配置文件：

```text
skills/a-share-kline-return-modeling/configs/backtest.yaml
```

建议配置项：

```yaml
signal_time: after_close
feature_cutoff_time: close
primary_entry_price_type: open
primary_exit_price_type: open
benchmark_entry_price_type: vwap
benchmark_exit_price_type: vwap
holding_trade_days: 5
commission_rate: configurable
stamp_tax_rate: configurable  # sell side only
transfer_fee_rate: configurable
min_commission: configurable
buy_slippage_rate: configurable
sell_slippage_rate: configurable
min_listing_days: configurable
min_amount: configurable
min_avg_amount_5: configurable
max_position_per_stock: configurable
max_picks_per_industry: configurable
replace_unfilled_entry: false
allow_exit_delay: true
```

成本、滑点、成交额阈值不在代码里写死，必须从配置读取，并写入评估输出，确保每次回测口径可复现。

成本计算拆分：

```text
buy_cost_rate：买入佣金和买入侧费用
sell_cost_rate：卖出佣金、印花税和卖出侧费用
buy_slippage_rate：买入滑点
sell_slippage_rate：卖出滑点
future_5_return = gross_future_5_return - buy_cost_rate - sell_cost_rate - buy_slippage_rate - sell_slippage_rate
```

如果 `min_commission` 暂不启用，也必须在配置里显式关闭。

### 价格与复权口径

V1 固定口径：

```text
技术特征：优先使用前复权价格，保证历史走势连续。
收益标签：使用与 entry/exit 可成交价一致的价格口径，主口径为真实 open-to-open 或等价还原口径。
涨跌停判断：使用未复权真实交易价或数据源提供的涨跌停字段。
成交额/成交量：使用原始成交额和成交量。
除权除息日：输出异常检查，不允许静默吞掉价格跳变。
```

`00_build_features.py` 必须在运行摘要里记录：

```text
price_adjustment_type
limit_price_source
amount_volume_adjustment_type
suspected_adjustment_error_dates
```

## 四、特征表设计

### 1. `stock_features.csv`

粒度：

```text
每行 = 一个股票 + 一个交易日
```

主键：

```text
trade_date
symbol
```

基础字段：

```text
name
industry
signal_time
feature_cutoff_time
close
pct_chg
turnover_pct
amount
is_st
is_training_eligible
listing_days
```

个股技术特征：

```text
ret_1
ret_3
ret_5
ret_10
ret_20
volatility_5
volatility_10
amount_ratio_5
amount_ratio_20
turnover_ratio_5
range_pos_20
dist_high_20
dist_low_20
close_ma_ratio_5
close_ma_ratio_20
```

横截面排名特征：

```text
ret_5_xrank
ret_20_xrank
amount_ratio_5_xrank
turnover_pct_xrank
volatility_5_xrank
range_pos_20_xrank
```

行业相对特征：

```text
industry_avg_ret_5
industry_avg_ret_20
industry_up_ratio
industry_strong_5pct_ratio
industry_amount_ratio_5
stock_vs_industry_ret_5
stock_industry_ret_5_rank
stock_industry_amount_rank
```

行业强度来源约束：

```text
industry_strength_score 只能由 feature_cutoff_time 之前的行业行情、成交额、宽度、涨停家数、相对强度等生成。
不能使用未来5日行业收益。
不能使用由未来个股表现聚合得到的行业标签。
行业因子必须单独做消融，防止和个股动量重复计数。
```

V1 固定行业分数：

```text
industry_strength_score = mean(
  industry_ret_5_xrank,
  industry_up_ratio_xrank,
  industry_amount_ratio_5_xrank
)
```

要求：

```text
三个分量均使用 T 日及以前数据。
三个分量均为当日行业横截面分位，越大越强。
行业样本数过少时标记 industry_sample_too_small。
缺失行业默认中性分，不参与额外加分。
```

市场环境特征：

```text
market_up_ratio
market_avg_pct_chg
market_strong_5pct_ratio
market_10pct_density_ma5_lag1
market_10pct_density_ma10_lag1
market_amount_ratio_5
```

风险特征：

```text
near_limit_up
high_turnover_high_position
overheat_flag
weak_industry_flag
liquidity_risk_flag
tradable_at_entry
tradable_at_exit
limit_up_at_entry
limit_down_during_holding
suspended_during_holding
new_stock_flag
low_liquidity_flag
one_word_limit_up_recent
```

字段可用时间分层：

```text
signal_known_features：
  T 日收盘后已经知道，可进入模型和 T 日信号排序。

execution_known_filters：
  T+1 开盘或执行时才知道，只能用于执行过滤、成交模拟和评估归因。
```

禁止把下面字段作为 T 日模型特征或 T 日排序字段：

```text
tradable_at_entry
limit_up_at_entry
entry_price
entry_open_missing
entry_suspended
```

标签字段：

```text
entry_trade_date
entry_price_type
entry_price
exit_trade_date
exit_price_type
exit_price
future_5_trade_date
future_5_close
gross_future_5_return
future_5_return
future_5_return_rank
future_5_return_rank_pct
label_top10
label_top30
label_top50
label_top1pct
label_top2pct
label_top5pct
relative_strong_label
label_direction
absolute_strong_label
absolute_strong_level
strong_rank_level
future_5_best_return
future_5_max_drawdown
future_5_return_to_drawdown
buy_cost_rate
sell_cost_rate
buy_slippage_rate
sell_slippage_rate
forced_exit_delay_days
actual_exit_trade_date
actual_future_5_return
```

### 2. `market_features.csv`

粒度：

```text
每行 = 一个交易日
```

特征字段：

```text
trade_date
market_up_ratio
market_avg_pct_chg
market_median_pct_chg
market_strong_5pct_ratio
market_10pct_density_ma5_lag1
market_10pct_density_ma10_lag1
market_amount_ratio_5
market_volatility_5
```

标签字段：

```text
future_market_10pct_density
market_opportunity_label
market_top5pct_avg_return
market_top30_avg_return
market_positive_ratio
market_extreme_return_density_5pct
market_extreme_return_density_10pct
```

其中：

```text
future_market_10pct_density =
当天股票池中 future_5_return >= 10% 的样本占比
```

诊断字段用途：

```text
market_top5pct_avg_return：未来5日当日Top5%股票平均收益
market_top30_avg_return：未来5日真实Top30股票平均收益
market_positive_ratio：未来5日正收益股票占比
market_extreme_return_density_5pct：未来5日涨幅>=5%占比
market_extreme_return_density_10pct：未来5日涨幅>=10%占比
```

这些字段第一版主要用于诊断市场机会模型到底是在识别“10%大机会”，还是只是在识别“市场整体上涨”。

## 五、标签生成规则

### 1. 未来5日收益

按每只股票的交易日序列和回测协议生成：

```text
entry_trade_date = T 后第 1 个市场交易日，不因个股停牌或涨停顺延
exit_trade_date = entry_trade_date 后第 5 个持有交易日之后的退出日
gross_future_5_return = exit_price / entry_price - 1
future_5_return = gross_future_5_return - buy_cost_rate - sell_cost_rate - buy_slippage_rate - sell_slippage_rate
```

要求：

```text
future_5_trade_date 必须存在
entry_price 和 exit_price 必须符合配置口径
无法买入或无法卖出的样本必须记录 tradable 字段
训练时 future_5_trade_date 必须早于预测锚点日
```

如果因为涨停、跌停、停牌导致不可成交：

```text
tradable_at_entry = False：样本不能作为可买入信号
tradable_at_exit = False：评估中必须按无法理想卖出处理，不能直接使用理论收益
```

V1 成交失败处理：

```text
买入日无法成交：跳过该股票
replace_unfilled_entry = false 时，不递补下一候选
replace_unfilled_entry = true 时，可从候选池顺延递补，但必须在回测输出中标记
卖出日无法成交：顺延到下一可卖出交易日
forced_exit_delay_days：记录卖出顺延天数
actual_exit_trade_date：记录实际卖出日期
actual_future_5_return：记录顺延后的实际扣费收益
```

注意：

```text
买入不顺延，卖出可顺延。
不要把 entry_trade_date 理解为“该股票下一个能交易的日期”。
```

### 2. 排名分位标签

按交易日分组：

```text
future_5_return_rank = future_5_return 当日降序排名，1 表示收益最高，数值越小越好
daily_stock_count = 当日有效样本数
future_5_return_rank_pct = 1 - (future_5_return_rank - 1) / (daily_stock_count - 1)
```

定义：

```text
收益最高 -> 1.0
收益最低 -> 0.0
rank ties 第一版固定 method="first"
```

推荐实现：

```python
df["future_5_return_rank"] = (
    df.groupby("trade_date")["future_5_return"]
      .rank(method="first", ascending=False)
)

daily_stock_count = df.groupby("trade_date")["future_5_return"].transform("count")
df["future_5_return_rank_pct"] = (
    1 - (df["future_5_return_rank"] - 1) / (daily_stock_count - 1)
)
```

当 `daily_stock_count <= 1` 时，该日不参与训练和评估。

禁止写反：

```python
df.groupby("trade_date")["future_5_return"].rank(pct=True, ascending=False)
```

该写法会让收益最高的股票分位接近 0，方向错误。

### 3. TopK 和分位标签

```text
label_top10 = future_5_return_rank <= 10
label_top30 = future_5_return_rank <= 30
label_top50 = future_5_return_rank <= 50
label_top1pct = future_5_return_rank_pct >= 0.99
label_top2pct = future_5_return_rank_pct >= 0.98
label_top5pct = future_5_return_rank_pct >= 0.95
relative_strong_label = future_5_return_rank_pct >= 0.95
```

用途：

```text
业务评估
辅助模型
最终信号判卷
区分 Top10 高质量命中和 Top30 边缘命中
跨股票池规模稳定评估
```

### 4. 相对强势等级

```text
strong_rank_level = 0：rank_pct < 0.50
strong_rank_level = 1：0.50 <= rank_pct < 0.80
strong_rank_level = 2：0.80 <= rank_pct < 0.95
strong_rank_level = 3：rank_pct >= 0.95
```

### 5. 绝对强势标签

```text
absolute_strong_label = future_5_return >= 0.10
```

```text
absolute_strong_level = 0：future_5_return <= 0
absolute_strong_level = 1：0 < future_5_return < 0.05
absolute_strong_level = 2：0.05 <= future_5_return < 0.10
absolute_strong_level = 3：future_5_return >= 0.10
```

### 6. 方向标签

```text
label_direction = future_5_return > 0
```

### 7. 收益路径和可交易标签

收益路径字段：

```text
future_5_best_return
future_5_max_drawdown
future_5_return_to_drawdown
```

可交易字段：

```text
tradable_at_entry
tradable_at_exit
limit_up_at_entry
limit_down_during_holding
suspended_during_holding
```

用途：

```text
不作为主训练目标
进入回测过滤、风险归因和最终验收
```

### 8. 市场机会密度滞后特征

市场机会密度标签本身使用未来 5 日收益计算，但预测日的市场机会特征必须只来自历史。

正确特征命名：

```text
market_10pct_density_ma5_lag1
market_10pct_density_ma10_lag1
```

含义：

```text
使用 t-1 及以前的历史机会密度，计算过去5日/10日均值，用来预测 t 日机会密度。
```

推荐实现：

```python
market["market_10pct_density_ma5_lag1"] = (
    market["future_market_10pct_density"].shift(1).rolling(5).mean()
)

market["market_10pct_density_ma10_lag1"] = (
    market["future_market_10pct_density"].shift(1).rolling(10).mean()
)
```

禁止实现：

```python
market["future_market_10pct_density"].rolling(5).mean()
```

该写法会把当天标签混入当天特征，造成未来泄漏。

## 六、脚本设计

### 1. `00_build_features.py`

职责：

```text
读取原始个股日K
过滤股票清单
生成个股特征
生成行业聚合特征
生成市场宽度特征
生成可交易口径未来5日标签
生成 TopK、分位、收益路径和可交易字段
输出 clean_stock_features.csv 和 clean_market_features.csv
```

关键参数：

```bash
python3 skills/a-share-kline-return-modeling/scripts/00_build_features.py \
  --stock-list skills/a-share-kline-return-modeling/data/00_股票清单.csv \
  --source-dir skills/a-share-data-fetching/data/单只股票日k \
  --output-dir skills/a-share-kline-return-modeling/data \
  --backtest-config skills/a-share-kline-return-modeling/configs/backtest.yaml
```

必须校验：

```text
不能把 future_* 字段加入特征列
不能把 entry_price / exit_price / tradable_at_exit 等未来交易结果加入预测特征列
每个 trade_date 覆盖股票数
标签缺失率
ST 和停牌样本处理
上市天数过滤
涨停不可买和跌停不可卖样本数量
低流动性样本数量
是否存在重复 trade_date + symbol
future_5_trade_date 是否正确向后5个交易日
future_5_return_rank_pct 是否收益最高接近1
Top30 正样本数量是否每天约为30
Top10 / Top50 / Top5pct 标签分布
是否存在 inf / -inf
```

必须输出：

```text
outputs/evaluation/data_quality_report.md
```

报告至少包含：

```text
股票数
交易日数
每日样本数分布
标签缺失率
不可交易样本比例
涨停无法买入比例
跌停无法卖出比例
停牌比例
future_5_return 极值
rank_pct 最大/最小检查
Top10/Top30/Top50 每日数量检查
疑似复权异常日期
成本扣除前后收益差异
不同年份标签分布漂移
```

### 2. `01_train_stock_rank_model.py`

职责：

```text
训练个股强势排序模型
按锚点日滚动训练
输出每日 TopN 候选池排名
```

当前默认主模型：

```text
LightGBMClassifier
目标：label_top50
输出：rank_strength_score = Top50 概率
```

可选对照模式：

```text
--model-mode raw_rank_pct_regression
  LightGBMRegressor / future_5_return_rank_pct

--model-mode top30_classifier
  LightGBMClassifier / label_top30

--model-mode weighted_rank_pct_regression
  LightGBMRegressor / 加权 future_5_return_rank_pct
```

后续可升级：

```text
LightGBMRanker
目标：strong_rank_level
group：trade_date
```

关键参数：

```bash
python3 skills/a-share-kline-return-modeling/scripts/01_train_stock_rank_model.py \
  --start-date 2025-05-01 \
  --end-date 2025-05-31 \
  --top-n 50 \
  --model-mode top50_classifier
```

训练窗口：

```text
默认过去365自然日
训练样本必须满足 future_5_trade_date < anchor_date
```

强制过滤规则：

```python
train_df = df[df["future_5_trade_date"] < anchor_date]
```

禁止只按 `trade_date < anchor_date` 过滤。示例：

```text
anchor_date = 2026-04-10
训练样本 trade_date = 2026-04-08
future_5_trade_date = 2026-04-15
```

这个样本在 2026-04-10 当天还不知道未来5日结果，不能进入训练。

输出两个文件：

```text
outputs/stock_rank_predictions/predictions.csv
outputs/stock_rank_predictions/predictions_with_truth.csv
```

根据 CR-20260529-001，`--top-n 50` 是 M3 第一阶段默认候选池口径。raw model score Top3 必须作为评估基线保留，但不再把 raw score 直接 Top3 作为唯一 M3 目标。

当前默认 `--model-mode top50_classifier` 是开发阶段实验后选定的主线实现，用于提高 Top50 候选池对真实 Top30 的召回。`raw_rank_pct_regression` 保留为可回退基线。

`predictions.csv` 只包含预测时可用字段：

```text
trade_date
symbol
name
industry
rank_strength_score
rank_strength_rank
industry_strength_score
model_mode
risk_flags
liquidity_risk_flag
```

不得包含：

```text
tradable_at_entry
limit_up_at_entry
entry_price
entry_suspended
```

这些字段属于 T+1 执行或评估字段，不能用于 T 日模型排序。

`predictions_with_truth.csv` 才包含评估字段：

```text
future_5_return
future_5_return_rank
future_5_return_rank_pct
label_top10
label_top30
label_top50
future_5_max_drawdown
tradable_at_exit
```

使用规则：

```text
03_generate_final_signals.py 只能读取 predictions.csv。
04_evaluate_top3.py 可以读取 predictions_with_truth.csv 或自行合并 truth。
```

### 2.1 Top50 候选池内二次排序

职责：

```text
读取模型 Top50 候选池
保留 raw model score Top3 基线
在候选池内评估已批准的规则二次排序
输出各策略按日、按月和整体汇总
```

第一版只允许 CR-20260529-001 批准的规则：

```text
ret_20
blend_model_low_overheat
blend_model_amount
```

强制约束：

```text
不得修改标签定义。
不得修改 T+1 open -> T+6 open 主交易口径。
不得修改成本、滑点、未来泄漏规则或 walk-forward 切分。
不得引入二阶段学习模型；如需引入，必须另提变更请求。
```

输出：

```text
outputs/evaluation/rerank_daily_summary.csv
outputs/evaluation/rerank_monthly_summary.csv
outputs/evaluation/rerank_overall_summary.csv
outputs/evaluation/rerank_strategy_summary.md
```

训练脚本必须校验：

```text
训练样本最大 future_5_trade_date < 当前 anchor_date
特征列泄漏扫描
特征列数量和清单
训练日期范围
训练样本数量
每日预测股票数量
预测分数分布
```

### 3. `02_train_market_opportunity_model.py`

职责：

```text
训练市场机会密度模型
预测当天是否适合积极出手
```

第一版模型：

```text
LightGBMRegressor
目标：future_market_10pct_density
```

也可增加分类模型：

```text
LightGBMClassifier
目标：market_opportunity_label
```

输出字段：

```text
trade_date
market_opportunity_score
predicted_10pct_density
market_opportunity_level
```

如果需要评估，另行输出：

```text
market_predictions_with_truth.csv
future_market_10pct_density
```

市场机会分级：

```text
高：predicted_10pct_density >= 历史70分位
中：历史40-70分位
低：低于历史40分位
```

### 4. `03_generate_final_signals.py`

职责：

```text
读取个股排序预测
读取市场机会预测
计算综合分
结合风险规则
输出 Top3 / Top2 / Top1 / 不出手
```

第一版综合分：

```text
stock_score =
  0.70 * rank_strength_score
+ 0.20 * industry_strength_score
```

V1 不把 `risk_penalty` 放进连续综合分。风险先做硬过滤、报表归因和轻量降级；连续扣分第二阶段再评估。

注意：

```text
market_opportunity_score 是同一天所有股票共享的市场状态，不参与同日个股排序。
它只用于决定当天出手数量：Top3 / Top2 / Top1 / 不出手。
```

第二阶段再加入：

```text
strong_10pct_prob
direction_up_prob
top30_prob
```

出手逻辑：

```text
市场机会高 + 风险低：允许 Top3
市场机会中：Top1 / Top2
市场机会低：不出手 / Top1
高风险：降级或不出手
```

输入校验：

```text
个股预测输入文件不得包含 future_ / label_ 字段
不得包含 strong_rank_level / absolute_strong_level 等标签字段
最终信号文件不得包含未来收益字段
最终信号不得使用 T+1 开盘后才知道的 entry 执行字段
执行过滤可以在 T+1 开盘后读取 tradable_at_entry / limit_up_at_entry
不得使用 tradable_at_exit
```

### 5. `04_evaluate_top3.py`

职责：

```text
评估最终信号
对比随机和简单基准
计算扣费后收益、回撤和可交易成交结果
输出月度和每日明细
```

主指标：

```text
Top3扣费后平均未来5日收益
Top3命中Top30平均数量
Top3命中Top10平均数量
Top3至少命中1只Top30交易日比例
Top3涨超10%比例
最大回撤
月度收益稳定性
出手天数比例
```

基准：

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

输出：

```text
outputs/evaluation/monthly_summary.csv
outputs/evaluation/daily_detail.csv
outputs/evaluation/baseline_compare.csv
outputs/evaluation/walk_forward_summary.csv
outputs/evaluation/bootstrap_confidence_interval.csv
```

评估脚本必须支持：

```text
按 trade_date bootstrap 重采样
模型 vs 基准收益差异置信区间
极端贡献日期统计
按行业集中度统计 Top3
不可交易样本归因
容量和流动性压力测试摘要
入选股票成交额分位
单票成交额占比
低流动性入选比例
```

## 七、特征列选择规则

严禁进入模型的字段：

```text
future_*
label_*
*_label
entry_trade_date
entry_price
exit_trade_date
exit_price
gross_future_5_return
buy_cost_rate
sell_cost_rate
buy_slippage_rate
sell_slippage_rate
tradable_at_exit
limit_down_during_holding
suspended_during_holding
forced_exit_delay_days
actual_exit_trade_date
actual_future_5_return
future_5_return_rank
future_5_return_rank_pct
strong_rank_level
absolute_strong_level
trade_date
symbol
name
industry
```

允许进入模型的字段：

```text
历史收益
历史波动
历史成交量/成交额
当日横截面排名
行业历史强度
市场宽度
预测时已知风险标记
low_liquidity_flag
节假日参考项
```

`tradable_at_entry`、`limit_up_at_entry`、`entry_price` 属于 T+1 执行字段，不能进入 T 日模型特征和信号排序。

模型脚本必须打印：

```text
特征列数量
特征列清单
是否存在 future_ 泄漏字段
训练日期范围
训练样本数量
预测股票数量
```

## 八、验证与验收

### 时间切分协议

禁止随机切分训练、验证、测试。

统一采用 walk-forward：

```text
训练：过去 N 个月
验证：之后 1 个月
窗口滚动
最终独立测试集只评估一次
```

权重搜索、阈值调整、行业集中度限制只能在验证窗口内完成。测试集不得反复调参。

冻结测试集规则：

```text
最终测试集在模型、特征、标签、权重、过滤规则、交易成本全部确定后只评估一次。
如果根据测试集结果调整方案，必须重新划定新的测试集，或进入下一版本实验。
```

### 信号级评估与组合级回测

评估拆成两层，不混用：

```text
信号级评估：每日 Top3 平均收益、命中 Top10/Top30、不可交易归因
组合级回测：考虑每天开仓、持有5日、资金占用、重叠持仓和现金
```

V1 组合级回测默认规则：

```text
每日最多新开 Top3
单日新仓预算 = 总资产的 1/5
每只入选股票等权
总持仓上限 100%
未出手或未成交资金保留现金
卖出资金在实际卖出后可复用
卖出日无法成交则顺延，并继续占用仓位
```

信号级评估用于判断模型 alpha，组合级回测用于判断策略资金曲线，两者都必须输出。

### V1 验证范围

```text
冒烟验证：至少 3 个月，用于发现标签、成本、成交模拟和泄漏问题。
正式 walk-forward：至少 12 个月。
独立测试集：最近 3-6 个月，冻结不反复调参。
```

### 第一阶段验收

只使用：

```text
rank_strength_score
industry_strength_score
ret_20
amount_ratio_5
range_pos_20
```

市场机会密度只用于控制出手数量，不进入同日个股排序。

验收要求：

```text
Top50候选池平均真实Top30命中显著高于随机Top50
最终Top3扣费后平均收益 > 随机Top3
最终Top3扣费后平均收益 >= 最强简单基准之一
最终Top3命中Top30平均数量 > raw model Top3
最终Top3命中Top10平均数量有改善
至少 2/3 验证月份优于随机基准
按月不能只靠单月贡献
Bootstrap 置信区间不能显示完全不显著
低机会密度月份减少无效出手
必须保留 raw model Top3 基线
```

### 第二阶段验收

加入：

```text
strong_10pct_prob
direction_up_prob
top30_prob
risk_penalty
```

验收要求：

```text
消融实验显示新增模块有正增量
不能只在单个月份有效
不能大幅减少出手天数换取表面命中率
不能靠提高行业集中度换取短期收益
```

## 九、执行顺序

建议按下面顺序实现：

```text
1. 新建 configs/backtest.yaml，固定交易口径和成本参数
2. 新建 scripts/00_build_features.py
3. 生成 clean_stock_features.csv 和 clean_market_features.csv
4. 校验可交易 future_5_return、TopK 标签和泄漏字段
5. 做标签 sanity check
6. 新建 scripts/04_evaluate_top3.py，先支持信号级评估
7. 加入组合级资金曲线回测
8. 用人工/简单规则生成一个预测文件，验证评估脚本正确性
9. 新建 scripts/01_train_stock_rank_model.py
10. 跑 2025-05、2026-03、2026-04 三个月验证
11. 做随机/动量/成交额/换手率/行业强度/简单回归基准对比
12. 跑至少 12 个月 walk-forward
13. 新建 scripts/02_train_market_opportunity_model.py
14. 新建 scripts/03_generate_final_signals.py
15. 做消融实验
16. 再决定是否加入方向模型、10%强势模型和Top30辅助模型
```

优先验证月份：

```text
2025-05：机会密度低，检验是否少犯错
2026-03：弱势月份，检验风险过滤
2026-04：机会密度高，检验是否敢出手
```

## 十、版本控制建议

建议提交粒度：

```text
commit 1：实现特征和标签生成
commit 2：实现Top3评估和基准
commit 3：实现个股排序模型
commit 4：实现市场机会密度模型
commit 5：实现最终信号层
```

大体积中间数据如果超过 100MB：

```text
走 Git LFS
或只提交脚本和小样本，不提交完整输出
```

## 十一、风险特征第一版固定规则

第一版先固定规则，避免为了单月结果反复调阈值。

```text
near_limit_up：
  pct_chg >= 9.5%

high_turnover_high_position：
  turnover_pct 位于该股近20日80分位以上
  且 range_pos_20 >= 0.8

overheat_flag：
  ret_5 > 15%
  且 range_pos_20 > 0.9

weak_industry_flag：
  industry_avg_ret_5 位于全行业后30%

liquidity_risk_flag：
  amount 低于股票池当日20分位
  或近5日平均成交额低于股票池当日20分位

tradability_filter：
  ST / *ST 剔除
  停牌剔除
  上市不足 min_listing_days 剔除
  T+1 开盘涨停且无法买入剔除
  过去 N 日频繁一字板剔除

industry_concentration_limit：
  Top3 中单一行业最多 max_picks_per_industry 只
  第一版只做约束和报表，不用它调高回测收益
```

阈值可以后续通过验证集调整，但第一版必须固定并记录。

V1 风险处理原则：

```text
ST / 新股 / 停牌 / 低流动性 / 买入不可成交：硬过滤
近涨停 / 高位高换手 / 过热 / 弱行业：报表归因或轻量降级
risk_penalty 连续扣分第二阶段再做，不进入 V1 主排序分
```

## 十二、walk-forward 汇总

新增统一汇总文件：

```text
outputs/evaluation/walk_forward_summary.csv
outputs/evaluation/rerank_walk_forward/rerank_strategy_summary.md
```

建议字段：

```text
period
train_start
train_end
test_start
test_end
trade_days
signal_days
avg_hit_top30_count
avg_hit_top10_count
hit_at_least_one_ratio
avg_net_future_5_return
median_net_future_5_return
strong_10pct_ratio
max_drawdown_like_metric
random_baseline_return
momentum_baseline_return
amount_growth_baseline_return
turnover_baseline_return
industry_baseline_return
bootstrap_return_ci_low
bootstrap_return_ci_high
max_single_day_contribution
signal_industry_concentration
```

用途：

```text
判断不同月份和不同市场环境下系统是否稳定，而不是只看单次结果。
同时对比 raw model Top3 基线与批准的 Top50 候选池二次排序规则。
```
