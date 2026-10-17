/**
 * 生成视图（设计 §10.1 的第二个视图）：Prompt 准备/编译与人工编辑、生成前确认单、
 * 尝试与批次三区的渲染与命令。
 *
 * 边界（设计 §10.1）：这里只持 DOM（句柄由工作区装配一次传入，不做第二次 getElementById
 * 分发）；不写库、不发网络、不重算业务判定。Prompt 版本/依据的唯一所有者是
 * prompts，确认队列/scope/mode 与尝试/候选链的唯一所有者是 generation；落库/派生/
 * 跨视图刷新都经 deps 回到工作区。确认单投影归 prompts，当前性/环境匹配的唯一判据
 * 在 generation，这里只转发，不重建规则。
 *
 * P5（#10 前端渲染迁移）：三区动态 UI（Prompt 卡片与人工编辑、确认单、尝试行与批次条）与
 * 四个错误位全部由 lit-html 模板拥有，按 shot/prompt 业务身份 keyed；草稿是唯一 UI 状态，按当前项目
 * + shot 精确归属，只有键入了与本次呈现基线不同的文本才算脏。模板直接消费 owner 只读投影，
 * 不再有重绘前的 querySelector 抓取/恢复、每次渲染重复挂监听，或分散在各处的 hidden/disabled
 * 写法；动态按钮的监听由模板 @event 独占（确认/批次按钮不再由工作区 bind 挂第二份）。
 * 错误文案也是视图状态：错误命令只重绘受影响的那一个错误位模板（不再 imperative 写 textContent）。
 * 只保留装配层一次传入的静态句柄做区域级生命周期可见性（locked/editor）与四个错误挂载点。
 *
 * TypeScript 迁移（计划 §9 V2.R7.5）：本文件是唯一手工维护实现；浏览器只消费 Vite 产物。
 */
import { html, nothing, render as renderLit, type TemplateResult } from "lit-html";
import { live } from "lit-html/directives/live.js";
import { createRef, ref } from "lit-html/directives/ref.js";
import { repeat } from "lit-html/directives/repeat.js";
import {
  ATTEMPT_ACTIVE_STATES,
  ATTEMPT_RECONCILE_MODES,
  ATTEMPT_STATES,
  MANUAL_EDIT_REASON_MAX,
  attemptCurrentEnvironmentIdentity,
  attemptPromptStaleness,
  attemptReconcileBlockedMessage,
  attemptReconcileEnvironment,
  attemptReconcileMode,
  attemptStateLabel,
  batchProgressText,
  candidateMatchesAttempt,
  promptStaleness,
  reviewIsCurrent,
  reviewSummaryText,
  selectionSummaryText,
  suitePlanSummary,
  topFinding,
} from "../domain/index.js";
import {
  ROLE_TEXT,
  errorMessageOf,
} from "./dom.js";
import type { ActionSnapshot } from "../session.js";
import type { EffectiveCapabilities, ModelSettings, ProviderCapability } from "../model-settings.js";
import type { InputsModule } from "../project-inputs.js";
import type { ConfirmationSheet, PromptCurrentBasis, PromptModule } from "../prompts.js";
import type {
  ConfirmationQueue,
  GenerationIntent,
  GenerationModule,
  PromptEntry,
  ReconcileAttemptOptions,
  ReconcileAttemptResult,
  StoreCandidateResult,
  SubmitAttemptOptions,
  SubmitAttemptResult,
} from "../generation.js";
import type { SelectionAdoptionModule } from "../selection-adoption.js";
import type {
  DependencyBlocking,
  ImagePromptProfile,
  PromptStaleness,
  SuitePlanSummary,
} from "../domain/type-contracts.js";

/**
 * 本视图负责的生成三区静态句柄（与 index.html 的 id 一一对应，由工作区一次装配）。
 * P5：三区内部的动态句柄（状态行、卡片/行列表、确认摘要、批次控件）与四个错误位都由
 * 模板拥有；这里只留区域级生命周期可见性（locked/editor）与四个错误挂载点——
 * 挂载点是装配层一次传入的空容器（模板渲染 `<p id="…-error" class="error" role="alert">`
 * 进去），视图不替换挂载点自身，也不做第二次 getElementById 分发。
 */
export type GenerationElements = {
  promptLocked: HTMLElement;
  promptEditor: HTMLElement;
  localPreparationStatus: HTMLElement;
  promptDetails: HTMLDetailsElement;
  /** `#prompt-error` 的挂载点（空容器；错误模板渲染到其中）。 */
  promptError: HTMLElement;
  /** `#generate-error` 的挂载点（空容器；与尝试位共用同一份文本）。 */
  generateError: HTMLElement;
  confirmLocked: HTMLElement;
  confirmEditor: HTMLElement;
  /** `#confirm-error` 的挂载点（空容器）。 */
  confirmError: HTMLElement;
  attemptLocked: HTMLElement;
  attemptEditor: HTMLElement;
  /** `#attempt-error` 的挂载点（空容器；与生成位共用同一份文本）。 */
  attemptError: HTMLElement;
};

/**
 * 窄依赖：生成面唯一所有者的命令/投影 + 工作区级收尾与跨视图刷新。
 * 不注入整个工作区；需要工作区状态的都经只读回调读取。
 * 文案类的本地化/连接/后缀助手仍归工作区（输入视图经同一实现复用），这里只经 deps 调用。
 */
export type GenerationViewDeps = {
  prompts: PromptModule;
  inputs: InputsModule;
  generation: GenerationModule;
  selectionAdoption: SelectionAdoptionModule;
  modelSettings: ModelSettings;
  beginAction(): ActionSnapshot;
  currentProjectId(): string | null;
  capabilities(): EffectiveCapabilities | null;
  /** deriveAndApplyState 之后的工作区局部投影：商品理解是否就绪。 */
  understandingReady(): boolean;
  deriveState(): Promise<void>;
  /** 阶段切换（确认单的「去补足此项」按 region 停靠、显式新建 action 回到生成页）；外壳归工作区。 */
  selectStage(stageId: string): void;
  /** 图号 → 人类可读标签（套图方案投影），批次进度与队列摘要共用。 */
  shotLabelOf(shotId: string): string;
  /** 候选预览 URL 缓存归工作区（比较/返工/尝试共用一份 object URL，关闭项目统一撤销）。 */
  ensurePreviewUrl(shotId: string, actionId: string, assetSha256: string): Promise<string | null>;
  /** 比较区入口状态：本片只读判断，比较面板本身下一片迁移。 */
  isComparing(shotId: string): boolean;
  openCompare(shotId: string, options?: { focus?: boolean }): void;
  /** 跨区收尾：比较面板 / 采用进度 / 派生投影仍由工作区渲染（下一片比较视图）。 */
  renderCompare(): void;
  renderSelectionProgress(): void;
  refreshDerived(): void;
  /** 槽位标识与状态词的中文投影；与输入视图共用工作区同一实现。 */
  localizeSlotTerms(message: unknown): string;
  /** 套图依据缺口的连接文本；与提示词分区共用同一实现。 */
  suiteBlockingText(blocking: DependencyBlocking[] | null | undefined): string;
  /** 有后缀的抛出信息；与返工区共用工作区同一实现。 */
  suffixedErrorMessage(error: unknown, fallback: string, suffix: string): string;
};

export type GenerationView = {
  renderPrompts(): void;
  prepareSystemPrompts(): Promise<void>;
  handleCompilePrompt(shotId: string): Promise<void>;
  handleSaveEditedPrompt(shotId: string): Promise<void>;
  handleReconfirmManualPrompt(shotId: string): Promise<void>;
  handleDiscardManualPrompt(shotId: string): Promise<void>;
  /** Prompt 版本/依据只做只读转发（返工区与尝试区经同一入口读，不持有第二份 Map）。 */
  promptRecordOf(shotId: string | null): PromptEntry | null;
  currentImageProfile(): ImagePromptProfile | null;
  promptCurrentBasis(shotId: string | null, provider?: ImagePromptProfile | null): PromptCurrentBasis;
  /** 确认单投影与确认命令（唯一所有者仍是 prompts/generation；这里只装配与呈现）。 */
  renderConfirm(): void;
  handleConfirmGeneration(): Promise<void>;
  confirmationIsCurrent(): boolean;
  confirmationIsCurrentForShot(shotId: string | null): boolean;
  queueShotIsCurrent(queue: ConfirmationQueue, shotId: string): boolean;
  /** 是否有一次确认提交在飞（渲染按钮禁用态与批次续跑共用同一判据）。 */
  isSubmitting(): boolean;
  /** 生成/确认/尝试三区同轮刷新（工作区 renderGenerationSections 的唯一缝）。 */
  render(): void;
  renderAttempts(): void;
  /** 应用 owner 只读文案投影（状态行/错误位）；由工作区订阅 generation 后调用，视图不退订。 */
  applyNotice(): void;
  /** 生成与尝试两处错误位的就近写入（比较视图经工作区复用同一实现）。 */
  showAttemptError(message?: string): void;
  /** 时间戳短格式：尝试历史与比较区共用同一实现。 */
  shortTime(iso: unknown): string;
  /** 项目切换/关闭时统一回收本视图的未保存草稿与呈现基线（P5 草稿精确归属）。 */
  resetViewState(): void;
};

/** 确认单缺项的返回停靠：region → 阶段外壳 id（字面量映射；region 的唯一权威是 prompts 的 fix）。 */
const BLOCKER_STAGE_BY_REGION: Record<string, string> = {
  intake: "intake",
  understanding: "understand",
  suite: "plan",
  style: "generate",
  shot_spec: "generate",
  prompt: "generate",
};

/* ------------------------------------------- 三区模板投影形状（视图只读，不重算判定） */

/** Prompt 卡片行：模板只读这里算好的字段。 */
type PromptRowView = {
  shotId: string;
  order: number;
  label: string;
  satisfied: boolean;
  blockingText: string;
  state: "none" | "saved" | "stale";
  entry: PromptEntry | null;
  isManual: boolean;
  stale: PromptStaleness | null;
  requestLine: string;
  sourceLine: string;
  hashText: string;
  warningTexts: string[];
  editReason: string;
  editedFromVersion: number | null;
  staleFields: string;
  draftText: string;
  draftReason: string;
  canCompile: boolean;
  showReconfirm: boolean;
  canReconfirm: boolean;
  canSaveEdit: boolean;
};

