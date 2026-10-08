import { createWorkbenchService } from "./service.js";

const __params = new URLSearchParams(location.search);
const __initialScenario = ["normal","partial","unknown"].includes(__params.get("scenario")) ? __params.get("scenario") : "normal";
const service = createWorkbenchService({ mode: "mock", latency: 90, scenario: __initialScenario });
service.setScenario(__initialScenario).catch(() => {});
window.__mockService = service;
window.__setMockScenario = (v) => service.setScenario(v);
window.__resetMock = () => service.reset();
window.__loadExample = () => service.loadExample();
const root = document.documentElement;
const inputView = document.querySelector("#input-view");
const planView = document.querySelector("#plan-view");
const canvasView = document.querySelector("#canvas-view");
const inspectorView = document.querySelector("#inspector-view");
const deliveryView = document.querySelector("#delivery-view");
const exportDialog = document.querySelector("#export-dialog");
const exportDialogBody = document.querySelector("#export-dialog-body");
const liveStatus = document.querySelector("#live-status");
const liveError = document.querySelector("#live-error");

let state = service.getState();
let lastNotice = "";
let lastError = "";
let localError = null;

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#039;");

const attr = (value) => escapeHtml(value);
const checked = (condition) => condition ? " checked" : "";
const disabled = (condition) => condition ? " disabled" : "";

const labels = {
  PLANNED: "待生成",
  QUEUED: "排队中",
  RUNNING: "生成中",
  READY: "待检查",
  PARTIAL: "部分完成",
  FAILED: "失败",
  UNKNOWN: "Unknown",
  STALE: "待返工",
  SELECTED: "已选成品",
};

function shotLabel(status) { return labels[status] || status || "—"; }

function shotStateText(shot) {
  if (shot.status === "QUEUED") return "排队中";
  if (shot.status === "RUNNING") return "生成中";
  if (shot.status === "READY") return "待检查";
  if (shot.status === "STALE") return "待返工";
  return shotLabel(shot.status);
}

const REASON_IMPACT = {
  scene: ["当前图的场景、构图、光线与提示词可变段（会再调用生图模型）", "商品事实锁、其他计划图、已保留的旧候选"],
  identity: ["参考图集合、模型或编辑路线；缺少新证据时先停下核对", "不用文字覆盖事实失败；其他计划图不动"],
  technical: ["画布、编码、几何与色彩合规化；确定性处理，不重发生成", "图像语义、已选身份与追溯记录"],
  copy: ["构图层的文字与版式；确定性合成", "基础候选、提示词与商品事实"],
  unclassified: ["不自动改变，转人工判断", "全部保持不变"],
};

const REASON_LABELS = { scene: "场景/构图", identity: "商品失真", technical: "尺寸/格式", copy: "精确文案", unclassified: "未归类" };

function renderReasonImpact(reason) {
  const impact = REASON_IMPACT[reason];
  return impact ? `将改变：${impact[0]}；不会改变：${impact[1]}。` : "";
}

function shotHistory(shot) {
  if (!shot.attempts.length) return "暂无生成记录";
  return shot.attempts
    .map((attempt) => attempt.reason ? `${attempt.id}（${REASON_LABELS[attempt.reason] || attempt.reason}）` : attempt.id)
    .join(" · ");
}

function statusTone(status) {
  if (["READY", "SELECTED", "READY_TO_EXPORT", "EXPORTED"].includes(status)) return "success";
  if (["FAILED", "UNKNOWN"].includes(status)) return "danger";
  if (["RUNNING", "QUEUED", "STALE", "PARTIAL"].includes(status)) return "warning";
  return "neutral";
}

function preserveFocus(renderFn) {
  const active = document.activeElement;
  const key = active?.dataset?.focusKey || active?.id || null;
  renderFn();
  if (key) {
    const target = document.querySelector(`[data-focus-key="${CSS.escape(key)}"]`) || document.getElementById(key);
    target?.focus({ preventScroll: true });
  }
}

function fieldError(field) {
  return localError?.field === field
    ? `<p class="field-error" id="error-${attr(field)}">${escapeHtml(localError.message)}</p>`
    : "";
}

function describe(field, baseId) {
  return localError?.field === field ? `${baseId} error-${field}` : baseId;
}

function draftOr(field, fallback) {
  const draft = localError?.draft;
  return draft && Object.hasOwn(draft, field) ? draft[field] : fallback;
}

function formError(fields) {
  return localError && fields.includes(localError.field)
    ? `<p class="form-error-summary" id="form-error-summary" role="alert" tabindex="-1">${escapeHtml(localError.message)}</p>`
    : "";
}

