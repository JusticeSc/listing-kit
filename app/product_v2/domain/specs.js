/**
 * Product V2 规格层（V2.3.3，计划 §9.6）：公共 StyleSpec 与单图 ShotSpec。
 *
 * 唯一权威：两个文档的形状、默认值派生、差异、失效投影与审核清单投影都在本文件；
 * 失效语义复用 invalidation.js 的 invalidationsFor，不在本文件复制一张表。
 *
 * 三条不可协商的规则：
 *  1) 风格改动影响全套，单图规格改动只影响目标 Shot（由失效投影统一说清）；
 *  2) 未保存的规格用角色默认值投影，并明确标注「默认」，不假装用户设置过；
 *  3) 校验失败抛 CONTRACT_INVALID：界面不会把半成品写进版本历史。
 */

import { DOMAIN_ERROR_CODES, invalid } from "./errors.js";
import { invalidationsFor } from "./invalidation.js";
import { DIMENSION_AXES, DIMENSION_UNITS, MAX_DIMENSION_OBJECT_LENGTH, MAX_DIMENSION_SOURCE_LENGTH,
  SLOT_ID_PATTERN, isNonEmptyString, isPlainObject, isSha256Hex, pushProblem } from "./shared.js";

/** @type {number} 当前写入版本（设计 §13.8：结构展示决定/对象来源文案）。 */
export const STYLE_SPEC_SCHEMA_VERSION = 2;
/** @type {number} 当前写入版本（设计 §13.8：展示覆盖/对象来源文案/明确参考选择）。 */
export const SHOT_SPEC_SCHEMA_VERSION = 2;
/** @type {number} 已发布历史版本：只读分支精确理解 PR18 形状（含 presentation/print/layout/flat 文案）。 */
export const LEGACY_STYLE_SPEC_SCHEMA_VERSION = 1;
/** @type {number} 已发布历史版本：只读分支精确理解 PR18 形状。 */
export const LEGACY_SHOT_SPEC_SCHEMA_VERSION = 1;
/** @type {"style"} */
export const STYLE_SPEC_DOCUMENT_ID = "style";
/** @type {number} */
export const MAX_STYLE_TEXT = 200;
/** @type {number} */
export const MAX_STYLE_AVOID = 10;
/** @type {number} */
export const MAX_SHOT_PURPOSE = 200;
/** @type {number} */
export const MAX_SHOT_ITEMS = 8;
/** @type {number} */
export const MAX_SHOT_ITEM_LENGTH = 60;
/** 一张图最多明确几条图中文字；超出应让用户挑必要的，而不是自动截断。 @type {number} */
export const MAX_ON_IMAGE_TEXTS = 4;
/** 单条文案原文上限（与 PR18 一致：MAX_SHOT_ITEM_LENGTH 口径）。 @type {number} */
export const MAX_ON_IMAGE_TEXT_LENGTH = 60;
/** 需要用户明确印字决定的角色：印字不是这些角色的固定目的，而是这张图的表达选择。
 * 主图/场景/细节/自定义不问印字（缺失→none，无文字版面即合法）；下面五个角色缺失→undecided。
 * 编译器不再把任何角色的绑定事实自动印上图（facts_auto 已退役）。 */
export const PRINT_DECISION_ROLES = Object.freeze(["infographic", "size", "comparison", "ingredient", "packaging"]);
/** @type {readonly import("./type-contracts.js").ShotPrintIntent[]} */
export const SHOT_PRINT_INTENTS = Object.freeze(["none", "selected", "undecided"]);
/** @type {readonly import("./type-contracts.js").ShotLayout[]} */
export const SHOT_LAYOUTS = Object.freeze(["product_only", "product_left_text_right", "product_right_text_left"]);
/** @type {readonly import("./type-contracts.js").OnImageTextStatus[]} */
export const ON_IMAGE_TEXT_STATUSES = Object.freeze(["proposed", "confirmed"]);
/** @type {readonly import("./type-contracts.js").OnImageTextOrigin[]} */
export const ON_IMAGE_TEXT_ORIGINS = Object.freeze(["user", "model", "reuse"]);

/** 外观状态取值；「原样保持」是证据忠实的默认建议，清洁是用户的明确例外。 */
export const APPEARANCE_STATES = Object.freeze(["as_shown", "clean_display", "undecided"]);
/** 内容物状态取值；不适用用于不看内容物的用途（例如只量尺寸）。 */
export const CONTENTS_STATES = Object.freeze(["as_shown", "empty", "not_applicable", "undecided"]);
/** 视角取值：缺失即沿用有依据的视角（安全默认，非证据）；显式非默认视角须有参考图证据。 */
export const VIEWPOINTS = Object.freeze(["reference_visible", "front", "side", "top"]);
/** 参考图能证明的非默认视角词表。 @type {readonly string[]} */
export const REFERENCE_VIEWPOINTS = Object.freeze(["front", "side", "top"]);
/** 测量来源分类（人工对照 source_basis 逐项确认，程序不猜）。 */
export const MEASUREMENT_SOURCE_KINDS = Object.freeze(["nominal", "measured"]);
/** 来源分类的上图原文（确定性英文标签，UI/编译器共用，不另造词表）。 */
export const MEASUREMENT_SOURCE_LABEL = Object.freeze({ nominal: "Nominal", measured: "Measured" });
/**
 * 展示决定的字段定义与建议值。建议只是界面预选，存下来的「未决定」一律阻断消费该决定的图，
 * 程序不替用户默选清洁或倒空。
 */
export const PRESENTATION_FIELDS = Object.freeze([
  Object.freeze({ key: "appearance_state", label: "外观状态", states: APPEARANCE_STATES,
    suggestion: "as_shown",
    options: Object.freeze([
      Object.freeze({ value: "as_shown", label: "保持原样", hint: "连同原照里可见的使用痕迹一起保留，不做清洁。" }),
      Object.freeze({ value: "clean_display", label: "干净展示", hint: "允许去除临时使用痕迹（水渍、残留），不改材质、结构、标识与颜色。" }),
      Object.freeze({ value: "undecided", label: "还没决定", hint: "未决定时这张图不会发送。" }),
    ]) }),
  Object.freeze({ key: "contents_state", label: "内容物", states: CONTENTS_STATES,
    suggestion: "empty",
    options: Object.freeze([
      Object.freeze({ value: "empty", label: "倒空", hint: "内容物为空、瓶口干净，不添加资料里没有的内容物。" }),
      Object.freeze({ value: "as_shown", label: "保持原样", hint: "保留原照里可见的内容物。" }),
      Object.freeze({ value: "not_applicable", label: "不适用", hint: "这个用途不看内容物（例如只量尺寸、只看材质）。" }),
      Object.freeze({ value: "undecided", label: "还没决定", hint: "未决定时这张图不会发送。" }),
    ]) }),
  Object.freeze({ key: "viewpoint", label: "视角", states: VIEWPOINTS,
    suggestion: "reference_visible",
    options: Object.freeze([
      Object.freeze({ value: "reference_visible", label: "沿用照片里能看到的角度", hint: "不虚构背面、内部或没拍到的角度；这是安全的默认。" }),
      Object.freeze({ value: "front", label: "正面", hint: "需要有能看到正面的参考图依据；没有依据会被拦下。" }),
      Object.freeze({ value: "side", label: "侧面", hint: "需要有能看到侧面的参考图依据；没有依据会被拦下。" }),
      Object.freeze({ value: "top", label: "顶视", hint: "需要有能看到顶面的参考图依据；没有依据会被拦下。" }),
    ]) }),
]);
/**
 * 哪些角色消费哪项展示决定 —— 「问不问」的投影依据：不消费的用途不因未决定而拦截。
 * 外观状态：所有呈现商品表面的用途都要表达真实表面状态。
 * 内容物：只有会看到内部/随附物/使用中的用途才需要这项决定。
 * 视角：所有用途都沿用有依据的视角；显式非默认视角逐图查证据。
 */
