# A股5日预测模型 V1 开发计划与里程碑

更新时间：2026-05-29 GMT+8

## 一、V1 总目标

把当前标签方案和技术方案落成一条可运行、可验证、可复盘的最小闭环：

```text
原始日K + 股票清单
  -> 可交易口径特征与标签
  -> 数据质量报告
  -> 基准策略评估
  -> 个股5日强势排序模型
  -> 信号级评估
  -> 组合级资金曲线回测
  -> walk-forward 验证
```

V1 的重点不是把模型做复杂，而是确认：

```text
口径正确
无未来泄漏
成本可复现
交易可执行
评估链路可靠
模型至少打败简单基准
```

## 二、开发原则

```text
先评估链路，再训练模型。
先基准策略，再机器学习。
先防泄漏，再追收益。
先信号级评估，再组合级回测。
先稳定性，再复杂度。
```

硬规则：

```text
主回测口径：T 日收盘后出信号，T+1 open 买入，T+6 open 卖出。
VWAP-to-VWAP 只做对照回测，不做唯一验收口径。
T+1 开盘后才知道的字段不能进入 T 日模型和信号排序。
买入不可成交默认不顺延；卖出不可成交允许顺延并记录。
future_*、label_*、entry_price、exit_price、actual_* 不得进入模型特征。
成本、滑点、流动性阈值全部从配置读取。
最终测试集只评估一次，不能边看测试集边调参。
```

## 三、里程碑总览

| 里程碑 | 名称 | 目标 | 验收关键词 |
|---|---|---|---|
| M0 | 项目基线 | 固定目录、配置和字段口径 | `backtest.yaml`、黑白名单 |
| M1 | 特征与标签 | 生成 clean 特征、标签和质量报告 | `rank_pct`、TopK、可交易收益 |
| M2 | 评估与基准 | 先跑通随机/动量等基准 | 信号级评估、组合级回测 |
| M3 | 个股排序模型 | Top50 候选池召回 + 规则二次排序 Top3 | 保留 raw 基线，二次排序有增量 |
| M4 | Walk-forward | 至少 12 个月滚动验证 | 月度稳定性、bootstrap |
| M5 | 市场机会模型 | 控制 Top3/Top2/Top1/不出手 | 降低低机会日无效出手 |
| M6 | 信号层 | 生成最终信号和执行过滤 | 无 truth 字段、可复盘 |
| M7 | 测试固化 | 防止后续改坏口径 | pytest 小样本测试 |
| M8 | 增强迭代 | 再考虑辅助模型和复杂融合 | 消融有正增量 |

## 四、M0 项目基线

### 目标

固定 V1 目录、配置、字段白名单/黑名单和回测协议。

### 交付物

```text
skills/a-share-kline-return-modeling/configs/backtest.yaml
skills/a-share-kline-return-modeling/tests/
skills/a-share-kline-return-modeling/samples/
skills/a-share-kline-return-modeling/outputs/evaluation/
```

### `backtest.yaml` 必须包含

```text
signal_time
feature_cutoff_time
primary_entry_price_type
primary_exit_price_type
benchmark_entry_price_type
benchmark_exit_price_type
holding_trade_days
commission_rate
stamp_tax_rate
transfer_fee_rate
min_commission
buy_slippage_rate
sell_slippage_rate
min_listing_days
min_amount
min_avg_amount_5
replace_unfilled_entry
allow_exit_delay
max_picks_per_industry
```

### 验收标准

```text
配置文件可被脚本读取。
字段黑名单明确禁止 future_* / label_* / entry_price / exit_price / actual_*。
字段分层明确 signal_known_features 和 execution_known_filters。
未意外恢复已清空的数据和脚本。
```

## 五、M1 特征与标签构建

### 目标

实现最小版 `00_build_features.py`，生成建模输入表和数据质量报告。

### 输入

