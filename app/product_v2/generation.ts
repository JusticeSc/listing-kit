/**
 * V2.R5.1 生成执行 Module：单张提交、按 task 核对、候选保存、单候选 VLM 复核
 * 与整套批次轮询的唯一执行权威。
 *
 * 职责（计划 §V2.R5.1）：
 *  - 先登记后外发：pending_submit 身份先落 IndexedDB，再发网关请求；
 *  - 冻结动作归属：所有状态写按 session.beginAction() 冻结的 projectId 落库；
 *  - 核对只按已保存 task id + 冻结执行身份查询，绝不重提、不偷用当前配置；
 *  - 下载/容量处理：候选字节 hash 校验、大小护栏、配额失败不产生半份记录。
 *
 * 本模块不持有 DOM、不持有编辑状态：套图/确认/Prompt/参考图等只读输入经 deps
 * 读取，渲染与文案经回调注入。workspace 只调用这里的接口并投影结果。
 *
 * TypeScript 迁移（计划 §9 V2.R7.5）：本文件是唯一手工维护实现；同名 `generation.js`
 * 由 `npm run build:frontend` 从本文件生成，浏览器只消费生成的 `.js`（import 说明符保持 `.js`）。
 */

 import {
   ATTEMPT_DOCUMENT_KIND,
   ATTEMPT_RECONCILE_MODES,
   ATTEMPT_STATES,
   attemptCurrentEnvironmentIdentity,
   attemptExecutionIdentityFromEnvironment,
   attemptReconcileBlockedMessage,
   attemptReconcileEnvironment,
   attemptReconcileRequestOf,
   currentAttempt,
   buildAttemptRecord,
   checkAttemptRecord,
   newActionId,
   nextFromStatusEnvelope,
   nextFromSubmitEnvelope,
   selectReferences,
   CANDIDATE_DOCUMENT_KIND,
   CONFIRM_DOCUMENT_ID,
   MAX_CANDIDATE_BYTES,
   buildCandidateRecord,
   candidateForAttempt,
   candidateStoreDecision,
   checkCandidateRecord,
   parsePngDimensions,
  reviewSummaryText,
  imagePromptProfile,
  canonicalJson,
  checkPromptRecord,
  checkConfirmationRecord,
  buildConfirmationRecord,
  confirmationSnapshot,
  DOMAIN_DOCUMENT_KINDS,
  promptStaleness,
  promptHash,
  batchProgressText,
  batchSubmitHalts,
  deriveBatchState,
  isNonEmptyString,
 } from "./domain/index.js";
 import { sha256Hex } from "./storage/db.js";
 import type { ConfirmationSheet } from "./prompts.js";
import type { AdoptionReviewAccess } from "./selection-adoption.js";
 import type { AttemptReconcileResult } from "./domain/attempt.js";
import type { ConsumptionFence, ProjectRepository } from "./storage/validate.js";
 import type {
  AttemptCurrentEnvironmentIdentity,
  AttemptError,
  AttemptRecord,
  AttemptState,
  BatchState,
  CandidateRecord,
  ConfirmationRecord,
  ConfirmationSnapshot,
  ConfirmationSubmissionMode,
  ImagePromptProfile,
  PromptRecord,
  PromptReferenceSelection,
  ReviewReport,
  Sha256Hex,
  SuitePlan,
  SuitePlanSummary,
  VlmOutcome,
} from "./domain/type-contracts.js";

const IMAGE_SUBMIT_PATH = "/api/v2/images/submit";
const IMAGE_STATUS_PATH = "/api/v2/images/status";
 const IMAGE_RESULT_PATH = "/api/v2/images/result";

const BATCH_POLL_INTERVAL_MS = 4000;
const BATCH_POLL_MAX_ROUNDS = 300;

/* --------------------------------------------------------------- 依赖与状态类型 */

/** session.beginAction() 冻结的动作归属：generation 代次 + projectId；alive() 同时判两者。 */
export type ActionSnapshot = {
  readonly generation: number;
  readonly projectId: string | null;
  alive(): boolean;
};

/** 版本链条目：记录本体 + IndexedDB 版本号（渲染/幂等判据）。 */
export type AttemptEntry = { record: AttemptRecord; version: number };
export type CandidateEntry = { record: CandidateRecord; version: number };
export type ReviewReportEntry = { report: ReviewReport; version: number };

/** 确认队列（documentId + 落库后的确认记录 + 版本）；pendingConfirmedShots 的输入。 */
export type ConfirmationQueue = {
  documentId: string;
  payload: ConfirmationRecord;
  version: number;
};

/** 参考图来源投影（intake.references → role/sha256）。 */
export type ReferenceSource = { role: string; sha256: string };

/** Prompt 版本条目（workspace 的 promptVersionAt / promptRecordOf 投影）。 */
export type PromptEntry = { version: number; record: PromptRecord };

/** 参考图出站载荷（本地仓库读出的字节转 base64）。 */
export type ReferencePayloadItem = {
  role: string;
  media_type: string;
  sha256: string;
  data_base64: string;
};

/** postImageJson 只返回「信封」；分类一律交给 domain。 */
type PostImageResponse = { envelope: unknown; status: number; transport: boolean };

/** 结果字节来源：同步内存面或 result 路由。 */
export type FetchedBytes =
  | { ok: true; buffer: ArrayBuffer; sha256?: string; media_type?: string;
      provider_id?: string; model_id?: string; task_id?: string | null }
  | { ok: false; reason: string; message: string; status?: number };

/** 同步协议提交信封暂存：action_id → 字节 + 信封声明哈希；取走即删、不落盘。 */
type SyncBytesEntry = { buffer: ArrayBuffer; expectSha: string | null };

/** 存储层最小契约（workspace 的 ProjectRepository 提供；此处只声明本 Module 用到的面）。 */
type StoredAsset = { sha256: Sha256Hex; byte_size: number };
type StoredAssetView = { blob: Blob | null; media_type?: string | null };
type AssetWriteInput = {
  bytes: ArrayBuffer; mediaType: string; originalName: string;
  role: string; width: number; height: number;
};
type DocumentSaveInput = { kind: string; documentId: string; payload: unknown; expectedVersion?: number };
type DocumentSaved = { version: number; payload?: unknown };
 /** restore 的 listLatest/listVersions 读出形状（确认/尝试/候选的头 + 版本链条目）。 */
 type DocumentRead = { document_id: string; payload: unknown; version: number };

export type GenerationRepository = {
  documents: {
    save(projectId: string, input: DocumentSaveInput): Promise<DocumentSaved>;
    get(projectId: string, kind: string, documentId: string, version: number): Promise<DocumentRead | null>;
    listLatest(projectId: string, kind: string): Promise<DocumentRead[]>;
    listVersions(projectId: string, kind: string, documentId: string): Promise<DocumentRead[]>;
  };
  assets: {
    get(projectId: string, sha256: string): Promise<StoredAssetView | null | undefined>;
    put(projectId: string, input: AssetWriteInput): Promise<StoredAsset>;
  };
} & Pick<ProjectRepository, "reserveGenerationAttempt" | "appendAttemptObservation" | "saveCandidate">;

/** workspace 注入的只读输入读者与投影回调；持久化顺序全部由本 Module 决定。 */
export type GenerationDependencies = {
  repository: GenerationRepository;
  beginAction(): ActionSnapshot;
  projectIdReader(): string | null;
  environmentReader(saved: unknown): unknown;
  requestHeaders(purpose: string, providerId?: string, source?: string): Record<string, string>;
  suitePlanReader(): SuitePlan | null;
  suiteSummaryReader(): SuitePlanSummary | null;
  promptEntryReader(shotId: string, version?: number | null): PromptEntry | null;
  confirmationReader(shotId: string): ConfirmationQueue | null;
  promptBasisReader(shotId: string, provider: ImagePromptProfile): unknown;
  fenceReader(shotId: string): ConsumptionFence;
  referenceSourceReader(): ReferenceSource[];
  promptsSheet(shotIds?: string[] | null): ConfirmationSheet | null;
  imageEnvironment(saved?: unknown): unknown;
  reviewAccess?: AdoptionReviewAccess | null;
  reviewFlightReader?: ((shotId: string) => boolean) | null;
  renderBatch(): void;
  renderAttempts(): void;
  status(text: string): void;
  attemptError(text: string): void;
  clearAttemptError(): void;
};

/** 批次运行状态（Module 内存面；不做第二份状态）。 */
export type BatchRunPhase = "submit" | "poll" | "fetch";
export type BatchRunState = {
  active: boolean; stopped: boolean; halted: boolean; haltReason: string;
  fetchBlocked: string; currentShotId: string | null; phase: BatchRunPhase;
};

