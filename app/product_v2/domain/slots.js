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
 * @param {unknown} a
 * @param {unknown} b
 * @returns {boolean}
 */
export function slotValueEquals(a, b) {
  if (Array.isArray(a) || Array.isArray(b)) {
    return Array.isArray(a) && Array.isArray(b) && a.length === b.length
      && a.every((item, index) => slotValueEquals(item, b[index]));
  }
  return a === b;
}

/** @type {readonly import("./type-contracts.js").SlotAuthority[]} */
export const SLOT_AUTHORITIES = Object.freeze([
  "core_fixed",        // 系统契约定义，用户可改值，模型只能提议，不可删除
  "category_dynamic",  // 语义模型按品类提议，用户确认或修改，可增删（有依赖时不可删）
  "user_custom",       // 用户自定义，用户自由增删
  "derived",           // 确定性规则派生，用户不能直接改值，只能改来源
]);
/** @type {readonly import("./type-contracts.js").SlotSource[]} */
export const SLOT_SOURCES = Object.freeze([
  "user_input",
  "reference_observation",
  "model_inference",
  "system_default",
  "derived_rule",
]);

/** @type {readonly import("./type-contracts.js").SlotStatus[]} */
export const SLOT_STATUSES = Object.freeze([
  "confirmed",
  "proposed",
  "missing",
  "conflict",
  "unknown",
  "superseded",
]);

/** @type {readonly import("./type-contracts.js").SlotValueType[]} */
export const SLOT_VALUE_TYPES = Object.freeze([
  "text", "text_list", "number", "boolean", "enum", "dimension_list",
]);

/** @type {readonly import("./type-contracts.js").SlotActor[]} */
export const SLOT_ACTORS = Object.freeze(["user", "model", "rule"]);

/** @type {readonly import("./type-contracts.js").SlotAction[]} */
export const SLOT_ACTIONS = Object.freeze([
  "propose", "edit", "confirm", "mark_conflict", "mark_unknown", "supersede",
]);

/**
 * 核心固定槽位注册表：只能由系统升级增删（计划 §4.2 第一行）。
 * critical 表示"没有确认它，就不允许把商品理解标成完成"。
 */
/** @type {readonly import("./type-contracts.js").CoreSlotDefinition[]} */
export const CORE_SLOT_REGISTRY = Object.freeze([
  Object.freeze({ slot_id: "product_name", label: "商品名称", value_type: "text", critical: true }),
  Object.freeze({ slot_id: "product_category", label: "商品品类", value_type: "text", critical: true }),
  Object.freeze({ slot_id: "signature_features", label: "必须保持的商品特征", value_type: "text_list", critical: true }),
  Object.freeze({ slot_id: "brand", label: "品牌", value_type: "text", critical: false }),
  Object.freeze({ slot_id: "key_material", label: "主要材质", value_type: "text", critical: false }),
  Object.freeze({ slot_id: "color_summary", label: "颜色概览", value_type: "text", critical: false }),
  Object.freeze({ slot_id: "size_summary", label: "尺寸概览", value_type: "text", critical: false }),
  Object.freeze({ slot_id: "size_dimensions", label: "尺寸规格（对象/轴向/数值/单位）",
    value_type: "dimension_list", critical: false }),
  Object.freeze({ slot_id: "package_contents", label: "包装内容物", value_type: "text_list", critical: false }),
]);

export const CORE_SLOT_IDS = Object.freeze(CORE_SLOT_REGISTRY.map((item) => item.slot_id));
export const CRITICAL_SLOT_IDS = Object.freeze(
  CORE_SLOT_REGISTRY.filter((item) => item.critical).map((item) => item.slot_id),
);

/** @type {Map<string, import("./type-contracts.js").CoreSlotDefinition>} */
const CORE_BY_ID = new Map(/** @type {Array<[string, import("./type-contracts.js").CoreSlotDefinition]>} */ (
  CORE_SLOT_REGISTRY.map((item) => [item.slot_id, item])));

