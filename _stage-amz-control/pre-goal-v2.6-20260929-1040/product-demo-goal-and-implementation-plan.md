# amz-listing-kit Product V1 Goal 与详细实施计划

> CONTROL-STATUS: current · AUTHORITY: product-contract-and-task-graph  
> 本文件唯一管辖产品目标、完成合同、目标架构、阶段、Gate、任务定义与依赖；执行进度、证据和唯一下一动作只在 current state 维护。

版本：v2.5  
日期：2026-09-29  
状态：当前唯一权威产品合同与实施任务图；Goal 生命周期、执行进度和唯一下一动作只以 current state 为准

本次修订：产品发起人已认可 `out/product-workbench-concept-2026-09-29/` 所表达的任务模型与视觉方向，但该候选仍是本地模拟，不能直接冒充正式产品。本计划把它提升为正式前端的交互基线，新增 D4.4–D4.14 纵向迁移任务：正式入口必须从真实 Workspace 投影首页、资料、动态方案、一键整套生成、逐图审核、两阶段返工、高级 Prompt 与导出，不得在浏览器内硬编码商品、候选、进度或成功状态。原 D4.2 可用性证据只保留为旧正式界面的历史基线，新界面必须在 D4.12 重新验收；陌生人走查和完成审计顺延至 D4.13/D4.14。未改变 Goal、C1–C13 或真实模型/人工验收门槛。

---

## 0. 一页结论

`amz-listing-kit` 要做成的不是 Aster 保温杯演示、固定七图流水线或 Prompt 编辑器，而是一个 Windows 本地、单人使用的商品套图工作台：

```text
新建或打开商品工作空间
  → 导入商品参考图、介绍、卖点与目标平台
  → 系统理解商品并提出 1..N 张动态套图方案
  → 用户可直接采用默认方案，也可调整图型、方向和完整 Prompt
  → 一键调用真实图片模型生成整套候选
  → 比较、选择、修改 Prompt 或只返工目标图片
  → 导出最终图片与可追溯 manifest
```

设计借鉴三份可运行参考 Skill 的机制，但不把它们的品类、张数、平台示例或批处理参数升级成本产品规则；参考项目跑通也不等于本 Goal 已完成。

| 参考范例 | 实际链路：输入 → 处理 → 输出 | 迁移到本产品 | 不照搬 |
|---|---|---|---|
| `ecommerce-image-suite` | 商品图与可选卖点 → 视觉分析形成商品结构化资料、由人修正，再按平台/图型生成逐图 Prompt 并调用图像 API → 图片、结果或错误记录 | 商品输入先落为可追溯 ProductBrief；用户确认事实；按 Shot 单独生成和保留结果 | 服装导向的输入引导、固定图型列表、只凭 Key 长度判断供应商可用；Skill 内的图片数量约束不替代本 Goal §2 |
| `ecom-details-image` | 视觉需求、用途、主体、风格、平台与可选参考图 → 匹配任务模板；只追问影响结果的缺项；多图共享 Campaign Style Lock，再编译逐图 Prompt → Prompt 或生成图片 | Archetype 作为任务语法；整套共享视觉方向与逐图差异分开；完整 Prompt 可查看、编辑和追溯 | 25 个模板不等于品类知识库；Amazon `5+7–9` 是示例而非本产品张数；GPT-Image-2 专属写法不当作 Qwen 或所有商品的硬规则；单次脚本不是本产品的持久工作空间 |
| `ecommerce-skills` 的 `batch-image` | SKU CSV、图片、描述和共享 Prompt 规范 → Provider 脚本处理变量、并发、成本、重试与续跑 → 分 SKU 图片、批次 manifest、文件检查报告 | Provider 适配、共享规范/商品变量分离、单 Shot Attempt、可恢复状态、manifest 与确定性文件检查 | CSV/多 SKU、最多 100 项、积分、并发数和抽样比例属于批处理策略；超时不能盲目重提，UNKNOWN 必须先按原任务身份核对 |

因此，本产品是“一个商品工作空间里，计划驱动的多种图片任务”：Brief/Plan/共享风格是整套上下文，每个 Shot 独立持有 Prompt、Attempt、Candidate 和选择结果；用户按整组目的审阅、按单图修改与返工。Skill 提供的是机制参考，不是固定商品答案或当前产品完成证据。

本轮不再安排模型能力实验。默认相信已选模型能够完成其声明能力；开发任务是把调用组织成可使用、可恢复、可更换模型的产品。模型输出仍是候选，最终采用权属于使用者。

旧 v1.22 及 D2.R1g 的第三版前端候选保留为历史证据，其中可复用布局、状态与异常轨迹可以迁移；固定夹具驱动的 ProductBrief、Plan 和 Prompt 不进入正式实现。旧计划快照位于：

`_stage-amz-control/product-v2-plan-20260928/docs__product-demo-goal-and-implementation-plan.md`

---

## 1. 当前事实基线与校准结论

### 1.1 已经存在且可以复用

| 资产 | 当前能证明什么 | 在新产品中的去向 |
|---|---|---|
| `demo/provider/dashscope_i2i.py` | 既有真实参考图请求、异步任务与 Unknown 核对实现/轨迹，可作为迁移源；不是正式 Product V1 入口 | D2.1 按正式 Provider 合同迁移，D2.5 仍需新鲜真实任务证据 |
| `demo/core/front_chain.py` 与合同测试 | Prompt、参考图、预算、动作身份和候选绑定可实现 | 提炼为正式 service，不直接把 demo 包接到 UI |
| `app/server.py`、旧 Mock service | 单页服务、正常/失败/Unknown/局部返工轨迹可复用 | 保留服务入口和状态测试，替换夹具业务逻辑 |
| `evals/product-demo/d2-r1g/` | 阶段式、图片优先的前端候选与反向探针 | 作为视觉和交互输入，不是正式 ProductBrief 编译器 |
| v2 导出、文件检查、版本不覆盖机制 | 本地文件处理与清单已有工程经验 | 选择性迁移到新 Workspace/Export 服务 |
| `src/`、`app/product_v1_server.py` 与 D0–D3 新鲜证据 | 正式 Workspace、动态 Brief/Plan/Prompt、真实 Provider、版本化候选/选择/返工/导出链已经存在 | 作为新前端唯一业务事实源；只补一键整套编排和缺失的 UI 投影，不在浏览器重建业务状态机 |
| `out/product-workbench-concept-2026-09-29/` | 已获认可的首页、资料页、可选方案页、图片优先审核台和精简交互层级 | 仅作为 D4.4 交互与视觉基线；迁移布局、信息优先级和动作语义，不迁移硬编码商品、历史图片或本地模拟状态 |

### 1.2 当前不能声称

- 已实现的正式后端链和旧正式页面不能证明新的产品交互已经完成；正式 UI 仍把过多内部阶段暴露给用户，尚未按获认可基线收敛。
- `out/product-workbench-concept-2026-09-29/` 只证明任务模型和视觉候选可操作；其中商品、候选、生成进度和导出均为本地模拟，不能证明真实 Workspace、Provider 或恢复链。
- D4.2 的浏览器证据针对替换前页面；关键 UI 变更后必须重跑，不得继承为最终版本可用性证据。
- 真实语义 Provider 当前受账户欠费影响；在恢复前可以完成 fake-provider 纵向开发，但不能用 fake、历史候选或本地素材补足 C3–C6/C11 的新鲜真实证据。
- D4.4–D4.12 完成前不能开始陌生人最终走查；D4.14 前不能冻结发布候选或完成 Goal。

### 1.3 本次废止的开发假设

1. 废止“先验证模型能力，再决定是否建设产品”；模型能力作为可替换外部依赖处理。
2. 废止“固定七张/八张才是一套图”；套图为由商品、卖点、平台和用户意图决定的 `1..N` 个 Shot。
3. 废止“穷举所有品类模板”；预置通用图片任务语法，具体品类内容由语义模型动态编译。
4. 废止“Mock 产品完成后再接真实后端”；每个阶段交付真实纵向能力，Mock 只用于错误与恢复测试。
5. 废止“F1–F8 是普通用户工作流”；用户负责最终采用，自动验证在 V1 只做可靠的文件/平台硬规则。
6. 废止“前端是内部对象展示器”；界面只投影用户任务、可操作对象、状态和下一步。

---

## 2. 系统 Goal objective

以下文本是当前系统 Goal objective 的规范文本。Goal 的实时状态与 ID 由系统 Goal 和 `_working/amz-listing-kit-product-demo/state.md` 管辖；本计划不另行声明 Goal 是否 active。

> 将 `amz-listing-kit` 建成一个陌生使用者能够独立使用的 Windows 本地商品套图生产产品：使用者从空白状态新建或打开一个商品工作空间，导入 1–3 张商品参考图，填写或补充商品介绍、真实卖点并选择 Amazon US；系统通过可替换的语义模型把输入编译成可查看、可修改的 ProductBrief、动态 `1..N` 张套图方案和每张实际发送给图片模型的完整 Prompt，默认无需使用者编写 Prompt；使用者可一键调用阿里云百炼 `qwen-image-3.0` 真实参考商品图生成整套候选，查看逐图进度和失败/Unknown，比较并保留历史候选，编辑某张 Prompt 或填写返工方向后只重新生成该张，逐图选定最终结果，并导出图片组及包含输入、方案、Prompt、模型、候选和选择关系的 manifest。  
>  
> 完成必须由新鲜证据证明：正式入口从空白启动；工作空间关闭并重开后资料、计划、任务、候选和选择均恢复；至少两个结构明显不同的商品得到不同且可解释的 ProductBrief、套图数量或 Shot 组合以及商品 Prompt 块，其中至少一个商品不是内置夹具；至少一个完整任务使用真实参考图请求生成并由人选定全部交付图片；Prompt 编辑产生新版本且只使目标 Shot 失效；单图返工保留旧候选且无关 Shot 的 Attempt 和文件哈希不变；局部失败不丢失成功结果，Unknown 先按原 provider task id 核对而不重复提交；导出文件通过 Amazon US 的确定性文件规则并能由 manifest 追溯；一名首次接触最终版本的人不使用命令行、JSON 或开发者口授，完成新建、生成方案、一键出图、一次单图返工、选择和导出。  
>  
> V1 默认语义模型和图片模型通过 Provider 接口配置，正式图片默认使用 `qwen-image-3.0`，但业务对象、工作空间和状态机不得绑定某一模型；模型选择界面、其他平台、批量 SKU、多用户权限、云部署、自动发布、销售效果证明、自动语义质检、穷举品类模板和像素级复杂排版不属于本 Goal。缺少真实模型凭据、真实参考图请求或人工最终选择时，不得用 Mock、历史候选、本地贴图或降低完成标准宣布完成。

