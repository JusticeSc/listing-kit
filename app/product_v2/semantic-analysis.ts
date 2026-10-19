import { checkFactSlot, isPlainObject, newActionId } from "./domain/index.js";
import type { FactSlot, SemanticAnalysisFailure, SemanticAnalysisRecord,
  SemanticAnalysisSource, SemanticProposal } from "./domain/type-contracts.js";
import type { ProjectRepository } from "./storage/validate.js";

export interface AnalysisAction {
  readonly generation: number;
  readonly projectId: string | null;
  alive(): boolean;
}
export interface CopyTargetSnapshot {
  slot_id: string;
  version: number;
  label: string;
  value_type: "text" | "text_list";
  value: string | string[];
}
export interface SemanticRequestBody {
  product_name: string;
  description: string;
  selling_points: string[];
  focus: string;
  references: { role: string; media_type: string; sha256: string }[];
  reference_images?: { role: string; media_type: string; sha256: string; data_base64: string }[];
  locale: string;
  platform: string;
  max_slots: number;
  existing_slot_ids: string[];
  copy_targets?: CopyTargetSnapshot[];
}
export interface PreparedAnalysis {
  source: SemanticAnalysisSource;
  provider: SemanticAnalysisRecord["provider"];
  body: SemanticRequestBody;
  headers: Readonly<Record<string, string>>;
}
export interface CopyProposalDraft {
  text: string;
  source_slot_id: string;
  source_slot_version: number;
  provider: string;
  model: string | null;
  requestedAt: string;
}
export interface AppliedProposal { applied: number; problems: string[] }
export interface SemanticAnalysisDependencies {
  repository: ProjectRepository;
  beginAction(): AnalysisAction;
  prepare(action: AnalysisAction): Promise<PreparedAnalysis>;
  sourceIsCurrent(source: SemanticAnalysisSource, action: AnalysisAction): Promise<boolean>;
  apply(proposal: SemanticProposal, projectId: string, action: AnalysisAction,
    source: SemanticAnalysisSource): Promise<AppliedProposal>;
}
export interface CopyProposalDependencies {
  repository: ProjectRepository;
  beginAction(): AnalysisAction;
  prepareCopy(action: AnalysisAction, targets: { slot_id: string; version: number }[]): Promise<PreparedAnalysis>;
  copyTargetsCurrent(prepared: PreparedAnalysis, action: AnalysisAction): Promise<boolean>;
}
export type CopyOutcome =
  | { kind: "skipped"; action: AnalysisAction }
  | { kind: "not_sent"; action: AnalysisAction; message: string }
  | { kind: "failed" | "unknown"; action: AnalysisAction; error: SemanticAnalysisFailure }
  | { kind: "stale"; action: AnalysisAction; record: SemanticAnalysisRecord }
  | { kind: "proposed"; action: AnalysisAction; record: SemanticAnalysisRecord;
      proposals: CopyProposalDraft[] };
export type AnalysisOutcome =
  | { kind: "skipped"; action: AnalysisAction }
  | { kind: "not_sent"; action: AnalysisAction; message: string }
  | { kind: "requires_confirmation"; action: AnalysisAction }
  | { kind: "failed" | "unknown"; action: AnalysisAction; error: SemanticAnalysisFailure }
  | { kind: "stale"; action: AnalysisAction; record: SemanticAnalysisRecord }
  | { kind: "apply_failed"; action: AnalysisAction; record: SemanticAnalysisRecord; message: string }
  | { kind: "applied"; action: AnalysisAction; record: SemanticAnalysisRecord;
      proposal: SemanticProposal; applied: AppliedProposal };

