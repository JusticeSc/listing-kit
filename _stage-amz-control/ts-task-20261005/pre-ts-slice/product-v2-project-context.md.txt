# amz-listing-kit Product V2 项目上下文

> CONTROL-STATUS: current · AUTHORITY: project-context
> 本文件回答“项目是什么、怎样运行、数据归谁、目录与质量门槛是什么”。产品目标、验收与任务图只在
> [`product-v2-refactor-plan.md`](product-v2-refactor-plan.md) 维护；执行位置只在
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
| Product V1 | 本机文件夹工作空间与旧完整生图闭环冻结为回归基线；只复用业务语义、Provider 经验和测试案例；重构最终人审与日落前回退审计后由 V2.R7.3 专批删除（SEL-009） | 当前仍可运行的行为见 `README.md` 的历史入口；设计与完成轨迹从 `docs/INDEX.md` 的 superseded 文档进入 |
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
├─ DeepSeek 仅文字商品分析（当前 reference_images=false）
├─ qwen-image-3.0 异步链 / 火山 doubao-seedream 同步生图
└─ qwen-vl-max 候选/整套复核（不等于已实现商品看图理解）
        │
        ▼
外部模型 Provider
```

### 3.1 权威状态

- **用户项目权威**：浏览器 IndexedDB。
- **当前项目指针**：同一浏览器 origin 下的 localStorage。
- **外部生成执行权威**：Provider的受理/结果；异步使用真实task ID，同步以原请求/action身份及结果字节追溯。浏览器保存冻结身份与观察历史，不为同步协议伪造task。
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
| 容器 | `amz-listing-kit:<git-sha>` | 镜像只含V2正式入口；发布事务（`deploy/release-transaction.sh`）把 previous 应用容器与 Caddy 配置备份保留到容器健康、外部 HTTPS、静态资源/版本指纹及约定页面主链全部验收结束，全部通过才 finalize 清理；任一必要失败回退并核对实际可用性 |
| 密钥来源 | 环境变量及已实现图像请求级BYOK | 变量见`.env.example`/§4.2；其他用途客户端配置仍是目标，不据服务器key或图像头宣称全用途完成 |

浏览器支持与 origin 取值由 SEL-012 固定：本机开发可用 `http://127.0.0.1` / `localhost`；远程正式入口必须经可信 HTTPS 暴露。固定端口 `8780` 是容器内部/服务器监听端口，不等于要求用户直接访问明文 `http://<IP>:8780`。

2026-09-30 落地（V2.UI.1）：TLS 终止在 Caddy 容器（配置 `deploy/caddy/Caddyfile`，由 `.github/workflows/ci-cd.yml` 的部署步骤收敛），使用 Let's Encrypt IP 证书 shortlived profile 自动续期，HTTPS 对外监听 8080；云安全组丢弃 443，大陆对未备案域名的 80 端口请求返回拦截页（`Server: Beaver`），因此不使用域名证书。应用容器继续只提供无状态 HTTP，当前试用入口为 `https://47.115.172.233:8080/`；明文 `http://47.115.172.233:8780` 只作负例，页面会精确提示缺的是安全上下文/WebCrypto。

## 4. 技术栈与可替换边界

| 层 | 当前选择 | 边界 |
|---|---|---|
| 前端 | 原生 HTML、CSS、JavaScript | 延续现有低依赖路线；业务状态通过 repository/service 接口访问，不让 DOM 成为状态源 |
| 浏览器持久化 | IndexedDB + Blob；localStorage 只放轻量指针 | 当前格式事务、容量提示、项目导入/导出；开发态旧版本兼容不要求（SEL-018）；不把图片 Base64 塞进 localStorage |
| 服务端 | Python；正式入口 `app/server.py` 默认启动 Product V2 无状态适配器（`--legacy-v1` 回 V1） | 服务方法无用户工作空间参数；请求进、模型响应出；正式入口不读写工作空间或最近项目索引 |
| 商品文字分析 | `deepseek-v4.1-flash`，经SemanticProvider适配 | 当前不发参考图，只产出事实提议；图文商品理解目标按计划§14.7，不能用元数据冒充看图 |
| 图片模型 | `qwen-image-3.0` 与大陆火山 `doubao-seedream-5-0-flash-260915` | 两个有限协议Adapter消费参考图；同步/异步归一业务结果，主流程不抠图、不部署本地分割模型 |
| 视觉复核 | `qwen-vl-max`，候选及整套各自业务合同 | 当前多模态传输可复用，复核schema不能冒充商品理解；可选辅助/交付政策以计划§14.8为准 |
| 确定性规则 | 版本化平台、文件、槽位依赖与状态规则 | 不把审美或模型自评伪装成硬规则 |
| 服务端数据库 | 无 | Product V2 不引入数据库、账户、租户或服务器项目索引 |
| 交付运行时 | Docker + GitHub Actions | CI 先验证同一 Dockerfile；远程服务器 Docker 从该提交的最小上下文构建 SHA 镜像并运行 |

