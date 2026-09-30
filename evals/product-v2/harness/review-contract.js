/**
 * V2.5.1 确定性验证器契约测试（真实 Chromium，非 Mock）。
 *
 * 正向：规则注册表纪律（版本/消费者/测量/未知策略）；单图三层测量；生成前映射；
 *       导出就绪；哈希复算；报告绑定与当前性。
 * 反向（故意让守卫变红）：坏注册表条目必须报对应路径；未登记阻断代码必须抛错；
 *       坏字节、记录不一致、低分辨率、透明通道、过期报告、缺选择、哈希篡改都必须被抓住，
 *       而「字节不可读」必须降为 UNKNOWN 提示且不阻断。
 *
 * 结果写到 window.__V2_REVIEW_RESULTS__，由 tools/verify_v2_5_1_deterministic_review.py 读取。
 */

import {
  DETERMINISTIC_RULES,
  REVIEW_CONTRACT_VERSION,
  REVIEW_SEVERITIES,
  buildReviewReport,
  checkReviewReport,
  checkRuleRegistry,
  evaluateCandidateFindings,
  evaluateExportReadiness,
  evaluateGenerationFindings,
  reviewIsCurrent,
  reviewSummaryText,
  topFinding,
  verifyAssetHashes,
} from "/domain/index.js";
import { expect, expectCode, serializeError } from "./harness-api.js";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

function utf8(text) {
  return new TextEncoder().encode(text);
}

/** PNG 魔数必须是原始字节；不能用 utf8() 编码，\x89 会变成两字节的 C2 89。 */
const PNG_MAGIC_BYTES = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

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

/** 造一张结构完整的 PNG（CRC 为零，本项目的解析器只做结构校验，不校验 CRC）。 */
function pngBytes({ width, height, colorType = 2, bitDepth = 8, trns = false } = {}) {
  const ihdr = new Uint8Array(13);
  const view = new DataView(ihdr.buffer);
  view.setUint32(0, width);
  view.setUint32(4, height);
  ihdr[8] = bitDepth;
  ihdr[9] = colorType;
  const parts = [PNG_MAGIC_BYTES, chunk("IHDR", ihdr)];
  if (trns) parts.push(chunk("tRNS", new Uint8Array(6)));
  parts.push(chunk("IDAT", new Uint8Array([0x78, 0x9c, 0x00])));
  parts.push(chunk("IEND", new Uint8Array(0)));
  return concat(parts);
}

function candidateFor(bytes, overrides = {}) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  return {
    schema_version: 1,
    candidate_id: "act-review-0001",
    shot_id: "shot_main",
    action_id: "act-review-0001",
    task_id: "task-review-0001",
    asset_sha256: "a".repeat(64),
    media_type: "image/png",
    byte_size: bytes.length,
    width: view.getUint32(16),
    height: view.getUint32(20),
    provider: { provider_id: "dashscope-qwen-image", model_id: "qwen-image-3.0" },
    created_at: "2026-09-30T12:00:00+08:00",
    ...overrides,
  };
}

function findingFor(findings, ruleId) {
  return findings.find((item) => item.rule_id === ruleId) || null;
}

