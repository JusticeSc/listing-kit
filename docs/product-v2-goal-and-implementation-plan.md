# amz-listing-kit Product V2 Goal 与详细实施计划

> CONTROL-STATUS: current · AUTHORITY: product-goal-plan
> **版本：v3.1 · 2026-09-30**
> 本文件是 Product V2 的目标、需求、行为、状态、任务、依赖、Gate 和完成证据的唯一权威。
> 项目运行边界见 [`product-v2-project-context.md`](product-v2-project-context.md)；当前进度只见
> [`../_working/amz-listing-kit-product-v2/state.md`](../_working/amz-listing-kit-product-v2/state.md)。

## 0. 一页结论

Product V2 不是服务器文件夹工作台，也不是“输入一句话后神秘出图”的 Prompt 增强器。它是一个由浏览器持有项目状态、由无状态服务器提供 AI 能力的商品套图生产工具：

```text
商品资料与参考图
→ DeepSeek 提议结构化商品理解
→ 人工只确认异常、未知和关键事实
→ 系统推荐可编辑套图计划
→ 用户可增删排序图片任务并修改单图规格
→ 编译实际发送给 qwen-image-3.0 的 Prompt
→ 逐图生成、保存候选、自动校验
→ 问题驱动的单图返工和新旧比较
→ 人工逐图采纳
→ 整套一致性与确定性平台检查
→ 浏览器导出交付包或完整项目包
```

本轮最重要的架构裁定：

- IndexedDB 是用户项目权威；localStorage 只保存轻量指针。
- 服务器不保存用户项目、最近项目、图片、候选、选择和导出包。
- `deepseek-v4.1-flash` 负责语义提议；`qwen-image-3.0` 负责参考图生成；可替换 VLM 负责发现图像问题。
- 主流程不运行抠图或主体分割模型。
- 固定机制是槽位协议、模板条件、版本依赖、Prompt 编译、状态与验证器；商品事实、品类槽位、套图数量、单图内容和返工方向动态产生并由人确认。
- 现有 Product V1 冻结为历史基线；D4.13/D4.14 不再是当前路线。

## 1. 事实基线与变更理由

### 1.1 可以复用的 Product V1 能力

- 正式入口、Provider 适配、真实参考图调用和候选下载已经跑通过。
- GenerationAttempt、部分失败、Unknown、按原 task ID 核对的语义已经形成。
- Prompt 版本、旧候选保留、单图返工隔离、人工选择、导出 manifest 已有代码与回归证据。
- 最终前端已经覆盖空白输入、套图、生成、审核、返工和交付的主要页面形态。
- D4.12 双次回归可以作为迁移反向保护，但只证明旧 Product V1。

### 1.2 必须替换的假设

| Product V1 假设 | Product V2 裁定 | 原因 |
|---|---|---|
| 服务器文件夹是工作空间权威 | 浏览器 IndexedDB 是项目权威 | 访问服务的每个浏览器应管理自己的状态；服务器不应向所有访问者暴露同一 recent index |
| Windows 文件夹选择器是入口 | 浏览器项目列表、新建、导入和导出 | 文件夹选择器操作的是服务器电脑，不是访问者电脑 |
| 商品事实结构基本固定 | 固定槽位 + 品类动态槽位 + 用户自定义槽位 | 不同商品需要不同事实结构，但核心依赖不能任意删除 |
| 套图主要由生成结果倒推 | 套图计划和 ShotSpec 是生成前可编辑合同 | 用户需要知道为什么生成、可改什么、验什么 |
| 自动检查以文件规则为主 | 生成前规则 + 单图 VLM + 整套一致性 + 导出硬检查 | 只靠人工无法有效降低审核负担 |
| 服务器保存任务与候选 | 浏览器保存 action/task/candidate；Provider 保存外部任务 | 服务器应可重启、可替换、不拥有用户项目 |
| 主流程可能依赖抠图 | 主流程直接使用参考图 | 分割不是商品理解的必要前提，并会增加资源、品类偏差和错误传播 |

### 1.3 完成声明的边界

以下声明在对应完成证据出现前始终禁止，不随局部任务完成而自动成立：

- Product V2 已完成端到端商品套图生产，或已达到陌生人可独立使用。
- VLM 能可靠识别所有商品失真或审美问题。
- Amazon US 全品类规则已经齐全。
- 浏览器持久化可以替代用户备份；清除站点数据不会丢项目。
- 无状态服务器能在“提交响应丢失且无 provider task ID”时自动证明外部任务结果。

具体哪些切片已经实现只看 `README.md` 与当前 state；本计划不保存会随施工变化的进度副本。

## 2. 系统 Goal 绑定

> 将 `amz-listing-kit` 建成一个陌生试用者可以在现代桌面浏览器中独立完成商品套图生产的可用产品：使用者从空白创建浏览器本地项目，上传并管理同一商品的参考图，填写商品名称及可选介绍、真实卖点与本次重点；项目、图片、候选、任务身份、审核和历史版本由浏览器 IndexedDB 持久化，localStorage 只保存当前项目指针，完整项目可导出和重新导入，Python 服务不保存用户工作空间或最近项目。系统通过可替换的 `deepseek-v4.1-flash` 语义适配器提出带来源、置信与确认状态的商品品类和动态事实槽位，使用者能够确认异常、修改推断并增删允许扩展的槽位；在已确认事实上，系统推荐 `1..N` 张可编辑套图计划，支持新增、复制、删除、排序图片任务和检查对比图、尺寸图等条件依赖。每张图片由共享 StyleSpec、单图 ShotSpec、平台规则和 Provider 适配规则编译成可查看、可编辑、与实际请求一致的完整 Prompt，并由无状态服务调用阿里云百炼 `qwen-image-3.0` 使用真实参考图生成候选。浏览器保存 action ID、provider task ID、Attempt、候选 Blob 与版本关系；局部失败不丢失成功结果，Unknown 不自动重提，已知 task ID 先向 Provider 核对。每个候选经过确定性规则和可替换视觉语言模型的分级校验，使用者在参考图、历史候选和返工候选的直接比较中处理问题，可按常见问题或自定义方向只返工目标图片，旧候选和无关图片保持不变。只有人工为全部必需图片选定候选并通过整套一致性及确定性导出检查后，浏览器才生成包含选定图片、manifest 和人读摘要的交付 ZIP；另可导出包含完整历史的项目 ZIP。主流程不要求用户编写 Prompt，不部署本地抠图模型，不建设服务器数据库、账户、多租户或服务器项目存储。
> 完成必须由新鲜证据证明：正式入口从空白浏览器状态启动且不读取服务器 recent-workspaces 或绝对路径；刷新、关闭浏览器和重启服务器后项目仍能从 IndexedDB 恢复；两个独立浏览器配置文件拥有不同项目列表；项目 ZIP 导出、清空浏览器状态、重新导入后业务记录和图片哈希一致；至少四类结构明显不同的商品能够形成不同、可解释、可人工修订的动态槽位和套图方案；套图支持人工新增、删除和排序 Shot，条件依赖能阻止无依据的对比、尺寸或成分表达；UI 展示的 Prompt 与真实请求一致且没有无规则的中英文拼接；至少一个完整任务使用真实参考图调用 `qwen-image-3.0`，保存可追溯候选并对每个候选产生绑定当前规格的自动校验报告；局部失败、刷新、服务重启和 Unknown 不导致静默丢失或重复提交；一次单图返工保留旧候选，且无关 Shot 的 Attempt、候选 Blob 和哈希不变；人工逐图采纳后能在浏览器生成可复检交付 ZIP；一名首次接触最终版本的人不使用命令行、JSON 或开发者口授，独立完成新建、资料确认、套图调整、整套生成、问题处理、一次局部返工、选择和导出。所有要求均有范围匹配的自动或人工证据才能完成 Goal，文档、Mock、自评或单张真实出图不能单独替代产品完成。

系统 Goal `01a0ca17-2179-7eb0-969a-af9c79c4d8ca` 已绑定上述文本；Goal 的运行、暂停、完成状态仍只由系统 Goal 管理，最近读数只记录在执行 state。

### 2.1 正式恢复 Goal 时的验收增补

现有 Goal 主体不推翻；下面两句是本轮暴露问题后必须追加的**拟绑定增补文本**：

> 正式远程入口必须在受支持的当前稳定版桌面 Chrome 或 Edge 的可信 HTTPS origin 中，从空白配置文件完成新建项目、刷新恢复、关闭浏览器后恢复和继续工作；远程明文 HTTP、缺少 IndexedDB 或缺少 WebCrypto 时不得误报成同一种“不支持”，必须指出真实能力缺口与可执行恢复方式。嵌入式浏览器不是首版保证环境，不为它另造服务器项目存储或自研密码学降级路径。
>
> 首页与工作台必须作为成品界面通过产品发起人走查：项目入口紧凑、主次操作明确；同页工作台按“资料—理解—方案—生成—审核返工—交付”组织，一次突出当前任务；生成与审核以图片为视觉中心，Prompt、hash、task id 等工程信息默认渐进披露；1440px、390px 与 200% 缩放下均无关键操作遮挡。功能可点、Mock 通过或开发者能解释均不能替代这项产品验收。

系统 Goal 于 2026-09-30T21:35 观测为 `active`（此前一度为 `paused`）；系统工具不支持就地改写既有 objective。因此本计划把增补作为唯一产品目标的组成部分落盘：现有 Goal objective 与本增补共同构成完成判据；若后续创建新 Goal，则把本增补合并进完整 objective，不能遗漏或降级。

## 3. 产品合同

本计划是本项目**唯一的需求来源**：新需求、缺陷与技术债都追加到这里，以任务卡的「结果 /
验收条件 / 验证证据」呈现（等价于用户故事 + AC），不另起 PRD；进度与决策分别只写
`_working/amz-listing-kit-product-v2/state.md` 与 `docs/product-v2-project-context.md` §4.1。

### 3.1 使用者与完成定义

- **操作者和审核者**：同一个商品运营人员。
- **工作场景**：为一个商品准备可交付的 Amazon US 商品套图。
- **完成**：全部必需 Shot 都有人工选定候选，硬性导出检查通过，并生成交付 ZIP。
- **系统承诺**：提供有依据的默认值、异常提示、可编辑计划、自动校验和局部返工；不承诺模型每次生成都可直接交付。

### 3.2 使用者必须决定什么

1. 商品参考图和商品名称是否正确。
2. 模型推断的关键事实、品类、冲突和未知是否接受或修改。
3. 推荐套图是否满足本次任务，以及是否增删排序图片。
4. 单图的目标、必须保持、允许变化和可选 Prompt 是否调整。
5. 自动校验指出的问题是否需要返工。
6. 每个 Shot 最终采用哪一个候选。

系统不要求使用者选择内部品类编码、手写完整 Prompt、理解 action/task ID 或制定验证算法。

### 3.3 必须、可以、禁止

**必须：**

- 空白创建、浏览器本地项目列表、刷新恢复、项目导入导出。
- 商品名称和至少一张参考图必填；平台固定显示 Amazon US。
- 品类由模型提议但必须被确认；关键事实保留来源和确认状态。
- 固定槽位不可删除；动态和自定义槽位按规则允许增删。
- 套图支持新增、复制、删除、排序和模板条件依赖。
- Prompt 与实际 Provider 请求文本一致，Prompt 版本绑定事实、StyleSpec 和 ShotSpec。
- 候选生成后自动触发或可恢复触发校验；报告绑定候选和审核合同版本。
- 人工 Selection 是最终采用权威；返工后目标 Shot 必须重新选择。
- 所有用户项目状态保存于浏览器；服务器重启不破坏已保存项目。
- 完整项目包和最终交付包分开，均带 schema/version/hash。
- 远程正式入口使用可信 HTTPS；当前稳定版桌面 Chrome/Edge 能从空白创建并恢复项目。
- 首页与同页工作台具有明确层级、单一主操作和渐进披露，并通过产品发起人的视觉与交互走查。

**可以：**

- 使用系统默认理解、套图模板、视觉风格、问题分类和返工建议。
- 直接修改事实、ShotSpec、StyleSpec 和完整 Prompt。
- 为一个 Shot 生成多个候选并选择旧候选。
- 将未来模型选择隐藏在 Provider 适配器后；V2 首版不要求暴露模型选择器。

**禁止：**

- 把模型推断直接标成用户已确认事实。
- 把所有商品固定为七张图或某个示例商品模板。
- 缺竞品资料仍生成带事实断言的对比图；缺尺寸仍编造尺寸。
- 在 localStorage 保存大图、完整项目或 Base64 候选。
- 在服务器写入用户工作空间、最近项目、候选或导出包。
- 用 Mock、历史候选、本地贴图或占位图冒充当前真实生成结果。
- 自动覆盖原始参考图、旧 Prompt、旧候选、旧报告和旧导出记录。
- 把 VLM 分数或综合分数当作自动采纳。
- 在 UNKNOWN 后静默重提生成请求。
- 为主流程引入本地抠图、分割模型或 GPU 依赖。

## 4. 对象、身份与一致性

### 4.1 核心对象

| 对象 | 稳定身份 | 关键职责 |
|---|---|---|
| Project | `project_id` | 浏览器项目、当前版本指针、创建/更新时间、schema 版本 |
| ProductInput | `project_id + version` | 用户原始输入和参考图顺序 |
| Asset | 内容 SHA-256 | IndexedDB Blob、媒体类型、原名、尺寸、角色 |
| FactSlot | `slot_id + version` | 字段定义、值、来源、确认、置信、证据和依赖 |
| ProductBrief | `project_id + version` | 已确认事实投影、品类、用户、场景、卖点和风险 |
| SuitePlan | `project_id + version` | 有序 Shot 引用、推荐依据、模板与共享 StyleSpec |
| StyleSpec | `plan_id + version` | 整套视觉风格和商品保真公共约束 |
| ShotSpec | `shot_id + version` | 图片角色、目标、事实引用、保留项、允许变化、文案和禁止项 |
| PromptVersion | `shot_id + version` | 实际 Prompt、语言策略、来源版本、编译器版本、人工编辑原因 |
| GenerationAttempt | `action_id` | provider task ID、状态、Prompt/Asset 版本、观察历史和错误 |
| Candidate | 内容 SHA-256 | 图片 Blob、来源 Attempt、尺寸和创建时间 |
| ReviewReport | `candidate_id + review_contract_version` | 确定性检查、VLM 发现、严重度、证据和 Unknown |
| SelectionVersion | `project_id + version` | 每个必需 Shot 的人工选择 |
| ExportRecord | 内容 hash | 交付/项目包 manifest、文件清单、检查和生成时间 |

### 4.2 槽位分类

| 类型 | 谁定义 | 谁可改值 | 谁可增删 |
|---|---|---|---|
| 核心固定槽位 | 系统契约 | 用户；模型只能提议 | 不可删除；系统升级才可增减 |
| 品类动态槽位 | 语义模型按 schema 提议 | 用户确认或修改 | 用户可删除非依赖项，也可新增 |
| 用户自定义槽位 | 用户 | 用户 | 用户自由增删 |
| 派生槽位 | 确定性规则 | 不能直接改；改来源 | 由来源与规则决定 |

### 4.3 来源与确认状态

`source` 至少区分：`user_input`、`reference_observation`、`model_inference`、`system_default`、`derived_rule`。
`status` 至少区分：`confirmed`、`proposed`、`missing`、`conflict`、`unknown`、`superseded`。

模型置信只能帮助排序，不能把 proposed 自动改为 confirmed。

### 4.4 失效传播

| 变化 | 必须失效 | 不得失效 |
|---|---|---|
| 参考图集合或关键身份事实变化 | ProductBrief、引用该事实的计划、Prompt、相关 ReviewReport、Selection | 历史记录和 Blob |
| 普通事实值变化 | 引用该事实的 ShotSpec、Prompt、候选当前性、报告和选择 | 不引用该事实的 Shot |
| StyleSpec 变化 | 所有当前 Prompt、相关候选当前性和整套一致性报告 | 原始输入与历史候选 |
| 单个 ShotSpec 变化 | 目标 Shot 的 Prompt、候选当前性、报告和选择 | 其他 Shot 的 Attempt、Blob 和选择 |
| 只编辑目标 Prompt | 目标 Shot 下游 | ProductBrief、Plan、其他 Shot |
| 新增或删除可选 Shot | SuitePlan、Selection 完整性、整套报告 | 既有 Shot 历史 |

## 5. 用户可见工作流与渐进披露

| 步骤 | 默认展示 | 按需展开 | 用户动作 | 完成条件 |
|---|---|---|---|---|
| 项目首页 | 本浏览器项目、创建和导入 | 存储用量、schema 版本 | 新建、打开、导入、删除 | 进入一个 Project |
| 商品资料 | 参考图、名称、介绍、卖点、重点 | 原图信息和自定义槽位 | 上传、排序、填写、保存 | 名称和参考图齐全 |
| 商品理解 | 冲突、未知、低置信、必确认项 | 全部事实、来源和置信 | 确认、修改、增删槽位 | 所有关键依赖 confirmed |
| 套图计划 | 有序图片任务、角色、目标、条件问题 | 完整 StyleSpec 与 ShotSpec | 增删复制排序、套模板、修改 | 无未满足硬依赖 |
| 生成前确认 | 张数、任务摘要、待发送资料、未处理风险 | 完整 Prompt、Provider 参数 | 返回修改或开始生成 | 用户明确提交 |
| 生成 | 整体和逐图真实状态 | task ID、Attempt 历史 | 核对 Unknown、重试已确认失败 | 每个必需 Shot 有候选或明确失败 |
| 审核与返工 | 大图、审核清单、问题、采纳 | Prompt、报告详情、全部历史 | 比较、选问题、改方向、返工、采纳 | 所有必需 Shot 已选择 |
| 交付 | 已选图、硬检查、整套问题 | manifest 内容 | 返回审核、导出交付包、导出项目包 | ZIP 在浏览器生成并校验 |

