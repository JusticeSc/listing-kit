/**
 * V2 主图纯裁剪契约测试（Node 原生进程，非 Mock；Issue #27）。
 *
 * 只测公开纯行为：
 * - planMainCrop：至少达到目标占比、完整保留主体、原像素不变；多层边缘噪线剥离
 *   （2px 整列噪线 + 孤立点噪，去 1px 不足、逐层到稳）、贴边主体与过大边缘区拒绝、
 *   各类明确拒绝（全白/非白底/过小/超画布/非法目标与输入/非不透明）；
 * - encodeOpaquePng：输出块结构合法（自有 CRC 表独立验块）、Node 内建 zlib 独立解压后
 *   RGB 行逐字节相等、输出能过领域 parsePngHeader 且判为不透明 RGB8。
 * 不测源文本/默认值/转发；cropMainPng 需要浏览器解码，由隔离 Chrome 验证覆盖，不在这里测。
 *
 * 直接运行：node --test evals/product-v2/node/main-crop-contract.test.mjs
 */

import { inflateSync } from "node:zlib";
import {
  encodeOpaquePng,
  planMainCrop,
} from "../../../build/frontend-node/app/product_v2/image-crop.js";
import { parsePngHeader } from "../../../build/frontend-node/app/product_v2/domain/index.js";
import { expect, expectCode } from "./harness-core.mjs";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

function whiteRgba(width, height) {
  const pixels = new Uint8ClampedArray(width * height * 4);
  pixels.fill(255);
  return pixels;
}

function paint(pixels, width, x0, y0, x1, y1, r, g, b) {
  for (let y = y0; y <= y1; y += 1) {
    for (let x = x0; x <= x1; x += 1) {
      const o = (y * width + x) * 4;
      pixels[o] = r;
      pixels[o + 1] = g;
      pixels[o + 2] = b;
    }
  }
}

function subject1200() {
  const pixels = whiteRgba(1200, 1200);
  paint(pixels, 1200, 150, 200, 1049, 1099, 20, 20, 20);
  return pixels;
}

function expectContains(rect, subject, label) {
  expect(rect.x <= subject.x && rect.y <= subject.y
    && rect.x + rect.width >= subject.x + subject.width
    && rect.y + rect.height >= subject.y + subject.height,
    label + "：裁剪不得截断主体");
}

function snapshot(bytes) {
  return bytes.slice();
}

function expectUnchanged(before, after, label) {
  expect(after.length === before.length, label + "：长度被改写");
  for (let i = 0; i < before.length; i += 1) {
    if (after[i] !== before[i]) {
      throw new Error(label + "：第 " + i + " 字节被改写（" + before[i] + "→" + after[i] + "）");
    }
  }
}

function expectRect(actual, x, y, width, height, label) {
  expect(actual.x === x && actual.y === y && actual.width === width && actual.height === height,
    label + "：期望 {" + x + "," + y + "," + width + "," + height + "}，实际 {"
    + actual.x + "," + actual.y + "," + actual.width + "," + actual.height + "}");
}
test("M1", "几何：至少达到85%且完整保留主体，取整不能略低于验收线", async () => {
  const pixels = subject1200();
  const before = snapshot(pixels);
  const plan = planMainCrop(pixels, 1200, 1200, 85);
  expectUnchanged(before, pixels, "planMainCrop 输入");
  expectRect(plan.subject_bbox, 150, 200, 900, 900, "subject_bbox");
  expect(plan.before_basis_points === 7500,
    "before 必须是 7500（900/1200），实际 " + plan.before_basis_points);
  expect(plan.after_basis_points >= 8500, "真实裁剪后占比不能略低于85%");
  expect(plan.subject_bbox.height / plan.rect.height >= 0.85,
    "不能只把显示基点四舍五入到85%，实际几何也必须达到门槛");
  expect(plan.rect.width >= 1000, "输出边长必须 ≥1000");
  expectContains(plan.rect, plan.subject_bbox, "M1");
  return { rect: plan.rect };
});

