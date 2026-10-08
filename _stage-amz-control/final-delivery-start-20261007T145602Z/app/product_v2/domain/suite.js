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

/**
 * 运行时计划形状：shots 元素为 ShotRecord（模板依赖在运行时被冻结，见 suite-plan.js）。
 * @typedef {Omit<import("./suite-plan.js").ShotRecord, "shot_id">} PlanRecordShotBase
 * @typedef {PlanRecordShotBase & {shot_id: string}} TemplateShot
 * @typedef {{schema_version: number, shots: ReadonlyArray<TemplateShot>}} PlanRecord
 */

/** @type {number} */
export const SUITE_PLAN_SCHEMA_VERSION = 1;
/** @type {"suite"} */
export const SUITE_PLAN_DOCUMENT_ID = "suite";
/** @type {number} */
export const MIN_SHOTS = 1;
/** @type {number} */
export const MAX_SHOTS = 20;

/**
 * 尚未添加任何图的空计划。
 * @returns {PlanRecord}
 */
export function emptySuitePlan() {
  return { schema_version: SUITE_PLAN_SCHEMA_VERSION, shots: [] };
}

/**
 * @param {PlanRecord} plan
 * @returns {void}
 */
function checkPlanShape(plan) {
  if (!isPlainObject(plan) || !Array.isArray(plan.shots)) {
    invalid("套图计划必须是 { shots: [...] }。");
  }
  if (plan.schema_version !== SUITE_PLAN_SCHEMA_VERSION) {
    invalid("套图计划版本不认识：" + String(plan.schema_version));
  }
}

/**
 * 空计划容忍（V2.R6.2）：null/undefined 表示「还没建过套图计划」，按空计划处理。
 * 这样首次从模板添加一张图不会因为计划尚不存在而报「套图计划必须是 {shots:[...]}」；
 * 真正的畸形计划（非空但字段不对）仍然照旧报错，不静默吞掉。
 * @param {PlanRecord | null | undefined} plan
 * @returns {PlanRecord}
 */
export function normalizeSuitePlan(plan) {
  return (plan === null || plan === undefined) ? emptySuitePlan() : plan;
}

/**
 * @param {{schema_version?: number}} plan
 * @param {ReadonlyArray<TemplateShot>} shots
 * @returns {PlanRecord}
 */
function withShots(plan, shots) {
  return { schema_version: SUITE_PLAN_SCHEMA_VERSION, shots };
}

/**
 * 按 shot_id 找图；计划畸形或找不到返回 null。
 * @param {unknown} plan
 * @param {string} shotId
 * @returns {import("./suite-plan.js").ShotRecord | null}
 */
export function shotById(plan, shotId) {
  if (!isPlainObject(plan) || !Array.isArray(plan.shots)) return null;
  return plan.shots.find((shot) => isPlainObject(shot) && shot.shot_id === shotId) || null;
}

/** id 派生：shot_<template_id>，冲突时加 _2、_3……；不引入随机数，刷新后才可复现。 */
/**
 * @param {{shots?: ReadonlyArray<import("./suite-plan.js").ShotRecord>} | null | undefined} plan
 * @param {string} base
 * @returns {string}
 */
export function nextShotId(plan, base) {
  const taken = new Set((plan && plan.shots ? plan.shots : [])
    .filter((shot) => isPlainObject(shot))
    .map((shot) => shot.shot_id));
  if (!taken.has(base)) return base;
  let index = 2;
  while (taken.has(base + "_" + index)) index += 1;
  return base + "_" + index;
}

/**
 * @param {string} templateId
 * @param {{shots?: ReadonlyArray<import("./suite-plan.js").ShotRecord>}} plan
 * @param {{shotId?: string | null, registry?: import("./suite-plan.js").SuiteRegistryView | null, factSlotIds?: ReadonlyArray<string>} | undefined} [options]
 * @returns {TemplateShot}
 */
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