内部对象名、action/task ID、Provider 参数和工程状态默认不常驻展示；只有排障、恢复或用户主动展开时出现。

## 6. 状态模型与合法动作

### 6.1 Project 状态

```text
EMPTY
→ INTAKE_READY
→ UNDERSTANDING_REVIEW
→ PLAN_REVIEW
→ READY_TO_GENERATE
→ GENERATING
→ REVIEWING
→ READY_TO_EXPORT
→ EXPORTED
```

任何上游改变都可以把后续投影变为 `STALE`，但不能删除历史。状态由当前对象关系派生，不由前端随意赋值。

### 6.2 GenerationAttempt 状态

```text
DRAFT
→ SUBMITTING
→ QUEUED
→ RUNNING
├─ SUCCEEDED
├─ FAILED_CONFIRMED
└─ UNKNOWN
     └─ reconcile(task_id)
         ├─ QUEUED / RUNNING
         ├─ SUCCEEDED
         └─ FAILED_CONFIRMED
```

- `action_id` 由浏览器在提交前生成并持久化。
- provider task ID 一经取得立即写入同一 Attempt。
- 已知 task ID 的 Unknown 只能先 reconcile。
- 未知 task ID 的提交超时不能由无状态服务器证明结果；保留 Unknown，用户显式决定是否发起一个新的 action。

### 6.3 Candidate 与 Selection

```text
Candidate: RECEIVING → STORED → REVIEW_PENDING → REVIEWED
Selection: UNSELECTED → SELECTED → STALE_AFTER_CHANGE → RESELECTED
```

Candidate 是否“可选”和是否“当前”是不同维度：历史候选可以保留并重新选择，但如果它与当前确认事实矛盾，必须展示过期原因并阻止静默采用。

## 7. 稳定机制与动态生成边界

### 7.1 系统提前设计

- 核心固定槽位及其类型、必填、来源和确认规则。
- 动态槽位的 JSON schema 和允许扩展边界。
- 通用图片角色、模板结构和条件依赖语言。
- StyleSpec、ShotSpec、PromptVersion、ReviewContract。
- Amazon US 通用确定性规则及规则版本。
- Prompt 编译语法、语言策略和 Provider 适配接口。
- GenerationAttempt、Unknown、候选、选择和失效传播。
- 常见审核问题分类及返工影响范围。
- 项目包、交付包、schema migration 和 manifest。

### 7.2 系统动态生成

- 品类建议、品类专属事实槽位和待确认异常。
- ProductBrief、套图数量、Shot 组合和推荐理由。
- StyleSpec/ShotSpec 的默认值、单图画面与 Prompt 语义内容。
- 候选图片、VLM 审核提议、返工改进方向。

### 7.3 人工可增删

- 非核心动态槽位和自定义槽位。
- 可选 Shot、图片顺序、模板实例。
- ShotSpec 的动态槽位、Prompt 和返工方向。

人工不能删除使系统无法解释状态的身份字段和版本关系，也不能把未确认模型推断改成“系统已验证”。

## 8. Prompt、风格与校验合同

### 8.1 Prompt 编译

```text
PromptContext
  confirmed_product_facts
  reference_asset_roles
  platform_profile
  suite_style_spec
  shot_spec
  negative_constraints
  provider_profile

→ ProductBlock
 + StyleBlock
 + ShotTaskBlock
 + CompositionBlock
 + CopyBlock
 + PlatformBlock
 + NegativeBlock
→ PromptVersion
```

- 用户界面以中文解释目标和结构。
- Provider 适配器决定实际 Prompt 的主语言和格式。
- 品牌名、专有名词和要求保留的准确文字不被机械翻译。
- 禁止按语言片段随意拼接造成重复、矛盾或中英文混杂。
- UI 展示文本、PromptVersion 保存文本与请求快照文本的 hash 必须一致。

### 8.2 校验层次

1. **输入预检**：必填、格式、事实冲突、参考图可读。
2. **计划预检**：模板依赖、事实依据、角色重复、覆盖缺口。
3. **生成预检**：Prompt 当前性、图片数量、外发资料、未处理风险。
4. **单图确定性检查**：文件格式、尺寸、透明、颜色空间等可复现规则。
5. **单图 VLM 检查**：商品失真、部件异常、明显畸形、穿模、乱码、目标完成度、禁止内容。
6. **整套检查**：商品与风格跨图一致性、卖点覆盖、角色重复或遗漏。
7. **导出检查**：人工选择完整、硬规则通过、manifest 与 Blob hash 一致。

严重度：`BLOCK`、`HIGH_RISK`、`WARNING`、`PASS`、`UNKNOWN`。VLM 不能单独产生 `PASS` 意义上的人工采纳，也不能把审美判断升级为平台硬阻断。

### 8.3 返工问题

固定常见问题：商品失真、部件错误、场景、构图、卖点表达、文字、风格、平台风险、其他。
问题是对现象的分类；改进方向是本次要改变什么。系统可根据报告提出方向，用户可自由改写。

## 9. 无状态 API 最小合同

| Method | Path | 输入 | 输出 | 服务器持久化 |
|---|---|---|---|---|
| GET | `/api/v2/capabilities` | 无 | schema、provider、规则和编译器版本 | 无 |
| POST | `/api/v2/semantic/analyze` | ProductInput 投影、参考图 | ProductBriefProposal、槽位、异常 | 无 |
| POST | `/api/v2/suites/plan` | 已确认 Brief、重点 | SuitePlanProposal | 无 |
| POST | `/api/v2/prompts/compile` | Brief、StyleSpec、ShotSpec、规则版本 | PromptProposal、来源映射 | 无 |
| POST | `/api/v2/images/submit` | action ID、Prompt、参考图、参数 | provider task ID 或明确错误/Unknown | 无 |
| POST | `/api/v2/images/status` | provider task ID | 权威状态、结果引用 | 无 |
| POST | `/api/v2/images/result` | provider task ID/结果引用 | 图片字节与元数据流 | 无 |
| POST | `/api/v2/reviews/image` | 参考图、候选图、ReviewContract | ReviewProposal | 无 |
| POST | `/api/v2/reviews/suite` | 候选缩略图、StyleSpec、Shot 摘要 | SuiteReviewProposal | 无 |

每个写外部系统的请求都带稳定 action ID。服务端错误响应必须区分输入拒绝、Provider 明确失败、超时/Unknown 和内部错误；不得返回“失败”掩盖未知结果。

### 9.1 V2.2.2 语义 Provider：契约、装配与错误分类

本节是 `deepseek-v4.1-flash` 适配器（`src/providers/v2_semantic.py`、
`src/providers/v2_dashscope_semantic.py`、`src/providers/v2_fake_semantic.py`）的操作级设计；
选型依据在项目上下文 §4.1 的 SEL-003/006/007，这里不重复论证，也不改变它们的结论。

**契约对象（SEL-006，权威表示 = Pydantic）**

- `SemanticRequest`：一次分析的全部输入（商品资料投影、参考图元数据、选项）。字段级约束（必填、长度、数量、词表）在模型上声明；越界即 `input_rejected` + `fatal`，绝不截断或补默认值后照常调用。
- `RawSlot`：模型原始槽位。跨字段校验：`value` 形状必须与 `value_type` 一致、`core_fixed` 必须命中核心注册表且 `value_type` 与注册表一致、`enum_values` 只允许 `enum` 使用、`depends_on` 合法且不含自依赖与重复。`critical` 不在模型契约里：归一化时由系统按 `CORE_SLOT_REGISTRY` 派生（V2.2.4 实测要求模型回显只会制造整包拒绝）。
- `RawProposal`：`summary` / `questions` / `slots`；`slots` 有常量上限（24），本次实际上限由请求的 `max_slots` 决定。

**装配（SEL-007）**

- `ChatOpenAI(model, base_url, api_key, timeout, max_retries=0)`，再 `with_structured_output(RawProposal, method="json_mode", include_raw=True, extra_body={"max_tokens": 预算})`；不注入 temperature 等本项目未验证的参数。
- 系统提示必须含 "JSON" 字样，并携带由 `RawProposal.model_json_schema()` 生成的格式说明（`json_mode` 不会自动注入格式，百炼同 OpenAI 要求提示中出现 json）。
- 令牌预算走 `extra_body.max_tokens`（默认 5000，`AMZ_V2_SEMANTIC_MAX_TOKENS`）：SEL-003 PoC 证明百炼兼容模式认 `max_tokens`，而 langchain-openai 1.6.6 会把 `max_tokens` 字段改写成 `max_completion_tokens`（本机实测），后者在百炼的支持未证实。默认值按 §9.3 实测校准：6 槽 ≈ 950 completion tokens（含 reasoning 324、prompt 1157），12 槽成功样本 1734（含 reasoning 547）；1400 与 3200 下都出现过截断（`evals/product-v2/v2.2.4-category-generality-20260930-021048.txt`、`-021404.txt`），因此取 5000，并用一次直连调用确认该参数被端点接受。
- 单次调用预算：`max_attempts=1`；库层重试被显式关闭，Unknown 之后不得自动重提（错误语义见下）。

**禁止的静默清洗（三条，全部改为分类失败）**

1. 不合成证据：模型没给 `evidence` 即 `INVALID_RESPONSE`；系统不代写、不补默认来源。
2. 不丢弃非法槽位：`slots` 出现非对象或违反跨字段约束的项，整包 `INVALID_RESPONSE`（带索引）。
3. 不截断：`len(slots) > max_slots` 即 `INVALID_RESPONSE`（带数量），不取前 N 个。

错误消息与证据不得回显输入正文或密钥（密钥片段按 `***` 遮蔽）。

**错误分类表（family / code / retry_policy）**

| 触发 | family | code | retry_policy |
|---|---|---|---|
| 输入字段越界、上下文超长 | input_rejected | INPUT_INVALID / INPUT_TOO_LONG | fatal |
| 401 / 403 | provider_failed | PROVIDER_AUTH_FAILED | fatal |
| 429 | provider_failed | PROVIDER_RATE_LIMITED | retryable |
| 其余 HTTP 失败（含 5xx） | provider_failed | PROVIDER_HTTP_ERROR | retryable |
| 连接失败（确定未送达） | provider_failed | PROVIDER_UNREACHABLE | retryable |
| 超时（无法区分是否送达） | provider_unknown | PROVIDER_TIMEOUT | requires_review |
| 内容策略拒绝 | provider_failed | PROVIDER_REFUSED | fatal |
| 输出被 `length` 截断 | provider_failed | PROVIDER_OUTPUT_TRUNCATED | requires_review |
| 可见文本为空 | provider_failed | INVALID_RESPONSE | retryable |
| JSON / 结构校验失败 | provider_failed | INVALID_RESPONSE | retryable |
| 未分类异常 | provider_unknown | PROVIDER_UNKNOWN | requires_review |

超时保守归 Unknown：宁可人工核对，也不自动重提。`retryable` 只表示“没有产生外部副作用、可以安全重试”，不代表系统会自动重试——真实调用仍受 §12.2 的预算纪律约束，重试必须是可见决定。

**验证入口**：`tools/verify_v2_2_2_semantic_provider.py`。离线部分（跨语言注册表、装配与真实请求体断言、错误映射矩阵、三条静默清洗负例、fake 全场景、无隐藏重试）默认执行；`--live` 增加 Q4 允许的最小真实调用（正例 1 次 + 无效密钥 401 负例 1 次）。

### 9.2 V2.2.3 商品资料与异常驱动理解界面

本节是「商品资料 → 商品理解」这一段的操作级设计：视图、动作、状态、规则与反馈。数据形状的权威仍是
§4 与浏览器侧 domain 契约（`app/product_v2/domain/`），本节不复制字段定义。

**服务端（第一组真实 API 路由，仍是纯无状态）**

| Method | Path | 输入 | 输出 | 失败语义 |
|---|---|---|---|---|
| GET | `/api/v2/capabilities` | 无 | 语义 provider 能力（id/模型/是否配置/契约版本）与 `analyze` 的请求字段 | 无 |
| POST | `/api/v2/semantic/analyze` | SemanticRequest 投影（名称/介绍/卖点/重点/参考图元数据/上限） | 语义提案（槽位 + 问题 + meta） | 分类错误 + `unknown` 标记 |

路由只做三件事：选 provider、调用、把分类错误映射成 HTTP 状态（`input_rejected`→400、
`provider_failed`→502、`provider_unknown`→504 且 `unknown=true`、`internal`→500）。请求体有字节上限，
非法 JSON 归 `input_rejected`。provider 由环境变量选择（默认取 `config/product-v2/providers.json`），
`fake-semantic` 用于无密钥环境与验证入口。服务端不落任何业务状态、不保存项目。

**重分析不排除已存在槽位**：请求里的 `existing_slot_ids` 一律传空。重复提案是「冲突检测」的输入——
已确认值与新提案不同时，`applySlotAction` 会把槽位变成 `conflict` 并保留双方证据，而不是静默覆盖。

**浏览器侧四个视图（同一个项目视图内，按顺序）**

| 视图 | 默认展示 | 按需展开 | 动作 | 规则 |
|---|---|---|---|---|
| 参考图 | 缩略图、角色、删除 | 原图信息（尺寸/字节/媒体类型/文件名） | 上传（可多选）、改角色、删除 | 至少一张 primary；同 sha256 不重复登记；≤20 张 |
| 商品资料 | 名称、介绍、卖点、重点 | — | 编辑（防抖草稿）、保存 | 字段上限取自 domain；未就绪时“分析”不可用并说明缺什么 |
| 分析 | 一个按钮与最近一次结果摘要 | 失败详情 | 分析 / 重新分析 | 前置条件=资料就绪；`unknown` 之后不自动重提，只能人工再点 |
| 商品理解 | 冲突、未知、缺失、未确认、必确认项 | 全部事实、来源、置信、依赖 | 确认、修改、标记未知、删除、新增 | 按钮集合由 `slotPermissions`/`canConfirmSlot`/`canDeleteSlot`/`canAddSlot` 派生；非法动作不出现 |

**草稿与确认事实**：表单内容在停止输入后防抖写入商品资料文档（同一 document_id，版本递增），刷新后
原样恢复；模型提案只经 `applySlotAction` 写入槽位文档，因此已确认值不会被覆盖。

**状态派生**：`EMPTY`（未就绪且无槽位）→ `INTAKE_READY`（资料就绪、无槽位）→ `UNDERSTANDING_REVIEW`
（有槽位但理解未就绪）→ `PLAN_REVIEW`（`briefReadiness` 通过）。状态由对象关系派生并写回项目记录，
不由界面任意赋值。`PLAN_REVIEW` 只表示“已具备进入套图规划的条件”；套图与生成尚未接入时，界面必须
显式说明可用范围，不能让状态标签暗示未实现的能力。

**验证入口**：`tools/verify_v2_2_3_intake_understanding.py`——用真实正式入口 + `fake-semantic`
provider 驱动真实浏览器：空白起点、上传参考图、草稿刷新保留、分析入库、异常优先列表、权限投影、
重分析冲突不覆盖、`unknown` 不自动重提（用浏览器网络事件计数）、状态推进、390px 与键盘路径。

契约套件的浏览器入口（`tools/v2_test_server.py`）复用正式入口的处理器与同一套路由，只额外挂 `/harness/`
并把 provider 固定为 `fake-semantic`：契约验证走的是产品代码路径，不是另一份静态服务器。

### 9.3 V2.2.4 四类商品通用性探针（Gate G2 证据）

本节定义「四类结构明显不同的商品得到不同、可解释、可追溯的动态槽位」怎样被机检。它不新增用户可见功能，
也不改变 §9.1 的契约与装配；它是 Gate G2 的完成证据入口，未通过时改槽位协议或 Prompt，不写商品名分支。

**固定输入（fixture 写在验证脚本里，不进用户项目）**

| 类别 | 输入要点 | 期望的结构差异 |
|---|---|---|
| 品牌刚性商品 | 品牌、型号、材质、性能数字 | 品牌/材质/性能参数类槽位 |
| 服装 | 面料、版型、适用场景 | 面料/版型/尺码类槽位 |
| 包装食品 | 配料、净含量、包装形态 | 配料/净含量/保质期类槽位 |
| 家具 | 尺寸、材质、承重、组装 | 尺寸/承重/安装类槽位 |

fixture 只提供 `SemanticRequest` 的字段（名称、介绍、卖点、本次重点、参考图元数据、locale、platform、
上限），不提供品类标签；探针不写 IndexedDB、不复用浏览器项目、不改任何产品状态。

**判据（全部机检；任一条不成立则 Gate G2 不通过）**

1. 输入驱动：四个 fixture 都通过 `parse_request`，且 `build_messages` 生成的用户消息两两不同。
2. 合法性：真实 provider 返回的每个槽位都通过消费侧 `check_proposal_slot`（与适配器内的
   `assert_proposal_legal` 是同一套硬约束，不接受任何非法槽位）。