---

## 3. 产品合同

### 3.1 使用者、任务与完成定义

- **使用者**：需要为单个商品准备 Amazon Listing 图片、但不擅长复杂提示词的运营或内容人员。
- **起点**：一个空白工作空间，或一个已经存在的商品工作空间文件夹。
- **输入**：当前 Goal 为 V1 约定 1–3 张同一商品参考图与商品名称；商品介绍、用户提供的真实卖点和“本次重点”均可选。只有参考图与商品名称是创建任务的最小硬输入；可选资料缺失不阻塞，模型不得把推断补成确定卖点。
- **平台呈现**：V1 只有 Amazon US 一个受支持 Profile。工作空间始终保存 Profile 身份/版本，界面明确显示“Amazon US”；不做只有一个选项的下拉框。“选择 Amazon US”在 V1 表示确认本任务适用于该目标，不代表界面必须提供平台选择器。1–3 张是当前 Goal 的 V1 范围，不是品类普遍规律，也不从参考 Skill 推导成永久上限。
- **任务**：得到一套与当前商品和交付目的匹配、可逐图选择和局部返工的图片。
- **完成**：计划内每个必需 Shot 都有一个人工选定候选，最终文件通过确定性导出检查并生成 manifest。

### 3.2 使用者必须决定什么

| 决定 | 为什么不能完全代替用户 | 系统怎样减负 |
|---|---|---|
| 参考图是否属于当前同一商品/变体、输入描述是否准确 | 这是生成目标与素材来源的业务事实 | 上传到某商品工作空间即默认声明为该商品素材，不逐张增加确认；仅当资料/图像明显冲突或含多个商品且影响方案时，内联询问标记为主商品、变体参考或排除 |
| 商品卖点是否真实 | 模型不能凭图片证明功能、材质、认证和宣传承诺 | 用户输入的卖点标为“用户提供”；模型推断标为“待核对”，不能自动变成图片文案 |
| 任务是否面向 Amazon US | V1 只有这一个受支持平台 | 清晰显示固定 Profile 和规则摘要；不提供假选择器，目标不符时明确告知当前不支持 |
| 是否调整默认套图方案 | 运营可能有本次活动或店铺意图 | 给出可直接执行的默认方案，只暴露必要调整项 |
| 哪张图可交付、哪里不满意 | 审美与业务接受权属于人 | 提供候选比较、快捷原因、自由描述与定向返工 |

不要求使用者选择品类编码、写完整 Prompt 或制定验证规则；“本次重点”是可留空的简短输入。只在资料缺失会实质改变图像目标、事实表达或平台合规时询问；其他情况使用有来源标签的默认方案。模型、尺寸、seed、Provider 参数默认隐藏在高级设置；只有存在多个可用模型或排障需要时才展示。

### 3.3 必须、可以、禁止

**必须：**

- 从空白创建、从文件夹打开、最近工作空间继续；
- 原始输入永不覆盖，所有 Brief/Plan/Prompt/Candidate/Export 版本可追溯；
- 商品理解、计划、Shot 和 Prompt 都由当前输入动态产生，不按商品名选择固定答案；
- 用户看到的完整 Prompt 与发送给 ImageProvider 的文本一致；
- 批量生成允许部分成功，成功候选不得因另一张失败而丢失；
- 返工只创建目标 Shot 的新版本，旧候选和未受影响 Shot 保持不变；
- 重启后能够继续，Unknown 必须先核对原外部任务；
- 导出只使用已选候选，并带机器清单和人读摘要。

**可以：**

- 使用系统建议的品类、卖点、场景、Style Lock 和套图计划；
- 修改 ProductBrief、添加/删除/排序可选 Shot、调整视觉方向；
- 查看、编辑、恢复系统推荐 Prompt；
- 为同一 Shot 生成多个候选并比较；
- 在高级设置中改模型配置，但 V1 不要求提供主流程模型选择器。

**禁止：**

- 用 Aster/Bex、商品名或 fixture id 分支生成正式 Brief/Plan/Prompt；
- 把固定七图、固定四图或某个品类配方当成所有商品的答案；
- 用 Mock 图片、历史图片或本地贴图标成真实模型的新生成结果；
- 自动覆盖原图、旧 Prompt、旧候选或旧导出包；
- 把模型自评、自动分割或综合分数当作人工最终采用；
- 在 UNKNOWN、缺凭据、缺参考图或预算拒绝后静默重提请求；
- 为了兼容旧实现，把内部 F1–F8、Attempt 或责任矩阵常驻展示给普通用户。

### 3.4 完成证据矩阵

| ID | 必须成立的声明 | 权威证据 | 通过线 |
|---|---|---|---|
| C1 | 产品从空白启动 | 全新工作目录录屏/E2E | 无预填商品、可新建和打开工作空间 |
| C2 | 工作空间是可恢复权威 | 关闭/重启/重开轨迹与文件哈希 | 输入、Plan、Prompt、Attempt、Candidate、Selection 全恢复 |
| C3 | 商品理解由输入驱动 | 两商品 Brief 差异与字段来源 | 无 fixture 常量泄漏；差异能追到输入 |
| C4 | 套图计划动态产生 | 两商品 Plan/Shot 对照 | 至少一项数量或 Shot 类型不同且理由可解释 |
| C5 | Prompt 可见、可改、真实发送 | PromptVersion、请求快照、hash/diff | UI 文本与请求文本一致；编辑创建新版本 |
| C6 | 真实参考图生成成立 | provider 请求快照、task id、下载文件 | 请求含参考图；非 Mock；至少一个完整任务产出候选 |
| C7 | 执行状态可靠 | 正常、部分失败、UNKNOWN、重启轨迹 | 不丢成功、不重复提交、可核对恢复 |
| C8 | 单图返工隔离 | 返工前后 Attempt/文件哈希 | 只目标 Shot 新增版本；旧候选保留 |
| C9 | 人工选择是提交权威 | SelectionVersion 与页面操作记录 | 每个必需 Shot 恰好一个最终候选 |
| C10 | 导出可交付、可追溯 | export manifest 与复检报告 | 文件规则通过；manifest 可反查输入至结果 |
| C11 | 机制不绑定示例商品 | 至少一个非内置商品完整任务 | 无代码/夹具修改即可完成 |
| C12 | 陌生人可使用 | 最终版本首次使用者走查 | 无命令行、JSON、开发者口授完成完整任务 |
| C13 | 工程入口可安装和回归 | 干净环境启动与全套验证报告 | 两次连续通过；无隐藏绝对路径和开发机状态 |

所有 C1–C13 均为 `proven` 才能完成 Goal。文档完成、原型可点、Mock E2E、单次真实出图或模型自评都不能单独代替产品完成。

---

## 4. 稳定机制与动态生成边界

### 4.1 系统提前设计什么

| 稳定机制 | 内容 |
|---|---|
| Workspace 契约 | 目录、身份、版本、不可覆盖、原子写入、恢复和导出格式 |
| PlatformProfile | Amazon US 主图/副图的文件硬规则、语言、比例和角色要求；每条硬规则保留官方来源、规则版本与核对时间 |
| Shot Archetype | 少量通用注册模式 + `custom` 回退；按通用 ShotSpec/Prompt 规则编译，不是封闭品类表，也不固定张数 |
| Prompt Grammar | 商品保真块、共享风格块、单图任务块、平台块、负面约束块 |
| Provider Contract | 语义模型与图片模型的输入、输出、能力、状态、错误和核对接口 |
| Version/Dependency | 哪些输入变化使 Brief、Plan、Prompt 或 Candidate 失效 |
| State Machine | 合法操作、部分失败、Unknown、重启和单图返工规则 |
| Export Contract | 被选文件、命名、尺寸检查、来源链和 manifest |

### 4.2 系统动态生成什么

- 商品品类、结构、颜色、材质表观和可见识别特征；
- 用户声明的卖点与模型推断信息之间的来源区分；
- 哪些特征必须保持、哪些画面元素允许改变；
- 套图张数、Shot 组合、顺序、每张目的和推荐理由；
- 共享视觉方向和各 Shot 场景、镜位、构图、光线；
- 每张结构化 Prompt 块与最终完整 Prompt；
- 根据返工原因提出“保持什么、改变什么”的新版本草案。

### 4.3 默认不是魔法

界面默认只让使用者完成任务，但设计机制必须可追溯：

```text
原始输入
  → ProductBrief（字段带 source/confidence/user_override）
  → PlanVersion（每个 Shot 带 purpose/reason/dependencies）
  → PromptVersion（完整文本 + 结构化块 + parent/diff）
  → GenerationAttempt（provider/model/request/task_id/status）
  → Candidate（文件/hash/来源版本）
  → SelectionVersion
  → ExportVersion
```

普通用户看到摘要和下一步；高级抽屉可以查看全部机制。隐藏复杂度不等于删除解释链。

