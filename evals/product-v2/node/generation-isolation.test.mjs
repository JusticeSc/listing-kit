import test from 'node:test';
import assert from 'node:assert/strict';
import { createGenerationModule } from '../../../build/frontend-node/app/product_v2/generation.js';
import { ATTEMPT_DOCUMENT_KIND, buildAttemptRecord, buildCandidateRecord, buildReworkDirective, emptyShotSpecFromShot, nextFromSubmitEnvelope, nextFromStatusEnvelope, selectReferences, CANDIDATE_DOCUMENT_KIND } from '../../../build/frontend-node/app/product_v2/domain/index.js';
import { sha256Hex } from '../../../build/frontend-node/app/product_v2/storage/db.js';
import { CONFIRM_SCHEMA_VERSION } from '../../../build/frontend-node/app/product_v2/domain/index.js';
import { IMAGE_PRICING } from './harness-core.mjs';

const provider = { provider_id: 'dashscope-qwen-image', model_id: 'qwen-image-3.0' };
const environment = { contract: 'v2.4.1', provider: { ...provider,
  capability_version: 2, credential_source: 'default', configured: true } };
// 返工预览用的有效图像环境：协议 + 目标 + 完整请求 profile（与产品 workspace 同一注入形状）。
const REWORK_REQUEST_PROFILE = { size: '1344*1344', n: 1, prompt_extend: false, watermark: false,
  output_format: 'png', supports_negative_prompt_field: false, max_reference_images: 3,
  reference_media_types: ['image/png', 'image/jpeg'], min_side: 384, max_side: 2048,
  min_area: 512 * 512, max_area: 2048 * 2048, min_ratio: 1 / 8, max_ratio: 8, max_prompt_chars: 4000 };
const reworkEnvironment = { contract: 'v2.4.1', provider: { ...provider,
  capability_version: 1, credential_source: 'default', configured: true,
  capabilities: { request_profile: REWORK_REQUEST_PROFILE } },
  // 有效图像定价与服务端能力块同形状：预览费用按此逐图计，不猜其它模型或地区的价格。
  pricing: { ...IMAGE_PRICING } };
// 参考图来源投影 + 已保存商品资料版本（同一快照读出）；shotSpec 缺失=未决定，走默认依据。
const REFERENCE_SOURCES = [{ role: 'primary', sha256: 'a'.repeat(64) }];
const referenceSourceReader = () => REFERENCE_SOURCES.map((item) => ({ ...item }));
const intakeVersionReader = () => 1;
const shotSpecReader = () => null;
const png = Uint8Array.from(Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jkXkAAAAASUVORK5CYII=', 'base64'));
function submitted(actionId, taskId) {
  const record = buildAttemptRecord({ actionId, shotId: 'shot_main_clean',
    prompt: { version: 1, hash: 'a'.repeat(64) },
    references: [{ role: 'primary', sha256: 'b'.repeat(64), uses: ['product_truth'],
      sources: [{ kind: 'product_input', document_id: 'intake', version: 1, asset_sha256: 'b'.repeat(64) }] }],
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
    referenceSourceReader, intakeVersionReader, shotSpecReader,
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
    referenceSourceReader, intakeVersionReader, shotSpecReader,
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
  }), attempt };
}

/** 返工预览夹具冻结的预览 hash/正文：compile 与 compileAndSave 必须用同一份，
 *  否则落版后核对（hash/正文逐字）会判「不是本次预览」，测不到业务路径。 */
const PREVIEW_HASH = 'ab'.repeat(32);
const PREVIEW_TEXT = 'rework preview text';
/** 返工夹具默认的单条预览引用（既有用例按它断言；改动会连带多个契约）。 */
const DEFAULT_PREVIEW_REFERENCES = [{ role: 'primary', sha256: 'r'.repeat(64), uses: ['product_truth'],
  sources: [{ kind: 'product_input', document_id: 'intake', version: 1, asset_sha256: 'r'.repeat(64) }] }];