/**
 * 核心注册表查询：返回注册定义，未登记返回 null（调用方据此拒绝越权 core_fixed）。
 * @param {unknown} slotId
 * @returns {import("./type-contracts.js").CoreSlotDefinition | null}
 */
export function coreSlotDefinition(slotId) {
  return (typeof slotId === "string" ? CORE_BY_ID.get(slotId) : undefined) || null;
}

/**
 * FactSlot 自检：分类词表、状态与值的对应、派生与核心一致性，返回问题列表（空数组 = 合法），不抛异常。
 * @param {unknown} slot
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkFactSlot(slot) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
  const problems = [];
  if (!isPlainObject(slot)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "FactSlot 必须是对象。");
    return problems;
  }
  /** @type {Record<string, unknown>} */
  const record = /** @type {Record<string, unknown>} */ (/** @type {unknown} */ (slot));
  checkSchemaVersion(record, FACT_SLOT_SCHEMA_VERSION, problems, "$");
  if (typeof record.slot_id !== "string" || !SLOT_ID_PATTERN.test(record.slot_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.slot_id",
      "slot_id 必须是 2-48 位小写字母开头的标识。");
  }
  if (!isNonEmptyString(record.label) || /** @type {string} */ (record.label).length > 60) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.label",
      "label 必须是 1-60 字符的非空字符串。");
  }
  if (!SLOT_AUTHORITIES.includes(/** @type {import("./type-contracts.js").SlotAuthority} */ (record.authority))) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.authority", "authority 不在词表内。");
  }
  if (!SLOT_VALUE_TYPES.includes(/** @type {import("./type-contracts.js").SlotValueType} */ (record.value_type))) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.value_type", "value_type 不在词表内。");
  }
  if (!SLOT_SOURCES.includes(/** @type {import("./type-contracts.js").SlotSource} */ (record.source))) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.source", "source 不在词表内。");
  }
  if (!SLOT_STATUSES.includes(/** @type {import("./type-contracts.js").SlotStatus} */ (record.status))) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.status", "status 不在词表内。");
  }
  if (record.confidence !== null && record.confidence !== undefined) {
    if (typeof record.confidence !== "number" || !Number.isFinite(record.confidence)
        || record.confidence < 0 || record.confidence > 1) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.confidence", "confidence 必须是 0..1 或 null。");
    }
    if (record.source !== "model_inference") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.confidence",
        "只有 model_inference 允许携带 confidence；人工与规则来源不写置信。");
    }
  }
  if (record.allow_model_proposal !== undefined && typeof record.allow_model_proposal !== "boolean") {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.allow_model_proposal",
      "allow_model_proposal 必须是布尔值。");
  }
  checkEvidenceList(problems, "$.evidence", record.evidence);
  if (record.depends_on !== undefined) {
    if (!Array.isArray(record.depends_on)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.depends_on", "depends_on 必须是数组。");
    } else {
      /** @type {Set<string>} */
      const seen = new Set();
      /** @type {Array<unknown>} */
      const dependencies = /** @type {Array<unknown>} */ (record.depends_on);
      dependencies.forEach((/** @type {unknown} */ raw, /** @type {number} */ index) => {
        const path = "$.depends_on[" + index + "]";
        if (typeof raw !== "string" || !SLOT_ID_PATTERN.test(raw)) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "depends_on 项必须是合法 slot_id。");
        } else if (raw === record.slot_id) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_DEPENDENCY_CYCLE, path, "槽位不能依赖自己。");
        } else if (seen.has(raw)) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "depends_on 不允许重复。");
        } else {
          seen.add(raw);
        }
      });
    }
  }
  // 状态与值的对应关系：这是"事实是不是事实"的唯一判据。
  const status = record.status;
  const hasValue = record.value !== null && record.value !== undefined;
  if (status === "confirmed" || status === "proposed") {
    if (!hasValue) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.value", /** @type {string} */ (status) + " 状态必须携带值。");
    } else {
      checkValueShape(problems, "$.value", /** @type {string} */ (record.value_type), record.value, record.enum_values);
    }
  }
  if ((status === "missing" || status === "unknown" || status === "conflict") && hasValue) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.value",
      /** @type {string} */ (status) + " 状态不允许携带值；争议值只能放在 evidence.note。");
  }
  if (status === "proposed" && record.source !== "model_inference") {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.source", "proposed 只能来自 model_inference。");
  }
  if (status === "confirmed" && record.source === "model_inference" && record.confidence === null) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.confidence",
      "人工确认的模型提案必须保留原置信读数。");
  }
  if (status === "conflict" && (!Array.isArray(record.evidence) || /** @type {Array<unknown>} */ (record.evidence).length < 2)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.evidence",
      "conflict 必须记录至少两条相互冲突的证据。");
  }
  if (record.authority === "derived") {
    if (record.source !== "derived_rule") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.source", "派生槽位只能由 derived_rule 写入。");
    }
    if (!Array.isArray(record.depends_on) || /** @type {Array<unknown>} */ (record.depends_on).length === 0) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.depends_on", "派生槽位必须声明来源槽位。");
    }
  }
  if (record.authority === "user_custom" && record.status === "confirmed"
      && record.source !== "user_input" && record.source !== "reference_observation") {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.source",
      "自定义槽位的确认值只能来自用户或参考图观察。");
  }
  if (record.authority === "core_fixed" && typeof record.slot_id === "string") {
    const definition = coreSlotDefinition(record.slot_id);
    if (!definition) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.slot_id",
        "core_fixed 槽位必须在系统注册表内；新增核心槽位属于系统升级，不能由界面或模型创建。");
    } else {
      if (record.value_type !== definition.value_type) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.value_type",
          "核心槽位 value_type 必须与注册表一致（" + definition.value_type + "）。");
      }
      if (record.critical !== definition.critical) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.critical",
          "核心槽位 critical 必须与注册表一致。");
      }
    }
  }
  return problems;
}