function renderInput() {
  const locked = Boolean(state.plan);
  const refs = state.product.references || [];
  const isBlank = !state.product.name && !refs.length && !String(state.inputs.sellingPoints || "").trim();
  const missing = [];
  if (!state.product.name) missing.push("商品名称");
  if (!refs.length) missing.push("至少一张商品参考图");
  if (!String(state.inputs.sellingPoints || "").trim()) missing.push("至少一条卖点");
  if (!state.inputs.confirmed) missing.push("勾选已核对");
  const refCards = refs.map((reference, index) => {
    return '<figure class="reference-card">'
      + '<img src="' + attr(reference.url) + '" alt="' + attr(state.product.name || "商品") + " " + attr(reference.label) + '参考图" width="420" height="420"' + (index ? ' loading="lazy" fetchpriority="low"' : ' fetchpriority="high"') + ">"
      + "<figcaption>" + escapeHtml(reference.label) + " · " + escapeHtml(reference.role || "主证据") + "</figcaption>"
      + (locked ? "" : '<figcaption class="ref-actions"><button class="button button-quiet" type="button" data-action="move-reference" data-index="' + index + '" data-direction="up"' + disabled(index === 0) + ">上移</button>"
        + '<button class="button button-quiet" type="button" data-action="move-reference" data-index="' + index + '" data-direction="down"' + disabled(index === refs.length - 1) + ">下移</button>"
        + '<button class="button button-quiet" type="button" data-action="remove-reference" data-index="' + index + '">移除</button></figcaption>')
      + "</figure>";
  }).join("");
  const facts = (state.product.facts || []).map((fact) => "<li><strong>" + fact.id + "</strong> " + escapeHtml(fact.label) + "</li>").join("");
  let body = '<div class="stack">'
    + '<section aria-labelledby="product-heading"><h3 class="section-title" id="product-heading">商品与参考图</h3>'
    + '<div class="stack"><div class="field"><label for="product-name">商品名称</label>'
    + '<input id="product-name" name="productName" type="text" required maxlength="80" value="' + attr(state.product.name || "") + '" placeholder="例如 Aster 01 保温杯"' + (locked ? " readonly" : "") + ">"
    + fieldError("productName") + "</div>"
    + '<div class="field"><label for="platform">平台</label>'
    + '<input id="platform" name="platform" type="text" maxlength="40" value="' + attr(state.product.platform || "Amazon US") + '"' + (locked ? " readonly" : "") + "></div></div>"
    + '<div class="reference-grid">' + (refCards || '<p class="hint">还没有参考图：先上传真实商品图，示例只是快捷填入。</p>') + "</div>";
  if (!locked) {
    body += '<form id="ref-add-form" action="none" method="post"><div class="stack">'
      + '<div class="field"><label for="ref-file">上传参考图（本地文件，不上传服务器）</label>'
      + '<input id="ref-file" name="refFile" type="file" accept="image/*" multiple></div>'
      + '<div class="field"><label for="ref-url">按地址添加参考图</label>'
      + '<input id="ref-url" name="refUrl" type="url" placeholder="https://...">'
      + '<p class="hint">演示不会访问这个地址。</p></div>'
      + '<div class="button-row"><button class="button button-secondary" type="submit">添加参考图</button></div>'
      + "</div></form>";
  }
  body += "</section>"
    + '<form id="input-form" action="/act" method="post" novalidate><div class="stack">'
    + formError(["sellingPoints", "confirmed", "productName", "references"])
    + '<div class="field"><label for="selling-points">商品卖点</label>'
    + '<textarea id="selling-points" name="sellingPoints" required maxlength="500" aria-describedby="selling-points-hint"' + (locked ? " readonly" : "") + ">" + escapeHtml(draftOr("sellingPoints", state.inputs.sellingPoints)) + "</textarea>"
    + '<p class="hint" id="selling-points-hint">用于规划整套图片；不会替代商品事实。</p>' + fieldError("sellingPoints") + "</div>"
    + '<div class="field"><label for="reference-url">参考链接</label>'
    + '<input id="reference-url" name="referenceUrl" type="url" value="' + attr(draftOr("referenceUrl", state.inputs.referenceUrl)) + '" aria-describedby="reference-url-hint"' + (locked ? " readonly" : "") + ">"
    + '<p class="hint" id="reference-url-hint">可选；演示不会访问这个地址。</p></div>'
    + '<label class="check-row" for="confirm-input"><input id="confirm-input" name="confirmed" type="checkbox" value="yes"' + checked(draftOr("confirmed", state.inputs.confirmed ? "yes" : "") === "yes") + disabled(locked) + '><span>我已对照参考图核对资料完整，未知的容量、材质和性能不会写进图片。</span></label>'
    + fieldError("confirmed");
  if (locked) {
    body += '<div class="notice-box"><p>资料已进入方案 v' + state.plan.version + "；本轮不在生成后改输入快照。</p></div>";
  } else {
    if (missing.length) body += '<div class="notice-box"><p>还差：' + escapeHtml(missing.join("、")) + "；齐了才能生成推荐方案。</p></div>";
    if (isBlank) body += '<div class="button-row"><button class="button button-secondary" type="button" data-action="load-example">加载示例资料（虚构 Aster 01）</button></div><p class="hint">只填入同一张表单，不是另一条产品路径。</p>';
    body += '<button class="button button-primary button-wide" type="submit"' + disabled(state.task.busy) + ">生成推荐方案</button>";
  }
  body += "</div></form>"
    + '<details class="fact-summary"><summary>查看 8 条商品事实锁</summary><ul>' + facts + "</ul></details>"
    + '<p class="hint">空白任务：先填入真实商品资料；虚构示例仅用于走查，不用于真实上架。</p>'
    + "</div>";
  inputView.innerHTML = state.plan
    ? '<details class="input-summary"><summary>资料摘要：' + escapeHtml(state.product.name || "未命名商品") + " · " + refs.length + " 张参考图 · 卖点与事实已确认（方案 v" + state.plan.version + "）</summary>" + body + "</details>"
    : body;
}

