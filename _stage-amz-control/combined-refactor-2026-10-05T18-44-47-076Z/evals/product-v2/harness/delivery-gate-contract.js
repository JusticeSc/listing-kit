/**
 * V2.6.2 交付门禁与交付包契约测试（真实 Chromium，非 Mock）。
 *
 * 正向：完整采用 + 当前单图报告 + 当前整套报告 + 哈希一致 → 门禁 ready，7 条规则全 PASS。
 * 反向：缺必需选择、整套报告缺失或过期、未确认 Unknown、字节哈希不符都必须 BLOCK。
 * 交付包：条目集合、逐条字节、manifest 反查、导出记录身份（append-only）。
 *
 * 结果写到 window.__V2_DELIVERY_RESULTS__，由 tools/verify_v2_6_2_delivery.py 读取。
 */

import {
  EXPORT_GATE_CONTRACT_VERSION,
  acknowledgementDocumentIdOf,
  assembleSuiteReview,
  buildAcknowledgement,
  buildDeliveryEntries,
  buildExportRecord,
  buildReviewReport,
  buildSelectionRecord,
  buildSelectionSet,
  checkSuiteReviewReport,
  deliveryFileName,
  deliveryImagePathOf,
  evaluateCandidateFindings,
  evaluateDeliveryGate,
  exportRecordDocumentIdOf,
  inputsFingerprintOf,
  resolveUnknowns,
  selectionFingerprintOf,
  suiteReviewIsCurrent,
} from "/domain/index.js";
import { sha256Hex } from "/storage/db.js";
import { buildZip, crc32, readZip } from "/storage/zip.js";
import { expect, serializeError } from "./harness-api.js";

const cases = [];
const AT = "2026-10-01T05:00:00+08:00";

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

