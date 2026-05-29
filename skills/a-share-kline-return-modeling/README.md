# A股日K 5日Top3可出手模型

这个目录是 A 股 5 个交易日 Top3 可出手模型的独立工作区。核心目标是：每个交易日稳定选出 3 只可出手股票，并且模型训练目标明确指向未来 5 个交易日收益率 `>= 10%` 的股票。原始行情数据放在 `skills/a-share-data-fetching/data/` 下，本目录只保存清洗后的模型输入数据、模型脚本和预测输出。

## 流程

当前模型流程按下面顺序执行：

1. 清洗原始个股日K、核心指数日K和申万行业指数日K，生成稳定的模型输入表。
2. 运行个股 5 日收益阈值模型，第一层以未来 5 日收益率达到 20% 及以上作为“强上涨/爆发”训练目标，每个交易日输出 Top20 候选池；业务验收仍看最终 Top3 未来 5 日收益率 `>= 10%`。
3. 运行个股 5 日亏损风险模型，判断候选股未来 5 日亏损超过 5% 的概率。
4. 运行行业 5 日风险模型，判断候选股所属申万行业是否顺风、弱势或高位回落。
5. 运行未来 5 日市场风险模型，判断全市场环境。
6. 最终信号层同时读取个股强上涨概率、亏损风险、行业预测和市场预测，固定输出每日 Top3；市场预测当前只保留诊断字段，不作为后置分数矫正。

## 目录规则

所有 5 日预测相关脚本都放在：

- `skills/a-share-kline-return-modeling/scripts/`

清洗后的模型输入数据放在：

- `skills/a-share-kline-return-modeling/data/`

清洗脚本输出三张核心数据表：

- `data/个股k线特征数据.csv`
- `data/指数k线特征数据.csv`
- `data/行业指数特征数据.csv`

后续模型只读取这些清洗后的核心表，不再依赖中间表。字段名以 `future_5_*` 开头的是训练和回测标签，只能作为答案 `y` 使用，不能进入模型特征 `X`，避免偷用未来数据。

## 目标与训练方案

当前 skill 的核心目标不是普通方向预测，而是：

```text
每个交易日稳定选出3只可出手股票，并且目标收益为未来5个交易日收益率 >= 10%
```

训练方案详见：

- `docs/top3_10pct_feature_table_design.md`
- `docs/top3_10pct_training_plan.md`
- `docs/top3_10pct_training_workflow.md`

第一版训练采用滚动时间切分：

```text
训练集：T-730天 到 T-90天
验证集：T-90天 到 T-10天
预测集：T
```

并且每条训练/验证样本必须满足：

```text
future_5_trade_date < 当前训练/验证截止日
```

禁止随机切分，禁止在测试月份调参后再报告该月份效果。

## 数据清洗

```bash
python3 skills/a-share-kline-return-modeling/scripts/00_clean_data.py
```

默认读取原始数据目录：

- `skills/a-share-data-fetching/data/`

清洗后得到：

- `个股k线特征数据.csv`：个股日K、基础行情、质量标记、特征工程、未来 5 日标签。
- `指数k线特征数据.csv`：核心指数日K、指数特征、未来 5 日标签。
- `行业指数特征数据.csv`：申万行业指数日K、行业指数特征、未来 5 日标签。

清洗脚本会把能按行业名称匹配到的申万行业指数特征合并进 `个股k线特征数据.csv`，字段名前缀为 `industry_index_*`，并保留 `stock_vs_industry_index_ret_*` 这类个股相对行业指数强弱字段。

## 个股10%收益预测

当前主脚本只保留一套收敛后的第一层方案：用未来 5 日收益率 `>=20%` 作为强上涨训练目标，固定 60 个特征，固定 LightGBM baseline 参数，固定末端风险扣分，每天输出 Top20 候选池。业务验收仍看最终信号层 Top3 未来 5 日收益 `>=10%` 的命中情况。

```bash
python3 skills/a-share-kline-return-modeling/scripts/01_predict_stock_direction.py \
  --stock-list skills/a-share-kline-return-modeling/data/00_股票清单.csv \
  --start-date 2026-04-01 \
  --end-date 2026-04-30
```

说明：

- 固定使用 LightGBM 二分类模型。
- 正样本固定定义为未来 5 日收益率 `>=20%`，用于学习更强的上涨信号；业务验收仍统计 Top3 未来 5 日收益 `>=10%`。
- 特征固定为当前收敛后的 `compact60`，不在主脚本里保留 `compact40/compact80/all` 研究分支。
- 每个锚点日固定输出最终得分最高的 20 只候选股票。
- 预测股票池固定剔除 ST 股票。
- 个股模型只负责生成候选池和收益候选概率，最终 Top3 由亏损风险模型、市场风险模型、行业风险模型和最终信号层重排后产生。

## 市场风险预测

用于预测未来 5 日市场方向和风险状态：

```bash
python3 skills/a-share-kline-return-modeling/scripts/02_predict_market_risk.py \
  --start-date 2026-04-01 \
  --end-date 2026-04-30
```

说明：

- 固定使用 LightGBM 二分类模型。

输出目录：

- `outputs/market_risk_predictions/`

## 个股亏损风险预测

用于预测个股未来 5 日收益率是否可能低于 `-5%`：

```bash
python3 skills/a-share-kline-return-modeling/scripts/02c_predict_stock_loss_risk.py \
  --start-date 2026-04-01 \
  --end-date 2026-04-30
```

输出目录：

