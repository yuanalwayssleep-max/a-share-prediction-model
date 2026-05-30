# RD 结构性代码审查报告

审查日期：2026-05-30 GMT+8
审查角色：rd / engineering lead
项目路径：`/Users/cocoon/Documents/code/a-share-prediction-model`
报告类型：结构性代码检查 / Code Review / 质量风险评估

## 1. 保存位置说明

PM 建议将本报告保存于：

```text
skills/a-share-kline-return-modeling/docs/code_reviews/2026-05-30-structural-code-review.md
```

理由：

- 代码审查报告是长期增长型资产，需要单独目录持续沉淀，避免和一次性验收报告、CR、小时报混在一起。
- 当前项目治理文档集中在 `skills/a-share-kline-return-modeling/docs/`，因此代码审查归档在 `docs/code_reviews/`。
- 本报告属于工程质量评审和结构性风险记录，不是模型实验产物，不应放入 `outputs/evaluation/`。
- 本报告暂不直接修改 `risk_register.md`、`decision_log.md`、`implementation_plan.md` 等治理/计划文档；若后续要同步 P0/P1 风险到风险台账，应由 PM 单独确认后执行。

## 2. 审查范围

RD 按 review-only 范围检查了：

- `git status`
- 根 `README.md`
- `skills/a-share-kline-return-modeling/README.md`
- `STATUS.md`
- 配置、测试、核心脚本和部分新增脚本
- 重点脚本：`00_build_features.py`、`01_train_stock_rank_model.py`、`05_run_walk_forward.py`、`08_evaluate_m3a_recall_experiments.py`、`14_backtest_portfolio_curve.py`、`21_generate_final_signals.py`、`22_backtest_final_signals.py`

执行过的轻量检查：

- AST 级重复扫描
- `py_compile` 静态编译
- 现有 pytest 尝试运行

未执行事项：

- 未读取 `.env`、密钥、敏感日志。
- 未修改业务文件。
- 未回滚或清理用户已有变更。

## 3. 总体结论

```text
代码能跑的部分不少，但当前最大风险是数据边界和执行链路边界不够硬。
尤其是 truth/future 字段混放、最终信号脚本允许 truth 输入、组合回测依赖 predictions_with_truth.csv，都会放大未来信息泄漏和口径漂移风险。
```

优先级判断：

1. 先做防泄漏收口。
2. 再修回测口径。
3. 再补训练健壮性。
4. 最后做结构重构和公共包抽取。

## 4. 主要发现

### P0-001：市场特征文件混入未来 truth，存在结构性泄漏风险

参考位置：

- `skills/a-share-kline-return-modeling/scripts/00_build_features.py:354`
- `skills/a-share-kline-return-modeling/scripts/00_build_features.py:364`
- `skills/a-share-kline-return-modeling/configs/backtest.yaml:40`

问题：

`build_market_features()` 同时产出 T 日可知市场特征和基于 `future_5_return` / `label_top30` 的未来统计字段，例如：

```text
future_market_10pct_density
market_top5pct_avg_return
market_top30_avg_return
market_positive_ratio
market_extreme_return_density_*
```

这些字段写入统一的 `clean_market_features.csv`，后续 gating、sizing、final signal 脚本读取同一文件。即使部分脚本当前只用 lag 字段，这种同表混放仍违反执行链路的防泄漏原则，后续极易误用。

建议：

- 拆分 `market_signal_features.csv` 和 `market_truth_labels.csv`。
- 所有执行/信号脚本入口加入 schema guard。
- 对 `future_*`、`label_*`、truth 字段和配置中禁止字段做黑名单校验。

### P0-002：最终信号生成允许读取 truth 输入

参考位置：

- `skills/a-share-kline-return-modeling/scripts/21_generate_final_signals.py:69`
- `skills/a-share-kline-return-modeling/scripts/21_generate_final_signals.py:224`

问题：

`21_generate_final_signals.py` 提供 `--use-truth-input`，可直接读取 `predictions_with_truth.csv`。虽然输出列做了过滤，但执行信号入口允许 truth 数据源进入，本身就不应存在。

建议：

- 最终信号脚本只接受 truth-free `predictions.csv`。
- 如需回测兼容，拆成 eval-only 脚本或专用 backtest 输入。
- 最终信号脚本启动时断言输入列不含 truth/future/label 字段。

