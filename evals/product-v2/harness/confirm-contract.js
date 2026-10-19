/**
 * V2.3.5 生成前确认契约测试（真实 Chromium，非 Mock）。
 *
 * 正向：正常确认单、外发摘要与请求快照一致、确认记录、指纹稳定性、确认后失效判定。
 * 反向（故意让守卫变红）：缺 Prompt、Prompt 过期、依赖不满足、Provider/平台不符、
 * 参考图数量越界、风险传播、计数与摘要篡改、缺依据不支持、不能确认被阻断的清单。
 *
 * 结果写到 window.__V2_CONFIRM_RESULTS__，由 tools/verify_v2_3_5_pre_generation_confirm.py 读取。
 */

import {
  CONFIRM_BLOCKER_CODES,
  CONFIRM_SCHEMA_VERSIONS_LEGACY,
  canonicalJson,
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
} from "/domain/index.js";

import { sha256Hex } from "/storage/db.js";
import { IMAGE_PROMPT_PROFILE, expect, expectCode, serializeError } from "./harness-api.js";

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
    // 夹具的显式展示决定：缺失会被新门阻断（「还要先决定『外观状态』」），与印字决定无关。
    presentation: { appearance_state: "as_shown", contents_state: "not_applicable" },
    ...overrides,
  };
}

function basisFixture(options = {}) {
  return {
    briefBasis: briefFixture().basis,
    suite_version: options.suiteVersion === undefined ? 1 : options.suiteVersion,
    style_version: options.styleVersion === undefined ? 1 : options.styleVersion,
    shot_spec_version: options.shotSpecVersion === undefined ? null : options.shotSpecVersion,
    // 只有显式给出时才带商品资料版本：其余用例的口径不变（调用方不给就是不比这一项）。
    ...(options.intakeVersion === undefined ? {} : { intake_version: options.intakeVersion }),
    platform: { version: PLATFORM_PROFILES[PLATFORM_ID].version },
    provider: options.providerProfile || IMAGE_PROMPT_PROFILE,
  };
}

/** 不印新增文字的规格：只关心 Prompt 就绪/计数/摘要/失效的用例用它，把印字决定显式设为 none，避免未决定门干扰它们真正要测的东西。 */
function noPrintSpec(shot, overrides = {}) {
  return { ...emptyShotSpecFromShot(shot), print_intent: "none", ...overrides };
}

/** 明确选择的图中文案：来源必须是本套件 briefFixture() 的已确认事实（slot 与版本精确一致），用于走「用户所选文案」真实路径。 */
function chosenPrintSpec(shot, overrides = {}) {
  return {
    ...emptyShotSpecFromShot(shot),
    print_intent: "selected",
    // 新门：要印文案必须同时给出能承载文字的版面；该用例测的是语言风险传播，不测版面选择，所以固定给左图右文。
    layout: "product_left_text_right",
    on_image_texts: [
      {
        text_id: "t_sig_1",
        text: "304不锈钢内胆",
        source: { kind: "fact_slot", document_id: "signature_features", version: 1 },
        status: "confirmed",
        origin: "user",
      },
    ],
    ...overrides,
  };
}

/** 已保存的商品资料版本（冻结参考图来源的精确版本；与产品调用方同一快照概念）。 */
const INTAKE_VERSION = 1;

