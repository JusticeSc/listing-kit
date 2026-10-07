/**
 * V2.5.5 整套一致性报告（计划 §9.20，唯一权威）。
 *
 * 输入是当前 SelectionSet、已选候选（含本地字节）、已确认依据 context、套图计划、公共风格、
 * 单图规格与所选候选的当前 ReviewReport 身份，以及一次整套视觉复核的运行记录。输出是同时绑定
 * selection_fingerprint 与 inputs_fingerprint 的 SuiteReviewReport：任一输入变化都会让它过期并可重算。
 *
 * 分工（不可越界）：
 *  - 确定性发现：suite.* 规则（必需选择、依据依赖、重复、推荐遗漏、卖点覆盖）由本文件组装；
 *    导出就绪与字节哈希一律复用 review.js 的 evaluateExportReadiness / verifyAssetHashes，不写第二套；
 *  - 视觉发现：VLM 只产生提示或 UNKNOWN，不能取消人工选择、不能升级为 BLOCK、不能替代人工采纳；
 *  - 本层是纯函数（除注入的 readBytes / digest 之外不碰存储、不发请求）；sha256 一律用注入的 digest。
 */

import { DOMAIN_ERROR_CODES, invalid } from "./errors.js";
import {
  DOMAIN_DOCUMENT_KINDS, checkSchemaVersion, isIsoTimestamp, isNonEmptyString,
  isPlainObject, isSha256Hex, pushProblem,
} from "./shared.js";
import { recommendPlan } from "./suite-plan.js";
import { suitePlanSummary } from "./suite.js";
import {
  REVIEW_SEVERITIES, evaluateExportReadiness, makeFinding, registeredRule, verifyAssetHashes,
} from "./review.js";
import { SELECTION_STATE_TEXT } from "./selection.js";

export const SUITE_REVIEW_SCHEMA_VERSION = 1;
export const SUITE_REVIEW_CONTRACT_VERSION = "v2.5.5";
export const SUITE_REVIEW_DOCUMENT_KIND = DOMAIN_DOCUMENT_KINDS.suite_review;
export const SUITE_REVIEW_DOCUMENT_ID = "suite_review";
export const SUITE_MAX_IMAGES = 8;
export const SUITE_VLM_MAX_FINDINGS = 12;
export const SUITE_VLM_MAX_EVIDENCE_LENGTH = 300;

/**
 * 整套 VLM check 词表：与服务端 src/providers/v2_suite_review.py 的 SUITE_VLM_CHECKS 键集合
 * 互为镜像（由 tools/verify_v2_5_5_suite_review.py 比对）；rule_id 与严重度的唯一权威仍是 review.js。
 */
export const SUITE_VLM_CHECK_TO_RULE = Object.freeze({
  suite_product_consistency: "vlm.suite_product_consistency",
  suite_color_material_consistency: "vlm.suite_color_material_consistency",
  suite_cross_image_anomaly: "vlm.suite_cross_image_anomaly",
  suite_style_consistency: "vlm.suite_style_consistency",
});

/** 视觉层未执行/未完成的分类原因（消费者只投影原因码，不在这里写界面文案）。 */
export const SUITE_VLM_REASONS = Object.freeze([
  "not_run", "no_selection", "over_limit", "missing_bytes", "image_too_large",
  "transport", "server", "protocol",
]);

/* ------------------------------------------------------------------ 规范化与指纹 */

function canonicalValue(value) {
  if (Array.isArray(value)) return value.map((item) => canonicalValue(item));
  if (isPlainObject(value)) {
    const out = {};
    Object.keys(value).sort().forEach((key) => {
      const item = value[key];
      if (item === undefined) return;
      out[key] = canonicalValue(item);
    });
    return out;
  }
  if (value === undefined) return null;
  return value;
}

/** 规范化载荷：键序稳定、去掉 undefined，用于指纹与证据复算（不依赖对象插入顺序）。 */
export function canonicalSuitePayload(value) {
  return JSON.stringify(canonicalValue(value));
}

function stringList(value) {
  return Array.isArray(value) ? value.filter((item) => isNonEmptyString(item)) : [];
}

function textOf(value) {
  if (value === undefined || value === null) return "";
  if (Array.isArray(value)) return value.join("；");
  return String(value);
}

function normalizeText(value) {
  return textOf(value).replace(/\s+/g, "").toLowerCase();
}

function withAffected(finding, shotIds) {
  return Object.freeze({
    ...finding,
    affected_shot_ids: Object.freeze(stringList(shotIds)),
  });
}

