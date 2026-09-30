/**
 * 项目包 ZIP 读写：薄适配器（SEL-008）。
 *
 * 结构解析与压缩/解压委托 vendored fflate 0.8.3（`../vendor/fflate.browser.js`，MIT）：
 * 写包固定 store（level 0）—— PNG/JPEG 本身已压缩，store 不增大体积且任何工具可读；
 * 读包支持 store 与 deflate（method 0/8）条目，不再依赖 DecompressionStream。
 *
 * 本文件只保留三类自有内容，通用能力不复刻：
 *   1) 产品上限与错误码：单包 < 4 GiB、条目 <= 65535（PACKAGE_TOO_LARGE）；
 *      非法结构、加密条目、未知压缩方法、重复路径归 PACKAGE_INVALID。ZIP64 直接拒绝，
 *      不静默截断。
 *   2) 完整性校验：fflate 的 unzipSync 不核对 CRC32，这里按中央目录逐条核对
 *      长度与 CRC32 —— 损坏或篡改的项目包必须在读入阶段被拒绝。
 *   3) 对外接口形状：buildZip / readZip / crc32（契约测试与调用方依赖）。
 */

import { unzipSync, zipSync } from "../vendor/fflate.browser.js";
import { STORAGE_ERROR_CODES, StorageError } from "./errors.js";

const MAX_ENTRIES = 0xffff;
const MAX_BYTES = 0xffffffff;
const EOCD_SIGNATURE = 0x06054b50;
const CENTRAL_SIGNATURE = 0x02014b50;

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let index = 0; index < 256; index += 1) {
    let value = index;
    for (let bit = 0; bit < 8; bit += 1) {
      value = (value & 1) ? (0xedb88320 ^ (value >>> 1)) : (value >>> 1);
    }
    table[index] = value >>> 0;
  }
  return table;
})();

export function crc32(bytes) {
  let crc = 0xffffffff;
  for (let index = 0; index < bytes.length; index += 1) {
    crc = CRC_TABLE[(crc ^ bytes[index]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function errorText(error) {
  return error instanceof Error && error.message ? error.message : String(error);
}

function invalid(message) {
  return new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, message);
}

/**
 * 只读中央目录，拿到逐条 CRC32/长度用于完整性校验（结构解析仍以 fflate 为准）。
 * 越界、缺 EOCD、坏签名都直接拒绝；ZIP64 按产品上限拒绝。
 */
function readDirectoryRecords(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let eocd = -1;
  const lowest = Math.max(0, bytes.length - 65557);
  for (let index = bytes.length - 22; index >= lowest; index -= 1) {
    if (view.getUint32(index, true) === EOCD_SIGNATURE) { eocd = index; break; }
  }
  if (eocd < 0) {
    throw invalid("不是有效的 ZIP：找不到中央目录结束记录。");
  }
  const entryCount = view.getUint16(eocd + 10, true);
  const centralSize = view.getUint32(eocd + 12, true);
  const centralOffset = view.getUint32(eocd + 16, true);
  if (entryCount === MAX_ENTRIES || centralSize === MAX_BYTES || centralOffset === MAX_BYTES) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_TOO_LARGE, "不支持 ZIP64 项目包。");
  }
  if (centralOffset + centralSize > bytes.length) {
    throw invalid("项目包被截断：中央目录越界。");
  }
  const decoder = new TextDecoder();
  const records = [];
  const seen = new Set();
  let cursor = centralOffset;
  for (let index = 0; index < entryCount; index += 1) {
    if (cursor + 46 > bytes.length || view.getUint32(cursor, true) !== CENTRAL_SIGNATURE) {
      throw invalid("中央目录第 " + index + " 项损坏。");
    }
    const flags = view.getUint16(cursor + 8, true);
    const method = view.getUint16(cursor + 10, true);
    const expectedCrc = view.getUint32(cursor + 16, true);
    const uncompressedSize = view.getUint32(cursor + 24, true);
    const nameLength = view.getUint16(cursor + 28, true);
    const extraLength = view.getUint16(cursor + 30, true);
    const commentLength = view.getUint16(cursor + 32, true);
    const path = decoder.decode(bytes.subarray(cursor + 46, cursor + 46 + nameLength));
    if ((flags & 0x0001) !== 0) {
      throw invalid("不支持加密条目：" + path);
    }
    if (method !== 0 && method !== 8) {
      throw invalid("不支持的压缩方法 " + method + "：" + path);
    }
    if (seen.has(path)) {
      throw invalid("项目包含重复条目：" + path);
    }
    seen.add(path);
    records.push({ path, crc: expectedCrc, size: uncompressedSize });
    cursor += 46 + nameLength + extraLength + commentLength;
  }
  return records;
}

export function buildZip(entries, { modifiedAt = new Date() } = {}) {
  if (entries.length > MAX_ENTRIES) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_TOO_LARGE, "ZIP 条目数超过 65535。");
  }
  const files = {};
  for (const entry of entries) {
    if (Object.prototype.hasOwnProperty.call(files, entry.path)) {
      throw invalid("ZIP 条目路径重复：" + entry.path);
    }
    files[entry.path] = [entry.bytes, { level: 0, mtime: modifiedAt }];
  }
  let bytes;
  try {
    bytes = zipSync(files, { level: 0 });
  } catch (error) {
    throw invalid("ZIP 写入失败：" + errorText(error));
  }
  if (bytes.length > MAX_BYTES) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_TOO_LARGE, "ZIP 超过 4 GiB 上限。");
  }
  return bytes;
}

export async function readZip(bytes, { maxEntries = 4096 } = {}) {
  if (!(bytes instanceof Uint8Array)) {
    throw invalid("readZip 需要 Uint8Array。");
  }
  const records = readDirectoryRecords(bytes);
  if (records.length > maxEntries) {
    throw new StorageError(
      STORAGE_ERROR_CODES.PACKAGE_TOO_LARGE,
      "项目包条目数 " + records.length + " 超过上限 " + maxEntries + "。",
    );
  }
  let files;
  try {
    files = unzipSync(bytes);
  } catch (error) {
    throw invalid("ZIP 解析失败：" + errorText(error));
  }
  return records.map((record) => {
    const data = files[record.path];
    if (!data) {
      throw invalid("条目缺失：" + record.path);
    }
    if (data.length !== record.size) {
      throw invalid("条目长度不符：" + record.path);
    }
    if (crc32(data) !== record.crc) {
      throw invalid("条目校验和不符：" + record.path);
    }
    return { path: record.path, bytes: data };
  });
}
