# 第十四次控制面校准（v1.18 → v1.19，2026-09-27）

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY
> 本文只记录本次校准的触发、裁定、前后哈希与检查读数。产品合同见
> `docs/product-demo-goal-and-implementation-plan.md`；当前状态见
> `_working/amz-listing-kit-product-demo/state.md`。本次零网络、零模型调用、零付费动作。

## 1. 触发与最早断点

D2.R1c 收尾时逐句复核计划 §6.11.4（离线假动作清单）与实际渲染文本：

- 第一句能在 `app/static/workbench.js` 的整套按钮提示里逐字找到（「离线演示，不调用模型」）；
- 后两句对不上：计划写「离线演示，不产生新候选」「离线演示，不写文件」，
  实际渲染是「离线演示：不调用模型，不写文件；这里只模拟状态变化，不产生真实新候选。」
  与「离线演示：未写出任何文件。该清单用于验证交付结构，不是文件下载。」；
- `README.md` §2「离线走查怎么起」仍写旧八页 tracer 与「离线演示，不做这件事」，
  与单页工作台、实际声明都不同。

界面文案更精确（明确写「不产生真实新候选」，并说明清单不是下载），因此裁定：改计划与 README、
不改界面；页面文案与渲染输出零变化。

同一次浏览器复核还发现一个真实实现缺陷：生成过程中点「重置演示」，在途整套生成会把
`phase` 写回重置后的新状态，留下「阶段：逐图审核 + 方案未生成」的矛盾态。已按 D2.R1c 在
`app/static/mock-service.js` 修复（重置进入同一动作队列），并加探针断言与反向注入验证；
细节见 `evals/product-demo/d2-r1c/mock-product-2026-09-26.md` §1.2。全程键盘复核还暴露第二个实现缺陷：
事实/视觉单选按键后焦点掉回 `body`，已按同一记录 §1.3 修复并加锚点判据。这两处都不是合同改动。

## 2. 裁定

1. 计划升到 v1.19，新增 §1.17；§6.11.4 三行改成渲染后的原文。走查说明引用其中两句，
   由 `evals/probes/walkthrough_brief.py` 用真 HTTP 取回的单页与渲染代码逐字核对
   （第三句允许引用可辨识子串，原句仍以计划为准）。
2. 三份机器契约只同步 `plan_version` → v1.19；合同、权威矩阵与状态词内容不动。
3. README §2 走查段改为单页流程与三句实际声明；README 其余 v2 部分不动。
4. 本次不触碰 §2 Goal 文本、§3 完成合同、§4 业务模型与 §5 阶段与 Gate；不因此把 D2.R1c 标 done。

## 3. 修改与恢复点

| 文件 | 改前 sha256 前 16 | 改后 sha256 前 16 |
|---|---|---|
| `docs/product-demo-goal-and-implementation-plan.md` | `E95D098295178263` | `873A939AF6437681` |
| `README.md` | `7C0115659CAB9A26` | `D4E17DAA31CFB227` |
| `demo/contract/processing_contracts.json` | `097422FD5EF80784` | `00BDFBF780D527EE` |
| `demo/contract/authority_matrix.json` | `4993ABFCD313543F` | `3B78A2AE052F7F02` |
| `demo/contract/state_vocabulary.json` | `C90B4F1DF10B7DD8` | `A682BA130AAE7D93` |
| `evals/product-demo/d2-r2/walkthrough-brief.md` | `92F62C5F46A9DC23` | `3AEEEEB6E0633522` |
| `app/static/mock-service.js`（§1 的重置竞态修复） | 未入快照 | `50485BA0956996ED` |
| `evals/probes/mock_workbench.mjs`（新增重置断言） | 未入快照 | `7927CC01AF16A14B` |
| `app/static/workbench.js`（§1 的键盘焦点修复） | `211389B7E66A2B26`（按新增属性逆推） | `CF5072F317545D25` |
| `app/server.py`（新增焦点锚点判据） | 未入快照 | `0C9D445B50426AE4` |

- 改前快照：`_stage-amz-control/calib-v119-20260927-0015/`（含前六份与两份证据文件的改前副本）。
- 修复的反向验证：把 `reset` 临时还原成旧实现，探针退出码 1
  （`reset must not surface the replaced generation as an error`）；恢复后文件逐字节一致。

## 4. 验证读数

| 检查 | 读数 |
|---|---|
| `contract_tools.py --project . --check` | rc=0；计划 v1.19；文件 / 契约自身 / 权威矩阵 / 状态词汇 / 与计划漂移全过 |
| `contract_tools.py --self-test` | rc=0；18/18 被正确抓到（含「契约按旧计划版本冻结」报出当前计划 v1.19） |
| `walkthrough_brief.py`（收尾重跑） | rc=0；8 步 · 41 句（「做过之后才出现」13 句）· 5 处按钮；新增两句假动作原文都有落点且已写进「你应该看到」 |
| `walkthrough_brief.py --self-test` | rc=0；5/5 与预期一致 |
| `mock_workbench.mjs` | 通过；含 §1 的重置断言（注入旧实现时 rc=1，证明会红） |
| 浏览器复核 | 真页面逐字显示两句新增假动作原文；生成中点「重置演示」最终回到「阶段：待确认资料 / 未生成」、无错误提示 |
| `app/server.py --check`（v1.19 修复后重跑） | rc=0、9.0s；10959 个文件路径 / 大小 / 修改时间未变；26 个关键文件逐字节未变。此后加入键盘焦点锚点判据，最近一次 7.4s / 10960 个文件（见 D2.R1c 记录 §2） |
| `tools/check_docs.py` | rc=0；登记 31 = 实际 31；真跑 11 条命令 |
| `check_project_state.py --project .` | rc=0；J0–J10 全过（state 写入本文件指针后收尾重跑） |
| `evals/probes/project_state.py` | rc=0；19 向全部与预期一致，state 逐字节恢复（收尾重跑） |

## 5. 验证边界

本文只证明控制面与措辞一致、判据可跑、重置竞态已修复；不证明 FE-08 已走查、D2.R1c 已完成、
点击后一定会渲染这些字（落点判据只证明它们来自真 HTTP 返回的页面与渲染代码），也不证明真实模型
与产品完成。页面渲染与完整闭环的逐句证据在 `evals/product-demo/d2-r1c/mock-product-2026-09-26.md`。

结论：计划与实现声明对齐到 v1.19，重置竞态已修复并双重验证；唯一下一动作仍是 D2.R1c 的
产品发起人 FE-08 走查。
