/**
 * V2.1.3 项目包契约测试：ZIP 读写、项目包往返、损坏包拒绝、导入事务与 id 冲突。
 * 结果写到 window.__V2_PACKAGE_RESULTS__。
 */

import {
  PACKAGE_FORMAT,
  PACKAGE_FORMAT_VERSION,
  buildZip,
  buildProjectPackage,
  crc32,
  exportProjectPackage,
  importProjectPackage,
  openStorage,
  parseProjectPackage,
  readZip,
  withTransaction,
  requestToPromise,
} from "/storage/index.js";

import { dropDatabase, expect, expectCode, newDbName, rawCount, serializeError, utf8Bytes }
  from "./harness-api.js";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

async function withRepo(run) {
  const name = newDbName("amz-v2-package");
  const opened = await openStorage({ name });
  try {
    return await run(opened, name);
  } finally {
    opened.close();
    await dropDatabase(name);
  }
}

async function seedProject(repository, { name = "打包验证项目" } = {}) {
  const project = await repository.projects.create({ name });
  await repository.documents.save(project.project_id, {
    kind: "product_input", documentId: "intake", payload: { note: "第一版资料" },
  });
  await repository.documents.save(project.project_id, {
    kind: "product_input", documentId: "intake", payload: { note: "第二版资料" }, expectedVersion: 1,
  });
  const first = await repository.assets.put(project.project_id, {
    bytes: utf8Bytes("reference-image-bytes-AAA"), mediaType: "image/png",
    originalName: "参考图 A.png", role: "primary", width: 1200, height: 900,
  });
  const second = await repository.assets.put(project.project_id, {
    bytes: new Uint8Array([0, 1, 2, 3, 250, 251, 252, 253]), mediaType: "image/jpeg",
    originalName: "细节图 B.jpg", role: "detail",
  });
  return { project, first, second };
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

test("Z04", "项目包往返：文档版本与资产哈希一致", () => withRepo(async ({ repository }) => {
  const seeded = await seedProject(repository);
  const built = await exportProjectPackage(repository, seeded.project.project_id);
  const parsed = await parseProjectPackage(built.bytes);
  expect(parsed.manifest.format === PACKAGE_FORMAT, "format 不符");
  expect(parsed.manifest.format_version === PACKAGE_FORMAT_VERSION, "format_version 不符");
  expect(parsed.project.project_id === seeded.project.project_id, "project_id 应保持");
  expect(parsed.project.name === seeded.project.name, "名称应保持");
  expect(parsed.documents.length === 2, "应含两个文档版本，实际 " + parsed.documents.length);
  expect(parsed.assets.length === 2, "应含两个资产，实际 " + parsed.assets.length);
  const hashes = parsed.assets.map((item) => item.sha256).sort();
  expect(JSON.stringify(hashes) === JSON.stringify([seeded.first.sha256, seeded.second.sha256].sort()),
    "资产哈希应一致");
  return { documents: parsed.documents.length, assets: parsed.assets.length, zip_bytes: built.bytes.length };
}));

test("Z05", "篡改资产内容：PACKAGE_HASH_MISMATCH", () => withRepo(async ({ repository }) => {
  const seeded = await seedProject(repository);
  const built = await exportProjectPackage(repository, seeded.project.project_id);
  const entries = await readZip(built.bytes);
  const tamperedEntries = entries.map((entry) => (entry.path.startsWith("assets/")
    ? { path: entry.path, bytes: utf8Bytes("替换后的假字节") }
    : entry));
  const tampered = buildZip(tamperedEntries);
  const outcome = await expectCode(
    () => parseProjectPackage(tampered), "PACKAGE_HASH_MISMATCH", "资产被替换");
  return { message: outcome.message };
}));

test("Z06", "包版本高于代码支持：PACKAGE_UNSUPPORTED_VERSION", () => withRepo(async ({ repository }) => {
  const seeded = await seedProject(repository);
  const built = await exportProjectPackage(repository, seeded.project.project_id);
  const entries = await readZip(built.bytes);
  const future = entries.map((entry) => {
    if (entry.path !== "manifest.json") return entry;
    const manifest = JSON.parse(new TextDecoder().decode(entry.bytes));
    manifest.format_version = 99;
    return { path: entry.path, bytes: utf8Bytes(JSON.stringify(manifest)) };
  });
  const outcome = await expectCode(
    () => parseProjectPackage(buildZip(future)), "PACKAGE_UNSUPPORTED_VERSION", "未来版本包");
  return { message: outcome.message };
}));

test("Z07", "导入到空库：同 id 恢复；重复导入自动分配新 id", () => withRepo(async ({ db, repository }) => {
  const seeded = await seedProject(repository);
  const built = await exportProjectPackage(repository, seeded.project.project_id);
  const name = newDbName("amz-v2-import");
  const target = await openStorage({ name });
  try {
    const first = await importProjectPackage(target.db, built.bytes);
    expect(first.project.project_id === seeded.project.project_id, "空库导入应保留 project_id");
    expect(first.id_assigned === false, "空库导入不应改 id");
    expect(first.documents === 2 && first.assets === 2, "导入数量不符：" + JSON.stringify(first));
    const second = await importProjectPackage(target.db, built.bytes);
    expect(second.id_assigned === true, "重复导入应分配新 id");
    expect(second.project.project_id !== first.project.project_id, "第二次导入应有不同 id");
    const list = await target.repository.projects.list();
    expect(list.length === 2, "两次导入应有两个项目");
    const restored = await target.repository.assets.list(first.project.project_id);
    const original = await target.repository.assets.list(
      list.find((item) => item.project_id !== first.project.project_id).project_id);
    expect(restored.length === 2 && original.length === 2, "两个项目的资产都应存在");
    return { first_id: first.project.project_id, second_id: second.project.project_id,
             documents: first.documents, assets: first.assets };
  } finally {
    target.close();
    await dropDatabase(name);
  }
}));

test("Z08", "导入中途失败：整笔事务回滚，目标库不留残留", () => withRepo(async ({ db, repository }) => {
  const seeded = await seedProject(repository);
  const built = await exportProjectPackage(repository, seeded.project.project_id);
  const name = newDbName("amz-v2-import-abort");
  const target = await openStorage({ name });
  try {
    const parsed = await parseProjectPackage(built.bytes);
    // 预置一条"孤儿文档"：key 与即将导入的文档相同，但没有对应项目记录。
    await withTransaction(target.db, ["documents"], "readwrite", (tx) => requestToPromise(
      tx.objectStore("documents").add({
        document_key: parsed.project.project_id + ":" + parsed.documents[0].kind + ":"
          + parsed.documents[0].document_id + ":" + parsed.documents[0].version,
        project_id: parsed.project.project_id,
        kind: parsed.documents[0].kind,
        document_id: parsed.documents[0].document_id,
        version: parsed.documents[0].version,
        schema_version: 1,
        payload: { note: "orphan" },
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      })));
    const outcome = await expectCode(
      () => importProjectPackage(target.db, built.bytes), "DUPLICATE_RECORD", "孤儿键冲突");
    const projects = await rawCount(target.db, "projects");
    const assets = await rawCount(target.db, "assets");
    expect(projects === 0 && assets === 0, "失败导入不得留下项目或资产，实际 "
      + JSON.stringify({ projects, assets }));
    return { code: outcome.code, projects, assets };
  } finally {
    target.close();
    await dropDatabase(name);
  }
}));

test("Z09", "导出→清空→导入：文档载荷与资产字节逐字节一致", () => withRepo(async ({ repository }) => {
  const seeded = await seedProject(repository);
  const built = await exportProjectPackage(repository, seeded.project.project_id);
  const name = newDbName("amz-v2-roundtrip");
  const target = await openStorage({ name });
  try {
    await importProjectPackage(target.db, built.bytes);
    const docs = await target.repository.documents.listVersions(
      seeded.project.project_id, "product_input", "intake");
    expect(docs.length === 2, "文档版本数应保持 2");
    expect(docs[1].payload.note === "第一版资料" && docs[0].payload.note === "第二版资料",
      "文档载荷应逐版本一致");
    const asset = await target.repository.assets.get(seeded.project.project_id, seeded.first.sha256);
    const bytes = new Uint8Array(await asset.blob.arrayBuffer());
    const originalBytes = utf8Bytes("reference-image-bytes-AAA");
    expect(bytes.length === originalBytes.length
      && bytes.every((value, index) => value === originalBytes[index]), "资产字节应逐字节一致");
    return { versions: docs.map((item) => item.version), sha256: asset.sha256 };
  } finally {
    target.close();
    await dropDatabase(name);
  }
}));

/* ---------- 运行器 ---------- */

function render(results) {
  const target = document.getElementById("results");
  if (target) target.textContent = JSON.stringify(results, null, 2);
}

async function runSuite() {
  const results = {
    suite: "v2.1.3-package-contract",
    status: "running",
    started_at: new Date().toISOString(),
    cases: [],
  };
  window.__V2_PACKAGE_RESULTS__ = results;
  for (const item of cases) {
    const startedAt = performance.now();
    try {
      const detail = await item.run();
      results.cases.push({
        id: item.id, title: item.title, ok: true,
        detail: detail === undefined ? null : detail,
        ms: Math.round(performance.now() - startedAt),
      });
    } catch (error) {
      results.cases.push({
        id: item.id, title: item.title, ok: false,
        error: serializeError(error),
        ms: Math.round(performance.now() - startedAt),
      });
    }
  }
  const failed = results.cases.filter((item) => !item.ok);
  results.status = failed.length === 0 ? "passed" : "failed";
  results.failed_ids = failed.map((item) => item.id);
  results.finished_at = new Date().toISOString();
  render(results);
}

const params = new URLSearchParams(location.search);
if (params.get("suite") !== "0") {
  runSuite().catch((error) => {
    window.__V2_PACKAGE_RESULTS__ = {
      suite: "v2.1.3-package-contract", status: "crashed", error: serializeError(error), cases: [],
    };
    render(window.__V2_PACKAGE_RESULTS__);
  });
} else {
  window.__V2_PACKAGE_RESULTS__ = { suite: "v2.1.3-package-contract", status: "skipped", cases: [] };
}
