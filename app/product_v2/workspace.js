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
  SHOT_TEMPLATES,
  SUITE_PLAN_DOCUMENT_ID,
  STYLE_SPEC_DOCUMENT_ID,
  addCustomShotToPlan,
  addShotFromTemplate,
  applySlotAction,
  assertShotSpec,
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
  buildReviewReport,
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
  compilePrompt,
  confirmationSnapshot,
  confirmationStaleness,
  copyShot,
  coreSlotDefinition,
  deriveBatchState,
  emptyShotSpecFromShot,
  emptyStyleSpec,
  emptyProductInput,
  evaluateCandidateFindings,
  intakeReadiness,
  moveShot,
  newActionId,
  nextFromStatusEnvelope,
  nextFromSubmitEnvelope,
  parsePngDimensions,
  previousVersionOf,
  promptHash,
  promptStaleness,
  recommendPlan,
  referenceFromAsset,
  reviewIsCurrent,
  reviewSummaryText,
  removeShot,
  requestSnapshotOf,
  selectReferences,
  seedSuitePlan,
  specChangeProjection,
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

const DRAFT_DEBOUNCE_MS = 600;
const ANALYZE_MAX_SLOTS = 12;
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

/** 审核优先级：冲突 → 未知 → 缺失 → 未确认 → 已确认 → 已移除。 */
const REVIEW_ORDER = Object.freeze({
  conflict: 0, unknown: 1, missing: 2, proposed: 3, confirmed: 4, superseded: 5,
});

const SCOPE_TEXT = "这一版覆盖“商品资料 → 商品理解 → 套图规划 → 规格 → Prompt → 生成前确认 → 整套生成与逐图进度（含单张核对）”；审核、返工与导出尚未接入。";

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
  let reviewReports = new Map();
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

  async function handleCompilePrompt(shotId) {
    if (!projectId || !suitePlan || !understandingReady) return;
    clearError(elements.promptError);
    try {
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
      });
      const references = selectReferences(shot, intake.references.map((item) => ({
        role: item.role, sha256: item.asset_sha256,
      })));
      const snapshot = requestSnapshotOf(compiled, { references: references });
      const hash = await promptHash(snapshot, { digest: sha256Hex });
      const payload = buildPromptRecord({ compiled: compiled, snapshot: snapshot, hash: hash });
      const problems = checkPromptRecord(payload);
      if (problems.length > 0) throw new Error(problems[0].message);
      const saved = await repository.documents.save(projectId, {
        kind: PROMPT_KIND, documentId: shotId, payload: payload,
      });
      promptVersions.set(shotId, { record: payload, version: saved.version });
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deriveAndApplyState();
      elements.promptStatus.textContent = "已保存 " + shotId + " 的 Prompt 版本 v" + saved.version + "。";
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

  /** 当前确认单：界面、状态派生与提交都读同一份投影，不各自重算。 */
  function buildCurrentSheet() {
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
    });
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
    const findings = evaluateCandidateFindings({
      candidate: candidate,
      bytes: view,
      roleId: shot ? shot.role_id : null,
    });
    const report = buildReviewReport({
      candidate: candidate, findings: findings, at: new Date().toISOString(),
    });
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

  function renderAttempts() {
    const ready = understandingReady && Boolean(suitePlan);
    elements.attemptLocked.hidden = ready;
    elements.attemptEditor.hidden = !ready;
    elements.attemptList.innerHTML = "";
    if (!ready) { renderBatch(); return; }
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
                  + (top ? " · 先看：" + top.title + " — " + top.detail : " · 全部通过"),
              }));
            } else {
              row.append(createElement("p", {
                className: "meta attempt-review",
                attrs: { "data-review-summary": "missing" },
                text: "自动检查报告尚未生成（候选保存时自动生成；旧候选会在重新打开项目时补建）。",
              }));
            }
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
      const canSubmit = confirmed && Boolean(entry) && !inFlight;
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
      if (!confirmed) {
        actions.append(createElement("span", {
          className: "meta", text: "生成前确认缺失或已过期：先回到上面重新确认。",
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
      if (!confirmationIsCurrent()) return { skipped: true, reason: "no_confirmation" };
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

  function renderHeaderText(projectRecord) {
    const state = projectRecord ? projectRecord.state : null;
    if (state === "READY_TO_GENERATE") {
      elements.scope.textContent = "生成前确认已通过：可以整套生成或逐张提交，并按任务编号核对进度；审核、返工与导出仍未接入。";
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
  };
}
