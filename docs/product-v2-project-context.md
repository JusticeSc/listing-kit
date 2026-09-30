# amz-listing-kit Product V2 项目上下文

> CONTROL-STATUS: current · AUTHORITY: project-context
> 本文件回答“项目是什么、怎样运行、数据归谁、目录与质量门槛是什么”。产品目标、验收与任务图只在
> [`product-v2-goal-and-implementation-plan.md`](product-v2-goal-and-implementation-plan.md) 维护；执行位置只在
> [`../_working/amz-listing-kit-product-v2/state.md`](../_working/amz-listing-kit-product-v2/state.md) 维护。

## 1. 项目身份

- **项目名称**：amz-listing-kit Product V2
- **目标使用者**：需要为电商商品制作一套可交付图片、但不希望从零学习复杂提示词工程的运营人员。
- **核心任务**：从商品参考图与少量商品资料出发，确认商品事实，编辑套图方案，调用图片模型生成候选，处理自动发现的问题，局部返工，人工选定并导出套图。
- **产品价值**：降低复杂生图任务的使用门槛，同时让设计者能查看和修改事实、套图、单图规格、Prompt、校验与候选关系。
- **当前平台边界**：Amazon US 通用图片要求；品类知识通过可扩展规则与动态槽位逐步增加，不假装已经覆盖全部品类。

## 2. 迁移基线与事实来源

| 层 | 稳定边界 | 事实从哪里读 |
|---|---|---|
| Product V1 | 本机文件夹工作空间与旧完整生图闭环冻结为回归基线；只复用业务语义、Provider 经验和测试案例，不继续扩展服务器工作空间；V2.7.4 冻结后由 V2.7.5 专批删除（SEL-009） | 当前仍可运行的行为见 `README.md` 的历史入口；设计与完成轨迹从 `docs/INDEX.md` 的 superseded 文档进入 |
| Product V2 | 浏览器拥有用户项目，Python 服务无业务状态；所有新能力都必须在这一所有权边界内实现 | 已落地行为只看 `README.md` 与代码；当前进度和证据只看 Product V2 state；目标只看 Product V2 计划 |
| 参考模板 | `docs/standards-template/` 是外部课程模板的原样副本，不是本项目运行规范 | 采纳映射、未采纳项与复访条件只在 `AGENTS.md` §Standards Mapping |

旧 Product V1 的“完成”只证明旧架构下的能力，不证明 Product V2 已经完成；未提交文件和选型 PoC
也只算候选或证据。任何“已实现”声明都必须由 README 指向的代码与范围匹配的验证证据支持。

## 3. 运行边界与数据所有权

```text
现代桌面浏览器
├─ localStorage：当前项目 ID、少量界面偏好
├─ IndexedDB：项目记录、参考图、候选图、任务身份、校验、选择和历史版本
├─ domain/：事实、套图、规格与 Prompt 编译的唯一权威（V2.3.4 起在浏览器侧执行）
└─ ZIP：完整项目包或最终交付包
        │
        │ 同源 HTTP；每次请求携带完成本动作所需上下文
        ▼
Python 无状态 AI 服务
├─ DeepSeek 语义分析
├─ qwen-image-3.0 提交、查询与结果转发（V2.4 起）
└─ 可替换视觉语言模型校验（V2.5 起）
        │
        ▼
外部模型 Provider
```

### 3.1 权威状态

- **用户项目权威**：浏览器 IndexedDB。
- **当前项目指针**：同一浏览器 origin 下的 localStorage。
- **外部生成执行权威**：Provider 的 task ID 与查询结果；浏览器保存身份和观察历史。
- **服务器**：不保存工作空间、最近项目、商品图、候选图、选择或导出包。
- **项目迁移与备份**：用户主动导出的完整项目 ZIP。
- **最终采用权**：人工 Selection；模型提议和 VLM 报告都不是最终采用。

### 3.2 无状态的准确边界

无状态指“不保存用户业务状态”，不是“进程没有配置或日志”。服务器可以读取模型配置、规则版本和环境变量，也可以输出不含项目内容的运行日志。图片只在当前请求中转，不作为服务器项目文件落盘。

如果生成提交超时且浏览器没有取得 provider task ID，结果保持 `UNKNOWN`，不得自动重提。只有已知 task ID 才能由任意重启后的服务器继续核对。

### 3.3 运行与部署取值

