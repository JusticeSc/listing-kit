/**
 * V2.3.4 Provider 感知 Prompt 编译器契约测试（Node 原生进程，非 Mock）。
 *
 * 正向：golden 快照、来源可解析、hash 稳定性、语言策略、主图平台覆盖、请求快照与版本记录。
 * 反向（故意让守卫变红）：keep/avoid 冲突、缺依据、未确认绑定、未确认事实泄漏、
 * 非逐字图中文案、参考图数量越界、快照与编译文本不一致、过期检测。
 *
 * 直接运行：node --test evals/product-v2/node/
 */

import {
  DOMAIN_ERROR_CODES,
  buildPromptRecord,
  canonicalJson,
  checkCompiledPrompt,
  checkPromptLanguage,
  checkPromptLeaks,
  checkPromptRecord,
  checkLiteralVerbatim,
  checkSpecConflicts,
  compilePrompt,
  emptyShotSpecFromShot,
  emptyStyleSpec,
  promptHash,
  promptStaleness,
  requestSnapshotOf,
} from "../../../app/product_v2/domain/index.js";

import { sha256Hex } from "../../../app/product_v2/storage/db.js";
import { IMAGE_PROMPT_PROFILE, expect, expectCode, serializeError } from "./harness-core.mjs";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

function json(value) {
  return JSON.stringify(value);
}

const SHA_PRIMARY = "a".repeat(64);
const SHA_COMPETITOR = "b".repeat(64);
const DIGEST = { digest: sha256Hex };

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
      { slot_id: "size_summary", version: 1 },
    ],
    category: { slot_id: "product_category", value: "保温杯" },
    confirmed_facts: [
      fact("product_name", "商品名称", "便携保温杯"),
      fact("product_category", "商品品类", "保温杯"),
      fact("signature_features", "必须保持的商品特征", ["304不锈钢内胆", "12小时保温"]),
      fact("size_summary", "尺寸概览", "500ml"),
    ],
    unresolved: [],
  };
}

function contextFixture(extraFacts = []) {
  return {
    facts: [
      { slot_id: "product_name", status: "confirmed", value: "便携保温杯" },
      { slot_id: "product_category", status: "confirmed", value: "保温杯" },
      { slot_id: "signature_features", status: "confirmed", value: ["304不锈钢内胆", "12小时保温"] },
      { slot_id: "size_summary", status: "confirmed", value: "500ml" },
      ...extraFacts,
    ],
    assets: [
      { role: "primary", sha256: SHA_PRIMARY },
      { role: "competitor", sha256: SHA_COMPETITOR },
    ],
  };
}

function mainShot(overrides = {}) {
  return {
    shot_id: "shot_main_clean",
    template_id: "main_clean",
    role_id: "main",
    label: "主图·干净背景",
    intent: "完整展示商品主体，背景干净，不添加资料里没有的部件",
    required: true,
    custom: false,
    dependencies: [{ kind: "asset_role", role: "primary" }],
    fact_slot_ids: [],
    ...overrides,
  };
}

function infographicShot(overrides = {}) {
  return {
    shot_id: "shot_infographic_benefits",
    template_id: "infographic_benefits",
    role_id: "infographic",
    label: "卖点信息图",
    intent: "用简短标注呈现已确认卖点，不写入未确认参数",
    required: false,
    custom: false,
    dependencies: [{ kind: "fact", slot_id: "signature_features" }],
    fact_slot_ids: ["signature_features"],
    ...overrides,
  };
}

function styleFixture(overrides = {}) {
  return {
    ...emptyStyleSpec(),
    background: "浅灰无缝背景",
    lighting: "柔和顶光",
    color_tone: "自然",
    composition: "商品居中，留白充足",
    avoid: ["文字水印"],
    ...overrides,
  };
}

function compileMain(overrides = {}) {
  const brief = briefFixture();
  const shot = mainShot();
  return compilePrompt({
    brief: brief,
    shot: shot,
    styleSpec: styleFixture(),
    shotSpec: emptyShotSpecFromShot(shot),
    context: contextFixture(),
    versions: { suite_version: 3, style_version: 1, shot_spec_version: 1 },
    providerProfile: IMAGE_PROMPT_PROFILE,
    ...overrides,
  });
}

