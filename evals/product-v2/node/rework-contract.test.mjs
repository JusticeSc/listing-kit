/**
 * V2.5.4 单图返工契约测试（Node 原生进程，非 Mock，纯领域函数）。
 *
 * 正向：指令绑定候选身份与来源、建议映射、方向归一、编译段落与来源引用、
 *       记录保留返工块、scope=[目标图] 的单图确认与整体快照比较。
 * 反向：空理由、未知分类、跨图候选、非法 sha、失效指令、篡改编译结果都必须被抓住。
 *
 * 直接运行：node --test evals/product-v2/node/
 */

import {
  DOMAIN_ERROR_CODES,
  PLATFORM_PROFILES,
  REWORK_CONTRACT_VERSION,
  REWORK_DIRECTION_MAX,
  REWORK_PROBLEM_IDS,
  REWORK_PROBLEMS,
  buildConfirmationRecord,
  buildConfirmationSheet,
  buildPromptRecord,
  buildReviewReport,
  buildReworkDirective,
  canonicalJson,
  checkCompiledPrompt,
  checkPromptRecord,
  checkReworkDirective,
  compilePrompt,
  confirmationSnapshot,
  confirmationStaleness,
  emptyShotSpecFromShot,
  emptyStyleSpec,
  normalizeReworkDirection,
  promptHash,
  requestSnapshotOf,
  reworkIsCurrent,
  reworkProblemLabel,
  reworkSummaryText,
  selectReferences,
  suggestReworkProblems,
  suggestedReworkDirection,
} from "../../../build/frontend-node/app/product_v2/domain/index.js";

import { sha256Hex } from "../../../build/frontend-node/app/product_v2/storage/db.js";
import { IMAGE_PRICING, IMAGE_PROMPT_PROFILE, expect, expectCode, serializeError } from "./harness-core.mjs";
const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

function json(value) {
  return JSON.stringify(value);
}
const DIGEST = { digest: sha256Hex };
const PLATFORM_ID = "amazon_us";
const PROVIDER_ID = "qwen-image-3.0";
const BASE_TIME = "2026-09-30T04:00:00+08:00";
const SHA_A = "a".repeat(64);
const SHA_B = "b".repeat(64);

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
      { slot_id: "signature_features", status: "confirmed",
        value: ["304不锈钢内胆", "12小时保温"] },
    ],
    assets: [{ role: "primary", sha256: SHA_A }],
    brief: briefFixture(),
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

function planFixture(shots) {
  return { schema_version: 1, shots: shots || [mainShot()] };
}

// 夹具的显式展示决定：外观按原样、内容不适用（主图/信息图不消费 contents_state），
// 让基座先过新的展示决定门，断言只测返工与确认隔离规则。
function styleFixture(overrides = {}) {
  return {
    ...emptyStyleSpec(),
    background: "浅灰无缝背景",
    lighting: "柔和顶光",
    color_tone: "自然",
    composition: "商品居中，留白充足",
    avoid: ["文字水印"],
    presentation: { appearance_state: "as_shown", contents_state: "not_applicable" },
    ...overrides,
  };
}

function basisFixture() {
  return {
    briefBasis: briefFixture().basis,
    suite_version: 1,
    style_version: 1,
    shot_spec_version: null,
    platform: { version: PLATFORM_PROFILES[PLATFORM_ID].version },
    provider: IMAGE_PROMPT_PROFILE,
  };
}
// 基座编译默认不替用户做印字决定：信息图用 none 显式关闭程序自动印字，
// 把基座固定下来，确认隔离的断言才只测 scope 投影，不被编译门干扰。
function noPrintSpec(shot, overrides = {}) {
  return { ...emptyShotSpecFromShot(shot), print_intent: "none", ...overrides };
}
// 需要 selected 基座时用：选一条已确认事实文案，来源版本与该套件 basis 一致，
// 只证明基座能显式带文案；本套件 RW-14/RW-15 不需要，走 noPrint。
function chosenPrintSpec(shot, overrides = {}) {
  return {
    ...emptyShotSpecFromShot(shot),
    print_intent: "selected",
    layout: "product_left_text_right",
    on_image_texts: [{
      text_id: "t1",
      text: "12小时保温",
      source: { kind: "fact_slot", document_id: "signature_features", version: 1 },
      status: "confirmed",
      origin: "user",
    }],
    ...overrides,
  };
}
// 已保存的商品资料版本（冻结参考图来源的精确版本；与产品调用方同一快照概念）。
const INTAKE_VERSION = 1;
// 问题候选的确切文档版本（夹具候选都已保存为该版本；返工指令绑定它）。
const CANDIDATE_VERSION = 1;

