# A股5日预测模型 V1 开发报告

报告日期：2026-05-30 GMT+8  
项目路径：`skills/a-share-kline-return-modeling/`  
当前阶段：V1 功能闭环完成，进入工程固化阶段

## 1. 结论摘要

本项目 V1 已完成从数据清洗、特征标签构建、个股模型训练、walk-forward 验证、组合级回测、最终信号生成到契约测试的主流程闭环。

当前状态可以定义为：

```text
V1 功能闭环完成。
防泄漏主链路完成。
一键主流程完成。
后续进入工程固化、结构清理和小样本测试增强阶段。
```

当前默认主线：

```text
模型：top50_classifier
候选池：Top50
最终输出：Top3
执行策略：full_size
候选风险开关：combined_size_v2
```

最新 12 个月验证结果：

```text
验证范围：2025-05 至 2026-04
平均 Top3 5日收益：2.75%
平均 Top30 命中数：0.801 / 3
收益优于随机月份：10 / 12
Top30 命中优于随机月份：10 / 12
full_size 最终资金曲线：2.7561
full_size 最大回撤：-9.91%
```

## 2. 开发目标

V1 的目标不是一次性追求复杂模型，而是先建立一条可信、可复现、可复盘的研究与执行辅助链路：

```text
原始日K + 股票清单
  -> 特征与标签
  -> 个股5日强势模型
  -> Top3 信号评估
  -> 组合级资金曲线
  -> 最终信号文件
  -> 防泄漏与契约测试
```

核心验收原则：

```text
口径正确
无未来泄漏
交易成本可复现
信号可执行
评估链路可靠
模型至少打败简单基准
```

## 3. 已完成交付

### 3.1 数据与标签

已实现：

```text
股票池读取与标准化
日 K 字段标准化
基础技术特征
行业强度特征
市场宽度特征
T+1 open 买入、T+6 open 卖出的 5 日可交易收益
成本、滑点、印花税、过户费扣减
future_5_return_rank
future_5_return_rank_pct
label_top10 / label_top30 / label_top50
label_direction
交易可行性字段
数据质量报告
```

主要输出：

```text
data/clean_stock_features.csv
data/clean_market_features.csv
data/market_signal_features.csv
data/market_truth_labels.csv
outputs/evaluation/data_quality_report.md
```

### 3.2 个股预测模型

当前主模型：

```text
脚本：scripts/01_train_stock_rank_model.py
模式：--model-mode top50_classifier
模型：LightGBMClassifier
目标：label_top50
输出：rank_strength_score
```

设计意图：

```text
第一阶段提高 Top50 候选召回。
第二阶段从候选中选 Top3。
最终 Top3 只要求落入真实 Top30，而不是必须命中真实 Top3。
```

已支持的实验/回退模式：

```text
raw_rank_pct_regression
top30_classifier
weighted_rank_pct_regression
top10pct_classifier
top15pct_classifier
top20pct_classifier
top25pct_classifier
```

### 3.3 Walk-forward 验证

已实现月度滚动验证：

```text
脚本：scripts/05_run_walk_forward.py
默认范围：2025-05 至 2026-04
训练窗口：365 天
训练输出：Top50
评估输出：Top3
```

主要输出：

```text
outputs/evaluation/walk_forward_summary.csv
outputs/evaluation/walk_forward_summary.md
outputs/evaluation/stock_rank_model_metrics.json
```

### 3.4 组合级回测

已实现现金约束组合回测：

```text
脚本：scripts/14_backtest_portfolio_curve.py
每日最多新开 Top3
每日新仓使用 1/5 资金袖套
单日 Top3 等权
总暴露不超过 100%
卖出资金实际退出后复用
```

已修正：

```text
回测输入只读 truth-free predictions.csv
判卷 truth 唯一来源为 clean_stock_features.csv
月度收益使用上月末权益作为基准
每日仓位按实际 pick 数计算
```

### 3.5 信号层

已实现最终信号生成和回测：

```text
脚本：scripts/21_generate_final_signals.py
回测：scripts/22_backtest_final_signals.py
默认策略：full_size
候选策略：combined_size_v2
```

最终信号文件不包含：

```text
future_* / label_* / actual_* / entry_price / exit_price / gross_future_5_return
```

当前主信号文件：

```text
outputs/final_signals/final_signals_full_size_2025-05_2026-04.csv
```

### 3.6 一键主流程

已新增主流程入口：

```text
scripts/23_run_main_pipeline.py
```

完整重跑：

```bash
python3 skills/a-share-kline-return-modeling/scripts/23_run_main_pipeline.py
```

复用已有 walk-forward，仅刷新最终信号和测试：

```bash
python3 skills/a-share-kline-return-modeling/scripts/23_run_main_pipeline.py \
  --skip-build-features \
  --skip-walk-forward \
  --skip-portfolio-backtest
```

主流程摘要：

```text
outputs/evaluation/main_pipeline_summary.md
outputs/evaluation/main_pipeline_summary.json
```

## 4. 最新指标

### 4.1 Walk-forward 汇总

| 指标 | 数值 |
|---|---:|
| 验证月份 | 12 |
| 平均 Top3 5日收益 | 2.75% |
| 平均 Top30 命中数 | 0.801 / 3 |
| 收益优于随机月份 | 10 / 12 |
| Top30 命中优于随机月份 | 10 / 12 |

逐月结果：