function resolveRef(ref, brief, context) {
  const known = {
    "intake.references": context.assets.length > 0,
    "style_spec.background": true,
    "style_spec.lighting": true,
    "style_spec.color_tone": true,
    "style_spec.composition": true,
    "style_spec.avoid": true,
    "shot_spec.purpose": true,
    "shot_spec.keep": true,
    "shot_spec.change_allowed": true,
    "shot_spec.notes": true,
  };
  if (Object.prototype.hasOwnProperty.call(known, ref)) return known[ref];
  if (/^platform:[a-z_]+@[0-9]+$/.test(ref)) return true;
  if (/^provider:[A-Za-z0-9._-]+@[0-9]+$/.test(ref)) return true;
  if (/^suite_plan\.shot:/.test(ref)) {
    return ref.endsWith(".role") || ref === "suite_plan.shot:" + "shot_main_clean"
      || ref.startsWith("suite_plan.shot:shot_");
  }
  if (/^product_brief\.fact:/.test(ref)) {
    const slotId = ref.slice("product_brief.fact:".length);
    return brief.confirmed_facts.some((item) => item.slot_id === slotId);
  }
  return false;
}

/* ------------------------------------------------------------ G01..G06 */

test("G01", "主图：分段顺序固定，平台纯白/无文字规则进入正文", async () => {
  const compiled = compileMain();
  const keys = compiled.sections.map((item) => item.key);
  expect(json(keys) === json([
    "product_fidelity", "style_shared", "shot_task", "platform_rules",
    "provider_contract", "negative_constraints",
  ]), "主图段落顺序必须固定：" + json(keys));
  expect(checkCompiledPrompt(compiled).length === 0, "主图默认编译必须自检通过。");
  expect(compiled.sections.some((item) => item.key === "platform_rules"),
    "主图必须携带平台规则段（纯白背景/无文字约束的落点）。");
  return { text_length: compiled.text.length };
});

test("G02", "每个段落的来源都能解析到当前输入；来源并集与声明一致", async () => {
  const brief = briefFixture();
  const context = contextFixture();
  const compiled = compileMain({ brief: brief, context: context });
  const broken = [];
  for (const item of compiled.sections) {
    expect(item.source_refs.length > 0, "段落 " + item.key + " 必须有来源。");
    for (const ref of item.source_refs) {
      if (!resolveRef(ref, brief, context)) broken.push(item.key + " → " + ref);
    }
  }
  expect(broken.length === 0, "存在无法解析的来源：" + json(broken));
  expect(json(compiled.source_refs) === json(compiled.sections.flatMap((item) => item.source_refs)
    .filter((ref, index, all) => all.indexOf(ref) === index)),
  "source_refs 必须是并按出现顺序去重。");
  return { refs: compiled.source_refs };
});

