/**
 * 三用途模型设置（模态对话框）：现有模型选择 + 仅标签页内存的 BYOK 密钥。
 * 查看或应用设置不调用供应商；密钥刷新或关闭标签页即清除。
 *
 * 密钥规则：provider id 与可选的标签页内存 key 组成单用途出站头，不落盘；
 * 能力读取是本地网关投影（/api/v2/capabilities），不外呼供应商。
 *
 * 本文件是唯一手工维护实现；浏览器只消费 Vite 构建产物。
 */

import { html, nothing, render } from "lit-html";
import type { TemplateResult } from "lit-html";
import { live } from "lit-html/directives/live.js";

/** Global purpose configuration. Only finite provider IDs persist; keys never leave tab memory except request headers. */
export type Purpose = "semantic" | "image" | "review";
export type ProviderChoice = {
  readonly id: string;
  readonly label: string;
  readonly model_id: string;
  readonly vision?: boolean;
};
export type ProviderCapability = {
  readonly provider_id?: string;
  readonly model_id?: string;
  readonly capability_version?: number;
  readonly credential_source?: string;
  readonly credential_reference?: { readonly source: string };
  readonly configured?: boolean;
  readonly capabilities?: Record<string, unknown>;
};
export type CapabilityBlock = {
  readonly contract?: string;
  readonly provider?: ProviderCapability;
  readonly [key: string]: unknown;
};
export type EffectiveCapabilities = {
  readonly ok: boolean;
  readonly provider_choices?: Record<Purpose, ProviderChoice[]>;
  readonly provider?: ProviderCapability;
  readonly images?: CapabilityBlock;
  readonly review?: CapabilityBlock;
  readonly suite_review?: CapabilityBlock;
  readonly analyze_fields?: string[];
  readonly [key: string]: unknown;
};

/** 配置变化监听器：不带参数，消费者按需重读 capabilities/refreshing。 */
export type ModelSettingsListener = () => void;

/** 模型设置公共接口：workspace/app 消费者只依赖这些成员做类型检查。 */
export type SavedExecutionView = {
  readonly provider?: { readonly provider_id?: unknown };
  readonly execution_identity?: { readonly credential_reference?: { readonly source?: unknown } };
  readonly payload?: {
    readonly fingerprint?: {
      readonly snapshot?: {
        readonly execution_target?: { readonly provider_id?: unknown; readonly credential_source?: unknown };
      };
    };
  };
};
export type ModelSettings = {
  headers(purpose: Purpose, providerId?: string, credentialSource?: string): Record<string, string>;
  allHeaders(imageProvider?: string, credentialSource?: string): Record<string, string>;
  refresh(): Promise<EffectiveCapabilities | null>;
  open(purpose?: Purpose, originalProviderId?: string): void;
  readonly capabilities: EffectiveCapabilities | null;
  readonly refreshing: boolean;
  imageEnvironment(providerId?: string, credentialSource?: string): CapabilityBlock | null;
  subscribe(listener: ModelSettingsListener): () => boolean;
  environmentFor(saved: unknown): CapabilityBlock | null;
};

const PURPOSES = ["semantic", "image", "review"] as const;

/**
 * 网关能力响应的运行时判别：只确认本地合同的最小事实（ok===true）；
 * 其余字段按可选契约读取，缺失时由调用方显式报错，不猜测。
 */
function isEffectiveCapabilities(value: unknown): value is EffectiveCapabilities {
  return typeof value === "object" && value !== null
    && "ok" in value && value.ok === true;
}

const LABELS: Record<Purpose, string> = { semantic: "商品理解", image: "图片生成", review: "AI 图片复核（按需）" };
const SUFFIXES: Record<Purpose, string> = { semantic: "Semantic", image: "Image", review: "Review" };
const PREFERENCE_KEY = "amz-listing-kit-v2:model-selection";

/**
 * 三用途模型设置（模态对话框）：现有模型选择 + 仅标签页内存的 BYOK 密钥。
 * 查看或应用设置不调用供应商；密钥刷新或关闭标签页即清除。
 */
