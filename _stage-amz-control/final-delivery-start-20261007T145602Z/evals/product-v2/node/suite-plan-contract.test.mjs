/**
 * V2.3.1 套图注册表契约测试（Node 原生进程，非 Mock）：
 * 图片角色、Shot 模板与条件依赖语言。
 *
 * 正向：注册表自检、参考图角色词表、模板投影、六类依赖求值、推荐排序与必需阻断、
 * 自定义 Shot 与草稿校验。
 * 反向（故意让守卫变红）：重复 id、未知角色、custom 模板、order 非法、非核心事实、
 * 空/重复 fact_any、any_of 递归限深、多余参数、未知依赖、无登记字段、无消费者角色、
 * custom 角色不唯一；R11 逐字段变异——FIELD_CONSUMERS 指名的消费者输出必须变化。
 *
 * 直接运行：node --test evals/product-v2/node/
 */

import {
  BLOCKING_FACT_STATUSES,
  CONFIRMED_FACT_STATUS,
  CORE_SLOT_IDS,
  CUSTOM_ROLE_ID,
  DEPENDENCY_KINDS,
  DOMAIN_ERROR_CODES,
  FIELD_CONSUMERS,
  IMAGE_ROLES,
  MAX_DEPENDENCY_DEPTH,
  REFERENCE_ROLES,
  REGISTRY_FIELDS,
  SHOT_TEMPLATES,
  SUITE_REGISTRY_SCHEMA_VERSION,
  checkShotDraft,
  createCustomShot,
  describeRegistry,
  describeRole,
  describeTemplate,
  evaluateDependencies,
  evaluateShot,
  instantiateTemplate,
  recommendPlan,
  templateDefinition,
  validateSuiteRegistry,
} from "../../../app/product_v2/domain/index.js";

import { expect, expectCode, serializeError } from "./harness-core.mjs";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

function json(value) {
  return JSON.stringify(value);
}

function cloneRegistry() {
  return {
    roles: structuredClone([...IMAGE_ROLES]),
    templates: structuredClone([...SHOT_TEMPLATES]),
  };
}

function roleAt(registry, roleId) {
  const role = registry.roles.find((item) => item.role_id === roleId);
  expect(Boolean(role), "测试假设角色存在：" + roleId);
  return role;
}

function templateAt(registry, templateId) {
  const template = registry.templates.find((item) => item.template_id === templateId);
  expect(Boolean(template), "测试假设模板存在：" + templateId);
  return template;
}

function fact(slotId, status) {
  return { slot_id: slotId, status, value: slotId + "-值" };
}

/** 结构性尺寸事实（V2.R6.2）：对象/轴向/有限正数/单位/来源依据，缺一即非尺寸。 */
function dimensionFact(slotId, status) {
  return {
    slot_id: slotId, status,
    value: [{ object: "瓶身", axis: "height", value: 21.5, unit: "cm", source_basis: "人工测量" }],
  };
}

function problemsMatching(problems, pathPart, textPart) {
  return problems.filter((item) => String(item.path || "").includes(pathPart)
    && String(item.message || "").includes(textPart));
}

function deepAnyOf(levels, leaf) {
  let node = leaf;
  for (let index = 0; index < levels; index += 1) {
    node = { kind: "any_of", of: [node] };
  }
  return node;
}

/* ------------------------------------------------------------ R01..R03 基础 */

test("R01", "内置注册表自检零问题；依赖谓词可求值（增删谓词不靠计数发现）", () => {
  const problems = validateSuiteRegistry();
  expect(problems.length === 0, "内置注册表不干净：" + json(problems.slice(0, 3)));
  const explicit = validateSuiteRegistry(cloneRegistry());
  expect(explicit.length === 0, "克隆的内置注册表也应零问题：" + json(explicit.slice(0, 3)));
  const described = describeRegistry();
  expect(described.schema_version === SUITE_REGISTRY_SCHEMA_VERSION,
    "schema_version 不一致：" + String(described.schema_version));
  expect(json(described.dependency_kinds) === json([...DEPENDENCY_KINDS]),
    "依赖词表与常量不一致。");
  return { problems: problems.length, roles: IMAGE_ROLES.length, templates: SHOT_TEMPLATES.length };
});

