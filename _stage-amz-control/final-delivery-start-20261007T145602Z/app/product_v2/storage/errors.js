/**
 * Product V2 存储层错误词表。
 *
 * 存储层不允许用"失败"掩盖语义：调用方必须能区分输入非法、版本冲突、
 * 数据不存在、浏览器不支持、配额不足。每个错误都带稳定 code，
 * 界面与测试按 code 断言，不匹配错误文案。
 */

export const STORAGE_ERROR_CODES = /** @type {const} */ (Object.freeze({
  INVALID_ARGUMENT: "INVALID_ARGUMENT",
  SCHEMA_INVALID: "SCHEMA_INVALID",
  SCHEMA_TOO_NEW: "SCHEMA_TOO_NEW",
  REVISION_CONFLICT: "REVISION_CONFLICT",
  NOT_FOUND: "NOT_FOUND",
  DUPLICATE_RECORD: "DUPLICATE_RECORD",
  QUOTA_EXCEEDED: "QUOTA_EXCEEDED",
  UNSUPPORTED_BROWSER: "UNSUPPORTED_BROWSER",
  TRANSACTION_ABORTED: "TRANSACTION_ABORTED",
  PACKAGE_INVALID: "PACKAGE_INVALID",
  PACKAGE_UNSUPPORTED_VERSION: "PACKAGE_UNSUPPORTED_VERSION",
  PACKAGE_HASH_MISMATCH: "PACKAGE_HASH_MISMATCH",
  PACKAGE_TOO_LARGE: "PACKAGE_TOO_LARGE",
  // V2.UI.1：能力缺口细分。界面按 details.gap 归因，不按文案猜原因。
  SECURE_CONTEXT_REQUIRED: "SECURE_CONTEXT_REQUIRED",
  CRYPTO_UNAVAILABLE: "CRYPTO_UNAVAILABLE",
  INDEXEDDB_UNAVAILABLE: "INDEXEDDB_UNAVAILABLE",
  DATABASE_OPEN_FAILED: "DATABASE_OPEN_FAILED",
  TRANSACTION_UNAVAILABLE: "TRANSACTION_UNAVAILABLE",
}));

/** 稳定错误码（界面/测试按 code 断言）。@typedef {typeof STORAGE_ERROR_CODES[keyof typeof STORAGE_ERROR_CODES]} StorageErrorCode */

/**
 * 能力缺口词表（V2.UI.1）：探针、错误 details 与界面诊断共用同一套取值。
 * - secure_context  当前来源不是安全上下文（远程明文 HTTP），WebCrypto 被浏览器禁用
 * - indexeddb       宿主没有 IndexedDB 工厂
 * - database_open   目标数据库打不开（存储被禁用、数据损坏等）
 * - random_uuid     安全来源但缺 crypto.randomUUID
 * - webcrypto       安全来源但缺 crypto.subtle
 * - transaction     目标库上无法完成最小读写事务
 */
export const CAPABILITY_GAPS = /** @type {const} */ (Object.freeze({
  SECURE_CONTEXT: "secure_context",
  INDEXEDDB: "indexeddb",
  DATABASE_OPEN: "database_open",
  RANDOM_UUID: "random_uuid",
  WEBCRYPTO: "webcrypto",
  TRANSACTION: "transaction",
}));

/** 能力缺口取值（探针、错误 details 与界面诊断共用）。@typedef {typeof CAPABILITY_GAPS[keyof typeof CAPABILITY_GAPS]} CapabilityGap */

export class StorageError extends Error {
  /**
   * @param {StorageErrorCode} code 稳定错误码
   * @param {string} message
   * @param {null|Record<string, unknown>} [details] 仅词表内字段；界面/测试按 code/details 断言
   */
  constructor(code, message, details = null) {
    super(message);
    this.name = "StorageError";
    /** @type {StorageErrorCode} */
    this.code = code;
    /** @type {null|Record<string, unknown>} */
    this.details = details;
  }

  /** @returns {{name:"StorageError",code:StorageErrorCode,message:string,details:null|Record<string,unknown>}} */
  toJSON() {
    return { name: /** @type {const} */ ("StorageError"), code: this.code, message: this.message, details: this.details };
  }
}

/**
 * WebCrypto 类缺口的统一构造：非安全来源与「安全来源但缺 API」是两种归因——
 * 前者改用 HTTPS 即可恢复，后者只能升级浏览器；错误码与 details.gap 必须能区分。
 */
/**
 * @param {CapabilityGap} gap
 * @param {string} message
 * @returns {StorageError}
 */
export function cryptoCapabilityError(gap, message) {
  const globalObject = typeof globalThis !== "undefined" ? globalThis : null;
  const location = globalObject ? globalObject.location : null;
  const origin = location && typeof location.origin === "string" ? location.origin : "";
  // isSecureContext 是 window/global 的属性，不在 Location 上。
  const insecure = Boolean(globalObject && globalObject.isSecureContext === false);
  if (insecure) {
    return new StorageError(
      STORAGE_ERROR_CODES.SECURE_CONTEXT_REQUIRED,
      message + " 当前来源 " + (origin || "（未知）") + " 不是安全上下文（HTTPS 或 localhost），浏览器禁用了 WebCrypto；请改用 HTTPS 入口。",
      { gap: CAPABILITY_GAPS.SECURE_CONTEXT, origin, secure_context: false, missing: gap },
    );
  }
  return new StorageError(
    STORAGE_ERROR_CODES.CRYPTO_UNAVAILABLE,
    message + " 当前浏览器缺少该 WebCrypto 能力（" + gap + "）。",
    { gap, origin, secure_context: true, missing: gap },
  );
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

/**
 * @param {{name?:string,message?:string}|StorageError|null|undefined|string} error
 * @param {StorageErrorCode} [fallbackCode=STORAGE_ERROR_CODES.TRANSACTION_ABORTED]
 * @returns {StorageError}
 */
export function toStorageError(error, fallbackCode = STORAGE_ERROR_CODES.TRANSACTION_ABORTED) {
  if (error instanceof StorageError) {
    return error;
  }
  const detail = error && typeof error === "object" ? error : null;
  const name = detail && typeof detail.name === "string" ? detail.name : "";
  const code = DOM_EXCEPTION_CODES[name] || fallbackCode;
  const message = detail && detail.message ? String(detail.message) : String(error);
  return new StorageError(code, message, { cause_name: name || null });
}
