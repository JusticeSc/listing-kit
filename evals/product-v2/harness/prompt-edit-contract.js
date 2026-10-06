/**
 * V2.3.6 Prompt 人工编辑版本契约测试（真实 Chromium，非 Mock）。
 *
 * 正向：编辑记录形状、逐字一致、hash 与请求快照一致、版本链、降级提示、失效投影、过期与确认联动。
 * 反向（故意让守卫变红）：空/空白/超长/控制字符/无变化、未确认事实泄漏、篡改记录、编译器仍严格。
 *
 * 结果写到 window.__V2_PROMPT_EDIT_RESULTS__，由 tools/verify_v2_3_6_prompt_manual_edit.py 读取。
 */

import {
  DOMAIN_ERROR_CODES,
  MANUAL_EDIT_REASON_CODES,
  MANUAL_EDIT_REASON_MAX,
  MANUAL_EDIT_WARNING_CODES,
  MAX_PROMPT_CHARS,
  PLATFORM_PROFILES,
  buildConfirmationRecord,
  buildConfirmationSheet,
  buildEditedPromptRecord,
  buildPromptRecord,
  canonicalJson,
  checkCompiledPrompt,
  checkPromptRecord,
  compilePrompt,
  confirmationSnapshot,
  confirmationStaleness,
  discardManualEdit,
  emptyShotSpecFromShot,
  emptyStyleSpec,
  invalidationsFor,
  latestSystemPromptVersion,
  promptHash,
  promptStaleness,
  reconfirmEditedPrompt,
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
const DIGEST = { digest: sha256Hex };
const PLATFORM_ID = "amazon_us";
const PROVIDER_ID = "qwen-image-3.0";
const BASE_TIME = "2026-09-30T04:00:00+08:00";

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

function contextFixture(extraFacts = []) {
  return {
    facts: [
      { slot_id: "product_name", status: "confirmed", value: "便携保温杯" },
      { slot_id: "product_category", status: "confirmed", value: "保温杯" },
      { slot_id: "signature_features", status: "confirmed", value: ["304不锈钢内胆", "12小时保温"] },
      ...extraFacts,
    ],
    assets: [{ role: "primary", sha256: SHA_PRIMARY }],
    brief: briefFixture(),
  };
}

const UNCONFIRMED_FACT = { slot_id: "coating_claim", status: "proposed", value: "纳米自清洁涂层" };

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

function planFixture(shots) {
  return { schema_version: 1, shots: shots || [mainShot()] };
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
    provider: IMAGE_PROMPT_PROFILE,
  };
}

/** 编译 + 快照 + hash + 版本记录：与 workspace.js 的真实链路同一套调用。 */
async function compiledEntry(shot, options = {}) {
  const context = options.context || contextFixture();
  const compiled = compilePrompt({
    brief: briefFixture(),
    shot: shot,
    styleSpec: options.styleSpec || styleFixture(),
    shotSpec: emptyShotSpecFromShot(shot),
    context: context,
    providerProfile: IMAGE_PROMPT_PROFILE,
    versions: {
      suite_version: 1,
      style_version: options.styleVersion === undefined ? 1 : options.styleVersion,
      shot_spec_version: null,
    },
  });
  const references = selectReferences(shot, context.assets);
  const snapshot = requestSnapshotOf(compiled, { references: references });
  const hash = await promptHash(snapshot, DIGEST);
  return {
    shot_id: shot.shot_id,
    version: 1,
    record: buildPromptRecord({ compiled: compiled, snapshot: snapshot, hash: hash }),
  };
}

async function edited(entry, text, options = {}) {
  return buildEditedPromptRecord({
    base: entry.record,
    baseVersion: options.baseVersion === undefined ? entry.version : options.baseVersion,
    text: text,
    reason: options.reason === undefined ? "调整文案与约束" : options.reason,
    editedAt: options.editedAt || BASE_TIME,
    context: options.context || contextFixture(),
    digest: sha256Hex,
  });
}

function codesOf(record) {
  return (record.compiled.warnings || []).map((warning) => warning.code);
}

