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

## 2. 当前事实基线

| 层 | 已实现事实 | Product V2 处理方式 |
|---|---|---|
| Product V1 | 本机文件夹工作空间、版本记录、真实 `qwen-image-3.0` 调用、候选、Unknown、单图返工、选择和导出均已有实现与回归证据 | 冻结为历史基线，复用业务语义和测试案例，不继续扩展服务器文件夹工作空间 |
| Product V2 | 已完成需求和架构重新裁定；浏览器存储层（IndexedDB schema、迁移、repository、事务与指针契约）与空白项目首页（本机项目 CRUD）已落地并有契约证据 | 商品资料、商品理解、套图、生成、审核与交付，以及无状态服务、DeepSeek 新适配和 VLM 校验尚未实现 |
| 参考模板 | `docs/standards-template/` 提供项目身份、活需求、进度和规范分工方法 | 采纳其要求（复用阶梯与选型门、人工确认门、活记忆精简、一类事实一个权威）落进现有五权威；GitHub/CD/Docker 步骤与 `standards/` 目录不适用。采纳映射、未采纳项与复访条件只在 `AGENTS.md` §Standards Mapping |

旧 Product V1 的“完成”只证明旧架构下的能力，不证明 Product V2 已经完成。Product V2 的任何完成声明必须重新取得范围匹配的证据。

## 3. 运行边界与数据所有权

