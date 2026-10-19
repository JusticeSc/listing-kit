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

/**
 * V2.R5.3 有效图像 Prompt 档的固定测试 fixture（纯领域常量，不调用模型、不读服务端）。
 * 形状与 domain.imagePromptProfile(capabilities.images) 的输出一致：目标 + 协议 + 请求 profile；
 * 数值沿用当前产品网关的保守请求限制（384..2048 边、512²..2048² 面积、比例 1/8..8、1344*1344）。
 */
export const IMAGE_PROMPT_PROFILE = Object.freeze({
  provider_id: "dashscope-qwen-image",
  model_id: "qwen-image-3.0",
  version: 1,
  protocol: "v2.4.1",
  size: "1344*1344",
  n: 1,
  prompt_extend: false,
  watermark: false,
  output_format: "png",
  supports_negative_prompt_field: false,
  max_reference_images: 3,
  reference_media_types: Object.freeze(["image/png", "image/jpeg"]),
  min_side: 384,
  max_side: 2048,
  min_area: 512 * 512,
  max_area: 2048 * 2048,
  min_ratio: 1 / 8,
  max_ratio: 8,
  max_prompt_chars: 4000,
});
/**
 * 与产品有效能力块上 images.pricing 同形状的固定报价 fixture（纯领域常量不调用模型不读服务端）。
 * 只给标准 canonical dashscope 档 image-cost.js pricingMatches 能通过的官方组合：
 * version:1/currency CNY/provider dashscope-qwen-image/model qwen-image-3.0/size 1344*1344/n 1/png。
 * 任意目标/参数/金额/地区/来源不同都按缺失或失配处理由调用 helper 按测试意图显式覆盖为 null 或其它值。
 */
export const IMAGE_PRICING = Object.freeze({
  version: 1,
  kind: "official",
  provider_id: "dashscope-qwen-image",
  model_id: "qwen-image-3.0",
  size: "1344*1344",
  n: 1,
  output_format: "png",
  currency: "CNY",
  input_image_fen: 2,
  output_image_fen: 18,
  verified_on: "2026-10-19",
  source_url: "https://help.aliyun.com/zh/model-studio/qwen-image-3.0.md",
  region: "cn-beijing",
});

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