function sheetOf(record, shot, options = {}) {
  const basisByShot = {};
  basisByShot[shot.shot_id] = basisFixture({ styleVersion: options.styleVersion });
  return buildConfirmationSheet({
    suitePlan: planFixture([shot]),
    promptEntries: [{ shot_id: shot.shot_id, record: record, version: options.version || 1 }],
    context: options.context || contextFixture(),
    currentBasisByShot: basisByShot,
    providerProfile: IMAGE_PROMPT_PROFILE,
  });
}

/* ---------------------------------------------------------------- 正向 */

test("M01", "正常编辑：新记录逐字等于全文，hash 覆盖请求快照，旧版本不动", async () => {
  const entry = await compiledEntry(mainShot());
  const text = entry.record.compiled.text + "\n\n补充约束：商品标志必须位于正面中心，颜色与参考图保持逐字一致。";
  const record = await edited(entry, text, { reason: "补充标志位置约束" });
  const problems = checkPromptRecord(record);
  expect(problems.length === 0, "人工编辑记录必须自检通过：" + JSON.stringify(problems.slice(0, 2)));
  expect(record.origin === "manual_edit", "必须标记为人工编辑版本。");
  expect(record.compiled.text === text && record.request_snapshot.prompt === text, "界面文本、记录文本与快照必须逐字一致。");
  expect(record.compiled.sections.length === 1 && record.compiled.sections[0].kind === "manual_edit", "人工编辑版只有一个全文段落。");
  expect(record.hash === await promptHash(record.request_snapshot, DIGEST), "hash 必须由请求快照重算得到。");
  expect(record.hash !== entry.record.hash, "编辑后的 hash 必须变化。");
  expect(record.edited_from.version === 1 && record.edited_from.hash === entry.record.hash, "必须记录被编辑版本与 hash。");
  expect(record.edit_reason === "补充标志位置约束" && record.edited_at === BASE_TIME, "必须记录编辑原因与时间。");
  expect(canonicalJson(record.basis) === canonicalJson(entry.record.basis), "编辑不得改变编译依据。");
  expect(entry.record.compiled.text.indexOf("补充约束") < 0, "被编辑的旧版本必须原样保留。");
  return { hash: record.hash.slice(0, 12), reason: record.edit_reason };
});

test("M02", "链式编辑：再次编辑基于人工版本，版本链与来源引用可追溯", async () => {
  const entry = await compiledEntry(mainShot());
  const first = await edited(entry, entry.record.compiled.text + "\n\n补充：四角留白均匀。", { reason: "第一次：留白" });
  const second = await buildEditedPromptRecord({
    base: first,
    baseVersion: 2,
    text: first.compiled.text + "\n补充：背景不得出现投影。",
    reason: "第二次：投影",
    editedAt: BASE_TIME,
    context: contextFixture(),
    digest: sha256Hex,
  });
  expect(checkPromptRecord(second).length === 0, "链式编辑记录必须自检通过。");
  expect(second.edited_from.version === 2 && second.edited_from.hash === first.hash, "必须指向被编辑的人工版本。");
  expect(second.hash !== first.hash && first.hash !== entry.record.hash, "每次编辑都必须产生新 hash。");
  expect(second.compiled.source_refs.includes("prompt_edit:" + first.hash), "来源必须能追到上一次编辑。");
  expect(second.compiled.source_refs.includes("prompt_edit:" + entry.record.hash), "来源必须保留最初编译版本。");
  return { refs: second.compiled.source_refs.filter((ref) => ref.startsWith("prompt_edit:")) };
});

/* ---------------------------------------------------------------- 反向 */

