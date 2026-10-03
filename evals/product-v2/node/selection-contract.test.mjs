/**
 * V2.6.1 人工选择契约测试（Node 原生进程，非 Mock，纯领域函数）。
 *
 * 正向：采用记录绑定候选身份/候选版本/审核指纹与时间、没有报告也能采用但明确留白、
 *       取消采用与原候选解耦、改选后重新变 current、SelectionSet 必需/可选计数。
 * 反向：跨图候选、缺身份、非法 sha、非正整数版本、未知动作、过高 schema 版本、
 *       篡改记录、非法时间戳不得误判过期、过期投影不许偷换成最新候选。
 *
 * 直接运行：node --test evals/product-v2/node/
 */

import {
  DOMAIN_ERROR_CODES,
  SELECTION_ACTIONS,
  SELECTION_CONTRACT_VERSION,
  SELECTION_SCHEMA_VERSION,
  SELECTION_STATES,
  SELECTION_STATE_TEXT,
  assertSelectionRecord,
  buildReviewReport,
  buildSelectionRecord,
  buildSelectionSet,
  checkSelectionRecord,
  deriveSelectionState,
  selectionCoversShot,
  selectionReviewFingerprint,
  selectionSetText,
  selectionStateLabel,
  selectionSummaryText,
} from "../../../app/product_v2/domain/index.js";

import { expect, expectCode, serializeError } from "./harness-core.mjs";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

const BASE_TIME = "2026-09-30T04:00:00+08:00";
const LATER_TIME = "2026-09-30T04:30:00+08:00";
const EARLIER_TIME = "2026-09-30T03:30:00+08:00";
const SHA_A = "a".repeat(64);
const SHA_B = "b".repeat(64);
const SHOT = "shot_main_clean";
const OTHER_SHOT = "shot_infographic_benefits";

function candidateFixture(overrides = {}) {
  return {
    candidate_id: "cand-main-001",
    shot_id: SHOT,
    asset_sha256: SHA_A,
    media_type: "image/png",
    width: 1600,
    height: 1600,
    attempt_action_id: "act-001",
    created_at: BASE_TIME,
    ...overrides,
  };
}

function reportFixture(candidate, overrides = {}) {
  return buildReviewReport({
    candidate: candidate,
    findings: overrides.findings || [{
      rule_id: "platform.min_long_side", severity: "BLOCK",
      detail: "长边 64px 低于平台缩放下限 1000px。", measured: { long_side: 64 },
    }],
    at: overrides.at || BASE_TIME,
  });
}

function selectionFixture(overrides = {}) {
  const cleared = overrides.action === "clear";
  const candidate = overrides.candidate || candidateFixture();
  return buildSelectionRecord({
    selectionId: overrides.selectionId || "sel-0001",
    action: overrides.action || "select",
    shotId: overrides.shotId || candidate.shot_id,
    candidate: cleared ? null : candidate,
    candidateVersion: cleared ? null : (overrides.candidateVersion || 1),
    report: overrides.report === undefined
      ? (cleared ? null : reportFixture(candidate)) : overrides.report,
    at: overrides.at || BASE_TIME,
  });
}

test("SL-01", "采用记录绑定候选身份、候选版本、审核指纹与时间（唯一权威字段齐全）", () => {
  const candidate = candidateFixture();
  const report = reportFixture(candidate);
  const record = selectionFixture({ candidate: candidate, report: report,
    candidateVersion: 3, at: LATER_TIME });
  expect(record.schema_version === SELECTION_SCHEMA_VERSION, "schema 版本必须是当前版本。");
  expect(record.contract_version === SELECTION_CONTRACT_VERSION,
    "合同版本必须是 " + SELECTION_CONTRACT_VERSION + "。");
  expect(record.action === "select" && record.shot_id === SHOT, "动作与目标图必须落在记录里。");
  expect(record.candidate_id === candidate.candidate_id && record.candidate_sha256 === SHA_A
    && record.candidate_version === 3, "采用必须绑定候选身份与候选记录版本。");
  expect(record.created_at === LATER_TIME, "选择时间按传入时间落盘（时钟由界面提供）。");
  expect(record.review_fingerprint && record.review_fingerprint.candidate_id === candidate.candidate_id
    && record.review_fingerprint.asset_sha256 === SHA_A
    && record.review_fingerprint.top_severity === "BLOCK"
    && record.review_fingerprint.top_rule_id === "platform.min_long_side"
    && record.review_fingerprint.finding_count === 1,
    "审核指纹必须记录「当时看得见什么」。");
  expect(Object.isFrozen(record) && Object.isFrozen(record.review_fingerprint),
    "记录与指纹必须是不可变快照。");
  expect(checkSelectionRecord(record).length === 0, "合法记录的自检必须为空。");
  return { candidate_version: record.candidate_version, fingerprint: record.review_fingerprint };
});

