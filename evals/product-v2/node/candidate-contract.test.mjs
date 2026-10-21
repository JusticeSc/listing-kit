/**
 * V2.4.4 候选字节流契约测试（Node 原生进程，非 Mock）。
 *
 * 正向：PNG 宽高解析来自字节本身；候选身份 = 来源 action；记录检查；
 *       幂等判据（已有候选不再保存）；批次投影在提供 candidateStored 时多一个
 *       「已生成、待保存候选」状态与 fetch 队列，保存完成后回到 done。
 * 反向（故意让守卫变红）：非 PNG / 短字节 / 坏签名必须拒绝；未成功或缺 task_id 的
 *       Attempt 不能建候选；candidateStored 类型非法必须拒绝；不提供 candidateStored
 *       时必须与 V2.4.3 行为完全一致（没有 fetch 队列）。
 *
 * 直接运行：node --test evals/product-v2/node/
 */

import {
  BATCH_NEXT_STEPS,
  MAX_CANDIDATE_BYTES,
  buildCandidateRecord,
  buildDerivedCandidateRecord,
  buildReviewReport,
  candidateById,
  candidateForAttempt,
  candidateMatchesAttempt,
  candidateOriginOf,
  candidateSameGenerationContent,
  candidateStoreDecision,
  checkCandidateRecord,
  checkDerivedParentLink,
  deriveBatchState,
  batchProgressText,
  evaluateCandidateFindings,
  evaluateExportReadiness,
  parsePngDimensions,
  reviewIsCurrent,
} from "../../../build/frontend-node/app/product_v2/domain/index.js";
import { expect, expectCode, serializeError } from "./harness-core.mjs";

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
  const generated = { record: goodRecord(), version: 1 };
  const cropped = {
    record: { ...generated.record, candidate_id: "crop-main-0001", origin: "derived" },
    version: 2,
  };
  expect(candidateForAttempt([generated, cropped], SUCCEEDED.action_id) === generated,
    "同一来源 action 的裁剪派生不得替代模型原候选，造成重复取回或保存身份错配");
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
    schema_version: 2,
    execution_identity: {
      schema_version: 1,
      protocol: "v2.4.1", capability_version: 2,
      credential_reference: { source: "byok" }, sync: false,
    },
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

/* ------------------------------------------------- Issue #27 派生（v2）契约 */

const PARENT_SHA = "c".repeat(64);
const DERIVED_SHA = "d".repeat(64);
const CROP_AT = "2026-10-21T09:00:00+08:00";

/** 与 C06 同一父候选（v1 形状由本套件按需降级），供派生契约共用。 */
function parentRecord() {
  return goodRecord({ assetSha256: PARENT_SHA });
}

function derivationOf(parent, overrides = {}) {
  return {
    kind: "crop",
    parent_candidate_id: parent.candidate_id,
    parent_version: 1,
    parent_asset_sha256: parent.asset_sha256,
    source_width: parent.width,
    source_height: parent.height,
    rect: { x: 96, y: 96, width: 1152, height: 1152 },
    subject_bbox: { x: 241, y: 180, width: 900, height: 984 },
    algorithm: "white-background-square-v1",
    resample: "none",
    pixel_preserving: true,
    before_basis_points: 7321,
    after_basis_points: 8542,
    ...overrides,
  };
}

function derivedRecord(overrides = {}) {
  const parent = parentRecord();
  return buildDerivedCandidateRecord({
    candidateId: "crop-main-0001",
    parent: parent,
    parentVersion: 1,
    assetSha256: DERIVED_SHA,
    byteSize: 24,
    width: 1152,
    height: 1152,
    derivation: derivationOf(parent),
    at: CROP_AT,
    ...overrides,
  });
}

test("C11", "派生构造：独立 identity 复用父 action/task/sync，provider 置空，血缘冻结", async () => {
  const parent = parentRecord();
  const record = derivedRecord();
  expect(record.schema_version === 2, "派生必须是 schema 2");
  expect(record.origin === "derived", "派生必须显式声明 origin=derived");
  expect(record.candidate_id === "crop-main-0001"
    && record.candidate_id !== parent.candidate_id, "派生身份必须独立于父候选");
  expect(record.action_id === parent.action_id && record.task_id === parent.task_id,
    "派生必须复用父候选的原 action/task（复核与导出按此找父 Attempt）");
  expect(record.sync === parent.sync, "派生必须复用父候选的同步标记");
  expect(record.provider.provider_id === null && record.provider.model_id === null,
    "派生 provider 必须置空，不能冒充上游模型");
  expect(record.derivation.parent_candidate_id === parent.candidate_id
    && record.derivation.parent_asset_sha256 === parent.asset_sha256
    && record.derivation.rect.width === 1152, "血缘必须固定父身份与裁剪矩形");
  expect(Object.isFrozen(record) && Object.isFrozen(record.derivation)
    && Object.isFrozen(record.derivation.rect), "派生记录与其血缘必须冻结");
  expect(checkCandidateRecord(record).length === 0, "合法派生必须零问题");
  return { candidate_id: record.candidate_id };
});

