/**
 * 审核视图（设计 §10.1 的第三个视图）：「审核」阶段的逐图审核列表、候选比较面板、
 * 单图返工闭环与人工采用。
 *
 * 边界（设计 §10.1）：这里只持比较/返工/采用三区的就地 UI 状态（当前查看的图与候选、
 * 跨项目记忆、按候选归属的返工草稿、在飞标识），不写库、不发网络、不重算业务判定。
 * 候选链与尝试链的唯一所有者是 generation，采用记录与单图报告的唯一所有者是
 * selectionAdoption；返工意图的编译/落版/确认收归 generation（它向 prompts 借窄能力）。
 * 落库/派生/跨区渲染都经 deps 回到工作区。比较排序与默认目标由 domain/compare.js 决定，这里只投影。
 *
 * P5（#10 前端渲染迁移）：本视图**全部**内容都是 lit-html 声明式模板 —— 审核卡列表、比较面板
 * （表头动作、两张大图、候选页签、审核清单、参考图、状态行）、返工面板（问题勾选、方向、
 * 预览、状态与错误）与放大对话框，都按业务身份 keyed 由状态投影。index.html 只留空壳挂载点
 * （<section>/<div>/<dialog>，共四个：比较面板、返工面板、放大对话框、审核列表挂载点）；命令式写入只剩外壳根的
 * hidden 与合同/图号元数据；没有重绘前
 * querySelector 抓取/恢复，没有每次渲染重复挂监听，也没有散落的 hidden/innerHTML 写法。
 * 草稿是唯一 UI 状态，按 project/shot/candidate 精确归属，切换候选不会把一条候选的编辑状态带到另一条。
 *
 * TypeScript 迁移（计划 §9 V2.R7.5）：本文件是唯一手工维护实现；浏览器产物由 Vite 生成。
 */
import { html, nothing, render as renderLit } from "lit-html";
import { repeat } from "lit-html/directives/repeat.js";
import { live } from "lit-html/directives/live.js";
import { ifDefined } from "lit-html/directives/if-defined.js";
import {
  ATTEMPT_STATES,
  COMPARE_CONTRACT_VERSION,
  COMPARE_SEVERITY_TEXT,
  COMPARE_STATE_TEXT,
  REWORK_CONTRACT_VERSION,
  REWORK_PROBLEMS,
  attemptStateLabel,
  compareCounts,
  compareRowHeadline,
  compareRows,
  defaultCompareTargetId,
  nextPendingShotId,
  reviewChecklist,
  reviewIsCurrent,
  reviewSummaryText,
  selectionSetText,
  sortFindings,
  suggestReworkProblems,
  suggestedReworkDirection,
  suitePlanSummary,
} from "../domain/index.js";
import {
  COMPARE_STATE_BADGE,
  ROLE_TEXT,
  SEVERITY_BADGE,
  errorMessageOf,
} from "./dom.js";
import type { ActionSnapshot } from "../session.js";
import type { InputsModule } from "../project-inputs.js";
import type {
  AttemptRecord,
  CompareRow,
  PlanShot,
  ReviewFinding,
  ReviewReport,
  SelectionState,
  SuitePlanSummary,
} from "../domain/type-contracts.js";
import type {
  AdoptionSource,
  SelectionAdoptionModule,
  SelectionEntry,
} from "../selection-adoption.js";
import type {
  GenerationModule,
  ReworkIntent,
} from "../generation.js";

/**
 * 本视图负责的 DOM 句柄：只剩四个**空壳挂载点**。面板/对话框/审核列表里的内容
 * —— 表头按钮、选择器、两张大图、状态行、返工区、放大对话框内容、逐图审核卡、
 * 采用进度与就地反馈 —— 全部由本文件的 lit 模板渲染，工作区不再逐个传 id 句柄。
 */
export type CompareElements = {
  /** 比较面板根（index 空壳）：只写 hidden 与合同/图号元数据，内容全归模板。 */
  comparePanel: HTMLElement;
  /** 返工面板根（index 空壳）：同上。 */
  reworkPanel: HTMLElement;
  /** 放大对话框根（index 空壳）：内容归模板；showModal/close 与 cancel 属对话框外壳生命周期。 */
  imageZoomDialog: HTMLDialogElement;
  /** 审核阶段逐图列表挂载点（index 空壳 `#review-list-mount`）：卡片、空占位与采用反馈全归模板。 */
  reviewList: HTMLElement;
};

/**
 * 窄依赖：审核面唯一所有者的命令/投影 + 工作区级收尾与跨区只读回调。
 * 不注入整个工作区；需要工作区状态的都经只读回调读取。
 * 候选预览 URL 缓存归工作区（比较/返工/尝试共用一份 object URL，关闭项目统一撤销）。
 */
export type CompareViewDeps = {
  inputs: InputsModule;
  generation: GenerationModule;
  selectionAdoption: SelectionAdoptionModule;
  beginAction(): ActionSnapshot;
  currentProjectId(): string | null;
  /** 图号 → 人类可读标签（套图方案投影）；工作区唯一实现。 */
  shotLabelOf(shotId: string): string;
  /** 时间戳短格式：唯一实现在生成视图。 */
  shortTime(iso: unknown): string;
  ensurePreviewUrl(shotId: string, actionId: string, assetSha256: string): Promise<string | null>;
  /** 阶段切换（打开比较即停靠审核阶段）；外壳归工作区。 */
  selectStage(stageId: string): void;
  /** 收起后把焦点还给用户看得见的审阅入口（跨阶段 DOM 归工作区）。 */
  focusReviewEntry(shotId: string | null): void;
  /** 采用/返工提交后的尝试链刷新（生成视图）。 */
  renderAttempts(): void;
  /** 生成阶段错误位写入（唯一所有者在生成视图：同时写 #generateError/#attemptError；比较区不自持第二份错误 DOM）。 */
  showAttemptError(message: string): void;
  /** 返工提交成功后把 Prompt 列表与确认单切到最新（生成视图）。 */
  renderPrompts(): void;
  renderConfirm(): void;
  /** 参考图来源链的存在性核对（存储读归工作区）。 */
  readAsset(projectId: string, sha256: string): Promise<unknown>;
  /** 返工提交成功后的项目状态派生（工作区）。 */
  deriveState(): Promise<void>;
  /** 工作区级错误上报（比较区异步收尾用）。 */
  reportError(error: unknown): void;
  /** 有后缀的抛出信息；与生成区共用工作区同一实现。 */
  suffixedErrorMessage(error: unknown, fallback: string, suffix: string): string;
};

export type CompareView = {
  /**
   * 外壳根的监听装配（幂等）：工作区装配期调用一次，只挂面板根/对话框根上的
   * keydown-cancel 等外壳行为；面板内部的按钮、选择器、文本框一律由模板 @event 持有。
   */
  bind(): void;
  /** 审核阶段的逐图入口（工作区 refreshDerived 的一环）。 */
  renderReviewList(): void;
  /** 比较面板同轮刷新（生成区收尾经此回调）。 */
  renderCompare(): void;
  /** 采用进度行（生成区收尾经此回调）。 */
  renderSelectionProgress(): void;
  /** 比较区入口（生成区尝试行与审核卡共用）。 */
  openCompare(shotId: string, options?: { candidateId?: string | null; focus?: boolean }): void;
  closeCompare(): void;
  isComparing(shotId: string): boolean;
  handleCompareKeydown(event: KeyboardEvent): void;
  handleBaselineChange(value: string | null): void;
  handleCompareReview(): Promise<void>;
  zoomViewed(): void;
  zoomBaseline(): void;
  closeImageZoom(): void;
  toggleZoomNative(): void;
  openReworkPanel(options?: { shotId?: string | null; candidateId?: string | null }): void;
  previewRework(): Promise<void>;
  editRework(): Promise<void>;
  submitRework(): Promise<void>;
  resetRework(): void;
  cancelRework(): void;
  handleReworkKeydown(event: KeyboardEvent): void;
  handleReworkDirectionInput(value: string): void;
  /** 人工采用/取消采用：默认对当前正看着的候选操作（与旧签名一致）。 */
  adoptCandidate(kind: "select" | "clear", shotId?: string | null, candidateId?: string | null): Promise<void>;
  /** 采用记录只读投影（阶段外壳与交付视图经同一入口读）。 */
  selectionEntryOf(shotId: string | null): SelectionEntry | null;
  selectionStateOf(shotId: string): SelectionState;
  adoptedMarkOf(shotId: string | null): { candidate_id: string | null; state: SelectionState } | null;
  adoptSourceOf(shotId: string | null, candidateId: string | null): AdoptionSource | null;
  selectionTextOf(shotId: string): string;
  /** 重开项目时的就地状态归零：与原 loadWorkspace 重置项一一对应。 */
  resetViewState(): void;
};

/** 返工草稿（按候选内存态；意图只在显式预览后产生，视图原样持有并交回，不重算）。 */
export type CompareReworkDraft = {
  problems: string[];
  direction: string;
  intent?: ReworkIntent | null;
};

/** 套图方案摘要里的单图形状（视图只读 shot_id/label/required，不重算方案）。 */
type SuiteShotSummary = SuitePlanSummary["shots"][number];

/* ---------------------------------------------------------------- UI 状态形状 */

/** 参考图条目：sha256/角色/可用 URL 都来自原任务动作观察，不猜、不替代。 */
type ReferenceEntryView = {
  sha256: string;
  role: string;
  missing: boolean;
  url: string | null;
};

/** 审核卡上的检查摘要（报告/补建失败/未检查三态如实区分）。 */
type ReviewCheckView = {
  reviewState: string;
  candidateId: string;
  badgeClass: string;
  stateLabel: string;
  summary: string | null;
  ai: { status: string; text: string } | null;
  reportFailure: string | null;
  headline: string | null;
  hint: string | null;
};

