/**
 * IndexedDB 打开、迁移执行、事务与纯工具函数。
 *
 * 关键约束：
 * - 打开版本低于现有数据库版本 → SCHEMA_TOO_NEW，不静默降级、不改数据。
 * - 迁移失败 → 升级事务整体回滚，不允许留下半个 schema。
 * - withTransaction 内不要 await 非 IndexedDB 的 Promise：事务会自动提交，
 *   之后再写入会得到 TransactionInactiveError。需要哈希/编码时先算完再进事务。
 */

import {
  CAPABILITY_GAPS,
  STORAGE_ERROR_CODES,
  StorageError,
  cryptoCapabilityError,
  toStorageError,
} from "./errors.js";
import { DB_NAME } from "./schema.js";
import { DEFAULT_MIGRATIONS } from "./migrations.js";

/** @returns {string} ISO 8601 时间戳 */
export function nowIso() {
  return new Date().toISOString();
}

/** @returns {string} crypto.randomUUID() 结果 */
export function randomId() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  throw cryptoCapabilityError(CAPABILITY_GAPS.RANDOM_UUID, "缺少 crypto.randomUUID，无法生成项目与记录 ID。");
}

/**
 * @param {ArrayBuffer|ArrayBufferView} bytes
 * @returns {Promise<string>} 64 位小写十六进制 SHA-256
 */
export async function sha256Hex(bytes) {
  const subtle = globalThis.crypto && globalThis.crypto.subtle;
  if (!subtle || typeof subtle.digest !== "function") {
    throw cryptoCapabilityError(CAPABILITY_GAPS.WEBCRYPTO, "缺少 crypto.subtle，无法计算 SHA-256。");
  }
  const view = bytes instanceof ArrayBuffer
    ? new Uint8Array(bytes)
    : new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const digest = await subtle.digest("SHA-256", view);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

/**
 * 把 IDBRequest 包成 Promise；成功 resolve result，失败 reject StorageError。
 * （IDBRequest<T> 与 Promise<T> 在 TS 声明里方变不兼容，这里用显式 @type 桥接，
 * 运行时就是同一个 Promise 对象，不产生额外包装。）
 * @template T
 * @param {IDBRequest<T>} request
 * @returns {Promise<T>}
 */
export function requestToPromise(request) {
  return /** @type {Promise<T>} */ (new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(toStorageError(request.error));
  }));
}

/**
 * 逐条收集 cursor 值直到遍历完成。
 * @template T
 * @param {IDBRequest<IDBCursorWithValue|null>} request
 * @returns {Promise<T[]>}
 */
export function openCursorPromise(request) {
  return /** @type {Promise<T[]>} */ (new Promise((resolve, reject) => {
    const items = [];
    request.onsuccess = () => {
      const cursor = request.result;
      if (!cursor) {
        resolve(items);
        return;
      }
      items.push(cursor.value);
      cursor.continue();
    };
    request.onerror = () => reject(toStorageError(request.error));
  }));
}

/**
 * 在一个事务里执行 fn(tx)，fn 正常结束且事务提交后 resolve(fn 的返回值)。
 * fn 抛出（或 reject）→ 事务 abort，之前在同一事务里的写入全部回滚。
 * @template T
 * @param {IDBDatabase} db
 * @param {string|ReadonlyArray<string>} storeNames
 * @param {IDBTransactionMode} mode
 * @param {(tx: IDBTransaction) => T|Promise<T>} fn
 * @returns {Promise<T>}
 */
export function withTransaction(db, storeNames, mode, fn) {
  const stores = Array.isArray(storeNames) ? storeNames : [storeNames];
  return new Promise((resolve, reject) => {
    let tx;
    try {
      tx = db.transaction(stores, mode);
    } catch (error) {
      reject(toStorageError(error));
      return;
    }
    let outcome;
    let fnError = null;
    let settled = false;
    const settleReject = (error) => {
      if (!settled) {
        settled = true;
        reject(error);
      }
    };
    const settleResolve = (value) => {
      if (!settled) {
        settled = true;
        resolve(value);
      }
    };
    tx.oncomplete = () => {
      if (fnError) settleReject(fnError);
      else settleResolve(outcome);
    };
    tx.onabort = () => settleReject(fnError || toStorageError(tx.error));
    tx.onerror = () => { /* 由 onabort 统一收口 */ };
    Promise.resolve()
      .then(() => fn(tx))
      .then((value) => { outcome = value; }, (error) => {
        fnError = toStorageError(error);
        let aborted = false;
        try {
          tx.abort();
          aborted = true;
        } catch (abortError) {
          aborted = false;
        }
        if (!aborted) settleReject(fnError);
      });
  });
}

