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
  ATTEMPT_RECONCILE_MODES,
  ATTEMPT_STATES,
  CANDIDATE_DOCUMENT_KIND,
  COMPARE_CONTRACT_VERSION,
  COMPARE_SEVERITY_TEXT,
  COMPARE_STATE_TEXT,
  CONFIRM_DOCUMENT_ID,
  CORE_SLOT_REGISTRY,
  DOMAIN_DOCUMENT_KINDS,
  FACT_SLOT_SCHEMA_VERSION,
  MAX_REFERENCES,
  MAX_CANDIDATE_BYTES,
  MANUAL_EDIT_REASON_MAX,
  PRODUCT_INPUT_SCHEMA_VERSION,
  PLATFORM_PROFILES,
  PROVIDER_PROFILES,
  REFERENCE_ROLES,
  REVIEW_REPORT_DOCUMENT_KIND,
  REWORK_CONTRACT_VERSION,
  REWORK_PROBLEMS,
  SELECTION_CONTRACT_VERSION,
  SHOT_TEMPLATES,
  SUITE_PLAN_DOCUMENT_ID,
  STYLE_SPEC_DOCUMENT_ID,
  addCustomShotToPlan,
  addShotFromTemplate,
  applySlotAction,
  assertShotSpec,
  assertSelectionRecord,
  assertStyleSpec,
  attemptPromptStaleness,
  attemptReconcileMode,
  attemptStateLabel,
  batchProgressText,
  batchSubmitHalts,
  blockingAttemptFor,
  buildAttemptRecord,
  buildCandidateRecord,
  briefReadiness,
  buildConfirmationRecord,
  buildConfirmationSheet,
  buildEditedPromptRecord,
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
  candidateForAttempt,
  candidateMatchesAttempt,
  candidateStoreDecision,
  checkConfirmationRecord,
  checkFactSlot,
  checkPromptRecord,
  compareCounts,
  compareRowHeadline,
  compareRows,
  compilePrompt,
  confirmationSnapshot,
  confirmationStaleness,
  copyShot,
  coreSlotDefinition,
  defaultCompareTargetId,
  deriveBatchState,
  deriveSelectionState,
  emptyShotSpecFromShot,
  emptyStyleSpec,
  emptyProductInput,
  evaluateCandidateFindings,
  intakeReadiness,
  mergeVlmReview,
  moveShot,
  newActionId,
  nextFromStatusEnvelope,
  nextFromSubmitEnvelope,
  nextPendingShotId,
  parsePngDimensions,
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
  suitePlanSummary,
  suiteSpecDigest,
  styleSpecDiff,
  topFinding,
  validateSuitePlan,
} from "./domain/index.js";
import { sha256Hex } from "./storage/db.js";

const INTAKE_DOCUMENT_ID = "intake";
const INTAKE_KIND = DOMAIN_DOCUMENT_KINDS.product_input;
const SLOT_KIND = DOMAIN_DOCUMENT_KINDS.fact_slot;
const SUITE_KIND = DOMAIN_DOCUMENT_KINDS.suite_plan;
const STYLE_KIND = DOMAIN_DOCUMENT_KINDS.style_spec;
const SHOT_SPEC_KIND = DOMAIN_DOCUMENT_KINDS.shot_spec;
const PROMPT_KIND = DOMAIN_DOCUMENT_KINDS.prompt_version;
const CONFIRM_KIND = DOMAIN_DOCUMENT_KINDS.generation_confirm;
const ATTEMPT_KIND = ATTEMPT_DOCUMENT_KIND;
const CANDIDATE_KIND = CANDIDATE_DOCUMENT_KIND;
const REVIEW_KIND = REVIEW_REPORT_DOCUMENT_KIND;

const CAPABILITIES_PATH = "/api/v2/capabilities";
const ANALYZE_PATH = "/api/v2/semantic/analyze";
const IMAGE_SUBMIT_PATH = "/api/v2/images/submit";
const IMAGE_STATUS_PATH = "/api/v2/images/status";
const IMAGE_RESULT_PATH = "/api/v2/images/result";
const REVIEW_PATH = "/api/v2/review/candidate";
const REWORK_CONFIRM_PREFIX = "rework:";
const SELECTION_KIND = DOMAIN_DOCUMENT_KINDS.selection;

const DRAFT_DEBOUNCE_MS = 600;
const ANALYZE_MAX_SLOTS = 12;
const MAX_REVIEW_IMAGE_BYTES = 4 * 1024 * 1024;
const MAX_REVIEW_REFERENCES = 3;
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

const SCOPE_TEXT = "这一版覆盖“商品资料 → 商品理解 → 套图规划 → 规格 → Prompt → 生成前确认 → 整套生成与逐图进度（含单张核对）→ 审核 → 单图返工 → 人工采用”；整套一致性报告与导出交付尚未接入。";

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

function splitLines(text) {
  return String(text || "").split("\n").map((item) => item.trim()).filter((item) => item.length > 0);
}