/** 与真实选择器同序的编辑模式预览引用（新用例注入，防止「冻结引用」与选择器漂移）。 */
const SEEN_REFERENCES = [
  { role: 'other', sha256: 'd'.repeat(64), uses: ['edit_source'],
    sources: [{ kind: 'candidate', document_id: 'shot_main_clean', version: 3, asset_sha256: 'd'.repeat(64) }] },
  { role: 'primary', sha256: 'a'.repeat(64), uses: ['product_truth'],
    sources: [{ kind: 'product_input', document_id: 'intake', version: 1, asset_sha256: 'a'.repeat(64) }] },
];

function reworkModuleHarness({ candidates, promptEntry, fence, compileCalls = null,
  previewReferences = DEFAULT_PREVIEW_REFERENCES, promptsSheet = () => null,
  imageEnvironment = () => reworkEnvironment } = {}) {
  let currentProject = 'project-rework';
  let generation = 1;
  const saves = [];
  const prompts = new Map();
  const attempts = candidates.map((entry) => ({
    document_id: entry.document_id, version: entry.version, payload: entry.attempt,
  }));
  const repository = {
    documents: {
      listLatest: async () => [],
      listVersions: async (_pid, kind, _doc) => kind === CANDIDATE_DOCUMENT_KIND ? candidates
        : kind === ATTEMPT_DOCUMENT_KIND ? [...attempts].sort((a, b) => b.version - a.version) : [],
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
    // 返工预览要读验将要发送的每一张参考图原字节：候选字节与商品原照都返回非空 Blob。
    assets: { get: async (_pid, _sha) => ({ blob: new Blob([png]), media_type: 'image/png',
      byte_size: png.byteLength }),
      put: async () => ({ sha256: '0'.repeat(64), byte_size: 1 }) },
    reserveGenerationAttempt: async () => { throw new Error('not covered by this consumer'); },
    appendAttemptObservation: async () => { throw new Error('not covered by this consumer'); },
    saveCandidate: async () => { throw new Error('not covered by this consumer'); },
  };
  const beginAction = () => {
    const projectId = currentProject, epoch = generation;
    return { projectId, generation: epoch, alive: () => projectId === currentProject && epoch === generation };
  };
  const previewState = { index: 0, hash: PREVIEW_HASH };
  const promptAbility = {
    compile: async (shotId, options = {}) => {
      compileCalls?.push({ shotId, directive: options.rework });
      // 每次预览都要产生「这一份」的具体字节：递增 hash 让重放与首份预览可区分，
      // 落版后的 hash/正文逐字核对才有可核对的真实差别。
      previewState.index += 1;
      previewState.hash = previewState.index === 1 ? PREVIEW_HASH
        : previewState.index.toString(16).padStart(2, '0').repeat(32);
      const references = typeof previewReferences === 'function'
        ? previewReferences(options.rework) : previewReferences;
      return { payload: { hash: previewState.hash }, compiled: { text: PREVIEW_TEXT },
        references: references.map((item) => ({ ...item, uses: [...item.uses],
          sources: item.sources.map((source) => ({ ...source })) })) };
    },
    compileAndSave: async (shotId, options = {}) => {
      const saveInput = { kind: 'prompt_version', documentId: shotId,
        payload: { shot_id: shotId, hash: previewState.hash, compiled: {
            text: PREVIEW_TEXT,
            rework: options.rework ? { directive_id: options.rework.directive_id,
              mode: options.rework.mode } : null },
          origin: 'system', basis: { rework: options.rework ? { ...options.rework } : null } } };
      const saved = await repository.documents.save(options.action?.projectId || currentProject, saveInput);
      return { saved };
    },
    rebaseManualForRework: async (shotId, options = {}) => {
      const saveInput = { kind: 'prompt_version', documentId: shotId,
        payload: { shot_id: shotId, hash: previewState.hash, compiled: {
            text: PREVIEW_TEXT,
            rework: options.rework ? { directive_id: options.rework.directive_id,
              mode: options.rework.mode } : null },
          origin: 'manual_edit', basis: { rework: options.rework ? { ...options.rework } : null } } };
      const saved = await repository.documents.save(options.action?.projectId || currentProject, saveInput);
      return { saved };
    },
    // 只读投影：与上面 compile 同形状，不落版（本次套件不测人工稿预览正文）。
    previewManualForRework: async (shotId, options = {}) => {
      const preview = await promptAbility.compile(shotId, options);
      return { payload: preview.payload, compiled: preview.compiled, references: preview.references };
    },
  };
  // 主图无 asset_role 依赖时走 primary 回退：来源只给 primary 原照。
  const shots = [{ shot_id: 'shot_main_clean', role_id: 'main' }];
  const module = createGenerationModule({ repository, beginAction,
    projectIdReader: () => currentProject, environmentReader: () => environment,
    requestHeaders: () => ({}), suitePlanReader: () => ({ shots }),
    suiteSummaryReader: () => ({ shots: [{ shot_id: 'shot_main_clean', label: '主图' }] }),
    promptEntryReader: (shotId) => prompts.get(shotId) || promptEntry,
    confirmationReader: () => null, promptBasisReader: () => null,
    fenceReader: () => fence, referenceSourceReader, intakeVersionReader, shotSpecReader,
    promptsSheet: (ids) => promptsSheet(ids), imageEnvironment,
    promptAbility,
  });
  return { module, beginAction, saves, previewState, prompts, attempts,
    switchProject: () => { currentProject = 'project-other'; generation += 1; } };
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
    mode: 'edit_candidate', problems: ['scene'], direction: '只把背景换成纯白，其余保持不变。' });
  assert.equal(intent.source.candidateId, 'act-rework-a');
  assert.equal(intent.source.assetSha256, 'd'.repeat(64));
  assert.equal(intent.source.version, 3);
  assert.equal(intent.directive.candidate_id, 'act-rework-a');
  assert.equal(intent.directive.mode, 'edit_candidate');
  assert.equal(intent.mode, 'edit_candidate');
  // 所见引用冻结自编译预览返回的引用列表（窄能力 compile 的输出）。
  assert.equal(intent.seenReferences.length, 1);
  assert.equal(intent.seenReferences[0].sha256, 'r'.repeat(64));
  assert.deepEqual(intent.seenReferences[0].uses, ['product_truth']);
  assert.equal(intent.seenPromptVersion, 7);
  assert.equal(intent.preview.text, 'rework preview text');
  assert.equal(saves.length, 0);
  assert.equal(compileCalls.length, 1);
  assert.equal(compileCalls[0].directive.shot_id, 'shot_main_clean');
});

