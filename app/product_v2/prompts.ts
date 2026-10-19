/** Prompt 版本、编译、人工覆盖和确认单的业务所有权；浏览器只加载生成的 .js。 */
import {
  DOMAIN_DOCUMENT_KINDS, PLATFORM_PROFILES, PROMPT_COMPILER_RULE_VERSION,
  assertConfirmationSheet, briefReadiness,
  buildConfirmationSheet, buildEditedPromptRecord, buildProductBrief, buildPromptRecord,
  canonicalJson, checkPromptRecord, compilePrompt, discardManualEdit, imagePromptProfile,
  promptHash, promptStaleness, reconfirmEditedPrompt, requestSnapshotOf, selectReferences,
  shotSignatureOf, styleSignatureOf, suitePlanSummary,
} from "./domain/index.js";
import { sha256Hex } from "./storage/db.js";
import type { ProjectRepository, StoredDocumentRecord } from "./storage/validate.js";
import type { ActionSnapshot, PromptEntry } from "./generation.js";
import type {
  BriefBasisItem, CompiledPrompt, ConfirmationCost, ConfirmationSelection, ImagePromptProfile, PromptBasis, PromptRecord,
  PromptReferenceIdentity, PromptReferenceSelection, ReworkDirective, ShotSpec, SlotEntry,
  StyleSpec, SuitePlan,
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
  /** 商品来源投影：只有 role/sha256 原始身份，不伪造冻结元数据；冻结经 selectReferences 产生。 */
  references: PromptReferenceIdentity[];
  sellingPoints: string[];
  /** 已提交商品资料文档版本（0=无文档）；参考图/卖点变化由它封印。 */
  intakeVersion: number;
};
export type PromptCurrentBasis = {
  compiler_rule_version: number;
  briefBasis: BriefBasisItem[];
  shot_signature: string | null;
  suite_version: number | null;
  style_version: number | null;
  style_signature: string | null;
  shot_spec_version: number | null;
  intake_version: number | null;
  platform: { version: number };
  provider: ImagePromptProfile | null;
};
export type ConfirmationFix = { region: string; shot_id: string | null; label: string; action: string };
export type ConfirmationBlocker = { code: string; message: string; fix: ConfirmationFix };
export type ConfirmationRisk = { code: string; message: string; shot_id?: string; label?: string };
export type ConfirmationSheetShot = {
  shot_id: string; order: number; label: string; role_id: string | null; role_label: string | null;
  intent: string | null; template_id: string | null; required: boolean; satisfied: boolean;
  prompt: { version: number | null; hash: string | null; chars: number | null; text: string | null };
  references: { role: string; sha256_prefix: string; sha256?: string;
    uses?: string[]; sources?: { kind?: string; document_id?: string; version?: number;
      asset_sha256?: string }[];
    source_label?: string }[];
  rework_mode?: string | null;
  problem_candidate?: { candidate_id: string; version: number; asset_sha256: string } | null;
  risks: ConfirmationRisk[]; blockers: ConfirmationBlocker[];
};
export type ConfirmationSheet = {
  schema_version: number; total: number; ready: number; blocked: number; can_submit: boolean;
  platform: { platform_id: string; version: number; label?: string };
  provider: Pick<ImagePromptProfile, "provider_id" | "model_id" | "version" | "protocol" | "size" | "n" | "prompt_extend" | "watermark" | "output_format">;
  external_summary: { model: string; size: string; n: number; prompt_extend: boolean; watermark: boolean;
    output_format: string; reference_count: number; reference_roles: string[]; prompt_chars: number;
    on_image_text_language?: string; statement: string; cost: ConfirmationCost };
  shots: ConfirmationSheetShot[]; scope_shot_ids?: string[]; selection: ConfirmationSelection;
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
  /** 只读准备保留人工全文的返工记录；与落版共用同一构造，预览不写历史。 */
  previewManualForRework(shotId: string, options: { rework: ReworkDirective }): Promise<CompiledPromptResult>;
  /** 返工遇人工全文且用户选 keep_manual：按当前指令重编后把人工文本变基到新依据，不改原文。 */
  rebaseManualForRework(shotId: string, options: { rework: ReworkDirective; action?: ActionSnapshot | null }): Promise<SavedPromptResult>;
  discard(shotId: string, action?: ActionSnapshot): Promise<PromptRecord | null>;
  isPreparing(): boolean;
}

export function sourceContext(source: ProjectSources) {
  return {
    facts: source.slots.map(({ slot }) => ({ slot_id: slot.slot_id, status: slot.status, value: slot.value })),
    assets: source.references,
  };
}

/** 记录的冻结返工血缘（唯一来源 base.basis.rework）：只有明确模式才回传；
 * 无 mode 历史（v2.5.4）既不猜编辑源，也不把它喂进新写入端。 */
