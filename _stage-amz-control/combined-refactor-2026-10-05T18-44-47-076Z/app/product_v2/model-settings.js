// Generated from app/product_v2/model-settings.ts; edit the TS source and run `npm run build:frontend`.
/**
 * 三用途模型设置（模态对话框）：现有模型选择 + 仅标签页内存的 BYOK 密钥。
 * 查看或应用设置不调用供应商；密钥刷新或关闭标签页即清除。
 *
 * 密钥规则：provider id 与可选的标签页内存 key 组成单用途出站头，不落盘；
 * 能力读取是本地网关投影（/api/v2/capabilities），不外呼供应商。
 *
 * TypeScript 迁移（计划 §9 V2.R7.5）：本文件是唯一手工维护实现；同名
 * `model-settings.js` 由 `npm run build:frontend` 从本文件生成，
 * 浏览器只消费生成的 `.js`。
 */
const PURPOSES = ["semantic", "image", "review"];
/**
 * 网关能力响应的运行时判别：只确认本地合同的最小事实（ok===true）；
 * 其余字段按可选契约读取，缺失时由调用方显式报错，不猜测。
 */
function isEffectiveCapabilities(value) {
    return typeof value === "object" && value !== null
        && "ok" in value && value.ok === true;
}
const LABELS = { semantic: "商品理解", image: "图片生成", review: "AI 图片复核（按需）" };
const SUFFIXES = { semantic: "Semantic", image: "Image", review: "Review" };
const PREFERENCE_KEY = "amz-listing-kit-v2:model-selection";
/**
 * 三用途模型设置（模态对话框）：现有模型选择 + 仅标签页内存的 BYOK 密钥。
 * 查看或应用设置不调用供应商；密钥刷新或关闭标签页即清除。
 */
