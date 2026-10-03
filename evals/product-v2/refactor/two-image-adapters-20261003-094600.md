# V2.R5.2 · 第二真实图片 Adapter（火山方舟 flash，同步协议）— 工作证据

> CONTROL-STATUS: current · NOT-AUTHORITY（时间点证据；真实付费链缺口继续保留）
> Goal：docs/product-v2-refactor-plan.md §2.1（sha256=3f9f1842d67d063f…）。本卡片按 §12.3
> 「协议 / R5.2」执行：保留 DashScope 三段链；第二协议是同步——即时图片结果归正，不伪造 task id。
> 日期：2026-10-03

## 1. 交付内容（唯一事实来源：仓库）

### 新文件 `src/providers/v2_volcengine_image.py`
- 官方同步接口：`POST {base}/images/generations`；`model=doubao-seedream-5-0-flash-260915`；
  参考图以 `data:image/<png|jpeg>;base64,…` 传 `image[]`；`size` 用 `W*H→WxH`；
  `response_format=b64_json`、`output_format=png`、`watermark=false`。
- 结果一次拿全：成功返回 `ImageTaskResult(task_id=None, status="SUCCEEDED",
  sync_result=(bytes,"image/png"), result_count=1, request_id=…)`；`to_dict()` 输出
  `sync=true` 且不含字节——字节只随本次提交信封回浏览器。
- 错误语义全部走 `v2_errors` 词表（§9）：
  - 429 → `provider_failed/UPSTREAM_RATE_LIMITED/retryable`（未受理，可重试）；
  - 欠费码（Arrearage/Arrears/Overdue）→ `provider_failed/UPSTREAM_ACCOUNT_ARREARS/retryable`；
  - 其他 4xx → `provider_failed/UPSTREAM_REJECTED/fatal`；5xx → `provider_unknown/
    UPSTREAM_OUTCOME_UNKNOWN/requires_review`（结果未知，绝不自动重提）；
  - 超时/连接中断 → `provider_unknown/PROVIDER_OUTCOME_UNKNOWN/requires_review`；
  - 内容安全空结果 → `provider_failed/UPSTREAM_EMPTY_RESULT/fatal`；
  - 字节非 PNG → `provider_failed/RESULT_IMAGE_INVALID/fatal`。
- 无效路由公正拒绝：`status()` / `result()` 对同步协议抛
  `provider_unknown/SYNC_TASK_ID_REQUIRED/requires_review`（不存在可核对的 task id；
  浏览器也不会走到这两条）。
- 端点只认 `https://…volces.com`（`_safe_base_url`）；身份/凭据走
  `v2_credentials.resolve_credentials`（ARK_API_KEY；默认档 fail-closed，AMZ_V2_DEFAULT_TRIAL）；
  BYOK 走 `apply_credentials`。出站白名单复用 `v2_outbound.DEFAULT_ALLOWED_HOSTS`
  （= aliyuncs.com + volces.com）。
- 建网不联网：`create_default_volcengine_image_provider` 按注册表口径装配（构造不发请求）。

### 能力档与域合同（DOM 一致）
- `IMAGES_CAPABILITY_VERSION` 2 → 3（图像网关能力块内容变化：新增同步协议标志与第二真实协议）。
- `v2_image.ImageTaskResult.to_dict()` 增加 `sync`（只在同步协议为 true）。
- `domain/attempt.js`：
  - `attemptCurrentEnvironmentIdentity` 从 `provider.capabilities.sync_tasks === true` 投影
    `sync`（这是服务端 capabilities 块的真实形状；误读外层键会把同步识别成异步）；
  - `attemptExecutionIdentityFromEnvironment` 与 `buildAttemptRecord` 冻结
    `execution_identity.sync`（缺席 = false，向后兼容旧 schema 2 记录，无迁移）；
  - `classifySubmitEnvelope` 认「task_id 为空 + task.sync=true + 明确状态」为同步终态：
    SUCCEEDED / FAILED / CANCELED / 其他→unknown；不带 sync 标志的空 task 成功仍是
    unknown（SUBMIT_NO_TASK_ID，反向语义不变）。
