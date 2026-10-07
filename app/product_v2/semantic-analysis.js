// Generated from app/product_v2/semantic-analysis.ts; edit the TS source and run `npm run build:frontend`.
import { checkFactSlot, isPlainObject, newActionId } from "./domain/index.js";
function isProposalSlot(value) {
    return isPlainObject(value) && checkFactSlot(value).length === 0
        && value.status === "proposed" && value.source === "model_inference"
        && (value.authority === "core_fixed" || value.authority === "category_dynamic")
        && typeof value.confidence === "number" && Number.isFinite(value.confidence)
        && value.confidence >= 0 && value.confidence <= 1
        && (value.model_id === undefined || typeof value.model_id === "string");
}
function readProposal(value, prepared) {
    if (!isPlainObject(value) || !Array.isArray(value.slots) || !value.slots.every(isProposalSlot)
        || typeof value.summary !== "string" || !Array.isArray(value.questions)
        || !value.questions.every((question) => typeof question === "string")
        || !isPlainObject(value.meta))
        throw new Error("商品理解返回了非法提案；没有写入事实槽位。");
    const meta = value.meta;
    if (meta.provider_id !== prepared.provider.provider_id || meta.model_id !== prepared.provider.model_id
        || typeof meta.reference_images_sent !== "boolean"
        || meta.reference_images_sent !== Boolean(prepared.body.reference_images?.length)
        || !Array.isArray(meta.inputs_used)
        || !meta.inputs_used.every((input) => typeof input === "string")
        || (meta.reference_images_sent && !meta.inputs_used.includes("actual_images"))
        || (meta.request_id !== null && typeof meta.request_id !== "string")) {
        throw new Error("商品理解的模型或实际看图身份与本次发送不符；没有写入事实槽位。");
    }
    return { slots: value.slots, summary: value.summary, questions: value.questions,
        meta: { provider_id: prepared.provider.provider_id, model_id: prepared.provider.model_id,
            request_id: meta.request_id, reference_images_sent: meta.reference_images_sent,
            inputs_used: meta.inputs_used } };
}
function readFailure(value, status) {
    const error = isPlainObject(value) && isPlainObject(value.error) ? value.error : {};
    return {
        family: typeof error.family === "string" ? error.family : "provider_unknown",
        code: typeof error.code === "string" ? error.code : "ANALYZE_RESPONSE_UNKNOWN",
        message: typeof error.message === "string" ? error.message : "商品理解未返回可核对的结果（HTTP " + status + "）。",
        retry_policy: typeof error.retry_policy === "string" ? error.retry_policy : "requires_review",
    };
}
function messageOf(error, fallback) {
    return error instanceof Error ? error.message : fallback;
}
/** Source-bound business execution. Headers/bytes live only inside this invocation. */
export function createSemanticAnalysisModule(deps) {
    const inFlight = new Set();
    const keyOf = (action) => action.projectId + "@" + action.generation;
    function isRunning() { return inFlight.has(keyOf(deps.beginAction())); }
    async function run({ allowNewAfterUnknown = false } = {}) {
        const action = deps.beginAction();
        const projectId = action.projectId;
        const flightKey = keyOf(action);
        if (!projectId || inFlight.has(flightKey))
            return { kind: "skipped", action };
        const pid = projectId;
        inFlight.add(flightKey);
        try {
            const previous = await deps.repository.documents.listLatest(pid, "semantic_analysis");
            const unresolved = previous.some(({ payload }) => isPlainObject(payload)
                && (payload.state === "pending_submit" || payload.state === "unknown"));
            if (unresolved && !allowNewAfterUnknown)
                return { kind: "requires_confirmation", action };
            let prepared;
            try {
                prepared = await deps.prepare(action);
            }
            catch (error) {
                return { kind: "not_sent", action,
                    message: messageOf(error, "本地资料尚未准备好；没有调用模型。") };
            }
            if (!action.alive() || !await deps.sourceIsCurrent(prepared.source, action)) {
                return { kind: "not_sent", action, message: "资料已变化；没有发送旧资料，请核对后重新明确发起。" };
            }
            const at = new Date().toISOString();
            const sentImages = prepared.body.reference_images || [];
            const imageProvenance = sentImages.map((item) => ({ role: String(item.role),
                media_type: String(item.media_type), sha256: String(item.sha256) }));
            const base = { schema_version: 1, action_id: newActionId(), source: prepared.source,
                provider: prepared.provider, created_at: at, updated_at: at,
                reference_images_sent: sentImages.length > 0, image_provenance: imageProvenance };
            let version = 0;
            async function save(record) {
                const saved = await deps.repository.documents.save(pid, { kind: "semantic_analysis",
                    documentId: base.action_id, payload: record, expectedVersion: version });
                version = saved.version;
            }
            await save({ ...base, state: "pending_submit", proposal: null, error: null, disposition: "not_applied" });
            if (!action.alive() || !await deps.sourceIsCurrent(prepared.source, action)) {
                const error = { family: "input_rejected", code: "SOURCE_CHANGED_BEFORE_SEND",
                    message: "资料已变化；未发送旧资料。", retry_policy: "fatal" };
                await save({ ...base, updated_at: new Date().toISOString(), state: "failed",
                    proposal: null, error, disposition: "not_applied" });
                return { kind: "not_sent", action, message: error.message };
            }
            let response;
            let payload;
            try {
                response = await fetch("/api/v2/semantic/analyze", { method: "POST",
                    headers: { "Content-Type": "application/json", ...prepared.headers },
                    body: JSON.stringify(prepared.body) });
                payload = await response.json();
            }
            catch {
                const error = { family: "provider_unknown", code: "ANALYZE_OUTCOME_UNKNOWN",
                    message: "理解结果未知，可能已经发送/计费；不会自动重试。", retry_policy: "requires_review" };
                await save({ ...base, updated_at: new Date().toISOString(), state: "unknown",
                    proposal: null, error, disposition: "not_applied" });
                return { kind: "unknown", action, error };
            }
            if (!response.ok || !isPlainObject(payload) || payload.ok !== true) {
                const error = readFailure(payload, response.status);
                const unknown = error.family === "provider_unknown" || response.status >= 500;
                await save({ ...base, updated_at: new Date().toISOString(), state: unknown ? "unknown" : "failed",
                    proposal: null, error, disposition: "not_applied" });
                return { kind: unknown ? "unknown" : "failed", action, error };
            }
            let proposal;
            try {
                proposal = readProposal(payload.proposal, prepared);
            }
            catch (error) {
                const failure = { family: "invalid_response", code: "PROPOSAL_INVALID",
                    message: messageOf(error, "商品理解返回了非法提案。"), retry_policy: "requires_review" };
                await save({ ...base, updated_at: new Date().toISOString(), state: "failed",
                    proposal: null, error: failure, disposition: "not_applied" });
                return { kind: "failed", action, error: failure };
            }
            let record = { ...base, updated_at: new Date().toISOString(),
                state: "succeeded", proposal, error: null, disposition: "stored" };
            await save(record);
            if (!action.alive() || !await deps.sourceIsCurrent(prepared.source, action)) {
                record = { ...record, updated_at: new Date().toISOString(), disposition: "stale" };
                await save(record);
                return { kind: "stale", action, record };
            }
            let applied;
            try {
                applied = await deps.apply(proposal, projectId, action, prepared.source);
            }
            catch (error) {
                return { kind: "apply_failed", action, record,
                    message: messageOf(error, "提案已保存到原资料，但写入事实槽位失败。") };
            }
            record = { ...record, updated_at: new Date().toISOString(), disposition: "applied" };
            await save(record);
            return { kind: "applied", action, record, proposal, applied };
        }
        finally {
            inFlight.delete(flightKey);
        }
    }
    return { run, isRunning };
}