function candidateFixture(shot, overrides = {}) {
  return {
    candidate_id: "cand-" + shot.shot_id,
    shot_id: shot.shot_id,
    asset_sha256: SHA_A,
    media_type: "image/png",
    width: 1600,
    height: 1600,
    attempt_action_id: "act-fixture",
    created_at: BASE_TIME,
    ...overrides,
  };
}

function reportFixture(shot, overrides = {}) {
  return buildReviewReport({
    candidate: overrides.candidate || candidateFixture(shot),
    findings: overrides.findings || [{
      rule_id: "platform.min_long_side", severity: "BLOCK",
      detail: "长边 64px 低于平台缩放下限 1000px。", measured: { long_side: 64 },
    }],
    at: BASE_TIME,
  });
}

function directiveFixture(shot, options = {}) {
  return buildReworkDirective({
    directiveId: options.directiveId || "rw-fixture-01",
    shotId: shot.shot_id,
    mode: options.mode || "edit_candidate",
    candidate: options.candidate || candidateFixture(shot),
    candidateDocument: options.candidateDocument || { document_id: shot.shot_id, version: CANDIDATE_VERSION },
    report: options.report === undefined ? reportFixture(shot) : options.report,
    problems: options.problems === undefined ? ["product_fidelity"] : options.problems,
    direction: options.direction === undefined ? "只把背景换成纯白，商品保持不变。" : options.direction,
    at: options.at || BASE_TIME,
  });
}

async function compiledEntry(shot, options = {}) {
  const context = contextFixture();
  const shotSpec = options.shotSpec || emptyShotSpecFromShot(shot);
  const compiled = compilePrompt({
    brief: briefFixture(),
    shot: shot,
    styleSpec: options.styleSpec || styleFixture(),
    shotSpec: shotSpec,
    context: context,
    providerProfile: IMAGE_PROMPT_PROFILE,
    versions: {
      suite_version: 1,
      style_version: options.styleVersion === undefined ? 1 : options.styleVersion,
      shot_spec_version: null,
    },
    ...(options.rework ? { rework: options.rework } : {}),
  });
  // 返工走产品同一选择器与同一选项：edit 模式候选首位，regenerate 只发原照。
  const references = selectReferences(shot, context.assets,
    { intakeVersion: INTAKE_VERSION, shotSpec: shotSpec,
      ...(options.rework ? { rework: options.rework } : {}) });
  const snapshot = requestSnapshotOf(compiled, { references: references });
  const hash = await promptHash(snapshot, DIGEST);
  return {
    shot_id: shot.shot_id,
    version: 1,
    compiled: compiled,
    record: buildPromptRecord({ compiled: compiled, snapshot: snapshot, hash: hash }),
  };
}

function sheetFixture(shot, record, options = {}) {
  const second = options.secondShot || infographicShot();
  const plan = planFixture([shot, second]);
  const entries = [{ shot_id: shot.shot_id, record: record, version: options.version || 1 }];
  if (options.secondRecord) {
    entries.push({ shot_id: second.shot_id, record: options.secondRecord, version: 1 });
  }
  const basisByShot = {};
  for (const item of plan.shots) basisByShot[item.shot_id] = basisFixture();
  return buildConfirmationSheet({
    suitePlan: plan,
    promptEntries: entries,
    context: contextFixture(),
    currentBasisByShot: basisByShot,
    providerProfile: IMAGE_PROMPT_PROFILE,
    pricing: options.pricing === undefined ? IMAGE_PRICING : options.pricing,
    ...(options.shotIds ? { shotIds: options.shotIds } : {}),
  });
}