```text
skills/a-share-data-fetching/data/单只股票日k/*.csv
skills/a-share-kline-return-modeling/data/00_股票清单.csv
skills/a-share-kline-return-modeling/configs/backtest.yaml
```

### 输出

```text
skills/a-share-kline-return-modeling/data/clean_stock_features.csv
skills/a-share-kline-return-modeling/data/clean_market_features.csv
skills/a-share-kline-return-modeling/outputs/evaluation/data_quality_report.md
```

### 必须实现

```text
股票池过滤
字段标准化
基础技术特征
行业强度 V1 公式
市场宽度特征
T+1 open -> T+6 open 可交易收益
成本和滑点扣减
future_5_return_rank
future_5_return_rank_pct
label_top10 / label_top30 / label_top50
label_top1pct / label_top2pct / label_top5pct
absolute_strong_label
label_direction
market opportunity 标签和 lag1 特征
可交易与成交失败字段
```

### 关键口径

```text
entry_trade_date = T 后第 1 个市场交易日，不因个股停牌或涨停顺延。
买入不可成交：该信号未成交，默认不递补。
卖出不可成交：顺延到下一可卖出日，并记录 forced_exit_delay_days。
rank_pct = 1 - (future_5_return_rank - 1) / (daily_stock_count - 1)。
当日最高收益 rank_pct = 1.0，最低收益 rank_pct = 0.0。
```

### 数据质量报告必须包含

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

### 验收标准

```text
clean 表能完整生成。
rank_pct 方向正确。
Top30 每日数量符合预期。
market lag 特征无当天标签泄漏。
data_quality_report.md 能解释主要异常。
```

## 六、M2 评估脚本与基准策略

### 目标

先实现 `04_evaluate_top3.py`，不用模型，先用简单基准把评估链路跑通。

### 输入

```text
clean_stock_features.csv
backtest.yaml
任意 predictions.csv 格式候选文件
```

### 输出

```text
outputs/evaluation/daily_detail.csv
outputs/evaluation/monthly_summary.csv
outputs/evaluation/baseline_compare.csv
outputs/evaluation/bootstrap_confidence_interval.csv
outputs/evaluation/portfolio_curve.csv
```

### 必须支持的基准

```text
随机 Top3
近5日收益率 Top3
近20日收益率 Top3
近5日成交额增幅 Top3
近5日换手率 Top3
行业强度 Top3
简单 LightGBM 回归 future_5_return 基准
```

### 评估分两层

```text
信号级评估：每日 Top3 平均收益、Top10/Top30 命中、不可交易归因。
组合级回测：每日开仓、持有5日、资金占用、重叠持仓、现金比例。
```

### 组合级 V1 规则

```text
每日最多新开 Top3。
单日新仓预算 = 总资产的 1/5。
每只入选股票等权。
总持仓上限 100%。
未出手或未成交资金保留现金。
卖出资金在实际卖出后可复用。
卖出日无法成交则顺延，并继续占用仓位。
```

### 验收标准

```text
能评估人工/规则预测文件。
所有成本参数写入输出。
能按日、按月复盘。
能输出资金曲线、最大回撤、现金比例、未成交比例。
能列出低命中日期和极端贡献日期。
```

## 七、M3 个股强势排序模型

### 目标

实现 `01_train_stock_rank_model.py`，训练主模型 `rank_strength_score`。根据 CR-20260529-001，M3 不再要求 raw model score 直接完成最终 Top3 排序，而是拆成：

```text
M3-A：使用 rank_strength_score 召回 Top50 候选池。
M3-B：在 Top50 候选池内，用已批准规则二次排序选 Top3。
```

raw model score Top3 必须作为基线保留，不能删除或被新规则覆盖。

### V1 模型

```text
默认主模型：LightGBMClassifier
默认目标：label_top50
输出分数：rank_strength_score = Top50 概率
训练方式：walk-forward / rolling train
```

保留可回退模式：

