/**
 * V2.3.2 套图编辑器契约测试（真实 Chromium，非 Mock）：
 * SuitePlan 文档的形状、操作与不变量。
 *
 * 正向：推荐播种、添加模板 / 自定义、复制、删除、排序、逐图依赖投影。
 * 反向（故意让守卫变红）：空计划、重复 id、未知角色、custom 越界、删除最后一张必需图、
 * 边界排序、非法 delta、失败原子（被拒操作不得改动输入计划）。
 *
 * 结果写到 window.__V2_SUITE_EDITOR_RESULTS__，由 tools/verify_v2_3_2_suite_editor.py 读取。
 */

import {
  DOMAIN_ERROR_CODES,
  MAX_SHOTS,
  MIN_SHOTS,
  SUITE_PLAN_SCHEMA_VERSION,
  addCustomShotToPlan,
  addShotFromTemplate,
  copyShot,
  emptySuitePlan,
  moveShot,
  nextShotId,
  removeShot,
  seedSuitePlan,
  shotById,
  suitePlanSummary,
  validateSuitePlan,
} from "/domain/index.js";

import { expect, expectCode, serializeError } from "./harness-api.js";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

function json(value) {
  return JSON.stringify(value);
}

function fact(slotId, status = "confirmed") {
  return { slot_id: slotId, status, value: slotId + "-值" };
}

function contextWith(overrides = {}) {
  return {
    facts: [fact("product_name"), fact("product_category"), fact("signature_features")],
    assets: [{ role: "primary", sha256: "a".repeat(64) }],
    ...overrides,
  };
}

function seededPlan() {
  return seedSuitePlan(contextWith()).plan;
}

function idsOf(plan) {
  return plan.shots.map((shot) => shot.shot_id);
}

function problemsMatching(problems, pathPart, textPart) {
  return problems.filter((item) => String(item.path || "").includes(pathPart)
    && String(item.message || "").includes(textPart));
}

/* ------------------------------------------------------------ E01..E04 基础 */

test("E01", "推荐播种：必需 + 依据已满足入选，被阻断可选带原因留下", () => {
  const result = seedSuitePlan(contextWith());
  expect(validateSuitePlan(result.plan).length === 0, "播种结果必须自检通过。");
  expect(json(idsOf(result.plan)) === json([
    "shot_main_clean", "shot_infographic_benefits", "shot_scene_lifestyle", "shot_detail_material",
  ]), "播种顺序必须是模板 order：" + json(idsOf(result.plan)));
  expect(result.plan.shots[0].required === true, "主图必须是必需图。");
  const skippedIds = result.skipped.map((item) => item.template_id);
  expect(json(skippedIds) === json([
    "size_dimensions", "comparison_competitor", "ingredient_composition", "packaging_contents",
  ]), "被阻断可选不静默塞入：" + json(skippedIds));
  const competitor = result.skipped.find((item) => item.template_id === "comparison_competitor");
  expect(competitor.blocking.some((item) => String(item.reason).includes("competitor")),
    "跳过项必须带精确原因：" + json(competitor.blocking));
  return { seeded: idsOf(result.plan), skipped: skippedIds };
});

test("E02", "空计划不是可保存方案：缺张数与缺必需图都要报", () => {
  const problems = validateSuitePlan(emptySuitePlan());
  expect(problemsMatching(problems, "$.shots", "至少").length >= 1,
    "空计划必须报至少一张：" + json(problems));
  expect(problemsMatching(problems, "$.shots", "必需").length >= 1,
    "空计划必须报缺必需图：" + json(problems));
  return { problems: problems.map((item) => item.message) };
});

test("E03", "添加模板图：同一模板允许重复且 id 自动去重；被阻断模板可添加但显示原因", () => {
  const plan = seededPlan();
  const again = addShotFromTemplate(plan, "scene_lifestyle");
  expect(again.shot.shot_id === "shot_scene_lifestyle_2", "重复模板要拿到 _2：" + again.shot.shot_id);
  const comparison = addShotFromTemplate(again.plan, "comparison_competitor");
  const summary = suitePlanSummary(comparison.plan, contextWith());
  const blocked = summary.shots.find((item) => item.shot_id === comparison.shot.shot_id);
  expect(!blocked.satisfied && blocked.blocking.some((item) => String(item.reason).includes("competitor")),
    "被阻断模板添加后必须显示原因：" + json(blocked));
  expect(summary.total === 6 && summary.blocked === 1, "投影数量不对：" + json([summary.total, summary.blocked]));
  return { ids: idsOf(comparison.plan), blocked: blocked.blocking };
});

test("E04", "自定义图：新增合法、空名称被拒、可复制且仍是可选图", async () => {
  const plan = seededPlan();
  const added = addCustomShotToPlan(plan, { label: "赠品特写", intent: "展示随附赠品" });
  expect(added.shot.shot_id === "shot_custom" && added.shot.required === false
    && added.shot.custom === true && added.shot.template_id === null,
  "自定义图字段不正确：" + json(added.shot));
  const invalidLabel = await expectCode(() => addCustomShotToPlan(plan, { label: "   " }),
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "空名称自定义图");
  const copied = copyShot(added.plan, added.shot.shot_id);
  expect(copied.shot.custom === true && copied.shot.required === false
    && copied.shot.shot_id === "shot_custom_copy", "自定义副本语义不正确：" + json(copied.shot));
  return { invalid_label: invalidLabel.message, copy_id: copied.shot.shot_id };
});

