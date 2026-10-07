/**
 * V2.5.3 候选比较与审核清单的视图模型（唯一权威）。
 *
 * 这是投影，不是第二套规则引擎：
 *  - 复核规则、严重度与「先看哪一条」仍由 domain/review.js 决定，本模块只读报告，不重算；
 *  - 每张图的验收依据仍由 domain/specs.js 的 reviewChecklist 投影；
 *  - 本模块只回答三件事：多个候选怎么排、默认看哪一个、下一个待处理在哪张图。
 * 不写存储、不产生选择、不调用模型，也不把「无发现」当成人工采纳。
 *
 * 排序规则（compare.severity_order@V2.5.3，消费者 review-panel@V2.5.3）：
 *  1. 有 BLOCK / HIGH_RISK / WARNING 的候选在前（异常优先）；
 *  2. 其次是 UNKNOWN（机器没查完，不等于没问题）；
 *  3. 再次是无发现（PASS）；
 *  4. 未检查的候选排最后（还不知道，不是通过）；
 *  5. 同档按版本新到旧，最后用 candidate_id 兜底，保证顺序稳定可复现。
 */
import { DOMAIN_ERROR_CODES } from "./errors.js";
import { REVIEW_SEVERITY_ORDER, topFinding } from "./review.js";
import { isNonEmptyString, isPlainObject, isSha256Hex, pushProblem } from "./shared.js";

export const COMPARE_CONTRACT_VERSION = "v2.5.3";

/** 待处理 = 需要人工先看的严重度；UNKNOWN 与 PASS 只提示，不阻断。 */
export const COMPARE_PENDING_SEVERITIES = Object.freeze(
  REVIEW_SEVERITY_ORDER.filter((item) => item !== "UNKNOWN"));

export const COMPARE_STATE_TEXT = Object.freeze({
  pending: "待处理", unknown: "未知", clean: "无发现", unchecked: "未检查",
});

export const COMPARE_SEVERITY_TEXT = Object.freeze({
  BLOCK: "阻断", HIGH_RISK: "高风险", WARNING: "提醒", UNKNOWN: "未知", PASS: "通过",
});

export const COMPARE_UNCHECKED_TEXT =
  "没有自动检查报告：保存候选时会自动生成，旧候选在重新打开项目时补建。";
export const COMPARE_CLEAN_TEXT = "自动检查没有发现问题（机器结论，人工确认仍然必要）。";

/** 严重度秩：只读 review.js 的顺序表；未登记的严重度与「没有发现」都排在最后。 */
export function compareSeverityRank(finding) {
  const severity = isPlainObject(finding) ? finding.severity : null;
  const index = REVIEW_SEVERITY_ORDER.indexOf(severity);
  return index === -1 ? REVIEW_SEVERITY_ORDER.length : index;
}

/** 审核清单顺序：阻断 → 高风险 → 提醒 → 未知 → 通过；同档保持报告原顺序（稳定排序）。 */
export function sortFindings(findings) {
  const list = Array.isArray(findings) ? findings : [];
  return list
    .map((item, index) => ({ item, index }))
    .filter((pair) => isPlainObject(pair.item))
    .sort((left, right) => (compareSeverityRank(left.item) - compareSeverityRank(right.item))
      || (left.index - right.index))
    .map((pair) => pair.item);
}

/**
 * 单个候选的复核状态：pending（需要先看）/ unknown（没查完）/ clean（无发现）/ unchecked（没有报告）。
 * options.current === false 表示报告与当前合同版本或候选字节不一致，一律降级为 unchecked。
 */
export function compareStateOf(report, options = {}) {
  if (!isPlainObject(report) || !Array.isArray(report.findings) || report.findings.length === 0) {
    return "unchecked";
  }
  if (options.current === false) return "unchecked";
  const top = topFinding(report);
  if (top && COMPARE_PENDING_SEVERITIES.indexOf(top.severity) >= 0) return "pending";
  const summary = isPlainObject(report.summary) ? report.summary : {};
  if (Number(summary.UNKNOWN || 0) > 0) return "unknown";
  return "clean";
}

/** 面板一行摘要：没有报告 / 无发现 / 最需要先看的一条；不重复整份报告。 */
export function compareRowHeadline(row) {
  if (!isPlainObject(row)) return "";
  if (row.review_state === "unchecked") return COMPARE_UNCHECKED_TEXT;
  if (row.review_state === "clean") return COMPARE_CLEAN_TEXT;
  const finding = row.top_finding;
  if (!isPlainObject(finding)) return COMPARE_STATE_TEXT[row.review_state] || "";
  const label = COMPARE_SEVERITY_TEXT[finding.severity] || String(finding.severity);
  return label + " · " + String(finding.title || finding.rule_id || "") + "：" + String(finding.detail || "");
}

/** 行的排序秩：未检查排在无发现之后（「还不知道」比「已确认没发现」更弱）。 */
export function compareRowRank(row) {
  if (!isPlainObject(row)) return REVIEW_SEVERITY_ORDER.length + 2;
  if (row.review_state === "unchecked") return REVIEW_SEVERITY_ORDER.length + 1;
  return compareSeverityRank(row.top_finding);
}