```text
raw_rank_pct_regression：LightGBMRegressor / future_5_return_rank_pct
top30_classifier：LightGBMClassifier / label_top30
weighted_rank_pct_regression：LightGBMRegressor / 加权 future_5_return_rank_pct
```

如果 LightGBM 环境缺失，可临时用 sklearn 模型兜底，但必须记录。

### 强制防泄漏

```text
train_df = df[df["future_5_trade_date"] < anchor_date]
```

不能只用：

```text
trade_date < anchor_date
```

### 输出

```text
outputs/stock_rank_predictions/predictions.csv
outputs/stock_rank_predictions/predictions_with_truth.csv
outputs/evaluation/stock_rank_model_metrics.json
outputs/evaluation/rerank_strategy_summary.md
outputs/evaluation/m3_recall_model_compare.md
outputs/evaluation/m3_candidate_rerank_report.md
outputs/evaluation/m3_risk_control_report.md
```

### `predictions.csv` 规则

```text
只能包含 T 日收盘后已知字段。
不能包含 future_* / label_*。
不能包含 tradable_at_entry / limit_up_at_entry / entry_price。
不能包含 tradable_at_exit / actual_*。
```

### 验收标准

```text
M3-A：Top50 候选池平均真实 Top30 命中显著高于随机 Top50。
M3-A：低召回月份必须可解释。
M3-B：最终 Top3 扣费后平均收益 > 随机 Top3。
M3-B：最终 Top3 平均收益 >= 最强简单基准之一。
M3-B：最终 Top3 平均 Top30 命中 > raw model Top3。
M3-B：至少 2/3 验证月份收益优于随机。
M3-B：收益不是由少数极端日期贡献。
必须同时输出 raw model Top3 基线和二次排序结果。
第一版只允许 ret_20、blend_model_low_overheat、blend_model_amount 三个规则二次排序。
```

## 八、M4 Walk-forward 验证

### 目标

验证模型不是只在少数月份有效。

### 验证范围

```text
冒烟验证：至少 3 个月。
正式 walk-forward：至少 12 个月。
独立测试集：最近 3-6 个月，冻结不反复调参。
```

### 输出

```text
outputs/evaluation/walk_forward_summary.csv
outputs/evaluation/monthly_stability.csv
outputs/evaluation/regime_breakdown.csv
outputs/evaluation/portfolio_backtest/portfolio_ledger.csv
outputs/evaluation/portfolio_backtest/portfolio_curve.csv
outputs/evaluation/portfolio_backtest/portfolio_backtest_report.md
```

### 验收标准

```text
至少 2/3 验证月份优于随机基准。
不能只靠单月贡献。
bootstrap 置信区间不能完全不显著。
open-to-open 主口径有效。
VWAP-to-VWAP 对照口径不矛盾。
组合级回测必须现金约束，持仓暴露不超过 100%。
卖出资金在实际退出后才能复用。
```

## 九、M5 市场机会模型

### 目标

实现 `02_train_market_opportunity_model.py`，只控制出手数量，不参与同日个股排序。

### 标签与诊断目标

```text
future_market_10pct_density
market_opportunity_label
market_top5pct_avg_return
market_top30_avg_return
market_positive_ratio
market_extreme_return_density_5pct
market_extreme_return_density_10pct
```

### 输出

```text
outputs/market_opportunity_predictions/market_opportunity_predictions.csv
outputs/evaluation/market_opportunity_model_metrics.json
```

### 验收标准

```text
market_10pct_density_ma5_lag1 必须 shift(1) 后 rolling。
低机会日减少无效出手。
不能大幅牺牲高机会日收益。
能解释是在识别整体上涨，还是识别高弹性机会。
```

## 十、M6 信号层与执行过滤

### 目标

实现 `03_generate_final_signals.py`，生成 Top3 / Top2 / Top1 / 不出手。

### V1 排序分

```text
stock_score =
  0.70 * rank_strength_score
+ 0.20 * industry_strength_score
```

V1 不把 `risk_penalty` 放进连续分。风险先做：

