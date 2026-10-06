# 正式开发：人工纵向主链与首批 TS 产物

> NOT-AUTHORITY: point-in-time evidence。目标/任务仍看产品计划，当前恢复点只看 state；本文不宣布完整 Goal、R7.5、图文能力或发布完成。

## 实际交付

- `app/product_v2/generation.js` 的 `confirmAndRun` 统一保存生成授权并执行批次；`workspace.js` 的首次生成和返工都切换至该入口，UI 不再另走保存授权/开始批次的旧路径。
- 修复受控 A→B 项目切换下的旧回调串扰：候选按原 Attempt/项目落库，原执行链和 flight 集合由回调持有，不清除 B 的进行中动作。`generation-isolation.test.mjs` 先失败、修复后通过；核对原项目候选动作/hash与新项目未被写入，而不是仅断言不抛异常。
- `domain/suite-review.js` 的依赖硬门只覆盖必需或已采用用途；未采用的可选尺寸草案不阻止主图交付，必需/已采用尺寸图仍被缺尺寸阻断。报告输入指纹包含 `dependency_scope=required_or_selected`，旧报告不能沿用新语义。`suite-dependency-scope.test.mjs` 覆盖正反边界。
- 交付 `manifest.json` 及 `checks.json` 的整套/每图增加真实 `ai_review` 投影；无 AI 调用为 `status=not_reviewed, reason=not_run, checked_at=null`，不伪装成 PASS/模型 Unknown。复用现有 `suiteReviewStatusOf`，没有放松确定性报告、采用与完整性门。
- `domain/attempt.ts` / `domain/config-export.ts` 是首批唯一手写源码，同名 JS 由现有锁定 TypeScript 编译。新增 `build:frontend` / `check:generated`；服务只提供生成 JS，TS/d.ts 返回 404，Docker 构建上下文排除 TS。编译器不进入生产运行时。README/context 已同步；session/model-settings/generation 的 TS 迁移仍在进行，不能把首批成功称为 R7.5 完成。
- 人工事实、结构化尺寸、按用途绑定与精确 Prompt 失效已有产品实现，未重复建设。四份过期 Node 孪生同步至当前浏览器行为合同；只改断言体的消费者行为，不重钉文案/实现名。

## 实际页面与字节证据

独立临时配置的 Chrome 无头，仅本地 fake provider，无付费、无系统键鼠。

1. 页面新建商品任务，上传已登记公开许可蜂蜜罐原图，人工确认核心事实，不发商品分析。
2. 选择主图/场景图及缺尺寸的可选尺寸草案；主图/场景图自动本地准备，同一发送摘要一次确认生成两个候选。
3. 页面打开比较、人工采用；主图就地返工，原主图采用和无关场景图采用未改变；网络未出现自动商品分析/AI 复核。
4. 未采用尺寸草案最初错误阻断整套交付；上述依赖范围修复后，运行真实本地确定性报告，无 AI 复核生成交付与完整项目包。
5. 管理浏览器的下载等待没有证明 native 下载成功，未把 blob 捕获当 native 下载。随后全新临时 Chrome 配置导入实际项目包，点击列表打开项目，在正式页面实际完成两类 native 下载。
6. 交付 ZIP：31,117 bytes，5 members；项目 ZIP：2,369,839 bytes，50 members。无 page errors。截图、原包、下载及 JSON 在 `_stage-amz-control/formal-development-20261005/`。
7. 对下载包逐项核对：主图原采用候选 `act-144e4fba7b214ffdadecf9453e7b02ad` 的 SHA256 为 `9d34b3e53e06250b60c06248c7848383e5771867b8c8f3954156679d9e8e4cd5`；场景候选 `act-73499842a25441c6be9a3f48d9205923` 为 `63aac5275511fba00cb93ebe33369fe462256f3a175d7f5fda31d389f3fd0467`。二者字节长度/hash 与清单一致。
8. 项目包导入后再导出：源包 44 份文档按 kind/id/version 逐份 JSON 相等，全部 4 个资产逐字节相等且 SHA256 正确，仅多 1 份本次交付 export_record。manifest/checks 整套及每图均如实 not_run。原始核对结果：`_stage-amz-control/formal-development-20261005/zip-integrity.json`。

## 本批实跑与失败记录

