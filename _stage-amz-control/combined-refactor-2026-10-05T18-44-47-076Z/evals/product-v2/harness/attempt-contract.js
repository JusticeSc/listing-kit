/**
 * V2.4.2 生成 Attempt 契约测试（真实 Chromium，非 Mock）。
 *
 * 正向：提交前落库的形状、信封 → 状态映射、合法迁移、恢复判据、防重复、过期标记、append-only。
 * 反向（故意让守卫变红）：无任务身份的“成功”、非法迁移、篡改记录、Unknown 回到 submitted、
 * 无 task id 的核对、查询回退状态。
 *
 * 结果写到 window.__V2_ATTEMPT_RESULTS__，由 tools/verify_v2_4_2_generation_attempt.py 读取。
 */

import {
  ATTEMPT_ERROR_FAMILIES,
  ATTEMPT_CREDENTIAL_SOURCES,
  ATTEMPT_PROTOCOL_PATTERN,
  ATTEMPT_RECONCILE_MODES,
  ATTEMPT_RETRY_POLICIES,
  ATTEMPT_STATES,
  activeAttemptFor,
  advanceAttempt,
  attemptCurrentEnvironmentIdentity,
  attemptExecutionIdentityOf,
  attemptNeedsReconcile,
  attemptPromptStaleness,
  attemptReconcileBlockedMessage,
  attemptReconcileEnvironment,
  attemptReconcileMode,
  attemptReconcileRequestOf,
  attemptStateLabel,
  blockingAttemptFor,
  buildAttemptRecord,
  canAttemptTransition,
  candidateStoreDecision,
  checkAttemptRecord,
  classifyStatusEnvelope,
  classifySubmitEnvelope,
  latestAttemptFor,
  newActionId,
  nextFromStatusEnvelope,
  nextFromSubmitEnvelope,
} from "/domain/index.js";
import { expect, expectCode, serializeError } from "./harness-api.js";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

const AT = "2026-09-30T10:00:00+08:00";
const AT2 = "2026-09-30T10:00:05+08:00";
const AT3 = "2026-09-30T10:00:09+08:00";
const HASH_A = "a".repeat(64);
const HASH_B = "b".repeat(64);
const ACTION_A = "act-11111111-2222-3333-4444-555555555555";
const ACTION_B = "act-99999999-8888-7777-6666-555555555555";

function provider() {
  return { provider_id: "dashscope-qwen-image", model_id: "qwen-image-3.0" };
}

function parameters(overrides = {}) {
  return { size: "1344*1344", n: 1, prompt_extend: false, watermark: false, ...overrides };
}

function attemptFixture(overrides = {}) {
  return buildAttemptRecord({
    actionId: ACTION_A,
    shotId: "shot_main_clean",
    prompt: { version: 1, hash: HASH_A },
    references: [{ role: "primary", sha256: HASH_B }],
    provider: provider(),
    parameters: parameters(),
    executionIdentity: { protocol: "v2.4.1", capabilityVersion: 2, credentialSource: "default" },
    at: AT,
    note: "第一次生成",
    ...overrides,
  });
}

function taskEnvelope(overrides = {}) {
  return {
    ok: true,
    unknown: false,
    task: {
      provider: provider(),
      task_id: "task-abc-001",
      status: "RUNNING",
      result_count: 0,
      error: null,
      request_id: "req-001",
      unknown: false,
      ...(overrides.task || {}),
    },
    ...(overrides.envelope || {}),
  };
}

function failureEnvelope(family, code, retryPolicy, message = "上游失败。") {
  return {
    ok: false,
    unknown: family === "provider_unknown",
    error: { family, code, message, retry_policy: retryPolicy,
             http_status: null, request_id: null, details: null },
  };
}

test("A01", "创建必须是 pending_submit，并留下 user 迁移那一条", async () => {
  const record = attemptFixture();
  expect(record.state === ATTEMPT_STATES.pending_submit, "新建 Attempt 必须是 pending_submit");
  expect(record.task_id === null, "创建时不允许有 task_id");
  expect(record.change_log.length === 1 && record.change_log[0].via === "user",
    "创建必须留下 user 迁移");
  expect(record.change_log[0].from === null && record.change_log[0].to === "pending_submit",
    "第一条迁移必须是 null → pending_submit");
  expect(checkAttemptRecord(record).length === 0, "创建出来的记录必须自检通过");
  const frozen = JSON.stringify(record);
  expect(JSON.stringify(record) === frozen, "记录必须是纯数据，可序列化");
  return { state: record.state, action_id: record.action_id };
});

