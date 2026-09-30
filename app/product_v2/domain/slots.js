/**
 * FactSlot 契约（V2.2.1）：槽位分类、合法状态、权限矩阵与状态转换。
 *
 * 三条不可协商的规则（计划 §4.2 / §4.3）：
 *  1. 权限由 authority 决定，不由界面决定；模型只能提案，不能确认。
 *  2. 来源与置信是事实的一部分；模型置信只影响排序，不能把 proposed 自动变成 confirmed。
 *  3. 转换器不能生产不合法事实：applySlotAction 出的槽位必须仍然通过 checkFactSlot。
 */

import { DOMAIN_ERROR_CODES, DomainError, denied, illegal, invalid } from "./errors.js";
import {
  FACT_SLOT_SCHEMA_VERSION,
  SLOT_ID_PATTERN,
  checkEvidenceList,
  checkSchemaVersion,
  checkValueShape,
  isNonEmptyString,
  isPlainObject,
  pushProblem,
} from "./shared.js";

/**
 * 槽位值的领域相等：槽位值只可能是标量或标量数组（checkValueShape 保证），
 * 所以用领域比较，不用 JSON 字符串比较——后者对键序敏感，还会把类型差异洗掉。
 */
export function slotValueEquals(a, b) {
  if (Array.isArray(a) || Array.isArray(b)) {
    return Array.isArray(a) && Array.isArray(b) && a.length === b.length
      && a.every((item, index) => slotValueEquals(item, b[index]));
  }
  return a === b;
}

export const SLOT_AUTHORITIES = Object.freeze([
  "core_fixed",        // 系统契约定义，用户可改值，模型只能提议，不可删除
  "category_dynamic",  // 语义模型按品类提议，用户确认或修改，可增删（有依赖时不可删）
  "user_custom",       // 用户自定义，用户自由增删
  "derived",           // 确定性规则派生，用户不能直接改值，只能改来源
]);

export const SLOT_SOURCES = Object.freeze([
  "user_input",
  "reference_observation",
  "model_inference",
  "system_default",
  "derived_rule",
]);

export const SLOT_STATUSES = Object.freeze([
  "confirmed",
  "proposed",
  "missing",
  "conflict",
  "unknown",
  "superseded",
]);

export const SLOT_VALUE_TYPES = Object.freeze(["text", "text_list", "number", "boolean", "enum"]);

export const SLOT_ACTORS = Object.freeze(["user", "model", "rule"]);

export const SLOT_ACTIONS = Object.freeze([
  "propose", "edit", "confirm", "mark_conflict", "mark_unknown", "supersede",
]);

/**
 * 核心固定槽位注册表：只能由系统升级增删（计划 §4.2 第一行）。
 * critical 表示"没有确认它，就不允许把商品理解标成完成"。
 */
export const CORE_SLOT_REGISTRY = Object.freeze([
  Object.freeze({ slot_id: "product_name", label: "商品名称", value_type: "text", critical: true }),
  Object.freeze({ slot_id: "product_category", label: "商品品类", value_type: "text", critical: true }),
  Object.freeze({ slot_id: "signature_features", label: "必须保持的商品特征", value_type: "text_list", critical: true }),
  Object.freeze({ slot_id: "brand", label: "品牌", value_type: "text", critical: false }),
  Object.freeze({ slot_id: "key_material", label: "主要材质", value_type: "text", critical: false }),
  Object.freeze({ slot_id: "color_summary", label: "颜色概览", value_type: "text", critical: false }),
  Object.freeze({ slot_id: "size_summary", label: "尺寸概览", value_type: "text", critical: false }),
  Object.freeze({ slot_id: "package_contents", label: "包装内容物", value_type: "text_list", critical: false }),
]);

export const CORE_SLOT_IDS = Object.freeze(CORE_SLOT_REGISTRY.map((item) => item.slot_id));
export const CRITICAL_SLOT_IDS = Object.freeze(
  CORE_SLOT_REGISTRY.filter((item) => item.critical).map((item) => item.slot_id),
);

const CORE_BY_ID = new Map(CORE_SLOT_REGISTRY.map((item) => [item.slot_id, item]));

export function coreSlotDefinition(slotId) {
  return CORE_BY_ID.get(slotId) || null;
}

