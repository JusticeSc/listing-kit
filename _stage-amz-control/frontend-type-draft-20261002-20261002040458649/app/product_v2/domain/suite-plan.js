/**
 * Product V2 套图计划领域：图片角色、Shot 模板与条件依赖（V2.3.1）。
 *
 * 唯一权威表示与唯一规则消费者都在本文件（计划 §9.4）：
 *  - 冻结数据（IMAGE_ROLES / SHOT_TEMPLATES）与纯函数规则同处一处，界面、编辑器与验证器读同一份；
 *  - 服务器不复制依赖规则；后续要用必须按计划 §9.4 的「新增消费者」条件重开；
 *  - 依赖只引用核心槽位 id、参考图角色与「该图绑定的已确认事实」，不写商品名或品类分支。
 *
 * 三条不可协商的规则：
 *  1) 只有 status=confirmed 的事实能作为图片依据；其余状态一律阻断并给精确原因；
 *  2) 配置里每个字段必须有消费者（FIELD_CONSUMERS），没有消费者的字段进不了注册表；
 *  3) 阻断精确到依赖：缺哪张参考图、缺哪条事实、哪条没确认，都要能说清。
 *
 * @typedef {{
 *   kind: "asset_role", role: string,
 * } | {
 *   kind: "fact", slot_id: string,
 * } | {
 *   kind: "fact_any", slot_ids: string[],
 * } | {
 *   kind: "bound_fact",
 * } | {
 *   kind: "any_of", of: DependencyRequirement[],
 * }} DependencyRequirement
 * @typedef {{
 *   role_id: string, label: string, purpose: string, custom: boolean,
 * }} SuiteRole
 * @typedef {{
 *   template_id: string, role_id: string, label: string, intent: string,
 *   required: boolean, order: number, dependencies: DependencyRequirement[],
 * }} SuiteTemplate
 * @typedef {{roles: SuiteRole[], templates: SuiteTemplate[]}} SuiteRegistry
 * @typedef {{
 *   facts?: Array<{slot_id: string, status: string, value?: import("./shared.js").SlotValue | null}>,
 *   assets?: Array<{role: string}>,
 *   bound_fact_ids?: string[],
 * }} EvalContext
 * @typedef {{
 *   shot_id: string | null, template_id: string | null, role_id: string,
 *   label: string, intent: string, required: boolean, custom: boolean,
 *   dependencies: DependencyRequirement[], fact_slot_ids: string[],
 * }} ShotDraft
 */

import { DOMAIN_ERROR_CODES, invalid } from "./errors.js";
import { REFERENCE_ROLES } from "./intake.js";
import { CORE_SLOT_IDS } from "./slots.js";
import { SLOT_ID_PATTERN, isNonEmptyString, isPlainObject, pushProblem } from "./shared.js";

export const SUITE_REGISTRY_SCHEMA_VERSION = 1;
export const CONFIRMED_FACT_STATUS = "confirmed";
export const BLOCKING_FACT_STATUSES = Object.freeze([
  "proposed", "missing", "conflict", "unknown", "superseded",
]);
export const DEPENDENCY_KINDS = Object.freeze([
  "asset_role", "fact", "fact_any", "bound_fact", "any_of",
]);
export const CUSTOM_ROLE_ID = "custom";
export const MAX_DEPENDENCY_DEPTH = 3;

/** 每种依赖谓词允许出现的参数；多余参数是配置错误，不是「以后可能有用」。 */
const DEPENDENCY_PARAMS = Object.freeze({
  asset_role: Object.freeze(["role"]),
  fact: Object.freeze(["slot_id"]),
  fact_any: Object.freeze(["slot_ids"]),
  bound_fact: Object.freeze([]),
  any_of: Object.freeze(["of"]),
});

/* ---------------------------------------------------------------- 依赖构造器 */

/**
 * @param {string} role
 * @returns {Readonly<{kind: "asset_role", role: string}>}
 */
export function assetRoleRequirement(role) {
  return Object.freeze({ kind: "asset_role", role });
}

/**
 * @param {string} slotId
 * @returns {Readonly<{kind: "fact", slot_id: string}>}
 */
