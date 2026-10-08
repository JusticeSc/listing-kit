(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const home = byId("home-screen");
  const intake = byId("intake-screen");
  const delivery = byId("delivery-screen");
  const notice = byId("app-notice");
  const form = byId("product-intake-form");
  const briefSection = byId("brief-workspace");
  const briefForm = byId("product-brief-form");
  const planSection = byId("plan-workspace");
  const planAdjustmentForm = byId("plan-adjustment-form");
  const planShots = byId("plan-shots");
  const promptDialog = byId("prompt-dialog");
  const reworkDialog = byId("rework-dialog");
  const promptForm = byId("prompt-editor-form");
  const promptText = byId("prompt-full-text");
  const imageInput = byId("reference-images");
  const sessionKey = "amzListingKit.productV1.workspaceDirectory";
  const deliveryKey = "amzListingKit.productV1.deliveryDirectory";
  let currentDirectory = null;
  let projection = null;
  let refItems = [];
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
  let reworkShotId = null;
  let reworkProposal = null;
  let reworkIdempotencyKey = null;
  let generationOutcomeUnknown = false;
  let chosenCandidates = new Map();
  let deliveryOpen = false;
  let deliveryPreflight = null;

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
    if (value) byId("export-delivery").disabled = true;
    byId("save-brief").disabled = value || briefForm.hidden || !(briefDirty || briefNeedsSave);
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
    reworkDialog.querySelectorAll("input, textarea").forEach((control) => {
      control.disabled = value;
    });
    byId("rework-preview-button").disabled = value;
    byId("rework-confirm").disabled = value || !reworkProposal;
    reworkDialog.setAttribute("aria-busy", value ? "true" : "false");
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
    refItems = [];
    byId("saved-images").replaceChildren();
    byId("image-selection").textContent = "";
    byId("image-error").hidden = true;
    byId("image-error").textContent = "";
  }

  function showHome() {
    home.hidden = false;
    intake.hidden = true;
    deliveryOpen = false;
    deliveryPreflight = null;
    delivery.hidden = true;
    sessionStorage.removeItem(deliveryKey);
    form.reset();
    briefForm.reset();
    projection = null;
    refItems = [];
    currentDirectory = null;
    stopGenerationPoll();
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

  function setReferencesFromProjection(references) {
    objectUrls.forEach((url) => URL.revokeObjectURL(url));
    objectUrls = [];
    refItems = (references || []).map((reference) => ({
      kind: "saved", sha256: reference.sha256, name: reference.name,
    }));
    renderReferenceTiles();
  }

  function referenceImageSource(item) {
    if (item.kind === "new") return item.objectUrl;
    const query = new URLSearchParams({ directory: currentDirectory });
    return "/api/workspace/references/" + item.sha256 + "?" + query.toString();
  }

  function makeTileButton(className, label, handler) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tile-button " + className;
    button.textContent = label;
    button.addEventListener("click", handler);
    return button;
  }

  function renderReferenceTiles() {
    const container = byId("saved-images");
    container.replaceChildren();
    refItems.forEach((item, index) => {
      const tile = document.createElement("figure");
      tile.className = "saved-image image-tile";
      tile.dataset.name = item.name;
      tile.dataset.kind = item.kind;
      const image = document.createElement("img");
      image.src = referenceImageSource(item);
      image.alt = (item.kind === "new" ? "待保存的商品参考图：" : "商品参考图：") + item.name;
      const caption = document.createElement("figcaption");
      caption.textContent = item.name;
      tile.append(image, caption);
      if (index === 0) {
        const badge = document.createElement("span");
        badge.className = "primary-badge";
        badge.textContent = "主要参考";
        tile.append(badge);
      }
      if (!intakeLocked) {
        const actions = document.createElement("div");
        actions.className = "tile-actions";
        actions.setAttribute("role", "group");
        actions.setAttribute("aria-label", "「" + item.name + "」的图片操作");
        if (index > 0) {
          actions.append(
            makeTileButton("tile-primary", "设为主要", () => moveReference(index, 0)),
            makeTileButton("tile-left", "前移", () => moveReference(index, index - 1)),
          );
        }
        actions.append(makeTileButton("tile-remove", "移除", () => removeReference(index)));
        tile.append(actions);
      }
      container.append(tile);
    });
  }

  function moveReference(fromIndex, toIndex) {
    if (toIndex < 0 || toIndex >= refItems.length) return;
    const [item] = refItems.splice(fromIndex, 1);
    refItems.splice(toIndex, 0, item);
    renderReferenceTiles();
    updateImageChoice();
    markDirty();
  }

  function removeReference(index) {
    const [item] = refItems.splice(index, 1);
    if (item && item.kind === "new") URL.revokeObjectURL(item.objectUrl);
    renderReferenceTiles();
    updateImageChoice();
    byId("image-error").textContent = "";
    byId("image-error").hidden = true;
    imageInput.removeAttribute("aria-invalid");
    markDirty();
  }

  function updateImageChoice({ revealError = false } = {}) {
    const count = refItems.length;
    const invalid = count === 0;
    const message = "请先选择至少 1 张商品参考图。";
    imageInput.setCustomValidity(invalid ? message : "");
    byId("image-selection").textContent = count
      ? "共 " + count + " 张参考图；第 1 张为主要参考。"
      : "";
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
  }

  function renderWorkspace(data, directory) {
    if (currentDirectory !== directory) chosenCandidates = new Map();
    projection = data;
    currentDirectory = directory;
    seedChoicesFromProjection();
    generationOutcomeUnknown = false;
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
    byId("save-state").textContent = data.product_brief
      ? "商品资料已保存。"
      : "资料会随动作一起保存到工作空间文件夹。";
    byId("image-error").hidden = true;
    byId("image-error").textContent = "";
    byId("product-name-error").hidden = true;
    byId("product-name-error").textContent = "";
    byId("product-name").removeAttribute("aria-invalid");
    intakeLocked = Boolean(data.product_brief);
    imageInput.removeAttribute("aria-invalid");
    imageInput.value = "";
    setReferencesFromProjection(data.intake.reference_images || []);
    updateImageChoice();
    ["product-name", "product-description", "selling-points", "user-intent", "reference-images"].forEach((id) => {
      byId(id).disabled = intakeLocked;
    });
    byId("upload-zone").hidden = intakeLocked;
    briefSection.hidden = !data.product_brief;
    if (data.product_brief) {
      renderBrief(data.product_brief, { isSaved: true });
    } else {
      briefForm.hidden = true;
      briefBaseline = null;
      briefDirty = false;
      briefNeedsSave = false;
      byId("brief-status").hidden = true;
      byId("brief-provenance").hidden = true;
      byId("brief-facts").replaceChildren();
    }
    setGenerationStatus("");
    renderPlan(data.plan);
    renderWorkspaceStage(data);
    home.hidden = true;
    intake.hidden = deliveryOpen;
    delivery.hidden = !deliveryOpen;
    document.title = (data.intake.product_name || "未命名商品")
      + (deliveryOpen ? " · 交付检查" : " · 商品套图工作台");
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
      byId("plan-save-state").textContent = "方案尚未生成；点“按此方案生成”会补齐缺失的步骤并开始。";
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

  function unknownGenerationActions() {
    return pendingGenerationActions().filter(({ attempt }) => attempt.status === "UNKNOWN");
  }

  function hasOpenGenerationAttempt() {
    return generationAttempts().some(({ attempt }) => openGenerationStates.has(attempt.status));
  }

  const GENERATION_POLL_MS = 4000;
  let generationPoll = null;
  let generationPollInFlight = false;

  function pollableGenerationActions() {
    return pendingGenerationActions().filter(
      ({ attempt }) => Boolean(attempt.provider_task_id)
        && (attempt.status === "SUBMITTED" || attempt.status === "RUNNING"));
  }

  function stopGenerationPoll() {
    if (generationPoll !== null) {
      window.clearInterval(generationPoll);
      generationPoll = null;
    }
  }

  function syncGenerationPoll() {
    const active = Boolean(currentDirectory) && pollableGenerationActions().length > 0;
    if (active && generationPoll === null) {
      generationPoll = window.setInterval(pollGenerationOnce, GENERATION_POLL_MS);
    } else if (!active) {
      stopGenerationPoll();
    }
  }

  async function pollGenerationOnce() {
    if (generationPollInFlight || busy || !currentDirectory || !projection) return;
    if (dirty || briefDirty || briefNeedsSave || planDirty || promptDialog.open) return;
    const targets = pollableGenerationActions();
    if (!targets.length) {
      stopGenerationPoll();
      return;
    }
    generationPollInFlight = true;
    const directory = currentDirectory;
    try {
      let data = null;
      for (const { attempt } of targets) {
        data = await request(
          `/api/attempts/${encodeURIComponent(attempt.action_id)}/reconcile`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ directory }),
          },
        );
        if (currentDirectory !== directory) return;
      }
      if (data) {
        renderWorkspace(data, directory);
        const shots = projection?.plan?.shot_specs || [];
        const done = shots.filter((shot) => (shot.candidates || []).length > 0).length;
        if (!pollableGenerationActions().length) {
          setGenerationStatus(`整套生成已结束：${done}/${shots.length} 张有候选。`, "success");
        } else {
          setGenerationStatus(`逐图生成中：${done}/${shots.length} 张已有候选，自动更新。`);
        }
      }
    } catch (error) {
      // Keep the last known state; the manual buttons remain available.
    } finally {
      generationPollInFlight = false;
      syncGenerationPoll();
    }
  }

  function generationErrorGuidance(raw) {
    const text = String(raw || "");
    if (text.includes("UPSTREAM_ACCOUNT_ARREARS")) {
      return "百炼账户欠费：充值后再点“重新生成这张”；系统不会自动重复提交。";
    }
    if (text.includes("UPSTREAM_RATE_LIMITED")) {
      return "上游限流：稍等片刻后再点“重新生成这张”。";
    }
    if (text.includes("PROVIDER_API_KEY_MISSING")) {
      return "图片模型凭据缺失：配置 API Key 后再生成。";
    }
    return "";
  }

  function hasUnsavedGenerationInputs() {
    return dirty || briefDirty || briefNeedsSave || planDirty
      || (promptReady && promptText.value !== activePromptBaseline);
  }

  function updateGenerationControls() {
    const plan = projection?.plan;
    const hasBrief = Boolean(projection?.product_brief);
    const hasPlan = Boolean(plan?.shot_specs?.length);
    const openAttempt = hasOpenGenerationAttempt();
    const actionIds = pendingGenerationActions();
    const hasPreviousAttempt = generationAttempts().length > 0;
    const hasUnsaved = hasUnsavedGenerationInputs();
    const suiteBlocked = busy || openAttempt || generationOutcomeUnknown;

    const generateSuite = byId("generate-suite");
    generateSuite.disabled = suiteBlocked || intakeLocked;
    generateSuite.textContent = openAttempt || (hasPreviousAttempt && !hasPlan)
      ? "等待本轮结果"
      : "生成整套图片";
    byId("preview-plan").disabled = suiteBlocked || intakeLocked;
    const fromPlan = byId("generate-from-plan");
    fromPlan.disabled = suiteBlocked || !hasBrief || hasUnsaved;
    fromPlan.textContent = openAttempt
      ? "等待本轮结果"
      : (hasPreviousAttempt ? "再次生成整套" : "按此方案生成");
    const hasUnknown = unknownGenerationActions().length > 0;
    byId("reconcile-generation").hidden = !hasUnknown;
    byId("reconcile-generation").disabled = busy;
    byId("refresh-generation").hidden = !(generationOutcomeUnknown || (openAttempt && actionIds.length === 0));
    byId("refresh-generation").disabled = busy;

    const hint = byId("generation-hint");
    let message = "";
    if (generationOutcomeUnknown) {
      message = "上次提交结果尚未确认；先重新载入状态，不要重复提交。";
    } else if (openAttempt && actionIds.length) {
      message = hasUnknown
        ? "有任务结果待核对；点“核对当前生成状态”，系统只查原任务，不会重复提交。"
        : "逐图生成进行中，结果会自动更新；已完成一张显示一张。";
    } else if (openAttempt) {
      message = "本方案仍有生成任务在处理中；请点“重新载入状态”，不能重复提交。";
    } else if (dirty) {
      message = "先完成商品资料的编辑。";
    } else if (briefDirty || briefNeedsSave) {
      message = "先保存商品理解后再生成。";
    } else if (planDirty) {
      message = "先保存套图方案调整后再生成。";
    } else if (promptReady && promptText.value !== activePromptBaseline) {
      message = "先保存提示词修改后再生成。";
    }
    hint.textContent = message;
    hint.hidden = !message;
    syncGenerationPoll();
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

  let reviewShotId = null;
  let reviewCandidateId = null;
  let brokenCandidates = new Set();

  function reviewShots() {
    return projection?.plan?.shot_specs || [];
  }

  function latestAttempt(shot) {
    const attempts = (shot?.generation_attempts || []).slice().sort(
      (left, right) => String(left.created_at || "").localeCompare(String(right.created_at || "")));
    return attempts.at(-1) || null;
  }

  function currentReviewShot() {
    const shots = reviewShots();
    if (!shots.length) return null;
    const found = shots.find((shot) => shot.id === reviewShotId);
    if (found) return found;
    return shots.find((shot) => (shot.candidates || []).length) || shots[0];
  }

  function currentReviewCandidate(shot) {
    const items = shot?.candidates || [];
    if (!items.length) return null;
    const viewed = items.find((item) => item.candidate_id === reviewCandidateId);
    if (viewed) return viewed;
    const adopted = items.find((item) => item.candidate_id === chosenCandidates.get(shot.id));
    return adopted || items[items.length - 1];
  }

  function selectReviewShot(shotId) {
    reviewShotId = shotId;
    reviewCandidateId = null;
    renderGeneration(projection?.plan || null);
  }

  function selectReviewCandidate(candidateId) {
    reviewCandidateId = candidateId;
    renderGeneration(projection?.plan || null);
  }

  async function adoptCurrentCandidate() {
    const shot = currentReviewShot();
    const candidate = currentReviewCandidate(shot);
    if (busy || !shot || !candidate || !currentDirectory || !projection) return;
    if (brokenCandidates.has(candidate.candidate_id)) {
      setSelectionStatus("这张候选文件不可读取，不能采用；生成记录仍保留。", "error");
      return;
    }
    setBusy(true);
    setSelectionStatus("正在保存这张的选择…");
    try {
      const data = await request(
        `/api/shots/${encodeURIComponent(shot.id)}/selection`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            directory: currentDirectory,
            expected_etag: projection.workspace.revision,
            candidate_sha256: candidate.candidate_id,
          }),
        });
      renderWorkspace(data, currentDirectory);
      const shots = data.plan?.shot_specs || [];
      const adopted = new Set(
        (data.selection?.choices || []).map((item) => item.shot.id));
      const count = shots.filter((item) => adopted.has(item.id)).length;
      setSelectionStatus(
        count === shots.length
          ? `全部 ${count}/${shots.length} 张已选定；可以导出。`
          : `已选定这张（${count}/${shots.length}）；采用即保存，继续审核其余图片。`);
    } catch (error) {
      setSelectionStatus(error.message || "选择未保存，请重试。", "error");
    } finally {
      setBusy(false);
    }
  }

  function renderGeneration(plan) {
    const section = byId("generation-workspace");
    const workbench = byId("review-workbench");
    const strip = byId("generation-shots");
    const shots = plan?.shot_specs || [];
    section.hidden = !shots.length;
    workbench.hidden = !shots.length;
    strip.replaceChildren();
    byId("review-candidates").replaceChildren();
    byId("review-attempts").replaceChildren();
    if (!shots.length) {
      updateGenerationControls();
      renderSelectionPanel(null);
      return;
    }

    const totalCandidates = shots.reduce((count, shot) => count + (shot.candidates || []).length, 0);
    const completedShots = shots.filter((shot) => (shot.candidates || []).length > 0).length;
    const runningShots = shots.filter(
      (shot) => openGenerationStates.has(latestAttempt(shot)?.status)).length;
    let title = runningShots
      ? `逐图生成中 · ${completedShots}/${shots.length} 张已有候选`
      : `生成结果 · ${completedShots}/${shots.length} 张有候选`;
    if (totalCandidates) title += ` · ${totalCandidates} 个候选`;
    byId("generation-title").textContent = title;

    const active = currentReviewShot();
    const activeId = active?.id || null;
    shots.forEach((shot, index) => {
      const latest = latestAttempt(shot);
      const current = currentReviewCandidate(shot);
      const adoptedId = chosenCandidates.get(shot.id);

      const tab = document.createElement("button");
      tab.type = "button";
      tab.className = "generation-shot";
      tab.dataset.shotId = shot.id;
      tab.dataset.state = latest?.status || "EMPTY";
      tab.dataset.hasCandidate = (shot.candidates || []).length ? "true" : "false";
      tab.dataset.adopted = adoptedId ? "true" : "false";
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", shot.id === activeId ? "true" : "false");
      tab.title = shot.title || shot.id || "套图图片";

      const thumb = document.createElement("span");
      thumb.className = "review-thumb";
      if (current) {
        const image = document.createElement("img");
        image.src = candidateImageUrl(current);
        image.alt = "";
        image.loading = "lazy";
        image.decoding = "async";
        thumb.append(image);
      } else {
        const placeholder = document.createElement("span");
        placeholder.className = "review-thumb-empty";
        placeholder.textContent = String(index + 1).padStart(2, "0");
        thumb.append(placeholder);
      }
      const label = document.createElement("span");
      label.className = "review-thumb-label";
      label.textContent = shot.title || shot.id || "套图图片";
      const state = document.createElement("span");
      state.className = "generation-state";
      state.dataset.state = latest?.status || "EMPTY";
      state.textContent = generationStateLabel(latest?.status);
      tab.append(thumb, label, state);
      if (adoptedId) {
        const badge = document.createElement("span");
        badge.className = "review-adopted-badge";
        badge.textContent = "已采用";
        tab.append(badge);
      }
      strip.append(tab);
    });

    const shotTitle = byId("review-shot-title");
    const shotState = byId("review-shot-state");
    const image = byId("review-image");
    const empty = byId("review-empty");
    const caption = byId("review-caption");
    const error = byId("review-error");
    const adoptButton = byId("review-adopt");
    const reworkButton = byId("review-rework");
    const retryButton = byId("review-retry");
    const promptButton = byId("review-prompt");
    const records = byId("review-records");
    const candidateList = byId("review-candidates");

    if (!active) {
      shotTitle.textContent = "尚未生成";
      shotState.textContent = "";
      image.hidden = true;
      empty.hidden = false;
      empty.textContent = "生成整套图片后，这里会显示当前图片的大图。";
      caption.textContent = "";
      adoptButton.disabled = true;
      reworkButton.hidden = true;
      retryButton.hidden = true;
      promptButton.hidden = true;
      records.hidden = true;
      error.hidden = true;
      candidateList.hidden = true;
      updateGenerationControls();
      renderSelectionPanel(plan);
      return;
    }

    const activeIndex = shots.indexOf(active);
    const latest = latestAttempt(active);
    const candidates = active.candidates || [];
    const shown = currentReviewCandidate(active);
    const adoptedId = chosenCandidates.get(active.id);
    const running = openGenerationStates.has(latest?.status);

    shotTitle.textContent = `${String(activeIndex + 1).padStart(2, "0")}  ${active.title || active.id || "套图图片"}`;
    shotState.dataset.state = latest?.status || "EMPTY";
    shotState.textContent = generationStateLabel(latest?.status);

    if (shown) {
      image.src = candidateImageUrl(shown);
      image.alt = `${active.title || "套图图片"}，${shown.candidate_id === adoptedId ? "已采用候选" : "候选预览"}`;
      image.onerror = () => {
        brokenCandidates.add(shown.candidate_id);
        image.hidden = true;
        empty.hidden = false;
        empty.textContent = "这张候选文件不可读取，不能采用；生成记录仍保留。";
        adoptButton.disabled = true;
      };
      image.hidden = false;
      empty.hidden = true;
      const isLatest = Boolean(latest && shown.attempt_action_id === latest.action_id);
      caption.textContent = [
        isLatest ? "本轮候选" : "历史候选",
        shown.width && shown.height ? `${shown.width} × ${shown.height}` : "",
        shown.created_at ? formatDate(shown.created_at) : "",
        shown.candidate_id === adoptedId ? "已采用" : "尚未采用",
      ].filter(Boolean).join(" · ");
    } else {
      image.onerror = null;
      image.hidden = true;
      image.removeAttribute("src");
      empty.hidden = false;
      empty.textContent = running
        ? "这张图正在生成，结果会自动更新。"
        : (latest?.status === "UNKNOWN"
          ? "这张图的结果待核对；点“核对当前生成状态”，系统只查原任务。"
          : (latest ? "这张图还没有候选，可以“重新生成这张”。" : "这张图尚未生成。"));
      caption.textContent = "";
    }

    candidates.forEach((candidate, index) => {
      const figure = document.createElement("figure");
      figure.className = "generation-candidate";
      figure.dataset.chosen = candidate.candidate_id === adoptedId ? "true" : "false";
      figure.dataset.viewed = candidate.candidate_id === shown?.candidate_id ? "true" : "false";
      const button = document.createElement("button");
      button.type = "button";
      button.className = "review-candidate-button";
      button.dataset.candidateId = candidate.candidate_id;
      button.setAttribute("aria-label", `查看候选 ${index + 1}`);
      button.setAttribute("aria-pressed", candidate.candidate_id === shown?.candidate_id ? "true" : "false");
      const thumb = document.createElement("img");
      thumb.src = candidateImageUrl(candidate);
      thumb.alt = "";
      thumb.loading = "lazy";
      thumb.decoding = "async";
      button.append(thumb);
      const label = document.createElement("figcaption");
      thumb.addEventListener("error", () => {
        figure.dataset.broken = "true";
        button.disabled = true;
        brokenCandidates.add(candidate.candidate_id);
        const note = document.createElement("span");
        note.className = "candidate-preview-error";
        note.textContent = "预览不可用";
        label.append(note);
      }, { once: true });
      const strong = document.createElement("strong");
      const isLatest = Boolean(latest && candidate.attempt_action_id === latest.action_id);
      strong.textContent = isLatest ? "本轮候选" : "历史候选";
      const meta = document.createElement("span");
      meta.textContent = candidate.candidate_id === adoptedId ? "已采用" : `候选 ${index + 1}`;
      label.append(strong, meta);
      figure.append(button, label);
      candidateList.append(figure);
    });
    candidateList.hidden = candidates.length === 0;

    adoptButton.disabled = !shown || shown.candidate_id === adoptedId;
    adoptButton.textContent = shown && shown.candidate_id === adoptedId ? "已采用这张" : "采用此图";
    const needsRegeneration = shotNeedsRegeneration(active);
    reworkButton.hidden = !candidates.length || running || needsRegeneration;
    reworkButton.dataset.reworkShotId = active.id;
    retryButton.hidden = running || (candidates.length > 0 && !needsRegeneration);
    retryButton.dataset.retryShotId = active.id;
    retryButton.textContent = needsRegeneration ? "用新提示词重新生成这张" : "重新生成这张";
    promptButton.hidden = !active.latest_prompt;
    promptButton.dataset.promptShotId = active.id;

    const rawError = latest?.error
      ? (typeof latest.error === "string" ? latest.error : (latest.error.message || ""))
      : "";
    if (rawError) {
      error.textContent = generationErrorGuidance(rawError) || rawError;
      error.title = rawError;
      error.hidden = false;
    } else {
      error.textContent = "";
      error.hidden = true;
    }

    const attemptHistory = (active.generation_attempts || []).slice().sort(
      (left, right) => String(left.created_at || "").localeCompare(String(right.created_at || "")));
    records.hidden = !attemptHistory.length;
    attemptHistory.forEach((attempt) => {
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
      byId("review-attempts").append(row);
    });

    updateGenerationControls();
    renderSelectionPanel(plan);
  }

  function shotNeedsRegeneration(shot) {
    const latest = shot?.latest_prompt;
    if (!latest) return false;
    const candidates = shot.candidates || [];
    if (!candidates.length) return false;
    const newest = candidates.reduce(
      (max, item) => Math.max(max, Number(item?.prompt?.version || 0)), 0);
    return Number(latest.version || 0) > newest;
  }

  function savedSelectionDigest(shotId) {
    const choices = (projection?.selection?.choices) || [];
    const match = choices.find((item) => item?.shot?.id === shotId);
    return match?.candidate_sha256 || null;
  }

  function seedChoicesFromProjection() {
    const choices = (projection?.selection?.choices) || [];
    chosenCandidates = new Map(
      choices
        .filter((item) => item?.shot?.id && item?.candidate_sha256)
        .map((item) => [item.shot.id, item.candidate_sha256]),
    );
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
    const chosen = shots.filter((shot) => savedSelectionDigest(shot.id));
    const complete = chosen.length === shots.length;
    const stale = shots.filter(shotNeedsRegeneration).length;
    byId("selection-progress").textContent = `${chosen.length}/${shots.length} 张已选`;
    byId("export-selection").disabled = busy || !complete;
    byId("selection-hint").textContent = complete
      ? "全部图片已选定；点“检查并导出”核对交付内容。"
      : stale
        ? `有 ${stale} 张图的提示词已更新；重新生成并采用新图，或重新采用旧图后在交付检查里确认不一致。`
        : "在审核区逐张查看候选并点“采用此图”；采用即保存，全部选定后可检查并导出。";
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

  async function loadCurrentProjection() {
    const query = new URLSearchParams({ directory: currentDirectory });
    return request("/api/workspace?" + query.toString());
  }

  async function reconcileGeneration() {
    if (busy || !currentDirectory) return;
    const actionIds = unknownGenerationActions().map(({ attempt }) => attempt.action_id);
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

  function setReworkStatus(message, tone = "") {
    const status = byId("rework-status");
    status.textContent = message || "";
    status.dataset.tone = tone;
    status.hidden = !message;
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

  async function openPrompt(shotId) {
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

  async function openRework(shotId) {
    if (busy || !projection?.plan || !currentDirectory) return;
    if (dirty || briefDirty || briefNeedsSave) {
      setPlanStatus("先保存商品资料和商品理解，再重做单张图片。", "error");
      return;
    }
    if (planDirty) {
      if (!window.confirm("方案调整尚未保存；打开返工层会放弃调整。要继续吗？")) return;
      renderPlan(projection.plan);
    }
    const shot = projection.plan.shot_specs.find((item) => item.id === shotId);
    if (!shot || !(shot.candidates || []).length) return;
    reworkShotId = shot.id;
    reworkProposal = null;
    reworkIdempotencyKey = null;
    reworkDialog.querySelectorAll('input[name="rework-reason"]').forEach((box) => {
      box.checked = false;
    });
    byId("rework-direction").value = "";
    byId("rework-preview").hidden = true;
    byId("rework-confirm").disabled = true;
    byId("rework-dialog-title").textContent = `重做这张：${shot.title || shot.id}`;
    byId("rework-dialog-meta").textContent = shot.latest_prompt
      ? `当前提示词 v${shot.latest_prompt.version}；预览不会调用图片模型。`
      : "这张图还没有提示词。";
    setReworkStatus("");
    if (!reworkDialog.open) reworkDialog.showModal();
  }

  function renderReworkProposal(data) {
    byId("rework-result").textContent = data.expected_result || "";
    byId("rework-keep").replaceChildren();
    (data.keep || []).forEach((item) => {
      const row = document.createElement("li");
      row.textContent = item;
      byId("rework-keep").append(row);
    });
    byId("rework-change").replaceChildren();
    (data.change || []).forEach((item) => {
      const row = document.createElement("li");
      row.textContent = item;
      byId("rework-change").append(row);
    });
    const diff = byId("rework-diff");
    diff.replaceChildren();
    const labels = { added: "新增", changed: "修改", removed: "移除" };
    (data.prompt?.diff || []).forEach((entry) => {
      const row = document.createElement("div");
      row.className = "rework-diff-row";
      const title = document.createElement("strong");
      title.textContent = `${labels[entry.kind] || entry.kind} · ${entry.id}`;
      const body = document.createElement("p");
      body.textContent = entry.kind === "changed"
        ? `原：${entry.before || ""}\n新：${entry.after || ""}`
        : (entry.text || "");
      row.append(title, body);
      diff.append(row);
    });
    if (!diff.childElementCount) {
      const note = document.createElement("p");
      note.className = "field-help";
      note.textContent = "提示词块没有逐字变化。";
      diff.append(note);
    }
    byId("rework-preview").hidden = false;
  }

  async function previewRework() {
    if (busy || !reworkShotId || !projection || !currentDirectory) return;
    const shotId = reworkShotId;
    const reasons = Array.from(
      reworkDialog.querySelectorAll('input[name="rework-reason"]:checked'),
    ).map((box) => box.value);
    const direction = byId("rework-direction").value.trim().slice(0, 500);
    if (!reasons.length && !direction) {
      setReworkStatus("先勾选不满意的地方，或写一句想怎么改。", "error");
      return;
    }
    setBusy(true);
    setReworkStatus("正在生成返工方案（预览阶段不调用图片模型）…");
    try {
      const data = await request(
        `/api/shots/${encodeURIComponent(shotId)}/rework-preview`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            directory: currentDirectory,
            expected_etag: projection.workspace.revision,
            quick_reasons: reasons,
            direction,
          }),
        });
      reworkProposal = data;
      reworkIdempotencyKey = makeIdempotencyKey();
      renderReworkProposal(data);
      setReworkStatus(
        `返工方案已生成：将创建 Prompt v${data.base.prompt_version + 1}，只重做这一张；确认后才会调用图片模型。`,
        "success");
    } catch (error) {
      reworkProposal = null;
      reworkIdempotencyKey = null;
      byId("rework-preview").hidden = true;
      setReworkStatus(error.message || "返工方案生成失败，请重试。", "error");
    } finally {
      setBusy(false);
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
      setPromptStatus(
        `提示词已保存为 v${shot.latest_prompt.version}；这张图需要重新生成并重新采用后才能导出。`,
        "success");
    } catch (error) {
      setPromptStatus(error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function confirmRework() {
    if (busy || !reworkShotId || !reworkProposal || !reworkIdempotencyKey
        || !projection || !currentDirectory) return;
    const shotId = reworkShotId;
    setBusy(true);
    setReworkStatus("正在确认并提交这一张的返工…");
    try {
      const data = await request(
        `/api/shots/${encodeURIComponent(shotId)}/rework`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            directory: currentDirectory,
            expected_etag: projection.workspace.revision,
            proposal: reworkProposal,
            idempotency_key: reworkIdempotencyKey,
          }),
        });
      renderWorkspace(data, currentDirectory);
      reworkDialog.close();
      setGenerationStatus("已确认返工：只重新生成这一张；旧候选保留，重新采用后才能导出。", "success");
    } catch (error) {
      const code = error.details?.code;
      if (code === "PROPOSAL_STALE" || code === "PROPOSAL_INVALID" || code === "REVISION_CONFLICT") {
        reworkProposal = null;
        reworkIdempotencyKey = null;
        byId("rework-confirm").disabled = true;
        byId("rework-preview").hidden = true;
        setReworkStatus(`返工方案已过期或冲突：${error.message} 请重新生成返工方案。`, "error");
        try {
          const fresh = await loadCurrentProjection();
          renderWorkspace(fresh, currentDirectory);
        } catch (_) {
          // 保留当前画面；上面的提示已经要求重新生成返工方案。
        }
      } else {
        setReworkStatus(error.message || "返工未提交，请重试。", "error");
      }
    } finally {
      setBusy(false);
    }
  }


  function handlePromptEdit() {
    byId("save-prompt").disabled = busy || !promptReady
      || promptText.value === activePromptBaseline;
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
      const versionChanged = previousVersion !== savedVersion;
      let message = versionChanged
        ? `商品理解已保存为版本 v${savedVersion}。`
        : `内容没有变化，继续使用版本 v${savedVersion}。`;
      if (versionChanged) {
        showBriefStatus(message + "正在更新受影响的套图方案…");
        byId("brief-save-state").textContent = "正在更新套图方案…";
        try {
          const compiled = await request("/api/plan/compile", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              directory: currentDirectory,
              expected_etag: data.workspace.revision,
            }),
          });
          renderWorkspace(compiled, currentDirectory);
          message = `商品理解已保存为版本 v${savedVersion}，套图方案已同步更新。`;
        } catch (compileError) {
          message = `商品理解已保存为版本 v${savedVersion}；套图方案更新未完成（${compileError.message}），生成整套时会自动补齐。`;
        }
      }
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

  function buildIntakeFormData() {
    byId("product-name").setCustomValidity("");
    updateImageChoice({ revealError: true });
    if (!form.reportValidity()) return null;
    const body = new FormData(form);
    body.delete("reference_images");
    body.delete("action_id");
    const referenceOrder = [];
    let uploadIndex = 0;
    refItems.forEach((item) => {
      if (item.kind === "new") {
        body.append("reference_images", item.file, item.name);
        referenceOrder.push("upload:" + uploadIndex);
        uploadIndex += 1;
      } else {
        referenceOrder.push("sha256:" + item.sha256);
      }
    });
    body.set("reference_order", JSON.stringify(referenceOrder));
    return body;
  }

  function suiteActionKey() {
    return "amzListingKit.suiteAction." + currentDirectory;
  }

  function currentSuiteActionId() {
    try {
      const existing = window.localStorage.getItem(suiteActionKey());
      if (existing && /^[A-Za-z0-9_-]{8,80}$/.test(existing)) return existing;
      const value = "ui" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
      window.localStorage.setItem(suiteActionKey(), value);
      return value;
    } catch (error) {
      return "ui" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
    }
  }

  function freshSuiteActionId() {
    try { window.localStorage.removeItem(suiteActionKey()); } catch (error) { /* ignore */ }
    return currentSuiteActionId();
  }

  function clearSuiteActionId() {
    try { window.localStorage.removeItem(suiteActionKey()); } catch (error) { /* ignore */ }
  }

  function renderIntakeFailure(error) {
    const field = error.details && error.details.field;
    let stateMessage = "动作未开始。";
    if (field === "product_name") {
      byId("product-name").setAttribute("aria-invalid", "true");
      byId("product-name-error").textContent = error.message;
      byId("product-name-error").hidden = false;
      byId("product-name").focus();
      stateMessage = "动作未开始：请填写商品名称。";
    } else if (field === "revision") {
      stateMessage = "动作未开始：工作空间已在别处更新，请重新载入后再试。";
    } else if (field === "reference_images" || field === "reference_order") {
      byId("image-error").textContent = error.message;
      byId("image-error").hidden = false;
      imageInput.setAttribute("aria-invalid", "true");
      imageInput.focus();
      stateMessage = "动作未开始：请检查商品参考图。";
    }
    byId("save-state").textContent = stateMessage;
    setNotice(error.message, "error");
  }

  async function generateSuite(event) {
    event.preventDefault();
    if (busy || !currentDirectory) return;
    const body = buildIntakeFormData();
    if (!body) return;
    const hasAttempts = generationAttempts().length > 0;
    if (hasAttempts && !window.confirm(
      "这个工作空间已有生成记录。重新生成会创建新一批任务，已有候选会保留。确定继续？")) return;
    const actionId = hasAttempts ? freshSuiteActionId() : currentSuiteActionId();
    body.set("action_id", actionId);
    setBusy(true);
    byId("save-state").textContent = "正在保存资料、准备方案并提交生成…";
    setNotice("");
    const directory = currentDirectory;
    try {
      const data = await request("/api/generations", { method: "POST", body });
      clearSuiteActionId();
      imageInput.value = "";
      renderWorkspace(data, directory);
      byId("save-state").textContent = "已开始生成。";
      setNotice("整套生成已开始，进度和结果会在下方逐张显示。");
      await loadRecent();
    } catch (error) {
      renderIntakeFailure(error);
    } finally {
      setBusy(false);
    }
  }

  async function previewPlan() {
    if (busy || !currentDirectory) return;
    const body = buildIntakeFormData();
    if (!body) return;
    setBusy(true);
    byId("save-state").textContent = "正在保存资料并生成方案…";
    setNotice("");
    const directory = currentDirectory;
    try {
      const data = await request("/api/plan/compile", { method: "POST", body });
      imageInput.value = "";
      renderWorkspace(data, directory);
      byId("save-state").textContent = "方案已生成，可在下方核对。";
      setNotice("套图方案已生成；核对或调整后点“按此方案生成”。");
      await loadRecent();
    } catch (error) {
      renderIntakeFailure(error);
    } finally {
      setBusy(false);
    }
  }

  async function generateFromPlan() {
    if (busy || !currentDirectory || !projection?.product_brief) return;
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
    const actionId = generationAttempts().length ? freshSuiteActionId() : currentSuiteActionId();
    const directory = currentDirectory;
    generationOutcomeUnknown = false;
    setGenerationStatus("正在准备方案并提交整套生成任务…");
    setBusy(true);
    try {
      const data = await request("/api/generations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          directory,
          expected_etag: projection.workspace.revision,
          action_id: actionId,
        }),
      });
      clearSuiteActionId();
      renderWorkspace(data, directory);
      setGenerationStatus("生成任务已记录；各张图的进度和候选会逐项显示。", "success");
    } catch (error) {
      setGenerationStatus("提交未完成：" + error.message, "error");
    } finally {
      setBusy(false);
    }
  }

  function handleReviewClick(event) {
    const tab = event.target.closest?.(".generation-shot");
    if (tab && !busy) {
      selectReviewShot(tab.dataset.shotId);
      return;
    }
    const candidateButton = event.target.closest?.(".review-candidate-button");
    if (candidateButton && !busy) {
      selectReviewCandidate(candidateButton.dataset.candidateId);
    }
  }

  async function retryShot(shotId) {
    if (busy || !currentDirectory || !projection) return;
    const stale = shotNeedsRegeneration(
      projection.plan?.shot_specs?.find((item) => item.id === shotId));
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
      setGenerationStatus(
        stale
          ? "已提交：用新提示词重新生成这一张。"
          : "已提交：只重跑这一张，其他图片的结果不受影响。",
        "success");
    } catch (error) {
      setGenerationStatus(error.message || "这张图没有提交成功，请重试。", "error");
    } finally {
      setBusy(false);
    }
  }

  function setDeliveryStatus(message, tone = "") {
    const status = byId("delivery-status");
    status.textContent = message || "";
    status.dataset.tone = tone;
    status.hidden = !message;
  }

  function deliveryCandidateSource(candidateId) {
    const query = new URLSearchParams({ directory: currentDirectory });
    return "/api/candidates/" + encodeURIComponent(candidateId) + "?" + query.toString();
  }

  function deliveryIssue(text, actionLabel, handler) {
    const item = document.createElement("li");
    item.className = "delivery-issue";
    const message = document.createElement("p");
    message.textContent = text;
    item.append(message);
    if (actionLabel && handler) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "text-button";
      button.textContent = actionLabel;
      button.addEventListener("click", handler);
      item.append(button);
    }
    return item;
  }

  function goToReview() {
    closeDelivery();
    const generation = byId("generation-workspace");
    if (!generation.hidden) generation.scrollIntoView({ block: "start" });
    byId("selection-panel").scrollIntoView({ block: "start" });
  }

  function goToPlan() {
    closeDelivery();
    const plan = byId("plan-workspace");
    if (!plan.hidden) plan.scrollIntoView({ block: "start" });
  }

  function openDelivery() {
    if (busy || !currentDirectory || !projection?.plan) return;
    deliveryOpen = true;
    sessionStorage.setItem(deliveryKey, currentDirectory);
    delivery.hidden = false;
    intake.hidden = true;
    document.title = (projection?.intake?.product_name || "未命名商品") + " · 交付检查";
    byId("delivery-title").focus?.();
    runExportPreflight();
  }

  function closeDelivery() {
    deliveryOpen = false;
    sessionStorage.removeItem(deliveryKey);
    delivery.hidden = true;
    intake.hidden = false;
    document.title = (projection?.intake?.product_name || "未命名商品") + " · 商品套图工作台";
  }

  function updateDeliveryGate() {
    const check = deliveryPreflight;
    const acknowledged = byId("delivery-ack").checked;
    byId("export-delivery").disabled = busy || !check || !(
      check.can_export && (!check.consistency_required || acknowledged)
    );
  }

  function renderDeliveryCheck(check) {
    deliveryPreflight = check;
    const missing = check.missing_shots || [];
    const blockers = check.blockers || [];
    const hard = check.hard_failures || [];
    const consistency = check.consistency || [];
    const notes = check.manual_notes || [];
    const checks = check.checks || [];

    const blockerList = byId("delivery-blocker-list");
    blockerList.replaceChildren();
    missing.forEach((item) => blockerList.append(deliveryIssue(
      `「${item.title}」还没有选定图片；采用一张候选后才能交付。`,
      "返回审核", goToReview,
    )));
    blockers.forEach((item) => blockerList.append(deliveryIssue(
      item.message,
      item.return_to === "review" ? "返回审核" : "返回资料",
      item.return_to === "review" ? goToReview : closeDelivery,
    )));
    byId("delivery-blockers").hidden = blockerList.childElementCount === 0;

    const hardList = byId("delivery-hard-list");
    hardList.replaceChildren();
    if (!hard.length) {
      const passedCount = checks.filter((item) => item.passed).length;
      hardList.append(deliveryIssue(
        checks.length
          ? `全部确定性硬检查通过（${passedCount}/${checks.length} 项）。`
          : "还没有可检查的已选图片。",
      ));
    } else {
      hard.forEach((item) => hardList.append(deliveryIssue(
        `「${item.shot_title || "图片"}」${item.rule_id} 未通过：${item.detail}`,
        "返回审核", goToReview,
      )));
    }

    const consistencyList = byId("delivery-consistency-list");
    consistencyList.replaceChildren();
    consistency.forEach((item) => consistencyList.append(deliveryIssue(
      item.message,
      item.return_to === "plan" ? "打开方案" : "返回审核",
      item.return_to === "plan" ? goToPlan : goToReview,
    )));
    byId("delivery-consistency").hidden = consistencyList.childElementCount === 0;
    byId("delivery-ack").checked = false;

    const selectedList = byId("delivery-selected");
    selectedList.replaceChildren();
    (check.selected || []).forEach((item) => {
      const entry = document.createElement("li");
      entry.className = "delivery-selected-item";
      const image = document.createElement("img");
      image.src = deliveryCandidateSource(item.candidate_id);
      image.alt = "已选图片：" + item.title;
      const body = document.createElement("div");
      const title = document.createElement("p");
      title.className = "delivery-selected-title";
      title.textContent = `「${item.title}」`
        + (item.width && item.height ? ` · ${item.width}×${item.height}` : "");
      const meta = document.createElement("p");
      meta.className = "delivery-selected-meta";
      meta.textContent = `命名 ${item.planned_file_name} · 当前提示词 v${item.latest_prompt_version}`
        + (item.model_id ? ` · ${item.model_id}` : "");
      body.append(title, meta);
      entry.append(image, body);
      selectedList.append(entry);
    });
    byId("delivery-selected-empty").hidden = selectedList.childElementCount > 0;

    const notesList = byId("delivery-notes-list");
    notesList.replaceChildren();
    notes.forEach((item) => notesList.append(deliveryIssue(`${item.rule_id}：${item.detail}`)));
    byId("delivery-notes").hidden = notesList.childElementCount === 0;

    const preview = check.manifest_preview || {};
    const planText = preview.plan
      ? `方案 v${preview.plan.version}（${preview.plan.shot_count} 张）`
      : "方案未就绪";
    const platformText = preview.platform
      ? `${preview.platform.profile_id} v${preview.platform.version}`
      : "平台规则未读取";
    byId("delivery-manifest").textContent =
      `追溯清单将记录：商品「${preview.product_name || "未命名"}」、平台 ${platformText}、${planText}、`
      + "每张图的提示词版本与模型、候选 SHA-256、检查结果。";
    byId("delivery-location").textContent = check.can_export
      ? "导出位置：工作空间下的 exports/ 目录；每次导出生成新版本，不覆盖旧交付包。"
      : "修正以上问题后，导出位置为工作空间下的 exports/ 目录。";
    renderExportSummary();
    updateDeliveryGate();
  }

  async function runExportPreflight() {
    if (!currentDirectory) return;
    setDeliveryStatus("正在检查交付条件…");
    byId("export-delivery").disabled = true;
    try {
      const check = await request("/api/exports/preflight", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ directory: currentDirectory }),
      });
      renderDeliveryCheck(check);
      setDeliveryStatus(
        check.ready
          ? "检查通过：全部图片已选定，硬检查通过，方案与提示词一致。"
          : check.can_export
            ? "硬检查通过；另有一致性问题，需要确认或返回处理。"
            : "还有影响交付的问题，先按下面的提示处理。",
        check.can_export ? "" : "error",
      );
    } catch (error) {
      setDeliveryStatus(error.message || "交付检查未完成，请重试。", "error");
    }
  }

  async function exportDelivery() {
    if (busy || !currentDirectory || deliveryPreflight === null) return;
    const acknowledged = byId("delivery-ack").checked;
    setBusy(true);
    updateDeliveryGate();
    setDeliveryStatus("正在导出图片组与追溯清单…");
    try {
      const data = await request("/api/exports", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          directory: currentDirectory,
          expected_etag: projection.workspace.revision,
          acknowledge_consistency: acknowledged,
        }),
      });
      renderWorkspace(data, currentDirectory);
      const warnings = data?.plan_wording_warnings || [];
      setDeliveryStatus(
        warnings.length
          ? `已导出：README 与追溯清单已记录 ${warnings.length} 处方案文本与提示词的不一致。`
          : "已导出：图片组与追溯清单都在导出目录中。",
        warnings.length ? "error" : "success",
      );
      renderExportSummary();
    } catch (error) {
      const code = error?.details?.code;
      if (["SELECTION_INCOMPLETE", "SELECTION_REQUIRED", "SELECTION_STALE",
           "CANDIDATE_NOT_FOUND", "CANDIDATE_FILE_INVALID", "PLATFORM_CHECK_FAILED",
           "EXPORT_CONSISTENCY_ACK_REQUIRED"].includes(code)) {
        await runExportPreflight();
      }
      setDeliveryStatus(error.message || "导出未完成，请重试。", "error");
    } finally {
      setBusy(false);
      updateDeliveryGate();
    }
  }

  async function revealExport() {
    if (!currentDirectory || !projection?.export) return;
    try {
      await request("/api/exports/reveal", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          directory: currentDirectory,
          export_id: projection.export.id,
        }),
      });
    } catch (error) {
      setDeliveryStatus(error.message || "打开导出文件夹失败。", "error");
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
  briefForm.addEventListener("input", handleBriefEdit);
  briefForm.addEventListener("change", handleBriefEdit);
  briefForm.addEventListener("submit", saveBrief);
  planAdjustmentForm.addEventListener("submit", savePlan);
  byId("preview-plan").addEventListener("click", previewPlan);
  byId("generate-from-plan").addEventListener("click", generateFromPlan);
  byId("export-selection").addEventListener("click", openDelivery);
  byId("delivery-back").addEventListener("click", closeDelivery);
  byId("export-delivery").addEventListener("click", exportDelivery);
  byId("delivery-ack").addEventListener("change", updateDeliveryGate);
  byId("reveal-export").addEventListener("click", revealExport);
  byId("generation-shots").addEventListener("click", handleReviewClick);
  byId("review-candidates").addEventListener("click", handleReviewClick);
  byId("review-adopt").addEventListener("click", adoptCurrentCandidate);
  byId("review-rework").addEventListener("click", () => {
    const shotId = byId("review-rework").dataset.reworkShotId;
    if (shotId && !busy) openRework(shotId);
  });
  byId("review-retry").addEventListener("click", () => {
    const shotId = byId("review-retry").dataset.retryShotId;
    if (shotId && !busy) retryShot(shotId);
  });
  byId("review-prompt").addEventListener("click", () => {
    const shotId = byId("review-prompt").dataset.promptShotId;
    if (shotId && !busy) openPrompt(shotId);
  });
  byId("reconcile-generation").addEventListener("click", reconcileGeneration);
  byId("refresh-generation").addEventListener("click", refreshGenerationState);
  planShots.addEventListener("click", handlePlanAction);
  planShots.addEventListener("input", handlePlanFieldEdit);
  planShots.addEventListener("change", handlePlanFieldEdit);
  promptForm.addEventListener("submit", savePrompt);
  byId("rework-preview-button").addEventListener("click", previewRework);
  byId("rework-confirm").addEventListener("click", confirmRework);
  reworkDialog.addEventListener("close", () => {
    reworkShotId = null;
    reworkProposal = null;
    reworkIdempotencyKey = null;
    setReworkStatus("");
  });
  promptText.addEventListener("input", handlePromptEdit);
  promptDialog.addEventListener("close", () => {
    activePromptShotId = null;
    activePromptVersion = null;
    activePromptBaseline = "";
    promptReady = false;
    promptText.value = "";
    updateGenerationControls();
  });
  imageInput.addEventListener("change", () => {
    const incoming = Array.from(imageInput.files || []);
    imageInput.value = "";
    if (!incoming.length) return;
    let overflow = false;
    incoming.forEach((file) => {
      if (refItems.length >= 3) {
        overflow = true;
        return;
      }
      const objectUrl = URL.createObjectURL(file);
      objectUrls.push(objectUrl);
      refItems.push({ kind: "new", name: file.name, file, objectUrl });
    });
    renderReferenceTiles();
    updateImageChoice();
    const error = byId("image-error");
    if (overflow) {
      error.textContent = "最多 3 张参考图。";
      error.hidden = false;
      imageInput.setAttribute("aria-invalid", "true");
    } else {
      error.textContent = "";
      error.hidden = true;
      imageInput.removeAttribute("aria-invalid");
    }
    markDirty();
  });
  form.addEventListener("input", (event) => {
    if (event.target === byId("product-name")) {
      byId("product-name").removeAttribute("aria-invalid");
      byId("product-name-error").hidden = true;
    }
    markDirty();
  });
  form.addEventListener("submit", generateSuite);

  async function boot() {
    await loadRecent();
    const directory = sessionStorage.getItem(sessionKey);
    if (!directory) return;
    try {
      const query = new URLSearchParams({ directory });
      const data = await request("/api/workspace?" + query.toString());
      renderWorkspace(data, directory);
      if (sessionStorage.getItem(deliveryKey) === directory && data.plan) {
        openDelivery();
      }
    } catch (error) {
      sessionStorage.removeItem(sessionKey);
      showHome();
      setNotice(error.message, "error");
    }
  }

  boot();
})();
