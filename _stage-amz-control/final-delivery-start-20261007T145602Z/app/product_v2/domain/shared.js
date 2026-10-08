/**
 * Product V2 领域契约的共享底座（V2.2.1）。
 *
 * 这一层只放"多处都要用、且不许各自解释一遍"的东西：schema 版本、长度上限、
 * JSON 形状判据与问题收集器。业务规则在 slots / intake / brief / invalidation。
 */

// 类型：见 ./type-contracts.d.ts（DomainProblem / DimensionMeasurement / EvidenceItem）。

import { DOMAIN_ERROR_CODES } from "./errors.js";

export const PRODUCT_INPUT_SCHEMA_VERSION = 1;
export const FACT_SLOT_SCHEMA_VERSION = 1;
export const PRODUCT_BRIEF_SCHEMA_VERSION = 1;

/** 文档种类（与 storage 的 DOCUMENT_KIND_PATTERN 一致）。 @type {Readonly<Record<import("./type-contracts.js").DomainDocumentKind, import("./type-contracts.js").DomainDocumentKind>>} */
export const DOMAIN_DOCUMENT_KINDS = Object.freeze({
  product_input: "product_input",
  semantic_analysis: "semantic_analysis",
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

/**
 * 尺寸事实的轴向与单位词表（V2.R6.2）：尺寸必须显式绑定对象/轴向/有限正数/单位与来源依据，
 * 不能用自由文本或任意标量事实冒充测量。这个词表是领域唯一的尺寸表达口径。
 */
/** @type {readonly import("./type-contracts.js").DimensionAxis[]} */
export const DIMENSION_AXES = Object.freeze([
  "height", "width", "length", "depth", "diameter", "weight", "volume", "thickness",
]);
/** @type {readonly import("./type-contracts.js").DimensionUnit[]} */
export const DIMENSION_UNITS = Object.freeze([
  "mm", "cm", "m", "in", "ft", "g", "kg", "ml", "l", "oz", "lb",
]);
export const MAX_DIMENSIONS = 12;
export const MAX_DIMENSION_OBJECT_LENGTH = 60;
export const MAX_DIMENSION_SOURCE_LENGTH = 120;

/** @type {readonly import("./type-contracts.js").EvidenceKind[]} */
export const EVIDENCE_KINDS = Object.freeze(["user", "asset", "model", "rule"]);

/**
 * @param {unknown} value
 * @returns {value is Record<string, unknown>}
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
 * @returns {value is import("./type-contracts.js").Sha256Hex}
 */
export function isSha256Hex(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

/**
 * @param {unknown} value
 * @returns {value is import("./type-contracts.js").IsoTimestamp}
 */
export function isIsoTimestamp(value) {
  return typeof value === "string" && value.length >= 20 && !Number.isNaN(Date.parse(value));
}

/**
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {string} code
 * @param {string} path
 * @param {string} message
 * @returns {void}
 */
export function pushProblem(problems, code, path, message) {
  problems.push({ code, path, message });
}

/**
 * @param {unknown} record
 * @param {number} expected
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {string} path
 * @returns {void}
 */
export function checkSchemaVersion(record, expected, problems, path) {
  const version = isPlainObject(record) ? record.schema_version : undefined;
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
 * @param {import("./type-contracts.js").DomainProblem[]} problems
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
    } else if (/** @type {string} */ (value).length > MAX_TEXT_LENGTH) {
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
      } else if (/** @type {string} */ (item).length > MAX_LIST_ITEM_LENGTH) {
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
    if (!/** @type {unknown[]} */ (/** @type {unknown} */ (enumValues)).includes(value)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "enum 值不在 enum_values 内。");
    }
    return;
  }
  if (valueType === "dimension_list") {
    checkDimensionList(problems, path, value);
    return;
  }
  pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path,
    "未知 value_type " + JSON.stringify(valueType) + "。");
}

/** 一条尺寸测量：对象 / 轴向 / 有限正数 / 单位 / 来源依据，缺一不可。
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {string} path
 * @param {unknown} item
 * @returns {void}
 */
