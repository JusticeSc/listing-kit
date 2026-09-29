# D1.P3 后半链合同验证（PC-08 – PC-13）

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY
> 任务：D1.P3（计划 v1.7 §6.10.1）
> 时间：2026-09-26T11:26:16+08:00
> 计划权威：`docs/product-demo-goal-and-implementation-plan.md` v1.7
> 状态权威：`_working/amz-listing-kit-product-demo/state.md`

本报告只记录 D1.P3 实际做了什么、跑出了什么、以及这些证据不能证明什么。
付费调用：**0 次**。冻结候选、账本、参考包一个字节未动（§6 有核对读数）。

## 1. 这个任务要解决什么

D1.P2 让前半链的合同能被证伪；后半链此前只有散文：没人证明「回来的东西能不能用、
谁给的结论、判错了怎么改、最后交出去的文件是不是同一份」这几条真的能实现，也没人证明
它们真的能被违反。

D1.P3 就是补这个洞：给 PC-08–PC-13 一份真能跑的实现（`demo/core/back_chain.py`）、
一条黄金链和 17 条反例，再用变异测试证明反例真的有牙。

**它同时给 D1.4 的事故补上了那道缺失的步骤**：`cylinder-v1` 在场景候选上必须返回
「不适用」并交回路由，而不是把不适用的尺子读成失败。

## 2. 实际产物

| 文件 | 作用 |
|---|---|
| `demo/core/back_chain.py` | PC-08–PC-13 实现：技术检查、事实路由、审美审核、返工路由、选择与确定性合成、最终复检与导出 |
| `demo/core/run_back_contracts.py` | 契约测试：黄金链 + 17 条反例 + 8 项变异测试 |
| `demo/core/human_fact_review.aster-01.json` | D1.5 的人工事实裁决**转成数据**：32 条 {事实, 候选} 记录 |
| `demo/core/human_visual_review.aster-01.json` | 人工视觉裁决（keep/redo/reject + 封闭理由集），不含任何总分 |
| `demo/core/verifier_plan.aster-01.json` | 拟定的事实验证路由（每条事实：规则 → 模型 → 人工），标注为 proposed |
| `evals/product-demo/d1-p3/back-contracts.json` | 本次运行的机器可读报告 |

## 3. PC-09 的三步顺序，以及它在四张候选上的真实读数

按合同，PC-09 必须先判**适用性**、再选**责任者**、最后**合并**。第一步的判据是
「纯背景列里被判成主体的像素占比」——它不是新发明的规则，而是把 D1.4 §3.1 那次对照
实验变成可执行的前置条件（探针复用 `measure_cylinder.build_mask`，不是第二份掩膜）。

| 图 | 左 18% 纯背景列的主体像素占比 |
|---|---|
| 夹具正面图 01-front-full | 0.0 |
| F-01 | 0.2063 |
| F-02 | 0.3921 |
| F-03 | 0.1584 |
| F-04 | 0.4163 |

阈值敏感性（阈值在 0.005–0.10 之间任取，分类结果都一样）：

| 阈值 | 夹具正面图 01-front-full | F-01 | F-02 | F-03 | F-04 |
|---|---|---|---|---|---|---|
| 0.005 | 适用 | 不适用 | 不适用 | 不适用 | 不适用 |
| 0.02 | 适用 | 不适用 | 不适用 | 不适用 | 不适用 |
| 0.05 | 适用 | 不适用 | 不适用 | 不适用 | 不适用 |
| 0.1 | 适用 | 不适用 | 不适用 | 不适用 | 不适用 |

**结论**：`cylinder-v1` 在棚拍夹具上适用、在四张场景候选上都不适用，两者相差两个数量级，
所以这个判据不是靠微调阈值制造出来的结论。

四张候选的路由结果（`route_summary`）：

| 候选 | 候选文件哈希 | 责任分布 |
|---|---|---|
| F-01 | 95db1ad085d0… | {"human": 8} |
| F-02 | 1cdf146ba17c… | {"human": 8} |
| F-03 | b09fd5a9e5af… | {"human": 8} |
| F-04 | 80ec57b21bdb… | {"human": 8} |

也就是说：**这一轮的事实结论全部由显式人工确认承担**；规则路线因前提不成立而未生效，
模型路线因本任务离线而未运行。两者都如实记在每条事实的 `trail` 里，没有一条被写成
「机器判过」。把它们真正建立起来是 D1.R1–D1.R3 的工作，本任务不预先认领。

