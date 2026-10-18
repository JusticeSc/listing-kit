/**
 * #9 程序表达契约：图中文字选择、单图版面与展示决定（Node 原生进程，零收费、不调用模型）。
 *
 * 同一份普通输入下，程序表达必须由「用户明确做的普通选择」驱动：
 *  - 印字：只印所选并确认的文案，不把这张图绑定的已确认事实自动印上图；
 *  - 版面：商品与文字的分布由明确布局决定，并写成正向描述；
 *  - 展示决定：干净展示／原样保持、倒空／保留内容物，未决定即阻断，不默选清洁。
 * 正向证明程序真的消费了选择；反向证明未确认、过期、跨平台不允许、未决定的选择会被
 * 抓住，而不是悄悄跳过或改写。
 *
 * 判据独立于实现：断言直接读编译结果里用户会看到的正文与来源，不复制编译器内部结构，
 * 也不靠整段提示词快照。纯领域断言（无宿主特有行为）只在 Node 侧，不设浏览器副本。
 *
 * 直接运行：node --test evals/product-v2/node/
 */

import {
  compilePrompt,
  emptyShotSpecFromShot,
  emptyStyleSpec,
  checkShotSpec,
  checkStyleSpec,
  shotSpecDiff,
  styleSpecDiff,
  requestSnapshotOf,
  buildPromptRecord,
  promptHash,
  promptStaleness,
} from "../../../build/frontend-node/app/product_v2/domain/index.js";

import { IMAGE_PROMPT_PROFILE, DIGEST, expect, serializeError } from "./harness-core.mjs";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

function json(value) {
  return JSON.stringify(value);
}

const SHA_PRIMARY = "a".repeat(64);

/** 已确认事实：中文商品事实，与用户明确选择的英文标题不同字面。 */
function fact(slotId, label, value, overrides = {}) {
  return { slot_id: slotId, label: label, value: value, source: "user_input", ...overrides };
}

function briefFixture() {
  return {
    schema_version: 1,
    basis: [
      { slot_id: "product_name", version: 1 },
      { slot_id: "product_category", version: 1 },
      { slot_id: "signature_features", version: 1 },
    ],
    category: { slot_id: "product_category", value: "保温杯" },
    confirmed_facts: [
      fact("product_name", "商品名称", "便携保温杯"),
      fact("product_category", "商品品类", "保温杯"),
      fact("signature_features", "必须保持的商品特征", ["304不锈钢内胆", "12小时保温"]),
    ],
    unresolved: [],
  };
}

function contextFixture() {
  return {
    facts: [
      { slot_id: "product_name", status: "confirmed", value: "便携保温杯" },
      { slot_id: "product_category", status: "confirmed", value: "保温杯" },
      { slot_id: "signature_features", status: "confirmed", value: ["304不锈钢内胆", "12小时保温"] },
    ],
    assets: [{ role: "primary", sha256: SHA_PRIMARY }],
  };
}

function styleFixture(overrides = {}) {
  // 夹具的显式展示决定：断言只测印字/版面/展示决定本身，所以先给一个已决定的基座。
  return {
    ...emptyStyleSpec(),
    background: "浅灰无缝背景",
    lighting: "柔和顶光",
    presentation: { appearance_state: "as_shown", contents_state: "not_applicable" },
    ...overrides,
  };
}

function infographicShot(overrides = {}) {
  return {
    shot_id: "shot_infographic_benefits",
    template_id: "infographic_benefits",
    role_id: "infographic",
    label: "类别介绍信息图",
    intent: "用一个清楚的标题说明商品类别，不写未确认卖点",
    required: false,
    custom: false,
    dependencies: [{ kind: "fact", slot_id: "signature_features" }],
    fact_slot_ids: ["signature_features"],
    ...overrides,
  };
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
    dependencies: [{ kind: "asset_role", role: "primary" }],
    fact_slot_ids: [],
    ...overrides,
  };
}

