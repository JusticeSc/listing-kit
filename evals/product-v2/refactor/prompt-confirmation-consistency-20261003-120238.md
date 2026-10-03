# V2.R5.3 · Prompt/确认/能力一致 — 工作证据

> CONTROL-STATUS: current · NOT-AUTHORITY（时间点证据；真实付费链缺口继续保留，见 §5）
> Goal：docs/product-v2-refactor-plan.md §2.1（sha256=3f9f1842d67d063fa9d8cfbbaf60eb5971fe24b46502c97455241ccac40d4607）
> 日期：2026-10-03；报告戳：20261003-120238（与统一验证报告同戳）

## 1. 交付内容（唯一事实来源：仓库 diff）

- `app/product_v2/domain/prompt.js`：删除 `PROVIDER_PROFILES`（无别名、无 shim，全调用方已迁移，`grep PROVIDER_PROFILES` 零命中）。
  新增 `imagePromptProfile(images)`（capabilities.images → 平铺非秘密档：目标 + 协议 + 15 请求字段；
  版本取 `provider.capability_version`，协议取 `images.contract`，参数取 `capabilities.request_profile`；
  缺字段即 `CONTRACT_INVALID`，不猜参数、不查模型表、不读凭据字段）。
  新增 `checkImagePromptProfile / assertImagePromptProfile / sizeScopeProblem / MAX_REFERENCE_SELECTION=3 /
  IMAGE_PROFILE_FIELDS / IMAGE_PROFILE_VERSION_PATTERN / IMAGE_SIZE_PATTERN`。
  `compilePrompt` 必需 `input.providerProfile`；`compiled.provider` 与 `basis.provider` 冻结完整档；
  `provider_contract` 段按有效 `size/format` 输出（不再硬编码"方形"）。
  `requestSnapshotOf` 快照加 `output_format + target={provider_id,model_id,protocol,capability_version}`；
  `promptStaleness` 比较目标/协议/版本/全部 15 请求字段，当前档缺字段即 stale，凭据轮换不 stale。
  `buildEditedPromptRecord` 按冻结档 `max_prompt_chars` 限长，不查模型表。
- `app/product_v2/domain/confirm.js`：`buildConfirmationSheet` 必需 `providerProfile`；
  `PROVIDER_MISMATCH` 按冻结档与当前档全文比对（参数，不只 model+version）；
  `sheet.provider/external_summary/confirmationSnapshot` 增 `output_format`（+`provider_id/protocol`）。
- Python 网关（`src/providers/v2_image.py` + 两真实 Adapter + fake + `app/product_v2_server.py`）：
  `image_request_profile()` 纯业务投影（qwen `min_area=512²`；flash 仅 `min_area=921600`，其余沿保守限制）；
  `profile_violation` 纯函数；网关 `_verify_request_profile` 在 `_verify_execution_target` 后、提交前执行，
  缺/不完整 profile 与能力外请求一律 `INPUT_INVALID/400`，不调用模型；`SubmitRequest` 冻结
  `n=1/prompt_extend=false/watermark=false/output_format=png`（缺省兼容旧直发）。
- 消费者迁移：harness `harness-api.js` + node `harness-core.mjs` 增固定 `IMAGE_PROMPT_PROFILE`
  纯领域 fixture（无模型调用）；prompt/confirm/prompt-edit/rework 两套件调用点全传 `providerProfile`；
  `config-export.test.mjs` 改本地字面量；`verify_v2_3_5/3_6` 页内探针改为从 `GET /api/v2/capabilities`
  经 `domain.imagePromptProfile` 实时投影（与页面编译同一档，不复制常量）。
- Node candidate C09 fixture 补 `schema_version: 2 + execution_identity`（与浏览器 harness 同形）；
  `verify_v2_r5_2_two_adapters.py` R52-01 恢复为"不豁免既有失败"口径。
- 有意删除的断言：主图 golden hash（`provider_contract` 文案随有效档合法变化，旧 hash 即失效，
  G01 改为结构/文案断言；全库 `grep GOLDEN_HASH` 零命中）。

## 2. JS/Python 合同对齐（实测，非推断）

- 15 键逐键一致：`size,n,prompt_extend,watermark,output_format,supports_negative_prompt_field,`
  `max_reference_images,reference_media_types,min_side,max_side,min_area,max_area,min_ratio,max_ratio,`
  `max_prompt_chars`（Python `image_request_profile()` 实测打印键序；JS `IMAGE_PROFILE_FIELDS` 同集合）。
- 面积下界：qwen/fake `262144`，flash `921600`；`1344*1344=1806336` 两档皆通过，
  `768*768=589824` 在 flash 档被拒（与网关 `R53-G01` 一致）。
- 秘密隔离：profile/快照/hash/target 全链无 `credential_source/configured/密钥` 字段；
  `profile_violation` 原因只含计数与参数名。

## 3. 验证证据（本仓库在线检查，全部可重跑，0 次真实模型调用）

- 统一验证器：`uv run --locked python tools/verify_v2_r5_2_two_adapters.py --label r53-parent-integration`
  → `evals/product-v2/PRODUCT-V2-R5.2-offline-e2e-20261003-120238.json`，**全绿、无 failed_ids**。
  关键项：`R53-G01..G03`（能力外 size/n/output_format 提交前 400 且 transport 不增加）；
  `R53-E01`（火山真实请求体与 Prompt 文本、hash、参考图 sha、冻结执行身份逐图一致）；
  `R53-E02`（纯凭据轮换：Prompt/确认保留、0 stale、0 新增外呼）；
  `R53-E03`（换模型目标：4 图全 stale、历史 Prompt/Attempt/候选保留、transport 仍为 5）；
  `R52-01`（node 镜像域套件零豁免通过，含修复后 C09）；`R52-02/03`（A01–A19 + 确认/编辑/套图回归）；
  `R52-E01..E08`（同步批次/刷新/显式新建/缺字节补救）；`R52-98/99`（入口 --check、零 console/page error）。
- Node 域套件：18 文件 `node --test` → **197 pass / 0 fail**（含 prompt G12、confirm H06 新增回归断言）。
- 守卫：`check_docs.py` 全过；`check_project_state.py` 全过；`refactor_resume.py` →
  `[PASS] 冷恢复：8 阶段 / 26 任务；状态 active；唯一下一动作 V2.R5.3`。

## 4. 验收对照（计划 §V2.R5.3）

- UI/记录/真实请求文本与 hash 一致 → `R53-E01` 通过。
- 不支持参数提交前明确拒绝 → `R53-G01..G03` 通过。
- 换模型/规格产生精确 stale → `R53-E03` + G12/H06 通过。
- 旧 Prompt 保留、不偷改 → `R53-E03`（`prompts/attempt_chains/candidates` 逐结构相等）通过。

## 5. 保留缺口（不属于本切片，勿视为完成）

- `V2.R4.2/R5.2` 真实付费证明：已认证 volcengine 运行时与预算捕获仍待同一工作台执行。
- 公共默认付费档保持关闭；`IMAGES_CAPABILITY_VERSION=3`；harness 固定 fixture `version: 1`
  仅为套件内自洽常量，页内探针以服务端实时能力为准。
