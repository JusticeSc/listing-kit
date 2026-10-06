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
import {
  attemptActions, ATTEMPT_ACTIVE_STATES, checkAttemptRecord,
  canAttemptTransition, nextFromSubmitEnvelope, nextFromStatusEnvelope,
  checkConfirmationRecord, checkPromptRecord, promptStaleness, canonicalJson, isPlainObject,
  shotSignatureOf, evaluateShot, selectReferences, PLATFORM_PROFILES,
  checkCandidateRecord, candidateMatchesAttempt,
  assertSelectionRecord, reviewIsCurrent, selectionReviewFingerprint, checkReviewReport, checkSuiteReviewReport,
} from "../domain/index.js";

/** @param {string} reason @param {Record<string,unknown>} [details] @returns {never} */
function transactionConflict(reason, details = {}) {
  throw new StorageError(STORAGE_ERROR_CODES.REVISION_CONFLICT,
    "业务来源或所见版本已变化；请刷新后明确决定。", { reason, ...details });
}

/** @param {unknown} version */
function requireVersion(version) {
  if (typeof version !== "number" || !Number.isInteger(version) || version < 0) {
    throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, "所见版本必须是非负整数。");
  }
}

/** 资产保留的是项目历史，不只最新输入；取消引用不会破坏旧 Prompt/候选的恢复。
 * @param {unknown} value @param {string} sha256 @returns {boolean} */
function referencesAsset(value, sha256) {
  if (!value || typeof value !== "object") return false;
  const fields = /** @type {Record<string,unknown>} */ (value);
  for (const key in fields) {
    if (["asset_sha256", "sha256", "candidate_sha256"].includes(key) && fields[key] === sha256) return true;
    if (referencesAsset(fields[key], sha256)) return true;
  }
  return false;
}

/**
 * 资产主键：projectId + ":" + sha256。
 * @param {string} projectId
 * @param {string} sha256
 * @returns {string}
 */
export function assetKeyOf(projectId, sha256) {
  return projectId + ":" + sha256;
}

/**
 * 文档主键：projectId + ":" + kind + ":" + documentId + ":" + version。
 * @param {string} projectId
 * @param {string} kind
 * @param {string} documentId
 * @param {number} version
 * @returns {string}
 */
export function documentKeyOf(projectId, kind, documentId, version) {
  return projectId + ":" + kind + ":" + documentId + ":" + version;
}

/**
 * @param {unknown} value
 * @param {string} label
 * @returns {string}
 */
function requireId(value, label) {
  if (!isNonEmptyString(value)) {
    throw new StorageError(STORAGE_ERROR_CODES.INVALID_ARGUMENT, label + " 必须是非空字符串。");
  }
  return value;
}

// 数值 version 排序独立于 document_key 的字符串表示；OCC 调用复用写事务。
/**
 * @param {IDBObjectStore} store
 * @param {string} projectId
 * @param {string} kind
 * @param {string} documentId
 * @returns {Promise<import("./validate.js").StoredDocumentRecord|null>}
 */
async function readDocumentHead(store, projectId, kind, documentId) {
  const range = IDBKeyRange.bound(
    [projectId, kind, documentId, 1], [projectId, kind, documentId, Infinity]);
  const cursor = await requestToPromise(
    store.index("by_project_document_version").openCursor(range, "prev"));
  return cursor ? /** @type {import("./validate.js").StoredDocumentRecord} */ (cursor.value) : null;
}

/**
 * @param {unknown} value
 * @returns {string}
 */
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

/**
 * @param {{revision:number}} record
 * @param {number|null} expectedRevision
 * @param {string} label
 * @returns {void}
 */
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