test("A02", "反向：缺字段 / 非法参考图 / 非法参数一律拒绝", async () => {
  const problems = [];
  const bad = [
    ["缺 action_id", { actionId: "" }],
    ["action_id 太短", { actionId: "abc" }],
    ["shot_id 非法", { shotId: "Main Shot" }],
    ["没有参考图", { references: [] }],
    ["参考图 4 张", { references: [1, 2, 3, 4].map(() => ({ role: "primary", sha256: HASH_B })) }],
    ["参考图角色不在词表", { references: [{ role: "hero", sha256: HASH_B }] }],
    ["参考图 sha 不合法", { references: [{ role: "primary", sha256: "zz" }] }],
    ["尺寸不合法", { parameters: parameters({ size: "1344x1344" }) }],
    ["n 越界", { parameters: parameters({ n: 0 }) }],
    ["prompt hash 不合法", { prompt: { version: 1, hash: "abc" } }],
    ["prompt 版本为 0", { prompt: { version: 0, hash: HASH_A } }],
    ["缺时间戳", { at: "" }],
  ];
  for (const [label, overrides] of bad) {
    const result = await expectCode(() => attemptFixture(overrides), "CONTRACT_INVALID", label);
    problems.push({ label, code: result.code });
  }
  expect(problems.length === bad.length, "每条非法输入都要被拒绝");
  return { rejected: problems.map((item) => item.label) };
});

test("A03", "提交信封 → 状态：受理 / 成功 / 失败 / 无法识别", async () => {
  const created = attemptFixture();
  const accepted = nextFromSubmitEnvelope(created, taskEnvelope(), { at: AT2 });
  expect(accepted.record.state === "submitted", "PENDING/RUNNING 必须落 submitted");
  expect(accepted.record.task_id === "task-abc-001", "必须保存 task_id");
  expect(accepted.record.request_id === "req-001", "必须保存 request_id");
  expect(accepted.record.error === null, "submitted 不允许带 error");
  const done = nextFromSubmitEnvelope(created,
    taskEnvelope({ task: { status: "SUCCEEDED", result_count: 1 } }), { at: AT2 });
  expect(done.record.state === "succeeded", "上游 SUCCEEDED 必须落 succeeded");
  const failed = nextFromSubmitEnvelope(created,
    taskEnvelope({ task: { status: "FAILED", error: "内容审核未通过" } }), { at: AT2 });
  expect(failed.record.state === "failed", "上游 FAILED 必须落 failed");
  expect(failed.record.error.family === "provider_failed", "失败要有 provider_failed 归口");
  expect(failed.record.error.message.includes("内容审核"), "失败原因要保留上游说明");
  const weird = nextFromSubmitEnvelope(created,
    taskEnvelope({ task: { status: "SOMETHING_NEW", task_id: "task-abc-002" } }), { at: AT2 });
  expect(weird.record.state === "unknown", "无法识别的任务状态必须落 unknown");
  expect(weird.record.error.retry_policy === "requires_review", "unknown 必须是 requires_review");
  return { accepted: accepted.record.state, done: done.record.state, failed: failed.record.state,
           weird: weird.record.state };
});

test("A04", "反向：没有任务编号的“成功”不许当成功", async () => {
  const created = attemptFixture();
  const noId = nextFromSubmitEnvelope(created,
    taskEnvelope({ task: { task_id: null, status: "SUCCEEDED" } }), { at: AT2 });
  expect(noId.record.state === "unknown", "缺少 task id 只能落 unknown");
  expect(noId.record.task_id === null, "不许伪造 task id");
  expect(noId.record.error.code === "TASK_ID_MISSING", "要留下 TASK_ID_MISSING");
  const emptyEnvelope = nextFromSubmitEnvelope(created, null, { at: AT2 });
  expect(emptyEnvelope.record.state === "unknown", "没有信封（连接中断）只能落 unknown");
  expect(emptyEnvelope.record.error.code === "SUBMIT_OUTCOME_UNKNOWN", "要留下可诊断的 code");
  return { missing: noId.record.error.code, transport: emptyEnvelope.record.error.code };
});

