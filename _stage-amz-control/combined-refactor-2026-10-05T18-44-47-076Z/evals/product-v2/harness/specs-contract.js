/**
 * V2.3.3 规格层契约测试（真实 Chromium，非 Mock）：StyleSpec 与 ShotSpec。
 *
 * 正向：默认值派生、差异、失效投影（整套 vs 单图）、回退选版、审核清单与 digest。
 * 反向（故意让守卫变红）：未知字段、超长、空 purpose、空列表、重复项、缺失 shotId、
 * 非法版本号；并断言校验与差异函数不修改输入（确定性）。
 *
 * 结果写到 window.__V2_SPECS_RESULTS__，由 tools/verify_v2_3_3_spec_versions.py 读取。
 */

import {
  DOMAIN_ERROR_CODES,
  MAX_SHOT_ITEMS,
  checkShotSpec,
  checkStyleSpec,
  emptyShotSpecFromShot,
  emptyStyleSpec,
  previousVersionOf,
  reviewChecklist,
  shotSpecDiff,
  specChangeProjection,
  styleSpecDiff,
  styleSpecSummary,
  suiteSpecDigest,
} from "/domain/index.js";

import { expect, expectCode, serializeError } from "./harness-api.js";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

function json(value) {
  return JSON.stringify(value);
}

function problemsMatching(problems, pathPart, textPart) {
  return problems.filter((item) => String(item.path || "").includes(pathPart)
    && String(item.message || "").includes(textPart));
}

function mainShot(overrides = {}) {
  return {
    shot_id: "shot_main_clean",
    template_id: "main_clean",
    role_id: "main",
    label: "主图·干净背景",
    intent: "完整展示商品主体，背景干净",
    required: true,
    custom: false,
    ...overrides,
  };
}

function styleFixture(overrides = {}) {
  return { ...emptyStyleSpec(), background: "浅灰无缝背景", avoid: ["文字水印"], ...overrides };
}

/* ------------------------------------------------------------ F01..F06 规格 */

test("F01", "空风格规格合法；投影只列有值字段", () => {
  const problems = checkStyleSpec(emptyStyleSpec());
  expect(problems.length === 0, "空风格必须合法：" + json(problems));
  expect(styleSpecSummary(emptyStyleSpec()).length === 0, "空风格投影必须为空。");
  const summary = styleSpecSummary(styleFixture({ lighting: "柔和顶光" }));
  expect(json(summary.map((item) => item.key)) === json(["background", "lighting", "avoid"]),
    "投影必须只列有值字段：" + json(summary.map((item) => item.key)));
  expect(summary.some((item) => item.text.includes("避免出现：文字水印")), "列表字段要拼成人读文本。");
  return { summary: summary.map((item) => item.text) };
});

test("F02", "风格校验反向探针：七类越界都要变红", () => {
  const base = styleFixture();
  expect(checkStyleSpec(base).length === 0, "基线必须零问题。");
  const mutations = [
    { why: "未知字段", path: ".pixel_style", text: "不在风格规格内",
      mutate(spec) { spec.pixel_style = "x"; } },
    { why: "文本字段类型错", path: ".background", text: "必须是文本",
      mutate(spec) { spec.background = 42; } },
    { why: "文本超长", path: ".lighting", text: "最长",
      mutate(spec) { spec.lighting = "x".repeat(201); } },
    { why: "avoid 非列表", path: ".avoid", text: "一行一条",
      mutate(spec) { spec.avoid = "文字水印"; } },
    { why: "avoid 超条数", path: ".avoid", text: "最多 10 条",
      mutate(spec) { spec.avoid = Array.from({ length: 11 }, (_, i) => "禁止" + i); } },
    { why: "avoid 重复", path: "$.avoid[1]", text: "不允许重复",
      mutate(spec) { spec.avoid = ["文字水印", "文字水印"]; } },
    { why: "avoid 空项", path: "$.avoid[0]", text: "不能为空",
      mutate(spec) { spec.avoid = ["   "]; } },
  ];
  const observed = [];
  for (const probe of mutations) {
    const spec = JSON.parse(json(base));
    probe.mutate(spec);
    const problems = checkStyleSpec(spec);
    expect(problems.length > 0, "守卫没有变红：" + probe.why);
    expect(problemsMatching(problems, probe.path, probe.text).length > 0,
      "没有找到预期问题：" + probe.why + " → " + probe.path + " / " + probe.text
        + "，实际 " + json(problems.slice(0, 3)));
    observed.push(probe.why);
  }
  return { probes: observed };
});