当前provider配置权威为 `config/product-v2/providers.json`，运行时由registry解析并注入消费者；百炼采用 `DASHSCOPE_API_KEY`、火山采用 `ARK_API_KEY`，无需额外DeepSeek key。图像已有请求级BYOK通道，不能据此声称理解/复核也已支持客户端选择与凭据；全用途目标见计划§14.7，具体差距见state。模型/参数不靠两份环境变量说明猜测；秘密不进持久化、包、日志、证据或Git，默认档受SEL-015的fail-closed约束。

### 4.1 选型记录

选型门禁的规则正文在仓库根 `AGENTS.md`；本节是**结论的唯一落点**：每条选型决策留一行，
写清约束、被拒方案与复访条件，避免下一个 Agent 重新讨论、重新实现已经决定过的问题。

| ID | 范围 | 决策 | 被拒方案 | 复访条件 |
|---|---|---|---|---|
| SEL-000 | 依赖政策 | Python pinned 依赖仍由 pyproject.toml + uv.lock 管理；浏览器原生 ESM，无产品构建。渐进前端工具已按 SEL-021 单独批准并锁根 package.json/package-lock.json；构建/框架仍需实际成本与独立选型，不把低依赖变成拒绝类型检查的理由；领域规则自研、通用原语复用 | 未经选型直接放开 npm/全仓 TS/框架；全零工具；多份 manifest/lock 权威 | 工具 PoC、实际 DOM 维护痛点、离线安装约束变化时 |
| SEL-001 | 编排层 | 不引入 LangGraph 与 Agent/Memory 编排，服务端保持无状态（业务状态权威是浏览器 IndexedDB）；引入 `langchain-core` / `langchain-openai` 仅作提示词、模型调用与结构化解析原语（见 SEL-003），不承担状态与编排 | LangGraph checkpointer + 服务端状态；Agent/Memory 编排 | 出现服务端自主多步编排，或需要跨进程恢复的长任务 |
| SEL-002 | 服务端 HTTP | 暂保留 stdlib `http.server`（零运行时依赖、端点少、单进程） | Flask / FastAPI + uvicorn | V2.4 图片上传/下载需要 multipart 与流式响应时重开 |
| SEL-003 | 语义/视觉调用传输层 | 用户已确认（2026-09-30）：`langchain-core` + `langchain-openai` 的 `ChatOpenAI` 指向百炼 OpenAI 兼容端点（`deepseek-v4.1-flash`）；显式 timeout、`max_retries=0`（禁止隐藏重试）；失败映射进 `v2_semantic` 四类归口。版本：langchain-core 1.6.6、langchain-openai 1.6.6（均 MIT）；依赖实测与 PoC 报告见 `evals/product-v2/sel003-transport-selection-20260929.txt` | LiteLLM（59 包，为单一兼容协议付 4 倍依赖）；`requests` 手写适配器（重复造 HTTP/重试轮子）；OpenAI SDK 直连（已含于 langchain-openai，不建双轨） | 接入第二个供应商或需要路由/降级/成本统计时评估 LiteLLM；需要 OpenAI 专有能力时评估直连。PoC 已发现：`deepseek-v4.1-flash` 为推理型输出，需给 reasoning 留预算 |
| SEL-004 | 项目管理规范 | 采纳 `docs/standards-template/` 的**要求**，落进现有五份权威（映射见 `AGENTS.md` §Standards Mapping），不新建 `standards/` 平行目录 | 复制模板另立一套 standards/（会与计划/state 形成双权威） | 需要对外交付独立规范包时重开 |
| SEL-005 | 持续交付 | 采用GitHub Actions + Docker：PR/push执行既有CI，main通过SSH在远程构建SHA镜像并发布，固定origin/端口。当前自动回退覆盖启动/健康；完整发布事务及数据恢复目标只读计划§7.4/§7.7，R7.4修复提前清理旧容器的缺口，不在规约准备中改流水线 | 新镜像仓库/编排平台、容器健康冒充用户主链、容器回滚冒充浏览器数据恢复 | 发布验收范围或数据格式改变时；合并授权取AGENTS/计划§16，不绕过分支保护 |
| SEL-006 | 语义契约表示 | Python 侧契约表示权威 = Pydantic（langchain-core 自带，锁定 2.13.5）：请求 / 原始提案 / 提案槽位三类模型 + 跨字段校验；校验作用在模型原始输出；错误四类归口、归一化映射、浏览器侧 `checkFactSlot` 与 `CORE_SLOT_REGISTRY` 保留 | Python 侧继续手写形状/不变量校验（重复造轮子，违反复用门）；浏览器改吃 schema（受 SEL-000 无构建约束，且与 SEL-001 状态权威错位） | V2.6.3 项目包跨版本迁移需要 schema 版本与迁移器时，以“契约权威”为题重开（评估 JSON Schema 作中立权威 + 双语言消费者） |
| SEL-007 | LangChain 使用边界 | v1 直调形态：`ChatOpenAI.with_structured_output(原始提案模型, method="json_mode", include_raw=True)`；系统/用户消息直接构造，JSON 格式说明由 Pydantic schema 生成并注入系统提示；LCEL 管道、ChatPromptTemplate、Agent/Memory 均不使用（保留为库内可用能力，不是本项目范式）；装配与错误分类的操作细节见计划 §9.1 | LCEL 管道（0.x 主推范式）；默认 `method="json_schema"`（百炼对自定义模型名的支持未证实；不支持时 400 且会被误分类）；`method="function_calling"`（依赖该模型在百炼的函数调用支持）；ChatPromptTemplate | 百炼确认支持 `response_format: json_schema` 时把 method 切换回默认（改一个装配参数 + 重跑契约测试）；需要多步编排时按 SEL-001 的复访条件另立决策 |
| SEL-008 | 浏览器 ZIP 能力 | 用户已定（2026-09-30）：vendor fflate 0.8.3（MIT）替换自研 ZIP 容器；vendored 单文件 = `esm/browser.js`（90,922B，自包含 ESM，上游 sha256 前 16 位 `B7CA4450B19559A1`），随附许可证文件并登记 vendor 表；`storage/zip.js` 退化为薄适配器：保持 buildZip/readZip 接口与我方错误码及上限检查，格式校验委托 fflate | 继续自研 ZIP 容器（8.7KB：CRC32 + 本地头/中央目录/EOCD）；minified UMD 33KB（全局脚本、非 ESM）；jszip（体积更大） | 上游发布修复版需升级时（重跑包合同与 V2.1.3 往返验证）；fflate 停更或许可变化时重选 |
| SEL-009 | V1 日落 | 已批准方向不变：先通过重构最终人审（V2.R7.2），形成日落前可回退基线，再由 V2.R7.3 经专批删除 V1 和真实失效依赖；保留历史证据，删后重跑完整回归/主链及最终指纹 | 边重构边删；跳过人审/基线；沿用删除前发布指纹 | V2.R7.2 与日落前审计通过时逐项核对引用；本轮未授权删除 |
| SEL-010 | 图像网关传输层 | 复用 `requests`（V1 已在用的锁定直接依赖）+ 三条无状态路由（submit / status / result）；协议与错误映射按 §9.10 自写，但请求形状沿用 V1 冻结合同（`src/providers/dashscope_image.py`）；PoC 与依赖实测见 `evals/product-v2/sel010-image-gateway-transport-poc-20260930.txt` | 官方 `dashscope` SDK（0.27.x→1.27.7 实测解析 32 包，拖入 aiohttp / typer / websocket-client 等）；`httpx`（第二套 HTTP 客户端，无协议收益）；OpenAI 兼容图像端点（百炼图像合成不是该形状） | 需要批量并发、取消、多供应商路由或成本统计时重估 SDK；百炼改协议时按冻结合同重测并更新 §9.10 |
| SEL-011 | 复核（VLM）通道与模型 | 用户已定（2026-09-30）：复核复用 SEL-003 的 langchain 通道（`ChatOpenAI` + json_mode 结构化输出 + `map_openai_exception` 四归口），默认模型 `qwen-vl-max`（`REVIEW_MODEL` 可覆盖，registry 条目 `dashscope-review`）；输入 = 候选 + ≤3 参考图 + ShotSpec 摘要 + 已确认事实；输出只允许 7 个 check + evidence + confidence；VLM 只提示、不得 BLOCK、失败落 Unknown、不产生采纳 | 新建第二套 HTTP 客户端/适配器层（重复造轮子）；官方 SDK（拖包）；让模型自带严重度或采纳结论；把审美判断升级为平台硬阻断 | 需要多模态模型路由/降级或成本统计；百炼模型命名/能力变化；检出质量校准需要模型对比时（后续任务） |
| SEL-012 | 浏览器支持与安全 origin | 用户恢复后的当前 Goal 验证范围为稳定版桌面 Chrome（计划 §2.4）；旧 Chrome/Edge 专项记录保留历史身份，不宣称 Edge 本轮通过。远程正式入口必须是可信 HTTPS secure context，TLS 由现有穿透/反向代理终止，应用容器保持无状态 HTTP。保留 IndexedDB + 原生 WebCrypto；不为明文 HTTP 自研 UUID/SHA-256、密码学 polyfill 或服务器项目存储；失败区分能力/schema/配额/事务并给恢复动作 | 浏览器手写密码学降级、服务端项目库、把所有宿主纳入保证范围、用无头结果替真人走查 | 当前 Goal 的浏览器范围或实际受控宿主需求改变时重开；先证明真实约束 |
| SEL-013 | 可访问性扫描 | 用户已定（2026-10-01，自审授权范围内）：vendor axe-core 4.13.0（MPL-2.0）单文件到测试侧 `evals/product-v2/vendor/`，由 `tools/verify_v2_6_4_accessibility.py` 注入正式入口页面运行扫描；不新增构建链、不进产品运行时 | 运行时 CDN 引入（不可离线复现）；npm/pip 构建依赖（违反 SEL-000 无构建链）；自写规则引擎（重复造轮子） | axe 上游大版本升级（重跑可访问性终验）；MPL 许可变化；需要运行时无障碍报告时重估 |
| SEL-014 | 重构运行形态与模型范围 | 用户确认：浏览器本地优先 + 无业务持久化 Python 网关；模型不是核心卖点，仅有限模型解耦；第二生图已锁定大陆火山 `doubao-seedream-5-0-flash-260915`（R4.1 锁方向 / R4.2 真链 / R5.2 同步 Adapter `v2_volcengine_image.py`），`providers.json` 双 image 条目 `dashscope-image` + `volcengine-ark`，不迁 Node 或引入服务端项目库 | 胖后端/账户数据库、全栈 TS、任意模型平台、仅换 model 字符串冒充生图兼容 | 跨设备/协作/后台持续执行成为实际需求，或有限协议维护成本实测不可接受时 |
| SEL-015 | 凭据产品政策 | 用户确认：BYOK 为主，部署默认档仅受限试用；默认 key 不下发、不附到用户 endpoint。BYOK 为内存会话 + HTTPS 请求级使用、不进本地持久化/包/日志/错误/诊断；R4.3 已实现图像 `X-AMZ-Listing-Key-Image` 单次请求内存态，出站 `v2_outbound.py` 白名单 `aliyuncs.com` + `volces.com`（R5.2 接入火山），线上 `default_trial=closed`；第二协议认证方式确定后复访实现 |
| SEL-016 | 前端工程化与 UI | 用户确认渐进类型检查/验证分层与 UI 人体工程审计方向；先实际任务基线，再原型和目标合同；复用已有业务语义但不将现有 domain/repository 或页面结构设为不可替换；不预定布局、六强制步骤、React/Vue、构建工具或全仓 TS；按 SEL-018 允许激进 clean cutover | 先换皮/拆文件、框架即工程化、机械降低点击而取消必要确认、Skill 代替真页面证据 | V2.R2/R3.1 的问题/原型/PoC 提供明确收益时选择工具与布局 |
| SEL-017 | Goal历史与当前绑定 | 历史原生handle/观察只保留原证明范围，新会话重读实际Goal。本轮用户手动触发后的正文/绑定只看计划§2.1及state；启动方案和编制来源在§16，不重复创建、不绑旧ID，不在context复制授权/预算 | 旧ID承担新正文、假状态、双计划/进度、方案确认冒充启动许可 | 新会话或目标变化时核对实际工具返回，按计划§16.2同步真实正文/绑定/受影响状态 |
| SEL-018 | 开发态兼容与设计自由度 | 用户明确：“不用考虑历史兼容性，现在仍在开发阶段，允许你做激进的设计。”旧版本/schema/包迁移及真实旧工件恢复不再要求；按计划 §2.3 clean cutover，可重做 Module/Interface/UI/记录格式、移除被替代路径；新开发库/旧格式拒绝须显式，不静默删除浏览器数据。同版本候选历史、人工选择、任务冻结身份、刷新恢复、ZIP哈希及安全不变量保留；其余权限门不变 | 为缺失旧测试包停工、保留向后兼容 shim/迁移层、将激进设计当作静默丢数据或付费/部署/V1删除授权 | 首次正式发布/存在需支持的历史用户数据时，重新定义版本兼容承诺；开发期不预建设迁移层 |
| SEL-019 | 问题导向参考系统研究 | V2.R2.3 已核查 pi `88ff80b`/0.99.2（MIT）、ComfyUI `2d6b7328`/0.38.0（GPL v3）、Open WebUI `8bd8b4f`/0.11.4（自定义品牌约束许可），固定全文 SHA/路径见 `evals/product-v2/refactor/reference-review-20261001.md`。仅采纳概念：用途/能力/协议 Adapter/凭据分层；交付只读采用候选原 action 的冻结 Prompt，不读当前编辑头；同 Shot 直接图片对照与稳定候选导航；Unknown 分身份恢复、状态/影响/下一动作先于技术详情。BYOK 仍仅内存，概念不等于新依赖或真实能力证明，布局由 R2.2 原型冻结 | 复制三套平台/代码/样式/品牌、账户或服务器项目库、pi 聊天兼容冒充图片协议、上游持久凭据照搬 IndexedDB、Comfy 元数据新功能、隐式自动重提/采用/付费、未选型新运行依赖 | R2.2/R4.1/R4.2 的原型/能力/费用证据；确需复制代码或引入库时重开许可/依赖门 |
| SEL-020 | 电商参考 skill 问题导向复核 | V2.R2.2 只读核查工作区根三目录：`ecommerce-image-suite-main/`（Apache-2.0 但 README 陈旧矛盾、占位符未填、模特/实拍无许可）、`ecom-details-image-main/`（自称 MIT 但无 LICENSE 文件，`.env.example` 含第三方代理明文 key 泄漏样本）、`ecommerce-skills-main/`（MIT 2026 dlazy，实读 platform-compliance/detect-task/item-detail＋shared 脚本/测试/规格）。结论：三者只提供流程编排与规格清单（批次 manifest、参考图锁定、先单图后整套、客观像素机检＋主观 VLM 质检分层、固定质检 prompt、中文排版四条件、逐轮 manifest、dry-run、不伪造测量），均无图片结果验收实现（保真/文字/事实/尺寸/齐全性须 amz 自建）；零字节复制，不复制代码/模板/样式/品牌/资产/凭据，不引入 Node 脚本链与真实调用/付费；证据 `evals/product-v2/refactor/prototype-review-20261002.md` §5 | 未经许可复制代码/模板原文、样式/模特/实拍资产、品牌与联系方式；硬编码供应商分支冒充解耦；真实模型调用/付费上传；把 prompt 自述或人工观感当验收结论；复用泄漏凭据 | R6 验收自建时复用 rubric/阈值数据；确需复制代码或引入依赖时重开许可/依赖门 |
| SEL-021 | 前端开发检查与渐进TS迁移 | 用户明确批准开发期检查器：根 package.json/package-lock.json 锁 typescript 6.0.3（Apache-2.0，无传递安装依赖），安装禁用 scripts；JSDoc/checkJs/noEmit，Node 24.19.0/npm 11.17.0，行为验证复用 node:test。真实领域 strict PoC 零诊断，错误 Shot ID 类型负例 TS2322；根开发依赖不进产品静态根或生产运行时。2026-10-05用户新增逐步TS迁移，并明确随当前功能验证穿插推进，任务合同只读计划§9 V2.R7.5；当前运行仍JS/ESM，迁移时先验证现有编译器的最小ESM产物方案，同步开发/CI/交付路径，不引入框架。既有类型接线归R3.2，历史证据 frontend-selection-20261002.md、frontend-approval-20261002.json 不证明TS已迁移 | 全仓TS强迁移、框架先行、类型检查等同node --check、编译器进入生产运行时、多份手工Implementation或依赖锁、隐式npx取包 | 本次逐批迁移先核实编译/静态交付成本和实际类型覆盖；新增依赖仍过选型门；移除dev工具成本小，浏览器ESM与业务合同保留 |