```text
现代桌面浏览器
├─ localStorage：当前项目 ID、少量界面偏好
├─ IndexedDB：项目记录、参考图、候选图、任务身份、校验、选择和历史版本
└─ ZIP：完整项目包或最终交付包
        │
        │ 同源 HTTP；每次请求携带完成本动作所需上下文
        ▼
Python 无状态 AI 服务
├─ DeepSeek 语义分析
├─ 套图规划与 Prompt 编译
├─ qwen-image-3.0 提交、查询与结果转发
└─ 可替换视觉语言模型校验
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
| 宿主 | 本机 / 内网 | 默认绑定回环地址；不承诺公网部署 |
| 部署目录 | 无 | 不部署到服务器，不写系统服务，不建部署账号 |
| 容器 | 无 | 不提供 Dockerfile；引入需先补 SEL 决策（SEL-005） |
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

首版语义与图片模型均通过阿里云百炼调用，统一从环境变量读取 `DASHSCOPE_API_KEY`；不要求额外的 `DEEPSEEK_API_KEY`。模型名称分别由 `SEMANTIC_MODEL`、`IMAGE_MODEL` 配置，VLM 名称留到 V2.5.2 选择后再写入 `VLM_MODEL`。密钥不得进入浏览器状态、项目包、日志、证据或 Git。

### 4.1 选型记录

选型门禁的规则正文在仓库根 `AGENTS.md`；本节是**结论的唯一落点**：每条选型决策留一行，
写清约束、被拒方案与复访条件，避免下一个 Agent 重新讨论、重新实现已经决定过的问题。

| ID | 范围 | 决策 | 被拒方案 | 复访条件 |
|---|---|---|---|---|
| SEL-000 | 依赖政策 | 分层：Python 侧允许登记过的 pinned 依赖；浏览器侧保持无构建步骤，只允许 vendor 单文件库；业务语义层自研 | 全层放开 npm 构建链；全零新增依赖 | 前端需要组件框架或状态管理，或离线安装条件变化 |
| SEL-001 | 编排层 | 暂不引入 LangGraph / LangChain：业务状态权威是浏览器 IndexedDB，服务端无状态，不设第二个权威 | LangGraph checkpointer + 服务端状态 | 出现服务端自主多步编排，或需要跨进程恢复的长任务 |
| SEL-002 | 服务端 HTTP | 暂保留 stdlib `http.server`（零运行时依赖、端点少、单进程） | Flask / FastAPI + uvicorn | V2.4 图片上传/下载需要 multipart 与流式响应时重开 |
| SEL-003 | 语义/视觉调用传输层 | 待决：`openai` SDK（推荐）/ litellm / 继续 requests —— 讨论中 | — | 定稿后补全决策与被拒理由 |
| SEL-004 | 项目管理规范 | 采纳 `docs/standards-template/` 的**要求**，落进现有五份权威（映射见 `AGENTS.md` §Standards Mapping），不新建 `standards/` 平行目录 | 复制模板另立一套 standards/（会与计划/state 形成双权威） | 需要对外交付独立规范包时重开 |
| SEL-005 | 持续集成 | 不引入 CI/CD：本机与内网使用，门禁由 `tools/` 守卫脚本承担并写进提交纪律 | GitHub Actions + CD 自动部署 | 出现多人协作、远端仓库或部署目标时重开 |

状态：SEL-000 已写入 `AGENTS.md`；SEL-001、SEL-002、SEL-004、SEL-005 是当前工作决策，
用户确认后转正式（SEL-004/SEL-005 的落点与未采纳清单见 `AGENTS.md` §Standards Mapping）；
SEL-003 未定——未定之前不新增依赖。

### 4.2 依赖与 vendor 登记

`tools/check_docs.py` 会把下面两张表与 `requirements.txt`、`app/product_v2/vendor/`
做双向比对：新增依赖必须同时改登记表与 `requirements.txt`，移除依赖必须两处同删。

<!-- dependency-registry:begin -->
| 包 | 版本 | 许可 | 用途 | 引入决策 | 移除成本 |
|---|---|---|---|---|---|
| pillow | 12.3.0 | MIT-CMU | 图像读写、尺寸与白底检查 | V1 基线已锁版本；V2 图像链路继续使用 | 中：校验与导出依赖它 |
| numpy | 2.4.6 | BSD-3-Clause（含 0BSD/MIT/Zlib/CC0 组件） | 像素与数组运算（V1 合成、白底统计） | V1 基线已锁版本 | 中：V1 图像链路依赖它 |
| requests | 2.34.2 | Apache-2.0 | 外部模型 HTTP 调用（V1 适配器与 V2.2 语义适配器） | V1 基线；SEL-003 讨论中可能被模型 SDK 取代 | 小：集中在 `src/providers/` |
| PyYAML | 6.0.3 | MIT | 读取 `slots.yaml`、平台与品类配置 | V1 基线已锁版本 | 小：配置读取集中 |
| python-dotenv | 1.2.3 | BSD-3-Clause | 本地 `.env` 加载（`run.py`） | V1 基线已锁版本 | 小：入口一处 |
| jsonschema | 4.26.0 | MIT | 结构契约校验（Draft 2020-12） | V1 基线已锁版本；V2 提案校验继续使用 | 小：契约校验集中 |
<!-- dependency-registry:end -->

<!-- vendor-registry:begin -->
| 文件 | 版本/来源 | 用途 | 引入决策 |
|---|---|---|---|
<!-- vendor-registry:end -->

当前 `app/product_v2/vendor/` 不存在——浏览器端零第三方库。引入第一个 vendor 库前先补
SEL 决策，再建目录、再登记。

## 5. 目标目录地图

```text
amz-listing-kit/
├─ app/
│  ├─ server.py                         # 正式服务入口：默认 V2；--legacy-v1 回 V1；--offline-fixture 旧 Mock
│  ├─ product_v1_server.py              # Product V1 历史实现，迁移期保留（--legacy-v1）
│  ├─ product_v2_server.py              # V2 无状态 HTTP 适配器（已落地，V2.1.4）
│  └─ product_v2/                       # V2 前端静态资源；storage/、domain/ 契约、项目首页、项目包与正式入口均已落地
├─ src/
│  ├─ product_v2_contracts.py           # 领域与 API 契约（目标）
│  ├─ providers/                        # DeepSeek、Qwen、VLM 适配器（目标）
│  ├─ prompt_compiler.py                # 纯编译边界（目标）
│  └─ validators/                       # 确定性验证器（目标）
├─ config/
│  └─ product-v2/                       # 平台、模板、问题分类和 provider 注册（目标）
├─ docs/
│  ├─ INDEX.md                          # 文档身份和读取路由
│  ├─ product-v2-project-context.md     # 本文件
│  └─ product-v2-goal-and-implementation-plan.md
├─ _working/amz-listing-kit-product-v2/
│  └─ state.md                          # 唯一执行状态
├─ evals/product-v2/                    # V2 验证证据（目标）
└─ tools/                               # 控制面、契约、浏览器和回归验证入口
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
| 构建 | 无构建产物：Python 直接运行 + 浏览器原生 ESM | `python app/server.py --check` |

## 8. 上下文读取与写入路由

读取顺序与写入路由的**唯一权威**在 [`docs/INDEX.md`](INDEX.md)（§1 的恢复读取顺序、§5 的
「写入路由：改哪里，不改哪里」）。本节不再复制这两张表：两处都写、内容一致时它们仍会
各自漂移，读者也不知道该信哪一份。本文件回到自己的问题——项目是什么、怎样运行、
数据归谁、目录与质量门槛是什么。
