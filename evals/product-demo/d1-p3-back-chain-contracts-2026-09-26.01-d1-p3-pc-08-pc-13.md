<!-- 拆分件 01/02 · 父文档 evals/product-demo/d1-p3-back-chain-contracts-2026-09-26.md -->
# D1.P3 后半链合同验证（PC-08 – PC-13）
[返回 d1-p3-back-chain-contracts-2026-09-26.md](d1-p3-back-chain-contracts-2026-09-26.md)

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

