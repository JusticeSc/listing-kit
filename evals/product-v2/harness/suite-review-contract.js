/**
 * V2.5.5 整套一致性契约测试（真实 Chromium，非 Mock）。
 *
 * 正向：suite 规则登记；确定性 BLOCK/WARNING 与 affected_shot_ids；一次完整装配（确定性 + 视觉）
 *       产出当前报告；指纹变化即过期。
 * 反向：缺选择、重复任务、卖点未覆盖、越界 shot_id、视觉通道失败与超限都必须被抓住且只落 Unknown。
 *
 * 结果写到 window.__V2_SUITE_RESULTS__，由 tools/verify_v2_5_5_suite_review.py 读取。
 */

import {
  SUITE_REVIEW_CONTRACT_VERSION,
  SUITE_VLM_CHECK_TO_RULE,
  assembleSuiteReview,
  buildReviewReport,
  buildSelectionRecord,
  buildSelectionSet,
  checkSuiteReviewReport,
  evaluateCandidateFindings,
  inputsFingerprintOf,
  selectionFingerprintOf,
  suiteReviewIsCurrent,
  registeredRule,
} from "/domain/index.js";
import { sha256Hex } from "/storage/db.js";
import { expect, serializeError } from "./harness-api.js";

const cases = [];
const AT = "2026-10-01T02:00:00+08:00";

function test(id, title, run) {
  cases.push({ id, title, run });
}

const PNG_MAGIC_BYTES = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

function utf8(text) {
  return new TextEncoder().encode(text);
}

function concat(parts) {
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.length;
  }
  return out;
}

function chunk(type, payload) {
  const out = new Uint8Array(12 + payload.length);
  const view = new DataView(out.buffer);
  view.setUint32(0, payload.length);
  out.set(utf8(type), 4);
  out.set(payload, 8);
  return out;
}

function pngBytes({ width, height, colorType = 2 } = {}) {
  const ihdr = new Uint8Array(13);
  const view = new DataView(ihdr.buffer);
  view.setUint32(0, width);
  view.setUint32(4, height);
  ihdr[8] = 8;
  ihdr[9] = colorType;
  return concat([PNG_MAGIC_BYTES, chunk("IHDR", ihdr),
    chunk("IDAT", new Uint8Array([0x78, 0x9c, 0x00])), chunk("IEND", new Uint8Array(0))]);
}

function shotOf(shotId, overrides = {}) {
  return {
    shot_id: shotId, role_id: "primary", role_label: "商品主图", label: "图 " + shotId,
    required: true, custom: true, template_id: null, fact_slot_ids: [], dependencies: [],
    intent: "展示商品", ...overrides,
  };
}

function candidateOf({ shotId, candidateId, sha, byteSize }) {
  return {
    schema_version: 1,
    candidate_id: candidateId,
    shot_id: shotId,
    action_id: candidateId,
    task_id: "task-" + candidateId,
    asset_sha256: sha,
    media_type: "image/png",
    byte_size: byteSize,
    width: 1600,
    height: 1600,
    provider: { provider_id: "dashscope-qwen-image", model_id: "qwen-image-3.0" },
    created_at: AT,
  };
}

function attemptOf(candidate) {
  return { action_id: candidate.action_id, task_id: candidate.task_id, shot_id: candidate.shot_id };
}

function findingIds(findings, ruleId) {
  const found = findings.filter((item) => item.rule_id === ruleId);
  return found.length ? found[0].affected_shot_ids.join(",") : null;
}