3. 结构差异：四类的 `category_dynamic` 槽位 id 集合两两不全等；至少两类存在「只属于该类」的动态槽位。
4. 可追溯：每个动态槽位满足 `source=model_inference`、`status=proposed`、`confidence∈[0,1]`、
   至少一条 evidence，且提案带非空 summary。
5. 无常量泄漏：fixture 的商品名、品牌与特征词不得出现在 `src/`、`config/` 与 `app/product_v2/**/*.js`；
   HTML 里的示例文案不算泄漏，但同一批词出现在 JS 里即失败。系统提示不得出现任何品类枚举。

**预算与停止条件（§12.2）**：`--live` 走 `dashscope-semantic`，每类最多 1 次、总计最多 4 次真实调用；
不重试、不“抽卡”。任何一类失败（分类失败或 Unknown）只按分类记录，该类判为未验证并使 G2 不通过；
不降低判据，也不因为结果不好看而重跑。离线模式只跑判据 1 与 5，0 次调用。

**证据**：`tools/verify_v2_2_4_category_generality.py` 输出
`evals/product-v2/v2.2.4-category-generality-<stamp>.txt/.json`：四个请求投影的指纹、每类的动态槽位
（slot_id/label/value_type/value/confidence/evidence）、核心槽位值、summary、questions、usage、
request_id 与逐条判据结论，供人工逐类审阅。

### 9.4 V2.3.1 图片角色、模板与条件依赖注册表

本节是 Gate G3 的第一块：把「一张图要什么依据」变成可机检、只有一个消费者的规则注册表。
它不新增用户可见功能，也不生成图片；界面消费与 Prompt 编译在 V2.3.2–V2.3.4。

**落点与唯一消费者**

- 唯一权威表示 = `app/product_v2/domain/suite-plan.js`：冻结数据 + 纯函数，与 `CORE_SLOT_REGISTRY`
  同法（无构建步骤、无新增依赖、不碰存储与网络）。
- 唯一规则消费者 = 同一模块导出的 `evaluateDependencies` / `evaluateShot` / `recommendPlan` /
  `checkShotDraft` / `validateSuiteRegistry`。服务器不复制这套规则；后续 `/api/v2/suites/plan`
  若需要，必须先按本节「新增消费者」条件重开，或在请求里携带浏览器解析好的 ShotSpec，
  不允许在 Python 里再写一份会悄悄分叉的依赖判断。
- 依赖只引用核心槽位 id 与「该图绑定的已确认事实」，不出现任何商品名、品牌或品类分支。
- 参考图角色词表必须与语义契约一致：浏览器 `REFERENCE_ROLES` 从 4 项扩到 6 项
  （`primary/detail/packaging/scene/competitor/other`）——否则「对比图」依赖在真实界面里永远无法
  满足。逐字比对仍由 `tools/verify_v2_2_2_semantic_provider.py` 的跨语言合同项负责（与核心槽位
  注册表同一项）；本节的验证器只断言「注册表依赖用到的 role 都在词表内」。

**数据形状（每个字段必须有消费者）**

- `IMAGE_ROLES`：`role_id` / `label` / `purpose` / `custom`；`custom` 角色是用户自定义图的落点。
- `SHOT_TEMPLATES`：`template_id` / `role_id` / `label` / `intent` / `required` / `order` /
  `dependencies`（按 `order` 升序构成推荐顺序）。
- 依赖谓词（故意很小，但足以表达对比/尺寸/成分三类硬依赖）：
  - `asset_role {role}`：必须有该角色的参考图（对比图要 `competitor`）；
  - `fact {slot_id}`：该核心槽位必须 `confirmed`；
  - `fact_any {slot_ids}`：给定核心槽位里至少一个 `confirmed`；
  - `bound_fact {}`：该图必须绑定至少一个已确认事实——品类专属的配料/成分事实没有固定
    slot_id，由人工在计划里绑定，注册表因此保持品类无关；
  - `any_of {of}`：任一子谓词成立（尺寸图 = 核心 `size_summary` 或人工绑定的动态尺寸事实）。
- 求值上下文：`facts`（`slot_id` / `status` / `value`）、`assets`（`role` / `sha256`）、
  `bound_fact_ids`。只有 `status=confirmed` 的事实算依据；其余状态一律阻断并给精确原因。

**行为**

- `recommendPlan(context, options)`：按 `order` 返回有序 Shot 实例与逐条依赖状态；必需模板即使被
  阻断也要返回（界面必须指出先补什么），可选模板保留「被阻断 + 原因」，不静默丢弃。
- `evaluateShot(shot, context)`：对已实例化的 Shot 用其绑定事实重新求值，供编辑器即时投影。
- `createCustomShot` / `checkShotDraft`：支持 custom；未知角色、空 label、非法绑定被拒。
- `validateSuiteRegistry`：重复 id、未知角色、未知依赖、空 `slot_ids`、`order` 非法或重复、
  注册表里的 custom 模板、未被任何模板引用的角色（custom 除外）、以及**没有消费者的字段**
  都报红；`any_of` 递归校验并限深。

**验证与证据**

- `tools/verify_v2_3_1_suite_registry.py`：`node --check` + 真实 Chromium 跑
  `evals/product-v2/harness/suite-plan-contract.js`（R01–R13）：正例、反向探针（每条守卫都要能
  变红），以及 R11 **改数据探针**——逐字段变异并断言 `FIELD_CONSUMERS` 指名的消费者输出必须变化。
- 证据：`evals/product-v2/v2.3.1-suite-registry-<stamp>.txt/.json`。

**边界与复访**：只证明角色/模板/依赖语言本身的机检行为与唯一消费者。不证明推荐组合的审美质量、
Prompt 编译、真实生成与审核（V2.3.4 起）。当 Python 侧确实需要独立判断依赖（例如服务端要在
不信任浏览器输入时自行阻断）时，按「新增一个消费者」重开本节，同时给出跨语言一致守卫。

### 9.5 V2.3.2 可增删复排的套图编辑器

本节把 §9.4 的注册表变成用户可编辑的套图计划：任意张数、复制、删除、排序，顺序与必需/可选
状态一致持久化；界面消费在 `app/product_v2/workspace.js` 的「套图规划」卡片。

**落点与唯一权威**

- 唯一权威表示与操作 = `app/product_v2/domain/suite.js`：`SuitePlan` 文档契约 + 纯函数操作，
  复用 §9.4 的注册表与 `checkShotDraft` / `evaluateShot`，不复制依赖规则、不新增依赖。
- 存储：`DOMAIN_DOCUMENT_KINDS.suite_plan`，`document_id = "suite"`，沿用既有版本化 documents
  仓库（append-only）；「没有方案」= 没有本文档，不用空数组冒充。
- 失效语义沿用 `invalidation.js`：增删走 `shot_added_or_removed`（scope=suite），本任务的
  验证不覆盖传播（V2.3.3 落版本与失效），只保证计划文档本身的事务性。

**数据形状与不变量**

- `shots` 数组的顺序就是持久化顺序（第 i 项 order = i+1），不额外存 order 字段以免两份真相。
- 每个 Shot：`shot_id` / `template_id` / `role_id` / `label` / `intent` / `required` / `custom` /
  `dependencies` / `fact_slot_ids`。
- 不变量：`1..20` 张；`shot_id` 合法且唯一；非自定义图必须来自已登记模板、角色一致、
  依赖与模板逐字一致；自定义图 `template_id=null`、依赖为空、`required=false`；
  整套至少 1 张必需图（Amazon 主图不允许删到 0）。

**操作（纯函数，失败原子）**

- `seedSuitePlan(context)`：必需模板 + 依赖已满足的可选模板，按 `order` 落成计划；被阻断的
  可选模板不静默塞入（在「添加」列表里带原因呈现）。
- `addShotFromTemplate` / `addCustomShotToPlan`：追加；id 由 `shot_<template_id>` 派生并自动
  去重（`_2`、`_3`…），同一模板允许出现多次（例如两个场景变体）。
- `copyShot`：新 id、`required=false`、名称加「（副本）」；原图不动，复制不是「改」。
- `removeShot`：会删掉最后一张、或删掉最后一张必需图时拒绝并给出精确原因。
- `moveShot(plan, shotId, ±1)`：数组内换位；边界处返回 unchanged（不报错）。
- 所有操作返回新计划对象，输入不被修改；失败抛 `CONTRACT_INVALID`，调用方因此不会写出
  半成品——这就是「操作事务失败不改变旧计划」的实现方式。

**界面契约（按钮 / 状态 / 反馈）**

- 按钮：`生成推荐方案`、`选择模板 + 添加模板图`、`添加自定义图（名称 + 用途）`；
  每行 `上移` / `下移` / `复制` / `删除`。
- 状态：`共 N 张，可生成 M 张`；每行显示 必需/自定义 徽标与依赖状态（满足或精确阻断原因）。
- 锁定：商品理解未就绪（非 `PLAN_REVIEW`）时套图卡片只读，并说明先完成哪一步。
- 反馈：操作失败显示精确原因，旧计划与存储版本都不变；刷新后顺序、复制与删除结果原样恢复。

**验证与证据**

- 契约 harness `evals/product-v2/harness/suite-editor-contract.js`（E01–E12）：操作语义、
  不变量、反向探针（每条守卫都能变红）、失败原子性与 id 去重。
- `tools/verify_v2_3_2_suite_editor.py`：域契约 + 真实正式入口 UI 流（生成推荐 → 复制 → 上移 →
  删除副本 → 删必需图被拒 → 加自定义图 → 刷新恢复）+ 存储版本对照 + 截图。
- 证据：`evals/product-v2/v2.3.2-suite-editor-<stamp>.txt/.json/.png`。

**边界与复访**：不证明 StyleSpec/ShotSpec 版本与失效传播（V2.3.3）、Prompt 编译与真实请求
（V2.3.4）、生成前确认与外发资料摘要（V2.3.5）。计划文档的跨机器迁移沿用项目包路径，不另开后门。

### 9.6 V2.3.3 StyleSpec 与 ShotSpec：编辑、版本与失效传播

本节把「公共风格」和「单图规格」变成可编辑、可回退、影响范围精确的规格层；Prompt 编译在 V2.3.4
消费这些字段，本任务只负责规格本身与它引起的失效投影。

**落点与唯一权威**

- 唯一权威表示与规则 = `app/product_v2/domain/specs.js`：两个文档契约、默认值派生、差异、失效投影
  与审核清单投影都在本文件；依赖规则复用 §9.4，失效语义复用 `invalidation.js`，不复制第二份。
- 存储：`DOMAIN_DOCUMENT_KINDS.style_spec`（`document_id = "style"`，项目级一份）与
  `DOMAIN_DOCUMENT_KINDS.shot_spec`（`document_id = shot_id`，每张图一份）；沿用 append-only
  documents 仓库与 `expectedVersion` 乐观并发，历史只增不改。

**数据形状**

- `StyleSpec`：`schema_version` + `background` / `lighting` / `color_tone` / `composition`（文本）
  + `avoid`（列表，一行一条）；空字段不进入投影（投影只列有值的字段）。
- `ShotSpec`：`schema_version` + `purpose`（必填，这张图要达成什么）+ `keep`（必须保持）+
  `change_allowed`（允许变化）+ `notes`（可选）；`keep` / `change_allowed` 各 1..8 项、单项 <= 60 字。
- 默认值由角色派生：`purpose` 取模板 intent，保留项/允许变化按角色给默认（主图必须保持商品外观、
  标识与颜色；场景图允许环境与道具变化），自定义图按通用默认；未保存的规格在界面上明确标注「默认」。

**操作与不变量**

- `checkStyleSpec` / `checkShotSpec`：未知字段、类型不符、超长、空 purpose、重复项、空列表都报红；
  失败抛 `CONTRACT_INVALID`，调用方不写半成品。
- `styleSpecDiff` / `shotSpecDiff`：只报告真正变化的字段，供界面显示「这次改了什么」。
- `specChangeProjection(changeKind, context)`：把 `invalidationsFor` 的结果投影成人读结论——
  影响哪些图、失效什么、保留什么；`style_changed` 影响全套，`shot_spec_changed` 只影响目标 Shot
  且必须带 shotId。
- `previousVersionOf(versions, currentVersion)`：回退只选「比当前小的最高版本」；回退 = 用旧 payload
  写一个新版本，历史不覆盖（由存储层保证）。
- `reviewChecklist(shot, {shotSpec, styleSpec})`：把规格投影成逐图审核清单（目的 / 必须保持 /
  允许变化 / 公共风格），确定性输出，供 V2.5 的自动与人工审核复用。
- `suiteSpecDigest(plan, {styleSpec, shotSpecsById})`：按计划顺序给出每张图的清单与「默认/已保存」
  状态，界面只消费这一份投影。

**界面契约**

- 「风格与单图规格」卡片：风格表单（五字段）+ `保存风格` + 版本号 + 失效投影提示（保存前就显示
  「会影响全部 N 张图：Prompt 版本与审核报告失效；套图计划与参考图保留」）。
- 每张图一份规格编辑器（目的 / 必须保持 / 允许变化）+ `保存` + 版本号 + `恢复上一版本`
  （无上一版本时禁用）+ 审核清单预览。
- 后置条件可见：保存成功后版本号 +1 且清单立刻反映新值；单图保存不得改变其他图的版本或清单。

**验证与证据**

- 契约 harness `evals/product-v2/harness/specs-contract.js`（F01–F12）：默认值、校验反向探针、
  差异、失效投影（整套 vs 单图）、回退选版、清单投影与 digest。
- `tools/verify_v2_3_3_spec_versions.py`：域契约 + 真实正式入口 UI 流（保存风格 → 清单全变 →
  只保存单图 → 其他图版本不变 → 回退成新版本且历史递增 → 刷新恢复）+ 截图与存储版本对照。
- 证据：`evals/product-v2/v2.3.3-spec-versions-<stamp>.txt/.json/.png`。

**边界与复访**：不证明 Prompt 编译与请求一致性（V2.3.4）、生成前确认（V2.3.5）、真实生成与审核
（Phase 4 起）。风格字段是结构化规格，不是 Prompt 片段；在 V2.3.4 里它们进入编译器输入，不得被
拼成无规则的中英文混合文本。

### 9.7 V2.3.4 Provider 感知 Prompt 编译器

本节把 §9.4 的依赖、§9.6 的规格、平台规则与 qwen-image-3.0 的 Provider 合同编译成
「可查看、可追溯、与实际请求逐字一致」的 Prompt 版本；编译器是纯函数，不调用模型、不生成图片。

**落点与唯一权威**

- 唯一权威表示与规则 = `app/product_v2/domain/prompt.js`：平台档（`PLATFORM_PROFILES`）、Provider 档
  （`PROVIDER_PROFILES`）、分段模板、语言策略、冲突判定、请求快照与来源引用都在本文件。
- 复用而不是重写：依赖是否满足复用 §9.4 `evaluateDependencies`；失效语义沿用 `invalidation.js` 的
  `prompt_edited`；hash 复用 `app/product_v2/storage/db.js` 的 WebCrypto `sha256Hex`（与 repository
  的 `digest` 注入同法由调用方注入，domain 不 import storage、不新增第二种散列）；Prompt 分段拼装是
  领域语义而非通用模板能力，不引入模板引擎或新依赖。
- 版本化记录：`DOMAIN_DOCUMENT_KINDS.prompt_version`（`document_id = shot_id`，每图一份，append-only）；
  输入变化只让版本过期，不覆盖历史。
- 顺带修复（同一节范围）：`suite.js` 在种子/手动添加模板图时，把模板依赖中由已确认核心事实满足的部分
  自动绑定为该图的文案来源（`impliedFactBindings`）。规则仍然只有 §9.4 依赖表一份，不新增界面、
  不写商品分支；否则卖点信息图等文字类图片会编译出没有文案来源的空壳 Prompt。

**输入、输出与原子性**

- 输入 = `brief`（已确认事实）+ 一个 `shot` + `styleSpec`/`shotSpec` + `context`（facts/assets，供依赖判定）
  + 平台档 + Provider 档。
- 输出 = `{ sections[], text, source_refs[], warnings[], language, platform, provider, basis }`：
  每个 section 有 `key/label/kind/text/source_refs`，`text` 是 sections 的确定性拼接（模型真正收到的字符串）。
- 失败 = `CONTRACT_INVALID` + 精确问题列表（缺依据、冲突、超长、非法引用），不返回半成品、不修改输入。
  调用方在失败时保留已保存的旧版本，并阻止生成（V2.3.5 在此之上做生成前确认）。

**语言策略（policy id = `zh-instruction-v1`）**

- 指令段（商品一致性/风格/任务/平台/避免）统一中文；段内任何非中文原文必须来自输入、去引号后以「」逐字引用；
  编译器对引用值做引号中和与空白归一，保证检查器不可能把用户值误当裸外语。
- 图中文字 = 平台语言：`amazon_us` 为英文；每条必须逐字等于某条已确认事实值，禁止翻译、改写或补全。
  事实值语言与平台语言不一致时给出 `ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE` 警告（交人工决定，不自动翻译）。
- Amazon 主图不得出现叠加文字/水印；主图编译时不产出文字段；若绑定了事实而未使用，必须给出显式警告，
  不静默丢弃。

**冲突、覆盖与泄漏守卫**

