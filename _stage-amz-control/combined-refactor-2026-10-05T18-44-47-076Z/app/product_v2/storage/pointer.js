/**
 * localStorage 只保存"当前打开哪个项目"的轻量指针。
 *
 * 允许的键只有 CURRENT_PROJECT_POINTER_KEY，值只有 {project_id, updated_at}。
 * 读到损坏、超长、多字段或指向已删除项目的指针时：清掉它并返回 null，
 * 让界面回到"没有当前项目"的空白状态，而不是崩溃或伪造一个项目。
 */

import { assertPointerShape, MAX_POINTER_BYTES } from "./validate.js";

export const CURRENT_PROJECT_POINTER_KEY = "amz-listing-kit-v2:current-project";

/**
 * @returns {Storage|null}
 */
function defaultStorage() {
  return globalThis.localStorage || null;
}

/**
 * @param {Storage|null} [storage=defaultStorage()]
 * @returns {void}
 */
export function removePointer(storage = defaultStorage()) {
  if (!storage) return;
  try {
    storage.removeItem(CURRENT_PROJECT_POINTER_KEY);
  } catch (_ignored) { /* 隐私模式下可能不可写；指针丢了不影响项目数据 */ }
}

/**
 * 读指针；损坏/超长/多字段一律清除并返回 null，不伪造项目。
 * @param {Storage|null} [storage=defaultStorage()]
 * @returns {{project_id:string, updated_at:string}|null}
 */
export function readPointer(storage = defaultStorage()) {
  if (!storage) return null;
  let raw = null;
  try {
    raw = storage.getItem(CURRENT_PROJECT_POINTER_KEY);
  } catch (_ignored) {
    return null;
  }
  if (!raw) return null;
  if (raw.length > MAX_POINTER_BYTES) {
    removePointer(storage);
    return null;
  }
  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (_ignored) {
    removePointer(storage);
    return null;
  }
  if (!assertPointerShape(parsed)) {
    removePointer(storage);
    return null;
  }
  return { project_id: parsed.project_id, updated_at: parsed.updated_at };
}

/**
 * @param {{project_id:string, updated_at:string}} pointer
 * @param {Storage|null} [storage=defaultStorage()]
 * @returns {boolean} 写入是否成功（隐私模式下可能失败）
 */
export function writePointer(pointer, storage = defaultStorage()) {
  if (!storage) return false;
  const canonical = { project_id: pointer.project_id, updated_at: pointer.updated_at };
  if (!assertPointerShape(canonical)) return false;
  const text = JSON.stringify(canonical);
  if (text.length > MAX_POINTER_BYTES) return false;
  try {
    storage.setItem(CURRENT_PROJECT_POINTER_KEY, text);
    return true;
  } catch (_ignored) {
    return false;
  }
}

/**
 * @param {Storage|null} [storage=defaultStorage()]
 * @returns {string[]}
 */
export function pointerKeys(storage = defaultStorage()) {
  if (!storage) return [];
  const keys = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (typeof key === "string") keys.push(key);
  }
  return keys.sort();
}
