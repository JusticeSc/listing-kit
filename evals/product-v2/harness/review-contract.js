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

/* R3.2：纯领域断言已迁至 evals/product-v2/node/（同名 .test.mjs），此处仅保留宿主特有案例。 */

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