function planProgress() {
  if (!state.plan) return { done: 0, total: 0, percent: 0 };
  const total = state.plan.shots.length;
  const done = state.plan.shots.filter((shot) => ["READY", "SELECTED", "FAILED", "UNKNOWN", "STALE"].includes(shot.status)).length;
  return { done, total, percent: total ? Math.round(done / total * 100) : 0 };
}

function renderPlan() {
  if (!state.plan) {
    planView.innerHTML = `<div class="empty-state"><p><strong>先确认商品资料</strong>系统会一次给出整套图片方案和默认提示词。</p></div>`;
    return;
  }
  const progress = planProgress();
  const current = state.plan.shots.find((shot) => shot.id === state.currentShotId) || state.plan.shots[0];
  const isDraft = state.plan.status === "DRAFT";
  const shots = state.plan.shots.map((shot, index) => `
    <li>
      <button class="shot-card" type="button" data-action="focus-shot" data-shot="${attr(shot.id)}" aria-current="${shot.id === state.currentShotId}" data-focus-key="shot-${attr(shot.id)}">
        <span class="shot-order">${String(index + 1).padStart(2, "0")}</span>
        <span class="shot-copy"><strong>${escapeHtml(shot.title)}</strong><span>${escapeHtml(shot.purpose)}</span><span class="shot-meta">${shot.required ? "必需图" : "可选图"} · 参考视图：${escapeHtml(shot.referenceView || "—")} · ${escapeHtml(shot.direction || "—")}</span>${shot.error ? `<span class="field-error">${escapeHtml(shot.error)}</span>` : ""}</span>
        <span class="shot-state" data-state="${attr(shot.status)}">${escapeHtml(shotStateText(shot))}</span>
      </button>
    </li>`).join("");
  const editor = isDraft && current ? `
    <details class="plan-editor"${localError && ["title", "purpose", "direction"].includes(localError.field) ? " open" : ""}>
      <summary>调整当前计划图</summary>
      <form id="plan-edit-form" action="/act" method="post">
        <input type="hidden" name="shotId" value="${attr(current.id)}">
        <div class="compact-stack">
          ${formError(["purpose", "direction"])}
          <div class="field"><label for="shot-title">图片名称</label><input id="shot-title" name="title" type="text" required maxlength="60" value="${attr(draftOr("title", current.title))}"></div>
          <div class="field"><label for="shot-purpose">购买判断 / 用途</label><textarea id="shot-purpose" name="purpose" required maxlength="240">${escapeHtml(draftOr("purpose", current.purpose))}</textarea></div>
          <div class="field"><label for="shot-direction">画面方向</label><textarea id="shot-direction" name="direction" required maxlength="240">${escapeHtml(draftOr("direction", current.direction || ""))}</textarea><p class="hint">文案与事实锁不会被这一段覆盖；保存后默认提示词按它重编译。</p>${fieldError("direction")}</div>
          <label class="check-row"><input name="required" type="checkbox" value="yes"${checked(current.required)}> <span>必需图（未选定时阻止导出）</span></label>
          <div class="button-row">
            <button class="button button-secondary" type="submit"${disabled(state.task.busy)}>保存调整</button>
            <button class="button button-quiet" type="button" data-action="move-shot" data-direction="up" data-shot="${attr(current.id)}"${disabled(current.order === 0 || state.task.busy)}>上移</button>
            <button class="button button-quiet" type="button" data-action="move-shot" data-direction="down" data-shot="${attr(current.id)}"${disabled(current.order === state.plan.shots.length - 1 || state.task.busy)}>下移</button>
            ${current.required ? "" : `<button class="button button-danger" type="button" data-action="remove-shot" data-shot="${attr(current.id)}"${disabled(state.task.busy)}>移除</button>`}
          </div>
        </div>
      </form>
    </details>` : "";
  planView.innerHTML = `
    <div class="stack">
      <div class="plan-toolbar">
        <p class="hint">共享视觉方向：柔和自然光 · 真实材质 · 无人物与道具 · F1–F8 事实锁全图生效</p>
        <div class="progress-line"><progress value="${progress.percent}" max="100">${progress.percent}%</progress><span>${progress.done}/${progress.total}</span></div>
        ${isDraft ? `<div class="button-row">
          <button class="button button-primary" type="button" data-action="generate-set"${disabled(state.task.busy)}>一键生成套图</button>
          <button class="button button-quiet" type="button" data-action="add-shot"${disabled(state.task.busy)}>添加可选图</button>
        </div><p class="hint">一键执行当前整套方案。离线演示，不调用模型。</p>` : `<p class="hint">方案 v${state.plan.version} 已固化；返工只在右侧处理目标图片。</p>`}
      </div>
      <ol class="shot-list">${shots}</ol>
      ${editor}
    </div>`;
}