export const PRESENTATION_CONSUMERS = Object.freeze({
  appearance_state: Object.freeze([
    "main", "infographic", "scene", "detail", "size", "comparison", "ingredient", "packaging",
    "custom",
  ]),
  contents_state: Object.freeze(["scene", "ingredient", "packaging", "custom"]),
  viewpoint: Object.freeze([
    "main", "infographic", "scene", "detail", "size", "comparison", "ingredient", "packaging",
    "custom",
  ]),
});

/** @type {readonly import("./type-contracts.js").StyleSpecField[]} */
export const STYLE_SPEC_FIELDS = Object.freeze([
  Object.freeze({ key: "background", label: "背景风格", kind: "text" }),
  Object.freeze({ key: "lighting", label: "光线", kind: "text" }),
  Object.freeze({ key: "color_tone", label: "色调", kind: "text" }),
  Object.freeze({ key: "composition", label: "构图约定", kind: "text" }),
  Object.freeze({ key: "avoid", label: "避免出现", kind: "list" }),
]);

/** @type {readonly string[]} V1=V2 同一键集合：V1 是 PR18 已发布形状（含 presentation/print/layout），
 * 不是封存旧草稿的 allowlist。V2 新增 reference_sha256s（明确参考子集）。 */
const STYLE_KEYS = Object.freeze(["schema_version", ...STYLE_SPEC_FIELDS.map((item) => item.key),
  "presentation"]);
/** @type {readonly string[]} */
const SHOT_KEYS_V1 = Object.freeze(["schema_version", "purpose", "keep", "change_allowed", "notes",
  "print_intent", "layout", "on_image_texts", "presentation"]);
/** @type {readonly string[]} */
const SHOT_KEYS = Object.freeze([...SHOT_KEYS_V1, "reference_sha256s"]);

/** 失效目标的人读名字；投影文本与界面提示共用这一份。 @type {Readonly<Record<string, string>>} */
export const ARTIFACT_LABELS = Object.freeze({
  prompt_versions: "Prompt 版本",
  review_reports: "审核报告",
  selection: "人工选择",
  suite_consistency_report: "整套一致性报告",
  product_brief: "商品理解",
  suite_plan: "套图计划",
  source_assets: "参考图",
  project_history: "项目历史",
  candidate_blobs: "候选图片",
  shot_spec: "单图规格",
  other_shots: "其他图片",
  unreferenced_shots: "未受影响的图片",
  existing_shot_history: "既有图片历史",
  selection_completeness: "选择完整性",
  suite_plan_revision: "套图计划版本",
});

/* ------------------------------------------------------------------ 公共风格 */

/**
 * 生成一份空白公共风格规格（未配置状态）。
 * @returns {import("./type-contracts.js").StyleSpec}
 */
export function emptyStyleSpec() {
  return {
    schema_version: STYLE_SPEC_SCHEMA_VERSION,
    background: "",
    lighting: "",
    color_tone: "",
    composition: "",
    avoid: [],
  };
}

/**
 * 校验单个文本字段（长度上限由调用方给出 label 描述）。
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {Record<string, unknown>} spec
 * @param {string} key
 * @param {string} label
 * @returns {void}
 */
function checkStyleText(problems, spec, key, label) {
  const value = spec[key];
  if (value === undefined || value === null) return;
  if (typeof value !== "string") {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$." + key,
      label + "必须是文本。");
    return;
  }
  if (value.length > MAX_STYLE_TEXT) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$." + key,
      label + "最长 " + MAX_STYLE_TEXT + " 字。");
  }
}

/**
 * 公共风格规格的形状与内容校验；返回问题列表（空 = 合法）。
 * 版本分派：schema_version=1 走 PR18 精确只读分支，=2 走当前写入分支；未知版本拒绝。
 * @param {unknown} spec
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkStyleSpec(spec) {
  if (isPlainObject(spec) && spec.schema_version === LEGACY_STYLE_SPEC_SCHEMA_VERSION) {
    return checkStyleSpecV1(spec);
  }
  return checkStyleSpecV2(spec);
}

/**
 * 公共风格 V1（PR18 已发布形状）只读校验：文本字段 + 可选 presentation（外观/内容物/视角均可出现）。
 * V1 的视角键在 PR18 时代不存在，但历史读分支不因未知键拒绝已发布视角值——视角取值仍须在词表内。
 * @param {unknown} spec
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkStyleSpecV1(spec) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
  const problems = [];
  if (!isPlainObject(spec)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "风格规格必须是对象。");
    return problems;
  }
  if (spec.schema_version !== LEGACY_STYLE_SPEC_SCHEMA_VERSION) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.schema_version",
      "风格规格版本必须是 " + LEGACY_STYLE_SPEC_SCHEMA_VERSION + "。");
  }
  for (const key of Object.keys(spec)) {
    if (!STYLE_KEYS.includes(key)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$." + key,
        "字段 " + key + " 不在风格规格内。");
    }
  }
  checkStyleFields(problems, spec);
  checkPresentation(problems, spec, "$.presentation");
  return problems;
}

/**
 * 公共风格 V2（当前写入）严格校验；新写入必须通过本函数。
 * @param {unknown} spec
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkStyleSpecV2(spec) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
  const problems = [];
  if (!isPlainObject(spec)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "风格规格必须是对象。");
    return problems;
  }
  if (spec.schema_version !== STYLE_SPEC_SCHEMA_VERSION) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.schema_version",
      "风格规格版本必须是 " + STYLE_SPEC_SCHEMA_VERSION + "。");
  }
  for (const key of Object.keys(spec)) {
    if (!STYLE_KEYS.includes(key)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$." + key,
        "字段 " + key + " 不在风格规格内。");
    }
  }
  checkStyleFields(problems, spec);
  checkPresentation(problems, spec, "$.presentation");
  return problems;
}

/**
 * 公共风格共有的文本/列表字段校验（新旧版本共用）。
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {Record<string, unknown>} spec
 * @returns {void}
 */
function checkStyleFields(problems, spec) {
  for (const field of STYLE_SPEC_FIELDS) {
    if (field.kind === "text") {
      checkStyleText(problems, spec, field.key, field.label);
      continue;
    }
    const avoid = spec.avoid;
    if (avoid === undefined || avoid === null) continue;
    if (!Array.isArray(avoid)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.avoid",
        field.label + "必须是一行一条的列表。");
      continue;
    }
    if (avoid.length > MAX_STYLE_AVOID) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.avoid",
        field.label + "最多 " + MAX_STYLE_AVOID + " 条。");
    }
    const seen = new Set();
    avoid.forEach((item, index) => {
      const path = "$.avoid[" + index + "]";
      if (!isNonEmptyString(item) || item.length > MAX_SHOT_ITEM_LENGTH) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path,
          "每条最多 " + MAX_SHOT_ITEM_LENGTH + " 字且不能为空。");
      } else if (seen.has(item)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "不允许重复。");
      } else {
        seen.add(item);
      }
    });
  }
}

/**
 * 判断公共风格是否完全未配置（或根本不是一个对象）。
 * @param {unknown} spec
 * @returns {boolean}
 */
export function styleSpecIsEmpty(spec) {
  if (!isPlainObject(spec)) return true;
  return styleSpecSummary(spec).length === 0;
}

/**
 * 公共风格的界面摘要（每条一段人读文本）；未配置返回空数组。
 * @param {unknown} spec
 * @returns {import("./type-contracts.js").StyleSpecSummaryItem[]}
 */
export function styleSpecSummary(spec) {
  if (!isPlainObject(spec)) return [];
  /** @type {import("./type-contracts.js").StyleSpecSummaryItem[]} */
  const items = [];
  for (const field of STYLE_SPEC_FIELDS) {
    const value = spec[field.key];
    if (field.kind === "text") {
      if (!isNonEmptyString(value)) continue;
      const trimmed = value.trim();
      items.push({ key: field.key, label: field.label, kind: "text",
        value: trimmed, text: field.label + "：" + trimmed });
      continue;
    }
    const list = Array.isArray(value)
      ? value.filter((item) => isNonEmptyString(item)).map((item) => item.trim())
      : [];
    if (list.length === 0) continue;
    items.push({ key: field.key, label: field.label, kind: "list",
      value: list, text: field.label + "：" + list.join("、") });
  }
  for (const field of PRESENTATION_FIELDS) {
    const state = presentationStateOf(spec, field.key);
    // 视角默认即沿用有依据的视角：只在用户显式选择非默认视角时才列入摘要。
    if (field.key === "viewpoint" ? state === "reference_visible" : state === "undecided") continue;
    items.push({ key: field.key, label: field.label, kind: "text",
      value: presentationLabel(field, state),
      text: field.label + "：" + presentationLabel(field, state) });
  }
  return items;
}

