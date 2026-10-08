/** Prompt 版本、编译、人工覆盖和确认单的业务所有权；浏览器只加载生成的 .js。 */
import {
  DOMAIN_DOCUMENT_KINDS, PLATFORM_PROFILES, assertConfirmationSheet, briefReadiness,
  buildConfirmationSheet, buildEditedPromptRecord, buildProductBrief, buildPromptRecord,
  canonicalJson, checkPromptRecord, compilePrompt, discardManualEdit, imagePromptProfile,
  promptHash, promptStaleness, reconfirmEditedPrompt, requestSnapshotOf, selectReferences,
  shotSignatureOf, suitePlanSummary,
} from "./domain/index.js";
import { sha256Hex } from "./storage/db.js";
import type { ProjectRepository, StoredDocumentRecord } from "./storage/validate.js";
import type { ActionSnapshot, PromptEntry } from "./generation.js";
import type {
  BriefBasisItem, CompiledPrompt, ImagePromptProfile, PromptRecord,
  PromptReferenceSelection, ReworkDirective, ShotSpec, SlotEntry, StyleSpec, SuitePlan,
} from "./domain/type-contracts.js";

/** 资料/事实/方案文档由 project-inputs（唯一所有者）提供；跨 Module 只传这一只读文档投影，不传闭包。 */
export type ProjectSources = {
  projectId: string | null;
  projectName: string;
  slots: SlotEntry[];
  suitePlan: SuitePlan | null;
  suiteVersion: number;
  styleSpec: StyleSpec;
  styleVersion: number;
  shotSpecs: Record<string, { spec: ShotSpec; version: number }>;
  references: PromptReferenceSelection[];
  sellingPoints: string[];
  /** 已提交商品资料文档版本（0=无文档）；参考图/卖点变化由它封印。 */
  intakeVersion: number;
};
export type PromptCurrentBasis = {
  briefBasis: BriefBasisItem[];
  shot_signature: string | null;
  suite_version: number | null;
  style_version: number | null;
  shot_spec_version: number | null;
  platform: { version: number };
  provider: ImagePromptProfile | null;
};
export type ConfirmationFix = { region: string; shot_id: string | null; label: string; action: string };
export type ConfirmationBlocker = { code: string; message: string; fix: ConfirmationFix };
export type ConfirmationRisk = { code: string; message: string; shot_id?: string; label?: string };
export type ConfirmationSheetShot = {
  shot_id: string; order: number; label: string; role_id: string | null; role_label: string | null;
  intent: string | null; template_id: string | null; required: boolean; satisfied: boolean;
  prompt: { version: number | null; hash: string | null; chars: number | null };
  references: { role: string; sha256_prefix: string }[];
  risks: ConfirmationRisk[]; blockers: ConfirmationBlocker[];
};
export type ConfirmationSheet = {
  schema_version: number; total: number; ready: number; blocked: number; can_submit: boolean;
  platform: { platform_id: string; version: number; label?: string };
  provider: Pick<ImagePromptProfile, "provider_id" | "model_id" | "version" | "protocol" | "size" | "n" | "prompt_extend" | "watermark" | "output_format">;
  external_summary: { model: string; size: string; n: number; prompt_extend: boolean; watermark: boolean;
    output_format: string; reference_count: number; reference_roles: string[]; prompt_chars: number;
    on_image_text_language?: string; statement: string };
  shots: ConfirmationSheetShot[]; scope_shot_ids?: string[];
  blockers: (ConfirmationBlocker & { shot_id: string; label: string; order: number })[];
  risks: ConfirmationRisk[];
};
export type CompiledPromptResult = {
  payload: PromptRecord; compiled: CompiledPrompt; references: PromptReferenceSelection[];
};
export type SavedPromptResult = CompiledPromptResult & { saved: StoredDocumentRecord<PromptRecord> };
export type PromptDraft = { text: string; reason: string };
export type PromptPreparation = { prepared: number; errors: string[]; reason?: "in_flight" | "no_project" | "no_plan" | "facts" | "configuration" | "unchanged" | "stale_session" };
export type PromptDependencies = {
  repository: ProjectRepository;
  beginAction(): ActionSnapshot;
  sources(): ProjectSources;
  imageEnvironment(): unknown;
};
export interface PromptModule {
  reset(): void;
  restore(action: ActionSnapshot): Promise<void>;
  entryOf(shotId: string | null, version?: number | null): PromptEntry | null;
  profile(environment?: unknown): ImagePromptProfile | null;
  basis(shotId: string | null, provider?: ImagePromptProfile | null, source?: ProjectSources): PromptCurrentBasis;
  sheet(shotIds?: string[] | null, provider?: ImagePromptProfile | null): ConfirmationSheet | null;
  compile(shotId: string, options?: { rework?: ReworkDirective; source?: ProjectSources }): Promise<CompiledPromptResult>;
  compileAndSave(shotId: string, options?: { action?: ActionSnapshot | null; rework?: ReworkDirective }): Promise<SavedPromptResult>;
  prepare(drafts: ReadonlyMap<string, PromptDraft>): Promise<PromptPreparation>;
  edit(shotId: string, text: string, reason: string, action?: ActionSnapshot): Promise<StoredDocumentRecord<PromptRecord>>;
  reconfirm(shotId: string, visibleText: string | null, action?: ActionSnapshot): Promise<StoredDocumentRecord<PromptRecord> | null>;
  discard(shotId: string, action?: ActionSnapshot): Promise<PromptRecord | null>;
  isPreparing(): boolean;
}