### P1-001：组合回测默认读取 `predictions_with_truth.csv`，预测产物和判卷 truth 耦合

参考位置：

- `skills/a-share-kline-return-modeling/scripts/14_backtest_portfolio_curve.py:17`
- `skills/a-share-kline-return-modeling/scripts/14_backtest_portfolio_curve.py:19`
- `skills/a-share-kline-return-modeling/scripts/14_backtest_portfolio_curve.py:70`

问题：

组合回测从月度目录读取 `predictions_with_truth.csv`，随后又 merge `clean_stock_features.csv` 中的 truth。这样存在两套 truth 来源，容易出现重复列、口径不一致和泄漏误用。

建议：

- 回测输入改为 truth-free `predictions.csv`。
- 唯一 truth 来源固定为 features/label 表。
- merge 后断言无重复 truth 列。

### P1-002：月度收益统计口径可能偏差

参考位置：

- `skills/a-share-kline-return-modeling/scripts/14_backtest_portfolio_curve.py:141`
- `skills/a-share-kline-return-modeling/scripts/14_backtest_portfolio_curve.py:145`
- `skills/a-share-kline-return-modeling/scripts/22_backtest_final_signals.py:52`

问题：

`summarize_monthly()` 用当月第一条 curve 记录作为月初权益，而不是上月末或当月首日前权益。若当月第一天已发生入场或回款，月收益会被扭曲。

建议：

- 构造完整交易日 equity 序列。
- 月收益统一使用 `month_end / previous_month_end - 1`。
- 首月使用初始资金作为基准。

### P1-003：最终信号回测硬编码 TopN=3

参考位置：

- `skills/a-share-kline-return-modeling/scripts/22_backtest_final_signals.py:111`

问题：

`22_backtest_final_signals.py` 调用 `backtest.build_ledger(signals, truth, top_n=3, ...)`，忽略实际信号文件每日 picks 数，也没有 `--top-n` 参数。若后续 M5 策略不是固定 3 只，仓位和收益会错。

建议：

- 从 `signals.groupby(trade_date).size()` 推导每日数量。
- 或增加 `--top-n` 参数并断言信号文件每日 pick 数匹配。
- 对动态 Top1/Top2/Top3 和仓位调节策略分别补测试。

### P1-004：top30/top50 二分类缺少单类别保护

参考位置：

- `skills/a-share-kline-return-modeling/scripts/01_train_stock_rank_model.py:173`
- `skills/a-share-kline-return-modeling/scripts/01_train_stock_rank_model.py:180`
- `skills/a-share-kline-return-modeling/scripts/01_train_stock_rank_model.py:192`

问题：

`top30_classifier` / `top50_classifier` 直接 `fit`，只有百分位分类器做了 `target.nunique()` 检查。极端窗口或过滤后只有单类时，训练可能报错或产生不可用模型。

建议：

- 统一封装 `validate_binary_target()`。
- 不足两类时跳过该 anchor，并记录 diagnostics。
- walk-forward 报告中显式记录跳过原因。

### P2-001：编号脚本堆叠，重复严重

参考位置：

- `skills/a-share-kline-return-modeling/scripts/01_train_stock_rank_model.py:13`
- `skills/a-share-kline-return-modeling/scripts/08_evaluate_m3a_recall_experiments.py:18`
- `skills/a-share-kline-return-modeling/scripts/14_backtest_portfolio_curve.py:12`
- `skills/a-share-kline-return-modeling/scripts/21_generate_final_signals.py:12`

问题：

当前 `scripts/` 至少 22 个编号脚本，AST 扫描发现重复函数较多：

```text
load_candidates：重复 5 次
load_market：重复 5 次
summarize_monthly：重复 7 次
write_report：重复 15 次
默认路径常量：散落 47 处
```

建议：

抽出公共包：

```text
src/a_share_kline/paths.py
src/a_share_kline/schema.py
src/a_share_kline/features.py
src/a_share_kline/training.py
src/a_share_kline/backtest.py
src/a_share_kline/reports.py
```

脚本只保留 CLI 编排。

### P2-002：路径策略不一致，脚本对运行目录敏感

参考位置：

- `skills/a-share-kline-return-modeling/scripts/05_run_walk_forward.py:15`
- `skills/a-share-kline-return-modeling/scripts/01_train_stock_rank_model.py:13`
- `skills/a-share-kline-return-modeling/scripts/00_build_features.py:441`

问题：

