/** 已核图像单价到本次真实请求的费用上界；不读密钥、不查询供应商、不使用历史实耗猜价。 */
import { canonicalJson, isNonEmptyString, isPlainObject } from "./shared.js";

/** @param {unknown} value @param {unknown} provider */
function pricingMatches(value, provider) {
  if (!isPlainObject(value) || !isPlainObject(provider) || value.version !== 1
      || value.currency !== "CNY" || value.provider_id !== provider.provider_id
      || value.model_id !== provider.model_id || value.size !== provider.size
      || value.n !== provider.n || value.n !== 1 || value.output_format !== provider.output_format
      || !Number.isSafeInteger(value.input_image_fen) || value.input_image_fen < 0
      || !Number.isSafeInteger(value.output_image_fen) || value.output_image_fen < 0) return false;
  if (value.kind === "test_double") {
    return String(value.provider_id).startsWith("fake-") && value.region === "local-test"
      && value.input_image_fen === 0 && value.output_image_fen === 0
      && value.verified_on === null && value.source_url === null;
  }
  if (value.kind !== "official" || value.region !== "cn-beijing" || value.output_image_fen <= 0
      || !/^\d{4}-\d{2}-\d{2}$/.test(String(value.verified_on))) return false;
  try {
    const url = new URL(value.source_url);
    return url.protocol === "https:" && !url.username && !url.password && !url.port
      && ["help.aliyun.com", "docs.bailian.console.aliyun.com", "www.volcengine.com", "docs.volcengine.com"]
        .includes(url.hostname);
  } catch { return false; }
}

/**
 * 每请求分别计参考图：同一原件出现在两张图的请求中须计两次，不按整批去重抵扣。
 * @param {unknown} provider
 * @param {ReadonlyArray<{shot_id: string, references?: ReadonlyArray<unknown>}>} shots
 * @param {unknown} pricing
 * @returns {import("./type-contracts.js").ConfirmationCost}
 */
export function imageCostOf(provider, shots, pricing) {
  const unavailable = () => ({ currency: /** @type {const} */ ("CNY"), upper_fen: null,
    pricing: null, per_shot: [], message: "当前模型、地区与参数的费用上界尚未核实；不会发送。" });
  if (!pricingMatches(pricing, provider)) return unavailable();
  const rate = /** @type {import("./type-contracts.js").ImagePricing} */ (pricing);
  // 只保存公开定价白名单，调用方额外字段不进入确认、IndexedDB 或项目包。
  const frozen = {
    version: rate.version, kind: rate.kind, provider_id: rate.provider_id, model_id: rate.model_id,
    size: rate.size, n: rate.n, output_format: rate.output_format, currency: rate.currency,
    input_image_fen: rate.input_image_fen, output_image_fen: rate.output_image_fen,
    verified_on: rate.verified_on, source_url: rate.source_url, region: rate.region,
  };
  const perShot = [];
  let total = 0;
  for (const shot of shots) {
    if (!isNonEmptyString(shot.shot_id) || !Array.isArray(shot.references)) return unavailable();
    const upper = shot.references.length * rate.input_image_fen + rate.n * rate.output_image_fen;
    total += upper;
    if (!Number.isSafeInteger(upper) || !Number.isSafeInteger(total)) return unavailable();
    perShot.push({ shot_id: shot.shot_id, input_images: shot.references.length, upper_fen: upper });
  }
  return { currency: "CNY", upper_fen: total, pricing: frozen, per_shot: perShot,
    message: rate.kind === "test_double"
      ? "本地测试替身：不调用供应商、不产生模型费用；不证明真实出图品质。"
      : "本次费用上界 ¥" + (total / 100).toFixed(2) + "（供应商原价，非实际结算；核价日期 "
        + rate.verified_on + "）。" };
}

/** 展示说明不属于计价输入；单价、来源与逐图金额必须进入确认指纹。 */
export function frozenImageCost(cost) {
  if (!isPlainObject(cost)) return null;
  return { currency: cost.currency, upper_fen: cost.upper_fen, pricing: cost.pricing,
    per_shot: cost.per_shot };
}

/** 报价必须能按冻结的逐图真实输入重新算出，不接受手填合计或未说明的折扣。 */
export function imageCostMatches(cost, provider, shots) {
  if (!isPlainObject(cost)) return false;
  return canonicalJson(frozenImageCost(cost))
    === canonicalJson(frozenImageCost(imageCostOf(provider, shots, cost.pricing)));
}
