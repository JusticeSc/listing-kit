/**
 * Product V2 Provider 感知 Prompt 编译器（V2.3.4，计划 §9.7）与 Prompt 人工编辑版本（V2.3.6，计划 §9.9）。
 *
 * 唯一权威：平台档、Provider 档、分段规则、语言策略、冲突判定、来源引用与请求快照都在本文件。
 * 三条不可协商的规则：
 *  1) 指令段统一中文；任何非中文原文必须来自输入并以「」逐字引用——没有无规则的中英混杂；
 *  2) 只有已确认且被该图绑定的事实可以作为图中文案，逐字使用，不翻译、不改写、不新增；
 *  3) 编译是纯函数：失败抛 CONTRACT_INVALID 并给出精确问题，不产半成品、不修改输入。
 *
 * 复用而不是重写：依赖判定用 suite-plan.js 的 evaluateShot；规格校验用 specs.js；
 * hash 复用 storage/db.js 的 WebCrypto sha256Hex，由调用方注入（与 repository 的 digest 注入同法）。
 */

import { DOMAIN_ERROR_CODES, invalid } from "./errors.js";
import { assertReworkDirective, reworkProblemLabel } from "./rework.js";
import { checkShotDraft, evaluateShot, roleDefinition } from "./suite-plan.js";
import {
  assertShotSpec,
  assertStyleSpec,
  emptyShotSpecFromShot,
  emptyStyleSpec,
} from "./specs.js";
import { invalidationsFor } from "./invalidation.js";
import { isNonEmptyString, isPlainObject, isSha256Hex, pushProblem } from "./shared.js";

export const PROMPT_SCHEMA_VERSION = 1;
export const PROMPT_LANGUAGE_POLICY_ID = "zh-instruction-v1";
export const MAX_PROMPT_CHARS = 4000;

/** 语言策略的机读声明：指令中文；图中文字语言随平台。 */
export const PROMPT_LANGUAGE_POLICY = Object.freeze({
  policy_id: PROMPT_LANGUAGE_POLICY_ID,
  instruction_language: "zh",
  on_image_text_language_source: "platform",
  verbatim_only: true,
  rules: Object.freeze([
    "指令段只写中文；非中文原文必须用「」引用。",
    "图中文字逐字等于已确认事实值，禁止翻译、改写或补全。",
    "事实值语言与平台语言不一致时给警告，交人工决定。",
  ]),
});

/** 平台档：语言、主图硬规则、允许叠加文字的角色。 */
export const PLATFORM_PROFILES = Object.freeze({
  amazon_us: Object.freeze({
    platform_id: "amazon_us",
    version: 1,
    label: "亚马逊美国站",
    on_image_text_language: "en",
    on_image_text_roles: Object.freeze([
      "infographic", "size", "comparison", "ingredient", "packaging",
    ]),
    main_image: Object.freeze({
      background_phrase: "纯白无缝背景「RGB(255,255,255)」",
      min_occupancy_percent: 85,
    }),
    base_rules: Object.freeze([
      "整套图片不得出现水印、边框、联系方式或与商品无关的叠加元素。",
      "只能使用已确认的商品事实，不添加未确认的参数、功效或承诺。",
    ]),
  }),
});

/**
 * 参考图选择的产品默认硬上限：与图像网关一次提交的参考图上限一致。
 * 具体上限由调用方按有效 Provider 档显式传入；缺省用它，不做模型查表。
 */
export const MAX_REFERENCE_SELECTION = 3;

export const IMAGE_PROFILE_VERSION_PATTERN = /^v[0-9A-Za-z._-]{1,40}$/;
export const IMAGE_SIZE_PATTERN = /^[0-9]{1,4}\*[0-9]{1,4}$/;

/**
 * 有效图像 Prompt 档（V2.R5.3）：从 capabilities.images 的 provider 能力投影出的
 * 非秘密请求 profile，平铺绑定目标身份与协议。credential_source / configured /
 * 密钥等凭据字段永不进入本档，因此也不进 basis 与请求 hash。
 *
 * 字段来源是服务端正式能力块：版本取 images.provider.capability_version，
 * 协议取 images.contract，请求参数取 images.provider.capabilities.request_profile。
 * 缺字段即拒绝（不猜参数、不兜底 model 表）。
 */
export const IMAGE_PROFILE_FIELDS = Object.freeze([
  "size", "n", "prompt_extend", "watermark", "output_format",
  "supports_negative_prompt_field", "max_reference_images", "reference_media_types",
  "min_side", "max_side", "min_area", "max_area", "min_ratio", "max_ratio",
  "max_prompt_chars",
]);

function isPositiveInteger(value) {
  return Number.isInteger(value) && value > 0;
}

function isPositiveNumber(value) {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

/** 尺寸是否落在某一档声明的边/面积/比例范围内；返回 null 表示合法。 */
export function sizeScopeProblem(profile, size) {
  if (!isNonEmptyString(size) || !IMAGE_SIZE_PATTERN.test(size)) {
    return "尺寸必须是「宽*高」格式。";
  }
  const parts = size.split("*");
  const width = Number(parts[0]);
  const height = Number(parts[1]);
  if (width < profile.min_side || width > profile.max_side
      || height < profile.min_side || height > profile.max_side) {
    return "尺寸边长超出档位 " + profile.min_side + ".." + profile.max_side + "。";
  }
  if (width * height < profile.min_area || width * height > profile.max_area) {
    return "尺寸面积超出档位 " + profile.min_area + ".." + profile.max_area + "。";
  }
  const ratio = width / height;
  if (ratio < profile.min_ratio || ratio > profile.max_ratio) {
    return "尺寸长宽比超出档位 " + profile.min_ratio + ".." + profile.max_ratio + "。";
  }
  return null;
}

/** 有效 Prompt 档的形状与自洽检查；返回问题列表（空 = 合法）。 */
export function checkImagePromptProfile(profile) {
  const problems = [];
  if (!isPlainObject(profile)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "图像 Prompt 档必须是对象。");
    return problems;
  }
  if (!isNonEmptyString(profile.provider_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.provider_id", "图像 Prompt 档缺少 provider_id。");
  }
  if (!isNonEmptyString(profile.model_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.model_id", "图像 Prompt 档缺少 model_id。");
  }
  if (!isPositiveInteger(profile.version)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.version", "图像 Prompt 档版本必须是正整数。");
  }
  if (!isNonEmptyString(profile.protocol) || !IMAGE_PROFILE_VERSION_PATTERN.test(String(profile.protocol))) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.protocol", "图像 Prompt 档协议版本不合法。");
  }
  for (const key of ["n", "max_reference_images", "min_side", "max_side",
                     "min_area", "max_area", "max_prompt_chars"]) {
    if (!isPositiveInteger(profile[key])) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$." + key,
        "图像 Prompt 档 " + key + " 必须是正整数。");
    }
  }
  for (const key of ["min_ratio", "max_ratio"]) {
    if (!isPositiveNumber(profile[key])) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$." + key,
        "图像 Prompt 档 " + key + " 必须是正数。");
    }
  }
  for (const key of ["prompt_extend", "watermark", "supports_negative_prompt_field"]) {
    if (typeof profile[key] !== "boolean") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$." + key,
        "图像 Prompt 档 " + key + " 必须是布尔值。");
    }
  }
  if (!isNonEmptyString(profile.output_format)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.output_format",
      "图像 Prompt 档缺少输出格式。");
  }
  if (!Array.isArray(profile.reference_media_types) || profile.reference_media_types.length === 0
      || profile.reference_media_types.some((item) => !isNonEmptyString(item))) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.reference_media_types",
      "图像 Prompt 档必须声明非空的参考图媒体类型。");
  }
  if (problems.length === 0) {
    if (profile.min_side > profile.max_side) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.min_side", "图像 Prompt 档边长上下限颠倒。");
    }
    if (profile.min_area > profile.max_area) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.min_area", "图像 Prompt 档面积上下限颠倒。");
    }
    if (profile.min_ratio > profile.max_ratio) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.min_ratio", "图像 Prompt 档比例上下限颠倒。");
    }
    const sizeProblem = sizeScopeProblem(profile, profile.size);
    if (sizeProblem) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.size", "默认尺寸不合法：" + sizeProblem);
    }
  }
  return problems;
}