function vlmRun(submitted, findings, extra = {}) {
  return {
    envelope: {
      ok: true,
      result: {
        contract_version: "v2.5.5",
        submitted_shot_ids: submitted,
        findings: findings,
        provider_id: "fake-suite-review",
        model_id: "fake-qwen-vl-max",
        request_id: "req-contract",
        checked_at: AT,
        latency_ms: 9,
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

/** 两张必需图（各一个当前候选与当前报告）的完整夹具；未知项由 unknownOnMain 注入。 */
async function fixture({ unknownOnMain = false } = {}) {
  const bytes = pngBytes({ width: 1600, height: 1600 });
  const sha = await sha256Hex(bytes);
  const main = candidateOf({ shotId: "shot_main", candidateId: "cand_main", sha: sha,
    byteSize: bytes.length });
  const scene = candidateOf({ shotId: "shot_scene", candidateId: "cand_scene", sha: sha,
    byteSize: bytes.length });
  const mainFindings = [...evaluateCandidateFindings({ candidate: main, bytes: bytes, roleId: "main" })];
  if (unknownOnMain) {
    mainFindings.push({ rule_id: "vlm.inspection_unavailable", severity: "UNKNOWN",
      detail: "契约测试：视觉通道未完成。" });
  }
  const mainReport = buildReviewReport({ candidate: main, at: AT, findings: mainFindings });
  const sceneReport = buildReviewReport({
    candidate: scene, at: AT,
    findings: evaluateCandidateFindings({ candidate: scene, bytes: bytes, roleId: "main" }),
  });
  const selectionFor = (shotId, candidate) => buildSelectionRecord({
    selectionId: "sel-" + shotId, action: "select", shotId: shotId, candidate: candidate,
    candidateVersion: 1, report: mainReport, at: AT,
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
  return { bytes, sha, main, scene, mainReport, sceneReport, selectionSet, shots };
}

function assembleInputs(fx, vlm, overrides = {}) {
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
    reportsByCandidate: { cand_main: fx.mainReport, cand_scene: fx.sceneReport },
    readBytes: async (sha) => (sha === fx.sha ? fx.bytes : null),
    digest: sha256Hex,
    vlmRun: vlm,
    at: AT,
    ...overrides,
  };
}

async function currentSuite(fx, vlm) {
  const inputs = assembleInputs(fx, vlm);
  const report = await assembleSuiteReview(inputs);
  const selectionFingerprint = selectionFingerprintOf(inputs.selectionSet);
  const inputsFingerprint = inputsFingerprintOf({
    selectionFingerprint: selectionFingerprint,
    suitePlan: inputs.suitePlan,
    styleSpec: inputs.styleSpec,
    shotSpecsById: inputs.shotSpecsById,
    reportsByCandidate: inputs.reportsByCandidate,
  });
  return { inputs, report, fingerprints: { selectionFingerprint, inputsFingerprint } };
}

function gateInputs(fx, suite, overrides = {}) {
  return {
    shots: [{ shot_id: "shot_main", required: true }, { shot_id: "shot_scene", required: true }],
    selections: { shot_main: "cand_main", shot_scene: "cand_scene" },
    candidatesByShot: { shot_main: [fx.main], shot_scene: [fx.scene] },
    reportsByCandidate: { cand_main: fx.mainReport, cand_scene: fx.sceneReport },
    attemptsByShot: { shot_main: [attemptOf(fx.main)], shot_scene: [attemptOf(fx.scene)] },
    readBytes: async (sha) => (sha === fx.sha ? fx.bytes : null),
    digest: sha256Hex,
    suiteReport: suite ? suite.report : null,
    suiteFingerprints: suite ? suite.fingerprints : null,
    acknowledgements: [],
    ...overrides,
  };
}

function severityOf(gate, ruleId) {
  const found = gate.findings.find((item) => item.rule_id === ruleId);
  return found ? found.severity : null;
}

test("D01", "正向：完整采用 + 当前报告 + 哈希一致 → ready 且七条规则全 PASS", async () => {
  const fx = await fixture();
  const suite = await currentSuite(fx, vlmRun(["shot_main", "shot_scene"], []));
  expect(checkSuiteReviewReport(suite.report).length === 0, "整套报告必须合法");
  const gate = await evaluateDeliveryGate(gateInputs(fx, suite));
  expect(gate.contract_version === EXPORT_GATE_CONTRACT_VERSION, "门禁合同版本必须是当前值");
  expect(gate.ready_to_export === true, "正向门禁必须 ready（实际："
    + gate.findings.filter((item) => item.severity === "BLOCK")
      .map((item) => item.rule_id + "：" + item.detail).join(" ｜ ") + "）");
  expect(gate.blocking.length === 0, "正向门禁不得有 BLOCK");
  ["export.selection_complete", "export.chain_integrity", "export.report_current",
   "export.no_blocking_findings", "export.asset_hash_matches", "export.suite_review_current",
   "export.unknown_acknowledged"].forEach((ruleId) => {
    expect(severityOf(gate, ruleId) === "PASS", ruleId + " 必须是 PASS");
  });
  expect(gate.unknowns.length === 0, "没有 Unknown 时 unknowns 必须是空数组");
  return { findings: gate.findings.length, status: gate.status };
});

test("D02", "反向：缺必需图选择 → selection_complete BLOCK 且点名 Shot", async () => {
  const fx = await fixture();
  const suite = await currentSuite(fx, vlmRun(["shot_main", "shot_scene"], []));
  const gate = await evaluateDeliveryGate(gateInputs(fx, suite, {
    selections: { shot_main: "cand_main" },
  }));
  expect(gate.ready_to_export === false, "缺必需选择必须阻断");
  expect(severityOf(gate, "export.selection_complete") === "BLOCK", "缺选择必须 BLOCK");
  const row = gate.findings.find((item) => item.rule_id === "export.selection_complete");
  expect((row.affected_shot_ids || []).join(",") === "shot_scene",
    "必须点名缺哪张图（实际：" + JSON.stringify(row.affected_shot_ids) + "）");
  return { detail: row.detail };
});

test("D03", "反向：整套报告缺失或过期 → suite_review_current BLOCK", async () => {
  const fx = await fixture();
  const suite = await currentSuite(fx, vlmRun(["shot_main", "shot_scene"], []));
  const missing = await evaluateDeliveryGate(gateInputs(fx, null));
  expect(missing.ready_to_export === false, "没有整套报告必须阻断");
  expect(severityOf(missing, "export.suite_review_current") === "BLOCK", "缺整套报告必须 BLOCK");
  const stale = await evaluateDeliveryGate(gateInputs(fx, {
    report: suite.report,
    fingerprints: { selectionFingerprint: suite.fingerprints.selectionFingerprint + "x",
      inputsFingerprint: suite.fingerprints.inputsFingerprint },
  }));
  expect(suiteReviewIsCurrent(suite.report, suite.fingerprints) === true, "同指纹必须判当前");
  expect(stale.ready_to_export === false, "过期整套报告必须阻断");
  expect(severityOf(stale, "export.suite_review_current") === "BLOCK",
    "过期整套报告必须 BLOCK（实际：" + severityOf(stale, "export.suite_review_current") + "）");
  return { missing: severityOf(missing, "export.suite_review_current") };
});

test("D04", "Unknown：未确认 BLOCK；确认后通过且身份稳定（append-only）", async () => {
  const fx = await fixture({ unknownOnMain: true });
  const suite = await currentSuite(fx, vlmRun(["shot_main", "shot_scene"], []));
  const blocked = await evaluateDeliveryGate(gateInputs(fx, suite));
  expect(blocked.ready_to_export === false, "未确认 Unknown 必须阻断");
  expect(severityOf(blocked, "export.unknown_acknowledged") === "BLOCK",
    "未确认 Unknown 必须 BLOCK");
  expect(blocked.unresolved_unknowns.length === 1, "必须只有一条待确认 Unknown");
  const unknown = blocked.unresolved_unknowns[0];
  expect(unknown.rule_id === "vlm.inspection_unavailable", "Unknown 必须来自单图报告");
  const record = buildAcknowledgement({ unknown: unknown, at: AT });
  const documentId = acknowledgementDocumentIdOf(record);
  expect(documentId === acknowledgementDocumentIdOf(buildAcknowledgement({ unknown: unknown, at: AT })),
    "同一未知项的确认身份必须稳定");
  const resolved = resolveUnknowns(blocked.unknowns, [record]);
  expect(resolved[0].acknowledged === true, "确认后必须标记 acknowledged");
  const passed = await evaluateDeliveryGate(gateInputs(fx, suite, { acknowledgements: [record] }));
  expect(passed.ready_to_export === true, "确认后门禁必须通过");
  expect(severityOf(passed, "export.unknown_acknowledged") === "PASS", "确认后规则必须 PASS");
  return { document_id: documentId, unknowns: blocked.unknowns.length };
});

test("D05", "反向：字节哈希不符 → asset_hash_matches BLOCK", async () => {
  const fx = await fixture();
  const suite = await currentSuite(fx, vlmRun(["shot_main", "shot_scene"], []));
  const gate = await evaluateDeliveryGate(gateInputs(fx, suite, {
    readBytes: async () => new Uint8Array([1, 2, 3, 4]),
  }));
  expect(gate.ready_to_export === false, "哈希不符必须阻断");
  expect(severityOf(gate, "export.asset_hash_matches") === "BLOCK", "哈希不符必须 BLOCK");
  return { detail: gate.findings.find((item) => item.rule_id === "export.asset_hash_matches").detail };
});

test("D06", "交付包往返：条目集合、逐条字节、manifest 反查与记录身份一致", async () => {
  const fx = await fixture();
  const suite = await currentSuite(fx, vlmRun(["shot_main", "shot_scene"], []));
  const gate = await evaluateDeliveryGate(gateInputs(fx, suite));
  const images = [
    { shot_id: "shot_main", candidate_id: "cand_main", media_type: "image/png", bytes: fx.bytes },
    { shot_id: "shot_scene", candidate_id: "cand_scene", media_type: "image/png", bytes: fx.bytes },
  ];
  const manifest = { schema_version: 1, contract_version: EXPORT_GATE_CONTRACT_VERSION,
    images: images.map((item) => ({ shot_id: item.shot_id, candidate_id: item.candidate_id,
      asset_sha256: fx.sha,
      file: deliveryImagePathOf({ shotId: item.shot_id, candidateId: item.candidate_id,
        mediaType: item.media_type }) })) };
  const checks = { schema_version: 1, contract_version: EXPORT_GATE_CONTRACT_VERSION,
    gate_status: gate.status };
  const entries = buildDeliveryEntries({ images: images, manifest: manifest, checks: checks,
    readme: "契约测试交付包" });
  const bytes = buildZip(entries, { modifiedAt: new Date(AT) });
  const roundTrip = await readZip(bytes);
  const paths = roundTrip.map((item) => item.path).sort();
  const expected = images.map((item) => deliveryImagePathOf({ shotId: item.shot_id,
    candidateId: item.candidate_id, mediaType: item.media_type }))
    .concat(["manifest.json", "checks.json", "README.txt"]).sort();
  expect(paths.join("|") === expected.join("|"), "条目集合必须与契约一致：" + paths.join("|"));
  for (const item of roundTrip) {
    const source = entries.find((entry) => entry.path === item.path);
    expect(!!source, "往返条目必须有来源：" + item.path);
    expect(item.bytes.length === source.bytes.length
      && item.bytes.every((value, index) => value === source.bytes[index]),
      "条目字节必须逐字节一致：" + item.path);
    expect(crc32(item.bytes) === crc32(source.bytes), "CRC32 必须一致：" + item.path);
  }
  const parsed = JSON.parse(new TextDecoder().decode(
    roundTrip.find((item) => item.path === "manifest.json").bytes));
  expect(paths.indexOf(parsed.images[0].file) >= 0 && paths.indexOf(parsed.images[1].file) >= 0,
    "manifest 必须能反查到图片条目");
  expect(roundTrip.length === expected.length, "往返条目数必须一致");
  const zipSha = await sha256Hex(bytes);
  const recordId = exportRecordDocumentIdOf({ at: AT, zipSha256: zipSha });
  expect(recordId === exportRecordDocumentIdOf({ at: AT, zipSha256: zipSha }), "记录身份必须稳定");
  expect(recordId !== exportRecordDocumentIdOf({ at: AT, zipSha256: fx.sha }),
    "不同包哈希必须得到不同记录身份");
  const record = buildExportRecord({ projectId: "proj-1", projectName: "契约测试",
    zipSha256: zipSha, zipBytes: bytes.length, entries: entries, gate: gate,
    selectionFingerprint: suite.fingerprints.selectionFingerprint,
    inputsFingerprint: suite.fingerprints.inputsFingerprint,
    includedShotIds: images.map((item) => item.shot_id), at: AT });
  expect(record.files.length === entries.length, "导出记录必须登记每个条目");
  expect(record.files.every((item, index) => item.byte_size === entries[index].bytes.length),
    "导出记录的字节数必须与条目一致");
  expect(deliveryFileName({ projectName: "契约测试", at: AT }).endsWith(".zip"), "交付包文件名必须可下载");
  return { entries: paths.length, zip_bytes: bytes.length, document_id: recordId };
});

async function runSuite() {
  const results = {
    suite: "v2.6.2-delivery", status: "passed", cases: [],
    started_at: new Date().toISOString(), finished_at: null,
  };
  for (const item of cases) {
    const startedAt = performance.now();
    try {
      const detail = await item.run();
      results.cases.push({ id: item.id, title: item.title, status: "passed",
        detail: detail === undefined ? null : detail,
        duration_ms: Math.round(performance.now() - startedAt) });
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
  window.__V2_DELIVERY_RESULTS__ = results;
  render(results);
}).catch((error) => {
  window.__V2_DELIVERY_RESULTS__ = {
    suite: "v2.6.2-delivery", status: "crashed", error: serializeError(error), cases: [],
  };
  render(window.__V2_DELIVERY_RESULTS__);
});
