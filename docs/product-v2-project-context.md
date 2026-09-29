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
| 参考模板 | `docs/standards-template/` 提供项目身份、活需求、进度和规范分工方法 | 只采纳“一类事实一个权威、活记忆精简、证据驱动”的思想；不采纳课堂式确认门、GitHub/CD 默认值或模板占位符 |

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

## 4. 技术栈与可替换边界

| 层 | 当前选择 | 边界 |
|---|---|---|
| 前端 | 原生 HTML、CSS、JavaScript | 延续现有低依赖路线；业务状态通过 repository/service 接口访问，不让 DOM 成为状态源 |
| 浏览器持久化 | IndexedDB + Blob；localStorage 只放轻量指针 | 需要 schema migration、事务、容量提示、项目导入/导出；不把图片 Base64 塞进 localStorage |
| 服务端 | Python，正式入口仍从 `app/server.py` 路由 | 服务方法无用户工作空间参数；请求进、模型响应出 |
| 语义模型 | `deepseek-v4.1-flash`，经 SemanticProvider 适配 | 输出必须通过结构契约；模型可替换，领域对象不绑定模型文本 |
| 图片模型 | 阿里云百炼 `qwen-image-3.0`，经 ImageProvider 适配 | 直接使用参考图；主流程不抠图、不部署本地分割模型 |
| 视觉校验 | 可替换 VLM Provider | 只提出分级问题与证据；具体模型 ID 在 V2.5.2 实现时按可用配置确定 |
| 确定性规则 | 版本化平台、文件、槽位依赖与状态规则 | 不把审美或模型自评伪装成硬规则 |
| 服务端数据库 | 无 | Product V2 不引入数据库、账户、租户或服务器项目索引 |

首版语义与图片模型均通过阿里云百炼调用，统一从环境变量读取 `DASHSCOPE_API_KEY`；不要求额外的 `DEEPSEEK_API_KEY`。模型名称分别由 `SEMANTIC_MODEL`、`IMAGE_MODEL` 配置，VLM 名称留到 V2.5.2 选择后再写入 `VLM_MODEL`。密钥不得进入浏览器状态、项目包、日志、证据或 Git。

## 5. 目标目录地图

```text
amz-listing-kit/
├─ app/
│  ├─ server.py                         # 正式服务入口
│  ├─ product_v1_server.py              # Product V1 历史实现，迁移期保留
│  ├─ product_v2_server.py              # V2 无状态 HTTP 适配器（目标）
│  └─ product_v2/                       # V2 前端静态资源；storage/ 与项目首页已落地，正式服务适配待建
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

## 8. 上下文读取与写入路由

读取顺序：

```text
docs/INDEX.md
→ 本文件
→ _working/amz-listing-kit-product-v2/state.md
→ 当前计划中 next_action 对应任务
→ 该任务证据与相关代码
```

写入规则：

- 项目身份、技术栈、运行边界、目录所有权变化：只改本文件。
- 目标、需求、状态机、任务、Gate、完成判据变化：只改 Product V2 计划。
- 当前进度、证据、阻塞、未知、下一动作变化：只改 Product V2 state。
- 当前已经实现的行为变化：改代码、测试，并更新 README 的实现说明。
- 一次验证发生了什么：写入 `evals/product-v2/`，由 state 只引用。
- 文档身份变化：改 `docs/INDEX.md`，并同步文档顶部 CONTROL-STATUS。
