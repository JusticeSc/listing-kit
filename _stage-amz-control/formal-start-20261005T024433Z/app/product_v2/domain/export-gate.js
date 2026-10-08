/**
 * V2.6.2 交付门禁与交付包内容（唯一权威）。
 *
 * 只消费既有测量：review.js 的 evaluateExportReadiness / verifyAssetHashes（PNG 与哈希）、
 * suite-review.js 的 checkSuiteReviewReport / suiteReviewIsCurrent（整套报告）、
 * registeredRule（严重度）。这里不重做第二套测量，也不自己算 sha256（由调用方注入 digest）。
 *
 * Unknown 确认是 append-only 文档 review_acknowledgement 的语义：只记录「已知悉」，
 * 不改写发现、不自动选择、不删除报告。导出记录 export_record 由调用方写库（本模块只产出形状）。
 */

import { registeredRule } from "./review.js";
import { evaluateExportReadiness, verifyAssetHashes } from "./review.js";
import { checkSuiteReviewReport, suiteReviewIsCurrent } from "./suite-review.js";
import { isNonEmptyString, isPlainObject, isSha256Hex } from "./shared.js";
import { DOMAIN_ERROR_CODES, invalid } from "./errors.js";

export const EXPORT_GATE_CONTRACT_VERSION = "v2.6.2";
export const EXPORT_RECORD_KIND = "export_record";
export const REVIEW_ACKNOWLEDGEMENT_KIND = "review_acknowledgement";
export const DELIVERY_ENTRY_NAMES = Object.freeze({
  manifest: "manifest.json",
  checks: "checks.json",
  readme: "README.txt",
});

function finding(ruleId, message, affectedShotIds, measured, severity) {
  const entry = registeredRule(ruleId);
  if (!entry) invalid("交付门禁引用了未登记的规则：" + String(ruleId));
  return Object.freeze({
    rule_id: entry.rule_id,
    rule_version: entry.version,
    severity: severity || entry.severity,
    title: entry.title,
    detail: message,
    measured: measured === undefined ? null : measured,
    affected_shot_ids: Object.freeze([...(affectedShotIds || [])]),
  });
}

/**
 * 把既有测量（review.js 的 makeFinding 不带归属）投影出受影响 Shot：只做只读解释，
 * 不重算测量本身；认不出归属时返回空数组，宁可少指也不乱指。
 */
function affectedShotsOf(item, knownShotIds) {
  const measured = isPlainObject(item.measured) ? item.measured : {};
  const values = [];
  ["missing", "shots", "issues", "mismatches"].forEach((key) => {
    if (Array.isArray(measured[key])) values.push(...measured[key]);
  });
  const found = new Set();
  values.forEach((value) => {
    const text = String(value);
    for (const shotId of knownShotIds) {
      if (text === shotId || text.indexOf(shotId + "：") === 0 || text.indexOf(shotId + ":") === 0) {
        found.add(shotId);
        break;
      }
    }
  });
  return [...found];
}

/** 未知项身份：单图 = 报告 + 规则；整套 = 报告 + 规则 + Shot 集合。同一身份只允许一条确认。 */
export function unknownIdentityOf(unknown) {
  if (!isPlainObject(unknown)) return null;
  const kind = unknown.target_kind === "suite_review" ? "suite_review" : "review_report";
  const targetId = isNonEmptyString(unknown.target_id) ? unknown.target_id : null;
  const ruleId = isNonEmptyString(unknown.rule_id) ? unknown.rule_id : null;
  if (!targetId || !ruleId) return null;
  const shotIds = Array.isArray(unknown.shot_ids) ? [...unknown.shot_ids].sort() : [];
  return kind + "|" + targetId + "|" + ruleId + "|" + shotIds.join(",");
}

