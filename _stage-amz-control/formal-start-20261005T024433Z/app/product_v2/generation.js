/**
 * V2.R5.1 生成执行 Module：单张提交、按 task 核对、候选保存、单候选 VLM 复核
 * 与整套批次轮询的唯一执行权威。
 *
 * 职责（计划 §V2.R5.1）：
 *  - 先登记后外发：pending_submit 身份先落 IndexedDB，再发网关请求；
 *  - 冻结动作归属：所有状态写按 session.beginAction() 冻结的 projectId 落库；
 *  - 核对只按已保存 task id + 冻结执行身份查询，绝不重提、不偷用当前配置；
 *  - 下载/容量处理：候选字节 hash 校验、大小护栏、配额失败不产生半份记录。
 *
 * 本模块不持有 DOM、不持有编辑状态：套图/确认/Prompt/参考图等只读输入经 deps
 * 读取，渲染与文案经回调注入。workspace 只调用这里的接口并投影结果。
 */

import {
  ATTEMPT_DOCUMENT_KIND,
  ATTEMPT_RECONCILE_MODES,
  ATTEMPT_STATES,
  attemptCurrentEnvironmentIdentity,
  attemptExecutionIdentityFromEnvironment,
  attemptReconcileBlockedMessage,
  attemptReconcileEnvironment,
  attemptReconcileRequestOf,
  blockingAttemptFor,
  buildAttemptRecord,
  newActionId,
  nextFromStatusEnvelope,
  nextFromSubmitEnvelope,
  selectReferences,
  CANDIDATE_DOCUMENT_KIND,
  MAX_CANDIDATE_BYTES,
  buildCandidateRecord,
  candidateForAttempt,
  candidateStoreDecision,
  parsePngDimensions,
  REVIEW_REPORT_DOCUMENT_KIND,
  buildReviewReport,
  evaluateCandidateFindings,
  mergeVlmReview,
  reviewIsCurrent,
  reviewSummaryText,
  imagePromptProfile,
  canonicalJson,
  checkPromptRecord,
  promptHash,
  batchProgressText,
  batchSubmitHalts,
  deriveBatchState,
  isNonEmptyString,
} from "./domain/index.js";
import { sha256Hex } from "./storage/db.js";

const IMAGE_SUBMIT_PATH = "/api/v2/images/submit";
const IMAGE_STATUS_PATH = "/api/v2/images/status";
const IMAGE_RESULT_PATH = "/api/v2/images/result";
const REVIEW_PATH = "/api/v2/review/candidate";

const BATCH_POLL_INTERVAL_MS = 4000;
const BATCH_POLL_MAX_ROUNDS = 300;

