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

 import {
  ATTEMPT_ACTIVE_STATES,
  ATTEMPT_RECONCILE_MODES,
  ATTEMPT_STATES,
  COMPARE_CONTRACT_VERSION,
  COMPARE_SEVERITY_TEXT,
  COMPARE_STATE_TEXT,
  CONFIRM_DOCUMENT_ID,
  MAX_REFERENCES,
  MANUAL_EDIT_REASON_MAX,
  PRODUCT_INPUT_SCHEMA_VERSION,
  REFERENCE_ROLES,
  REWORK_CONTRACT_VERSION,
  REWORK_PROBLEMS,
  attemptCurrentEnvironmentIdentity,
  assertConfirmationSheet,
  attemptPromptStaleness,
  attemptReconcileMode,
  attemptReconcileEnvironment,
  attemptReconcileBlockedMessage,
  attemptStateLabel,
  batchProgressText,
  buildConfirmationSheet,
  buildReworkDirective,
  candidateMatchesAttempt,
  compareCounts,
  compareRowHeadline,
  compareRows,
  defaultCompareTargetId,
  intakeReadiness,
  newActionId,
  nextPendingShotId,
  promptStaleness,
  reviewChecklist,
  reviewIsCurrent,
  reviewSummaryText,
  selectionSetText,
  selectionSummaryText,
  sortFindings,
  suggestReworkProblems,
  suggestedReworkDirection,
  suitePlanSummary,
  topFinding,
} from "./domain/index.js";
import { createGenerationModule } from "./generation.js";
import { consumptionFence, createProjectInputsModule } from "./project-inputs.js";
import { createPromptModule } from "./prompts.js";
import { createReviewDeliveryModule } from "./review-delivery.js";
import { createSelectionAdoptionModule } from "./selection-adoption.js";
import { createDeliveryView } from "./ui/delivery-view.js";
import { createInputView } from "./ui/input-view.js";
import { createStageShell } from "./ui/stage-shell.js";
import {
  COMPARE_STATE_BADGE,
  ROLE_TEXT,
  SEVERITY_BADGE,
  STATUS_TEXT,
  appendTech,
  clearError,
  createElement,
  errorMessageOf,
  showError,
  splitLines,
  techDetails,
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
 * @typedef {import("./domain/type-contracts.js").ReviewReport} ReviewReport
 * @typedef {import("./domain/type-contracts.js").ReviewFinding} ReviewFinding
 * @typedef {import("./domain/type-contracts.js").SelectionRecord} SelectionRecord
 * @typedef {import("./domain/type-contracts.js").SelectionState} SelectionState
 * @typedef {import("./domain/type-contracts.js").SuiteReviewReport} SuiteReviewReport
 * @typedef {import("./domain/type-contracts.js").CompareRow} CompareRow
 * @typedef {import("./domain/type-contracts.js").CompareState} CompareState
 * @typedef {import("./domain/type-contracts.js").DeliveryGateResult} DeliveryGateResult
 * @typedef {import("./ui/delivery-view.js").DeliveryView} DeliveryView
 * @typedef {import("./ui/input-view.js").InputView} InputView
 * @typedef {import("./domain/type-contracts.js").UnknownItem} UnknownItem
 * @typedef {import("./domain/type-contracts.js").GateFinding} GateFinding
 * @typedef {import("./domain/type-contracts.js").ImagePromptProfile} ImagePromptProfile
 * @typedef {import("./domain/type-contracts.js").ReworkDirective} ReworkDirective
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
 * @typedef {import("./generation.js").AttemptEntry} AttemptEntry
 * @typedef {import("./generation.js").CandidateEntry} CandidateEntry
 * @typedef {import("./generation.js").ReviewReportEntry} ReviewReportEntry
 * @typedef {import("./generation.js").ConfirmationQueue} ConfirmationQueue
 * @typedef {import("./generation.js").PromptEntry} PromptEntry
 * @typedef {import("./generation.js").StoreCandidateResult} StoreCandidateResult
 * @typedef {import("./generation.js").GenerationIntent} GenerationIntent
 * @typedef {import("./semantic-analysis.js").AnalysisOutcome} AnalysisOutcome
 * @typedef {import("./semantic-analysis.js").SemanticRequestBody} SemanticRequestBody
 */

/**
 * 生成前确认单：domain/confirm.js `buildConfirmationSheet` 的确定性输出。领域层不导出该结构
 * 类型，工作区按实际消费的字段在本地收窄，并在 Narrow 时用 `assertConfirmationSheet` 校验。
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
 * 工作区的生成意图投影：确认单在本地已收窄，identity/snapshot 沿用 generation.js 声明。
 * @typedef {GenerationIntent & {all: ConfirmationSheetView|null, sheet: ConfirmationSheetView|null}} WorkspaceGenerationIntent
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
 * @property {HTMLButtonElement} refAdd
 * @property {HTMLInputElement} refFile
 * @property {HTMLElement} refCount
 * @property {HTMLElement} refError
 * @property {HTMLElement} refEmpty
 * @property {HTMLElement} refList
 * @property {HTMLInputElement} intakeName
 * @property {HTMLTextAreaElement} intakeDescription
 * @property {HTMLTextAreaElement} intakePoints
 * @property {HTMLInputElement} intakeFocus
 * @property {HTMLButtonElement} intakeSave
 * @property {HTMLElement} intakeDraft
 * @property {HTMLElement} intakeError
 * @property {HTMLButtonElement} manualFacts
 * @property {HTMLButtonElement} analyzeRun
 * @property {HTMLElement} analyzeGate
 * @property {HTMLElement} analyzeResult
 * @property {HTMLElement} analyzeError
 * @property {HTMLButtonElement} analyzeNewAfterUnknown
 * @property {HTMLElement} slotsProgress
 * @property {HTMLButtonElement} slotsToggle
 * @property {HTMLElement} slotsEmpty
 * @property {HTMLElement} slotList
 * @property {HTMLInputElement} slotAddId
 * @property {HTMLInputElement} slotAddLabel
 * @property {HTMLSelectElement} slotAddType
 * @property {HTMLTextAreaElement} slotAddValue
 * @property {HTMLInputElement} slotAddAllowModel
 * @property {HTMLButtonElement} slotAddSave
 * @property {HTMLElement} slotAddStatus
 * @property {HTMLElement} slotsError
 * @property {HTMLElement} suiteLocked
 * @property {HTMLElement} suiteEditor
 * @property {HTMLButtonElement} suiteSeed
 * @property {HTMLSelectElement} suiteTemplate
 * @property {HTMLElement} suiteTemplateHint
 * @property {HTMLButtonElement} suiteAddTemplate
 * @property {HTMLButtonElement} suiteCustomToggle
 * @property {HTMLElement} suiteStatus
 * @property {HTMLElement} suiteCustomPanel
 * @property {HTMLInputElement} suiteCustomLabel
 * @property {HTMLInputElement} suiteCustomIntent
 * @property {HTMLButtonElement} suiteCustomSave
 * @property {HTMLElement} suiteCustomStatus
 * @property {HTMLElement} suiteEmpty
 * @property {HTMLElement} shotList
 * @property {HTMLElement} suiteError
 * @property {HTMLElement} specsLocked
 * @property {HTMLElement} specsEditor
 * @property {HTMLInputElement} styleBackground
 * @property {HTMLInputElement} styleLighting
 * @property {HTMLInputElement} styleColorTone
 * @property {HTMLInputElement} styleComposition
 * @property {HTMLTextAreaElement} styleAvoid
 * @property {HTMLButtonElement} styleSave
 * @property {HTMLButtonElement} styleRestore
 * @property {HTMLElement} styleVersion
 * @property {HTMLElement} styleEffect
 * @property {HTMLElement} styleStatus
 * @property {HTMLElement} styleError
 * @property {HTMLElement} shotSpecsEmpty
 * @property {HTMLElement} shotSpecList
 * @property {HTMLElement} specsError
 * @property {HTMLElement} promptLocked
 * @property {HTMLElement} promptEditor
 * @property {HTMLElement} localPreparationStatus
 * @property {HTMLElement} promptStatus
 * @property {HTMLElement} promptList
 * @property {HTMLElement} promptError
 * @property {HTMLElement} confirmLocked
 * @property {HTMLElement} confirmEditor
 * @property {HTMLElement} confirmStatus
 * @property {HTMLElement} confirmSummary
 * @property {HTMLElement} confirmBlockers
 * @property {HTMLElement} confirmRisks
 * @property {HTMLElement} confirmList
 * @property {HTMLButtonElement} confirmAction
 * @property {HTMLElement} confirmRecord
 * @property {HTMLElement} confirmError
 * @property {HTMLElement} attemptLocked
 * @property {HTMLElement} attemptEditor
 * @property {HTMLElement} attemptStatus
 * @property {HTMLElement} attemptProvider
 * @property {HTMLElement} batchBar
 * @property {HTMLElement} queueList
 * @property {HTMLButtonElement} batchStop
 * @property {HTMLButtonElement} batchReconcile
 * @property {HTMLButtonElement} batchRetry
 * @property {HTMLElement} batchProgress
 * @property {HTMLElement} batchHint
 * @property {HTMLElement} attemptList
 * @property {HTMLElement} attemptError
 * @property {HTMLElement} comparePanel
 * @property {HTMLElement} compareSubject
 * @property {HTMLButtonElement} compareJump
 * @property {HTMLButtonElement} compareClose
 * @property {HTMLElement} compareBasisTitle
 * @property {HTMLElement} compareReferences
 * @property {HTMLElement} compareCandidates
 * @property {HTMLElement} compareChecklist
 * @property {HTMLElement} compareStatus
 * @property {HTMLImageElement} compareViewedImage
 * @property {HTMLElement} compareViewedCaption
 * @property {HTMLButtonElement} compareViewedZoom
 * @property {HTMLImageElement} compareBaselineImage
 * @property {HTMLSelectElement} compareBaselineSelect
 * @property {HTMLButtonElement} compareBaselineZoom
 * @property {HTMLButtonElement} compareReview
 * @property {HTMLDialogElement} imageZoomDialog
 * @property {HTMLElement} imageZoomTitle
 * @property {HTMLImageElement} imageZoomContent
 * @property {HTMLButtonElement} imageZoomNative
 * @property {HTMLButtonElement} imageZoomClose
 * @property {HTMLButtonElement} reworkOpen
 * @property {HTMLElement} reworkPanel
 * @property {HTMLElement} reworkBasis
 * @property {HTMLElement} reworkProblems
 * @property {HTMLTextAreaElement} reworkDirection
 * @property {HTMLButtonElement} reworkPreview
 * @property {HTMLButtonElement} reworkEdit
 * @property {HTMLButtonElement} reworkSubmit
 * @property {HTMLButtonElement} reworkReset
 * @property {HTMLButtonElement} reworkCancel
 * @property {HTMLElement} reworkPreviewBox
 * @property {HTMLElement} reworkPreviewMeta
 * @property {HTMLElement} reworkPreviewText
 * @property {HTMLElement} reworkTech
 * @property {HTMLElement} reworkTechBody
 * @property {HTMLElement} reworkSummary
 * @property {HTMLElement} reworkStatus
 * @property {HTMLElement} reworkError
 * @property {HTMLButtonElement} adoptOpen
 * @property {HTMLButtonElement} adoptClear
 * @property {HTMLElement} adoptStatus
 * @property {HTMLElement} adoptError
 * @property {HTMLElement} adoptProgress
 * @property {HTMLElement} generateError
 * @property {HTMLElement} stageNav
 * @property {HTMLElement} stagePanels
 * @property {HTMLElement} stageSummary
 * @property {HTMLButtonElement} stageNextUnderstand
 * @property {HTMLElement} stageNextUnderstandNote
 * @property {HTMLButtonElement} stageNextPlan
 * @property {HTMLElement} stageNextPlanNote
 * @property {HTMLButtonElement} stageNextReview
 * @property {HTMLElement} stageNextReviewNote
 * @property {HTMLButtonElement} stageNextDeliver
 * @property {HTMLElement} stageNextDeliverNote
 * @property {HTMLElement} reviewList
 * @property {HTMLElement} reviewEmpty
 * @property {HTMLElement} suiteReviewStatus
 * @property {HTMLButtonElement} suiteReviewRun
 * @property {HTMLButtonElement} suiteAiReviewRun
 * @property {HTMLElement} suiteReviewNote
 * @property {HTMLElement} suiteReviewFindings
 * @property {HTMLElement} suiteReviewError
 * @property {HTMLElement} deliveryGate
 * @property {HTMLElement} deliverySuiteStatus
 * @property {HTMLElement} deliverySuiteFindings
 * @property {HTMLElement} deliveryUnknowns
 * @property {HTMLButtonElement} deliverExport
 * @property {HTMLButtonElement} deliverProjectPackage
 * @property {HTMLElement} deliverStatus
 * @property {HTMLElement} deliverResult
 * @property {HTMLElement} deliverError
 */

/**
 * 返工预览（handleReworkPreview 显式预览后产生；payload 是编译后请求载荷）。
 * @typedef {object} ReworkPreview
 * @property {string} directive_id
 * @property {import("./domain/type-contracts.js").CompiledPrompt} payload
 * @property {number} references
 * @property {string} text
 */
 /**
 * 返工草稿（按图内存态；预览/指令只在显式预览后产生，不自动生成）。
 * @typedef {object} ReworkDraft
 * @property {string[]} problems
 * @property {string} direction
 * @property {ReworkPreview|null} [preview]
 * @property {ReworkDirective|null} [directive]
 */

/**
 * 比较区行（compareInventory 的投影行；record 恒为已校验候选）。
 * @typedef {object} CompareInventoryRow
 * @property {string} candidate_id
 * @property {string} shot_id
 * @property {string} asset_sha256
 * @property {CompareState} review_state
 * @property {boolean} pending
 * @property {ReviewFinding|null} top_finding
 * @property {ReviewReport|null} report
 * @property {CandidateRecord} record
 * @property {number|null} version
 * @property {string} created_at
 * @property {string|null} attempt_action_id
 * @property {string|null} task_id
 * @property {number|null} width
 * @property {number|null} height
 */


const SCOPE_TEXT = "这一版覆盖“商品资料 → 商品理解 → 套图规划 → 规格 → Prompt → 生成前确认 → 整套生成与逐图进度（含单张核对）→ 审核 → 单图返工 → 人工采用”；整套一致性报告与导出交付尚未接入。";

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
    error: /** @type {HTMLElement} */ (document.getElementById("workspace-error")),
    scope: /** @type {HTMLElement} */ (document.getElementById("project-scope")),
    refAdd: /** @type {HTMLButtonElement} */ (document.getElementById("ref-add")),
    refFile: /** @type {HTMLInputElement} */ (document.getElementById("ref-file")),
    refCount: /** @type {HTMLElement} */ (document.getElementById("ref-count")),
    refError: /** @type {HTMLElement} */ (document.getElementById("ref-error")),
    refEmpty: /** @type {HTMLElement} */ (document.getElementById("ref-empty")),
    refList: /** @type {HTMLElement} */ (document.getElementById("ref-list")),
    intakeName: /** @type {HTMLInputElement} */ (document.getElementById("intake-name")),
    intakeDescription: /** @type {HTMLTextAreaElement} */ (document.getElementById("intake-description")),
    intakePoints: /** @type {HTMLTextAreaElement} */ (document.getElementById("intake-selling-points")),
    intakeFocus: /** @type {HTMLInputElement} */ (document.getElementById("intake-focus")),
    intakeSave: /** @type {HTMLButtonElement} */ (document.getElementById("intake-save")),
    intakeDraft: /** @type {HTMLElement} */ (document.getElementById("intake-draft")),
    intakeError: /** @type {HTMLElement} */ (document.getElementById("intake-error")),
    manualFacts: /** @type {HTMLButtonElement} */ (document.getElementById("manual-facts")),
    analyzeRun: /** @type {HTMLButtonElement} */ (document.getElementById("analyze-run")),
    analyzeGate: /** @type {HTMLElement} */ (document.getElementById("analyze-gate")),
    analyzeResult: /** @type {HTMLElement} */ (document.getElementById("analyze-result")),
    analyzeError: /** @type {HTMLElement} */ (document.getElementById("analyze-error")),
    analyzeNewAfterUnknown: /** @type {HTMLButtonElement} */ (document.getElementById("analyze-new-after-unknown")),
    slotsProgress: /** @type {HTMLElement} */ (document.getElementById("slots-progress")),
    slotsToggle: /** @type {HTMLButtonElement} */ (document.getElementById("slots-toggle")),
    slotsEmpty: /** @type {HTMLElement} */ (document.getElementById("slots-empty")),
    slotList: /** @type {HTMLElement} */ (document.getElementById("slot-list")),
    slotAddId: /** @type {HTMLInputElement} */ (document.getElementById("slot-add-id")),
    slotAddLabel: /** @type {HTMLInputElement} */ (document.getElementById("slot-add-label")),
    slotAddType: /** @type {HTMLSelectElement} */ (document.getElementById("slot-add-type")),
    slotAddValue: /** @type {HTMLTextAreaElement} */ (document.getElementById("slot-add-value")),
    slotAddAllowModel: /** @type {HTMLInputElement} */ (document.getElementById("slot-add-allow-model")),
    slotAddSave: /** @type {HTMLButtonElement} */ (document.getElementById("slot-add-save")),
    slotAddStatus: /** @type {HTMLElement} */ (document.getElementById("slot-add-status")),
    slotsError: /** @type {HTMLElement} */ (document.getElementById("slots-error")),
    suiteLocked: /** @type {HTMLElement} */ (document.getElementById("suite-locked")),
    suiteEditor: /** @type {HTMLElement} */ (document.getElementById("suite-editor")),
    suiteSeed: /** @type {HTMLButtonElement} */ (document.getElementById("suite-seed")),
    suiteTemplate: /** @type {HTMLSelectElement} */ (document.getElementById("suite-template")),
    suiteTemplateHint: /** @type {HTMLElement} */ (document.getElementById("suite-template-hint")),
    suiteAddTemplate: /** @type {HTMLButtonElement} */ (document.getElementById("suite-add-template")),
    suiteCustomToggle: /** @type {HTMLButtonElement} */ (document.getElementById("suite-custom-toggle")),
    suiteStatus: /** @type {HTMLElement} */ (document.getElementById("suite-status")),
    suiteCustomPanel: /** @type {HTMLElement} */ (document.getElementById("suite-custom-panel")),
    suiteCustomLabel: /** @type {HTMLInputElement} */ (document.getElementById("suite-custom-label")),
    suiteCustomIntent: /** @type {HTMLInputElement} */ (document.getElementById("suite-custom-intent")),
    suiteCustomSave: /** @type {HTMLButtonElement} */ (document.getElementById("suite-custom-save")),
    suiteCustomStatus: /** @type {HTMLElement} */ (document.getElementById("suite-custom-status")),
    suiteEmpty: /** @type {HTMLElement} */ (document.getElementById("suite-empty")),
    shotList: /** @type {HTMLElement} */ (document.getElementById("shot-list")),
    suiteError: /** @type {HTMLElement} */ (document.getElementById("suite-error")),
    specsLocked: /** @type {HTMLElement} */ (document.getElementById("specs-locked")),
    specsEditor: /** @type {HTMLElement} */ (document.getElementById("specs-editor")),
    styleBackground: /** @type {HTMLInputElement} */ (document.getElementById("style-background")),
    styleLighting: /** @type {HTMLInputElement} */ (document.getElementById("style-lighting")),
    styleColorTone: /** @type {HTMLInputElement} */ (document.getElementById("style-color-tone")),
    styleComposition: /** @type {HTMLInputElement} */ (document.getElementById("style-composition")),
    styleAvoid: /** @type {HTMLTextAreaElement} */ (document.getElementById("style-avoid")),
    styleSave: /** @type {HTMLButtonElement} */ (document.getElementById("style-save")),
    styleRestore: /** @type {HTMLButtonElement} */ (document.getElementById("style-restore")),
    styleVersion: /** @type {HTMLElement} */ (document.getElementById("style-version")),
    styleEffect: /** @type {HTMLElement} */ (document.getElementById("style-effect")),
    styleStatus: /** @type {HTMLElement} */ (document.getElementById("style-status")),
    styleError: /** @type {HTMLElement} */ (document.getElementById("style-error")),
    shotSpecsEmpty: /** @type {HTMLElement} */ (document.getElementById("shot-specs-empty")),
    shotSpecList: /** @type {HTMLElement} */ (document.getElementById("shot-spec-list")),
    specsError: /** @type {HTMLElement} */ (document.getElementById("specs-error")),
    promptLocked: /** @type {HTMLElement} */ (document.getElementById("prompt-locked")),
    promptEditor: /** @type {HTMLElement} */ (document.getElementById("prompt-editor")),
    localPreparationStatus: /** @type {HTMLElement} */ (document.getElementById("local-preparation-status")),
    promptStatus: /** @type {HTMLElement} */ (document.getElementById("prompt-status")),
    promptList: /** @type {HTMLElement} */ (document.getElementById("prompt-list")),
    promptError: /** @type {HTMLElement} */ (document.getElementById("prompt-error")),
    confirmLocked: /** @type {HTMLElement} */ (document.getElementById("confirm-locked")),
    confirmEditor: /** @type {HTMLElement} */ (document.getElementById("confirm-editor")),
    confirmStatus: /** @type {HTMLElement} */ (document.getElementById("confirm-status")),
    confirmSummary: /** @type {HTMLElement} */ (document.getElementById("confirm-summary")),
    confirmBlockers: /** @type {HTMLElement} */ (document.getElementById("confirm-blockers")),
    confirmRisks: /** @type {HTMLElement} */ (document.getElementById("confirm-risks")),
    confirmList: /** @type {HTMLElement} */ (document.getElementById("confirm-list")),
    confirmAction: /** @type {HTMLButtonElement} */ (document.getElementById("confirm-action")),
    confirmRecord: /** @type {HTMLElement} */ (document.getElementById("confirm-record")),
    confirmError: /** @type {HTMLElement} */ (document.getElementById("confirm-error")),
    attemptLocked: /** @type {HTMLElement} */ (document.getElementById("attempt-locked")),
    attemptEditor: /** @type {HTMLElement} */ (document.getElementById("attempt-editor")),
    attemptStatus: /** @type {HTMLElement} */ (document.getElementById("attempt-status")),
    attemptProvider: /** @type {HTMLElement} */ (document.getElementById("attempt-provider")),
    batchBar: /** @type {HTMLElement} */ (document.getElementById("attempt-batch")),
    queueList: /** @type {HTMLElement} */ (document.getElementById("generation-queues")),
    batchStop: /** @type {HTMLButtonElement} */ (document.getElementById("batch-stop")),
    batchReconcile: /** @type {HTMLButtonElement} */ (document.getElementById("batch-reconcile")),
    batchRetry: /** @type {HTMLButtonElement} */ (document.getElementById("batch-retry")),
    batchProgress: /** @type {HTMLElement} */ (document.getElementById("batch-progress")),
    batchHint: /** @type {HTMLElement} */ (document.getElementById("batch-hint")),
    attemptList: /** @type {HTMLElement} */ (document.getElementById("attempt-list")),
    attemptError: /** @type {HTMLElement} */ (document.getElementById("attempt-error")),
    comparePanel: /** @type {HTMLElement} */ (document.getElementById("compare-panel")),
    compareSubject: /** @type {HTMLElement} */ (document.getElementById("compare-subject")),
    compareJump: /** @type {HTMLButtonElement} */ (document.getElementById("compare-jump")),
    compareClose: /** @type {HTMLButtonElement} */ (document.getElementById("compare-close")),
    compareBasisTitle: /** @type {HTMLElement} */ (document.getElementById("compare-basis-title")),
    compareReferences: /** @type {HTMLElement} */ (document.getElementById("compare-references")),
    compareCandidates: /** @type {HTMLElement} */ (document.getElementById("compare-candidates")),
    compareChecklist: /** @type {HTMLElement} */ (document.getElementById("compare-checklist")),
    compareStatus: /** @type {HTMLElement} */ (document.getElementById("compare-status")),
    compareViewedImage: /** @type {HTMLImageElement} */ (document.getElementById("compare-viewed-image")),
    compareViewedCaption: /** @type {HTMLElement} */ (document.getElementById("compare-viewed-caption")),
    compareViewedZoom: /** @type {HTMLButtonElement} */ (document.getElementById("compare-viewed-zoom")),
    compareBaselineImage: /** @type {HTMLImageElement} */ (document.getElementById("compare-baseline-image")),
    compareBaselineSelect: /** @type {HTMLSelectElement} */ (document.getElementById("compare-baseline-select")),
    compareBaselineZoom: /** @type {HTMLButtonElement} */ (document.getElementById("compare-baseline-zoom")),
    compareReview: /** @type {HTMLButtonElement} */ (document.getElementById("compare-review")),
    imageZoomDialog: /** @type {HTMLDialogElement} */ (document.getElementById("image-zoom-dialog")),
    imageZoomTitle: /** @type {HTMLElement} */ (document.getElementById("image-zoom-title")),
    imageZoomContent: /** @type {HTMLImageElement} */ (document.getElementById("image-zoom-content")),
    imageZoomNative: /** @type {HTMLButtonElement} */ (document.getElementById("image-zoom-native")),
    imageZoomClose: /** @type {HTMLButtonElement} */ (document.getElementById("image-zoom-close")),
    reworkOpen: /** @type {HTMLButtonElement} */ (document.getElementById("rework-open")),
    reworkPanel: /** @type {HTMLElement} */ (document.getElementById("rework-panel")),
    reworkBasis: /** @type {HTMLElement} */ (document.getElementById("rework-basis")),
    reworkProblems: /** @type {HTMLElement} */ (document.getElementById("rework-problems")),
    reworkDirection: /** @type {HTMLTextAreaElement} */ (document.getElementById("rework-direction")),
    reworkPreview: /** @type {HTMLButtonElement} */ (document.getElementById("rework-preview")),
    reworkEdit: /** @type {HTMLButtonElement} */ (document.getElementById("rework-edit")),
    reworkSubmit: /** @type {HTMLButtonElement} */ (document.getElementById("rework-submit")),
    reworkReset: /** @type {HTMLButtonElement} */ (document.getElementById("rework-reset")),
    reworkCancel: /** @type {HTMLButtonElement} */ (document.getElementById("rework-cancel")),
    reworkPreviewBox: /** @type {HTMLElement} */ (document.getElementById("rework-preview-box")),
    reworkPreviewMeta: /** @type {HTMLElement} */ (document.getElementById("rework-preview-meta")),
    reworkPreviewText: /** @type {HTMLElement} */ (document.getElementById("rework-preview-text")),
    reworkTech: /** @type {HTMLElement} */ (document.getElementById("rework-tech")),
    reworkTechBody: /** @type {HTMLElement} */ (document.getElementById("rework-tech-body")),
    reworkSummary: /** @type {HTMLElement} */ (document.getElementById("rework-summary")),
    reworkStatus: /** @type {HTMLElement} */ (document.getElementById("rework-status")),
    reworkError: /** @type {HTMLElement} */ (document.getElementById("rework-error")),
    adoptOpen: /** @type {HTMLButtonElement} */ (document.getElementById("adopt-open")),
    adoptClear: /** @type {HTMLButtonElement} */ (document.getElementById("adopt-clear")),
    adoptStatus: /** @type {HTMLElement} */ (document.getElementById("adopt-status")),
    adoptError: /** @type {HTMLElement} */ (document.getElementById("adopt-error")),
    adoptProgress: /** @type {HTMLElement} */ (document.getElementById("adopt-progress")),
    generateError: /** @type {HTMLElement} */ (document.getElementById("generate-error")),
    stageNav: /** @type {HTMLElement} */ (document.getElementById("stage-nav")),
    stagePanels: /** @type {HTMLElement} */ (document.getElementById("stage-panels")),
    stageSummary: /** @type {HTMLElement} */ (document.getElementById("stage-summary")),
    stageNextUnderstand: /** @type {HTMLButtonElement} */ (document.getElementById("stage-next-understand")),
    stageNextUnderstandNote: /** @type {HTMLElement} */ (document.getElementById("stage-next-understand-note")),
    stageNextPlan: /** @type {HTMLButtonElement} */ (document.getElementById("stage-next-plan")),
    stageNextPlanNote: /** @type {HTMLElement} */ (document.getElementById("stage-next-plan-note")),
    stageNextReview: /** @type {HTMLButtonElement} */ (document.getElementById("stage-next-review")),
    stageNextReviewNote: /** @type {HTMLElement} */ (document.getElementById("stage-next-review-note")),
    stageNextDeliver: /** @type {HTMLButtonElement} */ (document.getElementById("stage-next-deliver")),
    stageNextDeliverNote: /** @type {HTMLElement} */ (document.getElementById("stage-next-deliver-note")),
    reviewList: /** @type {HTMLElement} */ (document.getElementById("review-list")),
    reviewEmpty: /** @type {HTMLElement} */ (document.getElementById("review-empty")),
    suiteReviewStatus: /** @type {HTMLElement} */ (document.getElementById("suite-review-status")),
    suiteReviewRun: /** @type {HTMLButtonElement} */ (document.getElementById("suite-review-run")),
    suiteAiReviewRun: /** @type {HTMLButtonElement} */ (document.getElementById("suite-ai-review-run")),
    suiteReviewNote: /** @type {HTMLElement} */ (document.getElementById("suite-review-note")),
    suiteReviewFindings: /** @type {HTMLElement} */ (document.getElementById("suite-review-findings")),
    suiteReviewError: /** @type {HTMLElement} */ (document.getElementById("suite-review-error")),
    deliveryGate: /** @type {HTMLElement} */ (document.getElementById("delivery-gate")),
    deliverySuiteStatus: /** @type {HTMLElement} */ (document.getElementById("delivery-suite-status")),
    deliverySuiteFindings: /** @type {HTMLElement} */ (document.getElementById("delivery-suite-findings")),
    deliveryUnknowns: /** @type {HTMLElement} */ (document.getElementById("delivery-unknowns")),
    deliverExport: /** @type {HTMLButtonElement} */ (document.getElementById("deliver-export")),
    deliverProjectPackage: /** @type {HTMLButtonElement} */ (document.getElementById("deliver-project-package")),
    deliverStatus: /** @type {HTMLElement} */ (document.getElementById("deliver-status")),
    deliverResult: /** @type {HTMLElement} */ (document.getElementById("delivery-result")),
    deliverError: /** @type {HTMLElement} */ (document.getElementById("deliver-error")),
  };

  // 交付视图（设计 §2.1 第四个视图）持 DOM、展开与自己的对象 URL；先声明后装配：
  // 下面的 onSelect 与两个 Module 的 changed 都只在装配完成后触发，不在装配期回调。
  /** @type {DeliveryView|null} */
  let deliveryView = null;
  // 输入视图（设计 §10.1 第一个视图）持资料/理解/方案的 DOM 与就地状态；同样先声明后装配。
  /** @type {InputView|null} */
  let inputView = null;

  const stageShell = createStageShell({
    nav: /** @type {HTMLElement} */ (elements.stageNav),
    panelRoot: /** @type {HTMLElement} */ (elements.stagePanels),
    summary: /** @type {HTMLElement} */ (elements.stageSummary),
    onSelect: (/** @type {string} */ id) => {
      if (id === "deliver") deliveryView?.requestGateRefresh();
      if (id === "understand" && projectId) void inputView?.prepareManualFacts();
      if (id === "generate" && projectId) void prepareSystemPrompts();
    },
  });

  /** @type {StoredProjectRecord|null} */
  let project = null;
  /** @type {string|null} */
  let projectId = null;
  // R3.3：动作身份冻结的本地别名——所有状态变更动作统一经 session.beginAction()。
  /** @type {() => ActionSnapshot} */
  const beginAction = () => session.beginAction();

  // 输入面唯一所有者（包04 收口）：资料/事实/方案/风格/单图规格与语义分析执行都在这里，
  // workspace 只保留 DOM 草稿编辑状态、装配与视图渲染，不再持有第二份输入状态。
  const inputs = createProjectInputsModule({
    repository,
    beginAction,
    settings: modelSettings,
    capabilities: () => capabilities,
    projectIdReader: () => projectId,
    projectNameReader: () => (project && project.name) || "",
    draftInput: draftInputPayload,
    changed: () => {
      void deriveAndApplyState().then(() => {
        inputView?.renderAnalyze();
        inputView?.renderDraftStatus();
        inputView?.renderConflictEditor();
        renderHeaderText(project);
      });
    },
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
    environmentReader: /** @param {unknown} saved */ (saved) => modelSettings.imageEnvironment(
      (/** @type {{provider?: {provider_id?: string}, payload?: {fingerprint?: {snapshot?: {execution_target?: {provider_id?: string}}}}}} */ (saved))?.provider?.provider_id || (/** @type {{payload?: {fingerprint?: {snapshot?: {execution_target?: {provider_id?: string}}}}}} */ (saved))?.payload?.fingerprint?.snapshot?.execution_target?.provider_id,
      (/** @type {{execution_identity?: {credential_reference?: {source?: string}}, payload?: {fingerprint?: {snapshot?: {execution_target?: {credential_source?: string}}}}}} */ (saved))?.execution_identity?.credential_reference?.source || (/** @type {{payload?: {fingerprint?: {snapshot?: {execution_target?: {credential_source?: string}}}}}} */ (saved))?.payload?.fingerprint?.snapshot?.execution_target?.credential_source),
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
    promptsSheet: (ids) => prompts.sheet(ids ?? null),
    imageEnvironment: (saved) => /** @type {unknown} */ (saved ?? modelSettings.imageEnvironment()),
    candidateReviewRequest: async () => { throw new Error("复核请求准备尚未装配。"); },
    renderAttempts: renderAttempts,
    renderBatch: renderBatch,
    status: (/** @type {string} */ text) => { elements.attemptStatus.textContent = text; },
    attemptError: showAttemptError,
    clearAttemptError: clearAttemptError,
  });
  const selectionAdoption = createSelectionAdoptionModule({
    repository: /** @type {import("./storage/validate.js").ProjectRepository} */ (/** @type {unknown} */ (repository)),
    generation,
    prompts,
    settings: modelSettings,
    beginAction, sources: projectSources,
    changed: () => { deliveryView?.render(); },
  });
  // 单图复核请求准备归 adoption：generation 的注入在 adoption 装配后补线，
  // 调用只发生在用户点击复核时（装配早已完成），不形成装配期循环。
  generation.setCandidateReviewRequest(
    (/** @type {string} */ shotId, /** @type {CandidateRecord} */ candidate, /** @type {string} */ pid) =>
      selectionAdoption.candidateReviewRequest(shotId, candidate, pid));
  generation.setReviewRunner(
    (/** @type {string} */ shotId, /** @type {string} */ candidateId) =>
      selectionAdoption.reviewCandidate(shotId, candidateId));
  generation.setReviewFlightReader(
    (/** @type {string} */ shotId) => selectionAdoption.isReviewInFlight(shotId));
  generation.setReviewAccess(selectionAdoption);
  const reviewDelivery = createReviewDeliveryModule({
    repository: /** @type {import("./storage/validate.js").ProjectRepository} */ (/** @type {unknown} */ (repository)),
    generation,
    adoption: selectionAdoption,
    settings: modelSettings,
    beginAction, sources: projectSources,
    changed: () => { deliveryView?.render(); },
  });

  // 交付视图只持 DOM、展开与自己的对象 URL；逐图采用状态、门禁、整套结论与两类导出
  // 都读 owner 投影，视图不写库、不重算判定、不组 manifest/ZIP。
  deliveryView = createDeliveryView({
    elements: {
      reviewList: elements.reviewList,
      suiteReviewStatus: elements.suiteReviewStatus,
      suiteReviewRun: elements.suiteReviewRun,
      suiteAiReviewRun: elements.suiteAiReviewRun,
      suiteReviewNote: elements.suiteReviewNote,
      suiteReviewFindings: elements.suiteReviewFindings,
      suiteReviewError: elements.suiteReviewError,
      deliveryGate: elements.deliveryGate,
      deliverySuiteStatus: elements.deliverySuiteStatus,
      deliverySuiteFindings: elements.deliverySuiteFindings,
      deliveryUnknowns: elements.deliveryUnknowns,
      deliverExport: elements.deliverExport,
      deliverStatus: elements.deliverStatus,
      deliverResult: elements.deliverResult,
      deliverError: elements.deliverError,
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
      selectionStateOf,
      selectStage: (/** @type {string} */ id) => stageShell.select(id),
    },
  });

  // 输入视图只持资料/理解/方案的 DOM、展开与就地编辑态；资料/事实/方案/风格/单图规格的
  // 读写都在 inputs（唯一所有者），落库/派生/跨视图刷新经下面的窄回调回到工作区。
  inputView = createInputView({
    elements: {
      intakeName: elements.intakeName,
      intakeDescription: elements.intakeDescription,
      intakePoints: elements.intakePoints,
      intakeFocus: elements.intakeFocus,
      intakeDraft: elements.intakeDraft,
      intakeError: elements.intakeError,
      analyzeNewAfterUnknown: elements.analyzeNewAfterUnknown,
      analyzeRun: elements.analyzeRun,
      analyzeGate: elements.analyzeGate,
      analyzeResult: elements.analyzeResult,
      analyzeError: elements.analyzeError,
      slotsProgress: elements.slotsProgress,
      slotsToggle: elements.slotsToggle,
      slotsEmpty: elements.slotsEmpty,
      slotList: elements.slotList,
      slotAddId: elements.slotAddId,
      slotAddLabel: elements.slotAddLabel,
      slotAddType: elements.slotAddType,
      slotAddValue: elements.slotAddValue,
      slotAddAllowModel: elements.slotAddAllowModel,
      slotAddStatus: elements.slotAddStatus,
      slotsError: elements.slotsError,
      suiteLocked: elements.suiteLocked,
      suiteEditor: elements.suiteEditor,
      suiteTemplate: elements.suiteTemplate,
      suiteTemplateHint: elements.suiteTemplateHint,
      suiteCustomToggle: elements.suiteCustomToggle,
      suiteCustomPanel: elements.suiteCustomPanel,
      suiteCustomLabel: elements.suiteCustomLabel,
      suiteCustomIntent: elements.suiteCustomIntent,
      suiteCustomStatus: elements.suiteCustomStatus,
      suiteStatus: elements.suiteStatus,
      suiteEmpty: elements.suiteEmpty,
      shotList: elements.shotList,
      suiteError: elements.suiteError,
      specsLocked: elements.specsLocked,
      specsEditor: elements.specsEditor,
      styleBackground: elements.styleBackground,
      styleLighting: elements.styleLighting,
      styleColorTone: elements.styleColorTone,
      styleComposition: elements.styleComposition,
      styleAvoid: elements.styleAvoid,
      styleVersion: elements.styleVersion,
      styleRestore: elements.styleRestore,
      styleEffect: elements.styleEffect,
      styleStatus: elements.styleStatus,
      styleError: elements.styleError,
      shotSpecsEmpty: elements.shotSpecsEmpty,
      shotSpecList: elements.shotSpecList,
      specsError: elements.specsError,
    },
    deps: {
      inputs,
      beginAction,
      currentProjectId: () => projectId,
      capabilities: () => capabilities,
      understandingBlocking: () => understandingBlocking,
      draftInput: draftInputPayload,
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

  /** @type {EffectiveCapabilities|null} */
  let capabilities = null;
  /** @type {string|null} */
  let capabilitiesError = null;
  /** @type {import("./domain/type-contracts.js").BriefReadiness["blocking"]} */
  let understandingBlocking = [];
  /** @type {unknown} */
  let understandingError = null;
  /** @type {boolean} */
  let understandingReady = false;
  // Prompt 版本/历史/准备状态 → prompts Module；确认队列/scope/mode → generation Module；
  // 采用记录 → selectionAdoption Module；整套报告/门禁/交付包 → reviewDelivery Module；
  // 资料/事实/方案/风格/单图规格 → project-inputs Module（唯一所有者）。
  // 本闭包不再持有上述可变状态，只保留 DOM 草稿编辑状态、视图装配与生命周期。
  /** @type {string|null} */
  let compareShotId = null;
  /** @type {string|null} */
  let compareCandidateId = null;
  /** @type {number} */
  let compareToken = 0;
  /** @type {number} */
  let compareImageToken = 0;
  /** @type {string|null} */
  let compareBaselineId = null;
  /** @type {Map<string, {candidateId: string|null, baselineId: string|null}>} */
  const compareViews = new Map();
  /** @type {HTMLElement|null} */
  let imageZoomReturnFocus = null;
  /** @type {Map<string, ReworkDraft>} */
  let reworkDrafts = new Map();
  /** @type {boolean} */
  let reworkInFlight = false;
  /** @type {string|null} */
  let reworkShotId = null;
  /** @type {{shot_id: string, candidate_id: string, asset_sha256: string, version: number|null}|null} */
  let reworkSource = null;
  /** @type {string[]} */
  let objectUrls = [];
  /** @type {Map<string, string>} */
  let previewUrls = new Map();
  /** @type {boolean} */
  let submissionInFlight = false;
  /** @type {WorkspaceGenerationIntent|null} */
  let displayedGenerationIntent = null;
  /** @type {boolean} */
  let bound = false;
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

  /** 生成与审核两个阶段都可能发起提交/核对：错误就近显示在对应阶段，两处同一份文本。
   * @param {string|undefined} message
   * @returns {void}
   */
  function showAttemptError(message) {
    showError(elements.generateError, message || "");
    showError(elements.attemptError, message || "");
  }

  /**
   * @returns {void}
   */
  function clearAttemptError() {
    clearError(elements.generateError);
    clearError(elements.attemptError);
  }

  /**
   * @returns {void}
   */
  function revokeObjectUrls() {
    for (const url of objectUrls) URL.revokeObjectURL(url);
    objectUrls = [];
  }

  /**
   * @returns {void}
   */
  function revokePreviewUrls() {
    for (const url of previewUrls.values()) URL.revokeObjectURL(url);
    previewUrls = new Map();
  }

  /**
   * DOM 草稿编辑区是 workspace 唯一保留的输入状态：所有者通过 draftInput 依赖读取它，
   * 落库/合并/指纹一律由 project-inputs 负责，这里不持有第二份资料状态。
   * @returns {CompleteProductInput}
   */
  function draftInputPayload() {
    return {
      schema_version: PRODUCT_INPUT_SCHEMA_VERSION,
      product_name: elements.intakeName.value.trim(),
      description: elements.intakeDescription.value.trim(),
      selling_points: splitLines(elements.intakePoints.value),
      focus: elements.intakeFocus.value.trim(),
      references: inputs.references().map((item) => ({ ...item })),
    };
  }

  /**
   * @param {unknown} error
   * @returns {void}
   */
  function handleInternalError(error) {
    showError(elements.error, errorMessageOf(error, "操作没有完成，请重试。"));
  }

  /* ------------------------------------------------------------ 参考图 */

  /**
   * @returns {Promise<void>}
   */
  async function renderReferences() {
    // 先异步取齐资产、只在最后一刻替换 DOM：重叠渲染不会把同一行插两次。
    const pid = projectId;
    if (!pid) return;
    const entries = inputs.references();
    const rows = [];
    const urls = [];
    for (const [index, entry] of entries.entries()) {
      const asset = await repository.assets.get(pid, entry.asset_sha256);
      const row = createElement("li", { className: "ref-row" });
      row.dataset.sha = entry.asset_sha256;

      const thumb = createElement("div", { className: "ref-thumb" });
      if (asset && asset.blob instanceof Blob) {
        const url = URL.createObjectURL(asset.blob);
        urls.push(url);
        thumb.append(createElement("img", {
          attrs: { src: url, alt: (asset.original_name || "参考图"), loading: "lazy" },
        }));
      } else {
        thumb.append(createElement("span", { className: "meta", text: "资产缺失" }));
      }

      const main = createElement("div", { className: "ref-main" });
      main.append(createElement("span", {
        className: "name",
        text: (asset && asset.original_name) || ("参考图 " + (index + 1)),
      }));
      const info = asset
        ? [asset.media_type, asset.byte_size + " 字节",
           (asset.width && asset.height ? asset.width + "×" + asset.height : "尺寸未知")].join(" · ")
        : "资产记录缺失";
      main.append(createElement("span", { className: "meta", text: info }));
      appendTech(main, ["sha256 " + entry.asset_sha256.slice(0, 12) + "…"]);

      const actions = createElement("div", { className: "ref-actions" });
      const select = createElement("select", {
        attrs: { "aria-label": "参考图角色" },
        props: { value: entry.role },
      });
      for (const role of REFERENCE_ROLES) {
        select.append(createElement("option", {
          text: /** @type {Record<string, string>} */ (ROLE_TEXT)[role] || role, attrs: { value: role },
        }));
      }
      select.value = entry.role;
      select.addEventListener("change", () => { handleRoleChange(index, /** @type {ReferenceRole} */ (select.value)); });
      const remove = createElement("button", {
        className: "danger", text: "删除", attrs: { type: "button" },
      });
      remove.addEventListener("click", () => { handleRemoveReference(index); });
      actions.append(select, remove);

      row.append(thumb, main, actions);
      rows.push(row);
    }
    revokeObjectUrls();
    objectUrls = urls;
    elements.refList.replaceChildren(...rows);
    elements.refCount.textContent = entries.length
      ? entries.length + " / " + MAX_REFERENCES + " 张"
      : "";
    elements.refEmpty.hidden = entries.length > 0;
  }

  /**
   * @param {number} index
   * @param {import("./domain/type-contracts.js").ReferenceRole} role
   * @returns {Promise<void>}
   */
  async function handleRoleChange(index, role) {
    const action = beginAction();
    clearError(elements.refError);
    if (inputs) await inputs.setReferenceRole(index, role);
    if (!action.alive()) return;
    renderAll();
  }

  /**
   * @param {number} index
   * @returns {Promise<void>}
   */
  async function handleRemoveReference(index) {
    const action = beginAction();
    clearError(elements.refError);
    if (inputs) await inputs.removeReference(index);
    if (!action.alive()) return;
    renderAll();
  }

  /**
   * @param {FileList|File[]|null|undefined} fileList
   * @returns {Promise<void>}
   */
  async function handleFiles(fileList) {
    const files = [...(fileList || [])];
    if (!files.length) return;
    const action = beginAction();
    if (!action.projectId) return;
    clearError(elements.refError);
    const added = await inputs.addReferences(files, (kind, file) => {
      if (!action.alive()) return;
      if (kind === "too_many") showError(elements.refError, "参考图最多 " + MAX_REFERENCES + " 张，多出的文件没有加入。");
      else if (kind === "too_large") showError(elements.refError, "“" + file.name + "”超过单张参考图上限 10MB，已跳过；请压缩后再上传。");
      else if (kind === "unreadable") showError(elements.refError, "“" + file.name + "”不是可读取的图片，已跳过。");
      else showError(elements.refError, "“" + file.name + "”与已有参考图内容相同，已跳过。");
    });
    if (added && action.alive()) renderAll();
  }




  /**
   * @returns {Promise<void>}
   */
  async function loadCapabilities() {
    capabilitiesError = null;
    capabilities = await modelSettings.refresh();
    if (!capabilities) capabilitiesError = "有效模型配置不可用；本地资料可继续编辑，请打开模型设置。";
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

  /* --------------------------------------------------------- Prompt 编译 */

  /* Prompt 版本/依据的唯一所有者是 prompts Module；以下只做只读转发，不持有第二份 Map。 */
  /**
   * @param {string} shotId
   * @param {number|null|undefined} version
   * @returns {PromptEntry|null}
   */
  function promptVersionAt(shotId, version) {
    return prompts.entryOf(shotId, version ?? null);
  }

  function currentImageProfile() {
    return prompts.profile(/** @type {unknown} */ (capabilities && capabilities.images));
  }

  /**
   * @param {string|null} shotId
   * @param {ImagePromptProfile|null} [provider]
   * @returns {unknown}
   */
  function promptCurrentBasis(shotId, provider = currentImageProfile()) {
    return prompts.basis(shotId, provider, projectSources());
  }

  /**
   * @param {string|null} shotId
   * @returns {PromptEntry|null}
   */
  function promptRecordOf(shotId) {
    return prompts.entryOf(shotId, null);
  }

  /** 未保存的编辑草稿：重渲染时保留用户输入，不让界面动作吞掉正在写的文本。 */
  /**
   * @returns {Map<string, {text: string, reason: string}>}
   */
  function capturePromptEdits() {
    const drafts = new Map();
    for (const area of /** @type {NodeListOf<HTMLTextAreaElement>} */ (elements.promptList.querySelectorAll("textarea.prompt-edit-text"))) {
      const shotId = area.getAttribute("data-shot-id");
      const reason = area.parentElement
        ? /** @type {HTMLInputElement|null} */ (area.parentElement.querySelector("input.prompt-edit-reason")) : null;
      if (shotId) drafts.set(shotId, { text: area.value, reason: reason ? reason.value : "" });
    }
    return drafts;
  }

  /**
   * @returns {void}
   */
  function renderPrompts() {
    const drafts = capturePromptEdits();
    const ready = Boolean(inputs.suitePlan());
    elements.promptLocked.hidden = ready;
    elements.promptEditor.hidden = !ready;
    elements.promptList.innerHTML = "";
    if (!ready) return;
    const summary = suitePlanSummary(inputs.suitePlan(), inputs.suiteContext());
    elements.promptStatus.textContent = summary
      ? "共 " + summary.total + " 张，依据已满足 " + summary.satisfiable + " 张可编译。"
      : "";
    if (!summary) return;
    summary.shots.forEach((item, index) => {
      // 已保存计划恒有 shot_id；null 仅存在于未落库草稿，跳过即可。
      const shotId = item.shot_id;
      if (typeof shotId !== "string") return;
      const entry = promptRecordOf(shotId);
      const stale = entry ? promptStaleness(entry.record, promptCurrentBasis(shotId)) : null;
      const card = createElement("div", {
        className: "shot-spec",
        attrs: {
          "data-shot-id": shotId,
          "data-prompt-state": entry ? (stale && stale.stale ? "stale" : "saved") : "none",
        },
      });
      const head = createElement("div", { className: "shot-spec-head" });
      head.append(createElement("span", { className: "name", text: (index + 1) + ". " + item.label }));
      head.append(createElement("span", {
        className: "meta", text: entry ? "版本 v" + entry.version : "未编译",
      }));
      head.append(createElement("span", {
        className: item.satisfied ? "badge" : "badge is-critical",
        text: item.satisfied ? "可编译" : "缺依据",
      }));
      if (stale && stale.stale) {
        head.append(createElement("span", { className: "badge is-critical", text: "已过期" }));
      }
      if (entry && entry.record.origin === "manual_edit") {
        head.append(createElement("span", { className: "badge is-proposed", text: "人工编辑" }));
      }
      card.append(head);
      if (entry) {
        card.append(createElement("pre", {
          className: "prompt-text", text: entry.record.compiled.text,
        }));
        const refs = entry.record.compiled.source_refs || [];
        const provider = entry.record.compiled.provider || {};
        card.append(createElement("p", {
          className: "meta",
          text: "请求：" + (provider.model_id || "?") + " · " + (provider.size || "?")
            + " · 参考图 " + (entry.record.request_snapshot.references || []).length + " 张",
        }));
        card.append(createElement("p", {
          className: "meta prompt-meta",
          text: "来源 " + refs.length + " 条 · " + entry.record.compiled.text.length
            + " 字 · hash " + entry.record.hash.slice(0, 12) + "…",
        }));
        card.append(createElement("p", { className: "meta prompt-hash", text: entry.record.hash }));
        for (const warning of entry.record.compiled.warnings || []) {
          card.append(createElement("p", {
            className: "meta prompt-warning",
            text: "提示：" + localizeSlotTerms(warning.message),
          }));
        }
        if (entry.record.origin === "manual_edit") {
          card.append(createElement("p", {
            className: "meta",
            text: "人工编辑 v" + entry.version + "（原因：" + entry.record.edit_reason + "；被编辑版本 v"
              + (entry.record.edited_from ? entry.record.edited_from.version : "?") + " 保留）",
          }));
        }
        if (stale && stale.stale) {
          card.append(createElement("p", {
            className: "meta prompt-warning",
            text: "依据已变化（" + stale.reasons.map(reason => reason.field).join("、") + "）。"
              + (entry.record.origin === "manual_edit"
                ? "人工全文没有被覆盖；请按当前依据重新确认，或明确丢弃后重新准备。"
                : "系统会本地重新准备，不调用模型。"),
          }));
        }
      } else if (!item.satisfied) {
        card.append(createElement("p", {
          className: "meta", text: "暂时缺依据：" + suiteBlockingText(item.blocking),
        }));
      }
      const toolbar = createElement("div", { className: "toolbar" });
      const compileButton = createElement("button", {
        text: entry?.record.origin === "manual_edit" ? "丢弃人工全文并重新准备" : "重新本地准备",
        className: entry?.record.origin === "manual_edit" ? "danger" : "", attrs: { type: "button" },
      });
      compileButton.disabled = !item.satisfied || inputs.isAnalysisRunning();
      compileButton.addEventListener("click", () => {
        if (entry?.record.origin === "manual_edit") void handleDiscardManualPrompt(shotId);
        else void handleCompilePrompt(shotId);
      });
      toolbar.append(compileButton);
      let reconfirmButton = null;
      if (entry?.record.origin === "manual_edit" && stale?.stale) {
        reconfirmButton = createElement("button", {
          text: "按当前依据确认此人工全文", attrs: { type: "button" },
        });
        reconfirmButton.disabled = !item.satisfied || inputs.isAnalysisRunning();
        reconfirmButton.addEventListener("click", () => { void handleReconfirmManualPrompt(shotId); });
        toolbar.append(reconfirmButton);
      }
      card.append(toolbar);
      if (entry) {
        const draft = drafts.get(shotId) || null;
        const unsaved = draft !== null && draft.text !== entry.record.compiled.text;
        const block = createElement("div", { className: "prompt-edit-block" });
        block.append(createElement("label", {
          className: "meta",
          attrs: { for: "prompt-edit-" + shotId },
          text: "人工编辑全文（保存为新版本；原版本保留）",
        }));
        const area = createElement("textarea", {
          className: "prompt-edit-text",
          attrs: { id: "prompt-edit-" + shotId, "data-shot-id": shotId, rows: "6" },
        });
        area.value = draft && unsaved ? draft.text : entry.record.compiled.text;
        block.append(area);
        area.addEventListener("input", () => {
          if (reconfirmButton) reconfirmButton.disabled = !item.satisfied || inputs.isAnalysisRunning() || area.value !== entry.record.compiled.text;
        });
        block.append(createElement("label", {
          className: "meta",
          attrs: { for: "prompt-edit-reason-" + shotId },
          text: "编辑原因（必填，写入版本记录）",
        }));
        const reason = createElement("input", {
          className: "prompt-edit-reason",
          attrs: {
            id: "prompt-edit-reason-" + shotId, type: "text", autocomplete: "off",
            maxlength: String(MANUAL_EDIT_REASON_MAX),
          },
        });
        if (draft && unsaved && draft.reason) reason.value = draft.reason;
        block.append(reason);
        const saveEdit = createElement("button", { text: "保存为新版本", attrs: { type: "button" } });
        saveEdit.disabled = inputs.isAnalysisRunning();
        saveEdit.addEventListener("click", () => { handleSaveEditedPrompt(shotId); });
        block.append(saveEdit);
        card.append(block);
      }
      elements.promptList.append(card);
    });
  }


  /** 本地准备是 prompts Module 的动作；这里只传 DOM 草稿并呈现结果文案。 */
  async function prepareSystemPrompts() {
    if (!projectId || prompts.isPreparing()) return;
    const action = beginAction();
    if (!action.projectId) return;
    const gate = !inputs.suitePlan()
      ? "先添加图片任务；本地准备不会调用模型。"
      : (!understandingReady ? "请人工确认核心事实；各图片用途的额外缺项就地补足。"
        : (!currentImageProfile() ? "等待有效图像配置；打开模型设置可恢复。" : null));
    if (gate) {
      elements.localPreparationStatus.textContent = gate;
      return;
    }
    elements.localPreparationStatus.textContent = "正在本地准备已就绪图片任务；不会调用模型…";
    renderConfirm();
    try {
      const result = await prompts.prepare(capturePromptEdits());
      if (!action.alive()) return;
      if (result.reason === "no_plan" || result.reason === "facts" || result.reason === "configuration") {
        elements.localPreparationStatus.textContent = result.reason === "no_plan"
          ? "先添加图片任务；本地准备不会调用模型。"
          : result.reason === "facts" ? "请人工确认核心事实；各图片用途的额外缺项就地补足。"
            : "等待有效图像配置；打开模型设置可恢复。";
        return;
      }
      if (result.reason === "in_flight" || result.reason === "unchanged"
        || result.reason === "stale_session" || result.reason === "no_project") return;
      elements.localPreparationStatus.textContent = result.errors.length
        ? "部分任务尚未准备：" + result.errors.join("；")
        : "本地准备完成" + (result.prepared ? "（更新 " + result.prepared + " 张）" : "")
          + "；未调用模型。人工文本保留，提交前请核对下面的摘要。";
      await deriveAndApplyState();
    } finally {
      if (action.alive()) { renderPrompts(); renderConfirm(); renderAttempts(); }
    }
  }

  /**
   * @param {string} shotId
   * @returns {Promise<void>}
   */
  async function handleReconfirmManualPrompt(shotId) {
    const entry = promptRecordOf(shotId);
    if (!entry || entry.record.origin !== "manual_edit") return;
    const action = beginAction();
    const area = /** @type {HTMLTextAreaElement|null} */ (elements.promptList.querySelector('textarea.prompt-edit-text[data-shot-id="' + shotId + '"]'));
    if (area && area.value !== entry.record.compiled.text) {
      showError(elements.promptError, "此全文有未保存修改；先保存，再重新确认，不会确认另一份旧文本。");
      return;
    }
    clearError(elements.promptError);
    try {
      const saved = await prompts.reconfirm(shotId, area ? area.value : null, action);
      if (!saved) return;
      if (!action.alive()) return;
      renderPrompts(); renderConfirm(); renderAttempts();
      elements.promptStatus.textContent = "人工全文原文保留，已按当前依据重新确认为 v" + saved.version + "；未调用模型。";
    } catch (error) {
      if (action.alive()) showError(elements.promptError, errorMessageOf(error, "重新确认失败；原人工全文保留。"));
    }
  }

  /**
   * @param {string} shotId
   * @returns {Promise<void>}
   */
  async function handleDiscardManualPrompt(shotId) {
    const entry = promptRecordOf(shotId);
    if (!entry || entry.record.origin !== "manual_edit") return;
    const action = beginAction();
    const area = /** @type {HTMLTextAreaElement|null} */ (elements.promptList.querySelector('textarea.prompt-edit-text[data-shot-id="' + shotId + '"]'));
    const previousDraft = area?.value;
    clearError(elements.promptError);
    try {
      const payload = await prompts.discard(shotId, action);
      if (!action.alive() || !payload) return;
      if (area && area.value === previousDraft) area.value = payload.compiled.text;
      renderPrompts(); renderConfirm(); renderAttempts();
      elements.promptStatus.textContent = "已明确丢弃人工覆盖并恢复当前系统 Prompt；历史全文保留，未调用模型。";
    } catch (error) {
      if (action.alive()) showError(elements.promptError, errorMessageOf(error, "丢弃未完成；原全文与输入保留。"));
    }
  }

  /**
   * @param {string} shotId
   * @returns {Promise<void>}
   */
  async function handleCompilePrompt(shotId) {
    if (!projectId || !inputs.suitePlan() || !understandingReady) return;
    const action = beginAction();
    clearError(elements.promptError);
    try {
      const result = await prompts.compileAndSave(shotId, { action });
      if (!action.alive()) return;
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deriveAndApplyState();
      if (!action.alive()) return;
      elements.promptStatus.textContent = "已保存 " + shotId + " 的 Prompt 版本 v"
        + result.saved.version + "。";
    } catch (error) {
      if (!action.alive()) return;
      showError(elements.promptError,
        errorMessageSuffixed(error, "编译未完成，旧版本已保留。", "（旧版本已保留）"));
      renderPrompts();
      renderConfirm();
      renderAttempts();
    }
  }

  /** 人工编辑：保存为新版本；失败时保留旧版本与用户输入，不清空文本区。
   * @param {string} shotId
   * @returns {Promise<void>}
   */
  async function handleSaveEditedPrompt(shotId) {
    if (!projectId || !inputs.suitePlan() || !understandingReady) return;
    const action = beginAction();
    clearError(elements.promptError);
    const entry = promptRecordOf(shotId);
    if (!entry) {
      showError(elements.promptError, "先编译并保存这张图的 Prompt，再编辑。");
      return;
    }
    const area = /** @type {HTMLTextAreaElement|null} */ (document.getElementById("prompt-edit-" + shotId));
    const reasonInput = /** @type {HTMLInputElement|null} */ (document.getElementById("prompt-edit-reason-" + shotId));
    try {
      const saved = await prompts.edit(shotId, area ? area.value : "", reasonInput ? reasonInput.value : "", action);
      if (!action.alive()) return;
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deriveAndApplyState();
      if (!action.alive()) return;
      elements.promptStatus.textContent = "已保存 " + shotId + " 的人工编辑版本 v" + saved.version
        + "（被编辑版本 v" + entry.version + " 保留）。";
    } catch (error) {
      if (action.alive()) {
        showError(elements.promptError,
          errorMessageSuffixed(error, "编辑未保存，旧版本与输入已保留。", "（旧版本与输入已保留）"));
      }
    }
  }

  /* ---------------------------------------------------------- 生成前确认 */

  /**
   * 确认单投影：界面、状态派生与提交都读同一份，不各自重算。
   * shotIds 给定时只投影这些图（V2.5.4 单图返工），否则是整套。
   */
  /**
   * 确认单投影：界面、状态派生与提交都读同一份，不各自重算。
   * 唯一所有者是 prompts Module；这里只转发，不重建规则。
   * @param {string[]|null} shotIds
   * @returns {ConfirmationSheetView|null}
   */
  function buildScopedSheet(shotIds, { providerProfile = currentImageProfile() } = {}) {
    return /** @type {ConfirmationSheetView|null} */ (prompts.sheet(shotIds, providerProfile));
  }

  /**
   * @returns {ConfirmationSheetView|null}
   */
  function buildCurrentSheet() {
    return buildScopedSheet(null);
  }

  /**
   * 意图装配（薄装配层）：scope/mode/队列所有权在 generation Module（设计§2.1），
   * 确认单投影归 prompts；当前性/环境匹配的唯一判据也在 generation
   * （isConfirmedShotCurrent / confirmationTargetMatched），这里只转发，不重建规则。
   * @returns {WorkspaceGenerationIntent|null}
   */
  function buildGenerationIntent() {
    const batch = generation.deriveBatch();
    const queue = batch.queue && batch.queue.length ? batch.queue : batch.retry_queue;
    const intent = generation.intent({ queue: batch.queue, retry_queue: batch.retry_queue });
    if (!intent) return null;
    return /** @type {WorkspaceGenerationIntent|null} */ ({ ...intent, all: intent.all, sheet: intent.sheet });
  }

  /**
   * 单图当前性：转发 generation.isConfirmedShotCurrent（执行与按钮同一判据）。
   * @param {ConfirmationQueue} queue
   * @param {string} shotId
   * @returns {boolean}
   */
  function queueShotIsCurrent(queue, shotId) {
    return generation.isConfirmedShotCurrent(queue, shotId);
  }

  /** 确认记录是否仍然对得上「这一批将要提交的东西」。 */
  /** 确认记录是否仍然对得上「这一批将要提交的东西」。
   * @returns {boolean}
   */
  function confirmationIsCurrent() {
    const queue = generation.confirmed();
    return Boolean(queue?.payload?.fingerprint?.snapshot?.execution_target
      && queue.payload.shots.some((/** @type {{shot_id: string}} */ shot) => queueShotIsCurrent(queue, shot.shot_id)));
  }

  /**
   * 这张图的返工确认是否仍然有效：与整套确认同一套「快照逐字比对」判定，
   * 只是作用域只有这一张图——改别的图不会让它失效，改这张图一定会失效。
   */
  /**
   * 这张图的返工确认是否仍然有效：与整套确认同一套「快照逐字比对」判定，
   * 只是作用域只有这一张图——改别的图不会让它失效，改这张图一定会失效。
   * @param {string} shotId
   * @returns {boolean}
   */
  function reworkConfirmationIsCurrent(shotId) {
    const entry = generation.reworkEntry(shotId);
    return Boolean(entry && queueShotIsCurrent(entry, shotId));
  }
  /** 提交这张图的条件：这张图在某个现存授权队列里仍有效（generation 统一判据）。
   * @param {string|null} shotId
   * @returns {boolean}
   */
  function confirmationIsCurrentForShot(shotId) {
    if (!shotId) return false;
    return generation.shotHasCurrent(shotId);
  }

  /**
   * @returns {void}
   */
  function renderConfirm() {
    const ready = Boolean(inputs.suitePlan());
    elements.confirmLocked.hidden = ready;
    elements.confirmEditor.hidden = !ready;
    elements.confirmSummary.innerHTML = "";
    elements.confirmBlockers.innerHTML = "";
    elements.confirmRisks.innerHTML = "";
    elements.confirmList.innerHTML = "";
    elements.confirmRecord.textContent = "";
    elements.confirmAction.disabled = true;
    displayedGenerationIntent = null;
    if (!ready) return;
    /** @type {ConfirmationSheetView|null} */
    let sheet = null;
    try {
      displayedGenerationIntent = buildGenerationIntent();
      sheet = displayedGenerationIntent ? displayedGenerationIntent.all : null;
    } catch (error) {
      showError(elements.confirmError,
        "生成前确认投影失败：" + (errorMessageOf(error, "未知错误")));
      return;
    }
    if (!sheet || !displayedGenerationIntent) {
      elements.confirmStatus.textContent = "尚未取得有效图像能力；恢复服务后再确认，不会提交未经核对的请求。";
      return;
    }
    const intent = displayedGenerationIntent;
    const sending = intent.sheet;
    const sendingIds = new Set(sending?.shots.map(item => item.shot_id) || []);
    elements.confirmStatus.textContent = "本次明确发送 " + (sending?.total || 0) + " 张；"
      + "用途缺项／过期任务不外发；已有成功、进行中或 Unknown 不自动重提。";
    elements.confirmSummary.append(createElement("p", {
      className: "confirm-summary", text: sending ? sending.external_summary.statement : "当前没有可新增发送的已就绪图片任务。",
    }));
    if (generation.mode() === "explicit_new") {
      elements.confirmSummary.append(createElement("p", {
        className: "prompt-warning",
        text: "这是另一个新动作，不是核对原任务。原 Unknown 可能已经被受理，另发可能重复扣费；原记录与采用不删除、不覆盖。",
      }));
    }
    elements.confirmSummary.append(createElement("p", {
      className: "meta",
      text: "每张图发送自己的 Prompt 文本与上列参考图；不发送本地文件本身、历史候选或其他项目数据。",
    }));
    for (const blocker of sheet.blockers) {
      const row = createElement("p", { className: "confirm-blocker" });
      row.append(createElement("span", { text: "#" + blocker.order + " " + blocker.label + " · " + blocker.code }));
      row.append(createElement("span", { className: "meta", text: localizeSlotTerms(blocker.message) }));
      row.append(createElement("span", {
        className: "meta", text: "返回：" + blocker.fix.region + " · " + blocker.fix.action,
      }));
      const fix = createElement("button", { text: "去补足此项", attrs: { type: "button" } });
      fix.addEventListener("click", () => {
        const task = /** @type {Record<string, string>} */ ({ intake: "intake", understanding: "understand", suite: "plan",
          style: "generate", shot_spec: "generate", prompt: "generate" })[blocker.fix.region];
        stageShell.select(task);
        if (blocker.fix.region === "prompt") /** @type {HTMLDetailsElement} */ (document.getElementById("prompt-details")).open = true;
      });
      row.append(fix);
      elements.confirmBlockers.append(row);
    }
    for (const risk of sheet.risks) {
      elements.confirmRisks.append(createElement("p", {
        className: "confirm-risk",
        text: risk.label + " · " + risk.code + "：" + localizeSlotTerms(risk.message),
      }));
    }
    for (const item of sheet.shots) {
      const row = createElement("div", {
        className: "confirm-shot",
        attrs: { "data-shot-id": item.shot_id, "data-blocked": String(item.blockers.length > 0) },
      });
      const head = createElement("div", { className: "confirm-shot-head" });
      head.append(createElement("span", { className: "name", text: item.order + ". " + item.label }));
      head.append(createElement("span", {
        className: "badge",
        text: (item.role_label || item.role_id || "未分类") + (item.required ? " · 必需" : " · 可选"),
      }));
      head.append(createElement("span", {
        className: item.blockers.length > 0 ? "badge is-critical" : "badge is-confirmed",
        text: sendingIds.has(item.shot_id) ? "本次发送" : item.blockers.length ? "本次不发送：缺项／过期" : "本次不重复提交",
      }));
      head.append(createElement("span", {
        className: "meta",
        text: item.prompt.version === null
          ? "未编译"
          : "Prompt v" + item.prompt.version + " · " + String(item.prompt.hash).slice(0, 12) + "…",
      }));
      row.append(head);
      if (item.intent) row.append(createElement("p", { className: "meta", text: "任务：" + item.intent }));
      row.append(createElement("p", {
        className: "meta",
        text: "参考图 " + item.references.length + " 张（"
          + (item.references.map((ref) => /** @type {Record<string, string>} */ (ROLE_TEXT)[ref.role] || ref.role).join("、") || "无") + "）"
          + (item.prompt.chars === null ? "" : " · 提示词 " + item.prompt.chars + " 字"),
      }));
      const referenceTech = techDetails(item.references.map(
        (ref) => (/** @type {Record<string, string>} */ (ROLE_TEXT)[ref.role] || ref.role) + " sha256 " + ref.sha256_prefix));
      if (referenceTech) row.append(referenceTech);
      if (item.risks.length > 0) {
        row.append(createElement("p", {
          className: "meta prompt-warning",
          attrs: { title: item.risks.map((risk) => risk.code).join("、") },
          text: "风险：" + item.risks
            .map((risk) => localizeSlotTerms(risk.message || risk.code)).join("；"),
        }));
      }
      elements.confirmList.append(row);
    }
    const identity = intent.identity;
    elements.confirmAction.disabled = !sending?.can_submit || !identity?.configured || inputs.isAnalysisRunning()
      || prompts.isPreparing() || submissionInFlight || modelSettings.refreshing
      || Boolean(generation.batchStateReader()?.active);
    elements.confirmAction.textContent = (generation.mode() === "explicit_new" ? "确认并另发 " : "确认并生成 ")
      + (sending?.total || 0) + " 张";
    elements.confirmRecord.textContent = identity?.configured
      ? "一次点击先保存这份授权，再按摘要外发；不会要求第二次提交。"
      : "原目标凭据未就绪。打开模型设置补凭据；本地事实、Prompt、采用和导出不受影响。";
  }

  /**
   * @returns {Promise<void>}
   */
  async function handleConfirmGeneration() {
    if (!projectId || !inputs.suitePlan() || submissionInFlight || prompts.isPreparing() || modelSettings.refreshing) return;
    const authorized = displayedGenerationIntent;
    const action = beginAction();
    const expectedVersion = generation.confirmed()?.version || 0;
    submissionInFlight = true;
    elements.confirmAction.disabled = true;
    clearError(elements.confirmError);
    try {
      await generation.confirmAndRun(/** @type {import("./generation.js").ConfirmAndRunInput} */ ({
        intent: authorized, readIntent: buildGenerationIntent,
        documentId: CONFIRM_DOCUMENT_ID, expectedVersion, action,
      }));
    } catch (error) {
      if (action.alive()) showError(elements.confirmError, errorMessageOf(error, "生成没有完成；授权与历史保留。"));
    } finally {
      submissionInFlight = false;
      if (action.alive()) { renderConfirm(); renderAttempts(); }
    }
  }

  /* ------------------------------------------------------------ 生成执行 */

  /**
   * @param {string|null} shotId
   * @returns {{version: number, hash: string}|null}
   */
  function currentPromptPointer(shotId) {
    const entry = promptRecordOf(shotId);
    return entry ? { version: entry.version, hash: entry.record.hash } : null;
  }

  /**
   * @returns {import("./model-settings.js").ProviderCapability|null}
   */
  function imageProviderBlock() {
    const images = capabilities && capabilities.images ? capabilities.images : null;
    return images && images.provider ? images.provider : null;
  }

  /**
   * @param {unknown} state
   * @returns {string}
   */
  function attemptBadgeClass(state) {
    if (state === ATTEMPT_STATES.succeeded) return "is-attempt-done";
    if (state === ATTEMPT_STATES.failed) return "is-attempt-failed";
    if (state === ATTEMPT_STATES.unknown) return "is-attempt-unknown";
    return "is-attempt-active";
  }

  /**
   * @param {unknown} iso
   * @returns {string}
   */
  function shortTime(iso) {
    if (!iso) return "?";
    try {
      // Date 接受的输入是 string|number|Date；其余形状直接走下面的 String 回退。
      const date = new Date(/** @type {string | number | Date} */ (iso));
      return date.toLocaleString("zh-CN", { hour12: false });
    } catch (error) {
      return String(iso);
    }
  }

  /** 单张「保存候选图片」按钮入口：只翻译结果，不做批次策略。
   * @param {string} shotId
   * @returns {Promise<StoreCandidateResult>}
   */
  async function handleStoreCandidate(shotId) {
    clearAttemptError();
    const result = await generation.storeCandidate(shotId);
    if (result.stored) {
      elements.attemptStatus.textContent = "候选已保存（" + result.width + "×" + result.height + "）。"
        + (result.review ? " " + result.review : "");
    } else if (result.failed) {
      showAttemptError( result.message);
    } else if (result.reason === "already_stored") {
      elements.attemptStatus.textContent = "这条记录的候选已在本地，无需重复保存。";
    } else if (result.reason === "not_succeeded") {
      showAttemptError( "这次生成还没有成功结论，暂不能保存候选。");
    } else if (result.reason === "no_task_id") {
      showAttemptError( "这条记录没有任务编号，无法取回候选。");
    } else if (result.reason === "no_attempt") {
      showAttemptError( "这张图还没有生成记录。");
    }
    return result;
  }

  /** 预览 URL 缓存：每个候选一个 object URL，关闭项目时统一撤销。 */
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

  /* ------------------------------------------- 候选比较与审核清单（V2.5.3） */

  /**
   * 面板只是投影：候选、报告、参考图全部来自 IndexedDB 已经存在的事实，
   * 排序与默认目标由 domain/compare.js 决定（唯一权威），这里不重算报告、不写任何记录。
   */
  /**
   * @returns {Record<string, AttemptRecord>}
   */
  function attemptsByActionId() {
    /** @type {Record<string, AttemptRecord>} */
    const map = {};
    for (const record of generation.allAttemptRecords()) {
      if (record && typeof record.action_id === "string") map[record.action_id] = record;
    }
    return map;
  }

  /** 每张图的候选行（异常优先）+ 计划顺序；报告只在 reviewIsCurrent 为真时参与。 */
  /** 每张图的候选行（异常优先）+ 计划顺序；报告只在 reviewIsCurrent 为真时参与。
   * @returns {{shots: Array<{shot_id: string}>, rowsByShotId: Record<string, CompareInventoryRow[]>}}
   */
  function compareInventory() {
    const shots = inputs.suitePlan() ? suitePlanSummary(inputs.suitePlan(), inputs.suiteContext()).shots : [];
    /** @type {Record<string, CompareInventoryRow[]>} */
    const rowsByShotId = {};
    const attempts = attemptsByActionId();
    for (const item of shots) {
      const chain = generation.candidateChainOf(item.shot_id);
      /** @type {Record<string, ReviewReport>} */
      const reports = {};
      for (const entry of chain) {
        const candidate = entry.record;
        if (!candidate || typeof candidate.candidate_id !== "string") continue;
        const existing = selectionAdoption.reportOf(candidate.candidate_id);
        if (existing && reviewIsCurrent(existing.report, candidate)) {
          reports[candidate.candidate_id] = existing.report;
        }
      }
      rowsByShotId[item.shot_id] = compareRows({
        candidates: chain, reportsByCandidateId: reports, attemptsByActionId: attempts,
      });
    }
    return { shots, rowsByShotId };
  }

  /**
   * @param {string} candidateId
   * @returns {string}
   */
  function compareTabId(candidateId) {
    return "compare-tab-" + String(candidateId).replace(/[^A-Za-z0-9_-]/g, "-");
  }

  /**
   * @param {CompareInventoryRow} row
   * @returns {string}
   */
  function compareStateLabel(row) {
    return COMPARE_STATE_TEXT[row.review_state] || row.review_state;
  }

  /**
   * 返工入口的状态：只有「正看着一条有字节的候选」才可发起。
   * 这里只投影 candidate_id + sha256，不写任何记录（写记录在相邻的独立返工区）。
   */
  /**
   * @param {PlanShot|null} shot
   * @param {CompareInventoryRow|null} row
   * @returns {void}
   */
  function updateReworkEntry(shot, row) {
    const candidate = row && row.record ? row.record : null;
    const sha256 = row ? row.asset_sha256 : null;
    const available = Boolean(shot && candidate && sha256);
    elements.reworkOpen.disabled = !available;
    if (available && shot && row && candidate && sha256) {
      elements.reworkOpen.dataset.shotId = shot.shot_id;
      elements.reworkOpen.dataset.candidateId = row.candidate_id;
      elements.reworkOpen.dataset.candidateSha256 = sha256;
    } else {
      delete elements.reworkOpen.dataset.shotId;
      delete elements.reworkOpen.dataset.candidateId;
      delete elements.reworkOpen.dataset.candidateSha256;
    }
  }

  /**
   * @param {string} shotId
   * @param {{candidateId?: string|null, focus?: boolean}} [options]
   * @returns {void}
   */
  function openCompare(shotId, options = {}) {
    compareShotId = shotId;
    const previous = compareViews.get(projectId + ":" + shotId);
    compareCandidateId = options.candidateId || previous?.candidateId || null;
    compareBaselineId = previous?.baselineId || null;
    stageShell.select("review");
    renderCompare();
    if (options.focus === true) {
      const active = /** @type {HTMLButtonElement|null} */ (elements.compareCandidates.querySelector('[role="tab"][aria-selected="true"]'));
      if (active) active.focus();
    }
  }

  /** 切换查看目标：不改规则、不写存储，只换清单与 aria 选中态，避免重建列表时丢焦点。 */
  /** 切换查看目标：不改规则、不写存储，只换清单与 aria 选中态，避免重建列表时丢焦点。
   * @param {string|null} candidateId
   * @param {{focus?: boolean}} [options]
   * @returns {void}
   */
  function selectCompareCandidate(candidateId, options = {}) {
    // 换一条候选时收起返工区（它绑定打开那一刻的候选身份），草稿保留。
    if (reworkShotId !== null && candidateId !== compareCandidateId) {
      closeReworkPanel({ focusCandidate: false });
    }
    compareCandidateId = candidateId;
    const tabs = /** @type {NodeListOf<HTMLButtonElement>} */ (elements.compareCandidates.querySelectorAll('[role="tab"]'));
    for (const tab of tabs) {
      const selected = tab.dataset.candidateId === candidateId;
      tab.setAttribute("aria-selected", selected ? "true" : "false");
      tab.tabIndex = selected ? 0 : -1;
      if (selected && options.focus === true) tab.focus();
    }
    const inventory = compareInventory();
    const shotId = compareShotId;
    if (!shotId) return;
    const rows = inventory.rowsByShotId[shotId] || [];
    const shot = (inputs.suitePlan()?.shots || [])
      .find((item) => item && item.shot_id === shotId) || null;
      const row = rows.find((item) => item.candidate_id === candidateId) || null;
      renderCompareChecklist(shot, row);
    updateReworkEntry(shot, row);
    updateAdoptEntry(shot, row);
    elements.compareStatus.textContent = "";
    void renderCompareImages(rows);
    if (shot) void refreshCompareReferences(shot).catch(handleInternalError);
  }

  /**
   * @returns {void}
   */
  function renderCompare() {
    const ready = Boolean(inputs.suitePlan());
    if (!ready || !compareShotId) {
      elements.comparePanel.hidden = true;
      elements.compareCandidates.innerHTML = "";
      elements.compareChecklist.innerHTML = "";
      elements.compareReferences.innerHTML = "";
      elements.compareBasisTitle.textContent = "";
      closeReworkPanel({ focusCandidate: false });
      updateReworkEntry(null, null);
      updateAdoptEntry(null, null);
      return;
    }
    const shotId = compareShotId;
    const shot = (inputs.suitePlan()?.shots || [])
      .find((item) => item && item.shot_id === shotId) || null;
    if (!shot) {
      compareShotId = null;
      renderCompare();
      return;
    }
    const inventory = compareInventory();
    const rows = inventory.rowsByShotId[shotId] || [];
    if (!rows.length) {
      compareShotId = null;
      renderCompare();
      return;
    }
    const targetId = rows.some((row) => row.candidate_id === compareCandidateId)
      ? compareCandidateId : defaultCompareTargetId(rows);
    compareCandidateId = targetId;
    elements.comparePanel.dataset.compareContract = COMPARE_CONTRACT_VERSION;
    elements.comparePanel.dataset.shotId = shotId;
    elements.comparePanel.hidden = false;
    const counts = compareCounts(rows);
    const parts = ["候选 " + counts.total];
    if (counts.pending) parts.push("待处理 " + counts.pending);
    if (counts.unknown) parts.push("未知 " + counts.unknown);
    if (counts.unchecked) parts.push("未检查 " + counts.unchecked);
    elements.compareSubject.textContent = shotLabelOf(shotId) + " · " + parts.join(" · ");
    const nextShot = nextPendingShotId({
      rowsByShotId: inventory.rowsByShotId,
      shotOrder: inventory.shots.map((item) => item.shot_id),
      currentShotId: shotId,
    });
    elements.compareJump.disabled = !nextShot;
    elements.compareJump.dataset.targetShot = nextShot || "";
    elements.compareStatus.textContent = "";
    renderCompareCandidates(rows, targetId);
    const targetRow = rows.find((row) => row.candidate_id === targetId) || null;
    renderCompareChecklist(shot, targetRow);
    updateReworkEntry(shot, targetRow);
    void renderCompareImages(rows);
    updateAdoptEntry(shot, targetRow);
    refreshCompareReferences(shot).catch(handleInternalError);
  }

  /**
   * @returns {void}
   */
  function rememberCompareView() {
    if (projectId && compareShotId) compareViews.set(projectId + ":" + compareShotId, {
      candidateId: compareCandidateId, baselineId: compareBaselineId,
    });
  }

  /**
   * @param {CompareInventoryRow[]} rows
   * @returns {Promise<void>}
   */
  async function renderCompareImages(rows) {
    const token = ++compareImageToken;
    const viewed = rows.find(row => row.candidate_id === compareCandidateId);
    const comparison = rows.find(row => row.candidate_id === compareBaselineId);
    if (!comparison || comparison.candidate_id === compareCandidateId) compareBaselineId = null;
    const select = elements.compareBaselineSelect;
    select.replaceChildren(createElement("option", { text: "不指定对照", attrs: { value: "" } }));
    for (const row of rows) {
      if (row.candidate_id === compareCandidateId) continue;
      const current = compareShotId;
      select.append(createElement("option", {
        text: "候选 v" + row.version + (current && adoptedMarkOf(current)?.candidate_id === row.candidate_id ? " · 已采用" : ""),
        attrs: { value: row.candidate_id },
      }));
    }
    select.value = compareBaselineId || "";
    rememberCompareView();
    const currentShot = compareShotId;
    const adopted = currentShot ? adoptedMarkOf(currentShot) : null;
    elements.compareViewedCaption.textContent = "当前查看：候选 v" + (viewed?.version || "?")
      + (adopted?.candidate_id === compareCandidateId ? " · 已采用" : " · 未采用此候选")
      + "；查看和对照不会改选。";
    const reviewShotId = compareShotId;
    elements.compareReview.disabled = !viewed || !reviewShotId || selectionAdoption.isReviewInFlight(reviewShotId)
    for (const { row, image, zoom } of [
      { row: viewed, image: elements.compareViewedImage, zoom: elements.compareViewedZoom },
      { row: compareBaselineId ? comparison : null, image: elements.compareBaselineImage, zoom: elements.compareBaselineZoom },
    ]) {
      image.hidden = true; image.removeAttribute("src"); zoom.disabled = true;
      if (!row) continue;
      const url = await ensurePreviewUrl(row.shot_id, row.candidate_id, row.asset_sha256);
      if (token !== compareImageToken) return;
      if (!url) { elements.compareStatus.textContent = "候选字节缺失；请恢复项目包，不会用另一张图片替代。"; continue; }
      image.src = url; image.hidden = false; image.dataset.candidateId = row.candidate_id;
      zoom.disabled = false;
    }
  }

  /**
   * @param {string} src
   * @param {string} label
   * @returns {void}
   */
  function openImageZoom(src, label) {
    if (!src) return;
    imageZoomReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    elements.imageZoomContent.src = src;
    elements.imageZoomContent.alt = label;
    elements.imageZoomContent.classList.remove("at-native-size");
    elements.imageZoomTitle.textContent = label;
    elements.imageZoomNative.textContent = "100% 像素";
    elements.imageZoomDialog.showModal();
    elements.imageZoomClose.focus();
  }

  /**
   * @returns {void}
   */
  function closeImageZoom() {
    elements.imageZoomDialog.close();
    elements.imageZoomContent.removeAttribute("src");
    if (imageZoomReturnFocus?.isConnected) imageZoomReturnFocus.focus();
  }

  /**
   * @param {CompareInventoryRow[]} rows
   * @param {string|null} targetId
   * @returns {void}
   */
  function renderCompareCandidates(rows, targetId) {
    const list = elements.compareCandidates;
    list.innerHTML = "";
    for (const row of rows) {
      const card = createElement("button", {
        className: "compare-card",
        attrs: {
          type: "button", role: "tab", id: compareTabId(row.candidate_id),
          "aria-selected": row.candidate_id === targetId ? "true" : "false",
          "aria-controls": "compare-checklist",
          "data-candidate-id": row.candidate_id,
          "data-review-state": row.review_state,
          tabindex: row.candidate_id === targetId ? "0" : "-1",
        },
      });
      const thumb = createElement("img", {
        attrs: { alt: "候选 v" + (row.version || "?") + " 预览", loading: "lazy" },
      });
      ensurePreviewUrl(row.shot_id, row.candidate_id, row.asset_sha256).then((url) => {
        if (url && card.isConnected) thumb.setAttribute("src", url);
      }).catch(() => {});
      card.append(thumb);
      const main = createElement("div", { className: "compare-card-main" });
      const head = createElement("div", { className: "compare-card-head" });
      head.append(createElement("span", {
        className: "name", text: "候选 v" + (row.version === null ? "?" : row.version),
      }));
      head.append(createElement("span", {
        className: "badge " + (/** @type {Record<string, string>} */ (COMPARE_STATE_BADGE)[row.review_state] || "is-review-unchecked"),
        text: compareStateLabel(row),
      }));
      const adopted = compareShotId ? adoptedMarkOf(compareShotId) : null;
      if (adopted && adopted.candidate_id === row.candidate_id) {
        head.append(createElement("span", {
          className: "badge is-adopted",
          attrs: { "data-adopted": adopted.state },
          text: adopted.state === "current" ? "已采用" : "已采用（已过期）",
        }));
      }
      main.append(head);
      const business = [];
      if (row.width && row.height) business.push(row.width + "×" + row.height);
      if (row.created_at) business.push(shortTime(row.created_at));
      main.append(createElement("span", { className: "meta", text: business.join(" · ") }));
      main.append(createElement("p", { className: "compare-headline", text: compareRowHeadline(row) }));
      card.append(main);
      card.addEventListener("click", () => { selectCompareCandidate(row.candidate_id); });
      // tablist 的直接子节点必须是 tab；技术详情放在右侧 tabpanel 的清单底部，
      // 既不嵌套交互控件，也不破坏 tabs 语义。
      list.append(card);
    }
  }

  /**
   * @param {ReviewFinding} finding
   * @returns {HTMLLIElement}
   */
  function compareFindingRow(finding) {
    const item = createElement("li", {
      className: "compare-finding",
      attrs: { "data-severity": finding.severity, "data-rule-id": finding.rule_id },
    });
    const head = createElement("div", { className: "compare-card-head" });
    head.append(createElement("span", {
      className: "badge " + (/** @type {Record<string, string>} */ (SEVERITY_BADGE)[finding.severity] || "is-review-unknown"),
      text: COMPARE_SEVERITY_TEXT[finding.severity] || finding.severity,
    }));
    head.append(createElement("span", { className: "name", text: finding.title }));
    head.append(createElement("span", {
      className: "meta", text: finding.rule_id + " · v" + finding.rule_version,
    }));
    item.append(head);
    item.append(createElement("p", { className: "meta", text: finding.detail }));
    if (finding.measured !== null && finding.measured !== undefined) {
      item.append(createElement("p", {
        className: "meta", text: "实测：" + JSON.stringify(finding.measured).slice(0, 160),
      }));
    }
    return item;
  }

  /** 审核清单 = 当前候选的待处理发现（异常优先）+ 这张图的验收依据 + 按需展开的完整报告。 */
  /** 审核清单 = 当前候选的待处理发现（异常优先）+ 这张图的验收依据 + 按需展开的完整报告。
   * @param {PlanShot|null} shot
   * @param {CompareInventoryRow|null} row
   * @returns {void}
   */
  function renderCompareChecklist(shot, row) {
    const box = elements.compareChecklist;
    box.innerHTML = "";
    box.setAttribute("aria-labelledby", row ? compareTabId(row.candidate_id) : "compare-title");
    if (!row) {
      box.append(createElement("p", { className: "meta", text: "先选择一个候选。" }));
      return;
    }
    box.dataset.compareState = row.review_state;
    box.dataset.candidateId = row.candidate_id;
    const report = row.report;
    if (report) {
      const findings = sortFindings(report.findings);
      const actionable = findings.filter((item) => item.severity !== "PASS");
      if (actionable.length) {
        box.append(createElement("h5", { text: "先看这些（" + actionable.length + "）" }));
        const list = createElement("ul", { className: "compare-findings" });
        for (const finding of actionable) list.append(compareFindingRow(finding));
        box.append(list);
      } else {
        // 没有待处理项时，这里一句话说明状态就够；细节在完整报告里。
        box.append(createElement("p", {
          className: "meta", text: compareRowHeadline(row),
        }));
      }
      const details = createElement("details", { className: "compare-report" });
      details.append(createElement("summary", {
        text: "完整报告（合同 " + report.review_contract_version + " · " + findings.length + " 条）",
      }));
      details.append(createElement("p", {
        className: "compare-report-row",
        text: "候选 sha256 " + String(row.asset_sha256).slice(0, 16) + "… · 报告生成 "
          + shortTime(report.created_at),
      }));
      const vlm = report.vlm;
      const vlmText = vlm
        ? (vlm.outcome === "checked" ? "已完成" : "未完成（结果未知，不阻断人工审核）")
        : "未检查";
      details.append(createElement("p", {
        className: "compare-report-row",
        attrs: { "data-compare-vlm": vlm ? vlm.outcome : "absent" },
        text: "视觉复核：" + vlmText + (vlm && vlm.model_id ? " · " + vlm.model_id : ""),
      }));
      const all = createElement("ul", { className: "compare-findings" });
      for (const finding of findings) all.append(compareFindingRow(finding));
      details.append(all);
      box.append(details);
    } else {
      box.append(createElement("p", { className: "meta", text: compareRowHeadline(row) }));
    }
    box.append(createElement("h5", { text: "这张图的验收依据" }));
    if (!shot) return;
    const specEntry = inputs.shotSpecEntry(shot.shot_id);
    const checklist = reviewChecklist(shot, {
      shotSpec: specEntry ? specEntry.spec : null, styleSpec: inputs.styleSpec(),
    });
    const criteria = createElement("ul", { className: "compare-basis-list" });
    criteria.append(createElement("li", { text: "目的：" + checklist.purpose }));
    if (checklist.must_keep.length) {
      criteria.append(createElement("li", { text: "必须保持：" + checklist.must_keep.join("；") }));
    }
    if (checklist.may_change.length) {
      criteria.append(createElement("li", { text: "允许变化：" + checklist.may_change.join("；") }));
    }
    if (checklist.style_lines.length) {
      criteria.append(createElement("li", { text: "公共风格：" + checklist.style_lines.join("；") }));
    }
    if (!checklist.saved) {
      criteria.append(createElement("li", {
        className: "meta", text: "单图规格尚未保存，这里用的是默认派生值。",
      }));
    }
    box.append(criteria);
    const techLines = [
      "candidate " + String(row.candidate_id),
      "sha256 " + String(row.asset_sha256).slice(0, 12) + "…",
    ];
    if (row.task_id) techLines.push("task " + String(row.task_id).slice(0, 8));
    else if (row.attempt_action_id) techLines.push("action " + String(row.attempt_action_id).slice(0, 8));
    const tech = techDetails(techLines);
    if (tech) box.append(tech);
  }

  /** 这张图实际会发送的参考图（与提交时同一选择函数），用作比较的左边一栏。 */
  /** 这张图实际会发送的参考图（与提交时同一选择函数），用作比较的左边一栏。
   * @param {PlanShot} shot
   * @returns {Promise<void>}
   */
  async function refreshCompareReferences(shot) {
    const token = ++compareToken;
    const pid = projectId;
    const viewed = adoptSourceOf(shot.shot_id, compareCandidateId)?.candidate;
    const origin = viewed ? attemptsByActionId()[viewed.action_id] : null;
    const references = origin?.references || [];
    const entries = /** @type {Array<{reference: {sha256: string, role: string}, asset: import("./storage/validate.js").StoredAssetRecord|null|undefined}>} */ ([]);
    for (const reference of references) {
      if (!pid) continue;
      const asset = await repository.assets.get(pid, reference.sha256);
      entries.push({ reference, asset });
    }
    if (token !== compareToken || pid !== projectId) return;
    const list = elements.compareReferences;
    list.innerHTML = "";
    if (!entries.length) {
      elements.compareBasisTitle.textContent = "找不到当前候选的原参考图来源链；不会用当前新资料冒充原图。";
      return;
    }
    elements.compareBasisTitle.textContent = "当前候选原任务参考图（" + entries.length + " 张）；均按原比例展示。";
    for (const entry of entries) {
      const item = createElement("li", { attrs: { "data-reference-sha256": entry.reference.sha256 } });
      const url = await ensurePreviewUrl("参考图", entry.reference.sha256, entry.reference.sha256);
      if (token !== compareToken) return;
      if (url) {
        item.append(createElement("img", {
          attrs: { src: url, alt: "参考图 " + entry.reference.role, loading: "lazy" },
        }));
        const zoom = createElement("button", { text: "放大参考原图", attrs: { type: "button" } });
        zoom.addEventListener("click", () => openImageZoom(url, "参考原图 · " + (/** @type {Record<string, string>} */ (ROLE_TEXT)[entry.reference.role] || entry.reference.role)));
        item.append(zoom);
      } else {
        item.append(createElement("span", { className: "meta", text: "资产缺失" }));
      }
      item.append(createElement("span", {
        className: "meta", text: /** @type {Record<string, string>} */ (ROLE_TEXT)[entry.reference.role] || entry.reference.role,
      }));
      appendTech(item, ["sha256 " + String(entry.reference.sha256).slice(0, 8) + "…"]);
      list.append(item);
    }
  }

  /**
   * @param {KeyboardEvent} event
   * @returns {void}
   */
  function handleCompareKeydown(event) {
    const tabs = Array.from(/** @type {NodeListOf<HTMLButtonElement>} */ (elements.compareCandidates.querySelectorAll('[role="tab"]')));
    if (!tabs.length) return;
    const current = tabs.findIndex((tab) => tab.getAttribute("aria-selected") === "true");
    const index = current === -1 ? 0 : current;
    let next = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      next = (index - 1 + tabs.length) % tabs.length;
    } else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else if (event.key === "Escape") {
      event.preventDefault();
      focusCompareEntry(compareShotId);
      return;
    } else {
      return;
    }
    event.preventDefault();
    selectCompareCandidate(tabs[next]?.dataset.candidateId ?? null, { focus: true });
  }

  /**
   * @returns {void}
   */
  function renderAttempts() {
    const ready = Boolean(inputs.suitePlan());
    elements.attemptLocked.hidden = ready;
    elements.attemptEditor.hidden = !ready;
    elements.attemptList.innerHTML = "";
    if (!ready) { renderBatch(); renderCompare(); renderSelectionProgress(); return; }
    const summary = suitePlanSummary(inputs.suitePlan(), inputs.suiteContext());
    const confirmed = confirmationIsCurrent();
    const provider = imageProviderBlock();
    elements.attemptProvider.textContent = provider
      ? "图像 provider：" + (provider.provider_id || "未声明") + " · " + (provider.model_id || "未声明")
        + (provider.configured === false ? " · 未配置（提交会被拒绝，不会调用模型）" : " · 已配置")
      : "图像 provider：尚未读到能力信息；提交前请确认服务端可用。";
    const counts = { total: 0, none: 0, active: 0, succeeded: 0, failed: 0, unknown: 0 };
    const shots = summary ? summary.shots : [];
    for (const item of shots) {
      const chain = generation.attemptChainOf(item.shot_id);
      const latest = generation.latestAttemptOf(item.shot_id);
      const record = latest ? latest.record : null;
      const state = record ? record.state : null;
      const entry = promptRecordOf(item.shot_id);
      const stale = record ? attemptPromptStaleness(record, currentPromptPointer(item.shot_id)) : null;
      counts.total += 1;
      if (!record) counts.none += 1;
      else if (state === ATTEMPT_STATES.succeeded) counts.succeeded += 1;
      else if (state === ATTEMPT_STATES.failed) counts.failed += 1;
      else if (state === ATTEMPT_STATES.unknown) counts.unknown += 1;
      else counts.active += 1;

      const rowShotId = item.shot_id;
      const row = createElement("div", {
        className: "attempt-row",
        attrs: { "data-shot-id": rowShotId, "data-attempt-state": state || "none",
                 "tabindex": "-1" },
      });
      const head = createElement("div", { className: "attempt-head" });
      head.append(createElement("span", { className: "name", text: item.label }));
      head.append(createElement("span", {
        className: "badge " + (record ? attemptBadgeClass(state) : "is-missing"),
        text: record ? attemptStateLabel(state) : "尚未生成",
      }));
      head.append(createElement("span", {
        className: "meta",
        text: entry ? "Prompt v" + entry.version : "未编译 Prompt",
      }));
      if (stale && stale.stale) {
        head.append(createElement("span", {
          className: "badge is-attempt-stale",
          text: "基于旧版本 v" + stale.attempt_version,
        }));
      }
      row.append(head);
      if (entry) {
        const promptTech = techDetails(["hash " + String(entry.record.hash).slice(0, 12) + "…"]);
        if (promptTech) row.append(promptTech);
      }
      if (record) {
        const parts = ["提交 " + shortTime(record.created_at)];
        if (record.updated_at !== record.created_at) parts.push("更新 " + shortTime(record.updated_at));
        row.append(createElement("p", { className: "meta attempt-task", text: parts.join(" · ") }));
        const attemptTech = ["action " + record.action_id];
        if (record.task_id) attemptTech.push("task " + record.task_id);
        appendTech(row, attemptTech);
        const note = record.change_log.length
          ? record.change_log[record.change_log.length - 1].note : null;
        if (note) row.append(createElement("p", { className: "meta", text: "最近一次变化：" + note }));
        if (record.error) {
          row.append(createElement("p", {
            className: "attempt-error-text",
            text: (state === ATTEMPT_STATES.unknown ? "未知原因：" : "失败原因：")
              + record.error.family + " / " + record.error.code + "：" + record.error.message
              + "（重试策略 " + record.error.retry_policy + "）",
          }));
        }
        if (state === ATTEMPT_STATES.succeeded) {
          const stored = generation.candidateForAttemptOf(item.shot_id, record.action_id);
          if (stored && candidateMatchesAttempt(stored, record)) {
            const candidate = stored.record;
            const thumb = createElement("div", { className: "attempt-preview" });
            const img = createElement("img", {
              attrs: { alt: item.label + " 的候选", loading: "lazy" },
            });
            thumb.append(img);
            row.append(thumb);
            ensurePreviewUrl(item.shot_id, record.action_id, candidate.asset_sha256)
              .then((url) => {
                if (url && img.isConnected) img.src = url;
              })
              .catch(() => {});
            row.append(createElement("p", {
              className: "meta attempt-candidate",
              text: "候选已保存到本地 · " + candidate.width + "×" + candidate.height + " · "
                + candidate.media_type + " · "
                + Math.max(1, Math.round(candidate.byte_size / 1024)) + " KB（预览来自本地字节）",
            }));
            appendTech(row, ["sha256 " + candidate.asset_sha256.slice(0, 12) + "…"]);
            const reviewEntry = selectionAdoption.reportOf(candidate.candidate_id);
            if (reviewEntry && reviewIsCurrent(reviewEntry.report, candidate)) {
              const top = topFinding(reviewEntry.report);
              row.append(createElement("p", {
                className: "meta attempt-review",
                attrs: {
                  "data-review-summary": reviewSummaryText(reviewEntry.report),
                  "data-review-contract": reviewEntry.report.review_contract_version,
                  "data-review-candidate": candidate.candidate_id,
                },
                text: reviewSummaryText(reviewEntry.report)
                  + (top ? " · 先看：" + top.title + " — " + top.detail : " · 无待处理项"),
              }));
            } else {
              row.append(createElement("p", {
                className: "meta attempt-review",
                attrs: { "data-review-summary": "missing" },
                text: "自动检查报告尚未生成（候选保存时自动生成；旧候选会在重新打开项目时补建）。",
              }));
            }
            const reviewButton = createElement("button", {
              text: rowShotId && selectionAdoption.isReviewInFlight(rowShotId) ? "复核中…" : "AI 复核这条候选（可选）",
              attrs: {
                type: "button",
                "data-review-action": candidate.candidate_id,
                title: "调用视觉语言模型找可疑问题；只提示，不自动采纳",
              },
            });
            reviewButton.disabled = Boolean(!rowShotId || selectionAdoption.isReviewInFlight(rowShotId))
              || !capabilities?.review?.provider || capabilities.review.provider.configured === false;
            reviewButton.addEventListener("click", async () => {
              if (!rowShotId) return;
              const outcome = await selectionAdoption.reviewCandidate(rowShotId, candidate.candidate_id);
              if (outcome && outcome.failed) {
                elements.attemptStatus.textContent = "复核未完成：" + outcome.message
                  + "（候选与报告保持不变）";
              }
            });
            row.append(reviewButton);
          } else if (stored) {
            row.append(createElement("p", {
              className: "meta attempt-note",
              text: "候选记录与来源 Attempt 不一致：不显示预览（记录保留，等待复核）。",
            }));
          } else {
            row.append(createElement("p", {
              className: "meta attempt-note",
              text: "上游已完成，候选字节尚未保存到本地。",
            }));
          }
        }
        // 比较区只看候选链：最新一次尝试是失败/未知时，历史候选仍然可以比较与返工。
        if (generation.candidateChainOf(rowShotId).length) {
          const compareButton = createElement("button", {
            text: "比较候选（" + generation.candidateChainOf(rowShotId).length + "）",
            attrs: {
              type: "button",
              "data-compare-action": rowShotId,
              "aria-expanded": String(compareShotId === rowShotId),
              title: "对比这张图的参考图、历史候选与审核清单",
            },
          });
          compareButton.addEventListener("click", (event) => {
            if (!rowShotId) return;
            openCompare(rowShotId, { focus: event.detail === 0 });
          });
          row.append(compareButton);
        }
        const selectionEntry = rowShotId ? selectionAdoption.entryOf(rowShotId) : null;
        const selectionState = rowShotId ? selectionAdoption.stateOf(rowShotId) : "none";
        if (selectionEntry || (rowShotId && generation.candidateChainOf(rowShotId).length)) {
          row.append(createElement("p", {
            className: "meta attempt-selection",
            attrs: {
              "data-selection-state": selectionState,
              "data-selection-shot": item.shot_id,
            },
            text: selectionSummaryText(selectionEntry ? selectionEntry.record : null, selectionState),
          }));
        }
        if ((state === ATTEMPT_STATES.pending_submit || state === ATTEMPT_STATES.unknown)
            && !record.task_id) {
          row.append(createElement("p", {
            className: "meta attempt-note",
            text: "这次提交没有留下任务编号（可能已到达上游）。系统不会自动重提；可以显式新建 action，或先核对（若已有编号）。",
          }));
        }
      }
      if (stale && stale.stale) {
        row.append(createElement("p", {
          className: "meta attempt-note",
          text: "这条记录基于 Prompt v" + stale.attempt_version + "；当前是 v" + stale.current_version
            + "。要按新版出图，请先重新确认，再新建 action。",
        }));
      }
      const actions = createElement("div", { className: "toolbar attempt-actions" });
      const batchState = generation.batchStateReader();
      const batchActive = Boolean(batchState && batchState.active);
      const inFlight = (rowShotId ? generation.isAttemptInFlight(rowShotId) : false) || inputs.isAnalysisRunning() || batchActive;
      const shotConfirmed = confirmationIsCurrentForShot(rowShotId);
      const canSubmit = shotConfirmed && Boolean(entry) && !inFlight;
      const reconcileMode = record ? attemptReconcileMode(record) : ATTEMPT_RECONCILE_MODES.none;
      const stuckPending = state === ATTEMPT_STATES.pending_submit && record && !record.task_id;
      if (reconcileMode === ATTEMPT_RECONCILE_MODES.by_task && record) {
        const environment = attemptCurrentEnvironmentIdentity(modelSettings.imageEnvironment(
          record.provider.provider_id, record.execution_identity.credential_reference.source));
        const gate = attemptReconcileEnvironment(record, environment);
        if (gate.mode !== ATTEMPT_RECONCILE_MODES.by_task) {
          actions.append(createElement("p", {
            className: "meta", text: attemptReconcileBlockedMessage(record),
          }));
          const credentials = createElement("button", {
            text: record.execution_identity.credential_reference.source === "byok"
              ? "给原目标补凭据" : "查看原目标配置",
            attrs: { type: "button", "data-original-credentials": item.shot_id },
          });
          credentials.addEventListener("click", () => modelSettings.open("image",
            record.execution_identity.credential_reference.source === "byok"
              ? record.provider.provider_id : undefined));
          actions.append(credentials);
        }
        const button = createElement("button", { text: "核对任务", attrs: { type: "button" } });
        button.disabled = inFlight || gate.mode !== ATTEMPT_RECONCILE_MODES.by_task;
        button.addEventListener("click", () => { handleReconcileAttempt(rowShotId); });
        actions.append(button);
      }
      if (!record) {
        const button = createElement("button", {
          className: "primary", text: "生成这张图", attrs: { type: "button" },
        });
        button.disabled = !canSubmit;
        button.addEventListener("click", () => { handleSubmitAttempt(rowShotId); });
        actions.append(button);
      } else if (stuckPending || state === ATTEMPT_STATES.unknown) {
        const button = createElement("button", {
          text: "新建 action（放弃核对）", attrs: { type: "button" },
        });
        button.disabled = !entry || inFlight;
        button.addEventListener("click", () => {
          handleSubmitAttempt(rowShotId, { explicitNew: true });
        });
        actions.append(button);
      } else if (state === ATTEMPT_STATES.failed) {
        const button = createElement("button", {
          text: "重试（新建 action）", attrs: { type: "button" },
        });
        button.disabled = !entry || inFlight;
        button.addEventListener("click", () => {
          handleSubmitAttempt(rowShotId, { explicitNew: true });
        });
        actions.append(button);
      } else if (state === ATTEMPT_STATES.succeeded) {
        const stored = generation.candidateForAttemptOf(rowShotId, record.action_id);
        if (!stored) {
          const save = createElement("button", {
            className: "primary", text: "保存候选图片", attrs: { type: "button" },
          });
          save.disabled = inFlight || (rowShotId ? generation.isCandidateInFlight(rowShotId) : false);
          save.addEventListener("click", () => { handleStoreCandidate(rowShotId); });
          actions.append(save);
        }
        const button = createElement("button", {
          text: "再生成一张（新建 action）", attrs: { type: "button" },
        });
        button.disabled = !entry || inFlight;
        button.addEventListener("click", () => {
          handleSubmitAttempt(rowShotId, { explicitNew: true });
        });
        actions.append(button);
      } else if (record && state && ATTEMPT_ACTIVE_STATES.includes(state)) {
        const label = inFlight ? "提交中…" : "上游处理中，先核对";
        const button = createElement("button", { text: label, attrs: { type: "button" } });
        button.disabled = true;
        actions.append(button);
      }
      if (!shotConfirmed) {
        actions.append(createElement("span", {
          className: "meta",
          text: "这张图还没有有效的生成前确认：先在「生成前确认」确认整套，或在候选比较面板里走一次返工确认。",
        }));
      } else if (!entry) {
        actions.append(createElement("span", { className: "meta", text: "先编译并保存这张图的 Prompt。" }));
      }
      row.append(actions);
      if (chain.length > 1) {
        const details = createElement("details", { className: "attempt-history" });
        details.append(createElement("summary", { text: "历史 " + chain.length + " 条状态记录（提交与核对均追加保留）" }));
        for (const item2 of chain.slice().reverse()) {
          const itemRecord = item2.record;
          details.append(createElement("p", {
            className: "attempt-history-row",
            text: "v" + item2.version + " · " + attemptStateLabel(itemRecord.state)
              + " · action " + itemRecord.action_id
              + (itemRecord.task_id ? " · task " + itemRecord.task_id : "")
              + " · " + shortTime(itemRecord.updated_at),
          }));
        }
        row.append(details);
      }
      elements.attemptList.append(row);
    }
    const activeText = counts.active > 0 ? "进行中 " + counts.active + " 张；" : "";
    elements.attemptStatus.textContent = "共 " + counts.total + " 张；未生成 " + counts.none + " 张；"
      + activeText + "已成功 " + counts.succeeded + " 张；结果未知 " + counts.unknown + " 张；失败 "
      + counts.failed + " 张。" + (confirmed ? "可以整套生成或逐张提交。" : "确认缺失或已过期，暂不能提交。");
    renderBatch();
    renderCompare();
    renderSelectionProgress();
    refreshDerived();
  }

  /** 单张提交（按钮入口）：只负责把核心结果翻译成界面反馈，执行顺序在生成 Module。 */
  /** 单张提交（按钮入口）：只负责把核心结果翻译成界面反馈，执行顺序在生成 Module。
   * @param {string|null} shotId
   * @param {import("./generation.js").SubmitAttemptOptions} [options]
   * @returns {Promise<import("./generation.js").SubmitAttemptResult|undefined>}
   */
  async function handleSubmitAttempt(shotId, options = {}) {
    if (!shotId) return;
    const action = options.action || beginAction();
    if (options.explicitNew) {
      generation.enterExplicitNew(shotId);
      stageShell.select("generate");
      renderConfirm();
      elements.confirmAction.focus();
      return;
    }
    clearAttemptError();
    const outcome = await generation.submitAttempt(shotId, { ...options, action });
    if (!action.alive()) return outcome;
    if (outcome.skipped) {
      if (outcome.reason === "no_confirmation") {
        showAttemptError(
          "生成前确认缺失或已过期：先回到「生成前确认」重新确认，再提交。");
      } else if (outcome.reason === "blocked") {
        const blocking = outcome.blocking;
        if (blocking) {
          showAttemptError( "同一张图已经有一条进行中的生成（"
            + attemptStateLabel(blocking.state) + "，action " + blocking.action_id
            + "）。先核对并按结论处理，再新建 action。");
        }
      } else if (outcome.reason === "no_prompt") {
        showAttemptError( "这张图还没有可用的 Prompt 版本：先编译并保存。");
      } else if (outcome.reason === "shot_missing") {
        showAttemptError( "这张图已不在套图方案里，先刷新套图规划。");
      } else if (outcome.reason === "no_references") {
        showAttemptError( "这张图没有可用参考图（至少需要一张）。");
      } else if (outcome.reason === "reference_read_failed") {
        showAttemptError( outcome.message);
      } else if (outcome.reason === "environment_unknown") {
        showAttemptError( outcome.message
          || "提交前读不到有效的图像环境身份；不猜身份，先确认服务端可用。");
      }
      return outcome;
    }
    if (outcome.thrown) {
      showAttemptError( outcome.message);
      return outcome;
    }
    const record = outcome.record;
    if (!record) return outcome;
    elements.attemptStatus.textContent = "action " + record.action_id + "：" + attemptStateLabel(record.state)
      + (record.task_id ? "（task " + record.task_id + "）" : "") + "。";
    if (record.state === ATTEMPT_STATES.unknown) {
      showAttemptError( "这次提交的结果没有确认：不要重复提交。"
        + (record.task_id ? "可以按任务编号核对。" : "没有任务编号，只能显式新建 action。"));
    } else if (record.state === ATTEMPT_STATES.failed && record.error) {
      showAttemptError( "这次提交明确失败：" + record.error.message
        + "（重试策略 " + record.error.retry_policy + "）。");
    }
    if (outcome.candidate && outcome.candidate.failed) {
      showAttemptError( outcome.candidate.message);
    } else if (outcome.candidate && outcome.candidate.stored && outcome.candidate.sha256) {
      elements.attemptStatus.textContent += " 候选已保存到本地（sha256 "
        + outcome.candidate.sha256.slice(0, 12) + "…）。";
    }
    return outcome;
  }

  /** 单张核对（按钮入口）：只负责把核心结果翻译成界面反馈，执行顺序在生成 Module。 */
  /** 单张核对（按钮入口）：只负责把核心结果翻译成界面反馈，执行顺序在生成 Module。
   * @param {string|null} shotId
   * @param {import("./generation.js").ReconcileAttemptOptions} [options]
   * @returns {Promise<import("./generation.js").ReconcileAttemptResult|undefined>}
   */
  async function handleReconcileAttempt(shotId, options = {}) {
    if (!shotId) return;
    const action = options.action || beginAction();
    clearAttemptError();
    const result = await generation.reconcileAttempt(shotId, { ...options, action });
    if (!action.alive()) return result;
    if (result.skipped) {
      if (result.reason === "no_task") {
        showAttemptError( "这条记录没有任务编号，无法核对；只能显式新建 action。");
      } else if (result.reason === "environment_blocked") {
        showAttemptError(result.message || "当前环境与冻结身份不一致，未发出核对请求。");
      } else if (result.reason === "no_identity") {
        showAttemptError(result.message || "这条 Attempt 没有冻结执行身份，不能按原身份核对。");
      }
      return result;
    }
    if (result.failed) {
      showAttemptError( result.message);
      return result;
    }
    if (result.advanced) {
      elements.attemptStatus.textContent = "已核对 task " + result.task_id + "："
        + attemptStateLabel(result.state) + "。";
      if (result.candidate && result.candidate.failed) {
        showAttemptError( result.candidate.message);
      } else if (result.candidate && result.candidate.stored && result.candidate.sha256) {
        elements.attemptStatus.textContent += " 候选已保存到本地（sha256 "
          + result.candidate.sha256.slice(0, 12) + "…）。";
      }
    } else {
      elements.attemptStatus.textContent = "已核对 task " + result.task_id + "：没有新结论（"
        + result.note + "）。";
    }
    return result;
  }

  /* --------------------------------------------- 单图返工闭环（V2.5.4） */

  /**
   * 返工区与比较区相邻但独立：比较区只投影、只读；这里才写 Prompt 版本、
   * 单图确认与新的生成尝试。草稿按图留在内存，预览只有用户确认时才落成版本。
   */

  /**
   * @param {string} shotId
   * @returns {string}
   */
  function reworkConfirmId(shotId) {
    return generation.reworkDocumentId(shotId);
  }

  /** 返工草稿按图保存；第一次打开时用报告的先看项预选问题与方向，之后保留用户改动。 */
  /** 返工草稿按图保存；第一次打开时用报告的先看项预选问题与方向，之后保留用户改动。
   * @param {string} shotId
   * @param {CompareInventoryRow|null} row
   * @returns {ReworkDraft}
   */
  function reworkDraftOf(shotId, row) {
    let draft = reworkDrafts.get(shotId);
    if (!draft) {
      draft = {
        problems: suggestReworkProblems(row ? row.report : null),
        direction: suggestedReworkDirection(row ? row.report : null),
        directive: null,
        preview: null,
      };
      reworkDrafts.set(shotId, draft);
    }
    return draft;
  }

  /**
   * @param {string} shotId
   * @param {string|null} candidateId
   * @returns {CompareInventoryRow|null}
   */
  function reworkShotRow(shotId, candidateId) {
    const inventory = compareInventory();
    const rows = inventory.rowsByShotId[shotId] || [];
    return rows.find((item) => item.candidate_id === candidateId) || rows[0] || null;
  }

  /**
   * @param {ReworkDraft|null} draft
   * @returns {string}
   */
  function reworkSummaryOf(draft) {
    if (draft && draft.preview) {
      return "预览已就绪：确认并生成会把它保存为 Prompt 新版本（旧版本保留），"
        + "只重新生成这张图；改过问题或方向后需要重新预览。";
    }
    return "选好问题或写下方向 → 预览返工 Prompt → 确认并生成这张图。";
  }

  /**
   * @param {string|null} shotId
   * @param {ReworkDraft|null} draft
   * @returns {void}
   */
  function updateReworkControls(shotId, draft) {
    if (!draft) return;
    const hasReason = draft.problems.length > 0
      || String(elements.reworkDirection.value || "").trim().length > 0;
    const busy = reworkInFlight;
    elements.reworkPreview.disabled = busy || !hasReason;
    elements.reworkEdit.disabled = busy || !draft.preview;
    elements.reworkSubmit.disabled = busy || !draft.preview;
    elements.reworkReset.disabled = busy;
    elements.reworkCancel.disabled = busy;
    elements.reworkSummary.textContent = reworkSummaryOf(draft);
  }

  /** 输入变了：旧预览不再代表将要发送的内容，必须重新预览。 */
  /** 输入变了：旧预览不再代表将要发送的内容，必须重新预览。
   * @param {ReworkDraft|null} draft
   * @returns {void}
   */
  function dirtyReworkDraft(draft) {
    if (!draft || !draft.preview) return;
    draft.preview = null;
    draft.directive = null;
    elements.reworkPreviewBox.hidden = true;
    elements.reworkStatus.hidden = true;
  }

  /**
   * @param {ReworkDraft|null} draft
   * @returns {void}
   */
  function renderReworkPreviewBox(draft) {
    if (!draft || !draft.preview) {
      elements.reworkPreviewBox.hidden = true;
      return;
    }
    elements.reworkPreviewBox.hidden = false;
    elements.reworkPreviewMeta.textContent =
      "将保存为 Prompt 新版本（旧版本保留）并只重新生成这张图 · 参考图 "
      + draft.preview.references + " 张 · 全文 " + draft.preview.text.length + " 字";
    elements.reworkPreviewText.textContent = draft.preview.text;
  }

  /**
   * @param {string} shotId
   * @param {ReworkDraft} draft
   * @returns {void}
   */
  function renderReworkProblems(shotId, draft) {
    const box = elements.reworkProblems;
    const host = /** @type {HTMLElement} */ (box.querySelector(".rework-problem-options") || box);
    for (const node of Array.from(host.querySelectorAll("label.rework-problem"))) node.remove();
    for (const problem of REWORK_PROBLEMS) {
      const label = createElement("label", {
        className: "check rework-problem",
        attrs: { title: problem.hint, "data-problem-id": problem.id },
      });
      const input = createElement("input", {
        attrs: { id: "rework-problem-" + problem.id, type: "checkbox", value: problem.id },
      });
      input.checked = draft.problems.indexOf(problem.id) >= 0;
      input.addEventListener("change", () => {
        if (input.checked) {
          if (draft.problems.indexOf(problem.id) === -1) {
            draft.problems = draft.problems.concat([problem.id]);
          }
        } else {
          draft.problems = draft.problems.filter((id) => id !== problem.id);
        }
        dirtyReworkDraft(draft);
        updateReworkControls(shotId, draft);
      });
      label.append(input, document.createTextNode(" " + problem.label));
      host.append(label);
    }
  }

  /** 入口：把当前正看着的候选（candidate_id + sha256）交给返工表单；只改内存状态。 */
  /** 入口：把当前正看着的候选（candidate_id + sha256）交给返工表单；只改内存状态。
   * @returns {void}
   */
  function openReworkPanel() {
    const shotId = elements.reworkOpen.dataset.shotId || compareShotId;
    const candidateId = elements.reworkOpen.dataset.candidateId || compareCandidateId;
    if (!shotId || !candidateId || reworkInFlight) return;
    const row = reworkShotRow(shotId, candidateId);
    if (!row || !row.record) {
      elements.compareStatus.textContent = "这条候选已经不在了，先重新选择候选。";
      return;
    }
    reworkShotId = shotId;
    reworkSource = {
      shot_id: shotId, candidate_id: row.candidate_id, asset_sha256: row.asset_sha256,
      version: row.version === null || row.version === undefined ? null : row.version,
    };
    const draft = reworkDraftOf(shotId, row);
    const panel = elements.reworkPanel;
    panel.hidden = false;
    panel.dataset.reworkContract = REWORK_CONTRACT_VERSION;
    panel.dataset.shotId = shotId;
    panel.dataset.candidateId = row.candidate_id;
    const basis = ["返工依据：候选 v" + (reworkSource.version === null ? "?" : reworkSource.version)];
    if (row.top_finding) basis.push("先看：" + row.top_finding.title);
    if (reworkConfirmationIsCurrent(shotId)) basis.push("这张图的返工确认仍然有效");
    elements.reworkBasis.textContent = basis.join(" · ");
    if (elements.reworkTech && elements.reworkTechBody) {
      elements.reworkTech.hidden = false;
      elements.reworkTechBody.textContent = "sha256 "
        + String(reworkSource.asset_sha256).slice(0, 12) + "… · candidate " + row.candidate_id;
    }
    renderReworkProblems(shotId, draft);
    if (elements.reworkDirection.value !== draft.direction) {
      elements.reworkDirection.value = draft.direction;
    }
    renderReworkPreviewBox(draft);
    elements.reworkStatus.hidden = true;
    clearError(elements.reworkError);
    updateReworkControls(shotId, draft);
    const first = /** @type {HTMLInputElement|null} */ (elements.reworkProblems.querySelector('input[type="checkbox"]'));
    if (first) first.focus();
    panel.scrollIntoView({ block: "nearest" });
  }

  /** 收起返工区：清掉未确认的预览；草稿（问题与方向）按图保留。 */
  /** 收起返工区：清掉未确认的预览；草稿（问题与方向）按图保留。
   * @param {{focusCandidate?: boolean}} [options]
   * @returns {void}
   */
  function closeReworkPanel({ focusCandidate = false } = {}) {
    const shotId = reworkShotId;
    const candidateId = reworkSource ? reworkSource.candidate_id : null;
    reworkShotId = null;
    reworkSource = null;
    elements.reworkPanel.hidden = true;
    elements.reworkPreviewBox.hidden = true;
    elements.reworkStatus.hidden = true;
    clearError(elements.reworkError);
    const draft = shotId ? reworkDrafts.get(shotId) : null;
    if (draft) {
      draft.preview = null;
      draft.directive = null;
    }
    if (focusCandidate && shotId) focusCompareCandidate(shotId, candidateId);
  }

  /** 收起后把焦点还给原候选：比较区还在就回到候选页签，否则回到该图的比较入口。 */
  /**
   * @param {string} shotId
   * @param {string|null} candidateId
   * @returns {void}
   */
  function focusCompareCandidate(shotId, candidateId) {
    const tab = candidateId ? /** @type {HTMLButtonElement|null} */ (elements.compareCandidates.querySelector(
      '[role="tab"][data-candidate-id="' + candidateId + '"]')) : null;
    if (tab) {
      tab.focus();
      return;
    }
    focusCompareEntry(shotId);
  }

  /**
   * 焦点只能落到用户当前看得见的比较入口。
   * V2.UI.2 起阶段分屏：尝试行在「生成」、审核卡在「审核返工」，跨阶段的入口是隐藏的，
   * 直接 focus 会被浏览器丢成 body。顺序：审核卡入口 → 尝试行入口 → 阶段条当前阶段 → 面板内关闭键。
   */
  /** 收起后把焦点还给原候选：比较区还在就回到候选页签，否则回到该图的比较入口。
   * @param {string|null} shotId
   * @returns {void}
   */
  function focusCompareEntry(shotId) {
    const isVisible = (/** @type {HTMLElement|null|undefined} */ node) => Boolean(node && node.offsetParent !== null);
    const reviewEntry = elements.reviewList
      ? /** @type {HTMLButtonElement|null} */ (elements.reviewList.querySelector('.review-card[data-shot-id="' + shotId + '"] button'))
      : null;
    const attemptEntry = /** @type {HTMLButtonElement|null} */ (elements.attemptList.querySelector(
      'button[data-compare-action="' + shotId + '"]'));
    const stageButton = /** @type {HTMLButtonElement|null} */ (elements.stageNav.querySelector("[data-stage-nav].is-current"));
    const target = [reviewEntry, attemptEntry, stageButton, elements.compareClose]
      .find(isVisible);
    if (target) target.focus();
  }

  /** 按建议重填：问题与方向回到报告先看项的默认值，预览作废。 */
  /** 按建议重填：问题与方向回到报告先看项的默认值，预览作废。
   * @returns {void}
   */
  function resetReworkDraft() {
    const shotId = reworkShotId;
    if (!shotId || reworkInFlight) return;
    const row = reworkShotRow(shotId, reworkSource ? reworkSource.candidate_id : null);
    reworkDrafts.delete(shotId);
    const draft = reworkDraftOf(shotId, row);
    renderReworkProblems(shotId, draft);
    if (elements.reworkDirection.value !== draft.direction) {
      elements.reworkDirection.value = draft.direction;
    }
    elements.reworkPreviewBox.hidden = true;
    elements.reworkStatus.hidden = true;
    clearError(elements.reworkError);
    updateReworkControls(shotId, draft);
  }

  /**
   * @returns {void}
   */
  function handleReworkCancel() {
    if (reworkInFlight) return;
    closeReworkPanel({ focusCandidate: true });
  }

  /** 预览：按当前问题与方向编译一次；只显示，不写记录。 */
  /** 预览：按当前问题与方向编译一次；只显示，不写记录。
   * @returns {Promise<void>}
   */
  async function handleReworkPreview() {
    if (!projectId || !reworkShotId || reworkInFlight) return;
    const shotId = reworkShotId;
    clearError(elements.reworkError);
    const row = reworkShotRow(shotId, reworkSource ? reworkSource.candidate_id : null);
    if (!row || !row.record) {
      showError(elements.reworkError, "返工依据已经不在，先回到比较区重新选择候选。");
      return;
    }
    const draft = reworkDraftOf(shotId, row);
    draft.direction = elements.reworkDirection.value;
    reworkInFlight = true;
    updateReworkControls(shotId, draft);
    try {
      const directive = buildReworkDirective({
        directiveId: newActionId(),
        shotId: shotId,
        candidate: row.record,
        report: row.report,
        problems: draft.problems,
        direction: draft.direction,
        at: new Date().toISOString(),
      });
      const result = await prompts.compile(shotId, { rework: directive });
      draft.directive = directive;
      draft.preview = {
        directive_id: directive.directive_id,
        payload: result.compiled,
        references: result.references.length,
        text: result.compiled.text,
      };
      renderReworkPreviewBox(draft);
      elements.reworkStatus.hidden = false;
      elements.reworkStatus.textContent = "预览已就绪：确认并生成时会先把它保存为新版本，"
        + "再只提交这一张图；预览本身没有写入任何记录。";
    } catch (error) {
      showError(elements.reworkError, errorMessageSuffixed(error, "预览没有生成，旧版本与输入保留。", "（预览未生成，旧版本与输入保留）"));
    } finally {
      reworkInFlight = false;
      const current = reworkDrafts.get(shotId);
      if (current) updateReworkControls(shotId, current);
    }
  }

  /** 查看/编辑完整 Prompt：把这次预览落成版本，再把焦点交给这张图的人工编辑区。 */
  /** 查看/编辑完整 Prompt：把这次预览落成版本，再把焦点交给这张图的人工编辑区。
   * @returns {Promise<void>}
   */
  async function handleReworkEdit() {
    if (!projectId || !reworkShotId || reworkInFlight) return;
    const shotId = reworkShotId;
    const draft = reworkDrafts.get(shotId);
    clearError(elements.reworkError);
    if (!draft || !draft.preview) {
      showError(elements.reworkError, "先预览返工 Prompt，再查看或编辑全文。");
      return;
    }
    reworkInFlight = true;
    updateReworkControls(shotId, draft);
    try {
      const latest = promptRecordOf(shotId);
      let version = latest ? latest.version : 0;
      const fromPreview = Boolean(latest && latest.record.compiled.rework
        && latest.record.compiled.rework.directive_id === draft.preview.directive_id);
      if (!fromPreview) {
        if (!draft.directive) throw new Error("先预览返工 Prompt，再查看或编辑全文。");
        const saved = await prompts.compileAndSave(shotId, { rework: draft.directive });
        version = saved.saved.version;
      }
      renderPrompts();
      renderConfirm();
      const area = /** @type {HTMLTextAreaElement|null} */ (elements.promptList.querySelector(
        '[data-shot-id="' + shotId + '"] textarea.prompt-edit-text'));
      elements.reworkStatus.hidden = false;
      elements.reworkStatus.textContent = "已保存为 Prompt v" + version
        + "；可以在下方「Prompt 预览与版本」里编辑全文并另存新版本。";
      if (area) {
        area.scrollIntoView({ block: "center" });
        area.focus();
      }
    } catch (error) {
      showError(elements.reworkError, errorMessageOf(error, "没有打开编辑区。"));
    } finally {
      reworkInFlight = false;
      const current = reworkDrafts.get(shotId);
      if (current) updateReworkControls(shotId, current);
    }
  }

  /**
   * @param {string} shotId
   * @returns {GenerationIntent|null}
   */
  function buildReworkIntent(shotId) {
    return /** @type {GenerationIntent|null} */ (generation.reworkIntent(shotId));
  }

  /**
   * 确认并生成这张图：先确保这次返工已经落成 Prompt 版本（发送的永远是这张图最新的版本），
   * 再写「只覆盖这张图」的确认记录、新建 Attempt 并核对一次结论；失败不影响旧候选。
   */
  /**
   * @returns {Promise<void>}
   */
  async function handleReworkSubmit() {
    if (!projectId || !reworkShotId || reworkInFlight) return;
    const action = beginAction();
    const shotId = reworkShotId;
    const sourceCandidateId = reworkSource ? reworkSource.candidate_id : null;
    const draft = reworkDrafts.get(shotId);
    clearError(elements.reworkError);
    if (!draft || !draft.preview || !draft.directive) {
      showError(elements.reworkError, "先预览返工 Prompt，再确认生成。");
      return;
    }
    reworkInFlight = true;
    updateReworkControls(shotId, draft);
    try {
      const latest = promptRecordOf(shotId);
      let version = latest ? latest.version : 0;
      const fromPreview = Boolean(latest && latest.record.compiled.rework
        && latest.record.compiled.rework.directive_id === draft.preview.directive_id);
      if (!fromPreview) {
        if (!draft.directive) throw new Error("先预览返工 Prompt，再确认生成。");
        const saved = await prompts.compileAndSave(shotId, { rework: draft.directive, action });
        version = saved.saved.version;
      }
      if (!action.alive()) return;
      const intent = buildReworkIntent(shotId);
      if (!intent) throw new Error("这张图当前还有阻断，返工没有外发。");
      await generation.confirmAndRun({
        intent, readIntent: () => buildReworkIntent(shotId), expectedVersion: version,
        documentId: reworkConfirmId(shotId), action,
      });
      if (!action.alive()) return;
      const latestAttempt = generation.latestAttemptOf(shotId);
      const state = latestAttempt ? latestAttempt.record.state : null;
      draft.directive = null;
      draft.preview = null;
      reworkShotId = null;
      reworkSource = null;
      elements.reworkPanel.hidden = true;
      elements.reworkPreviewBox.hidden = true;
      elements.reworkStatus.hidden = true;
      renderAttempts();
      await deriveAndApplyState();
      focusCompareCandidate(shotId, sourceCandidateId);
      elements.compareStatus.textContent = "返工已提交（Prompt v" + version + " · "
        + attemptStateLabel(state) + "）；旧候选保留，只有这张图新增了版本。";
    } catch (error) {
      if (action.alive()) {
        showError(elements.reworkError,
          errorMessageOf(error, "返工没有提交；旧候选与旧 Prompt 不受影响。"));
      }
    } finally {
      if (action.alive()) {
        reworkInFlight = false;
        const current = reworkDrafts.get(shotId);
        if (current) updateReworkControls(shotId, current);
      }
    }
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
   * @returns {void}
   */
  function renderBatch() {
    if (!elements.batchBar) return;
    const ready = Boolean(inputs.suitePlan());
    elements.batchBar.hidden = !ready;
    if (!ready) return;
    const state = generation.deriveBatch();
    const batchState = generation.batchStateReader();
    const running = Boolean(batchState && batchState.active);
    const confirmed = confirmationIsCurrent();
    const progress = [batchProgressText(state)];
    if (running && batchState) {
      if (batchState.phase === "poll") {
        progress.push("批次进行中：正在按任务编号核对上游进度");
      } else {
        progress.push(batchState.currentShotId
          ? "批次进行中：正在提交「" + shotLabelOf(batchState.currentShotId) + "」"
          : "批次进行中");
      }
    }
    if (batchState && batchState.halted) {
      progress.push("已停止新增提交（" + batchState.haltReason + "）；已提交的记录全部保留");
    }
    if (batchState && batchState.stopped) {
      progress.push("已停止新增提交；已提交的记录全部保留");
    }
    elements.batchProgress.textContent = progress.join("；") + "。";

    const hints = [];
    if (!confirmed) hints.push("生成前确认缺失或已过期：先回到「生成前确认」重新确认。");
    if (state.counts.blocked_no_prompt > 0) {
      hints.push("有 " + state.counts.blocked_no_prompt + " 张还没编译 Prompt。");
    }
    if (state.review_queue.length > 0) {
      hints.push("有 " + state.review_queue.length
        + " 张没有任务编号、无法核对：系统不会自动重提，需要显式新建 action。");
    }
    if (state.fetch_queue.length > 0) {
      hints.push("有 " + state.fetch_queue.length
        + " 张已生成但候选还没保存到本地：可以点「保存候选图片」逐张保存，或点「保存候选」一次保存剩余。");
    }
    if (batchState && batchState.fetchBlocked) {
      hints.push("候选保存受阻：" + batchState.fetchBlocked);
    }
    elements.batchHint.textContent = hints.join(" ");
    elements.batchHint.hidden = hints.length === 0;

    elements.queueList.replaceChildren();
    // 队列投影（pending/current/targetMatched）归 generation.queues() 所有；这里只渲染，不重算判据。
    for (const { queue, pending, current, targetMatched: matched } of generation.queues()) {
      if (!pending.length) continue;
      const target = queue.payload.fingerprint.snapshot.execution_target;
      if (!target) continue;
      const row = createElement("div", { className: "generation-queue" });
      row.append(createElement("p", {
        className: "meta", text: "原队列 v" + queue.version + " · " + target.model_id + " · "
          + target.protocol + " · 凭据 " + target.credential_source + " · 尚未提交 " + pending.length
          + " 张（当前依据有效 " + current.length + " 张）：" + pending.map((shotId) => shotLabelOf(shotId)).join("、"),
      }));
      row.append(createElement("p", { className: "meta", text: String(queue.payload.external_summary.statement) }));
      const resume = createElement("button", { text: "按原摘要继续未提交队列", attrs: { type: "button" } });
      resume.disabled = running || submissionInFlight || !matched || !current.length;
      resume.addEventListener("click", () => { void generation.runBatch({ confirmation: queue }); });
      const credentials = createElement("button", { text: "给原目标补凭据", attrs: { type: "button" } });
      credentials.addEventListener("click", () => modelSettings.open("image", target.provider_id));
      row.append(resume, credentials);
      elements.queueList.append(row);
    }
    elements.batchStop.hidden = !running;
    elements.batchReconcile.hidden = state.reconcile_queue.length === 0;
    elements.batchReconcile.disabled = running || state.reconcile_queue.length === 0;
    elements.batchReconcile.textContent = "核对进行中（" + state.reconcile_queue.length + " 张）";
    elements.batchRetry.hidden = state.retry_queue.length === 0;
    elements.batchRetry.disabled = running || state.retry_queue.length === 0;
    elements.batchRetry.textContent = "查看失败图的重试摘要（" + state.retry_queue.length + " 张）";
  }

  /* ----------------------------------------------- 人工选择与失效（V2.6.1） */

  // 人工选择与采用：记录所有权在 selectionAdoption Module；这里只做视图装配
  // （状态徽标/入口按钮）与动作转发，不直接读写记录或拼持久化顺序。
  /**
   * @param {string|null} shotId
   * @returns {{record: SelectionRecord, version: number}|null}
   */
  function selectionEntryOf(shotId) {
    return selectionAdoption.entryOf(shotId);
  }

  /**
   * @param {string} shotId
   * @returns {SelectionState}
   */
  function selectionStateOf(shotId) {
    return selectionAdoption.stateOf(shotId);
  }

  /** 某张图当前采用的候选（含过期标记）：只读投影，供比较列表做徽标。 */
  /** 某张图当前采用的候选（含过期标记）：只读投影，供比较列表做徽标。
   * @param {string|null} shotId
   * @returns {{candidate_id: string|null, state: SelectionState}|null}
   */
  function adoptedMarkOf(shotId) {
    return selectionAdoption.adoptedMark(shotId);
  }

  /** SelectionSet 投影：V2.5.5 / V2.6.2 的唯一输入集合；这里只报告数量，不拦导出。 */
  /** SelectionSet 投影：V2.5.5 / V2.6.2 的唯一输入集合；这里只报告数量，不拦导出。
   * @returns {import("./domain/type-contracts.js").SelectionSet}
   */
  function selectionSetNow() {
    return selectionAdoption.projection(projectSources()).set;
  }

  /**
   * @returns {void}
   */
  function renderSelectionProgress() {
    if (!inputs.suitePlan()) {
      elements.adoptProgress.textContent = "";
      return;
    }
    const set = selectionSetNow();
    elements.adoptProgress.textContent = set.summary.required_total > 0
      ? selectionSetText(set) + "采用只引用候选（candidate_id + sha256），不复制图片。"
      : "";
  }

  /** 比较区入口的状态：只投影候选身份，不写任何记录（写记录在相邻的独立采用区）。 */
  /** 比较区入口的状态：只投影候选身份，不写任何记录（写记录在相邻的独立采用区）。
   * @param {PlanShot|null} shot
   * @param {CompareInventoryRow|null} row
   * @returns {void}
   */
  function updateAdoptEntry(shot, row) {
    const available = Boolean(shot && row && row.record && row.record.asset_sha256);
    const selected = shot ? selectionAdoption.entryOf(shot.shot_id)?.record || null : null;
    const already = Boolean(selected && selected.action === "select" && row
      && selected.candidate_id === row.candidate_id
      && shot && selectionAdoption.stateOf(shot.shot_id) === "current");
    elements.adoptOpen.disabled = !available || already;
    elements.adoptClear.disabled = !selected || selected.action !== "select";
  }

  /** 采用目标：把「正看着的候选」解析成候选记录 + 文档版本 + 当前审核报告。 */
  /** 采用目标：把「正看着的候选」解析成候选记录 + 文档版本 + 当前审核报告。
   * @param {string|null} shotId
   * @param {string|null} candidateId
   * @returns {{candidate: CandidateRecord, version: number, report: ReviewReport|null}|null}
   */
  function adoptSourceOf(shotId, candidateId) {
    return selectionAdoption.sourceOf(shotId, candidateId);
  }

  /**
   * @param {string} shotId
   * @returns {string}
   */
  function selectionTextOf(shotId) {
    return selectionAdoption.summary(shotId);
  }

  /** One explicit human action. Identity freezes before any byte read; selection is append-only/OCC.
   * @param {"select"|"clear"} kind
   * @param {string|null} [shotId]
   * @param {string|null} [candidateId]
   * @returns {Promise<void>}
   */
  async function handleCandidateSelection(kind, shotId = compareShotId, candidateId = compareCandidateId) {
    if (!projectId || !shotId || selectionAdoption.isSelecting()) return;
    const action = beginAction();
    clearError(elements.adoptError);
    elements.adoptStatus.hidden = false;
    elements.adoptStatus.textContent = "正在保存 " + shotLabelOf(shotId) + " 的人工选择…";
    try {
      await selectionAdoption.select(kind, shotId, candidateId);
      if (!action.alive()) return;
      elements.adoptStatus.textContent = shotLabelOf(shotId)
        + (kind === "select" ? " 已采用候选" : " 已取消采用")
        + "；旧候选和旧采用保留在历史中。确定性硬阻断仍会阻止交付。";
    } catch (error) {
      if (!action.alive()) return;
      elements.adoptStatus.textContent = "人工选择没有保存；原采用保留。";
      showError(elements.adoptError, errorMessageOf(error, "存储失败，请重试。"));
    } finally {
      if (action.alive()) renderAttempts();
    }
  }

  /**
   * @param {StoredProjectRecord|null} projectRecord
   * @returns {void}
   */
  function renderHeaderText(projectRecord) {
    const state = projectRecord ? projectRecord.state : null;
    if (state === "READY_TO_GENERATE") {
      elements.scope.textContent = "生成前确认已通过：可以整套生成或逐张提交，并按任务编号核对进度；可以审核、单图返工与采用候选；整套一致性报告与导出交付仍未接入。";
    } else if (state === "PLAN_REVIEW") {
      elements.scope.textContent = "商品理解已就绪，可以编辑套图规划、规格、Prompt 与生成前确认；通过确认后才能提交生成。";
    } else {
      elements.scope.textContent = SCOPE_TEXT;
    }
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
    const state = entryCount === 0
      ? (intakeReadiness(draftPayload).ready ? "INTAKE_READY" : "EMPTY")
      : (understandingReady
        ? (confirmationIsCurrent() ? "READY_TO_GENERATE" : "PLAN_REVIEW")
        : "UNDERSTANDING_REVIEW");
    if (project && project.state !== state) {
      try {
        // 状态写按冻结项目落库（保存派生结论）；已过期动作不回写界面状态。
        const updated = await repository.projects.setState(action.projectId, state);
        if (action.alive()) {
          project = updated;
          if (onProjectChanged) onProjectChanged(project);
        }
      } catch (error) {
        if (action.alive()) {
          showError(elements.error, errorMessageOf(error, "状态写回失败。"));
        }
      }
    }
    if (action.alive()) renderHeaderText(project);
  }

  /* ---------------------------------------------------------- 六阶段投影与交付门禁（V2.UI.2） */

  /**
   * @returns {import("./domain/type-contracts.js").SuitePlanSummary["shots"]}
   */
  function shotSummariesNow() {
    return inputs.suitePlan() ? suitePlanSummary(inputs.suitePlan(), inputs.suiteContext()).shots : [];
  }

  /**
   * 每个阶段的完成 / 可用 / 摘要只在这里派生一次；外壳只负责画出来。
   * available=false 表示阶段条上的入口不可用（前置未完成），不是错误。
   */
  /**
   * @returns {Record<string, {status?: string, summary?: string, hint?: string, available?: boolean}>}
   */
  function computeStageStates() {
    const shots = shotSummariesNow();
    const entries = inputs.slotEntries();
    const confirmed = entries.filter((item) => item.slot.status === "confirmed").length;
    const unknownSlots = entries.filter((item) => item.slot.status === "unknown").length;
    const hasSlots = inputs.slotEntries().length > 0;
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
    const requiredSelected = requiredShots.filter((shot) => selectionStateOf(shot.shot_id) === "current");
    const selectedShots = shots.filter((shot) => selectionStateOf(shot.shot_id) === "current");
    const projectName = project ? project.name : "";
    const referenceCount = inputs.references().length;
    const intakeSummary = [projectName, referenceCount ? "参考图 " + referenceCount + " 张" : ""]
      .filter(Boolean).join(" · ");

    return {
      intake: {
        available: true,
        status: hasSlots ? "complete" : "current",
        hint: hasSlots ? "" : "上传参考图，自己填写商品事实；AI 理解是可选辅助。",
        summary: hasSlots ? intakeSummary : "",
      },
      understand: {
        available: hasSlots,
        status: understandingReady ? "complete" : "current",
        hint: hasSlots ? "" : "可直接填写并确认核心事实，不需要先调用模型。",
        summary: understandingReady
          ? "已确认 " + confirmed + " 项" + (unknownSlots ? " · 未知 " + unknownSlots + " 项" : "")
          : "",
      },
      plan: {
        available: understandingReady,
        status: shots.length ? "complete" : "current",
        hint: understandingReady ? "" : "先完成商品理解。",
        summary: shots.length ? shots.length + " 张图片任务" : "",
      },
      generate: {
        available: shots.length > 0,
        status: (shots.length > 0 && settled.length === shots.length) ? "complete" : "current",
        hint: shots.length ? "" : "先生成套图方案。",
        summary: shots.length
          ? withCandidate.length + "/" + shots.length + " 张有候选"
            + (unknownAttempts.length ? " · " + unknownAttempts.length + " 张待核对" : "")
          : "",
      },
      review: {
        available: withCandidate.length > 0,
        status: (shots.length > 0 && selectedShots.length === shots.length) ? "complete" : "current",
        hint: withCandidate.length ? "" : "先生成至少一张候选。",
        summary: shots.length
          ? "已采用 " + selectedShots.length + "/" + shots.length
            + " · 必需图 " + requiredSelected.length + "/" + requiredShots.length
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

  /** 默认停靠：最靠后的“可用且未完成”的阶段；全部完成则停在交付。 */
  /** 默认停靠：最靠后的“可用且未完成”的阶段；全部完成则停在交付。
   * @param {Record<string, {status?: string, summary?: string, hint?: string, available?: boolean}>|null} [states]
   * @returns {string}
   */
  function defaultStageId(states = null) {
    const map = states || computeStageStates();
    for (const id of ["intake", "understand", "plan", "generate", "review", "deliver"]) {
      if (map[id] && map[id].available !== false && map[id].status !== "complete") return id;
    }
    return "deliver";
  }

  /** 阶段底部的推进按钮：禁用时说明缺什么；不改变任何数据。 */
  /** 阶段底部的推进按钮：禁用时说明缺什么；不改变任何数据。
   * @param {Record<string, {status?: string, summary?: string, hint?: string, available?: boolean}>} states
   * @returns {void}
   */
  function renderStageFoot(states) {
    const shots = shotSummariesNow();
    elements.stageNextUnderstand.disabled = false;
    elements.stageNextUnderstandNote.textContent = understandingReady
      ? "" : "可以先规划图片任务；缺失的核心事实只阻断生成。";
    elements.stageNextPlan.disabled = false;
    elements.stageNextPlanNote.textContent = shots.length
      ? "" : "先生成或添加至少一张图片。";
    const candidates = states && states.review ? states.review.available : false;
    elements.stageNextReview.disabled = false;
    elements.stageNextReviewNote.textContent = candidates ? "" : "先产生至少一张候选。";
    const requiredShots = shots.filter((shot) => shot.required === true);
    const pending = requiredShots.filter((shot) => selectionStateOf(shot.shot_id) !== "current");
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
    renderReviewList();
    deliveryView?.render();
    deliveryView?.requestGateRefresh();
    return refreshStageShell();
  }

  /**
   * 审核阶段的逐图入口：图片 + 候选数 + 采用状态 + 逐图检查摘要 + 比较/返工/采用。
   *
   * 卡片右栏此前只有图名与徽标，真实链路走查（2026-10-01 自审）里一大片空白——
   * 人只能点开比较面板才知道这张图「查出了什么」。这里复读同一份当前报告
   * （compareInventory 已按 reviewIsCurrent 过滤），把状态、机器结论与「先看哪一条」
   * 摆到卡片上；不新增第二套规则，也不改变任何选择语义。
   * @returns {void}
   */
  function renderReviewList() {
    if (!elements.reviewList) return;
    elements.reviewList.innerHTML = "";
    const shots = shotSummariesNow();
    const reviewable = shots.filter((shot) => generation.candidateChainOf(shot.shot_id).length > 0);
    elements.reviewEmpty.hidden = reviewable.length > 0;
    const inventory = reviewable.length ? compareInventory() : { rowsByShotId: /** @type {Record<string, CompareInventoryRow[]>} */ ({}) };
    for (const shot of reviewable) {
      const chain = generation.candidateChainOf(shot.shot_id);
      const stored = generation.latestStoredCandidateOf(shot.shot_id);
      const state = selectionStateOf(shot.shot_id);
      const rows = inventory.rowsByShotId[shot.shot_id] || [];
      const shownRow = stored
        ? (rows.find((/** @type {CompareInventoryRow} */ row) => row.candidate_id === stored.record.candidate_id) || null)
        : null;
      const card = createElement("div", {
        className: "review-card",
        attrs: { "data-shot-id": shot.shot_id, "data-selection-state": state },
      });
      const head = createElement("div", { className: "review-card-head" });
      head.append(createElement("span", { className: "name", text: shot.label }));
      head.append(createElement("span", {
        className: "badge " + (state === "current" ? "is-adopted" : (state === "stale" ? "is-review-warn" : "is-empty")),
        text: state === "current" ? "已采用" : (state === "stale" ? "已采用（已过期）" : "未采用"),
      }));
      head.append(createElement("span", { className: "meta", text: "候选 " + chain.length + " 个" }));
      card.append(head);
      if (stored) {
        const candidate = stored.record;
        const preview = createElement("div", { className: "review-preview" });
        const img = createElement("img", { attrs: { alt: shot.label + " 的最新候选", loading: "lazy" } });
        preview.append(img);
        card.append(preview);
        ensurePreviewUrl(shot.shot_id, stored.record.action_id, candidate.asset_sha256)
          .then((url) => { if (url && img.isConnected) img.src = url; })
          .catch(() => {});
      } else {
        card.append(createElement("p", {
          className: "meta", text: "最新一次生成还没有保存到本地的候选；到「生成」里核对或重试。",
        }));
      }
      const check = createElement("div", {
        className: "review-card-check",
        attrs: {
          "data-shot-id": shot.shot_id,
          "data-review-state": shownRow ? shownRow.review_state : "unchecked",
          "data-candidate-id": shownRow ? shownRow.candidate_id : "",
        },
      });
      if (shownRow) {
        check.append(createElement("span", {
          className: "badge " + (/** @type {Record<string, string>} */ (COMPARE_STATE_BADGE)[shownRow.review_state] || "is-review-unchecked"),
          text: compareStateLabel(shownRow),
        }));
        if (shownRow.report) {
          check.append(createElement("span", {
            className: "meta review-check-summary", text: reviewSummaryText(shownRow.report),
          }));
        }
        check.append(createElement("p", {
          className: "meta review-check-headline", text: compareRowHeadline(shownRow),
        }));
      } else {
        check.append(createElement("span", {
          className: "badge is-review-unchecked",
          text: COMPARE_STATE_TEXT.unchecked,
        }));
        check.append(createElement("p", {
          className: "meta", text: "这张图还没有当前审核报告；打开「比较候选」可查看或补建。",
        }));
      }
      card.append(check);
      const actions = createElement("div", { className: "review-card-actions" });
      const compareButton = createElement("button", {
        text: "比较候选（" + chain.length + "）", attrs: { type: "button" },
      });
      compareButton.addEventListener("click", () => { openCompare(shot.shot_id, { focus: true }); });
      actions.append(compareButton);
      const reworkButton = createElement("button", { text: "按问题返工", attrs: { type: "button" } });
      reworkButton.disabled = !stored;
      reworkButton.addEventListener("click", () => {
        openCompare(shot.shot_id, {});
        openReworkPanel();
      });
      actions.append(reworkButton);
      const alreadyAdopted = state === "current";
      const adoptButton = createElement("button", {
        text: alreadyAdopted ? "已采用" : "采用候选", attrs: { type: "button" },
      });
      if (!alreadyAdopted) adoptButton.className = "primary";
      if (alreadyAdopted) adoptButton.title = "已采用这条候选；换用其他候选请点「比较候选」。";
      adoptButton.disabled = !stored || alreadyAdopted;
      adoptButton.addEventListener("click", () => {
        if (stored) void handleCandidateSelection("select", shot.shot_id, stored.record.candidate_id);
      });
      actions.append(adoptButton);
      card.append(actions);
      elements.reviewList.append(card);
    }
  }

  /* ------------------------------------------------------- 整套一致性（V2.5.5） */

  /**
   * @returns {{report: SuiteReviewReport, version: number}|null}
   */
  function suiteReportEntry() {
    return reviewDelivery.projection().suite;
  }


  /**
   * @returns {Record<string, SelectionRecord>}
   */
  function suiteSelectionMap() {
    const projection = selectionAdoption.projection(projectSources());
    const map = /** @type {Record<string, SelectionRecord>} */ ({});
    for (const [shotId, record] of Object.entries(projection.records)) {
      if (record && record.action === "select") map[shotId] = record;
    }
    return map;
  }

  /**
   * @returns {Record<string, CandidateRecord[]>}
   */
  function suiteCandidatesByShot() {
    const map = /** @type {Record<string, CandidateRecord[]>} */ ({});
    for (const shot of shotSummariesNow()) {
      map[shot.shot_id] = generation.candidateChainOf(shot.shot_id).map((entry) => entry.record);
    }
    return map;
  }

  /**
   * @returns {Record<string, AttemptRecord[]>}
   */
  function suiteAttemptsByShot() {
    const map = /** @type {Record<string, AttemptRecord[]>} */ ({});
    for (const [shotId, chain] of generation.attemptChainsNow()) {
      map[shotId] = chain.map((item) => item.record);
    }
    return map;
  }

  /**
   * @returns {void}
   */
  function renderAll() {
    clearError(elements.error);
    if (understandingError) {
      showError(elements.error,
        "商品理解投影失败：" + errorMessageOf(understandingError, "未知错误"));
    }
    renderReferences().catch(handleInternalError);
    inputView?.render();
    renderGenerationSections();
    renderHeaderText(project);
    refreshDerived();
  }

  /** 生成/确认/尝试三个分区的同轮刷新：全量渲染与输入侧命令收尾共用一处，避免三份写法。 */
  function renderGenerationSections() {
    renderPrompts();
    renderConfirm();
    renderAttempts();
  }

  /**
   * @returns {void}
   */
  function bind() {
    if (bound) return;
    bound = true;
    elements.refAdd.addEventListener("click", () => elements.refFile.click());
    elements.refFile.addEventListener("change", (/** @type {Event} */ event) => {
      handleFiles(/** @type {HTMLInputElement} */ (event.target).files).finally(() => { elements.refFile.value = ""; });
    });
    for (const node of [elements.intakeName, elements.intakeDescription,
                        elements.intakePoints, elements.intakeFocus]) {
      node.addEventListener("input", () => { inputView?.scheduleDraftSave(); });
    }
    elements.intakeSave.addEventListener("click", () => { void inputView?.handleSaveIntake(); });
    elements.analyzeRun.addEventListener("click", () => { void inputView?.runAnalyze(); });
    elements.analyzeNewAfterUnknown.addEventListener("click", () => { void inputView?.runAnalyze({ allowNewAfterUnknown: true }); });
    elements.manualFacts.addEventListener("click", () => { void inputView?.handleManualFacts(); });
    elements.slotsToggle.addEventListener("click", () => { inputView?.toggleAllSlots(); });
    elements.slotAddSave.addEventListener("click", () => { void inputView?.addSlot(); });
    elements.suiteSeed.addEventListener("click", () => { void inputView?.seedSuite(); });
    elements.suiteAddTemplate.addEventListener("click", () => { void inputView?.addTemplateShot(); });
    elements.suiteTemplate.addEventListener("change", () => { inputView?.refreshTemplateHint(); });
    elements.suiteCustomToggle.addEventListener("click", () => { inputView?.toggleCustomPanel(); });
    elements.suiteCustomSave.addEventListener("click", () => { void inputView?.addCustomShot(); });
    elements.styleSave.addEventListener("click", () => { void inputView?.saveStyle(); });
    elements.styleRestore.addEventListener("click", () => { void inputView?.restoreStyle(); });
    elements.confirmAction.addEventListener("click", () => { handleConfirmGeneration(); });
    elements.batchStop.addEventListener("click", () => { generation.stopBatch(); });
    elements.batchReconcile.addEventListener("click", () => { generation.reconcileOnce(); });
    elements.batchRetry.addEventListener("click", () => {
      generation.enterFailedRetry(generation.deriveBatch().retry_queue);
      stageShell.select("generate"); renderConfirm();
    });
    elements.compareJump.addEventListener("click", () => {
      const target = elements.compareJump.dataset.targetShot;
      if (!target) {
        elements.compareStatus.textContent = "这套图没有待处理的候选。";
        return;
      }
      openCompare(target, { focus: true });
      const row = /** @type {HTMLElement|null} */ (elements.attemptList.querySelector('.attempt-row[data-shot-id="' + target + '"]'));
      if (row) row.scrollIntoView({ block: "nearest" });
    });
    elements.compareClose.addEventListener("click", () => {
      const previous = compareShotId;
      compareShotId = null;
      compareCandidateId = null;
      renderCompare();
      const entry = previous ? /** @type {HTMLButtonElement|null} */ (elements.attemptList.querySelector(
        'button[data-compare-action="' + previous + '"]')) : null;
    });
    elements.compareCandidates.addEventListener("keydown", /** @type {(event: KeyboardEvent) => void} */ (handleCompareKeydown));
    elements.compareBaselineSelect.addEventListener("change", () => {
      compareBaselineId = elements.compareBaselineSelect.value || null;
      void renderCompareImages(compareShotId ? compareInventory().rowsByShotId[compareShotId] || [] : []);
    });
    elements.compareViewedZoom.addEventListener("click", () => openImageZoom(elements.compareViewedImage.src, elements.compareViewedCaption.textContent));
    elements.compareBaselineZoom.addEventListener("click", () => openImageZoom(elements.compareBaselineImage.src, "对照候选（不改变采用）"));
    elements.imageZoomClose.addEventListener("click", closeImageZoom);
    elements.imageZoomDialog.addEventListener("cancel", event => { event.preventDefault(); closeImageZoom(); });
    elements.imageZoomNative.addEventListener("click", () => {
      const native = elements.imageZoomContent.classList.toggle("at-native-size");
      elements.imageZoomNative.textContent = native ? "适应窗口" : "100% 像素";
    });
    elements.compareReview.addEventListener("click", async () => {
      const shotId = compareShotId, candidateId = compareCandidateId;
      if (!shotId || !candidateId) return;
      const outcome = await selectionAdoption.reviewCandidate(shotId, candidateId);
      if (shotId === compareShotId && candidateId === compareCandidateId) {
        renderCompare();
        elements.compareStatus.textContent = outcome?.failed ? "AI 复核未完成：" + outcome.message : "复核结果只属于所点击的这条候选，不自动采用。";
      }
    });
    elements.reworkOpen.addEventListener("click", () => { openReworkPanel(); });
    elements.reworkPreview.addEventListener("click", () => { handleReworkPreview(); });
    elements.reworkEdit.addEventListener("click", () => { handleReworkEdit(); });
    elements.reworkSubmit.addEventListener("click", () => { handleReworkSubmit(); });
    elements.reworkReset.addEventListener("click", () => { resetReworkDraft(); });
    elements.reworkCancel.addEventListener("click", () => { handleReworkCancel(); });
    elements.reworkPanel.addEventListener("keydown", (/** @type {KeyboardEvent} */ event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        handleReworkCancel();
      }
    });
    elements.adoptOpen.addEventListener("click", () => { void handleCandidateSelection("select"); });
    elements.adoptClear.addEventListener("click", () => { void handleCandidateSelection("clear"); });
    elements.reworkDirection.addEventListener("input", () => {
      const shotId = reworkShotId;
      const draft = shotId ? reworkDrafts.get(shotId) : null;
      if (!draft) return;
      draft.direction = elements.reworkDirection.value;
      dirtyReworkDraft(draft);
      updateReworkControls(shotId, draft);
    });
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") inputView?.saveIntakeNow().catch(() => {});
    });
    elements.stageNextUnderstand.addEventListener("click", () => {
      stageShell.select("plan", { focusHeading: true });
    });
    elements.stageNextPlan.addEventListener("click", () => {
      stageShell.select("generate", { focusHeading: true });
    });
    elements.stageNextReview.addEventListener("click", () => {
      stageShell.select("review", { focusHeading: true });
    });
    elements.stageNextDeliver.addEventListener("click", () => {
      stageShell.select("deliver", { focusHeading: true });
    });
    elements.deliverProjectPackage.addEventListener("click", () => { void deliveryView?.handleProjectExport(); });
    elements.deliverExport.addEventListener("click", () => { void deliveryView?.handleDeliveryExport(); });
    if (elements.suiteReviewRun) {
      elements.suiteReviewRun.addEventListener("click", () => { void deliveryView?.runSuiteReview(); });
      elements.suiteAiReviewRun.addEventListener("click", () => { void deliveryView?.runSuiteReview({ ai: true }); });
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
    revokePreviewUrls();
    revokeObjectUrls();
    deliveryView?.dispose();
    compareShotId = null;
    compareCandidateId = null;
    compareToken += 1;
    reworkDrafts = new Map();
    reworkInFlight = false;
    reworkShotId = null;
    reworkSource = null;
    elements.comparePanel.hidden = true;
    elements.reworkPanel.hidden = true;
    elements.reworkPreviewBox.hidden = true;

    // Prompt 版本/历史恢复归 prompts.restore 所有；授权/尝试/候选链恢复归 generation.restore。
    await prompts.restore(action);
    if (!action.alive()) return;
    await generation.restore(action);
    if (!action.alive()) return;
    // 采用记录+已知悉+单图报告由 selectionAdoption.restore 恢复（生成链已在上先灌入）。
    await selectionAdoption.restore(action);
    if (!action.alive()) return;
    // 整套报告与交付记录由 reviewDelivery.restore 恢复（suite+export；ack 已由 adoption.restore 恢复）。
    await reviewDelivery.restore(action);
    if (!action.alive()) return;
    const plan = inputs.suitePlan();
    for (const shot of (plan && Array.isArray(plan.shots) ? plan.shots : [])) {
      // 落库套图 shot_id 恒为 string（见上；此处同）。
      const latest = generation.latestStoredCandidateOf(/** @type {string} */ (shot.shot_id));
      if (!latest) continue;
      const candidate = latest.record;
      const stored = selectionAdoption.reportOf(candidate.candidate_id);
      // 重开只补建缺失/过期报告：内存面已有当前报告则跳过，避免 review_report 版本无意义 +1。
      if (stored && reviewIsCurrent(stored.report, candidate)) continue;
      try {
        await selectionAdoption.ensureReport(/** @type {string} */ (shot.shot_id), candidate, null, action.projectId);
      } catch (error) {
        // 打开项目时的报告补建是尽力而为；失败不阻塞工作区。
      }
      if (!action.alive()) return;
    }
    renderAll();
    await loadCapabilities();
    if (!action.alive()) return;
    // capabilities 是渲染输入（renderAnalyze 读 capabilitiesError、renderAttempts 读
    // 图像 provider），必须在它到位后重新投影，否则初次打开会留下"尚未读到能力信息"
    // 的陈旧文案，直到下一次用户动作触发渲染才消失。
    // 确认有效性依赖 capabilities 投影的有效档：能力到位后再做唯一一次状态派生；
    // 在能力到位前不派生，避免中间态先回写 PLAN_REVIEW、能力到位后又写回 READY_TO_GENERATE
    //（reload 路径两次生效写入，UI2-17 整库逐字判据必红）。
    // 阶段停靠必须在派生之后：understandingReady 等派生结论先就绪，否则重开必停在 understand。
    await deriveAndApplyState();
    refreshStageShell({ reset: true });
    renderAll();
  }

  modelSettings.subscribe(() => {
    capabilities = modelSettings.capabilities;
    capabilitiesError = capabilities ? null : "有效模型配置正在读取或不可用，请打开模型设置。";
    if (projectId) renderAll();
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
      revokeObjectUrls();
      revokePreviewUrls();
      deliveryView?.dispose();
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
