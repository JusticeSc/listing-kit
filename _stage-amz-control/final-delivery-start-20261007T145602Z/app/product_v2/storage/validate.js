/**
 * 存储层结构判据：记录写入前必须通过这些检查，读出的记录也必须仍然合法。
 * 这里的规则只保证"存储契约"，不解释业务含义；业务校验属于后续任务。
 */

import { STORAGE_ERROR_CODES, StorageError } from "./errors.js";
import { DOCUMENT_KIND_PATTERN, PROJECT_STATES } from "./schema.js";

export const MAX_DOCUMENT_BYTES = 1_000_000;
export const MAX_POINTER_BYTES = 512;
export const MAX_NAME_LENGTH = 120;

/** JSON 安全载荷的递归类型：这是 assertJsonSafePayload 能真正证明的全部。@typedef {string|number|boolean|null} JsonPrimitive */
/** @typedef {JsonPrimitive|JsonValue[]|{[key:string]:JsonValue}} JsonValue */

/**
 * projects 仓记录（断言后的存储契约形状）。
 * @typedef {{project_id:string, name:string, state:typeof PROJECT_STATES[number], revision:number, schema_version:number, created_at:string, updated_at:string}} StoredProjectRecord
 */

/**
 * documents 仓记录（append-only 历史）。
 * payload 泛型：读路径/导入路径未做业务校验，默认 JsonValue（只有 JSON 安全性证明）；
 * 已知的按 kind 保存路径以 StoredDocumentRecord<DomainDocumentPayloadByKind[T]> 实例化。
 * 业务形状收窄由 domain 校验器在消费边界完成。
 * @template [P=JsonValue]
 * @typedef {{document_key:string, project_id:string, kind:string, document_id:string, version:number, schema_version:number, payload:P, created_at:string, updated_at:string}} StoredDocumentRecord
 */

/**
 * assets 仓记录（内容寻址 Blob）。
 * @typedef {{asset_key:string, project_id:string, sha256:string, media_type:string, byte_size:number, original_name:string, role:string|null, width:number|null, height:number|null, schema_version:number, created_at:string, blob:Blob}} StoredAssetRecord
 */

/**
 * @typedef {{kind:import("../domain/type-contracts.js").DomainDocumentKind, documentId:string, version:number}} DocumentRef
 * @typedef {{actionId:string, version:number}} ActionObservationRef
 * @typedef {{sources:readonly DocumentRef[], projectionJson:string, assetSha256:readonly string[]}} ConsumptionFence
 * @typedef {{projectId:string, shotId:string, confirmation:DocumentRef, seenAction:ActionObservationRef|null, prompt:DocumentRef, pending:import("../domain/type-contracts.js").AttemptRecord, fence:ConsumptionFence}} ReserveAttemptInput
 * @typedef {{projectId:string, shotId:string, base:ActionObservationRef, via:"submit"|"query", envelope:unknown}} AppendAttemptObservationInput
 * @typedef {{project:StoredProjectRecord, documents:StoredDocumentRecord[], assets:StoredAssetRecord[]}} ProjectSnapshot
 * @typedef {{projectId:string, shotId:string, seenSelectionVersion:number, decision:import("../domain/type-contracts.js").SelectionRecord, fence:ConsumptionFence, candidate:DocumentRef|null, attempt:ActionObservationRef|null, report:DocumentRef|null}} CommitSelectionInput
 * @typedef {{projectId:string, exportDocumentId:string, payload:import("../domain/type-contracts.js").ExportRecordPayload, selections:readonly DocumentRef[], reports:readonly DocumentRef[], acknowledgements:readonly DocumentRef[], suiteReport:DocumentRef, candidates:readonly DocumentRef[], attempts:readonly ActionObservationRef[], originalPrompts:readonly DocumentRef[], fence:ConsumptionFence}} CommitDeliveryInput
 * @typedef {{projectId:string, kind:"review_report"|"suite_review", documentId:string, seenReportVersion:number, payload:import("../domain/type-contracts.js").ReviewReport|import("../domain/type-contracts.js").SuiteReviewReport, fence:ConsumptionFence}} CommitReviewInput
 */