export function checkFactSlot(slot) {
  const problems = [];
  if (!isPlainObject(slot)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "FactSlot 必须是对象。");
    return problems;
  }
  checkSchemaVersion(slot, FACT_SLOT_SCHEMA_VERSION, problems, "$");
  if (typeof slot.slot_id !== "string" || !SLOT_ID_PATTERN.test(slot.slot_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.slot_id",
      "slot_id 必须是 2-48 位小写字母开头的标识。");
  }
  if (!isNonEmptyString(slot.label) || slot.label.length > 60) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.label",
      "label 必须是 1-60 字符的非空字符串。");
  }
  if (!SLOT_AUTHORITIES.includes(slot.authority)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.authority", "authority 不在词表内。");
  }
  if (!SLOT_VALUE_TYPES.includes(slot.value_type)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.value_type", "value_type 不在词表内。");
  }
  if (!SLOT_SOURCES.includes(slot.source)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.source", "source 不在词表内。");
  }
  if (!SLOT_STATUSES.includes(slot.status)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.status", "status 不在词表内。");
  }
  if (slot.confidence !== null && slot.confidence !== undefined) {
    if (typeof slot.confidence !== "number" || !Number.isFinite(slot.confidence)
        || slot.confidence < 0 || slot.confidence > 1) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.confidence", "confidence 必须是 0..1 或 null。");
    }
    if (slot.source !== "model_inference") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.confidence",
        "只有 model_inference 允许携带 confidence；人工与规则来源不写置信。");
    }
  }
  if (slot.allow_model_proposal !== undefined && typeof slot.allow_model_proposal !== "boolean") {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.allow_model_proposal",
      "allow_model_proposal 必须是布尔值。");
  }
  checkEvidenceList(problems, "$.evidence", slot.evidence);
  if (slot.depends_on !== undefined) {
    if (!Array.isArray(slot.depends_on)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.depends_on", "depends_on 必须是数组。");
    } else {
      const seen = new Set();
      slot.depends_on.forEach((item, index) => {
        const path = "$.depends_on[" + index + "]";
        if (typeof item !== "string" || !SLOT_ID_PATTERN.test(item)) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "depends_on 项必须是合法 slot_id。");
        } else if (item === slot.slot_id) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_DEPENDENCY_CYCLE, path, "槽位不能依赖自己。");
        } else if (seen.has(item)) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "depends_on 不允许重复。");
        } else {
          seen.add(item);
        }
      });
    }
  }

  // 状态与值的对应关系：这是"事实是不是事实"的唯一判据。
  const status = slot.status;
  const hasValue = slot.value !== null && slot.value !== undefined;
  if (status === "confirmed" || status === "proposed") {
    if (!hasValue) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.value", status + " 状态必须携带值。");
    } else {
      checkValueShape(problems, "$.value", slot.value_type, slot.value, slot.enum_values);
    }
  }
  if ((status === "missing" || status === "unknown" || status === "conflict") && hasValue) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.value",
      status + " 状态不允许携带值；争议值只能放在 evidence.note。");
  }
  if (status === "proposed" && slot.source !== "model_inference") {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.source", "proposed 只能来自 model_inference。");
  }
  if (status === "confirmed" && slot.source === "model_inference" && slot.confidence === null) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.confidence",
      "人工确认的模型提案必须保留原置信读数。");
  }
  if (status === "conflict" && (Array.isArray(slot.evidence) ? slot.evidence.length : 0) < 2) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.evidence",
      "conflict 必须记录至少两条相互冲突的证据。");
  }
  if (slot.authority === "derived") {
    if (slot.source !== "derived_rule") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.source", "派生槽位只能由 derived_rule 写入。");
    }
    if (!Array.isArray(slot.depends_on) || slot.depends_on.length === 0) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.depends_on", "派生槽位必须声明来源槽位。");
    }
  }
  if (slot.authority === "user_custom" && slot.status === "confirmed"
      && slot.source !== "user_input" && slot.source !== "reference_observation") {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.source",
      "自定义槽位的确认值只能来自用户或参考图观察。");
  }
  if (slot.authority === "core_fixed" && typeof slot.slot_id === "string") {
    const definition = coreSlotDefinition(slot.slot_id);
    if (!definition) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.slot_id",
        "core_fixed 槽位必须在系统注册表内；新增核心槽位属于系统升级，不能由界面或模型创建。");
    } else {
      if (slot.value_type !== definition.value_type) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.value_type",
          "核心槽位 value_type 必须与注册表一致（" + definition.value_type + "）。");
      }
      if (slot.critical !== definition.critical) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.critical",
          "核心槽位 critical 必须与注册表一致。");
      }
    }
  }
  return problems;
}

export function assertFactSlot(slot) {
  const problems = checkFactSlot(slot);
  if (problems.length) {
    throw new DomainError(problems[0].code,
      "FactSlot 不合法：" + problems.map((item) => item.message).join("；"), { problems });
  }
  return slot;
}

