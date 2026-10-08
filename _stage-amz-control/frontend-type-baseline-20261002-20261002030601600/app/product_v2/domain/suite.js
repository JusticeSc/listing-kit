/**
 * Product V2 套图计划领域（V2.3.2，计划 §9.5）。
 *
 * 唯一权威：计划文档的形状、操作与不变量都在本文件；依赖规则不在本文件复制，
 * 而是复用 V2.3.1 注册表（checkShotDraft / evaluateShot / templateDefinition）。
 *
 * 三条不可协商的规则：
 *  1) shots 数组的顺序就是持久化顺序，不额外存 order 字段造成两份真相；
 *  2) 至少保留 1 张图、至少保留 1 张必需图；自定义图必须是可选图；
 *  3) 所有操作返回新计划；失败抛 CONTRACT_INVALID —— 调用方不会写出半成品。
 */

import { DOMAIN_ERROR_CODES, invalid } from "./errors.js";
import { SLOT_ID_PATTERN, isPlainObject, pushProblem } from "./shared.js";
import {
  checkShotDraft,
  createCustomShot,
  evaluateShot,
  recommendPlan,
  roleDefinition,
  templateDefinition,
} from "./suite-plan.js";

export const SUITE_PLAN_SCHEMA_VERSION = 1;
export const SUITE_PLAN_DOCUMENT_ID = "suite";
export const MIN_SHOTS = 1;
export const MAX_SHOTS = 20;

export function emptySuitePlan() {
  return { schema_version: SUITE_PLAN_SCHEMA_VERSION, shots: [] };
}

function checkPlanShape(plan) {
  if (!isPlainObject(plan) || !Array.isArray(plan.shots)) {
    invalid("套图计划必须是 { shots: [...] }。");
  }
  if (plan.schema_version !== SUITE_PLAN_SCHEMA_VERSION) {
    invalid("套图计划版本不认识：" + String(plan.schema_version));
  }
}

function withShots(plan, shots) {
  return { schema_version: SUITE_PLAN_SCHEMA_VERSION, shots };
}

export function shotById(plan, shotId) {
  if (!isPlainObject(plan) || !Array.isArray(plan.shots)) return null;
  return plan.shots.find((shot) => isPlainObject(shot) && shot.shot_id === shotId) || null;
}

/** id 派生：shot_<template_id>，冲突时加 _2、_3……；不引入随机数，刷新后才可复现。 */
export function nextShotId(plan, base) {
  const taken = new Set((plan && plan.shots ? plan.shots : [])
    .filter((shot) => isPlainObject(shot))
    .map((shot) => shot.shot_id));
  if (!taken.has(base)) return base;
  let index = 2;
  while (taken.has(base + "_" + index)) index += 1;
  return base + "_" + index;
}

function shotFromTemplate(templateId, plan, options = {}) {
  const registry = options.registry;
  const template = templateDefinition(templateId, registry);
  if (!template) invalid("模板不存在：" + String(templateId));
  const role = roleDefinition(template.role_id, registry);
  if (!role || role.custom === true) invalid("自定义图不来自模板。");
  return {
    shot_id: options.shotId || nextShotId(plan, "shot_" + template.template_id),
    template_id: template.template_id,
    role_id: template.role_id,
    label: template.label,
    intent: template.intent,
    required: template.required === true,
    custom: false,
    dependencies: template.dependencies,
    fact_slot_ids: [...(options.factSlotIds || [])],
  };
}

function assertValid(plan, registry) {
  const problems = validateSuitePlan(plan, registry);
  if (problems.length > 0) {
    invalid("套图计划不合法：" + problems[0].message, { problems: problems.slice(0, 3) });
  }
}

/* ------------------------------------------------------------------ 操作 */

/**
 * 模板依赖里由「已确认核心事实」满足的部分，在种子/手动添加时自动绑定为该图的文案来源。
 * 规则仍然只有 §9.4 的依赖注册表一份；这里只是把它反解成默认绑定，不新增判断。
 */