| 月份 | 交易日 | Top3收益 | Top30命中 |
|---|---:|---:|---:|
| 2025-05 | 15 | 1.90% | 0.733 / 3 |
| 2025-06 | 20 | 0.57% | 0.500 / 3 |
| 2025-07 | 23 | 0.30% | 0.391 / 3 |
| 2025-08 | 21 | 1.71% | 0.762 / 3 |
| 2025-09 | 22 | -0.48% | 0.364 / 3 |
| 2025-10 | 17 | 0.74% | 0.647 / 3 |
| 2025-11 | 20 | -0.78% | 0.600 / 3 |
| 2025-12 | 23 | 2.29% | 0.652 / 3 |
| 2026-01 | 20 | 3.01% | 0.850 / 3 |
| 2026-02 | 14 | 10.07% | 1.500 / 3 |
| 2026-03 | 22 | 2.08% | 1.136 / 3 |
| 2026-04 | 21 | 11.58% | 1.476 / 3 |

说明：

```text
2025-05 因 label_top50 在早期小股票池窗口出现单类别，4 个交易日被跳过。
这是为了避免退化二分类模型输出不可用概率。
```

### 4.2 最终信号回测

| 策略 | 交易数 | 信号日 | 平均仓位系数 | 最终资金曲线 | 累计收益 | 最大回撤 | 正收益月份 | 平均暴露 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| full_size | 714 | 238 | 1.0000 | 2.7561 | 175.61% | -9.91% | 84.62% | 96.31% |
| combined_size_v2 | 714 | 238 | 0.9340 | 2.6792 | 167.92% | -9.75% | 76.92% | 90.88% |

当前结论：

```text
修正 market_10pct_density 可知性滞后后，combined_size_v2 不再优于 full_size。
full_size 恢复为默认执行基准。
combined_size_v2 保留为候选风险开关，只作为后续对照。
```

## 5. 防泄漏与工程修复

2026-05-30 已根据结构性代码审查完成 P0/P1 修复。

关键修复：

```text
市场 signal/truth 拆分
最终信号禁止 truth 输入
预测输入、市场输入、最终输出加入 schema guard
组合回测改读 truth-free predictions.csv
月度收益口径修正为 previous month end
最终信号回测按每日实际 pick 数计仓
top30/top50 二分类加入单类别保护
YAML 配置解析和模型 fallback 异常捕获收窄
```

对应报告：

```text
docs/code_reviews/2026-05-30-structural-code-review.md
docs/code_reviews/2026-05-30-structural-code-review-fix-report.md
```

## 6. 测试与验证

已通过：

```bash
python3 -m py_compile skills/a-share-kline-return-modeling/scripts/*.py skills/a-share-kline-return-modeling/tests/*.py
python3 skills/a-share-kline-return-modeling/tests/test_build_features_contract.py
python3 skills/a-share-kline-return-modeling/tests/test_final_signal_contract.py
```

测试覆盖：

```text
5日交易日窗口口径
成本扣减计算
rank_pct 方向
模型特征无 future/label 泄漏
最终信号字段 truth-free
最终信号回测 smoke
max_exposure <= 100%
```

## 7. 当前风险

### 7.1 样本和市场阶段风险

当前主验证窗口为 2025-05 至 2026-04，虽然已有 12 个月 walk-forward，但仍属于有限窗口。2026-02 至 2026-04 贡献较高，后续应继续扩展历史区间和滚动外推验证。

### 7.2 特征与行业数据风险

当前行业强度主要来自股票清单中的行业分类和横截面日 K 聚合，尚未接入更完整的历史行业资金流、板块指数或行业涨跌幅序列。行业轮动识别仍有增强空间。

### 7.3 工程结构风险

当前 `scripts/` 中脚本数量较多，存在公共函数重复和路径风格不一致问题。虽然主流程已能跑通，但长期维护需要抽公共包。

待处理：

```text
P2-001：抽 src/a_share_kline 公共包
P2-002：统一 repo root 和默认路径策略
P2-004：增加小样本 fixture 测试和 CI
```

### 7.4 交易实盘风险

当前模型输出用于研究和交易纪律辅助，不是收益保证。真实交易仍需考虑：

```text
实时数据延迟
开盘成交滑点
涨跌停不可成交
个股停牌
交易容量
人工风控
黑天鹅事件
```

## 8. 后续计划

### M8 工程固化

优先级：

```text
1. 抽公共包 src/a_share_kline/
2. 统一路径和配置读取
3. 补小样本 fixture 测试
4. 整理主线脚本与实验脚本边界
5. 更新报告索引和 README，保持文档与真实主线一致
```

### 模型增强方向

后续可探索：

```text
扩展行业强度历史特征
构建行业轮动特征
增加市场 regime 特征
扩大历史回测区间
增加分市场环境的命中率分析
重新评估风险开关和仓位策略
```

### 日常使用流程

建议当前使用：

```bash
python3 skills/a-share-kline-return-modeling/scripts/23_run_main_pipeline.py \
  --skip-build-features \
  --skip-walk-forward \
  --skip-portfolio-backtest
```

完整复盘或大版本更新时使用：

```bash
python3 skills/a-share-kline-return-modeling/scripts/23_run_main_pipeline.py
```

## 9. 最终判断

V1 已达到“功能闭环完成”的标准：

```text
能从数据生成特征和标签。
能训练当前主模型。
能做 12 个月 walk-forward。
能生成 truth-free 最终信号。
能完成组合级回测。
能通过基础契约测试。
能用一键脚本复现主流程。
```

但 V1 仍处于工程固化阶段，还不是完全产品化系统。下一阶段重点不是继续盲目调参，而是把当前有效链路变得更稳、更清晰、更容易长期维护。
