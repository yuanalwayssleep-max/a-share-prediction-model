# Top3可出手模型特征表设计

## 目标

每日从股票池中选出最多 3 只可出手股票，目标是这些股票在未来 5 个交易日后的收益率达到 `10%` 及以上。

核心训练标签：

```text
target_5d_ge10 = future_5_return >= 0.10
```

辅助标签只用于训练评估，不进入特征：

```text
future_5_return
future_5_max_return
future_5_min_return
future_5_trade_date
target_5d_up
target_5d_ge05
target_5d_ge10
target_5d_loss05
daily_future_return_rank
daily_future_return_top3_label
```

## 表设计原则

- 一行表示一个 `trade_date + symbol` 的候选股票快照。
- 所有特征必须只使用 `trade_date` 当天收盘前已经知道的数据。
- `future_*`、`target_*`、`daily_future_*` 只能作为标签和回测答案，禁止进入模型特征。
- 主模型不再学习普通上涨方向，而是学习未来 5 日收益率 `>=10%` 的概率。
- Top3 输出必须同时满足收益概率、流动性、风险过滤和市场/行业环境，不再把概率最高的三只直接视为可出手。

## 主表

文件建议：

```text
data/个股Top3_10pct特征数据.csv
```

主键：

```text
trade_date
symbol
```

### 1. 基础字段

| 字段 | 含义 |
|---|---|
| trade_date | 信号日期 |
| symbol | 6位股票代码 |
| name | 股票名称 |
| board | 板块 |
| industry | 行业 |
| is_st | 是否ST |
| is_training_eligible | 是否可用于训练 |
| close | 当日收盘价 |
| pct_chg | 当日涨跌幅 |
| turnover_pct | 当日换手率 |
| amount | 成交额 |
| volume | 成交量 |
| limit_pct | 涨跌停幅度 |
| near_limit_up | 是否接近涨停 |
| near_limit_down | 是否接近跌停 |

### 2. 收益与动量特征

这些特征判断股票是否已经进入可持续强势，而不是普通反弹。

| 字段 | 含义 |
|---|---|
| ret_1 | 1日收益 |
| ret_2 | 2日收益 |
| ret_3 | 3日收益 |
| ret_5 | 5日收益 |
| ret_10 | 10日收益 |
| ret_20 | 20日收益 |
| ret_5_minus_ret_20 | 短期相对中期动量变化 |
| ret_3_minus_ret_10 | 短期相对10日动量变化 |
| momentum_accel_3_10 | 动量加速度 |
| consecutive_up_days_5 | 近5日上涨天数 |
| consecutive_down_days_5 | 近5日下跌天数 |
| close_ma_ratio_5 | 收盘价相对5日均线 |
| close_ma_ratio_10 | 收盘价相对10日均线 |
| close_ma_ratio_20 | 收盘价相对20日均线 |
| ma5_gt_ma10 | 5日均线是否强于10日均线 |
| ma10_gt_ma20 | 10日均线是否强于20日均线 |

### 3. 位置与突破特征

10%收益票通常需要有突破、强趋势或强反转结构，必须显式刻画。

| 字段 | 含义 |
|---|---|
| range_pos_20 | 20日价格区间位置 |
| range_pos_60 | 60日价格区间位置 |
| dist_high_20 | 距20日高点比例 |
| dist_high_60 | 距60日高点比例 |
| dist_low_20 | 距20日低点比例 |
| breakout_20_high | 是否突破20日高点 |
| breakout_60_high | 是否突破60日高点 |
| pullback_from_20_high | 距20日高点回撤 |
| new_high_with_volume | 放量新高 |
| low_position_rebound | 低位反弹 |
| failed_breakout_risk | 冲高失败风险 |

### 4. 量能与资金特征

未来 5 日涨 10% 往往需要量能确认，不能只看价格。

| 字段 | 含义 |
|---|---|
| amount_ratio_3 | 近3日成交额相对均值 |
| amount_ratio_5 | 近5日成交额相对均值 |
| amount_ratio_10 | 近10日成交额相对均值 |
| vol_ratio_3 | 近3日成交量相对均值 |
| vol_ratio_5 | 近5日成交量相对均值 |
| turnover_ratio_5 | 近5日换手相对均值 |
| amount_close_strength_3 | 放量上涨强度 |
| amount_close_strength_5 | 放量上涨强度 |
| price_volume_divergence_5 | 价量背离 |
| high_turnover_breakout | 高换手突破 |
| high_turnover_low_position | 高换手低位 |
| abnormal_amount_spike | 成交额异常放大 |

