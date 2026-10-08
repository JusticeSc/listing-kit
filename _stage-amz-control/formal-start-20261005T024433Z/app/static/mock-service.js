const FACTS = [
  { id: "F1", label: "杯体为单个高直筒，比例与侧壁形态正确", owner: "machine" },
  { id: "F2", label: "上部为哑光深青绿，无渐变或图案", owner: "machine" },
  { id: "F3", label: "下部深炭灰防滑套带三条水平筋", owner: "machine" },
  { id: "F4", label: "低矮杯盖有两级同心台阶且无开口", owner: "human" },
  { id: "F5", label: "杯盖与杯体间只有一圈窄陶土橙装饰环", owner: "machine" },
  { id: "F6", label: "平底、窄防滑圈，落地不悬浮", owner: "machine" },
  { id: "F7", label: "无把手、提带、吸管、杯嘴或多余杯体", owner: "human" },
  { id: "F8", label: "外表无文字、数字、Logo、标签或水印", owner: "human" },
];

const PRODUCT_LOCK = `Photograph of the exact same product as in the reference image. The product must stay exactly the same design, the same colours, the same proportions and the same number of parts as in the reference image: exactly one single tall straight-walled insulated tumbler with its screw-on lid closed; the upper roughly 72 percent of the body is matte deep teal green (about #0F6B66) with a matte finish, no gradient and no printed pattern; the lower roughly 28 percent is a dark charcoal gray (about #252A2A) grip sleeve carrying exactly three raised horizontal ribs; the lid is a low profile dark charcoal lid whose top shows exactly two clearly visible concentric stepped rings, with no opening on the lid top; one narrow terracotta orange ring (about #D97A45) sits in the seam between the lid and the body, evenly thick all the way around; the bottom is flat with a narrow dark gray non-slip ring, and the tumbler rests flat and grounded on its surface.`;
const BLANK_SURFACE = `Every outer surface of the product stays completely blank: no text, no numbers, no letters, no words, no logo, no brand mark, no label, no sticker, no watermark, no capacity marking and no decorative symbol anywhere on the product.`;
const NEGATIVE_SHAPE = `Not tapered, not waisted, not a mug, not bottle shaped, and with no handle, no side grip, no strap, no straw, no drinking spout, no flip top, no dome lid, no second cup and no second lid.`;
const NEGATIVE_PROMPT = `different product, different colour, different proportions, extra object, second cup, handle, side handle, strap, straw, drinking spout, flip top, dome lid, open lid, text, letters, words, numbers, logo, brand mark, watermark, label, sticker, typography, pattern, gradient, glossy metallic body, cropped product, floating object, cluttered background, props overlapping the product, hands, people, blurry, low resolution`;

const SHOT_DEFINITIONS = [
  {
    id: "S1",
    title: "主图 · 纯白正面",
    purpose: "让买家第一眼识别商品完整外观",
    required: true,
    direction: "纯白背景、正面平视、商品完整居中",
    referenceView: "正面全身",
    scene: "Studio scene for an Amazon US main image: the tumbler stands alone on a seamless pure white background (RGB 255,255,255), with no props and no visible horizon line.",
    composition: "Eye level straight-on view, whole product visible with clear margins, centred and filling about eighty five percent of the square frame.",
  },
  {
    id: "S2",
    title: "场景图 · 厨房台面",
    purpose: "展示商品在克制、无人物的日常环境中的视觉感受",
    required: true,
    direction: "浅色石材台面、侧前方三分之四视角、柔和窗光",
    referenceView: "正面全身",
    scene: "Scene for an Amazon US listing lifestyle image: the tumbler stands on a clean matte light stone kitchen counter next to a smooth neutral wall; a single soft window light comes from the upper left; nothing else is in the frame, and no prop overlaps or touches the product; no hands and no people.",
    composition: "Eye level three quarter front view, whole product visible with clear margins, centred, grounded by a soft natural contact shadow, square 1:1 composition.",
  },
  {
    id: "S3",
    title: "结构图 · 杯盖细节",
    purpose: "看清杯盖台阶、橙色环和闭合状态",
    required: true,
    direction: "杯体上部特写，完整杯盖与橙色环清晰可见",
    referenceView: "杯盖近景",
    scene: "Neutral studio close-up with soft even light and no props.",
    composition: "Crop to the upper third while keeping the full lid and orange trim ring visible; sharp square detail image.",
  },
  {
    id: "S4",
    title: "结构图 · 防滑套细节",
    purpose: "看清深炭灰防滑套、三条水平筋和平底",
    required: true,
    direction: "杯体下部特写，三条水平筋与平底完整可见",
    referenceView: "底部近景",
    scene: "Neutral studio close-up with soft even light and no props.",
    composition: "Crop to the lower third while keeping all three horizontal ribs and the flat base visible; sharp square detail image.",
  },
];

