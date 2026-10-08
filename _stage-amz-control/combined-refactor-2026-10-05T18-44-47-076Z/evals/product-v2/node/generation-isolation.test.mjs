import test from 'node:test';
import assert from 'node:assert/strict';
import { createGenerationModule } from '../../../app/product_v2/generation.js';
import { buildAttemptRecord, nextFromSubmitEnvelope, CANDIDATE_DOCUMENT_KIND } from '../../../app/product_v2/domain/index.js';
import { sha256Hex } from '../../../app/product_v2/storage/db.js';

const provider = { provider_id: 'dashscope-qwen-image', model_id: 'qwen-image-3.0' };
const environment = { contract: 'v2.4.1', provider: { ...provider,
  capability_version: 2, credential_source: 'default', configured: true } };
const png = Uint8Array.from(Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jkXkAAAAASUVORK5CYII=', 'base64'));
function submitted(actionId, taskId) {
  const record = buildAttemptRecord({ actionId, shotId: 'shot_main_clean',
    prompt: { version: 1, hash: 'a'.repeat(64) }, references: [{ role: 'primary', sha256: 'b'.repeat(64) }],
    provider, parameters: { size: '1344*1344', n: 1, prompt_extend: false, watermark: false },
    executionIdentity: { protocol: 'v2.4.1', capabilityVersion: 2, credentialSource: 'default' },
    at: '2026-10-05T10:00:00Z' });
  return nextFromSubmitEnvelope(record, { ok: true, unknown: false,
    task: { provider, task_id: taskId, status: 'PENDING', result_count: 0,
      error: null, request_id: null, unknown: false } }, { at: '2026-10-05T10:00:01Z' }).record;
}

// 同一 Shot ID 在不同项目里合法重复。迟到结果必须保全原项目，不得读取新项目的链。
test('late task success saves original candidate without clearing new project flight', async () => {
  let currentProject = 'project-A';
  let generation = 1;
  const saved = [];
  const requests = [];
  const pending = [];
  const fetchBefore = globalThis.fetch;
  globalThis.fetch = async (url, options) => {
    const body = JSON.parse(options.body);
    requests.push({ url, body });
    if (url.endsWith('/status')) return new Promise(resolve => pending.push({ body, resolve }));
    if (url.endsWith('/result')) return new Response(png, { status: 200,
      headers: { 'content-type': 'image/png', 'x-image-sha256': await sha256Hex(png) } });
    throw new Error('unexpected request ' + url);
  };
  const repository = {
    documents: { save: async (projectId, value) => {
      saved.push({ projectId, ...value });
      return { version: saved.length, payload: value.payload };
    } },
    assets: { put: async (projectId, value) => ({ sha256: await sha256Hex(value.bytes),
      byte_size: value.bytes.byteLength }) },
  };
  const beginAction = () => {
    const projectId = currentProject, epoch = generation;
    return { projectId, alive: () => projectId === currentProject && epoch === generation };
  };
  const module = createGenerationModule({ repository, beginAction,
    projectIdReader: () => currentProject, environmentReader: () => environment,
    requestHeaders: () => ({}), suitePlanReader: () => ({ shots: [{ shot_id: 'shot_main_clean', role_id: 'main' }] }),
    suiteSummaryReader: () => ({ shots: [] }), promptEntryReader: () => null,
    confirmationReader: () => null, promptBasisReader: () => null, referenceSourceReader: () => [],
    reviewRequestBuilder: () => null, renderAttempts: () => {}, renderBatch: () => {},
    status: () => {}, attemptError: () => {}, clearAttemptError: () => {},
  });
  try {
    module.loadAttemptChain('shot_main_clean', [{ record: submitted('action-project-A', 'task-A'), version: 1 }]);
    const a = module.reconcileAttempt('shot_main_clean');
    assert.equal(pending.length, 1);
    currentProject = 'project-B'; generation += 1; module.reset();
    module.loadAttemptChain('shot_main_clean', [{ record: submitted('action-project-B', 'task-B'), version: 1 }]);
    const b = module.reconcileAttempt('shot_main_clean');
    assert.equal(pending.length, 2);
    pending[0].resolve(new Response(JSON.stringify({ ok: true, task: { provider,
      task_id: 'task-A', status: 'SUCCEEDED', result_count: 1, error: null,
      request_id: null, unknown: false } }), { status: 200 }));
    await a;
    assert.equal(module.isAttemptInFlight('shot_main_clean'), true,
      'A completion must not clear B flight guard');
    const candidates = saved.filter(x => x.kind === CANDIDATE_DOCUMENT_KIND && x.projectId === 'project-A');
    assert.equal(candidates.length, 1, 'A success must preserve candidate in original project');
    assert.equal(candidates[0].payload.action_id, 'action-project-A');
    assert.equal(candidates[0].payload.asset_sha256, await sha256Hex(png));
    assert.equal(saved.filter(x => x.projectId === 'project-B').length, 0,
      'A callback must not write any B records');
    assert.equal(requests.filter(x => x.url.endsWith('/result'))[0]?.body.task_id, 'task-A');
    pending[1].resolve(new Response(JSON.stringify({ ok: true, task: { provider,
      task_id: 'task-B', status: 'PENDING', result_count: 0, error: null,
      request_id: null, unknown: false } }), { status: 200 }));
    await b;
    assert.equal(module.isAttemptInFlight('shot_main_clean'), false);
  } finally {
    globalThis.fetch = fetchBefore;
    for (const p of pending) p.resolve(new Response('{}', { status: 200 }));
  }
});