export function factRequirement(slotId) {
  return Object.freeze({ kind: "fact", slot_id: slotId });
}

/**
 * @param {string[]} slotIds
 * @returns {Readonly<{kind: "fact_any", slot_ids: readonly string[]}>}
 */
export function factAnyRequirement(slotIds) {
  return Object.freeze({ kind: "fact_any", slot_ids: Object.freeze([...slotIds]) });
}

/**
 * @returns {Readonly<{kind: "bound_fact"}>}
 */
export function boundFactRequirement() {
  return Object.freeze({ kind: "bound_fact" });
}

/**
 * @param {DependencyRequirement[]} requirements
 * @returns {Readonly<{kind: "any_of", of: Readonly<DependencyRequirement[]>}>}
 */
export function anyOfRequirement(requirements) {
  return Object.freeze({
    kind: "any_of",
    of: Object.freeze([...requirements].map((item) => Object.freeze({ ...item }))),
  });
}

/* ------------------------------------------------------------ 角色与模板数据 */

export const IMAGE_ROLES = Object.freeze([
  Object.freeze({ role_id: "main", label: "主图",
    purpose: "干净背景下的商品主体，突出整体外观", custom: false }),
  Object.freeze({ role_id: "infographic", label: "卖点信息图",
    purpose: "用简短标注呈现已确认卖点，不写未确认参数", custom: false }),
  Object.freeze({ role_id: "scene", label: "场景图",
    purpose: "商品在真实使用场景中的样子，场景不改变商品外观", custom: false }),
  Object.freeze({ role_id: "detail", label: "细节图",
    purpose: "材质、工艺或关键部件的特写", custom: false }),
  Object.freeze({ role_id: "size", label: "尺寸图",
    purpose: "标注已确认的尺寸与比例，不猜数字", custom: false }),
  Object.freeze({ role_id: "comparison", label: "对比图",
    purpose: "与竞品或旧款同框对比，必须有对比参照", custom: false }),
  Object.freeze({ role_id: "ingredient", label: "成分·配料图",
    purpose: "呈现配料、成分或材质构成，依据必须可追溯", custom: false }),
  Object.freeze({ role_id: "packaging", label: "包装内容物图",
    purpose: "包装形态与随附物品，不添加未确认的赠品", custom: false }),
  Object.freeze({ role_id: CUSTOM_ROLE_ID, label: "自定义图",
    purpose: "用户自定义的图片任务", custom: true }),
]);

export const SHOT_TEMPLATES = Object.freeze([
  Object.freeze({
    template_id: "main_clean", role_id: "main", label: "主图·干净背景",
    intent: "完整展示商品主体，背景干净，不添加资料里没有的部件",
    required: true, order: 10,
    dependencies: Object.freeze([assetRoleRequirement("primary")]),
  }),
  Object.freeze({
    template_id: "infographic_benefits", role_id: "infographic", label: "卖点信息图",
    intent: "用简短标注呈现已确认卖点，不写入未确认参数",
    required: false, order: 20,
    dependencies: Object.freeze([factRequirement("signature_features")]),
  }),
  Object.freeze({
    template_id: "scene_lifestyle", role_id: "scene", label: "场景图·使用中",
    intent: "把商品放进符合用途的真实场景，场景不改变商品外观",
    required: false, order: 30,
    dependencies: Object.freeze([
      assetRoleRequirement("primary"), factRequirement("product_category"),
    ]),
  }),
  Object.freeze({
    template_id: "detail_material", role_id: "detail", label: "细节图·材质工艺",
    intent: "近距离呈现材质、做工或结构细节，颜色与标识与参考图一致",
    required: false, order: 40,
    dependencies: Object.freeze([
      factAnyRequirement(["key_material", "signature_features"]),
    ]),
  }),
  Object.freeze({
    template_id: "size_dimensions", role_id: "size", label: "尺寸图",
    intent: "标注已确认的尺寸信息，不猜测未提供的数字",
    required: false, order: 50,
    dependencies: Object.freeze([
      anyOfRequirement([factRequirement("size_summary"), boundFactRequirement()]),
    ]),
  }),
  Object.freeze({
    template_id: "comparison_competitor", role_id: "comparison", label: "对比图·竞品同框",
    intent: "与竞品同框对比已确认差异，不贬低竞品或编造参数",
    required: false, order: 60,
    dependencies: Object.freeze([
      assetRoleRequirement("competitor"), factRequirement("signature_features"),
    ]),
  }),
  Object.freeze({
    template_id: "ingredient_composition", role_id: "ingredient", label: "成分·配料图",
    intent: "呈现配料、成分或材质构成；依据必须来自该图绑定的已确认事实",
    required: false, order: 70,
    dependencies: Object.freeze([boundFactRequirement()]),
  }),
  Object.freeze({
    template_id: "packaging_contents", role_id: "packaging", label: "包装内容物图",
    intent: "展示包装形态与随附物品，不添加未确认的赠品",
    required: false, order: 80,
    dependencies: Object.freeze([
      anyOfRequirement([factRequirement("package_contents"), boundFactRequirement()]),
    ]),
  }),
]);

