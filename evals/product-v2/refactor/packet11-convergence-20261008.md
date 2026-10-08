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

### 4.2 设置面板：一个真实产品缺陷 + 三个空证（产品侧 + 验证侧）

- 产品缺陷：填完商品资料后**立刻**打开设置面板并点应用（草稿仍在防抖里、尚未落盘）时，
  已输入的名字/介绍/卖点被清空、分析入口被锁。
  - 机制：`modelSettings.subscribe(() => { capabilities = …; if (projectId) renderAll(); })`
    在草稿落盘前整体重渲染，输入框按**存储值**（空）重画，待落盘草稿被丢弃。
  - 修复：订阅回调先落盘草稿再渲染。**只调 `inputs.saveIntakeNow()`**（无脏草稿即 no-op；
    真落盘时经 `changed` → 派生），不调用带无条件派生的 `inputView.saveIntakeNow()`
    ——后者会在能力就绪前派生并回写项目状态（§4.3(b)）。
  - 证据（一次性探针 `_working/p11fix/_probe_settings_intake.py`）：修复前 A 组（立刻应用）
    `name=""`、`gate="还缺：商品名称必填。"`，B 组（等 2s）正常；修复后 A/B 均保留
    `name/description`，入口可用。
  - 常驻守卫：`verify_v2_packet08_settings_vision.py` 新增 `P08-01e`（DOM 值保留 + 已落盘 +
    入口未锁），与其余检查一起进 CI 与两轮回归。
- 验证侧空证：P08-01d/-03pre 在资料未填时读到"还缺：商品名称必填"，断言退化成空条件；
  补上真实前置后同一套件 23/23 有真实输入（含新增 `P08-01e`：应用设置不丢未落盘草稿）。
- 注意：中途用 `--label` 单独复跑的同类证据（`fix6/diag2/draft-guard`）是同一套件的重复判定，
  已移入忽略目录 `_working/p11fix/scratch/`，不当作独立证据。

### 4.3 重开项目会改库：boot 期派生 + 环境代理掩盖（4_2 / UI2-17）

**(a) 4_2 重启后 `base` 陈旧，被环境代理伪装成 502。**

- 现象：`V2.4.2-20` 期望 400 `EXECUTION_IDENTITY_MISMATCH`，实得 **502 且 body 为空**；
  `-99` 浏览器闭环被 `HTTPError: HTTP Error 502: Bad Gateway` 打断。
- 机制两层：
  1. `restart_server()` 用 `make_server()`（端口 0）重起，拿到**新端口**，`base` 仍指旧端口；
     Windows 偶尔把刚释放的端口再发给它 → 时红时绿（正是它此前"r1 红 r2 绿"的来源）。
  2. 本机 `HTTP_PROXY=http://127.0.0.1:7897`，`urllib` 连回环也走代理；端口没人监听时代理回
     `502 Bad Gateway` + `Content-Length: 0`，把真实连接错误伪装成"网关故障"。Chromium 不走该代理，
     所以浏览器侧照常成功，掩盖了同一问题。
- 探针：`_working/p11fix/_probe_42_restart.py`（关闭后同端口 → `HTTPError 502 'Bad Gateway'`、
  body 空、新端口 26649 ≠ 旧端口 26634）；`_working/p11fix/_probe_loopback_noproxy.py`
  （加回环 no_proxy 后死端口 → `URLError [WinError 10061] 目标计算机积极拒绝`，活端口 200）。
- 修复：`restart_server()` 记 `port = server.server_address[1]` 后**按同端口重建并断言读回一致**
  （IndexedDB 按 origin 隔离，换端口会让"同项目核对"失去前提）；`tools/v2_verify_shared.py`
  为本进程/子进程设回环 `no_proxy`，不再让代理掩盖连接错误。
- 证据：`v2.4.2-generation-attempt-20261008-014820-fix3`（并给 `-20` 的证据补上
  `bad_payload/good_payload/bad_submit_payload`，失败时自解释）。
