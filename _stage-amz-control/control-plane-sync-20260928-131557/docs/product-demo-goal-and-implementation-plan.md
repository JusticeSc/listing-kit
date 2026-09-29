# amz-listing-kit Product V1 Goal 与详细实施计划

> CONTROL-STATUS: current · AUTHORITY: product-contract-and-task-graph  
> 本文件唯一管辖产品目标、完成合同、目标架构、阶段、Gate、任务定义与依赖；执行进度、证据和唯一下一动作只在 current state 维护。

版本：v2.2  
日期：2026-09-28  
状态：当前唯一权威产品合同与实施任务图；Goal 生命周期、执行进度和唯一下一动作只以 current state 为准

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

### 1.2 当前不能声称

- 正式入口尚不能从任意商品资料动态生成 ProductBrief、套图计划和 Prompt；
- 当前 `app/static/` 仍是被否定的旧 Mock 前端，不是目标产品；
- 浏览器脚本通过只证明旧轨迹可运行，不证明通用商品产品成立；
- Aster/Bex 两个固定夹具的差异不证明输入驱动的通用编译器；
- 旧的 Aster/F1–F8 Goal 只保留为历史背景，不再作为当前执行依据。

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
- **输入**：1–3 张同一商品参考图、商品名称/介绍、真实卖点、Amazon US 平台目标；其中只有参考图与商品名称为创建任务的最小硬输入，其余缺失项由系统提出草案并显式标注来源。
- **任务**：得到一套与当前商品和交付目的匹配、可逐图选择和局部返工的图片。
- **完成**：计划内每个必需 Shot 都有一个人工选定候选，最终文件通过确定性导出检查并生成 manifest。

### 3.2 使用者必须决定什么

| 决定 | 为什么不能完全代替用户 | 系统怎样减负 |
|---|---|---|
| 哪些素材属于同一商品 | 这是事实来源和外发授权边界 | 提供拖拽、预览、角色建议和重复/格式检查 |
| 商品介绍和卖点是否真实 | 模型不能凭图片证明功能、材质和宣传承诺 | 从图片与文字提出草案，标清来源，允许直接改 |
| 目标平台 | 决定图片用途、尺寸与主图规则 | 默认 Amazon US，平台规则自动进入计划和导出 |
| 是否调整默认套图方案 | 运营可能有本次活动或店铺意图 | 给出可直接执行的默认方案，只暴露必要调整项 |
| 哪张图可交付、哪里不满意 | 审美与业务接受权属于人 | 提供候选比较、快捷原因、自由描述与定向返工 |

模型、尺寸、seed、Provider 参数默认隐藏在高级设置；只有存在多个可用模型或排障需要时才展示。

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
| PlatformProfile | Amazon US 主图/副图的文件硬规则、语言、比例和角色要求 |
| Shot Archetype | `hero`、`feature`、`detail`、`lifestyle`、`scale`、`how_to`、`package`、`comparison`、`variant` 的字段和用途，不固定张数 |
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

---

## 5. 权威对象与工作空间格式

### 5.1 领域对象

| 对象 | 稳定身份 | 权威内容 |
|---|---|---|
| Workspace | `workspace_id` | 商品任务、当前指针、创建/更新时间和应用版本 |
| SourceAsset | 内容 SHA-256 | 原始图片、角色、来源和授权声明 |
| ProductInput | 版本 hash | 用户填写的名称、介绍、卖点、平台和本次意图 |
| ProductBrief | 版本 hash | 结构化商品理解、字段来源、不可变/可变边界 |
| PlatformProfile | `profile_id@version` | 平台规则和默认角色 |
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
| `revise_shot` | 用户给出方向/快捷原因 | 新 ShotSpec/PromptVersion 草案 | 先显示保持/改变项；用户确认后才调用模型 |
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

V1 图片默认使用 DashScope `qwen-image-3.0`。SemanticProvider 的确切 Provider/model 与配置在 D1.1 冻结；此项是配置决定，不做跨模型能力对比，也不建设模型选择器。Provider/model 只出现在配置、Attempt 和高级排障信息中；业务对象不引用供应商专属字段。

### 7.2 ProductCompiler

ProductCompiler 采用“模型提案 + 确定性编译”而不是自由文本直通：

1. SemanticProvider 输出符合 schema 的 ProductBriefDraft、PlanDraft 和 PromptBlocks；
2. 确定性代码校验字段、来源、Shot 身份、平台必需项和引用关系；
3. PromptCompiler 按固定顺序拼接：

```text
Product Fidelity Block
+ Campaign Style Lock
+ Shot Purpose/Scene/Composition Block
+ Platform/Output Block
+ Negative Constraints
```