/**
 * 浏览器项目仓库工厂。
 * @typedef {{
 *   db: IDBDatabase,
 *   storage?: Storage|null,
 *   now?: () => string,
 *   newId?: () => string,
 *   digest?: (bytes: ArrayBuffer|ArrayBufferView) => Promise<string>,
 * }} RepositoryDeps
 * @param {RepositoryDeps} deps
 * @returns {import("./validate.js").ProjectRepository}
 */
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

  /**
   * @param {{name:string, state?:string, projectId?:string|null}} [args]
   * @returns {Promise<import("./validate.js").StoredProjectRecord>}
   */
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
      const existing = await requestToPromise(
        /** @type {IDBRequest<import("./validate.js").StoredProjectRecord|undefined>} */ (store.get(record.project_id)));
      if (existing) {
        throw new StorageError(
          STORAGE_ERROR_CODES.DUPLICATE_RECORD, "项目 " + record.project_id + " 已存在。");
      }
      await requestToPromise(store.add(record));
      return record;
    });
  }

  /** @param {string} projectId @returns {Promise<import("./validate.js").StoredProjectRecord|null>} */
  async function getProject(projectId) {
    requireId(projectId, "project_id");
    return withTransaction(db, ["projects"], "readonly",
      (tx) => requestToPromise(/** @type {IDBRequest<import("./validate.js").StoredProjectRecord|undefined>} */ (tx.objectStore("projects").get(projectId))))
      .then((record) => record ?? null);
  }

  /** @returns {Promise<import("./validate.js").StoredProjectRecord[]>} */
  async function listProjects() {
    const all = await withTransaction(db, ["projects"], "readonly",
      (tx) => requestToPromise(/** @type {IDBRequest<import("./validate.js").StoredProjectRecord[]>} */ (tx.objectStore("projects").getAll())));
    return all.sort((left, right) => {
      if (left.updated_at === right.updated_at) return left.project_id.localeCompare(right.project_id);
      return right.updated_at.localeCompare(left.updated_at);
    });
  }

  /**
   * @param {string} projectId
   * @param {string} name
   * @param {{expectedRevision?:number|null}} [args]
   * @returns {Promise<import("./validate.js").StoredProjectRecord>}
   */
  async function renameProject(projectId, name, { expectedRevision = null } = {}) {
    requireId(projectId, "project_id");
    const trimmed = normalizeName(name);
    return withTransaction(db, ["projects"], "readwrite", async (tx) => {
      const store = tx.objectStore("projects");
      const record = await requestToPromise(
        /** @type {IDBRequest<import("./validate.js").StoredProjectRecord|undefined>} */ (store.get(projectId)));
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

  /**
   * @param {string} projectId
   * @param {string} state
   * @param {{expectedRevision?:number|null}} [args]
   * @returns {Promise<import("./validate.js").StoredProjectRecord>}
   */
  async function updateProjectState(projectId, state, { expectedRevision = null } = {}) {
    requireId(projectId, "project_id");
    if (!PROJECT_STATES.includes(state)) {
      throw new StorageError(STORAGE_ERROR_CODES.INVALID_ARGUMENT, "项目状态 " + state + " 不在状态词表内。");
    }
    return withTransaction(db, ["projects"], "readwrite", async (tx) => {
      const store = tx.objectStore("projects");
      const record = await requestToPromise(
        /** @type {IDBRequest<import("./validate.js").StoredProjectRecord|undefined>} */ (store.get(projectId)));
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

  /** @param {string} projectId @returns {Promise<boolean>} */
  async function deleteProject(projectId) {
    requireId(projectId, "project_id");
    await withTransaction(db, ["projects", "assets", "documents"], "readwrite", async (tx) => {
      const projects = tx.objectStore("projects");
      const record = await requestToPromise(
        /** @type {IDBRequest<import("./validate.js").StoredProjectRecord|undefined>} */ (projects.get(projectId)));
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

  /**
   * 复制项目：同一事务里复制项目记录、全部文档版本与全部资产字节。
   * 新项目用新的 project_id，因此资产键与文档键全部重写；原项目一个字节都不动。
   * 复制失败时事务回滚，不产生半个副本。
   * @param {string} projectId
   * @param {{name?:string|null}} [args]
   * @returns {Promise<{project:import("./validate.js").StoredProjectRecord, documents:number, assets:number}>}
   */
  async function duplicateProject(projectId, { name = null } = {}) {
    requireId(projectId, "project_id");
    const timestamp = now();
    return withTransaction(db, ["projects", "documents", "assets"], "readwrite", async (tx) => {
      const projects = tx.objectStore("projects");
      const source = await requestToPromise(
        /** @type {IDBRequest<import("./validate.js").StoredProjectRecord|undefined>} */ (projects.get(projectId)));
      if (!source) {
        throw new StorageError(STORAGE_ERROR_CODES.NOT_FOUND, "项目 " + projectId + " 不存在。");
      }
      const copyId = newId();
      const copy = {
        ...source,
        project_id: copyId,
        name: name ? normalizeName(name) : normalizeName(source.name + "（副本）"),
        revision: 1,
        created_at: timestamp,
        updated_at: timestamp,
      };
      assertProjectRecord(copy);
      await requestToPromise(projects.add(copy));

      const documents = tx.objectStore("documents");
      const sourceDocuments = await requestToPromise(
        /** @type {IDBRequest<import("./validate.js").StoredDocumentRecord[]>} */ (documents.index("by_project_kind")
          .getAll(IDBKeyRange.bound([projectId], [projectId, []]))));
      for (const record of sourceDocuments) {
        await requestToPromise(documents.add({
          ...record,
          document_key: documentKeyOf(copyId, record.kind, record.document_id, record.version),
          project_id: copyId,
        }));
      }

      const assets = tx.objectStore("assets");
      const sourceAssets = await requestToPromise(
        /** @type {IDBRequest<import("./validate.js").StoredAssetRecord[]>} */ (assets.index("by_project_id").getAll(IDBKeyRange.only(projectId))));
      for (const record of sourceAssets) {
        await requestToPromise(assets.add({
          ...record,
          asset_key: assetKeyOf(copyId, record.sha256),
          project_id: copyId,
        }));
      }
      return {
        project: copy,
        documents: sourceDocuments.length,
        assets: sourceAssets.length,
      };
    });
  }

  /**
   * 追加新版本文档；payload 类型与 kind 的关系由 DomainDocumentPayloadByKind 保证。
   * 写入前断言存储契约与 JSON 安全性；读回路径不提供业务形状证明。
   * @template {import("../domain/type-contracts.js").DomainDocumentKind} T
   * @param {string} projectId
   * @param {{kind:T, documentId:string, payload:import("../domain/type-contracts.js").DomainDocumentPayloadByKind[T], expectedVersion?:number|null, schemaVersion?:number}} [args]
   * @returns {Promise<import("./validate.js").StoredDocumentRecord<import("../domain/type-contracts.js").DomainDocumentPayloadByKind[T]>>}
   */
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
      const project = await requestToPromise(
        /** @type {IDBRequest<import("./validate.js").StoredProjectRecord|undefined>} */ (tx.objectStore("projects").get(projectId)));
      if (!project) {
        throw new StorageError(STORAGE_ERROR_CODES.NOT_FOUND, "项目 " + projectId + " 不存在。");
      }
      const store = tx.objectStore("documents");
      const head = await readDocumentHead(store, projectId, kind, documentId);
      const currentVersion = head ? head.version : 0;
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

  /** @param {IDBTransaction} tx @param {string} projectId */
  async function requireTransactionProject(tx, projectId) {
    requireId(projectId, "project_id");
    if (!await requestToPromise(tx.objectStore("projects").get(projectId))) {
      throw new StorageError(STORAGE_ERROR_CODES.NOT_FOUND, "原项目不存在。");
    }
  }

  /** @template P @param {IDBObjectStore} store @param {string} projectId
   * @param {string} kind @param {string} documentId @param {P} payload
   * @param {number} version @returns {Promise<import("./validate.js").StoredDocumentRecord<P>>} */
  async function appendBusinessDocument(store, projectId, kind, documentId, payload, version) {
    assertJsonSafePayload(payload);
    const timestamp = now();
    const record = {
      document_key: documentKeyOf(projectId, kind, documentId, version),
      project_id: projectId, kind, document_id: documentId, version,
      schema_version: RECORD_SCHEMA_VERSION, payload: structuredClone(payload),
      created_at: timestamp, updated_at: timestamp,
    };
    assertDocumentRecord(record);
    await requestToPromise(store.add(record));
    return record;
  }

  /** @param {IDBObjectStore} store @param {string} projectId @param {string} shotId
   * @returns {Promise<import("../domain/attempt.js").AttemptObservation[]>} */
  async function readAttemptObservations(store, projectId, shotId) {
    const rows = await requestToPromise(store.index("by_project_document")
      .getAll([projectId, "generation_attempt", shotId]));
    return rows.map(row => {
      if (checkAttemptRecord(row.payload).length || !Number.isInteger(row.version) || row.version < 1) {
        throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, "原尝试链不合法。");
      }
      return { record: /** @type {import("../domain/type-contracts.js").AttemptRecord} */ (row.payload),
        version: row.version };
    });
  }

  /** @param {IDBObjectStore} store @param {string} projectId
   * @param {import("./validate.js").DocumentRef} ref */
  async function exactDocument(store, projectId, ref) {
    requireVersion(ref.version);
    if (ref.version === 0) {
      throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, "精确来源版本必须大于零。");
    }
    const row = await requestToPromise(store.get(
      documentKeyOf(projectId, ref.kind, ref.documentId, ref.version)));
    if (!row) throw new StorageError(STORAGE_ERROR_CODES.NOT_FOUND, "精确来源版本缺失。");
    return /** @type {import("./validate.js").StoredDocumentRecord} */ (row);
  }

  /** 所有当前性判据在同一事务里读头，复用 Prompt 的消费范围而不是项目 revision。
   * @param {IDBTransaction} tx @param {import("./validate.js").ReserveAttemptInput} input
   * @param {import("../domain/type-contracts.js").PromptRecord} prompt */
  async function checkGenerationSources(tx, input, prompt) {
    const { projectId, shotId, fence } = input;
    const store = tx.objectStore("documents");
    const suite = await readDocumentHead(store, projectId, "suite_plan", "suite");
    const plan = /** @type {import("../domain/type-contracts.js").SuitePlan|null} */ (suite?.payload || null);
    const shot = plan?.shots.find(item => item.shot_id === shotId);
    if (!shot) transactionConflict("shot_missing");
    const style = await readDocumentHead(store, projectId, "style_spec", "style");
    const spec = await readDocumentHead(store, projectId, "shot_spec", shotId);
    const intake = await readDocumentHead(store, projectId, "product_input", "intake");
    const product = /** @type {import("../domain/type-contracts.js").ProductInput|null} */ (intake?.payload || null);
    const references = (product?.references || []).map(item => ({ role: item.role, sha256: item.asset_sha256 }));
    const slots = [];
    for (const item of prompt.basis.brief) {
      const head = await readDocumentHead(store, projectId, "fact_slot", item.slot_id);
      const slot = /** @type {import("../domain/type-contracts.js").FactSlot|null} */ (head?.payload || null);
      if (!head || slot?.status !== "confirmed") transactionConflict("fact_changed", { slotId: item.slot_id });
      slots.push({ slot, version: head.version });
    }
    const provider = prompt.compiled.provider;
    const current = {
      briefBasis: slots.map(item => ({ slot_id: item.slot.slot_id, version: item.version })),
      shot_signature: shotSignatureOf(shot), suite_version: suite?.version || null,
      style_version: style?.version || null, shot_spec_version: spec?.version || null,
      platform: { version: PLATFORM_PROFILES.amazon_us.version }, provider,
    };
    if (promptStaleness(prompt, current).stale) transactionConflict("consumed_sources_changed");
    const context = { facts: slots.map(item => ({
      slot_id: item.slot.slot_id, status: item.slot.status, value: item.slot.value,
    })), assets: references };
    if (!evaluateShot(shot, context).satisfied) transactionConflict("shot_blocked");
    const selected = selectReferences(shot, references, { maxReferences: provider.max_reference_images });
    // 请求一致性只核对实际发送快照；消费围栏头/投影由 checkFenceHeads 在同一事务内先行核对。
    if (canonicalJson(selected) !== canonicalJson(prompt.request_snapshot.references)) {
      transactionConflict("references_changed");
    }
    for (const sha of fence.assetSha256) {
      if (!await requestToPromise(tx.objectStore("assets").get(assetKeyOf(projectId, sha)))) {
        throw new StorageError(STORAGE_ERROR_CODES.NOT_FOUND, "原参考图字节缺失。");
      }
    }
  }

  /** 跨标签授权消费的唯一线性化点；oncomplete 之前调用者不得发送 HTTP。
   * @param {import("./validate.js").ReserveAttemptInput} input */
  async function reserveGenerationAttempt(input) {
    const { projectId, shotId, pending, confirmation, prompt, seenAction } = input;
    requireId(shotId, "shot_id");
    if (seenAction !== null) {
      if (!seenAction || typeof seenAction !== "object") {
        throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, "必须明确给出所见动作或 null。");
      }
      requireId(seenAction.actionId, "action_id");
      requireVersion(seenAction.version);
      if (seenAction.version === 0) {
        throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, "所见动作必须引用正版本。");
      }
    }
    if (checkAttemptRecord(pending).length || pending.state !== "pending_submit"
        || pending.shot_id !== shotId || confirmation.kind !== "generation_confirm"
        || prompt.kind !== "prompt_version" || prompt.documentId !== shotId) {
      throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, "预约身份或精确来源不合法。");
    }
    return withTransaction(db, ["projects", "documents", "assets"], "readwrite", async tx => {
      await requireTransactionProject(tx, projectId);
      const store = tx.objectStore("documents");
      const confRow = await exactDocument(store, projectId, confirmation);
      const promptRow = await exactDocument(store, projectId, prompt);
      if (checkConfirmationRecord(confRow.payload).length || checkPromptRecord(promptRow.payload).length) {
        throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, "原授权或 Prompt 不合法。");
      }
      const conf = /** @type {import("../domain/type-contracts.js").ConfirmationRecord} */ (confRow.payload);
      const originalPrompt = /** @type {import("../domain/type-contracts.js").PromptRecord} */ (promptRow.payload);
      const authorized = conf.shots.find(item => item.shot_id === shotId);
      const authorization = pending.authorization;
      const promptHead = await readDocumentHead(store, projectId, prompt.kind, shotId);
      if (!authorized || authorized.prompt_version !== prompt.version
          || authorized.prompt_hash !== originalPrompt.hash || promptHead?.version !== prompt.version
          || pending.prompt.version !== prompt.version || pending.prompt.hash !== originalPrompt.hash
          || authorization?.document_id !== confirmation.documentId
          || authorization.version !== confirmation.version || authorization.hash !== conf.fingerprint.hash
          || canonicalJson(pending.references) !== canonicalJson(originalPrompt.request_snapshot.references)) {
        transactionConflict("authorization_mismatch");
      }
      const target = conf.fingerprint.snapshot.execution_target;
      const identity = pending.execution_identity;
      const snapshot = originalPrompt.request_snapshot;
      if (!target || !conf.fingerprint.snapshot.can_submit
          || target.provider_id !== pending.provider.provider_id || target.model_id !== pending.provider.model_id
          || target.protocol !== identity?.protocol || target.capability_version !== identity?.capability_version
          || target.credential_source !== identity?.credential_reference.source || target.sync !== (identity?.sync === true)
          || pending.parameters.size !== snapshot.size || pending.parameters.n !== snapshot.n
          || pending.parameters.prompt_extend !== snapshot.prompt_extend || pending.parameters.watermark !== snapshot.watermark) {
        transactionConflict("execution_target_mismatch");
      }
      // 同一事务内先核对消费围栏头与图片投影（checkFenceHeads），再核对
      // Prompt 请求一致性（checkGenerationSources）：两者必须分别成立。
      await checkFenceHeads(tx, projectId, input.fence, [shotId]);
      await checkGenerationSources(tx, input, originalPrompt);
      const observations = await readAttemptObservations(store, projectId, shotId);
      const actions = attemptActions(observations);
      const current = actions.at(-1) || null;
      if (actions.some(item => item.record.authorization?.document_id === confirmation.documentId
          && item.record.authorization.version === confirmation.version)) transactionConflict("authorization_consumed");
      if ((current?.record.action_id || null) !== (seenAction?.actionId || null)
          || (current?.version || 0) !== (seenAction?.version || 0)) transactionConflict("action_changed");
      const mode = conf.fingerprint.snapshot.submission_mode;
      const state = current?.record.state;
      const allowed = mode === "initial" ? !current
        : mode === "failed_retry" ? state === "failed"
        : mode === "rework" ? state === "succeeded" || state === "failed"
        : mode === "explicit_new" ? state === "unknown"
          || (state === "pending_submit" && !current?.record.task_id) : false;
      if (!allowed) transactionConflict("submission_mode_blocked");
      for (const item of actions) {
        if (!ATTEMPT_ACTIVE_STATES.includes(item.record.state)) continue;
        if (item.record.task_id) transactionConflict("active_task");
        if (item === current && mode === "explicit_new") continue;
        const later = actions.filter(next => next.reservationVersion > item.reservationVersion);
        let superseded = false;
        for (const next of later) {
          const ref = next.record.authorization;
          if (!ref) continue;
          const row = await exactDocument(store, projectId,
            { kind: "generation_confirm", documentId: ref.document_id, version: ref.version });
          const payload = /** @type {import("../domain/type-contracts.js").ConfirmationRecord} */ (row.payload);
          if (payload.fingerprint.snapshot.submission_mode === "explicit_new") superseded = true;
        }
        if (!superseded) transactionConflict("active_reservation");
      }
      if (actions.some(item => item.record.action_id === pending.action_id)) transactionConflict("action_duplicate");
      const version = observations.reduce((max, item) => Math.max(max, item.version), 0) + 1;
      return appendBusinessDocument(store, projectId, "generation_attempt", shotId, pending, version);
    });
  }

  /** @param {import("./validate.js").AppendAttemptObservationInput} input */
  async function appendAttemptObservation(input) {
    const { projectId, shotId, base, via, envelope } = input;
    requireVersion(base.version);
    if (!base.version || !["submit", "query"].includes(via)) {
      throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, "观察来源不合法。");
    }
    return withTransaction(db, ["projects", "documents"], "readwrite", async tx => {
      await requireTransactionProject(tx, projectId);
      const store = tx.objectStore("documents");
      const observations = await readAttemptObservations(store, projectId, shotId);
      const original = observations.find(item => item.version === base.version);
      const latest = attemptActions(observations).find(item => item.record.action_id === base.actionId);
      if (!original || original.record.action_id !== base.actionId || !latest) transactionConflict("observation_missing");
      const classify = via === "submit" ? nextFromSubmitEnvelope : nextFromStatusEnvelope;
      const proposed = classify(original.record, envelope, { at: now() });
      let payload = proposed.record;
      if (latest.version !== base.version) {
        if (canonicalJson(latest.record) === canonicalJson(payload)
            || !canAttemptTransition(latest.record.state, payload.state, via)) {
          return /** @type {Promise<import("./validate.js").StoredDocumentRecord<import("../domain/type-contracts.js").AttemptRecord>>} */ (
            exactDocument(store, projectId, { kind: "generation_attempt", documentId: shotId, version: latest.version }));
        }
        payload = classify(latest.record, envelope, { at: now() }).record;
      }
      if (canonicalJson(latest.record) === canonicalJson(payload)) {
        return /** @type {Promise<import("./validate.js").StoredDocumentRecord<import("../domain/type-contracts.js").AttemptRecord>>} */ (
          exactDocument(store, projectId, { kind: "generation_attempt", documentId: shotId, version: latest.version }));
      }
      const version = observations.reduce((max, item) => Math.max(max, item.version), 0) + 1;
      return appendBusinessDocument(store, projectId, "generation_attempt", shotId, payload, version);
    });
  }

  /** 候选属于原 action；较新的预约不取消旧动作的合法结果。
   * @param {string} projectId @param {string} shotId
   * @param {import("../domain/type-contracts.js").CandidateRecord} candidate */
  async function saveCandidate(projectId, shotId, candidate) {
    if (checkCandidateRecord(candidate).length || candidate.shot_id !== shotId) {
      throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, "候选身份不合法。");
    }
    return withTransaction(db, ["projects", "documents", "assets"], "readwrite", async tx => {
      await requireTransactionProject(tx, projectId);
      const store = tx.objectStore("documents");
      const attempt = attemptActions(await readAttemptObservations(store, projectId, shotId))
        .find(item => item.record.action_id === candidate.action_id);
      if (!attempt || attempt.record.state !== "succeeded" || !candidateMatchesAttempt(candidate, attempt.record)) {
        transactionConflict("candidate_attempt_mismatch");
      }
      const asset = await requestToPromise(tx.objectStore("assets").get(assetKeyOf(projectId, candidate.asset_sha256)));
      if (!asset || asset.byte_size !== candidate.byte_size) {
        throw new StorageError(STORAGE_ERROR_CODES.NOT_FOUND, "候选字节缺失或不匹配。");
      }
      const rows = await requestToPromise(store.index("by_project_document").getAll([projectId, "candidate", shotId]));
      const existing = rows.find(row => row.payload.action_id === candidate.action_id);
      if (existing) {
        if (existing.payload.asset_sha256 !== candidate.asset_sha256) transactionConflict("candidate_bytes_conflict");
        return /** @type {import("./validate.js").StoredDocumentRecord<import("../domain/type-contracts.js").CandidateRecord>} */ (existing);
      }
      const version = rows.reduce((max, row) => Math.max(max, row.version), 0) + 1;
      return appendBusinessDocument(store, projectId, "candidate", shotId, candidate, version);
    });
  }

  /** @param {IDBTransaction} tx @param {string} projectId
   * @param {import("./validate.js").ConsumptionFence} fence @param {readonly string[]|null} [shotIds] */
  async function checkFenceHeads(tx, projectId, fence, shotIds = null) {
    const store = tx.objectStore("documents");
    /** @type {unknown} */
    let projection;
    try {
      projection = JSON.parse(fence.projectionJson);
    } catch {
      throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, "消费投影必须是有效 JSON。");
    }
    if (!isPlainObject(projection) || projection.project_id !== projectId || !Array.isArray(projection.shots)) {
      transactionConflict("projection_project_changed");
    }
    /** @type {import("./validate.js").StoredDocumentRecord|null} */
    let suiteHead = null;
    for (const ref of fence.sources) {
      requireVersion(ref.version);
      const head = await readDocumentHead(store, projectId, ref.kind, ref.documentId);
      if (ref.kind === "suite_plan" && ref.documentId === "suite") suiteHead = head;
      if ((head?.version || 0) === ref.version) continue;
      // 同内容的新版本不改变领域输入；不把“保存但无修改”变成业务失效。
      const original = ref.version ? await exactDocument(store, projectId, ref) : null;
      if (ref.kind === "suite_plan" && shotIds && head && original) {
        const before = /** @type {import("../domain/type-contracts.js").SuitePlan} */ (original.payload);
        const after = /** @type {import("../domain/type-contracts.js").SuitePlan} */ (head.payload);
        if (shotIds.every(id => {
          const left = before.shots.find(shot => shot.shot_id === id);
          const right = after.shots.find(shot => shot.shot_id === id);
          return left && right && shotSignatureOf(left) === shotSignatureOf(right);
        })) continue;
      }
      if (!head || !original || canonicalJson(head.payload) !== canonicalJson(original.payload)) {
        transactionConflict("consumed_head_changed", { kind: ref.kind, documentId: ref.documentId });
      }
    }
    const plan = /** @type {import("../domain/type-contracts.js").SuitePlan|null} */ (suiteHead?.payload || null);
    for (const projected of projection.shots) {
      if (!isPlainObject(projected) || typeof projected.shot_id !== "string") {
        throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, "消费图片投影不合法。");
      }
      const shot = plan?.shots.find(item => item.shot_id === projected.shot_id);
      if (!shot || projected.shot_signature !== shotSignatureOf(shot)) {
        transactionConflict("consumed_projection_changed");
      }
    }
    for (const sha of fence.assetSha256) {
      if (!await requestToPromise(tx.objectStore("assets").get(assetKeyOf(projectId, sha)))) {
        throw new StorageError(STORAGE_ERROR_CODES.NOT_FOUND, "消费的资产已缺失。");
      }
    }
  }

  /** @param {string} projectId @returns {Promise<import("./validate.js").ProjectSnapshot>} */
  async function readProjectSnapshot(projectId) {
    requireId(projectId, "project_id");
    return withTransaction(db, ["projects", "documents", "assets"], "readonly", async tx => {
      const project = await requestToPromise(tx.objectStore("projects").get(projectId));
      if (!project) throw new StorageError(STORAGE_ERROR_CODES.NOT_FOUND, "项目不存在。");
      const documents = await requestToPromise(tx.objectStore("documents").index("by_project_kind")
        .getAll(IDBKeyRange.bound([projectId, ""], [projectId, "\uffff"])));
      const assets = await requestToPromise(tx.objectStore("assets").index("by_project_id").getAll(projectId));
      return { project: assertProjectRecord(project),
        documents: documents.map(assertDocumentRecord), assets: assets.map(assertAssetRecord) };
    });
  }

  /** @param {import("./validate.js").CommitSelectionInput} input */
  async function commitSelection(input) {
    const { projectId, shotId, decision, seenSelectionVersion, candidate, attempt, report } = input;
    requireVersion(seenSelectionVersion);
    assertSelectionRecord(decision);
    if (decision.shot_id !== shotId) throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, "采用动作归属不匹配。");
    return withTransaction(db, ["projects", "documents", "assets"], "readwrite", async tx => {
      await requireTransactionProject(tx, projectId);
      const store = tx.objectStore("documents");
      const head = await readDocumentHead(store, projectId, "selection", shotId);
      if ((head?.version || 0) !== seenSelectionVersion) transactionConflict("selection_changed");
      if (decision.action === "select") {
        if (!candidate || !attempt || !report || candidate.kind !== "candidate" || candidate.documentId !== shotId
            || report.kind !== "review_report") throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, "采用缺少原来源链。");
        const candidateRow = await exactDocument(store, projectId, candidate);
        const stored = /** @type {import("../domain/type-contracts.js").CandidateRecord} */ (candidateRow.payload);
        const observation = (await readAttemptObservations(store, projectId, shotId))
          .find(item => item.record.action_id === attempt.actionId && item.version === attempt.version);
        const reportRow = await exactDocument(store, projectId, report);
        const reportHead = await readDocumentHead(store, projectId, report.kind, report.documentId);
        const checked = /** @type {import("../domain/type-contracts.js").ReviewReport} */ (reportRow.payload);
        if (checkCandidateRecord(stored).length || !observation || observation.record.state !== "succeeded"
            || !candidateMatchesAttempt(stored, observation.record) || !reviewIsCurrent(checked, stored)
            || reportHead?.version !== report.version || decision.candidate_id !== stored.candidate_id
            || decision.candidate_sha256 !== stored.asset_sha256 || decision.candidate_version !== candidate.version
            || canonicalJson(decision.review_fingerprint) !== canonicalJson(selectionReviewFingerprint(checked))) {
          transactionConflict("selection_source_changed");
        }
        const asset = await requestToPromise(tx.objectStore("assets").get(assetKeyOf(projectId, stored.asset_sha256)));
        if (!asset || asset.byte_size !== stored.byte_size) transactionConflict("selection_asset_missing");
        await checkFenceHeads(tx, projectId, input.fence, [shotId]);
      } else if (candidate || attempt || report) {
        throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, "取消采用不能携带候选或复核来源。");
      }
      return appendBusinessDocument(store, projectId, "selection", shotId, decision, seenSelectionVersion + 1);
    });
  }

  /** @param {import("./validate.js").CommitReviewInput} input */
  async function commitReviewReport(input) {
    const { projectId, kind, documentId, seenReportVersion, payload, fence } = input;
    requireVersion(seenReportVersion);
    const problems = kind === "review_report" ? checkReviewReport(payload) : checkSuiteReviewReport(payload);
    if (!["review_report", "suite_review"].includes(kind) || problems.length) {
      throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, "复核报告不合法。");
    }
    return withTransaction(db, ["projects", "documents", "assets"], "readwrite", async tx => {
      await requireTransactionProject(tx, projectId);
      const store = tx.objectStore("documents");
      const head = await readDocumentHead(store, projectId, kind, documentId);
      if ((head?.version || 0) !== seenReportVersion) transactionConflict("review_changed");
      const scope = kind === "review_report"
        ? [/** @type {import("../domain/type-contracts.js").ReviewReport} */ (payload).shot_id] : null;
      await checkFenceHeads(tx, projectId, fence, scope);
      return appendBusinessDocument(store, projectId, kind, documentId, payload, seenReportVersion + 1);
    });
  }

  /** 构包完成后的最后围栏：不钉住新候选或编辑 Prompt，只钉住实际交付的来源。
   * @param {import("./validate.js").CommitDeliveryInput} input */
  async function commitDeliveryRecord(input) {
    const { projectId, exportDocumentId, payload } = input;
    assertJsonSafePayload(payload);
    if (payload.project_id !== projectId || !input.candidates.length
        || input.selections.length !== input.candidates.length || input.reports.length !== input.candidates.length
        || canonicalJson([...payload.included_shot_ids].sort()) !== canonicalJson(input.candidates.map(ref => ref.documentId).sort())
        || input.suiteReport.kind !== "suite_review") {
      throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, "交付缺少完整的已采用来源集合。");
    }
    return withTransaction(db, ["projects", "documents", "assets"], "readwrite", async tx => {
      await requireTransactionProject(tx, projectId);
      const store = tx.objectStore("documents");
      const existing = await readDocumentHead(store, projectId, "export_record", exportDocumentId);
      if (existing) {
        if (canonicalJson(existing.payload) !== canonicalJson(payload)) transactionConflict("export_identity_conflict");
        return /** @type {import("./validate.js").StoredDocumentRecord<import("../domain/type-contracts.js").ExportRecordPayload>} */ (existing);
      }
      await checkFenceHeads(tx, projectId, input.fence, input.candidates.map(ref => ref.documentId));
      for (const ref of [...input.selections, ...input.reports, ...input.acknowledgements, input.suiteReport]) {
        const row = await exactDocument(store, projectId, ref);
        const head = await readDocumentHead(store, projectId, ref.kind, ref.documentId);
        if (!head || canonicalJson(head.payload) !== canonicalJson(row.payload)) transactionConflict("delivery_head_changed", { kind: ref.kind });
      }
      const suite = /** @type {import("../domain/type-contracts.js").SuiteReviewReport} */ (
        (await exactDocument(store, projectId, input.suiteReport)).payload);
      if (checkSuiteReviewReport(suite).length || suite.selection_fingerprint !== payload.selection_fingerprint
          || suite.inputs_fingerprint !== payload.inputs_fingerprint) transactionConflict("delivery_suite_mismatch");
      for (const ref of input.candidates) {
        if (ref.kind !== "candidate") throw new StorageError(STORAGE_ERROR_CODES.SCHEMA_INVALID, "交付候选来源种类不合法。");
        const row = await exactDocument(store, projectId, ref);
        const candidate = /** @type {import("../domain/type-contracts.js").CandidateRecord} */ (row.payload);
        const selectedRef = input.selections.find(item => item.kind === "selection" && item.documentId === ref.documentId);
        const reportRef = input.reports.find(item => item.kind === "review_report" && item.documentId === candidate.candidate_id);
        if (!selectedRef || !reportRef) transactionConflict("delivery_selection_missing");
        const selected = assertSelectionRecord((await exactDocument(store, projectId, selectedRef)).payload);
        const report = (await exactDocument(store, projectId, reportRef)).payload;
        if (selected.action !== "select" || selected.candidate_id !== candidate.candidate_id
            || selected.candidate_sha256 !== candidate.asset_sha256 || selected.candidate_version !== ref.version
            || !reviewIsCurrent(report, candidate)) transactionConflict("delivery_selection_mismatch");
        const action = input.attempts.find(item => item.actionId === candidate.action_id);
        if (!action) transactionConflict("delivery_attempt_missing");
        const observation = (await readAttemptObservations(store, projectId, ref.documentId))
          .find(item => item.version === action.version && item.record.action_id === action.actionId);
        if (!observation || observation.record.state !== "succeeded" || !candidateMatchesAttempt(candidate, observation.record)) {
          transactionConflict("delivery_attempt_mismatch");
        }
        const promptRef = input.originalPrompts.find(item => item.kind === "prompt_version"
          && item.documentId === ref.documentId && item.version === observation.record.prompt.version);
        if (!promptRef) transactionConflict("delivery_prompt_missing");
        const original = await exactDocument(store, projectId, promptRef);
        const prompt = /** @type {import("../domain/type-contracts.js").PromptRecord} */ (original.payload);
        if (checkPromptRecord(prompt).length || prompt.hash !== observation.record.prompt.hash) transactionConflict("delivery_prompt_mismatch");
        const asset = await requestToPromise(tx.objectStore("assets").get(assetKeyOf(projectId, candidate.asset_sha256)));
        if (!asset || asset.byte_size !== candidate.byte_size) transactionConflict("delivery_asset_missing");
      }
      return appendBusinessDocument(store, projectId, "export_record", exportDocumentId, payload, 1);
    });
  }

  /**
   * @param {string} projectId
   * @param {string} kind
   * @param {string} documentId
   * @param {number} version
   * @returns {Promise<import("./validate.js").StoredDocumentRecord|null>}
   */
  async function getDocument(projectId, kind, documentId, version) {
    requireId(projectId, "project_id");
    requireId(kind, "kind");
    requireId(documentId, "documentId");
    if (!Number.isInteger(version) || version < 1) {
      throw new StorageError(STORAGE_ERROR_CODES.INVALID_ARGUMENT, "version 必须是正整数。");
    }
    return withTransaction(db, ["documents"], "readonly",
      (tx) => requestToPromise(/** @type {IDBRequest<import("./validate.js").StoredDocumentRecord|undefined>} */ (tx.objectStore("documents").get(
        documentKeyOf(projectId, kind, documentId, version)))))
      .then((record) => record ?? null);
  }

  /**
   * @param {string} projectId
   * @param {string} kind
   * @param {string} documentId
   * @returns {Promise<import("./validate.js").StoredDocumentRecord[]>}
   */
  async function listDocumentVersions(projectId, kind, documentId) {
    requireId(projectId, "project_id");
    requireId(kind, "kind");
    requireId(documentId, "documentId");
    const history = await withTransaction(db, ["documents"], "readonly",
      (tx) => requestToPromise(/** @type {IDBRequest<import("./validate.js").StoredDocumentRecord[]>} */ (tx.objectStore("documents").index("by_project_document")
        .getAll(IDBKeyRange.only([projectId, kind, documentId])))));
    return history.sort((left, right) => right.version - left.version);
  }

  /**
   * @param {string} projectId
   * @param {string} kind
   * @param {string} documentId
   * @returns {Promise<import("./validate.js").StoredDocumentRecord|null>}
   */
  async function getLatestDocument(projectId, kind, documentId) {
    requireId(projectId, "project_id");
    requireId(kind, "kind");
    requireId(documentId, "documentId");
    return withTransaction(db, ["documents"], "readonly",
      (tx) => readDocumentHead(tx.objectStore("documents"), projectId, kind, documentId));
  }

  /**
   * 指定 kind 下每个 document_id 的最新版本（kind 参与索引键，查询不许跨 kind 返回）。
   * @param {string} projectId
   * @param {string} kind
   * @returns {Promise<import("./validate.js").StoredDocumentRecord[]>}
   */
  async function listLatestDocuments(projectId, kind) {
    requireId(projectId, "project_id");
    requireId(kind, "kind");
    const latest = await withTransaction(db, ["documents"], "readonly", (tx) => {
      const range = IDBKeyRange.bound([projectId, kind], [projectId, kind, []]);
      const request = tx.objectStore("documents").index("by_project_document_version")
        .openCursor(range, "prev");
      return new Promise((resolve, reject) => {
        /** @type {import("./validate.js").StoredDocumentRecord[]} */
        const records = [];
        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
          const cursor = request.result;
          if (!cursor) {
            resolve(records);
            return;
          }
          records.push(/** @type {import("./validate.js").StoredDocumentRecord} */ (cursor.value));
          // version ≥ 1：跳到当前文档的历史之前，只反序列化下一个文档的头。
          const currentKey = /** @type {IDBValidKey[]} */ (cursor.key);
          cursor.continue(/** @type {IDBValidKey} */ ([projectId, kind, currentKey[2], 0]));
        };
      });
    });
    return latest.sort((left, right) => left.document_id.localeCompare(right.document_id));
  }

  /**
   * 一个项目的全部文档版本（含历史），按 kind/document_id/version 稳定排序；导出项目包用。
   * @param {string} projectId
   * @returns {Promise<import("./validate.js").StoredDocumentRecord[]>}
   */
  async function listAllDocuments(projectId) {
    requireId(projectId, "project_id");
    const all = await withTransaction(db, ["documents"], "readonly",
      (tx) => requestToPromise(/** @type {IDBRequest<import("./validate.js").StoredDocumentRecord[]>} */ (tx.objectStore("documents").index("by_project_kind")
        .getAll(IDBKeyRange.bound([projectId], [projectId, []])))));
    return all.sort((left, right) => {
      if (left.kind !== right.kind) return left.kind.localeCompare(right.kind);
      if (left.document_id !== right.document_id) return left.document_id.localeCompare(right.document_id);
      return left.version - right.version;
    });
  }

  /**
   * 内容寻址写入资产：同项目同样字节只存一份；重复写入返回已有记录。
   * @param {string} projectId
   * @param {{bytes?:Uint8Array|ArrayBuffer|null, blob?:Blob|null, mediaType?:string, originalName?:string, role?:string|null, width?:number|null, height?:number|null}} [args]
   * @returns {Promise<import("./validate.js").StoredAssetRecord>}
   */
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
      const project = await requestToPromise(
        /** @type {IDBRequest<import("./validate.js").StoredProjectRecord|undefined>} */ (tx.objectStore("projects").get(projectId)));
      if (!project) {
        throw new StorageError(STORAGE_ERROR_CODES.NOT_FOUND, "项目 " + projectId + " 不存在。");
      }
      const store = tx.objectStore("assets");
      const existing = await requestToPromise(
        /** @type {IDBRequest<import("./validate.js").StoredAssetRecord|undefined>} */ (store.get(record.asset_key)));
      if (existing) return existing;
      await requestToPromise(store.add(record));
      return record;
    });
  }

  /**
   * @param {string} projectId
   * @param {string} sha256
   * @returns {Promise<import("./validate.js").StoredAssetRecord|null>}
   */
  async function getAsset(projectId, sha256) {
    requireId(projectId, "project_id");
    requireId(sha256, "sha256");
    return withTransaction(db, ["assets"], "readonly",
      (tx) => requestToPromise(/** @type {IDBRequest<import("./validate.js").StoredAssetRecord|undefined>} */ (tx.objectStore("assets").get(assetKeyOf(projectId, sha256)))))
      .then((record) => record ?? null);
  }

  /** @param {string} projectId @returns {Promise<import("./validate.js").StoredAssetRecord[]>} */
  async function listAssets(projectId) {
    requireId(projectId, "project_id");
    return withTransaction(db, ["assets"], "readonly",
      (tx) => requestToPromise(/** @type {IDBRequest<import("./validate.js").StoredAssetRecord[]>} */ (tx.objectStore("assets").index("by_project_id")
        .getAll(IDBKeyRange.only(projectId)))));
  }

  /**
   * @param {string} projectId
   * @param {string} sha256
   * @returns {Promise<boolean>}
   */
  async function deleteAsset(projectId, sha256) {
    requireId(projectId, "project_id");
    requireId(sha256, "sha256");
    return withTransaction(db, ["documents", "assets"], "readwrite", async (tx) => {
      const store = tx.objectStore("assets");
      const key = assetKeyOf(projectId, sha256);
      const existing = await requestToPromise(
        /** @type {IDBRequest<import("./validate.js").StoredAssetRecord|undefined>} */ (store.get(key)));
      if (!existing) return false;
      const documents = await requestToPromise(tx.objectStore("documents").index("by_project_kind")
        .getAll(IDBKeyRange.bound([projectId, ""], [projectId, "\uffff"])));
      if (documents.some(row => referencesAsset(row.payload, sha256))) transactionConflict("asset_referenced");
      await requestToPromise(store.delete(key));
      return true;
    });
  }

  /**
   * 把当前项目指针写到 localStorage（指针只能指向已存在的项目）。
   * @param {string} projectId
   * @returns {Promise<{project_id:string, updated_at:string}>}
   */
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

  /** @returns {Promise<import("./validate.js").StoredProjectRecord|null>} 指针失效时清除并返回 null。 */
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

  /** @returns {void} */
  function clearCurrentProject() {
    removePointer(storage);
  }

  return {
    reserveGenerationAttempt,
    appendAttemptObservation,
    saveCandidate,
    readProjectSnapshot,
    commitSelection,
    commitDeliveryRecord,
    commitReviewReport,
    projects: {
      create: createProject,
      get: getProject,
      list: listProjects,
      rename: renameProject,
      setState: updateProjectState,
      remove: deleteProject,
      duplicate: duplicateProject,
    },
    documents: {
      save: saveDocument,
      get: getDocument,
      listVersions: listDocumentVersions,
      getLatest: getLatestDocument,
      listLatest: listLatestDocuments,
      listAll: listAllDocuments,
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
