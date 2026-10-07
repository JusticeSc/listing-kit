// @ts-check
/**
 * 领域契约错误（V2.2.1）。
 *
 * 存储层负责"能不能存"，本层负责"是不是一个合法的商品理解对象"。
 * 两层的错误码刻意分开：界面可以据此给出不同的修复指引。
 */

export const DOMAIN_ERROR_CODES = Object.freeze({
  CONTRACT_INVALID: "CONTRACT_INVALID",
  CONTRACT_TRANSITION_ILLEGAL: "CONTRACT_TRANSITION_ILLEGAL",
  CONTRACT_PERMISSION_DENIED: "CONTRACT_PERMISSION_DENIED",
  CONTRACT_DEPENDENCY_CYCLE: "CONTRACT_DEPENDENCY_CYCLE",
  CONTRACT_SCHEMA_TOO_NEW: "CONTRACT_SCHEMA_TOO_NEW",
});

export class DomainError extends Error {
  /**
   * @param {string} code
   * @param {string} message
   * @param {unknown} [details]
   */
  constructor(code, message, details = null) {
    super(message);
    this.name = "DomainError";
    /** @type {string} */
    this.code = code;
    /** @type {unknown} */
    this.details = details;
  }
}

/**
 * @param {string} message
 * @param {unknown} [details]
 * @returns {never}
 */
export function invalid(message, details = null) {
  throw new DomainError(DOMAIN_ERROR_CODES.CONTRACT_INVALID, message, details);
}

/**
 * @param {string} message
 * @param {unknown} [details]
 * @returns {never}
 */
export function illegal(message, details = null) {
  throw new DomainError(DOMAIN_ERROR_CODES.CONTRACT_TRANSITION_ILLEGAL, message, details);
}

/**
 * @param {string} message
 * @param {unknown} [details]
 * @returns {never}
 */
export function denied(message, details = null) {
  throw new DomainError(DOMAIN_ERROR_CODES.CONTRACT_PERMISSION_DENIED, message, details);
}