function renderPrompt(shot) {
  const current = shot.promptVersions.at(-1);
  const changed = current.text !== shot.recommendedPrompt;
  const origin = current.originCandidateId ? ` · 来自 ${current.originCandidateId}` : " · 系统推荐";
  return `
    <details class="prompt-block"${localError && localError.field === "prompt" ? " open" : ""}>
      <summary>完整提示词 · ${escapeHtml(current.id)}${escapeHtml(origin)}${changed ? " · 已修改" : ""}</summary>
      <form id="prompt-form" action="/act" method="post">
        <input type="hidden" name="shotId" value="${attr(shot.id)}">
        <div class="stack">
          ${formError(["prompt"])}
          <div class="field">
            <label for="prompt-text">实际发送给模型的完整提示词</label>
            <textarea class="prompt-editor" id="prompt-text" name="prompt" required aria-describedby="${describe("prompt", "prompt-hint")}">${escapeHtml(draftOr("prompt", current.text))}</textarea>
            <p class="hint" id="prompt-hint">保存会创建新版本，并只让当前图进入需返工状态；旧候选不会删除。</p>
            ${fieldError("prompt")}
          </div>
          <div class="button-row">
            <button class="button button-secondary" type="submit"${disabled(state.task.busy)}>保存提示词新版本</button>
            ${changed ? `<button class="button button-quiet" type="button" data-action="restore-prompt" data-shot="${attr(shot.id)}"${disabled(state.task.busy)}>恢复推荐提示词</button>` : ""}
          </div>
          <details class="fact-summary"><summary>查看 negative prompt</summary><p class="hint">${escapeHtml(current.negativePrompt)}</p></details>
        </div>
      </form>
    </details>`;
}

function renderCandidateArea(shot) {
  const current = shot.candidates.find((item) => item.id === state.currentCandidateId) || shot.candidates[0];
  const currentIndex = shot.candidates.indexOf(current) + 1;
  const stage = `
    <div class="candidate-stage">
      <img class="candidate-main" src="${attr(current.url)}" width="1024" height="1024" fetchpriority="high" alt="${escapeHtml(shot.title)}，用于${escapeHtml(shot.purpose)}，候选 ${currentIndex}">
    </div>`;
  const options = shot.candidates.map((candidate) => {
    const versionCurrent = service.isCandidateCurrent(shot.id, candidate.id);
    const marks = [];
    if (candidate.selected) marks.push(versionCurrent ? "已选成品" : "已选成品 · 旧版本");
    else if (!versionCurrent) marks.push("旧版本");
    if (candidate.id === state.currentCandidateId) marks.push("当前候选");
    const caption = `${candidate.id}${marks.length ? " · " + marks.join(" · ") : ""}`;
    return `
    <div class="candidate-option">
      <input id="candidate-${attr(candidate.id)}" name="candidate" type="radio" value="${attr(candidate.id)}" data-action="focus-candidate" data-focus-key="candidate-${attr(candidate.id)}"${checked(candidate.id === state.currentCandidateId)}>
      <label for="candidate-${attr(candidate.id)}">
        <img src="${attr(candidate.url)}" alt="${escapeHtml(shot.title)}候选 ${escapeHtml(candidate.id)} 缩略图" width="520" height="520" loading="lazy" fetchpriority="low">
        <span>${escapeHtml(caption)}</span>
      </label>
    </div>`;
  }).join("");
  return `${stage}
    <fieldset class="candidate-picker">
      <legend>候选图片</legend>
      <div class="candidate-options">${options}</div>
    </fieldset>`;
}

