/**
 * V2.5.2 VLM 复核 Provider 的浏览器侧契约测试（Node 原生进程，非 Mock）。
 *
 * 正向：check 词表与规则注册表一一对应；成功信封合并进 ReviewReport；无发现落 PASS 完成标记；
 *       失败信封落 UNKNOWN；VLM 高风险不阻断导出（采纳权在人工）；报告重建可携带同一候选的复核块。
 * 反向：未知 check / 越界置信度 / 超长证据 / 跨候选绑定 / 过期合同 / 过期报告合并都必须被拒绝。
 *
 * 直接运行：node --test evals/product-v2/node/
 */

import {
  DETERMINISTIC_RULES,
  REVIEW_CONTRACT_VERSION,
  VLM_CHECK_TO_RULE,
  VLM_OUTCOMES,
  buildReviewReport,
  buildVlmReview,
  checkReviewReport,
  checkRuleRegistry,
  mergeVlmReview,
  reviewSummaryText,
  topFinding,
} from "../../../app/product_v2/domain/index.js";
import { expect, serializeError } from "./harness-core.mjs";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

const CANDIDATE = Object.freeze({
  candidate_id: "cand-vlm-0001",
  shot_id: "shot_main",
  asset_sha256: "a".repeat(64),
  media_type: "image/png",
});

function candidate(overrides = {}) {
  return { ...CANDIDATE, ...overrides };
}

function deterministicFindings() {
  return [{
    rule_id: "candidate.png_contract", severity: "PASS",
    detail: "PNG 合同通过（确定性层）", measured: {},
  }];
}

function baseReport(overrides = {}) {
  return buildReviewReport({
    candidate: candidate(overrides.candidate || {}),
    findings: deterministicFindings(),
    at: "2026-09-30T00:00:00Z",
  });
}

function okEnvelope(overrides = {}) {
  return {
    ok: true,
    unknown: false,
    result: {
      contract_version: REVIEW_CONTRACT_VERSION,
      candidate_sha256: CANDIDATE.asset_sha256,
      findings: [{
        check: "deformity",
        evidence: "杯口边缘出现第二道不自然的弧线",
        confidence: 0.72,
      }],
      summary: "模型摘要（不是采纳结论）",
      provider_id: "fake-review",
      model_id: "fake-qwen-vl-max",
      request_id: "req-vlm-1",
      checked_at: "2026-09-30T00:00:10Z",
      latency_ms: 123,
      ...(overrides.result || {}),
    },
    ...(overrides.envelope || {}),
  };
}

function failEnvelope(error = {}) {
  return {
    ok: false,
    unknown: true,
    error: {
      family: "provider_unknown",
      code: "PROVIDER_TIMEOUT",
      message: "读取超时；无法确认结果。",
      retry_policy: "requires_review",
      ...error,
    },
  };
}

function findingOf(report, ruleId) {
  return report.findings.find((item) => item.rule_id === ruleId) || null;
}

async function expectRejected(run, label) {
  try {
    await run();
  } catch (error) {
    return error.message || String(error);
  }
  throw new Error(label + "：期望被拒绝，但没有抛错。");
}

test("R14", "词表与纪律：check 映射齐全、每条映射都有 vlm 规则、无 BLOCK、outcome 词表固定", async () => {
  const checks = Object.keys(VLM_CHECK_TO_RULE);
  expect(checks.length === 7, "当前必须有 7 个 check（现在是 " + checks.length + "）");
  checks.forEach((check) => {
    const ruleId = VLM_CHECK_TO_RULE[check];
    const entry = DETERMINISTIC_RULES.find((item) => item.rule_id === ruleId);
    expect(entry, check + " 必须映射到已登记规则");
    expect(entry.layer === "vlm", ruleId + " 必须在 vlm 层");
    expect(entry.severity !== "BLOCK", ruleId + " 不得为 BLOCK");
  });
  expect(VLM_OUTCOMES.length === 2 && VLM_OUTCOMES.includes("checked")
    && VLM_OUTCOMES.includes("unknown"), "outcome 词表必须是 checked/unknown");
  expect(checkRuleRegistry().length === 0, "加入 vlm 规则后注册表仍必须零问题");
  return { checks: checks.length };
});

