/**
 * 白底主图的无重采样方形裁剪（Issue #27）。
 *
 * 仅接受 RGB8、非隔行、不透明 PNG；浏览器解码后 1:1 取像素，再编码为 RGB PNG。
 * 原件只读保留；输出不携带原 PNG 的附属元数据，来源由派生候选记录保存。
 * “像素保持”指保留解码像素，不承诺压缩字节或元数据相同。
 *
 * RGB 全 ≥250 视为背景，其余像素保守包围。仅在干净像素圈分隔的前提下，
 * 允许剥离最多 8px 的边缘噪线，输出限定在剥离后的区域；排除量超过画面 2% 或主体贴边时拒绝。
 * 默认目标 86%，为至少 85% 的验收留软边界测量余量；边长向下取整避免略低于目标。
 * 输出必须 ≥1000px、完整包含前景且确实缩小画布。检测不判断商品事实，须人工看预览。
 *
 * 本模块不写库、不联网、不采用。cropMainPng 使用成熟浏览器解码；
 * planMainCrop 与 encodeOpaquePng 是其实际使用的纯计算内层。
 */

import { MAX_CANDIDATE_BYTES, parsePngHeader } from "./domain/candidate.js";
import { invalid } from "./domain/errors.js";
import { crc32 } from "./storage/zip.js";
import { zlibSync } from "./vendor/fflate.browser.js";

export type CropRect = {
  x: number;
  y: number;
  width: number;
  height: number;
};

/**
 * 主图裁剪计划：口径全部可复算。
 * - before_basis_points = 主体最长边 / 原图最长边 ×10000（方图即边长比）；
 * - after_basis_points = 主体最长边 / 裁剪边长 ×10000；
 * - subject_bbox 是像素闭区间包围盒（width = maxX-minX+1），rect 是正方形裁剪区。
 */
export type MainCropPlan = {
  rect: CropRect;
  subject_bbox: CropRect;
  source_width: number;
  source_height: number;
  before_basis_points: number;
  after_basis_points: number;
  target_percent: number;
};


/** 默认构图目标，为原 85% 验收线保留 1 个百分点的测量余量。 */
export const DEFAULT_MAIN_CROP_TARGET_PERCENT = 86;

/** 主图裁剪边长下限（平台规则 ≥1000 PASS；1600 只是推荐，不在这里卡）。 */
export const MIN_MAIN_CROP_SIDE = 1000;

/** 白底判定：R/G/B 全 ≥250 才算背景，其余一律当前景（保守口径）。 */
export const WHITE_THRESHOLD = 250;

/** 边缘剥离上限：实测真图 ≤3px 即稳，8px 留余量且仍不足 1000 边长的 1%。 */
const MAX_EDGE_PEEL_PX = 8;

/** 被排除边缘非白占画面的上限：实测真图约 0.15%–0.3%，超 2% 判为非噪线。 */
const MAX_EDGE_DIRT_FRACTION = 0.02;

type ForegroundScan = {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
  count: number;
};

/** 裁剪实际用到的最小 2D 上下文面（HTML/Offscreen 两种 Canvas 都满足）。 */
type CropCanvasContext = {
  drawImage(image: CanvasImageSource, dx: number, dy: number): void;
  getImageData(sx: number, sy: number, sw: number, sh: number): ImageData;
};

function checkTargetPercent(targetPercent: number): number {
  if (typeof targetPercent !== "number" || !Number.isFinite(targetPercent)
    || targetPercent <= 0 || targetPercent >= 100) {
    invalid("目标主体占比必须在 (0,100) 内，实际 " + String(targetPercent) + "，拒绝裁剪。");
  }
  return targetPercent;
}

/**
 * 在给定闭区间内扫前景包围盒并计数；checkAlpha 为真时顺带要求全区不透明。
 * 返回 null 表示区间内全是背景。
 */