test("F03", "风格差异只报告真正变化的字段", () => {
  const before = styleFixture();
  const after = { ...before, background: "深灰渐变背景", avoid: ["文字水印", "默认模特"] };
  const diffs = styleSpecDiff(before, after);
  expect(json(diffs.map((item) => item.field)) === json(["background", "avoid"]),
    "差异字段不正确：" + json(diffs.map((item) => item.field)));
  expect(styleSpecDiff(before, { ...before }).length === 0, "没有变化时不应报告差异。");
  return { diffs: diffs.map((item) => item.label) };
});

test("F04", "单图默认值按角色派生：主图/场景/自定义各自不同", () => {
  const main = emptyShotSpecFromShot(mainShot());
  expect(main.purpose.includes("完整展示"), "默认目的取模板意图：" + main.purpose);
  expect(main.keep.some((item) => item.includes("标识")), "主图必须保持标识：" + json(main.keep));
  expect(json(main.change_allowed) === json(["背景"]), "主图只允许背景变化：" + json(main.change_allowed));
  const scene = emptyShotSpecFromShot(mainShot({ shot_id: "shot_scene", role_id: "scene", label: "场景图", intent: "放进真实场景" }));
  expect(scene.change_allowed.some((item) => item.includes("环境")), "场景图允许环境变化：" + json(scene.change_allowed));
  expect(checkShotSpec(main).length === 0 && checkShotSpec(scene).length === 0, "默认规格必须自检通过。");
  const custom = emptyShotSpecFromShot({ shot_id: "shot_custom", role_id: "custom", label: "赠品特写", custom: true });
  expect(custom.keep.length > 0 && custom.change_allowed.length > 0, "自定义图要有兜底默认。");
  return { main_keep: main.keep, scene_change: scene.change_allowed };
});

test("F05", "单图校验反向探针：九类越界都要变红", () => {
  const base = emptyShotSpecFromShot(mainShot());
  expect(checkShotSpec(base).length === 0, "基线必须零问题。");
  const mutations = [
    { why: "空 purpose", path: ".purpose", text: "目的不能为空",
      mutate(spec) { spec.purpose = "   "; } },
    { why: "purpose 超长", path: ".purpose", text: "最长",
      mutate(spec) { spec.purpose = "x".repeat(201); } },
    { why: "keep 非列表", path: ".keep", text: "必须是列表",
      mutate(spec) { spec.keep = "商品外观"; } },
    { why: "keep 空列表", path: ".keep", text: "至少要有一项",
      mutate(spec) { spec.keep = []; } },
    { why: "keep 超项数", path: ".keep", text: "最多",
      mutate(spec) { spec.keep = Array.from({ length: MAX_SHOT_ITEMS + 1 }, (_, i) => "项" + i); } },
    { why: "单项超长", path: "$.keep[0]", text: "最多",
      mutate(spec) { spec.keep = ["x".repeat(61)]; } },
    { why: "重复项", path: "$.keep[1]", text: "不允许重复",
      mutate(spec) { spec.keep = ["商品外观", "商品外观"]; } },
    { why: "未知字段", path: ".prompt", text: "不在单图规格内",
      mutate(spec) { spec.prompt = "raw prompt"; } },
    { why: "notes 非文本", path: ".notes", text: "备注必须是文本",
      mutate(spec) { spec.notes = 42; } },
  ];
  const observed = [];
  for (const probe of mutations) {
    const spec = JSON.parse(json(base));
    probe.mutate(spec);
    const problems = checkShotSpec(spec);
    expect(problems.length > 0, "守卫没有变红：" + probe.why);
    expect(problemsMatching(problems, probe.path, probe.text).length > 0,
      "没有找到预期问题：" + probe.why + " → " + probe.path + " / " + probe.text
        + "，实际 " + json(problems.slice(0, 3)));
    observed.push(probe.why);
  }
  return { probes: observed };
});

