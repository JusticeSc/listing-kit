/**
 * Product V2 候选图片契约（Issue #27 主图裁剪派生 v2，计划 §9.13 扩展）。
 *
 * 职责：把「一次成功的生成」变成一条可复核的候选记录 + 一份内容寻址的字节；
 * 同 Shot 的本地白底纯裁剪变成一条显式派生候选（不伪造 Attempt、不 POST）。
 *  - 生成候选身份 = 来源 Attempt 的 action_id：同一 action 只允许一条生成候选；
 *    重复下载 / 重复保存是幂等跳过，不是新版本。
 *  - 派生候选身份 = 独立稳定 crop-<intent>：与父候选共享同 shot/action/task/sync，
 *    记录 derivation 血缘（父精确版本/sha/rect/实际尺寸/算法），provider 置空不冒充上游。
 *  - 记录只持有 asset_sha256 指针；字节本体在 assets 仓（内容寻址，同字节只存一份）。
 *  - 媒体信息（宽高）从 PNG 字节头解析——来自字节本身，不来自任何声明。
 *  - 本层是纯函数：不写存储、不发请求、不读时钟、不生成 id。
 *  - schema 1 历史生成记录继续可读（缺 origin/derivation 即视为 generation）。
 */

import { ATTEMPT_STATES } from "./attempt.js";
import { DOMAIN_ERROR_CODES, invalid } from "./errors.js";
import {
  DOMAIN_DOCUMENT_KINDS, canonicalJson, checkSchemaVersion, isIsoTimestamp, isNonEmptyString,
  isPlainObject, isSha256Hex, pushProblem,
} from "./shared.js";

export const CANDIDATE_SCHEMA_VERSION = 2;
export const CANDIDATE_SCHEMA_VERSION_GENERATION = 1;
export const CANDIDATE_DOCUMENT_KIND = DOMAIN_DOCUMENT_KINDS.candidate;

/** 正整数的未知输入收窄：Number.isInteger 本身不收窄 unknown，比较前必须显式判类型。
 * @param {unknown} value @returns {boolean} */
function isPositiveIntegerValue(value) {
  return typeof value === "number" && Number.isInteger(value) && value >= 1;
}

/** @param {unknown} value @returns {boolean} */
function isNonNegativeIntegerValue(value) {
  return typeof value === "number" && Number.isInteger(value) && value >= 0;
}

/** 主体占比（basis points）只可能是 1..10000（两个方向都不可能超过 100%）。
 * @param {unknown} value @returns {boolean} */
function isBasisPointsValue(value) {
  return isPositiveIntegerValue(value) && value <= 10000;
}

/** 网关只允许 PNG；字节上限是护栏，不是配额（配额由存储层报 QUOTA_EXCEEDED）。 */
export const CANDIDATE_MEDIA_TYPE = "image/png";
export const MAX_CANDIDATE_BYTES = 24 * 1024 * 1024;

const PNG_MAGIC = Object.freeze([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

/**
 * 从 PNG 字节头解析尺寸与像素特征（V2.5.1 起是唯一解析器）：
 * 宽高必须来自 IHDR 字节；颜色类型/位深在头部足够时一并读出；
 * 透明通道 = 颜色类型 4/6，或块结构允许时扫到 tRNS。
 * 签名 / IHDR / 宽高 / 颜色类型不合法一律 invalid，不猜；块结构不完整时透明判定返回 null（未知）。
 * @param {Uint8Array|ArrayBuffer} bytes
 * @returns {import("./type-contracts.js").PngHeader}
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
 * @param {Uint8Array|ArrayBuffer} bytes
 * @returns {{width: number, height: number}}
 */
export function parsePngDimensions(bytes) {
  const header = parsePngHeader(bytes);
  return { width: header.width, height: header.height };
}

/** 派生候选的唯一算法取值；本文件是唯一权威（generation 直接 import 这份，仓库里不存在第二份同名字面）。 */
export const CANDIDATE_CROP_ALGORITHM = /** @type {const} */ ("white-background-square-v1");
/** 派生候选身份前缀：crop-<intent>，intent 只允许小写字母数字与连字符。 */
export const CANDIDATE_DERIVED_ID_PATTERN = /^crop-[a-z0-9-]{1,48}$/;

/** 构造生成候选记录；来源必须是已成功且有结果依据的 Attempt（异步=task_id，同步=冻结 sync 身份）。
 * @param {{shotId?: unknown, attempt?: unknown, assetSha256?: unknown, byteSize?: unknown,
 *          width?: unknown, height?: unknown, at?: unknown}} [args]
 * @returns {import("./type-contracts.js").CandidateRecord}
 */
export function buildCandidateRecord({ shotId, attempt, assetSha256, byteSize, width, height, at } = {}) {
  if (!isNonEmptyString(shotId)) invalid("候选需要 shot_id。");
  if (!isPlainObject(attempt)) invalid("候选需要来源 Attempt。");
  if (attempt.state !== ATTEMPT_STATES.succeeded) invalid("来源 Attempt 不是 succeeded，不能建候选。");
  if (!isNonEmptyString(attempt.action_id)) invalid("来源 Attempt 缺少 action_id。");
  const frozen = isPlainObject(attempt.execution_identity)
    ? attempt.execution_identity : null;
  const sync = frozen !== null && frozen.sync === true;
  if (!sync && !isNonEmptyString(attempt.task_id)) {
    invalid("来源 Attempt 没有 task_id（也不是同步协议记录），不能建候选。");
  }
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
    // V2.R5.2：同步协议候选显式声明来源（task_id 允许为 null）；异步候选固定 false。
    sync: sync === true,
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
    origin: "generation",
    derivation: null,
  });
}