- 残留：重启后浏览器是否复用旧实例的 keep-alive 连接无法从页面侧观测区分；`-20` 的直发探测
  走全新连接，服务端"无任务表"这一结构性前提不依赖实例身份。

**(b) UI2-17 重开项目会写库（产品侧）。**

- 现象：重开后阶段判定都对（落在「交付」），但整库摘要变了——`projects` 记录的
  `revision 5 → 8`、`updated_at` 变化，`documents`/`assets` 一字未动。
- 机制（用浏览器内包装 `IDBObjectStore.put` 钉出三次写）：`rev 6 = PLAN_REVIEW`
  （**能力/会话就绪前派生产生的中间态回写**，等于重开项目把已确认状态降级）、
  `rev 7/8 = READY_TO_GENERATE`（两次并发派生各自按同一份陈旧内存记录回写，
  `project.state !== state` 护栏被并发绕过）。触发者是 §4.2 的第一版修复：
  `modelSettings.subscribe` 在 boot 期发射 → `inputView.saveIntakeNow()` 里那句无条件的
  `deriveAndApplyState()`。这与 `loadWorkspace()` 既有约定（能力到位后**唯一一次**派生）冲突。
- 修复：见 §4.2 —— 订阅回调只落盘草稿，派生交给 `changed`；boot 路径回到"能力到位后一次派生"。
- 证据（同一次运行的仪器化证据）：修复后 UI2-17 `reload_writes = []`、`diff = {}`、
  前后摘要逐字节相同 → ui_2 16/16 全绿（`v2.ui.2-interaction-visual-20261008-015527fix6`）；
  packet08 复跑仍绿（§4.2 的保证未回退）。

### 4.4 harness 页载入卡住：加诊断 + 仅对可识别传输签名重载一次

- `tools/v2_verify_shared.py: read_suite()` 增加：常驻采集 console 错误、page 错误、
  `requestfailed` 与 `readyState`/脚本清单；超时时区分**脚本抛错**（不重试，直接把诊断抛出）
  与**资源没到**（传输抖动）：后者重载一次，并在套件结果里留 `load_stall_retried` 与
  `load_stall_evidence`（症状进证据，不静默吞掉）。这与 `verify_v2_ui_2_interaction_visual.py`
  既有的 `ConnectionResetError` 重试口径一致（只对可识别的传输错误重试一次并记录）。
- 证据：本轮 `p11close2` 两轮无一次触发（无人为掩盖）；上一次尝试的触发症状见 §3。

## 5. 发布条件（R7.4）：删源码钉，改用失败类别行为证明

- 删除 CI 中扫描工作流自身文本的 truth-table 步骤（本工作树改动，未提交；本轮只读核对生效）。
- CI 容器 job（Docker 部署前）改为 `tools/release_transaction_probe.py --offline-rollback`：
  用真实脚本 + 最小 stage 执行器逐个走失败类别并断言退出码与持久化事务状态。

| 类别 | 断言 | 检查号 |
|---|---|---|
| 用法错误 | exit 2，不写事务、不碰服务 | OR-01 |
| 无开放事务 | exit 4（需人工核对），HOME 零副作用 | OR-02/OR-07 |
| deploy 后验收/指纹类失败 | rollback 恢复旧版本并清事务 | OR-08 |
| deploy 阶段失败（候选不健康） | 脚本自身回退 exit 1，无残留事务 | OR-09 |
| 清理失败（新版本健康） | exit 4；新版本继续服务、previous 保留、**不自动回退** | OR-10 |
| 清障后 finalize | exit 0，previous/备份/事务才被清理 | OR-10b |
| 回退本身失败 | exit 3 且 journal 保留，不报成已恢复 | OR-11 |

结果：`--offline-rollback` **13/13 PASS**（`OR-00`…`OR-11`）。真实容器/TLS/HTTPS 与同 origin
容器页面（ST-LIVE/ST-DEAD/ST-10、`--page-smoke`）仍只能由 CI 的 Docker/发布条件证明。

## 6. 后续规划（按计划依赖顺序，判据与授权边界）

