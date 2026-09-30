# amz-listing-kit Product V2 Goal 与详细实施计划

> CONTROL-STATUS: current · AUTHORITY: product-goal-plan
> **版本：v3.0 · 2026-09-29**
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

### Phase 5：自动校验、比较与局部返工

目标：系统发现低级错误并把异常投影给用户，返工只影响目标 Shot。

**Gate G5：** 每个候选有当前 ReviewReport；参考/旧/新候选可直接比较；目标 Shot 返工后旧候选保留、无关 Blob 与 Attempt hash 不变；整套一致性报告可重算。

### Phase 6：选择、交付与可用性

目标：人工采纳形成唯一交付选择，浏览器生成交付包和完整项目包。

**Gate G6：** 缺选或硬检查失败时不能导出；交付 ZIP 可复检；完整项目包可跨浏览器恢复；390px、200% 缩放、键盘和失败反馈满足产品基线。

### Phase 7：跨品类、真实模型与首次使用者验收

目标：证明机制通用、主链真实、陌生人可独立完成，而不把 Mock 或单个商品当成产品完成。

**Gate G7：** C1–C15 全部 proven；至少一个非内置商品完成真实闭环；首次使用者无口授完成任务；代码、配置、静态资源与完成证据一致。

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
| V2.4.1 | 无状态 qwen-image-3.0 submit/status/result gateway | G3 | 不读取/写入用户 workspace；响应保留 Provider 身份和错误语义 | API 契约、磁盘 diff、fake provider | 切回 fake provider，不伪造成功 |
| V2.4.2 | 浏览器 Attempt、action ID、task ID 与 Unknown 恢复 | V2.4.1 | 提交前持久化身份；已知 task 可跨服务重启核对；无 task 的 Unknown 不自动重试 | 重启/超时/重复点击轨迹 | 用户显式创建新 action |
| V2.4.3 | 整套批次执行和逐图进度 | V2.4.2 | 部分失败不丢成功；刷新恢复；失败 Shot 可单独重试 | fake 正常/partial/unknown E2E | 停止新增提交，保留已有结果 |
| V2.4.4 | 候选字节流、Blob 持久化与容量管理 | V2.4.3 | 下载即存 IndexedDB；hash、媒体信息和来源 Attempt 一致；容量不足可恢复 | Blob hash、配额异常、刷新预览 | 不提交选择；提示导出/清理 |
| V2.5.1 | 生成前、单图和导出的确定性验证器 | G4 | 每条硬规则有版本、消费者和可复现测量；审美不冒充硬门 | 单元/反向探针 | 未知规则降为提示或禁用 |
| V2.5.2 | 可替换 VLM ReviewProvider | V2.5.1 | 输出绑定 Candidate/ReviewContract；非法/超时保留 Unknown；不自动采纳 | fake provider、已标样例、最小真实请求 | 允许人工审核继续，不伪造 PASS |
| V2.5.3 | 参考图、旧候选、新候选和审核清单比较界面 | V2.5.2 | 比较直接，异常优先，完整报告按需展开 | Playwright、视觉证据、键盘路径 | 回退单候选视图但保留数据 |
| V2.5.4 | 问题分类、改进方向和单图返工闭环 | V2.5.3 | 只目标 Shot 新建 Prompt/Attempt；旧候选保留；重新选择前不可导出 | 前后对象与 Blob hash diff | 返工失败仍保留旧可用候选 |
| V2.5.5 | 整套风格、商品与覆盖一致性报告 | V2.5.4 | 报告可重算并绑定整套版本；问题能定位到 Shot | 已知一致/漂移套图探针、人工复核 | Unknown 交人工，不自动拒绝整套 |
| V2.6.1 | 人工 Selection 与交付门禁 | G5 | 每个必需 Shot 恰一候选；过期、缺选、硬错误精确阻断 | 状态机、浏览器正反路径 | 保留选择，返回问题 Shot |
| V2.6.2 | 浏览器交付 ZIP | V2.6.1 | 只含选定图、manifest、README、检查；重导不覆盖历史记录 | 解包、hash、manifest 反查 | 生成失败不产生完成 ExportRecord |
| V2.6.3 | 项目 ZIP 迁移与 schema 升级闭环 | V2.6.2 | 完整历史跨浏览器恢复并可继续返工 | 双浏览器 round-trip | staging 导入、失败不 commit |
| V2.6.4 | 渐进披露、空/忙/错/Unknown、响应式与可访问性 | V2.6.3 | 390px、200% 缩放、键盘、焦点、错误恢复无阻塞 | Playwright、axe/人工走查、console/network | 不用说明文字掩盖模型错误 |
| V2.7.1 | Product V2 全回归与反向探针 | G6 | 两次连续全绿、指纹一致；每个关键守卫被证明能变红 | 汇总报告和原始日志 | 有漂移不进入真实验收 |
| V2.7.2 | 最小真实模型闭环 | V2.7.1 | DeepSeek、Qwen、VLM 各只做完成证据需要的最少调用；请求/结果可追溯 | 真实请求审计、task ID、候选与报告 | 失败保留证据，不循环烧钱 |
| V2.7.3 | 非内置商品与首次使用者走查 | V2.7.2 | 无命令行、JSON、口授完成全链；记录介入和失败点 | 录屏、观察表、项目/交付包 | 有介入则修复后换人重验 |
| V2.7.4 | C1–C15 完成审计与发布候选冻结 | V2.7.3 | 每项 proven；代码/配置/静态资源/证据无漂移；限制明确 | completion matrix、指纹、回退说明 | 任一 missing/indirect 则 Goal 不完成 |

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

- Product V1 代码、配置、证据和旧工作空间先保留，不删除、不自动迁移。
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