### 5. 波动与风险特征

目标是可出手 Top3，不是单纯找高弹性股票，所以必须刻画亏损和回撤风险。

| 字段 | 含义 |
|---|---|
| volatility_3 | 3日波动 |
| volatility_5 | 5日波动 |
| volatility_10 | 10日波动 |
| amp_mean_3 | 3日平均振幅 |
| amp_mean_5 | 5日平均振幅 |
| max_intraday_amp_5 | 近5日最大振幅 |
| max_down_pct_5 | 近5日最大单日跌幅 |
| gap_down_count_5 | 近5日跳空下跌次数 |
| upper_shadow_mean_5 | 上影线压力 |
| close_position_in_day | 当日收盘在日内位置 |
| hot_but_low_range_position | 热门但位置不强 |
| tail_risk_score | 尾部亏损风险综合分 |

### 6. 横截面排名特征

模型目标是每天选 Top3，所以必须让模型知道股票在当天全市场中的相对位置。

| 字段 | 含义 |
|---|---|
| stock_market_ret_1_rank | 当日1日收益市场排名 |
| stock_market_ret_3_rank | 3日收益市场排名 |
| stock_market_ret_5_rank | 5日收益市场排名 |
| stock_market_ret_20_rank | 20日收益市场排名 |
| stock_market_turnover_rank | 换手率市场排名 |
| stock_market_amount_rank | 成交额市场排名 |
| stock_market_volatility_rank | 波动率市场排名 |
| stock_market_range_pos_rank | 20日位置市场排名 |
| stock_market_momentum_improve_rank | 动量改善市场排名 |

### 7. 行业内相对强弱特征

强势票通常不是孤立上涨，需要知道它在行业内部是不是强。

| 字段 | 含义 |
|---|---|
| stock_industry_ret_1_rank | 行业内1日收益排名 |
| stock_industry_ret_3_rank | 行业内3日收益排名 |
| stock_industry_ret_5_rank | 行业内5日收益排名 |
| stock_industry_ret_20_rank | 行业内20日收益排名 |
| stock_industry_turnover_rank | 行业内换手排名 |
| stock_industry_amount_rank | 行业内成交额排名 |
| stock_industry_momentum_improve_rank | 行业内动量改善排名 |
| stock_vs_industry_ret_5 | 个股5日收益减行业5日收益 |
| stock_vs_industry_ret_20 | 个股20日收益减行业20日收益 |
| stock_vs_industry_turnover_pct | 个股换手相对行业 |
| stock_vs_industry_range_pos_20 | 个股位置相对行业 |

### 8. 行业指数特征

行业强弱决定 10%票出现概率。

| 字段 | 含义 |
|---|---|
| industry_index_code | 行业指数代码 |
| industry_index_level | 行业级别 |
| industry_index_pct_chg | 行业指数当日涨跌 |
| industry_index_ret_3 | 行业指数3日收益 |
| industry_index_ret_5 | 行业指数5日收益 |
| industry_index_ret_10 | 行业指数10日收益 |
| industry_index_ret_20 | 行业指数20日收益 |
| industry_index_range_pos_20 | 行业指数20日位置 |
| industry_index_breakout_20 | 行业指数是否突破 |
| industry_index_amount_ratio_5 | 行业指数成交额放大 |
| industry_index_volatility_5 | 行业指数波动 |
| industry_index_ret_5_xrank | 行业5日收益横截面排名 |
| industry_index_ret_20_xrank | 行业20日收益横截面排名 |
| industry_index_hot_score | 行业热度综合分 |
| industry_index_risk_score | 行业风险综合分 |

### 9. 市场环境特征

每日 Top3 能不能出手高度依赖市场环境。