/** 明确选择的一条图中文案：原文 + 精确来源版本。默认来源就是这类图会绑定的事实槽。 */
function selectedText(overrides = {}) {
  return {
    text_id: "t1",
    text: "CERAMIC MUG",
    source_slot_id: "signature_features",
    source_slot_version: 1,
    status: "confirmed",
    origin: "user",
    ...overrides,
  };
}

function shotSpec(shot, overrides = {}) {
  return { ...emptyShotSpecFromShot(shot), ...overrides };
}

function compile(shot, spec, overrides = {}) {
  return compilePrompt({
    brief: briefFixture(),
    shot: shot,
    styleSpec: styleFixture(),
    shotSpec: spec,
    context: contextFixture(),
    versions: { suite_version: 3, style_version: 1, shot_spec_version: 1 },
    providerProfile: IMAGE_PROMPT_PROFILE,
    ...overrides,
  });
}

function literalTexts(compiled) {
  const section = compiled.sections.find((item) => item.key === "on_image_text");
  return section ? section.items.map((item) => item.text) : [];
}

/** 只有角色、无依赖依据的最小图；用于只测表达投影的用例（template 用已登记的对应模板）。 */
function roleShot(roleId, overrides = {}) {
  const templateByRole = {
    scene: "scene_lifestyle",
    detail: "detail_material",
    packaging: "packaging_contents",
    ingredient: "ingredient_composition",
    size: "size_dimensions",
  };
  return {
    shot_id: "shot_" + roleId + "_1",
    template_id: templateByRole[roleId] || roleId + "_custom",
    role_id: roleId,
    label: roleId,
    intent: "呈现商品在用途里的样子",
    required: false,
    custom: true,
    dependencies: [],
    fact_slot_ids: [],
    ...overrides,
  };
}

function sectionText(compiled, key) {
  const section = compiled.sections.find((item) => item.key === key);
  return section ? section.text : "";
}

function sectionRefs(compiled, key) {
  const section = compiled.sections.find((item) => item.key === key);
  return section ? [...section.source_refs] : [];
}

function allText(compiled) {
  return compiled.text;
}

function errorOf(run) {
  try {
    run();
  } catch (error) {
    return serializeError(error);
  }
  return null;
}

/* ------------------------------------------------ 未决定：不自动枚举事实 */

test("P01", "信息图默认未决定：绑定事实不自动印上图，而是阻断并给出具体选择", async () => {
  const shot = infographicShot();
  const error = errorOf(() => compile(shot, shotSpec(shot)));
  const texts = error ? null : literalTexts(compile(shot, shotSpec(shot)));
  expect(error !== null,
    "未决定时不得静默把绑定事实印上图；实际编译成功：" + json(texts));
  expect(/文字|印字|文案/.test(error.message),
    "阻断消息必须指向印字决定：" + json(error));
  return { message: error.message };
});

/* -------------------------------------------------- 明确不印新增文字 */

test("P02", "明确无新增文字：不产生图中文字段，绑定事实不再被当成印字", async () => {
  const shot = infographicShot();
  const compiled = compile(shot, shotSpec(shot, { print_intent: "none" }));
  expect(literalTexts(compiled).length === 0,
    "选择不印新增文字时不得出现文字条目：" + json(literalTexts(compiled)));
  expect(!allText(compiled).includes("304不锈钢内胆"),
    "绑定事实不得再被自动印上图：" + allText(compiled));
  const explained = (compiled.warnings || []).some((item) => /不.*印|不会印|未选择/.test(item.message));
  expect(explained, "不印字必须给出人读说明，而不是静默丢弃：" + json(compiled.warnings));
  return { warnings: compiled.warnings.map((item) => item.code) };
});

/* ------------------------------------------------------ 只印所选文案 */

