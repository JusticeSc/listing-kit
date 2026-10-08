import test from 'node:test';
import assert from 'node:assert/strict';
import { createGenerationModule } from '../../../app/product_v2/generation.js';
import { buildAttemptRecord, buildCandidateRecord, nextFromSubmitEnvelope, nextFromStatusEnvelope, CANDIDATE_DOCUMENT_KIND } from '../../../app/product_v2/domain/index.js';
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
  const store = new Map();
  const repository = {
    documents: {
      save: async (projectId, value) => {
        saved.push({ projectId, ...value });
        const key = projectId + "|" + value.kind + "|" + value.documentId;
        const list = store.get(key) || [];
        const version = list.length + 1;
        list.push({ document_id: value.documentId, payload: value.payload, version });
        store.set(key, list);
        return { version, payload: value.payload };
      },
      listLatest: async (projectId, kind) => [],
      listVersions: async (projectId, kind, documentId) => {
        const key = projectId + "|" + kind + "|" + documentId;
        return (store.get(key) || []).map((item) => ({ ...item }));
      },
      get: async () => null,
    },
    assets: { put: async (projectId, value) => ({ sha256: await sha256Hex(value.bytes),
      byte_size: value.bytes.byteLength }) },
  };
  repository.appendAttemptObservation = async ({ projectId, shotId, base, envelope }) => {
    const chain = store.get(projectId + "|generation_attempt|" + shotId);
    const original = chain.find(item => item.version === base.version && item.payload.action_id === base.actionId);
    assert.ok(original, 'observation must refer to the original stored action');
    const result = nextFromStatusEnvelope(original.payload, envelope, { at: '2026-10-05T10:00:02Z' });
    return repository.documents.save(projectId, { kind: 'generation_attempt', documentId: shotId, payload: result.record });
  };
  repository.saveCandidate = (projectId, shotId, candidate) =>
    repository.documents.save(projectId, { kind: CANDIDATE_DOCUMENT_KIND, documentId: shotId, payload: candidate });
  const beginAction = () => {
    const projectId = currentProject, epoch = generation;
    return { projectId, alive: () => projectId === currentProject && epoch === generation };
  };
  const module = createGenerationModule({ repository, beginAction,
    projectIdReader: () => currentProject, environmentReader: () => environment,
    requestHeaders: () => ({}), suitePlanReader: () => ({ shots: [{ shot_id: 'shot_main_clean', role_id: 'main' }] }),
    suiteSummaryReader: () => ({ shots: [] }), promptEntryReader: () => null,
    confirmationReader: () => null, promptBasisReader: () => null,
    fenceReader: () => ({ sources: [], projectionJson: '{"shots":[]}', assetSha256: [] }),
    referenceSourceReader: () => [],
    promptsSheet: () => null, imageEnvironment: () => null,
  });
  const seedAttempt = (projectId, actionId, taskId) => {
    const key = projectId + "|generation_attempt|shot_main_clean";
    const list = store.get(key) || [];
    list.push({ document_id: 'shot_main_clean', payload: submitted(actionId, taskId), version: list.length + 1 });
    store.set(key, list);
  };
  try {
    seedAttempt('project-A', 'action-project-A', 'task-A');
    await module.restore(beginAction());
    const a = module.reconcileAttempt('shot_main_clean');
    assert.equal(pending.length, 1);
    currentProject = 'project-B'; generation += 1; module.reset();
    seedAttempt('project-B', 'action-project-B', 'task-B');
    await module.restore(beginAction());
    const b = module.reconcileAttempt('shot_main_clean');
    assert.equal(pending.length, 2);
    pending[0].resolve(new Response(JSON.stringify({ ok: true, task: { provider,
      task_id: 'task-A', status: 'SUCCEEDED', result_count: 1, error: null,
      request_id: null, unknown: false } }), { status: 200 }));
    await a;
    assert.equal(module.isAttemptInFlight('shot_main_clean'), true,
      'A completion must not clear B flight guard');
    const candidates = saved.filter(x => x.kind === CANDIDATE_DOCUMENT_KIND && x.projectId === 'project-A');
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

test('old candidate cannot hide the current action result still needing retrieval', async () => {
  const succeeded = (actionId, taskId) => nextFromStatusEnvelope(submitted(actionId, taskId),
    { ok: true, unknown: false, task: { provider, task_id: taskId, status: 'SUCCEEDED',
      result_count: 1, error: null, request_id: null, unknown: false } },
    { at: '2026-10-05T10:00:02Z' }).record;
  const old = succeeded('action-older-result', 'task-older');
  const current = succeeded('action-current-result', 'task-current');
  const candidate = record => buildCandidateRecord({ shotId: 'shot_main_clean', attempt: record,
    assetSha256: 'c'.repeat(64), byteSize: png.byteLength, width: 1, height: 1,
    at: '2026-10-05T10:00:03Z' });
  const attempts = [
    { document_id: 'shot_main_clean', version: 1, payload: submitted('action-older-result', 'task-older') },
    { document_id: 'shot_main_clean', version: 2, payload: current },
    { document_id: 'shot_main_clean', version: 3, payload: old },
  ];
  const candidates = [{ document_id: 'shot_main_clean', version: 1, payload: candidate(old) }];
  const repository = { documents: {
    listLatest: async () => [],
    listVersions: async (_pid, kind) => kind === 'generation_attempt' ? attempts
      : kind === CANDIDATE_DOCUMENT_KIND ? candidates : [],
  } };
  const action = { projectId: 'project-result-recovery', alive: () => true };
  const module = createGenerationModule({ repository, beginAction: () => action,
    projectIdReader: () => action.projectId, environmentReader: () => environment,
    requestHeaders: () => ({}), suitePlanReader: () => ({ shots: [{ shot_id: 'shot_main_clean', role_id: 'main' }] }),
    suiteSummaryReader: () => ({ shots: [{ shot_id: 'shot_main_clean', label: '主图' }] }),
    promptEntryReader: () => null, confirmationReader: () => null, promptBasisReader: () => null,
    fenceReader: () => ({ sources: [], projectionJson: '{"shots":[]}', assetSha256: [] }),
    referenceSourceReader: () => [],
    promptsSheet: () => null, imageEnvironment: () => null,
  });
  await module.restore(action);
  assert.deepEqual(module.deriveBatch().fetch_queue, ['shot_main_clean'],
    'the late old result is not the current action byte asset');
  candidates.push({ document_id: 'shot_main_clean', version: 2, payload: candidate(current) });
  await module.restore(action);
  assert.deepEqual(module.deriveBatch().fetch_queue, [],
    'retrieval ends only after the current action candidate is stored');
});

function reworkCandidateEntry({ actionId, taskId, sha, version }) {
  const pending = submitted(actionId, taskId);
  const attempt = nextFromStatusEnvelope(pending,
    { ok: true, unknown: false, task: { provider, task_id: taskId, status: 'SUCCEEDED',
      result_count: 1, error: null, request_id: null, unknown: false } },
    { at: '2026-10-08T10:00:00Z' }).record;
  return { document_id: 'shot_main_clean', version, payload: buildCandidateRecord({
    shotId: 'shot_main_clean', attempt, assetSha256: sha, byteSize: png.byteLength,
    width: 1, height: 1, at: '2026-10-08T10:00:00Z',
  }) };
}

function reworkModuleHarness({ candidates, promptEntry, fence, seenProfile = null, compileCalls = null } = {}) {
  let currentProject = 'project-rework';
  let generation = 1;
  const saves = [];
  const prompts = new Map();
  const repository = {
    documents: {
      listLatest: async () => [],
      listVersions: async (_pid, kind, _doc) => kind === CANDIDATE_DOCUMENT_KIND ? candidates : [],
      save: async (projectId, input) => {
        if (input.kind === 'prompt_version') {
          const entry = prompts.get(input.documentId) || { version: 0, record: null };
          const version = entry.version + 1;
          prompts.set(input.documentId, { version, record: input.payload });
          saves.push({ projectId, kind: input.kind, documentId: input.documentId, version });
          return { version, payload: input.payload };
        }
        saves.push({ projectId, kind: input.kind, documentId: input.documentId });
        return { version: candidates.length + saves.length };
      },
      get: async () => null,
    },
    assets: { get: async () => null, put: async () => ({ sha256: '0'.repeat(64), byte_size: 1 }) },
    reserveGenerationAttempt: async () => { throw new Error('not covered by this consumer'); },
    appendAttemptObservation: async () => { throw new Error('not covered by this consumer'); },
    saveCandidate: async () => { throw new Error('not covered by this consumer'); },
  };
  const beginAction = () => {
    const projectId = currentProject, epoch = generation;
    return { projectId, generation: epoch, alive: () => projectId === currentProject && epoch === generation };
  };
  const profile = seenProfile || { provider_id: provider.provider_id, model_id: provider.model_id };
  const promptAbility = {
    compile: async (shotId, options = {}) => {
      compileCalls?.push({ shotId, directive: options.rework });
      return { payload: { hash: 'p'.repeat(64) }, compiled: { text: 'rework preview text' }, references: [{ sha256: 'r'.repeat(64) }] };
    },
    compileAndSave: async (shotId, options = {}) => {
      const saveInput = { kind: 'prompt_version', documentId: shotId, payload: { shot_id: shotId } };
      const saved = await repository.documents.save(options.action?.projectId || currentProject, saveInput);
      return { saved };
    },
  };
  const module = createGenerationModule({ repository, beginAction,
    projectIdReader: () => currentProject, environmentReader: () => environment,
    requestHeaders: () => ({}), suitePlanReader: () => ({ shots: [{ shot_id: 'shot_main_clean', role_id: 'main' }] }),
    suiteSummaryReader: () => ({ shots: [{ shot_id: 'shot_main_clean', label: '主图' }] }),
    promptEntryReader: (shotId) => prompts.get(shotId) || promptEntry,
    confirmationReader: () => null, promptBasisReader: () => null,
    fenceReader: () => fence, referenceSourceReader: () => [],
    promptsSheet: () => null, imageEnvironment: () => profile,
    promptAbility,
  });
  return { module, beginAction, saves, switchProject: () => { currentProject = 'project-other'; generation += 1; } };
}

test('prepareRework binds the explicit source candidate and freezes its seen inputs', async () => {
  const first = reworkCandidateEntry({ actionId: 'act-rework-a', taskId: 'task-rework-a', sha: 'd'.repeat(64), version: 3 });
  const promptEntry = { version: 7, record: { hash: 'h'.repeat(64), origin: 'system', compiled: {} } };
  const fence = { sources: [{ kind: 'suite_plan', documentId: 'suite', version: 2 }],
    projectionJson: '{"shot":"shot_main_clean"}', assetSha256: ['a'.repeat(64)] };
  const compileCalls = [];
  const { module, beginAction, saves } = reworkModuleHarness({ candidates: [first], promptEntry, fence, compileCalls });
  await module.restore(beginAction());
  const intent = await module.prepareRework({ shotId: 'shot_main_clean', candidateId: 'act-rework-a',
    problems: ['scene'], direction: '只把背景换成纯白，其余保持不变。' });
  assert.equal(intent.source.candidateId, 'act-rework-a');
  assert.equal(intent.source.assetSha256, 'd'.repeat(64));
  assert.equal(intent.source.version, 3);
  assert.equal(intent.directive.candidate_id, 'act-rework-a');
  assert.equal(intent.seenPromptVersion, 7);
  assert.equal(intent.preview.text, 'rework preview text');
  assert.equal(saves.length, 0);
  assert.equal(compileCalls.length, 1);
  assert.equal(compileCalls[0].directive.shot_id, 'shot_main_clean');
});

test('prepareRework rejects an explicit source that is no longer in the chain', async () => {
  const first = reworkCandidateEntry({ actionId: 'act-rework-a', taskId: 'task-rework-a', sha: 'd'.repeat(64), version: 3 });
  const promptEntry = { version: 7, record: { hash: 'h'.repeat(64), origin: 'system', compiled: {} } };
  const { module, beginAction } = reworkModuleHarness({ candidates: [first], promptEntry,
    fence: { sources: [], projectionJson: '{}', assetSha256: [] } });
  await module.restore(beginAction());
  await assert.rejects(() => module.prepareRework({ shotId: 'shot_main_clean', candidateId: 'cand-gone',
    problems: ['scene'], direction: '只把背景换成纯白，其余保持不变。' }), /已经不在/);
});

test('confirmRework refuses a session-switched intent without persistence or submission', async () => {
  const first = reworkCandidateEntry({ actionId: 'act-rework-a', taskId: 'task-rework-a', sha: 'd'.repeat(64), version: 3 });
  const promptEntry = { version: 7, record: { hash: 'h'.repeat(64), origin: 'system', compiled: {} } };
  const harness = reworkModuleHarness({ candidates: [first], promptEntry,
    fence: { sources: [], projectionJson: '{}', assetSha256: [] } });
  await harness.module.restore(harness.beginAction());
  const intent = await harness.module.prepareRework({ shotId: 'shot_main_clean', candidateId: 'act-rework-a',
    problems: ['scene'], direction: '只把背景换成纯白，其余保持不变。' });
  harness.switchProject();
  const result = await harness.module.confirmRework({ intent });
  assert.equal(result.stale, true);
  assert.equal(result.reason, 'stale_session');
  assert.equal(result.confirmation, undefined);
  assert.equal(harness.saves.length, 0);
});

test('confirmRework protects an advanced manual prompt instead of overwriting it', async () => {
  const first = reworkCandidateEntry({ actionId: 'act-rework-a', taskId: 'task-rework-a', sha: 'd'.repeat(64), version: 3 });
  const manual = { version: 8, record: { hash: 'm'.repeat(64), origin: 'manual_edit', compiled: { text: 'manual text' } } };
  const harness = reworkModuleHarness({ candidates: [first], promptEntry: manual,
    fence: { sources: [], projectionJson: '{}', assetSha256: [] } });
  await harness.module.restore(harness.beginAction());
  const intent = await harness.module.prepareRework({ shotId: 'shot_main_clean', candidateId: 'act-rework-a',
    problems: ['scene'], direction: '只把背景换成纯白，其余保持不变。' });
  const result = await harness.module.confirmRework({ intent });
  assert.equal(result.stale, true);
  assert.equal(result.reason, 'manual_edit');
  assert.equal(harness.saves.length, 0);
});
