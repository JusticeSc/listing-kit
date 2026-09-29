# 第十五次控制面校准（v1.19 → v1.20，2026-09-27）

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY
> 本文只记录本次校准的触发、裁定、前后哈希与检查读数。产品合同见
> `docs/product-demo-goal-and-implementation-plan.md`；当前状态见
> `_working/amz-listing-kit-product-demo/state.md`。本次零网络、零模型调用、零付费动作。

## 1. 触发与最早断点

D2.R1c 把 §4.7.7/§4.7.8 从 D2.R1b 确认稿落到 `app/static/` 时，先做「确认稿 → 实现」对照：
第一版实现把三栏职责做错（候选挤进右栏）、没有候选主画布、候选用 button 卡、沿用旧色板、
点击目标 2.75rem、没有错误摘要，提示词也不显示来源候选。逐项改造之后又用真浏览器复核出三个
真实缺陷：参考图与候选图被 HTML `height` 属性钉死宽高比（主图实测 473×1024）；F4/F7/F8 的
结论选项把文字列挤成约 50px 竖排；事实核对、视觉结论、选候选三条本地记录误走 90ms 模拟队列，
点击后界面短暂回跳。三处已修复，细节与读数见 `evals/product-demo/d2-r1c/mock-product-2026-09-26.md` §9。

实现对齐后再次逐句复核 §4.7.7/§4.7.8，发现五处「计划写的词在界面上找不到或实现已更精简」
的漂移：线框右栏的「责任者」、状态投影里的「STALE」、导出后「显示路径」、「中性棋盘/白底可切」，
以及交付栏同一事实的第二处。按「界面文案比计划草稿更准确时改计划、不改界面」与「除必要按钮与
视图外不保留冗余」裁定：改计划与措辞，不动界面。

## 2. 裁定

1. 计划升到 v1.20，新增 §1.18；§4.7.7 线框「历史与责任者」改「历史（旧候选 / 旧版本）」、
   状态 7「标 STALE」改「标『待返工』」、状态 9 与 §4.7.4 导出后显示统一为「Mock 显示清单预览；
   正式执行含文件位置」、§4.7.8 图片行改「中性棋盘舞台托白色画布（无切换控件）」。
2. 三份机器契约只同步 `plan_version` → v1.20；合同、权威矩阵与状态词内容不动。
3. 本轮不动 §2 Goal 文本、§3 完成合同、§4 其他对象与状态、§5 阶段与 Gate；不因此把 D2.R1c 标 done。
4. 前端三个缺陷修复属于实现（见 §9 记录），不改变合同语义；界面冻结进入 FE-08 走查。

## 3. 修改与恢复点

| 文件 | 改前 sha256 前 16 | 改后 sha256 前 16 |
|---|---|---|
| `docs/product-demo-goal-and-implementation-plan.md` | `873A939AF6437681` | `A66FF78D84A851E5` |
| `demo/contract/processing_contracts.json` | `00BDFBF780D527EE` | `C653A021382A819B` |
| `demo/contract/authority_matrix.json` | `3B78A2AE052F7F02` | `77111DE8541704A6` |
| `demo/contract/state_vocabulary.json` | `A682BA130AAE7D93` | `7F261E9641CE4174` |
| `evals/product-demo/d2-r1c/mock-product-2026-09-26.md` | `63924614CA83B944` | `D6B46FCACD2A3818` |
| `_working/amz-listing-kit-product-demo/state.md` | `36640DD6CC4C84CA` | `36F18A5E96DD0737` |

- 改前快照：`_stage-amz-control/calib-v120-20260927-0157/`（六份改前副本）。
- 注意：`evals/probes/project_state.py` 会临时重写 state.md 再逐字节恢复（mtime 必变）。它不得与
  `app/server.py --check`（整个项目目录的前后写入监控）并行运行，否则会产生「项目目录被写入」的假阳性。

## 4. 验证读数

| 检查 | 读数 |
|---|---|
| `contract_tools.py --project . --check` | rc=0；计划 v1.20；文件 / 契约自身 / 权威矩阵 / 状态词汇 / 与计划漂移全过 |
| `contract_tools.py --self-test` | rc=0；18/18 被正确抓到（含「契约按旧计划版本冻结」报出当前计划 v1.20） |
| `app/server.py --offline-fixture demo/fixture/aster-01 --check` | rc=0；8.7s；10985 个文件路径/大小/修改时间未变；26 个关键文件逐字节未变 |
| `evals/probes/viewport_probe.py` | rc=0；1280 三栏（288 / 540.812 / 368px）、900 两栏（inspector col 2 / row 2）、358 单列（326px）；三档无横向滚动 |
| `evals/probes/walkthrough_brief.py` | rc=0；8 步 · 41 句（「做过之后才出现」13 句）每句都有落点 |
| `node evals/probes/mock_workbench.mjs` | 通过（含 originCandidateId 断言） |
| `evals/probes/project_state.py` | rc=0；19 向全部与预期一致；state 逐字节恢复（首次运行与守卫重叠造成一次假阳性，已定位为并行运行，见 §3 注） |
| `tools/check_docs.py` | rc=0；文档登记 31 = 实际 31；真跑 11 条去重命令（跳过 34 条，各有理由） |
| `tools/check_project_state.py --project .` | rc=0；J0–J10 全过（工作记录 3 份、活动记录唯一） |

## 5. 验证边界

本文只证明计划、契约、证据文件与 state 的控制面一致，以及列出的判据在 2026-09-27 可跑出上述读数；
不证明 FE-08 已走查、D2.R1c 已完成，也不证明真实模型与产品完成。界面渲染与完整闭环的逐句证据在
`evals/product-demo/d2-r1c/mock-product-2026-09-26.md` §9。

结论：计划与实现对齐到 v1.20；唯一下一动作仍是 D2.R1c 的产品发起人 FE-08 走查。