test("P03", "只印所选：程序只印明确确认的标题，且来源指向该选择", async () => {
  const shot = infographicShot();
  const compiled = compile(shot, shotSpec(shot, {
    print_intent: "selected",
    layout: "product_left_text_right",
    on_image_texts: [selectedText()],
  }));
  const texts = literalTexts(compiled);
  expect(json(texts) === json(["「CERAMIC MUG」"]),
    "只能出现所选的那一条文案：" + json(texts));
  expect(!allText(compiled).includes("304不锈钢内胆") && !allText(compiled).includes("12小时保温"),
    "未选择的事实不得因为绑定就被印上图：" + allText(compiled));
  const section = compiled.sections.find((item) => item.key === "on_image_text");
  expect(/shot_spec|on_image_text/.test(json(section.items.map((item) => item.source_ref))),
    "文字条目必须带精确来源引用：" + json(section.items));
  expect((compiled.warnings || []).every((item) => item.code !== "ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE"),
    "英文标题在英文平台不该报语言风险：" + json(compiled.warnings));
  return { texts, refs: section.items.map((item) => item.source_ref) };
});

test("P04", "只印所选但仍有待确认项：阻断，不跳过也不替用户确认", async () => {
  const shot = infographicShot();
  const error = errorOf(() => compile(shot, shotSpec(shot, {
    print_intent: "selected",
    layout: "product_left_text_right",
    on_image_texts: [selectedText(), selectedText({ text_id: "t2", text: "12H KEEP WARM", status: "proposed" })],
  })));
  expect(error !== null, "待确认文案必须阻断发送：" + json(error));
  expect(/待确认|未确认|确认/.test(error.message), "阻断消息要说明缺确认：" + json(error));
  const compiled = compile(shot, shotSpec(shot, {
    print_intent: "selected",
    layout: "product_left_text_right",
    on_image_texts: [selectedText()],
  }));
  expect(json(literalTexts(compiled)) === json(["「CERAMIC MUG」"]),
    "确认后的选择必须能正常编译：" + json(literalTexts(compiled)));
  return { message: error.message };
});

test("P05", "只印所选但来源版本已前进：阻断，不静默改用新值", async () => {
  const shot = infographicShot();
  const staleSpec = shotSpec(shot, {
    print_intent: "selected",
    layout: "product_left_text_right",
    on_image_texts: [selectedText({ source_slot_version: 0 })],
  });
  const bad = errorOf(() => compile(shot, staleSpec));
  expect(bad !== null, "来源版本非法必须阻断：" + json(bad));
  const versionAhead = errorOf(() => compile(shot, shotSpec(shot, {
    print_intent: "selected",
    layout: "product_left_text_right",
    on_image_texts: [selectedText({ source_slot_version: 2 })],
  })));
  expect(versionAhead !== null, "来源版本与当前依据不一致必须阻断：" + json(versionAhead));
  const unknownSlot = errorOf(() => compile(shot, shotSpec(shot, {
    print_intent: "selected",
    layout: "product_left_text_right",
    on_image_texts: [selectedText({ source_slot_id: "not_confirmed" })],
  })));
  expect(unknownSlot !== null, "来源事实不存在必须阻断：" + json(unknownSlot));
  return { messages: [bad.message, versionAhead.message, unknownSlot.message] };
});

/* ---------------------------------------------------------------- 布局 */

test("P06", "明确布局：正文出现对应正向版面要求，切换布局只改版面", async () => {
  const shot = infographicShot();
  const base = {
    print_intent: "selected",
    on_image_texts: [selectedText()],
  };
  const left = compile(shot, shotSpec(shot, { ...base, layout: "product_left_text_right" }));
  const right = compile(shot, shotSpec(shot, { ...base, layout: "product_right_text_left" }));
  const leftText = allText(left);
  const rightText = allText(right);
  expect(/左/.test(leftText) && /右/.test(leftText), "左侧布局要写明商品与文字的分区：" + leftText);
  expect(leftText !== rightText, "切换布局必须改变程序表达，而不是只存字段。");
  expect(json(literalTexts(right)) === json(["「CERAMIC MUG」"]),
    "换布局不改所选文案：" + json(literalTexts(right)));
  // 新门：要印文案的图不能选「只放商品」版面（会同时要求「不出现文字」和「印出文字」），必须阻断而不是静默印字。
  const onlyProductError = errorOf(() => compile(shot, shotSpec(shot, { ...base, layout: "product_only" })));
  expect(onlyProductError !== null && /只放商品/.test(onlyProductError.message) && /不能选/.test(onlyProductError.message),
    "印字图选只放商品版面必须被拦住并点明版面名：" + json(onlyProductError));
  const layoutSection = left.sections.find((item) => item.key === "shot_layout");
  expect(Boolean(layoutSection), "布局必须是独立的正文段落：" + json(left.sections.map((item) => item.key)));
  return { layout: layoutSection.text };
});

