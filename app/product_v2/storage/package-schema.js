/**
 * 当前项目包载荷版本边界：解析完整后、写入事务前拒绝不支持的 schema。
 * 不迁移旧格式、不修改历史报告、不补造执行身份。
 * PAYLOAD_SCHEMA_VERSIONS 镜像 domain 常量；storage 不依赖业务执行模块。
 */

import { STORAGE_ERROR_CODES, StorageError } from "./errors.js";


/** 文档种类 → 当前 payload schema_version。 */
/** @typedef {Record<string, number>} PayloadSchemaVersionMap */


/** @type {PayloadSchemaVersionMap} */
export const PAYLOAD_SCHEMA_VERSIONS = Object.freeze({
  product_input: 1,
  semantic_analysis: 1,
  fact_slot: 1,
  product_brief: 1,
  suite_plan: 1,
  style_spec: 1,
  shot_spec: 1,
  prompt_version: 1,
  generation_confirm: 1,
  generation_attempt: 2,
  candidate: 1,
  review_report: 1,
  selection: 1,
  suite_review: 1,
  export_record: 1,
  review_acknowledgement: 1,
});

/**
 * 低于该值就必须整体拒绝的 kind（V2.R4.4）：generation_attempt 自 schema 2 起要求
 * 冻结执行身份；旧 schema 1 记录不做 legacy 映射（计划 §2.3），导出的旧包按精确条目拒绝。
 */
/** @type {PayloadSchemaVersionMap} */
export const MIN_PAYLOAD_SCHEMA_VERSIONS = Object.freeze({
  generation_attempt: 2,
});

/**
 * @param {{kind:unknown, document_id:unknown, version:unknown}} record
 * @returns {string}
 */
export function entryLabel(record) {
  return String(record.kind) + "/" + String(record.document_id) + "/v" + String(record.version);
}

/** 拒绝不支持的载荷版本；Attempt 必须显式声明当前身份 schema。 */
/**
 * @param {{kind:string, document_id:string, version:number, payload:unknown}} record
 * @returns {void}
 */
export function assertPayloadSchemaSupported(record) {
  const max = PAYLOAD_SCHEMA_VERSIONS[record.kind];
  if (max === undefined) return;
  const min = MIN_PAYLOAD_SCHEMA_VERSIONS[record.kind];
  const fields = record.payload && typeof record.payload === "object"
    ? /** @type {Record<string, unknown>} */ (record.payload) : {};
  const declared = fields.schema_version;
  if (typeof declared !== "number" || !Number.isInteger(declared)) {
    if (min !== undefined) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_UNSUPPORTED_VERSION,
        "无法导入：文档 " + entryLabel(record) + " 缺少当前 payload schema_version；不补造执行身份。");
    }
    return;
  }
  if (declared > max) {
    throw new StorageError(
      STORAGE_ERROR_CODES.PACKAGE_UNSUPPORTED_VERSION,
      "无法导入：文档 " + entryLabel(record) + " 声明的 payload schema_version=" + declared
        + " 高于当前支持的 " + max + "；请用较新版本打开或先导出该记录。",
    );
  }
  if (min !== undefined && declared < min) {
    throw new StorageError(
      STORAGE_ERROR_CODES.PACKAGE_UNSUPPORTED_VERSION,
      "无法导入：文档 " + entryLabel(record) + " 声明的 payload schema_version=" + declared
        + " 低于当前要求的 " + min + "（该记录缺少冻结执行身份，不做 legacy 映射、"
        + "不部分写入）；按计划 §2.3 整包拒绝。",
    );
  }
}