test("M2", "边界：真图同构多层噪线逐层剥离到稳，口径与干净图完全一致；贴边与相连拒绝", async () => {
  const noisy = subject1200();
  paint(noisy, 1200, 0, 0, 1, 1199, 120, 120, 120);
  paint(noisy, 1200, 1198, 0, 1199, 1199, 120, 120, 120);
  paint(noisy, 1200, 1197, 14, 1197, 78, 249, 249, 250);
  const cleanPlan = planMainCrop(noisy, 1200, 1200, 85);
  expectRect(cleanPlan.subject_bbox, 150, 200, 900, 900, "噪线排除后 bbox");
  expect(cleanPlan.subject_bbox.height / cleanPlan.rect.height >= 0.85,
    "去除噪线后的实际主体占比必须至少85%");

  const touching = whiteRgba(1200, 1200);
  paint(touching, 1200, 0, 200, 899, 1099, 20, 20, 20);
  await expectCode(() => planMainCrop(touching, 1200, 1200, 85), "CONTRACT_INVALID", "真实贴边");

  const adjacent = whiteRgba(1200, 1200);
  paint(adjacent, 1200, 0, 0, 0, 1199, 120, 120, 120);
  paint(adjacent, 1200, 1, 200, 900, 1099, 20, 20, 20);
  await expectCode(() => planMainCrop(adjacent, 1200, 1200, 85),
    "CONTRACT_INVALID", "主体与外沿噪线相邻无法区分");

  const touchingNoise = whiteRgba(1200, 1200);
  paint(touchingNoise, 1200, 0, 200, 899, 1099, 20, 20, 20);
  paint(touchingNoise, 1200, 0, 0, 1199, 0, 120, 120, 120);
  await expectCode(() => planMainCrop(touchingNoise, 1200, 1200, 85),
    "CONTRACT_INVALID", "贴边主体叠加噪线");

  const wideDirt = whiteRgba(1200, 1200);
  paint(wideDirt, 1200, 0, 0, 1199, 7, 120, 120, 120);
  paint(wideDirt, 1200, 0, 1192, 1199, 1199, 120, 120, 120);
  paint(wideDirt, 1200, 0, 0, 7, 1199, 120, 120, 120);
  paint(wideDirt, 1200, 1192, 0, 1199, 1199, 120, 120, 120);
  paint(wideDirt, 1200, 100, 100, 999, 999, 20, 20, 20);
  await expectCode(() => planMainCrop(wideDirt, 1200, 1200, 85),
    "CONTRACT_INVALID", "边缘非白过大（第二件商品类）");
  return { probed: 5 };
});