function renderFactReview(shot, candidate) {
  const rows = state.product.facts.map((fact) => {
    const check = candidate.factChecks[fact.id];
    if (check.owner === "machine") {
      return `<div class="fact-row"><span class="fact-id">${fact.id}</span><span class="fact-text">${escapeHtml(fact.label)}<span class="fact-owner">Mock 检查器</span></span><span class="fact-result ${attr(check.verdict)}">${check.verdict === "pass" ? "通过" : escapeHtml(check.verdict)}</span></div>`;
    }
    return `<div class="fact-row"><span class="fact-id">${fact.id}</span><span class="fact-text">${escapeHtml(fact.label)}<span class="fact-owner">需要你目视确认</span></span>
      <span class="mini-options" role="group" aria-label="${fact.id} 核对结论">
        <label><input type="radio" name="fact-${attr(fact.id)}" value="pass" data-action="review-fact" data-shot="${attr(shot.id)}" data-candidate="${attr(candidate.id)}" data-fact="${attr(fact.id)}" data-focus-key="fact-${attr(fact.id)}-pass"${checked(check.verdict === "pass")}>通过</label>
        <label><input type="radio" name="fact-${attr(fact.id)}" value="fail" data-action="review-fact" data-shot="${attr(shot.id)}" data-candidate="${attr(candidate.id)}" data-fact="${attr(fact.id)}" data-focus-key="fact-${attr(fact.id)}-fail"${checked(check.verdict === "fail")}>不通过</label>
        <label><input type="radio" name="fact-${attr(fact.id)}" value="unknown" data-action="review-fact" data-shot="${attr(shot.id)}" data-candidate="${attr(candidate.id)}" data-fact="${attr(fact.id)}" data-focus-key="fact-${attr(fact.id)}-unknown"${checked(check.verdict === "unknown")}>未确认</label>
      </span></div>`;
  }).join("");
  const unresolved = Object.entries(candidate.factChecks).filter(([, check]) => check.verdict !== "pass").map(([id]) => id);
  const selectable = unresolved.length === 0 && candidate.visualVerdict === "keep";
  return `
    <section class="review-block" aria-labelledby="fact-review-heading">
      <h3 class="section-title" id="fact-review-heading">商品事实核对 <span>F1–F8</span></h3>
      <div class="fact-review">${rows}</div>
      <fieldset class="field">
        <legend class="field-label">整体视觉判断</legend>
        <div class="choice-grid">
          <label><input type="radio" name="visual-verdict" value="keep" data-action="review-visual" data-shot="${attr(shot.id)}" data-candidate="${attr(candidate.id)}" data-focus-key="visual-keep"${checked(candidate.visualVerdict === "keep")}>保留</label>
          <label><input type="radio" name="visual-verdict" value="redo" data-action="review-visual" data-shot="${attr(shot.id)}" data-candidate="${attr(candidate.id)}" data-focus-key="visual-redo"${checked(candidate.visualVerdict === "redo")}>重做</label>
          <label><input type="radio" name="visual-verdict" value="reject" data-action="review-visual" data-shot="${attr(shot.id)}" data-candidate="${attr(candidate.id)}" data-focus-key="visual-reject"${checked(candidate.visualVerdict === "reject")}>拒绝</label>
        </div>
      </fieldset>
      <div class="selection-gate">
        <p>${selectable ? "事实与视觉判断都已通过，可以选为成品。" : `还需：${unresolved.length ? `${unresolved.join("、")} 通过` : "视觉判断为保留"}。`}</p>
        <button class="button ${candidate.selected ? "button-quiet" : "button-primary"}" type="button" data-action="select-candidate" data-shot="${attr(shot.id)}" data-candidate="${attr(candidate.id)}"${disabled(!selectable || state.task.busy || candidate.selected)}>${candidate.selected ? "已选成品" : "选为成品"}</button>
      </div>
    </section>`;
}

function renderRework(shot) {
  if (shot.status === "UNKNOWN") {
    return `<section class="rework-block"><div class="error-box"><p>${escapeHtml(shot.error || "运行结果未知")}</p></div><button class="button button-secondary" type="button" data-action="reconcile-shot" data-shot="${attr(shot.id)}"${disabled(state.task.busy)}>核对运行状态</button></section>`;
  }
  return `
    <section class="rework-block" aria-labelledby="rework-heading">
      <h3 class="section-title" id="rework-heading">只返工这张 <span>旧候选保留</span></h3>
      <p class="hint">历史：${escapeHtml(shotHistory(shot))}</p>
      <form id="rework-form" action="/act" method="post">
        <input type="hidden" name="shotId" value="${attr(shot.id)}">
        ${formError(["reworkReason", "reworkDirection"])}
        <fieldset class="field">
          <legend class="field-label">不满意原因</legend>
          <div class="choice-grid reasons">
            <label><input type="radio" name="reason" value="scene" required${checked(draftOr("reworkReason", "") === "scene")}>场景 / 构图</label>
            <label><input type="radio" name="reason" value="identity" required${checked(draftOr("reworkReason", "") === "identity")}>商品失真</label>
            <label><input type="radio" name="reason" value="technical" required${checked(draftOr("reworkReason", "") === "technical")}>尺寸 / 白底</label>
            <label><input type="radio" name="reason" value="copy" required${checked(draftOr("reworkReason", "") === "copy")}>精确文案</label>
            <label><input type="radio" name="reason" value="unclassified" required${checked(draftOr("reworkReason", "") === "unclassified")}>还不能归类</label>
          </div>
          <p class="hint" id="rework-impact" aria-live="polite"></p>
          ${fieldError("reworkReason")}
        </fieldset>
        <div class="field">
          <label for="rework-direction">希望怎样改变</label>
          <textarea id="rework-direction" name="reworkDirection" required maxlength="500" aria-describedby="${describe("reworkDirection", "rework-hint")}">${escapeHtml(draftOr("reworkDirection", ""))}</textarea>
          <p class="hint" id="rework-hint">原因会决定改提示词、转确定性处理，还是先停下核对。</p>
          ${fieldError("reworkDirection")}
        </div>
        <button class="button button-secondary" type="submit"${disabled(state.task.busy)}>重做这张</button>
        <p class="hint">离线演示：不调用模型，不写文件；这里只模拟状态变化，不产生真实新候选。</p>
      </form>
    </section>`;
}