function reworkLineageOf(record: PromptRecord | null): ReworkDirective | null {
  const frozen = record && record.basis ? record.basis.rework : null;
  if (!frozen) return null;
  if (frozen.mode !== "edit_candidate" && frozen.mode !== "regenerate_original") return null;
  const fixed = frozen.problem_candidate;
  if (!fixed || typeof fixed.candidate_id !== "string" || typeof fixed.document_id !== "string"
      || !Number.isInteger(fixed.version) || typeof fixed.asset_sha256 !== "string") return null;
  // 冻结血缘按原字节原样回传：写入门（basis.rework）与选择器读同一份形状，不重建、不补造。
  return frozen as unknown as ReworkDirective;
}

/** 返工派生版本的人工续写：用同一冻结血缘重算参考图顺序（编辑源在首位），
 * 与写入门、事务核对调用同一选择器、同一选项；模式未声明的历史血缘不在此路径。 */
function lineageReferencesOf(source: ProjectSources, shotId: string,
  provider: ImagePromptProfile, lineage: ReworkDirective): PromptReferenceSelection[] {
  const shot = source.suitePlan?.shots.find((item) => item.shot_id === shotId);
  if (!shot) throw new Error("找不到这张图，可能已被删除。");
  const spec = source.shotSpecs[shotId];
  return selectReferences(shot, source.references, {
    maxReferences: provider.max_reference_images, intakeVersion: source.intakeVersion,
    shotSpec: spec?.spec || null, rework: lineage,
  });
}

