/**
 * 当前项目包载荷版本边界：写入事务前拒绝不支持的 schema。
 * 不迁移旧格式、不修改历史报告、不补造执行身份。
 */
import { STORAGE_ERROR_CODES, StorageError } from "./errors.js";

type PayloadSchemaVersionMap = Readonly<Partial<Record<string, number>>>;
type EntryIdentity = { kind: unknown; document_id: unknown; version: unknown };
type PayloadEntry = { kind: string; document_id: string; version: number; payload: unknown };

export const PAYLOAD_SCHEMA_VERSIONS: PayloadSchemaVersionMap = Object.freeze({
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

/** Attempt schema 2 才有冻结执行身份；旧记录整体拒绝，不做 legacy 映射。 */
export const MIN_PAYLOAD_SCHEMA_VERSIONS: PayloadSchemaVersionMap = Object.freeze({
  generation_attempt: 2,
});

export function entryLabel(record: EntryIdentity): string {
  return String(record.kind) + "/" + String(record.document_id) + "/v" + String(record.version);
}

export function assertPayloadSchemaSupported(record: PayloadEntry): void {
  const max = PAYLOAD_SCHEMA_VERSIONS[record.kind];
  if (max === undefined) return;
  const min = MIN_PAYLOAD_SCHEMA_VERSIONS[record.kind];
  const payload = record.payload;
  const declared = payload && typeof payload === "object" && "schema_version" in payload
    ? payload.schema_version : undefined;
  if (typeof declared !== "number" || !Number.isInteger(declared)) {
    if (min !== undefined) {
      throw new StorageError(STORAGE_ERROR_CODES.PACKAGE_UNSUPPORTED_VERSION,
        "无法导入：文档 " + entryLabel(record) + " 缺少当前 payload schema_version；不补造执行身份。");
    }
    return;
  }
  if (declared > max) {
    throw new StorageError(
      STORAGE_ERROR_CODES.PACKAGE_UNSUPPORTED_VERSION,
      "无法导入：文档 " + entryLabel(record) + " 声明的 payload schema_version=" + declared
        + " 高于当前支持的 " + max + "；请用较新版本打开或先导出该记录。",
    );
  }
  if (min !== undefined && declared < min) {
    throw new StorageError(
      STORAGE_ERROR_CODES.PACKAGE_UNSUPPORTED_VERSION,
      "无法导入：文档 " + entryLabel(record) + " 声明的 payload schema_version=" + declared
        + " 低于当前要求的 " + min + "（该记录缺少冻结执行身份，不做 legacy 映射、"
        + "不部分写入）；按计划 §2.3 整包拒绝。",
    );
  }
}
