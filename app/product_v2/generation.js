// Generated from app/product_v2/generation.ts; edit the TS source and run `npm run build:frontend`.
/**
 * V2.R5.1 生成执行 Module：单张提交、按 task 核对、候选保存
 * 与整套批次轮询的唯一执行权威。
 *
 * 职责（计划 §V2.R5.1）：
 *  - 先登记后外发：pending_submit 身份先落 IndexedDB，再发网关请求；
 *  - 冻结动作归属：所有状态写按 session.beginAction() 冻结的 projectId 落库；
 *  - 核对只按已保存 task id + 冻结执行身份查询，绝不重提、不偷用当前配置；
 *  - 下载/容量处理：候选字节 hash 校验、大小护栏、配额失败不产生半份记录。
 *
 * 本模块不持有 DOM、不持有编辑状态：套图/确认/Prompt/参考图等只读输入经 deps
 * 读取；单图 AI 复核与确定性报告归 selection-adoption（本模块只保全候选并通知投影变化），
 * 渲染/状态/错误文案由视图读 notice() + 订阅 subscribe() 自取，不注入 DOM 回调。
 * workspace 只调用这里的接口并投影结果。
 *
 * TypeScript 迁移（计划 §9 V2.R7.5）：本文件是唯一手工维护实现；同名 `generation.js`
 * 由 `npm run build:frontend` 从本文件生成，浏览器只消费生成的 `.js`（import 说明符保持 `.js`）。
 */