test("SL-02", "没有当前报告也可以采用，但记录必须写明「没有报告」（指纹为 null）", () => {
  const candidate = candidateFixture();
  const record = selectionFixture({ candidate: candidate, report: null });
  expect(record.review_fingerprint === null, "没有报告时不得编造指纹。");
  expect(checkSelectionRecord(record).length === 0, "缺报告不阻断人工选择。");
  const withReport = selectionFixture({ candidate: candidate, report: reportFixture(candidate) });
  expect(withReport.review_fingerprint !== null, "有报告时必须记下指纹。");
  return { without_report: record.review_fingerprint,
    with_report: withReport.review_fingerprint.top_severity };
});

test("SL-03", "采用必须来自这张图的候选：跨图、缺身份、非法 sha、非正整数版本都要被拒", async () => {
  const other = candidateFixture({ shot_id: OTHER_SHOT, candidate_id: "cand-other-001" });
  await expectCode(() => buildSelectionRecord({ selectionId: "sel-03a", action: "select",
    shotId: SHOT, candidate: other, candidateVersion: 1, at: BASE_TIME }),
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "跨图候选");
  await expectCode(() => buildSelectionRecord({ selectionId: "sel-03b", action: "select",
    shotId: SHOT, candidate: null, candidateVersion: 1, at: BASE_TIME }),
    DOMAIN_ERROR_CODES.CONTRACT_INVALID, "缺候选");
  await expectCode(() => buildSelectionRecord({ selectionId: "sel-03c", action: "select",
    shotId: SHOT, candidate: candidateFixture({ asset_sha256: "short" }), candidateVersion: 1,
    at: BASE_TIME }), DOMAIN_ERROR_CODES.CONTRACT_INVALID, "sha256 非法");
  for (const version of [0, -1, 1.5, null]) {
    await expectCode(() => buildSelectionRecord({ selectionId: "sel-03d", action: "select",
      shotId: SHOT, candidate: candidateFixture(), candidateVersion: version, at: BASE_TIME }),
      DOMAIN_ERROR_CODES.CONTRACT_INVALID, "候选版本 " + String(version));
  }
  return { rejected: 7 };
});

test("SL-04", "取消采用不携带候选身份；携带任何候选字段的记录都不合法", () => {
  const cleared = selectionFixture({ action: "clear" });
  expect(cleared.action === "clear" && cleared.candidate_id === null
    && cleared.candidate_sha256 === null && cleared.candidate_version === null
    && cleared.review_fingerprint === null, "取消采用必须与原候选解耦。");
  expect(checkSelectionRecord(cleared).length === 0, "合法的取消记录自检为空。");
  const tampered = { ...cleared, candidate_id: "cand-main-001" };
  const problems = checkSelectionRecord(tampered);
  expect(problems.some((item) => item.path === "$.candidate_id"),
    "带候选身份的取消记录必须报 $.candidate_id。");
  return { problems: problems.map((item) => item.path) };
});

test("SL-05", "记录自检：未知动作、缺目标图、非 ISO 时间、过高 schema 版本各落在正确路径", () => {
  const record = selectionFixture();
  const byPath = {};
  const patches = {
    action: { action: "adopt" },
    shot: { shot_id: "" },
    time: { created_at: "2026-09-30 04:00" },
    schema: { schema_version: SELECTION_SCHEMA_VERSION + 1 },
    contract: { contract_version: "v2.5.0" },
  };
  for (const label of Object.keys(patches)) {
    const problems = checkSelectionRecord({ ...record, ...patches[label] });
    byPath[label] = problems.map((item) => item.path + ":" + item.code);
    expect(problems.length >= 1, label + " 的篡改必须被检出。");
  }
  expect(byPath.action[0].startsWith("$.action"), "未知动作落在 $.action。");
  expect(byPath.shot[0].startsWith("$.shot_id"), "缺 shot_id 落在 $.shot_id。");
  expect(byPath.time[0].startsWith("$.created_at"), "非 ISO 时间落在 $.created_at。");
  expect(byPath.schema[0].startsWith("$.schema_version")
    && byPath.schema[0].includes(DOMAIN_ERROR_CODES.CONTRACT_SCHEMA_TOO_NEW),
    "过高 schema 版本必须是 SCHEMA_TOO_NEW，不许降级读取。");
  expect(byPath.contract[0].startsWith("$.contract_version"), "旧合同版本落在 $.contract_version。");
  return byPath;
});