/**
 * 迁移条目：version 必须连续递增；apply 在 versionchange 事务内同步执行。
 * @typedef {object} DatabaseMigration
 * @property {number} version
 * @property {string} describe
 * @property {(db: IDBDatabase, tx: IDBTransaction|null, context: {from: number, to: number}) => void} apply
 */

/**
 * @param {ReadonlyArray<DatabaseMigration>} migrations
 * @returns {ReadonlyArray<DatabaseMigration>}
 */
function sortMigrations(migrations) {
  return [...migrations].sort((a, b) => a.version - b.version);
}

/**
 * @param {ReadonlyArray<DatabaseMigration>} [migrations=DEFAULT_MIGRATIONS]
 * @returns {number}
 */
export function schemaVersionOf(migrations = DEFAULT_MIGRATIONS) {
  return sortMigrations(migrations).reduce((max, item) => Math.max(max, item.version), 0);
}

/**
 * 目标库打不开时保留已知的特定原因（版本过高、配额、schema 损坏），
 * 其余统一归为 DATABASE_OPEN_FAILED：界面据此把「存储被禁用/数据损坏」
 * 与「代码太旧」「空间不足」分开处理。
 */
/**
 * @param {StorageError|{code?:string,message?:string}|null|undefined|string} failure
 * @returns {StorageError}
 */
function wrapDatabaseOpenFailure(failure) {
  if (failure instanceof StorageError) {
    const keep = [
      STORAGE_ERROR_CODES.SCHEMA_TOO_NEW,
      STORAGE_ERROR_CODES.SCHEMA_INVALID,
      STORAGE_ERROR_CODES.QUOTA_EXCEEDED,
      STORAGE_ERROR_CODES.DUPLICATE_RECORD,
    ];
    if (keep.includes(failure.code)) {
      return failure;
    }
  }
  return new StorageError(
    STORAGE_ERROR_CODES.DATABASE_OPEN_FAILED,
    "打开本机项目数据库失败：" + (failure && typeof failure === "object" && failure.message ? failure.message : String(failure)),
    { gap: CAPABILITY_GAPS.DATABASE_OPEN, cause_code: failure && typeof failure === "object" && failure.code ? failure.code : null },
  );
}

/**
 * 打开（或创建）数据库并把所有缺失的迁移按版本顺序执行完。
 * 返回 IDBDatabase；调用方负责在不需要时 close()。
 * @param {{name?:string, migrations?:ReadonlyArray<DatabaseMigration>, idbFactory?:IDBFactory|null}} [options]
 * @returns {Promise<IDBDatabase>}
 */
export function openDatabase({
  name = DB_NAME,
  migrations = DEFAULT_MIGRATIONS,
  idbFactory = globalThis.indexedDB,
} = {}) {
  if (!idbFactory || typeof idbFactory.open !== "function") {
    return Promise.reject(new StorageError(
      STORAGE_ERROR_CODES.INDEXEDDB_UNAVAILABLE,
      "当前环境没有 IndexedDB。",
      { gap: CAPABILITY_GAPS.INDEXEDDB }));
  }
  const ordered = sortMigrations(migrations);
  const targetVersion = schemaVersionOf(ordered);
  return new Promise((resolve, reject) => {
    let request;
    try {
      request = idbFactory.open(name, targetVersion);
    } catch (error) {
      reject(wrapDatabaseOpenFailure(toStorageError(error)));
      return;
    }
    let upgradeError = null;
    request.onupgradeneeded = (event) => {
      const db = request.result;
      const tx = request.transaction;
      const from = event.oldVersion;
      try {
        for (const migration of ordered) {
          if (migration.version > from) {
            migration.apply(db, tx, { from, to: migration.version });
          }
        }
      } catch (error) {
        upgradeError = toStorageError(error);
        try {
          if (tx) tx.abort();
        } catch (_ignored) { /* 事务可能已因错误中止 */ }
      }
    };
    request.onsuccess = () => {
      const db = request.result;
      if (db.version > targetVersion) {
        db.close();
        reject(new StorageError(
          STORAGE_ERROR_CODES.SCHEMA_TOO_NEW,
          "浏览器里的数据库版本 " + db.version + " 高于代码支持的 " + targetVersion + "。"));
        return;
      }
      resolve(db);
    };
    request.onerror = () => {
      if (upgradeError) {
        // 迁移失败已有明确语义（事务回滚），不能被改写成能力缺口。
        reject(upgradeError);
        return;
      }
      reject(wrapDatabaseOpenFailure(toStorageError(request.error)));
    };
    request.onblocked = () => {
      // 另一个标签页占着旧版本连接；不静默重试，等它关闭。
    };
  });
}