/** 只有文案与 class 的行（摘要/风险），模板不重算。 */
type ConfirmLineView = { className: string; text: string };

type ConfirmBlockerView = {
  order: number;
  label: string;
  code: string;
  message: string;
  regionLabel: string;
  action: string;
  stage: string | undefined;
  openPromptDetails: boolean;
};

type ConfirmShotView = {
  shotId: string;
  order: number;
  label: string;
  roleText: string;
  blocked: boolean;
  stateText: string;
  stateClass: string;
  promptLine: string;
  intent: string | null;
  referencesLine: string;
  techLines: string[];
  risksText: string | null;
  risksTitle: string;
};

type ConfirmView = {
  status: string;
  summary: ConfirmLineView[];
  blockers: ConfirmBlockerView[];
  risks: ConfirmLineView[];
  shots: ConfirmShotView[];
  actionLabel: string;
  actionDisabled: boolean;
  record: string;
};

/** 尝试行上的动作项：按钮命令语义由模板 @event 独占，视图只给只读描述。 */
type AttemptActionCommand = "reconcile" | "submit" | "submit_new" | "store" | "original_credentials" | "none";
type AttemptActionView =
  | { tag: "paragraph"; className: string; text: string }
  | { tag: "span"; className: string; text: string }
  | {
    tag: "button";
    className: string;
    label: string;
    disabled: boolean;
    command: AttemptActionCommand;
    providerId?: string;
  };

type AttemptReviewView = {
  summary: string | null;
  contract: string | null;
  candidate: string;
  vlm: string | null;
  text: string;
};

type AttemptRowView = {
  shotId: string;
  label: string;
  state: string;
  badgeClass: string;
  badgeText: string;
  promptLine: string;
  staleBadgeText: string | null;
  promptTechLines: string[];
  taskLine: string | null;
  techLines: string[];
  note: string | null;
  errorText: string | null;
  preview: { key: string; shotId: string; actionId: string; sha256: string; alt: string } | null;
  candidateMeta: string | null;
  candidateTechLines: string[];
  review: AttemptReviewView | null;
  reviewButton: { candidateId: string; title: string } | null;
  candidateNote: string | null;
  compareCount: number;
  selection: { state: string; text: string } | null;
  pendingNote: string | null;
  staleNote: string | null;
  actions: AttemptActionView[];
  history: string[];
};

/** 尝试计数投影：状态行文案与逐行徽标共用同一份计数。 */
type AttemptCounts = {
  total: number; none: number; active: number; succeeded: number; failed: number; unknown: number;
};

type BatchQueueView = {
  meta: string;
  statement: string;
  resumeDisabled: boolean;
  providerId: string | undefined;
  queue: ConfirmationQueue;
};

type BatchView = {
  ready: boolean;
  progress: string;
  hints: string[];
  queues: BatchQueueView[];
  stopHidden: boolean;
  reconcileHidden: boolean;
  reconcileDisabled: boolean;
  reconcileLabel: string;
  retryHidden: boolean;
  retryDisabled: boolean;
  retryLabel: string;
};

/**
 * 生成视图工厂。
 * @param args.elements 本视图负责的 DOM 句柄
 * @param args.deps 窄依赖：业务所有者命令/投影 + 工作区收尾回调
 */
