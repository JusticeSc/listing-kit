// @ts-check
/**
 * Product V2 项目工作区（V2.2.3）：参考图 → 商品资料 → 分析 → 商品理解。
 *
 * 职责边界：
 *  - 只通过 storage repository 读写浏览器 IndexedDB；对服务器只用两个无状态 API
 *    （/api/v2/capabilities 与 /api/v2/semantic/analyze）。
 *  - 事实权限由 domain 契约决定：模型只能 propose，写入一律走 applySlotAction；
 *    按钮集合由 slotPermissions / canConfirmSlot / canDeleteSlot / canAddSlot 派生。
 *  - 项目状态由对象关系派生（EMPTY → INTAKE_READY → UNDERSTANDING_REVIEW → PLAN_REVIEW），
 *    不在这里任意赋值，也不让状态标签暗示尚未接入的套图与生成。
 *  - 套图规划（V2.3.2）复用领域层 suite.js 的纯函数操作：顺序、必需/可选与增删复排
 *    全部由契约决定；界面只负责投影与保存，失败时旧计划与存储版本都不变。
 *  - “删除”槽位实现为 supersede：退出活动事实集合，历史版本保留。
 */
import { html, render } from "lit-html";

import {
  ATTEMPT_STATES,
  PRODUCT_INPUT_SCHEMA_VERSION,
  intakeReadiness,
  suitePlanSummary,
} from "./domain/index.js";
import { createGenerationModule } from "./generation.js";
import { consumptionFence, createProjectInputsModule } from "./project-inputs.js";
import { createPromptModule } from "./prompts.js";
import { createReviewDeliveryModule } from "./review-delivery.js";
import { createSelectionAdoptionModule } from "./selection-adoption.js";
import { createCompareView } from "./ui/compare-view.js";
import { createDeliveryView } from "./ui/delivery-view.js";
import { createGenerationView } from "./ui/generation-view.js";
import { createInputView } from "./ui/input-view.js";
import { createStageShell } from "./ui/stage-shell.js";
import {
  STATUS_TEXT,
  errorMessageOf,
} from "./ui/dom.js";
/**
 * 本文件 JSDoc 类型说明（V2.R7.5 调用方严格化，不改运行时）：
 *  - 领域/存储/会话/模型设置/生成/语义分析的权威类型分别来自
 *    `domain/type-contracts.js`、`storage/validate.js`、`session.js`、
 *    `model-settings.js`、`generation.js`、`semantic-analysis.js` 的 TS 声明；
 *    这里只做调用面的局部收口，不建第二套业务约定。
 *  - DOM 句柄一律收窄到真实元素类型（按 index.html 标签断言非空；全部 id 已核对存在，
 *    既有运行时守卫保留为纵深防御）。
 *  - 未经校验的持久化读出在消费边界收窄（`unknown` → 守卫/断言），不伪造形状；
 *    已校验记录在验证边界注明来源后允许收窄。
 * @typedef {import("./domain/type-contracts.js").FactSlot} FactSlot
 * @typedef {import("./domain/type-contracts.js").FactSlotValue} FactSlotValue
 * @typedef {import("./domain/type-contracts.js").SlotEntry} SlotEntry
 * @typedef {import("./domain/type-contracts.js").SlotStatus} SlotStatus
 * @typedef {import("./domain/type-contracts.js").ProductInput} ProductInput
 * @typedef {import("./domain/type-contracts.js").ProductReference} ProductReference
 * @typedef {import("./domain/type-contracts.js").ReferenceRole} ReferenceRole
 * @typedef {import("./domain/type-contracts.js").SemanticProposal} SemanticProposal
 * @typedef {import("./domain/type-contracts.js").SemanticAnalysisSource} SemanticAnalysisSource
 * @typedef {import("./domain/type-contracts.js").PlanShot} PlanShot
 * @typedef {import("./domain/type-contracts.js").SuitePlan} SuitePlan
 * @typedef {import("./domain/type-contracts.js").SuitePlanSummary} SuitePlanSummary
 * @typedef {import("./domain/type-contracts.js").StyleSpec} StyleSpec
 * @typedef {import("./domain/type-contracts.js").ShotSpec} ShotSpec
 * @typedef {import("./domain/type-contracts.js").PromptRecord} PromptRecord
 * @typedef {import("./domain/type-contracts.js").ConfirmationRecord} ConfirmationRecord
 * @typedef {import("./domain/type-contracts.js").ConfirmationSnapshot} ConfirmationSnapshot
 * @typedef {import("./domain/type-contracts.js").AttemptRecord} AttemptRecord
 * @typedef {import("./domain/type-contracts.js").AttemptState} AttemptState
 * @typedef {import("./domain/type-contracts.js").CandidateRecord} CandidateRecord
 * @typedef {import("./domain/type-contracts.js").SelectionRecord} SelectionRecord
 * @typedef {import("./domain/type-contracts.js").SelectionState} SelectionState
 * @typedef {import("./domain/type-contracts.js").SuiteReviewReport} SuiteReviewReport
 * @typedef {import("./ui/compare-view.js").CompareView} CompareView
 * @typedef {import("./ui/delivery-view.js").DeliveryView} DeliveryView
 * @typedef {import("./ui/generation-view.js").GenerationView} GenerationView
 * @typedef {import("./ui/input-view.js").InputView} InputView
 * @typedef {import("./domain/type-contracts.js").UnknownItem} UnknownItem
 * @typedef {import("./domain/type-contracts.js").GateFinding} GateFinding
 * @typedef {import("./domain/type-contracts.js").ImagePromptProfile} ImagePromptProfile
 * @typedef {import("./domain/type-contracts.js").DomainProblem} DomainProblem
 * @typedef {import("./storage/validate.js").ProjectRepository} ProjectRepository
 * @typedef {import("./storage/validate.js").StoredProjectRecord} StoredProjectRecord
 * @typedef {import("./storage/validate.js").StoredDocumentRecord} StoredDocumentRecord
 * @typedef {import("./storage/validate.js").StoredAssetRecord} StoredAssetRecord
 * @typedef {import("./session.js").Session} Session
 * @typedef {import("./session.js").ActionSnapshot} ActionSnapshot
 * @typedef {import("./model-settings.js").ModelSettings} ModelSettings
 * @typedef {import("./model-settings.js").EffectiveCapabilities} EffectiveCapabilities
 * @typedef {import("./generation.js").GenerationModule} GenerationModule
 * @typedef {import("./generation.js").PromptEntry} PromptEntry
 * @typedef {import("./semantic-analysis.js").AnalysisOutcome} AnalysisOutcome
 * @typedef {import("./semantic-analysis.js").SemanticRequestBody} SemanticRequestBody
 */

