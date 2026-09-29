/**
 * Product V2 存储层入口：一次打开数据库并拿到仓库。
 * 后续模块（项目首页、商品理解、生成、交付）只依赖这里的 repository 接口。
 */

export * from "./errors.js";
export * from "./schema.js";
export * from "./validate.js";
export * from "./db.js";
export * from "./migrations.js";
export * from "./pointer.js";
export * from "./repository.js";
export * from "./zip.js";
export * from "./package.js";
export * from "./transfer.js";

import { openDatabase } from "./db.js";
import { createRepository } from "./repository.js";

export async function openStorage(options = {}) {
  const db = await openDatabase(options);
  const repository = createRepository({
    db,
    storage: options.storage,
    now: options.now,
    newId: options.newId,
    digest: options.digest,
  });
  return {
    db,
    repository,
    close() {
      db.close();
    },
  };
}
