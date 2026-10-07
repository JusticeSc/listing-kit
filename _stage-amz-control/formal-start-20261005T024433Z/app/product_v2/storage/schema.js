/**
 * Product V2 浏览器数据库的唯一 schema 出处。
 *
 * 库名与 Product V1 / legacy v2 不同，两个世代互不触碰；localStorage 只允许
 * 保存轻量指针（见 pointer.js），任何图片、候选或完整项目都不许进去。
 *
 * 规则：已发布的 v1 存储结构不允许原地修改。新增对象仓或索引必须追加迁移
 * （migrations.js），并同时更新本文件的 STORE_SPECS 作为"应该长什么样"的判据。
 * 契约测试会用 describeDatabase() 与 STORE_SPECS 对比，检出未走迁移的 schema 漂移。
 */

export const DB_NAME = "amz-listing-kit-v2";
export const STORAGE_SCHEMA_VERSION = 2;
export const RECORD_SCHEMA_VERSION = 1;

/** 项目状态词表（Product V2 计划 §6.1）。状态由对象关系派生，界面不得自由赋值。 */
export const PROJECT_STATES = Object.freeze([
  "EMPTY",
  "INTAKE_READY",
  "UNDERSTANDING_REVIEW",
  "PLAN_REVIEW",
  "READY_TO_GENERATE",
  "GENERATING",
  "REVIEWING",
  "READY_TO_EXPORT",
  "EXPORTED",
]);

/** 文档种类只做格式约束；具体契约由后续任务（V2.2.1 起）逐个落位。 */
export const DOCUMENT_KIND_PATTERN = /^[a-z][a-z0-9_]{1,48}$/;

function freezeStore(name, keyPath, indexes) {
  return Object.freeze({
    name,
    keyPath,
    autoIncrement: false,
    indexes: Object.freeze(indexes.map((index) => Object.freeze({
      name: index.name,
      keyPath: index.keyPath,
      unique: false,
      multiEntry: false,
    }))),
  });
}

/**
 * v1 对象仓：
 * - projects  项目元数据与身份（不含商品内容）
 * - assets    内容寻址的 Blob（键是 project_id + sha256，跨项目不串）
 * - documents 版本化 JSON（键是 project_id + kind + document_id + version，append-only）
 */
export const STORE_SPECS = Object.freeze([
  freezeStore("projects", "project_id", [
    { name: "by_updated_at", keyPath: "updated_at" },
  ]),
  freezeStore("assets", "asset_key", [
    { name: "by_project_id", keyPath: "project_id" },
    { name: "by_sha256", keyPath: "sha256" },
  ]),
  freezeStore("documents", "document_key", [
    { name: "by_project_kind", keyPath: ["project_id", "kind"] },
    { name: "by_project_document", keyPath: ["project_id", "kind", "document_id"] },
    { name: "by_project_document_version", keyPath: ["project_id", "kind", "document_id", "version"] },
  ]),
]);

export const STORE_NAMES = Object.freeze(STORE_SPECS.map((spec) => spec.name));

function normalizeKeyPath(keyPath) {
  return Array.isArray(keyPath) ? [...keyPath] : [keyPath];
}

function normalizeSpec(spec) {
  return {
    name: spec.name,
    keyPath: normalizeKeyPath(spec.keyPath),
    autoIncrement: Boolean(spec.autoIncrement),
    indexes: [...spec.indexes]
      .map((index) => ({
        name: index.name,
        keyPath: normalizeKeyPath(index.keyPath),
        unique: Boolean(index.unique),
        multiEntry: Boolean(index.multiEntry),
      }))
      .sort((a, b) => a.name.localeCompare(b.name)),
  };
}

/** 代码认为数据库"应该长什么样"。 */
export function expectedSchemaShape(specs = STORE_SPECS) {
  return specs
    .map((spec) => normalizeSpec(spec))
    .sort((a, b) => a.name.localeCompare(b.name));
}

/** 数据库实际长什么样；只读事务，不改任何数据。 */
export function describeDatabase(db) {
  const described = [];
  for (const name of Array.from(db.objectStoreNames).sort()) {
    const store = db.transaction(name, "readonly").objectStore(name);
    const indexes = Array.from(store.indexNames).sort().map((indexName) => {
      const index = store.index(indexName);
      return {
        name: indexName,
        keyPath: normalizeKeyPath(index.keyPath),
        unique: Boolean(index.unique),
        multiEntry: Boolean(index.multiEntry),
      };
    });
    described.push({
      name,
      keyPath: normalizeKeyPath(store.keyPath),
      autoIncrement: Boolean(store.autoIncrement),
      indexes,
    });
  }
  return described;
}

/** 返回人读漂移清单；空数组表示实际结构与 STORE_SPECS 一致。 */
export function schemaDrift(db, specs = STORE_SPECS) {
  const expected = expectedSchemaShape(specs);
  const actual = describeDatabase(db);
  const problems = [];
  const expectedByName = new Map(expected.map((item) => [item.name, item]));
  const actualByName = new Map(actual.map((item) => [item.name, item]));

  for (const item of expected) {
    const live = actualByName.get(item.name);
    if (!live) {
      problems.push("缺少对象仓 " + item.name);
      continue;
    }
    if (JSON.stringify(live.keyPath) !== JSON.stringify(item.keyPath)) {
      problems.push("对象仓 " + item.name + " 的 keyPath 是 " + JSON.stringify(live.keyPath)
        + "，应为 " + JSON.stringify(item.keyPath));
    }
    const liveIndexes = new Map(live.indexes.map((index) => [index.name, index]));
    for (const index of item.indexes) {
      const liveIndex = liveIndexes.get(index.name);
      if (!liveIndex) {
        problems.push("对象仓 " + item.name + " 缺少索引 " + index.name);
        continue;
      }
      if (JSON.stringify(liveIndex.keyPath) !== JSON.stringify(index.keyPath)) {
        problems.push("索引 " + item.name + "." + index.name + " 的 keyPath 是 "
          + JSON.stringify(liveIndex.keyPath) + "，应为 " + JSON.stringify(index.keyPath));
      }
      if (liveIndex.unique !== index.unique) {
        problems.push("索引 " + item.name + "." + index.name + " 的 unique="
          + liveIndex.unique + "，应为 " + index.unique);
      }
    }
    for (const index of live.indexes) {
      if (!item.indexes.some((expectedIndex) => expectedIndex.name === index.name)) {
        problems.push("对象仓 " + item.name + " 多出未登记索引 " + index.name);
      }
    }
  }
  for (const item of actual) {
    if (!expectedByName.has(item.name)) {
      problems.push("多出未登记对象仓 " + item.name);
    }
  }
  return problems;
}
