<!-- 拆分件 19/29 · 父文档 docs/product-v2-refactor-design.md -->
# §13当前设计：普通决定、文案与唯一owner
[返回设计目录](product-v2-refactor-design.md) · [上一主题](product-v2-refactor-design.18-workbench-layout-and-interactions.md) · [下一主题](product-v2-refactor-design.20-rework-inputs-paths-and-history.md)

### 13.4 普通决定、文案与记录形状

专业表达由系统承担；已有人工全文仍保护。新字段写入现有StyleSpec/ShotSpec与版本化Prompt链，不创建“意图包”、另一商品事实库或聊天Agent。

1. **事实**仍是现有FactSlot：用户输入/原照观察/模型提议/默认/派生有来源和状态；model只能propose，不能confirm。明确用户确认一次覆盖同一值，不让已确认值因换图重复录入；保存草稿不等于确认。
2. **展示决定**：StyleSpec的新 `presentation` 提供共用默认；ShotSpec同名字段只存明确单图覆盖，未覆盖则继承。字段为 `appearance_state: "as_shown" | "clean_display" | "undecided"`、`contents_state: "as_shown" | "empty" | "not_applicable" | "undecided"`、`viewpoint: "reference_visible" | "front" | "side" | "top"`。共用“洗净、倒空”同时设置前两项，不代表新物性；非容器不展示倒空问题。非原可见视角还须绑定可支持该视角的商品依据；仅文件名/角色不能证明视角。
3. **问不问**是用途及证据投影：相关展示状态有歧义且会改变请求时才问；没有歧义/不消费该决定的用途不拦截。未回答的必要项为undecided并阻断对应图，不默选清洁。用户选顶视但无支持图时给“补图/使用已证视角/暂不做此图”，不补造隐藏结构。
4. **上图文案**明确选择，不遍历所有事实自动印字。ShotSpec新增 `on_image_texts`，每项有稳定text_id、原文text、源FactSlot精确DocumentRef、status（proposed/confirmed）和origin（user/model/reuse）；只消费confirmed且来源当前的项。品牌按原文保留，数字/单位/维度对应原事实；说明指令与实际印字分段。系统可在一次已明确外发的理解中提出英文文案，人工确认；纯人工路线可用已有文案或明确选无字，不强制AI/翻译/专业Prompt。自由文本与事实的语义关系需人工对照，Schema绿不证明文案真实。
5. **推荐**仍由 `domain/suite-plan.js` 消费用途/事实/参考；每项输出目标相关性、依据、缺口及替代动作。只默认选目标相关且有依据的图；无尺寸不凑尺寸图，无竞品不凑对比图。未知非消费者不成为全项目填资料义务；用户可以显式建未就绪图，但不能偷偷生成。

系统建议的背景/光照等可逆创意标明“建议”；用户明确意图优先，商品事实/平台硬约束不得覆盖。已存在手写keep/change_allowed/notes原文保留；结构决定与其冲突时展示给人，不能声称字符串相交或万能LLM自评已消除全部语义冲突。

### 13.5 唯一owner、Module Interface与实施落点

接口名沿当前owner扩展；下一版落地时查全部引用并同包迁移。返回只在本领域定义窄联合，不建通用dispatch/总线/port层。视图只交用户输入/所见版本、读取投影，不能自行保存→授权→HTTP→report→selection。

| owner／现有文件 | 下一版完整命令或投影 | 所有权/消费者约束 |
|---|---|---|
| inputs `project-inputs.ts` / `domain/specs.js` | `savePresentation({scope, presentation, seenStyleVersion, seenSpecVersions})`；`saveImageTexts({shotId, texts, seenSpecVersion})`；`planRecommendations()`只读 | 共用决定保存StyleSpec一次；单图覆盖保存对应ShotSpec并OCC。涉及多条时返回逐图成功/冲突，不伪装全成功，不回滚真实历史；部分冲突须解决或明确排除后进入发送摘要。沿现有 `documents.save`/来源和通知，不新建通用批写平台 |
| inputs / semantic-analysis / `ui/input-view.ts` | `slotAction`及现有runAnalysis/sourceIsCurrent/applyProposal；相关提议/缺证投影 | 只确认用户看过的原输入版本；切项目/旧proposal不套到新资料。人工通道保留，文字理解不冒充实际看图，真实图文须显式发送 |
| prompts `prompts.ts` / `domain/prompt.js` | 现有compile/compileAndSave/requestSnapshotOf消费结构决定及下文RequestReferenceSelection；系统准备/人工稿当前性投影 | 独占表达、来源与版本；UI不拼Prompt、不用最新头替原动作；自动更新沿已证渲染基线，真正脏稿不覆盖 |
| generation `generation.ts` | `prepareSummary({scope, mode}) → SummaryIntent`；`confirmAndRun({intent}) → started/blocked/stale` | scope由用户选择，不让view自己裁队列；意图带所见项目/会话/来源/配置/图序/版本、requested与实际scope及逐图排除理由。状态变更必须重看摘要，不能自动扩大集合 |
| generation | `prepareRework({shotId,candidateId,mode,problems,direction,promptChoice}) → ReworkIntent`；`confirmRework({intent}) → started/blocked/stale` | mode仅edit_candidate/regenerate_original；candidateId是固定问题候选，实际模型源由冻结refs定义。完整当前性、Prompt保存、授权预约、提交/观察/候选保全都在本owner |
| adoption `selection-adoption.ts` | 现有reportOf/reviewCandidate/adopt/取消/ack及只读selection身份 | 下游订阅生成候选，补确定性report失败可见；AI按需，不能自动采用。看到的ID＋原report/attempt/selection版本一起交采用事务 |
| delivery `review-delivery.ts` | 现有整套检查/gate/交付与项目ZIP命令 | 单快照项目包；交付消费原采用/候选/原动作冻结Prompt，重验现有围栏。不从DOM组manifest、不以空集绿项证明套图合格 |
| session / workspace / 四个views | 生命周期装配、订阅、局部导航、DOM/草稿/URL | 保持单向装配和释放；新布局复用owner，不机械切大文件。项目state仅派生缓存，业务硬门读真实记录，不把视图导航当商品状态 |
| gateway / 两个Image Adapter | 继续现有SubmitRequest与有限registry/Transport | 不加mask/negative_prompt/seed/新模型或另一编辑API；本次双模式是实际参考输入与Prompt不同，模型仍输出新整图。网关无业务持久化 |

`ReworkIntent`保留projectId/generation/shotId/所见Prompt/来源fence/有效profile/编译预览，并明确分为 `problemCandidate: {candidateId,documentId,version,assetSha256}`、`mode`、`references`（下节）和 `promptChoice`。不把问题候选ID当模型源，不回调DOM重新读取摘要。只读投影携带四个身份及已有忙碌/错误；来源不可见/不在原项目/Blob缺失或hash不符返回blocked，零POST，不回退别图。

Scope模式仍是原initial/failed_retry/explicit_new/rework，不另建队列。准备读/编译不持久化或收费；确认重验原所见意图和完整候选/输入/配置，按原事务授权消费/OCC预约每图action。已预约/Unknown不能另发；停止只停后续新增，已发送的原任务继续有限观察/保存。双击、跨tab和换项目复用原同领域围栏；旧action晚到仍按原项目保全。

