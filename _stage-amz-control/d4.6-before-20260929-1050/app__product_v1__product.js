(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const home = byId("home-screen");
  const intake = byId("intake-screen");
  const notice = byId("app-notice");
  const form = byId("product-intake-form");
  const briefSection = byId("brief-workspace");
  const briefForm = byId("product-brief-form");
  const planSection = byId("plan-workspace");
  const planGenerateForm = byId("plan-generate-form");
  const planAdjustmentForm = byId("plan-adjustment-form");
  const planShots = byId("plan-shots");
  const promptDialog = byId("prompt-dialog");
  const promptForm = byId("prompt-editor-form");
  const promptText = byId("prompt-full-text");
  const imageInput = byId("reference-images");
  const sessionKey = "amzListingKit.productV1.workspaceDirectory";
  let currentDirectory = null;
  let projection = null;
  let savedReferences = [];
  let dirty = false;
  let briefDirty = false;
  let briefNeedsSave = false;
  let intakeLocked = false;
  let briefBaseline = null;
  let busy = false;
  let objectUrls = [];
  let planDraft = [];
  let planDirty = false;
  let activePromptShotId = null;
  let activePromptVersion = null;
  let activePromptBaseline = "";
  let promptReady = false;
  let promptReworkShotId = null;
  let generationOutcomeUnknown = false;
  let chosenCandidates = new Map();

  async function request(path, options = {}) {
    const response = await fetch(path, { cache: "no-store", ...options });
    const body = await response.json();
    if (!response.ok || body.ok !== true) {
      const error = body.error || {};
      const failure = new Error(error.message || "操作未完成，请重试。");
      failure.details = error;
      throw failure;
    }
    return body.data;
  }

  function setNotice(message, tone = "") {
    notice.textContent = message || "";
    notice.dataset.tone = tone;
    notice.hidden = !message;
  }

  function setBusy(value) {
    busy = value;
    byId("create-workspace").disabled = value;
    byId("open-workspace").disabled = value;
    byId("top-create-workspace").disabled = value;
    byId("top-open-workspace").disabled = value;
    byId("brand-home").disabled = value;
    byId("back-home").disabled = value;
    byId("save-intake").disabled = value || intakeLocked;
    byId("analyze-product").disabled = value || dirty || !projection?.readiness?.can_generate_product_brief;
    byId("save-brief").disabled = value || briefForm.hidden || !(briefDirty || briefNeedsSave);
    byId("generate-plan").disabled = value || !projection?.readiness?.can_generate_plan || briefDirty || briefNeedsSave;
    byId("save-plan").disabled = value || !planDirty;
    briefSection.setAttribute("aria-busy", value ? "true" : "false");
    briefForm.querySelectorAll("input, textarea, select").forEach((control) => {
      control.disabled = value;
    });
    planAdjustmentForm.querySelectorAll("input, textarea").forEach((control) => {
      control.disabled = value;
    });
    planShots.querySelectorAll("button").forEach((button) => { button.disabled = value || button.dataset.disabled === "true"; });
    promptText.disabled = value || !promptReady;
    byId("save-prompt").disabled = value || !promptReady
      || promptText.value === activePromptBaseline;
    byId("confirm-rework").disabled = value || !promptReady || !promptReworkShotId;
    byId("generation-workspace").setAttribute("aria-busy", value ? "true" : "false");
    updateGenerationControls();
    document.querySelectorAll(".recent-open").forEach((button) => { button.disabled = value; });
    renderSelectionPanel(projection?.plan || null);
  }

  function formatDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "" : date.toLocaleString("zh-CN", {
      year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    });
  }

  function renderRecent(items) {
    const list = byId("recent-list");
    list.replaceChildren();
    list.setAttribute("aria-busy", "false");
    byId("recent-count").textContent = items.length ? String(items.length) + " 个" : "";
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "empty-recent";
      const title = document.createElement("strong");
      title.textContent = "还没有最近工作空间";
      const hint = document.createElement("span");
      hint.textContent = "新建一套商品图片，或打开已经存在的工作空间。";
      empty.append(title, hint);
      list.append(empty);
      return;
    }
    for (const item of items) {
      const row = document.createElement("button");
      row.className = "recent-item recent-open";
      row.type = "button";
      row.title = item.directory;
      row.addEventListener("click", () => openWorkspace(item.directory));
      const mark = document.createElement("span");
      mark.className = "recent-mark";
      mark.setAttribute("aria-hidden", "true");
      mark.textContent = (item.name || "商").trim().slice(0, 1).toUpperCase();
      const copy = document.createElement("div");
      copy.className = "recent-copy";
      const name = document.createElement("h3");
      name.className = "recent-name";
      name.textContent = item.name;
      const detail = document.createElement("p");
      detail.className = "recent-path";
      detail.textContent = "Amazon US · " + formatDate(item.updated_at);
      const open = document.createElement("span");
      open.className = "recent-arrow";
      open.setAttribute("aria-hidden", "true");
      open.textContent = "继续 →";
      copy.append(name, detail);
      row.append(mark, copy, open);
      list.append(row);
    }
  }

  async function loadRecent() {
    byId("recent-list").setAttribute("aria-busy", "true");
    try {
      const data = await request("/api/workspaces/recent");
      renderRecent(data.workspaces || []);
    } catch (error) {
      renderRecent([]);
      setNotice(error.message, "error");
    }
  }

  function clearImagePreview() {
    objectUrls.forEach((url) => URL.revokeObjectURL(url));
    objectUrls = [];
    byId("saved-images").replaceChildren();
    byId("image-selection").textContent = "";
    byId("replace-note").hidden = true;
  }

  function showHome() {
    home.hidden = false;
    intake.hidden = true;
    form.reset();
    briefForm.reset();
    projection = null;
    savedReferences = [];
    currentDirectory = null;
    dirty = false;
    briefDirty = false;
    briefNeedsSave = false;
    intakeLocked = false;
    briefBaseline = null;
    briefSection.hidden = true;
    briefForm.hidden = true;
    planSection.hidden = true;
    planAdjustmentForm.hidden = true;
    planShots.replaceChildren();
    planDraft = [];
    planDirty = false;
    activePromptShotId = null;
    activePromptVersion = null;
    activePromptBaseline = "";
    promptReady = false;
    if (promptDialog.open) promptDialog.close();
    clearImagePreview();
    document.title = "商品套图工作台";
  }

  function renderWorkspaceStage(data) {
    const shots = data.plan?.shots || [];
    const hasGeneration = shots.some((shot) => (shot.attempts || []).length || (shot.candidates || []).length);
    const current = data.export || hasGeneration ? "review" : (data.plan ? "plan" : "intake");
    byId("workspace-stage").dataset.currentStage = current;
    document.querySelectorAll("#workspace-stage .stage").forEach((stage) => {
      const isCurrent = stage.dataset.stage === current;
      stage.classList.toggle("current", isCurrent);
      if (isCurrent) stage.setAttribute("aria-current", "step");
      else stage.removeAttribute("aria-current");
    });
  }

  function renderSavedImages(references) {
    const container = byId("saved-images");
    container.replaceChildren();
    for (const reference of references) {
      const figure = document.createElement("figure");
      figure.className = "saved-image";
      const image = document.createElement("img");
      image.alt = "商品参考图：" + reference.name;
      const query = new URLSearchParams({ directory: currentDirectory });
      image.src = "/api/workspace/references/" + reference.sha256 + "?" + query.toString();
      const caption = document.createElement("figcaption");
      caption.textContent = reference.name;
      figure.append(image, caption);
      container.append(figure);
    }
  }

  function renderFilePreview(files) {
    objectUrls.forEach((url) => URL.revokeObjectURL(url));
    objectUrls = [];
    const container = byId("saved-images");
    if (!files.length) {
      renderSavedImages(savedReferences);
      return;
    }
    container.replaceChildren();
    files.slice(0, 3).forEach((file) => {
      const figure = document.createElement("figure");
      figure.className = "saved-image";
      const image = document.createElement("img");
      const url = URL.createObjectURL(file);
      objectUrls.push(url);
      image.src = url;
      image.alt = "待保存的商品参考图：" + file.name;
      const caption = document.createElement("figcaption");
      caption.textContent = file.name;
      figure.append(image, caption);
      container.append(figure);
    });
  }

  function updateImageChoice({ revealError = false } = {}) {
    const count = imageInput.files.length;
    const invalid = count > 3 || (count === 0 && savedReferences.length === 0);
    let message = "";
    if (count > 3) message = "一次最多选择 3 张参考图。";
    else if (count === 0 && savedReferences.length === 0) message = "请先选择至少 1 张商品参考图。";
    imageInput.setCustomValidity(invalid ? message : "");
    byId("image-selection").textContent = count
      ? "已选择 " + count + " 张图片" + (savedReferences.length ? "，保存后替换现有图片" : "")
      : (savedReferences.length ? "已保存 " + savedReferences.length + " 张参考图" : "");
    byId("replace-note").hidden = !(count && savedReferences.length);
    const error = byId("image-error");
    if (revealError && invalid) {
      error.textContent = message;
      error.hidden = false;
      imageInput.setAttribute("aria-invalid", "true");
    } else if (!invalid) {
      error.textContent = "";
      error.hidden = true;
      imageInput.removeAttribute("aria-invalid");
    }
    renderFilePreview(Array.from(imageInput.files));
  }

  function renderWorkspace(data, directory) {
    if (currentDirectory !== directory) chosenCandidates = new Map();
    projection = data;
    currentDirectory = directory;
    seedChoicesFromProjection();
    generationOutcomeUnknown = false;
    savedReferences = data.intake.reference_images || [];
    byId("workspace-directory").value = directory;
    byId("workspace-revision").value = data.workspace.revision;
    byId("workspace-name").textContent = data.intake.product_name || "未命名商品";
    byId("product-name").value = data.intake.product_name || "";
    byId("product-description").value = data.intake.description || "";
    byId("selling-points").value = (data.intake.selling_points || [])
      .map((item) => typeof item === "string" ? item
        : (item && typeof item.text === "string" ? item.text : ""))
      .filter(Boolean)
      .join("\n");
    byId("user-intent").value = data.intake.user_intent || "";
    byId("workspace-status").textContent = data.workspace.status === "NEW" ? "新工作空间" : "资料已保存";
    byId("save-state").textContent = "资料保存在你选择的工作空间文件夹中。";
    byId("image-error").hidden = true;
    byId("image-error").textContent = "";
    byId("product-name-error").hidden = true;
    byId("product-name-error").textContent = "";
    byId("product-name").removeAttribute("aria-invalid");
    imageInput.removeAttribute("aria-invalid");
    imageInput.value = "";
    updateImageChoice();
    renderSavedImages(savedReferences);
    intakeLocked = Boolean(data.product_brief);
    ["product-name", "product-description", "selling-points", "user-intent", "reference-images"].forEach((id) => {
      byId(id).disabled = intakeLocked;
    });
    byId("upload-zone").hidden = intakeLocked;
    briefSection.hidden = !data.readiness.can_generate_product_brief;
    byId("analyze-product").textContent = data.product_brief ? "重新分析" : "生成商品理解";
    if (data.product_brief) {
      renderBrief(data.product_brief, { isSaved: true });
    } else {
      briefForm.hidden = true;
      briefBaseline = null;
      briefDirty = false;
      briefNeedsSave = false;
      byId("analyze-product").setAttribute("aria-expanded", "false");
      byId("brief-status").hidden = true;
      byId("brief-provenance").hidden = true;
      byId("brief-facts").replaceChildren();
    }
    setGenerationStatus("");
    renderPlan(data.plan);
    renderWorkspaceStage(data);
    home.hidden = true;
    intake.hidden = false;
    document.title = (data.intake.product_name || "未命名商品") + " · 商品套图工作台";
    dirty = false;
  }

  function setPlanStatus(message, tone = "") {
    const status = byId("plan-status");
    status.textContent = message || "";
    status.dataset.tone = tone;
    status.hidden = !message;
  }

  function makePlanField({ label, value, field, index, multiline = false }) {
    const wrapper = document.createElement("div");
    wrapper.className = "plan-edit-field";
    const controlId = `shot-${index}-${field}`;
    const labelNode = document.createElement("label");
    labelNode.htmlFor = controlId;
    labelNode.textContent = label;
    const control = document.createElement(multiline ? "textarea" : "input");
    control.id = controlId;
    control.name = `shots[${index}][${field}]`;
    control.dataset.shotField = field;
    control.dataset.shotId = planDraft[index].id;
    control.value = Array.isArray(value) ? value.join("\n") : (value || "");
    if (multiline) {
      control.rows = field === "preserve" || field === "change" ? 3 : 2;
      control.maxLength = 2000;
    } else {
      control.type = "text";
      control.maxLength = field === "title" ? 120 : 1000;
      control.required = true;
    }
    wrapper.append(labelNode, control);
    return wrapper;
  }

  function renderPlanShots() {
    planShots.replaceChildren();
    const facts = new Map((projection?.product_brief?.facts || []).map((fact) => [fact.key, fact]));
    planDraft.forEach((shot, index) => {
      const card = document.createElement("article");
      card.className = "plan-shot";
      card.dataset.shotId = shot.id;

      const head = document.createElement("div");
      head.className = "plan-shot-head";
      const number = document.createElement("span");
      number.className = "shot-number";
      number.textContent = String(index + 1).padStart(2, "0");
      const titleGroup = document.createElement("div");
      titleGroup.className = "plan-shot-title-group";
      const title = document.createElement("h3");
      title.textContent = shot.title;
      const tags = document.createElement("div");
      tags.className = "plan-shot-tags";
      const typeTag = document.createElement("span");
      typeTag.className = "shot-type-tag";
      typeTag.textContent = shot.archetype_id === "hero" ? "主图" : shot.archetype_id === "custom" ? "自定义图" : shot.archetype_id;
      const requiredTag = document.createElement("span");
      requiredTag.className = shot.required ? "shot-required" : "shot-optional";
      requiredTag.textContent = shot.required ? "必需" : "可选";
      tags.append(typeTag, requiredTag);
      titleGroup.append(title, tags);

      const actions = document.createElement("div");
      actions.className = "plan-shot-actions";
      const promptButton = document.createElement("button");
      promptButton.type = "button";
      promptButton.className = "button button-secondary button-compact";
      promptButton.dataset.action = "prompt";
      promptButton.dataset.shotId = shot.id;
      promptButton.textContent = shot.latest_prompt
        ? `提示词 v${shot.latest_prompt.version}` : "生成提示词";
      promptButton.setAttribute("aria-label", `${shot.latest_prompt ? "查看并编辑" : "生成并查看"}“${shot.title}”的完整提示词`);
      const moveUp = document.createElement("button");
      moveUp.type = "button";
      moveUp.className = "icon-button plan-order-button";
      moveUp.dataset.action = "move-up";
      moveUp.dataset.shotId = shot.id;
      moveUp.dataset.disabled = index === 0 ? "true" : "false";
      moveUp.disabled = index === 0 || busy;
      moveUp.textContent = "↑";
      moveUp.setAttribute("aria-label", `将“${shot.title}”上移`);
      const moveDown = document.createElement("button");
      moveDown.type = "button";
      moveDown.className = "icon-button plan-order-button";
      moveDown.dataset.action = "move-down";
      moveDown.dataset.shotId = shot.id;
      moveDown.dataset.disabled = index === planDraft.length - 1 ? "true" : "false";
      moveDown.disabled = index === planDraft.length - 1 || busy;
      moveDown.textContent = "↓";
      moveDown.setAttribute("aria-label", `将“${shot.title}”下移`);
      actions.append(promptButton, moveUp, moveDown);
      if (!shot.required) {
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "text-button text-button-danger";
        remove.dataset.action = "remove";
        remove.dataset.shotId = shot.id;
        remove.textContent = "移除";
        remove.setAttribute("aria-label", `从方案移除“${shot.title}”`);
        actions.append(remove);
      }
      head.append(number, titleGroup, actions);

      const purpose = document.createElement("p");
      purpose.className = "shot-purpose";
      purpose.textContent = shot.purpose;
      const reason = document.createElement("p");
      reason.className = "shot-reason";
      reason.textContent = shot.reason;

      const evidence = document.createElement("div");
      evidence.className = "shot-evidence";
      if (shot.supporting_fact_keys?.length) {
        const evidenceLabel = document.createElement("span");
        evidenceLabel.className = "shot-detail-label";
        evidenceLabel.textContent = "依据";
        evidence.append(evidenceLabel);
        shot.supporting_fact_keys.forEach((key) => {
          const fact = facts.get(key);
          const chip = document.createElement("span");
          chip.className = "fact-chip";
          chip.textContent = fact ? `${fact.key} · ${fact.value}` : key;
          evidence.append(chip);
        });
      } else {
        const neutral = document.createElement("span");
        neutral.className = "shot-no-evidence";
        neutral.textContent = "不含商品宣传事实";
        evidence.append(neutral);
      }

      const boundaries = document.createElement("p");
      boundaries.className = "shot-boundaries";
      boundaries.textContent = `保持：${(shot.preserve || []).join("、") || "商品身份"}　·　可调整：${(shot.change || []).join("、") || "背景与构图"}`;
      const dependencies = (shot.dependencies || []).map((dependency) => {
        const found = planDraft.find((item) => item.id === dependency);
        return found ? found.title : dependency;
      });
      if (dependencies.length) {
        const dependencyNode = document.createElement("p");
        dependencyNode.className = "shot-dependencies";
        dependencyNode.textContent = `前置：${dependencies.join("、")}`;
        boundaries.append(document.createTextNode(" "));
        card.append(head, purpose, reason, evidence, boundaries, dependencyNode);
      } else {
        card.append(head, purpose, reason, evidence, boundaries);
      }

      const edit = document.createElement("details");
      edit.className = "shot-edit-details";
      const summary = document.createElement("summary");
      summary.textContent = "调整这张图";
      const fields = document.createElement("div");
      fields.className = "shot-edit-grid";
      fields.append(
        makePlanField({ label: "图片名称", value: shot.title, field: "title", index }),
        makePlanField({ label: "图片目的", value: shot.purpose, field: "purpose", index, multiline: true }),
        makePlanField({ label: "选择理由", value: shot.reason, field: "reason", index, multiline: true }),
        makePlanField({ label: "必须保持", value: shot.preserve, field: "preserve", index, multiline: true }),
        makePlanField({ label: "允许变化", value: shot.change, field: "change", index, multiline: true }),
      );
      edit.append(summary, fields);
      card.append(edit);
      planShots.append(card);
    });
    byId("save-plan").disabled = busy || !planDirty;
  }

  function renderPlan(plan) {
    planSection.hidden = !projection?.product_brief;
    setPlanStatus("");
    byId("generate-plan").textContent = plan ? "重新生成方案" : "生成套图方案";
    if (!projection?.product_brief) {
      planAdjustmentForm.hidden = true;
      byId("plan-style").hidden = true;
      renderGeneration(null);
      return;
    }
    byId("plan-summary").textContent = plan
      ? `${plan.shot_specs.length} 张图片 · 套图方案 v${plan.version} · 商品理解 v${plan.source_brief.version}`
      : "商品理解已保存。系统会根据商品资料、卖点和 Amazon US 规则安排所需图片。";
    planDirty = false;
    planDraft = plan ? JSON.parse(JSON.stringify(plan.shot_specs)) : [];
    byId("plan-save-state").textContent = "默认方案可以直接使用；只有需要时再调整。";
    if (!plan) {
      byId("plan-style").hidden = true;
      planAdjustmentForm.hidden = true;
      planShots.replaceChildren();
      byId("save-plan").disabled = true;
      renderGeneration(null);
      return;
    }

    byId("plan-style").hidden = false;
    byId("plan-version").textContent = `方案 v${plan.version}`;
    const style = plan.style_lock || {};
    const styleContent = byId("plan-style-content");
    styleContent.replaceChildren();
    const direction = document.createElement("p");
    direction.className = "plan-direction";
    direction.textContent = style.direction || "";
    styleContent.append(direction);
    const styleDetails = document.createElement("div");
    styleDetails.className = "plan-style-details";
    [
      ["配色", (style.palette || []).join("、")],
      ["光线", style.lighting || ""],
      ["背景", style.background || ""],
      ["整组一致", (style.continuity_notes || []).join("；")],
    ].filter(([, value]) => value).forEach(([label, value]) => {
      const item = document.createElement("p");
      const term = document.createElement("span");
      term.textContent = label;
      const detail = document.createElement("strong");
      detail.textContent = value;
      item.append(term, detail);
      styleDetails.append(item);
    });
    styleContent.append(styleDetails);
    planAdjustmentForm.hidden = false;
    renderPlanShots();
    renderGeneration(plan);
  }

  const openGenerationStates = new Set(["CREATED", "SUBMITTED", "RUNNING", "UNKNOWN", "RECONCILING"]);
  const reconcilableGenerationStates = new Set(["SUBMITTED", "RUNNING", "UNKNOWN"]);

  function generationAttempts() {
    return (projection?.plan?.shot_specs || []).flatMap((shot) =>
      (Array.isArray(shot.generation_attempts) ? shot.generation_attempts : [])
        .map((attempt) => ({ shot, attempt })));
  }

  function pendingGenerationActions() {
    const seen = new Set();
    return generationAttempts().filter(({ attempt }) => {
      const actionId = attempt.action_id;
      if (!reconcilableGenerationStates.has(attempt.status) || !actionId || seen.has(actionId)) return false;
      seen.add(actionId);
      return true;
    });
  }

  function hasOpenGenerationAttempt() {
    return generationAttempts().some(({ attempt }) => openGenerationStates.has(attempt.status));
  }

  function hasUnsavedGenerationInputs() {
    return dirty || briefDirty || briefNeedsSave || planDirty
      || (promptReady && promptText.value !== activePromptBaseline);
  }

  function updateGenerationControls() {
    const start = byId("start-generation");
    if (!start) return;
    const plan = projection?.plan;
    const hasPlan = Boolean(plan?.shot_specs?.length);
    const openAttempt = hasOpenGenerationAttempt();
    const actionIds = pendingGenerationActions();
    const hasPreviousAttempt = generationAttempts().length > 0;
    const hasUnsaved = hasUnsavedGenerationInputs();

    start.disabled = busy || !hasPlan || hasUnsaved || openAttempt || generationOutcomeUnknown;
    start.textContent = openAttempt
      ? "等待本轮结果"
      : (hasPreviousAttempt ? "再次生成整套" : "采用方案并一键生成");
    byId("reconcile-generation").hidden = actionIds.length === 0;
    byId("reconcile-generation").disabled = busy;
    byId("refresh-generation").hidden = !(generationOutcomeUnknown || (openAttempt && actionIds.length === 0));
    byId("refresh-generation").disabled = busy;

    const hint = byId("generation-hint");
    let message = "";
    if (generationOutcomeUnknown) {
      message = "上次提交结果尚未确认；先重新载入状态，不要重复提交。";
    } else if (openAttempt && actionIds.length) {
      message = "本方案有生成任务尚未确认；先核对当前状态，不能重复提交。";
    } else if (openAttempt) {
      message = "本方案仍有生成任务在处理中；先刷新状态，不能重复提交。";
    } else if (dirty) {
      message = "先保存商品资料后再生成。";
    } else if (briefDirty || briefNeedsSave) {
      message = "先保存商品理解后再生成。";
    } else if (planDirty) {
      message = "先保存套图方案调整后再生成。";
    } else if (promptReady && promptText.value !== activePromptBaseline) {
      message = "先保存提示词修改后再生成。";
    }
    hint.textContent = message;
    hint.hidden = !message;
  }

  function generationStateLabel(status) {
    return ({
      CREATED: "准备提交",
      SUBMITTED: "已提交",
      RUNNING: "生成中",
      SUCCEEDED: "已完成",
      FAILED: "生成失败",
      UNKNOWN: "结果待核对",
      RECONCILING: "正在核对",
      REJECTED: "未提交",
    })[status] || "尚未生成";
  }

  function candidateImageUrl(candidate) {
    const query = new URLSearchParams({ directory: currentDirectory || "" });
    return `/api/candidates/${encodeURIComponent(candidate.candidate_id)}?${query.toString()}`;
  }

  function renderGeneration(plan) {
    const section = byId("generation-workspace");
    const list = byId("generation-shots");
    const hasPlan = Boolean(plan?.shot_specs?.length);
    section.hidden = !hasPlan;
    list.replaceChildren();
    if (!hasPlan) {
      updateGenerationControls();
      renderSelectionPanel(null);
      return;
    }

    const shots = plan.shot_specs;
    const totalCandidates = shots.reduce((count, shot) => count + (shot.candidates || []).length, 0);
    const completedShots = shots.filter((shot) => (shot.candidates || []).length > 0).length;
    byId("generation-title").textContent = `生成结果 · ${completedShots}/${shots.length} 张有候选`;
    if (totalCandidates) byId("generation-title").textContent += ` · ${totalCandidates} 个候选`;

    shots.forEach((shot, index) => {
      const attempts = (Array.isArray(shot.generation_attempts) ? shot.generation_attempts : [])
        .slice()
        .sort((left, right) => String(left.created_at || "").localeCompare(String(right.created_at || "")));
      const latest = attempts.at(-1) || null;
      const candidates = Array.isArray(shot.candidates) ? shot.candidates : [];
      const card = document.createElement("article");
      card.className = "generation-shot";

      const header = document.createElement("header");
      header.className = "generation-shot-header";
      const title = document.createElement("h4");
      title.textContent = `${String(index + 1).padStart(2, "0")}  ${shot.title || shot.id || "套图图片"}`;
      const state = document.createElement("span");
      state.className = "generation-state";
      state.dataset.state = latest?.status || "EMPTY";
      state.textContent = generationStateLabel(latest?.status);
      header.append(title, state);
      card.append(header);

      if (attempts.length) {
        const history = document.createElement("ol");
        history.className = "generation-attempts";
        attempts.forEach((attempt) => {
          const row = document.createElement("li");
          const label = document.createElement("span");
          label.className = "generation-attempt-label";
          label.textContent = generationStateLabel(attempt.status);
          const time = document.createElement("time");
          const timestamp = attempt.updated_at || attempt.created_at;
          if (timestamp) {
            time.dateTime = timestamp;
            time.textContent = formatDate(timestamp);
          }
          row.append(label);
          if (time.textContent) row.append(time);
          if (attempt.error) {
            const error = document.createElement("p");
            error.className = "generation-error";
            error.textContent = typeof attempt.error === "string"
              ? attempt.error
              : (attempt.error.message || "生成未完成，请核对状态。");
            row.append(error);
          }
          history.append(row);
        });
        card.append(history);
      } else {
        const empty = document.createElement("p");
        empty.className = "generation-empty";
        empty.textContent = "尚未生成";
        card.append(empty);
      }

      if (candidates.length) {
        const gallery = document.createElement("div");
        gallery.className = "generation-candidates";
        candidates.forEach((candidate, candidateIndex) => {
          const figure = document.createElement("figure");
          figure.className = "generation-candidate";
          const image = document.createElement("img");
          const isLatest = latest && candidate.attempt_action_id === latest.action_id;
          const candidateLabel = isLatest ? "本轮候选" : "历史候选";
          image.src = candidateImageUrl(candidate);
          image.alt = `${shot.title || shot.id || "套图图片"}，${candidateLabel} ${candidateIndex + 1}`;
          image.loading = "lazy";
          image.decoding = "async";
          if (Number.isInteger(candidate.width) && candidate.width > 0) image.width = candidate.width;
          if (Number.isInteger(candidate.height) && candidate.height > 0) image.height = candidate.height;
          const unavailable = document.createElement("span");
          unavailable.className = "candidate-preview-error";
          unavailable.hidden = true;
          unavailable.textContent = "预览暂不可用";
          image.addEventListener("error", () => {
            image.hidden = true;
            unavailable.hidden = false;
          }, { once: true });
          const caption = document.createElement("figcaption");
          const name = document.createElement("strong");
          name.textContent = candidateLabel;
          const meta = document.createElement("span");
          const dimensions = Number.isInteger(candidate.width) && Number.isInteger(candidate.height)
            ? `${candidate.width} × ${candidate.height}`
            : "";
          const created = candidate.created_at ? formatDate(candidate.created_at) : "";
          meta.textContent = [dimensions, created].filter(Boolean).join(" · ");
          caption.append(name);
          if (meta.textContent) caption.append(meta);
          const chosen = chosenCandidates.get(shot.id) === candidate.candidate_id;
          figure.dataset.chosen = chosen ? "true" : "false";
          const choose = document.createElement("button");
          choose.type = "button";
          choose.className = "button button-secondary candidate-choose";
          choose.dataset.shotId = shot.id;
          choose.dataset.candidateId = candidate.candidate_id;
          choose.textContent = chosen ? "已选用" : "选用这张";
          choose.setAttribute("aria-pressed", chosen ? "true" : "false");
          figure.append(image, unavailable, caption, choose);
          gallery.append(figure);
        });
        card.append(gallery);
      }

      const runningAttempt = attempts.some((attempt) => openGenerationStates.has(attempt.status));
      if (candidates.length && !runningAttempt) {
        const rework = document.createElement("button");
        rework.type = "button";
        rework.className = "button button-secondary generation-rework";
        rework.dataset.reworkShotId = shot.id;
        rework.textContent = "改提示词并返工";
        card.append(rework);
      }
      if (!candidates.length && !runningAttempt) {
        // A shot can end with no candidate at all (upstream rejection, rate
        // limit, timeout). Retrying it must not resubmit the whole set.
        const retry = document.createElement("button");
        retry.type = "button";
        retry.className = "button button-secondary generation-retry";
        retry.dataset.retryShotId = shot.id;
        retry.textContent = "重新生成这张";
        card.append(retry);
      }

      list.append(card);
    });
    updateGenerationControls();
    renderSelectionPanel(plan);
  }

  function savedSelectionDigest(shotId) {
    const choices = (projection?.selection?.choices) || [];
    const match = choices.find((item) => item?.shot?.id === shotId);
    return match?.candidate_sha256 || null;
  }

  function seedChoicesFromProjection() {
    const choices = (projection?.selection?.choices) || [];
    choices.forEach((item) => {
      if (item?.shot?.id && item?.candidate_sha256 && !chosenCandidates.has(item.shot.id)) {
        chosenCandidates.set(item.shot.id, item.candidate_sha256);
      }
    });
  }

  function setSelectionStatus(message, tone = "") {
    const status = byId("selection-status");
    status.textContent = message || "";
    status.dataset.tone = tone;
    status.hidden = !message;
  }

  function renderExportSummary() {
    const container = byId("export-summary");
    const record = projection?.export || null;
    byId("reveal-export").hidden = !record;
    container.replaceChildren();
    container.hidden = !record;
    if (!record) return;
    const heading = document.createElement("p");
    heading.className = "export-path";
    heading.textContent = `导出目录：${record.relative_path}`;
    container.append(heading);
    const files = document.createElement("ul");
    files.className = "export-files";
    (record.files || []).forEach((file) => {
      const item = document.createElement("li");
      item.textContent = `${file.relative_path} · sha256 ${String(file.file_sha256).slice(0, 12)}…`;
      files.append(item);
    });
    if (files.childElementCount) container.append(files);
    const checks = document.createElement("ul");
    checks.className = "export-checks";
    (record.checks || []).forEach((check) => {
      const item = document.createElement("li");
      item.dataset.passed = check.passed ? "true" : "false";
      item.textContent = `${check.rule_id}：${check.passed ? "通过" : "未通过"} · ${check.detail}`;
      checks.append(item);
    });
    if (checks.childElementCount) container.append(checks);
    const manifest = document.createElement("p");
    manifest.className = "export-manifest";
    manifest.textContent = `追溯清单：${record.manifest_relative_path}`;
    container.append(manifest);
  }

  function renderSelectionPanel(plan) {
    const panel = byId("selection-panel");
    const shots = plan?.shot_specs || [];
    panel.hidden = !shots.length;
    if (!shots.length) return;
    const chosen = shots.filter((shot) => chosenCandidates.get(shot.id));
    const complete = chosen.length === shots.length;
    byId("selection-progress").textContent = `${chosen.length}/${shots.length} 张已选`;
    const savedMatches = complete && shots.every(
      (shot) => savedSelectionDigest(shot.id) === chosenCandidates.get(shot.id));
    byId("save-selection").disabled = busy || !complete || savedMatches;
    byId("export-selection").disabled = busy || !projection?.selection;
    byId("selection-hint").textContent = complete
      ? (savedMatches ? "选择已保存；导出会写入图片组和追溯清单。" : "已为每张图片选定候选，保存后即可导出。")
      : "为每张图片选一张候选；保存后导出图片组与追溯清单。";
    renderExportSummary();
  }

  function setGenerationStatus(message, tone = "") {
    const status = byId("generation-status");
    status.textContent = message || "";
    status.dataset.tone = tone;
    status.hidden = !message;
  }

  function makeIdempotencyKey() {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    if (window.crypto?.getRandomValues) {
      const bytes = new Uint8Array(16);
      window.crypto.getRandomValues(bytes);
      return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
    }
    return `gen_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}`;
  }

  function projectionHasAttemptKey(data, key) {
    return (data?.plan?.shot_specs || []).some((shot) =>
      (shot.generation_attempts || []).some((attempt) => attempt.idempotency_key === key));
  }

  async function loadCurrentProjection() {
    const query = new URLSearchParams({ directory: currentDirectory });
    return request("/api/workspace?" + query.toString());
  }

  async function startGeneration() {
    if (busy || !currentDirectory || !projection?.plan?.shot_specs?.length) return;
    if (hasUnsavedGenerationInputs()) {
      updateGenerationControls();
      return;
    }
    if (hasOpenGenerationAttempt()) {
      updateGenerationControls();
      return;
    }
    if (generationOutcomeUnknown) {
      setGenerationStatus("上次提交结果尚未确认；请先重新载入状态。", "error");
      return;
    }
    if (generationAttempts().length && !window.confirm(
      "当前方案已有生成记录。重新生成会为整套图片创建新任务，已有候选会保留。确定继续？")) return;

    const directory = currentDirectory;
    const idempotencyKey = makeIdempotencyKey();
    const expectedEtag = projection.workspace.revision;
    generationOutcomeUnknown = false;
    setGenerationStatus("正在提交整套生成任务…");
    setBusy(true);
    try {
      const data = await request("/api/generation/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          directory,
          expected_etag: expectedEtag,
          idempotency_key: idempotencyKey,
        }),
      });
      generationOutcomeUnknown = false;
      renderWorkspace(data, directory);
      setGenerationStatus("生成任务已记录；各张图的进度和候选会逐项显示。", "success");
      const skippedShots = Array.isArray(data?.skipped_shots) ? data.skipped_shots : [];
      if (skippedShots.length) {
        const firstSkip = skippedShots[0] || {};
        setGenerationStatus(
          `已提交其余图片；${skippedShots.length} 张暂未备好提示词（${firstSkip.message || firstSkip.code || "未知原因"}）。可点该张的“只重跑这张”单独重试。`,
          "error",
        );
      }
    } catch (error) {
      generationOutcomeUnknown = true;
      setGenerationStatus("提交响应未确认，正在重新载入工作区状态…");
      try {
        const data = await loadCurrentProjection();
        const attemptFound = projectionHasAttemptKey(data, idempotencyKey);
        generationOutcomeUnknown = false;
        renderWorkspace(data, directory);
        setGenerationStatus(
          attemptFound
            ? "任务已记录；当前状态已更新。"
            : `工作区状态已更新，但未显示本次任务。${error.message}`,
          attemptFound ? "success" : "error",
        );
      } catch (refreshError) {
        generationOutcomeUnknown = true;
        updateGenerationControls();
        setGenerationStatus(
          `提交结果未确认，且工作区状态无法读取；再次提交已锁定。请先重新载入状态。${refreshError.message}`,
          "error",
        );
      }
    } finally {
      setBusy(false);
    }
  }

  async function reconcileGeneration() {
    if (busy || !currentDirectory) return;
    const actionIds = pendingGenerationActions().map(({ attempt }) => attempt.action_id);
    if (!actionIds.length) return;

    const directory = currentDirectory;
    setGenerationStatus("正在核对当前生成状态…");
    setBusy(true);
    try {
      const data = await request("/api/generation/reconcile", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ directory, action_ids: actionIds }),
      });
      renderWorkspace(data, directory);
      setGenerationStatus("当前生成状态已更新。", "success");
    } catch (error) {
      setGenerationStatus(`状态核对未完成：${error.message}`, "error");
    } finally {
      setBusy(false);
    }
  }

  async function refreshGenerationState() {
    if (busy || !currentDirectory) return;
    const directory = currentDirectory;
    setGenerationStatus("正在重新载入工作区状态…");
    setBusy(true);
    try {
      const data = await loadCurrentProjection();
      generationOutcomeUnknown = false;
      renderWorkspace(data, directory);
      setGenerationStatus("工作区状态已更新。", "success");
    } catch (error) {
      generationOutcomeUnknown = true;
      updateGenerationControls();
      setGenerationStatus(`状态仍未确认：${error.message}`, "error");
    } finally {
      setBusy(false);
    }
  }

  function markPlanDirty() {
    if (!projection?.plan || busy) return;
    planDirty = true;
    byId("plan-save-state").textContent = "方案有未保存的调整。";
    byId("save-plan").disabled = false;
    updateGenerationControls();
  }

  function setPromptStatus(message, tone = "") {
    const status = byId("prompt-status");
    status.textContent = message || "";
    status.dataset.tone = tone;
    status.hidden = !message;
  }

  function setPromptReworkMode(shotId) {
    promptReworkShotId = shotId || null;
    byId("rework-fields").hidden = !promptReworkShotId;
    byId("confirm-rework").hidden = !promptReworkShotId;
    byId("confirm-rework").disabled = busy || !promptReady || !promptReworkShotId;
    if (!promptReworkShotId) byId("rework-reason").value = "";
  }

  function renderPromptProvenance(prompt) {
    const container = byId("prompt-blocks");
    container.replaceChildren();
    const labels = {
      product_fidelity: "商品保真",
      style_lock: "整组视觉方向",
      shot_task: "本图任务",
      platform: "平台规则",
      negative: "负面约束",
    };
    (prompt.blocks || []).forEach((block) => {
      const row = document.createElement("div");
      row.className = "prompt-block-row";
      const title = document.createElement("strong");
      title.textContent = labels[block.kind] || block.kind;
      const sources = document.createElement("span");
      sources.textContent = (block.source_refs || []).join(" · ");
      row.append(title, sources);
      container.append(row);
    });
  }

  function loadPromptEditor(shot, prompt) {
    activePromptShotId = shot.id;
    activePromptVersion = prompt.version;
    activePromptBaseline = prompt.full_text;
    promptReady = true;
    byId("prompt-shot-id").value = shot.id;
    byId("prompt-version").value = String(prompt.version);
    byId("prompt-dialog-title").textContent = shot.title;
    byId("prompt-dialog-meta").textContent = `完整提示词 · v${prompt.version}${prompt.edit_mode === "manual" ? " · 已编辑" : ""}`;
    promptText.value = prompt.full_text;
    promptText.disabled = busy;
    renderPromptProvenance(prompt);
    byId("save-prompt").disabled = busy;
    byId("confirm-rework").disabled = busy || !promptReworkShotId;
  }

  async function generatePlan(event) {
    event.preventDefault();
    if (busy || !currentDirectory || !projection?.readiness?.can_generate_plan) return;
    if (dirty || briefDirty || briefNeedsSave) {
      setPlanStatus("先保存当前商品资料和商品理解，再生成方案。", "error");
      return;
    }
    if (planDirty && !window.confirm("方案有未保存的调整；重新生成后会放弃这些调整。继续吗？")) return;
    if (projection.plan && !window.confirm("重新生成会建立新的套图方案版本，并替换当前方案。继续吗？")) return;

    const expectedRevision = projection.workspace.revision;
    setPlanStatus("正在根据当前商品理解生成套图方案…");
    setBusy(true);
    try {
      const data = await request("/api/plan/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ directory: currentDirectory, expected_etag: expectedRevision }),
      });
      if (projection.workspace.revision !== expectedRevision) {
        throw new Error("工作空间在生成期间发生变化；方案未更新，请重新载入后再试。");
      }
      renderWorkspace(data, currentDirectory);
      setPlanStatus(`套图方案已生成：${data.plan.shot_specs.length} 张图片，可按需调整。`, "success");
    } catch (error) {
      setPlanStatus(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function savePlan(event) {
    event.preventDefault();
    if (busy || !planDirty || !projection?.plan || !currentDirectory) return;
    if (!planAdjustmentForm.reportValidity()) return;
    const payload = {
      directory: currentDirectory,
      expected_etag: projection.workspace.revision,
      plan: {
        shots: planDraft.map((shot) => ({
          id: shot.id,
          title: shot.title,
          purpose: shot.purpose,
          reason: shot.reason,
          preserve: shot.preserve || [],
          change: shot.change || [],
          dependencies: shot.dependencies || [],
        })),
      },
    };
    setPlanStatus("正在保存方案版本…");
    setBusy(true);
    try {
      const data = await request("/api/plan", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      renderWorkspace(data, currentDirectory);
      setPlanStatus(`方案调整已保存为 v${data.plan.version}。`, "success");
    } catch (error) {
      setPlanStatus(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  function handlePlanAction(event) {
    const button = event.target.closest("button[data-action]");
    if (!button || busy) return;
    const shotId = button.dataset.shotId;
    if (button.dataset.action === "prompt") {
      openPrompt(shotId);
      return;
    }
    const index = planDraft.findIndex((shot) => shot.id === shotId);
    if (index < 0) return;
    if (button.dataset.action === "move-up" || button.dataset.action === "move-down") {
      const nextIndex = button.dataset.action === "move-up" ? index - 1 : index + 1;
      if (nextIndex < 0 || nextIndex >= planDraft.length) return;
      [planDraft[index], planDraft[nextIndex]] = [planDraft[nextIndex], planDraft[index]];
      renderPlanShots();
      markPlanDirty();
      return;
    }
    if (button.dataset.action === "remove") {
      const dependent = planDraft.find((shot) => shot.id !== shotId && (shot.dependencies || []).includes(shotId));
      if (dependent) {
        setPlanStatus(`“${dependent.title}”依赖这张图；请先调整依赖关系。`, "error");
        return;
      }
      const removed = planDraft[index];
      planDraft.splice(index, 1);
      renderPlanShots();
      markPlanDirty();
      setPlanStatus(`已从本次调整中移除“${removed.title}”；保存方案后生效。`);
    }
  }

  function handlePlanFieldEdit(event) {
    const control = event.target.closest("[data-shot-field]");
    if (!control || busy) return;
    const shot = planDraft.find((item) => item.id === control.dataset.shotId);
    if (!shot) return;
    const field = control.dataset.shotField;
    shot[field] = field === "preserve" || field === "change"
      ? control.value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
      : control.value;
    markPlanDirty();
  }

  async function openPrompt(shotId, { rework = false } = {}) {
    if (busy || !projection?.plan || !currentDirectory) return;
    if (dirty || briefDirty || briefNeedsSave) {
      setPlanStatus("先保存商品资料和商品理解，再查看提示词。", "error");
      return;
    }
    if (planDirty) {
      if (!window.confirm("方案调整尚未保存；打开提示词会放弃调整。要继续吗？")) return;
      renderPlan(projection.plan);
    }
    const shot = projection.plan.shot_specs.find((item) => item.id === shotId);
    if (!shot) return;
    setPromptReworkMode(rework ? shot.id : null);
    activePromptShotId = shot.id;
    activePromptVersion = null;
    activePromptBaseline = "";
    promptReady = false;
    promptText.value = "";
    promptText.disabled = true;
    byId("prompt-dialog-title").textContent = shot.title;
    byId("prompt-dialog-meta").textContent = "正在准备完整提示词…";
    byId("prompt-blocks").replaceChildren();
    setPromptStatus(shot.latest_prompt ? "正在读取已保存的提示词…" : "正在为这张图编译提示词…");
    byId("save-prompt").disabled = true;
    if (!promptDialog.open) promptDialog.showModal();

    const expectedRevision = projection.workspace.revision;
    const needsCompile = !shot.latest_prompt;
    if (needsCompile) setBusy(true);
    try {
      let data;
      if (shot.latest_prompt) {
        data = projection;
      } else {
        data = await request("/api/prompt/compile", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            directory: currentDirectory,
            expected_etag: expectedRevision,
            shot_id: shot.id,
          }),
        });
        if (projection.workspace.revision !== expectedRevision) {
          throw new Error("工作空间已变化；请重新载入后再生成提示词。");
        }
        renderWorkspace(data, currentDirectory);
      }
      const currentShot = data.plan?.shot_specs.find((item) => item.id === shot.id);
      if (!currentShot?.latest_prompt) throw new Error("服务未返回这张图的提示词，请重新载入后再试。");
      loadPromptEditor(currentShot, currentShot.latest_prompt);
      setPromptStatus("提示词已就绪。可以直接使用，也可以修改后保存为新版本。", "success");
    } catch (error) {
      setPromptStatus(error.message, "error");
      promptText.disabled = true;
    } finally {
      if (needsCompile) setBusy(false);
    }
  }

  async function savePrompt(event) {
    event.preventDefault();
    if (busy || !promptReady || !activePromptShotId || !activePromptVersion || !projection || !currentDirectory) return;
    if (!promptForm.reportValidity()) return;
    const text = promptText.value;
    if (text === activePromptBaseline) return;
    setPromptStatus("正在保存新提示词版本…");
    setBusy(true);
    try {
      const data = await request("/api/prompt", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          directory: currentDirectory,
          expected_etag: projection.workspace.revision,
          shot_id: activePromptShotId,
          expected_prompt_version: activePromptVersion,
          full_text: text,
        }),
      });
      renderWorkspace(data, currentDirectory);
      const shot = data.plan?.shot_specs.find((item) => item.id === activePromptShotId);
      if (!shot?.latest_prompt) throw new Error("保存响应没有包含新提示词版本；请重新打开工作空间核对。");
      loadPromptEditor(shot, shot.latest_prompt);
      setPromptStatus(`提示词已保存为 v${shot.latest_prompt.version}。`, "success");
    } catch (error) {
      setPromptStatus(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function confirmRework() {
    if (busy || !promptReady || !promptReworkShotId || !projection || !currentDirectory) return;
    if (!promptForm.reportValidity()) return;
    const shotId = promptReworkShotId;
    const reason = byId("rework-reason").value.trim().slice(0, 500);
    setBusy(true);
    setPromptStatus("正在保存返工要求…");
    try {
      let revision = projection.workspace.revision;
      if (promptText.value !== activePromptBaseline) {
        const saved = await request("/api/prompt", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            directory: currentDirectory,
            expected_etag: revision,
            shot_id: shotId,
            expected_prompt_version: activePromptVersion,
            full_text: promptText.value,
            ...(reason ? { reason } : {}),
          }),
        });
        renderWorkspace(saved, currentDirectory);
        revision = saved.workspace.revision;
      } else if (reason) {
        setPromptStatus("提示词没有修改；返工说明只在提示词有改动时写入版本记录。", "");
      }
      setPromptStatus("正在提交返工：只重跑这张图…");
      const data = await request("/api/generation/rework", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          directory: currentDirectory,
          expected_etag: revision,
          shot_id: shotId,
          idempotency_key: makeIdempotencyKey(),
        }),
      });
      renderWorkspace(data, currentDirectory);
      promptDialog.close();
      setGenerationStatus("已提交返工：只重新生成这一张，旧候选保留。", "success");
    } catch (error) {
      setPromptStatus(error.message || "返工未提交，请重试。", "error");
    } finally {
      setBusy(false);
    }
  }


  function handlePromptEdit() {
    byId("save-prompt").disabled = busy || !promptReady
      || promptText.value === activePromptBaseline;
    byId("confirm-rework").disabled = busy || !promptReady || !promptReworkShotId;
    if (promptText.value !== activePromptBaseline) setPromptStatus("有未保存的提示词修改。", "");
    else setPromptStatus("");
    updateGenerationControls();
  }

  function sourceLabel(source) {
    return ({ user_input: "你提供的信息", reference_image: "模型参考图判断", model_inference: "模型推断", user_override: "你手动修改" })[source] || "来源待核对";
  }

  function factLabel(key) {
    if (key === "product_name") return "商品名称";
    const point = /^selling_point_(\d+)$/.exec(key);
    return point ? "真实卖点 " + point[1] : key;
  }

  function stateLabel(state) {
    return ({ confirmed: "已确认", inferred: "待核对", unknown: "未知", conflicted: "有冲突" })[state] || "待核对";
  }

  function renderBrief(fields, { isSaved = false, provider = null } = {}) {
    briefSection.hidden = false;
    briefForm.hidden = false;
    briefBaseline = JSON.parse(JSON.stringify(fields));
    briefDirty = false;
    briefNeedsSave = !isSaved;
    byId("analyze-product").setAttribute("aria-expanded", "true");
    const category = fields.category || { label: "", confidence: null, source: "model_inference" };
    byId("brief-category").value = category.label || "";
    byId("brief-category").dataset.initialValue = category.label || "";
    byId("brief-category").dataset.initialSource = category.source || "model_inference";
    byId("brief-category-confidence").value = category.confidence == null ? "" : String(category.confidence);
    byId("brief-category-source").value = category.source || "model_inference";
    byId("brief-category-origin").textContent = "来源：" + sourceLabel(category.source);
    byId("brief-facts").replaceChildren();
    if (!fields.facts.length) {
      const empty = document.createElement("p");
      empty.className = "field-help";
      empty.textContent = "暂时没有提取到商品事实；你仍可检查画面边界和待确认信息。";
      byId("brief-facts").append(empty);
    }
    fields.facts.forEach((fact, index) => {
      const group = document.createElement("fieldset");
      group.className = "brief-fact";
      group.dataset.key = fact.key;
      group.dataset.source = fact.source;
      group.dataset.initialSource = fact.source;
      group.dataset.sourceRefs = JSON.stringify(fact.source_refs || []);
      group.dataset.confidence = fact.confidence == null ? "" : String(fact.confidence);
      const legend = document.createElement("legend");
      legend.textContent = factLabel(fact.key);
      const origin = document.createElement("span");
      origin.className = "source-label";
      origin.dataset.factSource = "true";
      origin.setAttribute("aria-live", "polite");
      origin.textContent = "来源：" + sourceLabel(fact.source);
      const valueId = "brief-fact-value-" + index;
      const valueLabel = document.createElement("label");
      valueLabel.htmlFor = valueId;
      valueLabel.textContent = "事实内容";
      const value = document.createElement("textarea");
      value.id = valueId;
      value.rows = 2;
      value.maxLength = 2000;
      value.required = true;
      value.name = `facts[${index}][value]`;
      value.value = typeof fact.value === "string" ? fact.value : JSON.stringify(fact.value);
      value.dataset.factValue = "true";
      value.dataset.initialValue = value.value;
      value.setAttribute("aria-describedby", "brief-interpretation-help");
      const stateId = "brief-fact-state-" + index;
      const stateLabelNode = document.createElement("label");
      stateLabelNode.htmlFor = stateId;
      stateLabelNode.textContent = "核对状态";
      const state = document.createElement("select");
      state.id = stateId;
      state.name = `facts[${index}][state]`;
      state.dataset.factState = "true";
      state.dataset.initialState = fact.state;
      [["confirmed", "已确认"], ["inferred", "待核对"], ["unknown", "未知"], ["conflicted", "有冲突"]]
        .forEach(([key, text]) => {
          const option = document.createElement("option");
          option.value = key;
          option.textContent = text;
          option.selected = key === fact.state;
          state.append(option);
        });
      group.append(legend, origin, valueLabel, value, stateLabelNode, state);
      byId("brief-facts").append(group);
    });
    byId("brief-must-preserve").value = fields.must_preserve.join("\n");
    byId("brief-may-change").value = fields.may_change.join("\n");
    byId("brief-unknowns").value = fields.unknowns.join("\n");
    const versionText = isSaved ? "已保存版本 v" + fields.version : "尚未保存";
    byId("brief-provenance").textContent = provider
      ? versionText + " · " + provider.model_id + (provider.request_id ? " · 请求 " + provider.request_id : "")
      : versionText;
    byId("brief-provenance").hidden = false;
    byId("brief-status").hidden = true;
    byId("brief-save-state").textContent = isSaved
      ? "修改后保存会生成新版本。"
      : "这是未保存草案；保存后才进入工作空间。";
    byId("save-brief").textContent = isSaved ? "保存为新版本" : "保存商品理解";
    byId("save-brief").disabled = busy || !(briefDirty || briefNeedsSave);
  }

  function markBriefDirty() {
    if (!projection || busy) return;
    briefDirty = true;
    byId("brief-save-state").textContent = "有未保存的商品理解修改。";
    byId("save-brief").disabled = false;
    updateGenerationControls();
  }

  function updateFactOrigin(group) {
    const value = group.querySelector("[data-fact-value]");
    const state = group.querySelector("[data-fact-state]");
    const changed = value.value !== value.dataset.initialValue || state.value !== state.dataset.initialState;
    group.dataset.source = changed ? "user_override" : group.dataset.initialSource;
    group.querySelector("[data-fact-source]").textContent = "来源：" + sourceLabel(group.dataset.source);
  }

  function updateCategoryOrigin() {
    const input = byId("brief-category");
    const source = input.value.trim() !== input.dataset.initialValue
      ? "user_override" : input.dataset.initialSource;
    byId("brief-category-source").value = source;
    byId("brief-category-origin").textContent = "来源：" + sourceLabel(source);
  }

  function collectBriefEdits() {
    if (!briefBaseline) throw new Error("请先生成或载入商品理解。");
    const baselineCategory = briefBaseline.category || {};
    const categoryConfidence = byId("brief-category-confidence").value;
    const facts = Array.from(byId("brief-facts").querySelectorAll(".brief-fact")).map((group) => {
      const confidence = group.dataset.confidence;
      return {
        key: group.dataset.key,
        value: group.querySelector("[data-fact-value]").value.trim(),
        state: group.querySelector("[data-fact-state]").value,
        source: group.dataset.source || group.dataset.initialSource,
        confidence: confidence === "" ? null : Number(confidence),
        source_refs: JSON.parse(group.dataset.sourceRefs || "[]"),
      };
    });
    const lines = (id) => byId(id).value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean);
    return {
      category: {
        label: byId("brief-category").value.trim() || null,
        confidence: categoryConfidence === "" ? null : Number(categoryConfidence),
        source: byId("brief-category-source").value || baselineCategory.source || "model_inference",
      },
      facts,
      must_preserve: lines("brief-must-preserve"),
      may_change: lines("brief-may-change"),
      unknowns: lines("brief-unknowns"),
    };
  }

  function showBriefStatus(message, tone = "") {
    const status = byId("brief-status");
    status.textContent = message || "";
    status.dataset.tone = tone;
    status.hidden = !message;
  }

  async function analyzeProduct() {
    if (busy || dirty || !currentDirectory || !projection?.readiness?.can_generate_product_brief) return;
    if ((briefDirty || briefNeedsSave)
        && !window.confirm("这份商品理解有未保存内容；重新分析会替换当前编辑区，但不会删除已保存版本。继续吗？")) {
      return;
    }
    const expectedRevision = projection.workspace.revision;
    setNotice("");
    showBriefStatus("正在分析已保存的商品资料和参考图…");
    byId("analyze-product").textContent = "正在分析…";
    setBusy(true);
    try {
      const result = await request("/api/product-brief/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ directory: currentDirectory, expected_etag: expectedRevision }),
      });
      if (projection.workspace.revision !== expectedRevision
          || result.workspace_revision !== expectedRevision) {
        throw new Error("工作空间在分析期间发生变化；草案未保存，请重新载入后再试。");
      }
      renderBrief(result.product_brief, { provider: result.provider });
      showBriefStatus("商品理解草案已生成，检查并保存后才会进入工作空间。");
      byId("brief-category").focus({ preventScroll: true });
    } catch (error) {
      showBriefStatus(error.message, "error");
    } finally {
      byId("analyze-product").textContent = projection?.product_brief ? "重新分析" : "生成商品理解";
      setBusy(false);
    }
  }

  async function saveBrief(event) {
    event.preventDefault();
    if (busy || !briefForm.reportValidity() || !currentDirectory || !projection) return;
    let fields;
    try {
      fields = collectBriefEdits();
    } catch (error) {
      showBriefStatus(error.message, "error");
      return;
    }
    const previousVersion = projection.product_brief?.version ?? null;
    setNotice("");
    showBriefStatus("正在保存商品理解版本…");
    byId("brief-save-state").textContent = "正在保存…";
    setBusy(true);
    try {
      const data = await request("/api/product-brief", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          directory: currentDirectory,
          expected_etag: projection.workspace.revision,
          product_brief: fields,
        }),
      });
      const savedVersion = data.product_brief?.version;
      if (!savedVersion) throw new Error("保存响应缺少版本信息；请重新打开工作空间核对结果。");
      renderWorkspace(data, currentDirectory);
      const message = previousVersion === savedVersion
        ? `内容没有变化，继续使用版本 v${savedVersion}。`
        : `商品理解已保存为版本 v${savedVersion}。`;
      showBriefStatus(message, "success");
      byId("brief-save-state").textContent = message;
    } catch (error) {
      showBriefStatus(error.message, "error");
      byId("brief-save-state").textContent = "保存未完成；修改仍保留在当前页面。";
    } finally {
      setBusy(false);
    }
  }

  function handleBriefEdit(event) {
    if (event.target.id === "brief-category") updateCategoryOrigin();
    const group = event.target.closest(".brief-fact");
    if (group) updateFactOrigin(group);
    markBriefDirty();
  }

  async function openWorkspace(directory) {
    if (busy) return;
    setBusy(true);
    setNotice("");
    try {
      const data = await request("/api/workspaces/open", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ directory }),
      });
      sessionStorage.setItem(sessionKey, directory);
      renderWorkspace(data, directory);
      if (data.recent_index_warning) setNotice(data.recent_index_warning);
      byId("workspace-name").focus();
      await loadRecent();
    } catch (error) {
      setNotice(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function chooseFolder(purpose) {
    if (busy) return;
    setBusy(true);
    setNotice("");
    try {
      const selected = await request("/api/workspaces/select-folder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ purpose }),
      });
      if (!selected.directory) return;
      const path = purpose === "create" ? "/api/workspaces" : "/api/workspaces/open";
      const data = await request(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ directory: selected.directory }),
      });
      sessionStorage.setItem(sessionKey, selected.directory);
      renderWorkspace(data, selected.directory);
      if (data.recent_index_warning) setNotice(data.recent_index_warning);
      await loadRecent();
      if (purpose === "create") {
        imageInput.focus();
      } else {
        byId("workspace-name").focus();
      }
    } catch (error) {
      setNotice(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  function markDirty() {
    if (!projection || busy) return;
    dirty = true;
    byId("save-state").textContent = "有未保存的修改。";
    byId("workspace-status").textContent = "未保存";
    updateGenerationControls();
  }

  async function saveIntake(event) {
    event.preventDefault();
    if (busy) return;
    byId("product-name").setCustomValidity("");
    updateImageChoice({ revealError: true });
    if (!form.reportValidity()) return;
    const body = new FormData(form);
    if (!imageInput.files.length) body.delete("reference_images");
    setBusy(true);
    byId("save-state").textContent = "正在保存…";
    setNotice("");
    try {
      const data = await request("/api/intake", { method: "PUT", body });
      imageInput.value = "";
      renderWorkspace(data, currentDirectory);
      byId("save-state").textContent = "已保存到此工作空间。";
      setNotice("商品资料已保存。");
      await loadRecent();
    } catch (error) {
      const field = error.details && error.details.field;
      if (field === "product_name") {
        byId("product-name").setAttribute("aria-invalid", "true");
        byId("product-name-error").textContent = error.message;
        byId("product-name-error").hidden = false;
        byId("product-name").focus();
      } else if (field === "reference_images") {
        byId("image-error").textContent = error.message;
        byId("image-error").hidden = false;
        imageInput.setAttribute("aria-invalid", "true");
        imageInput.focus();
      }
      byId("save-state").textContent = "保存未完成。";
      setNotice(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  function handleCandidateChoose(event) {
    const reworkTarget = event.target.closest?.(".generation-rework");
    if (reworkTarget && !busy) {
      const reworkShotId = reworkTarget.dataset.reworkShotId;
      if (reworkShotId) openPrompt(reworkShotId, { rework: true });
      return;
    }
    const retryTarget = event.target.closest?.(".generation-retry");
    if (retryTarget && !busy) {
      const retryShotId = retryTarget.dataset.retryShotId;
      if (retryShotId) retryShot(retryShotId);
      return;
    }
    const target = event.target.closest?.(".candidate-choose");
    if (!target || busy) return;
    const shotId = target.dataset.shotId;
    const candidateId = target.dataset.candidateId;
    if (!shotId || !candidateId) return;
    if (chosenCandidates.get(shotId) === candidateId) {
      chosenCandidates.delete(shotId);
    } else {
      chosenCandidates.set(shotId, candidateId);
    }
    renderGeneration(projection?.plan || null);
    setSelectionStatus("");
  }

  async function retryShot(shotId) {
    if (busy || !currentDirectory || !projection) return;
    setBusy(true);
    setGenerationStatus("正在只重跑这一张…");
    try {
      const data = await request("/api/generation/rework", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          directory: currentDirectory,
          expected_etag: projection.workspace.revision,
          shot_id: shotId,
          idempotency_key: makeIdempotencyKey(),
        }),
      });
      renderWorkspace(data, currentDirectory);
      setGenerationStatus("已提交：只重跑这一张，其他图片的结果不受影响。", "success");
    } catch (error) {
      setGenerationStatus(error.message || "这张图没有提交成功，请重试。", "error");
    } finally {
      setBusy(false);
    }
  }

  async function saveSelection() {
    if (busy || !currentDirectory || !projection?.plan) return;
    const shots = projection.plan.shot_specs || [];
    const choices = shots
      .map((shot) => ({ shot_id: shot.id, candidate_sha256: chosenCandidates.get(shot.id) }))
      .filter((item) => item.candidate_sha256);
    if (choices.length !== shots.length) {
      setSelectionStatus("还有图片没有选定候选。", "error");
      return;
    }
    setBusy(true);
    setSelectionStatus("正在保存选择…");
    try {
      const data = await request("/api/selection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          directory: currentDirectory,
          expected_etag: projection.workspace.revision,
          choices,
        }),
      });
      renderWorkspace(data, currentDirectory);
      setSelectionStatus("选择已保存。");
    } catch (error) {
      setSelectionStatus(error.message || "选择未保存，请重试。", "error");
    } finally {
      setBusy(false);
    }
  }

  function planWordingDrift() {
    const shots = projection?.plan?.shot_specs || [];
    const choices = projection?.selection?.choices || [];
    const warnings = [];
    choices.forEach((choice) => {
      const shot = shots.find((item) => item.id === choice?.shot?.id);
      if (!shot || !shot.latest_prompt) return;
      const candidate = (shot.candidates || []).find(
        (item) => item.candidate_id === choice.candidate_sha256,
      );
      if (!candidate) return;
      const delivered = candidate.prompt?.version || 0;
      if (shot.latest_prompt.version > delivered) {
        warnings.push(`${shot.title}：交付的是提示词 v${delivered}，工作空间已有 v${shot.latest_prompt.version}（方案文本未更新）`);
      } else if (shot.latest_prompt.edit_mode === "manual") {
        warnings.push(`${shot.title}：提示词被手动改写为 v${shot.latest_prompt.version}，方案标题/用途可能已过时`);
      }
    });
    return warnings;
  }

  async function exportSelection() {
    if (busy || !currentDirectory || !projection?.selection) return;
    const drift = planWordingDrift();
    if (drift.length && !window.confirm(
      `导出前请注意：方案文本与提示词可能不一致\n- ${drift.join("\n- ")}\n\n点“确定”继续导出（README 会带上这条提示）；点“取消”先返回核对方案与提示词。`
    )) return;
    setBusy(true);
    setSelectionStatus("正在导出图片组与追溯清单…");
    try {
      const data = await request("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          directory: currentDirectory,
          expected_etag: projection.workspace.revision,
        }),
      });
      renderWorkspace(data, currentDirectory);
      setSelectionStatus("已导出：图片组与追溯清单都在导出目录中。");
      const wordingWarnings = data?.plan_wording_warnings || [];
      if (wordingWarnings.length) {
        setSelectionStatus(
          `已导出：图片组与追溯清单都在导出目录中；其中 ${wordingWarnings.length} 张的提示词与方案文本可能不一致（README 已注明，建议核对方案）。`,
          "error",
        );
      }
    } catch (error) {
      setSelectionStatus(error.message || "导出未完成，请重试。", "error");
    } finally {
      setBusy(false);
    }
  }

  async function revealExport() {
    if (!currentDirectory || !projection?.export) return;
    try {
      await request("/api/export/reveal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ directory: currentDirectory }),
      });
    } catch (error) {
      setSelectionStatus(error.message || "打开导出文件夹失败。", "error");
    }
  }

  async function returnHome() {
    if ((dirty || briefDirty || briefNeedsSave || planDirty)
        && !window.confirm("有未保存的修改；返回后会丢失。要继续吗？")) return;
    sessionStorage.removeItem(sessionKey);
    setNotice("");
    showHome();
    await loadRecent();
    byId("home-title").focus?.();
  }

  async function chooseFromHeader(purpose) {
    if (!intake.hidden && (dirty || briefDirty || briefNeedsSave || planDirty)
        && !window.confirm("有未保存的修改；切换工作空间后会丢失。要继续吗？")) return;
    await chooseFolder(purpose);
  }

  byId("create-workspace").addEventListener("click", () => chooseFolder("create"));
  byId("open-workspace").addEventListener("click", () => chooseFolder("open"));
  byId("top-create-workspace").addEventListener("click", () => chooseFromHeader("create"));
  byId("top-open-workspace").addEventListener("click", () => chooseFromHeader("open"));
  byId("brand-home").addEventListener("click", returnHome);
  byId("back-home").addEventListener("click", returnHome);
  byId("analyze-product").addEventListener("click", analyzeProduct);
  briefForm.addEventListener("input", handleBriefEdit);
  briefForm.addEventListener("change", handleBriefEdit);
  briefForm.addEventListener("submit", saveBrief);
  planGenerateForm.addEventListener("submit", generatePlan);
  planAdjustmentForm.addEventListener("submit", savePlan);
  byId("start-generation").addEventListener("click", startGeneration);
  byId("save-selection").addEventListener("click", saveSelection);
  byId("export-selection").addEventListener("click", exportSelection);
  byId("reveal-export").addEventListener("click", revealExport);
  byId("generation-shots").addEventListener("click", handleCandidateChoose);
  byId("reconcile-generation").addEventListener("click", reconcileGeneration);
  byId("refresh-generation").addEventListener("click", refreshGenerationState);
  planShots.addEventListener("click", handlePlanAction);
  planShots.addEventListener("input", handlePlanFieldEdit);
  planShots.addEventListener("change", handlePlanFieldEdit);
  promptForm.addEventListener("submit", savePrompt);
  byId("confirm-rework").addEventListener("click", confirmRework);
  promptText.addEventListener("input", handlePromptEdit);
  promptDialog.addEventListener("close", () => {
    activePromptShotId = null;
    activePromptVersion = null;
    activePromptBaseline = "";
    promptReady = false;
    promptText.value = "";
    setPromptReworkMode(null);
    updateGenerationControls();
  });
  imageInput.addEventListener("change", () => {
    updateImageChoice({ revealError: false });
    markDirty();
  });
  form.addEventListener("input", (event) => {
    if (event.target === byId("product-name")) {
      byId("product-name").removeAttribute("aria-invalid");
      byId("product-name-error").hidden = true;
    }
    markDirty();
  });
  form.addEventListener("submit", saveIntake);

  async function boot() {
    await loadRecent();
    const directory = sessionStorage.getItem(sessionKey);
    if (!directory) return;
    try {
      const query = new URLSearchParams({ directory });
      const data = await request("/api/workspace?" + query.toString());
      renderWorkspace(data, directory);
    } catch (error) {
      sessionStorage.removeItem(sessionKey);
      showHome();
      setNotice(error.message, "error");
    }
  }

  boot();
})();