| 占位符 | 本项目取值 | 说明 |
|---|---|---|
| 入口 | `python app/server.py` | 默认启动 Product V2 无状态服务；`--legacy-v1` 回 V1 回归入口 |
| 端口 | `8780`（默认） | 可用启动参数覆盖；内网穿透与否由使用者自行控制 |
| 健康检查 | `GET /api/health` | 返回 `product=v2`、`server_state=none` |
| 宿主 | 本机 Python 开发入口；远程服务器 Docker 正式运行 | 默认 Python 启动仍绑定回环地址；远程容器固定监听 `0.0.0.0:8780`，暴露范围由服务器和使用者控制 |
| 部署方式 | GitHub Actions → SSH → 远程 Docker | PR/push 先跑 CI；只有 `main` push 才传最小构建上下文，由远程 Docker 构建 SHA 镜像并替换同名容器 |
| 容器 | `amz-listing-kit:<git-sha>` | 镜像只包含 Product V2 正式入口；健康失败恢复上一容器，不清理其他应用 |
| 密钥来源 | 环境变量 | `DASHSCOPE_API_KEY` 等；变量清单见 `.env.example` 与本文件 §4.2 |

## 4. 技术栈与可替换边界

| 层 | 当前选择 | 边界 |
|---|---|---|
| 前端 | 原生 HTML、CSS、JavaScript | 延续现有低依赖路线；业务状态通过 repository/service 接口访问，不让 DOM 成为状态源 |
| 浏览器持久化 | IndexedDB + Blob；localStorage 只放轻量指针 | 需要 schema migration、事务、容量提示、项目导入/导出；不把图片 Base64 塞进 localStorage |
| 服务端 | Python；正式入口 `app/server.py` 默认启动 Product V2 无状态适配器（`--legacy-v1` 回 V1） | 服务方法无用户工作空间参数；请求进、模型响应出；正式入口不读写工作空间或最近项目索引 |
| 语义模型 | `deepseek-v4.1-flash`，经 SemanticProvider 适配 | 输出必须通过结构契约；模型可替换，领域对象不绑定模型文本 |
| 图片模型 | 阿里云百炼 `qwen-image-3.0`，经 ImageProvider 适配 | 直接使用参考图；主流程不抠图、不部署本地分割模型 |
| 视觉校验 | 可替换 VLM Provider | 只提出分级问题与证据；具体模型 ID 在 V2.5.2 实现时按可用配置确定 |
| 确定性规则 | 版本化平台、文件、槽位依赖与状态规则 | 不把审美或模型自评伪装成硬规则 |
| 服务端数据库 | 无 | Product V2 不引入数据库、账户、租户或服务器项目索引 |
| 交付运行时 | Docker + GitHub Actions | CI 先验证同一 Dockerfile；远程服务器 Docker 从该提交的最小上下文构建 SHA 镜像并运行 |

首版语义与图片模型均通过阿里云百炼调用，统一从环境变量读取 `DASHSCOPE_API_KEY`；不要求额外的 `DEEPSEEK_API_KEY`。模型名称分别由 `SEMANTIC_MODEL`、`IMAGE_MODEL` 配置，VLM 名称留到 V2.5.2 选择后再写入 `VLM_MODEL`。密钥不得进入浏览器状态、项目包、日志、证据或 Git。

### 4.1 选型记录

选型门禁的规则正文在仓库根 `AGENTS.md`；本节是**结论的唯一落点**：每条选型决策留一行，
写清约束、被拒方案与复访条件，避免下一个 Agent 重新讨论、重新实现已经决定过的问题。