test("P07", "主图不允许新增印字：选择文案也不得违反平台规则", async () => {
  const shot = mainShot({ fact_slot_ids: ["signature_features"] });
  const error = errorOf(() => compile(shot, shotSpec(shot, {
    print_intent: "selected",
    layout: "product_left_text_right",
    on_image_texts: [selectedText()],
  })));
  expect(error !== null, "主图选择印字必须被平台规则挡住：" + json(error));
  expect(/不允许新增文字|平台/.test(error.message),
    "主图的阻断消息必须说的是平台规则，而不是别的原因：" + json(error));
  const none = compile(shot, shotSpec(shot, { print_intent: "none" }));
  expect(literalTexts(none).length === 0, "主图不得出现图中文字段：" + json(literalTexts(none)));
  return { message: error.message };
});

/* ------------------------------------------------- 消费来源与过期关系 */

test("P08", "选择的来源参与消费依据：来源事实版本前进使这张图过期", async () => {
  const shot = infographicShot();
  const compiled = compile(shot, shotSpec(shot, {
    print_intent: "selected",
    layout: "product_left_text_right",
    on_image_texts: [selectedText()],
  }));
  const consumed = compiled.basis.brief.map((item) => item.slot_id);
  expect(consumed.includes("signature_features"),
    "所选文案的来源事实必须进入消费依据：" + json(compiled.basis.brief));
  const snapshot = requestSnapshotOf(compiled, { references: [{ role: "primary", sha256: SHA_PRIMARY }] });
  const record = buildPromptRecord({
    compiled: compiled, snapshot: snapshot, hash: await promptHash(snapshot, DIGEST),
  });
  const stale = promptStaleness(record, {
    briefBasis: compiled.basis.brief.map((item) =>
      item.slot_id === "signature_features" ? { ...item, version: 2 } : item),
    shot_signature: compiled.basis.shot_signature,
    suite_version: 3, style_version: 1, shot_spec_version: 1,
    platform: { version: 1 }, provider: IMAGE_PROMPT_PROFILE,
  });
  expect(stale.stale && stale.reasons.some((item) => item.field === "brief.signature_features"),
    "来源事实变化必须使这张图过期：" + json(stale));
  return { consumed };
});

/* ----------------------------------------------------------- 规格校验 */

