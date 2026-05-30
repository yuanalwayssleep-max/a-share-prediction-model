# CR-20260529-002 开展 M3-A 召回导向训练对照实验

状态：已实施
提出日期：2026-05-29
提出人：Codex
影响阶段：M3-A 候选池召回、M4 Walk-forward 验证

## 变更摘要

开展 M3-A 召回导向训练对照实验，验证 Top30 / Top50 召回导向目标是否能提升 Top50 候选池对真实 Top30 的覆盖。

第一版不替换当前 raw rank_pct 回归主模型，不改变最终信号链路，不修改标签定义、交易口径、成本滑点、未来泄漏规则和 walk-forward 切分。

## 背景

CR-20260529-001 已将 M3 调整为：

```text
M3-A：模型先召回 Top50 候选池
M3-B：在 Top50 候选池内二次排序选 Top3
```

但当前 M3-A 诊断显示，候选池召回能力不足：

```text
Top50 平均每天命中真实 Top30：7.36 / 30
随机 Top50 期望命中真实 Top30：6.43 / 30
召回提升约：1.14x
```

进一步归因显示，很多未被 Top50 召回的真实 Top30 并不是弱票，反而在以下特征上更强：

```text
ret_5_xrank
ret_20_xrank
range_pos_20_xrank
industry_strength_score
turnover_pct_xrank
amount_ratio_20
```

这说明现有特征已经包含一部分可用信号，但当前连续 rank_pct 回归目标没有把这些强势样本稳定推入 Top50。

## 当前方案

当前 `01_train_stock_rank_model.py` 使用：

```text
模型：LightGBMRegressor
目标：future_5_return_rank_pct
输出：rank_strength_score
候选池：按 rank_strength_score 取 Top50
```

当前训练目标偏“全横截面连续拟合”，模型会试图解释所有股票的相对分位，而不是专门优化“真实 Top30 是否进入候选池”。

这会带来两个问题：

```text
1. 模型可能把中位区间拟合得更平滑，但牺牲顶部召回。
2. 真实 Top30 里短期启动、行业扩散、量价快速增强的样本没有被足够加权。
```

## 建议变更

M3-A 不改变主模型，只新增召回导向对照实验。第一轮只允许以下三类实验，不引入更复杂二阶段模型：

```text
方案 A：Top30 二分类召回模型
  模型：LightGBMClassifier
  目标：label_top30
  输出：top30_recall_score
  候选池：按 top30_recall_score 取 Top50

方案 B：Top50 二分类召回模型
  模型：LightGBMClassifier
  目标：label_top50
  输出：top50_recall_score
  候选池：按 top50_recall_score 取 Top50

方案 C：加权 rank_pct 回归模型
  模型：LightGBMRegressor
  目标：future_5_return_rank_pct
  样本权重：
    label_top10 权重最高
    label_top30 次高
    label_top50 轻微加权
    其他样本正常权重
  输出：weighted_rank_strength_score
  候选池：按 weighted_rank_strength_score 取 Top50
```

第一版只做 walk-forward 对照评估，不替换主模型，不改变最终信号链路。输出必须同时保留：

```text
raw rank_pct 回归基线
Top30 分类召回模型
Top50 分类召回模型
加权 rank_pct 回归模型
```

M3-B 暂不变，仍只使用 CR-20260529-001 已批准的规则二次排序：

```text
ret_20
blend_model_low_overheat
blend_model_amount
```

## 不变项

本变更不允许修改：

```text
标签定义
T+1 open -> T+6 open 主交易口径
成本和滑点口径
未来泄漏黑名单
walk-forward 切分
Top50 候选池规模
最终 Top3 评估口径
```

本变更不引入：

```text
二阶段学习排序模型
stacking
自动调参
测试集反复调参
外部新增数据源
分钟线数据
```

## 影响范围

可能影响：

