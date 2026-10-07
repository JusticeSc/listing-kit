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

import { buildAttemptRecord } from "/domain/index.js";

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

/* R3.2：纯领域断言已迁至 evals/product-v2/node/（同名 .test.mjs），此处仅保留宿主特有案例。 */

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

test("Z10", "执行身份包往返：attempt（含冻结身份）导出→导入后逐字一致", () => withRepo(async ({ repository }) => {
  const seeded = await seedProject(repository);
  const attempt = buildAttemptRecord({
    actionId: "act-roundtrip-0001-aaaa-bbbb-cccccccccccc",
    shotId: "shot_main_clean",
    prompt: { version: 1, hash: "a".repeat(64) },
    references: [{ role: "primary", sha256: seeded.first.sha256 }],
    provider: { provider_id: "dashscope-qwen-image", model_id: "qwen-image-3.0" },
    executionIdentity: { protocol: "v2.4.1", capabilityVersion: 2, credentialSource: "default" },
    parameters: { size: "1344*1344", n: 1, prompt_extend: false, watermark: false },
    at: "2026-09-30T10:00:00+08:00",
    note: "打包往返",
  });
  await repository.documents.save(seeded.project.project_id, {
    kind: "generation_attempt", documentId: "shot_main_clean", payload: attempt,
  });
  const built = await exportProjectPackage(repository, seeded.project.project_id);
  const parsed = await parseProjectPackage(built.bytes);
  const attemptDocs = parsed.documents.filter((item) => item.kind === "generation_attempt");
  expect(attemptDocs.length === 1, "包内应含一条 attempt 记录");
  const roundtrip = attemptDocs[0].payload;
  expect(JSON.stringify(roundtrip.execution_identity)
    === JSON.stringify(attempt.execution_identity),
    "执行身份块往返后逐字一致：" + JSON.stringify(roundtrip.execution_identity));
  expect(JSON.stringify(roundtrip) === JSON.stringify(attempt),
    "attempt 记录往返后逐字一致");
  const name = newDbName("amz-v2-attempt-import");
  const target = await openStorage({ name });
  try {
    const imported = await importProjectPackage(target.db, built.bytes);
    expect(imported.id_assigned === false, "空库导入应保留 project_id");
    const docs = await target.repository.documents.listVersions(
      seeded.project.project_id, "generation_attempt", "shot_main_clean");
    expect(docs.length === 1
      && JSON.stringify(docs[0].payload.execution_identity)
        === JSON.stringify(attempt.execution_identity),
      "导入后的 attempt 执行身份保持");
    return { identity: roundtrip.execution_identity, documents: parsed.documents.length };
  } finally {
    target.close();
    await dropDatabase(name);
  }
}));

test("Z11", "反向：schema 1 的 attempt 记录（无冻结身份）整包原子拒绝", () => withRepo(async ({ repository }) => {
  const seeded = await seedProject(repository);
  await repository.documents.save(seeded.project.project_id, {
    kind: "generation_attempt", documentId: "shot_main_clean",
    payload: {
      schema_version: 1,
      action_id: "act-legacy-0001-aaaa-bbbb-cccccccccccc",
      shot_id: "shot_main_clean",
      state: "pending_submit",
      prompt: { version: 1, hash: "a".repeat(64) },
      references: [{ role: "primary", sha256: seeded.first.sha256 }],
      provider: { provider_id: "dashscope-qwen-image", model_id: "qwen-image-3.0" },
      parameters: { size: "1344*1344", n: 1, prompt_extend: false, watermark: false },
      task_id: null,
      request_id: null,
      error: null,
      created_at: "2026-09-30T10:00:00+08:00",
      updated_at: "2026-09-30T10:00:00+08:00",
      change_log: [{ at: "2026-09-30T10:00:00+08:00", via: "user",
                     from: null, to: "pending_submit", note: "旧记录" }],
    },
  });
  const built = await exportProjectPackage(repository, seeded.project.project_id);
  const outcome = await expectCode(
    () => parseProjectPackage(built.bytes), "PACKAGE_UNSUPPORTED_VERSION", "旧 attempt 记录");
  expect(outcome.message.includes("不做 legacy 映射")
    && outcome.message.includes("不部分写入"),
    "拒绝话术必须说清不做 legacy 映射与不部分写入：" + outcome.message);
  // 原子性：解析阶段拒绝，绝不触碰数据库（本用例没有第二个库；仓库内数据也不被改写）。
  const docs = await repository.documents.listVersions(
    seeded.project.project_id, "generation_attempt", "shot_main_clean");
  expect(docs.length === 1 && docs[0].payload.schema_version === 1,
    "原库内容保持原样（旧记录留在原库，不被静默删除或改写）");
  return { code: outcome.code, documents_in_repo: docs.length };
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
