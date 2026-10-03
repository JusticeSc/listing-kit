# V2.R5.1 · 生成执行 Module（单张/批量/返工统一执行路径）

> NOT-AUTHORITY: 点时证据，用于 V2.R5.1 切片；进度权威是 `_working/amz-listing-kit-product-v2/state.md`。

## 范围与结论

生成执行的业务顺序收敛到 `app/product_v2/generation.js`（`createGenerationModule`），
`app/product_v2/workspace.js` 只保留按钮入口并投影模块返回的核心结果：
对照 `attempt-contract.js` A06/A09 语义，提交失败/未知/Unknown 的 UI 只分类文案，
不自行改写持久化顺序或状态。

- 单张提交/核对：`performSubmitAttempt` / `performReconcileAttempt`。
- 整套批量与逐图进度：`deriveBatch` / `runBatch` / `runRetryOnce` / `stopBatch` / `reconcileOnce`。
- 候选与复核落库：`ensureCandidateStored`（幂等、hash 校验、24 MiB 护栏、配额失败不写半份）与
  `ensureReviewReport`（失败只提示不阻塞人工）。
- 会话/项目冻结：执行依赖 `deps.beginAction()` 提供冻结 action（含 projectId）与
  `action.alive()` 判据；模块内不持有会话状态。
- 整套返工：`runRetryOnce` 复用同一 `runBatch` 与同一条 Attempt 语义（不产生第二套执行路径）。

先持久化、再外发：pending_submit 记录（含冻结执行身份）在 submit 请求前写入 IndexedDB；
刷新/双击 → 只产生一条 Attempt、一次外发（V2.4.2-04/05）。

## 本切片改动（提交集中区）

- `app/product_v2/generation.js`
  - `attemptProviderIdentity()` 改读 `deps.environmentReader()`（workspace capabilities.images
    单一数据源）；删除模块内部 `imagesBlock` 第二副本与无人调用的 `setCapabilities`。
  - 删除未被调用的导出 `candidateChainsNow`、`reviewReportsReader`、`rememberAttempt`、
    `rememberCandidate` 的导出（函数保留内部使用）；保留 `attemptChainsNow`（UI 投影必需）。
- `app/product_v2/workspace.js` 与 `app/product_v2/session.js`：本切片未改（生成 Module 拆分
  与会话冻结动作在早前 R5.1 进行中工作已完成，本次仅修接线与回收死导出）。

## 运行验证（fake provider + 本机服务 + 真实 Chromium；0 真实模型调用、0 外网）

- 2026-10-03 08:46:47 `verify_v2_4_2_generation_attempt.py` → 全绿
  (`evals/product-v2/v2.4.2-generation-attempt-20261003-084647.json`)：
  提交前落库 pending_submit、双击单条、按 task 核对、刷新打断、Unknown 不自动重提、
  冻结身份漂移阻塞、服务重启恢复。
- 2026-10-03 08:47:05 `verify_v2_4_3_batch_execution.py` → 全绿
  (`evals/product-v2/v2.4.3-batch-suite-20261003-084705.json`)：
  整套批次逐张、部分失败不阻塞、重试留旧记录、停止只停新增、刷新恢复剩余、Unknown 分支。
- `_r51_slice_page.py`（A/B 项目迟到响应与跨项目隔离探针）→ ok；其 T:0 结论维持：
  A 的迟到响应只写入 A 链，B 的 UI 行与批次条不受污染。

## 验收对照（计划 §V2.R5.1）

| 判据 | 证据 |
|---|---|
| 双击/重入单条 Attempt | V2.4.2-05 |
| partial（单图失败不阻塞） | V2.4.3-05/06 |
| 停止新增 & 停止观察 ≠ 取消上游 | V2.4.3-09 |
| 刷新恢复身份 | V2.4.2-12、V2.4.3-10 |
| 超时/Unknown 不自动重提、显式新建 | V2.4.2-10/11、V2.4.3-07/08 |
| 服务重启恢复 | V2.4.2-09 |
| 配额/容量失败无半份记录 | `verify_v2_4_4_candidate_blob` 全绿（2026-10-03 08:51 `evals/product-v2/v2.4.4-candidate-blob-20261003-085109.json`；同轮修复 C09 fixture，使其代 R4.4 起必须带冻结执行身份的真实记录形状） |

## 边界与未知

- 停止语义（「停止观察不被当上游取消」）覆盖 fake 分支的提交阻断与已提交身份继续核对
  （V2.4.3-09）；429 计费型限流的真实重试语义属 R5.2 真实模型链时点证据，不在本切片。
- 本切片不含两真实协议接入与两模型真实证明（R5.2/R4.2）；`G4`/`G5`/`G6` 门与 RC 矩阵
  最终判定保持开放，不随本地 fake 绿色提前关闭。
- 交付 ZIP/manifest 修复（R6.3）不属本切片动作范围。

## Superseded 时点证据

早前 R5.1 in-flight 版本的失败/修复级联证据（08:34 attempt、08:34 batch、08:08 batch）仅作为
调查过程保留；它们不作为当前版本的行为结论，服从本文件「运行验证」最新时点记录。