- `keep` 与 `avoid`、`keep` 与 `change_allowed` 去重归一后相交 → 阻断编译。
- 主图要求纯白背景而公共风格给出非白背景 → 平台覆盖风格 + `STYLE_OVERRIDDEN_BY_PLATFORM` 警告，
  两个来源都写进 `source_refs`，不静默改写。
- 未确认或未绑定的事实值出现在任何段落 → `UNAUTHORIZED_FACT_VALUE` 阻断（对齐 V1 的既有教训）。
- Provider 约束：参考图 1..3、尺寸在 384..2048 与面积/比例合同内、`prompt_extend=false`、`watermark=false`、
  负向约束写进正文尾部（该模型没有独立 negative 字段）。

**记录、hash 与过期**

- `request_snapshot` = `{model, size, n, prompt_extend, watermark, reference_roles, prompt}`，含真实参考图的
  hash/角色引用，不含图片字节；`hash = sha256(canonicalJson(request_snapshot))`。
- `basis` = 槽位 basis + `suite_version` + `style_version` + `shot_spec_version` + 平台/Provider 档版本；
  `promptStaleness(record, current)` 机检过期并给出原因，供界面显示「需重新编译」。
- 界面展示文本、记录文本与快照文本必须是同一个字符串；UI 的 hash 不得由展示层另算。

**界面契约**

- 「Prompt 预览与版本」卡片：每张图一行/一卡，显示 `role_label`、编译状态、`text`、来源引用、
  `hash` 前 12 位与完整值、请求摘要（模型/尺寸/参考图角色/负向约束在正文）；未编译显示「未编译」，
  过期显示「已过期：原因」，失败显示精确阻断原因且旧版本仍可见。
- 按钮集合固定为「编译并保存版本」（就绪时可用）；不做生成、不做确认（后续任务）。

**验证与证据**

- 契约 harness `evals/product-v2/harness/prompt-contract.js`（G01–G12）：golden 快照、来源可解析、
  hash 稳定性与输入不变性、语言策略、主图平台覆盖、keep/avoid 冲突、依赖阻断、未授权事实泄漏、
  请求快照一致性、逐条反向探针。
- `tools/verify_v2_3_4_prompt_compiler.py`：`node --check` + 真实 Chromium 契约套件 + 正式入口 UI 流
  （编译→保存→界面/存储/hash 三者一致→改风格→过期→重新编译→刷新恢复）+ 截图 + 零 console error。
- 证据：`evals/product-v2/v2.3.4-prompt-compiler-<stamp>.txt/.json/.png`。

**边界与复访**：不调用任何模型、不生成图片、不证明出图质量（Phase 4）；不做生成前确认与外发资料摘要
（V2.3.5）。新增第二个 Provider 时只允许新增档位数据与差异项；若出现跨 Provider 的模板分叉，先按
「新增消费者」重开本节，不允许把平台或供应商分支写进界面层。

### 9.8 V2.3.5 生成前确认与外发资料摘要

本节把「套图计划 + 每图 PromptVersion + 参考图 + 平台/Provider 档」归约成一张确定性的生成前确认单：
用户提交前必须看到张数、每图任务与状态、将要发给外部模型的资料、尚未消除的风险；任何一图缺 Prompt、
Prompt 过期或依赖不满足都必须阻断并给出精确修改位置。本任务不调用模型、不提交任何生成请求。

**落点与唯一权威**

- 唯一权威表示与规则 = `app/product_v2/domain/confirm.js`：确认单形状、阻断码、外发资料摘要、风险传播与
  指纹失效判定都在本文件。不复制 Prompt 规则（复用 `prompt.js`），不复制依赖规则（复用 `suite-plan.js`
  的 `evaluateShot`），不写第二种散列（指纹由调用方注入 `storage/db.js` 的 `sha256Hex`）。
- 版本化记录：`DOMAIN_DOCUMENT_KINDS.generation_confirm`（`document_id = "generation"`，append-only）。
  每次确认写一条新版本，不覆盖、不删除历史。
- 项目状态：存在「与当前确认单指纹一致」的确认记录时，派生状态从 `PLAN_REVIEW` 前进到 `READY_TO_GENERATE`；
  确认失效（上游或 Prompt 前进）自动回落到 `PLAN_REVIEW`。状态仍由对象关系派生，界面不自由赋值（§6.1）。
- 界面只做投影与触发：确认按钮只写本地记录，不发请求；文案必须明说本版尚未调用图片模型。

**输入、输出与原子性**

- 输入 = `suitePlan` + 每图 `{record, version}`（可缺）+ `context`（facts/assets）+ 每图当前 basis
  （`briefBasis / suite_version / style_version / shot_spec_version / platform / provider`）。
- 输出 = 确认单 `{schema_version, platform, provider, total, ready, blocked, can_submit, shots[], external_summary, blockers[], risks[]}`：
  - `shots[]`：`shot_id / order / label / role_label / intent / template_id / required / satisfied / prompt{version, hash, chars} / references[{role, sha256_prefix}] / risks[] / blockers[]`；
  - `external_summary`：`model / size / n / prompt_extend / watermark / reference_count / reference_roles / prompt_chars / on_image_text_language / statement`，
    只出现真实会外发的参数与资料身份：参考图只列角色 + sha256 前 12 位，不含图片字节；
  - 精确位置：每个阻断带 `fix = {region, shot_id, label, action}`，`region ∈ intake / understanding / suite / style / shot_spec / prompt`。
- 阻断码（全部阻止提交）：`PROMPT_MISSING`、`PROMPT_RECORD_INVALID`、`PROMPT_TEXT_MISMATCH`、`PROMPT_STALE`、
  `DEPENDENCY_UNSATISFIED`、`PLATFORM_MISMATCH`、`PROVIDER_MISMATCH`、`REFERENCE_COUNT_INVALID`。
  `PROMPT_STALE` 的 fix 位置按过期原因字段投影（`brief.*` → 商品理解，`style_version` → 风格，`shot_spec_version` → 单图规格，
  `suite_version` → 套图规划，其余 → Prompt）。
- 风险（可确认但不得静默丢弃）= 编译警告（语言不一致、平台覆盖风格、主图绑定事实未使用）逐条进入 `risks[]`，
  界面可见；确认记录里必须列出「确认时存在的风险码」。
- 失败 = 不产出可提交确认单（`can_submit = false`），但仍返回完整投影供界面定位；确认写入失败不产生记录。

**指纹与失效**

- `snapshot = {schema_version, platform{platform_id,version}, provider{model_id,version}, can_submit, shots[{shot_id, prompt_version, prompt_hash, prompt_chars, reference_roles, blocked[]}], external_summary}`；
  `fingerprint = sha256(canonicalJson(snapshot))`。它与单图「请求快照 hash」是两个东西：后者证明一次请求，
  前者证明「这一批将要提交的东西」。
- 过期/缺依赖不是风险而是阻断：不允许用「确认」跳过。
- 已存在的确认记录与当前 snapshot 不一致 → 界面显示「确认已失效」并给出原因（张数、某图 Prompt 版本/hash、
  阻断状态或外发摘要变化），必须重新确认；失效不改写旧记录。

**界面契约**

- 「生成前确认」卡片（在 Prompt 卡片之后）：状态行显示总张数 / 就绪张数 / 阻断张数；下面是外发资料摘要一句、
  阻断清单（逐条含图片、阻断码、原因与 fix 位置）、风险清单和每图行（序号、名称、角色与必需/可选、Prompt 版本与
  hash 前 12 位、参考图角色与 hash 前缀、提示词字符数、风险码）。完整 Prompt 文本只在上面 Prompt 卡片展示，不复制第二份。
- 按钮集合固定为一个「生成前确认」（`can_submit` 时可用）+ 一行确认状态文本；本任务不提供「开始生成」按钮，
  确认成功后显示「已确认 vN…本版尚未调用图片模型」。未就绪时按钮禁用，阻断清单给出第一条 fix 位置。

**验证与证据**

- 契约 harness `evals/product-v2/harness/confirm-contract.js`（H01–H12）：确定性指纹与键序、正常全绿确认单、
  缺 Prompt 阻断、过期阻断（风格前进）、依赖不满足阻断、Provider/平台不符阻断、参考图数量越界阻断、
  风险传播（语言/覆盖/忽略）、外发摘要与 request_snapshot 一致、确认记录合法性与失效判定、逐条反向探针。
- `tools/verify_v2_3_5_pre_generation_confirm.py`：`node --check` + 真实 Chromium 契约套件 + 正式入口 UI 流
  （编译全部图 → 确认区显示张数与外发摘要 → 缺一张 Prompt 与缺依赖分别阻断并定位 → 全部就绪后确认 → 改风格使
  确认失效并回落 `PLAN_REVIEW` → 重新编译再次确认 → 刷新后确认记录、指纹与状态一致）+ 截图 + 零 console error
  + 回归旧套件。
- 证据：`evals/product-v2/v2.3.5-pre-generation-confirm-<stamp>.txt/.json/.png`。

**边界与复访**：不调用模型、不提交生成、不产生候选（Phase 4）；不证明出图质量与审核（Phase 5）。
新增第二个 Provider/平台时必须扩展档位数据与差异项，不允许在确认单里写供应商分支。

### 9.9 V2.3.6 Prompt 人工编辑版本

本节把「人工改提示词」变成可追溯的版本操作：用户直接编辑全文并保存为新版本，旧版本保留；语言与平台规则
降级为可见提示，产品真相仍硬阻断；编辑不改编译依据，所以上游前进后它会像编译版本一样过期。

**落点与唯一权威**

- 唯一权威 = `app/product_v2/domain/prompt.js` 的「人工编辑」段落：编辑记录形状、硬阻断清单、降级提示码与
  提示构造都在本文件；不新建第二份 Prompt 规则文件，也不在界面层重写规则。
- 复用而不是重写：硬阻断复用 `checkPromptLeaks`（未确认事实）与 `sectionProblems`；语言检查复用
  `checkPromptLanguage`（结果降级为提示）；失效投影复用 `invalidation.js` 的 `prompt_edited`；hash 复用注入式
  `sha256Hex`。编辑器不调用模型（不做对话式改写）。
- 版本与身份：仍写 `DOMAIN_DOCUMENT_KINDS.prompt_version`（`document_id = shot_id`，append-only）。
  记录新增 `origin`（`compiled` / `manual_edit`）、`edited_from{version,hash}`（人工版本才有）、
  `edit_reason`、`edited_at`；`basis` 逐字继承被编辑版本，不重算。

**输入、输出与原子性**

- 输入 = 基础 PromptVersion 记录 + 新全文 + 编辑原因（必填）+ 上下文事实 + 时间戳。
- 输出 = 新版本记录：`compiled.sections = [{key:"manual_edit", label:"人工编辑全文", kind:"manual_edit", text, source_refs}]`，
  `compiled.text` 逐字等于用户输入，`source_refs` = 基础来源 + `prompt_edit:<base_hash>`，
  `request_snapshot.prompt` 逐字等于同一字符串，`hash = sha256(canonicalJson(request_snapshot))`。
- 硬阻断（不产记录、旧版本不变）：基础记录不合法；全文为空或只有空白；超过 Provider 上限；含控制字符；
  与基础版本逐字相同（没有变化的“新版本”没有意义）；未确认事实值出现在文本里（引用与非引用都算）；
  新出现的「」引用不是任何已确认事实值（`MANUAL_EDIT_UNKNOWN_QUOTE`）；非文字白名单角色新增已确认文案
  （`MANUAL_EDIT_PLATFORM_TEXT_RULE`，主图属于此类）。
- 授权引用集合 = 被编辑文本里已有的「」引用 ∪ 已确认事实值 ∪ 平台背景短语：既能保留编译器产物
  （风格/规格/意图/平台常量），又不允许编辑绕过商品真相与平台文字规则。
- 唯一降级：语言策略（指令段出现未引用的非中文）写进 `compiled.warnings`
  （`MANUAL_EDIT_LANGUAGE_RULE`），界面与生成前确认都必须可见；编译器输出仍按 §9.7 严格自检，不因本节放宽。
- `checkCompiledPrompt` 对 `origin === "manual_edit"` 跳过语言策略阻断（其余段落、拼接与来源一致性照旧检查），
  保证下游（生成前确认、请求快照）读到同一份形状。

**失效投影与过期**

- 保存人工版本时写入 `invalidation = invalidationsFor("prompt_edited", {shotId})`：影响范围只限目标 Shot 的
  Prompt/审核/选择，保留商品理解、套图、单图规格与其他 Shot（与 §4.4 一致）。
- 编辑不改变 basis：上游槽位/风格/单图规格前进后，人工版本与编译版本同样判过期并阻止生成；
  重新编译会得到新的编译版本，用户可再次编辑。

**界面契约**

- 「Prompt 预览与版本」每图卡片增加：当前文本、`人工编辑 vN`（含原因）标记、可编辑全文的文本区、必填编辑原因、
  「保存为新版本」按钮；保存成功后卡片显示新版本、新 hash 与提示列表，旧版本仍可在版本历史中看到。
- 保存失败显示精确原因并保留旧版本与用户输入，不清空文本区；未编译的图没有编辑区（先编译）。
- 按钮集合固定为「编译并保存版本」与「保存为新版本」，不提供「让模型改写」之类未实现的承诺。

**验证与证据**

- 契约 harness `evals/product-v2/harness/prompt-edit-contract.js`（M01–M12）：正常编辑与链式编辑、hash 与快照一致、
  空/超长/控制字符/无变化阻断、未确认事实阻断、语言与引用降级为提示、主图平台提示、记录自检、失效投影精确、
  过期与确认失效联动、反向探针（篡改记录必须变红、编译器仍严格）。
- `tools/verify_v2_3_6_prompt_manual_edit.py`：`node --check` + 真实 Chromium 契约 + 正式入口 UI 流
  （编译全部 → 确认生成 → 编辑主图提示词 → 确认失效并回落 → 非法编辑被拒且旧版本保留 → 再次确认 → 刷新恢复）
  + 截图 + 零 console error + 回归既有套件。
- 证据：`evals/product-v2/v2.3.6-prompt-manual-edit-<stamp>.txt/.json/.png`。

**边界与复访**：不做分段编辑、模型改写、A/B 推荐或多版本并存比较（需要时另立任务）；不改变参考图选择与
请求参数（仍是 §9.7 的 Provider 档）；真实出图仍属 Phase 4，本任务只保证“将要发送的字符串”与记录一致。

### 9.10 V2.4.1 无状态图像网关：合同、装配与错误分类

本节是 `qwen-image-3.0` 网关的操作级设计：`src/providers/v2_image.py`（合同与分类）、
`v2_dashscope_image.py`（真实适配器）、`v2_fake_image.py`（替身）。选型依据在项目上下文 §4.1 的
SEL-010，这里不重复论证；请求形状沿用 V1 已验证的冻结合同，不重新发明协议。

**三条路由（都不保存任何状态）**

- `POST /api/v2/images/submit`：`action_id` + `prompt` + 参考图（角色 / 媒体类型 / sha256 / base64）
  + `size` / `seed` / `model_id` → provider 与 model 身份、task id、状态、结果数量、错误、request id。
- `POST /api/v2/images/status`：`task_id` → 权威状态（PENDING / RUNNING / SUCCEEDED / FAILED /
  CANCELED / UNKNOWN）与结果数量。
- `POST /api/v2/images/result`：`task_id` → 图片字节流（`Content-Type` + `X-Image-Sha256` + 身份响应头）。
- 上游签名结果地址只在本进程内使用；返回给浏览器的 JSON 永远不含地址。

**不变量（写成判据，验证器逐条检查）**

1. 无任务表：服务端不保存任务；同一 task id 在任意时刻、任意实例上给出同样结论。
2. 每次请求新建 provider 实例：任何“上次调用过”都不参与本次结论（取回结果不要求先查询）。
3. 输入白名单：契约外字段（含 `directory` / `workspace`）一律 400，不读本机路径。
4. 四类归口：`input_rejected`→400、`provider_failed`→502、`provider_unknown`→504
   （`unknown:true` + `requires_review`）、`internal`→500 / 503。
5. 明确失败与未知分离：任务 FAILED 是数据（200 + `status=FAILED` + 说明）；连接中断、5xx、
   无法解析与任务号不符才是 Unknown，且 Unknown 不自动重提。
6. 结果只认 PNG：非 PNG 字节进制失败，不做宽容解析；结果地址必须落在受信阿里云 HTTPS 主机。

**装配**：`v2_registry.create_image_provider` 读同一份 `config/product-v2/providers.json`
（`role=image`）：默认 `dashscope-image`，`AMZ_V2_IMAGE_PROVIDER=fake-image` 切替身，
`AMZ_V2_FAKE_IMAGE_SCENARIO` 选场景。密钥只从环境变量读（`DASHSCOPE_API_KEY`）；缺失时
capabilities 仍 200 且 `configured=false`，提交返回 503 `PROVIDER_NOT_CONFIGURED`。

**边界与复访**：本批不生成候选、不写浏览器状态、不证明出图质量；浏览器侧 Attempt / action ID /
Unknown 恢复属于 V2.4.2，批量与部分失败属于 V2.4.3，候选 Blob 属于 V2.4.4。真实调用只在
V2.4.5 的真实参考图闭环里按 §12.2 的成本纪律发生（V2.4.1–V2.4.4 全部用假替身离线验证，
所以 Gate G4 的「真实参考图请求成功」仍缺证据）。

