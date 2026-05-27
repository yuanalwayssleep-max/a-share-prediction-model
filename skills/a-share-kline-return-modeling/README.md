# A股日K 5日预测模型

这个目录是 A 股 5 个交易日预测模型的独立工作区。原始数据仍然放在仓库根目录的 `data/` 下，本目录只保存清洗后的模型输入数据、模型脚本和预测输出。

## 流程

当前模型流程按下面顺序执行：

1. 清洗原始个股日K和指数日K，生成稳定的模型输入表。
2. 运行个股 5 日 Top 股票池预测模型，判断个股是否更可能进入同日未来 5 日收益 Top 分位。
3. 运行未来 5 日市场风险模型，判断市场环境。
4. 最终信号层同时读取个股预测和市场预测，决定 `Top3 / Top2 / Top1 / 不出手`。

## 目录规则

所有 5 日预测相关脚本都放在：

- `skills/a-share-kline-return-modeling/scripts/`

清洗后的模型输入数据放在：

- `skills/a-share-kline-return-modeling/data/`

清洗脚本只输出两张核心数据表：

- `data/个股k线特征数据.csv`
- `data/指数k线特征数据.csv`

后续模型只读取这两张表，不再依赖中间表。字段名以 `future_5_*` 开头的是训练和回测标签，只能作为答案 `y` 使用，不能进入模型特征 `X`，避免偷用未来数据。

## 数据清洗

```bash
python3 skills/a-share-kline-return-modeling/scripts/clean_data.py
```

清洗后得到：

- `个股k线特征数据.csv`：个股日K、基础行情、质量标记、特征工程、未来 5 日标签。
- `指数k线特征数据.csv`：核心指数日K、指数特征、未来 5 日标签。

## 个股 Top 股票池预测

当前收敛方案只使用 Top 股票池预测。它用于每天挑选模型认为更可能进入未来 5 日收益 Top20 的股票。下面例子是每天只输出排名前 3 只：

```bash
python3 skills/a-share-kline-return-modeling/scripts/predict_stock_direction.py \
  --stock-list skills/a-share-kline-return-modeling/data/00_股票清单.csv \
  --start-date 2026-04-01 \
  --end-date 2026-04-30
```

说明：

- 固定使用 LightGBM 二分类模型。
- 默认 `--target-mode top_quantile`：训练目标是“是否进入同日未来 5 日收益前 N 分位”。
- 默认 `--top-quantile 0.2`：前 20% 作为正样本。
- 默认 `--top-n 3`：每个锚点日只输出模型排序前 3 只。
- 如需研究旧方向模型，可显式加 `--target-mode direction`。
- 预测股票池默认剔除 ST 股票。
- 如果要保留 ST，可加 `--include-st-prediction`。
- `--enable-overheat-penalty` 是研究开关，用于测试高换手、高波动、强动量、高位票的衰竭惩罚；默认不启用，因为它可能误伤强势延续行情。

## 市场风险预测

用于预测未来 5 日市场方向和风险状态：

```bash
python3 skills/a-share-kline-return-modeling/scripts/predict_market_risk.py \
  --start-date 2026-04-01 \
  --end-date 2026-04-30
```

说明：

- 固定使用 LightGBM 二分类模型。

输出目录：

- `outputs/market_risk_predictions/`

## 最终信号层

最终信号层负责把候选股票池压缩成四档动作：

- `Top3`：当天最多买 3 只。
- `Top2`：当天最多买 2 只。
- `Top1`：当天只买 1 只。
- `不出手`：当天空仓观察。

运行示例：

```bash
python3 skills/a-share-kline-return-modeling/scripts/apply_signal_decision_layer.py \
  --stock-prediction skills/a-share-kline-return-modeling/outputs/stock_direction_predictions/个股5日Top20预测_Top3输出_20260401_20260430_系统日期20260526.csv \
  --market-prediction skills/a-share-kline-return-modeling/outputs/market_risk_predictions/市场5日风险预测_20260401_20260430_系统日期20260526.csv
```

信号层会读取 `个股k线特征数据.csv` 做候选股风险识别。它不会重新训练模型，只做最后的出手判断：

- 高位、高换手、高波动且行业支撑不足的候选股会被视为脆弱候选。
- 中期涨幅高、短期已经转弱，同时换手和波动仍高，且市场/行业当天偏弱的候选股会被视为脆弱候选。
- 市场处于高风险时，当天大跌但仍靠强动量得到高分的候选股会被视为脆弱候选。
- 市场处于高风险时，涨停附近且处在 20 日高位区的候选股会被视为脆弱候选，避免在高风险环境追高位板。
- 市场宽度过弱、市场风险偏高时会降低出手数量或不出手。
- 当 Top 分数接近时，可以分散到 Top2 或 Top3。
- 长假节后如果市场宽度不足，会直接不出手。
- 节前高风险超跌反弹不追。

注意：信号层规则如果是根据某个月的历史结果调出来的，只能先视为样本内优化。每次新增规则后，需要至少用其他月份回测，确认没有明显误伤，再进入稳定规则。

输出目录：

- `outputs/final_signals/`

## 节假日前后专题预测

节假日特征已经写入清洗后的个股表和指数表。脚本会根据交易日之间的长休市间隔自动识别假期，不手工维护节日表。

清洗表新增的节假日特征包括：

- `is_pre_holiday_3`：是否处在节前 3 个交易日。
- `is_post_holiday_3`：是否处在节后 3 个交易日。
- `pre_holiday_tday`：距离长假前最后一个交易日还有几个交易日。
- `post_holiday_tday`：长假后第几个交易日。
- `holiday_gap_days`：本次休市自然日长度。

运行 2025 春节前至今的节假日前后窗口预测：

```bash
python3 skills/a-share-kline-return-modeling/scripts/predict_holiday_windows.py \
  --start-date 2025-01-01 \
  --end-date 2026-05-26
```

输出目录：

- `outputs/holiday_window_predictions/`

## 当前保留脚本

当前收敛后的主流程只保留下面 4 个脚本：

- `scripts/clean_data.py`：清洗原始数据，生成两张模型输入表。
- `scripts/predict_stock_direction.py`：个股 Top 股票池预测。
- `scripts/predict_market_risk.py`：市场风险预测。
- `scripts/apply_signal_decision_layer.py`：最终四档出手信号。

节假日前后专题使用：

- `scripts/predict_holiday_windows.py`：只对节前/节后窗口锚点做预测和汇总。

## 核心原则

- 原始数据只读，不在模型脚本中直接训练。
- 模型输入只使用 `个股k线特征数据.csv` 和 `指数k线特征数据.csv`。
- `future_5_*` 字段只能用于训练标签和回测判卷，不能作为预测特征。
- 单次预测输出尽量保持一张结果表，文件名包含预测日期范围和系统日期。
- 默认优先关注每日 Top1、Top2、Top3、Top5 股票池表现，而不是全市场所有股票方向准确率。