| ID | 范围 | 决策 | 被拒方案 | 复访条件 |
|---|---|---|---|---|
| SEL-000 | 依赖政策 | 分层：Python 侧允许登记过的 pinned 依赖，依赖管理与锁的唯一权威是 `pyproject.toml` + `uv.lock`（新增一律 `uv add`，CI 用 `uv sync --locked`）；浏览器侧保持无构建步骤，只允许 vendor 单文件库；领域规则（槽位注册表、错误归口、状态语义）自研，通用原语优先复用 | 全层放开 npm 构建链；全零新增依赖；requirements.txt 与 pyproject 双份手工维护 | 前端需要组件框架或状态管理，或离线安装条件变化 |
| SEL-001 | 编排层 | 不引入 LangGraph 与 Agent/Memory 编排，服务端保持无状态（业务状态权威是浏览器 IndexedDB）；引入 `langchain-core` / `langchain-openai` 仅作提示词、模型调用与结构化解析原语（见 SEL-003），不承担状态与编排 | LangGraph checkpointer + 服务端状态；Agent/Memory 编排 | 出现服务端自主多步编排，或需要跨进程恢复的长任务 |
| SEL-002 | 服务端 HTTP | 暂保留 stdlib `http.server`（零运行时依赖、端点少、单进程） | Flask / FastAPI + uvicorn | V2.4 图片上传/下载需要 multipart 与流式响应时重开 |
| SEL-003 | 语义/视觉调用传输层 | 用户已确认（2026-09-30）：`langchain-core` + `langchain-openai` 的 `ChatOpenAI` 指向百炼 OpenAI 兼容端点（`deepseek-v4.1-flash`）；显式 timeout、`max_retries=0`（禁止隐藏重试）；失败映射进 `v2_semantic` 四类归口。版本：langchain-core 1.6.6、langchain-openai 1.6.6（均 MIT）；依赖实测与 PoC 报告见 `evals/product-v2/sel003-transport-selection-20260929.txt` | LiteLLM（59 包，为单一兼容协议付 4 倍依赖）；`requests` 手写适配器（重复造 HTTP/重试轮子）；OpenAI SDK 直连（已含于 langchain-openai，不建双轨） | 接入第二个供应商或需要路由/降级/成本统计时评估 LiteLLM；需要 OpenAI 专有能力时评估直连。PoC 已发现：`deepseek-v4.1-flash` 为推理型输出，需给 reasoning 留预算 |
| SEL-004 | 项目管理规范 | 采纳 `docs/standards-template/` 的**要求**，落进现有五份权威（映射见 `AGENTS.md` §Standards Mapping），不新建 `standards/` 平行目录 | 复制模板另立一套 standards/（会与计划/state 形成双权威） | 需要对外交付独立规范包时重开 |
| SEL-005 | 持续交付 | 采用 GitHub Actions + Docker：PR/push 串行执行控制面、正式入口、浏览器合同和容器健康检查；仅 `main` 传最小 Product V2 构建上下文，由远程 Docker 构建 SHA 镜像，固定 `8780` 端口，失败恢复上一容器 | 继续只靠本机守卫；每次跨网传完整基础镜像；服务器拉整个 Git 仓库；引入镜像仓库或编排平台 | 需要多主机、零停机、镜像签名/制品留存或固定端口无法满足时重开 |
| SEL-006 | 语义契约表示 | Python 侧契约表示权威 = Pydantic（langchain-core 自带，锁定 2.13.5）：请求 / 原始提案 / 提案槽位三类模型 + 跨字段校验；校验作用在模型原始输出；错误四类归口、归一化映射、浏览器侧 `checkFactSlot` 与 `CORE_SLOT_REGISTRY` 保留 | Python 侧继续手写形状/不变量校验（重复造轮子，违反复用门）；浏览器改吃 schema（受 SEL-000 无构建约束，且与 SEL-001 状态权威错位） | V2.6.3 项目包跨版本迁移需要 schema 版本与迁移器时，以“契约权威”为题重开（评估 JSON Schema 作中立权威 + 双语言消费者） |
| SEL-007 | LangChain 使用边界 | v1 直调形态：`ChatOpenAI.with_structured_output(原始提案模型, method="json_mode", include_raw=True)`；系统/用户消息直接构造，JSON 格式说明由 Pydantic schema 生成并注入系统提示；LCEL 管道、ChatPromptTemplate、Agent/Memory 均不使用（保留为库内可用能力，不是本项目范式）；装配与错误分类的操作细节见计划 §9.1 | LCEL 管道（0.x 主推范式）；默认 `method="json_schema"`（百炼对自定义模型名的支持未证实；不支持时 400 且会被误分类）；`method="function_calling"`（依赖该模型在百炼的函数调用支持）；ChatPromptTemplate | 百炼确认支持 `response_format: json_schema` 时把 method 切换回默认（改一个装配参数 + 重跑契约测试）；需要多步编排时按 SEL-001 的复访条件另立决策 |
| SEL-008 | 浏览器 ZIP 能力 | 用户已定（2026-09-30）：vendor fflate 0.8.3（MIT）替换自研 ZIP 容器；vendored 单文件 = `esm/browser.js`（90,922B，自包含 ESM，上游 sha256 前 16 位 `B7CA4450B19559A1`），随附许可证文件并登记 vendor 表；`storage/zip.js` 退化为薄适配器：保持 buildZip/readZip 接口与我方错误码及上限检查，格式校验委托 fflate | 继续自研 ZIP 容器（8.7KB：CRC32 + 本地头/中央目录/EOCD）；minified UMD 33KB（全局脚本、非 ESM）；jszip（体积更大） | 上游发布修复版需升级时（重跑包合同与 V2.1.3 往返验证）；fflate 停更或许可变化时重选 |
| SEL-009 | V1 日落 | 用户已定（2026-09-30）：V2.7.4 发布候选冻结后，专批删除 Product V1 代码与随之失效的依赖（含自造重试/退避/文件锁：`src/imagegen.py` `_retry`、`src/application_service.py` 限流退避、`src/workspace_store.py` 文件锁）；git 历史保留，V1 证据不删除 | 边跑边删 V1；把 V1 主路径保留到 V2 完成 | V2.7.4 冻结时执行 V2.7.5；届时逐项复核依赖与工具引用 |
| SEL-010 | 图像网关传输层 | 复用 `requests`（V1 已在用的锁定直接依赖）+ 三条无状态路由（submit / status / result）；协议与错误映射按 §9.10 自写，但请求形状沿用 V1 冻结合同（`src/providers/dashscope_image.py`）；PoC 与依赖实测见 `evals/product-v2/sel010-image-gateway-transport-poc-20260930.txt` | 官方 `dashscope` SDK（0.27.x→1.27.7 实测解析 32 包，拖入 aiohttp / typer / websocket-client 等）；`httpx`（第二套 HTTP 客户端，无协议收益）；OpenAI 兼容图像端点（百炼图像合成不是该形状） | 需要批量并发、取消、多供应商路由或成本统计时重估 SDK；百炼改协议时按冻结合同重测并更新 §9.10 |

