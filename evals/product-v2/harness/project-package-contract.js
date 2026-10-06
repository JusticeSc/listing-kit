/**
 * V2.6.3 项目包契约测试（真实 Chromium，非 Mock）。
 *
 * 正向：格式 2 自描述记录 + 完整性计数 + 往返身份一致。
 * 旧格式原子拒绝；当前格式历史报告不被修改。
 * 反向：记录身份被换、完整性计数不符、格式过高/过低、payload schema 过高都必须按精确条目拒绝。
 *
 * 结果写到 window.__V2_TRANSFER_RESULTS__，由 tools/verify_v2_6_3_project_transfer.py 读取。
 */
import {
  PACKAGE_FORMAT,
  PACKAGE_FORMAT_VERSION,
  buildProjectPackage,
  buildZip,
  importProjectPackage,
  openStorage,
  parseProjectPackage,
  readZip,
} from "/storage/index.js";
import { dropDatabase, expect, expectCode, newDbName, rawCount, serializeError, utf8Bytes }
  from "./harness-api.js";

const cases = [];
const AT = "2026-10-01T05:30:00+08:00";
const DOC = new TextEncoder();
const TEXT = new TextDecoder();
/** 夹具资产内容 "LEG" 的真实 sha256（内容与清单必须自洽，解析器不允许对不上）。 */
const LEGACY_ASSET_SHA = "0f6009a8315c15f82ce0a91f884671433c2a88c2f4afd7c5acdca48d1da1e9dd";

function test(id, title, run) {
  cases.push({ id, title, run });
}

function legacyManifest(overrides = {}) {
  return {
    format: PACKAGE_FORMAT,
    format_version: 1,
    exported_at: AT,
    project: {
      project_id: "legacy-project", name: "旧包项目", state: "INTAKE_READY", revision: 1,
      schema_version: 1, created_at: AT, updated_at: AT,
    },
    documents: [
      { path: "documents/0000.json", kind: "product_input", document_id: "intake", version: 1,
        schema_version: 1, created_at: AT, updated_at: AT },
      { path: "documents/0001.json", kind: "review_report", document_id: "cand-legacy", version: 1,
        schema_version: 1, created_at: AT, updated_at: AT },
    ],
    assets: [
      { path: "assets/" + LEGACY_ASSET_SHA, sha256: LEGACY_ASSET_SHA, media_type: "image/png",
        byte_size: 3, original_name: "legacy.png", role: "primary", width: 1200, height: 1200,
        schema_version: 1, created_at: AT },
    ],
    ...overrides,
  };
}

/** 独立构造格式 1 旧包（记录文件只有 payload，身份只来自清单）。 */
function legacyPackageBytes({ reviewReport = null, manifestOverrides = {} } = {}) {
  const manifest = legacyManifest({ ...manifestOverrides });
  const entries = [
    { path: "manifest.json", bytes: DOC.encode(JSON.stringify(manifest)) },
    { path: "documents/0000.json",
      bytes: DOC.encode(JSON.stringify({ payload: { schema_version: 1, product_name: "旧包商品" } })) },
    { path: "documents/0001.json",
      bytes: DOC.encode(JSON.stringify({ payload: reviewReport })) },
    { path: "assets/" + LEGACY_ASSET_SHA, bytes: utf8Bytes("LEG") },
  ];
  return buildZip(entries, { modifiedAt: new Date(AT) });
}

function currentPackageBytes(reviewReport = v1ReviewReport({ contract: "v2.5.2" })) {
  const manifest = legacyManifest();
  const payloads = [{ schema_version: 1, product_name: "包往返商品" }, reviewReport];
  return buildProjectPackage({
    project: manifest.project,
    documents: manifest.documents.map((meta, index) => ({
      ...meta, project_id: manifest.project.project_id,
      document_key: meta.kind + "/" + meta.document_id, payload: payloads[index],
    })),
    assets: [{ ...manifest.assets[0], bytes: utf8Bytes("LEG") }],
    exportedAt: AT,
  }).bytes;
}

function v1ReviewReport({ contract = "v2.5.1" } = {}) {
  return {
    schema_version: 1, review_contract_version: contract,
    candidate_id: "cand-legacy", shot_id: "shot_legacy", asset_sha256: LEGACY_ASSET_SHA,
    vlm: { contract_version: contract, outcome: "checked", asset_sha256: LEGACY_ASSET_SHA,
      model_id: "旧模型", checked_at: AT },
    summary: { BLOCK: 0, HIGH_RISK: 0, WARNING: 0, PASS: 1, UNKNOWN: 0 },
    findings: [], created_at: AT,
  };
}