test("A05", "未提交的失败 vs 结果未知：input_rejected / 未配置 vs 5xx", async () => {
  const created = attemptFixture();
  const rejected = nextFromSubmitEnvelope(created,
    failureEnvelope("input_rejected", "INPUT_INVALID", "fatal", "字段不符合契约。"), { at: AT2 });
  expect(rejected.record.state === "failed", "请求被拒一定是 failed（没有提交到上游）");
  expect(rejected.record.task_id === null, "被拒的提交没有 task id");
  const notConfigured = nextFromSubmitEnvelope(created,
    failureEnvelope("internal", "PROVIDER_NOT_CONFIGURED", "fatal", "未配置密钥。"), { at: AT2 });
  expect(notConfigured.record.state === "failed", "未配置密钥是 failed，不是 unknown");
  const serverError = nextFromSubmitEnvelope(created,
    failureEnvelope("internal", "INTERNAL_ERROR", "fatal", "服务器内部错误。"), { at: AT2 });
  expect(serverError.record.state === "unknown", "本进程异常无法证明上游没受理，必须 unknown");
  expect(serverError.record.error.retry_policy === "requires_review", "unknown 必须 requires_review");
  const upstreamRejected = nextFromSubmitEnvelope(created,
    failureEnvelope("provider_failed", "PROVIDER_REJECTED", "retryable", "上游拒绝。"), { at: AT2 });
  expect(upstreamRejected.record.state === "failed", "上游明确拒绝是 failed");
  expect(upstreamRejected.record.error.retry_policy === "retryable", "重试语义要原样保留");
  return { rejected: rejected.record.state, not_configured: notConfigured.record.state,
           server_error: serverError.record.state, upstream: upstreamRejected.record.state };
});

test("A06", "合法迁移边逐个通过，非法边逐个被拒", async () => {
  const legal = [
    ["pending_submit", "submitted", "submit"],
    ["pending_submit", "failed", "submit"],
    ["pending_submit", "unknown", "submit"],
    ["pending_submit", "succeeded", "submit"],
    ["submitted", "running", "submit"],
    ["submitted", "succeeded", "query"],
    ["submitted", "failed", "query"],
    ["submitted", "unknown", "query"],
    ["running", "succeeded", "query"],
    ["running", "failed", "query"],
    ["running", "unknown", "query"],
    ["unknown", "running", "query"],
    ["unknown", "succeeded", "query"],
    ["unknown", "failed", "query"],
  ];
  for (const [from, to, via] of legal) {
    expect(canAttemptTransition(from, to, via), "应当允许：" + from + " → " + to + "（" + via + "）");
  }
  const illegal = [
    ["submitted", "pending_submit", "query"],
    ["running", "submitted", "query"],
    ["succeeded", "running", "query"],
    ["failed", "running", "query"],
    ["succeeded", "unknown", "query"],
    ["unknown", "submitted", "query"],
    ["unknown", "unknown", "query"],
    ["submitted", "succeeded", "submit"],
    ["running", "succeeded", "submit"],
    ["pending_submit", "running", "submit"],
    ["running", "submitted", "submit"],
  ];
  for (const [from, to, via] of illegal) {
    expect(!canAttemptTransition(from, to, via),
      "应当禁止：" + from + " → " + to + "（" + String(via) + "）");
  }
  expect(canAttemptTransition(null, "pending_submit", "user"), "创建边必须存在");
  expect(!canAttemptTransition(null, "submitted", "user"), "不能直接创建 submitted");
  return { legal: legal.length, illegal: illegal.length };
});

test("A07", "append-only：推进只追加，旧版本逐字保留", async () => {
  const created = attemptFixture();
  const snapshot = JSON.stringify(created);
  const submitted = nextFromSubmitEnvelope(created, taskEnvelope(), { at: AT2 }).record;
  expect(JSON.stringify(created) === snapshot, "推进不允许改到旧记录");
  expect(submitted.change_log.length === 2, "推进必须追加一条迁移");
  expect(submitted.change_log[0].to === "pending_submit" && submitted.change_log[1].to === "submitted",
    "迁移链要能读出完整历史");
  expect(submitted.created_at === created.created_at, "created_at 必须保持不变");
  expect(submitted.updated_at === AT2, "updated_at 必须等于最后一次迁移时间");
  expect(submitted.action_id === created.action_id, "同一次提交的 action_id 不许改");
  const running = nextFromStatusEnvelope(submitted,
    taskEnvelope({ task: { status: "RUNNING" } }), { at: AT3 }).record;
  expect(running.change_log.length === 3, "每次推进都追加版本");
  expect(running.state === "running", "查询 RUNNING 要推进到 running");
  expect(checkAttemptRecord(running).length === 0, "整条链必须始终自检通过");
  return { chain: running.change_log.map((item) => item.to) };
});