test("SL-06", "失效判断四态：none / current / cleared / stale", () => {
  const candidate = candidateFixture();
  const record = selectionFixture({ candidate: candidate });
  expect(deriveSelectionState(null, [candidate]) === "none", "没有选择记录时是 none。");
  expect(deriveSelectionState(record, [candidate]) === "current", "选择时已有的候选不引起过期。");
  expect(deriveSelectionState(record, [candidate, candidateFixture({
    candidate_id: "cand-main-002", created_at: LATER_TIME })]) === "stale",
    "之后出现的新成功候选必须让选择过期。");
  const cleared = selectionFixture({ action: "clear", at: LATER_TIME });
  expect(deriveSelectionState(cleared, [candidate]) === "cleared", "取消采用是独立状态。");
  expect(selectionStateLabel("stale") === SELECTION_STATE_TEXT.stale, "状态文案必须来自同一张表。");
  return { states: SELECTION_STATES.slice() };
});

test("SL-07", "过期只认更晚的成功候选：更早或同刻的候选都不引起过期", () => {
  const candidate = candidateFixture();
  const record = selectionFixture({ candidate: candidate, at: LATER_TIME });
  const earlier = candidateFixture({ candidate_id: "cand-main-000", created_at: EARLIER_TIME });
  const sameMoment = candidateFixture({ candidate_id: "cand-main-001b", created_at: LATER_TIME });
  expect(deriveSelectionState(record, [earlier, sameMoment]) === "current",
    "更早或同刻的候选不能把选择判成过期。");
  expect(deriveSelectionState(record, [candidateFixture({
    candidate_id: "cand-main-003", created_at: "2026-09-30T05:00:00+08:00" })]) === "stale",
    "更晚的候选必须判成过期。");
  return { earlier: deriveSelectionState(record, [earlier]),
    same_moment: deriveSelectionState(record, [sameMoment]), later: "stale" };
});
test("SL-08", "反向：非法时间戳与「没有候选」都不能被误判成过期", () => {
  const candidate = candidateFixture();
  const record = selectionFixture({ candidate: candidate });
  const broken = [
    { candidate_id: "cand-broken-1", created_at: "not-a-time" },
    { candidate_id: "cand-broken-2" },
    null,
    { payload: { candidate_id: "cand-broken-3", created_at: 42 } },
  ];
  expect(deriveSelectionState(record, broken) === "current",
    "失败 Attempt 不产生候选；解析不了时间的记录不许触发过期。");
  expect(deriveSelectionState(null, broken) === "none", "没有记录时仍是 none。");
  expect(deriveSelectionState(undefined, undefined) === "none", "缺参数不许抛错。");
  const wrapped = [{ record: { candidate_id: "cand-new",
    created_at: "2026-09-30T06:00:00+08:00" } }];
  expect(deriveSelectionState(record, wrapped) === "stale",
    "带 record 包装的候选行同样参与判断。");
  return { broken: broken.length };
});

test("SL-09", "改选：更晚的选择动作重新变 current，投影指向新采用的候选", () => {
  const first = candidateFixture();
  const second = candidateFixture({ candidate_id: "cand-main-002", asset_sha256: SHA_B,
    created_at: LATER_TIME });
  const record = selectionFixture({ candidate: second, candidateVersion: 2,
    at: "2026-09-30T05:00:00+08:00" });
  const state = deriveSelectionState(record, [first, second]);
  const covers = selectionCoversShot(record, [first, second]);
  expect(state === "current" && covers.state === "current" && covers.current === true,
    "改选之后必须当前有效。");
  expect(covers.candidate_id === second.candidate_id, "投影必须指向新采用的候选。");
  expect(record.candidate_version === 2 && record.candidate_sha256 === SHA_B,
    "改选记录绑定的是新候选身份。");
  return { state: state, candidate: covers.candidate_id };
});

test("SL-10", "过期投影不偷换身份：stale 时仍指向被采用的候选，而不是最新候选", () => {
  const adopted = candidateFixture();
  const record = selectionFixture({ candidate: adopted });
  const newer = candidateFixture({ candidate_id: "cand-main-004", asset_sha256: SHA_B,
    created_at: "2026-09-30T07:00:00+08:00" });
  const covers = selectionCoversShot(record, [adopted, newer]);
  expect(covers.state === "stale" && covers.current === false, "新候选出现后必须标成过期。");
  expect(covers.candidate_id === adopted.candidate_id, "过期不等于改选：身份仍是原候选。");
  expect(covers.candidate_id !== newer.candidate_id, "不许把最新候选冒充成已采用。");
  return covers;
});

