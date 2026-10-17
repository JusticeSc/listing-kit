/**
 * 交付视图（设计 §2.1 的第四个视图）：交付阶段逐图采用状态、门禁清单、Unknown 知悉、
 * 整套检查结论投影与两类导出。
 *
 * 边界（设计 §10.1）：这里只持展开/焦点与**自己创建**的对象 URL；不写库、不发网络、
 * 不重算门禁判定、不组 manifest/ZIP。业务执行与判定归 reviewDelivery / selectionAdoption。
 *
 * P5（#10 前端渲染迁移）：整套检查卡与交付卡的**全部**内容 —— 标题、工具行、运行/导出按钮、
 * 状态与错误行、门禁行、发现、Unknown 列表、整套结论、交付结果 —— 都由 lit-html 模板投影；
 * index 只留两个空壳（`#suite-review-card` / `#delivery-card`），本视图不再持任何内部句柄，
 * 也不再逐控件挂监听（动作全走模板 @event）。命令式写入只剩模板内部由状态决定的
 * `?disabled` / `?hidden`，没有第二套事实来源。
 *
 * TypeScript 迁移（计划 §9 V2.R7.5）：本文件是唯一手工维护实现；浏览器产物由 Vite 生成。
 */
import { html, nothing, render as renderLit } from "lit-html";
import { repeat } from "lit-html/directives/repeat.js";
import { COMPARE_SEVERITY_TEXT, REVIEW_SEVERITY_ORDER, suiteReviewSummaryText } from "../domain/index.js";
import { SEVERITY_BADGE, errorMessageOf } from "./dom.js";
import type { ReviewDeliveryModule } from "../review-delivery.js";
import type { SelectionAdoptionModule } from "../selection-adoption.js";
import type { GateFinding, ReviewSeverity, SuiteReviewReport, UnknownItem } from "../domain/type-contracts.js";
import type { ActionSnapshot } from "../session.js";

/** 方案投影里的 shot 形状（视图只读 label/required，不重算方案）。 */
export type SuiteShotSummary = { shot_id: string; label: string; required?: boolean };