- `npm run build:frontend`：实际生成两个 TS 对应 JS。
- `npm run check:types` / `check:generated` / `check:versions`：通过。覆盖仅 jsconfig 明确登记 TS 和已 opt-in 的 JS；未检查的依赖 JS 不宣称有类型保障，已迁 Interface 的调用方检查尚须后续完成。
- 仅运行直接受影响 Node 文件：attempt、config-export、suite-plan、suite-editor、prompt、prompt-edit、generation-isolation、suite-dependency-scope。71 条通过；未运行本轮最终两轮完整回归。
- `uv run --locked python app/server.py --check`：42/42，通过；实际 TS/d.ts 404、生成 JS 200。
- `package-smoke.py` 最初把导入误当自动打开而超时；按真实列表“打开”交互修正后通过。
- 新增 manifest 投影后的第一次下载超时；发现缺少 `suiteReviewStatusOf` 导入并补齐，之后同一路径 native 下载通过。失败原输出保留于会话工具产物 `artifact://926`，不把后来绿样本抹成无失败。
- Python Eval 后端不可用；字节核对改用已锁定 uv 的原生 Python 子进程，实际 exit=0。不是产品故障。

## 范围与准确下一步

上述 fake 候选只证明离线流程/保存/hash/交付，不证明真实图像质量、两供应商本轮补证、真人走查或线上发布。R6.1 人工部分可用；图文实际能力、原资料快照/迟到结果隔离仍需闭合，整项不能 done。R6.2/R6.3 的人工交付路径成立，完整设置/恢复/视口/键盘验收仍未全部成立。R7.5 后续 session/model-settings/generation 正在迁移且尚未集成检查；R7.1 最终回归与 R7.4 发布保持未完成。

继续：完成正在迁移的 Module 及实际消费者检查；复用现有人工项目闭合图文辅助的原快照/迟到回调，再按计划最终集成。保持原预算账本，未执行新增付费、Git 提交/推送/PR 或发布。

## 集成续接：失败保留与当前证明边界

