/**
 * V2.1.1 存储契约测试：在真实 Chromium 的 IndexedDB 上跑正向与反向探针。
 *
 * 正向：schema、项目 CRUD、文档版本、资产 Blob、事务、指针、迁移。
 * 反向（故意让守卫变红）：schema 漂移检测、非法载荷、版本冲突、降级打开、
 * 指针损坏与过期、迁移失败回滚、并发写只有一个赢家。
 *
 * 结果写到 window.__V2_STORAGE_RESULTS__，由 tools/verify_v2_1_1_indexeddb.py 读取。
 */

import {
  CURRENT_PROJECT_POINTER_KEY,
  STORAGE_SCHEMA_VERSION,
  STORE_SPECS,
  DEFAULT_MIGRATIONS,
  documentKeyOf,
  openDatabase,
  openStorage,
  pointerKeys,
  requestToPromise,
  schemaDrift,
  withTransaction,
  writePointer,
} from "/storage/index.js";

import {
  dropDatabase,
  expect,
  expectCode,
  newDbName,
  rawCount,
  rawGet,
  rawPut,
  serializeError,
  utf8Bytes,
} from "./harness-api.js";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

async function withRepo(run, options = {}) {
  const name = options.name || newDbName();
  const opened = await openStorage({ name, now: options.now });
  try {
    return await run(opened, name);
  } finally {
    opened.close();
    await dropDatabase(name);
  }
}

const PROBE_DOC = "probe_doc";

/* ---------- schema ---------- */

test("S01", "新建数据库的结构与 STORE_SPECS 一致，版本与代码一致", () => withRepo(async ({ db }, name) => {
  expect(db.version === STORAGE_SCHEMA_VERSION,
    "数据库版本应为 " + STORAGE_SCHEMA_VERSION + "，实际 " + db.version);
  const drift = schemaDrift(db);
  expect(drift.length === 0, "schema 漂移：" + drift.join("；"));
  const stores = Array.from(db.objectStoreNames).sort();
  expect(stores.length === STORE_SPECS.length, "对象仓数量不符：" + stores.join(","));
  return { db_name: name, version: db.version, stores };
}));

test("S02", "schema 漂移检测器能变红（缺失索引 / 幽灵对象仓）", () => withRepo(async ({ db }) => {
  const broken = STORE_SPECS.map((spec) => (spec.name === "documents"
    ? { ...spec, indexes: spec.indexes.filter((index) => index.name !== "by_project_document") }
    : spec));
  const missing = schemaDrift(db, broken);
  expect(missing.some((line) => line.includes("by_project_document")),
    "未检出缺失索引：" + missing.join("；"));
  const extra = [...STORE_SPECS,
    { name: "ghost_store", keyPath: "id", autoIncrement: false, indexes: [] }];
  const ghost = schemaDrift(db, extra);
  expect(ghost.some((line) => line.includes("ghost_store")),
    "未检出幽灵对象仓：" + ghost.join("；"));
  return { missing_index: missing[0], ghost_store: ghost[0] };
}));

/* ---------- 项目 ---------- */

test("P01", "空白新建项目只含身份字段，初始状态 EMPTY，无预填商品内容", () => withRepo(async ({ repository }) => {
  const record = await repository.projects.create({ name: "  水杯项目  " });
  const keys = Object.keys(record).sort();
  expect(record.name === "水杯项目", "名称应被 trim，实际 " + JSON.stringify(record.name));
  expect(record.state === "EMPTY", "初始状态应为 EMPTY，实际 " + record.state);
  expect(record.revision === 1, "初始 revision 应为 1");
  const expectedKeys = ["created_at", "name", "project_id", "revision", "schema_version", "state", "updated_at"];
  expect(JSON.stringify(keys) === JSON.stringify(expectedKeys), "字段集合不符：" + keys.join(","));
  return { project_id: record.project_id, keys };
}));