test("SL-11", "SelectionSet：必需图的 current / stale / missing 与可选项分开计数", () => {
  const main = candidateFixture();
  const info = candidateFixture({ shot_id: OTHER_SHOT, candidate_id: "cand-info-001" });
  const shots = [{ shot_id: SHOT, required: true }, { shot_id: OTHER_SHOT, required: true },
    { shot_id: "shot_optional", required: false }];
  const selections = {
    [SHOT]: selectionFixture({ candidate: main }),
    [OTHER_SHOT]: selectionFixture({ candidate: info, selectionId: "sel-011-info", at: BASE_TIME }),
  };
  const candidatesByShotId = {
    [SHOT]: [main, candidateFixture({ candidate_id: "cand-main-009",
      created_at: "2026-09-30T08:00:00+08:00" })],
    [OTHER_SHOT]: [info],
  };
  const set = buildSelectionSet({ shots: shots, selections: selections,
    candidatesByShotId: candidatesByShotId, at: LATER_TIME });
  expect(set.contract_version === SELECTION_CONTRACT_VERSION, "集合版本必须与记录同源。");
  expect(set.summary.required_total === 2 && set.summary.current === 1
    && set.summary.stale === 1 && set.summary.missing === 0,
    "必需图的三种状态必须分开计数：" + JSON.stringify(set.summary));
  expect(set.summary.optional_current === 0, "可选项不参与必需图统计。");
  const cleared = buildSelectionSet({ shots: shots,
    selections: { [SHOT]: selectionFixture({ action: "clear" }) },
    candidatesByShotId: { [SHOT]: [main] }, at: LATER_TIME });
  expect(cleared.summary.missing === 2, "取消采用必须计入缺选。");
  return { summary: set.summary, cleared: cleared.summary };
});

test("SL-12", "SelectionSet 只引用内容寻址身份，且是纯投影（不改输入、不含图片字节）", () => {
  const main = candidateFixture();
  const shots = [{ shot_id: SHOT, required: true }];
  const selections = { [SHOT]: selectionFixture({ candidate: main }) };
  const candidatesByShotId = { [SHOT]: [main] };
  const before = JSON.stringify({ shots: shots, selections: selections,
    candidatesByShotId: candidatesByShotId });
  const set = buildSelectionSet({ shots: shots, selections: selections,
    candidatesByShotId: candidatesByShotId, at: LATER_TIME });
  const entry = set.entries[0];
  const keys = Object.keys(entry).sort().join(",");
  expect(keys === "candidate_id,candidate_sha256,candidate_version,required,selected_at,"
    + "selection_id,shot_id,state", "条目字段是闭集合：" + keys);
  expect(entry.candidate_sha256 === SHA_A && entry.candidate_version === 1,
    "只留身份与版本，不留像素。");
  expect(JSON.stringify({ shots: shots, selections: selections,
    candidatesByShotId: candidatesByShotId }) === before, "纯投影不许改动输入对象。");
  const serialized = JSON.stringify(set);
  expect(serialized.indexOf("blob") < 0 && serialized.indexOf("data:" ) < 0,
    "集合里不许出现图片字节。");
  return { keys: keys };
});

test("SL-13", "摘要文案四态互不相同：过期必须说清过期，未采用不许暗示已就绪", () => {
  const candidate = candidateFixture();
  const record = selectionFixture({ candidate: candidate });
  const none = selectionSummaryText(null, "none");
  const current = selectionSummaryText(record, "current");
  const stale = selectionSummaryText(record, "stale");
  const cleared = selectionSummaryText(selectionFixture({ action: "clear" }), "cleared");
  const texts = [none, current, stale, cleared];
  expect(new Set(texts).size === 4, "四种状态必须给出不同文案。");
  const set = buildSelectionSet({ shots: [{ shot_id: SHOT, required: true }],
    selections: {}, candidatesByShotId: {}, at: LATER_TIME });
  expect(selectionSetText(set).indexOf("0/1") >= 0, "整套摘要必须给出必需图进度。");
  return { texts: texts.map((item) => item.length) };
});

