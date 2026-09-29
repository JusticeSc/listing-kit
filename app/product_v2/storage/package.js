/**
 * 项目包（完整历史 ZIP）的构建与解析。
 *
 * 包内结构：
 *   manifest.json          项目身份 + 文档元数据 + 资产元数据（唯一来源）
 *   documents/0000.json ... 每份文档版本一个文件，内容为 {payload}
 *   assets/<sha256>         原始资产字节，路径即内容哈希
 *
 * 解析时逐项校验：格式与版本、字段结构、文档载荷可 JSON 往返、资产 sha256 与字节数。
 * 任何一项不符都中止导入（调用方在单事务里 staging，不会留下半个项目）。
 */

import { STORAGE_ERROR_CODES, StorageError } from "./errors.js";
import { buildZip, readZip } from "./zip.js";
import { sha256Hex } from "./db.js";
import { PROJECT_STATES, DOCUMENT_KIND_PATTERN, RECORD_SCHEMA_VERSION } from "./schema.js";
import {
  assertJsonSafePayload,
  isIsoTimestamp,
  isNonNullableInteger,
  isNonEmptyString,
  isPositiveInteger,
  isSha256Hex,
} from "./validate.js";

export const PACKAGE_FORMAT = "amz-listing-kit-project";
export const PACKAGE_FORMAT_VERSION = 1;

const TEXT_ENCODER = new TextEncoder();
const TEXT_DECODER = new TextDecoder();

function jsonBytes(value) {
  return TEXT_ENCODER.encode(JSON.stringify(value));
}

function parseJson(bytes, label) {
  try {
    return JSON.parse(TEXT_DECODER.decode(bytes));
  } catch (error) {
    throw new StorageError(
      STORAGE_ERROR_CODES.PACKAGE_INVALID, label + " 不是合法 JSON：" + error.message);
  }
}

function documentPath(index) {
  return "documents/" + String(index).padStart(4, "0") + ".json";
}

function assetPath(sha256) {
  return "assets/" + sha256;
}

export function buildProjectPackage({ project, documents, assets, exportedAt = new Date().toISOString() }) {
  const sortedDocuments = [...documents].sort((left, right) => {
    if (left.kind !== right.kind) return left.kind.localeCompare(right.kind);
    if (left.document_id !== right.document_id) return left.document_id.localeCompare(right.document_id);
    return left.version - right.version;
  });
  const sortedAssets = [...assets].sort((left, right) => left.sha256.localeCompare(right.sha256));

  const manifest = {
    format: PACKAGE_FORMAT,
    format_version: PACKAGE_FORMAT_VERSION,
    exported_at: exportedAt,
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
  };

  const entries = [{ path: "manifest.json", bytes: jsonBytes(manifest) }];
  sortedDocuments.forEach((record, index) => {
    entries.push({ path: documentPath(index), bytes: jsonBytes({ payload: record.payload }) });
  });
  for (const record of sortedAssets) {
    entries.push({ path: assetPath(record.sha256), bytes: record.bytes });
  }
  return { bytes: buildZip(entries), manifest };
}

export async function parseProjectPackage(bytes) {
  const entries = await readZip(bytes);
  const files = new Map(entries.map((entry) => [entry.path, entry.bytes]));
  const manifestBytes = files.get("manifest.json");
  if (!manifestBytes) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "项目包缺少 manifest.json。");
  }
  const manifest = parseJson(manifestBytes, "manifest.json");
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
  const project = manifest.project;
  if (!project || typeof project !== "object") {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "manifest 缺少 project。");
  }
  if (!isNonEmptyString(project.project_id) || !isNonEmptyString(project.name)) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "project 缺少 project_id 或 name。");
  }
  if (!PROJECT_STATES.includes(project.state)) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "project.state 不在状态词表内。");
  }
  if (!isPositiveInteger(project.revision) || !isPositiveInteger(project.schema_version)) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "project 缺少 revision 或 schema_version。");
  }
  if (!isIsoTimestamp(project.created_at) || !isIsoTimestamp(project.updated_at)) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "project 缺少合法时间戳。");
  }

  const documents = [];
  const seenDocuments = new Set();
  for (const meta of manifest.documents || []) {
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
    const parsed = parseJson(payloadBytes, String(meta.path));
    assertJsonSafePayload(parsed ? parsed.payload : undefined, { label: "文档 payload（" + key + "）" });
    documents.push({
      kind: meta.kind,
      document_id: meta.document_id,
      version: meta.version,
      schema_version: meta.schema_version || RECORD_SCHEMA_VERSION,
      created_at: meta.created_at,
      updated_at: meta.updated_at,
      payload: parsed.payload,
    });
  }

  const assets = [];
  const seenAssets = new Set();
  for (const meta of manifest.assets || []) {
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
  return { manifest, project, documents, assets };
}
