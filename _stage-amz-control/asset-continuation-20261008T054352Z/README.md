# amz-listing-kit

> CONTROL-STATUS: current · AUTHORITY: implemented-behavior
> 本文件只回答“当前代码实际能做什么、怎样启动和验证”。产品目标见
> [`docs/product-v2-refactor-plan.md`](docs/product-v2-refactor-plan.md)，
> 当前进度与下一动作见
> [`_working/amz-listing-kit-product-v2/state.md`](_working/amz-listing-kit-product-v2/state.md)，
> 文档身份和读取顺序见 [`docs/INDEX.md`](docs/INDEX.md)。

只读冷恢复入口：`uv run --locked python tools/refactor_resume.py`。它核对仓库计划、状态与观察证据，
输出下一任务及可读 Goal；显示的是仓库保存的最近观察，不会查询系统 Goal。恢复会话须另读真实 Goal，
不能把历史观察当当前读数。当前2026-10-07完整交付恢复授权/产品Goal只见计划§2.1/§16.1，绑定与已用轮数只看state；有限差量入口见§15.6/设计§11.5。早期独立规划完成不是产品验收，当前完整任务/最终发布仍须实际证明。

## 当前可用边界

默认入口提供以实际图片任务为中心的 Product V2 工作区，项目与历史只保存在当前浏览器：

- 从空白页面新建、打开、重命名、复制和删除项目；
- 项目列表、商品资料草稿、参考图、槽位和商品理解都保存在当前浏览器的 IndexedDB；
- 文档最新版与保存时的 OCC 版本头按数值版本索引读取，不加载全部历史；本机数据库升级保留文档历史、资产和项目元数据，完整项目包仍包含全部版本。
- localStorage 只保存当前项目指针；
- 启动时先完成本机列表读取再解锁；返回首页遇到慢读取会显示忙碌状态，读取失败保留已有列表并提供键盘可用的重试入口，不把读取失败显示成空项目库。
- 将完整项目导出为 ZIP，或从 ZIP 导入；导入前校验结构和内容哈希；
- 在工作区里上传参考图（可选择角色、同内容自动去重）、填写商品资料并自动保存草稿；
- 不调用 AI 也可人工填写、确认或标记未知商品事实，选择图片用途、编辑结构化尺寸及用途依赖；缺尺寸只阻断消费尺寸的图，不阻断无关主图/场景图。
- 文字理解与商品看图理解均是显式辅助动作：文字模型只看资料和参考图元数据，看图模型接收上传图片的真实字节；提案保留来源、原资料版本和 action，仍由人工确认。资料变化或项目切换后迟到提案留在原记录，不污染当前事实。
- 常驻「模型设置」提供理解、生图、复核三用途的有限现有模型和自己的 key；密钥只在当前标签页内存及请求级头中，应用后清空输入，不进项目包或本地持久化。默认付费档缺省 closed；能力投影和实际请求共用同一有效配置。
- 在已确认事实上生成推荐套图方案，新增、复制、删除、排序图片任务，条件依赖不足时精确阻断；
- 编辑公共风格与单图规格，保存与回退都写新版本，改动的影响范围可机检；
- 按图编译可追溯的 Prompt 版本：指令统一中文、图中文案逐字来自已确认事实，界面文本、版本记录与请求快照 hash 一致；编译失败保留旧版本；
- 提示词人工编辑：在每张图的 Prompt 版本上直接改全文并保存为新版本，旧版本与编辑原因、来源都可追溯；只有语言策略降级为可见提示，
  空文本、超长、无变化、未确认事实、未授权新引用与主图新增文案仍然阻断；编辑只失效目标图的提示词/审核/选择，并要求重新确认；
- 默认 Prompt 自动本地准备，不覆盖人工全文；用户查看实际发送摘要后，一次「确认并生成」完成授权登记与执行。缺项、过期和受影响图在摘要中可见，确认按实际请求指纹绑定，修改后须重新授权。
- Python 只提供静态页面、健康检查与无状态能力/理解/生图/复核 API，不保存用户项目、任务表、参考图或候选。
- 「资料 → 理解 → 方案 → 生成 → 审核返工 → 交付」是六个可随时打开的任务入口，不是操作授权。异步更新不自动切换用户所在任务；生成、采用、导出等动作仍按领域就绪条件设门。Prompt 全文、hash、task id 和诊断收进详情。
- 生图网关使用有限 Adapter：DashScope `qwen-image-3.0` 为 submit/status/result 异步协议；大陆火山 `doubao-seedream-5-0-flash-260915` 一次提交返回同步图片字节，没有独立 task id，不伪造任务编号。
  参考图、尺寸、参数或目标越界明确拒绝；未知结果保留 Unknown，不自动重提。服务端不外发供应商签名地址或密钥。
