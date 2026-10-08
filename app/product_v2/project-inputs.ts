/** 输入面唯一所有者（设计 §2.1/§10.1/包04）：资料/事实/方案状态与业务命令。
 * workspace 只做装配、生命周期与视图渲染；本文件是唯一手工维护实现，
 * 同名 `project-inputs.js` 由 `npm run build:frontend` 从本文件生成。 */
import {
  DOMAIN_DOCUMENT_KINDS, FACT_SLOT_SCHEMA_VERSION, PRODUCT_INPUT_SCHEMA_VERSION,
  MAX_REFERENCES, SUITE_PLAN_DOCUMENT_ID, STYLE_SPEC_DOCUMENT_ID, CORE_SLOT_REGISTRY,
  addCustomShotToPlan, addShotFromTemplate, applySlotAction, canonicalJson, consumedSlotIdsOf,
  assertShotSpec, assertStyleSpec, briefReadiness, buildProductBrief,
  canAddSlot, checkFactSlot, coreSlotDefinition, copyShot,
  emptyProductInput, emptyShotSpecFromShot, emptyStyleSpec,
  intakeReadiness, isPlainObject, moveShot, previousVersionOf,
  referenceFromAsset, removeShot, seedSuitePlan, shotSignatureOf, validateSuitePlan,
} from "./domain/index.js";
import { STORAGE_ERROR_CODES } from "./storage/errors.js";
import { sha256Hex } from "./storage/db.js";
import type { ActionSnapshot } from "./session.js";
import type {
  ConsumptionFence, DocumentRef, ProjectRepository, ProjectSnapshot, StoredDocumentRecord,
} from "./storage/validate.js";
import type {
  BriefReadiness, FactSlot, PlanShot, ProductInput, ProductReference,
  ReferenceRole, SemanticAnalysisSource, SemanticProposal,
  ShotSpec, SlotActionSpec, SlotEntry, StyleSpec, SuitePlan,
} from "./domain/type-contracts.js";
import type { ProjectSources } from "./prompts.js";
import type {
  AnalysisOutcome, PreparedAnalysis,
} from "./semantic-analysis.js";
import { createSemanticAnalysisModule } from "./semantic-analysis.js";
import type { EffectiveCapabilities, ModelSettings } from "./model-settings.js";

const INTAKE_DOCUMENT_ID = "intake";
const INTAKE_KIND = DOMAIN_DOCUMENT_KINDS.product_input;
const SLOT_KIND = DOMAIN_DOCUMENT_KINDS.fact_slot;
const SUITE_KIND = DOMAIN_DOCUMENT_KINDS.suite_plan;
const STYLE_KIND = DOMAIN_DOCUMENT_KINDS.style_spec;
const SHOT_SPEC_KIND = DOMAIN_DOCUMENT_KINDS.shot_spec;

const DRAFT_DEBOUNCE_MS = 600;
const ANALYZE_MAX_SLOTS = 12;
const MAX_REFERENCE_IMAGE_BYTES = 10 * 1024 * 1024;
const ANALYZE_LOCALE = "zh-CN";
const ANALYZE_PLATFORM = "amazon_us";
const DEFAULT_ANALYZE_FIELDS = Object.freeze([
  "product_name", "description", "selling_points", "focus", "references",
  "locale", "platform", "max_slots", "existing_slot_ids",
]);

export type CompleteProductInput = {
  schema_version: number; product_name: string; description: string;
  selling_points: string[]; focus: string; references: ProductReference[];
};
export type InputSlotEntry = { slot: FactSlot; version: number };
export type InputShotSpecEntry = { spec: ShotSpec; version: number };
export type IntakeConflict = {
  version: number; at: string; merged?: boolean;
  unresolved?: { field: string; mine: unknown; theirs: unknown }[];
} | null;
export type LastAnalyze = {
  slots: number; applied: number; provider: string; model: string | null;
  sourceVersion: number; referenceImagesSent: boolean; imageProvenance: { role: string; media_type: string; sha256: string }[];
  at: string; summary: string;
} | null;
export type InputsDependencies = {
  repository: ProjectRepository;
  beginAction(): ActionSnapshot;
  settings: ModelSettings;
  capabilities(): EffectiveCapabilities | null;
  projectIdReader(): string | null;
  projectNameReader(): string;
  draftInput(): CompleteProductInput;
  changed?(): void;
};
export type InputsModule = {
  reset(): void;
  restore(action: ActionSnapshot): Promise<void>;
  scheduleDraftSave(): void;
  saveIntakeNow(): Promise<boolean>;
  currentIntakePayload(): CompleteProductInput;
  intakeSnapshot(): CompleteProductInput;
  draftVersion(): number;
  conflict(): IntakeConflict;
  resolveConflict(picks: Record<string, "mine" | "theirs">): Promise<boolean>;
  addReferences(files: FileList | File[] | null | undefined, report?: (kind: "too_many" | "too_large" | "unreadable" | "duplicate", file: File) => void): Promise<number>;
  setReferenceRole(index: number, role: ReferenceRole): Promise<void>;
  removeReference(index: number): Promise<void>;
  references(): ProductReference[];
  ensureCoreSlots(): Promise<number>;
  slotAction(slotId: string, spec: SlotActionSpec): Promise<void>;
  addCustomSlot(candidate: FactSlot): Promise<void>;
  slotEntries(): InputSlotEntry[];
  runAnalysis(options?: { allowNewAfterUnknown?: boolean }): Promise<AnalysisOutcome>;
  isAnalysisRunning(): boolean;
  analyzeState(): { requiresConfirmation: boolean; problems: string[]; last: LastAnalyze };
  applySuiteOp(run: () => { plan: SuitePlan } & Record<string, unknown>): Promise<boolean>;
  seedPlan(): Promise<boolean>;
  addShotFromTemplate(templateId: string): Promise<boolean>;
  addCustomShot(label: string, intent: string): Promise<boolean>;
  moveShot(shotId: string, delta: number): Promise<boolean>;
  copyShot(shotId: string, shotId2?: string): Promise<boolean>;
  removeShot(shotId: string): Promise<boolean>;
  suiteContext(): { facts: { slot_id: string; status: string; value: unknown }[];
    assets: { role: string; sha256: string }[] };
  sources(): ProjectSources;
  suitePlan(): SuitePlan | null;
  suiteVersion(): number;
  styleSpec(): StyleSpec;
  styleVersion(): number;
  shotSpecEntry(shotId: string | null): InputShotSpecEntry | null;
  shotSpecsById(): Record<string, InputShotSpecEntry>;
  saveStyle(next: StyleSpec): Promise<void>;
  restoreStyle(): Promise<number>;
  saveShotSpec(shotId: string, changes: Partial<ShotSpec>): Promise<void>;
  restoreShotSpec(shotId: string): Promise<void>;
  understanding(): { ready: boolean; blocking: BriefReadiness["blocking"]; error: unknown };
  deriveState(): Promise<void>;
  prepareAnalysis(action: ActionSnapshot): Promise<PreparedAnalysis>;
  sourceIsCurrent(source: SemanticAnalysisSource, action: ActionSnapshot): Promise<boolean>;
  applyProposal(proposal: SemanticProposal, pid: string, action: ActionSnapshot,
    source: SemanticAnalysisSource): Promise<{ applied: number; problems: string[] }>;
};

