/**
 * V2.5.3 候选比较与审核清单的浏览器侧契约测试（真实 Chromium，非 Mock，纯领域函数）。
 *
 * 正向：异常优先排序、同档新到旧、默认目标、无发现/未知/未检查的区分、跳转与计数。
 * 反向：乱序、重复候选、pending 与状态不一致、过期报告冒充当前结论都必须被抓住。
 *
 * 结果写到 window.__V2_COMPARE_RESULTS__，由 tools/verify_v2_5_3_compare_panel.py 读取。
 */

import {
  COMPARE_PENDING_SEVERITIES,
  REVIEW_SEVERITY_ORDER,
  buildReviewReport,
  checkCompareRows,
  compareCounts,
  compareRowHeadline,
  compareRows,
  compareSeverityRank,
  compareStateOf,
  defaultCompareTargetId,
  nextPendingShotId,
  sortFindings,
} from "/domain/index.js";
import { expect, serializeError } from "./harness-api.js";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

const SHA = { a: "a".repeat(64), b: "b".repeat(64), c: "c".repeat(64) };

function candidateRecord(id, sha, overrides = {}) {
  return {
    candidate_id: id,
    shot_id: "shot_main",
    asset_sha256: sha,
    media_type: "image/png",
    width: 1024,
    height: 1024,
    attempt_action_id: "act-" + id,
    created_at: "2026-09-30T00:00:00Z",
    ...overrides,
  };
}

function finding(ruleId, severity, detail) {
  return { rule_id: ruleId, severity, detail: detail, measured: { fixture: true } };
}

const passFinding = () => finding("candidate.png_contract", "PASS", "PNG 合同通过");
const warningFinding = () => finding("platform.recommended_long_side", "WARNING", "长边低于推荐值");
const blockFinding = () => finding("platform.min_long_side", "BLOCK", "长边低于平台下限");
const unknownFinding = () => finding("vlm.inspection_unavailable", "UNKNOWN", "复核未完成");

function report(candidate, findings) {
  return buildReviewReport({
    candidate, findings, at: "2026-09-30T00:10:00Z",
  });
}

/**
 * 六个候选：两条阻断（一旧一新）、一条提醒、一条未知、一条无发现（最新）、一条没有报告。
 * 故意让「最新」的候选是无发现的那个，用来区分「异常优先」和「新到旧」。
 */
function scenario() {
  const records = {
    "cand-clean-newest": candidateRecord("cand-clean-newest", SHA.a),
    "cand-block-old": candidateRecord("cand-block-old", SHA.b),
    "cand-block-new": candidateRecord("cand-block-new", SHA.c),
    "cand-warn": candidateRecord("cand-warn", SHA.a),
    "cand-unknown": candidateRecord("cand-unknown", SHA.b),
    "cand-missing": candidateRecord("cand-missing", SHA.c),
  };
  const reports = {
    "cand-clean-newest": report(records["cand-clean-newest"], [passFinding()]),
    "cand-block-old": report(records["cand-block-old"], [blockFinding(), passFinding()]),
    "cand-block-new": report(records["cand-block-new"], [blockFinding()]),
    "cand-warn": report(records["cand-warn"], [warningFinding(), passFinding()]),
    "cand-unknown": report(records["cand-unknown"], [unknownFinding()]),
  };
  const candidates = [
    { record: records["cand-missing"], version: 1 },
    { record: records["cand-clean-newest"], version: 7 },
    { record: records["cand-block-old"], version: 3 },
    { record: records["cand-unknown"], version: 4 },
    { record: records["cand-block-new"], version: 5 },
    { record: records["cand-warn"], version: 6 },
  ];
  return {
    records, reports, candidates,
    rows: compareRows({
      candidates, reportsByCandidateId: reports,
      attemptsByActionId: {
        "act-cand-block-new": { action_id: "act-cand-block-new", task_id: "task-9f8e7d6c" },
      },
    }),
  };
}

function rowOf(rows, candidateId) {
  return rows.find((row) => row.candidate_id === candidateId) || null;
}

test("CP-01", "排序满足异常优先：有问题的候选排在无发现与未检查之前", () => {
  const { rows } = scenario();
  expect(rows.length === 6, "应有 6 个候选行，实际 " + rows.length);
  const ranks = rows.map((row) => compareSeverityRank(row.top_finding));
  for (let index = 1; index < ranks.length; index += 1) {
    expect(ranks[index] >= ranks[index - 1], "第 " + index + " 行的严重度秩不应小于前一行");
  }
  expect(rows[0].candidate_id === "cand-block-new", "最严重的候选应排在第一");
  expect(rows[rows.length - 1].candidate_id === "cand-missing", "未检查的候选应排在最后");
});