/** 派生裁剪矩形的几何合法性（整数、落在父尺寸内、主体包围盒完整在 rect 内）。
 * rect / subject_bbox 先验证是对象：未知载荷不能因为取字段而抛 TypeError。 */
function checkCropGeometry(problems, derivation) {
  if (!isPlainObject(derivation) || !isPlainObject(derivation.rect)
      || !isPlainObject(derivation.subject_bbox)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.derivation.rect",
      "派生必须给出裁剪矩形与主体包围盒对象。");
    return;
  }
  const rect = derivation.rect;
  const bbox = derivation.subject_bbox;
  const fields = ["x", "y", "width", "height"];
  for (const field of fields) {
    const sized = field === "width" || field === "height";
    const valid = (value) => (sized ? isPositiveIntegerValue(value) : isNonNegativeIntegerValue(value));
    if (!valid(rect[field])) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.derivation.rect." + field,
        "裁剪矩形 " + field + " 不合法。");
    }
    if (!valid(bbox[field])) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.derivation.subject_bbox." + field,
        "主体包围盒 " + field + " 不合法。");
    }
  }
  const sourceWidth = derivation.source_width;
  const sourceHeight = derivation.source_height;
  if (!isPositiveIntegerValue(sourceWidth) || !isPositiveIntegerValue(sourceHeight)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.derivation.source_width/height",
      "派生来源尺寸不合法。");
    return;
  }
  if (!isNonNegativeIntegerValue(rect.x) || !isNonNegativeIntegerValue(rect.y)
      || !isPositiveIntegerValue(rect.width) || !isPositiveIntegerValue(rect.height)
      || !isNonNegativeIntegerValue(bbox.x) || !isNonNegativeIntegerValue(bbox.y)
      || !isPositiveIntegerValue(bbox.width) || !isPositiveIntegerValue(bbox.height)) {
    // 字段问题已逐项报出；越界/包含比较只对完整整数几何有意义。
    return;
  }
  if (rect.x + rect.width <= sourceWidth && rect.y + rect.height <= sourceHeight) {
    if (!(rect.x <= bbox.x && rect.y <= bbox.y
        && rect.x + rect.width >= bbox.x + bbox.width
        && rect.y + rect.height >= bbox.y + bbox.height)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.derivation.subject_bbox",
        "主体包围盒必须完整落在裁剪矩形内。");
    }
  } else {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.derivation.rect",
      "裁剪矩形越界：必须完整落在来源尺寸内。");
  }
}

/** 构造派生候选记录（Issue #27 本地白底纯裁剪）；父候选必须是同一 Shot 的真实生成候选。
 * @param {{candidateId?: unknown, parent?: unknown, parentVersion?: unknown, assetSha256?: unknown,
 *          byteSize?: unknown, width?: unknown, height?: unknown, derivation?: unknown, at?: unknown}} [args]
 * @returns {import("./type-contracts.js").CandidateRecord}
 */
