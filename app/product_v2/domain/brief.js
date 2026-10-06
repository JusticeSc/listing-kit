/**
 * ProductBrief 契约（V2.2.1）：已确认事实的投影 + 待处理异常 + 就绪门。
 *
 * ProductBrief 不是"另一份事实"，它是某几个精确槽位版本的投影：
 *   basis 记录"我读的是哪些槽位的哪个版本"，因此上游一变就能机检过期，
 *   而不是靠界面自己记得刷新。
 */

import { DOMAIN_ERROR_CODES, DomainError, invalid } from "./errors.js";
import {
  PRODUCT_BRIEF_SCHEMA_VERSION,
  SLOT_ID_PATTERN,
  checkSchemaVersion,
  isNonEmptyString,
  isPlainObject,
  pushProblem,
} from "./shared.js";
import { SLOT_SOURCES, assertFactSlot, slotValueEquals } from "./slots.js";

/** @type {readonly import("./type-contracts.js").UnresolvedItem["status"][]} */
const UNRESOLVED_STATUSES = Object.freeze(["proposed", "missing", "conflict", "unknown"]);

/**
 * 商品理解自检：basis、已确认事实、待处理三部分各自合法且互相引用一致，返回问题列表（空数组 = 合法），不抛异常。
 * @param {unknown} brief
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkProductBrief(brief) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
  const problems = [];
  if (!isPlainObject(brief)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "商品理解必须是对象。");
    return problems;
  }
  /** @type {Record<string, unknown>} */
  const record = /** @type {Record<string, unknown>} */ (/** @type {unknown} */ (brief));
  checkSchemaVersion(record, PRODUCT_BRIEF_SCHEMA_VERSION, problems, "$");

  /** @type {Set<string>} */
  const basisIds = new Set();
  if (!Array.isArray(record.basis)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.basis", "basis 必须是数组（可为空）。");
  } else {
    /** @type {Array<unknown>} */
    const basisItems = /** @type {Array<unknown>} */ (record.basis);
    basisItems.forEach((/** @type {unknown} */ raw, /** @type {number} */ index) => {
      const path = "$.basis[" + index + "]";
      if (!isPlainObject(raw)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "basis 项必须是对象。");
        return;
      }
      /** @type {Record<string, unknown>} */
      const item = /** @type {Record<string, unknown>} */ (/** @type {unknown} */ (raw));
      if (typeof item.slot_id !== "string" || !SLOT_ID_PATTERN.test(item.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "basis.slot_id 非法。");
      } else if (basisIds.has(item.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "basis 中 slot_id 重复。");
      } else {
        basisIds.add(item.slot_id);
      }
      if (!Number.isInteger(item.version) || /** @type {number} */ (item.version) < 1) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".version", "basis.version 必须是正整数。");
      }
    });
  }

  /** @type {Set<string>} */
  const confirmedIds = new Set();
  if (!Array.isArray(record.confirmed_facts)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.confirmed_facts", "confirmed_facts 必须是数组。");
  } else {
    /** @type {Array<unknown>} */
    const factItems = /** @type {Array<unknown>} */ (record.confirmed_facts);
    factItems.forEach((/** @type {unknown} */ raw, /** @type {number} */ index) => {
      const path = "$.confirmed_facts[" + index + "]";
      if (!isPlainObject(raw)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "confirmed_facts 项必须是对象。");
        return;
      }
      /** @type {Record<string, unknown>} */
      const item = /** @type {Record<string, unknown>} */ (/** @type {unknown} */ (raw));
      if (typeof item.slot_id !== "string" || !SLOT_ID_PATTERN.test(item.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "confirmed_facts.slot_id 非法。");
      } else if (confirmedIds.has(item.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "confirmed_facts 中 slot_id 重复。");
      } else {
        confirmedIds.add(item.slot_id);
      }
      if (item.slot_id !== undefined && !basisIds.has(/** @type {string} */ (item.slot_id))) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "confirmed_facts 引用了不在 basis 里的槽位。");
      }
      if (!isNonEmptyString(item.label)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".label", "事实必须有 label。");
      }
      if (item.value === null || item.value === undefined) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".value", "确认事实必须有值。");
      }
      if (!SLOT_SOURCES.includes(/** @type {import("./type-contracts.js").SlotSource} */ (item.source))) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".source", "事实来源不在词表内。");
      }
    });
  }

  if (record.category !== null && record.category !== undefined) {
    const path = "$.category";
    if (!isPlainObject(record.category)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "category 必须是对象或 null。");
    } else {
      /** @type {Record<string, unknown>} */
      const category = /** @type {Record<string, unknown>} */ (/** @type {unknown} */ (record.category));
      if (category.slot_id !== "product_category") {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "类别只能来自 product_category 槽位。");
      }
      if (!isNonEmptyString(category.value)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".value", "category.value 必须非空。");
      }
      if (typeof category.slot_id !== "string" || !basisIds.has(category.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "category 必须来自 basis 中的槽位。");
      }
    }
  }

  if (!Array.isArray(record.unresolved)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.unresolved", "unresolved 必须是数组。");
  } else {
    /** @type {Set<string>} */
    const seen = new Set();
    /** @type {Array<unknown>} */
    const pending = /** @type {Array<unknown>} */ (record.unresolved);
    pending.forEach((/** @type {unknown} */ raw, /** @type {number} */ index) => {
      const path = "$.unresolved[" + index + "]";
      if (!isPlainObject(raw)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "unresolved 项必须是对象。");
        return;
      }
      /** @type {Record<string, unknown>} */
      const item = /** @type {Record<string, unknown>} */ (/** @type {unknown} */ (raw));
      if (typeof item.slot_id !== "string" || !SLOT_ID_PATTERN.test(item.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "unresolved.slot_id 非法。");
      } else if (seen.has(item.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "unresolved 中 slot_id 重复。");
      } else {
        seen.add(item.slot_id);
      }
      if (!UNRESOLVED_STATUSES.includes(/** @type {import("./type-contracts.js").UnresolvedItem["status"]} */ (item.status))) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".status",
          "unresolved.status 只能是 proposed/missing/conflict/unknown。");
      }
      if (typeof item.critical !== "boolean") {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".critical", "unresolved.critical 必须是布尔值。");
      }
      if (typeof item.slot_id === "string" && confirmedIds.has(item.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "同一个槽位不能既确认又待处理。");
      }
    });
  }
  return problems;
}

