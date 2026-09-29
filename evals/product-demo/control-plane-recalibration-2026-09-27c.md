# 第十六次控制面校准（Goal 进入 blocked 的状态映射，2026-09-27）

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY
> 本文只记录本次校准的触发、裁定、前后哈希与检查读数。产品合同见
> `docs/product-demo-goal-and-implementation-plan.md`；当前状态见
> `_working/amz-listing-kit-product-demo/state.md`。本次零网络、零模型调用、零付费动作。

## 1. 触发与最早断点

D2.R1c 的全部 AI 侧工作已经完成：单页工作台实现与 v1.20 措辞对齐、R2.a 走查包三件产物
（任务说明、观察记录表、落点判据）、开发者预演与全部守卫。此后同一阻塞条件——
**FE-08 需要产品发起人（用户）亲自走查、D2.R2.b 需要一名未参与开发的真人**——连续四个
目标轮次没有变化；计划 §6.11.7 明文禁止在 D2.R3 关闭前开始 Phase 3 任务，§6.11.5 也写明
「这不是可以靠加班补上的工作」。按 Goal 纪要的 blocked 纪律（同一阻塞连续三轮以上且无法
在无用户输入下有实质进展），系统 Goal `01a0ca17-2179-7eb0-969a-af9c79c4d8ca` 于
2026-09-27T02:12:12+08:00 标记为 `blocked`。

但控制面 schema 此前没有 blocked 映射：`RECORD_STATUSES` 只有 active/paused/completed/
superseded，J9 只允许「记录读数一一对应」（active↔active、paused↔paused）。历史快照里
Goal 只出现过 active 与 paused（`_stage-amz-control/goal-active-20260926-2233`、
`calib-v117-20260926-2221`），没有 blocked 先例。若只把 Goal 标 blocked 而不同步记录，
或把观测写成 paused，都会让守卫与事实脱节。本次校准把映射补齐。

## 2. 裁定

1. Goal 控件读数 `blocked`（等外部输入、AI 无法推进）时，同一事实写满三处：
   执行记录 `status: paused`、受影响 Phase `status: blocked`、
   `system_goal_observed_status: blocked`。
2. `check_project_state.py` 的 J9 比对改为：active 记录仍必须配 active 读数；
   paused 记录允许读 paused（主动暂停）或 blocked（外部依赖暂停）；只要三处有一处没跟上，
   J9 仍会响。
3. 不给 `RECORD_STATUSES` 增加 blocked：那会牵动 J7（只对 active/paused 记录检查
   next_action）等多处语义，而 paused + blocked + blocked 的三层表达已能区分
   「记录暂停 / 阶段卡住 / 目标被标不可推进」。恢复路径：用户恢复输入后，三处一起改回
   active 并在恢复时记录一次读数。
4. 本次不动计划、契约、Goal 文本与任何产品事实。

## 3. 修改与恢复点

| 文件 | 改前 sha256 前 16 | 改后 sha256 前 16 |
|---|---|---|
| `tools/check_project_state.py` | `AA037A716A88011C` | `85B07AC00B4DF9A4` |
| `_working/amz-listing-kit-product-demo/state.md` | `36F18A5E96DD0737` | `7C103B24948C20DC` |

- 改前快照：`_stage-amz-control/goal-blocked-20260927-0211/`（两份改前副本）。
- state 在本次校准期间被两次写入：先同步 blocked 映射（此时 sha256 前 16 为 `C65E019C6D1742E4`），
  再把 `latest_audit` 指向本文并刷新 `updated_at`；上表为最终值。
- state 的三处同步：顶层 `status: paused`、Phase 2 `status: blocked`、
  `system_goal_observed_status: blocked`（observed_at 2026-09-27T02:12:23+08:00）；
  `blockers` 新增 `product_owner_fe08_walkthrough_pending_user_action` 与
  `d2r2b_real_user_not_yet_arranged`；`next_action_task` 保持 `D2.R1c`
  （J7 对 paused 记录仍要求且检查下一动作）。

## 4. 验证读数

| 检查 | 读数 |
|---|---|
| `check_project_state.py --project .`（判据改动后、state 同步前） | rc=0 —— 改动不破坏现状 |
| `evals/probes/project_state.py`（19 向注入自检） | rc=0；19 向全部与预期一致（含 O/P/Q 的 J9 用例；state 逐字节恢复） |
| `check_project_state.py --project .`（state 同步为 paused/blocked/blocked 后） | rc=0；J0–J10 全过 |
| `tools/check_docs.py` | rc=0；登记 31 = 实际 31；真跑 11 条去重命令（跳过 34 条） |
| Goal 控件读数 | `blocked`（2026-09-27T02:12:12+08:00） |

## 5. 验证边界

本文只证明「Goal blocked ↔ 记录 paused + 阶段 blocked + 读数 blocked」这一映射在三处
一致、守卫与自检可跑；不证明 FE-08、D2.R2.b 或任何产品事实。恢复时必须三处一起改回
active，J9 会对只改一处的状态继续报警。

结论：Goal 因外部依赖进入 blocked 已写满控制面；用户完成 FE-08 走查或安排 R2.b 真人后，
从本次记录恢复 active。