function impliedFactBindings(templateId, context, registry) {
  const template = templateDefinition(templateId, registry);
  const confirmed = new Set((context && Array.isArray(context.facts) ? context.facts : [])
    .filter((item) => isPlainObject(item) && item.status === "confirmed")
    .map((item) => item.slot_id));
  const out = new Set();
  const collect = (requirement) => {
    if (!isPlainObject(requirement)) return;
    if (requirement.kind === "fact" && confirmed.has(requirement.slot_id)) {
      out.add(requirement.slot_id);
    }
    if (requirement.kind === "fact_any") {
      for (const slotId of Array.isArray(requirement.slot_ids) ? requirement.slot_ids : []) {
        if (confirmed.has(slotId)) out.add(slotId);
      }
    }
    if (requirement.kind === "any_of") {
      for (const sub of Array.isArray(requirement.of) ? requirement.of : []) collect(sub);
    }
  };
  for (const requirement of (template && template.dependencies) || []) collect(requirement);
  return [...out];
}

export function seedSuitePlan(context, options = {}) {
  const recommendation = recommendPlan(context, options);
  const shots = [];
  const included = [];
  const skipped = [];
  for (const instance of recommendation.instances) {
    if (instance.required || instance.satisfied) {
      const explicit = options.bound_fact_ids_by_template
        && Array.isArray(options.bound_fact_ids_by_template[instance.template_id])
        ? options.bound_fact_ids_by_template[instance.template_id] : null;
      const bound = explicit || impliedFactBindings(instance.template_id, context, options.registry);
      const shot = shotFromTemplate(instance.template_id, { shots },
        { ...options, factSlotIds: bound });
      shots.push(shot);
      included.push(shot.shot_id);
    } else {
      skipped.push({ template_id: instance.template_id, blocking: instance.blocking });
    }
  }
  const plan = withShots({ schema_version: SUITE_PLAN_SCHEMA_VERSION }, shots);
  assertValid(plan, options.registry);
  return { plan, included, skipped };
}

export function addShotFromTemplate(plan, templateId, options = {}) {
  checkPlanShape(plan);
  if (plan.shots.length >= MAX_SHOTS) invalid("套图最多 " + MAX_SHOTS + " 张。");
  const ctx = options.context || {};
  const shot = shotFromTemplate(templateId,
    plan, { ...options, factSlotIds: impliedFactBindings(templateId, ctx, options.registry) });
  const next = withShots(plan, [...plan.shots, shot]);
  assertValid(next, options.registry);
  return { plan: next, shot };
}

export function addCustomShotToPlan(plan, input = {}, options = {}) {
  checkPlanShape(plan);
  if (plan.shots.length >= MAX_SHOTS) invalid("套图最多 " + MAX_SHOTS + " 张。");
  const draft = createCustomShot(input);
  const shot = { ...draft, shot_id: nextShotId(plan, "shot_custom") };
  const next = withShots(plan, [...plan.shots, shot]);
  assertValid(next, options.registry);
  return { plan: next, shot };
}

export function copyShot(plan, shotId, options = {}) {
  checkPlanShape(plan);
  if (plan.shots.length >= MAX_SHOTS) invalid("套图最多 " + MAX_SHOTS + " 张。");
  const source = shotById(plan, shotId);
  if (!source) invalid("找不到要复制的图：" + String(shotId));
  const base = source.template_id ? "shot_" + source.template_id + "_copy" : "shot_custom_copy";
  const shot = {
    shot_id: nextShotId(plan, base),
    template_id: source.template_id === undefined ? null : source.template_id,
    role_id: source.role_id,
    label: source.label + "（副本）",
    intent: source.intent,
    required: false,
    custom: source.custom === true,
    dependencies: source.dependencies,
    fact_slot_ids: [...(source.fact_slot_ids || [])],
  };
  const next = withShots(plan, [...plan.shots, shot]);
  assertValid(next, options.registry);
  return { plan: next, shot };
}

export function removeShot(plan, shotId, options = {}) {
  checkPlanShape(plan);
  const index = plan.shots.findIndex((shot) => isPlainObject(shot) && shot.shot_id === shotId);
  if (index < 0) invalid("找不到要删除的图：" + String(shotId));
  if (plan.shots.length <= MIN_SHOTS) invalid("套图至少保留 " + MIN_SHOTS + " 张。");
  const shot = plan.shots[index];
  const requiredCount = plan.shots.filter((item) => isPlainObject(item) && item.required === true).length;
  if (shot.required === true && requiredCount <= 1) {
    invalid("这是最后一张必需图，不能删除；必需图至少保留 1 张。");
  }
  const remaining = plan.shots.filter((item, itemIndex) => itemIndex !== index);
  const next = withShots(plan, remaining);
  assertValid(next, options.registry);
  return { plan: next, removed: shot };
}