- 串行集成检查保留两个失败：V2.2.3 分析后点击隐藏的理解区控件超时；UI3-16 的真实错误摘要缺少重试策略。当前 UI 合同 §2.6/§3 明确异步结果不自动导航，因此没有用自动切阶段迎合旧验证器。
- V2.2.3 改为用户显式导航至理解区；`v2.2.3-intake-understanding-20261005-205150-r75fix2.txt` 实跑全过。分析失败摘要补齐策略、Unknown 保留不自动重试；此前失败证据与后续结果分别保留，不把旧失败擦成绿色。
- Node 域孪生本轮先出现 219/226、7 条失败；已按当前消费者合同处理候选批次夹具、合法旧采用和复核超限，不改变产品来迎合旧断言。后续 226/226 是领域行为范围，不证明页面、真实模型或最终两轮回归。
- `generation.ts` 首次纳入检查时出现 4 个类型诊断：复核条目的 null/undefined 边界及未迁确认函数的 JS 推断签名。对应修正后一次 `npm run check:types` 零诊断；生成 JS 尚待统一编译及实际页面验证。
- 对实际调用方单独开启严格检查的测量发现 `app.js` 140 个、`workspace.js` 1121 个诊断；原绿色类型检查未覆盖这两个调用方。正按既有 JS 添加严格检查与具体类型，不机械改名或宣称全仓 TS；R7.5 仍未完成。
- 本机 `docker version` 有 CLI、无可连接的 Linux daemon；`tools/release_transaction_probe.py --selftest` 实际返回 exit 2，ST-01 `missing_prereq: docker info failed`。这不是回退已通过；未启动可见 Docker Desktop，后续须在已批准的具备 Docker 的运行通道证明事务。
- 真实图文调用前只核对公开准入：阿里云 [qwen-vl-max 官方模型页](https://help.aliyun.com/en/model-studio/qwen-vl-max) 给出北京输入 1.6 元/百万 token、输出 4 元/百万 token，最大输入 129024、最大输出 8192；当前 Adapter `max_tokens=5000`。按全输入上界及当前输出上界计算为 0.2264384 元，后续可用 0.23 元保守预留；本次尚未预留或发起付费调用。
- [蜂蜜罐来源页](https://commons.wikimedia.org/wiki/File:Antique_Glass_Honey_Jar_With_Rusted_Metal_Cap_(31009798197).jpg) 本轮重新核对为 Cindy Shebley / CC BY 2.0。实际发送候选素材是已保存 3840×2560 缩略图，SHA256 `c024b7cf2b04d39601a5146664879a5aff8d3fe4cb98b4990bda4c3ae6594461`；不是 5575×3717 的原站文件，记录来源和缩略版本，不冒称原站原始字节。Adapter 必须发送这份用户上传素材的真实字节，不以元数据代替看图。
- 历史启动/重开失败仍缺现象—机制归因，原日志只证明重开列表行数为 0；已知 readiness/读取恢复修复与后续绿色不自动关闭 RC19。保持发布门，不自行接受风险。

## 集成续接：编译、可选同步标志与真实缩放

- `build:frontend` 与 `check:generated` 已实际生成/核对六个 TS Module（attempt、config-export、semantic-analysis、session、model-settings、generation）；调用方 app/workspace 的严格检查仍在集成，不宣称 R7.5 完成。
- `v2.5.1-deterministic-review-20261005-212409-r75-c09.json` 保留 B04/B05/B09 失败。根因不是夹具：TS 迁移新守卫要求冻结身份必须写 `sync`，而原实现和合法已存记录允许缺省，缺省即异步；新守卫误判为无身份，已有 task 进不了核对队列。
- 修复 `AttemptExecutionIdentity.sync` 为可选，运行时守卫接受未声明/布尔值；不补造旧身份，也不修改上述失败夹具。编译后同浏览器入口 `v2.5.1-deterministic-review-20261005-212647-r75-optional-sync-fix.json` 全过，包含原失败批次用例、实际候选保存及报告刷新恢复。
- 原先受旧设计约束的 UI2 检查按冻结 UI 合同重基线，`v2.ui.2-interaction-visual-20261005-211310r75prebuild-green.txt/json` 22/22。阶段入口可达不授权业务动作，异步完成后由用户导航；既有键盘/视觉/IDB/错误检查保留，不靠恢复阶段锁或自动导航迎合旧验证器。
- Chrome 默认缩放通过独立临时配置的 `partition.default_zoom_level` 设置，启动参数明确 `--headless=new` 与实际窗口尺寸；125%/1440×900 实测 outer 1440×900、inner 1133×641、DPR 1.25；200%/1366×900 实测 outer 1366×900、inner 671×400、DPR 2。两者 `visualScale=1`、CSS zoom=1、transform=none，不以 CSS 或缩窗口冒充浏览器缩放。
- 在上述两种真实浏览器缩放中，页面导入现有同版本项目、列表打开、native 下载两类 ZIP 均成功，无横向溢出或 page error；200% 下另由 Enter 导航至交付。编译生成 Module 后再次在 200% 页面完成导入、打开和 native 下载，仍为交付 31,117 bytes/5 members、项目 2,369,839 bytes/50 members。截图与下载在 `_stage-amz-control/formal-development-20261005/zoom125-1440-*` 和 `zoom200-1366-*`；证明交互/字节，不证明 fake 候选质量或真人验收。
- 暂存准备中一次浏览器工具调用未明确 headless，进程参数显示缺 `--headless`，发现后关闭并确认进程已退出；该次不计入验收，后续明确验证 `--headless=new`。首次 Playwright 缩放 smoke 采用默认 1280×720 窗口导致尺寸断言失败，改为 `no_viewport=True` 后再验实际 outer/inner；保留失败，不把启动方式或工具窗口默认值当产品缩放缺陷。
- 实现说明的事前原字节快照为 `_stage-amz-control/r75-integration-docs-20261005/`。事前 SHA256：AGENTS `5491c20f592d9c470c154e4d6a8b5152d895de9d64620b1f3223b788d1869eb7`；README `c695de6fb2370ec13a9e85867b19297c8ca1e67053224665baadefe490c7c651`；context `b69f38a1b52b1132aafffb76bc9d4df512512f2e5133ca20a13290dcb744d12e`；state `813cd9a4292070145eb36e359c797e9b93c0b471ba0e929a668693563a453e0b`。本次更新只同步已有产品/编译行为和限制，不改 Goal、预算、真人门或发布准出规则。

## 集成续接：真实看图、载荷边界与拦截异常

- 实际页面第一次看图请求在网关出网前被拒：原理解路由仍按文字请求的 256KiB 限制读取正文，合法的 2,239,735 bytes JPEG 经 base64 后超限。`vision-ui-gateway-body-rejected-no-send.json` 保留失败；该拒绝发生在构造/调用模型之前，不以后来发现有缺口的 SDK 计数器证明零外呼。
- `app/product_v2_server.py` 的理解路由现按现有三张×4MiB 图片的 base64 上界加原文字元数据余量读取；没有改变单图/合计/张数/哈希合同。正式入口原自检新增消费者边界：合法大图成功、身份哈希不符和单图超限均在模型调用前拒绝；原输运超限检查改为真实新边界及响应 details。`uv run --locked python app/server.py --check` 实跑 45/45，输出 `artifact://1210`。
- 首次“离线”SDK 回放存在验证脚本错误：只拦截 `httpx.Client.send`，实际默认客户端由 `httpx2` 派发；虚拟 key 请求返回供应商 401/`PROVIDER_AUTH_FAILED`。原脚本 `model_calls=0` 不可信，该轮不是离线通过。失败完整保留在 `vision-ui-offline-isolation-failed-401.json`；账本保守计一次 SDK 调用并保留 0.23 元未结算预留，不宣称未计费或借重新跑绿抹去异常。
- 修正临时 smoke 的实际 `httpx2` 派发拦截，并在调用前检查 SDK 客户端确实受同一单次守卫控制。同一完整图片通过无联网 SDK 回放：`vision-ui-offline.json` 为 `offline_body_limit_ui_smoke`、真实模型调用 0；这里只证明传输/解析/保存，不证明图片理解质量。
- 随后由真实页面选择 `qwen-vl-max`、提供当前标签页 BYOK、上传登记许可素材，明确发出一次看图理解。实际 SDK 请求携带原上传 JPEG 的 2,239,735 bytes 和完整 SHA256 `c024b7cf2b04d39601a5146664879a5aff8d3fe4cb98b4990bda4c3ae6594461`；供应商/网关均 200、单次调用、无 page error。`vision-ui-live.json/png` 记录真实页面及请求。12 个模型槽位均为 proposed/model_inference，没有自动确认；截图显示模型提案、逐槽位确认和仍缺的结构化尺寸。
- 真实理解项目 ID 为 `e80ddebc-0b34-4079-a34b-6758ac891e55`。最后一版 semantic_analysis 为 version=3、succeeded/applied；原资料 version=2 的完整 payload/fingerprint 包含上述完整资产 hash。模型 evidence 展示使用哈希短标签，原资料快照保留完整身份，不把短标签当完整 hash。该脚本关闭临时 profile 前只保存理解阶段 JSON 投影和截图，没有 native 导出此项目；因此不能把这一成功宣称为 §14.9 完整图文辅助任务或其 ZIP 往返通过。
- 供应商返回 prompt_tokens=2549、completion_tokens=1479；按本轮已核官方价格估算 0.0099944 元，不是账单确认。成功调用的 0.23 元预留和 401 异常的 0.23 元预留均未释放。账本现保守计生图 8、语义/VLM 5、合计 13；本轮补充调用 2/3，增量预留 0.46/1 元，累计预算占用 1.61/5 元，既往 spent_cny=1.15 不清零。
- 另一次调用前页面 create-project 持续 disabled、没有模型请求；`vision-ui-transient-startup-disabled.json` 仅保留断言位置与当时零请求，未取得该失败的 UI 阶段轨迹。后来可用样本不解释这次失败，也不关闭历史 RC19；仍按 §7.6查证现象—机制。
- App 严格调用方检查已由该切片交付零本文件诊断。实际页面复现活动项目改名错误 `workspace is not defined`：名称已落库但页面报错；源码改由 Session 更新当前项目元数据，保留项目/generation，不重开工作区。Session 新方法尚待统一编译后同页面重验；workspace 严格调用方切片与发布事务切片仍未集成，完整 Goal/最终两轮回归/发布均未完成。

本节 `vision-ui-*` 相对路径均位于 `_stage-amz-control/formal-development-20261005/`；预算唯一在 `_working/amz-listing-kit-product-v2/budget-ledger.json`，不据本报告再次发起付费调用。

## 2026-10-06：当前 Goal 与结构重构合并执行

- 用户明确要求“我要你同时完成goal和重构”。实际系统工具先返回 paused，再执行 resume 返回 active；随后原生 get 的ID仍为 `1599c9600ae01cb7`，objective 与计划§2.1逐字一致。新观察为 `goal-observation-20261006-combined-refactor.json`；不创建新Goal、不改原文、额度、V1外部门或最终验收。
- 事前保存483份代码、配置、规约、既有行为夹具及两类代表ZIP的原字节，路径 `_stage-amz-control/combined-refactor-2026-10-05T18-44-47-076Z/`，逐文件bytes/SHA256见该目录 `snapshot-manifest.json`。本轮动作前仓库为main，已有113个修改/92个未跟踪项；它们不是本轮新造或可直接清除的文件。
- 独立临时Chrome进程明确 `--headless=new`，实际页面导入既有 `project-source.zip`、列表打开，在交付区原生下载当前完整项目包2364581 bytes，page errors为空。资料/候选可恢复成立；交付门显示“缺少必需选择：主图·干净背景”，尽管对应行显示已采用，因此不宣称当前完整交付通过、不跳硬门。原生包保存在 `_stage-amz-control/combined-refactor-downloads/`。
- 结构施工按计划§15.4承接：工作台职责/状态/执行Interface、稳定行为验证与隔离夹具、历史入口与生产依赖收敛。各片施工中不运行回归；整合后统一编译/相关行为与实际路径，原最终两轮和工程发布门仍保留。工程前沿R5.1尚未done。
- 发布静态判据的独立真实TLS smoke：原快照 `check_static` 在8419876-byte合法大页面返回1；当前完整读取后判断返回0；缺 `entry.js`、缺业务外壳分别返回1。原逻辑的 `curl | grep -q` 在pipefail下提前断管会拒绝正常响应；修复不跳过TLS、不放松缺资源判据。证据 `_stage-amz-control/combined-refactor/release-static-smoke.json`，临时脚本/私钥/服务均已清除。这只证明静态消费者，不证明Docker事务或用户旧启动缺陷根因。
- 上述smoke首次全部返回1；已保留 `release-static-smoke-initial-environment-failure.json`。实际Git curl 8.12.1使用Schannel、不采用 `CURL_CA_BUNDLE`；改为对子进程真实curl明确 `--cacert` 后TLS探测返回0，才执行修复前后判据。未修改系统信任库、不用不安全TLS参数、不重跑产品回归洗绿；Linux Docker事务机制仍等待获批CI实证。

## 2026-10-06：按用户要求停工与收尾

- 最新指令是“停止当前工作，做好收尾准备”。已取消`FinishWorkspaceCutover`、`FinishVerificationCutover`；旧施工代理此前已停止。`combined-refactor-walkthrough`及资源清单中的八个本轮本地/无头浏览器服务均返回已停止。未用停工收尾继续产品实现、编译、回归、产品模型调用、提交或部署。
- 收尾只读系统Goal为active；没有自行标paused/completed/drop或创建新Goal。项目执行停工，V2.R5.1改blocked、保留原恢复前沿及历史证明范围；七项未完成会话任务全部blocked。只有用户明确恢复才可继续施工。
- 最近一次实际Chrome新建主链：项目已写入IndexedDB，但打开报` suiteReports is not defined `、工作区隐藏。此前仅移除重复常量声明并通过语法检查，不是运行修复。原代理已迁出部分状态但旧读写/装配仍未闭合；续做代理已写`prompts.ts`、`authorization.ts`、`selection-adoption.ts`、`review-delivery.ts`，停工前尚未完成调用迁移、生成JS或实际重验。当前工作树是保留的中间态，不可算重构完成或可发布。
- 验证切片保留已落盘的共享夹具、`check_project_state.py`隔离root及`verify_v2_4_1_image_gateway.py`隔离修改；迁移未整体闭合，仍须核对共享名称、整份验证器互相导入、源码钉/浅回声行、实际状态隔离以及live脚本单次提交安全。没有执行本轮最终两轮，不得把删除旧钉或临时文件存在当行为通过。
- 历史入口已拆至本地`app/offline_fixture.py`，默认V2、显式V1、冻结离线fixture及doctor在停工前实际运行；V2最初44/45失败为首页title/脚本源码钉，删除后45/45，V1/fixture检查与更新doctor亦通过（原输出`artifact://1634`、`artifact://1636`）。这些是各自限定路径，不是新工作台或全Goal通过。生产Docker依赖闭包仍待真实CI。
- 发布静态TLS修复的限定证据见上节；随后已把实际运行文件与源树、不可变应用镜像ID、受服Caddy配置hash核对移到finalize清理previous之前，并纳入回退条件。最新workflow尚未重新解析或实际CI执行。事务自检的old/new标签仍取同一正式镜像，不能当不同版本恢复证明；实际旧版页面恢复仍未证。旧启动/重开RC19亦未闭合。
- 保存现场而非回滚、清库或提交；原483文件事前快照、两类已有ZIP和所有失败保留。详细续接文档写在OS临时目录`%TEMP%/amz-listing-kit-stop-handoff-20261006T020610Z.md`，不复制目标/任务表、不保存秘密。未再运行守卫；恢复时须按实际当前文件和保留失败闭合迁移，不因系统Goal仍active自动启动。
