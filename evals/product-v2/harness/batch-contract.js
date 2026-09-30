/**
 * V2.4.3 整套批次执行契约测试（真实 Chromium，非 Mock）。
 *
 * 正向：队列 = 套图顺序；计数与四个队列（提交 / 核对 / 重试 / 人工）；下一步优先级；
 *       系统性错误判定；未编译 Prompt 的投影；同输入同输出。
 * 反向（故意让守卫变红）：非法输入必须拒绝；没有任务编号的挂起/未知记录绝不允许
 *       进入提交或重试队列（不许自动重提）。
 *
 * 结果写到 window.__V2_BATCH_RESULTS__，由 tools/verify_v2_4_3_batch_execution.py 读取。
 */

import {
  BATCH_HALT_CODES,
  BATCH_NEXT_STEPS,
  BATCH_SHOT_STATES,
  BATCH_SHOT_STATE_LABELS,
  batchProgressText,
  batchSubmitHalts,
  deriveBatchState,
} from "/domain/index.js";
import { expect, expectCode, serializeError } from "./harness-api.js";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

const SHOTS = [
  { shot_id: "shot_main_clean", label: "主图" },
  { shot_id: "shot_feature_scene", label: "卖点场景图" },
  { shot_id: "shot_detail_macro", label: "细节图" },
];

function attempt(state, overrides = {}) {
  return {
    state: state,
    action_id: "act-11111111-2222-3333-4444-555555555555",
    task_id: null,
    ...overrides,
  };
}

function derive(latest, promptReady = () => true) {
  return deriveBatchState({
    shots: SHOTS,
    latestAttempts: latest || {},
    promptReady: promptReady,
  });
}

test("B01", "空批次：计数全零、下一步是 empty、没有任何队列", async () => {
  const state = deriveBatchState({ shots: [], latestAttempts: {}, promptReady: () => true });
  expect(state.counts.total === 0, "空批次的 total 必须是 0");
  expect(state.next_step === BATCH_NEXT_STEPS.empty, "空批次的下一步必须是 empty");
  expect(state.queue.length === 0 && state.retry_queue.length === 0
    && state.reconcile_queue.length === 0 && state.review_queue.length === 0,
    "空批次不允许有队列");
  expect(state.settled === true, "空批次视为已静置");
  expect(state.all_succeeded === false, "空批次不允许自称全部成功");
  expect(BATCH_HALT_CODES.length === 2, "停止码词表必须保持两条");
  return { next_step: state.next_step };
});

test("B02", "全部待提交：队列严格等于套图顺序，下一步是 submit", async () => {
  const state = derive({});
  expect(state.queue.join("|") === SHOTS.map((item) => item.shot_id).join("|"),
    "队列必须保持套图顺序");
  expect(state.counts.ready === 3 && state.counts.total === 3, "三张都应是待提交");
  expect(state.started === false, "还没有任何 Attempt 时 started 必须是 false");
  expect(state.next_step === BATCH_NEXT_STEPS.submit, "有队列时下一步必须是 submit");
  expect(state.rows.every((row) => row.state === BATCH_SHOT_STATES.ready), "每张图都投影为待提交");
  return { queue: state.queue };
});

test("B03", "没有 Prompt 的图投影为待编译，不进提交队列", async () => {
  const state = derive({}, (shotId) => shotId !== "shot_detail_macro");
  expect(state.queue.length === 2, "只有编译过 Prompt 的图可以提交");
  expect(!state.queue.includes("shot_detail_macro"), "未编译的图不许出现在提交队列");
  expect(state.counts.blocked_no_prompt === 1, "待编译 Prompt 必须计数");
  const onlyBlocked = deriveBatchState({
    shots: SHOTS,
    latestAttempts: {},
    promptReady: () => false,
  });
  expect(onlyBlocked.next_step === BATCH_NEXT_STEPS.compile, "没有待提交只剩待编译时下一步是 compile");
  expect(onlyBlocked.settled === false, "还有图没准备好时不允许视为已静置");
  return { blocked: state.counts.blocked_no_prompt, next_step: onlyBlocked.next_step };
});