状态：SEL-000 至 SEL-010 已定案（2026-09-30）。依赖权威已从 `requirements.txt` 迁移到
`pyproject.toml` + `uv.lock`，守卫、CI、README 同步（证据见
`evals/product-v2/dependency-authority-migration-20260930.txt`）；依赖按 SEL-003 引入
（langchain-core / langchain-openai）；工作区中的 V2.2.2 适配器草案在任务完成前
仍不得写成已实现能力。

### 4.2 依赖与 vendor 登记

`tools/check_docs.py` 会把下面两张表与 `pyproject.toml` + `uv.lock`、`app/product_v2/vendor/`
做双向比对：新增依赖必须同时改登记表与 `pyproject.toml`（`uv add` 落锁），移除依赖必须两处同删。

依赖权威从 `requirements.txt` 迁移到 `pyproject.toml` + `uv.lock`（SEL-000 修订，2026-09-30；
删除 requirements 文件、守卫改读锁文件、CI 与 README 同步；证据见
`evals/product-v2/dependency-authority-migration-20260930.txt`）。

<!-- dependency-registry:begin -->
| 包 | 版本 | 许可 | 用途 | 引入决策 | 移除成本 |
|---|---|---|---|---|---|
| jsonschema | 4.26.0 | MIT | Draft 2020-12 结构契约校验（V1 合同与验证器） | V1 基线；V2 提案校验权威是 Pydantic（SEL-006），去留随 V1 日落逐项核实 | 小 |
| langchain-core | 1.6.6 | MIT | 语义调用与结构化输出原语 | SEL-003/007 引入（2026-09-30） | 中：换回直连要重写适配器 |
| langchain-openai | 1.6.6 | MIT | ChatOpenAI 指向百炼兼容端点 | SEL-003 引入 | 中 |
| numpy | 2.4.6 | BSD-3-Clause | V1 像素与数组运算 | V1 基线 | 中：V1 图像链路依赖 |
| pillow | 12.3.0 | MIT-CMU | 图像读写、尺寸与校验 | V1 基线；V2 图像链路继续使用 | 中 |
| python-dotenv | 1.2.3 | BSD-3-Clause | `.env` 本地加载 | V1 基线；V2.2.2 正式入口接线复用 | 小 |
| pyyaml | 6.0.3 | MIT | YAML 配置读取（V1 配置与守卫） | V1 基线 | 小 |
| requests | 2.34.2 | Apache-2.0 | V1 外部模型 HTTP 调用与验证工具 | V1 基线；V2 语义改经 langchain-openai（SEL-003）；V2 图像网关客户端在 V2.4.1 选型 | 小：集中在 V1 链路与 `tools/` |
| onnxruntime | 1.30.0 | MIT | 抠图可选组（cutout，不默认安装） | V1 基线；随 V1 日落后复核 | 小：optional 组 |
| rembg | 2.0.84 | MIT | 抠图可选组（cutout，不默认安装） | V1 基线；随 V1 日落后复核 | 小：optional 组 |
| playwright | 1.63.0 | Apache-2.0 | dev 组：浏览器合同验证 | SEL-005 CI 引入 | 小：dev 组 |
| pydantic | 2.13.5 | MIT | 语义契约模型（SEL-006 锁定的传递依赖） | SEL-006 | 小：随 langchain-core 传递 |
| openai | 3.20.0 | Apache-2.0 | 兼容客户端（langchain-openai 传递依赖） | SEL-003 链路传递引入 | 小：随 langchain-openai 传递 |
<!-- dependency-registry:end -->