/** 编译 + 快照 + hash + 版本记录：与 workspace.js 的真实链路同一套调用。 */
async function compileEntry(shot, options = {}) {
  const context = options.context || contextFixture();
  const shotSpec = options.shotSpec || emptyShotSpecFromShot(shot);
  const compiled = compilePrompt({
    brief: briefFixture(),
    shot: shot,
    styleSpec: options.styleSpec || styleFixture(),
    shotSpec: shotSpec,
    context: context,
    providerProfile: IMAGE_PROMPT_PROFILE,
    versions: {
      suite_version: options.suiteVersion === undefined ? 1 : options.suiteVersion,
      style_version: options.styleVersion === undefined ? 1 : options.styleVersion,
      shot_spec_version: options.shotSpecVersion === undefined ? null : options.shotSpecVersion,
      intake_version: options.intakeVersion,
    },
  });
  const references = selectReferences(shot, context.assets,
    { intakeVersion: INTAKE_VERSION, shotSpec: shotSpec });
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
      intakeVersion: options.intakeVersion,
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
  // 只测就绪/计数/摘要，不关心印字：信息图用不印新增文字显式决定，避免未决定门干扰。
  const entries = [await compileEntry(plan.shots[0]), await compileEntry(plan.shots[1], { shotSpec: noPrintSpec(plan.shots[1]) })];
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
  // 只测指纹确定性，不关心印字：信息图用不印新增文字显式决定。
  const entries = [await compileEntry(plan.shots[0]), await compileEntry(plan.shots[1], { shotSpec: noPrintSpec(plan.shots[1]) })];
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
  // 只测风格过期，不关心印字：信息图用不印新增文字显式决定。
  const entries = [await compileEntry(plan.shots[0]), await compileEntry(plan.shots[1], { shotSpec: noPrintSpec(plan.shots[1]) })];
  const fresh = sheetOf({ plan: plan, entries: entries });
  expect(fresh.can_submit === true, "前置条件：先有一张可提交清单。");
  const stale = sheetOf({ plan: plan, entries: entries, styleVersion: 2 });
  expect(stale.can_submit === false && stale.blocked === 2, "风格前进必须让两张图都过期。");
  const fix = fixesOf(stale, "shot_main_clean")[0];
  expect(fix.region === "style", "过期原因是风格时必须指到风格区，实际 " + fix.region);
  return { fix: fix };
});

test("H13", "商品资料前进：确认单与提交门同一判据，阻断并指到 Prompt 区", async () => {
  const plan = planFixture();
  // 只测资料版本过期：信息图用不印新增文字显式决定，避免未决定门干扰。
  const entries = [
    await compileEntry(plan.shots[0], { intakeVersion: INTAKE_VERSION }),
    await compileEntry(plan.shots[1], { shotSpec: noPrintSpec(plan.shots[1]), intakeVersion: INTAKE_VERSION }),
  ];
  const fresh = sheetOf({ plan: plan, entries: entries, intakeVersion: INTAKE_VERSION });
  expect(fresh.can_submit === true,
    "前置条件：资料版本一致时可提交：" + JSON.stringify(fresh.blockers.slice(0, 2)));
  // 用户改了商品资料并保存（版本 +1）：提交门按冻结引用全等比较会拒绝；
  // 确认单必须用同一条判据如实阻断，不能让用户走到「确认单说可提交 → 提交被拒」。
  const advanced = sheetOf({ plan: plan, entries: entries, intakeVersion: INTAKE_VERSION + 1 });
  expect(advanced.can_submit === false && advanced.blocked === 2,
    "商品资料前进必须让两张图都待重新编译：" + JSON.stringify(advanced.blockers.slice(0, 2)));
  expect(codesOfShot(advanced, "shot_main_clean").includes(CONFIRM_BLOCKER_CODES.PROMPT_STALE),
    "必须是 PROMPT_STALE：" + JSON.stringify(codesOfShot(advanced, "shot_main_clean")));
  const fix = fixesOf(advanced, "shot_main_clean")[0];
  expect(fix.region === "prompt" && fix.shot_id === "shot_main_clean" && /商品资料/.test(String(fix.action || "")),
    "fix 必须指到 Prompt 区并说明是商品资料前进，实际 " + JSON.stringify(fix));
  return { fix: fix };
});