test("B04", "混合状态：计数、四个队列与下一步优先级正确；无身份记录不许进提交/重试队列", async () => {
  const latest = {
    shot_main_clean: attempt("succeeded", { task_id: "task-ok-001" }),
    shot_feature_scene: attempt("failed", { task_id: null }),
    shot_detail_macro: attempt("pending_submit", { task_id: null }),
  };
  const state = derive(latest, (shotId) => shotId !== "shot_detail_macro");
  expect(state.counts.succeeded === 1 && state.counts.failed === 1
    && state.counts.active === 1 && state.counts.blocked_no_prompt === 0
    && state.counts.total === 3,
    "计数必须与输入一一对应（有记录的图按记录状态投影，不受 Prompt 就绪影响）");
  expect(state.retry_queue.length === 1 && state.retry_queue[0] === "shot_feature_scene",
    "只有明确失败的图进重试队列");
  expect(state.review_queue.length === 1 && state.review_queue[0] === "shot_detail_macro",
    "没有任务编号的挂起记录必须进人工队列");
  expect(state.queue.length === 0, "没有可提交的图时提交队列必须为空");
  expect(!state.queue.includes("shot_detail_macro") && !state.retry_queue.includes("shot_detail_macro"),
    "反向：没有任务编号的挂起记录绝不允许进入提交或重试队列（不许自动重提）");
  expect(state.next_step === BATCH_NEXT_STEPS.review, "没有待提交、没有待编译时先处理人工队列");
  const readyAdded = derive({ ...latest, shot_detail_macro: null },
    (shotId) => shotId !== "shot_detail_macro");
  expect(readyAdded.next_step === BATCH_NEXT_STEPS.compile, "没有可提交的图时下一步是 compile");
  const noReady = derive({
    shot_main_clean: attempt("succeeded"),
    shot_feature_scene: attempt("failed"),
    shot_detail_macro: attempt("submitted", { task_id: "task-run-002" }),
  });
  expect(noReady.next_step === BATCH_NEXT_STEPS.wait, "有可按任务核对的在途记录时下一步是 wait");
  expect(noReady.reconcile_queue.length === 1 && noReady.review_queue.length === 0,
    "有任务编号的在途记录必须进核对队列而不是人工队列");
  return { counts: noReady.counts, retry: state.retry_queue, review: state.review_queue };
});

test("B05", "未知与失败的下一步：有身份可核对则 wait；无身份则 review；只剩失败则 retry；全成功则 done", async () => {
  const single = (record) => deriveBatchState({
    shots: [SHOTS[0]],
    latestAttempts: record ? { [SHOTS[0].shot_id]: record } : {},
    promptReady: () => true,
  });
  const byTask = single(attempt("unknown", { task_id: "task-u-001" }));
  expect(byTask.next_step === BATCH_NEXT_STEPS.wait, "有任务编号的未知下一步是按任务核对");
  expect(byTask.review_queue.length === 0, "有任务编号的未知不需要人工强制处理");
  const noIdentity = single(attempt("unknown", { task_id: null }));
  expect(noIdentity.next_step === BATCH_NEXT_STEPS.review, "无身份未知下一步是人工处理");
  const failedOnly = single(attempt("failed"));
  expect(failedOnly.next_step === BATCH_NEXT_STEPS.retry, "只剩失败下一步是重试");
  const allDone = deriveBatchState({
    shots: SHOTS,
    latestAttempts: {
      shot_main_clean: attempt("succeeded"),
      shot_feature_scene: attempt("succeeded"),
      shot_detail_macro: attempt("succeeded"),
    },
    promptReady: () => true,
  });
  expect(allDone.next_step === BATCH_NEXT_STEPS.done, "全部成功下一步是 done");
  expect(allDone.all_succeeded === true && allDone.settled === true, "全部成功必须同时是已静置");
  expect(allDone.queue.length === 0 && allDone.retry_queue.length === 0, "全部成功不允许再有队列");
  return { by_task: byTask.next_step, no_identity: noIdentity.next_step,
           failed: failedOnly.next_step, done: allDone.next_step };
});

test("B06", "反向：非法输入一律以 CONTRACT_INVALID 拒绝", async () => {
  const bad = [
    ["shots 不是数组", () => deriveBatchState({ shots: "shots", latestAttempts: {}, promptReady: () => true })],
    ["shot 缺 shot_id", () => deriveBatchState({ shots: [{ label: "主图" }], latestAttempts: {}, promptReady: () => true })],
    ["shot 不是对象", () => deriveBatchState({ shots: ["shot_main_clean"], latestAttempts: {}, promptReady: () => true })],
    ["latestAttempts 不是对象", () => deriveBatchState({ shots: SHOTS, latestAttempts: [], promptReady: () => true })],
    ["promptReady 不是函数", () => deriveBatchState({ shots: SHOTS, latestAttempts: {}, promptReady: true })],
  ];
  const rejected = [];
  for (const [label, run] of bad) {
    const result = await expectCode(run, "CONTRACT_INVALID", label);
    rejected.push({ label, code: result.code });
  }
  expect(rejected.length === bad.length, "每条非法输入都要被拒绝");
  return { rejected: rejected.map((item) => item.label) };
});

