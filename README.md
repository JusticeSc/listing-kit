# amz-listing-kit

> CONTROL-STATUS: current · AUTHORITY: implemented-behavior
> 本文件只回答“当前代码实际能做什么、怎样启动和验证”。产品目标见
> [`docs/product-v2-refactor-plan.md`](docs/product-v2-refactor-plan.md)，
> 当前进度与下一动作见
> [`_working/amz-listing-kit-product-v2/state.md`](_working/amz-listing-kit-product-v2/state.md)，
> 文档身份和读取顺序见 [`docs/INDEX.md`](docs/INDEX.md)。

只读冷恢复入口：`uv run --locked python tools/refactor_resume.py`。它核对仓库计划、状态与观察证据，
输出下一任务及可读 Goal；显示的是仓库保存的最近观察，不会查询系统 Goal。恢复会话须另读真实 Goal，
不能把历史观察当成当前读数。绑定合同与展示码归一范围见计划 §2.2。

## 当前可用边界

默认入口现在提供 Product V2 的浏览器本地项目外壳，以及“商品资料 → 商品理解 → 套图规划 → 规格 → Prompt → 生成前确认”工作区：

- 从空白页面新建、打开、重命名、复制和删除项目；
- 项目列表、商品资料草稿、参考图、槽位和商品理解都保存在当前浏览器的 IndexedDB；
- 文档最新版与保存时的 OCC 版本头按数值版本索引读取，不加载全部历史；本机数据库升级保留文档历史、资产和项目元数据，完整项目包仍包含全部版本。
- localStorage 只保存当前项目指针；
- 启动时先完成本机列表读取再解锁；返回首页遇到慢读取会显示忙碌状态，读取失败保留已有列表并提供键盘可用的重试入口，不把读取失败显示成空项目库。
- 将完整项目导出为 ZIP，或从 ZIP 导入；导入前校验结构和内容哈希；
- 在工作区里上传参考图（可选择角色、同内容自动去重）、填写商品资料并自动保存草稿；
- 点一次按钮做一次无状态语义分析，提案只以“模型提案”入库，由人工确认、修改、标记未知或移除；
- 在已确认事实上生成推荐套图方案，新增、复制、删除、排序图片任务，条件依赖不足时精确阻断；
- 编辑公共风格与单图规格，保存与回退都写新版本，改动的影响范围可机检；
- 按图编译可追溯的 Prompt 版本：指令统一中文、图中文案逐字来自已确认事实，界面文本、版本记录与请求快照 hash 一致；编译失败保留旧版本；
- 提示词人工编辑：在每张图的 Prompt 版本上直接改全文并保存为新版本，旧版本与编辑原因、来源都可追溯；只有语言策略降级为可见提示，
  空文本、超长、无变化、未确认事实、未授权新引用与主图新增文案仍然阻断；编辑只失效目标图的提示词/审核/选择，并要求重新确认；
- 生成前确认：把套图计划与每图 Prompt 归约成一张确认单，显示张数、每图任务、将发送的模型参数与参考图角色、未消除风险；
  缺 Prompt、Prompt 过期或依赖不足时精确阻断并给出返回位置；确认记录按指纹绑定、append-only，上游变化即失效并回落到「计划复核」状态；
- Python 服务只提供静态页面、健康检查与无状态 API（能力查询、语义分析、图像网关三段），不保存工作空间、最近项目或图片。
- 界面按「资料 → 理解 → 方案 → 生成 → 审核返工 → 交付」六阶段同页推进：阶段条始终可见，显示完成 / 当前 / 锁定，
  未解锁阶段给出原因；同一时刻只突出一个主操作；首页只有「新建项目」一个主操作与次级「导入项目包」；
  Prompt 全文、hash、task id 与项目元数据默认收进「详情」；390px 与 200% 缩放不遮挡关键操作，关键路径可纯键盘走通。
