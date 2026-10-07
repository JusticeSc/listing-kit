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
  ATTEMPT_DOCUMENT_KIND,
  ATTEMPT_ACTIVE_STATES,
  ATTEMPT_RECONCILE_MODES,
  ATTEMPT_STATES,
  CANDIDATE_DOCUMENT_KIND,
  COMPARE_CONTRACT_VERSION,
  COMPARE_SEVERITY_TEXT,
  COMPARE_STATE_TEXT,
  CONFIRM_DOCUMENT_ID,
  CORE_SLOT_REGISTRY,
  DOMAIN_DOCUMENT_KINDS,
  DIMENSION_AXES,
  DIMENSION_UNITS,
  MAX_DIMENSIONS,
  EXPORT_GATE_CONTRACT_VERSION,
  FACT_SLOT_SCHEMA_VERSION,
  MAX_REFERENCES,
  MANUAL_EDIT_REASON_MAX,
  PRODUCT_INPUT_SCHEMA_VERSION,
  PLATFORM_PROFILES,
  imagePromptProfile,
  REFERENCE_ROLES,
  REVIEW_REPORT_DOCUMENT_KIND,
  REVIEW_SEVERITY_ORDER,
  REWORK_CONTRACT_VERSION,
  REWORK_PROBLEMS,
  SELECTION_CONTRACT_VERSION,
  SLOT_VALUE_TYPES,
  SHOT_TEMPLATES,
  setShotFactBindings,
  shotSignatureOf,
  shotReadiness,
  SUITE_PLAN_DOCUMENT_ID,
  STYLE_SPEC_DOCUMENT_ID,
  acknowledgementDocumentIdOf,
  addCustomShotToPlan,
  addShotFromTemplate,
  attemptCurrentEnvironmentIdentity,
  applySlotAction,
  assertShotSpec,
  assertConfirmationSheet,
  assertSelectionRecord,
  assertStyleSpec,
  assembleSuiteReview,
  attemptPromptStaleness,
  attemptReconcileMode,
  attemptReconcileEnvironment,
  attemptReconcileBlockedMessage,
  attemptStateLabel,
  batchProgressText,
  briefReadiness,
  buildAcknowledgement,
  buildConfirmationSheet,
  buildDeliveryEntries,
  buildEditedPromptRecord,
  buildExportRecord,
  buildPromptRecord,
  buildProductBrief,
  buildReworkDirective,
  buildReviewReport,
  buildSelectionRecord,
  buildSelectionSet,
  canAddSlot,
  canConfirmSlot,
  canDeleteSlot,
  canEditValue,
  candidateMatchesAttempt,
  checkConfirmationRecord,
  checkFactSlot,
  checkPromptRecord,
  compareCounts,
  canonicalJson,
  compareRowHeadline,
  compareRows,
  discardManualEdit,
  reconfirmEditedPrompt,
  compilePrompt,
  confirmationSnapshot,
  confirmationStaleness,
  copyShot,
  coreSlotDefinition,
  defaultCompareTargetId,
  deliveryImagePathOf,
  deliveryFileName,
  deriveSelectionState,
  emptyShotSpecFromShot,
  emptyStyleSpec,
  emptyProductInput,
  evaluateDeliveryGate,
  exportRecordDocumentIdOf,
  intakeReadiness,
  isPlainObject,
  moveShot,
  newActionId,
  nextPendingShotId,
  previousVersionOf,
  promptHash,
  promptStaleness,
  recommendPlan,
  referenceFromAsset,
  reviewChecklist,
  reviewIsCurrent,
  reviewSummaryText,
  reworkIsCurrent,
  reworkSummaryText,
  removeShot,
  requestSnapshotOf,
  selectReferences,
  seedSuitePlan,
  selectionSetText,
  selectionStateLabel,
  selectionSummaryText,
  specChangeProjection,
  sortFindings,
  suggestReworkProblems,
  suggestedReworkDirection,
  selectionFingerprintOf,
  inputsFingerprintOf,
  suiteReviewIsCurrent,
  suiteReviewSummaryText,
  suiteReviewStatusOf,
  SUITE_MAX_IMAGES,
  SUITE_REVIEW_DOCUMENT_ID,
  suitePlanSummary,
  suiteSpecDigest,
  styleSpecDiff,
  topFinding,
  validateSuitePlan,
} from "./domain/index.js";
import { sha256Hex } from "./storage/db.js";
import { STORAGE_ERROR_CODES } from "./storage/errors.js";
import { buildZip, exportProjectPackage } from "./storage/index.js";
import { createGenerationModule } from "./generation.js";
import { createSemanticAnalysisModule } from "./semantic-analysis.js";
import { createStageShell } from "./ui/stage-shell.js";
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
 * 已校验的持久化槽位条目（storage 读出经 checkFactSlot 收窄后的内存面）。
 * @typedef {{slot: FactSlot, version: number}} ValidatedSlotEntry
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
 * createElement 的选项（不引入第二套 DOM 抽象，只收口现有调用）。
 * @typedef {object} WorkspaceElementOptions
 * @property {string} [className]
 * @property {string} [text]
 * @property {Record<string, string|number|boolean|null|undefined>} [attrs]
 * @property {Record<string, unknown>} [props]
 * @property {string} [htmlFor]
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

const INTAKE_DOCUMENT_ID = "intake";
/** 文档种类常量按字面量收口：storage `documents.save` 的泛型按 kind 推导载荷/回读类型。 */
/** @type {"product_input"} */
const INTAKE_KIND = /** @type {"product_input"} */ (DOMAIN_DOCUMENT_KINDS.product_input);
/** @type {"fact_slot"} */
const SLOT_KIND = /** @type {"fact_slot"} */ (DOMAIN_DOCUMENT_KINDS.fact_slot);
/** @type {"suite_plan"} */
const SUITE_KIND = /** @type {"suite_plan"} */ (DOMAIN_DOCUMENT_KINDS.suite_plan);
/** @type {"style_spec"} */
const STYLE_KIND = /** @type {"style_spec"} */ (DOMAIN_DOCUMENT_KINDS.style_spec);
/** @type {"shot_spec"} */
const SHOT_SPEC_KIND = /** @type {"shot_spec"} */ (DOMAIN_DOCUMENT_KINDS.shot_spec);
/** @type {"prompt_version"} */
const PROMPT_KIND = /** @type {"prompt_version"} */ (DOMAIN_DOCUMENT_KINDS.prompt_version);
/** @type {"generation_confirm"} */
const CONFIRM_KIND = /** @type {"generation_confirm"} */ (DOMAIN_DOCUMENT_KINDS.generation_confirm);
/** @type {"generation_attempt"} */
const ATTEMPT_KIND = /** @type {"generation_attempt"} */ (ATTEMPT_DOCUMENT_KIND);
/** @type {"candidate"} */
const CANDIDATE_KIND = /** @type {"candidate"} */ (CANDIDATE_DOCUMENT_KIND);
/** @type {"review_report"} */
const REVIEW_KIND = /** @type {"review_report"} */ (REVIEW_REPORT_DOCUMENT_KIND);

const CAPABILITIES_PATH = "/api/v2/capabilities";
const REVIEW_PATH = "/api/v2/review/candidate";
const SUITE_REVIEW_PATH = "/api/v2/review/suite";
/** @type {"suite_review"} */
const SUITE_REVIEW_KIND = /** @type {"suite_review"} */ (DOMAIN_DOCUMENT_KINDS.suite_review);
const MAX_SUITE_IMAGE_BYTES = 4 * 1024 * 1024;
const REWORK_CONFIRM_PREFIX = "rework:";
/** @type {"selection"} */
const SELECTION_KIND = /** @type {"selection"} */ (DOMAIN_DOCUMENT_KINDS.selection);
/** @type {"review_acknowledgement"} */
const REVIEW_ACK_KIND = /** @type {"review_acknowledgement"} */ (DOMAIN_DOCUMENT_KINDS.review_acknowledgement);
/** @type {"export_record"} */
const EXPORT_RECORD_KIND = /** @type {"export_record"} */ (DOMAIN_DOCUMENT_KINDS.export_record);

const DRAFT_DEBOUNCE_MS = 600;
const ANALYZE_MAX_SLOTS = 12;
const MAX_REVIEW_IMAGE_BYTES = 4 * 1024 * 1024;
const MAX_REVIEW_REFERENCES = 3;
// 单张参考图上限：与图像提交体上限（48MB，3 张 base64 后 ≈40MB）配套；
// 上游 qwen-image 对输入图也有约 10MB 的量级限制。
const MAX_REFERENCE_IMAGE_BYTES = 10 * 1024 * 1024;
const ANALYZE_LOCALE = "zh-CN";
const ANALYZE_PLATFORM = "amazon_us";
const DEFAULT_ANALYZE_FIELDS = Object.freeze([
  "product_name", "description", "selling_points", "focus", "references",
  "locale", "platform", "max_slots", "existing_slot_ids",
]);

const STATUS_TEXT = Object.freeze({
  confirmed: "已确认", proposed: "模型提案", missing: "缺失",
  conflict: "冲突", unknown: "未知", superseded: "已移除",
});

const AUTHORITY_TEXT = Object.freeze({
  core_fixed: "系统固定", category_dynamic: "品类动态", user_custom: "自定义", derived: "派生",
});

const ROLE_TEXT = Object.freeze({
  primary: "商品主图", detail: "细节图", packaging: "包装图", scene: "场景参考",
  competitor: "竞品参考", other: "其他",
});

const EVIDENCE_TEXT = Object.freeze({
  user: "用户输入", asset: "参考图", model: "模型", rule: "规则",
});

/** 严重度与复核状态 → 徽标样式；颜色只表达优先级，不改变任何规则判定。 */
const SEVERITY_BADGE = Object.freeze({
  BLOCK: "is-review-block", HIGH_RISK: "is-review-high", WARNING: "is-review-warn",
  UNKNOWN: "is-review-unknown", PASS: "is-review-pass",
});

const COMPARE_STATE_BADGE = Object.freeze({
  pending: "is-review-high", unknown: "is-review-unknown", clean: "is-review-pass",
  unchecked: "is-review-unchecked",
});

/** 审核优先级：冲突 → 未知 → 缺失 → 未确认 → 已确认 → 已移除。 */
const REVIEW_ORDER = Object.freeze({
  conflict: 0, unknown: 1, missing: 2, proposed: 3, confirmed: 4, superseded: 5,
});

/**
 * 列表排序键：把「必须确认（critical）且尚未收尾」提到冲突/未知之后、缺失之前。
 *
 * critical 是推进阶段门禁的真阻塞项，而 `missing` 大多只是待补的可选事实
 * （品牌、包装内容物等不参与解锁）。只按 REVIEW_ORDER 排，4 个不阻塞的 missing
 * 会压在 3 个阻塞的 proposed+critical 前面，与页面文案「先处理冲突、未知与必须确认
 * 的槽位」相反：读者按视觉顺序走，会先做几件不影响推进的事才碰到真正的门槛。
 * @param {SlotEntry} entry
 * @returns {number}
 */
function reviewRankOf(entry) {
  const status = entry.slot.status;
  if (status !== "confirmed" && status !== "superseded" && entry.slot.critical === true) {
    return 2;
  }
  const base = /** @type {Record<string, number>} */ (REVIEW_ORDER)[status] ?? 9;
  // 冲突/未知仍然最先；缺失及之后的普通状态整体后移一位，给 critical 让位。
  return base < 2 ? base : base + 1;
}

const SCOPE_TEXT = "这一版覆盖“商品资料 → 商品理解 → 套图规划 → 规格 → Prompt → 生成前确认 → 整套生成与逐图进度（含单张核对）→ 审核 → 单图返工 → 人工采用”；整套一致性报告与导出交付尚未接入。";

/**
 * @template {keyof HTMLElementTagNameMap} T
 * @param {T} tag
 * @param {WorkspaceElementOptions} [options]
 * @param {Array<string|Node|null|false|undefined>} [children]
 * @returns {HTMLElementTagNameMap[T]}
 */
function createElement(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  if (options.className) node.className = options.className;
  if (options.text !== undefined) node.textContent = options.text;
  if (options.attrs) {
    for (const [name, value] of Object.entries(options.attrs)) {
      if (value !== null && value !== undefined) node.setAttribute(name, String(value));
    }
  }
  if (options.props) Object.assign(node, options.props);
  for (const child of children) if (child) node.append(child);
  return node;
}

/**
 * @param {unknown} text
 * @returns {string[]}
 */
function splitLines(text) {
  return String(text || "").split("\n").map((item) => item.trim()).filter((item) => item.length > 0);
}

/**
 * 是否为纯字符串数组（商品资料卖点的合法形状；非字符串元素不算数）。
 * @param {unknown} value
 * @returns {value is string[]}
 */