test('prepareRework freezes the exact preview cost and regenerate carries fewer refs', async () => {
  const first = reworkCandidateEntry({ actionId: 'act-rework-a', taskId: 'task-rework-a', sha: 'd'.repeat(64), version: 3 });
  const promptEntry = { version: 7, record: { hash: 'h'.repeat(64), origin: 'system', compiled: {} } };
  const fence = { sources: [], projectionJson: '{}', assetSha256: [] };
  const { module, beginAction } = reworkModuleHarness({ candidates: [first], promptEntry, fence,
    previewReferences: (directive) => selectReferences({ shot_id: 'shot_main_clean', role_id: 'main' },
      REFERENCE_SOURCES, { maxReferences: 3, intakeVersion: 1, rework: directive }) });
  await module.restore(beginAction());
  // 编辑模式带候选编辑源 + 商品原照共两张实际引用：费用按逐图真实输入计。
  const edit = await module.prepareRework({ shotId: 'shot_main_clean', candidateId: 'act-rework-a',
    mode: 'edit_candidate', problems: ['scene'], direction: '只把背景换成纯白其余保持不变。' });
  assert.equal(edit.preview.references, SEEN_REFERENCES.length);
  assert.ok(edit.preview.cost && edit.preview.cost.upper_fen === 2 * SEEN_REFERENCES.length + 18,
    '编辑预览费用必须按实际引用数计：' + JSON.stringify(edit.preview.cost));
  assert.deepEqual(edit.preview.cost.pricing.provider_id, IMAGE_PRICING.provider_id);
  // 原照重画只发商品原照：同一报价下费用更低且仍然已核。
  const again = await module.prepareRework({ shotId: 'shot_main_clean', candidateId: 'act-rework-a',
    mode: 'regenerate_original', problems: ['scene'], direction: '按原资料重画。' });
  assert.equal(again.preview.references, DEFAULT_PREVIEW_REFERENCES.length);
  assert.ok(again.preview.cost && again.preview.cost.upper_fen === 2 * DEFAULT_PREVIEW_REFERENCES.length + 18,
    '重画预览费用必须按实际引用数计：' + JSON.stringify(again.preview.cost));
  assert.ok(again.preview.cost.upper_fen < edit.preview.cost.upper_fen, '两引用编辑必须贵于单引用重画');
});