test("F06", "单图差异：purpose 与 keep 各自成条，未变不报", () => {
  const before = emptyShotSpecFromShot(mainShot());
  const after = { ...before, purpose: "主图：完整展示保温杯", keep: [...before.keep, "杯盖形态"] };
  const diffs = shotSpecDiff(before, after);
  expect(json(diffs.map((item) => item.field)) === json(["purpose", "keep"]),
    "差异字段不正确：" + json(diffs.map((item) => item.field)));
  expect(shotSpecDiff(before, { ...before }).length === 0, "没有变化时不应报告差异。");
  return { diffs: diffs.map((item) => item.label) };
});

/* ------------------------------------------------------- F07..F09 失效与版本 */

test("F07", "整套投影：风格改动影响全部图片并保留计划与商品理解", () => {
  const projection = specChangeProjection("style_changed", { shotCount: 4 });
  expect(projection.scope === "project" && projection.affects === "suite",
    "风格必须影响整套：" + json(projection));
  expect(projection.affects_text === "全部 4 张图", "影响文本不正确：" + projection.affects_text);
  expect(projection.invalidates.includes("prompt_versions")
    && projection.invalidates.includes("review_reports"), "失效集合缺项：" + json(projection.invalidates));
  expect(projection.preserves.includes("suite_plan")
    && projection.preserves.includes("product_brief"), "保留集合缺项：" + json(projection.preserves));
  expect(projection.invalidates_text.includes("Prompt 版本"), "失效文本要人读：" + projection.invalidates_text);
  return { affects: projection.affects_text, invalidates: projection.invalidates_text };
});

test("F08", "单图投影：只影响目标图且必须带 shotId", async () => {
  const projection = specChangeProjection("shot_spec_changed", {
    shotId: "shot_main_clean", shotLabel: "主图·干净背景",
  });
  expect(projection.scope === "shot" && projection.affects === "shot", "单图改动必须是 shot scope。");
  expect(projection.affects_text.includes("主图·干净背景"), "影响文本要点名目标：" + projection.affects_text);
  expect(projection.preserves.includes("other_shots"), "必须保留其他图片：" + json(projection.preserves));
  expect(projection.invalidates.includes("selection"), "选择结果必须失效：" + json(projection.invalidates));
  const missing = await expectCode(() => specChangeProjection("shot_spec_changed", {}),
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "缺少 shotId 的单图投影");
  const unknown = await expectCode(() => specChangeProjection("nonsense_changed", {}),
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "未知变化类型");
  return { affects: projection.affects_text, missing: missing.message, unknown: unknown.message };
});

test("F09", "回退选版：只选比当前小的最高版本；边界与非法输入都要说清", async () => {
  const versions = [{ version: 3 }, { version: 2 }, { version: 1 }];
  expect(previousVersionOf(versions, 3).version === 2, "v3 的上一版必须是 v2。");
  expect(previousVersionOf(versions, 2).version === 1, "v2 的上一版必须是 v1。");
  expect(previousVersionOf(versions, 1) === null, "v1 没有上一版。");
  expect(previousVersionOf([], 2) === null, "空历史没有上一版。");
  const invalid = await expectCode(() => previousVersionOf(versions, 0),
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "非法当前版本");
  return { invalid: invalid.message };
});

/* --------------------------------------------------------- F10..F12 清单与聚合 */