test("P09", "规格守卫：非法印字意图/布局/条目必须变红，合法值可存", async () => {
  const shot = infographicShot();
  const ok = shotSpec(shot, {
    print_intent: "selected", layout: "product_left_text_right", on_image_texts: [selectedText()],
  });
  expect(checkShotSpec(ok).length === 0, "合法新字段不得被拒：" + json(checkShotSpec(ok)));
  const probes = [
    { why: "未知印字意图", mutate(spec) { spec.print_intent = "auto"; } },
    { why: "未知布局", mutate(spec) { spec.layout = "center"; } },
    { why: "文案重复 id", mutate(spec) { spec.on_image_texts = [selectedText(), selectedText()]; } },
    { why: "文案缺来源", mutate(spec) { spec.on_image_texts = [selectedText({ source_slot_id: "" })]; } },
    { why: "来源版本非正整数", mutate(spec) { spec.on_image_texts = [selectedText({ source_slot_version: 0 })]; } },
    { why: "未知确认状态", mutate(spec) { spec.on_image_texts = [selectedText({ status: "maybe" })]; } },
    { why: "文案为空", mutate(spec) { spec.on_image_texts = [selectedText({ text: "  " })]; } },
    { why: "文案超长", mutate(spec) { spec.on_image_texts = [selectedText({ text: "x".repeat(61) })]; } },
  ];
  const observed = [];
  for (const probe of probes) {
    const spec = JSON.parse(json(ok));
    probe.mutate(spec);
    expect(checkShotSpec(spec).length > 0, "守卫没有变红：" + probe.why);
    observed.push(probe.why);
  }
  const diff = shotSpecDiff(
    shotSpec(shot, { print_intent: "none" }),
    shotSpec(shot, { print_intent: "selected", layout: "product_left_text_right",
      on_image_texts: [selectedText()] }),
  );
  expect(diff.some((item) => item.field === "print_intent"), "差异投影要包含印字决定：" + json(diff));
  expect(diff.some((item) => item.field === "layout"), "差异投影要包含布局：" + json(diff));
  expect(diff.some((item) => item.field === "on_image_texts"), "差异投影要包含所选文案：" + json(diff));
  return { observed, diff: diff.map((item) => item.field) };
});

test("P10", "旧规格（无新字段）仍可读：不把缺失当成用户已选无字", async () => {
  const shot = infographicShot();
  const legacy = { schema_version: 1, purpose: "呈现类别", keep: ["商品外观"], change_allowed: ["背景"], notes: "" };
  expect(checkShotSpec(legacy).length === 0, "旧字段形状必须仍然合法：" + json(checkShotSpec(legacy)));
  const derived = emptyShotSpecFromShot(shot);
  expect(derived.print_intent === "undecided",
    "信息图未保存规格时默认是「未决定」，不是「不印」：" + json(derived));
  const mainDerived = emptyShotSpecFromShot(mainShot());
  expect(!("print_intent" in mainDerived),
    "不需要该决定的角色不投影印字字段（缺失=沿用该角色既有合同），而不是存一个「不印」：" + json(mainDerived));
  const mainLegacy = { schema_version: 1, purpose: "完整展示商品主体", keep: ["商品外观"],
    change_allowed: ["背景"], notes: "" };
  const mainCompiled = compile(mainShot(), mainLegacy);
  expect(literalTexts(mainCompiled).length === 0 && !allText(mainCompiled).includes("304不锈钢内胆"),
    "主图缺字段时不得出现图中文字：" + allText(mainCompiled));
  expect(!(mainCompiled.warnings || []).some((item) => item.code === "ON_IMAGE_TEXT_NONE_FACTS_SKIPPED"),
    "没有印字决定的角色不该收到「选择不印」的说明：" + json(mainCompiled.warnings));
  const error = errorOf(() => compile(shot, legacy));
  expect(error !== null, "缺字段的老规格仍按「未决定」阻断，而不是自动印字：" + json(error));
  return { derived: derived.print_intent, main: json(mainDerived.print_intent) };
});

/* ------------------------------------------------------ 展示决定（普通选择） */

test("P11", "展示决定按用途投影：消费的角色必须决定，不消费的不被拦也不产正文", async () => {
  const info = infographicShot();
  const noPrint = shotSpec(info, { print_intent: "none" });
  const undecided = errorOf(() => compile(info, noPrint, { styleSpec: emptyStyleSpec() }));
  expect(undecided !== null && /外观状态/.test(undecided.message),
    "消费外观状态的图未决定时必须阻断并指名该项：" + json(undecided));
  const scene = roleShot("scene");
  const onlyAppearance = styleFixture({ presentation: { appearance_state: "as_shown" } });
  const sceneBlocked = errorOf(() => compile(scene, shotSpec(scene), { styleSpec: onlyAppearance }));
  expect(sceneBlocked !== null && /内容物/.test(sceneBlocked.message),
    "会看到内容物的用途必须被要求决定内容物：" + json(sceneBlocked));
  const detail = roleShot("detail");
  const detailCompiled = compile(detail, shotSpec(detail), { styleSpec: onlyAppearance });
  expect(!/内容物/.test(sectionText(detailCompiled, "product_fidelity")),
    "不消费内容物的用途不得出现内容物正文：" + sectionText(detailCompiled, "product_fidelity"));
  return { info: undecided.message.slice(0, 40), scene: sceneBlocked.message.slice(0, 40) };
});