/**
 * 生成前确认单：domain/confirm.js `buildConfirmationSheet` 的确定性输出。领域层不导出该结构
 * 类型，工作区按实际消费的字段在本地收窄。
 * @typedef {{
 *   schema_version: number, total: number, ready: number, blocked: number, can_submit: boolean,
 *   platform: {platform_id: string, version: string, label?: string},
 *   provider: {provider_id: string, model_id: string, version: string, protocol: string, size: string,
 *              n: number, prompt_extend: boolean, watermark: boolean, output_format: string},
 *   external_summary: {model: string, size: string, n: number, prompt_extend: boolean, watermark: boolean,
 *                      output_format: string, reference_count: number, reference_roles: string[],
 *                      prompt_chars: number, on_image_text_language?: string, statement: string},
 *   shots: Array<ConfirmationSheetShot>,
 *   scope_shot_ids?: string[],
 *   blockers: Array<{shot_id: string, label: string, order: number, code: string, message: string,
 *                    fix: {region: string, shot_id: string|null, label: string, action: string}}>,
 *   risks: Array<{code: string, message: string, shot_id?: string, label?: string}>,
 * }} ConfirmationSheetView
 */

/**
 * 确认单中的单张图片行（字段与 confirm.js 输出逐项对应）。
 * @typedef {{
 *   shot_id: string, order: number, label: string, role_id: string|null, role_label: string|null,
 *   intent: string|null, template_id: string|null, required: boolean, satisfied: boolean,
 *   prompt: {version: number|null, hash: string|null, chars: number|null},
 *   references: Array<{role: string, sha256_prefix: string}>,
 *   risks: Array<{code: string, message: string, shot_id: string, label: string}>,
 *   blockers: Array<{code: string, message: string,
 *                    fix: {region: string, shot_id: string|null, label: string, action: string}}>,
 * }} ConfirmationSheetShot
 */

/**
 * 当前编辑中的商品资料：保存/出站前各字段都已落成具体值（不再是可选项）。
 * @typedef {{schema_version: number, product_name: string, description: string, selling_points: string[], focus: string, references: ProductReference[]}} CompleteProductInput
 */

/**
 * 元素表：按 index.html 实际标签收窄；全部 id 均在 index.html 中核对存在，
 * 因此句柄为非空（缺失即装配错误）；bind/render 的既有运行时守卫保留为纵深防御。
 * @typedef {object} WorkspaceElements
 * @property {HTMLElement} error
 * @property {HTMLElement} scope
 * @property {HTMLElement} intakeAnchor
 * @property {HTMLElement} analyzeAnchor
 * @property {HTMLElement} slotsAnchor
 * @property {HTMLElement} suiteAnchor
 * @property {HTMLElement} specsAnchor
 * @property {HTMLElement} refsAnchor
 * @property {HTMLElement} promptLocked
 * @property {HTMLElement} promptEditor
 * @property {HTMLElement} localPreparationStatus
 * @property {HTMLDetailsElement} promptDetails
 * @property {HTMLElement} promptError
 * @property {HTMLElement} confirmLocked
 * @property {HTMLElement} confirmEditor
 * @property {HTMLElement} confirmError
 * @property {HTMLElement} attemptLocked
 * @property {HTMLElement} attemptEditor
 * @property {HTMLElement} attemptError
 * @property {HTMLElement} comparePanel
 * @property {HTMLDialogElement} imageZoomDialog
 * @property {HTMLElement} reworkPanel
 * @property {HTMLElement} generateError
 * @property {HTMLElement} stageNav
 * @property {HTMLElement} stagePanels
 * @property {HTMLElement} stageSummary
 * @property {HTMLButtonElement} stageNextPlan
 * @property {HTMLElement} stageNextPlanNote
 * @property {HTMLButtonElement} stageNextMake
 * @property {HTMLElement} stageNextMakeNote
 * @property {HTMLButtonElement} stageNextDeliver
 * @property {HTMLElement} stageNextDeliverNote
 * @property {HTMLElement} taskList
 * @property {HTMLElement} shotExecution
 * @property {HTMLElement} suiteReviewCard
 * @property {HTMLElement} deliveryCard
 */

const SCOPE_TEXT = "资料与事实 → 方案 → 制作与审图 → 交付；外发由你明确确认，交付仍需通过当前门禁。";

/**
 * 工作区工厂：会话提供 repository/session/onProjectChanged；模型设置由外层装配透传。
 * 返回句柄只暴露 open/close/isOpen/setProject，不感知内部渲染状态。
 * @param {{repository: ProjectRepository, session: Session|null, modelSettings: ModelSettings, onProjectChanged?: ((project: StoredProjectRecord|null) => void)|null}} args
 * @returns {import("./session.js").WorkspaceHandle}
 */