/**
 * 商品理解断言：合法时原样返回入参，不合法抛 DomainError（首个问题码）。
 * @param {unknown} brief
 * @returns {import("./type-contracts.js").ProductBrief}
 */
export function assertProductBrief(brief) {
  const problems = checkProductBrief(brief);
  if (problems.length) {
    throw new DomainError(problems[0].code,
      "商品理解不合法：" + problems.map((item) => item.message).join("；"), { problems });
  }
  return /** @type {import("./type-contracts.js").ProductBrief} */ (/** @type {unknown} */ (brief));
}

/**
 * 由当前槽位（含版本）投影出 ProductBrief；只做投影，不做任何推断。
 * @param {unknown} slotEntries
 * @returns {import("./type-contracts.js").ProductBrief}
 */
export function buildProductBrief(slotEntries) {
  if (!Array.isArray(slotEntries)) invalid("slotEntries 必须是数组。");
  /** @type {import("./type-contracts.js").ConfirmedFact[]} */
  const confirmedFacts = [];
  /** @type {import("./type-contracts.js").UnresolvedItem[]} */
  const unresolved = [];
  /** @type {import("./type-contracts.js").BriefBasisItem[]} */
  const basis = [];
  /** @type {import("./type-contracts.js").BriefCategory | null} */
  let category = null;
  for (const /** @type {unknown} */ rawEntry of /** @type {Array<unknown>} */ (slotEntries)) {
    if (!isPlainObject(rawEntry)) invalid("slotEntries 项必须是 { slot, version }。");
    /** @type {Record<string, unknown>} */
    const entry = rawEntry;
    if (!isPlainObject(entry.slot)) invalid("slotEntries 项必须是 { slot, version }。");
    /** @type {unknown} */
    const rawSlot = entry.slot;
    /** @type {unknown} */
    const version = entry.version;
    assertFactSlot(rawSlot);
    /** @type {import("./type-contracts.js").FactSlot} */
    const slot = /** @type {import("./type-contracts.js").FactSlot} */ (/** @type {unknown} */ (rawSlot));
    if (!Number.isInteger(version) || /** @type {number} */ (version) < 1) invalid("槽位版本必须是正整数。");
    basis.push({ slot_id: slot.slot_id, version: /** @type {number} */ (version) });
    if (slot.status === "confirmed") {
      confirmedFacts.push({
        slot_id: slot.slot_id, label: slot.label,
        value: /** @type {import("./type-contracts.js").FactSlotValue} */ (structuredClone(slot.value)),
        source: slot.source,
      });
      if (slot.slot_id === "product_category" && typeof slot.value === "string") {
        category = { slot_id: "product_category", value: slot.value };
      }
    } else if (UNRESOLVED_STATUSES.includes(/** @type {import("./type-contracts.js").UnresolvedItem["status"]} */ (slot.status))) {
      unresolved.push({
        slot_id: slot.slot_id, label: slot.label,
        status: /** @type {"proposed" | "missing" | "conflict" | "unknown"} */ (slot.status),
        critical: slot.critical === true,
      });
    }
  }
  return {
    schema_version: PRODUCT_BRIEF_SCHEMA_VERSION,
    basis, category, confirmed_facts: confirmedFacts, unresolved,
  };
}


/**
 * 槽位条目索引：按 slot_id 建表，供一致性与过期判定复用。
 * @param {unknown} slotEntries
 * @returns {Map<string, import("./type-contracts.js").SlotEntry>}
 */