test("B07", "停止判定：系统性错误停止批次；单张失败与上游 504 不停止", async () => {
  const halting = [
    ["SUBMIT_OUTCOME_UNKNOWN", { family: "provider_unknown", code: "SUBMIT_OUTCOME_UNKNOWN" }],
    ["RESPONSE_UNREADABLE", { family: "provider_unknown", code: "RESPONSE_UNREADABLE" }],
    ["INTERNAL_ERROR", { family: "internal", code: "INTERNAL_ERROR" }],
    ["PROVIDER_NOT_CONFIGURED", { family: "internal", code: "PROVIDER_NOT_CONFIGURED" }],
  ];
  for (const [label, error] of halting) {
    expect(batchSubmitHalts({ state: "unknown", error: error }), "必须停止：" + label);
  }
  const continuing = [
    ["上游 504 单张未知", { state: "unknown", error: { family: "provider_unknown", code: "PROVIDER_OUTCOME_UNKNOWN" } }],
    ["请求被拒", { state: "failed", error: { family: "input_rejected", code: "INPUT_INVALID" } }],
    ["上游明确失败", { state: "failed", error: { family: "provider_failed", code: "PROVIDER_FAILED" } }],
    ["已受理", { state: "submitted", error: null }],
    ["成功", { state: "succeeded", error: null }],
  ];
  for (const [label, outcome] of continuing) {
    expect(!batchSubmitHalts(outcome), "不许停止：" + label);
  }
  expect(!batchSubmitHalts(null) && !batchSubmitHalts({}), "空值不许停止批次");
  return { halting: halting.length, continuing: continuing.length };
});

test("B08", "确定性与顺序：输入键顺序打乱不影响输出；同输入两次推导逐字相同", async () => {
  const ordered = {
    shot_main_clean: attempt("succeeded"),
    shot_feature_scene: attempt("failed"),
    shot_detail_macro: attempt("running", { task_id: "task-r-003" }),
  };
  const shuffled = {
    shot_detail_macro: attempt("running", { task_id: "task-r-003" }),
    shot_main_clean: attempt("succeeded"),
    shot_feature_scene: attempt("failed"),
  };
  const first = derive(ordered);
  const second = derive(shuffled);
  expect(JSON.stringify(first) === JSON.stringify(second), "键顺序不许影响推导结果");
  expect(first.rows.map((row) => row.shot_id).join("|")
    === SHOTS.map((item) => item.shot_id).join("|"), "行的顺序必须等于套图顺序");
  const again = derive(ordered);
  expect(JSON.stringify(again) === JSON.stringify(first), "同输入必须逐字得到同输出");
  return { next_step: first.next_step, rows: first.rows.length };
});

test("B09", "行投影：Attempt 状态原样透出，标签缺省回退 shot_id，进度文案包含关键计数", async () => {
  const state = derive({
    shot_main_clean: attempt("running", { task_id: "task-r-009" }),
    shot_feature_scene: attempt("succeeded"),
    shot_detail_macro: attempt("unknown"),
  });
  const row = state.rows[0];
  expect(row.state === "running", "Attempt 状态必须原样透出");
  expect(row.task_id === "task-r-009" && row.reconcile_mode === "by_task", "任务编号与核对方式必须透出");
  const noLabel = deriveBatchState({
    shots: [{ shot_id: "shot_main_clean" }],
    latestAttempts: {},
    promptReady: () => true,
  });
  expect(noLabel.rows[0].label === "shot_main_clean", "标签缺省时回退 shot_id");
  const text = batchProgressText(state);
  expect(text.includes("共 3 张") && text.includes("已成功 1")
    && text.includes("处理中 1") && text.includes("结果未知 1"),
    "进度文案必须包含关键计数：" + text);
  expect(batchProgressText(null) === "批次状态不可用。", "空状态的文案必须稳定");
  expect(BATCH_SHOT_STATE_LABELS.ready === "待提交", "状态词表必须保持产品用语");
  return { text: text };
});

/* ---------------------------------------------------------------- 运行器 */

function render(results) {
  const node = document.getElementById("results");
  if (node) node.textContent = JSON.stringify(results, null, 2);
}

async function runSuite() {
  const results = {
    suite: "v2.4.3-batch-execution",
    status: "running",
    cases: [],
    started_at: new Date().toISOString(),
  };
  window.__V2_BATCH_RESULTS__ = results;
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
    window.__V2_BATCH_RESULTS__ = {
      suite: "v2.4.3-batch-execution",
      status: "crashed",
      error: serializeError(error),
      cases: [],
    };
    render(window.__V2_BATCH_RESULTS__);
  });
} else {
  window.__V2_BATCH_RESULTS__ = { suite: "v2.4.3-batch-execution", status: "skipped", cases: [] };
}
