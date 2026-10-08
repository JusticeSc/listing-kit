/** 人工采用/取消/Unknown 知悉的持久化顺序；不依赖 DOM，不自动选择最新候选。 */
import {
  DOMAIN_DOCUMENT_KINDS, REVIEW_REPORT_DOCUMENT_KIND, acknowledgementDocumentIdOf, assertSelectionRecord,
  buildAcknowledgement, buildReviewReport, buildSelectionRecord, buildSelectionSet, candidateMatchesAttempt,
  deriveSelectionState, emptyShotSpecFromShot, evaluateCandidateFindings,
  mergeVlmReview,
  newActionId, promptStaleness, reviewIsCurrent, reviewStatusOf, reviewSummaryText, selectionSummaryText,
  suitePlanSummary,
} from "./domain/index.js";
import { confirmedFacts, sourceContext } from "./prompts.js";
import { sha256Hex } from "./storage/db.js";
import { consumptionFence } from "./project-inputs.js";
import type { ProjectRepository } from "./storage/validate.js";
 import type { ActionSnapshot, GenerationModule } from "./generation.js";
 import type { ModelSettings } from "./model-settings.js";
 import type { ProjectSources, PromptModule } from "./prompts.js";
 import type { AcknowledgementRecord, CandidateRecord, ReviewReport, SelectionRecord,
   SelectionSet, SelectionState, UnknownItem, VlmOutcome } from "./domain/type-contracts.js";
 export type ReviewCandidateResult = {
   skipped?: true; failed?: true;
   reason?: string; message?: string;
   ok?: boolean; outcome?: VlmOutcome;
   candidate_id?: string; summary?: string;
 };

export type SelectionEntry = { record: SelectionRecord; version: number };
export type AdoptionSource = { candidate: CandidateRecord; version: number; report: ReviewReport | null };
export type AdoptionOutcome = {
  skipped?: true; reason?: string; record?: SelectionRecord; version?: number;
  candidateVersion?: number | null; currentSession: boolean;
};
export type SelectionProjection = {
  set: SelectionSet;
  /** 领域复核/交付接口明确要求 shot_id → candidate_id，而不是 SelectionRecord。 */
  candidateIds: Record<string, string>;
  records: Record<string, SelectionRecord>;
  states: Record<string, SelectionState>;
};
 export type AdoptionReportEntry = { report: ReviewReport; version: number };
 export type SelectionDependencies = {
   repository: ProjectRepository;
   generation: GenerationModule;
   prompts: PromptModule;
   settings: ModelSettings;
   beginAction(): ActionSnapshot;
   sources(): ProjectSources;
   changed?(): void;
 };
export interface SelectionAdoptionModule {
  reset(): void;
  restore(action: ActionSnapshot): Promise<void>;
  entryOf(shotId: string | null): SelectionEntry | null;
  stateOf(shotId: string): SelectionState;
  adoptedMark(shotId: string | null): { candidate_id: string | null; state: SelectionState } | null;
  sourceOf(shotId: string | null, candidateId: string | null): AdoptionSource | null;
  reportOf(candidateId: string): AdoptionReportEntry | null;
  summary(shotId: string): string;
  projection(source?: ProjectSources): SelectionProjection;
  select(kind: "select" | "clear", shotId: string, candidateId: string | null): Promise<AdoptionOutcome>;
  acknowledge(unknown: UnknownItem): Promise<{ record: AcknowledgementRecord; currentSession: boolean }>;
  acknowledgements(): AcknowledgementRecord[];
  candidateReviewRequest(shotId: string, candidate: CandidateRecord, projectId: string): Promise<unknown>;
  reviewCandidate(shotId: string, candidateId: string): Promise<ReviewCandidateResult>;
  /** 单图 AI 复核状态投影（V2.R6.2）：未发起=not_reviewed（未复核/未运行，不阻断采用）；
   * 真发起失败/未知=unknown；真跑过=reviewed。视图只读此投影，不重算 vlm 块。 */
  reviewStatusOf(candidateId: string): { status: "reviewed" | "unknown" | "not_reviewed"; reason: string | null };
  /** 确定性检查报告最近一次补建失败的原因(未失败为 null)：与"可选 AI 未复核"分开如实显示。 */
  reportBuildFailure(candidateId: string): string | null;
  isSelecting(): boolean;
  isReviewInFlight(shotId: string): boolean;
}