test("P02", "空名称被拒绝：INVALID_ARGUMENT", () => withRepo(async ({ repository }) => {
  const outcome = await expectCode(
    () => repository.projects.create({ name: "   " }), "INVALID_ARGUMENT", "空名称");
  return outcome;
}));

test("P03", "项目列表按 updated_at 倒序", async () => {
  let currentTime = "2026-09-29T10:00:00.000Z";
  return withRepo(async ({ repository }) => {
    const first = await repository.projects.create({ name: "先建" });
    currentTime = "2026-09-29T11:00:00.000Z";
    const second = await repository.projects.create({ name: "后建" });
    const list = await repository.projects.list();
    expect(list.length === 2, "应有 2 个项目");
    expect(list[0].project_id === second.project_id && list[1].project_id === first.project_id,
      "排序应为后建在前：" + list.map((item) => item.name).join(","));
    return { order: list.map((item) => item.name) };
  }, { now: () => currentTime });
});

test("P04", "重命名递增 revision 并更新时间", () => withRepo(async ({ repository }) => {
  const created = await repository.projects.create({ name: "旧名" });
  const renamed = await repository.projects.rename(created.project_id, "新名", { expectedRevision: 1 });
  expect(renamed.name === "新名", "名称应更新");
  expect(renamed.revision === 2, "revision 应为 2，实际 " + renamed.revision);
  expect(renamed.updated_at >= created.updated_at, "updated_at 不应回退");
  return { revision: renamed.revision };
}));

test("P05", "过期 revision 的重命名被拒绝，且记录不被改动", () => withRepo(async ({ repository }) => {
  const created = await repository.projects.create({ name: "原名" });
  await repository.projects.rename(created.project_id, "第一次改名", { expectedRevision: 1 });
  const outcome = await expectCode(
    () => repository.projects.rename(created.project_id, "第二次改名", { expectedRevision: 1 }),
    "REVISION_CONFLICT", "过期重命名");
  const current = await repository.projects.get(created.project_id);
  expect(current.name === "第一次改名", "冲突写入不得生效，实际 " + current.name);
  expect(current.revision === 2, "冲突后 revision 应保持 2，实际 " + current.revision);
  return { conflict: outcome.code, name: current.name, revision: current.revision };
}));

test("P06", "非法项目状态被拒绝，状态保持原值", () => withRepo(async ({ repository }) => {
  const created = await repository.projects.create({ name: "状态验证" });
  await expectCode(() => repository.projects.setState(created.project_id, "MAGIC_STATE"),
    "INVALID_ARGUMENT", "非法状态");
  const current = await repository.projects.get(created.project_id);
  expect(current.state === "EMPTY" && current.revision === 1, "非法状态不得落库");
  const advanced = await repository.projects.setState(created.project_id, "INTAKE_READY", { expectedRevision: 1 });
  expect(advanced.state === "INTAKE_READY" && advanced.revision === 2, "合法状态应写入并递增 revision");
  return { state: advanced.state };
}));

test("P07", "删除项目在同一事务里清掉它的文档与资产", () => withRepo(async ({ db, repository }) => {
  const project = await repository.projects.create({ name: "待删除" });
  await repository.documents.save(project.project_id, {
    kind: PROBE_DOC, documentId: "brief", payload: { note: "x" },
  });
  await repository.assets.put(project.project_id, {
    bytes: utf8Bytes("delete-me"), mediaType: "image/png", originalName: "a.png",
  });
  await repository.pointer.set(project.project_id);
  await repository.projects.remove(project.project_id);
  const leftovers = {
    projects: await rawCount(db, "projects"),
    documents: await rawCount(db, "documents"),
    assets: await rawCount(db, "assets"),
  };
  expect(leftovers.projects === 0 && leftovers.documents === 0 && leftovers.assets === 0,
    "删除后三仓都应为空，实际 " + JSON.stringify(leftovers));
  const pointer = await repository.pointer.get();
  expect(pointer === null, "删除当前项目后指针应解析为 null");
  return { leftovers };
}));