/**
 * SelectionSet 规范化快照：只取身份与状态字段，不含生成时间（时间不改变「选择是什么」）。
 */
export function selectionFingerprintOf(selectionSet) {
  if (!isPlainObject(selectionSet) || !Array.isArray(selectionSet.entries)) {
    invalid("整套指纹需要 SelectionSet（entries 数组）。");
  }
  return canonicalSuitePayload({
    contract_version: isNonEmptyString(selectionSet.contract_version)
      ? selectionSet.contract_version : null,
    entries: selectionSet.entries.map((entry) => ({
      shot_id: entry && entry.shot_id ? entry.shot_id : null,
      required: Boolean(entry && entry.required === true),
      state: entry && entry.state ? entry.state : null,
      selection_id: entry && entry.selection_id ? entry.selection_id : null,
      candidate_id: entry && entry.candidate_id ? entry.candidate_id : null,
      candidate_sha256: entry && entry.candidate_sha256 ? entry.candidate_sha256 : null,
      candidate_version: entry && Number.isInteger(entry.candidate_version)
        ? entry.candidate_version : null,
      selected_at: entry && entry.selected_at ? entry.selected_at : null,
    })),
  });
}

function specPayloadOf(entry) {
  if (!isPlainObject(entry)) return {};
  return isPlainObject(entry.spec) ? entry.spec : entry;
}

function reportPayloadOf(entry) {
  if (!isPlainObject(entry)) return {};
  return isPlainObject(entry.report) ? entry.report : entry;
}

/**
 * 输入指纹：在选择指纹之外纳入 计划、公共风格、单图规格、所选报告身份。
 * reportsByCandidate 传「当前选中所指候选的当前报告」（键是 candidate_id）。
 */
export function inputsFingerprintOf({ selectionFingerprint = "", suitePlan = null,
                                      styleSpec = null, shotSpecsById = {},
                                      reportsByCandidate = {} } = {}) {
  const planShots = (suitePlan && Array.isArray(suitePlan.shots) ? suitePlan.shots : [])
    .filter((shot) => isPlainObject(shot))
    .map((shot) => ({
      shot_id: shot.shot_id === undefined ? null : shot.shot_id,
      template_id: shot.template_id === undefined ? null : shot.template_id,
      role_id: shot.role_id === undefined ? null : shot.role_id,
      label: shot.label === undefined ? null : shot.label,
      required: shot.required === true,
      custom: shot.custom === true,
      fact_slot_ids: Array.isArray(shot.fact_slot_ids) ? [...shot.fact_slot_ids] : [],
    }))
    .sort((left, right) => String(left.shot_id).localeCompare(String(right.shot_id)));
  const specs = Object.keys(shotSpecsById || {}).sort().map((shotId) => {
    const spec = specPayloadOf((shotSpecsById || {})[shotId]);
    return {
      shot_id: shotId,
      purpose: spec.purpose === undefined ? null : spec.purpose,
      keep: Array.isArray(spec.keep) ? [...spec.keep] : [],
      change_allowed: Array.isArray(spec.change_allowed) ? [...spec.change_allowed] : [],
    };
  });
  const style = isPlainObject(styleSpec) ? {
    background: styleSpec.background === undefined ? null : styleSpec.background,
    lighting: styleSpec.lighting === undefined ? null : styleSpec.lighting,
    color_tone: styleSpec.color_tone === undefined ? null : styleSpec.color_tone,
    composition: styleSpec.composition === undefined ? null : styleSpec.composition,
    avoid: Array.isArray(styleSpec.avoid) ? [...styleSpec.avoid] : [],
  } : null;
  const reports = Object.keys(reportsByCandidate || {}).sort().map((candidateId) => {
    const report = reportPayloadOf((reportsByCandidate || {})[candidateId]);
    return {
      candidate_id: candidateId,
      review_contract_version: report.review_contract_version === undefined
        ? null : report.review_contract_version,
      report_created_at: report.created_at === undefined ? null : report.created_at,
      report_asset_sha256: report.asset_sha256 === undefined ? null : report.asset_sha256,
      report_finding_count: Array.isArray(report.findings) ? report.findings.length : 0,
    };
  });
  return canonicalSuitePayload({
    selection: selectionFingerprint,
    style: style,
    shots: planShots,
    specs: specs,
    reports: reports,
  });
}

/* -------------------------------------------------------------- 确定性发现（suite.*） */

function shotLabelOf(shot) {
  if (!isPlainObject(shot)) return "未命名任务";
  return isNonEmptyString(shot.label) ? shot.label : String(shot.shot_id);
}