export function assertImagePromptProfile(profile) {
  const problems = checkImagePromptProfile(profile);
  if (problems.length > 0) {
    invalid("图像 Prompt 档不合法：" + problems[0].message, { problems: problems.slice(0, 3) });
  }
  return profile;
}

/**
 * 从 capabilities 的 images 块投影有效 Prompt 档（V2.R5.3）。
 * 只读版本（provider.capability_version）、协议（images.contract）与非秘密 request_profile；
 * 不取 credential_source / configured，缺字段或字段非法直接拒绝。
 */
export function imagePromptProfile(images) {
  if (!isPlainObject(images)) invalid("图像能力块缺失：无法投影有效 Prompt 档。");
  const contract = images.contract;
  if (!isNonEmptyString(contract) || !IMAGE_PROFILE_VERSION_PATTERN.test(contract)) {
    invalid("图像能力块的协议版本（images.contract）缺失或不合法。");
  }
  const provider = isPlainObject(images.provider) ? images.provider : null;
  if (!provider) invalid("图像能力块缺少 provider：不能投影 Prompt 档。");
  if (!isNonEmptyString(provider.provider_id)) invalid("图像能力块缺少 provider_id。");
  if (!isNonEmptyString(provider.model_id)) invalid("图像能力块缺少 model_id。");
  if (!isPositiveInteger(provider.capability_version)) {
    invalid("图像能力块缺少有效版本（images.provider.capability_version）。");
  }
  const capabilities = isPlainObject(provider.capabilities) ? provider.capabilities : null;
  const raw = capabilities && isPlainObject(capabilities.request_profile)
    ? capabilities.request_profile : null;
  if (!raw) invalid("图像 provider 缺少 request_profile：不能猜测请求参数。");
  const profile = {
    provider_id: provider.provider_id,
    model_id: provider.model_id,
    version: provider.capability_version,
    protocol: contract,
    size: raw.size,
    n: raw.n,
    prompt_extend: raw.prompt_extend,
    watermark: raw.watermark,
    output_format: raw.output_format,
    supports_negative_prompt_field: raw.supports_negative_prompt_field,
    max_reference_images: raw.max_reference_images,
    reference_media_types: Array.isArray(raw.reference_media_types)
      ? [...raw.reference_media_types] : raw.reference_media_types,
    min_side: raw.min_side,
    max_side: raw.max_side,
    min_area: raw.min_area,
    max_area: raw.max_area,
    min_ratio: raw.min_ratio,
    max_ratio: raw.max_ratio,
    max_prompt_chars: raw.max_prompt_chars,
  };
  return assertImagePromptProfile(profile);
}

/* ------------------------------------------------------------ 基础工具 */

function resolveProfile(kind, table, id) {
  const value = table[id];
  if (!value) invalid(kind + "档不存在：" + String(id));
  return value;
}

function normalizePhrase(value) {
  return String(value == null ? "" : value).normalize("NFKC").toLowerCase().replace(/\s+/g, "");
}

/** 把用户值变成安全引用：控制字符转空格、引号中和、空白归一，避免引用边界被值本身破坏。 */
export function quoteLiteral(value) {
  const clean = String(value == null ? "" : value)
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/「/g, "（").replace(/」/g, "）")
    .replace(/“/g, "（").replace(/”/g, "）")
    .replace(/‘/g, "（").replace(/’/g, "）")
    .replace(/\s+/g, " ")
    .trim();
  if (!clean) invalid("引用文本不能为空。");
  return "「" + clean + "」";
}

/** 稳定序列化：对象键排序、数组保持顺序；hash 与快照比较共用这一份。 */
export function canonicalJson(value) {
  return JSON.stringify(canonicalize(value));
}

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === "object") {
    const out = {};
    for (const key of Object.keys(value).sort()) out[key] = canonicalize(value[key]);
    return out;
  }
  return value === undefined ? null : value;
}

function hasCjk(text) {
  return /[\u3400-\u9fff]/.test(String(text));
}

function hasAsciiLetters(text) {
  return /[A-Za-z]/.test(String(text));
}

/** 文本的语言标签：zh / en / mixed；用于图中文字与平台语言的对照。 */
export function languageOf(text) {
  const cjk = hasCjk(text);
  const latin = hasAsciiLetters(text);
  if (cjk && latin) return "mixed";
  if (cjk) return "zh";
  if (latin) return "en";
  return "neutral";
}

function factTexts(fact) {
  const value = fact ? fact.value : null;
  if (Array.isArray(value)) {
    return value.filter((item) => typeof item === "string" && item.trim()).map((item) => item.trim());
  }
  if (typeof value === "string") return value.trim() ? [value.trim()] : [];
  if (typeof value === "number" && Number.isFinite(value)) return [String(value)];
  return [];
}

function section(key, label, kind, text, sourceRefs) {
  return Object.freeze({
    key: key,
    label: label,
    kind: kind,
    text: text,
    source_refs: Object.freeze([...new Set(sourceRefs)]),
  });
}

function literalSection(key, label, text, items, sourceRefs) {
  return Object.freeze({
    key: key,
    label: label,
    kind: "literal",
    text: text,
    items: Object.freeze(items.map((item) => Object.freeze({ ...item }))),
    source_refs: Object.freeze([...new Set(sourceRefs)]),
  });
}

function sectionProblems(sections) {
  const problems = [];
  if (!Array.isArray(sections) || sections.length === 0) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.sections", "编译结果至少要有段落。");
    return problems;
  }
  sections.forEach((item, index) => {
    const path = "$.sections[" + index + "]";
    if (!isPlainObject(item)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "段落必须是对象。");
      return;
    }
    if (!isNonEmptyString(item.key)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".key", "段落缺少 key。");
    }
    if (item.kind !== "instruction" && item.kind !== "literal" && item.kind !== "manual_edit") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".kind", "未知段落类型。");
    }
    if (!isNonEmptyString(item.text)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".text", "段落文本不能为空。");
    }
    if (!Array.isArray(item.source_refs) || item.source_refs.length === 0
        || item.source_refs.some((ref) => !isNonEmptyString(ref))) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".source_refs",
        "每个段落必须至少有一个可追溯来源。");
    }
  });
  return problems;
}