test("M03", "硬阻断：空文本 / 纯空白 / 超长 / 控制字符都不产记录", async () => {
  const entry = await compiledEntry(mainShot());
  await expectCode(async () => { await edited(entry, ""); }, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "空文本必须被拒");
  await expectCode(async () => { await edited(entry, "   \n\t  "); }, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "纯空白必须被拒");
  await expectCode(async () => { await edited(entry, "描".repeat(MAX_PROMPT_CHARS + 1)); },
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "超长必须被拒");
  await expectCode(async () => { await edited(entry, entry.record.compiled.text + "\u0007"); },
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "控制字符必须被拒");
  await expectCode(async () => { await edited(entry, entry.record.compiled.text, { reason: "" }); },
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "缺编辑原因必须被拒");
  await expectCode(async () => { await edited(entry, entry.record.compiled.text, { reason: "原".repeat(MANUAL_EDIT_REASON_MAX + 1) }); },
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "编辑原因超长必须被拒");
  return { probes: 6 };
});

test("M04", "无变化编辑被拒：不产生无意义的新版本", async () => {
  const entry = await compiledEntry(mainShot());
  const error = await expectCode(async () => { await edited(entry, entry.record.compiled.text); },
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "逐字相同必须被拒");
  expect(error.message.includes("逐字相同"), "拒绝理由必须说明没有变化，实际：" + error.message);
  return { message: error.message };
});

test("M05", "未确认事实仍硬阻断：非引用与引用写法都不能保存", async () => {
  const entry = await compiledEntry(mainShot());
  const context = contextFixture([UNCONFIRMED_FACT]);
  await expectCode(async () => {
    await edited(entry, entry.record.compiled.text + "\n补充：具备纳米自清洁涂层。", { context: context });
  }, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "未确认事实的非引用写法必须阻断");
  await expectCode(async () => {
    await edited(entry, entry.record.compiled.text + "\n补充：文案写「纳米自清洁涂层」。", { context: context });
  }, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "未确认事实即使加引用也必须阻断");
  return { probes: 2 };
});

test("M06", "语言策略降级为提示：英文指令不再阻断保存，但必须可见", async () => {
  const entry = await compiledEntry(mainShot());
  const record = await edited(entry, "Keep the product logo centered and the background pure white.", { reason: "临时英文表述" });
  const warnings = codesOf(record);
  expect(checkPromptRecord(record).length === 0, "语言违规在人工编辑里不能阻断保存。");
  expect(warnings.includes(MANUAL_EDIT_WARNING_CODES.LANGUAGE_RULE), "必须给出语言策略提示，实际 " + JSON.stringify(warnings));
  const message = record.compiled.warnings.find((item) => item.code === MANUAL_EDIT_WARNING_CODES.LANGUAGE_RULE).message;
  expect(message.includes("指令段" ) || message.includes("非中文"), "提示必须说明问题：" + message);
  return { warnings: warnings };
});

test("M07", "新增引用必须来自已确认事实：未授权引用阻断，已确认引用在文字角色上允许", async () => {
  const main = await compiledEntry(mainShot());
  const context = contextFixture([UNCONFIRMED_FACT]);
  await expectCode(async () => {
    await edited(main, main.record.compiled.text + "\n补充：画面里写「限时特惠」。", { context: context });
  }, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "未授权新增引用必须阻断");
  const info = await compiledEntry(infographicShot(), { context: context });
  const allowed = await edited(info, info.record.compiled.text + "\n补充：图中文字加一条「304不锈钢内胆」，逐字不改。",
    { context: context, reason: "补一条已确认卖点" });
  expect(checkPromptRecord(allowed).length === 0, "文字角色的已确认引用必须允许。");
  expect(allowed.compiled.text.includes("「304不锈钢内胆」"), "已确认引用必须逐字进入文本。");
  return { quotes: (allowed.compiled.text.match(/「[^」]*」/g) || []) };
});

test("M08", "平台文字规则仍然阻断：主图不能新增文案，文字角色可以", async () => {
  const context = contextFixture();
  const main = await compiledEntry(mainShot());
  const mainError = await expectDomainError(async () => {
    await edited(main, main.record.compiled.text + "\n补充：图中文字写「12小时保温」。", { context: context });
  }, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "主图新增文案必须阻断");
  expect(mainError.details && mainError.details.reason_code === MANUAL_EDIT_REASON_CODES.PLATFORM_TEXT_RULE,
    "阻断原因码必须是平台文字规则，实际 " + JSON.stringify(mainError.details));
  const info = await compiledEntry(infographicShot(), { context: context });
  const infoRecord = await edited(info, info.record.compiled.text + "\n补充：图中文字写「12小时保温」。",
    { context: context, reason: "补文案" });
  expect(checkPromptRecord(infoRecord).length === 0, "文字角色的已确认文案必须允许。");
  return { reason_code: mainError.details.reason_code };
});

