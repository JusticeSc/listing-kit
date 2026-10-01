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

/** Provider 档：qwen-image-3.0 合同（来源 = V1 `src/providers/dashscope_image.py` 的请求与校验）。 */
export const PROVIDER_PROFILES = Object.freeze({
  "qwen-image-3.0": Object.freeze({
    provider_id: "dashscope-qwen-image",
    model_id: "qwen-image-3.0",
    version: 1,
    size: "1344*1344",
    n: 1,
    prompt_extend: false,
    watermark: false,
    supports_negative_prompt_field: false,
    max_reference_images: 3,
    min_side: 384,
    max_side: 2048,
    min_area: 512 * 512,
    max_area: 2048 * 2048,
    min_ratio: 1 / 8,
    max_ratio: 8,
    max_prompt_chars: MAX_PROMPT_CHARS,
  }),
});

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
    provider: { model_id: provider.model_id, version: provider.version },
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
  const provider = resolveProfile("Provider", PROVIDER_PROFILES, input.providerId || "qwen-image-3.0");
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
  // 同一槽位的多条非目标语言文案合并为一条风险（给出条数），避免逐值重复上屏。
  const languageRisks = new Map();
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
          + "，图中将逐字保留原文，请人工确认是否使用。"
        : "商品事实「" + slotId + "」的文案不是 " + platform.on_image_text_language
          + "，图中将逐字保留原文，请人工确认是否使用。",
      source_refs: ["product_brief.fact:" + slotId, platformRef],
    });
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
    "输出规格：一张" + quoteLiteral(provider.size) + "的方形高清商品图，不添加水印。",
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
    provider: {
      provider_id: provider.provider_id,
      model_id: provider.model_id,
      version: provider.version,
      size: provider.size,
      n: provider.n,
      prompt_extend: provider.prompt_extend,
      watermark: provider.watermark,
      supports_negative_prompt_field: provider.supports_negative_prompt_field,
      max_prompt_chars: provider.max_prompt_chars,
    },
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
 * 参考图选择（Provider 感知）：先满足该 Shot 声明的 asset_role 依赖，再用主图补齐；
 * 数量不超过 Provider 上限；同一 sha256 只出现一次。选不出参考图时由请求快照统一报错。
 */
export function selectReferences(shot, references, options = {}) {
  const provider = resolveProfile("Provider", PROVIDER_PROFILES, options.providerId || "qwen-image-3.0");
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
      if (picked.length >= provider.max_reference_images) return picked;
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

/** 请求快照：只包含真实会发送的参数与参考图身份，不含图片字节；prompt 必须逐字等于编译文本。 */
export function requestSnapshotOf(compiled, options = {}) {
  assertCompiledPrompt(compiled);
  const provider = compiled.provider || {};
  const profile = PROVIDER_PROFILES[provider.model_id] || null;
  const refs = Array.isArray(options.references) ? options.references : [];
  if (profile && (refs.length < 1 || refs.length > profile.max_reference_images)) {
    invalid("参考图数量必须在 1.." + profile.max_reference_images + " 之间，当前 " + refs.length + " 张。");
  }
  const references = refs.map((item) => {
    if (!isPlainObject(item) || !isNonEmptyString(item.role)
        || !/^[0-9a-f]{64}$/.test(String(item.sha256 || ""))) {
      invalid("参考图必须带 role 与 sha256。");
    }
    return { role: item.role, sha256: item.sha256 };
  });
  return {
    model: provider.model_id,
    size: provider.size,
    n: provider.n,
    prompt_extend: provider.prompt_extend,
    watermark: provider.watermark,
    references: references,
    prompt: compiled.text,
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
  const provider = PROVIDER_PROFILES[(base.compiled.provider || {}).model_id] || null;
  const maxChars = provider ? provider.max_prompt_chars : MAX_PROMPT_CHARS;
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

/** 过期机检：槽位 basis、套图/风格/单图版本、平台与 Provider 档版本任一前进即过期。 */
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
  const providerVersion = isPlainObject(current.provider) ? current.provider.version : null;
  if ((basis.provider || {}).version !== providerVersion) {
    reasons.push({ field: "provider", stored: (basis.provider || {}).version ?? null, current: providerVersion, reason: "Provider 档版本前进" });
  }
  return { stale: reasons.length > 0, reasons: reasons };
}