- `outputs/stock_loss_risk_predictions/`

## 行业风险预测

用于预测申万行业未来 5 日方向和风险状态：

```bash
python3 skills/a-share-kline-return-modeling/scripts/02b_predict_industry_risk.py \
  --start-date 2026-04-01 \
  --end-date 2026-04-30 \
  --levels L1,L2,L3
```

输出目录：

- `outputs/industry_risk_predictions/`

## 最终信号层

最终信号层负责把候选股票池重排成每天固定 Top3。市场状态不再决定出手数量；市场风险原则上应优先进入个股模型学习，但当前直接入模版本尚未跑赢基线，所以信号层只保留市场分档诊断：

- `A强机会`
- `B偏强`
- `C中性`
- `D偏弱`
- `E高风险`

运行示例：

```bash
python3 skills/a-share-kline-return-modeling/scripts/03_apply_signal_decision_layer.py \
  --stock-prediction skills/a-share-kline-return-modeling/outputs/stock_direction_predictions/个股5日收益20pct预测_LightGBM_compact60_Top20候选_20260401_20260430_系统日期20260529.csv \
  --market-prediction skills/a-share-kline-return-modeling/outputs/market_risk_predictions/市场5日风险预测_20260401_20260430_系统日期20260526.csv \
  --stock-loss-risk-prediction skills/a-share-kline-return-modeling/outputs/stock_loss_risk_predictions/个股5日亏损风险预测_LightGBM_20260401_20260430_系统日期20260526.csv \
  --industry-prediction skills/a-share-kline-return-modeling/outputs/industry_risk_predictions/行业5日风险预测_LightGBM_20260401_20260430_系统日期20260526.csv
```

信号层会读取 `个股k线特征数据.csv` 做候选股风险识别。它不会重新训练模型，只做最后排序校准。行业风险模型在这里作为第二阶段校准器：行业顺风时小幅加分，行业高风险或弱势延续时小幅扣分，并参与脆弱候选识别。节假日不是单独专题流程，而是和市场风险、市场宽度、行业强弱一样作为信号层参考项：

- 小闭环第一层用未来 5 日收益率 `>=20%` 作为强上涨目标，先输出 Top20 候选池；信号层根据该概率、亏损风险和行业风险重排得到最终 Top3。
- 市场分档同时看市场风险模型、市场宽度、市场平均涨跌幅、5日强势股比例和5日下跌扩散比例。
- 市场风险模型不单独一票否决；风险预测被市场宽度或跌幅扩散确认时，进入 `D偏弱` 或 `E高风险` 诊断档。
- 候选股脆弱性只影响分数和排序，不直接过滤最终 Top3。
- 高位、高换手、高波动且行业支撑不足的候选股会被视为脆弱候选。
- 中期涨幅高、短期已经转弱，同时换手和波动仍高，且市场/行业当天偏弱的候选股会被视为脆弱候选。
- 市场处于高风险时，当天大跌但仍靠强动量得到高分的候选股会被视为脆弱候选。
- 市场处于高风险时，涨停附近且处在 20 日高位区的候选股会被视为脆弱候选，避免在高风险环境追高位板。
- 市场宽度过弱、市场风险偏高的影响不在信号层硬扣分；只有当市场入模版本跑赢基线后，才进入主路径。
- 长假前后风险只参与排序修正，不作为独立空仓规则。

注意：信号层规则如果是根据某个月的历史结果调出来的，只能先视为样本内优化。每次新增规则后，需要至少用其他月份回测，确认没有明显误伤，再进入稳定规则。

输出目录：

- `outputs/final_signals/`

## 节假日参考项

节假日特征已经写入清洗后的个股表和指数表。清洗脚本会根据交易日之间的长休市间隔自动识别假期，不手工维护节日表。

清洗表新增的节假日特征包括：

- `is_pre_holiday_3`：是否处在节前 3 个交易日。
- `is_post_holiday_3`：是否处在节后 3 个交易日。
- `pre_holiday_tday`：距离长假前最后一个交易日还有几个交易日。
- `post_holiday_tday`：长假后第几个交易日。
- `holiday_gap_days`：本次休市自然日长度。

这些字段由 `00_clean_data.py` 生成，并在 `03_apply_signal_decision_layer.py` 中参与最终出手修正。不要把节假日作为独立预测脚本长期维护。

## 当前保留脚本

当前收敛后的主流程保留下面 5 个脚本：

- `scripts/00_clean_data.py`：清洗原始数据，生成三张模型输入表。
- `scripts/01_predict_stock_direction.py`：个股未来 5 日收益阈值概率预测，小闭环默认阈值为 >=10%。
- `scripts/02_predict_market_risk.py`：市场风险预测。
- `scripts/02b_predict_industry_risk.py`：行业风险预测。
- `scripts/02c_predict_stock_loss_risk.py`：个股未来 5 日亏损风险预测。
- `scripts/03_apply_signal_decision_layer.py`：最终 Top3 排序校准信号。

## 核心原则

- 原始数据只读，不在模型脚本中直接训练。
- 模型输入只使用 `个股k线特征数据.csv`、`指数k线特征数据.csv` 和 `行业指数特征数据.csv`。
- `future_5_*` 字段只能用于训练标签和回测判卷，不能作为预测特征。
- 单次预测输出尽量保持一张结果表，文件名包含预测日期范围和系统日期。
- 默认优先关注每日 Top1、Top2、Top3 最终信号表现，而不是全市场所有股票方向准确率。