/**
 * FactSlot 断言：合法时原样返回入参，不合法抛 DomainError（首个问题码）。
 * @param {unknown} slot
 * @returns {import("./type-contracts.js").FactSlot}
 */
export function assertFactSlot(slot) {
  const problems = checkFactSlot(slot);
  if (problems.length) {
    throw new DomainError(problems[0].code,
      "FactSlot 不合法：" + problems.map((item) => item.message).join("；"), { problems });
  }
  return /** @type {import("./type-contracts.js").FactSlot} */ (/** @type {unknown} */ (slot));
}

/**
 * 槽位集合级判据：重复 id、悬空依赖、循环依赖。
 * @param {unknown} slots
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkSlotSet(slots) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
  const problems = [];
  if (!Array.isArray(slots)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "槽位集合必须是数组。");
    return problems;
  }
  /** @type {Map<string, Record<string, unknown>>} */
  const byId = new Map();
  /** @type {Array<unknown>} */ (slots).forEach((/** @type {unknown} */ raw, /** @type {number} */ index) => {
    checkFactSlot(raw).forEach((item) => {
      problems.push({ code: item.code, path: "slots[" + index + "]" + item.path.slice(1), message: item.message });
    });
    if (isPlainObject(raw)) {
      /** @type {Record<string, unknown>} */
      const candidate = raw;
      /** @type {unknown} */
      const id = candidate.slot_id;
      if (typeof id === "string") {
        if (byId.has(id)) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "slots[" + index + "].slot_id",
            "slot_id 重复：" + id);
        } else {
          byId.set(id, candidate);
        }
      }
    }
  });
  for (const slot of byId.values()) {
    /** @type {string} */
    const ownerId = /** @type {string} */ (slot.slot_id);
    for (const dependency of /** @type {Array<unknown>} */ (slot.depends_on || [])) {
      if (typeof dependency === "string" && !byId.has(dependency)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.depends_on",
          "槽位 " + ownerId + " 依赖不存在的槽位 " + dependency + "。");
      }
    }
  }
  /** @type {Map<string, "visiting" | "done">} */
  const state = new Map();
  /**
   * @param {string} slotId
   * @param {string[]} trail
   * @returns {void}
   */
  const visit = (slotId, trail) => {
    if (state.get(slotId) === "done") return;
    if (state.get(slotId) === "visiting") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_DEPENDENCY_CYCLE, "$.depends_on",
        "依赖成环：" + trail.concat(slotId).join(" → "));
      return;
    }
    state.set(slotId, "visiting");
    const slot = byId.get(slotId);
    for (const dependency of /** @type {Array<unknown>} */ ((slot && slot.depends_on) || [])) {
      if (typeof dependency === "string" && byId.has(dependency)) visit(dependency, trail.concat(slotId));
    }
    state.set(slotId, "done");
  };
  for (const slotId of byId.keys()) visit(slotId, []);
  return problems;
}