/* --------------------------------------------------- 字段 → 消费者（机检用） */

export const REGISTRY_FIELDS = Object.freeze({
  role: Object.freeze(["role_id", "label", "purpose", "custom"]),
  template: Object.freeze([
    "template_id", "role_id", "label", "intent", "required", "order", "dependencies",
  ]),
  dependency: Object.freeze(["kind", "role", "slot_id", "slot_ids", "of"]),
});

export const FIELD_CONSUMERS = Object.freeze({
  "role.role_id": "describeRole",
  "role.label": "describeRole",
  "role.purpose": "describeRole",
  "role.custom": "validateSuiteRegistry",
  "template.template_id": "describeTemplate",
  "template.role_id": "describeTemplate",
  "template.label": "describeTemplate",
  "template.intent": "describeTemplate",
  "template.required": "recommendPlan",
  "template.order": "recommendPlan",
  "template.dependencies": "evaluateDependencies",
  "dependency.kind": "evaluateDependencies",
  "dependency.role": "evaluateDependencies",
  "dependency.slot_id": "evaluateDependencies",
  "dependency.slot_ids": "evaluateDependencies",
  "dependency.of": "evaluateDependencies",
});

/**
 * 内置注册表：IMAGE_ROLES + SHOT_TEMPLATES 的原始可变视图（校验用，不改内容）。
 *
 * @returns {{roles: SuiteRole[], templates: SuiteTemplate[]}}
 */
export function builtinRegistry() {
  return { roles: IMAGE_ROLES, templates: SHOT_TEMPLATES };
}

function registryOf(registry) {
  const source = registry || builtinRegistry();
  return {
    roles: Array.isArray(source.roles) ? source.roles : [],
    templates: Array.isArray(source.templates) ? source.templates : [],
  };
}

/**
 * @param {string} roleId
 * @param {SuiteRegistry | null} [registry]
 * @returns {Readonly<SuiteRole> | null}
 */
export function roleDefinition(roleId, registry) {
  const { roles } = registryOf(registry);
  return roles.find((item) => item && item.role_id === roleId) || null;
}

/**
 * @param {string} templateId
 * @param {SuiteRegistry | null} [registry]
 * @returns {Readonly<SuiteTemplate> | null}
 */
export function templateDefinition(templateId, registry) {
  const { templates } = registryOf(registry);
  return templates.find((item) => item && item.template_id === templateId) || null;
}

/** 注册表自述：界面「能力清单」直接消费的形状（词表 + 依赖种类 + 模板描述）。
 *
 * @typedef {{
 *   schema_version: number, dependency_kinds: string[],
 *   roles: Array<{role_id: string, label: string, purpose: string, custom: boolean}>,
 *   templates: TemplateDescription[],
 * }} RegistryDescription
 * @param {SuiteRegistry | null} [registry]
 * @returns {RegistryDescription}
 */