### 9.11 V2.4.2 浏览器 Attempt、action ID、task ID 与 Unknown 恢复

本节是「一次生成」在浏览器里的身份与恢复设计；唯一权威是
`app/product_v2/domain/attempt.js`（形状、状态机、恢复判据），网关合同仍是 §9.10。

**对象**：`GenerationAttempt`，按 Shot 追加版本存进 IndexedDB
（`kind = generation_attempt`，`document_id = shot_id`，append-only，永不覆盖、永不删除）。
一条 Attempt 记录：`action_id`、`state`、`prompt{version,hash}`、`references[{role,sha256}]`、
`provider{provider_id,model_id}`、`parameters{size,n,prompt_extend,watermark}`、`task_id`、
`request_id`、`error{family,code,message,retry_policy}`、`created_at`、`updated_at`、`change_log[]`。

**状态机**（`pending_submit → submitted → running → succeeded | failed | unknown`）

1. `pending_submit` 在**发起请求之前**先落库：浏览器崩溃或刷新时，任务身份仍然存在。
2. 提交返回后按结果推进：拿到 task id → `submitted`（其后查询可能推进为 `running`）；
   上游明确拒绝（input_rejected / provider_failed）→ `failed`；连接中断、5xx、无法解析 → `unknown`。
3. `succeeded` / `failed` 是终态。`unknown` 也是该 Attempt 的终态：它**不允许**被改写成 `submitted`，
   只能由用户显式「新建 action」——那条新 Attempt 有新的 action_id，旧记录原样保留。
4. 有 task id 的 Attempt 必须能`核对`：查询按已保存的 task id 进行，因此服务端重启、换标签页、
   换浏览器会话都不影响结论（服务端没有任务表，§9.10）。
5. 没有 task id 的 Unknown 不许自动重提：界面只提供「核对」（若可能有 id）与「显式新建 action」。

**防重复**：同一 Shot 在 `pending_submit…running` 期间按钮不可用，且提交入口有重入保护；
双击、连点、刷新都不会产生第二条同 action 提交。重试属于用户动作，不属于自动行为。
唯一例外：没有 task id 的 `pending_submit`（刷新 / 崩溃中断、无法核对）与没有 task id 的 Unknown
同规则——不自动重提，但用户可以显式「新建 action（放弃核对）」；有 task id 的进行中记录仍然只能先核对。

**过期**：Attempt 记录它编译时用的 Prompt 版本与 hash。Prompt 被重新编译或人工编辑后，旧 Attempt
仍是历史（不失效、不删除），但界面必须标明「基于旧版本 v?」；要为新版本出图，用户确认后提交新 Attempt。

**证据要求**：提交前落库、双击只产生一条、刷新恢复、刷新中断的 pending 保留身份且不自动重提、
服务端重启后按 task id 核对、Unknown 不自动重提、显式新建 action 保留旧记录（含无身份的 pending）、
Prompt 前进后旧 Attempt 有「基于旧版本」标记。

**边界**：本批不保存候选字节（V2.4.4）、不做整套批量与部分失败（V2.4.3）、不做审核与返工（Phase 5）。

### 9.12 V2.4.3 整套批次执行与逐图进度

本节是「一键生成整套」的批次设计；唯一权威是 `app/product_v2/domain/batch.js`（纯函数投影），
单张 Attempt 的身份与恢复规则不变（§9.11）。批次层不写存储、不发请求、不读时钟、不生成 action id。

**没有批次实体**。批次不是一种被存储的对象：进度、队列与下一步全部由「套图顺序 + 每张图最新
Attempt + Prompt 就绪状态」即时推导（`deriveBatchState`，同输入必得同输出）。刷新、关标签页、
换浏览器会话后按同样输入重算即得同样结果，不存在第二份需要对账的状态，因此没有「批次丢了」
这种恢复问题。

每张图在批次里的状态是六值投影：`blocked_no_prompt`（无 Prompt）、`ready`（待提交）、
`active`（处理中）、`succeeded`、`failed`、`unknown`；前两个是「未提交」的两种原因，
其余是 Attempt 状态的直接投影。提交顺序 = 套图顺序（唯一权威是套图计划，批次层不重排）。

**队列与下一步**。推导输出四个队列：`queue`（可提交）、`reconcile_queue`（有 task id、只能核对）、
`retry_queue`（明确失败、可重试）、`review_queue`（无身份的未知，只能人工核对）。下一步优先级：
`empty → submit → compile → wait → review → retry → done`——先把能自动推进的动作补全，再把未知
交回人工。

**停止语义**。两种停止都不改变任何既有记录：

1. 系统性停止：提交结局属于 `BATCH_HALT_CODES`（`SUBMIT_OUTCOME_UNKNOWN`、`RESPONSE_UNREADABLE`）
   或 `error.family = internal`（服务端内部故障、provider 未配置）时，立即停新增提交——继续提交只会
   把剩余图片拖成同类记录。这是提交结局的判定（`batchSubmitHalts`），不是界面文案判断。
2. 用户停止：只停「新增提交」，不撤销、不覆盖、不删除任何已在途或已完成记录；再次点击从剩余队列继续。

单张的明确失败（input_rejected / provider_failed）与单张的未知（上游 504）不停止批次——它们可隔离、
可单独处理。

**无身份记录与重试**。无 task id 的 `pending_submit` 与 `unknown` 永不进入提交队列与重试队列
（`attemptReconcileMode` 判为不可核对），只能显式「新建 action」（§9.11 同规则）。重试是用户显式
动作：沿用旧 Prompt 版本、产生新 action_id、旧记录逐字保留。

**轮询**。批次运行在浏览器侧轮询（`BATCH_POLL_INTERVAL_MS = 4000`，最多 300 轮），只核对有 task id
的记录；每轮按最新记录重推投影并渲染。服务端不参与（无任务表，§9.10）。

**证据要求**（`tools/verify_v2_4_3_batch_execution.py`，V2.4.3-00..13）：正常批次按套图顺序
各提交一次并自动核对到全部成功；部分失败隔离（一张 failed 不阻塞其余，成功记录零改写）；失败单张
重试旧记录逐字保留；Unknown 无 task id 不自动重提、显式新建 action 后成功；停止只停新增提交；
刷新恢复后「继续生成剩余」。终版证据：`evals/product-v2/v2.4.3-batch-suite-<stamp>-final.txt/.json`
与 `evals/product-v2/evidence/v2.4.3-batch-suite-<stamp>.png`。

**边界**：本批不保存候选字节（V2.4.4），不做审核、比较与返工（Phase 5），不做交付门禁（Phase 6）。

### 9.13 V2.4.4 候选字节流、Blob 持久化与容量管理

本节把「成功结论」变成可复看、可核对的本地字节。唯一权威是 `app/product_v2/domain/candidate.js`
（纯函数：PNG 尺寸解析、候选记录构造与校验、与来源 Attempt 的身份匹配、入库判据）加上内容寻址的
assets 仓；批次层只多一个投影值（见下），不新增批次实体。

**身份与指针**。候选身份 = 来源 Attempt 的 `action_id`：同一 action 只允许一条候选记录，记录里只放
`asset_sha256` 指针与冻结的媒体信息（宽、高、字节数、媒体类型），字节本体在 assets 仓按 sha256 内容
寻址——同一份字节只存一份，导出与预览都读同一份字节。

**下载即存**。终态成功的那一步（提交直接到终态或核对到成功）自动取回字节：`POST /api/v2/images/result`
只接受 200 + `image/png`；服务端声明的 `X-Image-Sha256` 与本机重算的 sha256 必须一致，否则不保存
（宁可没有候选，也不存不可信字节）。取回与保存失败不改变既有 Attempt 记录。

**幂等与刷新**。已入库即跳过（`candidateStoreDecision`）：刷新、重开项目不重复保存、不新增取回请求；
预览用 object URL（每个候选一个，关闭项目统一撤销），来源是 IndexedDB 里的字节，不是上游临时地址。

**容量与半份记录**。assets 事务失败不产生半份记录：配额不足被翻译成可恢复指引（浏览器存储空间不足、
先清理或导出再点「保存候选图片」重试），记录保持原样，重试走同一 action。

**批次投影扩展**。批次每张图多一个状态 `succeeded_unstored`（已生成、待保存候选）与队列 `fetch_queue`；
`settled` 要求未保存数为 0；下一步优先级 `empty → submit → compile → wait → fetch → review → retry → done`；
只有待保存候选时按钮显示「保存候选（N 张）」，一次把剩余候选存完。

**证据要求**（`tools/verify_v2_4_4_candidate_blob.py`，V2.4.4-00..10）：C01–C10 契约套件全过并回归
Attempt / 批次 / 确认单 / Prompt 编辑 / 套图编辑器五个既有套件；单张成功自动入库且记录 sha = 重算 sha =
响应头 sha、64×64 预览可见；刷新后候选保留、零新增取回请求、不重复保存；取回失败一次不留半份记录且
可恢复；配额异常在 IndexedDB 协议层注入（产品代码无测试钩子）、失败可恢复；整套批次只提交剩余图一次、
全部成功且候选全部入库。终版证据：`evals/product-v2/v2.4.4-candidate-blob-<stamp>-final.txt/.json`
与 `evals/product-v2/evidence/v2.4.4-candidate-blob-<stamp>.png`。

**边界**：候选是「字节 + 身份」，不是「选中的成品」；本批不做审核、比较与选择（V2.5.x）、不做单图返工与
交付门禁（Phase 5 / 6），也不做容量统计与清理界面。

### 9.14 V2.4.5 真实参考图最小闭环与默认传输缺陷

本节把 Gate G4 的「真实参考图请求成功」从离线断言补成真证据，并记录首跑暴露的真实缺陷。

**工具**：`tools/verify_v2_4_5_live_reference.py`。只在显式 `--live` 且环境里存在 `DASHSCOPE_API_KEY`
时运行，默认不执行、不产生证据、不进 CI。预算按 §12.2：1 次 submit + 有界 status 轮询 + 1 次 result
取回；语义槽位由验证器直接播种（0 次语义调用）；参考图用 Product V1 真实运行留下的商品原图，路径与
sha256 写进证据。

**首跑发现的缺陷（2026-09-30）**：默认 HTTP 传输是模块级函数（`_requests_transport`），而 `_call`
按 Transport 协议调用 `self._transport.request(...)`；V2.4.1–V2.4.4 的全部离线验证都注入「对象式」
假传输，这条接缝从未被真实走过，所以真实提交必然 500（`AttributeError` 被归口成 Unknown 而不是伪造
成功——记录保持原样、不自动重提，行为本身符合合同）。修复：`src/providers/v2_dashscope_image.py`
新增 `_as_transport`，把函数式与对象式传输都归一成带 `request` 的对象；`tools/verify_v2_4_1_image_gateway.py`
新增 V2.4.1-24「默认传输离线回归」（monkeypatch `requests`，0 次网络），把这条缝永久纳入 CI。

**结果**：真实闭环通过。1 次真实 submit（真实商品参考图 + 生产 Prompt 编译结果）→ 3 次状态查询到
`succeeded`（task id `0a0d13c8-cb50-45dd-a15d-0533688b40a4`）→ 1 次结果取回：1344×1344 PNG、
1,452,960 字节，存为浏览器 IndexedDB 里的 Blob，sha256 三方一致（候选记录 = 本机重算 =
`X-Image-Sha256`），浏览器内可见预览。终版证据：`evals/product-v2/v2.4.5-live-reference-<stamp>-final.txt/.json`
与 `evals/product-v2/evidence/v2.4.5-live-reference-<stamp>.png`。

**边界**：不证明出图审美质量、跨品类通用性、审核与返工（Phase 5）；真实调用失败时保留证据、不循环重试。

### 9.15 V2.5.1 确定性验证器：生成前、单图与导出

把 §8.2 的第 1–4 与第 7 层校验落成一份带规则版本的确定性引擎：它只对可复现测量负责，不把审美
判断写成硬门；VLM（第 5 层）与整套一致性（第 6 层）由 V2.5.2 / V2.5.5 接入同一套 ReviewReport 词汇。
generation 层覆盖第 1–3 层（输入/计划/生成预检），消费「生成前确认单」这一个既有投影，不复制其计算。

**规则注册表**（唯一权威 = `app/product_v2/domain/review.js`）：每条规则必须有
`rule_id / version / layer / 违规严重度 / consumer / measurement / unknown_policy` 七要素；
`measurement` 指向已有权威（确认单、PNG 头解析、选择链），`consumer` 写成「组件@任务号」；
注册表自检（`checkRuleRegistry`）对缺要素、重复 id、未知词表直接失败。严重度语义：`BLOCK`
机械阻断其消费者的门；`HIGH_RISK` 必须醒目提示但不自动拒绝；`WARNING` 只告知；`PASS` 是已测量
通过的记录；`UNKNOWN` 只降级为提示、永不阻断（`unknown_policy = hint | disable`）。

**三层规则**
- generation（消费确认单）：Prompt 当前性、依据依赖、平台/Provider 匹配、参考图数量四组 blocker
  映射为 BLOCK；确认单 risks 映射为 WARNING；输出供 V2.5.3 审核面板消费。
- candidate（消费候选字节与记录）：PNG 合同与记录一致性 → BLOCK；最小长边 1000px（Amazon US
  启用缩放的要求）→ BLOCK；推荐长边 1600px、像素位深 > 8、主图非 1:1 → WARNING；透明通道存在
  （颜色类型 4/6 或 tRNS）→ HIGH_RISK（人工确认背景，不是自动拒绝）。所有宽高与颜色测量来自
  同一份 PNG 头解析（`candidate.parsePngHeader`），不建第二个解析器。
- export（纯函数 + 注入式字节读取）：全部必需 Shot 恰一条选择、所选候选报告为当前合同版本、
  所选报告无 BLOCK、选择→候选→来源 Attempt 身份一致、Blob 重算 sha256 与候选记录一致 → BLOCK。

**报告模型**：`buildReviewReport({candidate, findings, at})` 产出绑定
`candidate_id + review_contract_version + asset_sha256` 的 ReviewReport（findings + 按严重度汇总）；
`reviewIsCurrent(report, candidate)` 判当前性；报告以 `review_report` 文档写入 IndexedDB
（documentId = candidate_id），在候选保存路径同步生成——每个存下的候选都有当前报告。
`REVIEW_CONTRACT_VERSION` 随规则集语义上移（V2.5.2 接入 VLM 发现时同步处理），旧报告过期但
不被静默沿用。本批报告的当前性 = 候选身份 + 合同版本；绑定 ShotSpec 版本的判定在 V2.5.2 与
VLM 报告一并落地（失效表 `invalidation.js` 已把 review_reports 纳入）。

**消费者与验证器**：candidate 层在候选入库时生成报告并在工作台投影一行摘要（V2.5.1 自身消费）；
export 层由 V2.6.2 交付门禁消费（此前由探针证明）；generation 层由 V2.5.3 消费。
`evals/product-v2/harness/review-contract.js`（R01–R13）在真实 Chromium 覆盖注册表纪律与反向注入、
三层规则正反探针、未知降级不阻断、报告形状与当前性、哈希复算；
`tools/verify_v2_5_1_deterministic_review.py` 另跑既有套件回归与一次工作台闭环（候选保存后
IndexedDB 出现当前报告、界面出现摘要行、刷新后仍在），证据落盘并纳入 CI。真实调用预算：0。

### 9.16 V2.5.2 可替换 VLM 复核 Provider：单一通道、Unknown 不阻塞

把 §8.2 第 5 层（单图 VLM 检查）落成一条与语义链路同构、但**只产生风险提示**的通道：候选与参考图
经浏览器 → 无状态服务 → 百炼兼容端点（默认 `qwen-vl-max`，`REVIEW_MODEL` 可覆盖），输出结构化
findings 再由浏览器侧映射进 ReviewReport；VLM 不产生采纳、不产生 BLOCK、失败一律落 Unknown。

**服务端合同（唯一权威 = `src/providers/v2_review.py`）**：请求 = 候选图（sha256 + 严格 base64，
服务端解码复算哈希；不一致即 input_rejected）+ 最多 3 张参考图 + ShotSpec 摘要
（title/purpose/keep/allow_changes）+ 已确认事实 + 平台/语言；上限：候选 ≤4MB、单参考 ≤4MB、
合计 ≤16MB。模型输出只允许 7 个 check（product_fidelity / part_anomaly / deformity / clipping /
garbled_text / goal_completion / prohibited_content）+ evidence + confidence；未知 check、越界
置信度、超长证据整包拒绝（INVALID_RESPONSE），max_tokens 截断归 PROVIDER_OUTPUT_TRUNCATED——
不静默清洗。错误分类复用 `v2_errors.py` 四归口与 `v2_semantic.map_openai_exception`。

**传输（SEL-003 复用，SEL-011 定案）**：`DashScopeReviewProvider` 复用
`v2_langchain_chat` 的共享装配（ChatOpenAI：显式 timeout、max_retries=0）与
`with_structured_output(..., method="json_mode", include_raw=True)`；多模态消息 = 一个文本块 +
按顺序的候选/参考图 data URL 块。不新建 HTTP 客户端、重试层、JSON 修复或第二套错误词表；
`tools/verify_v2_5_2_vlm_review.py` 用静态守卫证明这条边界（禁止 requests/httpx/urllib/openai 直连、
禁止第二份 ChatOpenAI 装配）。`v2_fake_review` 按 10 类场景做测试替身；registry 新增
`dashscope-review` / `fake-review` 两条 role=review 条目
（`AMZ_V2_REVIEW_PROVIDER`、`REVIEW_MODEL`、`AMZ_V2_REVIEW_BASE_URL/TIMEOUT/MAX_TOKENS`）。