/* ------------------------------------------------------------ E05..E08 操作 */

test("E05", "复制：新 id、副本可选、名称标记、原图不动", () => {
  const plan = seededPlan();
  const before = json(plan);
  const copied = copyShot(plan, "shot_main_clean");
  expect(copied.shot.shot_id === "shot_main_clean_copy", "复制 id 不正确：" + copied.shot.shot_id);
  expect(copied.shot.required === false && copied.shot.label === "主图·干净背景（副本）",
    "副本必须是可选且带标记：" + json(copied.shot));
  expect(json(plan) === before, "复制不得改动原计划。");
  expect(copied.plan.shots.length === plan.shots.length + 1, "复制后数量应 +1。");
  return { copy_id: copied.shot.shot_id };
});

test("E06", "删除：可选可删；最后一张必需图与最后一张图都要被拒", async () => {
  const plan = seededPlan();
  const removed = removeShot(plan, "shot_scene_lifestyle");
  expect(removed.plan.shots.length === plan.shots.length - 1, "删除可选应生效。");
  const lastRequired = await expectCode(() => removeShot(plan, "shot_main_clean"),
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "删除最后一张必需图");
  const single = { schema_version: SUITE_PLAN_SCHEMA_VERSION, shots: [plan.shots[0]] };
  const lastShot = await expectCode(() => removeShot(single, "shot_main_clean"),
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "删除最后一张图");
  expect(validateSuitePlan(single).length === 0, "单张必需主图是合法计划。");
  return { last_required: lastRequired.message, last_shot: lastShot.message };
});

test("E07", "排序：±1 换位、边界不动、非法 delta 被拒", async () => {
  const plan = seededPlan();
  const moved = moveShot(plan, "shot_infographic_benefits", -1);
  expect(moved.moved === true, "上移应生效。");
  expect(json(idsOf(moved.plan).slice(0, 2)) === json(["shot_infographic_benefits", "shot_main_clean"]),
    "换位结果不正确：" + json(idsOf(moved.plan)));
  const top = moveShot(plan, "shot_main_clean", -1);
  expect(top.moved === false && json(top.plan) === json(plan), "边界移动必须原样返回。");
  const bottom = moveShot(plan, "shot_detail_material", 1);
  expect(bottom.moved === false, "底边移动必须原样返回。");
  const badDelta = await expectCode(() => moveShot(plan, "shot_main_clean", 2),
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "非法 delta");
  return { bad_delta: badDelta.message };
});

test("E08", "不变量校验：六类越界都要报红（反向探针）", () => {
  const base = seededPlan();
  const mutations = [
    { why: "shot_id 重复", path: ".shot_id", text: "重复",
      mutate(plan) { plan.shots[1].shot_id = plan.shots[0].shot_id; } },
    { why: "未知角色", path: ".role_id", text: "不在注册表内",
      mutate(plan) { plan.shots[1].role_id = "ghost"; } },
    { why: "custom 图带 template_id", path: ".template_id", text: "自定义图不来自模板",
      mutate(plan) {
        plan.shots[1] = { ...plan.shots[1], custom: true, role_id: "custom", required: false };
      } },
    { why: "非自定义图未知模板", path: ".template_id", text: "已登记模板",
      mutate(plan) { plan.shots[1].template_id = "ghost_template"; } },
    { why: "角色与模板不一致", path: ".role_id", text: "必须与模板一致",
      mutate(plan) { plan.shots[1].role_id = "detail"; } },
    { why: "自定义图被标必需", path: ".required", text: "自定义图必须是可选图",
      mutate(plan) {
        plan.shots[1] = { ...plan.shots[1], custom: true, template_id: null,
          role_id: "custom", dependencies: [], required: true };
      } },
    { why: "依赖与模板不一致", path: ".dependencies", text: "逐字一致",
      mutate(plan) { plan.shots[0].dependencies = []; } },
    { why: "缺必需图", path: "$.shots", text: "必需图",
      mutate(plan) { plan.shots[0].required = false; } },
  ];
  expect(validateSuitePlan(base).length === 0, "基线计划必须零问题。");
  const observed = [];
  for (const probe of mutations) {
    const plan = JSON.parse(JSON.stringify(base));
    probe.mutate(plan);
    const problems = validateSuitePlan(plan);
    expect(problems.length > 0, "守卫没有变红：" + probe.why);
    expect(problemsMatching(problems, probe.path, probe.text).length > 0,
      "没有找到预期问题：" + probe.why + " → " + probe.path + " / " + probe.text
        + "，实际 " + json(problems.slice(0, 3)));
    observed.push(probe.why);
  }
  return { probes: observed };
});

/* ------------------------------------------------------ E09..E12 事务与投影 */