export function buildDerivedCandidateRecord({ candidateId, parent, parentVersion, assetSha256,
  byteSize, width, height, derivation, at } = {}) {
  if (typeof candidateId !== "string" || !CANDIDATE_DERIVED_ID_PATTERN.test(candidateId)) {
    invalid("派生候选身份必须是 crop-<intent>（小写字母数字与连字符）。");
  }
  if (!isPlainObject(parent) || candidateOriginOf(parent) !== "generation") {
    invalid("派生需要真实生成父候选（不接受派生再派生）。");
  }
  if (!isNonEmptyString(parent.shot_id) || !isNonEmptyString(parent.candidate_id)
      || !isNonEmptyString(parent.action_id) || !isSha256Hex(parent.asset_sha256)
      || !isPositiveIntegerValue(parent.width) || !isPositiveIntegerValue(parent.height)) {
    invalid("父候选缺少 shot/candidate/action 身份、字节身份或实际宽高。");
  }
  if (!isPositiveIntegerValue(parentVersion)) {
    invalid("派生需要父候选精确文档版本。");
  }
  if (!isPositiveIntegerValue(width) || !isPositiveIntegerValue(height)) {
    invalid("派生候选宽高不合法。");
  }
  if (!isPlainObject(derivation)) invalid("派生需要 derivation 血缘。");
  if (derivation.kind !== "crop" || derivation.algorithm !== CANDIDATE_CROP_ALGORITHM
      || derivation.resample !== "none" || derivation.pixel_preserving !== true) {
    invalid("派生血缘只接受 kind=crop 白底正方形无重采样裁剪。");
  }
  if (derivation.parent_candidate_id !== parent.candidate_id
      || derivation.parent_version !== parentVersion
      || derivation.parent_asset_sha256 !== parent.asset_sha256) {
    invalid("派生血缘的父身份（candidate/version/sha）必须与父候选一致。");
  }
  if (derivation.source_width !== parent.width || derivation.source_height !== parent.height) {
    invalid("派生血缘的来源尺寸必须等于父候选实际尺寸。");
  }
  if (!isPlainObject(derivation.rect) || !isPlainObject(derivation.subject_bbox)) {
    invalid("派生必须给出裁剪矩形与主体包围盒对象。");
  }
  if (derivation.rect.width !== width || derivation.rect.height !== height
      || derivation.rect.width !== derivation.rect.height) {
    invalid("派生宽高必须等于正方形裁剪矩形。");
  }
  if (!isBasisPointsValue(derivation.before_basis_points)
      || !isBasisPointsValue(derivation.after_basis_points)) {
    invalid("派生前后主体占比（basis points）必须是 1..10000 的整数。");
  }
  if (!isSha256Hex(assetSha256)) invalid("派生候选需要 64 位十六进制 asset_sha256。");
  if (assetSha256 === parent.asset_sha256) invalid("派生字节必须与父候选不同（裁剪必变字节）。");
  if (!isPositiveIntegerValue(byteSize) || byteSize > MAX_CANDIDATE_BYTES) {
    invalid("派生候选字节数不合法或超过护栏上限（" + MAX_CANDIDATE_BYTES + " 字节）。");
  }
  if (!isIsoTimestamp(at)) invalid("派生候选缺少 ISO 时间。");
  const problems = [];
  checkCropGeometry(problems, derivation);
  if (problems.length) invalid("派生裁剪几何不合法：" + problems[0].message);
  return Object.freeze({
    schema_version: CANDIDATE_SCHEMA_VERSION,
    candidate_id: candidateId,
    shot_id: parent.shot_id,
    action_id: parent.action_id,
    task_id: isNonEmptyString(parent.task_id) ? parent.task_id : null,
    sync: parent.sync === true,
    asset_sha256: assetSha256,
    media_type: CANDIDATE_MEDIA_TYPE,
    byte_size: byteSize,
    width: width,
    height: height,
    provider: { provider_id: null, model_id: null },
    created_at: at,
    origin: "derived",
    derivation: Object.freeze({
      kind: "crop",
      parent_candidate_id: parent.candidate_id,
      parent_version: parentVersion,
      parent_asset_sha256: parent.asset_sha256,
      source_width: derivation.source_width,
      source_height: derivation.source_height,
      rect: Object.freeze({ x: derivation.rect.x, y: derivation.rect.y,
        width: derivation.rect.width, height: derivation.rect.height }),
      subject_bbox: Object.freeze({ x: derivation.subject_bbox.x, y: derivation.subject_bbox.y,
        width: derivation.subject_bbox.width, height: derivation.subject_bbox.height }),
      algorithm: CANDIDATE_CROP_ALGORITHM,
      resample: "none",
      pixel_preserving: true,
      before_basis_points: derivation.before_basis_points,
      after_basis_points: derivation.after_basis_points,
    }),
  });
}