test("G03", "hash 稳定：同输入同 hash；改一个字段即变化；不修改输入", async () => {
  const brief = briefFixture();
  const shot = mainShot();
  const context = contextFixture();
  const before = json([brief, shot, context]);
  const first = compilePrompt({
    brief: brief, shot: shot, styleSpec: styleFixture(),
    shotSpec: emptyShotSpecFromShot(shot), context: context,
    versions: { suite_version: 3, style_version: 1, shot_spec_version: 1 },
    providerProfile: IMAGE_PROMPT_PROFILE,
  });
  const second = compilePrompt({
    brief: brief, shot: shot, styleSpec: styleFixture(),
    shotSpec: emptyShotSpecFromShot(shot), context: context,
    versions: { suite_version: 3, style_version: 1, shot_spec_version: 1 },
    providerProfile: IMAGE_PROMPT_PROFILE,
  });
  expect(first.text === second.text, "同输入必须产生逐字相同的文本。");
  const snapA = requestSnapshotOf(first, { references: [{ role: "primary", sha256: SHA_PRIMARY }] });
  const snapB = requestSnapshotOf(second, { references: [{ role: "primary", sha256: SHA_PRIMARY }] });
  const [hashA, hashB] = [await promptHash(snapA, DIGEST), await promptHash(snapB, DIGEST)];
  expect(hashA === hashB, "同输入必须得到稳定 hash。");
  const changed = compilePrompt({
    brief: brief, shot: shot, styleSpec: styleFixture({ lighting: "强烈侧光" }),
    shotSpec: emptyShotSpecFromShot(shot), context: context,
    versions: { suite_version: 3, style_version: 1, shot_spec_version: 1 },
    providerProfile: IMAGE_PROMPT_PROFILE,
  });
  const hashC = await promptHash(
    requestSnapshotOf(changed, { references: [{ role: "primary", sha256: SHA_PRIMARY }] }), DIGEST);
  expect(hashC !== hashA, "改变风格后 hash 必须变化。");
  const keyOrderA = await promptHash({ b: 2, a: 1 }, DIGEST);
  const keyOrderB = await promptHash({ a: 1, b: 2 }, DIGEST);
  expect(keyOrderA === keyOrderB, "canonicalJson 必须对键序不敏感。");
  expect(json([brief, shot, context]) === before, "编译不得修改输入。");
  return { hash: hashA, changed_hash: hashC };
});

test("G04", "语言策略：指令段无未引用英文；反向探针能变红", async () => {
  const compiled = compileMain();
  expect(checkPromptLanguage(compiled.sections).length === 0, "默认编译必须通过语言检查。");
  const dirty = [{ key: "style_shared", label: "x", kind: "instruction",
    text: "背景保持 clean white background。", source_refs: ["style_spec.background"] }];
  const problems = checkPromptLanguage(dirty);
  expect(problems.length > 0 && /clean|white|background/.test(problems[0].message),
    "未引用英文必须被语言检查抓到：" + json(problems));
  const quoted = [{ key: "style_shared", label: "x", kind: "instruction",
    text: "背景保持「clean white background」。", source_refs: ["style_spec.background"] }];
  expect(checkPromptLanguage(quoted).length === 0, "引用后的英文必须放行。");
  return { dirty_problem: problems[0].message };
});

test("G05", "keep 与 avoid / change_allowed 冲突必须阻断编译", async () => {
  const brief = briefFixture();
  const shot = mainShot();
  const context = contextFixture();
  const base = {
    brief: brief, shot: shot, context: context,
    versions: { suite_version: 3, style_version: 1, shot_spec_version: 1 },
    providerProfile: IMAGE_PROMPT_PROFILE,
  };
  const conflictA = await expectCode(() => compilePrompt({
    ...base,
    styleSpec: styleFixture({ avoid: ["商品居中"] }),
    shotSpec: { ...emptyShotSpecFromShot(shot), keep: ["商品居中"] },
  }), DOMAIN_ERROR_CODES.CONTRACT_INVALID, "keep/avoid 冲突");
  const conflictB = await expectCode(() => compilePrompt({
    ...base,
    styleSpec: styleFixture(),
    shotSpec: { ...emptyShotSpecFromShot(shot), keep: ["商品居中"], change_allowed: ["商品居中"] },
  }), DOMAIN_ERROR_CODES.CONTRACT_INVALID, "keep/change 冲突");
  const unit = checkSpecConflicts(
    { ...emptyShotSpecFromShot(shot), keep: ["柔和顶光"] }, styleFixture({ avoid: ["柔和顶光"] }));
  expect(unit.length > 0, "冲突单元函数必须报红。");
  return { messages: [conflictA.message, conflictB.message] };
});

test("G06", "缺依据的图必须阻断编译并给出原因（复用依赖注册表）", async () => {
  const brief = briefFixture();
  const shot = infographicShot();
  const blocked = await expectCode(() => compilePrompt({
    brief: brief, shot: shot, styleSpec: styleFixture(),
    shotSpec: emptyShotSpecFromShot(shot),
    context: {
      facts: [{ slot_id: "signature_features", status: "proposed", value: ["304不锈钢"] }],
      assets: [{ role: "primary", sha256: SHA_PRIMARY }],
    },
    versions: { suite_version: 1, style_version: 0, shot_spec_version: 0 },
    providerProfile: IMAGE_PROMPT_PROFILE,
  }), DOMAIN_ERROR_CODES.CONTRACT_INVALID, "缺依据");
  expect(/依据|确认/.test(blocked.message), "阻断原因必须能指向缺失依据：" + blocked.message);
  return { message: blocked.message };
});

