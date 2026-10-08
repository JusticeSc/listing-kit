/**
 * ProductInput 契约（V2.2.1）：用户在商品资料页填的东西，以及"资料齐没齐"的判据。
 *
 * 只有用户显式填写的内容进这里；模型推断、参考图观察都不许写进 ProductInput。
 */

import { DOMAIN_ERROR_CODES, DomainError, invalid } from "./errors.js";
import {
  MAX_DESCRIPTION_LENGTH,
  MAX_FOCUS_LENGTH,
  MAX_LIST_ITEM_LENGTH,
  MAX_LIST_ITEMS,
  MAX_PRODUCT_NAME_LENGTH,
  MAX_REFERENCES,
  PRODUCT_INPUT_SCHEMA_VERSION,
  checkSchemaVersion,
  isNonEmptyString,
  isPlainObject,
  isSha256Hex,
  pushProblem,
} from "./shared.js";

// 与语义契约的 ReferencedAsset.role 逐字一致（V2.3.1：对比图依赖需要 competitor 角色；
// 跨语言一致性由 tools/verify_v2_2_2_semantic_provider.py 的跨语言合同项守住）。
/** @type {readonly import("./type-contracts.js").ReferenceRole[]} */
export const REFERENCE_ROLES = Object.freeze([
  "primary", "detail", "packaging", "scene", "competitor", "other",
]);

/**
 * 商品资料自检：名称、介绍、卖点、参考图的形状与词表，返回问题列表（空数组 = 合法），不抛异常。
 * @param {unknown} input
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkProductInput(input) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
  const problems = [];
  if (!isPlainObject(input)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "商品资料必须是对象。");
    return problems;
  }
  /** @type {Record<string, unknown>} */
  const record = /** @type {Record<string, unknown>} */ (/** @type {unknown} */ (input));
  checkSchemaVersion(record, PRODUCT_INPUT_SCHEMA_VERSION, problems, "$");
  if (!isNonEmptyString(record.product_name)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.product_name", "商品名称必填。");
  } else if (/** @type {string} */ (record.product_name).length > MAX_PRODUCT_NAME_LENGTH) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.product_name",
      "商品名称超过 " + MAX_PRODUCT_NAME_LENGTH + " 字符。");
  }
  if (record.description !== undefined) {
    if (typeof record.description !== "string") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.description", "介绍必须是字符串。");
    } else if (/** @type {string} */ (record.description).length > MAX_DESCRIPTION_LENGTH) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.description",
        "介绍超过 " + MAX_DESCRIPTION_LENGTH + " 字符。");
    }
  }
  if (record.focus !== undefined) {
    if (typeof record.focus !== "string") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.focus", "本次重点必须是字符串。");
    } else if (/** @type {string} */ (record.focus).length > MAX_FOCUS_LENGTH) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.focus",
        "本次重点超过 " + MAX_FOCUS_LENGTH + " 字符。");
    }
  }
  if (record.selling_points !== undefined) {
    if (!Array.isArray(record.selling_points)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.selling_points", "卖点必须是数组。");
    } else {
      /** @type {Array<unknown>} */
      const points = /** @type {Array<unknown>} */ (record.selling_points);
      if (points.length > MAX_LIST_ITEMS) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.selling_points",
          "卖点超过 " + MAX_LIST_ITEMS + " 条。");
      }
      points.forEach((/** @type {unknown} */ item, /** @type {number} */ index) => {
        const path = "$.selling_points[" + index + "]";
        if (!isNonEmptyString(item)) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "卖点必须是非空字符串。");
        } else if (/** @type {string} */ (item).length > MAX_LIST_ITEM_LENGTH) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path,
            "卖点超过 " + MAX_LIST_ITEM_LENGTH + " 字符。");
        }
      });
    }
  }
  /** @type {unknown} */
  const references = record.references;
  if (!Array.isArray(references) || references.length === 0) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.references", "至少需要一张参考图。");
  } else {
    /** @type {Array<unknown>} */
    const items = /** @type {Array<unknown>} */ (references);
    if (items.length > MAX_REFERENCES) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.references",
        "参考图超过 " + MAX_REFERENCES + " 张。");
    }
    /** @type {Set<string>} */
    const seen = new Set();
    items.forEach((/** @type {unknown} */ raw, /** @type {number} */ index) => {
      const path = "$.references[" + index + "]";
      if (!isPlainObject(raw)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "参考图项必须是对象。");
        return;
      }
      /** @type {Record<string, unknown>} */
      const item = /** @type {Record<string, unknown>} */ (/** @type {unknown} */ (raw));
      if (!isSha256Hex(item.asset_sha256)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".asset_sha256",
          "参考图必须引用资产 sha256。");
      } else if (seen.has(/** @type {string} */ (item.asset_sha256))) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".asset_sha256",
          "同一资产不允许重复登记。");
      } else {
        seen.add(/** @type {string} */ (item.asset_sha256));
      }
      if (!REFERENCE_ROLES.includes(/** @type {import("./type-contracts.js").ReferenceRole} */ (item.role))) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".role", "参考图角色不在词表内。");
      }
      if (item.note !== undefined && typeof item.note !== "string") {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".note", "参考图备注只能是字符串。");
      }
    });
    if (!items.some((/** @type {unknown} */ raw) => isPlainObject(raw) && /** @type {Record<string, unknown>} */ (raw).role === "primary")) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.references",
        "至少需要一张 primary 角色参考图。");
    }
  }
  return problems;
}

