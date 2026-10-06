/**
 * 可分享配置导出（V2.R4.4）：区分「随包分享的配置」与「需用户重新提供的凭据」。
 *
 *  - 可分享部分只选取非 secret 的有效配置投影：目标（provider/model）、协议版本、
 *    能力版本与参数默认档。来源是 capabilities 的 images 块与前端 Provider 档。
 *  - 凭据永远是使用方重新提供：导出文件只声明 reprovision_required 与允许的来源词表，
 *    BYOK / 部署密钥的值绝不进入导出（也不在购买/分享链路回显）。
 *  - 输出判据（checkShareableConfig）自带「不含 secret 形状字段」的负向审计：
 *    导出后任何含 api_key / token / 密钥字样的键都会被判为导出失败，不做部分分享。
 * 本层是纯函数：不写文件、不读网络、不碰 DOM。
 *
 * TypeScript 迁移（计划 §9 V2.R7.5）：本文件是唯一手工维护实现；同名 `config-export.js`
 * 由 `npm run build:frontend` 从本文件生成，浏览器只消费生成的 `.js`。
 */

import { DOMAIN_ERROR_CODES, invalid } from "./errors.js";
import { isIsoTimestamp, isNonEmptyString, isPlainObject, pushProblem } from "./shared.js";
import type { CredentialSourceLabel, DomainProblem, ShareableConfig } from "./type-contracts.js";

export const CONFIG_EXPORT_FORMAT = "amz-listing-kit-config";
export const CONFIG_EXPORT_FORMAT_VERSION = 1;
export const CONFIG_EXPORT_PARAMETERS: Readonly<Record<string, string>> = Object.freeze({
  size: "size", n: "n", prompt_extend: "prompt_extend", watermark: "watermark",
  max_reference_images: "max_reference_images",
});

/** 导出文件里出现这些键（任何层级的键名）都按「秘密混入导出」处理。 */
export const CONFIG_EXPORT_FORBIDDEN_KEYS: readonly string[] = Object.freeze([
  "api_key", "apikey", "secret", "secret_key", "client_secret",
  "token", "access_token", "refresh_token", "authorization", "api_token", "password",
]);

/** 凭据来源词表（镜像 R4.3 CredentialDecision 的来源标签；test_double 只出现在离线替身）。 */
export const CONFIG_CREDENTIAL_SOURCES: readonly CredentialSourceLabel[] = Object.freeze([
  "byok", "default", "test_double",
]);

/** 正整数判定（类型收窄）：运行时校验的公共原语，不改写值。 */
function isPositiveInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

/** `buildShareableConfig` 的输入：值与迁移前 JS 调用方的松散契约一致，运行时逐字段白名单投影。 */
export type ShareableConfigBuildInput = {
  imagesBlock?: unknown;
  profile?: unknown;
  at?: unknown;
};

/**
 * 构建导出：逐字段白名单投影，capabilities/档里多余的任何字段（含疑似凭据字段）
 * 都不会出现在导出结果里。
 */
export function buildShareableConfig({ imagesBlock, profile, at }: ShareableConfigBuildInput = {}): ShareableConfig {
  if (!isPlainObject(imagesBlock)) invalid("可分享配置导出需要读到的图像能力块。");
  if (!isPlainObject(profile)) invalid("可分享配置导出需要 Provider 档。");
  if (!isIsoTimestamp(at)) invalid("导出时间必须由调用方注入 ISO 时间戳。");
  const provider: Record<string, unknown> = isPlainObject(imagesBlock.provider)
    ? imagesBlock.provider : {};
  const providerId = isNonEmptyString(provider.provider_id) ? provider.provider_id : profile.provider_id;
  const modelId = isNonEmptyString(provider.model_id) ? provider.model_id : profile.model_id;
  if (!isNonEmptyString(providerId)) invalid("可分享配置缺少 provider 标识。");
  if (!isNonEmptyString(modelId)) invalid("可分享配置缺少 model 标识。");
  if (typeof imagesBlock.contract !== "string" || imagesBlock.contract.length > 40
      || !imagesBlock.contract.startsWith("v")) {
    invalid("可分享配置缺少合法协议版本（images.contract）。");
  }
  if (!isPositiveInteger(provider.capability_version)) {
    invalid("可分享配置缺少有效能力版本（images.provider.capability_version）。");
  }
  const config = {
    provider: { provider_id: providerId, model_id: modelId, version: profile.version },
    protocol: imagesBlock.contract,
    capability_version: provider.capability_version,
    parameters: {
      size: profile.size, n: profile.n,
      prompt_extend: profile.prompt_extend, watermark: profile.watermark,
      max_reference_images: profile.max_reference_images,
    },
  };
  const exported = {
    format: CONFIG_EXPORT_FORMAT,
    format_version: CONFIG_EXPORT_FORMAT_VERSION,
    exported_at: at,
    schema_version: CONFIG_EXPORT_FORMAT_VERSION,
    config: config,
    credentials: {
      reprovision_required: true,
      sources: ["byok", "default"],
      note: "本导出不含任何密钥；换设备或重载后需要重新提供凭据（BYOK 或恢复默认档）。",
    },
  };
  const problems = checkShareableConfig(exported);
  if (problems.length > 0) invalid(problems[0].message, { problems: problems });
  // 已由 checkShareableConfig 现场收口；此处只做类型边界的显式断言。
  return exported as ShareableConfig;
}