/* ------------------------------------------------------------ G07..G12 */

test("G07", "绑定事实未确认必须阻断；编译失败不产半成品", async () => {
  const brief = briefFixture();
  const shot = infographicShot({ fact_slot_ids: ["key_material"] });
  const before = json(brief);
  const error = await expectCode(() => compilePrompt({
    brief: brief, shot: shot, styleSpec: styleFixture(),
    shotSpec: emptyShotSpecFromShot(shot),
    context: contextFixture([{ slot_id: "key_material", status: "confirmed", value: "304不锈钢" }]),
    versions: { suite_version: 1, style_version: 0, shot_spec_version: 0 },
    providerProfile: IMAGE_PROMPT_PROFILE,
  }), DOMAIN_ERROR_CODES.CONTRACT_INVALID, "未确认绑定事实");
  expect(/key_material|确认/.test(error.message), "错误必须指名未确认的槽位：" + error.message);
  expect(json(brief) === before, "失败路径不得修改输入。");
  return { message: error.message };
});

test("G08", "未确认事实泄漏：裸文本出现即阻断；引用内不算；冲突值任何位置都阻断", async () => {
  const sections = [{ key: "shot_task", label: "x", kind: "instruction",
    text: "本图任务「主图」，目的「展示商品」。", source_refs: ["suite_plan.shot:shot_main_clean"] }];
  const proposed = [{ slot_id: "key_material", status: "proposed", value: "陶瓷内胆" }];
  expect(checkPromptLeaks(sections, proposed).length === 0, "未出现的提案值不应误报。");
  const leaked = [{ key: "shot_task", label: "x", kind: "instruction",
    text: "本图任务「主图」，采用陶瓷内胆展示。", source_refs: ["suite_plan.shot:shot_main_clean"] }];
  const problems = checkPromptLeaks(leaked, proposed);
  expect(problems.length > 0, "裸文本出现未确认事实必须阻断：" + json(problems));
  const quoted = [{ key: "shot_task", label: "x", kind: "instruction",
    text: "本图任务「主图」，风格「陶瓷内胆」。", source_refs: ["shot_spec.purpose"] }];
  expect(checkPromptLeaks(quoted, proposed).length === 0, "用户自己引用的文本不算泄漏。");
  const conflict = [{ key: "shot_task", label: "x", kind: "instruction",
    text: "本图任务「主图」，风格「陶瓷内胆」。", source_refs: ["shot_spec.purpose"] }];
  const conflictProblems = checkPromptLeaks(conflict,
    [{ slot_id: "key_material", status: "conflict", value: "陶瓷内胆" }]);
  expect(conflictProblems.length > 0, "冲突值出现在任何位置都必须阻断。");
  return { leak: problems[0].message };
});

test("G09", "主图平台覆盖与忽略警告：风格背景被覆盖、绑定事实不叠加", async () => {
  const shot = mainShot({ fact_slot_ids: ["signature_features"] });
  const compiled = compilePrompt({
    brief: briefFixture(), shot: shot, styleSpec: styleFixture(),
    shotSpec: emptyShotSpecFromShot(shot), context: contextFixture(),
    versions: { suite_version: 3, style_version: 1, shot_spec_version: 1 },
    providerProfile: IMAGE_PROMPT_PROFILE,
  });
  const codes = compiled.warnings.map((item) => item.code);
  expect(codes.includes("STYLE_OVERRIDDEN_BY_PLATFORM"), "非白风格背景必须给覆盖警告：" + json(codes));
  expect(codes.includes("MAIN_IMAGE_FACTS_IGNORED"), "主图绑定事实被忽略必须给警告：" + json(codes));
  expect(compiled.text.includes("浅灰无缝背景") === false, "被覆盖的背景不得出现在正文。");
  expect(compiled.text.includes("纯白无缝背景"), "覆盖后正文必须是纯白背景。");
  const refs = compiled.sections.flatMap((item) => item.source_refs);
  expect(refs.includes("style_spec.background"), "覆盖决策必须保留风格来源。");
  return { warnings: codes };
});