- 浏览器生成执行已接通：逐图提交生成前，先把这次生成的 `action_id`、Prompt 版本与 hash、
  参考图与参数以 `pending_submit` 写进 IndexedDB，再调用图像网关；提交 / 查询信封推进状态机
  （submitted / running / succeeded / failed / unknown），task id 与 request id 原样保存；
  双击与重入只会产生一条 Attempt；刷新、换标签页或服务端重启后，有 task id 的记录可继续核对；
  没有 task id 的 Unknown 与刷新中断的 pending 不自动重提，只能显式新建 action（旧记录与版本链原样保留）；
  Prompt 前进后仍保留原 Attempt/候选与冻结来源。成功字节按内容寻址保存，并生成绑定候选和检查合同的确定性报告。
  图片一成功即可查看/比较，不等待整批结束；比较展示该次实际参考图、历史候选和审核依据，查看不产生采用。
  旧已提交任务按原 provider/model/协议/能力/凭据来源核对；缺原凭据可在设置中补给，不切换新动作模型，不偷用当前或默认 key。
- 单图返工在比较附近就地完成，预览实际 Prompt 后明确生成；只为目标图新增授权/Attempt，不改变无关图或自动改选。人工采用、改选和取消直接操作同一 Selection，不另开重复确认面板；新的成功候选不自动覆盖原采用。
- AI 单图/整套复核仅在用户明确点击时运行，生成、查看、采用和打开页面不自动调用。未运行如实显示未复核，不伪装 PASS 或模型 Unknown。
  导出仍强制当前确定性单图/整套报告、硬规则、人工采用、原动作来源和字节 hash；已实际复核但结果 Unknown 的确认门保留。
  未采用的可选缺尺寸草案不阻止无关图片交付，必需或已采用的尺寸图仍受其依赖硬门约束。
  交付 ZIP 包含采用图片、`manifest.json`、`checks.json` 和 `README.txt`；整套/每图如实记录 `ai_review`，没有 AI 调用为 `not_reviewed/not_run`。
- 整套生成与逐图进度已接通：整套生成按套图顺序逐张提交；批次进度不是被存储的对象，而是由套图顺序、
  每张图最新 Attempt 与 Prompt 就绪状态即时推导——刷新后按同样输入重算，不存在第二份需要对账的状态；
  「停止」只停新增提交、保留全部已有记录，再点「继续生成剩余」接着走；单张明确失败不阻塞其余图片，
  可单独重试（重试 = 显式新建 action，旧记录逐字保留）；没有 task id 的记录永不自动重提，只能人工核对。

两类ZIP与人工任务链已有独立Chrome无头、真实页面和native下载的同版本证据，完整项目包保留全部版本与资产；原运行范围见 `evals/product-v2/refactor/generation-module-20261005-formal.md`。当前代码只接受当前格式，旧格式/缺身份应明确原子拒绝、不补造迁移或静默删库；但packet08旧ZIP/秘密探针存在空证，不能用其旧pass宣称这些要求已验证。

实现与证据分别说明：本地fake候选证明其实际运行的交互/顺序/恢复/完整性，不证明真图质量；真实供应商按原Adapter/输入/路径复用，不因报告更新重复付费。最新审计只运行新建/草稿保存/刷新及正式入口检查，当前完整任务、间歇根治、最终两轮/CI/容器发布仍未闭合，具体前沿取state。C15/C17真人验收仍未发生，属于本轮外部门，不冒充自动化通过。

理解 Adapter 分开业务合同：`v2_dashscope_semantic.py` 使用 `deepseek-v4.1-flash` 处理文字，`v2_dashscope_vision_semantic.py` 使用 `qwen-vl-max` 发送实际商品图片并返回可追溯提案；单图/整套图片复核不复用商品理解提案 schema。`v2_registry.py` 装配有限配置，测试替身仅用于离线验证，不代表模型能力或质量。

## 启动

环境要求：Python 3.13、uv 0.9+、现代桌面浏览器；依赖权威是 `pyproject.toml` + `uv.lock`。

