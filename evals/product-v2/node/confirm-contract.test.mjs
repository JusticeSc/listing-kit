/**
 * V2.3.5 生成前确认契约测试（Node 原生进程，非 Mock）。
 *
 * 正向：正常确认单、外发摘要与请求快照一致、确认记录、指纹稳定性、确认后失效判定。
 * 反向（故意让守卫变红）：缺 Prompt、Prompt 过期、依赖不满足、Provider/平台不符、
 * 参考图数量越界、风险传播、计数与摘要篡改、缺依据不支持、不能确认被阻断的清单。
 *
 * 直接运行：node --test evals/product-v2/node/
 */

import {
  CONFIRM_BLOCKER_CODES,
  DOMAIN_ERROR_CODES,
  PLATFORM_PROFILES,
  buildConfirmationRecord,
  buildConfirmationSheet,
  buildPromptRecord,
  checkConfirmationRecord,
  checkConfirmationSheet,
  compilePrompt,
  confirmationSnapshot,
  confirmationSnapshotJson,
  confirmationStaleness,
  emptyShotSpecFromShot,
  emptyStyleSpec,
  promptHash,
  requestSnapshotOf,
  selectReferences,
} from "../../../app/product_v2/domain/index.js";

import { sha256Hex } from "../../../app/product_v2/storage/db.js";
import { IMAGE_PROMPT_PROFILE, expect, expectCode, serializeError } from "./harness-core.mjs";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

const SHA_PRIMARY = "a".repeat(64);
const SHA_COMPETITOR = "b".repeat(64);
const PROVIDER_ID = "qwen-image-3.0";
const PLATFORM_ID = "amazon_us";
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