## 4. 黄金链结果（离线 · 零付费调用）

| 环节 | 结果 | 关键证据 |
|---|---|---|
| PC-08 技术检查 | 四张全部 accepted | 解码/边长≥1000/1:1/≤10MB 来自 `config/slots.yaml`；中间候选不判导出格式 |
| PC-09 事实路由 | 四张全部 accepted | 每条事实 8 条；`cylinder-v1` 记 not_applicable；模型记 not_run；人工逐条签字 |
| PC-10 审美审核 | accepted | 4 个候选 keep + 封闭理由；声明不生成总分 |
| PC-11 返工路由 | accepted | 原因 `background_clutter` → `scene_composition`；新 PromptVersion 保留父版本与事实锁；S1/S3 的候选哈希与提交数不变 |
| PC-12 选择与合成 | accepted | 选择 F-03；无文案 → 恒等合成（输出与候选逐字节相同） |
| PC-13 最终复检与导出 | accepted | 对最终 JPEG 重跑检查；导出 1 个文件；换目录核验 rc=0 |

**四候选逐一走完整后半链**（不是只看技术检查与事实路由）：

| 候选 | PC-09 事实 | PC-12 选择 | PC-12 合成 | PC-13 导出 | 换目录核验 rc |
|---|---|---|---|---|---|
| F-01 | accepted | accepted | accepted | accepted | 0 |
| F-02 | accepted | accepted | accepted | accepted | 0 |
| F-03 | accepted | accepted | accepted | accepted | 0 |
| F-04 | accepted | accepted | accepted | accepted | 0 |

四张都走通了「事实 → 选择 → 恒等合成 → 最终复检 → 导出 → 换目录核验」，
而且账本哈希在整轮里没有变化（§7）：**没有任何一步偷偷产生付费动作**。

工作目录全部在临时目录里，报告只记录哈希与结论。

## 5. 十八条用例

| 代号 | 注入的缺陷 | 期望 | 实际 | 结论 |
|---|---|---|---|---|
| B0 | 黄金后半链（PC-08…PC-13） | accepted | accepted | 一致 |
| B1 | 场景候选上 cylinder-v1 必须判不适用而非失败 | accepted | accepted | 一致 |
| B2 | 缺人工签字的事实保持未决并阻断选择 | needs_human | needs_human | 一致 |
| B3 | 人工标 unknown 的事实不得被当成通过 | needs_human | needs_human | 一致 |
| B4 | 人工判 fail 的事实让候选不可用 | business_reject | business_reject | 一致 |
| B5 | 审美 keep 不能覆盖事实 fail | business_reject | business_reject | 一致 |
| B6 | 人工判 redo 的候选不可选 | business_reject | business_reject | 一致 |
| B7 | 归不了类的返工原因交人工，不自动重跑 | needs_human | needs_human | 一致 |
| B8 | 单图返工不动其它 Shot（提交数与哈希都不变） | accepted | accepted | 一致 |
| B9 | 同一张图已有选择时不许后写覆盖 | business_reject | business_reject | 一致 |
| B10 | 排版溢出必须判失败且不产出文件 | technical_fail | technical_fail | 一致 |
| B11 | 字体缺失必须判失败，不自动换字体 | technical_fail | technical_fail | 一致 |
| B12 | 最终文件不合格时不发布该版本 | technical_fail | technical_fail | 一致 |
| B13 | 计划里的图没有全部选中时不许导出 | business_reject | business_reject | 一致 |
| B14 | 导出包被改写时换目录核验必须报红 | accepted | accepted | 一致 |
| B15 | 重导创建新版本且不覆盖旧包 | accepted | accepted | 一致 |
| B16 | 规则缺参数时判 unknown，不判失败 | unknown | unknown | 一致 |
| B17 | 实现不许自造合同没声明的状态 | accepted | accepted | 一致 |

## 6. 变异测试：8/8 项被反例抓住

| 变异 | 削弱了什么 | 必须变红的用例 |
|---|---|---|
| M1 | 停掉适用性前置（假装前提永远成立） | B1 |
| M2 | 把未决事实当成通过 | B2、B3 |
| M3 | 停掉「事实没过不可选」 | B4、B5 |
| M4 | 停掉「审美结论必须 keep」 | B6 |
| M5 | 停掉返工隔离记录 | B8 |
| M6 | 停掉最终文件复检（沿用中间候选结论） | B12 |
| M7 | 停掉排版溢出检测 | B10 |
| M8 | 停掉「重导创建新包」（原地覆盖） | B15 |