test("G10", "图中文字：逐字引用、语言警告、非逐字必被抓住", async () => {
  const brief = briefFixture();
  const shot = infographicShot();
  const compiled = compilePrompt({
    brief: brief, shot: shot, styleSpec: styleFixture(),
    shotSpec: { ...emptyShotSpecFromShot(shot), purpose: "呈现两条核心卖点" },
    context: contextFixture(),
    versions: { suite_version: 3, style_version: 1, shot_spec_version: 1 },
    providerProfile: IMAGE_PROMPT_PROFILE,
  });
  const literal = compiled.sections.find((item) => item.key === "on_image_text");
  expect(Boolean(literal), "卖点信息图必须有图中文字段。");
  expect(literal.items.length === 2, "两条已确认卖点都要逐字进入：" + json(literal.items));
  expect(literal.items.every((item) => item.text.startsWith("「") && item.text.endsWith("」")),
    "文字条目必须带引用。");
  expect(checkLiteralVerbatim(compiled.sections, brief).length === 0, "默认必须逐字通过。");
  const tampered = [{ ...literal, items: [{ text: "「304不锈钢内胆，超长续航」", language: "zh",
    source_ref: "product_brief.fact:signature_features" }] }];
  expect(checkLiteralVerbatim(tampered, brief).length > 0, "改写后的文字必须被抓住。");
  expect(json(compiled.warnings.map((item) => item.code)).includes("ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE"),
    "中文文案与 en 平台不一致时必须给警告。");
  return { items: literal.items, warnings: compiled.warnings.map((item) => item.code) };
});

test("G11", "请求快照与版本记录：prompt 逐字一致、参考图越界报红、记录可机检", async () => {
  const compiled = compileMain();
  const snapshot = requestSnapshotOf(compiled, {
    references: [{ role: "primary", sha256: SHA_PRIMARY }],
  });
  expect(snapshot.prompt === compiled.text, "快照 prompt 必须逐字等于编译文本。");
  expect(snapshot.model === "qwen-image-3.0" && snapshot.size === "1344*1344", "快照必须带模型与尺寸。");
  expect(snapshot.prompt_extend === false && snapshot.watermark === false, "必须禁用 Provider 改写与水印。");
  const hash = await promptHash(snapshot, DIGEST);
  const record = buildPromptRecord({ compiled: compiled, snapshot: snapshot, hash: hash });
  expect(checkPromptRecord(record).length === 0, "记录必须通过机检：" + json(checkPromptRecord(record)));
  const broken = { ...record, request_snapshot: { ...snapshot, prompt: snapshot.prompt + " " } };
  expect(checkPromptRecord(broken).length > 0, "快照与文本不一致必须报红。");
  const tooMany = await expectCode(() => requestSnapshotOf(compiled, {
    references: [1, 2, 3, 4].map((index) => ({ role: "other", sha256: String(index).repeat(64) })),
  }), DOMAIN_ERROR_CODES.CONTRACT_INVALID, "参考图数量越界");
  expect(/1\.\.3|参考图/.test(tooMany.message), "错误必须说明参考图上限：" + tooMany.message);
  return { hash: hash, snapshot_size: snapshot.size };
});