1. **G6/R7.5 类型覆盖**：`app`/`workspace`/`session` 等剩余 Module 按批 TS 化，调用方同批改道；
   `check:types`/`check:generated` 必须覆盖全部迁移 TS 及其浏览器 JS。判据：同一批内
   新建 + 改道 + 删除旧实现在一个验收单位内，任何提交点不得存在两份活着的同一逻辑。
2. **消费者切换与当前格式数据恢复**：G6 成立后按 §15.6.2 逐项核对可复用资产与受影响前提。
3. **R7.3 V1 工程清理**：按实际消费者闭包删除 V1 活路径/失效依赖，保留共享依赖与历史原件。
4. **R7.1 最终两轮**：删后跑完整两轮、指纹一致；计一个验收批次（当前已用 0/10）。
5. **真实能力补证（授权内）**：RC09 两个真实图像模型 + 一次真实图文/复核，最多 5 次生图
   （每次 1 张）与 2 次理解/复核、增量 ≤3 元；先预留、失败也计次、Unknown 不自动重提。
6. **R7.4 收口**：`refactor/completion-matrix-<ts>.md/json` 逐行适用项、无 missing/indirect/contradicted；
   PR 满足现有 CI/审查/分支保护后由代理合并并发布，发布后核对 HTTPS/静态/页面主链与最终指纹。

许可边界不变：C15/C17 需要真人到场（不适用项按 RC18 记录，模拟 E2E 不冒充）；
付费/上传/提交/部署/日落各自设门。

## 7. 明确未成立 / 未做（不得声称）

- C15/C17 独立真人走查未发生；模拟 E2E 不替代。
- 真实 Docker/TLS/HTTPS 发布、回退轨迹与同 origin 数据恢复：本机无 Docker 守护进程，未执行发布。
- V1 清理、删后两轮、最终完成矩阵、真实模型补证：未执行。
- RC19（Windows 回环间歇）**根因仍未定**：本轮只是把一类症状（死端口被代理伪装成 502）从
  诊断链上移除，并对 harness 页载入卡住加了传输签名重试 + 留痕；不得据此声称间歇已根治。
- 本轮未提交/未推送/未部署/未付费。

## 8. 恢复点与文件

- 进度权威：`_working/amz-listing-kit-product-v2/state.md`（已写入本轮条目；仍 V2.R5.1）。
- 冷恢复：`uv run --locked python tools/refactor_resume.py`。
- 本报告：`evals/product-v2/refactor/packet11-convergence-20261008.md`。
- 本轮定稿的产品改动：`app/product_v2/workspace.js`（设置订阅只落盘草稿、不在能力就绪前派生）。
- 本轮定稿的验证侧改动：`tools/v2_verify_shared.py`（回环 no_proxy + `read_suite` 诊断/传输签名重试）、
  `tools/verify_v2_ui_2_interaction_visual.py`（`STORAGE_DUMP`/`storage_diff`/`WRITE_TRACE` 与 UI2-17 留痕）、
  `tools/verify_v2_4_2_generation_attempt.py`（同端口重启 + `-20` 原始载荷证据）、
  `tools/verify_v2_1_4_formal_entry.py`、`tools/verify_v2_2_3_intake_understanding.py`、
  `tools/verify_v2_5_2_vlm_review.py`、`tools/verify_v2_6_1_selection.py`（悬挂引用）。
- 工作树里同批但更早定稿的改动（未提交，本轮已复跑验证）：3_5/4_4/5_3/8设置验证器、
  `generation.ts/.js` 与 `ui/generation-view.ts/.js`、`app/product_v2_server.py`、
  `tools/release_transaction_probe.py`、`.github/workflows/ci-cd.yml`（源码钉→行为证据）、
  `docs/`、`AGENTS.md`、`README.md`。
- 一次性探针（本地，忽略入库）：`_working/p11fix/_probe_*.py`；同套件重复判定的中途证据在
  `_working/p11fix/scratch/`。
- 全部改动**未提交、未推送**（工作树 27 个已跟踪文件为 M，另有既有未跟踪快照目录）。
