// Generated from app/product_v2/prompts.ts; edit the TS source and run `npm run build:frontend`.
/** Prompt 版本、编译、人工覆盖和确认单的业务所有权；浏览器只加载生成的 .js。 */
import { DOMAIN_DOCUMENT_KINDS, PLATFORM_PROFILES, assertConfirmationSheet, briefReadiness, buildConfirmationSheet, buildEditedPromptRecord, buildProductBrief, buildPromptRecord, canonicalJson, checkPromptRecord, compilePrompt, discardManualEdit, imagePromptProfile, promptHash, promptStaleness, reconfirmEditedPrompt, requestSnapshotOf, selectReferences, shotSignatureOf, suitePlanSummary, } from "./domain/index.js";
import { sha256Hex } from "./storage/db.js";
export function sourceContext(source) {
    return {
        facts: source.slots.map(({ slot }) => ({ slot_id: slot.slot_id, status: slot.status, value: slot.value })),
        assets: source.references,
    };
}
export function confirmedFacts(source) {
    return source.slots.filter(({ slot }) => slot.status === "confirmed").slice(0, 20).map(({ slot }) => ({
        slot_id: slot.slot_id, label: String(slot.label || slot.slot_id).slice(0, 60),
        value: (Array.isArray(slot.value) ? slot.value.join("；") : String(slot.value)).slice(0, 200),
        source: slot.source,
    }));
}
/** 只读当前依据投影（沿用既有 R6.2 算法，不引入第二套 currentness 约定）：
 * 活动输入实例与“已读快照”消费者共用同一份实现，避免各自重算。 */
