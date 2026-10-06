// Generated from app/product_v2/ui/input-view.ts; edit the TS source and run `npm run build:frontend`.
/**
 * 输入视图（设计 §10.1 的第一个视图）：资料 → 商品理解 → 方案 三区的渲染与就地状态。
 *
 * 边界（设计 §10.1）：这里只持 DOM、展开/编辑与交互状态，以及自己创建的节点；不写库、
 * 不发网络、不重算业务判定。资料/事实/方案/风格/单图规格的唯一所有者是 project-inputs，
 * 本视图只经它的命令与投影读写；真正落库/派生/跨视图刷新都经 deps 回到工作区。
 *
 * TypeScript 迁移（计划 §9 V2.R7.5）：本文件是唯一手工维护实现；同名 `input-view.js`
 * 由 `npm run build:frontend` 生成，浏览器只消费生成的 `.js`。
 */
import { DIMENSION_AXES, DIMENSION_UNITS, FACT_SLOT_SCHEMA_VERSION, MAX_DIMENSIONS, SHOT_TEMPLATES, SLOT_VALUE_TYPES, addCustomShotToPlan, addShotFromTemplate, canAddSlot, canConfirmSlot, canDeleteSlot, canEditValue, checkFactSlot, coreSlotDefinition, copyShot, emptyShotSpecFromShot, emptyStyleSpec, intakeReadiness, isPlainObject, moveShot, recommendPlan, removeShot, seedSuitePlan, setShotFactBindings, shotReadiness, specChangeProjection, styleSpecDiff, suitePlanSummary, suiteSpecDigest, } from "../domain/index.js";
import { AUTHORITY_TEXT, EVIDENCE_TEXT, ROLE_TEXT, STATUS_TEXT, clearError, createElement, describeBlocking, errorMessageOf, formatValue, reviewRankOf, showError, splitLines, techDetails, } from "./dom.js";
/**
 * 输入视图工厂。
 * @param args.elements 本视图负责的 DOM 句柄
 * @param args.deps 窄依赖：输入面所有者命令/投影 + 工作区收尾回调
 */
