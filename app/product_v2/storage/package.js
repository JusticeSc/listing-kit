/**
 * 项目包（完整历史 ZIP）的构建与解析。
 *
 * 包内结构（格式 2）：
 *   manifest.json          项目身份 + 文档元数据 + 资产元数据 + 完整性计数（唯一来源）
 *   documents/0000.json ... 每份文档版本一个自描述记录
 *                           {schema_version, kind, document_id, version, payload}
 *   assets/<sha256>         原始资产字节，路径即内容哈希
 *
 * 仅接受当前格式：旧格式明确拒绝，不猜测或迁移缺失的执行身份。
 *
 * 解析时逐项校验：格式与版本、字段结构、文档载荷可 JSON 往返、资产 sha256 与字节数。
 * 任何一项不符都中止导入（调用方先 staging 后单事务写入，不会留下半个项目）。
 */

import { STORAGE_ERROR_CODES, StorageError } from "./errors.js";
import { buildZip, readZip } from "./zip.js";
import { sha256Hex } from "./db.js";
import { PROJECT_STATES, DOCUMENT_KIND_PATTERN, RECORD_SCHEMA_VERSION } from "./schema.js";
import { assertPayloadSchemaSupported } from "./package-schema.js";
import {
  assertJsonSafePayload,
  isIsoTimestamp,
  isNonNullableInteger,
  isNonEmptyString,
  isPositiveInteger,
  isSha256Hex,
} from "./validate.js";

export const PACKAGE_FORMAT = "amz-listing-kit-project";
export const PACKAGE_FORMAT_VERSION = 2;
export const PACKAGE_FORMAT_VERSION_MIN_SUPPORTED = PACKAGE_FORMAT_VERSION;

/** 项目包内资产字节（sha256 与内容逐字对应）。@typedef {{sha256:string, media_type:string, original_name:string, role:string|null, width:number|null, height:number|null, schema_version:number, created_at?:string, bytes:Uint8Array}} PackageAsset */

/** 包内文档记录（created_at/updated_at 可能缺省，导入时补 now）。payload 是导入边界：只做过 JSON 安全性证明，业务形状由消费方收窄。@typedef {{kind:string, document_id:string, version:number, schema_version:number, created_at?:string, updated_at?:string, payload:import("./validate.js").JsonValue}} PackageDocument */

/** 项目包构建输入。@typedef {{project:import("./validate.js").StoredProjectRecord, documents:ReadonlyArray<import("./validate.js").StoredDocumentRecord>, assets:ReadonlyArray<PackageAsset>, exportedAt?:string}} BuildPackageInput */

/** manifest.json 中单条文档清单。@typedef {{path:string, kind:string, document_id:string, version:number, schema_version:number, created_at?:string, updated_at?:string}} ManifestDocument */

/** manifest.json 中单条资产清单。@typedef {{path:string, sha256:string, media_type:string, byte_size?:number, original_name?:string, role?:string|null, width?:number|null, height?:number|null, schema_version?:number, created_at?:string}} ManifestAsset */

/** manifest.json 完整性计数（格式 2 起）。@typedef {{documents:number, assets:number, document_bytes?:number, asset_bytes?:number}} ManifestIntegrity */

/** manifest.json 顶层结构（只反映运行时实际字段；format/format_version 恒存在）。@typedef {{format:string, format_version:number, exported_at?:string, record_schema_version?:number, project:{project_id:string, name:string, state:string, revision:number, schema_version:number, created_at:string, updated_at:string}, documents?:ManifestDocument[], assets?:ManifestAsset[], integrity?:ManifestIntegrity}} PackageManifest */

const TEXT_ENCODER = new TextEncoder();
const TEXT_DECODER = new TextDecoder();

/** @param {unknown} value @returns {Uint8Array} */
function jsonBytes(value) {
  return TEXT_ENCODER.encode(JSON.stringify(value));
}

/**
 * @param {Uint8Array} bytes
 * @param {string} label
 * @returns {unknown} 未验证 JSON——调用方必须逐字段断言
 */
function parseJson(bytes, label) {
  try {
    return JSON.parse(TEXT_DECODER.decode(bytes));
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    throw new StorageError(
      STORAGE_ERROR_CODES.PACKAGE_INVALID, label + " 不是合法 JSON：" + reason);
  }
}

/** @param {number} index @returns {string} */
function documentPath(index) {
  return "documents/" + String(index).padStart(4, "0") + ".json";
}

/** @param {string} sha256 @returns {string} */
function assetPath(sha256) {
  return "assets/" + sha256;
}

/**
 * 格式 2 的记录文件：自描述身份 + payload（解析时与清单逐字比对）。
 * @param {import("./validate.js").StoredDocumentRecord} record
 * @returns {Uint8Array}
 */
function documentRecordBytes(record) {
  return jsonBytes({
    schema_version: record.schema_version || RECORD_SCHEMA_VERSION,
    kind: record.kind,
    document_id: record.document_id,
    version: record.version,
    payload: record.payload,
  });
}