function isProposalSlot(value: unknown): value is FactSlot & { model_id?: string } {
  return isPlainObject(value) && checkFactSlot(value).length === 0
    && value.status === "proposed" && value.source === "model_inference"
    && (value.authority === "core_fixed" || value.authority === "category_dynamic")
    && typeof value.confidence === "number" && Number.isFinite(value.confidence)
    && value.confidence >= 0 && value.confidence <= 1
    && (value.model_id === undefined || typeof value.model_id === "string");
}
function isCopyProposal(value: unknown): value is { text: string; source_slot_id: string;
  source_slot_version: number } {
  return isPlainObject(value) && typeof value.text === "string" && value.text.trim().length > 0
    && value.text.length <= 60 && typeof value.source_slot_id === "string"
    && value.source_slot_id.length > 0 && typeof value.source_slot_version === "number"
    && Number.isInteger(value.source_slot_version) && value.source_slot_version >= 1;
}
function readProposal(value: unknown, prepared: PreparedAnalysis): SemanticProposal {
  if (!isPlainObject(value) || !Array.isArray(value.slots) || !value.slots.every(isProposalSlot)
    || typeof value.summary !== "string" || !Array.isArray(value.questions)
    || !value.questions.every((question): question is string => typeof question === "string")
    || !isPlainObject(value.meta)) throw new Error("商品理解返回了非法提案；没有写入事实槽位。");
  const meta = value.meta;
  if (meta.provider_id !== prepared.provider.provider_id || meta.model_id !== prepared.provider.model_id
    || typeof meta.reference_images_sent !== "boolean"
    || meta.reference_images_sent !== Boolean(prepared.body.reference_images?.length)
    || !Array.isArray(meta.inputs_used)
    || !meta.inputs_used.every((input): input is string => typeof input === "string")
    || (meta.reference_images_sent && !meta.inputs_used.includes("actual_images"))
    || (meta.request_id !== null && typeof meta.request_id !== "string")) {
    throw new Error("商品理解的模型或实际看图身份与本次发送不符；没有写入事实槽位。");
  }
  // 文案提议与事实提案二选一：未请求时响应里出现 copy_proposals 即非法（两种产出不混装）。
  const copyMode = Array.isArray(prepared.body.copy_targets) && prepared.body.copy_targets.length > 0;
  if (!copyMode && value.copy_proposals !== undefined) {
    throw new Error("商品理解返回了未请求的候选文案；没有写入事实槽位。");
  }
  if (copyMode && (!Array.isArray(value.copy_proposals) || !value.copy_proposals.every(isCopyProposal))) {
    throw new Error("候选文案返回了非法形状；没有写入任何提议。");
  }
  if (copyMode && value.slots.length > 0) {
    throw new Error("候选文案与事实提案不能混装；没有写入任何提议。");
  }
  return { slots: value.slots, summary: value.summary, questions: value.questions,
    ...(copyMode ? { copy_proposals: value.copy_proposals as SemanticProposal["copy_proposals"] } : {}),
    meta: { provider_id: prepared.provider.provider_id, model_id: prepared.provider.model_id,
      request_id: meta.request_id, reference_images_sent: meta.reference_images_sent,
      inputs_used: meta.inputs_used } };
}
function readFailure(value: unknown, status: number): SemanticAnalysisFailure {
  const error = isPlainObject(value) && isPlainObject(value.error) ? value.error : {};
  return {
    family: typeof error.family === "string" ? error.family : "provider_unknown",
    code: typeof error.code === "string" ? error.code : "ANALYZE_RESPONSE_UNKNOWN",
    message: typeof error.message === "string" ? error.message : "商品理解未返回可核对的结果（HTTP " + status + "）。",
    retry_policy: typeof error.retry_policy === "string" ? error.retry_policy : "requires_review",
  };
}
function messageOf(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}
/** 同一请求/保存/失败生命周期的唯一私有所有者：事实提案与候选文案共用，产出选择留在各自公开 run。
 * 只做请求前的准备（prepare）、三个当前性复核（isCurrent）与终态落库：不做自动重试，
 * Unknown 必落 unknown 并返回调用方；成功后由各自 run 决定 applied/proposed。 */
type SemanticRequestTexts = {
  prepareFallback: string;
  changedBeforePrepare: string;
  changedBeforeSend: string;
  unknownMessage: string;
  invalidFallback: string;
};
/** 成功态记录的精确类型：交还各自 run 做终态推进（applied/提议回显）时，
 * proposal/error/disposition 保持非空窄类型，不靠调用侧重新收窄。 */
type SucceededAnalysisRecord = Omit<SemanticAnalysisRecord,
  "state" | "proposal" | "error" | "disposition"> & {
  state: "succeeded"; proposal: SemanticProposal; error: null;
  disposition: "stored" | "stale" | "applied";
};
type SemanticSettled =
  | { kind: "ready"; record: SucceededAnalysisRecord;
      proposal: SemanticProposal; prepared: PreparedAnalysis; requestedAt: string;
      saveNext(record: SemanticAnalysisRecord): Promise<void> }
  | { kind: "not_sent"; action: AnalysisAction; message: string }
  | { kind: "failed" | "unknown"; action: AnalysisAction; error: SemanticAnalysisFailure }
  | { kind: "stale"; action: AnalysisAction; record: SemanticAnalysisRecord };