test("P08", "重复 project_id 被拒绝：DUPLICATE_RECORD", () => withRepo(async ({ repository }) => {
  const fixedId = crypto.randomUUID();
  await repository.projects.create({ name: "第一个", projectId: fixedId });
  const outcome = await expectCode(
    () => repository.projects.create({ name: "第二个", projectId: fixedId }),
    "DUPLICATE_RECORD", "重复项目标识");
  return outcome;
}));

test("P09", "复制项目：新 id 下复制文档与资产，原项目不受影响", () => withRepo(async ({ repository }) => {
  const source = await repository.projects.create({ name: "原项目" });
  await repository.documents.save(source.project_id, {
    kind: PROBE_DOC, documentId: "brief", payload: { note: "第一个版本" },
  });
  await repository.documents.save(source.project_id, {
    kind: PROBE_DOC, documentId: "brief", payload: { note: "第二个版本" }, expectedVersion: 1,
  });
  const asset = await repository.assets.put(source.project_id, {
    bytes: utf8Bytes("duplicate-source-bytes"), mediaType: "image/png", originalName: "ref.png",
  });
  const copy = await repository.projects.duplicate(source.project_id);
  const copyId = copy.project.project_id;
  expect(copyId !== source.project_id, "副本必须有新的 project_id");
  expect(copy.project.name === "原项目（副本）", "默认名称应标记副本，实际 " + copy.project.name);
  expect(copy.documents === 2 && copy.assets === 1, "复制数量不符：" + JSON.stringify(copy));
  const copyHistory = await repository.documents.listVersions(copyId, PROBE_DOC, "brief");
  expect(copyHistory.length === 2, "副本应保留两个文档版本，实际 " + copyHistory.length);
  const copyAsset = await repository.assets.get(copyId, asset.sha256);
  expect(copyAsset && copyAsset.asset_key !== asset.asset_key, "副本资产键必须重写");
  const copyBytes = new Uint8Array(await copyAsset.blob.arrayBuffer());
  expect(new TextDecoder().decode(copyBytes) === "duplicate-source-bytes", "副本字节应与原资产一致");
  await repository.projects.remove(copyId);
  const sourceAssets = await repository.assets.list(source.project_id);
  expect(sourceAssets.length === 1, "删除副本不得影响原项目资产");
  return { copy_id: copyId, documents: copy.documents, assets: copy.assets };
}));

/* ---------- 文档版本 ---------- */

test("D01", "文档 append-only：版本递增且旧版本仍可读", () => withRepo(async ({ repository }) => {
  const project = await repository.projects.create({ name: "文档验证" });
  const v1 = await repository.documents.save(project.project_id, {
    kind: PROBE_DOC, documentId: "plan", payload: { step: 1 },
  });
  const v2 = await repository.documents.save(project.project_id, {
    kind: PROBE_DOC, documentId: "plan", payload: { step: 2 }, expectedVersion: 1,
  });
  expect(v1.version === 1 && v2.version === 2, "版本应为 1、2");
  const history = await repository.documents.listVersions(project.project_id, PROBE_DOC, "plan");
  expect(history.length === 2 && history[0].version === 2, "历史应有两条且最新在前");
  const reread = await repository.documents.get(project.project_id, PROBE_DOC, "plan", 1);
  expect(reread.payload.step === 1, "旧版本内容不得被覆盖");
  const latest = await repository.documents.getLatest(project.project_id, PROBE_DOC, "plan");
  expect(latest.version === 2 && latest.payload.step === 2, "latest 应指向 v2");
  return { versions: history.map((item) => item.version) };
}));