const SHOT_FIXTURES = {
  S1: [{ id: "C-S1-01", url: "/media/reference/01-front-full.png", sourceKind: "mock_new_candidate", sourceLabel: "Mock 候选 · 未调用模型" }],
  S2: [
    { id: "F-01", url: "/media/candidate/F-01", sourceKind: "real_historical_candidate", sourceLabel: "历史真实候选 · 非本次生成" },
    { id: "F-02", url: "/media/candidate/F-02", sourceKind: "real_historical_candidate", sourceLabel: "历史真实候选 · 非本次生成" },
  ],
  S3: [{ id: "C-S3-01", url: "/media/reference/02-upper-closeup.png", sourceKind: "mock_new_candidate", sourceLabel: "Mock 候选 · 未调用模型" }],
  S4: [{ id: "C-S4-01", url: "/media/reference/03-lower-detail.png", sourceKind: "mock_new_candidate", sourceLabel: "Mock 候选 · 未调用模型" }],
};

const REWORK_FIXTURES = {
  S1: ["/media/reference/01-front-full.png"],
  S2: ["/media/candidate/F-03", "/media/candidate/F-04"],
  S3: ["/media/reference/02-upper-closeup.png"],
  S4: ["/media/reference/03-lower-detail.png"],
};

const clone = (value) => globalThis.structuredClone
  ? globalThis.structuredClone(value)
  : JSON.parse(JSON.stringify(value));

const wait = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function fullPrompt(shot) {
  const direction = shot.direction
    ? `Operator scene direction (compiled into this shot's scene): ${shot.direction}.`
    : "";
  return [PRODUCT_LOCK, BLANK_SURFACE, NEGATIVE_SHAPE, shot.scene, direction, shot.composition]
    .filter(Boolean)
    .join("\n\n");
}

function promptVersion(shot, number, text, origin = "system_recommended", originCandidateId = null) {
  return {
    id: `${shot.id}-P${number}`,
    number,
    text,
    negativePrompt: NEGATIVE_PROMPT,
    origin,
    originCandidateId,
    createdAt: `演示步骤 ${number}`,
  };
}

function initialFactChecks() {
  return Object.fromEntries(FACTS.map((fact) => [fact.id, {
    verdict: fact.owner === "machine" ? "pass" : "unknown",
    owner: fact.owner,
    note: fact.owner === "machine" ? "Mock 机器检查通过" : "等待你目视核对",
  }]));
}

function makeCandidate(raw, shot, attemptNumber = 1) {
  return {
    ...raw,
    attemptId: `${shot.id}-A${attemptNumber}`,
    promptVersionId: shot.promptVersions.at(-1).id,
    factChecks: initialFactChecks(),
    visualVerdict: "unreviewed",
    selected: false,
    superseded: false,
  };
}

function promptVersionText(shot, versionId) {
  const version = shot.promptVersions.find((item) => item.id === versionId);
  return version ? version.text : null;
}

function candidateIsCurrent(shot, candidateId) {
  const candidate = shot.candidates.find((item) => item.id === candidateId);
  if (!candidate) return false;
  const boundText = promptVersionText(shot, candidate.promptVersionId);
  const latest = shot.promptVersions.at(-1);
  return Boolean(boundText && latest && boundText === latest.text);
}

function selectionIsCurrent(shot) {
  return Boolean(shot.selectedCandidateId && candidateIsCurrent(shot, shot.selectedCandidateId));
}

function recomputePhase(state) {
  if (!state.plan || state.plan.status === "DRAFT") return;
  const required = state.plan.shots.filter((shot) => shot.required);
  const valid = required.filter((shot) => selectionIsCurrent(shot)).length;
  state.task.phase = required.length > 0 && valid >= required.length ? "READY_TO_EXPORT" : "REVIEW";
}

function makeShot(definition, order) {
  const base = {
    ...clone(definition),
    order,
    status: "PLANNED",
    candidates: [],
    selectedCandidateId: null,
    selectionHistory: [],
    attempts: [],
    error: null,
  };
  base.recommendedPrompt = fullPrompt(base);
  base.promptVersions = [promptVersion(base, 1, base.recommendedPrompt)];
  return base;
}

