<!-- 拆分件：技术栈与选型 SEL-000–009 -->
> [product-v2-project-context.md](product-v2-project-context.md) · CONTROL-STATUS: current · AUTHORITY: project-context
> 原文第 78–110 行 · [前片](product-v2-project-context.runtime.md) · [后片](product-v2-project-context.selection-010-018.md)

## 4. 技术栈与可替换边界

| 层 | 当前选择 | 边界 |
|---|---|---|
| 前端 | HTML/CSS、混合JS/TS源码，lit-html视图、Vite构建 | 业务状态通过既有Module/repository访问，唯一生产静态目录`dist/product-v2`；DOM不是业务状态源 |
| 浏览器持久化 | IndexedDB + Blob；localStorage 只放轻量指针 | 当前格式事务、容量提示、项目导入/导出；开发态旧版本兼容不要求（SEL-018）；不把图片 Base64 塞进 localStorage |
| 服务端 | Python FastAPI + Uvicorn；正式入口`app/server.py`，HTTP宿主`product_v2_http.py` | 无旧HTTP fallback；请求级无状态路由不读写用户项目、工作空间或最近项目索引 |
| 商品理解 | `deepseek-v4.1-flash`文字／`qwen-vl-max`商品图文提议，各自SemanticProvider | 文字不发原图；看图Adapter发送实际字节并保留source，输出仍待人工确认。现有真图文子步不等于当前辅助完整任务已验收 |
| 图片模型 | `qwen-image-3.0` 与大陆火山 `doubao-seedream-5-0-flash-260915` | 两个有限协议Adapter消费参考图；同步/异步归一业务结果，主流程不抠图、不部署本地分割模型 |
| 视觉复核 | `qwen-vl-max`，候选及整套各自业务合同 | 当前多模态传输可复用，复核schema不能冒充商品理解；可选辅助/交付政策以计划§14.8为准 |
| 确定性规则 | 版本化平台、文件、槽位依赖与状态规则 | 不把审美或模型自评伪装成硬规则 |
| 服务端数据库 | 无 | Product V2 不引入数据库、账户、租户或服务器项目索引 |
| 交付运行时 | Docker + GitHub Actions | CI 先验证同一 Dockerfile；远程服务器 Docker 从该提交的最小上下文构建 SHA 镜像并运行 |

当前provider配置权威为 `config/product-v2/providers.json`，registry解析后注入消费者；百炼采用 `DASHSCOPE_API_KEY`、火山采用 `ARK_API_KEY`，无需额外DeepSeek key。三用途客户端有限设置及请求级BYOK已实现接线，正式头分别为 `X-AMZ-Listing-Key-Semantic`／`-Image`／`-Review`；商品看图理解有独立Adapter/提议schema，不能用候选复核合同代替。当前全用途/秘密/辅助任务证明差距取state，不把API头存在或过时设置绿灯当完成。秘密不进持久化/包/日志/证据/Git，默认档受SEL-015 fail-closed约束。

### 4.1 选型记录

选型门禁的规则正文在仓库根 `AGENTS.md`；本节是**结论的唯一落点**：每条选型决策留一行，
写清约束、被拒方案与复访条件，避免下一个 Agent 重新讨论、重新实现已经决定过的问题。