test("D02", "expectedVersion 不符：REVISION_CONFLICT，且不写新版本", () => withRepo(async ({ repository }) => {
  const project = await repository.projects.create({ name: "冲突验证" });
  await repository.documents.save(project.project_id, {
    kind: PROBE_DOC, documentId: "plan", payload: { step: 1 },
  });
  const outcome = await expectCode(() => repository.documents.save(project.project_id, {
    kind: PROBE_DOC, documentId: "plan", payload: { step: 9 }, expectedVersion: 7,
  }), "REVISION_CONFLICT", "文档版本冲突");
  const history = await repository.documents.listVersions(project.project_id, PROBE_DOC, "plan");
  expect(history.length === 1, "冲突不得写新版本，实际 " + history.length);
  return { conflict: outcome.code, versions: history.map((item) => item.version) };
}));

test("D03", "非 JSON 载荷（函数 / Blob）被拒绝：SCHEMA_INVALID", () => withRepo(async ({ repository }) => {
  const project = await repository.projects.create({ name: "载荷验证" });
  const withFunction = await expectCode(() => repository.documents.save(project.project_id, {
    kind: PROBE_DOC, documentId: "x", payload: { callback: () => 1 },
  }), "SCHEMA_INVALID", "函数载荷");
  const withBlob = await expectCode(() => repository.documents.save(project.project_id, {
    kind: PROBE_DOC, documentId: "y", payload: { image: new Blob([utf8Bytes("img")]) },
  }), "SCHEMA_INVALID", "Blob 载荷");
  const withUndefined = await expectCode(() => repository.documents.save(project.project_id, {
    kind: PROBE_DOC, documentId: "z", payload: { note: undefined, value: 1 },
  }), "SCHEMA_INVALID", "undefined 字段");
  return { codes: [withFunction.code, withBlob.code, withUndefined.code] };
}));

test("D04", "超大 JSON 载荷被拒绝（图片必须进 assets）", () => withRepo(async ({ repository }) => {
  const project = await repository.projects.create({ name: "大小验证" });
  const outcome = await expectCode(() => repository.documents.save(project.project_id, {
    kind: PROBE_DOC, documentId: "big", payload: { text: "x".repeat(1_000_001) },
  }), "SCHEMA_INVALID", "超大载荷");
  expect(outcome.message.includes("assets"), "错误信息应指出图片应存 assets");
  return { message: outcome.message };
}));

test("D05", "不同 document_id / kind 互不影响", () => withRepo(async ({ repository }) => {
  const project = await repository.projects.create({ name: "隔离验证" });
  await repository.documents.save(project.project_id, { kind: PROBE_DOC, documentId: "a", payload: { v: 1 } });
  await repository.documents.save(project.project_id, { kind: PROBE_DOC, documentId: "b", payload: { v: 2 } });
  await repository.documents.save(project.project_id, { kind: "probe_other", documentId: "a", payload: { v: 3 } });
  const sameKind = await repository.documents.listLatest(project.project_id, PROBE_DOC);
  expect(sameKind.length === 2, "同 kind 下应有 2 个文档，实际 " + sameKind.length);
  const latestA = await repository.documents.getLatest(project.project_id, PROBE_DOC, "a");
  expect(latestA.payload.v === 1, "a 的内容不得被 b 覆盖");
  return { same_kind: sameKind.map((item) => item.document_id) };
}));

/* ---------- 资产 Blob ---------- */

test("A01", "资产往返：sha256、字节数与 Blob 内容一致", () => withRepo(async ({ repository }) => {
  const project = await repository.projects.create({ name: "资产验证" });
  const bytes = utf8Bytes("product-reference-image-bytes-0123456789");
  const stored = await repository.assets.put(project.project_id, {
    bytes, mediaType: "image/png", originalName: "参考图.png", role: "primary", width: 1200, height: 900,
  });
  expect(/^[0-9a-f]{64}$/.test(stored.sha256), "sha256 格式不符：" + stored.sha256);
  expect(stored.byte_size === bytes.byteLength, "byte_size 不符");
  const fetched = await repository.assets.get(project.project_id, stored.sha256);
  const roundTrip = new Uint8Array(await fetched.blob.arrayBuffer());
  expect(roundTrip.length === bytes.length && roundTrip.every((value, index) => value === bytes[index]),
    "读回的字节应与写入一致");
  expect(fetched.media_type === "image/png" && fetched.original_name === "参考图.png",
    "媒体信息应保留");
  return { sha256: stored.sha256, byte_size: stored.byte_size, media_type: fetched.media_type };
}));