第一次跑变异测试时有三项「没被抓住」，其中两项是**测试框架自己的缺陷**：用例抛异常时
记录的是函数名而不是用例代号，于是「异常」被读成了「仍然是绿的」。已修正，并且让 M1/M8
的削弱版保持同样的数据结构，使变红来自断言而不是异常。这条一并记下：**反例没红，先怀疑
测试框架，再怀疑实现。**

## 7. 冻结证据完整性核对（本次运行前后）

| 检查 | 读数 |
|---|---|
| 四候选文件哈希 vs D1.4 manifest | 全部一致（F-01…F-04） |
| 账本 | `ledger.jsonl` sha256 `fc80d815be501600…`；4 条记录；预算 4/8 |
| 首轮目录里最新的文件 | `plan.json` · mtime 2026-09-26 11:04（早于本任务） |
| 参考包三个视图 | sha256 与 manifest 一致（未重生成） |

## 8. 本文件不证明什么

- 不证明 G1 通过：G1 的裁决属于 D1.R4；本任务没有关闭它。
- 不证明四张候选的 F1–F8 由**自动**路线判过：它们由显式人工确认承担。
- 不证明 `cylinder-v1` 不能修：本任务只证明它当前的前提在场景输出上不成立。
- 不证明模型路线可用：本轮它根本没有运行。
- 不证明需要多张图的产品流程已经能跑完整：冻结批次只覆盖 S2 一张图的候选，
  B13 正是「计划里的图没选全就不许导出」的反例。
- 不证明跨商品通用：那属于 D1.P4。
- 不证明 Amazon 实际审核通过：技术规则的来源是 `config/slots.yaml`，不是平台官方复核。

## 9. 一处流程自省（本次自己犯规的地方）

2026-09-26 的控制面校准刚立了一条规矩：**改权威文档之前先在工作区外留一份快照**。
本次改 `_working/.../state.md` 与 `README.md` 时没有先留快照 —— 那份规矩是同一轮刚写下的，
执行时漏了。后果很轻（改动可从本文件与本轮工具记录复原），但规则就是这么开始漏的。

处置：改完之后立刻给这一版留了快照，并把哈希写进本节。下次改权威文件前先快照，再动手。

| 文件 | sha256 |
|---|---|
| `docs/product-demo-goal-and-implementation-plan.md` | `be2003caa50e558297a0d2c5ed12e926fa7a83c4a5336b3d2357d52930ee2ae8` |
| `docs/INDEX.md` | `0a366d33f6f450c742de219f725bf389226c4a09ffdf494ab7627fc1d83693c6` |
| `README.md` | `b98d7b349aa025ebe03fd57f65beaeef5712ac14cfebb4122bce29a83d2fa748` |
| `_working/amz-listing-kit-product-demo/state.md` | `005848fb284edcdfb7d9748e89eab80b6ff9138ff230fd0a90b6fe00a4578fd3` |
| `demo/core/back_chain.py` | `54b43f3cb306b689f9b72cb0674d6c291a42d5797351998278e6a1c74c96e194` |
| `demo/core/run_back_contracts.py` | `14b562c15767bb80af64c1aee8aa98ecce543a8d478c21b3176296bcb91b1640` |
| `demo/core/human_fact_review.aster-01.json` | `b0aeb8ad8e4f05f4ff35e644abfbd771a9f96a7eadd1a4c1ed08d18a4cbc203c` |
| `demo/core/human_visual_review.aster-01.json` | `8195ece73bb7cbd707a47e61e92d34e03fa03e5c95b856133332b810cdc8bf47` |
| `demo/core/verifier_plan.aster-01.json` | `b9c82b38b695d0e4f621d202e75395a7b5c604ac621407efcbe667a194c2949e` |
| `evals/product-demo/d1-p3/back-contracts.json` | `7d680da992a172a95df693d40a6125e5e6fbce90ce72e2891f92a96b521827b1` |
| `evals/product-demo/d1-p3-back-chain-contracts-2026-09-26.md` | 见快照目录 `SNAPSHOT.md`（文件不能记录自己的最终哈希） |

快照目录：`_stage-amz-control/d1-p3-20260926-112756/`。