function renderCanvas() {
  if (!state.plan || !state.currentShotId) {
    canvasView.innerHTML = `<div class="empty-state"><p><strong>先补齐资料</strong>确认商品资料后，候选大图出现在这里。</p></div>`;
    return;
  }
  const shot = state.plan.shots.find((item) => item.id === state.currentShotId);
  if (!shot) {
    canvasView.innerHTML = `<div class="empty-state"><p><strong>先补齐资料</strong>确认商品资料后，候选大图出现在这里。</p></div>`;
    return;
  }
  let body;
  if (shot.candidates.length) {
    body = renderCandidateArea(shot);
  } else if (shot.status === "FAILED") {
    body = `<div class="empty-state"><p><strong>这张图生成失败</strong>${escapeHtml(shot.error || "在右侧选择原因后，只返工这一张。")}</p></div>`;
  } else if (shot.status === "UNKNOWN") {
    body = `<div class="empty-state"><p><strong>结果处于 Unknown</strong>先核对运行状态，不能直接重提。</p></div>`;
  } else {
    body = `<div class="empty-state"><p><strong>还没有候选</strong>点「一键生成套图」后，这张图的候选会出现在这里。</p></div>`;
  }
  canvasView.innerHTML = `
    <div class="stack">
      <div class="canvas-head">
        <div><h3>${escapeHtml(shot.title)}</h3><p>${escapeHtml(shot.purpose)}</p></div>
        <span class="status-pill" data-tone="${statusTone(shot.status)}">${escapeHtml(shotLabel(shot.status))}</span>
      </div>
      ${body}
    </div>`;
}

function renderInspector() {
  if (!state.plan || !state.currentShotId) {
    inspectorView.innerHTML = `<div class="empty-state"><p><strong>先补齐资料</strong>有候选之后，这里显示画面要求、完整提示词和返工入口。</p></div>`;
    return;
  }
  const shot = state.plan.shots.find((item) => item.id === state.currentShotId);
  if (!shot) {
    inspectorView.innerHTML = `<div class="empty-state"><p><strong>先补齐资料</strong>有候选之后，这里显示画面要求、完整提示词和返工入口。</p></div>`;
    return;
  }
  const candidate = shot.candidates.find((item) => item.id === state.currentCandidateId) || shot.candidates[0] || null;
  const taskError = state.task.error ? `<div class="error-box"><p>${escapeHtml(state.task.error)}</p></div>` : "";
  inspectorView.innerHTML = `
    <div class="stack">
      ${taskError}
      ${renderRequirements(shot)}
      ${renderPrompt(shot)}
      ${candidate ? renderFactReview(shot, candidate) : ""}
      ${state.plan.status === "DRAFT" ? "" : renderRework(shot)}
    </div>`;
}

function renderRequirements(shot) {
  return `
    <details class="requirements-block">
      <summary>画面要求</summary>
      <ul class="requirement-list">
        <li>${escapeHtml(shot.direction || "中性电商场景")}</li>
        <li>参考视图：${escapeHtml(shot.referenceView || "正面全身")}</li>
        <li>柔和自然光、真实材质；无人物、无遮挡商品的道具</li>
        <li>商品外观严格保持参考图；F1–F8 事实锁全图生效</li>
      </ul>
    </details>`;
}

function renderDelivery() {
  const summary = service.getDeliverySummary();
  const blockers = service.getExportBlockers();
  deliveryView.innerHTML = `
    <div class="delivery-summary">
      <strong>必需图 ${summary.validSelected}/${summary.required || "—"}</strong>
      <span>${blockers.length ? escapeHtml(blockers.slice(0, 2).join("；")) : "所有必需图已选，可生成导出预览"}</span>
    </div>
    <button class="button ${blockers.length ? "button-quiet" : "button-primary"}" type="button" data-action="export"${disabled(blockers.length > 0 || state.task.busy)}>导出套图</button>`;
}