test("R02", "模板引用的参考图角色都在词表内；对比图依赖 competitor 角色", () => {
  expect(Object.isFrozen(REFERENCE_ROLES), "REFERENCE_ROLES 应是冻结的。");
  const dependencyRoles = [];
  for (const template of SHOT_TEMPLATES) {
    for (const requirement of template.dependencies) {
      if (requirement.kind === "asset_role") {
        dependencyRoles.push({ template: template.template_id, role: requirement.role });
      }
    }
  }
  expect(dependencyRoles.length >= 2, "至少应有两类参考图依赖。");
  for (const item of dependencyRoles) {
    expect(REFERENCE_ROLES.includes(item.role),
      "模板 " + item.template + " 引用了词表外的角色：" + String(item.role));
  }
  expect(dependencyRoles.some((item) => item.role === "competitor"),
    "对比图必须依赖 competitor 角色。");
  return { roles: [...REFERENCE_ROLES], asset_role_dependencies: dependencyRoles };
});

test("R03", "每个模板都能完整投影：角色、名称、意图、依赖文案非空", () => {
  let count = 0;
  for (const template of SHOT_TEMPLATES) {
    const described = describeTemplate(template.template_id);
    expect(Boolean(described), "模板无法投影：" + template.template_id);
    expect(Boolean(described.role_label), "模板缺角色名称：" + template.template_id);
    expect(described.label.trim().length > 0, "模板缺名称：" + template.template_id);
    expect(described.intent.trim().length > 0, "模板缺意图：" + template.template_id);
    expect(described.dependency_text.length === described.dependencies.length,
      "依赖文案数量应与依赖数量一致：" + template.template_id);
    for (const text of described.dependency_text) {
      expect(typeof text === "string" && text.trim().length > 0,
        "依赖文案为空：" + template.template_id);
    }
    count += 1;
  }
  const orders = SHOT_TEMPLATES.map((item) => item.order);
  expect(json(orders) === json([...orders].sort((left, right) => left - right)),
    "内置模板 order 应升序：" + json(orders));
  expect(new Set(orders).size === orders.length, "order 不允许重复。");
  return { templates: count, orders };
});

/* ------------------------------------------------- R04..R09 依赖求值语义 */

test("R04", "主图依赖主参考图：缺失阻断、补齐通过，原因精确到角色", () => {
  const dependencies = templateDefinition("main_clean").dependencies;
  const missing = evaluateDependencies(dependencies, { facts: [], assets: [] });
  expect(!missing.satisfied && missing.blocking.length === 1, "缺 primary 时应恰好一条阻断。");
  expect(missing.blocking[0].kind === "asset_role"
    && missing.blocking[0].reason.includes("primary"),
    "阻断原因必须点名 primary：" + json(missing.blocking));
  const withPrimary = evaluateDependencies(dependencies,
    { facts: [], assets: [{ role: "primary", sha256: "a".repeat(64) }] });
  expect(withPrimary.satisfied && withPrimary.blocking.length === 0, "有 primary 后主图应满足。");
  return { blocked_reason: missing.blocking[0].reason };
});

test("R05", "事实依赖只认 confirmed；其余每种状态都给出精确原因", () => {
  expect(CONFIRMED_FACT_STATUS === "confirmed", "确认状态词必须是 confirmed。");
  const dependencies = templateDefinition("infographic_benefits").dependencies;
  const absent = evaluateDependencies(dependencies, { facts: [], assets: [] });
  expect(!absent.satisfied && absent.blocking[0].reason.includes("signature_features"),
    "缺事实应点名槽位：" + json(absent.blocking));
  const perStatus = {};
  for (const status of BLOCKING_FACT_STATUSES) {
    const result = evaluateDependencies(dependencies,
      { facts: [fact("signature_features", status)], assets: [] });
    expect(!result.satisfied, "状态 " + status + " 不应满足事实依赖。");
    expect(result.blocking[0].reason.includes(status),
      "阻断原因应写明当前状态 " + status + "：" + json(result.blocking));
    perStatus[status] = result.blocking[0].reason;
  }
  expect(BLOCKING_FACT_STATUSES.includes("superseded") && BLOCKING_FACT_STATUSES.includes("unknown"),
    "阻断状态词表应包含 superseded 与 unknown。");
  const confirmed = evaluateDependencies(dependencies,
    { facts: [fact("signature_features", "confirmed")], assets: [] });
  expect(confirmed.satisfied, "confirmed 应满足事实依赖。");
  return { blocking_statuses: [...BLOCKING_FACT_STATUSES], absent_reason: absent.blocking[0].reason };
});

