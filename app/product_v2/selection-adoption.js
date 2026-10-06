// Generated from app/product_v2/selection-adoption.ts; edit the TS source and run `npm run build:frontend`.
/** 人工采用/取消/Unknown 知悉的持久化顺序；不依赖 DOM，不自动选择最新候选。 */
import { DOMAIN_DOCUMENT_KINDS, REVIEW_REPORT_DOCUMENT_KIND, acknowledgementDocumentIdOf, assertSelectionRecord, buildAcknowledgement, buildReviewReport, buildSelectionRecord, buildSelectionSet, candidateMatchesAttempt, deriveSelectionState, emptyShotSpecFromShot, evaluateCandidateFindings, mergeVlmReview, newActionId, promptStaleness, reviewIsCurrent, reviewSummaryText, selectionSummaryText, suitePlanSummary, } from "./domain/index.js";
import { confirmedFacts, sourceContext } from "./prompts.js";
import { sha256Hex } from "./storage/db.js";
import { consumptionFence } from "./project-inputs.js";
export function createSelectionAdoptionModule(deps) {
    let selections = new Map();
    let acknowledgements = new Map();
    let selecting = null;
    let reviewReports = new Map();
    let reviewFlights = new Set();
    function messageOf(error) {
        if (error !== null && typeof error === "object" && "message" in error
            && typeof error.message === "string")
            return error.message;
        return "";
    }
    function reportAccess() {
        return deps.reviewAccess || {
            reportOf: (candidateId) => reviewReports.get(candidateId) || null,
            reportsNow: () => Array.from(reviewReports.entries()),
            loadReport: (candidateId, entry) => { reviewReports.set(candidateId, entry); },
            ensureReport: (shotId, candidate, bytes, pid, options = {}) => ensureReviewReport(shotId, candidate, bytes, pid, options),
        };
    }
    function reset() {
        selections = new Map();
        acknowledgements = new Map();
        selecting = null;
        reviewReports = new Map();
        reviewFlights = new Set();
    }
    function basisOf(shotId, candidateId, source) {
        const candidate = deps.generation.candidateChainOf(shotId).find(entry => entry.record.candidate_id === candidateId)?.record;
        if (!candidate)
            return { consumedStale: false };
        const attempt = deps.generation.attemptChainOf(shotId).find(entry => entry.record.action_id === candidate.action_id)?.record;
        const prompt = attempt ? deps.prompts.entryOf(shotId, attempt.prompt.version) : null;
        return { consumedStale: !prompt || prompt.record.hash !== attempt?.prompt.hash
                || promptStaleness(prompt.record, deps.prompts.basis(shotId, prompt.record.compiled.provider, source)).stale };
    }
    function stateOf(shotId) {
        const record = selections.get(shotId)?.record || null;
        return deriveSelectionState(record, deps.generation.candidateChainOf(shotId), basisOf(shotId, record?.candidate_id || null, deps.sources()));
    }
    function sourceOf(shotId, candidateId) {
        if (!shotId || !candidateId)
            return null;
        const entry = deps.generation.candidateChainOf(shotId).find(entry => entry.record.candidate_id === candidateId);
        if (!entry)
            return null;
        const stored = reportAccess().reportOf(candidateId);
        return { candidate: entry.record, version: entry.version,
            report: stored && stored.version > 0 && reviewIsCurrent(stored.report, entry.record) ? stored.report : null };
    }
    function projection(source = deps.sources()) {
        const shots = source.suitePlan ? suitePlanSummary(source.suitePlan, sourceContext(source)).shots : [];
        const records = {}, candidateIds = {};
        const candidatesByShotId = {};
        const basisByShotId = {};
        for (const shot of shots) {
            const record = selections.get(shot.shot_id)?.record;
            if (record) {
                records[shot.shot_id] = record;
                if (record.action === "select" && record.candidate_id)
                    candidateIds[shot.shot_id] = record.candidate_id;
            }
            candidatesByShotId[shot.shot_id] = deps.generation.candidateChainOf(shot.shot_id).map(entry => entry.record);
            basisByShotId[shot.shot_id] = basisOf(shot.shot_id, record?.candidate_id || null, source);
        }
        const set = buildSelectionSet({ shots, selections: records, candidatesByShotId, basisByShotId, at: new Date().toISOString() });
        const states = {};
        for (const entry of set.entries)
            if (entry.shot_id)
                states[entry.shot_id] = entry.state;
        return { set, records, candidateIds, states };
    }
    async function select(kind, shotId, candidateId) {
        const action = deps.beginAction();
        if (!action.projectId || !shotId || selecting)
            return { skipped: true, reason: "in_flight", currentSession: action.alive() };
        const source = sourceOf(shotId, candidateId);
        const previous = selections.get(shotId);
        const flight = {};
        selecting = flight;
        const roleId = deps.sources().suitePlan?.shots.find(shot => shot.shot_id === shotId)?.role_id || null;
        const consumedSource = deps.sources();
        try {
            if (kind === "select") {
                if (!source)
                    throw new Error("候选已不在本地链中；原采用保留。");
                const asset = await deps.repository.assets.get(action.projectId, source.candidate.asset_sha256);
                if (!asset?.blob || await sha256Hex(await asset.blob.arrayBuffer()) !== source.candidate.asset_sha256) {
                    throw new Error("候选字节缺失或哈希不一致；原采用保留，请恢复项目包或候选字节。");
                }
                const checked = await reportAccess().ensureReport(shotId, source.candidate, null, action.projectId, { action, roleId });
                if (!checked || checked.version < 1 || !reviewIsCurrent(checked.report, source.candidate)) {
                    throw new Error("没有当前已保存的确定性检查报告；原采用保留。此检查不需要 AI 复核。");
                }
                source.report = checked.report;
            }
            const record = buildSelectionRecord({
                selectionId: newActionId(), action: kind, shotId,
                candidate: kind === "select" ? source?.candidate || null : null,
                candidateVersion: kind === "select" ? source?.version || null : null,
                report: kind === "select" ? source?.report || null : null, at: new Date().toISOString(),
            });
            assertSelectionRecord(record);
            const observation = kind === "select" && source
                ? deps.generation.attemptChainOf(shotId).find(item => item.record.action_id === source.candidate.action_id
                    && item.record.state === "succeeded") : null;
            const reportEntry = source ? reportAccess().reportOf(source.candidate.candidate_id) : null;
            const fence = consumptionFence(consumedSource, [shotId]);
            if (source)
                fence.assetSha256 = [...fence.assetSha256, source.candidate.asset_sha256];
            const saved = await deps.repository.commitSelection({
                projectId: action.projectId, shotId, decision: record, seenSelectionVersion: previous?.version || 0,
                fence, candidate: kind === "select" && source
                    ? { kind: "candidate", documentId: shotId, version: source.version } : null,
                attempt: observation ? { actionId: observation.record.action_id, version: observation.version } : null,
                report: kind === "select" && source && reportEntry
                    ? { kind: "review_report", documentId: source.candidate.candidate_id, version: reportEntry.version } : null,
            });
            if (action.alive())
                selections.set(shotId, { record, version: saved.version });
            return { record, version: saved.version, candidateVersion: source?.version || null, currentSession: action.alive() };
        }
        finally {
            if (selecting === flight)
                selecting = null;
        }
    }
    async function acknowledge(unknown) {
        const action = deps.beginAction();
        if (!action.projectId)
            throw new Error("缺少项目上下文，确认没有保存。");
        const record = buildAcknowledgement({ unknown, at: new Date().toISOString() });
        const documentId = acknowledgementDocumentIdOf(record);
        await deps.repository.documents.save(action.projectId, { kind: "review_acknowledgement", documentId, payload: record });
        if (action.alive())
            acknowledgements.set(documentId, record);
        return { record, currentSession: action.alive() };
    }
    async function restore(action) {
        if (!action.projectId)
            return;
        const selected = await deps.repository.documents.listLatest(action.projectId, DOMAIN_DOCUMENT_KINDS.selection);
        if (!action.alive())
            return;
        for (const stored of selected)
            selections.set(stored.document_id, { record: assertSelectionRecord(stored.payload), version: stored.version });
        const known = await deps.repository.documents.listLatest(action.projectId, DOMAIN_DOCUMENT_KINDS.review_acknowledgement);
        if (!action.alive())
            return;
        for (const stored of known)
            acknowledgements.set(stored.document_id, stored.payload);
        const reports = await deps.repository.documents.listLatest(action.projectId, REVIEW_REPORT_DOCUMENT_KIND);
        if (!action.alive())
            return;
        for (const stored of reports) {
            if (!stored.payload || typeof stored.payload !== "object")
                continue;
            reportAccess().loadReport(stored.document_id, {
                report: stored.payload, version: stored.version,
            });
        }
    }
    const MAX_REVIEW_IMAGE_BYTES = 4 * 1024 * 1024;
    const MAX_REVIEW_REFERENCES = 3;
    async function ensureReviewReport(shotId, candidate, bytes, pid, options = {}) {
        if (!pid)
            return null;
        const action = options.action || deps.beginAction();
        const existing = action.alive() ? reviewReports.get(candidate.candidate_id) : null;
        const consumedSource = deps.sources();
        if (existing && reviewIsCurrent(existing.report, candidate))
            return existing;
        let view = bytes || null;
        if (!view) {
            const asset = await deps.repository.assets.get(pid, candidate.asset_sha256);
            if (asset && asset.blob instanceof Blob) {
                view = new Uint8Array(await asset.blob.arrayBuffer());
            }
        }
        const suitePlan = consumedSource.suitePlan;
        const shot = (suitePlan && Array.isArray(suitePlan.shots) ? suitePlan.shots : [])
            .find((item) => item && item.shot_id === shotId);
        const deterministic = evaluateCandidateFindings({
            candidate: candidate,
            bytes: view,
            roleId: options.roleId !== undefined ? options.roleId : (shot ? shot.role_id : null),
        });
        let previous = null;
        if (existing && existing.report && existing.report.vlm
            && existing.report.vlm.asset_sha256 === candidate.asset_sha256) {
            previous = existing.report;
        }
        const carried = previous
            ? previous.findings.filter((item) => item && item.layer === "vlm") : [];
        let report = null;
        if (previous) {
            try {
                report = buildReviewReport({
                    candidate: candidate,
                    findings: deterministic.concat(carried),
                    vlm: previous.vlm,
                    at: new Date().toISOString(),
                });
            }
            catch (error) {
                report = null;
            }
        }
        if (!report) {
            report = buildReviewReport({
                candidate: candidate, findings: deterministic, at: new Date().toISOString(),
            });
        }
        let entry;
        try {
            const fence = consumptionFence(consumedSource, [shotId]);
            fence.assetSha256 = [...fence.assetSha256, candidate.asset_sha256];
            const saved = await deps.repository.commitReviewReport({
                projectId: pid, kind: "review_report", documentId: candidate.candidate_id,
                payload: report, seenReportVersion: existing?.version || 0,
                fence,
            });
            entry = { report, version: saved.version };
        }
        catch (error) {
            entry = { report, version: 0 };
        }
        if (action.alive())
            reviewReports.set(candidate.candidate_id, entry);
        return entry;
    }
    async function readReviewBytes(projectId, sha) {
        const asset = await deps.repository.assets.get(projectId, sha);
        return asset?.blob instanceof Blob ? new Uint8Array(await asset.blob.arrayBuffer()) : null;
    }
    async function reviewImagePayload(projectId, sha, mediaType) {
        const bytes = await readReviewBytes(projectId, sha);
        if (!bytes || bytes.length > MAX_REVIEW_IMAGE_BYTES)
            throw new Error("图片字节缺失或超过复核上限，没有发起 AI 复核。");
        if (await sha256Hex(bytes) !== sha)
            throw new Error("图片字节哈希不一致，没有发起 AI 复核。");
        let binary = "";
        for (let index = 0; index < bytes.length; index += 0x8000)
            binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
        return { media_type: mediaType, sha256: sha, data_base64: btoa(binary) };
    }
    /** 单图 AI 复核请求准备归 adoption：事实/规格/原动作/图片字节在此收口，generation 不反向依赖。 */
    async function candidateReviewRequest(shotId, candidate, projectId) {
        const source = structuredClone(deps.sources());
        const shot = source.suitePlan?.shots.find(entry => entry.shot_id === shotId);
        const spec = source.shotSpecs[shotId]?.spec || (shot ? emptyShotSpecFromShot(shot) : null);
        const original = deps.generation.attemptChainOf(shotId).find(entry => entry.record.action_id === candidate.action_id)?.record;
        if (!original || !candidateMatchesAttempt(candidate, original))
            throw new Error("候选的原动作来源链缺失或不一致，没有发起 AI 复核。");
        const references = original.references.slice(0, MAX_REVIEW_REFERENCES);
        const facts = confirmedFacts(source);
        const image = await reviewImagePayload(projectId, candidate.asset_sha256, candidate.media_type || "image/png");
        const payload = [];
        for (const ref of references) {
            const asset = await deps.repository.assets.get(projectId, ref.sha256);
            if (!asset?.blob)
                throw new Error("原动作参考图字节缺失，没有发起 AI 复核。");
            payload.push(await reviewImagePayload(projectId, ref.sha256, asset.media_type));
        }
        return { candidate: image, references: payload,
            shot: { title: String(shot?.label || shot?.role_id || "图片任务").slice(0, 200),
                purpose: String(spec?.purpose || "").slice(0, 500), keep_items: spec?.keep.slice(0, 8) || [],
                allow_changes: spec?.change_allowed.slice(0, 8) || [] },
            platform: "amazon_us", locale: "zh-CN", product_facts: facts };
    }
    const REVIEW_PATH = "/api/v2/review/candidate";
    async function reviewCandidate(shotId, candidateId) {
        const action = deps.beginAction();
        if (!action.projectId)
            return { skipped: true, reason: "no_project" };
        const pid = action.projectId;
        const flights = reviewFlights;
        if (flights.has(shotId))
            return { skipped: true, reason: "in_flight" };
        const headers = deps.settings.headers("review");
        const consumedSource = deps.sources();
        flights.add(shotId);
        deps.changed?.();
        try {
            const stored = deps.generation.candidateChainOf(shotId).find((entry) => entry.record.candidate_id === candidateId);
            const candidate = stored ? stored.record : null;
            if (!candidate)
                return { skipped: true, reason: "no_candidate" };
            let request = null;
            try {
                request = await candidateReviewRequest(shotId, candidate, pid);
            }
            catch (error) {
                return { failed: true, reason: "request_invalid", message: messageOf(error) || "复核请求无法构建。" };
            }
            if (!action.alive())
                return { skipped: true, reason: "stale_session" };
            let entry = reportAccess().reportOf(candidate.candidate_id);
            if (!entry || !reviewIsCurrent(entry.report, candidate)) {
                entry = await reportAccess().ensureReport(shotId, candidate, null, pid, { action });
            }
            if (!action.alive())
                return { skipped: true, reason: "stale_session" };
            if (!entry)
                return { failed: true, reason: "merge_invalid", message: "复核结果无法合并进报告。" };
            let envelope = null;
            try {
                const response = await fetch(REVIEW_PATH, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", ...headers },
                    body: JSON.stringify(request),
                });
                envelope = await response.json().catch(() => null);
            }
            catch (error) {
                envelope = null;
            }
            if (!envelope || typeof envelope !== "object") {
                envelope = { ok: false, unknown: true, error: { family: "internal", code: "REVIEW_TRANSPORT",
                        message: "复核服务没有返回可解析的结果（服务可能未启动）。", retry_policy: "requires_review" } };
            }
            const envelopeOk = envelope !== null && typeof envelope === "object"
                && "ok" in envelope && envelope.ok === true;
            let merged = null;
            try {
                merged = mergeVlmReview({ report: entry.report, candidate: candidate, review: envelope, at: new Date().toISOString() });
            }
            catch (error) {
                return { failed: true, reason: "merge_invalid", message: messageOf(error) || "复核结果无法合并进报告。" };
            }
            if (!merged || !merged.vlm) {
                return { failed: true, reason: "merge_invalid", message: "复核结果无法合并进报告。" };
            }
            const vlmBlock = merged.vlm;
            try {
                const fence = consumptionFence(consumedSource, [shotId]);
                fence.assetSha256 = [...fence.assetSha256, candidate.asset_sha256];
                const saved = await deps.repository.commitReviewReport({
                    projectId: pid, kind: "review_report", documentId: candidate.candidate_id,
                    payload: merged, seenReportVersion: entry.version,
                    fence,
                });
                if (action.alive())
                    reportAccess().loadReport(candidate.candidate_id, { report: merged, version: saved.version });
            }
            catch (error) {
                return { failed: true, reason: "stale_report", message: messageOf(error) || "复核来源已变化；原报告保留，没有自动重调。" };
            }
            return { ok: envelopeOk, outcome: vlmBlock.outcome, candidate_id: candidate.candidate_id, summary: reviewSummaryText(merged) };
        }
        finally {
            flights.delete(shotId);
            if (action.alive())
                deps.changed?.();
        }
    }
    return {
        reset, restore, stateOf, sourceOf, projection, select, acknowledge, candidateReviewRequest, reviewCandidate,
        reportOf: (candidateId) => reportAccess().reportOf(candidateId),
        reportsNow: () => reportAccess().reportsNow(),
        loadReport: (candidateId, entry) => reportAccess().loadReport(candidateId, entry),
        ensureReport: (shotId, candidate, bytes, pid, options = {}) => reportAccess().ensureReport(shotId, candidate, bytes, pid, options),
        entryOf: id => id ? selections.get(id) || null : null,
        adoptedMark(id) {
            const entry = id ? selections.get(id) : null;
            return id && entry?.record.action === "select" ? { candidate_id: entry.record.candidate_id, state: stateOf(id) } : null;
        },
        summary: id => selectionSummaryText(selections.get(id)?.record || null, stateOf(id)),
        acknowledgements: () => [...acknowledgements.values()], isSelecting: () => selecting !== null,
        isReviewInFlight: (shotId) => reviewFlights.has(shotId),
    };
}