test("A02", "同样字节重复写入只保留一份（内容寻址幂等）", () => withRepo(async ({ repository }) => {
  const project = await repository.projects.create({ name: "幂等验证" });
  const bytes = utf8Bytes("same-bytes");
  const first = await repository.assets.put(project.project_id, { bytes, mediaType: "image/png" });
  const second = await repository.assets.put(project.project_id, { bytes, mediaType: "image/png" });
  const list = await repository.assets.list(project.project_id);
  expect(first.asset_key === second.asset_key, "同字节应得到同 asset_key");
  expect(list.length === 1, "同字节只应存一份，实际 " + list.length);
  return { asset_key: first.asset_key, count: list.length };
}));

test("A03", "相同字节在不同项目各自独立，删除互不影响", () => withRepo(async ({ repository }) => {
  const projectA = await repository.projects.create({ name: "项目 A" });
  const projectB = await repository.projects.create({ name: "项目 B" });
  const bytes = utf8Bytes("shared-bytes-across-projects");
  const storedA = await repository.assets.put(projectA.project_id, { bytes, mediaType: "image/png" });
  const storedB = await repository.assets.put(projectB.project_id, { bytes, mediaType: "image/png" });
  expect(storedA.sha256 === storedB.sha256, "字节相同则 sha256 相同");
  expect(storedA.asset_key !== storedB.asset_key, "不同项目不得共用一条记录");
  await repository.assets.remove(projectA.project_id, storedA.sha256);
  const listA = await repository.assets.list(projectA.project_id);
  const listB = await repository.assets.list(projectB.project_id);
  expect(listA.length === 0 && listB.length === 1, "删除 A 不得影响 B");
  return { list_a: listA.length, list_b: listB.length };
}));

/* ---------- 事务 ---------- */

test("T01", "事务中抛错：同一事务的写入全部回滚", () => withRepo(async ({ db, repository }) => {
  const project = await repository.projects.create({ name: "回滚验证" });
  const before = await rawCount(db, "documents");
  const timestamp = new Date().toISOString();
  const outcome = await expectCode(() => withTransaction(db, ["documents"], "readwrite", async (tx) => {
    await requestToPromise(tx.objectStore("documents").add({
      document_key: "probe-rollback", project_id: project.project_id, kind: PROBE_DOC,
      document_id: "rollback", version: 1, schema_version: 1, payload: { ok: true },
      created_at: timestamp, updated_at: timestamp,
    }));
    throw new Error("故意失败");
  }), "TRANSACTION_ABORTED", "事务回滚");
  const after = await rawCount(db, "documents");
  expect(after === before, "回滚后文档数应仍为 " + before + "，实际 " + after);
  return { before, after, code: outcome.code };
}));

test("T02", "同一版本并发写：恰好一个成功，版本只加一", () => withRepo(async ({ repository }) => {
  const project = await repository.projects.create({ name: "并发验证" });
  await repository.documents.save(project.project_id, {
    kind: PROBE_DOC, documentId: "plan", payload: { writer: "base" },
  });
  const settled = await Promise.allSettled([
    repository.documents.save(project.project_id, {
      kind: PROBE_DOC, documentId: "plan", payload: { writer: "A" }, expectedVersion: 1,
    }),
    repository.documents.save(project.project_id, {
      kind: PROBE_DOC, documentId: "plan", payload: { writer: "B" }, expectedVersion: 1,
    }),
  ]);
  const winners = settled.filter((item) => item.status === "fulfilled");
  const losers = settled.filter((item) => item.status === "rejected")
    .map((item) => item.reason && item.reason.code);
  const history = await repository.documents.listVersions(project.project_id, PROBE_DOC, "plan");
  expect(winners.length === 1, "应恰好一个赢家，实际 " + winners.length);
  expect(losers.length === 1 && losers[0] === "REVISION_CONFLICT",
    "输家应为 REVISION_CONFLICT，实际 " + JSON.stringify(losers));
  expect(history.length === 2 && history[0].version === 2,
    "最终应恰好两个版本，实际 " + JSON.stringify(history.map((item) => item.version)));
  return { winners: winners.length, losers, versions: history.map((item) => item.version) };
}));