async function confirmationFixture(sheet) {
  const snapshot = confirmationSnapshot(sheet);
  return buildConfirmationRecord({
    sheet: sheet,
    hash: await promptHash(snapshot, DIGEST),
    confirmedAt: BASE_TIME,
  });
}

/* ---------------------------------------------------------------- 指令合同 */

test("RW-01", "空理由被拒：没有分类且方向为空或过短时，产出与自检都不放行", async () => {
  const shot = mainShot();
  const base = {
    directiveId: "rw-01", shotId: shot.shot_id, mode: "edit_candidate",
    candidate: candidateFixture(shot),
    candidateDocument: { document_id: shot.shot_id, version: CANDIDATE_VERSION },
    report: null, at: BASE_TIME,
  };
  await expectCode(() => buildReworkDirective({ ...base, problems: [], direction: "" }),
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "空分类 + 空方向");
  await expectCode(() => buildReworkDirective({ ...base, problems: [], direction: "改" }),
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "空分类 + 过短方向");
  // 缺模式的新指令同样不能放行：必须明确改这条候选或按原资料重画。
  await expectCode(() => buildReworkDirective({ ...base, mode: undefined, problems: ["scene"], direction: "" }),
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "缺返工模式");
  const problems = checkReworkDirective({
    schema_version: 1, contract_version: REWORK_CONTRACT_VERSION, directive_id: "rw-01",
    shot_id: shot.shot_id, candidate_id: "cand-1", candidate_sha256: SHA_A,
    problems: [], direction: "", created_at: BASE_TIME, source: {},
  });
  expect(problems.some((item) => item.message.indexOf("至少要有一个问题分类") >= 0),
    "空理由必须被 checkReworkDirective 明确拒绝。");
  return { problems: problems.length };
});

test("RW-02", "未知分类被拒：词表外的 id 在构建与自检两处都不能通过", async () => {
  const shot = mainShot();
  await expectCode(() => buildReworkDirective({
    directiveId: "rw-02", shotId: shot.shot_id, mode: "edit_candidate",
    candidate: candidateFixture(shot),
    candidateDocument: { document_id: shot.shot_id, version: CANDIDATE_VERSION },
    report: null, problems: ["product_fidelity", "mystery"], direction: "", at: BASE_TIME,
  }), DOMAIN_ERROR_CODES.CONTRACT_INVALID, "未知分类");
  const problems = checkReworkDirective({
    schema_version: 1, contract_version: REWORK_CONTRACT_VERSION, directive_id: "rw-02",
    shot_id: shot.shot_id, candidate_id: "cand-1", candidate_sha256: SHA_A,
    problems: ["mystery"], direction: "", created_at: BASE_TIME, source: {},
  });
  expect(problems.some((item) => item.path === "$.problems[0]"),
    "未知分类必须落在 $.problems[i] 路径上。");
  expect(REWORK_PROBLEM_IDS.length === REWORK_PROBLEMS.length && REWORK_PROBLEMS.every(
    (item) => item.id && item.label && item.hint), "九类问题的 id/label/hint 必须齐全。");
  return { problems: problems.map((item) => item.path) };
});

