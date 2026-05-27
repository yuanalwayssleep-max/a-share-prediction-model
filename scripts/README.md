# Scripts

当前 `scripts/` 根目录只保留稳定入口脚本；分析、审计、实验和流水线内部步骤收进子目录。

1. 数据爬取脚本
   - `fetch_single_stock_5m_intraday.py`：爬取单个股票当日/近N日分时。主链路使用东方财富 `trends2`，必须带合法 `User-Agent` 和 `Referer`；先保存 1分钟K/分时线，再本地聚合 5分钟K，避开历史分钟 `kline/get` 偶发断连。
   - `fetch_stock_daily_k_batch.py`：批量爬取多个股票日K线；默认 `auto` 模式下沪深股票用 `baostock`，北交所股票用 `efinance`，并要求关键字段完整。北交所/东方财富链路默认每只随机停顿 2-3 秒、每 20 只冷却 10 秒，并输出瞬时失败率/最终失败率。

常用日K抓取命令：

```bash
python3 scripts/fetch_stock_daily_k_batch.py \
  --symbols-csv skills/a-share-kline-return-modeling/outputs/00_股票清单.csv \
  --output-dir data/单只股票日k \
  --start-date 2023-05-26 \
  --end-date 2026-05-26 \
  --limit 900 \
  --mode all
```

如果北交所 `efinance` 断连较多，可以调小批次并拉长冷却：

```bash
python3 scripts/fetch_stock_daily_k_batch.py \
  --provider auto \
  --efinance-batch-size 20 \
  --efinance-batch-sleep-seconds 10 \
  --efinance-min-sleep-seconds 2 \
  --efinance-max-sleep-seconds 3 \
  --retries 6 \
  --efinance-extra-retries 6
```
   - 抓取完成后会写出 `failed_symbols_日K.csv` 和 `incomplete_symbols_日K.csv`。模型输入只使用字段完整的数据，不使用新浪等字段不完整的兜底源。
   - `fetch_core_index_daily_k.py`：爬取核心指数日K，默认路径 `data/指数日K文件/00_核心指数日K.csv`；加 `--build-features` 时同步生成 `00_核心指数特征.csv`。

常用分钟/分时抓取命令：

```bash
python3 scripts/fetch_single_stock_5m_intraday.py \
  --symbol 002396 \
  --start-date 2026-05-26 \
  --end-date 2026-05-26 \
  --ndays 1 \
  --output-dir outputs/single_stock_intraday/2026-05-26
```

`--ndays 1` 表示当日分时，`--ndays 5` 表示最近 5 日分时。输出包含：

- `eastmoney_<市场代码>_1min_k.csv`
- `eastmoney_<市场代码>_5min_k.csv`
- `eastmoney_<市场代码>_intraday.csv`

2. 5日预测模型入口
   - `prepare_5d_model_data.py`：统一准备建模数据；内部调用 `scripts/pipeline/merge_daily_k_files.py` 和 `scripts/pipeline/split_5d_model_tables.py`。
   - `train_5d_direction_model.py`：训练/回测个股未来5日方向模型。
   - `train_5d_return_model.py`：训练/回测个股未来5日收益模型。
   - `run_5d_direction_batch.py`：批量运行 5日方向预测、修正层、信号层。
   - `apply_5d_prediction_postprocess.py`：统一运行市场风险修正、自适应阈值和信号决策层。

推荐预测链路：

1. 个股模型先对全股票池做上涨/下跌方向预测，得到每日个股上涨概率和原始方向。
2. 市场预测模型预测未来5日市场方向，并在方向修正层调整个股方向预测，目标是提高 `修正后预测涨跌` 的成功率。
3. 信号层只接收已经修正后的方向预测，再判断候选股是否进入可交易信号。

市场模型方向修正示例：

```bash
python3 scripts/postprocess/apply_market_risk_correction.py \
  --output-dir skills/a-share-kline-return-modeling/outputs/runs/<run> \
  --data-dir skills/a-share-kline-return-modeling/outputs \
  --dates <YYYYMMDD,YYYYMMDD> \
  --prediction-suffix <03文件后缀> \
  --output-suffix <10文件后缀> \
  --correction-policy v15 \
  --label-csv 00_A股日K.csv \
  --feature-csv 00_5日方向模型特征表.csv \
  --market-prediction-csv <06_市场5日方向预测结果汇总.csv>
```

信号层使用修正后的 `10_个股预测结果_市场风险修正...csv`：

```bash
python3 scripts/postprocess/apply_signal_decision_layer.py \
  --detail-csv <10_个股预测结果_市场风险修正.csv> \
  --output-prefix <输出前缀> \
  --decision-policy v18_confidence_topn \
  --daily-max-signals 2
```

常用建模数据准备命令：

```bash
python3 scripts/prepare_5d_model_data.py --all
```

训练前建议先跑数据质量审计，生成训练过滤标记：

```bash
python3 scripts/audit/audit_clean_5d_model_data.py
```

后续批量预测时接入质量标记，训练集会剔除硬异常、软异常和特征缺失偏高样本；锚点日股票池不受影响：

```bash
python3 scripts/run_5d_direction_batch.py \
  --train-quality-csv skills/a-share-kline-return-modeling/outputs/11_建模训练样本质量标记.csv \
  --dates <YYYYMMDD,YYYYMMDD>
```

常用指数日K和特征生成命令：

```bash
python3 scripts/fetch_core_index_daily_k.py \
  --start-date 2023-05-26 \
  --end-date 2026-05-26 \
  --build-features
```

3. 子目录
   - `scripts/pipeline/`：建模数据准备内部步骤。
   - `scripts/postprocess/`：预测后的风险修正和信号过滤底层脚本。
   - `scripts/analysis/`：分析和评估脚本。
   - `scripts/audit/`：数据和规则审计脚本。
   - `scripts/experiments/`：实验性市场方向模型脚本。