/* ---------- 指针 ---------- */

test("L01", "localStorage 只存当前项目指针，且不含业务数据", () => withRepo(async ({ repository }) => {
  localStorage.clear();
  const project = await repository.projects.create({ name: "指针验证" });
  await repository.documents.save(project.project_id, {
    kind: PROBE_DOC, documentId: "brief", payload: { note: "x".repeat(500) },
  });
  await repository.assets.put(project.project_id, {
    bytes: utf8Bytes("fake-image-bytes"), mediaType: "image/png", originalName: "ref.png",
  });
  await repository.pointer.set(project.project_id);
  const keys = pointerKeys();
  expect(JSON.stringify(keys) === JSON.stringify([CURRENT_PROJECT_POINTER_KEY]),
    "localStorage 键应只有指针，实际 " + JSON.stringify(keys));
  const raw = localStorage.getItem(CURRENT_PROJECT_POINTER_KEY);
  expect(raw.length <= 512, "指针超过 512 字节");
  const parsed = JSON.parse(raw);
  expect(JSON.stringify(Object.keys(parsed).sort()) === JSON.stringify(["project_id", "updated_at"]),
    "指针字段应只有 project_id/updated_at，实际 " + Object.keys(parsed).join(","));
  expect(!raw.includes("fake-image") && !raw.includes("data:"), "指针疑似携带图片数据");
  return { keys, pointer_bytes: raw.length };
}));

test("L02", "指针指向已删除项目：读取返回 null 并自愈清除", () => withRepo(async ({ repository }) => {
  localStorage.clear();
  writePointer({ project_id: crypto.randomUUID(), updated_at: new Date().toISOString() });
  const current = await repository.pointer.get();
  expect(current === null, "过期指针应解析为 null");
  expect(localStorage.getItem(CURRENT_PROJECT_POINTER_KEY) === null, "过期指针应被清除");
  return { cleared: true };
}));

test("L03", "损坏指针：读取返回 null 并自愈清除，不抛错", () => withRepo(async ({ repository }) => {
  localStorage.clear();
  localStorage.setItem(CURRENT_PROJECT_POINTER_KEY, "{ 这不是 JSON");
  const current = await repository.pointer.get();
  expect(current === null, "损坏指针应解析为 null");
  expect(localStorage.getItem(CURRENT_PROJECT_POINTER_KEY) === null, "损坏指针应被清除");
  localStorage.setItem(CURRENT_PROJECT_POINTER_KEY,
    JSON.stringify({ project_id: "x", updated_at: new Date().toISOString(), payload: "nope" }));
  const again = await repository.pointer.get();
  expect(again === null, "多字段指针应被拒绝");
  return { cleared: true };
}));

test("L04", "把指针指向不存在的项目：NOT_FOUND 且不写指针", () => withRepo(async ({ repository }) => {
  localStorage.clear();
  const outcome = await expectCode(
    () => repository.pointer.set(crypto.randomUUID()), "NOT_FOUND", "未知项目指针");
  expect(localStorage.getItem(CURRENT_PROJECT_POINTER_KEY) === null, "失败时不得写入指针");
  return { code: outcome.code };
}));