test("RW-03", "跨图候选被拒：候选的 shot_id 与目标图不一致时不能当作返工依据", async () => {
  const shot = mainShot();
  const other = infographicShot();
  await expectCode(() => buildReworkDirective({
    directiveId: "rw-03", shotId: shot.shot_id, mode: "edit_candidate",
    candidate: candidateFixture(other),
    candidateDocument: { document_id: shot.shot_id, version: CANDIDATE_VERSION },
    report: null, problems: ["scene"], direction: "", at: BASE_TIME,
  }), DOMAIN_ERROR_CODES.CONTRACT_INVALID, "跨图候选");
  const directive = directiveFixture(other);
  await expectCode(() => compilePrompt({
    brief: briefFixture(), shot: shot, styleSpec: styleFixture(),
    shotSpec: emptyShotSpecFromShot(shot), context: contextFixture(),
    versions: { suite_version: 1, style_version: 1, shot_spec_version: null },
    providerProfile: IMAGE_PROMPT_PROFILE,
    rework: directive,
  }), DOMAIN_ERROR_CODES.CONTRACT_INVALID, "把别张图的返工指令塞进本图 Prompt");
  return { directive_shot: directive.shot_id, compiled_shot: shot.shot_id };
});

test("RW-04", "候选 sha256 非法被拒：构建与自检都要求 64 位 hex 身份", async () => {
  const shot = mainShot();
  await expectCode(() => buildReworkDirective({
    directiveId: "rw-04", shotId: shot.shot_id, mode: "edit_candidate",
    candidate: candidateFixture(shot, { asset_sha256: "abc123" }),
    candidateDocument: { document_id: shot.shot_id, version: CANDIDATE_VERSION },
    report: null, problems: ["scene"], direction: "", at: BASE_TIME,
  }), DOMAIN_ERROR_CODES.CONTRACT_INVALID, "非法 sha");
  const problems = checkReworkDirective({
    schema_version: 1, contract_version: REWORK_CONTRACT_VERSION, directive_id: "rw-04",
    shot_id: shot.shot_id, candidate_id: "cand-1", candidate_sha256: "abc123",
    problems: ["scene"], direction: "", created_at: BASE_TIME, source: {},
  });
  expect(problems.some((item) => item.path === "$.candidate_id"), "非法 sha 必须落在 $.candidate_id。");
  return { problems: problems.length };
});

test("RW-05", "指令失效：候选字节、候选 id 或合同版本变化后 reworkIsCurrent 为 false", async () => {
  const shot = mainShot();
  const directive = directiveFixture(shot);
  const document = { document_id: shot.shot_id, version: CANDIDATE_VERSION };
  const same = candidateFixture(shot);
  expect(reworkIsCurrent(directive, same, document) === true, "同一候选必须仍然有效。");
  expect(reworkIsCurrent(directive, candidateFixture(shot, { asset_sha256: SHA_B }), document) === false,
    "候选字节变化后指令必须失效。");
  expect(reworkIsCurrent(directive, candidateFixture(shot, { candidate_id: "cand-2" }), document) === false,
    "候选身份变化后指令必须失效。");
  expect(reworkIsCurrent({ ...directive, contract_version: "v0" }, same, document) === false,
    "合同版本变化后指令必须失效。");
  expect(reworkIsCurrent(directive, candidateFixture(infographicShot()), document) === false,
    "跨图候选必须失效。");
  // 问题候选的新版本不改变固定的旧依据：指令按固定的确切版本判过期。
  expect(reworkIsCurrent(directive, same, { document_id: shot.shot_id, version: CANDIDATE_VERSION + 1 }) === false,
    "候选文档版本前进后指令必须失效。");
  return { directive: directive.directive_id };
});

test("RW-06", "来源缺失也可追溯：没有报告时 source 记录为 null，而不是伪造结论", () => {
  const shot = mainShot();
  const directive = directiveFixture(shot, { report: null, problems: ["text"],
    direction: "把图里的中文改成英文卖点。" });
  expect(directive.source.review_contract_version === null, "没有报告就不能写报告版本。");
  expect(directive.source.top_rule_id === null && directive.source.top_severity === null,
    "没有报告就不能编造先看项。");
  expect(directive.source.candidate_id === directive.candidate_id
    && directive.source.asset_sha256 === directive.candidate_sha256,
    "来源必须绑定候选身份与字节。");
  return { source: directive.source };
});

