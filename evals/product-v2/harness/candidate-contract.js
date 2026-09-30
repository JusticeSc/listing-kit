/**
 * V2.4.4 候选字节流契约测试（真实 Chromium，非 Mock）。
 *
 * 正向：PNG 宽高解析来自字节本身；候选身份 = 来源 action；记录检查；
 *       幂等判据（已有候选不再保存）；批次投影在提供 candidateStored 时多一个
 *       「已生成、待保存候选」状态与 fetch 队列，保存完成后回到 done。
 * 反向（故意让守卫变红）：非 PNG / 短字节 / 坏签名必须拒绝；未成功或缺 task_id 的
 *       Attempt 不能建候选；candidateStored 类型非法必须拒绝；不提供 candidateStored
 *       时必须与 V2.4.3 行为完全一致（没有 fetch 队列）。
 *
 * 结果写到 window.__V2_CANDIDATE_RESULTS__，由 tools/verify_v2_4_4_candidate_blob.py 读取。
 */

import {
  BATCH_NEXT_STEPS,
  buildCandidateRecord,
  candidateForAttempt,
  candidateMatchesAttempt,
  candidateStoreDecision,
  checkCandidateRecord,
  deriveBatchState,
  batchProgressText,
  parsePngDimensions,
} from "/domain/index.js";
import { expect, expectCode, serializeError } from "./harness-api.js";

const cases = [];

function test(id, title, run) {
  cases.push({ id, title, run });
}

function pngHead(width, height) {
  const bytes = new Uint8Array(24);
  bytes.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], 0);
  const view = new DataView(bytes.buffer);
  view.setUint32(8, 13);
  bytes.set([0x49, 0x48, 0x44, 0x52], 12);
  view.setUint32(16, width);
  view.setUint32(20, height);
  return bytes;
}

const SHA_A = "a".repeat(64);
const SUCCEEDED = Object.freeze({
  action_id: "act-succeeded-0001",
  shot_id: "shot_main_clean",
  state: "succeeded",
  task_id: "task-abc-123",
  provider: { provider_id: "dashscope-qwen-image", model_id: "qwen-image-3.0" },
});

function goodRecord(overrides = {}) {
  return buildCandidateRecord({
    shotId: "shot_main_clean",
    attempt: SUCCEEDED,
    assetSha256: SHA_A,
    byteSize: 2048,
    width: 1344,
    height: 1344,
    at: "2026-09-30T12:00:00+08:00",
    ...overrides,
  });
}

test("C01", "PNG 宽高解析：数值来自 IHDR 字节本身（Uint8Array / ArrayBuffer 都支持）", async () => {
  const first = parsePngDimensions(pngHead(1344, 1344));
  expect(first.width === 1344 && first.height === 1344, "必须解析出 1344×1344");
  const second = parsePngDimensions(pngHead(768, 1024).buffer);
  expect(second.width === 768 && second.height === 1024, "ArrayBuffer 输入必须同样可解析");
  return first;
});

test("C02", "反向：非 PNG / 短字节 / 坏签名 / 0 宽必须拒绝", async () => {
  await expectCode(() => parsePngDimensions(new Uint8Array(10)),
    "CONTRACT_INVALID", "短字节");
  const badMagic = pngHead(512, 512);
  badMagic[0] = 0x00;
  await expectCode(() => parsePngDimensions(badMagic), "CONTRACT_INVALID", "坏签名");
  const badChunk = pngHead(512, 512);
  badChunk[12] = 0x58;
  await expectCode(() => parsePngDimensions(badChunk), "CONTRACT_INVALID", "第一块不是 IHDR");
  await expectCode(() => parsePngDimensions(pngHead(0, 512)), "CONTRACT_INVALID", "0 宽");
  return { probed: 4 };
});

test("C03", "构造候选：身份 = 来源 action，provider 原样透传，记录冻结", async () => {
  const record = goodRecord();
  expect(record.candidate_id === SUCCEEDED.action_id, "candidate_id 必须等于来源 action_id");
  expect(record.action_id === record.candidate_id, "action_id 与 candidate_id 必须一致");
  expect(record.task_id === "task-abc-123", "来源 task_id 必须保留");
  expect(record.media_type === "image/png", "媒体类型必须是 image/png");
  expect(record.width === 1344 && record.height === 1344, "宽高必须原样写进记录");
  expect(record.provider.provider_id === "dashscope-qwen-image"
    && record.provider.model_id === "qwen-image-3.0", "provider 身份必须透传");
  expect(Object.isFrozen(record), "候选记录必须冻结（append-only）");
  return { candidate_id: record.candidate_id };
});