/**
 * 从已验证的存储记录构建完整项目包（ZIP 字节 + manifest）。
 * @param {BuildPackageInput} input
 * @returns {{bytes:Uint8Array, manifest:PackageManifest}}
 */
export function buildProjectPackage({ project, documents, assets, exportedAt = new Date().toISOString() }) {
  const sortedDocuments = [...documents].sort((left, right) => {
    if (left.kind !== right.kind) return left.kind.localeCompare(right.kind);
    if (left.document_id !== right.document_id) return left.document_id.localeCompare(right.document_id);
    return left.version - right.version;
  });
  const sortedAssets = [...assets].sort((left, right) => left.sha256.localeCompare(right.sha256));
  const documentBytes = sortedDocuments.map((record) => documentRecordBytes(record));

  const manifest = {
    format: PACKAGE_FORMAT,
    format_version: PACKAGE_FORMAT_VERSION,
    exported_at: exportedAt,
    record_schema_version: RECORD_SCHEMA_VERSION,
    project: {
      project_id: project.project_id,
      name: project.name,
      state: project.state,
      revision: project.revision,
      schema_version: project.schema_version,
      created_at: project.created_at,
      updated_at: project.updated_at,
    },
    documents: sortedDocuments.map((record, index) => ({
      path: documentPath(index),
      kind: record.kind,
      document_id: record.document_id,
      version: record.version,
      schema_version: record.schema_version,
      created_at: record.created_at,
      updated_at: record.updated_at,
    })),
    assets: sortedAssets.map((record) => ({
      path: assetPath(record.sha256),
      sha256: record.sha256,
      media_type: record.media_type,
      byte_size: record.byte_size,
      original_name: record.original_name,
      role: record.role,
      width: record.width,
      height: record.height,
      schema_version: record.schema_version || RECORD_SCHEMA_VERSION,
      created_at: record.created_at,
    })),
    integrity: {
      documents: sortedDocuments.length,
      assets: sortedAssets.length,
      document_bytes: documentBytes.reduce((sum, bytes) => sum + bytes.length, 0),
      asset_bytes: sortedAssets.reduce((sum, record) => sum + record.bytes.length, 0),
    },
  };

  const entries = [{ path: "manifest.json", bytes: jsonBytes(manifest) }];
  sortedDocuments.forEach((record, index) => {
    entries.push({ path: documentPath(index), bytes: documentBytes[index] });
  });
  for (const record of sortedAssets) {
    entries.push({ path: assetPath(record.sha256), bytes: record.bytes });
  }
  return { bytes: buildZip(entries), manifest };
}

/**
 * 解析并完整校验项目包字节：清单结构、逐条身份、当前 schema、资产哈希。
 * 未通过任一步都抛 StorageError；绝不返回半验证的包。
 * @param {Uint8Array} bytes
 * @returns {Promise<{manifest:PackageManifest, project:PackageManifest["project"], documents:PackageDocument[], assets:PackageAsset[]}>}
 */