/** 候选来源投影：缺 origin 的 schema 1 历史记录视为 generation。 */
export function candidateOriginOf(candidate) {
  const record = candidate && isPlainObject(candidate.record) ? candidate.record : candidate;
  if (!isPlainObject(record)) return null;
  if (record.origin === "derived") return "derived";
  if (record.origin === undefined && record.schema_version === CANDIDATE_SCHEMA_VERSION_GENERATION) {
    return "generation";
  }
  if (record.origin === "generation") return "generation";
  return null;
}

/** 从候选链按 candidate_id 精确查找（生成/派生统一入口；review/导出按此找候选）。 */
export function candidateById(candidates, candidateId) {
  if (!Array.isArray(candidates) || !isNonEmptyString(candidateId)) return null;
  for (let index = candidates.length - 1; index >= 0; index -= 1) {
    const item = candidates[index];
    const record = item && isPlainObject(item.record) ? item.record : item;
    if (record && record.candidate_id === candidateId) return item;
  }
  return null;
}

/**
 * 派生候选与父生成候选的精确血缘一致性（存储保存与交付围栏共用这一份判据，不复制第二套）：
 * 同 Shot、同 action/task/sync、父 sha 与来源尺寸、输出正方形等于记录宽高。
 * 父文档版本本身由调用方按精确版本取出（记录里没有 version 字段可比）。
 * @param {unknown} candidate
 * @param {unknown} parent
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkDerivedParentLink(candidate, parent) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
  const problems = [];
  if (!isPlainObject(candidate) || candidateOriginOf(candidate) !== "derived"
      || !isPlainObject(candidate.derivation)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$",
      "只有派生候选需要父血缘复核。");
    return problems;
  }
  if (!isPlainObject(parent) || candidateOriginOf(parent) !== "generation") {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.parent",
      "派生父必须是真实生成候选（派生再派生不成立）。");
    return problems;
  }
  const derivation = candidate.derivation;
  const mismatch = (path, message) => pushProblem(
    problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, message);
  if (parent.candidate_id !== derivation.parent_candidate_id) {
    mismatch("$.derivation.parent_candidate_id", "父候选身份与血缘不一致。");
  }
  if (parent.shot_id !== candidate.shot_id) {
    mismatch("$.shot_id", "父候选必须与派生候选同属一张图。");
  }
  if (parent.action_id !== candidate.action_id) {
    mismatch("$.action_id", "派生必须复用父候选的原 action。");
  }
  if ((parent.task_id ?? null) !== (candidate.task_id ?? null)) {
    mismatch("$.task_id", "派生必须复用父候选的原 task。");
  }
  if ((parent.sync === true) !== (candidate.sync === true)) {
    mismatch("$.sync", "派生的同步标记必须与父候选一致。");
  }
  if (parent.asset_sha256 !== derivation.parent_asset_sha256) {
    mismatch("$.derivation.parent_asset_sha256", "父候选字节身份与血缘不一致。");
  }
  if (parent.width !== derivation.source_width || parent.height !== derivation.source_height) {
    mismatch("$.derivation.source_width/height", "父候选实际宽高与血缘不一致。");
  }
  if (candidate.candidate_id === parent.candidate_id) {
    mismatch("$.candidate_id", "派生身份必须独立于父候选。");
  }
  if (isPlainObject(derivation.rect)
      && (derivation.rect.width !== candidate.width || derivation.rect.height !== candidate.height)) {
    mismatch("$.derivation.rect", "派生记录宽高必须等于裁剪矩形。");
  }
  if (candidate.asset_sha256 === parent.asset_sha256) {
    mismatch("$.asset_sha256", "派生字节必须与父候选不同。");
  }
  return problems;
}

/**
 * 生成候选的幂等内容判据：同一候选身份指向同一份原件（字节身份、来源与尺寸一致）。
 * schema 1 历史记录与被重建的 schema 2 记录是同一份原件的两种封装；
 * schema_version / origin / derivation / created_at 这些封装字段不构成内容变化，
 * 因此重复保存应取回已有原件，而不是每次刷新都报「保存失败」或另写一版。
 * @param {unknown} existing
 * @param {unknown} candidate
 * @returns {boolean}
 */
