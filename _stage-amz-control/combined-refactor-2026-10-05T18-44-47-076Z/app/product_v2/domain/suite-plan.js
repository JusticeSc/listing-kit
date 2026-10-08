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
 */

import { DOMAIN_ERROR_CODES, invalid } from "./errors.js";
import { REFERENCE_ROLES } from "./intake.js";
import { CORE_SLOT_IDS } from "./slots.js";
import { SLOT_ID_PATTERN, isDimensionValue, isNonEmptyString, isPlainObject, pushProblem } from "./shared.js";

/** @type {number} */
export const SUITE_REGISTRY_SCHEMA_VERSION = 1;
/** @type {"confirmed"} */
export const CONFIRMED_FACT_STATUS = "confirmed";
/** @type {readonly import("./type-contracts.js").SlotStatus[]} */
export const BLOCKING_FACT_STATUSES = Object.freeze([
  "proposed", "missing", "conflict", "unknown", "superseded",
]);
/** @type {readonly import("./type-contracts.js").DependencyKind[]} */
export const DEPENDENCY_KINDS = Object.freeze([
  "asset_role", "fact", "fact_any", "bound_fact", "bound_dimension", "any_of",
]);
/** @type {"custom"} */
export const CUSTOM_ROLE_ID = "custom";
/** @type {number} */
export const MAX_DEPENDENCY_DEPTH = 3;

/** 每种依赖谓词允许出现的参数；多余参数是配置错误，不是「以后可能有用」。 @type {Readonly<Record<import("./type-contracts.js").DependencyKind, readonly string[]>>} */
const DEPENDENCY_PARAMS = Object.freeze({
  asset_role: Object.freeze(["role"]),
  fact: Object.freeze(["slot_id"]),
  fact_any: Object.freeze(["slot_ids"]),
  bound_fact: Object.freeze([]),
  bound_dimension: Object.freeze([]),
  any_of: Object.freeze(["of"]),
});

/**
 * 运行时依赖形状：依赖对象在运行时被 Object.freeze，fact_any / any_of 的数组按只读处理。
 * （与 type-contracts.d.ts 的 ShotDependency 同形；差异只在数组只读性，因为构造器会冻结数组。）
 *
 * @typedef {Readonly<{kind: "asset_role", role: string}>
 *   | Readonly<{kind: "fact", slot_id: string}>
 *   | Readonly<{kind: "fact_any", slot_ids: readonly string[]}>
 *   | Readonly<{kind: "bound_fact"}>
 *   | Readonly<{kind: "bound_dimension"}>
 *   | Readonly<{kind: "any_of", of: readonly FrozenShotDependency[]}>} FrozenShotDependency
 */

/**
 * 注册表模板的运行时读取形状（模板对象与依赖数组都被冻结）。
 * @typedef {Readonly<Omit<import("./type-contracts.js").ShotTemplate, "dependencies"> & {dependencies: readonly FrozenShotDependency[]}>} FrozenShotTemplate
 */

/**
 * 注册表的运行时读取形状：内置注册表整体冻结；外部传入的 SuiteRegistry 同样兼容。
 * @typedef {{roles: readonly import("./type-contracts.js").ImageRole[], templates: readonly FrozenShotTemplate[]}} SuiteRegistryView
 */

/**
 * 运行时 Shot 形状：模板依赖与绑定槽位数组在运行时被冻结；order 仅模板实例携带。
 * @typedef {Omit<import("./type-contracts.js").ShotDraft, "dependencies" | "fact_slot_ids"> & {dependencies: ReadonlyArray<FrozenShotDependency>, fact_slot_ids: readonly string[]}} ShotRecord
 */

/**
 * 单条依赖谓词的求值结果。
 * @typedef {{satisfied: boolean, reason: string | null, missing: string[]}} RequirementCheck
 */