部分脚本使用 `ROOT = Path(__file__).resolve().parents[3]`，部分使用相对路径 `Path("skills/...")`。从仓库根目录外运行时容易失败或写错位置。

建议：

- 统一 repo root 发现逻辑。
- 默认路径全部基于 root resolve。
- CLI 保留显式路径覆盖。

### P2-003：错误处理过宽，可能掩盖真实配置/依赖问题

参考位置：

- `skills/a-share-kline-return-modeling/scripts/00_build_features.py:75`
- `skills/a-share-kline-return-modeling/scripts/00_build_features.py:82`
- `skills/a-share-kline-return-modeling/scripts/01_train_stock_rank_model.py:91`
- `skills/a-share-kline-return-modeling/scripts/01_train_stock_rank_model.py:105`

问题：

`load_config()` 对 YAML 解析 `except Exception: pass` 后进入简易 parser，可能把格式错误当正常配置处理。模型工厂对 LightGBM 的所有异常都 fallback 到 sklearn，可能掩盖版本或参数错误。

建议：

- 只捕获 `ImportError` / `ModuleNotFoundError` 等明确异常。
- 配置解析失败应 fail fast，并打印文件路径和行号。
- 模型 fallback 要在日志/报告中明确记录。

### P2-004：测试与复现基础不足

参考位置：

- `skills/a-share-kline-return-modeling/tests/test_build_features_contract.py:12`
- `skills/a-share-kline-return-modeling/tests/test_build_features_contract.py:22`

问题：

未发现标准依赖声明文件，例如：

```text
requirements.txt
pyproject.toml
environment.yml
```

唯一测试依赖已生成的大 CSV 和 pandas，不是小样本可复现测试。`pytest` 当前因缺少 `pandas` 失败。

建议：

- 补依赖声明。
- 增加小 fixture 单元测试。
- 覆盖特征、标签、防泄漏、回测现金流、最终信号 schema。

## 5. 验证结果

### 静态编译

命令：

```bash
python3 -m py_compile skills/a-share-kline-return-modeling/scripts/*.py skills/a-share-kline-return-modeling/tests/*.py
```

结果：通过。

### Pytest

命令：

```bash
pytest -q skills/a-share-kline-return-modeling/tests/test_build_features_contract.py
```

结果：失败。

失败原因：当前 Python 环境缺少 `pandas`。

### 工作区状态

`git status --short` 显示存在大量未提交变更和未跟踪文件，包括新增治理文档、M3/M4/M5 报告、`08`-`22` 系列脚本。RD 未回滚、未修改、未清理这些变更。

## 6. 建议修复顺序

1. 防泄漏收口：拆 signal/truth 数据集，最终信号脚本禁用 truth 输入，所有执行链路加 schema guard。
2. 回测口径修复：回测只读 truth-free predictions，月收益按上月末权益计算，TopN/每日 pick 数不再硬编码。
3. 训练健壮性：二分类单类别保护、输入列存在性检查、diagnostics 标准化。
4. 结构重构：抽公共包，减少编号脚本互相复制；把实验脚本和主线脚本分目录管理。

## 7. 结构清理计划

### 第 1 阶段

建立 `src/a_share_kline/`，先迁移公共能力，不改变行为：

```text
paths
schema
io
backtest_metrics
reports
```

### 第 2 阶段

拆分数据 schema：

```text
market_signal_features
market_truth_labels
stock_signal_features
stock_truth_labels
```

并补 schema 测试。

### 第 3 阶段

统一以下脚本的组合回测、仓位、最终信号逻辑：

```text
14_backtest_portfolio_curve.py
18_backtest_position_sizing_policies.py
21_generate_final_signals.py
22_backtest_final_signals.py
```

### 第 4 阶段

补充工程化基础：

- 依赖文件
- CI 静态检查
- 最小 fixture 测试
- 将 `08`-`20` 标记为 experiments
- 主线入口只保留 README 中认可的少数命令

## 8. 后续 PM 动作建议

- 将 P0/P1 风险同步到 `docs/risk_register.md`。
- 在 `docs/decision_log.md` 中记录“执行链路禁止 truth 输入”的治理决策。
- 若要实施拆分 signal/truth 数据集，先补 CR 或 Gate Review，因为这会影响技术方案、输出结构和标签/判卷口径。
- 将本报告作为后续 M6/M7 工程固化和防泄漏改造的输入。