**路由（无状态）**：`POST /api/v2/review/candidate` 是唯一放宽到 24MB 的路由（要携带图片 base64；
其余路由保持 256KB 上限）。200 = `{ok, result:{contract_version, candidate_sha256,
findings[{check,evidence,confidence}], provider/model/request_id/usage/latency}}`；失败沿用分类信封
（provider_unknown/504、INVALID_RESPONSE/502、input_rejected/400）。服务器不保存图片、结果或
工作空间；capabilities 新增 `review` 块（合同、端点、provider、参考图能力）。

**浏览器（唯一规则权威 = `app/product_v2/domain/review.js`）**：`REVIEW_CONTRACT_VERSION` 升到
`v2.5.2`；注册表新增 `vlm` 层 9 条规则（7 个 check + 完成/未完成标记），注册表自检禁止 vlm 层出现
BLOCK（模型发现不能升级为平台硬阻断）。`buildVlmReview` 把服务端 check 映射到注册表规则并由注册表
决定严重度（模型不能自带严重度）；`mergeVlmReview` 只替换 vlm 层、保留确定性 findings；成功且零发现
落 `vlm.inspection_completed / PASS`（机器事实，不等于人工采纳）；任何失败（超时/非法/拒绝/传输）
落 `vlm.inspection_unavailable / UNKNOWN`，人工审核不因此受阻。候选行新增「自动复核（VLM）」按钮
（同一页面内一人操作；比较/审核清单面板是 V2.5.3）。重开项目发生报告重建时，同一候选字节上的
vlm 块整体带过去；规则不再兼容则丢弃复核部分（回到「VLM 未检查」），不伪造结论；跨候选携带被拒绝。

**验证与边界**：`evals/product-v2/harness/review-provider-contract.js`（R14–R21）在真实 Chromium
覆盖词表映射、合并、Unknown、反向注入与跨候选携带；`tools/verify_v2_5_2_vlm_review.py` 另跑已标样例
（`fixtures/v2.5.2/` 5 个契约级样例）、fake 场景矩阵、端点契约、工作台点击闭环（checked → 刷新 →
unknown）、R01–R13 回归与正式入口自检；证据 `evals/product-v2/v2.5.2-vlm-review-*-final.*` + 截图。
真实调用 1 次：`tools/probe_v2_5_2_review_live.py --live`（候选=参考=同一张真实商品照片），证明
通道、结构化输出与候选绑定；**不评估检出质量**，检出质量校准留给后续任务。

### 9.17 V2.5.3 候选比较与审核清单：只做投影，不新增第二套报告

V2.5.2 已经把「每个候选当前一份报告」备齐（确定性 + VLM，含严重度、Unknown 与先看项），
但界面只在一行里显示一句摘要：参考图、历史候选与返工候选之间不能直接比较，审核清单也没有按严重度组织。
V2.5.3 只补这块投影，不新增规则、不重算报告、不产生选择。

**领域层（唯一权威 = `app/product_v2/domain/compare.js`）**：`compareRows` 把同一 Shot 的候选
（storage 版本链 + 各自「当前」报告）排成异常优先的顺序——有 BLOCK / HIGH_RISK / WARNING 的在前，
其次 UNKNOWN，再次无发现，未检查排最后（「还不知道」比「已确认没发现」更弱）；同档按版本新到旧，
最后用 candidate_id 兜底，保证顺序可复现。`defaultCompareTargetId` 取排在最前的那一行，
所以默认看的是问题候选而不是最新候选；`nextPendingShotId` 按套图顺序绕回找下一个有待处理候选的 Shot；
`sortFindings` 给审核清单排序（稳定，PASS 只在完整报告里）；`checkCompareRows` 是行集合自检
（唯一性 / 身份 / 排序 / pending 一致），供反向探针证明守卫能变红。
严重度顺序只有一份：`domain/review.js` 导出的 `REVIEW_SEVERITY_ORDER`，`topFinding` 与本模块共用；
静态守卫 `V2.5.3-02` 禁止第二份顺序表，`V2.5.3-03` 禁止面板写文档 / 写资产 / 碰选择。

**界面（`app/product_v2/index.html` 的 `#compare-panel`）**：入口是每张图行内的「比较候选（n）」，
同一时刻只投影一张图（一人操作，不引入第二个工作区）。面板三块：
①「这张图实际发送的参考图」——用与提交同一个 `selectReferences` 选择函数，所以比较的左边就是真实输入；
②候选列表（`role="tablist"`）——每张卡显示缩略图、版本、尺寸 / 时间 / sha256、复核徽标与一行摘要；
③审核清单（`role="tabpanel"`）——先看项按严重度排序 → 完整报告 `<details>` 按需展开（合同版本、
候选哈希、视觉复核状态、全部通过项）→ 这张图的验收依据（`specs.reviewChecklist` 投影的
目的 / 必须保持 / 允许变化 / 公共风格；单图规格未保存时明确标注用的是默认派生值）。
键盘路径：候选卡是 tab（roving tabindex），←/→/↑/↓/Home/End 移动并即时切换清单，Escape 回到行内入口；
「下一个待处理」跳到另一张有问题的图并把焦点放到它的候选上。

**边界**：面板只读——不写文档、不写资产、不产生 Selection（采纳属 V2.6.1），也不重算报告；
候选与报告的当前性仍由 `reviewIsCurrent` 与 `ensureReviewReport` 决定，过期报告一律降级为「未检查」。
单候选时退化为单卡视图（数据不变），空列表不占版面。运行时检查 `V2.5.3-13` / `V2.5.3-16` 证明面板
不改变业务记录、也没有长成采纳或导出入口。

**验证与证据**：`evals/product-v2/harness/compare-panel.js`（CP-01–CP-15，真实 Chromium）覆盖
异常优先排序、同档新到旧、默认目标、无发现 / 未知 / 未检查的区分、清单稳定性与四条反向探针；
`tools/verify_v2_5_3_compare_panel.py` 另跑静态守卫、R01–R21 回归、真实工作台走查（两次生成 +
一个合规夹具候选：面板必须把待处理候选排在无发现候选之前，默认目标是有问题的那一个）、键盘路径、
刷新一致性、单候选回退与「下一个待处理」跳转、整页与面板特写截图。证据
`evals/product-v2/v2.5.3-compare-panel-*-final.*` + `evals/product-v2/evidence/v2.5.3-compare-panel-*`。

### 9.18 V2.5.4 问题分类、改进方向与单图返工闭环

返工不是「再点一次生成」，而是把某条候选的问题、用户决定的改进方向和实际重新发送的 Prompt
组成一条可追溯命令。V2.5.4 只负责生成新版本和证明影响隔离；人工 Selection 与导出门禁分别由
V2.6.1 / V2.6.2 提交，不能在本批提前宣称已经阻止导出。

**界面责任**：V2.5.3 的 `#compare-panel` 继续只读；它可以在内存中指出当前查看的候选，但不得写文档、
资产、Attempt 或 Selection。返工是同一页面中与比较区相邻的独立 `#rework-panel`：入口「用此候选发起返工」
把 `candidate_id + sha256` 交给返工表单；表单用原生 checkbox/fieldset 展示九类常见问题，允许自由改写方向，
提供「预览返工 Prompt」「查看/编辑完整 Prompt」「确认并生成这张图」「取消」。输入均有显式 label，状态用
克制的 polite/alert 反馈，键盘焦点从入口进入表单、完成或取消后回到原候选。预览只编译、不落盘：改动问题
或方向后必须重新预览才能提交；返工入口不依赖最新一次 Attempt 的状态，失败或 Unknown 的图仍可对历史候选
发起返工。

**领域对象（唯一权威 = `app/product_v2/domain/rework.js`）**：`ReworkDirective` 保存
`directive_id / shot_id / source candidate id+sha256 / source review contract+top finding /
problem categories / direction / created_at`。报告是建议来源而不是提交权威：用户确认指令后，报告重算不静默
改写方向；候选身份或字节变化时指令失效。完整指令嵌入新的 PromptVersion，避免另建一份平行返工文档。
Prompt 编译器只追加一个 `rework_directive` 段，其余来源段、参考图选择和 Provider 参数沿用现有权威。

**确认隔离**：整套确认不能用「任一 Prompt 改动 ⇒ 所有 Shot 都失效」的全有或全无判定。
`confirmationCoversCurrentShot(record, currentSheet, shotId)` 逐图比较 Prompt hash、实际参考图、平台与 Provider；
目标 Shot 新 Prompt 只使目标确认过期，无关 Shot 的原确认继续有效。公共 StyleSpec、平台或 Provider 改动若使
多个 Prompt 变化，则受影响 Shot 分别失效。目标图写一条 `scope_shot_ids=[shot_id]` 的局部确认后才可提交。

**执行与输出**：`ReworkDirective → PromptVersion → scoped GenerationConfirm → GenerationAttempt →
Candidate Blob → ReviewReport`。提交前先持久化 action；双击只产生一条；有 task id 的 Unknown 先核对，
无 task id 不自动重提；失败保留旧 Prompt、旧候选与可用 Blob。成功只给目标 Shot 新增版本，新候选不自动
成为最终选择，用户以后可以重新选择新候选或旧候选。

**不变量与验证**：比较面板交互前后业务记录逐字一致；目标以外的 Prompt/Confirmation/Attempt/Candidate/
Blob hash 零变化；旧候选保留；返工失败可恢复；刷新后完整来源链恢复。领域合同至少覆盖空理由、未知分类、
候选跨 Shot、hash 不符、来源缺失与反向探针；浏览器覆盖正常、失败、Unknown、重复点击、刷新、键盘焦点、
console/network 和 IndexedDB 后置条件。开发与回归使用 fake provider、真实模型调用为 0；V2.3.4–V2.5.3
相关回归必须保持全绿，禁止通过放宽 V2.5.3「比较区只读」判据过关。

### 9.19 V2.6.1 人工 Selection 与失效判断

整套一致性与交付都必须有一个明确的候选集合，不能偷用「最新候选」。因此 V2.6.1 在 V2.5.5 之前实施，
任务 ID 保留但依赖顺序以 §10.1 为准。`SelectionRecord` 保存 shot、candidate id/hash/version、选择动作身份、
选择时审核指纹和时间；一个必需 Shot 最多一个 current 选择。自动审核只提供依据，不产生选择。

用户可以采用、改选、取消采用，并可在返工后重新选择旧候选。目标 Shot 出现新的成功候选时，原选择变为
stale 而不是被覆盖；失败 Attempt 不影响已有选择。Selection 只引用内容寻址的候选，不复制图片。
输出 `SelectionSet`，作为 V2.5.5 与 V2.6.2 唯一输入集合；缺选和 stale 的实际导出阻断由 V2.6.2 验证。
界面（V2.6.1）：比较候选卡只放入口「采用此候选」；采用、改选与取消在相邻的独立「采用候选（人工选择）」面板完成。
每张图的行内摘要显示当前选择与过期提示；已采用的候选带「已采用 / 已采用（已过期）」徽标，选择文档只追加、不改写历史。

### 9.19a V2.UI.1 正式远程入口、浏览器能力与错误诊断

**结果**：受支持浏览器从正式远程入口真正能够创建和恢复项目；不支持时指出缺的是 IndexedDB、WebCrypto、数据库打开、schema、配额还是事务，而不是把所有失败都写成“IndexedDB 不支持”。本任务先于视觉重构和 V2.5.5。

**事实基线（2026-09-30 预检）**：`http://47.115.172.233:8780/` 在标准 Chromium 中 `indexedDB.open()` 成功，但 `isSecureContext=false`，`crypto.randomUUID` 与 `crypto.subtle` 不存在；点击“新建项目”后 `randomId()` 抛 `UNSUPPORTED_BROWSER`，界面却显示“IndexedDB 不支持”。用户截图所在宿主还可能连 IndexedDB 都未暴露，这是另一类能力缺口，不能混为一谈。

**实现合同**：

- 正式远程产品入口必须是浏览器认可的 HTTPS secure context；`http://127.0.0.1` / `localhost` 只作为本机开发例外。TLS 在现有穿透或反向代理层终止，应用容器继续提供无状态 HTTP；不在浏览器自研 UUID、SHA-256 或加密兼容层，也不把项目迁回服务器。
- 首版支持策略固定为当前稳定版桌面 Chrome 与 Edge；嵌入式浏览器只做 feature detection 和可恢复提示，不作为完成门槛。策略写入项目上下文 SEL-012，不能由界面文案临时改写。
- 存储启动探针分别测量 `indexedDB` 是否存在、目标数据库能否打开、`crypto.randomUUID`、`crypto.subtle`、一次最小只读/写事务；错误码新增或细分时仍由 `storage/errors.js` 统一归口，界面不得靠字符串猜原因。
- 首页错误投影必须包含：实际缺口、当前 origin、推荐动作（改用正式 HTTPS、Chrome/Edge、重试或导入项目包）；修复后可原位重试，不要求刷新整页。普通成功状态不显示工程诊断。

**验收与证据**：`tools/verify_v2_ui_1_remote_entry.py` 在本机 localhost、远程 HTTPS Chrome、远程 HTTPS Edge 三条路径检查首页、console/network、IndexedDB 后置条件；HTTP 远程负例必须准确报 `secure_context/WebCrypto`，而不是 IndexedDB。空白配置文件新建项目后刷新、关页重开与服务重启仍恢复；两个独立配置文件互不出现项目。证据写 `evals/product-v2/v2.ui.1-remote-entry-*-final.*` 与对应截图。若暂时没有可信 HTTPS 入口，本任务保持未完成，不用本机 localhost 绿替代。

**回退**：代理或部署变更失败时恢复上一容器/代理配置；不迁移、不删除浏览器数据。能力探针改动失败则回到旧启动代码并保留精确失败证据，不能放宽浏览器完成门。

### 9.19b V2.UI.2 前端交互契约与视觉基线

**结果**：在继续堆功能之前，先把业务模型编译成一致的用户界面模型，并用真实 HTML/CSS/JS 状态供产品发起人走查。这个任务只确定信息、行为、状态、规则、反馈、导航和表现层；不改领域对象、状态机、Provider 或 IndexedDB 所有权。

**界面模型**：

| 视图 | 对象与信息 | 主要行为 | 必须覆盖的状态 |
|---|---|---|---|
| 项目首页 | 项目名称、更新时间、阶段、最近预览 | 新建、导入、打开、重命名、复制、删除 | 空白、列表、创建中、导入失败、存储能力失败 |
| 工作台外壳 | 当前项目、保存状态、六阶段进度 | 返回项目、切换可达阶段、继续当前任务 | 草稿、就绪、处理中、部分失败、Unknown、可交付 |
| 资料/理解 | 参考图、名称、介绍、卖点、重点、异常事实 | 编辑、分析、确认、标未知、增删允许槽位 | 缺输入、分析中、冲突/低置信、已确认 |
| 方案/生成 | SuitePlan、StyleSpec、ShotSpec、Prompt、Attempt | 增删排序、编辑规格/Prompt、确认、整套或单图生成 | 依赖阻断、过期、运行中、部分失败、Unknown |
| 审核返工 | 参考图、候选、报告、Selection、SuiteReview | 比较、定位问题、返工、采用/改选、整套检查 | 未审核、高风险、过期、已采用、Unknown |
| 交付 | 导出门禁、Unknown 确认、交付记录 | 定位阻断、确认 Unknown、生成交付包/项目包 | 不可导出、就绪、生成失败、已生成 |

**布局与视觉合同**：

- 项目首页采用紧凑产品栏 + 有边界的主内容区；空状态以一个清楚的创建入口和次要“导入项目”组成，不保留大块装饰色带、大面积无意义留白或用 placeholder 代替可见 label。
- 工作台仍是一个页面，但使用六阶段进度导航；默认只展开当前任务，已完成阶段显示短摘要并可回看。页面同时只允许一个视觉主按钮，次要动作降级为普通按钮或菜单。
- 生成、比较和返工以图片画布为主；规则结果紧邻对应 Shot。完整 Prompt、hash、action/task id、provider 原始身份进入“详情”，但仍可查看与复制。
- 建立 CSS token（颜色、字体、间距、圆角、边框、阴影、焦点、状态色）与可复用组件状态；不用内联样式，不引入框架或新的运行时依赖。正常正文/控件对比度、48px 触控目标、可见 label、语义 form、逻辑 tab 顺序和 `:focus-visible` 是基线。
- 代表状态至少包含：空白首页、已有项目、资料缺失、理解异常、方案编辑、整套生成中/部分失败、候选比较与返工、交付阻断、存储错误。测试夹具只进 harness，不把演示商品或假状态写入产品入口。

**执行顺序与落盘**：先落盘交互契约 `docs/product-v2-ui-contract.md`（六阶段固定为「资料—理解—方案—生成—审核返工—交付」；逐视图写清对象/信息/行为/状态/规则/反馈/导航与按钮理由；INDEX 以 `设计草案` 登记，走查确认后转 `架构设计`/`current`），再在正式入口实现视觉基线，最后交产品发起人走查；未确认不得置 done，也不进入 V2.UI.3。施工指令与允许改动清单见 `_working/amz-listing-kit-product-v2/tasks/v2ui2-interaction-visual.md`；被合法 DOM 重组影响的既有验证器按 §9.19c 同一规则改为语义/状态断言，不放宽、不删断言，每次推送 CI 保持全绿。