function scanForeground(
  pixels: Uint8Array | Uint8ClampedArray,
  strideWidth: number,
  x0: number,
  x1: number,
  y0: number,
  y1: number,
  checkAlpha: boolean,
): ForegroundScan | null {
  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  let count = 0;
  for (let y = y0; y <= y1; y += 1) {
    const rowBase = y * strideWidth * 4;
    for (let x = x0; x <= x1; x += 1) {
      const o = rowBase + x * 4;
      if (checkAlpha && pixels[o + 3] !== 255) {
        invalid("输入在 (" + x + "," + y + ") 有非不透明像素（alpha=" + pixels[o + 3]
          + "），不满足白底不透明主图前提，拒绝裁剪。");
      }
      if (pixels[o] >= WHITE_THRESHOLD && pixels[o + 1] >= WHITE_THRESHOLD
        && pixels[o + 2] >= WHITE_THRESHOLD) {
        continue;
      }
      count += 1;
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    }
  }
  if (count === 0) return null;
  return { minX, maxX, minY, maxY, count };
}

/**
 * 纯几何：从 RGBA 解码像素规划主图正方形裁剪（不碰 DOM，cropMainPng 的真实内层）。
 * 拒绝一律抛 CONTRACT_INVALID 并说明原因，不猜、不吞主体、不静默让步。
 */
export function planMainCrop(
  pixels: Uint8Array | Uint8ClampedArray,
  width: number,
  height: number,
  targetPercent: number = DEFAULT_MAIN_CROP_TARGET_PERCENT,
): MainCropPlan {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1) {
    invalid("裁剪输入尺寸不合法：" + String(width) + "×" + String(height) + "。");
  }
  if (!(pixels instanceof Uint8Array) && !(pixels instanceof Uint8ClampedArray)) {
    invalid("planMainCrop 需要 Uint8Array/Uint8ClampedArray 的 RGBA 像素。");
  }
  if (pixels.length !== width * height * 4) {
    invalid("像素缓冲长度 " + pixels.length + " 与尺寸 " + width + "×" + height + "×4 不符。");
  }
  const target = checkTargetPercent(targetPercent);
  const full = scanForeground(pixels, width, 0, width - 1, 0, height - 1, true);
  if (full === null) {
    invalid("画面全白/全底色，未检测到主体，不做裁剪。");
  }
  let subject: ForegroundScan = full;
  let inset = 0;
  const touchesFrame = full.minX === 0 || full.maxX === width - 1
    || full.minY === 0 || full.maxY === height - 1;
  if (touchesFrame) {
    let settled: ForegroundScan | null = null;
    for (let margin = 1; margin <= MAX_EDGE_PEEL_PX; margin += 1) {
      if (margin * 2 >= Math.min(width, height)) {
        invalid("画面过小，无法在保留主体的同时剥离边缘像素，拒绝裁剪。");
      }
      const inner = scanForeground(pixels, width, margin, width - 1 - margin,
        margin, height - 1 - margin, false);
      if (inner === null) {
        invalid("仅边缘有一圈零散像素，框内无有效主体，拒绝裁剪。");
      } else if (inner.minX > margin && inner.maxX < width - 1 - margin
        && inner.minY > margin && inner.maxY < height - 1 - margin) {
        settled = inner;
        inset = margin;
        break;
      }
    }
    if (settled === null) {
      invalid("前景接触画面边缘且向内延伸超出 " + MAX_EDGE_PEEL_PX
        + "px（或背景整体非白），无法区分噪线与贴边主体，拒绝裁剪。");
    }
    const ringCount = full.count - settled.count;
    if (ringCount / (width * height) > MAX_EDGE_DIRT_FRACTION) {
      invalid("被排除的边缘非白区域过大（" + ringCount + "px），无法判定为噪线，拒绝裁剪。");
    }
    subject = settled;
  }
  const bboxWidth = subject.maxX - subject.minX + 1;
  const bboxHeight = subject.maxY - subject.minY + 1;
  const subjectLong = Math.max(bboxWidth, bboxHeight);
  const side = Math.floor((subjectLong * 100) / target);
  if (side < MIN_MAIN_CROP_SIDE) {
    invalid("裁剪边长 " + side + " 小于主图下限 " + MIN_MAIN_CROP_SIDE + "，拒绝裁剪。");
  }
  const shortSide = Math.min(width, height) - inset * 2;
  if (side > shortSide) {
    invalid("目标边长 " + side + " 超出白底有效短边 " + shortSide + "，不能重新纳入已剥离的外沿。");
  }
  if (side === width && side === height) {
    invalid("目标边长等于原图尺寸，裁剪无益，拒绝裁剪。");
  }
  const cx = (subject.minX + subject.maxX) / 2;
  const cy = (subject.minY + subject.maxY) / 2;
  const x = Math.min(Math.max(Math.round(cx - side / 2), inset), width - inset - side);
  const y = Math.min(Math.max(Math.round(cy - side / 2), inset), height - inset - side);
  if (!(x <= subject.minX && x + side - 1 >= subject.maxX
    && y <= subject.minY && y + side - 1 >= subject.maxY)) {
    invalid("裁剪矩形无法在画布内完整留住主体，拒绝裁剪。");
  }
  const subjectBbox: CropRect = { x: subject.minX, y: subject.minY, width: bboxWidth, height: bboxHeight };
  const rect: CropRect = { x, y, width: side, height: side };
  const plan: MainCropPlan = {
    rect,
    subject_bbox: subjectBbox,
    source_width: width,
    source_height: height,
    before_basis_points: Math.round((subjectLong * 10000) / Math.max(width, height)),
    after_basis_points: Math.round((subjectLong * 10000) / side),
    target_percent: target,
  };
  Object.freeze(subjectBbox);
  Object.freeze(rect);
  Object.freeze(plan);
  return plan;
}