```text
docs/development_milestones.md
docs/implementation_plan.md
scripts/01_train_stock_rank_model.py
scripts/05_run_walk_forward.py
scripts/06_analyze_rank_failures.py
outputs/evaluation/m3_recall_model_compare.csv
outputs/evaluation/m3_recall_model_compare.md
```

不影响：

```text
scripts/00_build_features.py 的标签口径
scripts/04_evaluate_top3.py 的收益和命中评估口径
scripts/07_evaluate_rerank_strategies.py 的已批准二次排序规则
```

## 预期收益

```text
让模型训练目标更贴近第一阶段业务目标：Top50 候选池召回真实 Top30。
减少连续回归目标对中位股票的过度关注。
提高真实 Top30 进入 Top50 的数量。
为后续 Top3 二次排序提供更好的候选池。
```

目标不是立即让最终 Top3 达标，而是先把 M3-A 召回端做强。

## 风险

```text
Top30 分类正样本较少，可能导致概率不稳定。
Top50 分类可能召回更宽，但排序质量下降。
样本加权可能牺牲平均收益或增加过热票比例。
如果直接按 12 个月结果挑最优方案，存在验证集过拟合风险。
分类模型输出概率可能需要校准，否则不同月份分数不可比。
```

控制措施：

```text
所有方案必须和 raw rank_pct 回归基线同窗口对照。
只看 M3-A Top50 召回是否提升，不允许用单月最终 Top3 收益反向挑模型。
输出低召回月份和过热/行业集中归因。
若后续要正式替换主模型，需另行提交“替换主模型/升级 M3-A 主线”的变更请求。
```

## 验收标准

补充后若再审通过，第一轮对照实验验收标准为：

```text
生成 12 个月 walk-forward 对照报告。
至少一个召回导向方案的 Top50 平均真实 Top30 命中高于 raw rank_pct 回归基线。
至少一个召回导向方案的 Top50 召回提升不只来自单月。
召回提升月份数量 >= 8 / 12。
不能显著增加低流动性、过热、近涨停样本比例。
必须保留 raw rank_pct 回归基线。
必须继续输出 M3-B 已批准规则二次排序结果。
```

建议阶段性目标：

```text
Top50 平均真实 Top30 命中：从 7.36 / 30 提升到 9.00 / 30 以上。
中期目标：10.00-12.00 / 30。
```

## 审批记录

审批结论：已批准，附带约束。
审批时间：2026-05-29 22:49 GMT+8
审批人：boss
产品经理评审人：小庄

审批意见：

```text
同意开展 M3-A 召回导向训练对照实验。

批准范围：
1. 仅批准进行 M3-A Top50 候选池召回导向对照实验。
2. 第一轮允许对照 raw rank_pct 回归基线、Top30 分类召回、Top50 分类召回、加权 rank_pct 回归。
3. 实验输出必须同时保留 raw rank_pct 回归基线，不得覆盖或删除现有主模型结果。
4. 第一轮评审重点只看 Top50 候选池对真实 Top30 的召回改善，不允许用最终 Top3 收益反向挑模型。
5. M3-B 保持 CR-20260529-001 已批准范围，仅允许 ret_20、blend_model_low_overheat、blend_model_amount 三个规则二次排序方案。

禁止事项：
1. 不得替换当前 raw rank_pct 回归主模型。
2. 不得改变最终信号链路。
3. 不得修改标签定义、交易口径、成本滑点、未来泄漏黑名单、walk-forward 切分、Top50 候选池规模。
4. 不得引入二阶段学习排序模型、stacking、自动调参、外部新增数据源或分钟线数据。
5. 不得根据 12 个月 walk-forward 最终 Top3 收益反向选择模型，避免验证集过拟合。

后续要求：
若召回导向方案通过对照实验，并希望正式替换 M3-A 主模型，必须另行提交“替换主模型/升级 M3-A 主线”的变更请求。
```

## 补充记录

补充时间：2026-05-29 GMT+8
补充人：Codex

根据审批意见，已将本 CR 的目标从：

```text
调整 M3-A 为 Top30 召回导向训练
```

