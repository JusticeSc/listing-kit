<!-- 拆分件 01/03 · 父文档 evals/product-v2/refactor/packet11-convergence-20261008.md -->
# V2.R5.1 差量收口：结转红闭合、机制与剩余前沿（2026-10-08）
[返回 packet11-convergence-20261008.md](packet11-convergence-20261008.md)

# V2.R5.1 差量收口：结转红闭合、机制与剩余前沿（2026-10-08）

> CONTROL-STATUS: historical · AUTHORITY: evidence
> 本文件是 2026-10-08 这一轮"审计上一轮 → 确定真实状态 → 收口结转红 → 排后续规划"的证据。
> 目标/任务/完成判据只在 `docs/product-v2-refactor-plan.md`；进度只在
> `_working/amz-listing-kit-product-v2/state.md`；本文件不新增任务、不改变完成判据。
> 本轮 0 次付费模型调用、未提交/未推送/未部署、未做 V1 日落。

## 1. 范围与授权边界

- 用户指令：审计之前的工作、确定当前状态、设计后续规划（本轮在本会话内继续把上一轮结转的
  红按既有任务收口，不新建任务/Goal/RC）。
- 预算账本 `_working/amz-listing-kit-product-v2/budget-ledger.json` 未变（image 8/8、
  semantic 5/6、总 13/14、已花 1.15 元、占用 1.61/5 元）：本轮全部验证用注入替身与本地假 provider。
- 权限门照旧：付费调用、私有上传、提交/推送、部署、V1 日落各自单独设门；本轮均未触发。

## 2. 审计：上一轮结转清单与实际结果

口径核对（本轮审计附带）：当前生效的 Goal 正文是计划 §2.1 的**重写版**
（Objective/Success criteria/Verification/Boundaries/Stop conditions），
sha256=`bac1155dbef21876391328dafd50a5624dee8461388754021a31aa59ff1c6fc6`；
系统 Goal 观察 `evals/product-v2/refactor/goal-observation-final-delivery-20261007.json`
的 `objective_sha256` 与 `tools/refactor_resume.py` 对实时 §2.1 的计算**一致**。
state 历史行里的 `6677a680…` 是重写前文本，只能当历史，不得用于绑定/一致性比对
（已在 state 顶部加提醒，未改写历史行）。

| 结转项 | 原状态 | 本轮实测 |
|---|---|---|
| `verify_v2_3_5_pre_generation_confirm.py` -03/-05/-06/-07/-08/-11 | 6 红未复跑 | **绿 25/25**（`v2.3.5-pre-generation-confirm-20261008-005056-diag6`） |
| `verify_v2_4_3_batch_execution.py` | 曾红 | **绿**（`…-20261008-005618-diag1`） |
| `verify_v2_4_4_candidate_blob.py` | 曾红（同源 ERR_CONNECTION_REFUSED） | **绿**（`…-20261008-005644-diag1`） |
| `verify_v2_5_3_compare_panel.py` -15 | 期望过期未收紧 | **绿 19/19**（`…-20261008-005703diag1`） |
| `verify_v2_packet08_settings_vision.py` 三个空证 | 未修 | **绿（含真实前置修复与新增 P08-01e）**，见 §4.2 |
| 端口改造后的悬挂引用（1_4/2_3/5_2/6_1） | 未复跑 | **四个全绿**，见 §4.1 |
| `verify_v2_4_2_generation_attempt.py` | 时红时绿（r1 红 r2 绿） | **绿**，见 §4.3(a) |
| `verify_v2_ui_2_interaction_visual.py` UI2-17 | 红 | **绿**，见 §4.3(b) |
| 两轮完整离线回归 | 未重跑 | **44 条 × 2 轮全绿、指纹一致**，见 §3 |
| 发布条件 truth-table 源码钉 | 未替换 | 已替换为行为证据（§5） |

## 3. 两轮完整离线回归（本轮工作批次）

- 入口：`uv run --locked python tools/verify_v2_7_1_regression.py --rounds 2`
  （命令清单只从 CI verify job 读取，44 条：文档/状态/索引/验证策略探针 6 条、npm 三门、
  `app/server.py --check`、33 个验证器）。
- 结果：`evals/product-v2/v2.7.1-regression-20261008-p11close2-final.txt/.json`
  → 两轮各 44 条 **rc=0**，结果信号指纹**逐字节一致**（`f971df6abdd031e6…`），`problems` 为空。
- 一次先前的尝试 `…-20261008-p11close-final.json`：第 1 轮全绿、**第 2 轮
  `tools/verify_v2_6_2_delivery.py` 在第一个 harness 页载入处 90s 超时**（页面从未落定结论：
  既不是 `passed/failed`，也没有 `crashed`）。这是本机回环偶发抖动族（RC19）的表现，不是产品缺陷：
  该页的模块图里没有本轮改动的任何产品文件，且"脚本抛错"会以 `status: "crashed"` 落定而不会超时。
  处置见 §4.4（加诊断 + 仅对可识别传输签名重载一次并留痕）。
- 批次说明：这是 **V2.R5.1 收口**的工作回归，不占用 R7.1 的最终验收批次（最终两轮在 G6/R7.3 之后跑）。

## 4. 本轮修复：现象 → 机制 → 修复 → 证据

### 4.1 端口改造留下的悬挂引用（验证侧，4 个验证器）

- 现象：`verify_v2_1_4_formal_entry.py` `NameError: name 'server' is not defined`；
  `verify_v2_2_3_intake_understanding.py`、`verify_v2_5_2_vlm_review.py`
  `NameError: name 'port' is not defined`；`verify_v2_6_1_selection.py`
  `AttributeError: module 'verify_v251' has no attribute 'free_port'`。
- 机制：3c945d5 把"探针先占端口"改为"产品服务器绑 0 号端口再读回"时删除了端口变量与本地
  `free_port`，四处引用留在原地。`py_compile` 只查语法，NameError/AttributeError 只在真跑时出现
  ——"22 个验证器都已改造"的静态收尾不等于它们还能跑。
- 修复：1_4 恢复 `server = FormalServer(port)`；2_3 报告行与 5_2 的四处直发 HTTP 改
  `server.server_address[1]`；6_1 去掉 `v251.free_port()`，改为绑 0 读回。
- 证据：`v2.1.4-formal-entry-20261008-014208-fix1`、`v2.2.3-intake-understanding-20261008-014226-fix1`、
  `v2.5.2-vlm-review-20261008-014241fix1`、`v2.6.1-selection-20261008-014250fix1`。

