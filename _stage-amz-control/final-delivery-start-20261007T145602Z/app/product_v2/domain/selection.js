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

/** 派生状态的界面文案（与 SELECTION_STATES 键一一对应）。
 * @type {Readonly<Record<import("./type-contracts.js").SelectionState, string>>}
 */
export const SELECTION_STATE_TEXT = Object.freeze({
  none: "尚未采用候选",
  current: "已采用",
  stale: "已过期",
  cleared: "已取消采用",
});

/** 选择时审核指纹：只记录「当时看得见什么」，供后续判断报告是否仍当前。没有报告时返回 null。
 * @param {unknown} report
 * @returns {import("./type-contracts.js").SelectionReviewFingerprint|null}
 */
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

/** 构造选择记录：select 必须绑定候选身份与候选记录版本；clear 不携带候选身份。
 * @param {{selectionId?: unknown, action?: unknown, shotId?: unknown, candidate?: unknown,
 *          candidateVersion?: unknown, report?: unknown, at?: unknown}} [args]
 * @returns {import("./type-contracts.js").SelectionRecord}
 */
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

/** 选择记录形状检查；返回问题清单（空数组 = 合法）。
 * @param {unknown} record
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkSelectionRecord(record) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
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

/** 校验通过则原样返回选择记录，否则抛 DomainError。
 * @param {unknown} record
 * @returns {import("./type-contracts.js").SelectionRecord}
 */
export function assertSelectionRecord(record) {
  const problems = checkSelectionRecord(record);
  if (problems.length > 0) invalid("选择记录不合法：" + problems[0].message);
  return record;
}

/**
 * 失效判据（V2.R6.2）：采用只在「它实际消费的依据或来源真的变了」时才过期——
 *  - 候选链**已提供**时：它指向的候选已不在候选链里（候选来源缺失）；
 *  - 候选链**已提供**时：该候选的字节身份（asset_sha256）与采用时不一致；
 *  - 调用方显式给出的按图消费依据已过期（options.consumedStale，来自该图 Prompt 的按槽位依据核对）。
 *  候选链没提供（null/undefined）时无法判定来源，保持 current。
 *
 * 关键边界：**之后出现更新的成功候选不再自动使采用过期**。自动审核只提供依据，采用是人的决定；
 * 新候选出现不等于人的决定失效，界面只提示「有新候选可比较」。改选仍是一条更晚的选择动作。
 * @param {unknown} record
 * @param {unknown} [candidates]
 * @param {{consumedStale?: boolean, consumedStaleReasons?: unknown}} [options]
 * @returns {import("./type-contracts.js").SelectionStaleReason[]}
 */
export function selectionStaleReasons(record, candidates = [], options = {}) {
  /** @type {import("./type-contracts.js").SelectionStaleReason[]} */
  const reasons = [];
  if (!isPlainObject(record) || record.action !== "select") return reasons;
  // 候选链「没提供」（null/undefined）与「提供但为空」不同：没提供时无法判定来源，
  // 保持 current；提供了就按链核对（缺候选、字节变化都算真实来源变化）。
  if (Array.isArray(candidates)) {
    const payloadOf = (item) => (item && isPlainObject(item.record) ? item.record : item);
    const found = candidates.map(payloadOf).find((item) => isPlainObject(item)
      && item.candidate_id === record.candidate_id) || null;
    if (!found) {
      reasons.push({ field: "candidate", stored: record.candidate_id, current: null,
        reason: "采用指向的候选已不在候选链里" });
    } else if (found.asset_sha256 !== record.candidate_sha256) {
      reasons.push({ field: "candidate.sha256", stored: record.candidate_sha256,
        current: found.asset_sha256 || null, reason: "采用消费的候选字节已变化" });
    }
  }
  if (options.consumedStale === true) {
    reasons.push({ field: "basis", stored: null, current: null,
      reason: "这张图实际消费的依据（已确认事实/规格/能力）已变化" });
  }
  if (Array.isArray(options.consumedStaleReasons)) {
    for (const item of options.consumedStaleReasons) reasons.push(item);
  }
  return reasons;
}