function be32(value: number): Uint8Array {
  return new Uint8Array([(value >>> 24) & 0xff, (value >>> 16) & 0xff, (value >>> 8) & 0xff, value & 0xff]);
}

/** PNG 数据块：长度 + 类型 + 数据 + 类型与数据的 CRC32（复用 storage/zip.js 的 crc32）。 */
function pngChunk(type: string, data: Uint8Array): Uint8Array {
  const out = new Uint8Array(12 + data.length);
  out.set(be32(data.length), 0);
  for (let i = 0; i < 4; i += 1) out[4 + i] = type.charCodeAt(i);
  out.set(data, 8);
  out.set(be32(crc32(out.subarray(4, 8 + data.length))), 8 + data.length);
  return out;
}

/**
 * 纯编码：RGB 像素 → RGB8 非隔行不透明 PNG（filter 0 单 IDAT，无损可逆）。
 * 压缩复用 vendored fflate 的 zlibSync，不自研、不新增依赖，不改写输入。
 */
export function encodeOpaquePng(rgb: Uint8Array, width: number, height: number): Uint8Array<ArrayBuffer> {
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1) {
    invalid("编码输入尺寸不合法：" + String(width) + "×" + String(height) + "。");
  }
  if (!(rgb instanceof Uint8Array)) {
    invalid("encodeOpaquePng 需要 Uint8Array 的 RGB 像素（无 alpha 通道）。");
  }
  if (rgb.length !== width * height * 3) {
    invalid("RGB 缓冲长度 " + rgb.length + " 与尺寸 " + width + "×" + height + "×3 不符。");
  }
  const stride = width * 3;
  const raw = new Uint8Array(height * (stride + 1));
  for (let y = 0; y < height; y += 1) {
    const dst = y * (stride + 1);
    raw[dst] = 0;
    raw.set(rgb.subarray(y * stride, (y + 1) * stride), dst + 1);
  }
  const compressed = zlibSync(raw);
  const ihdrData = new Uint8Array(13);
  ihdrData.set(be32(width), 0);
  ihdrData.set(be32(height), 4);
  ihdrData.set([8, 2, 0, 0, 0], 8);
  const ihdr = pngChunk("IHDR", ihdrData);
  const idat = pngChunk("IDAT", compressed);
  const iend = pngChunk("IEND", new Uint8Array(0));
  const out = new Uint8Array(8 + ihdr.length + idat.length + iend.length);
  out.set([137, 80, 78, 71, 13, 10, 26, 10], 0);
  out.set(ihdr, 8);
  out.set(idat, 8 + ihdr.length);
  out.set(iend, 8 + ihdr.length + idat.length);
  return out;
}

/** 取一块给定尺寸的 2D 上下文：优先 document Canvas，退到 OffscreenCanvas；都没有就拒绝。 */
function cropCanvasContext(width: number, height: number): CropCanvasContext {
  if (typeof document !== "undefined") {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (ctx === null) {
      invalid("取不到 Canvas 2D 上下文，无法解码，拒绝裁剪。");
    }
    return ctx;
  }
  if (typeof OffscreenCanvas === "function") {
    const offscreen = new OffscreenCanvas(width, height);
    const offCtx = offscreen.getContext("2d", { willReadFrequently: true });
    if (offCtx === null) {
      invalid("取不到 OffscreenCanvas 2D 上下文，无法解码，拒绝裁剪。");
    }
    return offCtx;
  }
  invalid("当前环境没有 document/OffscreenCanvas，无法解码 PNG，拒绝裁剪。");
}