/** 槽位集合级判据：重复 id、悬空依赖、循环依赖。 */
export function checkSlotSet(slots) {
  const problems = [];
  if (!Array.isArray(slots)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "槽位集合必须是数组。");
    return problems;
  }
  const byId = new Map();
  slots.forEach((slot, index) => {
    checkFactSlot(slot).forEach((item) => {
      problems.push({ code: item.code, path: "slots[" + index + "]" + item.path.slice(1), message: item.message });
    });
    if (isPlainObject(slot) && typeof slot.slot_id === "string") {
      if (byId.has(slot.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "slots[" + index + "].slot_id",
          "slot_id 重复：" + slot.slot_id);
      } else {
        byId.set(slot.slot_id, slot);
      }
    }
  });
  for (const slot of byId.values()) {
    for (const dependency of slot.depends_on || []) {
      if (!byId.has(dependency)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.depends_on",
          "槽位 " + slot.slot_id + " 依赖不存在的槽位 " + dependency + "。");
      }
    }
  }
  const state = new Map();
  const visit = (slotId, trail) => {
    if (state.get(slotId) === "done") return;
    if (state.get(slotId) === "visiting") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_DEPENDENCY_CYCLE, "$.depends_on",
        "依赖成环：" + trail.concat(slotId).join(" → "));
      return;
    }
    state.set(slotId, "visiting");
    const slot = byId.get(slotId);
    for (const dependency of (slot && slot.depends_on) || []) {
      if (byId.has(dependency)) visit(dependency, trail.concat(slotId));
    }
    state.set(slotId, "done");
  };
  for (const slotId of byId.keys()) visit(slotId, []);
  return problems;
}

export function assertSlotSet(slots) {
  const problems = checkSlotSet(slots);
  if (problems.length) {
    throw new DomainError(problems[0].code,
      "槽位集合不合法：" + problems.map((item) => item.message).join("；"), { problems });
  }
  return slots;
}

/* ------------------------------------------------------------------ */
/* 权限矩阵：谁能改值、谁能确认、谁能增删                                 */
/* ------------------------------------------------------------------ */

export function slotPermissions(slot) {
  const authority = slot && slot.authority;
  const custom = authority === "user_custom";
  const derived = authority === "derived";
  return {
    edit_value: {
      user: !derived,
      model: authority === "core_fixed" || authority === "category_dynamic"
        || (custom && slot.allow_model_proposal === true),
      rule: derived,
    },
    confirm: { user: !derived, model: false, rule: derived },
    delete: { user: custom || authority === "category_dynamic", model: false, rule: false },
    add: { user: true, model: true, rule: false },
  };
}

export function canEditValue(slot, actor) {
  return Boolean(slotPermissions(slot).edit_value[actor]);
}

export function canConfirmSlot(slot, actor) {
  if (!slotPermissions(slot).confirm[actor]) return false;
  return ["proposed", "missing", "unknown", "conflict"].includes(slot.status);
}

export function canDeleteSlot(slot, { dependencyCount = 0 } = {}) {
  if (!slot || !slotPermissions(slot).delete.user) return false;
  if (slot.authority === "user_custom") return true;
  return dependencyCount === 0;
}

export function canAddSlot(candidate, actor, { existingSlots = [] } = {}) {
  if (!isPlainObject(candidate)) return false;
  const authority = candidate.authority;
  const allowed = actor === "user"
    ? (authority === "category_dynamic" || authority === "user_custom")
    : actor === "model"
      ? authority === "category_dynamic"
      : false;
  if (!allowed) return false;
  if (existingSlots.some((slot) => slot && slot.slot_id === candidate.slot_id)) return false;
  return checkFactSlot(candidate).length === 0;
}

/* ------------------------------------------------------------------ */
/* 状态转换：非法动作抛错，合法动作不许产出不合法槽位                      */
/* ------------------------------------------------------------------ */

const CONFIRMABLE = new Set(["proposed", "missing", "unknown", "conflict"]);