/**
 * 展示决定的取值：只认允许列表内的值。外观/内容物缺失一律视为未决定；
 * 视角缺失视为沿用有依据的视角（安全默认，非证据）。
 * 注意：本函数只读单份规格，不做共用/单图继承；继承由编译器的 effectivePresentation
 * 按「单图是否自有该键」决定——单图显式 undecided 不是继承。
 * @param {Record<string, unknown> | null | undefined} spec
 * @param {string} key
 * @returns {string}
 */
export function presentationStateOf(spec, key) {
  const field = PRESENTATION_FIELDS.find((item) => item.key === key);
  if (!field) return "undecided";
  const presentation = isPlainObject(spec) ? spec.presentation : null;
  const state = isPlainObject(presentation) ? presentation[key] : undefined;
  if (field.states.includes(state)) return state;
  return key === "viewpoint" ? "reference_visible" : "undecided";
}

/**
 * 单图规格是否自有某展示决定键（区分「显式未决定」与「缺失即继承」）。
 * @param {unknown} spec
 * @param {string} key
 * @returns {boolean}
 */
export function presentationHasOwn(spec, key) {
  return isPlainObject(spec) && isPlainObject(spec.presentation)
    && Object.prototype.hasOwnProperty.call(spec.presentation, key);
}

/**
 * 这张图是否需要用户明确印字决定（决定权在角色，不在单个规格）。
 * @param {unknown} shot
 * @returns {boolean}
 */
export function printDecisionRoleOf(shot) {
  const roleId = isPlainObject(shot) ? shot.role_id : null;
  return PRINT_DECISION_ROLES.includes(roleId);
}

/**
 * 有效印字决定（只由本文件定义，编译器与清单共用一份）：存过就照存，
 * 没存过时「需要该决定的角色」是未决定，「其他角色」是不印新增文字。
 * 旧 facts_auto（把绑定事实自动印上图）已退役：新编译器只印明确选择的 confirmed 文案；
 * 只有 Parent 拥有的历史 Prompt 记录读分支还理解旧 facts_auto 正文。
 * @param {unknown} shotSpec
 * @param {unknown} shot
 * @returns {"none" | "selected" | "undecided"}
 */
export function effectivePrintIntentOf(shotSpec, shot) {
  const stored = isPlainObject(shotSpec) ? shotSpec.print_intent : null;
  if (SHOT_PRINT_INTENTS.includes(stored)) return /** @type {never} */ (stored);
  return printDecisionRoleOf(shot) ? "undecided" : "none";
}

/** 印字决定的人读名字（界面与清单共用）。 @param {string} intent @returns {string} */
export function printIntentLabelOf(intent) {
  if (intent === "none") return "不印新增文字";
  if (intent === "selected") return "只印所选文案";
  if (intent === "undecided") return "还没决定";
  return "按角色既有合同";
}

/** 版面的人读名字（界面与清单共用）。 @param {unknown} layout @returns {string} */
export function layoutLabelOf(layout) {
  if (layout === "product_left_text_right") return "商品在左、文字在右";
  if (layout === "product_right_text_left") return "商品在右、文字在左";
  return "只放商品";
}

/**
 * 展示决定取值的人读名字（界面与摘要共用一份词表）。
 * @param {import("./type-contracts.js").StyleSpecField | { key: string, label: string, options?: readonly { value: string, label: string }[] }} field
 * @param {string} state
 * @returns {string}
 */
export function presentationLabel(field, state) {
  const option = (field.options || []).find((item) => item.value === state);
  return option ? option.label : state;
}

/**
 * 展示决定的校验：形状、取值；未给出的键视为「未决定」，不填建议值也不拦截保存。
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {Record<string, unknown>} spec
 * @param {string} path
 * @returns {void}
 */
function checkPresentation(problems, spec, path) {
  const value = spec.presentation;
  if (value === undefined || value === null) return;
  if (!isPlainObject(value)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path,
      "展示决定必须是对象（外观状态/内容物/视角）。");
    return;
  }
  for (const key of Object.keys(value)) {
    if (!PRESENTATION_FIELDS.some((field) => field.key === key)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + "." + key,
        "字段 " + key + " 不在展示决定内。");
    }
  }
  for (const field of PRESENTATION_FIELDS) {
    const state = value[field.key];
    if (state === undefined || state === null) continue;
    if (!field.states.includes(state)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + "." + field.key,
        field.label + "取值不在允许列表内。");
    }
  }
}

/**
 * 字段值的规范化比较形态：text → trim；list → 过滤空项后逐条 trim。
 * @param {import("./type-contracts.js").StyleSpecField} field
 * @param {Record<string, unknown> | null | undefined} spec
 * @returns {string | string[]}
 */
function normalizedStyleValue(field, spec) {
  const value = spec ? spec[field.key] : undefined;
  if (field.kind === "text") return isNonEmptyString(value) ? value.trim() : "";
  return Array.isArray(value)
    ? value.filter((item) => isNonEmptyString(item)).map((item) => item.trim())
    : [];
}

/**
 * 公共风格的前后差异（逐字段 before/after）；无差异返回空数组。
 * @param {Record<string, unknown> | null | undefined} previous
 * @param {Record<string, unknown> | null | undefined} next
 * @returns {import("./type-contracts.js").SpecDiffItem[]}
 */
export function styleSpecDiff(previous, next) {
  const diffs = [];
  for (const field of STYLE_SPEC_FIELDS) {
    const before = normalizedStyleValue(field, previous);
    const after = normalizedStyleValue(field, next);
    if (JSON.stringify(before) !== JSON.stringify(after)) {
      diffs.push({ field: field.key, label: field.label, before, after });
    }
  }
  for (const field of PRESENTATION_FIELDS) {
    const before = presentationStateOf(previous, field.key);
    const after = presentationStateOf(next, field.key);
    if (before !== after) {
      diffs.push({ field: field.key, label: field.label, before, after });
    }
  }
  return diffs;
}

/* ------------------------------------------------------------------ 单图规格 */

/** 每种角色的默认「必须保持」；未保存规格时用这份投影。 @type {Readonly<Record<string, string[]>>} */
const DEFAULT_KEEP_BY_ROLE = Object.freeze({
  main: ["商品外观、颜色与比例", "标识与文字"],
  infographic: ["已确认卖点文字"],
  scene: ["商品外观与颜色", "标识与文字"],
  detail: ["材质与工艺细节", "颜色"],
  size: ["尺寸数字与单位"],
  comparison: ["商品外观与标识"],
  ingredient: ["配料与成分列表"],
  packaging: ["包装形态与随附物"],
  custom: ["商品外观与标识"],
});

/** 每种角色的默认「允许变化」；与 keep 同一份口径。 @type {Readonly<Record<string, string[]>>} */
const DEFAULT_ALLOW_BY_ROLE = Object.freeze({
  main: ["背景"],
  infographic: ["标注排版与配色"],
  scene: ["环境、道具与光线"],
  detail: ["对焦、景别与光线"],
  size: ["标注样式与排版"],
  comparison: ["对比版式"],
  ingredient: ["摆盘与构图"],
  packaging: ["陈设与光线"],
  custom: ["构图、场景与光线"],
});

/**
 * 从 Shot 派生一份默认单图规格（目的取 intent/label，keep/change_allowed 按角色默认）。
 *
 * 印字决定只在需要该决定的角色上投影：默认「未决定」，让用户明确选择要印的文案，
 * 而不是把这张图绑定的全部事实自动印上图；其他角色不出现该字段（有效决定=不印新增文字）。
 * @param {unknown} shot
 * @returns {import("./type-contracts.js").ShotSpec}
 */