### 4.4 端到端阶段：输入、处理、输出与用户决定

| 阶段 | 输入 | 系统处理 | 持久化输出 | 用户决定与失败边界 |
|---|---|---|---|---|
| 新建/打开工作空间 | 空目录或已有工作空间目录 | 初始化空索引，或校验身份、版本、引用并恢复当前投影 | `workspace.json` 与已验证的工作空间视图 | 损坏或不一致时只报告具体文件/引用，不覆盖修复、不载入示例商品 |
| 商品资料 | 1–3 张原图、商品名称、可选介绍/卖点/本次重点 | 校验文件并保存原始字节与 SHA-256；明确区分用户声明与缺失资料 | 不可覆盖的 SourceAsset、版本化 ProductInput | 素材加入该商品工作空间即默认归属；只有明显冲突或多商品歧义才显示内联裁定；可选字段可留空 |
| 商品理解与方案编译 | ProductInput、固定 Amazon US Profile、通用 Archetype 规则 | SemanticProvider 提出 Brief/Plan/Prompt 草案；代码验证来源、必需 Shot、引用和格式；PromptCompiler 编译完整逐图文本 | 带来源/状态的 ProductBrief、PlanVersion、ShotSpec、PromptVersion | 使用者纠正影响身份或宣传的关键事实，或直接接受默认方案；未确认推断不能成为卖点文案。低影响未知可标注/略过；影响方向的歧义才追问 |
| 整套生成 | 已接受的 Plan/Prompt、商品参考图、Provider 配置 | 对每个 READY Shot 建独立 action；提交、查状态、下载并校验结果 | 每图 GenerationAttempt 与 Candidate | 用户用一次主动作启动整套；局部失败保留成功图；`UNKNOWN` 用原 task id 核对，不自动重复提交 |
| 审核与单图返工 | 每张候选、当前 Prompt/Shot 和用户意见 | 用户选择候选；或把返工方向转换成“保持/改变”草案，仅重跑目标 Shot | 新 SelectionVersion，或目标 Shot 的 PromptVersion/Attempt/Candidate | 返工前展示变化范围并由用户确认；旧候选和无关 Shot 历史不覆盖 |
| 导出 | 所有必需 Shot 的用户选择、PlatformProfile 版本 | 确定性检查文件、规则和 hash，生成图片组及来源链 | 不可覆盖的 ExportVersion、manifest 与人读摘要 | 缺选图或硬规则失败则拒绝标记为完成；保留选择和候选供修正 |

### 4.5 决策权、默认值与不可变边界

| 内容 | 权威/默认 | 可否修改 | 规则 |
|---|---|---|---|
| 原始图片与用户输入 | 用户提供的原始内容及其 hash | 原件不可改；修改产生新的 ProductInput/Asset 版本 | 不覆盖原素材；保留来源和修改链 |
| 商品事实 | 用户提供的商品名称/描述/卖点是用户声明；模型识别的品类、外观和属性是带来源的推断 | 用户可纠正并生成新 Brief 版本 | 模型推断不能静默升级为已确认功能、材质、尺寸、认证或营销承诺；需要写入图中文字/卖点的内容必须有用户来源或确认 |
| 商品身份保护 | 默认保留参考商品及用户确认特征 | 可编辑“必须保持/允许变化”清单；变更以新版本保存 | 场景和风格变化不能悄悄改写已确认的商品身份；身份不确定且影响生成时先询问 |
| 套图计划与 Prompt | 系统给出的可执行默认提案 | 用户可调整 Shot、顺序、共享风格、返工方向和完整 Prompt；无需手写 | 修改创建版本；只使依赖它的下游对象 stale，不改历史 Attempt/Candidate |
| 平台硬规则与文件规则 | V1 的版本化 Amazon US Profile 和确定性检查 | 主流程不可绕过；未来 Profile 增加后再开放选择 | 规则失败阻止对应导出，不把语义/审美判断伪装为硬检查 |
| 模型调用、候选和最终采用 | Provider 回执/查询结果是外部执行证据；候选本身不是完成 | 历史不可覆盖；最终采用由用户决定 | `UNKNOWN` 先核对；每张图可独立成功/失败/返工，只有人工 Selection 进入导出 |

Archetype Registry 是少量可复用任务模式，不是品类表或全部图型答案。D0.1 为注册表加入 `custom` 通用回退；遇到食品纹理、家具尺寸展示等当前模式不合适的任务时，SemanticProvider 可产出 `custom` Shot，但仍必须符合统一 ShotSpec、来源、Prompt 和平台校验。产品特定内容随工作空间保存，不自动扩成全局模板；平台 Profile 的硬性必需类型仍必须满足。

---

## 5. 权威对象与工作空间格式

### 5.1 领域对象

| 对象 | 稳定身份 | 权威内容 |
|---|---|---|
| Workspace | `workspace_id` | 商品任务、当前指针、创建/更新时间和应用版本 |
| SourceAsset | 内容 SHA-256 | 原始图片、角色、来源和授权声明 |
| ProductInput | 版本 hash | 用户填写的名称、介绍、卖点、平台和本次意图 |
| ProductBrief | 版本 hash | 结构化商品理解、字段来源、不可变/可变边界 |
| PlatformProfile | `profile_id@version` | 平台规则、默认角色、官方来源 URI、规则来源版本与核对时间 |
| PlanVersion | 内容 hash | Style Lock、Shot 顺序、目的、理由和依赖 |
| ShotSpec | `shot_id + version` | 单图任务、允许变化、参考图角色和检查要求 |
| PromptVersion | 内容 hash | 结构化块、完整发送文本、父版本和 diff |
| GenerationAttempt | `action_id` | 一次外部调用、请求 hash、provider task id 和状态 |
| Candidate | 文件 SHA-256 | 不可覆盖图片及其全部上游版本 |
| SelectionVersion | 内容 hash | 每个 Shot 当前人工选择及变更历史 |
| ExportVersion | 内容 hash | 最终文件、检查结果、manifest 和生成时间 |

### 5.2 工作空间目录

```text
<workspace>/
  workspace.json                 # 当前指针与摘要；原子替换
  inputs/
    originals/                   # 原始文件，只增不改
    product-input-v001.json
  briefs/
    brief-v001.json
  plans/
    plan-v001.json
  shots/
    <shot_id>/
      spec-v001.json
      prompts/
        prompt-v001.json
      attempts/
        <action_id>.json
      candidates/
        <candidate_id>.png
        <candidate_id>.json
      review.jsonl
  selections/
    selection-v001.json
  exports/
    export-v001/
      images/
      manifest.json
      README.md
  logs/
    app.jsonl
```

约束：原始输入、版本文件、候选和导出包不可覆盖；当前指针可用“临时文件 + flush + 原子 replace”更新；单进程持有工作空间锁。V1 不引入 SQLite 作为业务权威，避免文件夹工作空间与数据库形成两个状态源；最近工作空间列表可以保存在应用级偏好文件中，不拥有业务状态。

---

## 6. 状态模型与动作合同

### 6.1 Workspace 状态

```text
NEW
  → INTAKE_READY
  → COMPILING
  → PLAN_READY
  → GENERATING
      ├─ 全部结束 → REVIEW_READY
      ├─ 局部失败 → REVIEW_READY_WITH_GAPS
      └─ 有未知   → RECONCILE_REQUIRED
  → REVIEWING
  → EXPORT_READY
  → EXPORTED
```

Workspace 状态是 Shot 状态的派生摘要，不单独制造第二套真相。

### 6.2 Shot 状态

```text
DRAFT → READY → QUEUED → RUNNING
                     ├─ SUCCEEDED → REVIEWABLE → SELECTED
                     ├─ FAILED    → RETRYABLE / NEEDS_INPUT
                     └─ UNKNOWN   → RECONCILING → 终态

编辑 Shot/Prompt：已有 Candidate 不变，当前 Shot → STALE/READY
返工：新增 PromptVersion/Attempt/Candidate，不覆盖历史
```

### 6.3 核心动作

| 动作 | 前置条件 | 状态变化与输出 | 失败/Unknown |
|---|---|---|---|
| `create_workspace` | 可写目录 | 空 Workspace | 路径不可写则不创建半成品 |
| `save_intake` | 至少名称 + 1 张参考图 | ProductInput 新版本 | 图片格式/同一商品由用户处理或明确拒绝 |
| `compile_plan` | Intake 完整、SemanticProvider 可用 | ProductBrief + PlanDraft + PromptDraft | 模型/解析失败保留输入，允许重试或手工补 Brief |
| `save_plan` | Plan 校验通过 | PlanVersion + ShotSpec/PromptVersion | 无依据卖点、缺必需主图时指出具体 Shot |
| `run_batch` | 至少一个 READY Shot、ImageProvider/key 可用 | 每 Shot 独立 Attempt | 局部失败不回滚成功；Unknown 不重提 |
| `reconcile_attempt` | 有 provider task id 的 UNKNOWN | 用原任务查询并转终态 | 仍未知则保持 UNKNOWN |
| `save_prompt` | 完整文本有效 | 新 PromptVersion，目标 Shot STALE | 不丢编辑文本；冲突指出对应商品事实 |
| `preview_rework` | 用户给出方向/快捷原因，目标 Shot 有可用候选 | 绑定当前 Shot/Prompt 版本的返工草案与保持/改变预览 | 不调用 ImageProvider；若输入版本已变化，草案失效并须重新预览 |
| `confirm_rework` | 用户明确确认当前返工草案；草案仍绑定最新 Shot/Prompt 版本 | 创建新 PromptVersion 与唯一 action_id/Attempt，仅提交目标 Shot | 双击使用同一 idempotency key；草案过期拒绝提交；UNKNOWN 先核对原 provider task id，不创建新提交 |
| `select_candidate` | Candidate 可读 | SelectionVersion | 不删除其他候选 |
| `export_set` | 所有必需 Shot 已选 | ExportVersion | 最终检查失败则不发布该版本 |