test('confirmRework rejects a changed fee basis before any persistence', async () => {
  const first = reworkCandidateEntry({ actionId: 'act-rework-a', taskId: 'task-rework-a', sha: 'd'.repeat(64), version: 3 });
  const promptEntry = { version: 7, record: { hash: 'h'.repeat(64), origin: 'system', compiled: {} } };
  const fence = { sources: [], projectionJson: '{}', assetSha256: [] };
  const currentEnvironment = { ...reworkEnvironment, pricing: { ...IMAGE_PRICING } };
  const harness = reworkModuleHarness({ candidates: [first], promptEntry, fence,
    previewReferences: SEEN_REFERENCES, imageEnvironment: () => currentEnvironment });
  await harness.module.restore(harness.beginAction());
  const intent = await harness.module.prepareRework({ shotId: 'shot_main_clean', candidateId: 'act-rework-a',
    mode: 'edit_candidate', problems: ['scene'], direction: '只把背景换成纯白其余保持不变。' });
  currentEnvironment.pricing.output_image_fen += 1;
  const result = await harness.module.confirmRework({ intent });
  assert.equal(result.stale, true);
  assert.equal(result.reason, 'pricing_changed');
  assert.equal(harness.saves.length, 0);
});

test('confirmRework refuses a newly in-flight action before saving instead of blaming pricing', async () => {
  const first = reworkCandidateEntry({ actionId: 'act-rework-a', taskId: 'task-rework-a', sha: 'd'.repeat(64), version: 3 });
  const harness = reworkModuleHarness({ candidates: [first],
    promptEntry: { version: 7, record: { hash: 'h'.repeat(64), origin: 'system', compiled: {} } },
    fence: { sources: [], projectionJson: '{}', assetSha256: [] } });
  await harness.module.restore(harness.beginAction());
  const intent = await harness.module.prepareRework({ shotId: 'shot_main_clean', candidateId: 'act-rework-a',
    mode: 'edit_candidate', problems: ['scene'], direction: '只换背景。' });
  harness.attempts.push({ document_id: 'shot_main_clean', version: 4,
    payload: submitted('act-new-in-flight', 'task-new-in-flight') });
  await harness.module.restore(harness.beginAction());
  const result = await harness.module.confirmRework({ intent });
  assert.equal(result.stale, true);
  assert.equal(result.reason, 'submission_mode_blocked');
  assert.equal(harness.saves.length, 0);
});