function renderExport() {
  if (!state.export) return;
  exportDialogBody.innerHTML = `
    <div class="notice-box"><p><strong>${escapeHtml(state.export.disclaimer)}</strong>。该清单用于验证交付结构，不是文件下载。</p></div>
    <ol class="manifest-list">${state.export.files.map((file) => `<li><span><strong>${escapeHtml(file.name)}</strong><br><code>${escapeHtml(file.shotId)} · ${escapeHtml(file.candidateId)}</code></span><code>${escapeHtml(file.promptVersionId)}</code></li>`).join("")}</ol>
    <details class="fact-summary"><summary>追溯内容</summary><p class="hint">每张文件绑定 Shot、人工选定候选和生成时使用的 PromptVersion；正式阶段还会加入请求与检查证据。</p></details>`;
}

function updateHeadings() {
  const stageChip = document.querySelector("#stage-chip");
  const stageLabels = {
    INPUT: "阶段：待确认资料",
    PLAN_READY: "阶段：方案可调整",
    GENERATING: "阶段：整套生成中",
    REVIEW: "阶段：逐图审核",
    READY_TO_EXPORT: "阶段：可导出",
    EXPORTED: "阶段：导出完成（Mock）",
  };
  const __title = document.querySelector("#page-title");
  if (__title) __title.textContent = state.product.name ? (state.product.name + " · 商品套图") : "商品套图";
  if (stageChip) stageChip.textContent = stageLabels[state.task.phase] || "阶段：—";
  const inputStatus = document.querySelector("#input-status");
  const planStatus = document.querySelector("#plan-status");
  const __isBlank = !state.product.name && !(state.product.references && state.product.references.length);
  inputStatus.textContent = state.plan ? (state.inputs.confirmed ? "已确认" : "待确认") : (__isBlank ? "待填写" : "待确认");
  inputStatus.dataset.tone = state.inputs.confirmed ? "success" : "neutral";
  planStatus.textContent = state.plan ? `v${state.plan.version} · ${shotLabel(state.plan.status)}` : "未生成";
  planStatus.dataset.tone = statusTone(state.plan?.status);
  root.classList.toggle("is-busy", state.task.busy);
}

function render() {
  preserveFocus(() => {
    renderInput();
    renderPlan();
    renderCanvas();
    renderInspector();
    renderDelivery();
    renderExport();
    updateHeadings();
  });
  if (state.task.notice && state.task.notice !== lastNotice) {
    liveStatus.textContent = state.task.notice;
    lastNotice = state.task.notice;
  }
  if (state.task.error && state.task.error !== lastError) {
    liveError.textContent = state.task.error;
    lastError = state.task.error;
  }
}

async function runAction(action, options = {}) {
  localError = null;
  try {
    await action();
    liveError.textContent = "";
  } catch (error) {
    localError = { field: error.field || null, message: error.message || "动作失败", draft: options.draft || null };
    liveError.textContent = localError.message;
    render();
    const summary = document.querySelector("#form-error-summary");
    const fieldTarget = error.field ? document.querySelector(`[name="${CSS.escape(error.field)}"]`) : null;
    (summary || fieldTarget)?.focus();
  }
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && event.isComposing) event.preventDefault();
}, true);

document.addEventListener("submit", (event) => {
  event.preventDefault();
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) return;
  const data = new FormData(form);
  if (form.id === "intake-meta-form") { event.stopPropagation(); return; }
  if (form.id === "ref-add-form") {
    const url = String(data.get("refUrl") || "").trim();
    if (!url) { liveError.textContent = "请先选择文件或填写图片地址。"; return; }
    const next = (state.product.references || []).concat([{ id: "ref-" + ((state.product.references || []).length + 1), label: "参考图" + ((state.product.references || []).length + 1), url }]);
    try { service.updateIntake({ references: next }); } catch (error) { liveError.textContent = error.message || "动作失败"; }
    return;
  }
  if (form.id === "input-form") {
    const draft = {
      sellingPoints: String(data.get("sellingPoints") || ""),
      referenceUrl: String(data.get("referenceUrl") || ""),
      confirmed: data.get("confirmed") === "yes" ? "yes" : "",
    };
    const nameInput = document.querySelector("#product-name");
    const platformInput = document.querySelector("#platform");
    try {
      service.updateIntake({ name: nameInput ? nameInput.value : state.product.name, platform: platformInput ? platformInput.value : state.product.platform, sellingPoints: draft.sellingPoints, referenceUrl: draft.referenceUrl, confirmed: draft.confirmed === "yes" });
    } catch (error) { liveError.textContent = error.message || "动作失败"; return; }
    runAction(() => service.createRecommendedPlan({
      name: nameInput ? nameInput.value : state.product.name,
      platform: platformInput ? platformInput.value : state.product.platform,
      references: state.product.references,
      sellingPoints: draft.sellingPoints,
      referenceUrl: draft.referenceUrl,
      confirmed: draft.confirmed === "yes",
    }), { draft });
  } else if (form.id === "plan-edit-form") {
    const draft = {
      title: String(data.get("title") || ""),
      purpose: String(data.get("purpose") || ""),
      direction: String(data.get("direction") || ""),
    };
    runAction(async () => {
      await service.updateShot(data.get("shotId"), {
        title: draft.title,
        purpose: draft.purpose,
        direction: draft.direction,
        required: data.get("required") === "yes",
      });
      const summary = document.querySelector("details.plan-editor > summary");
      if (summary) summary.focus();
    }, { draft });
  } else if (form.id === "prompt-form") {
    const draft = { prompt: String(data.get("prompt") || "") };
    runAction(() => service.savePrompt(data.get("shotId"), draft.prompt), { draft });
  } else if (form.id === "rework-form") {
    const draft = {
      reworkReason: String(data.get("reason") || ""),
      reworkDirection: String(data.get("reworkDirection") || ""),
    };
    runAction(() => service.reworkShot(data.get("shotId"), draft.reworkReason, draft.reworkDirection), { draft });
  }
});