test("R06", "尺寸图只认结构化尺寸：自由文本/标量不得冒充测量", () => {
  const dependencies = templateDefinition("size_dimensions").dependencies;
  const freeText = evaluateDependencies(dependencies,
    { facts: [fact("size_summary", "confirmed")], assets: [] });
  expect(!freeText.satisfied, "确认的自由文本 size_summary 也不得满足尺寸图。");
  expect(freeText.blocking[0].kind === "any_of", "any_of 应整体报告为一条阻断。");
  const coreProposed = evaluateDependencies(dependencies,
    { facts: [dimensionFact("size_dimensions", "proposed")], assets: [] });
  expect(!coreProposed.satisfied, "未确认的结构化尺寸不应满足。");
  const coreConfirmed = evaluateDependencies(dependencies,
    { facts: [dimensionFact("size_dimensions", "confirmed")], assets: [] });
  expect(coreConfirmed.satisfied, "结构化尺寸确认后尺寸图应满足。");
  const boundUnconfirmed = evaluateDependencies(dependencies,
    { facts: [dimensionFact("bottle_height", "proposed")], assets: [], bound_fact_ids: ["bottle_height"] });
  expect(!boundUnconfirmed.satisfied, "绑定尺寸未确认时应阻断。");
  const boundFreeText = evaluateDependencies(dependencies,
    { facts: [fact("bottle_height", "confirmed")], assets: [], bound_fact_ids: ["bottle_height"] });
  expect(!boundFreeText.satisfied, "绑定的自由文本/标量事实不得冒充尺寸测量。");
  const boundConfirmed = evaluateDependencies(dependencies,
    { facts: [dimensionFact("bottle_height", "confirmed")], assets: [],
      bound_fact_ids: ["bottle_height"] });
  expect(boundConfirmed.satisfied, "绑定的结构化尺寸确认后应满足。");
  const unbound = evaluateDependencies(dependencies,
    { facts: [dimensionFact("bottle_height", "confirmed")], assets: [] });
  expect(!unbound.satisfied, "确认但未绑定不得算数。");
  return { free_text_reason: freeText.blocking[0].reason, unbound_reason: unbound.blocking[0].reason };
});

test("R07", "对比图要竞品参考图 + 已确认特征；两条都缺都要逐条说清", () => {
  const dependencies = templateDefinition("comparison_competitor").dependencies;
  const noCompetitor = evaluateDependencies(dependencies,
    { facts: [fact("signature_features", "confirmed")], assets: [{ role: "primary" }] });
  expect(!noCompetitor.satisfied && noCompetitor.blocking.length === 1,
    "缺竞品图时应恰好一条阻断：" + json(noCompetitor.blocking));
  expect(noCompetitor.blocking[0].reason.includes("competitor"),
    "阻断原因要点名 competitor：" + json(noCompetitor.blocking));
  const noFacts = evaluateDependencies(dependencies,
    { facts: [], assets: [{ role: "primary" }, { role: "competitor" }] });
  expect(!noFacts.satisfied && noFacts.blocking[0].reason.includes("signature_features"),
    "缺确认特征要单独阻断：" + json(noFacts.blocking));
  const bothMissing = evaluateDependencies(dependencies, { facts: [], assets: [] });
  expect(bothMissing.blocking.length === 2, "两条依赖都要报告：" + json(bothMissing.blocking));
  const ok = evaluateDependencies(dependencies,
    { facts: [fact("signature_features", "confirmed")], assets: [{ role: "competitor" }] });
  expect(ok.satisfied, "竞品图 + 确认特征应满足对比图。");
  return { blocking_kinds: bothMissing.blocking.map((item) => item.kind) };
});

test("R08", "成分图只认该图绑定的已确认事实；确认但未绑定不算数", () => {
  const dependencies = templateDefinition("ingredient_composition").dependencies;
  const unbound = evaluateDependencies(dependencies,
    { facts: [fact("ingredient_list", "confirmed")], assets: [] });
  expect(!unbound.satisfied, "确认但未绑定的事实不应满足成分图。");
  expect(unbound.blocking[0].reason.includes("绑定"),
    "阻断原因应说明还没绑定：" + json(unbound.blocking));
  const boundUnconfirmed = evaluateDependencies(dependencies,
    { facts: [fact("ingredient_list", "proposed")], assets: [], bound_fact_ids: ["ingredient_list"] });
  expect(!boundUnconfirmed.satisfied, "绑定事实未确认应阻断。");
  expect(boundUnconfirmed.blocking[0].reason.includes("ingredient_list"),
    "阻断原因要点名绑定事实：" + json(boundUnconfirmed.blocking));
  const boundConfirmed = evaluateDependencies(dependencies,
    { facts: [fact("ingredient_list", "confirmed")], assets: [], bound_fact_ids: ["ingredient_list"] });
  expect(boundConfirmed.satisfied, "绑定事实确认后应满足。");
  const mixedBound = evaluateDependencies(dependencies,
    { facts: [fact("ingredient_a", "proposed"), fact("ingredient_b", "confirmed")],
      assets: [], bound_fact_ids: ["ingredient_a", "ingredient_b"] });
  expect(mixedBound.satisfied, "多条绑定里有一条 confirmed 即可。");
  return { unbound_reason: unbound.blocking[0].reason };
});