/** 带 details 的错误捕获：expectCode 只回 {code,message}，这里要读机读原因码。 */
async function expectDomainError(run, code, label) {
  try {
    await run();
  } catch (error) {
    const actual = error && error.code ? error.code : (error && error.name) || "unknown";
    if (actual !== code) {
      throw new Error(label + "：期望错误码 " + code + "，实际是 " + actual
        + "（" + (error && error.message) + "）");
    }
    return error;
  }
  throw new Error(label + "：期望抛出 " + code + "，但没有抛错。");
}

/* ------------------------------------------------- 记录机检、失效与确认 */

test("M09", "记录篡改必须变红：形状、来源、快照与失效投影都自检", async () => {
  const entry = await compiledEntry(mainShot());
  const record = await edited(entry, entry.record.compiled.text + "\n\n补充约束：商品标志位于正面中心。",
    { reason: "篡改基线" });
  expect(checkPromptRecord(record).length === 0, "前置条件：基线记录必须自检通过。");
  const probes = [];
  const mutate = (label, change) => {
    const copy = structuredClone(record);
    change(copy);
    const problems = checkPromptRecord(copy);
    expect(problems.length > 0, "篡改必须被发现：" + label);
    probes.push(label);
  };
  mutate("edited_from.hash", (item) => { item.edited_from.hash = "not-a-hash"; });
  mutate("edited_from.version", (item) => { item.edited_from.version = 0; });
  mutate("edit_reason", (item) => { item.edit_reason = "   "; });
  mutate("edited_at", (item) => { item.edited_at = "刚刚"; });
  mutate("compiled.origin", (item) => { delete item.compiled.origin; });
  mutate("invalidation.scope", (item) => { item.invalidation.scope = "project"; });
  mutate("invalidation.target_shot_id", (item) => { item.invalidation.target_shot_id = "shot_infographic_benefits"; });
  mutate("request_snapshot.prompt", (item) => { item.request_snapshot.prompt = item.request_snapshot.prompt + " "; });
  mutate("hash", (item) => { item.hash = ""; });
  mutate("basis", (item) => { delete item.basis; });
  expect(probes.length === 10, "探针数量必须与清单一致。");
  return { probes: probes };
});

test("M10", "失效投影精确：只失效目标图的提示词、审核与选择，不动上游与其他图", async () => {
  const target = "shot_main_clean";
  const projection = invalidationsFor("prompt_edited", { shotId: target });
  expect(projection.scope === "shot" && projection.target_shot_id === target, "必须是单图范围并记录目标图。");
  expect(projection.invalidates.length === 3, "影响面不得扩大，实际 " + JSON.stringify(projection.invalidates));
  for (const key of ["prompt_versions", "review_reports", "selection"]) {
    expect(projection.invalidates.includes(key), "必须失效 " + key + "，实际 " + JSON.stringify(projection.invalidates));
  }
  for (const key of ["product_brief", "suite_plan", "shot_spec", "other_shots", "project_history", "candidate_blobs"]) {
    expect(projection.preserves.includes(key), "必须保留 " + key + "，实际 " + JSON.stringify(projection.preserves));
  }
  const other = invalidationsFor("prompt_edited", { shotId: "shot_infographic_benefits" });
  expect(other.target_shot_id === "shot_infographic_benefits" && other.scope === "shot", "失效必须跟着目标图走。");
  await expectDomainError(async () => { invalidationsFor("prompt_edited", {}); },
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "缺 shotId 必须抛错");
  const base = await compiledEntry(mainShot());
  const record = await edited(base, base.record.compiled.text + "\n\n补充约束：四角留白均匀。", { reason: "留白" });
  expect(canonicalJson(record.invalidation) === canonicalJson(projection),
    "人工编辑记录的失效投影必须与失效图逐字一致。");
  return { invalidates: projection.invalidates, preserves: projection.preserves };
});

