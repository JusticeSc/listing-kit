# 控制面校准 #2（2026-09-26）

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY  
> 记录时间：2026-09-26T11:15:27+08:00。本文只记录这次校准读了什么、跑出了什么、据此改了什么。  
> 当前状态、下一动作和未来计划分别以 `_working/amz-listing-kit-product-demo/state.md`
> 与 `docs/product-demo-goal-and-implementation-plan.md` 为准。

## 1. 这次要回答什么

上一轮（`control-plane-single-authority-2026-09-26.md`）建立了「一类事实一个权威」，本轮的问题是：
那条规矩**现在还在不在**，以及「下一阶段详细实施规划」有没有可执行的落点。
判据不用形容词：跑守卫、读唯一权威、把两份文件逐行比。

可计费模型调用：**0 次**。没有改动任何候选、任何冻结证据、任何 `demo/` 代码。

## 2. 新鲜读数（全部本次运行）

| 检查 | 命令 | 结果 |
|---|---|---|
| 项目状态守卫 | `tools/check_project_state.py --project .` | rc=0（J0–J9 全过；3 份工作记录） |
| 状态反向探针 | `evals/probes/project_state.py` | 17/17 与预期一致，state 逐字节恢复 |
| 文档登记与身份 | `tools/check_docs.py` | rc=0（登记 30 份 = 仓库 30 份；真跑 10 条命令，跳过 31 条） |
| 处理合同守卫 | `demo/contract/contract_tools.py --check` | 先 **rc=3**，复核后 rc=0（见 §4） |
| 合同自检 | `contract_tools.py --self-test` | 18/18 项被正确抓到 |
| 前半链契约 | `demo/core/run_front_contracts.py` | 17/17 符合预期（零付费） |
| 参考包一致性 | `demo/fixture/pack_tools.py verify --project .` | READY |
| v2 冻结基线 | `tools/snapshot_v2_baseline.py --check` | **rc=1（预期红）**：代码树身份已变化，D1.C2 仍 blocked |
| Goal 生命周期 | 系统工具直读 | `active`（不是从文件推断的） |

Goal 文本一致性（本次做了内容级复核）：计划 §2 的引用块包含 objective 的 9 个特征句，
逐句命中；全仓库检索这三句的完整文本，**只有计划 §2 一份**（`rg` 结果只返回该文件）。
逐字节比对由 2026-09-25 的记录承担（`state-calibration-2026-09-25b.md` §9），本次没有重做——
那需要把 objective 原文从系统控件导出成文件。

## 3. 审计结论：控制面仍然「政出一门」

- 目标、阶段、Gate、任务与依赖只有 `docs/product-demo-goal-and-implementation-plan.md` 一份；
  state 只保存进度、证据、阻塞与下一动作，并且**只按 ID 引用**——这一条由守卫 J4/J6/J8 现场
  验证，不是宣言。
- 「当前状态」没有第二处：本次把 `evals/` 里 5 处含「下一动作 / 下一任务」的历史报告逐条看过，
  它们要么是时点快照，要么指向已退役 ID（见 §5），没有一处被当权威读。
- 文档身份唯一：INDEX 登记 30 份与仓库实际 30 份完全一致，无未登记、无登记不存在的文件。

## 4. 计划 v1.6 → v1.7：改了什么，凭什么改

计划升到 **v1.7**。四处新增、一处任务新增，理由见计划 §1.5；这里只记可核对的证据。

1. **合同守卫先变红、再复核、再变绿。** 版本号一升，`contract_tools --check` 立刻报
   「契约按计划版本 v1.6 冻结，当前计划是 v1.7 —— 计划改过，合同必须重审」（rc=3）。
   这证明冻结版本不是橡皮图章。复核结论：本次没有改动合同依赖的正文，故更新三份契约的
   冻结版本到 v1.7，守卫恢复 rc=0，自检仍 18/18。
2. **本次没有改动的小节（哈希登记，供下一步复核）**

| 小节 | sha256 前 24 位 |
|---|---|
| §2 Goal 文本 | `f6b8cbe7d2ca0d1a4d2a1891` |
| §4.2 状态边界 | `bd5a89f9424f6f04f3a5ad96` |
| §4.4 全链路处理合同 | `05f02b64f29bd36c6c6ce742` |
| §4.5 跨环节不变量 | `36a9fa569d63f83f665240c6` |
| §9.1.1 量测适用性 | `5456d135ca5348b8ec8bcb75` |

3. **v1.6 没有独立副本。** 想逐行对比 v1.6 与 v1.7 时，仓库与工作区外备份里都没有 v1.6 的
   计划文件（最近的快照是 v1.4，见 §5.1）。这条已按 §5.1 处置。