export function createModelSettings(): ModelSettings {
  const dialogNode = document.querySelector("#model-settings-dialog");
  const formNode = document.querySelector("#model-settings-form");
  const rowsNode = document.querySelector("#model-settings-rows");
  const originalNode = document.querySelector("#model-settings-original");
  const errorNode = document.querySelector("#model-settings-error");
  const statusNode = document.querySelector("#model-settings-status");
  const triggerNode = document.querySelector("#model-settings-open");
  const applyNode = document.querySelector("#model-settings-apply");
  const cancelNode = document.querySelector("#model-settings-cancel");
  if (!(dialogNode instanceof HTMLDialogElement) || !(formNode instanceof HTMLFormElement)
      || !(rowsNode instanceof HTMLElement) || !(originalNode instanceof HTMLElement)
      || !(errorNode instanceof HTMLElement) || !(statusNode instanceof HTMLElement)
      || !(triggerNode instanceof HTMLButtonElement) || !(applyNode instanceof HTMLButtonElement)
      || !(cancelNode instanceof HTMLButtonElement)) throw new Error("模型设置界面缺失。");
  const dialog: HTMLDialogElement = dialogNode;
  const form: HTMLFormElement = formNode;
  const rows: HTMLElement = rowsNode;
  const original: HTMLElement = originalNode;
  const error: HTMLElement = errorNode;
  const status: HTMLElement = statusNode;
  const trigger: HTMLButtonElement = triggerNode;
  const apply: HTMLButtonElement = applyNode;
  const cancel: HTMLButtonElement = cancelNode;

  let selected: Partial<Record<Purpose, string>> = {};
  let choices: Record<Purpose, ProviderChoice[]> = { semantic: [], image: [], review: [] };
  const keys = new Map<string, string>();
  const imageEnvironments = new Map<string, CapabilityBlock>();
  let capabilities: EffectiveCapabilities | null = null;
  const listeners = new Set<ModelSettingsListener>();
  /** 待应用的模型选择草稿（用途 → providerId；打开时从 selected 播种，应用前不写 owner）。 */
  const draftSelected: Partial<Record<Purpose, string>> = {};
  const draftKeys = new Map<string, string>();
  /** 标记为「应用时清除」的 keyId（purpose:providerId）；只决定占位提示，清除语义仍由空串草稿承担。 */
  const clearMarked = new Set<string>();
  let originalDraft: { purpose: Purpose; providerId: string } | null = null;
  let originalKeyDraft = "";
  let returnFocus: HTMLElement | null = null;
  let generation = 0;
  let preferenceLoaded = false;
  let refreshing = false;
  /** 设置内错误/状态投影状态：草稿错误只在对话框内有效，状态行是 refresh 投影。 */
  let draftError = "";
  let statusText = "";

  /**
   * 密钥在内存里的复合键（purpose:providerId）。
   */
  function keyId(purpose: Purpose, providerId: string): string { return purpose + ":" + providerId; }

  /**
   * 单用途出站头：provider id +（可选）标签页内存 key；不落盘。
   * 只有「本次标签页内存」这一来源才附带 key：保存记录声明了别的已知来源
   * （default/env/none/…）时，即使内存里恰好留着同 provider 的 key 也不发，
   * 否则会把作用域外的凭据冒充成原任务声明的来源。
   */
  function headers(purpose: Purpose, providerId: string | undefined = selected[purpose], credentialSource?: string): Record<string, string> {
    const result: Record<string, string> = {};
    if (!providerId) return result;
    result["X-AMZ-Listing-Provider-" + SUFFIXES[purpose]] = providerId;
    if (credentialSource !== undefined && credentialSource !== "byok") return result;
    const key = keys.get(keyId(purpose, providerId));
    if (key) result["X-AMZ-Listing-Key-" + SUFFIXES[purpose]] = key;
    return result;
  }

  /**
   * 一次请求携带的三用途头合集。
   */
  function allHeaders(imageProvider?: string, credentialSource?: string): Record<string, string> {
    return { ...headers("semantic"), ...headers("image", imageProvider, credentialSource), ...headers("review") };
  }

  /**
   * 能力读取是本地网关投影，不外呼供应商。
   */
  async function readCapabilities(imageProvider?: string, credentialSource?: string): Promise<EffectiveCapabilities> {
    const response = await fetch("/api/v2/capabilities", {
      headers: { Accept: "application/json", ...allHeaders(imageProvider, credentialSource) },
    });
    const payload: unknown = await response.json();
    if (!response.ok || !isEffectiveCapabilities(payload)) {
      throw new Error("无法读取有效模型配置（HTTP " + response.status + "）。");
    }
    return payload;
  }

  /** Capability reads are local gateway projections, never supplier calls. */
  /** 代次过期或失败时返回 null，不掩盖错误。 */
  function environmentKey(providerId: string, source: string | undefined): string {
    return source === undefined ? providerId : providerId + ":" + source;
  }
  /**
   * 指定图片 provider 的有效环境；给了凭据来源就只认该来源的投影。
   * 缺该来源条目时返回 null（环境不可用），绝不回退到当前配置——否则会把当前环境的
   * 身份当成保存记录声明的身份，让错误的目标/来源看起来可用。
   */
  function imageEnvironment(providerId: string | undefined = selected.image, credentialSource?: string): CapabilityBlock | null {
    if (!providerId) return null;
    if (credentialSource) return imageEnvironments.get(environmentKey(providerId, credentialSource)) || null;
    return imageEnvironments.get(providerId) || null;
  }
  /** owner 本地订阅通知（与 generation.ts 同一习惯：快照后逐个调用，不带参数）。 */
  function notify(): void {
    for (const listener of [...listeners]) listener();
  }

  async function refresh(): Promise<EffectiveCapabilities | null> {
    const token = ++generation;
    refreshing = true;
    capabilities = null;
    imageEnvironments.clear();
    notify();
    try {
      const payload = await readCapabilities();
      if (token !== generation) return null;
      const catalog = payload.provider_choices;
      if (!catalog || PURPOSES.some((p) => !Array.isArray(catalog[p]))) {
        throw new Error("服务未提供三用途模型目录；请升级网关，不能猜测可用模型。");
      }
      choices = catalog;
      const current: Record<Purpose, ProviderCapability | undefined> = { semantic: payload.provider, image: payload.images?.provider, review: payload.review?.provider };
      if (!preferenceLoaded) {
        preferenceLoaded = true;
        const saved: Partial<Record<Purpose, string>> = {};
        try {
          const raw: unknown = JSON.parse(localStorage.getItem(PREFERENCE_KEY) || "{}");
          if (raw !== null && typeof raw === "object") {
            for (const [key, candidate] of Object.entries(raw)) {
              if (typeof candidate !== "string") continue;
              if (key === "semantic" || key === "image" || key === "review") saved[key] = candidate;
            }
          }
        } catch { /* Optional nonsecret preferences do not govern project recovery. */ }
        for (const p of PURPOSES) {
          const preferred = saved[p];
          selected[p] = choices[p].some((c) => c.id === preferred) ? preferred : current[p]?.provider_id;
        }
      }
      for (const p of PURPOSES) {
        if (!choices[p].some((c) => c.id === selected[p])) selected[p] = current[p]?.provider_id;
      }
      const effective = PURPOSES.some((p) => current[p]?.provider_id !== selected[p])
        ? await readCapabilities() : payload;
      if (token !== generation) return null;
      capabilities = effective;
      if (effective.images?.provider?.provider_id) {
        const providerId = effective.images.provider.provider_id;
        imageEnvironments.set(providerId, effective.images);
        imageEnvironments.set(environmentKey(providerId, effective.images.provider.credential_source), effective.images);
      }
      for (const choice of choices.image) {
        if (!imageEnvironments.has(choice.id)) {
          const other = await readCapabilities(choice.id);
          if (token !== generation) return null;
          if (other.images?.provider?.provider_id === choice.id && other.images.provider) {
            imageEnvironments.set(choice.id, other.images);
            imageEnvironments.set(environmentKey(choice.id, other.images.provider.credential_source), other.images);
          }
        }
        if (keys.has(keyId("image", choice.id))) {
          const defaults = await readCapabilities(choice.id, "default");
          if (token !== generation) return null;
          if (defaults.images?.provider?.provider_id === choice.id && defaults.images.provider) {
            imageEnvironments.set(environmentKey(choice.id, defaults.images.provider.credential_source), defaults.images);
          }
        }
      }
      setStatusText("配置已应用；查看、应用设置不会调用供应商。密钥刷新或关闭标签页即清除。");
      return capabilities;
    } catch {
      if (token === generation) {
        capabilities = null;
        imageEnvironments.clear();
        setStatusText("模型配置暂不可用；本地资料与项目恢复不受影响。打开设置可重新读取。");
      }
      return null;
    } finally {
      if (token === generation) { refreshing = false; notify(); }
    }
  }

  function setStatusText(next: string): void {
    statusText = next;
    renderStatus();
  }

  function setDraftError(next: string): void {
    draftError = next;
    renderError();
  }

  function effectiveBlockOf(purpose: Purpose): ProviderCapability | null {
    if (purpose === "semantic") return capabilities?.provider || null;
    if (purpose === "image") return capabilities?.images?.provider || null;
    return capabilities?.review?.provider || null;
  }
  function effectiveTextOf(purpose: Purpose, current: ProviderCapability): string {
    const providerId = current.provider_id || "未声明";
    const modelId = current.model_id || "未声明";
    const state = current.configured === false ? "未配置（请求会被拒绝，不会调用模型）" : "已配置";
    const source = current.credential_source ? " · 凭据 " + current.credential_source : "";
    const scope = " · 密钥仅当前标签页内存，请求级发送";
    return LABELS[purpose] + "有效配置：" + providerId + " · " + modelId + " · " + state + source + scope + "。";
  }
  /**
   * 密钥输入占位提示：只投影「是否已提供/是否标记清除」，不读密钥内容。
   */
  function placeholderFor(purpose: Purpose, providerId: string): string {
    const id = keyId(purpose, providerId);
    if (clearMarked.has(id)) return "应用时清除；未应用不改变当前凭据";
    return keys.has(id) ? "已在本标签页提供；留空保留" : "自己的 API key（仅本标签页）";
  }

  /**
   * 单用途设置区模板：有效配置行 + 现有模型选择 + 本标签页密钥草稿。
   * 密钥经 live(.value) 属性绑定（不进 value attribute、不进存储/日志），键入即写入 draftKeys；
   * 键入不重渲染（光标稳定），切换模型/清除标记才重渲染本区。
   */
  function purposeSection(p: Purpose): TemplateResult {
    const current = effectiveBlockOf(p);
    const draftProvider = draftSelected[p] || "";
    const line = current
      ? effectiveTextOf(p, current)
      : LABELS[p] + "：缺少有效模型或凭据；请选择现有模型并提供自己的密钥，人工操作不受影响。";
    return html`
      <fieldset>
        <legend>${LABELS[p]}</legend>
        <p class="meta" data-effective-config=${p}>${line}</p>
        <label for=${"model-provider-" + p}>现有模型</label>
        <select id=${"model-provider-" + p} @change=${(event: Event) => onDraftProviderChange(p, event)}>
          ${choices[p].map((choice) => html`
            <option value=${choice.id} ?selected=${choice.id === draftProvider}>${choice.label} · ${choice.model_id}${choice.vision ? "（实际发送图片）" : ""}</option>`)}
        </select>
        <label for=${"model-key-" + p}>自己的密钥</label>
        <input id=${"model-key-" + p} type="password" autocomplete="off" spellcheck="false" maxlength="512"
          placeholder=${placeholderFor(p, draftProvider)}
          .value=${live(draftKeys.get(keyId(p, draftProvider)) || "")}
          @input=${(event: Event) => onDraftKeyInput(p, event)}>
        <button type="button" @click=${() => onClearKey(p)}>应用时清除此模型密钥</button>
      </fieldset>`;
  }

  /** 三用途设置区同轮渲染进 #model-settings-rows（静态容器本身不动）。 */
  function renderRows(): void {
    render(html`${PURPOSES.map((p) => purposeSection(p))}`, rows);
  }

  /** 原任务凭据补给区模板：只认调用方给定的 purpose/providerId，不切换新动作模型。 */
  function renderOriginal(): void {
    render(originalDraft ? originalPanel(originalDraft) : nothing, original);
    original.hidden = !originalDraft;
  }

  function originalPanel(draft: { purpose: Purpose; providerId: string }): TemplateResult {
    const { purpose, providerId } = draft;
    const id = keyId(purpose, providerId);
    return html`
      <h3>补给原任务凭据（不切换新动作模型）</h3>
      <p>${providerId}</p>
      <label for="model-key-original">原目标的 API key</label>
      <input id="model-key-original" type="password" autocomplete="off" spellcheck="false" maxlength="512"
        placeholder=${keys.has(id) ? "已在本标签页提供；留空保留" : "自己的 API key（仅本标签页）"}
        .value=${live(originalKeyDraft)}
        @input=${onOriginalKeyInput}>`;
  }

  function onOriginalKeyInput(event: Event): void {
    if (event.target instanceof HTMLInputElement) originalKeyDraft = event.target.value;
  }

  function onDraftProviderChange(p: Purpose, event: Event): void {
    if (!(event.target instanceof HTMLSelectElement)) return;
    draftSelected[p] = event.target.value;
    renderRows();
  }

  function onDraftKeyInput(p: Purpose, event: Event): void {
    if (!(event.target instanceof HTMLInputElement)) return;
    draftKeys.set(keyId(p, draftSelected[p] || ""), event.target.value);
  }

  function onClearKey(p: Purpose): void {
    const id = keyId(p, draftSelected[p] || "");
    draftKeys.set(id, "");
    clearMarked.add(id);
    renderRows();
  }
  /**
   * 打开设置对话框；purpose/originalProviderId 用于「补给原任务凭据」区块。
   */
  function open(purpose?: Purpose, originalProviderId?: string): void {
    returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : trigger;
    draftKeys.clear();
    clearMarked.clear();
    originalKeyDraft = "";
    originalDraft = purpose !== undefined && originalProviderId !== undefined
      ? { purpose, providerId: originalProviderId } : null;
    setDraftError("");
    for (const p of PURPOSES) draftSelected[p] = selected[p];
    renderRows();
    renderOriginal();
    // 空草稿必须显示为空选（selectedIndex -1），与原来 select.value = "" 一致；
    // ?selected 全否时浏览器会默认选中首项，这里一次性同步回空白，不改草稿。
    for (const p of PURPOSES) {
      if (draftSelected[p]) continue;
      const select = rows.querySelector("#model-provider-" + p);
      if (select instanceof HTMLSelectElement) select.selectedIndex = -1;
    }
    apply.disabled = choices.semantic.length === 0 || choices.image.length === 0 || choices.review.length === 0;
    if (!dialog.open) dialog.showModal();
    if (originalDraft) {
      const input = original.querySelector("#model-key-original");
      if (input instanceof HTMLInputElement) input.focus();
    } else {
      const select = rows.querySelector("#model-provider-" + (purpose || "semantic"));
      if (select instanceof HTMLSelectElement) select.focus();
      else cancel.focus();
    }
  }

  /** 清空全部草稿密钥输入后关闭对话框（未应用的 key 不写入内存 keys；错误草稿一并清）。 */
  function close(): void {
    draftKeys.clear();
    clearMarked.clear();
    originalKeyDraft = "";
    originalDraft = null;
    setDraftError("");
    for (const p of PURPOSES) draftSelected[p] = selected[p];
    renderRows();
    renderOriginal();
    dialog.close();
    returnFocus?.focus();
  }

  /** 设置内错误/状态模板：错误显隐与文案、状态行都由状态驱动渲染；不直接写 textContent/hidden。 */
  function renderError(): void {
    render(draftError ? html`${draftError}` : nothing, error);
    error.hidden = !draftError;
  }

  function renderStatus(): void {
    render(statusText ? html`${statusText}` : nothing, status);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (apply.disabled) return;
    setDraftError("");
    for (const p of PURPOSES) {
      const value = draftSelected[p];
      if (!value || !choices[p].some((c) => c.id === value)) { setDraftError("请选择目录中的现有模型。"); return; }
    }
    const originalKey = originalKeyDraft.trim();
    if ([...draftKeys.values(), originalKey].some((v) => /[\r\n\x00-\x1f\x7f]/.test(v))) {
      setDraftError("密钥含不允许的控制字符；没有应用。"); return;
    }
    for (const p of PURPOSES) selected[p] = draftSelected[p];
    for (const [id, raw] of draftKeys) { const value = raw.trim(); if (value) keys.set(id, value); else keys.delete(id); }
    if (originalDraft && originalKey) keys.set(keyId(originalDraft.purpose, originalDraft.providerId), originalKey);
    try { localStorage.setItem(PREFERENCE_KEY, JSON.stringify(selected)); } catch { /* Nonsecret preference persistence is optional. */ }
    close();
    await refresh();
  });
  cancel.addEventListener("click", close);
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
  trigger.addEventListener("click", () => { if (capabilities) open(); else void refresh().then(() => open()); });

  return {
    headers, allHeaders, refresh, open, imageEnvironment,
    get capabilities(): EffectiveCapabilities | null { return capabilities; },
    get refreshing(): boolean { return refreshing; },
    /**
     * 按保存身份解析有效图像环境：只读保存记录声明的 provider 与凭据来源，
     * 精确命中该来源的投影；缺该来源、形状异常或缺字段都返回 null，
     * 不回退当前配置、不猜测、不用别的来源顶替。
     */
    environmentFor(saved: unknown): CapabilityBlock | null {
      if (typeof saved !== "object" || saved === null) return null;
      const view = saved as SavedExecutionView;
      const providerId = view.provider?.provider_id
        ?? view.payload?.fingerprint?.snapshot?.execution_target?.provider_id;
      const source = view.execution_identity?.credential_reference?.source
        ?? view.payload?.fingerprint?.snapshot?.execution_target?.credential_source;
      if (typeof providerId !== "string" || !providerId || typeof source !== "string" || !source) return null;
      return imageEnvironment(providerId, source);
    },
    /**
     * 订阅配置变化；返回取消订阅函数。
     */
    subscribe(listener: ModelSettingsListener): () => boolean { listeners.add(listener); return () => listeners.delete(listener); },
  };
}