async function runSemanticRequest(options: {
  repository: ProjectRepository; action: AnalysisAction; projectId: string;
  prepare(): Promise<PreparedAnalysis>;
  isCurrent(prepared: PreparedAnalysis): Promise<boolean>;
  texts: SemanticRequestTexts;
}): Promise<SemanticSettled> {
  const { repository, action, projectId, prepare, isCurrent, texts } = options;
  let prepared: PreparedAnalysis;
  try { prepared = await prepare(); }
  catch (error) { return { kind: "not_sent", action,
    message: messageOf(error, texts.prepareFallback) }; }
  if (!action.alive() || !await isCurrent(prepared)) {
    return { kind: "not_sent", action, message: texts.changedBeforePrepare };
  }
  const requestedAt = new Date().toISOString();
  const sentImages = prepared.body.reference_images || [];
  const imageProvenance = sentImages.map((item) => ({ role: String(item.role),
    media_type: String(item.media_type), sha256: String(item.sha256) }));
  const base = { schema_version: 1 as const, action_id: newActionId(), source: prepared.source,
    provider: prepared.provider, created_at: requestedAt, updated_at: requestedAt,
    reference_images_sent: sentImages.length > 0, image_provenance: imageProvenance };
  let version = 0;
  async function save(record: SemanticAnalysisRecord): Promise<void> {
    const saved = await repository.documents.save(projectId, { kind: "semantic_analysis",
      documentId: base.action_id, payload: record, expectedVersion: version });
    version = saved.version;
  }
  await save({ ...base, state: "pending_submit", proposal: null, error: null, disposition: "not_applied" });
  if (!action.alive() || !await isCurrent(prepared)) {
    const error = { family: "input_rejected", code: "SOURCE_CHANGED_BEFORE_SEND",
      message: texts.changedBeforeSend, retry_policy: "fatal" };
    await save({ ...base, updated_at: new Date().toISOString(), state: "failed",
      proposal: null, error, disposition: "not_applied" });
    return { kind: "not_sent", action, message: error.message };
  }
  let response: Response;
  let payload: unknown;
  try {
    response = await fetch("/api/v2/semantic/analyze", { method: "POST",
      headers: { "Content-Type": "application/json", ...prepared.headers },
      body: JSON.stringify(prepared.body) });
    payload = await response.json();
  } catch {
    const error = { family: "provider_unknown", code: "ANALYZE_OUTCOME_UNKNOWN",
      message: texts.unknownMessage, retry_policy: "requires_review" };
    await save({ ...base, updated_at: new Date().toISOString(), state: "unknown",
      proposal: null, error, disposition: "not_applied" });
    return { kind: "unknown", action, error };
  }
  if (!response.ok || !isPlainObject(payload) || payload.ok !== true) {
    const error = readFailure(payload, response.status);
    const unknown = error.family === "provider_unknown" || response.status >= 500;
    await save({ ...base, updated_at: new Date().toISOString(), state: unknown ? "unknown" : "failed",
      proposal: null, error, disposition: "not_applied" });
    return { kind: unknown ? "unknown" : "failed", action, error };
  }
  let proposal: SemanticProposal;
  try { proposal = readProposal(payload.proposal, prepared); }
  catch (error) {
    const failure = { family: "invalid_response", code: "PROPOSAL_INVALID",
      message: messageOf(error, texts.invalidFallback), retry_policy: "requires_review" };
    await save({ ...base, updated_at: new Date().toISOString(), state: "failed",
      proposal: null, error: failure, disposition: "not_applied" });
    return { kind: "failed", action, error: failure };
  }
  let record: SucceededAnalysisRecord = {
    ...base, updated_at: new Date().toISOString(),
    state: "succeeded", proposal, error: null, disposition: "stored" };
  await save(record);
  if (!action.alive() || !await isCurrent(prepared)) {
    record = { ...record, updated_at: new Date().toISOString(), disposition: "stale" };
    await save(record);
    return { kind: "stale", action, record };
  }
  return { kind: "ready", record, proposal, prepared, requestedAt, saveNext: save };
}

