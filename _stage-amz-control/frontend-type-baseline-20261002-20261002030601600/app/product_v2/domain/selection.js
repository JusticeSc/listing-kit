/**
 * V2.6.1 人工选择（Selection）：候选采用、改选、取消采用与失效判断（唯一权威）。
 *
 * 选择不是「最新候选」的别名：整套一致性与交付必须先有一个明确的人工选择集合。
 *  - 一个必需 Shot 最多一条 current 选择；改选与取消采用都追加新版本，旧记录保留。
 *  - 目标 Shot 出现新的成功候选后，原选择变 stale（不覆盖、不自动改选、不自动取消）。
 *  - 选择只引用内容寻址的候选（candidate_id + sha256 + 候选记录版本），不复制图片。
 *  - 自动审核只提供依据，不产生选择；本模块不做审核、不做导出阻断（导出硬门属 V2.6.2）。
 * 本层是纯函数：不写存储、不发请求、不读时钟、不生成 id。
 */

import { DOMAIN_ERROR_CODES, invalid } from "./errors.js";
import { topFinding } from "./review.js";
import {
  DOMAIN_DOCUMENT_KINDS, checkSchemaVersion, isIsoTimestamp, isNonEmptyString,
  isPlainObject, isSha256Hex, pushProblem,
} from "./shared.js";

export const SELECTION_CONTRACT_VERSION = "v2.6.1";
export const SELECTION_SCHEMA_VERSION = 1;
export const SELECTION_DOCUMENT_KIND = DOMAIN_DOCUMENT_KINDS.selection;

/** 选择动作：select = 采用/改选；clear = 取消采用。两者都追加记录，不原地改写。 */
export const SELECTION_ACTIONS = Object.freeze(["select", "clear"]);

/** 派生状态（不存储）：none / current / stale / cleared。 */
export const SELECTION_STATES = Object.freeze(["none", "current", "stale", "cleared"]);

export const SELECTION_STATE_TEXT = Object.freeze({
  none: "尚未采用候选",
  current: "已采用",
  stale: "已过期",
  cleared: "已取消采用",
});

function timeValue(value) {
  const parsed = Date.parse(String(value));
  return Number.isNaN(parsed) ? null : parsed;
}

/** 选择时审核指纹：只记录「当时看得见什么」，供后续判断报告是否仍当前。没有报告时返回 null。 */
export function selectionReviewFingerprint(report) {
  if (!isPlainObject(report)) return null;
  const top = topFinding(report);
  return Object.freeze({
    review_contract_version: isNonEmptyString(report.review_contract_version)
      ? report.review_contract_version : null,
    report_created_at: isIsoTimestamp(report.created_at) ? report.created_at : null,
    candidate_id: isNonEmptyString(report.candidate_id) ? report.candidate_id : null,
    asset_sha256: isSha256Hex(report.asset_sha256) ? report.asset_sha256 : null,
    finding_count: Array.isArray(report.findings) ? report.findings.length : 0,
    top_rule_id: top ? top.rule_id : null,
    top_severity: top ? top.severity : null,
  });
}

/** 构造选择记录：select 必须绑定候选身份与候选记录版本；clear 不携带候选身份。 */
export function buildSelectionRecord({ selectionId, action, shotId, candidate = null,
                                       candidateVersion = null, report = null, at } = {}) {
  if (!isNonEmptyString(selectionId)) invalid("选择记录需要动作身份（selection_id）。");
  if (SELECTION_ACTIONS.indexOf(action) === -1) invalid("未知的选择动作：" + String(action));
  if (!isNonEmptyString(shotId)) invalid("选择记录需要 shot_id。");
  if (!isIsoTimestamp(at)) invalid("选择记录需要 ISO 时间（at）。");
  let candidateId = null;
  let candidateSha = null;
  let version = null;
  let fingerprint = null;
  if (action === "select") {
    if (!isPlainObject(candidate) || !isNonEmptyString(candidate.candidate_id)
        || !isSha256Hex(candidate.asset_sha256)) {
      invalid("采用候选必须绑定一条候选（candidate_id + sha256）。");
    }
    if (candidate.shot_id !== shotId) invalid("这条候选不属于这张图，不能采用。");
    if (!Number.isInteger(candidateVersion) || candidateVersion < 1) {
      invalid("采用候选需要候选记录版本号（正整数）。");
    }
    candidateId = candidate.candidate_id;
    candidateSha = candidate.asset_sha256;
    version = candidateVersion;
    fingerprint = selectionReviewFingerprint(report);
  }
  return Object.freeze({
    schema_version: SELECTION_SCHEMA_VERSION,
    contract_version: SELECTION_CONTRACT_VERSION,
    selection_id: selectionId,
    action: action,
    shot_id: shotId,
    candidate_id: candidateId,
    candidate_sha256: candidateSha,
    candidate_version: version,
    review_fingerprint: fingerprint,
    created_at: at,
  });
}