function duplicateKeyOf(shot) {
  if (!isPlainObject(shot)) return null;
  const facts = Array.isArray(shot.fact_slot_ids) ? [...shot.fact_slot_ids].sort() : [];
  const base = isNonEmptyString(shot.template_id)
    ? "template:" + shot.template_id
    : (isNonEmptyString(shot.label) ? "custom:" + normalizeText(shot.label) : null);
  if (base === null) return null;
  return base + "|" + facts.join(",");
}

function sellingPointCovered(point, suitePlan, factsById) {
  const needle = normalizeText(point);
  if (!needle) return true;
  const shots = suitePlan && Array.isArray(suitePlan.shots) ? suitePlan.shots : [];
  for (const shot of shots) {
    if (!isPlainObject(shot)) continue;
    const slotIds = Array.isArray(shot.fact_slot_ids) ? shot.fact_slot_ids : [];
    for (const slotId of slotIds) {
      const entry = factsById ? factsById[slotId] : null;
      const slot = isPlainObject(entry) && isPlainObject(entry.slot) ? entry.slot : entry;
      if (!isPlainObject(slot) || slot.status !== "confirmed") continue;
      if (normalizeText(slot.value).indexOf(needle) >= 0) return true;
    }
  }
  return false;
}

/**
 * 五个 suite.* 确定性检查：每条发现都带 affected_shot_ids（PASS 为空数组，问题带可定位的 Shot）。
 */
export function evaluateSuiteFindings({ suitePlan, selectionSet, context = {},
                                        factsById = {}, sellingPoints = [] } = {}) {
  if (!isPlainObject(suitePlan) || !Array.isArray(suitePlan.shots)) {
    invalid("整套检查需要套图计划（shots 数组）。");
  }
  if (!isPlainObject(selectionSet) || !Array.isArray(selectionSet.entries)) {
    invalid("整套检查需要 SelectionSet。");
  }
  const facts = isPlainObject(context) && Array.isArray(context.facts) ? context.facts : [];
  const assets = isPlainObject(context) && Array.isArray(context.assets) ? context.assets : [];
  const summary = suitePlanSummary(suitePlan, { facts: facts, assets: assets });
  const recommendation = recommendPlan({ facts: facts, assets: assets });
  const findings = [];

  const requiredEntries = selectionSet.entries
    .filter((entry) => isPlainObject(entry) && entry.required === true);
  const notCurrent = requiredEntries.filter((entry) => entry.state !== "current");
  if (notCurrent.length > 0) {
    const detail = notCurrent.map((entry) => {
      const label = shotLabelOf((suitePlan.shots || [])
        .find((shot) => isPlainObject(shot) && shot.shot_id === entry.shot_id));
      const stateText = SELECTION_STATE_TEXT[entry.state] || String(entry.state);
      return "「" + label + "」" + stateText;
    }).join("；");
    findings.push(withAffected(makeFinding("suite.selection_current", "BLOCK",
      "以下必需图没有当前有效的人工采用：" + detail + "；先采用或重新采用候选，再重算整套检查。",
      { shots: notCurrent.map((entry) => entry.shot_id), required_total: requiredEntries.length }),
      notCurrent.map((entry) => entry.shot_id)));
  } else {
    findings.push(withAffected(makeFinding("suite.selection_current", "PASS",
      "必需图的人工采用全部当前有效（" + requiredEntries.length + " 张）。",
      { required_total: requiredEntries.length }), []));
  }

  const blockedShots = summary.shots.filter((shot) => shot && shot.satisfied !== true);
  if (blockedShots.length > 0) {
    const detail = blockedShots.map((shot) => "「" + shotLabelOf(shot) + "」缺依据："
      + (Array.isArray(shot.blocking) ? shot.blocking : [])
        .map((item) => (item && (item.reason || item.message)) || "未知原因").join("；")).join("；");
    findings.push(withAffected(makeFinding("suite.dependency_satisfied", "BLOCK",
      "以下图任务的生成依据未满足：" + detail + "。",
      { shots: blockedShots.map((shot) => shot.shot_id) }),
      blockedShots.map((shot) => shot.shot_id)));
  } else {
    findings.push(withAffected(makeFinding("suite.dependency_satisfied", "PASS",
      "套图 " + summary.total + " 张的生成依据都已满足。", { total: summary.total }), []));
  }

  const groups = new Map();
  (suitePlan.shots || []).forEach((shot) => {
    const key = duplicateKeyOf(shot);
    if (!key) return;
    const list = groups.get(key) || [];
    list.push(shot);
    groups.set(key, list);
  });
  const duplicateGroups = [...groups.values()].filter((list) => list.length >= 2);
  if (duplicateGroups.length > 0) {
    const detail = duplicateGroups.map((list) => "「" + shotLabelOf(list[0]) + "」×" + list.length
      + "（" + list.map((shot) => shot.shot_id).join("、") + "）").join("；");
    findings.push(withAffected(makeFinding("suite.duplicates", "WARNING",
      "以下任务重复（同类模板且绑定依据集合相同）：" + detail
      + "；如果确认不是有意重复，可删减或让每张图绑定不同依据。",
      { groups: duplicateGroups.map((list) => list.map((shot) => shot.shot_id)) }),
      duplicateGroups.flatMap((list) => list.map((shot) => shot.shot_id))));
  } else {
    findings.push(withAffected(makeFinding("suite.duplicates", "PASS",
      "未发现重复任务（同类模板且绑定依据集合相同）。", { total: summary.total }), []));
  }

  const planTemplateIds = new Set((suitePlan.shots || [])
    .filter((shot) => isPlainObject(shot) && isNonEmptyString(shot.template_id))
    .map((shot) => shot.template_id));
  const omitted = recommendation.instances.filter((item) => item && item.satisfied === true
    && item.required !== true && !planTemplateIds.has(item.template_id));
  if (omitted.length > 0) {
    findings.push(withAffected(makeFinding("suite.recommended_omissions", "WARNING",
      "以下推荐图当前依据已满足，但没有纳入套图：" + omitted.map((item) => item.label).join("、")
      + "；有意省略可以忽略，需要时在套图方案里加入。",
      { templates: omitted.map((item) => item.template_id) }), []));
  } else {
    findings.push(withAffected(makeFinding("suite.recommended_omissions", "PASS",
      "依据可满足的推荐图都已纳入当前套图（或有依据缺口）。", { total: summary.total }), []));
  }

  const points = (Array.isArray(sellingPoints) ? sellingPoints : [])
    .map((item) => String(item === undefined || item === null ? "" : item).trim())
    .filter((item) => item.length > 0);
  if (points.length === 0) {
    findings.push(withAffected(makeFinding("suite.selling_point_coverage", "PASS",
      "没有填写卖点，无需检查覆盖。", { points: 0 }), []));
  } else {
    const uncovered = points.filter((point) => !sellingPointCovered(point, suitePlan, factsById));
    if (uncovered.length > 0) {
      findings.push(withAffected(makeFinding("suite.selling_point_coverage", "WARNING",
        "以下卖点在已确认依据里找不到落点：" + uncovered.map((item) => "「" + item + "」").join("、")
        + "；把卖点绑定到某张图的依据，或确认该卖点无需上镜。",
        { uncovered: uncovered, points: points.length }), []));
    } else {
      findings.push(withAffected(makeFinding("suite.selling_point_coverage", "PASS",
        "全部 " + points.length + " 条卖点都有已确认依据落点。", { points: points.length }), []));
    }
  }

  return Object.freeze({ findings: Object.freeze(findings) });
}