test("R15", "成功信封 → checked：发现按注册表严重度映射并绑定候选 sha，合并保留确定性层", async () => {
  const report = mergeVlmReview({
    report: baseReport(), candidate: candidate(), review: okEnvelope(),
    at: "2026-09-30T00:00:11Z",
  });
  expect(report.vlm.outcome === "checked", "outcome 必须是 checked");
  expect(report.vlm.asset_sha256 === CANDIDATE.asset_sha256, "复核块必须绑定候选 sha256");
  expect(report.vlm.provider_id === "fake-review", "复核块必须记录 provider 身份");
  expect(report.vlm.request_id === "req-vlm-1", "复核块必须记录 request id");
  const finding = findingOf(report, "vlm.deformity");
  expect(finding && finding.severity === "HIGH_RISK",
    "deformity 必须映射为注册表里的 HIGH_RISK");
  expect(finding.measured && finding.measured.confidence === 0.72, "发现必须保留模型置信度");
  expect(findingOf(report, "candidate.png_contract"), "确定性 findings 必须保留");
  expect(checkReviewReport(report).length === 0, "合并后的报告必须通过形状检查");
  expect(reviewSummaryText(report).includes("VLM 已检查"), "摘要必须显示 VLM 已检查");
  return { findings: report.findings.length };
});

test("R16", "无发现 → PASS 完成标记（机器事实，不是人工采纳）", async () => {
  const report = mergeVlmReview({
    report: baseReport(), candidate: candidate(),
    review: okEnvelope({ result: { findings: [] } }),
    at: "2026-09-30T00:00:12Z",
  });
  const marker = findingOf(report, "vlm.inspection_completed");
  expect(marker && marker.severity === "PASS", "无发现时必须落 vlm.inspection_completed/PASS");
  expect(marker.detail.includes("不等于人工采纳"), "PASS 标记必须声明不是采纳");
  expect(topFinding(report) === null || topFinding(report).severity !== "PASS",
    "PASS 不是需要人工先看的发现");
  return { outcome: report.vlm.outcome };
});

test("R17", "失败信封 → UNKNOWN：保留 family/code、不伪造 PASS、摘要显示未完成", async () => {
  const report = mergeVlmReview({
    report: baseReport(), candidate: candidate(), review: failEnvelope(),
    at: "2026-09-30T00:00:13Z",
  });
  expect(report.vlm.outcome === "unknown", "失败必须落 unknown");
  const finding = findingOf(report, "vlm.inspection_unavailable");
  expect(finding && finding.severity === "UNKNOWN", "失败必须落 UNKNOWN 提示");
  expect(finding.detail.includes("provider_unknown")
    && finding.detail.includes("PROVIDER_TIMEOUT"), "失败原因必须保留分类信息");
  expect(checkReviewReport(report).length === 0, "Unknown 报告必须仍然合法");
  expect(reviewSummaryText(report).includes("VLM 未完成"), "摘要必须显示 VLM 未完成");
  const again = mergeVlmReview({
    report: report, candidate: candidate(), review: failEnvelope(),
    at: "2026-09-30T00:00:14Z",
  });
  expect(again.findings.filter((item) => item.rule_id === "vlm.inspection_unavailable").length === 1,
    "重复失败不得堆积多条 UNKNOWN（VLM 层整体替换）");
  return { findings: report.findings.length };
});

