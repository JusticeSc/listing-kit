/**
 * V2.6.3 项目包契约测试（真实 Chromium，非 Mock）。
 *
 * 正向：格式 2 自描述记录 + 完整性计数 + 往返身份一致。
 * 迁移：格式 1 旧包升级到 2；旧复核合同丢弃 VLM 块；当前合同不动。
 * 反向：记录身份被换、完整性计数不符、格式过高/过低、payload schema 过高都必须按精确条目拒绝。
 *
 * 结果写到 window.__V2_TRANSFER_RESULTS__，由 tools/verify_v2_6_3_project_transfer.py 读取。
 */
import {
  PACKAGE_FORMAT,
  PACKAGE_FORMAT_VERSION,
  PACKAGE_FORMAT_VERSION_MIN_SUPPORTED,
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
    expect(parsed.migrations_applied.length === 0, "当前格式不需要迁移");
    return { integrity: built.manifest.integrity, applied: parsed.migrations_applied };
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

test("P03", "格式 1 旧包：升级为格式 2，旧 VLM 合同块被丢弃且记录在案", async () => {
  const legacy = legacyPackageBytes({ reviewReport: v1ReviewReport() });
  const parsed = await parseProjectPackage(legacy);
  const applied = parsed.migrations_applied.join(" | ");
  expect(parsed.manifest.format_version === PACKAGE_FORMAT_VERSION, "旧包必须升级到当前格式");
  expect(applied.indexOf("包格式 1 → 2") >= 0, "必须记录包格式迁移");
  expect(applied.indexOf("review_report/cand-legacy/v1") >= 0, "必须记录记录级迁移");
  const report = parsed.documents.find((item) => item.kind === "review_report");
  expect(report.payload.vlm === null, "旧合同 VLM 块必须丢弃");
  expect(report.payload.migrated_from_review_contract === "v2.5.1", "必须留下降级来源");
  return { applied: parsed.migrations_applied };
});

test("P04", "当前合同的复核报告不被改动", async () => {
  const legacy = legacyPackageBytes({ reviewReport: v1ReviewReport({ contract: "v2.5.2" }) });
  const parsed = await parseProjectPackage(legacy);
  const report = parsed.documents.find((item) => item.kind === "review_report");
  expect(report.payload.vlm !== null, "当前合同的 VLM 块必须保留");
  expect(parsed.migrations_applied.every((item) => item.indexOf("review_report") < 0),
    "当前合同不应触发记录级迁移");
  return { applied: parsed.migrations_applied };
});

test("P05", "格式过高/过低与完整性计数不符：都拒绝", async () => {
  const future = await expectCode(() => parseProjectPackage(legacyPackageBytes({
    manifestOverrides: { format_version: 99 } })), "PACKAGE_UNSUPPORTED_VERSION", "未来格式");
  // 0 不是历史格式（格式从 1 起），是损坏声明：按 PACKAGE_INVALID 拒绝，不进迁移链。
  const tooOld = await expectCode(() => parseProjectPackage(legacyPackageBytes({
    manifestOverrides: { format_version: 0 } })), "PACKAGE_INVALID", "非法格式声明");
  expect(PACKAGE_FORMAT_VERSION_MIN_SUPPORTED <= PACKAGE_FORMAT_VERSION, "支持区间必须自洽");
  const counted = legacyPackageBytes({ manifestOverrides: {
    format_version: 2, integrity: { documents: 5, assets: 1, document_bytes: 10, asset_bytes: 3 } } });
  const mismatch = await expectCode(() => parseProjectPackage(counted), "PACKAGE_INVALID",
    "完整性计数不符");
  return { future: future.message.slice(0, 40), too_old: tooOld.message.slice(0, 40),
           counted: mismatch.message.slice(0, 40) };
});

test("P06", "payload schema 高于当前支持：点名条目拒绝", async () => {
  const legacy = legacyPackageBytes({
    reviewReport: Object.assign(v1ReviewReport(), { schema_version: 99 }) });
  const outcome = await expectCode(() => parseProjectPackage(legacy),
    "PACKAGE_UNSUPPORTED_VERSION", "payload schema 过高");
  expect(outcome.message.indexOf("review_report/cand-legacy/v1") >= 0, "必须点名是哪一条记录");
  expect(outcome.message.indexOf("99") >= 0, "必须写出声明的版本");
  return { message: outcome.message };
});

test("P07", "格式 1 旧包可直接导入浏览器库（迁移在事务外完成）",
  () => withRepo(async ({ db, repository }) => {
    const legacy = legacyPackageBytes({ reviewReport: v1ReviewReport() });
    const result = await importProjectPackage(db, legacy);
    expect(result.project.project_id === "legacy-project", "旧包应保留 project_id");
    expect(result.documents === 2 && result.assets === 1,
      "导入数量不符：" + JSON.stringify(result));
    expect(result.migrations_applied.length >= 1, "导入结果必须报告已应用的迁移");
    const documents = await repository.documents.listAll("legacy-project");
    const report = documents.find((item) => item.kind === "review_report");
    expect(report && report.payload.vlm === null, "入库的是迁移后的记录");
    const assets = await rawCount(db, "assets");
    expect(assets === 1, "资产必须入库");
    return { migrations: result.migrations_applied, assets: assets };
  }));

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
