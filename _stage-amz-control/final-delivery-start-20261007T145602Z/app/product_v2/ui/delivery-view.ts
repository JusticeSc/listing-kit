/**
 * 交付视图（设计 §2.1 的第四个视图）：交付阶段逐图采用状态、门禁清单、Unknown 知悉、
 * 整套检查结论投影与两类导出。
 *
 * 边界（设计 §10.1）：这里只持 DOM、展开/焦点与**自己创建**的对象 URL；不写库、不发网络、
 * 不重算门禁判定、不组 manifest/ZIP。业务执行与判定归 reviewDelivery / selectionAdoption。
 *
 * TypeScript 迁移（计划 §9 V2.R7.5）：本文件是唯一手工维护实现；同名 `delivery-view.js`
 * 由 `npm run build:frontend` 生成，浏览器只消费生成的 `.js`。
 */
import { COMPARE_SEVERITY_TEXT, REVIEW_SEVERITY_ORDER, suiteReviewSummaryText } from "../domain/index.js";
import { SEVERITY_BADGE, appendTech, clearError, createElement, errorMessageOf, showError } from "./dom.js";
import type { ReviewDeliveryModule } from "../review-delivery.js";
import type { SelectionAdoptionModule } from "../selection-adoption.js";
import type { SuiteReviewReport, UnknownItem } from "../domain/type-contracts.js";
import type { ActionSnapshot } from "../session.js";

/** 方案投影里的 shot 形状（视图只读 label/required，不重算方案）。 */
export type SuiteShotSummary = { shot_id: string; label: string; required?: boolean };

export type DeliveryElements = {
  reviewList: HTMLElement;
  suiteReviewStatus: HTMLElement;
  suiteReviewRun: HTMLButtonElement;
  suiteAiReviewRun: HTMLButtonElement;
  suiteReviewNote: HTMLElement;
  suiteReviewFindings: HTMLElement;
  suiteReviewError: HTMLElement;
  deliveryGate: HTMLElement;
  deliverySuiteStatus: HTMLElement;
  deliverySuiteFindings: HTMLElement;
  deliveryUnknowns: HTMLElement;
  deliverExport: HTMLButtonElement;
  deliverStatus: HTMLElement;
  deliverResult: HTMLElement;
  deliverError: HTMLElement;
};

export type DeliveryViewDeps = {
  reviewDelivery: ReviewDeliveryModule;
  selectionAdoption: SelectionAdoptionModule;
  /** 只用于判断「方案是否已存在」；不在此重算方案。 */
  inputs: { suitePlan(): unknown };
  beginAction(): ActionSnapshot;
  currentProjectId(): string | null;
  capabilities(): { suite_review?: { provider?: { configured?: boolean } | null } | null } | null;
  shotSummaries(): SuiteShotSummary[];
  shotLabelOf(shotId: string): string;
  localizeShotIds(text: unknown): string;
  selectionStateOf(shotId: string): string;
  selectStage(stageId: string): void;
};

export type DeliveryView = {
  /** 门禁与整套结论一次同轮渲染（设计 §2.3 合并同一轮渲染）。 */
  render(): void;
  requestGateRefresh(): void;
  runSuiteReview(options?: { ai?: boolean }): Promise<void>;
  handleProjectExport(): Promise<void>;
  handleDeliveryExport(): Promise<void>;
  dispose(): void;
};

/** 门禁展示顺序：阻断优先，PASS 收在最后；不改判定，只改阅读顺序。 */
const GATE_SEVERITY_RANK: Record<string, number> = {
  BLOCK: 0, HIGH_RISK: 1, WARNING: 2, UNKNOWN: 3, PASS: 4,
};

/**
 * 交付视图工厂。
 * @param args.elements 本视图负责的 DOM 句柄
 * @param args.deps 窄依赖：业务命令/投影 + 装配期注入的投影回调
 */
