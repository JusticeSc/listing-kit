/**
 * Product V2 候选图片契约（V2.4.4，计划 §9.13）。
 *
 * @typedef {{
 *   schema_version: number, candidate_id: string, shot_id: string, action_id: string,
 *   task_id: string, asset_sha256: import("./shared.js").Sha256Hex, media_type: string,
 *   byte_size: number, width: number, height: number,
 *   provider: {provider_id: string|null, model_id: string|null},
 *   created_at: import("./shared.js").IsoTimestamp,
 * }} CandidateRecord
 * @typedef {Readonly<{width: number, height: number, bit_depth: number|null,
 *                     color_type: number|null, has_transparency: boolean|null}>} PngHeader
 * @typedef {Readonly<{version: number, record: CandidateRecord}>} CandidateChainEntry
 *
 * 职责：把「一次成功的生成」变成一条可复核的候选记录 + 一份内容寻址的字节。
 *  - 候选身份 = 来源 Attempt 的 action_id：同一 action 只允许一条候选记录；
 *    重复下载 / 重复保存是幂等跳过，不是新版本。
 *  - 记录只持有 asset_sha256 指针；字节本体在 assets 仓（内容寻址，同字节只存一份）。
 *  - 媒体信息（宽高）从 PNG 字节头解析——来自字节本身，不来自任何声明。
 *  - 本层是纯函数：不写存储、不发请求、不读时钟、不生成 id。
 */

import { ATTEMPT_STATES } from "./attempt.js";
import { DOMAIN_ERROR_CODES, invalid } from "./errors.js";
import {
  DOMAIN_DOCUMENT_KINDS, checkSchemaVersion, isIsoTimestamp, isNonEmptyString,
  isPlainObject, isSha256Hex, pushProblem,
} from "./shared.js";

export const CANDIDATE_SCHEMA_VERSION = 1;
export const CANDIDATE_DOCUMENT_KIND = DOMAIN_DOCUMENT_KINDS.candidate;

/** 网关只允许 PNG；字节上限是护栏，不是配额（配额由存储层报 QUOTA_EXCEEDED）。 */
export const CANDIDATE_MEDIA_TYPE = "image/png";
export const MAX_CANDIDATE_BYTES = 24 * 1024 * 1024;