---

## 7. 目标架构

```text
Browser UI
  ↓ HTTP/JSON
Application Service
  ├─ WorkspaceStore（唯一业务状态）
  ├─ ProductCompiler
  │    ├─ SemanticProvider
  │    ├─ ShotArchetype Registry
  │    ├─ PlatformProfile Registry
  │    └─ PromptCompiler
  ├─ GenerationService
  │    ├─ ImageProvider Registry
  │    ├─ Attempt/Unknown/Reconcile
  │    └─ Candidate Store
  ├─ ReviewService
  └─ ExportService + Deterministic Checks
```

### 7.1 Provider 接口

```python
class SemanticProvider:
    analyze_product(product_input, source_assets) -> ProductBriefDraft
    propose_plan(product_brief, platform_profile, archetypes, user_intent) -> PlanDraft
    propose_prompt_blocks(product_brief, shot_spec, style_spec) -> PromptBlocks

class ImageProvider:
    capabilities() -> ProviderCapabilities
    submit(action_id, references, prompt, params) -> Submitted | Rejected | Unknown
    query(provider_task_id) -> Running | Succeeded | Failed | Unknown
    download(provider_task_id, target_path) -> CandidateArtifact

class ReviewProvider:  # V1 可选，不是完成依赖
    inspect(reference_assets, candidate, review_contract) -> ReviewProposal
```

V1 图片默认使用 DashScope `qwen-image-3.0`；语义能力默认使用 DashScope OpenAI-compatible Chat Completions 的 `qwen3.7-plus`，配置 id 为 `dashscope-qwen-semantic`。选它是因为 SemanticProvider 必须看商品参考图，同时生成商品理解、套图方案和提示词草案；不进行模型横向评测，也不建设模型选择器。商品图分析使用 JSON Object 响应模式并由本地 JSON Schema 严格校验；纯文本 Plan/Prompt 使用 JSON Schema strict 模式并再次本地校验。Provider/model 只出现在配置、语义响应诊断和高级排障信息中；业务对象不引用供应商专属字段。

凭据从 `DASHSCOPE_API_KEY` 读取；端点默认沿用本项目既有的 `https://dashscope.aliyuncs.com/compatible-mode/v1`，如百炼账号要求地域/业务空间专属端点，可用 `DASHSCOPE_COMPATIBLE_BASE_URL` 覆盖，且必须与 API Key 的地域匹配。缺少 Key 或配置无效时必须明确阻止，不提供假结果。选择依据与实现验证见 `evals/product-demo/d1.1-semantic-provider-2026-09-28.md`；百炼官方 Chat Completions、结构化输出及模型文档是运行协议来源。

### 7.2 ProductCompiler

ProductCompiler 采用“模型提案 + 确定性编译”而不是自由文本直通：

1. SemanticProvider 输出符合 schema 的 ProductBriefDraft、PlanDraft 和 PromptBlocks；商品属性标注 `confirmed/inferred/unknown/conflicted` 及来源引用；
2. 只有用户输入/确认的卖点能作为肯定的营销主张；未确认推断可以显示为待核对的视觉判断，不可写成商品功能或卖点文案；身份相关的关键冲突在生成前请求用户裁定；
3. Shot Archetype 使用注册任务模式或 `custom`；`custom` 不新增产品类别数据库，仍由通用 ShotSpec 与 `shot_task` PromptBlock 承载；
4. 确定性代码校验字段、来源、Shot 身份、平台必需项和引用关系；
5. PromptCompiler 按固定顺序拼接：

```text
Product Fidelity Block
+ Campaign Style Lock
+ Shot Purpose/Scene/Composition Block
+ Platform/Output Block
+ Negative Constraints
```

6. 最终文本和结构化块一起保存；用户编辑全文时保留父版本和 diff；Brief/Plan/Prompt 更新只影响其依赖下游的当前版本；
7. 更换模型只更换 Provider/参数，不重写 ProductBrief、Plan 或 Workspace 状态机。

### 7.3 V1 确定性检查

只自动裁决可靠项目：文件存在且可解码、像素尺寸、比例、格式、色彩模式、体积，以及 Amazon 主图可确定的白底/透明通道等。商品是否完全一致、画面是否美观、卖点是否可信由人选择；ReviewProvider 的意见只能作为建议。

---

## 8. 前端交互合同

### 8.1 Screen Map

```text
S0 工作空间首页
  ├─ 新建商品工作空间 → S1
  ├─ 打开工作空间     → 恢复到 S1/S2/S3/S4
  └─ 最近工作空间     → 同上

S1 商品资料
  ├─ 生成整套图片 → 自动编译默认方案 → S3
  └─ 先看方案     → S2

S2 套图方案（可选）
  └─ 按此方案生成 → S3

S3 生成与审核
  ├─ 准备方案 / 逐图生成 / 失败或 Unknown 恢复
  ├─ 比较候选 / 采用此图
  ├─ 高级 Prompt / 只重做这张 → S3
  └─ 全部必需图已选择且硬检查通过 → S4

S4 导出
  └─ 导出套图 / 打开文件夹
```

任何时刻只有一个主任务区。已完成阶段折叠为摘要；未来阶段不提前显示空面板。阶段标识用于定位当前任务，不得成为要求用户逐步理解内部流水线的向导。默认主路径不打开 ProductBrief、Plan 或 Prompt 编辑器；它们必须存在且可追溯，但只在用户要核对或调整时展开。

### 8.2 视图与按钮

| 屏幕 | 主要视图 | 必要按钮 | 存在理由 |
|---|---|---|---|
| S0 | 产品价值一句话、最近工作空间、真实空态 | `新建商品套图`、`打开工作空间`、最近工作空间卡 | 让首次使用者知道从哪里开始，让已有用户直接恢复；正式页不预填示例商品，最近项只来自本机真实索引 |
| S1 | 参考图上传区、商品名、可选卖点/创作要求、固定 Amazon US 标签 | 主按钮 `生成整套图片`；次按钮 `先看方案`；仅素材冲突时出现“主商品/变体参考/排除” | 必填项只保留名称和至少一张参考图；保存是动作内部的持久化步骤，不额外制造“先保存才能继续”；V1 不展示英国、日本或模型选择等假入口 |
| S2 | 精简商品理解摘要、动态 Shot 卡、共享视觉方向 | `纠正商品资料`、添加/移除/排序可选 Shot、自然语言增加 `custom` Shot、`按此方案生成`；完整 Prompt 位于单 Shot 高级入口 | 默认方案不经编辑即可执行；用户只处理影响商品身份、宣传事实或套图目的的内容，不需要先理解 Prompt |
| S3 生成态 | 当前任务名称、整套进度、逐图缩略状态 | 正常生成无额外主按钮；局部失败显示 `重试这张`；仅 Unknown 显示 `核对状态`；账户/配置错误显示可执行修复 | 成功图随到随看且不因其他图失败而丢失；刷新和重启从 Workspace 恢复，不重播前端动画或重复提交 |
| S3 审核态 | 顶部整套缩略条、中央大图与候选历史、右侧当前图决策区 | `采用此图`、`重做这张`、高级设置中的 `查看和编辑完整提示词`、`查看生成记录`、全部选定后 `检查并导出` | 审核围绕图片与决定；Prompt 保留完整控制力但不是首屏工作中心；导出门禁由 service 投影而非前端计数决定 |
| S3 返工层 | 问题快捷项、自由修改方向、保持/改变/结果预览 | `生成返工方案`，预览就绪后 `确认并重做这张` | 第一步只编译版本化提案、不调用图片模型；第二步绑定 proposal/base version/action id，旧候选与非目标 Shot 保持不变 |
| S4 | 已选图片、缺失/硬检查摘要、命名、manifest 内容和导出位置 | `返回审核`、`导出交付包`、成功后 `打开文件夹` | 只显示会影响交付的检查和最终内容；缺选定图、硬规则失败或标题/Prompt 不一致时阻止导出并给出返回位置 |

S2 对模型推断明确标记来源；用户的修正保存为新 Brief 版本，再重编译受影响的 Plan/Prompt。未确认推断不得成为卖点文字；非关键视觉推断可供用户检查后接受默认方案。Prompt 编辑器是 S2/S3 的高级抽屉，展示系统生成的完整文本、结构化块、父版本和恢复推荐按钮；不是首屏必填项。S1 的 `生成整套图片` 是一个明确的“采用系统默认方案并执行”命令：若当前没有有效 Brief/Plan/Prompt，由 Application Service 先编译并原子保存这些版本，再创建生成批次；若准备失败则停在准备阶段并保留已确认输入，不创建半批次或假进度。

### 8.3 返工交互

用户可以使用快捷原因，也可以直接描述：

- 商品不像原图；
- 场景/背景不合适；
- 构图或产品大小不合适；
- 光线/颜色不合适；
- 文字或信息有问题；
- 其他（自由描述）。

系统先显示：

```text
保持：商品身份、已确认事实、整套 Style Lock、非目标 Shot
改变：当前 Shot 的 [scene/composition/light/copy/...]
结果：创建 Prompt vN+1，只重新生成当前 Shot，旧候选继续保留
```

流程固定为：输入快捷原因/文字 → `生成返工方案` → 展示保持/改变项和 Prompt 差异 → 用户点 `确认并重做这张` → 才提交图片模型。确认请求绑定 `proposal_id`、Shot/Prompt 基础版本和唯一 `action_id`；如果预览后基础版本变化则拒绝旧确认并要求刷新。预览阶段绝不创建图片 Attempt 或产生图片模型费用。若“商品不像原图”，系统优先检查参考图角色和商品保真块，不只是向 Prompt 尾部堆否定词。