export function emptyShotSpecFromShot(shot) {
  const roleId = isPlainObject(shot) && typeof shot.role_id === "string" ? shot.role_id : "custom";
  const purpose = isPlainObject(shot) && isNonEmptyString(shot.intent)
    ? shot.intent.trim()
    : (isPlainObject(shot) && isNonEmptyString(shot.label) ? shot.label.trim() : "这张图要达成什么");
  /** @type {import("./type-contracts.js").ShotSpec} */
  const spec = {
    schema_version: SHOT_SPEC_SCHEMA_VERSION,
    purpose,
    keep: [...(DEFAULT_KEEP_BY_ROLE[roleId] || DEFAULT_KEEP_BY_ROLE.custom)],
    change_allowed: [...(DEFAULT_ALLOW_BY_ROLE[roleId] || DEFAULT_ALLOW_BY_ROLE.custom)],
    notes: "",
  };
  if (PRINT_DECISION_ROLES.includes(roleId)) {
    spec.print_intent = "undecided";
    // 版面同样是用户决定：未决定就不写这个键（与 presentation 的「缺失＝未决定」一致，
    // 也避免把空串当成非法取值）。少了它只会让「要印文案」的图在编译门被拦下，
    // 不会静默替用户选一个版面。
    spec.on_image_texts = [];
  }
  return spec;
}

/**
 * 校验 keep / change_allowed 列表（元素类型、上限与去重）；可要求至少一项。
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {Record<string, unknown>} spec
 * @param {string} key
 * @param {string} label
 * @param {{required: boolean}} options
 * @returns {void}
 */
function checkShotItems(problems, spec, key, label, { required }) {
  const value = spec[key];
  if (value === undefined || value === null) {
    if (required) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$." + key,
        label + "至少要有一项。");
    }
    return;
  }
  if (!Array.isArray(value)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$." + key,
      label + "必须是列表。");
    return;
  }
  if (required && value.length === 0) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$." + key,
      label + "至少要有一项。");
  }
  if (value.length > MAX_SHOT_ITEMS) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$." + key,
      label + "最多 " + MAX_SHOT_ITEMS + " 项。");
  }
  const seen = new Set();
  value.forEach((item, index) => {
    const path = "$." + key + "[" + index + "]";
    if (!isNonEmptyString(item) || item.length > MAX_SHOT_ITEM_LENGTH) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path,
        "每项最多 " + MAX_SHOT_ITEM_LENGTH + " 字且不能为空。");
    } else if (seen.has(item)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "不允许重复。");
    } else {
      seen.add(item);
    }
  });
}

/**
 * 单图规格的形状与内容校验；返回问题列表（空 = 合法）。
 * 版本分派：schema_version=1 走 PR18 精确只读分支，=2 走当前写入分支；未知版本拒绝。
 * @param {unknown} spec
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkShotSpec(spec) {
  if (isPlainObject(spec) && spec.schema_version === LEGACY_SHOT_SPEC_SCHEMA_VERSION) {
    return checkShotSpecV1(spec);
  }
  return checkShotSpecV2(spec);
}

/**
 * 单图规格 V1（PR18 已发布形状）只读校验：flat 来源文案、print/layout/presentation 均可出现。
 * 这是已发布形状的精确理解，不是封存旧草稿的 allowlist。
 * @param {unknown} spec
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkShotSpecV1(spec) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
  const problems = [];
  if (!isPlainObject(spec)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "单图规格必须是对象。");
    return problems;
  }
  if (spec.schema_version !== LEGACY_SHOT_SPEC_SCHEMA_VERSION) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.schema_version",
      "单图规格版本必须是 " + LEGACY_SHOT_SPEC_SCHEMA_VERSION + "。");
  }
  for (const key of Object.keys(spec)) {
    if (!SHOT_KEYS_V1.includes(key)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$." + key,
        "字段 " + key + " 不在单图规格内。");
    }
  }
  checkShotSpecFields(problems, spec);
  checkShotPrintIntent(problems, spec);
  checkShotOnImageTexts(problems, spec, { version: 1 });
  checkPresentation(problems, spec, "$.presentation");
  return problems;
}

/**
 * 单图规格 V2（当前写入）严格校验：文案来源必须是对象 source（不再写 flat），
 * measurement/measurement_source 二选一由 imageTextProblems 复核；新写入必须通过本函数。
 * @param {unknown} spec
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkShotSpecV2(spec) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
  const problems = [];
  if (!isPlainObject(spec)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "单图规格必须是对象。");
    return problems;
  }
  if (spec.schema_version !== SHOT_SPEC_SCHEMA_VERSION) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.schema_version",
      "单图规格版本必须是 " + SHOT_SPEC_SCHEMA_VERSION + "。");
  }
  for (const key of Object.keys(spec)) {
    if (!SHOT_KEYS.includes(key)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$." + key,
        "字段 " + key + " 不在单图规格内。");
    }
  }
  checkShotSpecFields(problems, spec);
  checkShotPrintIntent(problems, spec);
  checkShotOnImageTexts(problems, spec, { version: 2 });
  checkPresentation(problems, spec, "$.presentation");
  checkReferenceSelection(problems, spec);
  return problems;
}

/**
 * 单图规格共有的目的/必须保持/允许变化/备注校验（新旧版本共用）。
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {Record<string, unknown>} spec
 * @returns {void}
 */
function checkShotSpecFields(problems, spec) {
  if (!isNonEmptyString(spec.purpose)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.purpose",
      "目的不能为空：这张图要达成什么必须先说清。");
  } else if (spec.purpose.length > MAX_SHOT_PURPOSE) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.purpose",
      "目的最长 " + MAX_SHOT_PURPOSE + " 字。");
  }
  checkShotItems(problems, spec, "keep", "必须保持", { required: true });
  checkShotItems(problems, spec, "change_allowed", "允许变化", { required: true });
  if (spec.notes !== undefined && spec.notes !== null && typeof spec.notes !== "string") {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.notes", "备注必须是文本。");
  } else if (typeof spec.notes === "string" && spec.notes.length > MAX_STYLE_TEXT) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.notes",
      "备注最长 " + MAX_STYLE_TEXT + " 字。");
  }
}

/**
 * 明确参考子集的形状校验：缺失=用本图角色依据；空数组=明确无依据（编译阻断，不回退）。
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {Record<string, unknown>} spec
 * @returns {void}
 */
function checkReferenceSelection(problems, spec) {
  const value = spec.reference_sha256s;
  if (value === undefined || value === null) return;
  if (!Array.isArray(value)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.reference_sha256s",
      "明确参考子集必须是 SHA 列表。");
    return;
  }
  const seen = new Set();
  value.forEach((sha, index) => {
    const path = "$.reference_sha256s[" + index + "]";
    if (!isSha256Hex(sha)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path,
        "参考图身份必须是 64 位小写 SHA256。");
    } else if (seen.has(sha)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "参考图不能重复选择。");
    } else {
      seen.add(sha);
    }
  });
}

/**
 * 印字决定与布局的取值校验；两个字段都可缺失（缺失=按角色既有合同）。
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {Record<string, unknown>} spec
 * @returns {void}
 */
function checkShotPrintIntent(problems, spec) {
  if (spec.print_intent !== undefined && spec.print_intent !== null
    && !SHOT_PRINT_INTENTS.includes(spec.print_intent)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.print_intent",
      "印字决定只能是 none／selected／undecided。");
  }
  if (spec.layout !== undefined && spec.layout !== null && !SHOT_LAYOUTS.includes(spec.layout)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.layout",
      "布局取值不在允许列表内。");
  }
}

/**
 * 所选图中文字的校验：形状、条数、唯一 id、原文长度与来源版本。
 * 只校验形状与可判定性；「来源是否是当前确认值」由编译期按当前事实核对。
 * V1 分支精确理解 PR18 flat 形状（也容忍对象 source 的已发布混合）；V2 要求对象 source。
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {Record<string, unknown>} spec
 * @param {{version: number}} options
 * @returns {void}
 */