/**
 * 浏览器项目仓库（storage/index.js 的 repository 成员）。
 * save 保留「kind → 业务 payload」的对应（写入前另有 JSON 安全性与存储契约断言）；
 * get/list 等读路径不做业务校验，payload 为 JsonValue，业务形状由消费方收窄。
 * @typedef {object} ProjectRepository
 * @property {{create:(a:{name:string,state?:string,projectId?:string|null})=>Promise<StoredProjectRecord>, get:(projectId:string)=>Promise<StoredProjectRecord|null>, list:()=>Promise<StoredProjectRecord[]>, rename:(projectId:string,name:string,a?:{expectedRevision?:number|null})=>Promise<StoredProjectRecord>, setState:(projectId:string,state:string,a?:{expectedRevision?:number|null})=>Promise<StoredProjectRecord>, remove:(projectId:string)=>Promise<boolean>, duplicate:(projectId:string,a?:{name?:string|null})=>Promise<{project:StoredProjectRecord,documents:number,assets:number}>}} projects
 * @property {{save:<T extends import("../domain/type-contracts.js").DomainDocumentKind>(projectId:string,a:{kind:T,documentId:string,payload:import("../domain/type-contracts.js").DomainDocumentPayloadByKind[T],expectedVersion?:number|null,schemaVersion?:number})=>Promise<StoredDocumentRecord<import("../domain/type-contracts.js").DomainDocumentPayloadByKind[T]>>, get:(projectId:string,kind:string,documentId:string,version:number)=>Promise<StoredDocumentRecord|null>, listVersions:(projectId:string,kind:string,documentId:string)=>Promise<StoredDocumentRecord[]>, getLatest:(projectId:string,kind:string,documentId:string)=>Promise<StoredDocumentRecord|null>, listLatest:(projectId:string,kind:string)=>Promise<StoredDocumentRecord[]>, listAll:(projectId:string)=>Promise<StoredDocumentRecord[]>}} documents
 * @property {{put:(projectId:string,a?:{bytes?:Uint8Array|ArrayBuffer|null,blob?:Blob|null,mediaType?:string,originalName?:string,role?:string|null,width?:number|null,height?:number|null})=>Promise<StoredAssetRecord>, get:(projectId:string,sha256:string)=>Promise<StoredAssetRecord|null>, list:(projectId:string)=>Promise<StoredAssetRecord[]>, remove:(projectId:string,sha256:string)=>Promise<boolean>}} assets
 * @property {{set:(projectId:string)=>Promise<{project_id:string,updated_at:string}>, get:()=>Promise<StoredProjectRecord|null>, clear:()=>void}} pointer
 * @property {(input:ReserveAttemptInput)=>Promise<StoredDocumentRecord<import("../domain/type-contracts.js").AttemptRecord>>} reserveGenerationAttempt
 * @property {(input:AppendAttemptObservationInput)=>Promise<StoredDocumentRecord<import("../domain/type-contracts.js").AttemptRecord>>} appendAttemptObservation
 * @property {(projectId:string,shotId:string,candidate:import("../domain/type-contracts.js").CandidateRecord)=>Promise<StoredDocumentRecord<import("../domain/type-contracts.js").CandidateRecord>>} saveCandidate
 * @property {(projectId:string)=>Promise<ProjectSnapshot>} readProjectSnapshot
 * @property {(input:CommitSelectionInput)=>Promise<StoredDocumentRecord<import("../domain/type-contracts.js").SelectionRecord>>} commitSelection
 * @property {(input:CommitDeliveryInput)=>Promise<StoredDocumentRecord<import("../domain/type-contracts.js").ExportRecordPayload>>} commitDeliveryRecord
 * @property {(input:CommitReviewInput)=>Promise<StoredDocumentRecord<import("../domain/type-contracts.js").ReviewReport|import("../domain/type-contracts.js").SuiteReviewReport>>} commitReviewReport
 */

/**
 * @param {string} message
 * @param {null|Record<string, unknown>} [details=null]
 * @returns {never}
 */
function invalid(message, details = null) {
  throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, message, details);
}

