/**
 * Product V2 整套批次执行（V2.4.3，计划 §9.12）。
 *
 * 设计边界：
 *  - 批次没有独立的存储实体：进度、队列与下一步全部是「套图顺序 + 每张图最新 Attempt +
 *    Prompt 就绪状态」的投影。刷新、关标签页、换浏览器会话只依赖已持久化的记录，
 *    不存在第二份需要对账的状态，因此不存在「批次丢了」这种恢复问题。
 *  - 本层是纯函数：不写存储、不发请求、不调用模型、不读时钟、不生成 action id。
 *  - 提交顺序 = 套图顺序（唯一权威是 suite plan，本层不重排）。
 *  - 「停止」只停新增提交：不撤销、不覆盖、不删除任何已有记录。
 *  - 结果未知永不进入提交队列与重试队列；有任务编号的记录进入核对队列，只查询、不重提。
 */

import { ATTEMPT_RECONCILE_MODES, ATTEMPT_STATES, attemptReconcileMode } from "./attempt.js";
import { invalid } from "./errors.js";
import { isNonEmptyString, isPlainObject } from "./shared.js";

export const BATCH_SCHEMA_VERSION = 1;

/**
 * 每张图在批次里的状态；前两个是「未提交」的两种原因，其余是 Attempt 状态的投影。
 * V2.4.4 起多一种「已成功但候选字节还没进 IndexedDB」的投影（succeeded_unstored）——
 * 只在调用方提供 candidateStored 时才会出现；不提供时行为与 V2.4.3 完全一致。
 */
export const BATCH_SHOT_STATES = Object.freeze({
  blocked_no_prompt: "blocked_no_prompt",
  ready: "ready",
  active: "active",
  succeeded: "succeeded",
  succeeded_unstored: "succeeded_unstored",
  failed: "failed",
  unknown: "unknown",
});

export const BATCH_SHOT_STATE_LABELS = Object.freeze({
  blocked_no_prompt: "待编译 Prompt",
  ready: "待提交",
  active: "处理中",
  succeeded: "已成功",
  succeeded_unstored: "已生成，待保存候选",
  failed: "失败",
  unknown: "结果未知",
});

/** 下一步优先级：empty → submit → compile → wait → fetch → review → retry → done。 */
export const BATCH_NEXT_STEPS = Object.freeze({
  empty: "empty",
  submit: "submit",
  compile: "compile",
  wait: "wait",
  fetch: "fetch",
  review: "review",
  retry: "retry",
  done: "done",
});

/**
 * 系统性提交错误：继续提交只会把剩余图片也拖成同类记录，批次立即停止新增提交。
 *  - SUBMIT_OUTCOME_UNKNOWN：连接中断或响应不可解析，无法判断上游是否受理；
 *  - RESPONSE_UNREADABLE：网关没有返回约定信封；
 *  - family = internal：服务端内部故障或 provider 未配置。
 * 单张的明确失败（input_rejected / provider_failed）与单张的未知（上游 504）不停止批次——
 * 它们可隔离、可单独处理。停止只停新增提交，已有记录逐字保留。
 */
export const BATCH_HALT_CODES = Object.freeze(["SUBMIT_OUTCOME_UNKNOWN", "RESPONSE_UNREADABLE"]);

export function batchSubmitHalts(outcome) {
  if (!isPlainObject(outcome)) return false;
  const error = isPlainObject(outcome.error) ? outcome.error : null;
  if (!error) return false;
  if (BATCH_HALT_CODES.includes(error.code)) return true;
  return error.family === "internal";
}

/**
 * 批次状态推导。输入全部是只读投影：
 *  - shots：套图顺序，[{shot_id, label}]（唯一权威是 suite plan，本层保持原顺序）；
 *  - latestAttempts：shot_id → 最新 Attempt 记录（或 null）；
 *  - promptReady：shot_id → 是否已有可提交的 Prompt 版本。
 * 输出：每张图的状态、计数、全部队列与下一步；同输入必须得到同输出。
 */