test("R09", "自定义 Shot 合法；未知角色、空名称、非法绑定逐项被拒", async () => {
  const custom = createCustomShot({ label: "赠品展示", intent: "展示随附赠品",
    factSlotIds: ["package_contents"] });
  expect(custom.role_id === CUSTOM_ROLE_ID && custom.custom === true && custom.template_id === null,
    "自定义图身份字段不正确：" + json(custom));
  expect(json(custom.dependencies) === "[]", "自定义图没有注册表依赖。");
  const invalidLabel = await expectCode(() => createCustomShot({ label: "   " }),
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "空名称的自定义图");
  const cleanDraft = checkShotDraft(instantiateTemplate("main_clean", { shotId: "s1" }));
  expect(cleanDraft.length === 0, "模板实例应通过草稿校验：" + json(cleanDraft));
  const customDraft = checkShotDraft(custom);
  expect(customDraft.length === 0, "合法自定义图应通过草稿校验：" + json(customDraft));
  const withTemplate = checkShotDraft({ ...custom, template_id: "main_clean" });
  expect(problemsMatching(withTemplate, "$.template_id", "自定义图不来自模板").length === 1,
    "自定义图带 template_id 应被拒：" + json(withTemplate));
  const ghostRole = checkShotDraft({ role_id: "ghost", template_id: null, label: "x",
    dependencies: [], fact_slot_ids: [] });
  expect(problemsMatching(ghostRole, "$.role_id", "不在注册表内").length === 1,
    "未知角色应被拒：" + json(ghostRole));
  const ghostTemplate = checkShotDraft({ role_id: "main", template_id: "ghost_template",
    label: "x", dependencies: [], fact_slot_ids: [] });
  expect(problemsMatching(ghostTemplate, "$.template_id", "已登记模板").length === 1,
    "未知模板应被拒：" + json(ghostTemplate));
  const mismatch = checkShotDraft({ ...instantiateTemplate("main_clean"), role_id: "detail" });
  expect(problemsMatching(mismatch, "$.role_id", "必须与模板一致").length === 1,
    "角色与模板不一致应被拒：" + json(mismatch));
  const badBinding = checkShotDraft({ ...instantiateTemplate("main_clean"),
    fact_slot_ids: ["Bad-ID"] });
  expect(problemsMatching(badBinding, "$.fact_slot_ids[0]", "合法 slot_id").length === 1,
    "非法绑定应被拒：" + json(badBinding));
  const dupBinding = checkShotDraft({ ...instantiateTemplate("main_clean"),
    fact_slot_ids: ["brand", "brand"] });
  expect(problemsMatching(dupBinding, "$.fact_slot_ids[1]", "不允许重复").length === 1,
    "重复绑定应被拒：" + json(dupBinding));
  const notArray = checkShotDraft({ ...instantiateTemplate("main_clean"), fact_slot_ids: "brand" });
  expect(problemsMatching(notArray, "$.fact_slot_ids", "必须是数组").length === 1,
    "非数组绑定应被拒：" + json(notArray));
  return { invalid_label: invalidLabel.message };
});

/* ---------------------------------------------- R10 反向探针：守卫必须能变红 */

