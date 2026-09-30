/**
 * 六阶段外壳（V2.UI.2）。
 *
 * 职责边界：
 *  - 只做界面投影：阶段条的 完成 / 当前 / 可用 / 锁定，面板显隐、切换与摘要。
 *  - 不持有业务状态、不读写存储、不派生领域数据；每个阶段的完成与可用判断
 *    由 workspace.js 计算后传入（computeStageStates）。
 *  - 阶段顺序与名称是产品合同的一部分（资料—理解—方案—生成—审核返工—交付）。
 */

export const STAGE_DEFINITIONS = Object.freeze([
  { id: "intake", number: 1, label: "资料" },
  { id: "understand", number: 2, label: "理解" },
  { id: "plan", number: 3, label: "方案" },
  { id: "generate", number: 4, label: "生成" },
  { id: "review", number: 5, label: "审核返工" },
  { id: "deliver", number: 6, label: "交付" },
]);

export function createStageShell({ nav, panelRoot, summary, onSelect = null }) {
  const buttons = new Map();
  const panels = new Map();
  for (const node of nav.querySelectorAll("[data-stage-nav]")) {
    buttons.set(node.dataset.stageNav, node);
  }
  for (const node of panelRoot.querySelectorAll("[data-stage-panel]")) {
    panels.set(node.dataset.stagePanel, node);
  }

  let states = {};
  let currentId = null;

  function paintSummary() {
    const state = states[currentId] || {};
    summary.textContent = state.summary || state.hint || "";
  }

  function paintButtons() {
    for (const [id, button] of buttons) {
      const state = states[id] || {};
      const locked = state.available === false;
      button.disabled = locked && id !== currentId;
      button.classList.toggle("is-current", id === currentId);
      button.classList.toggle("is-complete", state.status === "complete" && id !== currentId);
      button.classList.toggle("is-locked", locked);
      if (id === currentId) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
    }
  }

  function select(id) {
    if (!panels.has(id)) return;
    currentId = id;
    for (const [panelId, panel] of panels) panel.hidden = panelId !== id;
    paintButtons();
    paintSummary();
    revealCurrent();
    if (onSelect) onSelect(id);
  }

  /** 窄屏下阶段条可横向滚动：把当前阶段带进可视区，避免主任务被滚出屏幕。 */
  function revealCurrent() {
    const button = buttons.get(currentId);
    if (button && typeof button.scrollIntoView === "function") {
      button.scrollIntoView({ block: "nearest", inline: "nearest" });
    }
  }

  // 视口变窄（手机竖屏 / 窗口缩放）会让当前阶段滑出可视区；宽度变化时重新锚定一次。
  if (typeof window !== "undefined" && typeof window.addEventListener === "function") {
    let lastWidth = nav.clientWidth;
    window.addEventListener("resize", () => {
      if (nav.clientWidth === lastWidth) return;
      lastWidth = nav.clientWidth;
      revealCurrent();
    });
  }

  /** 传入各阶段状态；当前阶段被锁定或缺省时退回 fallback（默认第一个阶段）。 */
  function update(nextStates = {}, { fallback = null } = {}) {
    states = nextStates;
    const current = states[currentId];
    if (!currentId || !current || current.available === false) {
      const target = (fallback && panels.has(fallback)) ? fallback : STAGE_DEFINITIONS[0].id;
      if (currentId !== target) select(target);
      else { paintButtons(); paintSummary(); }
      return;
    }
    paintButtons();
    paintSummary();
  }

  for (const [id, button] of buttons) {
    button.addEventListener("click", () => { select(id); });
  }

  return {
    update,
    select,
    current: () => currentId,
  };
}