### 8.4 按钮门禁与反馈合同

| 动作 | 可执行前提 | 执行中 | 成功反馈 | 失败/Unknown |
|---|---|---|---|---|
| `生成整套图片` | 商品名、至少一张已保存参考图、工作空间可写；没有运行中的同一 action | 禁用重复点击，显示“准备方案/逐图生成”真实阶段 | 进入 S3，已完成候选立即可审阅 | 语义准备失败不提交图片；局部图片失败留在对应 Shot；Unknown 只能核对原任务 |
| `先看方案` | 与上相同，但不要求图片 Provider 可用 | 显示方案编译状态 | 进入 S2，展示已持久化 Brief/Plan/Prompt | 编译失败停在 S1，错误定位到资料、配置或 Provider |
| `按此方案生成` | Plan/Prompt 当前有效，无未裁决身份冲突 | 创建唯一批次并进入 S3 | 逐图状态来自 Workspace 投影 | 过期 etag/版本冲突要求刷新，不偷偷采用旧方案 |
| `采用此图` | Candidate 文件存在、hash 有效且属于当前 Shot | 保存 SelectionVersion | 当前 Shot 标记已选定，刷新后不丢失 | 候选损坏或版本冲突时不改变原选择 |
| `保存 Prompt` | 当前 Shot 可编辑且 base version 未过期 | 只写 PromptVersion，不调用图片模型 | 当前 Shot 标记 stale，主动作改为重新生成该图 | 失败保留原 Prompt/Selection，不显示已生效 |
| `确认并重做这张` | 返工 proposal 未过期且用户明确确认 | 只锁定目标 Shot；非目标 Shot 仍可审阅 | 新候选追加到历史，旧候选可切回 | Unknown 核对原 task id；不得自动整组重跑 |
| `检查并导出` | 所有必需 Shot 有有效 Selection，确定性硬检查通过 | 生成新的 ExportVersion，不覆盖旧导出 | 展示导出位置和打开文件夹入口 | 指出缺失 Shot/规则/一致性问题及返回位置，不创建伪完成 Export |

### 8.5 获认可候选与正式迁移边界

`out/product-workbench-concept-2026-09-29/` 是 D4.4 的交互与视觉参考，获认可内容包括：

- 首页只保留新建、打开、最近工作；
- 资料页突出参考图和最少商品事实，主动作是一键整套生成；
- 方案页可跳过，默认方案直接可用，也能用自然语言增加图片任务；
- 审核页以图片为中心，整套缩略条、大图、候选历史和当前图决策同时可见；
- 返工使用业务问题和修改方向表达，Prompt 作为高级能力保留；
- 中文界面精简，不用说明卡、内部对象名或开发者状态填满页面。

不得从该候选迁移：硬编码针织衫、历史素材、本地计时器、浏览器内 selection、模拟导出、Amazon UK/JP 下拉、`查看模拟结果` 或任何由前端自行推导的成功。正式迁移以 `app/product_v1_server.py` 的 API 与 Workspace 投影为唯一事实源；候选页面保留在 `out/` 供视觉回归和回退比较，不进入正式导航。

---