export function createInputView({ elements, deps }) {
    /** 视图状态：最近一次分析摘要、未写入的提案问题、结果未知的待确认标记。 */
    let lastAnalyze = null;
    let analyzeRequiresConfirmation = false;
    let analyzeProblems = [];
    /** 槽位列表展开与就地编辑态（只属于本视图）。 */
    let showAll = false;
    let interaction = { slotId: null, mode: null };
    // 依赖别名：搬过来的实现保持原调用写法，装配面只经上面的窄接口进出。
    const inputs = deps.inputs;
    const beginAction = deps.beginAction;
    const draftInputPayload = deps.draftInput;
    const deriveAndApplyState = deps.deriveState;
    const renderAll = deps.renderWorkspace;
    const refreshStageShell = deps.refreshStageShell;
    const selectStage = deps.selectStage;
    const handleInternalError = deps.reportError;
    const localizeSlotTerms = deps.localizeSlotTerms;
    const suiteBlockingText = deps.suiteBlockingText;
    function dependencyCountOf(slotId) {
        let count = 0;
        for (const entry of inputs.slotEntries()) {
            if ((entry.slot.depends_on || []).includes(slotId))
                count += 1;
        }
        return count;
    }
    function updateDraftStatus() {
        const conflictState = inputs.conflict();
        const storedVersion = inputs.draftVersion();
        const storedName = inputs.intakeSnapshot().product_name;
        if (conflictState) {
            // R3.3 双标签陈旧编辑：就地报冲突，不静默胜出。文档历史是 append-only。
            if (conflictState.merged === true) {
                elements.intakeDraft.textContent = "另一个标签页已保存版本 v" + conflictState.version
                    + "：你的输入已按本地优先自动合并为新版本；请核对内容后再次保存确认。";
            }
            else if (Array.isArray(conflictState.unresolved) && conflictState.unresolved.length > 0) {
                elements.intakeDraft.textContent = "另一个标签页已保存版本 v" + conflictState.version
                    + "：有 " + conflictState.unresolved.length + " 项需要你逐项解决，请在冲突编辑器里处理。";
            }
            else {
                elements.intakeDraft.textContent = "检测到另一个标签页已保存版本 v" + conflictState.version
                    + "：你正在编辑的内容没有覆盖它；再次保存会追加为新版本。";
            }
            return;
        }
        elements.intakeDraft.textContent = storedVersion
            ? "草稿已保存 · 版本 " + storedVersion + (storedName ? "" : "（尚未填写商品名称）")
            : "还没有保存过草稿。";
    }
    function scheduleDraftSave() {
        inputs.scheduleDraftSave();
        elements.intakeDraft.textContent = "正在编辑…";
        renderAnalyze();
    }
    function saveIntakeNow() {
        return inputs.saveIntakeNow().then((ok) => deriveAndApplyState().then(() => ok));
    }
    function renderIntake() {
        const stored = inputs.intakeSnapshot();
        elements.intakeName.value = stored.product_name || "";
        elements.intakeDescription.value = stored.description || "";
        elements.intakePoints.value = (stored.selling_points || []).join("\n");
        elements.intakeFocus.value = stored.focus || "";
        updateDraftStatus();
    }
    /**
     * 冲突编辑器只读所有者的未解决项；解决后由 owner 合并/落库，这里不直接写仓库。
     */
    function renderConflictEditor() {
        const host = elements.intakeError.parentElement;
        const existing = host ? host.querySelector(".conflict-editor") : null;
        const conflictState = inputs.conflict();
        const unresolved = conflictState && Array.isArray(conflictState.unresolved)
            ? conflictState.unresolved : [];
        if (!conflictState || !unresolved.length) {
            if (existing)
                existing.remove();
            return;
        }
        if (existing)
            return; // 已有编辑器：保留用户已经做出的选择，不重建。
        const editor = document.createElement("div");
        editor.className = "conflict-editor";
        editor.setAttribute("role", "group");
        editor.setAttribute("aria-label", "双标签编辑冲突，需要人工逐项解决");
        const title = document.createElement("p");
        title.className = "meta";
        title.textContent = "另一个标签页已保存版本 v" + conflictState.version
            + "：以下字段两边都改了，请逐项选择保留哪一边。";
        editor.append(title);
        const picks = new Map();
        for (const item of unresolved) {
            const row = document.createElement("div");
            row.className = "conflict-row";
            row.dataset.field = item.field;
            const label = document.createElement("p");
            label.className = "name";
            label.textContent = "字段：" + item.field;
            const mineBtn = document.createElement("button");
            mineBtn.type = "button";
            mineBtn.textContent = "保留我的";
            mineBtn.setAttribute("aria-pressed", "true");
            const theirsBtn = document.createElement("button");
            theirsBtn.type = "button";
            theirsBtn.textContent = "用对方的";
            theirsBtn.setAttribute("aria-pressed", "false");
            picks.set(item.field, "mine");
            mineBtn.addEventListener("click", () => {
                picks.set(item.field, "mine");
                mineBtn.setAttribute("aria-pressed", "true");
                theirsBtn.setAttribute("aria-pressed", "false");
            });
            theirsBtn.addEventListener("click", () => {
                picks.set(item.field, "theirs");
                mineBtn.setAttribute("aria-pressed", "false");
                theirsBtn.setAttribute("aria-pressed", "true");
            });
            const mineText = document.createElement("p");
            mineText.className = "meta";
            mineText.textContent = "我的：" + String(item.mine === "" ? "（空）" : item.mine);
            const theirsText = document.createElement("p");
            theirsText.className = "meta";
            theirsText.textContent = "对方 v" + conflictState.version + "：" + String(item.theirs === "" ? "（空）" : item.theirs);
            row.append(label, theirsText, mineText, mineBtn, theirsBtn);
            editor.append(row);
        }
        const saveBtn = document.createElement("button");
        saveBtn.type = "button";
        saveBtn.className = "primary";
        saveBtn.textContent = "按我的选择保存为新版本";
        saveBtn.addEventListener("click", () => {
            const resolved = {};
            for (const item of unresolved) {
                resolved[item.field] = picks.get(item.field) === "theirs" ? "theirs" : "mine";
            }
            inputs.resolveConflict(resolved).then((ok) => {
                if (!ok)
                    return;
                editor.remove();
                renderIntake();
            }).catch((error) => {
                showError(elements.intakeError, errorMessageOf(error, "冲突解决没有保存，请重试。"));
            });
        });
        const cancelBtn = document.createElement("button");
        cancelBtn.type = "button";
        cancelBtn.textContent = "稍后处理";
        cancelBtn.addEventListener("click", () => { editor.remove(); });
        editor.append(saveBtn, cancelBtn);
        elements.intakeError.textContent = "";
        elements.intakeError.hidden = true;
        elements.intakeError.before(editor);
    }
    function gateProblems() {
        return intakeReadiness(draftInputPayload()).blocking;
    }
    function seesImages(provider) {
        const caps = isPlainObject(provider) && isPlainObject(provider.capabilities) ? provider.capabilities : {};
        return caps.vision === true || caps.supports_images === true;
    }
    function renderAnalyze() {
        const problems = gateProblems();
        const ready = problems.length === 0;
        const provider = deps.capabilities()?.provider;
        const vision = seesImages(provider);
        const imageCount = Math.min(inputs.references().length, 3);
        elements.analyzeNewAfterUnknown.hidden = !analyzeRequiresConfirmation;
        elements.analyzeNewAfterUnknown.disabled = inputs.isAnalysisRunning()
            || !ready || !provider || provider.configured === false;
        elements.analyzeRun.textContent = (lastAnalyze ? "再次" : "") + (vision ? "图文理解" : "仅文字理解") + "（可选）";
        elements.analyzeRun.disabled = inputs.isAnalysisRunning() || !ready || !provider || provider.configured === false;
        elements.analyzeGate.textContent = inputs.isAnalysisRunning() ? "理解中；不会自动重试…"
            : !ready ? "还缺：" + describeBlocking(problems, localizeSlotTerms)
                : !provider || provider.configured === false
                    ? "此用途缺少有效模型或凭据；请打开模型设置。人工填写不受影响。"
                    : "将发给 " + provider.model_id + "：当前名称、介绍、卖点与重点，"
                        + (vision ? imageCount + " 张实际图片（按列表顺序，主图优先，最多 3 张）"
                            : "仅参考图元数据，不发送图片字节")
                        + "。供应商按实际调用计费；不能据元数据宣称已经看图。";
        if (lastAnalyze) {
            elements.analyzeResult.hidden = false;
            elements.analyzeResult.textContent = "最近一次分析：" + lastAnalyze.slots + " 个提案，写入 "
                + lastAnalyze.applied + " 个槽位 · " + lastAnalyze.provider
                + (lastAnalyze.model ? "（" + lastAnalyze.model + "）" : "")
                + " · 原资料 v" + lastAnalyze.sourceVersion
                + (lastAnalyze.referenceImagesSent ? " · 已发送实际图片" : " · 未发送图片字节")
                + " · " + lastAnalyze.at + (lastAnalyze.summary ? " · " + lastAnalyze.summary : "");
        }
        else {
            elements.analyzeResult.hidden = true;
            elements.analyzeResult.textContent = "";
        }
        if (analyzeProblems.length) {
            const list = createElement("ul", { className: "inline-list" });
            for (const item of analyzeProblems)
                list.append(createElement("li", { text: item }));
            elements.analyzeError.replaceChildren(createElement("span", { text: "部分提案没有写入：" }), list);
            elements.analyzeError.hidden = false;
        }
    }
    let manualFactsPreparing = false;
    async function prepareManualFacts() {
        if (!deps.currentProjectId() || manualFactsPreparing)
            return;
        const action = beginAction();
        const pid = action.projectId;
        if (!pid)
            return;
        manualFactsPreparing = true;
        try {
            await inputs.ensureCoreSlots();
            if (!action.alive())
                return;
            await deriveAndApplyState();
            renderSlots();
            refreshStageShell();
        }
        catch (error) {
            if (action.alive())
                handleInternalError(error);
        }
        finally {
            manualFactsPreparing = false;
        }
    }
    async function runAnalyze({ allowNewAfterUnknown = false } = {}) {
        const action = beginAction();
        analyzeProblems = [];
        analyzeRequiresConfirmation = false;
        clearError(elements.analyzeError);
        const pending = inputs.runAnalysis({ allowNewAfterUnknown });
        renderAnalyze();
        try {
            const outcome = await pending;
            if (!action.alive())
                return;
            if (outcome.kind === "requires_confirmation") {
                analyzeRequiresConfirmation = true;
                showError(elements.analyzeError, "原分析结果仍未知，可能已经计费。不会自动重提；只有明确选择“另发新分析”才会再次发送，可能重复计费。");
            }
            else if (outcome.kind === "not_sent" || outcome.kind === "apply_failed") {
                showError(elements.analyzeError, outcome.message);
            }
            else if (outcome.kind === "failed" || outcome.kind === "unknown") {
                analyzeRequiresConfirmation = outcome.kind === "unknown";
                showError(elements.analyzeError, describeAnalyzeFailure(outcome.error, outcome.kind === "unknown"));
            }
            else if (outcome.kind === "stale") {
                showError(elements.analyzeError, "提案已保留在原资料 v" + outcome.record.source.version
                    + " 的分析记录中；当前资料已变化，没有写入当前事实。");
            }
            else if (outcome.kind === "applied") {
                const { proposal, applied, record } = outcome;
                analyzeProblems = applied.problems;
                lastAnalyze = {
                    at: new Date(record.updated_at).toLocaleString("zh-CN", { hour12: false }),
                    provider: proposal.meta.provider_id, model: proposal.meta.model_id,
                    slots: proposal.slots.length, applied: applied.applied, summary: proposal.summary,
                    sourceVersion: record.source.version, referenceImagesSent: record.reference_images_sent,
                };
                if (proposal.questions.length)
                    analyzeProblems.push("模型提出的问题：" + proposal.questions.join(" / "));
            }
        }
        catch (error) {
            if (action.alive())
                handleInternalError(error);
        }
        finally {
            if (action.alive()) {
                try {
                    await deriveAndApplyState();
                }
                catch (error) {
                    handleInternalError(error);
                }
                renderAll();
            }
        }
    }
    /**
     * 分析失败的可见摘要：人话在前，分类与重试策略是网关信封在前端的投影（§9.10），
     * 与落库记录同源，不在渲染层重算。结果未知时追加「可能已计费、不会自动重试」，
     * 不把未知说成失败，也不让用户以为系统会自己重发。
     */
    function describeAnalyzeFailure(error, unknown) {
        const parts = [String(errorMessageOf(error, "分析失败"))];
        // 网关信封在前端的投影：只读已知标量字段，形状由网关契约给出（§9.10）。
        const info = isPlainObject(error) ? error : {};
        parts.push("分类：" + String(info.family || "internal")
            + " / " + String(info.code || "INTERNAL_ERROR"));
        if (info.retry_policy)
            parts.push("重试策略：" + String(info.retry_policy));
        if (unknown) {
            parts.push("结果未知：这次请求可能已经产生结果。系统不会自动重试，请确认后再手动点击“重新分析”。");
        }
        return parts.join(" ");
    }
    function renderSlots() {
        elements.slotList.replaceChildren();
        const entries = inputs.slotEntries();
        const understandingBlocking = deps.understandingBlocking();
        const critical = entries.filter((entry) => entry.slot.critical === true);
        const confirmedCritical = critical.filter((entry) => entry.slot.status === "confirmed");
        const open = entries.filter((entry) => entry.slot.status !== "confirmed" && entry.slot.status !== "superseded");
        elements.slotsProgress.textContent = entries.length
            ? "必须确认的槽位 " + confirmedCritical.length + " / " + critical.length + " 已确认 · 待处理 "
                + open.length + " 项 · 共 " + entries.length + " 项"
                + (understandingBlocking.length
                    ? " · 还缺：" + describeBlocking(understandingBlocking, localizeSlotTerms) : "")
            : "还没有槽位。";
        elements.slotsToggle.textContent = showAll ? "只看待处理项" : "显示全部事实";
        elements.slotsToggle.setAttribute("aria-expanded", showAll ? "true" : "false");
        elements.slotsEmpty.hidden = entries.length > 0;
        const list = (showAll ? entries : open).slice();
        list.sort((left, right) => {
            const byRank = reviewRankOf(left) - reviewRankOf(right);
            if (byRank !== 0)
                return byRank;
            return left.slot.slot_id.localeCompare(right.slot.slot_id);
        });
        for (const entry of list)
            elements.slotList.append(slotRow(entry));
    }
    /** 某个 slot_id 的中文名（找不到就退回原样）；依赖与来源引用用它去掉工程感。 */
    /**
     */
    function slotLabelOfId(slotId) {
        for (const entry of inputs.slotEntries()) {
            if (entry.slot && entry.slot.slot_id === slotId)
                return entry.slot.label || slotId;
        }
        return slotId;
    }
    /** 主行只放人话：来源档 + 置信（「必须确认」已经是徽标，不再重复一次）。 */
    /**
     */
    function slotMetaText(entry) {
        const slot = entry.slot;
        const parts = [AUTHORITY_TEXT[slot.authority] || slot.authority];
        if (slot.confidence !== null && slot.confidence !== undefined) {
            parts.push("置信 " + Number(slot.confidence).toFixed(2));
        }
        return parts.join(" · ");
    }
    /**
     * 事实卡的工程标识（V2.6.16）：slot_id、版本、依赖、证据来源引用（字段名 / 资产哈希 /
     * 模型 id）一律进折叠的技术详情，主行只留人能判断的信息；追溯链不减，只是换了位置。
     */
    function slotTechLines(entry) {
        const slot = entry.slot;
        const lines = ["标识 " + slot.slot_id, "版本 v" + entry.version];
        if (slot.depends_on && slot.depends_on.length) {
            lines.push("依赖 " + slot.depends_on.map((id) => slotLabelOfId(id)).join("、"));
        }
        const refs = (Array.isArray(slot.evidence) ? slot.evidence : [])
            .map((item) => (item && item.ref ? String(item.ref) : ""))
            .filter((ref) => ref !== "");
        if (refs.length)
            lines.push("来源引用 " + refs.join("、"));
        return lines;
    }
    function slotRow(entry) {
        const slot = entry.slot;
        const status = slot.status;
        const row = createElement("li", { className: "slot-row", attrs: { "data-status": status } });
        row.dataset.slotId = slot.slot_id;
        // 验证用：必须确认是「推进阶段门禁」的判据之一，断言要能区分它与普通待补项。
        row.dataset.critical = slot.critical === true ? "1" : "0";
        const head = createElement("div", { className: "slot-head" });
        head.append(createElement("span", {
            className: "badge is-" + status, text: STATUS_TEXT[status] || status,
        }));
        head.append(createElement("span", { className: "name", text: slot.label }));
        if (slot.critical === true) {
            head.append(createElement("span", { className: "badge is-critical", text: "必须确认" }));
        }
        head.append(createElement("span", { className: "meta", text: slotMetaText(entry) }));
        row.append(head);
        const valueText = formatValue(slot);
        if (valueText) {
            row.append(createElement("div", { className: "slot-value", text: valueText }));
        }
        else {
            const hint = status === "conflict"
                ? "模型提案与已确认值不一致；请给出裁决值。"
                : status === "unknown" ? "已标记为未知；需要时再补值确认。"
                    : status === "superseded" ? "已移除（历史版本保留）。" : "还没有值。";
            row.append(createElement("div", { className: "slot-value is-empty", text: hint }));
        }
        if (Array.isArray(slot.evidence) && slot.evidence.length) {
            const list = createElement("ul", { className: "evidence" });
            for (const item of slot.evidence) {
                const label = EVIDENCE_TEXT[item.kind] || item.kind;
                list.append(createElement("li", {
                    className: "meta",
                    text: item.note ? label + "：" + item.note : label,
                }));
            }
            row.append(list);
        }
        const mode = interaction.mode;
        if (interaction.slotId === slot.slot_id && mode)
            row.append(slotEditor(entry, mode));
        row.append(slotActions(entry));
        const tech = techDetails(slotTechLines(entry));
        if (tech)
            row.append(tech);
        return row;
    }
    function slotActions(entry) {
        const slot = entry.slot;
        const actions = createElement("div", { className: "slot-actions" });
        const editing = interaction.slotId === slot.slot_id && interaction.mode === "edit";
        if (canConfirmSlot(slot, "user")) {
            const direct = slot.status === "proposed";
            const confirm = createElement("button", {
                className: "primary", text: direct ? "确认" : "填值并确认", attrs: { type: "button" },
            });
            confirm.addEventListener("click", () => {
                if (direct) {
                    handleSlotAction(entry, { action: "confirm", actor: "user" });
                }
                else {
                    interaction = { slotId: slot.slot_id, mode: "confirm" };
                    renderSlots();
                }
            });
            actions.append(confirm);
        }
        if (canEditValue(slot, "user")) {
            const edit = createElement("button", {
                text: editing ? "取消修改" : "修改", attrs: { type: "button" },
            });
            edit.addEventListener("click", () => {
                interaction = editing
                    ? { slotId: null, mode: null }
                    : { slotId: slot.slot_id, mode: "edit" };
                renderSlots();
            });
            actions.append(edit);
        }
        if (slot.status !== "unknown" && slot.status !== "superseded") {
            const unknown = createElement("button", { text: "标记未知", attrs: { type: "button" } });
            unknown.addEventListener("click", () => {
                handleSlotAction(entry, { action: "mark_unknown", actor: "user" });
            });
            actions.append(unknown);
        }
        if (canDeleteSlot(slot, { dependencyCount: dependencyCountOf(slot.slot_id) })) {
            const remove = createElement("button", {
                className: "danger", text: "删除（保留历史）", attrs: { type: "button" },
            });
            remove.addEventListener("click", () => {
                handleSlotAction(entry, { action: "supersede", actor: "user" });
            });
            actions.append(remove);
        }
        return actions;
    }
    function dimensionEditor(initial) {
        const list = createElement("div", { className: "dimension-editor", attrs: { id: "slot-editor-value" } });
        const rows = createElement("div", { className: "dimension-rows" });
        const add = createElement("button", { text: "添加测量", attrs: { type: "button" } });
        const axisLabels = { height: "高度", width: "宽度", length: "长度", depth: "深度",
            diameter: "直径", weight: "重量", volume: "容量", thickness: "厚度" };
        function appendRow(measurement = {}) {
            if (rows.children.length >= MAX_DIMENSIONS)
                return;
            const row = createElement("fieldset", { className: "dimension-row" });
            row.append(createElement("legend", { text: "已确认的测量（不猜数字）" }));
            for (const [key, label] of [["object", "测量对象"], ["axis", "轴向"],
                ["value", "数值"], ["unit", "单位"], ["source_basis", "来源依据"]]) {
                const wrapper = createElement("label", { text: label });
                const control = key === "axis" || key === "unit"
                    ? createElement("select")
                    : createElement("input", { attrs: { type: key === "value" ? "number" : "text",
                            step: key === "value" ? "any" : null, min: key === "value" ? "0" : null } });
                control.dataset.dimensionField = key;
                if (key === "axis" || key === "unit") {
                    control.append(createElement("option", { text: "请选择", attrs: { value: "" } }));
                    for (const value of key === "axis" ? DIMENSION_AXES : DIMENSION_UNITS) {
                        control.append(createElement("option", { text: axisLabels[value] || value, attrs: { value } }));
                    }
                }
                const fields = measurement;
                control.value = fields[key] == null ? "" : String(fields[key]);
                wrapper.append(control);
                row.append(wrapper);
            }
            const remove = createElement("button", { text: "删除这条测量", attrs: { type: "button" } });
            remove.addEventListener("click", () => { row.remove(); add.disabled = false; });
            row.append(remove);
            rows.append(row);
            add.disabled = rows.children.length >= MAX_DIMENSIONS;
        }
        for (const measurement of Array.isArray(initial) && initial.length ? initial : [{}])
            appendRow(measurement);
        add.addEventListener("click", () => appendRow());
        list.append(rows, add);
        return list;
    }
    function suggestedValue(slot) {
        for (const item of slot.evidence || []) {
            if (item && item.ref === "model_proposal" && typeof item.note === "string") {
                try {
                    return JSON.parse(item.note);
                }
                catch (error) {
                    return null;
                }
            }
        }
        return null;
    }
    function slotEditor(entry, mode) {
        const slot = entry.slot;
        const editor = createElement("div", { className: "slot-editor" });
        const field = createElement("div", { className: "field" });
        field.append(createElement("label", {
            text: mode === "confirm" ? "给出裁决值后确认" : "修改后的值",
            attrs: { for: "slot-editor-value" },
        }));
        const suggestion = suggestedValue(slot);
        let node;
        if (slot.value_type === "text_list") {
            const initial = Array.isArray(slot.value) ? slot.value
                : (Array.isArray(suggestion) ? suggestion : []);
            node = createElement("textarea", { attrs: { id: "slot-editor-value", rows: 3 } });
            node.value = initial.join("\n");
        }
        else if (slot.value_type === "dimension_list") {
            node = dimensionEditor(Array.isArray(slot.value) ? slot.value : suggestion);
        }
        else if (slot.value_type === "boolean") {
            node = createElement("select", { attrs: { id: "slot-editor-value" } });
            node.append(createElement("option", { text: "是", attrs: { value: "true" } }));
            node.append(createElement("option", { text: "否", attrs: { value: "false" } }));
            node.value = String(slot.value === true || (slot.value === null && suggestion === true));
        }
        else if (slot.value_type === "enum") {
            node = createElement("select", { attrs: { id: "slot-editor-value" } });
            for (const item of slot.enum_values || []) {
                node.append(createElement("option", { text: item, attrs: { value: item } }));
            }
            node.value = typeof slot.value === "string" ? slot.value
                : (typeof suggestion === "string" ? suggestion : "");
        }
        else {
            const initial = slot.value !== null && slot.value !== undefined ? String(slot.value)
                : (suggestion !== null && suggestion !== undefined ? String(suggestion) : "");
            node = createElement("input", {
                attrs: {
                    id: "slot-editor-value",
                    type: slot.value_type === "number" ? "number" : "text",
                    step: slot.value_type === "number" ? "any" : null,
                },
            });
            node.value = initial;
        }
        node.dataset.role = "value";
        field.append(node);
        editor.append(field);
        const toolbar = createElement("div", { className: "toolbar" });
        const submit = createElement("button", {
            className: "primary", text: mode === "confirm" ? "确认" : "保存", attrs: { type: "button" },
        });
        submit.addEventListener("click", () => {
            let value;
            try {
                value = readEditorValue(slot, node);
            }
            catch (error) {
                showError(elements.slotsError, errorMessageOf(error, "值不合法。"));
                return;
            }
            clearError(elements.slotsError);
            handleSlotAction(entry, mode === "confirm"
                ? { action: "confirm", actor: "user", value, source: "user_input" }
                : { action: "edit", actor: "user", value, source: "user_input" });
        });
        const cancel = createElement("button", { text: "取消", attrs: { type: "button" } });
        cancel.addEventListener("click", () => {
            interaction = { slotId: null, mode: null };
            renderSlots();
        });
        toolbar.append(submit, cancel);
        editor.append(toolbar);
        return editor;
    }
    function readEditorValue(slot, node) {
        if (slot.value_type === "dimension_list") {
            const values = Array.from(node.querySelectorAll(".dimension-row"), (row) => {
                const fields = {};
                for (const control of row.querySelectorAll("[data-dimension-field]")) {
                    const key = control.dataset.dimensionField;
                    if (!key)
                        continue;
                    fields[key] = key === "value" ? Number(control.value) : control.value.trim();
                }
                // 轴向/单位选项来自 DIMENSION_AXES / DIMENSION_UNITS 词表；checkFactSlot 再校验。
                return {
                    object: String(fields.object || ""),
                    axis: String(fields.axis || ""),
                    value: Number(fields.value),
                    unit: String(fields.unit || ""),
                    source_basis: String(fields.source_basis || ""),
                };
            });
            if (!values.length)
                throw new Error("至少填写一条已确认的测量。");
            return values;
        }
        const raw = node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement
            || node instanceof HTMLSelectElement ? node.value : "";
        if (slot.value_type === "text_list") {
            const items = splitLines(raw);
            if (!items.length)
                throw new Error("文本列表至少要有一条。");
            return items;
        }
        if (slot.value_type === "number") {
            const text = String(raw).trim();
            if (!text)
                throw new Error("请填写数字。");
            const value = Number(text);
            if (!Number.isFinite(value))
                throw new Error("请填写合法的数字。");
            return value;
        }
        if (slot.value_type === "boolean")
            return raw === "true";
        const text = String(raw).trim();
        if (!text)
            throw new Error("值不能为空。");
        return text;
    }
    async function handleSlotAction(entry, spec) {
        const action = beginAction();
        if (!action.projectId)
            return;
        clearError(elements.slotsError);
        try {
            await inputs.slotAction(entry.slot.slot_id, spec);
            if (!action.alive())
                return;
            interaction = { slotId: null, mode: null };
            await deriveAndApplyState();
            renderAll();
        }
        catch (error) {
            if (action.alive()) {
                showError(elements.slotsError, errorMessageOf(error, "这个动作没有完成。"));
            }
        }
    }
    async function handleAddSlot() {
        clearError(elements.slotsError);
        elements.slotAddStatus.textContent = "";
        const slotId = elements.slotAddId.value.trim().toLowerCase();
        const label = elements.slotAddLabel.value.trim();
        const rawType = elements.slotAddType.value;
        const rawValue = elements.slotAddValue.value;
        // 值类型选项来自 index.html 的固定 select；词表校验后再按 SlotValueType 使用。
        if (!SLOT_VALUE_TYPES.includes(rawType)) {
            showError(elements.slotsError, "值类型不在支持列表内。");
            return;
        }
        const valueType = rawType;
        let value;
        try {
            if (valueType === "text_list") {
                value = splitLines(rawValue);
                if (!value.length)
                    throw new Error("文本列表至少要有一条。");
            }
            else if (valueType === "number") {
                value = Number(String(rawValue).trim());
                if (!Number.isFinite(value))
                    throw new Error("请填写合法的数字。");
            }
            else if (valueType === "boolean") {
                const text = String(rawValue).trim().toLowerCase();
                value = text === "是" || text === "true" || text === "1";
            }
            else {
                value = String(rawValue).trim();
                if (!value)
                    throw new Error("值不能为空。");
            }
        }
        catch (error) {
            showError(elements.slotsError, errorMessageOf(error, "值不合法。"));
            return;
        }
        const candidate = {
            schema_version: FACT_SLOT_SCHEMA_VERSION,
            slot_id: slotId,
            label,
            authority: "user_custom",
            value_type: valueType,
            value,
            source: "user_input",
            status: "confirmed",
            confidence: null,
            evidence: [{ kind: "user", ref: "user_input" }],
            depends_on: [],
            critical: false,
            allow_model_proposal: elements.slotAddAllowModel.checked,
        };
        const problems = checkFactSlot(candidate);
        if (problems.length) {
            showError(elements.slotsError, problems.map((item) => item.message).join("；"));
            return;
        }
        if (!canAddSlot(candidate, "user", { existingSlots: inputs.slotEntries().map((item) => item.slot) })) {
            showError(elements.slotsError, "槽位标识已存在，或这个槽位不允许新增。");
            return;
        }
        const action = beginAction();
        const pid = action.projectId;
        if (!pid)
            return;
        try {
            await inputs.addCustomSlot(candidate);
            if (!action.alive())
                return;
            elements.slotAddId.value = "";
            elements.slotAddLabel.value = "";
            elements.slotAddValue.value = "";
            elements.slotAddAllowModel.checked = false;
            elements.slotAddStatus.textContent = "已新增 " + candidate.slot_id;
            await deriveAndApplyState();
            renderAll();
        }
        catch (error) {
            if (action.alive()) {
                showError(elements.slotsError, errorMessageOf(error, "新增槽位失败。"));
            }
        }
    }
    function updateTemplateHint(recommendation) {
        const instance = recommendation.instances
            .find((item) => item.template_id === elements.suiteTemplate.value);
        if (!instance) {
            elements.suiteTemplateHint.textContent = "";
            return;
        }
        elements.suiteTemplateHint.textContent = instance.satisfied
            ? "该模板依据已满足。"
            : "该模板暂时缺依据：" + suiteBlockingText(instance.blocking);
    }
    function renderSuite() {
        elements.suiteLocked.hidden = true;
        elements.suiteEditor.hidden = false;
        const recommendation = recommendPlan(inputs.suiteContext());
        if (elements.suiteTemplate.options.length !== SHOT_TEMPLATES.length) {
            elements.suiteTemplate.innerHTML = "";
            for (const template of SHOT_TEMPLATES) {
                const option = document.createElement("option");
                option.value = template.template_id;
                option.textContent = template.label;
                elements.suiteTemplate.append(option);
            }
        }
        updateTemplateHint(recommendation);
        const plan = inputs.suitePlan();
        const summary = plan ? suitePlanSummary(plan, inputs.suiteContext()) : null;
        elements.suiteStatus.textContent = summary
            ? "共 " + summary.total + " 张，依据已满足 " + summary.satisfiable + " 张"
                + (summary.blocked ? "；" + summary.blocked + " 张缺依据" : "")
            : "还没有套图方案。";
        elements.suiteEmpty.hidden = Boolean(summary);
        elements.shotList.innerHTML = "";
        if (!summary || !plan)
            return;
        summary.shots.forEach((item, index) => {
            // 已保存计划恒有 shot_id（validateSuitePlan 要求字符串）；null 仅存在于未落库草稿。
            const shotId = item.shot_id;
            if (typeof shotId !== "string")
                return;
            const row = createElement("li", {
                className: "shot-row",
                attrs: { "data-shot-id": shotId, "data-blocked": String(!item.satisfied) },
            });
            const head = createElement("div", { className: "shot-head" });
            head.append(createElement("span", { className: "badge", text: String(index + 1) }));
            head.append(createElement("span", { className: "name", text: item.label }));
            const roleText = item.role_label || item.role_id;
            if (!item.custom && roleText && !String(item.label).startsWith(roleText)) {
                head.append(createElement("span", { className: "meta", text: roleText }));
            }
            head.append(createElement("span", {
                className: item.required ? "badge is-critical" : "badge",
                text: item.required ? "必需" : (item.custom ? "自定义" : "可选"),
            }));
            row.append(head);
            row.append(createElement("p", {
                className: "meta",
                text: item.satisfied ? "依据已满足。" : "暂时缺依据：" + suiteBlockingText(item.blocking),
            }));
            const planned = plan.shots.find(shot => shot.shot_id === shotId);
            if (!planned)
                return;
            const readiness = shotReadiness(planned, inputs.suiteContext());
            const fixes = createElement("div", { className: "shot-fixes" });
            const slotById = new Map(inputs.slotEntries().map((entry) => [entry.slot.slot_id, entry.slot]));
            for (const slotId of readiness.missing_fact_ids) {
                const definition = coreSlotDefinition(slotId);
                const fix = createElement("button", {
                    text: "填写／确认：" + (slotById.get(slotId)?.label || definition?.label || slotId),
                    attrs: { type: "button" },
                });
                fix.addEventListener("click", () => {
                    showAll = true;
                    interaction = { slotId, mode: "edit" };
                    if (!definition && !slotById.has(slotId)) {
                        elements.slotAddId.value = slotId;
                        elements.slotAddLabel.value = slotId;
                    }
                    selectStage("understand");
                    renderSlots();
                });
                fixes.append(fix);
            }
            for (const role of readiness.missing_asset_roles) {
                const fix = createElement("button", {
                    text: "补参考图：" + (ROLE_TEXT[role] || role), attrs: { type: "button" },
                });
                fix.addEventListener("click", () => selectStage("intake"));
                fixes.append(fix);
            }
            if (fixes.children.length)
                row.append(fixes);
            const bindings = createElement("details", { className: "shot-bindings" });
            bindings.append(createElement("summary", { text: "绑定这张图使用的已确认事实" }));
            const checks = [];
            for (const entry of inputs.slotEntries().filter(entry => entry.slot.status === "confirmed")) {
                const label = createElement("label", { className: "choice" });
                const check = createElement("input", { attrs: { type: "checkbox", value: entry.slot.slot_id } });
                check.checked = planned.fact_slot_ids.includes(entry.slot.slot_id);
                label.append(check, document.createTextNode(entry.slot.label));
                bindings.append(label);
                checks.push(check);
            }
            if (!checks.length) {
                bindings.append(createElement("p", { className: "meta", text: "先确认需要使用的事实；不从未确认提案猜文案或尺寸。" }));
            }
            const applyBindings = createElement("button", { text: "保存本图事实绑定", attrs: { type: "button" } });
            applyBindings.disabled = !checks.length;
            applyBindings.addEventListener("click", () => {
                const ids = checks.filter(check => check.checked).map(check => check.value);
                void handleSuiteOp(() => setShotFactBindings(plan, shotId, ids));
            });
            bindings.append(applyBindings);
            row.append(bindings);
            const actions = createElement("div", { className: "shot-actions" });
            const up = createElement("button", { text: "上移", attrs: { type: "button" } });
            up.disabled = index === 0;
            up.addEventListener("click", () => {
                handleSuiteOp(() => moveShot(plan, shotId, -1));
            });
            const down = createElement("button", { text: "下移", attrs: { type: "button" } });
            down.disabled = index === summary.shots.length - 1;
            down.addEventListener("click", () => {
                handleSuiteOp(() => moveShot(plan, shotId, 1));
            });
            const copy = createElement("button", { text: "复制", attrs: { type: "button" } });
            copy.addEventListener("click", () => {
                handleSuiteOp(() => copyShot(plan, shotId));
            });
            const remove = createElement("button", {
                text: "删除", className: "danger", attrs: { type: "button" },
            });
            remove.addEventListener("click", () => {
                handleSuiteOp(() => removeShot(plan, shotId));
            });
            actions.append(up, down, copy, remove);
            row.append(actions);
            elements.shotList.append(row);
        });
    }
    /**
     * 套图命令的统一出口：领域纯函数只产生新计划，落库与版本推进归 inputs.applySuiteOp。
     */
    async function handleSuiteOp(run) {
        if (!deps.currentProjectId())
            return false;
        clearError(elements.suiteError);
        try {
            const ok = await inputs.applySuiteOp(run);
            if (!ok)
                return false;
            renderSuite();
            renderStyleSpec();
            renderShotSpecs();
            deps.renderGenerationSections();
            await deriveAndApplyState();
            return true;
        }
        catch (error) {
            const action = beginAction();
            if (action.alive()) {
                showError(elements.suiteError, errorMessageOf(error, "操作没有完成，请重试。"));
            }
            return false;
        }
    }
    async function handleSuiteAddCustom() {
        const label = elements.suiteCustomLabel.value.trim();
        const intent = elements.suiteCustomIntent.value.trim();
        const plan = inputs.suitePlan();
        if (!plan)
            return;
        const ok = await handleSuiteOp(() => addCustomShotToPlan(plan, { label, intent }));
        if (ok) {
            elements.suiteCustomLabel.value = "";
            elements.suiteCustomIntent.value = "";
            elements.suiteCustomStatus.textContent = "已添加。";
        }
    }
    function styleFormPayload() {
        return {
            ...emptyStyleSpec(),
            background: elements.styleBackground.value.trim(),
            lighting: elements.styleLighting.value.trim(),
            color_tone: elements.styleColorTone.value.trim(),
            composition: elements.styleComposition.value.trim(),
            avoid: splitLines(elements.styleAvoid.value),
        };
    }
    function fillStyleForm(spec) {
        const pairs = [
            [elements.styleBackground, spec.background || ""],
            [elements.styleLighting, spec.lighting || ""],
            [elements.styleColorTone, spec.color_tone || ""],
            [elements.styleComposition, spec.composition || ""],
            [elements.styleAvoid, Array.isArray(spec.avoid) ? spec.avoid.join("\n") : ""],
        ];
        for (const [node, value] of pairs) {
            if (document.activeElement !== node)
                node.value = value;
        }
    }
    function renderStyleSpec() {
        const plan = inputs.suitePlan();
        const ready = Boolean(plan);
        elements.specsLocked.hidden = ready;
        elements.specsEditor.hidden = !ready;
        if (!plan)
            return;
        const shownSpec = inputs.styleSpec();
        const shownVersion = inputs.styleVersion();
        fillStyleForm(shownSpec);
        elements.styleVersion.textContent = shownVersion > 0
            ? "版本 v" + shownVersion
            : "尚未保存";
        elements.styleRestore.disabled = shownVersion <= 1;
        const projection = specChangeProjection("style_changed", {
            shotCount: plan.shots.length,
        });
        elements.styleEffect.textContent = "保存后影响：" + projection.affects_text
            + "；失效：" + projection.invalidates_text + "；保留：" + projection.preserves_text + "。";
    }
    function renderShotSpecs() {
        const plan = inputs.suitePlan();
        const ready = Boolean(plan);
        elements.specsLocked.hidden = ready;
        elements.specsEditor.hidden = !ready;
        elements.shotSpecList.innerHTML = "";
        if (!plan)
            return;
        elements.shotSpecsEmpty.hidden = plan.shots.length > 0;
        const byId = inputs.shotSpecsById();
        const digest = suiteSpecDigest(plan, { styleSpec: inputs.styleSpec(), shotSpecsById: byId });
        digest.shots.forEach((item, index) => {
            // 已保存计划恒有 shot_id；null 仅存在于未落库草稿，跳过即可。
            const shotId = item.shot_id;
            const shot = plan.shots[index];
            if (typeof shotId !== "string" || !shot)
                return;
            const entry = inputs.shotSpecEntry(shotId);
            const spec = entry ? entry.spec : emptyShotSpecFromShot(shot);
            const card = createElement("div", {
                className: "shot-spec", attrs: { "data-shot-id": shotId },
            });
            const head = createElement("div", { className: "shot-spec-head" });
            head.append(createElement("span", {
                className: "name", text: (index + 1) + ". " + item.label,
            }));
            head.append(createElement("span", {
                className: "meta", text: entry ? "规格 v" + entry.version : "默认（未保存）",
            }));
            card.append(head);
            const purposeField = createElement("div", { className: "field" });
            const purposeId = "spec-purpose-" + shotId;
            const purposeLabel = createElement("label", { text: "目的" });
            purposeLabel.setAttribute("for", purposeId);
            const purposeInput = createElement("input", { attrs: { id: purposeId, maxlength: "200" } });
            purposeInput.value = spec.purpose;
            purposeField.append(purposeLabel, purposeInput);
            card.append(purposeField);
            const keepField = createElement("div", { className: "field" });
            const keepId = "spec-keep-" + shotId;
            const keepLabel = createElement("label", { text: "必须保持（一行一条）" });
            keepLabel.setAttribute("for", keepId);
            const keepArea = createElement("textarea", { attrs: { id: keepId, rows: "2" } });
            keepArea.value = spec.keep.join("\n");
            keepField.append(keepLabel, keepArea);
            card.append(keepField);
            const changeField = createElement("div", { className: "field" });
            const changeId = "spec-change-" + shotId;
            const changeLabel = createElement("label", { text: "允许变化（一行一条）" });
            changeLabel.setAttribute("for", changeId);
            const changeArea = createElement("textarea", { attrs: { id: changeId, rows: "2" } });
            changeArea.value = spec.change_allowed.join("\n");
            changeField.append(changeLabel, changeArea);
            card.append(changeField);
            const toolbar = createElement("div", { className: "toolbar" });
            const saveButton = createElement("button", { text: "保存", attrs: { type: "button" } });
            saveButton.addEventListener("click", () => {
                handleSaveShotSpec(shotId, {
                    purpose: purposeInput.value.trim(),
                    keep: splitLines(keepArea.value),
                    change_allowed: splitLines(changeArea.value),
                });
            });
            const restoreButton = createElement("button", {
                text: "恢复上一版本", attrs: { type: "button" },
            });
            restoreButton.disabled = !entry || entry.version <= 1;
            restoreButton.addEventListener("click", () => { handleRestoreShotSpec(shotId); });
            toolbar.append(saveButton, restoreButton);
            card.append(toolbar);
            const checklist = createElement("details", { className: "slot-detail" });
            checklist.append(createElement("summary", { text: "审核清单" }));
            const list = createElement("ul", { className: "checklist" });
            for (const section of item.checklist.sections) {
                if (section.items.length === 0)
                    continue;
                const li = createElement("li");
                li.append(createElement("strong", { text: section.label + "：" }));
                li.append(createElement("span", { className: "meta", text: section.items.join("；") }));
                list.append(li);
            }
            checklist.append(list);
            card.append(checklist);
            elements.shotSpecList.append(card);
        });
    }
    async function handleSaveStyle() {
        const plan = inputs.suitePlan();
        if (!deps.currentProjectId() || !plan)
            return;
        const action = beginAction();
        if (!action.projectId)
            return;
        clearError(elements.styleError);
        elements.styleStatus.hidden = true;
        try {
            const next = styleFormPayload();
            const before = inputs.styleSpec();
            const diffs = styleSpecDiff(before, next);
            await inputs.saveStyle(next);
            if (!action.alive())
                return;
            renderStyleSpec();
            renderShotSpecs();
            deps.renderGenerationSections();
            await deriveAndApplyState();
            if (!action.alive())
                return;
            elements.styleStatus.hidden = false;
            elements.styleStatus.textContent = "已保存 v" + inputs.styleVersion()
                + (diffs.length > 0
                    ? "（改动：" + diffs.map((item) => item.label).join("、") + "）"
                    : "（没有字段变化）");
        }
        catch (error) {
            if (action.alive()) {
                showError(elements.styleError, errorMessageOf(error, "保存没有完成，请重试。"));
            }
        }
    }
    async function handleRestoreStyle() {
        if (!deps.currentProjectId() || inputs.styleVersion() <= 1)
            return;
        const action = beginAction();
        if (!action.projectId)
            return;
        clearError(elements.styleError);
        try {
            const before = inputs.styleVersion();
            const restoredVersion = await inputs.restoreStyle();
            if (!action.alive())
                return;
            renderStyleSpec();
            renderShotSpecs();
            deps.renderGenerationSections();
            await deriveAndApplyState();
            if (!action.alive())
                return;
            elements.styleStatus.hidden = false;
            elements.styleStatus.textContent = restoredVersion > 0
                ? "已恢复上一版本的内容（v" + before + " → v" + restoredVersion + "）。"
                : "已恢复上一版本的内容。";
        }
        catch (error) {
            if (action.alive()) {
                showError(elements.styleError, errorMessageOf(error, "恢复没有完成，请重试。"));
            }
        }
    }
    async function handleSaveShotSpec(shotId, changes) {
        if (!deps.currentProjectId())
            return;
        const action = beginAction();
        if (!action.projectId)
            return;
        clearError(elements.specsError);
        try {
            await inputs.saveShotSpec(shotId, changes);
            if (!action.alive())
                return;
            renderShotSpecs();
            deps.renderGenerationSections();
            await deriveAndApplyState();
        }
        catch (error) {
            if (action.alive()) {
                showError(elements.specsError, errorMessageOf(error, "保存没有完成，请重试。"));
            }
        }
    }
    async function handleRestoreShotSpec(shotId) {
        if (!deps.currentProjectId())
            return;
        const action = beginAction();
        if (!action.projectId)
            return;
        clearError(elements.specsError);
        try {
            await inputs.restoreShotSpec(shotId);
            if (!action.alive())
                return;
            renderShotSpecs();
            deps.renderGenerationSections();
            await deriveAndApplyState();
        }
        catch (error) {
            if (action.alive()) {
                showError(elements.specsError, errorMessageOf(error, "恢复没有完成，请重试。"));
            }
        }
    }
    /* -------------------------------------------------------------- 视图入口 */
    /** 资料/理解/方案三区同轮渲染；顺序与原 renderAll 的分区调用一致。 */
    function render() {
        renderIntake();
        renderAnalyze();
        renderSlots();
        renderSuite();
        renderStyleSpec();
        renderShotSpecs();
    }
    /** 重开项目时的就地状态归零：与原 loadWorkspace 重置的四项一一对应（不含待确认标记）。 */
    function resetViewState() {
        lastAnalyze = null;
        analyzeProblems = [];
        showAll = false;
        interaction = { slotId: null, mode: null };
    }
    /** 资料表单「保存」：落库 → 派生 → 只刷新理解区与页眉（保留原 bind 的刷新面）。 */
    async function handleSaveIntake() {
        try {
            await saveIntakeNow();
            await deriveAndApplyState();
            renderAnalyze();
            deps.renderHeader();
        }
        catch (error) {
            handleInternalError(error);
        }
    }
    /** 「人工填写事实」：先落库资料，再准备核心槽位，最后停靠理解阶段。 */
    async function handleManualFacts() {
        const action = beginAction();
        try {
            await saveIntakeNow();
            if (!action.alive())
                return;
            await prepareManualFacts();
            if (action.alive())
                selectStage("understand", { focusHeading: true });
        }
        catch (error) {
            if (action.alive())
                handleInternalError(error);
        }
    }
    /** 槽位列表展开/收起（只切本视图的局部状态）。 */
    function toggleAllSlots() {
        showAll = !showAll;
        renderSlots();
    }
    /** 按推荐模板种子建计划；落库与派生由 applySuiteOp 与工作区负责。 */
    function seedSuite() {
        return handleSuiteOp(() => seedSuitePlan(inputs.suiteContext()));
    }
    /** 从下拉模板追加一张图（计划不存在时空操作，与原 bind 一致）。 */
    function addTemplateShot() {
        const plan = inputs.suitePlan();
        if (!plan)
            return Promise.resolve(false);
        return handleSuiteOp(() => addShotFromTemplate(plan, elements.suiteTemplate.value, { context: inputs.suiteContext() }));
    }
    /** 模板下拉的提示语刷新（只读推荐投影，不改计划）。 */
    function refreshTemplateHint() {
        updateTemplateHint(recommendPlan(inputs.suiteContext()));
    }
    /** 自定义图面板的展开态属于本视图。 */
    function toggleCustomPanel() {
        const opening = elements.suiteCustomPanel.hidden;
        elements.suiteCustomPanel.hidden = !opening;
        elements.suiteCustomToggle.setAttribute("aria-expanded", String(opening));
    }
    return {
        render,
        renderIntake,
        renderDraftStatus: updateDraftStatus,
        renderAnalyze,
        renderConflictEditor,
        renderSlots,
        resetViewState,
        saveIntakeNow,
        scheduleDraftSave,
        handleSaveIntake,
        handleManualFacts,
        prepareManualFacts,
        runAnalyze,
        toggleAllSlots,
        addSlot: handleAddSlot,
        seedSuite,
        addTemplateShot,
        refreshTemplateHint,
        toggleCustomPanel,
        addCustomShot: handleSuiteAddCustom,
        saveStyle: handleSaveStyle,
        restoreStyle: handleRestoreStyle,
    };
}