test("C12", "反向：派生拒绝非法父/错误血缘/越界几何/超限字节，且不抛 TypeError", async () => {
  const parent = parentRecord();
  const base = { candidateId: "crop-main-0001", parent: parent, parentVersion: 1,
    assetSha256: DERIVED_SHA, byteSize: 24, width: 1152, height: 1152, at: CROP_AT };
  await expectCode(() => buildDerivedCandidateRecord({
    ...base, derivation: derivationOf(derivedRecord(), { parent_candidate_id: "crop-main-0001" }),
  }), "CONTRACT_INVALID", "派生不能以派生为父");
  await expectCode(() => buildDerivedCandidateRecord({ ...base, parentVersion: 0,
    derivation: derivationOf(parent) }), "CONTRACT_INVALID", "父版本必须是正整数");
  await expectCode(() => buildDerivedCandidateRecord({ ...base,
    derivation: derivationOf(parent, { algorithm: "nearest-neighbour" }) }),
  "CONTRACT_INVALID", "算法标识不符必须拒绝");
  await expectCode(() => buildDerivedCandidateRecord({ ...base,
    derivation: derivationOf(parent, { resample: "bilinear" }) }),
  "CONTRACT_INVALID", "有重采样的派生必须拒绝");
  await expectCode(() => buildDerivedCandidateRecord({ ...base,
    derivation: derivationOf(parent, { rect: { x: 200, y: 96, width: 1200, height: 1200 } }),
    width: 1200, height: 1200 }), "CONTRACT_INVALID", "裁剪矩形越界必须拒绝");
  await expectCode(() => buildDerivedCandidateRecord({ ...base,
    derivation: derivationOf(parent, { subject_bbox: { x: 1000, y: 180, width: 900, height: 984 } }) }),
  "CONTRACT_INVALID", "主体包围盒必须完整落在裁剪矩形内");
  await expectCode(() => buildDerivedCandidateRecord({ ...base,
    derivation: derivationOf(parent, { rect: "not-a-rect" }) }),
  "CONTRACT_INVALID", "rect 不是对象时必须给合同错误而不是 TypeError");
  await expectCode(() => buildDerivedCandidateRecord({ ...base,
    derivation: derivationOf(parent, { subject_bbox: null }) }),
  "CONTRACT_INVALID", "subject_bbox 缺失时必须给合同错误而不是 TypeError");
  await expectCode(() => buildDerivedCandidateRecord({ ...base, assetSha256: PARENT_SHA,
    derivation: derivationOf(parent) }), "CONTRACT_INVALID", "派生字节必须与父不同");
  await expectCode(() => buildDerivedCandidateRecord({ ...base, byteSize: MAX_CANDIDATE_BYTES + 1,
    derivation: derivationOf(parent) }), "CONTRACT_INVALID", "超过字节护栏必须拒绝");
  return { probed: 10 };
});