test("SL-14", "自检对篡改记录判红：值域越界被检出，assertSelectionRecord 抛领域错误", () => {
  const record = selectionFixture();
  const sameShape = { ...record, candidate_sha256: "0".repeat(64) };
  expect(checkSelectionRecord(sameShape).length === 0,
    "形状合法的替换值不算形状错误（身份是否与本图候选一致由候选链与导出硬门负责）。");
  const broken = { ...record, candidate_sha256: "0".repeat(63) };
  const problems = checkSelectionRecord(broken);
  expect(problems.some((item) => item.path === "$.candidate_id"),
    "不足 64 位的 sha 必须落在 $.candidate_id。");
  let code = null;
  try {
    assertSelectionRecord(broken);
  } catch (error) {
    code = error.code;
  }
  expect(code === DOMAIN_ERROR_CODES.CONTRACT_INVALID, "assertSelectionRecord 必须抛领域错误。");
  return { broken: problems.map((item) => item.path), code: code };
});

test("SL-15", "审核指纹随报告变化：同一份报告稳定，不同 top 发现必须不同", () => {
  const candidate = candidateFixture();
  const blocking = reportFixture(candidate);
  const warning = buildReviewReport({
    candidate: candidate,
    findings: [{ rule_id: "platform.recommended_long_side", severity: "WARNING",
      detail: "长边 1200px 低于推荐值 1600px。", measured: { long_side: 1200 } }],
    at: BASE_TIME,
  });
  const first = selectionReviewFingerprint(blocking);
  const again = selectionReviewFingerprint(blocking);
  const second = selectionReviewFingerprint(warning);
  expect(JSON.stringify(first) === JSON.stringify(again), "同一份报告必须给出同样的指纹。");
  expect(first.top_severity === "BLOCK" && second.top_severity === "WARNING"
    && first.top_rule_id !== second.top_rule_id, "不同发现必须给出不同指纹。");
  expect(selectionReviewFingerprint(null) === null
    && selectionReviewFingerprint(42) === null, "没有报告时不得编造指纹。");
  return { blocking: first, warning: second };
});

test("SL-16", "词表纪律：动作、状态与文案表一一对应，不许各自解释一遍", () => {
  expect(SELECTION_ACTIONS.length === 2 && SELECTION_ACTIONS.indexOf("select") >= 0
    && SELECTION_ACTIONS.indexOf("clear") >= 0, "动作必须是 select / clear。");
  expect(SELECTION_STATES.length === 4
    && SELECTION_STATES.every((state) => typeof SELECTION_STATE_TEXT[state] === "string"),
    "四种状态都必须有文案。");
  expect(Object.keys(SELECTION_STATE_TEXT).length === SELECTION_STATES.length,
    "文案表不许有多余键。");
  expect(selectionStateLabel("mystery") === "未知状态", "未知状态必须有兜底文案。");
  return { actions: SELECTION_ACTIONS.slice(), states: SELECTION_STATES.slice() };
});

test("SL-17", "反向：残缺输入不得让投影层抛错（空项目或损坏记录下也要能渲染）", () => {
  expect(deriveSelectionState(null) === "none", "空记录。");
  expect(deriveSelectionState({ action: "select" }) === "none", "缺时间的记录不许当 current。");
  expect(deriveSelectionState({ action: "clear" }) === "cleared", "取消采用不依赖时间。");
  const set = buildSelectionSet({});
  expect(set.entries.length === 0 && set.summary.required_total === 0,
    "空输入必须给出空集合。");
  expect(selectionSetText(null) === "", "空集合文案为空字符串。");
  expect(selectionCoversShot({ action: "select", candidate_id: "cand-x",
    created_at: BASE_TIME }, null).state === "current", "没有候选链时保持当前。");
  return { states: ["none", "cleared"] };
});

test("SL-18", "记录是字段闭集合：不夹带 blob、像素、坐标或未登记字段", () => {
  const record = selectionFixture();
  const keys = Object.keys(record).sort();
  expect(keys.join(",") === "action,candidate_id,candidate_sha256,candidate_version,"
    + "contract_version,created_at,review_fingerprint,schema_version,selection_id,shot_id",
    "选择记录字段是闭集合：" + keys.join(","));
  const fingerprintKeys = Object.keys(record.review_fingerprint).sort();
  expect(fingerprintKeys.join(",") === "asset_sha256,candidate_id,finding_count,"
    + "report_created_at,review_contract_version,top_rule_id,top_severity",
    "指纹字段是闭集合：" + fingerprintKeys.join(","));
  expect(!("blob" in record) && !("pixels" in record) && !("bytes" in record),
    "记录里不许出现图片内容。");
  return { keys: keys, fingerprint_keys: fingerprintKeys };
});


/* Node 原生运行器：与原浏览器版同一批 cases，断言不改写。 */
import nodeTest from "node:test";
for (const item of cases) {
  nodeTest(`${item.id} :: ${item.title}`, { timeout: 60000 }, async () => { await item.run(); });
}