/** 单张提交结果（扁平可选判别式：skipped / thrown / 已受理）。 */
export type SubmitAttemptResult = {
  skipped?: true; thrown?: true; submitted?: true;
  reason?: string; message?: string;
  blocking?: AttemptRecord;
  state?: AttemptState | null; error?: AttemptError | null;
  task_id?: string | null; request_id?: string | null;
  provider_id?: string | null; model_id?: string | null; note?: string;
  record?: AttemptRecord;
  candidate?: StoreCandidateResult | null;
};

/** 单张核对结果。 */
export type ReconcileAttemptResult = {
  skipped?: true; failed?: true; advanced?: boolean;
  reason?: string; message?: string;
  gate?: AttemptReconcileResult;
  task_id?: string | null; state?: AttemptState | null; note?: string;
  candidate?: StoreCandidateResult | null;
};

/** 候选保存结果。 */
export type StoreCandidateResult = {
  stored?: true; skipped?: true; failed?: true;
  reason?: string; message?: string;
  candidate_id?: string; sha256?: Sha256Hex;
  width?: number; height?: number; byte_size?: number;
  review?: string | null;
};

export type SubmitAttemptOptions = {
  action?: ActionSnapshot;
  confirmation?: ConfirmationQueue;
  requestHeaders?: Record<string, string>;
  explicitNew?: boolean;
  note?: string;
};
export type ReconcileAttemptOptions = { action?: ActionSnapshot };
export type EnsureCandidateOptions = {
  action?: ActionSnapshot;
  flights?: Set<string>;
  candidates?: CandidateEntry[];
  record?: AttemptRecord;
  roleId?: string | null;
  bytes?: ArrayBuffer;
  syncBytes?: Map<string, SyncBytesEntry>;
  quiet?: boolean;
};
export type EnsureReviewReportOptions = { action?: ActionSnapshot; roleId?: string | null };
export type PollActiveAttemptsOptions = {
  action?: ActionSnapshot; intervalMs?: number; maxRounds?: number; once?: boolean;
};
export type RunBatchInput = { confirmation?: ConfirmationQueue; action?: ActionSnapshot };

/** 摘要意图（workspace buildGenerationIntent 的投影）。 */
export type GenerationIntent = {
  all: ConfirmationSheet | null;
  sheet: ConfirmationSheet | null;
  identity: AttemptCurrentEnvironmentIdentity | null;
  mode: ConfirmationSubmissionMode;
  snapshot: ConfirmationSnapshot | null;
};
export type AuthorizationQueueView = {
  queue: ConfirmationQueue; pending: string[]; current: string[]; targetMatched: boolean;
};
export type ConfirmAndRunInput = {
  intent: GenerationIntent | null;
  readIntent: () => GenerationIntent | null;
  documentId: string;
  expectedVersion: number;
  action?: ActionSnapshot;
};
export type ConfirmAndRunResult = { skipped?: true; confirmation?: ConfirmationQueue };

/** 公开接口（workspace 与测试只调用这些方法）。 */
export type GenerationModule = {
  attemptChainOf(shotId: string): AttemptEntry[];
  latestAttemptOf(shotId: string): AttemptEntry | null;
  allAttemptRecords(): AttemptRecord[];
  candidateChainOf(shotId: string): CandidateEntry[];
  latestStoredCandidateOf(shotId: string): CandidateEntry | null;
  candidateForAttemptOf(shotId: string, actionId: string | null): CandidateEntry | null;
  submitAttempt(shotId: string, options?: SubmitAttemptOptions): Promise<SubmitAttemptResult>;
  reconcileAttempt(shotId: string, options?: ReconcileAttemptOptions): Promise<ReconcileAttemptResult>;
  storeCandidate(shotId: string, options?: EnsureCandidateOptions): Promise<StoreCandidateResult>;
  buildReferencePayload(references: PromptReferenceSelection[], pid: string): Promise<ReferencePayloadItem[]>;
  setReviewFlightReader(reader: (shotId: string) => boolean): void;
  setReviewAccess(access: AdoptionReviewAccess): void;
  deriveBatch(): BatchState;
  batchStateReader(): BatchRunState | null;
  runBatch(input?: RunBatchInput): Promise<void>;
  reconcileOnce(): Promise<void>;
  confirmAndRun(input: ConfirmAndRunInput): Promise<ConfirmAndRunResult>;
  stopBatch(): void;
  pendingConfirmedShots(confirmation: ConfirmationQueue | null | undefined): string[];
  confirmationTargetMatched(confirmation: ConfirmationQueue | null | undefined): boolean;
  isConfirmedShotCurrent(confirmation: ConfirmationQueue | null | undefined, shotId: string): boolean;
  rememberConfirmation(queue: ConfirmationQueue): void;
  restore(action: ActionSnapshot): Promise<void>;
  confirmed(): ConfirmationQueue | null;
  reworkEntry(shotId: string): ConfirmationQueue | null;
  reworkDocumentId(shotId: string): string;
  mode(): ConfirmationSubmissionMode;
  enterFailedRetry(shotIds: string[]): void;
  enterExplicitNew(shotId: string): void;
  hasCurrent(): boolean;
  shotHasCurrent(shotId: string | null): boolean;
  confirmationFor(shotId: string): ConfirmationQueue | null;
  queues(): AuthorizationQueueView[];
  intent(batch: { queue: string[]; retry_queue: string[] }): GenerationIntent | null;
  reworkIntent(shotId: string): GenerationIntent;
  isAttemptInFlight(shotId: string): boolean;
  isCandidateInFlight(shotId: string): boolean;
  isReviewInFlight(shotId: string): boolean;
  attemptChainsNow(): [string, AttemptEntry[]][];
  reset(): void;
};

/* --------------------------------------------------------------- 运行时窄化助手 */

/** 抛出值的可读信息（原实现按 error.message 取值；此处 in/typeof 收窄，与旧行为一致）。 */
function messageOf(error: unknown): string {
  if (error === null || typeof error !== "object" || !("message" in error)) return "";
  const message = error.message;
  return typeof message === "string" ? message : "";
}

/** 同步提交信封里的结果字节字段（服务端契约；in/typeof 收窄，缺失即 null，绝不伪造字节）。 */
function readSyncEnvelope(envelope: unknown): { imageBase64: string; imageSha256: string | null } | null {
  if (envelope === null || typeof envelope !== "object" || !("image_base64" in envelope)) return null;
  const base64 = envelope.image_base64;
  if (typeof base64 !== "string") return null;
  const rawSha = "image_sha256" in envelope ? envelope.image_sha256 : null;
  return {
    imageBase64: base64,
    imageSha256: typeof rawSha === "string" ? rawSha.toLowerCase() : null,
  };
}

/** 出站请求体里的目标 provider id（服务端契约；未知即 undefined，不伪造）。 */
function providerIdFromBody(body: unknown): string | undefined {
  if (body === null || typeof body !== "object" || !("target" in body)) return undefined;
  const target = body.target;
  if (target === null || typeof target !== "object" || !("provider_id" in target)) return undefined;
  return typeof target.provider_id === "string" ? target.provider_id : undefined;
}

/**
 * type-contracts.d.ts 是确认契约的权威；domain/confirm.js 仍是未迁移 JS，其推断签名把
 * executionIdentity 收成 null|undefined（`= null` 默认值），并把确认目标里的
 * protocol/capability_version/credential_source 从 unknown 收窄丢失，导致合法入参/结果都对不上
 * ConfirmationSnapshot / ConfirmationRecord。这里只按声明收口调用面：运行时仍是同一个函数、
 * 同一批实参，不做值转换、不新增校验，也不改公开面。
 */
type ConfirmationExecutionInput = {
  executionIdentity?: AttemptCurrentEnvironmentIdentity | null;
  submissionMode?: ConfirmationSubmissionMode;
};
type ConfirmationBuildInput = ConfirmationExecutionInput & {
  sheet: unknown;
  hash: unknown;
  confirmedAt: unknown;
};
const snapshotOfSheet = confirmationSnapshot as
  (sheet: unknown, options?: ConfirmationExecutionInput) => ConfirmationSnapshot;
const recordOfConfirmation = buildConfirmationRecord as
  (input: ConfirmationBuildInput) => ConfirmationRecord;

/* --------------------------------------------------------------- Module */