/** Source-bound business execution. Headers/bytes live only inside this invocation. */
export function createSemanticAnalysisModule(deps: SemanticAnalysisDependencies) {
  const inFlight = new Set<string>();
  const keyOf = (action: AnalysisAction) => action.projectId + "@" + action.generation;
  function isRunning(): boolean { return inFlight.has(keyOf(deps.beginAction())); }

  async function run({ allowNewAfterUnknown = false } = {}): Promise<AnalysisOutcome> {
    const action = deps.beginAction();
    const projectId = action.projectId;
    const flightKey = keyOf(action);
    if (!projectId || inFlight.has(flightKey)) return { kind: "skipped", action };
    const pid: string = projectId;
    inFlight.add(flightKey);
    try {
      const previous = await deps.repository.documents.listLatest(pid, "semantic_analysis");
      const unresolved = previous.some(({ payload }) => isPlainObject(payload)
        && (payload.state === "pending_submit" || payload.state === "unknown"));
      if (unresolved && !allowNewAfterUnknown) return { kind: "requires_confirmation", action };
      const settled = await runSemanticRequest({
        repository: deps.repository, action, projectId: pid,
        prepare: () => deps.prepare(action),
        isCurrent: (prepared) => deps.sourceIsCurrent(prepared.source, action),
        texts: { prepareFallback: "本地资料尚未准备好；没有调用模型。",
          changedBeforePrepare: "资料已变化；没有发送旧资料，请核对后重新明确发起。",
          changedBeforeSend: "资料已变化；未发送旧资料。",
          unknownMessage: "理解结果未知，可能已经发送/计费；不会自动重试。",
          invalidFallback: "商品理解返回了非法提案。" },
      });
      if (settled.kind !== "ready") {
        if (settled.kind === "stale") return settled;
        if (settled.kind === "not_sent") return { kind: settled.kind, action, message: settled.message };
        return { kind: settled.kind, action, error: settled.error };
      }
      const { record, proposal, prepared, saveNext } = settled;
      let applied: AppliedProposal;
      try { applied = await deps.apply(proposal, projectId, action, prepared.source); }
      catch (error) { return { kind: "apply_failed", action, record,
        message: messageOf(error, "提案已保存到原资料，但写入事实槽位失败。") }; }
      const appliedRecord: SucceededAnalysisRecord = { ...record, updated_at: new Date().toISOString(), disposition: "applied" };
      await saveNext(appliedRecord);
      return { kind: "applied", action, record: appliedRecord, proposal, applied };
    } finally { inFlight.delete(flightKey); }
  }
  return { run, isRunning };
}

/**
 * 候选文案提议执行：与事实提案同一 POST 路由、同一记录形状，但产出只是提议。
 * 记录 disposition 恒为 stored（从不 applied）：提议不写入任何事实或规格，
 * 用户在规格区逐条确认后才由保存命令写入 on_image_texts。版本过期在返回后由调用方
 * 按目标槽位的当前版本复核（stale 不落库、不覆盖，只是不再展示）。
 */
export function createCopyProposalModule(deps: CopyProposalDependencies) {
  const inFlight = new Set<string>();
  const keyOf = (action: AnalysisAction) => action.projectId + "@" + action.generation + "@copy";
  function isRunning(): boolean { return inFlight.has(keyOf(deps.beginAction())); }

  async function run(targets: { slot_id: string; version: number }[]): Promise<CopyOutcome> {
    const action = deps.beginAction();
    const projectId = action.projectId;
    const flightKey = keyOf(action);
    if (!projectId || inFlight.has(flightKey)) return { kind: "skipped", action };
    const pid: string = projectId;
    inFlight.add(flightKey);
    try {
      const settled = await runSemanticRequest({
        repository: deps.repository, action, projectId: pid,
        prepare: () => deps.prepareCopy(action, targets),
        isCurrent: (prepared) => deps.copyTargetsCurrent(prepared, action),
        texts: { prepareFallback: "目标事实尚未就绪；没有调用模型。",
          changedBeforePrepare: "目标事实已变化；没有发送旧快照，请核对后重新明确发起。",
          changedBeforeSend: "目标事实已变化；未发送旧快照。",
          unknownMessage: "提议结果未知，可能已经发送/计费；不会自动重试。",
          invalidFallback: "候选文案返回了非法形状。" },
      });
      if (settled.kind !== "ready") return settled;
      const { record, proposal, prepared, requestedAt } = settled;
      // 只回显请求过的目标身份：响应里多出的来源一律丢弃（readProposal 已保证形状，这里保证归属）。
      const wanted = new Map((prepared.body.copy_targets || []).map((target) => [target.slot_id, target.version]));
      const proposals: CopyProposalDraft[] = (proposal.copy_proposals || [])
        .filter((item) => wanted.get(item.source_slot_id) === item.source_slot_version)
        .map((item) => ({ text: item.text, source_slot_id: item.source_slot_id,
          source_slot_version: item.source_slot_version,
          provider: prepared.provider.provider_id, model: prepared.provider.model_id, requestedAt }));
      return { kind: "proposed", action, record, proposals };
    } finally { inFlight.delete(flightKey); }
  }
  return { run, isRunning };
}