/**
 * 一次依赖求值的内部状态（factIndex / assetRoleSet / boundFactSet 的产物）。
 * @typedef {{facts: Map<string, Record<string, unknown> & {slot_id: string}>, assetRoles: Set<string>, boundFactIds: Set<string>}} EvaluationState
 */

/**
 * 一次依赖求值的结果：满足判定与精确阻断列表。
 * @typedef {{satisfied: boolean, blocking: import("./type-contracts.js").DependencyBlocking[]}} DependencyEvaluation
 */

/**
 * 角色的人读投影（describeRole 的返回）。
 * @typedef {{role_id: string, label: string, purpose: string, custom: boolean}} RoleDescription
 */

/**
 * 模板的人读投影（describeTemplate 的返回）。
 * @typedef {{template_id: string, role_id: string, role_label: string | null, label: string, intent: string, required: boolean, order: number, custom: boolean, dependencies: ReadonlyArray<FrozenShotDependency>, dependency_text: string[]}} TemplateDescription
 */

/**
 * recommendPlan 的 options（seedSuitePlan 复用同一份）。
 * @typedef {{registry?: SuiteRegistryView | null, bound_fact_ids_by_template?: Record<string, string[]> | null}} RecommendOptions
 */

/* ---------------------------------------------------------------- 依赖构造器 */

/**
 * 依赖构造器：需要某参考图角色。
 * @param {string} role
 * @returns {FrozenShotDependency}
 */
export function assetRoleRequirement(role) {
  return Object.freeze({ kind: "asset_role", role });
}

/**
 * 依赖构造器：需要某条已确认事实。
 * @param {string} slotId
 * @returns {FrozenShotDependency}
 */
export function factRequirement(slotId) {
  return Object.freeze({ kind: "fact", slot_id: slotId });
}

/**
 * 依赖构造器：需要列出的已确认事实之一。
 * @param {ReadonlyArray<string>} slotIds
 * @returns {FrozenShotDependency}
 */
export function factAnyRequirement(slotIds) {
  return Object.freeze({ kind: "fact_any", slot_ids: Object.freeze([...slotIds]) });
}

/**
 * 依赖构造器：需要该图绑定至少一条已确认事实。
 * @returns {FrozenShotDependency}
 */
export function boundFactRequirement() {
  return Object.freeze({ kind: "bound_fact" });
}

/**
 * 尺寸图专用：这张图绑定的已确认事实里，至少有一条是**结构性尺寸测量**
 * （对象/轴向/有限正数/单位/来源依据），自由文本或标量不算数（V2.R6.2）。
 * @returns {FrozenShotDependency}
 */
export function boundDimensionRequirement() {
  return Object.freeze({ kind: "bound_dimension" });
}

/**
 * 依赖构造器：满足其一即可；子依赖递归校验。
 * @param {ReadonlyArray<FrozenShotDependency>} requirements
 * @returns {FrozenShotDependency}
 */
export function anyOfRequirement(requirements) {
  return Object.freeze({
    kind: "any_of",
    of: Object.freeze([...requirements].map((item) => Object.freeze({ ...item }))),
  });
}

/* ------------------------------------------------------------ 角色与模板数据 */

/** @type {readonly import("./type-contracts.js").ImageRole[]} */
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