/**
 * 失效判断四态：none / current / stale / cleared。
 * 新成功候选不再自动引起 stale（见 selectionStaleReasons）；只有实际消费依据/来源变化才过期。
 * @param {unknown} record
 * @param {unknown} [candidates]
 * @param {{consumedStale?: boolean, consumedStaleReasons?: unknown}} [options]
 * @returns {import("./type-contracts.js").SelectionState}
 */
export function deriveSelectionState(record, candidates = [], options = {}) {
  if (!isPlainObject(record)) return "none";
  if (record.action === "clear") return "cleared";
  if (!isIsoTimestamp(record.created_at)) return "none";
  return selectionStaleReasons(record, candidates, options).length > 0 ? "stale" : "current";
}

/** 选择与候选链的关系投影：这条选择现在指向哪条候选、是否仍有效。
 * @param {unknown} record
 * @param {unknown} [candidates]
 * @param {{consumedStale?: boolean, consumedStaleReasons?: unknown}} [options]
 * @returns {{state: import("./type-contracts.js").SelectionState, candidate_id: string|null, current: boolean}}
 */
export function selectionCoversShot(record, candidates = [], options = {}) {
  const state = deriveSelectionState(record, candidates, options);
  return Object.freeze({
    state: state,
    candidate_id: state === "current" || state === "stale" ? record.candidate_id : null,
    current: state === "current",
  });
}

/** SelectionSet：V2.5.5 与 V2.6.2 的唯一输入集合（这里只派生，不阻断导出）。
 * @param {{shots?: unknown, selections?: unknown, candidatesByShotId?: unknown,
 *          basisByShotId?: unknown, at?: unknown}} [args]
 * @returns {import("./type-contracts.js").SelectionSet}
 */
export function buildSelectionSet({ shots, selections, candidatesByShotId,
                                    basisByShotId = {}, at } = {}) {
  const list = Array.isArray(shots) ? shots : [];
  const byShot = isPlainObject(selections) ? selections : {};
  const candidateMap = isPlainObject(candidatesByShotId) ? candidatesByShotId : {};
  const basisMap = isPlainObject(basisByShotId) ? basisByShotId : {};
  const entries = list.map((shot) => {
    const shotId = shot && isNonEmptyString(shot.shot_id) ? shot.shot_id : null;
    const record = shotId && isPlainObject(byShot[shotId]) ? byShot[shotId] : null;
    const basis = shotId && isPlainObject(basisMap[shotId]) ? basisMap[shotId] : {};
    const state = deriveSelectionState(record, candidateMap[shotId] || [], basis);
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

/** 派生状态的界面文案（与 SELECTION_STATES 键一一对应）。
 * @param {unknown} state
 * @returns {string}
 */
export function selectionStateLabel(state) {
  return SELECTION_STATE_TEXT[state] || "未知状态";
}

/** 单行摘要（行内状态行与提示共用）：不含命令，也不暗示导出已经就绪。
 * @param {unknown} record
 * @param {import("./type-contracts.js").SelectionState|null} [state]
 * @returns {string}
 */
export function selectionSummaryText(record, state = null) {
  const derived = state || deriveSelectionState(record, []);
  if (derived === "none") return "尚未采用候选：在候选比较里选一条，点「采用此候选」。";
  if (derived === "cleared") return "已取消采用（历史保留）；可以重新采用任一候选。";
  const head = "已采用候选 v" + record.candidate_version
    + "（选择记录 " + record.selection_id + "）";
  if (derived === "stale") {
    return head + "；已过期：它实际消费的候选来源或依据已变化，请重新采用（新候选或旧候选都行）。";
  }
  return head + "；当前仍有效（自动审核只提供依据，选择由人做出）。";
}

/** 整套摘要（SelectionSet 投影）：只报告数量，不在这里拦导出。
 * @param {unknown} set
 * @returns {string}
 */
export function selectionSetText(set) {
  if (!isPlainObject(set) || !isPlainObject(set.summary)) return "";
  const summary = set.summary;
  return "人工采用：必需图 " + summary.current + "/" + summary.required_total
    + " 张当前有效；过期 " + summary.stale + " 张；缺选 " + summary.missing + " 张。";
}