function messageOf(error: unknown, fallback: string): string {
  if (error instanceof Error && typeof error.message === "string" && error.message) return error.message;
  if (error !== null && typeof error === "object" && "message" in error
    && typeof (error as { message: unknown }).message === "string"
    && (error as { message: string }).message) return (error as { message: string }).message;
  return fallback;
}
function splitLines(text: string): string[] {
  return String(text || "").split("\n").map((item) => item.trim()).filter((item) => item.length > 0);
}
function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}
function isProductReference(value: unknown): value is ProductReference {
  return isPlainObject(value) && typeof (value as Record<string, unknown>).asset_sha256 === "string"
    && typeof (value as Record<string, unknown>).role === "string";
}
function productInputFromStored(payload: unknown): ProductInput {
  return { ...emptyProductInput(), ...(isPlainObject(payload) ? payload as object : {}) };
}
async function blobToBase64(blob: Blob): Promise<string> {
  const buffer = await blob.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

/** 消费围栏（设计 §10.3）：把“这次决策实际消费的输入版本”变成事务内可复核的只读引用。
 * 纯函数、无 secret、无 DOM；候选/报告/资产等业务追加引用由调用方补。 */
export function consumptionFence(source: ProjectSources, shotIds: readonly string[]): ConsumptionFence {
  const confirmed: string[] = [];
  const slotsById = new Map<string, InputSlotEntry>();
  for (const entry of source.slots) {
    slotsById.set(entry.slot.slot_id, entry);
    if (entry.slot.status === "confirmed") confirmed.push(entry.slot.slot_id);
  }
  const wanted = new Set(shotIds);
  const sources: DocumentRef[] = [
    { kind: SUITE_KIND, documentId: SUITE_PLAN_DOCUMENT_ID, version: source.suiteVersion },
    { kind: STYLE_KIND, documentId: STYLE_SPEC_DOCUMENT_ID, version: source.styleVersion },
    { kind: INTAKE_KIND, documentId: INTAKE_DOCUMENT_ID, version: source.intakeVersion },
  ];
  const shots: { shot_id: string; shot_signature: string; shot_spec_version: number;
    consumed_slots: { slot_id: string; version: number }[] }[] = [];
  for (const shot of source.suitePlan?.shots || []) {
    if (!wanted.has(shot.shot_id)) continue;
    const consumedSlots: { slot_id: string; version: number }[] = [];
    for (const slotId of consumedSlotIdsOf(shot, confirmed)) {
      const version = slotsById.get(slotId)?.version ?? 0;
      sources.push({ kind: SLOT_KIND, documentId: slotId, version });
      consumedSlots.push({ slot_id: slotId, version });
    }
    const specVersion = source.shotSpecs[shot.shot_id]?.version ?? 0;
    sources.push({ kind: SHOT_SPEC_KIND, documentId: shot.shot_id, version: specVersion });
    shots.push({ shot_id: shot.shot_id, shot_signature: shotSignatureOf(shot),
      shot_spec_version: specVersion, consumed_slots: consumedSlots });
  }
  const assetSha256 = [...new Set(source.references.map((item) => item.sha256))].sort();
  return {
    sources,
    projectionJson: canonicalJson({ project_id: source.projectId,
      suite_version: source.suiteVersion, style_version: source.styleVersion,
      intake_version: source.intakeVersion, shots, asset_sha256: assetSha256 }),
    assetSha256,
  };
}

/** 从同一只读快照重建输入面只读投影（完整项目包/交付一致性读取用）：与 restore 同形状，不引入第二套约定。 */
export function projectSourcesFromSnapshot(snapshot: ProjectSnapshot): ProjectSources {
  const latest = new Map<string, StoredDocumentRecord>();
  for (const row of snapshot.documents) {
    const key = row.kind + "/" + row.document_id;
    if ((latest.get(key)?.version || 0) < row.version) latest.set(key, row);
  }
  let intake: ProductInput = emptyProductInput();
  let intakeVersion = 0;
  const intakeRow = latest.get(INTAKE_KIND + "/" + INTAKE_DOCUMENT_ID);
  if (intakeRow && isPlainObject(intakeRow.payload)) {
    intake = productInputFromStored(intakeRow.payload);
    if (!Array.isArray(intake.references)) intake.references = [];
    if (!Array.isArray(intake.selling_points)) intake.selling_points = [];
    intakeVersion = intakeRow.version;
  }
  const slots: InputSlotEntry[] = [];
  const shotSpecs: Record<string, InputShotSpecEntry> = {};
  let suitePlan: SuitePlan | null = null;
  let suiteVersion = 0;
  let styleSpec: StyleSpec = emptyStyleSpec();
  let styleVersion = 0;
  for (const [key, row] of latest) {
    if (row.kind === SLOT_KIND && isPlainObject(row.payload)) {
      // 槽位形状以消费边界 checkFactSlot 为准；此处按 fact_slot 文档契约投影。
      slots.push({ slot: row.payload as unknown as FactSlot, version: row.version });
    } else if (row.kind === SHOT_SPEC_KIND && isPlainObject(row.payload)) {
      shotSpecs[row.document_id] = { spec: row.payload as unknown as ShotSpec, version: row.version };
    } else if (row.kind === SUITE_KIND && key === SUITE_KIND + "/" + SUITE_PLAN_DOCUMENT_ID
      && isPlainObject(row.payload) && Array.isArray(row.payload.shots)) {
      suitePlan = row.payload as unknown as SuitePlan;
      suiteVersion = row.version;
    } else if (row.kind === STYLE_KIND && key === STYLE_KIND + "/" + STYLE_SPEC_DOCUMENT_ID
      && isPlainObject(row.payload)) {
      styleSpec = { ...emptyStyleSpec(), ...(row.payload as Partial<StyleSpec>) };
      styleVersion = row.version;
    }
  }
  return {
    projectId: snapshot.project.project_id, projectName: snapshot.project.name,
    slots, suitePlan, suiteVersion, styleSpec, styleVersion, shotSpecs,
    references: intake.references.map((item) => ({ role: item.role, sha256: item.asset_sha256 })),
    sellingPoints: [...(intake.selling_points || [])], intakeVersion,
  };
}

export function createProjectInputsModule(deps: InputsDependencies): InputsModule {
  let intake: ProductInput = emptyProductInput();
  let intakeVersion = 0;
  let intakeFingerprint = "";
  let slots = new Map<string, InputSlotEntry>();
  let suitePlan: SuitePlan | null = null;
  let suiteVersion = 0;
  let understandingReady = false;
  let understandingBlocking: BriefReadiness["blocking"] = [];
  let understandingError: unknown = null;
  let lastAnalyze: LastAnalyze = null;
  let analyzeRequiresConfirmation = false;
  let analyzeProblems: string[] = [];
  let styleSpec: StyleSpec = emptyStyleSpec();
  let styleVersion = 0;
  let shotSpecs = new Map<string, InputShotSpecEntry>();
  let saveTimer: ReturnType<typeof setTimeout> | null = null;
  let intakeConflict: IntakeConflict = null;

  function fingerprintOf(payload: CompleteProductInput | ProductInput): string {
    return JSON.stringify([payload.product_name, payload.description,
      (payload as CompleteProductInput).selling_points, (payload as CompleteProductInput).focus,
      payload.references]);
  }
  function slotEntries(): InputSlotEntry[] {
    return [...slots.values()].map((entry) => ({ slot: entry.slot, version: entry.version }));
  }
  function suiteContext() {
    return {
      facts: [...slots.values()].map((entry) => ({
        slot_id: entry.slot.slot_id, status: entry.slot.status, value: entry.slot.value,
      })),
      assets: intake.references.map((item) => ({ role: item.role, sha256: item.asset_sha256 })),
    };
  }
  function sources(): ProjectSources {
    const specs: Record<string, { spec: ShotSpec; version: number }> = {};
    for (const [shotId, entry] of shotSpecs) specs[shotId] = { spec: entry.spec, version: entry.version };
    return {
      projectId: deps.projectIdReader(), projectName: deps.projectNameReader(),
      slots: slotEntries().map((entry) => ({ slot: entry.slot, version: entry.version })),
      suitePlan, suiteVersion, styleSpec, styleVersion, shotSpecs: specs,
      references: intake.references.map((item) => ({ role: item.role, sha256: item.asset_sha256 })),
      sellingPoints: [...(intake.selling_points || [])], intakeVersion,
    };
  }
  function shotSpecEntry(shotId: string | null): InputShotSpecEntry | null {
    if (!shotId) return null;
    return shotSpecs.get(shotId) || null;
  }
  function shotSpecsById(): Record<string, InputShotSpecEntry> {
    const byId: Record<string, InputShotSpecEntry> = {};
    for (const [shotId, entry] of shotSpecs.entries()) byId[shotId] = entry;
    return byId;
  }
  function understanding() {
    return { ready: understandingReady, blocking: understandingBlocking, error: understandingError };
  }
  function draftVersion(): number { return intakeVersion; }
  function conflict(): IntakeConflict { return intakeConflict; }
  function references(): ProductReference[] {
    return intake.references.map((item) => ({ ...item }));
  }
  function intakeSnapshot(): CompleteProductInput {
    return { ...(intake as CompleteProductInput) };
  }

  function reset(): void {
    intake = emptyProductInput(); intakeVersion = 0; intakeFingerprint = "";
    slots = new Map(); lastAnalyze = null; analyzeProblems = [];
    analyzeRequiresConfirmation = false;
    suitePlan = null; suiteVersion = 0; understandingReady = false;
    understandingBlocking = []; understandingError = null;
    styleSpec = emptyStyleSpec(); styleVersion = 0; shotSpecs = new Map();
    intakeConflict = null;
    if (saveTimer !== null) { clearTimeout(saveTimer); saveTimer = null; }
  }

  async function restore(action: ActionSnapshot): Promise<void> {
    const pid = action.projectId;
    if (!pid) return;
    const intakeDoc = await deps.repository.documents.getLatest(pid, INTAKE_KIND, INTAKE_DOCUMENT_ID);
    if (!action.alive()) return;
    if (intakeDoc && intakeDoc.payload && typeof intakeDoc.payload === "object") {
      intake = { ...emptyProductInput(), ...(intakeDoc.payload as object) };
      if (!Array.isArray(intake.references)) intake.references = [];
      if (!Array.isArray(intake.selling_points)) intake.selling_points = [];
      intakeVersion = intakeDoc.version;
    }
    intakeFingerprint = fingerprintOf(intake as CompleteProductInput);
    const slotDocs = await deps.repository.documents.listLatest(pid, SLOT_KIND);
    if (!action.alive()) return;
    for (const record of slotDocs) {
      if (record.kind === SLOT_KIND && record.payload && typeof record.payload === "object") {
        slots.set(record.document_id, { slot: record.payload as FactSlot, version: record.version });
      }
    }
    const suiteDoc = await deps.repository.documents.getLatest(pid, SUITE_KIND, SUITE_PLAN_DOCUMENT_ID);
    if (!action.alive()) return;
    if (suiteDoc && suiteDoc.payload && Array.isArray((suiteDoc.payload as { shots?: unknown }).shots)) {
      suitePlan = suiteDoc.payload as SuitePlan;
      suiteVersion = suiteDoc.version;
    }
    const styleDoc = await deps.repository.documents.getLatest(pid, STYLE_KIND, STYLE_SPEC_DOCUMENT_ID);
    if (!action.alive()) return;
    if (styleDoc && styleDoc.payload && typeof styleDoc.payload === "object") {
      styleSpec = { ...emptyStyleSpec(), ...(styleDoc.payload as Partial<StyleSpec>) };
      styleVersion = styleDoc.version;
    }
    const specDocs = await deps.repository.documents.listLatest(pid, SHOT_SPEC_KIND);
    if (!action.alive()) return;
    for (const record of specDocs) {
      if (record.payload && typeof record.payload === "object") {
        shotSpecs.set(record.document_id, { spec: record.payload as ShotSpec, version: record.version });
      }
    }
  }

  function currentIntakePayload(): CompleteProductInput {
    return deps.draftInput();
  }

  function mergeIntakePayloads(base: unknown, mine: unknown, theirs: unknown) {
    if (!isPlainObject(mine) || !isPlainObject(theirs)) return null;
    const baseSafe = isPlainObject(base) ? base as Record<string, unknown> : {};
    const mineRec = mine as Record<string, unknown>;
    const theirsRec = theirs as Record<string, unknown>;
    const mineRefs = Array.isArray(mineRec.references) ? mineRec.references : [];
    const theirRefs = Array.isArray(theirsRec.references) ? theirsRec.references : [];
    const refBySha = new Map<string, ProductReference>();
    for (const ref of theirRefs) {
      if (isProductReference(ref)) refBySha.set(ref.asset_sha256, ref);
    }
    for (const ref of mineRefs) {
      if (isProductReference(ref)) refBySha.set(ref.asset_sha256, ref);
    }
    const textFields = ["product_name", "description", "focus"];
    const unresolved: { field: string; mine: unknown; theirs: unknown }[] = [];
    const mergedTexts: Record<string, string> = {};
    for (const field of textFields) {
      const b = typeof baseSafe[field] === "string" ? baseSafe[field] as string : "";
      const m = typeof mineRec[field] === "string" ? mineRec[field] as string : "";
      const h = typeof theirsRec[field] === "string" ? theirsRec[field] as string : "";
      if (m === h) { mergedTexts[field] = m; continue; }
      if (m === b) { mergedTexts[field] = h; continue; }
      if (h === b) { mergedTexts[field] = m; continue; }
      unresolved.push({ field, mine: m, theirs: h });
    }
    const basePoints = isStringArray(baseSafe.selling_points) ? baseSafe.selling_points : [];
    const minePoints = isStringArray(mineRec.selling_points) ? mineRec.selling_points : [];
    const theirPoints = isStringArray(theirsRec.selling_points) ? theirsRec.selling_points : [];
    const joins = (list: string[]) => list.join(" ");
    let mergedPoints = minePoints;
    if (joins(minePoints) === joins(theirPoints)) mergedPoints = minePoints;
    else if (joins(minePoints) === joins(basePoints)) mergedPoints = theirPoints;
    else if (joins(theirPoints) === joins(basePoints)) mergedPoints = minePoints;
    else {
      mergedPoints = [...minePoints];
      for (const point of theirPoints) {
        if (!mergedPoints.includes(point)) mergedPoints.push(point);
      }
    }
    if (unresolved.length > 0) return { merged: false as const, unresolved };
    return {
      merged: true as const,
      record: {
        schema_version: PRODUCT_INPUT_SCHEMA_VERSION,
        product_name: mergedTexts.product_name, description: mergedTexts.description,
        focus: mergedTexts.focus, selling_points: mergedPoints,
        references: [...refBySha.values()],
      } as ProductInput,
    };
  }

  async function saveIntakeNow(): Promise<boolean> {
    if (saveTimer !== null) { clearTimeout(saveTimer); saveTimer = null; }
    const action = deps.beginAction();
    if (!action.projectId) return false;
    const pid = action.projectId;
    const payload = currentIntakePayload();
    const fingerprint = fingerprintOf(payload);
    if (fingerprint === intakeFingerprint) return false;
    let record: StoredDocumentRecord<ProductInput>;
    try {
      record = await deps.repository.documents.save(pid, {
        kind: INTAKE_KIND, documentId: INTAKE_DOCUMENT_ID, payload,
        expectedVersion: intakeVersion,
      }) as StoredDocumentRecord<ProductInput>;
    } catch (error) {
      if (typeof error === "object" && error !== null && "code" in error
        && (error as { code: unknown }).code === STORAGE_ERROR_CODES.REVISION_CONFLICT) {
        const latest = await deps.repository.documents.getLatest(pid, INTAKE_KIND, INTAKE_DOCUMENT_ID);
        if (!action.alive()) return false;
        const latestPayload = latest && latest.payload ? latest.payload : null;
        const latestVersion = latest ? latest.version : 0;
        const basePayload = intake;
        const merged = latestPayload ? mergeIntakePayloads(basePayload, payload, latestPayload) : null;
        if (merged && merged.merged && merged.record) {
          const mergedRecord = await deps.repository.documents.save(pid, {
            kind: INTAKE_KIND, documentId: INTAKE_DOCUMENT_ID,
            payload: merged.record, expectedVersion: latestVersion,
          }) as StoredDocumentRecord<ProductInput>;
          if (!action.alive()) return false;
          intake = mergedRecord.payload;
          intakeVersion = mergedRecord.version;
          intakeFingerprint = fingerprintOf(mergedRecord.payload as CompleteProductInput);
          intakeConflict = { version: latestVersion, at: new Date().toISOString(), merged: true };
          deps.changed?.();
          return false;
        }
        if (merged && !merged.merged && Array.isArray(merged.unresolved) && merged.unresolved.length > 0) {
          if (!action.alive()) return false;
          intakeConflict = { version: latestVersion, at: new Date().toISOString(),
            merged: false, unresolved: merged.unresolved };
          deps.changed?.();
          return false;
        }
        intakeConflict = { version: latest && latest.payload ? latest.version : 0,
          at: new Date().toISOString() };
        deps.changed?.();
        return false;
      }
      throw error;
    }
    if (!action.alive()) return false;
    intake = payload;
    intakeVersion = record.version;
    intakeFingerprint = fingerprint;
    intakeConflict = null;
    deps.changed?.();
    return true;
  }

  function scheduleDraftSave(): void {
    if (saveTimer !== null) clearTimeout(saveTimer);
    const scheduled = deps.beginAction();
    saveTimer = setTimeout(() => {
      saveTimer = null;
      if (!scheduled.alive()) return;
      void saveIntakeNow().then(() => deriveState()).then(() => deps.changed?.());
    }, DRAFT_DEBOUNCE_MS);
  }

  async function resolveConflict(picks: Record<string, "mine" | "theirs">): Promise<boolean> {
    const action = deps.beginAction();
    const pid = action.projectId;
    if (!pid || !intakeConflict) return false;
    const latest = await deps.repository.documents.getLatest(pid, INTAKE_KIND, INTAKE_DOCUMENT_ID);
    const latestPayload = latest && latest.payload ? latest.payload : {};
    const latestVersion = latest ? latest.version : intakeConflict.version;
    const unresolved = intakeConflict.unresolved || [];
    const resolved: Record<string, unknown> = {};
    for (const item of unresolved) {
      resolved[item.field] = picks[item.field] === "theirs" ? item.theirs : item.mine;
    }
    const base = latestPayload && typeof latestPayload === "object" ? latestPayload : {};
    const merged = mergeIntakePayloads(base, Object.assign({}, base, resolved), base);
    const record = merged && merged.merged && merged.record
      ? merged.record
      : { ...emptyProductInput(), ...(isPlainObject(base) ? base as object : {}), ...resolved };
    const saved = await deps.repository.documents.save(pid, {
      kind: INTAKE_KIND, documentId: INTAKE_DOCUMENT_ID,
      payload: record as ProductInput, expectedVersion: latestVersion,
    }) as StoredDocumentRecord<ProductInput>;
    if (!action.alive()) return false;
    intake = record as ProductInput;
    intakeVersion = saved.version;
    intakeFingerprint = fingerprintOf(record as CompleteProductInput);
    intakeConflict = null;
    deps.changed?.();
    return true;
  }

  async function addReferences(files: FileList | File[] | null | undefined,
    report?: (kind: "too_many" | "too_large" | "unreadable" | "duplicate", file: File) => void): Promise<number> {
    const list = [...(files || [])];
    if (!list.length) return 0;
    const action = deps.beginAction();
    if (!action.projectId) return 0;
    const known = new Set(intake.references.map((item) => item.asset_sha256));
    let wantsPrimary = !intake.references.some((item) => item.role === "primary");
    let added = 0;
    for (const file of list) {
      if (intake.references.length >= MAX_REFERENCES) { report?.("too_many", file); break; }
      if (file.size > MAX_REFERENCE_IMAGE_BYTES) { report?.("too_large", file); continue; }
      let width: number | null = null;
      let height: number | null = null;
      try {
        const bitmap = await createImageBitmap(file);
        width = bitmap.width; height = bitmap.height; bitmap.close();
      } catch { report?.("unreadable", file); continue; }
      if (!action.alive()) break;
      const role = wantsPrimary ? "primary" : "other";
      const asset = await deps.repository.assets.put(action.projectId, {
        blob: file, mediaType: file.type || "application/octet-stream",
        originalName: file.name, role, width, height,
      });
      if (known.has(asset.sha256)) { report?.("duplicate", file); continue; }
      known.add(asset.sha256);
      if (action.alive()) intake.references.push(referenceFromAsset(asset, { role }));
      wantsPrimary = false;
      added += 1;
    }
    if (added) await saveIntakeNow();
    return added;
  }

  async function setReferenceRole(index: number, role: ReferenceRole): Promise<void> {
    const entry = intake.references[index];
    if (!entry) return;
    entry.role = role;
    await saveIntakeNow();
  }

  async function removeReference(index: number): Promise<void> {
    if (!intake.references[index]) return;
    intake.references.splice(index, 1);
    await saveIntakeNow();
  }

  async function persistSlot(slot: FactSlot, pid: string, action: ActionSnapshot | null,
    expectedVersion: number | null = null): Promise<StoredDocumentRecord<FactSlot>> {
    const record = await deps.repository.documents.save(pid, {
      kind: SLOT_KIND, documentId: slot.slot_id, payload: slot, expectedVersion,
    }) as StoredDocumentRecord<FactSlot>;
    if (!action || action.alive()) {
      slots.set(slot.slot_id, { slot: record.payload, version: record.version });
    }
    return record;
  }

  async function ensureCoreSlots(): Promise<number> {
    const action = deps.beginAction();
    const pid = action.projectId;
    if (!pid) return 0;
    let created = 0;
    const { CORE_SLOT_REGISTRY } = await import("./domain/index.js");
    for (const definition of CORE_SLOT_REGISTRY as { slot_id: string; label: string;
      value_type: FactSlot["value_type"]; critical: boolean }[]) {
      if (slots.has(definition.slot_id)) continue;
      await persistSlot({
        schema_version: FACT_SLOT_SCHEMA_VERSION, slot_id: definition.slot_id,
        label: definition.label, authority: "core_fixed", value_type: definition.value_type,
        value: null, source: "system_default", status: "missing", confidence: null,
        evidence: [], depends_on: [], critical: definition.critical,
      }, pid, action);
      created += 1;
    }
    return created;
  }

  function baseSlotFor(raw: FactSlot & { model_id?: string }, proposalIds: Set<string>): FactSlot | null {
    const definition = raw.authority === "core_fixed" ? coreSlotDefinition(raw.slot_id) : null;
    if (raw.authority === "core_fixed" && !definition) return null;
    const known = new Set(slots.keys());
    const base: FactSlot = {
      schema_version: FACT_SLOT_SCHEMA_VERSION, slot_id: raw.slot_id,
      label: definition ? definition.label : raw.label, authority: raw.authority,
      value_type: definition ? definition.value_type : raw.value_type,
      value: null, source: "system_default", status: "missing", confidence: null,
      evidence: [], depends_on: (raw.depends_on || []).filter((id) => proposalIds.has(id) || known.has(id)),
      critical: definition ? definition.critical : (raw as { critical?: boolean }).critical === true,
    };
    if (base.value_type === "enum") {
      base.enum_values = Array.isArray((raw as { enum_values?: unknown }).enum_values)
        ? [...(raw as { enum_values: string[] }).enum_values] : [];
    }
    if (base.authority === "user_custom") base.allow_model_proposal = true;
    return base;
  }

  async function applyProposal(proposal: SemanticProposal, pid: string, action: ActionSnapshot,
    source: SemanticAnalysisSource): Promise<{ applied: number; problems: string[] }> {
    const rawSlots = Array.isArray(proposal.slots) ? proposal.slots : [];
    const proposalIds = new Set(rawSlots.map((item) => item && item.slot_id).filter(Boolean));
    const problems: string[] = [];
    let applied = 0;
    for (const raw of rawSlots) {
      if (!await sourceIsCurrent(source, action)) {
        problems.push("资料已变化；其余提案仅保留在原资料的分析记录中，没有继续写入当前槽位。");
        break;
      }
      try {
        const existing = slots.get(raw.slot_id);
        const base = existing ? existing.slot : baseSlotFor(raw, proposalIds);
        if (!base) { problems.push(raw.slot_id + "：模型把未知槽位标成系统固定槽位，已拒绝。"); continue; }
        const next = applySlotAction(base, { action: "propose", actor: "model",
          value: raw.value, confidence: raw.confidence, evidence: raw.evidence }) as FactSlot & { model_id?: string };
        if (typeof raw.model_id === "string") next.model_id = raw.model_id;
        next.evidence.push({ kind: "model", ref: "product_input:" + source.document_id + "@v" + source.version,
          note: "本次提案使用的原资料快照；不是人工确认。" });
        await persistSlot(next, pid, action, existing ? existing.version : 0);
        applied += 1;
      } catch (error) {
        const slotId = raw && raw.slot_id ? raw.slot_id : "未知槽位";
        problems.push(slotId + "：" + messageOf(error, "提案被拒绝"));
      }
    }
    return { applied, problems };
  }

  async function sourceIsCurrent(source: SemanticAnalysisSource, action: ActionSnapshot): Promise<boolean> {
    if (!action.alive() || !action.projectId || intakeConflict?.unresolved?.length) return false;
    if (source.fingerprint !== fingerprintOf(currentIntakePayload())) return false;
    const pid = action.projectId;
    const stored = await deps.repository.documents.getLatest(pid, INTAKE_KIND, source.document_id);
    return action.alive() && stored !== null
      && source.fingerprint === fingerprintOf(productInputFromStored(stored.payload) as CompleteProductInput)
      && source.fingerprint === fingerprintOf(currentIntakePayload());
  }

  async function prepareAnalysis(action: ActionSnapshot): Promise<PreparedAnalysis> {
    const authorizedPayload = currentIntakePayload();
    const fingerprint = fingerprintOf(authorizedPayload);
    const capabilities = deps.capabilities();
    const provider = capabilities?.provider;
    const headers = deps.settings.headers("semantic");
    if (!provider || provider.configured === false) throw new Error("此用途缺少有效模型或凭据；人工填写不受影响。");
    const providerId = provider.provider_id;
    const modelId = provider.model_id;
    if (typeof providerId !== "string" || typeof modelId !== "string") {
      throw new Error("此用途缺少有效模型或凭据；人工填写不受影响。");
    }
    const pid = action.projectId;
    if (!pid) throw new Error("缺少项目上下文；没有调用模型，请核对后明确发起。");
    await saveIntakeNow();
    if (!action.alive() || fingerprint !== intakeFingerprint || intakeConflict?.unresolved?.length) {
      throw new Error("资料已变化或存在未解决冲突；没有调用模型，请核对后明确发起。");
    }
    const readiness = intakeReadiness(authorizedPayload);
    if (!readiness.ready) {
      const detail = readiness.blocking.map(item => item.message).join("；");
      throw new Error(detail ? "商品资料还不完整：" + detail + "。" : "商品资料还不完整。");
    }
    const version = intakeVersion;
    await ensureCoreSlots();
    return {
      source: { document_id: INTAKE_DOCUMENT_ID, version, fingerprint, payload: authorizedPayload },
      provider: { provider_id: providerId, model_id: modelId,
        credential_source: provider.credential_source || "none" },
      body: await buildAnalyzeBody(pid, provider, authorizedPayload),
      headers,
    };
  }

  async function buildAnalyzeBody(pid: string, semanticProvider: unknown, payload: CompleteProductInput) {
    if (!pid) throw new Error("缺少项目上下文，无法读取参考图字节。");
    const providerCaps: Record<string, unknown> = isPlainObject(semanticProvider)
      && isPlainObject(semanticProvider.capabilities) ? semanticProvider.capabilities : {};
    const vision = providerCaps.vision === true || providerCaps.supports_images === true;
    const selected = vision
      ? [...payload.references.filter(ref => ref.role === "primary"),
        ...payload.references.filter(ref => ref.role !== "primary")].slice(0, 3) : [];
    const imageHashes = new Set(selected.map(ref => ref.asset_sha256));
    const references: { sha256: string; media_type: string; role: ReferenceRole;
      original_name: string | null }[] = [];
    const referenceImages: { role: string; media_type: string; sha256: string;
      data_base64: string }[] = [];
    for (const entry of payload.references) {
      const asset = await deps.repository.assets.get(pid, entry.asset_sha256);
      if (!asset) {
        throw new Error("参考图资产缺失（sha256 " + entry.asset_sha256.slice(0, 12) + "…），请重新上传。");
      }
      references.push({ sha256: asset.sha256, media_type: asset.media_type || "application/octet-stream",
        role: entry.role, original_name: asset.original_name || null });
      if (!imageHashes.has(entry.asset_sha256)) continue;
      if (!(asset.blob instanceof Blob) || !["image/png", "image/jpeg"].includes(asset.media_type)
          || asset.blob.size > 4 * 1024 * 1024) {
        throw new Error("图文理解每张参考图须为 PNG/JPEG 且不超过 4MiB；仅文字理解不会发送这些字节。");
      }
      if (await sha256Hex(await asset.blob.arrayBuffer()) !== entry.asset_sha256) {
        throw new Error("参考图字节与本地哈希不一致，没有外发。");
      }
      referenceImages.push({ role: entry.role, media_type: asset.media_type,
        sha256: entry.asset_sha256, data_base64: await blobToBase64(asset.blob) });
    }
    const body = {
      product_name: payload.product_name, description: payload.description,
      selling_points: payload.selling_points, focus: payload.focus, references,
      ...(vision ? { reference_images: referenceImages } : {}),
      locale: ANALYZE_LOCALE, platform: ANALYZE_PLATFORM,
      max_slots: ANALYZE_MAX_SLOTS, existing_slot_ids: [],
    };
    const declared = (isPlainObject(semanticProvider) && isPlainObject(semanticProvider.capabilities)
      ? semanticProvider.capabilities.analyze_fields : undefined) || deps.capabilities()?.analyze_fields;
    const allowed = isStringArray(declared) && declared.length
      ? declared : [...DEFAULT_ANALYZE_FIELDS];
    const BODY_KEYS = ["product_name", "description", "selling_points", "focus", "references",
      "reference_images", "locale", "platform", "max_slots", "existing_slot_ids"];
    const allowedSet = new Set(allowed);
    const filtered: Record<string, unknown> = { ...body };
    for (const key of BODY_KEYS) if (!allowedSet.has(key)) delete filtered[key];
    return filtered as unknown as PreparedAnalysis["body"];
  }

  async function runAnalysis(options: { allowNewAfterUnknown?: boolean } = {}): Promise<AnalysisOutcome> {
    const action = deps.beginAction();
    analyzeProblems = [];
    analyzeRequiresConfirmation = false;
    const pending = semanticAnalysis.run({ allowNewAfterUnknown: options.allowNewAfterUnknown });
    try {
      const outcome = await pending;
      if (!action.alive()) return outcome;
      if (outcome.kind === "requires_confirmation") {
        analyzeRequiresConfirmation = true;
      } else if (outcome.kind === "failed" || outcome.kind === "unknown") {
        analyzeRequiresConfirmation = outcome.kind === "unknown";
      } else if (outcome.kind === "applied") {
        const { proposal, applied, record } = outcome;
        analyzeProblems = applied.problems;
        lastAnalyze = {
          at: new Date(record.updated_at).toLocaleString("zh-CN", { hour12: false }),
          provider: proposal.meta.provider_id, model: proposal.meta.model_id,
          slots: proposal.slots.length, applied: applied.applied, summary: proposal.summary,
          sourceVersion: record.source.version, referenceImagesSent: record.reference_images_sent,
          imageProvenance: [...(record.image_provenance || [])],
        };
        if (proposal.questions.length) analyzeProblems.push("模型提出的问题：" + proposal.questions.join(" / "));
      }
      return outcome;
    } finally {
      if (action.alive()) {
        try { await deriveState(); } catch { /* 派生失败由调用方渲染既有错误面。 */ }
        deps.changed?.();
      }
    }
  }

  function isAnalysisRunning(): boolean {
    return semanticAnalysis.isRunning();
  }

  function analyzeState() {
    return { requiresConfirmation: analyzeRequiresConfirmation, problems: analyzeProblems, last: lastAnalyze };
  }

  async function slotAction(slotId: string, spec: SlotActionSpec): Promise<void> {
    const action = deps.beginAction();
    const pid = action.projectId;
    if (!pid) return;
    const entry = slots.get(slotId);
    if (!entry) throw new Error("找不到这个事实槽位。");
    const next = applySlotAction(entry.slot, spec);
    await persistSlot(next, pid, action);
    if (!action.alive()) return;
    await deriveState();
    deps.changed?.();
  }

  async function addCustomSlot(candidate: FactSlot): Promise<void> {
    const action = deps.beginAction();
    const pid = action.projectId;
    if (!pid) return;
    const problems = checkFactSlot(candidate);
    if (problems.length) throw new Error(problems.map((item) => item.message).join("；"));
    if (!canAddSlot(candidate, "user", { existingSlots: slotEntries().map((item) => item.slot) })) {
      throw new Error("槽位标识已存在，或这个槽位不允许新增。");
    }
    await persistSlot(candidate, pid, action);
    if (!action.alive()) return;
    await deriveState();
    deps.changed?.();
  }

  async function applySuiteOp(run: () => { plan: SuitePlan } & Record<string, unknown>): Promise<boolean> {
    const action = deps.beginAction();
    const pid = action.projectId;
    if (!pid) return false;
    const result = run();
    const nextPlan = result.plan;
    const problems = validateSuitePlan(nextPlan);
    if (problems.length > 0) throw new Error(problems[0].message);
    const saved = await deps.repository.documents.save(pid, {
      kind: SUITE_KIND, documentId: SUITE_PLAN_DOCUMENT_ID,
      payload: nextPlan, expectedVersion: suiteVersion,
    });
    if (!action.alive()) return false;
    suitePlan = nextPlan;
    suiteVersion = typeof saved.version === "number" ? saved.version : suiteVersion + 1;
    await deriveState();
    deps.changed?.();
    return true;
  }

  async function seedPlan(): Promise<boolean> {
    return applySuiteOp(() => ({ plan: seedSuitePlan(suiteContext()).plan as SuitePlan }));
  }

  async function addShotFromTemplateCmd(templateId: string): Promise<boolean> {
    const plan = suitePlan;
    if (!plan) return false;
    return applySuiteOp(() => addShotFromTemplate(plan, templateId, { context: suiteContext() }) as unknown as { plan: SuitePlan });
  }

  async function addCustomShot(label: string, intent: string): Promise<boolean> {
    const plan = suitePlan;
    if (!plan) return false;
    return applySuiteOp(() => addCustomShotToPlan(plan, { label, intent }) as unknown as { plan: SuitePlan });
  }

  async function suiteOp1(name: "moveShot" | "copyShot" | "removeShot", shotId: string, deltaOrId?: number | string): Promise<boolean> {
    const plan = suitePlan;
    if (!plan) return false;
    if (name === "moveShot") return applySuiteOp(() => moveShot(plan, shotId, deltaOrId as number) as unknown as { plan: SuitePlan });
    if (name === "copyShot") return applySuiteOp(() => copyShot(plan, shotId) as unknown as { plan: SuitePlan });
    return applySuiteOp(() => removeShot(plan, shotId) as unknown as { plan: SuitePlan });
  }
  async function moveShotCmd(shotId: string, delta: number): Promise<boolean> {
    return suiteOp1("moveShot", shotId, delta);
  }
  async function copyShotCmd(shotId: string): Promise<boolean> {
    return suiteOp1("copyShot", shotId);
  }
  async function removeShotCmd(shotId: string): Promise<boolean> {
    return suiteOp1("removeShot", shotId);
  }
  async function saveStyle(next: StyleSpec): Promise<void> {
    const action = deps.beginAction();
    const pid = action.projectId;
    if (!pid) return;
    assertStyleSpec(next);
    const record = await deps.repository.documents.save(pid, {
      kind: STYLE_KIND, documentId: STYLE_SPEC_DOCUMENT_ID, payload: next,
      expectedVersion: styleVersion,
    });
    if (!action.alive()) return;
    styleSpec = next;
    styleVersion = record.version;
    deps.changed?.();
  }
  async function restoreStyle(): Promise<number> {
    const action = deps.beginAction();
    const pid = action.projectId;
    if (!pid || styleVersion <= 1) throw new Error("没有更早的版本可以恢复。");
    const versions = await deps.repository.documents.listVersions(pid, STYLE_KIND, STYLE_SPEC_DOCUMENT_ID);
    const target = previousVersionOf(versions, styleVersion);
    if (!target) throw new Error("没有更早的版本可以恢复。");
    const restored = { ...emptyStyleSpec(), ...(target.payload as Partial<StyleSpec>) };
    const record = await deps.repository.documents.save(pid, {
      kind: STYLE_KIND, documentId: STYLE_SPEC_DOCUMENT_ID,
      payload: restored, expectedVersion: styleVersion,
    });
    if (!action.alive()) return 0;
    styleSpec = restored;
    styleVersion = record.version;
    deps.changed?.();
    return record.version;
  }
  async function saveShotSpec(shotId: string, changes: Partial<ShotSpec>): Promise<void> {
    const action = deps.beginAction();
    const pid = action.projectId;
    if (!pid || !suitePlan) return;
    const shot = suitePlan.shots.find((item) => (item as PlanShot).shot_id === shotId);
    if (!shot) throw new Error("找不到这张图，可能已被删除。");
    const entry = shotSpecEntry(shotId);
    const base = entry ? entry.spec : emptyShotSpecFromShot(shot);
    const next = { ...base, ...changes };
    assertShotSpec(next);
    const record = await deps.repository.documents.save(pid, {
      kind: SHOT_SPEC_KIND, documentId: shotId, payload: next,
      expectedVersion: entry ? entry.version : 0,
    });
    if (!action.alive()) return;
    shotSpecs.set(shotId, { spec: next, version: record.version });
    deps.changed?.();
  }
  async function restoreShotSpec(shotId: string): Promise<void> {
    const action = deps.beginAction();
    const pid = action.projectId;
    if (!pid) return;
    const entry = shotSpecEntry(shotId);
    if (!entry || entry.version <= 1) throw new Error("没有更早的版本可以恢复。");
    const versions = await deps.repository.documents.listVersions(pid, SHOT_SPEC_KIND, shotId);
    const target = previousVersionOf(versions, entry.version);
    if (!target) throw new Error("没有更早的版本可以恢复。");
    const restored = target.payload as ShotSpec;
    const record = await deps.repository.documents.save(pid, {
      kind: SHOT_SPEC_KIND, documentId: shotId, payload: restored, expectedVersion: entry.version,
    });
    if (!action.alive()) return;
    shotSpecs.set(shotId, { spec: restored, version: record.version });
    deps.changed?.();
  }

  async function deriveState(): Promise<void> {
    const action = deps.beginAction();
    if (!action.projectId) return;
    understandingBlocking = [];
    understandingError = null;
    understandingReady = false;
    try {
      const brief = buildProductBrief(slotEntries());
      const readiness = briefReadiness(brief);
      understandingReady = readiness.ready;
      understandingBlocking = readiness.blocking;
    } catch (error) {
      understandingError = error;
    }
  }

  // 语义分析执行归本所有者：source-bound，不向 workspace 暴露可注入的执行器。
  const semanticAnalysis = createSemanticAnalysisModule({
    repository: deps.repository, beginAction: deps.beginAction,
    prepare: prepareAnalysis, sourceIsCurrent, apply: applyProposal,
  });

  return {
    reset, restore, scheduleDraftSave, saveIntakeNow, currentIntakePayload,
    intakeSnapshot,
    draftVersion, conflict, resolveConflict, addReferences, setReferenceRole,
    removeReference, references, ensureCoreSlots, slotAction, addCustomSlot,
    slotEntries, runAnalysis, isAnalysisRunning, analyzeState, applySuiteOp,
    seedPlan, addShotFromTemplate: addShotFromTemplateCmd, addCustomShot,
    moveShot: moveShotCmd, copyShot: copyShotCmd, removeShot: removeShotCmd,
    suiteContext, sources, suitePlan: () => suitePlan, suiteVersion: () => suiteVersion,
    styleSpec: () => styleSpec, styleVersion: () => styleVersion,
    shotSpecEntry, shotSpecsById, saveStyle, restoreStyle, saveShotSpec,
    restoreShotSpec, understanding, deriveState,
    prepareAnalysis, sourceIsCurrent, applyProposal,
  };
}