- `domain/candidate.js`：
  - `candidateStoreDecision`：succeeded + 冻结 `sync===true` 允许 task_id 为空入库；
    其他空 task 维持 `no_task_id`；
  - `buildCandidateRecord` / `checkCandidateRecord`：候选新增 `sync` 布尔键；同步候选合法形状
    = `task_id:null + sync:true`；异步候选固定 `sync:false`（旧记录键缺席按 false 读，
    无 schema 版位变化，包迁移零改动）；
  - `candidateMatchesAttempt` 以 `Boolean(record.sync)` 对齐来源 attempt。
- `generation.js`（生成执行 Module，R5.1 收敛口）：
  - 提交成功且信封带 `image_base64`：解码为 ArrayBuffer，登记进 `pendingSyncBytes`
    （action_id → {buffer, expectSha}，进程内存，不落盘、不进日志），随后
    `ensureCandidateStored` 取走即删，并用 sha256Hex 独立复核 expectSha；
    hash 不一致 → 不保存任何候选（`sync_sha_mismatch`），记录保持原样。
  - `pickSyncOrFetchResultBytes`：同步记录（task_id 空 + sync 冻结）只从内存面取字节；
    刷新/关页后 map 必空 → `sync_bytes_missing` 失败 + 明确补救指引（人工核对现有结论，
    显式新建 action），绝不伪造字节、绝不按假 task 重取。异步记录照旧走 result 路由。
  - batch（V2.4.4 链）不变：fetch 步骤对同步与异步共用同一保存入口。

### 注册表与配置
- `v2_registry.create_image_provider` 增加 `v2_volcengine_image` 分支；
  `config/product-v2/providers.json` 新增 `volcengine-ark` entry（role=image，
  `ARK_API_KEY` / `AMZ_V2_ARK_BASE_URL` / `AMZ_V2_ARK_TIMEOUT`，capabilities 含
  `sync_tasks:true`、`test_double:false`、`stateless:true`）。
- `.env.example` 记录火山端点 / 密钥 / 超时 / provider 选择（默认档仍 fail-closed）。

## 2. 验证证据（本仓库在线检查，全部可重跑）
- 工具：`tools/verify_v2_r5_2_two_adapters.py`（0 次真实模型调用）——
  报告 `evals/product-v2/PRODUCT-V2-R5.2-offline-e2e-20261003-094235.json`（42/42 通过），
  截图 `PRODUCT-V2-R5.2-batch-20261003-094246.png`、`PRODUCT-V2-R5.2-refresh-20261003-094249.png`。
  覆盖：node 语法门；node 镜像域套件（预存 C09 失败点名保留）；U01–U20（注入 transport 的
  适配器单元：请求形状 / 成功字节 / request_id / 429 / 欠费 / 4xx / 5xx / 超时 / 空数据 /
  非 PNG / status+result 拒绝 / fail-closed / 出站白名单 / BYOK / 注册表装配）；
  G01–G08（Python 网关层：capabilities→volcengine-ark+cap_v3；提交→200 信封 task_id=null+
  sync=true+字节 sha 复核+恰好 1 次外呼；status→provider_unknown SYNC_TASK_ID_REQUIRED；
  能力版本 2 冻结漂移→400 EXECUTION_IDENTITY_MISMATCH 且不转发；非法协议 target→400）；
  E01–E08（真实 Chromium e2e：seed→套图→编译→确认→`#batch-run`→4 张全部 succeeded、
  恰好 4 次 transport 提交且 0 次 status 外呼、每图候选入库且 asset sha256 与字节一致、
  UI 显示「候选已保存到本地」、刷新后 4 记录+4 候选仍在、显式新建 action 第 5 次提交仍成功、
  fresh module 缺字节 → `sync_bytes_missing` 明确补救、结束后调用数恰 5）。