export function describeRegistry(registry) {
  const { roles, templates } = registryOf(registry);
  return {
    schema_version: SUITE_REGISTRY_SCHEMA_VERSION,
    dependency_kinds: [...DEPENDENCY_KINDS],
    roles: roles.map((role) => ({ ...role })),
    templates: templates.map((template) => describeTemplate(template.template_id, registry)),
  };
}

/** 角色描述：界面按钮/文案用的稳定投影；未知角色返回 null（调用方自己决定降级文案）。
 *
 * @typedef {{role_id: string, label: string, purpose: string, custom: boolean}} RoleDescription
 * @param {string} roleId
 * @param {SuiteRegistry | null} [registry]
 * @returns {RoleDescription | null}
 */
export function describeRole(roleId, registry) {
  const role = roleDefinition(roleId, registry);
  if (!role) return null;
  return {
    role_id: role.role_id,
    label: role.label,
    purpose: role.purpose,
    custom: role.custom === true,
  };
}

/** 依赖的人话描述（界面提示直接用）；未知形状返回「非法依赖」，绝不抛错。
 *
 * @param {unknown} requirement
 * @returns {string}
 */
export function describeDependency(requirement) {
  if (!isPlainObject(requirement)) return "非法依赖";
  if (requirement.kind === "asset_role") {
    return `需要 ${String(requirement.role)} 角色的参考图`;
  }
  if (requirement.kind === "fact") {
    return `需要已确认事实：${String(requirement.slot_id)}`;
  }
  if (requirement.kind === "fact_any") {
    const ids = Array.isArray(requirement.slot_ids) ? requirement.slot_ids : [];
    return `需要已确认事实之一：${ids.join("、")}`;
  }
  if (requirement.kind === "bound_fact") {
    return "需要该图绑定至少一条已确认事实";
  }
  if (requirement.kind === "any_of") {
    const list = Array.isArray(requirement.of) ? requirement.of : [];
    return "满足其一即可：" + list.map((item) => describeDependency(item)).join(" 或 ");
  }
  return `未知依赖类型：${String(requirement.kind)}`;
}

/** 模板描述：界面模板卡片直接消费的稳定投影；未知模板返回 null。
 *
 * @typedef {{template_id: string, role_id: string, role_label: string | null,
 *            label: string, intent: string, required: boolean, order: number,
 *            custom: boolean, dependencies: DependencyRequirement[],
 *            dependency_text: string[]}} TemplateDescription
 * @param {string} templateId
 * @param {SuiteRegistry | null} [registry]
 * @returns {TemplateDescription | null}
 */
export function describeTemplate(templateId, registry) {
  const template = templateDefinition(templateId, registry);
  if (!template) return null;
  const role = describeRole(template.role_id, registry);
  return {
    template_id: template.template_id,
    role_id: template.role_id,
    role_label: role ? role.label : null,
    label: template.label,
    intent: template.intent,
    required: template.required === true,
    order: template.order,
    custom: Boolean(role && role.custom),
    dependencies: Array.isArray(template.dependencies) ? template.dependencies.map((item) => ({ ...item })) : [],
    dependency_text: (Array.isArray(template.dependencies) ? template.dependencies : [])
      .map((item) => describeDependency(item)),
  };
}

/* -------------------------------------------------------------------- 求值 */

function factIndex(context) {
  const list = Array.isArray(context && context.facts) ? context.facts : [];
  const index = new Map();
  for (const fact of list) {
    if (isPlainObject(fact) && typeof fact.slot_id === "string") index.set(fact.slot_id, fact);
  }
  return index;
}

function assetRoleSet(context) {
  const list = Array.isArray(context && context.assets) ? context.assets : [];
  const roles = new Set();
  for (const asset of list) {
    if (isPlainObject(asset) && typeof asset.role === "string") roles.add(asset.role);
  }
  return roles;
}

function boundFactSet(context) {
  const list = Array.isArray(context && context.bound_fact_ids) ? context.bound_fact_ids : [];
  return new Set(list.filter((item) => typeof item === "string"));
}

