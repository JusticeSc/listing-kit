/**
 * IndexedDB 打开、迁移执行、事务与纯工具函数。
 *
 * 关键约束：
 * - 打开版本低于现有数据库版本 → SCHEMA_TOO_NEW，不静默降级、不改数据。
 * - 迁移失败 → 升级事务整体回滚，不允许留下半个 schema。
 * - withTransaction 内不要 await 非 IndexedDB 的 Promise：事务会自动提交，
 *   之后再写入会得到 TransactionInactiveError。需要哈希/编码时先算完再进事务。
 */

import { STORAGE_ERROR_CODES, StorageError, toStorageError } from "./errors.js";
import { DB_NAME } from "./schema.js";
import { DEFAULT_MIGRATIONS } from "./migrations.js";

export function nowIso() {
  return new Date().toISOString();
}

export function randomId() {
  if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  throw new StorageError(STORAGE_ERROR_CODES.UNSUPPORTED_BROWSER, "当前浏览器缺少 crypto.randomUUID。");
}

export async function sha256Hex(bytes) {
  const subtle = globalThis.crypto && globalThis.crypto.subtle;
  if (!subtle) {
    throw new StorageError(STORAGE_ERROR_CODES.UNSUPPORTED_BROWSER, "当前浏览器缺少 WebCrypto。");
  }
  const view = bytes instanceof ArrayBuffer
    ? new Uint8Array(bytes)
    : new Uint8Array(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const digest = await subtle.digest("SHA-256", view);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export function requestToPromise(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(toStorageError(request.error));
  });
}

export function openCursorPromise(request) {
  return new Promise((resolve, reject) => {
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
  });
}

/**
 * 在一个事务里执行 fn(tx)，fn 正常结束且事务提交后 resolve(fn 的返回值)。
 * fn 抛出（或 reject）→ 事务 abort，之前在同一事务里的写入全部回滚。
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

function sortMigrations(migrations) {
  return [...migrations].sort((a, b) => a.version - b.version);
}

export function schemaVersionOf(migrations = DEFAULT_MIGRATIONS) {
  return sortMigrations(migrations).reduce((max, item) => Math.max(max, item.version), 0);
}

/**
 * 打开（或创建）数据库并把所有缺失的迁移按版本顺序执行完。
 * 返回 IDBDatabase；调用方负责在不需要时 close()。
 */
export function openDatabase({
  name = DB_NAME,
  migrations = DEFAULT_MIGRATIONS,
  idbFactory = globalThis.indexedDB,
} = {}) {
  if (!idbFactory) {
    return Promise.reject(new StorageError(
      STORAGE_ERROR_CODES.UNSUPPORTED_BROWSER, "当前环境没有 IndexedDB。"));
  }
  const ordered = sortMigrations(migrations);
  const targetVersion = schemaVersionOf(ordered);
  return new Promise((resolve, reject) => {
    let request;
    try {
      request = idbFactory.open(name, targetVersion);
    } catch (error) {
      reject(toStorageError(error));
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
          tx.abort();
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
      reject(upgradeError || toStorageError(request.error));
    };
    request.onblocked = () => {
      // 另一个标签页占着旧版本连接；不静默重试，等它关闭。
    };
  });
}