/** @type {readonly FrozenShotTemplate[]} */
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
    intent: "标注已确认的结构化尺寸（对象/轴向/数值/单位与来源）；不猜数字、不用自由文本冒充测量",
    required: false, order: 50,
    dependencies: Object.freeze([
      anyOfRequirement([factRequirement("size_dimensions"), boundDimensionRequirement()]),
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

/** @type {Readonly<Record<"role" | "template" | "dependency", readonly string[]>>} */
export const REGISTRY_FIELDS = Object.freeze({
  role: Object.freeze(["role_id", "label", "purpose", "custom"]),
  template: Object.freeze([
    "template_id", "role_id", "label", "intent", "required", "order", "dependencies",
  ]),
  dependency: Object.freeze(["kind", "role", "slot_id", "slot_ids", "of"]),
});

/** @type {Readonly<Record<string, string>>} */
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
 * 内置注册表（IMAGE_ROLES / SHOT_TEMPLATES）；调用方没传 registry 时全领域用它。
 * @returns {SuiteRegistryView}
 */
export function builtinRegistry() {
  return { roles: IMAGE_ROLES, templates: SHOT_TEMPLATES };
}

/**
 * @param {SuiteRegistryView | null | undefined} [registry]
 * @returns {SuiteRegistryView}
 */
function registryOf(registry) {
  const source = registry || builtinRegistry();
  return {
    roles: Array.isArray(source.roles) ? source.roles : [],
    templates: Array.isArray(source.templates) ? source.templates : [],
  };
}

/**
 * 按 roleId 找角色定义；找不到（含传入非字符串 id）返回 null。
 * @param {unknown} roleId
 * @param {SuiteRegistryView | null | undefined} [registry]
 * @returns {import("./type-contracts.js").ImageRole | null}
 */
export function roleDefinition(roleId, registry) {
  const { roles } = registryOf(registry);
  return roles.find((item) => item && item.role_id === roleId) || null;
}

/**
 * 按 templateId 找模板定义；找不到（含传入非字符串 id）返回 null。
 * @param {unknown} templateId
 * @param {SuiteRegistryView | null | undefined} [registry]
 * @returns {FrozenShotTemplate | null}
 */
export function templateDefinition(templateId, registry) {
  const { templates } = registryOf(registry);
  return templates.find((item) => item && item.template_id === templateId) || null;
}

/**
 * 注册表的人读投影（界面用）。
 * @param {SuiteRegistryView | null | undefined} [registry]
 * @returns {{schema_version: number, dependency_kinds: import("./type-contracts.js").DependencyKind[], roles: import("./type-contracts.js").ImageRole[], templates: (TemplateDescription | null)[]}}
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

/**
 * 单个角色的人读投影；未登记返回 null。
 * @param {string} roleId
 * @param {SuiteRegistryView | null | undefined} [registry]
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

/**
 * 一条依赖谓词的人读描述；未知/非法依赖也给出文字。
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
  if (requirement.kind === "bound_dimension") {
    return "需要该图绑定至少一条已确认的结构性尺寸（对象/轴向/数值/单位/来源）";
  }
  if (requirement.kind === "any_of") {
    const list = Array.isArray(requirement.of) ? requirement.of : [];
    return "满足其一即可：" + list.map((item) => describeDependency(item)).join(" 或 ");
  }
  return `未知依赖类型：${String(requirement.kind)}`;
}

/**
 * 单个模板的人读投影（依赖描述逐条展开）；未登记返回 null。
 * @param {string} templateId
 * @param {SuiteRegistryView | null | undefined} [registry]
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

/**
 * @param {import("./type-contracts.js").EvalContext | null | undefined} context
 * @returns {Map<string, Record<string, unknown> & {slot_id: string}>}
 */
function factIndex(context) {
  const list = Array.isArray(context && context.facts)
    ? (/** @type {{facts: ReadonlyArray<{slot_id: string, status: string, value?: unknown}>}} */ (context)).facts
    : [];
  /** @type {Map<string, Record<string, unknown> & {slot_id: string}>} */
  const index = new Map();
  for (const fact of list) {
    if (isPlainObject(fact) && typeof fact.slot_id === "string") index.set(fact.slot_id, fact);
  }
  return index;
}

/**
 * @param {import("./type-contracts.js").EvalContext | null | undefined} context
 * @returns {Set<string>}
 */
function assetRoleSet(context) {
  const list = Array.isArray(context && context.assets)
    ? (/** @type {{assets: ReadonlyArray<{role: string}>}} */ (context)).assets
    : [];
  /** @type {Set<string>} */
  const roles = new Set();
  for (const asset of list) {
    if (isPlainObject(asset) && typeof asset.role === "string") roles.add(asset.role);
  }
  return roles;
}

/**
 * @param {import("./type-contracts.js").EvalContext | null | undefined} context
 * @returns {Set<string>}
 */
function boundFactSet(context) {
  const list = Array.isArray(context && context.bound_fact_ids)
    ? (/** @type {{bound_fact_ids: ReadonlyArray<string>}} */ (context)).bound_fact_ids
    : [];
  return new Set(list.filter((item) => typeof item === "string"));
}

/**
 * 已确认才放行；其余状态一律阻断并给精确原因。
 * @param {Record<string, unknown> & {slot_id: string} | null | undefined} fact
 * @param {string} slotId
 * @returns {RequirementCheck}
 */
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

/**
 * 递归求值一条依赖谓词；嵌套 any_of 一并展开。
 * @param {FrozenShotDependency} requirement
 * @param {EvaluationState} state
 * @returns {RequirementCheck}
 */
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
  if (requirement.kind === "bound_dimension") {
    const bound = [...state.boundFactIds];
    if (!bound.length) {
      return { satisfied: false, reason: "该尺寸图还没有绑定已确认的尺寸事实", missing: [] };
    }
    let sawConfirmed = false;
    for (const slotId of bound) {
      const fact = state.facts.get(slotId);
      if (!checkFact(fact, slotId).satisfied) continue;
      sawConfirmed = true;
      if (isDimensionValue((/** @type {Record<string, unknown>} */ (fact)).value)) {
        return { satisfied: true, reason: null, missing: [] };
      }
    }
    if (sawConfirmed) {
      return {
        satisfied: false,
        reason: `绑定的尺寸事实必须是结构性测量（对象/轴向/有限正数/单位/来源依据）：${bound.join("、")}`,
        missing: bound,
      };
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
  return { satisfied: false, reason: `未知依赖类型：${String((/** @type {{kind: unknown}} */ (requirement)).kind)}`, missing: [] };
}

/**
 * 对一组依赖谓词求值；只有全部满足才算满足，阻断精确到每条谓词。
 * @param {ReadonlyArray<FrozenShotDependency> | null | undefined} dependencies
 * @param {import("./type-contracts.js").EvalContext | null | undefined} context
 * @returns {DependencyEvaluation}
 */
export function evaluateDependencies(dependencies, context) {
  const state = {
    facts: factIndex(context),
    assetRoles: assetRoleSet(context),
    boundFactIds: boundFactSet(context),
  };
  const list = /** @type {ReadonlyArray<FrozenShotDependency>} */ (Array.isArray(dependencies) ? dependencies : []);
  /** @type {import("./type-contracts.js").DependencyBlocking[]} */
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
 * 从模板生成一份冻结的 Shot 草稿（未持久化时 shot_id 为 null）。
 * @param {string} templateId
 * @param {{shotId?: string | null, factSlotIds?: ReadonlyArray<string>} | undefined} [options]
 * @param {SuiteRegistryView | null | undefined} [registry]
 * @returns {Readonly<ShotRecord>}
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
 * 求值一张图的依赖（缺 dependencies 时回退模板定义）；id 字段透传原值。
 * @param {unknown} shot
 * @param {import("./type-contracts.js").EvalContext | null | undefined} context
 * @param {SuiteRegistryView | null | undefined} [registry]
 * @returns {{shot_id: unknown, template_id: unknown, satisfied: boolean, blocking: import("./type-contracts.js").DependencyBlocking[]}}
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

/* --------------------------------------------------- 按图就绪与消费依据投影 */

/**
 * 这张图自己的确定性签名（V2.R6.2）：只覆盖它自己的定义字段，与整份套图文档版本无关。
 * 因此改另一张图不会让这张图的 Prompt 过期；只有这张图自己的定义变了才变。
 * 用确定性字符串（键排序），只用于「和上次编译时是不是同一张图」的比较。
 * @type {readonly (keyof import("./type-contracts.js").ShotDraft)[]}
 */
export const SHOT_SIGNATURE_FIELDS = Object.freeze([
  "shot_id", "template_id", "role_id", "label", "intent", "required", "custom",
  "dependencies", "fact_slot_ids",
]);

/**
 * 稳定序列化：数组保持顺序，对象键排序；undefined 与空槽都写成 null。
 * @param {unknown} value
 * @returns {string}
 */
function stableStringify(value) {
  if (Array.isArray(value)) return "[" + value.map(stableStringify).join(",") + "]";
  if (isPlainObject(value)) {
    return "{" + Object.keys(value).sort()
      .filter((key) => value[key] !== undefined)
      .map((key) => JSON.stringify(key) + ":" + stableStringify(value[key])).join(",") + "}";
  }
  return value === undefined ? "null" : JSON.stringify(value);
}

/**
 * Shot 的确定性签名（stableStringify 的键排序投影）。
 * @param {unknown} shot
 * @returns {string}
 */
export function shotSignatureOf(shot) {
  if (!isPlainObject(shot)) invalid("Shot 签名需要一张 Shot 对象。");
  /** @type {Record<string, unknown>} */
  const projection = {};
  for (const key of SHOT_SIGNATURE_FIELDS) projection[key] = shot[key] === undefined ? null : shot[key];
  return stableStringify(projection);
}

/**
 * 这张图实际消费的已确认事实槽位（V2.R6.2）：绑定的文案来源 + 满足它依赖谓词的已确认槽位。
 * 只包含「真正提供依据」的槽位（fact/fact_any/bound_fact 里已确认的那些）；asset_role 不产槽位。
 * 用途缺项按图算，不把无关事实塞进这张图的消费依据。
 * @param {unknown} shot
 * @param {readonly string[]} [confirmedSlotIds]
 * @returns {string[]}
 */
export function consumedSlotIdsOf(shot, confirmedSlotIds = []) {
  const confirmed = new Set((Array.isArray(confirmedSlotIds) ? confirmedSlotIds : [])
    .filter((item) => typeof item === "string"));
  /** @type {Set<string>} */
  const ids = new Set();
  const bound = isPlainObject(shot) && Array.isArray(shot.fact_slot_ids) ? shot.fact_slot_ids : [];
  for (const slotId of bound) if (confirmed.has(slotId)) ids.add(slotId);
  /** @param {FrozenShotDependency} requirement */
  const collect = (requirement) => {
    if (!isPlainObject(requirement)) return;
    if (requirement.kind === "fact" && confirmed.has(requirement.slot_id)) {
      ids.add(requirement.slot_id);
    }
    if (requirement.kind === "fact_any") {
      for (const slotId of Array.isArray(requirement.slot_ids) ? requirement.slot_ids : []) {
        if (confirmed.has(slotId)) ids.add(slotId);
      }
    }
    if (requirement.kind === "bound_fact" || requirement.kind === "bound_dimension") {
      for (const slotId of bound) if (confirmed.has(slotId)) ids.add(slotId);
    }
    if (requirement.kind === "any_of") {
      for (const sub of Array.isArray(requirement.of) ? requirement.of : []) collect(sub);
    }
  };
  for (const requirement of (isPlainObject(shot) && Array.isArray(shot.dependencies)
    ? shot.dependencies : [])) collect(requirement);
  return [...ids].sort();
}

/**
 * 按用途的就绪投影（消费者可见，V2.R6.2）：给出这张图能否本地准备、缺什么、缺在哪个槽位/角色。
 * 不要求全部槽位都填；只按这张图实际消费的事实与参考图角色算。
 * @param {unknown} shot
 * @param {import("./type-contracts.js").EvalContext | null | undefined} context
 * @param {SuiteRegistryView | null | undefined} [registry]
 * @returns {{shot_id: unknown, template_id: unknown, role_id: unknown, ready: boolean, blocking: import("./type-contracts.js").DependencyBlocking[], consumed_slot_ids: string[], missing_fact_ids: string[], missing_asset_roles: string[]}}
 */
export function shotReadiness(shot, context, registry) {
  const evaluation = evaluateShot(shot, context, registry);
  const confirmedIds = (Array.isArray(context && context.facts)
    ? (/** @type {{facts: ReadonlyArray<{slot_id: string, status: string, value?: unknown}>}} */ (context)).facts
    : [])
    .filter((item) => isPlainObject(item) && item.status === CONFIRMED_FACT_STATUS)
    .map((item) => item.slot_id);
  /** @type {Set<string>} */
  const missingFacts = new Set();
  /** @type {Set<string>} */
  const missingAssets = new Set();
  for (const item of evaluation.blocking) {
    const missing = Array.isArray(item.missing) ? item.missing : [];
    if (item.kind === "asset_role") {
      for (const role of missing) missingAssets.add(role);
    } else {
      for (const slotId of missing) missingFacts.add(slotId);
    }
  }
  return {
    shot_id: evaluation.shot_id,
    template_id: evaluation.template_id,
    role_id: isPlainObject(shot) ? (shot.role_id === undefined ? null : shot.role_id) : null,
    ready: evaluation.satisfied,
    blocking: evaluation.blocking.map((item) => ({
      kind: item.kind, reason: item.reason, missing: [...(item.missing || [])],
    })),
    consumed_slot_ids: consumedSlotIdsOf(shot, confirmedIds),
    missing_fact_ids: [...missingFacts].sort(),
    missing_asset_roles: [...missingAssets].sort(),
  };
}

/**
 * 全模板的就绪推荐（按 order 排序；逐模板求值依赖，附精确阻断）。
 * @param {import("./type-contracts.js").EvalContext | null | undefined} context
 * @param {RecommendOptions | undefined} [options]
 * @returns {import("./type-contracts.js").PlanRecommendation}
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
 * 自定义 Shot 草稿（冻结；shot_id 为 null，由计划分配真实 id）。
 * @param {{label?: string, intent?: string, factSlotIds?: ReadonlyArray<string>} | undefined} [args]
 * @returns {Readonly<ShotRecord>}
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
 * 一张 Shot 草案的注册表机检（角色/模板/绑定/依赖形状）；返回问题列表（空 = 合法）。
 * @param {unknown} shot
 * @param {SuiteRegistryView | null | undefined} [registry]
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkShotDraft(shot, registry) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
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

/**
 * @param {import("./type-contracts.js").DomainProblem[]} problems
 * @param {Record<string, unknown>} object
 * @param {"role" | "template" | "dependency"} kind
 * @param {string} path
 * @returns {void}
 */
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

/**
 * 依赖数组（含嵌套 any_of）的形状机检；返回问题列表。
 * @param {unknown} dependencies
 * @param {string} path
 * @param {number} [depth]
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
function validateDependencies(dependencies, path, depth = 0) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
  const problems = [];
  if (!Array.isArray(dependencies)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "dependencies 必须是数组。");
    return problems;
  }
  dependencies.forEach(/** @param {FrozenShotDependency} requirement @param {number} index */ (requirement, index) => {
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
      if (!REFERENCE_ROLES.includes(/** @type {import("./type-contracts.js").ReferenceRole} */ (requirement.role))) {
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
 * 注册表整体机检：角色/模板/依赖的字段消费者、唯一性、顺序与引用完整性。
 * @param {SuiteRegistryView | null | undefined} [registry]
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function validateSuiteRegistry(registry) {
  const { roles, templates } = registryOf(registry);
  /** @type {import("./type-contracts.js").DomainProblem[]} */
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