export function checkSelectionRecord(record) {
  const problems = [];
  if (!isPlainObject(record)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "选择记录必须是对象。");
    return problems;
  }
  checkSchemaVersion(record, SELECTION_SCHEMA_VERSION, problems, "$");
  if (record.contract_version !== SELECTION_CONTRACT_VERSION) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.contract_version",
      "选择合同版本不是当前版本。");
  }
  if (!isNonEmptyString(record.selection_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.selection_id",
      "缺少选择动作身份。");
  }
  if (SELECTION_ACTIONS.indexOf(record.action) === -1) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.action",
      "未知的选择动作：" + String(record.action));
  }
  if (!isNonEmptyString(record.shot_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shot_id", "缺少 shot_id。");
  }
  if (record.action === "select") {
    if (!isNonEmptyString(record.candidate_id) || !isSha256Hex(record.candidate_sha256)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.candidate_id",
        "采用候选必须绑定候选身份。");
    }
    if (!Number.isInteger(record.candidate_version) || record.candidate_version < 1) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.candidate_version",
        "采用候选需要候选记录版本号。");
    }
  } else if (record.candidate_id !== null || record.candidate_sha256 !== null
             || record.candidate_version !== null) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.candidate_id",
      "取消采用不应携带候选身份。");
  }
  if (!isIsoTimestamp(record.created_at)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.created_at", "缺少 ISO 时间。");
  }
  return problems;
}

export function assertSelectionRecord(record) {
  const problems = checkSelectionRecord(record);
  if (problems.length > 0) invalid("选择记录不合法：" + problems[0].message);
  return record;
}

/**
 * 失效判断：选择动作之后出现更晚的成功候选 ⇒ stale。
 * 失败 Attempt 不产生候选，因此不影响选择；改选旧候选是一条更晚的选择动作，重新变 current。
 */
export function deriveSelectionState(record, candidates = []) {
  if (!isPlainObject(record)) return "none";
  if (record.action === "clear") return "cleared";
  if (!isIsoTimestamp(record.created_at)) return "none";
  const selectedAt = timeValue(record.created_at);
  const list = Array.isArray(candidates) ? candidates : [];
  const newer = list.some((item) => {
    const payload = item && isPlainObject(item.record) ? item.record : item;
    if (!isPlainObject(payload) || !isIsoTimestamp(payload.created_at)) return false;
    const candidateAt = timeValue(payload.created_at);
    return candidateAt !== null && selectedAt !== null && candidateAt > selectedAt;
  });
  return newer ? "stale" : "current";
}

/** 选择与候选链的关系投影：这条选择现在指向哪条候选、是否仍有效。 */
export function selectionCoversShot(record, candidates = []) {
  const state = deriveSelectionState(record, candidates);
  return Object.freeze({
    state: state,
    candidate_id: state === "current" || state === "stale" ? record.candidate_id : null,
    current: state === "current",
  });
}

/** SelectionSet：V2.5.5 与 V2.6.2 的唯一输入集合（这里只派生，不阻断导出）。 */
export function buildSelectionSet({ shots, selections, candidatesByShotId, at } = {}) {
  const list = Array.isArray(shots) ? shots : [];
  const byShot = isPlainObject(selections) ? selections : {};
  const candidateMap = isPlainObject(candidatesByShotId) ? candidatesByShotId : {};
  const entries = list.map((shot) => {
    const shotId = shot && isNonEmptyString(shot.shot_id) ? shot.shot_id : null;
    const record = shotId && isPlainObject(byShot[shotId]) ? byShot[shotId] : null;
    const state = deriveSelectionState(record, candidateMap[shotId] || []);
    return Object.freeze({
      shot_id: shotId,
      required: Boolean(shot && shot.required === true),
      state: state,
      selection_id: record ? record.selection_id : null,
      candidate_id: record && record.action === "select" ? record.candidate_id : null,
      candidate_sha256: record && record.action === "select" ? record.candidate_sha256 : null,
      candidate_version: record && record.action === "select" ? record.candidate_version : null,
      selected_at: record ? record.created_at : null,
    });
  });
  const requiredEntries = entries.filter((entry) => entry.required);
  return Object.freeze({
    contract_version: SELECTION_CONTRACT_VERSION,
    generated_at: isIsoTimestamp(at) ? at : null,
    entries: Object.freeze(entries),
    summary: Object.freeze({
      required_total: requiredEntries.length,
      current: requiredEntries.filter((entry) => entry.state === "current").length,
      stale: requiredEntries.filter((entry) => entry.state === "stale").length,
      missing: requiredEntries.filter((entry) => entry.state === "none"
        || entry.state === "cleared").length,
      optional_current: entries.filter((entry) => !entry.required
        && entry.state === "current").length,
    }),
  });
}

export function selectionStateLabel(state) {
  return SELECTION_STATE_TEXT[state] || "未知状态";
}

/** 单行摘要（行内状态行与提示共用）：不含命令，也不暗示导出已经就绪。 */
export function selectionSummaryText(record, state = null) {
  const derived = state || deriveSelectionState(record, []);
  if (derived === "none") return "尚未采用候选：在候选比较里选一条，点「采用此候选」。";
  if (derived === "cleared") return "已取消采用（历史保留）；可以重新采用任一候选。";
  const head = "已采用候选 v" + record.candidate_version
    + "（选择记录 " + record.selection_id + "）";
  if (derived === "stale") {
    return head + "；已过期：之后出现了新候选，请重新采用（新候选或旧候选都行）。";
  }
  return head + "；当前仍有效（自动审核只提供依据，选择由人做出）。";
}

/** 整套摘要（SelectionSet 投影）：只报告数量，不在这里拦导出。 */
export function selectionSetText(set) {
  if (!isPlainObject(set) || !isPlainObject(set.summary)) return "";
  const summary = set.summary;
  return "人工采用：必需图 " + summary.current + "/" + summary.required_total
    + " 张当前有效；过期 " + summary.stale + " 张；缺选 " + summary.missing + " 张。";
}