test("M11", "过期与确认联动：编辑不改依据，但改变确认指纹并让旧确认失效", async () => {
  const shot = mainShot();
  const entry = await compiledEntry(shot);
  const fresh = promptStaleness(entry.record, basisFixture());
  expect(fresh.stale === false, "刚编译的记录不得过期：" + JSON.stringify(fresh.reasons));
  const record = await edited(entry, entry.record.compiled.text + "\n\n补充约束：四角留白均匀。", { reason: "留白" });
  const afterEdit = promptStaleness(record, basisFixture());
  expect(afterEdit.stale === false, "编辑继承依据，不得因编辑本身过期：" + JSON.stringify(afterEdit.reasons));
  const afterStyle = promptStaleness(record, basisFixture({ styleVersion: 2 }));
  expect(afterStyle.stale === true, "风格前进后人工版本必须过期。");
  expect(afterStyle.reasons.some((reason) => reason.field === "style_version"), "过期原因必须点名风格版本。");
  const before = sheetOf(entry.record, shot);
  expect(before.can_submit === true, "前置条件：未编辑版本可提交。");
  const confirmation = buildConfirmationRecord({
    sheet: before,
    hash: await promptHash(confirmationSnapshot(before), DIGEST),
    confirmedAt: BASE_TIME,
  });
  const same = confirmationStaleness(confirmation, confirmationSnapshot(sheetOf(entry.record, shot)));
  expect(same.stale === false, "同一清单必须判定为未失效。");
  const afterSheet = sheetOf(record, shot, { version: 2 });
  const diff = confirmationStaleness(confirmation, confirmationSnapshot(afterSheet));
  expect(diff.stale === true, "编辑后旧确认必须失效。");
  const fields = diff.reasons.map((reason) => reason.field);
  expect(fields.some((field) => field.indexOf("shots." + shot.shot_id) === 0),
    "失效原因必须指到目标图，实际 " + JSON.stringify(fields));
  const reConfirmed = buildConfirmationRecord({
    sheet: afterSheet,
    hash: await promptHash(confirmationSnapshot(afterSheet), DIGEST),
    confirmedAt: BASE_TIME,
  });
  expect(reConfirmed.fingerprint.hash !== confirmation.fingerprint.hash, "指纹必须变化。");
  expect(reConfirmed.shots[0].prompt_version === 2, "重新确认必须记录新版本号。");
  const stable = confirmationStaleness(reConfirmed, confirmationSnapshot(sheetOf(record, shot, { version: 2 })));
  expect(stable.stale === false, "重新确认后必须回到有效。");
  // V2.R6.2：人工文本重新确认（逐字保留原文本、依据更新到当前）与丢弃覆盖。
  const basisNow = {
    briefBasis: record.basis.brief,
    shot_signature: record.basis.shot_signature,
    suite_version: 1, style_version: 1, shot_spec_version: null,
    platform: { version: PLATFORM_PROFILES[PLATFORM_ID].version },
    provider: IMAGE_PROMPT_PROFILE,
  };
  const reconfirmed = await reconfirmEditedPrompt({
    base: record, baseVersion: 2, reason: "文本仍适用，依据已更新",
    at: BASE_TIME, basis: basisNow, context: contextFixture(), digest: sha256Hex,
  });
  expect(reconfirmed.compiled.text === record.compiled.text, "重新确认必须逐字保留人工文本。");
  expect(reconfirmed.reconfirmed === true && reconfirmed.edited_from.version === 2,
    "重新确认必须指向被确认版本并留痕：" + JSON.stringify(reconfirmed.edited_from));
  expect(checkPromptRecord(reconfirmed).length === 0, "重新确认记录必须自检通过。");
  expect(promptStaleness(reconfirmed, basisNow).stale === false, "重新确认后不得过期。");
  await expectCode(async () => { await reconfirmEditedPrompt({
    base: record, baseVersion: 2, reason: "缺依据", at: BASE_TIME, context: contextFixture(),
    digest: sha256Hex }); },
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "当前编译依据");
  const history = [{ version: 1, record: entry.record }, { version: 2, record: record }];
  const discarded = discardManualEdit(record, history);
  expect(discarded.target && discarded.target.version === 1 && discarded.requires_recompile === false,
    "丢弃人工覆盖应回到最新系统版本：" + JSON.stringify(discarded.target));
  expect(latestSystemPromptVersion(history).record.origin !== "manual_edit",
    "最新系统版本必须不是人工编辑。");
  await expectCode(() => { discardManualEdit(entry.record, history); },
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "系统编译版本");
  return { fields: fields };
});