/* ---------------------------------------------------------------- 导出层测量复用 */

function shotIdsFromIssueText(value) {
  const text = String(value === undefined || value === null ? "" : value);
  if (!text) return null;
  const cut = text.search(/[：: ]/);
  const id = cut < 0 ? text : text.slice(0, cut);
  return isNonEmptyString(id) ? id : null;
}

function attributionFor(finding) {
  const measured = isPlainObject(finding && finding.measured) ? finding.measured : {};
  if (finding.rule_id === "export.selection_complete") {
    return stringList(measured.missing);
  }
  if (finding.rule_id === "export.no_blocking_findings") {
    return stringList(measured.shots);
  }
  if (finding.rule_id === "export.chain_integrity"
      || finding.rule_id === "export.report_current"
      || finding.rule_id === "export.asset_hash_matches") {
    const entries = []
      .concat(Array.isArray(measured.issues) ? measured.issues : [])
      .concat(Array.isArray(measured.missing) ? measured.missing : [])
      .concat(Array.isArray(measured.mismatches) ? measured.mismatches : []);
    const ids = entries.map((item) => shotIdsFromIssueText(item)).filter((item) => item !== null);
    return [...new Set(ids)];
  }
  return [];
}

/**
 * 把导出就绪与哈希核对的发现原样并入整套报告，只补 affected_shot_ids 归属（测量不重做）。
 */
export function mergeExportFindings({ readinessFindings = [], hashFindings = [] } = {}) {
  const all = [...(Array.isArray(readinessFindings) ? readinessFindings : []),
    ...(Array.isArray(hashFindings) ? hashFindings : [])];
  return Object.freeze(all.map((finding) => withAffected(finding, attributionFor(finding))));
}

