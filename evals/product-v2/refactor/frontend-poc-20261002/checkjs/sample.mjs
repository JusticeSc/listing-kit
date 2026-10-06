import { invalidationsFor } from "../../../../../app/product_v2/domain/invalidation.js";

const result = invalidationsFor("shot_spec_changed", { shotId: "shot-main" });
if (result.scope !== "shot" || result.target_shot_id !== "shot-main") {
  throw new Error("单图规格变化必须保持目标图身份与单图影响范围。");
}
if (!result.preserves.includes("other_shots") || !result.preserves.includes("candidate_blobs")) {
  throw new Error("单图变化不得丢弃无关图或候选字节。");
}
console.log("poc-invalidation:", result.scope, result.target_shot_id);