test("A08", "查询不回退、不空转：PENDING / 无响应 / 服务端故障都不推进", async () => {
  const submitted = nextFromSubmitEnvelope(attemptFixture(), taskEnvelope(), { at: AT2 }).record;
  const running = nextFromStatusEnvelope(submitted,
    taskEnvelope({ task: { status: "RUNNING" } }), { at: AT3 }).record;
  const back = nextFromStatusEnvelope(running,
    taskEnvelope({ task: { status: "PENDING" } }), { at: AT3 });
  expect(back.record === running, "上游回退到 PENDING 时记录必须原样不动");
  expect(back.outcome.advanced === false, "没有结论就不是推进");
  const offline = nextFromStatusEnvelope(running, null, { at: AT3 });
  expect(offline.record === running, "查询没有响应时记录必须原样不动");
  expect(offline.outcome.state === null, "无响应不能编造状态");
  const broken = nextFromStatusEnvelope(running,
    failureEnvelope("internal", "INTERNAL_ERROR", "fatal", "服务端故障。"), { at: AT3 });
  expect(broken.record === running, "服务端故障不能改写 Attempt");
  const same = nextFromStatusEnvelope(submitted,
    taskEnvelope({ task: { status: "PENDING" } }), { at: AT3 });
  expect(same.record === submitted, "同状态查询不产生新版本");
  return { back: back.outcome.note, offline: offline.outcome.note };
});

test("A09", "Unknown 恢复：有 task id 可核对，无 task id 只能显式新建", async () => {
  const created = attemptFixture();
  const withTask = nextFromStatusEnvelope(
    nextFromSubmitEnvelope(created, taskEnvelope(), { at: AT2 }).record,
    failureEnvelope("provider_unknown", "PROVIDER_STATUS_UNKNOWN", "requires_review"), { at: AT3 }).record;
  expect(withTask.state === "unknown", "查询未确认要落 unknown");
  expect(attemptReconcileMode(withTask) === ATTEMPT_RECONCILE_MODES.by_task, "有 task id 必须可核对");
  expect(attemptNeedsReconcile(withTask), "unknown 需要核对");
  const reconciled = nextFromStatusEnvelope(withTask,
    taskEnvelope({ task: { status: "SUCCEEDED", result_count: 1 } }), { at: AT3 });
  expect(reconciled.record.state === "succeeded", "核对发现成功就要落 succeeded");
  expect(reconciled.outcome.advanced === true, "核对成功属于推进");
  const noTask = nextFromSubmitEnvelope(created,
    failureEnvelope("provider_unknown", "PROVIDER_OUTCOME_UNKNOWN", "requires_review"), { at: AT2 }).record;
  expect(attemptReconcileMode(noTask) === ATTEMPT_RECONCILE_MODES.blocked_no_identity,
    "没有 task id 时必须说明无法核对");
  const blocked = await expectCode(() => advanceAttempt(noTask,
    { state: "succeeded", at: AT3, via: "query" }), "CONTRACT_TRANSITION_ILLEGAL",
    "没有 task id 的 Unknown 不许核对推进");
  expect(blocked.code === "CONTRACT_TRANSITION_ILLEGAL", "必须明确报非法迁移");
  const newAction = attemptFixture({ actionId: ACTION_B, at: AT3, note: "用户显式新建 action" });
  const chain = [noTask, newAction];
  expect(latestAttemptFor(chain, "shot_main_clean").action_id === ACTION_B, "最新 Attempt 是新建的那条");
  expect(noTask.state === "unknown" && noTask.change_log.length === 2, "旧记录必须原样保留");
  return { with_task: attemptReconcileMode(withTask), no_task: attemptReconcileMode(noTask),
           reconciled: reconciled.record.state };
});

test("A10", "防重复：进行中的 Attempt 阻止再次提交", async () => {
  const pending = attemptFixture();
  expect(blockingAttemptFor([pending], "shot_main_clean").state === "pending_submit",
    "pending_submit 必须拦住第二次提交");
  const submitted = nextFromSubmitEnvelope(pending, taskEnvelope(), { at: AT2 }).record;
  expect(activeAttemptFor([pending, submitted], "shot_main_clean").task_id === "task-abc-001",
    "submitted 必须拦住第二次提交");
  const running = nextFromStatusEnvelope(submitted,
    taskEnvelope({ task: { status: "RUNNING" } }), { at: AT3 }).record;
  expect(Boolean(activeAttemptFor([running], "shot_main_clean")), "running 必须拦住第二次提交");
  const done = nextFromStatusEnvelope(running,
    taskEnvelope({ task: { status: "SUCCEEDED" } }), { at: AT3 }).record;
  expect(blockingAttemptFor([done], "shot_main_clean") === null, "终态之后才允许新建 action");
  const failed = nextFromSubmitEnvelope(pending,
    failureEnvelope("provider_failed", "PROVIDER_REJECTED", "retryable"), { at: AT2 }).record;
  expect(blockingAttemptFor([failed], "shot_main_clean") === null, "明确失败之后允许用户重试");
  expect(activeAttemptFor([done], "shot_other") === null, "防重复必须按 Shot 隔离");
  return { pending: "blocked", running: "blocked", terminal: "open" };
});

