import assert from "node:assert/strict";
import { createMockService, mockContract, MockDomainError } from "../../app/static/mock-service.js";

async function expectCode(promise, code) {
  await assert.rejects(promise, (error) => error instanceof MockDomainError && error.code === code);
}

async function reviewAndSelect(service, shotId, candidateId) {
  for (const factId of ["F4", "F7", "F8"]) {
    await service.reviewFact(shotId, candidateId, factId, "pass");
  }
  await service.reviewVisual(shotId, candidateId, "keep");
  await service.selectCandidate(shotId, candidateId);
}

async function normalTrace() {
  const service = createMockService({ latency: 0 });
  assert.equal(service.kind, "mock");
  for (const method of mockContract.requiredMethods) assert.equal(typeof service[method], "function", method);

  await service.loadExample();
  await service.createRecommendedPlan({
    name: "Aster 01 保温杯",
    sellingPoints: "高直筒；深青绿；三条水平筋",
    references: service.getState().product.references,
    referenceUrl: "https://example.invalid/brief",
    confirmed: true,
  });
  let state = service.getState();
  assert.equal(state.plan.status, "DRAFT");
  assert.equal(state.plan.shots.length, 4);

  await service.addShot();
  state = service.getState();
  assert.equal(state.plan.shots.length, 5);
  assert.equal(state.plan.shots.at(-1).required, false);
  await service.removeShot(state.plan.shots.at(-1).id);
  await expectCode(service.updateShot("S1", { direction: "   " }), "SHOT_DIRECTION_REQUIRED");
  await expectCode(service.updateShot("S1", { purpose: "  " }), "PURPOSE_REQUIRED");
  await service.updateShot("S1", { purpose: "验证方案调整真的进入状态", direction: "纯白背景、正面平视、留出安全边距", required: true });
  state = service.getState();
  {
    const s1 = state.plan.shots.find((shot) => shot.id === "S1");
    assert.equal(s1.direction, "纯白背景、正面平视、留出安全边距");
    assert.equal(s1.referenceView, "正面全身");
    assert.ok(s1.recommendedPrompt.includes("Operator scene direction"), "plan direction compiled into prompt");
    assert.equal(s1.promptVersions.length, 1, "plan edit recompiles one fresh default version");
    assert.ok(!("progress" in s1), "no fabricated per-shot progress field");
  }
  await service.moveShot("S2", "up");
  await service.moveShot("S2", "down");

  await service.generateSet();
  state = service.getState();
  assert.equal(state.plan.status, "READY");
  assert.ok(state.plan.shots.every((shot) => shot.status === "READY"));
  assert.deepEqual(state.plan.shots.find((shot) => shot.id === "S2").candidates.map((item) => item.id), ["F-01", "F-02"]);
  assert.ok(state.plan.shots.every((shot) => !("progress" in shot)), "per-shot fake percentage stays removed");

  await reviewAndSelect(service, "S1", "C-S1-01");
  const beforeEdit = service.getState();
  const s2Before = beforeEdit.plan.shots.find((shot) => shot.id === "S2");
  const otherCounts = Object.fromEntries(beforeEdit.plan.shots.filter((shot) => shot.id !== "S2").map((shot) => [shot.id, [shot.candidates.length, shot.attempts.length]]));
  const editedPrompt = `${s2Before.promptVersions.at(-1).text}\n\nMake the neutral wall slightly warmer while keeping no text and no handle on the exact same product.`;
  await service.focusShot("S2");
  await service.focusCandidate("F-02");
  await service.savePrompt("S2", editedPrompt);
  state = service.getState();
  assert.equal(state.plan.shots.find((shot) => shot.id === "S2").status, "STALE");
  assert.equal(state.plan.shots.find((shot) => shot.id === "S2").candidates.length, 2, "prompt edit preserves old candidates");
  assert.equal(state.plan.shots.find((shot) => shot.id === "S2").promptVersions.at(-1).originCandidateId, "F-02", "prompt version records which candidate it came from");
  await reviewAndSelect(service, "S2", "F-01");
  assert.equal(service.isCandidateCurrent("S2", "F-01"), false, "old candidate is bound to a previous prompt version");
  assert.equal(service.getDeliverySummary().validSelected, 1, "stale-bound selection does not count as a valid delivery");
  assert.ok(service.getExportBlockers().some((item) => item.includes("旧提示词版本")), "stale-bound selection must block export");
  await expectCode(service.exportDelivery(), "EXPORT_BLOCKED");
  await service.reworkShot("S2", "scene", "背景更暖，但仍然干净无道具");
  state = service.getState();
  const s2After = state.plan.shots.find((shot) => shot.id === "S2");
  assert.equal(s2After.candidates.length, 3);
  assert.equal(s2After.promptVersions.length, 3);
  assert.equal(s2After.candidates.at(-1).promptVersionId, s2After.promptVersions.at(-1).id);
  assert.equal(s2After.promptVersions.at(-1).originCandidateId, "F-01", "scene rework version records the candidate being reworked");
  assert.equal(service.getDeliverySummary().invalid.length, 1, "reworked shot keeps its stale selection until reselected");
  for (const shot of state.plan.shots.filter((shot) => shot.id !== "S2")) {
    assert.deepEqual([shot.candidates.length, shot.attempts.length], otherCounts[shot.id], `${shot.id} must not rerun`);
  }

  await reviewAndSelect(service, "S2", s2After.candidates.at(-1).id);
  assert.equal(service.isCandidateCurrent("S2", s2After.candidates.at(-1).id), true, "current-version candidate restores a valid selection");
  assert.equal(service.getDeliverySummary().invalid.length, 0);
  await reviewAndSelect(service, "S3", "C-S3-01");
  await reviewAndSelect(service, "S4", "C-S4-01");
  assert.deepEqual(service.getExportBlockers(), []);
  await service.exportDelivery();
  state = service.getState();
  assert.equal(state.task.phase, "EXPORTED");
  assert.equal(state.export.mode, "preview_only");
  assert.equal(state.export.files.length, 4);
  assert.ok(state.export.files.every((file) => file.promptVersionId));
  assert.equal(state.export.files.find((file) => file.shotId === "S2").candidateId, s2After.candidates.at(-1).id, "delivery binds the current-version candidate");
  return state;
}