test("C13", "记录检查：v1/v2 生成与 v2 派生都合法；伪造父、假 provider、错误归属、越界都必须被抓住", async () => {
  const parent = parentRecord();
  const derived = derivedRecord();
  const v1 = { ...parent, schema_version: 1 };
  delete v1.origin;
  delete v1.derivation;
  expect(checkCandidateRecord(v1).length === 0, "schema 1 历史生成记录必须继续可读");
  expect(candidateOriginOf(v1) === "generation", "schema 1 历史记录读入即视为 generation");
  expect(checkCandidateRecord(parent).length === 0, "schema 2 生成候选必须零问题");
  expect(checkCandidateRecord(derived).length === 0, "schema 2 派生候选必须零问题");

  const outOfBounds = checkCandidateRecord({
    ...derived, derivation: { ...derived.derivation, rect: { x: 200, y: 96, width: 1200, height: 1200 } },
    width: 1200, height: 1200,
  });
  expect(outOfBounds.some((item) => item.path === "$.derivation.rect"),
    "越界裁剪矩形必须被报出");
  const fakeProvider = checkCandidateRecord({
    ...derived, provider: { provider_id: "dashscope-qwen-image", model_id: "qwen-image-3.0" },
  });
  expect(fakeProvider.some((item) => item.path === "$.provider"),
    "派生候选不能携带上游 provider 身份");
  const wrongOwner = checkCandidateRecord({ ...derived, candidate_id: parent.candidate_id });
  expect(wrongOwner.some((item) => item.path === "$.candidate_id"),
    "派生身份不能借用父候选 / 生成身份格式");
  const selfParent = checkCandidateRecord({ ...derived,
    derivation: { ...derived.derivation, parent_candidate_id: derived.candidate_id } });
  expect(selfParent.some((item) => item.path === "$.derivation.parent_candidate_id"),
    "父候选不能是派生自身");
  const v1Derived = checkCandidateRecord({ ...derived, schema_version: 1 });
  expect(v1Derived.some((item) => item.path === "$.schema_version"),
    "派生候选必须是 schema 2");
  const noProvider = checkCandidateRecord({ ...parent, provider: undefined });
  expect(noProvider.some((item) => item.path === "$.provider"),
    "缺少 provider 身份必须被报出（生成来自 Attempt，派生显式置空）");
  const tooLarge = checkCandidateRecord({ ...parent, byte_size: MAX_CANDIDATE_BYTES + 1 });
  expect(tooLarge.some((item) => item.path === "$.byte_size"),
    "超过 24MiB 护栏的候选必须被报出");
  const brokenRect = checkCandidateRecord({ ...derived, derivation: { ...derived.derivation, rect: "nope" } });
  expect(brokenRect.some((item) => item.path === "$.derivation.rect"),
    "rect 不是对象时必须报问题而不是抛 TypeError");
  return { probed: 11 };
});

test("C14", "父血缘判据：同 action/task/sync/sha/尺寸一致才成立，任一项错配都报精确路径", async () => {
  const parent = parentRecord();
  const derived = derivedRecord();
  expect(checkDerivedParentLink(derived, parent).length === 0, "合法派生对其父必须零问题");
  const cases = [
    [{ ...parent, task_id: "task-other" }, "$.task_id"],
    [{ ...parent, sync: true }, "$.sync"],
    [{ ...parent, action_id: "act-other" }, "$.action_id"],
    [{ ...parent, shot_id: "shot-other" }, "$.shot_id"],
    [{ ...parent, asset_sha256: "e".repeat(64) }, "$.derivation.parent_asset_sha256"],
    [{ ...parent, width: 1024 }, "$.derivation.source_width/height"],
    [{ ...parent, candidate_id: derived.candidate_id }, "$.derivation.parent_candidate_id"],
  ];
  for (const [tampered, path] of cases) {
    const problems = checkDerivedParentLink(derived, tampered);
    expect(problems.some((item) => item.path === path),
      "父候选 " + path + " 错配必须被抓住，实际 " + JSON.stringify(problems));
  }
  const wrongLineage = checkDerivedParentLink(derived, derivedRecord());
  expect(wrongLineage.length > 0, "派生不能以派生为父");
  return { probed: cases.length + 1 };
});

test("C15", "消费者身份：按 candidate_id 精确取派生、按 action 取原候选，派生仍能对上父 Attempt", async () => {
  const parent = parentRecord();
  const derived = derivedRecord();
  const chain = [{ record: parent, version: 1 }, { record: derived, version: 2 }];
  expect(candidateById(chain, derived.candidate_id).version === 2, "派生必须按自己的 id 找到");
  expect(candidateById(chain, parent.candidate_id).version === 1, "原候选必须按自己的 id 找到");
  expect(candidateById(chain, "crop-missing") === null, "不存在的派生必须返回 null");
  expect(candidateForAttempt(chain, parent.action_id) === chain[0],
    "幂等保存必须取回模型原候选，不让派生顶替");
  expect(candidateMatchesAttempt(derived, SUCCEEDED) === true,
    "派生复用父 action/task/sync，必须能对上原 Attempt（写库不等于来源不匹配）");
  expect(candidateMatchesAttempt(derived, { ...SUCCEEDED, task_id: "task-other" }) === false,
    "task 不符仍必须判不一致");
  const decision = candidateStoreDecision({ attempt: SUCCEEDED, candidates: chain });
  expect(decision.needed === false && decision.reason === "already_stored"
    && decision.candidate === chain[0], "已有原候选时派生不得触发再次取回/保存");
  return { probed: 7 };
});