const REVERSE_MUTATIONS = [
  { id: "dup_role_id", why: "角色 id 重复", path: ".role_id", text: "role_id 重复",
    mutate(registry) { roleAt(registry, "detail").role_id = "main"; } },
  { id: "role_id_invalid", why: "角色 id 形状非法", path: "", text: "role_id 必须是合法标识",
    mutate(registry) { roleAt(registry, "detail").role_id = "BadID"; } },
  { id: "role_label_missing", why: "角色缺名称", path: "", text: "角色必须有名称",
    mutate(registry) { roleAt(registry, "detail").label = ""; } },
  { id: "role_unused", why: "角色没有模板引用（没有消费者）", path: "", text: "没有被任何模板引用",
    mutate(registry) {
      registry.templates = registry.templates.filter((item) => item.template_id !== "detail_material");
    } },
  { id: "custom_not_unique", why: "custom 角色不唯一", path: "$.roles", text: "恰有一个 custom 角色",
    mutate(registry) { roleAt(registry, "main").custom = true; } },
  { id: "dup_template_id", why: "模板 id 重复", path: ".template_id", text: "template_id 重复",
    mutate(registry) { templateAt(registry, "infographic_benefits").template_id = "main_clean"; } },
  { id: "template_unknown_role", why: "模板引用未登记角色", path: ".role_id", text: "未登记的角色",
    mutate(registry) { templateAt(registry, "main_clean").role_id = "ghost"; } },
  { id: "template_custom_role", why: "custom 角色出现在模板", path: ".role_id",
    text: "自定义图不通过注册表模板提供",
    mutate(registry) {
      registry.templates.push({ template_id: "custom_extra", role_id: "custom", label: "x",
        intent: "y", required: false, order: 999, dependencies: [] });
    } },
  { id: "template_label_missing", why: "模板缺名称", path: "", text: "模板必须有名称",
    mutate(registry) { templateAt(registry, "main_clean").label = ""; } },
  { id: "template_intent_missing", why: "模板缺拍摄意图", path: "", text: "模板必须有拍摄意图",
    mutate(registry) { templateAt(registry, "main_clean").intent = ""; } },
  { id: "template_required_invalid", why: "required 不是布尔值", path: ".required", text: "required 必须是布尔值",
    mutate(registry) { templateAt(registry, "main_clean").required = "yes"; } },
  { id: "order_duplicate", why: "order 重复", path: ".order", text: "order 不允许重复",
    mutate(registry) { templateAt(registry, "infographic_benefits").order = 10; } },
  { id: "order_nonpositive", why: "order 非正", path: ".order", text: "order 必须是正整数",
    mutate(registry) { templateAt(registry, "infographic_benefits").order = 0; } },
  { id: "order_fraction", why: "order 非整数", path: ".order", text: "order 必须是正整数",
    mutate(registry) { templateAt(registry, "infographic_benefits").order = 20.5; } },
  { id: "unregistered_field", why: "模板带未登记字段（没有消费者）", path: ".priority", text: "没有登记",
    mutate(registry) { templateAt(registry, "main_clean").priority = 1; } },
  { id: "dependencies_not_array", why: "dependencies 不是数组", path: "", text: "dependencies 必须是数组",
    mutate(registry) { templateAt(registry, "main_clean").dependencies = null; } },
  { id: "dependency_not_object", why: "依赖不是对象", path: "", text: "依赖必须是对象",
    mutate(registry) { templateAt(registry, "main_clean").dependencies = [42]; } },
  { id: "dependency_unknown_kind", why: "未知依赖类型", path: "", text: "未知依赖类型",
    mutate(registry) { templateAt(registry, "main_clean").dependencies = [{ kind: "or_else" }]; } },
  { id: "dependency_extra_param", why: "依赖带多余参数", path: "", text: "不接受参数 note",
    mutate(registry) {
      templateAt(registry, "main_clean").dependencies = [{ kind: "asset_role", role: "primary", note: "x" }];
    } },
  { id: "bound_dimension_extra_param", why: "bound_dimension 不接受参数", path: "", text: "不接受参数 note",
    mutate(registry) {
      templateAt(registry, "size_dimensions").dependencies =
        [{ kind: "bound_dimension", note: "x" }];
    } },
  { id: "asset_role_unknown", why: "参考图角色不在词表", path: "", text: "参考图角色不在词表内",
    mutate(registry) { templateAt(registry, "main_clean").dependencies = [{ kind: "asset_role", role: "ghost_role" }]; } },
  { id: "fact_not_core", why: "事实依赖引用非核心槽位", path: "", text: "fact 依赖必须引用核心槽位",
    mutate(registry) {
      templateAt(registry, "infographic_benefits").dependencies = [{ kind: "fact", slot_id: "ghost_fact" }];
    } },
  { id: "fact_any_empty", why: "fact_any 为空", path: "", text: "至少要有一个核心槽位",
    mutate(registry) { templateAt(registry, "detail_material").dependencies = [{ kind: "fact_any", slot_ids: [] }]; } },
  { id: "fact_any_duplicate", why: "fact_any 槽位重复", path: "", text: "槽位不允许重复",
    mutate(registry) {
      templateAt(registry, "detail_material").dependencies = [{ kind: "fact_any", slot_ids: ["brand", "brand"] }];
    } },
  { id: "fact_any_not_core", why: "fact_any 引用非核心槽位", path: "", text: "只能引用核心槽位",
    mutate(registry) {
      templateAt(registry, "detail_material").dependencies = [{ kind: "fact_any", slot_ids: ["ghost_fact"] }];
    } },
  { id: "any_of_too_deep", why: "any_of 嵌套超过限深", path: "", text: "依赖嵌套超过",
    mutate(registry) {
      templateAt(registry, "size_dimensions").dependencies =
        [deepAnyOf(MAX_DEPENDENCY_DEPTH + 1, { kind: "fact", slot_id: "brand" })];
    } },
];