CI 浏览器验证依赖来自 pyproject 的 dev 组（`playwright==1.63.0`，Apache-2.0），不进入生产镜像。
GitHub Actions 复用官方 `actions/checkout@v6`、`actions/setup-python@v6`，用 `uv sync --locked` 与
`uv run` 执行守卫、正式入口和浏览器验证；SEL-005 是引入依据。

<!-- vendor-registry:begin -->
| 文件 | 版本/来源 | 用途 | 引入决策 |
|---|---|---|---|
| fflate.browser.js | fflate 0.8.3（npm `esm/browser.js`，自包含 ESM，90,922B，sha256 `B7CA4450B19559A1D50EB381ADCEE94B82449674BE4CD17789D9BEBA7E6122A1`） | 浏览器 ZIP 读写（项目包导入导出） | SEL-008（2026-09-30 定，同批落地）；MIT |
| fflate.LICENSE.txt | fflate 0.8.3 MIT 许可证原文（1,069B，sha256 `0A1DF3A083D0C010560AA342E87959C8C1070E6FD54545741F083F22D0C8B551`） | 第三方许可证随附 | SEL-008；与库文件同批校验 |
<!-- vendor-registry:end -->

SEL-008 已落地（2026-09-30）：`storage/zip.js` 退化为薄适配器，结构解析与解压委托
fflate，只保留产品上限/错误码与逐条 CRC32 完整性校验（fflate 自身不校验 CRC32）。
升级上游时重跑包合同与 V2.1.3 往返验证，并更新本表哈希；证据
`evals/product-v2/sel008-fflate-vendoring-20260930.txt`。

## 5. 目标目录地图

```text
amz-listing-kit/
├─ app/
│  ├─ server.py                         # 正式服务入口：默认 V2；--legacy-v1 回 V1；--offline-fixture 旧 Mock
│  ├─ product_v1_server.py              # Product V1 历史实现，迁移期保留（--legacy-v1）
│  ├─ product_v2_server.py              # V2 无状态 HTTP 适配器：静态资源 + /api/health + capabilities + semantic/analyze
│  └─ product_v2/                       # V2 前端静态资源；domain/prompt.js 是 Prompt 编译与人工编辑唯一权威（V2.3.4 / V2.3.6）、domain/confirm.js 是生成前确认唯一权威（V2.3.5）、domain/review.js 是确定性校验（规则注册表 / ReviewReport）唯一权威（V2.5.1）；vendor/ 已 vendored fflate 0.8.3（SEL-008）
├─ src/
│  ├─ product_v2_contracts.py           # 领域与 API 契约（目标）
│  ├─ providers/                        # 语义链路已落地（v2_semantic / v2_dashscope_semantic / v2_fake_semantic）；图像网关已落地（v2_image / v2_dashscope_image / v2_fake_image）；错误词表唯一权威 = v2_errors.py；VLM ReviewProvider 仍是目标（V2.5.2，真实调用复用 SEL-003 的 langchain 通道）
│  └─ validators/                       # 未启用：确定性校验的唯一落点是 app/product_v2/domain/review.js（V2.5.1），本目录不建第二份
├─ config/
│  └─ product-v2/                       # provider 注册表（providers.json，已落地）；平台、模板与问题分类仍是目标
├─ docs/
│  ├─ INDEX.md                          # 文档身份和读取路由
│  ├─ product-v2-project-context.md     # 本文件
│  └─ product-v2-goal-and-implementation-plan.md
├─ _working/amz-listing-kit-product-v2/
│  └─ state.md                          # 唯一执行状态
├─ evals/product-v2/                    # V2 验证证据（目标）
├─ .github/workflows/ci-cd.yml           # PR/push CI；main Docker CD
├─ Dockerfile                            # 只打包 Product V2 正式运行入口
└─ tools/                               # 控制面、契约、浏览器和回归验证入口；v2_test_server.py 复用产品处理器 + fake provider
```