test("C16", "按派生 ID 的复核与导出链：报告绑定派生字节，选择链经父 Attempt 判可导出", async () => {
  const derived = derivedRecord();
  const parent = parentRecord();
  const bytes = pngHead(1152, 1152);
  const findings = evaluateCandidateFindings({ candidate: derived, bytes: bytes, roleId: "main" });
  expect(findings.every((item) => item.severity !== "BLOCK"),
    "合法派生不得在单图检查里出现阻断：" + JSON.stringify(findings.filter((i) => i.severity === "BLOCK")));
  const report = buildReviewReport({ candidate: derived, findings: findings, at: "2026-10-21T09:05:00+08:00" });
  expect(reviewIsCurrent(report, derived) === true, "报告必须对派生候选当前有效");
  const base = {
    shots: [{ shot_id: "shot_main_clean", required: true }],
    selections: { shot_main_clean: derived.candidate_id },
    candidatesByShot: { shot_main_clean: [{ record: parent, version: 1 }, { record: derived, version: 2 }] },
    reportsByCandidate: { [derived.candidate_id]: report },
    attemptsByShot: { shot_main_clean: [{ record: SUCCEEDED, version: 1 }] },
  };
  const ready = evaluateExportReadiness(base);
  expect(ready.exportable === true,
    "派生被采用后必须能通过导出链检查：" + JSON.stringify(ready.findings.filter((i) => i.severity === "BLOCK")));
  const wrongAttempt = evaluateExportReadiness({
    ...base,
    attemptsByShot: { shot_main_clean: [{ record: { ...SUCCEEDED, task_id: "task-other" }, version: 1 }] },
  });
  expect(wrongAttempt.exportable === false
    && wrongAttempt.findings.some((item) => item.rule_id === "export.chain_integrity"
      && item.severity === "BLOCK"), "父 Attempt 错配必须阻断导出");
  const forgedParent = checkDerivedParentLink(derived, { ...parent, action_id: "act-other" });
  expect(forgedParent.length > 0, "伪造的父动作必须被交付前判据拒绝");
  return { probed: 5 };
});

test("C17", "生成候选幂等：v1 历史与重建的 v2 是同一原件（封装字段不构成内容变化）", async () => {
  const v2 = goodRecord({ assetSha256: PARENT_SHA });
  const v1 = { ...v2, schema_version: 1, created_at: "2026-09-30T11:00:00+08:00" };
  delete v1.origin;
  delete v1.derivation;
  const rebuilt = goodRecord({ assetSha256: PARENT_SHA, at: "2026-10-21T10:00:00+08:00" });
  expect(candidateSameGenerationContent(v1, rebuilt) === true,
    "同一 candidate_id/字节/尺寸/来源的 v1 与 v2 必须判为同一原件（不因新增 origin/null 冲突）");
  expect(candidateSameGenerationContent(rebuilt, v1) === true, "判据必须对称");
  expect(candidateSameGenerationContent(v1, goodRecord({ assetSha256: "e".repeat(64) })) === false,
    "字节身份不同必须判为不同内容");
  expect(candidateSameGenerationContent(v1, goodRecord({ assetSha256: PARENT_SHA, width: 1024 })) === false,
    "尺寸不同必须判为不同内容");
  const otherProvider = buildCandidateRecord({
    shotId: "shot_main_clean", attempt: { ...SUCCEEDED, provider: { provider_id: "other", model_id: "x" } },
    assetSha256: PARENT_SHA, byteSize: 2048, width: 1344, height: 1344, at: CROP_AT,
  });
  expect(candidateSameGenerationContent(v1, otherProvider) === false,
    "来源 provider 不同必须判为不同内容");
  expect(candidateSameGenerationContent(derivedRecord(), derivedRecord()) === false,
    "派生记录不走生成幂等判据");
  return { probed: 6 };
});

/* ---------------------------------------------------------------- 运行器 */

function render(results) {
  const node = document.getElementById("results");
  if (node) node.textContent = JSON.stringify(results, null, 2);
}


/* Node 原生运行器：与原浏览器版同一批 cases，断言不改写。 */
import nodeTest from "node:test";
for (const item of cases) {
  nodeTest(`${item.id} :: ${item.title}`, { timeout: 60000 }, async () => { await item.run(); });
}