test("R10", "反向探针：每条注册表守卫都必须能变红", () => {
  const baseline = validateSuiteRegistry(cloneRegistry());
  expect(baseline.length === 0, "变异前的克隆注册表必须零问题：" + json(baseline.slice(0, 3)));
  const boundary = cloneRegistry();
  templateAt(boundary, "size_dimensions").dependencies =
    [deepAnyOf(MAX_DEPENDENCY_DEPTH, { kind: "fact", slot_id: "brand" })];
  const boundaryProblems = validateSuiteRegistry(boundary);
  expect(boundaryProblems.length === 0,
    "限深边界内（" + MAX_DEPENDENCY_DEPTH + " 层）应合法：" + json(boundaryProblems.slice(0, 3)));
  const observed = [];
  for (const probe of REVERSE_MUTATIONS) {
    const registry = cloneRegistry();
    probe.mutate(registry);
    const problems = validateSuiteRegistry(registry);
    expect(problems.length > 0, "守卫没有变红：" + probe.id);
    expect(problemsMatching(problems, probe.path, probe.text).length > 0,
      "没有找到预期问题：" + probe.id + " → [" + probe.path + "] / " + probe.text
        + "，实际：" + json(problems.slice(0, 3)));
    observed.push(probe.id);
  }
  return { probes: observed, boundary_depth: MAX_DEPENDENCY_DEPTH };
});

/* ------------------------------------------ R11 改数据探针：字段必须有消费者 */