/** 从当前单图报告与整套报告里收集全部 UNKNOWN（唯一来源：报告里的发现本身）。 */
export function collectUnknowns({ shots = [], selections = {}, reportsByCandidate = {},
                                  candidatesByShot = {}, suiteReport = null } = {}) {
  const unknowns = [];
  shots.forEach((shot) => {
    if (!isPlainObject(shot) || !isNonEmptyString(shot.shot_id)) return;
    const candidateId = selections[shot.shot_id];
    if (!isNonEmptyString(candidateId)) return;
    const chain = Array.isArray(candidatesByShot[shot.shot_id]) ? candidatesByShot[shot.shot_id] : [];
    const candidate = chain.map((item) => (isPlainObject(item) && isPlainObject(item.record))
      ? item.record : item).find((item) => isPlainObject(item)
      && item.candidate_id === candidateId) || null;
    const report = isPlainObject(reportsByCandidate[candidateId])
      && isPlainObject(reportsByCandidate[candidateId].report)
      ? reportsByCandidate[candidateId].report : reportsByCandidate[candidateId];
    if (!candidate || !isPlainObject(report)) return;
    (Array.isArray(report.findings) ? report.findings : []).forEach((item) => {
      if (!isPlainObject(item) || item.severity !== "UNKNOWN") return;
      unknowns.push({
        target_kind: "review_report",
        target_id: candidateId,
        rule_id: item.rule_id,
        shot_ids: [shot.shot_id],
        title: item.title,
        detail: item.detail,
        asset_sha256: candidate.asset_sha256,
      });
    });
  });
  if (isPlainObject(suiteReport)) {
    (Array.isArray(suiteReport.findings) ? suiteReport.findings : []).forEach((item) => {
      if (!isPlainObject(item) || item.severity !== "UNKNOWN") return;
      unknowns.push({
        target_kind: "suite_review",
        target_id: "suite_review",
        rule_id: item.rule_id,
        shot_ids: Array.isArray(item.affected_shot_ids) ? [...item.affected_shot_ids] : [],
        title: item.title,
        detail: item.detail,
        asset_sha256: null,
      });
    });
  }
  return unknowns;
}

/** 已确认的未知项：acknowledgements 里能对上身份（kind/target/rule/shot 集合）的条目。 */
export function resolveUnknowns(unknowns, acknowledgements = []) {
  const acknowledged = new Set();
  (Array.isArray(acknowledgements) ? acknowledgements : []).forEach((record) => {
    const payload = isPlainObject(record) && isPlainObject(record.payload) ? record.payload : record;
    const identity = unknownIdentityOf(payload);
    if (identity) acknowledged.add(identity);
  });
  return unknowns.map((item) => Object.freeze({
    ...item,
    identity: unknownIdentityOf(item),
    acknowledged: acknowledged.has(unknownIdentityOf(item)),
  }));
}

/** 人工确认记录（append-only）：document_id = 身份摘要，写库由调用方完成。 */
export function buildAcknowledgement({ unknown, at, actor = "user" } = {}) {
  const identity = unknownIdentityOf(unknown);
  if (!identity) invalid("确认记录需要有效的未知项身份（target/rule）。");
  if (!isNonEmptyString(at)) invalid("确认记录需要 ISO 时间（at）。");
  const shotIds = Array.isArray(unknown.shot_ids) ? [...unknown.shot_ids].sort() : [];
  return Object.freeze({
    schema_version: 1,
    contract_version: EXPORT_GATE_CONTRACT_VERSION,
    target_kind: unknown.target_kind === "suite_review" ? "suite_review" : "review_report",
    target_id: unknown.target_id,
    rule_id: unknown.rule_id,
    shot_ids: Object.freeze(shotIds),
    acknowledged_at: at,
    actor: actor,
    note: "已知悉：不改写发现、不自动选择、不删除报告。",
  });
}

export function acknowledgementDocumentIdOf(acknowledgement) {
  const identity = unknownIdentityOf(acknowledgement);
  if (!identity) invalid("确认记录缺少身份，无法生成 document_id。");
  return "ack-" + identity.replace(/[^A-Za-z0-9_-]+/g, "-").slice(0, 80);
}

/**
 * 交付门禁：复用导出就绪、字节哈希、整套报告与 Unknown 确认四类既有测量。
 * 返回 {status, ready_to_export, findings, blocking, unknowns, unresolved_unknowns}。
 */