async function withRepo(run, prefix = "amz-v263") {
  const name = newDbName(prefix);
  const opened = await openStorage({ name });
  try {
    return await run(opened, name);
  } finally {
    opened.close();
    await dropDatabase(name);
  }
}

async function collect(repository, projectId) {
  const project = await repository.projects.get(projectId);
  const documents = await repository.documents.listAll(projectId);
  const stored = await repository.assets.list(projectId);
  const assets = [];
  for (const record of stored) {
    assets.push({ ...record, bytes: new Uint8Array(await record.blob.arrayBuffer()) });
  }
  return { project, documents, assets, exportedAt: AT };
}

async function seedProject(repository, { name = "迁移验证项目" } = {}) {
  const project = await repository.projects.create({ name });
  await repository.documents.save(project.project_id, {
    kind: "product_input", documentId: "intake", payload: { schema_version: 1, note: "第一版" },
  });
  const asset = await repository.assets.put(project.project_id, {
    bytes: utf8Bytes("迁移验证资产"), mediaType: "image/png", originalName: "资产.png",
    role: "primary", width: 1200, height: 900,
  });
  return { project, asset };
}

test("P01", "格式 2 往返：记录自描述、完整性计数相符、无需迁移",
  () => withRepo(async ({ repository }) => {
    const seeded = await seedProject(repository);
    const built = await buildProjectPackage(await collect(repository, seeded.project.project_id));
    expect(built.manifest.format_version === PACKAGE_FORMAT_VERSION, "导出必须是当前格式");
    expect(built.manifest.integrity && built.manifest.integrity.documents === 1,
      "manifest 必须带完整性计数");
    const entries = await readZip(built.bytes);
    const record = JSON.parse(TEXT.decode(
      entries.find((item) => item.path === "documents/0000.json").bytes));
    expect(record.kind === "product_input" && record.document_id === "intake"
      && record.version === 1, "记录文件必须自描述身份");
    const parsed = await parseProjectPackage(built.bytes);
    expect(parsed.documents.length === 1 && parsed.assets.length === 1, "往返数量一致");
    return { integrity: built.manifest.integrity };
  }));

test("P02", "记录文件身份被换：按条目拒绝，不静默导入",
  () => withRepo(async ({ repository }) => {
    const seeded = await seedProject(repository);
    const built = await buildProjectPackage(await collect(repository, seeded.project.project_id));
    const entries = await readZip(built.bytes);
    const swapped = entries.map((entry) => (entry.path === "documents/0000.json"
      ? { path: entry.path, bytes: DOC.encode(JSON.stringify({
        schema_version: 1, kind: "product_input", document_id: "other", version: 1,
        payload: { schema_version: 1 } })) }
      : entry));
    const outcome = await expectCode(() => parseProjectPackage(buildZip(swapped)),
      "PACKAGE_INVALID", "记录身份不符");
    expect(outcome.message.indexOf("product_input/intake/v1") >= 0
      || outcome.message.indexOf("不一致") >= 0, "错误必须点名条目");
    return { message: outcome.message };
  }));

test("P03", "格式 1 旧包拒绝，不补造当前身份", async () => {
  const outcome = await expectCode(
    () => parseProjectPackage(legacyPackageBytes({ reviewReport: v1ReviewReport() })),
    "PACKAGE_UNSUPPORTED_VERSION", "旧包不可自动迁移");
  return { code: outcome.code };
});

test("P04", "当前格式保留历史复核报告的原始内容", async () => {
  const original = v1ReviewReport();
  const parsed = await parseProjectPackage(currentPackageBytes(original));
  const report = parsed.documents.find((item) => item.kind === "review_report");
  expect(JSON.stringify(report.payload) === JSON.stringify(original),
    "导入不得丢弃历史复核块或改写合同");
  return { contract: report.payload.review_contract_version };
});