/** 逐图审核卡投影：所有字段都来自 owner 只读投影，模板不重算。 */
type ReviewCardView = {
  shotId: string;
  label: string;
  state: SelectionState;
  chainCount: number;
  badgeClass: string;
  badgeText: string;
  adoptedCandidateId: string;
  storedCandidateId: string | null;
  previewUrl: string | null;
  message: string | null;
  check: ReviewCheckView | null;
  displayedIsAdopted: boolean;
  stored: boolean;
  canRework: boolean;
  canAdopt: boolean;
  adoptTitle: string | null;
};

/** 比较区就地投影：面板模板与审核卡共用的唯一来源（视图不重算业务判定）。 */
type CompareUiState = {
  shotId: string | null;
  shot: PlanShot | null;
  candidateId: string | null;
  baselineId: string | null;
  subject: string;
  status: string;
  jumpTarget: string | null;
  rows: CompareRow[];
  references: ReferenceEntryView[];
  basisTitle: string;
  viewedCaption: string;
  viewedUrl: string | null;
  baselineUrl: string | null;
  reviewEnabled: boolean;
  adoptSelectEnabled: boolean;
  adoptClearEnabled: boolean;
  reworkEntry: { shotId: string; candidateId: string; sha256: string } | null;
  /** 放大对话框内容（模板投影；showModal/close 才是对话框外壳生命周期）。 */
  zoomSrc: string | null;
  zoomLabel: string;
  zoomNative: boolean;
  /** 审核区就地反馈（采用进度、采用结果行、就地错误）：全部由模板投影，不再直接写节点。 */
  adoptProgress: string;
  adoptStatus: string;
  adoptError: string;
};

/** 返工区就地投影：draftKey 精确到 project/shot/candidate，草稿不跨候选复用。 */
type ReworkUiState = {
  shotId: string | null;
  candidateId: string | null;
  assetSha256: string | null;
  version: number | null;
  draftKey: string | null;
  draft: CompareReworkDraft | null;
  basis: string;
  tech: string;
  inFlight: boolean;
  status: string;
  /** 就地错误文案（归模板投影，不再由 showError 直接写节点）。 */
  error: string;
};

/** 预览 URL 的视图侧缓存：工作区已有同一份缓存，这里只避免同一代渲染重复重建节点。 */
type UrlCache = Map<string, string>;

function cacheKeyOf(row: CompareRow): string {
  return row.candidate_id + "@" + row.asset_sha256;
}

function urlOf(cache: UrlCache, row: CompareRow | null): string | null {
  if (!row) return null;
  return cache.get(cacheKeyOf(row)) || null;
}

/**
 * 放大对话框的默认标题（与 index 里原来写死的文案一致；打开时被所看图的图注替换）。
 * 对话框内容归模板，标题只是同一份 UI 状态的投影。
 */
const ZOOM_DEFAULT_TITLE = "原比例查看";

/**
 * 审核视图工厂。
 * @param args.elements 本视图负责的 DOM 句柄
 * @param args.deps 窄依赖：业务命令/投影 + 装配期注入的投影回调
 */
