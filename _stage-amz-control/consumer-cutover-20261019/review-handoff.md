"""第5批同包切换（schema 2/3）变更清单 —— 独立审查交接。

本轮切片：闭合「同包合同与出站消费」剩余项（计划 §13.8 一次切换的实装）。

## 变更范围（本切片新增）
Domain:
- app/product_v2/domain/frozen-reference.js（新文件，唯一冻结引用判据）：
  REFERENCE_USES / MAX_REFERENCE_SELECTION / checkFrozenReferences 自 prompt.js 原样上移；
  prompt.js 对外再导出（既有导入路径不变）；attempt 校验复用同一判据，不成环。
- app/product_v2/domain/shared.js：canonicalJson/canonicalize/isPositiveInteger 上移至此
  （prompt.js 停止再导出 canonicalJson，直接导入方 confirm.js/attempt.ts 已迁移）；
  CONFIRM_BLOCKER_CODES 词表上移至此（review.js 在模块初始化期读取，叶子常量不得反向依赖 confirm.js）。
- app/product_v2/domain/confirm.js：CONFIRM_SCHEMA_VERSION 1→2（旧记录 schema 1 保持只读可核）；
  确认单引用投影带完整 sha256 与 sources.asset_sha256；confirmationSnapshot 逐图带
  references（冻结引用全形状），删除逐图冗余 reference_roles；checkConfirmationRecord 按版本分支：
  schema 2 快照/记录引用经 checkFrozenReferences，记录逐图引用必须是指纹快照的展示投影
  （recordReferencesMatchSnapshot）；schema 1 维持原形状。
- app/product_v2/domain/attempt.ts：ATTEMPT_SCHEMA_VERSION 2→3；buildAttemptRecord 保存完整
  冻结元数据（attemptReferenceOf），checkAttemptRecord schema 3 走 checkFrozenReferences、
  schema ≤2 保留身份形状；attemptExecutionIdentityOf 接受 schema ≥2（在途旧任务原身份观察）。
- app/product_v2/domain/review.js：CONFIRM_BLOCKER_CODES 改从 shared.js 导入（打断初始化循环）。
- app/product_v2/storage/repository.js：reserveGenerationAttempt 参考图核对按 pending.schema_version
  分支：schema 3 与 Prompt 快照逐字比较；schema ≤2 保持身份投影比较（不改写历史）。
- app/product_v2/storage/package-schema.js：PAYLOAD_SCHEMA_VERSIONS 镜像同抬
  （generation_confirm 2、generation_attempt 3；MIN generation_attempt 3，旧包精确条目整包拒绝）。
- app/product_v2/prompts.ts：ConfirmationSheetShot.sources 类型补 asset_sha256（仅类型注记）。

Tests/verifiers（同判据更新，不重复固定旧措辞）:
- node/attempt-contract.test.mjs + harness/attempt-contract.js：夹具 frozenRefs；A02 增
  「参考图缺冻结元数据」反例；新增 A21（schema 3 保存完整元数据；schema 2 旧记录仍可机检；
  缺执行身份仍拒绝）。
- node/confirm-contract.test.mjs + harness/confirm-contract.js：H09 改为人读字段（statement/label）
  无完整 hash + 前缀与完整身份一致（对象内完整 sha256 是快照投影同源，界面只渲染前缀）。
- node/generation-isolation.test.mjs：mock sheet schema_version 2；attempt 夹具带冻结元数据。
- node/rework-contract.test.mjs：RW-16 期望来源含 asset_sha256。
- harness/package-contract.js：Z10 往返 attempt 用完整引用；harness/project-package-contract.js：
  P08 增加 schema 2 整包拒绝。
- tools/verify_v2_4_2_generation_attempt.py：V2.4.2-06 请求引用按 {role,sha256} 身份投影与记录比较；
- tools/verify_v2_r5_2_two_adapters.py：probe attempt 用完整引用；references 子句改全等比较，
  删除死掉的 identity_of；tools/verify_v2_5_3_compare_panel.py：probe attempt 用完整引用。

## 已运行验证（均离线，0 次真实模型调用）
- npm run check:types → 退出码 0
- npm run build:frontend → 退出码 0；dist/product-v2/domain/index.js 动态 import 正常
  （CONFIRM_BLOCKER_CODES.PROMPT_MISSING 可读；修复前该 barrel 初始化即抛错）
- npm run build:frontend-node → 退出码 0
- npm run test:domain → 277/277 通过
- verify_v2_4_2_generation_attempt.py：27/27
- verify_v2_3_5_pre_generation_confirm.py：13/13
- verify_v2_4_3_batch_execution.py：全过（含 B01–B09 + 契约回归）
- verify_v2_4_4_candidate_blob.py：全过
- verify_v2_5_4_rework_loop.py：全过
- verify_v2_6_3_project_transfer.py：全过（含 P01–P08）
- verify_v2_5_1_deterministic_review.py：全过
- verify_v2_2_1_product_contracts.py：全过
- verify_v2_r5_2_two_adapters.py：passed（offline E2E）
- verify_v2_5_3_compare_panel.py：全过（第一轮回归曾因本文件旧夹具 FAIL，已修复）
- verify_v2_7_1_regression.py 第一轮在 verify_v2_5_3 处停止（即上项），修复后需重跑两轮全绿。

## 审查关注点
1. 确认记录验证器新分支（recordReferencesMatchSnapshot）是否与冻结合同一致、是否过度/不足约束。
2. package MIN generation_attempt=3 的整包拒绝语义（§13.8 + 成功判据「不支持旧格式显式原子拒绝」）。
3. repository.reserve 双分支是否会在 schema 3 attempt × 旧 prompt 上正确冲突（fail-closed）。
4. review.js 阻断码改源的循环根因（dist barrel 初始化崩溃）修复是否完整、有无同类初始化读取残留。
5. 测试更新是否构成「re-pin 旧实现」——H09/RW-16/V2.4.2-06 均按新合同改写判据。