SEL-000..013 中对旧计划 §9.x 的操作设计引用仍指冻结的
`product-v2-goal-and-implementation-plan.md`，不把历史操作说明当未来任务。
SEL-014..021保存技术方向和固定来源；SEL-021工具已批准，第二生图及旧授权来源在计划§12，本轮启动方案在§16。当前执行绑定与前沿取state，不据历史工程/发布授权施工；新框架或依赖仍过选型门。

状态：SEL-000 至 SEL-011 已定案（2026-09-30）。依赖权威已从 `requirements.txt` 迁移到
`pyproject.toml` + `uv.lock`，守卫、CI、README 同步（证据见
`evals/product-v2/dependency-authority-migration-20260930.txt`）；依赖按 SEL-003 引入
（langchain-core / langchain-openai）。现有文字分析、图像与复核能力按实际装配/证据说明；
新增图文商品理解和全用途客户端设置仍是目标，不据复用库或模型名称宣称已接通。

### 4.2 依赖与 vendor 登记

`tools/check_docs.py` 双向核对 Python 的 pyproject/uv.lock、前端开发期根 package.json/package-lock.json
及 vendor 登记。每类依赖只有一份 manifest/lock 权威；新增/移除必须同步对应登记，不放开任意 npm 包。

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
GitHub Actions 复用官方 actions/checkout@v6、actions/setup-python@v6（SEL-005）；前端复用
官方 [setup-node v6.4.0](https://github.com/actions/setup-node/tree/v6.4.0)，固定 commit
`48b55a011bda9f5d6aeb4c2d9c7362e8dae4041e`（MIT，已核 LICENSE/API tag；SEL-021）。
Node 从根 engines 读精确版本，CI 安装同 engines 的 npm 后 npm ci 禁 scripts；禁自动缓存，不引入
产品构建/Node 运行时/认证框架。uv sync --locked 与 uv run 继续执行 Python/浏览器验证。

前端开发期版本合同：Node `24.19.0`、npm `11.17.0`，来源为本机已安装工具；根 manifest/lock 锁定，
R3.2 CI 已声明接线（尚待集成验证）；Node 只用于验证，Python/静态 ESM 仍是产品运行时。安装只允许已批准包，使用
`npm ci --ignore-scripts`，不通过 npx 隐式下载工具。当前依赖仅 typescript，一个 dev 包，无传递安装依赖。

<!-- frontend-dependency-registry:begin -->
| 包 | 版本 | 许可 | 用途 | 引入决策 | 移除成本 |
|---|---|---|---|---|---|
| typescript | 6.0.3 | Apache-2.0 | dev-only JSDoc/checkJs/noEmit | SEL-021；用户明确批准 | 小：删除开发依赖、锁条目与检查配置 |
<!-- frontend-dependency-registry:end -->

<!-- vendor-registry:begin -->
| 文件 | 版本/来源 | 用途 | 引入决策 |
|---|---|---|---|
| fflate.browser.js | fflate 0.8.3（npm `esm/browser.js`，自包含 ESM，90,922B，sha256 `B7CA4450B19559A1D50EB381ADCEE94B82449674BE4CD17789D9BEBA7E6122A1`） | 浏览器 ZIP 读写（项目包导入导出） | SEL-008（2026-09-30 定，同批落地）；MIT |
| fflate.browser.d.ts | 自研类型边界（随 `fflate.browser.js` 同目录，仅 `zipSync/unzipSync` 两入口及所用选项形状） | TypeScript checkJs/noEmit 下 `storage/zip.js` 的 vendor 导入类型（不进运行时） | SEL-021 开发期检查；随库文件同目录校验，不改第三方实现 |
| fflate.LICENSE.txt | fflate 0.8.3 MIT 许可证原文（1,069B，sha256 `0A1DF3A083D0C010560AA342E87959C8C1070E6FD54545741F083F22D0C8B551`） | 第三方许可证随附 | SEL-008；与库文件同批校验 |
| axe-core.min.js | axe-core 4.13.0（npm `axe.min.js`，IIFE 单文件，580,491B，sha256 `C24F097BD2F451D4F933E8BC7D8D539F8672A2EBCB5CC9F9F3EEC8CA9470A0C1`） | 可访问性扫描（测试侧注入正式入口页面，不进产品运行时） | SEL-013（2026-10-01 定，同批落地）；MPL-2.0 |
| axe-core.LICENSE.txt | axe-core 4.13.0 MPL-2.0 许可证原文（15,921B，sha256 `AF175B9D96EE93C21A036152E1B905B0B95304D4AE8C2C921C7609100BA8DF7E`） | 第三方许可证随附 | SEL-013；与库文件同批校验 |
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
│  ├─ product_v2_server.py              # 当前无状态HTTP装配：静态/health/capabilities、semantic/analyze、images submit/status/result、review/candidate及review/suite；尚无商品图文理解合同
│  └─ product_v2/                       # V2 前端静态资源；domain/prompt.js 是 Prompt 编译与人工编辑唯一权威（V2.3.4 / V2.3.6）、domain/confirm.js 是生成前确认唯一权威（V2.3.5）、domain/review.js 是确定性校验与 VLM 复核映射（规则注册表 / ReviewReport）唯一权威（V2.5.1 / V2.5.2）、domain/compare.js 是候选比较与审核清单排序的视图模型唯一权威（先看顺序仍取自 review.js 的 REVIEW_SEVERITY_ORDER，V2.5.3）、domain/rework.js 是九类返工问题与 ReworkDirective 返工指令合同的唯一权威（比较区保持只读，V2.5.4）、domain/selection.js 是人工选择（SelectionRecord/SelectionSet、采用/改选/取消与失效判断）唯一权威（V2.6.1）；vendor/ 已 vendored fflate 0.8.3（SEL-008）
├─ src/
│  ├─ providers/                       # 分用途业务合同、registry/credentials/outbound、有限协议Adapter；v2_langchain_chat共享已批准图文传输；v2_errors.py为错误词表
│  └─ validators/                       # 未启用：确定性校验的唯一落点是 app/product_v2/domain/review.js（V2.5.1），本目录不建第二份
├─ config/
│  └─ product-v2/                      # providers.json为有限配置权威；平台/模板/规则继续集中前端domain，不迁出第二份表
├─ docs/
│  ├─ INDEX.md                          # 文档身份和读取路由
│  ├─ product-v2-project-context.md     # 本文件
│  └─ product-v2-refactor-plan.md        # 当前目标/任务；旧 goal-and-implementation-plan 是历史基线
├─ _working/amz-listing-kit-product-v2/
│  └─ state.md                          # 唯一执行状态
├─ evals/product-v2/                   # 时间点证据，不是规约或进度权威
├─ .github/workflows/ci-cd.yml           # PR/push CI；main Docker CD
├─ Dockerfile                            # 只打包 Product V2 正式运行入口
└─ tools/                               # 控制面、契约、浏览器和回归验证入口；v2_test_server.py 复用产品处理器 + fake provider
```

新增目录前先判断它属于实现、目标、状态还是证据；不能归类的目录先不建。目录地图描述的是目标落点，尚未存在的均标为“目标”，不能据此声称已经实现。

### 5.1 业务模块与承接边界

业务合同只在计划§14；本节规定实现落点，不复制需求矩阵或另立状态机。下表是**本轮目标职责**，不是现有代码全部满足这些边界的声明。复用现有Module和domain，不先建万能facade、独立人工数据模型或公共合同大文件。

| 职责 | 既有落点 | 接口/状态边界 |
|---|---|---|
| 资料与事实 | domain/intake、slots、brief；workspace事实入口；repository | 人工与模型都提交同一领域动作；source保留证据来源，actor控制权限，status表示确认。输入草稿、提议与confirmed投影分开 |
| 图片任务与需求 | domain/suite-plan、specs | 用途/模板及事实/参考图依赖单一注册；可保存不完整任务，逐Shot派生就绪/缺项，UI和Python不重建表 |
| 本地准备与确认 | domain/prompt、confirm、invalidation；workspace编排 | 确定性编译与消费Basis，人工文本保护；确认取实际请求摘要，不强制调用文字模型或多次页面确认 |
| 会话与存储 | project-session、storage/repository及db | ready/身份/生命周期/OCC、文档版本、追加观察及Blob事务；异步回调归属原快照，事务不await网络 |
| 生成执行 | generation；domain/attempt、batch、rework、candidate | 单张/批量/返工同一执行顺序；冻结登记先于外发，partial/Unknown保持原身份，不在UI拼第二路径 |
| 比较与采用 | domain/compare、selection、review；workspace候选区 | 查看/对照仅视图，Selection只由人改变；本地确定性检查与可选AI建议分别当前，异步不夺焦点 |
| 交付与恢复 | domain/suite-review、export-gate；storage/package、transfer及ZIP | 保留当前确定性测量/报告门，AI未运行状态与模型Unknown解耦；采用候选原动作决定manifest，当前包/秘密隔离保持 |
| 模型边界 | product_v2_server；providers/semantic、review、suite_review、image及registry/credentials/outbound/langchain_chat | 无业务落盘；请求级有限有效配置/凭据，共享传输不共享错误业务schema。商品看图理解需要独立提议合同，不复用要求candidate的复核请求 |
| UI投影 | index、workspace、ui/stage-shell及styles | 默认任务/就地高级/非秘密诊断投影同一快照；六入口不是业务门，操作前置取domain/能力，不自造权限 |

Interface是可调用的业务动作及可渲染快照，不等于HTTP或额外转发层；Seam是可替换协议/凭据/传输/存储等边界。fake仅替外部模型，保持正式装配和领域消费，不能以fake出图证明真模型理解/忠实度。

落实时对齐入口、纯规则、repository后置和正式出站捕获；基础配置在R4.3闭合现有消费者，新图文业务消费者由R6.1后续承接，最终全用途仍由G6/RC07验收。接口表写完不是实现完成；依赖、需求修订后的done和准备启动步骤只读计划§6/§7.5/§16，state不复制合同。


## 6. 不变约束

1. 模型输出是候选，不是事实、决定或完成证据。
2. 未确认商品事实不得进入带事实断言的图片方案和 Prompt。
3. 用户可以查看和修改完整 Prompt，但主路径不要求用户从零编写 Prompt。
4. 参考图、候选、历史 Prompt、返工结果和导出版本不被静默覆盖。
5. 修改事实、StyleSpec、ShotSpec 或 Prompt 必须按依赖范围使下游版本失效。
6. 一次 Shot 返工不得改变无关 Shot 的候选、任务身份和选择。
7. 外部调用超时是 `UNKNOWN`，不是失败；已知 task ID 先核对再决定是否重试。
8. VLM只提出可选建议，人工决定采用；硬规则来自可复现的确定性检查。无AI报告不强制付费复核，准确交付政策唯一在计划§14.8。
9. 主流程不需要主体分割或抠图；抠图仅可作为未来独立、显式选择的专项能力。
10. 服务器不保存用户项目状态；浏览器清理数据或 origin 变化造成的迁移由项目包解决。
11. 默认密钥只在服务器；BYOK按SEL-015仅当前页内存/HTTPS请求级，不进持久化、Git、包、日志、错误或证据。当前已实现的图像头为 `X-AMZ-Listing-Key-Image`，其他用途不能据此宣称已接通；默认档缺省closed，当前启用与权限以实际配置及计划为准。
12. 远程正式入口必须来自可信 HTTPS secure context；本机 localhost 是唯一明文开发例外。
13. 默认界面投影业务任务而非工程结构；Prompt/hash/task id 可查但必须渐进披露。

## 7. 质量门槛

| 层 | 必须证明什么 | 主要证据 |
|---|---|---|
| 控制面 | 唯一目标、唯一状态、唯一下一动作、文档全部登记 | `tools/check_docs.py`、`tools/check_project_state.py` |
| 领域与存储 | 当前 schema、事务、依赖失效、Blob 生命周期与同版本往返正确；旧版本兼容按 SEL-018 不要求 | 单元测试、反向探针、导入/导出哈希比对 |
| 服务合同 | 无服务器业务持久化；错误、Unknown 与 Provider 身份可恢复 | API 契约测试、服务器重启轨迹、磁盘差异审计 |
| 浏览器产品 | 正式入口从空白用户动作走通人工和辅助路径、比较/恢复/实际导出；真实视口/缩放/键盘及人因后置 | 支持契约/自动化权限以计划§3/§7.2为准；§14.9任务、浏览器请求/IDB/ZIP及真实读图，UI草图不算运行证据 |
| 生成系统 | 真实参考图、实际Prompt及原action/request/task（若协议存在）与候选可追溯；图文理解真的发送原图 | 出站捕获、Provider记录、候选hash及独立质量观察；HTTP/schema成功不能代替忠实度或文字质量 |
| 工程与真人验收 | 工程主链按计划§14.8–14.9/§10证明；目标用户可用性和独立首次使用是另一层证据 | UI§8区分设计确认、工程浏览器验证、C17/C15；真人门本轮之外，不能冒充通过，也不能用其未发生否定工程范围定义 |
| 格式检查 | 暂无 ruff/eslint：本仓库没有格式化工具链，格式由 `.gitattributes` 与评审保证 | 引入格式化工具需先过选型门（SEL 记录） |
| 静态检查 | 采用SEL-021已批准的渐进TypeScript checkJs/noEmit与锁定工具；实际覆盖由配置/CI决定 | 不将node语法检查、选型批准或历史绿灯写成当前全仓类型通过 |
| 行为验证 | 原生node领域行为与Python合同/宿主验证分层，按计划§7.3及实际已接线入口 | 行为/边界/转换与IDB/网络/浏览器后置分工；规则见AGENTS，不因规约修订新增验证框架 |
| 覆盖率 | 暂不设阈值：本项目的判据是“证据能判红”，不是行覆盖率 | 若引入覆盖率门槛，先立 SEL 决策并说明理由 |
| 应用构建 | 前端无需编译；Python 可直接运行；正式交付物是 CI 构建的 Docker 镜像 | `python app/server.py --check`、`docker build` |
| 容器交付 | 当前启动/健康回退与目标完整发布回退分别说明，不把容器healthy当线上页面通过 | 计划§7.7/R7.4；既有Docker/Actions/部署日志及实际HTTPS/资源/主链/回退证据，准备不运行发布 |

## 8. 上下文读取与写入路由

读取顺序与写入路由的**唯一权威**在 [`docs/INDEX.md`](INDEX.md)（§1 的恢复读取顺序、§5 的
「写入路由：改哪里，不改哪里」）。本节不再复制这两张表：两处都写、内容一致时它们仍会
各自漂移，读者也不知道该信哪一份。本文件回到自己的问题——项目是什么、怎样运行、
数据归谁、目录与质量门槛是什么。