export function createGenerationModule(deps) {
  const functionDeps = ["beginAction", "projectIdReader", "environmentReader",
    "suitePlanReader", "suiteSummaryReader", "promptEntryReader",
    "shotConfirmationReader", "wholeConfirmationReader", "referenceSourceReader",
    "reviewRequestBuilder", "renderAttempts", "renderBatch", "status",
    "attemptError", "clearAttemptError", "focusAfterBatch"];
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
  let reviewInFlight = new Set();
  let reviewReports = new Map();
  let batchState = null;
  // V2.R5.2 同步协议：提交信封里的结果字节暂存（action_id → {buffer, expectSha}）。
  // 明确不落盘：页面刷新/关闭即失效，候选保存走显式补救路径。取走即删。
  const pendingSyncBytes = new Map();

  function sleep(ms) {
    return new Promise((resolve) => { window.setTimeout(resolve, ms); });
  }

  /* ------------------------------------------------------------ 链与身份 */

  function attemptChainOf(shotId) {
    return attemptChains.get(shotId) || [];
  }

  function latestAttemptOf(shotId) {
    const chain = attemptChainOf(shotId);
    return chain.length ? chain[chain.length - 1] : null;
  }

  function allAttemptRecords() {
    const list = [];
    for (const chain of attemptChains.values()) {
      for (const entry of chain) list.push(entry.record);
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
    if (!latest || latest.record.state !== ATTEMPT_STATES.succeeded) return null;
    return candidateForAttempt(candidateChainOf(shotId), latest.record.action_id);
  }

  function attemptProviderIdentity() {
    // V2.R4.4：当前环境的有效图像身份由 domain 统一投影（协议/目标/模型/能力版本/凭据来源）。
    // 能力块单一数据源是 workspace 的 capabilities 读取器；读不到有效身份返回 null：
    // 提交与核对都按「目标不可用」处理，不猜身份、不用兜底冒充。
    return attemptCurrentEnvironmentIdentity(deps.environmentReader());
  }


  /** 渲染投影：某次 Attempt 之前保存的候选（存在即幂等保存已冻结的事实）。 */
  function candidateForAttemptOf(shotId, actionId) {
    return candidateForAttempt(candidateChainOf(shotId), actionId);
  }

  function reset() {
    attemptChains = new Map();
    attemptInFlight = new Set();
    candidateChains = new Map();
    candidateInFlight = new Set();
    reviewInFlight = new Set();
    reviewReports.clear();
    pendingSyncBytes.clear();
    batchState = null;
  }

  function loadAttemptChain(shotId, entries) {
    attemptChains.set(shotId, entries);
  }

  function loadCandidateChain(shotId, entries) {
    candidateChains.set(shotId, entries);
  }

  function setReviewReport(candidateId, entry) {
    reviewReports.set(candidateId, entry);
  }

  /* ------------------------------------------------------------ 传输层 */

  async function blobToBase64(blob) {
    const buffer = await blob.arrayBuffer();
    const bytes = new Uint8Array(buffer);
    let binary = "";
    const chunk = 0x8000;
    for (let index = 0; index < bytes.length; index += chunk) {
      binary += String.fromCharCode.apply(null, bytes.subarray(index, index + chunk));
    }
    return btoa(binary);
  }

  /** 提交信封里的同步结果字节：base64 → ArrayBuffer；失败返回 null（绝不伪造字节）。 */
  function base64ToBuffer(base64) {
    try {
      const binary = window.atob(base64);
      const bytes = new Uint8Array(binary.length);
      for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
      return bytes.buffer;
    } catch (error) {
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
  async function postImageJson(path, body) {
    let response;
    try {
      response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch (error) {
      return { envelope: null, status: 0, transport: true };
    }
    let envelope = null;
    try {
      envelope = await response.json();
    } catch (error) {
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
    const gate = attemptReconcileEnvironment(record, attemptProviderIdentity());
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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(attemptReconcileRequestOf(record)),
      });
    } catch (error) {
      return {
        ok: false, reason: "transport",
        message: "取回候选时连接中断；记录保持原样，可以重试（不会重新生成）。",
      };
    }
    if (!response.ok) {
      let envelope = null;
      try {
        envelope = await response.json();
      } catch (error) {
        envelope = null;
      }
      const failure = envelope && envelope.error ? envelope.error : null;
      return {
        ok: false, reason: "http", status: response.status,
        message: failure
          ? "取回候选失败：" + failure.family + " / " + failure.code + "：" + failure.message
          : "取回候选失败（HTTP " + response.status + "）；记录保持原样，可以重试。",
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
      task_id: response.headers.get("x-task-id") || taskId,
    };
  }

  /* ------------------------------------------------------------ 复核报告 */

  /**
   * 候选的确定性审核报告（V2.5.1）：绑定 candidate_id + 合同版本 + sha256；
   * 评估或保存失败都不影响候选本身（界面显示报告缺失，下次打开项目会补建）。
   * pid 必须来自动作冻结的 projectId：报告只写发起动作的项目。
   */
  async function ensureReviewReport(shotId, candidate, bytes, pid) {
    if (!pid) return null;
    const existing = reviewReports.get(candidate.candidate_id);
    if (existing && reviewIsCurrent(existing.report, candidate)) return existing;
    let view = bytes || null;
    if (!view) {
      const asset = await repository.assets.get(pid, candidate.asset_sha256);
      if (asset && asset.blob instanceof Blob) {
        view = new Uint8Array(await asset.blob.arrayBuffer());
      }
    }
    const suitePlan = deps.suitePlanReader();
    const shot = (suitePlan && Array.isArray(suitePlan.shots) ? suitePlan.shots : [])
      .find((item) => item && item.shot_id === shotId);
    const deterministic = evaluateCandidateFindings({
      candidate: candidate,
      bytes: view,
      roleId: shot ? shot.role_id : null,
    });
    // 合同版本或规则升级后重建报告：同一候选字节上的 VLM 复核块整体带过去；
    // 旧规则与当前注册表不兼容时丢弃复核部分（回到「VLM 未检查」），不伪造结论。
    const previous = existing && existing.report && existing.report.vlm
      && existing.report.vlm.asset_sha256 === candidate.asset_sha256 ? existing.report : null;
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
      } catch (error) {
        report = null;
      }
    }
    if (!report) {
      report = buildReviewReport({
        candidate: candidate, findings: deterministic, at: new Date().toISOString(),
      });
    }
    try {
      const saved = await repository.documents.save(pid, {
        kind: REVIEW_REPORT_DOCUMENT_KIND, documentId: candidate.candidate_id, payload: report,
      });
      reviewReports.set(candidate.candidate_id, { report: report, version: saved.version });
    } catch (error) {
      // 报告保存失败不改写候选：内存里保留这次评估，界面可见，下次打开项目重试。
      reviewReports.set(candidate.candidate_id, { report: report, version: 0 });
    }
    return reviewReports.get(candidate.candidate_id);
  }

  /* ------------------------------------------------------------ VLM 复核 */

  /**
   * V2.5.2：对目标 Shot 的最新候选执行一次 VLM 复核。
   * 失败信封与传输失败都投影成 Unknown（保留分类原因）；不自动采纳、不阻塞人工审核。
   */
  async function reviewCandidate(shotId) {
    const action = deps.beginAction();
    if (!action.projectId) return { skipped: true, reason: "no_project" };
    if (reviewInFlight.has(shotId)) return { skipped: true, reason: "in_flight" };
    reviewInFlight.add(shotId);
    if (action.alive()) deps.renderAttempts();
    try {
      const stored = latestStoredCandidateOf(shotId);
      const candidate = stored && stored.record ? stored.record : stored;
      if (!candidate) return { skipped: true, reason: "no_candidate" };
      const current = reviewReports.get(candidate.candidate_id);
      if (!current || !reviewIsCurrent(current.report, candidate)) {
        await ensureReviewReport(shotId, candidate, null, action.projectId);
      }
      if (!action.alive()) return { skipped: true, reason: "stale_session" };
      let request;
      try {
        request = await deps.reviewRequestBuilder(shotId, candidate);
      } catch (error) {
        return {
          failed: true, reason: "request_invalid",
          message: (error && error.message) || "复核请求无法构建。",
        };
      }
      if (!action.alive()) return { skipped: true, reason: "stale_session" };
      let envelope = null;
      try {
        const response = await fetch(REVIEW_PATH, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(request),
        });
        envelope = await response.json().catch(() => null);
      } catch (error) {
        envelope = null;
      }
      if (!envelope || typeof envelope !== "object") {
        envelope = {
          ok: false, unknown: true,
          error: {
            family: "internal", code: "REVIEW_TRANSPORT",
            message: "复核服务没有返回可解析的结果（服务可能未启动）。",
            retry_policy: "requires_review",
          },
        };
      }
      const entry = reviewReports.get(candidate.candidate_id);
      let merged = null;
      try {
        merged = mergeVlmReview({
          report: entry.report, candidate: candidate, review: envelope,
          at: new Date().toISOString(),
        });
      } catch (error) {
        return {
          failed: true, reason: "merge_invalid",
          message: (error && error.message) || "复核结果无法合并进报告。",
        };
      }
      try {
        const saved = await repository.documents.save(action.projectId, {
          kind: REVIEW_REPORT_DOCUMENT_KIND, documentId: candidate.candidate_id, payload: merged,
        });
        if (action.alive()) {
          reviewReports.set(candidate.candidate_id, { report: merged, version: saved.version });
        }
      } catch (error) {
        if (action.alive()) {
          reviewReports.set(candidate.candidate_id, { report: merged, version: 0 });
        }
      }
      return {
        ok: envelope.ok === true,
        outcome: merged.vlm.outcome,
        candidate_id: candidate.candidate_id,
        summary: reviewSummaryText(merged),
      };
    } finally {
      reviewInFlight.delete(shotId);
      if (action.alive()) deps.renderAttempts();
    }
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
  async function pickSyncOrFetchResultBytes(record) {
    const isSync = !(record.task_id)
      && record.execution_identity && record.execution_identity.sync === true;
    if (!isSync) {
      if (!isNonEmptyString(record.task_id)) {
        return { ok: false, reason: "no_result_source", message: "记录既没有 task_id 也不是同步协议，没有可拉取的结果来源。" };
      }
      return fetchImageResultBytes(record);
    }
    const queued = pendingSyncBytes.get(record.action_id);
    if (queued) {
      pendingSyncBytes.delete(record.action_id);
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
  function rememberSyncBytes(actionId, buffer, expectSha) {
    if (actionId && buffer) {
      pendingSyncBytes.set(actionId, { buffer: buffer, expectSha: expectSha || null });
    }
  }

  /**
   * 候选保存核心：把一次成功的生成变成 IndexedDB 里的字节 + 元数据记录。
   * 幂等：同一 action 已有候选则跳过；字节走内容寻址，同 hash 只存一份。
   * 配额不足不产生半份记录：asset 事务失败就没有记录，界面给出可恢复指引。
   */
  async function ensureCandidateStored(shotId, options = {}) {
    const action = options.action || deps.beginAction();
    if (!action.projectId) return { skipped: true, reason: "no_project" };
    if (candidateInFlight.has(shotId)) return { skipped: true, reason: "in_flight" };
    candidateInFlight.add(shotId);
    try {
      const latest = latestAttemptOf(shotId);
      if (!latest) return { skipped: true, reason: "no_attempt" };
      const record = latest.record;
      const decision = candidateStoreDecision({
        attempt: record, candidates: candidateChainOf(shotId),
      });
      if (!decision.needed) {
        if (decision.reason === "already_stored" && decision.candidate) {
          const existing = decision.candidate.record || decision.candidate;
          try {
            await ensureReviewReport(shotId, existing, null, action.projectId);
          } catch (error) {
            // 旧候选的报告补建是尽力而为，不改变幂等语义。
          }
        }
        return { skipped: true, reason: decision.reason };
      }
      const fetched = options.bytes
        ? { ok: true, buffer: options.bytes }
        : await pickSyncOrFetchResultBytes(record);
      if (!fetched.ok) {
        return { failed: true, reason: fetched.reason, message: fetched.message };
      }
      if (fetched.buffer.byteLength > MAX_CANDIDATE_BYTES) {
        return {
          failed: true, reason: "too_large",
          message: "结果字节超过护栏上限（" + MAX_CANDIDATE_BYTES + " 字节），候选未保存。",
        };
      }
      let dimensions;
      try {
        dimensions = parsePngDimensions(new Uint8Array(fetched.buffer));
      } catch (error) {
        return {
          failed: true, reason: "bad_bytes",
          message: (error && error.message) || "结果不是可解析的 PNG，候选未保存。",
        };
      }
      let reviewSummary = null;
      let asset;
      try {
        // 候选保存是"上游已完成"的数据保全写：即使会话已切换，也按冻结项目落库。
        asset = await repository.assets.put(action.projectId, {
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
        const saved = await repository.documents.save(action.projectId, {
          kind: CANDIDATE_DOCUMENT_KIND, documentId: shotId, payload: candidate,
        });
        if (action.alive()) {
          rememberCandidate(shotId, { record: candidate, version: saved.version });
        }
        try {
          const reviewEntry = await ensureReviewReport(shotId, candidate,
            new Uint8Array(fetched.buffer), action.projectId);
          reviewSummary = reviewEntry ? reviewSummaryText(reviewEntry.report) : null;
        } catch (error) {
          reviewSummary = null;
        }
      } catch (error) {
        if (error && error.code === "QUOTA_EXCEEDED") {
          return {
            failed: true, reason: "quota",
            message: "浏览器存储空间不足，候选未保存（记录保持原样）。"
              + "可以先导出项目或清理旧数据，再点「保存候选图片」重试。",
          };
        }
        return {
          failed: true, reason: "storage",
          message: (error && error.message) || "候选保存失败；记录保持原样，可以重试。",
        };
      }
      return {
        stored: true, candidate_id: record.action_id, sha256: asset.sha256,
        width: dimensions.width, height: dimensions.height, byte_size: asset.byte_size,
        review: reviewSummary,
      };
    } finally {
      candidateInFlight.delete(shotId);
      if (!options.quiet && action.alive()) deps.renderAttempts();
    }
  }

  /* ------------------------------------------------------------ 单张提交 */

  async function performSubmitAttempt(shotId, options = {}) {
    // 批次循环传入自己的冻结动作（循环的会话/项目归属）；单张提交在这里冻结。
    const action = options.action || deps.beginAction();
    if (!action.alive() || !action.projectId || !deps.suitePlanReader()) {
      return { skipped: true, reason: "not_ready" };
    }
    if (attemptInFlight.has(shotId)) return { skipped: true, reason: "in_flight" };
    attemptInFlight.add(shotId);
    try {
      if (!deps.shotConfirmationReader(shotId)) {
        return { skipped: true, reason: "no_confirmation" };
      }
      const blocking = blockingAttemptFor(allAttemptRecords(), shotId);
      // 显式「放弃核对」只允许放弃没有任务编号、无法核对的 pending 记录；
      // 有 task id 的记录仍然只能先核对（防重复提交的语义不变）。
      const abandonStuck = Boolean(options.explicitNew) && Boolean(blocking)
        && blocking.state === ATTEMPT_STATES.pending_submit && !blocking.task_id;
      if (blocking && !abandonStuck) {
        return { skipped: true, reason: "blocked", blocking: blocking };
      }
      const entry = deps.promptEntryReader(shotId);
      if (!entry) return { skipped: true, reason: "no_prompt" };
      const shot = deps.suitePlanReader().shots.find((item) => item.shot_id === shotId);
      if (!shot) return { skipped: true, reason: "shot_missing" };
      const profile = imagePromptProfile(deps.environmentReader());
      const snapshot = entry.record.request_snapshot;
      const problems = checkPromptRecord(entry.record);
      if (problems.length || canonicalJson(entry.record.compiled.provider) !== canonicalJson(profile)
          || await promptHash(snapshot, { digest: sha256Hex }) !== entry.record.hash) {
        return {
          skipped: true, reason: "prompt_stale",
          message: "Prompt 与有效图像能力或冻结请求不一致；请重新编译并确认，不会提交。",
        };
      }
      const references = selectReferences(shot, deps.referenceSourceReader(),
        { maxReferences: profile.max_reference_images });
      if (references.length === 0) return { skipped: true, reason: "no_references" };
      if (canonicalJson(references) !== canonicalJson(snapshot.references)) {
        return {
          skipped: true, reason: "references_changed",
          message: "参考图已变化；请重新编译并确认，不会替换已确认的参考图后直接提交。",
        };
      }
      let referencePayload;
      try {
        referencePayload = await buildReferencePayload(references, action.projectId);
      } catch (error) {
        return {
          skipped: true, reason: "reference_read_failed",
          message: (error && error.message) || "参考图读取失败，没有提交。",
        };
      }
      if (referencePayload.some((item) => !profile.reference_media_types.includes(item.media_type))) {
        return {
          skipped: true, reason: "reference_media_unsupported",
          message: "参考图格式不在当前模型支持范围内；请使用受支持格式后重新确认。",
        };
      }
      const identity = attemptProviderIdentity();
      if (!identity) {
        return {
          skipped: true, reason: "environment_unknown",
          message: "提交前读不到有效的图像环境身份（协议/目标/模型/能力版本/凭据来源）；"
            + "先确认服务端可用，再提交。不猜身份。",
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
      if (!action.alive() || !deps.shotConfirmationReader(shotId)) {
        return { skipped: true, reason: "no_confirmation" };
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
        parameters: parameters,
        at: at,
        note: options.explicitNew ? "用户显式新建 action" : (options.note || "用户发起生成"),
      });
      // 先按冻结项目登记（pending_submit），再发请求；会话切换不回收这条登记。
      const saved = await repository.documents.save(action.projectId, {
        kind: ATTEMPT_DOCUMENT_KIND, documentId: shotId, payload: record,
      });
      if (action.alive()) {
        rememberAttempt(shotId, { record: record, version: saved.version });
        deps.renderAttempts();
        deps.status("已登记 " + actionId + "（pending_submit），正在提交…");
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
        target: snapshot.target,
      });
      const outcome = nextFromSubmitEnvelope(record, envelope, { at: new Date().toISOString() });
      // 提交结果的数据保全写：任务已发给上游，记录必须落库，界面不再驱动。
      const savedNext = await repository.documents.save(action.projectId, {
        kind: ATTEMPT_DOCUMENT_KIND, documentId: shotId, payload: outcome.record,
      });
      if (action.alive()) {
        rememberAttempt(shotId, { record: outcome.record, version: savedNext.version });
      }
      // 提交直接到终态（成功）时，同一步把候选字节存进 IndexedDB；失败不掩盖提交结论。
      // V2.R5.2 同步协议：信封自带结果字节；先登记进内存面（含信封声明哈希），候选保存
      // 取走时独立重算并核对；不一致则不保存。异步记录没有这个步骤。
      if (outcome.record.state === ATTEMPT_STATES.succeeded && envelope
          && typeof envelope.image_base64 === "string") {
        const bytes = base64ToBuffer(envelope.image_base64);
        if (!bytes) {
          return { ...outcome.outcome, record: outcome.record, submitted: true,
                   message: "同步结果字节解码失败，候选未保存；请人工核对或重新生成。", candidate: null };
        }
        rememberSyncBytes(actionId, bytes,
          typeof envelope.image_sha256 === "string" ? envelope.image_sha256.toLowerCase() : null);
      }
      let candidate = null;
      if (outcome.record.state === ATTEMPT_STATES.succeeded) {
        candidate = await ensureCandidateStored(shotId, { quiet: true });
      }
      return { ...outcome.outcome, record: outcome.record, submitted: true, candidate: candidate };
    } catch (error) {
      return {
        thrown: true, state: null, error: null,
        message: (error && error.message) || "提交没有完成；已登记的身份与历史仍然保留。",
      };
    } finally {
      attemptInFlight.delete(shotId);
      if (action.alive()) deps.renderAttempts();
    }
  }

  /* ------------------------------------------------------------ 单张核对 */

  async function performReconcileAttempt(shotId, options = {}) {
    // 核对只查询上游并推进已有记录；pid 必须来自冻结动作（批次循环传入）。
    const action = options.action || deps.beginAction();
    if (!action.alive() || !action.projectId) return { skipped: true, reason: "in_flight" };
    if (attemptInFlight.has(shotId)) return { skipped: true, reason: "in_flight" };
    attemptInFlight.add(shotId);
    try {
      const latest = latestAttemptOf(shotId);
      if (!latest || !latest.record.task_id) return { skipped: true, reason: "no_task" };
      // V2.R4.4：核对先过冻结身份判据——环境漂移或凭据来源失配时不发请求、不重提、不改记录。
      const current = attemptProviderIdentity();
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
      const { envelope } = await postImageJson(IMAGE_STATUS_PATH,
        attemptReconcileRequestOf(latest.record));
      const outcome = nextFromStatusEnvelope(latest.record, envelope,
        { at: new Date().toISOString() });
      if (outcome.outcome.advanced) {
        // 核对推进是数据保全写：按冻结项目落库；会话已切换时不回写内存缓存。
        const saved = await repository.documents.save(action.projectId, {
          kind: ATTEMPT_DOCUMENT_KIND, documentId: shotId, payload: outcome.record,
        });
        if (action.alive()) {
          rememberAttempt(shotId, { record: outcome.record, version: saved.version });
        }
        // 核对推进到成功时，同一步把候选字节存进 IndexedDB；失败不掩盖核对结论。
        let candidate = null;
        if (outcome.record.state === ATTEMPT_STATES.succeeded) {
          candidate = await ensureCandidateStored(shotId, { quiet: true });
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
    } catch (error) {
      return {
        failed: true,
        message: (error && error.message) || "核对没有完成，记录保持原样。",
      };
    } finally {
      attemptInFlight.delete(shotId);
      if (action.alive()) deps.renderAttempts();
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
    if (batchState && batchState.active) batchState.stopped = true;
    deps.renderBatch();
  }

  /**
   * 整套批次 / 批量重试（options.retry）：按套图顺序先提交，再按已保存 task id
   * 轮询推进。停止只停新增提交：不撤销、不覆盖、不删除任何已有记录。
   */
  async function runBatch(options = {}) {
    const retryMode = options.retry === true;
    if (!deps.projectIdReader() || !deps.suitePlanReader() || (batchState && batchState.active)) return;
    const action = deps.beginAction();
    deps.clearAttemptError();
    if (retryMode && !deps.wholeConfirmationReader()) {
      deps.attemptError("生成前确认缺失或已过期：先回到「生成前确认」重新确认，再重试。");
      return;
    }
    const plan = deriveBatch();
    if (retryMode) {
      if (plan.retry_queue.length === 0) {
        deps.attemptError("没有明确失败的图可重试。");
        return;
      }
    } else if (plan.queue.length === 0 && plan.fetch_queue.length === 0) {
      deps.attemptError("没有待提交的图；可以核对进行中、重试失败的图或保存候选。");
      return;
    } else if (plan.queue.length > 0 && !deps.wholeConfirmationReader()) {
      deps.attemptError("生成前确认缺失或已过期：先回到「生成前确认」重新确认，再整套生成。");
      return;
    }
    const queue = retryMode ? plan.retry_queue : plan.queue;
    batchState = {
      active: true, stopped: false, halted: false, haltReason: "", fetchBlocked: "",
      currentShotId: null, phase: "submit",
    };
    deps.renderAttempts();
    let submitted = 0;
    try {
      for (const shotId of queue) {
        // 会话切换/关闭：立即停止新增提交；已提交任务的结果仍会被保全落库。
        if (!action.alive()) break;
        if (batchState.stopped || batchState.halted) break;
        if (!retryMode && !deps.wholeConfirmationReader()) {
          batchState.halted = true;
          batchState.haltReason = "生成前确认已过期";
          break;
        }
        batchState.currentShotId = shotId;
        deps.renderBatch();
        const outcome = await performSubmitAttempt(shotId, retryMode
          ? { explicitNew: true, note: "批次重试失败图", action }
          : { note: "整套生成：批次提交", action });
        if (outcome.skipped) continue;
        submitted += 1;
        if (outcome.thrown) {
          batchState.halted = true;
          batchState.haltReason = outcome.message || "提交没有完成";
          break;
        }
        if (batchSubmitHalts(outcome)) {
          batchState.halted = true;
          batchState.haltReason = (outcome.error && outcome.error.message)
            || (retryMode ? "系统性提交错误" : "系统性提交错误（继续提交会产生更多未知记录）");
          break;
        }
        // 上游按账号限流（百炼 429 Throttling.RateQuota：未受理、可重试）：整套生成逐张推进，
        // 让本张先出结论再提交下一张，避免突发提交把可重试的限流变成成片失败。
        if (!retryMode) await pollActiveAttempts({ action });
      }
      if (action.alive()) {
        batchState.phase = "poll";
        batchState.currentShotId = null;
        await pollActiveAttempts({ action });
      }
    } catch (error) {
      if (action.alive() && batchState) {
        batchState.halted = true;
        batchState.haltReason = (error && error.message)
          || (retryMode ? "重试执行出现异常" : "批次执行出现异常");
      }
    } finally {
      if (action.alive()) {
        const finished = batchState;
        batchState = null;
        deps.renderAttempts();
        const finalState = deriveBatch();
        if (retryMode) {
          deps.status(finished && finished.halted
            ? "重试已停止新增提交（" + finished.haltReason + "）：已提交的记录全部保留。"
            : "重试结束：本批提交 " + submitted + " 张；" + batchProgressText(finalState));
        } else if (finished && finished.halted) {
          deps.status("批次已停止新增提交（" + finished.haltReason
            + "）：本批提交 " + submitted + " 张，已有记录全部保留。");
        } else if (finished && finished.stopped) {
          deps.status("批次已停止：本批提交 " + submitted
            + " 张，已有记录全部保留；可继续核对或继续生成剩余。");
        } else {
          deps.status("批次结束：" + batchProgressText(finalState));
        }
        deps.focusAfterBatch();
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
    for (let round = 0; round < maxRounds; round += 1) {
      if (batchState && batchState.halted) return;
      if (!action.alive()) return;
      const state = deriveBatch();
      if (state.reconcile_queue.length === 0 && state.fetch_queue.length === 0) return;
      if (batchState) { batchState.phase = "poll"; deps.renderBatch(); }
      for (const shotId of state.reconcile_queue) {
        if (batchState && batchState.halted) return;
        if (!action.alive()) return;
        await performReconcileAttempt(shotId, { action });
      }
      // 候选保存：配额受阻时记录原因并停本轮保存；核对路径不受影响。
      if (!(batchState && batchState.fetchBlocked)) {
        const fetchState = deriveBatch();
        for (const shotId of fetchState.fetch_queue) {
          if (batchState) {
            batchState.currentShotId = shotId;
            batchState.phase = "fetch";
            deps.renderBatch();
          }
          if (!action.alive()) return;
          const stored = await ensureCandidateStored(shotId, { action });
          if (stored && stored.failed && stored.reason === "quota") {
            if (batchState) batchState.fetchBlocked = stored.message;
            break;
          }
        }
      }
      if (!action.alive()) return;
      deps.renderAttempts();
      if (once) return;
      // 停止只停新增提交：已提交的身份仍然各查一次，给出当前结论后不再轮询。
      if (batchState && batchState.stopped) return;
      const after = deriveBatch();
      if (after.reconcile_queue.length === 0 && after.fetch_queue.length === 0) return;
      if (round === maxRounds - 1 && batchState) {
        batchState.halted = true;
        batchState.haltReason = "上游长时间没有结论，已停止自动核对；记录仍在，可继续核对";
        return;
      }
      await sleep(intervalMs);
    }
  }

  /** 批量的「核对进行中」：所有有任务编号的在途记录各查一次，不重提。 */
  async function reconcileOnce() {
    deps.clearAttemptError();
    const before = deriveBatch();
    if (before.reconcile_queue.length === 0) {
      deps.attemptError("没有可按任务编号核对的记录。");
      return;
    }
    try {
      await pollActiveAttempts({ once: true });
    } catch (error) {
      deps.attemptError((error && error.message) || "核对没有完成，记录保持原样。");
      return;
    }
    const after = deriveBatch();
    deps.status("已核对 " + before.reconcile_queue.length + " 张："
      + batchProgressText(after));
  }

  return {
    // 链读取(渲染投影用)
    attemptChainOf, latestAttemptOf, allAttemptRecords,
    candidateChainOf, latestStoredCandidateOf,
    candidateForAttemptOf,
    loadAttemptChain, loadCandidateChain, setReviewReport,
    reviewReportOf: (candidateId) => reviewReports.get(candidateId) || null,
    reviewReportsNow: () => Array.from(reviewReports.entries()),
    // 执行接口(UI 只转发)
    submitAttempt: performSubmitAttempt,
    reconcileAttempt: performReconcileAttempt,
    storeCandidate: ensureCandidateStored,
    ensureReviewReport, buildReferencePayload, reviewCandidate,
    // 批次
    deriveBatch, batchStateReader, runBatch, reconcileOnce,
    runRetryOnce: () => runBatch({ retry: true }),
    stopBatch,
    // 飞行标识（渲染投影用）
    isAttemptInFlight: (shotId) => attemptInFlight.has(shotId),
    isCandidateInFlight: (shotId) => candidateInFlight.has(shotId),
    isReviewInFlight: (shotId) => reviewInFlight.has(shotId),
    attemptChainsNow: () => Array.from(attemptChains.entries()),
    reset,
  };
}
