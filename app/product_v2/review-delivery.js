// Generated from app/product_v2/review-delivery.ts; edit the TS source and run `npm run build:frontend`.
/** 整套复核、交付硬门、原动作溯源与两类 ZIP 的唯一执行 Module；无 DOM、无对象 URL。 */
import { DOMAIN_DOCUMENT_KINDS, EXPORT_GATE_CONTRACT_VERSION, SUITE_MAX_IMAGES, SUITE_REVIEW_DOCUMENT_ID, assembleSuiteReview, buildDeliveryEntries, buildExportRecord, candidateMatchesAttempt, checkSuiteReviewReport, deliveryFileName, deliveryImagePathOf, emptyShotSpecFromShot, evaluateDeliveryGate, exportRecordDocumentIdOf, inputsFingerprintOf, selectionFingerprintOf, suitePlanSummary, suiteReviewIsCurrent, suiteReviewStatusOf, suiteReviewSummaryText, buildSelectionSet, assertSelectionRecord, promptStaleness, checkPromptRecord, checkReviewReport, checkAttemptRecord, checkCandidateRecord, attemptActions, } from "./domain/index.js";
import { sha256Hex } from "./storage/db.js";
import { buildZip, exportProjectPackage } from "./storage/index.js";
import { confirmedFacts, sourceContext, promptCurrentBasisOf } from "./prompts.js";
import { consumptionFence, projectSourcesFromSnapshot } from "./project-inputs.js";
const SUITE_REVIEW_PATH = "/api/v2/review/suite";
const MAX_REVIEW_IMAGE_BYTES = 4 * 1024 * 1024;
/** 导出的领域投影全部来自同一 IDB 快照，不能混用当前页面 Map 与另一个事务的字节。 */
function deliverySnapshot(stored) {
    const source = projectSourcesFromSnapshot(stored);
    const heads = new Map();
    const exact = new Map();
    const attempts = new Map();
    const candidatesByShot = {};
    for (const row of stored.documents) {
        const key = row.kind + "/" + row.document_id;
        if ((heads.get(key)?.version || 0) < row.version)
            heads.set(key, row);
        exact.set(key + "/" + row.version, row);
        if (row.kind === "generation_attempt") {
            if (checkAttemptRecord(row.payload).length)
                throw new Error("项目尝试历史不合法，不能交付。");
            const chain = attempts.get(row.document_id) || [];
            chain.push({ record: row.payload, version: row.version });
            attempts.set(row.document_id, chain);
        }
        else if (row.kind === "candidate") {
            if (checkCandidateRecord(row.payload).length)
                throw new Error("项目候选历史不合法，不能交付。");
            (candidatesByShot[row.document_id] ||= []).push(row.payload);
        }
    }
    const shots = source.suitePlan ? suitePlanSummary(source.suitePlan, sourceContext(source)).shots : [];
    const records = {}, candidateIds = {};
    const attemptsByShot = {}, basisByShotId = {};
    const reportsByCandidate = {}, reportEntries = {};
    const factsById = {}, shotSpecsById = {};
    for (const entry of source.slots)
        factsById[entry.slot.slot_id] = entry.slot;
    for (const [id, entry] of Object.entries(source.shotSpecs))
        shotSpecsById[id] = entry.spec;
    for (const shot of shots) {
        const id = shot.shot_id;
        candidatesByShot[id] ||= [];
        attemptsByShot[id] = attemptActions(attempts.get(id) || []).map(entry => entry.record);
        const selected = heads.get("selection/" + id);
        if (!selected)
            continue;
        const selection = assertSelectionRecord(selected.payload);
        records[id] = selection;
        if (selection.action !== "select" || !selection.candidate_id)
            continue;
        candidateIds[id] = selection.candidate_id;
        const candidate = candidatesByShot[id].find(item => item.candidate_id === selection.candidate_id);
        const attempt = candidate ? attemptsByShot[id].find(item => item.action_id === candidate.action_id) : null;
        const original = attempt ? exact.get("prompt_version/" + id + "/" + attempt.prompt.version) : null;
        const prompt = original?.payload;
        basisByShotId[id] = { consumedStale: !prompt || !attempt || checkPromptRecord(prompt).length > 0
                || prompt.hash !== attempt.prompt.hash || promptStaleness(prompt, promptCurrentBasisOf(source, id, prompt.compiled.provider)).stale };
        const report = heads.get("review_report/" + selection.candidate_id);
        if (report) {
            if (checkReviewReport(report.payload).length)
                throw new Error("已采用候选的检查报告不合法。");
            reportsByCandidate[selection.candidate_id] = report.payload;
            reportEntries[selection.candidate_id] = { report: report.payload, version: report.version };
        }
    }
    const set = buildSelectionSet({ shots, selections: records, candidatesByShotId: candidatesByShot,
        basisByShotId, at: new Date().toISOString() });
    const states = {};
    for (const item of set.entries)
        if (item.shot_id)
            states[item.shot_id] = item.state;
    const selection = { set, records, candidateIds, states };
    const selectionFingerprint = selectionFingerprintOf(set);
    const inputsFingerprint = inputsFingerprintOf({ selectionFingerprint, suitePlan: source.suitePlan,
        styleSpec: source.styleSpec, shotSpecsById, reportsByCandidate });
    const suiteRow = heads.get("suite_review/" + SUITE_REVIEW_DOCUMENT_ID);
    if (suiteRow && checkSuiteReviewReport(suiteRow.payload).length)
        throw new Error("整套检查报告不合法。");
    const suite = suiteRow ? { report: suiteRow.payload, version: suiteRow.version } : null;
    const acknowledgements = [];
    for (const row of heads.values())
        if (row.kind === "review_acknowledgement")
            acknowledgements.push(row.payload);
    const snap = { source, selection, shots, shotSpecsById, factsById, candidatesByShot, attemptsByShot,
        reportsByCandidate, reportEntries, acknowledgements, suite, fingerprints: { selectionFingerprint, inputsFingerprint } };
    function ref(kind, id, version) {
        const row = version === undefined ? heads.get(kind + "/" + id) : exact.get(kind + "/" + id + "/" + version);
        if (!row)
            throw new Error("交付精确来源缺失：" + kind + "/" + id);
        return { kind, documentId: id, version: row.version };
    }
    return { snap, ref, attempts };
}
export function createReviewDeliveryModule(deps) {
    let suite = null;
    let running = null;
    let exporting = null;
    let gate = null;
    let record = null;
    let gateRevision = 0;
    let gateTimer = null;
    function reset() {
        suite = null;
        running = null;
        exporting = null;
        gate = null;
        record = null;
        gateRevision += 1;
        if (gateTimer !== null)
            clearTimeout(gateTimer);
        gateTimer = null;
    }
    function snapshot(freeze = false) {
        const source = deps.sources();
        const selection = deps.adoption.projection(source);
        const shots = source.suitePlan ? suitePlanSummary(source.suitePlan, sourceContext(source)).shots : [];
        const shotSpecsById = {}, factsById = {};
        const candidatesByShot = {}, attemptsByShot = {};
        const reportsByCandidate = {}, reportEntries = {};
        for (const [id, entry] of Object.entries(source.shotSpecs))
            shotSpecsById[id] = entry.spec;
        for (const { slot } of source.slots)
            factsById[slot.slot_id] = slot;
        for (const shot of shots) {
            candidatesByShot[shot.shot_id] = deps.generation.candidateChainOf(shot.shot_id).map(entry => entry.record);
            attemptsByShot[shot.shot_id] = attemptActions(deps.generation.attemptChainOf(shot.shot_id)).map(entry => entry.record);
            const id = selection.candidateIds[shot.shot_id];
            const entry = id ? deps.adoption.reportOf(id) : null;
            if (entry && entry.version > 0) {
                reportsByCandidate[id] = entry.report;
                reportEntries[id] = entry;
            }
        }
        const selectionFingerprint = selectionFingerprintOf(selection.set);
        const inputsFingerprint = inputsFingerprintOf({ selectionFingerprint, suitePlan: source.suitePlan,
            styleSpec: source.styleSpec, shotSpecsById, reportsByCandidate });
        const result = { source, selection, shots, shotSpecsById, factsById, candidatesByShot, attemptsByShot,
            reportsByCandidate, reportEntries, acknowledgements: deps.adoption.acknowledgements(), suite,
            fingerprints: { selectionFingerprint, inputsFingerprint } };
        return freeze ? structuredClone(result) : result;
    }
    async function readBytes(projectId, sha) {
        const asset = await deps.repository.assets.get(projectId, sha);
        return asset?.blob instanceof Blob ? new Uint8Array(await asset.blob.arrayBuffer()) : null;
    }
    async function imagePayload(projectId, sha, mediaType) {
        const bytes = await readBytes(projectId, sha);
        if (!bytes || bytes.length > MAX_REVIEW_IMAGE_BYTES)
            throw new Error("图片字节缺失或超过复核上限，没有发起 AI 复核。");
        if (await sha256Hex(bytes) !== sha)
            throw new Error("图片字节哈希不一致，没有发起 AI 复核。");
        let binary = "";
        for (let index = 0; index < bytes.length; index += 0x8000)
            binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
        return { media_type: mediaType, sha256: sha, data_base64: btoa(binary) };
    }
    function styleSummary(source) {
        const style = source.styleSpec;
        return [style.background && "背景：" + style.background, style.lighting && "光线：" + style.lighting,
            style.color_tone && "色调：" + style.color_tone, style.composition && "构图：" + style.composition,
            style.avoid.length && "避免：" + style.avoid.join("、")].filter(Boolean).join("；").slice(0, 500);
    }
    async function suiteRequest(snap, projectId) {
        const requested = snap.shots.filter(shot => snap.selection.states[shot.shot_id] === "current").map(shot => shot.shot_id);
        if (!requested.length || requested.length > SUITE_MAX_IMAGES)
            return {
                reason: requested.length ? "over_limit" : "no_selection", requested, submitted: [], shaByShot: {}, request: null
            };
        const images = [], submitted = [], shaByShot = {};
        try {
            for (const id of requested) {
                const candidate = snap.candidatesByShot[id].find(candidate => candidate.candidate_id === snap.selection.candidateIds[id]);
                if (!candidate)
                    throw new Error("缺少候选来源。");
                const shot = snap.source.suitePlan?.shots.find(shot => shot.shot_id === id);
                const spec = snap.shotSpecsById[id] || (shot ? emptyShotSpecFromShot(shot) : null);
                const image = await imagePayload(projectId, candidate.asset_sha256, candidate.media_type || "image/png");
                images.push({ shot_id: id, title: String(shot?.label || shot?.role_id || "图片任务").slice(0, 200),
                    purpose: String(spec?.purpose || "").slice(0, 500), keep_items: spec?.keep.slice(0, 8) || [],
                    allow_changes: spec?.change_allowed.slice(0, 8) || [], image });
                submitted.push(id);
                shaByShot[id] = candidate.asset_sha256;
            }
        }
        catch {
            return { reason: "missing_bytes", requested, submitted: [], shaByShot: {}, request: null };
        }
        return { reason: null, requested, submitted, shaByShot,
            request: { images, platform: "amazon_us", locale: "zh-CN", style_summary: styleSummary(snap.source), product_facts: confirmedFacts(snap.source) } };
    }
    async function runSuiteReview({ ai = false } = {}) {
        const action = deps.beginAction();
        if (!action.projectId || running)
            return { skipped: true, reason: "in_flight", currentSession: action.alive() };
        const snap = snapshot(true);
        if (!snap.source.suitePlan)
            return { failed: true, reason: "no_plan", message: "还没有套图方案。", currentSession: action.alive() };
        const fence = consumptionFence(snap.source, snap.shots.map(shot => shot.shot_id));
        const reviewSources = [...fence.sources], reviewAssets = [...fence.assetSha256];
        for (const shot of snap.shots) {
            const selection = deps.adoption.entryOf(shot.shot_id);
            reviewSources.push({ kind: "selection", documentId: shot.shot_id, version: selection?.version || 0 });
            const id = snap.selection.candidateIds[shot.shot_id];
            const report = id ? snap.reportEntries[id] : null;
            if (id)
                reviewSources.push({ kind: "review_report", documentId: id, version: report?.version || 0 });
            const candidate = snap.candidatesByShot[shot.shot_id]?.find(item => item.candidate_id === id);
            if (candidate)
                reviewAssets.push(candidate.asset_sha256);
        }
        fence.sources = reviewSources;
        fence.assetSha256 = reviewAssets;
        if (ai && !deps.settings.capabilities?.suite_review?.provider?.configured) {
            deps.settings.open("review");
            return { failed: true, reason: "configuration_missing", currentSession: action.alive() };
        }
        // 凭据只属于这一请求的内存快照，永不进入 snap、报告或 ZIP。
        const headers = ai ? deps.settings.headers("review") : {};
        const flight = {};
        running = flight;
        deps.changed();
        try {
            let vlmRun = null;
            if (ai) {
                const prepared = await suiteRequest(snap, action.projectId);
                if (!action.alive())
                    return { skipped: true, reason: "stale_session", currentSession: false };
                let envelope = null;
                if (prepared.request) {
                    try {
                        const response = await fetch(SUITE_REVIEW_PATH, { method: "POST",
                            headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify(prepared.request) });
                        envelope = await response.json().catch(() => null);
                    }
                    catch {
                        envelope = null;
                    }
                }
                const reason = prepared.reason || (!envelope || typeof envelope !== "object" ? "transport"
                    : ("ok" in envelope && envelope.ok === true ? null : "server"));
                vlmRun = { envelope, reason, requested_shot_ids: prepared.requested,
                    submitted_shot_ids: prepared.reason ? [] : prepared.submitted, asset_sha256_by_shot: prepared.reason ? {} : prepared.shaByShot };
            }
            const report = await assembleSuiteReview({
                selectionSet: snap.selection.set, suitePlan: snap.source.suitePlan, styleSpec: snap.source.styleSpec,
                shotSpecsById: snap.shotSpecsById, context: sourceContext(snap.source), factsById: snap.factsById,
                sellingPoints: snap.source.sellingPoints, shots: snap.shots, selections: snap.selection.candidateIds,
                candidatesByShot: snap.candidatesByShot, attemptsByShot: snap.attemptsByShot,
                reportsByCandidate: snap.reportsByCandidate, previousReport: snap.suite?.report || null,
                readBytes: (sha) => readBytes(action.projectId, sha), digest: sha256Hex, vlmRun, at: new Date().toISOString(),
            });
            const saved = await deps.repository.commitReviewReport({
                projectId: action.projectId, kind: "suite_review", documentId: SUITE_REVIEW_DOCUMENT_ID,
                payload: report, seenReportVersion: snap.suite?.version || 0, fence,
            });
            if (action.alive())
                suite = { report, version: saved.version };
            return { ok: true, currentSession: action.alive(), summary: suiteReviewSummaryText(report), vlm: report.vlm?.outcome || "not_run" };
        }
        catch (error) {
            return { failed: true, reason: "assemble_invalid", currentSession: action.alive(),
                message: error instanceof Error ? error.message : "整套检查没有保存；之前的报告保留。" };
        }
        finally {
            if (running === flight)
                running = null;
            if (action.alive()) {
                requestGateRefresh();
                deps.changed();
            }
        }
    }
    async function evaluate(snap, projectId, read = sha => readBytes(projectId, sha)) {
        return evaluateDeliveryGate({ shots: snap.shots, selections: snap.selection.candidateIds,
            candidatesByShot: snap.candidatesByShot, reportsByCandidate: snap.reportsByCandidate, attemptsByShot: snap.attemptsByShot,
            suiteReport: snap.suite?.report || null, suiteFingerprints: snap.fingerprints, acknowledgements: snap.acknowledgements,
            readBytes: read, digest: sha256Hex });
    }
    async function refreshGate() {
        const action = deps.beginAction(), revision = ++gateRevision;
        if (!action.projectId) {
            gate = null;
            deps.changed();
            return null;
        }
        const snap = snapshot(true);
        let next;
        try {
            next = { ...await evaluate(snap, action.projectId), failed: false, checked_at: new Date().toISOString() };
        }
        catch (error) {
            next = { failed: true, message: error instanceof Error ? error.message : "交付门禁无法完成。",
                ready_to_export: false, findings: [], blocking: [], unknowns: [], unresolved_unknowns: [] };
        }
        if (!action.alive() || revision !== gateRevision)
            return null;
        const now = snapshot().fingerprints;
        if (now.selectionFingerprint !== snap.fingerprints.selectionFingerprint || now.inputsFingerprint !== snap.fingerprints.inputsFingerprint) {
            requestGateRefresh();
            return null;
        }
        gate = next;
        deps.changed();
        return next;
    }
    function requestGateRefresh() {
        gateRevision += 1;
        gate = null;
        if (gateTimer !== null)
            clearTimeout(gateTimer);
        gateTimer = setTimeout(() => { gateTimer = null; void refreshGate(); }, 60);
    }
    function counts(findings) {
        const result = { block: 0, high_risk: 0, warning: 0, unknown: 0, pass: 0 };
        for (const item of findings)
            result[item.severity.toLowerCase()] += 1;
        return result;
    }
    async function exportDelivery() {
        const action = deps.beginAction();
        if (!action.projectId || exporting)
            return { skipped: true, currentSession: action.alive() };
        const flight = {};
        exporting = flight;
        deps.changed();
        try {
            const stored = await deps.repository.readProjectSnapshot(action.projectId);
            const { snap, ref, attempts } = deliverySnapshot(stored);
            const assets = new Map();
            for (const asset of stored.assets)
                assets.set(asset.sha256, asset);
            const bytesBySha = new Map();
            const snapshotBytes = async (sha) => {
                const cached = bytesBySha.get(sha);
                if (cached)
                    return cached;
                const asset = assets.get(sha);
                if (!asset)
                    return null;
                const bytes = new Uint8Array(await asset.blob.arrayBuffer());
                bytesBySha.set(sha, bytes);
                return bytes;
            };
            const checked = await evaluate(snap, action.projectId, snapshotBytes);
            if (action.alive()) {
                gate = { ...checked, failed: false, checked_at: new Date().toISOString() };
                deps.changed();
            }
            if (!checked.ready_to_export)
                throw new Error("交付门禁未通过：先处理阻断项并确认 Unknown。没有生成交付包。");
            const files = [];
            const images = [];
            for (const shot of snap.shots) {
                const id = snap.selection.candidateIds[shot.shot_id];
                if (!id)
                    continue;
                const candidate = snap.candidatesByShot[shot.shot_id].find(candidate => candidate.candidate_id === id);
                const attempt = candidate ? snap.attemptsByShot[shot.shot_id].find(attempt => attempt.action_id === candidate.action_id
                    && candidateMatchesAttempt(candidate, attempt)) : null;
                if (!candidate || !attempt)
                    throw new Error(shot.label + " 的候选原动作来源链缺失，不能打包。");
                const bytes = await snapshotBytes(candidate.asset_sha256);
                if (!bytes || await sha256Hex(bytes) !== candidate.asset_sha256)
                    throw new Error(shot.label + " 的候选字节缺失或哈希不一致，不能打包。");
                const mediaType = candidate.media_type || "image/png";
                images.push({ shot_id: shot.shot_id, candidate_id: id, media_type: mediaType, bytes });
                // 原 action 冻结的 Prompt 指针是交付来源，绝不读当前编辑头。
                files.push({ shot_id: shot.shot_id, shot_label: shot.label, candidate_id: id,
                    attempt_action_id: candidate.action_id, attempt_state: attempt.state, asset_sha256: candidate.asset_sha256,
                    media_type: mediaType, byte_size: bytes.length, prompt_version: attempt.prompt.version, prompt_hash: attempt.prompt.hash,
                    path: deliveryImagePathOf({ shotId: shot.shot_id, candidateId: id, mediaType }) });
            }
            if (!images.length)
                throw new Error("没有可交付的已采用候选。");
            const at = new Date().toISOString(), projectName = snap.source.projectName;
            const manifest = { schema_version: 1, contract_version: EXPORT_GATE_CONTRACT_VERSION,
                project_id: action.projectId, project_name: projectName, exported_at: at,
                selection_fingerprint: snap.fingerprints.selectionFingerprint, inputs_fingerprint: snap.fingerprints.inputsFingerprint,
                ai_review: suiteReviewStatusOf(snap.suite?.report), images: files.map(file => ({
                    ...file, file: file.path, ai_review: suiteReviewStatusOf(snap.reportsByCandidate[file.candidate_id]),
                })) };
            const checks = { schema_version: 1, contract_version: EXPORT_GATE_CONTRACT_VERSION, generated_at: at,
                gate_status: checked.status, findings: checked.findings,
                per_shot: files.map(file => {
                    const entry = snap.reportEntries[file.candidate_id], findings = entry?.report.findings || [];
                    return { shot_id: file.shot_id, candidate_id: file.candidate_id, report_version: entry?.version || null,
                        ai_review: suiteReviewStatusOf(entry?.report), counts: counts(findings),
                        findings: findings.filter(item => item.severity !== "PASS").map(item => ({ rule_id: item.rule_id, severity: item.severity, title: item.title, detail: item.detail })) };
                }),
                suite_review: snap.suite ? { document_id: SUITE_REVIEW_DOCUMENT_ID, version: snap.suite.version,
                    ai_review: suiteReviewStatusOf(snap.suite.report), selection_fingerprint: snap.suite.report.selection_fingerprint,
                    inputs_fingerprint: snap.suite.report.inputs_fingerprint, counts: counts(snap.suite.report.findings) } : null,
                acknowledgements: snap.acknowledgements.map(ack => ({ document_id: acknowledgementId(ack), rule_id: ack.rule_id,
                    target_kind: ack.target_kind, shot_ids: ack.shot_ids, acknowledged_at: ack.acknowledged_at })) };
            const readme = ["商品套图交付包", "", "项目：" + (projectName || "(未命名)"), "生成时间：" + at,
                "包含图片：" + files.length + " 张（每张一个已采用候选）", "", "清单：",
                ...files.map(file => "- " + file.shot_label + "：" + file.path + "（candidate " + file.candidate_id + " · sha256 " + file.asset_sha256.slice(0, 12) + "…）"),
                "", "manifest.json 记录每张图的来源与指纹；checks.json 记录门禁与审核发现。",
                "本包只包含已采用的候选；未采用候选与完整历史请用「导出项目包」。"].join("\n");
            const entries = buildDeliveryEntries({ images, manifest, checks, readme });
            const bytes = buildZip(entries, { modifiedAt: new Date(at) }), sha = await sha256Hex(bytes);
            const payload = buildExportRecord({ projectId: action.projectId, projectName, zipSha256: sha,
                zipBytes: bytes.length, entries, gate: checked, ...snap.fingerprints, includedShotIds: images.map(image => image.shot_id), at });
            if (!snap.suite)
                throw new Error("缺少整套确定性检查，不能交付。");
            const candidateRefs = [], promptRefs = [];
            const actionRefs = [];
            for (const file of files) {
                const row = stored.documents.find(row => row.kind === "candidate" && row.document_id === file.shot_id
                    && row.payload.candidate_id === file.candidate_id);
                if (!row)
                    throw new Error("候选精确版本缺失。");
                candidateRefs.push(ref("candidate", file.shot_id, row.version));
                const observation = attemptActions(attempts.get(file.shot_id) || [])
                    .find(item => item.record.action_id === file.attempt_action_id);
                if (!observation)
                    throw new Error("原动作精确观察缺失。");
                actionRefs.push({ actionId: observation.record.action_id, version: observation.version });
                promptRefs.push(ref("prompt_version", file.shot_id, file.prompt_version));
            }
            // 围栏只钉住实际交付的 shots：无关 shot 调整不误阻断交付（设计 §10.6）。
            const fence = consumptionFence(snap.source, images.map(image => image.shot_id));
            fence.assetSha256 = [...fence.assetSha256, ...files.map(file => file.asset_sha256)];
            await deps.repository.commitDeliveryRecord({
                projectId: action.projectId, exportDocumentId: exportRecordDocumentIdOf({ at, zipSha256: sha }), payload,
                selections: files.map(file => ref("selection", file.shot_id)),
                reports: files.map(file => ref("review_report", file.candidate_id)),
                acknowledgements: snap.acknowledgements.map(ack => ref("review_acknowledgement", acknowledgementId(ack))),
                suiteReport: ref("suite_review", SUITE_REVIEW_DOCUMENT_ID), candidates: candidateRefs, attempts: actionRefs,
                originalPrompts: promptRefs, fence,
            });
            const file_name = deliveryFileName({ projectName, at });
            if (action.alive())
                record = { file_name, byte_size: bytes.length, sha256: sha, at };
            return { currentSession: action.alive(), artifact: { bytes, file_name, sha256: sha, at },
                includedShots: images.length, projectId: action.projectId };
        }
        finally {
            if (exporting === flight)
                exporting = null;
            if (action.alive())
                deps.changed();
        }
    }
    async function exportProject() {
        const action = deps.beginAction();
        if (!action.projectId)
            return { skipped: true, currentSession: action.alive() };
        const projectName = deps.sources().projectName;
        const { bytes, manifest } = await exportProjectPackage(deps.repository, action.projectId);
        const at = manifest.exported_at, sha = await sha256Hex(bytes);
        const safe = projectName.replace(/[\\/:*?"<>|\s]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "project";
        const stamp = at.replace(/[-:]/g, "").replace("T", "-").slice(0, 13);
        return { currentSession: action.alive(), projectId: action.projectId,
            artifact: { bytes, file_name: safe + "-" + stamp + ".zip", sha256: sha, at } };
    }
    async function restore(action) {
        if (!action.projectId)
            return;
        const reports = await deps.repository.documents.listLatest(action.projectId, DOMAIN_DOCUMENT_KINDS.suite_review);
        if (!action.alive())
            return;
        const head = reports.find(doc => doc.document_id === SUITE_REVIEW_DOCUMENT_ID);
        if (head) {
            const problems = checkSuiteReviewReport(head.payload);
            if (problems.length)
                throw new Error("已保存的整套报告无法恢复：" + problems[0].message);
            suite = { report: head.payload, version: head.version };
        }
        const exports = await deps.repository.documents.listLatest(action.projectId, DOMAIN_DOCUMENT_KINDS.export_record);
        if (!action.alive())
            return;
        const latest = exports.map(doc => doc.payload).sort((a, b) => a.exported_at.localeCompare(b.exported_at)).at(-1);
        if (latest)
            record = { file_name: deliveryFileName({ projectName: deps.sources().projectName, at: latest.exported_at }),
                byte_size: latest.zip_bytes, sha256: latest.zip_sha256, at: latest.exported_at };
    }
    return { reset, restore, runSuiteReview, requestGateRefresh, refreshGate, exportDelivery, exportProject,
        fingerprints: () => snapshot().fingerprints,
        projection() {
            const snap = snapshot();
            return { suite, suiteCurrent: Boolean(suite && suiteReviewIsCurrent(suite.report, snap.fingerprints)),
                gate, running: running !== null, exporting: exporting !== null, record };
        } };
}
function acknowledgementId(record) {
    return [record.target_kind, record.target_id, record.rule_id, ...record.shot_ids].join("|");
}