import { ATTEMPT_DOCUMENT_KIND, ATTEMPT_RECONCILE_MODES, ATTEMPT_STATES, attemptCurrentEnvironmentIdentity, attemptExecutionIdentityFromEnvironment, attemptReconcileBlockedMessage, attemptReconcileEnvironment, attemptReconcileRequestOf, currentAttempt, buildAttemptRecord, checkAttemptRecord, newActionId, nextFromStatusEnvelope, nextFromSubmitEnvelope, selectReferences, CANDIDATE_DOCUMENT_KIND, CONFIRM_DOCUMENT_ID, MAX_CANDIDATE_BYTES, buildCandidateRecord, candidateForAttempt, candidateStoreDecision, checkCandidateRecord, parsePngDimensions, imagePromptProfile, canonicalJson, checkPromptRecord, checkConfirmationRecord, buildConfirmationRecord, confirmationSnapshot, DOMAIN_DOCUMENT_KINDS, promptStaleness, promptHash, batchProgressText, batchSubmitHalts, deriveBatchState, isNonEmptyString, } from "./domain/index.js";
import { sha256Hex } from "./storage/db.js";
const IMAGE_SUBMIT_PATH = "/api/v2/images/submit";
const IMAGE_STATUS_PATH = "/api/v2/images/status";
const IMAGE_RESULT_PATH = "/api/v2/images/result";
const BATCH_POLL_INTERVAL_MS = 4000;
const BATCH_POLL_MAX_ROUNDS = 300;
/* --------------------------------------------------------------- 运行时窄化助手 */
/** 抛出值的可读信息（原实现按 error.message 取值；此处 in/typeof 收窄，与旧行为一致）。 */
function messageOf(error) {
    if (error === null || typeof error !== "object" || !("message" in error))
        return "";
    const message = error.message;
    return typeof message === "string" ? message : "";
}
/** 同步提交信封里的结果字节字段（服务端契约；in/typeof 收窄，缺失即 null，绝不伪造字节）。 */
function readSyncEnvelope(envelope) {
    if (envelope === null || typeof envelope !== "object" || !("image_base64" in envelope))
        return null;
    const base64 = envelope.image_base64;
    if (typeof base64 !== "string")
        return null;
    const rawSha = "image_sha256" in envelope ? envelope.image_sha256 : null;
    return {
        imageBase64: base64,
        imageSha256: typeof rawSha === "string" ? rawSha.toLowerCase() : null,
    };
}
/** 出站请求体里的目标 provider id（服务端契约；未知即 undefined，不伪造）。 */
function providerIdFromBody(body) {
    if (body === null || typeof body !== "object" || !("target" in body))
        return undefined;
    const target = body.target;
    if (target === null || typeof target !== "object" || !("provider_id" in target))
        return undefined;
    return typeof target.provider_id === "string" ? target.provider_id : undefined;
}
const snapshotOfSheet = confirmationSnapshot;
const recordOfConfirmation = buildConfirmationRecord;
/* --------------------------------------------------------------- Module */
export function createGenerationModule(deps) {
    const functionDeps = ["beginAction", "projectIdReader", "environmentReader", "requestHeaders",
        "suitePlanReader", "suiteSummaryReader", "promptEntryReader",
        "confirmationReader", "promptBasisReader", "fenceReader", "referenceSourceReader",
        "promptsSheet", "imageEnvironment"];
    for (const name of functionDeps) {
        if (typeof deps[name] !== "function") {
            throw new Error("生成执行 Module 缺少依赖：" + name + "。");
        }
    }
    if (!deps.repository) {
        throw new Error("生成执行 Module 缺少依赖：repository。");
    }
    const repository = deps.repository;
    let attemptChains = new Map();
    let attemptInFlight = new Set();
    let candidateChains = new Map();
    let candidateInFlight = new Set();
    let authorizationInFlight = new Set();
    let batchState = null;
    // 授权队列/scope/mode 的唯一所有者（设计§2.1：generation 拥有显示摘要→明确提交→登记→执行的完整动作）。
    // 独立 authorization.ts 按包02删除，不留兼容别名。
    let confirmedQueues = new Map();
    let confirmed = null;
    let reworkQueues = new Map();
    let authorizationScope = null;
    let authorizationMode = "initial";
    // V2.R5.2 同步协议：提交信封里的结果字节暂存（action_id → {buffer, expectSha}）。
    // 明确不落盘：页面刷新/关闭即失效，候选保存走显式补救路径。取走即删。
    let pendingSyncBytes = new Map();
    // owner 只读文案投影 + 唯一投影变化通知出口：视图订阅读投影，不注入 DOM 回调。
    // 文案只是旁路动作的呈现结果，不参与任何业务判定（设计 §11.5.2）。
    let noticeStatus = "";
    let noticeError = "";
    const listeners = new Set();
    function notify() {
        for (const listener of [...listeners])
            listener();
    }
    function setStatus(text) {
        noticeStatus = text;
        notify();
    }
    function setNoticeError(text) {
        noticeError = text;
        notify();
    }
    function clearNoticeError() {
        if (!noticeError)
            return;
        noticeError = "";
        notify();
    }
    /* ------------------------------------------------------------ 链与身份 */
    function attemptChainOf(shotId) {
        return attemptChains.get(shotId) || [];
    }
    function latestAttemptOf(shotId) {
        return currentAttempt(attemptChainOf(shotId));
    }
    function allAttemptRecords() {
        const list = [];
        for (const chain of attemptChains.values()) {
            for (const entry of chain)
                list.push(entry.record);
        }
        return list;
    }
    function rememberAttempt(shotId, entry) {
        const chain = attemptChainOf(shotId).filter((item) => item.version !== entry.version);
        chain.push(entry);
        chain.sort((left, right) => left.version - right.version);
        attemptChains.set(shotId, chain);
    }
    function candidateChainOf(shotId) {
        return candidateChains.get(shotId) || [];
    }
    function rememberCandidate(shotId, entry) {
        const chain = candidateChainOf(shotId).filter((item) => item.version !== entry.version);
        chain.push(entry);
        chain.sort((left, right) => left.version - right.version);
        candidateChains.set(shotId, chain);
    }
    /** 最新 Attempt 若是「已成功且有候选」，返回该候选；其它情况返回 null。 */
    function latestStoredCandidateOf(shotId) {
        const latest = latestAttemptOf(shotId);
        if (!latest || latest.record.state !== ATTEMPT_STATES.succeeded)
            return null;
        return candidateForAttemptOf(shotId, latest.record.action_id);
    }
    function attemptProviderIdentity(record) {
        // A saved task resolves its frozen target, independently of the model selected for new actions.
        return attemptCurrentEnvironmentIdentity(deps.environmentReader(record));
    }
    /** 渲染投影：某次 Attempt 之前保存的候选（存在即幂等保存已冻结的事实）。 */
    function candidateForAttemptOf(shotId, actionId) {
        // Unchecked cast: 候选链条目恒为 {record, version}；domain 只回链中的元素（既有不变量）。
        const found = candidateForAttempt(candidateChainOf(shotId), actionId);
        return found;
    }
    function reset() {
        attemptChains = new Map();
        attemptInFlight = new Set();
        candidateChains = new Map();
        candidateInFlight = new Set();
        authorizationInFlight = new Set();
        confirmedQueues = new Map();
        confirmed = null;
        reworkQueues = new Map();
        authorizationScope = null;
        authorizationMode = "initial";
        pendingSyncBytes = new Map();
        batchState = null;
        // 换项目只清旁路文案；订阅者（视图）生命周期归 workspace 装配，不在 reset 里退订。
        noticeStatus = "";
        noticeError = "";
    }
    // 授权面：confirmedQueues/confirmed/reworkQueues/authorizationScope/authorizationMode 的
    // 唯一所有者（设计§2.1：显示摘要→明确提交→登记→执行的完整动作归 generation）。
    // rememberConfirmation 复用旧 authorization.ts:109-117 语义：整套确认更新 scope/mode，
    // 返工确认按 shot 登记；版本相等时后到覆盖（旧 JS 用 >=，与 TS 的 <= 同义）。
    const REWORK_CONFIRM_PREFIX = "rework:";
    function rememberConfirmation(queue) {
        confirmedQueues.set(queue.documentId + ":" + queue.version, queue);
        if (queue.documentId === CONFIRM_DOCUMENT_ID && (!confirmed || confirmed.version <= queue.version)) {
            confirmed = queue;
            authorizationScope = null;
            authorizationMode = "initial";
        }
        else if (queue.documentId.startsWith(REWORK_CONFIRM_PREFIX)) {
            const id = queue.documentId.slice(REWORK_CONFIRM_PREFIX.length);
            if ((reworkQueues.get(id)?.version || 0) <= queue.version)
                reworkQueues.set(id, queue);
        }
    }
    // restore 复用旧 authorization.ts:157-170：按 generation_confirm 列头+版本链恢复，
    // 每条经 checkConfirmationRecord 校验后登记（validation boundary，不伪造形状）。
    // restore 前调用方先 reset()（workspace loadWorkspace 已做），这里不二次清空。
    async function restore(action) {
        if (!action.projectId)
            return;
        const latest = await repository.documents.listLatest(action.projectId, DOMAIN_DOCUMENT_KINDS.generation_confirm);
        for (const head of latest) {
            if (!action.alive())
                return;
            const versions = await repository.documents.listVersions(action.projectId, DOMAIN_DOCUMENT_KINDS.generation_confirm, head.document_id);
            if (!action.alive())
                return;
            for (const stored of versions) {
                const problems = checkConfirmationRecord(stored.payload);
                if (problems.length)
                    throw new Error("已保存的生成授权无法恢复：" + problems[0].message);
                rememberConfirmation({
                    documentId: stored.document_id,
                    payload: stored.payload,
                    version: stored.version,
                });
            }
        }
        const plan = deps.suitePlanReader();
        const shots = plan && Array.isArray(plan.shots)
            ? plan.shots.map((shot) => shot && shot.shot_id).filter((id) => typeof id === "string")
            : [];
        for (const shotId of shots) {
            if (!action.alive())
                return;
            const attemptDocs = await repository.documents.listVersions(action.projectId, ATTEMPT_DOCUMENT_KIND, shotId);
            if (!action.alive())
                return;
            const attempts = [];
            for (const stored of attemptDocs.slice().reverse()) {
                if (checkAttemptRecord(stored.payload).length) {
                    throw new Error("已保存的尝试链无法恢复：shot " + shotId);
                }
                attempts.push({ record: stored.payload, version: stored.version });
            }
            attemptChains.set(shotId, attempts);
        }
        for (const shotId of shots) {
            if (!action.alive())
                return;
            const candidateDocs = await repository.documents.listVersions(action.projectId, CANDIDATE_DOCUMENT_KIND, shotId);
            if (!action.alive())
                return;
            const candidates = [];
            for (const stored of candidateDocs.slice().reverse()) {
                if (checkCandidateRecord(stored.payload).length) {
                    throw new Error("已保存的候选链无法恢复：shot " + shotId);
                }
                candidates.push({ record: stored.payload, version: stored.version });
            }
            candidateChains.set(shotId, candidates);
        }
    }
    // 按优先级排列的候选队列：返工（按登记倒序）在前，全部确认（含历史版本倒序）在后。
    // confirmationFor/queues 共用同一顺序，不重建原授权。
    function orderedQueues() {
        return [...reworkQueues.values()].reverse().concat([...confirmedQueues.values()].reverse().filter((queue) => !queue.documentId.startsWith(REWORK_CONFIRM_PREFIX)));
    }
    // 进入失败重试/显式另发：登记 scope + mode（旧 authorization.ts:175-176 语义，不改业务）。
    function hasCurrentQueue() {
        return Boolean(confirmed?.payload.shots.some((shot) => isConfirmedShotCurrent(confirmed, shot.shot_id)));
    }
    function shotHasCurrentQueue(shotId) {
        return Boolean(shotId && orderedQueues().some((queue) => isConfirmedShotCurrent(queue, shotId)));
    }
    // confirmationFor 复用旧 authorization.ts:179 语义：ordered 顺序 + pendingAuthorizationShots，
    // 不依赖外部 attemptChain，复用内部 pendingConfirmedShots（同一判据）。
    function confirmationForOf(shotId) {
        return orderedQueues().find((queue) => pendingConfirmedShots(queue).includes(shotId)) || null;
    }
    // queues 复用内部 pendingConfirmedShots/isConfirmedShotCurrent/confirmationTargetMatched，
    // 返回 {queue,pending,current,targetMatched} 投影；环境经 imageEnvironment(queue) 取同快照身份。
    function queuesView() {
        return orderedQueues().map((queue) => {
            const pending = pendingConfirmedShots(queue);
            return {
                queue,
                pending,
                current: pending.filter((id) => isConfirmedShotCurrent(queue, id)),
                targetMatched: confirmationTargetMatched(queue),
            };
        });
    }
    // intent 复用旧 authorization.ts:136-147：prompts.sheet + scope/mode + confirmationSnapshot。
    // 旧 prompts/environment 间接依赖由新增 deps promptsSheet/imageEnvironment 替代。
    // 冻结的 scope/mode 与授权文档/所见版本随 intent 一起交给视图；外发前 owner 重算同 scope
    // 摘要比对（见 confirmAndRun），视图不再传 readIntent/documentId/expectedVersion。
    function intentForScope(scope, mode, all) {
        const eligible = new Set(scope);
        const ids = all.shots.filter((shot) => eligible.has(shot.shot_id) && !shot.blockers.length)
            .map((shot) => shot.shot_id);
        const sheet = ids.length ? deps.promptsSheet(ids) : null;
        const identity = attemptCurrentEnvironmentIdentity(deps.imageEnvironment());
        const snapshot = sheet && identity ? snapshotOfSheet(sheet, {
            executionIdentity: identity, submissionMode: mode,
        }) : null;
        const action = deps.beginAction();
        const reworkShotId = mode === "rework" && scope.length === 1 ? scope[0] : null;
        const documentId = reworkShotId ? REWORK_CONFIRM_PREFIX + reworkShotId : CONFIRM_DOCUMENT_ID;
        const seenVersion = reworkShotId
            ? (reworkQueues.get(reworkShotId)?.version || 0)
            : (confirmed?.version || 0);
        return {
            projectId: action.projectId || "", generation: action.generation, mode,
            scope: [...scope], documentId, seenVersion, all, sheet, identity, snapshot,
        };
    }
    function intentOf(batch) {
        const all = deps.promptsSheet(null);
        if (!all)
            return null;
        const scope = authorizationScope
            || (authorizationMode === "failed_retry" ? batch.retry_queue : batch.queue);
        return intentForScope(scope, authorizationMode, all);
    }
    /** 所见摘要命令：只消费 owner 自己的 scope/mode 与当前批次队列，不接受队列/版本参数。 */
    function prepareSummary() {
        const batch = deriveBatch();
        return intentOf({ queue: batch.queue, retry_queue: batch.retry_queue });
    }
    function reworkIntentOf(shotId) {
        const all = deps.promptsSheet(null);
        const sheet = deps.promptsSheet([shotId]);
        if (!all || !sheet?.can_submit)
            throw new Error("这张图当前还有阻断，返工没有外发。");
        return intentForScope([shotId], "rework", all);
    }
    /* ------------------------------------------------------------ 传输层 */
    async function blobToBase64(blob) {
        const buffer = await blob.arrayBuffer();
        const bytes = new Uint8Array(buffer);
        let binary = "";
        const chunk = 0x8000;
        for (let index = 0; index < bytes.length; index += chunk) {
            binary += String.fromCharCode(...bytes.subarray(index, index + chunk));
        }
        return btoa(binary);
    }
    /** 提交信封里的同步结果字节：base64 → ArrayBuffer；失败返回 null（绝不伪造字节）。 */
    function base64ToBuffer(base64) {
        try {
            const binary = window.atob(base64);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++)
                bytes[i] = binary.charCodeAt(i);
            return bytes.buffer;
        }
        catch (error) {
            return null;
        }
    }
    /** 参考图字节从本地仓库读取并转 base64；读不到就不发请求（绝不发半份资料）。 */
    async function buildReferencePayload(references, pid) {
        const payload = [];
        for (const item of references) {
            const asset = await repository.assets.get(pid, item.sha256);
            if (!asset || !asset.blob) {
                throw new Error("参考图资产缺失（sha256 " + String(item.sha256).slice(0, 12) + "…），请重新上传。");
            }
            payload.push({
                role: item.role,
                media_type: asset.media_type || "image/png",
                sha256: item.sha256,
                data_base64: await blobToBase64(asset.blob),
            });
        }
        return payload;
    }
    /** 网关调用只返回「信封」；分类一律交给 domain（classifySubmitEnvelope / classifyStatusEnvelope）。 */
    async function postImageJson(path, body, record, requestHeaders) {
        const headers = requestHeaders || deps.requestHeaders("image", record?.provider?.provider_id || providerIdFromBody(body), record?.execution_identity?.credential_reference?.source);
        let response;
        try {
            response = await fetch(path, {
                method: "POST",
                headers: { "Content-Type": "application/json", ...headers },
                body: JSON.stringify(body),
            });
        }
        catch (error) {
            return { envelope: null, status: 0, transport: true };
        }
        let envelope = null;
        try {
            envelope = await response.json();
        }
        catch (error) {
            envelope = null;
        }
        if (!envelope || typeof envelope !== "object") {
            return {
                envelope: {
                    ok: false,
                    unknown: true,
                    error: {
                        family: "provider_unknown",
                        code: "RESPONSE_UNREADABLE",
                        message: "服务端返回 HTTP " + response.status + "，但响应不是约定的 JSON。",
                        retry_policy: "requires_review",
                    },
                },
                status: response.status,
                transport: false,
            };
        }
        return { envelope: envelope, status: response.status, transport: false };
    }
    /**
     * 取回候选字节：POST /api/v2/images/result。
     * 只接受 200 + image/png；服务端声明的 X-Image-Sha256 与本机重算的 sha256 必须一致，
     * 不一致就不保存（宁可没有候选，也不存不可信字节）。
     */
    async function fetchImageResultBytes(record) {
        const gate = attemptReconcileEnvironment(record, attemptProviderIdentity(record));
        if (gate.mode !== ATTEMPT_RECONCILE_MODES.by_task) {
            return {
                ok: false, reason: "environment_blocked",
                message: attemptReconcileBlockedMessage(record),
            };
        }
        let response;
        try {
            response = await fetch(IMAGE_RESULT_PATH, {
                method: "POST",
                headers: { "Content-Type": "application/json", ...deps.requestHeaders("image", record.provider.provider_id, record.execution_identity.credential_reference.source) },
                body: JSON.stringify(attemptReconcileRequestOf(record)),
            });
        }
        catch (error) {
            return {
                ok: false, reason: "transport",
                message: "取回候选时连接中断；记录保持原样，可以重试（不会重新生成）。",
            };
        }
        if (!response.ok) {
            let envelope = null;
            try {
                envelope = await response.json();
            }
            catch (error) {
                envelope = null;
            }
            let failureText = null;
            if (envelope && typeof envelope === "object" && "error" in envelope) {
                const failure = envelope.error;
                if (failure && typeof failure === "object") {
                    const family = "family" in failure ? String(failure.family) : "";
                    const code = "code" in failure ? String(failure.code) : "";
                    const detail = "message" in failure ? String(failure.message) : "";
                    failureText = "取回候选失败：" + family + " / " + code + "：" + detail;
                }
            }
            return {
                ok: false, reason: "http", status: response.status,
                message: failureText
                    ?? "取回候选失败（HTTP " + response.status + "）；记录保持原样，可以重试。",
            };
        }
        const mediaType = String(response.headers.get("content-type") || "");
        if (!mediaType.includes("image/png")) {
            return {
                ok: false, reason: "bad_media",
                message: "结果不是 PNG（" + (mediaType || "无类型") + "），候选未保存。",
            };
        }
        const buffer = await response.arrayBuffer();
        const sha = await sha256Hex(buffer);
        const declared = String(response.headers.get("x-image-sha256") || "").toLowerCase();
        if (declared && declared !== sha) {
            return {
                ok: false, reason: "hash_mismatch",
                message: "下载字节的 sha256 与服务端声明不一致，候选未保存。",
            };
        }
        return {
            ok: true, buffer: buffer, sha256: sha, media_type: "image/png",
            provider_id: response.headers.get("x-provider-id") || "",
            model_id: response.headers.get("x-model-id") || "",
            task_id: response.headers.get("x-task-id") || record.task_id,
        };
    }
    /* ------------------------------------------------------------ 候选保存 */
    /**
     * 结果字节来源解析（V2.R5.2）：
     * - 同步记录（task_id 为空、冻结 sync === true）：字节只可能在提交信封到达过一次；
     *   模块内 pendingBytesMap 以 action_id 为键暂存（会话内存，不落盘），取走即删。
     *   刷新/关页后 map 必为空 → 明确失败并给出显式补救路径（显式新建 action 或人工核对），
     *   绝不伪造字节、绝不自动把「等待候选」伪装成完成。
     * - 异步记录（有 task_id）：照旧走 result 路由拉取。
     */
    async function pickSyncOrFetchResultBytes(record, syncBytes = pendingSyncBytes) {
        const isSync = !(record.task_id)
            && record.execution_identity && record.execution_identity.sync === true;
        if (!isSync) {
            if (!isNonEmptyString(record.task_id)) {
                return { ok: false, reason: "no_result_source", message: "记录既没有 task_id 也不是同步协议，没有可拉取的结果来源。" };
            }
            return fetchImageResultBytes(record);
        }
        const queued = syncBytes.get(record.action_id);
        if (queued) {
            syncBytes.delete(record.action_id);
            const sha = await sha256Hex(queued.buffer);
            if (queued.expectSha && queued.expectSha !== sha) {
                return {
                    ok: false, reason: "sync_sha_mismatch",
                    message: "同步结果字节哈希与提交信封不一致，候选未保存；请重新生成或人工核对。",
                };
            }
            return { ok: true, buffer: queued.buffer };
        }
        return {
            ok: false, reason: "sync_bytes_missing",
            message: "同步结果是一次性字节，页面刷新后不再可取；人工核对现有结论后，显式新建 action 重新生成。",
        };
    }
    /** 把提交信封里的同步结果字节登记进内存面（action_id 序；取走即删，不持久化）。 */
    function rememberSyncBytes(actionId, buffer, expectSha, syncBytes = pendingSyncBytes) {
        if (actionId && buffer) {
            syncBytes.set(actionId, { buffer: buffer, expectSha: expectSha || null });
        }
    }
    /**
     * 候选保存核心：把一次成功的生成变成 IndexedDB 里的字节 + 元数据记录。
     * 幂等：同一 action 已有候选则跳过；字节走内容寻址，同 hash 只存一份。
     * 配额不足不产生半份记录：asset 事务失败就没有记录，界面给出可恢复指引。
     */
    async function ensureCandidateStored(shotId, options = {}) {
        const action = options.action || deps.beginAction();
        if (!action.projectId)
            return { skipped: true, reason: "no_project" };
        const pid = action.projectId;
        const flights = options.flights || candidateInFlight;
        if (flights.has(shotId))
            return { skipped: true, reason: "in_flight" };
        flights.add(shotId);
        const candidates = options.candidates || candidateChainOf(shotId);
        const record = options.record || latestAttemptOf(shotId)?.record;
        // 候选取回失败的原因必须能被界面说清（ui-contract §2.6「失败说明发生了什么、影响哪项、
        // 下一步在哪里」）：批次路径此前只对配额记录 fetchBlocked，其它取回失败原因被丢弃，
        // 用户只看到「候选还没保存」而不知道原因。空串表示当前没有未解决的取回失败。
        const note = (message) => {
            if (batchState)
                batchState.fetchNotice = message;
        };
        try {
            if (!record)
                return { skipped: true, reason: "no_attempt" };
            const decision = candidateStoreDecision({
                attempt: record, candidates,
            });
            if (!decision.needed) {
                // 旧候选的确定性报告补建归 adoption（订阅候选变化 / restore），generation 只保全候选。
                return { skipped: true, reason: decision.reason };
            }
            const fetched = options.bytes
                ? { ok: true, buffer: options.bytes }
                : await pickSyncOrFetchResultBytes(record, options.syncBytes);
            if (!fetched.ok) {
                note(fetched.message);
                return { failed: true, reason: fetched.reason, message: fetched.message };
            }
            if (fetched.buffer.byteLength > MAX_CANDIDATE_BYTES) {
                note("结果字节超过护栏上限（" + MAX_CANDIDATE_BYTES + " 字节），候选未保存。");
                return {
                    failed: true, reason: "too_large",
                    message: "结果字节超过护栏上限（" + MAX_CANDIDATE_BYTES + " 字节），候选未保存。",
                };
            }
            let dimensions;
            try {
                dimensions = parsePngDimensions(new Uint8Array(fetched.buffer));
            }
            catch (error) {
                note(messageOf(error) || "结果不是可解析的 PNG，候选未保存。");
                return {
                    failed: true, reason: "bad_bytes",
                    message: messageOf(error) || "结果不是可解析的 PNG，候选未保存。",
                };
            }
            try {
                // 候选保存是"上游已完成"的数据保全写：即使会话已切换，也按冻结项目落库。
                const asset = await repository.assets.put(pid, {
                    bytes: fetched.buffer,
                    mediaType: "image/png",
                    originalName: shotId + "-" + record.action_id.slice(0, 8) + ".png",
                    role: "candidate",
                    width: dimensions.width,
                    height: dimensions.height,
                });
                const candidate = buildCandidateRecord({
                    shotId: shotId,
                    attempt: record,
                    assetSha256: asset.sha256,
                    byteSize: asset.byte_size,
                    width: dimensions.width,
                    height: dimensions.height,
                    at: new Date().toISOString(),
                });
                const saved = await repository.saveCandidate(pid, shotId, candidate);
                // 取回/保存成功即清掉上一次失败提示：提示必须反映当前是否仍有未保存的候选。
                note("");
                if (action.alive()) {
                    rememberCandidate(shotId, { record: candidate, version: saved.version });
                }
                // 候选/资产保全成功即完成；确定性报告由 adoption 单向消费（订阅 + restore），
                // 报告补建失败不改变这里的保存成功结论，也不丢已存图片。
                return {
                    stored: true, candidate_id: record.action_id, sha256: asset.sha256,
                    width: dimensions.width, height: dimensions.height, byte_size: asset.byte_size,
                };
            }
            catch (error) {
                if (error !== null && typeof error === "object" && "code" in error && error.code === "QUOTA_EXCEEDED") {
                    note("浏览器存储空间不足，候选未保存（记录保持原样）。"
                        + "可以先导出项目或清理旧数据，再点「保存候选图片」重试。");
                    return {
                        failed: true, reason: "quota",
                        message: "浏览器存储空间不足，候选未保存（记录保持原样）。"
                            + "可以先导出项目或清理旧数据，再点「保存候选图片」重试。",
                    };
                }
                note(messageOf(error) || "候选保存失败；记录保持原样，可以重试。");
                return {
                    failed: true, reason: "storage",
                    message: messageOf(error) || "候选保存失败；记录保持原样，可以重试。",
                };
            }
        }
        finally {
            flights.delete(shotId);
            if (!options.quiet && action.alive())
                notify();
        }
    }
    /* ------------------------------------------------------------ 单张提交 */
    function authorizationUsed(confirmation, shotId) {
        return attemptChainOf(shotId).some(({ record }) => record.authorization?.document_id === confirmation.documentId
            && record.authorization?.version === confirmation.version);
    }
    /* 授权队列：已持久化授权绝不从新模型/最新 Prompt 推断（pending 按冻结链消费）。 */
    /** 队列恢复的同一环境匹配判据（执行与按钮投影共用）：冻结目标 6 键逐字一致 + 已配置。 */
    function confirmationTargetMatched(confirmation) {
        const target = confirmation?.payload?.fingerprint?.snapshot?.execution_target;
        if (!target)
            return false;
        const identity = attemptCurrentEnvironmentIdentity(deps.environmentReader(confirmation));
        if (!identity || !identity.configured)
            return false;
        const keys = ["provider_id", "model_id", "protocol", "capability_version", "credential_source", "sync"];
        return keys.every((key) => identity[key] === target[key]);
    }
    /**
     * 授权当前性：提示词版本+哈希仍对得上落库 Prompt，且快照依据（provider 档/参考图选择）
     *   未过期。执行（performSubmit 的 frozenTarget 比对）与按钮投影（resume 可点/提交可点）
     *   消费同一函数；UI 不另写逐键比对。
     */
    function isConfirmedShotCurrent(confirmation, shotId) {
        if (!confirmation || !shotId)
            return false;
        const target = confirmation.payload?.fingerprint?.snapshot?.execution_target;
        if (!target)
            return false;
        const saved = confirmation.payload.shots.find((shot) => shot.shot_id === shotId);
        if (!saved || typeof saved.prompt_version !== "number")
            return false;
        if (deps.promptEntryReader(shotId)?.version !== saved.prompt_version)
            return false;
        const entry = deps.promptEntryReader(shotId, saved.prompt_version);
        if (!entry || entry.record.hash !== saved.prompt_hash)
            return false;
        const shot = deps.suitePlanReader()?.shots?.find((item) => item.shot_id === shotId);
        if (!shot)
            return false;
        try {
            const environment = deps.environmentReader(confirmation);
            const profile = imagePromptProfile(environment);
            if (promptStaleness(entry.record, deps.promptBasisReader(shotId, profile)).stale)
                return false;
            const references = selectReferences(shot, deps.referenceSourceReader(), { maxReferences: profile.max_reference_images });
            return canonicalJson(references) === canonicalJson(entry.record.request_snapshot.references);
        }
        catch {
            return false;
        }
    }
    /** 原授权仍读精确版本；Prompt 头有意改变时先让用户决定，不改用新版内容。 */
    function pendingConfirmedShots(confirmation) {
        const snapshot = confirmation?.payload?.fingerprint?.snapshot;
        if (!snapshot?.execution_target)
            return [];
        // snapshot 来自 confirmation.payload：这条 conf 守卫只收窄类型。
        if (!confirmation || checkConfirmationRecord(confirmation.payload).length)
            return [];
        const confirmed = confirmation;
        const mode = snapshot.submission_mode;
        const currentIds = new Set((deps.suitePlanReader()?.shots || []).map(shot => shot.shot_id));
        return confirmed.payload.shots.filter(shot => {
            const id = shot.shot_id;
            if (!currentIds.has(id) || authorizationUsed(confirmed, id))
                return false;
            const latest = latestAttemptOf(id)?.record;
            if (!latest)
                return mode !== "failed_retry";
            if ([ATTEMPT_STATES.pending_submit, ATTEMPT_STATES.submitted, ATTEMPT_STATES.running].includes(latest.state)) {
                return mode === "explicit_new" && latest.state === ATTEMPT_STATES.pending_submit && !latest.task_id;
            }
            if (latest.state === ATTEMPT_STATES.unknown)
                return mode === "explicit_new";
            if (mode === "failed_retry")
                return latest.state === ATTEMPT_STATES.failed;
            if (mode === "initial")
                return false;
            return true;
        }).map(shot => shot.shot_id);
    }
    async function performSubmitAttempt(shotId, options = {}) {
        // 批次循环传入自己的冻结动作（循环的会话/项目归属）；单张提交在这里冻结。
        const action = options.action || deps.beginAction();
        if (!action.alive() || !action.projectId || !deps.suitePlanReader()) {
            return { skipped: true, reason: "not_ready" };
        }
        const pid = action.projectId;
        const flights = attemptInFlight;
        if (flights.has(shotId))
            return { skipped: true, reason: "in_flight" };
        flights.add(shotId);
        const candidateFlights = candidateInFlight;
        const syncBytes = pendingSyncBytes;
        try {
            const confirmation = options.confirmation || deps.confirmationReader(shotId);
            if (!confirmation || !pendingConfirmedShots(confirmation).includes(shotId)) {
                return { skipped: true, reason: "no_confirmation", message: "没有这张图尚未消费的原授权；先核对摘要，不会按新设置猜一个动作。" };
            }
            const confirmSnapshot = confirmation.payload.fingerprint.snapshot;
            const frozenTarget = confirmSnapshot.execution_target;
            // pendingConfirmedShots 已确认该 conf 有冻结目标：这条守卫只收窄类型。
            if (!frozenTarget)
                return { skipped: true, reason: "no_confirmation" };
            const environment = deps.environmentReader(confirmation);
            const identity = attemptCurrentEnvironmentIdentity(environment);
            if (!identity || !identity.configured) {
                return { skipped: true, reason: "credential_missing", message: "原队列的凭据未就绪；给原目标补凭据，不会改用新动作模型。" };
            }
            const targetKeys = ["provider_id", "model_id", "protocol", "capability_version", "credential_source", "sync"];
            if (targetKeys.some((key) => identity[key] !== frozenTarget[key])) {
                return { skipped: true, reason: "environment_changed", message: "原队列的目标、协议、能力版本或凭据来源不匹配；保持队列，不会切目标外发。" };
            }
            const requestHeaders = options.requestHeaders || deps.requestHeaders("image", identity.provider_id, identity.credential_source);
            const seenAction = latestAttemptOf(shotId);
            const blocking = seenAction && ["pending_submit", "submitted", "running"].includes(seenAction.record.state)
                ? seenAction.record : null;
            // 显式「放弃核对」只允许放弃没有任务编号、无法核对的 pending 记录；
            // 有 task id 的记录仍然只能先核对（防重复提交的语义不变）。
            const abandonStuck = confirmSnapshot.submission_mode === "explicit_new" && blocking !== null
                && blocking.state === ATTEMPT_STATES.pending_submit && !blocking.task_id;
            if (blocking && !abandonStuck) {
                return { skipped: true, reason: "blocked", blocking: blocking };
            }
            const authorizedPrompt = confirmation.payload.shots.find(shot => shot.shot_id === shotId);
            // pendingConfirmedShots 已确认该 shot 在授权内：这条守卫只收窄类型。
            if (!authorizedPrompt)
                return { skipped: true, reason: "no_confirmation" };
            const entry = deps.promptEntryReader(shotId, authorizedPrompt.prompt_version);
            if (!entry || entry.record.hash !== authorizedPrompt.prompt_hash) {
                return { skipped: true, reason: "no_prompt", message: "原授权绑定的 Prompt 版本或哈希缺失；不会替换为最新版。" };
            }
            const shot = deps.suitePlanReader()?.shots?.find((item) => item.shot_id === shotId);
            if (!shot)
                return { skipped: true, reason: "shot_missing" };
            const candidates = candidateChainOf(shotId);
            const profile = imagePromptProfile(environment);
            const snapshot = entry.record.request_snapshot;
            const problems = checkPromptRecord(entry.record);
            if (problems.length || canonicalJson(entry.record.compiled.provider) !== canonicalJson(profile)
                || promptStaleness(entry.record, deps.promptBasisReader(shotId, profile)).stale
                || await promptHash(snapshot, { digest: sha256Hex }) !== entry.record.hash) {
                return {
                    skipped: true, reason: "prompt_stale",
                    message: "Prompt 与有效图像能力或冻结请求不一致；请重新编译并确认，不会提交。",
                };
            }
            const source = await repository.documents.get(pid, DOMAIN_DOCUMENT_KINDS.generation_confirm, confirmation.documentId, confirmation.version);
            if (!source || canonicalJson(source.payload) !== canonicalJson(confirmation.payload)
                || await sha256Hex(new TextEncoder().encode(canonicalJson(source.payload.fingerprint.snapshot)))
                    !== source.payload.fingerprint.hash) {
                return { skipped: true, reason: "authorization_missing", message: "IndexedDB 中的原授权版本或指纹不一致，没有外发。" };
            }
            const references = selectReferences(shot, deps.referenceSourceReader(), { maxReferences: profile.max_reference_images });
            if (references.length === 0)
                return { skipped: true, reason: "no_references" };
            if (canonicalJson(references) !== canonicalJson(snapshot.references)) {
                return {
                    skipped: true, reason: "references_changed",
                    message: "参考图已变化；请重新编译并确认，不会替换已确认的参考图后直接提交。",
                };
            }
            let referencePayload;
            try {
                referencePayload = await buildReferencePayload(references, pid);
            }
            catch (error) {
                return {
                    skipped: true, reason: "reference_read_failed",
                    message: messageOf(error) || "参考图读取失败，没有提交。",
                };
            }
            if (referencePayload.some((item) => !profile.reference_media_types.includes(item.media_type))) {
                return {
                    skipped: true, reason: "reference_media_unsupported",
                    message: "参考图格式不在当前模型支持范围内；请使用受支持格式后重新确认。",
                };
            }
            const target = {
                provider_id: identity.provider_id, model_id: identity.model_id,
                protocol: identity.protocol, capability_version: identity.capability_version,
            };
            if (canonicalJson(target) !== canonicalJson(snapshot.target)) {
                return {
                    skipped: true, reason: "environment_changed",
                    message: "执行目标与已确认请求不一致；请按当前目标重新编译并确认。",
                };
            }
            if (!action.alive())
                return { skipped: true, reason: "stale_session" };
            if (promptStaleness(entry.record, deps.promptBasisReader(shotId, profile)).stale) {
                return { skipped: true, reason: "prompt_stale", message: "本图实际消费的依据已变化；原 Prompt 保留，没有外发。" };
            }
            const parameters = {
                size: snapshot.size, n: snapshot.n,
                prompt_extend: snapshot.prompt_extend, watermark: snapshot.watermark,
            };
            const actionId = newActionId();
            const at = new Date().toISOString();
            const record = buildAttemptRecord({
                actionId: actionId,
                shotId: shotId,
                prompt: { version: entry.version, hash: entry.record.hash },
                references: references,
                provider: { provider_id: identity.provider_id, model_id: identity.model_id },
                executionIdentity: attemptExecutionIdentityFromEnvironment(identity),
                authorization: { document_id: confirmation.documentId, version: confirmation.version,
                    hash: confirmation.payload.fingerprint.hash },
                parameters: parameters,
                at: at,
                note: options.explicitNew ? "用户显式新建 action" : (options.note || "用户发起生成"),
            });
            // 事务核对当前来源、所见动作及授权消费；跨标签只有预约赢家可进入外发。
            // 围栏唯一实现是 project-inputs.consumptionFence（经 fenceReader 注入）；
            // 请求一致性（basis.references）仍由 repository.checkGenerationSources 核对。
            const fence = deps.fenceReader(shotId);
            const saved = await repository.reserveGenerationAttempt({
                projectId: pid, shotId,
                confirmation: { kind: "generation_confirm", documentId: confirmation.documentId, version: confirmation.version },
                seenAction: seenAction ? { actionId: seenAction.record.action_id, version: seenAction.version } : null,
                prompt: { kind: "prompt_version", documentId: shotId, version: entry.version },
                pending: record,
                fence: {
                    sources: [...fence.sources,
                        { kind: DOMAIN_DOCUMENT_KINDS.prompt_version, documentId: shotId, version: entry.version }],
                    projectionJson: fence.projectionJson,
                    assetSha256: [...fence.assetSha256, ...references.map(item => item.sha256)],
                },
            });
            if (!action.alive())
                return { skipped: true, reason: "stale_session", record };
            if (action.alive()) {
                rememberAttempt(shotId, { record: record, version: saved.version });
                notify();
                setStatus("已登记 " + actionId + "（pending_submit），正在提交…");
            }
            const { envelope } = await postImageJson(IMAGE_SUBMIT_PATH, {
                action_id: actionId,
                prompt: snapshot.prompt,
                references: referencePayload,
                size: parameters.size,
                n: snapshot.n,
                prompt_extend: snapshot.prompt_extend,
                watermark: snapshot.watermark,
                output_format: snapshot.output_format,
                model_id: snapshot.model,
                target: { ...snapshot.target, credential_source: identity.credential_source },
            }, record, requestHeaders);
            const outcome = nextFromSubmitEnvelope(record, envelope, { at: new Date().toISOString() });
            // 旧 action 的响应按原预约保全；同 action 并发观察不得回退终态。
            const savedNext = await repository.appendAttemptObservation({
                projectId: pid, shotId, base: { actionId, version: saved.version }, via: "submit", envelope,
            });
            outcome.record = savedNext.payload;
            if (action.alive()) {
                rememberAttempt(shotId, { record: savedNext.payload, version: savedNext.version });
            }
            // 提交直接到终态（成功）时，同一步把候选字节存进 IndexedDB；失败不掩盖提交结论。
            // V2.R5.2 同步协议：信封自带结果字节；先登记进内存面（含信封声明哈希），候选保存
            // 取走时独立重算并核对；不一致则不保存。异步记录没有这个步骤。
            const syncEnvelope = readSyncEnvelope(envelope);
            if (outcome.record.state === ATTEMPT_STATES.succeeded && syncEnvelope) {
                const bytes = base64ToBuffer(syncEnvelope.imageBase64);
                if (!bytes) {
                    return { ...outcome.outcome, record: outcome.record, submitted: true,
                        message: "同步结果字节解码失败，候选未保存；请人工核对或重新生成。", candidate: null };
                }
                rememberSyncBytes(actionId, bytes, syncEnvelope.imageSha256, syncBytes);
            }
            let candidate = null;
            if (outcome.record.state === ATTEMPT_STATES.succeeded) {
                candidate = await ensureCandidateStored(shotId, {
                    quiet: true, action, record: outcome.record, candidates,
                    flights: candidateFlights, syncBytes,
                });
            }
            return { ...outcome.outcome, record: outcome.record, submitted: true, candidate: candidate };
        }
        catch (error) {
            return {
                thrown: true, state: null, error: null,
                message: messageOf(error) || "提交没有完成；已登记的身份与历史仍然保留。",
            };
        }
        finally {
            flights.delete(shotId);
            if (action.alive())
                notify();
        }
    }
    /* ------------------------------------------------------------ 单张核对 */
    async function performReconcileAttempt(shotId, options = {}) {
        // 核对只查询上游并推进已有记录；pid 必须来自冻结动作（批次循环传入）。
        const action = options.action || deps.beginAction();
        if (!action.alive() || !action.projectId)
            return { skipped: true, reason: "in_flight" };
        const pid = action.projectId;
        const flights = attemptInFlight;
        if (flights.has(shotId))
            return { skipped: true, reason: "in_flight" };
        flights.add(shotId);
        const candidateFlights = candidateInFlight;
        try {
            const latest = latestAttemptOf(shotId);
            if (!latest || !latest.record.task_id)
                return { skipped: true, reason: "no_task" };
            const candidates = candidateChainOf(shotId);
            // V2.R4.4：核对先过冻结身份判据——环境漂移或凭据来源失配时不发请求、不重提、不改记录。
            const current = attemptProviderIdentity(latest.record);
            const gate = attemptReconcileEnvironment(latest.record, current);
            if (gate.mode !== ATTEMPT_RECONCILE_MODES.by_task) {
                return {
                    skipped: true,
                    reason: gate.mode === ATTEMPT_RECONCILE_MODES.blocked_environment
                        ? "environment_blocked" : "no_identity",
                    message: attemptReconcileBlockedMessage(latest.record),
                    gate: gate,
                };
            }
            // 按冻结身份发核对请求：服务端再按同一身份核对目标（EXECUTION_IDENTITY_MISMATCH 兜底）。
            const { envelope } = await postImageJson(IMAGE_STATUS_PATH, attemptReconcileRequestOf(latest.record), latest.record);
            const outcome = nextFromStatusEnvelope(latest.record, envelope, { at: new Date().toISOString() });
            if (outcome.outcome.advanced) {
                // 核对推进是数据保全写：按冻结项目落库；会话已切换时不回写内存缓存。
                const saved = await repository.appendAttemptObservation({
                    projectId: pid, shotId, base: { actionId: latest.record.action_id, version: latest.version },
                    via: "query", envelope,
                });
                outcome.record = saved.payload;
                if (action.alive()) {
                    rememberAttempt(shotId, { record: saved.payload, version: saved.version });
                }
                // 核对推进到成功时，同一步把候选字节存进 IndexedDB；失败不掩盖核对结论。
                let candidate = null;
                if (outcome.record.state === ATTEMPT_STATES.succeeded) {
                    candidate = await ensureCandidateStored(shotId, {
                        quiet: true, action, record: outcome.record, candidates, flights: candidateFlights,
                    });
                }
                return {
                    advanced: true, task_id: latest.record.task_id, state: outcome.record.state,
                    candidate: candidate,
                };
            }
            return {
                advanced: false, task_id: latest.record.task_id, state: latest.record.state,
                note: outcome.outcome.note || "记录保持原样",
            };
        }
        catch (error) {
            return {
                failed: true,
                message: messageOf(error) || "核对没有完成，记录保持原样。",
            };
        }
        finally {
            flights.delete(shotId);
            if (action.alive())
                notify();
        }
    }
    /* ------------------------------------------------------------ 整套批次 */
    function batchStateReader() {
        return batchState;
    }
    /** 批次状态 = 套图顺序 + 每张图最新 Attempt + Prompt 就绪状态的投影；没有第二份状态。 */
    function deriveBatch() {
        const summary = deps.suiteSummaryReader();
        const shots = summary ? summary.shots : [];
        const latest = {};
        for (const item of shots) {
            const entry = latestAttemptOf(item.shot_id);
            latest[item.shot_id] = entry ? entry.record : null;
        }
        return deriveBatchState({
            shots: shots.map((item) => ({ shot_id: item.shot_id, label: item.label })),
            latestAttempts: latest,
            promptReady: (id) => Boolean(deps.promptEntryReader(id)),
            candidateStored: (id) => Boolean(latestStoredCandidateOf(id)),
        });
    }
    function stopBatch() {
        if (batchState && batchState.active)
            batchState.stopped = true;
        notify();
    }
    /**
     * 摘要授权、原确认落库及执行是一个动作；UI 只交出用户看过的那份摘要。
     * owner 内部重算同 scope 的摘要比对（当前性），stale 时返回新摘要且零外发、不自动确认。
     */
    async function confirmAndRun({ intent }) {
        const action = deps.beginAction();
        if (!action.projectId || !action.alive() || batchState?.active)
            return { skipped: true, reason: "not_ready" };
        if (!intent || intent.projectId !== action.projectId || intent.generation !== action.generation) {
            return { skipped: true, reason: "stale_session", message: "项目或会话已切换；这份摘要不再有效，没有外发。" };
        }
        const pid = action.projectId;
        const flights = authorizationInFlight;
        if (flights.has(intent.documentId))
            return { skipped: true, reason: "in_flight" };
        flights.add(intent.documentId);
        try {
            // intent / sheet / identity 缺一即没有可比对的摘要：与下面 !snapshot 走同一条拒绝。
            if (!intent.sheet || !intent.identity || !intent.identity.configured) {
                throw new Error("摘要与实际发送内容不一致，没有外发。");
            }
            const snapshot = snapshotOfSheet(intent.sheet, { executionIdentity: intent.identity, submissionMode: intent.mode });
            if (canonicalJson(snapshot) !== canonicalJson(intent.snapshot)) {
                throw new Error("摘要与实际发送内容不一致，没有外发。");
            }
            const hash = await promptHash(snapshot, { digest: sha256Hex });
            if (!action.alive())
                return { skipped: true, reason: "stale_session" };
            // 异步 hash 之后重新核对同一 scope 的当前摘要：变了就返回新摘要，不把新内容当已确认。
            let fresh = null;
            try {
                const all = deps.promptsSheet(null);
                fresh = all ? intentForScope(intent.scope, intent.mode, all) : null;
            }
            catch (error) {
                fresh = null;
            }
            if (!fresh || !fresh.snapshot || canonicalJson(fresh.snapshot) !== canonicalJson(intent.snapshot)) {
                return { stale: true, reason: "summary_changed",
                    message: "摘要已变化或当前未就绪；请核对新摘要后再确认，没有外发。", intent: fresh };
            }
            const payload = recordOfConfirmation({
                sheet: intent.sheet, hash, confirmedAt: new Date().toISOString(),
                executionIdentity: intent.identity, submissionMode: intent.mode,
            });
            const saved = await repository.documents.save(pid, {
                kind: DOMAIN_DOCUMENT_KINDS.generation_confirm, documentId: intent.documentId,
                payload, expectedVersion: intent.seenVersion,
            });
            const confirmation = {
                documentId: intent.documentId, payload, version: saved.version,
            };
            if (!action.alive())
                return { confirmation, skipped: true };
            rememberConfirmation(confirmation);
            if (!action.alive())
                return { confirmation, skipped: true };
            notify();
            await runBatch({ confirmation, action });
            return { confirmation };
        }
        finally {
            flights.delete(intent.documentId);
        }
    }
    /**
     * 同一次授权的单张、整套与返工共用队列。停止只停新增提交，不取消上游。
     */
    async function runBatch({ confirmation, action = deps.beginAction() } = {}) {
        if (!action.alive() || !action.projectId || !deps.suitePlanReader() || batchState?.active)
            return;
        clearNoticeError();
        const queue = pendingConfirmedShots(confirmation);
        if (!queue.length) {
            setNoticeError("原队列没有可新增提交的图；Unknown 只核对或明确另发，不自动重提。");
            return;
        }
        // 队列非空即保证确认与冻结目标存在：这条守卫只收窄类型。
        if (!confirmation || !confirmation.payload.fingerprint.snapshot.execution_target)
            return;
        const frozenTarget = confirmation.payload.fingerprint.snapshot.execution_target;
        const requestHeaders = deps.requestHeaders("image", frozenTarget.provider_id, frozenTarget.credential_source);
        const running = { active: true, stopped: false, halted: false, haltReason: "", fetchBlocked: "",
            fetchNotice: "", currentShotId: null, phase: "submit" };
        batchState = running;
        notify();
        let submitted = 0;
        const skipped = [];
        try {
            for (const shotId of queue) {
                if (!action.alive() || running.stopped || running.halted)
                    break;
                running.currentShotId = shotId;
                notify();
                const outcome = await performSubmitAttempt(shotId, {
                    action, confirmation, requestHeaders, note: "用户一次授权的原队列提交",
                });
                if (!action.alive())
                    return;
                if (outcome.skipped) {
                    const reason = outcome.reason || "";
                    skipped.push(shotId + "：" + (outcome.message || reason));
                    if (["credential_missing", "environment_changed", "authorization_missing", "stale_session"].includes(reason)) {
                        running.halted = true;
                        running.haltReason = outcome.message || reason;
                    }
                    continue;
                }
                submitted += 1;
                if (outcome.thrown || batchSubmitHalts(outcome)) {
                    running.halted = true;
                    running.haltReason = outcome.message || outcome.error?.message || "提交没有可确认结论";
                    break;
                }
                await pollActiveAttempts({ action });
            }
            if (action.alive()) {
                running.phase = "poll";
                running.currentShotId = null;
                await pollActiveAttempts({ action });
            }
        }
        catch (error) {
            if (action.alive()) {
                running.halted = true;
                running.haltReason = messageOf(error) || "批次执行出现异常";
            }
        }
        finally {
            if (action.alive()) {
                const finished = running;
                // 停止/暂停是合同要求可见的状态（ui-contract §3「已停止新增」）：
                // 保留一个 active=false 的快照，renderBatch 才能持续显示停止/暂停与「已提交的记录全部保留」；
                // 置 null 会让随后的 renderAttempts 通用文案立刻覆盖它（实测 #batch-progress 从未出现停止提示）。
                // 轮询判定改用 live 快照（见 pollActiveAttempts），所以这里不改变核对语义。
                batchState = { ...finished, active: false };
                notify();
                const result = deriveBatch();
                setStatus((finished?.stopped ? "已停止新增提交；" : finished?.halted ? "已暂停（" + finished.haltReason + "）；" : "本批结束；")
                    + "已提交 " + submitted + " 张；" + batchProgressText(result)
                    + (skipped.length ? "；未提交：" + skipped.join("；") : "")
                    + "。原授权、未提交队列与所有历史记录保留。");
            }
        }
    }
    /** 轮询在途记录（只查询、不重提）。批次运行中循环到没有可核对的记录为止。 */
    async function pollActiveAttempts(options = {}) {
        const intervalMs = options.intervalMs || BATCH_POLL_INTERVAL_MS;
        const maxRounds = options.maxRounds || BATCH_POLL_MAX_ROUNDS;
        const once = options.once === true;
        // 动作归属：批次传入自己的冻结动作；独立核对在这里冻结。
        const action = options.action || deps.beginAction();
        // 只有运行中的批次快照才参与停止/暂停判定：批次结束后快照仍保留（供 UI 显示停止/暂停），
        // 但不得因此让后续独立核对（reconcileOnce）变成空操作。
        const live = batchState && batchState.active ? batchState : null;
        for (let round = 0; round < maxRounds; round += 1) {
            if (live && live.halted)
                return;
            if (!action.alive())
                return;
            const state = deriveBatch();
            if (state.reconcile_queue.length === 0 && state.fetch_queue.length === 0)
                return;
            if (live) {
                live.phase = "poll";
                notify();
            }
            for (const shotId of state.reconcile_queue) {
                if (live && live.halted)
                    return;
                if (!action.alive())
                    return;
                await performReconcileAttempt(shotId, { action });
            }
            if (!action.alive())
                return;
            // 候选保存：配额受阻时记录原因并停本轮保存；核对路径不受影响。
            if (!(live && live.fetchBlocked)) {
                const fetchState = deriveBatch();
                for (const shotId of fetchState.fetch_queue) {
                    if (!action.alive())
                        return;
                    if (live) {
                        live.currentShotId = shotId;
                        live.phase = "fetch";
                        notify();
                    }
                    const stored = await ensureCandidateStored(shotId, { action });
                    if (!action.alive())
                        return;
                    if (stored && stored.failed && stored.reason === "quota") {
                        if (live) {
                            live.fetchBlocked = stored.message || "";
                            // 本地存储放不下候选时继续轮询没有意义：这一张会一直停在取回队列，
                            // 界面却显示"正在按任务编号核对"（其实没有在途任务可核对），
                            // 而提示区让用户点的手动按钮在批次结束前不可用。与其它无法继续的情形一致：
                            // 保留记录，停批次，把原因与下一步交给提示区。
                            live.halted = true;
                            live.haltReason = stored.message || "候选保存受阻";
                            return;
                        }
                        break;
                    }
                }
            }
            if (!action.alive())
                return;
            notify();
            if (once)
                return;
            // 停止只停新增提交：已提交的身份仍然各查一次，给出当前结论后不再轮询。
            if (live && live.stopped)
                return;
            const after = deriveBatch();
            if (after.reconcile_queue.length === 0 && after.fetch_queue.length === 0)
                return;
            if (round === maxRounds - 1 && live) {
                live.halted = true;
                live.haltReason = "上游长时间没有结论，已停止自动核对；记录仍在，可继续核对";
                return;
            }
            await new Promise((resolve) => {
                window.setTimeout(() => { resolve(); }, intervalMs);
            });
        }
    }
    /** 批量的「核对进行中」：所有有任务编号的在途记录各查一次，不重提。 */
    async function reconcileOnce() {
        clearNoticeError();
        const before = deriveBatch();
        if (before.reconcile_queue.length === 0) {
            setNoticeError("没有可按任务编号核对的记录。");
            return;
        }
        try {
            await pollActiveAttempts({ once: true });
        }
        catch (error) {
            setNoticeError(messageOf(error) || "核对没有完成，记录保持原样。");
            return;
        }
        const after = deriveBatch();
        setStatus("已核对 " + before.reconcile_queue.length + " 张："
            + batchProgressText(after));
    }
    return {
        // 链读取(渲染投影用)
        attemptChainOf, latestAttemptOf, allAttemptRecords,
        candidateChainOf, latestStoredCandidateOf,
        candidateForAttemptOf,
        // 执行接口(UI 只转发)
        submitAttempt: performSubmitAttempt,
        reconcileAttempt: performReconcileAttempt,
        storeCandidate: ensureCandidateStored,
        buildReferencePayload,
        // 批次
        deriveBatch, batchStateReader, runBatch, reconcileOnce,
        confirmAndRun, stopBatch,
        pendingConfirmedShots, confirmationTargetMatched, isConfirmedShotCurrent,
        rememberConfirmation, restore,
        reworkEntry: (shotId) => reworkQueues.get(shotId) || null,
        enterFailedRetry: (shotIds) => {
            authorizationScope = [...shotIds];
            authorizationMode = "failed_retry";
        },
        enterExplicitNew: (shotId) => {
            authorizationScope = [shotId];
            const state = latestAttemptOf(shotId)?.record.state;
            authorizationMode = state === ATTEMPT_STATES.succeeded ? "rework"
                : state === ATTEMPT_STATES.failed ? "failed_retry" : "explicit_new";
        },
        hasCurrent: hasCurrentQueue,
        shotHasCurrent: shotHasCurrentQueue,
        confirmationFor: confirmationForOf,
        queues: queuesView,
        prepareSummary,
        reworkIntent: reworkIntentOf,
        // 只读文案投影与投影变化通知（视图订阅；不注入 DOM 回调）
        notice: () => ({ status: noticeStatus, error: noticeError }),
        subscribe: (listener) => {
            listeners.add(listener);
            return () => { listeners.delete(listener); };
        },
        // 飞行标识（渲染投影用）
        isAttemptInFlight: (shotId) => attemptInFlight.has(shotId),
        isCandidateInFlight: (shotId) => candidateInFlight.has(shotId),
        attemptChainsNow: () => Array.from(attemptChains.entries()),
        reset,
    };
}
