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
  MAX_REFERENCES,
  PRODUCT_INPUT_SCHEMA_VERSION,
  REFERENCE_ROLES,
  intakeReadiness,
  reviewIsCurrent,
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
  ROLE_TEXT,
  STATUS_TEXT,
  appendTech,
  clearError,
  createElement,
  errorMessageOf,
  showError,
  splitLines,
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
 * @typedef {import("./generation.js").ReviewReportEntry} ReviewReportEntry
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
  // 审核视图（设计 §10.1 第三个视图）持比较/返工/采用三区的 DOM 与就地状态；同样先声明后装配。
  /** @type {CompareView|null} */
  let compareView = null;

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
      selectionStateOf: (/** @type {string} */ shotId) => compareView?.selectionStateOf(shotId) ?? "none",
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
      isComparing: (/** @type {string} */ shotId) => compareView?.isComparing(shotId) ?? false,
      openCompare: (/** @type {string} */ shotId, /** @type {{focus?: boolean}|undefined} */ options) => compareView?.openCompare(shotId, options),
      renderCompare: () => compareView?.renderCompare(),
      renderSelectionProgress: () => compareView?.renderSelectionProgress(),
      refreshDerived,
      localizeSlotTerms,
      suiteBlockingText,
      suffixedErrorMessage: errorMessageSuffixed,
    },
  });

  /** @type {EffectiveCapabilities|null} */
  let capabilities = null;
  /** @type {import("./domain/type-contracts.js").BriefReadiness["blocking"]} */
  let understandingBlocking = [];
  /** @type {unknown} */
  let understandingError = null;
  /** @type {boolean} */
  let understandingReady = false;
  // 审核视图只持比较/返工/采用三区的 DOM 与就地状态；候选/报告读写都在 generation /
  // selectionAdoption（唯一所有者），Prompt 版本/编译在 prompts，跨区刷新经下面的窄回调回到工作区。
  compareView = createCompareView({
    elements: {
      comparePanel: elements.comparePanel,
      compareSubject: elements.compareSubject,
      compareJump: elements.compareJump,
      compareClose: elements.compareClose,
      compareBasisTitle: elements.compareBasisTitle,
      compareReferences: elements.compareReferences,
      compareCandidates: elements.compareCandidates,
      compareChecklist: elements.compareChecklist,
      compareStatus: elements.compareStatus,
      compareViewedImage: elements.compareViewedImage,
      compareViewedCaption: elements.compareViewedCaption,
      compareViewedZoom: elements.compareViewedZoom,
      compareBaselineImage: elements.compareBaselineImage,
      compareBaselineSelect: elements.compareBaselineSelect,
      compareBaselineZoom: elements.compareBaselineZoom,
      compareReview: elements.compareReview,
      imageZoomDialog: elements.imageZoomDialog,
      imageZoomTitle: elements.imageZoomTitle,
      imageZoomContent: elements.imageZoomContent,
      imageZoomNative: elements.imageZoomNative,
      imageZoomClose: elements.imageZoomClose,
      reworkOpen: elements.reworkOpen,
      reworkPanel: elements.reworkPanel,
      reworkBasis: elements.reworkBasis,
      reworkProblems: elements.reworkProblems,
      reworkDirection: elements.reworkDirection,
      reworkPreview: elements.reworkPreview,
      reworkEdit: elements.reworkEdit,
      reworkSubmit: elements.reworkSubmit,
      reworkReset: elements.reworkReset,
      reworkCancel: elements.reworkCancel,
      reworkPreviewBox: elements.reworkPreviewBox,
      reworkPreviewMeta: elements.reworkPreviewMeta,
      reworkPreviewText: elements.reworkPreviewText,
      reworkTech: elements.reworkTech,
      reworkTechBody: elements.reworkTechBody,
      reworkSummary: elements.reworkSummary,
      reworkStatus: elements.reworkStatus,
      reworkError: elements.reworkError,
      adoptOpen: elements.adoptOpen,
      adoptClear: elements.adoptClear,
      adoptStatus: elements.adoptStatus,
      adoptError: elements.adoptError,
      adoptProgress: elements.adoptProgress,
      reviewList: elements.reviewList,
      reviewEmpty: elements.reviewEmpty,
    },
    deps: {
      inputs,
      prompts,
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
      renderPrompts: () => generationView?.renderPrompts(),
      renderConfirm: () => generationView?.renderConfirm(),
      promptRecordOf: (/** @type {string|null} */ shotId) => generationView?.promptRecordOf(shotId) ?? null,
      focusPromptEditor: (/** @type {string} */ shotId) => {
        const area = /** @type {HTMLTextAreaElement|null} */ (elements.promptList.querySelector(
          '[data-shot-id="' + shotId + '"] textarea.prompt-edit-text'));
        if (area) {
          area.scrollIntoView({ block: "center" });
          area.focus();
        }
      },
      readAsset: (/** @type {string} */ pid, /** @type {string} */ sha256) => repository.assets.get(pid, sha256),
      queueShotIsCurrent: (/** @type {import("./generation.js").ConfirmationQueue} */ queue, /** @type {string} */ shotId) => generationView?.queueShotIsCurrent(queue, shotId) ?? false,
      deriveState: deriveAndApplyState,
      reportError: handleInternalError,
      suffixedErrorMessage: errorMessageSuffixed,
    },
  });
  // Prompt 版本/历史/准备状态 → prompts Module；确认队列/scope/mode → generation Module；
  // 采用记录 → selectionAdoption Module；整套报告/门禁/交付包 → reviewDelivery Module；
  // 资料/事实/方案/风格/单图规格 → project-inputs Module（唯一所有者）。
  // 本闭包不再持有上述可变状态，只保留 DOM 草稿编辑状态、视图装配与生命周期。
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
    const requiredSelected = requiredShots.filter((shot) => (compareView?.selectionStateOf(shot.shot_id) ?? "none") === "current");
    const selectedShots = shots.filter((shot) => (compareView?.selectionStateOf(shot.shot_id) ?? "none") === "current");
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
    compareView?.renderReviewList();
    deliveryView?.render();
    deliveryView?.requestGateRefresh();
    return refreshStageShell();
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
      compareView?.openCompare(target, { focus: true });
      const row = /** @type {HTMLElement|null} */ (elements.attemptList.querySelector('.attempt-row[data-shot-id="' + target + '"]'));
      if (row) row.scrollIntoView({ block: "nearest" });
    });
    elements.compareClose.addEventListener("click", () => { compareView?.closeCompare(); });
    elements.compareCandidates.addEventListener("keydown", /** @type {(event: KeyboardEvent) => void} */ ((/** @type {KeyboardEvent} */ event) => compareView?.handleCompareKeydown(event)));
    elements.compareBaselineSelect.addEventListener("change", () => { compareView?.handleBaselineChange(); });
    elements.compareViewedZoom.addEventListener("click", () => compareView?.zoomViewed());
    elements.compareBaselineZoom.addEventListener("click", () => compareView?.zoomBaseline());
    elements.imageZoomClose.addEventListener("click", () => compareView?.closeImageZoom());
    elements.imageZoomDialog.addEventListener("cancel", (/** @type {Event} */ event) => { event.preventDefault(); compareView?.closeImageZoom(); });
    elements.imageZoomNative.addEventListener("click", () => { compareView?.toggleZoomNative(); });
    elements.compareReview.addEventListener("click", () => { void compareView?.handleCompareReview(); });
    elements.reworkOpen.addEventListener("click", () => { compareView?.openReworkPanel(); });
    elements.reworkPreview.addEventListener("click", () => { void compareView?.previewRework(); });
    elements.reworkEdit.addEventListener("click", () => { void compareView?.editRework(); });
    elements.reworkSubmit.addEventListener("click", () => { void compareView?.submitRework(); });
    elements.reworkReset.addEventListener("click", () => { compareView?.resetRework(); });
    elements.reworkCancel.addEventListener("click", () => { compareView?.cancelRework(); });
    elements.reworkPanel.addEventListener("keydown", (/** @type {KeyboardEvent} */ event) => { compareView?.handleReworkKeydown(event); });
    elements.adoptOpen.addEventListener("click", () => { void compareView?.adoptCandidate("select"); });
    elements.adoptClear.addEventListener("click", () => { void compareView?.adoptCandidate("clear"); });
    elements.reworkDirection.addEventListener("input", () => { compareView?.handleReworkDirectionInput(); });
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
    compareView?.resetViewState();

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
    // capabilities 是渲染输入（input-view 经 deps.capabilities() 读能力、renderAttempts 读
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