/** 共享键扫描：任何层级的键命中 FORBIDDEN_KEYS 就是要失败（不是为止于换字段名）。 */
export function findSecretShapeKeys(value: unknown, path = "$"): string[] {
  const hits: string[] = [];
  if (Array.isArray(value)) {
    const items: unknown[] = value;
    items.forEach((item, index) => {
      hits.push(...findSecretShapeKeys(item, path + "[" + index + "]"));
    });
    return hits;
  }
  if (!isPlainObject(value)) return hits;
  for (const [key, child] of Object.entries(value)) {
    const childPath = path + "." + key;
    if (CONFIG_EXPORT_FORBIDDEN_KEYS.includes(String(key).toLowerCase())) {
      hits.push(childPath);
    }
    hits.push(...findSecretShapeKeys(child, childPath));
  }
  return hits;
}

/** 导出文件校验：形状 + 约束 + 不含 secret 形状键；返回问题列表（空 = 合法）。 */
export function checkShareableConfig(value: unknown): DomainProblem[] {
  const problems: DomainProblem[] = [];
  if (!isPlainObject(value)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "配置导出必须是对象。");
    return problems;
  }
  if (value.format !== CONFIG_EXPORT_FORMAT) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.format",
      "不是本产品的配置导出（format 不符）。");
  }
  if (value.format_version !== CONFIG_EXPORT_FORMAT_VERSION
      || value.schema_version !== CONFIG_EXPORT_FORMAT_VERSION) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.format_version",
      "配置导出版本不是当前支持的 " + CONFIG_EXPORT_FORMAT_VERSION + "。");
  }
  if (!isIsoTimestamp(value.exported_at)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.exported_at",
      "exported_at 必须是 ISO 时间戳。");
  }
  if (!isPlainObject(value.config)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.config",
      "缺少可分享配置块 config。");
  } else {
    const config = value.config;
    if (!isPlainObject(config.provider) || !isNonEmptyString(config.provider.provider_id)
        || !isNonEmptyString(config.provider.model_id)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.config.provider",
        "config.provider 必须记录 {provider_id, model_id}。");
    }
    if (typeof config.protocol !== "string" || !config.protocol.startsWith("v")) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.config.protocol",
        "config.protocol 必须是协议版本号。");
    }
    if (!isPositiveInteger(config.capability_version)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.config.capability_version",
        "config.capability_version 必须是正整数。");
    }
    if (!isPlainObject(config.parameters)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.config.parameters",
        "config.parameters 必须是对象。");
    }
  }
  const credentials = value.credentials;
  if (!isPlainObject(credentials)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.credentials",
      "credentials 必须声明 reprovision_required=true 与合法来源词表（凭据由使用方重新提供）。");
  } else {
    const sources: unknown[] = Array.isArray(credentials.sources) ? credentials.sources : [];
    if (credentials.reprovision_required !== true || !Array.isArray(credentials.sources)
        || sources.some((item) => !CONFIG_CREDENTIAL_SOURCES.some((known) => known === item))) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.credentials",
        "credentials 必须声明 reprovision_required=true 与合法来源词表（凭据由使用方重新提供）。");
    } else if (isNonEmptyString(credentials.note) === false) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.credentials.note",
        "credentials.note 必须说明凭据需要重新提供。");
    }
  }
  for (const hit of findSecretShapeKeys(value)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, hit,
      "配置导出包含 secret 形状字段；导出只允许非 secret 配置。");
  }
  return problems;
}