const FIELD_PROBES = {
  "role.role_id": {
    consumer: "describeRole",
    mutate(registry) { roleAt(registry, "main").role_id = "main_v2"; },
    snapshot(registry) { return describeRole("main", registry); },
  },
  "role.label": {
    consumer: "describeRole",
    mutate(registry) { roleAt(registry, "main").label = "主图·改"; },
    snapshot(registry) { return describeRole("main", registry); },
  },
  "role.purpose": {
    consumer: "describeRole",
    mutate(registry) { roleAt(registry, "main").purpose = "改过的用途"; },
    snapshot(registry) { return describeRole("main", registry); },
  },
  "role.custom": {
    consumer: "validateSuiteRegistry",
    mutate(registry) { roleAt(registry, "main").custom = true; },
    snapshot(registry) { return validateSuiteRegistry(registry); },
  },
  "template.template_id": {
    consumer: "describeTemplate",
    mutate(registry) { templateAt(registry, "main_clean").template_id = "main_clean_v2"; },
    snapshot(registry) { return describeTemplate("main_clean", registry); },
  },
  "template.role_id": {
    consumer: "describeTemplate",
    mutate(registry) { templateAt(registry, "main_clean").role_id = "detail"; },
    snapshot(registry) { return describeTemplate("main_clean", registry); },
  },
  "template.label": {
    consumer: "describeTemplate",
    mutate(registry) { templateAt(registry, "main_clean").label = "主图·改"; },
    snapshot(registry) { return describeTemplate("main_clean", registry); },
  },
  "template.intent": {
    consumer: "describeTemplate",
    mutate(registry) { templateAt(registry, "main_clean").intent = "改过的意图"; },
    snapshot(registry) { return describeTemplate("main_clean", registry); },
  },
  "template.required": {
    consumer: "recommendPlan",
    mutate(registry) { templateAt(registry, "infographic_benefits").required = true; },
    snapshot(registry) {
      return recommendPlan({ facts: [], assets: [{ role: "primary" }] }, { registry })
        .required_blocked;
    },
  },
  "template.order": {
    consumer: "recommendPlan",
    mutate(registry) { templateAt(registry, "infographic_benefits").order = 5; },
    snapshot(registry) {
      return recommendPlan({ facts: [], assets: [] }, { registry }).instances
        .map((item) => item.template_id);
    },
  },
  "template.dependencies": {
    consumer: "evaluateDependencies",
    mutate(registry) { templateAt(registry, "main_clean").dependencies = []; },
    snapshot(registry) {
      return evaluateDependencies(templateAt(registry, "main_clean").dependencies,
        { facts: [], assets: [] });
    },
  },
  "dependency.kind": {
    consumer: "evaluateDependencies",
    mutate(registry) {
      templateAt(registry, "main_clean").dependencies = [{ kind: "fact", slot_id: "product_name" }];
    },
    snapshot(registry) {
      return evaluateDependencies(templateAt(registry, "main_clean").dependencies,
        { facts: [], assets: [{ role: "primary" }] });
    },
  },
  "dependency.role": {
    consumer: "evaluateDependencies",
    mutate(registry) { templateAt(registry, "main_clean").dependencies[0].role = "competitor"; },
    snapshot(registry) {
      return evaluateDependencies(templateAt(registry, "main_clean").dependencies,
        { facts: [], assets: [{ role: "primary" }] });
    },
  },
  "dependency.slot_id": {
    consumer: "evaluateDependencies",
    mutate(registry) {
      templateAt(registry, "infographic_benefits").dependencies[0].slot_id = "product_category";
    },
    snapshot(registry) {
      return evaluateDependencies(templateAt(registry, "infographic_benefits").dependencies,
        { facts: [fact("product_category", "confirmed")], assets: [] });
    },
  },
  "dependency.slot_ids": {
    consumer: "evaluateDependencies",
    mutate(registry) { templateAt(registry, "detail_material").dependencies[0].slot_ids = ["brand"]; },
    snapshot(registry) {
      return evaluateDependencies(templateAt(registry, "detail_material").dependencies,
        { facts: [fact("key_material", "confirmed")], assets: [] });
    },
  },
  "dependency.of": {
    consumer: "evaluateDependencies",
    mutate(registry) {
      templateAt(registry, "size_dimensions").dependencies[0].of = [{ kind: "fact", slot_id: "brand" }];
    },
    snapshot(registry) {
      return evaluateDependencies(templateAt(registry, "size_dimensions").dependencies,
        { facts: [fact("size_summary", "confirmed")], assets: [] });
    },
  },
};

test("R11", "改数据探针：每个登记字段都必须有消费者，改动必须让它变样", () => {
  const declared = [];
  for (const kind of Object.keys(REGISTRY_FIELDS)) {
    for (const field of REGISTRY_FIELDS[kind]) {
      const key = kind + "." + field;
      declared.push(key);
      expect(Boolean(FIELD_CONSUMERS[key]), "字段没有登记消费者：" + key);
      expect(Boolean(FIELD_PROBES[key]), "字段缺少改数据探针（新增字段必须同时补消费者与探针）：" + key);
      expect(FIELD_PROBES[key].consumer === FIELD_CONSUMERS[key],
        "探针指名的消费者与 FIELD_CONSUMERS 不一致：" + key);
    }
  }
  const extra = Object.keys(FIELD_PROBES).filter((key) => !declared.includes(key));
  expect(extra.length === 0, "探针引用了未登记字段：" + json(extra));
  const observed = [];
  for (const key of declared) {
    const probe = FIELD_PROBES[key];
    const before = probe.snapshot(cloneRegistry());
    const mutated = cloneRegistry();
    probe.mutate(mutated);
    const after = probe.snapshot(mutated);
    expect(json(before) !== json(after),
      "改动 " + key + " 后消费者 " + probe.consumer + " 的输出没有变化——字段没有真实消费者。");
    observed.push({ field: key, consumer: probe.consumer });
  }
  return { fields: observed.length, consumers: observed };
});

/* -------------------------------------------- R12..R13 推荐计划与按图求值 */