test("F10", "审核清单：默认规格标默认，保存规格标已保存，风格行随风格变化", () => {
  const shot = mainShot();
  const withoutSpec = reviewChecklist(shot, { styleSpec: styleFixture() });
  expect(withoutSpec.saved === false, "未保存规格必须标默认。");
  expect(withoutSpec.sections.length === 4, "清单固定四段：" + json(withoutSpec.sections.map((s) => s.key)));
  expect(withoutSpec.style_lines.some((item) => item.includes("浅灰无缝背景")), "风格行必须投影公共风格。");
  const savedSpec = emptyShotSpecFromShot(shot);
  savedSpec.purpose = "主图：完整展示保温杯";
  const withSpec = reviewChecklist(shot, { shotSpec: savedSpec, styleSpec: emptyStyleSpec() });
  expect(withSpec.saved === true && withSpec.purpose === "主图：完整展示保温杯", "保存规格必须如实投影。");
  expect(withSpec.style_configured === false && withSpec.sections[3].items.length === 0,
    "未设置公共风格时风格段为空。");
  return { default_saved: withoutSpec.saved, sections: withoutSpec.sections.map((s) => s.key) };
});

test("F11", "聚合 digest：按计划顺序、默认/已保存计数、风格配置状态", () => {
  const plan = { schema_version: 1, shots: [mainShot(), mainShot({ shot_id: "shot_scene", role_id: "scene", label: "场景图", required: false })] };
  const spec = emptyShotSpecFromShot(mainShot());
  const digest = suiteSpecDigest(plan, {
    styleSpec: styleFixture(),
    shotSpecsById: { shot_main_clean: { spec, version: 2 } },
  });
  expect(digest.total === 2 && digest.saved === 1 && digest.defaults === 1,
    "计数不正确：" + json([digest.total, digest.saved, digest.defaults]));
  expect(digest.style_configured === true, "风格已配置必须如实投影。");
  expect(json(digest.shots.map((item) => item.shot_id)) === json(["shot_main_clean", "shot_scene"]),
    "必须按计划顺序：" + json(digest.shots.map((item) => item.shot_id)));
  expect(digest.shots[1].version === 0 && digest.shots[1].saved === false, "默认图版本必须是 0。");
  return { total: digest.total, saved: digest.saved };
});

test("F12", "确定性：同输入两次投影一致；校验与差异不修改输入", () => {
  const shot = mainShot();
  const style = styleFixture();
  const first = json(reviewChecklist(shot, { styleSpec: style }));
  const second = json(reviewChecklist(shot, { styleSpec: style }));
  expect(first === second, "审核清单必须确定性输出。");
  const styleSnapshot = json(style);
  const shotSnapshot = json(shot);
  checkStyleSpec(style);
  checkShotSpec(emptyShotSpecFromShot(shot));
  styleSpecDiff(style, styleFixture({ background: "别的背景" }));
  shotSpecDiff(emptyShotSpecFromShot(shot), { ...emptyShotSpecFromShot(shot), purpose: "别的目的" });
  expect(json(style) === styleSnapshot && json(shot) === shotSnapshot, "校验/差异不得修改输入。");
  return { deterministic: true };
});

/* ---------------------------------------------------------------- 运行器 */

function render(results) {
  const node = document.getElementById("results");
  if (node) node.textContent = JSON.stringify(results, null, 2);
}

async function runSuite() {
  const results = {
    suite: "v2.3.3-specs",
    status: "running",
    cases: [],
    started_at: new Date().toISOString(),
  };
  window.__V2_SPECS_RESULTS__ = results;
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
    window.__V2_SPECS_RESULTS__ = {
      suite: "v2.3.3-specs",
      status: "crashed",
      error: serializeError(error),
      cases: [],
    };
    render(window.__V2_SPECS_RESULTS__);
  });
} else {
  window.__V2_SPECS_RESULTS__ = { suite: "v2.3.3-specs", status: "skipped", cases: [] };
}
