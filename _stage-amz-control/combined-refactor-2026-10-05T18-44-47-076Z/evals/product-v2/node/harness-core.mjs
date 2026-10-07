/**
 * Node 原生契约测试的公共装置（R3.2）。
 * 只保留两个纯逻辑能力：领域断言 helper、Node 内建 WebCrypto 散列。
 * 不依赖浏览器：不再有 /storage 的 openStorage、dropDatabase、rawPut 等。
 * 只有测试文件用它；产品代码不得 import 本文件。
 */

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
 * Node 内置 WebCrypto（subtle.digest 是全局的），与浏览器 storage/db.js 的
 * sha256Hex 语义一致；产品层仍旧注入 storage/db.js 的 sha256Hex。
 */
export function sha256Hex(bytes) {
  return globalThis.crypto.subtle.digest("SHA-256", bytes)
    .then((digest) => Array.from(new Uint8Array(digest))
      .map((b) => b.toString(16).padStart(2, "0")).join(""));
}

export const DIGEST = { digest: sha256Hex };

/**
 * V2.R5.3 有效图像 Prompt 档的固定测试 fixture（纯领域常量，不调用模型、不读服务端）。
 * 与浏览器 harness-api.js 的同名 fixture 一致：目标 + 协议 + 请求 profile；
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