test("R12", "推荐计划按 order 有序；必需阻断保留在列表里并给原因", () => {
  const empty = recommendPlan({ facts: [], assets: [] });
  const expectedOrder = [...SHOT_TEMPLATES].sort((left, right) => left.order - right.order)
    .map((item) => item.template_id);
  expect(json(empty.instances.map((item) => item.template_id)) === json(expectedOrder),
    "实例顺序必须按 order：" + json(empty.instances.map((item) => item.template_id)));
  expect(json(empty.satisfiable) === "[]", "空上下文不应有可满足模板：" + json(empty.satisfiable));
  expect(json(empty.blocked) === json(expectedOrder), "空上下文所有模板都应被阻断：" + json(empty.blocked));
  expect(json(empty.required_blocked) === json(["main_clean"]),
    "无参考图时必需主图应被阻断并报告：" + json(empty.required_blocked));
  for (const instance of empty.instances) {
    expect(instance.blocking.length > 0, "被阻断实例必须携带原因：" + instance.template_id);
  }
  const facts = CORE_SLOT_IDS.map((slotId) => fact(slotId, "confirmed"));
  const assets = [{ role: "primary" }, { role: "competitor" }];
  const full = recommendPlan({ facts, assets });
  expect(json(full.required_blocked) === "[]", "资料齐全时不应有必需阻断：" + json(full.required_blocked));
  expect(json(full.blocked) === json(["ingredient_composition"]),
    "只有成分图应被阻断（未绑定事实）：" + json(full.blocked));
  const unconfirmedBinding = recommendPlan({ facts, assets },
    { bound_fact_ids_by_template: { ingredient_composition: ["ingredient_list"] } });
  expect(json(unconfirmedBinding.blocked) === json(["ingredient_composition"]),
    "只绑定未确认事实仍然阻断：" + json(unconfirmedBinding.blocked));
  const confirmedBinding = recommendPlan(
    { facts: [...facts, fact("ingredient_list", "confirmed")], assets },
    { bound_fact_ids_by_template: { ingredient_composition: ["ingredient_list"] } });
  expect(confirmedBinding.satisfiable.length === SHOT_TEMPLATES.length,
    "全部满足时应 8/8：" + json(confirmedBinding.blocked));
  return { required_blocked: empty.required_blocked, full_blocked: full.blocked };
});

test("R13", "evaluateShot 用图自身绑定事实求值：绑定与模板依赖一起生效", () => {
  const shot = instantiateTemplate("size_dimensions",
    { shotId: "s-size", factSlotIds: ["bottle_height"] });
  expect(shot.shot_id === "s-size" && json(shot.fact_slot_ids) === json(["bottle_height"]),
    "实例化字段不正确：" + json(shot));
  const unbound = evaluateShot({ ...shot, fact_slot_ids: [] },
    { facts: [fact("bottle_height", "confirmed")], assets: [] });
  expect(!unbound.satisfied, "没有绑定时不得借用别处确认的事实。");
  const boundProposed = evaluateShot(shot, { facts: [dimensionFact("bottle_height", "proposed")], assets: [] });
  expect(!boundProposed.satisfied, "绑定事实未确认应阻断。");
  const boundFreeText = evaluateShot(shot, { facts: [fact("bottle_height", "confirmed")], assets: [] });
  expect(!boundFreeText.satisfied, "绑定的自由文本事实不得满足尺寸图。");
  const boundConfirmed = evaluateShot(shot,
    { facts: [dimensionFact("bottle_height", "confirmed")], assets: [] });
  expect(boundConfirmed.satisfied && boundConfirmed.shot_id === "s-size"
    && boundConfirmed.template_id === "size_dimensions",
    "绑定确认后应满足并保留身份：" + json(boundConfirmed));
  const customShot = createCustomShot({ label: "赠品展示" });
  const customEvaluation = evaluateShot(customShot, { facts: [], assets: [] });
  expect(customEvaluation.satisfied && customEvaluation.blocking.length === 0,
    "自定义图没有注册表依赖，由人工审核把关：" + json(customEvaluation));
  const mainShot = instantiateTemplate("main_clean", { shotId: "s-main" });
  const mainBlocked = evaluateShot(mainShot, { facts: [], assets: [] });
  expect(!mainBlocked.satisfied && mainBlocked.blocking[0].reason.includes("primary"),
    "模板依赖在没有参考图时也要阻断：" + json(mainBlocked));
  return { evaluated: ["size_dimensions", "custom", "main_clean"] };
});

/* ---------------------------------------------------------------- 运行器 */

function render(results) {
  const node = document.getElementById("results");
  if (node) node.textContent = JSON.stringify(results, null, 2);
}


/* Node 原生运行器：与原浏览器版同一批 cases，断言不改写。 */
import nodeTest from "node:test";
for (const item of cases) {
  nodeTest(`${item.id} :: ${item.title}`, { timeout: 60000 }, async () => { await item.run(); });
}