export function createCompareView(
  { elements, deps }: { elements: CompareElements; deps: CompareViewDeps },
): CompareView {
  const { inputs, generation, selectionAdoption } = deps;

  // 比较区就地状态：当前打开的图与候选、异步图片请求的代次、跨项目记忆、放大关闭后恢复焦点。
  let compareToken = 0;
  let compareImageToken = 0;
  const compareViews = new Map<string, { candidateId: string | null; baselineId: string | null }>();
  let imageZoomReturnFocus: HTMLElement | null = null;

  // 返工草稿按 project/shot/candidate 归属：切换候选不会把 A 的编辑带到 B。
  let reworkDrafts = new Map<string, CompareReworkDraft>();

  const compareImageUrls: UrlCache = new Map();
  const candidatePreviewUrls: UrlCache = new Map();
  const reviewPreviewUrls: UrlCache = new Map();
  const candidatePreviewPending = new Set<string>();
  const reviewPreviewPending = new Set<string>();

  let bound = false;

  const state: CompareUiState = {
    shotId: null,
    shot: null,
    candidateId: null,
    baselineId: null,
    subject: "",
    status: "",
    jumpTarget: null,
    rows: [],
    references: [],
    basisTitle: "",
    viewedCaption: "",
    viewedUrl: null,
    baselineUrl: null,
    reviewEnabled: false,
    adoptSelectEnabled: false,
    adoptClearEnabled: false,
    reworkEntry: null,
    zoomSrc: null,
    zoomLabel: ZOOM_DEFAULT_TITLE,
    zoomNative: false,
    adoptProgress: "",
    adoptStatus: "",
    adoptError: "",
  };

  const rework: ReworkUiState = {
    shotId: null,
    candidateId: null,
    assetSha256: null,
    version: null,
    draftKey: null,
    draft: null,
    basis: "",
    tech: "",
    inFlight: false,
    status: "",
    error: "",
  };

  /** 套图摘要快照：审核列表与阶段无关的本地投影入口，不重算方案。 */
  function shotSummaries(): SuiteShotSummary[] {
    const plan = inputs.suitePlan();
    return plan ? suitePlanSummary(plan, inputs.suiteContext()).shots : [];
  }

  /**
   * 面板只是投影：候选、报告、参考图全部来自 IndexedDB 已经存在的事实，
   * 排序与默认目标由 domain/compare.js 决定（唯一权威），这里不重算报告、不写任何记录。
   */
  function attemptsByActionId(): Record<string, AttemptRecord> {
    const map: Record<string, AttemptRecord> = {};
    for (const record of generation.allAttemptRecords()) {
      if (record && typeof record.action_id === "string") map[record.action_id] = record;
    }
    return map;
  }

  /** 每张图的候选行（异常优先）+ 计划顺序；报告只在 reviewIsCurrent 为真时参与。 */
  function compareInventory(): {
    shots: SuiteShotSummary[]; rowsByShotId: Record<string, CompareRow[]>;
  } {
    const shots = shotSummaries();
    const rowsByShotId: Record<string, CompareRow[]> = {};
    const attempts = attemptsByActionId();
    for (const item of shots) {
      const chain = generation.candidateChainOf(item.shot_id);
      const reports: Record<string, ReviewReport> = {};
      for (const entry of chain) {
        const candidate = entry.record;
        if (!candidate || typeof candidate.candidate_id !== "string") continue;
        const existing = selectionAdoption.reportOf(candidate.candidate_id);
        if (existing && reviewIsCurrent(existing.report, candidate)) {
          reports[candidate.candidate_id] = existing.report;
        }
      }
      rowsByShotId[item.shot_id] = compareRows({
        candidates: chain, reportsByCandidateId: reports, attemptsByActionId: attempts,
      });
    }
    return { shots, rowsByShotId };
  }

  function compareTabId(candidateId: string): string {
    return "compare-tab-" + String(candidateId).replace(/[^A-Za-z0-9_-]/g, "-");
  }

  function compareStateLabel(row: CompareRow): string {
    return COMPARE_STATE_TEXT[row.review_state] || row.review_state;
  }

  /* ------------------------------------------------------------- 模板片段 */

  /** 单条发现行（比较清单与完整报告共用同一形状）。 */
  function compareFindingRow(finding: ReviewFinding) {
    const measured = finding.measured !== null && finding.measured !== undefined
      ? html`<p class="meta">实测：${JSON.stringify(finding.measured).slice(0, 160)}</p>`
      : nothing;
    return html`
      <li class="compare-finding" data-severity=${finding.severity} data-rule-id=${finding.rule_id}>
        <div class="compare-card-head">
          <span class="badge ${SEVERITY_BADGE[finding.severity] || "is-review-unknown"}">${COMPARE_SEVERITY_TEXT[finding.severity] || finding.severity}</span>
          <span class="name">${finding.title}</span>
          <span class="meta">${finding.rule_id + " · v" + finding.rule_version}</span>
        </div>
        <p class="meta">${finding.detail}</p>
        ${measured}
      </li>
    `;
  }

  /** 候选页签：tablist 的直接子节点必须是 tab；点击只换查看目标，不写存储。 */
  function candidateCardTemplate(row: CompareRow, selectedCandidateId: string | null) {
    const selected = row.candidate_id === selectedCandidateId;
    const adopted = state.shotId ? adoptedMarkOf(state.shotId) : null;
    const isAdopted = Boolean(adopted && adopted.candidate_id === row.candidate_id);
    const business: string[] = [];
    if (row.width && row.height) business.push(row.width + "×" + row.height);
    if (row.created_at) business.push(deps.shortTime(row.created_at));
    const url = urlOf(candidatePreviewUrls, row);
    return html`
      <button
        type="button"
        role="tab"
        id=${compareTabId(row.candidate_id)}
        class="compare-card"
        aria-selected=${selected ? "true" : "false"}
        aria-controls="compare-checklist"
        data-candidate-id=${row.candidate_id}
        data-review-state=${row.review_state}
        tabindex=${selected ? "0" : "-1"}
        @click=${() => selectCompareCandidate(row.candidate_id)}
      >
        ${url
          ? html`<img src=${url} alt=${"候选 v" + (row.version || "?") + " 预览"} loading="lazy">`
          : html`<img alt=${"候选 v" + (row.version || "?") + " 预览"} loading="lazy">`}
        <div class="compare-card-main">
          <div class="compare-card-head">
            <span class="name">${"候选 v" + (row.version === null ? "?" : row.version)}</span>
            <span class="badge ${COMPARE_STATE_BADGE[row.review_state] || "is-review-unchecked"}">${compareStateLabel(row)}</span>
            ${isAdopted && adopted
              ? html`<span class="badge is-adopted" data-adopted=${adopted.state}>${adopted.state === "current" ? "已采用" : "已采用（已过期）"}</span>`
              : nothing}
          </div>
          <span class="meta">${business.join(" · ")}</span>
          <p class="compare-headline">${compareRowHeadline(row)}</p>
        </div>
      </button>
    `;
  }

  /** 审核清单 = 当前候选的待处理发现（异常优先）+ 这张图的验收依据 + 按需展开的完整报告。 */
  function checklistTemplate() {
    const row = state.rows.find((item) => item.candidate_id === state.candidateId) || null;
    if (!row) return html`<p class="meta">先选择一个候选。</p>`;
    const report = row.report;
    return html`
      ${report ? checklistReportTemplate(row, report) : html`<p class="meta">${compareRowHeadline(row)}</p>`}
      ${checklistBasisTemplate(row)}
    `;
  }

  function checklistReportTemplate(row: CompareRow, report: ReviewReport) {
    const findings = sortFindings(report.findings);
    const actionable = findings.filter((item) => item.severity !== "PASS");
    const vlm = report.vlm;
    const vlmText = vlm
      ? (vlm.outcome === "checked" ? "已完成" : "未完成（结果未知，不阻断人工审核）")
      : "未复核（未运行，未发起 AI 复核；不阻断人工采用）";
    return html`
      ${actionable.length
        ? html`
            <h5>${"先看这些（" + actionable.length + "）"}</h5>
            <ul class="compare-findings">${repeat(actionable, (finding, index) => finding.rule_id + "|" + index, (finding) => compareFindingRow(finding))}</ul>
          `
        : html`<p class="meta">${compareRowHeadline(row)}</p>`}
      <details class="compare-report">
        <summary>${"完整报告（合同 " + report.review_contract_version + " · " + findings.length + " 条）"}</summary>
        <p class="compare-report-row">${"候选 sha256 " + String(row.asset_sha256).slice(0, 16) + "… · 报告生成 " + deps.shortTime(report.created_at)}</p>
        <p class="compare-report-row" data-compare-vlm=${vlm ? vlm.outcome : "not_run"}>${"视觉复核（按需发起）：" + vlmText + (vlm && vlm.model_id ? " · " + vlm.model_id : "")}</p>
        <ul class="compare-findings">${repeat(findings, (finding, index) => finding.rule_id + "|" + index, (finding) => compareFindingRow(finding))}</ul>
      </details>
    `;
  }

  /** 验收依据收进披露区：清单主区保持短，展开可见同一份字段（不删信息、不改判定）。 */
  function checklistBasisTemplate(row: CompareRow) {
    const shot = state.shot;
    if (!shot) return nothing;
    const specEntry = inputs.shotSpecEntry(shot.shot_id);
    const checklist = reviewChecklist(shot, {
      shotSpec: specEntry ? specEntry.spec : null, styleSpec: inputs.styleSpec(),
    });
    const techLines: string[] = [
      "candidate " + String(row.candidate_id),
      "sha256 " + String(row.asset_sha256).slice(0, 12) + "…",
    ];
    if (row.task_id) techLines.push("task " + String(row.task_id).slice(0, 8));
    else if (row.attempt_action_id) techLines.push("action " + String(row.attempt_action_id).slice(0, 8));
    return html`
      <details class="compare-basis">
        <summary>这张图的验收依据</summary>
        <ul class="compare-basis-list">
          <li>${"目的：" + checklist.purpose}</li>
          ${checklist.must_keep.length ? html`<li>${"必须保持：" + checklist.must_keep.join("；")}</li>` : nothing}
          ${checklist.may_change.length ? html`<li>${"允许变化：" + checklist.may_change.join("；")}</li>` : nothing}
          ${checklist.style_lines.length ? html`<li>${"公共风格：" + checklist.style_lines.join("；")}</li>` : nothing}
          ${checklist.saved ? nothing : html`<li class="meta">单图规格尚未保存，这里用的是默认派生值。</li>`}
        </ul>
      </details>
      <details class="tech-details">
        <summary>技术详情</summary>
        <p class="meta tech-body">${techLines.join(" · ")}</p>
      </details>
    `;
  }

  function referencesTemplate() {
    return repeat(state.references, (entry) => entry.sha256 + "|" + entry.role, (entry) => html`
      <li data-reference-sha256=${entry.sha256}>
        ${entry.url
          ? html`
              <img src=${entry.url} alt=${"参考图 " + entry.role} loading="lazy">
              <button type="button" @click=${() => openImageZoom(entry.url || "", "参考原图 · " + (ROLE_TEXT[entry.role] || entry.role))}>放大参考原图</button>
            `
          : html`<span class="meta">资产缺失</span>`}
        <span class="meta">${ROLE_TEXT[entry.role] || entry.role}</span>
        <details class="tech-details">
          <summary>技术详情</summary>
          <p class="meta tech-body">${"sha256 " + String(entry.sha256).slice(0, 8) + "…"}</p>
        </details>
      </li>
    `);
  }

  function baselineOptionsTemplate() {
    return html`
      <option value="">不指定对照</option>
      ${repeat(state.rows.filter((row) => row.candidate_id !== state.candidateId),
        (row) => row.candidate_id,
        (row) => {
          const adopted = state.shotId ? adoptedMarkOf(state.shotId) : null;
          const suffix = adopted && adopted.candidate_id === row.candidate_id ? " · 已采用" : "";
          return html`<option value=${row.candidate_id}>${"候选 v" + row.version + suffix}</option>`;
        })}
    `;
  }

  /** 返工问题勾选：模板拥有实际勾选态（live 强制按草稿投影，重填后不留 DOM 残影）。 */
  function reworkProblemsTemplate() {
    const draft = rework.draft;
    if (!rework.shotId || !draft) return nothing;
    return repeat(REWORK_PROBLEMS, (problem) => problem.id, (problem) => html`
      <label class="check rework-problem" title=${problem.hint} data-problem-id=${problem.id}>
        <input
          id=${"rework-problem-" + problem.id}
          type="checkbox"
          value=${problem.id}
          .checked=${live(draft.problems.indexOf(problem.id) >= 0)}
          @change=${(event: Event) => toggleReworkProblem(problem.id, Boolean((event.target as HTMLInputElement).checked))}
        >
        ${" " + problem.label}
      </label>
    `);
  }

  /**
   * 比较面板整块内容：index 只留 <section> 空壳，这里的模板按状态投影全部子节点
   * （结构不变时就地 patch ⇒ 焦点、details 展开态、半截输入都不会被重画抹掉）。
   */
  function comparePanelTemplate() {
    const viewed = state.rows.find((row) => row.candidate_id === state.candidateId) || null;
    const comparison = state.baselineId
      ? (state.rows.find((row) => row.candidate_id === state.baselineId) || null)
      : null;
    const entry = state.reworkEntry;
    return html`
      <div class="compare-head">
        <h4 id="compare-title">候选比较与审核清单</h4>
        <span id="compare-subject" class="meta">${state.subject}</span>
        <span class="compare-head-actions">
          <button id="adopt-open" class="primary" type="button" ?disabled=${!state.adoptSelectEnabled}
            @click=${() => { void adoptCandidate("select"); }}>采用当前候选</button>
          <button id="adopt-clear" type="button" ?disabled=${!state.adoptClearEnabled}
            @click=${() => { void adoptCandidate("clear"); }}>取消这张图的采用</button>
          <button id="rework-open" type="button" ?disabled=${!entry}
            data-shot-id=${entry ? entry.shotId : ""} data-candidate-id=${entry ? entry.candidateId : ""} data-candidate-sha256=${entry ? entry.sha256 : ""}
            @click=${() => { if (entry) openReworkPanel({ shotId: entry.shotId, candidateId: entry.candidateId }); }}>返工当前候选</button>
          <button id="compare-review" type="button" ?disabled=${!state.reviewEnabled}
            title="只在你点这一下时才调用 AI 复核；查看、切换、采用都不会触发。未复核不阻断人工采用。"
            @click=${() => { void handleCompareReview(); }}>AI 复核当前查看候选（按需发起，可选）</button>
          <button id="compare-jump" type="button" ?disabled=${!state.jumpTarget}
            data-target-shot=${state.jumpTarget || ""}
            @click=${() => { jumpToNextPending(); }}>下一个待处理</button>
          <button id="compare-close" type="button" @click=${() => { closeCompare(); }}>收起</button>
        </span>
      </div>
      <p class="meta" id="compare-basis-title">${state.basisTitle}</p>
      <div class="compare-image-grid">
        <figure>
          <figcaption>原任务参考图</figcaption>
          <ul id="compare-references" class="compare-references">${referencesTemplate()}</ul>
        </figure>
        <figure>
          <figcaption>
            <label for="compare-baseline-select">对照候选</label>
            <select id="compare-baseline-select" .value=${live(state.baselineId || "")}
              @change=${(event: Event) => { handleBaselineChange((event.target as HTMLSelectElement).value); }}>${baselineOptionsTemplate()}</select>
          <img id="compare-baseline-image" alt="所指定的对照候选" ?hidden=${!state.baselineUrl}
            src=${ifDefined(state.baselineUrl ?? undefined)}
            data-candidate-id=${ifDefined(comparison ? comparison.candidate_id : undefined)}>
          <button id="compare-baseline-zoom" type="button" ?disabled=${!state.baselineUrl}
            @click=${() => { zoomBaseline(); }}>放大对照候选</button>
        </figure>
        <figure>
          <figcaption id="compare-viewed-caption">${state.viewedCaption}</figcaption>
          <img id="compare-viewed-image" alt="当前查看候选" ?hidden=${!state.viewedUrl}
            src=${ifDefined(state.viewedUrl ?? undefined)}
            data-candidate-id=${ifDefined(viewed ? viewed.candidate_id : undefined)}>
          <button id="compare-viewed-zoom" type="button" ?disabled=${!state.viewedUrl}
            @click=${() => { zoomViewed(); }}>放大当前候选</button>
        </figure>
      </div>
      <div class="compare-body">
        <div class="compare-column">
          <p class="meta">候选（异常优先，同档新到旧）</p>
          <div id="compare-candidates" class="compare-candidates" role="tablist" aria-label="候选"
            @keydown=${(event: KeyboardEvent) => { handleCompareKeydown(event); }}>
            ${repeat(state.rows, (row) => row.candidate_id,
              (row) => candidateCardTemplate(row, state.candidateId))}
          </div>
        </div>
        <div class="compare-column">
          <div id="compare-checklist" role="tabpanel" tabindex="0" aria-label="审核清单"
            aria-labelledby=${state.candidateId ? compareTabId(state.candidateId) : "compare-title"}
            data-candidate-id=${ifDefined(viewed ? viewed.candidate_id : undefined)}
            data-compare-state=${ifDefined(viewed ? viewed.review_state : undefined)}>
            ${checklistTemplate()}
          </div>
        </div>
      </div>
      <p id="compare-status" class="meta" role="status">${state.status}</p>
    `;
  }

  /** 预览就绪时的一行元信息（与旧投影逐字一致：参考图张数 + 全文长度）。 */
  function reworkPreviewMetaOf(intent: ReworkIntent): string {
    return "将保存为 Prompt 新版本（旧版本保留）并只重新生成这张图 · 参考图 "
      + intent.preview.references + " 张 · 全文 " + intent.preview.text.length + " 字";
  }

  /**
   * 返工面板整块内容：草稿（问题/方向/意图）是唯一状态，勾选、方向、预览、状态与错误都按它投影。
   * 外墙 <section> 的 hidden 属外壳生命周期（见 projectRoots），这里只投影内部。
   */
  function reworkPanelTemplate() {
    const draft = rework.draft;
    const intent = draft && draft.intent ? draft.intent : null;
    const hasReason = Boolean(draft && (draft.problems.length > 0
      || String(draft.direction || "").trim().length > 0));
    return html`
      <div class="rework-head">
        <h4 id="rework-title">按问题返工这张图</h4>
        <span id="rework-basis" class="meta">${rework.basis}</span>
        <span class="rework-head-actions">
          <button id="rework-reset" type="button" class="link-button" ?disabled=${rework.inFlight}
            @click=${() => { resetRework(); }}>按建议重填</button>
          <button id="rework-cancel" type="button" ?disabled=${rework.inFlight}
            @click=${() => { cancelRework(); }}>取消</button>
        </span>
      </div>
      <details id="rework-tech" class="tech-details" ?hidden=${!rework.tech}>
        <summary>技术详情</summary>
        <p id="rework-tech-body" class="meta">${rework.tech}</p>
      </details>
      <fieldset id="rework-problems" class="rework-problems">
        <legend class="meta">问题分类（可多选；至少要选一类或写一句方向）</legend>
        <div class="rework-problem-options">${reworkProblemsTemplate()}</div>
      </fieldset>
      <div class="field">
        <label for="rework-direction">改进方向（可改写）</label>
        <textarea id="rework-direction" rows="2" maxlength="300" .value=${live(draft ? draft.direction : "")}
          @input=${(event: Event) => { handleReworkDirectionInput((event.target as HTMLTextAreaElement).value); }}></textarea>
      <div class="toolbar">
        <button id="rework-preview" type="button" ?disabled=${rework.inFlight || !hasReason}
          @click=${() => { void previewRework(); }}>预览返工 Prompt</button>
        <button id="rework-edit" type="button" disabled
          @click=${() => { void editRework(); }}>查看/编辑完整 Prompt</button>
        <button id="rework-submit" type="button" class="primary" ?disabled=${rework.inFlight || !intent}
          @click=${() => { void submitRework(); }}>确认并生成这张图</button>
      </div>
      <div id="rework-preview-box" class="rework-preview" ?hidden=${!intent}>
        <p id="rework-preview-meta" class="meta">${intent ? reworkPreviewMetaOf(intent) : ""}</p>
        <pre id="rework-preview-text" class="prompt-text">${intent ? intent.preview.text : ""}</pre>
      </div>
      <p id="rework-summary" class="meta">${rework.shotId ? reworkSummaryOf(draft) : ""}</p>
      <p id="rework-status" class="status" role="status" ?hidden=${rework.status.length === 0}>${rework.status}</p>
      <p id="rework-error" class="error" role="alert" ?hidden=${rework.error.length === 0}>${rework.error}</p>
    `;
  }

  /** 放大对话框内容：图源、图注与「100% 像素」都在状态里，showModal/close 才是外壳生命周期。 */
  function imageZoomTemplate() {
    return html`
      <div class="toolbar">
        <h2 id="image-zoom-title">${state.zoomLabel}</h2>
        <button id="image-zoom-native" type="button" @click=${() => { toggleZoomNative(); }}>
          ${state.zoomNative ? "适应窗口" : "100% 像素"}</button>
        <button id="image-zoom-close" type="button" @click=${() => { closeImageZoom(); }}>关闭</button>
      </div>
      <div class="image-zoom-scroll">
        <img id="image-zoom-content" alt=${state.zoomLabel}
          class=${state.zoomNative ? "at-native-size" : ""}
          src=${ifDefined(state.zoomSrc ?? undefined)}>
      </div>
    `;
  }

  /* --------------------------------------------------------------- 模板渲染 */

  /**
   * 三块内容各自一次 renderLit：结构不变时就地 patch ⇒ 节点身份稳定（焦点、滚动位置、
   * details 展开态与半截输入都不会被重画抹掉）。拆开是为了让方向输入只重画返工区。
   */
  function renderComparePanel(): void {
    renderLit(comparePanelTemplate(), elements.comparePanel);
    projectRoots();
  }

  function renderReworkPanel(): void {
    renderLit(reworkPanelTemplate(), elements.reworkPanel);
    projectRoots();
  }

  function renderImageZoom(): void {
    renderLit(imageZoomTemplate(), elements.imageZoomDialog);
  }

  function renderComparePanels(): void {
    renderComparePanel();
    renderReworkPanel();
    renderImageZoom();
  }

  /**
   * 本视图唯一的命令式写入口：<section>/<dialog> 外壳根不属于模板内容，这里只写它们的
   * 生命周期 hidden 与合同/图号元数据（面板内部一切一律由模板投影）。
   */
  function projectRoots(): void {
    const panel = elements.comparePanel;
    const open = state.shotId !== null && state.rows.length > 0;
    panel.hidden = !open;
    if (open && state.shotId) {
      panel.dataset.compareContract = COMPARE_CONTRACT_VERSION;
      panel.dataset.shotId = state.shotId;
    } else {
      delete panel.dataset.compareContract;
      delete panel.dataset.shotId;
    }
    const reworkOpen = rework.shotId !== null;
    elements.reworkPanel.hidden = !reworkOpen;
    if (reworkOpen && rework.shotId) {
      elements.reworkPanel.dataset.reworkContract = REWORK_CONTRACT_VERSION;
      elements.reworkPanel.dataset.shotId = rework.shotId;
      elements.reworkPanel.dataset.candidateId = rework.candidateId || "";
    } else {
      delete elements.reworkPanel.dataset.reworkContract;
      delete elements.reworkPanel.dataset.shotId;
      delete elements.reworkPanel.dataset.candidateId;
    }
  }

  /** 模板内静态控件不再按需 querySelector：输入值由模板事件参数传入草稿。 */

  /** 返工区就地报错：文案进屋 UI 状态随模板投影，重画不会把它抹掉。 */
  function setReworkError(message: string): void {
    rework.error = message;
    renderReworkPanel();
  }

  /* ----------------------------------------------------------- 投影与渲染 */

  function clearCompareState(): void {
    state.shotId = null;
    state.shot = null;
    state.candidateId = null;
    state.baselineId = null;
    state.subject = "";
    state.jumpTarget = null;
    state.rows = [];
    state.references = [];
    state.basisTitle = "";
    state.viewedCaption = "";
    state.viewedUrl = null;
    state.baselineUrl = null;
    state.reviewEnabled = false;
    state.adoptSelectEnabled = false;
    state.adoptClearEnabled = false;
    state.reworkEntry = null;
    closeReworkPanel({ focusCandidate: false });
  }

  /** 从 owner 只读投影重算比较区状态；不读写记录、不改判定。 */
  function projectCompare(): void {
    const plan = inputs.suitePlan();
    if (!plan || !state.shotId) {
      clearCompareState();
      return;
    }
    const shot = (plan.shots || []).find((item) => item && item.shot_id === state.shotId) || null;
    if (!shot) {
      state.shotId = null;
      clearCompareState();
      return;
    }
    const inventory = compareInventory();
    const shotId = shot.shot_id;
    const rows = inventory.rowsByShotId[shotId] || [];
    if (!rows.length) {
      state.shotId = null;
      clearCompareState();
      return;
    }
    const candidateId = rows.some((row) => row.candidate_id === state.candidateId)
      ? state.candidateId : defaultCompareTargetId(rows);
    state.candidateId = candidateId;
    state.shotId = shotId;
    state.shot = shot;
    let baselineId = state.baselineId;
    if (!baselineId || baselineId === candidateId
      || !rows.some((row) => row.candidate_id === baselineId)) baselineId = null;
    state.baselineId = baselineId;
    state.rows = rows;

    const counts = compareCounts(rows);
    const parts = ["候选 " + counts.total];
    if (counts.pending) parts.push("待处理 " + counts.pending);
    if (counts.unknown) parts.push("未知 " + counts.unknown);
    if (counts.unchecked) parts.push("未检查 " + counts.unchecked);
    state.subject = deps.shotLabelOf(shotId) + " · " + parts.join(" · ");

    state.jumpTarget = nextPendingShotId({
      rowsByShotId: inventory.rowsByShotId,
      shotOrder: inventory.shots.map((item) => item.shot_id),
      currentShotId: shotId,
    }) || null;

    rememberCompareView();

    const targetRow = rows.find((row) => row.candidate_id === candidateId) || null;
    const candidate = targetRow && targetRow.record ? targetRow.record : null;
    const sha256 = targetRow ? targetRow.asset_sha256 : null;
    state.reworkEntry = (targetRow && candidate && sha256)
      ? { shotId, candidateId: targetRow.candidate_id, sha256 }
      : null;

    const selected = selectionAdoption.entryOf(shotId)?.record || null;
    const already = Boolean(selected && selected.action === "select" && targetRow
      && selected.candidate_id === targetRow.candidate_id
      && selectionAdoption.stateOf(shotId) === "current");
    state.adoptSelectEnabled = Boolean(targetRow && targetRow.record && targetRow.record.asset_sha256) && !already;
    state.adoptClearEnabled = Boolean(selected && selected.action === "select");

    const adopted = adoptedMarkOf(shotId);
    state.reviewEnabled = Boolean(targetRow && !selectionAdoption.isReviewInFlight(shotId));
    state.viewedCaption = "当前查看：候选 v" + (targetRow?.version || "?")
      + (adopted?.candidate_id === candidateId ? " · 已采用" : " · 未采用此候选")
      + "；查看和对照不会改选。";
    state.viewedUrl = urlOf(compareImageUrls, targetRow);
    const comparison = baselineId ? (rows.find((row) => row.candidate_id === baselineId) || null) : null;
    state.baselineUrl = urlOf(compareImageUrls, comparison);
  }

  function renderCompare(): void {
    state.status = "";
    projectCompare();
    renderComparePanels();
    if (state.shotId) {
      for (const row of state.rows) ensureCandidatePreview(row);
      void loadCompareImages();
    }
    if (state.shot) void refreshCompareReferences(state.shot);
  }

  /** 预览缩略图：只请求一次，成功后按 keyed 模板补 src（不重建卡片）。 */
  function ensureCandidatePreview(row: CompareRow): void {
    const key = cacheKeyOf(row);
    if (candidatePreviewUrls.has(key) || candidatePreviewPending.has(key)) return;
    candidatePreviewPending.add(key);
    deps.ensurePreviewUrl(row.shot_id, row.candidate_id, row.asset_sha256)
      .then((url) => {
        candidatePreviewPending.delete(key);
        if (!url) return;
        candidatePreviewUrls.set(key, url);
        if (state.shotId === row.shot_id && state.rows.some((item) => item.candidate_id === row.candidate_id)) {
          renderComparePanel();
        }
      })
      .catch(() => { candidatePreviewPending.delete(key); });
  }

  function ensureReviewPreview(shotId: string, actionId: string, sha256: string): string | null {
    const key = shotId + ":" + actionId + ":" + sha256;
    const cached = reviewPreviewUrls.get(key);
    if (cached) return cached;
    if (reviewPreviewPending.has(key)) return null;
    reviewPreviewPending.add(key);
    deps.ensurePreviewUrl(shotId, actionId, sha256)
      .then((url) => {
        reviewPreviewPending.delete(key);
        if (!url) return;
        reviewPreviewUrls.set(key, url);
        renderReviewList();
      })
      .catch(() => { reviewPreviewPending.delete(key); });
    return null;
  }

  function rememberCompareView(): void {
    const projectId = deps.currentProjectId();
    if (projectId && state.shotId) compareViews.set(projectId + ":" + state.shotId, {
      candidateId: state.candidateId, baselineId: state.baselineId,
    });
  }

  /** 当前查看/对照两张大图：代次守卫，晚到的旧请求不改当前投影。 */
  async function loadCompareImages(): Promise<void> {
    const token = ++compareImageToken;
    const rows = state.rows;
    const viewed = rows.find((row) => row.candidate_id === state.candidateId) || null;
    const comparison = state.baselineId
      ? (rows.find((row) => row.candidate_id === state.baselineId) || null)
      : null;
    let missing = false;
    for (const row of [viewed, comparison]) {
      if (!row) continue;
      if (compareImageUrls.has(cacheKeyOf(row))) continue;
      const url = await deps.ensurePreviewUrl(row.shot_id, row.candidate_id, row.asset_sha256);
      if (token !== compareImageToken) return;
      if (!url) { missing = true; continue; }
      compareImageUrls.set(cacheKeyOf(row), url);
    }
    if (token !== compareImageToken) return;
    state.viewedUrl = urlOf(compareImageUrls, viewed);
    state.baselineUrl = urlOf(compareImageUrls, comparison);
    if (missing) state.status = "候选字节缺失；请恢复项目包，不会用另一张图片替代。";
    renderComparePanel();
  }

  /** 这张图实际会发送的参考图（与提交时同一选择函数），用作比较的左边一栏。 */
  async function refreshCompareReferences(shot: PlanShot): Promise<void> {
    const token = ++compareToken;
    const pid = deps.currentProjectId();
    const viewed = adoptSourceOf(shot.shot_id, state.candidateId)?.candidate;
    const origin = viewed ? attemptsByActionId()[viewed.action_id] : null;
    const references = origin?.references || [];
    const entries: ReferenceEntryView[] = [];
    for (const reference of references) {
      if (!pid) continue;
      const asset = await deps.readAsset(pid, reference.sha256);
      entries.push({ sha256: reference.sha256, role: reference.role, missing: !asset, url: null });
    }
    if (token !== compareToken || pid !== deps.currentProjectId()) return;
    for (const entry of entries) {
      entry.url = await deps.ensurePreviewUrl("参考图", entry.sha256, entry.sha256);
      if (token !== compareToken) return;
    }
    if (token !== compareToken) return;
    state.references = entries;
    if (!entries.length) {
      state.basisTitle = "找不到当前候选的原参考图来源链；不会用当前新资料冒充原图。";
    } else {
      state.basisTitle = "当前候选原任务参考图（" + entries.length + " 张）；均按原比例展示。";
    }
    if (!state.shotId) return;
    renderComparePanel();
  }

  /* ------------------------------------------------------------- 放大查看 */

  function openImageZoom(src: string, label: string): void {
    if (!src) return;
    imageZoomReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    state.zoomSrc = src;
    state.zoomLabel = label;
    state.zoomNative = false;
    renderImageZoom();
    if (!elements.imageZoomDialog.open) elements.imageZoomDialog.showModal();
    elements.imageZoomDialog.querySelector<HTMLButtonElement>("#image-zoom-close")?.focus();
  }

  function closeImageZoom(): void {
    if (elements.imageZoomDialog.open) elements.imageZoomDialog.close();
    state.zoomSrc = null;
    state.zoomNative = false;
    state.zoomLabel = ZOOM_DEFAULT_TITLE;
    renderImageZoom();
    if (imageZoomReturnFocus?.isConnected) imageZoomReturnFocus.focus();
  }

  function zoomViewed(): void {
    openImageZoom(state.viewedUrl || "", state.viewedCaption);
  }

  function zoomBaseline(): void {
    openImageZoom(state.baselineUrl || "", "对照候选（不改变采用）");
  }

  function toggleZoomNative(): void {
    state.zoomNative = !state.zoomNative;
    renderImageZoom();
  }

  /* ------------------------------------------------------------- 比较入口 */

  function focusCandidateTab(candidateId: string | null): void {
    if (!candidateId) return;
    const tab = elements.comparePanel.querySelector<HTMLButtonElement>(
      '[role="tab"][data-candidate-id="' + candidateId + '"]');
    if (tab) tab.focus({ preventScroll: true });
  }

  function openCompare(shotId: string, options: { candidateId?: string | null; focus?: boolean } = {}): void {
    state.shotId = shotId;
    state.status = "";
    const requested = options.candidateId;
    if (requested !== undefined) {
      // 卡片动作显式交给哪条候选就看哪条：无效目标不静默回退，面板保持可解释的空选择。
      const rows = compareInventory().rowsByShotId[shotId] || [];
      const exists = requested === null || rows.some((row) => row.candidate_id === requested);
      state.candidateId = exists ? requested : null;
      state.baselineId = null;
      deps.selectStage("review");
      renderCompare();
      if (!exists) setCompareStatus("这条候选已经不在了，先重新选择候选。");
    } else {
      const previous = compareViews.get(deps.currentProjectId() + ":" + shotId);
      state.candidateId = previous?.candidateId || null;
      state.baselineId = previous?.baselineId || null;
      deps.selectStage("review");
      renderCompare();
    }
    if (options.focus === true) focusCandidateTab(state.candidateId);
  }

  function closeCompare(): void {
    state.shotId = null;
    state.candidateId = null;
    renderCompare();
  }

  function isComparing(shotId: string): boolean {
    return state.shotId === shotId;
  }

  function setCompareStatus(text: string): void {
    state.status = text;
    renderComparePanel();
  }

  /** 「下一个待处理」：按 domain 给的目标换图，换图即换到审核阶段并把焦点交给默认候选页签。 */
  function jumpToNextPending(): void {
    const target = state.jumpTarget;
    if (!target) return;
    openCompare(target, { focus: true });
  }

  /** 切换查看目标：不改规则、不写存储，只换清单与选中态；列表节点按候选 keyed 复用。 */
  function selectCompareCandidate(candidateId: string | null, options: { focus?: boolean } = {}): void {
    // 换一条候选时收起返工区（它绑定打开那一刻的候选身份），该候选自己的草稿保留。
    if (rework.shotId !== null && candidateId !== state.candidateId) {
      closeReworkPanel({ focusCandidate: false });
    }
    state.candidateId = candidateId;
    state.status = "";
    renderCompare();
    if (options.focus === true) focusCandidateTab(candidateId);
  }

  function handleCompareKeydown(event: KeyboardEvent): void {
    const rows = state.rows;
    if (!rows.length) return;
    const current = rows.findIndex((row) => row.candidate_id === state.candidateId);
    const index = current === -1 ? 0 : current;
    let next: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (index + 1) % rows.length;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      next = (index - 1 + rows.length) % rows.length;
    } else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = rows.length - 1;
    else if (event.key === "Escape") {
      event.preventDefault();
      deps.focusReviewEntry(state.shotId);
      return;
    } else {
      return;
    }
    event.preventDefault();
    if (next === null) return;
    selectCompareCandidate(rows[next].candidate_id, { focus: true });
  }

  function handleBaselineChange(value: string | null): void {
    const picked = value || null;
    state.baselineId = picked && state.rows.some((row) => row.candidate_id === picked) ? picked : null;
    rememberCompareView();
    renderComparePanel();
    void loadCompareImages();
  }

  /** 单图 AI 复核（按需发起）：只响应用户显式点击；查看/切换/采用不调用此函数。
   * 未运行如实记 not_run（reviewStatusOf 投影），不折叠成 Unknown、不进 ack 门。 */
  async function handleCompareReview(): Promise<void> {
    const shotId = state.shotId, candidateId = state.candidateId;
    if (!shotId || !candidateId) return;
    const outcome = await selectionAdoption.reviewCandidate(shotId, candidateId);
    if (shotId === state.shotId && candidateId === state.candidateId) {
      renderCompare();
      setCompareStatus(outcome?.failed
        ? "AI 复核未完成：" + outcome.message + "（真实失败才记 Unknown，未发起仍是未复核）"
        : "复核结果只属于所点击的这条候选，不自动采用；未复核不阻断人工采用。");
    }
  }

  /* --------------------------------------------- 单图返工闭环（V2.5.4） */

  /**
   * 返工区与比较区相邻但独立：比较区只投影、只读；这里才写 Prompt 版本、
   * 单图确认与新的生成尝试。草稿按 project/shot/candidate 留在内存，预览只有用户确认时才落成版本。
   */
  function draftKeyOf(shotId: string, candidateId: string): string {
    const projectId = deps.currentProjectId() || "";
    return projectId + "::" + shotId + "::" + candidateId;
  }

  function reworkDraftOf(shotId: string, candidateId: string, row: CompareRow | null): CompareReworkDraft {
    const key = draftKeyOf(shotId, candidateId);
    let draft = reworkDrafts.get(key);
    if (!draft) {
      draft = {
        problems: suggestReworkProblems(row ? row.report : null),
        direction: suggestedReworkDirection(row ? row.report : null),
        intent: null,
      };
      reworkDrafts.set(key, draft);
    }
    return draft;
  }

  function reworkShotRow(shotId: string, candidateId: string | null): CompareRow | null {
    const inventory = compareInventory();
    const rows = inventory.rowsByShotId[shotId] || [];
    // 显式目标必须精确命中：缺失时返回 null 并由调用方阻断，不回退到另一条候选。
    if (candidateId) return rows.find((item) => item.candidate_id === candidateId) || null;
    return rows[0] || null;
  }

  function reworkSummaryOf(draft: CompareReworkDraft | null): string {
    if (draft && draft.intent) {
      return "预览已就绪：确认并生成会把它保存为 Prompt 新版本（旧版本保留），"
        + "只重新生成这张图；改过问题或方向后需要重新预览。";
    }
    return "选好问题或写下方向 → 预览返工 Prompt → 确认并生成这张图。";
  }

  /** 输入变了：旧意图不再代表将要发送的内容，必须重新预览。 */
  function dirtyReworkDraft(draft: CompareReworkDraft | null): void {
    if (!draft || !draft.intent) return;
    draft.intent = null;
    rework.status = "";
  }

  function toggleReworkProblem(problemId: string, checked: boolean): void {
    const draft = rework.draft;
    if (!draft) return;
    if (checked) {
      if (draft.problems.indexOf(problemId) === -1) draft.problems = draft.problems.concat([problemId]);
    } else {
      draft.problems = draft.problems.filter((id) => id !== problemId);
    }
    dirtyReworkDraft(draft);
    renderReworkPanel();
  }

  /** 入口：只接受显式候选身份；缺失时可见阻断，不回退到另一条候选。 */
  function openReworkPanel(options: { shotId?: string | null; candidateId?: string | null } = {}): void {
    const shotId = options.shotId !== undefined ? options.shotId : state.shotId;
    const candidateId = options.candidateId !== undefined ? options.candidateId : state.candidateId;
    if (!shotId || !candidateId || rework.inFlight) return;
    const row = reworkShotRow(shotId, candidateId);
    if (!row || !row.record || row.candidate_id !== candidateId) {
      setCompareStatus("这条候选已经不在了，先重新选择候选。");
      return;
    }
    // 同一意图不跨候选复用：来源变化时旧候选的意图作废，必须重新预览。
    if (rework.shotId !== null && (rework.shotId !== shotId || rework.candidateId !== row.candidate_id)) {
      const stale = rework.draftKey ? reworkDrafts.get(rework.draftKey) : null;
      if (stale) stale.intent = null;
    }
    rework.shotId = shotId;
    rework.candidateId = row.candidate_id;
    rework.assetSha256 = row.asset_sha256;
    rework.version = row.version === null || row.version === undefined ? null : row.version;
    rework.draftKey = draftKeyOf(shotId, row.candidate_id);
    rework.draft = reworkDraftOf(shotId, row.candidate_id, row);
    rework.status = "";
    rework.error = "";
    const basis = ["返工依据：候选 v" + (rework.version === null ? "?" : rework.version)];
    if (row.top_finding) basis.push("先看：" + row.top_finding.title);
    rework.basis = basis.join(" · ");
    rework.tech = "sha256 " + String(rework.assetSha256).slice(0, 12) + "… · candidate " + row.candidate_id;
    // 问题勾选、方向文本、预览与状态全部随模板投影（方向是草稿的投影，不在这里回写节点）。
    renderComparePanels();
    const first = elements.reworkPanel
      .querySelector<HTMLInputElement>("#rework-problems input[type=\"checkbox\"]");
    if (first) first.focus();
    elements.reworkPanel.scrollIntoView({ block: "nearest" });
  }

  /** 收起返工区：清掉未确认的意图；草稿（问题与方向）按候选保留。 */
  function closeReworkPanel({ focusCandidate = false }: { focusCandidate?: boolean } = {}): void {
    const shotId = rework.shotId;
    const candidateId = rework.candidateId;
    const draft = rework.draftKey ? reworkDrafts.get(rework.draftKey) : null;
    if (draft) draft.intent = null;
    rework.shotId = null;
    rework.candidateId = null;
    rework.assetSha256 = null;
    rework.version = null;
    rework.draftKey = null;
    rework.draft = null;
    rework.basis = "";
    rework.tech = "";
    rework.status = "";
    rework.error = "";
    renderComparePanels();
    if (focusCandidate && shotId) focusCompareCandidate(shotId, candidateId);
  }

  /** 收起后把焦点还给原候选：比较区还在就回到候选页签，否则回到该图的比较入口。 */
  function focusCompareCandidate(shotId: string, candidateId: string | null): void {
    const tab = candidateId ? elements.comparePanel.querySelector<HTMLButtonElement>(
      '[role="tab"][data-candidate-id="' + candidateId + '"]') : null;
    if (tab) {
      tab.focus();
      return;
    }
    deps.focusReviewEntry(shotId);
  }

  /** 按建议重填：问题与方向回到报告先看项的默认值，预览作废。 */
  function resetRework(): void {
    const shotId = rework.shotId;
    if (!shotId || !rework.candidateId || rework.inFlight) return;
    const row = reworkShotRow(shotId, rework.candidateId);
    const key = rework.draftKey;
    if (key) reworkDrafts.delete(key);
    rework.draft = reworkDraftOf(shotId, rework.candidateId, row);
    rework.status = "";
    rework.error = "";
    renderComparePanels();
  }

  function cancelRework(): void {
    if (rework.inFlight) return;
    closeReworkPanel({ focusCandidate: true });
  }

  function handleReworkKeydown(event: KeyboardEvent): void {
    if (event.key === "Escape") {
      event.preventDefault();
      cancelRework();
    }
  }

  function handleReworkDirectionInput(value: string): void {
    const draft = rework.draft;
    if (!draft) return;
    draft.direction = value;
    dirtyReworkDraft(draft);
    renderReworkPanel();
  }

  /** 预览：owner 编译一次只读意图；视图只持有并显示，不写记录。 */
  async function previewRework(): Promise<void> {
    const shotId = rework.shotId;
    const draft = rework.draft;
    if (!deps.currentProjectId() || !shotId || !draft || rework.inFlight) return;
    const sourceCandidateId = rework.candidateId;
    setReworkError("");
    if (!sourceCandidateId) {
      setReworkError("返工依据已经不在，先回到比较区重新选择候选。");
      return;
    }
    const row = reworkShotRow(shotId, sourceCandidateId);
    if (!row || !row.record || row.candidate_id !== sourceCandidateId) {
      setReworkError("返工依据已经不在，先回到比较区重新选择候选。");
      return;
    }
    // 预览前不再从 DOM 现读方向：方向已在每次键入时由模板事件写入草稿。
    rework.inFlight = true;
    renderReworkPanel();
    try {
      draft.intent = await generation.prepareRework({
        shotId, candidateId: sourceCandidateId, problems: [...draft.problems], direction: draft.direction,
        report: row.report || null,
      });
      rework.status = "预览已就绪：确认并生成时会先把它保存为新版本，"
        + "再只提交这一张图；预览本身没有写入任何记录。";
    } catch (error) {
      draft.intent = null;
      setReworkError(deps.suffixedErrorMessage(error, "预览没有生成，旧版本与输入保留。", "（预览未生成，旧版本与输入保留）"));
    } finally {
      rework.inFlight = false;
      if (rework.draftKey === draftKeyOf(shotId, sourceCandidateId)) renderReworkPanel();
    }
  }

  /** 查看/编辑完整 Prompt 已收归确认路径：不再提供预览直落版的中间入口。 */
  async function editRework(): Promise<void> {
    const draft = rework.draft;
    setReworkError("");
    if (!rework.shotId || !draft || !draft.intent) {
      setReworkError("先预览返工 Prompt，再确认生成。");
      return;
    }
    setReworkError("返工全文只在确认生成时由 owner 落成新版本；人工全文请到 Prompt 列表显式编辑。");
  }

  /**
   * 确认并生成这张图：只把预览时 owner 给的意图原样交回确认。
   * 当前性、Prompt 落版、确认/预约/提交都在 owner 内部；视图不重算、不猜版本。
   */
  async function submitRework(): Promise<void> {
    const shotId = rework.shotId;
    const draft = rework.draft;
    if (!deps.currentProjectId() || !shotId || !draft || rework.inFlight) return;
    const action = deps.beginAction();
    const sourceCandidateId = rework.candidateId;
    setReworkError("");
    if (!draft.intent) {
      setReworkError("先预览返工 Prompt，再确认生成。");
      return;
    }
    const currentSource = reworkShotRow(shotId, sourceCandidateId);
    if (!sourceCandidateId || !currentSource || currentSource.candidate_id !== sourceCandidateId) {
      draft.intent = null;
      renderReworkPanel();
      setReworkError("返工依据已经不在，先回到比较区重新选择候选。");
      return;
    }
    rework.inFlight = true;
    renderReworkPanel();
    try {
      const intent = draft.intent;
      const result = await generation.confirmRework({ intent });
      if (!action.alive()) return;
      if (result.stale) {
        // owner 已判过期且零外发：只呈现，不自动确认、不自动重提；旧意图作废。
        draft.intent = null;
        renderReworkPanel();
        setReworkError(result.message || "返工意图已过期；请重新预览后再确认返工。");
        return;
      }
      if (result.skipped) {
        setReworkError(result.message || "返工没有提交；旧候选与旧 Prompt 不受影响。");
        return;
      }
      const latestAttempt = generation.latestAttemptOf(shotId);
      const attemptState = latestAttempt ? latestAttempt.record.state : null;
      draft.intent = null;
      rework.shotId = null;
      rework.candidateId = null;
      rework.assetSha256 = null;
      rework.version = null;
      rework.draftKey = null;
      rework.draft = null;
      rework.basis = "";
      rework.tech = "";
      rework.status = "";
      renderReworkPanel();
      deps.renderAttempts();
      deps.renderPrompts();
      deps.renderConfirm();
      await deps.deriveState();
      focusCompareCandidate(shotId, sourceCandidateId);
      setCompareStatus("返工已提交（Prompt v" + (result.promptVersion || "?") + " · "
        + attemptStateLabel(attemptState) + "）；旧候选保留，只有这张图新增了版本。");
      // 与生成区单张提交同一语义：unknown 成功返回也要如实提示定位（只增显示调用，不改控制流与返回）。
      if (attemptState === ATTEMPT_STATES.unknown) {
        const noTaskId = !latestAttempt || !latestAttempt.record.task_id;
        deps.showAttemptError("这次返工提交的结果没有确认：不要重复提交。"
          + (noTaskId ? "没有任务编号，只能显式新建 action。" : "可以按任务编号核对。"));
      }
    } catch (error) {
      if (action.alive()) {
        setReworkError(errorMessageOf(error, "返工没有提交；旧候选与旧 Prompt 不受影响。"));
      }
    } finally {
      if (action.alive()) {
        rework.inFlight = false;
        renderReworkPanel();
      }
    }
  }

  /* ----------------------------------------------- 人工选择与失效（V2.6.1） */

  // 人工选择与采用：记录所有权在 selectionAdoption Module；这里只做视图装配
  // （状态徽标/入口按钮）与动作转发，不直接读写记录或拼持久化顺序。
  function selectionEntryOf(shotId: string | null): SelectionEntry | null {
    return selectionAdoption.entryOf(shotId);
  }

  function selectionStateOf(shotId: string): SelectionState {
    return selectionAdoption.stateOf(shotId);
  }

  /** 某张图当前采用的候选（含过期标记）：只读投影，供比较列表做徽标。 */
  function adoptedMarkOf(shotId: string | null): { candidate_id: string | null; state: SelectionState } | null {
    return selectionAdoption.adoptedMark(shotId);
  }

  /** 采用进度行：只读投影，写进 UI 状态后由审核区模板一次投影（不再直接写节点）。 */
  function renderSelectionProgress(): void {
    if (!inputs.suitePlan()) {
      state.adoptProgress = "";
    } else {
      const set = selectionAdoption.projection(inputs.sources()).set;
      state.adoptProgress = set.summary.required_total > 0
        ? selectionSetText(set) + "采用只引用候选（candidate_id + sha256），不复制图片。"
        : "";
    }
    renderReviewList();
  }

  /** 采用目标：把「正看着的候选」解析成候选记录 + 文档版本 + 当前审核报告。 */
  function adoptSourceOf(shotId: string | null, candidateId: string | null): AdoptionSource | null {
    return selectionAdoption.sourceOf(shotId, candidateId);
  }

  function selectionTextOf(shotId: string): string {
    return selectionAdoption.summary(shotId);
  }

  function setAdoptStatus(text: string): void {
    state.adoptStatus = text;
    renderReviewList();
  }

  /** 就地错误：文案归 UI 状态随模板投影，重画不会把上一次的错误悄悄抹掉。 */
  function setAdoptError(text: string): void {
    state.adoptError = text;
    renderReviewList();
  }

  /** One explicit human action. Identity freezes before any byte read; selection is append-only/OCC. */
  async function adoptCandidate(kind: "select" | "clear", shotId: string | null = state.shotId,
    candidateId: string | null = state.candidateId): Promise<void> {
    if (!deps.currentProjectId() || !shotId || selectionAdoption.isSelecting()) return;
    const action = deps.beginAction();
    state.adoptError = "";
    setAdoptStatus("正在保存 " + deps.shotLabelOf(shotId) + " 的人工选择…");
    try {
      await selectionAdoption.select(kind, shotId, candidateId);
      if (!action.alive()) return;
      setAdoptStatus(deps.shotLabelOf(shotId)
        + (kind === "select" ? " 已采用候选" : " 已取消采用")
        + "；旧候选和旧采用保留在历史中。确定性硬阻断仍会阻止交付。");
    } catch (error) {
      if (!action.alive()) return;
      setAdoptStatus("人工选择没有保存；原采用保留。");
      setAdoptError(errorMessageOf(error, "存储失败，请重试。"));
    } finally {
      // 行内采用后立即重画审核卡：data-selection-state 与已采用按钮都来自重画，
      // 走查里“等待 current”才有稳定的可观测终态；只读投影，不写库不发请求。
      if (action.alive()) { deps.renderAttempts(); renderReviewList(); renderCompare(); }
    }
  }

  /* ------------------------------------------------------- 逐图审核列表 */

  /**
   * 审核阶段的逐图入口：图片 + 候选数 + 采用状态 + 逐图检查摘要 + 比较/返工/采用。
   * 卡片只复读同一份当前报告（compareInventory 已按 reviewIsCurrent 过滤）；
   * 不新增第二套规则，也不改变任何选择语义。
   */
  function reviewCards(): ReviewCardView[] {
    const shots = shotSummaries();
    const reviewable = shots.filter((shot) => generation.candidateChainOf(shot.shot_id).length > 0);
    if (!reviewable.length) return [];
    const inventory = compareInventory();
    const cards: ReviewCardView[] = [];
    for (const shot of reviewable) {
      const chain = generation.candidateChainOf(shot.shot_id);
      // 卡片显示最新 Attempt 的已保存候选（latestStoredCandidateOf）：只有它才满足
      // 采用前置（计划§14.5：确定性合法 + 当前采用依据 + 明确 actor=user）。
      const stored = generation.latestStoredCandidateOf(shot.shot_id);
      const stateName = selectionStateOf(shot.shot_id);
      const adopted = adoptedMarkOf(shot.shot_id);
      const shownCandidateId = stored ? stored.record.candidate_id : null;
      const displayedIsAdopted = Boolean(shownCandidateId && adopted
        && adopted.candidate_id === shownCandidateId && adopted.state === "current");
      const rows = inventory.rowsByShotId[shot.shot_id] || [];
      const shownRow = stored
        ? (rows.find((row) => row.candidate_id === stored.record.candidate_id) || null)
        : null;
      const badgeClass = displayedIsAdopted
        ? "is-adopted"
        : (stateName === "stale" && adopted ? "is-review-warn" : "is-empty");
      const badgeText = displayedIsAdopted
        ? "已采用"
        : (adopted && adopted.state === "stale" && adopted.candidate_id === shownCandidateId
          ? "已采用（已过期）" : "未采用此候选");
      const previewKey = stored
        ? shot.shot_id + ":" + stored.record.action_id + ":" + stored.record.asset_sha256
        : "";
      const card: ReviewCardView = {
        shotId: shot.shot_id,
        label: shot.label,
        state: stateName,
        chainCount: chain.length,
        badgeClass,
        badgeText,
        adoptedCandidateId: adopted?.candidate_id || "",
        storedCandidateId: shownCandidateId,
        previewUrl: previewKey ? (reviewPreviewUrls.get(previewKey) || null) : null,
        message: stored
          ? null
          : (chain.length
            ? "这条候选缺少原动作观察，暂不能采用；到「生成」里用已有动作重新生成后再采用。"
            : "这张图还没有已保存的候选；到「生成」里生成后再比较。"),
        check: stored ? reviewCheckOf(shownRow) : null,
        displayedIsAdopted,
        stored: Boolean(stored),
        canRework: Boolean(stored && shownCandidateId),
        canAdopt: Boolean(stored && shownCandidateId) && !displayedIsAdopted,
        adoptTitle: displayedIsAdopted ? "已采用这条候选；换用其他候选请点「比较候选」。" : null,
      };
      cards.push(card);
      if (stored) ensureReviewPreview(shot.shot_id, stored.record.action_id, stored.record.asset_sha256);
    }
    return cards;
  }

  function reviewCheckOf(shownRow: CompareRow | null): ReviewCheckView {
    if (!shownRow) {
      return {
        reviewState: "unchecked",
        candidateId: "",
        badgeClass: "is-review-unchecked",
        stateLabel: COMPARE_STATE_TEXT.unchecked,
        summary: null,
        ai: null,
        reportFailure: null,
        headline: null,
        hint: "这张图还没有当前审核报告；打开「比较候选」可查看或补建。",
      };
    }
    let ai: { status: string; text: string } | null = null;
    let reportFailure: string | null = null;
    if (shownRow.report) {
      const aiStatus = selectionAdoption.reviewStatusOf(shownRow.candidate_id);
      ai = {
        status: aiStatus.status,
        text: aiStatus.status === "reviewed" ? "AI 复核：已完成（只提示，不自动采纳）"
          : aiStatus.status === "unknown" ? "AI 复核：未完成（结果未知，不阻断人工采用）"
            : "AI 复核：未复核（未运行，按需发起才会调用；不阻断人工采用）",
      };
    } else {
      // 只在真的补建失败时多一行：确定性报告缺失 ≠ AI 未复核，失败原因必须如实显示。
      const failure = selectionAdoption.reportBuildFailure(shownRow.candidate_id);
      if (failure) {
        reportFailure = "自动检查报告补建失败：" + failure
          + "（候选与本地图片保留，采用会被挡住；重新打开或再次采用会补建，不需要 AI）";
      }
    }
    return {
      reviewState: shownRow.review_state,
      candidateId: shownRow.candidate_id,
      badgeClass: COMPARE_STATE_BADGE[shownRow.review_state] || "is-review-unchecked",
      stateLabel: compareStateLabel(shownRow),
      summary: shownRow.report ? reviewSummaryText(shownRow.report) : null,
      ai,
      reportFailure,
      headline: compareRowHeadline(shownRow),
      hint: null,
    };
  }

  function reviewCardTemplate(card: ReviewCardView) {
    return html`
      <div class="review-card" data-shot-id=${card.shotId} data-selection-state=${card.state}>
        <div class="review-card-head">
          <span class="name">${card.label}</span>
          <span class="badge ${card.badgeClass}" data-adopted-candidate-id=${card.adoptedCandidateId}>${card.badgeText}</span>
          <span class="meta">${"候选 " + card.chainCount + " 个"}</span>
        </div>
        ${card.stored
          ? html`
              <div class="review-preview">
                ${card.previewUrl
                  ? html`<img src=${card.previewUrl} alt=${card.label + " 的最新候选"} loading="lazy">`
                  : html`<img alt=${card.label + " 的最新候选"} loading="lazy">`}
              </div>
              ${card.check ? reviewCheckTemplate(card) : nothing}
              <div class="review-card-actions">
                <button type="button" @click=${() => openCompare(card.shotId, { focus: true })}>${"比较候选（" + card.chainCount + "）"}</button>
                <button type="button" ?disabled=${!card.canRework} @click=${() => {
                  // 点击时捕获本卡实际显示的候选身份：晚到候选不得改目标，缺失时阻断不回退。
                  if (!card.storedCandidateId) return;
                  openCompare(card.shotId, { candidateId: card.storedCandidateId });
                  openReworkPanel({ shotId: card.shotId, candidateId: card.storedCandidateId });
                }}>按问题返工</button>
                <button
                  type="button"
                  class=${card.displayedIsAdopted ? "" : "primary"}
                  title=${ifDefined(card.adoptTitle || undefined)}
                  ?disabled=${!card.canAdopt}
                  @click=${() => {
                    if (card.storedCandidateId) void adoptCandidate("select", card.shotId, card.storedCandidateId);
                  }}
                >${card.displayedIsAdopted ? "已采用" : "采用候选"}</button>
              </div>
            `
          : html`<p class="meta">${card.message || ""}</p>`}
      </div>
    `;
  }

  function reviewCheckTemplate(card: ReviewCardView) {
    const check = card.check;
    if (!check) return nothing;
    return html`
      <div
        class="review-card-check"
        data-shot-id=${card.shotId}
        data-review-state=${check.reviewState}
        data-candidate-id=${check.candidateId}
      >
        <span class="badge ${check.badgeClass}">${check.stateLabel}</span>
        ${check.reportFailure ? html`<p class="meta review-check-report" data-review-report="failed">${check.reportFailure}</p>` : nothing}
        <details class="review-check-details">
          <summary>检查摘要</summary>
          ${check.summary ? html`<p class="meta review-check-summary">${check.summary}</p>` : nothing}
          ${check.ai ? html`<p class="meta review-check-ai" data-review-ai=${check.ai.status}>${check.ai.text}</p>` : nothing}
          ${check.headline ? html`<p class="meta review-check-headline">${check.headline}</p>` : nothing}
          ${check.hint ? html`<p class="meta">${check.hint}</p>` : nothing}
        </details>
      </div>
    `;
  }

  /**
   * 审核区整块投影（index 只留 `#review-list-mount` 空壳）：采用进度、空占位、逐图卡、
   * 采用状态与就地错误同属一份 UI 状态；卡片按 shot_id keyed，重画只 patch 变化的行。
   */
  function reviewAreaTemplate(cards: ReviewCardView[]) {
    return html`
      <p id="adopt-progress" class="meta" role="status">${state.adoptProgress}</p>
      <p id="review-empty" class="empty" ?hidden=${cards.length > 0}>还没有生成成功的候选；先在「生成」里整套生成或逐张提交。</p>
      <div id="review-list" class="review-list">
        ${repeat(cards, (card) => card.shotId, (card) => reviewCardTemplate(card))}
      </div>
      <p id="adopt-status" class="status" role="status" ?hidden=${state.adoptStatus.length === 0}>${state.adoptStatus}</p>
      <p id="adopt-error" class="error" role="alert" ?hidden=${state.adoptError.length === 0}>${state.adoptError}</p>
    `;
  }

  function renderReviewList(): void {
    if (!elements.reviewList) return;
    renderLit(reviewAreaTemplate(reviewCards()), elements.reviewList);
  }

  /** 重开项目时的就地状态归零：与原 loadWorkspace 重置项一一对应。 */
  function resetViewState(): void {
    state.shotId = null;
    state.candidateId = null;
    state.baselineId = null;
    state.status = "";
    state.rows = [];
    state.references = [];
    compareToken += 1;
    compareImageToken += 1;
    compareImageUrls.clear();
    candidatePreviewUrls.clear();
    reviewPreviewUrls.clear();
    candidatePreviewPending.clear();
    reviewPreviewPending.clear();
    reworkDrafts = new Map();
    rework.shotId = null;
    rework.candidateId = null;
    rework.assetSha256 = null;
    rework.version = null;
    rework.draftKey = null;
    rework.draft = null;
    rework.basis = "";
    rework.tech = "";
    rework.inFlight = false;
    rework.status = "";
    rework.error = "";
    state.zoomSrc = null;
    state.zoomNative = false;
    state.zoomLabel = ZOOM_DEFAULT_TITLE;
    state.adoptProgress = "";
    state.adoptError = "";
    setAdoptStatus("");
    renderCompare();
    renderReviewList();
  }

  /* ------------------------------------------------------- 外壳监听装配 */

  /**
   * 幂等装配：只挂**外壳根**监听（面板内的按钮/选择器/文本框都由模板 @event 自己持有，
   * 不在这里重复挂）。工作区装配期调用一次；重复调用不会产生第二份监听。
   */
  function bind(): void {
    if (bound) return;
    bound = true;
    // Escape 取消返工：keydown 归返工面板根（模板内部没有第二层包裹节点）。
    elements.reworkPanel.addEventListener("keydown", (event) => { handleReworkKeydown(event); });
    // 对话框的 Escape 由 cancel 事件接管；关闭后焦点回到打开前的元素。
    elements.imageZoomDialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      closeImageZoom();
    });
  }

  // 装配期先成形一次：模板自带的选择器/输入框在第一个业务渲染之前就有确定初值
  //（例如对照下拉在选项插入前不会先被赋一次值），此后所有投影都是就地 patch。
  renderComparePanels();
  // 审核区同理：进度/空占位/列表/采用反馈的空壳在第一个业务渲染前就位（无项目时是空态）。
  renderReviewList();

  return {
    bind,
    renderReviewList,
    renderCompare,
    renderSelectionProgress,
    openCompare,
    closeCompare,
    isComparing,
    handleCompareKeydown,
    handleBaselineChange,
    handleCompareReview,
    zoomViewed,
    zoomBaseline,
    closeImageZoom,
    toggleZoomNative,
    openReworkPanel,
    previewRework,
    editRework,
    submitRework,
    resetRework,
    cancelRework,
    handleReworkKeydown,
    handleReworkDirectionInput,
    adoptCandidate,
    selectionEntryOf,
    selectionStateOf,
    adoptedMarkOf,
    adoptSourceOf,
    selectionTextOf,
    resetViewState,
  };
}