test("A11", "过期标记：Prompt 前进后旧 Attempt 标「基于旧版本」", async () => {
  const record = attemptFixture();
  const same = attemptPromptStaleness(record, { version: 1, hash: HASH_A });
  expect(same.stale === false && same.reason_code === "CURRENT", "同一版本不算过期");
  const moved = attemptPromptStaleness(record, { version: 2, hash: "c".repeat(64) });
  expect(moved.stale === true && moved.reason_code === "PROMPT_MOVED", "版本前进必须标过期");
  expect(moved.current_version === 2 && moved.attempt_version === 1, "要能说清旧版本和新版本");
  const edited = attemptPromptStaleness(record, { version: 1, hash: "d".repeat(64) });
  expect(edited.stale === true, "同一版本号但文本变了（人工编辑）也算过期");
  const unknown = attemptPromptStaleness(record, null);
  expect(unknown.stale === false && unknown.reason_code === "CURRENT_PROMPT_UNKNOWN",
    "读不到当前 Prompt 时不许冒充过期");
  expect(attemptPromptStaleness(null, { version: 1, hash: HASH_A }) === null, "没有记录就没有结论");
  return { moved: moved.reason_code, edited: edited.reason_code };
});

test("A12", "反向：篡改记录、抹掉历史、Unknown 回写 submitted 都要被守卫抓住", async () => {
  const created = attemptFixture();
  const submitted = nextFromSubmitEnvelope(created, taskEnvelope(), { at: AT2 }).record;
  const unknown = nextFromStatusEnvelope(submitted,
    failureEnvelope("provider_unknown", "PROVIDER_STATUS_UNKNOWN", "requires_review"), { at: AT3 }).record;
  const clone = (value) => JSON.parse(JSON.stringify(value));
  const probes = [];

  const stateOnly = clone(submitted);
  stateOnly.state = "succeeded";
  probes.push(["只改 state 不改迁移链", stateOnly]);

  const noTask = clone(submitted);
  noTask.task_id = null;
  probes.push(["submitted 但没有 task id", noTask]);

  const badAction = clone(created);
  badAction.action_id = "x";
  probes.push(["action_id 非法", badAction]);

  const noHistory = clone(created);
  delete noHistory.change_log;
  probes.push(["删掉 change_log", noHistory]);

  const rewritten = clone(unknown);
  rewritten.state = "submitted";
  rewritten.task_id = null;
  rewritten.error = null;
  rewritten.change_log[rewritten.change_log.length - 1] = {
    at: AT3, via: "submit", from: "unknown", to: "submitted", note: "偷偷回写",
  };
  probes.push(["Unknown 偷偷回写成 submitted", rewritten]);

  const brokenChain = clone(submitted);
  brokenChain.change_log[1].from = null;
  probes.push(["迁移链断裂", brokenChain]);

  const noisySuccess = clone(created);
  noisySuccess.state = "succeeded";
  noisySuccess.change_log[0].to = "succeeded";
  noisySuccess.error = { family: "provider_failed", code: "X", message: "y", retry_policy: "fatal" };
  probes.push(["成功却带 error", noisySuccess]);

  const silentUnknown = clone(unknown);
  silentUnknown.error = null;
  probes.push(["unknown 没有原因", silentUnknown]);

  const failures = [];
  for (const [label, candidate] of probes) {
    const problems = checkAttemptRecord(candidate);
    if (problems.length === 0) failures.push(label);
  }
  expect(failures.length === 0, "这些篡改必须全部被拒绝，漏掉：" + failures.join(" / "));
  return { rejected: probes.map((item) => item[0]) };
});

test("A13", "词表与常量：错误归口、重试语义、状态文案、action id 形状", async () => {
  for (const state of Object.keys(ATTEMPT_STATES)) {
    expect(typeof attemptStateLabel(state) === "string" && attemptStateLabel(state).length > 0,
      "每个状态都要有给用户看的文案");
  }
  const id = newActionId(() => "11111111-2222-3333-4444-555555555555");
  expect(id.length >= 8 && id.length <= 64, "action id 长度必须在网关契约内");
  const envelope = classifySubmitEnvelope(taskEnvelope({ task: { status: "PENDING" } }));
  expect(envelope.state === "submitted" && envelope.task_id === "task-abc-001",
    "分类结果必须带任务身份");
  const status = classifyStatusEnvelope(taskEnvelope({ task: { status: "SUCCEEDED" } }));
  expect(status.state === "succeeded", "查询分类必须能给出 succeeded");
  const order = Object.keys(ATTEMPT_STATES);
  return { families: ATTEMPT_ERROR_FAMILIES.length, retry: ATTEMPT_RETRY_POLICIES.length, action_id: id };
});