async function sha256Hex(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

test("R01", "注册表纪律：17 条规则、三层覆盖、零问题、版本与消费者齐备", async () => {
  expect(DETERMINISTIC_RULES.length === 17, "当前注册表必须是 17 条规则（现在是 "
    + DETERMINISTIC_RULES.length + "）");
  expect(checkRuleRegistry().length === 0, "正式注册表必须零问题");
  const layers = new Set(DETERMINISTIC_RULES.map((item) => item.layer));
  ["generation", "candidate", "export"].forEach((layer) => {
    expect(layers.has(layer), "必须覆盖 " + layer + " 层");
  });
  DETERMINISTIC_RULES.forEach((item) => {
    expect(Number.isInteger(item.version) && item.version >= 1, item.rule_id + " 必须有版本");
    expect(/@V\d+(\.\d+)+$/.test(item.consumer), item.rule_id + " 的消费者必须带任务锚点");
    expect(typeof item.measurement === "string" && item.measurement.length > 0,
      item.rule_id + " 必须有可复现测量");
    expect(["hint", "disable"].includes(item.unknown_policy), item.rule_id + " 必须有未知策略");
  });
  return { rules: DETERMINISTIC_RULES.length };
});

test("R02", "反向：坏注册表条目必须按路径报错（重复 id/坏版本/坏消费者/坏严重度/未认领代码）", async () => {
  const bad = [
    { rule_id: "x.one", version: 1, layer: "candidate", title: "t", severity: "BLOCK",
      consumer: "store@V2.5.1", measurement: "m", unknown_policy: "hint" },
    { rule_id: "x.one", version: 0, layer: "nope", title: "", severity: "PASS",
      consumer: "没有锚点", measurement: "", unknown_policy: "maybe" },
  ];
  const problems = checkRuleRegistry(bad);
  const paths = problems.map((item) => item.path);
  ["$[1].rule_id", "$[1].version", "$[1].layer", "$[1].title", "$[1].severity",
    "$[1].consumer", "$[1].measurement", "$[1].unknown_policy"].forEach((path) => {
    expect(paths.includes(path), "坏注册表必须报出 " + path);
  });
  expect(problems.some((item) => item.message.indexOf("确认单阻断代码") !== -1),
    "未被认领的确认单阻断代码必须报错");
  return { problems: problems.length };
});

test("R03", "合规候选：1344×1344、8 位、无透明通道 → 无 BLOCK，计数与发现一致", async () => {
  const bytes = pngBytes({ width: 1344, height: 1344 });
  const findings = evaluateCandidateFindings({
    candidate: candidateFor(bytes), bytes: bytes, roleId: "main",
  });
  expect(!findings.some((item) => item.severity === "BLOCK"), "合规候选不允许有 BLOCK");
  expect(findingFor(findings, "platform.min_long_side").severity === "PASS", "最小长边必须 PASS");
  expect(findingFor(findings, "platform.recommended_long_side").severity === "WARNING",
    "1344px 低于推荐 1600px，必须是提醒而不是阻断");
  expect(findingFor(findings, "platform.main_square").severity === "PASS", "1:1 主图必须 PASS");
  expect(findingFor(findings, "platform.alpha_channel").severity === "PASS", "无透明必须 PASS");
  return { findings: findings.length };
});

test("R04", "反向：800px 候选必须 BLOCK，且 topFinding 指向该阻断", async () => {
  const bytes = pngBytes({ width: 800, height: 800 });
  const findings = evaluateCandidateFindings({
    candidate: candidateFor(bytes), bytes: bytes, roleId: "main",
  });
  const min = findingFor(findings, "platform.min_long_side");
  expect(min.severity === "BLOCK", "低于 1000px 必须阻断");
  expect(min.measured.long_side === 800, "测量值必须是 800");
  const report = buildReviewReport({
    candidate: candidateFor(bytes), findings: findings, at: "2026-09-30T12:00:00+08:00",
  });
  expect(report.summary.BLOCK === 1, "汇总必须计 1 个阻断");
  expect(topFinding(report).rule_id === "platform.min_long_side", "topFinding 必须指向最小长边");
  return { block: report.summary.BLOCK };
});

test("R05", "主图非 1:1 是提醒；非主图角色不出现该规则", async () => {
  const bytes = pngBytes({ width: 1344, height: 1000 });
  const main = evaluateCandidateFindings({
    candidate: candidateFor(bytes, { height: 1000 }), bytes: bytes, roleId: "main",
  });
  expect(findingFor(main, "platform.main_square").severity === "WARNING",
    "主图偏离 1:1 必须是提醒（审美不冒充硬门）");
  const scene = evaluateCandidateFindings({
    candidate: candidateFor(bytes, { height: 1000 }), bytes: bytes, roleId: "scene",
  });
  expect(findingFor(scene, "platform.main_square") === null, "非主图不评估 1:1 规则");
  return { main: 1, scene: 0 };
});

test("R06", "透明通道（颜色类型 6 或 tRNS）必须是 HIGH_RISK 而不是 BLOCK", async () => {
  const rgba = pngBytes({ width: 1344, height: 1344, colorType: 6 });
  const first = evaluateCandidateFindings({
    candidate: candidateFor(rgba), bytes: rgba, roleId: "main",
  });
  const alpha = findingFor(first, "platform.alpha_channel");
  expect(alpha.severity === "HIGH_RISK", "RGBA 必须给 HIGH_RISK");
  expect(!first.some((item) => item.severity === "BLOCK"), "透明通道不允许变成 BLOCK");
  const palette = pngBytes({ width: 1344, height: 1344, colorType: 3, trns: true });
  const second = evaluateCandidateFindings({
    candidate: candidateFor(palette), bytes: palette, roleId: "main",
  });
  expect(findingFor(second, "platform.alpha_channel").severity === "HIGH_RISK",
    "调色板 + tRNS 同样必须给 HIGH_RISK");
  return { rgba: 1, trns: 1 };
});
test("R07", "位深 16 是提醒；记录与字节不一致是阻断", async () => {
  const deep = pngBytes({ width: 1344, height: 1344, bitDepth: 16 });
  const findings = evaluateCandidateFindings({
    candidate: candidateFor(deep), bytes: deep, roleId: "main",
  });
  expect(findingFor(findings, "candidate.pixel_depth").severity === "WARNING",
    "16 位必须是提醒（不阻断）");
  const mismatch = evaluateCandidateFindings({
    candidate: candidateFor(deep, { width: 1000 }), bytes: deep, roleId: "main",
  });
  const record = findingFor(mismatch, "candidate.record_consistent");
  expect(record.severity === "BLOCK", "记录与字节不一致必须阻断");
  expect(record.measured.record.width === 1000 && record.measured.measured.width === 1344,
    "测量必须同时给出记录值与实读值");
  return { probed: 2 };
});

test("R08", "反向：坏字节 → PNG 合同阻断；字节不可读 → 逐条 UNKNOWN 且绝不阻断", async () => {
  const validBytes = pngBytes({ width: 1344, height: 1344 });
  const validCandidate = candidateFor(validBytes);
  const garbage = new Uint8Array(64);
  const broken = evaluateCandidateFindings({
    candidate: validCandidate, bytes: garbage, roleId: "main",
  });
  expect(findingFor(broken, "candidate.png_contract").severity === "BLOCK",
    "坏签名必须阻断");
  const unreadable = evaluateCandidateFindings({
    candidate: validCandidate, bytes: null, roleId: "main",
  });
  expect(unreadable.filter((item) => item.severity === "UNKNOWN").length >= 5,
    "字节不可读时每条测量规则都必须降级为 UNKNOWN");
  expect(!unreadable.some((item) => item.severity === "BLOCK"),
    "测量失败不允许变成阻断（未知只提示）");
  const report = buildReviewReport({
    candidate: validCandidate, findings: unreadable, at: "2026-09-30T12:00:00+08:00",
  });
  expect(report.summary.BLOCK === 0 && report.summary.UNKNOWN >= 5,
    "报告必须如实记录 UNKNOWN 而不是伪装通过");
  return { unknown: report.summary.UNKNOWN };
});

test("R09", "生成前：blocker 映射为 BLOCK、risk 映射为提醒、干净确认单 ready；未登记代码抛错", async () => {
  const sheet = {
    shots: [
      { shot_id: "shot_main", label: "主图", blockers: [
        { code: "PROMPT_STALE", message: "Prompt 已过期", fix: { region: "prompt" } },
      ], risks: [] },
      { shot_id: "shot_scene", label: "场景图", blockers: [], risks: [{ message: "卖点较密集" }] },
    ],
  };
  const result = evaluateGenerationFindings(sheet);
  expect(result.ready === false, "有 blocker 时不允许 ready");
  const prompt = findingFor(result.findings, "generation.prompt_current");
  expect(prompt && prompt.severity === "BLOCK", "PROMPT_STALE 必须映射到 Prompt 当前性阻断");
  expect(prompt.measured.fix && prompt.measured.fix.region === "prompt", "必须带修复位置");
  const risk = findingFor(result.findings, "generation.risk_visible");
  expect(risk && risk.severity === "WARNING", "风险项必须是提醒而不是阻断");
  const clean = evaluateGenerationFindings({
    shots: [{ shot_id: "shot_main", label: "主图", blockers: [], risks: [] }],
  });
  expect(clean.ready === true && clean.findings.length === 0, "干净确认单必须 ready 且无发现");
  await expectCode(() => evaluateGenerationFindings({
    shots: [{ shot_id: "shot_main", label: "主图", blockers: [{ code: "NOT_A_CODE" }], risks: [] }],
  }), "CONTRACT_INVALID", "未登记阻断代码必须抛错");
  return { generation_findings: result.findings.length };
});

test("R10", "导出就绪：完整链可导出；缺选择/过期报告/报告含阻断/链断裂都必须被拦", async () => {
  const at = "2026-09-30T12:00:00+08:00";
  const bytes = pngBytes({ width: 1344, height: 1344 });
  const candidate = candidateFor(bytes);
  const findings = evaluateCandidateFindings({ candidate: candidate, bytes: bytes, roleId: "main" });
  const goodReport = buildReviewReport({ candidate: candidate, findings: findings, at: at });
  const attempt = {
    action_id: candidate.action_id, task_id: candidate.task_id,
    shot_id: candidate.shot_id, state: "succeeded",
  };
  const base = {
    shots: [{ shot_id: "shot_main", required: true }],
    selections: { shot_main: candidate.candidate_id },
    candidatesByShot: { shot_main: [{ record: candidate, version: 1 }] },
    reportsByCandidate: { [candidate.candidate_id]: goodReport },
    attemptsByShot: { shot_main: [{ record: attempt, version: 1 }] },
  };
  const ready = evaluateExportReadiness(base);
  expect(ready.exportable === true, "完整链必须可导出");
  expect(ready.findings.filter((item) => item.severity === "PASS").length === 4,
    "四条同步导出规则都必须给出 PASS 记录");
  const missing = evaluateExportReadiness({ ...base, selections: {} });
  expect(missing.exportable === false
    && findingFor(missing.findings, "export.selection_complete").severity === "BLOCK",
    "缺必需选择必须阻断");
  const stale = evaluateExportReadiness({
    ...base,
    reportsByCandidate: { [candidate.candidate_id]:
      { ...goodReport, review_contract_version: "v0.0.1" } },
  });
  expect(stale.exportable === false
    && findingFor(stale.findings, "export.report_current").severity === "BLOCK",
    "过期合同版本的报告必须阻断");
  const badBytes = pngBytes({ width: 800, height: 800 });
  const badCandidate = candidateFor(badBytes, {
    candidate_id: "act-review-0002", action_id: "act-review-0002", task_id: "task-0002",
  });
  const badReport = buildReviewReport({
    candidate: badCandidate,
    findings: evaluateCandidateFindings({ candidate: badCandidate, bytes: badBytes, roleId: "main" }),
    at: at,
  });
  const blocking = evaluateExportReadiness({
    ...base,
    selections: { shot_main: badCandidate.candidate_id },
    candidatesByShot: { shot_main: [{ record: badCandidate, version: 1 }] },
    reportsByCandidate: { [badCandidate.candidate_id]: badReport },
    attemptsByShot: { shot_main: [{ record: { ...attempt, action_id: badCandidate.action_id,
      task_id: badCandidate.task_id }, version: 1 }] },
  });
  expect(blocking.exportable === false
    && findingFor(blocking.findings, "export.no_blocking_findings").severity === "BLOCK",
    "所选报告含 BLOCK 时必须拦截");
  const noAttempt = evaluateExportReadiness({ ...base, attemptsByShot: {} });
  expect(noAttempt.exportable === false
    && findingFor(noAttempt.findings, "export.chain_integrity").severity === "BLOCK",
    "来源 Attempt 缺失必须拦截");
  return { probed: 5 };
});

test("R11", "哈希复算：真实 WebCrypto 一致通过；篡改与缺失阻断；缺 digest 注入抛错", async () => {
  const bytes = pngBytes({ width: 1344, height: 1344 });
  const sha = await sha256Hex(bytes);
  const candidate = candidateFor(bytes, { asset_sha256: sha });
  const input = {
    selections: { shot_main: candidate.candidate_id },
    candidatesByShot: { shot_main: [{ record: candidate, version: 1 }] },
  };
  const ok = await verifyAssetHashes({ ...input, readBytes: async () => bytes, digest: sha256Hex });
  expect(ok.ok === true
    && findingFor(ok.findings, "export.asset_hash_matches").severity === "PASS",
    "一致字节必须通过");
  const tampered = await verifyAssetHashes({
    ...input, readBytes: async () => pngBytes({ width: 1000, height: 1000 }), digest: sha256Hex,
  });
  expect(tampered.ok === false
    && findingFor(tampered.findings, "export.asset_hash_matches").severity === "BLOCK",
    "篡改字节必须阻断");
  const missing = await verifyAssetHashes({
    ...input, readBytes: async () => null, digest: sha256Hex,
  });
  expect(missing.ok === false, "字节缺失必须阻断");
  await expectCode(() => verifyAssetHashes({ ...input, readBytes: async () => bytes }),
    "CONTRACT_INVALID", "缺 digest 注入必须抛错");
  return { sha: sha.slice(0, 12) };
});
test("R12", "报告模型：绑定身份、冻结、当前性；篡改汇总/未登记规则/空 findings 都被检查器抓住", async () => {
  const at = "2026-09-30T12:00:00+08:00";
  const bytes = pngBytes({ width: 1344, height: 1344 });
  const candidate = candidateFor(bytes);
  const findings = evaluateCandidateFindings({ candidate: candidate, bytes: bytes, roleId: "main" });
  const report = buildReviewReport({ candidate: candidate, findings: findings, at: at });
  expect(Object.isFrozen(report) && Object.isFrozen(report.findings)
    && Object.isFrozen(report.summary), "报告、findings、summary 都必须冻结");
  expect(report.review_contract_version === REVIEW_CONTRACT_VERSION, "合同版本必须是当前值");
  expect(report.candidate_id === candidate.candidate_id
    && report.asset_sha256 === candidate.asset_sha256, "报告必须绑定候选身份与字节哈希");
  expect(checkReviewReport(report).length === 0, "合法报告必须零问题");
  expect(reviewIsCurrent(report, candidate) === true, "同一候选同一合同必须判当前");
  expect(reviewIsCurrent(report, { ...candidate, asset_sha256: "b".repeat(64) }) === false,
    "字节哈希变化必须判过期");
  expect(reviewIsCurrent({ ...report, review_contract_version: "v0" }, candidate) === false,
    "合同版本变化必须判过期");
  const tampered = checkReviewReport({
    ...report, summary: { ...report.summary, BLOCK: report.summary.BLOCK + 1 },
  });
  expect(tampered.some((item) => item.path === "$.summary.BLOCK"),
    "汇总与 findings 不一致必须被抓住");
  const unknownRule = checkReviewReport({
    ...report,
    findings: [{ rule_id: "nope.nope", severity: "PASS", detail: "x" }],
  });
  expect(unknownRule.some((item) => item.path === "$.findings[0].rule_id"),
    "未登记规则必须被抓住");
  await expectCode(() => buildReviewReport({ candidate: candidate, findings: [], at: at }),
    "CONTRACT_INVALID", "空 findings 必须拒绝");
  await expectCode(() => buildReviewReport({
    candidate: candidate,
    findings: [{ rule_id: "nope.nope", severity: "PASS", detail: "x" }], at: at,
  }), "CONTRACT_INVALID", "未登记规则必须拒绝");
  return { probed: 7 };
});

test("R13", "摘要与排序：topFinding 按 BLOCK>HIGH_RISK>WARNING>UNKNOWN；摘要文本含各类计数", async () => {
  const at = "2026-09-30T12:00:00+08:00";
  const bytes = pngBytes({ width: 1344, height: 1344 });
  const candidate = candidateFor(bytes);
  const ordered = [
    { rule_id: "generation.risk_visible", severity: "WARNING", detail: "提醒项" },
    { rule_id: "candidate.pixel_depth", severity: "UNKNOWN", detail: "未知项" },
    { rule_id: "platform.alpha_channel", severity: "HIGH_RISK", detail: "高风险项" },
    { rule_id: "platform.min_long_side", severity: "BLOCK", detail: "阻断项" },
  ];
  const report = buildReviewReport({ candidate: candidate, findings: ordered, at: at });
  expect(topFinding(report).severity === "BLOCK", "topFinding 必须最先返回 BLOCK");
  const text = reviewSummaryText(report);
  ["阻断 1", "高风险 1", "提醒 1", "未知 1"].forEach((part) => {
    expect(text.indexOf(part) !== -1, "摘要必须包含「" + part + "」：" + text);
  });
  expect(REVIEW_SEVERITIES.length === 5, "严重度词表必须保持五项");
  return { text: text };
});

/* ---------------------------------------------------------------- 运行器 */

function render(results) {
  const node = document.getElementById("results");
  if (node) node.textContent = JSON.stringify(results, null, 2);
}

async function runSuite() {
  const results = {
    suite: "v2.5.1-deterministic-review",
    status: "running",
    cases: [],
    started_at: new Date().toISOString(),
  };
  window.__V2_REVIEW_RESULTS__ = results;
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
    window.__V2_REVIEW_RESULTS__ = {
      suite: "v2.5.1-deterministic-review",
      status: "crashed",
      error: serializeError(error),
      cases: [],
    };
    render(window.__V2_REVIEW_RESULTS__);
  });
} else {
  window.__V2_REVIEW_RESULTS__ = {
    suite: "v2.5.1-deterministic-review", status: "skipped", cases: [],
  };
}