新增目录前先判断它属于实现、目标、状态还是证据；不能归类的目录先不建。目录地图描述的是目标落点，尚未存在的均标为“目标”，不能据此声称已经实现。

## 6. 不变约束

1. 模型输出是候选，不是事实、决定或完成证据。
2. 未确认商品事实不得进入带事实断言的图片方案和 Prompt。
3. 用户可以查看和修改完整 Prompt，但主路径不要求用户从零编写 Prompt。
4. 参考图、候选、历史 Prompt、返工结果和导出版本不被静默覆盖。
5. 修改事实、StyleSpec、ShotSpec 或 Prompt 必须按依赖范围使下游版本失效。
6. 一次 Shot 返工不得改变无关 Shot 的候选、任务身份和选择。
7. 外部调用超时是 `UNKNOWN`，不是失败；已知 task ID 先核对再决定是否重试。
8. VLM 负责发现问题，人工负责最终采纳；硬规则只来自可复现的确定性检查。
9. 主流程不需要主体分割或抠图；抠图仅可作为未来独立、显式选择的专项能力。
10. 服务器不保存用户项目状态；浏览器清理数据或 origin 变化造成的迁移由项目包解决。
11. 密钥只从服务器环境变量读取，不进入浏览器、Git、项目包或证据文件。

## 7. 质量门槛

| 层 | 必须证明什么 | 主要证据 |
|---|---|---|
| 控制面 | 唯一目标、唯一状态、唯一下一动作、文档全部登记 | `tools/check_docs.py`、`tools/check_project_state.py` |
| 领域与存储 | schema、迁移、事务、依赖失效和 Blob 生命周期正确 | 单元测试、反向探针、导入/导出哈希比对 |
| 服务合同 | 无服务器业务持久化；错误、Unknown 与 Provider 身份可恢复 | API 契约测试、服务器重启轨迹、磁盘差异审计 |
| 浏览器产品 | 空白启动、刷新恢复、完整主链、失败与窄屏可用 | Playwright、控制台/网络、IndexedDB 后置条件、视觉证据 |
| 生成系统 | 真实参考图、真实 Prompt、真实 task ID、候选和报告可追溯 | Provider 请求快照、模型记录、候选哈希、ReviewReport |
| 产品完成 | 陌生使用者能够独立完成不同品类任务 | 首次使用者走查、完成矩阵；Mock 或自评不能替代 |
| 格式检查 | 暂无 ruff/eslint：本仓库没有格式化工具链，格式由 `.gitattributes` 与评审保证 | 引入格式化工具需先过选型门（SEL 记录） |
| 静态检查 | 暂无静态检查器；等价手段是守卫脚本（`tools/check_*.py`）与 `node --check` 语法门 | 同上 |
| 单元测试 | 以验证入口（`tools/verify_*.py`）与反向探针为主，不以 pytest 收集为门槛 | 证据要求见计划 §12 与 `AGENTS.md` |
| 覆盖率 | 暂不设阈值：本项目的判据是“证据能判红”，不是行覆盖率 | 若引入覆盖率门槛，先立 SEL 决策并说明理由 |
| 应用构建 | 前端无需编译；Python 可直接运行；正式交付物是 CI 构建的 Docker 镜像 | `python app/server.py --check`、`docker build` |
| 容器交付 | 镜像只含正式 V2 运行资源；健康检查通过；部署失败可恢复上一容器 | `docker build`、容器 `/api/health`、GitHub Actions run 与部署日志 |

## 8. 上下文读取与写入路由

读取顺序与写入路由的**唯一权威**在 [`docs/INDEX.md`](INDEX.md)（§1 的恢复读取顺序、§5 的
「写入路由：改哪里，不改哪里」）。本节不再复制这两张表：两处都写、内容一致时它们仍会
各自漂移，读者也不知道该信哪一份。本文件回到自己的问题——项目是什么、怎样运行、
数据归谁、目录与质量门槛是什么。