/* ------------------------------------------------- V2.R4.4 冻结执行身份与环境核对 */

const DEFAULT_IDENTITY = {
  schema_version: 1, protocol: "v2.4.1", capability_version: 2,
  credential_reference: { source: "default" },
  sync: false,
};

function environmentIdentity(overrides = {}) {
  return {
    protocol: "v2.4.1",
    provider_id: "dashscope-qwen-image",
    model_id: "qwen-image-3.0",
    capability_version: 2,
    credential_source: "default",
    configured: true,
    sync: false,
    ...overrides,
  };
}

test("A14", "冻结执行身份：创建时刻写入，推进不改写，缺失或残缺一律拒绝", async () => {
  const record = attemptFixture();
  expect(JSON.stringify(record.execution_identity) === JSON.stringify(DEFAULT_IDENTITY),
    "新建 Attempt 必须冻结执行身份（协议/能力版本/凭据引用），实际 "
      + JSON.stringify(record.execution_identity));
  const advanced = nextFromSubmitEnvelope(record, taskEnvelope(), { at: AT2 }).record;
  expect(JSON.stringify(advanced.execution_identity) === JSON.stringify(DEFAULT_IDENTITY),
    "推进到 submitted 不得改写冻结身份");
  const reconciled = nextFromStatusEnvelope(advanced, taskEnvelope(
    { task: { status: "UNKNOWN" } }), { at: AT3 }).record;
  expect(JSON.stringify(reconciled.execution_identity) === JSON.stringify(DEFAULT_IDENTITY),
    "核对推进也不得改写冻结身份");
  const missing = await expectCode(
    () => attemptFixture({ executionIdentity: null }), "CONTRACT_INVALID", "缺执行身份");
  const brokenProtocol = await expectCode(
    () => attemptFixture({ executionIdentity: {
      protocol: "https://images.example.com", capabilityVersion: 2, credentialSource: "default" } }),
    "CONTRACT_INVALID", "协议版本必须是 v 契约号");
  const badSource = await expectCode(
    () => attemptFixture({ executionIdentity: {
      protocol: "v2.4.1", capabilityVersion: 2, credentialSource: "operator_giveaway" } }),
    "CONTRACT_INVALID", "凭据来源必须在词表内");
  return { missing: missing.code, protocol: brokenProtocol.code, source: badSource.code };
});

test("A15", "反向：环境身份漂移（协议/目标/模型/能力版本/凭据来源）必须阻塞核对", async () => {
  const record = attemptFixture({ taskId: "task-abc-001" });
  const same = attemptReconcileEnvironment(record, environmentIdentity());
  expect(same.mode === ATTEMPT_RECONCILE_MODES.by_task,
    "同目标同来源才允许按 task 核对，实际 " + same.mode);
  const drifts = [
    ["协议漂移", { protocol: "v2.4.2" }],
    ["provider 漂移", { provider_id: "volcengine-seedream" }],
    ["model 漂移", { model_id: "doubao-seedream-5-0-flash-260915" }],
    ["能力版本漂移", { capability_version: 3 }],
  ];
  for (const [label, patch] of drifts) {
    const gate = attemptReconcileEnvironment(record, environmentIdentity(patch));
    expect(gate.mode === ATTEMPT_RECONCILE_MODES.blocked_environment,
      label + " 必须阻塞核对，实际 " + gate.mode);
    expect(gate.reasons.includes("target_unavailable"), label + " 必须点名 target_unavailable");
  }
  const noEnv = attemptReconcileEnvironment(record, null);
  expect(noEnv.mode === ATTEMPT_RECONCILE_MODES.blocked_environment
    && noEnv.reasons.includes("target_unavailable"),
    "环境不可读必须按目标不可用阻塞，不猜身份");
  const rotated = attemptReconcileEnvironment(record, environmentIdentity({
    credential_source: "none" }));
  expect(rotated.mode === ATTEMPT_RECONCILE_MODES.blocked_environment
    && rotated.reasons.includes("credential_missing"),
    "凭据来源失配必须点名 credential_missing（默认档关闭后不再偷用当前配置查旧任务）");
  const unavailable = attemptReconcileEnvironment(record, environmentIdentity({ configured: false }));
  expect(unavailable.mode === ATTEMPT_RECONCILE_MODES.blocked_environment
    && unavailable.reasons.includes("credential_missing"),
    "身份相同但凭据不可用时不能核对");
  return { same: same.mode, drifts: drifts.length, unavailable: unavailable.mode };
});