## 9. 正式 API 最小合同

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/workspaces` | 在指定目录创建空工作空间 |
| POST | `/api/workspaces/open` | 打开并恢复工作空间 |
| GET | `/api/workspace` | 读取当前 UI 投影 |
| PUT | `/api/intake` | 保存资料与原始图片 |
| POST | `/api/plan/compile` | 真实语义模型生成 Brief/Plan/Prompt 草案 |
| PUT | `/api/brief` | 保存用户纠正后的 ProductBrief 新版本，并使受影响的 Plan/Prompt 当前版本 stale |
| PUT | `/api/plan` | 保存用户调整后的 PlanVersion |
| PUT | `/api/shots/{id}/prompt` | 保存 PromptVersion |
| POST | `/api/generations` | 为待生成 Shot 建立真实批次 |
| GET | `/api/generations/{id}` | 获取进度和逐 Shot 状态 |
| POST | `/api/attempts/{id}/reconcile` | 核对 UNKNOWN，不创建新提交 |
| POST | `/api/shots/{id}/rework-preview` | 基于用户返工方向生成版本化预览，不调用 ImageProvider |
| POST | `/api/shots/{id}/rework` | 提交用户已确认且未过期的返工草案；请求携带 proposal_id、基础版本、action_id/idempotency_key |
| PUT | `/api/shots/{id}/selection` | 选择候选 |
| POST | `/api/exports` | 复检并生成不可覆盖导出版本 |

前端不根据本地变量推导业务成功；所有按钮门禁和状态来自 service 投影。

### 9.1 D0.3 工作空间与商品资料服务契约

D0.3 先实现可由正式 HTTP 入口调用的框架无关服务方法：`create_workspace(directory)`、`open_workspace(directory)`、`get_workspace_projection(directory)` 和 `save_intake(directory, expected_etag, ...)`。这一切片不连接旧 Mock，不调用任何模型；HTTP 路由绑定由后续正式入口切片完成，业务状态始终只由 WorkspaceStore 读取。

服务响应将 HTTP 状态码与 JSON body 分开保存；body 固定为成功 `{"ok":true,"data":object,"error":null}` 或失败 `{"ok":false,"data":null,"error":object}`。`error` 固定含 `code`、面向使用者的 `message`、`field`、`recoverable`、`next_action` 和结构化 `details`，供 HTTP 层原样映射和页面定位字段。

工作空间投影仅包含当前入口需要的信息：

```text
workspace = {id, status, created_at, updated_at, revision}
intake = {product_name, description, selling_points, user_intent, reference_images}
readiness = {state, can_save_intake, missing_required}
```

空白工作空间只显示 `NEW`、空商品资料和缺少项，不出现 Plan、Prompt、生成或候选占位。资料写入使用投影里的 `revision` 作为 `expected_etag`；陈旧请求以 `REVISION_CONFLICT` 拒绝，且在版本核对通过前不写文件。商品名称和 1–3 张可解码的 JPEG/PNG/TIFF/GIF 参考图为保存所需材料；路径由内容 SHA-256 派生，原文件名只作显示元数据。平台版本从当前 `amazon-us` 配置读取。资料落盘顺序为原图、不可变 ProductInput 版本、最后原子提交 Workspace 当前指针；重复保存不产生新版本。

D0.3 合同测试须覆盖空白创建、缺料定位、无效/错误目录、无效图片不落盘、陈旧 revision、成功保存后重开恢复，以及稳定的错误 envelope。D0.3 完成后才开始 D0.4 页面路由和表单接线；浏览器不得在本地另存一份业务真相。

---

## 10. 实施阶段与任务卡

执行纪律：任一时刻最多一个任务 active；每个 Gate 由 current state 引用新鲜证据关闭。任务表是结构权威，状态不写在本节。

### Phase -1：Goal 与控制面切换

**结果：** 新目标、计划、执行状态和当前实现各有唯一权威；旧 Aster Goal 不再驱动施工。

| ID | 结果 | 依赖 | 产物 | 验收与证据 | 失败/回退 |
|---|---|---|---|---|---|
| D-1.1 | 重建权威产品计划并校准当前状态 | — | 本计划 v2.3、校准审计、旧文件快照 | `docs/INDEX.md` 仍只有一份产品目标和执行状态；守卫通过 | 恢复 `_stage-amz-control/product-v2-plan-20260928/` 快照 |
| D-1.2 | 替换并绑定系统 Goal objective | D-1.1 | 与 §2 一致的新 Goal id/objective | 读取系统 Goal 后 objective 语义逐项一致；旧 Goal 不再是当前执行依据 | 无法更新则结束旧 Goal 后新建，禁止双目标并行 |
| D-1.3 | 恢复 Goal 并冻结开工基线 | D-1.2 | Goal active 读数、代码/入口/检查清单、基线报告 | 系统 Goal active；控制面守卫和当前回归通过；无产品代码提前修改 | 回归失败先诊断，Goal 未 active 则保持 paused |

**Gate G-1：** 系统 Goal 已采用 §2 objective 并为 active；当前 state 绑定正确 Goal id；文档/项目状态守卫通过；旧计划只作历史证据。

### Phase 0：文件夹工作空间与真实空白入口

**结果：** 用户可以从空白创建/打开/恢复商品工作空间；还不调用模型也不伪造未来结果。

| ID | 结果 | 依赖 | 产物 | 验收与证据 | 失败/回退 |
|---|---|---|---|---|---|
| D0.1 | 冻结 Product V1 文件契约与配置语法 | G-1 | Workspace/ProductInput/Brief/Plan/Shot/Prompt/Attempt/Candidate/Selection/Export schema；archetype/platform/provider 配置；离线验收器与时点报告 | 按下方 D0.1 合同完成正反样例、配置 bundle、hash/版本/引用/选择导出门禁验证；正式 Provider 配置可直接通过 | 任一契约或配置失败就保持 D0.1 pending，不进入 D0.2；不迁移旧 v2 数据；冻结后禁止无版本原地改语义 |
| D0.2 | 实现 WorkspaceStore | D0.1 | `src/workspace_store.py`、原子写入、锁、内容 hash、版本分配 | 创建/保存/崩溃前后/并发锁/不可覆盖测试 | 写失败不移动当前指针；保留临时文件供诊断 |
| D0.3 | 建立正式 Application Service | D0.2 | service 接口、工作空间 UI 投影、错误结构 | API 合同测试覆盖空白、缺料、坏目录和恢复 | 不读取旧 Mock 内存状态作为权威 |
| D0.4 | 实现 S0/S1 空白前端 | D0.3 | 新建、打开、最近、上传、字段编辑和保存 | 桌面/390px；键盘可操作；空白无未来面板 | 保留旧入口快照，不在旧三栏 DOM 上叠补丁 |
| D0.5 | 跑通工作空间纵向切片 | D0.4 | 创建→保存→关闭→重开证据 | 原始图 hash 不变；字段和当前状态恢复；零联网 | 任一状态只在浏览器内存在则 Gate 不过 |

#### D0.1 详细实施合同

**输入与边界**

- 输入：Goal §2、产品合同 §3–7、现有 `contracts/product-v1.schema.json`、`config/product-v1/` 和 `src/product_v1_contracts.py`。D0.1 只冻结文件形状、配置语法与记录间的不变量；不实现 WorkspaceStore、UI、Provider 调用或真实模型请求。
- 领域记录：Workspace、ProductInput（含可选 `user_intent`/“本次重点”）、ProductBrief、Plan、ShotSpec、Prompt、GenerationAttempt、Candidate、Selection、Export；应用配置：ArchetypeRegistry、PlatformProfile（规则来源 URI/版本/核对时间）、ProviderRegistry。
- 未配置 SemanticProvider 默认值允许作为 D0.1 的显式待配置状态；但 D1.1 必须在启用编译前冻结确切 Provider/model/响应格式。图片 Provider 的默认模型固定为 Goal 指定的 `qwen-image-3.0`。
- Archetype Registry 保留少量通用注册类型并加入 `custom` 通用回退；更新 schema/config 与校验器，使 `custom` Shot 依靠统一 `title/purpose/reason/preserve/change` 等字段表达当前商品任务，不要求扩建品类模板；平台必需的注册类型仍须存在。

**执行顺序**

1. 固定每种记录的身份、版本、必填/可空字段、枚举、hash 计算与相对路径规则；模型提案不得写入正式记录而跳过来源、引用与硬约束校验。
2. 完成三份应用配置的严格校验及交叉引用：Archetype id 唯一；平台必需 Archetype 存在；平台尺寸范围自洽；默认 Provider id/role 正确，图片 Provider 必须声明参考图和任务查询能力。
3. 明确 `max_attempts` 是同一 action 下的自动提交上限，不包含查询/轮询。V1 Provider 默认值为 `1`；人工发起的重试创建新 action。请求进入 UNKNOWN 后不得自动重提，必须先按原 provider task id 核对；没有可核对 id 时保留 UNKNOWN 并停止提交。提高上限须等 D2.2 证明对应错误可安全重试，不以模型能力实验决定。
4. 补足跨记录验证和可定位的错误：错误至少指出记录 kind、字段路径和违反的规则，避免只返回无法行动的外层 `oneOf` 错误。
5. 新增 `tools/verify_product_v1_contracts.py`，从内存构造合法正例及变异反例；不联网、不读取用户工作空间、不写项目业务数据。把本次实际验证结果写入 `evals/product-demo/`，由 current state 链接。

**必测正反例**

- 正例：schema meta-check 通过；三份当前配置组成有效 bundle；一份关联完整的最小工作空间图通过，并覆盖每一种领域记录以及输入→Brief→Plan/Shot→Prompt→Attempt→Candidate→Selection→Export 的版本和引用关系；一个未由现有注册模式表达的任务通过 `custom` 完成结构校验。
- 结构反例：缺必填字段、未知字段、错误 schema/version、非法枚举、格式错误 hash、Prompt 文本 hash 不一致均被拒绝。
- 配置反例：重复 id、平台指向不存在的 Archetype、默认 Provider 的 role 错误、图片 Provider 缺少参考图/查询能力、`max_attempts` 缺失或越界均被拒绝。
- 关系反例：跨 Workspace/不存在的版本引用、Attempt 使用其他 Shot/Prompt、Candidate 与文件 hash 不符、重复或错配 Selection、导出候选不等于 Selection、缺少必需 Shot、`..`/绝对路径/反斜线逃逸均被拒绝。
- Archetype 反例：合法 `custom` ShotSpec 通过；未知注册 id、缺少任务目的/必要字段的 `custom` ShotSpec 失败；平台 Profile 引用不存在的必需 Archetype 失败。
- 选择语义：审核中的部分 Selection 是合法中间态；生成 Export 时必须拒绝缺少任何必需 Shot 的 Selection。不得把“半成品被拒绝导出”误做成“记录不合法”。
- 来源结构：合同保存用户声明与模型推断的来源/状态字段，内容 hash 覆盖每个 Brief 版本；D0.1 只验证这些字段、hash 与引用结构，不判断自然语言是否忠实表达事实。模型推断事实不得写成肯定营销文案、用户纠正形成新 Brief 版本等行为要求由 D1.2/D1.4 用固定语义样例验证。
- 验收器对合法样例退出码为 0；每个反例必须断言失败类别与字段定位，不能只断言“有异常”。运行完全离线且重复结果相同。

**冻结与回退规则**

D0.1 可在首次正式 Workspace 写入之前迭代；D0.2 开始产生持久化记录后，任何会改变校验结果或字段语义的变更必须明确版本号及读取/迁移策略。因为 V1 schema 拒绝未知字段，“只做加法”本身不构成兼容证明。D0.1 不改写、不导入旧 v2 数据；验收红时保留当前文件快照、修契约与正反例后重跑，不能放宽验证器迁就坏配置。

**Gate G0：** C1、C2 的工作空间部分 proven；正式入口真实空白启动并能恢复，且没有商品夹具、Mock 候选或未来阶段占位。

### Phase 1：商品理解、动态计划与 Prompt 编译

**结果：** 新商品资料能够通过真实 SemanticProvider 产生可解释、可修改的 Brief、动态 Plan 和完整 Prompt；不调用图片模型。

| ID | 结果 | 依赖 | 产物 | 验收与证据 | 失败/回退 |
|---|---|---|---|---|---|
| D1.1 | 建立 SemanticProvider 与默认 DashScope 适配器 | G0 | `qwen3.7-plus` 默认配置、结构化 draft 合同、脱敏日志、fake 合同适配器 | 真实调用可返回本地 schema 合法草案；无 key 明确阻止而非造结果；调用失败不写 Workspace | provider 错误仅保存脱敏摘要，不自动重试或污染 Workspace |
| D1.2 | 编译并可纠正 ProductBrief | D1.1 | 字段来源、可见事实、用户声明、待核对推断、不可变/可变边界与 Brief 更新动作 | 用户能看见并纠正关键事实；修正生成新版本及新 hash；来源与 `confirmed/inferred/unknown/conflicted` 状态保留；固定语义样例证明模型推断的材质/功能/尺寸不会转成肯定卖点 | 不确定信息标 `inferred/unknown/conflicted`；只在影响身份、宣传或方案时追问；语义规则测试不等于模型能力 benchmark |
| D1.3 | 编译动态 PlanVersion | D1.2 | 通用 Archetype Registry + `custom` 回退、PlatformProfile、Style Lock、1..N ShotSpec | 无固定张数/品类配方；每 Shot 有目的/理由/依赖；Amazon 必需主图存在 | 无依据卖点图不加入；用户可删除可选 Shot；注册类型不适用时用 `custom`，不因新商品阻断 |
| D1.4 | 编译并版本化 Prompt | D1.3 | PromptBlocks、完整文本、parent/diff/hash | UI 文本等于 service 返回文本；固定输入可复现；编辑只使目标 Shot stale；编译器只把允许作为商品声明的已确认事实写成肯定文案，推断/未知/冲突事实不得变成肯定卖点，Prompt 来源块可追溯 | 编译失败不回退空 Prompt；固定语义样例验证产品规则，不声称模型输出永不幻觉 |
| D1.5 | 实现 S2 方案工作区 | D1.4 | Brief 来源/核对状态、纠正动作、Shot 卡、调整/排序、Prompt 抽屉、一键生成门禁 | 默认不写 Prompt 可继续；纠正有版本链；固定目标标签可见；无内部 F1–F8 | 信息层级不清先改合同，不用说明卡掩盖 |
| D1.6 | 执行输入驱动反向探针 | D1.5 | 两结构不同商品 + 一份非内置输入的 Brief/Plan/Prompt 对照 | 无 Aster 泄漏；至少一处 Shot 组合或数量不同；商品块不同 | 任何固定 fixture fallback 立即跑红 |
| D1.7 | 固化“参考图优先”的冲突措辞守卫 | D1.3、D1.4 | ProductBrief 中 `conflicted` 事实的编译期守卫：Plan 编译警告、Prompt 末尾的不可越过指令、SemanticProvider 指令约束 | 商品文字与参考图冲突的措辞（如领型、门襟、纽扣）出现在 Shot 才能触发的文本里时产生 `CONFLICTED_WORDING_IN_SHOT`；Prompt 的 product-fidelity 块标注这些词 “NOT confirmed”，negative 块以“不得添加参考图中不可见部件”收尾；无冲突事实时不生成守卫文本 | 守卫不代替人工裁定：冲突仍由人决定以图还是以文字为准；不自动改写商品名称或已保存的 Shot 文本 |
| D1.8 | 单张阻断隔离与用户措辞授权 | D1.4、D1.7 | 提示词编译守卫区分“用户自己写过的措辞”与“模型推断词”；整套生成对单张提示词编译失败做隔离并显式报告 | 商品名/描述/卖点里出现过的词不再被判为未授权断言（`tools/verify_product_v1_conflict_guard.py` 4/4）；单张编译失败时其余 Shot 照常提交，`data.skipped_shots` 带原因，该张仍可经 `/api/generation/rework` 恢复（`tools/verify_product_v1_generation_isolation.py` 13/13）；缺 etag/版本冲突/未知 Shot 返回 428/409/404 设计信封 | 不得放过用户从未写过的推断词；不得把“整组失败”当成唯一失败语义；被跳过的图不能静默消失 |

**Gate G1：** C3–C5、C11 的编译部分 proven；使用者能从真实输入得到可直接执行且可调整的默认方案，系统不依赖穷举品类或固定图片数。

### Phase 2：真实整套生成与可恢复执行

**结果：** 一键对 Plan 中待执行 Shot 发起真实参考图生成，逐图保存进度、结果和异常，重启后可继续。

| ID | 结果 | 依赖 | 产物 | 验收与证据 | 失败/回退 |
|---|---|---|---|---|---|
| D2.1 | 将已验证 I2I 代码提升为正式 ImageProvider | G1 | `src/providers/dashscope_image.py`、provider registry、capability snapshot | 请求包含有序参考图、完整 Prompt、model/params；demo 包不再是正式入口 | 保留原 adapter 只读快照，合同不一致则不切换 |
| D2.2 | 持久化 Attempt 与 Unknown 核对 | D2.1 | action id、request hash、task id、状态与 reconcile | 双击/重启不重复 submit；Unknown 用原 task id 核对 | 无 task id 的未知保持人工处理，不假定失败 |
| D2.3 | 实现 Plan 批量执行器 | D2.2 | 每 Shot 独立队列、并发上限、局部失败和取消边界 | 成功/失败/Unknown 混合轨迹；成功候选不回滚 | 不自动整组重跑；预算/凭据拒绝零提交 |
| D2.4 | 实现 S3 进度与异常反馈 | D2.3 | 整套缩略条、当前图、进度、失败/核对入口 | 刷新/重启后状态一致；只有 Unknown 显示核对 | UI 不猜测完成，不靠轮询次数判失败 |
| D2.5 | 完成真实整套生成轨迹 | D2.4 | 新鲜 provider 请求、task id、候选、成本与时间记录 | 至少一个完整 Plan 真生成；非 Mock；参考图请求可审计 | 模型画面不好进入人工审核/返工，不转回能力实验 |

**Gate G2：** C6、C7 proven；正式页面可真实一键出整套，部分失败与 Unknown 可恢复，重启不丢任务或重复付费提交。

### Phase 3：审核、单图返工、选择与导出

**结果：** 用户从候选完成图片决策和局部修正，并得到可交付文件夹。

| ID | 结果 | 依赖 | 产物 | 验收与证据 | 失败/回退 |
|---|---|---|---|---|---|
| D3.1 | 完成候选比较与人工选择 | G2 | 大图/缩略图/候选历史、SelectionVersion | 每个必需 Shot 可唯一选定；旧候选始终可查看 | 文件损坏候选不可选但不删除 |
| D3.2 | 完成 Prompt 编辑与定向返工 | D3.1 | 编辑器、返工原因、版本化预览、确认动作与新版本链 | 预览不调用 ImageProvider；确认绑定 proposal 与基础版本；只目标 Shot 新建 Prompt/Attempt/Candidate；无关 hash 不变 | 过期草案拒绝提交并要求重新预览；不自动整组重跑 |
| D3.3 | 实现确定性平台/文件检查 | D3.1 | Amazon US 主图与通用文件检查报告 | 测量值、规则版本、官方来源 URI 与核对时间写入 Profile/报告/manifest；pass/fail 可复现 | 语义/审美只提示人工，不伪装硬门；无来源的规则不得宣称已验证合规 |
| D3.4 | 完成 ExportVersion | D3.2、D3.3 | 图片命名、manifest、人读 README、打开文件夹 | 只导出当前选择；篡改文件可被 hash 检出；重导不覆盖 | 任一必需图缺失或硬规则失败则拒绝发布该版本 |
| D3.5 | 跑完整真实业务闭环 | D3.4 | 空白→方案→真实套图→单图返工→选择→导出证据 | C8–C10 全 proven；至少一次返工保留旧候选 | 发现上游语义错误回到最早责任层，不在导出层补假状态 |
| D3.6 | 对齐方案文本与交付物标题 | D3.4 | 导出前的一致性提示：交付包标题取自当前方案，而提示词可被单独改写 | 操作员只改了某张图的提示词、没有更新方案文本时，导出前能看到“标题与这张图的提示词不一致”的提示并跳回方案编辑；不得静默导出不一致标题 | 不改写任何已保存记录；改方案还是改提示词由人决定（改方案会使整套 Prompt 失效，这一点必须在提示里说明） |

**Gate G3：** C8–C10 proven；用户能够完成完整套图生产闭环，导出包可追溯且不依赖命令行。

### Phase 4：产品化、陌生人走查与完成审计

**结果：** 获认可的图片优先工作台接入真实业务链；产品可以在干净 Windows 状态启动、诊断、备份和恢复，并由首次使用者独立完成任务。

D4.1–D4.3 已形成启动、旧正式界面可用性和备份恢复基线。由于 D4.4 起替换关键前端信息架构，D4.2 的 done 状态只表示历史任务及其证据真实存在，不证明最终界面；D4.12 必须对新正式版本重新执行全部可用性、可访问性、恢复和回归验收。D4.3 的 Workspace 备份机制可以复用，但最终发布候选仍须重跑换目录恢复。

| ID | 结果 | 依赖 | 产物 | 验收与证据 | 失败/回退 |
|---|---|---|---|---|---|
| D4.1 | 提供 Windows 启动器、设置和 doctor | G3 | 一键启动、端口/目录/key/provider 检查、清晰错误页 | 无开发机绝对路径；缺配置给出可执行修复 | doctor 不修改业务文件；旧启动方式保留到发布冻结 |
| D4.2 | 完成可用性与可访问性收敛 | D4.1 | 键盘/焦点/错误关联/loading/390px/200% 检查 | 主流程无隐藏按钮、横向溢出或仅颜色状态 | 不为动效牺牲操作；问题回对应 Screen/Action 合同 |
| D4.3 | 完成干净安装、备份和恢复演练 | D4.2 | 安装记录、工作空间备份、恢复和版本清单 | 换目录后可打开并继续；原图/候选/hash 一致 | 恢复不覆盖较新 Workspace；冲突另存副本 |
| D4.4 | 冻结获认可前端交互合同与迁移映射 | D4.3 | §8 合同、候选→正式对象/动作/状态/API 映射、旧正式静态资源快照 | 每个可见按钮都有前提、命令、成功、失败和恢复；明确不迁移硬编码商品/候选/本地状态；Amazon US 为固定标签 | 候选仅保留在 `out/`；映射不完整则不改正式入口，旧正式静态资源可恢复 |
| D4.5 | 建立正式首页与工作空间外壳 | D4.4 | 正式 S0、加载/空/错误态、真实最近索引、新建/打开/恢复导航 | 全新启动无预填商品或历史图；最近项只来自真实索引；打开损坏/不可写目录有可执行反馈；刷新恢复正确 Screen | 前端失败只回退静态资源快照，不改 Workspace；旧页面不进入正式导航 |
| D4.6 | 完成商品资料纵向切片 | D4.5 | 图片上传/预览、商品名、可选卖点/创作要求、固定 Amazon US、保存与字段错误 | 1–3 张图及字段真实写入 Workspace；原图 hash 不变；缺图/缺名称/写入冲突定位到字段；刷新/重启恢复 | 保存失败不清空表单、不移动当前输入版本；禁止用浏览器内对象冒充已保存 |
| D4.7 | 完成动态方案与一键整套编排 | D4.6 | 精简 Brief 摘要、动态 Shot、自然语言 `custom`、`先看方案`、`生成整套图片` 应用命令 | 主动作可从有效 Intake 自动编译并持久化 Brief/Plan/Prompt 后创建唯一 GenerationBatch；次动作只停在方案页；无固定张数/品类常量；双击不重复提交 | 语义准备失败零图片提交；任一步失败保留最近有效版本；不得由前端串出半完成成功状态 |
| D4.8 | 完成逐图生成、异常与恢复界面 | D4.7 | 准备/生成真实阶段、逐 Shot 状态、局部失败、欠费/限流、Unknown 核对、重启恢复 | 成功候选随到随看；局部失败不清除成功图；Unknown 只按原 task id 核对；刷新/重启不重复付费提交 | Provider 失败保留 Attempt/Candidate；无可查询 id 的 Unknown 保持人工处理，不假定失败 |
| D4.9 | 完成图片优先审核与选择工作台 | D4.8 | 整套缩略条、中央大图、候选历史、当前图决策、SelectionVersion、导出门禁 | 切换 Shot/候选不会丢状态；每个必需 Shot 可唯一选定；旧候选始终可见；候选损坏不可选但不删除；刷新恢复选择 | UI 不按缩略图数量推导可导出；保存选择失败保留原选择并显示冲突 |
| D4.10 | 完成两阶段返工与高级 Prompt | D4.9 | 快捷原因/自由方向、返工 proposal、保持/改变/结果和 Prompt diff、确认执行、Prompt 高级抽屉 | 预览阶段零 ImageProvider 调用；确认绑定 proposal/base/action id；仅目标 Shot 新建 Prompt/Attempt/Candidate；旧候选和无关 Shot hash 不变；Prompt 保存使目标 Shot stale | 过期 proposal 拒绝确认；失败不覆盖旧 Prompt/Selection；不得自动整组重跑 |
| D4.11 | 完成导出检查与交付界面 | D4.10 | 已选图片摘要、硬检查/一致性问题、导出位置、ExportVersion、打开文件夹 | 未选全、硬规则失败或标题/Prompt 不一致时精确阻断；成功导出只包含当前选择，manifest 可反查输入/版本/模型/候选；重导不覆盖 | 失败不创建完成 ExportVersion；历史选择和旧导出保持可用 |
| D4.12 | 对最终前端重做产品级回归 | D4.11 | 正常/缺料/局部失败/Unknown/重启/返工/导出浏览器轨迹，桌面/390px/200%/键盘/焦点检查，换目录恢复，两次全回归 | 正式入口无 Mock/历史图/开发机路径；零未解释 console error；所有按钮门禁来自 service；两次连续通过且静态资源、代码和证据指纹一致 | 任一关键路径失败回到最早责任任务；D4.2/D4.3 旧证据不得替代本次复验 |
| D4.13 | 执行最终首次使用者走查 | D4.12 | 业务任务、屏幕/事件记录、开发者介入计数、问题与修订 | 首次使用者不靠命令行、JSON 或口授完成新建、方案/一键生成、一次单图返工、选择和导出；开发者介入 0 | 关键路径修改后必须换新的首次使用者重验；走查问题回对应 D4.5–D4.12 |
| D4.14 | 建立 C1–C13 完成审计并冻结发布候选 | D4.13 | completion matrix、发布 manifest、限制、备份/回退说明 | 每项 C1–C13 均有范围匹配的新鲜 proven 证据；正式入口、文档、文件指纹一致；无代码/配置/资产漂移 | 任一项 missing/indirect 或真实凭据/人工选择缺失时 Goal 保持未完成 |

#### D4.4–D4.14 详细实施合同

**实施边界**

- 正式改动落在 `app/product_v1/`、`app/product_v1_server.py` 和确有缺口的 Application Service/API；不得把 `out/` 候选文件直接改名后上线。
- `src/workspace_store.py` 及已验证的 Brief/Plan/Prompt/Attempt/Candidate/Selection/Export 记录继续拥有业务状态；JavaScript 只渲染投影、收集命令和反馈结果。
- 为一键主路径可以增加一个应用层编排命令，但不得新增第二套领域对象。命令必须带 `action_id`、`expected_etag` 和幂等边界；内部顺序固定为 `validate intake → compile missing/stale versions → persist → create generation batch`。
- 正式页面只展示 Amazon US 固定目标。Provider 配置仍可替换，但模型选择器、其他站点和批量 SKU 不进入本阶段。
- 每完成一个任务只迁移一个可观察纵向结果；保持单任务 WIP。视觉静态资源、验证脚本可以在不写同一权威文件时准备，但不得越过 Gate 合并。

**页面—服务—持久状态映射**

| 用户动作 | 正式服务/API | 权威写入或读取 | 页面不得自行做的事 |
|---|---|---|---|
| 新建/打开/最近工作空间 | `/api/workspaces*`、`GET /api/workspace` | Workspace 与本机 recent index | 预填示例商品、从 localStorage 伪造最近项或工作状态 |
| 编辑并继续 | `PUT /api/intake` | 新 ProductInput 版本、参考图相对路径与 hash | 仅保存浏览器 File/Object URL 后声称资料已保存 |
| 先看方案 | ProductBrief/Plan/Prompt 编译服务 | 新 Brief/Plan/Prompt 版本及来源 | 在 JS 里套模板、固定张数或凭品类常量造 Shot |
| 生成整套图片 | 应用层 `generate_suite` 编排命令 | 必要编译版本、GenerationBatch、逐 Shot Attempt | 用多个无幂等前端请求拼接“一键”，用计时器假装进度 |
| 查看进度/异常 | Workspace 投影与 reconcile | Attempt/Candidate 状态、provider task id | 以轮询次数判失败，Unknown 后直接重提 |
| 采用候选 | Selection 服务 | SelectionVersion | 只切 CSS 选中态或覆盖旧候选 |
| 编辑 Prompt/返工 | Prompt 更新、rework preview/confirm | PromptVersion、proposal、目标 Attempt/Candidate | 预览阶段调用图片模型、改动无关 Shot、丢弃旧候选 |
| 检查并导出 | Export 服务 | 检查报告、ExportVersion、manifest | 用前端计数宣布可导出，覆盖历史交付包 |

**每个任务的完成证据**

1. 组件证据：新增/改变的 API、状态投影、版本和门禁有正反合同测试。
2. 轨迹证据：至少覆盖正常、缺料、业务拒绝、技术失败和需要恢复的路径；涉及外部异步任务时必须覆盖 Unknown。
3. 浏览器证据：从正式入口操作，核对可见反馈、console/network、API 响应和 Workspace 文件后置条件；截图或 DOM green 不能单独证明完成。
4. 回退证据：静态资源可恢复，Workspace 不被前端迁移破坏；外部调用或导出失败时已存在版本仍可打开。
5. 任务状态只有在上述证据落盘并由 current state 引用后才能从 pending 改为 done；候选页面获认可不等于任一 D4.5–D4.14 已完成。

**Gate G4：** C1–C13 全部 proven；发布候选冻结后未发生代码、配置或资产漂移，方可标记系统 Goal 完成。

---

## 11. 任务依赖主链

```text
D-1.1 → D-1.2 → D-1.3 → G-1
  → D0.1 → D0.2 → D0.3 → D0.4 → D0.5 → G0
  → D1.1 → D1.2 → D1.3 → D1.4 → D1.5 → D1.6 → G1
  → D1.1 → D1.2 → D1.3 → D1.4 → D1.5 → D1.6 → D1.7 → D1.8 → G1
  → D2.1 → D2.2 → D2.3 → D2.4 → D2.5 → G2
  → D3.1 → D3.2 ─┐
             D3.3 ├→ D3.4 → D3.5 → G3
  → D4.1 → D4.2 → D4.3 → D4.4 → D4.5 → D4.6 → D4.7
    → D4.8 → D4.9 → D4.10 → D4.11 → D4.12 → D4.13 → D4.14 → G4