function slotIndex(slotEntries) {
  /** @type {Map<string, import("./type-contracts.js").SlotEntry>} */
  const current = new Map();
  if (!Array.isArray(slotEntries)) return current;
  for (const /** @type {unknown} */ raw of slotEntries) {
    if (!isPlainObject(raw)) continue;
    /** @type {Record<string, unknown>} */
    const entry = raw;
    if (!isPlainObject(entry.slot)) continue;
    /** @type {Record<string, unknown>} */
    const slot = /** @type {Record<string, unknown>} */ (/** @type {unknown} */ (entry.slot));
    /** @type {unknown} */
    const id = slot.slot_id;
    if (typeof id !== "string") continue;
    current.set(
      id,
      /** @type {import("./type-contracts.js").SlotEntry} */ (/** @type {unknown} */ (entry)),
    );
  }
  return current;
}

/**
 * brief 与当前槽位集合的一致性：过期与投影错误分开报。
 * @param {unknown} brief
 * @param {unknown} slotEntries
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function briefProblemsAgainstSlots(brief, slotEntries) {
  const problems = checkProductBrief(brief);
  const current = slotIndex(slotEntries);
  /** @type {import("./type-contracts.js").ProductBrief} */
  const snapshot = /** @type {import("./type-contracts.js").ProductBrief} */ (/** @type {unknown} */ (brief));
  for (const item of snapshot.basis || []) {
    const entry = current.get(item.slot_id);
    if (!entry) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.basis",
        "basis 引用了不存在的槽位 " + item.slot_id + "。");
      continue;
    }
    if (entry.version !== item.version) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.basis",
        "槽位 " + item.slot_id + " 已有新版本（basis v" + item.version + " → 当前 v" + entry.version + "），商品理解已过期。");
    }
  }
  for (const fact of snapshot.confirmed_facts || []) {
    const entry = current.get(fact.slot_id);
    if (!entry) continue;
    if (entry.slot.status !== "confirmed") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.confirmed_facts",
        "槽位 " + fact.slot_id + " 当前状态是 " + entry.slot.status + "，不能再作为已确认事实。");
    } else if (!slotValueEquals(entry.slot.value, fact.value)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.confirmed_facts",
        "槽位 " + fact.slot_id + " 的值已改变，商品理解与事实不一致。");
    }
  }
  for (const item of snapshot.unresolved || []) {
    const entry = current.get(item.slot_id);
    if (entry && entry.slot.status === "confirmed") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.unresolved",
        "槽位 " + item.slot_id + " 已确认，不该继续留在待处理列表。");
    }
  }
  return problems;
}

/**
 * 商品理解是否过期：basis 版本与当前槽位版本逐项比对，给出可读原因。
 * @param {unknown} brief
 * @param {unknown} slotEntries
 * @returns {import("./type-contracts.js").BriefStaleness}
 */
export function briefIsStale(brief, slotEntries) {
  const current = slotIndex(slotEntries);
  /** @type {import("./type-contracts.js").BriefStaleness["reasons"]} */
  const reasons = [];
  /** @type {import("./type-contracts.js").ProductBrief} */
  const snapshot = /** @type {import("./type-contracts.js").ProductBrief} */ (/** @type {unknown} */ (brief));
  for (const item of snapshot.basis || []) {
    const entry = current.get(item.slot_id);
    if (!entry) {
      reasons.push({ slot_id: item.slot_id, basis_version: item.version, current_version: null, reason: "槽位已不存在" });
    } else if (entry.version !== item.version) {
      reasons.push({ slot_id: item.slot_id, basis_version: item.version, current_version: entry.version, reason: "槽位版本已前进" });
    }
  }
  return { stale: reasons.length > 0, reasons };
}

/**
 * 商品理解完成条件（计划 §5 第三行）：所有关键依赖 confirmed。
 * @param {unknown} brief
 * @returns {import("./type-contracts.js").BriefReadiness}
 */
export function briefReadiness(brief) {
  /** @type {import("./type-contracts.js").BriefReadiness["blocking"]} */
  const blocking = [];
  /** @type {import("./type-contracts.js").ProductBrief} */
  const snapshot = /** @type {import("./type-contracts.js").ProductBrief} */ (/** @type {unknown} */ (brief));
  for (const item of snapshot.unresolved || []) {
    if (item.critical === true) {
      blocking.push({
        code: "CRITICAL_SLOT_UNRESOLVED", slot_id: item.slot_id, status: item.status,
        message: "关键槽位 " + item.slot_id + " 仍是 " + item.status + "。",
      });
    }
  }
  if (!(snapshot.confirmed_facts || []).length) {
    blocking.push({
      code: "NO_CONFIRMED_FACTS", slot_id: null, status: "missing",
      message: "还没有任何已确认事实。",
    });
  }
  return { ready: blocking.length === 0, blocking };
}
