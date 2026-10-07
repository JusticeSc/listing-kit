/**
 * 迁移登记表：数据库结构的每一次变化都必须在这里追加一条，不允许改历史条目。
 * apply(db, tx, {from, to}) 在 IDB 的 versionchange 事务里同步执行；
 * 抛出异常会让整个升级事务回滚，数据库保持在旧版本，不会留下半个 schema。
 */

import { STORE_SPECS, STORAGE_SCHEMA_VERSION } from "./schema.js";

function applyStoreSpec(db, spec) {
  const store = db.createObjectStore(spec.name, {
    keyPath: spec.keyPath,
    autoIncrement: spec.autoIncrement,
  });
  for (const index of spec.indexes) {
    store.createIndex(index.name, index.keyPath, {
      unique: index.unique,
      multiEntry: index.multiEntry,
    });
  }
}

export const DEFAULT_MIGRATIONS = Object.freeze([
  Object.freeze({
    version: 1,
    describe: "创建 projects / assets / documents 与必需索引",
    apply(db) {
      for (const spec of STORE_SPECS) {
        if (!db.objectStoreNames.contains(spec.name)) {
          applyStoreSpec(db, spec);
        }
      }
    },
  }),
]);

if (DEFAULT_MIGRATIONS.length === 0
    || DEFAULT_MIGRATIONS[DEFAULT_MIGRATIONS.length - 1].version !== STORAGE_SCHEMA_VERSION) {
  throw new Error("schema.js 的 STORAGE_SCHEMA_VERSION 与 migrations.js 的最后一条迁移不一致。");
}