/**
 * 把同一 Shot 的候选与各自「当前」报告排成异常优先的顺序。
 *
 * candidates：storage 版本记录（{record, version}）或裸候选记录；
 * reportsByCandidateId：candidate_id → 报告（调用方先用 reviewIsCurrent 过滤，本模块不重算）；
 * attemptsByActionId：action_id → Attempt 记录（只用于显示来源，可缺省）。
 */
export function compareRows({ candidates, reportsByCandidateId, attemptsByActionId } = {}) {
  const list = Array.isArray(candidates) ? candidates : [];
  const reports = isPlainObject(reportsByCandidateId) ? reportsByCandidateId : {};
  const attempts = isPlainObject(attemptsByActionId) ? attemptsByActionId : {};
  const rows = list.map((entry) => {
    const record = isPlainObject(entry) && isPlainObject(entry.record) ? entry.record : entry;
    if (!isPlainObject(record) || !isNonEmptyString(record.candidate_id)) return null;
    const report = isPlainObject(reports[record.candidate_id]) ? reports[record.candidate_id] : null;
    const attempt = isPlainObject(attempts[record.attempt_action_id])
      ? attempts[record.attempt_action_id] : null;
    return Object.freeze({
      candidate_id: record.candidate_id,
      shot_id: record.shot_id,
      asset_sha256: record.asset_sha256,
      version: isPlainObject(entry) && Number.isInteger(entry.version) ? entry.version : null,
      created_at: record.created_at,
      attempt_action_id: record.attempt_action_id || null,
      task_id: attempt && isNonEmptyString(attempt.task_id) ? attempt.task_id : null,
      width: Number.isInteger(record.width) ? record.width : null,
      height: Number.isInteger(record.height) ? record.height : null,
      review_state: compareStateOf(report),
      pending: compareStateOf(report) === "pending",
      top_finding: report ? topFinding(report) : null,
      report,
      record,
    });
  }).filter(Boolean);
  rows.sort((left, right) => (compareRowRank(left) - compareRowRank(right))
    || ((right.version || 0) - (left.version || 0))
    || String(left.candidate_id).localeCompare(String(right.candidate_id)));
  return Object.freeze(rows);
}

/** 默认查看目标 = 排在最前的那一个（异常优先，同级新到旧）。 */
export function defaultCompareTargetId(rows) {
  const list = Array.isArray(rows) ? rows : [];
  return list.length && isNonEmptyString(list[0].candidate_id) ? list[0].candidate_id : null;
}

/** 概览计数：面板标题行用；不展开细节。 */
export function compareCounts(rows) {
  const counts = { total: 0, pending: 0, unknown: 0, clean: 0, unchecked: 0 };
  for (const row of Array.isArray(rows) ? rows : []) {
    counts.total += 1;
    if (isPlainObject(row) && Object.prototype.hasOwnProperty.call(counts, row.review_state)) {
      counts[row.review_state] += 1;
    }
  }
  return counts;
}

/** 下一个待处理的 Shot：从当前之后按计划顺序找，绕回一圈；没有就返回 null。 */
export function nextPendingShotId({ rowsByShotId, shotOrder, currentShotId } = {}) {
  const rows = isPlainObject(rowsByShotId) ? rowsByShotId : {};
  const order = Array.isArray(shotOrder)
    ? shotOrder.filter((item) => isNonEmptyString(item))
    : Object.keys(rows);
  if (order.length === 0) return null;
  const start = order.indexOf(currentShotId);
  for (let step = 1; step <= order.length; step += 1) {
    const index = start === -1 ? step - 1 : (start + step) % order.length;
    const shotId = order[index];
    const list = Array.isArray(rows[shotId]) ? rows[shotId] : [];
    if (list.some((row) => row && row.pending === true)) return shotId;
  }
  return null;
}

/** 行集合自检：唯一性、身份、排序与状态一致；反向探针用它证明守卫会变红。 */
export function checkCompareRows(rows) {
  const problems = [];
  if (!Array.isArray(rows)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "比较行必须是数组。");
    return problems;
  }
  const seen = new Set();
  let previousRank = -1;
  rows.forEach((row, index) => {
    const path = "$[" + index + "]";
    if (!isPlainObject(row)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "行必须是对象。");
      return;
    }
    if (!isNonEmptyString(row.candidate_id)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".candidate_id",
        "缺少 candidate_id。");
    } else if (seen.has(row.candidate_id)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".candidate_id",
        "同一个候选出现两次。");
    } else {
      seen.add(row.candidate_id);
    }
    if (!isSha256Hex(row.asset_sha256)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".asset_sha256",
        "缺少候选字节哈希。");
    }
    const rank = compareRowRank(row);
    if (rank < previousRank) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "行顺序不满足异常优先。");
    }
    previousRank = rank;
    if (row.pending !== (row.review_state === "pending")) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".pending",
        "pending 标记与 review_state 不一致。");
    }
    if (row.pending === true && !isPlainObject(row.top_finding)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".top_finding",
        "待处理行必须给出先看的发现。");
    }
  });
  return problems;
}