test('prepareRework rejects an explicit source that is no longer in the chain', async () => {
  const first = reworkCandidateEntry({ actionId: 'act-rework-a', taskId: 'task-rework-a', sha: 'd'.repeat(64), version: 3 });
  const promptEntry = { version: 7, record: { hash: 'h'.repeat(64), origin: 'system', compiled: {} } };
  const { module, beginAction } = reworkModuleHarness({ candidates: [first], promptEntry,
    fence: { sources: [], projectionJson: '{}', assetSha256: [] } });
  await module.restore(beginAction());
  await assert.rejects(() => module.prepareRework({ shotId: 'shot_main_clean', candidateId: 'cand-gone',
    mode: 'edit_candidate', problems: ['scene'], direction: '只把背景换成纯白，其余保持不变。' }), /已经不在/);
});

test('confirmRework refuses a session-switched intent without persistence or submission', async () => {
  const first = reworkCandidateEntry({ actionId: 'act-rework-a', taskId: 'task-rework-a', sha: 'd'.repeat(64), version: 3 });
  const promptEntry = { version: 7, record: { hash: 'h'.repeat(64), origin: 'system', compiled: {} } };
  const harness = reworkModuleHarness({ candidates: [first], promptEntry,
    fence: { sources: [], projectionJson: '{}', assetSha256: [] } });
  await harness.module.restore(harness.beginAction());
  const intent = await harness.module.prepareRework({ shotId: 'shot_main_clean', candidateId: 'act-rework-a',
    mode: 'edit_candidate', problems: ['scene'], direction: '只把背景换成纯白，其余保持不变。' });
  harness.switchProject();
  const result = await harness.module.confirmRework({ intent });
  assert.equal(result.stale, true);
  assert.equal(result.reason, 'stale_session');
  assert.equal(result.confirmation, undefined);
  assert.equal(harness.saves.length, 0);
});