function checkShotOnImageTexts(problems, spec, { version }) {
  const value = spec.on_image_texts;
  if (value === undefined || value === null) return;
  if (!Array.isArray(value)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.on_image_texts",
      "所选图中文字必须是列表。");
    return;
  }
  if (value.length > MAX_ON_IMAGE_TEXTS) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.on_image_texts",
      "一张图最多 " + MAX_ON_IMAGE_TEXTS + " 条图中文字。");
  }
  const seen = new Set();
  value.forEach((item, index) => {
    const path = "$.on_image_texts[" + index + "]";
    if (!isPlainObject(item)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "每条图中文字必须是对象。");
      return;
    }
    if (!isNonEmptyString(item.text_id)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".text_id", "缺少稳定的条目 id。");
    } else if (seen.has(item.text_id)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".text_id", "条目 id 不允许重复。");
    } else {
      seen.add(item.text_id);
    }
    if (!isNonEmptyString(item.text) || item.text.length > MAX_ON_IMAGE_TEXT_LENGTH) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".text",
        "原文不能为空且最多 " + MAX_ON_IMAGE_TEXT_LENGTH + " 字。");
    }
    if (version === 2) {
      checkImageTextSource(problems, path, item);
    } else if (!checkImageTextSourceLoose(problems, path, item)) {
      // V1 只读：flat 与对象两种已发布形状都理解；都不满足才报。
    }
    if (!ON_IMAGE_TEXT_STATUSES.includes(item.status)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".status",
        "状态只能是 proposed／confirmed。");
    }
    if (!ON_IMAGE_TEXT_ORIGINS.includes(item.origin)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".origin",
        "来源只能是 user／model／reuse。");
    }
    checkMeasurementBindings(problems, path, item);
  });
}

/**
 * V2 文案来源：必须是 source 对象（kind=document 精确引用）。
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {string} path
 * @param {Record<string, unknown>} item
 * @returns {void}
 */
function checkImageTextSource(problems, path, item) {
  const source = item.source;
  if (!isPlainObject(source)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".source",
      "必须指明这条文案来自哪个已确认事实（source 对象）。");
    return;
  }
  if (source.kind !== "fact_slot") {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".source.kind",
      "来源 kind 必须是 fact_slot。");
  }
  if (typeof source.document_id !== "string" || !SLOT_ID_PATTERN.test(source.document_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".source.document_id",
      "来源槽位标识不合法。");
  }
  if (!Number.isInteger(source.version) || source.version < 1) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".source.version",
      "来源版本必须是正整数。");
  }
  for (const key of Object.keys(source)) {
    if (!["kind", "document_id", "version"].includes(key)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".source." + key,
        "字段 " + key + " 不在来源引用内。");
    }
  }
  if (item.source_slot_id !== undefined || item.source_slot_version !== undefined) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".source",
      "新版本不再写 flat 来源字段（source_slot_id/source_slot_version）。");
  }
}

/**
 * V1 文案来源只读理解：flat 或对象任一合法即通过（已发布混合形状）。
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {string} path
 * @param {Record<string, unknown>} item
 * @returns {boolean} 任一形状合法
 */
function checkImageTextSourceLoose(problems, path, item) {
  if (imageTextSourceOf(item)) return true;
  pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".source_slot_id",
    "必须指明这条文案来自哪个已确认事实。");
  return false;
}

/**
 * measurement/measurement_source 的形状校验（二选一，V1/V2 共用形状口径）。
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {string} path
 * @param {Record<string, unknown>} item
 * @returns {void}
 */
function checkMeasurementBindings(problems, path, item) {
  const hasSingle = item.measurement !== undefined && item.measurement !== null;
  const hasGroup = item.measurement_source !== undefined && item.measurement_source !== null;
  if (hasSingle && hasGroup) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".measurement",
      "单条测量绑定与分组来源标签只能二选一。");
    return;
  }
  if (hasSingle) checkMeasurementBinding(problems, path + ".measurement", item.measurement);
  if (hasGroup) checkMeasurementSourceBinding(problems, path + ".measurement_source", item.measurement_source);
}

/**
 * 单条测量绑定的形状校验：索引 + 确认标签 + 原始测量四元。
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {string} path
 * @param {unknown} binding
 * @returns {void}
 */
function checkMeasurementBinding(problems, path, binding) {
  if (!isPlainObject(binding)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "测量绑定必须是对象。");
    return;
  }
  if (!Number.isInteger(binding.index) || binding.index < 0) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".index",
      "测量索引必须是非负整数。");
  }
  // 标签二选一：只给轴向标签（纯型号/参数值），或对象+轴向都给；
  // 只给对象不给轴向没有合法纸面形状，直接拒绝。
  if (!isNonEmptyString(binding.axis_label)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".axis_label",
      "轴向英文标签不能为空（须人工确认映射）。");
  }
  if (binding.object_label !== undefined && binding.object_label !== null
    && typeof binding.object_label !== "string") {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".object_label",
      "对象英文标签必须是文本。");
  }
  if (!MEASUREMENT_SOURCE_KINDS.includes(binding.source_kind)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".source_kind",
      "来源分类只能是 nominal／measured（须人工对照来源依据确认）。");
  }
  if (!isNonEmptyString(binding.object) || binding.object.length > MAX_DIMENSION_OBJECT_LENGTH) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".object",
      "测量对象必须与来源确认值的对象逐字一致（1-" + MAX_DIMENSION_OBJECT_LENGTH + " 字）。");
  }
  if (!DIMENSION_AXES.includes(binding.axis)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".axis",
      "测量轴向必须与来源确认值的轴向一致（" + DIMENSION_AXES.join("/") + "）。");
  }
  if (typeof binding.value !== "number" || !Number.isFinite(binding.value) || binding.value <= 0) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".value",
      "测量数值必须与来源确认值的数值一致（有限正数）。");
  }
  if (!DIMENSION_UNITS.includes(binding.unit)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".unit",
      "测量单位必须与来源确认值的单位一致（" + DIMENSION_UNITS.join("/") + "）。");
  }
  if (!isNonEmptyString(binding.source_basis) || binding.source_basis.length > MAX_DIMENSION_SOURCE_LENGTH) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".source_basis",
      "测量来源依据必须与来源确认值逐字一致（1-" + MAX_DIMENSION_SOURCE_LENGTH + " 字）。");
  }
}

/**
 * 分组来源标签的形状校验：索引集 + 测量快照 + 统一分类。
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {string} path
 * @param {unknown} binding
 * @returns {void}
 */
function checkMeasurementSourceBinding(problems, path, binding) {
  if (!isPlainObject(binding)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "分组来源标签必须是对象。");
    return;
  }
  if (!Array.isArray(binding.indices) || binding.indices.length === 0
    || !binding.indices.every((index) => Number.isInteger(index) && index >= 0)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".indices",
      "分组索引必须是非空非负整数列表。");
  }
  if (!Array.isArray(binding.measurements) || binding.measurements.length === 0) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".measurements",
      "分组必须携带所覆盖测量项的快照。");
  } else if (Array.isArray(binding.indices)
    && binding.measurements.length !== binding.indices.length) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".measurements",
      "分组测量快照必须与索引一一对应。");
  } else {
    binding.measurements.forEach((item, position) => {
      const itemPath = path + ".measurements[" + position + "]";
      if (!isPlainObject(item) || !isNonEmptyString(item.object) || !isNonEmptyString(item.axis)
        || typeof item.value !== "number" || !Number.isFinite(item.value)
        || !isNonEmptyString(item.unit) || !isNonEmptyString(item.source_basis)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, itemPath,
          "分组测量项必须是完整的测量快照（对象/轴向/数值/单位/来源依据）。");
      }
    });
  }
  if (!MEASUREMENT_SOURCE_KINDS.includes(binding.source_kind)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".source_kind",
      "来源分类只能是 nominal／measured（须人工对照来源依据确认）。");
  }
}

/* ------------------------------------------------- 图中文案来源与测量绑定 */

/**
 * 文案的规范来源引用：当前对象 source 与已发布 flat 来源都精确理解（只读方向）。
 * 非法形状一律返回 null（调用方按缺来源报可操作问题，不抛错）。
 * @param {unknown} item
 * @returns {{kind: "fact_slot", document_id: string, version: number} | null}
 */
