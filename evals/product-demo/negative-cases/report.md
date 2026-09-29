# P2 负样本对照报告（改色 / 加字 / 改结构 / 改数量）

时间：2026-09-25T23:17:44+08:00  
可计费模型调用：**0 次**

预期写在 `evals/product-demo/negative-cases/expectations.json`（声明时间 2026-09-25T23:05:00+08:00），本报告只做对照。判定走 `demo/fixture/product_check.py` 的同一段代码。

## 1. 逐例对照

| 例 | 类 | 预期 | 实际 | 实际命中的非通过谓词 | 预期谓词 | 结论 |
|---|---|---|---|---|---|---|
| `neg-01-recolor-upper` | 改色 | not_pass | hard_fail（rc 4） | F2/body_upper_share、F3/body_lower_share、F3/rib_count、F6/bottom_ring_present | rib_count、bottom_ring_present、body_upper_share、body_lower_share | 成立 |
| `neg-02-add-text` | 加字 | not_hard_fail | pass（rc 0） | （无） | （不要求） | 成立 |
| `neg-03-add-handle` | 改结构 | not_pass | hard_fail（rc 4） | F2/body_upper_share、F3/body_lower_share、F6/bottom_spread_share、F7/body_protrusion | body_protrusion | 成立 |
| `neg-04-lidless` | 改结构 | not_pass | hard_fail（rc 4） | F4/lid_share、F5/trim_span_count、F5/trim_share、F5/trim_top_position | trim_span_count | 成立 |
| `neg-05-extra-ribs` | 改数量 | not_pass | hard_fail（rc 4） | F3/rib_count | rib_count | 成立 |
| `neg-06-second-cup` | 改数量 | not_pass | hard_fail（rc 4） | F7/extra_area_share | extra_area_share | 成立 |
| `neg-07-flat-lid` | 改结构 | pass | pass（rc 0） | （无） | （不要求） | 成立 |

## 2. 未变异对照与误报率

| 对照 | 预期 | 实际 | 说明 |
|---|---|---|---|
| `control-A` | not_hard_fail | manual | 未变异对照。A 被判 manual 是预期的真报（实测 4 条筋，与设计 3 条不符），不是误报。 |
| `control-B` | not_hard_fail | pass | 未变异对照。B 机器整体 pass；它在 D0.1 是因人工看出「顶面暗凹像开口」才被排除 —— 那属于机器不覆盖的范围。 |
| `control-C` | not_hard_fail | pass | 未变异对照，也是全部负样本的母本。它必须仍是 pass，否则负样本的「变化」无法归因。 |

误报率 = 对照里被判硬失败的比例 = 0/3。对照被判 `manual` 不计入误报。

## 3. 漏报台账

| 例 | 是漏报吗 | 谁负责 | 为什么 |
|---|---|---|---|
| `neg-02-add-text` | 是（预期内） | 人工档 | 见 `expectations.json` 的 rationale；对应的机器缺口登记在事实卡 `machine_check_gaps` |
| `neg-07-flat-lid` | 是（预期内） | 人工档 | 见 `expectations.json` 的 rationale；对应的机器缺口登记在事实卡 `machine_check_gaps` |

## 4. 这张表不证明什么

- 它不证明「门禁能拦下所有坏图」：只证明这七例改动与三个对照的判定符合事先写下的预期；
- 两个字面缺口是**故意留下并被记账**的：F8 文字（人工档）、F4 阶梯级数与盖顶开口（机器判据只有盖高）。它们由人看、不由机器判 —— 这正是事实卡 `machine_check_gaps` 登记的内容；
- 机器判 `hard_fail` 不总能指出「最初改的是什么」：结构变异会连带打断按颜色分的带。所以报告列出**实际命中的每一条谓词**，而不是只给一个结论；
- 三个对照（n=3）不足以给误报率任何统计意义，它只回答「这一次有没有误伤」。