/* -------------------------------------------------------------------- 视觉复核合并 */

function checkedResultOf(result, submitted) {
  if (!isPlainObject(result)) throw new Error("整套复核结果必须是对象。");
  if (result.contract_version !== SUITE_REVIEW_CONTRACT_VERSION) {
    throw new Error("整套复核合同版本不一致：" + String(result.contract_version));
  }
  if (!Array.isArray(result.findings) || result.findings.length > SUITE_VLM_MAX_FINDINGS) {
    throw new Error("整套复核 findings 数量非法。");
  }
  const echoed = stringList(result.submitted_shot_ids);
  if (echoed.length !== submitted.length
      || echoed.some((shotId) => submitted.indexOf(shotId) === -1)) {
    throw new Error("整套复核回显的送审集合与请求不一致。");
  }
  result.findings.forEach((item) => {
    if (!isPlainObject(item)) throw new Error("整套复核发现必须是对象。");
    if (!SUITE_VLM_CHECK_TO_RULE[item.check]) {
      throw new Error("整套复核发现引用了未登记的 check：" + String(item.check));
    }
    const shotIds = stringList(item.shot_ids);
    if (shotIds.length === 0) throw new Error("整套复核发现缺少 shot_ids。");
    shotIds.forEach((shotId) => {
      if (submitted.indexOf(shotId) === -1) {
        throw new Error("整套复核发现引用了未送审的图：" + shotId);
      }
    });
    if (!isNonEmptyString(item.evidence) || item.evidence.length > SUITE_VLM_MAX_EVIDENCE_LENGTH) {
      throw new Error("整套复核证据必须是非空短文本。");
    }
    if (typeof item.confidence !== "number" || !Number.isFinite(item.confidence)
        || item.confidence < 0 || item.confidence > 1) {
      throw new Error("整套复核置信度必须在 0..1 之间。");
    }
  });
  return {
    findings: result.findings,
    provider_id: isNonEmptyString(result.provider_id) ? result.provider_id : null,
    model_id: isNonEmptyString(result.model_id) ? result.model_id : null,
    request_id: isNonEmptyString(result.request_id) ? result.request_id : null,
    checked_at: isIsoTimestamp(result.checked_at) ? result.checked_at : null,
    latency_ms: typeof result.latency_ms === "number" ? result.latency_ms : null,
    summary: isNonEmptyString(result.summary) ? result.summary.slice(0, 500) : "",
  };
}

function unknownReasonText(reason) {
  if (reason === "no_selection") return "当前没有已采用的候选，没有可送审的图片";
  if (reason === "over_limit") {
    return "已选图超过单次上限（最多 " + SUITE_MAX_IMAGES + " 张）";
  }
  if (reason === "missing_bytes") return "有已选图的本地字节缺失或不可读，未把半份资料送审";
  if (reason === "image_too_large") return "有已选图超过单张字节上限，未发起整套复核";
  if (reason === "transport") return "复核服务没有返回可解析的结果（服务可能未启动）";
  if (reason === "server") return "复核服务返回了分类失败";
  if (reason === "protocol") return "复核回应的结构或身份与请求不对应";
  return "尚未运行整套视觉复核";
}

function unknownFindingFor(reason, requested, at, message, error) {
  const detail = "整套视觉复核未完成：" + unknownReasonText(reason)
    + (message ? "（" + message + "）" : "")
    + "；确定性部分不受影响，人工复核继续。";
  const measured = {
    reason: reason,
    at: at,
    requested_shot_ids: [...requested],
    family: error && isNonEmptyString(error.family) ? error.family : null,
    code: error && isNonEmptyString(error.code) ? error.code : null,
    request_id: error && isNonEmptyString(error.request_id) ? error.request_id : null,
  };
  return withAffected(makeFinding("vlm.suite_inspection_unavailable", "UNKNOWN",
    detail, measured), requested);
}

function unknownBlockFor(reason, requested, submitted, shaByShot, at, error, message) {
  return Object.freeze({
    outcome: "unknown",
    contract_version: SUITE_REVIEW_CONTRACT_VERSION,
    requested_shot_ids: Object.freeze([...requested]),
    submitted_shot_ids: Object.freeze([...submitted]),
    asset_sha256_by_shot: Object.freeze({ ...shaByShot }),
    provider_id: null,
    model_id: null,
    request_id: error && isNonEmptyString(error.request_id) ? error.request_id : null,
    checked_at: at,
    latency_ms: null,
    summary: isNonEmptyString(message) ? message.slice(0, 300) : "",
    reason: reason,
  });
}