function checkFact(fact, slotId) {
  if (!fact) {
    return { satisfied: false, reason: `事实 ${slotId} 缺失`, missing: [slotId] };
  }
  if (fact.status !== CONFIRMED_FACT_STATUS) {
    return {
      satisfied: false,
      reason: `事实 ${slotId} 尚未确认（当前 ${String(fact.status)}）`,
      missing: [slotId],
    };
  }
  return { satisfied: true, reason: null, missing: [] };
}

function evaluateRequirement(requirement, state) {
  if (!isPlainObject(requirement)) {
    return { satisfied: false, reason: "依赖不是对象。", missing: [] };
  }
  if (requirement.kind === "asset_role") {
    if (state.assetRoles.has(requirement.role)) return { satisfied: true, reason: null, missing: [] };
    return { satisfied: false, reason: `缺少 ${String(requirement.role)} 角色的参考图`, missing: [requirement.role] };
  }
  if (requirement.kind === "fact") {
    return checkFact(state.facts.get(requirement.slot_id), requirement.slot_id);
  }
  if (requirement.kind === "fact_any") {
    const ids = Array.isArray(requirement.slot_ids) ? requirement.slot_ids : [];
    for (const slotId of ids) {
      if (checkFact(state.facts.get(slotId), slotId).satisfied) {
        return { satisfied: true, reason: null, missing: [] };
      }
    }
    return {
      satisfied: false,
      reason: `下列事实都还不能作为依据：${ids.join("、")}`,
      missing: ids,
    };
  }
  if (requirement.kind === "bound_fact") {
    const bound = [...state.boundFactIds];
    if (!bound.length) {
      return { satisfied: false, reason: "该图还没有绑定已确认事实", missing: [] };
    }
    for (const slotId of bound) {
      if (checkFact(state.facts.get(slotId), slotId).satisfied) {
        return { satisfied: true, reason: null, missing: [] };
      }
    }
    return { satisfied: false, reason: `绑定的 ${bound.join("、")} 都还没有确认`, missing: bound };
  }
  if (requirement.kind === "any_of") {
    const list = Array.isArray(requirement.of) ? requirement.of : [];
    const results = list.map((item) => evaluateRequirement(item, state));
    if (results.some((item) => item.satisfied)) return { satisfied: true, reason: null, missing: [] };
    return {
      satisfied: false,
      reason: "以下任一条都不成立：" + results.map((item) => item.reason).join("；"),
      missing: results.flatMap((item) => item.missing),
    };
  }
  return { satisfied: false, reason: `未知依赖类型：${String(requirement.kind)}`, missing: [] };
}

/**
 * @typedef {{
 *   kind: string, reason: string | null, missing: string[],
 * }} DependencyBlocker
 * @typedef {{satisfied: boolean, blocking: DependencyBlocker[]}} DependencyEvaluation
 * @param {DependencyRequirement[]} dependencies
 * @param {EvalContext | null} [context]
 * @returns {DependencyEvaluation}
 */
export function evaluateDependencies(dependencies, context) {
  const state = {
    facts: factIndex(context),
    assetRoles: assetRoleSet(context),
    boundFactIds: boundFactSet(context),
  };
  const list = Array.isArray(dependencies) ? dependencies : [];
  const blocking = [];
  for (const requirement of list) {
    const result = evaluateRequirement(requirement, state);
    if (!result.satisfied) {
      blocking.push({
        kind: isPlainObject(requirement) ? requirement.kind : null,
        reason: result.reason,
        missing: [...result.missing],
      });
    }
  }
  return { satisfied: blocking.length === 0, blocking };
}

/**
 * @param {string} templateId
 * @param {{shotId?: string|null, factSlotIds?: string[]}} [options]
 * @param {SuiteRegistry | null} [registry]
 * @returns {Readonly<ShotDraft>}
 */
export function instantiateTemplate(templateId, options = {}, registry) {
  const template = templateDefinition(templateId, registry);
  if (!template) invalid(`模板不存在：${String(templateId)}`);
  return Object.freeze({
    shot_id: options.shotId === undefined ? null : options.shotId,
    template_id: template.template_id,
    role_id: template.role_id,
    label: template.label,
    intent: template.intent,
    required: template.required === true,
    order: template.order,
    custom: false,
    dependencies: template.dependencies,
    fact_slot_ids: Object.freeze([...(options.factSlotIds || [])]),
  });
}