| ID | 范围 | 决策 | 被拒方案 | 复访条件 |
|---|---|---|---|---|
| SEL-000 | 依赖政策 | Python pinned依赖由pyproject.toml + uv.lock管理；前端根package.json/package-lock.json为唯一工具/浏览器依赖权威。SEL-021/023已切到标准tsc检查、Vite构建及lit-html视图；生产仅Python与构建后静态ESM。新框架/依赖仍须选型；领域规则自研、通用原语复用 | 未经选型放开npm/全仓TS/框架；全零工具；多份manifest/lock权威 | 实际维护痛点、离线安装或工具约束变化时 |
| SEL-001 | 编排层 | 不引入 LangGraph 与 Agent/Memory 编排，服务端保持无状态（业务状态权威是浏览器 IndexedDB）；引入 `langchain-core` / `langchain-openai` 仅作提示词、模型调用与结构化解析原语（见 SEL-003），不承担状态与编排 | LangGraph checkpointer + 服务端状态；Agent/Memory 编排 | 出现服务端自主多步编排，或需要跨进程恢复的长任务 |
| SEL-002 | 服务端 HTTP | SEL-022已在本次候选落实FastAPI/Uvicorn，旧stdlib HTTP实现退出；产品保留正文限额、错误/凭据/出站/Unknown政策 | 无实际收益引框架；新旧HTTP双运行链 | HTTP政策或宿主约束变化时，运行真实TCP与页面验证 |
| SEL-003 | 语义/视觉调用传输层 | 用户已确认（2026-09-30）：`langchain-core` + `langchain-openai` 的 `ChatOpenAI` 指向百炼 OpenAI 兼容端点（`deepseek-v4.1-flash`）；显式 timeout、`max_retries=0`（禁止隐藏重试）；失败映射进 `v2_semantic` 四类归口。版本：langchain-core 1.6.6、langchain-openai 1.6.6（均 MIT）；依赖实测与 PoC 报告见 `evals/product-v2/sel003-transport-selection-20260929.txt` | LiteLLM（59 包，为单一兼容协议付 4 倍依赖）；`requests` 手写适配器（重复造 HTTP/重试轮子）；OpenAI SDK 直连（已含于 langchain-openai，不建双轨） | 接入第二个供应商或需要路由/降级/成本统计时评估 LiteLLM；需要 OpenAI 专有能力时评估直连。PoC 已发现：`deepseek-v4.1-flash` 为推理型输出，需给 reasoning 留预算 |
| SEL-004 | 项目管理规范 | 采纳`docs/standards-template/`的要求而不复制目录；产品终点/正式依赖、项目工作规则、具体Issue/PR、产品权限/恢复分工按INDEX，映射见AGENTS。具体问题使用Issue不构成第二份完整产品Goal或本地进度表 | 复制模板另建standards/，或以防双权威为由禁用产品Issue；在state/报告重抄工单明细 | 需要对外交付独立规范包或协作分工改变时重开 |
| SEL-005 | 持续交付 | 沿用GitHub Actions + Docker：PR-to-main/main push/manual触发既有CI，只有main push才触发既有受保护发布，固定origin/端口。release事务保留previous至acceptance/指纹/finalize后，离线stage证据不等于真实Docker/HTTPS；R7.4按当前候选证明实际容器页面、可信发布及同origin恢复，不重建CD | 新镜像仓库/编排平台、healthy冒充用户主链、容器回退冒充浏览器数据恢复、源码token自匹配冒充条件真值 | 发布验收范围或数据格式改变时；合并/发布权限取AGENTS、计划§17最新修订与state，不绕保护或最新停工 |
| SEL-006 | 语义契约表示 | Python 侧契约表示权威 = Pydantic（langchain-core 自带，锁定 2.13.5）：请求 / 原始提案 / 提案槽位三类模型 + 跨字段校验；校验作用在模型原始输出；错误四类归口、归一化映射、浏览器侧 `checkFactSlot` 与 `CORE_SLOT_REGISTRY` 保留 | Python 侧继续手写形状/不变量校验（重复造轮子，违反复用门）；浏览器改吃 schema（受 SEL-000 无构建约束，且与 SEL-001 状态权威错位） | V2.6.3 项目包跨版本迁移需要 schema 版本与迁移器时，以“契约权威”为题重开（评估 JSON Schema 作中立权威 + 双语言消费者） |
| SEL-007 | LangChain 使用边界 | v1 直调形态：`ChatOpenAI.with_structured_output(原始提案模型, method="json_mode", include_raw=True)`；系统/用户消息直接构造，JSON 格式说明由 Pydantic schema 生成并注入系统提示；LCEL 管道、ChatPromptTemplate、Agent/Memory 均不使用（保留为库内可用能力，不是本项目范式）；装配与错误分类的操作细节见计划 §9.1 | LCEL 管道（0.x 主推范式）；默认 `method="json_schema"`（百炼对自定义模型名的支持未证实；不支持时 400 且会被误分类）；`method="function_calling"`（依赖该模型在百炼的函数调用支持）；ChatPromptTemplate | 百炼确认支持 `response_format: json_schema` 时把 method 切换回默认（改一个装配参数 + 重跑契约测试）；需要多步编排时按 SEL-001 的复访条件另立决策 |
| SEL-008 | 浏览器 ZIP 能力 | 用户已定（2026-09-30）：vendor fflate 0.8.3（MIT）替换自研 ZIP 容器；vendored 单文件 = `esm/browser.js`（90,922B，自包含 ESM，上游 sha256 前 16 位 `B7CA4450B19559A1`），随附许可证文件并登记 vendor 表；`storage/zip.js` 退化为薄适配器：保持 buildZip/readZip 接口与我方错误码及上限检查，格式校验委托 fflate | 继续自研 ZIP 容器（8.7KB：CRC32 + 本地头/中央目录/EOCD）；minified UMD 33KB（全局脚本、非 ESM）；jszip（体积更大） | 上游发布修复版需升级时（重跑包合同与 V2.1.3 往返验证）；fflate 停更或许可变化时重选 |
| SEL-009 | V1工程清理 | 2026-10-07用户明确纳入本轮R7.3：先证明V2覆盖当前用途、明确V1独有用途、切换正式消费者并取得精确代码/同版本数据恢复基线，再删V1活入口/实现/失效配置/依赖；保留共享依赖与历史/用户原件。最终两轮和指纹在删除后，C17/C15独立真人仍外部，不作为工程清理前置 | 盲删共享依赖/用户数据、保留两套活实现当“回退”、删后沿用旧指纹、模拟E2E冒充真人签署 | 逐项实际消费者闭包与用途覆盖成立再执行，删后正式V2主链/恢复及最终R7.1/R7.4验收 |

<!-- 续接：原选型表在 product-v2-project-context.selection-010-018.md 从 SEL-010 接续；此标记在重组时移除。 -->