/**
 * 一次整套视觉复核的运行记录 → VLM findings + vlm 块。
 * vlmRun = { envelope | null, reason, requested_shot_ids, submitted_shot_ids, asset_sha256_by_shot }。
 * 任何结构/身份异常都投影为 UNKNOWN（保留原因），绝不抛错、绝不产生 PASS 假象。
 */
export function buildSuiteVlmFindings({ vlmRun, at } = {}) {
  if (!isIsoTimestamp(at)) invalid("整套复核需要 ISO 时间（at）。");
  const run = isPlainObject(vlmRun) ? vlmRun : {};
  const requested = stringList(run.requested_shot_ids);
  const submitted = stringList(run.submitted_shot_ids);
  const shaByShot = {};
  if (isPlainObject(run.asset_sha256_by_shot)) {
    Object.keys(run.asset_sha256_by_shot).forEach((shotId) => {
      if (isSha256Hex(run.asset_sha256_by_shot[shotId])) {
        shaByShot[shotId] = run.asset_sha256_by_shot[shotId];
      }
    });
  }
  const envelope = isPlainObject(run.envelope) ? run.envelope : null;
  const findings = [];
  let vlm = null;

  if (envelope && envelope.ok === true) {
    let checked = null;
    let failure = null;
    try {
      checked = checkedResultOf(envelope.result, submitted);
    } catch (error) {
      failure = error;
    }
    if (checked) {
      checked.findings.forEach((item) => {
        const ruleId = SUITE_VLM_CHECK_TO_RULE[item.check];
        const entry = registeredRule(ruleId);
        findings.push(withAffected(makeFinding(ruleId, entry.severity, item.evidence, {
          check: item.check,
          confidence: item.confidence,
          shot_ids: stringList(item.shot_ids),
          provider_id: checked.provider_id,
          model_id: checked.model_id,
          request_id: checked.request_id,
          checked_at: checked.checked_at || at,
        }), item.shot_ids));
      });
      if (findings.length === 0) {
        findings.push(withAffected(makeFinding("vlm.suite_inspection_completed", "PASS",
          "整套视觉复核完成，未报告跨图问题（这只是机器事实，不等于人工采纳）。", {
            provider_id: checked.provider_id,
            model_id: checked.model_id,
            request_id: checked.request_id,
            checked_at: checked.checked_at || at,
          }), []));
      }
      vlm = Object.freeze({
        outcome: "checked",
        contract_version: SUITE_REVIEW_CONTRACT_VERSION,
        requested_shot_ids: Object.freeze([...requested]),
        submitted_shot_ids: Object.freeze([...submitted]),
        asset_sha256_by_shot: Object.freeze({ ...shaByShot }),
        provider_id: checked.provider_id,
        model_id: checked.model_id,
        request_id: checked.request_id,
        checked_at: checked.checked_at || at,
        latency_ms: checked.latency_ms,
        summary: checked.summary,
        reason: null,
      });
    } else {
      findings.push(unknownFindingFor("protocol", requested, at,
        failure && failure.message ? failure.message : null, null));
      vlm = unknownBlockFor("protocol", requested, submitted, shaByShot, at, null,
        failure && failure.message ? failure.message : null);
    }
  } else if (envelope) {
    const error = isPlainObject(envelope.error) ? envelope.error : {};
    const message = isNonEmptyString(error.message) ? error.message.slice(0, 300) : "复核未完成。";
    findings.push(unknownFindingFor("server", requested, at, message, error));
    vlm = unknownBlockFor("server", requested, submitted, shaByShot, at, error, message);
  } else {
    const reason = SUITE_VLM_REASONS.indexOf(run.reason) >= 0 ? run.reason : "not_run";
    findings.push(unknownFindingFor(reason, requested, at, null, null));
    vlm = unknownBlockFor(reason, requested, submitted, shaByShot, at, null, null);
  }

  return Object.freeze({ findings: Object.freeze(findings), vlm: vlm });
}

/* -------------------------------------------------------------------------- 报告 */

/**
 * SuiteReviewReport：绑定 selection_fingerprint + inputs_fingerprint 的不可变快照。
 * findings 只允许引用注册表规则；每条必须带 affected_shot_ids；summary 由本函数计算。
 */