test("P12", "干净展示才给去污例外；原样保持不得写成清洁", async () => {
  const shot = mainShot();
  const clean = compile(shot, shotSpec(shot),
    { styleSpec: styleFixture({ presentation: { appearance_state: "clean_display" } }) });
  const cleanFidelity = sectionText(clean, "product_fidelity");
  expect(/允许去掉临时使用痕迹/.test(cleanFidelity),
    "干净展示必须写出明确例外：" + cleanFidelity);
  expect(sectionRefs(clean, "product_fidelity").includes("style_spec.presentation.appearance_state"),
    "例外必须带来源：" + json(sectionRefs(clean, "product_fidelity")));
  const asShown = compile(shot, shotSpec(shot),
    { styleSpec: styleFixture({ presentation: { appearance_state: "as_shown" } }) });
  const shownFidelity = sectionText(asShown, "product_fidelity");
  expect(!/允许去掉临时使用痕迹/.test(shownFidelity) && /原样/.test(shownFidelity),
    "原样保持不得带清洁例外，也不得被写成干净：" + shownFidelity);
  return { clean: cleanFidelity.length, as_shown: shownFidelity.length };
});

test("P13", "内容物决定写成正向状态：倒空与保留各有正文，不适用不产正文", async () => {
  const scene = roleShot("scene");
  const emptyCompiled = compile(scene, shotSpec(scene),
    { styleSpec: styleFixture({ presentation: { appearance_state: "as_shown", contents_state: "empty" } }) });
  expect(/内容物为空/.test(sectionText(emptyCompiled, "product_fidelity")),
    "倒空必须写成正向状态：" + sectionText(emptyCompiled, "product_fidelity"));
  const keepCompiled = compile(scene, shotSpec(scene),
    { styleSpec: styleFixture({ presentation: { appearance_state: "as_shown", contents_state: "as_shown" } }) });
  expect(/内容物保持原样/.test(sectionText(keepCompiled, "product_fidelity")) &&
    !/内容物为空/.test(sectionText(keepCompiled, "product_fidelity")),
    "保留内容物必须写成保持原样：" + sectionText(keepCompiled, "product_fidelity"));
  const naCompiled = compile(scene, shotSpec(scene), { styleSpec: styleFixture() });
  expect(!/内容物/.test(sectionText(naCompiled, "product_fidelity")),
    "不适用时不该出现内容物正文：" + sectionText(naCompiled, "product_fidelity"));
  return { empty: "ok" };
});

test("P14", "单图覆盖优先于共用默认；差异与守卫都看得见", async () => {
  const scene = roleShot("scene");
  const spec = shotSpec(scene, { presentation: { appearance_state: "clean_display" } });
  const compiled = compile(scene, spec, { styleSpec: styleFixture() });
  expect(/允许去掉临时使用痕迹/.test(sectionText(compiled, "product_fidelity")),
    "单图覆盖必须胜过共用默认：" + sectionText(compiled, "product_fidelity"));
  expect(sectionRefs(compiled, "product_fidelity").includes("shot_spec.presentation.appearance_state"),
    "覆盖要指到单图规格来源：" + json(sectionRefs(compiled, "product_fidelity")));
  const shotDiff = shotSpecDiff(shotSpec(scene), spec);
  expect(shotDiff.some((item) => item.field === "appearance_state"),
    "单图差异要包含展示决定：" + json(shotDiff));
  const styleDiff = styleSpecDiff(styleFixture(),
    styleFixture({ presentation: { appearance_state: "clean_display" } }));
  expect(styleDiff.some((item) => item.field === "appearance_state"),
    "风格差异要包含展示决定：" + json(styleDiff));
  const badShot = JSON.parse(json(spec));
  badShot.presentation = { appearance_state: "sparkling" };
  expect(checkShotSpec(badShot).length > 0, "非法外观状态必须变红。");
  const badStyle = JSON.parse(json(styleFixture()));
  badStyle.presentation = { contents_state: "half" };
  expect(checkStyleSpec(badStyle).length > 0, "非法内容物状态必须变红。");
  const unknownKey = JSON.parse(json(styleFixture()));
  unknownKey.presentation = { viewpoint: "top" };
  expect(checkStyleSpec(unknownKey).length > 0, "展示决定以外的键必须变红。");
  return { refs: sectionRefs(compiled, "product_fidelity") };
});

