/**
 * ProductBrief 契约（V2.2.1）：已确认事实的投影 + 待处理异常 + 就绪门。
 *
 * ProductBrief 不是"另一份事实"，它是某几个精确槽位版本的投影：
 *   basis 记录"我读的是哪些槽位的哪个版本"，因此上游一变就能机检过期，
 *   而不是靠界面自己记得刷新。
 *
 * @typedef {{
 *   schema_version: number,
 *   basis: Array<{slot_id: string, version: number}>,
 *   category: {slot_id: string, value: string} | null,
 *   confirmed_facts: Array<{slot_id: string, label: string, value: import("./shared.js").SlotValue, source: string}>,
 *   unresolved: Array<{slot_id: string, label: string, status: string, critical: boolean}>,
 * }} ProductBrief
 * @typedef {import("./slots.js").SlotEntry} SlotEntry
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

const UNRESOLVED_STATUSES = Object.freeze(["proposed", "missing", "conflict", "unknown"]);

/**
 * @param {unknown} brief
 * @returns {import("./shared.js").DomainProblem[]}
 */
export function checkProductBrief(brief) {
  const problems = [];
  if (!isPlainObject(brief)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "商品理解必须是对象。");
    return problems;
  }
  checkSchemaVersion(brief, PRODUCT_BRIEF_SCHEMA_VERSION, problems, "$");

  const basisIds = new Set();
  if (!Array.isArray(brief.basis)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.basis", "basis 必须是数组（可为空）。");
  } else {
    brief.basis.forEach((item, index) => {
      const path = "$.basis[" + index + "]";
      if (!isPlainObject(item)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "basis 项必须是对象。");
        return;
      }
      if (typeof item.slot_id !== "string" || !SLOT_ID_PATTERN.test(item.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "basis.slot_id 非法。");
      } else if (basisIds.has(item.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "basis 中 slot_id 重复。");
      } else {
        basisIds.add(item.slot_id);
      }
      if (!Number.isInteger(item.version) || item.version < 1) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".version", "basis.version 必须是正整数。");
      }
    });
  }

  const confirmedIds = new Set();
  if (!Array.isArray(brief.confirmed_facts)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.confirmed_facts", "confirmed_facts 必须是数组。");
  } else {
    brief.confirmed_facts.forEach((item, index) => {
      const path = "$.confirmed_facts[" + index + "]";
      if (!isPlainObject(item)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "confirmed_facts 项必须是对象。");
        return;
      }
      if (typeof item.slot_id !== "string" || !SLOT_ID_PATTERN.test(item.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "confirmed_facts.slot_id 非法。");
      } else if (confirmedIds.has(item.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "confirmed_facts 中 slot_id 重复。");
      } else {
        confirmedIds.add(item.slot_id);
      }
      if (item.slot_id !== undefined && !basisIds.has(item.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "confirmed_facts 引用了不在 basis 里的槽位。");
      }
      if (!isNonEmptyString(item.label)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".label", "事实必须有 label。");
      }
      if (item.value === null || item.value === undefined) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".value", "确认事实必须有值。");
      }
      if (!SLOT_SOURCES.includes(item.source)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".source", "事实来源不在词表内。");
      }
    });
  }

  if (brief.category !== null && brief.category !== undefined) {
    const path = "$.category";
    if (!isPlainObject(brief.category)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "category 必须是对象或 null。");
    } else {
      if (brief.category.slot_id !== "product_category") {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "类别只能来自 product_category 槽位。");
      }
      if (!isNonEmptyString(brief.category.value)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".value", "category.value 必须非空。");
      }
      if (!basisIds.has(brief.category.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "category 必须来自 basis 中的槽位。");
      }
    }
  }

  if (!Array.isArray(brief.unresolved)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.unresolved", "unresolved 必须是数组。");
  } else {
    const seen = new Set();
    brief.unresolved.forEach((item, index) => {
      const path = "$.unresolved[" + index + "]";
      if (!isPlainObject(item)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "unresolved 项必须是对象。");
        return;
      }
      if (typeof item.slot_id !== "string" || !SLOT_ID_PATTERN.test(item.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "unresolved.slot_id 非法。");
      } else if (seen.has(item.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "unresolved 中 slot_id 重复。");
      } else {
        seen.add(item.slot_id);
      }
      if (!UNRESOLVED_STATUSES.includes(item.status)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".status",
          "unresolved.status 只能是 proposed/missing/conflict/unknown。");
      }
      if (typeof item.critical !== "boolean") {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".critical", "unresolved.critical 必须是布尔值。");
      }
      if (confirmedIds.has(item.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".slot_id", "同一个槽位不能既确认又待处理。");
      }
    });
  }
  return problems;
}

/**
 * @param {unknown} brief
 * @returns {ProductBrief}
 */