| 字段 | 含义 |
|---|---|
| market_up_ratio | 当日股票上涨占比 |
| market_avg_pct_chg | 当日平均涨跌幅 |
| market_median_pct_chg | 当日中位涨跌幅 |
| market_limit_up_count | 涨停数量 |
| market_limit_down_count | 跌停数量 |
| market_ge5_count | 当日涨幅 >=5% 数量 |
| market_ge10_count | 当日涨幅 >=10% 数量 |
| market_amount_total | 全市场成交额 |
| market_amount_ratio_5 | 全市场成交额放大 |
| market_risk_level | 市场风险等级 |
| market_regime | 市场状态 |
| index_sh_ret_5 | 上证5日收益 |
| index_hs300_ret_5 | 沪深300 5日收益 |
| index_zz500_ret_5 | 中证500 5日收益 |
| index_zz1000_ret_5 | 中证1000 5日收益 |

### 10. 题材与股票属性特征

如果题材字段质量可用，建议做轻量编码，不要直接把长文本塞进模型。

| 字段 | 含义 |
|---|---|
| board_code | 板块编码 |
| industry_code | 行业编码 |
| region_code | 地域编码 |
| concept_count | 概念数量 |
| hot_concept_hit_count | 命中热门概念数量 |
| is_beijing_exchange | 是否北交所 |
| is_chinext | 是否创业板 |
| is_star_market | 是否科创板 |
| listing_days | 上市天数 |

## 标签字段

这些字段落表，但禁止进入模型特征。

| 字段 | 含义 |
|---|---|
| future_5_trade_date | 5个交易日后的日期 |
| future_5_close | 5个交易日后的收盘价 |
| future_5_return | 5日后收益率 |
| future_5_direction | 5日后方向 |
| target_5d_up | future_5_return > 0 |
| target_5d_ge05 | future_5_return >= 5% |
| target_5d_ge10 | future_5_return >= 10% |
| target_5d_loss05 | future_5_return <= -5% |
| daily_future_return_rank | 当日真实未来收益排名 |
| daily_future_return_top3_label | 是否为当日真实未来收益Top3 |

## 建议模型输入视图

训练时建议从主表生成两个视图。

### 视图一：10%收益概率模型

目标：

```text
y = target_5d_ge10
```

用途：

```text
找到未来5日收益率可能 >=10% 的候选票
```

输出：

```text
prob_5d_ge10
rank_by_prob_5d_ge10
```

### 视图二：Top3强度排序模型

训练样本：

```text
只在 prob_5d_ge10 候选池 或 历史 target_5d_up / target_5d_ge05 样本中训练
```

目标可选：

```text
future_5_return
daily_future_return_rank
daily_future_return_top3_label
```

用途：

```text
在可能上涨的票中，找未来5日收益最强的3只
```

输出：

```text
strength_score_5d
final_top3_score = prob_5d_ge10 * strength_score_5d
```

## 最终信号表

文件建议：

```text
outputs/final_signals/每日Top3_10pct可出手信号_*.csv
```

字段：

| 字段 | 含义 |
|---|---|
| trade_date | 信号日期 |
| signal_rank | 最终排名，1到3 |
| is_final_signal | 是否最终出手 |
| signal_action | Top3 / Top2 / Top1 / 不出手 |
| symbol | 股票代码 |
| name | 股票名称 |
| industry | 行业 |
| prob_5d_ge10 | 5日收益>=10%概率 |
| strength_score_5d | 上涨强度分 |
| risk_score_5d | 亏损风险分 |
| final_top3_score | 最终Top3分 |
| signal_reason | 出手原因 |
| block_reason | 不出手原因 |
| future_5_trade_date | 回测用 |
| future_5_return | 回测用 |
| target_5d_ge10 | 回测用 |

## 当前旧表需要调整的点

当前 `个股k线特征数据.csv` 已经有不少可用字段，但相对新目标还缺几类关键特征：

- 缺少 `target_5d_ge10` 这类明确的 10%收益标签。
- 缺少 `ret_1/ret_2`、`range_pos_60`、`breakout_20_high`、`breakout_60_high` 等突破结构。
- 缺少更完整的成交额、成交量、价量背离和异常放量特征。
- 缺少市场涨停数量、当日强势股数量、全市场成交额等强行情环境特征。
- 缺少“真实当日未来收益Top3”标签，不利于训练最终 Top3 排序。
- 当前默认目标容易退化成普通方向预测，不足以支撑“未来5日收益10%以上”的业务目标。