/* -------------------------------------------- 印字与版面的 fail-closed 门 */

test("P15", "只印所选但没选版面必须先拦版面：消息含「还得先决定版面」且不产图中文字段（抓版面门被跳过回归）", async () => {
  const shot = infographicShot();
  const error = errorOf(() => compile(shot, shotSpec(shot, {
    print_intent: "selected",
    on_image_texts: [selectedText()],
  })));
  expect(error !== null, "选了要印文案却没选版面必须阻断：" + json(error));
  expect(/还得先决定版面/.test(error.message), "阻断消息必须让人先决定版面：" + json(error));
  expect(error.details && json(error.details).includes("$.shot_spec.layout"),
    "问题定位必须指到版面字段：" + json(error));
  expect(!json(error.details).includes("on_image_text"),
    "版面门先触发时不得顺带产出图中文字段：" + json(error));
  return { message: error.message };
});

test("P16", "只印所选不能配只放商品版面：消息含「不能选」并点明版面名；换左图右文后同输入可编译且版面段与文字段并存（抓矛盾版面放行回归）", async () => {
  const shot = infographicShot();
  const base = { print_intent: "selected", on_image_texts: [selectedText()] };
  const error = errorOf(() => compile(shot, shotSpec(shot, { ...base, layout: "product_only" })));
  expect(error !== null, "要印文案的图选只放商品版面必须阻断：" + json(error));
  expect(/不能选/.test(error.message) && /只放商品/.test(error.message),
    "阻断消息必须点明版面名并说不能选：" + json(error));
  const fixed = compile(shot, shotSpec(shot, { ...base, layout: "product_left_text_right" }));
  const keys = fixed.sections.map((item) => item.key);
  expect(keys.includes("shot_layout") && keys.includes("on_image_text"),
    "换成文字版面后必须同时有版面段与图中文字段：" + json(keys));
  expect(json(literalTexts(fixed)) === json(["「CERAMIC MUG」"]),
    "换版面不得改动所选文案：" + json(literalTexts(fixed)));
  return { message: error.message, keys };
});

test("P17", "不印新增文字不点版面也不阻断：正文不含版面段（抓不印字被版面门误拦回归）", async () => {
  const shot = infographicShot();
  const compiled = compile(shot, shotSpec(shot, { print_intent: "none" }));
  const keys = compiled.sections.map((item) => item.key);
  expect(!keys.includes("shot_layout"), "不印字且没选版面时不得出现版面段：" + json(keys));
  expect(!allText(compiled).includes("版面"), "不印字正文不得提版面：" + allText(compiled));
  expect(literalTexts(compiled).length === 0, "不印字不得出现文字条目：" + json(literalTexts(compiled)));
  const codes = compiled.warnings.map((item) => item.code);
  expect(codes.includes("ON_IMAGE_TEXT_NONE_FACTS_SKIPPED"),
    "不印字时要说清绑定的事实在画面上不会出现：" + json(codes));
  expect(!codes.includes("ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE"),
    "不印字就不该有语言风险：" + json(codes));
  return { keys, warnings: codes };
});