async function fixture() {
  const bytes = pngBytes({ width: 1600, height: 1600 });
  const sha = await sha256Hex(bytes);
  const main = candidateOf({ shotId: "shot_main", candidateId: "cand_main", sha: sha,
    byteSize: bytes.length });
  const scene = candidateOf({ shotId: "shot_scene", candidateId: "cand_scene", sha: sha,
    byteSize: bytes.length });
  const report = buildReviewReport({
    candidate: main, at: AT,
    findings: evaluateCandidateFindings({ candidate: main, bytes: bytes, roleId: "main" }),
  });
  const sceneReport = buildReviewReport({
    candidate: scene, at: AT,
    findings: evaluateCandidateFindings({ candidate: scene, bytes: bytes, roleId: "main" }),
  });
  const selectionFor = (shotId, candidate) => buildSelectionRecord({
    selectionId: "sel-" + shotId, action: "select", shotId: shotId, candidate: candidate,
    candidateVersion: 1, report: report, at: AT,
  });
  const shots = [shotOf("shot_main"), shotOf("shot_scene")];
  const selectionSet = buildSelectionSet({
    shots: shots.map((shot) => ({ shot_id: shot.shot_id, required: shot.required })),
    selections: {
      shot_main: selectionFor("shot_main", main),
      shot_scene: selectionFor("shot_scene", scene),
    },
    candidatesByShotId: { shot_main: [main], shot_scene: [scene] },
    at: AT,
  });
  return { bytes, sha, main, scene, report, sceneReport, selectionSet, shots };
}

function vlmRun(submitted, findings, extra = {}) {
  return {
    envelope: {
      ok: true,
      result: {
        contract_version: SUITE_REVIEW_CONTRACT_VERSION,
        submitted_shot_ids: submitted,
        findings: findings,
        provider_id: "fake-suite-review",
        model_id: "fake-qwen-vl-max",
        request_id: "req-1",
        checked_at: AT,
        latency_ms: 12,
        summary: "契约测试",
      },
    },
    reason: null,
    requested_shot_ids: submitted,
    submitted_shot_ids: submitted,
    asset_sha256_by_shot: {},
    ...extra,
  };
}

function assembleInputs(fx, vlm) {
  return {
    selectionSet: fx.selectionSet,
    suitePlan: { schema_version: 1, shots: fx.shots },
    styleSpec: { schema_version: 1, background: "白底", lighting: "柔和", color_tone: "",
      composition: "", avoid: [] },
    shotSpecsById: {
      shot_main: { schema_version: 1, purpose: "白底展示", keep: ["商品外观"],
        change_allowed: ["背景"], notes: "" },
      shot_scene: { schema_version: 1, purpose: "场景展示", keep: ["商品外观"],
        change_allowed: ["背景"], notes: "" },
    },
    context: { facts: [], assets: [] },
    factsById: {},
    sellingPoints: [],
    shots: [{ shot_id: "shot_main", required: true }, { shot_id: "shot_scene", required: true }],
    selections: { shot_main: "cand_main", shot_scene: "cand_scene" },
    candidatesByShot: { shot_main: [fx.main], shot_scene: [fx.scene] },
    attemptsByShot: { shot_main: [attemptOf(fx.main)], shot_scene: [attemptOf(fx.scene)] },
    reportsByCandidate: { cand_main: fx.report, cand_scene: fx.sceneReport },
    readBytes: async (sha) => (sha === fx.sha ? fx.bytes : null),
    digest: sha256Hex,
    vlmRun: vlm,
    at: AT,
  };
}

test("S01", "suite 规则登记：BLOCK/WARNING/视觉规则齐备，视觉规则不得为 BLOCK", async () => {
  expect(registeredRule("suite.selection_current").severity === "BLOCK", "suite.selection_current 必须 BLOCK");
  expect(registeredRule("suite.dependency_satisfied").severity === "BLOCK", "suite.dependency_satisfied 必须 BLOCK");
  ["suite.duplicates", "suite.recommended_omissions", "suite.selling_point_coverage"]
    .forEach((ruleId) => expect(registeredRule(ruleId) && registeredRule(ruleId).severity === "WARNING",
      ruleId + " 必须登记为 WARNING"));
  Object.keys(SUITE_VLM_CHECK_TO_RULE).forEach((check) => {
    const rule = registeredRule(SUITE_VLM_CHECK_TO_RULE[check]);
    expect(rule && rule.severity !== "BLOCK", check + " 映射的规则不得是 BLOCK");
  });
  return { checks: Object.keys(SUITE_VLM_CHECK_TO_RULE).length };
});

