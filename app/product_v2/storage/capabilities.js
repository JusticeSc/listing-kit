/**
 * 浏览器能力探针（V2.UI.1）。
 *
 * 远程明文 HTTP 不是安全上下文：IndexedDB 仍然可用，但浏览器会禁用
 * crypto.randomUUID 与 crypto.subtle。探针把「能不能用」拆成互不替代的
 * 能力项分别测量，避免把 WebCrypto 缺失误报成「IndexedDB 不支持」。
 *
 * 测量项：
 *   1. 当前来源是否安全上下文（HTTPS 或 localhost）
 *   2. 宿主是否暴露 IndexedDB 工厂
 *   3. 目标数据库能否打开（走真实 openDatabase 与迁移路径）
 *   4. crypto.randomUUID 是否存在
 *   5. crypto.subtle 是否存在
 *   6. 目标库上能否完成一次最小读写事务（保留键写入后立刻删除，不留业务记录）
 *
 * 探针只做测量：不写业务记录、不建额外数据库、不动 localStorage。
 */

import { openDatabase } from "./db.js";
import { CAPABILITY_GAPS } from "./errors.js";
import { DB_NAME } from "./schema.js";

const GAP_ORDER = Object.freeze([
  CAPABILITY_GAPS.SECURE_CONTEXT,
  CAPABILITY_GAPS.INDEXEDDB,
  CAPABILITY_GAPS.DATABASE_OPEN,
  CAPABILITY_GAPS.RANDOM_UUID,
  CAPABILITY_GAPS.WEBCRYPTO,
  CAPABILITY_GAPS.TRANSACTION,
]);

const PROBE_STORE = "documents";
const PROBE_KEY_PATH = "document_key";
const PROBE_KEY = "__capability_probe__";

/** 在目标库上写一条保留键记录再删掉；成功与否只说明引擎能否完成读写事务。 */
function probeReadWriteTransaction(db) {
  return new Promise((resolve) => {
    let transaction;
    try {
      transaction = db.transaction(PROBE_STORE, "readwrite");
    } catch (error) {
      resolve(false);
      return;
    }
    let settled = false;
    const finish = (value) => {
      if (!settled) {
        settled = true;
        resolve(value);
      }
    };
    transaction.oncomplete = () => finish(true);
    transaction.onabort = () => finish(false);
    transaction.onerror = () => finish(false);
    try {
      const store = transaction.objectStore(PROBE_STORE);
      const record = {};
      record[PROBE_KEY_PATH] = PROBE_KEY;
      const write = store.put(record);
      write.onerror = () => finish(false);
      write.onsuccess = () => {
        const remove = store.delete(PROBE_KEY);
        remove.onerror = () => finish(false);
      };
    } catch (error) {
      finish(false);
    }
  });
}

export async function probeBrowserCapabilities(options = {}) {
  const {
    idbFactory = globalThis.indexedDB,
    cryptoObj = globalThis.crypto,
    locationObj = globalThis.location,
    secureContextFlag = globalThis.isSecureContext,
    openDatabaseFn = openDatabase,
  } = options;

  const origin = locationObj && typeof locationObj.origin === "string" ? locationObj.origin : "";
  const secureContext = secureContextFlag === true;
  const indexeddb = Boolean(idbFactory && typeof idbFactory.open === "function");
  const randomUuid = Boolean(cryptoObj && typeof cryptoObj.randomUUID === "function");
  const webcrypto = Boolean(
    cryptoObj && cryptoObj.subtle && typeof cryptoObj.subtle.digest === "function",
  );

  let databaseOpen = false;
  let databaseOpenError = null;
  let transaction = null;
  let database = null;

  if (indexeddb) {
    try {
      database = await openDatabaseFn({ idbFactory });
      databaseOpen = true;
    } catch (error) {
      const code = error && error.code ? String(error.code) : String((error && error.name) || error);
      const message = error && error.message ? "：" + error.message : "";
      databaseOpenError = code + message;
    }
  }
  if (database) {
    try {
      transaction = await probeReadWriteTransaction(database);
    } finally {
      database.close();
    }
  }

  const gaps = [];
  const addGap = (gap) => {
    if (!gaps.includes(gap)) gaps.push(gap);
  };
  if (!secureContext) addGap(CAPABILITY_GAPS.SECURE_CONTEXT);
  if (!indexeddb) addGap(CAPABILITY_GAPS.INDEXEDDB);
  if (indexeddb && !databaseOpen) addGap(CAPABILITY_GAPS.DATABASE_OPEN);
  if (!randomUuid) addGap(CAPABILITY_GAPS.RANDOM_UUID);
  if (!webcrypto) addGap(CAPABILITY_GAPS.WEBCRYPTO);
  if (transaction === false) addGap(CAPABILITY_GAPS.TRANSACTION);
  gaps.sort((a, b) => GAP_ORDER.indexOf(a) - GAP_ORDER.indexOf(b));

  return {
    ok: gaps.length === 0,
    origin,
    secure_context: secureContext,
    indexeddb,
    database_open: databaseOpen,
    database_name: DB_NAME,
    database_open_error: databaseOpenError,
    random_uuid: randomUuid,
    webcrypto,
    transaction,
    gaps,
  };
}
