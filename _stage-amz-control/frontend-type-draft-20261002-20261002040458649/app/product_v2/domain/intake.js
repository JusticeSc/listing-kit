/**
 * ProductInput 契约（V2.2.1）：用户在商品资料页填的东西，以及"资料齐没齐"的判据。
 *
 * 只有用户显式填写的内容进这里；模型推断、参考图观察都不许写进 ProductInput。
 *
 * @typedef {{
 *   schema_version: number,
 *   product_name: string,
 *   description?: string,
 *   focus?: string,
 *   selling_points?: string[],
 *   references: ProductReference[],
 * }} ProductInput
 * @typedef {{
 *   asset_sha256: import("./shared.js").Sha256Hex,
 *   role: string,
 *   note?: string,
 * }} ProductReference
 * @typedef {{sha256?: string}} AssetIdentity 最小资产身份（referenceFromAsset 只读 sha256）。
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
export const REFERENCE_ROLES = Object.freeze([
  "primary", "detail", "packaging", "scene", "competitor", "other",
]);

/**
 * @param {unknown} input
 * @returns {import("./shared.js").DomainProblem[]}
 */
export function checkProductInput(input) {
  const problems = [];
  if (!isPlainObject(input)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "商品资料必须是对象。");
    return problems;
  }
  checkSchemaVersion(input, PRODUCT_INPUT_SCHEMA_VERSION, problems, "$");
  if (!isNonEmptyString(input.product_name)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.product_name", "商品名称必填。");
  } else if (input.product_name.length > MAX_PRODUCT_NAME_LENGTH) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.product_name",
      "商品名称超过 " + MAX_PRODUCT_NAME_LENGTH + " 字符。");
  }
  if (input.description !== undefined) {
    if (typeof input.description !== "string") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.description", "介绍必须是字符串。");
    } else if (input.description.length > MAX_DESCRIPTION_LENGTH) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.description",
        "介绍超过 " + MAX_DESCRIPTION_LENGTH + " 字符。");
    }
  }
  if (input.focus !== undefined) {
    if (typeof input.focus !== "string") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.focus", "本次重点必须是字符串。");
    } else if (input.focus.length > MAX_FOCUS_LENGTH) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.focus",
        "本次重点超过 " + MAX_FOCUS_LENGTH + " 字符。");
    }
  }
  if (input.selling_points !== undefined) {
    if (!Array.isArray(input.selling_points)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.selling_points", "卖点必须是数组。");
    } else {
      if (input.selling_points.length > MAX_LIST_ITEMS) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.selling_points",
          "卖点超过 " + MAX_LIST_ITEMS + " 条。");
      }
      input.selling_points.forEach((item, index) => {
        const path = "$.selling_points[" + index + "]";
        if (!isNonEmptyString(item)) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "卖点必须是非空字符串。");
        } else if (item.length > MAX_LIST_ITEM_LENGTH) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path,
            "卖点超过 " + MAX_LIST_ITEM_LENGTH + " 字符。");
        }
      });
    }
  }
  const references = input.references;
  if (!Array.isArray(references) || references.length === 0) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.references", "至少需要一张参考图。");
  } else {
    if (references.length > MAX_REFERENCES) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.references",
        "参考图超过 " + MAX_REFERENCES + " 张。");
    }
    const seen = new Set();
    references.forEach((item, index) => {
      const path = "$.references[" + index + "]";
      if (!isPlainObject(item)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "参考图项必须是对象。");
        return;
      }
      if (!isSha256Hex(item.asset_sha256)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".asset_sha256",
          "参考图必须引用资产 sha256。");
      } else if (seen.has(item.asset_sha256)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".asset_sha256",
          "同一资产不允许重复登记。");
      } else {
        seen.add(item.asset_sha256);
      }
      if (!REFERENCE_ROLES.includes(item.role)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".role", "参考图角色不在词表内。");
      }
      if (item.note !== undefined && typeof item.note !== "string") {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".note", "参考图备注只能是字符串。");
      }
    });
    if (!references.some((item) => isPlainObject(item) && item.role === "primary")) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.references",
        "至少需要一张 primary 角色参考图。");
    }
  }
  return problems;
}

/**
 * @param {unknown} input
 * @returns {ProductInput}
 */
export function assertProductInput(input) {
  const problems = checkProductInput(input);
  if (problems.length) {
    throw new DomainError(DOMAIN_ERROR_CODES.CONTRACT_INVALID,
      "商品资料不合法：" + problems.map((item) => item.message).join("；"), { problems });
  }
  return input;
}

/** 商品资料完成条件（计划 §5 第二行）：名称和参考图齐全。 */
/**
 * @typedef {{ready: boolean, blocking: string[]}} IntakeReadiness
 * @param {unknown} input
 * @returns {IntakeReadiness}
 */
export function intakeReadiness(input) {
  const problems = checkProductInput(input);
  if (problems.length) return { ready: false, blocking: problems };
  return { ready: true, blocking: [] };
}

/** 空白资料：新建项目后的起点；ready 为 false，界面据此显示空状态。
 *
 * @returns {ProductInput}
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
 * @param {AssetIdentity} asset
 * @param {{role?: string, note?: string}} [options]
 * @returns {ProductReference}
 */
export function referenceFromAsset(asset, { role = "primary", note } = {}) {
  if (!isPlainObject(asset) || !isSha256Hex(asset.sha256)) invalid("参考图必须来自已保存的资产（含 sha256）。");
  if (!REFERENCE_ROLES.includes(role)) invalid("参考图角色不在词表内。");
  const entry = { asset_sha256: asset.sha256, role };
  if (note !== undefined) entry.note = note;
  return entry;
}