test("RW-07", "建议来自报告：平台规则映射到平台风险，没有报告时不给任何默认分类", () => {
  const shot = mainShot();
  const report = reportFixture(shot);
  expect(canonicalJson(suggestReworkProblems(report)) === canonicalJson(["platform_risk"]),
    "平台规则应先建议「平台风险」。");
  const direction = suggestedReworkDirection(report);
  expect(direction.indexOf("最小长边") >= 0, "建议方向必须引用报告先看项标题：" + direction);
  expect(direction.indexOf("只修改这一点") >= 0, "建议方向必须明确只改这一处。");
  expect(suggestReworkProblems(null).length === 0 && suggestedReworkDirection(null) === "",
    "没有报告就返回空建议，由用户自己写。");
  const vlmReport = reportFixture(shot, {
    findings: [{ rule_id: "vlm.part_anomaly", severity: "HIGH_RISK",
                 detail: "把手处出现不存在的部件。", measured: { anomaly: "handle" } }],
  });
  expect(canonicalJson(suggestReworkProblems(vlmReport)) === canonicalJson(["part_error"]),
    "VLM 部件异常应建议「部件错误」。");
  return { suggested: suggestReworkProblems(report), direction_len: direction.length };
});

test("RW-08", "方向归一：引号换成括号、换行压平、首尾去空白后才进入指令", () => {
  expect(normalizeReworkDirection("「背景」换成纯白\n『风格』不动 ") === "（背景）换成纯白 （风格）不动",
    "归一化结果不符合约定。");
  const shot = mainShot();
  const directive = directiveFixture(shot, { problems: [], direction: "「背景」换成纯白\n不要动商品" });
  expect(directive.direction === "（背景）换成纯白 不要动商品", "指令里的方向必须已归一。");
  expect(directive.direction.length >= 4 && directive.direction.length <= REWORK_DIRECTION_MAX,
    "归一后的方向必须在长度范围内。");
  expect(normalizeReworkDirection(null) === "", "空值归一化为空串。");
  return { direction: directive.direction };
});

/* ---------------------------------------------------------------- 摘要与编译 */

test("RW-09", "一行摘要：方向在、不暗示采纳；未知问题 id 原样返回不发明标签", () => {
  const shot = mainShot();
  const directive = directiveFixture(shot, {
    problems: ["product_fidelity", "text"], direction: "把标识改回参考图的样子。",
  });
  const summary = reworkSummaryText(directive);
  expect(summary.indexOf("改这条候选") >= 0, "摘要必须写明改法（edit 模式）：" + summary);
  expect(summary.indexOf("方向：") >= 0 && summary.indexOf("改回参考图") >= 0, "必须含方向。");
  expect(summary.indexOf("采纳") < 0 && summary.indexOf("已选择") < 0, "摘要不得暗示采纳。");
  expect(reworkProblemLabel("mystery") === "mystery", "未知 id 原样返回，不发明标签。");
  return { summary: summary };
});

