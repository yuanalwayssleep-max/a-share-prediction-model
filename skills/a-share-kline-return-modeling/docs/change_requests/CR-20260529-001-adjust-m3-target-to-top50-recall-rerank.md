# CR-20260529-001 调整 M3 目标为 Top50 召回 + 二次排序

状态：已实施
提出日期：2026-05-29
提出人：Codex
影响阶段：M3 个股强势排序模型、M4 Walk-forward 验证

## 变更摘要

将 M3 从“模型直接输出 Top3”调整为“模型先召回 Top50，再在 Top50 候选池内二次排序选 Top3”。

## 背景

按原 M3 目标执行后，模型直接按 `rank_strength_score` 取 Top3 的效果未达到验收标准。

12 个月 walk-forward 清理标签泄漏后的结果显示：

```text
raw model Top3 平均收益：约 1.28%
raw model Top3 平均 Top30 命中：约 0.60 / 3
```

进一步失败归因显示，模型 Top50 候选池中包含较多真实 Top30，但这些强票经常没有被排进 raw model Top3。

示例：

```text
2025-08：Top50 候选池平均真实 Top30 命中约 6.86 个，但 raw Top3 命中约 0.19 / 3
2025-09：Top50 候选池平均真实 Top30 命中约 8.55 个，但 raw Top3 命中约 0.32 / 3
2026-04：Top50 候选池平均真实 Top30 命中约 11.24 个，但 raw Top3 命中约 1.24 / 3
```

这说明当前模型更适合作为候选池召回器，而不是最终 Top3 排序器。

## 当前方案

M3 当前目标：

```text
训练个股强势排序模型
直接根据 rank_strength_score 输出 Top3
以 Top3 收益和 Top30 命中作为主要验收
```

## 建议变更

M3 拆成两个子目标：

```text
M3-A：候选池召回
  使用模型输出 Top50 候选池
  验收重点：Top50 中真实 Top30 的召回数量

M3-B：候选池内二次排序
  在 Top50 内使用二次排序规则或二阶段模型选 Top3
  候选方案：ret_20、blend_model_low_overheat、blend_model_amount
  验收重点：最终 Top3 收益、Top30 命中、月度稳定性
```

第一版建议先固化为规则二次排序，不立即引入新模型：

```text
候选池：model_rank Top50
二次排序候选一：ret_20
二次排序候选二：blend_model_low_overheat
二次排序候选三：blend_model_amount
```

## 影响范围

可能影响：

```text
docs/development_milestones.md
docs/implementation_plan.md
scripts/01_train_stock_rank_model.py
scripts/03_generate_final_signals.py
scripts/05_run_walk_forward.py
scripts/07_evaluate_rerank_strategies.py
outputs/evaluation/walk_forward_summary.csv
```

不影响：

```text
标签定义
T+1 open -> T+6 open 主回测口径
成本和滑点口径
未来泄漏黑名单
```

## 预期收益

```text
保留模型的候选池召回能力
避免 raw model score 顶部排序不稳定的问题
提高最终 Top3 的 Top30 命中
提高弱月份中从候选池挖出真实强票的能力
```

当前实验结果显示，在模型候选池内二次排序：

```text
ret_20 二次排序：
  12个月平均收益约 1.52%
  平均 Top30 命中约 0.74 / 3

raw model score：
  12个月平均收益约 1.28%
  平均 Top30 命中约 0.60 / 3
```

## 风险

```text
ret_20 本质是动量规则，可能在风格切换时失效
二次排序可能降低模型本身解释性
候选池扩大到 Top50 后，若二次排序不稳，噪声也会增加
如果后续在测试集上反复挑二次排序规则，可能过拟合
```

## 验收标准

审批通过后，M3 新验收标准建议为：

```text
M3-A 候选池召回：
  Top50 候选池平均真实 Top30 命中显著高于随机 Top50
  低命中月份必须可解释

M3-B 二次排序：
  最终 Top3 平均收益 > 随机 Top3
  最终 Top3 平均收益 >= 最强简单基准之一
  最终 Top3 平均 Top30 命中 > raw model Top3
  至少 2/3 月份收益优于随机
  不能只靠单月极端收益贡献
```

## 审批记录

审批结论：已批准，附带约束。
审批时间：2026-05-29 21:59 GMT+8
审批人：boss
审批意见：

```text
同意将 M3 调整为 Top50 候选池召回 + 候选池内二次排序选 Top3。
第一版仅批准规则二次排序方案：ret_20、blend_model_low_overheat、blend_model_amount。
必须保留 raw model Top3 基线，不得修改标签、交易口径、成本滑点、未来泄漏规则或 walk-forward 切分。
如后续引入二阶段模型，需另提变更请求。
```

## 实施记录

实施时间：2026-05-29 GMT+8
实施人：Codex

实施内容：

```text
已将 M3 文档目标同步为 Top50 候选池召回 + 候选池内规则二次排序 Top3。
已保留 raw model score Top3 作为 walk-forward 与 rerank 评估基线。
已将 05_run_walk_forward.py 的汇总扩展为 raw 基线 + 已批准二次排序策略。
已将 07_evaluate_rerank_strategies.py 限定为 raw model_score、ret_20、blend_model_low_overheat、blend_model_amount。
```

验证结果：

```text
python3 -m py_compile 05_run_walk_forward.py 07_evaluate_rerank_strategies.py 00_build_features.py 01_train_stock_rank_model.py 04_evaluate_top3.py：通过
python3 skills/a-share-kline-return-modeling/tests/test_build_features_contract.py：通过
python3 skills/a-share-kline-return-modeling/scripts/07_evaluate_rerank_strategies.py --start-period 2025-05 --end-period 2026-04：通过
```