- 无状态图像网关已就位：`/api/v2/images/submit|status|result` 三段路由转发一次
  `qwen-image-3.0` 调用——提交只返回任务身份（provider/model、task id、状态、结果数量、request id），
  查询返回权威状态，取回返回 PNG 字节；上游签名地址从不外发，服务端不保存任务表。
  契约外字段（如 `directory`）、参考图数量/内容、尺寸与提示词越界一律 400；上游 4xx 是明确失败（含可重试的
  限流与欠费），5xx、连接中断、任务号不符归 Unknown 并要求人工核对，未知不自动重提。
  缺少 `DASHSCOPE_API_KEY` 时 capabilities 仍 200 且 `configured=false`，提交返回 503。
- 浏览器生成执行已接通：逐图提交生成前，先把这次生成的 `action_id`、Prompt 版本与 hash、
  参考图与参数以 `pending_submit` 写进 IndexedDB，再调用图像网关；提交 / 查询信封推进状态机
  （submitted / running / succeeded / failed / unknown），task id 与 request id 原样保存；
  双击与重入只会产生一条 Attempt；刷新、换标签页或服务端重启后，有 task id 的记录可继续核对；
  没有 task id 的 Unknown 与刷新中断的 pending 不自动重提，只能显式新建 action（旧记录与版本链原样保留）；
  Prompt 前进后旧 Attempt 标记「基于旧版本 v?」。候选字节在成功结论的同一步按内容寻址保存到浏览器本地
  （详见下节「真实出图链路」），并同步生成绑定候选与检查合同版本的确定性检查报告
  （格式 / 尺寸 / 透明通道 / 平台缩放规则；无法测量只提示、不阻断）；候选行提供「自动复核（VLM）」
  ——调用可替换的视觉语言模型找可疑问题，只提示、不自动采纳、失败保留 Unknown；候选行另有
  「比较候选（n）」：把这张图**实际发送的参考图**、按异常优先排序的历史候选与逐候选审核清单
  （先看项 + 按需展开的完整报告 + 这张图的验收依据）放在一起对比，方向键/Home/End 可只在候选间移动；
  面板只读，不产生采纳。返工是相邻的独立面板：勾选九类常见问题或写清改进方向，预览将发送的
  完整 Prompt，再「确认并生成这张图」；预览只编译不落盘，改动输入后必须重新预览；最新一次尝试失败或
  Unknown 时，历史候选仍可发起返工。返工只给目标图新增 Prompt 版本、单图确认与 Attempt，旧候选与无关图
  逐字保留。采纳（人工选择）也已接通：比较区的「采用此候选」只把该候选交给相邻的「采用候选（人工选择）」
  面板，采用、改选与取消都在那里完成，一张必需图最多一个当前选择；这张图之后出现新的成功候选时，旧选择自动标为过期而不被覆盖，可以重新采用新候选
  或旧候选。整套一致性报告与交付包下载已接通：审核阶段可运行「整套检查」（跨图商品/风格一致性与跨图低级
  异常），报告绑定当前选择与输入的指纹、过期即要求重算，视觉通道失败只落 Unknown；交付阶段先过门禁
  （选择性、选择链、报告当前性、字节哈希、整套报告、Unknown 确认逐条可见），通过后「生成交付包（ZIP）」
  下载 `images/<shot>-<candidate>.png` + `manifest.json` + `checks.json` + `README.txt`，导出记录只追加，
  刷新后仍能看到最近一次包身份。
- 整套生成与逐图进度已接通：整套生成按套图顺序逐张提交；批次进度不是被存储的对象，而是由套图顺序、
  每张图最新 Attempt 与 Prompt 就绪状态即时推导——刷新后按同样输入重算，不存在第二份需要对账的状态；
  「停止」只停新增提交、保留全部已有记录，再点「继续生成剩余」接着走；单张明确失败不阻塞其余图片，
  可单独重试（重试 = 显式新建 action，旧记录逐字保留）；没有 task id 的记录永不自动重提，只能人工核对。