**2026-10-01 修订（用户授权）**：用户授权执行者「全权自行负责自审自测自改」，V2.UI.2 以自审走查（自动化 E2E + 截图视觉复核）先行通过并继续 V2.UI.3；产品发起人走查与陌生人验收（C15/C17、V2.7.3）保留为发布前人工硬门，不得由自审替代。自审证据：`evals/product-v2/v2.ui.2-walkthrough-record.md` 自审节 + `evals/product-v2/remote-persistence-*` + `evals/product-v2/v2.7.2-remote-real-e2e-*`。

**2026-10-01 修订（V2.UI.3 自审通过）**：同一授权下，V2.UI.3 以自审先行通过：`tools/verify_v2_ui_3_frontend.py` 16/16（空白创建→采用→交付门禁的 fake 主链、失败/Unknown 演练、焦点与保存状态、390px/200%、零意外 console），并按 CI 清单跑完 27 项既有回归；发现并修复「无任务编号的 Unknown 行缺少说明」与验收套件演练 provider 复用缺陷。证据：`evals/product-v2/v2.ui.3-frontend-20261001-025613-final.*`（+回归重跑 `-030253.*`）与 `evals/product-v2/evidence/v2.ui.3-frontend-*`。后续动作转 V2.5.5；产品发起人走查（C15/C17）仍是发布前人工硬门。

**2026-10-01 修订（V2.5.5 自审通过）**：整套一致性以自审先行通过：`tools/verify_v2_5_5_suite_review.py` 12/12（服务端词表/合同/上限镜像、单一权威、S01–S06 契约套件、工作台 current→发现→定位→过期→重算→刷新、视觉失败只落 UNKNOWN）+ 全量回归（含 V2.3.2/V2.5.2/V2.5.3/V2.5.4 的语义化断言修订）；期间修复两个真实缺陷：审核分区与方案阶段节点 id/键名撞车（错误提示写进错误的元素）、契约套件夹具 action_id 与候选身份不一致。证据：`evals/product-v2/v2.5.5-suite-review-20261001-034436-final.*` 与 `evals/product-v2/evidence/v2.5.5-suite-review-*-final-*.png`。后续动作转 V2.6.2。

**验收与证据**：用正式入口与 fake provider 产出 1440px 整页、关键区域特写、390px 和 200% 缩放证据；产品发起人在真实页面走查首页、资料、方案、生成、审核和错误状态，明确确认信息层级、主操作、图片比较与视觉方向。任何“需要旁边解释才知道点哪里”、工程字段压过业务信息、关键操作被遮挡或视觉仍像调试表单，都使本任务未通过。证据写 `evals/product-v2/v2.ui.2-interaction-visual-*-final.*`。

**回退**：设计未确认时只改交互契约和表现层，不继续 V2.UI.3；现有业务代码和数据不动。

### 9.19c V2.UI.3 真实首页与同页工作台重构

**结果**：把 V2.UI.2 的契约落到正式入口，所有页面由真实 repository/domain/service 状态驱动；不再维护“演示页面”和“真实页面”两套前端。现有项目数据、版本链、动作身份、候选 Blob 与报告合同保持兼容。

**实施边界**：

- 重组 `index.html` 的语义结构和 `styles.css` 设计系统；`app.js` 负责项目首页与应用外壳，`workspace.js` 将已有分区投影进六阶段导航。DOM 不是新状态源；是否可进入某阶段继续由现有领域状态、依赖和报告派生。
- 首页完成空/列表/创建/导入/异常五态；工作台完成阶段摘要、当前阶段、全局保存状态和唯一主操作。异步完成后焦点落到结果标题或首个问题，失败焦点落到错误摘要。
- 不删除现有功能：槽位增删确认、套图增删排序、Style/Shot/Prompt 编辑、生成前确认、批量生成、Unknown 核对、比较、返工、采用都必须在新结构中可达；旧验证器若因合法 DOM 重构失效，应改为语义/状态断言，不能删断言求绿。
- V2.5.5 的“整套一致性”进入审核阶段，V2.6.2 的门禁与下载进入交付阶段；本任务只预留正确落点，不伪造未实现结果。

**验收与证据**：`tools/verify_v2_ui_3_frontend.py` 跑空白创建到人工采用的完整 fake 链、每个阶段的拒绝/失败/Unknown、刷新恢复、键盘路径、390px、200% 缩放、零意外 console/network，并核对 IndexedDB 前后状态。既有 V2.1.2、V2.2.3、V2.3.2–V2.3.6、V2.4.2–V2.4.4、V2.5.3–V2.5.4、V2.6.1 回归必须保持；产品发起人最终浏览器走查通过后才允许开始 V2.5.5。证据写 `evals/product-v2/v2.ui.3-frontend-*-final.*`。

**回退**：按 Git 提交边界恢复旧 DOM/CSS/投影，IndexedDB schema 与业务记录不回滚；新 UI 未通过时仍保留修复后的 V2.UI.1 正式入口。

### 9.20 V2.5.5 基于 SelectionSet 的整套一致性报告

输入是当前 SelectionSet、已选候选 Blob、ProductBrief、SuitePlan、StyleSpec、ShotSpec 与单图 ReviewReport。
确定性部分检查必需角色、卖点覆盖、重复/遗漏、尺寸格式、报告当前性及 Selection/Blob/hash 一致；视觉部分
复用 SEL-003/011 的 ChatOpenAI 通道，检查商品外观、颜色材质、公共风格与跨图低级异常，不新建 HTTP 客户端。

`SuiteReviewReport` 绑定 `selection_fingerprint + contract_version`，每条发现带 `affected_shot_ids`；选择变化后
报告精确过期并可重算。确定性 BLOCK 交给导出硬门；VLM 只能给提示或 Unknown，不能取消人工选择，Unknown
由用户明确复核。报告界面直接跳到相关 Shot，不建立第二套候选状态。

**落地契约（V2.5.5 实现层）：**

- 唯一权威 `app/product_v2/domain/suite-review.js`：`SuiteReviewReport` 的构造、输入指纹与当前性、确定性发现组装与 VLM 合并；报告以新文档种类 `suite_review`（append-only，document_id=`suite_review`）写入浏览器 IndexedDB。
- 规则注册表新增（review.js，唯一权威）：`suite.selection_current`、`suite.dependency_satisfied`（BLOCK）；`suite.duplicates`、`suite.recommended_omissions`、`suite.selling_point_coverage`（WARNING）；`vlm.suite_product_consistency`、`vlm.suite_color_material_consistency`、`vlm.suite_cross_image_anomaly`（HIGH_RISK）；`vlm.suite_style_consistency`、`vlm.suite_inspection_completed`、`vlm.suite_inspection_unavailable`（WARNING）。每条发现必须带 `affected_shot_ids`；导出层测量复用 `evaluateExportReadiness` / `verifyAssetHashes`，不写第二套。
- 视觉通道：服务端新增无状态 `POST /api/v2/review/suite`；provider 复用 SEL-003 的 ChatOpenAI 装配（不新建 HTTP 客户端）。请求=每张被选图的 {shot_id、标题/目的/保持/允许、sha256+bytes}+已确认事实+公共风格摘要；响应 findings 每条带 `shot_ids`（⊆ 送审集合）与 check（词表与服务端 `SUITE_VLM_CHECKS`、浏览器 `SUITE_VLM_CHECK_TO_RULE` 互为镜像，由验证器比对）。单次最多 8 张；超过 8 张时视觉层记 Unknown 并说明，确定性部分照常。
- 报告绑定：`selection_fingerprint`（SelectionSet 规范化快照）与 `inputs_fingerprint`（另含计划、规格、所选报告身份）；选择或输入变化即过期并可重算。VLM 失败只产生 UNKNOWN，不自动取消选择、不拒绝整套；确定性 BLOCK 供 V2.6.2 导出硬门消费。
- 界面：独立「整套一致性」分区（状态行 未检查/当前/已过期；「运行整套检查」；按严重度分组、每条发现可点击跳转到对应图行；视觉层显示 checked/unknown 与 provider 身份）；不建立第二套候选状态。
- 正式入口自检新增整套复核检查（33 项以上），同步更新既有验证器里对旧计数的断言。
- 验证：`tools/verify_v2_5_5_suite_review.py` = 静态守卫 + `suite-review-contract` 套件 + SL/RW/CP/R 回归 + 跨语言镜像比对（词表/合同版本/张数上限）+ 工作台走查（一致套图、漂移探针、选择变化失效、Unknown 人工复核、刷新恢复、跳转定位、零意外 console）。证据 `evals/product-v2/v2.5.5-suite-review-*-final.*` + `evidence/v2.5.5-suite-review-*.png`。

### 9.21 V2.6.2 浏览器交付 ZIP 与硬门禁

**落地契约（V2.6.2 实现层）：**

- 交付门禁唯一权威 `app/product_v2/domain/export-gate.js`：只消费既有测量（`evaluateExportReadiness`、`verifyAssetHashes`、`suiteReviewIsCurrent`、`checkSuiteReviewReport`），不重做第二套；新规则登记进 review.js 注册表：`export.suite_review_current`（BLOCK：整套报告存在、对当前 selection/inputs 当前且无未消解 BLOCK）与 `export.unknown_acknowledged`（BLOCK：当前单图与整套报告中的每条 UNKNOWN 都有对应人工确认）。
- Unknown 确认是 append-only 文档 `review_acknowledgement`（document_id = 目标报告 id + rule_id + 规范化 shot_ids 摘要；含 target_kind/target_id/rule_id/shot_ids/acknowledged_at）：只记录「已知悉」，不改写发现、不自动选择、不删除报告。
- 交付包用 `storage/zip.js`（buildZip）生成，固定内容：`images/<shot_id>-<candidate_id>.<ext>`、`manifest.json`（选择与输入指纹、每图 shot/candidate/attempt/asset sha256、PromptVersion 身份）、`checks.json`（当前单图与整套发现投影）、`README.txt`（人读摘要）；成功后写入 append-only 文档 `export_record`（包 sha256、字节数、included_shot_ids/candidate_id/sha256 清单、生成时间），重复生成只追加、不覆盖历史；任何一步失败不产生完成记录，界面返回精确问题 Shot。
- 新文档种类 `export_record` 与 `review_acknowledgement` 登记进 shared.js `DOMAIN_DOCUMENT_KINDS`（唯一权威）。界面：交付分区含门禁清单（逐条 PASS/BLOCK 与定位）、「生成交付包」按钮、成功后的文件名/大小/sha256 与下载入口；不新增第二套状态。
- 验证：`tools/verify_v2_6_2_delivery.py` + `delivery-gate-contract` 套件：正反门禁（缺选择、整套报告过期、未确认 Unknown、哈希不符）、ZIP 解包逐文件核对、manifest 反查输入到候选、失败不落记录、重复生成保留历史。证据 `evals/product-v2/v2.6.2-delivery-*-final.*` + `evidence/v2.6.2-delivery-*.png`。

### 9.22 V2.6.3 项目 ZIP 迁移与 schema 升级闭环

**落地契约（V2.6.3 实现层）：**

- 迁移权威仍是 `storage/package.js` + `transfer.js`：包格式升到 2，携带每记录 schema_version 与完整文档/资产清单；`parseProjectPackage` 先校验格式与完整性，再按 `migrations.js` 迁移链升级旧包（格式 1 / 旧 schema）；无法升级时给出精确条目并拒绝导入，不做静默降级。
- 导入保持单 IndexedDB 事务（projects/documents/assets）且全量先校验后写入：任一记录非法整体回滚，不留半成品；导入为新 project_id 时保留完整历史（所有文档版本与资产字节），导入后可直接继续返工、选择与生成交付包。
- 验证：`tools/verify_v2_6_3_project_transfer.py` + 双浏览器往返（导出 → 清空 → 导入 → 再导出逐哈希一致；导入后完成一次返工与一次交付包生成）+ 旧格式 fixture 升级路径。证据 `evals/product-v2/v2.6.3-transfer-*-final.*` + `evidence/v2.6.3-transfer-*.png`。

### 9.23 V2.6.4 渐进披露、空/忙/错/Unknown 与可访问性

**落地契约（V2.6.4 实现层）：**

- 界面唯一权威仍是 `app/product_v2/index.html` + `workspace.js` + `styles.css`，不新增业务状态：工程字段（指纹、sha256、attempt/task id）默认收进「详情」；每个分区必须可观察空/忙/错/Unknown 四态，且每态都有下一步动作（重试、取消、定位、确认），不用说明文字掩盖模型错误。
- 390px 宽度与 200% 缩放不遮挡关键操作、无横向溢出；完整任务路径可纯键盘走通（可见焦点、图标按钮有可访问名、异步完成后焦点落点明确）。
- 验证：`tools/verify_v2_6_4_accessibility.py` = Playwright 390px/200% 截图 + 键盘脚本 + axe 扫描 + console/network 断言 + 真实入口走查。证据 `evals/product-v2/v2.6.4-a11y-*-final.*` + `evidence/v2.6.4-a11y-*.png`。

## 10. 实施阶段、任务与 Gate

任何时刻最多一个阶段 active。每个任务同时交付必要的数据合同、服务、界面和验证，不把“前端做完”“后端做完”当作用户可观察成果。

**选型前置：** 任何任务在动手前必须先过 `AGENTS.md` 的选型门禁——预计新增运行时依赖，
或新增通用基础设施（而不是业务语义）时，先交选型报告并经用户确认；结论记入
`docs/product-v2-project-context.md` §4，依赖登记由 `tools/check_docs.py` 双向比对。
未过门禁的任务不得进入实现。

### Phase 0：控制面与遗留基线切换

目标：Product V2 成为唯一当前目标，Product V1 成为可回归历史基线。

**Gate G0：** INDEX、项目上下文、计划和 state 身份一致；文档与状态守卫全绿；旧 D4.13 不再是 next action；旧代码零功能改动且可由 git 恢复。

### Phase 1：浏览器拥有项目

目标：用户从空白浏览器创建、恢复、删除、导入和导出项目；服务器不保存业务状态。

**Gate G1：** 刷新、浏览器重开和服务器重启均恢复项目；两个独立浏览器配置文件项目列表不同；项目包往返 hash 一致；服务器 recent index 和文件夹 API 不参与 V2 正式路径。

### Phase 2：商品理解与异常确认

目标：DeepSeek 根据输入生成结构化商品理解，用户只需处理关键异常并能编辑槽位。

**Gate G2：** 四类商品得到不同动态槽位；来源、状态和依赖可追溯；非法模型输出不写入项目；关键事实未确认时不能进入计划完成态。

### Phase 3：可编辑套图与 Prompt 编译

目标：推荐方案可增删排序，条件依赖明确，Prompt 可见可改且与真实请求一致。

**Gate G3：** 用户能新增自定义 Shot、修改 StyleSpec/ShotSpec；缺依赖的对比/尺寸/成分图被精确阻断；失效传播范围正确；Prompt 无规则混杂检查通过。

### Phase 4：真实整套生成与浏览器恢复

目标：浏览器持有 Attempt 与候选，服务器无状态调用 qwen-image-3.0。

**Gate G4：** 真实参考图请求成功；批量部分失败不丢结果；已知 task ID 在服务器重启后可继续查询；Unknown 不自动重提；候选 Blob 和来源链持久化。

### Phase 5：产品界面、自动校验、比较、局部返工、人工选择与整套一致性

目标：正式远程入口在受支持浏览器可用，业务对象被投影为可走查的成品界面；系统发现低级错误并把异常投影给用户，返工只影响目标 Shot；人工明确选出整套候选后，系统才对该集合做一致性检查。

**Gate G5：** 正式 HTTPS 入口在当前 Chrome/Edge 能空白创建与恢复项目；首页和六阶段同页工作台通过产品发起人的视觉/交互走查；每个候选有当前 ReviewReport；参考/旧/新候选可直接比较；目标 Shot 返工后旧候选保留、无关 Blob 与 Attempt hash 不变；每个必需 Shot 有明确且当前的人工 Selection；整套一致性报告绑定 SelectionSet、可重算并定位到 Shot。

### Phase 6：选择、交付与可用性

目标：基于 Phase 5 的人工选择与一致性结论，浏览器生成交付包和完整项目包，并完成可用性收尾。

**Gate G6：** 缺选或硬检查失败时不能导出；交付 ZIP 可复检；完整项目包可跨浏览器恢复；390px、200% 缩放、键盘和失败反馈满足产品基线。

### Phase 7：跨品类、真实模型与首次使用者验收

目标：证明机制通用、主链真实、陌生人可独立完成，而不把 Mock 或单个商品当成产品完成。

**Gate G7：** C1–C17 全部 proven；至少一个非内置商品完成真实闭环；首次使用者无口授完成任务；代码、配置、静态资源与完成证据一致。

### 10.1 唯一任务表