test("C04", "反向：未成功 / 缺 task_id / 坏 sha / 坏宽高 / 坏时间必须拒绝", async () => {
  await expectCode(() => goodRecord({ attempt: { ...SUCCEEDED, state: "failed" } }),
    "CONTRACT_INVALID", "failed 不能建候选");
  await expectCode(() => goodRecord({ attempt: { ...SUCCEEDED, task_id: null } }),
    "CONTRACT_INVALID", "缺 task_id 不能建候选");
  await expectCode(() => goodRecord({ assetSha256: "z".repeat(64) }),
    "CONTRACT_INVALID", "非十六进制 sha 必须拒绝");
  await expectCode(() => goodRecord({ width: 0 }), "CONTRACT_INVALID", "0 宽必须拒绝");
  await expectCode(() => goodRecord({ at: "not-a-time" }), "CONTRACT_INVALID", "坏时间必须拒绝");
  return { probed: 5 };
});

test("C05", "记录检查：合法零问题；篡改字段给出精确路径", async () => {
  const good = goodRecord();
  expect(checkCandidateRecord(good).length === 0, "合法记录必须零问题");
  const tamperedAction = checkCandidateRecord({ ...good, action_id: "act-other" });
  expect(tamperedAction.some((problem) => problem.path === "$.action_id"),
    "action_id 篡改必须被报出");
  const tamperedSha = checkCandidateRecord({ ...good, asset_sha256: "xy" });
  expect(tamperedSha.some((problem) => problem.path === "$.asset_sha256"),
    "sha256 篡改必须被报出");
  const tamperedMedia = checkCandidateRecord({ ...good, media_type: "image/jpeg" });
  expect(tamperedMedia.some((problem) => problem.path === "$.media_type"),
    "媒体类型篡改必须被报出");
  const tamperedDims = checkCandidateRecord({ ...good, width: 0 });
  expect(tamperedDims.some((problem) => problem.path === "$.width/height"),
    "宽高篡改必须被报出");
  expect(checkCandidateRecord(null).length === 1, "非对象必须报问题而不是崩溃");
  return { good_problems: 0 };
});

test("C06", "candidateForAttempt：从版本链按 action 找候选；找不到返回 null；裸记录也认", async () => {
  const chain = [
    { record: { action_id: "act-1" }, version: 1 },
    { record: { action_id: "act-2" }, version: 2 },
  ];
  expect(candidateForAttempt(chain, "act-1").version === 1, "必须找到第一条的候选");
  expect(candidateForAttempt(chain, "act-2").version === 2, "必须找到第二条的候选");
  expect(candidateForAttempt(chain, "act-3") === null, "不存在的 action 必须返回 null");
  expect(candidateForAttempt([{ action_id: "act-9" }], "act-9") !== null, "裸记录数组也要认");
  expect(candidateForAttempt(null, "act-1") === null, "非数组必须返回 null 而不是崩溃");
  return { probed: 5 };
});

test("C07", "candidateStoreDecision：未成功 / 缺编号 / 未保存 / 已保存四种投影", async () => {
  expect(candidateStoreDecision({ attempt: null }).needed === false, "没有 Attempt 不需要保存");
  expect(candidateStoreDecision({ attempt: { state: "running" } }).reason === "not_succeeded",
    "未成功不能保存候选");
  expect(candidateStoreDecision({
    attempt: { state: "succeeded", task_id: null },
  }).reason === "no_task_id", "缺 task_id 不能保存候选");
  const unstored = candidateStoreDecision({ attempt: SUCCEEDED, candidates: [] });
  expect(unstored.needed === true && unstored.reason === "unstored", "成功且无候选时必须待保存");
  const stored = candidateStoreDecision({
    attempt: SUCCEEDED,
    candidates: [{ record: { action_id: SUCCEEDED.action_id }, version: 1 }],
  });
  expect(stored.needed === false && stored.reason === "already_stored",
    "同一 action 已有候选必须幂等跳过");
  return { probed: 5 };
});

test("C08", "candidateMatchesAttempt：三个身份字段任一不符都必须判不一致", async () => {
  const record = goodRecord();
  expect(candidateMatchesAttempt(record, SUCCEEDED) === true, "一致时必须为 true");
  expect(candidateMatchesAttempt({ ...record, action_id: "act-other" }, SUCCEEDED) === false,
    "action 不符必须 false");
  expect(candidateMatchesAttempt({ ...record, task_id: "task-other" }, SUCCEEDED) === false,
    "task 不符必须 false");
  expect(candidateMatchesAttempt({ ...record, shot_id: "shot-other" }, SUCCEEDED) === false,
    "shot 不符必须 false");
  expect(candidateMatchesAttempt(null, SUCCEEDED) === false, "空候选必须 false");
  return { probed: 5 };
});

const SHOTS = [
  { shot_id: "shot_main_clean", label: "主图" },
  { shot_id: "shot_feature_scene", label: "卖点场景图" },
];

function batchAttempt(shotId, overrides = {}) {
  return {
    shot_id: shotId,
    action_id: "act-" + shotId,
    task_id: "task-" + shotId,
    state: "succeeded",
    ...overrides,
  };
}