test("H05", "缺依赖：对比图没有竞品素材时阻断并定位到套图规划", async () => {
  const plan = planFixture([mainShot(), infographicShot(), comparisonShot()]);
  const fullContext = contextFixture({
    assets: [{ role: "primary", sha256: SHA_PRIMARY }, { role: "competitor", sha256: SHA_COMPETITOR }],
  });
  // 只测缺依赖阻断，不关心印字：信息图/对比图都用不印新增文字显式决定。
  // 对比图显式选中「主图商品依据 + 竞品」：确认单要的是缺依赖阻断，
  // 不能让参考选择先因缺主图依据而失败。
  const comparisonSpec = noPrintSpec(plan.shots[2],
    { reference_sha256s: [SHA_PRIMARY, SHA_COMPETITOR] });
  const entries = [
    await compileEntry(plan.shots[0], { context: fullContext }),
    await compileEntry(plan.shots[1], { shotSpec: noPrintSpec(plan.shots[1]) }),
    await compileEntry(plan.shots[2], { context: fullContext, shotSpec: comparisonSpec }),
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
  // 历史只读记录（schema1：简单引用、无冻结元数据）只走确认单自己的计数门，
  // 不走新记录的冻结自检：0 张与 4 张都在这里被 REFERENCE_COUNT_INVALID 拦截。
  const legacyOf = (references) => copyRecord(entry, (record) => {
    record.schema_version = 1;
    record.request_snapshot.references = references;
  });
  const emptyRefs = legacyOf([]);
  const tooMany = legacyOf(["a", "b", "c", "d"].map((letter) => ({ role: "primary", sha256: letter.repeat(64) })));
  const emptySheet = sheetOf({ plan: plan, entries: [emptyRefs] });
  const manySheet = sheetOf({ plan: plan, entries: [tooMany] });
  expect(codesOfShot(emptySheet, "shot_main_clean").includes(CONFIRM_BLOCKER_CODES.REFERENCE_COUNT_INVALID), "0 张参考图必须阻断。");
  expect(codesOfShot(manySheet, "shot_main_clean").includes(CONFIRM_BLOCKER_CODES.REFERENCE_COUNT_INVALID), "4 张参考图必须阻断。");
  return { empty: emptySheet.blocked, many: manySheet.blocked };
});

test("H08", "风险传播：编译警告进入确认单且带归口图片", async () => {
  const plan = planFixture();
  // 语言风险必须来自「用户所选文案」：信息图显式选择一条中文已确认事实原文（signature_features/版本1），而不是旧自动枚举事实。
  const entries = [await compileEntry(plan.shots[0]), await compileEntry(plan.shots[1], { shotSpec: chosenPrintSpec(plan.shots[1]) })];
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
  // 只测摘要形状，不关心印字：信息图用不印新增文字显式决定。
  const entries = [await compileEntry(plan.shots[0]), await compileEntry(plan.shots[1], { shotSpec: noPrintSpec(plan.shots[1]) })];
  const sheet = sheetOf({ plan: plan, entries: entries });
  for (const item of sheet.shots) {
    const entry = entries.find((candidate) => candidate.shot_id === item.shot_id);
    const snapshot = entry.record.request_snapshot;
    expect(item.references.length === snapshot.references.length, "参考图数量必须与快照一致。");
    item.references.forEach((ref, index) => {
      expect(ref.role === snapshot.references[index].role, "参考图角色必须与快照一致。");
    });
  }
  // 新确认单携带完整 sha256（快照投影同源），但人读字段
  // （statement/label）与界面渲染只出现 12 位前缀；完整 hash 不进人读文案。
  const readable = JSON.stringify([sheet.external_summary.statement,
    ...sheet.shots.map((item) => item.label)]);
  for (const entry of entries) {
    expect(!readable.includes(entry.record.request_snapshot.references[0].sha256), "完整参考图 hash 不得出现在人读确认单。");
  }
  sheet.shots.forEach((item) => item.references.forEach((ref) => {
    expect(ref.sha256_prefix === String(ref.sha256).slice(0, 12), "展示前缀必须与完整身份一致。");
  }));
  return { roles: sheet.external_summary.reference_roles };
});

test("H10", "确认记录：只在可提交清单上建立，且形状可机检", async () => {
  const plan = planFixture();
  // 只测确认记录形状，不关心印字：信息图用不印新增文字显式决定。
  const entries = [await compileEntry(plan.shots[0]), await compileEntry(plan.shots[1], { shotSpec: noPrintSpec(plan.shots[1]) })];
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
  // 新记录逐图引用被改成与指纹快照不一致（用途/来源篡改或缺失）必须变红。
  const tamperedUses = JSON.parse(JSON.stringify(record));
  tamperedUses.shots[0].references[0].uses = ["style_reference"];
  expect(checkConfirmationRecord(tamperedUses).length > 0, "用途与快照不一致必须不自检通过。");
  const droppedMetadata = JSON.parse(JSON.stringify(record));
  delete droppedMetadata.shots[0].references[0].uses;
  delete droppedMetadata.shots[0].references[0].sources;
  expect(checkConfirmationRecord(droppedMetadata).length > 0, "缺冻结元数据必须不自检通过。");
  const tamperedSnapshot = JSON.parse(JSON.stringify(record));
  delete tamperedSnapshot.fingerprint.snapshot.shots[0].references[0].uses;
  expect(checkConfirmationRecord(tamperedSnapshot).length > 0, "快照引用缺冻结元数据必须不自检通过。");
  for (const version of CONFIRM_SCHEMA_VERSIONS_LEGACY) {
    const legacy = structuredClone(record);
    legacy.schema_version = version;
    legacy.fingerprint.snapshot.schema_version = version;
    for (const shot of legacy.fingerprint.snapshot.shots) {
      if (version === 1) {
        shot.reference_roles = shot.references.map(ref => ref.role);
        delete shot.references;
      } else {
        shot.references = shot.references.map(ref => ({ role: ref.role, sha256: ref.sha256 }));
      }
    }
    for (const shot of legacy.shots) {
      shot.references = shot.references.map(ref => ({ role: ref.role,
        sha256_prefix: ref.sha256_prefix, ...(version === 2 ? { sha256: ref.sha256 } : {}) }));
    }
    legacy.fingerprint.hash = await promptHash(legacy.fingerprint.snapshot, DIGEST);
    const frozen = canonicalJson(legacy);
    expect(checkConfirmationRecord(legacy).length === 0,
      "既有角色/身份快照必须仍可只读恢复：" + JSON.stringify(checkConfirmationRecord(legacy)));
    expect(canonicalJson(legacy) === frozen, "读取不得回填用途/来源或改写历史指纹。");
    expect(confirmationStaleness(legacy, confirmationSnapshot(sheet)).stale,
      "旧授权不能替代新请求完整冻结来源的明确确认。");
  }
  const oldSnapshot = structuredClone(record);
  oldSnapshot.fingerprint.snapshot.schema_version = 2;
  expect(checkConfirmationRecord(oldSnapshot).length > 0, "新记录不能绑定旧格式指纹快照。");
  return { version: 1, hash: record.fingerprint.hash };
});

test("H11", "确认失效：上游变化或 Prompt 前进后必须重新确认", async () => {
  const plan = planFixture();
  // 只测确认失效，不关心印字：前后编译都用不印新增文字显式决定。
  const noPrint = noPrintSpec(plan.shots[1]);
  const entries = [await compileEntry(plan.shots[0]), await compileEntry(plan.shots[1], { shotSpec: noPrint })];
  const sheet = sheetOf({ plan: plan, entries: entries });
  const hash = await promptHash(confirmationSnapshot(sheet), DIGEST);
  const record = buildConfirmationRecord({ sheet: sheet, hash: hash, confirmedAt: new Date().toISOString() });
  const same = confirmationStaleness(record, confirmationSnapshot(sheetOf({ plan: plan, entries: entries })));
  expect(same.stale === false, "同一清单必须判定为未失效。");
  const bumped = confirmationStaleness(record, confirmationSnapshot(sheetOf({ plan: plan, entries: entries, styleVersion: 2 })));
  expect(bumped.stale === true, "风格前进后确认必须失效。");
  const fields = bumped.reasons.map((reason) => reason.field);
  expect(fields.some((field) => field === "shots.shot_main_clean"), "失效原因必须指到具体图片，实际 " + JSON.stringify(fields));
  const recompiled = [await compileEntry(plan.shots[0], { styleVersion: 2, version: 2 }), await compileEntry(plan.shots[1], { styleVersion: 2, version: 2, shotSpec: noPrintSpec(plan.shots[1]) })];
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
  // 只测反向探针，不关心印字：信息图用不印新增文字显式决定。
  const entries = [await compileEntry(plan.shots[0]), await compileEntry(plan.shots[1], { shotSpec: noPrintSpec(plan.shots[1]) })];
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

async function runSuite() {
  const results = {
    suite: "v2.3.5-confirm",
    status: "running",
    cases: [],
    started_at: new Date().toISOString(),
  };
  window.__V2_CONFIRM_RESULTS__ = results;
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
    render(results);
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
    window.__V2_CONFIRM_RESULTS__ = {
      suite: "v2.3.5-confirm",
      status: "crashed",
      error: serializeError(error),
      cases: [],
    };
    render(window.__V2_CONFIRM_RESULTS__);
  });
} else {
  window.__V2_CONFIRM_RESULTS__ = { suite: "v2.3.5-confirm", status: "skipped", cases: [] };
}