前端开发期检查（渐进 TS 迁移，计划 §9 V2.R7.5）用仓库根 `package.json` + `package-lock.json` 锁定的
TypeScript 6.0.3（Node 24.19.0 / npm 11.17.0），只在开发与 CI 使用，不进产品运行时。`app/product_v2/`
下每个已迁移 Module 只有一份手工维护的源码：`.ts` 是权威，同目录同名 `.js` 是生成产物且 import
说明符保持 `.js`；浏览器只加载生成的 `.js`，正式入口对 `.ts` / `.d.ts` 一律返回 404，Docker 镜像
也排除 TS 源，生产运行时没有编译器。

现有TS源码包括 `domain/attempt`、`domain/config-export`、`semantic-analysis`、`session`、`model-settings`、五个业务owner（project-inputs/prompts/generation/selection-adoption/review-delivery）、`ui/dom`与四视图；本次之前的审计已校验15个TS产物，范围见其checks。实际strict集合/调用方取 `jsconfig.json`及各JS的opt-in，emit/新鲜度取compiler program批准范围内全部TS（含传递import的input-view），不能把文件存在或检查绿灯等同全仓类型/业务保障。

```bash
npm ci --ignore-scripts
npm run check:types        # 严格类型检查；实际覆盖由 jsconfig.json 决定，未纳入的文件不在保障内
npm run build:frontend     # 类型检查并生成同目录 .js（改过 TS 必须重跑并提交）
npm run check:generated    # 只校验生成产物与 TS 源码一致（CI 用，防止静默服务旧 JS）
npm run test:domain        # 领域行为的 node 原生测试
```

```powershell
uv sync --locked
uv run python app\server.py --check
uv run python app\server.py --open
```

默认地址为 `http://127.0.0.1:8780/`。若需要让内网或穿透工具访问，可显式设置监听地址；暴露范围和访问控制由运行者负责：

```powershell
uv run python app\server.py --host 0.0.0.0 --port 8780
```

当前实现依赖浏览器原生IndexedDB、`crypto.randomUUID`与WebCrypto SHA-256；本轮工程验证范围是稳定版桌面Chrome（计划§2.4），旧Edge记录仅历史，不冒充本轮通过。localhost是浏览器认可的开发安全上下文，远程正式入口必须是HTTPS：
本仓库的部署把 TLS 终止在 Caddy 容器（`deploy/caddy/Caddyfile`，Let's Encrypt IP 证书 shortlived
profile 自动续期），应用容器仍只提供无状态 HTTP，当前试用入口是 `https://47.115.172.233:8080/`。
直接打开明文 `http://<IP>:8780` 时，Chrome/Edge 会保留 IndexedDB 但禁用 WebCrypto；页面会精确说明
“缺的是安全上下文 / WebCrypto”并禁用新建与导入，不会把缺口误报成 IndexedDB 不支持（证据见
`evals/product-v2/v2.ui.1-remote-entry-*-final.*`）。

模型设置按用途选择注册表的有限目录，自己的 key 只在当前标签页内存中使用，不开放任意模型 ID 或目标地址。
理解可选 `dashscope-semantic`（`deepseek-v4.1-flash`，只发送文字及参考图元数据，明确未看图）或
`dashscope-vision`（`qwen-vl-max`，发送实际图片字节）。看图支持 1–3 张 PNG/JPEG、单张 ≤4MiB；
网关按 base64 载荷读取后校验字节上限和完整 SHA256，输出仍是待人工确认的提议，不自动成为事实。
图像双 Adapter 为 `dashscope-qwen-image`（`qwen-image-3.0`，异步）和 `volcengine-ark`
（`doubao-seedream-5-0-flash-260915`，同步一步到终态、无 task 链）。单图及整套复核共用
`dashscope-review`（`qwen-vl-max`），只由用户明确发起，不随生成、比较或采用自动调用。
缺可用凭据时返回分类错误，不伪造结果；显式离线验证才使用测试替身。

凭据口径（V2.R4.3）：部署密钥受默认档开关 `AMZ_V2_DEFAULT_TRIAL` 约束，未设置或 `closed/off/0/false`
时不会把部署密钥传入模型；无独立 BYOK 的有效调用请求返回 503 PROVIDER_NOT_CONFIGURED，
capabilities 给出 `credential_source` 与 `default_trial` 状态；显式 `open/on/1/true` 才沿用部署密钥。
三用途 BYOK 分别通过 `X-AMZ-Listing-Key-Semantic`、`X-AMZ-Listing-Key-Image`、
`X-AMZ-Listing-Key-Review` 请求头使用，应用后清空输入框，不落盘、不回显、不进项目包。
部署侧 DashScope 使用 `DASHSCOPE_API_KEY`，火山使用 `ARK_API_KEY`；默认档开关不限制独立 BYOK。
出站统一走白名单（`v2_outbound.py`：`aliyuncs.com` + `volces.com` 后缀），非白名单、
私网与非 https 目标在传输前被拒绝。

