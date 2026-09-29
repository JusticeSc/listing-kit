/**
 * 浏览器项目仓库：Product V2 里"用户的项目"的唯一读写入口。
 *
 * 三类数据分工：
 * - projects：项目身份与状态（不含商品内容、不含图片）
 * - documents：版本化 JSON，append-only；expectedVersion 不符时拒绝写入，历史不覆盖
 * - assets：内容寻址 Blob，同项目同样字节只存一份；跨项目互不可见
 *
 * 每个写方法都在单个 IndexedDB 事务里完成"读取—检查—写入"，
 * 因此同一浏览器的两个标签页并发写也不会互相覆盖或写出半个结果。
 */

import { STORAGE_ERROR_CODES, StorageError, toStorageError } from "./errors.js";
import { nowIso, randomId, requestToPromise, sha256Hex, withTransaction } from "./db.js";
import { PROJECT_STATES, RECORD_SCHEMA_VERSION } from "./schema.js";
import {
  assertAssetRecord,
  assertDocumentRecord,
  assertJsonSafePayload,
  assertProjectRecord,
  isNonEmptyString,
  MAX_NAME_LENGTH,
} from "./validate.js";
import { readPointer, removePointer, writePointer } from "./pointer.js";

export function assetKeyOf(projectId, sha256) {
  return projectId + ":" + sha256;
}

export function documentKeyOf(projectId, kind, documentId, version) {
  return projectId + ":" + kind + ":" + documentId + ":" + version;
}

function requireId(value, label) {
  if (!isNonEmptyString(value)) {
    throw new StorageError(STORAGE_ERROR_CODES.INVALID_ARGUMENT, label + " 必须是非空字符串。");
  }
  return value;
}

function normalizeName(value) {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text) {
    throw new StorageError(STORAGE_ERROR_CODES.INVALID_ARGUMENT, "项目名称不能为空。");
  }
  if (text.length > MAX_NAME_LENGTH) {
    throw new StorageError(
      STORAGE_ERROR_CODES.INVALID_ARGUMENT,
      "项目名称超过 " + MAX_NAME_LENGTH + " 个字符。",
    );
  }
  return text;
}

function requireRevision(record, expectedRevision, label) {
  if (expectedRevision === undefined || expectedRevision === null) return;
  if (Number(expectedRevision) !== record.revision) {
    throw new StorageError(
      STORAGE_ERROR_CODES.REVISION_CONFLICT,
      label + " 已被其他操作修改：期望 revision=" + expectedRevision
        + "，当前是 " + record.revision + "。",
      { expected: Number(expectedRevision), actual: record.revision },
    );
  }
}