/**
 * 槽位集合断言：合法时原样返回入参，不合法抛 DomainError（首个问题码）。
 * @param {unknown} slots
 * @returns {import("./type-contracts.js").FactSlot[]}
 */
export function assertSlotSet(slots) {
  const problems = checkSlotSet(slots);
  if (problems.length) {
    throw new DomainError(problems[0].code,
      "槽位集合不合法：" + problems.map((item) => item.message).join("；"), { problems });
  }
  return /** @type {import("./type-contracts.js").FactSlot[]} */ (/** @type {unknown} */ (slots));
}

/* ------------------------------------------------------------------ */
/* 权限矩阵：谁能改值、谁能确认、谁能增删                                 */
/* ------------------------------------------------------------------ */

/**
 * 权限矩阵：由 authority 派生改值/确认/增删三类权限，界面按钮据此派生，不许另写一套。
 * @param {unknown} slot
 * @returns {import("./type-contracts.js").SlotPermissions}
 */
export function slotPermissions(slot) {
  /** @type {Record<string, unknown>} */
  const record = /** @type {Record<string, unknown>} */ (/** @type {unknown} */ (isPlainObject(slot) ? slot : {}));
  // 原语义：slot 为 null/undefined 时 authority 为 undefined（slot && slot.authority），保持行为不变。
  const authority = isPlainObject(slot) ? record.authority : undefined;
  const custom = authority === "user_custom";
  const derived = authority === "derived";
  const allowProposal = isPlainObject(slot) ? record.allow_model_proposal === true : false;
  return {
    edit_value: {
      user: !derived,
      model: authority === "core_fixed" || authority === "category_dynamic" || (custom && allowProposal),
      rule: derived,
    },
    confirm: { user: !derived, model: false, rule: derived },
    delete: { user: custom || authority === "category_dynamic", model: false, rule: false },
    add: { user: true, model: true, rule: false },
  };
}

/**
 * 指定行为者是否可改该槽位的值。
 * @param {unknown} slot
 * @param {unknown} actor
 * @returns {boolean}
 */
export function canEditValue(slot, actor) {
  /** @type {import("./type-contracts.js").SlotPermissions} */
  const matrix = slotPermissions(slot);
  return Boolean(/** @type {Record<string, boolean>} */ (/** @type {unknown} */ (matrix.edit_value))[/** @type {string} */ (actor)]);
}

/**
 * 指定行为者是否可确认该槽位（权限通过且状态在可确认集合内）。
 * @param {unknown} slot
 * @param {unknown} actor
 * @returns {boolean}
 */
export function canConfirmSlot(slot, actor) {
  if (!slotPermissions(slot).confirm[/** @type {import("./type-contracts.js").SlotActor} */ (actor)]) return false;
  // 原语义：slot 为 null/undefined 时直接读 slot.status 抛 TypeError；合法调用方恒传对象，此处保持原读法。
  return ["proposed", "missing", "unknown", "conflict"].includes(
    /** @type {import("./type-contracts.js").SlotStatus} */ (/** @type {Record<string, unknown>} */ (/** @type {unknown} */ (slot)).status));
}

/**
 * 用户是否可删除该槽位；category_dynamic 有被依赖时需 dependencyCount 拦下。
 * @param {unknown} slot
 * @param {{dependencyCount?: number}} [options]
 * @returns {boolean}
 */