## 5. 本次发现的问题与处置

| # | 发现 | 证据 | 处置 |
|---|---|---|---|
| 1 | 改权威文档不留快照，事后无法独立比对 | 工作区外最近的计划快照是 v1.4（`_stage-amz-control\control-rebaseline-20260926-103053\`），不存在 v1.6 副本 | INDEX §5 写入路由新增「改权威文档前先留快照」并记哈希；本次为 v1.7 留快照 |
| 2 | 「换商品不改代码」只是判据文字，商品路径写死在模块常量里 | `rg` 命中 `demo/core/front_chain.py`、`demo/core/prompt.py`、`demo/fixture/product_check.py`、`demo/fixture/pack_tools.py`、`demo/provider/run_first_round.py` | 新增任务 **D1.P4**（商品包解析 + `demo/**.py` 哈希清单探针）；计划 §4.6 写明「商品身份只能来自商品数据包」 |
| 3 | D1.P3、D1.R1–R4、Phase 2 只有 Outcome，没有输入/处理/输出 | 计划 v1.6 §6.3/§6.4 逐行复核 | 计划 §6.10/§6.11 补实现规格（含 PC-09 的三步顺序、人工裁决落数据、tracer 页面与走查协议） |
| 4 | 事实验证若用视觉模型，成本与授权没有归属 | `evals/probes/vlm_stability/report.json` 显示项目已在用 `qwen-vl-max`（`qwen-vl-max-latest` 403 不可用） | 计划 §10 新增成本口径：只允许已在用的 `qwen-vl-max`，逐次记账，阶段上限 ≤ 40 次；换模型或提高上限需新授权 |
| 5 | 历史报告里仍有指向已退役任务 ID 的「下一动作」 | `control-plane-single-authority-2026-09-26.md:60`（指向 D1.6）、`d0-8-g0-audit-2026-09-25.md:21`（指向 D1.1） | **不改证据文件**（改了就是篡改历史）。以计划 §7.2 为准：这些 ID 已退役，不得出现在 `next_action_task` |
| 6 | 项目不是 git 仓库，回滚靠手工快照 | 项目根 `git log` → `fatal: not a git repository` | 登记为 D7.2（干净状态安装与回退演练）的输入；不当成缺陷，但不得假设有版本控制兜底 |
| 7 | Phase 2 与 Phase 6 需要真人，且不可由 AI 替代 | 计划 §6.11、state `unknowns` | 计划 §6.11 写明前置条件（提前约定人选、不接受口头技术指导）；未安排则 Gate 保持未过 |
| 8 | v2 冻结基线仍是红的 | `snapshot_v2_baseline --check` rc=1 | 这是环境阻塞（提交内存门槛），不是产品失败；不用 `--force`、不改哈希，D1.C2 继续 blocked |

## 6. 本次改动的文件与哈希

| 文件 | sha256 |
|---|---|
| `docs/product-demo-goal-and-implementation-plan.md`（v1.7） | `be2003caa50e558297a0d2c5ed12e926fa7a83c4a5336b3d2357d52930ee2ae8` |
| `docs/INDEX.md` | `0a366d33f6f450c742de219f725bf389226c4a09ffdf494ab7627fc1d83693c6` |
| `_working/amz-listing-kit-product-demo/state.md` | `ff3fdb1ed7a378afb233f4e51d720f425279040942ed2f92c118156925b6a8d4` |
| `demo/contract/processing_contracts.json` | `15e351615a8db8a1d22d035b7815269dffe24f2d660b412c0e717521fc5ddb17` |
| `demo/contract/authority_matrix.json` | `71245327ee7e278a0aa190423e158bf48b817722e867bf21070e99b44c8e63b1` |
| `demo/contract/state_vocabulary.json` | `c0fa626c827c264b0ef55a8add9573a6f8018b0470c3335688e26f06a35d9a61` |

工作区外快照：`_stage-amz-control/plan-v17-20260926-111536/`；改计划的那段脚本留在
`_stage-amz-control/apply_plan_v17.py`（锚点唯一、失败即中止），可供第三方复核本次到底改了什么。

## 7. 本文件不证明什么

- 不证明产品可用：Phase 1 仍在进行，G1 的机器分项仍未裁决。
- 不证明换商品通用：D1.P4 还没跑，目前只有「路径写死在代码里」这条负面证据。
- 不证明 v2 基线可用：那条仍是红的，本次没有尝试环境绕过。
- 不证明 MCP/外部验收：本次全部离线，零付费调用。