## 实际运行链

```text
app/server.py
  → app/product_v2_server.py
      ├─ GET /、/index.html、静态资源
      ├─ GET /api/health
      ├─ GET /api/v2/capabilities            provider 能力与 analyze 请求字段
      ├─ POST /api/v2/semantic/analyze       一次无状态分析；分类错误 + unknown 标记
      ├─ POST /api/v2/images/submit          单次登记与提交；按协议返回 task 或同步字节
      ├─ POST /api/v2/images/status          按原目标/task 查询异步状态
      ├─ POST /api/v2/images/result          按原目标/task 取回 PNG 字节
      ├─ POST /api/v2/review/candidate       显式单图 AI 复核
      └─ POST /api/v2/review/suite           显式整套 AI 复核

浏览器 app/product_v2/app.js
  → session.js / model-settings.js / semantic-analysis.js / generation.js（各自 TS 源编译产物；会话、内存凭据、理解动作及生成顺序）
  → workspace.js（任务与领域投影、发起业务动作）
  → storage/repository.js
      ├─ IndexedDB：项目、对象、Blob、版本（generation_attempt 版本链 append-only）
      └─ localStorage：当前项目 ID
```

页面不会读取服务器文件夹，也没有 `directory`、workspace 或 recent-workspaces 参数。项目导入先在内存中校验，
成功后才写入浏览器数据库；同 ID 项目会作为新项目导入，不覆盖既有项目。

## 验证当前实现

以下入口分别验证正式服务、浏览器存储、项目首页、项目包和领域合同；浏览器验证首次先执行 `uv run playwright install chromium`：

```powershell
uv run python app\server.py --check
uv run python tools\verify_v2_1_1_indexeddb.py
uv run python tools\verify_v2_1_2_project_home.py
uv run python tools\verify_v2_1_3_project_package.py
uv run python tools\verify_v2_1_4_formal_entry.py
uv run python tools\verify_v2_2_1_product_contracts.py
uv run python tools\verify_v2_2_2_semantic_provider.py
uv run python tools\verify_v2_2_3_intake_understanding.py
uv run python tools\verify_v2_2_4_category_generality.py
uv run python tools\verify_v2_3_1_suite_registry.py
uv run python tools\verify_v2_3_2_suite_editor.py
uv run python tools\verify_v2_3_3_spec_versions.py
uv run python tools\verify_v2_3_4_prompt_compiler.py
uv run python tools\verify_v2_3_5_pre_generation_confirm.py
uv run python tools\verify_v2_3_6_prompt_manual_edit.py
uv run python tools\verify_v2_4_1_image_gateway.py
uv run python tools\verify_v2_4_2_generation_attempt.py
uv run python tools\verify_v2_4_3_batch_execution.py
uv run python tools\verify_v2_4_4_candidate_blob.py
uv run python tools\verify_v2_5_1_deterministic_review.py
uv run python tools\verify_v2_5_2_vlm_review.py
uv run python tools\verify_v2_5_3_compare_panel.py
uv run python tools\verify_v2_5_4_rework_loop.py
uv run python tools\verify_v2_6_1_selection.py
uv run python tools\verify_v2_ui_2_interaction_visual.py
```

远程 HTTPS 正式入口与浏览器能力诊断单独验证（需要能访问 `https://47.115.172.233:8080`
与明文负例 `http://47.115.172.233:8780`，因此不进 CI，部署后按需运行）：

```powershell
uv run python tools\verify_v2_ui_1_remote_entry.py
```

`verify_v2_2_2_semantic_provider.py` 默认只做离线回放（真实 ChatOpenAI + 假传输），不联网；
加 `--live` 才会做计划 §12.2 允许的最小真实调用（正例 1 次 + 无效密钥 401 负例 1 次），
需要已在服务器环境里配置 `DASHSCOPE_API_KEY`。
 `verify_v2_2_4_category_generality.py` 默认只跑离线检查（C1 输入驱动、C5 无常量泄漏）；
加 `--live` 才会做四类商品的真实语义调用（每类最多 1 次、不重试），同样需要 `DASHSCOPE_API_KEY`。