function formatValue(slot) {
  const value = slot.value;
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.join("；");
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

function describeBlocking(blocking) {
  return (blocking || []).map((item) => item.message).join("；");
}

export function createWorkspace({ repository, onProjectChanged = null }) {
  const elements = {
    error: document.getElementById("workspace-error"),
    scope: document.getElementById("project-scope"),
    refAdd: document.getElementById("ref-add"),
    refFile: document.getElementById("ref-file"),
    refCount: document.getElementById("ref-count"),
    refError: document.getElementById("ref-error"),
    refEmpty: document.getElementById("ref-empty"),
    refList: document.getElementById("ref-list"),
    intakeName: document.getElementById("intake-name"),
    intakeDescription: document.getElementById("intake-description"),
    intakePoints: document.getElementById("intake-selling-points"),
    intakeFocus: document.getElementById("intake-focus"),
    intakeSave: document.getElementById("intake-save"),
    intakeDraft: document.getElementById("intake-draft"),
    intakeError: document.getElementById("intake-error"),
    analyzeRun: document.getElementById("analyze-run"),
    analyzeGate: document.getElementById("analyze-gate"),
    analyzeResult: document.getElementById("analyze-result"),
    analyzeError: document.getElementById("analyze-error"),
    slotsProgress: document.getElementById("slots-progress"),
    slotsToggle: document.getElementById("slots-toggle"),
    slotsEmpty: document.getElementById("slots-empty"),
    slotList: document.getElementById("slot-list"),
    slotAddId: document.getElementById("slot-add-id"),
    slotAddLabel: document.getElementById("slot-add-label"),
    slotAddType: document.getElementById("slot-add-type"),
    slotAddValue: document.getElementById("slot-add-value"),
    slotAddAllowModel: document.getElementById("slot-add-allow-model"),
    slotAddSave: document.getElementById("slot-add-save"),
    slotAddStatus: document.getElementById("slot-add-status"),
    slotsError: document.getElementById("slots-error"),
    suiteLocked: document.getElementById("suite-locked"),
    suiteEditor: document.getElementById("suite-editor"),
    suiteSeed: document.getElementById("suite-seed"),
    suiteTemplate: document.getElementById("suite-template"),
    suiteTemplateHint: document.getElementById("suite-template-hint"),
    suiteAddTemplate: document.getElementById("suite-add-template"),
    suiteCustomToggle: document.getElementById("suite-custom-toggle"),
    suiteStatus: document.getElementById("suite-status"),
    suiteCustomPanel: document.getElementById("suite-custom-panel"),
    suiteCustomLabel: document.getElementById("suite-custom-label"),
    suiteCustomIntent: document.getElementById("suite-custom-intent"),
    suiteCustomSave: document.getElementById("suite-custom-save"),
    suiteCustomStatus: document.getElementById("suite-custom-status"),
    suiteEmpty: document.getElementById("suite-empty"),
    shotList: document.getElementById("shot-list"),
    suiteError: document.getElementById("suite-error"),
    specsLocked: document.getElementById("specs-locked"),
    specsEditor: document.getElementById("specs-editor"),
    styleBackground: document.getElementById("style-background"),
    styleLighting: document.getElementById("style-lighting"),
    styleColorTone: document.getElementById("style-color-tone"),
    styleComposition: document.getElementById("style-composition"),
    styleAvoid: document.getElementById("style-avoid"),
    styleSave: document.getElementById("style-save"),
    styleRestore: document.getElementById("style-restore"),
    styleVersion: document.getElementById("style-version"),
    styleEffect: document.getElementById("style-effect"),
    styleStatus: document.getElementById("style-status"),
    styleError: document.getElementById("style-error"),
    shotSpecsEmpty: document.getElementById("shot-specs-empty"),
    shotSpecList: document.getElementById("shot-spec-list"),
    specsError: document.getElementById("specs-error"),
    promptLocked: document.getElementById("prompt-locked"),
    promptEditor: document.getElementById("prompt-editor"),
    promptStatus: document.getElementById("prompt-status"),
    promptList: document.getElementById("prompt-list"),
    promptError: document.getElementById("prompt-error"),
    confirmLocked: document.getElementById("confirm-locked"),
    confirmEditor: document.getElementById("confirm-editor"),
    confirmStatus: document.getElementById("confirm-status"),
    confirmSummary: document.getElementById("confirm-summary"),
    confirmBlockers: document.getElementById("confirm-blockers"),
    confirmRisks: document.getElementById("confirm-risks"),
    confirmList: document.getElementById("confirm-list"),
    confirmAction: document.getElementById("confirm-action"),
    confirmRecord: document.getElementById("confirm-record"),
    confirmError: document.getElementById("confirm-error"),
    attemptLocked: document.getElementById("attempt-locked"),
    attemptEditor: document.getElementById("attempt-editor"),
    attemptStatus: document.getElementById("attempt-status"),
    attemptProvider: document.getElementById("attempt-provider"),
    batchBar: document.getElementById("attempt-batch"),
    batchRun: document.getElementById("batch-run"),
    batchStop: document.getElementById("batch-stop"),
    batchReconcile: document.getElementById("batch-reconcile"),
    batchRetry: document.getElementById("batch-retry"),
    batchProgress: document.getElementById("batch-progress"),
    batchHint: document.getElementById("batch-hint"),
    attemptList: document.getElementById("attempt-list"),
    attemptError: document.getElementById("attempt-error"),
    comparePanel: document.getElementById("compare-panel"),
    compareSubject: document.getElementById("compare-subject"),
    compareJump: document.getElementById("compare-jump"),
    compareClose: document.getElementById("compare-close"),
    compareBasisTitle: document.getElementById("compare-basis-title"),
    compareReferences: document.getElementById("compare-references"),
    compareCandidates: document.getElementById("compare-candidates"),
    compareChecklist: document.getElementById("compare-checklist"),
    compareStatus: document.getElementById("compare-status"),
    reworkOpen: document.getElementById("rework-open"),
    reworkPanel: document.getElementById("rework-panel"),
    reworkBasis: document.getElementById("rework-basis"),
    reworkProblems: document.getElementById("rework-problems"),
    reworkDirection: document.getElementById("rework-direction"),
    reworkPreview: document.getElementById("rework-preview"),
    reworkEdit: document.getElementById("rework-edit"),
    reworkSubmit: document.getElementById("rework-submit"),
    reworkReset: document.getElementById("rework-reset"),
    reworkCancel: document.getElementById("rework-cancel"),
    reworkPreviewBox: document.getElementById("rework-preview-box"),
    reworkPreviewMeta: document.getElementById("rework-preview-meta"),
    reworkPreviewText: document.getElementById("rework-preview-text"),
    reworkSummary: document.getElementById("rework-summary"),
    reworkStatus: document.getElementById("rework-status"),
    reworkError: document.getElementById("rework-error"),
    adoptOpen: document.getElementById("adopt-open"),
    adoptPanel: document.getElementById("adopt-panel"),
    adoptBasis: document.getElementById("adopt-basis"),
    adoptCancel: document.getElementById("adopt-cancel"),
    adoptCurrent: document.getElementById("adopt-current"),
    adoptFingerprint: document.getElementById("adopt-fingerprint"),
    adoptSubmit: document.getElementById("adopt-submit"),
    adoptClear: document.getElementById("adopt-clear"),
    adoptReadiness: document.getElementById("adopt-readiness"),
    adoptStatus: document.getElementById("adopt-status"),
    adoptError: document.getElementById("adopt-error"),
    adoptProgress: document.getElementById("adopt-progress"),
  };

  let project = null;
  let projectId = null;
  let intake = emptyProductInput();
  let intakeVersion = 0;
  let intakeFingerprint = "";
  let slots = new Map();
  let capabilities = null;
  let capabilitiesError = null;
  let understandingBlocking = [];
  let understandingError = null;
  let lastAnalyze = null;
  let analyzeProblems = [];
  let showAll = false;
  let interaction = { slotId: null, mode: null };
  let suitePlan = null;
  let suiteVersion = 0;
  let understandingReady = false;
  let styleSpec = emptyStyleSpec();
  let styleVersion = 0;
  let shotSpecs = new Map();
  let promptVersions = new Map();
  let confirmRecord = null;
  let attemptChains = new Map();
  let attemptInFlight = new Set();
  let candidateChains = new Map();
  let candidateInFlight = new Set();
  let reviewInFlight = new Set();
  let reviewReports = new Map();
  let compareShotId = null;
  let compareCandidateId = null;
  let compareToken = 0;
  let reworkDrafts = new Map();
  let reworkConfirmations = new Map();
  let reworkInFlight = false;
  let reworkShotId = null;
  let reworkSource = null;
  let selections = new Map();
  let adoptInFlight = false;
  let adoptShotId = null;
  let adoptCandidateId = null;
  let adoptSource = null;
  let previewUrls = new Map();
  let batchState = null;
  let busy = false;
  let saveTimer = null;
  let objectUrls = [];
  let bound = false;
  let openToken = 0;
  /* ------------------------------------------------------ 公共读写与工具 */

  function showError(element, message) {
    element.textContent = message;
    element.hidden = false;
  }

  function clearError(element) {
    element.textContent = "";
    element.hidden = true;
  }

  function revokeObjectUrls() {
    for (const url of objectUrls) URL.revokeObjectURL(url);
    objectUrls = [];
  }

  function revokePreviewUrls() {
    for (const url of previewUrls.values()) URL.revokeObjectURL(url);
    previewUrls = new Map();
  }

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

  function fingerprintOf(payload) {
    return JSON.stringify([
      payload.product_name, payload.description, payload.selling_points,
      payload.focus, payload.references,
    ]);
  }

  function slotEntries() {
    return [...slots.values()].map((entry) => ({ slot: entry.slot, version: entry.version }));
  }

  function dependencyCountOf(slotId) {
    let count = 0;
    for (const entry of slots.values()) {
      if ((entry.slot.depends_on || []).includes(slotId)) count += 1;
    }
    return count;
  }

  function handleInternalError(error) {
    showError(elements.error, (error && error.message) || "操作没有完成，请重试。");
  }

  /* ------------------------------------------------------------ 参考图 */

  async function renderReferences() {
    // 先异步取齐资产、只在最后一刻替换 DOM：重叠渲染不会把同一行插两次。
    const entries = intake.references.map((item) => ({ ...item }));
    const rows = [];
    const urls = [];
    for (const [index, entry] of entries.entries()) {
      const asset = await repository.assets.get(projectId, entry.asset_sha256);
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
           (asset.width && asset.height ? asset.width + "×" + asset.height : "尺寸未知"),
           "sha256 " + entry.asset_sha256.slice(0, 12) + "…"].join(" · ")
        : "资产记录缺失 · sha256 " + entry.asset_sha256.slice(0, 12) + "…";
      main.append(createElement("span", { className: "meta", text: info }));

      const actions = createElement("div", { className: "ref-actions" });
      const select = createElement("select", {
        attrs: { "aria-label": "参考图角色" },
        props: { value: entry.role },
      });
      for (const role of REFERENCE_ROLES) {
        select.append(createElement("option", {
          text: ROLE_TEXT[role] || role, attrs: { value: role },
        }));
      }
      select.value = entry.role;
      select.addEventListener("change", () => { handleRoleChange(index, select.value); });
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

  async function handleRoleChange(index, role) {
    const entry = intake.references[index];
    if (!entry) return;
    entry.role = role;
    clearError(elements.refError);
    await saveIntakeNow();
    renderAll();
  }

  async function handleRemoveReference(index) {
    if (!intake.references[index]) return;
    intake.references.splice(index, 1);
    clearError(elements.refError);
    await saveIntakeNow();
    renderAll();
  }

  async function handleFiles(fileList) {
    const files = [...(fileList || [])];
    if (!files.length) return;
    clearError(elements.refError);
    const known = new Set(intake.references.map((item) => item.asset_sha256));
    let wantsPrimary = !intake.references.some((item) => item.role === "primary");
    let added = 0;
    for (const file of files) {
      if (intake.references.length >= MAX_REFERENCES) {
        showError(elements.refError, "参考图最多 " + MAX_REFERENCES + " 张，多出的文件没有加入。");
        break;
      }
      let width = null;
      let height = null;
      try {
        const bitmap = await createImageBitmap(file);
        width = bitmap.width;
        height = bitmap.height;
        bitmap.close();
      } catch (error) {
        showError(elements.refError, "“" + file.name + "”不是可读取的图片，已跳过。");
        continue;
      }
      const role = wantsPrimary ? "primary" : "other";
      const asset = await repository.assets.put(projectId, {
        blob: file,
        mediaType: file.type || "application/octet-stream",
        originalName: file.name,
        role,
        width,
        height,
      });
      if (known.has(asset.sha256)) {
        showError(elements.refError, "“" + file.name + "”与已有参考图内容相同，已跳过。");
        continue;
      }
      known.add(asset.sha256);
      intake.references.push(referenceFromAsset(asset, { role }));
      wantsPrimary = false;
      added += 1;
    }
    if (added) {
      await saveIntakeNow();
      renderAll();
    }
  }

  /* ---------------------------------------------------------- 商品资料 */

  function updateDraftStatus() {
    elements.intakeDraft.textContent = intakeVersion
      ? "草稿已保存 · 版本 " + intakeVersion + (intake.product_name ? "" : "（尚未填写商品名称）")
      : "还没有保存过草稿。";
  }

  function scheduleDraftSave() {
    if (saveTimer !== null) clearTimeout(saveTimer);
    elements.intakeDraft.textContent = "正在编辑…";
    renderAnalyze();
    saveTimer = setTimeout(() => {
      saveTimer = null;
      saveIntakeNow()
        .then(() => deriveAndApplyState())
        .then(() => { renderAnalyze(); renderHeaderText(project); })
        .catch(handleInternalError);
    }, DRAFT_DEBOUNCE_MS);
  }

  function saveIntakeNow() {
    if (saveTimer !== null) {
      clearTimeout(saveTimer);
      saveTimer = null;
    }
    const payload = currentIntakePayload();
    const fingerprint = fingerprintOf(payload);
    if (fingerprint === intakeFingerprint) {
      updateDraftStatus();
      return Promise.resolve(false);
    }
    return (async () => {
      const record = await repository.documents.save(projectId, {
        kind: INTAKE_KIND, documentId: INTAKE_DOCUMENT_ID, payload,
      });
      intake = payload;
      intakeVersion = record.version;
      intakeFingerprint = fingerprint;
      updateDraftStatus();
      return true;
    })();
  }

  function renderIntake() {
    elements.intakeName.value = intake.product_name || "";
    elements.intakeDescription.value = intake.description || "";
    elements.intakePoints.value = (intake.selling_points || []).join("\n");
    elements.intakeFocus.value = intake.focus || "";
    updateDraftStatus();
  }
  /* -------------------------------------------------------------- 分析 */

  function gateProblems() {
    return intakeReadiness(currentIntakePayload()).blocking;
  }

  function renderAnalyze() {
    const problems = gateProblems();
    const ready = problems.length === 0;
    elements.analyzeRun.textContent = lastAnalyze ? "重新分析" : "分析商品资料";
    elements.analyzeRun.disabled = busy || !ready;
    elements.analyzeGate.textContent = busy
      ? "分析中…"
      : ready
        ? (capabilitiesError ? "分析服务状态：" + capabilitiesError : "资料已就绪。")
        : "还缺：" + describeBlocking(problems);

    if (lastAnalyze) {
      elements.analyzeResult.hidden = false;
      elements.analyzeResult.textContent = "最近一次分析：" + lastAnalyze.slots + " 个提案，写入 "
        + lastAnalyze.applied + " 个槽位 · " + lastAnalyze.provider
        + (lastAnalyze.model ? "（" + lastAnalyze.model + "）" : "")
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

  function reportAnalyzeFailure(status, result) {
    const error = result && result.error ? result.error : null;
    const parts = [];
    if (error) {
      parts.push(error.message || error.code || "分析失败");
      parts.push("分类：" + (error.family || "internal") + " / " + (error.code || "INTERNAL_ERROR"));
      if (error.retry_policy) parts.push("重试策略：" + error.retry_policy);
      if (error.request_id) parts.push("请求 ID：" + error.request_id);
    } else {
      parts.push("分析服务返回 HTTP " + status + "，响应不是本产品约定的错误结构。");
    }
    if (result && result.unknown === true) {
      parts.push("结果未知：这次请求可能已经产生结果。系统不会自动重试，请确认后再手动点击“重新分析”。");
    } else if (status === 503) {
      parts.push("语义 provider 当前不可用：检查 config/product-v2/providers.json、依赖与 DASHSCOPE_API_KEY。");
    } else if (status === 400) {
      parts.push("服务端拒绝了这份请求；按提示修改资料后可以再试。");
    }
    showError(elements.analyzeError, parts.join(" "));
  }

  async function buildAnalyzeBody() {
    const payload = currentIntakePayload();
    const references = [];
    for (const entry of payload.references) {
      const asset = await repository.assets.get(projectId, entry.asset_sha256);
      if (!asset) {
        throw new Error("参考图资产缺失（sha256 " + entry.asset_sha256.slice(0, 12) + "…），请重新上传。");
      }
      references.push({
        sha256: asset.sha256,
        media_type: asset.media_type || "application/octet-stream",
        role: entry.role,
        original_name: asset.original_name || null,
      });
    }
    const body = {
      product_name: payload.product_name,
      description: payload.description,
      selling_points: payload.selling_points,
      focus: payload.focus,
      references,
      locale: ANALYZE_LOCALE,
      platform: ANALYZE_PLATFORM,
      max_slots: ANALYZE_MAX_SLOTS,
      existing_slot_ids: [],
    };
    const allowed = capabilities && Array.isArray(capabilities.analyze_fields)
      && capabilities.analyze_fields.length
      ? capabilities.analyze_fields
      : DEFAULT_ANALYZE_FIELDS;
    const filtered = {};
    for (const field of allowed) if (field in body) filtered[field] = body[field];
    return filtered;
  }

  async function persistSlot(slot) {
    const record = await repository.documents.save(projectId, {
      kind: SLOT_KIND, documentId: slot.slot_id, payload: slot,
    });
    slots.set(slot.slot_id, { slot: record.payload, version: record.version });
    return record;
  }

  async function ensureCoreSlots() {
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
      });
      created += 1;
    }
    return created;
  }

  function baseSlotFor(raw, proposalIds) {
    const definition = raw.authority === "core_fixed" ? coreSlotDefinition(raw.slot_id) : null;
    if (raw.authority === "core_fixed" && !definition) return null;
    const known = new Set(slots.keys());
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

  async function applyProposal(proposal) {
    const rawSlots = Array.isArray(proposal.slots) ? proposal.slots : [];
    const proposalIds = new Set(rawSlots.map((item) => item && item.slot_id).filter(Boolean));
    const problems = [];
    let applied = 0;
    for (const raw of rawSlots) {
      try {
        const existing = slots.get(raw.slot_id);
        const base = existing ? existing.slot : baseSlotFor(raw, proposalIds);
        if (!base) {
          problems.push(raw.slot_id + "：模型把未知槽位标成系统固定槽位，已拒绝。");
          continue;
        }
        const next = applySlotAction(base, {
          action: "propose", actor: "model",
          value: raw.value, confidence: raw.confidence, evidence: raw.evidence,
        });
        if (typeof raw.model_id === "string") next.model_id = raw.model_id;
        await persistSlot(next);
        applied += 1;
      } catch (error) {
        const slotId = raw && raw.slot_id ? raw.slot_id : "未知槽位";
        problems.push(slotId + "：" + ((error && error.message) || "提案被拒绝"));
      }
    }
    return { applied, problems };
  }

  async function runAnalyze() {
    if (busy) return;
    busy = true;
    analyzeProblems = [];
    clearError(elements.analyzeError);
    renderAnalyze();
    try {
      await saveIntakeNow();
      const readiness = intakeReadiness(intake);
      if (!readiness.ready) {
        showError(elements.analyzeError, "商品资料还不完整：" + describeBlocking(readiness.blocking));
        return;
      }
      await ensureCoreSlots();
      let body;
      try {
        body = await buildAnalyzeBody();
      } catch (error) {
        showError(elements.analyzeError, "本地资料不完整：" + ((error && error.message) || "未知错误"));
        return;
      }
      let response;
      try {
        response = await fetch(ANALYZE_PATH, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      } catch (error) {
        showError(elements.analyzeError,
          "无法连接分析服务（本机服务是否在运行？）。这次调用可能已经发送，系统不会自动重试；"
          + "需要时请手动再次点击。");
        return;
      }
      let result = null;
      try {
        result = await response.json();
      } catch (error) {
        result = null;
      }
      if (!response.ok || !result || result.ok !== true) {
        reportAnalyzeFailure(response.status, result);
        return;
      }
      const proposal = result.proposal || {};
      const applied = await applyProposal(proposal);
      const meta = proposal.meta || {};
      analyzeProblems = applied.problems;
      lastAnalyze = {
        at: new Date().toLocaleString("zh-CN", { hour12: false }),
        provider: meta.provider_id || "未声明 provider",
        model: meta.model_id || "",
        slots: Array.isArray(proposal.slots) ? proposal.slots.length : 0,
        applied: applied.applied,
        summary: proposal.summary || "",
      };
      if (Array.isArray(proposal.questions) && proposal.questions.length) {
        analyzeProblems.push("模型提出的问题：" + proposal.questions.join(" / "));
      }
    } catch (error) {
      handleInternalError(error);
    } finally {
      busy = false;
      try {
        await deriveAndApplyState();
      } catch (error) {
        handleInternalError(error);
      }
      renderAll();
    }
  }

  async function loadCapabilities() {
    capabilities = null;
    capabilitiesError = null;
    try {
      const response = await fetch(CAPABILITIES_PATH, { headers: { Accept: "application/json" } });
      let payload = null;
      try {
        payload = await response.json();
      } catch (error) {
        payload = null;
      }
      if (response.ok && payload && payload.ok === true) {
        capabilities = payload;
        if (payload.provider && payload.provider.configured === false) {
          capabilitiesError = "当前的语义 provider 未配置完成，请检查密钥与依赖。";
        }
      } else {
        capabilitiesError = "capabilities 接口返回 HTTP " + response.status + "。";
      }
    } catch (error) {
      capabilitiesError = (error && error.message) || "无法访问 capabilities 接口。";
    }
  }
  /* ---------------------------------------------------------- 商品理解 */

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
        + (understandingBlocking.length ? " · 还缺：" + describeBlocking(understandingBlocking) : "")
      : "还没有槽位。";
    elements.slotsToggle.textContent = showAll ? "只看待处理项" : "显示全部事实";
    elements.slotsToggle.setAttribute("aria-expanded", showAll ? "true" : "false");
    elements.slotsEmpty.hidden = entries.length > 0;

    const list = (showAll ? entries : open).slice();
    list.sort((left, right) => {
      const byStatus = (REVIEW_ORDER[left.slot.status] ?? 9) - (REVIEW_ORDER[right.slot.status] ?? 9);
      if (byStatus !== 0) return byStatus;
      const byCritical = Number(right.slot.critical === true) - Number(left.slot.critical === true);
      if (byCritical !== 0) return byCritical;
      return left.slot.slot_id.localeCompare(right.slot.slot_id);
    });
    for (const entry of list) elements.slotList.append(slotRow(entry));
  }

  function slotMetaText(entry) {
    const slot = entry.slot;
    const parts = [slot.slot_id, AUTHORITY_TEXT[slot.authority] || slot.authority];
    if (slot.critical === true) parts.push("必须确认");
    if (slot.confidence !== null && slot.confidence !== undefined) {
      parts.push("置信 " + Number(slot.confidence).toFixed(2));
    }
    parts.push("版本 v" + entry.version);
    if (slot.depends_on && slot.depends_on.length) parts.push("依赖 " + slot.depends_on.join("、"));
    return parts.join(" · ");
  }

  function slotRow(entry) {
    const slot = entry.slot;
    const status = slot.status;
    const row = createElement("li", { className: "slot-row", attrs: { "data-status": status } });
    row.dataset.slotId = slot.slot_id;

    const head = createElement("div", { className: "slot-head" });
    head.append(createElement("span", {
      className: "badge is-" + status, text: STATUS_TEXT[status] || status,
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
        const label = EVIDENCE_TEXT[item.kind] || item.kind;
        list.append(createElement("li", {
          className: "meta",
          text: label + " · " + item.ref + (item.note ? "：" + item.note : ""),
        }));
      }
      row.append(list);
    }

    if (interaction.slotId === slot.slot_id) row.append(slotEditor(entry, interaction.mode));
    row.append(slotActions(entry));
    return row;
  }

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
        showError(elements.slotsError, (error && error.message) || "值不合法。");
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

  function readEditorValue(slot, node) {
    const raw = node.value;
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

  async function handleSlotAction(entry, spec) {
    clearError(elements.slotsError);
    try {
      const next = applySlotAction(entry.slot, spec);
      await persistSlot(next);
      interaction = { slotId: null, mode: null };
      await deriveAndApplyState();
      renderAll();
    } catch (error) {
      showError(elements.slotsError, (error && error.message) || "这个动作没有完成。");
    }
  }

  async function handleAddSlot() {
    clearError(elements.slotsError);
    elements.slotAddStatus.textContent = "";
    const slotId = elements.slotAddId.value.trim().toLowerCase();
    const label = elements.slotAddLabel.value.trim();
    const valueType = elements.slotAddType.value;
    const rawValue = elements.slotAddValue.value;
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
      showError(elements.slotsError, (error && error.message) || "值不合法。");
      return;
    }
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
    try {
      await persistSlot(candidate);
      elements.slotAddId.value = "";
      elements.slotAddLabel.value = "";
      elements.slotAddValue.value = "";
      elements.slotAddAllowModel.checked = false;
      elements.slotAddStatus.textContent = "已新增 " + candidate.slot_id;
      await deriveAndApplyState();
      renderAll();
    } catch (error) {
      showError(elements.slotsError, (error && error.message) || "新增槽位失败。");
    }
  }
  /* ------------------------------------------------------ 状态派生与装载 */

  /* ------------------------------------------------------------ 套图规划 */

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

  function suiteBlockingText(blocking) {
    return (blocking || []).map((item) => item.reason || item.message).join("；");
  }

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

  function renderSuite() {
    elements.suiteLocked.hidden = understandingReady;
    elements.suiteEditor.hidden = !understandingReady;
    if (!understandingReady) return;
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
    const summary = suitePlan ? suitePlanSummary(suitePlan, suiteContext()) : null;
    elements.suiteStatus.textContent = summary
      ? "共 " + summary.total + " 张，依据已满足 " + summary.satisfiable + " 张"
        + (summary.blocked ? "；" + summary.blocked + " 张缺依据" : "")
      : "还没有套图方案。";
    elements.suiteEmpty.hidden = Boolean(summary);
    elements.shotList.innerHTML = "";
    if (!summary) return;
    summary.shots.forEach((item, index) => {
      const row = createElement("li", {
        className: "shot-row",
        attrs: { "data-shot-id": item.shot_id, "data-blocked": String(!item.satisfied) },
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
      const actions = createElement("div", { className: "shot-actions" });
      const up = createElement("button", { text: "上移", attrs: { type: "button" } });
      up.disabled = index === 0;
      up.addEventListener("click", () => {
        handleSuiteOp(() => moveShot(suitePlan, item.shot_id, -1));
      });
      const down = createElement("button", { text: "下移", attrs: { type: "button" } });
      down.disabled = index === summary.shots.length - 1;
      down.addEventListener("click", () => {
        handleSuiteOp(() => moveShot(suitePlan, item.shot_id, 1));
      });
      const copy = createElement("button", { text: "复制", attrs: { type: "button" } });
      copy.addEventListener("click", () => {
        handleSuiteOp(() => copyShot(suitePlan, item.shot_id));
      });
      const remove = createElement("button", {
        text: "删除", className: "danger", attrs: { type: "button" },
      });
      remove.addEventListener("click", () => {
        handleSuiteOp(() => removeShot(suitePlan, item.shot_id));
      });
      actions.append(up, down, copy, remove);
      row.append(actions);
      elements.shotList.append(row);
    });
  }

  async function handleSuiteOp(run) {
    if (!understandingReady || !projectId) return false;
    clearError(elements.suiteError);
    try {
      const result = run();
      const nextPlan = result && result.plan ? result.plan : result;
      const problems = validateSuitePlan(nextPlan);
      if (problems.length > 0) throw new Error(problems[0].message);
      const saved = await repository.documents.save(projectId, {
        kind: SUITE_KIND,
        documentId: SUITE_PLAN_DOCUMENT_ID,
        payload: nextPlan,
      });
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
      showError(elements.suiteError, (error && error.message) || "操作没有完成，请重试。");
      return false;
    }
  }

  async function handleSuiteAddCustom() {
    const label = elements.suiteCustomLabel.value.trim();
    const intent = elements.suiteCustomIntent.value.trim();
    const ok = await handleSuiteOp(() => addCustomShotToPlan(suitePlan, { label, intent }));
    if (ok) {
      elements.suiteCustomLabel.value = "";
      elements.suiteCustomIntent.value = "";
      elements.suiteCustomStatus.textContent = "已添加。";
    }
  }

  /* -------------------------------------------------- 风格与单图规格 */

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

  function fillStyleForm(spec) {
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

  function renderStyleSpec() {
    const ready = understandingReady && Boolean(suitePlan);
    elements.specsLocked.hidden = ready;
    elements.specsEditor.hidden = !ready;
    if (!ready) return;
    fillStyleForm(styleSpec);
    elements.styleVersion.textContent = styleVersion > 0
      ? "版本 v" + styleVersion
      : "尚未保存";
    elements.styleRestore.disabled = styleVersion <= 1;
    const projection = specChangeProjection("style_changed", {
      shotCount: suitePlan.shots.length,
    });
    elements.styleEffect.textContent = "保存后影响：" + projection.affects_text
      + "；失效：" + projection.invalidates_text + "；保留：" + projection.preserves_text + "。";
  }

  function shotSpecEntry(shotId) {
    return shotSpecs.get(shotId) || null;
  }

  function renderShotSpecs() {
    const ready = understandingReady && Boolean(suitePlan);
    elements.specsLocked.hidden = ready;
    elements.specsEditor.hidden = !ready;
    elements.shotSpecList.innerHTML = "";
    if (!ready) return;
    elements.shotSpecsEmpty.hidden = suitePlan.shots.length > 0;
    const byId = {};
    for (const [shotId, entry] of shotSpecs.entries()) byId[shotId] = entry;
    const digest = suiteSpecDigest(suitePlan, { styleSpec, shotSpecsById: byId });
    digest.shots.forEach((item, index) => {
      const shot = suitePlan.shots[index];
      const entry = shotSpecEntry(item.shot_id);
      const spec = entry ? entry.spec : emptyShotSpecFromShot(shot);
      const card = createElement("div", {
        className: "shot-spec", attrs: { "data-shot-id": item.shot_id },
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
      const purposeId = "spec-purpose-" + item.shot_id;
      const purposeLabel = createElement("label", { text: "目的" });
      purposeLabel.setAttribute("for", purposeId);
      const purposeInput = createElement("input", { attrs: { id: purposeId, maxlength: "200" } });
      purposeInput.value = spec.purpose;
      purposeField.append(purposeLabel, purposeInput);
      card.append(purposeField);

      const keepField = createElement("div", { className: "field" });
      const keepId = "spec-keep-" + item.shot_id;
      const keepLabel = createElement("label", { text: "必须保持（一行一条）" });
      keepLabel.setAttribute("for", keepId);
      const keepArea = createElement("textarea", { attrs: { id: keepId, rows: "2" } });
      keepArea.value = spec.keep.join("\n");
      keepField.append(keepLabel, keepArea);
      card.append(keepField);

      const changeField = createElement("div", { className: "field" });
      const changeId = "spec-change-" + item.shot_id;
      const changeLabel = createElement("label", { text: "允许变化（一行一条）" });
      changeLabel.setAttribute("for", changeId);
      const changeArea = createElement("textarea", { attrs: { id: changeId, rows: "2" } });
      changeArea.value = spec.change_allowed.join("\n");
      changeField.append(changeLabel, changeArea);
      card.append(changeField);

      const toolbar = createElement("div", { className: "toolbar" });
      const saveButton = createElement("button", { text: "保存", attrs: { type: "button" } });
      saveButton.addEventListener("click", () => {
        handleSaveShotSpec(item.shot_id, {
          purpose: purposeInput.value.trim(),
          keep: splitLines(keepArea.value),
          change_allowed: splitLines(changeArea.value),
        });
      });
      const restoreButton = createElement("button", {
        text: "恢复上一版本", attrs: { type: "button" },
      });
      restoreButton.disabled = !entry || entry.version <= 1;
      restoreButton.addEventListener("click", () => { handleRestoreShotSpec(item.shot_id); });
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

  async function handleSaveStyle() {
    if (!projectId || !suitePlan) return;
    clearError(elements.styleError);
    elements.styleStatus.hidden = true;
    try {
      const next = styleFormPayload();
      assertStyleSpec(next);
      const diffs = styleSpecDiff(styleSpec, next);
      const record = await repository.documents.save(projectId, {
        kind: STYLE_KIND,
        documentId: STYLE_SPEC_DOCUMENT_ID,
        payload: next,
        expectedVersion: styleVersion > 0 ? styleVersion : null,
      });
      styleSpec = next;
      styleVersion = record.version;
      renderStyleSpec();
      renderShotSpecs();
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deriveAndApplyState();
      elements.styleStatus.hidden = false;
      elements.styleStatus.textContent = "已保存 v" + record.version
        + (diffs.length > 0
          ? "（改动：" + diffs.map((item) => item.label).join("、") + "）"
          : "（没有字段变化）");
    } catch (error) {
      showError(elements.styleError, (error && error.message) || "保存没有完成，请重试。");
    }
  }

  async function handleRestoreStyle() {
    if (!projectId || styleVersion <= 1) return;
    clearError(elements.styleError);
    try {
      const versions = await repository.documents.listVersions(
        projectId, STYLE_KIND, STYLE_SPEC_DOCUMENT_ID);
      const target = previousVersionOf(versions, styleVersion);
      if (!target) {
        showError(elements.styleError, "没有更早的版本可以恢复。");
        return;
      }
      const record = await repository.documents.save(projectId, {
        kind: STYLE_KIND,
        documentId: STYLE_SPEC_DOCUMENT_ID,
        payload: target.payload,
        expectedVersion: styleVersion,
      });
      styleSpec = { ...emptyStyleSpec(), ...target.payload };
      styleVersion = record.version;
      renderStyleSpec();
      renderShotSpecs();
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deriveAndApplyState();
      elements.styleStatus.hidden = false;
      elements.styleStatus.textContent = "已恢复 v" + target.version
        + " 的内容，写为新版本 v" + record.version + "。";
    } catch (error) {
      showError(elements.styleError, (error && error.message) || "恢复没有完成，请重试。");
    }
  }

  async function handleSaveShotSpec(shotId, changes) {
    if (!projectId || !suitePlan) return;
    clearError(elements.specsError);
    try {
      const shot = suitePlan.shots.find((item) => item.shot_id === shotId);
      if (!shot) throw new Error("找不到这张图，可能已被删除。");
      const entry = shotSpecEntry(shotId);
      const base = entry ? entry.spec : emptyShotSpecFromShot(shot);
      const next = {
        ...base,
        purpose: changes.purpose,
        keep: changes.keep,
        change_allowed: changes.change_allowed,
      };
      assertShotSpec(next);
      const record = await repository.documents.save(projectId, {
        kind: SHOT_SPEC_KIND,
        documentId: shotId,
        payload: next,
        expectedVersion: entry ? entry.version : null,
      });
      shotSpecs.set(shotId, { spec: next, version: record.version });
      renderShotSpecs();
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deriveAndApplyState();
    } catch (error) {
      showError(elements.specsError, (error && error.message) || "保存没有完成，请重试。");
    }
  }

  async function handleRestoreShotSpec(shotId) {
    if (!projectId) return;
    clearError(elements.specsError);
    try {
      const entry = shotSpecEntry(shotId);
      if (!entry || entry.version <= 1) {
        showError(elements.specsError, "没有更早的版本可以恢复。");
        return;
      }
      const versions = await repository.documents.listVersions(projectId, SHOT_SPEC_KIND, shotId);
      const target = previousVersionOf(versions, entry.version);
      if (!target) {
        showError(elements.specsError, "没有更早的版本可以恢复。");
        return;
      }
      const record = await repository.documents.save(projectId, {
        kind: SHOT_SPEC_KIND,
        documentId: shotId,
        payload: target.payload,
        expectedVersion: entry.version,
      });
      shotSpecs.set(shotId, { spec: target.payload, version: record.version });
      renderShotSpecs();
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deriveAndApplyState();
    } catch (error) {
      showError(elements.specsError, (error && error.message) || "恢复没有完成，请重试。");
    }
  }

  /* --------------------------------------------------------- Prompt 编译 */

  function promptCurrentBasis(shotId) {
    let briefBasis = [];
    try {
      briefBasis = buildProductBrief(slotEntries()).basis;
    } catch (error) {
      briefBasis = [];
    }
    const specEntry = shotSpecEntry(shotId);
    return {
      briefBasis: briefBasis,
      suite_version: suiteVersion > 0 ? suiteVersion : null,
      style_version: styleVersion > 0 ? styleVersion : null,
      shot_spec_version: specEntry ? specEntry.version : null,
      platform: { version: PLATFORM_PROFILES.amazon_us.version },
      provider: { version: PROVIDER_PROFILES["qwen-image-3.0"].version },
    };
  }

  function promptRecordOf(shotId) {
    const entry = promptVersions.get(shotId) || null;
    if (!entry || !entry.record || !entry.record.compiled) return null;
    return entry;
  }

  /** 未保存的编辑草稿：重渲染时保留用户输入，不让界面动作吞掉正在写的文本。 */
  function capturePromptEdits() {
    const drafts = new Map();
    for (const area of elements.promptList.querySelectorAll("textarea.prompt-edit-text")) {
      const shotId = area.getAttribute("data-shot-id");
      const reason = area.parentElement
        ? area.parentElement.querySelector("input.prompt-edit-reason") : null;
      if (shotId) drafts.set(shotId, { text: area.value, reason: reason ? reason.value : "" });
    }
    return drafts;
  }

  function renderPrompts() {
    const drafts = capturePromptEdits();
    const ready = understandingReady && Boolean(suitePlan);
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
      const entry = promptRecordOf(item.shot_id);
      const stale = entry ? promptStaleness(entry.record, promptCurrentBasis(item.shot_id)) : null;
      const card = createElement("div", {
        className: "shot-spec",
        attrs: {
          "data-shot-id": item.shot_id,
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
          card.append(createElement("p", { className: "meta prompt-warning", text: "提示：" + warning.message }));
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
            text: "已过期（" + stale.reasons.map((reason) => reason.field).join("、") + "），请重新编译。",
          }));
        }
      } else if (!item.satisfied) {
        card.append(createElement("p", {
          className: "meta", text: "暂时缺依据：" + suiteBlockingText(item.blocking),
        }));
      }
      const toolbar = createElement("div", { className: "toolbar" });
      const compileButton = createElement("button", {
        text: "编译并保存版本", className: "primary", attrs: { type: "button" },
      });
      compileButton.disabled = !item.satisfied || busy;
      compileButton.addEventListener("click", () => { handleCompilePrompt(item.shot_id); });
      toolbar.append(compileButton);
      card.append(toolbar);
      if (entry) {
        const draft = drafts.get(item.shot_id) || null;
        const unsaved = Boolean(draft) && draft.text !== entry.record.compiled.text;
        const block = createElement("div", { className: "prompt-edit-block" });
        block.append(createElement("label", {
          className: "meta",
          attrs: { for: "prompt-edit-" + item.shot_id },
          text: "人工编辑全文（保存为新版本；原版本保留）",
        }));
        const area = createElement("textarea", {
          className: "prompt-edit-text",
          attrs: { id: "prompt-edit-" + item.shot_id, "data-shot-id": item.shot_id, rows: "6" },
        });
        area.value = unsaved ? draft.text : entry.record.compiled.text;
        block.append(area);
        block.append(createElement("label", {
          className: "meta",
          attrs: { for: "prompt-edit-reason-" + item.shot_id },
          text: "编辑原因（必填，写入版本记录）",
        }));
        const reason = createElement("input", {
          className: "prompt-edit-reason",
          attrs: {
            id: "prompt-edit-reason-" + item.shot_id, type: "text", autocomplete: "off",
            maxlength: String(MANUAL_EDIT_REASON_MAX),
          },
        });
        if (unsaved && draft.reason) reason.value = draft.reason;
        block.append(reason);
        const saveEdit = createElement("button", { text: "保存为新版本", attrs: { type: "button" } });
        saveEdit.disabled = busy;
        saveEdit.addEventListener("click", () => { handleSaveEditedPrompt(item.shot_id); });
        block.append(saveEdit);
        card.append(block);
      }
      elements.promptList.append(card);
    });
  }

  /**
   * 纯编译一张图的 Prompt（不写记录）：预览、保存与提交共用同一条编译路径。
   */
  async function compileShotPrompt(shotId, options = {}) {
    const shot = suitePlan.shots.find((item) => item.shot_id === shotId);
    if (!shot) throw new Error("找不到这张图，可能已被删除。");
    const brief = buildProductBrief(slotEntries());
    const specEntry = shotSpecEntry(shotId);
    const compiled = compilePrompt({
      brief: brief,
      shot: shot,
      styleSpec: styleSpec,
      shotSpec: specEntry ? specEntry.spec : null,
      context: suiteContext(),
      versions: {
        suite_version: suiteVersion,
        style_version: styleVersion,
        shot_spec_version: specEntry ? specEntry.version : null,
      },
      ...(options.rework ? { rework: options.rework } : {}),
    });
    const references = selectReferences(shot, intake.references.map((item) => ({
      role: item.role, sha256: item.asset_sha256,
    })));
    const snapshot = requestSnapshotOf(compiled, { references: references });
    const hash = await promptHash(snapshot, { digest: sha256Hex });
    const payload = buildPromptRecord({ compiled: compiled, snapshot: snapshot, hash: hash });
    const problems = checkPromptRecord(payload);
    if (problems.length > 0) throw new Error(problems[0].message);
    return { payload: payload, compiled: compiled, references: references };
  }

  /** 保存一条已编译的 Prompt 版本；版本号由 repository 递增，旧版本保留。 */
  async function savePromptPayload(shotId, payload) {
    const saved = await repository.documents.save(projectId, {
      kind: PROMPT_KIND, documentId: shotId, payload: payload,
    });
    promptVersions.set(shotId, { record: payload, version: saved.version });
    return saved;
  }

  /**
   * 编译并保存一张图的 Prompt 版本（V2.5.4 起可选带返工指令）。
   * 纯编译 + 保存；失败抛错交给调用方，界面文案不在这一层写死。
   */
  async function compileAndSavePrompt(shotId, options = {}) {
    const result = await compileShotPrompt(shotId, options);
    const saved = await savePromptPayload(shotId, result.payload);
    return { saved: saved, payload: result.payload, compiled: result.compiled,
             references: result.references };
  }

  async function handleCompilePrompt(shotId) {
    if (!projectId || !suitePlan || !understandingReady) return;
    clearError(elements.promptError);
    try {
      const result = await compileAndSavePrompt(shotId);
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deriveAndApplyState();
      elements.promptStatus.textContent = "已保存 " + shotId + " 的 Prompt 版本 v"
        + result.saved.version + "。";
    } catch (error) {
      showError(elements.promptError,
        (error && error.message) ? error.message + "（旧版本已保留）" : "编译未完成，旧版本已保留。");
      renderPrompts();
      renderConfirm();
      renderAttempts();
    }
  }

  /** 人工编辑：保存为新版本；失败时保留旧版本与用户输入，不清空文本区。 */
  async function handleSaveEditedPrompt(shotId) {
    if (!projectId || !suitePlan || !understandingReady) return;
    clearError(elements.promptError);
    const entry = promptRecordOf(shotId);
    if (!entry) {
      showError(elements.promptError, "先编译并保存这张图的 Prompt，再编辑。");
      return;
    }
    const area = document.getElementById("prompt-edit-" + shotId);
    const reasonInput = document.getElementById("prompt-edit-reason-" + shotId);
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
      const saved = await repository.documents.save(projectId, {
        kind: PROMPT_KIND, documentId: shotId, payload: record,
      });
      promptVersions.set(shotId, { record: record, version: saved.version });
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deriveAndApplyState();
      elements.promptStatus.textContent = "已保存 " + shotId + " 的人工编辑版本 v" + saved.version
        + "（被编辑版本 v" + entry.version + " 保留）。";
    } catch (error) {
      showError(elements.promptError,
        (error && error.message) ? error.message + "（旧版本与输入已保留）" : "编辑未保存，旧版本与输入已保留。");
    }
  }

  /* ---------------------------------------------------------- 生成前确认 */

  /**
   * 确认单投影：界面、状态派生与提交都读同一份，不各自重算。
   * shotIds 给定时只投影这些图（V2.5.4 单图返工），否则是整套。
   */
  function buildScopedSheet(shotIds) {
    if (!suitePlan) return null;
    const entries = [...promptVersions.entries()].map(([shotId, entry]) => ({
      shot_id: shotId, record: entry.record, version: entry.version,
    }));
    const basisByShot = {};
    for (const shot of suitePlan.shots) {
      basisByShot[shot.shot_id] = promptCurrentBasis(shot.shot_id);
    }
    return buildConfirmationSheet({
      suitePlan: suitePlan,
      promptEntries: entries,
      context: suiteContext(),
      currentBasisByShot: basisByShot,
      shotIds: shotIds,
    });
  }

  function buildCurrentSheet() {
    return buildScopedSheet(null);
  }

  /** 确认记录是否仍然对得上「这一批将要提交的东西」。 */
  function confirmationIsCurrent() {
    if (!confirmRecord) return false;
    try {
      const sheet = buildCurrentSheet();
      if (!sheet || !sheet.can_submit) return false;
      return !confirmationStaleness(confirmRecord.payload, confirmationSnapshot(sheet)).stale;
    } catch (error) {
      return false;
    }
  }

  /**
   * 这张图的返工确认是否仍然有效：与整套确认同一套「快照逐字比对」判定，
   * 只是作用域只有这一张图——改别的图不会让它失效，改这张图一定会失效。
   */
  function reworkConfirmationIsCurrent(shotId) {
    const entry = reworkConfirmations.get(shotId);
    if (!entry) return false;
    try {
      const sheet = buildScopedSheet([shotId]);
      if (!sheet || !sheet.can_submit) return false;
      return !confirmationStaleness(entry.payload, confirmationSnapshot(sheet)).stale;
    } catch (error) {
      return false;
    }
  }

  /** 提交这张图的条件：整套确认有效，或这张图有自己有效的返工确认。 */
  function confirmationIsCurrentForShot(shotId) {
    return confirmationIsCurrent() || reworkConfirmationIsCurrent(shotId);
  }

  function renderConfirm() {
    const ready = understandingReady && Boolean(suitePlan);
    elements.confirmLocked.hidden = ready;
    elements.confirmEditor.hidden = !ready;
    elements.confirmSummary.innerHTML = "";
    elements.confirmBlockers.innerHTML = "";
    elements.confirmRisks.innerHTML = "";
    elements.confirmList.innerHTML = "";
    elements.confirmRecord.textContent = "";
    elements.confirmAction.disabled = true;
    if (!ready) return;
    let sheet = null;
    try {
      sheet = buildCurrentSheet();
    } catch (error) {
      showError(elements.confirmError,
        "生成前确认投影失败：" + ((error && error.message) || "未知错误"));
      return;
    }
    if (!sheet) return;
    elements.confirmStatus.textContent = "共 " + sheet.total + " 张；就绪 " + sheet.ready
      + " 张；阻断 " + sheet.blocked + " 张" + (sheet.can_submit ? "；可以确认。" : "。");
    elements.confirmSummary.append(createElement("p", {
      className: "confirm-summary", text: sheet.external_summary.statement,
    }));
    elements.confirmSummary.append(createElement("p", {
      className: "meta",
      text: "每张图发送自己的 Prompt 文本与上列参考图；不发送本地文件本身、历史候选或其他项目数据。",
    }));
    for (const blocker of sheet.blockers) {
      const row = createElement("p", { className: "confirm-blocker" });
      row.append(createElement("span", { text: "#" + blocker.order + " " + blocker.label + " · " + blocker.code }));
      row.append(createElement("span", { className: "meta", text: blocker.message }));
      row.append(createElement("span", {
        className: "meta", text: "返回：" + blocker.fix.region + " · " + blocker.fix.action,
      }));
      elements.confirmBlockers.append(row);
    }
    for (const risk of sheet.risks) {
      elements.confirmRisks.append(createElement("p", {
        className: "confirm-risk",
        text: risk.label + " · " + risk.code + "：" + risk.message,
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
        text: item.blockers.length > 0 ? "阻断 " + item.blockers.length + " 项" : "就绪",
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
          + (item.references.map((ref) => ref.role + " " + ref.sha256_prefix).join("、") || "无") + "）"
          + (item.prompt.chars === null ? "" : " · 提示词 " + item.prompt.chars + " 字"),
      }));
      if (item.risks.length > 0) {
        row.append(createElement("p", {
          className: "meta prompt-warning",
          text: "风险：" + item.risks.map((risk) => risk.code).join("、"),
        }));
      }
      elements.confirmList.append(row);
    }
    elements.confirmAction.disabled = !sheet.can_submit || busy;
    if (confirmRecord) {
      const staleness = confirmationStaleness(confirmRecord.payload, confirmationSnapshot(sheet));
      elements.confirmRecord.textContent = staleness.stale
        ? "已确认 v" + confirmRecord.version + " 已失效（"
          + staleness.reasons.map((reason) => reason.field).join("、") + "），需要重新确认。"
        : "已确认 v" + confirmRecord.version + "（" + confirmRecord.payload.confirmed_at
          + "）；本版尚未调用图片模型。";
    } else {
      elements.confirmRecord.textContent = "尚未确认。";
    }
  }

  async function handleConfirmGeneration() {
    if (!projectId || !suitePlan) return;
    clearError(elements.confirmError);
    try {
      const sheet = buildCurrentSheet();
      if (!sheet) throw new Error("还没有可确认的套图方案。");
      if (!sheet.can_submit) {
        throw new Error("还有 " + sheet.blocked + " 张图未就绪，不能确认生成。");
      }
      const snapshot = confirmationSnapshot(sheet);
      const hash = await promptHash(snapshot, { digest: sha256Hex });
      const payload = buildConfirmationRecord({
        sheet: sheet, hash: hash, confirmedAt: new Date().toISOString(),
      });
      const problems = checkConfirmationRecord(payload);
      if (problems.length > 0) throw new Error(problems[0].message);
      const saved = await repository.documents.save(projectId, {
        kind: CONFIRM_KIND, documentId: CONFIRM_DOCUMENT_ID, payload: payload,
      });
      confirmRecord = { payload: payload, version: saved.version };
      renderConfirm();
      renderAttempts();
      elements.confirmRecord.textContent = "已确认 v" + saved.version + "（" + payload.confirmed_at
        + "）；本版尚未调用图片模型。";
      await deriveAndApplyState();
    } catch (error) {
      showError(elements.confirmError, (error && error.message) || "确认没有完成，请重试。");
      renderConfirm();
    }
  }

  /* ------------------------------------------------------------ 生成执行 */

  /** 每张图的 Attempt 版本链（按版本升序）；append-only，界面只追加不覆盖。 */
  function attemptChainOf(shotId) {
    return attemptChains.get(shotId) || [];
  }

  function latestAttemptOf(shotId) {
    const chain = attemptChainOf(shotId);
    return chain.length ? chain[chain.length - 1] : null;
  }

  function allAttemptRecords() {
    const list = [];
    for (const chain of attemptChains.values()) {
      for (const entry of chain) list.push(entry.record);
    }
    return list;
  }

  function rememberAttempt(shotId, entry) {
    const chain = attemptChainOf(shotId).filter((item) => item.version !== entry.version);
    chain.push(entry);
    chain.sort((left, right) => left.version - right.version);
    attemptChains.set(shotId, chain);
  }

  /** 每张图的候选版本链（按版本升序）；append-only，一条候选绑定一个来源 action。 */
  function candidateChainOf(shotId) {
    return candidateChains.get(shotId) || [];
  }

  function candidateForAttemptRecord(shotId, actionId) {
    return candidateForAttempt(candidateChainOf(shotId), actionId);
  }

  function rememberCandidate(shotId, entry) {
    const chain = candidateChainOf(shotId).filter((item) => item.version !== entry.version);
    chain.push(entry);
    chain.sort((left, right) => left.version - right.version);
    candidateChains.set(shotId, chain);
  }

  /** 最新 Attempt 若是「已成功且有候选」，返回该候选；其它情况返回 null。 */
  function latestStoredCandidateOf(shotId) {
    const latest = latestAttemptOf(shotId);
    if (!latest || latest.record.state !== ATTEMPT_STATES.succeeded) return null;
    return candidateForAttemptRecord(shotId, latest.record.action_id);
  }

  function currentPromptPointer(shotId) {
    const entry = promptRecordOf(shotId);
    return entry ? { version: entry.version, hash: entry.record.hash } : null;
  }

  function imageProviderBlock() {
    const images = capabilities && capabilities.images ? capabilities.images : null;
    return images && images.provider ? images.provider : null;
  }

  function attemptProviderIdentity() {
    const block = imageProviderBlock();
    const profile = PROVIDER_PROFILES["qwen-image-3.0"];
    return {
      provider_id: (block && block.provider_id) || profile.provider_id,
      model_id: (block && block.model_id) || profile.model_id,
      configured: block ? block.configured !== false : false,
    };
  }

  function attemptParametersOf(entry) {
    const snapshot = entry.record.request_snapshot || {};
    const profile = PROVIDER_PROFILES["qwen-image-3.0"];
    return {
      size: snapshot.size || profile.size,
      n: snapshot.n || profile.n,
      prompt_extend: snapshot.prompt_extend === true,
      watermark: snapshot.watermark === true,
    };
  }

  function attemptIsActive(state) {
    return state === ATTEMPT_STATES.pending_submit || state === ATTEMPT_STATES.submitted
      || state === ATTEMPT_STATES.running;
  }

  function attemptBadgeClass(state) {
    if (state === ATTEMPT_STATES.succeeded) return "is-attempt-done";
    if (state === ATTEMPT_STATES.failed) return "is-attempt-failed";
    if (state === ATTEMPT_STATES.unknown) return "is-attempt-unknown";
    return "is-attempt-active";
  }

  function shortTime(iso) {
    if (!iso) return "?";
    try {
      return new Date(iso).toLocaleString("zh-CN", { hour12: false });
    } catch (error) {
      return String(iso);
    }
  }

  async function blobToBase64(blob) {
    const buffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    let binary = "";
    const chunk = 0x8000;
    for (let index = 0; index < bytes.length; index += chunk) {
      binary += String.fromCharCode.apply(null, bytes.subarray(index, index + chunk));
    }
    return btoa(binary);
  }

  /** 参考图字节从本地仓库读取并转 base64；读不到就不发请求（绝不发半份资料）。 */
  async function buildSubmitReferences(references) {
    const payload = [];
    for (const item of references) {
      const asset = await repository.assets.get(projectId, item.sha256);
      if (!asset || !asset.blob) {
        throw new Error("参考图资产缺失（sha256 " + String(item.sha256).slice(0, 12) + "…），请重新上传。");
      }
      payload.push({
        role: item.role,
        media_type: asset.media_type || "image/png",
        sha256: item.sha256,
        data_base64: await blobToBase64(asset.blob),
      });
    }
    return payload;
  }

  /** 网关调用只返回「信封」；分类一律交给 domain（classifySubmitEnvelope / classifyStatusEnvelope）。 */
  async function postImageJson(path, body) {
    let response;
    try {
      response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch (error) {
      return { envelope: null, status: 0, transport: true };
    }
    let envelope = null;
    try {
      envelope = await response.json();
    } catch (error) {
      envelope = null;
    }
    if (!envelope || typeof envelope !== "object") {
      return {
        envelope: {
          ok: false,
          unknown: true,
          error: {
            family: "provider_unknown",
            code: "RESPONSE_UNREADABLE",
            message: "服务端返回 HTTP " + response.status + "，但响应不是约定的 JSON。",
            retry_policy: "requires_review",
          },
        },
        status: response.status,
        transport: false,
      };
    }
    return { envelope: envelope, status: response.status, transport: false };
  }

  /**
   * 取回候选字节：POST /api/v2/images/result。
   * 只接受 200 + image/png；服务端声明的 X-Image-Sha256 与本机重算的 sha256 必须一致，
   * 不一致就不保存（宁可没有候选，也不存不可信字节）。
   */
  async function fetchImageResultBytes(taskId) {
    let response;
    try {
      response = await fetch(IMAGE_RESULT_PATH, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task_id: taskId }),
      });
    } catch (error) {
      return {
        ok: false, reason: "transport",
        message: "取回候选时连接中断；记录保持原样，可以重试（不会重新生成）。",
      };
    }
    if (!response.ok) {
      let envelope = null;
      try {
        envelope = await response.json();
      } catch (error) {
        envelope = null;
      }
      const failure = envelope && envelope.error ? envelope.error : null;
      return {
        ok: false, reason: "http", status: response.status,
        message: failure
          ? "取回候选失败：" + failure.family + " / " + failure.code + "：" + failure.message
          : "取回候选失败（HTTP " + response.status + "）；记录保持原样，可以重试。",
      };
    }
    const mediaType = String(response.headers.get("content-type") || "");
    if (!mediaType.includes("image/png")) {
      return {
        ok: false, reason: "bad_media",
        message: "结果不是 PNG（" + (mediaType || "无类型") + "），候选未保存。",
      };
    }
    const buffer = await response.arrayBuffer();
    const sha = await sha256Hex(buffer);
    const declared = String(response.headers.get("x-image-sha256") || "").toLowerCase();
    if (declared && declared !== sha) {
      return {
        ok: false, reason: "hash_mismatch",
        message: "下载字节的 sha256 与服务端声明不一致，候选未保存。",
      };
    }
    return {
      ok: true, buffer: buffer, sha256: sha, media_type: "image/png",
      provider_id: response.headers.get("x-provider-id") || "",
      model_id: response.headers.get("x-model-id") || "",
      task_id: response.headers.get("x-task-id") || taskId,
    };
  }

  /**
   * 候选的确定性审核报告（V2.5.1）：绑定 candidate_id + 合同版本 + sha256；
   * 评估或保存失败都不影响候选本身（界面显示报告缺失，下次打开项目会补建）。
   */
  async function ensureReviewReport(shotId, candidate, bytes) {
    const existing = reviewReports.get(candidate.candidate_id);
    if (existing && reviewIsCurrent(existing.report, candidate)) return existing;
    let view = bytes || null;
    if (!view) {
      const asset = await repository.assets.get(projectId, candidate.asset_sha256);
      if (asset && asset.blob instanceof Blob) {
        view = new Uint8Array(await asset.blob.arrayBuffer());
      }
    }
    const shot = (suitePlan && Array.isArray(suitePlan.shots) ? suitePlan.shots : [])
      .find((item) => item && item.shot_id === shotId);
    const deterministic = evaluateCandidateFindings({
      candidate: candidate,
      bytes: view,
      roleId: shot ? shot.role_id : null,
    });
    // 合同版本或规则升级后重建报告：同一候选字节上的 VLM 复核块整体带过去；
    // 旧规则与当前注册表不兼容时丢弃复核部分（回到「VLM 未检查」），不伪造结论。
    const previous = existing && existing.report && existing.report.vlm
      && existing.report.vlm.asset_sha256 === candidate.asset_sha256 ? existing.report : null;
    const carried = previous
      ? previous.findings.filter((item) => item && item.layer === "vlm") : [];
    let report = null;
    if (previous) {
      try {
        report = buildReviewReport({
          candidate: candidate,
          findings: deterministic.concat(carried),
          vlm: previous.vlm,
          at: new Date().toISOString(),
        });
      } catch (error) {
        report = null;
      }
    }
    if (!report) {
      report = buildReviewReport({
        candidate: candidate, findings: deterministic, at: new Date().toISOString(),
      });
    }
    try {
      const saved = await repository.documents.save(projectId, {
        kind: REVIEW_KIND, documentId: candidate.candidate_id, payload: report,
      });
      reviewReports.set(candidate.candidate_id, { report: report, version: saved.version });
    } catch (error) {
      // 报告保存失败不改写候选：内存里保留这次评估，界面可见，下次打开项目重试。
      reviewReports.set(candidate.candidate_id, { report: report, version: 0 });
    }
    return reviewReports.get(candidate.candidate_id);
  }

  /**
   * V2.5.2：把目标 Shot 的最新候选投影成一次复核请求。
   * 图片字节只从 IndexedDB 读；资料缺失或超上限时抛错（调用方转为未完成，不送半份资料）。
   */
  async function buildReviewRequest(shotId, candidate) {
    const asset = await repository.assets.get(projectId, candidate.asset_sha256);
    if (!asset || !(asset.blob instanceof Blob)) {
      throw new Error("候选字节缺失，无法复核；请重新生成或重新导入项目。");
    }
    if (asset.blob.size > MAX_REVIEW_IMAGE_BYTES) {
      throw new Error("候选字节超过复核上限（" + MAX_REVIEW_IMAGE_BYTES + " 字节），未发起复核。");
    }
    const shot = (suitePlan && Array.isArray(suitePlan.shots) ? suitePlan.shots : [])
      .find((item) => item && item.shot_id === shotId) || null;
    const specEntry = shotSpecEntry(shotId);
    const spec = specEntry ? specEntry.spec : (shot ? emptyShotSpecFromShot(shot) : null);
    const references = shot
      ? selectReferences(shot, (Array.isArray(intake.references) ? intake.references : [])
          .map((item) => ({ role: item.role, sha256: item.asset_sha256 })))
        .slice(0, MAX_REVIEW_REFERENCES)
      : [];
    const referencePayload = await buildSubmitReferences(references);
    const facts = [];
    for (const entry of slots.values()) {
      const slot = entry && entry.slot ? entry.slot : null;
      if (!slot || slot.status !== "confirmed") continue;
      const value = Array.isArray(slot.value) ? slot.value.join("；") : String(slot.value);
      facts.push({
        label: String(slot.label || slot.slot_id).slice(0, 60),
        value: value.slice(0, 200),
      });
      if (facts.length >= 20) break;
    }
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
        title: String((shot && (shot.role_label || shot.role_id)) || "图片任务").slice(0, 200),
        purpose: spec ? String(spec.purpose || "").slice(0, 500) : "",
        keep_items: spec ? spec.keep.slice(0, 8) : [],
        allow_changes: spec ? spec.change_allowed.slice(0, 8) : [],
      },
      platform: ANALYZE_PLATFORM,
      product_facts: facts,
      locale: ANALYZE_LOCALE,
    };
  }

  /**
   * V2.5.2：对目标 Shot 的最新候选执行一次 VLM 复核。
   * 失败信封与传输失败都投影成 Unknown（保留分类原因）；不自动采纳、不阻塞人工审核。
   */
  async function reviewCandidate(shotId) {
    if (!projectId) return { skipped: true, reason: "no_project" };
    if (reviewInFlight.has(shotId)) return { skipped: true, reason: "in_flight" };
    reviewInFlight.add(shotId);
    renderAttempts();
    try {
      const stored = latestStoredCandidateOf(shotId);
      const candidate = stored && stored.record ? stored.record : stored;
      if (!candidate) return { skipped: true, reason: "no_candidate" };
      const current = reviewReports.get(candidate.candidate_id);
      if (!current || !reviewIsCurrent(current.report, candidate)) {
        await ensureReviewReport(shotId, candidate, null);
      }
      let request;
      try {
        request = await buildReviewRequest(shotId, candidate);
      } catch (error) {
        return {
          failed: true, reason: "request_invalid",
          message: (error && error.message) || "复核请求无法构建。",
        };
      }
      let envelope = null;
      try {
        const response = await fetch(REVIEW_PATH, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(request),
        });
        envelope = await response.json().catch(() => null);
      } catch (error) {
        envelope = null;
      }
      if (!envelope || typeof envelope !== "object") {
        envelope = {
          ok: false, unknown: true,
          error: {
            family: "internal", code: "REVIEW_TRANSPORT",
            message: "复核服务没有返回可解析的结果（服务可能未启动）。",
            retry_policy: "requires_review",
          },
        };
      }
      const entry = reviewReports.get(candidate.candidate_id);
      let merged = null;
      try {
        merged = mergeVlmReview({
          report: entry.report, candidate: candidate, review: envelope,
          at: new Date().toISOString(),
        });
      } catch (error) {
        return {
          failed: true, reason: "merge_invalid",
          message: (error && error.message) || "复核结果无法合并进报告。",
        };
      }
      try {
        const saved = await repository.documents.save(projectId, {
          kind: REVIEW_KIND, documentId: candidate.candidate_id, payload: merged,
        });
        reviewReports.set(candidate.candidate_id, { report: merged, version: saved.version });
      } catch (error) {
        reviewReports.set(candidate.candidate_id, { report: merged, version: 0 });
      }
      return {
        ok: envelope.ok === true,
        outcome: merged.vlm.outcome,
        candidate_id: candidate.candidate_id,
        summary: reviewSummaryText(merged),
      };
    } finally {
      reviewInFlight.delete(shotId);
      renderAttempts();
    }
  }

  /**
   * 候选保存核心：把一次成功的生成变成 IndexedDB 里的字节 + 元数据记录。
   * 幂等：同一 action 已有候选则跳过；字节走内容寻址，同 hash 只存一份。
   * 配额不足不产生半份记录：asset 事务失败就没有记录，界面给出可恢复指引。
   */
  async function ensureCandidateStored(shotId, options = {}) {
    if (!projectId) return { skipped: true, reason: "no_project" };
    if (candidateInFlight.has(shotId)) return { skipped: true, reason: "in_flight" };
    candidateInFlight.add(shotId);
    try {
      const latest = latestAttemptOf(shotId);
      if (!latest) return { skipped: true, reason: "no_attempt" };
      const record = latest.record;
      const decision = candidateStoreDecision({
        attempt: record, candidates: candidateChainOf(shotId),
      });
      if (!decision.needed) {
        if (decision.reason === "already_stored" && decision.candidate) {
          const existing = decision.candidate.record || decision.candidate;
          try {
            await ensureReviewReport(shotId, existing, null);
          } catch (error) {
            // 旧候选的报告补建是尽力而为，不改变幂等语义。
          }
        }
        return { skipped: true, reason: decision.reason };
      }
      const fetched = await fetchImageResultBytes(record.task_id);
      if (!fetched.ok) {
        return { failed: true, reason: fetched.reason, message: fetched.message };
      }
      if (fetched.buffer.byteLength > MAX_CANDIDATE_BYTES) {
        return {
          failed: true, reason: "too_large",
          message: "结果字节超过护栏上限（" + MAX_CANDIDATE_BYTES + " 字节），候选未保存。",
        };
      }
      let dimensions;
      try {
        dimensions = parsePngDimensions(new Uint8Array(fetched.buffer));
      } catch (error) {
        return {
          failed: true, reason: "bad_bytes",
          message: (error && error.message) || "结果不是可解析的 PNG，候选未保存。",
        };
      }
      let reviewSummary = null;
      let asset;
      try {
        asset = await repository.assets.put(projectId, {
          bytes: fetched.buffer,
          mediaType: "image/png",
          originalName: shotId + "-" + record.action_id.slice(0, 8) + ".png",
          role: "candidate",
          width: dimensions.width,
          height: dimensions.height,
        });
        const candidate = buildCandidateRecord({
          shotId: shotId,
          attempt: record,
          assetSha256: asset.sha256,
          byteSize: asset.byte_size,
          width: dimensions.width,
          height: dimensions.height,
          at: new Date().toISOString(),
        });
        const saved = await repository.documents.save(projectId, {
          kind: CANDIDATE_KIND, documentId: shotId, payload: candidate,
        });
        rememberCandidate(shotId, { record: candidate, version: saved.version });
        try {
          const reviewEntry = await ensureReviewReport(shotId, candidate,
            new Uint8Array(fetched.buffer));
          reviewSummary = reviewEntry ? reviewSummaryText(reviewEntry.report) : null;
        } catch (error) {
          reviewSummary = null;
        }
      } catch (error) {
        if (error && error.code === "QUOTA_EXCEEDED") {
          return {
            failed: true, reason: "quota",
            message: "浏览器存储空间不足，候选未保存（记录保持原样）。"
              + "可以先导出项目或清理旧数据，再点「保存候选图片」重试。",
          };
        }
        return {
          failed: true, reason: "storage",
          message: (error && error.message) || "候选保存失败；记录保持原样，可以重试。",
        };
      }
      return {
        stored: true, candidate_id: record.action_id, sha256: asset.sha256,
        width: dimensions.width, height: dimensions.height, byte_size: asset.byte_size,
        review: reviewSummary,
      };
    } finally {
      candidateInFlight.delete(shotId);
      if (!options.quiet) renderAttempts();
    }
  }

  /** 单张「保存候选图片」按钮入口：只翻译结果，不做批次策略。 */
  async function handleStoreCandidate(shotId) {
    clearError(elements.attemptError);
    const result = await ensureCandidateStored(shotId);
    if (result.stored) {
      elements.attemptStatus.textContent = "候选已保存：sha256 " + result.sha256.slice(0, 12)
        + "…（" + result.width + "×" + result.height + "）。"
        + (result.review ? " " + result.review : "");
    } else if (result.failed) {
      showError(elements.attemptError, result.message);
    } else if (result.reason === "already_stored") {
      elements.attemptStatus.textContent = "这条记录的候选已在本地，无需重复保存。";
    } else if (result.reason === "not_succeeded") {
      showError(elements.attemptError, "这次生成还没有成功结论，暂不能保存候选。");
    } else if (result.reason === "no_task_id") {
      showError(elements.attemptError, "这条记录没有任务编号，无法取回候选。");
    } else if (result.reason === "no_attempt") {
      showError(elements.attemptError, "这张图还没有生成记录。");
    }
    return result;
  }

  /** 预览 URL 缓存：每个候选一个 object URL，关闭项目时统一撤销。 */
  async function ensurePreviewUrl(shotId, actionId, assetSha256) {
    const key = shotId + ":" + actionId;
    if (previewUrls.has(key)) return previewUrls.get(key);
    const asset = await repository.assets.get(projectId, assetSha256);
    if (!asset || !(asset.blob instanceof Blob)) return null;
    const url = URL.createObjectURL(asset.blob);
    previewUrls.set(key, url);
    return url;
  }

  /* ------------------------------------------- 候选比较与审核清单（V2.5.3） */

  /**
   * 面板只是投影：候选、报告、参考图全部来自 IndexedDB 已经存在的事实，
   * 排序与默认目标由 domain/compare.js 决定（唯一权威），这里不重算报告、不写任何记录。
   */
  function attemptsByActionId() {
    const map = {};
    for (const record of allAttemptRecords()) {
      if (record && typeof record.action_id === "string") map[record.action_id] = record;
    }
    return map;
  }

  /** 每张图的候选行（异常优先）+ 计划顺序；报告只在 reviewIsCurrent 为真时参与。 */
  function compareInventory() {
    const shots = suitePlan ? suitePlanSummary(suitePlan, suiteContext()).shots : [];
    const rowsByShotId = {};
    const attempts = attemptsByActionId();
    for (const item of shots) {
      const chain = candidateChainOf(item.shot_id);
      const reports = {};
      for (const entry of chain) {
        const candidate = entry && entry.record ? entry.record : entry;
        if (!candidate || typeof candidate.candidate_id !== "string") continue;
        const existing = reviewReports.get(candidate.candidate_id);
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

  function compareTabId(candidateId) {
    return "compare-tab-" + String(candidateId).replace(/[^A-Za-z0-9_-]/g, "-");
  }

  function compareStateLabel(row) {
    return COMPARE_STATE_TEXT[row.review_state] || row.review_state;
  }

  /**
   * 返工入口的状态：只有「正看着一条有字节的候选」才可发起。
   * 这里只投影 candidate_id + sha256，不写任何记录（写记录在相邻的独立返工区）。
   */
  function updateReworkEntry(shot, row) {
    const available = Boolean(shot && row && row.record && row.asset_sha256);
    elements.reworkOpen.disabled = !available;
    if (available) {
      elements.reworkOpen.dataset.shotId = shot.shot_id;
      elements.reworkOpen.dataset.candidateId = row.candidate_id;
      elements.reworkOpen.dataset.candidateSha256 = row.asset_sha256;
    } else {
      delete elements.reworkOpen.dataset.shotId;
      delete elements.reworkOpen.dataset.candidateId;
      delete elements.reworkOpen.dataset.candidateSha256;
    }
  }

  function openCompare(shotId, options = {}) {
    compareShotId = shotId;
    compareCandidateId = options.candidateId || null;
    renderCompare();
    if (options.focus === true) {
      const active = elements.compareCandidates.querySelector('[role="tab"][aria-selected="true"]');
      if (active) active.focus();
    }
  }

  /** 切换查看目标：不改规则、不写存储，只换清单与 aria 选中态，避免重建列表时丢焦点。 */
  function selectCompareCandidate(candidateId, options = {}) {
    // 换一条候选时收起返工区（它绑定打开那一刻的候选身份），草稿保留。
    if (reworkShotId !== null && candidateId !== compareCandidateId) {
      closeReworkPanel({ focusCandidate: false });
    }
    if (adoptShotId !== null && candidateId !== compareCandidateId) {
      closeAdoptPanel({ focusCandidate: false });
    }
    compareCandidateId = candidateId;
    const tabs = elements.compareCandidates.querySelectorAll('[role="tab"]');
    for (const tab of tabs) {
      const selected = tab.dataset.candidateId === candidateId;
      tab.setAttribute("aria-selected", selected ? "true" : "false");
      tab.tabIndex = selected ? 0 : -1;
      if (selected && options.focus === true) tab.focus();
    }
    const inventory = compareInventory();
    const rows = inventory.rowsByShotId[compareShotId] || [];
    const shot = ((suitePlan && suitePlan.shots) || [])
      .find((item) => item && item.shot_id === compareShotId) || null;
    const row = rows.find((item) => item.candidate_id === candidateId) || null;
    renderCompareChecklist(shot, row);
    updateReworkEntry(shot, row);
    updateAdoptEntry(shot, row);
    elements.compareStatus.textContent = "";
  }

  function renderCompare() {
    const ready = understandingReady && Boolean(suitePlan);
    if (!ready || !compareShotId) {
      elements.comparePanel.hidden = true;
      elements.compareCandidates.innerHTML = "";
      elements.compareChecklist.innerHTML = "";
      elements.compareReferences.innerHTML = "";
      elements.compareBasisTitle.textContent = "";
      closeReworkPanel({ focusCandidate: false });
      updateReworkEntry(null, null);
      closeAdoptPanel({ focusCandidate: false });
      updateAdoptEntry(null, null);
      return;
    }
    const shot = ((suitePlan && suitePlan.shots) || [])
      .find((item) => item && item.shot_id === compareShotId) || null;
    if (!shot) {
      compareShotId = null;
      renderCompare();
      return;
    }
    const inventory = compareInventory();
    const rows = inventory.rowsByShotId[compareShotId] || [];
    if (!rows.length) {
      compareShotId = null;
      renderCompare();
      return;
    }
    const targetId = rows.some((row) => row.candidate_id === compareCandidateId)
      ? compareCandidateId : defaultCompareTargetId(rows);
    compareCandidateId = targetId;
    elements.comparePanel.dataset.compareContract = COMPARE_CONTRACT_VERSION;
    elements.comparePanel.dataset.shotId = compareShotId;
    elements.comparePanel.hidden = false;
    const counts = compareCounts(rows);
    const parts = ["候选 " + counts.total];
    if (counts.pending) parts.push("待处理 " + counts.pending);
    if (counts.unknown) parts.push("未知 " + counts.unknown);
    if (counts.unchecked) parts.push("未检查 " + counts.unchecked);
    elements.compareSubject.textContent = shotLabelOf(compareShotId) + " · " + parts.join(" · ");
    const nextShot = nextPendingShotId({
      rowsByShotId: inventory.rowsByShotId,
      shotOrder: inventory.shots.map((item) => item.shot_id),
      currentShotId: compareShotId,
    });
    elements.compareJump.disabled = !nextShot;
    elements.compareJump.dataset.targetShot = nextShot || "";
    elements.compareStatus.textContent = "";
    renderCompareCandidates(rows, targetId);
    const targetRow = rows.find((row) => row.candidate_id === targetId) || null;
    renderCompareChecklist(shot, targetRow);
    updateReworkEntry(shot, targetRow);
    updateAdoptEntry(shot, targetRow);
    refreshCompareReferences(shot).catch(handleInternalError);
  }

  function renderCompareCandidates(rows, targetId) {
    const list = elements.compareCandidates;
    list.innerHTML = "";
    for (const row of rows) {
      const item = createElement("li");
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
        className: "badge " + (COMPARE_STATE_BADGE[row.review_state] || "is-review-unchecked"),
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
      const source = [];
      if (row.task_id) source.push("task " + String(row.task_id).slice(0, 8));
      else if (row.attempt_action_id) source.push("action " + String(row.attempt_action_id).slice(0, 8));
      if (row.width && row.height) source.push(row.width + "×" + row.height);
      if (row.created_at) source.push(shortTime(row.created_at));
      source.push("sha256 " + String(row.asset_sha256).slice(0, 12) + "…");
      main.append(createElement("span", { className: "meta", text: source.join(" · ") }));
      main.append(createElement("p", { className: "compare-headline", text: compareRowHeadline(row) }));
      card.append(main);
      card.addEventListener("click", () => { selectCompareCandidate(row.candidate_id); });
      item.append(card);
      list.append(item);
    }
  }

  function compareFindingRow(finding) {
    const item = createElement("li", {
      className: "compare-finding",
      attrs: { "data-severity": finding.severity, "data-rule-id": finding.rule_id },
    });
    const head = createElement("div", { className: "compare-card-head" });
    head.append(createElement("span", {
      className: "badge " + (SEVERITY_BADGE[finding.severity] || "is-review-unknown"),
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
  }

  /** 这张图实际会发送的参考图（与提交时同一选择函数），用作比较的左边一栏。 */
  async function refreshCompareReferences(shot) {
    const token = ++compareToken;
    const references = selectReferences(shot, (Array.isArray(intake.references) ? intake.references : [])
      .map((item) => ({ role: item.role, sha256: item.asset_sha256 })));
    const entries = [];
    for (const reference of references) {
      const asset = await repository.assets.get(projectId, reference.sha256);
      entries.push({ reference, asset });
    }
    if (token !== compareToken) return;
    const list = elements.compareReferences;
    list.innerHTML = "";
    if (!entries.length) {
      elements.compareBasisTitle.textContent = "这张图没有可用参考图（现在提交会被拒绝）。";
      return;
    }
    elements.compareBasisTitle.textContent = "这张图实际发送的参考图（" + entries.length + " 张）";
    for (const entry of entries) {
      const item = createElement("li", { attrs: { "data-reference-sha256": entry.reference.sha256 } });
      const url = await ensurePreviewUrl("参考图", entry.reference.sha256, entry.reference.sha256);
      if (token !== compareToken) return;
      if (url) {
        item.append(createElement("img", {
          attrs: { src: url, alt: "参考图 " + entry.reference.role, loading: "lazy" },
        }));
      } else {
        item.append(createElement("span", { className: "meta", text: "资产缺失" }));
      }
      item.append(createElement("span", {
        className: "meta", text: (ROLE_TEXT[entry.reference.role] || entry.reference.role)
          + " · " + String(entry.reference.sha256).slice(0, 8) + "…",
      }));
      list.append(item);
    }
  }

  function handleCompareKeydown(event) {
    const tabs = Array.from(elements.compareCandidates.querySelectorAll('[role="tab"]'));
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
      const entry = elements.attemptList.querySelector(
        'button[data-compare-action="' + compareShotId + '"]');
      if (entry) entry.focus(); else elements.compareClose.focus();
      return;
    } else {
      return;
    }
    event.preventDefault();
    selectCompareCandidate(tabs[next].dataset.candidateId, { focus: true });
  }

  function renderAttempts() {
    const ready = understandingReady && Boolean(suitePlan);
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
      const chain = attemptChainOf(item.shot_id);
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

      const row = createElement("div", {
        className: "attempt-row",
        attrs: { "data-shot-id": item.shot_id, "data-attempt-state": state || "none" },
      });
      const head = createElement("div", { className: "attempt-head" });
      head.append(createElement("span", { className: "name", text: item.label }));
      head.append(createElement("span", {
        className: "badge " + (record ? attemptBadgeClass(state) : "is-missing"),
        text: record ? attemptStateLabel(state) : "尚未生成",
      }));
      head.append(createElement("span", {
        className: "meta",
        text: entry
          ? "Prompt v" + entry.version + " · " + String(entry.record.hash).slice(0, 12) + "…"
          : "未编译 Prompt",
      }));
      if (stale && stale.stale) {
        head.append(createElement("span", {
          className: "badge is-attempt-stale",
          text: "基于旧版本 v" + stale.attempt_version,
        }));
      }
      row.append(head);
      if (record) {
        const parts = ["action " + record.action_id];
        if (record.task_id) parts.push("task " + record.task_id);
        parts.push("提交 " + shortTime(record.created_at));
        if (record.updated_at !== record.created_at) parts.push("更新 " + shortTime(record.updated_at));
        row.append(createElement("p", { className: "meta attempt-task", text: parts.join(" · ") }));
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
          const stored = candidateForAttemptRecord(item.shot_id, record.action_id);
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
                + Math.max(1, Math.round(candidate.byte_size / 1024)) + " KB · sha256 "
                + candidate.asset_sha256.slice(0, 12) + "…（预览来自 IndexedDB 里的字节）",
            }));
            const reviewEntry = reviewReports.get(candidate.candidate_id);
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
              text: reviewInFlight.has(item.shot_id) ? "复核中…" : "自动复核（VLM）",
              attrs: {
                type: "button",
                "data-review-action": candidate.candidate_id,
                title: "调用视觉语言模型找可疑问题；只提示，不自动采纳",
              },
            });
            reviewButton.disabled = reviewInFlight.has(item.shot_id);
            reviewButton.addEventListener("click", async () => {
              const outcome = await reviewCandidate(item.shot_id);
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
        if (candidateChainOf(item.shot_id).length) {
          const compareButton = createElement("button", {
            text: "比较候选（" + candidateChainOf(item.shot_id).length + "）",
            attrs: {
              type: "button",
              "data-compare-action": item.shot_id,
              "aria-expanded": String(compareShotId === item.shot_id),
              title: "对比这张图的参考图、历史候选与审核清单",
            },
          });
          compareButton.addEventListener("click", (event) => {
            openCompare(item.shot_id, { focus: event.detail === 0 });
          });
          row.append(compareButton);
        }
        const selectionEntry = selections.get(item.shot_id) || null;
        const selectionState = deriveSelectionState(selectionEntry ? selectionEntry.record : null,
          candidateChainOf(item.shot_id).map((entry) => entry.record));
        if (selectionEntry || candidateChainOf(item.shot_id).length) {
          row.append(createElement("p", {
            className: "meta attempt-selection",
            attrs: {
              "data-selection-state": selectionState,
              "data-selection-shot": item.shot_id,
            },
            text: selectionSummaryText(selectionEntry ? selectionEntry.record : null, selectionState),
          }));
        }
        if (state === ATTEMPT_STATES.pending_submit && !record.task_id) {
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
      const batchActive = Boolean(batchState && batchState.active);
      const inFlight = attemptInFlight.has(item.shot_id) || busy || batchActive;
      const shotConfirmed = confirmationIsCurrentForShot(item.shot_id);
      const canSubmit = shotConfirmed && Boolean(entry) && !inFlight;
      const reconcileMode = record ? attemptReconcileMode(record) : ATTEMPT_RECONCILE_MODES.none;
      const stuckPending = state === ATTEMPT_STATES.pending_submit && !record.task_id;
      if (reconcileMode === ATTEMPT_RECONCILE_MODES.by_task) {
        const button = createElement("button", { text: "核对任务", attrs: { type: "button" } });
        button.disabled = inFlight;
        button.addEventListener("click", () => { handleReconcileAttempt(item.shot_id); });
        actions.append(button);
      }
      if (!record) {
        const button = createElement("button", {
          className: "primary", text: "生成这张图", attrs: { type: "button" },
        });
        button.disabled = !canSubmit;
        button.addEventListener("click", () => { handleSubmitAttempt(item.shot_id); });
        actions.append(button);
      } else if (stuckPending || state === ATTEMPT_STATES.unknown) {
        const button = createElement("button", {
          text: "新建 action（放弃核对）", attrs: { type: "button" },
        });
        button.disabled = !canSubmit;
        button.addEventListener("click", () => {
          handleSubmitAttempt(item.shot_id, { explicitNew: true });
        });
        actions.append(button);
      } else if (state === ATTEMPT_STATES.failed) {
        const button = createElement("button", {
          text: "重试（新建 action）", attrs: { type: "button" },
        });
        button.disabled = !canSubmit;
        button.addEventListener("click", () => {
          handleSubmitAttempt(item.shot_id, { explicitNew: true });
        });
        actions.append(button);
      } else if (state === ATTEMPT_STATES.succeeded) {
        const stored = candidateForAttemptRecord(item.shot_id, record.action_id);
        if (!stored) {
          const save = createElement("button", {
            className: "primary", text: "保存候选图片", attrs: { type: "button" },
          });
          save.disabled = inFlight || candidateInFlight.has(item.shot_id);
          save.addEventListener("click", () => { handleStoreCandidate(item.shot_id); });
          actions.append(save);
        }
        const button = createElement("button", {
          text: "再生成一张（新建 action）", attrs: { type: "button" },
        });
        button.disabled = !canSubmit;
        button.addEventListener("click", () => {
          handleSubmitAttempt(item.shot_id, { explicitNew: true });
        });
        actions.append(button);
      } else if (attemptIsActive(state)) {
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
        details.append(createElement("summary", { text: "历史 " + chain.length + " 次提交（只追加，不覆盖）" }));
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
  }

  /**
   * 单张提交核心：先落库（pending_submit），再发请求。
   * 重入保护在函数第一行生效：双击 / 连点只会产生一条 Attempt。
   * 返回信封分类（供单张界面与批次循环共用判断）；批次策略不在这里。
   */
  async function performSubmitAttempt(shotId, options = {}) {
    if (!projectId || !suitePlan) return { skipped: true, reason: "not_ready" };
    if (attemptInFlight.has(shotId)) return { skipped: true, reason: "in_flight" };
    attemptInFlight.add(shotId);
    try {
      if (!confirmationIsCurrentForShot(shotId)) {
        return { skipped: true, reason: "no_confirmation" };
      }
      const blocking = blockingAttemptFor(allAttemptRecords(), shotId);
      // 显式「放弃核对」只允许放弃没有任务编号、无法核对的 pending 记录；
      // 有 task id 的记录仍然只能先核对（防重复提交的语义不变）。
      const abandonStuck = Boolean(options.explicitNew) && Boolean(blocking)
        && blocking.state === ATTEMPT_STATES.pending_submit && !blocking.task_id;
      if (blocking && !abandonStuck) {
        return { skipped: true, reason: "blocked", blocking: blocking };
      }
      const entry = promptRecordOf(shotId);
      if (!entry) return { skipped: true, reason: "no_prompt" };
      const shot = suitePlan.shots.find((item) => item.shot_id === shotId);
      if (!shot) return { skipped: true, reason: "shot_missing" };
      const references = selectReferences(shot, intake.references.map((item) => ({
        role: item.role, sha256: item.asset_sha256,
      })));
      if (references.length === 0) return { skipped: true, reason: "no_references" };
      let referencePayload;
      try {
        referencePayload = await buildSubmitReferences(references);
      } catch (error) {
        return {
          skipped: true, reason: "reference_read_failed",
          message: (error && error.message) || "参考图读取失败，没有提交。",
        };
      }
      const identity = attemptProviderIdentity();
      const parameters = attemptParametersOf(entry);
      const actionId = newActionId();
      const at = new Date().toISOString();
      const record = buildAttemptRecord({
        actionId: actionId,
        shotId: shotId,
        prompt: { version: entry.version, hash: entry.record.hash },
        references: references,
        provider: { provider_id: identity.provider_id, model_id: identity.model_id },
        parameters: parameters,
        at: at,
        note: options.explicitNew ? "用户显式新建 action" : (options.note || "用户发起生成"),
      });
      const saved = await repository.documents.save(projectId, {
        kind: ATTEMPT_KIND, documentId: shotId, payload: record,
      });
      rememberAttempt(shotId, { record: record, version: saved.version });
      renderAttempts();
      elements.attemptStatus.textContent = "已登记 " + actionId + "（pending_submit），正在提交…";
      const { envelope } = await postImageJson(IMAGE_SUBMIT_PATH, {
        action_id: actionId,
        prompt: entry.record.compiled.text,
        references: referencePayload,
        size: parameters.size,
      });
      const outcome = nextFromSubmitEnvelope(record, envelope, { at: new Date().toISOString() });
      const savedNext = await repository.documents.save(projectId, {
        kind: ATTEMPT_KIND, documentId: shotId, payload: outcome.record,
      });
      rememberAttempt(shotId, { record: outcome.record, version: savedNext.version });
      // 提交直接到终态（成功）时，同一步把候选字节存进 IndexedDB；失败不掩盖提交结论。
      let candidate = null;
      if (outcome.record.state === ATTEMPT_STATES.succeeded) {
        candidate = await ensureCandidateStored(shotId, { quiet: true });
      }
      return { ...outcome.outcome, record: outcome.record, submitted: true, candidate: candidate };
    } catch (error) {
      return {
        thrown: true, state: null, error: null,
        message: (error && error.message) || "提交没有完成；已登记的身份与历史仍然保留。",
      };
    } finally {
      attemptInFlight.delete(shotId);
      renderAttempts();
    }
  }

  /** 单张提交（按钮入口）：只负责把核心结果翻译成界面反馈，批次策略不在这里。 */
  async function handleSubmitAttempt(shotId, options = {}) {
    clearError(elements.attemptError);
    const outcome = await performSubmitAttempt(shotId, options);
    if (outcome.skipped) {
      if (outcome.reason === "no_confirmation") {
        showError(elements.attemptError,
          "生成前确认缺失或已过期：先回到「生成前确认」重新确认，再提交。");
      } else if (outcome.reason === "blocked") {
        const blocking = outcome.blocking;
        showError(elements.attemptError, "同一张图已经有一条进行中的生成（"
          + attemptStateLabel(blocking.state) + "，action " + blocking.action_id
          + "）。先核对并按结论处理，再新建 action。");
      } else if (outcome.reason === "no_prompt") {
        showError(elements.attemptError, "这张图还没有可用的 Prompt 版本：先编译并保存。");
      } else if (outcome.reason === "shot_missing") {
        showError(elements.attemptError, "这张图已不在套图方案里，先刷新套图规划。");
      } else if (outcome.reason === "no_references") {
        showError(elements.attemptError, "这张图没有可用参考图（至少需要一张）。");
      } else if (outcome.reason === "reference_read_failed") {
        showError(elements.attemptError, outcome.message);
      }
      return outcome;
    }
    if (outcome.thrown) {
      showError(elements.attemptError, outcome.message);
      return outcome;
    }
    const record = outcome.record;
    elements.attemptStatus.textContent = "action " + record.action_id + "：" + attemptStateLabel(record.state)
      + (record.task_id ? "（task " + record.task_id + "）" : "") + "。";
    if (record.state === ATTEMPT_STATES.unknown) {
      showError(elements.attemptError, "这次提交的结果没有确认：不要重复提交。"
        + (record.task_id ? "可以按任务编号核对。" : "没有任务编号，只能显式新建 action。"));
    } else if (record.state === ATTEMPT_STATES.failed) {
      showError(elements.attemptError, "这次提交明确失败：" + record.error.message
        + "（重试策略 " + record.error.retry_policy + "）。");
    }
    if (outcome.candidate && outcome.candidate.failed) {
      showError(elements.attemptError, outcome.candidate.message);
    } else if (outcome.candidate && outcome.candidate.stored) {
      elements.attemptStatus.textContent += " 候选已保存到本地（sha256 "
        + outcome.candidate.sha256.slice(0, 12) + "…）。";
    }
    return outcome;
  }

  /**
   * 按已保存的 task id 核对核心：只用查询推进状态，绝不重提。
   * 服务端没有任务表，因此服务端重启、换标签页都不改变结论。
   */
  async function performReconcileAttempt(shotId) {
    if (!projectId || attemptInFlight.has(shotId)) return { skipped: true, reason: "in_flight" };
    attemptInFlight.add(shotId);
    try {
      const latest = latestAttemptOf(shotId);
      if (!latest || !latest.record.task_id) return { skipped: true, reason: "no_task" };
      const { envelope } = await postImageJson(IMAGE_STATUS_PATH, { task_id: latest.record.task_id });
      const outcome = nextFromStatusEnvelope(latest.record, envelope, { at: new Date().toISOString() });
      if (outcome.outcome.advanced) {
        const saved = await repository.documents.save(projectId, {
          kind: ATTEMPT_KIND, documentId: shotId, payload: outcome.record,
        });
        rememberAttempt(shotId, { record: outcome.record, version: saved.version });
        // 核对推进到成功时，同一步把候选字节存进 IndexedDB；失败不掩盖核对结论。
        let candidate = null;
        if (outcome.record.state === ATTEMPT_STATES.succeeded) {
          candidate = await ensureCandidateStored(shotId, { quiet: true });
        }
        return {
          advanced: true, task_id: latest.record.task_id, state: outcome.record.state,
          candidate: candidate,
        };
      }
      return {
        advanced: false, task_id: latest.record.task_id, state: latest.record.state,
        note: outcome.outcome.note || "记录保持原样",
      };
    } catch (error) {
      return {
        failed: true,
        message: (error && error.message) || "核对没有完成，记录保持原样。",
      };
    } finally {
      attemptInFlight.delete(shotId);
      renderAttempts();
    }
  }

  /** 单张核对（按钮入口）。 */
  async function handleReconcileAttempt(shotId) {
    clearError(elements.attemptError);
    const result = await performReconcileAttempt(shotId);
    if (result.skipped) {
      if (result.reason === "no_task") {
        showError(elements.attemptError, "这条记录没有任务编号，无法核对；只能显式新建 action。");
      }
      return result;
    }
    if (result.failed) {
      showError(elements.attemptError, result.message);
      return result;
    }
    if (result.advanced) {
      elements.attemptStatus.textContent = "已核对 task " + result.task_id + "："
        + attemptStateLabel(result.state) + "。";
      if (result.candidate && result.candidate.failed) {
        showError(elements.attemptError, result.candidate.message);
      } else if (result.candidate && result.candidate.stored) {
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

  function reworkConfirmId(shotId) {
    return REWORK_CONFIRM_PREFIX + shotId;
  }

  /** 返工草稿按图保存；第一次打开时用报告的先看项预选问题与方向，之后保留用户改动。 */
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

  function reworkShotRow(shotId, candidateId) {
    const inventory = compareInventory();
    const rows = inventory.rowsByShotId[shotId] || [];
    return rows.find((item) => item.candidate_id === candidateId) || rows[0] || null;
  }

  function reworkSummaryOf(draft) {
    if (draft && draft.preview) {
      return "预览已就绪：确认并生成会把它保存为 Prompt 新版本（旧版本保留），"
        + "只重新生成这张图；改过问题或方向后需要重新预览。";
    }
    return "选好问题或写下方向 → 预览返工 Prompt → 确认并生成这张图。";
  }

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
  function dirtyReworkDraft(draft) {
    if (!draft || !draft.preview) return;
    draft.preview = null;
    draft.directive = null;
    elements.reworkPreviewBox.hidden = true;
    elements.reworkStatus.hidden = true;
  }

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

  function renderReworkProblems(shotId, draft) {
    const box = elements.reworkProblems;
    const host = box.querySelector(".rework-problem-options") || box;
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
    const basis = ["返工依据：候选 v" + (reworkSource.version === null ? "?" : reworkSource.version),
                   "sha256 " + String(reworkSource.asset_sha256).slice(0, 12) + "…"];
    if (row.top_finding) basis.push("先看：" + row.top_finding.title);
    if (reworkConfirmationIsCurrent(shotId)) basis.push("这张图的返工确认仍然有效");
    elements.reworkBasis.textContent = basis.join(" · ");
    renderReworkProblems(shotId, draft);
    if (elements.reworkDirection.value !== draft.direction) {
      elements.reworkDirection.value = draft.direction;
    }
    renderReworkPreviewBox(draft);
    elements.reworkStatus.hidden = true;
    clearError(elements.reworkError);
    updateReworkControls(shotId, draft);
    const first = elements.reworkProblems.querySelector('input[type="checkbox"]');
    if (first) first.focus();
    panel.scrollIntoView({ block: "nearest" });
  }

  /** 收起返工区：清掉未确认的预览；草稿（问题与方向）按图保留。 */
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
  function focusCompareCandidate(shotId, candidateId) {
    const tab = candidateId ? elements.compareCandidates.querySelector(
      '[role="tab"][data-candidate-id="' + candidateId + '"]') : null;
    if (tab) {
      tab.focus();
      return;
    }
    const entry = elements.attemptList.querySelector(
      'button[data-compare-action="' + shotId + '"]');
    if (entry) entry.focus();
  }

  /** 按建议重填：问题与方向回到报告先看项的默认值，预览作废。 */
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

  function handleReworkCancel() {
    if (reworkInFlight) return;
    closeReworkPanel({ focusCandidate: true });
  }

  /** 预览：按当前问题与方向编译一次；只显示，不写记录。 */
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
        payload: result.payload,
        references: result.references.length,
        text: result.payload.compiled.text,
      };
      renderReworkPreviewBox(draft);
      elements.reworkStatus.hidden = false;
      elements.reworkStatus.textContent = "预览已就绪：确认并生成时会先把它保存为新版本，"
        + "再只提交这一张图；预览本身没有写入任何记录。";
    } catch (error) {
      showError(elements.reworkError, (error && error.message)
        ? error.message + "（预览未生成，旧版本与输入保留）"
        : "预览没有生成，旧版本与输入保留。");
    } finally {
      reworkInFlight = false;
      const current = reworkDrafts.get(shotId);
      if (current) updateReworkControls(shotId, current);
    }
  }

  /** 查看/编辑完整 Prompt：把这次预览落成版本，再把焦点交给这张图的人工编辑区。 */
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
      const fromPreview = Boolean(latest && latest.record.rework
        && latest.record.rework.directive_id === draft.preview.directive_id);
      if (!fromPreview) {
        const saved = await savePromptPayload(shotId, draft.preview.payload);
        version = saved.version;
      }
      renderPrompts();
      renderConfirm();
      const area = elements.promptList.querySelector(
        '[data-shot-id="' + shotId + '"] textarea.prompt-edit-text');
      elements.reworkStatus.hidden = false;
      elements.reworkStatus.textContent = "已保存为 Prompt v" + version
        + "；可以在下方「Prompt 预览与版本」里编辑全文并另存新版本。";
      if (area) {
        area.scrollIntoView({ block: "center" });
        area.focus();
      }
    } catch (error) {
      showError(elements.reworkError, (error && error.message) || "没有打开编辑区。");
    } finally {
      reworkInFlight = false;
      const current = reworkDrafts.get(shotId);
      if (current) updateReworkControls(shotId, current);
    }
  }

  /**
   * 确认并生成这张图：先确保这次返工已经落成 Prompt 版本（发送的永远是这张图最新的版本），
   * 再写「只覆盖这张图」的确认记录、新建 Attempt 并核对一次结论；失败不影响旧候选。
   */
  async function handleReworkSubmit() {
    if (!projectId || !reworkShotId || reworkInFlight) return;
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
      const fromPreview = Boolean(latest && latest.record.rework
        && latest.record.rework.directive_id === draft.preview.directive_id);
      if (!fromPreview) {
        const saved = await savePromptPayload(shotId, draft.preview.payload);
        version = saved.version;
      }
      const sheet = buildScopedSheet([shotId]);
      if (!sheet || !Array.isArray(sheet.shots) || sheet.shots.length === 0) {
        throw new Error("这张图已经不在套图方案里，返工没有提交。");
      }
      if (!sheet.can_submit) throw new Error("这张图当前还有阻断，不能提交返工。");
      const snapshot = confirmationSnapshot(sheet);
      const hash = await promptHash(snapshot, { digest: sha256Hex });
      const payload = buildConfirmationRecord({
        sheet: sheet, hash: hash, confirmedAt: new Date().toISOString(),
      });
      const problems = checkConfirmationRecord(payload);
      if (problems.length > 0) throw new Error(problems[0].message);
      const savedConfirm = await repository.documents.save(projectId, {
        kind: CONFIRM_KIND, documentId: reworkConfirmId(shotId), payload: payload,
      });
      reworkConfirmations.set(shotId, { payload: payload, version: savedConfirm.version });
      const outcome = await handleSubmitAttempt(shotId, {
        note: "单图返工：" + reworkSummaryText(draft.directive).slice(0, 120),
      });
      if (outcome && outcome.skipped) {
        throw new Error("返工提交被跳过（" + outcome.reason + "）。");
      }
      if (outcome && outcome.thrown) throw new Error(outcome.message);
      await handleReconcileAttempt(shotId);
      const latestAttempt = latestAttemptOf(shotId);
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
      showError(elements.reworkError,
        (error && error.message) || "返工没有提交；旧候选与旧 Prompt 不受影响。");
    } finally {
      reworkInFlight = false;
      const current = reworkDrafts.get(shotId);
      if (current) updateReworkControls(shotId, current);
    }
  }

  /* ------------------------------------------------------------ 整套批次执行 */

  const BATCH_POLL_INTERVAL_MS = 4000;
  const BATCH_POLL_MAX_ROUNDS = 300;

  function sleep(ms) {
    return new Promise((resolve) => { window.setTimeout(resolve, ms); });
  }

  function shotLabelOf(shotId) {
    const summary = suitePlan ? suitePlanSummary(suitePlan, suiteContext()) : null;
    const item = (summary ? summary.shots : []).find((shot) => shot.shot_id === shotId);
    return item ? item.label : shotId;
  }

  /** 批次状态 = 套图顺序 + 每张图最新 Attempt + Prompt 就绪状态的投影；没有第二份状态。 */
  function deriveBatch() {
    const summary = suitePlan ? suitePlanSummary(suitePlan, suiteContext()) : null;
    const shots = summary ? summary.shots : [];
    const latest = {};
    for (const item of shots) {
      const entry = latestAttemptOf(item.shot_id);
      latest[item.shot_id] = entry ? entry.record : null;
    }
    return deriveBatchState({
      shots: shots.map((item) => ({ shot_id: item.shot_id, label: item.label })),
      latestAttempts: latest,
      promptReady: (shotId) => Boolean(promptRecordOf(shotId)),
      candidateStored: (shotId) => Boolean(latestStoredCandidateOf(shotId)),
    });
  }

  function renderBatch() {
    if (!elements.batchBar) return;
    const ready = understandingReady && Boolean(suitePlan);
    elements.batchBar.hidden = !ready;
    if (!ready) return;
    const state = deriveBatch();
    const running = Boolean(batchState && batchState.active);
    const confirmed = confirmationIsCurrent();
    const progress = [batchProgressText(state)];
    if (running) {
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

    elements.batchRun.hidden = running;
    const queueReady = state.queue.length > 0;
    const fetchOnly = !queueReady && state.fetch_queue.length > 0;
    elements.batchRun.disabled = running || (queueReady ? !confirmed : !fetchOnly);
    if (queueReady) {
      elements.batchRun.textContent = state.started
        ? "继续生成剩余（" + state.queue.length + " 张）"
        : "整套生成（" + state.queue.length + " 张）";
    } else if (fetchOnly) {
      elements.batchRun.textContent = "保存候选（" + state.fetch_queue.length + " 张）";
    } else if (state.counts.total > 0 && state.all_succeeded) {
      elements.batchRun.textContent = "已全部生成";
    } else {
      elements.batchRun.textContent = "没有待生成的图";
    }
    elements.batchStop.hidden = !running;
    elements.batchReconcile.hidden = state.reconcile_queue.length === 0;
    elements.batchReconcile.disabled = running || state.reconcile_queue.length === 0;
    elements.batchReconcile.textContent = "核对进行中（" + state.reconcile_queue.length + " 张）";
    elements.batchRetry.hidden = state.retry_queue.length === 0;
    elements.batchRetry.disabled = running || !confirmed || state.retry_queue.length === 0;
    elements.batchRetry.textContent = "重试失败（" + state.retry_queue.length + " 张）";
  }

  /**
   * 整套批次：按套图顺序先提交所有「待提交」的图，再按已保存 task id 轮询推进。
   * 停止只停新增提交：不撤销、不覆盖、不删除任何已有记录。
   */
  async function handleBatchRun() {
    if (!projectId || !suitePlan || (batchState && batchState.active)) return;
    clearError(elements.attemptError);
    const plan = deriveBatch();
    if (plan.queue.length === 0 && plan.fetch_queue.length === 0) {
      showError(elements.attemptError, "没有待提交的图；可以核对进行中、重试失败的图或保存候选。");
      return;
    }
    if (plan.queue.length > 0 && !confirmationIsCurrent()) {
      showError(elements.attemptError,
        "生成前确认缺失或已过期：先回到「生成前确认」重新确认，再整套生成。");
      return;
    }
    batchState = {
      active: true, stopped: false, halted: false, haltReason: "", fetchBlocked: "",
      currentShotId: null, phase: "submit",
    };
    renderAttempts();
    let submitted = 0;
    try {
      for (const shotId of plan.queue) {
        if (batchState.stopped || batchState.halted) break;
        if (!confirmationIsCurrent()) {
          batchState.halted = true;
          batchState.haltReason = "生成前确认已过期";
          break;
        }
        batchState.currentShotId = shotId;
        renderBatch();
        const outcome = await performSubmitAttempt(shotId, { note: "整套生成：批次提交" });
        if (outcome.skipped) continue;
        submitted += 1;
        if (outcome.thrown) {
          batchState.halted = true;
          batchState.haltReason = outcome.message || "提交没有完成";
          break;
        }
        if (batchSubmitHalts(outcome)) {
          batchState.halted = true;
          batchState.haltReason = (outcome.error && outcome.error.message)
            || "系统性提交错误（继续提交会产生更多未知记录）";
          break;
        }
      }
      batchState.phase = "poll";
      batchState.currentShotId = null;
      await pollActiveAttempts();
    } catch (error) {
      batchState.halted = true;
      batchState.haltReason = (error && error.message) || "批次执行出现异常";
    } finally {
      const finished = batchState;
      batchState = null;
      renderAttempts();
      const finalState = deriveBatch();
      if (finished && finished.halted) {
        elements.attemptStatus.textContent = "批次已停止新增提交（" + finished.haltReason
          + "）：本批提交 " + submitted + " 张，已有记录全部保留。";
      } else if (finished && finished.stopped) {
        elements.attemptStatus.textContent = "批次已停止：本批提交 " + submitted
          + " 张，已有记录全部保留；可继续核对或继续生成剩余。";
      } else {
        elements.attemptStatus.textContent = "批次结束：" + batchProgressText(finalState);
      }
    }
  }

  /** 轮询在途记录（只查询、不重提）。批次运行中循环到没有可核对的记录为止。 */
  async function pollActiveAttempts(options = {}) {
    const intervalMs = options.intervalMs || BATCH_POLL_INTERVAL_MS;
    const maxRounds = options.maxRounds || BATCH_POLL_MAX_ROUNDS;
    const once = options.once === true;
    for (let round = 0; round < maxRounds; round += 1) {
      if (batchState && batchState.halted) return;
      const state = deriveBatch();
      if (state.reconcile_queue.length === 0 && state.fetch_queue.length === 0) return;
      if (batchState) { batchState.phase = "poll"; renderBatch(); }
      for (const shotId of state.reconcile_queue) {
        if (batchState && batchState.halted) return;
        await performReconcileAttempt(shotId);
      }
      // 候选保存：配额受阻时记录原因并停本轮保存；核对路径不受影响。
      if (!(batchState && batchState.fetchBlocked)) {
        const fetchState = deriveBatch();
        for (const shotId of fetchState.fetch_queue) {
          if (batchState) {
            batchState.currentShotId = shotId;
            batchState.phase = "fetch";
            renderBatch();
          }
          const stored = await ensureCandidateStored(shotId);
          if (stored && stored.failed && stored.reason === "quota") {
            if (batchState) batchState.fetchBlocked = stored.message;
            break;
          }
        }
      }
      renderAttempts();
      if (once) return;
      // 停止只停新增提交：已提交的身份仍然各查一次，给出当前结论后不再轮询。
      if (batchState && batchState.stopped) return;
      const after = deriveBatch();
      if (after.reconcile_queue.length === 0 && after.fetch_queue.length === 0) return;
      if (round === maxRounds - 1 && batchState) {
        batchState.halted = true;
        batchState.haltReason = "上游长时间没有结论，已停止自动核对；记录仍在，可继续核对";
        return;
      }
      await sleep(intervalMs);
    }
  }

  /** 批量的「核对进行中」：所有有任务编号的在途记录各查一次，不重提。 */
  async function handleBatchReconcile() {
    clearError(elements.attemptError);
    const before = deriveBatch();
    if (before.reconcile_queue.length === 0) {
      showError(elements.attemptError, "没有可按任务编号核对的记录。");
      return;
    }
    try {
      await pollActiveAttempts({ once: true });
    } catch (error) {
      showError(elements.attemptError, (error && error.message) || "核对没有完成，记录保持原样。");
      return;
    }
    const after = deriveBatch();
    elements.attemptStatus.textContent = "已核对 " + before.reconcile_queue.length + " 张："
      + batchProgressText(after);
  }

  /** 批量的「重试失败」：只对明确失败的图显式新建 action，绝不动未知与在途记录。 */
  async function handleBatchRetry() {
    if (batchState && batchState.active) return;
    clearError(elements.attemptError);
    if (!confirmationIsCurrent()) {
      showError(elements.attemptError,
        "生成前确认缺失或已过期：先回到「生成前确认」重新确认，再重试。");
      return;
    }
    const plan = deriveBatch();
    if (plan.retry_queue.length === 0) {
      showError(elements.attemptError, "没有明确失败的图可重试。");
      return;
    }
    batchState = {
      active: true, stopped: false, halted: false, haltReason: "", fetchBlocked: "",
      currentShotId: null, phase: "submit",
    };
    renderAttempts();
    let submitted = 0;
    try {
      for (const shotId of plan.retry_queue) {
        if (batchState.stopped || batchState.halted) break;
        batchState.currentShotId = shotId;
        renderBatch();
        const outcome = await performSubmitAttempt(shotId, {
          explicitNew: true, note: "批次重试失败图",
        });
        if (outcome.skipped) continue;
        submitted += 1;
        if (outcome.thrown || batchSubmitHalts(outcome)) {
          batchState.halted = true;
          batchState.haltReason = outcome.thrown
            ? (outcome.message || "提交没有完成")
            : ((outcome.error && outcome.error.message) || "系统性提交错误");
          break;
        }
      }
      batchState.phase = "poll";
      batchState.currentShotId = null;
      await pollActiveAttempts();
    } catch (error) {
      batchState.halted = true;
      batchState.haltReason = (error && error.message) || "重试执行出现异常";
    } finally {
      const finished = batchState;
      batchState = null;
      renderAttempts();
      elements.attemptStatus.textContent = finished && finished.halted
        ? "重试已停止新增提交（" + finished.haltReason + "）：已提交的记录全部保留。"
        : "重试结束：本批提交 " + submitted + " 张；" + batchProgressText(deriveBatch());
    }
  }

  /* ----------------------------------------------- 人工选择与失效（V2.6.1） */

  function selectionEntryOf(shotId) {
    return selections.get(shotId) || null;
  }

  function candidatePayloadsOf(shotId) {
    return candidateChainOf(shotId).map((entry) => entry.record);
  }

  function selectionStateOf(shotId) {
    const entry = selectionEntryOf(shotId);
    return deriveSelectionState(entry ? entry.record : null, candidatePayloadsOf(shotId));
  }

  /** 某张图当前采用的候选（含过期标记）：只读投影，供比较列表做徽标。 */
  function adoptedMarkOf(shotId) {
    const entry = selectionEntryOf(shotId);
    if (!entry || !entry.record || entry.record.action !== "select") return null;
    return { candidate_id: entry.record.candidate_id, state: selectionStateOf(shotId) };
  }

  /** SelectionSet 投影：V2.5.5 / V2.6.2 的唯一输入集合；这里只报告数量，不拦导出。 */
  function selectionSetNow() {
    const summaries = suitePlan ? suitePlanSummary(suitePlan, suiteContext()).shots : [];
    const shots = summaries.map((shot) => ({
      shot_id: shot.shot_id, required: shot.required === true,
    }));
    const selectionsByShot = {};
    for (const [shotId, entry] of selections) selectionsByShot[shotId] = entry.record;
    const candidatesByShotId = {};
    for (const shot of shots) candidatesByShotId[shot.shot_id] = candidatePayloadsOf(shot.shot_id);
    return buildSelectionSet({
      shots: shots, selections: selectionsByShot, candidatesByShotId: candidatesByShotId,
      at: new Date().toISOString(),
    });
  }

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
  function updateAdoptEntry(shot, row) {
    const available = Boolean(shot && row && row.record && row.asset_sha256);
    elements.adoptOpen.disabled = !available;
    if (available) {
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
  function adoptSourceOf(shotId, candidateId) {
    for (const entry of candidateChainOf(shotId)) {
      if (entry.record && entry.record.candidate_id === candidateId) {
        const stored = reviewReports.get(candidateId);
        const report = stored && reviewIsCurrent(stored.report, entry.record)
          ? stored.report : null;
        return { candidate: entry.record, version: entry.version, report: report };
      }
    }
    return null;
  }

  function selectionTextOf(shotId) {
    const entry = selectionEntryOf(shotId);
    return selectionSummaryText(entry ? entry.record : null, selectionStateOf(shotId));
  }

  function renderAdoptPanel() {
    if (!adoptShotId || !adoptSource) return;
    const shotId = adoptShotId;
    const source = adoptSource;
    const entry = selectionEntryOf(shotId);
    const state = selectionStateOf(shotId);
    const summary = suitePlan ? suitePlanSummary(suitePlan, suiteContext()).shots
      .find((item) => item.shot_id === shotId) : null;
    elements.adoptBasis.textContent = shotLabelOf(shotId) + " · 当前" + selectionStateLabel(state)
      + " · 候选 v" + source.version + " · sha256 "
      + String(source.candidate.asset_sha256).slice(0, 12) + "…";
    elements.adoptCurrent.textContent = selectionTextOf(shotId);
    elements.adoptFingerprint.textContent = source.report
      ? "将绑定当前审核报告：" + reviewSummaryText(source.report)
        + "（审核合同 " + String(source.report.review_contract_version) + "）"
      : "这条候选还没有当前审核报告：采用会明确记下「没有报告」，导出前仍需补一份当前报告。";
    const already = Boolean(entry && entry.record && entry.record.action === "select"
      && entry.record.candidate_id === source.candidate.candidate_id && state === "current");
    elements.adoptSubmit.disabled = adoptInFlight || already;
    elements.adoptSubmit.textContent = already ? "已采用这条候选" : "采用这条候选";
    elements.adoptClear.disabled = adoptInFlight
      || !(entry && entry.record && entry.record.action === "select");
    elements.adoptReadiness.textContent = summary && summary.required
      ? "这张图是必需图：导出前必须有当前有效的选择。"
      : "这张图是可选图：采用后仍可改选或取消。";
  }

  function openAdoptPanel() {
    const shotId = elements.adoptOpen.dataset.shotId || null;
    const candidateId = elements.adoptOpen.dataset.candidateId || null;
    if (!shotId || !candidateId) return;
    const source = adoptSourceOf(shotId, candidateId);
    if (!source) {
      elements.compareStatus.textContent = "这条候选已经不在本地候选链里，无法采用。";
      return;
    }
    adoptShotId = shotId;
    adoptCandidateId = candidateId;
    adoptSource = source;
    elements.adoptPanel.hidden = false;
    elements.adoptPanel.dataset.adoptContract = SELECTION_CONTRACT_VERSION;
    elements.adoptPanel.dataset.shotId = shotId;
    elements.adoptPanel.dataset.candidateId = candidateId;
    elements.adoptStatus.textContent = "";
    elements.adoptStatus.hidden = true;
    clearError(elements.adoptError);
    renderAdoptPanel();
    const target = elements.adoptSubmit.disabled ? elements.adoptCancel : elements.adoptSubmit;
    if (target) target.focus();
  }

  function closeAdoptPanel({ focusCandidate = false } = {}) {
    const shotId = adoptShotId;
    const candidateId = adoptCandidateId;
    adoptShotId = null;
    adoptCandidateId = null;
    adoptSource = null;
    elements.adoptPanel.hidden = true;
    elements.adoptStatus.textContent = "";
    elements.adoptStatus.hidden = true;
    clearError(elements.adoptError);
    if (focusCandidate && shotId && candidateId) focusCompareCandidate(shotId, candidateId);
  }

  /** 写一条选择记录：select = 采用 / 改选；clear = 取消采用。失败时不改内存里的旧选择。 */
  async function writeSelectionRecord(action) {
    if (!projectId || !adoptShotId || !adoptSource) return null;
    const shotId = adoptShotId;
    const source = adoptSource;
    const record = buildSelectionRecord({
      selectionId: newActionId(),
      action: action,
      shotId: shotId,
      candidate: action === "select" ? source.candidate : null,
      candidateVersion: action === "select" ? source.version : null,
      report: action === "select" ? source.report : null,
      at: new Date().toISOString(),
    });
    assertSelectionRecord(record);
    const saved = await repository.documents.save(projectId, {
      kind: SELECTION_KIND, documentId: shotId, payload: record,
    });
    const previous = selectionEntryOf(shotId);
    selections.set(shotId, { record: record, version: saved.version });
    return { record: record, version: saved.version, previous: previous };
  }

  async function handleAdoptSubmit() {
    if (adoptInFlight) return;
    adoptInFlight = true;
    elements.adoptStatus.textContent = "";
    elements.adoptStatus.hidden = true;
    clearError(elements.adoptError);
    renderAdoptPanel();
    try {
      const source = adoptSource;
      const result = await writeSelectionRecord("select");
      if (!result) return;
      const replaced = result.previous && result.previous.record
        && result.previous.record.action === "select" ? result.previous.record : null;
      elements.adoptStatus.hidden = false;
      elements.adoptStatus.textContent = "已采用候选 v" + (source ? source.version : "?")
        + "（选择记录 v" + result.version + "）。"
        + (replaced ? "上一次选择保留在历史里。" : "")
        + "改选或取消采用只会追加新记录。";
    } catch (error) {
      showError(elements.adoptError, (error && error.message) || "选择没有保存，请重试。");
    } finally {
      adoptInFlight = false;
      renderAttempts();
      renderAdoptPanel();
    }
  }

  async function handleAdoptClear() {
    if (adoptInFlight) return;
    adoptInFlight = true;
    elements.adoptStatus.textContent = "";
    elements.adoptStatus.hidden = true;
    clearError(elements.adoptError);
    renderAdoptPanel();
    try {
      const result = await writeSelectionRecord("clear");
      if (!result) return;
      elements.adoptStatus.hidden = false;
      elements.adoptStatus.textContent = "已取消采用（选择记录 v" + result.version
        + "）；历史保留，可以重新采用任一候选。";
    } catch (error) {
      showError(elements.adoptError, (error && error.message) || "取消采用没有保存，请重试。");
    } finally {
      adoptInFlight = false;
      renderAttempts();
      renderAdoptPanel();
    }
  }

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

  async function deriveAndApplyState() {
    if (!projectId) return;
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
        project = await repository.projects.setState(projectId, state);
        if (onProjectChanged) onProjectChanged(project);
      } catch (error) {
        showError(elements.error, (error && error.message) || "状态写回失败。");
      }
    }
    renderHeaderText(project);
  }

  function renderAll() {
    clearError(elements.error);
    if (understandingError) {
      showError(elements.error,
        "商品理解投影失败：" + ((understandingError && understandingError.message) || "未知错误"));
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
  }

  function bind() {
    if (bound) return;
    bound = true;
    elements.refAdd.addEventListener("click", () => elements.refFile.click());
    elements.refFile.addEventListener("change", (event) => {
      handleFiles(event.target.files).finally(() => { elements.refFile.value = ""; });
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
    elements.batchRun.addEventListener("click", () => { handleBatchRun(); });
    elements.batchStop.addEventListener("click", () => {
      if (batchState && batchState.active) {
        batchState.stopped = true;
        renderBatch();
      }
    });
    elements.batchReconcile.addEventListener("click", () => { handleBatchReconcile(); });
    elements.batchRetry.addEventListener("click", () => { handleBatchRetry(); });
    elements.compareJump.addEventListener("click", () => {
      const target = elements.compareJump.dataset.targetShot;
      if (!target) {
        elements.compareStatus.textContent = "这套图没有待处理的候选。";
        return;
      }
      openCompare(target, { focus: true });
      const row = elements.attemptList.querySelector('.attempt-row[data-shot-id="' + target + '"]');
      if (row) row.scrollIntoView({ block: "nearest" });
    });
    elements.compareClose.addEventListener("click", () => {
      const previous = compareShotId;
      compareShotId = null;
      compareCandidateId = null;
      renderCompare();
      const entry = elements.attemptList.querySelector(
        'button[data-compare-action="' + previous + '"]');
      if (entry) entry.focus();
    });
    elements.compareCandidates.addEventListener("keydown", handleCompareKeydown);
    elements.reworkOpen.addEventListener("click", () => { openReworkPanel(); });
    elements.reworkPreview.addEventListener("click", () => { handleReworkPreview(); });
    elements.reworkEdit.addEventListener("click", () => { handleReworkEdit(); });
    elements.reworkSubmit.addEventListener("click", () => { handleReworkSubmit(); });
    elements.reworkReset.addEventListener("click", () => { resetReworkDraft(); });
    elements.reworkCancel.addEventListener("click", () => { handleReworkCancel(); });
    elements.reworkPanel.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        handleReworkCancel();
      }
    });
    elements.adoptOpen.addEventListener("click", () => { openAdoptPanel(); });
    elements.adoptSubmit.addEventListener("click", () => { handleAdoptSubmit(); });
    elements.adoptClear.addEventListener("click", () => { handleAdoptClear(); });
    elements.adoptCancel.addEventListener("click", () => {
      closeAdoptPanel({ focusCandidate: true });
    });
    elements.adoptPanel.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeAdoptPanel({ focusCandidate: true });
      }
    });
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
  }

  async function loadWorkspace() {
    const token = ++openToken;
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
    confirmRecord = null;
    attemptChains = new Map();
    attemptInFlight = new Set();
    candidateChains = new Map();
    candidateInFlight = new Set();
    reviewReports = new Map();
    revokePreviewUrls();
    batchState = null;
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
    adoptShotId = null;
    adoptCandidateId = null;
    adoptSource = null;
    elements.comparePanel.hidden = true;
    elements.reworkPanel.hidden = true;
    elements.reworkPreviewBox.hidden = true;
    elements.adoptPanel.hidden = true;
    showAll = false;
    interaction = { slotId: null, mode: null };

    const intakeDoc = await repository.documents.getLatest(projectId, INTAKE_KIND, INTAKE_DOCUMENT_ID);
    if (token !== openToken) return;
    if (intakeDoc && intakeDoc.payload && typeof intakeDoc.payload === "object") {
      intake = { ...emptyProductInput(), ...intakeDoc.payload };
      if (!Array.isArray(intake.references)) intake.references = [];
      if (!Array.isArray(intake.selling_points)) intake.selling_points = [];
      intakeVersion = intakeDoc.version;
    }
    intakeFingerprint = fingerprintOf(intake);
    const slotDocs = await repository.documents.listLatest(projectId, SLOT_KIND);
    if (token !== openToken) return;
    for (const record of slotDocs) {
      if (record.kind === SLOT_KIND && record.payload && typeof record.payload === "object") {
        slots.set(record.document_id, { slot: record.payload, version: record.version });
      }
    }
    const suiteDoc = await repository.documents.getLatest(
      projectId, SUITE_KIND, SUITE_PLAN_DOCUMENT_ID);
    if (token !== openToken) return;
    if (suiteDoc && suiteDoc.payload && Array.isArray(suiteDoc.payload.shots)) {
      suitePlan = suiteDoc.payload;
      suiteVersion = suiteDoc.version;
    }
    const styleDoc = await repository.documents.getLatest(
      projectId, STYLE_KIND, STYLE_SPEC_DOCUMENT_ID);
    if (token !== openToken) return;
    if (styleDoc && styleDoc.payload && typeof styleDoc.payload === "object") {
      styleSpec = { ...emptyStyleSpec(), ...styleDoc.payload };
      styleVersion = styleDoc.version;
    }
    const specDocs = await repository.documents.listLatest(projectId, SHOT_SPEC_KIND);
    if (token !== openToken) return;
    for (const record of specDocs) {
      if (record.payload && typeof record.payload === "object") {
        shotSpecs.set(record.document_id, { spec: record.payload, version: record.version });
      }
    }
    const promptDocs = await repository.documents.listLatest(projectId, PROMPT_KIND);
    if (token !== openToken) return;
    for (const record of promptDocs) {
      if (record.payload && typeof record.payload === "object" && record.payload.compiled) {
        promptVersions.set(record.document_id, { record: record.payload, version: record.version });
      }
    }
    const confirmDocs = await repository.documents.listLatest(projectId, CONFIRM_KIND);
    if (token !== openToken) return;
    for (const record of confirmDocs) {
      if (record.document_id === CONFIRM_DOCUMENT_ID && record.payload && record.payload.fingerprint) {
        confirmRecord = { payload: record.payload, version: record.version };
      } else if (record.document_id.startsWith(REWORK_CONFIRM_PREFIX)
                 && record.payload && record.payload.fingerprint) {
        reworkConfirmations.set(
          record.document_id.slice(REWORK_CONFIRM_PREFIX.length),
          { payload: record.payload, version: record.version });
      }
    }
    for (const shot of (suitePlan && Array.isArray(suitePlan.shots) ? suitePlan.shots : [])) {
      const attemptDocs = await repository.documents.listVersions(projectId, ATTEMPT_KIND, shot.shot_id);
      if (token !== openToken) return;
      attemptChains.set(shot.shot_id, attemptDocs.slice().reverse()
        .map((record) => ({ record: record.payload, version: record.version })));
    }
    for (const shot of (suitePlan && Array.isArray(suitePlan.shots) ? suitePlan.shots : [])) {
      const candidateDocs = await repository.documents.listVersions(projectId, CANDIDATE_KIND, shot.shot_id);
      if (token !== openToken) return;
      candidateChains.set(shot.shot_id, candidateDocs.slice().reverse()
        .map((record) => ({ record: record.payload, version: record.version })));
    }
    const selectionDocs = await repository.documents.listLatest(projectId, SELECTION_KIND);
    if (token !== openToken) return;
    for (const record of selectionDocs) {
      if (record.payload && typeof record.payload === "object") {
        selections.set(record.document_id, { record: record.payload, version: record.version });
      }
    }
    const reviewDocs = await repository.documents.listLatest(projectId, REVIEW_KIND);
    if (token !== openToken) return;
    for (const record of reviewDocs) {
      if (record.payload && typeof record.payload === "object") {
        reviewReports.set(record.document_id, { report: record.payload, version: record.version });
      }
    }
    for (const shot of (suitePlan && Array.isArray(suitePlan.shots) ? suitePlan.shots : [])) {
      const latest = latestStoredCandidateOf(shot.shot_id);
      if (!latest) continue;
      const candidate = latest.record;
      const stored = reviewReports.get(candidate.candidate_id);
      if (stored && reviewIsCurrent(stored.report, candidate)) continue;
      try {
        await ensureReviewReport(shot.shot_id, candidate, null);
      } catch (error) {
        // 打开项目时的报告补建是尽力而为；失败不阻塞工作区。
      }
      if (token !== openToken) return;
    }
    renderAll();
    await deriveAndApplyState();
    renderAll();
    await loadCapabilities();
    if (token !== openToken) return;
    renderAnalyze();
  }

  return {
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
    async close() {
      openToken += 1;
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
    setProject(projectRecord) {
      if (projectRecord && projectRecord.project_id === projectId) {
        project = projectRecord;
        renderHeaderText(project);
      }
    },
    async reviewLatestCandidate(shotId) {
      return reviewCandidate(shotId);
    },
  };
}