test("P05", "格式过高/过低与完整性计数不符：都拒绝", async () => {
  const future = await expectCode(() => parseProjectPackage(legacyPackageBytes({
    manifestOverrides: { format_version: 99 } })), "PACKAGE_UNSUPPORTED_VERSION", "未来格式");
  // 0 是损坏声明，不是可支持的历史格式。
  const tooOld = await expectCode(() => parseProjectPackage(legacyPackageBytes({
    manifestOverrides: { format_version: 0 } })), "PACKAGE_INVALID", "非法格式声明");
  const entries = await readZip(currentPackageBytes());
  const counted = buildZip(entries.map(entry => entry.path === "manifest.json"
    ? { ...entry, bytes: DOC.encode(JSON.stringify({
      ...JSON.parse(TEXT.decode(entry.bytes)), integrity: { documents: 5, assets: 1 },
    })) } : entry));
  const mismatch = await expectCode(() => parseProjectPackage(counted), "PACKAGE_INVALID",
    "完整性计数不符");
  return { future: future.message.slice(0, 40), too_old: tooOld.message.slice(0, 40),
           counted: mismatch.message.slice(0, 40) };
});

test("P06", "payload schema 高于当前支持：点名条目拒绝", async () => {
  const bytes = currentPackageBytes({ ...v1ReviewReport(), schema_version: 99 });
  const outcome = await expectCode(() => parseProjectPackage(bytes),
    "PACKAGE_UNSUPPORTED_VERSION", "payload schema 过高");
  expect(outcome.message.indexOf("review_report/cand-legacy/v1") >= 0, "必须点名是哪一条记录");
  expect(outcome.message.indexOf("99") >= 0, "必须写出声明的版本");
  return { message: outcome.message };
});

test("P07", "旧包拒绝不写入任何项目、文档或资产",
  () => withRepo(async ({ db, repository }) => {
    const existing = await seedProject(repository);
    const before = await Promise.all(["projects", "documents", "assets"].map(store => rawCount(db, store)));
    await expectCode(() => importProjectPackage(db,
      legacyPackageBytes({ reviewReport: v1ReviewReport() })),
    "PACKAGE_UNSUPPORTED_VERSION", "旧包须在写入前拒绝");
    const after = await Promise.all(["projects", "documents", "assets"].map(store => rawCount(db, store)));
    expect(JSON.stringify(after) === JSON.stringify(before), "拒绝不能产生半份项目");
    expect((await repository.projects.get(existing.project.project_id)).name === existing.project.name,
      "已有项目不能被拒绝的包覆盖");
    return { before, after };
  }));

test("P08", "Attempt 缺失或旧 schema 拒绝，不把未知身份当当前版本", async () => {
  for (const payload of [{}, { schema_version: 1 }]) {
    const bytes = buildProjectPackage({
      project: legacyManifest().project,
      documents: [{ project_id: "legacy-project", document_key: "attempt/action",
        kind: "generation_attempt", document_id: "action", version: 1,
        schema_version: 1, created_at: AT, updated_at: AT, payload }],
      assets: [], exportedAt: AT,
    }).bytes;
    await expectCode(() => parseProjectPackage(bytes), "PACKAGE_UNSUPPORTED_VERSION",
      "没有当前身份 schema 的 Attempt 不可导入");
  }
});

async function runSuite() {
  const results = {
    suite: "v2.6.3-project-package", status: "passed", cases: [],
    started_at: new Date().toISOString(), finished_at: null,
  };
  for (const item of cases) {
    const startedAt = performance.now();
    try {
      const detail = await item.run();
      results.cases.push({ id: item.id, title: item.title, status: "passed",
        detail: detail === undefined ? null : detail,
        duration_ms: Math.round(performance.now() - startedAt) });
    } catch (error) {
      results.status = "failed";
      results.cases.push({ id: item.id, title: item.title, status: "failed",
        error: serializeError(error), duration_ms: Math.round(performance.now() - startedAt) });
    }
  }
  results.finished_at = new Date().toISOString();
  return results;
}

function render(results) {
  const node = document.getElementById("results");
  if (node) node.textContent = JSON.stringify(results, null, 1);
}

runSuite().then((results) => {
  window.__V2_TRANSFER_RESULTS__ = results;
  render(results);
}).catch((error) => {
  window.__V2_TRANSFER_RESULTS__ = {
    suite: "v2.6.3-project-package", status: "crashed", error: serializeError(error), cases: [],
  };
  render(window.__V2_TRANSFER_RESULTS__);
});