test("A16", "反向：历史记录没有身份不补造、不映射，也不发目标核对请求", async () => {
  const legacy = JSON.parse(JSON.stringify(attemptFixture({ taskId: "task-abc-001" })));
  legacy.schema_version = 1;
  delete legacy.execution_identity;
  const gate = attemptReconcileEnvironment(legacy, environmentIdentity());
  expect(gate.mode === ATTEMPT_RECONCILE_MODES.blocked_no_identity
    && gate.reasons.includes("identity_unknown"),
    "历史记录必须按 blocked_no_identity 阻塞（不做 legacy 映射）");
  expect(attemptReconcileMode(legacy) === ATTEMPT_RECONCILE_MODES.blocked_no_identity,
    "词表模式也要把历史记录归为无身份");
  await expectCode(() => attemptReconcileRequestOf(legacy), "CONTRACT_INVALID",
    "历史记录不许构造目标核对请求");
  // 同 task 不同 target 不串：冻结身份在记录里，当前环境指向别处也不走新目标。
  const drifted = attemptReconcileEnvironment(
    attemptFixture({ taskId: "task-abc-001" }),
    environmentIdentity({ provider_id: "volcengine-seedream", credential_source: "byok" }));
  expect(drifted.mode !== ATTEMPT_RECONCILE_MODES.by_task,
    "换设置后已提交任务不许走新目标");
  return { legacy_reason: gate.reasons[0], drifted_mode: drifted.mode };
});

test("A17", "凭据轮换不使无关 Prompt 过期：过期判定只看 Prompt 版本与哈希", async () => {
  const base = attemptFixture();
  const rotated = attemptFixture({
    executionIdentity: {
      protocol: "v2.4.1", capabilityVersion: 2, credentialSource: "byok",
    },
  });
  expect(JSON.stringify(base.execution_identity.credential_reference) !== JSON.stringify(
    rotated.execution_identity.credential_reference), "两条记录只有凭据来源不同");
  const current = { version: 1, hash: HASH_A };
  expect(attemptPromptStaleness(base, current).stale === false,
    "同一 Prompt 版本 + 轮换凭据不产生过期");
  expect(attemptPromptStaleness(rotated, current).stale === false,
    "另一条凭据来源不同的记录同样不过期");
  const moved = { version: 2, hash: HASH_B };
  expect(attemptPromptStaleness(base, moved).stale === true
    && attemptPromptStaleness(rotated, moved).stale === true,
    "Prompt 真前进时仍然精确过期（与凭据无关）");
  expect(attemptPromptStaleness(base, moved).reason_code === "PROMPT_MOVED",
    "过期原因必须是 PROMPT_MOVED，不许把凭据变化冒充成 Prompt 变化");
  expect(JSON.stringify(base.prompt) === JSON.stringify(rotated.prompt),
    "两条记录的 prompt 块逐字一致（身份块不参与 prompt 事实）");
  return { moved: "PROMPT_MOVED", rotated: "CURRENT" };
});

test("A18", "环境身份投影与目标核对请求形状：blocked_environment 模式与无猜身份", async () => {
  expect(ATTEMPT_RECONCILE_MODES.blocked_environment === "blocked_environment",
    "词表必须包含 blocked_environment 模式");
  expect(ATTEMPT_CREDENTIAL_SOURCES.join(",") === "byok,default,none,test_double,env",
    "凭据来源词表：BYOK/默认档/未配置/测试替身/直构探针");
  expect(ATTEMPT_PROTOCOL_PATTERN.test("v2.4.1") === true, "协议版本形如 v2.4.1");
  expect(ATTEMPT_PROTOCOL_PATTERN.test("https://x") === false,
    "协议字段不许混入 URL（目标地址不是身份的一部分）");
  const block = {
    contract: "v2.4.1",
    provider: { provider_id: "dashscope-qwen-image", model_id: "qwen-image-3.0",
                capability_version: 2, configured: true, credential_source: "default",
                capabilities: {} },
  };
  expect(JSON.stringify(attemptCurrentEnvironmentIdentity(block))
    === JSON.stringify(environmentIdentity()),
    "环境身份投影必须来自 images 块的完整字段（异步块 sync=false）");
  const syncBlock = {
    contract: "v2.4.1",
    provider: { provider_id: "volcengine-ark", model_id: "doubao-seedream-5-0-flash-260915",
                capability_version: 3, configured: true, credential_source: "default",
                capabilities: { sync_tasks: true } },
  };
  expect(JSON.stringify(attemptCurrentEnvironmentIdentity(syncBlock))
    === JSON.stringify(environmentIdentity({
      provider_id: "volcengine-ark",
      model_id: "doubao-seedream-5-0-flash-260915",
      capability_version: 3,
      sync: true,
    })),
    "同步 provider 的能力块必须投影出 sync=true 身份（task_id 为空不再是理由）");
  expect(attemptCurrentEnvironmentIdentity(null) === null, "没有能力块就不猜身份");
  expect(attemptCurrentEnvironmentIdentity({ contract: "v2.4.1",
    provider: { provider_id: "dashscope-qwen-image", model_id: "qwen-image-3.0" } }) === null,
    "缺能力版本/凭据来源的身份必须被拒（不猜能力版本）");
  const withTask = attemptFixture({ taskId: "task-abc-001" });
  const request = attemptReconcileRequestOf(withTask);
  expect(request.task_id === "task-abc-001"
    && request.target.provider_id === "dashscope-qwen-image"
    && request.target.model_id === "qwen-image-3.0"
    && request.target.protocol === "v2.4.1"
    && request.target.capability_version === 2,
    "核对请求必须按冻结身份带 target（服务端再核对一次，同 task 不同 target 不串）");
  return { request_ok: true };
});