test("G12", "过期机检：只认这张图实际消费的依据；无关槽位不使这张图过期", async () => {
  const compiled = compileMain();
  const snapshot = requestSnapshotOf(compiled, { references: [{ role: "primary", sha256: SHA_PRIMARY }] });
  const record = buildPromptRecord({
    compiled: compiled, snapshot: snapshot, hash: await promptHash(snapshot, DIGEST),
  });
  const current = {
    briefBasis: compiled.basis.brief,
    shot_signature: compiled.basis.shot_signature,
    suite_version: 3,
    style_version: 1,
    shot_spec_version: 1,
    platform: { version: 1 },
    provider: IMAGE_PROMPT_PROFILE,
  };
  expect(promptStaleness(record, current).stale === false, "一致时不应过期。");
  const styleBumped = promptStaleness(record, { ...current, style_version: 2 });
  expect(styleBumped.stale && styleBumped.reasons[0].field === "style_version",
    "风格版本前进必须过期：" + json(styleBumped));
  // 主图只依赖主参考图、不消费任何事实：无关槽位变化不得使这张图过期（V2.R6.2）。
  const unrelatedBumped = promptStaleness(record, {
    ...current,
    briefBasis: [...current.briefBasis, { slot_id: "size_summary", version: 2 }],
  });
  expect(unrelatedBumped.stale === false,
    "未消费的槽位变化不得使这张图过期：" + json(unrelatedBumped));
  // 这张图自己的定义变了 → 过期，原因点名 shot_signature（改别的图不影响本图）。
  const signatureChanged = promptStaleness(record, { ...current, shot_signature: "changed" });
  expect(signatureChanged.stale && signatureChanged.reasons[0].field === "shot_signature",
    "这张图自己的定义变化必须过期：" + json(signatureChanged));
  const providerBumped = promptStaleness(record, {
    ...current, provider: { ...IMAGE_PROMPT_PROFILE, version: IMAGE_PROMPT_PROFILE.version + 1 },
  });
  expect(providerBumped.stale, "Provider 档版本前进必须过期。");
  const paramBumped = promptStaleness(record, {
    ...current, provider: { ...IMAGE_PROMPT_PROFILE, size: "2048*2048" },
  });
  expect(paramBumped.stale && paramBumped.reasons[0].field === "provider",
    "请求参数变化必须过期：" + json(paramBumped));
  const credentialRotated = promptStaleness(record, {
    ...current,
    provider: { ...IMAGE_PROMPT_PROFILE, credential_source: "byok", configured: false },
  });
  expect(credentialRotated.stale === false,
    "纯凭据轮换不得使 Prompt 过期：" + json(credentialRotated));
  const missingField = promptStaleness(record, {
    ...current, provider: { provider_id: "dashscope-qwen-image", model_id: "qwen-image-3.0", version: 1 },
  });
  expect(missingField.stale && missingField.reasons[0].field === "provider",
    "当前档缺字段必须过期：" + json(missingField));
  // 消费该槽位的图：它消费的槽位版本前进 → 过期；它没消费的槽位前进 → 不过期。
  const infoShot = infographicShot();
  const infoCompiled = compileMain({ shot: infoShot, shotSpec: emptyShotSpecFromShot(infoShot) });
  const infoSnapshot = requestSnapshotOf(infoCompiled,
    { references: [{ role: "primary", sha256: SHA_PRIMARY }] });
  const infoRecord = buildPromptRecord({
    compiled: infoCompiled, snapshot: infoSnapshot, hash: await promptHash(infoSnapshot, DIGEST),
  });
  expect(json(infoCompiled.basis.brief) === json([{ slot_id: "signature_features", version: 1 }]),
    "信息图只消费它用到的已确认事实：" + json(infoCompiled.basis.brief));
  const infoCurrent = {
    briefBasis: infoCompiled.basis.brief,
    shot_signature: infoCompiled.basis.shot_signature,
    suite_version: 3, style_version: 1, shot_spec_version: 1,
    platform: { version: 1 }, provider: IMAGE_PROMPT_PROFILE,
  };
  const consumedBumped = promptStaleness(infoRecord, {
    ...infoCurrent,
    briefBasis: infoCurrent.briefBasis.map((item) =>
      item.slot_id === "signature_features" ? { ...item, version: 2 } : item),
  });
  expect(consumedBumped.stale && consumedBumped.reasons.some((item) =>
    item.field === "brief.signature_features"),
  "消费的槽位版本前进必须过期：" + json(consumedBumped));
  expect(checkPromptLanguage(compiled.sections).length === 0, "回归：默认编译仍满足语言策略。");
  return { style: styleBumped.reasons, info_basis: infoCompiled.basis.brief };
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