test("R18", "反向：未知 check / 越界置信度 / 超长证据 / 跨候选绑定 / 过期合同全部拒绝", async () => {
  const rejected = {};
  rejected.unknown_check = await expectRejected(() => buildVlmReview({
    candidate: candidate(),
    review: okEnvelope({ result: { findings: [{ check: "no_such", evidence: "x", confidence: 0.5 }] } }),
    at: "2026-09-30T00:00:20Z",
  }), "未知 check");
  rejected.confidence = await expectRejected(() => buildVlmReview({
    candidate: candidate(),
    review: okEnvelope({ result: { findings: [{ check: "deformity", evidence: "x", confidence: 1.4 }] } }),
    at: "2026-09-30T00:00:21Z",
  }), "越界置信度");
  rejected.evidence = await expectRejected(() => buildVlmReview({
    candidate: candidate(),
    review: okEnvelope({ result: { findings: [{ check: "deformity", evidence: "x".repeat(301), confidence: 0.5 }] } }),
    at: "2026-09-30T00:00:22Z",
  }), "超长证据");
  rejected.cross_candidate = await expectRejected(() => buildVlmReview({
    candidate: candidate(),
    review: okEnvelope({ result: { candidate_sha256: "b".repeat(64) } }),
    at: "2026-09-30T00:00:23Z",
  }), "跨候选绑定");
  rejected.stale_contract = await expectRejected(() => buildVlmReview({
    candidate: candidate(),
    review: okEnvelope({ result: { contract_version: "v0" } }),
    at: "2026-09-30T00:00:24Z",
  }), "过期合同");
  return rejected;
});

test("R19", "合并前置：报告过期或候选不匹配时拒绝合并", async () => {
  const stale = { ...baseReport(), review_contract_version: "v0" };
  const a = await expectRejected(() => mergeVlmReview({
    report: stale, candidate: candidate(), review: okEnvelope(),
    at: "2026-09-30T00:00:30Z",
  }), "过期报告合并");
  const b = await expectRejected(() => mergeVlmReview({
    report: baseReport(), candidate: candidate({ asset_sha256: "c".repeat(64) }),
    review: okEnvelope(), at: "2026-09-30T00:00:31Z",
  }), "候选不匹配合并");
  return { stale: a, mismatch: b };
});

test("R20", "VLM 高风险不阻断导出：最高严重度为 HIGH_RISK，先看项指向它，采纳权仍在人工", async () => {
  const report = mergeVlmReview({
    report: baseReport(), candidate: candidate(), review: okEnvelope(),
    at: "2026-09-30T00:00:40Z",
  });
  expect(report.findings.every((item) => item.severity !== "BLOCK"),
    "VLM findings 不得出现 BLOCK");
  const top = topFinding(report);
  expect(top && top.rule_id === "vlm.deformity", "topFinding 必须指向高风险发现");
  expect(report.summary.HIGH_RISK === 1, "summary 必须计数高风险");
  const serialized = JSON.stringify(report).toLowerCase();
  expect(!serialized.includes("\"accepted\"") && !serialized.includes("\"selection\""),
    "复核报告不得包含自动采纳或选择字段");
  return { top: top.rule_id, high_risk: report.summary.HIGH_RISK };
});

test("R21", "报告重建携带同一候选的复核块；候选字节变化时不得携带", async () => {
  const reviewed = mergeVlmReview({
    report: baseReport(), candidate: candidate(), review: okEnvelope(),
    at: "2026-09-30T00:00:50Z",
  });
  const carried = reviewed.findings.filter((item) => item.layer === "vlm");
  const rebuilt = buildReviewReport({
    candidate: candidate(),
    findings: deterministicFindings().concat(carried),
    vlm: reviewed.vlm,
    at: "2026-09-30T00:00:51Z",
  });
  expect(rebuilt.vlm && rebuilt.vlm.outcome === "checked", "同一候选重建必须保留复核块");
  expect(checkReviewReport(rebuilt).length === 0, "重建报告必须合法");
  const rejected = await expectRejected(() => buildReviewReport({
    candidate: candidate({ asset_sha256: "d".repeat(64) }),
    findings: deterministicFindings().concat(carried),
    vlm: reviewed.vlm,
    at: "2026-09-30T00:00:52Z",
  }), "跨候选携带复核块");
  return { rebuilt: rebuilt.vlm.outcome, rejected: rejected.slice(0, 30) };
});

function render(results) {
  const node = document.getElementById("results");
  if (node) node.textContent = JSON.stringify(results, null, 2);
}


/* Node 原生运行器：与原浏览器版同一批 cases，断言不改写。 */
import nodeTest from "node:test";
for (const item of cases) {
  nodeTest(`${item.id} :: ${item.title}`, { timeout: 60000 }, async () => { await item.run(); });
}