function isStringArray(value) {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

/**
 * 存储读出的商品资料载荷（读路径不做业务校验）：与装载路径同一口径补齐契约字段，
 * 不猜测缺失值，也不放行非对象载荷。
 * @param {unknown} payload
 * @returns {ProductInput}
 */
function productInputFromStored(payload) {
  return { ...emptyProductInput(), ...(isPlainObject(payload) ? payload : {}) };
}

/**
 * 商品资料参考图（由本应用写出的 ProductReference）：三方合并只接受这种形状。
 * @param {unknown} value
 * @returns {value is ProductReference}
 */
function isProductReference(value) {
  return isPlainObject(value) && typeof value.asset_sha256 === "string"
    && typeof value.role === "string";
}

/**
 * V2.6.4 渐进披露：工程字段（sha256 / action / task / 指纹）默认收进「技术详情」。
 * 业务判读所需信息留在主行；技术字段不删除、展开即可见，也仍可从 dataset 读取。
 * @param {string|string[]} lines
 * @param {string} [label]
 * @returns {HTMLElementTagNameMap["details"]|null}
 */
function techDetails(lines, label = "技术详情") {
  const items = (Array.isArray(lines) ? lines : [lines]).filter(
    (item) => typeof item === "string" && item.length > 0);
  if (!items.length) return null;
  const details = createElement("details", { className: "tech-details" });
  details.append(createElement("summary", { text: label }));
  details.append(createElement("p", { className: "meta tech-body", text: items.join(" · ") }));
  return details;
}

/**
 * 追加技术详情节点：无内容时是空操作，保持既有「有内容才出现」的渲染行为。
 * @param {HTMLElement} parent
 * @param {string|string[]} lines
 * @param {string} [label]
 * @returns {void}
 */
function appendTech(parent, lines, label) {
  const node = techDetails(lines, label);
  if (node) parent.append(node);
}

/**
 * @param {FactSlot} slot
 * @returns {string}
 */
function formatValue(slot) {
  const value = slot.value;
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.join("；");
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

/**
 * @param {Array<{message: string}>|DomainProblem[]|null|undefined} blocking
 * @param {((message: string) => string)|null} [mapMessage]
 * @returns {string}
 */
function describeBlocking(blocking, mapMessage = null) {
  return (blocking || [])
    .map((item) => (mapMessage ? mapMessage(item.message) : item.message))
    .join("；");
}

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

  const stageShell = createStageShell({
    nav: /** @type {HTMLElement} */ (elements.stageNav),
    panelRoot: /** @type {HTMLElement} */ (elements.stagePanels),
    summary: /** @type {HTMLElement} */ (elements.stageSummary),
    onSelect: (/** @type {string} */ id) => {
      if (id === "deliver") requestDeliveryGateRefresh();
      if (id === "understand" && projectId) void prepareManualFacts();
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

  // V2.R5.1：生成执行 Module——单张提交/核对/候选保存/VLM 复核/整套批次的唯一执行权威。
  // workspace 保留只读输入的读者与投影回调；持久化顺序全部由 Module 决定。
  /** @type {GenerationModule} */
  const generation = createGenerationModule({
    // workspace 的 repository 即 storage ProjectRepository（权威面）；生成 Module 只消费
    // 其 documents.save/get + assets.get/put 子集，这里按消费面收窄（同一运行时对象）。
    repository: /** @type {import("./generation.js").GenerationRepository} */ (/** @type {unknown} */ (repository)),
    beginAction: beginAction,
    projectIdReader: () => projectId,
    environmentReader: /** @param {unknown} saved */ (saved) => modelSettings.imageEnvironment(
      (/** @type {{provider?: {provider_id?: string}, payload?: {fingerprint?: {snapshot?: {execution_target?: {provider_id?: string}}}}}} */ (saved))?.provider?.provider_id || (/** @type {{payload?: {fingerprint?: {snapshot?: {execution_target?: {provider_id?: string}}}}}} */ (saved))?.payload?.fingerprint?.snapshot?.execution_target?.provider_id,
      (/** @type {{execution_identity?: {credential_reference?: {source?: string}}, payload?: {fingerprint?: {snapshot?: {execution_target?: {credential_source?: string}}}}}} */ (saved))?.execution_identity?.credential_reference?.source || (/** @type {{payload?: {fingerprint?: {snapshot?: {execution_target?: {credential_source?: string}}}}}} */ (saved))?.payload?.fingerprint?.snapshot?.execution_target?.credential_source),
    requestHeaders: /** @param {import("./model-settings.js").Purpose} purpose */ (purpose, providerId, source) => modelSettings.headers(purpose, providerId, source),
    suitePlanReader: () => suitePlan,
    // suitePlanSummary 的 shot_id/required_blocked 保留 Shot 原值（可空）；已落库计划恒有 id，
    // 这里按调用契约收口（声明面的收窄以 domain 声明为准）。
    suiteSummaryReader: () => (suitePlan ? /** @type {SuitePlanSummary} */ (suitePlanSummary(suitePlan, suiteContext())) : null),
    promptEntryReader: (/** @type {string} */ shotId, /** @type {number|null|undefined} */ version) => version ? promptVersionAt(shotId, version) : promptRecordOf(shotId),
    confirmationReader: (/** @type {string} */ shotId) => [...reworkConfirmations.values()].reverse()
      .find(queue => generation.pendingConfirmedShots(queue).includes(shotId))
      || [...confirmedQueues.values()].reverse()
      .find(queue => generation.pendingConfirmedShots(queue).includes(shotId)) || null,
    promptBasisReader: (/** @type {string} */ shotId, /** @type {ImagePromptProfile} */ provider) => promptCurrentBasis(shotId, provider),
    referenceSourceReader: () => intake.references.map((item) => ({
      role: item.role, sha256: item.asset_sha256,
    })),
    reviewRequestBuilder: (/** @type {string} */ shotId, /** @type {CandidateRecord} */ candidate, /** @type {string} */ pid) => buildReviewRequest(shotId, candidate, pid),
    confirmationSaved: async (queue, action) => {
      if (!action.alive()) return;
      rememberConfirmation(queue.documentId, queue);
      if (queue.documentId === CONFIRM_DOCUMENT_ID) {
        generationScope = null;
        generationMode = "initial";
      }
      await deriveAndApplyState();
    },
    renderAttempts: renderAttempts,
    renderBatch: renderBatch,
    status: (/** @type {string} */ text) => { elements.attemptStatus.textContent = text; },
    attemptError: showAttemptError,
    clearAttemptError: clearAttemptError,
  });

  const semanticAnalysis = createSemanticAnalysisModule({
    repository,
    beginAction,
    prepare: prepareAnalysis,
    sourceIsCurrent: analysisSourceIsCurrent,
    apply: applyProposal,
  });

  /** @type {ProductInput} */
  let intake = emptyProductInput();
  /** @type {number} */
  let intakeVersion = 0;
  /** @type {string} */
  let intakeFingerprint = "";
  /** @type {Map<string, ValidatedSlotEntry>} */
  let slots = new Map();
  /** @type {EffectiveCapabilities|null} */
  let capabilities = null;
  /** @type {string|null} */
  let capabilitiesError = null;
  /** @type {import("./domain/type-contracts.js").BriefReadiness["blocking"]} */
  let understandingBlocking = [];
  /** @type {unknown} */
  let understandingError = null;
  /** @type {{slots: number, applied: number, provider: string, model: string|null, sourceVersion: number, referenceImagesSent: boolean, at: string, summary: string}|null} */
  let lastAnalyze = null;
  /** @type {boolean} */
  let analyzeRequiresConfirmation = false;
  /** @type {string[]} */
  let analyzeProblems = [];
  /** @type {boolean} */
  let showAll = false;
  /** @type {{slotId: string|null, mode: string|null}} */
  let interaction = { slotId: null, mode: null };
  /** @type {SuitePlan|null} */
  let suitePlan = null;
  /** @type {number} */
  let suiteVersion = 0;
  /** @type {boolean} */
  let understandingReady = false;
  /** @type {StyleSpec} */
  let styleSpec = emptyStyleSpec();
  /** @type {number} */
  let styleVersion = 0;
  /** @type {Map<string, {spec: ShotSpec, version: number}>} */
  let shotSpecs = new Map();
  /** @type {Map<string, PromptEntry>} */
  let promptVersions = new Map();
  /** @type {Map<string, Map<number, PromptEntry>>} */
  let promptHistory = new Map();
  /** @type {Map<string, ConfirmationQueue & {documentId: string}>} */
  let confirmedQueues = new Map();
  /** @type {(ConfirmationQueue & {documentId: string})|null} */
  let confirmRecord = null;
  /** @type {Map<string, {report: SuiteReviewReport, version: number}>} */
  let suiteReports = new Map();
  /** @type {boolean} */
  let suiteRunInFlight = false;
  // V2.6.2：交付门禁结果与交付记录（记录只追加，不新增第二套状态）。
  /** @type {(DeliveryGateResult & {failed?: boolean, message?: string|null, checked_at?: string})|{failed: boolean, message?: string|null, ready_to_export: boolean, findings: GateFinding[], blocking: GateFinding[], unknowns: UnknownItem[], unresolved_unknowns: UnknownItem[]}|null} */
  let deliveryGateState = null;
  /** @type {ReturnType<typeof setTimeout>|null} */
  let deliveryGateTimer = null;
  /** @type {boolean} */
  let deliveryInFlight = false;
  /** @type {{file_name: string, byte_size: number, sha256: string, at: string, url: string|null}|null} */
  let deliveryRecord = null;
  /** @type {Map<string, {record: import("./domain/type-contracts.js").AcknowledgementRecord, version: number}>} */
  let acknowledgements = new Map();
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
  /** @type {Map<string, ConfirmationQueue & {documentId: string}>} */
  let reworkConfirmations = new Map();
  /** @type {boolean} */
  let reworkInFlight = false;
  /** @type {string|null} */
  let reworkShotId = null;
  /** @type {{shot_id: string, candidate_id: string, asset_sha256: string, version: number|null}|null} */
  let reworkSource = null;
  /** @type {Map<string, {record: SelectionRecord, version: number}>} */
  let selections = new Map();
  /** @type {boolean} */
  let adoptInFlight = false;
  /** @type {Map<string, string>} */
  let previewUrls = new Map();
  /** @type {boolean} */
  let localPreparationInFlight = false;
  /** @type {boolean} */
  let submissionInFlight = false;
  /** @type {WorkspaceGenerationIntent|null} */
  let displayedGenerationIntent = null;
  /** @type {string[]|null} */
  let generationScope = null;
  /** @type {import("./domain/type-contracts.js").ConfirmationSubmissionMode} */
  let generationMode = "initial";
  /** @type {string} */
  let lastPreparationInputs = "";
  /** @type {ReturnType<typeof setTimeout>|null} */
  let saveTimer = null;
  /** @type {string[]} */
  let objectUrls = [];
  /** @type {boolean} */
  let bound = false;
  /**
   * R3.3：不再自管递增 token；每个动作经 session.beginAction() 冻结
   * { generation, projectId }，alive() 同时判断"会话代未变"与"仍是同一项目"。
   * @type {{merged?: boolean, unresolved?: Array<{field: string, mine: unknown, theirs: unknown}>, version?: number, at?: string}|null}
   */
  let intakeConflict = null;
  /* 双标签陈旧编辑的三态（V2.R3.3）：
   * - merged=true：已按三路合并落库（本地输入优先），视图已同步到新版本；
   * - unresolved 非空：合并仍冲突，冲突编辑器打开中，必须人工逐项解决后再次保存；
   * - 仅 version/at：合并失败的旧路径，就地报冲突并不覆盖，等待再次保存追加新版本。 */
  /* ------------------------------------------------------ 公共读写与工具 */

  /**
   * 抛出值的可读信息（catch 变量为 unknown；只读 message 字符串，缺失即空串）。
   * @param {unknown} error
   * @param {string} fallback
   * @returns {string}
   */
  function errorMessageOf(error, fallback) {
    if (error instanceof Error && typeof error.message === "string" && error.message) return error.message;
    if (error !== null && typeof error === "object" && "message" in error
      && typeof error.message === "string" && error.message) return error.message;
    return fallback;
  }

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
   * @param {HTMLElement} element
   * @param {string} message
   * @returns {void}
   */
  function showError(element, message) {
    element.textContent = message;
    element.hidden = false;
  }

  /**
   * @param {HTMLElement} element
   * @returns {void}
   */
  function clearError(element) {
    element.textContent = "";
    element.hidden = true;
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
   * @returns {CompleteProductInput}
   */
  function currentIntakePayload() {
    return {
      schema_version: PRODUCT_INPUT_SCHEMA_VERSION,
      product_name: elements.intakeName.value.trim(),
      description: elements.intakeDescription.value.trim(),
      selling_points: splitLines(elements.intakePoints.value),
      focus: elements.intakeFocus.value.trim(),
      references: intake.references.map((item) => ({ ...item })),
    };
  }

  /**
   * @param {ProductInput} payload
   * @returns {string}
   */
  function fingerprintOf(payload) {
    return JSON.stringify([
      payload.product_name, payload.description, payload.selling_points,
      payload.focus, payload.references,
    ]);
  }

  /**
   * @returns {ValidatedSlotEntry[]}
   */
  function slotEntries() {
    return [...slots.values()].map((entry) => ({ slot: entry.slot, version: entry.version }));
  }

  /**
   * @param {string} slotId
   * @returns {number}
   */
  function dependencyCountOf(slotId) {
    let count = 0;
    for (const entry of slots.values()) {
      if ((entry.slot.depends_on || []).includes(slotId)) count += 1;
    }
    return count;
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
    const entries = intake.references.map((item) => ({ ...item }));
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
    const entry = intake.references[index];
    if (!entry) return;
    const action = beginAction();
    entry.role = role;
    clearError(elements.refError);
    await saveIntakeNow();
    if (!action.alive()) return;
    renderAll();
  }

  /**
   * @param {number} index
   * @returns {Promise<void>}
   */
  async function handleRemoveReference(index) {
    if (!intake.references[index]) return;
    const action = beginAction();
    intake.references.splice(index, 1);
    clearError(elements.refError);
    await saveIntakeNow();
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
    const known = new Set(intake.references.map((item) => item.asset_sha256));
    let wantsPrimary = !intake.references.some((item) => item.role === "primary");
    let added = 0;
    for (const file of files) {
      if (intake.references.length >= MAX_REFERENCES) {
        if (action.alive()) {
          showError(elements.refError, "参考图最多 " + MAX_REFERENCES + " 张，多出的文件没有加入。");
        }
        break;
      }
      if (file.size > MAX_REFERENCE_IMAGE_BYTES) {
        if (action.alive()) {
          showError(elements.refError,
            "“" + file.name + "”超过单张参考图上限 10MB，已跳过；请压缩后再上传。");
        }
        continue;
      }
      let width = null;
      let height = null;
      try {
        const bitmap = await createImageBitmap(file);
        width = bitmap.width;
        height = bitmap.height;
        bitmap.close();
      } catch (error) {
        if (action.alive()) {
          showError(elements.refError, "“" + file.name + "”不是可读取的图片，已跳过。");
        }
        continue;
      }
      if (!action.alive()) break;   // 会话已切换：不再向仓库继续写参考图
      const role = wantsPrimary ? "primary" : "other";
      const asset = await repository.assets.put(action.projectId, {
        blob: file,
        mediaType: file.type || "application/octet-stream",
        originalName: file.name,
        role,
        width,
        height,
      });
      if (known.has(asset.sha256)) {
        if (action.alive()) {
          showError(elements.refError, "“" + file.name + "”与已有参考图内容相同，已跳过。");
        }
        continue;
      }
      known.add(asset.sha256);
      if (action.alive()) {
        intake.references.push(referenceFromAsset(asset, { role }));
      }
      wantsPrimary = false;
      added += 1;
    }
    if (added) {
      await saveIntakeNow();
      if (action.alive()) renderAll();
    }
  }

  /* ---------------------------------------------------------- 商品资料 */

  /**
   * @returns {void}
   */
  function updateDraftStatus() {
    if (intakeConflict) {
      // R3.3 双标签陈旧编辑：就地报冲突，不静默胜出。文档历史是 append-only。
      if (intakeConflict.merged === true) {
        elements.intakeDraft.textContent = "另一个标签页已保存版本 v" + intakeConflict.version
          + "：你的输入已按本地优先自动合并为新版本；请核对内容后再次保存确认。";
      } else if (Array.isArray(intakeConflict.unresolved) && intakeConflict.unresolved.length > 0) {
        elements.intakeDraft.textContent = "另一个标签页已保存版本 v" + intakeConflict.version
          + "：有 " + intakeConflict.unresolved.length + " 项需要你逐项解决，请在冲突编辑器里处理。";
      } else {
        elements.intakeDraft.textContent = "检测到另一个标签页已保存版本 v" + intakeConflict.version
          + "：你正在编辑的内容没有覆盖它；再次保存会追加为新版本。";
      }
      return;
    }
    elements.intakeDraft.textContent = intakeVersion
      ? "草稿已保存 · 版本 " + intakeVersion + (intake.product_name ? "" : "（尚未填写商品名称）")
      : "还没有保存过草稿。";
  }

  /**
   * @returns {void}
   */
  function scheduleDraftSave() {
    clearTimeout(saveTimer ?? undefined);
    // 冻结动作归属：这个定时器属于当前会话/项目；换项目或换会话后不再写。
    const scheduled = beginAction();
    elements.intakeDraft.textContent = "正在编辑…";
    renderAnalyze();
    saveTimer = setTimeout(() => {
      saveTimer = null;
      if (!scheduled.alive()) return;
      saveIntakeNow()
        .then(() => deriveAndApplyState())
        .then(() => { if (scheduled.alive()) { renderAnalyze(); renderHeaderText(project); } })
        .catch(handleInternalError);
    }, DRAFT_DEBOUNCE_MS);
  }

  /**
   * @returns {Promise<boolean>}
   */
  function saveIntakeNow() {
    if (saveTimer !== null) {
      clearTimeout(saveTimer);
      saveTimer = null;
    }
    const action = beginAction();
    if (!action.projectId) {
      // 会话已关闭后的迟到调用：不动仓库，编辑器里的输入原样保留给用户。
      return Promise.resolve(false);
    }
    const pid = action.projectId;
    const payload = currentIntakePayload();
    const fingerprint = fingerprintOf(payload);
    if (fingerprint === intakeFingerprint) {
      updateDraftStatus();
      return Promise.resolve(false);
    }
    return (async () => {
      let record;
      try {
        record = await repository.documents.save(pid, {
          kind: INTAKE_KIND,
          documentId: INTAKE_DOCUMENT_ID,
          payload,
          // R3.3 OCC：编辑传观察版本。另一标签页已前进时按 REVISION_CONFLICT 就地报冲突。
          expectedVersion: intakeVersion > 0 ? intakeVersion : null,
        });
      } catch (error) {
        if (typeof error === "object" && error !== null && "code" in error
          && error.code === STORAGE_ERROR_CODES.REVISION_CONFLICT) {
          const latest = await repository.documents.getLatest(pid, INTAKE_KIND, INTAKE_DOCUMENT_ID);
          if (!action.alive()) return false;
          const latestPayload = latest && latest.payload ? latest.payload : null;
          const latestVersion = latest ? latest.version : 0;
          const basePayload = intake;
          const baseVersion = intakeVersion;
          const merged = latestPayload ? mergeIntakePayloads(basePayload, payload, latestPayload) : null;
          if (merged && merged.merged && merged.record) {
            const mergedRecord = await repository.documents.save(pid, {
              kind: INTAKE_KIND,
              documentId: INTAKE_DOCUMENT_ID,
              payload: merged.record,
              expectedVersion: latestVersion,
            });
            if (!action.alive()) return false;
            intake = merged.record;
            intakeVersion = mergedRecord.version;
            intakeFingerprint = fingerprintOf(merged.record);
            intakeConflict = {
              version: latestVersion,
              at: new Date().toISOString(),
              merged: true,
            };
            updateDraftStatus();
            renderIntake();
            return false;
          }
          if (merged && Array.isArray(merged.unresolved) && merged.unresolved.length > 0) {
            if (!action.alive()) return false;
            intakeConflict = {
              version: latestVersion,
              at: new Date().toISOString(),
              merged: false,
              unresolved: merged.unresolved,
            };
            updateDraftStatus();
            renderConflictEditor(basePayload, baseVersion, latestPayload, latestVersion, merged.unresolved);
            return false;
          }
          intakeConflict = {
            version: latest && latest.payload ? latest.version : 0,
            at: new Date().toISOString(),
          };
          updateDraftStatus();
          return false;
        }
        throw error;
      }
      // 记录已按冻结项目落库；界面状态只属于还活着的会话。
      if (!action.alive()) return false;
      intake = payload;
      intakeVersion = record.version;
      intakeFingerprint = fingerprint;
      intakeConflict = null;
      updateDraftStatus();
      return true;
    })();
  }

  /**
   * 双标签三路合并（V2.R3.3）：base=本标签页上次成功读取的版本，mine=本次想保存的
   * 输入，theirs=另一个标签页已落库的最新版本。字段级规则：
   * - 文本字段：以本地输入为准；theirs 单独改过且 mine 没改的字段并入（不丢对方输入）；
   * - 卖点：单方改动直接取改动方；双方都改则按本地优先并集；
   * - 参考图：按 asset_sha256 并集，role 以本地为准、本地没有的沿用对方；
   * - 同一文本字段 base/theirs/mine 三方互不相同 => 不自动合并，逐项进冲突编辑器。
   * 返回 { merged:true, record } 或 { merged:false, unresolved:[{field, mine, theirs}] }；
   * 全部失败返回 null（走旧的就地报冲突路径）。
   */
  /**
   * @param {unknown} base
   * @param {unknown} mine
   * @param {unknown} theirs
   * @returns {{merged: boolean, unresolved?: Array<{field: string, mine: unknown, theirs: unknown}>, record?: ProductInput}|null}
   */
  function mergeIntakePayloads(base, mine, theirs) {
    if (!isPlainObject(mine) || !isPlainObject(theirs)) return null;
    const baseSafe = isPlainObject(base) ? base : {};
    const mineRefs = Array.isArray(mine.references) ? mine.references : [];
    const theirRefs = Array.isArray(theirs.references) ? theirs.references : [];
    /** @type {Map<string, ProductReference>} */
    const refBySha = new Map();
    for (const ref of theirRefs) {
      if (isProductReference(ref)) refBySha.set(ref.asset_sha256, ref);
    }
    for (const ref of mineRefs) {
      if (isProductReference(ref)) refBySha.set(ref.asset_sha256, ref);
    }
    const textFields = ["product_name", "description", "focus"];
    const unresolved = [];
    /** @type {Record<string, string>} */
    const mergedTexts = {};
    for (const field of textFields) {
      const b = typeof baseSafe[field] === "string" ? baseSafe[field] : "";
      const m = typeof mine[field] === "string" ? mine[field] : "";
      const h = typeof theirs[field] === "string" ? theirs[field] : "";
      if (m === h) { mergedTexts[field] = m; continue; }
      if (m === b) { mergedTexts[field] = h; continue; }
      if (h === b) { mergedTexts[field] = m; continue; }
      unresolved.push({ field: field, mine: m, theirs: h });
    }
    const basePoints = isStringArray(baseSafe.selling_points) ? baseSafe.selling_points : [];
    const minePoints = isStringArray(mine.selling_points) ? mine.selling_points : [];
    const theirPoints = isStringArray(theirs.selling_points) ? theirs.selling_points : [];
    const joins = (/** @type {string[]} */ list) => list.join("\u0000");
    /** @type {string[]} */
    let mergedPoints = minePoints;
    if (joins(minePoints) === joins(theirPoints)) mergedPoints = minePoints;
    else if (joins(minePoints) === joins(basePoints)) mergedPoints = theirPoints;
    else if (joins(theirPoints) === joins(basePoints)) mergedPoints = minePoints;
    else {
      mergedPoints = [...minePoints];
      for (const point of theirPoints) {
        if (!mergedPoints.includes(point)) mergedPoints.push(point);
      }
    }
    if (unresolved.length > 0) {
      return { merged: false, unresolved: unresolved };
    }
    return {
      merged: true,
      record: {
        schema_version: PRODUCT_INPUT_SCHEMA_VERSION,
        product_name: mergedTexts.product_name,
        description: mergedTexts.description,
        focus: mergedTexts.focus,
        selling_points: mergedPoints,
        references: [...refBySha.values()],
      },
    };
  }

  /** 冲突编辑器：三方互不相同的字段逐项展示，只能二选一；解决后保存为新版本。 */
  /**
   * @param {unknown} basePayload
   * @param {number} baseVersion
   * @param {unknown} latestPayload
   * @param {number} latestVersion
   * @param {Array<{field: string, mine: unknown, theirs: unknown}>} unresolved
   * @returns {void}
   */
  function renderConflictEditor(basePayload, baseVersion, latestPayload, latestVersion, unresolved) {
    const editor = document.createElement("div");
    editor.className = "conflict-editor";
    editor.setAttribute("role", "group");
    editor.setAttribute("aria-label", "双标签编辑冲突，需要人工逐项解决");
    const title = document.createElement("p");
    title.className = "meta";
    title.textContent = "另一个标签页已保存版本 v" + latestVersion
      + "（你的版本 v" + baseVersion + "）：以下字段两边都改了，请逐项选择保留哪一边。";
    editor.append(title);
    const picks = new Map();
    for (const item of unresolved) {
      const row = document.createElement("div");
      row.className = "conflict-row";
      row.dataset.field = item.field;
      const label = document.createElement("p");
      label.className = "name";
      label.textContent = "字段：" + item.field;
      const mineBtn = document.createElement("button");
      mineBtn.type = "button";
      mineBtn.textContent = "保留我的";
      mineBtn.setAttribute("aria-pressed", "true");
      const theirsBtn = document.createElement("button");
      theirsBtn.type = "button";
      theirsBtn.textContent = "用对方的";
      theirsBtn.setAttribute("aria-pressed", "false");
      picks.set(item.field, "mine");
      mineBtn.addEventListener("click", () => {
        picks.set(item.field, "mine");
        mineBtn.setAttribute("aria-pressed", "true");
        theirsBtn.setAttribute("aria-pressed", "false");
      });
      theirsBtn.addEventListener("click", () => {
        picks.set(item.field, "theirs");
        mineBtn.setAttribute("aria-pressed", "false");
        theirsBtn.setAttribute("aria-pressed", "true");
      });
      const mineText = document.createElement("p");
      mineText.className = "meta";
      mineText.textContent = "我的：" + String(item.mine === "" ? "（空）" : item.mine);
      const theirsText = document.createElement("p");
      theirsText.className = "meta";
      theirsText.textContent = "对方 v" + latestVersion + "：" + String(item.theirs === "" ? "（空）" : item.theirs);
      row.append(label, theirsText, mineText, mineBtn, theirsBtn);
      editor.append(row);
    }
    const saveBtn = document.createElement("button");
    saveBtn.type = "button";
    saveBtn.className = "primary";
    saveBtn.textContent = "按我的选择保存为新版本";
    saveBtn.addEventListener("click", () => {
      /** @type {Record<string, unknown>} */
      const resolved = {};
      for (const item of unresolved) {
        resolved[item.field] = picks.get(item.field) === "theirs" ? item.theirs : item.mine;
      }
      const base = latestPayload && typeof latestPayload === "object" ? latestPayload : {};
      const merged = mergeIntakePayloads(base, Object.assign({}, base, resolved), base);
      const record = merged && merged.merged && merged.record
        ? merged.record
        : { ...emptyProductInput(), ...(isPlainObject(base) ? base : {}), ...resolved };
      const action = beginAction();
      const pid = action.projectId;
      if (!pid) return;
      repository.documents.save(pid, {
        kind: INTAKE_KIND,
        documentId: INTAKE_DOCUMENT_ID,
        payload: record,
        expectedVersion: latestVersion,
      }).then((saved) => {
        if (!action.alive()) return;
        intake = record;
        intakeVersion = saved.version;
        intakeFingerprint = fingerprintOf(record);
        intakeConflict = null;
        editor.remove();
        updateDraftStatus();
        renderIntake();
      }).catch((error) => {
        if (!action.alive()) return;
        showError(elements.intakeError, errorMessageOf(error, "冲突解决没有保存，请重试。"));
      });
    });
    const cancelBtn = document.createElement("button");
    cancelBtn.type = "button";
    cancelBtn.textContent = "稍后处理";
    cancelBtn.addEventListener("click", () => { editor.remove(); });
    editor.append(saveBtn, cancelBtn);
    elements.intakeError.textContent = "";
    elements.intakeError.hidden = true;
    elements.intakeError.before(editor);
  }

  /**
   * @returns {void}
   */
  function renderIntake() {
    elements.intakeName.value = intake.product_name || "";
    elements.intakeDescription.value = intake.description || "";
    elements.intakePoints.value = (intake.selling_points || []).join("\n");
    elements.intakeFocus.value = intake.focus || "";
    updateDraftStatus();
  }
  /* -------------------------------------------------------------- 分析 */

  /**
   * @returns {DomainProblem[]}
   */
  function gateProblems() {
    return intakeReadiness(currentIntakePayload()).blocking;
  }

  /**
   * @param {unknown} provider
   * @returns {boolean}
   */
  function seesImages(provider) {
    const caps = isPlainObject(provider) && isPlainObject(provider.capabilities) ? provider.capabilities : {};
    return caps.vision === true || caps.supports_images === true;
  }

  /**
   * @returns {void}
   */
  function renderAnalyze() {
    const problems = gateProblems();
    const ready = problems.length === 0;
    const provider = capabilities?.provider;
    const vision = seesImages(provider);
    const imageCount = Math.min(intake.references.length, 3);
    elements.analyzeNewAfterUnknown.hidden = !analyzeRequiresConfirmation;
    elements.analyzeNewAfterUnknown.disabled = semanticAnalysis.isRunning()
      || !ready || !provider || provider.configured === false;
    elements.analyzeRun.textContent = (lastAnalyze ? "再次" : "") + (vision ? "图文理解" : "仅文字理解") + "（可选）";
    elements.analyzeRun.disabled = semanticAnalysis.isRunning() || !ready || !provider || provider.configured === false;
    elements.analyzeGate.textContent = semanticAnalysis.isRunning() ? "理解中；不会自动重试…"
      : !ready ? "还缺：" + describeBlocking(problems, localizeSlotTerms)
        : !provider || provider.configured === false
          ? "此用途缺少有效模型或凭据；请打开模型设置。人工填写不受影响。"
          : "将发给 " + provider.model_id + "：当前名称、介绍、卖点与重点，"
            + (vision ? imageCount + " 张实际图片（按列表顺序，主图优先，最多 3 张）"
              : "仅参考图元数据，不发送图片字节")
            + "。供应商按实际调用计费；不能据元数据宣称已经看图。";

    if (lastAnalyze) {
      elements.analyzeResult.hidden = false;
      elements.analyzeResult.textContent = "最近一次分析：" + lastAnalyze.slots + " 个提案，写入 "
        + lastAnalyze.applied + " 个槽位 · " + lastAnalyze.provider
        + (lastAnalyze.model ? "（" + lastAnalyze.model + "）" : "")
        + " · 原资料 v" + lastAnalyze.sourceVersion
        + (lastAnalyze.referenceImagesSent ? " · 已发送实际图片" : " · 未发送图片字节")
        + " · " + lastAnalyze.at + (lastAnalyze.summary ? " · " + lastAnalyze.summary : "");
    } else {
      elements.analyzeResult.hidden = true;
      elements.analyzeResult.textContent = "";
    }

    if (analyzeProblems.length) {
      const list = createElement("ul", { className: "inline-list" });
      for (const item of analyzeProblems) list.append(createElement("li", { text: item }));
      elements.analyzeError.replaceChildren(
        createElement("span", { text: "部分提案没有写入：" }), list);
      elements.analyzeError.hidden = false;
    }
  }


  /**
   * @param {string|null} [pid]
   * @param {unknown} [semanticProvider]
   * @param {CompleteProductInput} [payload]
   * @returns {Promise<SemanticRequestBody>}
   */
  async function buildAnalyzeBody(pid = projectId, semanticProvider = capabilities?.provider, payload = currentIntakePayload()) {
    if (!pid) throw new Error("缺少项目上下文，无法读取参考图字节。");
    /** @type {{sha256: string, media_type: string, role: ReferenceRole, original_name: string|null}[]} */
    const references = [];
    const vision = seesImages(semanticProvider);
    const selected = vision
      ? [...payload.references.filter(ref => ref.role === "primary"),
        ...payload.references.filter(ref => ref.role !== "primary")].slice(0, 3) : [];
    const imageHashes = new Set(selected.map(ref => ref.asset_sha256));
    /** @type {NonNullable<import("./semantic-analysis.js").SemanticRequestBody["reference_images"]>} */
    const referenceImages = [];
    for (const entry of payload.references) {
      const asset = await repository.assets.get(pid, entry.asset_sha256);
      if (!asset) {
        throw new Error("参考图资产缺失（sha256 " + entry.asset_sha256.slice(0, 12) + "…），请重新上传。");
      }
      references.push({
        sha256: asset.sha256,
        media_type: asset.media_type || "application/octet-stream",
        role: entry.role,
        original_name: asset.original_name || null,
      });
      if (imageHashes.has(entry.asset_sha256)) {
        if (!(asset.blob instanceof Blob) || !["image/png", "image/jpeg"].includes(asset.media_type)
            || asset.blob.size > 4 * 1024 * 1024) {
          throw new Error("图文理解每张参考图须为 PNG/JPEG 且不超过 4MiB；仅文字理解不会发送这些字节。");
        }
        if (await sha256Hex(await asset.blob.arrayBuffer()) !== entry.asset_sha256) {
          throw new Error("参考图字节与本地哈希不一致，没有外发。");
        }
        referenceImages.push({ role: entry.role, media_type: asset.media_type,
          sha256: entry.asset_sha256, data_base64: await blobToBase64(asset.blob) });
      }
    }
    /** @type {SemanticRequestBody} */
    const body = {
      product_name: payload.product_name,
      description: payload.description,
      selling_points: payload.selling_points,
      focus: payload.focus,
      references,
      ...(vision ? { reference_images: referenceImages } : {}),
      locale: ANALYZE_LOCALE,
      platform: ANALYZE_PLATFORM,
      max_slots: ANALYZE_MAX_SLOTS,
      existing_slot_ids: [],
    };
    const declaredFields = isPlainObject(semanticProvider) && isPlainObject(semanticProvider.capabilities)
      ? semanticProvider.capabilities.analyze_fields : undefined;
    const declared = declaredFields || capabilities?.analyze_fields;
    const allowed = isStringArray(declared) && declared.length ? declared : [...DEFAULT_ANALYZE_FIELDS];
    /** 出站体只保留用途声明允许的字段；字段集缺省时回落到 DEFAULT_ANALYZE_FIELDS（含全部必需字段）。 */
    /** @type {(keyof SemanticRequestBody)[]} */
    const BODY_KEYS = ["product_name", "description", "selling_points", "focus", "references",
      "reference_images", "locale", "platform", "max_slots", "existing_slot_ids"];
    const allowedSet = new Set(allowed);
    /** @type {Partial<SemanticRequestBody>} */
    const filtered = { ...body };
    for (const key of BODY_KEYS) if (!allowedSet.has(key)) delete filtered[key];
    return /** @type {SemanticRequestBody} */ (filtered);
  }

  /** pid 必须来自动作冻结的 projectId：旧回调只写自己项目，绝不写换会话后的当前项目。 */
  /** pid 必须来自动作冻结的 projectId：旧回调只写自己项目，绝不写换会话后的当前项目。
   * @param {FactSlot} slot
   * @param {string} pid
   * @param {ActionSnapshot|null} [action]
   * @param {number|null} [expectedVersion]
   * @returns {Promise<StoredDocumentRecord>}
   */
  async function persistSlot(slot, pid, action = null, expectedVersion = null) {
    const record = await repository.documents.save(pid, {
      kind: SLOT_KIND, documentId: slot.slot_id, payload: slot,
      expectedVersion,
    });
    // 槽位缓存属于当前会话；动作已过期时只保留落库结果，不污染新项目的缓存。
    if (!action || action.alive()) {
      slots.set(slot.slot_id, { slot: record.payload, version: record.version });
    }
    return record;
  }

  /**
   * @param {string} pid
   * @param {ActionSnapshot} action
   * @returns {Promise<number>}
   */
  async function ensureCoreSlots(pid, action) {
    let created = 0;
    for (const definition of CORE_SLOT_REGISTRY) {
      if (slots.has(definition.slot_id)) continue;
      await persistSlot({
        schema_version: FACT_SLOT_SCHEMA_VERSION,
        slot_id: definition.slot_id,
        label: definition.label,
        authority: "core_fixed",
        value_type: definition.value_type,
        value: null,
        source: "system_default",
        status: "missing",
        confidence: null,
        evidence: [],
        depends_on: [],
        critical: definition.critical,
      }, pid, action);
      created += 1;
    }
    return created;
  }

  let manualFactsPreparing = false;
  /**
   * @returns {Promise<void>}
   */
  async function prepareManualFacts() {
    if (!projectId || manualFactsPreparing) return;
    const action = beginAction();
    const pid = action.projectId;
    if (!pid) return;
    manualFactsPreparing = true;
    try {
      await ensureCoreSlots(pid, action);
      if (!action.alive()) return;
      await deriveAndApplyState();
      renderSlots();
      refreshStageShell();
    } catch (error) {
      if (action.alive()) handleInternalError(error);
    } finally { manualFactsPreparing = false; }
  }

  /**
   * @param {FactSlot & {model_id?: string}} raw
   * @param {Set<string>} proposalIds
   * @returns {FactSlot|null}
   */
  function baseSlotFor(raw, proposalIds) {
    const definition = raw.authority === "core_fixed" ? coreSlotDefinition(raw.slot_id) : null;
    if (raw.authority === "core_fixed" && !definition) return null;
    const known = new Set(slots.keys());
    /** @type {FactSlot} */
    const base = {
      schema_version: FACT_SLOT_SCHEMA_VERSION,
      slot_id: raw.slot_id,
      label: definition ? definition.label : raw.label,
      authority: raw.authority,
      value_type: definition ? definition.value_type : raw.value_type,
      value: null,
      source: "system_default",
      status: "missing",
      confidence: null,
      evidence: [],
      depends_on: (raw.depends_on || []).filter((id) => proposalIds.has(id) || known.has(id)),
      critical: definition ? definition.critical : raw.critical === true,
    };
    if (base.value_type === "enum") {
      base.enum_values = Array.isArray(raw.enum_values) ? raw.enum_values.slice() : [];
    }
    if (base.authority === "user_custom") base.allow_model_proposal = true;
    return base;
  }

  /**
   * @param {SemanticProposal} proposal
   * @param {string} pid
   * @param {ActionSnapshot} action
   * @param {SemanticAnalysisSource} source
   * @returns {Promise<import("./semantic-analysis.js").AppliedProposal>}
   */
  async function applyProposal(proposal, pid, action, source) {
    const rawSlots = Array.isArray(proposal.slots) ? proposal.slots : [];
    const proposalIds = new Set(rawSlots.map((item) => item && item.slot_id).filter(Boolean));
    const problems = [];
    let applied = 0;
    for (const raw of rawSlots) {
      if (!await analysisSourceIsCurrent(source, action)) {
        problems.push("资料已变化；其余提案仅保留在原资料的分析记录中，没有继续写入当前槽位。");
        break;
      }
      try {
        const existing = slots.get(raw.slot_id);
        const base = existing ? existing.slot : baseSlotFor(raw, proposalIds);
        if (!base) {
          problems.push(raw.slot_id + "：模型把未知槽位标成系统固定槽位，已拒绝。");
          continue;
        }
        /** @type {FactSlot & {model_id?: string}} */
        const next = applySlotAction(base, {
          action: "propose", actor: "model",
          value: raw.value, confidence: raw.confidence, evidence: raw.evidence,
        });
        if (typeof raw.model_id === "string") next.model_id = raw.model_id;
        next.evidence.push({ kind: "model", ref: "product_input:" + source.document_id + "@v" + source.version,
          note: "本次提案使用的原资料快照；不是人工确认。" });
        await persistSlot(next, pid, action, existing ? existing.version : 0);
        applied += 1;
      } catch (error) {
        const slotId = raw && raw.slot_id ? raw.slot_id : "未知槽位";
        problems.push(slotId + "：" + (errorMessageOf(error, "提案被拒绝")));
      }
    }
    return { applied, problems };
  }

  /**
   * @param {SemanticAnalysisSource} source
   * @param {ActionSnapshot} action
   * @returns {Promise<boolean>}
   */
  async function analysisSourceIsCurrent(source, action) {
    if (!action.alive() || !action.projectId || source.fingerprint !== fingerprintOf(currentIntakePayload())
        || intakeConflict?.unresolved?.length) return false;
    const pid = action.projectId;
    const stored = await repository.documents.getLatest(pid, INTAKE_KIND, source.document_id);
    return action.alive() && stored !== null
      && source.fingerprint === fingerprintOf(productInputFromStored(stored.payload))
      && source.fingerprint === fingerprintOf(currentIntakePayload());
  }

  /**
   * @param {ActionSnapshot} action
   * @returns {Promise<import("./semantic-analysis.js").PreparedAnalysis>}
   */
  async function prepareAnalysis(action) {
    const authorizedPayload = currentIntakePayload();
    const fingerprint = fingerprintOf(authorizedPayload);
    const provider = capabilities?.provider;
    const headers = modelSettings.headers("semantic");
    if (!provider || provider.configured === false) throw new Error("此用途缺少有效模型或凭据；人工填写不受影响。");
    const providerId = provider.provider_id;
    const modelId = provider.model_id;
    if (typeof providerId !== "string" || typeof modelId !== "string") {
      throw new Error("此用途缺少有效模型或凭据；人工填写不受影响。");
    }
    const pid = action.projectId;
    if (!pid) throw new Error("缺少项目上下文；没有调用模型，请核对后明确发起。");
    await saveIntakeNow();
    if (!action.alive() || fingerprint !== intakeFingerprint || intakeConflict?.unresolved?.length) {
      throw new Error("资料已变化或存在未解决冲突；没有调用模型，请核对后明确发起。");
    }
    const readiness = intakeReadiness(authorizedPayload);
    if (!readiness.ready) throw new Error("商品资料还不完整：" + describeBlocking(readiness.blocking, localizeSlotTerms));
    const version = intakeVersion;
    await ensureCoreSlots(pid, action);
    return {
      source: { document_id: INTAKE_DOCUMENT_ID, version, fingerprint, payload: authorizedPayload },
      provider: { provider_id: providerId, model_id: modelId,
        credential_source: provider.credential_source || "none" },
      body: await buildAnalyzeBody(pid, provider, authorizedPayload),
      headers,
    };
  }

  /**
   * @param {{allowNewAfterUnknown?: boolean}} [args]
   * @returns {Promise<void>}
   */
  async function runAnalyze({ allowNewAfterUnknown = false } = {}) {
    const action = beginAction();
    analyzeProblems = [];
    analyzeRequiresConfirmation = false;
    clearError(elements.analyzeError);
    const pending = semanticAnalysis.run({ allowNewAfterUnknown });
    renderAnalyze();
    try {
      const outcome = await pending;
      if (!action.alive()) return;
      if (outcome.kind === "requires_confirmation") {
        analyzeRequiresConfirmation = true;
        showError(elements.analyzeError, "原分析结果仍未知，可能已经计费。不会自动重提；只有明确选择“另发新分析”才会再次发送，可能重复计费。");
      } else if (outcome.kind === "not_sent" || outcome.kind === "apply_failed") {
        showError(elements.analyzeError, outcome.message);
      } else if (outcome.kind === "failed" || outcome.kind === "unknown") {
        analyzeRequiresConfirmation = outcome.kind === "unknown";
        showError(elements.analyzeError, describeAnalyzeFailure(outcome.error, outcome.kind === "unknown"));
      } else if (outcome.kind === "stale") {
        showError(elements.analyzeError, "提案已保留在原资料 v" + outcome.record.source.version
          + " 的分析记录中；当前资料已变化，没有写入当前事实。");
      } else if (outcome.kind === "applied") {
        const { proposal, applied, record } = outcome;
        analyzeProblems = applied.problems;
        lastAnalyze = {
          at: new Date(record.updated_at).toLocaleString("zh-CN", { hour12: false }),
          provider: proposal.meta.provider_id, model: proposal.meta.model_id,
          slots: proposal.slots.length, applied: applied.applied, summary: proposal.summary,
          sourceVersion: record.source.version, referenceImagesSent: record.reference_images_sent,
        };
        if (proposal.questions.length) analyzeProblems.push("模型提出的问题：" + proposal.questions.join(" / "));
      }
    } catch (error) {
      if (action.alive()) handleInternalError(error);
    } finally {
      if (action.alive()) {
        try { await deriveAndApplyState(); }
        catch (error) { handleInternalError(error); }
        renderAll();
      }
    }
  }

  /**
   * @returns {Promise<void>}
   */
  async function loadCapabilities() {
    capabilitiesError = null;
    capabilities = await modelSettings.refresh();
    if (!capabilities) capabilitiesError = "有效模型配置不可用；本地资料可继续编辑，请打开模型设置。";
  }
  /* ---------------------------------------------------------- 商品理解 */

  /**
   * 分析失败的可见摘要：人话在前，分类与重试策略是网关信封在前端的投影（§9.10），
   * 与落库记录同源，不在渲染层重算。结果未知时追加「可能已计费、不会自动重试」，
   * 不把未知说成失败，也不让用户以为系统会自己重发。
   */
  /**
   * @param {unknown} error
   * @param {unknown} unknown
   * @returns {string}
   */
  function describeAnalyzeFailure(error, unknown) {
    const parts = [String(errorMessageOf(error, "分析失败"))];
    // 网关信封在前端的投影：只读已知标量字段，形状由网关契约给出（§9.10）。
    const info = isPlainObject(error) ? error : {};
    parts.push("分类：" + String(info.family || "internal")
      + " / " + String(info.code || "INTERNAL_ERROR"));
    if (info.retry_policy) parts.push("重试策略：" + String(info.retry_policy));
    if (unknown) {
      parts.push("结果未知：这次请求可能已经产生结果。系统不会自动重试，请确认后再手动点击“重新分析”。");
    }
    return parts.join(" ");
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
    const labels = slotEntries()
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
   * @returns {void}
   */
  function renderSlots() {
    elements.slotList.replaceChildren();
    const entries = slotEntries();
    const critical = entries.filter((entry) => entry.slot.critical === true);
    const confirmedCritical = critical.filter((entry) => entry.slot.status === "confirmed");
    const open = entries.filter(
      (entry) => entry.slot.status !== "confirmed" && entry.slot.status !== "superseded");

    elements.slotsProgress.textContent = entries.length
      ? "必须确认的槽位 " + confirmedCritical.length + " / " + critical.length + " 已确认 · 待处理 "
        + open.length + " 项 · 共 " + entries.length + " 项"
        + (understandingBlocking.length
          ? " · 还缺：" + describeBlocking(understandingBlocking, localizeSlotTerms) : "")
      : "还没有槽位。";
    elements.slotsToggle.textContent = showAll ? "只看待处理项" : "显示全部事实";
    elements.slotsToggle.setAttribute("aria-expanded", showAll ? "true" : "false");
    elements.slotsEmpty.hidden = entries.length > 0;

    const list = (showAll ? entries : open).slice();
    list.sort((left, right) => {
      const byRank = reviewRankOf(left) - reviewRankOf(right);
      if (byRank !== 0) return byRank;
      return left.slot.slot_id.localeCompare(right.slot.slot_id);
    });
    for (const entry of list) elements.slotList.append(slotRow(entry));
  }

  /** 某个 slot_id 的中文名（找不到就退回原样）；依赖与来源引用用它去掉工程感。 */
  /**
   * @param {string} slotId
   * @returns {string}
   */
  function slotLabelOfId(slotId) {
    for (const entry of slotEntries()) {
      if (entry.slot && entry.slot.slot_id === slotId) return entry.slot.label || slotId;
    }
    return slotId;
  }

  /** 主行只放人话：来源档 + 置信（「必须确认」已经是徽标，不再重复一次）。 */
  /**
   * @param {ValidatedSlotEntry} entry
   * @returns {string}
   */
  function slotMetaText(entry) {
    const slot = entry.slot;
    const parts = [/** @type {Record<string, string>} */ (AUTHORITY_TEXT)[slot.authority] || slot.authority];
    if (slot.confidence !== null && slot.confidence !== undefined) {
      parts.push("置信 " + Number(slot.confidence).toFixed(2));
    }
    return parts.join(" · ");
  }

  /**
   * 事实卡的工程标识（V2.6.16）：slot_id、版本、依赖、证据来源引用（字段名 / 资产哈希 /
   * 模型 id）一律进折叠的技术详情，主行只留人能判断的信息；追溯链不减，只是换了位置。
   */
  /**
   * @param {ValidatedSlotEntry} entry
   * @returns {string[]}
   */
  function slotTechLines(entry) {
    const slot = entry.slot;
    const lines = ["标识 " + slot.slot_id, "版本 v" + entry.version];
    if (slot.depends_on && slot.depends_on.length) {
      lines.push("依赖 " + slot.depends_on.map((id) => slotLabelOfId(id)).join("、"));
    }
    const refs = (Array.isArray(slot.evidence) ? slot.evidence : [])
      .map((item) => (item && item.ref ? String(item.ref) : ""))
      .filter((ref) => ref !== "");
    if (refs.length) lines.push("来源引用 " + refs.join("、"));
    return lines;
  }

  /**
   * @param {ValidatedSlotEntry} entry
   * @returns {HTMLLIElement}
   */
  function slotRow(entry) {
    const slot = entry.slot;
    const status = slot.status;
    const row = createElement("li", { className: "slot-row", attrs: { "data-status": status } });
    row.dataset.slotId = slot.slot_id;
    // 验证用：必须确认是「推进阶段门禁」的判据之一，断言要能区分它与普通待补项。
    row.dataset.critical = slot.critical === true ? "1" : "0";

    const head = createElement("div", { className: "slot-head" });
    head.append(createElement("span", {
      className: "badge is-" + status, text: /** @type {Record<string, string>} */ (STATUS_TEXT)[status] || status,
    }));
    head.append(createElement("span", { className: "name", text: slot.label }));
    if (slot.critical === true) {
      head.append(createElement("span", { className: "badge is-critical", text: "必须确认" }));
    }
    head.append(createElement("span", { className: "meta", text: slotMetaText(entry) }));
    row.append(head);

    const valueText = formatValue(slot);
    if (valueText) {
      row.append(createElement("div", { className: "slot-value", text: valueText }));
    } else {
      const hint = status === "conflict"
        ? "模型提案与已确认值不一致；请给出裁决值。"
        : status === "unknown" ? "已标记为未知；需要时再补值确认。"
          : status === "superseded" ? "已移除（历史版本保留）。" : "还没有值。";
      row.append(createElement("div", { className: "slot-value is-empty", text: hint }));
    }

    if (Array.isArray(slot.evidence) && slot.evidence.length) {
      const list = createElement("ul", { className: "evidence" });
      for (const item of slot.evidence) {
        const label = /** @type {Record<string, string>} */ (EVIDENCE_TEXT)[item.kind] || item.kind;
        list.append(createElement("li", {
          className: "meta",
          text: item.note ? label + "：" + item.note : label,
        }));
      }
      row.append(list);
    }

    const mode = interaction.mode;
    if (interaction.slotId === slot.slot_id && mode) row.append(slotEditor(entry, mode));
    row.append(slotActions(entry));
    const tech = techDetails(slotTechLines(entry));
    if (tech) row.append(tech);
    return row;
  }

  /**
   * @param {ValidatedSlotEntry} entry
   * @returns {HTMLDivElement}
   */
  function slotActions(entry) {
    const slot = entry.slot;
    const actions = createElement("div", { className: "slot-actions" });
    const editing = interaction.slotId === slot.slot_id && interaction.mode === "edit";

    if (canConfirmSlot(slot, "user")) {
      const direct = slot.status === "proposed";
      const confirm = createElement("button", {
        className: "primary", text: direct ? "确认" : "填值并确认", attrs: { type: "button" },
      });
      confirm.addEventListener("click", () => {
        if (direct) {
          handleSlotAction(entry, { action: "confirm", actor: "user" });
        } else {
          interaction = { slotId: slot.slot_id, mode: "confirm" };
          renderSlots();
        }
      });
      actions.append(confirm);
    }

    if (canEditValue(slot, "user")) {
      const edit = createElement("button", {
        text: editing ? "取消修改" : "修改", attrs: { type: "button" },
      });
      edit.addEventListener("click", () => {
        interaction = editing
          ? { slotId: null, mode: null }
          : { slotId: slot.slot_id, mode: "edit" };
        renderSlots();
      });
      actions.append(edit);
    }

    if (slot.status !== "unknown" && slot.status !== "superseded") {
      const unknown = createElement("button", { text: "标记未知", attrs: { type: "button" } });
      unknown.addEventListener("click", () => {
        handleSlotAction(entry, { action: "mark_unknown", actor: "user" });
      });
      actions.append(unknown);
    }

    if (canDeleteSlot(slot, { dependencyCount: dependencyCountOf(slot.slot_id) })) {
      const remove = createElement("button", {
        className: "danger", text: "删除（保留历史）", attrs: { type: "button" },
      });
      remove.addEventListener("click", () => {
        handleSlotAction(entry, { action: "supersede", actor: "user" });
      });
      actions.append(remove);
    }
    return actions;
  }

  /**
   * @param {unknown} initial
   * @returns {HTMLDivElement}
   */
  function dimensionEditor(initial) {
    const list = createElement("div", { className: "dimension-editor", attrs: { id: "slot-editor-value" } });
    const rows = createElement("div", { className: "dimension-rows" });
    const add = createElement("button", { text: "添加测量", attrs: { type: "button" } });
    /** @type {Record<string, string>} */
    const axisLabels = { height: "高度", width: "宽度", length: "长度", depth: "深度",
      diameter: "直径", weight: "重量", volume: "容量", thickness: "厚度" };
    /**
     * @param {import("./domain/type-contracts.js").DimensionMeasurement|Record<string, unknown>} [measurement]
     * @returns {void}
     */
    function appendRow(measurement = {}) {
      if (rows.children.length >= MAX_DIMENSIONS) return;
      const row = createElement("fieldset", { className: "dimension-row" });
      row.append(createElement("legend", { text: "已确认的测量（不猜数字）" }));
      for (const [key, label] of [["object", "测量对象"], ["axis", "轴向"],
        ["value", "数值"], ["unit", "单位"], ["source_basis", "来源依据"]]) {
        const wrapper = createElement("label", { text: label });
        const control = key === "axis" || key === "unit"
          ? createElement("select")
          : createElement("input", { attrs: { type: key === "value" ? "number" : "text",
            step: key === "value" ? "any" : null, min: key === "value" ? "0" : null } });
        control.dataset.dimensionField = key;
        if (key === "axis" || key === "unit") {
          control.append(createElement("option", { text: "请选择", attrs: { value: "" } }));
          for (const value of key === "axis" ? DIMENSION_AXES : DIMENSION_UNITS) {
            control.append(createElement("option", { text: axisLabels[value] || value, attrs: { value } }));
          }
        }
        const fields = /** @type {Record<string, unknown>} */ (measurement);
        control.value = fields[key] == null ? "" : String(fields[key]);
        wrapper.append(control);
        row.append(wrapper);
      }
      const remove = createElement("button", { text: "删除这条测量", attrs: { type: "button" } });
      remove.addEventListener("click", () => { row.remove(); add.disabled = false; });
      row.append(remove);
      rows.append(row);
      add.disabled = rows.children.length >= MAX_DIMENSIONS;
    }
    for (const measurement of Array.isArray(initial) && initial.length ? initial : [{}]) appendRow(measurement);
    add.addEventListener("click", () => appendRow());
    list.append(rows, add);
    return list;
  }

  /**
   * @param {FactSlot} slot
   * @returns {unknown}
   */
  function suggestedValue(slot) {
    for (const item of slot.evidence || []) {
      if (item && item.ref === "model_proposal" && typeof item.note === "string") {
        try {
          return JSON.parse(item.note);
        } catch (error) {
          return null;
        }
      }
    }
    return null;
  }

  /**
   * @param {ValidatedSlotEntry} entry
   * @param {string} mode
   * @returns {HTMLDivElement}
   */
  function slotEditor(entry, mode) {
    const slot = entry.slot;
    const editor = createElement("div", { className: "slot-editor" });
    const field = createElement("div", { className: "field" });
    field.append(createElement("label", {
      text: mode === "confirm" ? "给出裁决值后确认" : "修改后的值",
      attrs: { for: "slot-editor-value" },
    }));

    const suggestion = suggestedValue(slot);
    let node;
    if (slot.value_type === "text_list") {
      const initial = Array.isArray(slot.value) ? slot.value
        : (Array.isArray(suggestion) ? suggestion : []);
      node = createElement("textarea", { attrs: { id: "slot-editor-value", rows: 3 } });
      node.value = initial.join("\n");
    } else if (slot.value_type === "dimension_list") {
      node = dimensionEditor(Array.isArray(slot.value) ? slot.value : suggestion);
    } else if (slot.value_type === "boolean") {
      node = createElement("select", { attrs: { id: "slot-editor-value" } });
      node.append(createElement("option", { text: "是", attrs: { value: "true" } }));
      node.append(createElement("option", { text: "否", attrs: { value: "false" } }));
      node.value = String(slot.value === true || (slot.value === null && suggestion === true));
    } else if (slot.value_type === "enum") {
      node = createElement("select", { attrs: { id: "slot-editor-value" } });
      for (const item of slot.enum_values || []) {
        node.append(createElement("option", { text: item, attrs: { value: item } }));
      }
      node.value = typeof slot.value === "string" ? slot.value
        : (typeof suggestion === "string" ? suggestion : "");
    } else {
      const initial = slot.value !== null && slot.value !== undefined ? String(slot.value)
        : (suggestion !== null && suggestion !== undefined ? String(suggestion) : "");
      node = createElement("input", {
        attrs: {
          id: "slot-editor-value",
          type: slot.value_type === "number" ? "number" : "text",
          step: slot.value_type === "number" ? "any" : null,
        },
      });
      node.value = initial;
    }
    node.dataset.role = "value";
    field.append(node);
    editor.append(field);

    const toolbar = createElement("div", { className: "toolbar" });
    const submit = createElement("button", {
      className: "primary", text: mode === "confirm" ? "确认" : "保存", attrs: { type: "button" },
    });
    submit.addEventListener("click", () => {
      let value;
      try {
        value = readEditorValue(slot, node);
      } catch (error) {
        showError(elements.slotsError, errorMessageOf(error, "值不合法。"));
        return;
      }
      clearError(elements.slotsError);
      handleSlotAction(entry, mode === "confirm"
        ? { action: "confirm", actor: "user", value, source: "user_input" }
        : { action: "edit", actor: "user", value, source: "user_input" });
    });
    const cancel = createElement("button", { text: "取消", attrs: { type: "button" } });
    cancel.addEventListener("click", () => {
      interaction = { slotId: null, mode: null };
      renderSlots();
    });
    toolbar.append(submit, cancel);
    editor.append(toolbar);
    return editor;
  }

  /**
   * @param {FactSlot} slot
   * @param {HTMLElement} node
   * @returns {import("./domain/type-contracts.js").FactSlotValue}
   */
  function readEditorValue(slot, node) {
    if (slot.value_type === "dimension_list") {
      /** @type {import("./domain/type-contracts.js").DimensionMeasurement[]} */
      const values = Array.from(node.querySelectorAll(".dimension-row"), (row) => {
        /** @type {Record<string, string|number>} */
        const fields = {};
        for (const control of /** @type {NodeListOf<HTMLInputElement|HTMLSelectElement>} */ (row.querySelectorAll("[data-dimension-field]"))) {
          const key = control.dataset.dimensionField;
          if (!key) continue;
          fields[key] = key === "value" ? Number(control.value) : control.value.trim();
        }
        // 轴向/单位选项来自 DIMENSION_AXES / DIMENSION_UNITS 词表；checkFactSlot 再校验。
        return {
          object: String(fields.object || ""),
          axis: /** @type {import("./domain/type-contracts.js").DimensionAxis} */ (String(fields.axis || "")),
          value: Number(fields.value),
          unit: /** @type {import("./domain/type-contracts.js").DimensionUnit} */ (String(fields.unit || "")),
          source_basis: String(fields.source_basis || ""),
        };
      });
      if (!values.length) throw new Error("至少填写一条已确认的测量。");
      return values;
    }
    const raw = node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement
      || node instanceof HTMLSelectElement ? node.value : "";
    if (slot.value_type === "text_list") {
      const items = splitLines(raw);
      if (!items.length) throw new Error("文本列表至少要有一条。");
      return items;
    }
    if (slot.value_type === "number") {
      const text = String(raw).trim();
      if (!text) throw new Error("请填写数字。");
      const value = Number(text);
      if (!Number.isFinite(value)) throw new Error("请填写合法的数字。");
      return value;
    }
    if (slot.value_type === "boolean") return raw === "true";
    const text = String(raw).trim();
    if (!text) throw new Error("值不能为空。");
    return text;
  }

  /**
   * @param {ValidatedSlotEntry} entry
   * @param {import("./domain/type-contracts.js").SlotActionSpec} spec
   * @returns {Promise<void>}
   */
  async function handleSlotAction(entry, spec) {
    const action = beginAction();
    const pid = action.projectId;
    if (!pid) return;
    clearError(elements.slotsError);
    try {
      const next = applySlotAction(entry.slot, spec);
      await persistSlot(next, pid, action);
      if (!action.alive()) return;
      interaction = { slotId: null, mode: null };
      await deriveAndApplyState();
      renderAll();
    } catch (error) {
      if (action.alive()) {
        showError(elements.slotsError, errorMessageOf(error, "这个动作没有完成。"));
      }
    }
  }

  /**
   * @returns {Promise<void>}
   */
  async function handleAddSlot() {
    clearError(elements.slotsError);
    elements.slotAddStatus.textContent = "";
    const slotId = elements.slotAddId.value.trim().toLowerCase();
    const label = elements.slotAddLabel.value.trim();
    const rawType = elements.slotAddType.value;
    const rawValue = elements.slotAddValue.value;
    // 值类型选项来自 index.html 的固定 select；词表校验后再按 SlotValueType 使用。
    if (!/** @type {readonly string[]} */ (SLOT_VALUE_TYPES).includes(rawType)) {
      showError(elements.slotsError, "值类型不在支持列表内。");
      return;
    }
    /** @type {import("./domain/type-contracts.js").SlotValueType} */
    const valueType = /** @type {import("./domain/type-contracts.js").SlotValueType} */ (rawType);
    /** @type {FactSlotValue} */
    let value;
    try {
      if (valueType === "text_list") {
        value = splitLines(rawValue);
        if (!value.length) throw new Error("文本列表至少要有一条。");
      } else if (valueType === "number") {
        value = Number(String(rawValue).trim());
        if (!Number.isFinite(value)) throw new Error("请填写合法的数字。");
      } else if (valueType === "boolean") {
        const text = String(rawValue).trim().toLowerCase();
        value = text === "是" || text === "true" || text === "1";
      } else {
        value = String(rawValue).trim();
        if (!value) throw new Error("值不能为空。");
      }
    } catch (error) {
      showError(elements.slotsError, errorMessageOf(error, "值不合法。"));
      return;
    }
    /** @type {FactSlot} */
    const candidate = {
      schema_version: FACT_SLOT_SCHEMA_VERSION,
      slot_id: slotId,
      label,
      authority: "user_custom",
      value_type: valueType,
      value,
      source: "user_input",
      status: "confirmed",
      confidence: null,
      evidence: [{ kind: "user", ref: "user_input" }],
      depends_on: [],
      critical: false,
      allow_model_proposal: elements.slotAddAllowModel.checked,
    };
    const problems = checkFactSlot(candidate);
    if (problems.length) {
      showError(elements.slotsError, problems.map((item) => item.message).join("；"));
      return;
    }
    if (!canAddSlot(candidate, "user", { existingSlots: slotEntries().map((item) => item.slot) })) {
      showError(elements.slotsError, "槽位标识已存在，或这个槽位不允许新增。");
      return;
    }
    const action = beginAction();
    const pid = action.projectId;
    if (!pid) return;
    try {
      await persistSlot(candidate, pid, action);
      if (!action.alive()) return;
      elements.slotAddId.value = "";
      elements.slotAddLabel.value = "";
      elements.slotAddValue.value = "";
      elements.slotAddAllowModel.checked = false;
      elements.slotAddStatus.textContent = "已新增 " + candidate.slot_id;
      await deriveAndApplyState();
      renderAll();
    } catch (error) {
      if (action.alive()) {
        showError(elements.slotsError, errorMessageOf(error, "新增槽位失败。"));
      }
    }
  }
  /* ------------------------------------------------------ 状态派生与装载 */

  /* ------------------------------------------------------------ 套图规划 */

  /**
   * @returns {import("./domain/type-contracts.js").EvalContext}
   */
  function suiteContext() {
    return {
      facts: [...slots.values()].map((entry) => ({
        slot_id: entry.slot.slot_id,
        status: entry.slot.status,
        value: entry.slot.value,
      })),
      assets: intake.references.map((item) => ({ role: item.role, sha256: item.asset_sha256 })),
    };
  }

  /**
   * 套图依据缺口的本地连接文本（与 domain/confirm.js blockingText 同形状输入，
   * 但此处只用于模板提示/行内说明，不做门禁判定；缺口无文案时按空串连接，由调用文案兜底）。
   * @param {import("./domain/type-contracts.js").DependencyBlocking[]|null|undefined} blocking
   * @returns {string}
   */
  function suiteBlockingText(blocking) {
    return (blocking || []).map((item) => item.reason || "").join("；");
  }

  /**
   * @param {import("./domain/type-contracts.js").PlanRecommendation} recommendation
   * @returns {void}
   */
  function updateTemplateHint(recommendation) {
    const instance = recommendation.instances
      .find((item) => item.template_id === elements.suiteTemplate.value);
    if (!instance) {
      elements.suiteTemplateHint.textContent = "";
      return;
    }
    elements.suiteTemplateHint.textContent = instance.satisfied
      ? "该模板依据已满足。"
      : "该模板暂时缺依据：" + suiteBlockingText(instance.blocking);
  }

  /**
   * @returns {void}
   */
  function renderSuite() {
    elements.suiteLocked.hidden = true;
    elements.suiteEditor.hidden = false;
    const recommendation = recommendPlan(suiteContext());
    if (elements.suiteTemplate.options.length !== SHOT_TEMPLATES.length) {
      elements.suiteTemplate.innerHTML = "";
      for (const template of SHOT_TEMPLATES) {
        const option = document.createElement("option");
        option.value = template.template_id;
        option.textContent = template.label;
        elements.suiteTemplate.append(option);
      }
    }
    updateTemplateHint(recommendation);
    const plan = suitePlan;
    const summary = plan ? /** @type {SuitePlanSummary} */ (suitePlanSummary(plan, suiteContext())) : null;
    elements.suiteStatus.textContent = summary
      ? "共 " + summary.total + " 张，依据已满足 " + summary.satisfiable + " 张"
        + (summary.blocked ? "；" + summary.blocked + " 张缺依据" : "")
      : "还没有套图方案。";
    elements.suiteEmpty.hidden = Boolean(summary);
    elements.shotList.innerHTML = "";
    if (!summary || !plan) return;
    summary.shots.forEach((item, index) => {
      // 已保存计划恒有 shot_id（validateSuitePlan 要求字符串）；null 仅存在于未落库草稿。
      const shotId = item.shot_id;
      if (typeof shotId !== "string") return;
      const row = createElement("li", {
        className: "shot-row",
        attrs: { "data-shot-id": shotId, "data-blocked": String(!item.satisfied) },
      });
      const head = createElement("div", { className: "shot-head" });
      head.append(createElement("span", { className: "badge", text: String(index + 1) }));
      head.append(createElement("span", { className: "name", text: item.label }));
      const roleText = item.role_label || item.role_id;
      if (!item.custom && roleText && !String(item.label).startsWith(roleText)) {
        head.append(createElement("span", { className: "meta", text: roleText }));
      }
      head.append(createElement("span", {
        className: item.required ? "badge is-critical" : "badge",
        text: item.required ? "必需" : (item.custom ? "自定义" : "可选"),
      }));
      row.append(head);
      row.append(createElement("p", {
        className: "meta",
        text: item.satisfied ? "依据已满足。" : "暂时缺依据：" + suiteBlockingText(item.blocking),
      }));
      const planned = plan.shots.find(shot => shot.shot_id === shotId);
      if (!planned) return;
      const readiness = shotReadiness(planned, suiteContext());
      const fixes = createElement("div", { className: "shot-fixes" });
      for (const slotId of readiness.missing_fact_ids) {
        const definition = coreSlotDefinition(slotId);
        const fix = createElement("button", {
          text: "填写／确认：" + (slots.get(slotId)?.slot.label || definition?.label || slotId),
          attrs: { type: "button" },
        });
        fix.addEventListener("click", () => {
          showAll = true;
          interaction = { slotId, mode: "edit" };
          if (!definition && !slots.has(slotId)) {
            elements.slotAddId.value = slotId;
            elements.slotAddLabel.value = slotId;
          }
          stageShell.select("understand");
          renderSlots();
        });
        fixes.append(fix);
      }
      for (const role of readiness.missing_asset_roles) {
        const fix = createElement("button", {
          text: "补参考图：" + (/** @type {Record<string, string>} */ (ROLE_TEXT)[role] || role), attrs: { type: "button" },
        });
        fix.addEventListener("click", () => stageShell.select("intake"));
        fixes.append(fix);
      }
      if (fixes.children.length) row.append(fixes);
      const bindings = createElement("details", { className: "shot-bindings" });
      bindings.append(createElement("summary", { text: "绑定这张图使用的已确认事实" }));
      /** @type {HTMLInputElement[]} */
      const checks = [];
      for (const entry of slotEntries().filter(entry => entry.slot.status === "confirmed")) {
        const label = createElement("label", { className: "choice" });
        const check = createElement("input", { attrs: { type: "checkbox", value: entry.slot.slot_id } });
        check.checked = planned.fact_slot_ids.includes(entry.slot.slot_id);
        label.append(check, document.createTextNode(entry.slot.label));
        bindings.append(label);
        checks.push(check);
      }
      if (!checks.length) {
        bindings.append(createElement("p", { className: "meta", text: "先确认需要使用的事实；不从未确认提案猜文案或尺寸。" }));
      }
      const applyBindings = createElement("button", { text: "保存本图事实绑定", attrs: { type: "button" } });
      applyBindings.disabled = !checks.length;
      applyBindings.addEventListener("click", () => {
        const ids = checks.filter(check => check.checked).map(check => check.value);
        void handleSuiteOp(() => setShotFactBindings(plan, shotId, ids));
      });
      bindings.append(applyBindings);
      row.append(bindings);
      const actions = createElement("div", { className: "shot-actions" });
      const up = createElement("button", { text: "上移", attrs: { type: "button" } });
      up.disabled = index === 0;
      up.addEventListener("click", () => {
        handleSuiteOp(() => moveShot(plan, shotId, -1));
      });
      const down = createElement("button", { text: "下移", attrs: { type: "button" } });
      down.disabled = index === summary.shots.length - 1;
      down.addEventListener("click", () => {
        handleSuiteOp(() => moveShot(plan, shotId, 1));
      });
      const copy = createElement("button", { text: "复制", attrs: { type: "button" } });
      copy.addEventListener("click", () => {
        handleSuiteOp(() => copyShot(plan, shotId));
      });
      const remove = createElement("button", {
        text: "删除", className: "danger", attrs: { type: "button" },
      });
      remove.addEventListener("click", () => {
        handleSuiteOp(() => removeShot(plan, shotId));
      });
      actions.append(up, down, copy, remove);
      row.append(actions);
      elements.shotList.append(row);
    });
  }

  /**
   * @param {() => {plan: import("./domain/suite.js").PlanRecord, [key: string]: unknown}} run
   * @returns {Promise<boolean>}
   */
  async function handleSuiteOp(run) {
    if (!projectId) return false;
    const action = beginAction();
    const pid = action.projectId;
    if (!pid) return false;
    clearError(elements.suiteError);
    try {
      const result = run();
      // 领域纯函数返回运行时冻结计划（PlanRecord）；与持久化契约同形，收窄到声明面的 SuitePlan。
      const nextPlan = /** @type {SuitePlan} */ (result.plan);
      const problems = validateSuitePlan(nextPlan);
      if (problems.length > 0) throw new Error(problems[0].message);
      const saved = await repository.documents.save(pid, {
        kind: SUITE_KIND,
        documentId: SUITE_PLAN_DOCUMENT_ID,
        payload: nextPlan,
        expectedVersion: suiteVersion,
      });
      if (!action.alive()) return false;
      suitePlan = nextPlan;
      suiteVersion = saved && typeof saved.version === "number" ? saved.version : suiteVersion + 1;
      renderSuite();
      renderStyleSpec();
      renderShotSpecs();
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deriveAndApplyState();
      return true;
    } catch (error) {
      if (action.alive()) {
        showError(elements.suiteError, errorMessageOf(error, "操作没有完成，请重试。"));
      }
      return false;
    }
  }

  /**
   * @returns {Promise<void>}
   */
  async function handleSuiteAddCustom() {
    const label = elements.suiteCustomLabel.value.trim();
    const intent = elements.suiteCustomIntent.value.trim();
    const plan = suitePlan;
    if (!plan) return;
    const ok = await handleSuiteOp(() => addCustomShotToPlan(plan, { label, intent }));
    if (ok) {
      elements.suiteCustomLabel.value = "";
      elements.suiteCustomIntent.value = "";
      elements.suiteCustomStatus.textContent = "已添加。";
    }
  }

  /* -------------------------------------------------- 风格与单图规格 */

  /**
   * @returns {StyleSpec}
   */
  function styleFormPayload() {
    return {
      ...emptyStyleSpec(),
      background: elements.styleBackground.value.trim(),
      lighting: elements.styleLighting.value.trim(),
      color_tone: elements.styleColorTone.value.trim(),
      composition: elements.styleComposition.value.trim(),
      avoid: splitLines(elements.styleAvoid.value),
    };
  }

  /**
   * @param {StyleSpec} spec
   * @returns {void}
   */
  function fillStyleForm(spec) {
    /** @type {Array<[HTMLInputElement|HTMLTextAreaElement, string]>} */
    const pairs = [
      [elements.styleBackground, spec.background || ""],
      [elements.styleLighting, spec.lighting || ""],
      [elements.styleColorTone, spec.color_tone || ""],
      [elements.styleComposition, spec.composition || ""],
      [elements.styleAvoid, Array.isArray(spec.avoid) ? spec.avoid.join("\n") : ""],
    ];
    for (const [node, value] of pairs) {
      if (document.activeElement !== node) node.value = value;
    }
  }

  /**
   * @returns {void}
   */
  function renderStyleSpec() {
    const plan = suitePlan;
    const ready = Boolean(plan);
    elements.specsLocked.hidden = ready;
    elements.specsEditor.hidden = !ready;
    if (!plan) return;
    fillStyleForm(styleSpec);
    elements.styleVersion.textContent = styleVersion > 0
      ? "版本 v" + styleVersion
      : "尚未保存";
    elements.styleRestore.disabled = styleVersion <= 1;
    const projection = specChangeProjection("style_changed", {
      shotCount: plan.shots.length,
    });
    elements.styleEffect.textContent = "保存后影响：" + projection.affects_text
      + "；失效：" + projection.invalidates_text + "；保留：" + projection.preserves_text + "。";
  }

  /**
   * @param {string|null} shotId
   * @returns {{spec: ShotSpec, version: number}|null}
   */
  function shotSpecEntry(shotId) {
    if (!shotId) return null;
    return shotSpecs.get(shotId) || null;
  }

  /**
   * @returns {void}
   */
  function renderShotSpecs() {
    const plan = suitePlan;
    const ready = Boolean(plan);
    elements.specsLocked.hidden = ready;
    elements.specsEditor.hidden = !ready;
    elements.shotSpecList.innerHTML = "";
    if (!plan) return;
    elements.shotSpecsEmpty.hidden = plan.shots.length > 0;
    /** @type {Record<string, {spec?: ShotSpec|null, version: number}|null|undefined>} */
    const byId = {};
    for (const [shotId, entry] of shotSpecs.entries()) byId[shotId] = entry;
    const digest = suiteSpecDigest(plan, { styleSpec, shotSpecsById: byId });
    digest.shots.forEach((item, index) => {
      // 已保存计划恒有 shot_id；null 仅存在于未落库草稿，跳过即可。
      const shotId = item.shot_id;
      const shot = plan.shots[index];
      if (typeof shotId !== "string" || !shot) return;
      const entry = shotSpecEntry(shotId);
      const spec = entry ? entry.spec : emptyShotSpecFromShot(shot);
      const card = createElement("div", {
        className: "shot-spec", attrs: { "data-shot-id": shotId },
      });
      const head = createElement("div", { className: "shot-spec-head" });
      head.append(createElement("span", {
        className: "name", text: (index + 1) + ". " + item.label,
      }));
      head.append(createElement("span", {
        className: "meta", text: entry ? "规格 v" + entry.version : "默认（未保存）",
      }));
      card.append(head);

      const purposeField = createElement("div", { className: "field" });
      const purposeId = "spec-purpose-" + shotId;
      const purposeLabel = createElement("label", { text: "目的" });
      purposeLabel.setAttribute("for", purposeId);
      const purposeInput = createElement("input", { attrs: { id: purposeId, maxlength: "200" } });
      purposeInput.value = spec.purpose;
      purposeField.append(purposeLabel, purposeInput);
      card.append(purposeField);

      const keepField = createElement("div", { className: "field" });
      const keepId = "spec-keep-" + shotId;
      const keepLabel = createElement("label", { text: "必须保持（一行一条）" });
      keepLabel.setAttribute("for", keepId);
      const keepArea = createElement("textarea", { attrs: { id: keepId, rows: "2" } });
      keepArea.value = spec.keep.join("\n");
      keepField.append(keepLabel, keepArea);
      card.append(keepField);

      const changeField = createElement("div", { className: "field" });
      const changeId = "spec-change-" + shotId;
      const changeLabel = createElement("label", { text: "允许变化（一行一条）" });
      changeLabel.setAttribute("for", changeId);
      const changeArea = createElement("textarea", { attrs: { id: changeId, rows: "2" } });
      changeArea.value = spec.change_allowed.join("\n");
      changeField.append(changeLabel, changeArea);
      card.append(changeField);

      const toolbar = createElement("div", { className: "toolbar" });
      const saveButton = createElement("button", { text: "保存", attrs: { type: "button" } });
      saveButton.addEventListener("click", () => {
        handleSaveShotSpec(shotId, {
          purpose: purposeInput.value.trim(),
          keep: splitLines(keepArea.value),
          change_allowed: splitLines(changeArea.value),
        });
      });
      const restoreButton = createElement("button", {
        text: "恢复上一版本", attrs: { type: "button" },
      });
      restoreButton.disabled = !entry || entry.version <= 1;
      restoreButton.addEventListener("click", () => { handleRestoreShotSpec(shotId); });
      toolbar.append(saveButton, restoreButton);
      card.append(toolbar);

      const checklist = createElement("details", { className: "slot-detail" });
      checklist.append(createElement("summary", { text: "审核清单" }));
      const list = createElement("ul", { className: "checklist" });
      for (const section of item.checklist.sections) {
        if (section.items.length === 0) continue;
        const li = createElement("li");
        li.append(createElement("strong", { text: section.label + "：" }));
        li.append(createElement("span", { className: "meta", text: section.items.join("；") }));
        list.append(li);
      }
      checklist.append(list);
      card.append(checklist);
      elements.shotSpecList.append(card);
    });
  }

  /**
   * @returns {Promise<void>}
   */
  async function handleSaveStyle() {
    if (!projectId || !suitePlan) return;
    const action = beginAction();
    const pid = action.projectId;
    if (!pid) return;
    clearError(elements.styleError);
    elements.styleStatus.hidden = true;
    try {
      const next = styleFormPayload();
      assertStyleSpec(next);
      const diffs = styleSpecDiff(styleSpec, next);
      const record = await repository.documents.save(pid, {
        kind: STYLE_KIND,
        documentId: STYLE_SPEC_DOCUMENT_ID,
        payload: next,
        expectedVersion: styleVersion > 0 ? styleVersion : null,
      });
      if (!action.alive()) return;
      styleSpec = next;
      styleVersion = record.version;
      renderStyleSpec();
      renderShotSpecs();
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deriveAndApplyState();
      if (!action.alive()) return;
      elements.styleStatus.hidden = false;
      elements.styleStatus.textContent = "已保存 v" + record.version
        + (diffs.length > 0
          ? "（改动：" + diffs.map((item) => item.label).join("、") + "）"
          : "（没有字段变化）");
    } catch (error) {
      if (action.alive()) {
        showError(elements.styleError, errorMessageOf(error, "保存没有完成，请重试。"));
      }
    }
  }

  /**
   * @returns {Promise<void>}
   */
  async function handleRestoreStyle() {
    if (!projectId || styleVersion <= 1) return;
    const action = beginAction();
    const pid = action.projectId;
    if (!pid) return;
    clearError(elements.styleError);
    try {
      const versions = await repository.documents.listVersions(
        pid, STYLE_KIND, STYLE_SPEC_DOCUMENT_ID);
      const target = previousVersionOf(versions, styleVersion);
      if (!target) {
        showError(elements.styleError, "没有更早的版本可以恢复。");
        return;
      }
      const restored = /** @type {StyleSpec} */ ({
        ...emptyStyleSpec(),
        ...(isPlainObject(target.payload) ? target.payload : {}),
      });
      const record = await repository.documents.save(pid, {
        kind: STYLE_KIND,
        documentId: STYLE_SPEC_DOCUMENT_ID,
        payload: restored,
        expectedVersion: styleVersion,
      });
      if (!action.alive()) return;
      styleSpec = restored;
      styleVersion = record.version;
      renderStyleSpec();
      renderShotSpecs();
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deriveAndApplyState();
      if (!action.alive()) return;
      elements.styleStatus.hidden = false;
      elements.styleStatus.textContent = "已恢复 v" + target.version
        + " 的内容，写为新版本 v" + record.version + "。";
    } catch (error) {
      if (action.alive()) {
        showError(elements.styleError, errorMessageOf(error, "恢复没有完成，请重试。"));
      }
    }
  }

  /**
   * @param {string} shotId
   * @param {Partial<ShotSpec>} changes
   * @returns {Promise<void>}
   */
  async function handleSaveShotSpec(shotId, changes) {
    if (!projectId || !suitePlan) return;
    const action = beginAction();
    const pid = action.projectId;
    if (!pid) return;
    clearError(elements.specsError);
    try {
      const shot = suitePlan.shots.find((item) => item.shot_id === shotId);
      if (!shot) throw new Error("找不到这张图，可能已被删除。");
      const entry = shotSpecEntry(shotId);
      const base = entry ? entry.spec : emptyShotSpecFromShot(shot);
      const next = {
        ...base,
        purpose: changes.purpose ?? base.purpose,
        keep: changes.keep ?? base.keep,
        change_allowed: changes.change_allowed ?? base.change_allowed,
      };
      assertShotSpec(next);
      const record = await repository.documents.save(pid, {
        kind: SHOT_SPEC_KIND,
        documentId: shotId,
        payload: next,
        expectedVersion: entry ? entry.version : null,
      });
      if (!action.alive()) return;
      shotSpecs.set(shotId, { spec: next, version: record.version });
      renderShotSpecs();
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deriveAndApplyState();
    } catch (error) {
      if (action.alive()) {
        showError(elements.specsError, errorMessageOf(error, "保存没有完成，请重试。"));
      }
    }
  }

  /**
   * @param {string} shotId
   * @returns {Promise<void>}
   */
  async function handleRestoreShotSpec(shotId) {
    if (!projectId) return;
    const action = beginAction();
    const pid = action.projectId;
    if (!pid) return;
    clearError(elements.specsError);
    try {
      const entry = shotSpecEntry(shotId);
      if (!entry || entry.version <= 1) {
        showError(elements.specsError, "没有更早的版本可以恢复。");
        return;
      }
      const versions = await repository.documents.listVersions(
        pid, SHOT_SPEC_KIND, shotId);
      const target = previousVersionOf(versions, entry.version);
      if (!target) {
        showError(elements.specsError, "没有更早的版本可以恢复。");
        return;
      }
      // 历史版本 payload 由本应用写入的 ShotSpec；恢复前用同一校验器复核，不写回形状不符的记录。
      const restored = /** @type {ShotSpec} */ (target.payload);
      assertShotSpec(restored);
      const record = await repository.documents.save(pid, {
        kind: SHOT_SPEC_KIND,
        documentId: shotId,
        payload: restored,
        expectedVersion: entry.version,
      });
      if (!action.alive()) return;
      shotSpecs.set(shotId, { spec: restored, version: record.version });
      renderShotSpecs();
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deriveAndApplyState();
    } catch (error) {
      if (action.alive()) {
        showError(elements.specsError, errorMessageOf(error, "恢复没有完成，请重试。"));
      }
    }
  }

  /* --------------------------------------------------------- Prompt 编译 */

  /**
   * @param {string} shotId
   * @param {PromptEntry} entry
   * @returns {void}
   */
  function rememberPromptVersion(shotId, entry) {
    let history = promptHistory.get(shotId);
    if (!history) { history = new Map(); promptHistory.set(shotId, history); }
    history.set(entry.version, entry);
    const previous = promptVersions.get(shotId);
    if (!previous || previous.version <= entry.version) {
      promptVersions.set(shotId, entry);
    }
  }

  /**
   * @param {string} shotId
   * @param {number} version
   * @returns {PromptEntry|null}
   */
  function promptVersionAt(shotId, version) {
    return promptHistory.get(shotId)?.get(version) || null;
  }

  /**
   * 落库确认的内存登记：entry 为落库前的 {payload, version}（documentId 另传），
   * 函数内补齐 documentId 后存入队列（运行时展开构造，不改形状）。
   * @param {string} documentId
   * @param {{payload: ConfirmationRecord, version: number}} entry
   * @returns {{documentId: string, payload: ConfirmationRecord, version: number}}
   */
  function rememberConfirmation(documentId, entry) {
    const stored = { ...entry, documentId };
    confirmedQueues.set(documentId + ":" + entry.version, stored);
    if (documentId === CONFIRM_DOCUMENT_ID && (!confirmRecord || entry.version >= confirmRecord.version)) {
      confirmRecord = stored;
    } else if (documentId.startsWith(REWORK_CONFIRM_PREFIX)) {
      const shotId = documentId.slice(REWORK_CONFIRM_PREFIX.length);
      const previous = reworkConfirmations.get(shotId);
      if (!previous || entry.version >= previous.version) reworkConfirmations.set(shotId, stored);
    }
    return stored;
  }

  /**
   * @returns {ImagePromptProfile|null}
   */
  function currentImageProfile() {
    try {
      return imagePromptProfile(capabilities && capabilities.images);
    } catch (error) {
      return null;
    }
  }

  /**
   * @param {string|null} shotId
   * @param {ImagePromptProfile|null} [provider]
   * @returns {unknown}
   */
  function promptCurrentBasis(shotId, provider = currentImageProfile()) {
    /** @type {import("./domain/type-contracts.js").BriefBasisItem[]} */
    let briefBasis = [];
    try {
      briefBasis = buildProductBrief(slotEntries()).basis;
    } catch (error) {
      briefBasis = [];
    }
    const specEntry = shotSpecEntry(shotId);
    const shot = suitePlan?.shots.find(item => item.shot_id === shotId);
    return {
      briefBasis: briefBasis,
      shot_signature: shot ? shotSignatureOf(shot) : null,
      suite_version: suiteVersion > 0 ? suiteVersion : null,
      style_version: styleVersion > 0 ? styleVersion : null,
      shot_spec_version: specEntry ? specEntry.version : null,
      platform: { version: PLATFORM_PROFILES.amazon_us.version },
      provider,
    };
  }

  /**
   * @param {string|null} shotId
   * @returns {PromptEntry|null}
   */
  function promptRecordOf(shotId) {
    if (!shotId) return null;
    const entry = promptVersions.get(shotId) || null;
    if (!entry || !entry.record || !entry.record.compiled) return null;
    return entry;
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
    const ready = Boolean(suitePlan);
    elements.promptLocked.hidden = ready;
    elements.promptEditor.hidden = !ready;
    elements.promptList.innerHTML = "";
    if (!ready) return;
    const summary = suitePlanSummary(suitePlan, suiteContext());
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
      compileButton.disabled = !item.satisfied || semanticAnalysis.isRunning();
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
        reconfirmButton.disabled = !item.satisfied || semanticAnalysis.isRunning();
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
          if (reconfirmButton) reconfirmButton.disabled = !item.satisfied || semanticAnalysis.isRunning() || area.value !== entry.record.compiled.text;
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
        saveEdit.disabled = semanticAnalysis.isRunning();
        saveEdit.addEventListener("click", () => { handleSaveEditedPrompt(shotId); });
        block.append(saveEdit);
        card.append(block);
      }
      elements.promptList.append(card);
    });
  }

  /**
   * 纯编译一张图的 Prompt（不写记录）：预览、保存与提交共用同一条编译路径。
   */
  /**
   * @param {string} shotId
   * @param {{action?: ActionSnapshot|null, rework?: import("./domain/type-contracts.js").ReworkDirective}} [options]
   * @returns {Promise<{payload: PromptRecord, compiled: import("./domain/type-contracts.js").CompiledPrompt, references: import("./domain/type-contracts.js").PromptReferenceSelection[]}>}
   */
  async function compileShotPrompt(shotId, options = {}) {
    const shot = (suitePlan && suitePlan.shots ? suitePlan.shots : []).find((item) => item.shot_id === shotId);
    if (!shot) throw new Error("找不到这张图，可能已被删除。");
    const brief = buildProductBrief(slotEntries());
    const specEntry = shotSpecEntry(shotId);
    const providerProfile = currentImageProfile();
    if (!providerProfile) throw new Error("尚未取得有效图像能力，请恢复模型服务后再编译；不会猜测模型参数。");
    const compiled = compilePrompt({
      brief: brief,
      shot: shot,
      styleSpec: styleSpec,
      shotSpec: specEntry ? specEntry.spec : null,
      context: suiteContext(),
      providerProfile: providerProfile,
      versions: {
        suite_version: suiteVersion,
        style_version: styleVersion,
        shot_spec_version: specEntry ? specEntry.version : null,
      },
      ...(options.rework ? { rework: options.rework } : {}),
    });
    const references = selectReferences(shot, intake.references.map((item) => ({
      role: item.role, sha256: item.asset_sha256,
    })), { maxReferences: providerProfile.max_reference_images });
    const snapshot = requestSnapshotOf(compiled, { references: references });
    const hash = await promptHash(snapshot, { digest: sha256Hex });
    const payload = buildPromptRecord({ compiled: compiled, snapshot: snapshot, hash: hash });
    const problems = checkPromptRecord(payload);
    if (problems.length > 0) throw new Error(problems[0].message);
    return { payload: payload, compiled: compiled, references: references };
  }

  /** 保存一条已编译的 Prompt 版本；版本号由 repository 递增，旧版本保留。 */
  /** 保存一条已编译的 Prompt 版本；版本号由 repository 递增，旧版本保留。
   * @param {string} shotId
   * @param {PromptRecord} payload
   * @param {ActionSnapshot|null} [action]
   * @param {number} [expectedVersion]
   * @returns {Promise<import("./storage/validate.js").StoredDocumentRecord<PromptRecord>>}
   */
  async function savePromptPayload(shotId, payload, action = null, expectedVersion = promptRecordOf(shotId)?.version || 0) {
    const pid = action ? action.projectId : projectId;
    if (!pid) throw new Error("缺少项目上下文，无法保存 Prompt 版本。");
    const saved = await repository.documents.save(pid, {
      kind: PROMPT_KIND, documentId: shotId, payload: payload,
      expectedVersion,
    });
    if (!action || action.alive()) {
      rememberPromptVersion(shotId, { record: payload, version: saved.version });
    }
    return saved;
  }

  /**
   * 编译并保存一张图的 Prompt 版本（V2.5.4 起可选带返工指令）。
   * 纯编译 + 保存；失败抛错交给调用方，界面文案不在这一层写死。
   */
  /**
   * @param {string} shotId
   * @param {{action?: ActionSnapshot|null, rework?: import("./domain/type-contracts.js").ReworkDirective}} [options]
   * @returns {Promise<{saved: import("./storage/validate.js").StoredDocumentRecord<PromptRecord>, payload: PromptRecord, compiled: import("./domain/type-contracts.js").CompiledPrompt, references: import("./domain/type-contracts.js").PromptReferenceSelection[]}>}
   */
  async function compileAndSavePrompt(shotId, options = {}) {
    const expectedVersion = promptRecordOf(shotId)?.version || 0;
    const result = await compileShotPrompt(shotId, options);
    const saved = await savePromptPayload(shotId, result.payload, options.action || null, expectedVersion);
    return { saved: saved, payload: result.payload, compiled: result.compiled,
             references: result.references };
  }

  /** Local preparation only. Manual records and unsaved human drafts are never overwritten. */
  /** Local preparation only. Manual records and unsaved human drafts are never overwritten.
   * @returns {Promise<void>}
   */
  async function prepareSystemPrompts() {
    if (!projectId || localPreparationInFlight) return;
    if (!suitePlan || !understandingReady || !currentImageProfile()) {
      elements.localPreparationStatus.textContent = !suitePlan
        ? "先添加图片任务；本地准备不会调用模型。"
        : !understandingReady ? "请人工确认核心事实；各图片用途的额外缺项就地补足。"
          : "等待有效图像配置；打开模型设置可恢复。";
      return;
    }
    const summary = suitePlanSummary(suitePlan, suiteContext());
    const stamp = canonicalJson({ project_id: projectId, shots: summary.shots.map(item => ({
      id: item.shot_id, satisfied: item.satisfied, basis: promptCurrentBasis(item.shot_id),
      origin: promptRecordOf(item.shot_id)?.record.origin || null,
    })) });
    if (stamp === lastPreparationInputs) return;
    const action = beginAction();
    localPreparationInFlight = true;
    elements.localPreparationStatus.textContent = "正在本地准备已就绪图片任务；不会调用模型…";
    renderConfirm();
    let prepared = 0;
    const errors = [];
    try {
      const drafts = capturePromptEdits();
      for (const item of summary.shots) {
        if (!action.alive()) return;
        if (!item.satisfied) continue;
        // 已保存计划恒有 shot_id；null 仅存在于未落库草稿，跳过即可。
        const shotId = item.shot_id;
        if (typeof shotId !== "string") continue;
        const entry = promptRecordOf(shotId);
        const draft = drafts.get(shotId);
        if (entry?.record.origin === "manual_edit"
            || (draft && entry && draft.text !== entry.record.compiled.text)) continue;
        if (entry && !promptStaleness(entry.record, promptCurrentBasis(shotId)).stale) continue;
        try {
          await compileAndSavePrompt(shotId, { action });
          prepared += 1;
        } catch (error) { errors.push(item.label + "：" + errorMessageOf(error, "本地准备失败")); }
      }
      if (!action.alive()) return;
      lastPreparationInputs = stamp;
      elements.localPreparationStatus.textContent = errors.length
        ? "部分任务尚未准备：" + errors.join("；")
        : "本地准备完成" + (prepared ? "（更新 " + prepared + " 张）" : "")
          + "；未调用模型。人工文本保留，提交前请核对下面的摘要。";
      await deriveAndApplyState();
    } finally {
      localPreparationInFlight = false;
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
    const context = { facts: slotEntries().map(entry => entry.slot), brief: buildProductBrief(slotEntries()) };
    clearError(elements.promptError);
    try {
      const current = await compileShotPrompt(shotId);
      const record = await reconfirmEditedPrompt({
        base: entry.record, baseVersion: entry.version,
        reason: "用户按当前依据显式确认保留此人工全文", at: new Date().toISOString(),
        basis: current.compiled.basis, references: current.references,
        context: { ...context, currentCompiled: current.compiled }, digest: sha256Hex,
      });
      const saved = await savePromptPayload(shotId, record, action, entry.version);
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
      const history = promptHistory.get(shotId);
      const discarded = discardManualEdit(entry.record, history ? [...history.values()] : []);
      // 历史系统版本来自本应用写入的 PromptRecord；用同一校验器复核后再作为恢复候选。
      const candidate = discarded.target && isPlainObject(discarded.target.record)
        && checkPromptRecord(discarded.target.record).length === 0
        ? /** @type {PromptRecord} */ (discarded.target.record) : null;
      const payload = candidate && !promptStaleness(candidate, promptCurrentBasis(shotId)).stale
        ? candidate : (await compileShotPrompt(shotId)).payload;
      await savePromptPayload(shotId, payload, action, entry.version);
      if (!action.alive()) return;
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
    if (!projectId || !suitePlan || !understandingReady) return;
    const action = beginAction();
    clearError(elements.promptError);
    try {
      const result = await compileAndSavePrompt(shotId, { action });
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
    if (!projectId || !suitePlan || !understandingReady) return;
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
      const context = suiteContext();
      context.brief = buildProductBrief(slotEntries());
      const record = await buildEditedPromptRecord({
        base: entry.record,
        baseVersion: entry.version,
        text: area ? area.value : "",
        reason: reasonInput ? reasonInput.value : "",
        editedAt: new Date().toISOString(),
        context: context,
        digest: sha256Hex,
      });
      const pid = action.projectId;
      if (!pid) return;
      const saved = await repository.documents.save(pid, {
        kind: PROMPT_KIND, documentId: shotId, payload: record,
        expectedVersion: entry.version,
      });
      if (!action.alive()) return;
      rememberPromptVersion(shotId, { record, version: saved.version });
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
   * shotIds 给定时只投影这些图（V2.5.4 单图返工），否则是整套。
   * @param {string[]|null} shotIds
   * @param {{providerProfile?: ImagePromptProfile|null, promptEntries?: Array<{shot_id: string, record: PromptRecord, version: number}>|null}} [options]
   * @returns {ConfirmationSheetView|null}
   */
  function buildScopedSheet(/** @type {string[]|null} */ shotIds, { providerProfile = currentImageProfile(), promptEntries = null } = {}) {
    if (!suitePlan || !providerProfile) return null;
    const entries = promptEntries || [...promptVersions.entries()].map(([shotId, entry]) => ({
      shot_id: shotId, record: entry.record, version: entry.version,
    }));
    /** @type {Record<string, unknown>} */
    const basisByShot = {};
    for (const shot of suitePlan.shots) {
      const shotId = shot.shot_id;
      if (typeof shotId !== "string") continue;
      basisByShot[shotId] = promptCurrentBasis(shotId, providerProfile);
    }
    // buildConfirmationSheet 的输出由 assertConfirmationSheet 校验后再按本地视图收窄。
    const sheet = buildConfirmationSheet({
      suitePlan: suitePlan,
      promptEntries: entries,
      providerProfile: providerProfile,
      context: suiteContext(),
      currentBasisByShot: basisByShot,
      shotIds: shotIds,
    });
    assertConfirmationSheet(sheet);
    return /** @type {ConfirmationSheetView} */ (sheet);
  }

  /**
   * @returns {ConfirmationSheetView|null}
   */
  function buildCurrentSheet() {
    return buildScopedSheet(null);
  }

  /**
   * @returns {WorkspaceGenerationIntent|null}
   */
  function buildGenerationIntent() {
    const all = buildCurrentSheet();
    if (!all) return null;
    const batch = generation.deriveBatch();
    const eligible = new Set(generationScope || (generationMode === "failed_retry" ? batch.retry_queue : batch.queue));
    const ids = all.shots.filter(item => eligible.has(item.shot_id) && !item.blockers.length).map(item => item.shot_id);
    const sheet = ids.length ? buildScopedSheet(ids) : null;
    const identity = attemptCurrentEnvironmentIdentity(modelSettings.imageEnvironment());
    const snapshot = sheet && identity
      ? confirmationSnapshot(sheet, { executionIdentity: identity, submissionMode: generationMode }) : null;
    return { all, sheet, identity, snapshot, mode: generationMode };
  }

  /**
   * @param {ConfirmationQueue} queue
   * @param {string} shotId
   * @returns {boolean}
   */
  function queueShotIsCurrent(queue, shotId) {
    const target = queue.payload.fingerprint.snapshot.execution_target;
    if (!target) return false;
    const saved = queue.payload.shots.find(shot => shot.shot_id === shotId);
    if (!saved || typeof saved.prompt_version !== "number") return false;
    const entry = promptVersionAt(shotId, saved.prompt_version);
    if (!entry || entry.record.hash !== saved.prompt_hash) return false;
    const shot = suitePlan?.shots.find(shot => shot.shot_id === shotId);
    if (!shot) return false;
    const environment = modelSettings.imageEnvironment(target.provider_id, target.credential_source);
    try {
      const profile = imagePromptProfile(environment);
      if (promptStaleness(entry.record, promptCurrentBasis(shotId, profile)).stale) return false;
      const references = selectReferences(shot, intake.references.map(ref => ({ role: ref.role, sha256: ref.asset_sha256 })),
        { maxReferences: profile.max_reference_images });
      return canonicalJson(references) === canonicalJson(entry.record.request_snapshot.references);
    } catch { return false; }
  }

  /** 确认记录是否仍然对得上「这一批将要提交的东西」。 */
  /** 确认记录是否仍然对得上「这一批将要提交的东西」。
   * @returns {boolean}
   */
  function confirmationIsCurrent() {
    const queue = confirmRecord;
    return Boolean(queue?.payload?.fingerprint?.snapshot?.execution_target
      && queue.payload.shots.some(shot => queueShotIsCurrent(queue, shot.shot_id)));
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
    const entry = reworkConfirmations.get(shotId);
    return Boolean(entry && queueShotIsCurrent(entry, shotId));
  }

  /** 提交这张图的条件：整套确认有效，或这张图有自己有效的返工确认。 */
  /** 提交这张图的条件：整套确认有效，或这张图有自己有效的返工确认。
   * @param {string|null} shotId
   * @returns {boolean}
   */
  function confirmationIsCurrentForShot(shotId) {
    if (!shotId) return false;
    return [...confirmedQueues.values()].some(queue => queue.payload.shots.some(shot => shot.shot_id === shotId)
      && queueShotIsCurrent(queue, shotId));
  }

  /**
   * @returns {void}
   */
  function renderConfirm() {
    const ready = Boolean(suitePlan);
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
    if (generationMode === "explicit_new") {
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
    elements.confirmAction.disabled = !sending?.can_submit || !identity?.configured || semanticAnalysis.isRunning()
      || localPreparationInFlight || submissionInFlight || modelSettings.refreshing
      || Boolean(generation.batchStateReader()?.active);
    elements.confirmAction.textContent = (generationMode === "explicit_new" ? "确认并另发 " : "确认并生成 ")
      + (sending?.total || 0) + " 张";
    elements.confirmRecord.textContent = identity?.configured
      ? "一次点击先保存这份授权，再按摘要外发；不会要求第二次提交。"
      : "原目标凭据未就绪。打开模型设置补凭据；本地事实、Prompt、采用和导出不受影响。";
  }

  /**
   * @returns {Promise<void>}
   */
  async function handleConfirmGeneration() {
    if (!projectId || !suitePlan || submissionInFlight || localPreparationInFlight || modelSettings.refreshing) return;
    const authorized = displayedGenerationIntent;
    const action = beginAction();
    const expectedVersion = confirmRecord?.version || 0;
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

  /**
   * @param {Blob} blob
   * @returns {Promise<string>}
   */
  async function blobToBase64(blob) {
    const buffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    let binary = "";
    const chunk = 0x8000;
    for (let index = 0; index < bytes.length; index += chunk) {
      binary += String.fromCharCode(...bytes.subarray(index, index + chunk));
    }
    return btoa(binary);
  }

  /**
   * Freeze the explicit candidate, current confirmed facts and original reference chain before reading bytes.
   * 图片字节只从 IndexedDB 读；资料缺失或超上限时抛错（调用方转为未完成，不送半份资料）。
   */
  /**
   * Freeze the explicit candidate, current confirmed facts and original reference chain before reading bytes.
   * 图片字节只从 IndexedDB 读；资料缺失或超上限时抛错（调用方转为未完成，不送半份资料）。
   * @param {string} shotId
   * @param {CandidateRecord} candidate
   * @param {string} pid
   * @returns {Promise<unknown>}
   */
  async function buildReviewRequest(shotId, candidate, pid) {
    const shot = (suitePlan?.shots || []).find(item => item.shot_id === shotId) || null;
    const spec = shotSpecEntry(shotId)?.spec || (shot ? emptyShotSpecFromShot(shot) : null);
    const original = attemptsByActionId()[candidate.action_id];
    if (!original) throw new Error("候选的原动作来源链缺失，没有发起 AI 复核。");
    const references = original.references.slice(0, MAX_REVIEW_REFERENCES);
    const facts = confirmedFactPayloads();
    const asset = await repository.assets.get(pid, candidate.asset_sha256);
    if (!asset?.blob || asset.blob.size > MAX_REVIEW_IMAGE_BYTES) {
      throw new Error("候选字节缺失或超过复核上限，没有发起 AI 复核。");
    }
    if (await sha256Hex(await asset.blob.arrayBuffer()) !== candidate.asset_sha256) {
      throw new Error("候选字节哈希不一致，没有发起 AI 复核。");
    }
    const referencePayload = await generation.buildReferencePayload(references, pid);
    return {
      candidate: {
        media_type: candidate.media_type || "image/png",
        sha256: candidate.asset_sha256,
        data_base64: await blobToBase64(asset.blob),
      },
      references: referencePayload.map((item) => ({
        media_type: item.media_type,
        sha256: item.sha256,
        data_base64: item.data_base64,
      })),
      shot: {
        title: String((shot && (shot.label || shot.role_id)) || "图片任务").slice(0, 200),
        purpose: spec ? String(spec.purpose || "").slice(0, 500) : "",
        keep_items: spec ? spec.keep.slice(0, 8) : [],
        allow_changes: spec ? spec.change_allowed.slice(0, 8) : [],
      },
      platform: ANALYZE_PLATFORM,
      product_facts: facts,
      locale: ANALYZE_LOCALE,
    };
  }

  /** 单张「保存候选图片」按钮入口：只翻译结果，不做批次策略。 */
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
    const shots = suitePlan ? suitePlanSummary(suitePlan, suiteContext()).shots : [];
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
        const existing = generation.reviewReportOf(candidate.candidate_id);
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
    const shot = ((suitePlan && suitePlan.shots) || [])
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
    const ready = Boolean(suitePlan);
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
    const shot = ((suitePlan && suitePlan.shots) || [])
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
    elements.compareReview.disabled = !viewed || !reviewShotId || generation.isReviewInFlight(reviewShotId)
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
    const specEntry = shotSpecEntry(shot.shot_id);
    const checklist = reviewChecklist(shot, {
      shotSpec: specEntry ? specEntry.spec : null, styleSpec: styleSpec,
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
    const ready = Boolean(suitePlan);
    elements.attemptLocked.hidden = ready;
    elements.attemptEditor.hidden = !ready;
    elements.attemptList.innerHTML = "";
    if (!ready) { renderBatch(); renderCompare(); renderSelectionProgress(); return; }
    const summary = suitePlanSummary(suitePlan, suiteContext());
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
      const latest = chain.length ? chain[chain.length - 1] : null;
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
            const reviewEntry = generation.reviewReportOf(candidate.candidate_id);
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
              text: rowShotId && generation.isReviewInFlight(rowShotId) ? "复核中…" : "AI 复核这条候选（可选）",
              attrs: {
                type: "button",
                "data-review-action": candidate.candidate_id,
                title: "调用视觉语言模型找可疑问题；只提示，不自动采纳",
              },
            });
            reviewButton.disabled = Boolean(!rowShotId || generation.isReviewInFlight(rowShotId))
              || !capabilities?.review?.provider || capabilities.review.provider.configured === false;
            reviewButton.addEventListener("click", async () => {
              if (!rowShotId) return;
              const outcome = await generation.reviewCandidate(rowShotId, candidate.candidate_id);
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
        const selectionEntry = rowShotId ? selections.get(rowShotId) || null : null;
        const selectionState = deriveSelectionState(selectionEntry ? selectionEntry.record : null,
          (rowShotId ? generation.candidateChainOf(rowShotId) : []).map((entry) => entry.record));
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
      const inFlight = (rowShotId ? generation.isAttemptInFlight(rowShotId) : false) || semanticAnalysis.isRunning() || batchActive;
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
        button.disabled = !canSubmit;
        button.addEventListener("click", () => {
          handleSubmitAttempt(rowShotId, { explicitNew: true });
        });
        actions.append(button);
      } else if (state === ATTEMPT_STATES.failed) {
        const button = createElement("button", {
          text: "重试（新建 action）", attrs: { type: "button" },
        });
        button.disabled = !canSubmit;
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
        button.disabled = !canSubmit;
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
    return REWORK_CONFIRM_PREFIX + shotId;
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
      const result = await compileShotPrompt(shotId, { rework: directive });
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
      const latest = promptVersions.get(shotId) || null;
      let version = latest ? latest.version : 0;
      const fromPreview = Boolean(latest && latest.record.compiled.rework
        && latest.record.compiled.rework.directive_id === draft.preview.directive_id);
      if (!fromPreview) {
        if (!draft.directive) throw new Error("先预览返工 Prompt，再查看或编辑全文。");
        const saved = await compileAndSavePrompt(shotId, { rework: draft.directive });
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
    const sheet = buildScopedSheet([shotId]);
    if (!sheet || !sheet?.can_submit) throw new Error("这张图当前还有阻断，返工没有外发。");
    const identity = attemptCurrentEnvironmentIdentity(modelSettings.imageEnvironment());
    const mode = "rework";
    return { sheet, identity, mode,
      snapshot: confirmationSnapshot(sheet, { executionIdentity: identity, submissionMode: mode }) };
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
      const latest = promptVersions.get(shotId) || null;
      let version = latest ? latest.version : 0;
      const fromPreview = Boolean(latest && latest.record.compiled.rework
        && latest.record.compiled.rework.directive_id === draft.preview.directive_id);
      if (!fromPreview) {
        if (!draft.directive) throw new Error("先预览返工 Prompt，再确认生成。");
        const saved = await compileAndSavePrompt(shotId, { rework: draft.directive, action });
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
    const summary = suitePlan ? suitePlanSummary(suitePlan, suiteContext()) : null;
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
    const summary = suitePlan ? suitePlanSummary(suitePlan, suiteContext()) : null;
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
    const ready = Boolean(suitePlan);
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
    for (const queue of [...confirmedQueues.values()].reverse()) {
      const pending = generation.pendingConfirmedShots(queue);
      if (!pending.length) continue;
      const target = queue.payload.fingerprint.snapshot.execution_target;
      if (!target) continue;
      const identity = attemptCurrentEnvironmentIdentity(modelSettings.imageEnvironment(target.provider_id, target.credential_source));
      const keys = /** @type {const} */ (["provider_id", "model_id", "protocol", "capability_version", "credential_source", "sync"]);
      const matched = Boolean(identity?.configured) && keys
        .every(key => identity?.[key] === target[key]);
      const current = pending.filter(id => queueShotIsCurrent(queue, id));
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

  /**
   * @param {string|null} shotId
   * @returns {{record: SelectionRecord, version: number}|null}
   */
  function selectionEntryOf(shotId) {
    if (!shotId) return null;
    return selections.get(shotId) || null;
  }

  /**
   * @param {string} shotId
   * @returns {CandidateRecord[]}
   */
  function candidatePayloadsOf(shotId) {
    return generation.candidateChainOf(shotId).map((entry) => entry.record);
  }

  /**
   * @param {string} shotId
   * @returns {SelectionState}
   */
  function selectionStateOf(shotId) {
    const entry = selectionEntryOf(shotId);
    return deriveSelectionState(entry ? entry.record : null, candidatePayloadsOf(shotId));
  }

  /** 某张图当前采用的候选（含过期标记）：只读投影，供比较列表做徽标。 */
  /** 某张图当前采用的候选（含过期标记）：只读投影，供比较列表做徽标。
   * @param {string|null} shotId
   * @returns {{candidate_id: string|null, state: SelectionState}|null}
   */
  function adoptedMarkOf(shotId) {
    if (!shotId) return null;
    const entry = selectionEntryOf(shotId);
    if (!entry || !entry.record || entry.record.action !== "select") return null;
    return { candidate_id: entry.record.candidate_id, state: selectionStateOf(shotId) };
  }

  /** SelectionSet 投影：V2.5.5 / V2.6.2 的唯一输入集合；这里只报告数量，不拦导出。 */
  /** SelectionSet 投影：V2.5.5 / V2.6.2 的唯一输入集合；这里只报告数量，不拦导出。
   * @returns {import("./domain/type-contracts.js").SelectionSet}
   */
  function selectionSetNow() {
    const summaries = suitePlan ? suitePlanSummary(suitePlan, suiteContext()).shots : [];
    const shots = summaries.map((shot) => ({
      shot_id: shot.shot_id, required: shot.required === true,
    }));
    const selectionsByShot = /** @type {Record<string, SelectionRecord>} */ ({});
    for (const [shotId, entry] of selections) selectionsByShot[shotId] = entry.record;
    const candidatesByShotId = /** @type {Record<string, CandidateRecord[]>} */ ({});
    for (const shot of shots) candidatesByShotId[shot.shot_id] = candidatePayloadsOf(shot.shot_id);
    return buildSelectionSet({
      shots: shots, selections: selectionsByShot, candidatesByShotId: candidatesByShotId,
      at: new Date().toISOString(),
    });
  }

  /**
   * @returns {void}
   */
  function renderSelectionProgress() {
    if (!suitePlan) {
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
    const available = Boolean(shot && row && row.record && row.asset_sha256);
    const selected = shot ? selectionEntryOf(shot.shot_id)?.record : null;
    const already = Boolean(selected?.action === "select" && row && selected.candidate_id === row.candidate_id
      && shot && selectionStateOf(shot.shot_id) === "current");
    elements.adoptOpen.disabled = adoptInFlight || !available || already;
    elements.adoptOpen.textContent = already ? "已采用当前候选"
      : selected?.action === "select" ? "改选当前候选" : "采用当前候选";
    elements.adoptClear.disabled = adoptInFlight || selected?.action !== "select";
    if (available && shot && row) {
      elements.adoptOpen.dataset.shotId = shot.shot_id;
      elements.adoptOpen.dataset.candidateId = row.candidate_id;
      elements.adoptOpen.dataset.candidateSha256 = row.asset_sha256;
    } else {
      delete elements.adoptOpen.dataset.shotId;
      delete elements.adoptOpen.dataset.candidateId;
      delete elements.adoptOpen.dataset.candidateSha256;
    }
  }

  /** 采用目标：把「正看着的候选」解析成候选记录 + 文档版本 + 当前审核报告。 */
  /** 采用目标：把「正看着的候选」解析成候选记录 + 文档版本 + 当前审核报告。
   * @param {string|null} shotId
   * @param {string|null} candidateId
   * @returns {{candidate: CandidateRecord, version: number, report: ReviewReport|null}|null}
   */
  function adoptSourceOf(shotId, candidateId) {
    if (!shotId) return null;
    for (const entry of generation.candidateChainOf(shotId)) {
      if (entry.record && entry.record.candidate_id === candidateId) {
        const stored = generation.reviewReportOf(candidateId);
        const report = stored && reviewIsCurrent(stored.report, entry.record)
          ? stored.report : null;
        return { candidate: entry.record, version: entry.version, report: report };
      }
    }
    return null;
  }

  /**
   * @param {string} shotId
   * @returns {string}
   */
  function selectionTextOf(shotId) {
    const entry = selectionEntryOf(shotId);
    return selectionSummaryText(entry ? entry.record : null, selectionStateOf(shotId));
  }

  /** One explicit human action. Identity freezes before any byte read; selection is append-only/OCC. */
  /** One explicit human action. Identity freezes before any byte read; selection is append-only/OCC.
   * @param {string} kind
   * @param {string|null} [shotId]
   * @param {string|null} [candidateId]
   * @returns {Promise<void>}
   */
  async function handleCandidateSelection(kind, shotId = compareShotId, candidateId = compareCandidateId) {
    if (!projectId || !shotId || adoptInFlight) return;
    const action = beginAction();
    const source = candidateId ? adoptSourceOf(shotId, candidateId) : null;
    const previous = selectionEntryOf(shotId);
    adoptInFlight = true;
    clearError(elements.adoptError);
    elements.adoptStatus.hidden = false;
    elements.adoptStatus.textContent = "正在保存 " + shotLabelOf(shotId) + " 的人工选择…";
    try {
      if (kind === "select") {
        if (!source) throw new Error("候选已不在本地链中；原采用保留。");
        if (!action.projectId) throw new Error("缺少项目上下文，人工选择没有保存。");
        const asset = await repository.assets.get(action.projectId, source.candidate.asset_sha256);
        if (!asset?.blob || await sha256Hex(await asset.blob.arrayBuffer()) !== source.candidate.asset_sha256) {
          throw new Error("候选字节缺失或哈希不一致；原采用保留，请恢复项目包或候选字节。");
        }
        const checked = await generation.ensureReviewReport(shotId, source.candidate, null, action.projectId);
        source.report = checked?.report || null;
        if (!source.report || !reviewIsCurrent(source.report, source.candidate)) {
          throw new Error("没有当前确定性检查报告；原采用保留。此检查不需要 AI 复核。");
        }
      }
      if (!action.alive()) return;
      if (!action.projectId) return;
      const record = buildSelectionRecord({
        selectionId: newActionId(), action: kind, shotId,
        candidate: kind === "select" ? source?.candidate || null : null,
        candidateVersion: kind === "select" ? source?.version || null : null,
        report: kind === "select" ? source?.report || null : null,
        at: new Date().toISOString(),
      });
      assertSelectionRecord(record);
      const saved = await repository.documents.save(action.projectId, {
        kind: SELECTION_KIND, documentId: shotId, payload: record,
        expectedVersion: previous?.version || null,
      });
      if (!action.alive()) return;
      selections.set(shotId, { record, version: saved.version });
      elements.adoptStatus.textContent = shotLabelOf(shotId) + (kind === "select"
        ? " 已采用候选 v" + (source ? source.version : "?") : " 已取消采用")
        + "；旧候选和旧采用保留在历史中。确定性硬阻断仍会阻止交付。";
    } catch (error) {
      if (action.alive()) {
        elements.adoptStatus.textContent = "人工选择没有保存；原采用保留。";
        showError(elements.adoptError, errorMessageOf(error, "存储失败，请重试。"));
      }
    } finally {
      adoptInFlight = false;
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
    understandingBlocking = [];
    understandingError = null;
    understandingReady = false;
    try {
      const brief = buildProductBrief(slotEntries());
      const readiness = briefReadiness(brief);
      understandingReady = readiness.ready;
      understandingBlocking = readiness.blocking;
    } catch (error) {
      understandingError = error;
    }
    const state = slots.size === 0
      ? (intakeReadiness(intake).ready ? "INTAKE_READY" : "EMPTY")
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
    return suitePlan ? suitePlanSummary(suitePlan, suiteContext()).shots : [];
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
    const entries = slotEntries();
    const confirmed = entries.filter((item) => item.slot.status === "confirmed").length;
    const unknownSlots = entries.filter((item) => item.slot.status === "unknown").length;
    const hasSlots = slots.size > 0;
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
    const referenceCount = Array.isArray(intake.references) ? intake.references.length : 0;
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
    renderSuitePanel();
    requestDeliveryGateRefresh();
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

  /** 已确认事实的最小投影（单图复核与整套复核共用，唯一来源）。 */
  /** 已确认事实的最小投影（单图复核与整套复核共用，唯一来源）。
   * @returns {Array<{slot_id: string, label: string, value: unknown, source: string}>}
   */
  function confirmedFactPayloads() {
    const facts = /** @type {Array<{slot_id: string, label: string, value: unknown, source: string}>} */ ([]);
    for (const entry of slots.values()) {
      const slot = entry && entry.slot ? entry.slot : null;
      if (!slot || slot.status !== "confirmed") continue;
      const value = Array.isArray(slot.value) ? slot.value.join("；") : String(slot.value);
      facts.push({
        slot_id: slot.slot_id, label: String(slot.label || slot.slot_id).slice(0, 60),
        value: value.slice(0, 200), source: slot.source,
      });
      if (facts.length >= 20) break;
    }
    return facts;
  }

  /**
   * @returns {{report: SuiteReviewReport, version: number}|null}
   */
  function suiteReportEntry() {
    return suiteReports.get(SUITE_REVIEW_DOCUMENT_ID) || null;
  }

  /**
   * @returns {Record<string, ShotSpec>}
   */
  function suiteShotSpecsById() {
    const byId = /** @type {Record<string, ShotSpec>} */ ({});
    for (const [shotId, entry] of shotSpecs) {
      if (entry && entry.spec) byId[shotId] = entry.spec;
    }
    return byId;
  }

  /**
   * @returns {Record<string, ReviewReport>}
   */
  function suiteReportsByCandidate() {
    const map = /** @type {Record<string, ReviewReport>} */ ({});
    for (const entry of generation.reviewReportsNow()) {
      const candidateId = entry[0];
      const value = entry[1];
      if (value && value.report) map[candidateId] = value.report;
    }
    return map;
  }

  /**
   * @returns {Record<string, SelectionRecord>}
   */
  function suiteSelectionMap() {
    const map = /** @type {Record<string, SelectionRecord>} */ ({});
    for (const [shotId, entry] of selections) {
      if (entry && entry.record && entry.record.action === "select") {
        map[shotId] = entry.record;
      }
    }
    return map;
  }

  /**
   * @returns {Record<string, CandidateRecord[]>}
   */
  function suiteCandidatesByShot() {
    const map = /** @type {Record<string, CandidateRecord[]>} */ ({});
    for (const shot of shotSummariesNow()) map[shot.shot_id] = candidatePayloadsOf(shot.shot_id);
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
   * @returns {Record<string, FactSlot>}
   */
  function suiteFactsById() {
    const map = /** @type {Record<string, FactSlot>} */ ({});
    for (const [slotId, entry] of slots) {
      if (entry && entry.slot) map[slotId] = entry.slot;
    }
    return map;
  }

  /** 当前选择与输入的指纹（报告当前性唯一依据；与 domain 的规范化逐字一致）。 */
  /** 当前选择与输入的指纹（报告当前性唯一依据；与 domain 的规范化逐字一致）。
   * @returns {{selectionSet: import("./domain/type-contracts.js").SelectionSet, selectionFingerprint: string, inputsFingerprint: string}}
   */
  function suiteFingerprintsNow() {
    const selectionSet = selectionSetNow();
    const selectionFingerprint = selectionFingerprintOf(selectionSet);
    const inputsFingerprint = inputsFingerprintOf({
      selectionFingerprint: selectionFingerprint,
      suitePlan: suitePlan,
      styleSpec: styleSpec,
      shotSpecsById: suiteShotSpecsById(),
      reportsByCandidate: suiteReportsByCandidate(),
    });
    return { selectionSet, selectionFingerprint, inputsFingerprint };
  }

  /**
   * @returns {string}
   */
  function suiteStyleSummaryText() {
    if (!styleSpec) return "";
    const parts = [];
    if (styleSpec.background) parts.push("背景：" + styleSpec.background);
    if (styleSpec.lighting) parts.push("光线：" + styleSpec.lighting);
    if (styleSpec.color_tone) parts.push("色调：" + styleSpec.color_tone);
    if (styleSpec.composition) parts.push("构图：" + styleSpec.composition);
    if (Array.isArray(styleSpec.avoid) && styleSpec.avoid.length) {
      parts.push("避免：" + styleSpec.avoid.join("、"));
    }
    return parts.join("；").slice(0, 500);
  }

  /**
   * 送审集合与请求体：图片字节只从 IndexedDB 读；任何一张缺字节/超上限都不送半份资料。
   * 返回 {request, requested, submitted, shaByShot, reason}；reason 非空时 request 为 null。
   */
  /**
   * @typedef {object} SuiteVlmSnapshot
   * @property {Array<{shot_id: string, label: string}>} shots
   * @property {Record<string, string|null>} selections
   * @property {Record<string, SelectionState>} selectionStates
   * @property {Record<string, CandidateRecord[]>} candidatesByShot
   * @property {Record<string, ShotSpec>} shotSpecsById
   * @property {string} styleSummary
   * @property {Array<{slot_id: string, label: string, value: unknown, source: string}>} productFacts
   * @property {SuitePlan|null} suitePlan
   */
  /**
   * @typedef {object} SuiteVlmPrepared
   * @property {string|null} reason
   * @property {string[]} requested
   * @property {string[]} submitted
   * @property {Record<string, string>} shaByShot
   * @property {unknown} request
   */
  /**
   * @param {SuiteVlmSnapshot} snapshot
   * @param {string} pid
   * @returns {Promise<SuiteVlmPrepared>}
   */
  async function suiteVlmRequestFor(snapshot, pid) {
    const selectionMap = snapshot.selections;
    const requested = snapshot.shots.filter(shot => snapshot.selectionStates[shot.shot_id] === "current")
      .map(shot => shot.shot_id);
    if (requested.length === 0) {
      return { reason: "no_selection", requested: [], submitted: [], shaByShot: {}, request: null };
    }
    if (requested.length > SUITE_MAX_IMAGES) {
      return { reason: "over_limit", requested: requested, submitted: [], shaByShot: {}, request: null };
    }
    const images = /** @type {Array<{shot_id: string, title: string, purpose: string, keep_items: string[], allow_changes: string[], image: {media_type: string, sha256: string, data_base64: string}}>} */ ([]);
    const submitted = /** @type {string[]} */ ([]);
    const shaByShot = /** @type {Record<string, string>} */ ({});
    const planShots = snapshot.suitePlan && Array.isArray(snapshot.suitePlan.shots) ? snapshot.suitePlan.shots : [];
    for (const shotId of requested) {
      const candidateId = selectionMap[shotId];
      const chain = snapshot.candidatesByShot[shotId] || [];
      const candidate = chain.find((/** @type {CandidateRecord} */ item) => item && item.candidate_id === candidateId) || null;
      if (!candidate) {
        return { reason: "missing_bytes", requested: requested, submitted: [], shaByShot: {}, request: null };
      }
      let asset = null;
      try {
        asset = await repository.assets.get(pid, candidate.asset_sha256);
      } catch (error) {
        asset = null;
      }
      if (!asset || !(asset.blob instanceof Blob)) {
        return { reason: "missing_bytes", requested: requested, submitted: [], shaByShot: {}, request: null };
      }
      if (asset.blob.size > MAX_SUITE_IMAGE_BYTES) {
        return { reason: "image_too_large", requested: requested, submitted: [], shaByShot: {}, request: null };
      }
      const shot = planShots.find((/** @type {PlanShot} */ item) => item && item.shot_id === shotId) || null;
      const spec = snapshot.shotSpecsById[shotId] || (shot ? emptyShotSpecFromShot(shot) : null);
      submitted.push(shotId);
      shaByShot[shotId] = candidate.asset_sha256;
      images.push({
        shot_id: shotId,
        title: String((shot && (shot.label || shot.role_id)) || "图片任务").slice(0, 200),
        purpose: spec ? String(spec.purpose || "").slice(0, 500) : "",
        keep_items: spec ? spec.keep.slice(0, 8) : [],
        allow_changes: spec ? spec.change_allowed.slice(0, 8) : [],
        image: {
          media_type: candidate.media_type || "image/png",
          sha256: candidate.asset_sha256,
          data_base64: await blobToBase64(asset.blob),
        },
      });
    }
    return {
      reason: null, requested: requested, submitted: submitted, shaByShot: shaByShot,
      request: {
        images: images,
        platform: ANALYZE_PLATFORM,
        locale: ANALYZE_LOCALE,
        style_summary: snapshot.styleSummary,
        product_facts: snapshot.productFacts,
      },
    };
  }

  /** Deterministic checks are local. Only the explicit AI action transmits the frozen adopted suite. */
  /** Deterministic checks are local. Only the explicit AI action transmits the frozen adopted suite.
   * @param {{ai?: boolean}} [options]
   * @returns {Promise<{skipped?: boolean, reason?: string, failed?: boolean, message?: string, ok?: boolean, summary?: string, vlm?: string}|undefined>}
   */
  async function runSuiteReview({ ai = false } = {}) {
    const action = beginAction();
    if (!action.projectId) return { skipped: true, reason: "no_project" };
    if (suiteRunInFlight) return { skipped: true, reason: "in_flight" };
    if (!suitePlan) return { failed: true, reason: "no_plan", message: "还没有套图方案。" };
    if (ai && (!capabilities?.suite_review?.provider || capabilities.suite_review.provider.configured === false)) {
      modelSettings.open("review");
      return { failed: true, reason: "configuration_missing" };
    }
    const requestHeaders = modelSettings.headers("review");
    const snapshot = {
      suitePlan, styleSpec, shotSpecsById: suiteShotSpecsById(),
      context: suiteContext(), factsById: suiteFactsById(),
      sellingPoints: [...(intake.selling_points || [])],
      shots: shotSummariesNow(), selections: /** @type {Record<string, string|null>} */ (Object.fromEntries(
        Object.entries(suiteSelectionMap()).map(([shotId, record]) => [shotId, record.candidate_id]))),
      selectionStates: /** @type {Record<string, SelectionState>} */ (Object.fromEntries(shotSummariesNow().map((/** @type {{shot_id: string}} */ shot) => [shot.shot_id, selectionStateOf(shot.shot_id)]))),
      candidatesByShot: suiteCandidatesByShot(), attemptsByShot: suiteAttemptsByShot(),
      reportsByCandidate: suiteReportsByCandidate(), styleSummary: suiteStyleSummaryText(),
      productFacts: confirmedFactPayloads(), previousReport: suiteReportEntry()?.report || null,
    };
    suiteRunInFlight = true;
    clearError(elements.suiteReviewError);
    renderSuitePanel();
    try {
      const at = new Date().toISOString();
      const fingerprints = suiteFingerprintsNow();
      const selectionMap = snapshot.selections;
      const prepared = ai ? await suiteVlmRequestFor(snapshot, action.projectId)
        : { reason: "not_run", requested: /** @type {string[]} */ ([]), submitted: /** @type {string[]} */ ([]), shaByShot: /** @type {Record<string, string>} */ ({}), request: /** @type {unknown} */ (null) };
      if (!action.alive()) return { skipped: true, reason: "stale_session" };
      let envelope = null;
      let reason = prepared.reason;
      if (prepared.request) {
        try {
          const response = await fetch(SUITE_REVIEW_PATH, {
            method: "POST",
            headers: { "Content-Type": "application/json", ...requestHeaders },
            body: JSON.stringify(prepared.request),
          });
          envelope = await response.json().catch(() => null);
        } catch (error) {
          envelope = null;
        }
        reason = !envelope || typeof envelope !== "object"
          ? "transport" : (envelope.ok === true ? null : "server");
      }
      const vlmRun = {
        envelope: envelope,
        reason: reason || null,
        requested_shot_ids: prepared.requested,
        submitted_shot_ids: prepared.reason ? [] : prepared.submitted,
        asset_sha256_by_shot: prepared.reason ? {} : prepared.shaByShot,
      };
      const report = await assembleSuiteReview({
        selectionSet: fingerprints.selectionSet,
        suitePlan: snapshot.suitePlan,
        styleSpec: snapshot.styleSpec,
        shotSpecsById: snapshot.shotSpecsById,
        context: snapshot.context,
        factsById: snapshot.factsById,
        sellingPoints: snapshot.sellingPoints,
        shots: snapshot.shots,
        selections: selectionMap,
        candidatesByShot: snapshot.candidatesByShot,
        attemptsByShot: snapshot.attemptsByShot,
        reportsByCandidate: snapshot.reportsByCandidate,
        previousReport: snapshot.previousReport,
        readBytes: async (/** @type {string} */ sha) => {
          if (!action.projectId) return null;
          const asset = await repository.assets.get(action.projectId, sha);
          return asset && asset.blob instanceof Blob
            ? new Uint8Array(await asset.blob.arrayBuffer()) : null;
        },
        digest: sha256Hex,
        vlmRun: ai ? vlmRun : null,
        at: at,
      });
      const saved = await repository.documents.save(action.projectId, {
        kind: SUITE_REVIEW_KIND, documentId: SUITE_REVIEW_DOCUMENT_ID, payload: report,
      });
      const version = saved.version;
      if (action.alive()) {
        suiteReports.set(SUITE_REVIEW_DOCUMENT_ID, { report: report, version: version });
      }
      return {
        ok: true,
        summary: suiteReviewSummaryText(report),
        vlm: report.vlm ? report.vlm.outcome : "not_run",
      };
    } catch (error) {
      if (action.alive()) showError(elements.suiteReviewError,
        errorMessageOf(error, "整套检查没有保存；之前的报告保留。"));
      return {
        failed: true, reason: "assemble_invalid",
        message: errorMessageOf(error, "整套检查无法完成。"),
      };
    } finally {
      if (action.alive()) {
        suiteRunInFlight = false;
        renderSuitePanel();
        requestDeliveryGateRefresh();
      }
    }
  }

  /**
   * @param {string} shotId
   * @returns {void}
   */
  function jumpToReviewShot(shotId) {
    stageShell.select("review");
    if (!elements.reviewList) return;
    const row = /** @type {HTMLElement|null} */ (elements.reviewList.querySelector('.review-card[data-shot-id="' + shotId + '"]'));
    if (!row) return;
    row.scrollIntoView({ block: "center" });
    const button = /** @type {HTMLButtonElement|null} */ (row.querySelector("button"));
    if (button) button.focus({ preventScroll: true });
  }

  /** 门禁：整套一致性阻断不属于任何一张图，定位回审核阶段的整套检查运行按钮。 */
  /** 门禁：整套一致性阻断不属于任何一张图，定位回审核阶段的整套检查运行按钮。
   * @returns {void}
   */
  function jumpToSuiteCheck() {
    stageShell.select("review");
    if (!elements.suiteReviewRun) return;
    elements.suiteReviewRun.scrollIntoView({ block: "center" });
    elements.suiteReviewRun.focus({ preventScroll: true });
  }

  /** 整套一致性分区：状态行 + 运行按钮 + 按严重度分组的发现（每条可跳到对应图行）。 */
  /** 整套一致性分区：状态行 + 运行按钮 + 按严重度分组的发现（每条可跳到对应图行）。
   * @returns {void}
   */
  function renderSuitePanel() {
    if (!elements.suiteReviewStatus || !elements.suiteReviewFindings) return;
    const entry = suiteReportEntry();
    const report = entry ? entry.report : null;
    const current = report && projectId
      ? suiteReviewIsCurrent(report, suiteFingerprintsNow()) : false;
    elements.suiteReviewRun.disabled = !projectId || !suitePlan || suiteRunInFlight;
    elements.suiteReviewRun.textContent = suiteRunInFlight ? "检查中…" : "运行本地确定性检查";
    elements.suiteAiReviewRun.disabled = !projectId || !suitePlan || suiteRunInFlight
      || !capabilities?.suite_review?.provider || capabilities.suite_review.provider.configured === false;
    elements.suiteAiReviewRun.textContent = "AI 复核当前采用套图（可选）";
    if (!report) {
      elements.suiteReviewStatus.textContent = projectId && suitePlan
        ? "尚未运行整套检查。"
        : "先在「方案」生成套图方案，再运行整套检查。";
      elements.suiteReviewNote.textContent = "";
    } else if (!current) {
      elements.suiteReviewStatus.textContent = "整套检查已过期：选择或输入在报告之后发生了变化，请重新运行。"
        + " 上一版：" + suiteReviewSummaryText(report);
      elements.suiteReviewNote.textContent = "";
    } else {
      elements.suiteReviewStatus.textContent = suiteReviewSummaryText(report);
      const vlm = report.vlm && report.vlm.outcome === "checked" ? report.vlm : null;
      elements.suiteReviewNote.textContent = vlm
        ? ("视觉复核：" + String(vlm.model_id || vlm.provider_id || "已完成")
           + (vlm.checked_at ? " · " + vlm.checked_at : ""))
        : "未做 AI 复核；当前确定性检查与人工采用仍是交付硬门。";
    }
    elements.suiteReviewFindings.innerHTML = "";
    if (!report) return;
    appendSuiteFindings(elements.suiteReviewFindings, report);
  }

  /**
   * 整套发现的单一投影（审核阶段与交付阶段共用，避免两套写法 / 两个事实来源）。
   * 只读传入的报告，重排成「严重度分组 + 逐条定位」；不写任何状态。
   */
  /**
   * @param {HTMLElement} container
   * @param {SuiteReviewReport} report
   * @returns {void}
   */
  function appendSuiteFindings(container, report) {
    const findings = Array.isArray(report.findings) ? report.findings : [];
    const shown = findings.filter((item) => item && item.severity !== "PASS");
    if (shown.length === 0) {
      container.append(createElement("p", {
        className: "meta", text: "没有需要人工处理的整套发现。",
      }));
    }
    for (const severity of REVIEW_SEVERITY_ORDER) {
      const group = shown.filter((item) => item.severity === severity);
      if (!group.length) continue;
      container.append(createElement("p", {
        className: "meta suite-group", text: COMPARE_SEVERITY_TEXT[severity] || severity,
      }));
      for (const finding of group) {
        const row = createElement("div", {
          className: "suite-finding",
          attrs: { "data-rule-id": finding.rule_id, "data-severity": finding.severity },
        });
        row.append(createElement("span", {
          className: "badge " + (/** @type {Record<string, string>} */ (SEVERITY_BADGE)[finding.severity] || "is-review-unknown"),
          text: COMPARE_SEVERITY_TEXT[finding.severity] || finding.severity,
        }));
        row.append(createElement("span", {
          className: "name", text: String(finding.title || finding.rule_id),
        }));
        row.append(createElement("p", { className: "meta", text: localizeShotIds(finding.detail) }));
        for (const shotId of (Array.isArray(finding.affected_shot_ids) ? finding.affected_shot_ids : [])) {
          const jump = createElement("button", {
            text: "定位：" + shotLabelOf(shotId), attrs: { type: "button", "data-shot-id": shotId },
          });
          jump.addEventListener("click", () => { jumpToReviewShot(shotId); });
          row.append(jump);
        }
        container.append(row);
      }
    }
    const passCount = findings.filter((item) => item && item.severity === "PASS").length;
    if (passCount > 0) {
      container.append(createElement("p", {
        className: "meta", text: "另 " + passCount + " 项确定性检查通过（细节在候选审核清单里）。",
      }));
    }
  }

  /* -------------------------------------------------- 交付门禁与交付包（V2.6.2） */

  /** 读取已采用候选的字节（IndexedDB Blob → Uint8Array）；缺失返回 null。 */
  /** 读取已采用候选的字节（IndexedDB Blob → Uint8Array）；缺失返回 null。
   * @param {string} sha256
   * @param {string|null} [pid]
   * @returns {Promise<Uint8Array|null>}
   */
  async function readCandidateBytes(sha256, pid = projectId) {
    if (!pid) return null;
    const asset = await repository.assets.get(pid, sha256);
    return asset && asset.blob instanceof Blob
      ? new Uint8Array(await asset.blob.arrayBuffer()) : null;
  }
  /** 交付门禁的输入投影：与整套检查共用同一批只读投影，不重做第二套测量。 */
  /** 交付门禁的输入投影：与整套检查共用同一批只读投影，不重做第二套测量。
   * @param {string|null} [pid]
   * @returns {Parameters<typeof evaluateDeliveryGate>[0]}
   */
  function deliveryGateInputs(pid = projectId) {
    const suiteEntry = suiteReportEntry();
    return /** @type {Parameters<typeof evaluateDeliveryGate>[0]} */ ({
      shots: shotSummariesNow().map((shot) => ({
        shot_id: shot.shot_id, required: shot.required === true,
      })),
      selections: suiteSelectionMap(),
      candidatesByShot: suiteCandidatesByShot(),
      reportsByCandidate: suiteReportsByCandidate(),
      attemptsByShot: suiteAttemptsByShot(),
      suiteReport: suiteEntry ? suiteEntry.report : null,
      suiteFingerprints: suiteFingerprintsNow(),
      acknowledgements: [...acknowledgements.values()].map((entry) => entry.record),
      readBytes: (/** @type {string} */ sha) => readCandidateBytes(sha, pid),
      digest: sha256Hex,
    });
  }

  /** 去抖重算：任何影响交付的写入之后都走这里；界面只能读 deliveryGateState。 */
  /** 去抖重算：任何影响交付的写入之后都走这里；界面只能读 deliveryGateState。
   * @returns {void}
   */
  function requestDeliveryGateRefresh() {
    clearTimeout(deliveryGateTimer ?? undefined);
    deliveryGateTimer = setTimeout(() => {
      deliveryGateTimer = null;
      refreshDeliveryGate().catch(() => {});
    }, 60);
  }

  /** 门禁结果只保存在内存里：检查失败不写任何存储，也不产生交付记录。 */
  /** 门禁结果只保存在内存里：检查失败不写任何存储，也不产生交付记录。
   * @returns {Promise<void>}
   */
  async function refreshDeliveryGate() {
    const action = beginAction();
    if (!action.projectId) {
      if (action.alive()) {
        deliveryGateState = null;
        renderDeliveryGate();
      }
      return;
    }
    let next = null;
    let failure = null;
    try {
      next = await evaluateDeliveryGate(deliveryGateInputs(action.projectId));
    } catch (error) {
      failure = errorMessageOf(error, "交付门禁无法完成。");
    }
    if (!action.alive()) return;
    deliveryGateState = next
      ? { ...next, failed: false, checked_at: new Date().toISOString() }
      : { failed: true, message: failure, ready_to_export: false,
          findings: [], blocking: [], unknowns: [], unresolved_unknowns: [] };
    renderDeliveryGate();
  }

  /** 门禁展示顺序：阻断优先，PASS 收在最后；不改判定，只改阅读顺序。 */
  const GATE_SEVERITY_RANK = Object.freeze({
    BLOCK: 0, HIGH_RISK: 1, WARNING: 2, UNKNOWN: 3, PASS: 4,
  });

  /** 门禁逐条：严重度徽标 + 说明 + 受影响 Shot 的定位入口。 */
  /** 门禁逐条：严重度徽标 + 说明 + 受影响 Shot 的定位入口。
   * @returns {void}
   */
  function renderDeliveryFindings() {
    const state = deliveryGateState;
    const findings = state && Array.isArray(state.findings) ? state.findings : [];
    if (!findings.length) {
      elements.deliveryGate.append(createElement("p", {
        className: "meta",
        text: state && state.failed
          ? ("门禁检查失败：" + (state.message || "未知错误"))
          : "正在核对交付门禁…",
      }));
      return;
    }
    const ordered = findings.slice().sort((left, right) =>
      (GATE_SEVERITY_RANK[left.severity] === undefined ? 9 : GATE_SEVERITY_RANK[left.severity])
      - (GATE_SEVERITY_RANK[right.severity] === undefined ? 9 : GATE_SEVERITY_RANK[right.severity]));
    for (const item of ordered) {
      const passed = item.severity === "PASS";
      const row = createElement("div", {
        className: "gate-finding" + (passed ? " is-pass" : ""),
        attrs: { "data-rule-id": item.rule_id, "data-severity": item.severity },
      });
      row.append(createElement("span", {
        className: "badge " + (/** @type {Record<string, string>} */ (SEVERITY_BADGE)[item.severity] || "is-review-unknown"),
        text: COMPARE_SEVERITY_TEXT[item.severity] || item.severity,
      }));
      row.append(createElement("span", { className: "name", text: String(item.title || item.rule_id) }));
      // 通过项压成一行（信息不减、占位减半）；阻断项保留独立说明行便于逐条处理。
      row.append(createElement(passed ? "span" : "p", {
        className: "meta", text: localizeShotIds(item.detail),
      }));
      // Unknown 的处置入口就是下面的「确认已知悉」；这里不再给会误导的跳图按钮。
      const jumpable = !passed && item.rule_id !== "export.unknown_acknowledged";
      for (const shotId of (jumpable && Array.isArray(item.affected_shot_ids)
        ? item.affected_shot_ids : [])) {
        const jump = createElement("button", {
          text: "去处理：" + shotLabelOf(shotId), attrs: { type: "button", "data-shot-id": shotId },
        });
        jump.addEventListener("click", () => { jumpToReviewShot(shotId); });
        row.append(jump);
      }
      // 整套一致性阻断不是某一张图的问题：给「去运行整套检查」把使用者送回审核阶段的运行按钮。
      if (!passed && item.rule_id === "export.suite_review_current") {
        const jump = createElement("button", {
          text: "去运行整套检查", attrs: { type: "button", "data-suite-action": "run" },
        });
        jump.addEventListener("click", () => { jumpToSuiteCheck(); });
        row.append(jump);
      }
      elements.deliveryGate.append(row);
    }
  }

  /**
   * 交付页的整套检查投影（V2.6.15）：交付是最后决策点，门禁全绿只说明「硬检查通过」，
   * 不代表没有风险 —— 这里复读同一份 suite review 报告（单一权威），把非阻断的
   * 高风险/提醒连同定位入口摆到导出按钮前面；过期报告如实说明，阻断仍由门禁负责。
   */
  /**
   * @returns {void}
   */
  function renderDeliverySuite() {
    if (!elements.deliverySuiteStatus || !elements.deliverySuiteFindings) return;
    elements.deliverySuiteStatus.textContent = "";
    elements.deliverySuiteFindings.innerHTML = "";
    const entry = suiteReportEntry();
    const report = entry ? entry.report : null;
    if (!report) {
      elements.deliverySuiteStatus.textContent = projectId && suitePlan
        ? "尚未运行整套检查；交付门禁会在缺失或不当前时阻断导出。"
        : "先在「方案」生成套图方案，再运行整套检查。";
      return;
    }
    const current = projectId ? suiteReviewIsCurrent(report, suiteFingerprintsNow()) : false;
    elements.deliverySuiteStatus.textContent = current
      ? suiteReviewSummaryText(report)
      : ("整套检查已过期：选择或输入在报告之后发生了变化，请回审核阶段重新运行。上一版："
         + suiteReviewSummaryText(report));
    appendSuiteFindings(elements.deliverySuiteFindings, report);
  }

  /** 待确认 Unknown：每条一个「确认已知悉」按钮；确认是 append-only 记录，不改写报告。 */
  /** 待确认 Unknown：每条一个「确认已知悉」按钮；确认是 append-only 记录，不改写报告。
   * @returns {void}
   */
  function renderDeliveryUnknowns() {
    if (!elements.deliveryUnknowns) return;
    elements.deliveryUnknowns.innerHTML = "";
    const state = deliveryGateState;
    const unknowns = state && Array.isArray(state.unknowns) ? state.unknowns : [];
    if (!unknowns.length) return;
    elements.deliveryUnknowns.append(createElement("p", {
      className: "meta", text: "未知项（模型无法判定）：逐条确认已知悉后才允许交付。",
    }));
    for (const unknown of unknowns) {
      const row = createElement("div", {
        className: "gate-unknown",
        attrs: { "data-rule-id": unknown.rule_id, "data-target-id": unknown.target_id },
      });
      row.append(createElement("span", { className: "name", text: String(unknown.title || unknown.rule_id) }));
      row.append(createElement("p", { className: "meta", text: String(unknown.detail || "") }));
      const button = createElement("button", {
        text: unknown.acknowledged === true ? "已确认" : "确认已知悉", attrs: { type: "button" },
      });
      button.disabled = unknown.acknowledged === true;
      button.addEventListener("click", () => { acknowledgeUnknown(unknown, button); });
      row.append(button);
      elements.deliveryUnknowns.append(row);
    }
  }

  /** 确认只追加：document_id 由未知项身份派生，重复确认只新增版本。 */
  /** 确认只追加：document_id 由未知项身份派生，重复确认只新增版本。
   * @param {UnknownItem} unknown
   * @param {HTMLButtonElement} button
   * @returns {Promise<void>}
   */
  async function acknowledgeUnknown(unknown, button) {
    if (!projectId) return;
    const action = beginAction();
    if (!action.projectId) return;
    clearError(elements.deliverError);
    button.disabled = true;
    try {
      const at = new Date().toISOString();
      const record = buildAcknowledgement({ unknown: unknown, at: at });
      const documentId = acknowledgementDocumentIdOf(record);
      const saved = await repository.documents.save(action.projectId, {
        kind: REVIEW_ACK_KIND, documentId: documentId, payload: record,
      });
      if (!action.alive()) return;
      acknowledgements.set(documentId, { record: record, version: saved.version });
      await refreshDeliveryGate();
      if (!action.alive()) return;
      elements.deliverStatus.textContent = "已记录「已知悉」（append-only，不作为通过证据）。";
    } catch (error) {
      if (action.alive()) {
        button.disabled = false;
        showError(elements.deliverError, errorMessageOf(error, "确认没有保存，请重试。"));
      }
    }
  }

  /** 最近一次交付包结果：刷新后仍有记录（无 blob 时只显示身份，不伪装可下载）。 */
  /**
   * @returns {void}
   */
  function renderDeliveryResult() {
    if (!elements.deliverResult) return;
    elements.deliverResult.innerHTML = "";
    if (!deliveryRecord) {
      elements.deliverResult.hidden = true;
      return;
    }
    elements.deliverResult.hidden = false;
    elements.deliverResult.append(createElement("p", {
      className: "meta",
      text: "最近一次交付包：" + deliveryRecord.file_name + "（"
        + Math.round(deliveryRecord.byte_size / 1024) + " KB）",
    }));
    appendTech(elements.deliverResult,
      ["sha256 " + String(deliveryRecord.sha256).slice(0, 16) + "…"]);
    if (deliveryRecord.url) {
      elements.deliverResult.append(createElement("a", {
        text: "下载交付包",
        attrs: { href: deliveryRecord.url, download: deliveryRecord.file_name },
      }));
    }
  }

  /** 交付阶段：逐图采用状态 + 门禁清单 + Unknown 确认 + 生成交付包入口。 */
  /**
   * @returns {void}
   */
  function renderDeliveryGate() {
    if (!elements.deliveryGate) return;
    elements.deliveryGate.innerHTML = "";
    const shots = shotSummariesNow();
    for (const shot of shots) {
      const state = selectionStateOf(shot.shot_id);
      const row = createElement("div", {
        className: "gate-row", attrs: { "data-shot-id": shot.shot_id, "data-selection-state": state },
      });
      row.append(createElement("span", { className: "name", text: shot.label }));
      row.append(createElement("span", {
        className: "badge " + (state === "current" ? "is-adopted" : (state === "stale" ? "is-review-warn" : "is-empty")),
        text: state === "current" ? "已采用" : (state === "stale" ? "已采用（已过期）" : "未采用"),
      }));
      row.append(createElement("span", {
        className: "meta", text: shot.required === true ? "必需图" : "可选图",
      }));
      if (state !== "current") {
        const jump = createElement("button", { text: "去审核", attrs: { type: "button" } });
        jump.addEventListener("click", () => { stageShell.select("review"); });
        row.append(jump);
      }
      elements.deliveryGate.append(row);
    }
    renderDeliveryFindings();
    renderDeliverySuite();
    renderDeliveryUnknowns();
    renderDeliveryResult();
    const requiredShots = shots.filter((shot) => shot.required === true);
    const pending = requiredShots.filter((shot) => selectionStateOf(shot.shot_id) !== "current");
    const state = deliveryGateState;
    elements.deliverExport.disabled = !(state && state.ready_to_export === true) || deliveryInFlight;
    elements.deliverStatus.textContent = !shots.length
      ? "还没有套图方案。"
      : (deliveryInFlight
        ? "正在生成交付包…"
        : (pending.length
          ? "还差 " + pending.length + " 张必需图没有当前有效的采用。"
          : (!state || state.failed || !state.findings.length
            ? "正在核对交付门禁…"
            : (state.ready_to_export
              ? "交付门禁通过：可以生成交付包（只包含已采用的候选）。"
              : "交付门禁未通过：" + state.blocking.length + " 条阻断，逐条处理后才能生成。"))));
  }
  /**
   * @param {{exported_at?: string}} manifest
   * @returns {string}
   */
  function stageFileName(manifest) {
    const safe = ((project && project.name) || "project")
      .replace(/[\\/:*?"<>|\s]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "project";
    const stamp = String(manifest.exported_at || new Date().toISOString())
      .replace(/[-:]/g, "").replace("T", "-").slice(0, 13);
    return safe + "-" + stamp + ".zip";
  }

  /**
   * @returns {Promise<void>}
   */
  async function handleExportFromWorkspace() {
    const action = beginAction();
    if (!action.projectId) return;
    clearError(elements.deliverError);
    elements.deliverStatus.textContent = "正在打包完整项目…";
    try {
      const { bytes, manifest } = await exportProjectPackage(repository, action.projectId);
      if (!action.alive()) return;
      const blob = new Blob([bytes.slice()], { type: "application/zip" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = stageFileName(manifest);
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10_000);
      elements.deliverStatus.textContent = "已导出项目包（含完整历史，可在别的浏览器导入）。";
    } catch (error) {
      if (action.alive()) {
        elements.deliverStatus.textContent = "";
        showError(elements.deliverError, errorMessageOf(error, "导出失败，请重试。"));
      }
    }
  }

  /* ------------------------------------------------------ 交付包生成（V2.6.2） */

  /** 交付包 manifest：选择与输入指纹 + 每图身份（含 PromptVersion 与 Attempt）。 */
  /**
   * @typedef {object} DeliveryFileRow
   * @property {string} path
   * @property {string} shot_id
   * @property {string} shot_label
   * @property {string} candidate_id
   * @property {string} attempt_action_id
   * @property {string} attempt_state
   * @property {string} asset_sha256
   * @property {string} media_type
   * @property {number} byte_size
   * @property {number|null} prompt_version
   * @property {string|null} prompt_hash
   */
  /**
   * @param {{at: string, files: DeliveryFileRow[], selectionFingerprint: string|null, inputsFingerprint: string|null}} args
   * @returns {unknown}
   */
  function buildDeliveryManifest({ at, files, selectionFingerprint, inputsFingerprint }) {
    return {
      schema_version: 1,
      contract_version: EXPORT_GATE_CONTRACT_VERSION,
      project_id: projectId,
      project_name: (project && project.name) || "",
      exported_at: at,
      selection_fingerprint: selectionFingerprint,
      inputs_fingerprint: inputsFingerprint,
      ai_review: suiteReviewStatusOf(suiteReportEntry()?.report),
      images: files.map((file) => ({
        shot_id: file.shot_id,
        shot_label: file.shot_label,
        candidate_id: file.candidate_id,
        attempt_action_id: file.attempt_action_id,
        attempt_state: file.attempt_state,
        asset_sha256: file.asset_sha256,
        media_type: file.media_type,
        byte_size: file.byte_size,
        file: file.path,
        prompt_version: file.prompt_version,
        prompt_hash: file.prompt_hash,
        ai_review: suiteReviewStatusOf(generation.reviewReportOf(file.candidate_id)?.report),
      })),
    };
  }

  /** 交付包 checks：当前门禁发现 + 每张采用候选的单图报告投影 + Unknown 确认记录。 */
  /**
   * @param {{at: string, gate: DeliveryGateResult, files: Array<{candidate_id: string, shot_id: string}>}} args
   * @returns {unknown}
   */
  function buildDeliveryChecks({ at, gate, files }) {
    const suiteEntry = suiteReportEntry();
    const countsOf = (/** @type {ReviewFinding[]} */ findings) => {
      const counts = /** @type {{block: number, warning: number, unknown: number, pass: number}} */ ({ block: 0, warning: 0, unknown: 0, pass: 0 });
      findings.forEach((item) => {
        if (!item || typeof item.severity !== "string") return;
        const key = /** @type {string} */ (item.severity.toLowerCase());
        if (Object.prototype.hasOwnProperty.call(counts, key)) counts[/** @type {"block"|"warning"|"unknown"|"pass"} */ (key)] += 1;
      });
      return counts;
    };
    return {
      schema_version: 1,
      contract_version: EXPORT_GATE_CONTRACT_VERSION,
      generated_at: at,
      gate_status: gate.status,
      findings: gate.findings.map((item) => ({
        rule_id: item.rule_id, rule_version: item.rule_version, severity: item.severity,
        title: item.title, detail: item.detail, measured: item.measured,
        affected_shot_ids: [...item.affected_shot_ids],
      })),
      per_shot: files.map((file) => {
        const entry = generation.reviewReportOf(file.candidate_id);
        const findings = entry && entry.report && Array.isArray(entry.report.findings)
          ? entry.report.findings : [];
        return {
          shot_id: file.shot_id,
          candidate_id: file.candidate_id,
          report_version: entry ? entry.version : null,
          ai_review: suiteReviewStatusOf(entry?.report),
          counts: countsOf(findings),
          findings: findings.filter((/** @type {ReviewFinding} */ item) => item && item.severity !== "PASS").map((/** @type {ReviewFinding} */ item) => ({
            rule_id: item.rule_id, severity: item.severity,
            title: item.title, detail: item.detail,
          })),
        };
      }),
      suite_review: suiteEntry ? {
        document_id: SUITE_REVIEW_DOCUMENT_ID,
        version: suiteEntry.version,
        ai_review: suiteReviewStatusOf(suiteEntry.report),
        selection_fingerprint: suiteEntry.report.selection_fingerprint,
        inputs_fingerprint: suiteEntry.report.inputs_fingerprint,
        counts: countsOf(Array.isArray(suiteEntry.report.findings) ? suiteEntry.report.findings : []),
      } : null,
      acknowledgements: [...acknowledgements.values()].map((entry) => ({
        document_id: entry.record.target_id,
        rule_id: entry.record.rule_id,
        target_kind: entry.record.target_kind,
        shot_ids: Array.isArray(entry.record.shot_ids) ? [...entry.record.shot_ids] : [],
        acknowledged_at: entry.record.acknowledged_at,
      })),
    };
  }

  /** 交付包 README：直接给人看的小抄（不替代 manifest/checks）。 */
  /**
   * @param {{at: string, files: DeliveryFileRow[]}} args
   * @returns {string}
   */
  function buildDeliveryReadme({ at, files }) {
    const lines = [
      "商品套图交付包",
      "",
      "项目：" + ((project && project.name) || "(未命名)"),
      "生成时间：" + at,
      "包含图片：" + files.length + " 张（每张一个已采用候选）",
      "",
      "清单：",
    ];
    files.forEach((file) => {
      lines.push("- " + file.shot_label + "：" + file.path
        + "（candidate " + file.candidate_id + " · sha256 "
        + String(file.asset_sha256).slice(0, 12) + "…）");
    });
    lines.push("");
    lines.push("manifest.json 记录每张图的来源与指纹；checks.json 记录门禁与审核发现。");
    lines.push("本包只包含已采用的候选；未采用候选与完整历史请用「导出项目包」。");
    return lines.join("\n");
  }

  /** 生成交付包：门禁通过才打包；任何一步失败都不写 export_record。 */
  /**
   * @returns {Promise<void>}
   */
  async function handleDeliverExport() {
    if (!projectId || deliveryInFlight) return;
    const action = beginAction();
    clearError(elements.deliverError);
    deliveryInFlight = true;
    renderDeliveryGate();
    try {
      await refreshDeliveryGate();
      if (!action.alive()) return;
      const state = deliveryGateState;
      if (!state || state.failed || state.ready_to_export !== true || !("status" in state)) {
        showError(elements.deliverError, state && state.failed
          ? ("门禁检查失败：" + (state.message || "未知错误"))
          : "交付门禁未通过：先处理阻断项并确认 Unknown。");
        elements.deliverStatus.textContent = "交付门禁未通过，没有生成交付包。";
        return;
      }
      const selectionMap = /** @type {Record<string, string>} */ (Object.fromEntries(
        Object.entries(suiteSelectionMap()).map(([shotId, record]) => [shotId, record.candidate_id])));
      const images = /** @type {Array<{shot_id: string, candidate_id: string, media_type: string, bytes: Uint8Array}>} */ ([]);
      const files = /** @type {DeliveryFileRow[]} */ ([]);
      for (const shot of shotSummariesNow()) {
        if (!action.alive()) return;
        const candidateId = selectionMap[shot.shot_id];
        if (!candidateId) continue;
        const candidate = candidatePayloadsOf(shot.shot_id)
          .find((/** @type {CandidateRecord} */ item) => item && item.candidate_id === candidateId) || null;
        if (!candidate) {
          if (action.alive()) {
            showError(elements.deliverError, shot.label + " 的选择指向的候选不存在，不能打包。");
            elements.deliverStatus.textContent = "交付包未生成。";
          }
          return;
        }
        const bytes = await readCandidateBytes(candidate.asset_sha256, action.projectId);
        if (!bytes) {
          if (action.alive()) {
            showError(elements.deliverError, shot.label + " 的候选字节缺失，不能打包。");
            elements.deliverStatus.textContent = "交付包未生成。";
          }
          return;
        }
        const mediaType = candidate.media_type || "image/png";
        images.push({
          shot_id: shot.shot_id, candidate_id: candidateId,
          media_type: mediaType, bytes: bytes,
        });
        // B01/RC16：manifest 的 Prompt 溯源必须读被采用候选原 action Attempt 冻结的
        // prompt{version,hash}，不读当前编辑头 promptRecordOf。旧候选 + 新编译头并存时，
        // 若仍取当前头，同一 candidate/action/asset 会被记下错误的当前 Prompt 版本。
        const attemptRecord = attemptsByActionId()[candidate.action_id] || null;
        const frozenPrompt = attemptRecord && attemptRecord.prompt ? attemptRecord.prompt : null;
        files.push({
          shot_id: shot.shot_id, shot_label: shot.label,
          candidate_id: candidateId, attempt_action_id: candidate.action_id,
          attempt_state: attemptRecord ? attemptRecord.state : "",
          asset_sha256: candidate.asset_sha256, media_type: mediaType,
          byte_size: bytes.length,
          path: deliveryImagePathOf({
            shotId: shot.shot_id, candidateId: candidateId, mediaType: mediaType,
          }),
          prompt_version: frozenPrompt ? frozenPrompt.version : null,
          prompt_hash: frozenPrompt ? frozenPrompt.hash : null,
        });
      }
      if (!images.length) {
        showError(elements.deliverError, "没有可交付的已采用候选。");
        elements.deliverStatus.textContent = "交付包未生成。";
        return;
      }
      const at = new Date().toISOString();
      const fingerprints = suiteFingerprintsNow();
      const manifest = buildDeliveryManifest({
        at: at, files: files,
        selectionFingerprint: fingerprints.selectionFingerprint,
        inputsFingerprint: fingerprints.inputsFingerprint,
      });
      const checks = buildDeliveryChecks({ at: at, gate: state, files: files });
      const readme = buildDeliveryReadme({ at: at, files: files });
      const entries = buildDeliveryEntries({
        images: images, manifest: manifest, checks: checks, readme: readme,
      });
      const zipBytes = buildZip(entries, { modifiedAt: new Date(at) });
      const zipSha256 = await sha256Hex(zipBytes);
      const projectName = (project && project.name) || "";
      if (!action.projectId || !projectName) throw new Error("缺少项目上下文，交付包未生成。");
      const record = buildExportRecord({
        projectId: action.projectId, projectName: projectName,
        zipSha256: zipSha256, zipBytes: zipBytes.length, entries: entries,
        gate: state,
        selectionFingerprint: fingerprints.selectionFingerprint,
        inputsFingerprint: fingerprints.inputsFingerprint,
        includedShotIds: images.map((/** @type {{shot_id: string}} */ item) => item.shot_id), at: at,
      });
      await repository.documents.save(action.projectId, {
        kind: EXPORT_RECORD_KIND,
        documentId: exportRecordDocumentIdOf({ at: at, zipSha256: zipSha256 }),
        payload: record,
      });
      if (!action.alive()) return;
      const url = URL.createObjectURL(new Blob([zipBytes.slice()], { type: "application/zip" }));
      objectUrls.push(url);
      deliveryRecord = {
        file_name: deliveryFileName({ projectName: projectName, at: at }),
        byte_size: zipBytes.length, sha256: zipSha256, at: at, url: url,
      };
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = deliveryRecord.file_name;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      elements.deliverStatus.textContent = "已生成交付包（" + images.length
        + " 张图；记录已追加，不覆盖历史）。";
    } catch (error) {
      if (action.alive()) {
        elements.deliverStatus.textContent = "交付包未生成。";
        showError(elements.deliverError, errorMessageOf(error, "生成交付包失败，请重试。"));
      }
    } finally {
      if (action.alive()) {
        deliveryInFlight = false;
        renderDeliveryGate();
      }
    }
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
    renderIntake();
    renderAnalyze();
    renderSlots();
    renderSuite();
    renderStyleSpec();
    renderShotSpecs();
    renderPrompts();
    renderConfirm();
    renderAttempts();
    renderHeaderText(project);
    refreshDerived();
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
      node.addEventListener("input", scheduleDraftSave);
    }
    elements.intakeSave.addEventListener("click", () => {
      saveIntakeNow()
        .then(() => deriveAndApplyState())
        .then(() => { renderAnalyze(); renderHeaderText(project); })
        .catch(handleInternalError);
    });
    elements.analyzeRun.addEventListener("click", () => { runAnalyze(); });
    elements.analyzeNewAfterUnknown.addEventListener("click", () => { void runAnalyze({ allowNewAfterUnknown: true }); });
    elements.manualFacts.addEventListener("click", async () => {
      const action = beginAction();
      try {
        await saveIntakeNow();
        if (!action.alive()) return;
        await prepareManualFacts();
        if (action.alive()) stageShell.select("understand", { focusHeading: true });
      } catch (error) { if (action.alive()) handleInternalError(error); }
    });
    elements.slotsToggle.addEventListener("click", () => {
      showAll = !showAll;
      renderSlots();
    });
    elements.slotAddSave.addEventListener("click", () => { handleAddSlot(); });
    elements.suiteSeed.addEventListener("click", () => {
      handleSuiteOp(() => seedSuitePlan(suiteContext()));
    });
    elements.suiteAddTemplate.addEventListener("click", () => {
      handleSuiteOp(() => addShotFromTemplate(
        suitePlan, elements.suiteTemplate.value, { context: suiteContext() }));
    });
    elements.suiteTemplate.addEventListener("change", () => {
      updateTemplateHint(recommendPlan(suiteContext()));
    });
    elements.suiteCustomToggle.addEventListener("click", () => {
      const opening = elements.suiteCustomPanel.hidden;
      elements.suiteCustomPanel.hidden = !opening;
      elements.suiteCustomToggle.setAttribute("aria-expanded", String(opening));
    });
    elements.suiteCustomSave.addEventListener("click", () => { handleSuiteAddCustom(); });
    elements.styleSave.addEventListener("click", () => { handleSaveStyle(); });
    elements.styleRestore.addEventListener("click", () => { handleRestoreStyle(); });
    elements.confirmAction.addEventListener("click", () => { handleConfirmGeneration(); });
    elements.batchStop.addEventListener("click", () => { generation.stopBatch(); });
    elements.batchReconcile.addEventListener("click", () => { generation.reconcileOnce(); });
    elements.batchRetry.addEventListener("click", () => {
      generationMode = "failed_retry"; generationScope = generation.deriveBatch().retry_queue;
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
      const outcome = await generation.reviewCandidate(shotId, candidateId);
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
      if (document.visibilityState === "hidden" && saveTimer !== null) {
        saveIntakeNow().catch(() => {});
      }
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
    elements.deliverProjectPackage.addEventListener("click", () => { handleExportFromWorkspace(); });
    elements.deliverExport.addEventListener("click", () => { handleDeliverExport(); });
    if (elements.suiteReviewRun) {
      elements.suiteReviewRun.addEventListener("click", () => { runSuiteReview(); });
      elements.suiteAiReviewRun.addEventListener("click", () => { void runSuiteReview({ ai: true }); });
    }
  }

  /**
   * @returns {Promise<void>}
   */
  async function loadWorkspace() {
    const action = beginAction();
    const pid = projectId && action.projectId && projectId === action.projectId ? projectId : null;
    if (!pid) return;
    intake = emptyProductInput();
    intakeVersion = 0;
    intakeFingerprint = "";
    slots = new Map();
    lastAnalyze = null;
    analyzeProblems = [];
    suitePlan = null;
    suiteVersion = 0;
    understandingReady = false;
    styleSpec = emptyStyleSpec();
    styleVersion = 0;
    shotSpecs = new Map();
    promptVersions = new Map();
    promptHistory = new Map();
    confirmedQueues = new Map();
    lastPreparationInputs = "";
    confirmRecord = null;
    // V2.R5.1：生成执行侧链/飞行集合/报告全部在 Module 里,loadWorkspace 统一重灌。
    generation.reset();
    suiteReports = new Map();
    suiteRunInFlight = false;
    deliveryGateState = null;
    deliveryInFlight = false;
    deliveryRecord = null;
    acknowledgements = new Map();
    revokePreviewUrls();
    compareShotId = null;
    compareCandidateId = null;
    compareToken += 1;
    reworkDrafts = new Map();
    reworkConfirmations = new Map();
    reworkInFlight = false;
    reworkShotId = null;
    reworkSource = null;
    selections = new Map();
    adoptInFlight = false;
    elements.comparePanel.hidden = true;
    elements.reworkPanel.hidden = true;
    elements.reworkPreviewBox.hidden = true;
    showAll = false;
    interaction = { slotId: null, mode: null };

    const intakeDoc = await repository.documents.getLatest(pid, INTAKE_KIND, INTAKE_DOCUMENT_ID);
    if (!action.alive()) return;
    if (intakeDoc && intakeDoc.payload && typeof intakeDoc.payload === "object") {
      intake = { ...emptyProductInput(), ...intakeDoc.payload };
      if (!Array.isArray(intake.references)) intake.references = [];
      if (!Array.isArray(intake.selling_points)) intake.selling_points = [];
      intakeVersion = intakeDoc.version;
    }
    intakeFingerprint = fingerprintOf(intake);
    const slotDocs = await repository.documents.listLatest(pid, SLOT_KIND);
    if (!action.alive()) return;
    for (const record of slotDocs) {
      if (record.kind === SLOT_KIND && record.payload && typeof record.payload === "object") {
        // 槽位形状以消费边界 checkFactSlot 为准；此处按 fact_slot 文档契约投影。
        slots.set(record.document_id, { slot: /** @type {FactSlot} */ (record.payload), version: record.version });
      }
    }
    const suiteDoc = await repository.documents.getLatest(
      pid, SUITE_KIND, SUITE_PLAN_DOCUMENT_ID);
    if (!action.alive()) return;
    if (suiteDoc && suiteDoc.payload && Array.isArray(suiteDoc.payload.shots)) {
      // 套图计划形状以消费边界 validateSuitePlan 为准；此处按 suite_plan 文档契约投影。
      suitePlan = /** @type {SuitePlan} */ (suiteDoc.payload);
      suiteVersion = suiteDoc.version;
    }
    const styleDoc = await repository.documents.getLatest(
      pid, STYLE_KIND, STYLE_SPEC_DOCUMENT_ID);
    if (!action.alive()) return;
    if (styleDoc && styleDoc.payload && typeof styleDoc.payload === "object") {
      // 风格形状以消费边界 assertStyleSpec 为准；此处按 style_spec 文档契约投影。
      styleSpec = { ...emptyStyleSpec(), .../** @type {Partial<StyleSpec>} */ (styleDoc.payload) };
      styleVersion = styleDoc.version;
    }
    const specDocs = await repository.documents.listLatest(pid, SHOT_SPEC_KIND);
    if (!action.alive()) return;
    for (const record of specDocs) {
      if (record.payload && typeof record.payload === "object") {
        // 单图规格形状以消费边界 assertShotSpec 为准；此处按 shot_spec 文档契约投影。
        shotSpecs.set(record.document_id, { spec: /** @type {ShotSpec} */ (record.payload), version: record.version });
      }
    }
    const promptDocs = await repository.documents.listLatest(pid, PROMPT_KIND);
    if (!action.alive()) return;
    for (const latest of promptDocs) {
      const versions = await repository.documents.listVersions(pid, PROMPT_KIND, latest.document_id);
      if (!action.alive()) return;
      for (const stored of versions) {
        const problems = checkPromptRecord(stored.payload);
        if (problems.length) throw new Error("已保存的 Prompt 无法恢复：" + problems[0].message);
        // 已通过 checkPromptRecord 校验（validation boundary），收窄为 PromptRecord。
        rememberPromptVersion(stored.document_id, { record: /** @type {PromptRecord} */ (stored.payload), version: stored.version });
      }
    }
    const confirmDocs = await repository.documents.listLatest(pid, CONFIRM_KIND);
    if (!action.alive()) return;
    for (const latest of confirmDocs) {
      const versions = await repository.documents.listVersions(pid, CONFIRM_KIND, latest.document_id);
      if (!action.alive()) return;
      for (const stored of versions) {
        const problems = checkConfirmationRecord(stored.payload);
        if (problems.length) throw new Error("已保存的生成授权无法恢复：" + problems[0].message);
        // 已通过 checkConfirmationRecord 校验（validation boundary），收窄为 ConfirmationRecord。
        rememberConfirmation(stored.document_id, { payload: /** @type {ConfirmationRecord} */ (stored.payload), version: stored.version });
      }
    }
    for (const shot of (suitePlan && Array.isArray(suitePlan.shots) ? suitePlan.shots : [])) {
      // 落库套图 shot_id 恒为 string（null 仅预持久草稿，无落库文档可列；此处按落库形状投影）。
      const attemptDocs = await repository.documents.listVersions(pid, ATTEMPT_KIND, /** @type {string} */ (shot.shot_id));
      if (!action.alive()) return;
      generation.loadAttemptChain(shot.shot_id, attemptDocs.slice().reverse()
        // 本工作区经生成 Module 写入的尝试链投影（Module 内按 AttemptRecord 形状消费）。
        .map((record) => ({ record: /** @type {AttemptRecord} */ (record.payload), version: record.version })));
    }
    for (const shot of (suitePlan && Array.isArray(suitePlan.shots) ? suitePlan.shots : [])) {
      const candidateDocs = await repository.documents.listVersions(pid, CANDIDATE_KIND, /** @type {string} */ (shot.shot_id));
      if (!action.alive()) return;
      generation.loadCandidateChain(shot.shot_id, candidateDocs.slice().reverse()
        // 本工作区经生成 Module 写入的候选链投影（Module 内按 CandidateRecord 形状消费）。
        .map((record) => ({ record: /** @type {CandidateRecord} */ (record.payload), version: record.version })));
    }
    const selectionDocs = await repository.documents.listLatest(pid, SELECTION_KIND);
    if (!action.alive()) return;
    for (const record of selectionDocs) {
      if (record.payload && typeof record.payload === "object") {
        // 采用记录形状以消费边界 assertSelectionRecord 为准；此处按 selection 文档契约投影。
        selections.set(record.document_id, { record: /** @type {SelectionRecord} */ (record.payload), version: record.version });
      }
    }
    const reviewDocs = await repository.documents.listLatest(pid, REVIEW_KIND);
    if (!action.alive()) return;
    for (const record of reviewDocs) {
      if (record.payload && typeof record.payload === "object") {
        // 本工作区写入的确定性复核报告的投影（消费时 reviewIsCurrent 按形状使用；此处只做内存登记）。
        generation.setReviewReport(record.document_id, { report: /** @type {ReviewReport} */ (record.payload), version: record.version });
      }
    }
    const suiteDocs = await repository.documents.listLatest(pid, SUITE_REVIEW_KIND);
    if (!action.alive()) return;
    for (const record of suiteDocs) {
      if (record.document_id === SUITE_REVIEW_DOCUMENT_ID
          && record.payload && typeof record.payload === "object") {
        // 本工作区写入的整套报告的投影（消费时 suiteReviewIsCurrent 校验版本与指纹）。
        suiteReports.set(SUITE_REVIEW_DOCUMENT_ID, {
          report: /** @type {SuiteReviewReport} */ (record.payload), version: record.version,
        });
      }
    }
    const ackDocs = await repository.documents.listLatest(pid, REVIEW_ACK_KIND);
    if (!action.alive()) return;
    for (const record of ackDocs) {
      if (record.payload && typeof record.payload === "object") {
        // 本工作区写入的已知悉记录的投影（append-only 消费，不做门禁证据）。
        acknowledgements.set(record.document_id,
          { record: /** @type {import("./domain/type-contracts.js").AcknowledgementRecord} */ (record.payload), version: record.version });
      }
    }
    const exportDocs = await repository.documents.listLatest(pid, EXPORT_RECORD_KIND);
    if (!action.alive()) return;
    if (exportDocs.length) {
      const payloads = exportDocs.map((item) => item.payload)
        .filter((item) => item && typeof item === "object")
        .sort((left, right) => String(left.exported_at || "")
          .localeCompare(String(right.exported_at || "")));
      const latest = payloads.length ? payloads[payloads.length - 1] : null;
      if (latest && typeof latest === "object") {
        deliveryRecord = {
          file_name: deliveryFileName({
            projectName: (project && project.name) || "", at: latest.exported_at,
          }),
          byte_size: Number(latest.zip_bytes) || 0,
          sha256: String(latest.zip_sha256 || ""),
          at: latest.exported_at || "",
          url: null,
        };
      }
    }
    for (const shot of (suitePlan && Array.isArray(suitePlan.shots) ? suitePlan.shots : [])) {
      // 落库套图 shot_id 恒为 string（见上；此处同）。
      const latest = generation.latestStoredCandidateOf(/** @type {string} */ (shot.shot_id));
      if (!latest) continue;
      const candidate = latest.record;
      const stored = generation.reviewReportOf(candidate.candidate_id);
      // 重开只补建缺失/过期报告：内存面已有当前报告则跳过，避免 review_report 版本无意义 +1。
      if (stored && reviewIsCurrent(stored.report, candidate)) continue;
      try {
        await generation.ensureReviewReport(/** @type {string} */ (shot.shot_id), candidate, null, action.projectId);
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
      if (saveTimer !== null) {
        try {
          await saveIntakeNow();
        } catch (error) {
          handleInternalError(error);
        }
      }
      revokeObjectUrls();
      revokePreviewUrls();
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