/** 记录依据 + 冻结返工血缘：血缘字段原样保留（含 problems 与 problem_candidate 的独立副本）。 */
function basisWithLineage(basis: PromptBasis, lineage: ReworkDirective): PromptBasis {
  const frozen = lineage as unknown as NonNullable<PromptBasis["rework"]>;
  return { ...basis, rework: { ...frozen, problems: [...frozen.problems] } };
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
 * 活动输入实例与“已读快照”消费者共用同一份实现，避免各自重算。
 * compiler_rule_version 每次都盖当前编译器版本（parent 导出的唯一常量）；
 * intake_version 封印商品资料版本（冻结引用里嵌了它）；style_signature 只封印本图
 * 实际消费的共用风格字段（被单图覆盖的字段变化不使本图过期）。 */
export function promptCurrentBasisOf(source: ProjectSources, shotId: string | null,
  provider: ImagePromptProfile | null): PromptCurrentBasis {
  let briefBasis: BriefBasisItem[] = [];
  try { briefBasis = buildProductBrief(source.slots).basis; } catch { /* 未就绪事实仍可投影缺项。 */ }
  const shot = source.suitePlan?.shots.find(item => item.shot_id === shotId);
  const spec = shotId ? source.shotSpecs[shotId]?.spec || null : null;
  return {
    compiler_rule_version: PROMPT_COMPILER_RULE_VERSION,
    briefBasis, shot_signature: shot ? shotSignatureOf(shot) : null,
    suite_version: source.suiteVersion || null, style_version: source.styleVersion || null,
    style_signature: shot ? styleSignatureOf(source.styleSpec, spec, shot) : null,
    shot_spec_version: shotId ? source.shotSpecs[shotId]?.version || null : null,
    intake_version: source.intakeVersion || null,
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
    // 视角决定要在确认单里按本图实际会冻结的商品依据判：与编译同一选择器、同一选项。
    // 选不出时留空，由决定门按 fail-closed 说明该补什么，不默认放行。
    const referencesByShot: Record<string, unknown> = {};
    for (const shot of source.suitePlan.shots) {
      if (!shot.shot_id) continue;
      currentBasisByShot[shot.shot_id] = basis(shot.shot_id, provider, source);
      try {
        referencesByShot[shot.shot_id] = selectReferences(shot, source.references, {
          maxReferences: provider.max_reference_images, intakeVersion: source.intakeVersion,
          shotSpec: source.shotSpecs[shot.shot_id]?.spec || null,
        });
      } catch { /* 引用不成立时不带证据，保持阻断而不是换个说法。 */ }
    }
    const environment = deps.imageEnvironment();
    const result = buildConfirmationSheet({
      suitePlan: source.suitePlan, providerProfile: provider, context: sourceContext(source),
      promptEntries: [...versions].map(([shot_id, entry]) => ({ shot_id, ...entry })),
      currentBasisByShot, shotIds,
      pricing: environment && typeof environment === "object" && "pricing" in environment ? environment.pricing : null,
      // 普通决定的阻断必须能指到具体控件，所以把决定所依赖的规格、简报与实际依据一并交给确认单。
      brief: buildProductBrief(source.slots), styleSpec: source.styleSpec, shotSpecsById: source.shotSpecs,
      referencesByShot, slotEntries: source.slots,
    });
    assertConfirmationSheet(result);
    return result as ConfirmationSheet;
  }
  /** 同一选择器、同一选项：编译、运行前核对、事务核对四处必须逐字一致。
   * 先选再编：references 冻结完整元数据后才交给编译器做正文/依据绑定。 */
  async function compile(shotId: string, options: { rework?: ReworkDirective; source?: ProjectSources } = {}): Promise<CompiledPromptResult> {
    const source = options.source || deps.sources();
    const shot = source.suitePlan?.shots.find(item => item.shot_id === shotId);
    if (!shot) throw new Error("找不到这张图，可能已被删除。");
    const providerProfile = profile();
    if (!providerProfile) throw new Error("尚未取得有效图像能力，请恢复模型服务后再编译；不会猜测模型参数。");
    const spec = source.shotSpecs[shotId];
    if (!Number.isInteger(source.intakeVersion) || source.intakeVersion < 1) {
      throw new Error("商品资料还没有已保存版本；先保存商品资料，再编译这张图。");
    }
    const references = selectReferences(shot, source.references, {
      maxReferences: providerProfile.max_reference_images, intakeVersion: source.intakeVersion,
      shotSpec: spec?.spec || null, ...(options.rework ? { rework: options.rework } : {}),
    });
    const compiled = compilePrompt({
      brief: buildProductBrief(source.slots), shot, styleSpec: source.styleSpec,
      shotSpec: spec?.spec || null, context: sourceContext(source), providerProfile,
      references, slotEntries: source.slots,
      versions: { suite_version: source.suiteVersion, style_version: source.styleVersion,
        shot_spec_version: spec?.version || null, intake_version: source.intakeVersion },
      ...(options.rework ? { rework: options.rework } : {}),
    });
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
  /** 人工编辑走当前选择器重算完整冻结引用；返工派生的版本继续携带 base 的冻结血缘
   * （编辑源在首位、模式在 basis.rework），无 mode 历史不猜编辑源（也不进新写入端）。 */
  async function edit(shotId: string, text: string, reason: string, action = deps.beginAction()) {
    const entry = entryOf(shotId);
    if (!entry) throw new Error("先编译并保存这张图的 Prompt，再编辑。");
    const source = deps.sources();
    const current = await compile(shotId, { source });
    const lineage = reworkLineageOf(entry.record);
    const record = await buildEditedPromptRecord({
      base: entry.record, baseVersion: entry.version, text, reason, editedAt: new Date().toISOString(),
      context: { ...sourceContext(source), brief: buildProductBrief(source.slots),
        shotSpec: source.shotSpecs[shotId]?.spec || null },
      basis: lineage ? basisWithLineage(current.compiled.basis, lineage) : current.compiled.basis,
      references: lineage ? lineageReferencesOf(source, shotId, current.compiled.provider, lineage) : current.references,
      currentCompiled: current.compiled, digest: sha256Hex,
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
    // 返工派生的版本重新确认时保留同一冻结血缘与图序（编辑源在首位）；普通人工全文明用当前依据。
    const lineage = reworkLineageOf(entry.record);
    const provider = profile();
    const record = await reconfirmEditedPrompt({
      base: entry.record, baseVersion: entry.version, reason: "用户按当前依据显式确认保留此人工全文",
      at: new Date().toISOString(),
      basis: lineage ? basisWithLineage(current.compiled.basis, lineage) : current.compiled.basis,
      references: lineage && provider ? lineageReferencesOf(source, shotId, provider, lineage) : current.references,
      currentCompiled: current.compiled,
      context: { facts: source.slots.map(entry => entry.slot), brief: buildProductBrief(source.slots),
        shotSpec: source.shotSpecs[shotId]?.spec || null },
      digest: sha256Hex,
    });
    return save(shotId, record, action, entry.version);
  }
  async function previewManualForRework(shotId: string,
    options: { rework: ReworkDirective }): Promise<CompiledPromptResult> {
    const entry = entryOf(shotId);
    if (!entry || entry.record.origin !== "manual_edit") {
      throw new Error("当前不是人工全文；返工按普通编译路径走，不需要保留人工全文。");
    }
    const current = await compile(shotId, { rework: options.rework });
    const record = await reconfirmEditedPrompt({
      base: entry.record, baseVersion: entry.version,
      reason: "返工保留人工全文并按当前返工依据重新确认",
      at: new Date().toISOString(), basis: current.compiled.basis, references: current.references,
      currentCompiled: current.compiled,
      context: { facts: deps.sources().slots.map(entry => entry.slot),
        brief: buildProductBrief(deps.sources().slots),
        shotSpec: deps.sources().shotSpecs[shotId]?.spec || null },
      digest: sha256Hex,
    });
    return { payload: record, compiled: record.compiled, references: current.references };
  }
  async function rebaseManualForRework(shotId: string,
    options: { rework: ReworkDirective; action?: ActionSnapshot | null }): Promise<SavedPromptResult> {
    const action = options.action || deps.beginAction();
    const previous = entryOf(shotId)?.version || 0;
    const prepared = await previewManualForRework(shotId, options);
    const saved = await save(shotId, prepared.payload, action, previous);
    return { ...prepared, saved };
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
  return { reset, restore, entryOf, profile, basis, sheet, compile, compileAndSave, prepare, edit, reconfirm,
    previewManualForRework, rebaseManualForRework, discard, isPreparing: () => preparing !== null };
}