export function createRepository({
  db,
  storage = globalThis.localStorage || null,
  now = nowIso,
  newId = randomId,
  digest = sha256Hex,
} = {}) {
  if (!db) {
    throw new StorageError(STORAGE_ERROR_CODES.INVALID_ARGUMENT, "createRepository 需要已打开的数据库连接。");
  }

  async function createProject({ name, state = "EMPTY", projectId = null } = {}) {
    const trimmed = normalizeName(name);
    if (!PROJECT_STATES.includes(state)) {
      throw new StorageError(STORAGE_ERROR_CODES.INVALID_ARGUMENT, "项目状态 " + state + " 不在状态词表内。");
    }
    const timestamp = now();
    const record = {
      project_id: projectId ? requireId(projectId, "project_id") : newId(),
      schema_version: RECORD_SCHEMA_VERSION,
      name: trimmed,
      state,
      revision: 1,
      created_at: timestamp,
      updated_at: timestamp,
    };
    assertProjectRecord(record);
    return withTransaction(db, ["projects"], "readwrite", async (tx) => {
      const store = tx.objectStore("projects");
      const existing = await requestToPromise(store.get(record.project_id));
      if (existing) {
        throw new StorageError(
          STORAGE_ERROR_CODES.DUPLICATE_RECORD, "项目 " + record.project_id + " 已存在。");
      }
      await requestToPromise(store.add(record));
      return record;
    });
  }

  async function getProject(projectId) {
    requireId(projectId, "project_id");
    return withTransaction(db, ["projects"], "readonly",
      (tx) => requestToPromise(tx.objectStore("projects").get(projectId)));
  }

  async function listProjects() {
    const all = await withTransaction(db, ["projects"], "readonly",
      (tx) => requestToPromise(tx.objectStore("projects").getAll()));
    return all.sort((left, right) => {
      if (left.updated_at === right.updated_at) return left.project_id.localeCompare(right.project_id);
      return right.updated_at.localeCompare(left.updated_at);
    });
  }

  async function renameProject(projectId, name, { expectedRevision = null } = {}) {
    requireId(projectId, "project_id");
    const trimmed = normalizeName(name);
    return withTransaction(db, ["projects"], "readwrite", async (tx) => {
      const store = tx.objectStore("projects");
      const record = await requestToPromise(store.get(projectId));
      if (!record) {
        throw new StorageError(STORAGE_ERROR_CODES.NOT_FOUND, "项目 " + projectId + " 不存在。");
      }
      requireRevision(record, expectedRevision, "项目");
      const updated = { ...record, name: trimmed, revision: record.revision + 1, updated_at: now() };
      assertProjectRecord(updated);
      await requestToPromise(store.put(updated));
      return updated;
    });
  }

  async function updateProjectState(projectId, state, { expectedRevision = null } = {}) {
    requireId(projectId, "project_id");
    if (!PROJECT_STATES.includes(state)) {
      throw new StorageError(STORAGE_ERROR_CODES.INVALID_ARGUMENT, "项目状态 " + state + " 不在状态词表内。");
    }
    return withTransaction(db, ["projects"], "readwrite", async (tx) => {
      const store = tx.objectStore("projects");
      const record = await requestToPromise(store.get(projectId));
      if (!record) {
        throw new StorageError(STORAGE_ERROR_CODES.NOT_FOUND, "项目 " + projectId + " 不存在。");
      }
      requireRevision(record, expectedRevision, "项目");
      const updated = { ...record, state, revision: record.revision + 1, updated_at: now() };
      assertProjectRecord(updated);
      await requestToPromise(store.put(updated));
      return updated;
    });
  }

  async function deleteProject(projectId) {
    requireId(projectId, "project_id");
    await withTransaction(db, ["projects", "assets", "documents"], "readwrite", async (tx) => {
      const projects = tx.objectStore("projects");
      const record = await requestToPromise(projects.get(projectId));
      if (!record) {
        throw new StorageError(STORAGE_ERROR_CODES.NOT_FOUND, "项目 " + projectId + " 不存在。");
      }
      await requestToPromise(projects.delete(projectId));
      const assets = tx.objectStore("assets");
      const assetKeys = await requestToPromise(
        assets.index("by_project_id").getAllKeys(IDBKeyRange.only(projectId)));
      for (const key of assetKeys) {
        await requestToPromise(assets.delete(key));
      }
      const documents = tx.objectStore("documents");
      const documentKeys = await requestToPromise(
        documents.index("by_project_kind")
          .getAllKeys(IDBKeyRange.bound([projectId], [projectId, []])));
      for (const key of documentKeys) {
        await requestToPromise(documents.delete(key));
      }
      return true;
    });
    const pointer = readPointer(storage);
    if (pointer && pointer.project_id === projectId) {
      removePointer(storage);
    }
    return true;
  }

  async function saveDocument(projectId, {
    kind,
    documentId,
    payload,
    expectedVersion = null,
    schemaVersion = RECORD_SCHEMA_VERSION,
  } = {}) {
    requireId(projectId, "project_id");
    requireId(kind, "kind");
    requireId(documentId, "documentId");
    assertJsonSafePayload(payload, { label: "文档 payload" });
    return withTransaction(db, ["projects", "documents"], "readwrite", async (tx) => {
      const project = await requestToPromise(tx.objectStore("projects").get(projectId));
      if (!project) {
        throw new StorageError(STORAGE_ERROR_CODES.NOT_FOUND, "项目 " + projectId + " 不存在。");
      }
      const store = tx.objectStore("documents");
      const history = await requestToPromise(
        store.index("by_project_document").getAll(IDBKeyRange.only([projectId, kind, documentId])));
      const currentVersion = history.reduce((max, item) => Math.max(max, item.version), 0);
      if (expectedVersion !== null && expectedVersion !== undefined
          && Number(expectedVersion) !== currentVersion) {
        throw new StorageError(
          STORAGE_ERROR_CODES.REVISION_CONFLICT,
          "文档 " + kind + "/" + documentId + " 期望 version=" + expectedVersion
            + "，当前是 " + currentVersion + "。",
          { expected: Number(expectedVersion), actual: currentVersion },
        );
      }
      const timestamp = now();
      const record = {
        document_key: documentKeyOf(projectId, kind, documentId, currentVersion + 1),
        project_id: projectId,
        kind,
        document_id: documentId,
        version: currentVersion + 1,
        schema_version: schemaVersion,
        payload: structuredClone(payload),
        created_at: timestamp,
        updated_at: timestamp,
      };
      assertDocumentRecord(record);
      await requestToPromise(store.add(record));
      return record;
    });
  }

  async function getDocument(projectId, kind, documentId, version) {
    requireId(projectId, "project_id");
    requireId(kind, "kind");
    requireId(documentId, "documentId");
    if (!Number.isInteger(version) || version < 1) {
      throw new StorageError(STORAGE_ERROR_CODES.INVALID_ARGUMENT, "version 必须是正整数。");
    }
    return withTransaction(db, ["documents"], "readonly",
      (tx) => requestToPromise(tx.objectStore("documents").get(
        documentKeyOf(projectId, kind, documentId, version))));
  }

  async function listDocumentVersions(projectId, kind, documentId) {
    requireId(projectId, "project_id");
    requireId(kind, "kind");
    requireId(documentId, "documentId");
    const history = await withTransaction(db, ["documents"], "readonly",
      (tx) => requestToPromise(tx.objectStore("documents").index("by_project_document")
        .getAll(IDBKeyRange.only([projectId, kind, documentId]))));
    return history.sort((left, right) => right.version - left.version);
  }

  async function getLatestDocument(projectId, kind, documentId) {
    const history = await listDocumentVersions(projectId, kind, documentId);
    return history.length ? history[0] : null;
  }

  async function listLatestDocuments(projectId, kind) {
    requireId(projectId, "project_id");
    requireId(kind, "kind");
    const all = await withTransaction(db, ["documents"], "readonly",
      (tx) => requestToPromise(tx.objectStore("documents").index("by_project_kind")
        .getAll(IDBKeyRange.bound([projectId], [projectId, []]))));
    const latest = new Map();
    for (const record of all) {
      const current = latest.get(record.document_id);
      if (!current || record.version > current.version) latest.set(record.document_id, record);
    }
    return [...latest.values()].sort((left, right) => left.document_id.localeCompare(right.document_id));
  }

  async function putAsset(projectId, {
    bytes = null,
    blob = null,
    mediaType = "",
    originalName = "",
    role = null,
    width = null,
    height = null,
  } = {}) {
    requireId(projectId, "project_id");
    let source = blob;
    if (blob && !(blob instanceof Blob)) {
      throw new StorageError(STORAGE_ERROR_CODES.INVALID_ARGUMENT, "blob 必须是 Blob。");
    }
    if (!source) {
      if (!bytes) {
        throw new StorageError(STORAGE_ERROR_CODES.INVALID_ARGUMENT, "putAsset 需要 bytes 或 blob。");
      }
      const view = bytes instanceof ArrayBuffer ? new Uint8Array(bytes) : bytes;
      source = new Blob([view], { type: mediaType || "application/octet-stream" });
    }
    const buffer = await source.arrayBuffer();
    const sha = await digest(buffer);
    const record = {
      asset_key: assetKeyOf(projectId, sha),
      project_id: projectId,
      sha256: sha,
      media_type: mediaType || source.type || "application/octet-stream",
      byte_size: buffer.byteLength,
      original_name: typeof originalName === "string" ? originalName : "",
      role: role === null ? null : String(role),
      width: width === null ? null : Number(width),
      height: height === null ? null : Number(height),
      schema_version: RECORD_SCHEMA_VERSION,
      created_at: now(),
      blob: source,
    };
    assertAssetRecord(record);
    return withTransaction(db, ["projects", "assets"], "readwrite", async (tx) => {
      const project = await requestToPromise(tx.objectStore("projects").get(projectId));
      if (!project) {
        throw new StorageError(STORAGE_ERROR_CODES.NOT_FOUND, "项目 " + projectId + " 不存在。");
      }
      const store = tx.objectStore("assets");
      const existing = await requestToPromise(store.get(record.asset_key));
      if (existing) return existing;
      await requestToPromise(store.add(record));
      return record;
    });
  }

  async function getAsset(projectId, sha256) {
    requireId(projectId, "project_id");
    requireId(sha256, "sha256");
    return withTransaction(db, ["assets"], "readonly",
      (tx) => requestToPromise(tx.objectStore("assets").get(assetKeyOf(projectId, sha256))));
  }

  async function listAssets(projectId) {
    requireId(projectId, "project_id");
    return withTransaction(db, ["assets"], "readonly",
      (tx) => requestToPromise(tx.objectStore("assets").index("by_project_id")
        .getAll(IDBKeyRange.only(projectId))));
  }

  async function deleteAsset(projectId, sha256) {
    requireId(projectId, "project_id");
    requireId(sha256, "sha256");
    return withTransaction(db, ["assets"], "readwrite", async (tx) => {
      const store = tx.objectStore("assets");
      const key = assetKeyOf(projectId, sha256);
      const existing = await requestToPromise(store.get(key));
      if (!existing) return false;
      await requestToPromise(store.delete(key));
      return true;
    });
  }

  async function setCurrentProject(projectId) {
    const project = await getProject(projectId);
    if (!project) {
      throw new StorageError(STORAGE_ERROR_CODES.NOT_FOUND, "项目 " + projectId + " 不存在。");
    }
    const written = writePointer({ project_id: project.project_id, updated_at: project.updated_at }, storage);
    if (!written) {
      throw new StorageError(
        STORAGE_ERROR_CODES.UNSUPPORTED_BROWSER, "当前浏览器无法写入 localStorage 指针。");
    }
    return { project_id: project.project_id, updated_at: project.updated_at };
  }

  async function getCurrentProject() {
    const pointer = readPointer(storage);
    if (!pointer) return null;
    const project = await getProject(pointer.project_id);
    if (!project) {
      removePointer(storage);
      return null;
    }
    return project;
  }

  function clearCurrentProject() {
    removePointer(storage);
  }

  return {
    projects: {
      create: createProject,
      get: getProject,
      list: listProjects,
      rename: renameProject,
      setState: updateProjectState,
      remove: deleteProject,
    },
    documents: {
      save: saveDocument,
      get: getDocument,
      listVersions: listDocumentVersions,
      getLatest: getLatestDocument,
      listLatest: listLatestDocuments,
    },
    assets: {
      put: putAsset,
      get: getAsset,
      list: listAssets,
      remove: deleteAsset,
    },
    pointer: {
      set: setCurrentProject,
      get: getCurrentProject,
      clear: clearCurrentProject,
    },
  };
}