const EXAMPLE_PRODUCT = {
  sku: "demo-tumbler-aster-01",
  name: "Aster 01 保温杯",
  platform: "Amazon US",
  fixture: true,
  references: [
    { id: "front", label: "正面全身", role: "主证据", url: "/media/reference/01-front-full.png" },
    { id: "lid", label: "杯盖近景", role: "主证据", url: "/media/reference/02-upper-closeup.png" },
    { id: "base", label: "底部近景", role: "主证据", url: "/media/reference/03-lower-detail.png" },
  ],
};

const EXAMPLE_INPUTS = {
  sellingPoints: "高直筒极简外观；深青绿与深炭灰撞色；防滑套三条水平筋",
  referenceUrl: "https://example.invalid/aster-01-brief",
  confirmed: false,
};

function mockCandidatesForShot(shot, references) {
  const firstRef = (references && references[0] && references[0].url) || "/media/reference/01-front-full.png";
  return [{
    id: "C-" + shot.id + "-01",
    url: firstRef,
    sourceKind: "mock_new_candidate",
    sourceLabel: "Mock 候选 · 未调用模型",
  }];
}

function makeInitialState(scenario = "normal") {
  return {
    meta: {
      schema: "amz-workbench-mock/v1",
      mode: "offline_mock",
      scenario,
      disclaimer: "演示环境 · 不调用模型 · 不写文件",
      fixtureDisclaimer: "空白任务：先填入真实商品资料",
    },
    product: {
      sku: "",
      name: "",
      platform: "Amazon US",
      fixture: false,
      references: [],
      facts: clone(FACTS),
    },
    inputs: {
      sellingPoints: "",
      referenceUrl: "",
      confirmed: false,
    },
    task: {
      phase: "INPUT",
      busy: false,
      operation: null,
      notice: "先填写商品资料，系统再给出推荐方案。",
      error: null,
    },
    plan: null,
    currentShotId: null,
    currentCandidateId: null,
    export: null,
    sequence: 0,
  };
}

export class MockDomainError extends Error {
  constructor(code, message, field = null) {
    super(message);
    this.name = "MockDomainError";
    this.code = code;
    this.field = field;
  }
}