export function promptCurrentBasisOf(source, shotId, provider) {
    let briefBasis = [];
    try {
        briefBasis = buildProductBrief(source.slots).basis;
    }
    catch { /* 未就绪事实仍可投影缺项。 */ }
    const shot = source.suitePlan?.shots.find(item => item.shot_id === shotId);
    return {
        briefBasis, shot_signature: shot ? shotSignatureOf(shot) : null,
        suite_version: source.suiteVersion || null, style_version: source.styleVersion || null,
        shot_spec_version: shotId ? source.shotSpecs[shotId]?.version || null : null,
        platform: { version: PLATFORM_PROFILES.amazon_us.version }, provider,
    };
}
export function createPromptModule(deps) {
    let versions = new Map();
    let history = new Map();
    let preparing = null;
    let lastPreparationInputs = "";
    function reset() {
        versions = new Map();
        history = new Map();
        preparing = null;
        lastPreparationInputs = "";
    }
    function remember(shotId, entry) {
        let chain = history.get(shotId);
        if (!chain) {
            chain = new Map();
            history.set(shotId, chain);
        }
        chain.set(entry.version, entry);
        if ((versions.get(shotId)?.version || 0) <= entry.version)
            versions.set(shotId, entry);
    }
    function entryOf(shotId, version) {
        if (!shotId)
            return null;
        return (version ? history.get(shotId)?.get(version) : versions.get(shotId)) || null;
    }
    function profile(environment = deps.imageEnvironment()) {
        try {
            return imagePromptProfile(environment);
        }
        catch {
            return null;
        }
    }
    function basis(shotId, provider = profile(), source = deps.sources()) {
        return promptCurrentBasisOf(source, shotId, provider);
    }
    function sheet(shotIds = null, provider = profile()) {
        const source = deps.sources();
        if (!source.suitePlan || !provider)
            return null;
        const currentBasisByShot = {};
        for (const shot of source.suitePlan.shots) {
            if (shot.shot_id)
                currentBasisByShot[shot.shot_id] = basis(shot.shot_id, provider, source);
        }
        const result = buildConfirmationSheet({
            suitePlan: source.suitePlan, providerProfile: provider, context: sourceContext(source),
            promptEntries: [...versions].map(([shot_id, entry]) => ({ shot_id, ...entry })),
            currentBasisByShot, shotIds,
        });
        assertConfirmationSheet(result);
        return result;
    }
    async function compile(shotId, options = {}) {
        const source = options.source || deps.sources();
        const shot = source.suitePlan?.shots.find(item => item.shot_id === shotId);
        if (!shot)
            throw new Error("找不到这张图，可能已被删除。");
        const providerProfile = profile();
        if (!providerProfile)
            throw new Error("尚未取得有效图像能力，请恢复模型服务后再编译；不会猜测模型参数。");
        const spec = source.shotSpecs[shotId];
        const compiled = compilePrompt({
            brief: buildProductBrief(source.slots), shot, styleSpec: source.styleSpec,
            shotSpec: spec?.spec || null, context: sourceContext(source), providerProfile,
            versions: { suite_version: source.suiteVersion, style_version: source.styleVersion, shot_spec_version: spec?.version || null },
            ...(options.rework ? { rework: options.rework } : {}),
        });
        const references = selectReferences(shot, source.references, { maxReferences: providerProfile.max_reference_images });
        const snapshot = requestSnapshotOf(compiled, { references });
        const hash = await promptHash(snapshot, { digest: sha256Hex });
        const payload = buildPromptRecord({ compiled, snapshot, hash });
        const problems = checkPromptRecord(payload);
        if (problems.length)
            throw new Error(problems[0].message);
        return { payload, compiled, references };
    }
    async function save(shotId, payload, action, expectedVersion) {
        if (!action.projectId)
            throw new Error("缺少项目上下文，无法保存 Prompt 版本。");
        const saved = await deps.repository.documents.save(action.projectId, {
            kind: "prompt_version", documentId: shotId, payload, expectedVersion,
        });
        if (action.alive())
            remember(shotId, { record: payload, version: saved.version });
        return saved;
    }
    async function compileAndSave(shotId, options = {}) {
        const action = options.action || deps.beginAction();
        const previous = entryOf(shotId)?.version || 0;
        const result = await compile(shotId, options);
        const saved = await save(shotId, result.payload, action, previous);
        return { ...result, saved };
    }
    async function prepare(drafts) {
        const action = deps.beginAction();
        if (!action.projectId)
            return { prepared: 0, errors: [], reason: "no_project" };
        if (preparing)
            return { prepared: 0, errors: [], reason: "in_flight" };
        const source = deps.sources();
        if (!source.suitePlan)
            return { prepared: 0, errors: [], reason: "no_plan" };
        if (!briefReadiness(buildProductBrief(source.slots)).ready)
            return { prepared: 0, errors: [], reason: "facts" };
        const provider = profile();
        if (!provider)
            return { prepared: 0, errors: [], reason: "configuration" };
        const summary = suitePlanSummary(source.suitePlan, sourceContext(source));
        const stamp = canonicalJson({ project_id: action.projectId, shots: summary.shots.map(item => ({
                id: item.shot_id, satisfied: item.satisfied, basis: basis(item.shot_id, provider, source),
                origin: entryOf(item.shot_id)?.record.origin || null,
            })) });
        if (stamp === lastPreparationInputs)
            return { prepared: 0, errors: [], reason: "unchanged" };
        const flight = {};
        preparing = flight;
        let prepared = 0;
        const errors = [];
        try {
            for (const item of summary.shots) {
                if (!action.alive())
                    return { prepared, errors, reason: "stale_session" };
                if (!item.satisfied || !item.shot_id)
                    continue;
                const entry = entryOf(item.shot_id), draft = drafts.get(item.shot_id);
                if (entry?.record.origin === "manual_edit" || (draft && entry && draft.text !== entry.record.compiled.text))
                    continue;
                if (entry && !promptStaleness(entry.record, basis(item.shot_id)).stale)
                    continue;
                try {
                    await compileAndSave(item.shot_id, { action });
                    prepared += 1;
                }
                catch (error) {
                    errors.push(item.label + "：" + (error instanceof Error ? error.message : "本地准备失败"));
                }
            }
            if (action.alive() && !errors.length)
                lastPreparationInputs = stamp;
            return { prepared, errors };
        }
        finally {
            if (preparing === flight)
                preparing = null;
        }
    }
    async function edit(shotId, text, reason, action = deps.beginAction()) {
        const entry = entryOf(shotId);
        if (!entry)
            throw new Error("先编译并保存这张图的 Prompt，再编辑。");
        const source = deps.sources();
        const record = await buildEditedPromptRecord({
            base: entry.record, baseVersion: entry.version, text, reason, editedAt: new Date().toISOString(),
            context: { ...sourceContext(source), brief: buildProductBrief(source.slots) }, digest: sha256Hex,
        });
        return save(shotId, record, action, entry.version);
    }
    async function reconfirm(shotId, visibleText, action = deps.beginAction()) {
        const entry = entryOf(shotId);
        if (!entry || entry.record.origin !== "manual_edit")
            return null;
        if (visibleText !== null && visibleText !== entry.record.compiled.text) {
            throw new Error("此全文有未保存修改；先保存，再重新确认，不会确认另一份旧文本。");
        }
        const source = deps.sources();
        const current = await compile(shotId, { source });
        const record = await reconfirmEditedPrompt({
            base: entry.record, baseVersion: entry.version, reason: "用户按当前依据显式确认保留此人工全文",
            at: new Date().toISOString(), basis: current.compiled.basis, references: current.references,
            context: { facts: source.slots.map(entry => entry.slot), brief: buildProductBrief(source.slots), currentCompiled: current.compiled },
            digest: sha256Hex,
        });
        return save(shotId, record, action, entry.version);
    }
    async function discard(shotId, action = deps.beginAction()) {
        const entry = entryOf(shotId);
        if (!entry || entry.record.origin !== "manual_edit")
            return null;
        const discarded = discardManualEdit(entry.record, [...(history.get(shotId)?.values() || [])]);
        const raw = discarded.target?.record;
        const candidate = raw && !checkPromptRecord(raw).length ? raw : null;
        const payload = candidate && !promptStaleness(candidate, basis(shotId)).stale ? candidate : (await compile(shotId)).payload;
        await save(shotId, payload, action, entry.version);
        return payload;
    }
    async function restore(action) {
        if (!action.projectId)
            return;
        const latest = await deps.repository.documents.listLatest(action.projectId, DOMAIN_DOCUMENT_KINDS.prompt_version);
        for (const head of latest) {
            if (!action.alive())
                return;
            const chain = await deps.repository.documents.listVersions(action.projectId, DOMAIN_DOCUMENT_KINDS.prompt_version, head.document_id);
            if (!action.alive())
                return;
            for (const stored of chain) {
                const problems = checkPromptRecord(stored.payload);
                if (problems.length)
                    throw new Error("已保存的 Prompt 无法恢复：" + problems[0].message);
                remember(stored.document_id, { record: stored.payload, version: stored.version });
            }
        }
    }
    return { reset, restore, entryOf, profile, basis, sheet, compile, compileAndSave, prepare, edit, reconfirm, discard,
        isPreparing: () => preparing !== null };
}