4. 最终文本和结构化块一起保存；用户编辑全文时保留父版本和 diff；
5. 更换模型只更换 Provider/参数，不重写 ProductBrief、Plan 或 Workspace 状态机。

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
  └─ 生成套图方案 → S2

S2 套图方案
  └─ 一键生成整套 → S3

S3 生成与审核
  ├─ 编辑 Prompt / 只重做这张 → S3
  └─ 全部必需图已选择 → S4

S4 导出
  └─ 导出套图 / 打开文件夹
```

任何时刻只有一个主任务区。已完成阶段折叠为摘要；未来阶段不提前显示空面板。

### 8.2 视图与按钮

| 屏幕 | 主要视图 | 必要按钮 | 存在理由 |
|---|---|---|---|
| S0 | 最近工作空间列表、空态 | `新建工作空间`、`打开工作空间` | 解释产品如何启动和恢复，不把示例商品当默认状态 |
| S1 | 图片上传区、商品名称、介绍、卖点、平台 | `保存`、`生成套图方案` | 建立事实来源；按钮只在名称和参考图齐备时启用 |
| S2 | 商品理解摘要、套图 Shot 卡片、共享视觉方向 | `编辑资料`、`添加图片`、`移除/排序`、`查看/编辑提示词`、`一键生成整套` | 让默认方案可直接用，同时保留设计者需要的可解释控制 |
| S3 | 顶部整套缩略条、中央当前候选、右侧当前图操作 | `比较候选`、`采用此图`、`编辑提示词`、`只重做这张`、`核对状态`、`去导出` | 审核围绕图片和决策，不围绕内部流水线；Unknown 才出现核对 |
| S4 | 已选图片网格、缺失/检查摘要、导出位置 | `返回审核`、`导出套图`、`打开文件夹` | 导出前只显示会阻止交付的问题和最终内容 |

Prompt 编辑器是 S2/S3 的高级抽屉，展示系统生成的完整文本、结构化块、父版本和恢复推荐按钮；不是首屏必填项。

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

用户确认后执行。若“商品不像原图”，系统优先检查参考图角色和商品保真块，不只是向 Prompt 尾部堆否定词。

---

## 9. 正式 API 最小合同

| 方法 | 路径 | 作用 |
|---|---|---|
| POST | `/api/workspaces` | 在指定目录创建空工作空间 |
| POST | `/api/workspaces/open` | 打开并恢复工作空间 |
| GET | `/api/workspace` | 读取当前 UI 投影 |
| PUT | `/api/intake` | 保存资料与原始图片 |
| POST | `/api/plan/compile` | 真实语义模型生成 Brief/Plan/Prompt 草案 |
| PUT | `/api/plan` | 保存用户调整后的 PlanVersion |
| PUT | `/api/shots/{id}/prompt` | 保存 PromptVersion |
| POST | `/api/generations` | 为待生成 Shot 建立真实批次 |
| GET | `/api/generations/{id}` | 获取进度和逐 Shot 状态 |
| POST | `/api/attempts/{id}/reconcile` | 核对 UNKNOWN，不创建新提交 |
| POST | `/api/shots/{id}/revise` | 生成定向返工草案并确认执行 |
| PUT | `/api/shots/{id}/selection` | 选择候选 |
| POST | `/api/exports` | 复检并生成不可覆盖导出版本 |

前端不根据本地变量推导业务成功；所有按钮门禁和状态来自 service 投影。

---

## 10. 实施阶段与任务卡

执行纪律：任一时刻最多一个任务 active；每个 Gate 由 current state 引用新鲜证据关闭。任务表是结构权威，状态不写在本节。

### Phase -1：Goal 与控制面切换

**结果：** 新目标、计划、执行状态和当前实现各有唯一权威；旧 Aster Goal 不再驱动施工。

| ID | 结果 | 依赖 | 产物 | 验收与证据 | 失败/回退 |
|---|---|---|---|---|---|
| D-1.1 | 重建权威产品计划并校准当前状态 | — | 本计划 v2.1、校准审计、旧文件快照 | `docs/INDEX.md` 仍只有一份产品目标和执行状态；守卫通过 | 恢复 `_stage-amz-control/product-v2-plan-20260928/` 快照 |
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
- 领域记录：Workspace、ProductInput、ProductBrief、Plan、ShotSpec、Prompt、GenerationAttempt、Candidate、Selection、Export；应用配置：ArchetypeRegistry、PlatformProfile、ProviderRegistry。
- 未配置 SemanticProvider 默认值允许作为 D0.1 的显式待配置状态；但 D1.1 必须在启用编译前冻结确切 Provider/model/响应格式。图片 Provider 的默认模型固定为 Goal 指定的 `qwen-image-3.0`。

**执行顺序**

1. 固定每种记录的身份、版本、必填/可空字段、枚举、hash 计算与相对路径规则；模型提案不得写入正式记录而跳过来源、引用与硬约束校验。
2. 完成三份应用配置的严格校验及交叉引用：Archetype id 唯一；平台必需 Archetype 存在；平台尺寸范围自洽；默认 Provider id/role 正确，图片 Provider 必须声明参考图和任务查询能力。
3. 明确 `max_attempts` 是同一 action 下的自动提交上限，不包含查询/轮询。V1 Provider 默认值为 `1`；人工发起的重试创建新 action。请求进入 UNKNOWN 后不得自动重提，必须先按原 provider task id 核对；没有可核对 id 时保留 UNKNOWN 并停止提交。提高上限须等 D2.2 证明对应错误可安全重试，不以模型能力实验决定。
4. 补足跨记录验证和可定位的错误：错误至少指出记录 kind、字段路径和违反的规则，避免只返回无法行动的外层 `oneOf` 错误。
5. 新增 `tools/verify_product_v1_contracts.py`，从内存构造合法正例及变异反例；不联网、不读取用户工作空间、不写项目业务数据。把本次实际验证结果写入 `evals/product-demo/`，由 current state 链接。

**必测正反例**

- 正例：schema meta-check 通过；三份当前配置组成有效 bundle；一份关联完整的最小工作空间图通过，并覆盖每一种领域记录以及输入→Brief→Plan/Shot→Prompt→Attempt→Candidate→Selection→Export 的版本和引用关系。
- 结构反例：缺必填字段、未知字段、错误 schema/version、非法枚举、格式错误 hash、Prompt 文本 hash 不一致均被拒绝。
- 配置反例：重复 id、平台指向不存在的 Archetype、默认 Provider 的 role 错误、图片 Provider 缺少参考图/查询能力、`max_attempts` 缺失或越界均被拒绝。
- 关系反例：跨 Workspace/不存在的版本引用、Attempt 使用其他 Shot/Prompt、Candidate 与文件 hash 不符、重复或错配 Selection、导出候选不等于 Selection、缺少必需 Shot、`..`/绝对路径/反斜线逃逸均被拒绝。
- 选择语义：审核中的部分 Selection 是合法中间态；生成 Export 时必须拒绝缺少任何必需 Shot 的 Selection。不得把“半成品被拒绝导出”误做成“记录不合法”。
- 验收器对合法样例退出码为 0；每个反例必须断言失败类别与字段定位，不能只断言“有异常”。运行完全离线且重复结果相同。

**冻结与回退规则**

D0.1 可在首次正式 Workspace 写入之前迭代；D0.2 开始产生持久化记录后，任何会改变校验结果或字段语义的变更必须明确版本号及读取/迁移策略。因为 V1 schema 拒绝未知字段，“只做加法”本身不构成兼容证明。D0.1 不改写、不导入旧 v2 数据；验收红时保留当前文件快照、修契约与正反例后重跑，不能放宽验证器迁就坏配置。

**Gate G0：** C1、C2 的工作空间部分 proven；正式入口真实空白启动并能恢复，且没有商品夹具、Mock 候选或未来阶段占位。

### Phase 1：商品理解、动态计划与 Prompt 编译

**结果：** 新商品资料能够通过真实 SemanticProvider 产生可解释、可修改的 Brief、动态 Plan 和完整 Prompt；不调用图片模型。

| ID | 结果 | 依赖 | 产物 | 验收与证据 | 失败/回退 |
|---|---|---|---|---|---|
| D1.1 | 建立 SemanticProvider 与默认 DashScope 适配器 | G0 | 接口、结构化响应、配置、脱敏日志、fake 合同适配器 | 真实调用可返回 schema；无 key 明确阻止而非造结果 | provider 错误保存原响应摘要，不污染 Workspace |
| D1.2 | 编译 ProductBrief | D1.1 | 字段来源、可见事实、声明卖点、不可变/可变边界 | 图片/文字变化导致正确字段变化；用户覆盖保留来源 | 不确定信息标 `inferred/unknown`，不写成已确认事实 |
| D1.3 | 编译动态 PlanVersion | D1.2 | archetype registry、PlatformProfile、Style Lock、1..N ShotSpec | 无固定张数；每 Shot 有目的/理由/依赖；Amazon 必需主图存在 | 无依据图型不加入；用户可删除可选 Shot |
| D1.4 | 编译并版本化 Prompt | D1.3 | PromptBlocks、完整文本、parent/diff/hash | UI 文本等于 service 返回文本；同输入稳定；编辑只使目标 Shot stale | 编译失败不回退空 Prompt |
| D1.5 | 实现 S2 方案工作区 | D1.4 | Brief 摘要、Shot 卡、调整/排序、Prompt 抽屉、一键生成门禁 | 默认不写 Prompt 可继续；高级信息可查；无内部 F1–F8 | 信息层级不清先改合同，不用说明卡掩盖 |
| D1.6 | 执行输入驱动反向探针 | D1.5 | 两结构不同商品 + 一份非内置输入的 Brief/Plan/Prompt 对照 | 无 Aster 泄漏；至少一处 Shot 组合或数量不同；商品块不同 | 任何固定 fixture fallback 立即跑红 |

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
| D3.2 | 完成 Prompt 编辑与定向返工 | D3.1 | 编辑器、返工原因、影响预览、新版本链 | 只目标 Shot 新建 Prompt/Attempt/Candidate；无关 hash 不变 | 返工方向不清先让用户确认，不自动整组重跑 |
| D3.3 | 实现确定性平台/文件检查 | D3.1 | Amazon US 主图与通用文件检查报告 | 测量值、规则版本、pass/fail 可复现 | 语义/审美只提示人工，不伪装硬门 |
| D3.4 | 完成 ExportVersion | D3.2、D3.3 | 图片命名、manifest、人读 README、打开文件夹 | 只导出当前选择；篡改文件可被 hash 检出；重导不覆盖 | 任一必需图缺失或硬规则失败则拒绝发布该版本 |
| D3.5 | 跑完整真实业务闭环 | D3.4 | 空白→方案→真实套图→单图返工→选择→导出证据 | C8–C10 全 proven；至少一次返工保留旧候选 | 发现上游语义错误回到最早责任层，不在导出层补假状态 |

**Gate G3：** C8–C10 proven；用户能够完成完整套图生产闭环，导出包可追溯且不依赖命令行。

### Phase 4：产品化、陌生人走查与完成审计

**结果：** 产品可以在干净 Windows 状态启动、诊断、备份和恢复，并由首次使用者独立完成任务。

| ID | 结果 | 依赖 | 产物 | 验收与证据 | 失败/回退 |
|---|---|---|---|---|---|
| D4.1 | 提供 Windows 启动器、设置和 doctor | G3 | 一键启动、端口/目录/key/provider 检查、清晰错误页 | 无开发机绝对路径；缺配置给出可执行修复 | doctor 不修改业务文件；旧启动方式保留到发布冻结 |
| D4.2 | 完成可用性与可访问性收敛 | D4.1 | 键盘/焦点/错误关联/loading/390px/200% 检查 | 主流程无隐藏按钮、横向溢出或仅颜色状态 | 不为动效牺牲操作；问题回对应 Screen/Action 合同 |
| D4.3 | 完成干净安装、备份和恢复演练 | D4.2 | 安装记录、工作空间备份、恢复和版本清单 | 换目录后可打开并继续；原图/候选/hash 一致 | 恢复不覆盖较新 Workspace；冲突另存副本 |
| D4.4 | 执行首次使用者走查 | D4.3 | 业务任务、屏幕/事件记录、问题与修订 | 首次使用者不靠命令行/JSON/口授完成；开发者介入 0 | 关键路径修改后换新首次使用者重验 |
| D4.5 | 建立 C1–C13 完成审计并冻结发布候选 | D4.4 | completion matrix、版本 manifest、限制与回退说明 | 每项 proven；两次连续全回归；正式入口与文档一致 | 任一必要项 missing/indirect 时 Goal 保持未完成 |

**Gate G4：** C1–C13 全部 proven；发布候选冻结后未发生代码、配置或资产漂移，方可标记系统 Goal 完成。

---

## 11. 任务依赖主链

```text
D-1.1 → D-1.2 → D-1.3 → G-1
  → D0.1 → D0.2 → D0.3 → D0.4 → D0.5 → G0
  → D1.1 → D1.2 → D1.3 → D1.4 → D1.5 → D1.6 → G1
  → D2.1 → D2.2 → D2.3 → D2.4 → D2.5 → G2
  → D3.1 → D3.2 ─┐
             D3.3 ├→ D3.4 → D3.5 → G3
  → D4.1 → D4.2 → D4.3 → D4.4 → D4.5 → G4
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

- 把 Aster 商品常量注入第二商品 Prompt，C3/C11 必须失败；
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
