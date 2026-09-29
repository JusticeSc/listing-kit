/**
 * 最小标准 ZIP 读写（无第三方依赖）。
 *
 * 写：method=0（store），UTF-8 文件名，标准本地头 + 中央目录 + EOCD。
 *     PNG/JPEG 本身已压缩，store 不会明显变大，换来的是实现小、可被任何工具打开。
 * 读：支持 method 0（store）与 method 8（deflate-raw），逐条校验 CRC32 与长度；
 *     加密条目、ZIP64、未知压缩方法都显式拒绝，不猜、不跳过。
 *
 * 限制：单包 < 4 GiB、条目数 < 65535 —— 超出时报 PACKAGE_TOO_LARGE，
 * 不做静默截断。
 */

import { STORAGE_ERROR_CODES, StorageError } from "./errors.js";

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

function dosDateTime(date) {
  const year = Math.max(1980, date.getFullYear());
  const time = (date.getHours() << 11) | (date.getMinutes() << 5) | (date.getSeconds() >> 1);
  const day = ((year - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate();
  return { time: time & 0xffff, date: day & 0xffff };
}

function concat(chunks, total) {
  const output = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.length;
  }
  return output;
}

export function buildZip(entries, { modifiedAt = new Date() } = {}) {
  if (entries.length > 0xffff) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_TOO_LARGE, "ZIP 条目数超过 65535。");
  }
  const encoder = new TextEncoder();
  const { time, date } = dosDateTime(modifiedAt);
  const chunks = [];
  const central = [];
  let offset = 0;
  for (const entry of entries) {
    const nameBytes = encoder.encode(entry.path);
    const data = entry.bytes;
    const crc = crc32(data);
    const local = new Uint8Array(30 + nameBytes.length);
    const localView = new DataView(local.buffer);
    localView.setUint32(0, 0x04034b50, true);
    localView.setUint16(4, 20, true);
    localView.setUint16(6, 0x0800, true);
    localView.setUint16(8, 0, true);
    localView.setUint16(10, time, true);
    localView.setUint16(12, date, true);
    localView.setUint32(14, crc, true);
    localView.setUint32(18, data.length, true);
    localView.setUint32(22, data.length, true);
    localView.setUint16(26, nameBytes.length, true);
    localView.setUint16(28, 0, true);
    local.set(nameBytes, 30);
    chunks.push(local, data);

    const directory = new Uint8Array(46 + nameBytes.length);
    const directoryView = new DataView(directory.buffer);
    directoryView.setUint32(0, 0x02014b50, true);
    directoryView.setUint16(4, 20, true);
    directoryView.setUint16(6, 20, true);
    directoryView.setUint16(8, 0x0800, true);
    directoryView.setUint16(10, 0, true);
    directoryView.setUint16(12, time, true);
    directoryView.setUint16(14, date, true);
    directoryView.setUint32(16, crc, true);
    directoryView.setUint32(20, data.length, true);
    directoryView.setUint32(24, data.length, true);
    directoryView.setUint16(28, nameBytes.length, true);
    directoryView.setUint16(30, 0, true);
    directoryView.setUint16(32, 0, true);
    directoryView.setUint16(34, 0, true);
    directoryView.setUint16(36, 0, true);
    directoryView.setUint32(38, 0, true);
    directoryView.setUint32(42, offset, true);
    directory.set(nameBytes, 46);
    central.push(directory);

    offset += local.length + data.length;
    if (offset > 0xffffffff) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_TOO_LARGE, "ZIP 超过 4 GiB 上限。");
    }
  }
  const centralSize = central.reduce((sum, item) => sum + item.length, 0);
  const end = new Uint8Array(22);
  const endView = new DataView(end.buffer);
  endView.setUint32(0, 0x06054b50, true);
  endView.setUint16(4, 0, true);
  endView.setUint16(6, 0, true);
  endView.setUint16(8, entries.length, true);
  endView.setUint16(10, entries.length, true);
  endView.setUint32(12, centralSize, true);
  endView.setUint32(16, offset, true);
  endView.setUint16(20, 0, true);
  return concat([...chunks, ...central, end], offset + centralSize + end.length);
}