const PNG_MAGIC = Object.freeze([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

/**
 * 从 PNG 字节头解析尺寸与像素特征（V2.5.1 起是唯一解析器）：
 * 宽高必须来自 IHDR 字节；颜色类型/位深在头部足够时一并读出；
 * 透明通道 = 颜色类型 4/6，或块结构允许时扫到 tRNS。
 * 签名 / IHDR / 宽高 / 颜色类型不合法一律 invalid，不猜；块结构不完整时透明判定返回 null（未知）。
 *
 * @param {Uint8Array | ArrayBuffer} bytes
 * @returns {PngHeader}
 */
export function parsePngHeader(bytes) {
  const view = bytes instanceof Uint8Array ? bytes
    : bytes instanceof ArrayBuffer ? new Uint8Array(bytes)
      : null;
  if (!view || view.byteLength < 24) invalid("PNG 字节不足 24 字节，无法解析宽高。");
  for (let index = 0; index < PNG_MAGIC.length; index += 1) {
    if (view[index] !== PNG_MAGIC[index]) invalid("字节不是 PNG（签名不符）。");
  }
  if (String.fromCharCode(view[12], view[13], view[14], view[15]) !== "IHDR") {
    invalid("PNG 第一个数据块不是 IHDR。");
  }
  const width = (view[16] << 24 | view[17] << 16 | view[18] << 8 | view[19]) >>> 0;
  const height = (view[20] << 24 | view[21] << 16 | view[22] << 8 | view[23]) >>> 0;
  if (width < 1 || height < 1) invalid("PNG 宽高不合法：" + width + "×" + height + "。");
  let bitDepth = null;
  let colorType = null;
  if (view.byteLength >= 26) {
    bitDepth = view[24];
    colorType = view[25];
    if (bitDepth < 1) invalid("PNG 位深不合法：" + bitDepth + "。");
    if ([0, 2, 3, 4, 6].indexOf(colorType) === -1) {
      invalid("PNG 颜色类型不合法：" + colorType + "。");
    }
  }
  return {
    width: width,
    height: height,
    bit_depth: bitDepth,
    color_type: colorType,
    has_transparency: pngTransparency(view, colorType),
  };
}

/** 透明通道判定：颜色类型 4/6 直接为真；否则按块结构找 tRNS；结构不完整返回 null（未知，不猜）。 */
function pngTransparency(view, colorType) {
  if (colorType === 4 || colorType === 6) return true;
  if (colorType === null) return null;
  let offset = 8;
  while (offset + 8 <= view.byteLength) {
    const length = (view[offset] << 24 | view[offset + 1] << 16
      | view[offset + 2] << 8 | view[offset + 3]) >>> 0;
    const type = String.fromCharCode(view[offset + 4], view[offset + 5],
      view[offset + 6], view[offset + 7]);
    if (offset + 12 + length > view.byteLength) return null;
    if (type === "tRNS") return true;
    if (type === "IDAT" || type === "IEND") return false;
    offset += length + 12;
  }
  return null;
}

/** 从 PNG 字节头解析宽高（V2.4.4 起的对外形状；解析权威是 parsePngHeader）。
 *
 * @param {Uint8Array | ArrayBuffer} bytes
 * @returns {{width: number, height: number}}
 */
export function parsePngDimensions(bytes) {
  const header = parsePngHeader(bytes);
  return { width: header.width, height: header.height };
}

/** 构造候选记录；来源必须是已成功且有 task id 的 Attempt，所有身份字段必填。
 *
 * @typedef {{attempt: import("./attempt.js").AttemptRecord}} BuildCandidateRecordInput
 * @param {{shotId: string, attempt: import("./attempt.js").AttemptRecord,
 *          assetSha256: import("./shared.js").Sha256Hex, byteSize: number,
 *          width: number, height: number,
 *          at: import("./shared.js").IsoTimestamp}} [input]
 * @returns {Readonly<CandidateRecord>}
 */
export function buildCandidateRecord({
  shotId, attempt, assetSha256, byteSize, width, height, at,
} = {}) {
  if (!isNonEmptyString(shotId)) invalid("候选需要 shot_id。");
  if (!isPlainObject(attempt)) invalid("候选需要来源 Attempt。");
  if (attempt.state !== ATTEMPT_STATES.succeeded) invalid("来源 Attempt 不是 succeeded，不能建候选。");
  if (!isNonEmptyString(attempt.action_id)) invalid("来源 Attempt 缺少 action_id。");
  if (!isNonEmptyString(attempt.task_id)) invalid("来源 Attempt 缺少 task_id，不能建候选。");
  if (!isSha256Hex(assetSha256)) invalid("候选需要 64 位十六进制 asset_sha256。");
  if (!Number.isInteger(byteSize) || byteSize < 1) invalid("候选字节数不合法。");
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1) {
    invalid("候选宽高不合法。");
  }
  if (!isIsoTimestamp(at)) invalid("候选缺少 ISO 时间。");
  return Object.freeze({
    schema_version: CANDIDATE_SCHEMA_VERSION,
    candidate_id: attempt.action_id,
    shot_id: shotId,
    action_id: attempt.action_id,
    task_id: attempt.task_id,
    asset_sha256: assetSha256,
    media_type: CANDIDATE_MEDIA_TYPE,
    byte_size: byteSize,
    width: width,
    height: height,
    provider: {
      provider_id: attempt.provider ? attempt.provider.provider_id || null : null,
      model_id: attempt.provider ? attempt.provider.model_id || null : null,
    },
    created_at: at,
  });
}

/** 记录形状检查；返回问题清单（空数组 = 合法）。
 *
 * @param {unknown} record
 * @returns {import("./shared.js").DomainProblem[]}
 */
export function checkCandidateRecord(record) {
  const problems = [];
  if (!isPlainObject(record)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "候选记录必须是对象。");
    return problems;
  }
  checkSchemaVersion(record, CANDIDATE_SCHEMA_VERSION, problems, "$");
  if (!isNonEmptyString(record.candidate_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.candidate_id", "缺少 candidate_id。");
  }
  if (!isNonEmptyString(record.shot_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shot_id", "缺少 shot_id。");
  }
  if (!isNonEmptyString(record.action_id) || record.action_id !== record.candidate_id) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.action_id",
      "候选身份必须等于来源 Attempt 的 action_id。");
  }
  if (!isNonEmptyString(record.task_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.task_id", "缺少来源 task_id。");
  }
  if (!isSha256Hex(record.asset_sha256)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.asset_sha256",
      "asset_sha256 必须是 64 位十六进制。");
  }
  if (record.media_type !== CANDIDATE_MEDIA_TYPE) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.media_type",
      "候选媒体类型必须是 " + CANDIDATE_MEDIA_TYPE + "。");
  }
  if (!Number.isInteger(record.byte_size) || record.byte_size < 1) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.byte_size", "字节数不合法。");
  }
  if (!Number.isInteger(record.width) || !Number.isInteger(record.height)
      || record.width < 1 || record.height < 1) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.width/height", "宽高不合法。");
  }
  if (!isIsoTimestamp(record.created_at)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.created_at", "缺少 ISO 时间。");
  }
  return problems;
}

/** 从候选链（同 Shot 的版本序列）找某个 action 的候选；幂等保存的判据。
 *
 * @param {unknown} candidates
 * @param {unknown} actionId
 * @returns {CandidateChainEntry | CandidateRecord | null}
 */
export function candidateForAttempt(candidates, actionId) {
  if (!Array.isArray(candidates) || !isNonEmptyString(actionId)) return null;
  for (let index = candidates.length - 1; index >= 0; index -= 1) {
    const item = candidates[index];
    const record = item && isPlainObject(item.record) ? item.record : item;
    if (record && record.action_id === actionId) return item;
  }
  return null;
}

/** 候选与来源 Attempt 的一致性（预览 / 导出前的复核判据）。
 *
 * @param {unknown} candidate
 * @param {unknown} attempt
 * @returns {boolean}
 */
export function candidateMatchesAttempt(candidate, attempt) {
  const record = candidate && isPlainObject(candidate.record) ? candidate.record : candidate;
  if (!isPlainObject(record) || !isPlainObject(attempt)) return false;
  return record.action_id === attempt.action_id
    && record.task_id === attempt.task_id
    && record.shot_id === attempt.shot_id;
}

/** 投影：这张图现在该不该（重新）保存候选。
 *
 * @typedef {{needed: boolean, reason: string, candidate?: CandidateChainEntry | CandidateRecord}} CandidateStoreDecision
 * @param {{attempt?: unknown, candidates?: unknown}} [input]
 * @returns {CandidateStoreDecision}
 */
export function candidateStoreDecision({ attempt, candidates } = {}) {
  if (!isPlainObject(attempt)) return { needed: false, reason: "no_attempt" };
  if (attempt.state !== ATTEMPT_STATES.succeeded) {
    return { needed: false, reason: "not_succeeded" };
  }
  if (!isNonEmptyString(attempt.task_id)) {
    return { needed: false, reason: "no_task_id" };
  }
  const existing = candidateForAttempt(candidates || [], attempt.action_id);
  if (existing) return { needed: false, reason: "already_stored", candidate: existing };
  return { needed: true, reason: "unstored" };
}