export function createGenerationView(
  { elements, deps }: { elements: GenerationElements; deps: GenerationViewDeps },
): GenerationView {
  // 依赖别名：搬过来的实现保持原调用写法，装配面只经上面的窄接口进出。
  const inputs = deps.inputs;
  const prompts = deps.prompts;
  const generation = deps.generation;
  const modelSettings = deps.modelSettings;
  const selectionAdoption = deps.selectionAdoption;
  const beginAction = deps.beginAction;
  const localizeSlotTerms = deps.localizeSlotTerms;
  const suiteBlockingText = deps.suiteBlockingText;
  const suffixedErrorMessage = deps.suffixedErrorMessage;

  /** 确认提交在飞（同页双击闸）：视图持有的表现态，不是业务状态。 */
  let submissionInFlight = false;
  /** 本轮确认单呈现给用户的意图；提交时消费「用户看见的那份」，不重算当前最新。 */
  let displayedGenerationIntent: GenerationIntent | null = null;

  /* --------------------------------------------------------- Prompt 编译 */

  // P5 草稿的单一来源（视图状态；DOM 只投影）：键是本视图当前项目的 shot_id，
  // 项目切换经 resetViewState（工作区 reset 链统一回收）后重建，旧项目草稿不外溢。
  type PromptDraftCell = { text: string; reason: string };
  let promptDrafts = new Map<string, PromptDraftCell>();
  /** 每个 shot 的呈现基线：本次渲染时 record 的系统文本；脏判据与恢复都只对它，
   *  保存/重新确认/丢弃成功后由下一轮 render 重置，自动准备覆写系统文本不再被误判为脏草稿。 */
  let promptBaselineText = new Map<string, string>();
  /** 草稿归属的当前项目 id：与 deps.currentProjectId() 不一致＝新一轮 render 先清空草稿。 */
  let draftOwnerProjectId: string | null = null;

  // ---- 显式 UI 状态：命令结果与 owner 投影都先写状态，再由模板投影成 DOM ----
  /** Prompt 区行投影与状态行文案。 */
  let promptRows: PromptRowView[] = [];
  let promptReady = false;
  let promptStatusText = "";
  /** 阶段级本地准备状态行（在 prompt-details 之外，只有这一个投影根）。 */
  let localPreparationText = "";
  /** 确认单投影（含按钮文案/禁用态）与尝试区投影。 */
  let confirmView: ConfirmView = emptyConfirmView();
  let attemptRows: AttemptRowView[] = [];
  let attemptBatch: BatchView = emptyBatchView();
  let attemptStatusText = "";
  /** 确认按钮的唯一节点引用（模板 ref）：显式新建 action 回到生成页时把焦点交回它。 */
  const confirmActionRef = createRef<HTMLButtonElement>();
  /** 候选预览 URL 的视图侧缓存；字节唯一所有者仍是工作区的预览缓存。 */
  const previewUrls = new Map<string, string>();
  const previewPending = new Set<string>();

  // ---- 四个错误位各一份 UI 状态：空串＝无错误（模板用 ?hidden 收起），非空即当前文案 ----
  /** Prompt 区错误（编译/保存/重新确认/丢弃）。 */
  let promptErrorText = "";
  /** 确认单错误（投影失败/授权已变化/外发失败）。 */
  let confirmErrorText = "";
  /** 生成执行位错误；与尝试位共用同一份文本（旧实现同时写这两个位置）。 */
  let generateErrorText = "";
  /** 尝试/候选位错误；与生成位共用同一份文本。 */
  let attemptErrorText = "";

  function emptyConfirmView(): ConfirmView {
    return {
      status: "", summary: [], blockers: [], risks: [], shots: [],
      actionLabel: "确认并生成 0 张", actionDisabled: true,
      record: "",
    };
  }

  function emptyBatchView(): BatchView {
    return {
      ready: false, progress: "", hints: [], queues: [],
      stopHidden: true, reconcileHidden: true, reconcileDisabled: true, reconcileLabel: "核对进行中",
      retryHidden: true, retryDisabled: true, retryLabel: "重试失败",
    };
  }

  /** 技术详情模板：工程字段收进折叠块；同一模板位置复用同一 DOM，展开态不会被重绘重置。 */
  function techDetailsTemplate(lines: string[], label = "技术详情"): TemplateResult | typeof nothing {
    const items = lines.filter((item) => typeof item === "string" && item.length > 0);
    if (!items.length) return nothing;
    return html`
      <details class="tech-details">
        <summary>${label}</summary>
        <p class="meta tech-body">${items.join(" · ")}</p>
      </details>`;
  }

  /** 错误位模板：与旧节点同一 id/class/role，文本与 hidden 由模板投影（挂载点由装配层传入）。 */
  function errorTemplate(id: string, text: string): TemplateResult {
    return html`<p id=${id} class="error" role="alert" ?hidden=${!text}>${text}</p>`;
  }

  /* 错误就近写入：每次只重绘受影响的那个错误位（不整区重绘，也无需通用 DOM 助手）。 */
  function renderPromptError(): void {
    renderLit(errorTemplate("prompt-error", promptErrorText), elements.promptError);
  }
  function renderConfirmError(): void {
    renderLit(errorTemplate("confirm-error", confirmErrorText), elements.confirmError);
  }
  function renderGenerateError(): void {
    renderLit(errorTemplate("generate-error", generateErrorText), elements.generateError);
  }
  function renderAttemptError(): void {
    renderLit(errorTemplate("attempt-error", attemptErrorText), elements.attemptError);
  }
  function setPromptError(message: string): void { promptErrorText = message; renderPromptError(); }
  function setConfirmError(message: string): void { confirmErrorText = message; renderConfirmError(); }
  function setGenerateError(message: string): void { generateErrorText = message; renderGenerateError(); }
  function setAttemptError(message: string): void { attemptErrorText = message; renderAttemptError(); }

  function promptRecordOf(shotId: string | null): PromptEntry | null {
    return prompts.entryOf(shotId, null);
  }

  /** 声明式读口：当前呈现给用户的草稿单元（未编辑时即基线文本 + 空理由）。 */
  function currentDraftCell(shotId: string, recordText: string): PromptDraftCell {
    const draft = promptDrafts.get(shotId);
    return { text: draft ? draft.text : recordText, reason: draft ? draft.reason : "" };
  }

  /** 脏判据（P5 基线）：只在「键入了与本次呈现基线不同的文本」时为真，与持久记录无关。 */
  function isPromptDirty(shotId: string): boolean {
    const draft = promptDrafts.get(shotId);
    if (!draft) return false;
    const baseline = promptBaselineText.get(shotId);
    return baseline === undefined ? draft.text !== "" : draft.text !== baseline;
  }

  function currentImageProfile(): ImagePromptProfile | null {
    return prompts.profile(deps.capabilities()?.images);
  }

  function promptCurrentBasis(
    shotId: string | null, provider: ImagePromptProfile | null = currentImageProfile(),
  ): PromptCurrentBasis {
    // prompts Module 的 basis 缺省来源就是工作区的 projectSources（装配时已注入），
    // 这里不再经工作区转一手，读到的是同一份只读投影。
    return prompts.basis(shotId, provider);
  }

  /** 未保存的编辑草稿（P5）：来源是视图状态，不再重绘前抓取 DOM；
   *  这是 prompts.prepare 的既有入参需要旧签名，这里仅做只读快照转发。 */
  function capturePromptEdits(): Map<string, { text: string; reason: string }> {
    const drafts = new Map<string, { text: string; reason: string }>();
    for (const [shotId, cell] of promptDrafts) {
      drafts.set(shotId, { text: cell.text, reason: cell.reason });
    }
    return drafts;
  }

  /** Prompt 行投影：模板只读这里算好的字段，不重算业务判定。 */
  function projectPromptRows(summary: SuitePlanSummary): PromptRowView[] {
    const running = inputs.isAnalysisRunning();
    const rows: PromptRowView[] = [];
    summary.shots.forEach((item, index) => {
      // 已保存计划恒有 shot_id；null 仅存在于未落库草稿，跳过即可。
      const shotId = item.shot_id;
      if (typeof shotId !== "string") return;
      const entry = promptRecordOf(shotId);
      const stale = entry ? promptStaleness(entry.record, promptCurrentBasis(shotId)) : null;
      const isManual = Boolean(entry && entry.record.origin === "manual_edit");
      // 呈现基线＝本次呈现时记录里的系统文本；草稿只由真正的 input 事件写入。
      if (entry) promptBaselineText.set(shotId, entry.record.compiled.text);
      const cell = entry ? currentDraftCell(shotId, entry.record.compiled.text) : null;
      const provider = entry ? entry.record.compiled.provider : null;
      const dirty = entry ? isPromptDirty(shotId) : false;
      rows.push({
        shotId,
        order: index + 1,
        label: item.label,
        satisfied: item.satisfied,
        blockingText: suiteBlockingText(item.blocking),
        state: entry ? (stale && stale.stale ? "stale" : "saved") : "none",
        entry,
        isManual,
        stale,
        requestLine: "请求：" + (provider && provider.model_id ? provider.model_id : "?") + " · "
          + (provider && provider.size ? provider.size : "?") + " · 参考图 "
          + (entry ? (entry.record.request_snapshot.references || []).length : 0) + " 张",
        sourceLine: entry
          ? "来源 " + (entry.record.compiled.source_refs || []).length + " 条 · "
            + entry.record.compiled.text.length + " 字 · hash " + entry.record.hash.slice(0, 12) + "…"
          : "",
        hashText: entry ? entry.record.hash : "",
        warningTexts: entry
          ? (entry.record.compiled.warnings || []).map((warning) => localizeSlotTerms(warning.message))
          : [],
        editReason: entry && typeof entry.record.edit_reason === "string" ? entry.record.edit_reason : "",
        editedFromVersion: entry && entry.record.edited_from ? entry.record.edited_from.version : null,
        staleFields: stale ? stale.reasons.map((reason) => reason.field).join("、") : "",
        draftText: cell ? cell.text : "",
        draftReason: cell ? cell.reason : "",
        canCompile: item.satisfied && !running,
        showReconfirm: isManual && Boolean(stale && stale.stale),
        canReconfirm: item.satisfied && !running && !dirty,
        canSaveEdit: !running,
      });
    });
    return rows;
  }

  /** Prompt 卡片模板：编译/丢弃/重新确认/保存四个按钮的监听由模板独占。 */
  function promptCardTemplate(row: PromptRowView): TemplateResult {
    const entry = row.entry;
    return html`
      <div class="shot-spec" data-shot-id=${row.shotId} data-prompt-state=${row.state}>
        <div class="shot-spec-head">
          <span class="name">${row.order + ". " + row.label}</span>
          <span class="meta">${entry ? "版本 v" + entry.version : "未编译"}</span>
          <span class=${row.satisfied ? "badge" : "badge is-critical"}>${row.satisfied ? "可编译" : "缺依据"}</span>
          ${row.stale && row.stale.stale ? html`<span class="badge is-critical">已过期</span>` : nothing}
          ${row.isManual ? html`<span class="badge is-proposed">人工编辑</span>` : nothing}
        </div>
        ${entry ? html`
          <pre class="prompt-text">${entry.record.compiled.text}</pre>
          <p class="meta">${row.requestLine}</p>
          <p class="meta prompt-meta">${row.sourceLine}</p>
          <p class="meta prompt-hash">${row.hashText}</p>
          ${row.warningTexts.map((text) => html`<p class="meta prompt-warning">${"提示：" + text}</p>`)}
          ${row.isManual ? html`
            <p class="meta">${"人工编辑 v" + entry.version + "（原因：" + row.editReason + "；被编辑版本 v"
              + (row.editedFromVersion === null ? "?" : row.editedFromVersion) + " 保留）"}</p>` : nothing}
          ${row.stale && row.stale.stale ? html`
            <p class="meta prompt-warning">${"依据已变化（" + row.staleFields + "）。"
              + (row.isManual
                ? "人工全文没有被覆盖；请按当前依据重新确认，或明确丢弃后重新准备。"
                : "系统会本地重新准备，不调用模型。")}</p>` : nothing}
        ` : (row.satisfied ? nothing : html`<p class="meta">${"暂时缺依据：" + row.blockingText}</p>`)}
        <div class="toolbar">
          <button
            type="button"
            class=${row.isManual ? "danger" : ""}
            ?disabled=${!row.canCompile}
            @click=${() => {
              if (row.isManual) void handleDiscardManualPrompt(row.shotId);
              else void handleCompilePrompt(row.shotId);
            }}
          >${row.isManual ? "丢弃人工全文并重新准备" : "重新本地准备"}</button>
          ${row.showReconfirm ? html`
            <button
              type="button"
              ?disabled=${!row.canReconfirm}
              @click=${() => { void handleReconfirmManualPrompt(row.shotId); }}
            >按当前依据确认此人工全文</button>` : nothing}
        </div>
        ${entry ? html`
          <div class="prompt-edit-block">
            <label class="meta" for=${"prompt-edit-" + row.shotId}>人工编辑全文（保存为新版本；原版本保留）</label>
            <textarea
              class="prompt-edit-text"
              id=${"prompt-edit-" + row.shotId}
              data-shot-id=${row.shotId}
              rows="6"
              .value=${live(row.draftText)}
              @input=${(event: Event) => { onPromptTextInput(row.shotId, event); }}
            ></textarea>
            <label class="meta" for=${"prompt-edit-reason-" + row.shotId}>编辑原因（必填，写入版本记录）</label>
            <input
              class="prompt-edit-reason"
              id=${"prompt-edit-reason-" + row.shotId}
              type="text"
              autocomplete="off"
              maxlength=${String(MANUAL_EDIT_REASON_MAX)}
              .value=${live(row.draftReason)}
              @input=${(event: Event) => { onPromptReasonInput(row.shotId, event); }}
            >
            <button
              type="button"
              ?disabled=${!row.canSaveEdit}
              @click=${() => { void handleSaveEditedPrompt(row.shotId); }}
            >保存为新版本</button>
          </div>` : nothing}
      </div>
    `;
  }

  /** Prompt 区（状态行 + 卡片列表）：整区一个模板根，卡片按 shot keyed 稳定复用。 */
  function renderPromptRegion(): void {
    renderLit(html`
      <p id="prompt-status" class="meta" role="status">${promptStatusText}</p>
      <div id="prompt-list">${repeat(promptRows, (row) => row.shotId, (row) => promptCardTemplate(row))}</div>
    `, elements.promptEditor);
  }

  function renderPrompts(): void {
    // 项目切换的精确归属：上一项目的草稿/基线不再参与本项目的任何判据或恢复。
    const currentProjectId = deps.currentProjectId();
    if (currentProjectId !== draftOwnerProjectId) {
      promptDrafts.clear();
      promptBaselineText.clear();
      draftOwnerProjectId = currentProjectId;
    }
    promptReady = Boolean(inputs.suitePlan());
    elements.promptLocked.hidden = promptReady;
    elements.promptEditor.hidden = !promptReady;
    const summary: SuitePlanSummary | null = promptReady
      ? suitePlanSummary(inputs.suitePlan(), inputs.suiteContext()) : null;
    promptRows = summary ? projectPromptRows(summary) : [];
    promptStatusText = summary
      ? "共 " + summary.total + " 张，依据已满足 " + summary.satisfiable + " 张可编译。"
      : "";
    renderPromptRegion();
  }

  /** 草稿键入后的行投影刷新：只重算行，不覆盖命令/摘要写下的状态行。 */
  function refreshPromptRows(): void {
    const summary = promptReady ? suitePlanSummary(inputs.suitePlan(), inputs.suiteContext()) : null;
    promptRows = summary ? projectPromptRows(summary) : [];
    renderPromptRegion();
  }

  /** 命令结果与 owner 文案落状态行：写状态再重绘，文本与按钮态都在模板里。 */
  function setPromptStatus(text: string): void {
    promptStatusText = text;
    renderPromptRegion();
  }

  /** 阶段级本地准备状态行（prompt-details 之外的独立投影根）。 */
  function setLocalPreparationStatus(text: string): void {
    localPreparationText = text;
    renderLit(html`${localPreparationText}`, elements.localPreparationStatus);
  }

  /** 视图状态里的草稿单元：没有草稿时用已呈现的行（不查 DOM，也不误清另一字段）。 */
  function draftCellFor(shotId: string): { text: string; reason: string } {
    const draft = promptDrafts.get(shotId);
    if (draft) return { text: draft.text, reason: draft.reason };
    const row = promptRows.find((item) => item.shotId === shotId);
    return { text: row ? row.draftText : "", reason: row ? row.draftReason : "" };
  }

  function onPromptTextInput(shotId: string, event: Event): void {
    if (!(event.target instanceof HTMLTextAreaElement)) return;
    const cell = draftCellFor(shotId);
    promptDrafts.set(shotId, { text: event.target.value, reason: cell.reason });
    refreshPromptRows();
  }

  function onPromptReasonInput(shotId: string, event: Event): void {
    if (!(event.target instanceof HTMLInputElement)) return;
    const cell = draftCellFor(shotId);
    promptDrafts.set(shotId, { text: cell.text, reason: event.target.value });
    refreshPromptRows();
  }


  /** 本地准备是 prompts Module 的动作；这里只传视图状态里的草稿并呈现结果文案。 */
  async function prepareSystemPrompts(): Promise<void> {
    if (!deps.currentProjectId() || prompts.isPreparing()) return;
    const action = beginAction();
    if (!action.projectId) return;
    const gate = !inputs.suitePlan()
      ? "先添加图片任务；本地准备不会调用模型。"
      : (!deps.understandingReady() ? "请人工确认核心事实；各图片用途的额外缺项就地补足。"
        : (!currentImageProfile() ? "等待有效图像配置；打开模型设置可恢复。" : null));
    if (gate) {
      setLocalPreparationStatus(gate);
      return;
    }
    setLocalPreparationStatus("正在本地准备已就绪图片任务；不会调用模型…");
    renderConfirm();
    try {
      const result = await prompts.prepare(capturePromptEdits());
      if (!action.alive()) return;
      if (result.reason === "no_plan" || result.reason === "facts" || result.reason === "configuration") {
        setLocalPreparationStatus(result.reason === "no_plan"
          ? "先添加图片任务；本地准备不会调用模型。"
          : result.reason === "facts" ? "请人工确认核心事实；各图片用途的额外缺项就地补足。"
            : "等待有效图像配置；打开模型设置可恢复。");
        return;
      }
      if (result.reason === "in_flight" || result.reason === "stale_session"
        || result.reason === "no_project") return;
      if (result.reason === "unchanged") {
        // P5：unchanged 是完成态，不再静默早退——状态行必须落地，否则「正在本地准备…」悬空。
        setLocalPreparationStatus(
          "本地准备结果：各图片任务的依据没有变化，无需重试；未调用模型。");
        return;
      }
      setLocalPreparationStatus(result.errors.length
        ? "部分任务尚未准备：" + result.errors.join("；")
        : "本地准备完成" + (result.prepared ? "（更新 " + result.prepared + " 张）" : "")
          + "；未调用模型。人工文本保留，提交前请核对下面的摘要。");
      await deps.deriveState();
    } finally {
      if (action.alive()) { renderPrompts(); renderConfirm(); renderAttempts(); }
    }
  }

  async function handleReconfirmManualPrompt(shotId: string): Promise<void> {
    const entry = promptRecordOf(shotId);
    if (!entry || entry.record.origin !== "manual_edit") return;
    const action = beginAction();
    // P5：草稿单一来源——脏判据与文本都从视图状态读，textarea 可能已随上一轮重绘清空。
    if (isPromptDirty(shotId)) {
      setPromptError("此全文有未保存修改；先保存，再重新确认，不会确认另一份旧文本。");
      return;
    }
    setPromptError("");
    try {
      const visibleText = currentDraftCell(shotId, entry.record.compiled.text).text;
      const saved = await prompts.reconfirm(shotId, visibleText, action);
      if (!saved) return;
      if (!action.alive()) return;
      promptDrafts.delete(shotId);
      renderPrompts(); renderConfirm(); renderAttempts();
      setPromptStatus("人工全文原文保留，已按当前依据重新确认为 v" + saved.version + "；未调用模型。");
    } catch (error) {
      if (action.alive()) setPromptError(errorMessageOf(error, "重新确认失败；原人工全文保留。"));
    }
  }

  async function handleDiscardManualPrompt(shotId: string): Promise<void> {
    const entry = promptRecordOf(shotId);
    if (!entry || entry.record.origin !== "manual_edit") return;
    const action = beginAction();
    setPromptError("");
    try {
      const payload = await prompts.discard(shotId, action);
      if (!action.alive() || !payload) return;
      // 明确丢弃＝视图状态里该 shot 的草稿一起回收；重绘后 textarea 内容是恢复的系统文本。
      promptDrafts.delete(shotId);
      renderPrompts(); renderConfirm(); renderAttempts();
      setPromptStatus("已明确丢弃人工覆盖并恢复当前系统 Prompt；历史全文保留，未调用模型。");
    } catch (error) {
      if (action.alive()) setPromptError(errorMessageOf(error, "丢弃未完成；原全文与输入保留。"));
    }
  }

  async function handleCompilePrompt(shotId: string): Promise<void> {
    if (!deps.currentProjectId() || !inputs.suitePlan() || !deps.understandingReady()) return;
    const action = beginAction();
    setPromptError("");
    try {
      const result = await prompts.compileAndSave(shotId, { action });
      if (!action.alive()) return;
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deps.deriveState();
      if (!action.alive()) return;
      setPromptStatus("已保存 " + shotId + " 的 Prompt 版本 v" + result.saved.version + "。");
    } catch (error) {
      if (!action.alive()) return;
      setPromptError(
        suffixedErrorMessage(error, "编译未完成，旧版本已保留。", "（旧版本已保留）"));
      renderPrompts();
      renderConfirm();
      renderAttempts();
    }
  }

  /** 人工编辑：保存为新版本；失败时保留旧版本与用户输入，不清空文本区。 */
  async function handleSaveEditedPrompt(shotId: string): Promise<void> {
    if (!deps.currentProjectId() || !inputs.suitePlan() || !deps.understandingReady()) return;
    const action = beginAction();
    setPromptError("");
    const entry = promptRecordOf(shotId);
    if (!entry) {
      setPromptError("先编译并保存这张图的 Prompt，再编辑。");
      return;
    }
    // P5：保存读的是视图状态里用户看见的文本/理由；textarea 不再是数据来源，
    // 二次 getElementById 查询路径删除。
    const cell = currentDraftCell(shotId, entry.record.compiled.text);
    try {
      const saved = await prompts.edit(shotId, cell.text, cell.reason, action);
      if (!action.alive()) return;
      promptDrafts.delete(shotId);
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deps.deriveState();
      if (!action.alive()) return;
      setPromptStatus("已保存 " + shotId + " 的人工编辑版本 v" + saved.version
        + "（被编辑版本 v" + entry.version + " 保留）。");
    } catch (error) {
      if (action.alive()) {
        setPromptError(
          suffixedErrorMessage(error, "编辑未保存，旧版本与输入已保留。", "（旧版本与输入已保留）"));
      }
    }
  }

  /* ---------------------------------------------------------- 生成前确认 */

  /** 单图当前性：转发 generation.isConfirmedShotCurrent（执行与按钮同一判据）。 */
  function queueShotIsCurrent(queue: ConfirmationQueue, shotId: string): boolean {
    return generation.isConfirmedShotCurrent(queue, shotId);
  }

  /** 确认记录是否仍然对得上「这一批将要提交的东西」（owner 只读投影）。 */
  function confirmationIsCurrent(): boolean {
    return generation.hasCurrent();
  }

  /** 提交这张图的条件：这张图在某个现存授权队列里仍有效（generation 统一判据）。 */
  function confirmationIsCurrentForShot(shotId: string | null): boolean {
    if (!shotId) return false;
    return generation.shotHasCurrent(shotId);
  }

  /** 确认单投影：所见摘要由 generation 准备，这里只呈现，不重算、不猜版本。 */
  function projectConfirm(): ConfirmView {
    let sheet: ConfirmationSheet | null = null;
    try {
      // 所见摘要由 generation 准备：视图只保存并原样交回，不重算、不猜版本。
      displayedGenerationIntent = generation.prepareSummary();
      sheet = displayedGenerationIntent ? displayedGenerationIntent.all : null;
    } catch (error) {
      setConfirmError(
        "生成前确认投影失败：" + errorMessageOf(error, "未知错误"));
      return emptyConfirmView();
    }
    if (!sheet || !displayedGenerationIntent) {
      return {
        ...emptyConfirmView(),
        status: "尚未取得有效图像能力；恢复服务后再确认，不会提交未经核对的请求。",
      };
    }
    const intent = displayedGenerationIntent;
    const sending = intent.sheet;
    const sendingIds = new Set(sending ? sending.shots.map((item) => item.shot_id) : []);
    const summary: ConfirmLineView[] = [{
      className: "confirm-summary",
      text: sending ? sending.external_summary.statement : "当前没有可新增发送的已就绪图片任务。",
    }];
    if (intent.mode === "explicit_new") {
      summary.push({
        className: "prompt-warning",
        text: "这是另一个新动作，不是核对原任务。原 Unknown 可能已经被受理，另发可能重复扣费；原记录与采用不删除、不覆盖。",
      });
    }
    summary.push({
      className: "meta",
      text: "每张图发送自己的 Prompt 文本与上列参考图；不发送本地文件本身、历史候选或其他项目数据。",
    });
    const blockers: ConfirmBlockerView[] = sheet.blockers.map((blocker) => ({
      order: blocker.order,
      label: blocker.label,
      code: blocker.code,
      message: localizeSlotTerms(blocker.message),
      regionLabel: blocker.fix.region,
      action: blocker.fix.action,
      stage: BLOCKER_STAGE_BY_REGION[blocker.fix.region],
      openPromptDetails: blocker.fix.region === "prompt",
    }));
    const risks: ConfirmLineView[] = sheet.risks.map((risk) => ({
      className: "confirm-risk",
      text: risk.label + " · " + risk.code + "：" + localizeSlotTerms(risk.message),
    }));
    const shots: ConfirmShotView[] = sheet.shots.map((item) => ({
      shotId: item.shot_id,
      order: item.order,
      label: item.label,
      roleText: (item.role_label || item.role_id || "未分类") + (item.required ? " · 必需" : " · 可选"),
      blocked: item.blockers.length > 0,
      stateClass: item.blockers.length > 0 ? "badge is-critical" : "badge is-confirmed",
      stateText: sendingIds.has(item.shot_id) ? "本次发送"
        : item.blockers.length ? "本次不发送：缺项／过期" : "本次不重复提交",
      promptLine: item.prompt.version === null
        ? "未编译"
        : "Prompt v" + item.prompt.version + " · " + String(item.prompt.hash).slice(0, 12) + "…",
      intent: item.intent,
      referencesLine: "参考图 " + item.references.length + " 张（"
        + (item.references.map((ref) => ROLE_TEXT[ref.role] || ref.role).join("、") || "无") + "）"
        + (item.prompt.chars === null ? "" : " · 提示词 " + item.prompt.chars + " 字"),
      techLines: item.references.map((ref) => (ROLE_TEXT[ref.role] || ref.role) + " sha256 " + ref.sha256_prefix),
      risksText: item.risks.length > 0
        ? "风险：" + item.risks.map((risk) => localizeSlotTerms(risk.message || risk.code)).join("；")
        : null,
      risksTitle: item.risks.map((risk) => risk.code).join("、"),
    }));
    const identity = intent.identity;
    return {
      status: "本次明确发送 " + (sending ? sending.total : 0) + " 张；"
        + "用途缺项／过期任务不外发；已有成功、进行中或 Unknown 不自动重提。",
      summary,
      blockers,
      risks,
      shots,
      actionLabel: (intent.mode === "explicit_new" ? "确认并另发 " : "确认并生成 ")
        + (sending ? sending.total : 0) + " 张",
      actionDisabled: !(sending && sending.can_submit) || !(identity && identity.configured)
        || inputs.isAnalysisRunning() || prompts.isPreparing() || submissionInFlight
        || modelSettings.refreshing || Boolean(generation.batchStateReader()?.active),
      record: identity && identity.configured
        ? "一次点击先保存这份授权，再按摘要外发；不会要求第二次提交。"
        : "原目标凭据未就绪。打开模型设置补凭据；本地事实、Prompt、采用和导出不受影响。",
    };
  }

  /** 确认单模板：摘要/阻断项/风险/逐图行与确认按钮全部由模板拥有。 */
  function confirmRegionTemplate(): TemplateResult {
    const view = confirmView;
    return html`
      <p id="confirm-status" class="meta" role="status">${view.status}</p>
      <div id="confirm-summary">
        ${view.summary.map((line) => html`<p class=${line.className}>${line.text}</p>`)}
      </div>
      <div id="confirm-blockers">
        ${view.blockers.map((blocker) => html`
          <p class="confirm-blocker">
            <span>${"#" + blocker.order + " " + blocker.label + " · " + blocker.code}</span>
            <span class="meta">${blocker.message}</span>
            <span class="meta">${"返回：" + blocker.regionLabel + " · " + blocker.action}</span>
            <button
              type="button"
              @click=${() => {
                if (blocker.stage) deps.selectStage(blocker.stage);
                // P5：#prompt-details 归属装配层（工作区一次性注入），视图不全局查询。
                if (blocker.openPromptDetails) elements.promptDetails.open = true;
              }}
            >去补足此项</button>
          </p>`)}
      </div>
      <div id="confirm-risks">
        ${view.risks.map((line) => html`<p class=${line.className}>${line.text}</p>`)}
      </div>
      <div id="confirm-list">
        ${repeat(view.shots, (row) => row.shotId, (row) => html`
          <div class="confirm-shot" data-shot-id=${row.shotId} data-blocked=${String(row.blocked)}>
            <div class="confirm-shot-head">
              <span class="name">${row.order + ". " + row.label}</span>
              <span class="badge">${row.roleText}</span>
              <span class=${row.stateClass}>${row.stateText}</span>
              <span class="meta">${row.promptLine}</span>
            </div>
            ${row.intent ? html`<p class="meta">${"任务：" + row.intent}</p>` : nothing}
            <p class="meta">${row.referencesLine}</p>
            ${techDetailsTemplate(row.techLines)}
            ${row.risksText === null ? nothing
              : html`<p class="meta prompt-warning" title=${row.risksTitle}>${row.risksText}</p>`}
          </div>`)}
      </div>
      <div class="toolbar">
        <button
          id="confirm-action"
          class="primary"
          type="button"
          ${ref(confirmActionRef)}
          ?disabled=${view.actionDisabled}
          @click=${() => { void handleConfirmGeneration(); }}
        >${view.actionLabel}</button>
        <span id="confirm-record" class="meta" role="status">${view.record}</span>
      </div>
    `;
  }

  function renderConfirmRegion(): void {
    renderLit(confirmRegionTemplate(), elements.confirmEditor);
  }

  /** 提交在飞的按钮禁用：只改这一处投影，不重算用户看过的摘要。 */
  function setConfirmActionDisabled(disabled: boolean): void {
    confirmView.actionDisabled = disabled;
    renderConfirmRegion();
  }

  function renderConfirm(): void {
    const ready = Boolean(inputs.suitePlan());
    elements.confirmLocked.hidden = ready;
    elements.confirmEditor.hidden = !ready;
    displayedGenerationIntent = null;
    confirmView = ready ? projectConfirm() : emptyConfirmView();
    renderConfirmRegion();
  }

  async function handleConfirmGeneration(): Promise<void> {
    if (!deps.currentProjectId() || !inputs.suitePlan() || submissionInFlight
      || prompts.isPreparing() || modelSettings.refreshing) return;
    const authorized = displayedGenerationIntent;
    if (!authorized) return;
    const action = beginAction();
    submissionInFlight = true;
    setConfirmActionDisabled(true);
    setConfirmError("");
    try {
      // 只交出用户看过的那份摘要：授权文档/所见版本/当前性核对都在 owner 内部完成。
      const result = await generation.confirmAndRun({ intent: authorized });
      // stale：owner 已算出新摘要并零外发；把新摘要直接读给用户，避免"只说过期、不知道变成什么"。
      // 不自动确认、不自动重提；下面 finally 的 renderConfirm 会按 owner 当前投影重新呈现。
      if (result.stale && action.alive()) {
        const fresh = result.intent?.sheet?.external_summary?.statement || "";
        setConfirmError(
          (result.message || "摘要已变化；请核对新摘要后再确认。") + (fresh ? "当前摘要：" + fresh : ""));
      }
    } catch (error) {
      if (action.alive()) setConfirmError(errorMessageOf(error, "生成没有完成；授权与历史保留。"));
    } finally {
      submissionInFlight = false;
      // 确认写库后派生项目状态（PLAN_REVIEW → READY_TO_GENERATE）：与编译保存同一语义，
      // 否则确认存在但状态不前进，-05 类“确认存在且状态前进”断言永远红。
      try { if (action.alive()) await deps.deriveState(); } catch { /* 状态派生失败不吞确认结果 */ }
      if (action.alive()) { renderConfirm(); renderAttempts(); }
     }
  }

  /* ------------------------------------------------------------ 生成执行 */

  /** 尝试状态行：命令结果就近写入状态并重绘；owner 旁路文案也经 applyNotice 落到这里。 */
  function setAttemptStatus(text: string): void {
    attemptStatusText = text;
    renderAttemptRegion();
  }

  /** 上一份已应用的 owner 错误文本：只在 owner 从"有错误"变回"无错误"时同步清 DOM。 */
  let appliedOwnerError = "";

  /**
   * owner 投影变化的应用（订阅 generation 后由工作区调用）：先按只读投影重渲染尝试/候选行
   * 与批次进度（含跨区刷新），再写 owner 的旁路文案——顺序与旧回调一致（render 后 status），
   * 否则状态行会被计数摘要盖掉。忙碌/进度仍只读飞行标识与批次投影，不解读业务状态。
   */
  function applyNotice(): void {
    renderAttempts();
    const notice = generation.notice();
    if (notice.status) setAttemptStatus(notice.status);
    if (notice.error) showAttemptError(notice.error);
    else if (appliedOwnerError) clearAttemptError();
    appliedOwnerError = notice.error;
  }

  /** 生成与尝试两个位置共用同一份错误文本：错误就近显示在对应阶段（只重绘这两个错误位）。 */
  function showAttemptError(message?: string): void {
    setGenerateError(message || "");
    setAttemptError(message || "");
  }

  function clearAttemptError(): void {
    setGenerateError("");
    setAttemptError("");
  }

  /** 图像能力投影：只读 capabilities，不重算判定。 */
  function imageProviderBlock(): ProviderCapability | null {
    const caps = deps.capabilities();
    const images = caps && caps.images ? caps.images : null;
    return images && images.provider ? images.provider : null;
  }

  function attemptBadgeClass(state: unknown): string {
    if (state === ATTEMPT_STATES.succeeded) return "is-attempt-done";
    if (state === ATTEMPT_STATES.failed) return "is-attempt-failed";
    if (state === ATTEMPT_STATES.unknown) return "is-attempt-unknown";
    return "is-attempt-active";
  }

  function shortTime(iso: unknown): string {
    if (!iso) return "?";
    try {
      // Date 接受的输入是 string|number|Date；其余形状直接走下面的 String 回退。
      const date = new Date(iso as string | number | Date);
      return date.toLocaleString("zh-CN", { hour12: false });
    } catch (error) {
      return String(iso);
    }
  }

  /** 当前 Prompt 指针：尝试的新旧依据比对输入（版本 + hash）。 */
  function currentPromptPointer(shotId: string | null): { version: number; hash: string } | null {
    const entry = promptRecordOf(shotId);
    return entry ? { version: entry.version, hash: entry.record.hash } : null;
  }

  /** 单张「保存候选图片」按钮入口：只翻译结果，不做批次策略。 */
  async function handleStoreCandidate(shotId: string): Promise<StoreCandidateResult> {
    clearAttemptError();
    const result = await generation.storeCandidate(shotId);
    if (result.stored) {
      // 报告摘要只读 adoption 的投影（确定性报告由 adoption 单向消费）；未建好就不显示摘要。
      const candidateId = result.candidate_id;
      const entry = candidateId ? selectionAdoption.reportOf(candidateId) : null;
      setAttemptStatus("候选已保存（" + result.width + "×" + result.height + "）。"
        + (entry ? " " + reviewSummaryText(entry.report) : ""));
    } else if (result.failed) {
      showAttemptError(result.message);
    } else if (result.reason === "already_stored") {
      setAttemptStatus("这条记录的候选已在本地，无需重复保存。");
    } else if (result.reason === "not_succeeded") {
      showAttemptError("这次生成还没有成功结论，暂不能保存候选。");
    } else if (result.reason === "no_task_id") {
      showAttemptError("这条记录没有任务编号，无法取回候选。");
    } else if (result.reason === "no_attempt") {
      showAttemptError("这张图还没有生成记录。");
    }
    return result;
  }

  /** 尝试行投影：模板只读这里算好的字段；按钮命令语义由模板 @event 独占。 */
  function projectAttemptRows(summary: SuitePlanSummary, counts: AttemptCounts): AttemptRowView[] {
    const rows: AttemptRowView[] = [];
    const batchActive = Boolean(generation.batchStateReader()?.active);
    for (const item of summary.shots) {
      const shotId = item.shot_id;
      const chain = generation.attemptChainOf(shotId);
      const latest = generation.latestAttemptOf(shotId);
      const record = latest ? latest.record : null;
      const state = record ? record.state : null;
      const entry = promptRecordOf(shotId);
      const stale = record ? attemptPromptStaleness(record, currentPromptPointer(shotId)) : null;
      counts.total += 1;
      if (!record) counts.none += 1;
      else if (state === ATTEMPT_STATES.succeeded) counts.succeeded += 1;
      else if (state === ATTEMPT_STATES.failed) counts.failed += 1;
      else if (state === ATTEMPT_STATES.unknown) counts.unknown += 1;
      else counts.active += 1;

      const inFlight = generation.isAttemptInFlight(shotId) || inputs.isAnalysisRunning() || batchActive;
      const shotConfirmed = confirmationIsCurrentForShot(shotId);
      const canSubmit = shotConfirmed && Boolean(entry) && !inFlight;
      const reconcileMode = record ? attemptReconcileMode(record) : ATTEMPT_RECONCILE_MODES.none;
      const stuckPending = Boolean(state === ATTEMPT_STATES.pending_submit && record && !record.task_id);

      let taskLine: string | null = null;
      let techLines: string[] = [];
      let note: string | null = null;
      let errorText: string | null = null;
      let preview: AttemptRowView["preview"] = null;
      let candidateMeta: string | null = null;
      let candidateTechLines: string[] = [];
      let review: AttemptReviewView | null = null;
      let reviewButton: AttemptRowView["reviewButton"] = null;
      let candidateNote: string | null = null;
      let pendingNote: string | null = null;
      if (record) {
        const parts = ["提交 " + shortTime(record.created_at)];
        if (record.updated_at !== record.created_at) parts.push("更新 " + shortTime(record.updated_at));
        taskLine = parts.join(" · ");
        techLines = ["action " + record.action_id];
        if (record.task_id) techLines.push("task " + record.task_id);
        note = record.change_log.length ? record.change_log[record.change_log.length - 1].note : null;
        if (record.error) {
          errorText = (state === ATTEMPT_STATES.unknown ? "未知原因：" : "失败原因：")
            + record.error.family + " / " + record.error.code + "：" + record.error.message
            + "（重试策略 " + record.error.retry_policy + "）";
        }
        if (state === ATTEMPT_STATES.succeeded) {
          const stored = generation.candidateForAttemptOf(shotId, record.action_id);
          if (stored && candidateMatchesAttempt(stored, record)) {
            const candidate = stored.record;
            preview = {
              key: shotId + ":" + record.action_id + ":" + candidate.asset_sha256,
              shotId,
              actionId: record.action_id,
              sha256: candidate.asset_sha256,
              alt: item.label + " 的候选",
            };
            candidateMeta = "候选已保存到本地 · " + candidate.width + "×" + candidate.height + " · "
              + candidate.media_type + " · "
              + Math.max(1, Math.round(candidate.byte_size / 1024)) + " KB（预览来自本地字节）";
            candidateTechLines = ["sha256 " + candidate.asset_sha256.slice(0, 12) + "…"];
            const reviewEntry = selectionAdoption.reportOf(candidate.candidate_id);
            if (reviewEntry && reviewIsCurrent(reviewEntry.report, candidate)) {
              const top = topFinding(reviewEntry.report);
              review = {
                summary: reviewSummaryText(reviewEntry.report),
                contract: reviewEntry.report.review_contract_version,
                candidate: candidate.candidate_id,
                vlm: null,
                text: reviewSummaryText(reviewEntry.report)
                  + (top ? " · 先看：" + top.title + " — " + top.detail : " · 无待处理项"),
              };
            } else {
              // 确定性报告缺失与"补建失败"必须分开：失败要如实显示原因，不能伪装成"AI 未复核"。
              const reportFailure = selectionAdoption.reportBuildFailure(candidate.candidate_id);
              review = {
                summary: reportFailure ? "failed" : "missing",
                contract: null,
                candidate: "",
                vlm: "not_run",
                text: (reportFailure
                  ? "自动检查报告补建失败：" + reportFailure
                    + "（候选与本地图片保留，原采用不受影响;采用或重新打开项目会再补建，不需要 AI）"
                  : "自动检查报告尚未生成（候选保存或重新打开项目后由本地补建，不调用模型）")
                  + " AI 复核未运行：按需发起才会调用，未复核不阻断人工采用。",
              };
            }
            reviewButton = {
              candidateId: candidate.candidate_id,
              title: "只在你点这一下时才调用视觉语言模型找可疑问题；查看、采用都不会触发。只提示，不自动采纳；未复核不阻断人工采用。",
            };
          } else if (stored) {
            candidateNote = "候选记录与来源 Attempt 不一致：不显示预览（记录保留，等待复核）。";
          } else {
            candidateNote = "上游已完成，候选字节尚未保存到本地。";
          }
        }
        if ((state === ATTEMPT_STATES.pending_submit || state === ATTEMPT_STATES.unknown)
            && !record.task_id) {
          pendingNote = "这次提交没有留下任务编号（可能已到达上游）。系统不会自动重提；可以显式新建 action，或先核对（若已有编号）。";
        }
      }

      // 比较区只看候选链：最新一次尝试是失败/未知时，历史候选仍然可以比较与返工。
      const candidateCount = generation.candidateChainOf(shotId).length;
      const selectionEntry = selectionAdoption.entryOf(shotId);
      const selectionState = selectionAdoption.stateOf(shotId);

      const actions: AttemptActionView[] = [];
      if (reconcileMode === ATTEMPT_RECONCILE_MODES.by_task && record) {
        const environment = attemptCurrentEnvironmentIdentity(modelSettings.imageEnvironment(
          record.provider.provider_id, record.execution_identity.credential_reference.source));
        const gate = attemptReconcileEnvironment(record, environment);
        if (gate.mode !== ATTEMPT_RECONCILE_MODES.by_task) {
          actions.push({ tag: "paragraph", className: "meta", text: attemptReconcileBlockedMessage(record) });
          actions.push({
            tag: "button",
            className: "",
            label: record.execution_identity.credential_reference.source === "byok"
              ? "给原目标补凭据" : "查看原目标配置",
            disabled: false,
            command: "original_credentials",
            providerId: record.execution_identity.credential_reference.source === "byok"
              ? record.provider.provider_id : undefined,
          });
        }
        actions.push({
          tag: "button",
          className: "",
          label: "核对任务",
          disabled: inFlight || gate.mode !== ATTEMPT_RECONCILE_MODES.by_task,
          command: "reconcile",
        });
      }
      if (!record) {
        actions.push({
          tag: "button", className: "primary", label: "生成这张图",
          disabled: !canSubmit, command: "submit",
        });
      } else if (stuckPending || state === ATTEMPT_STATES.unknown) {
        actions.push({
          tag: "button", className: "", label: "新建 action（放弃核对）",
          disabled: !entry || inFlight, command: "submit_new",
        });
      } else if (state === ATTEMPT_STATES.failed) {
        actions.push({
          tag: "button", className: "", label: "重试（新建 action）",
          disabled: !entry || inFlight, command: "submit_new",
        });
      } else if (state === ATTEMPT_STATES.succeeded) {
        const stored = generation.candidateForAttemptOf(shotId, record.action_id);
        if (!stored) {
          // 批次运行中也要能用：取回失败时提示区正让用户点这个按钮,而它只做本地保存,
          // 同一张的并发保存由 isCandidateInFlight 挡住(模块内直接 no-op)。
          actions.push({
            tag: "button", className: "primary", label: "保存候选图片",
            disabled: generation.isAttemptInFlight(shotId) || inputs.isAnalysisRunning()
              || generation.isCandidateInFlight(shotId),
            command: "store",
          });
        }
        actions.push({
          tag: "button", className: "", label: "再生成一张（新建 action）",
          disabled: !entry || inFlight, command: "submit_new",
        });
      } else if (record && state && ATTEMPT_ACTIVE_STATES.includes(state)) {
        actions.push({
          tag: "button", className: "", label: inFlight ? "提交中…" : "上游处理中，先核对",
          disabled: true, command: "none",
        });
      }
      if (!shotConfirmed) {
        actions.push({
          tag: "span", className: "meta",
          text: "这张图还没有有效的生成前确认：先在「生成前确认」确认整套，或在候选比较面板里走一次返工确认。",
        });
      } else if (!entry) {
        actions.push({ tag: "span", className: "meta", text: "先编译并保存这张图的 Prompt。" });
      }

      rows.push({
        shotId,
        label: item.label,
        state: state || "none",
        badgeClass: record ? attemptBadgeClass(state) : "is-missing",
        badgeText: record ? attemptStateLabel(state) : "尚未生成",
        promptLine: entry ? "Prompt v" + entry.version : "未编译 Prompt",
        staleBadgeText: stale && stale.stale ? "基于旧版本 v" + stale.attempt_version : null,
        promptTechLines: entry ? ["hash " + String(entry.record.hash).slice(0, 12) + "…"] : [],
        taskLine,
        techLines,
        note,
        errorText,
        preview,
        candidateMeta,
        candidateTechLines,
        review,
        reviewButton,
        candidateNote,
        compareCount: candidateCount,
        selection: (selectionEntry || candidateCount > 0)
          ? { state: selectionState, text: selectionSummaryText(selectionEntry ? selectionEntry.record : null, selectionState) }
          : null,
        pendingNote,
        staleNote: stale && stale.stale
          ? "这条记录基于 Prompt v" + stale.attempt_version + "；当前是 v" + stale.current_version
            + "。要按新版出图，请先重新确认，再新建 action。"
          : null,
        actions,
        history: chain.length > 1
          ? chain.slice().reverse().map((item2) => {
            const itemRecord = item2.record;
            return "v" + item2.version + " · " + attemptStateLabel(itemRecord.state)
              + " · action " + itemRecord.action_id
              + (itemRecord.task_id ? " · task " + itemRecord.task_id : "")
              + " · " + shortTime(itemRecord.updated_at);
          })
          : [],
      });
    }
    return rows;
  }

  /** 失败图重试摘要：进入失败重试 scope 后回到生成页并刷新确认单（原工作区监听同一语义）。 */
  function onBatchRetry(): void {
    generation.enterFailedRetry(generation.deriveBatch().retry_queue);
    deps.selectStage("generate");
    renderConfirm();
  }

  /** AI 复核这条候选：真失败才提示，未发起仍是未复核。 */
  async function handleReviewCandidate(shotId: string, candidateId: string): Promise<void> {
    const outcome = await selectionAdoption.reviewCandidate(shotId, candidateId);
    if (outcome && outcome.failed) {
      setAttemptStatus("复核未完成：" + outcome.message
        + "（候选与报告保持不变；真实失败才记 Unknown，未发起仍是未复核）");
    }
  }

  function onAttemptAction(shotId: string, action: AttemptActionView): void {
    if (action.tag !== "button") return;
    if (action.command === "reconcile") void handleReconcileAttempt(shotId);
    else if (action.command === "submit") void handleSubmitAttempt(shotId);
    else if (action.command === "submit_new") void handleSubmitAttempt(shotId, { explicitNew: true });
    else if (action.command === "store") void handleStoreCandidate(shotId);
    else if (action.command === "original_credentials") modelSettings.open("image", action.providerId);
  }

  function actionTemplate(shotId: string, action: AttemptActionView): TemplateResult {
    if (action.tag === "paragraph") return html`<p class=${action.className}>${action.text}</p>`;
    if (action.tag === "span") return html`<span class=${action.className}>${action.text}</span>`;
    return html`
      <button
        type="button"
        class=${action.className}
        ?disabled=${action.disabled}
        data-original-credentials=${action.command === "original_credentials" ? shotId : nothing}
        @click=${() => { onAttemptAction(shotId, action); }}
      >${action.label}</button>`;
  }

  /** 尝试行模板：预览图片地址读视图侧缓存（同代只请求一次，keyed 行不重建）。 */
  function attemptRowTemplate(row: AttemptRowView): TemplateResult {
    const previewUrl = row.preview ? previewUrls.get(row.preview.key) || null : null;
    return html`
      <div class="attempt-row" data-shot-id=${row.shotId} data-attempt-state=${row.state} tabindex="-1">
        <div class="attempt-head">
          <span class="name">${row.label}</span>
          <span class=${"badge " + row.badgeClass}>${row.badgeText}</span>
          <span class="meta">${row.promptLine}</span>
          ${row.staleBadgeText === null ? nothing
            : html`<span class="badge is-attempt-stale">${row.staleBadgeText}</span>`}
        </div>
        ${techDetailsTemplate(row.promptTechLines)}
        ${row.taskLine === null ? nothing : html`<p class="meta attempt-task">${row.taskLine}</p>`}
        ${techDetailsTemplate(row.techLines)}
        ${row.note === null ? nothing : html`<p class="meta">${"最近一次变化：" + row.note}</p>`}
        ${row.errorText === null ? nothing : html`<p class="attempt-error-text">${row.errorText}</p>`}
        ${!row.preview ? nothing : html`
          <div class="attempt-preview">
            ${previewUrl === null
              ? html`<img alt=${row.preview.alt} loading="lazy">`
              : html`<img src=${previewUrl} alt=${row.preview.alt} loading="lazy">`}
          </div>`}
        ${row.candidateMeta === null ? nothing
          : html`<p class="meta attempt-candidate">${row.candidateMeta}</p>`}
        ${techDetailsTemplate(row.candidateTechLines)}
        ${!row.review ? nothing : html`
          <p
            class="meta attempt-review"
            data-review-summary=${row.review.summary === null ? nothing : row.review.summary}
            data-review-contract=${row.review.contract === null ? nothing : row.review.contract}
            data-review-candidate=${row.review.candidate === "" ? nothing : row.review.candidate}
            data-review-vlm=${row.review.vlm === null ? nothing : row.review.vlm}
          >${row.review.text}</p>`}
        ${!row.reviewButton ? nothing : html`
          <button
            type="button"
            data-review-action=${row.reviewButton.candidateId}
            title=${row.reviewButton.title}
            @click=${() => {
              const candidateId = row.reviewButton ? row.reviewButton.candidateId : "";
              if (candidateId) void handleReviewCandidate(row.shotId, candidateId);
            }}
          >${selectionAdoption.isReviewInFlight(row.shotId)
            ? "复核中…" : "AI 复核这条候选（按需发起，可选）"}</button>`}
        ${row.candidateNote === null ? nothing
          : html`<p class="meta attempt-note">${row.candidateNote}</p>`}
        ${row.compareCount === 0 ? nothing : html`
          <button
            type="button"
            data-compare-action=${row.shotId}
            aria-expanded=${String(deps.isComparing(row.shotId))}
            title="对比这张图的参考图、历史候选与审核清单"
            @click=${(event: Event) => {
              deps.openCompare(row.shotId, { focus: (event as MouseEvent).detail === 0 });
            }}
          >${"比较候选（" + row.compareCount + "）"}</button>`}
        ${!row.selection ? nothing : html`
          <p
            class="meta attempt-selection"
            data-selection-state=${row.selection.state}
            data-selection-shot=${row.shotId}
          >${row.selection.text}</p>`}
        ${row.pendingNote === null ? nothing
          : html`<p class="meta attempt-note">${row.pendingNote}</p>`}
        ${row.staleNote === null ? nothing : html`<p class="meta attempt-note">${row.staleNote}</p>`}
        <div class="toolbar attempt-actions">
          ${row.actions.map((action) => actionTemplate(row.shotId, action))}
        </div>
        ${row.history.length === 0 ? nothing : html`
          <details class="attempt-history">
            <summary>${"历史 " + row.history.length + " 条状态记录（提交与核对均追加保留）"}</summary>
            ${row.history.map((line) => html`<p class="attempt-history-row">${line}</p>`)}
          </details>`}
      </div>
    `;
  }

  /** 尝试/批次区模板：状态行、provider 行、批次条与逐图行都在一个模板根下。 */
  function attemptRegionTemplate(): TemplateResult {
    const provider = imageProviderBlock();
    const providerText = provider
      ? "图像 provider：" + (provider.provider_id || "未声明") + " · " + (provider.model_id || "未声明")
        + (provider.configured === false ? " · 未配置（提交会被拒绝，不会调用模型）" : " · 已配置")
      : "图像 provider：尚未读到能力信息；提交前请确认服务端可用。";
    const batch = attemptBatch;
    return html`
      <p id="attempt-status" class="meta" role="status">${attemptStatusText}</p>
      <p id="attempt-provider" class="meta">${providerText}</p>
      <div id="attempt-batch" class="attempt-batch" ?hidden=${!batch.ready}>
        <div class="toolbar attempt-batch-actions">
          <button id="batch-stop" type="button" ?hidden=${batch.stopHidden}
            @click=${() => { generation.stopBatch(); }}>停止新增提交</button>
          <button id="batch-reconcile" type="button" ?hidden=${batch.reconcileHidden}
            ?disabled=${batch.reconcileDisabled}
            @click=${() => { void generation.reconcileOnce(); }}>${batch.reconcileLabel}</button>
          <button id="batch-retry" type="button" ?hidden=${batch.retryHidden}
            ?disabled=${batch.retryDisabled}
            @click=${() => { onBatchRetry(); }}>${batch.retryLabel}</button>
        </div>
        <p id="batch-progress" class="meta" role="status">${batch.progress}</p>
        <p id="batch-hint" class="meta" ?hidden=${batch.hints.length === 0}>${batch.hints.join(" ")}</p>
        <div id="generation-queues">
          ${batch.queues.map((queueRow) => html`
            <div class="generation-queue">
              <p class="meta">${queueRow.meta}</p>
              <p class="meta">${queueRow.statement}</p>
              <button type="button" ?disabled=${queueRow.resumeDisabled}
                @click=${() => { void generation.runBatch({ confirmation: queueRow.queue }); }}
              >按原摘要继续未提交队列</button>
              <button type="button"
                @click=${() => { modelSettings.open("image", queueRow.providerId); }}
              >给原目标补凭据</button>
            </div>`)}
        </div>
      </div>
      <div id="attempt-list">${repeat(attemptRows, (row) => row.shotId, (row) => attemptRowTemplate(row))}</div>
    `;
  }

  function renderAttemptRegion(): void {
    renderLit(attemptRegionTemplate(), elements.attemptEditor);
    hydrateAttemptPreviews();
  }

  /** 预览缩略图只请求一次；URL 到位后重绘尝试区（keyed 行不重建、不重复请求）。 */
  function hydrateAttemptPreviews(): void {
    for (const row of attemptRows) {
      const preview = row.preview;
      if (!preview || previewUrls.has(preview.key) || previewPending.has(preview.key)) continue;
      previewPending.add(preview.key);
      deps.ensurePreviewUrl(preview.shotId, preview.actionId, preview.sha256)
        .then((url) => {
          previewPending.delete(preview.key);
          if (!url) return;
          previewUrls.set(preview.key, url);
          renderAttemptRegion();
        })
        .catch(() => { previewPending.delete(preview.key); });
    }
  }

  /** 批次投影（进度/提示/原队列/三个批次按钮）与尝试行同轮渲染，不重算判据。 */
  function projectBatch(): BatchView {
    const ready = Boolean(inputs.suitePlan());
    if (!ready) return emptyBatchView();
    const state = generation.deriveBatch();
    const batchState = generation.batchStateReader();
    const running = Boolean(batchState && batchState.active);
    const progress = [batchProgressText(state)];
    if (running && batchState) {
      if (batchState.phase === "poll") {
        progress.push("批次进行中：正在按任务编号核对上游进度");
      } else {
        progress.push(batchState.currentShotId
          ? "批次进行中：正在提交「" + deps.shotLabelOf(batchState.currentShotId) + "」"
          : "批次进行中");
      }
    }
    if (batchState && batchState.halted) {
      progress.push("已停止新增提交（" + batchState.haltReason + "）；已提交的记录全部保留");
    }
    if (batchState && batchState.stopped) {
      progress.push("已停止新增提交；已提交的记录全部保留");
    }
    const hints: string[] = [];
    if (!confirmationIsCurrent()) hints.push("生成前确认缺失或已过期：先回到「生成前确认」重新确认。");
    if (state.counts.blocked_no_prompt > 0) {
      hints.push("有 " + state.counts.blocked_no_prompt + " 张还没编译 Prompt。");
    }
    if (state.review_queue.length > 0) {
      hints.push("有 " + state.review_queue.length
        + " 张没有任务编号、无法核对：系统不会自动重提，需要显式新建 action。");
    }
    if (state.fetch_queue.length > 0) {
      hints.push("有 " + state.fetch_queue.length
        + " 张已生成但候选还没保存到本地：可以点「保存候选图片」逐张保存，或点「保存候选」一次保存剩余。");
    }
    if (batchState && batchState.fetchBlocked) {
      hints.push("候选保存受阻：" + batchState.fetchBlocked);
    }
    if (batchState && batchState.fetchNotice && !batchState.fetchBlocked) {
      hints.push(batchState.fetchNotice + "候选记录保持原样，可以点「保存候选图片」重试。");
    }
    const queues: BatchQueueView[] = [];
    // 队列投影（pending/current/targetMatched）归 generation.queues() 所有；这里只渲染，不重算判据。
    for (const { queue, pending, current, targetMatched: matched } of generation.queues()) {
      if (!pending.length) continue;
      const target = queue.payload.fingerprint.snapshot.execution_target;
      if (!target) continue;
      queues.push({
        meta: "原队列 v" + queue.version + " · " + target.model_id + " · "
          + target.protocol + " · 凭据 " + target.credential_source + " · 尚未提交 " + pending.length
          + " 张（当前依据有效 " + current.length + " 张）："
          + pending.map((shotId) => deps.shotLabelOf(shotId)).join("、"),
        statement: String(queue.payload.external_summary.statement),
        resumeDisabled: running || submissionInFlight || !matched || !current.length,
        providerId: target.provider_id,
        queue,
      });
    }
    return {
      ready: true,
      progress: progress.join("；") + "。",
      hints,
      queues,
      stopHidden: !running,
      reconcileHidden: state.reconcile_queue.length === 0,
      reconcileDisabled: running || state.reconcile_queue.length === 0,
      reconcileLabel: "核对进行中（" + state.reconcile_queue.length + " 张）",
      retryHidden: state.retry_queue.length === 0,
      retryDisabled: running || state.retry_queue.length === 0,
      retryLabel: "查看失败图的重试摘要（" + state.retry_queue.length + " 张）",
    };
  }

  function renderAttempts(): void {
    const ready = Boolean(inputs.suitePlan());
    elements.attemptLocked.hidden = ready;
    elements.attemptEditor.hidden = !ready;
    const counts: AttemptCounts = { total: 0, none: 0, active: 0, succeeded: 0, failed: 0, unknown: 0 };
    if (!ready) {
      attemptRows = [];
      attemptStatusText = "";
    } else {
      const summary = suitePlanSummary(inputs.suitePlan(), inputs.suiteContext());
      attemptRows = summary ? projectAttemptRows(summary, counts) : [];
      const activeText = counts.active > 0 ? "进行中 " + counts.active + " 张；" : "";
      attemptStatusText = "共 " + counts.total + " 张；未生成 " + counts.none + " 张；"
        + activeText + "已成功 " + counts.succeeded + " 张；结果未知 " + counts.unknown + " 张；失败 "
        + counts.failed + " 张。" + (confirmationIsCurrent()
          ? "可以整套生成或逐张提交。" : "确认缺失或已过期，暂不能提交。");
    }
    attemptBatch = projectBatch();
    renderAttemptRegion();
    deps.renderCompare();
    deps.renderSelectionProgress();
    deps.refreshDerived();
  }

  /** 单张提交（按钮入口）：只负责把核心结果翻译成界面反馈，执行顺序在生成 Module。 */
  async function handleSubmitAttempt(
    shotId: string | null, options: SubmitAttemptOptions = {},
  ): Promise<SubmitAttemptResult | undefined> {
    if (!shotId) return;
    const action = options.action || beginAction();
    if (options.explicitNew) {
      generation.enterExplicitNew(shotId);
      deps.selectStage("generate");
      renderConfirm();
      confirmActionRef.value?.focus();
      return;
    }
    clearAttemptError();
    const outcome = await generation.submitAttempt(shotId, { ...options, action });
    if (!action.alive()) return outcome;
    if (outcome.skipped) {
      if (outcome.reason === "no_confirmation") {
        showAttemptError(
          "生成前确认缺失或已过期：先回到「生成前确认」重新确认，再提交。");
      } else if (outcome.reason === "blocked") {
        const blocking = outcome.blocking;
        if (blocking) {
          showAttemptError("同一张图已经有一条进行中的生成（"
            + attemptStateLabel(blocking.state) + "，action " + blocking.action_id
            + "）。先核对并按结论处理，再新建 action。");
        }
      } else if (outcome.reason === "no_prompt") {
        showAttemptError("这张图还没有可用的 Prompt 版本：先编译并保存。");
      } else if (outcome.reason === "shot_missing") {
        showAttemptError("这张图已不在套图方案里，先刷新套图规划。");
      } else if (outcome.reason === "no_references") {
        showAttemptError("这张图没有可用参考图（至少需要一张）。");
      } else if (outcome.reason === "reference_read_failed") {
        showAttemptError(outcome.message);
      } else if (outcome.reason === "environment_unknown") {
        showAttemptError(outcome.message
          || "提交前读不到有效的图像环境身份；不猜身份，先确认服务端可用。");
      }
      return outcome;
    }
    if (outcome.thrown) {
      showAttemptError(outcome.message);
      return outcome;
    }
    const record = outcome.record;
    if (!record) return outcome;
    setAttemptStatus("action " + record.action_id + "：" + attemptStateLabel(record.state)
      + (record.task_id ? "（task " + record.task_id + "）" : "") + "。");
    if (record.state === ATTEMPT_STATES.unknown) {
      showAttemptError("这次提交的结果没有确认：不要重复提交。"
        + (record.task_id ? "可以按任务编号核对。" : "没有任务编号，只能显式新建 action。"));
    } else if (record.state === ATTEMPT_STATES.failed && record.error) {
      showAttemptError("这次提交明确失败：" + record.error.message
        + "（重试策略 " + record.error.retry_policy + "）。");
    }
    if (outcome.candidate && outcome.candidate.failed) {
      showAttemptError(outcome.candidate.message);
    } else if (outcome.candidate && outcome.candidate.stored && outcome.candidate.sha256) {
      setAttemptStatus(attemptStatusText + " 候选已保存到本地（sha256 "
        + outcome.candidate.sha256.slice(0, 12) + "…）。");
    }
    return outcome;
  }

  /** 单张核对（按钮入口）：只负责把核心结果翻译成界面反馈，执行顺序在生成 Module。 */
  async function handleReconcileAttempt(
    shotId: string | null, options: ReconcileAttemptOptions = {},
  ): Promise<ReconcileAttemptResult | undefined> {
    if (!shotId) return;
    const action = options.action || beginAction();
    clearAttemptError();
    const result = await generation.reconcileAttempt(shotId, { ...options, action });
    if (!action.alive()) return result;
    if (result.skipped) {
      if (result.reason === "no_task") {
        showAttemptError("这条记录没有任务编号，无法核对；只能显式新建 action。");
      } else if (result.reason === "environment_blocked") {
        showAttemptError(result.message || "当前环境与冻结身份不一致，未发出核对请求。");
      } else if (result.reason === "no_identity") {
        showAttemptError(result.message || "这条 Attempt 没有冻结执行身份，不能按原身份核对。");
      }
      return result;
    }
    if (result.failed) {
      showAttemptError(result.message);
      return result;
    }
    if (result.advanced) {
      setAttemptStatus("已核对 task " + result.task_id + "："
        + attemptStateLabel(result.state) + "。");
      if (result.candidate && result.candidate.failed) {
        showAttemptError(result.candidate.message);
      } else if (result.candidate && result.candidate.stored && result.candidate.sha256) {
        setAttemptStatus(attemptStatusText + " 候选已保存到本地（sha256 "
          + result.candidate.sha256.slice(0, 12) + "…）。");
      }
    } else {
      setAttemptStatus("已核对 task " + result.task_id + "：没有新结论（"
        + result.note + "）。");
    }
    return result;
  }

  /** 生成/确认/尝试三区同轮刷新：全量渲染与输入侧命令收尾共用一处，避免三份写法。 */
  function render(): void {
    renderPrompts();
    renderConfirm();
    renderAttempts();
  }

  /** 项目切换/关闭的统一回收（P5）：未保存草稿、呈现基线与三区投影都按 project 精确归属，不外溢。
   *  与 compare/delivery 的 reset/dispose 同一语义；工作区 reset 链在 owner reset 之后调用。 */
  function resetViewState(): void {
    promptDrafts.clear();
    promptBaselineText.clear();
    draftOwnerProjectId = null;
    promptRows = [];
    promptReady = false;
    promptStatusText = "";
    localPreparationText = "";
    confirmView = emptyConfirmView();
    attemptRows = [];
    attemptBatch = emptyBatchView();
    attemptStatusText = "";
    submissionInFlight = false;
    displayedGenerationIntent = null;
    appliedOwnerError = "";
    // 四个错误位也按项目归属回收：清状态并在同一轮把挂载点里的模板收起（不自持旧文案）。
    promptErrorText = "";
    confirmErrorText = "";
    generateErrorText = "";
    attemptErrorText = "";
    renderPromptError();
    renderConfirmError();
    renderGenerateError();
    renderAttemptError();
    // 工作区在重开项目时撤销全部预览 object URL，视图侧缓存必须一起清，否则会留下失效地址。
    previewUrls.clear();
    previewPending.clear();
  }

  // 装配完成即把四个错误位渲染成模板（空文本＋hidden），
  // 使 #prompt-error/#confirm-error/#generate-error/#attempt-error 在任何命令之前就已存在。
  renderPromptError();
  renderConfirmError();
  renderGenerateError();
  renderAttemptError();

  return {
    renderPrompts,
    prepareSystemPrompts,
    handleCompilePrompt,
    handleSaveEditedPrompt,
    handleReconfirmManualPrompt,
    handleDiscardManualPrompt,
    promptRecordOf,
    currentImageProfile,
    promptCurrentBasis,
    renderConfirm,
    handleConfirmGeneration,
    confirmationIsCurrent,
    confirmationIsCurrentForShot,
    queueShotIsCurrent,
    isSubmitting: () => submissionInFlight,
    render,
    renderAttempts,
    applyNotice,
    showAttemptError,
    shortTime,
    resetViewState,
  };
}
