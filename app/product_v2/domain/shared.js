/**
 * Product V2 领域契约的共享底座（V2.2.1）。
 *
 * 这一层只放"多处都要用、且不许各自解释一遍"的东西：schema 版本、长度上限、
 * JSON 形状判据与问题收集器。业务规则在 slots / intake / brief / invalidation。
 */

import { DOMAIN_ERROR_CODES } from "./errors.js";

export const PRODUCT_INPUT_SCHEMA_VERSION = 1;
export const FACT_SLOT_SCHEMA_VERSION = 1;
export const PRODUCT_BRIEF_SCHEMA_VERSION = 1;

/** 文档种类（与 storage 的 DOCUMENT_KIND_PATTERN 一致）。 */
export const DOMAIN_DOCUMENT_KINDS = Object.freeze({
  product_input: "product_input",
  fact_slot: "fact_slot",
  product_brief: "product_brief",
  suite_plan: "suite_plan",
  style_spec: "style_spec",
  shot_spec: "shot_spec",
  prompt_version: "prompt_version",
  generation_confirm: "generation_confirm",
  generation_attempt: "generation_attempt",
});

export const MAX_TEXT_LENGTH = 500;
export const MAX_LIST_ITEMS = 20;
export const MAX_LIST_ITEM_LENGTH = 200;
export const MAX_PRODUCT_NAME_LENGTH = 120;
export const MAX_DESCRIPTION_LENGTH = 2000;
export const MAX_FOCUS_LENGTH = 500;
export const MAX_REFERENCES = 20;
export const SLOT_ID_PATTERN = /^[a-z][a-z0-9_]{1,47}$/;

export const EVIDENCE_KINDS = Object.freeze(["user", "asset", "model", "rule"]);

export function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

export function isSha256Hex(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

export function isIsoTimestamp(value) {
  return typeof value === "string" && value.length >= 20 && !Number.isNaN(Date.parse(value));
}

export function pushProblem(problems, code, path, message) {
  problems.push({ code, path, message });
}

/** 版本只向前；读到更高版本的对象必须显式拒绝，而不是猜着读。 */
export function checkSchemaVersion(record, expected, problems, path) {
  const version = record.schema_version;
  if (!Number.isInteger(version) || version < 1) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".schema_version",
      "缺少正整数 schema_version。");
    return;
  }
  if (version > expected) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_SCHEMA_TOO_NEW, path + ".schema_version",
      "对象版本 " + version + " 高于当前契约 " + expected + "，不要降级覆盖。");
  }
}

export function checkValueShape(problems, path, valueType, value, enumValues) {
  if (valueType === "text") {
    if (!isNonEmptyString(value)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "text 值必须是非空字符串。");
    } else if (value.length > MAX_TEXT_LENGTH) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "text 值超过 " + MAX_TEXT_LENGTH + " 字符。");
    }
    return;
  }
  if (valueType === "text_list") {
    if (!Array.isArray(value) || value.length === 0) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "text_list 值必须是非空数组。");
      return;
    }
    if (value.length > MAX_LIST_ITEMS) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "text_list 超过 " + MAX_LIST_ITEMS + " 项。");
    }
    value.forEach((item, index) => {
      if (!isNonEmptyString(item)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + "[" + index + "]", "text_list 项必须是非空字符串。");
      } else if (item.length > MAX_LIST_ITEM_LENGTH) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + "[" + index + "]", "text_list 项超过 " + MAX_LIST_ITEM_LENGTH + " 字符。");
      }
    });
    return;
  }
  if (valueType === "number") {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "number 值必须是有限数字。");
    }
    return;
  }
  if (valueType === "boolean") {
    if (typeof value !== "boolean") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "boolean 值必须是 true/false。");
    }
    return;
  }
  if (valueType === "enum") {
    if (!Array.isArray(enumValues) || enumValues.length === 0
        || enumValues.some((item) => !isNonEmptyString(item))) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID,
        path.replace(/\.value$/, ".enum_values"), "enum 类型必须声明非空 enum_values。");
      return;
    }
    if (!enumValues.includes(value)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "enum 值不在 enum_values 内。");
    }
    return;
  }
  pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path,
    "未知 value_type " + JSON.stringify(valueType) + "。");
}

export function checkEvidenceList(problems, path, evidence) {
  if (!Array.isArray(evidence)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "evidence 必须是数组。");
    return;
  }
  evidence.forEach((item, index) => {
    const itemPath = path + "[" + index + "]";
    if (!isPlainObject(item)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, itemPath, "evidence 项必须是对象。");
      return;
    }
    if (!EVIDENCE_KINDS.includes(item.kind)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, itemPath + ".kind", "evidence.kind 不在词表内。");
    }
    if (!isNonEmptyString(item.ref)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, itemPath + ".ref", "evidence.ref 必须是非空字符串。");
    }
    if (item.note !== undefined && typeof item.note !== "string") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, itemPath + ".note", "evidence.note 只能是字符串。");
    }
    if (item.observed_at !== undefined && !isIsoTimestamp(item.observed_at)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, itemPath + ".observed_at", "evidence.observed_at 必须是 ISO 时间戳。");
    }
  });
}