```text
硬过滤：ST、新股、停牌、低流动性、买入不可成交。
归因/轻量降级：近涨停、高位高换手、过热、弱行业。
```

### 出手数量

```text
市场机会高：最多 Top3
市场机会中：最多 Top2
市场机会低：最多 Top1
市场机会极低：不出手
```

### 验收标准

```text
最终信号文件不包含 future_* / label_* / truth 字段。
T 日最终信号不使用 T+1 开盘后才知道的字段。
每个交易日最多 3 只股票。
出手数量由市场机会分数控制。
输出不出手日期和原因。
```

## 十一、M7 小样本测试与口径固化

### 目标

用最小样本测试守住最容易出错的口径。

### 交付物

```text
samples/small_stock_daily_k.csv
samples/small_stock_list.csv
tests/test_label_rank_direction.py
tests/test_no_future_feature_leakage.py
tests/test_market_density_lag.py
tests/test_future_5_trade_date_filter.py
tests/test_backtest_cost_calculation.py
tests/test_signal_file_has_no_truth_columns.py
```

### 验收标准

```text
python3 -m pytest skills/a-share-kline-return-modeling/tests 可运行。
测试不依赖全量行情数据。
排名方向、成本扣减、market lag、防泄漏、信号文件字段均有覆盖。
```

## 十二、M8 增强迭代

V1 稳定后再考虑：

```text
LightGBMRanker / LambdaRank
10% 强势辅助模型
方向辅助模型
Top30 概率校准模型
更丰富行业数据
复杂风险扣分
多模型 stacking
自动调参
外部资金流数据
```

合入条件：

```text
必须和 V1 baseline 做消融对照。
必须至少在 12 个月 walk-forward 中有正增量。
不能只提高单月收益。
不能通过减少出手天数制造表面高胜率。
不能引入更高泄漏风险。
```

## 十三、推荐执行顺序

```text
M0 项目基线
M1 特征与标签构建
M2 评估脚本与基准策略
M7 小样本测试与口径固化
M3 个股强势排序模型
M4 Walk-forward 验证
M5 市场机会模型
M6 信号层与执行过滤
M8 增强迭代
```

核心理由：

```text
先把数据口径和评估链路锁死，再训练模型。
先证明简单基准，再证明机器学习有增量。
先让测试覆盖关键口径，再做复杂信号层。
```

## 十四、第一阶段建议目标

### Day 1

```text
创建 backtest.yaml。
实现字段读取、股票池过滤、字段标准化。
跑出第一版 clean_stock_features.csv。
```

### Day 2

```text
实现 T+1 open -> T+6 open 标签。
实现成本扣减和 rank_pct。
输出 data_quality_report.md。
```

### Day 3

```text
实现随机/动量/成交额/换手率/行业强度基准。
实现信号级评估。
检查 TopK 命中和收益口径。
```

### Day 4

```text
实现组合级资金曲线回测。
补小样本测试。
修复泄漏字段和交易日窗口问题。
```

### Day 5

```text
实现个股排序 baseline。
跑 3 个月冒烟验证。
输出第一版复盘结论。
```

## 十五、V1 完成定义

V1 完成必须同时满足：

```text
一条命令能构建 clean 特征和标签。
一条命令能生成 data_quality_report.md。
一条命令能跑随机/动量/成交额/换手率/行业强度基准。
一条命令能训练个股排序模型。
一条命令能输出信号级评估和组合级回测。
测试能证明关键字段没有未来泄漏。
评估文件记录完整交易成本、滑点、复权和价格口径。
至少完成 3 个月冒烟验证。
正式验收前完成至少 12 个月 walk-forward。
```

## 十六、暂不做

```text
不先做复杂深度学习模型。
不先做多模型 stacking。
不先接入更多外部数据源。
不先做自动交易或实盘下单。
不把 VWAP 口径作为唯一验收。
不根据测试集反复调参。
不在没有测试保护的情况下大改标签口径。
```