test("L05", "创建项目并设指针后可以按指针取回该项目", () => withRepo(async ({ repository }) => {
  localStorage.clear();
  const project = await repository.projects.create({ name: "取回验证" });
  await repository.pointer.set(project.project_id);
  const current = await repository.pointer.get();
  expect(current && current.project_id === project.project_id, "指针应取回同一项目");
  repository.pointer.clear();
  expect(await repository.pointer.get() === null, "清除后指针应为 null");
  return { project_id: project.project_id };
}));

/* ---------- 迁移 ---------- */

function probeMigrations() {
  const v1 = [{
    version: 1,
    describe: "probe v1",
    apply(db) {
      const store = db.createObjectStore("items", { keyPath: "id" });
      store.createIndex("by_kind", "kind", { unique: false });
    },
  }];
  const v2 = [...v1, {
    version: 2,
    describe: "probe v2",
    apply(db) {
      db.createObjectStore("notes", { keyPath: "id" });
    },
  }];
  return { v1, v2 };
}

test("M01", "迁移 v1→v2：追加对象仓且旧数据保留", async () => {
  const name = newDbName("amz-v2-migrate");
  const { v1, v2 } = probeMigrations();
  const first = await openDatabase({ name, migrations: v1 });
  try {
    expect(first.version === 1, "首次打开版本应为 1");
    await rawPut(first, "items", { id: "a", kind: "k", value: 1 });
  } finally {
    first.close();
  }
  const second = await openDatabase({ name, migrations: v2 });
  try {
    expect(second.version === 2, "迁移后版本应为 2，实际 " + second.version);
    const item = await rawGet(second, "items", "a");
    expect(item && item.value === 1, "迁移后旧数据应保留");
    expect(second.objectStoreNames.contains("notes"), "迁移后应出现 notes 仓");
    return { version: second.version, stores: Array.from(second.objectStoreNames).sort() };
  } finally {
    second.close();
    await dropDatabase(name);
  }
});

test("M02", "代码版本低于数据库版本：SCHEMA_TOO_NEW，且数据不丢", async () => {
  const name = newDbName("amz-v2-downgrade");
  const { v1, v2 } = probeMigrations();
  const first = await openDatabase({ name, migrations: v2 });
  try {
    await rawPut(first, "items", { id: "keep", kind: "k", value: 42 });
  } finally {
    first.close();
  }
  const outcome = await expectCode(
    () => openDatabase({ name, migrations: v1 }), "SCHEMA_TOO_NEW", "降级打开");
  const reopened = await openDatabase({ name, migrations: v2 });
  try {
    const item = await rawGet(reopened, "items", "keep");
    expect(item && item.value === 42, "降级被拒后数据应完好");
    return { code: outcome.code, value: item.value };
  } finally {
    reopened.close();
    await dropDatabase(name);
  }
});

test("M03", "迁移抛错：升级事务回滚，不留下半个 schema", async () => {
  const name = newDbName("amz-v2-broken");
  const broken = [{
    version: 1,
    describe: "broken",
    apply(db) {
      db.createObjectStore("partial", { keyPath: "id" });
      throw new Error("迁移故意失败");
    },
  }];
  const outcome = await expectCode(
    () => openDatabase({ name, migrations: broken }), "TRANSACTION_ABORTED", "失败迁移");
  const good = [{
    version: 1,
    describe: "good",
    apply(db) {
      db.createObjectStore("ok", { keyPath: "id" });
    },
  }];
  const reopened = await openDatabase({ name, migrations: good });
  try {
    expect(reopened.objectStoreNames.contains("ok"), "重开后应有 ok 仓");
    expect(!reopened.objectStoreNames.contains("partial"), "失败迁移的 partial 不得残留");
    return { code: outcome.code, stores: Array.from(reopened.objectStoreNames).sort() };
  } finally {
    reopened.close();
    await dropDatabase(name);
  }
});