- 契约：`evals/product-v2/harness/attempt-contract.js` 新增 A18 同步投影子案 + A19
  （task_id 为空的同步成功可入库、非同步形状维持拒绝、SUCCEEDED/FAILED/unknown 分类）；
  node 镜像 `evals/product-v2/node/attempt-contract.test.mjs` 同步新增（现 222 pass）。
- 守卫：`tools/check_project_state.py`、`tools/check_docs.py --no-run`、
  `tools/check_verification.py`（44 入口 / 40 CI 模式）全过；verification.json 注册
  `tools/verify_v2_r5_2_two_adapters.py`（category browser, ci true）；CI 作业接线同命令。

### 异步批次回归修复（2026-10-03 10:56，本机时间）

- 失败证据：`evals/product-v2/v2.4.3-batch-suite-20261003-105401-r52-diagnosis.json`。
  捕获到首张已成功但候选未保存，仅一次提交/核对，页面明确显示
  `批次已停止新增提交（isNonEmptyString is not defined）`。不是超时长度或确认失效；
  新同步/异步字节分流调用领域 helper 时漏了导入，异步候选保存抛错中断批次。
- 修复：`app/product_v2/generation.js` 从已有领域入口导入 `isNonEmptyString`；
  未改轮询超时、确认规则、Unknown 或提交身份。占位 `submit_lock` 和临时采集已移除。
- 原始异步消费者验证：
  `evals/product-v2/v2.4.3-batch-suite-20261003-105608-r52-helper-fix.json` 全部检查通过，
  包括逐张提交、部分失败隔离、重试保留历史、Unknown 不重提、停止、刷新及继续生成，
  最终 10 张全部成功。沿用已有浏览器回归作回归判据，没有新增框架。
- 同步消费者验证：
  `evals/product-v2/PRODUCT-V2-R5.2-offline-e2e-20261003-105608.json` 专项检查通过；
  4 张批次候选落库、刷新仍在、显式新 action、缺一次性字节的补救均通过。
  该工具仍豁免已记录的 Node C09 失败（222 pass / 1 fail），**不代表全域回归全绿**。
- 两次验证都是本机服务与假上游，真实模型调用 0、外部网络调用 0。R5.2 的离线实现
  有上述证据，真实证明未闭合；依计划 §12.4 修正 state 中过早的 `done` 为 `blocked`，
  保留 R5.3 为下一项可达工程任务。
- state 变更前快照：
  `_stage-amz-control/r52-helper-fix-20261003/state.md`；
  SHA256 前 `dd4e6c47e43c4636d03c812fff03b64f2a6a1cd4e6b46098a5b6b0a38ecb6825`，
  后 `937fe3b74a900c09fb81dd7c492a8070e89b0a9214717c750ca557dccba5bcd5`。


## 3. 边界与如实保留的缺口
- 本证据是离线消费者行为；真实付费链（R4.2/R7.1/R5.2 真实证明）未执行：无真实参考图生成的
  费用与模型侧结果，不宣称 RC09 已证。
- 侧位注明：`node --test` 中 C09（batch 候选投影 fetch 竞态）在本次改动前就失败
  （2026-10-03 基线 201 pass/2 fail）；属 R5.1/R6.x 待查缺陷，不因本卡重跑掩盖或洗绿。
- `verify_v2_1_2` 的 flake 与启动间歇缺陷仍未定位；不因本卡改变状态。
- 未提交、不部署；- env.example 只是模板。

## 4. 下一步（继续按计划顺序）
- V2.R5.3（能力驱动 Prompt/确认一致性）以两 Adapter 有效能力为输入推进离线部分；
  R5.2 真实付费证明与 R4.2/R7.1 共用获批运行环境后执行。