/**
 * @typedef {{
 *   shot_id: string | null, template_id: string | null,
 *   satisfied: boolean, blocking: DependencyBlocker[],
 * }} ShotEvaluation
 * @param {unknown} shot
 * @param {EvalContext | null} [context]
 * @param {SuiteRegistry | null} [registry]
 * @returns {ShotEvaluation}
 */
export function evaluateShot(shot, context, registry) {
  const dependencies = isPlainObject(shot) && Array.isArray(shot.dependencies)
    ? shot.dependencies
    : (isPlainObject(shot) && shot.template_id
      ? (templateDefinition(shot.template_id, registry) || {}).dependencies
      : []);
  const boundFactIds = isPlainObject(shot) && Array.isArray(shot.fact_slot_ids) ? shot.fact_slot_ids : [];
  const result = evaluateDependencies(dependencies, { ...(context || {}), bound_fact_ids: boundFactIds });
  return {
    shot_id: isPlainObject(shot) ? shot.shot_id ?? null : null,
    template_id: isPlainObject(shot) ? shot.template_id ?? null : null,
    satisfied: result.satisfied,
    blocking: result.blocking,
  };
}

/**
 * @typedef {{
 *   template_id: string, role_id: string, role_label: string | null,
 *   label: string, intent: string, required: boolean, order: number,
 *   custom: boolean, fact_slot_ids: string[],
 *   satisfied: boolean, blocking: DependencyBlocker[],
 * }} RecommendedShotInstance
 * @typedef {{
 *   instances: RecommendedShotInstance[],
 *   satisfiable: string[], blocked: string[], required_blocked: string[],
 * }} PlanRecommendation
 * @param {EvalContext | null} context
 * @param {{registry?: SuiteRegistry|null, bound_fact_ids_by_template?: Record<string, string[]>}} [options]
 * @returns {PlanRecommendation}
 */
export function recommendPlan(context, options = {}) {
  const { templates } = registryOf(options.registry);
  const boundByTemplate = isPlainObject(options.bound_fact_ids_by_template)
    ? options.bound_fact_ids_by_template
    : {};
  const instances = [...templates]
    .filter((template) => isPlainObject(template))
    .sort((left, right) => Number(left.order) - Number(right.order))
    .map((template) => {
      const bound = Array.isArray(boundByTemplate[template.template_id])
        ? boundByTemplate[template.template_id]
        : [];
      const result = evaluateDependencies(template.dependencies, { ...(context || {}), bound_fact_ids: bound });
      const role = roleDefinition(template.role_id, options.registry);
      return {
        template_id: template.template_id,
        role_id: template.role_id,
        role_label: role ? role.label : null,
        label: template.label,
        intent: template.intent,
        required: template.required === true,
        order: template.order,
        custom: Boolean(role && role.custom),
        fact_slot_ids: [...bound],
        satisfied: result.satisfied,
        blocking: result.blocking,
      };
    });
  return {
    instances,
    satisfiable: instances.filter((item) => item.satisfied).map((item) => item.template_id),
    blocked: instances.filter((item) => !item.satisfied).map((item) => item.template_id),
    required_blocked: instances.filter((item) => item.required && !item.satisfied)
      .map((item) => item.template_id),
  };
}

/* ------------------------------------------------------------ 自定义 Shot */

/**
 * @param {{label: string, intent?: string, factSlotIds?: string[]}} [input]
 * @returns {Readonly<ShotDraft>}
 */
export function createCustomShot({ label, intent = "", factSlotIds = [] } = {}) {
  if (!isNonEmptyString(label)) invalid("自定义图必须有名称。");
  return Object.freeze({
    shot_id: null,
    template_id: null,
    role_id: CUSTOM_ROLE_ID,
    label,
    intent: typeof intent === "string" ? intent : "",
    required: false,
    order: null,
    custom: true,
    dependencies: Object.freeze([]),
    fact_slot_ids: Object.freeze([...factSlotIds]),
  });
}