test("S02", "缺必需选择：suite.selection_current 报 BLOCK 且 affected_shot_ids 精确", async () => {
  const fx = await fixture();
  const inputs = assembleInputs(fx, vlmRun(["shot_main", "shot_scene"], []));
  inputs.selectionSet = buildSelectionSet({
    shots: [{ shot_id: "shot_main", required: true }, { shot_id: "shot_scene", required: true }],
    selections: { shot_main: fx.selectionSet.entries[0] ? null : null },
    candidatesByShotId: { shot_main: [fx.main], shot_scene: [fx.scene] },
    at: AT,
  });
  const report = await assembleSuiteReview(inputs);
  expect(findingIds(report.findings, "suite.selection_current") === "shot_main,shot_scene",
    "缺选择必须带全部的 Shot 归属（实际：" + findingIds(report.findings, "suite.selection_current") + "）");
  expect(report.summary.BLOCK >= 1, "缺必需选择必须是 BLOCK");
  return { block: report.summary.BLOCK };
});

test("S03", "重复任务与卖点未覆盖：两条 WARNING 都要出现并可定位", async () => {
  const fx = await fixture();
  const inputs = assembleInputs(fx, vlmRun(["shot_main", "shot_scene"], []));
  inputs.suitePlan = {
    schema_version: 1,
    shots: [shotOf("shot_main", { template_id: "dup_tpl" }),
      shotOf("shot_scene", { template_id: "dup_tpl" })],
  };
  inputs.sellingPoints = ["12小时保温"];
  const report = await assembleSuiteReview(inputs);
  expect(findingIds(report.findings, "suite.duplicates") === "shot_main,shot_scene",
    "重复任务必须两条 Shot 都列出");
  const coverage = report.findings.find((item) => item.rule_id === "suite.selling_point_coverage");
  expect(coverage && coverage.severity === "WARNING" && coverage.detail.indexOf("12小时保温") >= 0,
    "未覆盖卖点必须报 WARNING 并点名卖点");
  expect(coverage && coverage.affected_shot_ids.length === 0,
    "计划级发现（卖点覆盖）没有单图归属，必须是空数组而不是乱指一张图");
  return { warnings: report.summary.WARNING };
});

test("S04", "完整装配：确定性零 BLOCK、视觉 checked、报告当前；指纹变化即过期", async () => {
  const fx = await fixture();
  const inputs = assembleInputs(fx, vlmRun(["shot_main", "shot_scene"], []));
  const report = await assembleSuiteReview(inputs);
  expect(report.contract_version === SUITE_REVIEW_CONTRACT_VERSION, "报告合同版本必须是当前值");
  expect(checkSuiteReviewReport(report).length === 0, "合法报告必须零问题");
  const blockRules = report.findings.filter((item) => item.severity === "BLOCK")
    .map((item) => item.rule_id + "：" + item.detail).join(" ｜ ");
  expect(report.summary.BLOCK === 0,
    "完整采用 + 报告当前 + 哈希一致时不得有 BLOCK（实际：" + blockRules + "）");
  expect(report.vlm && report.vlm.outcome === "checked", "视觉复核必须落 checked");
  expect(findingIds(report.findings, "vlm.suite_inspection_completed") === "",
    "无发现时必须有完成性 PASS（affected_shot_ids 为空）");
  const selectionFingerprint = selectionFingerprintOf(inputs.selectionSet);
  const inputsFingerprint = inputsFingerprintOf({
    selectionFingerprint: selectionFingerprint,
    suitePlan: inputs.suitePlan,
    styleSpec: inputs.styleSpec,
    shotSpecsById: inputs.shotSpecsById,
    reportsByCandidate: inputs.reportsByCandidate,
  });
  expect(suiteReviewIsCurrent(report, { selectionFingerprint: selectionFingerprint,
    inputsFingerprint: inputsFingerprint }) === true, "同一指纹必须判当前");
  expect(suiteReviewIsCurrent(report, { selectionFingerprint: selectionFingerprint + "x",
    inputsFingerprint: inputsFingerprint }) === false, "选择指纹变化必须判过期");
  return { summary: report.summary };
});