async function partialAndUnknownTrace() {
  const service = createMockService({ latency: 0, scenario: "partial" });
  await service.loadExample();
  await service.createRecommendedPlan({ name: "Aster 01 保温杯", references: service.getState().product.references, sellingPoints: "演示", confirmed: true });
  await service.generateSet();
  let state = service.getState();
  assert.equal(state.plan.status, "PARTIAL");
  assert.equal(state.plan.shots.find((shot) => shot.id === "S1").status, "READY");
  assert.equal(state.plan.shots.find((shot) => shot.id === "S2").candidates.length, 2);
  assert.equal(state.plan.shots.find((shot) => shot.id === "S3").status, "FAILED");
  assert.equal(state.plan.shots.find((shot) => shot.id === "S4").status, "UNKNOWN");
  await expectCode(service.reworkShot("S4", "scene", "直接重试"), "RECONCILE_FIRST");
  await service.reconcileShot("S4");
  await service.reworkShot("S3", "scene", "重新给出清晰杯盖细节");
  await service.reworkShot("S4", "technical", "保持方图并确保底部完整");
  state = service.getState();
  assert.equal(state.plan.shots.find((shot) => shot.id === "S3").status, "READY");
  assert.equal(state.plan.shots.find((shot) => shot.id === "S4").status, "READY");
  assert.equal(state.plan.shots.find((shot) => shot.id === "S1").candidates.length, 1, "successful shot preserved");
  assert.equal(state.plan.shots.find((shot) => shot.id === "S2").candidates.length, 2, "successful shot preserved");

  const s1 = state.plan.shots.find((shot) => shot.id === "S1");
  await expectCode(service.savePrompt("S1", "make it blue"), "FACT_LOCK_BROKEN");
  assert.equal(service.getState().plan.shots.find((shot) => shot.id === "S1").promptVersions.length, s1.promptVersions.length);
  await expectCode(service.exportDelivery(), "EXPORT_BLOCKED");
  return service.getState();
}

async function resetDuringGenerateTrace() {
  const service = createMockService({ latency: 5 });
  await service.loadExample();
  await service.createRecommendedPlan({ name: "Aster 01 保温杯", references: service.getState().product.references, sellingPoints: "重置竞态", confirmed: true });
  const generating = service.generateSet();
  const resetting = service.reset();
  await Promise.allSettled([generating, resetting]);
  const state = service.getState();
  assert.equal(state.plan, null, "reset during generation must not leave an old plan behind");
  assert.equal(state.task.phase, "INPUT", "reset must win: the page returns to the initial stage");
  assert.equal(state.task.busy, false, "reset must not leave the task busy");
  assert.equal(state.task.operation, null, "reset must not leave an operation label behind");
  assert.equal(state.task.error, null, "reset must not surface the replaced generation as an error");
  return state;
}

const first = await normalTrace();
const second = await normalTrace();
assert.deepEqual(second, first, "same normal trace must be deterministic");
await partialAndUnknownTrace();
await resetDuringGenerateTrace();

console.log("mock workbench contract: passed — deterministic replay, plan direction compiled into prompt, prompt version traced to its source candidate, discrete states (no fabricated percentage), partial/Unknown preserved and isolated");