export function createModelSettings() {
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
        || !(cancelNode instanceof HTMLButtonElement))
        throw new Error("模型设置界面缺失。");
    const dialog = dialogNode;
    const form = formNode;
    const rows = rowsNode;
    const original = originalNode;
    const error = errorNode;
    const status = statusNode;
    const trigger = triggerNode;
    const apply = applyNode;
    const cancel = cancelNode;
    let selected = {};
    let choices = { semantic: [], image: [], review: [] };
    const keys = new Map();
    const imageEnvironments = new Map();
    let capabilities = null;
    const listeners = new Set();
    const selectors = new Map();
    const draftKeys = new Map();
    let originalDraft = null;
    let returnFocus = null;
    let generation = 0;
    let preferenceLoaded = false;
    let refreshing = false;
    /**
     * 密钥在内存里的复合键（purpose:providerId）。
     */
    function keyId(purpose, providerId) { return purpose + ":" + providerId; }
    /**
     * 单用途出站头：provider id +（可选）标签页内存 key；不落盘。
     */
    function headers(purpose, providerId = selected[purpose], credentialSource) {
        const result = {};
        if (!providerId)
            return result;
        result["X-AMZ-Listing-Provider-" + SUFFIXES[purpose]] = providerId;
        const key = keys.get(keyId(purpose, providerId));
        if (key && credentialSource !== "default")
            result["X-AMZ-Listing-Key-" + SUFFIXES[purpose]] = key;
        return result;
    }
    /**
     * 一次请求携带的三用途头合集。
     */
    function allHeaders(imageProvider, credentialSource) {
        return { ...headers("semantic"), ...headers("image", imageProvider, credentialSource), ...headers("review") };
    }
    /**
     * 能力读取是本地网关投影，不外呼供应商。
     */
    async function readCapabilities(imageProvider, credentialSource) {
        const response = await fetch("/api/v2/capabilities", {
            headers: { Accept: "application/json", ...allHeaders(imageProvider, credentialSource) },
        });
        const payload = await response.json();
        if (!response.ok || !isEffectiveCapabilities(payload)) {
            throw new Error("无法读取有效模型配置（HTTP " + response.status + "）。");
        }
        return payload;
    }
    /** Capability reads are local gateway projections, never supplier calls. */
    /** 代次过期或失败时返回 null，不掩盖错误。 */
    function environmentKey(providerId, source) {
        return source === undefined ? providerId : providerId + ":" + source;
    }
    async function refresh() {
        const token = ++generation;
        refreshing = true;
        capabilities = null;
        imageEnvironments.clear();
        for (const listener of listeners)
            listener();
        try {
            const payload = await readCapabilities();
            if (token !== generation)
                return null;
            const catalog = payload.provider_choices;
            if (!catalog || PURPOSES.some((p) => !Array.isArray(catalog[p]))) {
                throw new Error("服务未提供三用途模型目录；请升级网关，不能猜测可用模型。");
            }
            choices = catalog;
            const current = { semantic: payload.provider, image: payload.images?.provider, review: payload.review?.provider };
            if (!preferenceLoaded) {
                preferenceLoaded = true;
                const saved = {};
                try {
                    const raw = JSON.parse(localStorage.getItem(PREFERENCE_KEY) || "{}");
                    if (raw !== null && typeof raw === "object") {
                        for (const [key, candidate] of Object.entries(raw)) {
                            if (typeof candidate !== "string")
                                continue;
                            if (key === "semantic" || key === "image" || key === "review")
                                saved[key] = candidate;
                        }
                    }
                }
                catch { /* Optional nonsecret preferences do not govern project recovery. */ }
                for (const p of PURPOSES) {
                    const preferred = saved[p];
                    selected[p] = choices[p].some((c) => c.id === preferred) ? preferred : current[p]?.provider_id;
                }
            }
            for (const p of PURPOSES) {
                if (!choices[p].some((c) => c.id === selected[p]))
                    selected[p] = current[p]?.provider_id;
            }
            const effective = PURPOSES.some((p) => current[p]?.provider_id !== selected[p])
                ? await readCapabilities() : payload;
            if (token !== generation)
                return null;
            capabilities = effective;
            if (effective.images?.provider?.provider_id) {
                const providerId = effective.images.provider.provider_id;
                imageEnvironments.set(providerId, effective.images);
                imageEnvironments.set(environmentKey(providerId, effective.images.provider.credential_source), effective.images);
            }
            for (const choice of choices.image) {
                if (!imageEnvironments.has(choice.id)) {
                    const other = await readCapabilities(choice.id);
                    if (token !== generation)
                        return null;
                    if (other.images?.provider?.provider_id === choice.id && other.images.provider) {
                        imageEnvironments.set(choice.id, other.images);
                        imageEnvironments.set(environmentKey(choice.id, other.images.provider.credential_source), other.images);
                    }
                }
                if (keys.has(keyId("image", choice.id))) {
                    const defaults = await readCapabilities(choice.id, "default");
                    if (token !== generation)
                        return null;
                    if (defaults.images?.provider?.provider_id === choice.id && defaults.images.provider) {
                        imageEnvironments.set(environmentKey(choice.id, defaults.images.provider.credential_source), defaults.images);
                    }
                }
            }
            status.textContent = "配置已应用；查看、应用设置不会调用供应商。密钥刷新或关闭标签页即清除。";
            return capabilities;
        }
        catch {
            if (token === generation) {
                capabilities = null;
                imageEnvironments.clear();
                status.textContent = "模型配置暂不可用；本地资料与项目恢复不受影响。打开设置可重新读取。";
            }
            return null;
        }
        finally {
            if (token === generation) {
                refreshing = false;
                for (const listener of listeners)
                    listener();
            }
        }
    }
    function showKeyState(purpose, providerId, input) {
        input.value = draftKeys.get(keyId(purpose, providerId)) || "";
        input.placeholder = keys.has(keyId(purpose, providerId)) ? "已在本标签页提供；留空保留" : "自己的 API key（仅本标签页）";
    }
    /**
     * 创建密码输入框（密钥只在标签页内存）。
     */
    function keyField(purpose, providerId) {
        const input = document.createElement("input");
        input.type = "password";
        input.autocomplete = "off";
        input.spellcheck = false;
        input.maxLength = 512;
        input.id = "model-key-" + purpose;
        showKeyState(purpose, providerId, input);
        return input;
    }
    /**
     * 打开设置对话框；purpose/originalProviderId 用于「补给原任务凭据」区块。
     */
    function open(purpose, originalProviderId) {
        returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : trigger;
        rows.replaceChildren();
        original.replaceChildren();
        selectors.clear();
        draftKeys.clear();
        originalDraft = null;
        error.hidden = true;
        for (const p of PURPOSES) {
            const section = document.createElement("fieldset");
            const legend = document.createElement("legend");
            legend.textContent = LABELS[p];
            section.append(legend);
            const selectLabel = document.createElement("label");
            selectLabel.htmlFor = "model-provider-" + p;
            selectLabel.textContent = "现有模型";
            const select = document.createElement("select");
            select.id = selectLabel.htmlFor;
            for (const choice of choices[p]) {
                const option = document.createElement("option");
                option.value = choice.id;
                option.textContent = choice.label + " · " + choice.model_id + (choice.vision ? "（实际发送图片）" : "");
                select.append(option);
            }
            select.value = selected[p] || "";
            const input = keyField(p, select.value);
            const label = document.createElement("label");
            label.htmlFor = input.id;
            label.textContent = "自己的密钥";
            const clear = document.createElement("button");
            clear.type = "button";
            clear.textContent = "应用时清除此模型密钥";
            clear.addEventListener("click", () => { draftKeys.set(keyId(p, select.value), ""); input.value = ""; input.placeholder = "应用时清除；未应用不改变当前凭据"; });
            input.addEventListener("input", () => { draftKeys.set(keyId(p, select.value), input.value); });
            select.addEventListener("change", () => showKeyState(p, select.value, input));
            section.append(selectLabel, select, label, input, clear);
            selectors.set(p, select);
            rows.append(section);
        }
        if (purpose && originalProviderId) {
            const title = document.createElement("h3");
            title.textContent = "补给原任务凭据（不切换新动作模型）";
            const name = document.createElement("p");
            name.textContent = originalProviderId;
            const input = keyField(purpose, originalProviderId);
            input.id = "model-key-original";
            const label = document.createElement("label");
            label.htmlFor = input.id;
            label.textContent = "原目标的 API key";
            originalDraft = { purpose, providerId: originalProviderId, input };
            original.append(title, name, label, input);
            original.hidden = false;
        }
        else
            original.hidden = true;
        apply.disabled = choices.semantic.length === 0 || choices.image.length === 0 || choices.review.length === 0;
        if (!dialog.open)
            dialog.showModal();
        if (originalDraft)
            originalDraft.input.focus();
        else
            (selectors.get(purpose || "semantic") || cancel).focus();
    }
    /** 清空全部草稿密钥输入后关闭对话框（未应用的 key 不写入内存 keys）。 */
    function close() {
        for (const input of form.querySelectorAll("input[type=password]"))
            if (input instanceof HTMLInputElement)
                input.value = "";
        draftKeys.clear();
        originalDraft = null;
        dialog.close();
        returnFocus?.focus();
    }
    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (apply.disabled)
            return;
        error.hidden = true;
        for (const p of PURPOSES) {
            const value = selectors.get(p)?.value;
            if (!value || !choices[p].some((c) => c.id === value)) {
                error.textContent = "请选择目录中的现有模型。";
                error.hidden = false;
                return;
            }
        }
        const originalKey = originalDraft?.input.value.trim();
        if ([...draftKeys.values(), originalKey || ""].some((v) => /[\r\n\x00-\x1f\x7f]/.test(v))) {
            error.textContent = "密钥含不允许的控制字符；没有应用。";
            error.hidden = false;
            return;
        }
        for (const p of PURPOSES)
            selected[p] = selectors.get(p)?.value;
        for (const [id, raw] of draftKeys) {
            const value = raw.trim();
            if (value)
                keys.set(id, value);
            else
                keys.delete(id);
        }
        if (originalDraft && originalKey)
            keys.set(keyId(originalDraft.purpose, originalDraft.providerId), originalKey);
        try {
            localStorage.setItem(PREFERENCE_KEY, JSON.stringify(selected));
        }
        catch { /* Nonsecret preference persistence is optional. */ }
        close();
        await refresh();
    });
    cancel.addEventListener("click", close);
    dialog.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
    trigger.addEventListener("click", () => { if (capabilities)
        open();
    else
        void refresh().then(() => open()); });
    return {
        headers, allHeaders, refresh, open,
        get capabilities() { return capabilities; },
        get refreshing() { return refreshing; },
        /**
         * 指定图片 provider（可选凭据来源）的有效环境；未配置返回 null。
         */
        imageEnvironment(providerId = selected.image, credentialSource) {
            if (!providerId)
                return null;
            return (credentialSource ? imageEnvironments.get(providerId + ":" + credentialSource) : null)
                || imageEnvironments.get(providerId) || null;
        },
        /**
         * 订阅配置变化；返回取消订阅函数。
         */
        subscribe(listener) { listeners.add(listener); return () => listeners.delete(listener); },
    };
}