test("S05", "视觉漂移：check 映射到登记规则；越界 shot_id 必须落 UNKNOWN（protocol）", async () => {
  const fx = await fixture();
  const drift = vlmRun(["shot_main", "shot_scene"], [
    { check: "suite_product_consistency", shot_ids: ["shot_main", "shot_scene"],
      evidence: "两张图的商品比例不一致。", confidence: 0.7 },
    { check: "suite_style_consistency", shot_ids: ["shot_scene"],
      evidence: "第二张背景色温偏暖。", confidence: 0.5 },
  ]);
  const report = await assembleSuiteReview(assembleInputs(fx, drift));
  const product = report.findings.find((item) => item.rule_id === "vlm.suite_product_consistency");
  expect(product && product.severity === "HIGH_RISK", "跨图商品一致性必须是 HIGH_RISK");
  expect(product && product.affected_shot_ids.join(",") === "shot_main,shot_scene",
    "发现必须保留 AI 给的 Shot 归属");
  const outside = vlmRun(["shot_main", "shot_scene"], [
    { check: "suite_product_consistency", shot_ids: ["shot_outside"],
      evidence: "引用了没送审的图。", confidence: 0.9 },
  ]);
  const rejected = await assembleSuiteReview(assembleInputs(fx, outside));
  expect(rejected.vlm.outcome === "unknown", "越界输出必须落 Unknown");
  expect(rejected.findings.some((item) => item.rule_id === "vlm.suite_inspection_unavailable"
    && item.severity === "UNKNOWN"), "必须出现未完成 UNKNOWN 行");
  expect(!rejected.findings.some((item) => item.rule_id === "vlm.suite_product_consistency"),
    "越界发现不得被当成有效发现");
  return { high_risk: report.summary.HIGH_RISK };
});

test("S06", "视觉失败与超限：只落 UNKNOWN，确定性部分不受影响", async () => {
  const fx = await fixture();
  const serverFailure = {
    envelope: { ok: false, unknown: true,
      error: { family: "internal", code: "PROVIDER_NOT_CONFIGURED", message: "未配置密钥。",
        retry_policy: "fatal" } },
    reason: "server", requested_shot_ids: ["shot_main", "shot_scene"],
    submitted_shot_ids: [], asset_sha256_by_shot: {},
  };
  const report = await assembleSuiteReview(assembleInputs(fx, serverFailure));
  const unknown = report.findings.find((item) => item.rule_id === "vlm.suite_inspection_unavailable");
  expect(unknown && unknown.severity === "UNKNOWN", "视觉失败必须是 UNKNOWN");
  expect(unknown && unknown.measured && unknown.measured.reason === "server",
    "必须保留分类原因（server）");
  const blockRules = report.findings.filter((item) => item.severity === "BLOCK")
    .map((item) => item.rule_id + "：" + item.detail).join(" ｜ ");
  expect(report.summary.BLOCK === 0,
    "视觉失败不得让确定性部分变成 BLOCK（实际：" + blockRules + "）");
  const overLimit = { envelope: null, reason: "over_limit", requested_shot_ids: ["shot_main"],
    submitted_shot_ids: [], asset_sha256_by_shot: {} };
  const limited = await assembleSuiteReview(assembleInputs(fx, overLimit));
  const limitedUnknown = limited.findings
    .find((item) => item.rule_id === "vlm.suite_inspection_unavailable");
  expect(limitedUnknown && limitedUnknown.measured.reason === "over_limit", "超限必须记 over_limit");
  return { unknown: report.summary.UNKNOWN };
});

async function runSuite() {
  const results = {
    suite: "v2.5.5-suite-review", status: "passed", cases: [],
    started_at: new Date().toISOString(), finished_at: null,
  };
  for (const item of cases) {
    const startedAt = performance.now();
    try {
      const detail = await item.run();
      results.cases.push({ id: item.id, title: item.title, status: "passed",
        detail: detail === undefined ? null : detail, duration_ms: Math.round(performance.now() - startedAt) });
    } catch (error) {
      results.status = "failed";
      results.cases.push({ id: item.id, title: item.title, status: "failed",
        error: serializeError(error), duration_ms: Math.round(performance.now() - startedAt) });
    }
  }
  results.finished_at = new Date().toISOString();
  return results;
}

function render(results) {
  const node = document.getElementById("results");
  if (node) node.textContent = JSON.stringify(results, null, 1);
}

runSuite().then((results) => {
  window.__V2_SUITE_RESULTS__ = results;
  render(results);
}).catch((error) => {
  window.__V2_SUITE_RESULTS__ = {
    suite: "v2.5.5-suite-review", status: "crashed", error: serializeError(error), cases: [],
  };
  render(window.__V2_SUITE_RESULTS__);
});