export function createGenerationModule(deps: GenerationDependencies): GenerationModule {
  const functionDeps = ["beginAction", "projectIdReader", "environmentReader", "requestHeaders",
    "suitePlanReader", "suiteSummaryReader", "promptEntryReader",
    "confirmationReader", "promptBasisReader", "fenceReader", "referenceSourceReader",
    "promptsSheet", "imageEnvironment",
    "renderAttempts", "renderBatch", "status",
    "attemptError", "clearAttemptError"] as const;
  for (const name of functionDeps) {
    if (typeof deps[name] !== "function") {
      throw new Error("生成执行 Module 缺少依赖：" + name + "。");
    }
  }
  if (!deps.repository) {
    throw new Error("生成执行 Module 缺少依赖：repository。");
  }

  const repository = deps.repository;
  let attemptChains = new Map<string, AttemptEntry[]>();
  let attemptInFlight = new Set<string>();
  let candidateChains = new Map<string, CandidateEntry[]>();
  let candidateInFlight = new Set<string>();
  let authorizationInFlight = new Set<string>();
  let batchState: BatchRunState | null = null;
  // 授权队列/scope/mode 的唯一所有者（设计§2.1：generation 拥有显示摘要→明确提交→登记→执行的完整动作）。
  // 独立 authorization.ts 按包02删除，不留兼容别名。
  let confirmedQueues = new Map<string, ConfirmationQueue>();
  let confirmed: ConfirmationQueue | null = null;
  let reworkQueues = new Map<string, ConfirmationQueue>();
  let authorizationScope: string[] | null = null;
  let authorizationMode: ConfirmationSubmissionMode = "initial";
  // V2.R5.2 同步协议：提交信封里的结果字节暂存（action_id → {buffer, expectSha}）。
  // 明确不落盘：页面刷新/关闭即失效，候选保存走显式补救路径。取走即删。
  let pendingSyncBytes = new Map<string, SyncBytesEntry>();

  /* ------------------------------------------------------------ 链与身份 */

  function attemptChainOf(shotId: string): AttemptEntry[] {
    return attemptChains.get(shotId) || [];
  }

  function latestAttemptOf(shotId: string): AttemptEntry | null {
    return currentAttempt(attemptChainOf(shotId));
  }

  function allAttemptRecords(): AttemptRecord[] {
    const list: AttemptRecord[] = [];
    for (const chain of attemptChains.values()) {
      for (const entry of chain) list.push(entry.record);
    }
    return list;
  }

  function rememberAttempt(shotId: string, entry: AttemptEntry): void {
    const chain = attemptChainOf(shotId).filter((item) => item.version !== entry.version);
    chain.push(entry);
    chain.sort((left, right) => left.version - right.version);
    attemptChains.set(shotId, chain);
  }

  function candidateChainOf(shotId: string): CandidateEntry[] {
    return candidateChains.get(shotId) || [];
  }

  function rememberCandidate(shotId: string, entry: CandidateEntry): void {
    const chain = candidateChainOf(shotId).filter((item) => item.version !== entry.version);
    chain.push(entry);
    chain.sort((left, right) => left.version - right.version);
    candidateChains.set(shotId, chain);
  }

  /** 最新 Attempt 若是「已成功且有候选」，返回该候选；其它情况返回 null。 */
  function latestStoredCandidateOf(shotId: string): CandidateEntry | null {
    const latest = latestAttemptOf(shotId);
    if (!latest || latest.record.state !== ATTEMPT_STATES.succeeded) return null;
    return candidateForAttemptOf(shotId, latest.record.action_id);
  }

  function attemptProviderIdentity(record: AttemptRecord): AttemptCurrentEnvironmentIdentity | null {
    // A saved task resolves its frozen target, independently of the model selected for new actions.
    return attemptCurrentEnvironmentIdentity(deps.environmentReader(record));
  }

  /** 渲染投影：某次 Attempt 之前保存的候选（存在即幂等保存已冻结的事实）。 */
  function candidateForAttemptOf(shotId: string, actionId: string | null): CandidateEntry | null {
    // Unchecked cast: 候选链条目恒为 {record, version}；domain 只回链中的元素（既有不变量）。
    const found = candidateForAttempt(candidateChainOf(shotId), actionId) as CandidateEntry | null;
    return found;
  }
  function reset(): void {
    attemptChains = new Map<string, AttemptEntry[]>();
    attemptInFlight = new Set<string>();
    candidateChains = new Map<string, CandidateEntry[]>();
    candidateInFlight = new Set<string>();
    authorizationInFlight = new Set<string>();
    confirmedQueues = new Map<string, ConfirmationQueue>();
    confirmed = null;
    reworkQueues = new Map<string, ConfirmationQueue>();
    authorizationScope = null;
    authorizationMode = "initial";
    pendingSyncBytes = new Map<string, SyncBytesEntry>();
    batchState = null;
  }
  // 授权面：confirmedQueues/confirmed/reworkQueues/authorizationScope/authorizationMode 的
  // 唯一所有者（设计§2.1：显示摘要→明确提交→登记→执行的完整动作归 generation）。
  // rememberConfirmation 复用旧 authorization.ts:109-117 语义：整套确认更新 scope/mode，
  // 返工确认按 shot 登记；版本相等时后到覆盖（旧 JS 用 >=，与 TS 的 <= 同义）。
  const REWORK_CONFIRM_PREFIX = "rework:";
  function rememberConfirmation(queue: ConfirmationQueue): void {
    confirmedQueues.set(queue.documentId + ":" + queue.version, queue);
    if (queue.documentId === CONFIRM_DOCUMENT_ID && (!confirmed || confirmed.version <= queue.version)) {
      confirmed = queue;
      authorizationScope = null;
      authorizationMode = "initial";
    } else if (queue.documentId.startsWith(REWORK_CONFIRM_PREFIX)) {
      const id = queue.documentId.slice(REWORK_CONFIRM_PREFIX.length);
      if ((reworkQueues.get(id)?.version || 0) <= queue.version) reworkQueues.set(id, queue);
    }
  }
  // restore 复用旧 authorization.ts:157-170：按 generation_confirm 列头+版本链恢复，
  // 每条经 checkConfirmationRecord 校验后登记（validation boundary，不伪造形状）。
  // restore 前调用方先 reset()（workspace loadWorkspace 已做），这里不二次清空。
  async function restore(action: ActionSnapshot): Promise<void> {
    if (!action.projectId) return;
    const latest = await repository.documents.listLatest(action.projectId, DOMAIN_DOCUMENT_KINDS.generation_confirm);
    for (const head of latest) {
      if (!action.alive()) return;
      const versions = await repository.documents.listVersions(
        action.projectId, DOMAIN_DOCUMENT_KINDS.generation_confirm, head.document_id);
      if (!action.alive()) return;
      for (const stored of versions) {
        const problems = checkConfirmationRecord(stored.payload);
        if (problems.length) throw new Error("已保存的生成授权无法恢复：" + problems[0].message);
        rememberConfirmation({
          documentId: stored.document_id,
          payload: stored.payload as ConfirmationQueue["payload"],
          version: stored.version,
        });
      }
    }
    const plan = deps.suitePlanReader();
    const shots = plan && Array.isArray(plan.shots)
      ? plan.shots.map((shot) => shot && shot.shot_id).filter((id): id is string => typeof id === "string")
      : [];
    for (const shotId of shots) {
      if (!action.alive()) return;
      const attemptDocs = await repository.documents.listVersions(
        action.projectId, ATTEMPT_DOCUMENT_KIND, shotId);
      if (!action.alive()) return;
      const attempts: AttemptEntry[] = [];
      for (const stored of attemptDocs.slice().reverse()) {
        if (checkAttemptRecord(stored.payload).length) {
          throw new Error("已保存的尝试链无法恢复：shot " + shotId);
        }
        attempts.push({ record: stored.payload as AttemptRecord, version: stored.version });
      }
      attemptChains.set(shotId, attempts);
    }
    for (const shotId of shots) {
      if (!action.alive()) return;
      const candidateDocs = await repository.documents.listVersions(
        action.projectId, CANDIDATE_DOCUMENT_KIND, shotId);
      if (!action.alive()) return;
      const candidates: CandidateEntry[] = [];
      for (const stored of candidateDocs.slice().reverse()) {
        if (checkCandidateRecord(stored.payload).length) {
          throw new Error("已保存的候选链无法恢复：shot " + shotId);
        }
        candidates.push({ record: stored.payload as CandidateRecord, version: stored.version });
      }
      candidateChains.set(shotId, candidates);
    }
  }
  // 按优先级排列的候选队列：返工（按登记倒序）在前，全部确认（含历史版本倒序）在后。
  // confirmationFor/queues 共用同一顺序，不重建原授权。
  function orderedQueues(): ConfirmationQueue[] {
    return [...reworkQueues.values()].reverse().concat(
      [...confirmedQueues.values()].reverse().filter(
        (queue) => !queue.documentId.startsWith(REWORK_CONFIRM_PREFIX)));
  }
  // 进入失败重试/显式另发：登记 scope + mode（旧 authorization.ts:175-176 语义，不改业务）。
  function hasCurrentQueue(): boolean {
    return Boolean(confirmed?.payload.shots.some((shot) => isConfirmedShotCurrent(confirmed, shot.shot_id)));
  }
  function shotHasCurrentQueue(shotId: string | null): boolean {
    return Boolean(shotId && orderedQueues().some((queue) => isConfirmedShotCurrent(queue, shotId)));
  }
  // confirmationFor 复用旧 authorization.ts:179 语义：ordered 顺序 + pendingAuthorizationShots，
  // 不依赖外部 attemptChain，复用内部 pendingConfirmedShots（同一判据）。
  function confirmationForOf(shotId: string): ConfirmationQueue | null {
    return orderedQueues().find((queue) => pendingConfirmedShots(queue).includes(shotId)) || null;
  }
  // queues 复用内部 pendingConfirmedShots/isConfirmedShotCurrent/confirmationTargetMatched，
  // 返回 {queue,pending,current,targetMatched} 投影；环境经 imageEnvironment(queue) 取同快照身份。
  function queuesView(): AuthorizationQueueView[] {
    return orderedQueues().map((queue) => {
      const pending = pendingConfirmedShots(queue);
      return {
        queue,
        pending,
        current: pending.filter((id) => isConfirmedShotCurrent(queue, id)),
        targetMatched: confirmationTargetMatched(queue),
      };
    });
  }
  // intent 复用旧 authorization.ts:136-147：prompts.sheet + scope/mode + confirmationSnapshot。
  // 旧 prompts/environment 间接依赖由新增 deps promptsSheet/imageEnvironment 替代。
  function intentOf(batch: { queue: string[]; retry_queue: string[] }): GenerationIntent | null {
    const all = deps.promptsSheet(null);
    if (!all) return null;
    const eligible = new Set(authorizationScope
      || (authorizationMode === "failed_retry" ? batch.retry_queue : batch.queue));
    const ids = all.shots.filter((shot) => eligible.has(shot.shot_id) && !shot.blockers.length)
      .map((shot) => shot.shot_id);
    const sheet = ids.length ? deps.promptsSheet(ids) : null;
    const identity = attemptCurrentEnvironmentIdentity(deps.imageEnvironment());
    const snapshot = sheet && identity ? snapshotOfSheet(sheet, {
      executionIdentity: identity, submissionMode: authorizationMode,
    }) : null;
    return { all, sheet, identity, snapshot, mode: authorizationMode };
  }
  function reworkIntentOf(shotId: string): GenerationIntent {
    const sheet = deps.promptsSheet([shotId]);
    if (!sheet?.can_submit) throw new Error("这张图当前还有阻断，返工没有外发。");
    const identity = attemptCurrentEnvironmentIdentity(deps.imageEnvironment());
    const snapshot = snapshotOfSheet(sheet, { executionIdentity: identity, submissionMode: "rework" });
    return { all: sheet, sheet, identity, snapshot, mode: "rework" };
  }

  /* ------------------------------------------------------------ 传输层 */

  async function blobToBase64(blob: Blob): Promise<string> {
    const buffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    let binary = "";
    const chunk = 0x8000;
    for (let index = 0; index < bytes.length; index += chunk) {
      binary += String.fromCharCode(...bytes.subarray(index, index + chunk));
    }
    return btoa(binary);
  }

  /** 提交信封里的同步结果字节：base64 → ArrayBuffer；失败返回 null（绝不伪造字节）。 */
  function base64ToBuffer(base64: string): ArrayBuffer | null {
    try {
      const binary = window.atob(base64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      return bytes.buffer;
    } catch (error) {
      return null;
    }
  }

  /** 参考图字节从本地仓库读取并转 base64；读不到就不发请求（绝不发半份资料）。 */
  async function buildReferencePayload(references: PromptReferenceSelection[], pid: string): Promise<ReferencePayloadItem[]> {
    const payload: ReferencePayloadItem[] = [];
    for (const item of references) {
      const asset = await repository.assets.get(pid, item.sha256);
      if (!asset || !asset.blob) {
        throw new Error("参考图资产缺失（sha256 " + String(item.sha256).slice(0, 12) + "…），请重新上传。");
      }
      payload.push({
        role: item.role,
        media_type: asset.media_type || "image/png",
        sha256: item.sha256,
        data_base64: await blobToBase64(asset.blob),
      });
    }
    return payload;
  }

  /** 网关调用只返回「信封」；分类一律交给 domain（classifySubmitEnvelope / classifyStatusEnvelope）。 */
  async function postImageJson(path: string, body: unknown, record: AttemptRecord | null,
    requestHeaders?: Record<string, string>): Promise<PostImageResponse> {
    const headers = requestHeaders || deps.requestHeaders("image",
      record?.provider?.provider_id || providerIdFromBody(body),
      record?.execution_identity?.credential_reference?.source);
    let response: Response;
    try {
      response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers },
        body: JSON.stringify(body),
      });
    } catch (error) {
      return { envelope: null, status: 0, transport: true };
    }
    let envelope: unknown = null;
    try {
      envelope = await response.json();
    } catch (error) {
      envelope = null;
    }
    if (!envelope || typeof envelope !== "object") {
      return {
        envelope: {
          ok: false,
          unknown: true,
          error: {
            family: "provider_unknown",
            code: "RESPONSE_UNREADABLE",
            message: "服务端返回 HTTP " + response.status + "，但响应不是约定的 JSON。",
            retry_policy: "requires_review",
          },
        },
        status: response.status,
        transport: false,
      };
    }
    return { envelope: envelope, status: response.status, transport: false };
  }

  /**
   * 取回候选字节：POST /api/v2/images/result。
   * 只接受 200 + image/png；服务端声明的 X-Image-Sha256 与本机重算的 sha256 必须一致，
   * 不一致就不保存（宁可没有候选，也不存不可信字节）。
   */
  async function fetchImageResultBytes(record: AttemptRecord): Promise<FetchedBytes> {
    const gate = attemptReconcileEnvironment(record, attemptProviderIdentity(record));
    if (gate.mode !== ATTEMPT_RECONCILE_MODES.by_task) {
      return {
        ok: false, reason: "environment_blocked",
        message: attemptReconcileBlockedMessage(record),
      };
    }
    let response: Response;
    try {
      response = await fetch(IMAGE_RESULT_PATH, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...deps.requestHeaders("image",
          record.provider.provider_id, record.execution_identity.credential_reference.source) },
        body: JSON.stringify(attemptReconcileRequestOf(record)),
      });
    } catch (error) {
      return {
        ok: false, reason: "transport",
        message: "取回候选时连接中断；记录保持原样，可以重试（不会重新生成）。",
      };
    }
    if (!response.ok) {
      let envelope: unknown = null;
      try {
        envelope = await response.json();
      } catch (error) {
        envelope = null;
      }
      let failureText: string | null = null;
      if (envelope && typeof envelope === "object" && "error" in envelope) {
        const failure = envelope.error;
        if (failure && typeof failure === "object") {
          const family = "family" in failure ? String(failure.family) : "";
          const code = "code" in failure ? String(failure.code) : "";
          const detail = "message" in failure ? String(failure.message) : "";
          failureText = "取回候选失败：" + family + " / " + code + "：" + detail;
        }
      }
      return {
        ok: false, reason: "http", status: response.status,
        message: failureText
          ?? "取回候选失败（HTTP " + response.status + "）；记录保持原样，可以重试。",
      };
    }
    const mediaType = String(response.headers.get("content-type") || "");
    if (!mediaType.includes("image/png")) {
      return {
        ok: false, reason: "bad_media",
        message: "结果不是 PNG（" + (mediaType || "无类型") + "），候选未保存。",
      };
    }
    const buffer = await response.arrayBuffer();
    const sha = await sha256Hex(buffer);
    const declared = String(response.headers.get("x-image-sha256") || "").toLowerCase();
    if (declared && declared !== sha) {
      return {
        ok: false, reason: "hash_mismatch",
        message: "下载字节的 sha256 与服务端声明不一致，候选未保存。",
      };
    }
    return {
      ok: true, buffer: buffer, sha256: sha, media_type: "image/png",
      provider_id: response.headers.get("x-provider-id") || "",
      model_id: response.headers.get("x-model-id") || "",
      task_id: response.headers.get("x-task-id") || record.task_id,
    };
  }


  /* ------------------------------------------------------------ 候选保存 */

  /**
   * 结果字节来源解析（V2.R5.2）：
   * - 同步记录（task_id 为空、冻结 sync === true）：字节只可能在提交信封到达过一次；
   *   模块内 pendingBytesMap 以 action_id 为键暂存（会话内存，不落盘），取走即删。
   *   刷新/关页后 map 必为空 → 明确失败并给出显式补救路径（显式新建 action 或人工核对），
   *   绝不伪造字节、绝不自动把「等待候选」伪装成完成。
   * - 异步记录（有 task_id）：照旧走 result 路由拉取。
   */
  async function pickSyncOrFetchResultBytes(record: AttemptRecord,
    syncBytes: Map<string, SyncBytesEntry> = pendingSyncBytes): Promise<FetchedBytes> {
    const isSync = !(record.task_id)
      && record.execution_identity && record.execution_identity.sync === true;
    if (!isSync) {
      if (!isNonEmptyString(record.task_id)) {
        return { ok: false, reason: "no_result_source", message: "记录既没有 task_id 也不是同步协议，没有可拉取的结果来源。" };
      }
      return fetchImageResultBytes(record);
    }
    const queued = syncBytes.get(record.action_id);
    if (queued) {
      syncBytes.delete(record.action_id);
      const sha = await sha256Hex(queued.buffer);
      if (queued.expectSha && queued.expectSha !== sha) {
        return {
          ok: false, reason: "sync_sha_mismatch",
          message: "同步结果字节哈希与提交信封不一致，候选未保存；请重新生成或人工核对。",
        };
      }
      return { ok: true, buffer: queued.buffer };
    }
    return {
      ok: false, reason: "sync_bytes_missing",
      message: "同步结果是一次性字节，页面刷新后不再可取；人工核对现有结论后，显式新建 action 重新生成。",
    };
  }

  /** 把提交信封里的同步结果字节登记进内存面（action_id 序；取走即删，不持久化）。 */
  function rememberSyncBytes(actionId: string, buffer: ArrayBuffer, expectSha: string | null,
    syncBytes: Map<string, SyncBytesEntry> = pendingSyncBytes): void {
    if (actionId && buffer) {
      syncBytes.set(actionId, { buffer: buffer, expectSha: expectSha || null });
    }
  }

  /**
   * 候选保存核心：把一次成功的生成变成 IndexedDB 里的字节 + 元数据记录。
   * 幂等：同一 action 已有候选则跳过；字节走内容寻址，同 hash 只存一份。
   * 配额不足不产生半份记录：asset 事务失败就没有记录，界面给出可恢复指引。
   */
  async function ensureCandidateStored(shotId: string, options: EnsureCandidateOptions = {}): Promise<StoreCandidateResult> {
    const action = options.action || deps.beginAction();
    if (!action.projectId) return { skipped: true, reason: "no_project" };
    const pid = action.projectId;
    const flights = options.flights || candidateInFlight;
    if (flights.has(shotId)) return { skipped: true, reason: "in_flight" };
    flights.add(shotId);
    const candidates = options.candidates || candidateChainOf(shotId);
    const record = options.record || latestAttemptOf(shotId)?.record;
    const roleId = options.roleId !== undefined ? options.roleId
      : deps.suitePlanReader()?.shots?.find(shot => shot.shot_id === shotId)?.role_id || null;
    try {
      if (!record) return { skipped: true, reason: "no_attempt" };
      const decision = candidateStoreDecision({
        attempt: record, candidates,
      });
      if (!decision.needed) {
        if (decision.reason === "already_stored" && decision.candidate) {
          // Unchecked cast: decision.candidate 恒为候选链条目 {record, version}（既有不变量）。
          const storedEntry = decision.candidate as CandidateEntry;
          const existing = storedEntry.record;
          try {
            if (deps.reviewAccess) await deps.reviewAccess.ensureReport(shotId, existing, null, pid, { action, roleId });
          } catch (error) {
            // 旧候选的报告补建是尽力而为，不改变幂等语义。
          }
        }
        return { skipped: true, reason: decision.reason };
      }
      const fetched: FetchedBytes = options.bytes
        ? { ok: true, buffer: options.bytes }
        : await pickSyncOrFetchResultBytes(record, options.syncBytes);
      if (!fetched.ok) {
        return { failed: true, reason: fetched.reason, message: fetched.message };
      }
      if (fetched.buffer.byteLength > MAX_CANDIDATE_BYTES) {
        return {
          failed: true, reason: "too_large",
          message: "结果字节超过护栏上限（" + MAX_CANDIDATE_BYTES + " 字节），候选未保存。",
        };
      }
      let dimensions: { width: number; height: number };
      try {
        dimensions = parsePngDimensions(new Uint8Array(fetched.buffer));
      } catch (error) {
        return {
          failed: true, reason: "bad_bytes",
          message: messageOf(error) || "结果不是可解析的 PNG，候选未保存。",
        };
      }
      let reviewSummary: string | null = null;
      try {
        // 候选保存是"上游已完成"的数据保全写：即使会话已切换，也按冻结项目落库。
        const asset = await repository.assets.put(pid, {
          bytes: fetched.buffer,
          mediaType: "image/png",
          originalName: shotId + "-" + record.action_id.slice(0, 8) + ".png",
          role: "candidate",
          width: dimensions.width,
          height: dimensions.height,
        });
        const candidate = buildCandidateRecord({
          shotId: shotId,
          attempt: record,
          assetSha256: asset.sha256,
          byteSize: asset.byte_size,
          width: dimensions.width,
          height: dimensions.height,
          at: new Date().toISOString(),
        });
        const saved = await repository.saveCandidate(pid, shotId, candidate);
        if (action.alive()) {
          rememberCandidate(shotId, { record: candidate, version: saved.version });
        }
        try {
          const reviewEntry = deps.reviewAccess ? await deps.reviewAccess.ensureReport(shotId, candidate,
            new Uint8Array(fetched.buffer), pid, { action, roleId }) : null;
          reviewSummary = reviewEntry ? reviewSummaryText(reviewEntry.report) : null;
        } catch (error) {
          reviewSummary = null;
        }
        return {
          stored: true, candidate_id: record.action_id, sha256: asset.sha256,
          width: dimensions.width, height: dimensions.height, byte_size: asset.byte_size,
          review: reviewSummary,
        };
      } catch (error) {
        if (error !== null && typeof error === "object" && "code" in error && error.code === "QUOTA_EXCEEDED") {
          return {
            failed: true, reason: "quota",
            message: "浏览器存储空间不足，候选未保存（记录保持原样）。"
              + "可以先导出项目或清理旧数据，再点「保存候选图片」重试。",
          };
        }
        return {
          failed: true, reason: "storage",
          message: messageOf(error) || "候选保存失败；记录保持原样，可以重试。",
        };
      }
    } finally {
      flights.delete(shotId);
      if (!options.quiet && action.alive()) deps.renderAttempts();
    }
  }

  /* ------------------------------------------------------------ 单张提交 */

  function authorizationUsed(confirmation: ConfirmationQueue, shotId: string): boolean {
    return attemptChainOf(shotId).some(({ record }) =>
      record.authorization?.document_id === confirmation.documentId
      && record.authorization?.version === confirmation.version);
  }

  /* 授权队列：已持久化授权绝不从新模型/最新 Prompt 推断（pending 按冻结链消费）。 */
  /** 队列恢复的同一环境匹配判据（执行与按钮投影共用）：冻结目标 6 键逐字一致 + 已配置。 */
  function confirmationTargetMatched(confirmation: ConfirmationQueue | null | undefined): boolean {
    const target = confirmation?.payload?.fingerprint?.snapshot?.execution_target;
    if (!target) return false;
    const identity = attemptCurrentEnvironmentIdentity(deps.environmentReader(confirmation));
    if (!identity || !identity.configured) return false;
    const keys = ["provider_id", "model_id", "protocol", "capability_version", "credential_source", "sync"] as const;
    return keys.every((key) => identity[key] === (target as unknown as Record<string, unknown>)[key]);
  }

  /**
   * 授权当前性：提示词版本+哈希仍对得上落库 Prompt，且快照依据（provider 档/参考图选择）
   *   未过期。执行（performSubmit 的 frozenTarget 比对）与按钮投影（resume 可点/提交可点）
   *   消费同一函数；UI 不另写逐键比对。
   */
  function isConfirmedShotCurrent(confirmation: ConfirmationQueue | null | undefined, shotId: string): boolean {
    if (!confirmation || !shotId) return false;
    const target = confirmation.payload?.fingerprint?.snapshot?.execution_target;
    if (!target) return false;
    const saved = confirmation.payload.shots.find((shot) => shot.shot_id === shotId);
    if (!saved || typeof saved.prompt_version !== "number") return false;
    if (deps.promptEntryReader(shotId)?.version !== saved.prompt_version) return false;
    const entry = deps.promptEntryReader(shotId, saved.prompt_version);
    if (!entry || entry.record.hash !== saved.prompt_hash) return false;
    const shot = deps.suitePlanReader()?.shots?.find((item) => item.shot_id === shotId);
    if (!shot) return false;
    try {
      const environment = deps.environmentReader(confirmation);
      const profile = imagePromptProfile(environment);
      if (promptStaleness(entry.record, deps.promptBasisReader(shotId, profile)).stale) return false;
      const references = selectReferences(shot, deps.referenceSourceReader(),
        { maxReferences: profile.max_reference_images });
      return canonicalJson(references) === canonicalJson(entry.record.request_snapshot.references);
    } catch { return false; }
  }

  /** 原授权仍读精确版本；Prompt 头有意改变时先让用户决定，不改用新版内容。 */
  function pendingConfirmedShots(confirmation: ConfirmationQueue | null | undefined): string[] {
    const snapshot = confirmation?.payload?.fingerprint?.snapshot;
    if (!snapshot?.execution_target) return [];
    // snapshot 来自 confirmation.payload：这条 conf 守卫只收窄类型。
    if (!confirmation || checkConfirmationRecord(confirmation.payload).length) return [];
    const confirmed = confirmation;
    const mode = snapshot.submission_mode;
    const currentIds = new Set((deps.suitePlanReader()?.shots || []).map(shot => shot.shot_id));
    return confirmed.payload.shots.filter(shot => {
      const id = shot.shot_id;
      if (!currentIds.has(id) || authorizationUsed(confirmed, id)) return false;
      const latest = latestAttemptOf(id)?.record;
      if (!latest) return mode !== "failed_retry";
      if ([ATTEMPT_STATES.pending_submit, ATTEMPT_STATES.submitted, ATTEMPT_STATES.running].includes(latest.state)) {
        return mode === "explicit_new" && latest.state === ATTEMPT_STATES.pending_submit && !latest.task_id;
      }
      if (latest.state === ATTEMPT_STATES.unknown) return mode === "explicit_new";
      if (mode === "failed_retry") return latest.state === ATTEMPT_STATES.failed;
      if (mode === "initial") return false;
      return true;
    }).map(shot => shot.shot_id);
  }
  async function performSubmitAttempt(shotId: string, options: SubmitAttemptOptions = {}): Promise<SubmitAttemptResult> {
    // 批次循环传入自己的冻结动作（循环的会话/项目归属）；单张提交在这里冻结。
    const action = options.action || deps.beginAction();
    if (!action.alive() || !action.projectId || !deps.suitePlanReader()) {
      return { skipped: true, reason: "not_ready" };
    }
    const pid = action.projectId;
    const flights = attemptInFlight;
    if (flights.has(shotId)) return { skipped: true, reason: "in_flight" };
    flights.add(shotId);
    const candidateFlights = candidateInFlight;
    const syncBytes = pendingSyncBytes;
    try {
      const confirmation = options.confirmation || deps.confirmationReader(shotId);
      if (!confirmation || !pendingConfirmedShots(confirmation).includes(shotId)) {
        return { skipped: true, reason: "no_confirmation", message: "没有这张图尚未消费的原授权；先核对摘要，不会按新设置猜一个动作。" };
      }
      const confirmSnapshot = confirmation.payload.fingerprint.snapshot;
      const frozenTarget = confirmSnapshot.execution_target;
      // pendingConfirmedShots 已确认该 conf 有冻结目标：这条守卫只收窄类型。
      if (!frozenTarget) return { skipped: true, reason: "no_confirmation" };
      const environment = deps.environmentReader(confirmation);
      const identity = attemptCurrentEnvironmentIdentity(environment);
      if (!identity || !identity.configured) {
        return { skipped: true, reason: "credential_missing", message: "原队列的凭据未就绪；给原目标补凭据，不会改用新动作模型。" };
      }
      const targetKeys = ["provider_id", "model_id", "protocol", "capability_version", "credential_source", "sync"] as const;
      if (targetKeys.some((key) => identity[key] !== frozenTarget[key])) {
        return { skipped: true, reason: "environment_changed", message: "原队列的目标、协议、能力版本或凭据来源不匹配；保持队列，不会切目标外发。" };
      }
      const requestHeaders = options.requestHeaders || deps.requestHeaders("image", identity.provider_id, identity.credential_source);
      const seenAction = latestAttemptOf(shotId);
      const blocking = seenAction && ["pending_submit", "submitted", "running"].includes(seenAction.record.state)
        ? seenAction.record : null;
      // 显式「放弃核对」只允许放弃没有任务编号、无法核对的 pending 记录；
      // 有 task id 的记录仍然只能先核对（防重复提交的语义不变）。
      const abandonStuck = confirmSnapshot.submission_mode === "explicit_new" && blocking !== null
        && blocking.state === ATTEMPT_STATES.pending_submit && !blocking.task_id;
      if (blocking && !abandonStuck) {
        return { skipped: true, reason: "blocked", blocking: blocking };
      }
      const authorizedPrompt = confirmation.payload.shots.find(shot => shot.shot_id === shotId);
      // pendingConfirmedShots 已确认该 shot 在授权内：这条守卫只收窄类型。
      if (!authorizedPrompt) return { skipped: true, reason: "no_confirmation" };
      const entry = deps.promptEntryReader(shotId, authorizedPrompt.prompt_version);
      if (!entry || entry.record.hash !== authorizedPrompt.prompt_hash) {
        return { skipped: true, reason: "no_prompt", message: "原授权绑定的 Prompt 版本或哈希缺失；不会替换为最新版。" };
      }
      const shot = deps.suitePlanReader()?.shots?.find((item) => item.shot_id === shotId);
      if (!shot) return { skipped: true, reason: "shot_missing" };
      const candidates = candidateChainOf(shotId);
      const profile = imagePromptProfile(environment);
      const snapshot = entry.record.request_snapshot;
      const problems = checkPromptRecord(entry.record);
      if (problems.length || canonicalJson(entry.record.compiled.provider) !== canonicalJson(profile)
          || promptStaleness(entry.record, deps.promptBasisReader(shotId, profile)).stale
          || await promptHash(snapshot, { digest: sha256Hex }) !== entry.record.hash) {
        return {
          skipped: true, reason: "prompt_stale",
          message: "Prompt 与有效图像能力或冻结请求不一致；请重新编译并确认，不会提交。",
        };
      }
      const source = await repository.documents.get(pid, DOMAIN_DOCUMENT_KINDS.generation_confirm,
        confirmation.documentId, confirmation.version) as { payload: ConfirmationRecord } | null;
      if (!source || canonicalJson(source.payload) !== canonicalJson(confirmation.payload)
          || await sha256Hex(new TextEncoder().encode(canonicalJson(source.payload.fingerprint.snapshot)))
            !== source.payload.fingerprint.hash) {
        return { skipped: true, reason: "authorization_missing", message: "IndexedDB 中的原授权版本或指纹不一致，没有外发。" };
      }
      const references = selectReferences(shot, deps.referenceSourceReader(),
        { maxReferences: profile.max_reference_images });
      if (references.length === 0) return { skipped: true, reason: "no_references" };
      if (canonicalJson(references) !== canonicalJson(snapshot.references)) {
        return {
          skipped: true, reason: "references_changed",
          message: "参考图已变化；请重新编译并确认，不会替换已确认的参考图后直接提交。",
        };
      }
      let referencePayload: ReferencePayloadItem[];
      try {
        referencePayload = await buildReferencePayload(references, pid);
      } catch (error) {
        return {
          skipped: true, reason: "reference_read_failed",
          message: messageOf(error) || "参考图读取失败，没有提交。",
        };
      }
      if (referencePayload.some((item) => !profile.reference_media_types.includes(item.media_type))) {
        return {
          skipped: true, reason: "reference_media_unsupported",
          message: "参考图格式不在当前模型支持范围内；请使用受支持格式后重新确认。",
        };
      }
      const target = {
        provider_id: identity.provider_id, model_id: identity.model_id,
        protocol: identity.protocol, capability_version: identity.capability_version,
      };
      if (canonicalJson(target) !== canonicalJson(snapshot.target)) {
        return {
          skipped: true, reason: "environment_changed",
          message: "执行目标与已确认请求不一致；请按当前目标重新编译并确认。",
        };
      }
      if (!action.alive()) return { skipped: true, reason: "stale_session" };
      if (promptStaleness(entry.record, deps.promptBasisReader(shotId, profile)).stale) {
        return { skipped: true, reason: "prompt_stale", message: "本图实际消费的依据已变化；原 Prompt 保留，没有外发。" };
      }
      const parameters = {
        size: snapshot.size, n: snapshot.n,
        prompt_extend: snapshot.prompt_extend, watermark: snapshot.watermark,
      };
      const actionId = newActionId();
      const at = new Date().toISOString();
      const record = buildAttemptRecord({
        actionId: actionId,
        shotId: shotId,
        prompt: { version: entry.version, hash: entry.record.hash },
        references: references,
        provider: { provider_id: identity.provider_id, model_id: identity.model_id },
        executionIdentity: attemptExecutionIdentityFromEnvironment(identity),
        authorization: { document_id: confirmation.documentId, version: confirmation.version,
          hash: confirmation.payload.fingerprint.hash },
        parameters: parameters,
        at: at,
        note: options.explicitNew ? "用户显式新建 action" : (options.note || "用户发起生成"),
      });
      // 事务核对当前来源、所见动作及授权消费；跨标签只有预约赢家可进入外发。
      // 围栏唯一实现是 project-inputs.consumptionFence（经 fenceReader 注入）；
      // 请求一致性（basis.references）仍由 repository.checkGenerationSources 核对。
      const fence = deps.fenceReader(shotId);
      const saved = await repository.reserveGenerationAttempt({
        projectId: pid, shotId,
        confirmation: { kind: "generation_confirm", documentId: confirmation.documentId, version: confirmation.version },
        seenAction: seenAction ? { actionId: seenAction.record.action_id, version: seenAction.version } : null,
        prompt: { kind: "prompt_version", documentId: shotId, version: entry.version },
        pending: record,
        fence: {
          sources: [...fence.sources,
            { kind: DOMAIN_DOCUMENT_KINDS.prompt_version, documentId: shotId, version: entry.version }],
          projectionJson: fence.projectionJson,
          assetSha256: [...fence.assetSha256, ...references.map(item => item.sha256)],
        },
      });
      if (!action.alive()) return { skipped: true, reason: "stale_session", record };
      if (action.alive()) {
        rememberAttempt(shotId, { record: record, version: saved.version });
        deps.renderAttempts();
        deps.status("已登记 " + actionId + "（pending_submit），正在提交…");
      }
      const { envelope } = await postImageJson(IMAGE_SUBMIT_PATH, {
        action_id: actionId,
        prompt: snapshot.prompt,
        references: referencePayload,
        size: parameters.size,
        n: snapshot.n,
        prompt_extend: snapshot.prompt_extend,
        watermark: snapshot.watermark,
        output_format: snapshot.output_format,
        model_id: snapshot.model,
        target: { ...snapshot.target, credential_source: identity.credential_source },
      }, record, requestHeaders);
      const outcome = nextFromSubmitEnvelope(record, envelope, { at: new Date().toISOString() });
      // 旧 action 的响应按原预约保全；同 action 并发观察不得回退终态。
      const savedNext = await repository.appendAttemptObservation({
        projectId: pid, shotId, base: { actionId, version: saved.version }, via: "submit", envelope,
      });
      outcome.record = savedNext.payload;
      if (action.alive()) {
        rememberAttempt(shotId, { record: savedNext.payload, version: savedNext.version });
      }
      // 提交直接到终态（成功）时，同一步把候选字节存进 IndexedDB；失败不掩盖提交结论。
      // V2.R5.2 同步协议：信封自带结果字节；先登记进内存面（含信封声明哈希），候选保存
      // 取走时独立重算并核对；不一致则不保存。异步记录没有这个步骤。
      const syncEnvelope = readSyncEnvelope(envelope);
      if (outcome.record.state === ATTEMPT_STATES.succeeded && syncEnvelope) {
        const bytes = base64ToBuffer(syncEnvelope.imageBase64);
        if (!bytes) {
          return { ...outcome.outcome, record: outcome.record, submitted: true,
                   message: "同步结果字节解码失败，候选未保存；请人工核对或重新生成。", candidate: null };
        }
        rememberSyncBytes(actionId, bytes, syncEnvelope.imageSha256, syncBytes);
      }
      let candidate: StoreCandidateResult | null = null;
      if (outcome.record.state === ATTEMPT_STATES.succeeded) {
        candidate = await ensureCandidateStored(shotId, {
          quiet: true, action, record: outcome.record, candidates, roleId: shot.role_id,
          flights: candidateFlights, syncBytes,
        });
      }
      return { ...outcome.outcome, record: outcome.record, submitted: true, candidate: candidate };
    } catch (error) {
      return {
        thrown: true, state: null, error: null,
        message: messageOf(error) || "提交没有完成；已登记的身份与历史仍然保留。",
      };
    } finally {
      flights.delete(shotId);
      if (action.alive()) deps.renderAttempts();
    }
  }

  /* ------------------------------------------------------------ 单张核对 */

  async function performReconcileAttempt(shotId: string, options: ReconcileAttemptOptions = {}): Promise<ReconcileAttemptResult> {
    // 核对只查询上游并推进已有记录；pid 必须来自冻结动作（批次循环传入）。
    const action = options.action || deps.beginAction();
    if (!action.alive() || !action.projectId) return { skipped: true, reason: "in_flight" };
    const pid = action.projectId;
    const flights = attemptInFlight;
    if (flights.has(shotId)) return { skipped: true, reason: "in_flight" };
    flights.add(shotId);
    const candidateFlights = candidateInFlight;
    try {
      const latest = latestAttemptOf(shotId);
      if (!latest || !latest.record.task_id) return { skipped: true, reason: "no_task" };
      const candidates = candidateChainOf(shotId);
      const roleId = deps.suitePlanReader()?.shots?.find(shot => shot.shot_id === shotId)?.role_id || null;
      // V2.R4.4：核对先过冻结身份判据——环境漂移或凭据来源失配时不发请求、不重提、不改记录。
      const current = attemptProviderIdentity(latest.record);
      const gate = attemptReconcileEnvironment(latest.record, current);
      if (gate.mode !== ATTEMPT_RECONCILE_MODES.by_task) {
        return {
          skipped: true,
          reason: gate.mode === ATTEMPT_RECONCILE_MODES.blocked_environment
            ? "environment_blocked" : "no_identity",
          message: attemptReconcileBlockedMessage(latest.record),
          gate: gate,
        };
      }
      // 按冻结身份发核对请求：服务端再按同一身份核对目标（EXECUTION_IDENTITY_MISMATCH 兜底）。
      const { envelope } = await postImageJson(IMAGE_STATUS_PATH,
        attemptReconcileRequestOf(latest.record), latest.record);
      const outcome = nextFromStatusEnvelope(latest.record, envelope,
        { at: new Date().toISOString() });
      if (outcome.outcome.advanced) {
        // 核对推进是数据保全写：按冻结项目落库；会话已切换时不回写内存缓存。
        const saved = await repository.appendAttemptObservation({
          projectId: pid, shotId, base: { actionId: latest.record.action_id, version: latest.version },
          via: "query", envelope,
        });
        outcome.record = saved.payload;
        if (action.alive()) {
          rememberAttempt(shotId, { record: saved.payload, version: saved.version });
        }
        // 核对推进到成功时，同一步把候选字节存进 IndexedDB；失败不掩盖核对结论。
        let candidate: StoreCandidateResult | null = null;
        if (outcome.record.state === ATTEMPT_STATES.succeeded) {
          candidate = await ensureCandidateStored(shotId, {
            quiet: true, action, record: outcome.record, candidates, roleId, flights: candidateFlights,
          });
        }
        return {
          advanced: true, task_id: latest.record.task_id, state: outcome.record.state,
          candidate: candidate,
        };
      }
      return {
        advanced: false, task_id: latest.record.task_id, state: latest.record.state,
        note: outcome.outcome.note || "记录保持原样",
      };
    } catch (error) {
      return {
        failed: true,
        message: messageOf(error) || "核对没有完成，记录保持原样。",
      };
    } finally {
      flights.delete(shotId);
      if (action.alive()) deps.renderAttempts();
    }
  }

  /* ------------------------------------------------------------ 整套批次 */

  function batchStateReader(): BatchRunState | null {
    return batchState;
  }

  /** 批次状态 = 套图顺序 + 每张图最新 Attempt + Prompt 就绪状态的投影；没有第二份状态。 */
  function deriveBatch(): BatchState {
    const summary = deps.suiteSummaryReader();
    const shots = summary ? summary.shots : [];
    const latest: Record<string, AttemptRecord | null> = {};
    for (const item of shots) {
      const entry = latestAttemptOf(item.shot_id);
      latest[item.shot_id] = entry ? entry.record : null;
    }
    return deriveBatchState({
      shots: shots.map((item) => ({ shot_id: item.shot_id, label: item.label })),
      latestAttempts: latest,
      promptReady: (id) => Boolean(deps.promptEntryReader(id)),
      candidateStored: (id) => Boolean(latestStoredCandidateOf(id)),
    });
  }

  function stopBatch(): void {
    if (batchState && batchState.active) batchState.stopped = true;
    deps.renderBatch();
  }

  /** 摘要授权、原确认落库及执行是一个动作；UI 不决定持久化与外发的先后。 */
  async function confirmAndRun({ intent, readIntent, documentId, expectedVersion,
    action = deps.beginAction() }: ConfirmAndRunInput): Promise<ConfirmAndRunResult> {
    if (!action.projectId || !action.alive() || batchState?.active) return { skipped: true };
    const pid = action.projectId;
    const flights = authorizationInFlight;
    if (flights.has(documentId)) return { skipped: true };
    flights.add(documentId);
    try {
      // intent / sheet / identity 缺一即没有可比对的摘要：与下面 !snapshot 走同一条拒绝。
      if (!intent || !intent.sheet || !intent.identity || !intent.identity.configured) {
        throw new Error("摘要与实际发送内容不一致，没有外发。");
      }
      const snapshot = snapshotOfSheet(intent.sheet,
        { executionIdentity: intent.identity, submissionMode: intent.mode });
      if (canonicalJson(snapshot) !== canonicalJson(intent.snapshot)) {
        throw new Error("摘要与实际发送内容不一致，没有外发。");
      }
      const hash = await promptHash(snapshot, { digest: sha256Hex });
      if (!action.alive()) return { skipped: true };
      if (canonicalJson(snapshot) !== canonicalJson(readIntent()?.snapshot)) {
        throw new Error("摘要已变化或当前未就绪；请核对新摘要后再确认，没有外发。");
      }
      const payload: ConfirmationRecord = recordOfConfirmation({
        sheet: intent.sheet, hash, confirmedAt: new Date().toISOString(),
        executionIdentity: intent.identity, submissionMode: intent.mode,
      });
      const saved = await repository.documents.save(pid, {
        kind: DOMAIN_DOCUMENT_KINDS.generation_confirm, documentId, payload, expectedVersion,
      });
      const confirmation: ConfirmationQueue = { documentId, payload, version: saved.version };
      if (!action.alive()) return { confirmation, skipped: true };
      rememberConfirmation(confirmation);
      if (!action.alive()) return { confirmation, skipped: true };
      await runBatch({ confirmation, action });
      return { confirmation };
    } finally {
      flights.delete(documentId);
    }
  }

  /**
   * 同一次授权的单张、整套与返工共用队列。停止只停新增提交，不取消上游。
   */
  async function runBatch({ confirmation, action = deps.beginAction() }: RunBatchInput = {}): Promise<void> {
    if (!action.alive() || !action.projectId || !deps.suitePlanReader() || batchState?.active) return;
    deps.clearAttemptError();
    const queue = pendingConfirmedShots(confirmation);
    if (!queue.length) {
      deps.attemptError("原队列没有可新增提交的图；Unknown 只核对或明确另发，不自动重提。");
      return;
    }
    // 队列非空即保证确认与冻结目标存在：这条守卫只收窄类型。
    if (!confirmation || !confirmation.payload.fingerprint.snapshot.execution_target) return;
    const frozenTarget = confirmation.payload.fingerprint.snapshot.execution_target;
    const requestHeaders = deps.requestHeaders("image", frozenTarget.provider_id, frozenTarget.credential_source);
    const running: BatchRunState = { active: true, stopped: false, halted: false, haltReason: "", fetchBlocked: "",
      currentShotId: null, phase: "submit" };
    batchState = running;
    deps.renderAttempts();
    let submitted = 0;
    const skipped: string[] = [];
    try {
      for (const shotId of queue) {
        if (!action.alive() || running.stopped || running.halted) break;
        running.currentShotId = shotId;
        deps.renderBatch();
        const outcome = await performSubmitAttempt(shotId, {
          action, confirmation, requestHeaders, note: "用户一次授权的原队列提交",
        });
        if (!action.alive()) return;
        if (outcome.skipped) {
          const reason = outcome.reason || "";
          skipped.push(shotId + "：" + (outcome.message || reason));
          if (["credential_missing", "environment_changed", "authorization_missing", "stale_session"].includes(reason)) {
            running.halted = true;
            running.haltReason = outcome.message || reason;
          }
          continue;
        }
        submitted += 1;
        if (outcome.thrown || batchSubmitHalts(outcome)) {
          running.halted = true;
          running.haltReason = outcome.message || outcome.error?.message || "提交没有可确认结论";
          break;
        }
        await pollActiveAttempts({ action });
      }
      if (action.alive()) {
        running.phase = "poll";
        running.currentShotId = null;
        await pollActiveAttempts({ action });
      }
    } catch (error) {
      if (action.alive()) {
        running.halted = true;
        running.haltReason = messageOf(error) || "批次执行出现异常";
      }
    } finally {
      if (action.alive()) {
        const finished = running;
        batchState = null;
        deps.renderAttempts();
        const result = deriveBatch();
        deps.status((finished?.stopped ? "已停止新增提交；" : finished?.halted ? "已暂停（" + finished.haltReason + "）；" : "本批结束；")
          + "已提交 " + submitted + " 张；" + batchProgressText(result)
          + (skipped.length ? "；未提交：" + skipped.join("；") : "")
          + "。原授权、未提交队列与所有历史记录保留。");
      }
    }
  }

  /** 轮询在途记录（只查询、不重提）。批次运行中循环到没有可核对的记录为止。 */
  async function pollActiveAttempts(options: PollActiveAttemptsOptions = {}): Promise<void> {
    const intervalMs = options.intervalMs || BATCH_POLL_INTERVAL_MS;
    const maxRounds = options.maxRounds || BATCH_POLL_MAX_ROUNDS;
    const once = options.once === true;
    // 动作归属：批次传入自己的冻结动作；独立核对在这里冻结。
    const action = options.action || deps.beginAction();
    for (let round = 0; round < maxRounds; round += 1) {
      if (batchState && batchState.halted) return;
      if (!action.alive()) return;
      const state = deriveBatch();
      if (state.reconcile_queue.length === 0 && state.fetch_queue.length === 0) return;
      if (batchState) { batchState.phase = "poll"; deps.renderBatch(); }
      for (const shotId of state.reconcile_queue) {
        if (batchState && batchState.halted) return;
        if (!action.alive()) return;
        await performReconcileAttempt(shotId, { action });
      }
      if (!action.alive()) return;
      // 候选保存：配额受阻时记录原因并停本轮保存；核对路径不受影响。
      if (!(batchState && batchState.fetchBlocked)) {
        const fetchState = deriveBatch();
        for (const shotId of fetchState.fetch_queue) {
          if (!action.alive()) return;
          if (batchState) {
            batchState.currentShotId = shotId;
            batchState.phase = "fetch";
            deps.renderBatch();
          }
          const stored = await ensureCandidateStored(shotId, { action });
          if (!action.alive()) return;
          if (stored && stored.failed && stored.reason === "quota") {
            if (batchState) batchState.fetchBlocked = stored.message || "";
            break;
          }
        }
      }
      if (!action.alive()) return;
      deps.renderAttempts();
      if (once) return;
      // 停止只停新增提交：已提交的身份仍然各查一次，给出当前结论后不再轮询。
      if (batchState && batchState.stopped) return;
      const after = deriveBatch();
      if (after.reconcile_queue.length === 0 && after.fetch_queue.length === 0) return;
      if (round === maxRounds - 1 && batchState) {
        batchState.halted = true;
        batchState.haltReason = "上游长时间没有结论，已停止自动核对；记录仍在，可继续核对";
        return;
      }
      await new Promise<void>((resolve) => {
        window.setTimeout(() => { resolve(); }, intervalMs);
      });
    }
  }

  /** 批量的「核对进行中」：所有有任务编号的在途记录各查一次，不重提。 */
  async function reconcileOnce(): Promise<void> {
    deps.clearAttemptError();
    const before = deriveBatch();
    if (before.reconcile_queue.length === 0) {
      deps.attemptError("没有可按任务编号核对的记录。");
      return;
    }
    try {
      await pollActiveAttempts({ once: true });
    } catch (error) {
      deps.attemptError(messageOf(error) || "核对没有完成，记录保持原样。");
      return;
    }
    const after = deriveBatch();
    deps.status("已核对 " + before.reconcile_queue.length + " 张："
      + batchProgressText(after));
  }

  return {
    // 链读取(渲染投影用)
    attemptChainOf, latestAttemptOf, allAttemptRecords,
    candidateChainOf, latestStoredCandidateOf,
    candidateForAttemptOf,
    // 执行接口(UI 只转发)
    submitAttempt: performSubmitAttempt,
    reconcileAttempt: performReconcileAttempt,
    storeCandidate: ensureCandidateStored,
    buildReferencePayload,
    setReviewFlightReader: (reader) => { deps.reviewFlightReader = reader; },
    setReviewAccess: (access) => { deps.reviewAccess = access; },
    // 批次
    deriveBatch, batchStateReader, runBatch, reconcileOnce,
    confirmAndRun, stopBatch,
    pendingConfirmedShots, confirmationTargetMatched, isConfirmedShotCurrent,
    rememberConfirmation, restore,
    confirmed: () => confirmed,
    reworkEntry: (shotId) => reworkQueues.get(shotId) || null,
    reworkDocumentId: (shotId) => REWORK_CONFIRM_PREFIX + shotId,
    mode: () => authorizationMode,
    enterFailedRetry: (shotIds) => {
      authorizationScope = [...shotIds];
      authorizationMode = "failed_retry";
    },
    enterExplicitNew: (shotId) => {
      authorizationScope = [shotId];
      const state = latestAttemptOf(shotId)?.record.state;
      authorizationMode = state === ATTEMPT_STATES.succeeded ? "rework"
        : state === ATTEMPT_STATES.failed ? "failed_retry" : "explicit_new";
    },
    hasCurrent: hasCurrentQueue,
    shotHasCurrent: shotHasCurrentQueue,
    confirmationFor: confirmationForOf,
    queues: queuesView,
    intent: intentOf,
    reworkIntent: reworkIntentOf,
    // 飞行标识（渲染投影用）
    isAttemptInFlight: (shotId) => attemptInFlight.has(shotId),
    isCandidateInFlight: (shotId) => candidateInFlight.has(shotId),
    isReviewInFlight: (shotId) => deps.reviewFlightReader ? deps.reviewFlightReader(shotId) : false,
    attemptChainsNow: () => Array.from(attemptChains.entries()),
    reset,
  };
}
