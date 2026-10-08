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
import { isNonEmptyString, isPlainObject, pushProblem } from "./shared.js";

export const STYLE_SPEC_SCHEMA_VERSION = 1;
export const SHOT_SPEC_SCHEMA_VERSION = 1;
export const STYLE_SPEC_DOCUMENT_ID = "style";
export const MAX_STYLE_TEXT = 200;
export const MAX_STYLE_AVOID = 10;
export const MAX_SHOT_PURPOSE = 200;
export const MAX_SHOT_ITEMS = 8;
export const MAX_SHOT_ITEM_LENGTH = 60;

export const STYLE_SPEC_FIELDS = Object.freeze([
  Object.freeze({ key: "background", label: "背景风格", kind: "text" }),
  Object.freeze({ key: "lighting", label: "光线", kind: "text" }),
  Object.freeze({ key: "color_tone", label: "色调", kind: "text" }),
  Object.freeze({ key: "composition", label: "构图约定", kind: "text" }),
  Object.freeze({ key: "avoid", label: "避免出现", kind: "list" }),
]);

const STYLE_KEYS = Object.freeze(["schema_version", ...STYLE_SPEC_FIELDS.map((item) => item.key)]);
const SHOT_KEYS = Object.freeze(["schema_version", "purpose", "keep", "change_allowed", "notes"]);

/** 失效目标的人读名字；投影文本与界面提示共用这一份。 */
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

export function checkStyleSpec(spec) {
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
  return problems;
}

export function styleSpecIsEmpty(spec) {
  if (!isPlainObject(spec)) return true;
  return styleSpecSummary(spec).length === 0;
}

export function styleSpecSummary(spec) {
  if (!isPlainObject(spec)) return [];
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
  return items;
}

function normalizedStyleValue(field, spec) {
  const value = spec ? spec[field.key] : undefined;
  if (field.kind === "text") return isNonEmptyString(value) ? value.trim() : "";
  return Array.isArray(value)
    ? value.filter((item) => isNonEmptyString(item)).map((item) => item.trim())
    : [];
}

export function styleSpecDiff(previous, next) {
  const diffs = [];
  for (const field of STYLE_SPEC_FIELDS) {
    const before = normalizedStyleValue(field, previous);
    const after = normalizedStyleValue(field, next);
    if (JSON.stringify(before) !== JSON.stringify(after)) {
      diffs.push({ field: field.key, label: field.label, before, after });
    }
  }
  return diffs;
}

/* ------------------------------------------------------------------ 单图规格 */

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

export function emptyShotSpecFromShot(shot) {
  const roleId = isPlainObject(shot) && typeof shot.role_id === "string" ? shot.role_id : "custom";
  const purpose = isPlainObject(shot) && isNonEmptyString(shot.intent)
    ? shot.intent.trim()
    : (isPlainObject(shot) && isNonEmptyString(shot.label) ? shot.label.trim() : "这张图要达成什么");
  return {
    schema_version: SHOT_SPEC_SCHEMA_VERSION,
    purpose,
    keep: [...(DEFAULT_KEEP_BY_ROLE[roleId] || DEFAULT_KEEP_BY_ROLE.custom)],
    change_allowed: [...(DEFAULT_ALLOW_BY_ROLE[roleId] || DEFAULT_ALLOW_BY_ROLE.custom)],
    notes: "",
  };
}

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

export function checkShotSpec(spec) {
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
  return problems;
}

function normalizedShotItems(value) {
  return Array.isArray(value)
    ? value.filter((item) => isNonEmptyString(item)).map((item) => item.trim())
    : [];
}

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
  return diffs;
}

/* -------------------------------------------------------- 失效投影与版本 */

function labelList(keys) {
  return keys.map((key) => ARTIFACT_LABELS[key] || key);
}

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

export function reviewChecklist(shot, options = {}) {
  if (!isPlainObject(shot)) invalid("审核清单需要一张 Shot。");
  const savedSpec = isPlainObject(options.shotSpec) ? options.shotSpec : null;
  const spec = savedSpec || emptyShotSpecFromShot(shot);
  const style = options.styleSpec || emptyStyleSpec();
  const styleItems = styleSpecSummary(style).map((item) => item.text);
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
    sections: [
      { key: "purpose", label: "这张图的目的", items: [spec.purpose] },
      { key: "keep", label: "必须保持", items: [...spec.keep] },
      { key: "change", label: "允许变化", items: [...spec.change_allowed] },
      { key: "style", label: "公共风格", items: styleItems },
    ],
  };
}

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

export function assertStyleSpec(spec) {
  const problems = checkStyleSpec(spec);
  if (problems.length > 0) invalid("风格规格不合法：" + problems[0].message,
    { problems: problems.slice(0, 3) });
  return spec;
}

export function assertShotSpec(spec) {
  const problems = checkShotSpec(spec);
  if (problems.length > 0) invalid("单图规格不合法：" + problems[0].message,
    { problems: problems.slice(0, 3) });
  return spec;
}
