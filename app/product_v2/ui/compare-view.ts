/**
 * 审核视图（设计 §10.1 的第三个视图）：「审核」阶段的逐图审核列表、候选比较面板、
 * 单图返工闭环与人工采用。
 *
 * 边界（设计 §10.1）：这里只持比较/返工/采用三区的 DOM 与就地内存态（当前查看的
 * 图与候选、跨项目记忆、返工草稿与在飞标识），不写库、不发网络、不重算业务判定。
 * 候选链与尝试链的唯一所有者是 generation，采用记录与单图报告的唯一所有者是
 * selectionAdoption，Prompt 版本/编译的唯一所有者是 prompts；落库/派生/跨区渲染
 * 都经 deps 回到工作区。比较排序与默认目标由 domain/compare.js 决定，这里只投影。
 *
 * TypeScript 迁移（计划 §9 V2.R7.5）：本文件是唯一手工维护实现；同名 `compare-view.js`
 * 由 `npm run build:frontend` 生成，浏览器只消费生成的 `.js`。
 */
import {
  ATTEMPT_STATES,
  COMPARE_CONTRACT_VERSION,
  COMPARE_SEVERITY_TEXT,
  COMPARE_STATE_TEXT,
  REWORK_CONTRACT_VERSION,
  REWORK_PROBLEMS,
  attemptStateLabel,
  buildReworkDirective,
  compareCounts,
  compareRowHeadline,
  compareRows,
  defaultCompareTargetId,
  newActionId,
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
  appendTech,
  clearError,
  createElement,
  errorMessageOf,
  showError,
  techDetails,
} from "./dom.js";
import type { ActionSnapshot } from "../session.js";
import type { InputsModule } from "../project-inputs.js";
import type { PromptModule } from "../prompts.js";
import type {
  AttemptRecord,
  CompareRow,
  CompiledPrompt,
  PlanShot,
  ReviewFinding,
  ReviewReport,
  ReworkDirective,
  SelectionRecord,
  SelectionSet,
  SelectionState,
  SuitePlanSummary,
} from "../domain/type-contracts.js";
import type {
  AdoptionSource,
  SelectionAdoptionModule,
  SelectionEntry,
} from "../selection-adoption.js";
import type {
  ConfirmationQueue,
  GenerationModule,
  PromptEntry,
} from "../generation.js";

/** 本视图负责的审核三区 DOM 句柄（与 index.html 的 id 一一对应，由工作区一次装配）。 */
export type CompareElements = {
  comparePanel: HTMLElement;
  compareSubject: HTMLElement;
  compareJump: HTMLButtonElement;
  compareClose: HTMLButtonElement;
  compareBasisTitle: HTMLElement;
  compareReferences: HTMLElement;
  compareCandidates: HTMLElement;
  compareChecklist: HTMLElement;
  compareStatus: HTMLElement;
  compareViewedImage: HTMLImageElement;
  compareViewedCaption: HTMLElement;
  compareViewedZoom: HTMLButtonElement;
  compareBaselineImage: HTMLImageElement;
  compareBaselineSelect: HTMLSelectElement;
  compareBaselineZoom: HTMLButtonElement;
  compareReview: HTMLButtonElement;
  imageZoomDialog: HTMLDialogElement;
  imageZoomTitle: HTMLElement;
  imageZoomContent: HTMLImageElement;
  imageZoomNative: HTMLButtonElement;
  imageZoomClose: HTMLButtonElement;
  reworkOpen: HTMLButtonElement;
  reworkPanel: HTMLElement;
  reworkBasis: HTMLElement;
  reworkProblems: HTMLElement;
  reworkDirection: HTMLTextAreaElement;
  reworkPreview: HTMLButtonElement;
  reworkEdit: HTMLButtonElement;
  reworkSubmit: HTMLButtonElement;
  reworkReset: HTMLButtonElement;
  reworkCancel: HTMLButtonElement;
  reworkPreviewBox: HTMLElement;
  reworkPreviewMeta: HTMLElement;
  reworkPreviewText: HTMLElement;
  reworkTech: HTMLElement;
  reworkTechBody: HTMLElement;
  reworkSummary: HTMLElement;
  reworkStatus: HTMLElement;
  reworkError: HTMLElement;
  adoptOpen: HTMLButtonElement;
  adoptClear: HTMLButtonElement;
  adoptStatus: HTMLElement;
  adoptError: HTMLElement;
  adoptProgress: HTMLElement;
  reviewList: HTMLElement;
  reviewEmpty: HTMLElement;
};

/**
 * 窄依赖：审核面唯一所有者的命令/投影 + 工作区级收尾与跨区只读回调。
 * 不注入整个工作区；需要工作区状态的都经只读回调读取。
 * 候选预览 URL 缓存归工作区（比较/返工/尝试共用一份 object URL，关闭项目统一撤销）。
 */
export type CompareViewDeps = {
  inputs: InputsModule;
  prompts: PromptModule;
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
  /** 返工「查看/编辑全文」把 Prompt 列表与确认单切到最新（生成视图）。 */
  renderPrompts(): void;
  renderConfirm(): void;
  /** 生成视图的 Prompt 版本只读转发（返工落版经同一入口读，不持有第二份 Map）。 */
  promptRecordOf(shotId: string | null): PromptEntry | null;
  /** 把返工落版后的全文编辑区滚到可见并聚焦（Prompt 列表 DOM 归生成区）。 */
  focusPromptEditor(shotId: string): void;
  /** 参考图来源链的存在性核对（存储读归工作区）。 */
  readAsset(projectId: string, sha256: string): Promise<unknown>;
  /** 单图返工确认当前性判据（生成视图与整套同一实现）。 */
  queueShotIsCurrent(queue: ConfirmationQueue, shotId: string): boolean;
  /** 返工提交成功后的项目状态派生（工作区）。 */
  deriveState(): Promise<void>;
  /** 工作区级错误上报（比较区异步收尾用）。 */
  reportError(error: unknown): void;
  /** 有后缀的抛出信息；与生成区共用工作区同一实现。 */
  suffixedErrorMessage(error: unknown, fallback: string, suffix: string): string;
};

