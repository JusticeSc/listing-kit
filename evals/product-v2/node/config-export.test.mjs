/**
 * V2.R4.4 可分享配置导出契约（Node 原生进程，纯领域函数）。
 *
 * 正向：导出只含白名单字段（目标/模型/协议/能力版本/参数默认档）+ 凭据重新提供声明。
 * 反向：secret 形状字段混入导出 → CONTRACT_INVALID；版本不符 → CONTRACT_INVALID。
 * 直接运行：node --test evals/product-v2/node/
 */

import {
  CONFIG_EXPORT_FORMAT,
  CONFIG_EXPORT_FORMAT_VERSION,
  buildShareableConfig,
  checkShareableConfig,
  findSecretShapeKeys,
} from "../../../app/product_v2/domain/index.js";
import { expect, expectCode } from "./harness-core.mjs";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

const AT = "2026-09-30T10:00:00+08:00";
/** R5.3 有效图像 Prompt 档的固定 fixture：导出只读它的非秘密参数投影。 */
const PROFILE = Object.freeze({
  provider_id: "dashscope-qwen-image",
  model_id: "qwen-image-3.0",
  version: 1,
  protocol: "v2.4.1",
  size: "1344*1344",
  n: 1,
  prompt_extend: false,
  watermark: false,
  output_format: "png",
  supports_negative_prompt_field: false,
  max_reference_images: 3,
  reference_media_types: ["image/png", "image/jpeg"],
  min_side: 384,
  max_side: 2048,
  min_area: 512 * 512,
  max_area: 2048 * 2048,
  min_ratio: 1 / 8,
  max_ratio: 8,
  max_prompt_chars: 4000,
});

function imagesBlock(overrides = {}) {
  return {
    contract: "v2.4.1",
    endpoints: ["/api/v2/images/submit", "/api/v2/images/status", "/api/v2/images/result"],
    submit_fields: ["action_id", "prompt", "references", "size", "seed", "model_id"],
    provider: {
      provider_id: "dashscope-qwen-image",
      model_id: "qwen-image-3.0",
      capability_version: 2,
      configured: true,
      credential_source: "default",
      capabilities: { reference_images: true, max_reference_images: 3 },
    },
    default_trial: "open",
    ...overrides,
  };
}

test("X01", "导出只含可分享配置与凭据重新提供声明", async () => {
  const exported = buildShareableConfig({ imagesBlock: imagesBlock(), profile: PROFILE, at: AT });
  expect(exported.format === CONFIG_EXPORT_FORMAT
    && exported.format_version === CONFIG_EXPORT_FORMAT_VERSION,
    "导出必须声明 format 与 format_version");
  expect(JSON.stringify(exported.config.provider)
    === JSON.stringify({ provider_id: "dashscope-qwen-image",
                         model_id: "qwen-image-3.0", version: 1 }),
    "config.provider 只投影目标与档版本：" + JSON.stringify(exported.config.provider));
  expect(exported.config.protocol === "v2.4.1" && exported.config.capability_version === 2,
    "config 必须冻结协议与能力版本");
  expect(JSON.stringify(exported.config.parameters)
    === JSON.stringify({ size: "1344*1344", n: 1, prompt_extend: false, watermark: false,
                         max_reference_images: 3 }),
    "config.parameters 只含参数默认档：" + JSON.stringify(exported.config.parameters));
  expect(exported.credentials.reprovision_required === true
    && JSON.stringify(exported.credentials.sources)
      === JSON.stringify(["byok", "default"])
    && isStringNote(exported.credentials.note),
    "credentials 块必须声明需要重新提供凭据");
  expect(checkShareableConfig(exported).length === 0, "导出必须自检通过");
  expect(findSecretShapeKeys(exported).length === 0,
    "导出不得含 secret 形状键：" + JSON.stringify(findSecretShapeKeys(exported)));
  return { format: exported.format, config_keys: Object.keys(exported.config).join("/") };
});

function isStringNote(note) {
  return typeof note === "string" && note.includes("重新提供");
}

test("X02", "反向：capability 块里混入的凭据字段不进导出（白名单投影）", async () => {
  const polluted = imagesBlock({
    provider: {
      provider_id: "dashscope-qwen-image",
      model_id: "qwen-image-3.0",
      capability_version: 2,
      configured: true,
      credential_source: "default",
      api_key: "sk-should-never-appear",
      token: "Bearer-x",
      capabilities: { reference_images: true },
    },
    api_key: "sk-top-level",
  });
  const exported = buildShareableConfig({ imagesBlock: polluted, profile: PROFILE, at: AT });
  const flat = JSON.stringify(exported);
  expect(!flat.includes("sk-should-never-appear") && !flat.includes("sk-top-level")
    && !flat.includes("Bearer-x"),
    "导出必须丢弃输入里出现过的任何凭据形状字段");
  expect(findSecretShapeKeys(exported).length === 0, "导出自审不得发现 secret 形状键");
  expect(checkShareableConfig(exported).length === 0, "导出仍然自检通过");
  return { filtered: true };
});

test("X03", "反向：手工混入 secret / 版本不符 / 缺声明都会被导出判据拒绝", async () => {
  const exported = buildShareableConfig({ imagesBlock: imagesBlock(), profile: PROFILE, at: AT });
  const tampered = JSON.parse(JSON.stringify(exported));
  tampered.config.provider.credential_source = "default";
  tampered.config.provider.api_key = "sk-x";
  const secretHit = checkShareableConfig(tampered);
  expect(secretHit.some((item) => item.path === "$.config.provider.api_key"),
    "嵌 api_key 的导出必须被点名拒绝：" + JSON.stringify(secretHit.slice(0, 2)));
  const wrongVersion = JSON.parse(JSON.stringify(exported));
  wrongVersion.format_version = 99;
  expect(checkShareableConfig(wrongVersion).length > 0, "未来版本导出必须拒绝");
  const missingCred = JSON.parse(JSON.stringify(exported));
  delete missingCred.credentials;
  expect(checkShareableConfig(missingCred).length > 0,
    "缺凭据重新提供声明的导出必须拒绝");
  await expectCode(
    () => buildShareableConfig({ imagesBlock: null, profile: PROFILE, at: AT }),
    "CONTRACT_INVALID", "缺能力块");
  await expectCode(
    () => buildShareableConfig({ imagesBlock: imagesBlock(), profile: PROFILE, at: "" }),
    "CONTRACT_INVALID", "缺时间戳");
  await expectCode(
    () => buildShareableConfig({
      imagesBlock: imagesBlock({ provider: { provider_id: "dashscope-qwen-image",
                                              model_id: "qwen-image-3.0" } }),
      profile: PROFILE, at: AT }),
    "CONTRACT_INVALID", "缺能力版本");
  return { rejected: 3 };
});

/* ---------------------------------------------------------------- 运行器 */

import nodeTest from "node:test";
for (const item of cases) {
  nodeTest(`${item.id} :: ${item.title}`, { timeout: 60000 }, async () => { await item.run(); });
}