test("CP-02", "同档按版本新到旧：两条阻断按版本降序", () => {
  const { rows } = scenario();
  const blocked = rows.filter((row) => row.review_state === "pending")
    .map((row) => row.candidate_id);
  expect(blocked.join(",") === "cand-block-new,cand-block-old,cand-warn",
    "待处理候选应按版本降序，实际 " + blocked.join(","));
});

test("CP-03", "默认目标是异常优先而不是最新：最新的无发现候选不能让位", () => {
  const { rows } = scenario();
  const newest = rows.reduce((best, row) => (row.version > best.version ? row : best), rows[0]);
  expect(newest.candidate_id === "cand-clean-newest", "夹具里最新的候选应是无发现的那条");
  expect(defaultCompareTargetId(rows) === "cand-block-new", "默认目标必须是排在最前的候选");
  expect(defaultCompareTargetId([]) === null, "没有候选时应返回 null");
});

test("CP-04", "严重度顺序表只有一份：compare 模块与 review.js 共用同一顺序", () => {
  expect(compareSeverityRank({ severity: "BLOCK" }) === 0, "阻断应排第一");
  expect(compareSeverityRank({ severity: "UNKNOWN" }) === 3, "未知应排第四");
  expect(compareSeverityRank({ severity: "PASS" }) === REVIEW_SEVERITY_ORDER.length,
    "通过项不参与先看顺序");
  expect(compareSeverityRank(null) === REVIEW_SEVERITY_ORDER.length,
    "没有发现与通过项同级");
});

test("CP-05", "无发现 = clean：不是待处理，摘要说明只是机器结论", () => {
  const { rows } = scenario();
  const row = rowOf(rows, "cand-clean-newest");
  expect(row.review_state === "clean", "只通过的报告应是 clean");
  expect(row.pending === false, "clean 不是待处理");
  expect(row.top_finding === null, "clean 没有先看项");
  expect(compareRowHeadline(row).indexOf("机器结论") >= 0, "摘要应说明机器结论不是人工采纳");
});

test("CP-06", "没有报告 = unchecked：提示会自动补建，且不算待处理", () => {
  const { rows } = scenario();
  const row = rowOf(rows, "cand-missing");
  expect(row.review_state === "unchecked", "缺少报告应是 unchecked");
  expect(row.pending === false, "没有报告不能算作待处理结论");
  const text = compareRowHeadline(row);
  expect(text.indexOf("报告") >= 0 && text.indexOf("补建") >= 0, "摘要应说明报告会补建");
});

test("CP-07", "未知 = UNKNOWN：不算待处理，但仍排在无发现之前", () => {
  const { rows } = scenario();
  const unknown = rowOf(rows, "cand-unknown");
  const clean = rowOf(rows, "cand-clean-newest");
  expect(unknown.review_state === "unknown", "UNKNOWN 报告应是 unknown 状态");
  expect(unknown.pending === false, "未知不能升级为待处理硬门");
  expect(rows.indexOf(unknown) < rows.indexOf(clean), "未知应排在无发现之前");
});

test("CP-08", "审核清单排序稳定：阻断 → 提醒 → 未知 → 通过，同档保持原顺序", () => {
  const first = finding("candidate.png_contract", "PASS", "第一条通过");
  const second = finding("platform.alpha_channel", "PASS", "第二条通过");
  const sorted = sortFindings([
    first, warningFinding(), second, blockFinding(), unknownFinding(),
  ]);
  const severities = sorted.map((item) => item.severity).join(",");
  expect(severities === "BLOCK,WARNING,UNKNOWN,PASS,PASS", "清单顺序不正确：" + severities);
  expect(sorted[3].detail === "第一条通过" && sorted[4].detail === "第二条通过",
    "同档必须保持报告原顺序（稳定排序）");
});