export function createDeliveryView(
  { elements, deps }: { elements: DeliveryElements; deps: DeliveryViewDeps },
): DeliveryView {
  /** 对象 URL 归视图持有：下载链接由各次导出命令即时创建，不进 owner，dispose 时释放。 */
  const downloadUrlByFile = new Map<string, string>();
  const createdUrls: string[] = [];

  /** 整套检查只做视图装配与动作转发：执行、报告与门禁刷新归 reviewDelivery 所有。 */
  async function runSuiteReview({ ai = false }: { ai?: boolean } = {}): Promise<void> {
    const action = deps.beginAction();
    if (!action.projectId || !action.alive()) return;
    clearError(elements.suiteReviewError);
    try {
      const outcome = await deps.reviewDelivery.runSuiteReview({ ai });
      if (!action.alive()) return;
      if (outcome && outcome.failed) {
        showError(elements.suiteReviewError,
          errorMessageOf(outcome.message || outcome.reason, "整套检查没有保存；之前的报告保留。"));
      }
    } catch (error) {
      if (action.alive()) showError(elements.suiteReviewError,
        errorMessageOf(error, "整套检查没有保存；之前的报告保留。"));
    } finally {
      if (action.alive()) { renderSuitePanel(); deps.reviewDelivery.requestGateRefresh(); }
    }
  }

  /**
   * 跳回审核阶段的具体图卡：换阶段后滚动到行并把焦点交给首个按钮（键盘可见）。
   */
  function jumpToReviewShot(shotId: string): void {
    deps.selectStage("review");
    if (!elements.reviewList) return;
    const row = elements.reviewList.querySelector<HTMLElement>('.review-card[data-shot-id="' + shotId + '"]');
    if (!row) return;
    row.scrollIntoView({ block: "center" });
    const button = row.querySelector<HTMLButtonElement>("button");
    if (button) button.focus({ preventScroll: true });
  }

  /** 门禁：整套一致性阻断不属于任何一张图，定位回审核阶段的整套检查运行按钮。 */
  function jumpToSuiteCheck(): void {
    deps.selectStage("review");
    if (!elements.suiteReviewRun) return;
    elements.suiteReviewRun.scrollIntoView({ block: "center" });
    elements.suiteReviewRun.focus({ preventScroll: true });
  }

  /** 整套一致性分区：状态行 + 运行按钮 + 按严重度分组的发现（每条可跳到对应图行）。 */
  function renderSuitePanel(): void {
    if (!elements.suiteReviewStatus || !elements.suiteReviewFindings) return;
    const projection = deps.reviewDelivery.projection();
    const entry = projection.suite;
    const report = entry ? entry.report : null;
    const current = projection.suiteCurrent;
    const running = projection.running;
    const pid = deps.currentProjectId();
    const planReady = Boolean(deps.inputs.suitePlan());
    const caps = deps.capabilities();
    const reviewProvider = caps && caps.suite_review ? caps.suite_review.provider : null;
    elements.suiteReviewRun.disabled = !pid || !planReady || Boolean(running);
    elements.suiteReviewRun.textContent = running ? "检查中…" : "运行本地确定性检查";
    elements.suiteAiReviewRun.disabled = !pid || !planReady || Boolean(running)
      || !reviewProvider || reviewProvider.configured === false;
    if (!report) {
      elements.suiteReviewStatus.textContent = pid && planReady
        ? "尚未运行整套检查。"
        : "先在「方案」生成套图方案，再运行整套检查。";
      elements.suiteReviewNote.textContent = "";
    } else if (!current) {
      elements.suiteReviewStatus.textContent = "整套检查已过期：选择或输入在报告之后发生了变化，请重新运行。"
        + " 上一版：" + suiteReviewSummaryText(report);
      elements.suiteReviewNote.textContent = "";
    } else {
      elements.suiteReviewStatus.textContent = suiteReviewSummaryText(report);
      const vlm = report.vlm && report.vlm.outcome === "checked" ? report.vlm : null;
      elements.suiteReviewNote.textContent = vlm
        ? ("视觉复核：" + String(vlm.model_id || vlm.provider_id || "已完成")
           + (vlm.checked_at ? " · " + vlm.checked_at : ""))
        : "未做 AI 复核；当前确定性检查与人工采用仍是交付硬门。";
    }
    elements.suiteReviewFindings.innerHTML = "";
    if (!report) return;
    appendSuiteFindings(elements.suiteReviewFindings, report);
  }

  /**
   * 整套发现的单一投影（审核阶段与交付阶段共用，避免两套写法 / 两个事实来源）。
   * 只读传入的报告，重排成「严重度分组 + 逐条定位」；不写任何状态。
   */
  function appendSuiteFindings(container: HTMLElement, report: SuiteReviewReport): void {
    const findings = Array.isArray(report.findings) ? report.findings : [];
    const shown = findings.filter((item) => item && item.severity !== "PASS");
    if (shown.length === 0) {
      container.append(createElement("p", {
        className: "meta", text: "没有需要人工处理的整套发现。",
      }));
    }
    for (const severity of REVIEW_SEVERITY_ORDER) {
      const group = shown.filter((item) => item.severity === severity);
      if (!group.length) continue;
      container.append(createElement("p", {
        className: "meta suite-group", text: COMPARE_SEVERITY_TEXT[severity] || severity,
      }));
      for (const finding of group) {
        const row = createElement("div", {
          className: "suite-finding",
          attrs: { "data-rule-id": finding.rule_id, "data-severity": finding.severity },
        });
        row.append(createElement("span", {
          className: "badge " + (SEVERITY_BADGE[finding.severity] || "is-review-unknown"),
          text: COMPARE_SEVERITY_TEXT[finding.severity] || finding.severity,
        }));
        row.append(createElement("span", {
          className: "name", text: String(finding.title || finding.rule_id),
        }));
        row.append(createElement("p", { className: "meta", text: deps.localizeShotIds(finding.detail) }));
        for (const shotId of (Array.isArray(finding.affected_shot_ids) ? finding.affected_shot_ids : [])) {
          const jump = createElement("button", {
            text: "定位：" + deps.shotLabelOf(shotId), attrs: { type: "button", "data-shot-id": shotId },
          });
          jump.addEventListener("click", () => { jumpToReviewShot(shotId); });
          row.append(jump);
        }
        container.append(row);
      }
    }
    const passCount = findings.filter((item) => item && item.severity === "PASS").length;
    if (passCount > 0) {
      container.append(createElement("p", {
        className: "meta", text: "另 " + passCount + " 项确定性检查通过（细节在候选审核清单里）。",
      }));
    }
  }

  /** 交付门禁只做视图装配与动作转发：输入投影、去抖刷新与门禁状态归 reviewDelivery 所有。 */
  function requestGateRefresh(): void {
    deps.reviewDelivery.requestGateRefresh();
  }

  /** 门禁逐条：严重度徽标 + 说明 + 受影响 Shot 的定位入口。 */
  function renderDeliveryFindings(): void {
    const state = deps.reviewDelivery.projection().gate;
    const findings = state && Array.isArray(state.findings) ? state.findings : [];
    if (!findings.length) {
      elements.deliveryGate.append(createElement("p", {
        className: "meta",
        text: state && state.failed
          ? ("门禁检查失败：" + (state.message || "未知错误"))
          : "正在核对交付门禁…",
      }));
      return;
    }
    const rankOf = (severity: string): number =>
      GATE_SEVERITY_RANK[severity] === undefined ? 9 : GATE_SEVERITY_RANK[severity];
    const ordered = findings.slice().sort((left, right) => rankOf(left.severity) - rankOf(right.severity));
    for (const item of ordered) {
      const passed = item.severity === "PASS";
      const row = createElement("div", {
        className: "gate-finding" + (passed ? " is-pass" : ""),
        attrs: { "data-rule-id": item.rule_id, "data-severity": item.severity },
      });
      row.append(createElement("span", {
        className: "badge " + (SEVERITY_BADGE[item.severity] || "is-review-unknown"),
        text: COMPARE_SEVERITY_TEXT[item.severity] || item.severity,
      }));
      row.append(createElement("span", { className: "name", text: String(item.title || item.rule_id) }));
      // 通过项压成一行（信息不减、占位减半）；阻断项保留独立说明行便于逐条处理。
      row.append(createElement(passed ? "span" : "p", {
        className: "meta", text: deps.localizeShotIds(item.detail),
      }));
      // Unknown 的处置入口就是下面的「确认已知悉」；这里不再给会误导的跳图按钮。
      const jumpable = !passed && item.rule_id !== "export.unknown_acknowledged";
      for (const shotId of (jumpable && Array.isArray(item.affected_shot_ids)
        ? item.affected_shot_ids : [])) {
        const jump = createElement("button", {
          text: "去处理：" + deps.shotLabelOf(shotId), attrs: { type: "button", "data-shot-id": shotId },
        });
        jump.addEventListener("click", () => { jumpToReviewShot(shotId); });
        row.append(jump);
      }
      // 整套一致性阻断不是某一张图的问题：给「去运行整套检查」把使用者送回审核阶段的运行按钮。
      if (!passed && item.rule_id === "export.suite_review_current") {
        const jump = createElement("button", {
          text: "去运行整套检查", attrs: { type: "button", "data-suite-action": "run" },
        });
        jump.addEventListener("click", () => { jumpToSuiteCheck(); });
        row.append(jump);
      }
      elements.deliveryGate.append(row);
    }
  }

  /**
   * 交付页的整套检查投影（V2.6.15）：交付是最后决策点，门禁全绿只说明「硬检查通过」，
   * 不代表没有风险 —— 这里复读同一份 suite review 报告（单一权威），把非阻断的
   * 高风险/提醒连同定位入口摆到导出按钮前面；过期报告如实说明，阻断仍由门禁负责。
   */
  function renderDeliverySuite(): void {
    if (!elements.deliverySuiteStatus || !elements.deliverySuiteFindings) return;
    elements.deliverySuiteStatus.textContent = "";
    elements.deliverySuiteFindings.innerHTML = "";
    const entry = deps.reviewDelivery.projection().suite;
    const report = entry ? entry.report : null;
    if (!report) {
      elements.deliverySuiteStatus.textContent = deps.currentProjectId() && deps.inputs.suitePlan()
        ? "尚未运行整套检查；交付门禁会在缺失或不当前时阻断导出。"
        : "先在「方案」生成套图方案，再运行整套检查。";
      return;
    }
    const current = deps.currentProjectId() ? deps.reviewDelivery.projection().suiteCurrent : false;
    elements.deliverySuiteStatus.textContent = current
      ? suiteReviewSummaryText(report)
      : ("整套检查已过期：选择或输入在报告之后发生了变化，请回审核阶段重新运行。上一版："
         + suiteReviewSummaryText(report));
    appendSuiteFindings(elements.deliverySuiteFindings, report);
  }

  /** 待确认 Unknown：每条一个「确认已知悉」按钮；确认是 append-only 记录，不改写报告。 */
  function renderDeliveryUnknowns(): void {
    if (!elements.deliveryUnknowns) return;
    elements.deliveryUnknowns.innerHTML = "";
    const state = deps.reviewDelivery.projection().gate;
    const unknowns = state && Array.isArray(state.unknowns) ? state.unknowns : [];
    if (!unknowns.length) return;
    elements.deliveryUnknowns.append(createElement("p", {
      className: "meta", text: "未知项（模型无法判定）：逐条确认已知悉后才允许交付。",
    }));
    for (const unknown of unknowns) {
      const row = createElement("div", {
        className: "gate-unknown",
        attrs: { "data-rule-id": unknown.rule_id, "data-target-id": unknown.target_id },
      });
      row.append(createElement("span", { className: "name", text: String(unknown.title || unknown.rule_id) }));
      row.append(createElement("p", { className: "meta", text: String(unknown.detail || "") }));
      const button = createElement("button", {
        text: unknown.acknowledged === true ? "已确认" : "确认已知悉", attrs: { type: "button" },
      });
      button.disabled = unknown.acknowledged === true;
      button.addEventListener("click", () => { void acknowledgeUnknown(unknown, button); });
      row.append(button);
      elements.deliveryUnknowns.append(row);
    }
  }

  /** 确认只追加：document_id 由未知项身份派生，重复确认只新增版本。 */
  async function acknowledgeUnknown(
    unknown: UnknownItem,
    button: HTMLButtonElement,
  ): Promise<void> {
    if (!deps.currentProjectId()) return;
    const action = deps.beginAction();
    if (!action.projectId) return;
    clearError(elements.deliverError);
    button.disabled = true;
    try {
      const outcome = await deps.selectionAdoption.acknowledge(unknown);
      if (!action.alive()) return;
      await deps.reviewDelivery.refreshGate();
      if (!action.alive()) return;
      void outcome;
      elements.deliverStatus.textContent = "已记录「已知悉」（append-only，不作为通过证据）。";
    } catch (error) {
      if (action.alive()) {
        button.disabled = false;
        showError(elements.deliverError, errorMessageOf(error, "确认没有保存，请重试。"));
      }
    }
  }

  /** 最近一次交付包结果：刷新后仍有记录（无 blob 时只显示身份，不伪装可下载）。 */
  function renderDeliveryResult(): void {
    if (!elements.deliverResult) return;
    elements.deliverResult.innerHTML = "";
    const record = deps.reviewDelivery.projection().record;
    if (!record) {
      elements.deliverResult.hidden = true;
      return;
    }
    elements.deliverResult.hidden = false;
    elements.deliverResult.append(createElement("p", {
      className: "meta",
      text: "最近一次交付包：" + record.file_name + "（"
        + Math.round(record.byte_size / 1024) + " KB）",
    }));
    appendTech(elements.deliverResult,
      ["sha256 " + String(record.sha256).slice(0, 16) + "…"]);
    // 对象 URL 归视图持有：下载链接由各次导出命令即时创建，不进 owner。
    const url = downloadUrlByFile.get(record.sha256) || null;
    if (url) {
      elements.deliverResult.append(createElement("a", {
        text: "下载交付包",
        attrs: { href: url, download: record.file_name },
      }));
    }
  }

  /** 交付阶段：逐图采用状态 + 门禁清单 + Unknown 确认 + 生成交付包入口。 */
  function renderDeliveryGate(): void {
    if (!elements.deliveryGate) return;
    elements.deliveryGate.innerHTML = "";
    const shots = deps.shotSummaries();
    for (const shot of shots) {
      const state = deps.selectionStateOf(shot.shot_id);
      const row = createElement("div", {
        className: "gate-row", attrs: { "data-shot-id": shot.shot_id, "data-selection-state": state },
      });
      row.append(createElement("span", { className: "name", text: shot.label }));
      row.append(createElement("span", {
        className: "badge " + (state === "current" ? "is-adopted" : (state === "stale" ? "is-review-warn" : "is-empty")),
        text: state === "current" ? "已采用" : (state === "stale" ? "已采用（已过期）" : "未采用"),
      }));
      row.append(createElement("span", {
        className: "meta", text: shot.required === true ? "必需图" : "可选图",
      }));
      if (state !== "current") {
        const jump = createElement("button", { text: "去审核", attrs: { type: "button" } });
        jump.addEventListener("click", () => { deps.selectStage("review"); });
        row.append(jump);
      }
      elements.deliveryGate.append(row);
    }
    renderDeliveryFindings();
    renderDeliverySuite();
    renderDeliveryUnknowns();
    renderDeliveryResult();
    const requiredShots = shots.filter((shot) => shot.required === true);
    const pending = requiredShots.filter((shot) => deps.selectionStateOf(shot.shot_id) !== "current");
    const projection = deps.reviewDelivery.projection();
    const state = projection.gate;
    elements.deliverExport.disabled = !(state && state.ready_to_export === true) || Boolean(projection.exporting);
    elements.deliverStatus.textContent = !shots.length
      ? "还没有套图方案。"
      : (projection.exporting
        ? "正在生成交付包…"
        : (pending.length
          ? "还差 " + pending.length + " 张必需图没有当前有效的采用。"
          : (!state || state.failed || !state.findings.length
            ? "正在核对交付门禁…"
            : (state.ready_to_export
              ? "交付门禁通过：可以生成交付包（只包含已采用的候选）。"
              : "交付门禁未通过：" + state.blocking.length + " 条阻断，逐条处理后才能生成。"))));
  }

  /** 两类导出共用下载：blob → 对象 URL → 一次性锚点点击；URL 记在本视图，close 时释放。 */
  function downloadArtifact(artifact: { bytes: Uint8Array; file_name: string }): void {
    const blob = new Blob([artifact.bytes.slice()], { type: "application/zip" });
    const url = URL.createObjectURL(blob);
    createdUrls.push(url);
    const record = deps.reviewDelivery.projection().record;
    if (record) downloadUrlByFile.set(record.sha256, url);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = artifact.file_name;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
  }

  /** 完整项目包导出（含完整历史，可在别的浏览器导入）。 */
  async function handleProjectExport(): Promise<void> {
    const action = deps.beginAction();
    if (!action.projectId) return;
    clearError(elements.deliverError);
    elements.deliverStatus.textContent = "正在打包完整项目…";
    try {
      const outcome = await deps.reviewDelivery.exportProject();
      if (!action.alive() || !outcome.artifact) return;
      downloadArtifact(outcome.artifact);
      elements.deliverStatus.textContent = "已导出项目包（含完整历史，可在别的浏览器导入）。";
    } catch (error) {
      if (action.alive()) {
        elements.deliverStatus.textContent = "";
        showError(elements.deliverError, errorMessageOf(error, "导出失败，请重试。"));
      }
    }
  }

  /** 生成交付包：门禁未通过时 owner 抛错，这里只翻译结果，不做批次策略。 */
  async function handleDeliveryExport(): Promise<void> {
    const action = deps.beginAction();
    if (!action.projectId || !deps.currentProjectId()) return;
    clearError(elements.deliverError);
    renderDeliveryGate();
    try {
      const outcome = await deps.reviewDelivery.exportDelivery();
      if (!action.alive()) return;
      if (outcome && outcome.skipped) return;
      if (outcome && outcome.artifact) {
        downloadArtifact(outcome.artifact);
        elements.deliverStatus.textContent = "已生成交付包（" + (outcome.includedShots || 0)
          + " 张图；记录已追加，不覆盖历史）。";
      }
    } catch (error) {
      if (action.alive()) {
        elements.deliverStatus.textContent = "交付包未生成。";
        showError(elements.deliverError, errorMessageOf(error, "生成交付包失败，请重试。"));
      }
    } finally {
      if (action.alive()) renderDeliveryGate();
    }
  }

  /** 门禁与整套结论同轮渲染；调用方（装配壳/owner changed）只调这一个入口。 */
  function render(): void {
    renderSuitePanel();
    renderDeliveryGate();
  }

  /** 释放本视图创建的对象 URL；不碰其他视图的 URL 池。 */
  function dispose(): void {
    for (const url of createdUrls) URL.revokeObjectURL(url);
    createdUrls.length = 0;
    downloadUrlByFile.clear();
  }

  return {
    render,
    requestGateRefresh,
    runSuiteReview,
    handleProjectExport,
    handleDeliveryExport,
    dispose,
  };
}
