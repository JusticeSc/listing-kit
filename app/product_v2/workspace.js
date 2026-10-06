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
  ATTEMPT_STATES,
  COMPARE_CONTRACT_VERSION,
  COMPARE_SEVERITY_TEXT,
  COMPARE_STATE_TEXT,
  MAX_REFERENCES,
  PRODUCT_INPUT_SCHEMA_VERSION,
  REFERENCE_ROLES,
  REWORK_CONTRACT_VERSION,
  REWORK_PROBLEMS,
  assertConfirmationSheet,
  attemptStateLabel,
  buildConfirmationSheet,
  buildReworkDirective,
  compareCounts,
  compareRowHeadline,
  compareRows,
  defaultCompareTargetId,
  intakeReadiness,
  newActionId,
  nextPendingShotId,
  reviewChecklist,
  reviewIsCurrent,
  reviewSummaryText,
  selectionSetText,
  sortFindings,
  suggestReworkProblems,
  suggestedReworkDirection,
  suitePlanSummary,
} from "./domain/index.js";
import { createGenerationModule } from "./generation.js";
import { consumptionFence, createProjectInputsModule } from "./project-inputs.js";
import { createPromptModule } from "./prompts.js";
import { createReviewDeliveryModule } from "./review-delivery.js";
import { createSelectionAdoptionModule } from "./selection-adoption.js";
import { createDeliveryView } from "./ui/delivery-view.js";
import { createGenerationView } from "./ui/generation-view.js";
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
 * @typedef {import("./ui/generation-view.js").GenerationView} GenerationView
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
 * @typedef {import("./generation.js").PromptEntry} PromptEntry
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
  // 生成视图（设计 §10.1 第二个视图）持 Prompt/确认/尝试三区的 DOM 与命令；同样先声明后装配。
  /** @type {GenerationView|null} */
  let generationView = null;

  const stageShell = createStageShell({
    nav: /** @type {HTMLElement} */ (elements.stageNav),
    panelRoot: /** @type {HTMLElement} */ (elements.stagePanels),
    summary: /** @type {HTMLElement} */ (elements.stageSummary),
    onSelect: (/** @type {string} */ id) => {
      if (id === "deliver") deliveryView?.requestGateRefresh();
      if (id === "understand" && projectId) void inputView?.prepareManualFacts();
      if (id === "generate" && projectId) void generationView?.prepareSystemPrompts();
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
    renderAttempts: () => generationView?.renderAttempts(),
    renderBatch: () => generationView?.renderBatch(),
    status: (/** @type {string} */ text) => { generationView?.setAttemptStatus(text); },
    attemptError: (/** @type {string|undefined} */ message) => { generationView?.showAttemptError(message); },
    clearAttemptError: () => generationView?.clearAttemptError(),
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

  // 生成视图只持 Prompt/确认/尝试三区的 DOM 与命令；Prompt 版本/依据读写都在 prompts、
  // 确认队列与尝试链都在 generation，采用记录只读投影走 selectionAdoption，
  // 落库/派生/跨区渲染经下面的窄回调回到工作区。
  generationView = createGenerationView({
    elements: {
      promptLocked: elements.promptLocked,
      promptEditor: elements.promptEditor,
      localPreparationStatus: elements.localPreparationStatus,
      promptStatus: elements.promptStatus,
      promptList: elements.promptList,
      promptError: elements.promptError,
      generateError: elements.generateError,
      confirmLocked: elements.confirmLocked,
      confirmEditor: elements.confirmEditor,
      confirmStatus: elements.confirmStatus,
      confirmSummary: elements.confirmSummary,
      confirmBlockers: elements.confirmBlockers,
      confirmRisks: elements.confirmRisks,
      confirmList: elements.confirmList,
      confirmAction: elements.confirmAction,
      confirmRecord: elements.confirmRecord,
      confirmError: elements.confirmError,
      attemptLocked: elements.attemptLocked,
      attemptEditor: elements.attemptEditor,
      attemptProvider: elements.attemptProvider,
      attemptStatus: elements.attemptStatus,
      attemptError: elements.attemptError,
      attemptList: elements.attemptList,
      batchBar: elements.batchBar,
      batchProgress: elements.batchProgress,
      batchHint: elements.batchHint,
      queueList: elements.queueList,
      batchStop: elements.batchStop,
      batchReconcile: elements.batchReconcile,
      batchRetry: elements.batchRetry,
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
      isComparing: (shotId) => compareShotId === shotId,
      openCompare,
      renderCompare,
      renderSelectionProgress,
      refreshDerived,
      localizeSlotTerms,
      suiteBlockingText,
      suffixedErrorMessage: errorMessageSuffixed,
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
  function buildScopedSheet(shotIds, { providerProfile = generationView?.currentImageProfile() } = {}) {
    return /** @type {ConfirmationSheetView|null} */ (prompts.sheet(shotIds, providerProfile));
  }

  /**
   * @returns {ConfirmationSheetView|null}
   */
  function buildCurrentSheet() {
    return buildScopedSheet(null);
  }

  /**
   * 这张图的返工确认是否仍然有效：与整套确认同一套「快照逐字比对」判定，
   * 只是作用域只有这一张图——改别的图不会让它失效，改这张图一定会失效。
   * @param {string} shotId
   * @returns {boolean}
   */
  function reworkConfirmationIsCurrent(shotId) {
    const entry = generation.reworkEntry(shotId);
    return Boolean(entry && generationView?.queueShotIsCurrent(entry, shotId));
  }
  /* ------------------------------------------------------------ 生成执行 */

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
      if (row.created_at) business.push(generationView?.shortTime(row.created_at));
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
          + generationView?.shortTime(report.created_at),
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
      const latest = generationView?.promptRecordOf(shotId) || null;
      let version = latest ? latest.version : 0;
      const fromPreview = Boolean(latest && latest.record.compiled.rework
        && latest.record.compiled.rework.directive_id === draft.preview.directive_id);
      if (!fromPreview) {
        if (!draft.directive) throw new Error("先预览返工 Prompt，再查看或编辑全文。");
        const saved = await prompts.compileAndSave(shotId, { rework: draft.directive });
        version = saved.saved.version;
      }
      generationView?.renderPrompts();
      generationView?.renderConfirm();
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
      const latest = generationView?.promptRecordOf(shotId) || null;
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
      generationView?.renderAttempts();
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
      if (action.alive()) generationView?.renderAttempts();
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
        ? (generationView?.confirmationIsCurrent() ? "READY_TO_GENERATE" : "PLAN_REVIEW")
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
    generationView?.render();
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
    elements.confirmAction.addEventListener("click", () => { void generationView?.handleConfirmGeneration(); });
    elements.batchStop.addEventListener("click", () => { generation.stopBatch(); });
    elements.batchReconcile.addEventListener("click", () => { generation.reconcileOnce(); });
    elements.batchRetry.addEventListener("click", () => {
      generation.enterFailedRetry(generation.deriveBatch().retry_queue);
      stageShell.select("generate"); generationView?.renderConfirm();
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