export function deriveBatchState({
  shots, latestAttempts = {}, promptReady = () => true, candidateStored = null,
} = {}) {
  if (!Array.isArray(shots)) invalid("批次需要套图顺序（shots 必须是数组）");
  if (!isPlainObject(latestAttempts)) invalid("latestAttempts 必须是 shot_id 到记录的映射");
  if (typeof promptReady !== "function") invalid("promptReady 必须是函数");
  if (candidateStored !== null && typeof candidateStored !== "function") {
    invalid("candidateStored 必须是函数或 null（null = 不投影候选状态）");
  }
  const counts = {
    total: 0, ready: 0, active: 0, succeeded: 0, unstored: 0, failed: 0, unknown: 0,
    blocked_no_prompt: 0,
  };
  const rows = [];
  const queue = [];
  const reconcileQueue = [];
  const fetchQueue = [];
  const retryQueue = [];
  const reviewQueue = [];
  let started = false;
  for (const shot of shots) {
    if (!isPlainObject(shot) || !isNonEmptyString(shot.shot_id)) {
      invalid("套图里的每一项都必须是带 shot_id 的对象");
    }
    const shotId = shot.shot_id;
    const record = isPlainObject(latestAttempts[shotId]) ? latestAttempts[shotId] : null;
    const hasPrompt = promptReady(shotId) === true;
    let state;
    let candidateStoredFlag = null;
    if (!record) {
      state = hasPrompt ? BATCH_SHOT_STATES.ready : BATCH_SHOT_STATES.blocked_no_prompt;
    } else {
      started = true;
      state = record.state;
      if (state === ATTEMPT_STATES.succeeded && candidateStored !== null) {
        candidateStoredFlag = candidateStored(shotId) === true;
        if (!candidateStoredFlag) state = BATCH_SHOT_STATES.succeeded_unstored;
      }
    }
    counts.total += 1;
    if (state === BATCH_SHOT_STATES.ready) {
      counts.ready += 1;
      queue.push(shotId);
    } else if (state === BATCH_SHOT_STATES.blocked_no_prompt) {
      counts.blocked_no_prompt += 1;
    } else if (state === BATCH_SHOT_STATES.succeeded_unstored) {
      counts.unstored += 1;
      fetchQueue.push(shotId);
    } else if (state === ATTEMPT_STATES.succeeded) {
      counts.succeeded += 1;
    } else if (state === ATTEMPT_STATES.failed) {
      counts.failed += 1;
      retryQueue.push(shotId);
    } else if (state === ATTEMPT_STATES.unknown) {
      counts.unknown += 1;
      const mode = attemptReconcileMode(record);
      if (mode === ATTEMPT_RECONCILE_MODES.by_task) reconcileQueue.push(shotId);
      else reviewQueue.push(shotId);
    } else {
      counts.active += 1;
      const mode = attemptReconcileMode(record);
      if (mode === ATTEMPT_RECONCILE_MODES.by_task) reconcileQueue.push(shotId);
      else reviewQueue.push(shotId);
    }
    rows.push({
      shot_id: shotId,
      label: isNonEmptyString(shot.label) ? shot.label : shotId,
      state: state,
      has_prompt: hasPrompt,
      has_attempt: Boolean(record),
      attempt_state: record ? record.state : null,
      action_id: record ? record.action_id : null,
      task_id: record ? record.task_id : null,
      candidate_stored: candidateStoredFlag,
      reconcile_mode: record ? attemptReconcileMode(record) : ATTEMPT_RECONCILE_MODES.none,
    });
  }
  const settled = counts.ready === 0 && counts.active === 0
    && counts.blocked_no_prompt === 0 && counts.unstored === 0;
  const allSucceeded = counts.total > 0 && counts.succeeded === counts.total;
  let nextStep = BATCH_NEXT_STEPS.done;
  if (counts.total === 0) nextStep = BATCH_NEXT_STEPS.empty;
  else if (queue.length > 0) nextStep = BATCH_NEXT_STEPS.submit;
  else if (counts.blocked_no_prompt > 0) nextStep = BATCH_NEXT_STEPS.compile;
  else if (reconcileQueue.length > 0) nextStep = BATCH_NEXT_STEPS.wait;
  else if (fetchQueue.length > 0) nextStep = BATCH_NEXT_STEPS.fetch;
  else if (reviewQueue.length > 0) nextStep = BATCH_NEXT_STEPS.review;
  else if (retryQueue.length > 0) nextStep = BATCH_NEXT_STEPS.retry;
  return {
    schema_version: BATCH_SCHEMA_VERSION,
    rows: rows,
    counts: counts,
    queue: queue,
    reconcile_queue: reconcileQueue,
    fetch_queue: fetchQueue,
    retry_queue: retryQueue,
    review_queue: reviewQueue,
    started: started,
    settled: settled,
    all_succeeded: allSucceeded,
    next_step: nextStep,
  };
}

/** 进度一行文案（界面直接投影；词表在这里，不散落在各处）。 */
export function batchProgressText(state) {
  const counts = isPlainObject(state) ? state.counts : null;
  if (!isPlainObject(counts)) return "批次状态不可用。";
  const parts = [
    "共 " + counts.total + " 张",
    "已成功 " + counts.succeeded,
    "处理中 " + counts.active,
    "待提交 " + counts.ready,
  ];
  if (counts.failed > 0) parts.push("失败 " + counts.failed);
  if (counts.unknown > 0) parts.push("结果未知 " + counts.unknown);
  if (counts.unstored > 0) parts.push("待保存候选 " + counts.unstored);
  if (counts.blocked_no_prompt > 0) parts.push("待编译 Prompt " + counts.blocked_no_prompt);
  return parts.join(" · ") + "。";
}