export function canDeleteSlot(slot, { dependencyCount = 0 } = {}) {
  if (!slot || !slotPermissions(slot).delete.user) return false;
  // 原语义：slot 非空（上行已守卫），此处直接读 authority，保持原读法。
  if (/** @type {Record<string, unknown>} */ (/** @type {unknown} */ (slot)).authority === "user_custom") return true;
  return dependencyCount === 0;
}

/**
 * 指定行为者是否可新增候选槽位（含重复 id 与形状自检）。
 * @param {unknown} candidate
 * @param {unknown} actor
 * @param {{existingSlots?: Array<unknown>}} [options]
 * @returns {boolean}
 */
export function canAddSlot(candidate, actor, { existingSlots = [] } = {}) {
  if (!isPlainObject(candidate)) return false;
  /** @type {Record<string, unknown>} */
  const draft = /** @type {Record<string, unknown>} */ (/** @type {unknown} */ (candidate));
  const authority = draft.authority;
  const allowed = actor === "user"
    ? (authority === "category_dynamic" || authority === "user_custom")
    : actor === "model"
      ? authority === "category_dynamic"
      : false;
  if (!allowed) return false;
  if (existingSlots.some((/** @type {unknown} */ raw) => isPlainObject(raw) && /** @type {Record<string, unknown>} */ (raw).slot_id === draft.slot_id)) return false;
  return checkFactSlot(draft).length === 0;
}

/* ------------------------------------------------------------------ */
/* 状态转换：非法动作抛错，合法动作不许产出不合法槽位                      */
/* ------------------------------------------------------------------ */

/** @type {Readonly<Set<string>>} */
const CONFIRMABLE = new Set(["proposed", "missing", "unknown", "conflict"]);

/**
 * 槽位动作自检：权限、状态可达、动作参数形状，返回问题列表（空数组 = 合法），不抛异常。
 * @param {unknown} slot
 * @param {unknown} spec
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkSlotAction(slot, spec) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
  const problems = [];
  /** @type {Record<string, unknown>} */
  const current = /** @type {Record<string, unknown>} */ (/** @type {unknown} */ (isPlainObject(slot) ? slot : {}));
  // 收窄说明：原实现假设 slot 为对象；此处守卫仅为 checkJs 下 unknown 收窄，合法输入行为不变。
  if (!isPlainObject(spec)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.action", "未知动作。");
    return problems;
  }
  /** @type {Record<string, unknown>} */
  const request = spec;
  if (!SLOT_ACTIONS.includes(/** @type {import("./type-contracts.js").SlotAction} */ (request.action))) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.action", "未知动作。");
    return problems;
  }
  const actor = request.actor;
  if (!SLOT_ACTORS.includes(/** @type {import("./type-contracts.js").SlotActor} */ (actor))) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.actor", "未知行为者。");
    return problems;
  }
  const action = request.action;
  const status = current.status;
  const hasValue = request.value !== null && request.value !== undefined;

  if (action === "propose") {
    if (actor !== "model") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED, "$.actor", "只有模型可以 propose。");
    }
    if (!canEditValue(current, "model")) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED, "$", "该槽位不允许模型提案。");
    }
    if (status === "superseded") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_TRANSITION_ILLEGAL, "$.action",
        "已 supersede 的槽位不能再次提案，请新增槽位。");
    }
    if (!hasValue) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.value", "propose 必须携带值。");
    }
    if (typeof request.confidence !== "number" || request.confidence < 0 || request.confidence > 1) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.confidence", "propose 必须携带 0..1 的 confidence。");
    }
  }
  if (action === "edit") {
    if (actor !== "user") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED, "$.actor", "只有用户可以编辑值。");
    }
    if (!canEditValue(current, "user")) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED, "$", "派生槽位不能直接改值，请改来源槽位。");
    }
    if (!hasValue) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.value", "edit 必须携带值。");
    }
  }
  if (action === "confirm") {
    if (actor !== "user" && actor !== "rule") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED, "$.actor", "模型不能确认事实。");
    }
    if (actor === "rule" && current.authority !== "derived") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED, "$", "规则只能确认派生槽位。");
    }
    if (!CONFIRMABLE.has(/** @type {string} */ (status))) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_TRANSITION_ILLEGAL, "$.action",
        "当前状态 " + /** @type {string} */ (status) + " 不能直接确认。");
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
    const evidence = Array.isArray(request.evidence) ? request.evidence : [];
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