文档、状态和控制面守卫必须串行执行：

```powershell
uv run python tools\check_docs.py --no-run
uv run python tools\check_project_state.py
uv run python evals\probes\project_state.py
```

`--no-run` 只检查文档结构与登记关系，不证明 README 中的命令已执行。产品完成声明还需要浏览器、
IndexedDB、API、真实 Provider 和首次使用者证据，具体门槛由产品计划定义。

## CI/CD

  `.github/workflows/ci-cd.yml` 在 PR 和 push 上执行控制面守卫、当前 Product V2 浏览器验证、Docker 构建、
  容器健康检查和发布事务自检（真实一次性容器，`tools/release_transaction_probe.py --selftest`，缺 Docker/构建/
  Playwright 按 exit 2 报 missing_prereq，不伪造绿）。本机不承担正式容器运行。只有 `main` push 会部署：
  Actions 使用仓库中的 `SSH_HOST`、`SSH_USER`、`SSH_PRIVATE_KEY`，把最小 Product V2 构建上下文传到远程
  服务器，由远程 Docker 构建以 Git SHA 标记的镜像并按 `deploy/release-transaction.sh` 做完整发布事务
  （previous 与 TLS 配置备份保留到容器健康、外部 HTTPS、静态资源/页面主链全部验收结束；全部通过才清理，
  含 finalize 的健康 + HTTPS + 静态重验证；重验证失败 exit 1 走回退到上一已知可用状态并核对实际可用性，
  收尾失败 exit 4 需人工清理且绝不自动回滚；回退失败报 `unrecovered_failed_release` exit 3）。
  PR 不部署。服务器可选将运行时变量放在 `$HOME/.config/amz-listing-kit/app.env`。

这套流程存在不等于已经部署成功；是否真实上线必须以对应的 GitHub Actions run 和目标机
`GET /api/health` 为证据。

## 历史 Product V1

旧Product V1源码与显式入口暂存，描述的是历史服务器文件夹工作空间实现，**不是当前已验收可用的回归/回退基线**。本轮计划R7.3在V2用途覆盖、正式消费者切换及代码/同版本数据恢复基线后清除其活路径；共享依赖与必要历史/用户原件保留。当前默认入口是V2，未执行V1清理前的历史启动方式如下：

```powershell
uv run python app\server.py --legacy-v1 --check
uv run python app\server.py --legacy-v1 --open
uv run python tools\regress_product_v1.py
```

旧离线 Mock 只用于历史状态轨迹回归：

```powershell
uv run python app\server.py --offline-fixture demo\fixture\aster-01 --check
```

Product V1 的设计和完成轨迹已登记为 `superseded`；需要追溯时从 `docs/INDEX.md` 进入，不把固定七坑位、
服务器工作空间或抠图路线重新带回 Product V2。

## 代码地图

```text
app/server.py                    正式启动入口；默认 V2
app/product_v2_server.py         V2 无状态 HTTP 装配：静态、能力、文字/商品图文理解、生图、单图/整套复核
app/product_v2/                  V2 页面、IndexedDB、会话/设置/理解/生成 Module；TS 唯一手工源，同名 JS 为编译产物
app/product_v2/domain/           领域合同；prompt.js / confirm.js 各为唯一权威，attempt.ts / config-export.ts 由 npm run build:frontend 生成同名 JS
src/providers/                   有限语义/图文/生图/复核 Adapter、共享 langchain 图文传输、registry/credentials/errors/outbound；出站白名单 aliyuncs.com + volces.com
config/product-v2/               provider 注册表与选择环境变量；当前实现依赖它，是否已提交以 git status 为准
tools/                           自检、契约验证和控制面守卫
evals/product-v2/                时点证据，不是当前状态或规范
docs/INDEX.md                    文档身份与读写路由
```

## 配置与安全边界

- 当前默认服务绑定 `127.0.0.1`；是否经内网穿透暴露由运行者决定。
- Product V2 服务端没有账户、租户、数据库或用户项目索引。
- `DASHSCOPE_API_KEY`、`SEMANTIC_MODEL`、`IMAGE_MODEL` 等只从服务端环境变量读取。
- 浏览器站点数据被清理或 origin 改变时，只能通过此前导出的项目 ZIP 恢复。
- 本文件描述的是当前工作树里经过验证入口检查的实现；工作树中的新文件是否已被 Git 提交，以 `git status` 为准。