/**
 * 商品资料断言：合法时原样返回入参，不合法抛 DomainError（CONTRACT_INVALID）。
 * @param {unknown} input
 * @returns {import("./type-contracts.js").ProductInput}
 */
export function assertProductInput(input) {
  const problems = checkProductInput(input);
  if (problems.length) {
    throw new DomainError(DOMAIN_ERROR_CODES.CONTRACT_INVALID,
      "商品资料不合法：" + problems.map((item) => item.message).join("；"), { problems });
  }
  return /** @type {import("./type-contracts.js").ProductInput} */ (/** @type {unknown} */ (input));
}

/**
 * 商品资料完成条件（计划 §5 第二行）：名称和参考图齐全。
 * @param {unknown} input
 * @returns {import("./type-contracts.js").IntakeReadiness}
 */
export function intakeReadiness(input) {
  const problems = checkProductInput(input);
  if (problems.length) return { ready: false, blocking: problems };
  return { ready: true, blocking: [] };
}

/**
 * 空白资料：新建项目后的起点；ready 为 false，界面据此显示空状态。
 * @returns {import("./type-contracts.js").ProductInput}
 */
export function emptyProductInput() {
  return {
    schema_version: PRODUCT_INPUT_SCHEMA_VERSION,
    product_name: "",
    description: "",
    selling_points: [],
    focus: "",
    references: [],
  };
}

/**
 * 由已保存资产登记一条参考图；资产必须含 sha256，角色必须在词表内。
 * @param {unknown} asset
 * @param {{role?: unknown, note?: unknown}} [options]
 * @returns {import("./type-contracts.js").ProductReference}
 */
export function referenceFromAsset(asset, { role = "primary", note } = {}) {
  if (!isPlainObject(asset)) invalid("参考图必须来自已保存的资产（含 sha256）。");
  /** @type {Record<string, unknown>} */
  const saved = asset;
  if (!isSha256Hex(saved.sha256)) invalid("参考图必须来自已保存的资产（含 sha256）。");
  if (!REFERENCE_ROLES.includes(/** @type {import("./type-contracts.js").ReferenceRole} */ (role))) invalid("参考图角色不在词表内。");
  /** @type {import("./type-contracts.js").ProductReference} */
  const entry = {
    asset_sha256: /** @type {import("./type-contracts.js").Sha256Hex} */ (saved.sha256),
    role: /** @type {import("./type-contracts.js").ReferenceRole} */ (role),
  };
  if (note !== undefined) entry.note = /** @type {string} */ (note);
  return entry;
}