export function createMockService({ latency = 90, scenario = "normal" } = {}) {
  let state = makeInitialState(scenario);
  const listeners = new Set();

  const emit = () => {
    const snapshot = clone(state);
    listeners.forEach((listener) => listener(snapshot));
  };
  const announce = (message, error = null) => {
    state.task.notice = message;
    state.task.error = error;
    emit();
  };
  const requirePlan = () => {
    if (!state.plan) throw new MockDomainError("NO_PLAN", "请先生成推荐方案。");
    return state.plan;
  };
  const findShot = (shotId) => {
    const shot = requirePlan().shots.find((item) => item.id === shotId);
    if (!shot) throw new MockDomainError("SHOT_NOT_FOUND", "没有找到这张计划图。");
    return shot;
  };
  const findCandidate = (shot, candidateId) => {
    const candidate = shot.candidates.find((item) => item.id === candidateId);
    if (!candidate) throw new MockDomainError("CANDIDATE_NOT_FOUND", "没有找到这个候选。");
    return candidate;
  };
  // 用户动作按到达顺序排队执行：真人连点两下不该看到「忙」这种系统内部话。
  let queue = Promise.resolve();
  const mutate = (operation, fn) => {
    const run = async () => {
      state.task.busy = true;
      state.task.operation = operation;
      state.task.error = null;
      emit();
      await wait(latency);
      try {
        const result = await fn();
        state.task.busy = false;
        state.task.operation = null;
        emit();
        return result;
      } catch (error) {
        state.task.busy = false;
        state.task.operation = null;
        state.task.error = error.message || "动作失败";
        emit();
        throw error;
      }
    };
    const result = queue.then(run, run);
    queue = result.catch(() => {});
    return result;
  };

  return {
    kind: "mock",
    getState: () => clone(state),
    subscribe(listener) {
      listeners.add(listener);
      listener(clone(state));
      return () => listeners.delete(listener);
    },
    async reset(nextScenario = state.meta.scenario) {
      // 重置也要进同一个队列：生成过程中点「重置演示」时，在途动作不许把 phase 写回新状态。
      return mutate("正在清空任务", async () => {
        state = makeInitialState(nextScenario);
        return clone(state);
      });
    },
    async setScenario(nextScenario) {
      if (!["normal", "partial", "unknown"].includes(nextScenario)) {
        throw new MockDomainError("BAD_SCENARIO", "不认识这个演示情形。");
      }
      return this.reset(nextScenario);
    },
    async loadExample() {
      return mutate("正在填入示例资料", async () => {
        if (state.plan) throw new MockDomainError("PLAN_EXISTS", "方案已生成；示例只能填入空白新任务。");
        state.product = { sku: EXAMPLE_PRODUCT.sku, name: EXAMPLE_PRODUCT.name, platform: EXAMPLE_PRODUCT.platform, fixture: true, references: clone(EXAMPLE_PRODUCT.references), facts: clone(FACTS) };
        state.inputs = { sellingPoints: EXAMPLE_INPUTS.sellingPoints, referenceUrl: EXAMPLE_INPUTS.referenceUrl, confirmed: false };
        state.task.phase = "INPUT";
        announce("已填入虚构示例。这只是同一张表单的快捷填写，换成真实资料即可开始正式任务。", null);
      });
    },
    updateIntake(patch) {
      if (state.plan) throw new MockDomainError("PLAN_EXISTS", "方案已生成；要换商品请先清空任务。");
      if (Object.hasOwn(patch, "name")) state.product.name = String(patch.name || "").slice(0, 80);
      if (Object.hasOwn(patch, "platform")) state.product.platform = String(patch.platform || "").slice(0, 40) || "Amazon US";
      if (Object.hasOwn(patch, "references") && Array.isArray(patch.references)) {
        state.product.references = patch.references.filter((r) => r && r.url).slice(0, 6).map((r, i) => ({ id: r.id || ("ref-" + (i + 1)), label: String(r.label || ("参考图" + (i + 1))).slice(0, 24), role: "主证据", url: String(r.url).slice(0, 2000) }));
        if (!state.product.sku) state.product.sku = "user-intake-" + String(state.sequence + 1).padStart(2, "0");
      }
      if (Object.hasOwn(patch, "sellingPoints")) state.inputs.sellingPoints = String(patch.sellingPoints || "").slice(0, 500);
      if (Object.hasOwn(patch, "referenceUrl")) state.inputs.referenceUrl = String(patch.referenceUrl || "").slice(0, 500);
      if (Object.hasOwn(patch, "confirmed")) state.inputs.confirmed = Boolean(patch.confirmed);
      announce("", null);
    },
    async createRecommendedPlan(inputs) {
      return mutate("正在生成推荐方案", async () => {
        const name = String(inputs.name ?? state.product.name ?? "").trim();
        const refs = Array.isArray(inputs.references) ? inputs.references : state.product.references;
        const cleanPoints = String(inputs.sellingPoints ?? state.inputs.sellingPoints ?? "").trim();
        if (!name) throw new MockDomainError("INPUT_REQUIRED", "请填写商品名称。", "productName");
        if (!refs || !refs.length) throw new MockDomainError("INPUT_REQUIRED", "请至少添加一张商品参考图。", "references");
        if (!cleanPoints) throw new MockDomainError("INPUT_REQUIRED", "请填写至少一个商品卖点。", "sellingPoints");
        if (!inputs.confirmed && !state.inputs.confirmed) throw new MockDomainError("CONFIRM_REQUIRED", "请先确认已核对商品资料。", "confirmed");
        state.product.name = name.slice(0, 80);
        if (inputs.platform) state.product.platform = String(inputs.platform).slice(0, 40);
        if (Array.isArray(inputs.references)) state.product.references = inputs.references.filter((r) => r && r.url).slice(0, 6);
        if (!state.product.sku) state.product.sku = "user-intake-01";
        state.inputs = {
          sellingPoints: cleanPoints,
          referenceUrl: String(inputs.referenceUrl ?? state.inputs.referenceUrl ?? "").trim(),
          confirmed: true,
        };
        state.plan = {
          version: 1,
          status: "DRAFT",
          shots: SHOT_DEFINITIONS.map(makeShot),
        };
        state.currentShotId = "S1";
        state.currentCandidateId = null;
        state.task.phase = "PLAN_READY";
        announce("推荐方案已生成。你可以直接一键生成，也可以先调整。", null);
      });
    },
    async updateShot(shotId, patch) {
      return mutate("正在保存方案调整", async () => {
        const shot = findShot(shotId);
        if (state.plan.status !== "DRAFT") throw new MockDomainError("PLAN_FROZEN", "套图生成后不能改这一版方案；请保留本次结果后创建新版。");
        const nextPurpose = Object.hasOwn(patch, "purpose") ? String(patch.purpose || "").trim() : shot.purpose;
        const nextDirection = Object.hasOwn(patch, "direction") ? String(patch.direction || "").trim() : shot.direction;
        if (!nextPurpose) throw new MockDomainError("PURPOSE_REQUIRED", "用途不能为空。", "purpose");
        if (!nextDirection) throw new MockDomainError("SHOT_DIRECTION_REQUIRED", "画面方向不能为空。", "direction");
        if (Object.hasOwn(patch, "title")) shot.title = String(patch.title || "").trim() || shot.title;
        shot.purpose = nextPurpose;
        shot.direction = nextDirection;
        if (Object.hasOwn(patch, "required")) shot.required = Boolean(patch.required);
        shot.recommendedPrompt = fullPrompt(shot);
        shot.promptVersions = [promptVersion(shot, 1, shot.recommendedPrompt)];
        announce(`已保存 ${shot.id} 的方案调整。`);
      });
    },
    async addShot() {
      return mutate("正在添加计划图", async () => {
        const plan = requirePlan();
        if (plan.status !== "DRAFT") throw new MockDomainError("PLAN_FROZEN", "套图生成后不能向这一版添加图片。");
        const serial = plan.shots.length + 1;
        const shot = makeShot({
          id: `S${serial}`,
          title: "可选图 · 新镜位",
          purpose: "补充当前套图尚未覆盖的一个购买判断",
          required: false,
          direction: "中性电商棚景，请补充具体画面方向",
          referenceView: "正面全身",
          scene: "Clean neutral e-commerce studio scene with no people and no text.",
          composition: "Whole product visible with clear margins in a square 1:1 frame.",
        }, plan.shots.length);
        plan.shots.push(shot);
        state.currentShotId = shot.id;
        announce("已添加一张可选计划图。请填写它的用途。", null);
      });
    },
    async removeShot(shotId) {
      return mutate("正在移除计划图", async () => {
        const plan = requirePlan();
        const shot = findShot(shotId);
        if (plan.status !== "DRAFT") throw new MockDomainError("PLAN_FROZEN", "套图生成后不能从这一版移除图片。");
        if (shot.required) throw new MockDomainError("REQUIRED_SHOT", "必需图不能直接移除；可以先改为可选图。");
        plan.shots = plan.shots.filter((item) => item.id !== shotId);
        plan.shots.forEach((item, index) => { item.order = index; });
        state.currentShotId = plan.shots[0]?.id || null;
        announce("已移除可选计划图。", null);
      });
    },
    async moveShot(shotId, direction) {
      return mutate("正在调整顺序", async () => {
        const plan = requirePlan();
        if (plan.status !== "DRAFT") throw new MockDomainError("PLAN_FROZEN", "套图生成后不能改这一版顺序。");
        const index = plan.shots.findIndex((item) => item.id === shotId);
        const target = direction === "up" ? index - 1 : index + 1;
        if (index < 0 || target < 0 || target >= plan.shots.length) return;
        [plan.shots[index], plan.shots[target]] = [plan.shots[target], plan.shots[index]];
        plan.shots.forEach((item, order) => { item.order = order; });
        announce("套图顺序已更新。", null);
      });
    },
    focusShot(shotId) {
      const shot = findShot(shotId);
      state.currentShotId = shot.id;
      state.currentCandidateId = shot.selectedCandidateId || shot.candidates[0]?.id || null;
      emit();
    },
    focusCandidate(candidateId) {
      const shot = findShot(state.currentShotId);
      findCandidate(shot, candidateId);
      state.currentCandidateId = candidateId;
      emit();
    },
    async generateSet() {
      return mutate("正在一键生成套图", async () => {
        const plan = requirePlan();
        if (plan.status !== "DRAFT") throw new MockDomainError("ALREADY_GENERATED", "这一版方案已经生成过；请检查候选或只返工目标图片。");
        plan.status = "RUNNING";
        state.task.phase = "GENERATING";
        plan.shots.forEach((shot) => { shot.status = "QUEUED"; });
        emit();
        for (const shot of plan.shots) {
          shot.status = "RUNNING";
          emit();
          await wait(latency);
          const shouldFail = state.meta.scenario === "partial" && shot.id === "S3";
          const shouldUnknown = (state.meta.scenario === "partial" && shot.id === "S4")
            || (state.meta.scenario === "unknown" && shot.id === "S2");
          if (shouldFail) {
            shot.status = "FAILED";
            shot.error = "Mock 失败：本镜位未产生候选；其他图片已保留。";
          } else if (shouldUnknown) {
            shot.status = "UNKNOWN";
            shot.error = "Mock Unknown：不知道请求是否完成，禁止直接重提。";
          } else {
            const fixtures = state.product.fixture ? (SHOT_FIXTURES[shot.id] || [{
              id: `C-${shot.id}-01`,
              url: "/media/reference/01-front-full.png",
              sourceKind: "mock_new_candidate",
              sourceLabel: "Mock 候选 · 未调用模型",
            }]) : mockCandidatesForShot(shot, state.product.references);
            shot.attempts.push({ id: `${shot.id}-A1`, status: "SUCCEEDED", kind: "mock" });
            shot.candidates = fixtures.map((raw) => makeCandidate(raw, shot));
            shot.status = "READY";
          }
          emit();
        }
        plan.status = plan.shots.some((shot) => ["FAILED", "UNKNOWN"].includes(shot.status))
          ? "PARTIAL" : "READY";
        state.task.phase = "REVIEW";
        state.currentShotId = plan.shots.find((shot) => shot.candidates.length)?.id || plan.shots[0]?.id || null;
        state.currentCandidateId = findShot(state.currentShotId).candidates[0]?.id || null;
        announce(plan.status === "READY"
          ? "整套候选已就绪。请逐张核对并选择成品。"
          : "部分图片没有完成。已成功的候选仍然保留，请只处理问题图。", null);
      });
    },
    async savePrompt(shotId, text, origin = "user_edit") {
      return mutate("正在保存提示词新版本", async () => {
        const shot = findShot(shotId);
        const clean = String(text || "").trim();
        if (!clean) throw new MockDomainError("PROMPT_REQUIRED", "完整提示词不能为空。", "prompt");
        const lower = clean.toLowerCase();
        const missing = ["exact same product", "no text", "no handle"].filter((anchor) => !lower.includes(anchor));
        if (missing.length) throw new MockDomainError("FACT_LOCK_BROKEN", `事实锁缺失：${missing.join("、")}。请恢复这些约束再保存。`, "prompt");
        const current = shot.promptVersions.at(-1);
        if (current.text === clean) throw new MockDomainError("NO_PROMPT_CHANGE", "提示词没有变化，不需要创建新版本。", "prompt");
        const sourceCandidateId = origin === "restore_recommended"
          ? null
          : (shot.candidates.some((item) => item.id === state.currentCandidateId) ? state.currentCandidateId : null);
        const next = promptVersion(shot, current.number + 1, clean, origin, sourceCandidateId);
        shot.promptVersions.push(next);
        if (shot.selectedCandidateId) {
          shot.selectionHistory.push({ candidateId: shot.selectedCandidateId, reason: "prompt_changed" });
          const selected = shot.candidates.find((item) => item.id === shot.selectedCandidateId);
          if (selected) selected.selected = false;
          shot.selectedCandidateId = null;
        }
        shot.status = shot.candidates.length ? "STALE" : shot.status;
        state.currentShotId = shot.id;
        recomputePhase(state);
        announce("提示词新版本已保存；旧候选仍可比较，但不再代表当前版本。", null);
      });
    },
    async restoreRecommendedPrompt(shotId) {
      const shot = findShot(shotId);
      return this.savePrompt(shotId, shot.recommendedPrompt, "restore_recommended");
    },
    // 核对与选择是本地记录，不走 mutate 的模拟等待：点击立即在界面上成立，
    // 不出现「先回到未选、等一轮再选中」的回跳（2026-09-27 实测抓到的交互瑕疵）。
    reviewFact(shotId, candidateId, factId, verdict) {
      const shot = findShot(shotId);
      const candidate = findCandidate(shot, candidateId);
      const check = candidate.factChecks[factId];
      if (!check) throw new MockDomainError("FACT_NOT_FOUND", "没有找到这条商品事实。");
      if (check.owner !== "human") throw new MockDomainError("MACHINE_OWNED", "这条读数由当前检查器给出；演示中不能手改。");
      if (!["pass", "fail", "unknown"].includes(verdict)) throw new MockDomainError("BAD_VERDICT", "不认识这个核对结论。");
      check.verdict = verdict;
      check.note = verdict === "pass" ? "你已目视确认" : verdict === "fail" ? "你判定不符合商品事实" : "仍需核对";
      if (verdict === "fail") candidate.visualVerdict = "reject";
      announce(`已记录 ${factId} 的核对结论。`, null);
    },
    reviewVisual(shotId, candidateId, verdict) {
      const shot = findShot(shotId);
      const candidate = findCandidate(shot, candidateId);
      if (!["keep", "redo", "reject"].includes(verdict)) throw new MockDomainError("BAD_VISUAL_VERDICT", "请选择保留、重做或拒绝。");
      candidate.visualVerdict = verdict;
      announce(verdict === "keep" ? "已标记为可保留候选；仍需商品核对全部通过后才能选为成品。" : "已记录不满意方向。", null);
    },
    selectCandidate(shotId, candidateId) {
      const shot = findShot(shotId);
      const candidate = findCandidate(shot, candidateId);
      const unresolved = Object.entries(candidate.factChecks).filter(([, item]) => item.verdict !== "pass");
      if (unresolved.length) throw new MockDomainError("FACTS_NOT_PASS", `还有 ${unresolved.map(([id]) => id).join("、")} 未通过，不能选为成品。`);
      if (candidate.visualVerdict !== "keep") throw new MockDomainError("NOT_KEPT", "请先把这个候选判为“保留”。");
      shot.candidates.forEach((item) => { item.selected = false; });
      candidate.selected = true;
      shot.selectedCandidateId = candidate.id;
      shot.status = "SELECTED";
      state.currentCandidateId = candidate.id;
      recomputePhase(state);
      const required = state.plan.shots.filter((item) => item.required).length;
      const valid = state.plan.shots.filter((item) => item.required && selectionIsCurrent(item)).length;
      announce(selectionIsCurrent(shot)
        ? `已选定 ${shot.id}。必需图 ${valid}/${required}。`
        : `已选定 ${shot.id}，但该候选绑定旧提示词版本 ${candidate.promptVersionId}，不计入交付；请选择当前版本候选，或先恢复该版本再交付。`, null);
    },
    async reworkShot(shotId, reason, direction) {
      return mutate("正在只返工目标图片", async () => {
        const shot = findShot(shotId);
        if (shot.status === "UNKNOWN") throw new MockDomainError("RECONCILE_FIRST", "这张图的上次结果仍是 Unknown。请先核对运行状态，不能直接重提。");
        if (!reason) throw new MockDomainError("REASON_REQUIRED", "请选择返工原因。", "reworkReason");
        const cleanDirection = String(direction || "").trim();
        if (!cleanDirection) throw new MockDomainError("DIRECTION_REQUIRED", "请写清希望这一张怎样改变。", "reworkDirection");
        if (reason === "identity") throw new MockDomainError("IDENTITY_ROUTE", "商品身份错误不能靠追加场景词解决；正式产品会转到参考资产/模型路线核对。");
        if (reason === "unclassified") throw new MockDomainError("HUMAN_ROUTE", "原因尚未归类，先人工判断改哪一层，系统不会自动重试。");
        const before = state.plan.shots.map((item) => ({ id: item.id, candidates: item.candidates.length, attempts: item.attempts.length }));
        const currentPrompt = shot.promptVersions.at(-1);
        let text = currentPrompt.text;
        let executionKind = "mock_model_attempt";
        if (reason === "scene") {
          text = `${text}\n\nUSER REWORK DIRECTION: ${cleanDirection}`;
          const sourceCandidateId = shot.candidates.some((item) => item.id === state.currentCandidateId)
            ? state.currentCandidateId : null;
          shot.promptVersions.push(promptVersion(shot, currentPrompt.number + 1, text, "rework_scene", sourceCandidateId));
        } else if (reason === "technical") {
          executionKind = "mock_deterministic_transform";
        } else if (reason === "copy") {
          executionKind = "mock_composition_layer";
        }
        const attemptNumber = shot.attempts.length + 1;
        shot.attempts.push({ id: `${shot.id}-A${attemptNumber}`, status: "SUCCEEDED", kind: executionKind, reason, direction: cleanDirection });
        const urls = REWORK_FIXTURES[shot.id] || ["/media/reference/01-front-full.png"];
        const url = urls[(attemptNumber - 2) % urls.length];
        const candidate = makeCandidate({
          id: `C-${shot.id}-R${attemptNumber - 1}`,
          url,
          sourceKind: executionKind,
          sourceLabel: reason === "scene" ? "Mock 新候选 · 未调用模型" : "Mock 确定性结果 · 未写文件",
        }, shot, attemptNumber);
        shot.candidates.push(candidate);
        shot.status = "READY";
        shot.error = null;
        state.currentShotId = shot.id;
        state.currentCandidateId = candidate.id;
        recomputePhase(state);
        const after = state.plan.shots.map((item) => ({ id: item.id, candidates: item.candidates.length, attempts: item.attempts.length }));
        state.lastReworkInvariant = { targetShotId: shot.id, before, after };
        announce(`只返工了 ${shot.id}；旧候选仍在，其他计划图没有重跑。`, null);
      });
    },
    async reconcileShot(shotId) {
      return mutate("正在核对运行状态", async () => {
        const shot = findShot(shotId);
        if (shot.status !== "UNKNOWN") throw new MockDomainError("NOT_UNKNOWN", "这张图当前不是 Unknown。");
        shot.status = "FAILED";
        shot.error = "Mock 核对结果：上次运行没有可用候选，现在可以按原因只返工这张。";
        recomputePhase(state);
        announce("已核对：没有发现可用候选，状态改为失败；现在可以安全返工目标图。", null);
      });
    },
    getExportBlockers() {
      if (!state.plan) return ["尚未生成套图方案"];
      const blockers = [];
      for (const shot of state.plan.shots.filter((item) => item.required)) {
        if (!shot.selectedCandidateId) {
          blockers.push(`${shot.id} 尚未选定成品`);
        } else if (!selectionIsCurrent(shot)) {
          const candidate = shot.candidates.find((item) => item.id === shot.selectedCandidateId);
          blockers.push(`${shot.id} 的成品绑定旧提示词版本（${candidate?.promptVersionId || "—"}，当前 ${shot.promptVersions.at(-1).id}）`);
        }
        if (["FAILED", "UNKNOWN", "STALE"].includes(shot.status)) blockers.push(`${shot.id} 状态为 ${shot.status}`);
      }
      return blockers;
    },
    getDeliverySummary() {
      const required = state.plan ? state.plan.shots.filter((item) => item.required) : [];
      return {
        required: required.length,
        validSelected: required.filter((item) => selectionIsCurrent(item)).length,
        invalid: required.filter((item) => item.selectedCandidateId && !selectionIsCurrent(item)).map((shot) => {
          const candidate = shot.candidates.find((item) => item.id === shot.selectedCandidateId);
          return {
            shotId: shot.id,
            candidateId: shot.selectedCandidateId,
            boundVersionId: candidate ? candidate.promptVersionId : null,
            currentVersionId: shot.promptVersions.at(-1) ? shot.promptVersions.at(-1).id : null,
          };
        }),
      };
    },
    isCandidateCurrent(shotId, candidateId) {
      const shot = state.plan ? state.plan.shots.find((item) => item.id === shotId) : null;
      return shot ? candidateIsCurrent(shot, candidateId) : false;
    },
    async exportDelivery() {
      return mutate("正在生成导出预览", async () => {
        const blockers = this.getExportBlockers();
        if (blockers.length) throw new MockDomainError("EXPORT_BLOCKED", `暂不能导出：${blockers.join("；")}。`);
        state.export = {
          id: "MOCK-OUTPUT-01",
          createdAt: "演示步骤完成",
          mode: "preview_only",
          disclaimer: "离线演示：未写出任何文件",
          files: state.plan.shots.filter((shot) => shot.required).map((shot, index) => ({
            name: `${String(index + 1).padStart(2, "0")}-${shot.id}.png`,
            shotId: shot.id,
            candidateId: shot.selectedCandidateId,
            promptVersionId: shot.candidates.find((item) => item.id === shot.selectedCandidateId)?.promptVersionId,
          })),
        };
        state.task.phase = "EXPORTED";
        announce("导出预览已生成；这是 Mock，不写文件。", null);
      });
    },
  };
}

export const mockContract = Object.freeze({
  facts: FACTS,
  scenarios: ["normal", "partial", "unknown"],
  requiredMethods: [
    "getState", "subscribe", "reset", "setScenario", "loadExample", "updateIntake", "createRecommendedPlan", "updateShot",
    "addShot", "removeShot", "moveShot", "focusShot", "focusCandidate", "generateSet",
    "savePrompt", "restoreRecommendedPrompt", "reviewFact", "reviewVisual", "selectCandidate",
    "reworkShot", "reconcileShot", "getExportBlockers", "getDeliverySummary",
    "isCandidateCurrent", "exportDelivery",
  ],
});