/**
 * @param {unknown} shot
 * @param {SuiteRegistry | null} [registry]
 * @returns {import("./shared.js").DomainProblem[]}
 */
export function checkShotDraft(shot, registry) {
  const problems = [];
  if (!isPlainObject(shot)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "Shot 必须是对象。");
    return problems;
  }
  const role = roleDefinition(shot.role_id, registry);
  if (!role) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.role_id", "图片角色不在注册表内。");
  } else if (role.custom) {
    if (!isNonEmptyString(shot.label)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.label", "自定义图必须有名称。");
    }
    if (shot.template_id !== null && shot.template_id !== undefined) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.template_id",
        "自定义图不来自模板。");
    }
  } else {
    const template = templateDefinition(shot.template_id, registry);
    if (!template) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.template_id",
        "非自定义图必须来自已登记模板。");
    } else if (template.role_id !== shot.role_id) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.role_id",
        "Shot 的角色必须与模板一致。");
    }
  }
  const bound = shot.fact_slot_ids;
  if (!Array.isArray(bound)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.fact_slot_ids",
      "fact_slot_ids 必须是数组。");
  } else {
    const seen = new Set();
    bound.forEach((slotId, index) => {
      if (typeof slotId !== "string" || !SLOT_ID_PATTERN.test(slotId)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID,
          `$.fact_slot_ids[${index}]`, "绑定的事实必须是合法 slot_id。");
      } else if (seen.has(slotId)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID,
          `$.fact_slot_ids[${index}]`, "绑定的事实不允许重复。");
      } else {
        seen.add(slotId);
      }
    });
  }
  for (const problem of validateDependencies(shot.dependencies, "$.dependencies")) {
    problems.push(problem);
  }
  return problems;
}

/* ------------------------------------------------------------------ 校验 */