真实出图链路已接通：每张图可以登记并提交一次生成（真实调用需要服务端配置 `DASHSCOPE_API_KEY`；无密钥时
提交被明确拒绝），并按已保存的 task id 核对结论；成功结论会在同一步把结果字节存进浏览器本地
（内容寻址、sha256 与服务端声明一致，刷新后仍可预览、不重复保存），取回失败或浏览器空间不足会留下
明确的可恢复提示。单图返工闭环已在默认页面接通，证据见 `evals/product-v2/v2.5.4-rework-loop-*-final.*`；
人工采纳（人工选择）已接通并能刷新恢复，证据见
`evals/product-v2/v2.6.1-selection-*-final.*`；整套一致性报告见
`evals/product-v2/v2.5.5-suite-review-*-final.*`，交付门禁与交付包（含 Unknown 逐条确认、哈希核对、
Python 独立解包核对）见 `evals/product-v2/v2.6.2-delivery-*-final.*`。
项目包的格式升级与迁移已接通：导入旧格式包会按迁移链升级并提示，当前格式逐记录自描述、带完整性
计数与逐资产哈希，跨浏览器往返后可在新浏览器继续返工与交付，证据见
`evals/product-v2/v2.6.3-transfer-*-final.*`。
项目界面的渐进披露与可访问性终验已接通：sha256 / action / task 等工程字段默认收进「技术详情」，
390px 与 200% 缩放无横向溢出，键盘路径与 axe WCAG A/AA 扫描纳入
`tools/verify_v2_6_4_accessibility.py`，证据见 `evals/product-v2/v2.6.4-a11y-*-final.*`。
当前默认页面**还不能**对外声明可用：真实模型端到端与陌生人走查属于发布前人工门（尚未执行）；
不能因为旧 Product V1 已实现过就声称当前入口已具备这些。

服务端语义链路已经接入正式入口：`src/providers/v2_semantic.py`（契约与错误分类）、
`v2_dashscope_semantic.py`（DeepSeek 适配器）、`v2_fake_semantic.py`（测试替身）与
`src/providers/v2_registry.py`（按 `config/product-v2/providers.json` 与环境变量选 provider）
把商品资料投影变成候选槽位提案。`fake-semantic` 只用于无密钥环境与验证入口，不代表真实模型质量。

## 启动

环境要求：Python 3.13、uv 0.9+、现代桌面浏览器；依赖权威是 `pyproject.toml` + `uv.lock`。

```powershell
uv sync --locked
uv run python app\server.py --check
uv run python app\server.py --open
```

默认地址为 `http://127.0.0.1:8780/`。若需要让内网或穿透工具访问，可显式设置监听地址；暴露范围和访问控制由运行者负责：

```powershell
uv run python app\server.py --host 0.0.0.0 --port 8780
```

当前实现依赖浏览器原生 IndexedDB、`crypto.randomUUID` 与 WebCrypto SHA-256；首版只保证当前稳定版桌面
Chrome 与 Edge（SEL-012）。localhost 是浏览器认可的开发安全上下文；远程正式入口必须是 HTTPS：
本仓库的部署把 TLS 终止在 Caddy 容器（`deploy/caddy/Caddyfile`，Let's Encrypt IP 证书 shortlived
profile 自动续期），应用容器仍只提供无状态 HTTP，当前试用入口是 `https://47.115.172.233:8080/`。
直接打开明文 `http://<IP>:8780` 时，Chrome/Edge 会保留 IndexedDB 但禁用 WebCrypto；页面会精确说明
“缺的是安全上下文 / WebCrypto”并禁用新建与导入，不会把缺口误报成 IndexedDB 不支持（证据见
`evals/product-v2/v2.ui.1-remote-entry-*-final.*`）。