收窄为：

```text
开展 M3-A 召回导向训练对照实验，不替换主模型，不改变最终信号链路。
```

补充后的执行边界：

```text
只做 M3-A Top50 召回对照实验。
不替换当前 raw rank_pct 回归主模型。
不使用最终 Top3 收益反向挑模型。
不修改 M3-B 已批准二次排序范围。
若实验有效，另提正式替换主模型 CR。
```

流程修订记录：

```text
2026-05-29：根据用户要求，已从 change_request_process.md 移除“commit + push 才正式进入审批流程”的强制要求。
本 CR 后续再审不再受 GitHub 同步条件限制。
```

## 实施记录

实施时间：2026-05-29 GMT+8
实施人：Codex

实施内容：

```text
新增独立实验脚本 scripts/08_evaluate_m3a_recall_experiments.py。
该脚本只输出 M3-A Top50 召回对照实验结果。
未修改 01_train_stock_rank_model.py 主模型训练流程。
未覆盖 outputs/stock_rank_predictions 下的现有主模型预测结果。
未改变最终信号链路。
未修改标签定义、交易口径、成本滑点、未来泄漏黑名单、walk-forward 切分、Top50 候选池规模。
```

实验范围：

```text
时间：2025-05 至 2026-04
候选池规模：Top50
训练窗口：过去 365 自然日
训练防泄漏规则：exit_trade_date < anchor_date
对照方案：
  raw_rank_pct_regression
  top30_classifier
  top50_classifier
  weighted_rank_pct_regression
```

输出文件：

```text
outputs/evaluation/m3_recall_model_compare.md
outputs/evaluation/m3_recall_model_compare.csv
outputs/evaluation/m3_recall_model_monthly_compare.csv
outputs/evaluation/m3_recall_model_daily.csv
outputs/evaluation/m3_recall_model_predictions.csv
outputs/evaluation/m3_recall_model_diagnostics.csv
```

验证命令：

```text
python3 -m py_compile skills/a-share-kline-return-modeling/scripts/08_evaluate_m3a_recall_experiments.py skills/a-share-kline-return-modeling/scripts/01_train_stock_rank_model.py：通过
python3 skills/a-share-kline-return-modeling/tests/test_build_features_contract.py：通过
python3 skills/a-share-kline-return-modeling/scripts/08_evaluate_m3a_recall_experiments.py --start-month 2025-05 --end-month 2026-04：通过
```

核心结果：

```text
raw_rank_pct_regression：
  Top50 平均真实 Top30 命中：7.51 / 30
  月份数：12

top30_classifier：
  Top50 平均真实 Top30 命中：8.99 / 30
  相对 raw 提升：+1.47 / 30
  召回优于 raw 的月份：9 / 12
  近涨停比例相对 raw：+1.69pct
  过热比例相对 raw：+1.58pct

top50_classifier：
  Top50 平均真实 Top30 命中：8.93 / 30
  相对 raw 提升：+1.41 / 30
  召回优于 raw 的月份：9 / 12
  近涨停比例相对 raw：+1.41pct
  过热比例相对 raw：+1.53pct

weighted_rank_pct_regression：
  Top50 平均真实 Top30 命中：8.33 / 30
  相对 raw 提升：+0.81 / 30
  召回优于 raw 的月份：8 / 12
  近涨停比例相对 raw：+0.56pct
  过热比例相对 raw：+0.49pct
```

阶段判断：

```text
对照实验完成。
召回导向模型显著提高 Top50 对真实 Top30 的覆盖。
top30_classifier 与 top50_classifier 接近 9.00 / 30 阶段目标，但伴随近涨停和过热样本比例上升。
weighted_rank_pct_regression 提升较温和，但风险暴露增加更小。
本 CR 不批准替换主模型，因此当前不替换 raw rank_pct 回归主模型。
如需正式升级 M3-A 主线，必须另提“替换主模型/升级 M3-A 主线”变更请求。
```