/** @param {unknown} value @returns {value is string} */
export function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

/** @param {unknown} value @returns {value is string} */
export function isIsoTimestamp(value) {
  return typeof value === "string" && value.length >= 20 && !Number.isNaN(Date.parse(value));
}

/** @param {unknown} value @returns {value is string} 64 位小写十六进制 */
export function isSha256Hex(value) {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

/** @param {unknown} value @returns {value is number} */
export function isPositiveInteger(value) {
  return Number.isInteger(value) && value >= 1;
}

/** @param {unknown} value @returns {value is number|null} */
export function isNullableInteger(value) {
  return value === null || (Number.isInteger(value) && value >= 0);
}

/** null / undefined / 非负整数都算合法（width、height 这类可选测量值）。 */
/** @param {unknown} value @returns {value is number|null|undefined} */
export function isNonNullableInteger(value) {
  return value === null || value === undefined || (Number.isInteger(value) && value >= 0);
}

/**
 * 存储契约断言：项目记录。通过后返回同一引用（调用方已有更精确类型时可忽略返回值）。
 * @param {unknown} record
 * @returns {{project_id:string, name:string, state:string, revision:number, schema_version:number, created_at:string, updated_at:string}}
 */
export function assertProjectRecord(record) {
  if (!record || typeof record !== "object") invalid("项目记录必须是对象。");
  const fields = /** @type {Record<string, unknown>} */ (record);
  if (!isNonEmptyString(fields.project_id)) invalid("项目记录缺少 project_id。");
  if (!isNonEmptyString(fields.name)) invalid("项目记录缺少名称。");
  if (typeof fields.name !== "string" || fields.name.length > MAX_NAME_LENGTH) invalid("项目名称超过 " + MAX_NAME_LENGTH + " 个字符。");
  if (!isPositiveInteger(fields.schema_version)) invalid("项目记录缺少 schema_version。");
  if (!isPositiveInteger(fields.revision)) invalid("项目记录缺少 revision。");
  if (typeof fields.state !== "string" || !PROJECT_STATES.includes(fields.state)) {
    invalid("项目状态 " + JSON.stringify(fields.state) + " 不在状态词表内。");
  }
  if (!isIsoTimestamp(fields.created_at)) invalid("项目记录缺少合法 created_at。");
  if (!isIsoTimestamp(fields.updated_at)) invalid("项目记录缺少合法 updated_at。");
  return /** @type {StoredProjectRecord} */ (record);
}

/**
 * 存储契约断言：文档记录。只证明存储契约 + payload 的 JSON 安全性；
 * 不证明业务 payload 形状（由 domain 校验器在消费边界收窄）。
 * @param {unknown} record
 * @returns {StoredDocumentRecord}
 */
export function assertDocumentRecord(record) {
  if (!record || typeof record !== "object") invalid("文档记录必须是对象。");
  const fields = /** @type {Record<string, unknown>} */ (record);
  if (!isNonEmptyString(fields.document_key)) invalid("文档记录缺少 document_key。");
  if (!isNonEmptyString(fields.project_id)) invalid("文档记录缺少 project_id。");
  if (typeof fields.kind !== "string" || !DOCUMENT_KIND_PATTERN.test(fields.kind)) {
    invalid("文档 kind " + JSON.stringify(fields.kind) + " 不符合格式约束。");
  }
  if (!isNonEmptyString(fields.document_id)) invalid("文档记录缺少 document_id。");
  if (!isPositiveInteger(fields.version)) invalid("文档记录缺少 version。");
  if (!isPositiveInteger(fields.schema_version)) invalid("文档记录缺少 schema_version。");
  if (!isIsoTimestamp(fields.created_at) || !isIsoTimestamp(fields.updated_at)) {
    invalid("文档记录缺少合法时间戳。");
  }
  assertJsonSafePayload(fields.payload, { label: "文档 payload" });
  return /** @type {StoredDocumentRecord} */ (record);
}

/**
 * 存储契约断言：资产记录（Blob 内容寻址）。
 * @param {unknown} record
 * @param {{requireBlob?:boolean}} [options]
 * @returns {{asset_key:string, project_id:string, sha256:string, media_type:string, byte_size:number, original_name:string, role:string|null, width:number|null, height:number|null, schema_version:number, created_at:string, blob:Blob}}
 */
export function assertAssetRecord(record, { requireBlob = true } = {}) {
  if (!record || typeof record !== "object") invalid("资产记录必须是对象。");
  const fields = /** @type {Record<string, unknown>} */ (record);
  if (!isNonEmptyString(fields.asset_key)) invalid("资产记录缺少 asset_key。");
  if (!isNonEmptyString(fields.project_id)) invalid("资产记录缺少 project_id。");
  if (!isSha256Hex(fields.sha256)) invalid("资产记录缺少合法 sha256。");
  if (!isNonEmptyString(fields.media_type)) invalid("资产记录缺少 media_type。");
  if (typeof fields.byte_size !== "number" || !Number.isInteger(fields.byte_size) || fields.byte_size < 0) {
    invalid("资产记录 byte_size 非法。");
  }
  if (!isIsoTimestamp(fields.created_at)) invalid("资产记录缺少合法 created_at。");
  if (!isNullableInteger(fields.width) || !isNullableInteger(fields.height)) {
    invalid("资产记录 width/height 必须是 null 或非负整数。");
  }
  if (fields.role !== null && typeof fields.role !== "string") {
    invalid("资产记录 role 必须是 null 或字符串。");
  }
  if (requireBlob && !(fields.blob instanceof Blob)) invalid("资产记录缺少 Blob。");
  return /** @type {StoredAssetRecord} */ (record);
}

/** localStorage 指针只允许两个字段；多一个字段就是把业务状态偷偷塞进了 localStorage。 */
/** @param {unknown} pointer @returns {pointer is {project_id:string, updated_at:string}} */
export function assertPointerShape(pointer) {
  if (!pointer || typeof pointer !== "object" || Array.isArray(pointer)) return false;
  const fields = /** @type {Record<string, unknown>} */ (pointer);
  const keys = Object.keys(fields).sort();
  if (keys.length !== 2 || keys[0] !== "project_id" || keys[1] !== "updated_at") return false;
  return isNonEmptyString(fields.project_id) && isIsoTimestamp(fields.updated_at);
}

/**
 * payload 必须是可 JSON 往返的纯数据：图片、Blob、函数、undefined、循环引用
 * 都要在写入前被拒绝，否则 IndexedDB 里会出现无法序列化进项目包的记录。
 * 只证明 JSON 安全性并返回 JsonValue 视图——不证明业务记录形状；
 * 业务形状由 domain 校验器在消费边界收窄。
 * @param {unknown} payload
 * @param {{label?:string, maxBytes?:number}} [options]
 * @returns {JsonValue}
 */
export function assertJsonSafePayload(payload, { label = "payload", maxBytes = MAX_DOCUMENT_BYTES } = {}) {
  let text;
  try {
    text = JSON.stringify(payload);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    invalid(label + " 不是可 JSON 序列化的数据：" + reason);
  }
  if (text === undefined) invalid(label + " 不能是 undefined。");
  if (text.length > maxBytes) {
    invalid(label + " 超过 " + maxBytes + " 字节上限；图片必须存 assets，不能进 JSON 文档。", {
      bytes: text.length,
      max_bytes: maxBytes,
    });
  }
  /** @type {[string, unknown][]} */
  const stack = [[label, payload]];
  while (stack.length) {
    const entry = /** @type {[string, unknown]} */ (stack.pop());
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
      const record = /** @type {Record<string, unknown>} */ (value);
      if (record instanceof Blob || record instanceof Date || record instanceof ArrayBuffer) {
        invalid(label + " 在 " + path + " 含非 JSON 对象（"
          + (record.constructor ? record.constructor.name : "unknown") + "），不能写入文档仓。");
      }
      for (const key of Object.keys(record)) {
        stack.push([path + "." + key, record[key]]);
      }
      continue;
    }
    invalid(label + " 在 " + path + " 含不支持的类型 " + type + "。");
  }
  return /** @type {JsonValue} */ (payload);
}