export function imageTextSourceOf(item) {
  if (!isPlainObject(item)) return null;
  const source = item.source;
  if (isPlainObject(source)) {
    if (source.kind !== "fact_slot") return null;
    if (typeof source.document_id !== "string" || !SLOT_ID_PATTERN.test(source.document_id)) return null;
    if (!Number.isInteger(source.version) || source.version < 1) return null;
    return { kind: "fact_slot", document_id: source.document_id, version: source.version };
  }
  // 已发布 flat 形状（schema1 只读理解）：任一缺失即非法。
  if (typeof item.source_slot_id !== "string" || !SLOT_ID_PATTERN.test(item.source_slot_id)) return null;
  if (!Number.isInteger(item.source_slot_version) || item.source_slot_version < 1) return null;
  return { kind: "fact_slot", document_id: item.source_slot_id, version: item.source_slot_version };
}

/**
 * 数字的确定性上图文本：整数不带小数点，非整数用最短往返表示（String(value)）。
 * 负数/非有限数不在这里拦（形状校验负责），但绝不输出 NaN/Infinity 上图。
 * @param {number} value
 * @returns {string | null} 非法数字返回 null
 */
function canonicalNumberText(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return String(value);
}

/**
 * 单条测量的确定性上图文本（设计 §13.14.4）：「标签: 数值 单位」或「标签: 数值 单位 (来源)」。
 * 标签取人工确认的 object_label/axis_label 组合：object_label 非空时「对象 轴向」，
 * 否则只用轴向标签。数值/单位/来源标签三处全部来自绑定原文，不做任何改写。
 * @param {import("./type-contracts.js").MeasurementBinding} binding
 * @param {{includeSource?: boolean}} [options] 默认 true（含来源后缀）；UI 预览可用 false 只看数值部分
 * @returns {string | null} 绑定形状非法时返回 null（调用方按形状问题报，不抛错）
 */
export function formatMeasurementText(binding, { includeSource = true } = {}) {
  if (!isPlainObject(binding)) return null;
  if (!isNonEmptyString(binding.axis_label)) return null;
  if (!MEASUREMENT_SOURCE_KINDS.includes(binding.source_kind)) return null;
  if (typeof binding.value !== "number" || !Number.isFinite(binding.value)) return null;
  if (!isNonEmptyString(binding.unit)) return null;
  const digits = canonicalNumberText(binding.value);
  if (digits === null) return null;
  const objectLabel = typeof binding.object_label === "string" ? binding.object_label.trim() : "";
  const axisLabel = binding.axis_label.trim();
  const label = objectLabel ? objectLabel + " " + axisLabel : axisLabel;
  const unit = binding.unit.trim();
  const core = label + ": " + digits + " " + unit;
  if (!includeSource) return core;
  return core + " (" + MEASUREMENT_SOURCE_LABEL[binding.source_kind] + ")";
}

/**
 * 文案的测量/来源精确性复核（编译/确认共用）：只返回问题，不抛错、不修改输入。
 * 无测量绑定的文案直接通过（plain 文案的确认/版本门在 decisionProblems，不在这里重复）。
 * 有绑定的文案逐项核对：来源槽位已确认且版本一致→槽位值是 dimension_list→
 * 索引命中→快照四元与来源值逐字节相等→条目原文逐字等于规范文本。
 * @param {unknown} item
 * @param {{brief?: unknown, shotSpec?: unknown}} [options] brief 必须有 confirmed_facts/basis；shotSpec 保留供未来同条复核
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function imageTextProblems(item, { brief = null } = {}) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
  const problems = [];
  if (!isPlainObject(item)) return problems;
  const hasSingle = item.measurement !== undefined && item.measurement !== null;
  const hasGroup = item.measurement_source !== undefined && item.measurement_source !== null;
  if (!hasSingle && !hasGroup) return problems;
  if (hasSingle && hasGroup) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.measurement",
      "单条测量绑定与分组来源标签只能二选一。");
    return problems;
  }
  const source = imageTextSourceOf(item);
  if (!source) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.source",
      "这条文案缺少可判定的来源引用，无法核对测量绑定。");
    return problems;
  }
  const confirmed = new Map((isPlainObject(brief) && Array.isArray(brief.confirmed_facts)
    ? brief.confirmed_facts : []).filter((fact) => isPlainObject(fact)).map((fact) => [fact.slot_id, fact]));
  const basisVersions = new Map((isPlainObject(brief) && Array.isArray(brief.basis)
    ? brief.basis : []).filter((entry) => isPlainObject(entry)).map((entry) => [entry.slot_id, entry.version]));
  const fact = confirmed.get(source.document_id);
  if (!fact) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.source",
      "这条文案的来源事实没有确认值，无法核对测量绑定。");
    return problems;
  }
  if (basisVersions.get(source.document_id) !== source.version) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.source.version",
      "这条文案的来源已改变；请核对后重新确认，不会悄悄替换文案。");
    return problems;
  }
  const measurements = Array.isArray(fact.value) ? fact.value : null;
  if (!measurements) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.source",
      "这条文案绑定了测量，但来源事实不是结构化尺寸列表；请移除绑定或改绑尺寸事实。");
    return problems;
  }
  const text = isNonEmptyString(item.text) ? item.text.trim() : "";
  if (hasSingle) {
    checkSingleMeasurementProblems(problems, item.measurement, measurements, text);
  } else {
    checkGroupedMeasurementProblems(problems, item.measurement_source, measurements, text);
  }
  return problems;
}

/**
 * 单条测量绑定的精确性复核：索引命中→快照四元逐字节相等→原文逐字等于规范文本。
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {unknown} binding
 * @param {unknown[]} measurements 来源槽位当前确认值的测量列表
 * @param {string} text 条目原文（已 trim）
 * @returns {void}
 */
function checkSingleMeasurementProblems(problems, binding, measurements, text) {
  if (!isPlainObject(binding)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.measurement",
      "测量绑定必须是对象。");
    return;
  }
  const index = binding.index;
  if (!Number.isInteger(index) || index < 0 || index >= measurements.length) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.measurement.index",
      "测量索引已过期（来源列表已编辑/重排）；请重新选择测量项并确认。");
    return;
  }
  const current = measurements[index];
  if (!isPlainObject(current)
    || current.object !== binding.object || current.axis !== binding.axis
    || current.value !== binding.value || current.unit !== binding.unit
    || current.source_basis !== binding.source_basis) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.measurement",
      "测量快照与来源当前值不一致（对象/轴向/数值/单位/来源依据须逐项相等）；请重新确认。");
    return;
  }
  if (!isNonEmptyString(binding.axis_label)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.measurement.axis_label",
      "轴向英文标签不能为空（须人工确认映射）。");
    return;
  }
  if (!MEASUREMENT_SOURCE_KINDS.includes(binding.source_kind)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.measurement.source_kind",
      "来源分类只能是 nominal／measured（须人工对照来源依据确认）。");
    return;
  }
  const canonical = formatMeasurementText(binding);
  if (canonical === null || text !== canonical) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.text",
      "文案原文与测量绑定不一致：应逐字为「" + String(canonical || "（绑定非法）") + "」。");
  }
}

/**
 * 分组来源标签的精确性复核：索引一一命中→快照逐字节相等→原文逐字等于统一来源标签。
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {unknown} binding
 * @param {unknown[]} measurements 来源槽位当前确认值的测量列表
 * @param {string} text 条目原文（已 trim）
 * @returns {void}
 */