test("M3", "拒绝：全白无主体 / 非白底 / 过小输出 / 超画布 / 非法目标与输入 / 非不透明", async () => {
  await expectCode(() => planMainCrop(whiteRgba(1200, 1200), 1200, 1200, 85),
    "CONTRACT_INVALID", "全白无主体");
  const gray = whiteRgba(1200, 1200);
  paint(gray, 1200, 0, 0, 1199, 1199, 240, 240, 240);
  await expectCode(() => planMainCrop(gray, 1200, 1200, 85), "CONTRACT_INVALID", "非白底");
  const tiny = whiteRgba(1200, 1200);
  paint(tiny, 1200, 550, 550, 649, 649, 20, 20, 20);
  await expectCode(() => planMainCrop(tiny, 1200, 1200, 85),
    "CONTRACT_INVALID", "输出边长不足 1000");
  const huge = whiteRgba(1200, 1200);
  paint(huge, 1200, 25, 25, 1174, 1174, 20, 20, 20);
  await expectCode(() => planMainCrop(huge, 1200, 1200, 85),
    "CONTRACT_INVALID", "目标边长超出画布");
  const good = subject1200();
  for (const bad of [0, 100, Number.NaN, Number.POSITIVE_INFINITY]) {
    await expectCode(() => planMainCrop(good, 1200, 1200, bad),
      "CONTRACT_INVALID", "非法目标 " + String(bad));
  }
  await expectCode(() => planMainCrop(new Uint8ClampedArray(16), 1200, 1200, 85),
    "CONTRACT_INVALID", "缓冲长度与尺寸不符");
  await expectCode(() => planMainCrop(good, 1200.5, 1200, 85),
    "CONTRACT_INVALID", "非整数宽");
  const translucent = subject1200();
  translucent[3] = 0;
  await expectCode(() => planMainCrop(translucent, 1200, 1200, 85),
    "CONTRACT_INVALID", "非不透明像素");
  return { probed: 11 };
});

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) {
      c = (c & 1) !== 0 ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
    }
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32Local(bytes) {
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i += 1) {
    crc = CRC_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function be32(bytes, offset) {
  return ((bytes[offset] << 24) | (bytes[offset + 1] << 16)
    | (bytes[offset + 2] << 8) | bytes[offset + 3]) >>> 0;
}

test("M4", "编码：块序列合法且 CRC 自洽；zlib 独立解压后 RGB 行逐字节相等；过领域解析判不透明 RGB8", async () => {
  const rgb = new Uint8Array([
    255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255,
    0, 0, 0, 128, 64, 32, 250, 251, 252, 1, 2, 3,
    16, 32, 48, 64, 128, 192, 200, 150, 100, 255, 255, 0,
  ]);
  const before = snapshot(rgb);
  const png = encodeOpaquePng(rgb, 4, 3);
  expectUnchanged(before, rgb, "encodeOpaquePng 输入");
  const signature = [137, 80, 78, 71, 13, 10, 26, 10];
  for (let i = 0; i < signature.length; i += 1) {
    expect(png[i] === signature[i], "PNG 签名第 " + i + " 字节不对");
  }
  const chunks = [];
  let offset = 8;
  while (offset < png.length) {
    const length = be32(png, offset);
    const type = String.fromCharCode(png[offset + 4], png[offset + 5], png[offset + 6], png[offset + 7]);
    const data = png.slice(offset + 8, offset + 8 + length);
    const stored = be32(png, offset + 8 + length);
    const body = new Uint8Array(4 + length);
    body.set(png.slice(offset + 4, offset + 8), 0);
    body.set(data, 4);
    expect(crc32Local(body) === stored, type + " 块 CRC 必须自洽");
    chunks.push({ type, data });
    offset += 12 + length;
  }
  expect(chunks[0].type === "IHDR" && chunks.at(-1).type === "IEND"
    && chunks.some((chunk) => chunk.type === "IDAT"), "PNG 必需块与起止顺序必须有效");
  const ihdr = chunks[0].data;
  expect(ihdr.length === 13, "IHDR 必须是 13 字节");
  expect(be32(ihdr, 0) === 4 && be32(ihdr, 4) === 3, "IHDR 宽高必须是 4×3");
  const tail = [ihdr[8], ihdr[9], ihdr[10], ihdr[11], ihdr[12]].join(",");
  expect(tail === "8,2,0,0,0", "IHDR 必须是 RGB8/压缩0/滤波0/非隔行，实际 " + tail);
  const raw = inflateSync(Buffer.concat(chunks.filter((chunk) => chunk.type === "IDAT").map((chunk) => chunk.data)));
  expect(raw.length === 3 * (1 + 4 * 3), "解压后扫描行总长不对，实际 " + raw.length);
  const decoded = new Uint8Array(rgb.length);
  for (let row = 0; row < 3; row += 1) {
    const base = row * 13;
    const filter = raw[base];
    expect(filter <= 4, "PNG 扫描行滤波类型必须有效");
    for (let i = 0; i < 12; i += 1) {
      const index = row * 12 + i;
      const left = i >= 3 ? decoded[index - 3] : 0;
      const above = row > 0 ? decoded[index - 12] : 0;
      const corner = row > 0 && i >= 3 ? decoded[index - 15] : 0;
      let predictor = 0;
      if (filter === 1) predictor = left;
      if (filter === 2) predictor = above;
      if (filter === 3) predictor = Math.floor((left + above) / 2);
      if (filter === 4) {
        const p = left + above - corner;
        const a = Math.abs(p - left), b = Math.abs(p - above), c = Math.abs(p - corner);
        predictor = a <= b && a <= c ? left : b <= c ? above : corner;
      }
      decoded[index] = (raw[base + 1 + i] + predictor) & 255;
    }
  }
  expectUnchanged(rgb, decoded, "独立解码后的 RGB");
  const header = parsePngHeader(png);
  expect(header.width === 4 && header.height === 3, "领域解析宽高必须是 4×3");
  expect(header.bit_depth === 8 && header.color_type === 2, "领域解析必须是 RGB8");
  expect(header.has_transparency === false, "输出必须判为不透明（现有 alpha 检测不阻断）");
  return { bytes: png.length };
});

test("M5", "几何：近角主体在画布内完整保留并满足方形尺寸与占比", async () => {
  const pixels = whiteRgba(1200, 1200);
  paint(pixels, 1200, 2, 2, 901, 901, 20, 20, 20);
  const plan = planMainCrop(pixels, 1200, 1200, 85);
  expectRect(plan.subject_bbox, 2, 2, 900, 900, "subject_bbox");
  expect(plan.rect.x >= 0 && plan.rect.y >= 0
    && plan.rect.x + plan.rect.width <= 1200 && plan.rect.y + plan.rect.height <= 1200,
    "rect 必须在画布内");
  expectContains(plan.rect, plan.subject_bbox, "M5");
  expect(plan.rect.width === plan.rect.height && plan.rect.width >= 1000
    && Math.max(plan.subject_bbox.width, plan.subject_bbox.height) / plan.rect.width >= 0.85,
    "近角裁剪必须达到主图方形尺寸和实际85%占比");
  return { rect: plan.rect };
});

test("M6", "边界：靠近画布边的主体不能让已剥离的灰线重新进入输出", async () => {
  const pixels = whiteRgba(1200, 1200);
  paint(pixels, 1200, 0, 0, 0, 1199, 120, 120, 120);
  paint(pixels, 1200, 20, 200, 919, 1099, 20, 20, 20);
  const plan = planMainCrop(pixels, 1200, 1200, 85);
  const rect = plan.rect;
  expectContains(rect, { x: 20, y: 200, width: 900, height: 900 }, "M6");
  let white = true;
  for (let i = 0; i < rect.width; i += 1) {
    const offsets = [
      (rect.y * 1200 + rect.x + i) * 4,
      ((rect.y + rect.height - 1) * 1200 + rect.x + i) * 4,
      ((rect.y + i) * 1200 + rect.x) * 4,
      ((rect.y + i) * 1200 + rect.x + rect.width - 1) * 4,
    ];
    for (const offset of offsets) {
      if (pixels[offset] !== 255 || pixels[offset + 1] !== 255 || pixels[offset + 2] !== 255) white = false;
    }
  }
  expect(white, "裁剪输出不能保留已剥离的灰色边线");
});

/* Node 原生运行器：与其它契约测试同一写法。 */
import nodeTest from "node:test";
for (const item of cases) {
  nodeTest(`${item.id} :: ${item.title}`, { timeout: 60000 }, async () => { await item.run(); });
}
