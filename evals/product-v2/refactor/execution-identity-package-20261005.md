# V2.R4.4 · 同版本执行身份/项目包合同（2026-10-05 设置接线后重判）

> CONTROL-STATUS: evidence · AUTHORITY: none（时点证据，不是规范）
> NOT-AUTHORITY: point-in-time verification evidence only。0 次真实模型调用、0 外部网络。
> 任务卡：`docs/product-v2-refactor-plan.md` §V2.R4.4；输出合同 = 计划 §V2.R4.4「输出」。
> 前置 V2.R4.3 已 done（`config-and-credential-20261005.md`）。历史 R4.4 证据保留原证明范围
> （`execution-identity-package-20261003-072854.md`），本报告只证明 R4.3 设置接线后的当前缺口已闭合。

## 1. 做了什么

- R4.3 把图像 provider 改名（`dashscope-image→dashscope-qwen-image`、`fake-image→fake-qwen-image`）
  并新增 vision 语义条目（`config/product-v2/providers.json`）。R4.4 重判确认：改名后无
  legacy 映射残留——冻结身份按当前 id 核对，旧 id 不被猜测（`attempt.js` 注释 + `package-schema.js`
  MIN=2 拒绝语义 + 服务端 `_verify_execution_target` 失配 400）。
- 工作树 identity 相关增量（`attempt.js` authorization 可选块、`attemptReconcileRequestOf` 凭据来源
  缺失显式 invalid、`attemptReconcileEnvironment` configured=false 视为缺凭据）与 R4.4 验收同向：
  不构造目标核对请求、不猜身份，只给明确恢复条件。
- 基线包核对：正式启动快照 `r44-current-project.zip`（172709B，sha256
  `ae7a55a3…d657540`，72 项）内 18 条 `generation_attempt` 的 payload 均为
  `schema_version=2` 且带完整 `execution_identity`（protocol `v2.4.1`、capability_version、
  credential_reference.source），满足当前 `MIN_PAYLOAD_SCHEMA_VERSIONS{generation_attempt:2}`；
  不触发旧格式整包拒绝（§2.3 拒绝路径由 Z11 覆盖，当前包不在此列）。

## 2. 证据（本轮 fresh，全部离线）

| 验证器 | 结果 | 证据 |
|---|---|---|
| 生成 Attempt V2.4.2（含 V2.4.2-19/19b 漂移恢复、V2.4.2-20 同 task 不同 target 400、V2.4.2-22 配置导出契约） | 26/26 passed | `evals/product-v2/v2.4.2-generation-attempt-20261005-184623.{json,txt,png}` |
| 网关 V2.4.1（含 BYOK/默认档 closed/出站白名单/磁盘不变量 V2.4.1-23） | 33/33 passed | `evals/product-v2/v2.4.1-image-gateway-20261005-184700.{json,txt}` |
| 项目包 V2.1.3（含 Z10 身份往返、Z11 旧格式原子拒绝、真实导出/导入逐项一致） | 8 checks passed，套件 Z04–Z11 全过 | `evals/product-v2/v2.1.3-project-package-20261005-184649.{json,txt}` |
| Node 合同（attempt/config-export/package） | 25/25 | 现场运行 |
| 正式入口 `--check` | 38/38 | 现场运行 |
| `check:types` | 0 error | 现场运行 |
| `check_docs --no-run` / `check_project_state` / `refactor_resume` | 全过，next=V2.R4.4 | 现场运行 |

## 3. 验收对照（计划 §V2.R4.4）

- 换设置后已提交 task 不走新目标：V2.4.2-19/19b（漂移阻塞 + 恢复后同 task 原身份核对成功）。
- 同 task 不同 target 不串：V2.4.2-20（mismatch 400 `EXECUTION_IDENTITY_MISMATCH`，一致放行）。
- 同版本包对象/hash/候选保持：V2.1.3-03/04/05 + Z10；基线包 payloadacher schema 2 带身份（本报告 §1）。
- 缺原 key 明确可恢复：V2.4.2-19 blocked_environment 恢复条件文案 + V2.4.1-31/32。
- 密钥轮换不使无关 Prompt 过期：V2.4.2-14（Prompt 陈旧度只看 Prompt 版本）。
- 配置导出区分可分享/需重给凭据：V2.4.2-22 + config-export 契约。
- 旧格式明确拒绝：Z11 + config-export 旧格式拒绝（拒绝路径仍有效，当前基线包不受影响）。

## 4. 已知未闭合（照实记录，不在本任务内）

- `npm run test:domain` 213 pass / 10 fail（G12/SL-06/07/08/10/11/R01/R06/R13/S06）：
  与 R4.3 报告记录的同一集合一致，为工作树既有 domain/harness 改动所致，与本轮 R4.4
  三件套（attempt/package/gateway）无因果关系；R4.4 相关 Node 合同 25/25 全过。
  归属后论证，不在本报告洗绿。
- 付费 PoC（R4.2 已 done，历史证据保留）、真实图文消费者（R6.1）、最终全用途（G6/RC07）、
  C15/C17 真人验收：均不在本轮，按计划后论证。