/**
 * 应用一次槽位动作，返回新槽位（不修改入参）。任何非法动作抛 DomainError。
 * @param {unknown} slot
 * @param {unknown} spec
 * @returns {import("./type-contracts.js").FactSlot}
 */
export function applySlotAction(slot, spec) {
  const problems = checkSlotAction(slot, spec);
  if (problems.length) {
    const first = problems[0];
    if (first.code === DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED) throw denied(first.message, { problems });
    if (first.code === DOMAIN_ERROR_CODES.CONTRACT_TRANSITION_ILLEGAL) throw illegal(first.message, { problems });
    throw invalid(first.message, { problems });
  }
  /** @type {Record<string, unknown>} */
  const request = /** @type {Record<string, unknown>} */ (spec);
  /** @type {import("./type-contracts.js").FactSlot} */
  const next = /** @type {import("./type-contracts.js").FactSlot} */ (structuredClone(slot));
  /** @type {import("./type-contracts.js").EvidenceItem[]} */
  const evidence = Array.isArray(request.evidence) ? /** @type {import("./type-contracts.js").EvidenceItem[]} */ (structuredClone(request.evidence)) : [];
  const appendEvidence = () => { next.evidence = (next.evidence || []).concat(evidence); };
  if (request.action === "propose") {
    if (next.status === "confirmed" && slotValueEquals(next.value, request.value)) {
      appendEvidence();
    } else if (next.status === "confirmed") {
      /** @type {import("./type-contracts.js").EvidenceItem[]} */
      const prior = Array.isArray(next.evidence) ? next.evidence : [];
      next.evidence = prior.concat(/** @type {import("./type-contracts.js").EvidenceItem[]} */ ([
        { kind: "user", ref: "confirmed_value", note: JSON.stringify(next.value) },
        { kind: "model", ref: "model_proposal", note: JSON.stringify(request.value) },
      ])).concat(evidence);
      next.value = null;
      next.status = "conflict";
      next.confidence = null;
      next.source = "model_inference";
    } else {
      next.value = /** @type {import("./type-contracts.js").FactSlotValue} */ (structuredClone(request.value));
      next.status = "proposed";
      next.source = "model_inference";
      next.confidence = /** @type {number} */ (request.confidence);
      appendEvidence();
    }
  } else if (request.action === "edit") {
    next.value = /** @type {import("./type-contracts.js").FactSlotValue} */ (structuredClone(request.value));
    next.status = "confirmed";
    next.source = SLOT_SOURCES.includes(/** @type {import("./type-contracts.js").SlotSource} */ (request.source)) ? /** @type {import("./type-contracts.js").SlotSource} */ (request.source) : "user_input";
    next.confidence = null;
    appendEvidence();
  } else if (request.action === "confirm") {
    if (request.value !== null && request.value !== undefined) {
      next.value = /** @type {import("./type-contracts.js").FactSlotValue} */ (structuredClone(request.value));
      next.source = SLOT_SOURCES.includes(/** @type {import("./type-contracts.js").SlotSource} */ (request.source)) ? /** @type {import("./type-contracts.js").SlotSource} */ (request.source) : "user_input";
      next.confidence = null;
    }
    next.status = "confirmed";
    if (request.actor === "rule") next.source = "derived_rule";
    appendEvidence();
  } else if (request.action === "mark_conflict") {
    next.value = null;
    next.status = "conflict";
    next.confidence = null;
    next.evidence = evidence;
  } else if (request.action === "mark_unknown") {
    next.value = null;
    next.status = "unknown";
  } else if (request.action === "supersede") {
    next.status = "superseded";
  }

  const nextProblems = checkFactSlot(next);
  if (nextProblems.length) {
    throw invalid("动作会产出不合法的槽位：" + nextProblems.map((item) => item.message).join("；"),
      { problems: nextProblems });
  }
  return next;
}