test('confirmRework refuses an intent whose frozen head is not this preview bytes', async () => {
  const first = reworkCandidateEntry({ actionId: 'act-rework-a', taskId: 'task-rework-a', sha: 'd'.repeat(64), version: 3 });
  const promptEntry = { version: 7, record: { hash: 'h'.repeat(64), origin: 'system', compiled: {} } };
  const candidates = [{ ...first, version: 3 }];
  const fence = { sources: [], projectionJson: '{}', assetSha256: [] };
  // 这张图的可提交摘要：确认/预约/执行路径要求同一份可提交清单；本用例只测预览字节同一性。
  const shotIds = ['shot_main_clean'];
  const sheet = {
    schema_version: CONFIRM_SCHEMA_VERSION,
    platform: { platform_id: 'amazon_us', version: 1, label: 'Amazon US' },
    provider: { provider_id: provider.provider_id, model_id: provider.model_id, version: 1,
      protocol: 'v2.4.1', size: '1344*1344', n: 1, prompt_extend: false, watermark: false,
      output_format: 'png' },
    total: 1, ready: 1, blocked: 0, can_submit: true, blockers: [], risks: [],
    shots: [],
    selection: { selected_shot_ids: ['shot_main_clean'], excluded: [] },
    external_summary: { model: provider.model_id, size: '1344*1344', n: 1, prompt_extend: false,
      watermark: false, output_format: 'png', reference_count: 2, reference_roles: ['other', 'primary'],
      prompt_chars: PREVIEW_TEXT.length, cost: { currency: 'CNY', upper_fen: 22,
        pricing: { ...IMAGE_PRICING }, per_shot: [{ shot_id: 'shot_main_clean', input_images: 2, upper_fen: 22 }],
        message: 'Two exact frozen inputs plus one output' } },
  };
  // 可提交摘要必须反映「当前已保存 Prompt」：否则确认会绑定旧版正文/哈希，
  // 重放场景测不到真实重编路径（首次确认后摘要仍停在 7 号版本）。
  const sheetNow = (ids) => {
    const head = harness.prompts.get('shot_main_clean')
      || { version: promptEntry.version, record: promptEntry.record };
    const shot = { shot_id: 'shot_main_clean', order: 1, label: '主图', role_id: 'main', role_label: '主图',
      intent: null, template_id: null, required: true, satisfied: true,
      prompt: { version: head.version, hash: head.record.hash, chars: PREVIEW_TEXT.length },
      references: SEEN_REFERENCES.map((ref) => ({ ...ref, sha256_prefix: ref.sha256.slice(0, 12) })),
      risks: [], blockers: [] };
    const list = ids === null || ids === undefined ? [shot] : [shot].filter((item) => ids.includes(item.shot_id));
    // 同一实际清单的逐图参考数与所选范围一起带：子集调用走同一 helper 保持新 validator 同口径。
    return { ...sheet, total: list.length, ready: list.length, can_submit: list.length > 0, shots: list,
      selection: { selected_shot_ids: list.map((item) => item.shot_id), excluded: [] } };
  };
  // 夹具预览引用必须与真实选择器输出逐项一致：否则 seenReferences 与提交时重算比较会在
  // 这里悄悄漂移，后面的断言就测不到真正想测的「预览字节同一性」。
  const directive = buildReworkDirective({ directiveId: 'rework-preview-identity', shotId: 'shot_main_clean',
    mode: 'edit_candidate',
    candidate: { candidate_id: first.payload.candidate_id, shot_id: 'shot_main_clean',
      asset_sha256: first.payload.asset_sha256, media_type: first.payload.media_type,
      width: 1, height: 1, attempt_action_id: first.payload.attempt_action_id, created_at: '2026-10-08T10:00:00Z' },
    candidateDocument: { document_id: 'shot_main_clean', version: 3 },
    problems: ['scene'], direction: '只把背景换成纯白，其余保持不变。', at: '2026-10-08T10:00:00Z' });
  assert.deepEqual(selectReferences({ shot_id: 'shot_main_clean', role_id: 'main' }, REFERENCE_SOURCES,
    { maxReferences: REWORK_REQUEST_PROFILE.max_reference_images, intakeVersion: 1,
      shotSpec: emptyShotSpecFromShot({ shot_id: 'shot_main_clean', role_id: 'main' }), rework: directive }),
  SEEN_REFERENCES, '夹具预览引用必须等于真实选择器输出');
  const harness = reworkModuleHarness({ candidates, promptEntry, fence, previewReferences: SEEN_REFERENCES,
    promptsSheet: sheetNow });
  await harness.module.restore(harness.beginAction());
  const intent = await harness.module.prepareRework({ shotId: 'shot_main_clean', candidateId: 'act-rework-a',
    mode: 'edit_candidate', problems: ['scene'], direction: '只把背景换成纯白，其余保持不变。',
    directiveId: 'rework-preview-identity' });
  assert.equal(intent.directive.directive_id, 'rework-preview-identity');
  assert.equal(intent.preview.hash, PREVIEW_HASH);
  assert.equal(intent.seenPromptVersion, 7);
  const firstResult = await harness.module.confirmRework({ intent });
  assert.equal(firstResult.promptVersion, 1, '第一次确认应落版一版返工 Prompt：' + JSON.stringify(firstResult));
  assert.equal(harness.saves.filter((row) => row.kind === 'prompt_version').length, 1);
  // 外部覆盖（同版本号、另一份字节）：预览后确认前 head 被改写。
  // 第一道核对（版本+所见哈希）必须判 prompt_changed，零新增版本、零外发。
  const firstBytes = { version: harness.prompts.get('shot_main_clean').version,
    record: harness.prompts.get('shot_main_clean').record };
  assert.equal(firstBytes.record.hash, PREVIEW_HASH, '前置：首次落版的字节就是第一份预览');
  const rewrittenBytes = { version: firstBytes.version, record: { ...firstBytes.record,
    hash: 'cd'.repeat(32), compiled: { text: 'rewritten elsewhere' } } };
  harness.prompts.set('shot_main_clean', rewrittenBytes);
  const replayIntent = await harness.module.prepareRework({ shotId: 'shot_main_clean', candidateId: 'act-rework-a',
    mode: 'edit_candidate', problems: ['scene'], direction: '只把背景换成纯白，其余保持不变。',
    directiveId: 'rework-preview-identity' });
  harness.prompts.set('shot_main_clean', firstBytes);
  const savesBefore = harness.saves.filter((row) => row.kind === 'prompt_version').length;
  const replay = await harness.module.confirmRework({ intent: replayIntent });
  assert.equal(replay.stale, true,
    '确认时 head 已被外部换成另一份字节时必须判过期：' + JSON.stringify(replay));
  assert.equal(replay.reason, 'prompt_changed');
  assert.equal(replay.confirmation, undefined);
  assert.equal(harness.saves.filter((row) => row.kind === 'prompt_version').length, savesBefore,
    '被判过期时不得追加 Prompt 版本');
  // 复现同一改法的再次预览（同 directive_id、同 seen 版本，但编译出的字节与 head 不同）：
  // 「同预览」必须按字节同一性判断。确认结果要么拒绝，要么绑定的 Prompt 就是本次预览的
  // 字节；绝不能因为 directive_id 命中就跳过落版、把旧 head 的字节当成已确认内容授权。
  const recheckIntent = await harness.module.prepareRework({ shotId: 'shot_main_clean', candidateId: 'act-rework-a',
    mode: 'edit_candidate', problems: ['scene'], direction: '只把背景换成纯白，其余保持不变。',
    directiveId: 'rework-preview-identity' });
  assert.notEqual(recheckIntent.preview.hash, PREVIEW_HASH,
    '前置：这次预览编译出的字节与首次落版的 head 不同');
  assert.equal(recheckIntent.directive.directive_id, 'rework-preview-identity',
    '前置：改法身份与 head 冻结的 directive 相同（旧判定会误判为「同预览」）');
  const savesBeforeReplay = harness.saves.filter((row) => row.kind === 'prompt_version').length;
  const recheck = await harness.module.confirmRework({ intent: recheckIntent });
  if (recheck.stale) {
    assert.equal(recheck.confirmation, undefined);
    assert.equal(harness.saves.filter((row) => row.kind === 'prompt_version').length, savesBeforeReplay,
      '被判过期时不得追加 Prompt 版本');
  } else {
    const bound = recheck.confirmation?.payload?.fingerprint?.snapshot?.shots?.[0];
    assert.ok(bound, '确认必须带可核对的冻结摘要：' + JSON.stringify(recheck));
    assert.equal(bound.prompt_hash, recheckIntent.preview.hash,
      '确认授权的 Prompt 必须是本次预览的字节，不能是旧 head 的字节：' + JSON.stringify(bound));
    assert.notEqual(bound.prompt_hash, PREVIEW_HASH,
      '本次预览不是首发字节：确认不得绑定首发字节');
    assert.equal(harness.saves.filter((row) => row.kind === 'prompt_version').length, savesBeforeReplay + 1,
      '按本次预览字节落版恰好一次');
  }
});

test('confirmRework protects an advanced manual prompt instead of overwriting it', async () => {
  const first = reworkCandidateEntry({ actionId: 'act-rework-a', taskId: 'task-rework-a', sha: 'd'.repeat(64), version: 3 });
  const manual = { version: 8, record: { hash: 'm'.repeat(64), origin: 'manual_edit', compiled: { text: 'manual text' } } };
  const harness = reworkModuleHarness({ candidates: [first], promptEntry: manual,
    fence: { sources: [], projectionJson: '{}', assetSha256: [] } });
  await harness.module.restore(harness.beginAction());
  const intent = await harness.module.prepareRework({ shotId: 'shot_main_clean', candidateId: 'act-rework-a',
    mode: 'edit_candidate', problems: ['scene'], direction: '只把背景换成纯白，其余保持不变。' });
  const result = await harness.module.confirmRework({ intent });
  assert.equal(result.stale, true);
  assert.equal(result.reason, 'manual_choice_missing');
  assert.equal(harness.saves.length, 0);
});