function checkDeclaredFields(problems, object, kind, path) {
  const declared = REGISTRY_FIELDS[kind] || [];
  for (const key of Object.keys(object)) {
    if (!declared.includes(key)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${path}.${key}`,
        `字段 ${key} 没有登记：没有消费者的字段不能进入注册表。`);
      continue;
    }
    if (!FIELD_CONSUMERS[`${kind}.${key}`]) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${path}.${key}`,
        `字段 ${key} 没有消费者：先加消费者再加字段。`);
    }
  }
  for (const field of declared) {
    if (!FIELD_CONSUMERS[`${kind}.${field}`]) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${path}.${field}`,
        `声明了字段 ${field} 却没有登记消费者。`);
    }
  }
}

function validateDependencies(dependencies, path, depth = 0) {
  const problems = [];
  if (!Array.isArray(dependencies)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "dependencies 必须是数组。");
    return problems;
  }
  dependencies.forEach((requirement, index) => {
    const itemPath = `${path}[${index}]`;
    if (!isPlainObject(requirement)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, itemPath, "依赖必须是对象。");
      return;
    }
    checkDeclaredFields(problems, requirement, "dependency", itemPath);
    if (depth > MAX_DEPENDENCY_DEPTH) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, itemPath,
        `依赖嵌套超过 ${MAX_DEPENDENCY_DEPTH} 层。`);
      return;
    }
    if (!DEPENDENCY_KINDS.includes(requirement.kind)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${itemPath}.kind`,
        "未知依赖类型。");
      return;
    }
    const allowed = DEPENDENCY_PARAMS[requirement.kind] || [];
    for (const key of Object.keys(requirement)) {
      if (key !== "kind" && !allowed.includes(key)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${itemPath}.${key}`,
          `${requirement.kind} 不接受参数 ${key}。`);
      }
    }
    if (requirement.kind === "asset_role") {
      if (!REFERENCE_ROLES.includes(requirement.role)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${itemPath}.role`,
          "参考图角色不在词表内。");
      }
    } else if (requirement.kind === "fact") {
      if (!CORE_SLOT_IDS.includes(requirement.slot_id)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${itemPath}.slot_id`,
          "fact 依赖必须引用核心槽位。");
      }
    } else if (requirement.kind === "fact_any") {
      const ids = requirement.slot_ids;
      if (!Array.isArray(ids) || !ids.length) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${itemPath}.slot_ids`,
          "fact_any 至少要有一个核心槽位。");
      } else {
        if (new Set(ids).size !== ids.length) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${itemPath}.slot_ids`,
            "fact_any 的槽位不允许重复。");
        }
        ids.forEach((slotId, slotIndex) => {
          if (!CORE_SLOT_IDS.includes(slotId)) {
            pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID,
              `${itemPath}.slot_ids[${slotIndex}]`, "fact_any 只能引用核心槽位。");
          }
        });
      }
    } else if (requirement.kind === "any_of") {
      problems.push(...validateDependencies(requirement.of, `${itemPath}.of`, depth + 1));
    }
  });
  return problems;
}

/**
 * @param {unknown} registry
 * @returns {import("./shared.js").DomainProblem[]}
 */
export function validateSuiteRegistry(registry) {
  const { roles, templates } = registryOf(registry);
  const problems = [];
  const roleIds = new Set();
  roles.forEach((role, index) => {
    const path = `$.roles[${index}]`;
    if (!isPlainObject(role)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "角色必须是对象。");
      return;
    }
    checkDeclaredFields(problems, role, "role", path);
    if (!isNonEmptyString(role.role_id) || !SLOT_ID_PATTERN.test(role.role_id)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${path}.role_id`,
        "role_id 必须是合法标识。");
    } else if (roleIds.has(role.role_id)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${path}.role_id`,
        "role_id 重复。");
    } else {
      roleIds.add(role.role_id);
    }
    if (!isNonEmptyString(role.label)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${path}.label`,
        "角色必须有名称。");
    }
    if (!isNonEmptyString(role.purpose)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${path}.purpose`,
        "角色必须有用途说明。");
    }
    if (typeof role.custom !== "boolean") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${path}.custom`,
        "custom 必须是布尔值。");
    }
  });
  const customRoles = roles.filter((role) => isPlainObject(role) && role.custom === true);
  if (customRoles.length !== 1 || customRoles[0].role_id !== CUSTOM_ROLE_ID) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.roles",
      `必须恰有一个 custom 角色，且 role_id 为 ${CUSTOM_ROLE_ID}。`);
  }
  const templateIds = new Set();
  const orders = new Set();
  const usedRoles = new Set();
  templates.forEach((template, index) => {
    const path = `$.templates[${index}]`;
    if (!isPlainObject(template)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "模板必须是对象。");
      return;
    }
    checkDeclaredFields(problems, template, "template", path);
    if (!isNonEmptyString(template.template_id) || !SLOT_ID_PATTERN.test(template.template_id)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${path}.template_id`,
        "template_id 必须是合法标识。");
    } else if (templateIds.has(template.template_id)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${path}.template_id`,
        "template_id 重复。");
    } else {
      templateIds.add(template.template_id);
    }
    const role = roleDefinition(template.role_id, { roles, templates });
    if (!role) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${path}.role_id`,
        "模板引用了未登记的角色。");
    } else if (role.custom) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${path}.role_id`,
        "自定义图不通过注册表模板提供。");
    } else {
      usedRoles.add(role.role_id);
    }
    if (!isNonEmptyString(template.label)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${path}.label`,
        "模板必须有名称。");
    }
    if (!isNonEmptyString(template.intent)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${path}.intent`,
        "模板必须有拍摄意图。");
    }
    if (typeof template.required !== "boolean") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${path}.required`,
        "required 必须是布尔值。");
    }
    if (!Number.isInteger(template.order) || template.order <= 0) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${path}.order`,
        "order 必须是正整数。");
    } else if (orders.has(template.order)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `${path}.order`,
        "order 不允许重复。");
    } else {
      orders.add(template.order);
    }
    problems.push(...validateDependencies(template.dependencies, `${path}.dependencies`));
  });
  roles.forEach((role, index) => {
    if (!isPlainObject(role) || role.custom === true) return;
    if (!usedRoles.has(role.role_id)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, `$.roles[${index}].role_id`,
        "该角色没有被任何模板引用（没有消费者）。");
    }
  });
  return problems;
}