/** 默认上下文只有主图素材：竞品素材在需要时显式加入，保证“缺依赖”可以被反向触发。 */
function contextFixture(extra = {}) {
  return {
    facts: [
      { slot_id: "product_name", status: "confirmed", value: "便携保温杯" },
      { slot_id: "product_category", status: "confirmed", value: "保温杯" },
      { slot_id: "signature_features", status: "confirmed", value: ["304不锈钢内胆", "12小时保温"] },
      { slot_id: "size_summary", status: "confirmed", value: "500ml" },
    ],
    assets: [{ role: "primary", sha256: SHA_PRIMARY }],
    ...extra,
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

function comparisonShot(overrides = {}) {
  return {
    shot_id: "shot_comparison_competitor",
    template_id: "comparison_competitor",
    role_id: "comparison",
    label: "对比图·竞品同框",
    intent: "与竞品同框对比已确认差异，不贬低竞品或编造参数",
    required: false,
    custom: false,
    dependencies: [
      { kind: "asset_role", role: "competitor" },
      { kind: "fact", slot_id: "signature_features" },
    ],
    fact_slot_ids: ["signature_features"],
    ...overrides,
  };
}

function planFixture(shots) {
  return { schema_version: 1, shots: shots || [mainShot(), infographicShot()] };
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

function basisFixture(options = {}) {
  return {
    briefBasis: briefFixture().basis,
    suite_version: options.suiteVersion === undefined ? 1 : options.suiteVersion,
    style_version: options.styleVersion === undefined ? 1 : options.styleVersion,
    shot_spec_version: options.shotSpecVersion === undefined ? null : options.shotSpecVersion,
    platform: { version: PLATFORM_PROFILES[PLATFORM_ID].version },
    provider: options.providerProfile || IMAGE_PROMPT_PROFILE,
  };
}

/** 编译 + 快照 + hash + 版本记录：与 workspace.js 的真实链路同一套调用。 */
async function compileEntry(shot, options = {}) {
  const context = options.context || contextFixture();
  const compiled = compilePrompt({
    brief: briefFixture(),
    shot: shot,
    styleSpec: options.styleSpec || styleFixture(),
    shotSpec: emptyShotSpecFromShot(shot),
    context: context,
    providerProfile: IMAGE_PROMPT_PROFILE,
    versions: {
      suite_version: options.suiteVersion === undefined ? 1 : options.suiteVersion,
      style_version: options.styleVersion === undefined ? 1 : options.styleVersion,
      shot_spec_version: options.shotSpecVersion === undefined ? null : options.shotSpecVersion,
    },
  });
  const references = selectReferences(shot, context.assets);
  const snapshot = requestSnapshotOf(compiled, { references: references });
  const hash = await promptHash(snapshot, DIGEST);
  return {
    shot_id: shot.shot_id,
    version: options.version === undefined ? 1 : options.version,
    record: buildPromptRecord({ compiled: compiled, snapshot: snapshot, hash: hash }),
  };
}

function sheetOf(options = {}) {
  const plan = options.plan || planFixture();
  const providerProfile = options.providerProfile || IMAGE_PROMPT_PROFILE;
  const basisByShot = {};
  for (const shot of plan.shots) {
    basisByShot[shot.shot_id] = basisFixture({
      styleVersion: options.styleVersion,
      suiteVersion: options.suiteVersion,
      shotSpecVersion: (options.shotSpecVersions || {})[shot.shot_id],
      providerProfile: providerProfile,
    });
  }
  if (options.basisOverride) Object.assign(basisByShot, options.basisOverride);
  return buildConfirmationSheet({
    suitePlan: plan,
    promptEntries: options.entries || [],
    context: options.context || contextFixture(),
    currentBasisByShot: basisByShot,
    platformId: options.platformId || PLATFORM_ID,
    providerProfile: providerProfile,
  });
}

function codesOfShot(sheet, shotId) {
  const item = sheet.shots.find((entry) => entry.shot_id === shotId);
  return item ? item.blockers.map((blocker) => blocker.code) : [];
}

function fixesOf(sheet, shotId) {
  const item = sheet.shots.find((entry) => entry.shot_id === shotId);
  return item ? item.blockers.map((blocker) => blocker.fix) : [];
}

function copyRecord(entry, mutate) {
  const clone = JSON.parse(JSON.stringify({ shot_id: entry.shot_id, version: entry.version, record: entry.record }));
  mutate(clone.record);
  return clone;
}

/* ---------------------------------------------------------------- 正向 */

test("H01", "全部就绪：can_submit、计数与外发摘要与请求快照一致", async () => {
  const plan = planFixture();
  const entries = [await compileEntry(plan.shots[0]), await compileEntry(plan.shots[1])];
  const sheet = sheetOf({ plan: plan, entries: entries });
  const problems = checkConfirmationSheet(sheet);
  expect(problems.length === 0, "确认单自检必须通过：" + JSON.stringify(problems.slice(0, 2)));
  expect(sheet.can_submit === true && sheet.ready === 2 && sheet.blocked === 0, "两张图应全部就绪。");
  const expectedRefs = entries.reduce((total, entry) => total + entry.record.request_snapshot.references.length, 0);
  const expectedChars = entries.reduce((total, entry) => total + entry.record.compiled.text.length, 0);
  expect(sheet.external_summary.reference_count === expectedRefs, "参考图数量必须等于快照合计。");
  expect(sheet.external_summary.prompt_chars === expectedChars, "提示词字符数必须等于记录文本合计。");
  expect(sheet.external_summary.model === PROVIDER_ID, "外发摘要必须写真实模型。");
  expect(sheet.external_summary.statement.includes(PROVIDER_ID), "摘要句必须写明模型。");
  expect(sheet.shots.every((item) => item.prompt.version === 1 && item.prompt.hash.length === 64), "每图必须带版本与 hash。");
  return { summary: sheet.external_summary };
});

test("H02", "确定性：同一输入两次构建与键序变化产生相同指纹", async () => {
  const plan = planFixture();
  const entries = [await compileEntry(plan.shots[0]), await compileEntry(plan.shots[1])];
  const first = sheetOf({ plan: plan, entries: entries });
  const second = sheetOf({ plan: plan, entries: entries });
  const reorderShot = (shot) => {
    const out = {};
    for (const key of Object.keys(shot).reverse()) out[key] = shot[key];
    return out;
  };
  const reorderedPlan = { shots: plan.shots.map(reorderShot), schema_version: 1 };
  const third = sheetOf({ plan: reorderedPlan, entries: entries.slice().reverse() });
  expect(confirmationSnapshotJson(first) === confirmationSnapshotJson(second), "相同输入必须产生相同指纹。");
  expect(confirmationSnapshotJson(first) === confirmationSnapshotJson(third), "键序与数组顺序不得改变指纹。");
  const hash = await promptHash(confirmationSnapshot(first), DIGEST);
  expect(/^[0-9a-f]{64}$/.test(hash), "指纹必须可注入 sha256。");
  return { hash: hash };
});

/* ---------------------------------------------------------------- 反向 */

test("H03", "缺 Prompt：阻断并定位到具体图片与 Prompt 区", async () => {
  const plan = planFixture();
  const entries = [await compileEntry(plan.shots[0])];
  const sheet = sheetOf({ plan: plan, entries: entries });
  expect(sheet.can_submit === false && sheet.blocked === 1, "缺一张 Prompt 必须阻断。");
  expect(codesOfShot(sheet, "shot_infographic_benefits").includes(CONFIRM_BLOCKER_CODES.PROMPT_MISSING), "缺 Prompt 必须有对应阻断码。");
  const fix = fixesOf(sheet, "shot_infographic_benefits")[0];
  expect(fix.region === "prompt" && fix.shot_id === "shot_infographic_benefits", "fix 必须指到该图的 Prompt 区。");
  expect(fixesOf(sheet, "shot_main_clean").length === 0, "已就绪的图不应有阻断。");
  return { blockers: sheet.blockers.map((item) => item.code + "@" + item.shot_id) };
});

test("H04", "Prompt 过期：风格前进后阻断并定位到风格区", async () => {
  const plan = planFixture();
  const entries = [await compileEntry(plan.shots[0]), await compileEntry(plan.shots[1])];
  const fresh = sheetOf({ plan: plan, entries: entries });
  expect(fresh.can_submit === true, "前置条件：先有一张可提交清单。");
  const stale = sheetOf({ plan: plan, entries: entries, styleVersion: 2 });
  expect(stale.can_submit === false && stale.blocked === 2, "风格前进必须让两张图都过期。");
  const fix = fixesOf(stale, "shot_main_clean")[0];
  expect(fix.region === "style", "过期原因是风格时必须指到风格区，实际 " + fix.region);
  return { fix: fix };
});

test("H05", "缺依赖：对比图没有竞品素材时阻断并定位到套图规划", async () => {
  const plan = planFixture([mainShot(), infographicShot(), comparisonShot()]);
  const fullContext = contextFixture({
    assets: [{ role: "primary", sha256: SHA_PRIMARY }, { role: "competitor", sha256: SHA_COMPETITOR }],
  });
  const entries = [
    await compileEntry(plan.shots[0], { context: fullContext }),
    await compileEntry(plan.shots[1]),
    await compileEntry(plan.shots[2], { context: fullContext }),
  ];
  const sheet = sheetOf({ plan: plan, entries: entries });
  expect(sheet.blocked === 1 && sheet.total === 3, "只有缺依赖的对比图应被阻断。");
  expect(codesOfShot(sheet, "shot_comparison_competitor").includes(CONFIRM_BLOCKER_CODES.DEPENDENCY_UNSATISFIED), "必须有依赖阻断码。");
  const fix = fixesOf(sheet, "shot_comparison_competitor")[0];
  expect(fix.region === "suite", "依赖阻断必须指回套图规划。");
  const withCompetitor = sheetOf({ plan: plan, entries: entries, context: fullContext });
  expect(withCompetitor.can_submit === true, "补上竞品素材后应可提交。");
  return { without: sheet.blocked, with: withCompetitor.ready };
});

test("H06", "Provider 或平台不符：记录被改后不能提交", async () => {
  const plan = planFixture([mainShot()]);
  const entry = await compileEntry(plan.shots[0]);
  // 当前有效档前进（能力版本不同）→ 冻结档与当前档不符
  const bumpedProfile = { ...IMAGE_PROMPT_PROFILE, version: IMAGE_PROMPT_PROFILE.version + 1 };
  const providerSheet = sheetOf({ plan: plan, entries: [entry], providerProfile: bumpedProfile });
  expect(codesOfShot(providerSheet, "shot_main_clean").includes(CONFIRM_BLOCKER_CODES.PROVIDER_MISMATCH), "Provider 版本不符必须阻断。");
  // 请求参数不同（同版本）同样必须阻断，而不是只看版本号
  const paramSheet = sheetOf({ plan: plan, entries: [entry], providerProfile: { ...IMAGE_PROMPT_PROFILE, size: "2048*2048" } });
  expect(codesOfShot(paramSheet, "shot_main_clean").includes(CONFIRM_BLOCKER_CODES.PROVIDER_MISMATCH), "请求参数不符必须阻断。");
  // 冻结档被改但快照 target 未同步 → 记录自检必须判红（先于确认单比较）
  const tampered = copyRecord(entry, (record) => { record.compiled.provider.version = 2; });
  const tamperedSheet = sheetOf({ plan: plan, entries: [tampered] });
  expect(codesOfShot(tamperedSheet, "shot_main_clean").includes(CONFIRM_BLOCKER_CODES.PROMPT_RECORD_INVALID), "冻结档与快照 target 不符必须判记录无效。");
  const platformChanged = copyRecord(entry, (record) => { record.compiled.platform.platform_id = "amazon_de"; });
  const platformSheet = sheetOf({ plan: plan, entries: [platformChanged] });
  expect(codesOfShot(platformSheet, "shot_main_clean").includes(CONFIRM_BLOCKER_CODES.PLATFORM_MISMATCH), "平台不符必须阻断。");
  return { provider: providerSheet.blocked, platform: platformSheet.blocked };
});

test("H07", "参考图越界：0 张与 4 张都不能提交", async () => {
  const plan = planFixture([mainShot()]);
  const entry = await compileEntry(plan.shots[0]);
  const emptyRefs = copyRecord(entry, (record) => { record.request_snapshot.references = []; });
  const tooMany = copyRecord(entry, (record) => {
    record.request_snapshot.references = ["a", "b", "c", "d"].map((letter) => ({ role: "primary", sha256: letter.repeat(64) }));
  });
  const emptySheet = sheetOf({ plan: plan, entries: [emptyRefs] });
  const manySheet = sheetOf({ plan: plan, entries: [tooMany] });
  expect(codesOfShot(emptySheet, "shot_main_clean").includes(CONFIRM_BLOCKER_CODES.REFERENCE_COUNT_INVALID), "0 张参考图必须阻断。");
  expect(codesOfShot(manySheet, "shot_main_clean").includes(CONFIRM_BLOCKER_CODES.REFERENCE_COUNT_INVALID), "4 张参考图必须阻断。");
  return { empty: emptySheet.blocked, many: manySheet.blocked };
});

test("H08", "风险传播：编译警告进入确认单且带归口图片", async () => {
  const plan = planFixture();
  const entries = [await compileEntry(plan.shots[0]), await compileEntry(plan.shots[1])];
  const withExtra = entries.map((item) => item.shot_id === "shot_main_clean"
    ? copyRecord(item, (record) => {
        record.compiled.warnings = record.compiled.warnings.concat([{ code: "STYLE_OVERRIDDEN_BY_PLATFORM", message: "平台规则覆盖了风格背景。" }]);
      })
    : item);
  const sheet = sheetOf({ plan: plan, entries: withExtra });
  const codes = sheet.risks.map((risk) => risk.code + "@" + risk.shot_id);
  expect(codes.includes("ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE@shot_infographic_benefits"), "图中文案语言风险必须传播，实际 " + JSON.stringify(codes));
  expect(codes.includes("STYLE_OVERRIDDEN_BY_PLATFORM@shot_main_clean"), "平台覆盖风险必须传播。");
  expect(sheet.can_submit === true, "风险不是阻断：仍可提交但必须可见。");
  return { risks: codes };
});

test("H09", "外发摘要只列角色与 hash 前缀，且与每条请求快照一致", async () => {
  const plan = planFixture();
  const entries = [await compileEntry(plan.shots[0]), await compileEntry(plan.shots[1])];
  const sheet = sheetOf({ plan: plan, entries: entries });
  for (const item of sheet.shots) {
    const entry = entries.find((candidate) => candidate.shot_id === item.shot_id);
    const snapshot = entry.record.request_snapshot;
    expect(item.references.length === snapshot.references.length, "参考图数量必须与快照一致。");
    item.references.forEach((ref, index) => {
      expect(ref.role === snapshot.references[index].role, "参考图角色必须与快照一致。");
      expect(ref.sha256_prefix === snapshot.references[index].sha256.slice(0, 12), "只允许写 hash 前缀。");
      expect(ref.sha256_prefix.length === 12, "前缀长度固定 12。");
    });
  }
  const text = JSON.stringify(sheet);
  for (const entry of entries) {
    expect(!text.includes(entry.record.request_snapshot.references[0].sha256), "完整参考图 hash 不得出现在人读确认单。");
  }
  return { sha256_prefix: sheet.shots[0].references[0].sha256_prefix, roles: sheet.external_summary.reference_roles };
});

test("H10", "确认记录：只在可提交清单上建立，且形状可机检", async () => {
  const plan = planFixture();
  const entries = [await compileEntry(plan.shots[0]), await compileEntry(plan.shots[1])];
  const sheet = sheetOf({ plan: plan, entries: entries });
  const hash = await promptHash(confirmationSnapshot(sheet), DIGEST);
  const record = buildConfirmationRecord({ sheet: sheet, hash: hash, confirmedAt: new Date().toISOString() });
  const problems = checkConfirmationRecord(record);
  expect(problems.length === 0, "合法确认记录必须通过自检：" + JSON.stringify(problems.slice(0, 2)));
  expect(record.fingerprint.snapshot.can_submit === true, "记录必须绑定可提交快照。");
  expect(record.shots.length === 2 && record.shots.every((item) => item.prompt_hash.length === 64), "记录必须包含每图指纹。");
  const blockedSheet = sheetOf({ plan: plan, entries: [entries[0]] });
  await expectCode(async () => {
    buildConfirmationRecord({ sheet: blockedSheet, hash: hash, confirmedAt: new Date().toISOString() });
  }, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "被阻断的清单不得建立确认记录");
  const broken = JSON.parse(JSON.stringify(record));
  delete broken.fingerprint;
  expect(checkConfirmationRecord(broken).length > 0, "缺指纹的记录必须不自检通过。");
  return { version: 1, hash: record.fingerprint.hash };
});

test("H11", "确认失效：上游变化或 Prompt 前进后必须重新确认", async () => {
  const plan = planFixture();
  const entries = [await compileEntry(plan.shots[0]), await compileEntry(plan.shots[1])];
  const sheet = sheetOf({ plan: plan, entries: entries });
  const hash = await promptHash(confirmationSnapshot(sheet), DIGEST);
  const record = buildConfirmationRecord({ sheet: sheet, hash: hash, confirmedAt: new Date().toISOString() });
  const same = confirmationStaleness(record, confirmationSnapshot(sheetOf({ plan: plan, entries: entries })));
  expect(same.stale === false, "同一清单必须判定为未失效。");
  const bumped = confirmationStaleness(record, confirmationSnapshot(sheetOf({ plan: plan, entries: entries, styleVersion: 2 })));
  expect(bumped.stale === true, "风格前进后确认必须失效。");
  const fields = bumped.reasons.map((reason) => reason.field);
  expect(fields.some((field) => field === "shots.shot_main_clean"), "失效原因必须指到具体图片，实际 " + JSON.stringify(fields));
  const recompiled = [await compileEntry(plan.shots[0], { styleVersion: 2, version: 2 }), await compileEntry(plan.shots[1], { styleVersion: 2, version: 2 })];
  const afterSheet = sheetOf({ plan: plan, entries: recompiled, styleVersion: 2 });
  const afterBump = confirmationStaleness(record, confirmationSnapshot(afterSheet));
  expect(afterBump.stale === true, "重新编译后相对旧确认仍应判定为变化。");
  const newRecord = buildConfirmationRecord({
    sheet: afterSheet,
    hash: await promptHash(confirmationSnapshot(afterSheet), DIGEST),
    confirmedAt: new Date().toISOString(),
  });
  const stable = confirmationStaleness(newRecord, confirmationSnapshot(sheetOf({ plan: plan, entries: recompiled, styleVersion: 2 })));
  expect(stable.stale === false, "重新确认后必须回到未失效。");
  return { fields: fields };
});

/* ---------------------------------------------------------------- 反向探针 */

test("H12", "反向探针：计数、fix、摘要与输入错误都必须变红", async () => {
  const plan = planFixture();
  const entries = [await compileEntry(plan.shots[0]), await compileEntry(plan.shots[1])];
  const sheet = sheetOf({ plan: plan, entries: entries });
  const badCount = JSON.parse(JSON.stringify(sheet));
  badCount.total = 5;
  expect(checkConfirmationSheet(badCount).length > 0, "计数篡改必须被机检发现。");
  const badFix = JSON.parse(JSON.stringify(sheet));
  badFix.shots[0].blockers.push({ code: "X", message: "x" });
  expect(checkConfirmationSheet(badFix).length > 0, "阻断缺 fix 必须被机检发现。");
  const badSummary = JSON.parse(JSON.stringify(sheet));
  badSummary.external_summary.prompt_chars = badSummary.external_summary.prompt_chars + 1;
  expect(checkConfirmationSheet(badSummary).length > 0, "摘要与逐图不一致必须被机检发现。");
  await expectCode(async () => { buildConfirmationSheet({}); }, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "缺套图计划必须拒绝");
  const noBasis = buildConfirmationSheet({
    suitePlan: plan, promptEntries: entries, context: contextFixture(), currentBasisByShot: {},
    providerProfile: IMAGE_PROMPT_PROFILE,
  });
  expect(noBasis.can_submit === false, "没有当前依据时不能提交。");
  expect(codesOfShot(noBasis, "shot_main_clean").includes(CONFIRM_BLOCKER_CODES.PROMPT_STALE), "缺依据必须按过期处理。");
  return { probes: 5 };
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