test("A19", "同步协议（V2.R5.2）：task_id 为空的同步成功可入库，非同步形状维持拒绝", async () => {
  const syncRecord = attemptFixture({
    executionIdentity: { protocol: "v2.4.1", capabilityVersion: 2,
      credentialSource: "default", sync: true },
  });
  const accepted = nextFromSubmitEnvelope(syncRecord, taskEnvelope({
    task: { task_id: null, sync: true, status: "SUCCEEDED", result_count: 1 },
  }), { at: AT2 });
  expect(accepted.record.state === ATTEMPT_STATES.succeeded,
    "同步协议的明确 SUCCEEDED 必须落 succeeded（无 task id 不是理由）");
  expect(accepted.record.task_id === null, "同步协议不许伪造 task id");
  expect(JSON.stringify(accepted.record.execution_identity) === JSON.stringify({
    schema_version: 1, protocol: "v2.4.1", capability_version: 2,
    credential_reference: { source: "default" }, sync: true,
  }), "同步记录的冻结身份必须显式携带 sync: true");
  const store = candidateStoreDecision({ attempt: accepted.record, candidates: [] });
  expect(store.needed === true, "同步成功记录允许建候选（冻结 sync 身份就是结果依据）");
  const asyncShape = attemptFixture();
  const refused = nextFromSubmitEnvelope(asyncShape,
    taskEnvelope({ task: { task_id: null, status: "SUCCEEDED" } }), { at: AT2 });
  expect(refused.record.state === ATTEMPT_STATES.unknown,
    "没有同步标志的 task_id 为空成功仍是 unknown（不许混入）");
  const nonSyncStore = candidateStoreDecision({ attempt: refused.record, candidates: [] });
  expect(nonSyncStore.needed === false,
    "非同步的无 task_id 成功仍拒绝建候选（这里一直是 unknown，理由本就不是入库问题）");
  const failedSync = nextFromSubmitEnvelope(syncRecord, taskEnvelope({
    task: { task_id: null, sync: true, status: "CANCELED" },
  }), { at: AT2 });
  expect(failedSync.record.state === ATTEMPT_STATES.failed
    && failedSync.record.error && failedSync.record.error.code === "SYNC_FAILED",
    "同步协议明确 CANCELED/FAILED 落 failed（provider_failed，无字节可存）");
  return { sync_ok: true, refused: refused.record.state, failed: failedSync.record.state };
});

/* ---------------------------------------------------------------- 运行器 */

function render(results) {
  const node = document.getElementById("results");
  if (node) node.textContent = JSON.stringify(results, null, 2);
}

async function runSuite() {
  const results = {
    suite: "v2.4.2-generation-attempt",
    status: "running",
    cases: [],
    started_at: new Date().toISOString(),
  };
  window.__V2_ATTEMPT_RESULTS__ = results;
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
    window.__V2_ATTEMPT_RESULTS__ = {
      suite: "v2.4.2-generation-attempt",
      status: "crashed",
      error: serializeError(error),
      cases: [],
    };
    render(window.__V2_ATTEMPT_RESULTS__);
  });
} else {
  window.__V2_ATTEMPT_RESULTS__ = { suite: "v2.4.2-generation-attempt", status: "skipped", cases: [] };
}