/* ---------------------------------------------------------------- 反向探针 */

test("M12", "反向探针：编译器仍严格，编辑入口的非法输入全部保留原因码", async () => {
  const entry = await compiledEntry(mainShot());
  const compilerOutput = {
    sections: [{
      key: "product_fidelity", label: "商品一致性", kind: "instruction",
      text: "Keep the product logo centered.", source_refs: ["intake.references"],
    }],
  };
  compilerOutput.text = compilerOutput.sections[0].text;
  compilerOutput.source_refs = ["intake.references"];
  expect(checkCompiledPrompt(compilerOutput).length > 0,
    "没有 origin 的编译器产物必须继续被语言策略阻断。");
  const englishRecord = await edited(entry, "Keep the product logo centered and the background pure white.",
    { reason: "英文草稿" });
  expect(checkPromptRecord(englishRecord).length === 0, "前置条件：英文人工编辑版本本身可保存（只给提示）。");
  const asCompiler = structuredClone(englishRecord);
  delete asCompiler.origin;
  delete asCompiler.compiled.origin;
  expect(checkPromptRecord(asCompiler).length > 0, "去掉 origin 后必须回到编译器的严格语言策略。");
  const probes = [];
  const probe = async (label, run) => {
    const error = await expectDomainError(run, DOMAIN_ERROR_CODES.CONTRACT_INVALID, label);
    const reason = (error.details && error.details.reason_code) || "TEXT";
    probes.push(label + ":" + reason);
    return error;
  };
  await probe("空文本", () => edited(entry, ""));
  await probe("无原因", () => edited(entry, entry.record.compiled.text + "\n补充：四角留白均匀。", { reason: "" }));
  await probe("无变化", () => edited(entry, entry.record.compiled.text));
  const unknown = await probe("未授权引用", () => edited(entry, entry.record.compiled.text + "\n补充：画面里写「限时特惠」。"));
  expect(unknown.details && unknown.details.reason_code === MANUAL_EDIT_REASON_CODES.UNKNOWN_QUOTE,
    "未授权引用必须是引用原因码，实际 " + JSON.stringify(unknown.details));
  const platform = await probe("主图新增文案", () => edited(entry, entry.record.compiled.text + "\n补充：画面里写「12小时保温」。"));
  expect(platform.details && platform.details.reason_code === MANUAL_EDIT_REASON_CODES.PLATFORM_TEXT_RULE,
    "主图新增文案必须是平台文字原因码，实际 " + JSON.stringify(platform.details));
  return { probes: probes };
});

/* ---------------------------------------------------------------- 运行器 */

function render(results) {
  const node = document.getElementById("results");
  if (node) node.textContent = JSON.stringify(results, null, 2);
}

async function runSuite() {
  const results = {
    suite: "v2.3.6-prompt-edit",
    status: "running",
    cases: [],
    started_at: new Date().toISOString(),
  };
  window.__V2_PROMPT_EDIT_RESULTS__ = results;
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
    window.__V2_PROMPT_EDIT_RESULTS__ = {
      suite: "v2.3.6-prompt-edit",
      status: "crashed",
      error: serializeError(error),
      cases: [],
    };
    render(window.__V2_PROMPT_EDIT_RESULTS__);
  });
} else {
  window.__V2_PROMPT_EDIT_RESULTS__ = { suite: "v2.3.6-prompt-edit", status: "skipped", cases: [] };
}
