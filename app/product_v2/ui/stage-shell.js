/**
 * 六阶段外壳（V2.UI.2）。
 *
 * 职责边界：
 *  - Only project task navigation, panels and summaries; every task entry stays reachable.
 *  - Operation readiness remains in domain/workspace; opening a task never authorizes its action.
 *  - 阶段顺序与名称是产品合同的一部分（资料—理解—方案—生成—审核返工—交付）。
 */

/** 六阶段定义（顺序是产品合同）。@typedef {{id:string, number:number, label:string}} StageDefinition */

/** 单个阶段的状态投影（由 domain/workspace 派生；shell 只读）。@typedef {{status?:string, summary?:string, hint?:string, [key:string]:unknown}} StageState */

/** @typedef {(stageId:string) => void} StageSelectCallback */

export const STAGE_DEFINITIONS = /** @type {ReadonlyArray<StageDefinition>} */ (Object.freeze([
  { id: "intake", number: 1, label: "资料" },
  { id: "understand", number: 2, label: "理解" },
  { id: "plan", number: 3, label: "方案" },
  { id: "generate", number: 4, label: "生成" },
  { id: "review", number: 5, label: "审核返工" },
  { id: "deliver", number: 6, label: "交付" },
]));

/**
 * 六阶段外壳：只管项目任务导航/面板/摘要，不赋予任何操作就绪。
 * @param {{
 *   nav: HTMLElement,
 *   panelRoot: HTMLElement,
 *   summary: HTMLElement,
 *   onSelect?: StageSelectCallback|null,
 * }} args
 * @returns {{update:(nextStates:Record<string, StageState>, options?:{fallback?:string|null}) => void, select:(id:string, options?:{focusHeading?:boolean}) => void, current:() => string|null}}
 */
export function createStageShell({ nav, panelRoot, summary, onSelect = null }) {
  /** @type {Map<string, HTMLButtonElement>} */
  const buttons = new Map();
  /** @type {Map<string, HTMLElement>} */
  const panels = new Map();
  for (const node of nav.querySelectorAll("[data-stage-nav]")) {
    buttons.set(node.dataset.stageNav, node);
  }
  for (const node of panelRoot.querySelectorAll("[data-stage-panel]")) {
    panels.set(node.dataset.stagePanel, node);
  }

  /** @type {Record<string, StageState>} */
  let states = {};
  /** @type {string|null} */
  let currentId = null;

  /** @returns {void} */
  function paintSummary() {
    const state = states[currentId] || /** @type {StageState} */ ({});
    summary.textContent = state.summary || state.hint || "";
  }

  /** @returns {void} */
  function paintButtons() {
    for (const [id, button] of buttons) {
      const state = states[id] || /** @type {StageState} */ ({});
      button.disabled = false;
      button.classList.toggle("is-current", id === currentId);
      button.classList.toggle("is-complete", state.status === "complete" && id !== currentId);
      button.classList.remove("is-locked");
      if (id === currentId) button.setAttribute("aria-current", "step");
      else button.removeAttribute("aria-current");
    }
  }

  /**
   * @param {string} id
   * @param {{focusHeading?:boolean}} [options]
   * @returns {void}
   */
  function select(id, { focusHeading = false } = {}) {
    if (!panels.has(id)) return;
    currentId = id;
    for (const [panelId, panel] of panels) panel.hidden = panelId !== id;
    paintButtons();
    paintSummary();
    revealCurrent();
    if (onSelect) onSelect(id);
    if (focusHeading) {
      const panel = /** @type {HTMLElement} */ (panels.get(id));
      const heading = panel.querySelector("h3");
      if (heading && typeof heading.focus === "function") heading.focus();
    }
  }

  /** 窄屏下阶段条可横向滚动：把当前阶段带进可视区，避免主任务被滚出屏幕。 */
  /** @returns {void} */
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

  /** Keep the user's task selected during asynchronous updates, even when its action becomes blocked. */
  /**
   * @param {Record<string, StageState>} [nextStates={}]
   * @param {{fallback?:string|null}} [options]
   * @returns {void}
   */
  function update(nextStates = {}, { fallback = null } = {}) {
    states = nextStates;
    const current = states[currentId];
    if (!currentId || !current) {
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
    /** @returns {string|null} 当前选中阶段 id */
    current: () => currentId,
  };
}
