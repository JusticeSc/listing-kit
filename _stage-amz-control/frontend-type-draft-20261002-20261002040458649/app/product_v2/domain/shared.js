/**
 * Product V2 领域契约的共享底座（V2.2.1）。
 *
 * 这一层只放"多处都要用、且不许各自解释一遍"的东西：schema 版本、长度上限、
 * JSON 形状判据与问题收集器。业务规则在 slots / intake / brief / invalidation。
 *
 * 类型枢纽：可复用的基础契约类型集中在这里，其它模块用
 * `import("./shared.js").TypeName` 引用，不复制第二套。
 *
 * @typedef {string} Sha256Hex 64 位小写十六进制（运行时由 isSha256Hex 判定）。
 * @typedef {string} IsoTimestamp ISO-8601 时间戳（运行时由 isIsoTimestamp 判定）。
 * @typedef {{code: string, path: string, message: string}} DomainProblem 校验问题项。
 * @typedef {{kind: string, ref: string, note?: string, observed_at?: string}} EvidenceItem 证据项。
 * @typedef {string | number | boolean | Array<string | number | boolean>} SlotValue 槽位值：标量或标量数组。
 * @typedef {Record<string, unknown>} PlainRecord 纯对象记录（isPlainObject 守卫后的形状）。
 * @typedef {(bytes: Uint8Array) => Promise<string>} DigestFn 注入的 sha256 摘要函数。
 * @typedef {(sha256: string) => Promise<Uint8Array | null>} ReadBytesFn 按 sha256 读字节的注入函数。
 * @typedef {(shotId: string) => boolean} PromptReadyFn 某 Shot 是否已有可编译 Prompt。
 * @typedef {(shotId: string) => boolean} CandidateStoredFn 某 Shot 的成功候选是否已落库。
 * @typedef {() => string} RandomSourceFn 随机源（newActionId 注入，便于测试确定性）。
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
  candidate: "candidate",
  review_report: "review_report",
  selection: "selection",
  suite_review: "suite_review",
  export_record: "export_record",
  review_acknowledgement: "review_acknowledgement",
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

/**
 * @param {unknown} value
 * @returns {value is PlainRecord}
 */
export function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

/**
 * @param {unknown} value
 * @returns {value is string}
 */
export function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

/**
 * @param {unknown} value
 * @returns {value is string}
 */
export function isSha256Hex(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

/**
 * @param {unknown} value
 * @returns {value is string}
 */
export function isIsoTimestamp(value) {
  return typeof value === "string" && value.length >= 20 && !Number.isNaN(Date.parse(value));
}

/**
 * @param {DomainProblem[]} problems
 * @param {string} code
 * @param {string} path
 * @param {string} message
 * @returns {void}
 */
export function pushProblem(problems, code, path, message) {
  problems.push({ code, path, message });
}

/** 版本只向前；读到更高版本的对象必须显式拒绝，而不是猜着读。 */
/**
 * @param {{schema_version?: unknown}} record
 * @param {number} expected
 * @param {DomainProblem[]} problems
 * @param {string} path
 * @returns {void}
 */
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

/**
 * @param {DomainProblem[]} problems
 * @param {string} path
 * @param {string} valueType
 * @param {unknown} value
 * @param {unknown} [enumValues]
 * @returns {void}
 */
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

/**
 * @param {DomainProblem[]} problems
 * @param {string} path
 * @param {unknown} evidence
 * @returns {void}
 */
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