export function moveShot(plan, shotId, delta, options = {}) {
  checkPlanShape(plan);
  if (delta !== 1 && delta !== -1) invalid("只支持上移（-1）或下移（+1）。");
  const index = plan.shots.findIndex((shot) => isPlainObject(shot) && shot.shot_id === shotId);
  if (index < 0) invalid("找不到要移动的图：" + String(shotId));
  const target = index + delta;
  if (target < 0 || target >= plan.shots.length) return { plan, moved: false };
  const shots = [...plan.shots];
  [shots[index], shots[target]] = [shots[target], shots[index]];
  const next = withShots(plan, shots);
  assertValid(next, options.registry);
  return { plan: next, moved: true };
}

/* ------------------------------------------------------------ 校验与投影 */

export function validateSuitePlan(plan, registry) {
  const problems = [];
  if (!isPlainObject(plan)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "套图计划必须是对象。");
    return problems;
  }
  if (plan.schema_version !== SUITE_PLAN_SCHEMA_VERSION) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.schema_version",
      "套图计划版本必须是 " + SUITE_PLAN_SCHEMA_VERSION + "。");
  }
  if (!Array.isArray(plan.shots)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shots", "shots 必须是数组。");
    return problems;
  }
  if (plan.shots.length < MIN_SHOTS) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shots",
      "套图至少要有 " + MIN_SHOTS + " 张图。");
  }
  if (plan.shots.length > MAX_SHOTS) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shots",
      "套图最多 " + MAX_SHOTS + " 张图。");
  }
  const seenIds = new Set();
  plan.shots.forEach((shot, index) => {
    const path = "$.shots[" + index + "]";
    if (!isPlainObject(shot)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "Shot 必须是对象。");
      return;
    }
    for (const problem of checkShotDraft(shot, registry)) {
      problems.push({
        code: problem.code,
        path: path + String(problem.path || "$").slice(1),
        message: problem.message,
      });
    }
    if (typeof shot.shot_id !== "string" || !SLOT_ID_PATTERN.test(shot.shot_id)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".shot_id",
        "shot_id 必须是合法标识。");
    } else if (seenIds.has(shot.shot_id)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".shot_id",
        "shot_id 不允许重复。");
    } else {
      seenIds.add(shot.shot_id);
    }
    if (typeof shot.required !== "boolean") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".required",
        "required 必须是布尔值。");
    }
    if (shot.custom === true && shot.required === true) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".required",
        "自定义图必须是可选图。");
    }
    if (shot.custom !== true && typeof shot.template_id === "string") {
      const template = templateDefinition(shot.template_id, registry);
      if (template
          && JSON.stringify(shot.dependencies) !== JSON.stringify(template.dependencies)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".dependencies",
          "依赖必须与模板逐字一致。");
      }
    }
  });
  if (!plan.shots.some((shot) => isPlainObject(shot) && shot.required === true)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shots",
      "套图至少要有 1 张必需图。");
  }
  return problems;
}

export function suitePlanSummary(plan, context, registry) {
  const shots = (plan && Array.isArray(plan.shots) ? plan.shots : []).map((shot) => {
    const evaluation = evaluateShot(shot, context || {}, registry);
    const role = roleDefinition(shot.role_id, registry);
    return {
      shot_id: shot.shot_id,
      template_id: shot.template_id === undefined ? null : shot.template_id,
      label: shot.label,
      role_id: shot.role_id,
      role_label: role ? role.label : null,
      required: shot.required === true,
      custom: shot.custom === true,
      satisfied: evaluation.satisfied,
      blocking: evaluation.blocking,
    };
  });
  return {
    total: shots.length,
    satisfiable: shots.filter((item) => item.satisfied).length,
    blocked: shots.filter((item) => !item.satisfied).length,
    required_blocked: shots.filter((item) => item.required && !item.satisfied)
      .map((item) => item.shot_id),
    shots,
  };
}
