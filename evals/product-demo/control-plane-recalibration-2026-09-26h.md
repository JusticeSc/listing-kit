# 第十二次控制面校准（v1.16 → v1.17，2026-09-26）

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY  
> 本文只记录本次校准的输入、裁定和检查结果。Goal 与实施合同见
> `docs/product-demo-goal-and-implementation-plan.md`；当前状态见
> `_working/amz-listing-kit-product-demo/state.md`。本次零网络、零模型调用、零付费动作。

## 1. 触发与最早断点

产品发起人确认采用「前端先定义产品，后端按界面反推」的开发方向，并要求完成控制面校准。
审计发现 v1.16 同时存在 §2 现行 Goal 与 §2.1 拟更新 Goal。后者虽标为草案，但仍是第二份可引用的
目标正文；同时 §1.14 把系统 Goal 的动态 `paused` 状态写进了计划。这两处分别违反「产品目标唯一」
和「生命周期状态只由系统 Goal 管辖」。

## 2. 裁定

1. 系统 Goal `01a0ca17-2179-7eb0-969a-af9c79c4d8ca` 的 objective 已覆盖最终产品、完成证据、
   非目标和模型失败停止线，继续作为唯一目标，不因实施顺序变化而改写。
2. 删除 §2.1 第二份 Goal 草案；前端优先、完整 mock 走查、界面冻结后反推最小后端，归入计划的
   实施合同，已经由 v1.16 的 §5、§6.11.3A 与 §6.12.0 承载。
3. 产品方向已确认，不再把「方向未批准」列为 blocker；FE-01–FE-04 尚未产出和冻结仍是当前事实，
   所以下一动作保持 D2.R1b，不虚报完成。
4. 系统 Goal 本次实读仍为 `paused`；生命周期未被本文或 state 改写，Phase 2 继续 blocked。

## 3. 修改与恢复点

- 计划：v1.16 → v1.17；新增 §1.15，删除第二份 Goal 草案和计划中的动态状态句。
- 三份机器合同：只把 `plan_version` 复核并同步为 v1.17；状态词、权限和处理语义未改。
- current state：刷新系统 Goal 实读时间；删除两个已失效的等待项；保留 `D2.R1b` 为唯一下一动作。
- 改前快照：`_stage-amz-control/calib-v117-20260926-2221/`。
- 改前 sha256：计划 `BBE412D3F6BDA4A5`；state `3053EC312CE6F224`；processing contract
  `CEDB65200586A658`；authority matrix `AE522F110BEBA1D7`；state vocabulary `EF0BBA9CC8206A75`。

## 4. 验证边界

本次验证只证明控制面的一致性与可恢复性，不证明 D2.R1b 已完成、前端可用、真实模型效果或产品
完成。

| 检查 | 本次读数 |
|---|---|
| 系统 Goal 直读 | id 与 state 一致；objective 与计划 §2 一致；生命周期仍为 `paused` |
| `contract_tools.py --check` | rc=0；识别计划 v1.17；文件、处理合同、权限、状态词汇和计划漂移全部通过 |
| `contract_tools.py --self-test` | rc=0；18/18 个反例全部被正确拦截 |
| `check_project_state.py --project .` | rc=0；J0–J10 全部通过 |
| `evals/probes/project_state.py` | rc=0；19 向符合预期，state 已逐字节恢复，探针副本已清理 |
| `tools/check_docs.py` | rc=0；登记 31 份 = 实际 31 份；产品目标、执行状态和实现各自唯一；11 条去重命令实跑通过 |

改后 sha256：计划 `F5F5DEABBBBF5195`；state `25FEF29C17E1A792`；processing contract
`C7F931D4AAD148AF`；authority matrix `873855817CEDB9D5`；state vocabulary `D2DF859986E17448`。

结论：控制面现已对齐到 v1.17，但系统 Goal 未恢复，因此这只是“准备与路由正确”，不是正式执行
已经恢复。唯一合法下一动作仍为 D2.R1b；只有系统 Goal 恢复为 active 后才可开始写其交付物。