export async function evaluateDeliveryGate({ shots, selections, candidatesByShot,
                                             reportsByCandidate, attemptsByShot,
                                             readBytes, digest,
                                             suiteReport = null, suiteFingerprints = null,
                                             acknowledgements = [] } = {}) {
  if (!Array.isArray(shots)) invalid("交付门禁需要 shots 列表。");
  if (typeof readBytes !== "function" || typeof digest !== "function") {
    invalid("交付门禁需要注入 readBytes 与 digest（不写第二种散列）。");
  }
  const readiness = evaluateExportReadiness({
    shots: shots, selections: selections, candidatesByShot: candidatesByShot,
    reportsByCandidate: reportsByCandidate, attemptsByShot: attemptsByShot,
  });
  const hashCheck = await verifyAssetHashes({
    selections: selections, candidatesByShot: candidatesByShot,
    readBytes: readBytes, digest: digest,
  });
  const knownShotIds = shots
    .filter((shot) => isPlainObject(shot) && isNonEmptyString(shot.shot_id))
    .map((shot) => shot.shot_id);
  const findings = [...readiness.findings, ...hashCheck.findings].map((item) => Object.freeze({
    ...item, affected_shot_ids: Object.freeze(affectedShotsOf(item, knownShotIds)),
  }));

  if (!isPlainObject(suiteReport)) {
    findings.push(finding("export.suite_review_current", "还没有整套一致性报告；先运行整套检查。", []));
  } else {
    const shapeProblems = checkSuiteReviewReport(suiteReport);
    const current = suiteFingerprints
      ? suiteReviewIsCurrent(suiteReport, suiteFingerprints) : false;
    if (shapeProblems.length || !current) {
      findings.push(finding("export.suite_review_current",
        shapeProblems.length ? "整套一致性报告结构不合法，必须重跑。"
          : "整套一致性报告已过期（选择或输入已变化），必须重跑。", []));
    } else {
      const blocking = (suiteReport.findings || [])
        .filter((item) => isPlainObject(item) && item.severity === "BLOCK");
      if (blocking.length) {
        findings.push(finding("export.suite_review_current",
          "整套一致性报告仍有 " + blocking.length + " 条阻断项。",
          blocking.flatMap((item) => Array.isArray(item.affected_shot_ids)
            ? item.affected_shot_ids : [])));
      } else {
        findings.push(finding("export.suite_review_current",
          "整套一致性报告对当前选择有效。", [], null, "PASS"));
      }
    }
  }

  const unknowns = resolveUnknowns(collectUnknowns({
    shots: shots, selections: selections, reportsByCandidate: reportsByCandidate,
    candidatesByShot: candidatesByShot, suiteReport: suiteReport,
  }), acknowledgements);
  const unresolved = unknowns.filter((item) => item.acknowledged !== true);
  if (unresolved.length) {
    findings.push(finding("export.unknown_acknowledged",
      "还有 " + unresolved.length + " 条 Unknown 没有人工确认；确认后才允许交付。",
      unresolved.flatMap((item) => item.shot_ids)));
  } else {
    findings.push(finding("export.unknown_acknowledged",
      "全部 Unknown 已人工确认（或没有 Unknown）。", [], null, "PASS"));
  }

  const normalized = findings.map((item) => Object.freeze({
    ...item,
    severity: item.severity === "PASS" ? "PASS" : (item.severity || "UNKNOWN"),
  }));
  const blocking = normalized.filter((item) => item.severity === "BLOCK");
  return Object.freeze({
    contract_version: EXPORT_GATE_CONTRACT_VERSION,
    status: blocking.length ? "blocked" : "ready",
    ready_to_export: blocking.length === 0,
    findings: Object.freeze(normalized),
    blocking: Object.freeze(blocking),
    unknowns: Object.freeze(unknowns),
    unresolved_unknowns: Object.freeze(unresolved),
  });
}

/** 交付包条目：images/<shot>-<candidate>.<ext> + manifest.json + checks.json + README.txt。 */
export function deliveryImagePathOf({ shotId, candidateId, mediaType } = {}) {
  if (!isNonEmptyString(shotId) || !isNonEmptyString(candidateId)) {
    invalid("交付包图片路径需要 shot_id 与 candidate_id。");
  }
  const ext = mediaType === "image/jpeg" ? "jpg" : "png";
  return "images/" + String(shotId).replace(/[^A-Za-z0-9_-]+/g, "-")
    + "-" + String(candidateId).replace(/[^A-Za-z0-9_-]+/g, "-") + "." + ext;
}