test("RW-10", "编译带返工段：段落、来源引用、compiled.rework 与 basis 绑定同一条指令", async () => {
  const shot = mainShot();
  const editCandidate = candidateFixture(shot, { asset_sha256: SHA_B });
  const directive = directiveFixture(shot, {
    candidate: editCandidate, problems: ["product_fidelity"], direction: "只把背景换成纯白。",
  });
  const entry = await compiledEntry(shot, { rework: directive });
  const compiled = entry.record.compiled;
  const section = compiled.sections.filter((item) => item.key === "rework_directive")[0] || null;
  expect(Boolean(section), "必须新增 rework_directive 段。");
  expect(section.text.indexOf("本次返工要求") >= 0
    && section.text.indexOf("只把背景换成纯白") >= 0, "段落必须逐字含方向与标题。");
  expect(compiled.source_refs.indexOf("rework:" + directive.directive_id) >= 0, "来源必须含指令 id。");
  expect(compiled.source_refs.indexOf("candidate:" + directive.candidate_id) >= 0, "来源必须含候选 id。");
  expect(compiled.source_refs.indexOf("suite_plan.shot:" + shot.shot_id) >= 0, "来源必须含套图计划图。");
  expect(compiled.rework && compiled.rework.directive_id === directive.directive_id
    && compiled.rework.candidate_sha256 === directive.candidate_sha256, "编译结果必须绑定同一条指令。");
  expect(canonicalJson(entry.record.basis.rework.problems) === canonicalJson(["product_fidelity"]),
    "basis 必须记录本次返工问题分类。");
  expect(entry.record.basis.rework.mode === "edit_candidate",
    "basis 必须冻结本次返工模式：" + json(entry.record.basis.rework));
  const refs = entry.record.request_snapshot.references;
  expect(refs[0].sha256 === SHA_B && refs[0].uses.indexOf("edit_source") >= 0,
    "edit 模式第一张图必须是问题候选：" + json(refs));
  expect(refs.some((item) => item.uses.indexOf("product_truth") >= 0 && item.sha256 === SHA_A),
    "商品原照依据必须跟在候选之后：" + json(refs));
  const redo = directiveFixture(shot, { mode: "regenerate_original", candidate: editCandidate,
    directiveId: "rw-fixture-regen" });
  const redoEntry = await compiledEntry(shot, { rework: redo });
  const redoRefs = redoEntry.record.request_snapshot.references;
  expect(redoRefs.every((item) => item.uses.indexOf("edit_source") < 0),
    "原照重画不能发送历史候选图：" + json(redoRefs));
  expect(redoEntry.record.basis.rework.mode === "regenerate_original",
    "basis 必须冻结重画模式：" + json(redoEntry.record.basis.rework));
  expect(compiled.provider.model_id === PROVIDER_ID, "Provider 档沿用现有权威。");
  expect(checkCompiledPrompt(compiled).length === 0, "带返工的编译必须自检通过。");
  return { chars: compiled.text.length, sections: compiled.sections.length };
});

test("RW-11", "反向探针：篡改返工块或删掉返工段都会被编译自检抓住", async () => {
  const shot = mainShot();
  const entry = await compiledEntry(shot, { rework: directiveFixture(shot) });
  const compiled = entry.record.compiled;
  expect(checkCompiledPrompt(compiled).length === 0, "基准编译必须先通过自检。");
  const hijacked = { ...compiled, rework: { ...compiled.rework, candidate_id: "cand-hijack" } };
  expect(checkCompiledPrompt(hijacked).length > 0, "改绑候选必须报错。");
  const badSha = { ...compiled, rework: { ...compiled.rework, candidate_sha256: "not-a-hash" } };
  expect(checkCompiledPrompt(badSha).length > 0, "篡改 sha 必须报错。");
  const withoutSection = {
    ...compiled, sections: compiled.sections.filter((item) => item.key !== "rework_directive"),
  };
  expect(checkCompiledPrompt(withoutSection).length > 0, "删掉返工段必须报错。");
  return { probes: 3 };
});

test("RW-12", "版本记录保留返工块：记录自检通过，hash 覆盖含返工要求的请求快照", async () => {
  const shot = mainShot();
  const directive = directiveFixture(shot, { problems: ["scene"], direction: "背景换成纯白。" });
  const entry = await compiledEntry(shot, { rework: directive });
  const record = entry.record;
  expect(checkPromptRecord(record).length === 0, "记录必须自检通过。");
  expect(record.compiled.rework && record.compiled.rework.directive_id === directive.directive_id,
    "记录必须保留返工块。");
  expect(record.request_snapshot.prompt === record.compiled.text, "快照与全文必须逐字一致。");
  expect(record.request_snapshot.prompt.indexOf("本次返工要求") >= 0, "快照必须包含返工要求。");
  expect(record.hash === await promptHash(record.request_snapshot, DIGEST), "hash 必须覆盖请求快照。");
  return { hash: record.hash.slice(0, 12) };
});