/**
 * 主入口：RGB8 白底主图 PNG → 独立裁剪字节 + 可复核计划。
 * 输入先过 parsePngHeader（RGB8/非隔行/无透明任一不满足都拒绝），再经浏览器解码
 * 1:1 取像素（无重采样），区域 RGB 原样拷贝后无损编码；全程不改写 source。
 */
export async function cropMainPng(
  source: Uint8Array,
  targetPercent: number = DEFAULT_MAIN_CROP_TARGET_PERCENT,
): Promise<{ bytes: Uint8Array<ArrayBuffer>; plan: MainCropPlan }> {
  if (!(source instanceof Uint8Array)) {
    invalid("cropMainPng 需要 Uint8Array 输入。");
  }
  checkTargetPercent(targetPercent);
  if (source.length < 29) {
    invalid("PNG 字节不足 29 字节，无法读出 IHDR（含隔行标志），拒绝裁剪。");
  }
  const header = parsePngHeader(source);
  if (header.bit_depth !== 8 || header.color_type !== 2) {
    invalid("只支持 RGB8 PNG（bit_depth=8/color_type=2），实际 bit_depth="
      + String(header.bit_depth) + "/color_type=" + String(header.color_type)
      + "，不降位深、不静默改色，拒绝裁剪。");
  }
  if (header.has_transparency !== false) {
    invalid(header.has_transparency === true
      ? "输入含透明通道（alpha 颜色类型或 tRNS），只做不透明白底裁剪，拒绝裁剪。"
      : "PNG 块结构不完整，透明通道无法判定（未知不猜），拒绝裁剪。");
  }
  // IHDR 数据：宽(16-19) 高(20-23) 位深(24) 颜色类型(25) 压缩(26) 滤波(27) 隔行(28)。
  if (source[26] !== 0 || source[27] !== 0) {
    invalid("不支持的 PNG 压缩/滤波方式（仅支持 0/0），拒绝裁剪。");
  }
  if (source[28] !== 0) {
    invalid("不支持隔行（interlace）PNG，拒绝裁剪。");
  }
  const width = header.width;
  const height = header.height;
  if (source.byteLength > MAX_CANDIDATE_BYTES || width * height > 16 * 1024 * 1024) {
    invalid("输入字节或解码像素超过本地护栏，拒绝裁剪。");
  }
  if (typeof createImageBitmap !== "function") {
    invalid("当前环境不支持 createImageBitmap（需要浏览器环境解码 PNG），拒绝裁剪。");
  }
  const copy = new Uint8Array(source);
  const blob = new Blob([copy.buffer], { type: "image/png" });
  let bitmap: ImageBitmap | null = null;
  try {
    bitmap = await createImageBitmap(blob);
  } catch (error: unknown) {
    invalid("浏览器解码 PNG 失败："
      + (error instanceof Error && error.message ? error.message : String(error)));
  }
  if (bitmap === null) {
    invalid("浏览器解码 PNG 失败：未返回位图，拒绝裁剪。");
  }
  try {
    if (bitmap.width !== width || bitmap.height !== height) {
      invalid("浏览器解码尺寸 " + bitmap.width + "×" + bitmap.height
        + " 与 PNG 头 " + width + "×" + height + " 不一致，拒绝裁剪。");
    }
    const ctx = cropCanvasContext(width, height);
    ctx.drawImage(bitmap, 0, 0);
    const decoded = ctx.getImageData(0, 0, width, height).data;
    const plan = planMainCrop(decoded, width, height, targetPercent);
    const side = plan.rect.width;
    const rgb = new Uint8Array(side * side * 3);
    for (let row = 0; row < side; row += 1) {
      const srcBase = ((plan.rect.y + row) * width + plan.rect.x) * 4;
      const dstBase = row * side * 3;
      for (let col = 0; col < side; col += 1) {
        const s = srcBase + col * 4;
        const d = dstBase + col * 3;
        rgb[d] = decoded[s];
        rgb[d + 1] = decoded[s + 1];
        rgb[d + 2] = decoded[s + 2];
      }
    }
    return { bytes: encodeOpaquePng(rgb, side, side), plan };
  } finally {
    bitmap.close();
  }
}
