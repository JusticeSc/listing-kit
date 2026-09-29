/**
 * Product V2 存储层错误词表。
 *
 * 存储层不允许用"失败"掩盖语义：调用方必须能区分输入非法、版本冲突、
 * 数据不存在、浏览器不支持、配额不足。每个错误都带稳定 code，
 * 界面与测试按 code 断言，不匹配错误文案。
 */

export const STORAGE_ERROR_CODES = Object.freeze({
  INVALID_ARGUMENT: "INVALID_ARGUMENT",
  SCHEMA_INVALID: "SCHEMA_INVALID",
  SCHEMA_TOO_NEW: "SCHEMA_TOO_NEW",
  REVISION_CONFLICT: "REVISION_CONFLICT",
  NOT_FOUND: "NOT_FOUND",
  DUPLICATE_RECORD: "DUPLICATE_RECORD",
  QUOTA_EXCEEDED: "QUOTA_EXCEEDED",
  UNSUPPORTED_BROWSER: "UNSUPPORTED_BROWSER",
  TRANSACTION_ABORTED: "TRANSACTION_ABORTED",
});

export class StorageError extends Error {
  constructor(code, message, details = null) {
    super(message);
    this.name = "StorageError";
    this.code = code;
    this.details = details;
  }

  toJSON() {
    return { name: this.name, code: this.code, message: this.message, details: this.details };
  }
}

const DOM_EXCEPTION_CODES = Object.freeze({
  QuotaExceededError: "QUOTA_EXCEEDED",
  VersionError: "SCHEMA_TOO_NEW",
  ConstraintError: "DUPLICATE_RECORD",
  DataCloneError: "SCHEMA_INVALID",
  DataError: "SCHEMA_INVALID",
  InvalidStateError: "TRANSACTION_ABORTED",
  TransactionInactiveError: "TRANSACTION_ABORTED",
  NotFoundError: "NOT_FOUND",
  AbortError: "TRANSACTION_ABORTED",
  TypeError: "INVALID_ARGUMENT",
});

export function toStorageError(error, fallbackCode = STORAGE_ERROR_CODES.TRANSACTION_ABORTED) {
  if (error instanceof StorageError) {
    return error;
  }
  const name = error && typeof error.name === "string" ? error.name : "";
  const code = DOM_EXCEPTION_CODES[name] || fallbackCode;
  const message = error && error.message ? String(error.message) : String(error);
  return new StorageError(code, message, { cause_name: name || null });
}