export function buildSuiteReviewReport({ selectionFingerprint, inputsFingerprint,
                                         findings, vlm = null, at } = {}) {
  if (!isNonEmptyString(selectionFingerprint)) invalid("整套报告需要 selection_fingerprint。");
  if (!isNonEmptyString(inputsFingerprint)) invalid("整套报告需要 inputs_fingerprint。");
  if (!isIsoTimestamp(at)) invalid("整套报告需要 ISO 时间（at）。");
  if (!Array.isArray(findings) || findings.length === 0) invalid("整套报告需要非空 findings 数组。");
  if (vlm !== null && vlm !== undefined) {
    if (!isPlainObject(vlm)
        || ["checked", "unknown"].indexOf(vlm.outcome) === -1
        || vlm.contract_version !== SUITE_REVIEW_CONTRACT_VERSION) {
      invalid("整套报告的 VLM 块不合法。");
    }
  }
  const normalized = findings.map((item) => {
    if (!isPlainObject(item)) invalid("整套报告的发现必须是对象。");
    const entry = registeredRule(item.rule_id);
    if (!entry) invalid("整套报告发现引用了未登记的规则：" + String(item.rule_id));
    if (REVIEW_SEVERITIES.indexOf(item.severity) === -1) {
      invalid("整套报告发现严重度不合法：" + String(item.severity));
    }
    if (!isNonEmptyString(item.detail)) invalid("整套报告发现必须有 detail。");
    if (!Array.isArray(item.affected_shot_ids)
        || item.affected_shot_ids.some((shotId) => !isNonEmptyString(shotId))) {
      invalid("整套报告每条发现必须带 affected_shot_ids（字符串数组）。");
    }
    return Object.freeze({
      rule_id: entry.rule_id,
      rule_version: Number.isInteger(item.rule_version) ? item.rule_version : entry.version,
      layer: entry.layer,
      severity: item.severity,
      title: isNonEmptyString(item.title) ? item.title : entry.title,
      detail: item.detail,
      measured: item.measured === undefined ? null : item.measured,
      affected_shot_ids: Object.freeze([...item.affected_shot_ids]),
    });
  });
  const summary = { BLOCK: 0, HIGH_RISK: 0, WARNING: 0, PASS: 0, UNKNOWN: 0 };
  normalized.forEach((item) => { summary[item.severity] += 1; });
  return Object.freeze({
    schema_version: SUITE_REVIEW_SCHEMA_VERSION,
    contract_version: SUITE_REVIEW_CONTRACT_VERSION,
    selection_fingerprint: selectionFingerprint,
    inputs_fingerprint: inputsFingerprint,
    vlm: vlm === null || vlm === undefined ? null : Object.freeze({ ...vlm }),
    summary: Object.freeze(summary),
    findings: Object.freeze(normalized),
    created_at: at,
  });
}

/** 报告形状检查：与 checkReviewReport 同构，但要求每条发现带 affected_shot_ids。 */
export function checkSuiteReviewReport(report) {
  const problems = [];
  if (!isPlainObject(report)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "整套一致性报告必须是对象。");
    return problems;
  }
  checkSchemaVersion(report, SUITE_REVIEW_SCHEMA_VERSION, problems, "$");
  if (report.contract_version !== SUITE_REVIEW_CONTRACT_VERSION) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.contract_version",
      "整套报告合同版本不是当前版本。");
  }
  if (!isNonEmptyString(report.selection_fingerprint)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.selection_fingerprint",
      "缺少 selection_fingerprint。");
  }
  if (!isNonEmptyString(report.inputs_fingerprint)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.inputs_fingerprint",
      "缺少 inputs_fingerprint。");
  }
  if (!isIsoTimestamp(report.created_at)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.created_at", "缺少 ISO 时间。");
  }
  if (report.vlm !== null && report.vlm !== undefined) {
    if (!isPlainObject(report.vlm)
        || ["checked", "unknown"].indexOf(report.vlm.outcome) === -1) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.vlm",
        "VLM 块必须是 checked/unknown。");
    } else if (report.vlm.contract_version !== SUITE_REVIEW_CONTRACT_VERSION) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.vlm.contract_version",
        "VLM 块必须绑定当前合同版本。");
    }
  }
  if (!Array.isArray(report.findings) || report.findings.length === 0) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.findings",
      "findings 必须是非空数组。");
    return problems;
  }
  const counts = { BLOCK: 0, HIGH_RISK: 0, WARNING: 0, PASS: 0, UNKNOWN: 0 };
  report.findings.forEach((item, index) => {
    const path = "$.findings[" + index + "]";
    if (!isPlainObject(item)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "发现必须是对象。");
      return;
    }
    if (!isNonEmptyString(item.rule_id) || !registeredRule(item.rule_id)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".rule_id",
        "发现引用了未登记的规则：" + String(item.rule_id));
    }
    if (REVIEW_SEVERITIES.indexOf(item.severity) === -1) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".severity",
        "严重度不在词表内：" + String(item.severity));
    } else {
      counts[item.severity] += 1;
    }
    if (!isNonEmptyString(item.detail)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".detail", "缺少 detail。");
    }
    if (!Array.isArray(item.affected_shot_ids)
        || item.affected_shot_ids.some((shotId) => !isNonEmptyString(shotId))) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".affected_shot_ids",
        "每条发现必须带 affected_shot_ids（字符串数组）。");
    }
  });
  if (!isPlainObject(report.summary)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.summary", "缺少 summary。");
  } else {
    REVIEW_SEVERITIES.forEach((severity) => {
      if (report.summary[severity] !== counts[severity]) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.summary." + severity,
          "汇总与 findings 计数不一致（" + report.summary[severity] + " 与 " + counts[severity] + "）。");
      }
    });
  }
  return problems;
}