function checkGroupedMeasurementProblems(problems, binding, measurements, text) {
  if (!isPlainObject(binding)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.measurement_source",
      "分组来源标签必须是对象。");
    return;
  }
  const indices = binding.indices;
  const snapshot = binding.measurements;
  if (!Array.isArray(indices) || indices.length === 0
    || !indices.every((entry) => Number.isInteger(entry) && entry >= 0)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.measurement_source.indices",
      "分组索引必须是非空非负整数列表。");
    return;
  }
  if (!Array.isArray(snapshot) || snapshot.length !== indices.length) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.measurement_source.measurements",
      "分组测量快照必须与索引一一对应。");
    return;
  }
  if (!MEASUREMENT_SOURCE_KINDS.includes(binding.source_kind)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.measurement_source.source_kind",
      "来源分类只能是 nominal／measured（须人工对照来源依据确认）。");
    return;
  }
  for (let position = 0; position < indices.length; position += 1) {
    const index = indices[position];
    const frozen = snapshot[position];
    const current = index < measurements.length ? measurements[index] : null;
    if (!isPlainObject(frozen) || !isPlainObject(current)
      || current.object !== frozen.object || current.axis !== frozen.axis
      || current.value !== frozen.value || current.unit !== frozen.unit
      || current.source_basis !== frozen.source_basis) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID,
        "$.measurement_source.measurements[" + position + "]",
        "分组测量快照与来源当前值不一致；请重新确认分组。");
      return;
    }
  }
  const canonical = MEASUREMENT_SOURCE_LABEL[binding.source_kind];
  if (text !== canonical) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.text",
      "分组来源标签原文应逐字为「" + canonical + "」。");
  }
}

/**
 * 参考图视角证据（设计 §13.4.2/13.13.3）：只有「来源 reference_observation、已确认、
 * 证据指向当前启用参考图的完整 SHA、值只含 front|side|top」的 FactSlot 才能证明视角。
 * 只读、无 AI、不按文件名/角色猜测。调用方用第二个参数分别过滤「项目证据」与「本次冻结引用」。
 * @param {ReadonlyArray<{slot: import("./type-contracts.js").FactSlot, version: number}> | null | undefined} slotEntries
 * @param {readonly string[] | null | undefined} activeReferenceShas 本次实际消费的 product_truth SHA 集合
 * @returns {{viewpoints: string[], slots: {slot_id: string, version: number}[]}}
 */
export function referenceViewpointEvidence(slotEntries, activeReferenceShas) {
  const active = new Set(Array.isArray(activeReferenceShas) ? activeReferenceShas : []);
  /** @type {Set<string>} */
  const viewpoints = new Set();
  /** @type {{slot_id: string, version: number}[]} */
  const slots = [];
  for (const entry of Array.isArray(slotEntries) ? slotEntries : []) {
    if (!isPlainObject(entry) || !isPlainObject(entry.slot)) continue;
    const slot = entry.slot;
    if (slot.source !== "reference_observation" || slot.status !== "confirmed") continue;
    if (slot.value_type !== "enum" && slot.value_type !== "text_list") continue;
    const evidence = Array.isArray(slot.evidence) ? slot.evidence : [];
    const bound = evidence.some((item) => isPlainObject(item) && item.kind === "asset"
      && typeof item.ref === "string" && active.has(item.ref));
    if (!bound) continue;
    const values = Array.isArray(slot.value) ? slot.value : [slot.value];
    const found = values.filter((value) => REFERENCE_VIEWPOINTS.includes(value));
    if (!found.length) continue;
    for (const value of found) viewpoints.add(value);
    slots.push({ slot_id: slot.slot_id, version: entry.version });
  }
  return { viewpoints: [...viewpoints], slots };
}

/**
 * keep / change_allowed 的规范化比较形态；非数组一律视为空列表。
 * @param {unknown} value
 * @returns {string[]}
 */
function normalizedShotItems(value) {
  return Array.isArray(value)
    ? value.filter((item) => isNonEmptyString(item)).map((item) => item.trim())
    : [];
}

/**
 * 单图规格的前后差异（目的 + keep/change_allowed）；无差异返回空数组。
 * @param {Record<string, unknown> | null | undefined} previous
 * @param {Record<string, unknown> | null | undefined} next
 * @returns {import("./type-contracts.js").SpecDiffItem[]}
 */
export function shotSpecDiff(previous, next) {
  const diffs = [];
  const prevPurpose = previous && isNonEmptyString(previous.purpose) ? previous.purpose.trim() : "";
  const nextPurpose = next && isNonEmptyString(next.purpose) ? next.purpose.trim() : "";
  if (prevPurpose !== nextPurpose) {
    diffs.push({ field: "purpose", label: "目的", before: prevPurpose, after: nextPurpose });
  }
  for (const [key, label] of [["keep", "必须保持"], ["change_allowed", "允许变化"]]) {
    const before = normalizedShotItems(previous ? previous[key] : null);
    const after = normalizedShotItems(next ? next[key] : null);
    if (JSON.stringify(before) !== JSON.stringify(after)) {
      diffs.push({ field: key, label, before, after });
    }
  }
  const prevIntent = previous && isNonEmptyString(previous.print_intent) ? previous.print_intent : "";
  const nextIntent = next && isNonEmptyString(next.print_intent) ? next.print_intent : "";
  if (prevIntent !== nextIntent) {
    diffs.push({ field: "print_intent", label: "图中文字", before: prevIntent, after: nextIntent });
  }
  const prevLayout = previous && isNonEmptyString(previous.layout) ? previous.layout : "";
  const nextLayout = next && isNonEmptyString(next.layout) ? next.layout : "";
  if (prevLayout !== nextLayout) {
    diffs.push({ field: "layout", label: "版面", before: prevLayout, after: nextLayout });
  }
  const prevTexts = onImageTextLines(previous);
  const nextTexts = onImageTextLines(next);
  if (JSON.stringify(prevTexts) !== JSON.stringify(nextTexts)) {
    diffs.push({ field: "on_image_texts", label: "所选图中文字", before: prevTexts, after: nextTexts });
  }
  for (const field of PRESENTATION_FIELDS) {
    const before = presentationLabel(field, presentationStateOf(previous, field.key));
    const after = presentationLabel(field, presentationStateOf(next, field.key));
    if (before !== after) {
      diffs.push({ field: field.key, label: field.label, before, after });
    }
  }
  const prevRefs = Array.isArray(previous?.reference_sha256s) ? previous.reference_sha256s : null;
  const nextRefs = Array.isArray(next?.reference_sha256s) ? next.reference_sha256s : null;
  if (JSON.stringify(prevRefs) !== JSON.stringify(nextRefs)) {
    diffs.push({ field: "reference_sha256s", label: "本图参考选择",
      before: prevRefs === null ? ["按本图角色依据"] : prevRefs.map((sha) => String(sha).slice(0, 12)),
      after: nextRefs === null ? ["按本图角色依据"] : nextRefs.map((sha) => String(sha).slice(0, 12)) });
  }
  return diffs;
}

/**
 * 所选图中文字的人读比较形态；未确认项带状态后缀，便于界面说清「还要确认什么」。
 * @param {Record<string, unknown> | null | undefined} spec
 * @returns {string[]}
 */
function onImageTextLines(spec) {
  const list = spec && Array.isArray(spec.on_image_texts) ? spec.on_image_texts : [];
  return list.filter((item) => isPlainObject(item) && isNonEmptyString(item.text))
    .map((item) => item.text + (item.status === "confirmed" ? "" : "（待确认）"));
}

/* -------------------------------------------------------- 失效投影与版本 */

/**
 * @param {readonly string[]} keys
 * @returns {string[]}
 */
function labelList(keys) {
  return keys.map((key) => ARTIFACT_LABELS[key] || key);
}

/**
 * 失效投影（人读版）：一次变化影响什么、失效什么、保留什么。
 * @param {import("./type-contracts.js").ChangeKind} changeKind
 * @param {import("./type-contracts.js").InvalidationContext & {shotCount?: number, shotLabel?: string}} [context]
 * @returns {{change_kind: string, scope: string, target_shot_id: string | null, affects: "suite" | "shot", affects_text: string, invalidates: string[], preserves: string[], invalidates_text: string, preserves_text: string}}
 */