export function createSelectionAdoptionModule(deps: SelectionDependencies): SelectionAdoptionModule {
  let selections = new Map<string, SelectionEntry>();
  let acknowledgements = new Map<string, AcknowledgementRecord>();
  let selecting: object | null = null;
  let reviewReports = new Map<string, AdoptionReportEntry>();
  let reviewFlights = new Set<string>();
  // 确定性报告的单飞行与失败记忆(键=冻结项目/会话+候选身份+观察版本)。
  // 单飞行让并发消费(采用/AI 复核/订阅补建)共用同一份重建;失败记忆只用于避免订阅热循环
  // 并如实对外显示"补建失败"——它不是熔断,任何显式消费/重新打开/新版本都会重新补建。
  let reportFlights = new Map<string, Promise<AdoptionReportEntry | null>>();
  let reportFailures = new Map<string, { key: string; reason: string }>();
  function messageOf(error: unknown): string {
    if (error !== null && typeof error === "object" && "message" in error
      && typeof error.message === "string") return error.message;
    return "";
  }
  // 确定性报告的唯一消费者是 adoption：内存面就是这一份 Map（无第二份投影、无 setter 注入）。
  function reset() {
    selections = new Map(); acknowledgements = new Map(); selecting = null;
    reviewReports = new Map(); reviewFlights = new Set();
    reportFlights = new Map(); reportFailures = new Map();
    backfillFlight = null; backfillAgain = false;
  }
  /* ------------------------------------------ 候选变化 -> 缺失/过期报告补建 */
  // generation 是候选链唯一所有者；adoption 只读订阅其投影变化，在本地补缺失/过期报告。
  // 补建绝不发起 AI 复核（not_run 保持 not_run），失败不改变候选保全与原采用，也不抛给通知链。
  let backfillFlight: Promise<void> | null = null;
  let backfillAgain = false;
  async function backfillReports(action: ActionSnapshot, notifyViews: boolean): Promise<void> {
    if (!action.projectId) return;
    const source = deps.sources();
    const plan = source.suitePlan;
    const shots = plan && Array.isArray(plan.shots) ? plan.shots : [];
    let changed = false;
    for (const shot of shots) {
      if (!action.alive()) return;
      const shotId = typeof shot.shot_id === "string" ? shot.shot_id : null;
      const candidate = shotId ? deps.generation.latestStoredCandidateOf(shotId)?.record : null;
      if (!shotId || !candidate) continue;
      const stored = reviewReports.get(candidate.candidate_id) || null;
      // 已有当前报告即跳过：避免 review_report 版本无意义 +1。
      if (stored && stored.version > 0 && reviewIsCurrent(stored.report, candidate)) continue;
      const before = stored?.version || 0;
      const key = reportFlightKey(action, candidate, before);
      const failureBefore = reportFailures.get(candidate.candidate_id)?.key || "";
      // 同一候选同一观察版本刚失败过就先不重试(订阅可能连续触发)；显式消费/重新打开/新版本会再补建。
      if (failureBefore === key) continue;
      // 字节与报告构建都在 ensureReviewReport 内统一处理：失败会记下原因(不静默 continue)，
      // 绝不写"字节不可读"的降级报告冒充已检查，候选字节与原采用不受影响。
      const entry = await ensureReviewReport(shotId, candidate, null, action.projectId, { action });
      if (entry && entry.version > before) changed = true;
      if ((reportFailures.get(candidate.candidate_id)?.key || "") !== failureBefore) changed = true;
    }
    // 新增/更新了报告、或补建失败(需要如实显示失败原因)就刷一次视图投影(订阅异步补建时必需)；
    // 恢复路径不刷，由 loadWorkspace 之后的 renderAll 统一呈现，避免加载中途触发阶段外壳/渲染副作用。
    if (notifyViews && changed && action.alive()) deps.changed?.();
  }
  async function runBackfill(notifyViews = true): Promise<void> {
    if (backfillFlight) { backfillAgain = true; return backfillFlight; }
    const action = deps.beginAction();
    const flight = backfillReports(action, notifyViews);
    backfillFlight = flight;
    try {
      await flight;
    } finally {
      if (backfillFlight === flight) {
        backfillFlight = null;
        if (backfillAgain) { backfillAgain = false; void runBackfill(); }
      }
    }
  }
  deps.generation.subscribe(() => { void runBackfill(); });
  function basisOf(shotId: string, candidateId: string | null, source: ProjectSources) {
    const candidate = deps.generation.candidateChainOf(shotId).find(entry => entry.record.candidate_id === candidateId)?.record;
    if (!candidate) return { consumedStale: false };
    const attempt = deps.generation.attemptChainOf(shotId).find(entry => entry.record.action_id === candidate.action_id)?.record;
    const prompt = attempt ? deps.prompts.entryOf(shotId, attempt.prompt.version) : null;
    return { consumedStale: !prompt || prompt.record.hash !== attempt?.prompt.hash
      || promptStaleness(prompt.record, deps.prompts.basis(shotId, prompt.record.compiled.provider, source)).stale };
  }
  function stateOf(shotId: string): SelectionState {
    const record = selections.get(shotId)?.record || null;
    return deriveSelectionState(record, deps.generation.candidateChainOf(shotId),
      basisOf(shotId, record?.candidate_id || null, deps.sources()));
  }
  function sourceOf(shotId: string | null, candidateId: string | null): AdoptionSource | null {
    if (!shotId || !candidateId) return null;
    const entry = deps.generation.candidateChainOf(shotId).find(entry => entry.record.candidate_id === candidateId);
    if (!entry) return null;
    const stored = reviewReports.get(candidateId) || null;
    return { candidate: entry.record, version: entry.version,
      report: stored && stored.version > 0 && reviewIsCurrent(stored.report, entry.record) ? stored.report : null };
  }
  function projection(source = deps.sources()): SelectionProjection {
    const shots = source.suitePlan ? suitePlanSummary(source.suitePlan, sourceContext(source)).shots : [];
    const records: Record<string, SelectionRecord> = {}, candidateIds: Record<string, string> = {};
    const candidatesByShotId: Record<string, CandidateRecord[]> = {};
    const basisByShotId: Record<string, { consumedStale: boolean }> = {};
    for (const shot of shots) {
      const record = selections.get(shot.shot_id)?.record;
      if (record) {
        records[shot.shot_id] = record;
        if (record.action === "select" && record.candidate_id) candidateIds[shot.shot_id] = record.candidate_id;
      }
      candidatesByShotId[shot.shot_id] = deps.generation.candidateChainOf(shot.shot_id).map(entry => entry.record);
      basisByShotId[shot.shot_id] = basisOf(shot.shot_id, record?.candidate_id || null, source);
    }
    const set = buildSelectionSet({ shots, selections: records, candidatesByShotId, basisByShotId, at: new Date().toISOString() });
    const states: Record<string, SelectionState> = {};
    for (const entry of set.entries) if (entry.shot_id) states[entry.shot_id] = entry.state;
    return { set, records, candidateIds, states };
  }
  async function select(kind: "select" | "clear", shotId: string, candidateId: string | null): Promise<AdoptionOutcome> {
    const action = deps.beginAction();
    if (!action.projectId || !shotId || selecting) return { skipped: true, reason: "in_flight", currentSession: action.alive() };
    const source = sourceOf(shotId, candidateId);
    const previous = selections.get(shotId);
    const flight = {}; selecting = flight;
    const roleId = deps.sources().suitePlan?.shots.find(shot => shot.shot_id === shotId)?.role_id || null;
    const consumedSource = deps.sources();
    try {
      if (kind === "select") {
        if (!source) throw new Error("候选已不在本地链中；原采用保留。");
        const asset = await deps.repository.assets.get(action.projectId, source.candidate.asset_sha256);
        if (!asset?.blob || await sha256Hex(await asset.blob.arrayBuffer()) !== source.candidate.asset_sha256) {
          throw new Error("候选字节缺失或哈希不一致；原采用保留，请恢复项目包或候选字节。");
        }
        const checked = await ensureReviewReport(shotId, source.candidate, null, action.projectId, { action, roleId });
        if (!checked || checked.version < 1 || !reviewIsCurrent(checked.report, source.candidate)) {
          throw new Error("没有当前已保存的确定性检查报告；原采用保留。此检查不需要 AI 复核。");
        }
        source.report = checked.report;
      }
      const record = buildSelectionRecord({
        selectionId: newActionId(), action: kind, shotId,
        candidate: kind === "select" ? source?.candidate || null : null,
        candidateVersion: kind === "select" ? source?.version || null : null,
        report: kind === "select" ? source?.report || null : null, at: new Date().toISOString(),
      });
      assertSelectionRecord(record);
      const observation = kind === "select" && source
        ? deps.generation.attemptChainOf(shotId).find(item => item.record.action_id === source.candidate.action_id
          && item.record.state === "succeeded") : null;
      const reportEntry = source ? reviewReports.get(source.candidate.candidate_id) || null : null;
      const fence = consumptionFence(consumedSource, [shotId]);
      if (source) fence.assetSha256 = [...fence.assetSha256, source.candidate.asset_sha256];
      const saved = await deps.repository.commitSelection({
        projectId: action.projectId, shotId, decision: record, seenSelectionVersion: previous?.version || 0,
        fence, candidate: kind === "select" && source
          ? { kind: "candidate", documentId: shotId, version: source.version } : null,
        attempt: observation ? { actionId: observation.record.action_id, version: observation.version } : null,
        report: kind === "select" && source && reportEntry
          ? { kind: "review_report", documentId: source.candidate.candidate_id, version: reportEntry.version } : null,
      });
      if (action.alive()) selections.set(shotId, { record, version: saved.version });
      return { record, version: saved.version, candidateVersion: source?.version || null, currentSession: action.alive() };
    } finally { if (selecting === flight) selecting = null; }
  }
  async function acknowledge(unknown: UnknownItem) {
    const action = deps.beginAction();
    if (!action.projectId) throw new Error("缺少项目上下文，确认没有保存。");
    const record = buildAcknowledgement({ unknown, at: new Date().toISOString() });
    const documentId = acknowledgementDocumentIdOf(record);
    await deps.repository.documents.save(action.projectId, { kind: "review_acknowledgement", documentId, payload: record });
    if (action.alive()) acknowledgements.set(documentId, record);
    return { record, currentSession: action.alive() };
  }
  async function restore(action: ActionSnapshot) {
    if (!action.projectId) return;
    const selected = await deps.repository.documents.listLatest(action.projectId, DOMAIN_DOCUMENT_KINDS.selection);
    if (!action.alive()) return;
    for (const stored of selected) selections.set(stored.document_id,
      { record: assertSelectionRecord(stored.payload), version: stored.version });
    const known = await deps.repository.documents.listLatest(action.projectId, DOMAIN_DOCUMENT_KINDS.review_acknowledgement);
    if (!action.alive()) return;
    for (const stored of known) acknowledgements.set(stored.document_id, stored.payload as AcknowledgementRecord);
    const reports = await deps.repository.documents.listLatest(action.projectId, REVIEW_REPORT_DOCUMENT_KIND);
    if (!action.alive()) return;
    for (const stored of reports) {
      if (!stored.payload || typeof stored.payload !== "object") continue;
      reviewReports.set(stored.document_id, {
        report: stored.payload as ReviewReport, version: stored.version,
      });
    }
    // 恢复后补一次缺失/过期确定性报告（订阅之外的显式入口）；只读候选链，不发起 AI 复核。
    // 恢复路径不在这里刷视图：renderAll 紧随其后，且加载中途渲染会有阶段外壳副作用。
    if (!action.alive()) return;
    await runBackfill(false);
  }
  const MAX_REVIEW_IMAGE_BYTES = 4 * 1024 * 1024;
  const MAX_REVIEW_REFERENCES = 3;
  /** 单飞行键：冻结项目/会话 + 候选身份 + 观察到的报告版本(与提交时的 seenReportVersion 同口径)。 */
  function reportFlightKey(action: ActionSnapshot, candidate: CandidateRecord, seenVersion: number): string {
    return [action.projectId || "", action.generation, candidate.candidate_id, seenVersion].join("@");
  }
  /**
   * 确定性报告 get-or-build。同一(项目/会话, 候选, 观察版本)只跑一份飞行：
   * 并发消费(采用/AI 复核/订阅补建)共用同一份重建结果，避免同一目标被重建多次。
   * 只有成功落库的报告才记入内存并算 current；失败保留原有已保存条目、记下失败原因并返回 null
   * (调用方据此区分"确定性报告缺失/失败"与"AI 未复核")，绝不生成 version 0 的伪报告。
   * 本函数只做确定性检查，绝不发起 AI 复核；失败后下一次显式消费会重新补建。
   */
  async function ensureReviewReport(shotId: string, candidate: CandidateRecord, bytes: Uint8Array | null,
    pid: string | null, options: { action?: ActionSnapshot; roleId?: string | null } = {}): Promise<AdoptionReportEntry | null> {
    if (!pid) return null;
    const action = options.action || deps.beginAction();
    const existing = action.alive() ? reviewReports.get(candidate.candidate_id) || null : null;
    if (existing && existing.version > 0 && reviewIsCurrent(existing.report, candidate)) return existing;
    const key = reportFlightKey(action, candidate, existing?.version || 0);
    const running = reportFlights.get(key);
    if (running) return running;
    const flight = buildDeterministicReport(shotId, candidate, bytes, pid, action,
      options.roleId, existing, key);
    reportFlights.set(key, flight);
    try {
      return await flight;
    } finally {
      // 只清自己那一次飞行：切项目/close 的 reset 之后不得误删新会话的同键飞行。
      if (reportFlights.get(key) === flight) reportFlights.delete(key);
    }
  }
  /**
   * 构建/落库确定性报告：所有失败收敛成"返回 null + 记原因"，绝不抛给并发调用方。
   * action 只用来冻结项目/会话归属：旧会话(close/切项目)之后的落库结果绝不写内存 Map
   * (库内报告仍按冻结项目保全，下次恢复会读回)，也不触发视图通知。
   */
  async function buildDeterministicReport(shotId: string, candidate: CandidateRecord, bytes: Uint8Array | null,
    pid: string, action: ActionSnapshot, roleId: string | null | undefined,
    existing: AdoptionReportEntry | null, key: string): Promise<AdoptionReportEntry | null> {
    const fail = (reason: string): null => {
      if (action.alive()) reportFailures.set(candidate.candidate_id, { key, reason });
      return null;
    };
    try {
      const current = action.alive() ? reviewReports.get(candidate.candidate_id) || null : null;
      if (current && current.version > 0 && reviewIsCurrent(current.report, candidate)) return current;
      const consumedSource = deps.sources();
      let view: Uint8Array | null = bytes || null;
      if (!view) {
        const asset = await deps.repository.assets.get(pid, candidate.asset_sha256);
        if (asset?.blob instanceof Blob) view = new Uint8Array(await asset.blob.arrayBuffer());
      }
      // 字节读不出来就不建"字节不可读"的降级报告：保持缺失并如实记原因(候选与本地图片不受影响)。
      if (!view) return fail("候选字节读不到，确定性检查没有构建。");
      const suitePlan = consumedSource.suitePlan;
      const shot = (suitePlan && Array.isArray(suitePlan.shots) ? suitePlan.shots : [])
        .find((item) => item && item.shot_id === shotId);
      const deterministic = evaluateCandidateFindings({
        candidate: candidate,
        bytes: view,
        roleId: roleId !== undefined ? roleId : (shot ? shot.role_id : null),
      });
      let previous: ReviewReport | null = null;
      if (existing && existing.report && existing.report.vlm
          && existing.report.vlm.asset_sha256 === candidate.asset_sha256) {
        previous = existing.report;
      }
      const carried = previous
        ? previous.findings.filter((item) => item && item.layer === "vlm") : [];
      let report: ReviewReport | null = null;
      if (previous) {
        try {
          report = buildReviewReport({
            candidate: candidate,
            findings: deterministic.concat(carried),
            vlm: previous.vlm,
            at: new Date().toISOString(),
          });
        } catch (error) {
          report = null;
        }
      }
      if (!report) {
        report = buildReviewReport({
          candidate: candidate, findings: deterministic, at: new Date().toISOString(),
        });
      }
      const fence = consumptionFence(consumedSource, [shotId]);
      fence.assetSha256 = [...fence.assetSha256, candidate.asset_sha256];
      const saved = await deps.repository.commitReviewReport({
        projectId: pid, kind: "review_report", documentId: candidate.candidate_id,
        payload: report, seenReportVersion: existing?.version || 0,
        fence,
      });
      // 落库必须返回真实版本号才算 current：拿不到就按失败处理，绝不写 version 0 的伪报告。
      if (!saved || !(saved.version > 0)) return fail("报告落库没有返回有效版本，未记为已保存。");
      const entry: AdoptionReportEntry = { report, version: saved.version };
      if (action.alive()) {
        // 库内先写、内存后写：旧会话(已切项目/close)只在库里留下报告，绝不写新会话的 Map。
        reviewReports.set(candidate.candidate_id, entry);
        reportFailures.delete(candidate.candidate_id);
      }
      return entry;
    } catch (error) {
      return fail(messageOf(error) || "确定性检查报告没有保存。");
    }
  }
  async function readReviewBytes(projectId: string, sha: string): Promise<Uint8Array | null> {
    const asset = await deps.repository.assets.get(projectId, sha);
    return asset?.blob instanceof Blob ? new Uint8Array(await asset.blob.arrayBuffer()) : null;
  }
  async function reviewImagePayload(projectId: string, sha: string, mediaType: string) {
    const bytes = await readReviewBytes(projectId, sha);
    if (!bytes || bytes.length > MAX_REVIEW_IMAGE_BYTES) throw new Error("图片字节缺失或超过复核上限，没有发起 AI 复核。");
    if (await sha256Hex(bytes) !== sha) throw new Error("图片字节哈希不一致，没有发起 AI 复核。");
    let binary = "";
    for (let index = 0; index < bytes.length; index += 0x8000) binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
    return { media_type: mediaType, sha256: sha, data_base64: btoa(binary) };
  }
  /** 单图 AI 复核请求准备归 adoption：事实/规格/原动作/图片字节在此收口，generation 不反向依赖。 */
  async function candidateReviewRequest(shotId: string, candidate: CandidateRecord, projectId: string) {
    const source = structuredClone(deps.sources());
    const shot = source.suitePlan?.shots.find(entry => entry.shot_id === shotId);
    const spec = source.shotSpecs[shotId]?.spec || (shot ? emptyShotSpecFromShot(shot) : null);
    const original = [...deps.generation.attemptChainOf(shotId)].reverse().find(entry => entry.record.action_id === candidate.action_id && candidateMatchesAttempt(candidate, entry.record))?.record
      || deps.generation.attemptChainOf(shotId).find(entry => entry.record.action_id === candidate.action_id)?.record;
    if (!original || !candidateMatchesAttempt(candidate, original)) throw new Error("候选的原动作来源链缺失或不一致，没有发起 AI 复核。");
    const references = original.references.slice(0, MAX_REVIEW_REFERENCES);
    const facts = confirmedFacts(source);
    const image = await reviewImagePayload(projectId, candidate.asset_sha256, candidate.media_type || "image/png");
    const payload = [];
    for (const ref of references) {
      const asset = await deps.repository.assets.get(projectId, ref.sha256);
      if (!asset?.blob) throw new Error("原动作参考图字节缺失，没有发起 AI 复核。");
      payload.push(await reviewImagePayload(projectId, ref.sha256, asset.media_type));
    }
    return { candidate: image, references: payload,
      shot: { title: String(shot?.label || shot?.role_id || "图片任务").slice(0, 200),
        purpose: String(spec?.purpose || "").slice(0, 500), keep_items: spec?.keep.slice(0, 8) || [],
        allow_changes: spec?.change_allowed.slice(0, 8) || [] },
      platform: "amazon_us", locale: "zh-CN", product_facts: facts };
  }
  const REVIEW_PATH = "/api/v2/review/candidate";
  async function reviewCandidate(shotId: string, candidateId: string): Promise<ReviewCandidateResult> {
    const action = deps.beginAction();
    if (!action.projectId) return { skipped: true, reason: "no_project" };
    const pid = action.projectId;
    const flights = reviewFlights;
    if (flights.has(shotId)) return { skipped: true, reason: "in_flight" };
    const headers = deps.settings.headers("review");
    const consumedSource = deps.sources();
    flights.add(shotId);
    deps.changed?.();
    try {
      const stored = deps.generation.candidateChainOf(shotId).find((entry) => entry.record.candidate_id === candidateId);
      const candidate: CandidateRecord | null = stored ? stored.record : null;
      if (!candidate) return { skipped: true, reason: "no_candidate" };
      let request: unknown = null;
      try {
        request = await candidateReviewRequest(shotId, candidate, pid);
      } catch (error) {
        return { failed: true, reason: "request_invalid", message: messageOf(error) || "复核请求无法构建。" };
      }
      if (!action.alive()) return { skipped: true, reason: "stale_session" };
      let entry = reviewReports.get(candidate.candidate_id) || null;
      if (!entry || !reviewIsCurrent(entry.report, candidate)) {
        entry = await ensureReviewReport(shotId, candidate, null, pid, { action });
      }
      if (!action.alive()) return { skipped: true, reason: "stale_session" };
      if (!entry) return { failed: true, reason: "report_missing",
        message: "确定性检查报告缺失或补建失败，AI 结果没有合并(候选与本地图片保留；下次显式复核/采用会再补建，不会自动重调)。" };
      let envelope: unknown = null;
      try {
        const response = await fetch(REVIEW_PATH, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...headers },
          body: JSON.stringify(request),
        });
        envelope = await response.json().catch(() => null);
      } catch (error) {
        envelope = null;
      }
      if (!envelope || typeof envelope !== "object") {
        envelope = { ok: false, unknown: true, error: { family: "internal", code: "REVIEW_TRANSPORT",
          message: "复核服务没有返回可解析的结果（服务可能未启动）。", retry_policy: "requires_review" } };
      }
      const envelopeOk = envelope !== null && typeof envelope === "object"
        && "ok" in envelope && envelope.ok === true;
      let merged: ReviewReport | null = null;
      try {
        merged = mergeVlmReview({ report: entry.report, candidate: candidate, review: envelope, at: new Date().toISOString() });
      } catch (error) {
        return { failed: true, reason: "merge_invalid", message: messageOf(error) || "复核结果无法合并进报告。" };
      }
      if (!merged || !merged.vlm) {
        return { failed: true, reason: "merge_invalid", message: "复核结果无法合并进报告。" };
      }
      const vlmBlock = merged.vlm;
      try {
        const fence = consumptionFence(consumedSource, [shotId]);
        fence.assetSha256 = [...fence.assetSha256, candidate.asset_sha256];
        const saved = await deps.repository.commitReviewReport({
          projectId: pid, kind: "review_report", documentId: candidate.candidate_id,
          payload: merged, seenReportVersion: entry.version,
          fence,
        });
        if (!saved || !(saved.version > 0)) {
          return { failed: true, reason: "stale_report", message: "报告落库没有返回有效版本；原报告保留，没有自动重调。" };
        }
        if (action.alive()) reviewReports.set(candidate.candidate_id, { report: merged, version: saved.version });
      } catch (error) {
        return { failed: true, reason: "stale_report", message: messageOf(error) || "复核来源已变化；原报告保留，没有自动重调。" };
      }
      return { ok: envelopeOk, outcome: vlmBlock.outcome, candidate_id: candidate.candidate_id, summary: reviewSummaryText(merged) };
    } finally {
      flights.delete(shotId);
      if (action.alive()) deps.changed?.();
    }
  }
  return {
    reset, restore, stateOf, sourceOf, projection, select, acknowledge, candidateReviewRequest, reviewCandidate,
    reportOf: (candidateId) => reviewReports.get(candidateId) || null,
    reportBuildFailure: (candidateId) => reportFailures.get(candidateId)?.reason || null,
    reviewStatusOf: (candidateId) => {
      const stored = reviewReports.get(candidateId) || null;
      const projected = reviewStatusOf(stored ? stored.report : null);
      return { status: projected.status, reason: projected.reason };
    },
    entryOf: id => id ? selections.get(id) || null : null,
    adoptedMark(id) {
      const entry = id ? selections.get(id) : null;
      return id && entry?.record.action === "select" ? { candidate_id: entry.record.candidate_id, state: stateOf(id) } : null;
    },
    summary: id => selectionSummaryText(selections.get(id)?.record || null, stateOf(id)),
    acknowledgements: () => [...acknowledgements.values()], isSelecting: () => selecting !== null,
    isReviewInFlight: (shotId) => reviewFlights.has(shotId),
  };
}
