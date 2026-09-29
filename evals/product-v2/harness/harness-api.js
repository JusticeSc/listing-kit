/**
 * 契约测试的公共装置：打开/清理数据库、raw 读写、断言与 window.v2Harness。
 * 只有测试页用它；产品代码不得 import 本文件。
 */

import {
  CURRENT_PROJECT_POINTER_KEY,
  STORAGE_SCHEMA_VERSION,
  STORE_SPECS,
  describeDatabase,
  expectedSchemaShape,
  openStorage,
  pointerKeys,
  readPointer,
  requestToPromise,
  schemaDrift,
  withTransaction,
  writePointer,
} from "/storage/index.js";

export {
  CURRENT_PROJECT_POINTER_KEY,
  STORAGE_SCHEMA_VERSION,
  STORE_SPECS,
  describeDatabase,
  expectedSchemaShape,
  openStorage,
  pointerKeys,
  readPointer,
  requestToPromise,
  schemaDrift,
  withTransaction,
  writePointer,
};

export function newDbName(prefix = "amz-v2-contract") {
  return prefix + "-" + crypto.randomUUID();
}

export function dropDatabase(name) {
  return new Promise((resolve) => {
    const request = indexedDB.deleteDatabase(name);
    const done = () => resolve(true);
    request.onsuccess = done;
    request.onerror = done;
    request.onblocked = done;
  });
}

export function rawPut(db, storeName, value) {
  return withTransaction(db, [storeName], "readwrite",
    (tx) => requestToPromise(tx.objectStore(storeName).put(value)));
}

export function rawGet(db, storeName, key) {
  return withTransaction(db, [storeName], "readonly",
    (tx) => requestToPromise(tx.objectStore(storeName).get(key)));
}

export function rawCount(db, storeName) {
  return withTransaction(db, [storeName], "readonly",
    (tx) => requestToPromise(tx.objectStore(storeName).count()));
}

export function expect(condition, message) {
  if (!condition) throw new Error(message);
}

export function serializeError(error) {
  if (!error) return { message: "unknown error" };
  return {
    name: error.name || "Error",
    code: error.code || null,
    message: error.message || String(error),
    details: error.details || null,
  };
}

export async function expectCode(run, code, label) {
  try {
    await run();
  } catch (error) {
    const actual = error && error.code ? error.code : (error && error.name) || "unknown";
    if (actual !== code) {
      throw new Error(label + "：期望错误码 " + code + "，实际是 " + actual
        + "（" + (error && error.message) + "）");
    }
    return { code: actual, message: error.message };
  }
  throw new Error(label + "：期望抛出 " + code + "，但没有抛错。");
}

export function utf8Bytes(text) {
  return new TextEncoder().encode(text);
}

/* ---- window.v2Harness：Python 侧驱动的窄接口 ---- */

const handles = new Map();

export async function harnessOpen({ name, storage } = {}) {
  const opened = await openStorage({ name, storage });
  handles.set(name, opened);
  return { dbName: name, version: opened.db.version, stores: Array.from(opened.db.objectStoreNames) };
}

export function harnessHandle(name) {
  const opened = handles.get(name);
  if (!opened) throw new Error("没有已打开的数据库：" + name);
  return opened.repository;
}

export function harnessClose(name) {
  const opened = handles.get(name);
  if (!opened) return false;
  opened.close();
  handles.delete(name);
  return true;
}

if (typeof window !== "undefined") {
  window.v2Harness = {
    open: harnessOpen,
    close: harnessClose,
    createProject: (name, projectName) => harnessHandle(name).projects.create({ name: projectName }),
    listProjects: (name) => harnessHandle(name).projects.list(),
    deleteProject: (name, projectId) => harnessHandle(name).projects.remove(projectId),
    setCurrentProject: (name, projectId) => harnessHandle(name).pointer.set(projectId),
    getCurrentProject: (name) => harnessHandle(name).pointer.get(),
    pointerKeys,
    pointerRaw: () => localStorage.getItem(CURRENT_PROJECT_POINTER_KEY),
  };
}