test("P18", "文字版面必须真的有文字：不印字却选文字版面被拦（另一个方向也不许自相矛盾）", async () => {
  const shot = infographicShot();
  // (a) 明确不印新增文字，却留着「商品在左，文字在右」版面：正文会为文字留位置而没有任何文案。
  const orphanLayout = errorOf(() => compile(shot, shotSpec(shot, {
    print_intent: "none", layout: "product_left_text_right",
  })));
  expect(orphanLayout !== null, "不印字配文字版面必须阻断，不能排出「放置下方给定的文字」：" + json(orphanLayout));
  expect(/不会有图上文字|没有文案可放|不能选/.test(orphanLayout.message),
    "阻断消息要说清为什么：" + json(orphanLayout));
  expect(/只放商品/.test(orphanLayout.message), "阻断消息要给出可执行的改法：" + json(orphanLayout));
  // (b) 同一张图改成「只放商品」就能编译，且正文里没有文字段。
  const fixed = compile(shot, shotSpec(shot, { print_intent: "none", layout: "product_only" }));
  expect(!fixed.sections.some((item) => item.key === "on_image_text"),
    "改对版面后不得再出现文字段：" + json(fixed.sections.map((item) => item.key)));
  // (c) 非印字决定角色（尺寸图）若被导入数据写成文字版面，而手上只有不能逐字上图的尺寸值
  //     （或者这个用途根本不允许文字），同样拦下；换成「只放商品」可编译。
  const size = roleShot("size");
  const sizeTextLayout = { ...shotSpec(size), layout: "product_left_text_right" };
  const sizeBlocked = errorOf(() => compile(size, sizeTextLayout));
  expect(sizeBlocked !== null, "没有可印文字的尺寸图不得排文字版面：" + json(sizeBlocked));
  const sizeFixed = compile(size, { ...shotSpec(size), layout: "product_only" });
  expect(sizeFixed.sections.some((item) => item.key === "visual_brief"),
    "改对版面后尺寸图仍要拿到画面简报：" + json(sizeFixed.sections.map((item) => item.key)));
  return { infographic: orphanLayout.message, size: sizeBlocked.message };
});

test("P19", "所选文案的来源必须还在本图绑定里：解绑后不得继续印（界面也不该让它隐形）", async () => {
  const shot = infographicShot();
  const spec = shotSpec(shot, {
    print_intent: "selected", layout: "product_left_text_right",
    on_image_texts: [selectedText()],
  });
  // 先证明这份规格本身合法（绑定里就有来源槽位）。
  const ok = compile(shot, spec);
  expect(json(literalTexts(ok)) === json(["「CERAMIC MUG」"]), "绑定来源时必须能印：" + json(literalTexts(ok)));
  // 再解绑来源：条目会从界面的候选里消失，此时继续印就等于印用户已经移出这张图的依据。
  const unbound = infographicShot({ fact_slot_ids: [] });
  const error = errorOf(() => compile(unbound, spec));
  expect(error !== null, "来源解绑后必须阻断：" + json(error));
  expect(/不在这张图的绑定里/.test(error.message), "阻断消息要说明是绑定关系变了：" + json(error));
  // 保留一个别的可印事实时也不能替用户改来源：仍然阻断。
  const reboundOther = infographicShot({ fact_slot_ids: ["product_category"] });
  const stillBlocked = errorOf(() => compile(reboundOther, spec));
  expect(stillBlocked !== null, "换成别的绑定不得静默改用其它来源：" + json(stillBlocked));
  expect(/不在这张图的绑定里/.test(stillBlocked.message), "仍要指回绑定关系：" + json(stillBlocked));
  return { messages: [error.message, stillBlocked.message] };
});

/* ---------------------------------------------------------------- 运行器 */

import nodeTest from "node:test";
for (const item of cases) {
  nodeTest(`${item.id} :: ${item.title}`, { timeout: 60000 }, async () => { await item.run(); });
}
