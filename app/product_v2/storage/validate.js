/**
 * 存储层结构判据：记录写入前必须通过这些检查，读出的记录也必须仍然合法。
 * 这里的规则只保证"存储契约"，不解释业务含义；业务校验属于后续任务。
 */

import { STORAGE_ERROR_CODES, StorageError } from "./errors.js";
import { DOCUMENT_KIND_PATTERN, PROJECT_STATES } from "./schema.js";

export const MAX_DOCUMENT_BYTES = 1_000_000;
export const MAX_POINTER_BYTES = 512;
export const MAX_NAME_LENGTH = 120;

function invalid(message, details = null) {
  throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, message, details);
}

export function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

export function isIsoTimestamp(value) {
  return typeof value === "string" && value.length >= 20 && !Number.isNaN(Date.parse(value));
}

export function isSha256Hex(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

export function isPositiveInteger(value) {
  return Number.isInteger(value) && value >= 1;
}

export function isNullableInteger(value) {
  return value === null || (Number.isInteger(value) && value >= 0);
}

export function assertProjectRecord(record) {
  if (!record || typeof record !== "object") invalid("项目记录必须是对象。");
  if (!isNonEmptyString(record.project_id)) invalid("项目记录缺少 project_id。");
  if (!isNonEmptyString(record.name)) invalid("项目记录缺少名称。");
  if (record.name.length > MAX_NAME_LENGTH) invalid("项目名称超过 " + MAX_NAME_LENGTH + " 个字符。");
  if (!isPositiveInteger(record.schema_version)) invalid("项目记录缺少 schema_version。");
  if (!isPositiveInteger(record.revision)) invalid("项目记录缺少 revision。");
  if (!PROJECT_STATES.includes(record.state)) {
    invalid("项目状态 " + JSON.stringify(record.state) + " 不在状态词表内。");
  }
  if (!isIsoTimestamp(record.created_at)) invalid("项目记录缺少合法 created_at。");
  if (!isIsoTimestamp(record.updated_at)) invalid("项目记录缺少合法 updated_at。");
  return record;
}

export function assertDocumentRecord(record) {
  if (!record || typeof record !== "object") invalid("文档记录必须是对象。");
  if (!isNonEmptyString(record.document_key)) invalid("文档记录缺少 document_key。");
  if (!isNonEmptyString(record.project_id)) invalid("文档记录缺少 project_id。");
  if (typeof record.kind !== "string" || !DOCUMENT_KIND_PATTERN.test(record.kind)) {
    invalid("文档 kind " + JSON.stringify(record.kind) + " 不符合格式约束。");
  }
  if (!isNonEmptyString(record.document_id)) invalid("文档记录缺少 document_id。");
  if (!isPositiveInteger(record.version)) invalid("文档记录缺少 version。");
  if (!isPositiveInteger(record.schema_version)) invalid("文档记录缺少 schema_version。");
  if (!isIsoTimestamp(record.created_at) || !isIsoTimestamp(record.updated_at)) {
    invalid("文档记录缺少合法时间戳。");
  }
  assertJsonSafePayload(record.payload, { label: "文档 payload" });
  return record;
}

export function assertAssetRecord(record, { requireBlob = true } = {}) {
  if (!record || typeof record !== "object") invalid("资产记录必须是对象。");
  if (!isNonEmptyString(record.asset_key)) invalid("资产记录缺少 asset_key。");
  if (!isNonEmptyString(record.project_id)) invalid("资产记录缺少 project_id。");
  if (!isSha256Hex(record.sha256)) invalid("资产记录缺少合法 sha256。");
  if (!isNonEmptyString(record.media_type)) invalid("资产记录缺少 media_type。");
  if (!Number.isInteger(record.byte_size) || record.byte_size < 0) invalid("资产记录 byte_size 非法。");
  if (!isIsoTimestamp(record.created_at)) invalid("资产记录缺少合法 created_at。");
  if (!isNullableInteger(record.width) || !isNullableInteger(record.height)) {
    invalid("资产记录 width/height 必须是 null 或非负整数。");
  }
  if (record.role !== null && typeof record.role !== "string") {
    invalid("资产记录 role 必须是 null 或字符串。");
  }
  if (requireBlob && !(record.blob instanceof Blob)) invalid("资产记录缺少 Blob。");
  return record;
}

/** localStorage 指针只允许两个字段；多一个字段就是把业务状态偷偷塞进了 localStorage。 */
export function assertPointerShape(pointer) {
  if (!pointer || typeof pointer !== "object" || Array.isArray(pointer)) return false;
  const keys = Object.keys(pointer).sort();
  if (keys.length !== 2 || keys[0] !== "project_id" || keys[1] !== "updated_at") return false;
  return isNonEmptyString(pointer.project_id) && isIsoTimestamp(pointer.updated_at);
}

/**
 * payload 必须是可 JSON 往返的纯数据：图片、Blob、函数、undefined、循环引用
 * 都要在写入前被拒绝，否则 IndexedDB 里会出现无法序列化进项目包的记录。
 */
export function assertJsonSafePayload(payload, { label = "payload", maxBytes = MAX_DOCUMENT_BYTES } = {}) {
  let text;
  try {
    text = JSON.stringify(payload);
  } catch (error) {
    invalid(label + " 不是可 JSON 序列化的数据：" + error.message);
  }
  if (text === undefined) invalid(label + " 不能是 undefined。");
  if (text.length > maxBytes) {
    invalid(label + " 超过 " + maxBytes + " 字节上限；图片必须存 assets，不能进 JSON 文档。", {
      bytes: text.length,
      max_bytes: maxBytes,
    });
  }
  const stack = [[label, payload]];
  while (stack.length) {
    const entry = stack.pop();
    const path = entry[0];
    const value = entry[1];
    if (value === null) continue;
    const type = typeof value;
    if (type === "string" || type === "number" || type === "boolean") continue;
    if (type === "function" || type === "undefined" || type === "symbol" || type === "bigint") {
      invalid(label + " 在 " + path + " 含 " + type + "，不能写入文档仓。");
    }
    if (Array.isArray(value)) {
      value.forEach(function (item, index) { stack.push([path + "[" + index + "]", item]); });
      continue;
    }
    if (type === "object") {
      if (value instanceof Blob || value instanceof Date || value instanceof ArrayBuffer) {
        invalid(label + " 在 " + path + " 含非 JSON 对象（"
          + (value.constructor ? value.constructor.name : "unknown") + "），不能写入文档仓。");
      }
      for (const key of Object.keys(value)) {
        stack.push([path + "." + key, value[key]]);
      }
      continue;
    }
    invalid(label + " 在 " + path + " 含不支持的类型 " + type + "。");
  }
  return payload;
}