/** 报告是否对当前选择与输入仍然有效（字符串指纹逐字比较，选择或输入变化即过期）。 */
export function suiteReviewIsCurrent(report, fingerprints = {}) {
  if (!isPlainObject(report) || !isPlainObject(fingerprints)) return false;
  return report.selection_fingerprint === fingerprints.selectionFingerprint
    && report.inputs_fingerprint === fingerprints.inputsFingerprint;
}

/** 一行摘要（界面状态行与提示共用）。 */
export function suiteReviewSummaryText(report) {
  const summary = report && isPlainObject(report.summary) ? report.summary : {};
  const vlm = report && isPlainObject(report.vlm) ? report.vlm : null;
  const vlmText = vlm
    ? (vlm.outcome === "checked" ? "视觉复核已完成" : "视觉复核未完成（Unknown）")
    : "视觉复核未检查";
  return "整套检查 " + String(report && report.contract_version)
    + "：阻断 " + Number(summary.BLOCK || 0)
    + " · 高风险 " + Number(summary.HIGH_RISK || 0)
    + " · 提醒 " + Number(summary.WARNING || 0)
    + " · 未知 " + Number(summary.UNKNOWN || 0)
    + " · " + vlmText;
}

/* -------------------------------------------------------------------- 组合入口 */

/**
 * 一次整套检查的组装入口：确定性（suite.* + 复用的 export.*）+ 视觉合并 + 指纹 + 报告。
 * readBytes / digest 由调用方注入（分别读 IndexedDB Blob 与 storage/db.js 的 sha256Hex）。
 */
export async function assembleSuiteReview({ selectionSet, suitePlan, styleSpec = null,
                                            shotSpecsById = {}, context = {}, factsById = {},
                                            sellingPoints = [], shots, selections,
                                            candidatesByShot, attemptsByShot,
                                            reportsByCandidate, readBytes, digest,
                                            vlmRun = null, at } = {}) {
  if (!isPlainObject(suitePlan) || !Array.isArray(suitePlan.shots)) {
    invalid("整套检查需要套图计划（shots 数组）。");
  }
  if (!Array.isArray(shots)) invalid("整套检查需要 shots 列表。");
  if (!isIsoTimestamp(at)) invalid("整套检查需要 ISO 时间（at）。");
  const suiteFindings = evaluateSuiteFindings({
    suitePlan: suitePlan, selectionSet: selectionSet, context: context,
    factsById: factsById, sellingPoints: sellingPoints,
  }).findings;
  const readiness = evaluateExportReadiness({
    shots: shots, selections: selections, candidatesByShot: candidatesByShot,
    reportsByCandidate: reportsByCandidate, attemptsByShot: attemptsByShot,
  });
  const hashCheck = await verifyAssetHashes({
    selections: selections, candidatesByShot: candidatesByShot,
    readBytes: readBytes, digest: digest,
  });
  const exportFindings = mergeExportFindings({
    readinessFindings: readiness.findings, hashFindings: hashCheck.findings,
  });
  const vlm = buildSuiteVlmFindings({ vlmRun: vlmRun, at: at });
  const selectionFingerprint = selectionFingerprintOf(selectionSet);
  const inputsFingerprint = inputsFingerprintOf({
    selectionFingerprint: selectionFingerprint,
    suitePlan: suitePlan,
    styleSpec: styleSpec,
    shotSpecsById: shotSpecsById,
    reportsByCandidate: reportsByCandidate,
  });
  return buildSuiteReviewReport({
    selectionFingerprint: selectionFingerprint,
    inputsFingerprint: inputsFingerprint,
    findings: [...suiteFindings, ...exportFindings, ...vlm.findings],
    vlm: vlm.vlm,
    at: at,
  });
}