export function sourceContext(source: ProjectSources) {
  return {
    facts: source.slots.map(({ slot }) => ({ slot_id: slot.slot_id, status: slot.status, value: slot.value })),
    assets: source.references,
  };
}
/** 复核请求用已确认事实投影：只按服务端 FactItem 契约送 {label, value}；
 * slot_id/source 是本地溯源字段，服务端 extra=forbid 会 400（input_rejected，不调用模型）。
 * Prompt/简报侧的 ConfirmedFact（含 slot_id/source/value 原值）不受影响。 */
export function confirmedFacts(source: ProjectSources) {
  return source.slots.filter(({ slot }) => slot.status === "confirmed").slice(0, 20).map(({ slot }) => ({
    label: String(slot.label || slot.slot_id).slice(0, 60),
    value: (Array.isArray(slot.value) ? slot.value.join("；") : String(slot.value)).slice(0, 200),
  }));
}

/** 只读当前依据投影（沿用既有 R6.2 算法，不引入第二套 currentness 约定）：
 * 活动输入实例与“已读快照”消费者共用同一份实现，避免各自重算。 */
export function promptCurrentBasisOf(source: ProjectSources, shotId: string | null,
  provider: ImagePromptProfile | null): PromptCurrentBasis {
  let briefBasis: BriefBasisItem[] = [];
  try { briefBasis = buildProductBrief(source.slots).basis; } catch { /* 未就绪事实仍可投影缺项。 */ }
  const shot = source.suitePlan?.shots.find(item => item.shot_id === shotId);
  return {
    briefBasis, shot_signature: shot ? shotSignatureOf(shot) : null,
    suite_version: source.suiteVersion || null, style_version: source.styleVersion || null,
    shot_spec_version: shotId ? source.shotSpecs[shotId]?.version || null : null,
    platform: { version: PLATFORM_PROFILES.amazon_us.version }, provider,
  };
}