test("CP-09", "下一个待处理：按计划顺序绕回，跳过没有问题的图", () => {
  const { rows } = scenario();
  const cleanRows = rows.filter((row) => !row.pending);
  const rowsByShotId = {
    s1: rows, s2: cleanRows, s3: rows.filter((row) => row.candidate_id === "cand-warn"),
  };
  const order = ["s1", "s2", "s3"];
  expect(nextPendingShotId({ rowsByShotId, shotOrder: order, currentShotId: "s1" }) === "s3",
    "应跳过无问题的 s2 直接到 s3");
  expect(nextPendingShotId({ rowsByShotId, shotOrder: order, currentShotId: "s2" }) === "s3",
    "从 s2 出发应到 s3");
  expect(nextPendingShotId({ rowsByShotId, shotOrder: order, currentShotId: "s3" }) === "s1",
    "到末尾应绕回 s1");
  expect(nextPendingShotId({
    rowsByShotId: { s1: cleanRows }, shotOrder: ["s1"], currentShotId: "s1",
  }) === null, "全部无问题时返回 null");
});

test("CP-10", "概览计数与行状态一致", () => {
  const { rows } = scenario();
  const counts = compareCounts(rows);
  expect(counts.total === rows.length, "总数应等于行数");
  expect(counts.pending === 3 && counts.unknown === 1 && counts.clean === 1
    && counts.unchecked === 1, "计数不正确：" + JSON.stringify(counts));
});

test("CP-11", "反向：乱序的行集合会被 checkCompareRows 抓住", () => {
  const { rows } = scenario();
  const scrambled = [rows[5], rows[0], rows[1], rows[2], rows[3], rows[4]];
  const problems = checkCompareRows(scrambled);
  expect(problems.length > 0, "乱序必须报错");
  expect(problems.some((item) => item.message.indexOf("异常优先") >= 0),
    "错误信息应指出顺序问题");
  expect(checkCompareRows(rows).length === 0, "正常行集合不应报错");
});

test("CP-12", "反向：重复候选会被抓住", () => {
  const { rows } = scenario();
  const duplicated = rows.concat([rows[0]]);
  const problems = checkCompareRows(duplicated);
  expect(problems.some((item) => item.message.indexOf("出现两次") >= 0),
    "同一个候选出现两次必须报错");
});

test("CP-13", "反向：pending 标记与状态不一致会被抓住", () => {
  const { rows } = scenario();
  const tampered = rows.map((row, index) => (index === 0
    ? { ...row, pending: false } : row));
  const problems = checkCompareRows(tampered);
  expect(problems.some((item) => item.message.indexOf("pending") >= 0),
    "pending 与 review_state 不一致必须报错");
});

test("CP-14", "比较行不含采纳字段：面板不产生 Selection", () => {
  const { rows } = scenario();
  const forbidden = ["selected", "selection", "adopted", "adoption", "chosen",
                     "selected_candidate_id"];
  for (const row of rows) {
    for (const key of Object.keys(row)) {
      expect(forbidden.indexOf(key) === -1, "比较行不应包含 " + key);
    }
  }
  const row = rows[0];
  expect(row.attempt_action_id === "act-cand-block-new", "行应保留来源 action 以便追溯");
  expect(row.task_id === "task-9f8e7d6c", "有 Attempt 记录时应带出 task id");
});

test("CP-15", "过期报告降级为未检查：不拿旧结论冒充当前结论", () => {
  const { reports } = scenario();
  const stale = reports["cand-block-new"];
  expect(compareStateOf(stale) === "pending", "夹具报告本身应是待处理");
  expect(compareStateOf(stale, { current: false }) === "unchecked",
    "报告与当前候选/合同不一致时必须降级为未检查");
  expect(compareStateOf(null) === "unchecked", "没有报告就是未检查");
});

async function runSuite() {
  const results = {
    suite: "v2.5.3-compare-panel",
    status: "running",
    cases: [],
    started_at: new Date().toISOString(),
  };
  window.__V2_COMPARE_RESULTS__ = results;
  for (const item of cases) {
    const startedAt = performance.now();
    try {
      await item.run();
      results.cases.push({
        id: item.id, title: item.title, ok: true,
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
  return results;
}

function render(results) {
  const node = document.getElementById("results");
  if (!node) return;
  node.textContent = JSON.stringify(results, null, 2);
}

const params = new URLSearchParams(location.search);
if (params.get("suite") !== "0") {
  runSuite().catch((error) => {
    window.__V2_COMPARE_RESULTS__ = {
      suite: "v2.5.3-compare-panel",
      status: "crashed",
      error: serializeError(error),
      cases: [],
    };
    render(window.__V2_COMPARE_RESULTS__);
  });
} else {
  window.__V2_COMPARE_RESULTS__ = {
    suite: "v2.5.3-compare-panel", status: "skipped", cases: [],
  };
}