test("RW-13", "对照与拦截：无返工的编译没有返工段；非法指令在编译前被拒绝", async () => {
  const shot = mainShot();
  const plain = await compiledEntry(shot);
  expect(!plain.compiled.sections.some((item) => item.key === "rework_directive"),
    "无返工不能凭空出现返工段。");
  expect(plain.compiled.rework === null, "无返工时 compiled.rework 必须是 null。");
  expect(!("rework" in plain.record.compiled), "记录里不能凭空写入返工块。");
  await expectCode(() => compilePrompt({
    brief: briefFixture(), shot: shot, styleSpec: styleFixture(),
    shotSpec: emptyShotSpecFromShot(shot), context: contextFixture(),
    versions: { suite_version: 1, style_version: 1, shot_spec_version: null },
    providerProfile: IMAGE_PROMPT_PROFILE,
    rework: {
      schema_version: 1, contract_version: REWORK_CONTRACT_VERSION, directive_id: "rw-bad",
      shot_id: shot.shot_id, candidate_id: "cand-1", candidate_sha256: SHA_A,
      problems: [], direction: "", created_at: BASE_TIME, source: {},
    },
  }), DOMAIN_ERROR_CODES.CONTRACT_INVALID, "空理由指令进编译");
  return { plain_sections: plain.record.compiled.sections.length };
});

/* ---------------------------------------------------------------- 确认隔离 */

// RW-14 用 noPrint 基座：确认隔离只测 scope 投影，不测印字选择。
test("RW-14", "单图确认隔离：scope=[X] 只投影 X；X 变让确认过期，Y 变不影响", async () => {
  const x = mainShot();
  const y = infographicShot();
  const xEntry = await compiledEntry(x);
  const yEntry = await compiledEntry(y, { shotSpec: noPrintSpec(y) });
  const sheetX = sheetFixture(x, xEntry.record, {
    secondShot: y, secondRecord: yEntry.record, shotIds: [x.shot_id],
  });
  expect(canonicalJson(sheetX.scope_shot_ids) === canonicalJson([x.shot_id]),
    "scope 必须只有目标图。");
  expect(sheetX.shots.length === 1 && sheetX.shots[0].shot_id === x.shot_id,
    "确认单只投影目标图。");
  const recordX = await confirmationFixture(sheetX);
  expect(canonicalJson(recordX.fingerprint.snapshot.scope_shot_ids) === canonicalJson([x.shot_id]),
    "快照必须带 scope，重开项目后还能判断作用域。");
  const changedX = await compiledEntry(x, { styleSpec: styleFixture({ lighting: "硬顶光，明显投影" }) });
  const sheetXChanged = sheetFixture(x, changedX.record, {
    secondShot: y, secondRecord: yEntry.record, shotIds: [x.shot_id],
  });
  const staleX = confirmationStaleness(recordX, confirmationSnapshot(sheetXChanged));
  expect(staleX.stale === true, "目标图 Prompt 变化必须让单图确认过期。");
  const changedY = await compiledEntry(y, { styleSpec: styleFixture({ lighting: "硬顶光，明显投影" }), shotSpec: noPrintSpec(y) });
  const sheetXWithChangedY = sheetFixture(x, xEntry.record, {
    secondShot: y, secondRecord: changedY.record, shotIds: [x.shot_id],
  });
  const staleY = confirmationStaleness(recordX, confirmationSnapshot(sheetXWithChangedY));
  expect(staleY.stale === false, "无关图变化不能影响目标图的单图确认。");
  return { stale_reasons: staleX.reasons.map((item) => item.field) };
});