export function checkDimension(problems, path, item) {
  if (!isPlainObject(item)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path,
      "尺寸测量必须是对象（object/axis/value/unit/source_basis）。");
    return;
  }
  /** @type {Record<string, unknown>} */
  const measurement = /** @type {Record<string, unknown>} */ (/** @type {unknown} */ (item));
  if (!isNonEmptyString(measurement.object) || /** @type {string} */ (measurement.object).length > MAX_DIMENSION_OBJECT_LENGTH) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".object",
      "尺寸测量必须说明测量对象（1-" + MAX_DIMENSION_OBJECT_LENGTH + " 字）。");
  }
  if (!/** @type {readonly unknown[]} */ (/** @type {unknown} */ (DIMENSION_AXES)).includes(measurement.axis)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".axis",
      "轴向必须在词表内：" + DIMENSION_AXES.join("/") + "。");
  }
  if (typeof measurement.value !== "number" || !Number.isFinite(measurement.value) || /** @type {number} */ (measurement.value) <= 0) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".value",
      "尺寸数值必须是有限正数（不许自由文本或 0/负值）。");
  }
  if (!/** @type {readonly unknown[]} */ (/** @type {unknown} */ (DIMENSION_UNITS)).includes(measurement.unit)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".unit",
      "单位必须在词表内：" + DIMENSION_UNITS.join("/") + "。");
  }
  if (!isNonEmptyString(measurement.source_basis) || /** @type {string} */ (measurement.source_basis).length > MAX_DIMENSION_SOURCE_LENGTH) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".source_basis",
      "尺寸测量必须给出人确认的来源依据（1-" + MAX_DIMENSION_SOURCE_LENGTH + " 字）。");
  }
}

/**
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {string} path
 * @param {unknown} value
 * @returns {void}
 */
export function checkDimensionList(problems, path, value) {
  if (!Array.isArray(value) || value.length === 0) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path,
      "尺寸事实必须是非空的测量数组。");
    return;
  }
  if (value.length > MAX_DIMENSIONS) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path,
      "尺寸测量最多 " + MAX_DIMENSIONS + " 条。");
  }
  /** @type {Set<string>} */
  const seen = new Set();
  value.forEach((item, index) => {
    const itemPath = path + "[" + index + "]";
    checkDimension(problems, itemPath, item);
    if (isPlainObject(item) && isNonEmptyString(item.object)
        && isNonEmptyString(item.axis) && isNonEmptyString(item.unit)) {
      const key = String(item.object) + "|" + String(item.axis) + "|" + String(item.unit);
      if (seen.has(key)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, itemPath,
          "同一对象+轴向+单位只允许一条（避免自相矛盾的重复测量）。");
      } else {
        seen.add(key);
      }
    }
  });
}

/** 值是否是结构性尺寸事实（消费者用它区分「真测量」与自由文本/标量）。
 * @param {unknown} value
 * @returns {value is import("./type-contracts.js").DimensionMeasurement[]}
 */
export function isDimensionValue(value) {
  if (!Array.isArray(value) || value.length === 0) return false;
  /** @type {import("./type-contracts.js").DomainProblem[]} */
  const problems = [];
  checkDimensionList(problems, "$", value);
  return problems.length === 0;
}

/**
 * @param {import("./type-contracts.js").DomainProblem[]} problems
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
    /** @type {Record<string, unknown>} */
    const entry = /** @type {Record<string, unknown>} */ (/** @type {unknown} */ (item));
    if (!/** @type {readonly unknown[]} */ (/** @type {unknown} */ (EVIDENCE_KINDS)).includes(entry.kind)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, itemPath + ".kind", "evidence.kind 不在词表内。");
    }
    if (!isNonEmptyString(entry.ref)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, itemPath + ".ref", "evidence.ref 必须是非空字符串。");
    }
    if (entry.note !== undefined && typeof entry.note !== "string") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, itemPath + ".note", "evidence.note 只能是字符串。");
    }
    if (entry.observed_at !== undefined && !isIsoTimestamp(entry.observed_at)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, itemPath + ".observed_at", "evidence.observed_at 必须是 ISO 时间戳。");
    }
  });
}
