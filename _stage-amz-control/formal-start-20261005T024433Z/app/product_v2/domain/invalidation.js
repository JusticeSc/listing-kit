/**
 * 失效图（V2.2.1，计划 §4.4）：一次变化必须失效什么、必须保留什么。
 *
 * 两条容易写错的边界在这里被写成判据：
 *  - 失效 ≠ 删除：project_history 与 candidate_blobs 永远在 preserves 里。
 *  - 影响范围要精确：改一张图的规格或提示词，不许连带失效别的 Shot。
 */

import { invalid } from "./errors.js";

export const CHANGE_KINDS = Object.freeze([
  "references_changed",
  "identity_fact_changed",
  "fact_value_changed",
  "style_changed",
  "shot_spec_changed",
  "prompt_edited",
  "shot_added_or_removed",
]);

const NEVER_INVALIDATED = Object.freeze(["project_history", "candidate_blobs"]);

/**
 * @typedef {{shotId?: string, shotIds?: string[], briefUsesSlot?: boolean}} InvalidationContext
 * @typedef {{scope: string, invalidates: readonly string[], preserves: readonly string[]}} InvalidationRule
 * @type {Readonly<Record<string, InvalidationRule>>}
 */
export const INVALIDATION_TABLE = Object.freeze({
  references_changed: Object.freeze({
    scope: "project",
    invalidates: Object.freeze(["product_brief", "suite_plan", "prompt_versions", "review_reports", "selection"]),
    preserves: Object.freeze([...NEVER_INVALIDATED, "source_assets"]),
  }),
  identity_fact_changed: Object.freeze({
    scope: "project",
    invalidates: Object.freeze(["product_brief", "suite_plan", "prompt_versions", "review_reports", "selection"]),
    preserves: Object.freeze([...NEVER_INVALIDATED, "source_assets"]),
  }),
  fact_value_changed: Object.freeze({
    scope: "targeted",
    invalidates: Object.freeze(["suite_plan", "prompt_versions", "review_reports", "selection"]),
    preserves: Object.freeze([...NEVER_INVALIDATED, "unreferenced_shots", "source_assets", "product_brief"]),
  }),
  style_changed: Object.freeze({
    scope: "project",
    invalidates: Object.freeze(["prompt_versions", "review_reports", "suite_consistency_report"]),
    preserves: Object.freeze([...NEVER_INVALIDATED, "product_brief", "suite_plan", "source_assets"]),
  }),
  shot_spec_changed: Object.freeze({
    scope: "shot",
    invalidates: Object.freeze(["prompt_versions", "review_reports", "selection"]),
    preserves: Object.freeze([...NEVER_INVALIDATED, "product_brief", "suite_plan", "other_shots", "source_assets"]),
  }),
  prompt_edited: Object.freeze({
    scope: "shot",
    invalidates: Object.freeze(["prompt_versions", "review_reports", "selection"]),
    preserves: Object.freeze([...NEVER_INVALIDATED, "product_brief", "suite_plan", "shot_spec", "other_shots"]),
  }),
  shot_added_or_removed: Object.freeze({
    scope: "suite",
    invalidates: Object.freeze(["suite_plan_revision", "selection_completeness", "suite_consistency_report"]),
    preserves: Object.freeze([...NEVER_INVALIDATED, "existing_shot_history", "source_assets"]),
  }),
});

/**
 * @param {string} changeKind
 * @param {InvalidationContext} [context]
 * @returns {{kind: string, scope: string, invalidates: string[], preserves: string[], target_shot_id: string | null}}
 */
export function invalidationsFor(changeKind, context = {}) {
  const rule = INVALIDATION_TABLE[changeKind];
  if (!rule) invalid("未知变化类型 " + JSON.stringify(changeKind) + "。", { change_kind: changeKind });
  const result = {
    kind: changeKind,
    scope: rule.scope,
    invalidates: [...rule.invalidates],
    preserves: [...rule.preserves],
    target_shot_id: context.shotId || null,
  };
  if (changeKind === "fact_value_changed") {
    const shotIds = Array.isArray(context.shotIds) ? context.shotIds : [];
    result.invalidates = [];
    if (context.briefUsesSlot === true) result.invalidates.push("product_brief");
    for (const shotId of shotIds) {
      result.invalidates.push("shot:" + shotId + ":prompt", "shot:" + shotId + ":review", "shot:" + shotId + ":selection");
    }
  }
  if ((changeKind === "shot_spec_changed" || changeKind === "prompt_edited") && !context.shotId) {
    invalid("变化类型 " + changeKind + " 必须带 shotId，否则无法把影响限制在目标 Shot。");
  }
  return result;
}