test("RW-15", "整套确认不受影响：无 scope 字段，快照与单图确认不能互相冒充", async () => {
  const x = mainShot();
  const y = infographicShot();
  const xEntry = await compiledEntry(x);
  const yEntry = await compiledEntry(y, { shotSpec: noPrintSpec(y) });
  const sheetAll = sheetFixture(x, xEntry.record, { secondShot: y, secondRecord: yEntry.record });
  expect(sheetAll.scope_shot_ids === undefined, "整套确认不能带 scope 字段。");
  expect(sheetAll.shots.length === 2, "整套确认必须投影全部图。");
  const recordAll = await confirmationFixture(sheetAll);
  expect(recordAll.fingerprint.snapshot.scope_shot_ids === undefined, "整套快照不能带 scope。");
  expect(confirmationStaleness(recordAll, confirmationSnapshot(sheetAll)).stale === false,
    "同一份整套确认必须仍然有效。");
  const scoped = sheetFixture(x, xEntry.record, {
    secondShot: y, secondRecord: yEntry.record, shotIds: [x.shot_id],
  });
  expect(canonicalJson(confirmationSnapshot(scoped))
    !== canonicalJson(recordAll.fingerprint.snapshot), "单图确认与整套确认不能互相冒充。");
  return { shots: sheetAll.shots.length };
});

test("RW-16", "确认页图序与职责：编辑模式确认单带候选编辑源与商品原照，重生成模式不含候选", async () => {
  const shot = mainShot();
  const editDirective = directiveFixture(shot, { mode: "edit_candidate" });
  const editEntry = await compiledEntry(shot, { rework: editDirective });
  const editSheet = sheetFixture(shot, editEntry.record, { shotIds: [shot.shot_id] });
  const sheetRefs = editSheet.shots[0].references;
  const frozenRefs = editEntry.record.request_snapshot.references;
  expect(sheetRefs.length === frozenRefs.length,
    "确认单参考图数量必须与冻结请求一致：" + json(sheetRefs));
  expect(canonicalJson(sheetRefs.map((item) => item.uses)) === canonicalJson(frozenRefs.map((item) => item.uses)),
    "确认单用途必须与冻结请求同序一致：" + json(sheetRefs.map((item) => item.uses)));
  expect(canonicalJson(sheetRefs.map((item) => item.sha256_prefix))
    === canonicalJson(frozenRefs.map((item) => String(item.sha256).slice(0, 12))),
    "确认单必须按实际发送顺序列出图序：" + json(sheetRefs.map((item) => item.sha256_prefix)));
  const editSource = sheetRefs.find((item) => (item.uses || []).includes("edit_source"));
  // schema 2 确认单来源带 asset_sha256（冻结字节身份），与请求快照同形状（§13.8 一次切换）。
  expect(editSource !== undefined
    && canonicalJson(editSource.sources) === canonicalJson([{ kind: "candidate",
      document_id: shot.shot_id, version: CANDIDATE_VERSION, asset_sha256: SHA_A },
      { kind: "product_input", document_id: "intake", version: INTAKE_VERSION, asset_sha256: SHA_A }]),
    "编辑源必须标注固定问题候选与商品资料的精确文档版本与资产字节：" + json(editSource));
  expect(sheetRefs.every((item) => (item.uses || []).includes("edit_source")
    || (item.uses || []).includes("product_truth")),
    "编辑模式确认单每张参考图都要有职责说明：" + json(sheetRefs));
  const regenerateDirective = directiveFixture(shot, { mode: "regenerate_original" });
  const regenerateEntry = await compiledEntry(shot, { rework: regenerateDirective });
  const regenerateSheet = sheetFixture(shot, regenerateEntry.record, { shotIds: [shot.shot_id] });
  const regenerateRefs = regenerateSheet.shots[0].references;
  expect(regenerateRefs.length === regenerateEntry.record.request_snapshot.references.length,
    "重生成确认单数量必须与冻结请求一致：" + json(regenerateRefs));
  expect(regenerateRefs.every((item) => canonicalJson(item.uses) === canonicalJson(["product_truth"])),
    "原照重生成确认单不得出现候选编辑源：" + json(regenerateRefs));
  return { edit: sheetRefs.map((item) => item.uses.join("/")), regenerate: regenerateRefs.length };
});

/* ---------------------------------------------------------------- 运行器 */


/* Node 原生运行器：与原浏览器版同一批 cases，断言不改写。 */
import nodeTest from "node:test";
for (const item of cases) {
  nodeTest(`${item.id} :: ${item.title}`, { timeout: 60000 }, async () => { await item.run(); });
}