| ID | 结果/产物 | Depends | 验收条件 | 验证证据 | 失败/回退 |
|---|---|---|---|---|---|
| V2.0.1 | Product V2 权威地图、项目上下文、详细计划与 Goal 绑定 | — | 新旧世代、事实所有者、非目标和系统 Goal 身份明确 | INDEX、上下文、计划 diff、Goal 读数 | 回退控制面提交，不改实现 |
| V2.0.2 | Product V2 state 与守卫适配 | V2.0.1 | 唯一 active state、唯一 next action、旧 state 可保留为 superseded | `check_docs`、`check_project_state` 和反向探针 | 回退守卫和 state，不降低门槛 |
| V2.0.3 | Product V1 冻结基线与迁移边界 | V2.0.2 | 旧 D4.12 证据可定位；旧正式入口未被本次文档切换破坏 | git diff、旧回归报告、`product-v1-d4.12-baseline` 标签 | 从 Git 标签恢复 |
| V2.CI.1 | GitHub Actions CI 与 Docker CD | V2.1.4 | PR/push 校验控制面、正式入口、浏览器合同并构建健康镜像；仅 `main` SSH 部署 SHA 镜像；健康失败自动恢复上一容器且不删除其他应用 | 本地静态/容器验证、PR Action run、main 部署日志与 `/api/health` | PR 不部署；CD 失败保留或恢复上一容器，必要时暂停 workflow |
| V2.1.1 | IndexedDB schema、repository、migration 与事务测试 | G0 | JSON/Blob 版本、当前指针、事务和迁移契约可执行 | 单元测试、schema 反向探针 | feature flag 回退旧入口 |
| V2.1.2 | 空白项目首页与项目 CRUD | V2.1.1 | 新建、打开、重命名、复制、删除只影响当前浏览器 | Playwright + IndexedDB 后置条件 | 保留旧 Product V1 路由 |
| V2.1.3 | 完整项目 ZIP 导入/导出 | V2.1.1 | 往返后对象、Blob 和 hash 一致；损坏包被拒绝且不污染现有项目 | round-trip、篡改包测试 | 导入先 staging，失败不 commit |
| V2.1.4 | V2 正式入口脱离服务器 workspace/recent | V2.1.2, V2.1.3 | V2 请求无 directory；服务重启和磁盘审计证明不保存业务状态 | API 契约、磁盘前后 diff、浏览器恢复 | V1 路由保留但不进 V2 导航 |
| V2.2.1 | FactSlot、ProductInput、ProductBrief 和失效图契约 | G1 | 固定/动态/自定义槽位权限和来源状态可机检 | schema、状态转换、依赖传播测试 | 不迁移旧项目，保留 schema 版本 |
| V2.2.2 | `deepseek-v4.1-flash` SemanticProvider | V2.2.1 | 结构输出校验、超时/拒绝/非法响应分类明确；给推理型输出预留预算且可见文本为空时明确判错 | fake provider、契约测试、最小真实请求 | Provider 可配置回退；不写半成品 |
| V2.2.3 | 商品资料与异常驱动理解界面 | V2.2.2 | 默认只突出冲突、未知、低置信和必确认项；可展开全部事实 | 浏览器轨迹、可访问性、状态后置条件 | 保留用户输入草稿，不覆盖确认事实 |
| V2.2.4 | 四类商品理解通用性探针 | V2.2.3 | 品牌刚性商品、服装、包装食品、家具产生合理差异且无示例常量泄漏 | 固定输入/输出、字段来源与人工审阅记录 | 未通过则改槽位协议/Prompt，不写商品名分支 |
| V2.3.1 | 通用图片角色、模板和条件依赖注册表 | G2 | 对比、尺寸、食品等依赖有唯一规则消费者；支持 custom | 配置校验与改数据探针 | 无消费者字段禁止进入配置 |
| V2.3.2 | 可新增、复制、删除、排序的套图编辑器 | V2.3.1 | 任意 `1..N` Shot；必需/可选和顺序一致持久化 | Playwright、计划 diff、刷新恢复 | 操作事务失败不改变旧计划 |
| V2.3.3 | StyleSpec 与 ShotSpec 编辑、版本和失效传播 | V2.3.2 | 公共风格影响全套；单图修改只影响目标；审核清单可投影 | 版本/依赖测试、UI 后置条件 | 回退到上一版本，不覆盖历史 |
| V2.3.4 | Provider 感知 Prompt 编译器 | V2.3.3 | Prompt 来源可追溯；界面、记录与请求 hash 一致；语言策略明确 | golden、请求快照、混杂/冲突探针 | 编译失败保留旧版本并阻止生成 |
| V2.3.5 | 生成前确认与外发资料摘要 | V2.3.4 | 显示张数、任务、风险和发送资料；过期/缺依赖不能提交 | 浏览器正反路径 | 返回准确修改位置 |
| V2.3.6 | Prompt 人工编辑版本 | V2.3.5 | 可直接编辑全文并保存为新版本；旧版本保留；编辑后失效投影精确；界面文本与记录/快照 hash 一致 | 编辑正反路径、语言策略降级为提示、版本历史 | 编辑失败不改旧版本 |
| V2.4.1 | 无状态 qwen-image-3.0 submit/status/result gateway | G3 | 不读取/写入用户 workspace；响应保留 Provider 身份和错误语义 | API 契约、磁盘 diff、fake provider | 切回 fake provider，不伪造成功 |
| V2.4.2 | 浏览器 Attempt、action ID、task ID 与 Unknown 恢复 | V2.4.1 | 提交前持久化身份；已知 task 可跨服务重启核对；无 task 的 Unknown 不自动重试 | 重启/超时/重复点击轨迹 | 用户显式创建新 action |
| V2.4.3 | 整套批次执行和逐图进度 | V2.4.2 | 部分失败不丢成功；刷新恢复；失败 Shot 可单独重试 | fake 正常/partial/unknown E2E | 停止新增提交，保留已有结果 |
| V2.4.4 | 候选字节流、Blob 持久化与容量管理 | V2.4.3 | 下载即存 IndexedDB；hash、媒体信息和来源 Attempt 一致；容量不足可恢复 | Blob hash、配额异常、刷新预览 | 不提交选择；提示导出/清理 |
| V2.4.5 | 真实参考图最小闭环（一笔预算内的真实调用） | V2.4.4 | 真实 qwen-image 请求含真实参考图与真实 Prompt；候选非 Mock 并存为浏览器 Blob，task id 可追溯 | 真实请求审计 + 候选 hash + 状态轨迹 | 失败按分类保留证据、不循环重试；Unknown 只核对不重提 |
| V2.5.1 | 生成前、单图和导出的确定性验证器 | G4 | 每条硬规则有版本、消费者和可复现测量；审美不冒充硬门 | 单元/反向探针 | 未知规则降为提示或禁用 |
| V2.5.2 | 可替换 VLM ReviewProvider | V2.5.1 | 输出绑定 Candidate/ReviewContract；非法/超时保留 Unknown；不自动采纳；真实调用复用 SEL-003 的 langchain 通道，不新建 HTTP 客户端或适配器 | fake provider、已标样例、最小真实请求 | 允许人工审核继续，不伪造 PASS |
| V2.5.3 | 参考图、旧候选、新候选和审核清单比较界面 | V2.5.2 | 比较直接，异常优先，完整报告按需展开 | Playwright、视觉证据、键盘路径 | 回退单候选视图但保留数据 |
| V2.5.4 | 问题分类、改进方向和单图返工闭环 | V2.5.3 | 只目标 Shot 新建 Prompt/Attempt/Candidate/Review；完整返工来源可追溯；旧候选与无关确认、Attempt、Blob hash 不变；新候选不自动选择 | 领域反向探针、前后对象/hash diff、浏览器正常/失败/Unknown/刷新/双击轨迹 | 返工失败仍保留旧可用候选；比较区保持只读 |
| V2.6.1 | 人工 Selection 与失效判断 | V2.5.4 | 每个必需 Shot 最多一个 current 选择；新成功候选使目标旧选择 stale；用户可重新选择新或旧候选；自动审核不产生选择 | 状态机、选择/改选/取消/返工后重选浏览器路径 | 保留候选，选择写入失败不改旧 Selection |
| V2.UI.1 | 正式 HTTPS 入口、Chrome/Edge 支持矩阵与精确能力诊断 | V2.6.1 | 远程空白创建/刷新/关页恢复；HTTP/WebCrypto 与 IndexedDB 缺失不混报；不引入服务器项目状态或自研密码学降级 | localhost + 远程 HTTPS Chrome/Edge + HTTP 负例、console/network、IndexedDB 后置条件 | 恢复上一代理/容器；无 HTTPS 则保持未完成 |
| V2.UI.2 | 前端交互契约、六阶段信息架构与视觉基线 | V2.UI.1 | 首页、工作台和关键异常状态可走查；一个主操作、图片优先、工程信息渐进披露；产品发起人确认 | 1440/390/200% 代表状态截图、键盘与语义检查、产品发起人走查记录 | 未确认只改设计，不进入实现 |
| V2.UI.3 | 真实项目首页与同页工作台重构 | V2.UI.2 | 所有既有业务能力由真实状态驱动并可达；空/忙/错/Unknown、刷新与键盘路径成立；旧数据合同不变 | 新 UI E2E + V2.1.2 至 V2.6.1 相关浏览器回归 + IndexedDB 后置条件 | Git 回退 UI，保留数据和 V2.UI.1 入口修复 |
| V2.5.5 | 基于 SelectionSet 的整套风格、商品与覆盖一致性报告 | V2.UI.3 | 报告绑定 selection fingerprint、可重算；确定性与 VLM 权限分离；问题能定位到 Shot | 已知一致/漂移套图探针、选择变化失效、人工复核 | Unknown 交人工，不自动取消选择或拒绝整套 |
| V2.6.2 | 浏览器交付 ZIP 与硬门禁 | V2.5.5 | 全部必需选择 current、硬检查通过且 Unknown 已人工复核；ZIP 只含选定图、manifest、README、检查；重导不覆盖历史记录 | 正反门禁、解包、hash、manifest 反查 | 生成失败不产生完成 ExportRecord；返回精确问题 Shot |
| V2.6.3 | 项目 ZIP 迁移与 schema 升级闭环 | V2.6.2 | 完整历史跨浏览器恢复并可继续返工 | 双浏览器 round-trip | staging 导入、失败不 commit |
| V2.6.4 | 全链渐进披露、空/忙/错/Unknown、响应式与可访问性终验 | V2.6.3 | 在 V2.UI.3 基线上补齐交付阶段；390px、200% 缩放、键盘、焦点、错误恢复无阻塞 | Playwright、axe/人工走查、console/network | 不用说明文字掩盖模型错误，不回退成纵向工程表单 |
| V2.7.1 | Product V2 全回归与反向探针 | G6 | 两次连续全绿、指纹一致；每个关键守卫被证明能变红 | 汇总报告和原始日志 | 有漂移不进入真实验收 |
| V2.7.2 | 最小真实模型闭环 | V2.7.1 | DeepSeek、Qwen、VLM 各只做完成证据需要的最少调用；请求/结果可追溯 | 真实请求审计、task ID、候选与报告 | 失败保留证据，不循环烧钱 |
| V2.7.3 | 非内置商品与首次使用者走查 | V2.7.2 | 无命令行、JSON、口授完成全链；记录介入和失败点 | 录屏、观察表、项目/交付包 | 有介入则修复后换人重验 |
| V2.7.4 | C1–C17 完成审计与发布候选冻结 | V2.7.3 | 每项 proven；代码/配置/静态资源/证据无漂移；限制明确 | completion matrix、指纹、回退说明 | 任一 missing/indirect 则 Goal 不完成 |
| V2.7.5 | Product V1 日落批次 | V2.7.4 | V1 代码、入口、配置、验证器与失效依赖删除；正式入口只剩 V2；历史可由 git 恢复 | 删除清单、依赖重登、守卫与回归 | 任何 V2 缺口暴露时从 git 恢复，不半删 |

## 11. 完成证据矩阵

| ID | 必须成立的声明 | 通过线 |
|---|---|---|
| C1 | 浏览器从空白状态启动 | 无服务器 recent、绝对路径、预填商品或历史候选 |
| C2 | 浏览器项目可恢复 | 刷新、浏览器重开、服务器重启后业务对象和 Blob 恢复 |
| C3 | 浏览器之间自然分离 | 两个独立浏览器配置文件项目列表和 IndexedDB 不互相出现 |
| C4 | 项目可迁移 | 项目 ZIP 导出、清空、导入后对象与 Blob hash 一致 |
| C5 | 商品理解输入驱动 | 四类商品动态槽位和 Brief 有合理差异，无商品名/fixture 分支 |
| C6 | 人工控制事实 | 来源、置信、确认与异常可见；模型提议不能自动提交为事实 |
| C7 | 套图真正可编辑 | 可新增、复制、删除、排序 Shot；条件依赖能精确阻断无依据任务 |
| C8 | Prompt 可见、可改、真实发送 | UI、PromptVersion、请求快照文本 hash 一致；语言策略明确 |
| C9 | 真实参考图生成成立 | qwen 请求含真实参考图和 task ID；候选非 Mock 并存为浏览器 Blob |
| C10 | 执行可恢复 | 双击、部分失败、刷新、服务重启、Unknown 不丢成功、不静默重复提交 |
| C11 | 自动校验减负 | 每候选有当前报告；异常优先；VLM Unknown/误判不自动采纳或硬拒绝 |
| C12 | 单图返工隔离 | 旧候选保留；只目标 Shot 新增版本；无关 Attempt/Blob hash 不变 |
| C13 | 人工选择和导出可追溯 | 全部必需 Shot 恰一选择；ZIP manifest 可反查输入到候选 |
| C14 | 机制不绑定示例商品 | 非内置商品无需修改代码或夹具完成任务 |
| C15 | 陌生人可独立使用 | 无命令行、JSON、开发者口授完成完整任务；介入为零 |
| C16 | 正式远程入口真实可用 | 可信 HTTPS origin；当前稳定版桌面 Chrome/Edge 从空白创建、刷新、关页重开与服务重启后恢复；HTTP/WebCrypto 与 IndexedDB 缺失被准确区分 |
| C17 | 前端是可走查的成品界面 | 首页与六阶段同页工作台通过产品发起人走查；图片优先、唯一主操作、工程信息渐进披露；1440px、390px、200% 缩放与键盘路径成立 |

`proven` 必须有对象、条件、时点、来源、结果和限制。逻辑推演、文档完成、Mock、单次截图或模型自评分别只能证明其直接观察到的层次。

## 12. 验证策略与成本纪律

### 12.1 四层验证

1. **组件**：schema、纯函数、状态转换、规则、adapter。
2. **轨迹**：一个动作跨 IndexedDB、API、Provider、候选和报告的完整前后状态。
3. **系统**：真实浏览器的正常、拒绝、失败、Unknown、恢复、导入导出。
4. **产品**：不同商品、真实模型、首次使用者和最终交付包。

浏览器绿色必须同时检查：可见界面、console/network、IndexedDB/API 后置条件和生成/导出文件；只查 DOM 不足以证明业务闭环。

### 12.2 真实调用预算原则

- 开发和绝大多数回归使用 fake provider。
- 真实调用只用于 adapter 最小探针和最终完成证据。
- 每次真实调用前明确目的、预计请求数、已有证据缺口和停止条件。
- Unknown 有 task ID 时先核对；没有 task ID 时不自动重提。
- 真实模型效果不以“反复抽卡直到看起来不错”代替系统验证。

## 13. 迁移、回退与停止条件

### 13.1 迁移原则

- Product V1 代码、配置、证据和旧工作空间先保留、不自动迁移；V2.7.4 发布候选冻结后由 V2.7.5 专批删除（SEL-009），git 历史保留，V1 证据不删除。
- Product V2 使用独立前端资源、API 前缀、schema 和浏览器数据库名。
- 复用 Provider 与业务语义时通过接口提取，不让 V2 重新依赖 WorkspaceStore。
- V2 达到 G6 前，旧正式入口仍可用于回归和对照；V2 导航不能同时提供两条完成同一任务的主路径。

### 13.2 回退

- 每个切片由 feature flag 或独立入口隔离，失败时回退到上一切片。
- IndexedDB schema migration 先复制或 staging，成功后切换当前 schema。
- 导入和生成结果先验证 hash/结构，再 commit 项目状态。
- 不使用破坏性 git 命令回退用户已有修改。

### 13.3 停止并请求用户的条件

- 需要改变“浏览器持有状态、服务器无状态、主流程不抠图”的根边界。
- 需要新增付费 Provider、显著增加真实调用或扩大用户可见范围。
- 外部模型合同与已配置模型不兼容，且选择不同模型会改变用户体验或成本。
- 完成标准必须降级才能宣布完成。

实现细节、目录命名、测试工具和可逆的小范围默认值由开发者自行决定，不为这些事项反复向用户提问。

## 14. 控制面维护规则

- `docs/INDEX.md`：只管理文档身份和读取路由。
- `docs/product-v2-project-context.md`：只管理项目身份、运行边界、技术栈、目录和质量门槛。
- 本文件：只管理目标、需求、对象/状态、任务、依赖、Gate 和完成标准。
- `_working/amz-listing-kit-product-v2/state.md`：只管理进度、证据、阻塞、未知和唯一下一动作。
- `README.md`：只描述已实现行为和真实启动方式，不把本计划中的未来能力写成当前实现。
- `evals/product-v2/`：只保存时点证据，不发布当前计划或状态。

当新证据改变设计时，先找最早失效层：目标、契约、架构、任务、实现或验证。只改对应权威，并为可重复失败增加回归证据；不得复制到多份文档“保持同步”。