export function assertProductBrief(brief) {
  const problems = checkProductBrief(brief);
  if (problems.length) {
    throw new DomainError(problems[0].code,
      "商品理解不合法：" + problems.map((item) => item.message).join("；"), { problems });
  }
  return brief;
}

/** 由当前槽位（含版本）投影出 ProductBrief；只做投影，不做任何推断。 */
/**
 * @param {SlotEntry[]} slotEntries
 * @returns {ProductBrief}
 */
export function buildProductBrief(slotEntries) {
  if (!Array.isArray(slotEntries)) invalid("slotEntries 必须是数组。");
  const confirmedFacts = [];
  const unresolved = [];
  const basis = [];
  let category = null;
  for (const entry of slotEntries) {
    if (!isPlainObject(entry) || !isPlainObject(entry.slot)) invalid("slotEntries 项必须是 { slot, version }。");
    const slot = entry.slot;
    const version = entry.version;
    assertFactSlot(slot);
    if (!Number.isInteger(version) || version < 1) invalid("槽位版本必须是正整数。");
    basis.push({ slot_id: slot.slot_id, version });
    if (slot.status === "confirmed") {
      confirmedFacts.push({
        slot_id: slot.slot_id, label: slot.label,
        value: structuredClone(slot.value), source: slot.source,
      });
      if (slot.slot_id === "product_category" && typeof slot.value === "string") {
        category = { slot_id: slot.slot_id, value: slot.value };
      }
    } else if (UNRESOLVED_STATUSES.includes(slot.status)) {
      unresolved.push({
        slot_id: slot.slot_id, label: slot.label, status: slot.status,
        critical: slot.critical === true,
      });
    }
  }
  return {
    schema_version: PRODUCT_BRIEF_SCHEMA_VERSION,
    basis, category, confirmed_facts: confirmedFacts, unresolved,
  };
}

function slotIndex(slotEntries) {
  const current = new Map();
  for (const entry of slotEntries || []) {
    if (entry && isPlainObject(entry.slot) && typeof entry.slot.slot_id === "string") {
      current.set(entry.slot.slot_id, entry);
    }
  }
  return current;
}

/** brief 与当前槽位集合的一致性：过期与投影错误分开报。 */
/**
 * @param {unknown} brief
 * @param {unknown} slotEntries
 * @returns {import("./shared.js").DomainProblem[]}
 */
export function briefProblemsAgainstSlots(brief, slotEntries) {
  const problems = checkProductBrief(brief);
  const current = slotIndex(slotEntries);
  for (const item of brief.basis || []) {
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
  for (const fact of brief.confirmed_facts || []) {
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
  for (const item of brief.unresolved || []) {
    const entry = current.get(item.slot_id);
    if (entry && entry.slot.status === "confirmed") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.unresolved",
        "槽位 " + item.slot_id + " 已确认，不该继续留在待处理列表。");
    }
  }
  return problems;
}

/**
 * 过期原因：basis 里某槽位不存在或版本已前进。
 *
 * @typedef {{stale: boolean, reasons: Array<{slot_id: string, basis_version: number|null, current_version: number|null, reason: string}>}} BriefStaleness
 * @param {unknown} brief
 * @param {unknown} slotEntries
 * @returns {BriefStaleness}
 */
export function briefIsStale(brief, slotEntries) {
  const current = slotIndex(slotEntries);
  const reasons = [];
  for (const item of brief.basis || []) {
    const entry = current.get(item.slot_id);
    if (!entry) {
      reasons.push({ slot_id: item.slot_id, basis_version: item.version, current_version: null, reason: "槽位已不存在" });
    } else if (entry.version !== item.version) {
      reasons.push({ slot_id: item.slot_id, basis_version: item.version, current_version: entry.version, reason: "槽位版本已前进" });
    }
  }
  return { stale: reasons.length > 0, reasons };
}

/** 商品理解完成条件（计划 §5 第三行）：所有关键依赖 confirmed。
 *
 * @typedef {{code: string, slot_id: string|null, status: string, message: string}} BriefBlocker
 * @typedef {{ready: boolean, blocking: BriefBlocker[]}} BriefReadiness
 * @param {unknown} brief
 * @returns {BriefReadiness}
 */
export function briefReadiness(brief) {
  const blocking = [];
  for (const item of brief.unresolved || []) {
    if (item.critical === true) {
      blocking.push({
        code: "CRITICAL_SLOT_UNRESOLVED", slot_id: item.slot_id, status: item.status,
        message: "关键槽位 " + item.slot_id + " 仍是 " + item.status + "。",
      });
    }
  }
  if (!(brief.confirmed_facts || []).length) {
    blocking.push({
      code: "NO_CONFIRMED_FACTS", slot_id: null, status: "missing",
      message: "还没有任何已确认事实。",
    });
  }
  return { ready: blocking.length === 0, blocking };
}