export function specChangeProjection(changeKind, context = {}) {
  const result = invalidationsFor(changeKind, context);
  const shotCount = Number.isInteger(context.shotCount) ? context.shotCount : null;
  const shotLabel = isNonEmptyString(context.shotLabel) ? context.shotLabel.trim() : null;
  const affectsSuite = result.scope === "project";
  const affectsText = affectsSuite
    ? (shotCount === null ? "全部图片" : "全部 " + shotCount + " 张图")
    : (shotLabel ? "只有「" + shotLabel + "」这一张" : "只有目标这一张");
  return {
    change_kind: changeKind,
    scope: result.scope,
    target_shot_id: result.target_shot_id || null,
    affects: affectsSuite ? "suite" : "shot",
    affects_text: affectsText,
    invalidates: [...result.invalidates],
    preserves: [...result.preserves],
    invalidates_text: labelList(result.invalidates).join("、"),
    preserves_text: labelList(result.preserves).join("、"),
  };
}

/**
 * 取 versions 里 version < currentVersion 的最大者；要求 currentVersion 是正整数。
 * @param {unknown} versions
 * @param {number} currentVersion
 * @returns {{version: number} & Record<string, unknown> | null}
 */
export function previousVersionOf(versions, currentVersion) {
  if (!Number.isInteger(currentVersion) || currentVersion < 1) {
    invalid("当前版本必须是正整数。");
  }
  const list = (Array.isArray(versions) ? versions : [])
    .filter((item) => isPlainObject(item) && Number.isInteger(item.version))
    .filter((item) => item.version < currentVersion)
    .sort((left, right) => right.version - left.version);
  return list.length ? list[0] : null;
}

/* -------------------------------------------------------- 审核清单与聚合 */

/**
 * 单图的审核清单投影：目的/必须保持/允许变化/公共风格四段。
 * @param {unknown} shot
 * @param {{shotSpec?: import("./type-contracts.js").ShotSpec | null, styleSpec?: import("./type-contracts.js").StyleSpec | null}} [options]
 * @returns {{shot_id: string | null, label: string, role_id: string | null, required: boolean, custom: boolean, saved: boolean, purpose: string, must_keep: string[], may_change: string[], style_configured: boolean, style_lines: string[], sections: {key: string, label: string, items: string[]}[]}}
 */
export function reviewChecklist(shot, options = {}) {
  if (!isPlainObject(shot)) invalid("审核清单需要一张 Shot。");
  const savedSpec = isPlainObject(options.shotSpec) ? options.shotSpec : null;
  const spec = savedSpec || emptyShotSpecFromShot(shot);
  const style = options.styleSpec || emptyStyleSpec();
  const styleItems = styleSpecSummary(style).map((item) => item.text);
  // #9：程序表达的决定必须出现在人读清单里（用户复核的就是这些决定），而不仅存在于编译内部。
  const printIntent = effectivePrintIntentOf(spec, shot);
  const decision = [
    { key: "presentation_appearance", label: "外观状态", items: [] },
    { key: "presentation_contents", label: "内容物", items: [] },
    { key: "presentation_viewpoint", label: "视角", items: [] },
  ];
  const decisionKeyOf = (fieldKey) => fieldKey === "appearance_state" ? "presentation_appearance"
    : fieldKey === "contents_state" ? "presentation_contents" : "presentation_viewpoint";
  const sections = [
    { key: "purpose", label: "这张图的目的", items: [spec.purpose] },
    { key: "keep", label: "必须保持", items: [...spec.keep] },
    { key: "change", label: "允许变化", items: [...spec.change_allowed] },
    { key: "style", label: "公共风格", items: styleItems },
  ];
  if (PRINT_DECISION_ROLES.includes(shot.role_id)) {
    sections.push({ key: "print", label: "图中文字",
      items: [printIntent === "undecided" ? "还没决定（未决定时这张图不会发送）"
        : printIntentLabelOf(printIntent)] });
    if (printIntent === "selected") {
      // 记录可能来自导入/手改而没有 on_image_texts：清单只报事实，不在这里抛错（编译门会给可操作消息）。
      const texts = Array.isArray(spec.on_image_texts) ? spec.on_image_texts.filter((item) => isPlainObject(item)) : [];
      sections.push({ key: "on_image_texts", label: "所选文案",
        items: texts.length > 0
          ? texts.map((item) => item.text + (item.status === "confirmed" ? "" : "（待确认）"))
          : ["（还没有所选文案：去规格区勾选已确认文案）"] });
    }
    if (isNonEmptyString(spec.layout)) {
      sections.push({ key: "layout", label: "版面", items: [layoutLabelOf(spec.layout)] });
    }
  }
  for (const field of PRESENTATION_FIELDS) {
    if (!PRESENTATION_CONSUMERS[field.key].includes(shot.role_id)) continue;
    const state = presentationStateOf(spec, field.key);
    const target = decision.find((item) => item.key === decisionKeyOf(field.key));
    if (field.key === "viewpoint") {
      // 视角默认即沿用有依据的视角：清单只在显式选择非默认视角时列出该决定。
      if (state !== "reference_visible") target.items.push(presentationLabel(field, state));
      continue;
    }
    target.items.push(state === "undecided"
      ? "还没决定（未决定时这张图不会发送）" : presentationLabel(field, state));
  }
  for (const item of decision) {
    if (item.items.length > 0) sections.push(item);
  }
  return {
    shot_id: typeof shot.shot_id === "string" ? shot.shot_id : null,
    label: isNonEmptyString(shot.label) ? shot.label : "",
    role_id: typeof shot.role_id === "string" ? shot.role_id : null,
    required: shot.required === true,
    custom: shot.custom === true,
    saved: Boolean(savedSpec),
    purpose: spec.purpose,
    must_keep: [...spec.keep],
    may_change: [...spec.change_allowed],
    style_configured: styleItems.length > 0,
    style_lines: styleItems,
    sections: sections,
  };
}

/**
 * 整套图的规格聚合：每张图的保存状态、版本与完整审核清单。
 * @param {unknown} plan
 * @param {{shotSpecsById?: Record<string, {spec?: import("./type-contracts.js").ShotSpec | null, version: number} | null | undefined>, styleSpec?: import("./type-contracts.js").StyleSpec | null}} [options]
 * @returns {{total: number, saved: number, defaults: number, style_configured: boolean, shots: {shot_id: string | null, label: string, saved: boolean, version: number, checklist: {shot_id: string | null, label: string, role_id: string | null, required: boolean, custom: boolean, saved: boolean, purpose: string, must_keep: string[], may_change: string[], style_configured: boolean, style_lines: string[], sections: {key: string, label: string, items: string[]}[]}}[]}}
 */
export function suiteSpecDigest(plan, options = {}) {
  const shots = (isPlainObject(plan) && Array.isArray(plan.shots) ? plan.shots : [])
    .map((shot) => {
      const entry = options.shotSpecsById && shot && options.shotSpecsById[shot.shot_id]
        ? options.shotSpecsById[shot.shot_id]
        : null;
      return {
        shot_id: shot.shot_id,
        label: shot.label,
        saved: Boolean(entry && entry.spec),
        version: entry && Number.isInteger(entry.version) ? entry.version : 0,
        checklist: reviewChecklist(shot, {
          shotSpec: entry ? entry.spec : null,
          styleSpec: options.styleSpec || null,
        }),
      };
    });
  return {
    total: shots.length,
    saved: shots.filter((item) => item.saved).length,
    defaults: shots.filter((item) => !item.saved).length,
    style_configured: !styleSpecIsEmpty(options.styleSpec || null),
    shots,
  };
}

/**
 * 校验公共风格并原样返回；失败抛 CONTRACT_INVALID（绝不写半成品进版本历史）。
 * @param {import("./type-contracts.js").StyleSpec} spec
 * @returns {import("./type-contracts.js").StyleSpec}
 */
export function assertStyleSpec(spec) {
  const problems = checkStyleSpec(spec);
  if (problems.length > 0) invalid("风格规格不合法：" + problems[0].message,
    { problems: problems.slice(0, 3) });
  return spec;
}

/**
 * 校验单图规格并原样返回；失败抛 CONTRACT_INVALID。
 * @param {import("./type-contracts.js").ShotSpec} spec
 * @returns {import("./type-contracts.js").ShotSpec}
 */
export function assertShotSpec(spec) {
  const problems = checkShotSpec(spec);
  if (problems.length > 0) invalid("单图规格不合法：" + problems[0].message,
    { problems: problems.slice(0, 3) });
  return spec;
}