export async function parseProjectPackage(bytes) {
  const entries = await readZip(bytes);
  const files = new Map(entries.map((entry) => [entry.path, entry.bytes]));
  const manifestBytes = files.get("manifest.json");
  if (!manifestBytes) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "项目包缺少 manifest.json。");
  }
  const manifest = /** @type {Record<string, unknown>} */ (parseJson(manifestBytes, "manifest.json"));
  if (manifest.format !== PACKAGE_FORMAT) {
    throw new StorageError(
      STORAGE_ERROR_CODES.PACKAGE_INVALID,
      "不是本产品的项目包（format=" + String(manifest.format) + "）。",
    );
  }
  if (!isPositiveInteger(manifest.format_version)) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "manifest 缺少合法的 format_version。");
  }
  if (manifest.format_version > PACKAGE_FORMAT_VERSION) {
    throw new StorageError(
      STORAGE_ERROR_CODES.PACKAGE_UNSUPPORTED_VERSION,
      "项目包版本 " + manifest.format_version + " 高于当前支持的 " + PACKAGE_FORMAT_VERSION + "。",
    );
  }
  if (manifest.format_version < PACKAGE_FORMAT_VERSION_MIN_SUPPORTED) {
    throw new StorageError(
      STORAGE_ERROR_CODES.PACKAGE_UNSUPPORTED_VERSION,
      "项目包版本 " + manifest.format_version + " 低于仍然支持的 "
        + PACKAGE_FORMAT_VERSION_MIN_SUPPORTED + "。",
    );
  }
  const project = manifest.project;
  if (!project || typeof project !== "object") {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "manifest 缺少 project。");
  }
  const projectRecord = /** @type {Record<string, unknown>} */ (project);
  if (!isNonEmptyString(projectRecord.project_id) || !isNonEmptyString(projectRecord.name)) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "project 缺少 project_id 或 name。");
  }
  if (typeof projectRecord.state !== "string" || !PROJECT_STATES.includes(projectRecord.state)) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "project.state 不在状态词表内。");
  }
  if (!isPositiveInteger(projectRecord.revision) || !isPositiveInteger(projectRecord.schema_version)) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "project 缺少 revision 或 schema_version。");
  }
  if (!isIsoTimestamp(projectRecord.created_at) || !isIsoTimestamp(projectRecord.updated_at)) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "project 缺少合法时间戳。");
  }

  /** @type {PackageDocument[]} */
  const documents = [];
  const seenDocuments = new Set();
  for (const meta of /** @type {ManifestDocument[]} */ (manifest.documents || [])) {
    if (typeof meta.kind !== "string" || !DOCUMENT_KIND_PATTERN.test(meta.kind)) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "文档 kind 非法：" + String(meta.kind));
    }
    if (!isNonEmptyString(meta.document_id) || !isPositiveInteger(meta.version)) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "文档缺少 document_id 或 version。");
    }
    const key = meta.kind + "/" + meta.document_id + "/v" + meta.version;
    if (seenDocuments.has(key)) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "项目包内文档重复：" + key);
    }
    seenDocuments.add(key);
    const payloadBytes = files.get(meta.path);
    if (!payloadBytes) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "项目包缺少文档文件：" + String(meta.path));
    }
    const parsed = /** @type {Record<string, unknown>} */ (parseJson(payloadBytes, String(meta.path)));
    const identity = [parsed.kind, parsed.document_id, parsed.version,
      parsed.schema_version || RECORD_SCHEMA_VERSION].join("|");
    const expected = [meta.kind, meta.document_id, meta.version,
      meta.schema_version || RECORD_SCHEMA_VERSION].join("|");
    if (identity !== expected) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID,
        "记录文件与清单身份不一致：" + key + "（文件=" + identity + "，清单=" + expected + "）。");
    }
    const payload = assertJsonSafePayload(parsed ? parsed.payload : undefined, { label: "文档 payload（" + key + "）" });
    documents.push({
      kind: meta.kind,
      document_id: meta.document_id,
      version: meta.version,
      schema_version: meta.schema_version || RECORD_SCHEMA_VERSION,
      created_at: meta.created_at,
      updated_at: meta.updated_at,
      payload,
    });
  }

  /** @type {PackageAsset[]} */
  const assets = [];
  const seenAssets = new Set();
  for (const meta of /** @type {ManifestAsset[]} */ (manifest.assets || [])) {
    if (!isSha256Hex(meta.sha256)) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "资产 sha256 非法：" + String(meta.sha256));
    }
    if (seenAssets.has(meta.sha256)) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "项目包内资产重复：" + meta.sha256);
    }
    seenAssets.add(meta.sha256);
    const assetBytes = files.get(meta.path);
    if (!assetBytes) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "项目包缺少资产文件：" + String(meta.path));
    }
    const digest = await sha256Hex(assetBytes);
    if (digest !== meta.sha256) {
      throw new StorageError(
        STORAGE_ERROR_CODES.PACKAGE_HASH_MISMATCH,
        "资产内容与清单不符：" + meta.sha256 + " 实际为 " + digest + "。",
      );
    }
    if (Number.isInteger(meta.byte_size) && meta.byte_size !== assetBytes.length) {
      throw new StorageError(
        STORAGE_ERROR_CODES.PACKAGE_HASH_MISMATCH,
        "资产字节数与清单不符：" + meta.sha256,
      );
    }
    if (!isNonEmptyString(meta.media_type)) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "资产缺少 media_type：" + meta.sha256);
    }
    if (!isNonNullableInteger(meta.width) || !isNonNullableInteger(meta.height)) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "资产 width/height 非法：" + meta.sha256);
    }
    assets.push({
      sha256: meta.sha256,
      media_type: meta.media_type,
      original_name: typeof meta.original_name === "string" ? meta.original_name : "",
      role: meta.role === null || typeof meta.role === "string" ? (meta.role ?? null) : null,
      width: meta.width ?? null,
      height: meta.height ?? null,
      schema_version: meta.schema_version || RECORD_SCHEMA_VERSION,
      created_at: meta.created_at,
      bytes: assetBytes,
    });
  }
  if (manifest.integrity) {
    const integrity = /** @type {ManifestIntegrity} */ (manifest.integrity);
    if (integrity.documents !== documents.length || integrity.assets !== assets.length) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID,
        "项目包完整性计数与清单不符：文档 " + documents.length + "/" + String(integrity.documents)
          + "，资产 " + assets.length + "/" + String(integrity.assets) + "。");
    }
  }

  for (const record of documents) assertPayloadSchemaSupported(record);
  return {
    manifest: /** @type {PackageManifest} */ (manifest),
    project: /** @type {PackageManifest["project"]} */ (projectRecord),
    documents,
    assets,
  };
}
