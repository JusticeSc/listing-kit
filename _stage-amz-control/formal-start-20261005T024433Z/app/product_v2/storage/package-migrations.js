/**
 * 项目包迁移链（V2.6.3）。
 *
 * 职责边界：
 *  - 只处理「包格式」与「记录形状」的升级，不改写业务事实、不重算报告、不补默认事实。
 *  - 迁移在事务外跟随解析执行：先按当前格式完整校验，再按链逐级升级；任何一步无法升级
 *    都带精确条目（kind/document_id/version）拒绝导入，不做静默降级。
 *  - PAYLOAD_SCHEMA_VERSIONS / CURRENT_REVIEW_CONTRACT_VERSION 是 storage 层对 domain 常量的
 *    镜像（storage 不反向依赖 domain）；V2.6.3 验证器逐条比对，漂移会被测出来。
 */

import { STORAGE_ERROR_CODES, StorageError } from "./errors.js";

export const MIGRATION_CONTRACT_VERSION = "v2.6.3";

/** 文档种类 → 当前 payload schema_version。 */
export const PAYLOAD_SCHEMA_VERSIONS = Object.freeze({
  product_input: 1,
  fact_slot: 1,
  product_brief: 1,
  suite_plan: 1,
  style_spec: 1,
  shot_spec: 1,
  prompt_version: 1,
  generation_confirm: 1,
  generation_attempt: 2,
  candidate: 1,
  review_report: 1,
  selection: 1,
  suite_review: 1,
  export_record: 1,
  review_acknowledgement: 1,
});

/**
 * 低于该值就必须整体拒绝的 kind（V2.R4.4）：generation_attempt 自 schema 2 起要求
 * 冻结执行身份；旧 schema 1 记录不做 legacy 映射（计划 §2.3），导出的旧包按精确条目拒绝。
 */
export const MIN_PAYLOAD_SCHEMA_VERSIONS = Object.freeze({
  generation_attempt: 2,
});

/** 当前复核合同版本（镜像 domain/review.js 的 REVIEW_CONTRACT_VERSION）。 */
export const CURRENT_REVIEW_CONTRACT_VERSION = "v2.5.2";

export function entryLabel(record) {
  return String(record.kind) + "/" + String(record.document_id) + "/v" + String(record.version);
}

/** 记录声明的 payload schema_version 高于当前支持时拒绝，并点名是哪一条。 */
export function assertPayloadSchemaSupported(record) {
  const max = PAYLOAD_SCHEMA_VERSIONS[record.kind];
  if (max === undefined || !record.payload || typeof record.payload !== "object") return;
  const declared = record.payload.schema_version;
  if (!Number.isInteger(declared)) return;
  if (declared > max) {
    throw new StorageError(
      STORAGE_ERROR_CODES.PACKAGE_UNSUPPORTED_VERSION,
      "无法升级：文档 " + entryLabel(record) + " 声明的 payload schema_version=" + declared
        + " 高于当前支持的 " + max + "；请用较新版本打开或先导出该记录。",
    );
  }
  const min = MIN_PAYLOAD_SCHEMA_VERSIONS[record.kind];
  if (min !== undefined && declared < min) {
    throw new StorageError(
      STORAGE_ERROR_CODES.PACKAGE_UNSUPPORTED_VERSION,
      "无法导入：文档 " + entryLabel(record) + " 声明的 payload schema_version=" + declared
        + " 低于当前要求的 " + min + "（该记录缺少冻结执行身份，不做 legacy 映射、"
        + "不部分写入）；按计划 §2.3 整包拒绝。",
    );
  }
}

/**
 * 记录级迁移：只做「旧合同块的结论已不可信，因此丢弃它」这类可验证动作。
 * 丢弃不是降级掩盖——界面会在加载时按当前规则重建确定性报告，旧结论不会被冒充为当前结论。
 */
export const RECORD_MIGRATIONS = Object.freeze([
  Object.freeze({
    kind: "review_report",
    describe: "复核合同版本过期：丢弃 VLM 块（确定性发现保留，加载时按当前规则重算）",
    apply(record) {
      const payload = record.payload;
      if (!payload || typeof payload !== "object") return null;
      if (payload.review_contract_version === CURRENT_REVIEW_CONTRACT_VERSION) return null;
      if (!payload.vlm) return null;
      return Object.freeze({
        ...payload, vlm: null, migrated_from_review_contract: payload.review_contract_version,
      });
    },
  }),
]);

export function migrateRecord(record) {
  let current = record;
  const applied = [];
  for (const migration of RECORD_MIGRATIONS) {
    if (migration.kind !== current.kind) continue;
    const next = migration.apply(current);
    if (next) {
      current = { ...current, payload: next };
      applied.push(entryLabel(record) + "：" + migration.describe);
    }
  }
  return { record: current, applied };
}

/** 包格式迁移链：逐级 +1，缺失中间步骤即拒绝（不跳级、不猜测）。 */
export const PACKAGE_MIGRATIONS = Object.freeze([
  Object.freeze({
    to_version: 2,
    describe: "记录文件自描述（kind/document_id/version/schema_version）+ manifest 完整性计数",
    apply(draft) {
      return {
        ...draft,
        manifest: {
          ...draft.manifest,
          format_version: 2,
          migrated_from_format: draft.manifest.format_version,
        },
      };
    },
  }),
]);

export function migratePackage(draft, { targetVersion }) {
  let current = draft;
  const applied = [];
  let version = draft.manifest.format_version;
  while (version < targetVersion) {
    const step = PACKAGE_MIGRATIONS.find((item) => item.to_version === version + 1);
    if (!step) {
      throw new StorageError(
        STORAGE_ERROR_CODES.PACKAGE_UNSUPPORTED_VERSION,
        "无法升级：项目包格式 " + version + " 没有到 " + (version + 1) + " 的迁移步骤。",
      );
    }
    current = step.apply(current);
    applied.push("包格式 " + version + " → " + step.to_version + "：" + step.describe);
    version = step.to_version;
  }
  return { draft: current, applied };
}