语义分析默认走注册表里的 `dashscope-semantic`（`deepseek-v4.1-flash`），需要服务器环境变量 `DASHSCOPE_API_KEY`；缺密钥时该路由返回
明确的 503 分类错误并提示 provider 未配置，不会假装成功。无密钥环境与验证入口可设
`AMZ_V2_SEMANTIC_PROVIDER=fake-semantic` 使用测试替身。密钥只允许通过服务器环境变量提供，
不得写进浏览器、项目包、日志或 Git。图像双 Adapter：`dashscope-image`（`qwen-image-3.0`，异步）与 `volcengine-ark`（`doubao-seedream-5-0-flash-260915`，同步一步到终态、无 task 链），第二生图环境变量 `ARK_API_KEY`；复核 `dashscope-review` / 整套复核 `dashscope-suite-review`（`qwen-vl-max`，VLM 只分级不自动采用）。

凭据口径（V2.R4.3）：部署密钥受默认档开关 `AMZ_V2_DEFAULT_TRIAL` 约束，未设置或 `closed/off/0/false`
时不会进入真实模型调用（路由返回 503 PROVIDER_NOT_CONFIGURED，capabilities 会给出
`credential_source` 与 `default_trial` 状态）；显式设 `open/on/1/true` 才沿用部署密钥。
图像网关另外支持 BYOK：浏览器单次请求可带 `X-AMZ-Listing-Key-Image` 头，密钥只在请求内存中
转发与使用，不落盘、不回显；出站统一走白名单（`v2_outbound.py`：`aliyuncs.com` + `volces.com` 后缀），非白名单、
私网与非 https 目标在传输前被拒绝。

## 实际运行链

```text
app/server.py
  → app/product_v2_server.py
      ├─ GET /、/index.html、静态资源
      ├─ GET /api/health
      ├─ GET /api/v2/capabilities            provider 能力与 analyze 请求字段
      ├─ POST /api/v2/semantic/analyze       一次无状态分析；分类错误 + unknown 标记
      ├─ POST /api/v2/images/submit          提交一次生成；只返回任务身份
      ├─ POST /api/v2/images/status          按 task id 查询权威状态
      └─ POST /api/v2/images/result          按 task id 取回 PNG 字节

浏览器 app/product_v2/app.js
  → workspace.js（参考图 / 商品资料 / 分析 / 商品理解 / 套图 / 规格 / Prompt / 确认 / 生成执行）
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

`.github/workflows/ci-cd.yml` 在 PR 和 push 上执行控制面守卫、当前 Product V2 浏览器验证、Docker 构建和
容器健康检查。本机不承担正式容器运行。只有 `main` push 会部署：Actions 使用仓库中的 `SSH_HOST`、
`SSH_USER`、`SSH_PRIVATE_KEY`，把最小 Product V2 构建上下文传到远程服务器，由远程 Docker 构建以
Git SHA 标记的镜像并替换同名容器。新容器健康失败时恢复上一容器；PR 不部署。服务器可选将运行时变量放在
`$HOME/.config/amz-listing-kit/app.env`。

这套流程存在不等于已经部署成功；是否真实上线必须以对应的 GitHub Actions run 和目标机
`GET /api/health` 为证据。

## 历史 Product V1

旧 Product V1 仍作为回归基线保留，拥有服务器文件夹工作空间、商品资料、提示词、真实图片生成、候选、
单图返工、人工选择和导出等能力。它的状态所有权与 Product V2 不同，不是默认产品入口：

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
app/product_v2_server.py         V2 无状态 HTTP 适配器（静态资源 + capabilities + semantic/analyze + images/submit|status|result）
app/product_v2/                  V2 页面、IndexedDB 存储与工作区（workspace.js）
app/product_v2/domain/           领域合同：事实槽位、套图、规格、Prompt 编译与人工编辑、生成前确认、生成 Attempt（prompt.js / confirm.js / attempt.js 是各自唯一权威）
src/providers/                   Provider 适配器与注册表（语义：v2_semantic / v2_dashscope_semantic / v2_fake_semantic；图像：v2_image / v2_dashscope_image / v2_volcengine_image / v2_fake_image；复核：v2_dashscope_review / v2_fake_review；整套复核：v2_dashscope_suite_review / v2_fake_suite_review；错误词表：v2_errors；出站白名单：v2_outbound `aliyuncs.com` + `volces.com`）
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