test("E09", "失败原子：被拒操作不得产生半成品，输入计划逐字不变", async () => {
  const plan = seededPlan();
  const snapshot = json(plan);
  const attempts = [
    () => removeShot(plan, "shot_main_clean"),
    () => removeShot(plan, "shot_ghost"),
    () => moveShot(plan, "shot_ghost", 1),
    () => moveShot(plan, "shot_main_clean", 3),
    () => addCustomShotToPlan(plan, { label: "" }),
    () => copyShot(plan, "shot_ghost"),
  ];
  const messages = [];
  for (const attempt of attempts) {
    const refused = await expectCode(attempt, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "非法操作");
    messages.push(refused.message);
  }
  expect(json(plan) === snapshot, "被拒操作改动了输入计划。");
  return { refused: messages };
});

test("E10", "投影精确：缺竞品与缺主图都点名；补齐后逐图转满足", () => {
  const plan = seededPlan();
  const summary = suitePlanSummary(plan, contextWith());
  expect(summary.required_blocked.length === 0, "主图有 primary 时不应 blocked：" + json(summary.required_blocked));
  const noAsset = suitePlanSummary(plan, contextWith({ assets: [] }));
  expect(json(noAsset.required_blocked) === json(["shot_main_clean"]),
    "缺主参考图时必须点名必需图：" + json(noAsset.required_blocked));
  const comparison = addShotFromTemplate(plan, "comparison_competitor");
  const withCompetitor = suitePlanSummary(comparison.plan, contextWith({
    assets: [{ role: "primary" }, { role: "competitor" }],
  }));
  const comparisonItem = withCompetitor.shots.find((item) => item.template_id === "comparison_competitor");
  expect(comparisonItem.satisfied, "补齐竞品图后对比图应满足：" + json(comparisonItem.blocking));
  return { required_blocked: noAsset.required_blocked, total: withCompetitor.total };
});

test("E11", "id 派生可复现：冲突时 _2、_3，已占用则跳过", () => {
  const plan = seededPlan();
  expect(nextShotId(plan, "shot_main_clean") === "shot_main_clean_2", "首次冲突应给 _2。");
  const two = addShotFromTemplate(plan, "scene_lifestyle");
  const three = addShotFromTemplate(two.plan, "scene_lifestyle");
  expect(three.shot.shot_id === "shot_scene_lifestyle_3",
    "第二次冲突应给 _3：" + three.shot.shot_id);
  expect(shotById(three.plan, "shot_scene_lifestyle") !== null, "原图必须还在。");
  expect(MAX_SHOTS >= 20, "张数上限不应收紧到 20 以下。");
  return { ids: idsOf(three.plan) };
});

test("E12", "操作返回新对象：数组不共享，输入顺序与内容不变", () => {
  const plan = seededPlan();
  const before = json(plan);
  const moved = moveShot(plan, "shot_infographic_benefits", -1);
  expect(moved.plan !== plan && moved.plan.shots !== plan.shots, "必须返回新的数组与对象。");
  expect(json(plan) === before, "输入计划被改写。");
  const added = addShotFromTemplate(plan, "scene_lifestyle");
  expect(added.plan !== plan && added.plan.shots.length === plan.shots.length + 1
    && plan.shots.length === 4, "添加后长度不对或改写了输入。");
  return { moved: idsOf(moved.plan).slice(0, 2) };
});

/* ---------------------------------------------------------------- 运行器 */

function render(results) {
  const node = document.getElementById("results");
  if (node) node.textContent = JSON.stringify(results, null, 2);
}

async function runSuite() {
  const results = {
    suite: "v2.3.2-suite-editor",
    status: "running",
    cases: [],
    started_at: new Date().toISOString(),
  };
  window.__V2_SUITE_EDITOR_RESULTS__ = results;
  render(results);
  for (const item of cases) {
    const startedAt = performance.now();
    try {
      const detail = await item.run();
      results.cases.push({
        id: item.id, title: item.title, ok: true,
        detail: detail === undefined ? null : detail,
        ms: Math.round(performance.now() - startedAt),
      });
    } catch (error) {
      results.cases.push({
        id: item.id, title: item.title, ok: false,
        error: serializeError(error),
        ms: Math.round(performance.now() - startedAt),
      });
    }
  }
  const failed = results.cases.filter((item) => !item.ok);
  results.status = failed.length === 0 ? "passed" : "failed";
  results.failed_ids = failed.map((item) => item.id);
  results.finished_at = new Date().toISOString();
  render(results);
}

const params = new URLSearchParams(location.search);
if (params.get("suite") !== "0") {
  runSuite().catch((error) => {
    window.__V2_SUITE_EDITOR_RESULTS__ = {
      suite: "v2.3.2-suite-editor",
      status: "crashed",
      error: serializeError(error),
      cases: [],
    };
    render(window.__V2_SUITE_EDITOR_RESULTS__);
  });
} else {
  window.__V2_SUITE_EDITOR_RESULTS__ = {
    suite: "v2.3.2-suite-editor", status: "skipped", cases: [],
  };
}