export function candidateSameGenerationContent(existing, candidate) {
  if (!isPlainObject(existing) || !isPlainObject(candidate)) return false;
  if (candidateOriginOf(existing) !== "generation" || candidateOriginOf(candidate) !== "generation") {
    return false;
  }
  const keys = ["candidate_id", "shot_id", "action_id", "asset_sha256", "media_type",
    "byte_size", "width", "height"];
  if (!keys.every(key => (existing[key] ?? null) === (candidate[key] ?? null))) return false;
  if ((existing.task_id ?? null) !== (candidate.task_id ?? null)) return false;
  if (Boolean(existing.sync) !== Boolean(candidate.sync)) return false;
  const providerOf = (record) => (isPlainObject(record.provider)
    ? [record.provider.provider_id ?? null, record.provider.model_id ?? null]
    : [null, null]);
  return canonicalJson(providerOf(existing)) === canonicalJson(providerOf(candidate));
}

/** 记录形状检查；返回问题清单（空数组 = 合法）。schema 1 历史生成记录继续可读。
 * @param {unknown} record
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkCandidateRecord(record) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
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
  if (!isNonEmptyString(record.action_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.action_id", "缺少来源 action_id。");
  }
  const origin = candidateOriginOf(record);
  if (origin === null) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.origin",
      "origin 必须是 generation/derived（schema 1 历史缺省视为 generation）。");
  } else if (origin === "generation") {
    if (record.action_id !== record.candidate_id) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.action_id",
        "生成候选身份必须等于来源 Attempt 的 action_id。");
    }
    if (record.derivation !== null && record.derivation !== undefined) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.derivation",
        "生成候选不得携带 derivation 血缘。");
    }
    if (record.schema_version === CANDIDATE_SCHEMA_VERSION && record.origin !== "generation") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.origin",
        "schema 2 生成候选必须显式声明 origin=generation。");
    }
  } else {
    if (record.schema_version !== CANDIDATE_SCHEMA_VERSION) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.schema_version",
        "派生候选必须是 schema 2。");
    }
    if (typeof record.candidate_id !== "string"
        || !CANDIDATE_DERIVED_ID_PATTERN.test(record.candidate_id)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.candidate_id",
        "派生候选身份必须是 crop-<intent>。");
    }
    if (record.candidate_id === record.action_id) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.candidate_id",
        "派生候选身份必须独立于来源 action_id。");
    }
    const derivation = record.derivation;
    if (!isPlainObject(derivation)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.derivation",
        "派生候选必须携带 derivation 血缘。");
    } else {
      if (derivation.kind !== "crop") {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.derivation.kind",
          "派生只接受 kind=crop。");
      }
      if (!isNonEmptyString(derivation.parent_candidate_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.derivation.parent_candidate_id",
          "缺少父候选身份。");
      }
      if (!isPositiveIntegerValue(derivation.parent_version)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.derivation.parent_version",
          "缺少父候选精确版本。");
      }
      if (!isSha256Hex(derivation.parent_asset_sha256)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.derivation.parent_asset_sha256",
          "父候选字节身份必须是 64 位十六进制。");
      }
      if (derivation.parent_candidate_id === record.candidate_id) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.derivation.parent_candidate_id",
          "父候选不能是派生候选自身。");
      }
      if (derivation.algorithm !== CANDIDATE_CROP_ALGORITHM) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.derivation.algorithm",
          "派生算法必须是 " + CANDIDATE_CROP_ALGORITHM + "。");
      }
      if (derivation.resample !== "none" || derivation.pixel_preserving !== true) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.derivation.resample",
          "派生必须声明无重采样且像素保持。");
      }
      if (!isBasisPointsValue(derivation.before_basis_points)
          || !isBasisPointsValue(derivation.after_basis_points)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID,
          "$.derivation.before_basis_points/after_basis_points",
          "派生前后主体占比必须是 1..10000 的整数。");
      }
      if (!isPlainObject(derivation.rect) || !isPlainObject(derivation.subject_bbox)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.derivation.rect",
          "派生必须给出裁剪矩形与主体包围盒。");
      } else {
        checkCropGeometry(problems, derivation);
        if (derivation.rect.width !== record.width || derivation.rect.height !== record.height
            || derivation.rect.width !== derivation.rect.height) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.derivation.rect",
            "派生宽高必须等于正方形裁剪矩形。");
        }
      }
      if (record.asset_sha256 === derivation.parent_asset_sha256) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.asset_sha256",
          "派生字节必须与父候选不同。");
      }
    }
    if (isPlainObject(record.provider)
        && (record.provider.provider_id !== null || record.provider.model_id !== null)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.provider",
        "派生 provider 必须置空（本地修正不冒充上游模型）。");
    }
  }
  if (!isPlainObject(record.provider)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.provider",
      "缺少 provider 身份（生成候选来自 Attempt，派生候选显式置空）。");
  }
  if (isPlainObject(record.provider)
      && (typeof record.provider.provider_id !== "string"
        && record.provider.provider_id !== null
        && record.provider.provider_id !== undefined
        || typeof record.provider.model_id !== "string"
        && record.provider.model_id !== null
        && record.provider.model_id !== undefined)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.provider",
      "provider 身份只允许字符串或 null。");
  }
  if (!isNonEmptyString(record.task_id)) {
    // V2.R5.2 同步协议候选：task_id 允许为 null，但必须显式携带 sync === true；
    // 缺这个声明的记录维持历史判据（缺 task_id 即不符）。
    if (record.sync !== true || record.task_id !== null) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.task_id",
        "缺少来源 task_id（同步候选必须显式声明 sync 且 task_id 为 null）。");
    }
  }
  if (!isSha256Hex(record.asset_sha256)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.asset_sha256",
      "asset_sha256 必须是 64 位十六进制。");
  }
  if (record.media_type !== CANDIDATE_MEDIA_TYPE) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.media_type",
      "候选媒体类型必须是 " + CANDIDATE_MEDIA_TYPE + "。");
  }
  if (!isPositiveIntegerValue(record.byte_size)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.byte_size", "字节数不合法。");
  } else if (record.byte_size > MAX_CANDIDATE_BYTES) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.byte_size",
      "候选字节数超过护栏上限（" + MAX_CANDIDATE_BYTES + " 字节）。");
  }
  if (!isPositiveIntegerValue(record.width) || !isPositiveIntegerValue(record.height)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.width/height", "宽高不合法。");
  }
  if (!isIsoTimestamp(record.created_at)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.created_at", "缺少 ISO 时间。");
  }
  return problems;
}

/** 从候选链（同 Shot 的版本序列）找某个 action 的生成候选；幂等保存的判据。
 * 派生共享同 action，必须跳过：同一 action 的裁剪派生不得替代模型原候选。
 * @param {unknown} candidates
 * @param {unknown} actionId
 * @returns {unknown}
 */