```

单任务 WIP。只有测试编写、静态资源或独立审计确实不写同一权威文件时才并行；并行不改变 Gate 顺序。

---

## 12. 验证策略

### 12.1 四层证据

1. **组件证据**：schema、hash、原子写入、Prompt 编译、Provider 合同、文件检查。
2. **轨迹证据**：正常、缺料、业务拒绝、技术失败、Unknown、重启、局部返工。
3. **系统证据**：浏览器从空白到导出；真实 provider 请求与结果；干净环境安装。
4. **产品证据**：非内置商品与首次使用者独立完成。

### 12.2 必须存在的反向探针

- 把任一内置夹具的商品身份常量注入非夹具资料 Prompt，C3/C11 必须失败；反向探针测的是跨商品泄漏，不是某个水杯细节是否符合设计偏好；
- 提交只由模型推断的卖点，若没有用户确认却出现在肯定营销文案里，C3/C5 必须失败；
- 用 `custom` Shot 表达一个不由现有注册模式覆盖的视觉任务时，通用流程必须可编译/生成，不得要求新增某一商品类别模板；
- 把计划强制固定为同样张数/Shot，C4 必须失败；
- UI Prompt 与请求 Prompt 改成不同文本，C5 必须失败；
- 删除请求中的参考图，C6 必须失败；
- UNKNOWN 后创建新 submit，C7 必须失败；
- 返工时改变无关 Shot hash 或 Attempt 数，C8 必须失败；
- 导出未选候选或被篡改图片，C9/C10 必须失败；
- 用 Mock/历史候选替代真实调用，完成审计必须失败。

### 12.3 “不做模型能力实验”的准确边界

不再用固定候选数、F1–F8 成功率或跨品类 benchmark 决定是否开发。真实调用仍需做功能验收：请求是否携带参考图、响应是否可下载、任务状态是否可核对、用户能否得到并选择候选。这是产品链路验证，不是模型选型实验。

---

## 13. 迁移、回退与停止条件

### 13.1 迁移原则

- 新正式能力优先放在 `src/` 与 `app/`，从 `demo/` 复制/提炼后再以合同测试证明等价；
- 旧 v2、旧 Mock 前端和历史 eval 在 G4 前不删除，只能从正式导航移除；
- 每个 Phase 开始前保存受影响权威文件和可执行入口快照；
- 不迁移无法说明消费方的对象、表或配置。

### 13.2 回退

- schema/Workspace 写入失败：不移动当前版本指针；
- 新 service 失败：恢复上一工作包快照，旧历史入口仍可用于诊断但不冒充产品；
- Provider 失败：保留 Attempt 和已有 Candidate，禁止重置整个 Workspace；
- 前端失败：回退静态资源版本，不改业务文件；
- 导出失败：不创建完成的 ExportVersion，历史选择仍有效。

### 13.3 停止并请求用户的条件

- 无法替换旧系统 Goal，导致 objective 与当前计划同时有效；
- 必须决定是否扩大 V1 到 Amazon US 以外平台、多人或批量 SKU；
- 需要真实商品事实，但用户输入与图片发生不可裁决冲突；
- 外部请求为 UNKNOWN 且 provider 无任何可查询身份；
- 完成需要把 Mock、历史图或模型自评冒充真实产品证据；
- 任何不可逆操作将覆盖原始素材、历史候选或用户工作空间。

---

## 14. 明确推迟的能力

- 主流程中的模型选择器；Provider 注册机制已经预留，第二个正式适配器出现后再展示；
- Amazon US 之外的平台 Profile；
- 自动语义/审美质检与自动 Prompt 自修循环；
- 批量 SKU、队列调度、多用户权限和共享数据库；
- 云部署、自动上架、运营指标或销售效果归因；
- 精确文字排版、复杂信息图后处理和视频；
- 完整品类知识库。真实使用中反复出现的规则再沉淀为 Category Hint，不预先穷举。

这些项目不得进入当前完成条件，也不得以“架构预留”为由提前建设。

---

## 15. 执行状态路由

当前进度、证据、阻塞和唯一下一动作只读：

`_working/amz-listing-kit-product-demo/state.md`

当前代码实际能做什么只读：

`README.md`、正式入口代码与新鲜验证结果。

控制面校准和某次运行结果只作时点证据，位于 `evals/`；它们不得发布新的当前计划或执行状态。