test("C09", "批次候选投影：已成功未保存 → succeeded_unstored + fetch_queue + 下一步 fetch；保存后回到 done", async () => {
  const attempts = {
    shot_main_clean: batchAttempt("shot_main_clean"),
    shot_feature_scene: batchAttempt("shot_feature_scene"),
  };
  const partial = deriveBatchState({
    shots: SHOTS, latestAttempts: attempts, promptReady: () => true,
    candidateStored: (shotId) => shotId === "shot_feature_scene",
  });
  expect(partial.counts.succeeded === 1 && partial.counts.unstored === 1,
    "计数必须分开：已保存 1、待保存 1");
  expect(partial.fetch_queue.length === 1 && partial.fetch_queue[0] === "shot_main_clean",
    "待保存候选必须进 fetch 队列且保持套图顺序");
  expect(partial.next_step === BATCH_NEXT_STEPS.fetch, "下一步必须是 fetch");
  expect(partial.settled === false, "候选没保存完不算静置");
  expect(partial.rows[0].state === "succeeded_unstored" && partial.rows[0].candidate_stored === false,
    "未保存的行必须投影为 succeeded_unstored");
  expect(partial.rows[1].candidate_stored === true, "已保存的行必须标记 candidate_stored");
  const text = batchProgressText(partial);
  expect(text.includes("待保存候选 1"), "进度文案必须包含待保存候选计数：" + text);
  const done = deriveBatchState({
    shots: SHOTS, latestAttempts: attempts, promptReady: () => true,
    candidateStored: () => true,
  });
  expect(done.next_step === BATCH_NEXT_STEPS.done, "全部保存后下一步是 done");
  expect(done.all_succeeded === true && done.settled === true, "全部保存后必须同时是全部成功与静置");
  const waiting = deriveBatchState({
    shots: SHOTS,
    latestAttempts: {
      shot_main_clean: batchAttempt("shot_main_clean", { state: "running" }),
      shot_feature_scene: attempts.shot_feature_scene,
    },
    promptReady: () => true,
    candidateStored: () => false,
  });
  expect(waiting.next_step === BATCH_NEXT_STEPS.wait, "有在途记录时 fetch 不能抢到 wait 前面");
  const reviewFirst = deriveBatchState({
    shots: SHOTS,
    latestAttempts: {
      shot_main_clean: batchAttempt("shot_main_clean"),
      shot_feature_scene: {
        shot_id: "shot_feature_scene", action_id: "act-u", task_id: null, state: "unknown",
      },
    },
    promptReady: () => true,
    candidateStored: () => false,
  });
  expect(reviewFirst.next_step === BATCH_NEXT_STEPS.fetch,
    "fetch（可自动继续）必须先于人工 review");
  const retryAfter = deriveBatchState({
    shots: SHOTS,
    latestAttempts: {
      shot_main_clean: batchAttempt("shot_main_clean"),
      shot_feature_scene: batchAttempt("shot_feature_scene", { state: "failed" }),
    },
    promptReady: () => true,
    candidateStored: () => false,
  });
  expect(retryAfter.next_step === BATCH_NEXT_STEPS.fetch, "fetch 必须先于 retry 呈现");
  return { unstored: partial.counts.unstored, next_step: partial.next_step };
});

test("C10", "反向与向后兼容：candidateStored 类型非法必须拒绝；不提供时与 V2.4.3 完全一致", async () => {
  await expectCode(() => deriveBatchState({
    shots: SHOTS, latestAttempts: {}, promptReady: () => true, candidateStored: "yes",
  }), "CONTRACT_INVALID", "candidateStored 非函数必须拒绝");
  const legacy = deriveBatchState({
    shots: SHOTS,
    latestAttempts: {
      shot_main_clean: batchAttempt("shot_main_clean"),
      shot_feature_scene: batchAttempt("shot_feature_scene"),
    },
    promptReady: () => true,
  });
  expect(legacy.counts.succeeded === 2 && legacy.counts.unstored === 0,
    "不提供 candidateStored 时不得出现 unstored 计数");
  expect(legacy.fetch_queue.length === 0, "不提供 candidateStored 时 fetch 队列必须为空");
  expect(legacy.next_step === BATCH_NEXT_STEPS.done && legacy.settled === true,
    "不提供 candidateStored 时行为与 V2.4.3 一致");
  expect(legacy.rows.every((row) => row.candidate_stored === null),
    "不提供 candidateStored 时行投影必须是 null 而不是 false");
  return { probed: 4 };
});

/* ---------------------------------------------------------------- 运行器 */

function render(results) {
  const node = document.getElementById("results");
  if (node) node.textContent = JSON.stringify(results, null, 2);
}

async function runSuite() {
  const results = {
    suite: "v2.4.4-candidate-blob",
    status: "running",
    cases: [],
    started_at: new Date().toISOString(),
  };
  window.__V2_CANDIDATE_RESULTS__ = results;
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
    window.__V2_CANDIDATE_RESULTS__ = {
      suite: "v2.4.4-candidate-blob",
      status: "crashed",
      error: serializeError(error),
      cases: [],
    };
    render(window.__V2_CANDIDATE_RESULTS__);
  });
} else {
  window.__V2_CANDIDATE_RESULTS__ = { suite: "v2.4.4-candidate-blob", status: "skipped", cases: [] };
}