export function candidateForAttempt(candidates, actionId) {
  if (!Array.isArray(candidates) || !isNonEmptyString(actionId)) return null;
  for (let index = candidates.length - 1; index >= 0; index -= 1) {
    const item = candidates[index];
    const record = item && isPlainObject(item.record) ? item.record : item;
    if (!record || record.action_id !== actionId) continue;
    if (candidateOriginOf(record) === "derived") continue;
    return item;
  }
  return null;
}

/** 候选与来源 Attempt 的一致性（预览 / 导出前的复核判据）。同步候选 task_id 允许为 null。
 * @param {unknown} candidate
 * @param {unknown} attempt
 * @returns {boolean}
 */
export function candidateMatchesAttempt(candidate, attempt) {
  const record = candidate && isPlainObject(candidate.record) ? candidate.record : candidate;
  if (!isPlainObject(record) || !isPlainObject(attempt)) return false;
  return record.action_id === attempt.action_id
    && record.task_id === attempt.task_id
    && Boolean(record.sync) === Boolean(attempt.execution_identity
      && attempt.execution_identity.sync)
    && record.shot_id === attempt.shot_id;
}

/**
 * 投影：这张图现在该不该（重新）保存候选。
 * V2.R5.2 同步协议：succeeded 且冻结身份声明 sync === true 时，task_id 允许为空，照样入库；
 * 其他任何「succeeded 无 task_id」形状仍拒绝（reason no_task_id）。
 * @param {{attempt?: unknown, candidates?: unknown}} [args]
 * @returns {import("./type-contracts.js").CandidateStoreDecision}
 */
export function candidateStoreDecision({ attempt, candidates } = {}) {
  if (!isPlainObject(attempt)) return { needed: false, reason: "no_attempt" };
  if (attempt.state !== ATTEMPT_STATES.succeeded) {
    return { needed: false, reason: "not_succeeded" };
  }
  if (!isNonEmptyString(attempt.task_id)) {
    const frozen = isPlainObject(attempt.execution_identity) ? attempt.execution_identity : null;
    if (!(frozen && frozen.sync === true && isNonEmptyString(attempt.action_id))) {
      return { needed: false, reason: "no_task_id" };
    }
  }
  const existing = candidateForAttempt(candidates || [], attempt.action_id);
  if (existing) return { needed: false, reason: "already_stored", candidate: existing };
  return { needed: true, reason: "unstored" };
}