document.addEventListener("change", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) return;
  if (target.id === "product-name" || target.id === "platform" || target.id === "selling-points" || target.id === "reference-url") {
    try {
      const patch = {};
      if (target.id === "product-name") patch.name = target.value;
      if (target.id === "platform") patch.platform = target.value;
      if (target.id === "selling-points") patch.sellingPoints = target.value;
      if (target.id === "reference-url") patch.referenceUrl = target.value;
      service.updateIntake(patch);
    } catch (error) { liveError.textContent = error.message || "动作失败"; }
    return;
  }
  if (target.id === "confirm-input") {
    try { service.updateIntake({ confirmed: target.checked }); } catch (error) { liveError.textContent = error.message || "动作失败"; }
    return;
  }
  if (target.id === "ref-file" && target.files && target.files.length) {
    const files = Array.from(target.files).slice(0, 6 - (state.product.references || []).length);
    const next = (state.product.references || []).slice();
    files.forEach((f) => { next.push({ id: "ref-" + (next.length + 1), label: "参考图" + (next.length + 1), url: URL.createObjectURL(f) }); });
    try { service.updateIntake({ references: next }); } catch (error) { liveError.textContent = error.message || "动作失败"; }
    target.value = "";
    return;
  }
  if (target.dataset.action === "focus-candidate") {   service.focusCandidate(target.value);
  } else if (target.dataset.action === "review-fact") {
    runAction(() => service.reviewFact(target.dataset.shot, target.dataset.candidate, target.dataset.fact, target.value));
  } else if (target.name === "reason" && target.closest("#rework-form")) {
    const impact = document.querySelector("#rework-impact");
    if (impact) impact.textContent = renderReasonImpact(target.value);
  } else if (target.dataset.action === "review-visual") {
    runAction(() => service.reviewVisual(target.dataset.shot, target.dataset.candidate, target.value));
  }
});

document.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-action]");
  if (!button || button.disabled) return;
  const { action, shot, candidate, direction } = button.dataset;
  if (action === "focus-shot") service.focusShot(shot);
  else if (action === "focus-candidate") service.focusCandidate(candidate);
  else if (action === "generate-set") runAction(() => service.generateSet());
  else if (action === "add-shot") runAction(() => service.addShot());
  else if (action === "remove-shot") runAction(() => service.removeShot(shot));
  else if (action === "move-shot") runAction(() => service.moveShot(shot, direction));
  else if (action === "restore-prompt") runAction(() => service.restoreRecommendedPrompt(shot));
  else if (action === "select-candidate") runAction(() => service.selectCandidate(shot, candidate));
  else if (action === "reconcile-shot") runAction(() => service.reconcileShot(shot));
  else if (action === "export") runAction(async () => {
    await service.exportDelivery();
    if (!exportDialog.open) exportDialog.showModal();
  });
  else if (action === "close-export") exportDialog.close();
  else if (action === "load-example") runAction(() => service.loadExample());
  else if (action === "remove-reference") {
    const idx = Number(button.dataset.index);
    const next = (state.product.references || []).filter((_, i) => i !== idx);
    try { service.updateIntake({ references: next }); } catch (error) { liveError.textContent = error.message || "动作失败"; }
  }
  else if (action === "move-reference") {
    const idx = Number(button.dataset.index);
    const dir = button.dataset.direction;
    const next = (state.product.references || []).slice();
    const t = dir === "up" ? idx - 1 : idx + 1;
    if (idx >= 0 && t >= 0 && t < next.length) { const tmp = next[idx]; next[idx] = next[t]; next[t] = tmp; }
    try { service.updateIntake({ references: next }); } catch (error) { liveError.textContent = error.message || "动作失败"; }
  }
});

{ const __rb = document.querySelector("#reset-workbench"); if (__rb) __rb.remove(); }
exportDialog.addEventListener("click", (event) => {
  if (event.target === exportDialog) exportDialog.close();
});

service.subscribe((snapshot) => {
  state = snapshot;
  render();
});
