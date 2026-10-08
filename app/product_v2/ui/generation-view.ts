/**
 * 生成视图（设计 §10.1 的第二个视图）：Prompt 准备/编译与人工编辑、生成前确认单、
 * 尝试与批次三区的渲染与命令。
 *
 * 边界（设计 §10.1）：这里只持 DOM（不做第二次 getElementById 分发，句柄由工作区装配
 * 一次传入）；不写库、不发网络、不重算业务判定。Prompt 版本/依据的唯一所有者是
 * prompts，确认队列/scope/mode 与尝试/候选链的唯一所有者是 generation；落库/派生/
 * 跨视图刷新都经 deps 回到工作区。确认单投影归 prompts，当前性/环境匹配的唯一判据
 * 在 generation，这里只转发，不重建规则。
 *
 * TypeScript 迁移（计划 §9 V2.R7.5）：本文件是唯一手工维护实现；同名 `generation-view.js`
 * 由 `npm run build:frontend` 生成，浏览器只消费生成的 `.js`。
 */
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
  appendTech,
  clearError,
  createElement,
  errorMessageOf,
  showError,
  techDetails,
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
  SuitePlanSummary,
} from "../domain/type-contracts.js";

/** 本视图负责的生成三区 DOM 句柄（与 index.html 的 id 一一对应，由工作区一次装配）。 */
export type GenerationElements = {
  promptLocked: HTMLElement;
  promptEditor: HTMLElement;
  localPreparationStatus: HTMLElement;
  promptStatus: HTMLElement;
  promptList: HTMLElement;
  promptError: HTMLElement;
  generateError: HTMLElement;
  confirmLocked: HTMLElement;
  confirmEditor: HTMLElement;
  confirmStatus: HTMLElement;
  confirmSummary: HTMLElement;
  confirmBlockers: HTMLElement;
  confirmRisks: HTMLElement;
  confirmList: HTMLElement;
  confirmAction: HTMLButtonElement;
  confirmRecord: HTMLElement;
  confirmError: HTMLElement;
  attemptLocked: HTMLElement;
  attemptEditor: HTMLElement;
  attemptProvider: HTMLElement;
  attemptStatus: HTMLElement;
  attemptError: HTMLElement;
  attemptList: HTMLElement;
  batchBar: HTMLElement;
  batchProgress: HTMLElement;
  batchHint: HTMLElement;
  queueList: HTMLElement;
  batchStop: HTMLButtonElement;
  batchReconcile: HTMLButtonElement;
  batchRetry: HTMLButtonElement;
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
  renderBatch(): void;
  /** 应用 owner 只读文案投影（状态行/错误位）；由工作区订阅 generation 后调用，视图不退订。 */
  applyNotice(): void;
  /** 生成与尝试两处错误位的就近写入（比较视图经工作区复用同一实现）。 */
  showAttemptError(message?: string): void;
  /** 时间戳短格式：尝试历史与比较区共用同一实现。 */
  shortTime(iso: unknown): string;
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

  function promptRecordOf(shotId: string | null): PromptEntry | null {
    return prompts.entryOf(shotId, null);
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

  /** 未保存的编辑草稿：重渲染时保留用户输入，不让界面动作吞掉正在写的文本。 */
  function capturePromptEdits(): Map<string, { text: string; reason: string }> {
    const drafts = new Map<string, { text: string; reason: string }>();
    const areas = elements.promptList.querySelectorAll("textarea.prompt-edit-text") as NodeListOf<HTMLTextAreaElement>;
    for (const area of areas) {
      const shotId = area.getAttribute("data-shot-id");
      const reason = area.parentElement
        ? (area.parentElement.querySelector("input.prompt-edit-reason") as HTMLInputElement | null)
        : null;
      if (shotId) drafts.set(shotId, { text: area.value, reason: reason ? reason.value : "" });
    }
    return drafts;
  }

  function renderPrompts(): void {
    const drafts = capturePromptEdits();
    const ready = Boolean(inputs.suitePlan());
    elements.promptLocked.hidden = ready;
    elements.promptEditor.hidden = !ready;
    elements.promptList.innerHTML = "";
    if (!ready) return;
    const summary: SuitePlanSummary | null = suitePlanSummary(inputs.suitePlan(), inputs.suiteContext());
    elements.promptStatus.textContent = summary
      ? "共 " + summary.total + " 张，依据已满足 " + summary.satisfiable + " 张可编译。"
      : "";
    if (!summary) return;
    summary.shots.forEach((item, index) => {
      // 已保存计划恒有 shot_id；null 仅存在于未落库草稿，跳过即可。
      const shotId = item.shot_id;
      if (typeof shotId !== "string") return;
      const entry = promptRecordOf(shotId);
      const stale = entry ? promptStaleness(entry.record, promptCurrentBasis(shotId)) : null;
      const card = createElement("div", {
        className: "shot-spec",
        attrs: {
          "data-shot-id": shotId,
          "data-prompt-state": entry ? (stale && stale.stale ? "stale" : "saved") : "none",
        },
      });
      const head = createElement("div", { className: "shot-spec-head" });
      head.append(createElement("span", { className: "name", text: (index + 1) + ". " + item.label }));
      head.append(createElement("span", {
        className: "meta", text: entry ? "版本 v" + entry.version : "未编译",
      }));
      head.append(createElement("span", {
        className: item.satisfied ? "badge" : "badge is-critical",
        text: item.satisfied ? "可编译" : "缺依据",
      }));
      if (stale && stale.stale) {
        head.append(createElement("span", { className: "badge is-critical", text: "已过期" }));
      }
      if (entry && entry.record.origin === "manual_edit") {
        head.append(createElement("span", { className: "badge is-proposed", text: "人工编辑" }));
      }
      card.append(head);
      if (entry) {
        card.append(createElement("pre", {
          className: "prompt-text", text: entry.record.compiled.text,
        }));
        const refs = entry.record.compiled.source_refs || [];
        const provider = entry.record.compiled.provider || {};
        card.append(createElement("p", {
          className: "meta",
          text: "请求：" + (provider.model_id || "?") + " · " + (provider.size || "?")
            + " · 参考图 " + (entry.record.request_snapshot.references || []).length + " 张",
        }));
        card.append(createElement("p", {
          className: "meta prompt-meta",
          text: "来源 " + refs.length + " 条 · " + entry.record.compiled.text.length
            + " 字 · hash " + entry.record.hash.slice(0, 12) + "…",
        }));
        card.append(createElement("p", { className: "meta prompt-hash", text: entry.record.hash }));
        for (const warning of entry.record.compiled.warnings || []) {
          card.append(createElement("p", {
            className: "meta prompt-warning",
            text: "提示：" + localizeSlotTerms(warning.message),
          }));
        }
        if (entry.record.origin === "manual_edit") {
          card.append(createElement("p", {
            className: "meta",
            text: "人工编辑 v" + entry.version + "（原因：" + entry.record.edit_reason + "；被编辑版本 v"
              + (entry.record.edited_from ? entry.record.edited_from.version : "?") + " 保留）",
          }));
        }
        if (stale && stale.stale) {
          card.append(createElement("p", {
            className: "meta prompt-warning",
            text: "依据已变化（" + stale.reasons.map((reason: { field: string }) => reason.field).join("、") + "）。"
              + (entry.record.origin === "manual_edit"
                ? "人工全文没有被覆盖；请按当前依据重新确认，或明确丢弃后重新准备。"
                : "系统会本地重新准备，不调用模型。"),
          }));
        }
      } else if (!item.satisfied) {
        card.append(createElement("p", {
          className: "meta", text: "暂时缺依据：" + suiteBlockingText(item.blocking),
        }));
      }
      const toolbar = createElement("div", { className: "toolbar" });
      const compileButton = createElement("button", {
        text: entry?.record.origin === "manual_edit" ? "丢弃人工全文并重新准备" : "重新本地准备",
        className: entry?.record.origin === "manual_edit" ? "danger" : "", attrs: { type: "button" },
      });
      compileButton.disabled = !item.satisfied || inputs.isAnalysisRunning();
      compileButton.addEventListener("click", () => {
        if (entry?.record.origin === "manual_edit") void handleDiscardManualPrompt(shotId);
        else void handleCompilePrompt(shotId);
      });
      toolbar.append(compileButton);
      let reconfirmButton: HTMLButtonElement | null = null;
      if (entry?.record.origin === "manual_edit" && stale?.stale) {
        reconfirmButton = createElement("button", {
          text: "按当前依据确认此人工全文", attrs: { type: "button" },
        });
        reconfirmButton.disabled = !item.satisfied || inputs.isAnalysisRunning();
        reconfirmButton.addEventListener("click", () => { void handleReconfirmManualPrompt(shotId); });
        toolbar.append(reconfirmButton);
      }
      card.append(toolbar);
      if (entry) {
        const draft = drafts.get(shotId) || null;
        const unsaved = draft !== null && draft.text !== entry.record.compiled.text;
        const block = createElement("div", { className: "prompt-edit-block" });
        block.append(createElement("label", {
          className: "meta",
          attrs: { for: "prompt-edit-" + shotId },
          text: "人工编辑全文（保存为新版本；原版本保留）",
        }));
        const area = createElement("textarea", {
          className: "prompt-edit-text",
          attrs: { id: "prompt-edit-" + shotId, "data-shot-id": shotId, rows: "6" },
        });
        area.value = draft && unsaved ? draft.text : entry.record.compiled.text;
        block.append(area);
        area.addEventListener("input", () => {
          if (reconfirmButton) reconfirmButton.disabled = !item.satisfied || inputs.isAnalysisRunning() || area.value !== entry.record.compiled.text;
        });
        block.append(createElement("label", {
          className: "meta",
          attrs: { for: "prompt-edit-reason-" + shotId },
          text: "编辑原因（必填，写入版本记录）",
        }));
        const reason = createElement("input", {
          className: "prompt-edit-reason",
          attrs: {
            id: "prompt-edit-reason-" + shotId, type: "text", autocomplete: "off",
            maxlength: String(MANUAL_EDIT_REASON_MAX),
          },
        });
        if (draft && unsaved && draft.reason) reason.value = draft.reason;
        block.append(reason);
        const saveEdit = createElement("button", { text: "保存为新版本", attrs: { type: "button" } });
        saveEdit.disabled = inputs.isAnalysisRunning();
        saveEdit.addEventListener("click", () => { handleSaveEditedPrompt(shotId); });
        block.append(saveEdit);
        card.append(block);
      }
      elements.promptList.append(card);
    });
  }

  /** 本地准备是 prompts Module 的动作；这里只传 DOM 草稿并呈现结果文案。 */
  async function prepareSystemPrompts(): Promise<void> {
    if (!deps.currentProjectId() || prompts.isPreparing()) return;
    const action = beginAction();
    if (!action.projectId) return;
    const gate = !inputs.suitePlan()
      ? "先添加图片任务；本地准备不会调用模型。"
      : (!deps.understandingReady() ? "请人工确认核心事实；各图片用途的额外缺项就地补足。"
        : (!currentImageProfile() ? "等待有效图像配置；打开模型设置可恢复。" : null));
    if (gate) {
      elements.localPreparationStatus.textContent = gate;
      return;
    }
    elements.localPreparationStatus.textContent = "正在本地准备已就绪图片任务；不会调用模型…";
    renderConfirm();
    try {
      const result = await prompts.prepare(capturePromptEdits());
      if (!action.alive()) return;
      if (result.reason === "no_plan" || result.reason === "facts" || result.reason === "configuration") {
        elements.localPreparationStatus.textContent = result.reason === "no_plan"
          ? "先添加图片任务；本地准备不会调用模型。"
          : result.reason === "facts" ? "请人工确认核心事实；各图片用途的额外缺项就地补足。"
            : "等待有效图像配置；打开模型设置可恢复。";
        return;
      }
      if (result.reason === "in_flight" || result.reason === "unchanged"
        || result.reason === "stale_session" || result.reason === "no_project") return;
      elements.localPreparationStatus.textContent = result.errors.length
        ? "部分任务尚未准备：" + result.errors.join("；")
        : "本地准备完成" + (result.prepared ? "（更新 " + result.prepared + " 张）" : "")
          + "；未调用模型。人工文本保留，提交前请核对下面的摘要。";
      await deps.deriveState();
    } finally {
      if (action.alive()) { renderPrompts(); renderConfirm(); renderAttempts(); }
    }
  }

  async function handleReconfirmManualPrompt(shotId: string): Promise<void> {
    const entry = promptRecordOf(shotId);
    if (!entry || entry.record.origin !== "manual_edit") return;
    const action = beginAction();
    const area = elements.promptList.querySelector(
      'textarea.prompt-edit-text[data-shot-id="' + shotId + '"]',
    ) as HTMLTextAreaElement | null;
    if (area && area.value !== entry.record.compiled.text) {
      showError(elements.promptError, "此全文有未保存修改；先保存，再重新确认，不会确认另一份旧文本。");
      return;
    }
    clearError(elements.promptError);
    try {
      const saved = await prompts.reconfirm(shotId, area ? area.value : null, action);
      if (!saved) return;
      if (!action.alive()) return;
      renderPrompts(); renderConfirm(); renderAttempts();
      elements.promptStatus.textContent = "人工全文原文保留，已按当前依据重新确认为 v" + saved.version + "；未调用模型。";
    } catch (error) {
      if (action.alive()) showError(elements.promptError, errorMessageOf(error, "重新确认失败；原人工全文保留。"));
    }
  }

  async function handleDiscardManualPrompt(shotId: string): Promise<void> {
    const entry = promptRecordOf(shotId);
    if (!entry || entry.record.origin !== "manual_edit") return;
    const action = beginAction();
    const area = elements.promptList.querySelector(
      'textarea.prompt-edit-text[data-shot-id="' + shotId + '"]',
    ) as HTMLTextAreaElement | null;
    const previousDraft = area?.value;
    clearError(elements.promptError);
    try {
      const payload = await prompts.discard(shotId, action);
      if (!action.alive() || !payload) return;
      if (area && area.value === previousDraft) area.value = payload.compiled.text;
      renderPrompts(); renderConfirm(); renderAttempts();
      elements.promptStatus.textContent = "已明确丢弃人工覆盖并恢复当前系统 Prompt；历史全文保留，未调用模型。";
    } catch (error) {
      if (action.alive()) showError(elements.promptError, errorMessageOf(error, "丢弃未完成；原全文与输入保留。"));
    }
  }

  async function handleCompilePrompt(shotId: string): Promise<void> {
    if (!deps.currentProjectId() || !inputs.suitePlan() || !deps.understandingReady()) return;
    const action = beginAction();
    clearError(elements.promptError);
    try {
      const result = await prompts.compileAndSave(shotId, { action });
      if (!action.alive()) return;
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deps.deriveState();
      if (!action.alive()) return;
      elements.promptStatus.textContent = "已保存 " + shotId + " 的 Prompt 版本 v"
        + result.saved.version + "。";
    } catch (error) {
      if (!action.alive()) return;
      showError(elements.promptError,
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
    clearError(elements.promptError);
    const entry = promptRecordOf(shotId);
    if (!entry) {
      showError(elements.promptError, "先编译并保存这张图的 Prompt，再编辑。");
      return;
    }
    const area = document.getElementById("prompt-edit-" + shotId) as HTMLTextAreaElement | null;
    const reasonInput = document.getElementById("prompt-edit-reason-" + shotId) as HTMLInputElement | null;
    try {
      const saved = await prompts.edit(shotId, area ? area.value : "", reasonInput ? reasonInput.value : "", action);
      if (!action.alive()) return;
      renderPrompts();
      renderConfirm();
      renderAttempts();
      await deps.deriveState();
      if (!action.alive()) return;
      elements.promptStatus.textContent = "已保存 " + shotId + " 的人工编辑版本 v" + saved.version
        + "（被编辑版本 v" + entry.version + " 保留）。";
    } catch (error) {
      if (action.alive()) {
        showError(elements.promptError,
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

  function renderConfirm(): void {
    const ready = Boolean(inputs.suitePlan());
    elements.confirmLocked.hidden = ready;
    elements.confirmEditor.hidden = !ready;
    elements.confirmSummary.innerHTML = "";
    elements.confirmBlockers.innerHTML = "";
    elements.confirmRisks.innerHTML = "";
    elements.confirmList.innerHTML = "";
    elements.confirmRecord.textContent = "";
    elements.confirmAction.disabled = true;
    displayedGenerationIntent = null;
    if (!ready) return;
    let sheet: ConfirmationSheet | null = null;
    try {
      // 所见摘要由 generation 准备：视图只保存并原样交回，不重算、不猜版本。
      displayedGenerationIntent = generation.prepareSummary();
      sheet = displayedGenerationIntent ? displayedGenerationIntent.all : null;
    } catch (error) {
      showError(elements.confirmError,
        "生成前确认投影失败：" + errorMessageOf(error, "未知错误"));
      return;
    }
    if (!sheet || !displayedGenerationIntent) {
      elements.confirmStatus.textContent = "尚未取得有效图像能力；恢复服务后再确认，不会提交未经核对的请求。";
      return;
    }
    const intent = displayedGenerationIntent;
    const sending = intent.sheet;
    const sendingIds = new Set(sending?.shots.map((item) => item.shot_id) || []);
    elements.confirmStatus.textContent = "本次明确发送 " + (sending?.total || 0) + " 张；"
      + "用途缺项／过期任务不外发；已有成功、进行中或 Unknown 不自动重提。";
    elements.confirmSummary.append(createElement("p", {
      className: "confirm-summary", text: sending ? sending.external_summary.statement : "当前没有可新增发送的已就绪图片任务。",
    }));
    if (intent.mode === "explicit_new") {
      elements.confirmSummary.append(createElement("p", {
        className: "prompt-warning",
        text: "这是另一个新动作，不是核对原任务。原 Unknown 可能已经被受理，另发可能重复扣费；原记录与采用不删除、不覆盖。",
      }));
    }
    elements.confirmSummary.append(createElement("p", {
      className: "meta",
      text: "每张图发送自己的 Prompt 文本与上列参考图；不发送本地文件本身、历史候选或其他项目数据。",
    }));
    for (const blocker of sheet.blockers) {
      const row = createElement("p", { className: "confirm-blocker" });
      row.append(createElement("span", { text: "#" + blocker.order + " " + blocker.label + " · " + blocker.code }));
      row.append(createElement("span", { className: "meta", text: localizeSlotTerms(blocker.message) }));
      row.append(createElement("span", {
        className: "meta", text: "返回：" + blocker.fix.region + " · " + blocker.fix.action,
      }));
      const fix = createElement("button", { text: "去补足此项", attrs: { type: "button" } });
      fix.addEventListener("click", () => {
        const task = ({ intake: "intake", understanding: "understand", suite: "plan",
          style: "generate", shot_spec: "generate", prompt: "generate" } as Record<string, string>)[blocker.fix.region];
        deps.selectStage(task);
        if (blocker.fix.region === "prompt") {
          (document.getElementById("prompt-details") as HTMLDetailsElement).open = true;
        }
      });
      row.append(fix);
      elements.confirmBlockers.append(row);
    }
    for (const risk of sheet.risks) {
      elements.confirmRisks.append(createElement("p", {
        className: "confirm-risk",
        text: risk.label + " · " + risk.code + "：" + localizeSlotTerms(risk.message),
      }));
    }
    for (const item of sheet.shots) {
      const row = createElement("div", {
        className: "confirm-shot",
        attrs: { "data-shot-id": item.shot_id, "data-blocked": String(item.blockers.length > 0) },
      });
      const head = createElement("div", { className: "confirm-shot-head" });
      head.append(createElement("span", { className: "name", text: item.order + ". " + item.label }));
      head.append(createElement("span", {
        className: "badge",
        text: (item.role_label || item.role_id || "未分类") + (item.required ? " · 必需" : " · 可选"),
      }));
      head.append(createElement("span", {
        className: item.blockers.length > 0 ? "badge is-critical" : "badge is-confirmed",
        text: sendingIds.has(item.shot_id) ? "本次发送" : item.blockers.length ? "本次不发送：缺项／过期" : "本次不重复提交",
      }));
      head.append(createElement("span", {
        className: "meta",
        text: item.prompt.version === null
          ? "未编译"
          : "Prompt v" + item.prompt.version + " · " + String(item.prompt.hash).slice(0, 12) + "…",
      }));
      row.append(head);
      if (item.intent) row.append(createElement("p", { className: "meta", text: "任务：" + item.intent }));
      row.append(createElement("p", {
        className: "meta",
        text: "参考图 " + item.references.length + " 张（"
          + (item.references.map((ref) => ROLE_TEXT[ref.role] || ref.role).join("、") || "无") + "）"
          + (item.prompt.chars === null ? "" : " · 提示词 " + item.prompt.chars + " 字"),
      }));
      const referenceTech = techDetails(item.references.map(
        (ref) => (ROLE_TEXT[ref.role] || ref.role) + " sha256 " + ref.sha256_prefix));
      if (referenceTech) row.append(referenceTech);
      if (item.risks.length > 0) {
        row.append(createElement("p", {
          className: "meta prompt-warning",
          attrs: { title: item.risks.map((risk) => risk.code).join("、") },
          text: "风险：" + item.risks
            .map((risk) => localizeSlotTerms(risk.message || risk.code)).join("；"),
        }));
      }
      elements.confirmList.append(row);
    }
    const identity = intent.identity;
    elements.confirmAction.disabled = !sending?.can_submit || !identity?.configured || inputs.isAnalysisRunning()
      || prompts.isPreparing() || submissionInFlight || modelSettings.refreshing
      || Boolean(generation.batchStateReader()?.active);
    elements.confirmAction.textContent = (intent.mode === "explicit_new" ? "确认并另发 " : "确认并生成 ")
      + (sending?.total || 0) + " 张";
    elements.confirmRecord.textContent = identity?.configured
      ? "一次点击先保存这份授权，再按摘要外发；不会要求第二次提交。"
      : "原目标凭据未就绪。打开模型设置补凭据；本地事实、Prompt、采用和导出不受影响。";
  }

  async function handleConfirmGeneration(): Promise<void> {
    if (!deps.currentProjectId() || !inputs.suitePlan() || submissionInFlight
      || prompts.isPreparing() || modelSettings.refreshing) return;
    const authorized = displayedGenerationIntent;
    if (!authorized) return;
    const action = beginAction();
    submissionInFlight = true;
    elements.confirmAction.disabled = true;
    clearError(elements.confirmError);
    try {
      // 只交出用户看过的那份摘要：授权文档/所见版本/当前性核对都在 owner 内部完成。
      const result = await generation.confirmAndRun({ intent: authorized });
      // stale：owner 已算出新摘要并零外发；把新摘要直接读给用户，避免"只说过期、不知道变成什么"。
      // 不自动确认、不自动重提；下面 finally 的 renderConfirm 会按 owner 当前投影重新呈现。
      if (result.stale && action.alive()) {
        const fresh = result.intent?.sheet?.external_summary?.statement || "";
        showError(elements.confirmError,
          (result.message || "摘要已变化；请核对新摘要后再确认。") + (fresh ? "当前摘要：" + fresh : ""));
      }
    } catch (error) {
      if (action.alive()) showError(elements.confirmError, errorMessageOf(error, "生成没有完成；授权与历史保留。"));
    } finally {
      submissionInFlight = false;
      // 确认写库后派生项目状态（PLAN_REVIEW → READY_TO_GENERATE）：与编译保存同一语义，
      // 否则确认存在但状态不前进，-05 类“确认存在且状态前进”断言永远红。
      try { if (action.alive()) await deps.deriveState(); } catch { /* 状态派生失败不吞确认结果 */ }
      if (action.alive()) { renderConfirm(); renderAttempts(); }
     }
  }

  /* ------------------------------------------------------------ 生成执行 */

  /** 尝试状态行：命令结果就近写入的唯一实现；owner 旁路文案也经 applyNotice 落到这里。 */
  function setAttemptStatus(text: string): void {
    elements.attemptStatus.textContent = text;
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

  /** 生成与尝试两个位置共用同一份错误文本：错误就近显示在对应阶段。 */
  function showAttemptError(message?: string): void {
    showError(elements.generateError, message || "");
    showError(elements.attemptError, message || "");
  }

  function clearAttemptError(): void {
    clearError(elements.generateError);
    clearError(elements.attemptError);
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

  function renderAttempts(): void {
    const ready = Boolean(inputs.suitePlan());
    elements.attemptLocked.hidden = ready;
    elements.attemptEditor.hidden = !ready;
    elements.attemptList.innerHTML = "";
    if (!ready) { renderBatch(); deps.renderCompare(); deps.renderSelectionProgress(); return; }
    const summary = suitePlanSummary(inputs.suitePlan(), inputs.suiteContext());
    const confirmed = confirmationIsCurrent();
    const provider = imageProviderBlock();
    elements.attemptProvider.textContent = provider
      ? "图像 provider：" + (provider.provider_id || "未声明") + " · " + (provider.model_id || "未声明")
        + (provider.configured === false ? " · 未配置（提交会被拒绝，不会调用模型）" : " · 已配置")
      : "图像 provider：尚未读到能力信息；提交前请确认服务端可用。";
    const counts = { total: 0, none: 0, active: 0, succeeded: 0, failed: 0, unknown: 0 };
    const shots = summary ? summary.shots : [];
    for (const item of shots) {
      const chain = generation.attemptChainOf(item.shot_id);
      const latest = generation.latestAttemptOf(item.shot_id);
      const record = latest ? latest.record : null;
      const state = record ? record.state : null;
      const entry = promptRecordOf(item.shot_id);
      const stale = record ? attemptPromptStaleness(record, currentPromptPointer(item.shot_id)) : null;
      counts.total += 1;
      if (!record) counts.none += 1;
      else if (state === ATTEMPT_STATES.succeeded) counts.succeeded += 1;
      else if (state === ATTEMPT_STATES.failed) counts.failed += 1;
      else if (state === ATTEMPT_STATES.unknown) counts.unknown += 1;
      else counts.active += 1;

      const rowShotId = item.shot_id;
      const row = createElement("div", {
        className: "attempt-row",
        attrs: { "data-shot-id": rowShotId, "data-attempt-state": state || "none",
                 "tabindex": "-1" },
      });
      const head = createElement("div", { className: "attempt-head" });
      head.append(createElement("span", { className: "name", text: item.label }));
      head.append(createElement("span", {
        className: "badge " + (record ? attemptBadgeClass(state) : "is-missing"),
        text: record ? attemptStateLabel(state) : "尚未生成",
      }));
      head.append(createElement("span", {
        className: "meta",
        text: entry ? "Prompt v" + entry.version : "未编译 Prompt",
      }));
      if (stale && stale.stale) {
        head.append(createElement("span", {
          className: "badge is-attempt-stale",
          text: "基于旧版本 v" + stale.attempt_version,
        }));
      }
      row.append(head);
      if (entry) {
        const promptTech = techDetails(["hash " + String(entry.record.hash).slice(0, 12) + "…"]);
        if (promptTech) row.append(promptTech);
      }
      if (record) {
        const parts = ["提交 " + shortTime(record.created_at)];
        if (record.updated_at !== record.created_at) parts.push("更新 " + shortTime(record.updated_at));
        row.append(createElement("p", { className: "meta attempt-task", text: parts.join(" · ") }));
        const attemptTech = ["action " + record.action_id];
        if (record.task_id) attemptTech.push("task " + record.task_id);
        appendTech(row, attemptTech);
        const note = record.change_log.length
          ? record.change_log[record.change_log.length - 1].note : null;
        if (note) row.append(createElement("p", { className: "meta", text: "最近一次变化：" + note }));
        if (record.error) {
          row.append(createElement("p", {
            className: "attempt-error-text",
            text: (state === ATTEMPT_STATES.unknown ? "未知原因：" : "失败原因：")
              + record.error.family + " / " + record.error.code + "：" + record.error.message
              + "（重试策略 " + record.error.retry_policy + "）",
          }));
        }
        if (state === ATTEMPT_STATES.succeeded) {
          const stored = generation.candidateForAttemptOf(item.shot_id, record.action_id);
          if (stored && candidateMatchesAttempt(stored, record)) {
            const candidate = stored.record;
            const thumb = createElement("div", { className: "attempt-preview" });
            const img = createElement("img", {
              attrs: { alt: item.label + " 的候选", loading: "lazy" },
            });
            thumb.append(img);
            row.append(thumb);
            deps.ensurePreviewUrl(item.shot_id, record.action_id, candidate.asset_sha256)
              .then((url) => {
                if (url && img.isConnected) img.src = url;
              })
              .catch(() => {});
            row.append(createElement("p", {
              className: "meta attempt-candidate",
              text: "候选已保存到本地 · " + candidate.width + "×" + candidate.height + " · "
                + candidate.media_type + " · "
                + Math.max(1, Math.round(candidate.byte_size / 1024)) + " KB（预览来自本地字节）",
            }));
            appendTech(row, ["sha256 " + candidate.asset_sha256.slice(0, 12) + "…"]);
            const reviewEntry = selectionAdoption.reportOf(candidate.candidate_id);
            if (reviewEntry && reviewIsCurrent(reviewEntry.report, candidate)) {
              const top = topFinding(reviewEntry.report);
              row.append(createElement("p", {
                className: "meta attempt-review",
                attrs: {
                  "data-review-summary": reviewSummaryText(reviewEntry.report),
                  "data-review-contract": reviewEntry.report.review_contract_version,
                  "data-review-candidate": candidate.candidate_id,
                },
                text: reviewSummaryText(reviewEntry.report)
                  + (top ? " · 先看：" + top.title + " — " + top.detail : " · 无待处理项"),
              }));
            } else {
              // 确定性报告缺失与"补建失败"必须分开：失败要如实显示原因，不能伪装成"AI 未复核"。
              const reportFailure = selectionAdoption.reportBuildFailure(candidate.candidate_id);
              row.append(createElement("p", {
                className: "meta attempt-review",
                attrs: {
                  "data-review-summary": reportFailure ? "failed" : "missing",
                  "data-review-vlm": "not_run",
                },
                text: (reportFailure
                  ? "自动检查报告补建失败：" + reportFailure
                    + "（候选与本地图片保留，原采用不受影响;采用或重新打开项目会再补建，不需要 AI）"
                  : "自动检查报告尚未生成（候选保存或重新打开项目后由本地补建，不调用模型）")
                  + " AI 复核未运行：按需发起才会调用，未复核不阻断人工采用。",
              }));
            }
            const reviewButton = createElement("button", {
              text: rowShotId && selectionAdoption.isReviewInFlight(rowShotId) ? "复核中…" : "AI 复核这条候选（按需发起，可选）",
              attrs: {
                type: "button",
                "data-review-action": candidate.candidate_id,
                title: "只在你点这一下时才调用视觉语言模型找可疑问题；查看、采用都不会触发。只提示，不自动采纳；未复核不阻断人工采用。",
              },
            });
            reviewButton.addEventListener("click", async () => {
              if (!rowShotId) return;
              const outcome = await selectionAdoption.reviewCandidate(rowShotId, candidate.candidate_id);
              if (outcome && outcome.failed) {
                setAttemptStatus("复核未完成：" + outcome.message
                  + "（候选与报告保持不变；真实失败才记 Unknown，未发起仍是未复核）");
              }
            });
            row.append(reviewButton);
          } else if (stored) {
            row.append(createElement("p", {
              className: "meta attempt-note",
              text: "候选记录与来源 Attempt 不一致：不显示预览（记录保留，等待复核）。",
            }));
          } else {
            row.append(createElement("p", {
              className: "meta attempt-note",
              text: "上游已完成，候选字节尚未保存到本地。",
            }));
          }
        }
        // 比较区只看候选链：最新一次尝试是失败/未知时，历史候选仍然可以比较与返工。
        if (generation.candidateChainOf(rowShotId).length) {
          const compareButton = createElement("button", {
            text: "比较候选（" + generation.candidateChainOf(rowShotId).length + "）",
            attrs: {
              type: "button",
              "data-compare-action": rowShotId,
              "aria-expanded": String(deps.isComparing(rowShotId)),
              title: "对比这张图的参考图、历史候选与审核清单",
            },
          });
          compareButton.addEventListener("click", (event) => {
            if (!rowShotId) return;
            deps.openCompare(rowShotId, { focus: event.detail === 0 });
          });
          row.append(compareButton);
        }
        const selectionEntry = rowShotId ? selectionAdoption.entryOf(rowShotId) : null;
        const selectionState = rowShotId ? selectionAdoption.stateOf(rowShotId) : "none";
        if (selectionEntry || (rowShotId && generation.candidateChainOf(rowShotId).length)) {
          row.append(createElement("p", {
            className: "meta attempt-selection",
            attrs: {
              "data-selection-state": selectionState,
              "data-selection-shot": item.shot_id,
            },
            text: selectionSummaryText(selectionEntry ? selectionEntry.record : null, selectionState),
          }));
        }
        if ((state === ATTEMPT_STATES.pending_submit || state === ATTEMPT_STATES.unknown)
            && !record.task_id) {
          row.append(createElement("p", {
            className: "meta attempt-note",
            text: "这次提交没有留下任务编号（可能已到达上游）。系统不会自动重提；可以显式新建 action，或先核对（若已有编号）。",
          }));
        }
      }
      if (stale && stale.stale) {
        row.append(createElement("p", {
          className: "meta attempt-note",
          text: "这条记录基于 Prompt v" + stale.attempt_version + "；当前是 v" + stale.current_version
            + "。要按新版出图，请先重新确认，再新建 action。",
        }));
      }
      const actions = createElement("div", { className: "toolbar attempt-actions" });
      const batchState = generation.batchStateReader();
      const batchActive = Boolean(batchState && batchState.active);
      const inFlight = (rowShotId ? generation.isAttemptInFlight(rowShotId) : false) || inputs.isAnalysisRunning() || batchActive;
      const shotConfirmed = confirmationIsCurrentForShot(rowShotId);
      const canSubmit = shotConfirmed && Boolean(entry) && !inFlight;
      const reconcileMode = record ? attemptReconcileMode(record) : ATTEMPT_RECONCILE_MODES.none;
      const stuckPending = state === ATTEMPT_STATES.pending_submit && record && !record.task_id;
      if (reconcileMode === ATTEMPT_RECONCILE_MODES.by_task && record) {
        const environment = attemptCurrentEnvironmentIdentity(modelSettings.imageEnvironment(
          record.provider.provider_id, record.execution_identity.credential_reference.source));
        const gate = attemptReconcileEnvironment(record, environment);
        if (gate.mode !== ATTEMPT_RECONCILE_MODES.by_task) {
          actions.append(createElement("p", {
            className: "meta", text: attemptReconcileBlockedMessage(record),
          }));
          const credentials = createElement("button", {
            text: record.execution_identity.credential_reference.source === "byok"
              ? "给原目标补凭据" : "查看原目标配置",
            attrs: { type: "button", "data-original-credentials": item.shot_id },
          });
          credentials.addEventListener("click", () => modelSettings.open("image",
            record.execution_identity.credential_reference.source === "byok"
              ? record.provider.provider_id : undefined));
          actions.append(credentials);
        }
        const button = createElement("button", { text: "核对任务", attrs: { type: "button" } });
        button.disabled = inFlight || gate.mode !== ATTEMPT_RECONCILE_MODES.by_task;
        button.addEventListener("click", () => { void handleReconcileAttempt(rowShotId); });
        actions.append(button);
      }
      if (!record) {
        const button = createElement("button", {
          className: "primary", text: "生成这张图", attrs: { type: "button" },
        });
        button.disabled = !canSubmit;
        button.addEventListener("click", () => { void handleSubmitAttempt(rowShotId); });
        actions.append(button);
      } else if (stuckPending || state === ATTEMPT_STATES.unknown) {
        const button = createElement("button", {
          text: "新建 action（放弃核对）", attrs: { type: "button" },
        });
        button.disabled = !entry || inFlight;
        button.addEventListener("click", () => {
          void handleSubmitAttempt(rowShotId, { explicitNew: true });
        });
        actions.append(button);
      } else if (state === ATTEMPT_STATES.failed) {
        const button = createElement("button", {
          text: "重试（新建 action）", attrs: { type: "button" },
        });
        button.disabled = !entry || inFlight;
        button.addEventListener("click", () => {
          void handleSubmitAttempt(rowShotId, { explicitNew: true });
        });
        actions.append(button);
      } else if (state === ATTEMPT_STATES.succeeded) {
        const stored = generation.candidateForAttemptOf(rowShotId, record.action_id);
        if (!stored) {
          const save = createElement("button", {
            className: "primary", text: "保存候选图片", attrs: { type: "button" },
          });
          // 批次运行中也要能用：取回失败时提示区正让用户点这个按钮,而它只做本地保存,
          // 同一张的并发保存由 isCandidateInFlight 挡住(模块内直接 no-op)。
          save.disabled = (rowShotId ? generation.isAttemptInFlight(rowShotId) : false)
            || inputs.isAnalysisRunning()
            || (rowShotId ? generation.isCandidateInFlight(rowShotId) : false);
          save.addEventListener("click", () => { void handleStoreCandidate(rowShotId); });
          actions.append(save);
        }
        const button = createElement("button", {
          text: "再生成一张（新建 action）", attrs: { type: "button" },
        });
        button.disabled = !entry || inFlight;
        button.addEventListener("click", () => {
          void handleSubmitAttempt(rowShotId, { explicitNew: true });
        });
        actions.append(button);
      } else if (record && state && ATTEMPT_ACTIVE_STATES.includes(state)) {
        const label = inFlight ? "提交中…" : "上游处理中，先核对";
        const button = createElement("button", { text: label, attrs: { type: "button" } });
        button.disabled = true;
        actions.append(button);
      }
      if (!shotConfirmed) {
        actions.append(createElement("span", {
          className: "meta",
          text: "这张图还没有有效的生成前确认：先在「生成前确认」确认整套，或在候选比较面板里走一次返工确认。",
        }));
      } else if (!entry) {
        actions.append(createElement("span", { className: "meta", text: "先编译并保存这张图的 Prompt。" }));
      }
      row.append(actions);
      if (chain.length > 1) {
        const details = createElement("details", { className: "attempt-history" });
        details.append(createElement("summary", { text: "历史 " + chain.length + " 条状态记录（提交与核对均追加保留）" }));
        for (const item2 of chain.slice().reverse()) {
          const itemRecord = item2.record;
          details.append(createElement("p", {
            className: "attempt-history-row",
            text: "v" + item2.version + " · " + attemptStateLabel(itemRecord.state)
              + " · action " + itemRecord.action_id
              + (itemRecord.task_id ? " · task " + itemRecord.task_id : "")
              + " · " + shortTime(itemRecord.updated_at),
          }));
        }
        row.append(details);
      }
      elements.attemptList.append(row);
    }
    const activeText = counts.active > 0 ? "进行中 " + counts.active + " 张；" : "";
    setAttemptStatus("共 " + counts.total + " 张；未生成 " + counts.none + " 张；"
      + activeText + "已成功 " + counts.succeeded + " 张；结果未知 " + counts.unknown + " 张；失败 "
      + counts.failed + " 张。" + (confirmed ? "可以整套生成或逐张提交。" : "确认缺失或已过期，暂不能提交。"));
    renderBatch();
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
      elements.confirmAction.focus();
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
      setAttemptStatus(elements.attemptStatus.textContent + " 候选已保存到本地（sha256 "
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
        setAttemptStatus(elements.attemptStatus.textContent + " 候选已保存到本地（sha256 "
          + result.candidate.sha256.slice(0, 12) + "…）。");
      }
    } else {
      setAttemptStatus("已核对 task " + result.task_id + "：没有新结论（"
        + result.note + "）。");
    }
    return result;
  }

  function renderBatch(): void {
    if (!elements.batchBar) return;
    const ready = Boolean(inputs.suitePlan());
    elements.batchBar.hidden = !ready;
    if (!ready) return;
    const state = generation.deriveBatch();
    const batchState = generation.batchStateReader();
    const running = Boolean(batchState && batchState.active);
    const confirmed = confirmationIsCurrent();
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
    elements.batchProgress.textContent = progress.join("；") + "。";

    const hints = [];
    if (!confirmed) hints.push("生成前确认缺失或已过期：先回到「生成前确认」重新确认。");
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
    elements.batchHint.textContent = hints.join(" ");
    elements.batchHint.hidden = hints.length === 0;

    elements.queueList.replaceChildren();
    // 队列投影（pending/current/targetMatched）归 generation.queues() 所有；这里只渲染，不重算判据。
    for (const { queue, pending, current, targetMatched: matched } of generation.queues()) {
      if (!pending.length) continue;
      const target = queue.payload.fingerprint.snapshot.execution_target;
      if (!target) continue;
      const row = createElement("div", { className: "generation-queue" });
      row.append(createElement("p", {
        className: "meta", text: "原队列 v" + queue.version + " · " + target.model_id + " · "
          + target.protocol + " · 凭据 " + target.credential_source + " · 尚未提交 " + pending.length
          + " 张（当前依据有效 " + current.length + " 张）：" + pending.map((shotId) => deps.shotLabelOf(shotId)).join("、"),
      }));
      row.append(createElement("p", { className: "meta", text: String(queue.payload.external_summary.statement) }));
      const resume = createElement("button", { text: "按原摘要继续未提交队列", attrs: { type: "button" } });
      resume.disabled = running || submissionInFlight || !matched || !current.length;
      resume.addEventListener("click", () => { void generation.runBatch({ confirmation: queue }); });
      const credentials = createElement("button", { text: "给原目标补凭据", attrs: { type: "button" } });
      credentials.addEventListener("click", () => modelSettings.open("image", target.provider_id));
      row.append(resume, credentials);
      elements.queueList.append(row);
    }
    elements.batchStop.hidden = !running;
    elements.batchReconcile.hidden = state.reconcile_queue.length === 0;
    elements.batchReconcile.disabled = running || state.reconcile_queue.length === 0;
    elements.batchReconcile.textContent = "核对进行中（" + state.reconcile_queue.length + " 张）";
    elements.batchRetry.hidden = state.retry_queue.length === 0;
    elements.batchRetry.disabled = running || state.retry_queue.length === 0;
    elements.batchRetry.textContent = "查看失败图的重试摘要（" + state.retry_queue.length + " 张）";
  }

  /** 生成/确认/尝试三区同轮刷新：全量渲染与输入侧命令收尾共用一处，避免三份写法。 */
  function render(): void {
    renderPrompts();
    renderConfirm();
    renderAttempts();
  }

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
    renderBatch,
    applyNotice,
    showAttemptError,
    shortTime,
  };
}