export function buildDeliveryEntries({ images = [], manifest, checks, readme } = {}) {
  if (!Array.isArray(images)) invalid("交付包需要 images 列表。");
  if (!isPlainObject(manifest) || !isPlainObject(checks) || !isNonEmptyString(readme)) {
    invalid("交付包需要 manifest、checks 与 README。");
  }
  const entries = [];
  const seen = new Set();
  images.forEach((item) => {
    if (!isPlainObject(item) || !isNonEmptyString(item.shot_id)
        || !isNonEmptyString(item.candidate_id) || !(item.bytes instanceof Uint8Array)) {
      invalid("交付包图片条目需要 shot_id、candidate_id 与 bytes。");
    }
    const path = deliveryImagePathOf({
      shotId: item.shot_id, candidateId: item.candidate_id, mediaType: item.media_type,
    });
    if (seen.has(path)) invalid("交付包路径重复：" + path);
    seen.add(path);
    entries.push({ path: path, bytes: item.bytes });
  });
  const encoder = new TextEncoder();
  entries.push({ path: DELIVERY_ENTRY_NAMES.manifest,
                 bytes: encoder.encode(JSON.stringify(manifest, null, 2)) });
  entries.push({ path: DELIVERY_ENTRY_NAMES.checks,
                 bytes: encoder.encode(JSON.stringify(checks, null, 2)) });
  entries.push({ path: DELIVERY_ENTRY_NAMES.readme, bytes: encoder.encode(readme) });
  return Object.freeze(entries.map((item) => Object.freeze({
    path: item.path, bytes: item.bytes,
  })));
}

/** 导出记录（append-only）：包身份 + 内容清单 + 生成时间；不覆盖历史。 */
export function buildExportRecord({ projectId, projectName, zipSha256, zipBytes, entries,
                                    gate, selectionFingerprint, inputsFingerprint,
                                    includedShotIds, at } = {}) {
  if (!isNonEmptyString(projectId) || !isNonEmptyString(projectName)) {
    invalid("导出记录需要项目身份。");
  }
  if (!isSha256Hex(zipSha256)) invalid("导出记录需要交付包 sha256。");
  if (!Number.isInteger(zipBytes) || zipBytes < 1) invalid("导出记录需要字节数。");
  if (!isNonEmptyString(at)) invalid("导出记录需要 ISO 时间（at）。");
  const files = (Array.isArray(entries) ? entries : []).map((item) => ({
    path: item.path, byte_size: item.bytes.length,
  }));
  return Object.freeze({
    schema_version: 1,
    contract_version: EXPORT_GATE_CONTRACT_VERSION,
    project_id: projectId,
    project_name: projectName,
    zip_sha256: zipSha256,
    zip_bytes: zipBytes,
    files: Object.freeze(files.map((item) => Object.freeze(item))),
    included_shot_ids: Object.freeze([...(includedShotIds || [])]),
    selection_fingerprint: selectionFingerprint || null,
    inputs_fingerprint: inputsFingerprint || null,
    gate: Object.freeze({
      status: gate && gate.status ? gate.status : "ready",
      findings: Object.freeze((gate && Array.isArray(gate.findings) ? gate.findings : [])
        .map((item) => Object.freeze({ rule_id: item.rule_id, severity: item.severity }))),
    }),
    exported_at: at,
  });
}

/**
 * 导出记录 document_id：时间戳 + 包 sha256 前 12 位；每次生成都是新 document_id，
 * 因此 listLatest(export_record) 天然是「只追加、不覆盖」的历史。
 */
export function exportRecordDocumentIdOf({ at, zipSha256 } = {}) {
  if (!isNonEmptyString(at) || !isSha256Hex(zipSha256)) {
    invalid("导出记录身份需要 at 与包 sha256。");
  }
  // 毫秒精度（YYYYMMDDHHMMSSmmm）：同一秒内多次生成也能按 document_id 排出时间顺序。
  const stamp = String(at).replace(/[-:.TZ]/g, "").slice(0, 17);
  return "export-" + stamp + "-" + String(zipSha256).slice(0, 12);
}

/** 交付包文件名：项目名 + 时间戳；调用方用于下载与展示。 */
export function deliveryFileName({ projectName, at } = {}) {
  const safe = String(projectName || "project").replace(/[\\/:*?"<>|\s]+/g, "-")
    .replace(/^-+|-+$/g, "").slice(0, 60) || "project";
  const stamp = String(at || new Date().toISOString()).replace(/[-:]/g, "").replace("T", "-")
    .slice(0, 13);
  return safe + "-交付包-" + stamp + ".zip";
}

export const EXPORT_GATE_ERROR_CODES = DOMAIN_ERROR_CODES;