export function checkSlotAction(slot, spec) {
  const problems = [];
  if (!isPlainObject(spec) || !SLOT_ACTIONS.includes(spec.action)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.action", "未知动作。");
    return problems;
  }
  const actor = spec.actor;
  if (!SLOT_ACTORS.includes(actor)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.actor", "未知行为者。");
    return problems;
  }
  const action = spec.action;
  const status = slot.status;
  const hasValue = spec.value !== null && spec.value !== undefined;

  if (action === "propose") {
    if (actor !== "model") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED, "$.actor", "只有模型可以 propose。");
    }
    if (!canEditValue(slot, "model")) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED, "$", "该槽位不允许模型提案。");
    }
    if (status === "superseded") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_TRANSITION_ILLEGAL, "$.action",
        "已 supersede 的槽位不能再次提案，请新增槽位。");
    }
    if (!hasValue) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.value", "propose 必须携带值。");
    }
    if (typeof spec.confidence !== "number" || spec.confidence < 0 || spec.confidence > 1) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.confidence", "propose 必须携带 0..1 的 confidence。");
    }
  }
  if (action === "edit") {
    if (actor !== "user") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED, "$.actor", "只有用户可以编辑值。");
    }
    if (!canEditValue(slot, "user")) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED, "$", "派生槽位不能直接改值，请改来源槽位。");
    }
    if (!hasValue) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.value", "edit 必须携带值。");
    }
  }
  if (action === "confirm") {
    if (!["user", "rule"].includes(actor)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED, "$.actor", "模型不能确认事实。");
    }
    if (actor === "rule" && slot.authority !== "derived") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED, "$", "规则只能确认派生槽位。");
    }
    if (!CONFIRMABLE.has(status)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_TRANSITION_ILLEGAL, "$.action",
        "当前状态 " + status + " 不能直接确认。");
    }
    if ((status === "missing" || status === "unknown") && !hasValue) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_TRANSITION_ILLEGAL, "$.value",
        "missing/unknown 的槽位必须先给出值再确认。");
    }
    if (status === "conflict" && !hasValue) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_TRANSITION_ILLEGAL, "$.value",
        "冲突必须由用户给出裁决值才能确认。");
    }
  }
  if (action === "mark_conflict") {
    if (actor === "model") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED, "$.actor",
        "模型不能把槽位标成冲突；提案冲突由系统在 propose 时判定。");
    }
    const evidence = Array.isArray(spec.evidence) ? spec.evidence : [];
    if (evidence.length < 2) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.evidence", "标记冲突必须给出至少两条证据。");
    }
  }
  if (action === "mark_unknown" && status === "superseded") {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_TRANSITION_ILLEGAL, "$.action", "已 supersede 的槽位不能再标 unknown。");
  }
  if (action === "supersede" && status === "superseded") {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_TRANSITION_ILLEGAL, "$.action", "槽位已经是 superseded。");
  }
  return problems;
}

/** 应用一次槽位动作，返回新槽位（不修改入参）。任何非法动作抛 DomainError。 */
export function applySlotAction(slot, spec) {
  const problems = checkSlotAction(slot, spec);
  if (problems.length) {
    const first = problems[0];
    if (first.code === DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED) throw denied(first.message, { problems });
    if (first.code === DOMAIN_ERROR_CODES.CONTRACT_TRANSITION_ILLEGAL) throw illegal(first.message, { problems });
    throw invalid(first.message, { problems });
  }
  const next = structuredClone(slot);
  const evidence = Array.isArray(spec.evidence) ? structuredClone(spec.evidence) : [];
  const appendEvidence = () => { next.evidence = (next.evidence || []).concat(evidence); };

  if (spec.action === "propose") {
    if (next.status === "confirmed" && slotValueEquals(next.value, spec.value)) {
      appendEvidence();
    } else if (next.status === "confirmed") {
      const prior = Array.isArray(next.evidence) ? next.evidence : [];
      next.evidence = prior.concat([
        { kind: "user", ref: "confirmed_value", note: JSON.stringify(next.value) },
        { kind: "model", ref: "model_proposal", note: JSON.stringify(spec.value) },
      ]).concat(evidence);
      next.value = null;
      next.status = "conflict";
      next.confidence = null;
      next.source = "model_inference";
    } else {
      next.value = structuredClone(spec.value);
      next.status = "proposed";
      next.source = "model_inference";
      next.confidence = spec.confidence;
      appendEvidence();
    }
  } else if (spec.action === "edit") {
    next.value = structuredClone(spec.value);
    next.status = "confirmed";
    next.source = SLOT_SOURCES.includes(spec.source) ? spec.source : "user_input";
    next.confidence = null;
    appendEvidence();
  } else if (spec.action === "confirm") {
    if (spec.value !== null && spec.value !== undefined) {
      next.value = structuredClone(spec.value);
      next.source = SLOT_SOURCES.includes(spec.source) ? spec.source : "user_input";
      next.confidence = null;
    }
    next.status = "confirmed";
    if (spec.actor === "rule") next.source = "derived_rule";
    appendEvidence();
  } else if (spec.action === "mark_conflict") {
    next.value = null;
    next.status = "conflict";
    next.confidence = null;
    next.evidence = evidence;
  } else if (spec.action === "mark_unknown") {
    next.value = null;
    next.status = "unknown";
  } else if (spec.action === "supersede") {
    next.status = "superseded";
  }

  const nextProblems = checkFactSlot(next);
  if (nextProblems.length) {
    throw invalid("动作会产出不合法的槽位：" + nextProblems.map((item) => item.message).join("；"),
      { problems: nextProblems });
  }
  return next;
}