test("M04", "真实 v1 项目升级：数值最新版、历史、资产与 OCC 保持一致", async () => {
  const name = newDbName("amz-v2-real-upgrade");
  const old = await openStorage({ name, migrations: DEFAULT_MIGRATIONS.slice(0, 1) });
  let project;
  let asset;
  try {
    project = await old.repository.projects.create({ name: "旧库升级" });
    asset = await old.repository.assets.put(project.project_id, {
      bytes: utf8Bytes("upgrade-asset-preserved"), mediaType: "image/png", originalName: "old.png",
    });
    for (const documentId of ["a", "a:x", "中文"]) {
      for (const version of [1, 9, 10, 100]) {
        await rawPut(old.db, "documents", {
          document_key: documentKeyOf(project.project_id, PROBE_DOC, documentId, version),
          project_id: project.project_id, kind: PROBE_DOC, document_id: documentId,
          version, schema_version: 1, payload: { documentId, version },
          created_at: project.created_at, updated_at: project.updated_at,
        });
      }
    }
  } finally {
    old.close();
  }
  const upgraded = await openStorage({ name });
  try {
    const repo = upgraded.repository;
    const latest = await repo.documents.listLatest(project.project_id, PROBE_DOC);
    const expectedIds = ["a", "a:x", "中文"].sort((a, b) => a.localeCompare(b));
    expect(JSON.stringify(latest.map((row) => row.document_id)) === JSON.stringify(expectedIds),
      "升级后最新版列表必须保留全部独立文档及原排序");
    expect(latest.every((row) => row.version === 100 && row.payload.version === 100),
      "最新版必须按数值取 100，不能取字符串排序的 9");
    expect(await repo.documents.getLatest(project.project_id, PROBE_DOC, "missing") === null,
      "不存在文档必须返回 null");
    expect((await repo.documents.listLatest(project.project_id, "absent")).length === 0,
      "不存在 kind 不得返回相邻 kind");
    const retained = await repo.assets.get(project.project_id, asset.sha256);
    expect(await retained.blob.text() === "upgrade-asset-preserved", "升级后资产字节不得改变");
    expect(JSON.stringify(await repo.projects.get(project.project_id)) === JSON.stringify(project),
      "升级不得重写项目元数据");
    const history = await repo.documents.listVersions(project.project_id, PROBE_DOC, "a");
    expect(JSON.stringify(history.map((row) => row.payload.version)) === "[100,10,9,1]",
      "升级必须保留完整历史及各版本载荷");
    const writes = await Promise.allSettled([101, 102].map((value) => repo.documents.save(project.project_id, {
      kind: PROBE_DOC, documentId: "a", expectedVersion: 100, payload: { value },
    })));
    expect(writes.filter((row) => row.status === "fulfilled").length === 1, "OCC 必须只有一个赢家");
    expect(writes.filter((row) => row.status === "rejected")
      .every((row) => row.reason.code === "REVISION_CONFLICT"), "OCC 输家必须得到可见冲突");
    expect((await repo.documents.getLatest(project.project_id, PROBE_DOC, "a")).version === 101,
      "升级后保存必须在数值版本头上仅追加一次");
    return { old_version: 1, new_version: upgraded.db.version,
      latest_versions: latest.map((row) => row.version), history_versions: history.map((row) => row.version) };
  } finally {
    upgraded.close();
    await dropDatabase(name);
  }
});

/* ---------- 运行器 ---------- */

function render(results) {
  const target = document.getElementById("results");
  if (!target) return;
  target.textContent = JSON.stringify(results, null, 2);
}

async function runSuite() {
  const results = {
    suite: "v2.1.1-storage-contract",
    status: "running",
    started_at: new Date().toISOString(),
    cases: [],
  };
  window.__V2_STORAGE_RESULTS__ = results;
  localStorage.clear();
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
    window.__V2_STORAGE_RESULTS__ = {
      suite: "v2.1.1-storage-contract",
      status: "crashed",
      error: serializeError(error),
      cases: [],
    };
    render(window.__V2_STORAGE_RESULTS__);
  });
} else {
  window.__V2_STORAGE_RESULTS__ = { suite: "v2.1.1-storage-contract", status: "skipped", cases: [] };
}