export type CompareView = {
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
  handleBaselineChange(): void;
  handleCompareReview(): Promise<void>;
  zoomViewed(): void;
  zoomBaseline(): void;
  closeImageZoom(): void;
  toggleZoomNative(): void;
  openReworkPanel(): void;
  previewRework(): Promise<void>;
  editRework(): Promise<void>;
  submitRework(): Promise<void>;
  resetRework(): void;
  cancelRework(): void;
  handleReworkKeydown(event: KeyboardEvent): void;
  handleReworkDirectionInput(): void;
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

/** 返工预览（previewRework 显式预览后产生；payload 是编译后请求载荷）。 */
export type CompareReworkPreview = {
  directive_id: string;
  payload: CompiledPrompt;
  references: number;
  text: string;
};

/** 返工草稿（按图内存态；预览/指令只在显式预览后产生，不自动生成）。 */
export type CompareReworkDraft = {
  problems: string[];
  direction: string;
  preview?: CompareReworkPreview | null;
  directive?: ReworkDirective | null;
};

/** 套图方案摘要里的单图形状（视图只读 shot_id/label/required，不重算方案）。 */
type SuiteShotSummary = SuitePlanSummary["shots"][number];

/**
 * 审核视图工厂。
 * @param args.elements 本视图负责的 DOM 句柄
 * @param args.deps 窄依赖：业务命令/投影 + 装配期注入的投影回调
 */
export function createCompareView(
  { elements, deps }: { elements: CompareElements; deps: CompareViewDeps },
): CompareView {
  const { inputs, generation, selectionAdoption, prompts } = deps;

  // 比较区就地状态：当前打开的图与候选、异步图片请求的代次、跨项目记忆、放大关闭后恢复焦点。
  let compareShotId: string | null = null;
  let compareCandidateId: string | null = null;
  let compareToken = 0;
  let compareImageToken = 0;
  let compareBaselineId: string | null = null;
  const compareViews = new Map<string, { candidateId: string | null; baselineId: string | null }>();
  let imageZoomReturnFocus: HTMLElement | null = null;
  // 返工区就地状态：草稿按图留在内存，预览只有用户确认时才落成版本。
  let reworkDrafts = new Map<string, CompareReworkDraft>();
  let reworkInFlight = false;
  let reworkShotId: string | null = null;
  let reworkSource: { shot_id: string; candidate_id: string; asset_sha256: string; version: number | null } | null = null;

  /** 套图摘要快照：审核列表与阶段无关的本地投影入口，不重算方案。 */
  function shotSummaries(): SuiteShotSummary[] {
    const plan = inputs.suitePlan();
    return plan ? suitePlanSummary(plan, inputs.suiteContext()).shots : [];
  }

  /**
   * 这张图的返工确认是否仍然有效：与整套确认同一套「快照逐字比对」判定，
   * 只是作用域只有这一张图——改别的图不会让它失效，改这张图一定会失效。
   */
  function reworkConfirmationIsCurrent(shotId: string): boolean {
    const entry = generation.reworkEntry(shotId);
    return Boolean(entry && deps.queueShotIsCurrent(entry, shotId));
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

  /**
   * 返工入口的状态：只有「正看着一条有字节的候选」才可发起。
   * 这里只投影 candidate_id + sha256，不写任何记录（写记录在相邻的独立返工区）。
   */
  function updateReworkEntry(shot: { shot_id: string } | null, row: CompareRow | null): void {
    const candidate = row && row.record ? row.record : null;
    const sha256 = row ? row.asset_sha256 : null;
    const available = Boolean(shot && candidate && sha256);
    elements.reworkOpen.disabled = !available;
    if (available && shot && row && candidate && sha256) {
      elements.reworkOpen.dataset.shotId = shot.shot_id;
      elements.reworkOpen.dataset.candidateId = row.candidate_id;
      elements.reworkOpen.dataset.candidateSha256 = sha256;
    } else {
      delete elements.reworkOpen.dataset.shotId;
      delete elements.reworkOpen.dataset.candidateId;
      delete elements.reworkOpen.dataset.candidateSha256;
    }
  }

  function openCompare(shotId: string, options: { candidateId?: string | null; focus?: boolean } = {}): void {
    compareShotId = shotId;
    const previous = compareViews.get(deps.currentProjectId() + ":" + shotId);
    compareCandidateId = options.candidateId || previous?.candidateId || null;
    compareBaselineId = previous?.baselineId || null;
    deps.selectStage("review");
    renderCompare();
    if (options.focus === true) {
      const active = elements.compareCandidates.querySelector<HTMLButtonElement>('[role="tab"][aria-selected="true"]');
      if (active) active.focus();
    }
  }

  function closeCompare(): void {
    compareShotId = null;
    compareCandidateId = null;
    renderCompare();
  }

  function isComparing(shotId: string): boolean {
    return compareShotId === shotId;
  }

  /** 切换查看目标：不改规则、不写存储，只换清单与 aria 选中态，避免重建列表时丢焦点。 */
  function selectCompareCandidate(candidateId: string | null, options: { focus?: boolean } = {}): void {
    // 换一条候选时收起返工区（它绑定打开那一刻的候选身份），草稿保留。
    if (reworkShotId !== null && candidateId !== compareCandidateId) {
      closeReworkPanel({ focusCandidate: false });
    }
    compareCandidateId = candidateId;
    const tabs = elements.compareCandidates.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    for (const tab of tabs) {
      const selected = tab.dataset.candidateId === candidateId;
      tab.setAttribute("aria-selected", selected ? "true" : "false");
      tab.tabIndex = selected ? 0 : -1;
      if (selected && options.focus === true) tab.focus();
    }
    const inventory = compareInventory();
    const shotId = compareShotId;
    if (!shotId) return;
    const rows = inventory.rowsByShotId[shotId] || [];
    const shot = (inputs.suitePlan()?.shots || [])
      .find((item) => item && item.shot_id === shotId) || null;
    const row = rows.find((item) => item.candidate_id === candidateId) || null;
    renderCompareChecklist(shot, row);
    updateReworkEntry(shot, row);
    updateAdoptEntry(shot, row);
    elements.compareStatus.textContent = "";
    void renderCompareImages(rows);
    if (shot) void refreshCompareReferences(shot).catch(deps.reportError);
  }

  function renderCompare(): void {
    const ready = Boolean(inputs.suitePlan());
    if (!ready || !compareShotId) {
      elements.comparePanel.hidden = true;
      elements.compareCandidates.innerHTML = "";
      elements.compareChecklist.innerHTML = "";
      elements.compareReferences.innerHTML = "";
      elements.compareBasisTitle.textContent = "";
      closeReworkPanel({ focusCandidate: false });
      updateReworkEntry(null, null);
      updateAdoptEntry(null, null);
      return;
    }
    const shotId = compareShotId;
    const shot = (inputs.suitePlan()?.shots || [])
      .find((item) => item && item.shot_id === shotId) || null;
    if (!shot) {
      compareShotId = null;
      renderCompare();
      return;
    }
    const inventory = compareInventory();
    const rows = inventory.rowsByShotId[shotId] || [];
    if (!rows.length) {
      compareShotId = null;
      renderCompare();
      return;
    }
    const targetId = rows.some((row) => row.candidate_id === compareCandidateId)
      ? compareCandidateId : defaultCompareTargetId(rows);
    compareCandidateId = targetId;
    elements.comparePanel.dataset.compareContract = COMPARE_CONTRACT_VERSION;
    elements.comparePanel.dataset.shotId = shotId;
    elements.comparePanel.hidden = false;
    const counts = compareCounts(rows);
    const parts = ["候选 " + counts.total];
    if (counts.pending) parts.push("待处理 " + counts.pending);
    if (counts.unknown) parts.push("未知 " + counts.unknown);
    if (counts.unchecked) parts.push("未检查 " + counts.unchecked);
    elements.compareSubject.textContent = deps.shotLabelOf(shotId) + " · " + parts.join(" · ");
    const nextShot = nextPendingShotId({
      rowsByShotId: inventory.rowsByShotId,
      shotOrder: inventory.shots.map((item) => item.shot_id),
      currentShotId: shotId,
    });
    elements.compareJump.disabled = !nextShot;
    elements.compareJump.dataset.targetShot = nextShot || "";
    elements.compareStatus.textContent = "";
    renderCompareCandidates(rows, targetId);
    const targetRow = rows.find((row) => row.candidate_id === targetId) || null;
    renderCompareChecklist(shot, targetRow);
    updateReworkEntry(shot, targetRow);
    void renderCompareImages(rows);
    updateAdoptEntry(shot, targetRow);
    void refreshCompareReferences(shot).catch(deps.reportError);
  }

  function rememberCompareView(): void {
    const projectId = deps.currentProjectId();
    if (projectId && compareShotId) compareViews.set(projectId + ":" + compareShotId, {
      candidateId: compareCandidateId, baselineId: compareBaselineId,
    });
  }

  async function renderCompareImages(rows: CompareRow[]): Promise<void> {
    const token = ++compareImageToken;
    const viewed = rows.find(row => row.candidate_id === compareCandidateId);
    const comparison = rows.find(row => row.candidate_id === compareBaselineId);
    if (!comparison || comparison.candidate_id === compareCandidateId) compareBaselineId = null;
    const select = elements.compareBaselineSelect;
    select.replaceChildren(createElement("option", { text: "不指定对照", attrs: { value: "" } }));
    for (const row of rows) {
      if (row.candidate_id === compareCandidateId) continue;
      const current = compareShotId;
      select.append(createElement("option", {
        text: "候选 v" + row.version + (current && adoptedMarkOf(current)?.candidate_id === row.candidate_id ? " · 已采用" : ""),
        attrs: { value: row.candidate_id },
      }));
    }
    select.value = compareBaselineId || "";
    rememberCompareView();
    const currentShot = compareShotId;
    const adopted = currentShot ? adoptedMarkOf(currentShot) : null;
    elements.compareViewedCaption.textContent = "当前查看：候选 v" + (viewed?.version || "?")
      + (adopted?.candidate_id === compareCandidateId ? " · 已采用" : " · 未采用此候选")
      + "；查看和对照不会改选。";
    const reviewShotId = compareShotId;
    elements.compareReview.disabled = !viewed || !reviewShotId || selectionAdoption.isReviewInFlight(reviewShotId);
    for (const { row, image, zoom } of [
      { row: viewed, image: elements.compareViewedImage, zoom: elements.compareViewedZoom },
      { row: compareBaselineId ? comparison : null, image: elements.compareBaselineImage, zoom: elements.compareBaselineZoom },
    ]) {
      image.hidden = true; image.removeAttribute("src"); zoom.disabled = true;
      if (!row) continue;
      const url = await deps.ensurePreviewUrl(row.shot_id, row.candidate_id, row.asset_sha256);
      if (token !== compareImageToken) return;
      if (!url) { elements.compareStatus.textContent = "候选字节缺失；请恢复项目包，不会用另一张图片替代。"; continue; }
      image.src = url; image.hidden = false; image.dataset.candidateId = row.candidate_id;
      zoom.disabled = false;
    }
  }

  function openImageZoom(src: string, label: string): void {
    if (!src) return;
    imageZoomReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    elements.imageZoomContent.src = src;
    elements.imageZoomContent.alt = label;
    elements.imageZoomContent.classList.remove("at-native-size");
    elements.imageZoomTitle.textContent = label;
    elements.imageZoomNative.textContent = "100% 像素";
    elements.imageZoomDialog.showModal();
    elements.imageZoomClose.focus();
  }

  function closeImageZoom(): void {
    elements.imageZoomDialog.close();
    elements.imageZoomContent.removeAttribute("src");
    if (imageZoomReturnFocus?.isConnected) imageZoomReturnFocus.focus();
  }

  function zoomViewed(): void {
    openImageZoom(elements.compareViewedImage.src, elements.compareViewedCaption.textContent || "");
  }

  function zoomBaseline(): void {
    openImageZoom(elements.compareBaselineImage.src, "对照候选（不改变采用）");
  }

  function toggleZoomNative(): void {
    const native = elements.imageZoomContent.classList.toggle("at-native-size");
    elements.imageZoomNative.textContent = native ? "适应窗口" : "100% 像素";
  }

  function renderCompareCandidates(rows: CompareRow[], targetId: string | null): void {
    const list = elements.compareCandidates;
    list.innerHTML = "";
    for (const row of rows) {
      const card = createElement("button", {
        className: "compare-card",
        attrs: {
          type: "button", role: "tab", id: compareTabId(row.candidate_id),
          "aria-selected": row.candidate_id === targetId ? "true" : "false",
          "aria-controls": "compare-checklist",
          "data-candidate-id": row.candidate_id,
          "data-review-state": row.review_state,
          tabindex: row.candidate_id === targetId ? "0" : "-1",
        },
      });
      const thumb = createElement("img", {
        attrs: { alt: "候选 v" + (row.version || "?") + " 预览", loading: "lazy" },
      });
      deps.ensurePreviewUrl(row.shot_id, row.candidate_id, row.asset_sha256).then((url) => {
        if (url && card.isConnected) thumb.setAttribute("src", url);
      }).catch(() => {});
      card.append(thumb);
      const main = createElement("div", { className: "compare-card-main" });
      const head = createElement("div", { className: "compare-card-head" });
      head.append(createElement("span", {
        className: "name", text: "候选 v" + (row.version === null ? "?" : row.version),
      }));
      head.append(createElement("span", {
        className: "badge " + (COMPARE_STATE_BADGE[row.review_state] || "is-review-unchecked"),
        text: compareStateLabel(row),
      }));
      const adopted = compareShotId ? adoptedMarkOf(compareShotId) : null;
      if (adopted && adopted.candidate_id === row.candidate_id) {
        head.append(createElement("span", {
          className: "badge is-adopted",
          attrs: { "data-adopted": adopted.state },
          text: adopted.state === "current" ? "已采用" : "已采用（已过期）",
        }));
      }
      main.append(head);
      const business = [];
      if (row.width && row.height) business.push(row.width + "×" + row.height);
      if (row.created_at) business.push(deps.shortTime(row.created_at));
      main.append(createElement("span", { className: "meta", text: business.join(" · ") }));
      main.append(createElement("p", { className: "compare-headline", text: compareRowHeadline(row) }));
      card.append(main);
      card.addEventListener("click", () => { selectCompareCandidate(row.candidate_id); });
      // tablist 的直接子节点必须是 tab；技术详情放在右侧 tabpanel 的清单底部，
      // 既不嵌套交互控件，也不破坏 tabs 语义。
      list.append(card);
    }
  }

  function compareFindingRow(finding: ReviewFinding): HTMLLIElement {
    const item = createElement("li", {
      className: "compare-finding",
      attrs: { "data-severity": finding.severity, "data-rule-id": finding.rule_id },
    });
    const head = createElement("div", { className: "compare-card-head" });
    head.append(createElement("span", {
      className: "badge " + (SEVERITY_BADGE[finding.severity] || "is-review-unknown"),
      text: COMPARE_SEVERITY_TEXT[finding.severity] || finding.severity,
    }));
    head.append(createElement("span", { className: "name", text: finding.title }));
    head.append(createElement("span", {
      className: "meta", text: finding.rule_id + " · v" + finding.rule_version,
    }));
    item.append(head);
    item.append(createElement("p", { className: "meta", text: finding.detail }));
    if (finding.measured !== null && finding.measured !== undefined) {
      item.append(createElement("p", {
        className: "meta", text: "实测：" + JSON.stringify(finding.measured).slice(0, 160),
      }));
    }
    return item;
  }

  /** 审核清单 = 当前候选的待处理发现（异常优先）+ 这张图的验收依据 + 按需展开的完整报告。 */
  function renderCompareChecklist(shot: PlanShot | null, row: CompareRow | null): void {
    const box = elements.compareChecklist;
    box.innerHTML = "";
    box.setAttribute("aria-labelledby", row ? compareTabId(row.candidate_id) : "compare-title");
    if (!row) {
      box.append(createElement("p", { className: "meta", text: "先选择一个候选。" }));
      return;
    }
    box.dataset.compareState = row.review_state;
    box.dataset.candidateId = row.candidate_id;
    const report = row.report;
    if (report) {
      const findings = sortFindings(report.findings);
      const actionable = findings.filter((item) => item.severity !== "PASS");
      if (actionable.length) {
        box.append(createElement("h5", { text: "先看这些（" + actionable.length + "）" }));
        const list = createElement("ul", { className: "compare-findings" });
        for (const finding of actionable) list.append(compareFindingRow(finding));
        box.append(list);
      } else {
        // 没有待处理项时，这里一句话说明状态就够；细节在完整报告里。
        box.append(createElement("p", {
          className: "meta", text: compareRowHeadline(row),
        }));
      }
      const details = createElement("details", { className: "compare-report" });
      details.append(createElement("summary", {
        text: "完整报告（合同 " + report.review_contract_version + " · " + findings.length + " 条）",
      }));
      details.append(createElement("p", {
        className: "compare-report-row",
        text: "候选 sha256 " + String(row.asset_sha256).slice(0, 16) + "… · 报告生成 "
          + deps.shortTime(report.created_at),
      }));
      const vlm = report.vlm;
      const vlmText = vlm
        ? (vlm.outcome === "checked" ? "已完成" : "未完成（结果未知，不阻断人工审核）")
        : "未复核（未运行，未发起 AI 复核；不阻断人工采用）";
      details.append(createElement("p", {
        className: "compare-report-row",
        attrs: { "data-compare-vlm": vlm ? vlm.outcome : "not_run" },
        text: "视觉复核（按需发起）：" + vlmText + (vlm && vlm.model_id ? " · " + vlm.model_id : ""),
      }));
      const all = createElement("ul", { className: "compare-findings" });
      for (const finding of findings) all.append(compareFindingRow(finding));
      details.append(all);
      box.append(details);
    } else {
      box.append(createElement("p", { className: "meta", text: compareRowHeadline(row) }));
    }
    box.append(createElement("h5", { text: "这张图的验收依据" }));
    if (!shot) return;
    const specEntry = inputs.shotSpecEntry(shot.shot_id);
    const checklist = reviewChecklist(shot, {
      shotSpec: specEntry ? specEntry.spec : null, styleSpec: inputs.styleSpec(),
    });
    const criteria = createElement("ul", { className: "compare-basis-list" });
    criteria.append(createElement("li", { text: "目的：" + checklist.purpose }));
    if (checklist.must_keep.length) {
      criteria.append(createElement("li", { text: "必须保持：" + checklist.must_keep.join("；") }));
    }
    if (checklist.may_change.length) {
      criteria.append(createElement("li", { text: "允许变化：" + checklist.may_change.join("；") }));
    }
    if (checklist.style_lines.length) {
      criteria.append(createElement("li", { text: "公共风格：" + checklist.style_lines.join("；") }));
    }
    if (!checklist.saved) {
      criteria.append(createElement("li", {
        className: "meta", text: "单图规格尚未保存，这里用的是默认派生值。",
      }));
    }
    box.append(criteria);
    const techLines = [
      "candidate " + String(row.candidate_id),
      "sha256 " + String(row.asset_sha256).slice(0, 12) + "…",
    ];
    if (row.task_id) techLines.push("task " + String(row.task_id).slice(0, 8));
    else if (row.attempt_action_id) techLines.push("action " + String(row.attempt_action_id).slice(0, 8));
    const tech = techDetails(techLines);
    if (tech) box.append(tech);
  }

  /** 这张图实际会发送的参考图（与提交时同一选择函数），用作比较的左边一栏。 */
  async function refreshCompareReferences(shot: PlanShot): Promise<void> {
    const token = ++compareToken;
    const pid = deps.currentProjectId();
    const viewed = adoptSourceOf(shot.shot_id, compareCandidateId)?.candidate;
    const origin = viewed ? attemptsByActionId()[viewed.action_id] : null;
    const references = origin?.references || [];
    const entries: Array<{ reference: { sha256: string; role: string }; asset: unknown }> = [];
    for (const reference of references) {
      if (!pid) continue;
      const asset = await deps.readAsset(pid, reference.sha256);
      entries.push({ reference, asset });
    }
    if (token !== compareToken || pid !== deps.currentProjectId()) return;
    const list = elements.compareReferences;
    list.innerHTML = "";
    if (!entries.length) {
      elements.compareBasisTitle.textContent = "找不到当前候选的原参考图来源链；不会用当前新资料冒充原图。";
      return;
    }
    elements.compareBasisTitle.textContent = "当前候选原任务参考图（" + entries.length + " 张）；均按原比例展示。";
    for (const entry of entries) {
      const item = createElement("li", { attrs: { "data-reference-sha256": entry.reference.sha256 } });
      const url = await deps.ensurePreviewUrl("参考图", entry.reference.sha256, entry.reference.sha256);
      if (token !== compareToken) return;
      if (url) {
        item.append(createElement("img", {
          attrs: { src: url, alt: "参考图 " + entry.reference.role, loading: "lazy" },
        }));
        const zoom = createElement("button", { text: "放大参考原图", attrs: { type: "button" } });
        zoom.addEventListener("click", () => openImageZoom(url, "参考原图 · " + (ROLE_TEXT[entry.reference.role] || entry.reference.role)));
        item.append(zoom);
      } else {
        item.append(createElement("span", { className: "meta", text: "资产缺失" }));
      }
      item.append(createElement("span", {
        className: "meta", text: ROLE_TEXT[entry.reference.role] || entry.reference.role,
      }));
      appendTech(item, ["sha256 " + String(entry.reference.sha256).slice(0, 8) + "…"]);
      list.append(item);
    }
  }

  function handleCompareKeydown(event: KeyboardEvent): void {
    const tabs = Array.from(elements.compareCandidates.querySelectorAll<HTMLButtonElement>('[role="tab"]'));
    if (!tabs.length) return;
    const current = tabs.findIndex((tab) => tab.getAttribute("aria-selected") === "true");
    const index = current === -1 ? 0 : current;
    let next: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") next = (index + 1) % tabs.length;
    else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      next = (index - 1 + tabs.length) % tabs.length;
    } else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else if (event.key === "Escape") {
      event.preventDefault();
      deps.focusReviewEntry(compareShotId);
      return;
    } else {
      return;
    }
    event.preventDefault();
    if (next === null) return;
    selectCompareCandidate(tabs[next]?.dataset.candidateId ?? null, { focus: true });
  }

  function handleBaselineChange(): void {
    compareBaselineId = elements.compareBaselineSelect.value || null;
    void renderCompareImages(compareShotId ? compareInventory().rowsByShotId[compareShotId] || [] : []);
  }

  /** 单图 AI 复核（按需发起）：只响应用户显式点击；查看/切换/采用不调用此函数。
   * 未运行如实记 not_run（reviewStatusOf 投影），不折叠成 Unknown、不进 ack 门。 */
  async function handleCompareReview(): Promise<void> {
    const shotId = compareShotId, candidateId = compareCandidateId;
    if (!shotId || !candidateId) return;
    const outcome = await selectionAdoption.reviewCandidate(shotId, candidateId);
    if (shotId === compareShotId && candidateId === compareCandidateId) {
      renderCompare();
      elements.compareStatus.textContent = outcome?.failed ? "AI 复核未完成：" + outcome.message + "（真实失败才记 Unknown，未发起仍是未复核）" : "复核结果只属于所点击的这条候选，不自动采用；未复核不阻断人工采用。";
    }
  }

  /* --------------------------------------------- 单图返工闭环（V2.5.4） */

  /**
   * 返工区与比较区相邻但独立：比较区只投影、只读；这里才写 Prompt 版本、
   * 单图确认与新的生成尝试。草稿按图留在内存，预览只有用户确认时才落成版本。
   * 返工草稿按图保存；第一次打开时用报告的先看项预选问题与方向，之后保留用户改动。
   */
  function reworkDraftOf(shotId: string, row: CompareRow | null): CompareReworkDraft {
    let draft = reworkDrafts.get(shotId);
    if (!draft) {
      draft = {
        problems: suggestReworkProblems(row ? row.report : null),
        direction: suggestedReworkDirection(row ? row.report : null),
        directive: null,
        preview: null,
      };
      reworkDrafts.set(shotId, draft);
    }
    return draft;
  }

  function reworkShotRow(shotId: string, candidateId: string | null): CompareRow | null {
    const inventory = compareInventory();
    const rows = inventory.rowsByShotId[shotId] || [];
    return rows.find((item) => item.candidate_id === candidateId) || rows[0] || null;
  }

  function reworkSummaryOf(draft: CompareReworkDraft | null): string {
    if (draft && draft.preview) {
      return "预览已就绪：确认并生成会把它保存为 Prompt 新版本（旧版本保留），"
        + "只重新生成这张图；改过问题或方向后需要重新预览。";
    }
    return "选好问题或写下方向 → 预览返工 Prompt → 确认并生成这张图。";
  }

  function updateReworkControls(shotId: string | null, draft: CompareReworkDraft | null): void {
    if (!draft) return;
    const hasReason = draft.problems.length > 0
      || String(elements.reworkDirection.value || "").trim().length > 0;
    const busy = reworkInFlight;
    elements.reworkPreview.disabled = busy || !hasReason;
    elements.reworkEdit.disabled = busy || !draft.preview;
    elements.reworkSubmit.disabled = busy || !draft.preview;
    elements.reworkReset.disabled = busy;
    elements.reworkCancel.disabled = busy;
    elements.reworkSummary.textContent = reworkSummaryOf(draft);
  }

  /** 输入变了：旧预览不再代表将要发送的内容，必须重新预览。 */
  function dirtyReworkDraft(draft: CompareReworkDraft | null): void {
    if (!draft || !draft.preview) return;
    draft.preview = null;
    draft.directive = null;
    elements.reworkPreviewBox.hidden = true;
    elements.reworkStatus.hidden = true;
  }

  function renderReworkPreviewBox(draft: CompareReworkDraft | null): void {
    if (!draft || !draft.preview) {
      elements.reworkPreviewBox.hidden = true;
      return;
    }
    elements.reworkPreviewBox.hidden = false;
    elements.reworkPreviewMeta.textContent =
      "将保存为 Prompt 新版本（旧版本保留）并只重新生成这张图 · 参考图 "
      + draft.preview.references + " 张 · 全文 " + draft.preview.text.length + " 字";
    elements.reworkPreviewText.textContent = draft.preview.text;
  }

  function renderReworkProblems(shotId: string, draft: CompareReworkDraft): void {
    const box = elements.reworkProblems;
    const host = (box.querySelector(".rework-problem-options") as HTMLElement | null) || box;
    for (const node of Array.from(host.querySelectorAll("label.rework-problem"))) node.remove();
    for (const problem of REWORK_PROBLEMS) {
      const label = createElement("label", {
        className: "check rework-problem",
        attrs: { title: problem.hint, "data-problem-id": problem.id },
      });
      const input = createElement("input", {
        attrs: { id: "rework-problem-" + problem.id, type: "checkbox", value: problem.id },
      });
      input.checked = draft.problems.indexOf(problem.id) >= 0;
      input.addEventListener("change", () => {
        if (input.checked) {
          if (draft.problems.indexOf(problem.id) === -1) {
            draft.problems = draft.problems.concat([problem.id]);
          }
        } else {
          draft.problems = draft.problems.filter((id) => id !== problem.id);
        }
        dirtyReworkDraft(draft);
        updateReworkControls(shotId, draft);
      });
      label.append(input, document.createTextNode(" " + problem.label));
      host.append(label);
    }
  }

  /** 入口：把当前正看着的候选（candidate_id + sha256）交给返工表单；只改内存状态。 */
  function openReworkPanel(): void {
    const shotId = elements.reworkOpen.dataset.shotId || compareShotId;
    const candidateId = elements.reworkOpen.dataset.candidateId || compareCandidateId;
    if (!shotId || !candidateId || reworkInFlight) return;
    const row = reworkShotRow(shotId, candidateId);
    if (!row || !row.record) {
      elements.compareStatus.textContent = "这条候选已经不在了，先重新选择候选。";
      return;
    }
    reworkShotId = shotId;
    reworkSource = {
      shot_id: shotId, candidate_id: row.candidate_id, asset_sha256: row.asset_sha256,
      version: row.version === null || row.version === undefined ? null : row.version,
    };
    const draft = reworkDraftOf(shotId, row);
    const panel = elements.reworkPanel;
    panel.hidden = false;
    panel.dataset.reworkContract = REWORK_CONTRACT_VERSION;
    panel.dataset.shotId = shotId;
    panel.dataset.candidateId = row.candidate_id;
    const basis = ["返工依据：候选 v" + (reworkSource.version === null ? "?" : reworkSource.version)];
    if (row.top_finding) basis.push("先看：" + row.top_finding.title);
    if (reworkConfirmationIsCurrent(shotId)) basis.push("这张图的返工确认仍然有效");
    elements.reworkBasis.textContent = basis.join(" · ");
    if (elements.reworkTech && elements.reworkTechBody) {
      elements.reworkTech.hidden = false;
      elements.reworkTechBody.textContent = "sha256 "
        + String(reworkSource.asset_sha256).slice(0, 12) + "… · candidate " + row.candidate_id;
    }
    renderReworkProblems(shotId, draft);
    if (elements.reworkDirection.value !== draft.direction) {
      elements.reworkDirection.value = draft.direction;
    }
    renderReworkPreviewBox(draft);
    elements.reworkStatus.hidden = true;
    clearError(elements.reworkError);
    updateReworkControls(shotId, draft);
    const first = elements.reworkProblems.querySelector<HTMLInputElement>('input[type="checkbox"]');
    if (first) first.focus();
    panel.scrollIntoView({ block: "nearest" });
  }

  /** 收起返工区：清掉未确认的预览；草稿（问题与方向）按图保留。 */
  function closeReworkPanel({ focusCandidate = false }: { focusCandidate?: boolean } = {}): void {
    const shotId = reworkShotId;
    const candidateId = reworkSource ? reworkSource.candidate_id : null;
    reworkShotId = null;
    reworkSource = null;
    elements.reworkPanel.hidden = true;
    elements.reworkPreviewBox.hidden = true;
    elements.reworkStatus.hidden = true;
    clearError(elements.reworkError);
    const draft = shotId ? reworkDrafts.get(shotId) : null;
    if (draft) {
      draft.preview = null;
      draft.directive = null;
    }
    if (focusCandidate && shotId) focusCompareCandidate(shotId, candidateId);
  }

  /** 收起后把焦点还给原候选：比较区还在就回到候选页签，否则回到该图的比较入口。 */
  function focusCompareCandidate(shotId: string, candidateId: string | null): void {
    const tab = candidateId ? elements.compareCandidates.querySelector<HTMLButtonElement>(
      '[role="tab"][data-candidate-id="' + candidateId + '"]') : null;
    if (tab) {
      tab.focus();
      return;
    }
    deps.focusReviewEntry(shotId);
  }

  /** 按建议重填：问题与方向回到报告先看项的默认值，预览作废。 */
  function resetRework(): void {
    const shotId = reworkShotId;
    if (!shotId || reworkInFlight) return;
    const row = reworkShotRow(shotId, reworkSource ? reworkSource.candidate_id : null);
    reworkDrafts.delete(shotId);
    const draft = reworkDraftOf(shotId, row);
    renderReworkProblems(shotId, draft);
    if (elements.reworkDirection.value !== draft.direction) {
      elements.reworkDirection.value = draft.direction;
    }
    elements.reworkPreviewBox.hidden = true;
    elements.reworkStatus.hidden = true;
    clearError(elements.reworkError);
    updateReworkControls(shotId, draft);
  }

  function cancelRework(): void {
    if (reworkInFlight) return;
    closeReworkPanel({ focusCandidate: true });
  }

  function handleReworkKeydown(event: KeyboardEvent): void {
    if (event.key === "Escape") {
      event.preventDefault();
      cancelRework();
    }
  }

  function handleReworkDirectionInput(): void {
    const shotId = reworkShotId;
    const draft = shotId ? reworkDrafts.get(shotId) : null;
    if (!draft) return;
    draft.direction = elements.reworkDirection.value;
    dirtyReworkDraft(draft);
    updateReworkControls(shotId, draft);
  }

  /** 预览：按当前问题与方向编译一次；只显示，不写记录。 */
  async function previewRework(): Promise<void> {
    if (!deps.currentProjectId() || !reworkShotId || reworkInFlight) return;
    const shotId = reworkShotId;
    clearError(elements.reworkError);
    const row = reworkShotRow(shotId, reworkSource ? reworkSource.candidate_id : null);
    if (!row || !row.record) {
      showError(elements.reworkError, "返工依据已经不在，先回到比较区重新选择候选。");
      return;
    }
    const draft = reworkDraftOf(shotId, row);
    draft.direction = elements.reworkDirection.value;
    reworkInFlight = true;
    updateReworkControls(shotId, draft);
    try {
      const directive = buildReworkDirective({
        directiveId: newActionId(),
        shotId: shotId,
        candidate: row.record,
        report: row.report,
        problems: draft.problems,
        direction: draft.direction,
        at: new Date().toISOString(),
      });
      const result = await prompts.compile(shotId, { rework: directive });
      draft.directive = directive;
      draft.preview = {
        directive_id: directive.directive_id,
        payload: result.compiled,
        references: result.references.length,
        text: result.compiled.text,
      };
      renderReworkPreviewBox(draft);
      elements.reworkStatus.hidden = false;
      elements.reworkStatus.textContent = "预览已就绪：确认并生成时会先把它保存为新版本，"
        + "再只提交这一张图；预览本身没有写入任何记录。";
    } catch (error) {
      showError(elements.reworkError, deps.suffixedErrorMessage(error, "预览没有生成，旧版本与输入保留。", "（预览未生成，旧版本与输入保留）"));
    } finally {
      reworkInFlight = false;
      const current = reworkDrafts.get(shotId);
      if (current) updateReworkControls(shotId, current);
    }
  }

  /** 查看/编辑完整 Prompt：把这次预览落成版本，再把焦点交给这张图的人工编辑区。 */
  async function editRework(): Promise<void> {
    if (!deps.currentProjectId() || !reworkShotId || reworkInFlight) return;
    const shotId = reworkShotId;
    const draft = reworkDrafts.get(shotId);
    clearError(elements.reworkError);
    if (!draft || !draft.preview) {
      showError(elements.reworkError, "先预览返工 Prompt，再查看或编辑全文。");
      return;
    }
    reworkInFlight = true;
    updateReworkControls(shotId, draft);
    try {
      const latest = deps.promptRecordOf(shotId) || null;
      let version = latest ? latest.version : 0;
      const fromPreview = Boolean(latest && latest.record.compiled.rework
        && latest.record.compiled.rework.directive_id === draft.preview.directive_id);
      if (!fromPreview) {
        if (!draft.directive) throw new Error("先预览返工 Prompt，再查看或编辑全文。");
        const saved = await prompts.compileAndSave(shotId, { rework: draft.directive });
        version = saved.saved.version;
      }
      deps.renderPrompts();
      deps.renderConfirm();
      deps.focusPromptEditor(shotId);
      elements.reworkStatus.hidden = false;
      elements.reworkStatus.textContent = "已保存为 Prompt v" + version
        + "；可以在下方「Prompt 预览与版本」里编辑全文并另存新版本。";
    } catch (error) {
      showError(elements.reworkError, errorMessageOf(error, "没有打开编辑区。"));
    } finally {
      reworkInFlight = false;
      const current = reworkDrafts.get(shotId);
      if (current) updateReworkControls(shotId, current);
    }
  }

  /**
   * 确认并生成这张图：先确保这次返工已经落成 Prompt 版本（发送的永远是这张图最新的版本），
   * 再写「只覆盖这张图」的确认记录、新建 Attempt 并核对一次结论；失败不影响旧候选。
   */
  async function submitRework(): Promise<void> {
    if (!deps.currentProjectId() || !reworkShotId || reworkInFlight) return;
    const action = deps.beginAction();
    const shotId = reworkShotId;
    const sourceCandidateId = reworkSource ? reworkSource.candidate_id : null;
    const draft = reworkDrafts.get(shotId);
    clearError(elements.reworkError);
    if (!draft || !draft.preview || !draft.directive) {
      showError(elements.reworkError, "先预览返工 Prompt，再确认生成。");
      return;
    }
    reworkInFlight = true;
    updateReworkControls(shotId, draft);
    try {
      const latest = deps.promptRecordOf(shotId) || null;
      let promptVersion = latest ? latest.version : 0;
      const fromPreview = Boolean(latest && latest.record.compiled.rework
        && latest.record.compiled.rework.directive_id === draft.preview.directive_id);
      if (!fromPreview) {
        if (!draft.directive) throw new Error("先预览返工 Prompt，再确认生成。");
        const saved = await prompts.compileAndSave(shotId, { rework: draft.directive, action });
        promptVersion = saved.saved.version;
      }
      if (!action.alive()) return;
      // 所见摘要由 generation 准备（授权文档/所见版本/返工 scope 都在 owner 内部）；
      // 视图只保存并原样交回，提交前不重算、不猜版本，也不决定持久化与外发的先后。
      const intent = generation.reworkIntent(shotId);
      const result = await generation.confirmAndRun({ intent });
      if (!action.alive()) return;
      if (result.stale) {
        // owner 已算出新摘要且零外发：只呈现，不自动确认、不自动重提。
        const fresh = result.intent?.sheet?.external_summary?.statement || "";
        showError(elements.reworkError,
          (result.message || "摘要已变化；请核对新摘要后再确认返工。") + (fresh ? "当前摘要：" + fresh : ""));
        return;
      }
      const latestAttempt = generation.latestAttemptOf(shotId);
      const state = latestAttempt ? latestAttempt.record.state : null;
      draft.directive = null;
      draft.preview = null;
      reworkShotId = null;
      reworkSource = null;
      elements.reworkPanel.hidden = true;
      elements.reworkPreviewBox.hidden = true;
      elements.reworkStatus.hidden = true;
      deps.renderAttempts();
      await deps.deriveState();
      focusCompareCandidate(shotId, sourceCandidateId);
      elements.compareStatus.textContent = "返工已提交（Prompt v" + promptVersion + " · "
        + attemptStateLabel(state) + "）；旧候选保留，只有这张图新增了版本。";
      // 与生成区单张提交同一语义：unknown 成功返回也要如实提示定位（只增显示调用，不改控制流与返回）。
      if (state === ATTEMPT_STATES.unknown) {
        const noTaskId = !latestAttempt || !latestAttempt.record.task_id;
        deps.showAttemptError("这次返工提交的结果没有确认：不要重复提交。"
          + (noTaskId ? "没有任务编号，只能显式新建 action。" : "可以按任务编号核对。"));
      }
    } catch (error) {
      if (action.alive()) {
        showError(elements.reworkError,
          errorMessageOf(error, "返工没有提交；旧候选与旧 Prompt 不受影响。"));
      }
    } finally {
      if (action.alive()) {
        reworkInFlight = false;
        const current = reworkDrafts.get(shotId);
        if (current) updateReworkControls(shotId, current);
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
  function renderSelectionProgress(): void {
    if (!inputs.suitePlan()) {
      elements.adoptProgress.textContent = "";
      return;
    }
    const set = selectionAdoption.projection(inputs.sources()).set;
    elements.adoptProgress.textContent = set.summary.required_total > 0
      ? selectionSetText(set) + "采用只引用候选（candidate_id + sha256），不复制图片。"
      : "";
  }

  /** 比较区入口的状态：只投影候选身份，不写任何记录（写记录在相邻的独立采用区）。 */
  function updateAdoptEntry(shot: { shot_id: string } | null, row: CompareRow | null): void {
    const available = Boolean(shot && row && row.record && row.record.asset_sha256);
    const selected = shot ? selectionAdoption.entryOf(shot.shot_id)?.record || null : null;
    const already = Boolean(selected && selected.action === "select" && row
      && selected.candidate_id === row.candidate_id
      && shot && selectionAdoption.stateOf(shot.shot_id) === "current");
    elements.adoptOpen.disabled = !available || already;
    elements.adoptClear.disabled = !selected || selected.action !== "select";
  }

  /** 采用目标：把「正看着的候选」解析成候选记录 + 文档版本 + 当前审核报告。 */
  function adoptSourceOf(shotId: string | null, candidateId: string | null): AdoptionSource | null {
    return selectionAdoption.sourceOf(shotId, candidateId);
  }

  function selectionTextOf(shotId: string): string {
    return selectionAdoption.summary(shotId);
  }

  /** One explicit human action. Identity freezes before any byte read; selection is append-only/OCC. */
  async function adoptCandidate(kind: "select" | "clear", shotId: string | null = compareShotId,
    candidateId: string | null = compareCandidateId): Promise<void> {
    if (!deps.currentProjectId() || !shotId || selectionAdoption.isSelecting()) return;
    const action = deps.beginAction();
    clearError(elements.adoptError);
    elements.adoptStatus.hidden = false;
    elements.adoptStatus.textContent = "正在保存 " + deps.shotLabelOf(shotId) + " 的人工选择…";
    try {
      await selectionAdoption.select(kind, shotId, candidateId);
      if (!action.alive()) return;
      elements.adoptStatus.textContent = deps.shotLabelOf(shotId)
        + (kind === "select" ? " 已采用候选" : " 已取消采用")
        + "；旧候选和旧采用保留在历史中。确定性硬阻断仍会阻止交付。";
    } catch (error) {
      if (!action.alive()) return;
      elements.adoptStatus.textContent = "人工选择没有保存；原采用保留。";
      showError(elements.adoptError, errorMessageOf(error, "存储失败，请重试。"));
    } finally {
      if (action.alive()) deps.renderAttempts();
    }
  }

  /**
   * 审核阶段的逐图入口：图片 + 候选数 + 采用状态 + 逐图检查摘要 + 比较/返工/采用。
   *
   * 卡片右栏此前只有图名与徽标，真实链路走查（2026-10-01 自审）里一大片空白——
   * 人只能点开比较面板才知道这张图「查出了什么」。这里复读同一份当前报告
   * （compareInventory 已按 reviewIsCurrent 过滤），把状态、机器结论与「先看哪一条」
   * 摆到卡片上；不新增第二套规则，也不改变任何选择语义。
   */
  function renderReviewList(): void {
    if (!elements.reviewList) return;
    elements.reviewList.innerHTML = "";
    const shots = shotSummaries();
    const reviewable = shots.filter((shot) => generation.candidateChainOf(shot.shot_id).length > 0);
    elements.reviewEmpty.hidden = reviewable.length > 0;
    const inventory = reviewable.length ? compareInventory() : { rowsByShotId: {} as Record<string, CompareRow[]> };
    for (const shot of reviewable) {
      const chain = generation.candidateChainOf(shot.shot_id);
      const stored = generation.latestStoredCandidateOf(shot.shot_id);
      const state = selectionStateOf(shot.shot_id);
      const rows = inventory.rowsByShotId[shot.shot_id] || [];
      const shownRow = stored
        ? (rows.find((row) => row.candidate_id === stored.record.candidate_id) || null)
        : null;
      const card = createElement("div", {
        className: "review-card",
        attrs: { "data-shot-id": shot.shot_id, "data-selection-state": state },
      });
      const head = createElement("div", { className: "review-card-head" });
      head.append(createElement("span", { className: "name", text: shot.label }));
      head.append(createElement("span", {
        className: "badge " + (state === "current" ? "is-adopted" : (state === "stale" ? "is-review-warn" : "is-empty")),
        text: state === "current" ? "已采用" : (state === "stale" ? "已采用（已过期）" : "未采用"),
      }));
      head.append(createElement("span", { className: "meta", text: "候选 " + chain.length + " 个" }));
      card.append(head);
      if (stored) {
        const candidate = stored.record;
        const preview = createElement("div", { className: "review-preview" });
        const img = createElement("img", { attrs: { alt: shot.label + " 的最新候选", loading: "lazy" } });
        preview.append(img);
        card.append(preview);
        deps.ensurePreviewUrl(shot.shot_id, stored.record.action_id, candidate.asset_sha256)
          .then((url) => { if (url && img.isConnected) img.src = url; })
          .catch(() => {});
      } else {
        card.append(createElement("p", {
          className: "meta", text: "最新一次生成还没有保存到本地的候选；到「生成」里核对或重试。",
        }));
      }
      const check = createElement("div", {
        className: "review-card-check",
        attrs: {
          "data-shot-id": shot.shot_id,
          "data-review-state": shownRow ? shownRow.review_state : "unchecked",
          "data-candidate-id": shownRow ? shownRow.candidate_id : "",
        },
      });
      if (shownRow) {
        check.append(createElement("span", {
          className: "badge " + (COMPARE_STATE_BADGE[shownRow.review_state] || "is-review-unchecked"),
          text: compareStateLabel(shownRow),
        }));
        if (shownRow.report) {
          check.append(createElement("span", {
            className: "meta review-check-summary", text: reviewSummaryText(shownRow.report),
          }));
          const aiStatus = selectionAdoption.reviewStatusOf(shownRow.candidate_id);
          check.append(createElement("p", {
            className: "meta review-check-ai",
            attrs: { "data-review-ai": aiStatus.status },
            text: aiStatus.status === "reviewed" ? "AI 复核：已完成（只提示，不自动采纳）"
              : aiStatus.status === "unknown" ? "AI 复核：未完成（结果未知，不阻断人工采用）"
                : "AI 复核：未复核（未运行，按需发起才会调用；不阻断人工采用）",
          }));
        } else {
          // 只在真的补建失败时多一行：确定性报告缺失 ≠ AI 未复核，失败原因必须如实显示。
          const reportFailure = selectionAdoption.reportBuildFailure(shownRow.candidate_id);
          if (reportFailure) {
            check.append(createElement("p", {
              className: "meta review-check-report",
              attrs: { "data-review-report": "failed" },
              text: "自动检查报告补建失败：" + reportFailure
                + "（候选与本地图片保留，采用会被挡住；重新打开或再次采用会补建，不需要 AI）",
            }));
          }
        }
        check.append(createElement("p", {
          className: "meta review-check-headline", text: compareRowHeadline(shownRow),
        }));
      } else {
        check.append(createElement("span", {
          className: "badge is-review-unchecked",
          text: COMPARE_STATE_TEXT.unchecked,
        }));
        check.append(createElement("p", {
          className: "meta", text: "这张图还没有当前审核报告；打开「比较候选」可查看或补建。",
        }));
      }
      card.append(check);
      const actions = createElement("div", { className: "review-card-actions" });
      const compareButton = createElement("button", {
        text: "比较候选（" + chain.length + "）", attrs: { type: "button" },
      });
      compareButton.addEventListener("click", () => { openCompare(shot.shot_id, { focus: true }); });
      actions.append(compareButton);
      const reworkButton = createElement("button", { text: "按问题返工", attrs: { type: "button" } });
      reworkButton.disabled = !stored;
      reworkButton.addEventListener("click", () => {
        openCompare(shot.shot_id, {});
        openReworkPanel();
      });
      actions.append(reworkButton);
      const alreadyAdopted = state === "current";
      const adoptButton = createElement("button", {
        text: alreadyAdopted ? "已采用" : "采用候选", attrs: { type: "button" },
      });
      if (!alreadyAdopted) adoptButton.className = "primary";
      if (alreadyAdopted) adoptButton.title = "已采用这条候选；换用其他候选请点「比较候选」。";
      adoptButton.disabled = !stored || alreadyAdopted;
      adoptButton.addEventListener("click", () => {
        if (stored) void adoptCandidate("select", shot.shot_id, stored.record.candidate_id);
      });
      actions.append(adoptButton);
      card.append(actions);
      elements.reviewList.append(card);
    }
  }

  /** 重开项目时的就地状态归零：与原 loadWorkspace 重置项一一对应。 */
  function resetViewState(): void {
    compareShotId = null;
    compareCandidateId = null;
    compareToken += 1;
    reworkDrafts = new Map();
    reworkInFlight = false;
    reworkShotId = null;
    reworkSource = null;
    elements.comparePanel.hidden = true;
    elements.reworkPanel.hidden = true;
    elements.reworkPreviewBox.hidden = true;
  }

  return {
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