export function createPromptModule(deps: PromptDependencies): PromptModule {
  let versions = new Map<string, PromptEntry>();
  let history = new Map<string, Map<number, PromptEntry>>();
  let preparing: object | null = null;
  let lastPreparationInputs = "";

  function reset() {
    versions = new Map(); history = new Map(); preparing = null; lastPreparationInputs = "";
  }
  function remember(shotId: string, entry: PromptEntry) {
    let chain = history.get(shotId);
    if (!chain) { chain = new Map(); history.set(shotId, chain); }
    chain.set(entry.version, entry);
    if ((versions.get(shotId)?.version || 0) <= entry.version) versions.set(shotId, entry);
  }
  function entryOf(shotId: string | null, version?: number | null): PromptEntry | null {
    if (!shotId) return null;
    return (version ? history.get(shotId)?.get(version) : versions.get(shotId)) || null;
  }
  function profile(environment: unknown = deps.imageEnvironment()): ImagePromptProfile | null {
    try { return imagePromptProfile(environment); } catch { return null; }
  }
  function basis(shotId: string | null, provider: ImagePromptProfile | null = profile(), source = deps.sources()): PromptCurrentBasis {
    return promptCurrentBasisOf(source, shotId, provider);
  }
  function sheet(shotIds: string[] | null = null, provider: ImagePromptProfile | null = profile()) {
    const source = deps.sources();
    if (!source.suitePlan || !provider) return null;
    const currentBasisByShot: Record<string, PromptCurrentBasis> = {};
    for (const shot of source.suitePlan.shots) {
      if (shot.shot_id) currentBasisByShot[shot.shot_id] = basis(shot.shot_id, provider, source);
    }
    const result = buildConfirmationSheet({
      suitePlan: source.suitePlan, providerProfile: provider, context: sourceContext(source),
      promptEntries: [...versions].map(([shot_id, entry]) => ({ shot_id, ...entry })),
      currentBasisByShot, shotIds,
    });
    assertConfirmationSheet(result);
    return result as ConfirmationSheet;
  }
  async function compile(shotId: string, options: { rework?: ReworkDirective; source?: ProjectSources } = {}): Promise<CompiledPromptResult> {
    const source = options.source || deps.sources();
    const shot = source.suitePlan?.shots.find(item => item.shot_id === shotId);
    if (!shot) throw new Error("找不到这张图，可能已被删除。");
    const providerProfile = profile();
    if (!providerProfile) throw new Error("尚未取得有效图像能力，请恢复模型服务后再编译；不会猜测模型参数。");
    const spec = source.shotSpecs[shotId];
    const compiled = compilePrompt({
      brief: buildProductBrief(source.slots), shot, styleSpec: source.styleSpec,
      shotSpec: spec?.spec || null, context: sourceContext(source), providerProfile,
      versions: { suite_version: source.suiteVersion, style_version: source.styleVersion, shot_spec_version: spec?.version || null },
      ...(options.rework ? { rework: options.rework } : {}),
    });
    const references = selectReferences(shot, source.references, { maxReferences: providerProfile.max_reference_images });
    const snapshot = requestSnapshotOf(compiled, { references });
    const hash = await promptHash(snapshot, { digest: sha256Hex });
    const payload = buildPromptRecord({ compiled, snapshot, hash });
    const problems = checkPromptRecord(payload);
    if (problems.length) throw new Error(problems[0].message);
    return { payload, compiled, references };
  }
  async function save(shotId: string, payload: PromptRecord, action: ActionSnapshot, expectedVersion: number) {
    if (!action.projectId) throw new Error("缺少项目上下文，无法保存 Prompt 版本。");
    const saved = await deps.repository.documents.save(action.projectId, {
      kind: "prompt_version", documentId: shotId, payload, expectedVersion,
    });
    if (action.alive()) remember(shotId, { record: payload, version: saved.version });
    return saved;
  }
  async function compileAndSave(shotId: string, options: { action?: ActionSnapshot | null; rework?: ReworkDirective } = {}): Promise<SavedPromptResult> {
    const action = options.action || deps.beginAction();
    const previous = entryOf(shotId)?.version || 0;
    const result = await compile(shotId, options);
    const saved = await save(shotId, result.payload, action, previous);
    return { ...result, saved };
  }
  async function prepare(drafts: ReadonlyMap<string, PromptDraft>): Promise<PromptPreparation> {
    const action = deps.beginAction();
    if (!action.projectId) return { prepared: 0, errors: [], reason: "no_project" };
    if (preparing) return { prepared: 0, errors: [], reason: "in_flight" };
    const source = deps.sources();
    if (!source.suitePlan) return { prepared: 0, errors: [], reason: "no_plan" };
    if (!briefReadiness(buildProductBrief(source.slots)).ready) return { prepared: 0, errors: [], reason: "facts" };
    const provider = profile();
    if (!provider) return { prepared: 0, errors: [], reason: "configuration" };
    const summary = suitePlanSummary(source.suitePlan, sourceContext(source));
    const stamp = canonicalJson({ project_id: action.projectId, shots: summary.shots.map(item => ({
      id: item.shot_id, satisfied: item.satisfied, basis: basis(item.shot_id, provider, source),
      origin: entryOf(item.shot_id)?.record.origin || null,
    })) });
    if (stamp === lastPreparationInputs) return { prepared: 0, errors: [], reason: "unchanged" };
    const flight = {}; preparing = flight;
    let prepared = 0;
    const errors: string[] = [];
    try {
      for (const item of summary.shots) {
        if (!action.alive()) return { prepared, errors, reason: "stale_session" };
        if (!item.satisfied || !item.shot_id) continue;
        const entry = entryOf(item.shot_id), draft = drafts.get(item.shot_id);
        if (entry?.record.origin === "manual_edit" || (draft && entry && draft.text !== entry.record.compiled.text)) continue;
        if (entry && !promptStaleness(entry.record, basis(item.shot_id)).stale) continue;
        try { await compileAndSave(item.shot_id, { action }); prepared += 1; }
        catch (error) { errors.push(item.label + "：" + (error instanceof Error ? error.message : "本地准备失败")); }
      }
      if (action.alive() && !errors.length) lastPreparationInputs = stamp;
      return { prepared, errors };
    } finally { if (preparing === flight) preparing = null; }
  }
  async function edit(shotId: string, text: string, reason: string, action = deps.beginAction()) {
    const entry = entryOf(shotId);
    if (!entry) throw new Error("先编译并保存这张图的 Prompt，再编辑。");
    const source = deps.sources();
    const record = await buildEditedPromptRecord({
      base: entry.record, baseVersion: entry.version, text, reason, editedAt: new Date().toISOString(),
      context: { ...sourceContext(source), brief: buildProductBrief(source.slots) }, digest: sha256Hex,
    });
    return save(shotId, record, action, entry.version);
  }
  async function reconfirm(shotId: string, visibleText: string | null, action = deps.beginAction()) {
    const entry = entryOf(shotId);
    if (!entry || entry.record.origin !== "manual_edit") return null;
    if (visibleText !== null && visibleText !== entry.record.compiled.text) {
      throw new Error("此全文有未保存修改；先保存，再重新确认，不会确认另一份旧文本。");
    }
    const source = deps.sources();
    const current = await compile(shotId, { source });
    const record = await reconfirmEditedPrompt({
      base: entry.record, baseVersion: entry.version, reason: "用户按当前依据显式确认保留此人工全文",
      at: new Date().toISOString(), basis: current.compiled.basis, references: current.references,
      context: { facts: source.slots.map(entry => entry.slot), brief: buildProductBrief(source.slots), currentCompiled: current.compiled },
      digest: sha256Hex,
    });
    return save(shotId, record, action, entry.version);
  }
  async function discard(shotId: string, action = deps.beginAction()) {
    const entry = entryOf(shotId);
    if (!entry || entry.record.origin !== "manual_edit") return null;
    const discarded = discardManualEdit(entry.record, [...(history.get(shotId)?.values() || [])]);
    const raw = discarded.target?.record;
    const candidate = raw && !checkPromptRecord(raw).length ? raw as PromptRecord : null;
    const payload = candidate && !promptStaleness(candidate, basis(shotId)).stale ? candidate : (await compile(shotId)).payload;
    await save(shotId, payload, action, entry.version);
    return payload;
  }
  async function restore(action: ActionSnapshot) {
    if (!action.projectId) return;
    const latest = await deps.repository.documents.listLatest(action.projectId, DOMAIN_DOCUMENT_KINDS.prompt_version);
    for (const head of latest) {
      if (!action.alive()) return;
      const chain = await deps.repository.documents.listVersions(action.projectId, DOMAIN_DOCUMENT_KINDS.prompt_version, head.document_id);
      if (!action.alive()) return;
      for (const stored of chain) {
        const problems = checkPromptRecord(stored.payload);
        if (problems.length) throw new Error("已保存的 Prompt 无法恢复：" + problems[0].message);
        remember(stored.document_id, { record: stored.payload as PromptRecord, version: stored.version });
      }
    }
  }
  return { reset, restore, entryOf, profile, basis, sheet, compile, compileAndSave, prepare, edit, reconfirm, discard,
    isPreparing: () => preparing !== null };
}