export function promptSourceRefs(sections) {
  const refs = [];
  for (const item of Array.isArray(sections) ? sections : []) {
    for (const ref of item && Array.isArray(item.source_refs) ? item.source_refs : []) {
      if (!refs.includes(ref)) refs.push(ref);
    }
  }
  return refs;
}

/** 去掉引用片段后剩下的裸文本；语言与泄漏检查共用这一份。 */
export function stripQuotedSpans(text) {
  return String(text == null ? "" : text)
    .replace(/「[^」]*」/g, " ")
    .replace(/『[^』]*』/g, " ")
    .replace(/“[^”]*”/g, " ")
    .replace(/‘[^’]*’/g, " ");
}

/** 语言检查：指令段不得出现未引用的英文；文中文字必须是逐字引用的字符串。 */
export function checkPromptLanguage(sections) {
  const problems = [];
  for (const item of Array.isArray(sections) ? sections : []) {
    const path = "$.sections[" + String(item && item.key) + "]";
    if (!isPlainObject(item)) continue;
    if (item.kind === "instruction" || item.kind === "manual_edit") {
      const bare = stripQuotedSpans(item.text)
        .replace(/[0-9]/g, "")
        .replace(/[\s\u3000!-/:-@\[-`{-~。，、；：！？…—－（）《》【】·]/g, "");
      const runs = bare.match(/[A-Za-z]+/g) || [];
      if (runs.length > 0) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path,
          "指令段出现未引用的非中文内容：" + runs.join("、") + "；请用「」逐字引用。");
      }
    }
    if (item.kind === "literal") {
      const items = Array.isArray(item.items) ? item.items : [];
      if (items.length === 0) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "文字段没有逐字条目。");
      }
      for (const entry of items) {
        if (!isPlainObject(entry) || !/^「[^」]+」$/.test(String(entry.text || ""))) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path,
            "文中文字必须逐字放在「」里。");
          continue;
        }
        if (entry.language !== "zh" && entry.language !== "en" && entry.language !== "mixed") {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "文字条目缺少语言标签。");
        }
        if (!isNonEmptyString(entry.source_ref)) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "文字条目缺少来源。");
        }
      }
    }
  }
  return problems;
}

/* ------------------------------------------------------ 冲突、泄漏与逐字 */

/** keep / change_allowed 与公共风格 avoid 的确定性冲突判定。 */
export function checkSpecConflicts(shotSpec, styleSpec) {
  const problems = [];
  const avoid = new Set((styleSpec.avoid || []).map(normalizePhrase));
  const change = new Set((shotSpec.change_allowed || []).map(normalizePhrase));
  for (const item of shotSpec.keep || []) {
    const key = normalizePhrase(item);
    if (avoid.has(key)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shot_spec.keep",
        "保持项与避免项冲突：" + item + "。");
    }
    if (change.has(key)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shot_spec.keep",
        "保持项与允许变化项冲突：" + item + "。");
    }
  }
  return problems;
}

/**
 * 未确认事实泄漏：conflict 值在任何位置出现都阻断（冲突必须先解决）；
 * 其余未确认状态只检查引用之外的裸文本——引用内容来自用户自己的输入，不算模型偷写事实。
 */
export function checkPromptLeaks(sections, contextFacts, options = {}) {
  const problems = [];
  const joined = (Array.isArray(sections) ? sections : [])
    .map((item) => (item && item.text) || "").join("\n");
  const full = normalizePhrase(joined);
  const bare = normalizePhrase(stripQuotedSpans(joined));
  for (const fact of Array.isArray(contextFacts) ? contextFacts : []) {
    if (!isPlainObject(fact) || fact.status === "confirmed") continue;
    for (const value of factTexts(fact)) {
      const phrase = normalizePhrase(value);
      if (phrase.length < 3) continue;
      const hit = (fact.status === "conflict" || options.includeQuoted === true)
        ? full.includes(phrase) : bare.includes(phrase);
      if (hit) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.sections",
          "未确认的「" + String(fact.slot_id) + "」值出现在提示词：" + value + "。");
      }
    }
  }
  return problems;
}

/** 图中文字必须逐字等于某条已确认事实值，并带一致的语言标签。 */
export function checkLiteralVerbatim(sections, brief) {
  const problems = [];
  const confirmed = new Map(
    ((brief && brief.confirmed_facts) || [])
      .filter((item) => isPlainObject(item))
      .map((item) => [item.slot_id, item]));
  for (const item of Array.isArray(sections) ? sections : []) {
    if (!isPlainObject(item) || item.kind !== "literal") continue;
    for (const entry of Array.isArray(item.items) ? item.items : []) {
      const slotId = String(entry.source_ref || "").replace(/^product_brief\.fact:/, "");
      const fact = confirmed.get(slotId);
      const inner = String(entry.text || "").replace(/^「/, "").replace(/」$/, "");
      if (!fact || !factTexts(fact).includes(inner)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID,
          "$.sections[" + item.key + "]", "图中文字不是已确认事实的逐字值：" + entry.text);
        continue;
      }
      const language = languageOf(inner);
      if (language !== "neutral" && entry.language !== language) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID,
          "$.sections[" + item.key + "]", "文字条目的语言标签与内容不一致：" + entry.text);
      }
    }
  }
  return problems;
}

/* ------------------------------------------------------------ 编译器 */

export function promptBasisOf(input, platform, provider) {
  const versions = isPlainObject(input.versions) ? input.versions : {};
  const positive = (value) => (Number.isInteger(value) && value > 0 ? value : null);
  return {
    brief: (input.brief.basis || []).map((item) => ({
      slot_id: item.slot_id, version: item.version,
    })),
    suite_version: positive(versions.suite_version),
    style_version: positive(versions.style_version),
    shot_spec_version: positive(versions.shot_spec_version),
    platform: { platform_id: platform.platform_id, version: platform.version },
    // 冻结完整有效档（含目标、协议、能力边界与请求参数）；凭据字段从不进入本档。
    provider: { ...provider },
    ...(isPlainObject(input.rework) ? {
      rework: {
        directive_id: input.rework.directive_id,
        candidate_id: input.rework.candidate_id,
        candidate_sha256: input.rework.candidate_sha256,
        problems: [...(Array.isArray(input.rework.problems) ? input.rework.problems : [])],
      },
    } : {}),
  };
}

export function compilePrompt(input) {
  if (!isPlainObject(input)) invalid("Prompt 编译输入必须是对象。");
  const brief = input.brief;
  if (!isPlainObject(brief) || !Array.isArray(brief.confirmed_facts) || !Array.isArray(brief.basis)) {
    invalid("Prompt 编译需要合法的 ProductBrief（含 basis 与 confirmed_facts）。");
  }
  const shot = input.shot;
  if (!isPlainObject(shot)) invalid("Prompt 编译需要一张 Shot。");
  const problems = [];
  problems.push(...checkShotDraft(shot));
  const platform = resolveProfile("平台", PLATFORM_PROFILES, input.platformId || "amazon_us");
  const profileProblems = checkImagePromptProfile(input.providerProfile);
  if (profileProblems.length > 0) {
    invalid("Prompt 编译缺少有效 Provider 档：" + profileProblems[0].message,
      { problems: profileProblems.slice(0, 3) });
  }
  const provider = input.providerProfile;
  const styleSpec = input.styleSpec ? assertStyleSpec(input.styleSpec) : emptyStyleSpec();
  const shotSpec = input.shotSpec ? assertShotSpec(input.shotSpec) : emptyShotSpecFromShot(shot);
  problems.push(...checkSpecConflicts(shotSpec, styleSpec));
  // 返工指令（V2.5.4）：只允许作用于本图，且必须已经通过领域校验。
  const rework = isPlainObject(input.rework) ? assertReworkDirective(input.rework) : null;
  if (rework && rework.shot_id !== shot.shot_id) {
    invalid("返工指令属于另一张图，不能用于编译这张图的 Prompt。");
  }
  const context = isPlainObject(input.context) ? input.context : {};
  const dependency = evaluateShot(shot, context);
  for (const item of dependency.blocking) {
    problems.push({
      code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: "$.shot.dependencies",
      message: "这张图的依据还没有满足：" + (item.reason || "未知原因") + "。",
    });
  }
  const confirmed = new Map(
    brief.confirmed_facts.filter((item) => isPlainObject(item)).map((item) => [item.slot_id, item]));
  const boundIds = Array.isArray(shot.fact_slot_ids) ? shot.fact_slot_ids : [];
  for (const slotId of boundIds) {
    if (!confirmed.has(slotId)) {
      problems.push({
        code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: "$.shot.fact_slot_ids",
        message: "绑定的商品事实「" + slotId + "」还没有确认值，不能进入提示词。",
      });
    }
  }
  if (problems.length > 0) {
    invalid("Prompt 编译未通过：" + problems[0].message
      + (problems.length > 1 ? "（共 " + problems.length + " 项）" : ""),
      { problems: problems.slice(0, 6) });
  }

  const role = roleDefinition(shot.role_id) || {};
  const roleLabel = isNonEmptyString(shot.label) ? shot.label : (role.label || shot.role_id);
  const shotRef = "suite_plan.shot:" + shot.shot_id;
  const platformRef = "platform:" + platform.platform_id + "@" + platform.version;
  const providerRef = "provider:" + provider.model_id + "@" + provider.version;
  const warnings = [];
  const sections = [];
  const boundFacts = boundIds.map((slotId) => confirmed.get(slotId)).filter(Boolean);
  const allowsText = platform.on_image_text_roles.includes(shot.role_id);
  const isMain = shot.role_id === "main";

  let fidelity = "以提供的商品参考图为唯一外观依据：保持商品的轮廓、比例、颜色、材质、标识与现有部件不变；不要添加、删除、复制、换色或重新设计商品特征。";
  if (allowsText && boundFacts.length > 0) {
    fidelity += "图中如需出现文字，只能逐字使用后面列出的已确认文案。";
  } else if (!allowsText) {
    fidelity += "不要在图片上叠加文字、参数、徽标或水印。";
  }
  sections.push(section("product_fidelity", "商品一致性", "instruction", fidelity,
    ["intake.references", shotRef, shotRef + ".role", platformRef]));

  const styleLines = [];
  const styleRefs = [];
  const background = isNonEmptyString(styleSpec.background) ? styleSpec.background : null;
  if (isMain) {
    styleLines.push("主图背景" + platform.main_image.background_phrase);
    styleRefs.push(platformRef);
    if (background && !/(纯白|白色|white)/i.test(background)) {
      styleRefs.push("style_spec.background");
      warnings.push({
        code: "STYLE_OVERRIDDEN_BY_PLATFORM",
        message: "公共风格背景「" + background + "」被主图平台规则覆盖为纯白背景。",
        source_refs: ["style_spec.background", platformRef],
      });
    } else if (background) {
      styleRefs.push("style_spec.background");
    }
  } else if (background) {
    styleLines.push("背景" + quoteLiteral(background));
    styleRefs.push("style_spec.background");
  }
  for (const [key, label] of [["lighting", "光线"], ["color_tone", "色调"], ["composition", "构图"]]) {
    if (isNonEmptyString(styleSpec[key])) {
      styleLines.push(label + quoteLiteral(styleSpec[key]));
      styleRefs.push("style_spec." + key);
    }
  }
  if (styleLines.length > 0) {
    sections.push(section("style_shared", "公共风格", "instruction",
      "公共风格（整套一致）：" + styleLines.join("；") + "。", styleRefs));
  }

  const taskLines = ["本图任务" + quoteLiteral(roleLabel)
    + "，目的" + quoteLiteral(shotSpec.purpose || shot.intent || role.purpose || roleLabel) + "。"];
  const taskRefs = [shotRef, "shot_spec.purpose"];
  if (shotSpec.keep.length > 0) {
    taskLines.push("必须保持：" + shotSpec.keep.map(quoteLiteral).join("、") + "。");
    taskRefs.push("shot_spec.keep");
  }
  if (shotSpec.change_allowed.length > 0) {
    taskLines.push("允许变化：" + shotSpec.change_allowed.map(quoteLiteral).join("、") + "。");
    taskRefs.push("shot_spec.change_allowed");
  }
  if (isNonEmptyString(shotSpec.notes)) {
    taskLines.push("补充说明：" + quoteLiteral(shotSpec.notes) + "。");
    taskRefs.push("shot_spec.notes");
  }
  sections.push(section("shot_task", "本图任务", "instruction", taskLines.join(""), taskRefs));

  if (rework) {
    // 用户方向按「逐字引用」处理：括号内允许任意语言，语言策略仍然成立。
    const problemText = rework.problems.map(reworkProblemLabel).join("、");
    const reworkLines = ["本次返工要求（只改这张图，其它段落保持不变）："];
    if (problemText) reworkLines.push("这次的问题属于" + quoteLiteral(problemText) + "；");
    if (rework.direction) reworkLines.push("改进方向" + quoteLiteral(rework.direction) + "；");
    reworkLines.push("不要重复出现上一条候选里已经被指出的同类问题。");
    sections.push(section("rework_directive", "本次返工要求", "instruction", reworkLines.join(""),
      ["rework:" + rework.directive_id, "candidate:" + rework.candidate_id, shotRef]));
  }

  const textItems = [];
  const textRefs = [];
  // V2.6.17：只有「允许图中文字」的角色才会排出文字段落 —— 无文字角色（场景图/细节图等）
  // 报「图中将逐字保留原文」是误报。同一槽位的多条非目标语言文案仍合并为一条风险
  //（给出条数），消息里补上可操作建议（改英文后重新确认）。
  const languageRisks = new Map();
  if (allowsText) {
    for (const fact of boundFacts) {
      for (const value of factTexts(fact)) {
        const language = languageOf(value);
        const sourceRef = "product_brief.fact:" + fact.slot_id;
        textItems.push({ text: quoteLiteral(value), language: language, source_ref: sourceRef });
        textRefs.push(sourceRef);
        if (language !== platform.on_image_text_language) {
          languageRisks.set(fact.slot_id, (languageRisks.get(fact.slot_id) || 0) + 1);
        }
      }
    }
    for (const [slotId, count] of languageRisks) {
      warnings.push({
        code: "ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE",
        message: count > 1
          ? "商品事实「" + slotId + "」有 " + count + " 条文案不是 " + platform.on_image_text_language
            + "，图中将逐字保留原文，请人工确认是否使用；建议把这条事实值改成英文后重新确认。"
          : "商品事实「" + slotId + "」的文案不是 " + platform.on_image_text_language
            + "，图中将逐字保留原文，请人工确认是否使用；建议把这条事实值改成英文后重新确认。",
        source_refs: ["product_brief.fact:" + slotId, platformRef],
      });
    }
  }
  if (allowsText && textItems.length > 0) {
    const header = "图中文字（只允许逐字使用以下已确认文案，不翻译、不改写、不新增；文字语言应为"
      + quoteLiteral(platform.on_image_text_language) + "）：\n";
    sections.push(literalSection("on_image_text", "图中文字",
      header + textItems.map((item) => "- " + item.text).join("\n"), textItems, textRefs));
  } else if (isMain && boundFacts.length > 0) {
    warnings.push({
      code: "MAIN_IMAGE_FACTS_IGNORED",
      message: "主图不得叠加文字，绑定的 " + boundFacts.length + " 条事实不会出现在画面上。",
      source_refs: boundFacts.map((fact) => "product_brief.fact:" + fact.slot_id).concat([platformRef]),
    });
  }

  const platformLines = ["平台规则" + quoteLiteral(platform.label) + "："];
  if (isMain) {
    platformLines.push("主图必须使用" + platform.main_image.background_phrase
      + "，商品主体至少占画面 " + platform.main_image.min_occupancy_percent
      + "%，不得出现文字、水印或边框。");
  }
  platformLines.push(...platform.base_rules);
  sections.push(section("platform_rules", "平台规则", "instruction",
    platformLines.join(""), [platformRef]));

  sections.push(section("provider_contract", "输出规格", "instruction",
    "输出规格：一张" + quoteLiteral(provider.size) + "的" + quoteLiteral(provider.output_format)
      + "格式高清商品图，不添加水印。",
    [providerRef]));

  const avoidList = [
    ...styleSpec.avoid,
    "水印", "文字错乱或文字变形",
    "商品变形、多出部件或与参考图不符的颜色和标识",
  ];
  if (!allowsText) avoidList.push("任何叠加文字、参数徽标或边框");
  sections.push(section("negative_constraints", "必须避免", "instruction",
    "必须避免：" + avoidList.map(quoteLiteral).join("、") + "。",
    ["style_spec.avoid", platformRef, providerRef, "shot_spec.keep"]));

  const text = sections.map((item) => item.text).join("\n\n");
  const compiled = {
    schema_version: PROMPT_SCHEMA_VERSION,
    shot_id: shot.shot_id,
    role_id: shot.role_id,
    label: roleLabel,
    language: {
      policy_id: PROMPT_LANGUAGE_POLICY_ID,
      instruction: "zh",
      on_image_text: platform.on_image_text_language,
    },
    platform: { platform_id: platform.platform_id, version: platform.version, label: platform.label },
    provider: { ...provider },
    sections: sections,
    text: text,
    source_refs: promptSourceRefs(sections),
    warnings: warnings,
    basis: promptBasisOf(input, platform, provider),
    rework: rework ? Object.freeze({
      contract_version: rework.contract_version,
      directive_id: rework.directive_id,
      candidate_id: rework.candidate_id,
      candidate_sha256: rework.candidate_sha256,
      problems: rework.problems,
      direction: rework.direction,
    }) : null,
  };
  const selfCheck = [
    ...checkCompiledPrompt(compiled),
    ...checkLiteralVerbatim(sections, brief),
    ...checkPromptLeaks(sections, context.facts),
  ];
  if (text.length > provider.max_prompt_chars) {
    selfCheck.push({
      code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: "$.text",
      message: "提示词长度 " + text.length + " 超过 Provider 上限 " + provider.max_prompt_chars + "。",
    });
  }
  if (selfCheck.length > 0) {
    invalid("Prompt 编译自检未通过：" + selfCheck[0].message, { problems: selfCheck.slice(0, 6) });
  }
  return compiled;
}

/* --------------------------------------------------- 自检、快照与版本记录 */

/**
 * 参考图选择：先满足该 Shot 声明的 asset_role 依赖，再用主图补齐；
 * 数量不超过调用方给的有效上限（缺省产品硬上限）；同一 sha256 只出现一次。
 * 只做 role/hash 选择，不做模型查表；选不出参考图时由请求快照统一报错。
 */
export function selectReferences(shot, references, options = {}) {
  const limit = options.maxReferences === undefined ? MAX_REFERENCE_SELECTION : options.maxReferences;
  if (!isPositiveInteger(limit)) invalid("参考图上限必须是正整数。");
  const list = (Array.isArray(references) ? references : [])
    .map((item) => ({
      role: item && item.role,
      sha256: item && (item.sha256 || item.asset_sha256),
    }))
    .filter((item) => isNonEmptyString(item.role) && /^[0-9a-f]{64}$/.test(String(item.sha256 || "")));
  const requiredRoles = (isPlainObject(shot) && Array.isArray(shot.dependencies) ? shot.dependencies : [])
    .filter((item) => isPlainObject(item) && item.kind === "asset_role" && isNonEmptyString(item.role))
    .map((item) => item.role);
  const order = [...new Set([...requiredRoles, "primary", "detail", "packaging", "scene", "competitor", "other"])];
  const picked = [];
  for (const role of order) {
    for (const item of list) {
      if (item.role !== role) continue;
      if (picked.some((entry) => entry.sha256 === item.sha256)) continue;
      picked.push({ role: item.role, sha256: item.sha256 });
      if (picked.length >= limit) return picked;
    }
  }
  return picked;
}

export function checkCompiledPrompt(compiled) {
  const problems = [];
  if (!isPlainObject(compiled)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "编译结果必须是对象。");
    return problems;
  }
  if (compiled.rework !== undefined && compiled.rework !== null) {
    const rework = compiled.rework;
    if (!isPlainObject(rework) || !isNonEmptyString(rework.contract_version)
        || !isNonEmptyString(rework.directive_id) || !isNonEmptyString(rework.candidate_id)
        || !isSha256Hex(rework.candidate_sha256)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.rework",
        "返工块必须绑定指令与候选身份。");
    } else if (!(Array.isArray(compiled.sections) ? compiled.sections : [])
      .some((item) => item && item.key === "rework_directive")) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.rework",
        "带返工块的编译结果必须有「本次返工要求」段落。");
    } else {
      // 返工块与来源引用必须指向同一条指令与同一条候选，防止只改一处就冒充另一条返工。
      const refs = Array.isArray(compiled.source_refs) ? compiled.source_refs : [];
      if (refs.indexOf("rework:" + rework.directive_id) === -1
          || refs.indexOf("candidate:" + rework.candidate_id) === -1) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.rework",
          "返工块必须与来源引用一致（rework:<id> 与 candidate:<id>）。");
      }
    }
  }
  problems.push(...sectionProblems(compiled.sections));
  if (compiled.origin !== "manual_edit") {
    problems.push(...checkPromptLanguage(compiled.sections));
  }
  const expectedText = (Array.isArray(compiled.sections) ? compiled.sections : [])
    .map((item) => item.text).join("\n\n");
  if (compiled.text !== expectedText) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.text",
      "text 必须等于 sections 的确定性拼接。");
  }
  const expectedRefs = promptSourceRefs(compiled.sections);
  if (canonicalJson(compiled.source_refs || []) !== canonicalJson(expectedRefs)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.source_refs",
      "source_refs 必须等于各段落来源的并集。");
  }
  return problems;
}

export function assertCompiledPrompt(compiled) {
  const problems = checkCompiledPrompt(compiled);
  if (problems.length > 0) {
    invalid("编译结果不合法：" + problems[0].message, { problems: problems.slice(0, 3) });
  }
  return compiled;
}

/**
 * 快照与冻结档一致性检查：build/checkPromptRecord 与 requestSnapshotOf 共用。
 * 只比较请求相关字段与目标身份，不比较任何凭据字段；返回问题列表。
 */
function checkSnapshotAgainstProfile(profile, snapshot) {
  const problems = [];
  if (!isPlainObject(snapshot)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.request_snapshot", "请求快照必须是对象。");
    return problems;
  }
  if (!isPlainObject(profile)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.compiled.provider",
      "编译结果缺少冻结的 Provider 档。");
    return problems;
  }
  const expect = (key, expected) => {
    if (snapshot[key] !== expected) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.request_snapshot." + key,
        "请求快照的 " + key + " 必须等于冻结档的 " + String(expected) + "。");
    }
  };
  expect("model", profile.model_id);
  expect("size", profile.size);
  expect("n", profile.n);
  expect("prompt_extend", profile.prompt_extend);
  expect("watermark", profile.watermark);
  expect("output_format", profile.output_format);
  const target = isPlainObject(snapshot.target) ? snapshot.target : null;
  const expectedTarget = isPositiveInteger(profile.version)
    ? { provider_id: profile.provider_id, model_id: profile.model_id,
        protocol: profile.protocol, capability_version: profile.version } : null;
  if (!target || !expectedTarget
      || canonicalJson(target) !== canonicalJson(expectedTarget)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.request_snapshot.target",
      "请求快照的 target 必须等于冻结档的目标身份（协议/目标/模型/能力版本）。");
  }
  const refs = Array.isArray(snapshot.references) ? snapshot.references : null;
  if (!refs) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.request_snapshot.references",
      "请求快照缺少参考图数组。");
  } else {
    // 数量上下限由 requestSnapshotOf 与确认单（REFERENCE_COUNT_INVALID）负责；
    // 这里只核对每条参考图的身份形状，避免同一件事被两处不同码重复判定。
    refs.forEach((item, index) => {
      if (!isPlainObject(item) || !isNonEmptyString(item.role) || !isSha256Hex(item.sha256)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID,
          "$.request_snapshot.references[" + index + "]", "参考图必须带 role 与 sha256。");
      }
    });
  }
  return problems;
}

/** 请求快照：只包含真实会发送的参数与参考图身份，不含图片字节；prompt 必须逐字等于编译文本。 */
export function requestSnapshotOf(compiled, options = {}) {
  assertCompiledPrompt(compiled);
  const profile = assertImagePromptProfile(compiled.provider);
  const refs = Array.isArray(options.references) ? options.references : [];
  if (refs.length < 1 || refs.length > profile.max_reference_images) {
    invalid("参考图数量必须在 1.." + profile.max_reference_images + " 之间，当前 " + refs.length + " 张。");
  }
  const references = refs.map((item) => {
    if (!isPlainObject(item) || !isNonEmptyString(item.role)
        || !/^[0-9a-f]{64}$/.test(String(item.sha256 || ""))) {
      invalid("参考图必须带 role 与 sha256。");
    }
    return { role: item.role, sha256: item.sha256 };
  });
  const sizeProblem = sizeScopeProblem(profile, profile.size);
  if (sizeProblem) invalid("冻结档位的默认尺寸不合法：" + sizeProblem);
  return {
    model: profile.model_id,
    size: profile.size,
    n: profile.n,
    prompt_extend: profile.prompt_extend,
    watermark: profile.watermark,
    output_format: profile.output_format,
    references: references,
    prompt: compiled.text,
    target: {
      provider_id: profile.provider_id,
      model_id: profile.model_id,
      protocol: profile.protocol,
      capability_version: profile.version,
    },
  };
}

/** hash 复用注入的 sha256Hex（WebCrypto）；本层不写第二种散列。 */
export async function promptHash(snapshot, options = {}) {
  const digest = options.digest;
  if (typeof digest !== "function") {
    invalid("Prompt hash 需要注入 digest（复用 sha256Hex），不在本层另写散列。");
  }
  const bytes = new TextEncoder().encode(canonicalJson(snapshot));
  const hex = await digest(bytes);
  if (typeof hex !== "string" || !/^[0-9a-f]{64}$/.test(hex)) {
    invalid("digest 必须返回 64 位十六进制 sha256。");
  }
  return hex;
}

export function buildPromptRecord({ compiled, snapshot, hash } = {}) {
  assertCompiledPrompt(compiled);
  const snapshotProblems = checkSnapshotAgainstProfile(compiled.provider, snapshot);
  if (snapshotProblems.length > 0) {
    invalid(snapshotProblems[0].message, { problems: snapshotProblems.slice(0, 3) });
  }
  if (!isPlainObject(snapshot) || snapshot.prompt !== compiled.text) {
    invalid("请求快照的 prompt 必须与编译文本逐字一致。");
  }
  if (typeof hash !== "string" || !/^[0-9a-f]{64}$/.test(hash)) {
    invalid("Prompt 记录缺少有效 hash。");
  }
  return {
    schema_version: PROMPT_SCHEMA_VERSION,
    shot_id: compiled.shot_id,
    role_id: compiled.role_id,
    label: compiled.label,
    compiled: {
      sections: compiled.sections,
      text: compiled.text,
      source_refs: compiled.source_refs,
      warnings: compiled.warnings,
      language: compiled.language,
      platform: compiled.platform,
      provider: compiled.provider,
      ...(compiled.rework ? { rework: compiled.rework } : {}),
    },
    request_snapshot: snapshot,
    hash: hash,
    basis: compiled.basis,
  };
}

/** 版本记录形状（存储层写入前使用）。 */
export function checkPromptRecord(record) {
  const problems = [];
  if (!isPlainObject(record)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "Prompt 记录必须是对象。");
    return problems;
  }
  if (record.schema_version !== PROMPT_SCHEMA_VERSION) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.schema_version",
      "Prompt 记录版本不认识：" + String(record.schema_version));
  }
  if (!isNonEmptyString(record.shot_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shot_id", "记录缺少 shot_id。");
  }
  problems.push(...checkCompiledPrompt(record.compiled));
  problems.push(...checkImagePromptProfile(record.compiled && record.compiled.provider));
  problems.push(...checkSnapshotAgainstProfile(
    record.compiled && record.compiled.provider, record.request_snapshot));
  if (!isPlainObject(record.request_snapshot)
      || record.request_snapshot.prompt !== (record.compiled && record.compiled.text)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.request_snapshot",
      "快照 prompt 必须与编译文本逐字一致。");
  }
  if (typeof record.hash !== "string" || !/^[0-9a-f]{64}$/.test(record.hash)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.hash", "记录缺少有效 hash。");
  }
  if (!isPlainObject(record.basis)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.basis", "记录缺少编译依据。");
  }
  if (record.origin === "manual_edit") {
    if (!isPlainObject(record.edited_from) || !isSha256Hex(record.edited_from.hash)
        || !Number.isInteger(record.edited_from.version) || record.edited_from.version < 1) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.edited_from",
        "人工编辑版本必须记录被编辑的版本号与 hash。");
    }
    if (!isNonEmptyString(record.edit_reason)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.edit_reason",
        "人工编辑版本必须记录编辑原因。");
    }
    if (typeof record.edited_at !== "string" || Number.isNaN(Date.parse(record.edited_at))) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.edited_at",
        "人工编辑版本必须记录 ISO 时间戳。");
    }
    if ((record.compiled || {}).origin !== "manual_edit") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.compiled.origin",
        "人工编辑版本的 compiled.origin 必须是 manual_edit。");
    }
    if (!isPlainObject(record.invalidation) || record.invalidation.scope !== "shot"
        || record.invalidation.target_shot_id !== record.shot_id) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.invalidation",
        "人工编辑必须记录只影响目标 Shot 的失效投影。");
    }
  }
  return problems;
}

/* ------------------------------------------------------ 人工编辑（V2.3.6） */

export const MANUAL_EDIT_WARNING_CODES = Object.freeze({
  LANGUAGE_RULE: "MANUAL_EDIT_LANGUAGE_RULE",
});

/** 人工编辑的机读阻断原因：只有语言策略降级为提示，其余仍然阻断。 */
export const MANUAL_EDIT_REASON_CODES = Object.freeze({
  UNKNOWN_QUOTE: "MANUAL_EDIT_UNKNOWN_QUOTE",
  PLATFORM_TEXT_RULE: "MANUAL_EDIT_PLATFORM_TEXT_RULE",
});

export const MANUAL_EDIT_REASON_MAX = 200;

const CONTROL_CHAR_PATTERN = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/;
const QUOTE_PATTERN = /「[^」]*」/g;

function trimQuotes(value) {
  return String(value == null ? "" : value).replace(/^「/, "").replace(/」$/, "");
}

/** 人工编辑的硬阻断：空文本、控制字符、超长、与当前版本逐字相同。 */
export function checkEditText(text, options = {}) {
  const problems = [];
  if (typeof text !== "string" || text.trim().length === 0) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.text", "编辑后的提示词不能为空。");
    return problems;
  }
  if (CONTROL_CHAR_PATTERN.test(text)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.text", "提示词不能包含控制字符。");
  }
  const maxChars = Number.isInteger(options.maxChars) ? options.maxChars : MAX_PROMPT_CHARS;
  if (text.length > maxChars) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.text",
      "提示词长度 " + text.length + " 超过 Provider 上限 " + maxChars + "。");
  }
  if (typeof options.baseText === "string" && text === options.baseText) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.text",
      "编辑后的文本与当前版本逐字相同，不需要新版本。");
  }
  return problems;
}

/**
 * 人工编辑规则：只有语言策略降级为提示；未授权引用与平台文字白名单仍然阻断。
 * 被编辑文本里已经存在的引用视为已授权（编译器产物或用户输入的产物），新增引用必须来自已确认事实。
 */
export function checkManualEditRules({ text, base, brief } = {}) {
  const problems = [];
  const warnings = [];
  const baseText = (base && base.compiled && base.compiled.text) || "";
  const allowedQuotes = new Set(
    (String(baseText).match(QUOTE_PATTERN) || []).map((quote) => normalizePhrase(trimQuotes(quote))));
  const platform = base && base.compiled && base.compiled.platform
    ? PLATFORM_PROFILES[base.compiled.platform.platform_id] || null : null;
  const backgroundPhrase = platform ? normalizePhrase(platform.main_image.background_phrase) : "";
  const roleId = (base && base.role_id) || null;
  const textAllowed = platform ? platform.on_image_text_roles.includes(roleId) : true;
  const confirmed = new Set();
  for (const fact of (brief && Array.isArray(brief.confirmed_facts) ? brief.confirmed_facts : [])) {
    for (const value of factTexts(fact)) confirmed.add(normalizePhrase(value));
  }
  for (const quote of String(text == null ? "" : text).match(QUOTE_PATTERN) || []) {
    const phrase = normalizePhrase(trimQuotes(quote));
    if (phrase === backgroundPhrase || allowedQuotes.has(phrase)) continue;
    if (confirmed.has(phrase)) {
      if (!textAllowed) {
        problems.push({
          code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: "$.text",
          reason_code: MANUAL_EDIT_REASON_CODES.PLATFORM_TEXT_RULE,
          message: "这张图（" + String(roleId) + "）按平台规则不能新增叠加文案：" + quote + "。",
        });
      }
      continue;
    }
    problems.push({
      code: DOMAIN_ERROR_CODES.CONTRACT_INVALID, path: "$.text",
      reason_code: MANUAL_EDIT_REASON_CODES.UNKNOWN_QUOTE,
      message: "新引用不是任何已确认事实值：" + quote + "；先到「商品理解」确认它，或改成不引用的表述。",
    });
  }
  for (const problem of checkPromptLanguage([{
    key: "manual_edit", label: "人工编辑全文", kind: "manual_edit", text: text,
    source_refs: ["manual_edit"],
  }])) {
    warnings.push({ code: MANUAL_EDIT_WARNING_CODES.LANGUAGE_RULE, message: problem.message });
  }
  return { problems: problems, warnings: warnings };
}

/** 人工编辑版本：全文直接生效，hash 覆盖真实请求快照，basis 逐字继承被编辑版本。 */
export async function buildEditedPromptRecord({ base, baseVersion, text, reason, editedAt, context, digest } = {}) {
  const baseProblems = checkPromptRecord(base);
  if (baseProblems.length > 0) {
    invalid("被编辑的 Prompt 记录不合法：" + baseProblems[0].message, { problems: baseProblems.slice(0, 3) });
  }
  if (!Number.isInteger(baseVersion) || baseVersion < 1) {
    invalid("人工编辑需要被编辑版本的版本号（来自文档仓库）。");
  }
  const frozenProvider = base.compiled.provider;
  const maxChars = isPositiveInteger(frozenProvider && frozenProvider.max_prompt_chars)
    ? frozenProvider.max_prompt_chars : MAX_PROMPT_CHARS;
  const textProblems = checkEditText(text, { maxChars: maxChars, baseText: base.compiled.text });
  if (textProblems.length > 0) {
    invalid("人工编辑未通过：" + textProblems[0].message, { problems: textProblems });
  }
  if (!isNonEmptyString(reason) || reason.trim().length > MANUAL_EDIT_REASON_MAX) {
    invalid("人工编辑必须填写不超过 " + MANUAL_EDIT_REASON_MAX + " 字的编辑原因。");
  }
  if (typeof editedAt !== "string" || Number.isNaN(Date.parse(editedAt))) {
    invalid("人工编辑需要 ISO 时间戳。");
  }
  const sourceRefs = [...new Set([...(base.compiled.source_refs || []), "prompt_edit:" + base.hash])];
  const sections = [Object.freeze({
    key: "manual_edit",
    label: "人工编辑全文",
    kind: "manual_edit",
    text: text,
    source_refs: Object.freeze([...sourceRefs]),
  })];
  const leaks = checkPromptLeaks(sections, (context || {}).facts, { includeQuoted: true });
  if (leaks.length > 0) {
    invalid("人工编辑未通过：" + leaks[0].message, { problems: leaks.slice(0, 3) });
  }
  const rules = checkManualEditRules({ text: text, base: base, brief: (context || {}).brief });
  if (rules.problems.length > 0) {
    invalid("人工编辑未通过：" + rules.problems[0].message, {
      problems: rules.problems.slice(0, 3),
      reason_code: rules.problems[0].reason_code || null,
    });
  }
  const compiled = {
    schema_version: PROMPT_SCHEMA_VERSION,
    shot_id: base.shot_id,
    role_id: base.role_id,
    label: base.label,
    origin: "manual_edit",
    language: { ...(base.compiled.language || {}) },
    platform: { ...(base.compiled.platform || {}) },
    provider: { ...(base.compiled.provider || {}) },
    sections: sections,
    text: text,
    source_refs: sourceRefs,
    warnings: rules.warnings,
    basis: base.basis,
  };
  const problems = checkCompiledPrompt(compiled);
  if (problems.length > 0) {
    invalid("人工编辑记录自检未通过：" + problems[0].message, { problems: problems.slice(0, 3) });
  }
  const snapshot = requestSnapshotOf(compiled, {
    references: (base.request_snapshot && base.request_snapshot.references) || [],
  });
  const hash = await promptHash(snapshot, { digest: digest });
  const record = {
    schema_version: PROMPT_SCHEMA_VERSION,
    shot_id: base.shot_id,
    role_id: base.role_id,
    label: base.label,
    origin: "manual_edit",
    edited_from: { version: baseVersion, hash: base.hash },
    edit_reason: reason.trim(),
    edited_at: editedAt,
    invalidation: invalidationsFor("prompt_edited", { shotId: base.shot_id }),
    compiled: compiled,
    request_snapshot: snapshot,
    hash: hash,
    basis: compiled.basis,
  };
  const recordProblems = checkPromptRecord(record);
  if (recordProblems.length > 0) {
    invalid("人工编辑记录不合法：" + recordProblems[0].message, { problems: recordProblems.slice(0, 3) });
  }
  return record;
}

/**
 * 过期机检：槽位 basis、套图/风格/单图版本、平台档与完整 Provider 档任一变化即过期。
 *
 * Provider 比较不再只看 numeric version：目标（provider_id/model_id）、协议与请求相关
 * 能力边界/参数任一不同都判过期；当前档缺字段也判过期。凭据字段（credential_source /
 * configured / 密钥引用）不在比较集合内，因此纯凭据轮换不使 Prompt 过期。
 */
export function promptStaleness(record, current = {}) {
  const reasons = [];
  const basis = isPlainObject(record) && isPlainObject(record.basis) ? record.basis : null;
  if (!basis) {
    return { stale: true, reasons: [{ field: "basis", stored: null, current: null, reason: "记录缺少编译依据。" }] };
  }
  const storedBasis = new Map((basis.brief || []).map((item) => [item.slot_id, item.version]));
  const currentBasis = new Map((current.briefBasis || []).map((item) => [item.slot_id, item.version]));
  for (const [slotId, version] of storedBasis) {
    if (!currentBasis.has(slotId)) {
      reasons.push({ field: "brief." + slotId, stored: version, current: null, reason: "槽位已不存在" });
    } else if (currentBasis.get(slotId) !== version) {
      reasons.push({ field: "brief." + slotId, stored: version, current: currentBasis.get(slotId), reason: "槽位版本已前进" });
    }
  }
  for (const [slotId, version] of currentBasis) {
    if (!storedBasis.has(slotId)) {
      reasons.push({ field: "brief." + slotId, stored: null, current: version, reason: "出现新槽位" });
    }
  }
  for (const key of ["suite_version", "style_version", "shot_spec_version"]) {
    const stored = basis[key] === undefined ? null : basis[key];
    const now = current[key] === undefined ? null : current[key];
    if (stored !== now) {
      reasons.push({ field: key, stored: stored, current: now, reason: "版本已前进" });
    }
  }
  const platformVersion = isPlainObject(current.platform) ? current.platform.version : null;
  if ((basis.platform || {}).version !== platformVersion) {
    reasons.push({ field: "platform", stored: (basis.platform || {}).version ?? null, current: platformVersion, reason: "平台档版本前进" });
  }
  reasons.push(...providerStaleReasons(basis.provider, current.provider));
  return { stale: reasons.length > 0, reasons: reasons };
}

/** Provider 档的过期原因：目标 / 协议 / 版本 / 请求参数与能力边界任一不同或缺失即过期。 */
function providerStaleReasons(storedProvider, currentProvider) {
  const reasons = [];
  const stored = isPlainObject(storedProvider) ? storedProvider : null;
  const now = isPlainObject(currentProvider) ? currentProvider : null;
  if (!stored) {
    return [{ field: "provider", stored: null, current: now, reason: "记录缺少 Provider 档。" }];
  }
  if (!now) {
    return [{ field: "provider", stored: stored.version ?? null, current: null, reason: "当前 Provider 档缺失。" }];
  }
  const fields = ["provider_id", "model_id", "version", "protocol", ...IMAGE_PROFILE_FIELDS];
  const missing = fields.filter((key) => stored[key] === undefined || now[key] === undefined);
  if (missing.length > 0) {
    return [{
      field: "provider", stored: stored.version ?? null, current: now.version ?? null,
      reason: "Provider 档字段不完整：" + missing.join("、"),
    }];
  }
  const before = {};
  const after = {};
  for (const key of fields) {
    before[key] = stored[key];
    after[key] = now[key];
  }
  if (canonicalJson(before) !== canonicalJson(after)) {
    return [{
      field: "provider", stored: stored.version ?? null, current: now.version ?? null,
      reason: "Provider 档目标或请求参数变化",
    }];
  }
  return reasons;
}
