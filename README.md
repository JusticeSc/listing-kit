# amz-listing-kit

> CONTROL-STATUS: current · AUTHORITY: implemented-behavior
> 本文件只回答“当前代码实际能做什么、怎样启动和验证”。产品目标见
> [`docs/product-v2-goal-and-implementation-plan.md`](docs/product-v2-goal-and-implementation-plan.md)，
> 当前进度与下一动作见
> [`_working/amz-listing-kit-product-v2/state.md`](_working/amz-listing-kit-product-v2/state.md)，
> 文档身份和读取顺序见 [`docs/INDEX.md`](docs/INDEX.md)。

## 当前可用边界

默认入口现在提供 Product V2 的浏览器本地项目外壳，以及“商品资料 → 商品理解 → 套图规划 → 规格 → Prompt → 生成前确认”工作区：

- 从空白页面新建、打开、重命名、复制和删除项目；
- 项目列表、商品资料草稿、参考图、槽位和商品理解都保存在当前浏览器的 IndexedDB；
- localStorage 只保存当前项目指针；
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
  或旧候选。整套一致性报告与导出交付仍是后续批次。
- 整套生成与逐图进度已接通：整套生成按套图顺序逐张提交；批次进度不是被存储的对象，而是由套图顺序、
  每张图最新 Attempt 与 Prompt 就绪状态即时推导——刷新后按同样输入重算，不存在第二份需要对账的状态；
  「停止」只停新增提交、保留全部已有记录，再点「继续生成剩余」接着走；单张明确失败不阻塞其余图片，
  可单独重试（重试 = 显式新建 action，旧记录逐字保留）；没有 task id 的记录永不自动重提，只能人工核对。

真实出图链路已接通：每张图可以登记并提交一次生成（真实调用需要服务端配置 `DASHSCOPE_API_KEY`；无密钥时
提交被明确拒绝），并按已保存的 task id 核对结论；成功结论会在同一步把结果字节存进浏览器本地
（内容寻址、sha256 与服务端声明一致，刷新后仍可预览、不重复保存），取回失败或浏览器空间不足会留下
明确的可恢复提示。单图返工闭环已在默认页面接通，证据见 `evals/product-v2/v2.5.4-rework-loop-*-final.*`；
人工采纳（人工选择）已接通并能刷新恢复，证据见
`evals/product-v2/v2.6.1-selection-*-final.*`；当前默认页面**还不能**做整套一致性报告与导出交付套图——
它们属于后续批次；不能因为旧 Product V1 已实现过就声称当前入口也已具备。

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

语义分析默认走注册表里的 `dashscope-semantic`，需要服务器环境变量 `DASHSCOPE_API_KEY`；缺密钥时该路由返回
明确的 503 分类错误并提示 provider 未配置，不会假装成功。无密钥环境与验证入口可设
`AMZ_V2_SEMANTIC_PROVIDER=fake-semantic` 使用测试替身。密钥只允许通过服务器环境变量提供，
不得写进浏览器、项目包、日志或 Git。

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
src/providers/                   Provider 适配器与注册表（语义：v2_semantic / v2_dashscope_semantic / v2_fake_semantic；图像：v2_image / v2_dashscope_image / v2_fake_image；错误词表：v2_errors）
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
