import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";

import {
  buildSelectionRecord,
  deriveSelectionState,
  selectionCoversShot,
} from "../../../../app/product_v2/domain/selection.js";
import {
  ATTEMPT_UNKNOWN_FAMILY,
  canAttemptTransition,
  transportUnknownError,
} from "../../../../app/product_v2/domain/attempt.js";
import { parsePngHeader } from "../../../../app/product_v2/domain/candidate.js";
import { invalidationsFor } from "../../../../app/product_v2/domain/invalidation.js";
import { promptHash } from "../../../../app/product_v2/domain/prompt.js";
import { DOMAIN_ERROR_CODES } from "../../../../app/product_v2/domain/errors.js";

const BASE = "2026-09-30T04:00:00+08:00";
const LATER = "2026-09-30T04:30:00+08:00";
const SHOT = "shot_main_clean";
const SHA_A = "a".repeat(64);

function candidateFixture(overrides = {}) {
  return {
    candidate_id: "cand-main-001",
    shot_id: SHOT,
    asset_sha256: SHA_A,
    media_type: "image/png",
    width: 1600,
    height: 1600,
    attempt_action_id: "act-001",
    created_at: BASE,
    ...overrides,
  };
}

function selectFixture(overrides = {}) {
  return buildSelectionRecord({
    selectionId: "sel-001",
    action: "select",
    shotId: SHOT,
    candidate: candidateFixture(),
    candidateVersion: 1,
    at: BASE,
    ...overrides,
  });
}

test("selection: adoption is current, newer candidate stales it, clear stays cleared", () => {
  const record = selectFixture();
  assert.equal(deriveSelectionState(record, []), "current");
  assert.equal(
    deriveSelectionState(record, [{ record: { created_at: LATER } }]),
    "stale",
  );
  const covers = selectionCoversShot(record, [{ record: { created_at: LATER } }]);
  assert.equal(covers.state, "stale");
  assert.equal(covers.current, false);
  assert.equal(covers.candidate_id, "cand-main-001");

  const cleared = buildSelectionRecord({
    selectionId: "sel-002",
    action: "clear",
    shotId: SHOT,
    at: LATER,
  });
  assert.equal(deriveSelectionState(cleared, [{ record: { created_at: LATER } }]), "cleared");
});

test("selection: cross-shot candidate and unknown action are rejected", () => {
  assert.throws(
    () =>
      buildSelectionRecord({
        selectionId: "sel-x",
        action: "select",
        shotId: SHOT,
        candidate: candidateFixture({ shot_id: "shot_other" }),
        candidateVersion: 1,
        at: BASE,
      }),
    (error) => error.code === DOMAIN_ERROR_CODES.CONTRACT_INVALID,
  );
  assert.throws(
    () =>
      buildSelectionRecord({
        selectionId: "sel-x",
        action: "bogus",
        shotId: SHOT,
        at: BASE,
      }),
    (error) => error.code === DOMAIN_ERROR_CODES.CONTRACT_INVALID,
  );
});

test("attempt: submit vs query paths and terminal states", () => {
  assert.equal(canAttemptTransition("pending_submit", "submitted", "submit"), true);
  // submitted -> succeeded is a query conclusion, never a second submit (no duplicate submit).
  assert.equal(canAttemptTransition("submitted", "succeeded", "submit"), false);
  assert.equal(canAttemptTransition("submitted", "succeeded", "query"), true);
  assert.equal(canAttemptTransition("succeeded", "failed", "query"), false);
  // unknown never falls back to submitted (would be a blind resubmit).
  assert.equal(canAttemptTransition("unknown", "submitted", "query"), false);
  assert.equal(canAttemptTransition("unknown", "running", "query"), true);

  const unknown = transportUnknownError("no response");
  assert.equal(unknown.family, ATTEMPT_UNKNOWN_FAMILY);
  assert.equal(unknown.retry_policy, "requires_review");
});

test("candidate: real PNG header parses, truncated and magic failures rejected", () => {
  const png = Buffer.from([
    0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
    0, 0, 0, 13, 73, 72, 68, 82,
    0, 0, 0, 10, 0, 0, 0, 20, 8, 6, 0, 0, 0,
  ]);
  const header = parsePngHeader(png);
  assert.equal(header.width, 10);
  assert.equal(header.height, 20);
  assert.equal(header.color_type, 6);
  assert.equal(header.has_transparency, true);

  assert.throws(
    () => parsePngHeader(Buffer.from([1, 2, 3])),
    (error) => error.code === DOMAIN_ERROR_CODES.CONTRACT_INVALID,
  );
  assert.throws(
    () => parsePngHeader(Buffer.alloc(24, 0)),
    (error) => error.code === DOMAIN_ERROR_CODES.CONTRACT_INVALID,
  );
});

test("invalidation: shot-scoped change is precise, missing shotId rejected", () => {
  const result = invalidationsFor("shot_spec_changed", { shotId: "shot_1" });
  assert.equal(result.scope, "shot");
  assert.ok(result.invalidates.includes("selection"));
  assert.ok(result.preserves.includes("other_shots"));
  assert.ok(result.preserves.includes("project_history"));
  assert.ok(result.preserves.includes("candidate_blobs"));

  assert.throws(
    () => invalidationsFor("shot_spec_changed", {}),
    (error) => error.code === DOMAIN_ERROR_CODES.CONTRACT_INVALID,
  );
  assert.throws(
    () => invalidationsFor("no_such_kind", {}),
    (error) => error.code === DOMAIN_ERROR_CODES.CONTRACT_INVALID,
  );
});

test("promptHash: missing digest rejected, injected node digest is stable", async () => {
  await assert.rejects(
    () => promptHash({ prompt: "x" }, {}),
    (error) => error.code === DOMAIN_ERROR_CODES.CONTRACT_INVALID,
  );
  const digest = async (bytes) => createHash("sha256").update(bytes).digest("hex");
  const snapshot = { prompt: "x", size: "1344*1344" };
  const first = await promptHash(snapshot, { digest });
  const second = await promptHash(snapshot, { digest });
  assert.match(first, /^[0-9a-f]{64}$/);
  assert.equal(first, second);
});
