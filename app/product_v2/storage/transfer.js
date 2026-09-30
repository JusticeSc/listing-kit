/**
 * 项目级导入/导出：把浏览器里的完整项目（项目记录 + 全部文档版本 + 全部资产字节）
 * 变成一个 ZIP；把 ZIP 还原回一个新的或同 id 的项目。
 *
 * 导入是"先 staging 后提交"：解析与哈希校验全部在事务外完成，
 * 数据库写入放在一个 projects+documents+assets 的读写事务里；
 * 任何一步抛错都会 abort，浏览器里不会出现导入了一半的项目。
 */

import { STORAGE_ERROR_CODES, StorageError } from "./errors.js";
import { nowIso, randomId, requestToPromise, withTransaction } from "./db.js";
import { RECORD_SCHEMA_VERSION } from "./schema.js";
import { assertAssetRecord, assertDocumentRecord, assertProjectRecord } from "./validate.js";
import { assetKeyOf, documentKeyOf } from "./repository.js";
import { buildProjectPackage, parseProjectPackage } from "./package.js";

export async function exportProjectPackage(repository, projectId, { exportedAt } = {}) {
  const project = await repository.projects.get(projectId);
  if (!project) {
    throw new StorageError(STORAGE_ERROR_CODES.NOT_FOUND, "项目 " + projectId + " 不存在。");
  }
  const documents = await repository.documents.listAll(projectId);
  const storedAssets = await repository.assets.list(projectId);
  const assets = [];
  for (const record of storedAssets) {
    assets.push({
      sha256: record.sha256,
      media_type: record.media_type,
      byte_size: record.byte_size,
      original_name: record.original_name,
      role: record.role,
      width: record.width,
      height: record.height,
      schema_version: record.schema_version,
      created_at: record.created_at,
      bytes: new Uint8Array(await record.blob.arrayBuffer()),
    });
  }
  return buildProjectPackage({ project, documents, assets, exportedAt });
}

export async function importProjectPackage(db, packageBytes, { now = nowIso, newId = randomId } = {}) {
  const parsed = await parseProjectPackage(packageBytes);
  const timestamp = now();
  return withTransaction(db, ["projects", "documents", "assets"], "readwrite", async (tx) => {
    const projects = tx.objectStore("projects");
    let projectId = parsed.project.project_id;
    let idAssigned = false;
    const existing = await requestToPromise(projects.get(projectId));
    if (existing) {
      projectId = newId();
      idAssigned = true;
    }
    const project = {
      project_id: projectId,
      name: parsed.project.name,
      state: parsed.project.state,
      revision: parsed.project.revision,
      schema_version: parsed.project.schema_version,
      created_at: parsed.project.created_at,
      updated_at: parsed.project.updated_at,
    };
    assertProjectRecord(project);
    await requestToPromise(projects.add(project));

    const documents = tx.objectStore("documents");
    for (const record of parsed.documents) {
      const row = {
        document_key: documentKeyOf(projectId, record.kind, record.document_id, record.version),
        project_id: projectId,
        kind: record.kind,
        document_id: record.document_id,
        version: record.version,
        schema_version: record.schema_version || RECORD_SCHEMA_VERSION,
        payload: record.payload,
        created_at: isoTimestampOr(record.created_at, timestamp),
        updated_at: isoTimestampOr(record.updated_at, timestamp),
      };
      assertDocumentRecord(row);
      await requestToPromise(documents.add(row));
    }

    const assets = tx.objectStore("assets");
    for (const record of parsed.assets) {
      const blob = new Blob([record.bytes], { type: record.media_type });
      const row = {
        asset_key: assetKeyOf(projectId, record.sha256),
        project_id: projectId,
        sha256: record.sha256,
        media_type: record.media_type,
        byte_size: record.bytes.length,
        original_name: record.original_name,
        role: record.role,
        width: record.width,
        height: record.height,
        schema_version: record.schema_version || RECORD_SCHEMA_VERSION,
        created_at: isoTimestampOr(record.created_at, timestamp),
        blob,
      };
      assertAssetRecord(row);
      await requestToPromise(assets.add(row));
    }

    return {
      project,
      id_assigned: idAssigned,
      documents: parsed.documents.length,
      assets: parsed.assets.length,
      manifest: parsed.manifest,
      migrations_applied: parsed.migrations_applied || [],
    };
  });
}

function isoTimestampOr(value, fallback) {
  return typeof value === "string" && !Number.isNaN(Date.parse(value)) ? value : fallback;
}
