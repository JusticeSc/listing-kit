/* R3.2：本套件的宿主特有案例（Z04, Z05, Z06, Z07, Z08, Z09）仍由浏览器版 evals/product-v2/harness/package-contract.js 走真实 IDB/WebCrypto 覆盖。 */
/**
 * V2.1.3 项目包契约测试：ZIP 读写、项目包往返、损坏包拒绝、导入事务与 id 冲突。
 * 直接运行：node --test evals/product-v2/node/
 */


import { expect, expectCode, serializeError, utf8Bytes } from "./harness-core.mjs";

import { buildZip, crc32, readZip } from "../../../app/product_v2/storage/zip.js";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}



/* ---------- ZIP 读写 ---------- */

test("Z01", "ZIP 往返：UTF-8 路径与二进制字节一致", async () => {
  const entries = [
    { path: "manifest.json", bytes: utf8Bytes("{\"ok\":true}") },
    { path: "assets/中文名.bin", bytes: new Uint8Array([0, 255, 128, 7, 9]) },
  ];
  const zip = buildZip(entries);
  const parsed = await readZip(zip);
  expect(parsed.length === 2, "应读出 2 个条目，实际 " + parsed.length);
  const names = parsed.map((item) => item.path).sort();
  expect(JSON.stringify(names) === JSON.stringify(["assets/中文名.bin", "manifest.json"]),
    "路径不符：" + JSON.stringify(names));
  const binary = parsed.find((item) => item.path.endsWith(".bin")).bytes;
  expect(JSON.stringify([...binary]) === JSON.stringify([0, 255, 128, 7, 9]), "二进制字节应一致");
  return { entries: names, zip_bytes: zip.length };
});

test("Z02", "损坏 ZIP 被拒绝：截断与内容篡改都报 PACKAGE_INVALID", async () => {
  const zip = buildZip([{ path: "a.txt", bytes: utf8Bytes("hello-zip-world") }]);
  const truncated = zip.slice(0, Math.floor(zip.length / 2));
  const truncation = await expectCode(() => readZip(truncated), "PACKAGE_INVALID", "截断 ZIP");
  const tampered = zip.slice();
  tampered[40] = tampered[40] ^ 0xff;
  const corruption = await expectCode(() => readZip(tampered), "PACKAGE_INVALID", "篡改 ZIP");
  return { truncation: truncation.message, corruption: corruption.message };
});

test("Z03", "能读别的工具用 deflate 压缩的 ZIP", async () => {
  const payload = utf8Bytes("deflate-payload-".repeat(20));
  const deflated = new Uint8Array(await new Response(
    new Blob([payload]).stream().pipeThrough(new CompressionStream("deflate-raw")),
  ).arrayBuffer());
  const checksum = crc32(payload);
  // 手工拼一个 method=8 的 ZIP（模拟别的工具产出的压缩包）：本地头 + 中央目录 + EOCD
  const name = utf8Bytes("compressed.txt");
  const local = new Uint8Array(30 + name.length);
  const localView = new DataView(local.buffer);
  localView.setUint32(0, 0x04034b50, true);
  localView.setUint16(4, 20, true);
  localView.setUint16(6, 0x0800, true);
  localView.setUint16(8, 8, true);
  localView.setUint32(14, checksum, true);
  localView.setUint32(18, deflated.length, true);
  localView.setUint32(22, payload.length, true);
  localView.setUint16(26, name.length, true);
  local.set(name, 30);
  const central = new Uint8Array(46 + name.length);
  const centralView = new DataView(central.buffer);
  centralView.setUint32(0, 0x02014b50, true);
  centralView.setUint16(4, 20, true);
  centralView.setUint16(6, 20, true);
  centralView.setUint16(8, 0x0800, true);
  centralView.setUint16(10, 8, true);
  centralView.setUint32(16, checksum, true);
  centralView.setUint32(20, deflated.length, true);
  centralView.setUint32(24, payload.length, true);
  centralView.setUint16(28, name.length, true);
  centralView.setUint32(42, 0, true);
  central.set(name, 46);
  const eocd = new Uint8Array(22);
  const eocdView = new DataView(eocd.buffer);
  eocdView.setUint32(0, 0x06054b50, true);
  eocdView.setUint16(8, 1, true);
  eocdView.setUint16(10, 1, true);
  eocdView.setUint32(12, central.length, true);
  eocdView.setUint32(16, local.length + deflated.length, true);
  const zip = new Uint8Array(local.length + deflated.length + central.length + eocd.length);
  zip.set(local, 0);
  zip.set(deflated, local.length);
  zip.set(central, local.length + deflated.length);
  zip.set(eocd, local.length + deflated.length + central.length);
  const parsed = await readZip(zip);
  expect(parsed.length === 1 && parsed[0].path === "compressed.txt", "应读出压缩条目");
  const roundTrip = parsed[0].bytes;
  expect(roundTrip.length === payload.length
    && roundTrip.every((value, index) => value === payload[index]), "解压结果应与原文一致");
  // 反向：CRC 被改动后必须拒绝
  const brokenCentral = central.slice();
  new DataView(brokenCentral.buffer).setUint32(16, checksum ^ 0xffff, true);
  const broken = new Uint8Array(local.length + deflated.length + central.length + eocd.length);
  broken.set(local, 0);
  broken.set(deflated, local.length);
  broken.set(brokenCentral, local.length + deflated.length);
  broken.set(eocd, local.length + deflated.length + central.length);
  const crcFailure = await expectCode(() => readZip(broken), "PACKAGE_INVALID", "deflate CRC 校验");
  return { deflated_bytes: deflated.length, payload_bytes: payload.length,
           crc_failure: crcFailure.message };
});

/* ---------- 项目包 ---------- */


/* Node 原生运行器：与原浏览器版同一批 cases，断言不改写。 */
import nodeTest from "node:test";
for (const item of cases) {
  nodeTest(`${item.id} :: ${item.title}`, { timeout: 60000 }, async () => { await item.run(); });
}