/** 本视图只持两个空壳挂载点：整套检查卡（审核阶段）与交付卡（交付阶段）。 */
export type DeliveryElements = {
  /** 审核阶段的整套检查卡根（内容全归模板）。 */
  suiteReviewCard: HTMLElement;
  /** 交付阶段的交付卡根（门禁/整套结论/Unknown/导出全归模板）。 */
  deliveryCard: HTMLElement;
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
  /** 跨视图定位归工作区：审核卡 DOM 由审核视图持有，本视图只发意图。 */
  focusReviewShot(shotId: string): void;
  focusSuiteCheck(): void;
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

/** 交付逐图采用行（只读投影）。 */
type GateRowView = {
  shotId: string;
  label: string;
  state: string;
  required: boolean;
};

/** 门禁发现行：定位入口按 severity/rule 决定，Unknown 只留确认入口。 */
type GateFindingView = {
  key: string;
  ruleId: string;
  severity: ReviewSeverity;
  title: string;
  detail: string;
  passed: boolean;
  shotIds: string[];
  suiteAction: boolean;
};

/** 待确认未知项：key 由规则 + 目标派生，作为模板与在飞集合的身份。 */
type UnknownView = {
  key: string;
  ruleId: string;
  targetId: string;
  title: string;
  detail: string;
  acknowledged: boolean;
  item: UnknownItem;
};

/** 整套结论的单一投影：分组标题与逐条发现同一序列，null 分组标题不伪造 finding。 */
type SuiteEntryView =
  | { kind: "group"; key: string; text: string }
  | {
      kind: "finding"; key: string; ruleId: string; severity: ReviewSeverity;
      title: string; detail: string; shotIds: string[];
    };

type SuiteView = {
  entries: SuiteEntryView[];
  empty: string;
  passCount: number;
};

const EMPTY_SUITE_VIEW: SuiteView = { entries: [], empty: "", passCount: 0 };

/** 最近一次交付包（无 blob 时只显示身份，不伪装可下载）。 */
type DeliveryResultView = {
  text: string;
  sha: string;
  fileName: string;
};

/**
 * 交付视图工厂。
 * @param args.elements 本视图负责的两个空壳挂载点
 * @param args.deps 窄依赖：业务命令/投影 + 装配期注入的投影回调
 */
export function createDeliveryView(
  { elements, deps }: { elements: DeliveryElements; deps: DeliveryViewDeps },
): DeliveryView {
  /** 对象 URL 归视图持有：下载链接由各次导出命令即时创建，不进 owner，dispose 时释放。 */
  const downloadUrlByFile = new Map<string, string>();
  const createdUrls: string[] = [];

  /**
   * 单一 UI 状态：模板只消费它（静态控件的能力、文案与可见性都由它投影）。
   * 门禁/整套结论/交付记录仍是 reviewDelivery 的只读投影，这里只放「就地呈现」的部分。
   */
  const state: {
    rows: GateRowView[];
    findings: GateFindingView[];
    gatePlaceholder: string;
    unknowns: UnknownView[];
    pendingAcks: Set<string>;
    result: DeliveryResultView | null;
    suiteStatus: string;
    suiteNote: string;
    suiteError: string;
    suiteView: SuiteView;
    suiteRunDisabled: boolean;
    suiteRunLabel: string;
    suiteAiDisabled: boolean;
    deliverySuiteStatus: string;
    deliverySuiteView: SuiteView;
    deliverStatus: string;
    deliverError: string;
    exportDisabled: boolean;
  } = {
    rows: [],
    findings: [],
    gatePlaceholder: "正在核对交付门禁…",
    unknowns: [],
    pendingAcks: new Set(),
    result: null,
    suiteStatus: "尚未运行整套检查。",
    suiteNote: "",
    suiteError: "",
    suiteView: EMPTY_SUITE_VIEW,
    suiteRunDisabled: true,
    suiteRunLabel: "运行本地确定性检查",
    suiteAiDisabled: true,
    deliverySuiteStatus: "",
    deliverySuiteView: EMPTY_SUITE_VIEW,
    deliverStatus: "",
    deliverError: "",
    exportDisabled: true,
  };

  /* ------------------------------------------------------------- 模板片段 */

  function gateFindingTemplate(finding: GateFindingView) {
    return html`
      <div
        class="gate-finding${finding.passed ? " is-pass" : ""}"
        data-rule-id=${finding.ruleId}
        data-severity=${finding.severity}
      >
        <span class="badge ${SEVERITY_BADGE[finding.severity] || "is-review-unknown"}">${COMPARE_SEVERITY_TEXT[finding.severity] || finding.severity}</span>
        <span class="name">${finding.title}</span>
        ${finding.passed
          ? html`<span class="meta">${finding.detail}</span>`
          : html`<p class="meta">${finding.detail}</p>`}
        ${repeat(finding.shotIds, (shotId) => shotId, (shotId) => html`
          <button type="button" data-shot-id=${shotId} @click=${() => jumpToReviewShot(shotId)}>${"去处理：" + deps.shotLabelOf(shotId)}</button>
        `)}
        ${finding.suiteAction
          ? html`<button type="button" data-suite-action="run" @click=${() => jumpToSuiteCheck()}>去运行整套检查</button>`
          : nothing}
      </div>
    `;
  }

  /** 交付门禁：逐图采用行 + 按严重度排序的发现（互相内嵌在同一个容器里，保持阅读顺序）。 */
  function gateTemplate() {
    return html`
      ${repeat(state.rows, (row) => row.shotId, (row) => html`
        <div class="gate-row" data-shot-id=${row.shotId} data-selection-state=${row.state}>
          <span class="name">${row.label}</span>
          <span class="badge ${row.state === "current" ? "is-adopted" : (row.state === "stale" ? "is-review-warn" : "is-empty")}">${row.state === "current" ? "已采用" : (row.state === "stale" ? "已采用（已过期）" : "未采用")}</span>
          <span class="meta">${row.required ? "必需图" : "可选图"}</span>
          ${row.state !== "current"
            ? html`<button type="button" @click=${() => deps.selectStage("review")}>去审核</button>`
            : nothing}
        </div>
      `)}
      ${state.findings.length
        ? repeat(state.findings, (finding) => finding.key, (finding) => gateFindingTemplate(finding))
        : html`<p class="meta">${state.gatePlaceholder}</p>`}
    `;
  }

  /** 待确认 Unknown：每条一个「确认已知悉」按钮；确认是 append-only 记录，不改写报告。 */
  function unknownsTemplate() {
    if (!state.unknowns.length) return nothing;
    return html`
      <p class="meta">未知项（模型无法判定）：逐条确认已知悉后才允许交付。</p>
      ${repeat(state.unknowns, (unknown) => unknown.key, (unknown) => html`
        <div class="gate-unknown" data-rule-id=${unknown.ruleId} data-target-id=${unknown.targetId}>
          <span class="name">${unknown.title}</span>
          <p class="meta">${unknown.detail}</p>
          <button
            type="button"
            ?disabled=${unknown.acknowledged || state.pendingAcks.has(unknown.key)}
            @click=${() => { void acknowledgeUnknown(unknown); }}
          >${unknown.acknowledged ? "已确认" : "确认已知悉"}</button>
        </div>
      `)}
    `;
  }

  function resultTemplate() {
    const record = state.result;
    if (!record) return nothing;
    const url = downloadUrlByFile.get(record.sha) || null;
    return html`
      <p class="meta">${record.text}</p>
      <details class="tech-details">
        <summary>技术详情</summary>
        <p class="meta tech-body">${"sha256 " + record.sha.slice(0, 16) + "…"}</p>
      </details>
      ${url ? html`<a href=${url} download=${record.fileName}>下载交付包</a>` : nothing}
    `;
  }

  function suiteEntriesTemplate(view: SuiteView) {
    return html`
      ${view.empty ? html`<p class="meta">${view.empty}</p>` : nothing}
      ${repeat(view.entries, (entry) => entry.key, (entry) => (entry.kind === "group"
        ? html`<p class="meta suite-group">${entry.text}</p>`
        : html`
            <div class="suite-finding" data-rule-id=${entry.ruleId} data-severity=${entry.severity}>
              <span class="badge ${SEVERITY_BADGE[entry.severity] || "is-review-unknown"}">${COMPARE_SEVERITY_TEXT[entry.severity] || entry.severity}</span>
              <span class="name">${entry.title}</span>
              <p class="meta">${entry.detail}</p>
              ${repeat(entry.shotIds, (shotId) => shotId, (shotId) => html`
                <button type="button" data-shot-id=${shotId} @click=${() => jumpToReviewShot(shotId)}>${"定位：" + deps.shotLabelOf(shotId)}</button>
              `)}
            </div>
          `))}
      ${view.passCount > 0
        ? html`<p class="meta">${"另 " + view.passCount + " 项确定性检查通过（细节在候选审核清单里）。"}</p>`
        : nothing}
    `;
  }

  /** 整套一致性卡（审核阶段）：index 只留 `<section id="suite-review-card" class="card">`。 */
  function suiteCardTemplate() {
    return html`
      <div class="card-head">
        <h4 id="suite-review-title">整套一致性</h4>
        <p id="suite-review-status" class="meta" role="status">${state.suiteStatus}</p>
      </div>
      <div class="toolbar">
        <button id="suite-review-run" type="button" ?disabled=${state.suiteRunDisabled}
          @click=${() => { void runSuiteReview(); }}>${state.suiteRunLabel}</button>
        <button id="suite-ai-review-run" type="button" ?disabled=${state.suiteAiDisabled}
          @click=${() => { void runSuiteReview({ ai: true }); }}>AI 复核当前采用套图（可选）</button>
        <span id="suite-review-note" class="meta">${state.suiteNote}</span>
      </div>
      <div id="suite-review-findings" class="suite-findings">${suiteEntriesTemplate(state.suiteView)}</div>
      <p id="suite-review-error" class="error" role="alert" ?hidden=${state.suiteError.length === 0}>${state.suiteError}</p>
    `;
  }

  /** 交付卡（交付阶段）：门禁 + 整套结论 + Unknown 知悉 + 两类导出 + 结果/错误同一投影。 */
  function deliveryCardTemplate() {
    return html`
      <div class="card-head">
        <h4 id="deliver-gate-title">交付门禁</h4>
        <p class="meta">交付包只包含已采用的候选；整套一致性与确定性导出检查通过后才允许生成。</p>
      </div>
      <div id="delivery-gate" class="delivery-gate">${gateTemplate()}</div>
      <section id="delivery-suite" class="delivery-suite" aria-labelledby="delivery-suite-title">
        <h5 id="delivery-suite-title" class="delivery-suite-title">整套检查结论</h5>
        <p id="delivery-suite-status" class="meta" role="status">${state.deliverySuiteStatus}</p>
        <div id="delivery-suite-findings" class="suite-findings">${suiteEntriesTemplate(state.deliverySuiteView)}</div>
      </section>
      <div id="delivery-unknowns" class="delivery-unknowns">${unknownsTemplate()}</div>
      <div class="toolbar">
        <button id="deliver-export" class="primary" type="button" ?disabled=${state.exportDisabled}
          @click=${() => { void handleDeliveryExport(); }}>生成交付包（ZIP）</button>
        <button id="deliver-project-package" type="button"
          @click=${() => { void handleProjectExport(); }}>导出项目包（完整历史）</button>
        <span id="deliver-status" class="meta" role="status">${state.deliverStatus}</span>
      </div>
      <div id="delivery-result" class="delivery-result" ?hidden=${!state.result}>${resultTemplate()}</div>
      <p id="deliver-error" class="error" role="alert" ?hidden=${state.deliverError.length === 0}>${state.deliverError}</p>
    `;
  }

  function renderSuiteCard(): void {
    renderLit(suiteCardTemplate(), elements.suiteReviewCard);
  }

  function renderDeliveryCard(): void {
    renderLit(deliveryCardTemplate(), elements.deliveryCard);
  }

  /* ------------------------------------------------------------- 整套结论 */

  /**
   * 整套发现的单一投影（审核阶段与交付阶段共用，避免两套写法 / 两个事实来源）。
   * 只读传入的报告，重排成「严重度分组 + 逐条定位」；不写任何状态。
   */
  function suiteViewOf(report: SuiteReviewReport | null): SuiteView {
    if (!report) return EMPTY_SUITE_VIEW;
    const findings = Array.isArray(report.findings) ? report.findings : [];
    const shown = findings.filter((item) => item && item.severity !== "PASS");
    const entries: SuiteEntryView[] = [];
    for (const severity of REVIEW_SEVERITY_ORDER) {
      const group = shown.filter((item) => item.severity === severity);
      if (!group.length) continue;
      entries.push({
        kind: "group", key: "group:" + severity, text: COMPARE_SEVERITY_TEXT[severity] || severity,
      });
      for (const finding of group) {
        entries.push({
          kind: "finding",
          key: "finding:" + finding.rule_id + ":" + entries.length,
          ruleId: finding.rule_id,
          severity: finding.severity,
          title: String(finding.title || finding.rule_id),
          detail: deps.localizeShotIds(finding.detail),
          shotIds: Array.isArray(finding.affected_shot_ids) ? finding.affected_shot_ids : [],
        });
      }
    }
    return {
      entries,
      empty: shown.length === 0 ? "没有需要人工处理的整套发现。" : "",
      passCount: findings.filter((item) => item && item.severity === "PASS").length,
    };
  }

  /**
   * 整套一致性分区：状态行、运行按钮能力/文案、附注与发现全部进 UI 状态，最后同轮渲染卡片。
   */
  function renderSuitePanel(): void {
    const projection = deps.reviewDelivery.projection();
    const entry = projection.suite;
    const report = entry ? entry.report : null;
    const current = projection.suiteCurrent;
    const running = projection.running;
    const pid = deps.currentProjectId();
    const planReady = Boolean(deps.inputs.suitePlan());
    const caps = deps.capabilities();
    const reviewProvider = caps && caps.suite_review ? caps.suite_review.provider : null;
    state.suiteRunDisabled = !pid || !planReady || Boolean(running);
    state.suiteRunLabel = running ? "检查中…" : "运行本地确定性检查";
    state.suiteAiDisabled = !pid || !planReady || Boolean(running)
      || !reviewProvider || reviewProvider.configured === false;
    if (!report) {
      state.suiteStatus = pid && planReady
        ? "尚未运行整套检查。"
        : "先在「方案」生成套图方案，再运行整套检查。";
      state.suiteNote = "";
    } else if (!current) {
      state.suiteStatus = "整套检查已过期：选择或输入在报告之后发生了变化，请重新运行。"
        + " 上一版：" + suiteReviewSummaryText(report);
      state.suiteNote = "";
    } else {
      state.suiteStatus = suiteReviewSummaryText(report);
      const vlm = report.vlm && report.vlm.outcome === "checked" ? report.vlm : null;
      state.suiteNote = vlm
        ? ("视觉复核：" + String(vlm.model_id || vlm.provider_id || "已完成")
           + (vlm.checked_at ? " · " + vlm.checked_at : ""))
        : "未做 AI 复核；当前确定性检查与人工采用仍是交付硬门。";
    }
    state.suiteView = suiteViewOf(report);
    renderSuiteCard();
  }

  /** 交付门禁只做视图装配与动作转发：输入投影、去抖刷新与门禁状态归 reviewDelivery 所有。 */
  function requestGateRefresh(): void {
    deps.reviewDelivery.requestGateRefresh();
  }

  /**
   * 交付页的整套检查投影（V2.6.15）：交付是最后决策点，门禁全绿只说明「硬检查通过」，
   * 不代表没有风险 —— 这里复读同一份 suite review 报告（单一权威）。
   */
  function renderDeliverySuite(): void {
    const projection = deps.reviewDelivery.projection();
    const entry = projection.suite;
    const report = entry ? entry.report : null;
    if (!report) {
      state.deliverySuiteStatus = deps.currentProjectId() && deps.inputs.suitePlan()
        ? "尚未运行整套检查；交付门禁会在缺失或不当前时阻断导出。"
        : "先在「方案」生成套图方案，再运行整套检查。";
      state.deliverySuiteView = EMPTY_SUITE_VIEW;
      return;
    }
    const current = deps.currentProjectId() ? projection.suiteCurrent : false;
    state.deliverySuiteStatus = current
      ? suiteReviewSummaryText(report)
      : ("整套检查已过期：选择或输入在报告之后发生了变化，请回审核阶段重新运行。上一版："
         + suiteReviewSummaryText(report));
    state.deliverySuiteView = suiteViewOf(report);
  }

  /* --------------------------------------------------------------- 门禁 */

  /** 最近一次交付包结果：刷新后仍有记录（无 blob 时只显示身份，不伪装可下载）。 */
  function projectDeliveryResult(): void {
    const record = deps.reviewDelivery.projection().record;
    if (!record) {
      state.result = null;
      return;
    }
    state.result = {
      text: "最近一次交付包：" + record.file_name + "（" + Math.round(record.byte_size / 1024) + " KB）",
      sha: String(record.sha256),
      fileName: record.file_name,
    };
  }

  /** 交付阶段：逐图采用状态 + 门禁清单 + Unknown 确认 + 生成交付包入口（全部进状态后渲染）。 */
  function renderDeliveryGate(): void {
    const shots = deps.shotSummaries();
    state.rows = shots.map((shot) => ({
      shotId: shot.shot_id,
      label: shot.label,
      state: deps.selectionStateOf(shot.shot_id),
      required: shot.required === true,
    }));
    const projection = deps.reviewDelivery.projection();
    const gate = projection.gate;
    const findings: GateFinding[] = gate && Array.isArray(gate.findings) ? gate.findings : [];
    state.gatePlaceholder = gate && gate.failed
      ? ("门禁检查失败：" + (gate.message || "未知错误"))
      : "正在核对交付门禁…";

    const ordered = findings.slice().sort((left, right) => {
      const leftRank = GATE_SEVERITY_RANK[left.severity];
      const rightRank = GATE_SEVERITY_RANK[right.severity];
      return (leftRank === undefined ? 9 : leftRank) - (rightRank === undefined ? 9 : rightRank);
    });
    state.findings = ordered.map((item, index) => ({
      key: String(item.rule_id) + ":" + index,
      ruleId: String(item.rule_id),
      severity: item.severity,
      title: String(item.title || item.rule_id),
      detail: deps.localizeShotIds(item.detail),
      passed: item.severity === "PASS",
      // Unknown 的处置入口就是下面的「确认已知悉」；这里不再给会误导的跳图按钮。
      shotIds: (item.severity !== "PASS" && item.rule_id !== "export.unknown_acknowledged"
        && Array.isArray(item.affected_shot_ids)) ? item.affected_shot_ids : [],
      // 整套一致性阻断不是某一张图的问题：给「去运行整套检查」把使用者送回审核阶段的运行按钮。
      suiteAction: item.severity !== "PASS" && item.rule_id === "export.suite_review_current",
    }));

    const unknowns: UnknownItem[] = gate && Array.isArray(gate.unknowns) ? gate.unknowns : [];
    state.unknowns = unknowns.map((item, index) => ({
      key: String(item.rule_id) + ":" + String(item.target_id) + ":" + index,
      ruleId: String(item.rule_id),
      targetId: String(item.target_id),
      title: String(item.title || item.rule_id),
      detail: String(item.detail || ""),
      acknowledged: item.acknowledged === true,
      item,
    }));
    // 已不在当前门禁里的待确认项不再占着在飞集合（重新核对后按钮必须回报真实状态）。
    for (const key of state.pendingAcks) {
      if (!state.unknowns.some((unknown) => unknown.key === key)) state.pendingAcks.delete(key);
    }

    projectDeliveryResult();

    const requiredShots = state.rows.filter((row) => row.required);
    const pending = requiredShots.filter((row) => row.state !== "current");
    state.exportDisabled = !(gate && gate.ready_to_export === true) || Boolean(projection.exporting);
    state.deliverStatus = !state.rows.length
      ? "还没有套图方案。"
      : (projection.exporting
        ? "正在生成交付包…"
        : (pending.length
          ? "还差 " + pending.length + " 张必需图没有当前有效的采用。"
          : (!gate || gate.failed || !gate.findings.length
            ? "正在核对交付门禁…"
            : (gate.ready_to_export
              ? "交付门禁通过：可以生成交付包（只包含已采用的候选）。"
              : "交付门禁未通过：" + gate.blocking.length + " 条阻断，逐条处理后才能生成。"))));

    renderDeliverySuite();
    renderDeliveryCard();
  }

  /** 确认只追加：document_id 由未知项身份派生，重复确认只新增版本。 */
  async function acknowledgeUnknown(unknown: UnknownView): Promise<void> {
    if (!deps.currentProjectId()) return;
    const action = deps.beginAction();
    if (!action.projectId) return;
    state.deliverError = "";
    state.pendingAcks.add(unknown.key);
    renderDeliveryCard();
    try {
      const outcome = await deps.selectionAdoption.acknowledge(unknown.item);
      if (!action.alive()) return;
      await deps.reviewDelivery.refreshGate();
      if (!action.alive()) return;
      void outcome;
      state.pendingAcks.delete(unknown.key);
      renderDeliveryGate();
      state.deliverStatus = "已记录「已知悉」（append-only，不作为通过证据）。";
      renderDeliveryCard();
    } catch (error) {
      if (action.alive()) {
        state.pendingAcks.delete(unknown.key);
        state.deliverError = errorMessageOf(error, "确认没有保存，请重试。");
        renderDeliveryCard();
      }
    }
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

  /** 整套检查只做视图装配与动作转发：执行、报告与门禁刷新归 reviewDelivery 所有。 */
  async function runSuiteReview({ ai = false }: { ai?: boolean } = {}): Promise<void> {
    const action = deps.beginAction();
    if (!action.projectId || !action.alive()) return;
    state.suiteError = "";
    try {
      const outcome = await deps.reviewDelivery.runSuiteReview({ ai });
      if (!action.alive()) return;
      if (outcome && outcome.failed) {
        state.suiteError = errorMessageOf(outcome.message || outcome.reason,
          "整套检查没有保存；之前的报告保留。");
      }
    } catch (error) {
      if (action.alive()) {
        state.suiteError = errorMessageOf(error, "整套检查没有保存；之前的报告保留。");
      }
    } finally {
      if (action.alive()) { renderSuitePanel(); deps.reviewDelivery.requestGateRefresh(); }
    }
  }

  /**
   * 跨阶段定位审核卡：审核卡 DOM 由审核视图持有，这里只把意图交回工作区，
   * 不直接抓另一个视图的节点（P5 不留跨视图 querySelector）。
   */
  function jumpToReviewShot(shotId: string): void {
    deps.selectStage("review");
    deps.focusReviewShot(shotId);
  }

  /** 门禁：整套一致性阻断不属于任何一张图，定位回审核阶段的整套检查运行按钮。 */
  function jumpToSuiteCheck(): void {
    deps.selectStage("review");
    deps.focusSuiteCheck();
  }

  /** 完整项目包导出（含完整历史，可在别的浏览器导入）。 */
  async function handleProjectExport(): Promise<void> {
    const action = deps.beginAction();
    if (!action.projectId) return;
    state.deliverError = "";
    state.deliverStatus = "正在打包完整项目…";
    renderDeliveryCard();
    try {
      const outcome = await deps.reviewDelivery.exportProject();
      if (!action.alive() || !outcome.artifact) return;
      downloadArtifact(outcome.artifact);
      state.deliverStatus = "已导出项目包（含完整历史，可在别的浏览器导入）。";
      renderDeliveryCard();
    } catch (error) {
      if (action.alive()) {
        state.deliverStatus = "";
        state.deliverError = errorMessageOf(error, "导出失败，请重试。");
        renderDeliveryCard();
      }
    }
  }

  /** 生成交付包：门禁未通过时 owner 抛错，这里只翻译结果，不做批次策略。 */
  async function handleDeliveryExport(): Promise<void> {
    const action = deps.beginAction();
    if (!action.projectId || !deps.currentProjectId()) return;
    state.deliverError = "";
    renderDeliveryGate();
    try {
      const outcome = await deps.reviewDelivery.exportDelivery();
      if (!action.alive()) return;
      if (outcome && outcome.skipped) return;
      if (outcome && outcome.artifact) {
        downloadArtifact(outcome.artifact);
        state.deliverStatus = "已生成交付包（" + (outcome.includedShots || 0)
          + " 张图；记录已追加，不覆盖历史）。";
      }
    } catch (error) {
      if (action.alive()) {
        state.deliverStatus = "交付包未生成。";
        state.deliverError = errorMessageOf(error, "生成交付包失败，请重试。");
      }
    } finally {
      if (action.alive()) renderDeliveryGate();
    }
  }

  /** 门禁与整套结论同轮渲染；调用方（装配壳/owner changed）只调这一个入口。 */
  function renderAll(): void {
    renderSuitePanel();
    renderDeliveryGate();
  }

  /** 释放本视图创建的对象 URL；不碰其他视图的 URL 池。 */
  function dispose(): void {
    for (const url of createdUrls) URL.revokeObjectURL(url);
    createdUrls.length = 0;
    downloadUrlByFile.clear();
  }

  // 装配期先成形一次：两个空壳在第一个业务渲染之前就有内容（节点身份此后保持稳定）。
  renderAll();

  return {
    render: renderAll,
    requestGateRefresh,
    runSuiteReview,
    handleProjectExport,
    handleDeliveryExport,
    dispose,
  };
}