async function inflateRaw(bytes) {
  if (typeof DecompressionStream !== "function") {
    throw new StorageError(
      STORAGE_ERROR_CODES.UNSUPPORTED_BROWSER,
      "当前浏览器不支持解压 deflate 条目（缺少 DecompressionStream）。",
    );
  }
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

export async function readZip(bytes, { maxEntries = 4096 } = {}) {
  if (!(bytes instanceof Uint8Array)) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "readZip 需要 Uint8Array。");
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let eocd = -1;
  const lowest = Math.max(0, bytes.length - 65557);
  for (let index = bytes.length - 22; index >= lowest; index -= 1) {
    if (view.getUint32(index, true) === 0x06054b50) { eocd = index; break; }
  }
  if (eocd < 0) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "不是有效的 ZIP：找不到中央目录结束记录。");
  }
  const entryCount = view.getUint16(eocd + 10, true);
  const centralSize = view.getUint32(eocd + 12, true);
  const centralOffset = view.getUint32(eocd + 16, true);
  if (entryCount === 0xffff || centralSize === 0xffffffff || centralOffset === 0xffffffff) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_TOO_LARGE, "不支持 ZIP64 项目包。");
  }
  if (entryCount > maxEntries) {
    throw new StorageError(
      STORAGE_ERROR_CODES.PACKAGE_TOO_LARGE, "项目包条目数 " + entryCount + " 超过上限 " + maxEntries + "。");
  }
  if (centralOffset + centralSize > bytes.length) {
    throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "项目包被截断：中央目录越界。");
  }
  const decoder = new TextDecoder();
  const entries = [];
  let cursor = centralOffset;
  for (let index = 0; index < entryCount; index += 1) {
    if (cursor + 46 > bytes.length || view.getUint32(cursor, true) !== 0x02014b50) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "中央目录第 " + index + " 项损坏。");
    }
    const flags = view.getUint16(cursor + 8, true);
    const method = view.getUint16(cursor + 10, true);
    const expectedCrc = view.getUint32(cursor + 16, true);
    const compressedSize = view.getUint32(cursor + 20, true);
    const uncompressedSize = view.getUint32(cursor + 24, true);
    const nameLength = view.getUint16(cursor + 28, true);
    const extraLength = view.getUint16(cursor + 30, true);
    const commentLength = view.getUint16(cursor + 32, true);
    const localOffset = view.getUint32(cursor + 42, true);
    const name = decoder.decode(bytes.subarray(cursor + 46, cursor + 46 + nameLength));
    if ((flags & 0x0001) !== 0) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "不支持加密条目：" + name);
    }
    if (localOffset + 30 > bytes.length || view.getUint32(localOffset, true) !== 0x04034b50) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "本地文件头损坏：" + name);
    }
    const localNameLength = view.getUint16(localOffset + 26, true);
    const localExtraLength = view.getUint16(localOffset + 28, true);
    const dataStart = localOffset + 30 + localNameLength + localExtraLength;
    if (dataStart + compressedSize > bytes.length) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "条目被截断：" + name);
    }
    const raw = bytes.subarray(dataStart, dataStart + compressedSize);
    let data;
    if (method === 0) data = raw.slice();
    else if (method === 8) data = await inflateRaw(raw);
    else {
      throw new StorageError(
        STORAGE_ERROR_CODES.PACKAGE_INVALID, "不支持的压缩方法 " + method + "：" + name);
    }
    if (data.length !== uncompressedSize) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "条目长度不符：" + name);
    }
    if (crc32(data) !== expectedCrc) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_INVALID, "条目校验和不符：" + name);
    }
    entries.push({ path: name, bytes: data });
    cursor += 46 + nameLength + extraLength + commentLength;
  }
  return entries;
}