/**
 * @param {PlanRecord} plan
 * @param {import("./suite-plan.js").SuiteRegistryView | null | undefined} [registry]
 * @returns {void}
 */
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
 * @param {string} templateId
 * @param {import("./type-contracts.js").EvalContext | null | undefined} context
 * @param {import("./suite-plan.js").SuiteRegistryView | null | undefined} registry
 * @returns {string[]}
 */
function impliedFactBindings(templateId, context, registry) {
  const template = templateDefinition(templateId, registry);
  const confirmed = new Set((context && Array.isArray(context.facts) ? context.facts : [])
    .filter((item) => isPlainObject(item) && item.status === "confirmed")
    .map((item) => item.slot_id));
  /** @type {Set<string>} */
  const out = new Set();
  /** @param {import("./suite-plan.js").FrozenShotDependency} requirement */
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

/**
 * 由推荐模板种子建计划：必需图或已满足的模板自动纳入，其余跳过并给出原因。
 * @param {import("./type-contracts.js").EvalContext | null | undefined} context
 * @param {{registry?: import("./suite-plan.js").SuiteRegistryView | null, bound_fact_ids_by_template?: Record<string, string[]> | null, shotId?: string | null} | undefined} [options]
 * @returns {{plan: PlanRecord, included: string[], skipped: {template_id: string, blocking: import("./type-contracts.js").DependencyBlocking[]}[]}}
 */
export function seedSuitePlan(context, options = {}) {
  const recommendation = recommendPlan(context, options);
  /** @type {import("./suite-plan.js").ShotRecord[]} */
  const shots = [];
  /** @type {string[]} */
  const included = [];
  /** @type {{template_id: string, blocking: import("./type-contracts.js").DependencyBlocking[]}[]} */
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

/**
 * 从模板添加一张图（自动把模板里已满足的已确认事实绑定为文案来源）；返回新计划与这张图。
 * @param {PlanRecord | null | undefined} plan
 * @param {string} templateId
 * @param {{context?: import("./type-contracts.js").EvalContext | null, registry?: import("./suite-plan.js").SuiteRegistryView | null, shotId?: string | null, factSlotIds?: ReadonlyArray<string>} | undefined} [options]
 * @returns {{plan: PlanRecord, shot: import("./suite-plan.js").ShotRecord}}
 */
export function addShotFromTemplate(plan, templateId, options = {}) {
  plan = normalizeSuitePlan(plan);
  checkPlanShape(plan);
  if (plan.shots.length >= MAX_SHOTS) invalid("套图最多 " + MAX_SHOTS + " 张。");
  const ctx = options.context || {};
  const shot = shotFromTemplate(templateId,
    plan, { ...options, factSlotIds: impliedFactBindings(templateId, ctx, options.registry) });
  const next = withShots(plan, [...plan.shots, shot]);
  assertValid(next, options.registry);
  return { plan: next, shot };
}

/**
 * 编辑某张图绑定的文案来源（V2.R6.2）：人可以为某个用途单独挑选它消费的已确认事实，
 * 不必把无关事实塞进这张图的依据。只校验形状与去重；是否已确认由各用途就绪投影按图判定。
 * @param {PlanRecord | null | undefined} plan
 * @param {string} shotId
 * @param {ReadonlyArray<string>} slotIds
 * @param {{registry?: import("./suite-plan.js").SuiteRegistryView | null} | undefined} [options]
 * @returns {{plan: PlanRecord, shot: import("./suite-plan.js").ShotRecord}}
 */
export function setShotFactBindings(plan, shotId, slotIds, options = {}) {
  plan = normalizeSuitePlan(plan);
  checkPlanShape(plan);
  if (!Array.isArray(slotIds)) invalid("绑定的事实必须是 slot_id 数组。");
  const seen = new Set();
  for (const slotId of slotIds) {
    if (typeof slotId !== "string" || !SLOT_ID_PATTERN.test(slotId)) {
      invalid("绑定的事实必须是合法 slot_id：" + String(slotId));
    }
    if (seen.has(slotId)) invalid("绑定的事实不允许重复：" + slotId);
    seen.add(slotId);
  }
  const index = plan.shots.findIndex((shot) => isPlainObject(shot) && shot.shot_id === shotId);
  if (index < 0) invalid("找不到要改绑定的图：" + String(shotId));
  const shot = { ...plan.shots[index], fact_slot_ids: [...slotIds] };
  const next = withShots(plan, plan.shots.map((item, itemIndex) => (itemIndex === index ? shot : item)));
  assertValid(next, options.registry);
  return { plan: next, shot };
}

/**
 * 添加自定义图（可选图；名称必填）；返回新计划与这张图。
 * @param {PlanRecord | null | undefined} plan
 * @param {{label?: string, intent?: string, factSlotIds?: ReadonlyArray<string>} | undefined} [input]
 * @param {{registry?: import("./suite-plan.js").SuiteRegistryView | null} | undefined} [options]
 * @returns {{plan: PlanRecord, shot: import("./suite-plan.js").ShotRecord}}
 */
export function addCustomShotToPlan(plan, input = {}, options = {}) {
  plan = normalizeSuitePlan(plan);
  checkPlanShape(plan);
  if (plan.shots.length >= MAX_SHOTS) invalid("套图最多 " + MAX_SHOTS + " 张。");
  const draft = createCustomShot(input);
  const shot = { ...draft, shot_id: nextShotId(plan, "shot_custom") };
  const next = withShots(plan, [...plan.shots, shot]);
  assertValid(next, options.registry);
  return { plan: next, shot };
}

/**
 * 复制一张图（副本必为可选图；label 加「（副本）」）；返回新计划与这张图。
 * @param {PlanRecord | null | undefined} plan
 * @param {string} shotId
 * @param {{registry?: import("./suite-plan.js").SuiteRegistryView | null} | undefined} [options]
 * @returns {{plan: PlanRecord, shot: import("./suite-plan.js").ShotRecord}}
 */
export function copyShot(plan, shotId, options = {}) {
  plan = normalizeSuitePlan(plan);
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

/**
 * 删除一张图（保底：至少保留 1 张图、最后一张必需图不可删）；返回新计划与被删的图。
 * @param {PlanRecord | null | undefined} plan
 * @param {string} shotId
 * @param {{registry?: import("./suite-plan.js").SuiteRegistryView | null} | undefined} [options]
 * @returns {{plan: PlanRecord, removed: import("./suite-plan.js").ShotRecord}}
 */
export function removeShot(plan, shotId, options = {}) {
  plan = normalizeSuitePlan(plan);
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

/**
 * 上移（-1）/下移（+1）；越界时不动。返回新计划与是否移动。
 * @param {PlanRecord | null | undefined} plan
 * @param {string} shotId
 * @param {number} delta
 * @param {{registry?: import("./suite-plan.js").SuiteRegistryView | null} | undefined} [options]
 * @returns {{plan: PlanRecord, moved: boolean}}
 */
export function moveShot(plan, shotId, delta, options = {}) {
  plan = normalizeSuitePlan(plan);
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

/**
 * 套图计划的全部机检（文档形状/数量/逐图草案/依赖一致性）；返回问题列表（空 = 合法）。
 * @param {unknown} plan
 * @param {import("./suite-plan.js").SuiteRegistryView | null | undefined} [registry]
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function validateSuitePlan(plan, registry) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
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

/**
 * 按图的求值汇总（界面可见）；输入是已校验的计划，shot_id 必为真实 id。
 * @param {PlanRecord | null | undefined} plan
 * @param {import("./type-contracts.js").EvalContext | null | undefined} context
 * @param {import("./suite-plan.js").SuiteRegistryView | null | undefined} [registry]
 * @returns {{total: number, satisfiable: number, blocked: number, required_blocked: string[], shots: {shot_id: string, template_id: string | null, label: string, role_id: string, role_label: string | null, required: boolean, custom: boolean, satisfied: boolean, blocking: import("./type-contracts.js").DependencyBlocking[]}[]}}
 */
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
