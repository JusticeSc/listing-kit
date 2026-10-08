/**
 * Product V2 领域契约入口（V2.2.1）。
 * 浏览器界面与后续 provider 只依赖这里的纯函数；它们不碰存储、不碰网络。
 */

export const CONTRACT_VERSION = "v2.2.1";

export * from "./errors.js";
export * from "./shared.js";
export * from "./slots.js";
export * from "./intake.js";
export * from "./brief.js";
export * from "./invalidation.js";
export * from "./suite-plan.js";
export * from "./suite.js";
export * from "./specs.js";
export * from "./prompt.js";
export * from "./confirm.js";
export * from "./attempt.js";
export * from "./batch.js";
export * from "./candidate.js";
export * from "./review.js";
export * from "./compare.js";
export * from "./rework.js";
export * from "./selection.js";
export * from "./suite-review.js";
export * from "./export-gate.js";