export function createWorkspace({ repository, session = null, modelSettings, onProjectChanged = null }) {
  if (!session) {
    throw new Error("createWorkspace 需要 session（V2.R3.3 会话 Module）。");
  }
  /** @type {WorkspaceElements} */
  const elements = {
    error: /** @type {HTMLElement} */ (document.getElementById("workspace-error-mount")),
    scope: /** @type {HTMLElement} */ (document.getElementById("project-scope")),
    intakeAnchor: /** @type {HTMLElement} */ (document.getElementById("intake-card")),
    analyzeAnchor: /** @type {HTMLElement} */ (document.getElementById("analyze-card")),
    slotsAnchor: /** @type {HTMLElement} */ (document.getElementById("slots-card")),
    suiteAnchor: /** @type {HTMLElement} */ (document.getElementById("suite-card")),
    specsAnchor: /** @type {HTMLElement} */ (document.getElementById("specs-section")),
    refsAnchor: /** @type {HTMLElement} */ (document.getElementById("references-card")),
    promptLocked: /** @type {HTMLElement} */ (document.getElementById("prompt-locked")),
    promptEditor: /** @type {HTMLElement} */ (document.getElementById("prompt-editor")),
    localPreparationStatus: /** @type {HTMLElement} */ (document.getElementById("local-preparation-status")),
    promptDetails: /** @type {HTMLDetailsElement} */ (document.getElementById("prompt-details")),
    promptError: /** @type {HTMLElement} */ (document.getElementById("prompt-error-mount")),
    confirmLocked: /** @type {HTMLElement} */ (document.getElementById("confirm-locked")),
    confirmEditor: /** @type {HTMLElement} */ (document.getElementById("confirm-editor")),
    confirmError: /** @type {HTMLElement} */ (document.getElementById("confirm-error-mount")),
    attemptLocked: /** @type {HTMLElement} */ (document.getElementById("attempt-locked")),
    attemptEditor: /** @type {HTMLElement} */ (document.getElementById("attempt-editor")),
    attemptError: /** @type {HTMLElement} */ (document.getElementById("attempt-error-mount")),
    comparePanel: /** @type {HTMLElement} */ (document.getElementById("compare-panel")),
    imageZoomDialog: /** @type {HTMLDialogElement} */ (document.getElementById("image-zoom-dialog")),
    reworkPanel: /** @type {HTMLElement} */ (document.getElementById("rework-panel")),
    generateError: /** @type {HTMLElement} */ (document.getElementById("generate-error-mount")),
    stageNav: /** @type {HTMLElement} */ (document.getElementById("stage-nav")),
    stagePanels: /** @type {HTMLElement} */ (document.getElementById("stage-panels")),
    stageSummary: /** @type {HTMLElement} */ (document.getElementById("stage-summary")),
    stageNextPlan: /** @type {HTMLButtonElement} */ (document.getElementById("stage-next-plan")),
    stageNextPlanNote: /** @type {HTMLElement} */ (document.getElementById("stage-next-plan-note")),
    stageNextMake: /** @type {HTMLButtonElement} */ (document.getElementById("stage-next-make")),
    stageNextMakeNote: /** @type {HTMLElement} */ (document.getElementById("stage-next-make-note")),
    stageNextDeliver: /** @type {HTMLButtonElement} */ (document.getElementById("stage-next-deliver")),
    stageNextDeliverNote: /** @type {HTMLElement} */ (document.getElementById("stage-next-deliver-note")),
    taskList: /** @type {HTMLElement} */ (document.getElementById("task-list-mount")),
    shotExecution: /** @type {HTMLElement} */ (document.getElementById("shot-execution")),
    suiteReviewCard: /** @type {HTMLElement} */ (document.getElementById("suite-review-card")),
    deliveryCard: /** @type {HTMLElement} */ (document.getElementById("delivery-card")),
  };

  // 交付视图（设计 §2.1 第四个视图）持 DOM、展开与自己的对象 URL；先声明后装配：
  // 下面的 onSelect 与两个 Module 的 changed 都只在装配完成后触发，不在装配期回调。
  /** @type {DeliveryView|null} */
  let deliveryView = null;
  // 输入视图（设计 §10.1 第一个视图）持资料/理解/方案的 DOM 与就地状态；同样先声明后装配。
  /** @type {InputView|null} */
  let inputView = null;
  // 生成视图（设计 §10.1 第二个视图）持 Prompt/确认/尝试三区的 DOM 与命令；同样先声明后装配。
  /** @type {GenerationView|null} */
  let generationView = null;
  // 审核视图（设计 §10.1 第三个视图）持比较/返工/采用三区的 DOM 与就地状态；同样先声明后装配。
  /** @type {CompareView|null} */
  let compareView = null;

  const stageShell = createStageShell({
    nav: /** @type {HTMLElement} */ (elements.stageNav),
    panelRoot: /** @type {HTMLElement} */ (elements.stagePanels),
    summary: /** @type {HTMLElement} */ (elements.stageSummary),
    onSelect: (/** @type {string} */ id) => {
      if (id === "deliver") deliveryView?.requestGateRefresh();
      // intake 是默认停靠阶段，进入它不等于用户要求建槽位：核心事实的建立仍由
      // 「人工填写事实」或槽位卡片的显式按钮触发（与本轮之前进入 intake 的语义一致）。
      if (id === "make" && projectId) void generationView?.prepareSystemPrompts();
    },
  });

  /** @type {StoredProjectRecord|null} */
  let project = null;
  /** @type {string|null} */
  let projectId = null;
  /** @type {EffectiveCapabilities|null} */
  let capabilities = null;
  /** @type {import("./domain/type-contracts.js").BriefReadiness["blocking"]} */
  let understandingBlocking = [];
  /** @type {unknown} */
  let understandingError = null;
  /** @type {boolean} */
  let understandingReady = false;
  /** @type {Map<string, string>} */
  let previewUrls = new Map();
  /** @type {boolean} */
  let bound = false;
  // 视图在装配时即可读取投影；所有读取闭包依赖先完成初始化。
  // R3.3：动作身份冻结的本地别名——所有状态变更动作统一经 session.beginAction()。
  /** @type {() => ActionSnapshot} */
  const beginAction = () => session.beginAction();

  // 输入面唯一所有者（包04 收口）：资料/事实/方案/风格/单图规格与语义分析执行都在这里，
  // workspace 只装配读取视图草稿的边界，不持有第二份输入状态。
  const inputs = createProjectInputsModule({
    repository,
    beginAction,
    settings: modelSettings,
    capabilities: () => capabilities,
    projectIdReader: () => projectId,
    projectNameReader: () => (project && project.name) || "",
    draftInput: () => inputView?.draftInputPayload() ?? ({
      schema_version: PRODUCT_INPUT_SCHEMA_VERSION,
      product_name: "", description: "", selling_points: [], focus: "", references: [],
    }),
  });
  /** 跨 Module 只读文档投影：唯一来源是 inputs.sources()（不传闭包、不留第二份投影）。 */
  const projectSources = () => inputs.sources();

  const prompts = createPromptModule({
    repository: /** @type {import("./storage/validate.js").ProjectRepository} */ (/** @type {unknown} */ (repository)),
    beginAction, sources: projectSources,
    imageEnvironment: () => /** @type {unknown} */ (capabilities && capabilities.images),
  });
  // 装配顺序固定为 prompts → generation → selection → delivery（设计§10.1）。
  // selection/delivery 的 generation 依赖是已装配实例，不传 null 占位。
  // 授权队列/scope/mode 的唯一所有者是 generation（设计§2.1）；确认单投影归 prompts。
  /** @type {GenerationModule} */
  const generation = createGenerationModule({
    // workspace 的 repository 即 storage ProjectRepository（权威面）；生成 Module 只消费
    // 其 documents.save/get/listLatest/listVersions + assets.get/put 子集，这里按消费面收窄（同一运行时对象）。
    repository: /** @type {import("./generation.js").GenerationRepository} */ (/** @type {unknown} */ (repository)),
    beginAction: beginAction,
    projectIdReader: () => projectId,
    environmentReader: (saved) => modelSettings.environmentFor(saved),
    requestHeaders: /** @param {import("./model-settings.js").Purpose} purpose */ (purpose, providerId, source) => modelSettings.headers(purpose, providerId, source),
    suitePlanReader: () => inputs.suitePlan(),
    suiteSummaryReader: () => {
      const plan = inputs.suitePlan();
      return plan ? /** @type {SuitePlanSummary} */ (suitePlanSummary(plan, inputs.suiteContext())) : null;
    },
    promptEntryReader: (shotId, version) => prompts.entryOf(shotId, version ?? null),
    confirmationReader: (shotId) => generation.confirmationFor(shotId),
    promptBasisReader: (shotId, provider) => prompts.basis(shotId, provider, projectSources()),
    fenceReader: (shotId) => consumptionFence(projectSources(), [shotId]),
    referenceSourceReader: () => inputs.references().map((item) => ({
      role: item.role, sha256: item.asset_sha256,
    })),
    intakeVersionReader: () => projectSources().intakeVersion,
    shotSpecReader: (shotId) => projectSources().shotSpecs[shotId] || null,
    promptsSheet: (ids) => prompts.sheet(ids ?? null),
    imageEnvironment: (saved) => /** @type {unknown} */ (saved ?? modelSettings.imageEnvironment()),
    promptAbility: {
      compile: (shotId, options) => prompts.compile(shotId, options),
      previewManualForRework: (shotId, options) => prompts.previewManualForRework(shotId, options),
      compileAndSave: (shotId, options) => prompts.compileAndSave(shotId, options),
      rebaseManualForRework: (shotId, options) => prompts.rebaseManualForRework(shotId, options),
    },
  });
  const selectionAdoption = createSelectionAdoptionModule({
    repository: /** @type {import("./storage/validate.js").ProjectRepository} */ (/** @type {unknown} */ (repository)),
    generation,
    prompts,
    settings: modelSettings,
    beginAction, sources: projectSources,
  });
  const reviewDelivery = createReviewDeliveryModule({
    repository: /** @type {import("./storage/validate.js").ProjectRepository} */ (/** @type {unknown} */ (repository)),
    generation,
    adoption: selectionAdoption,
    settings: modelSettings,
    beginAction, sources: projectSources,
  });

  // 交付视图只持 DOM、展开与自己的对象 URL；逐图采用状态、门禁、整套结论与两类导出
  // 都读 owner 投影，视图不写库、不重算判定、不组 manifest/ZIP。
  deliveryView = createDeliveryView({
    elements: {
      suiteReviewCard: elements.suiteReviewCard,
      deliveryCard: elements.deliveryCard,
    },
    deps: {
      reviewDelivery,
      selectionAdoption,
      inputs,
      beginAction,
      currentProjectId: () => projectId,
      capabilities: () => capabilities,
      shotSummaries: shotSummariesNow,
      shotLabelOf,
      localizeShotIds,
      selectionStateOf: (/** @type {string} */ shotId) => compareView?.selectionStateOf(shotId) ?? "none",
      selectStage: (/** @type {string} */ id) => stageShell.select(id),
      // 跨视图定位：审核卡/整套检查按钮的 DOM 归审核视图与交付视图各自持有，
      // 交付视图只发意图，滚动与焦点收敛在这里（P5 不留跨视图 querySelector）。
      focusReviewShot: (/** @type {string} */ shotId) => focusCompareEntry(shotId),
      focusSuiteCheck: () => {
        const button = /** @type {HTMLButtonElement|null} */ (elements.suiteReviewCard.querySelector("#suite-review-run"));
        if (!button) return;
        button.scrollIntoView({ block: "center" });
        button.focus({ preventScroll: true });
      },
    },
  });

  // 输入视图只持资料/理解/方案的 DOM、展开与就地编辑态；资料/事实/方案/风格/单图规格的
  // 读写都在 inputs（唯一所有者），落库/派生/跨视图刷新经下面的窄回调回到工作区。
  inputView = createInputView({
    elements: {
      intakeAnchor: elements.intakeAnchor,
      analyzeAnchor: elements.analyzeAnchor,
      slotsAnchor: elements.slotsAnchor,
      suiteAnchor: elements.suiteAnchor,
      specsAnchor: elements.specsAnchor,
      refsAnchor: elements.refsAnchor,
    },
    deps: {
      inputs,
      beginAction,
      currentProjectId: () => projectId,
      capabilities: () => capabilities,
      understandingBlocking: () => understandingBlocking,
      readAsset: (/** @type {string} */ pid, /** @type {string} */ sha256) => repository.assets.get(pid, sha256),
      deriveState: deriveAndApplyState,
      renderWorkspace: renderAll,
      renderGenerationSections,
      renderHeader: () => renderHeaderText(project),
      refreshStageShell,
      selectStage: (/** @type {string} */ id, /** @type {{focusHeading?: boolean}|undefined} */ options) => stageShell.select(id, options),
      reportError: handleInternalError,
      localizeSlotTerms,
      suiteBlockingText,
    },
  });

  // 生成视图只持 Prompt/确认/尝试三区的 DOM 与命令；Prompt 版本/依据读写都在 prompts、
  // 确认队列与尝试链都在 generation，采用记录只读投影走 selectionAdoption，
  // 落库/派生/跨区渲染经下面的窄回调回到工作区。
  generationView = createGenerationView({
    elements: {
      promptLocked: elements.promptLocked,
      promptEditor: elements.promptEditor,
      localPreparationStatus: elements.localPreparationStatus,
      promptDetails: elements.promptDetails,
      promptError: elements.promptError,
      generateError: elements.generateError,
      confirmLocked: elements.confirmLocked,
      confirmEditor: elements.confirmEditor,
      confirmError: elements.confirmError,
      attemptLocked: elements.attemptLocked,
      attemptEditor: elements.attemptEditor,
      attemptError: elements.attemptError,
      taskList: elements.taskList,
      shotExecution: elements.shotExecution,
    },
    deps: {
      prompts,
      inputs,
      generation,
      selectionAdoption,
      modelSettings,
      beginAction,
      currentProjectId: () => projectId,
      capabilities: () => capabilities,
      understandingReady: () => understandingReady,
      deriveState: deriveAndApplyState,
      selectStage: (stageId) => stageShell.select(stageId),
      shotLabelOf,
      ensurePreviewUrl,
      viewedShotId: () => compareView?.currentShotId() ?? null,
      isComparing: (/** @type {string} */ shotId) => compareView?.isComparing(shotId) ?? false,
      openCompare: (/** @type {string} */ shotId, /** @type {{focus?: boolean}|undefined} */ options) => compareView?.openCompare(shotId, options),
      renderCompare: () => compareView?.renderCompare(),
      refreshDerived,
      localizeSlotTerms,
      suiteBlockingText,
      suffixedErrorMessage: errorMessageSuffixed,
    },
  });

  // 审核视图只持比较/返工/采用三区的 DOM 与就地状态；候选/报告读写都在 generation /
  // selectionAdoption（唯一所有者），Prompt 版本/编译在 prompts，跨区刷新经下面的窄回调回到工作区。
  compareView = createCompareView({
    elements: {
      comparePanel: elements.comparePanel,
      reworkPanel: elements.reworkPanel,
      imageZoomDialog: elements.imageZoomDialog,
    },
    deps: {
      inputs,
      generation,
      selectionAdoption,
      beginAction,
      currentProjectId: () => projectId,
      shotLabelOf,
      shortTime: (/** @type {unknown} */ iso) => generationView?.shortTime(iso) ?? "",
      ensurePreviewUrl,
      selectStage: (/** @type {string} */ stageId) => stageShell.select(stageId),
      focusReviewEntry: focusCompareEntry,
      renderAttempts: () => generationView?.renderAttempts(),
      showAttemptError: (/** @type {string} */ message) => { generationView?.showAttemptError(message); },
      renderPrompts: () => generationView?.renderPrompts(),
      renderConfirm: () => generationView?.renderConfirm(),
      onViewedShotChanged: (/** @type {string|null} */ shotId) => {
        if (!shotId) return;
        generationView?.onViewedShotChanged(shotId);
      },
      readAsset: (/** @type {string} */ pid, /** @type {string} */ sha256) => repository.assets.get(pid, sha256),
      deriveState: deriveAndApplyState,
      reportError: handleInternalError,
      suffixedErrorMessage: errorMessageSuffixed,
    },
  });
  compareView.bind();
  // 业务owner只发布投影变化；工作区一次订阅并路由到视图，不把DOM回调注入owner。
  inputs.subscribe(() => {
    void deriveAndApplyState().then(() => {
      inputView?.renderAnalyze();
      inputView?.renderIntake();
      renderHeaderText(project);
    }).catch(handleInternalError);
  });
  generation.subscribe(() => { generationView?.applyNotice(); });
  selectionAdoption.subscribe(() => {
    deliveryView?.render();
    generationView?.renderAttempts();
  });
  reviewDelivery.subscribe(() => { deliveryView?.render(); });
  // Prompt 版本/历史/准备状态 → prompts Module；确认队列/scope/mode → generation Module；
  // 采用记录 → selectionAdoption Module；整套报告/门禁/交付包 → reviewDelivery Module；
  // 资料/事实/方案/风格/单图规格 → project-inputs Module（唯一所有者）。
  // 本闭包只保留视图装配、生命周期、导航与跨 owner 协调。
  /* ------------------------------------------------------ 公共读写与工具 */

  /**
   * 有后缀的抛出信息：有 message 即 message + suffix，否则原样返回 fallback（与旧三元输出一致）。
   * @param {unknown} error
   * @param {string} fallback
   * @param {string} suffix
   * @returns {string}
   */
  function errorMessageSuffixed(error, fallback, suffix) {
    if (error instanceof Error && typeof error.message === "string" && error.message) return error.message + suffix;
    if (error !== null && typeof error === "object" && "message" in error
      && typeof error.message === "string" && error.message) return error.message + suffix;
    return fallback;
  }


  /**
   * @returns {void}
   */
  function revokePreviewUrls() {
    for (const url of previewUrls.values()) URL.revokeObjectURL(url);
    previewUrls = new Map();
  }


  /** @param {string} message 工作区协调错误（不拥有各视图内部错误）。 */
  function renderWorkspaceError(message) {
    render(html`<p id="workspace-error" class="error" role="alert" ?hidden=${!message}>${message}</p>`, elements.error);
  }

  /**
   * @param {unknown} error
   * @returns {void}
   */
  function handleInternalError(error) {
    renderWorkspaceError(errorMessageOf(error, "操作没有完成，请重试。"));
  }

  /**
   * @returns {Promise<void>}
   */
  async function loadCapabilities() {
    capabilities = await modelSettings.refresh();
  }

  /**
   * 渲染层本地化：domain 的阻塞消息只认 slot_id 与英文状态词，展示前换成用户认得的
   * 槽位名与中文状态（V2.6.9 走查发现「关键槽位 product_name 仍是 proposed」直接上屏）。
   */
  /**
   * @param {unknown} message
   * @returns {string}
   */
  function localizeSlotTerms(message) {
    let out = String(message == null ? "" : message);
    const labels = inputs.slotEntries()
      .map((entry) => ({
        id: String((entry.slot && entry.slot.slot_id) || ""),
        label: String((entry.slot && entry.slot.label) || ""),
      }))
      .filter((item) => item.id && item.label && item.label !== item.id)
      .sort((left, right) => right.id.length - left.id.length);
    for (const item of labels) {
      if (out.indexOf(item.id) >= 0) out = out.split(item.id).join(item.label);
    }
    for (const [status, text] of Object.entries(STATUS_TEXT)) {
      if (out.indexOf(status) >= 0) out = out.split(status).join(text);
    }
    return out;
  }

  /**
   * 套图依据缺口的连接文本（与 domain/confirm.js blockingText 同形状输入，只做展示连接，
   * 不做门禁判定）。提示词分区仍在使用，故实现留在工作区，输入视图经依赖注入复用同一份。
   * @param {import("./domain/type-contracts.js").DependencyBlocking[]|null|undefined} blocking
   * @returns {string}
   */
  function suiteBlockingText(blocking) {
    return (blocking || []).map((item) => item.reason || "").join("；");
  }


  /* ------------------------------------------------------------ 生成执行 */

  /** 预览 URL 缓存：每个候选一个 object URL，关闭项目时统一撤销。
   * @param {string} shotId
   * @param {string} actionId
   * @param {string} assetSha256
   * @returns {Promise<string|null>}
   */
  async function ensurePreviewUrl(shotId, actionId, assetSha256) {
    const key = shotId + ":" + actionId;
    const cached = previewUrls.get(key);
    if (cached) return cached;
    const pid = projectId;
    if (!pid) return null;
    const asset = await repository.assets.get(pid, assetSha256);
    if (pid !== projectId || !asset || !(asset.blob instanceof Blob)) return null;
    const url = URL.createObjectURL(asset.blob);
    previewUrls.set(key, url);
    return url;
  }

  /**
   * @param {string} shotId
   * @returns {string}
   */
  function shotLabelOf(shotId) {
    const summary = inputs.suitePlan() ? suitePlanSummary(inputs.suitePlan(), inputs.suiteContext()) : null;
    const item = (summary ? summary.shots : []).find((shot) => shot.shot_id === shotId);
    return item ? item.label : shotId;
  }

  /**
   * 渲染层本地化：domain 的门禁/报告文案里 shot_id 是机器标识，展示时替换成用户认得的图名。
   * 只改投影、不改 domain 数据（导出与存档仍保留 shot_id）；长 id 先替换，避免互为子串时误伤。
   */
  /**
   * @param {unknown} text
   * @returns {string}
   */
  function localizeShotIds(text) {
    let out = String(text == null ? "" : text);
    const summary = inputs.suitePlan() ? suitePlanSummary(inputs.suitePlan(), inputs.suiteContext()) : null;
    const shots = (summary ? summary.shots : []).slice().sort((left, right) =>
      String(right.shot_id).length - String(left.shot_id).length);
    for (const item of shots) {
      if (item && item.shot_id && out.indexOf(item.shot_id) >= 0) {
        out = out.split(item.shot_id).join(item.label || item.shot_id);
      }
    }
    return out;
  }

  /**
   * 焦点只能落到用户当前看得见的入口。B4 四段分屏：比较/审核区住在「制作与审图」,
   * 任务行与查看对象在同屏左侧。顺序：任务行查看按钮 → 本图执行区入口 →
   * 阶段条当前阶段（始终可见）。B4 起比较面板不再输出 `.review-card` 列表,
   * 因此旧的面板内卡片入口分支已删除；比较区打开时由比较视图自己管候选页签焦点。
   * @param {string|null} shotId
   * @returns {void}
   */
  function focusCompareEntry(shotId) {
    const isVisible = (/** @type {HTMLElement|null|undefined} */ node) => Boolean(node && node.offsetParent !== null);
    const taskEntry = shotId && elements.taskList
      ? /** @type {HTMLButtonElement|null} */ (elements.taskList.querySelector(
        'button[data-view-shot="' + shotId + '"]'))
      : null;
    if (taskEntry && isVisible(taskEntry)) { taskEntry.focus(); return; }
    const attemptEntry = shotId && elements.shotExecution
      ? /** @type {HTMLButtonElement|null} */ (elements.shotExecution.querySelector(
        'button[data-compare-action="' + shotId + '"]'))
      : null;
    const stageButton = /** @type {HTMLButtonElement|null} */ (elements.stageNav.querySelector("[data-stage-nav].is-current"));
    const target = [attemptEntry, stageButton]
      .find(isVisible);
    if (target) target.focus();
  }

  /**
   * @param {StoredProjectRecord|null} projectRecord
   * @returns {void}
   */
  function renderHeaderText(projectRecord) {
    const state = projectRecord ? projectRecord.state : null;
    const text = state === "READY_TO_GENERATE"
      ? "生成前确认已通过：可整套或逐张提交，并按任务编号核对进度；审核、返工与采用后，按当前交付门禁处理整套检查和导出。"
      : state === "PLAN_REVIEW"
        ? "商品理解已就绪，可以编辑套图规划、规格、Prompt 与生成前确认；通过确认后才能提交生成。"
        : SCOPE_TEXT;
    render(html`${text}`, elements.scope);
  }

  /**
   * @returns {Promise<void>}
   */
  async function deriveAndApplyState() {
    const action = beginAction();
    if (!action.projectId) return;
    await inputs.deriveState();
    const understood = inputs.understanding();
    understandingBlocking = understood.blocking;
    understandingError = understood.error;
    understandingReady = understood.ready;
    const entryCount = inputs.slotEntries().length;
    const draftPayload = inputs.intakeSnapshot();
    // 「确认是否仍当前」的判定输入包含图像能力投影（generation.isConfirmedShotCurrent →
    // environmentFor(saved) → imagePromptProfile）。模型设置刷新窗口内 capabilities=null、
    // imageEnvironments 已清空（model-settings.refresh 开头），此时该判定恒为「不当前」——
    // 那是「还不知道」，不是「已失效」。把不确定当失效会回写 PLAN_REVIEW，而授权其实没过期
    // （boot 路径已单独规避同一竞态：loadWorkspace「能力到位后再做唯一一次状态派生」）。
    // 这里是同一收口的唯一实现处：判定输入不确定时保留既有派生结论，不写库、不伪造「需重新确认」。
    const confirmationDecidable = !modelSettings.refreshing;
    const state = entryCount === 0
      ? (intakeReadiness(draftPayload).ready ? "INTAKE_READY" : "EMPTY")
      : (understandingReady
        ? (confirmationDecidable
          ? (generationView?.confirmationIsCurrent() ? "READY_TO_GENERATE" : "PLAN_REVIEW")
          : null)
        : "UNDERSTANDING_REVIEW");
    if (state !== null && project && project.state !== state) {
      try {
        // 状态写按冻结项目落库（保存派生结论）；已过期动作不回写界面状态。
        const updated = await repository.projects.setState(action.projectId, state);
        if (action.alive()) {
          project = updated;
          if (onProjectChanged) onProjectChanged(project);
        }
      } catch (error) {
        if (action.alive()) {
          renderWorkspaceError(errorMessageOf(error, "状态写回失败。"));
        }
      }
    }
    if (action.alive()) renderHeaderText(project);
  }

  /* ---------------------------------------------------------- 四阶段投影与交付门禁（B4） */

  /**
   * @returns {import("./domain/type-contracts.js").SuitePlanSummary["shots"]}
   */
  function shotSummariesNow() {
    return inputs.suitePlan() ? suitePlanSummary(inputs.suitePlan(), inputs.suiteContext()).shots : [];
  }

  /**
   * 每个阶段的完成 / 可用 / 摘要只在这里派生一次；外壳只负责画出来。
   * available=false 表示阶段条上的入口不可用（前置未完成），不是错误。
   * B4 四段：资料与事实（资料+理解合并）、方案、制作与审图（生成+审核返工合并）、交付。
   * @returns {Record<string, {status?: string, summary?: string, hint?: string, available?: boolean}>}
   */
  function computeStageStates() {
    const shots = shotSummariesNow();
    const entries = inputs.slotEntries();
    const confirmed = entries.filter((item) => item.slot.status === "confirmed").length;
    const unknownSlots = entries.filter((item) => item.slot.status === "unknown").length;
    const hasSlots = entries.length > 0;
    const withCandidate = shots.filter((shot) =>
      Boolean(generation.latestStoredCandidateOf(shot.shot_id)));
    const settled = shots.filter((shot) => {
      if (generation.latestStoredCandidateOf(shot.shot_id)) return true;
      const latest = generation.latestAttemptOf(shot.shot_id);
      return Boolean(latest && latest.record.state === ATTEMPT_STATES.failed);
    });
    const unknownAttempts = shots.filter((shot) => {
      const latest = generation.latestAttemptOf(shot.shot_id);
      return Boolean(latest && latest.record.state === ATTEMPT_STATES.unknown);
    });
    const requiredShots = shots.filter((shot) => shot.required === true);
    const requiredSelected = requiredShots.filter((shot) => (compareView?.selectionStateOf(shot.shot_id) ?? "none") === "current");
    const selectedShots = shots.filter((shot) => (compareView?.selectionStateOf(shot.shot_id) ?? "none") === "current");
    const projectName = project ? project.name : "";
    const referenceCount = inputs.references().length;
    const intakeSummary = [projectName, referenceCount ? "参考图 " + referenceCount + " 张" : ""]
      .filter(Boolean).join(" · ");
    const factsSummary = understandingReady
      ? "已确认 " + confirmed + " 项" + (unknownSlots ? " · 未知 " + unknownSlots + " 项" : "")
      : "事实待确认";

    return {
      intake: {
        available: true,
        status: hasSlots ? "complete" : "current",
        hint: hasSlots ? "" : "上传参考图，自己填写商品事实；AI 理解是可选辅助。",
        summary: hasSlots ? [intakeSummary, factsSummary].filter(Boolean).join(" · ") : "",
      },
      plan: {
        available: understandingReady,
        status: shots.length ? "complete" : "current",
        hint: understandingReady ? "" : "先确认核心事实。",
        summary: shots.length ? shots.length + " 张图片任务" : "",
      },
      make: {
        available: shots.length > 0,
        status: (shots.length > 0 && shots.length === settled.length && selectedShots.length === shots.length)
          ? "complete" : "current",
        hint: shots.length ? "" : "先生成套图方案。",
        summary: shots.length
          ? "候选 " + withCandidate.length + "/" + shots.length
            + " · 已采用 " + selectedShots.length + "/" + shots.length
            + (unknownAttempts.length ? " · " + unknownAttempts.length + " 张待核对" : "")
          : "",
      },
      deliver: {
        available: withCandidate.length > 0,
        status: "current",
        hint: withCandidate.length ? "" : "先生成候选。",
        summary: shots.length
          ? "必需图已采用 " + requiredSelected.length + "/" + requiredShots.length
          : "",
      },
    };
  }

  /** 默认停靠：最靠后的“可用且未完成”的阶段；全部完成则停在交付。
   * @param {Record<string, {status?: string, summary?: string, hint?: string, available?: boolean}>|null} [states]
   * @returns {string}
   */
  function defaultStageId(states = null) {
    const map = states || computeStageStates();
    for (const id of ["intake", "plan", "make", "deliver"]) {
      if (map[id] && map[id].available !== false && map[id].status !== "complete") return id;
    }
    return "deliver";
  }

  /** 阶段底部的推进按钮：禁用时说明缺什么；不改变任何数据。
   * @param {Record<string, {status?: string, summary?: string, hint?: string, available?: boolean}>} states
   * @returns {void}
   */
  function renderStageFoot(states) {
    const shots = shotSummariesNow();
    elements.stageNextPlan.disabled = false;
    elements.stageNextPlanNote.textContent = shots.length
      ? "" : "先生成或添加至少一张图片任务。";
    const candidates = states && states.make ? states.make.available : false;
    elements.stageNextMake.disabled = false;
    elements.stageNextMakeNote.textContent = candidates ? "" : "先产生至少一张候选。";
    const requiredShots = shots.filter((shot) => shot.required === true);
    const pending = requiredShots.filter((shot) => (compareView?.selectionStateOf(shot.shot_id) ?? "none") !== "current");
    elements.stageNextDeliver.disabled = false;
    elements.stageNextDeliverNote.textContent = shots.length === 0
      ? "先生成候选。"
      : (pending.length ? "还有 " + pending.length + " 张必需图没有采用候选。" : "");
  }

  /**
   * @param {{reset?: boolean}} [options]
   * @returns {Record<string, {status?: string, summary?: string, hint?: string, available?: boolean}>}
   */
  function refreshStageShell({ reset = false } = {}) {
    const states = computeStageStates();
    if (reset) stageShell.select(defaultStageId(states));
    stageShell.update(states, { fallback: defaultStageId(states) });
    renderStageFoot(states);
    return states;
  }

  /**
   * 业务状态变化后的统一收尾：派生投影（审核列表 / 交付门禁）与阶段外壳一起刷新。
   * 所有会改变套图、Attempt、候选与采用状态的处理函数都经 renderAttempts 落到这里，
   * 避免阶段条与阶段脚注停留在旧状态（例如生成推荐方案后仍显示「先生成或添加至少一张图片」）。
   * @returns {Record<string, {status?: string, summary?: string, hint?: string, available?: boolean}>}
   */
  function refreshDerived() {
    deliveryView?.render();
    deliveryView?.requestGateRefresh();
    return refreshStageShell();
  }


  /**
   * @returns {void}
   */
  function renderAll() {
    renderWorkspaceError(understandingError
      ? "商品理解投影失败：" + errorMessageOf(understandingError, "未知错误")
      : "");
    inputView?.render();
    renderGenerationSections();
    renderHeaderText(project);
    refreshDerived();
  }

  /** 生成/确认/尝试三个分区的同轮刷新：全量渲染与输入侧命令收尾共用一处，避免三份写法。 */
  function renderGenerationSections() {
    generationView?.render();
  }

  /**
   * @returns {void}
   */
  function bind() {
    if (bound) return;
    bound = true;
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") inputView?.saveIntakeNow().catch(() => {});
    });
    // 真脏草稿才拦截刷新：Prompt 全文键入（与呈现基线不同）＋资料草稿（与已保存内容不同）
    // ＋比较区返工草稿；绝不拿 DOM 文本与刚落库的系统文本比对。
    window.addEventListener("beforeunload", (event) => {
      if (!hasUnsavedDraftsNow()) return;
      event.preventDefault();
      // 兼容旧浏览器：returnValue 非空才弹确认框。
      event.returnValue = "";
    });
    elements.stageNextPlan.addEventListener("click", () => {
      stageShell.select("plan", { focusHeading: true });
    });
    elements.stageNextMake.addEventListener("click", () => {
      stageShell.select("make", { focusHeading: true });
    });
    elements.stageNextDeliver.addEventListener("click", () => {
      stageShell.select("deliver", { focusHeading: true });
    });
  }

  /** 刷新保护判据：各视图/owner 自己的脏判据之和，工作区不重建规则。
   * @returns {boolean}
   */
  function hasUnsavedDraftsNow() {
    if (generationView?.hasUnsavedDrafts()) return true;
    if (compareView?.hasUnsavedDrafts()) return true;
    return hasUnsavedFactDrafts();
  }

  /** 资料草稿是否真的与已保存内容不同：草稿读侧（唯一权威）对 owner 投影，不碰 DOM。
   * @returns {boolean}
   */
  function hasUnsavedFactDrafts() {
    if (!inputView) return false;
    try {
      return JSON.stringify(inputView.draftInputPayload())
        !== JSON.stringify(inputs.intakeSnapshot());
    } catch {
      return false;
    }
  }

  /**
   * @returns {Promise<void>}
   */
  async function loadWorkspace() {
    const action = beginAction();
    const pid = projectId && action.projectId && projectId === action.projectId ? projectId : null;
    if (!pid) return;
    inputView?.resetViewState();
    understandingReady = false;
    // 资料/事实/方案/风格/单图规格的唯一所有者是 project-inputs：reset+restore 一次灌入。
    inputs.reset();
    await inputs.restore(action);
    if (!action.alive()) return;
    prompts.reset();
    // V2.R5.1：生成执行侧链/飞行集合/报告/授权队列全部在 Module 里，loadWorkspace 统一重灌。
    generation.reset();
    selectionAdoption.reset();
    reviewDelivery.reset();
    // P5：未保存草稿/呈现基线按 project 精确归属，项目切换/关闭统一从视图状态回收。
    generationView?.resetViewState();
    revokePreviewUrls();
    deliveryView?.dispose();
    compareView?.resetViewState();

    // Prompt 版本/历史恢复归 prompts.restore 所有；授权/尝试/候选链恢复归 generation.restore。
    await prompts.restore(action);
    if (!action.alive()) return;
    await generation.restore(action);
    if (!action.alive()) return;
    // 采用记录+已知悉+单图报告由 selectionAdoption.restore 恢复（生成链已在上先灌入）；
    // 缺失/过期确定性报告的补建也归 adoption（restore 内 + 订阅生成候选变化），工作区不补、不吞异常。
    await selectionAdoption.restore(action);
    if (!action.alive()) return;
    // 整套报告与交付记录由 reviewDelivery.restore 恢复（suite+export；ack 已由 adoption.restore 恢复）。
    await reviewDelivery.restore(action);
    if (!action.alive()) return;
    renderAll();
    await loadCapabilities();
    if (!action.alive()) return;
    // capabilities 是渲染输入（input-view 经 deps.capabilities() 读能力、renderAttempts 读
    // 图像 provider），必须在它到位后重新投影，否则初次打开会留下"尚未读到能力信息"
    // 的陈旧文案，直到下一次用户动作触发渲染才消失。
    // 确认有效性依赖 capabilities 投影的有效档：能力到位后再做唯一一次状态派生；
    // 在能力到位前不派生，避免中间态先回写 PLAN_REVIEW、能力到位后又写回 READY_TO_GENERATE
    //（reload 路径两次生效写入，UI2-17 整库逐字判据必红）。
    // 阶段停靠必须在派生之后：understandingReady 等派生结论先就绪，否则重开必停在 intake。
    await deriveAndApplyState();
    refreshStageShell({ reset: true });
    renderAll();
  }

  modelSettings.subscribe(() => {
    capabilities = modelSettings.capabilities;
    if (!projectId) return;
    // 能力变化只更新投影；未保存输入由输入视图唯一持有，不再为了重绘提前落盘。
    renderAll();
  });
  return {
    /** @param {StoredProjectRecord} projectRecord @returns {Promise<void>} */
    async open(projectRecord) {
      bind();
      project = projectRecord;
      projectId = projectRecord.project_id;
      renderAll();
      try {
        await loadWorkspace();
      } catch (error) {
        handleInternalError(error);
      }
    },
    /** @returns {boolean} */
    isOpen() {
      return projectId !== null;
    },
    /** @returns {Promise<void>} */
    async close() {
      // 会话代由 session 统一推进；这里只做关闭时的收尾：
      // 先把未保存的草稿按当前（旧）会话落库，再清理本地资源与项目引用。
      // 不承诺取消上游：已发出的请求与已提交的任务照常完成，结果记录仍会写入。
      await inputView?.saveIntakeNow();
      revokePreviewUrls();
      deliveryView?.dispose();
      inputView?.resetViewState();
      generationView?.resetViewState();
      compareView?.resetViewState();
      project = null;
      projectId = null;
    },
    /** @param {StoredProjectRecord} projectRecord @returns {void} */
    setProject(projectRecord) {
      if (projectRecord && projectRecord.project_id === projectId) {
        project = projectRecord;
        renderHeaderText(project);
      }
    },
  };
}
