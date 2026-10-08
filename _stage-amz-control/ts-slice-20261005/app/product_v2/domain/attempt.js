/**
 * Product V2 生成 Attempt：一次生成的身份、状态机与恢复判据（V2.4.2，计划 §9.11）。
 *
 * 唯一权威：记录形状、合法状态迁移、恢复判据、防重复与「基于旧版本」标记都在本文件。
 * 复用而不是重写：
 *  - 参考图角色复用 intake.js 的 REFERENCE_ROLES，条数上限复用 provider 合同；
 *  - 上游错误词表（family / retry_policy）是 §9.10 网关信封在前端的投影，权威是
 *    src/providers/v2_errors.py；两边一致性由 V2.4.2 验证器现场核对；
 *  - 散列与时间戳都由调用方注入，本层不写第二种散列，也不自己取当前时间。
 * 本层是纯函数：不写存储、不发请求、不调用模型。它只回答「这个响应等于哪个状态」，
 * 界面负责投影与保存，绝不在界面里各写一套判断。
 */

import { DOMAIN_ERROR_CODES, illegal, invalid } from "./errors.js";
import {
  DOMAIN_DOCUMENT_KINDS,
  SLOT_ID_PATTERN,
  checkSchemaVersion,
  isIsoTimestamp,
  isNonEmptyString,
  isPlainObject,
  isSha256Hex,
  pushProblem,
} from "./shared.js";
import { REFERENCE_ROLES } from "./intake.js";
import { canonicalJson } from "./prompt.js";

export const ATTEMPT_SCHEMA_VERSION = 2;
export const ATTEMPT_DOCUMENT_KIND = DOMAIN_DOCUMENT_KINDS.generation_attempt;
export const ATTEMPT_ACTION_ID_PATTERN = /^[A-Za-z0-9._:-]{8,64}$/;
export const ATTEMPT_TASK_ID_PATTERN = /^[A-Za-z0-9._:-]{1,256}$/;
export const ATTEMPT_SIZE_PATTERN = /^[0-9]{1,4}\*[0-9]{1,4}$/;
export const MAX_ATTEMPT_REFERENCES = 3;
export const MAX_ATTEMPT_N = 4;

/**
 * 冻结执行身份（V2.R4.4）：已提交任务保留「协议 / 目标 / 模型 / 能力版本 / 凭据引用」，
 * 换设置后仍按原身份核对；不猜目标，不偷用当前配置查询旧任务。
 *  - protocol：图像网关请求契约版本（服务端 IMAGE_CONTRACT_VERSION，例如 "v2.4.1"）；
 *  - capability_version：服务端能力声明版本（IMAGES_CAPABILITY_VERSION，正整数；R5.2 接入
 *    第二协议 Adapter 时会前移，旧任务因此按原能力版本核对）；
 *  - credential_reference：只记录来源标签（byok / default / none / test_double），
 *    **密钥值本身永不入记录**（凭据轮换不使无关 Prompt 过期：该块也不进 request_snapshot）。
 * 同版本新旧任务按各自冻结身份核对；schema_version < 2 的历史记录没有身份块，
 * 不做 legacy 映射（按计划 §2.3 显式拒绝自动核对，不补造身份）。
 */
export const ATTEMPT_EXECUTION_IDENTITY_SCHEMA_VERSION = 1;
export const ATTEMPT_PROTOCOL_PATTERN = /^v[0-9A-Za-z._-]{1,40}$/;
export const ATTEMPT_CREDENTIAL_SOURCES = Object.freeze([
  "byok", "default", "none", "test_double", "env",
]);

/** 状态词表：pending_submit 必须在发起请求之前落库。 */
export const ATTEMPT_STATES = Object.freeze({
  pending_submit: "pending_submit",
  submitted: "submitted",
  running: "running",
  succeeded: "succeeded",
  failed: "failed",
  unknown: "unknown",
});

export const ATTEMPT_ACTIVE_STATES = Object.freeze(["pending_submit", "submitted", "running"]);
export const ATTEMPT_TERMINAL_STATES = Object.freeze(["succeeded", "failed", "unknown"]);

export const ATTEMPT_STATE_LABELS = Object.freeze({
  pending_submit: "已登记，等待提交",
  submitted: "已提交，等待上游",
  running: "上游处理中",
  succeeded: "已成功",
  failed: "已失败",
  unknown: "结果未知，需要核对",
});

/** 恢复方式：none = 不需要核对；by_task = 可按已保存 task id 核对；
 *  blocked_no_identity = 没有身份（含历史记录），只能显式新建；
 *  blocked_environment = 有身份但当前环境漂移/缺凭据，只能恢复环境后按原身份核对。 */
export const ATTEMPT_RECONCILE_MODES = Object.freeze({
  none: "none",
  by_task: "by_task",
  blocked_no_identity: "blocked_no_identity",
  blocked_environment: "blocked_environment",
});

/**
 * 合法迁移表：值 = 允许的来源。
 *  - submit：提交响应（可能一步到 submitted / failed / unknown）
 *  - query：按已保存 task id 查询（不重提，因此不会回到 submitted）
 *  - user：用户显式新建（只允许创建 pending_submit）
 */
export const ATTEMPT_TRANSITIONS = Object.freeze({
  pending_submit: Object.freeze({
    submitted: Object.freeze(["submit"]),
    failed: Object.freeze(["submit"]),
    unknown: Object.freeze(["submit"]),
    // 上游可能在提交响应里直接给出确定结果（快速完成 / 立即拒绝）；那是结论，不是跳步。
    succeeded: Object.freeze(["submit"]),
  }),
  submitted: Object.freeze({
    running: Object.freeze(["submit", "query"]),
    succeeded: Object.freeze(["query"]),
    failed: Object.freeze(["submit", "query"]),
    unknown: Object.freeze(["submit", "query"]),
  }),
  running: Object.freeze({
    succeeded: Object.freeze(["query"]),
    failed: Object.freeze(["query"]),
    unknown: Object.freeze(["query"]),
  }),
  succeeded: Object.freeze({}),
  failed: Object.freeze({}),
  unknown: Object.freeze({
    running: Object.freeze(["query"]),
    succeeded: Object.freeze(["query"]),
    failed: Object.freeze(["query"]),
  }),
});

/** 上游错误词表（§9.10）：权威在 src/providers/v2_errors.py，本文件只是前端投影。 */
export const ATTEMPT_ERROR_FAMILIES = Object.freeze([
  "input_rejected", "provider_failed", "provider_unknown", "internal",
]);
export const ATTEMPT_RETRY_POLICIES = Object.freeze(["retryable", "requires_review", "fatal"]);
export const ATTEMPT_UNKNOWN_FAMILY = "provider_unknown";

/** 没有信封（连接中断、读取失败）时的合成归口：结果未知，绝不自动重提。 */
export function transportUnknownError(message) {
  return {
    family: ATTEMPT_UNKNOWN_FAMILY,
    code: "TRANSPORT_UNKNOWN",
    message: isNonEmptyString(message) ? message : "请求没有拿到响应，无法判断上游是否受理。",
    retry_policy: "requires_review",
  };
}

export function canAttemptTransition(from, to, via = null) {
  if (from === null || from === undefined) {
    return to === ATTEMPT_STATES.pending_submit && (via === null || via === undefined || via === "user");
  }
  const allowed = ATTEMPT_TRANSITIONS[from];
  if (!allowed || !Object.prototype.hasOwnProperty.call(allowed, to)) return false;
  if (via === null || via === undefined) return true;
  return allowed[to].includes(via);
}

export function attemptStateLabel(state) {
  return ATTEMPT_STATE_LABELS[state] || "未知状态";
}

/** 用户显式新建 action 的稳定标识；随机源由调用方注入，便于测试确定性。 */
export function newActionId(randomSource = null) {
  const uuid = typeof randomSource === "function"
    ? String(randomSource())
    : (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function"
      ? globalThis.crypto.randomUUID() : "");
  const compact = uuid.replace(/[^A-Za-z0-9]/g, "");
  if (compact.length < 5) {
    invalid("生成 action_id 需要可用的随机源（crypto.randomUUID）。");
  }
  const value = "act-" + compact;
  if (!ATTEMPT_ACTION_ID_PATTERN.test(value)) invalid("生成的 action_id 不合法：" + value);
  return value;
}

/* ------------------------------------------------------------ 记录形状 */

/**
 * 记录校验：形状 + 词表 + 迁移链。返回问题列表（空数组 = 合法），不抛异常。
 * 迁移链是强约束：`state` 必须等于 `change_log` 的终点，`updated_at` 必须等于最后一次迁移时间。
 */
export function checkAttemptRecord(record) {
  const problems = [];
  if (!isPlainObject(record)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "Attempt 记录必须是对象。");
    return problems;
  }
  checkSchemaVersion(record, ATTEMPT_SCHEMA_VERSION, problems, "$");
  if (!isNonEmptyString(record.action_id) || !ATTEMPT_ACTION_ID_PATTERN.test(record.action_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.action_id",
      "action_id 必须是 8–64 位的稳定标识。");
  }
  if (!isNonEmptyString(record.shot_id) || !SLOT_ID_PATTERN.test(record.shot_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shot_id",
      "shot_id 必须是合法 Shot 标识。");
  }
  const state = record.state;
  if (!Object.prototype.hasOwnProperty.call(ATTEMPT_STATES, String(state))) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.state",
      "状态不在词表内：" + String(state));
  }
  const prompt = record.prompt;
  if (!isPlainObject(prompt)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.prompt",
      "缺少 prompt{version,hash}。");
  } else {
    if (!Number.isInteger(prompt.version) || prompt.version < 1) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.prompt.version",
        "prompt.version 必须是正整数。");
    }
    if (!isSha256Hex(prompt.hash)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.prompt.hash",
        "prompt.hash 必须是 64 位小写十六进制。");
    }
  }
  if (record.authorization !== undefined) {
    const authorization = record.authorization;
    if (!isPlainObject(authorization) || !isNonEmptyString(authorization.document_id)
        || !Number.isInteger(authorization.version) || authorization.version < 1
        || !isSha256Hex(authorization.hash)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.authorization",
        "生成授权来源需要原确认文档标识、版本和指纹哈希。");
    }
  }
  const references = record.references;
  if (!Array.isArray(references) || references.length < 1
      || references.length > MAX_ATTEMPT_REFERENCES) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.references",
      "参考图必须是 1.." + MAX_ATTEMPT_REFERENCES + " 项。");
  } else {
    references.forEach((item, index) => {
      const path = "$.references[" + index + "]";
      if (!isPlainObject(item)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "参考图项必须是对象。");
        return;
      }
      if (!REFERENCE_ROLES.includes(item.role)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".role",
          "参考图角色不在词表内：" + String(item.role));
      }
      if (!isSha256Hex(item.sha256)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".sha256",
          "参考图 sha256 不合法。");
      }
    });
  }
  const provider = record.provider;
  if (!isPlainObject(provider) || !isNonEmptyString(provider.provider_id)
      || provider.provider_id.length > 120 || !isNonEmptyString(provider.model_id)
      || provider.model_id.length > 120) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.provider",
      "provider 必须记录 {provider_id, model_id}。");
  }
  const identity = record.execution_identity;
  if (!isPlainObject(identity)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.execution_identity",
      "缺少冻结执行身份 execution_identity（协议/能力版本/凭据引用）。");
  } else {
    if (identity.schema_version !== ATTEMPT_EXECUTION_IDENTITY_SCHEMA_VERSION) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.execution_identity.schema_version",
        "执行身份块版本不认识：" + String(identity.schema_version));
    }
    if (typeof identity.protocol !== "string"
        || !ATTEMPT_PROTOCOL_PATTERN.test(identity.protocol)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.execution_identity.protocol",
        "执行身份协议版本必须是 v 开头的契约版本号（如 v2.4.1）。");
    }
    if (!Number.isInteger(identity.capability_version) || identity.capability_version < 1) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.execution_identity.capability_version",
        "执行身份 capability_version 必须是正整数。");
    }
    const reference = identity.credential_reference;
    if (!isPlainObject(reference) || !ATTEMPT_CREDENTIAL_SOURCES.includes(reference.source)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.execution_identity.credential_reference",
        "credential_reference.source 必须在词表内：" + ATTEMPT_CREDENTIAL_SOURCES.join("/") + "。");
    }
  }
  const parameters = record.parameters;
  if (!isPlainObject(parameters)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.parameters",
      "缺少 parameters{size,n,prompt_extend,watermark}。");
  } else {
    if (typeof parameters.size !== "string" || !ATTEMPT_SIZE_PATTERN.test(parameters.size)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.parameters.size",
        "参数 size 必须是「宽*高」。");
    }
    if (!Number.isInteger(parameters.n) || parameters.n < 1 || parameters.n > MAX_ATTEMPT_N) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.parameters.n",
        "参数 n 必须是 1.." + MAX_ATTEMPT_N + " 的整数。");
    }
    if (typeof parameters.prompt_extend !== "boolean") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.parameters.prompt_extend",
        "参数 prompt_extend 必须是布尔值。");
    }
    if (typeof parameters.watermark !== "boolean") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.parameters.watermark",
        "参数 watermark 必须是布尔值。");
    }
  }
  const hasTaskId = record.task_id !== null && record.task_id !== undefined;
  if (hasTaskId) {
    if (!isNonEmptyString(record.task_id) || !ATTEMPT_TASK_ID_PATTERN.test(String(record.task_id))) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.task_id", "task_id 不合法。");
    }
  } else if (state === ATTEMPT_STATES.submitted || state === ATTEMPT_STATES.running) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.task_id",
      "已提交或运行中的 Attempt 必须带 task_id。");
  }
  if (record.request_id !== null && record.request_id !== undefined
      && !isNonEmptyString(record.request_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.request_id",
      "request_id 只能是 null 或非空字符串。");
  }
  const hasError = record.error !== null && record.error !== undefined;
  if (hasError) {
    const error = record.error;
    const shapeOk = isPlainObject(error)
      && ATTEMPT_ERROR_FAMILIES.includes(error.family)
      && ATTEMPT_RETRY_POLICIES.includes(error.retry_policy)
      && isNonEmptyString(error.code) && isNonEmptyString(error.message);
    if (!shapeOk) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.error",
        "error 必须是 {family,code,message,retry_policy} 且词表合法。");
    }
  }
  const errorExpected = state === ATTEMPT_STATES.failed || state === ATTEMPT_STATES.unknown;
  if (errorExpected && !hasError) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.error",
      "failed / unknown 必须留下失败原因。");
  }
  if (!errorExpected && hasError) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.error",
      "只有 failed / unknown 才带 error，其余状态必须清空。");
  }
  if (!isIsoTimestamp(record.created_at)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.created_at",
      "created_at 必须是 ISO 时间戳。");
  }
  if (!isIsoTimestamp(record.updated_at)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.updated_at",
      "updated_at 必须是 ISO 时间戳。");
  }
  const changeLog = record.change_log;
  if (!Array.isArray(changeLog) || changeLog.length === 0) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.change_log",
      "change_log 至少要有创建那一条。");
  } else {
    let previous = undefined;
    changeLog.forEach((entry, index) => {
      const path = "$.change_log[" + index + "]";
      if (!isPlainObject(entry)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "迁移项必须是对象。");
        return;
      }
      if (!isIsoTimestamp(entry.at)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".at",
          "迁移时间必须是 ISO 时间戳。");
      }
      if (index === 0) {
        if (entry.from !== null) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".from",
            "第一条迁移必须从 null 开始。");
        }
      } else if (entry.from !== previous) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".from",
          "迁移链断裂：上一条到 " + String(previous) + "，这条从 " + String(entry.from) + " 开始。");
      }
      if (!canAttemptTransition(entry.from, entry.to, entry.via)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path,
          "非法迁移：" + String(entry.from) + " → " + String(entry.to) + "（via " + String(entry.via) + "）。");
      }
      previous = entry.to;
    });
    if (previous !== state) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.state",
        "state 必须等于迁移链终点 " + String(previous) + "。");
    }
    const last = changeLog[changeLog.length - 1];
    if (isPlainObject(last) && last.at !== record.updated_at) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.updated_at",
        "updated_at 必须等于最后一次迁移时间。");
    }
    const first = changeLog[0];
    if (isPlainObject(first) && first.at !== record.created_at) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.created_at",
        "created_at 必须等于第一条迁移时间。");
    }
  }
  return problems;
}

/* ------------------------------------------------------------ 创建与推进 */

/**
 * 创建一条 Attempt：**一律以 pending_submit 落库**，且在发起请求之前完成写入。
 * 函数本身不写存储：调用方先 `documents.save(...)`，拿到版本后再发请求。
 * 执行身份（execution_identity）必须在创建时冻结：换设置后仍按原身份核对，创建时刻之后的
 * 任何环境变化都不回写这条记录。
 */
export function buildAttemptRecord({
  actionId, shotId, prompt, references, provider, parameters, executionIdentity = null, authorization = null,
  taskId = null, requestId = null, error = null, at, note = "用户显式发起生成",
} = {}) {
  const referencesList = Array.isArray(references)
    ? references.map((item) => ({ role: item && item.role, sha256: item && item.sha256 }))
    : references;
  const identity = isPlainObject(executionIdentity)
    ? {
      schema_version: ATTEMPT_EXECUTION_IDENTITY_SCHEMA_VERSION,
      protocol: executionIdentity.protocol,
      capability_version: executionIdentity.capabilityVersion,
      credential_reference: { source: executionIdentity.credentialSource },
      // V2.R5.2：同步协议在响应里一次性给结果字节、没有 task id；缺席 = 异步（默认）。
      sync: executionIdentity.sync === true,
    }
    : null;
  const record = {
    schema_version: ATTEMPT_SCHEMA_VERSION,
    action_id: actionId,
    shot_id: shotId,
    state: ATTEMPT_STATES.pending_submit,
    prompt: isPlainObject(prompt) ? { version: prompt.version, hash: prompt.hash } : prompt,
    references: referencesList,
    provider: isPlainObject(provider)
      ? { provider_id: provider.provider_id, model_id: provider.model_id }
      : provider,
    execution_identity: identity,
    ...(authorization ? { authorization: {
      document_id: authorization.document_id, version: authorization.version, hash: authorization.hash,
    } } : {}),
    parameters: isPlainObject(parameters)
      ? {
        size: parameters.size, n: parameters.n,
        prompt_extend: parameters.prompt_extend, watermark: parameters.watermark,
      }
      : parameters,
    task_id: taskId,
    request_id: requestId,
    error: error,
    created_at: at,
    updated_at: at,
    change_log: [{ at: at, via: "user", from: null, to: ATTEMPT_STATES.pending_submit, note: note }],
  };
  const problems = checkAttemptRecord(record);
  if (problems.length > 0) invalid(problems[0].message, { problems: problems });
  return record;
}

/**
 * 推进一条 Attempt：只允许迁移表内的边，并且**必须由调用方给出时间与来源**。
 * 没有 task id 的 Unknown 不允许再动（禁止自动重提）；只能新建一条 action。
 */
export function advanceAttempt(record, options = {}) {
  const existing = checkAttemptRecord(record);
  if (existing.length > 0) {
    invalid("Attempt 记录不合法，不能推进：" + existing[0].message, { problems: existing });
  }
  const state = options.state;
  const via = options.via;
  const at = options.at;
  if (!Object.prototype.hasOwnProperty.call(ATTEMPT_STATES, String(state))) {
    invalid("推进目标状态不在词表内：" + String(state));
  }
  if (!["submit", "query", "user"].includes(via)) {
    invalid("推进来源必须是 submit / query / user。");
  }
  if (!isIsoTimestamp(at)) {
    invalid("推进必须带 ISO 时间戳（由调用方注入，便于复核）。");
  }
  if (!canAttemptTransition(record.state, state, via)) {
    illegal("非法状态迁移：" + record.state + " → " + String(state) + "（via " + String(via) + "）。",
      { from: record.state, to: state, via: via });
  }
  if (record.state === ATTEMPT_STATES.unknown && !isNonEmptyString(record.task_id)) {
    illegal("没有 task id 的 Unknown 不能核对，只能显式新建 action。",
      { from: record.state, action_id: record.action_id });
  }
  const nextError = (state === ATTEMPT_STATES.failed || state === ATTEMPT_STATES.unknown)
    ? (options.error === undefined ? record.error : options.error)
    : null;
  const next = {
    ...record,
    state: state,
    task_id: options.taskId === undefined ? record.task_id : options.taskId,
    request_id: options.requestId === undefined ? record.request_id : options.requestId,
    error: nextError,
    updated_at: at,
    change_log: [...record.change_log, {
      at: at, via: via, from: record.state, to: state,
      note: options.note === undefined ? null : options.note,
    }],
  };
  const problems = checkAttemptRecord(next);
  if (problems.length > 0) invalid("推进后的记录不合法：" + problems[0].message, { problems: problems });
  if (canonicalJson(record.execution_identity) !== canonicalJson(next.execution_identity)) {
    invalid("推进不得改写冻结执行身份：换设置后已提交任务仍按原身份核对。");
  }
  return next;
}

/* ------------------------------------------------------------ 冻结执行身份（V2.R4.4） */

/** 读取记录上的冻结执行身份块；历史记录（schema_version < 2）返回 null，不做 legacy 补造。 */
export function attemptExecutionIdentityOf(record) {
  if (!isPlainObject(record)) return null;
  if (record.schema_version !== ATTEMPT_SCHEMA_VERSION) return null;
  return isPlainObject(record.execution_identity) ? record.execution_identity : null;
}

/**
 * 当前环境的有效图像身份（提交/核对时刻用这个快照；当前读数不是历史记录的身份）。
 * 输入是 capabilities 的 images 块（签名见 V2.4.1：contract / provider / default_trial）。
 * provider 缺失或身份字段不完整时返回 null，调用方按「环境目标不可用」处理，不猜身份。
 */
export function attemptCurrentEnvironmentIdentity(imagesBlock) {
  if (!isPlainObject(imagesBlock)) return null;
  const provider = isPlainObject(imagesBlock.provider) ? imagesBlock.provider : null;
  if (!provider) return null;
  if (!isNonEmptyString(provider.provider_id) || !isNonEmptyString(provider.model_id)) {
    return null;
  }
  if (typeof imagesBlock.contract !== "string"
      || !ATTEMPT_PROTOCOL_PATTERN.test(imagesBlock.contract)) {
    return null;
  }
  if (!Number.isInteger(provider.capability_version) || provider.capability_version < 1) {
    return null;
  }
  const source = provider.credential_reference && isPlainObject(provider.credential_reference)
    ? provider.credential_reference.source
    : provider.credential_source;
  if (!ATTEMPT_CREDENTIAL_SOURCES.includes(source)) return null;
  const capabilities = isPlainObject(provider.capabilities) ? provider.capabilities : {};
  return {
    protocol: imagesBlock.contract,
    provider_id: provider.provider_id,
    model_id: provider.model_id,
    capability_version: provider.capability_version,
    credential_source: source,
    configured: provider.configured !== false,
    // V2.R5.2：同步协议适配器（火山方舟 flash）的提交响应自带结果字节，没有 task id。
    // 服务端 capabilities 的形状是 provider.capabilities.sync_tasks；异步 provider 没有这个
    // 键 → false，语义与历史记录一致。
    sync: capabilities.sync_tasks === true,
  };
}

/** 把当前环境身份转成「冻结进记录」的 executionIdentity 输入（提交前用）。 */
export function attemptExecutionIdentityFromEnvironment(current) {
  if (!isPlainObject(current)) {
    invalid("提交前必须读到有效的图像环境身份（协议/目标/模型/能力版本/凭据来源）。");
  }
  return {
    protocol: current.protocol,
    capabilityVersion: current.capability_version,
    credentialSource: current.credential_source,
    sync: current.sync === true,
  };
}

/**
 * 提交/核对前判据：冻结身份 vs 当前环境的核对模式。
 *  - by_task：目标与凭据来源与冻结身份一致 → 允许按 task id 核对；
 *  - blocked_environment：目标能力漂移（协议/目标/模型/能力版本任一变化）或凭据来源失配
 *    （credential_missing）→ 不发请求、不重提、不改记录；恢复条件在 message。
 *  - blocked_no_identity：历史记录没有身份块（schema_version < 2）→ 不补造、不映射。
 */
export function attemptReconcileEnvironment(record, current) {
  const frozen = attemptExecutionIdentityOf(record);
  if (!frozen) {
    return {
      mode: ATTEMPT_RECONCILE_MODES.blocked_no_identity,
      reasons: ["identity_unknown"],
      frozen: null,
    };
  }
  if (!isNonEmptyString(record.task_id)) {
    return {
      mode: ATTEMPT_RECONCILE_MODES.blocked_no_identity,
      reasons: ["task_unknown"],
      frozen: frozen,
    };
  }
  const provider = isPlainObject(record.provider) ? record.provider : {};
  const reasons = [];
  if (!isPlainObject(current)) {
    reasons.push("target_unavailable");
  } else {
    if (current.protocol !== frozen.protocol
        || current.provider_id !== provider.provider_id
        || current.model_id !== provider.model_id
        || current.capability_version !== frozen.capability_version) {
      reasons.push("target_unavailable");
    }
    if (current.configured === false || current.credential_source !== frozen.credential_reference.source) {
      reasons.push("credential_missing");
    }
  }
  if (reasons.length > 0) {
    return {
      mode: ATTEMPT_RECONCILE_MODES.blocked_environment,
      reasons: reasons,
      frozen: frozen,
      applied_target: current ? {
        protocol: current.protocol, provider_id: current.provider_id,
        model_id: current.model_id, capability_version: current.capability_version,
        credential_source: current.credential_source,
      } : null,
    };
  }
  return { mode: ATTEMPT_RECONCILE_MODES.by_task, reasons: [], frozen: frozen };
}

/** 核对被阻塞时的界面话术：说清原身份、当前环境与恢复条件；不假称已取消、不引导重提。 */
export function attemptReconcileBlockedMessage(record) {
  const provider = isPlainObject(record.provider) ? record.provider : {};
  const task = isNonEmptyString(record.task_id) ? "（task " + record.task_id + "）" : "";
  if (!attemptExecutionIdentityOf(record)) {
    return "这条 Attempt（" + String(record.action_id || "") + "）是历史记录，没有冻结执行身份，"
      + "不会给它补造身份或按当前设置核对；如需继续生成，请显式新建 action。";
  }
  return "已提交任务" + task + "的执行身份与当前环境不一致，保持原状态不动："
    + "期望协议 " + String(record.execution_identity.protocol)
    + "、目标 " + String(provider.provider_id || "?") + "/" + String(provider.model_id || "?")
    + "、能力版本 v" + String(record.execution_identity.capability_version || "?")
    + "。恢复条件：提供原目标的同一来源凭据（"
    + String(record.execution_identity.credential_reference.source)
    + "），并保持原协议和能力版本，再按任务编号核对。新动作模型不需要切回，"
    + "不会重新提交，也不会把其他目标的结果归到这条记录。";
}

/** 核对请求体：服务端按冻结身份核目标（EXECUTION_IDENTITY_MISMATCH 的前端侧来源）。 */
export function attemptReconcileRequestOf(record) {
  const frozen = attemptExecutionIdentityOf(record);
  if (!frozen) {
    invalid("历史 Attempt 没有执行身份，不构造目标核对请求（不补造、不猜测）。");
  }
  const provider = isPlainObject(record.provider) ? record.provider : {};
  const credentialSource = isPlainObject(frozen.credential_reference)
    ? frozen.credential_reference.source
    : null;
  if (!isNonEmptyString(credentialSource)) {
    invalid("冻结执行身份缺少凭据来源，不构造目标核对请求（不补造、不猜测）。");
  }
  return {
    task_id: isNonEmptyString(record.task_id) ? record.task_id : null,
    target: {
      provider_id: provider.provider_id,
      model_id: provider.model_id,
      protocol: frozen.protocol,
      capability_version: frozen.capability_version,
      credential_source: credentialSource,
    },
  };
}

/* ------------------------------------------------------------ 恢复判据 */

function attemptOrder(record) {
  return String((record && (record.updated_at || record.created_at)) || "");
}

/** 同一个 Shot 的最新 Attempt；append-only 版本链里最后写的那条。 */
export function latestAttemptFor(attempts, shotId) {
  const list = (Array.isArray(attempts) ? attempts : [])
    .filter((item) => isPlainObject(item) && item.shot_id === shotId)
    .sort((left, right) => attemptOrder(left).localeCompare(attemptOrder(right)));
  return list.length ? list[list.length - 1] : null;
}

/** 正在进行的 Attempt（pending_submit / submitted / running）；它存在时按钮必须不可用。 */
export function activeAttemptFor(attempts, shotId) {
  const latest = latestAttemptFor(attempts, shotId);
  if (!latest) return null;
  return ATTEMPT_ACTIVE_STATES.includes(latest.state) ? latest : null;
}

/** 提交入口的防重复判据：返回 null = 可以新建 action，否则返回拦路的 Attempt。 */
export function blockingAttemptFor(attempts, shotId) {
  return activeAttemptFor(attempts, shotId);
}

export function attemptNeedsReconcile(record) {
  if (!isPlainObject(record)) return false;
  return record.state === ATTEMPT_STATES.unknown || record.state === ATTEMPT_STATES.pending_submit;
}

export function attemptReconcileMode(record) {
  if (!isPlainObject(record)) return ATTEMPT_RECONCILE_MODES.none;
  if (record.state === ATTEMPT_STATES.succeeded || record.state === ATTEMPT_STATES.failed) {
    return ATTEMPT_RECONCILE_MODES.none;
  }
  if (!isNonEmptyString(record.task_id)) return ATTEMPT_RECONCILE_MODES.blocked_no_identity;
  // 历史记录（schema_version < 2 或缺身份块）不能按原身份核对：不补造、不按当前设置猜。
  if (!attemptExecutionIdentityOf(record)) return ATTEMPT_RECONCILE_MODES.blocked_no_identity;
  return ATTEMPT_RECONCILE_MODES.by_task;
}

/** 「基于旧版本」标记：Prompt 前进（重编译或人工编辑）后旧 Attempt 仍然是历史，只是不再是当前依据。 */
export function attemptPromptStaleness(attempt, currentPrompt) {
  if (!isPlainObject(attempt) || !isPlainObject(attempt.prompt)) return null;
  const attemptVersion = attempt.prompt.version;
  const attemptHash = attempt.prompt.hash;
  if (!isPlainObject(currentPrompt) || !Number.isInteger(currentPrompt.version)
      || !isSha256Hex(currentPrompt.hash)) {
    return {
      stale: false, reason_code: "CURRENT_PROMPT_UNKNOWN",
      attempt_version: attemptVersion, current_version: null,
    };
  }
  if (currentPrompt.version !== attemptVersion || currentPrompt.hash !== attemptHash) {
    return {
      stale: true, reason_code: "PROMPT_MOVED",
      attempt_version: attemptVersion, current_version: currentPrompt.version,
    };
  }
  return {
    stale: false, reason_code: "CURRENT",
    attempt_version: attemptVersion, current_version: currentPrompt.version,
  };
}

/* ------------------------------------------------ 网关信封 → Attempt 状态 */

function readTask(envelope) {
  return isPlainObject(envelope) && isPlainObject(envelope.task) ? envelope.task : null;
}

function readIdentity(task) {
  const provider = isPlainObject(task && task.provider) ? task.provider : {};
  return {
    task_id: isNonEmptyString(task && task.task_id) ? String(task.task_id) : null,
    request_id: isNonEmptyString(task && task.request_id) ? String(task.request_id) : null,
    provider_id: isNonEmptyString(provider.provider_id) ? String(provider.provider_id) : null,
    model_id: isNonEmptyString(provider.model_id) ? String(provider.model_id) : null,
    // V2.R5.2：同步协议标志只从响应本身读；异步 provider 的响应没有这个键 → false。
    sync: task && task.sync === true,
  };
}

function normalizedError(raw, defaults) {
  const source = isPlainObject(raw) ? raw : {};
  return {
    family: ATTEMPT_ERROR_FAMILIES.includes(source.family) ? source.family : defaults.family,
    code: isNonEmptyString(source.code) ? String(source.code) : defaults.code,
    message: isNonEmptyString(source.message) ? String(source.message) : defaults.message,
    retry_policy: ATTEMPT_RETRY_POLICIES.includes(source.retry_policy)
      ? source.retry_policy : defaults.retry_policy,
  };
}

function unknownError(raw, defaults) {
  const error = normalizedError(raw, defaults);
  error.family = ATTEMPT_UNKNOWN_FAMILY;
  error.retry_policy = "requires_review";
  return error;
}

/**
 * 提交响应 → Attempt 状态。界面不许另写一套判断。
 *  - 拿到任务身份（PENDING/RUNNING）→ submitted；上游说成功/失败就直接落终态；
 *  - 没拿到任务身份、连接中断、无法解析 → unknown（绝不当作失败，也绝不自动重提）；
 *  - 请求本身被拒（input_rejected）与未配置密钥 → failed，因为这一定没有提交到上游。
 */
export function classifySubmitEnvelope(envelope) {
  const env = isPlainObject(envelope) ? envelope : null;
  const task = readTask(env);
  if (task && env.ok === true) {
    const identity = readIdentity(task);
    const status = String(task.status || "").toUpperCase();
    // V2.R5.2 同步协议：提交即终态；结果字节在同一个信封里，浏览器侧独立复核哈希。
    // 这里只承认不可伪造的形状：task_id 为空 + task.sync 为 true + 明确的状态值。
    if (!task.task_id && task.sync === true) {
      if (status === "SUCCEEDED") {
        return { ...identity, state: ATTEMPT_STATES.succeeded, error: null,
                 note: "同步结果已返回" };
      }
      if (status === "FAILED" || status === "CANCELED") {
        return {
          ...identity, state: ATTEMPT_STATES.failed,
          note: "同步生成明确未成功（" + status + "）",
          error: normalizedError(null, {
            family: "provider_failed", code: "SYNC_FAILED",
            message: "同步生成没有成功（" + status + "）。", retry_policy: "fatal",
          }),
        };
      }
      return {
        ...identity, state: ATTEMPT_STATES.unknown,
        note: "同步响应状态无法识别：" + status,
        error: unknownError(null, {
          family: ATTEMPT_UNKNOWN_FAMILY, code: "SYNC_STATUS_UNRECOGNIZED",
          message: "同步响应的状态无法识别；结果未知，不要自动重提。",
          retry_policy: "requires_review",
        }),
      };
    }
    if (!identity.task_id) {
      return {
        ...identity, state: ATTEMPT_STATES.unknown, note: "提交响应缺少任务编号",
        error: unknownError(null, {
          family: ATTEMPT_UNKNOWN_FAMILY, code: "TASK_ID_MISSING",
          message: "上游没有返回任务编号，无法核对这次提交；不要自动重提。",
          retry_policy: "requires_review",
        }),
      };
    }
    if (status === "PENDING" || status === "RUNNING") {
      return { ...identity, state: ATTEMPT_STATES.submitted, error: null,
               note: "上游已受理（" + status + "）" };
    }
    if (status === "SUCCEEDED") {
      return { ...identity, state: ATTEMPT_STATES.succeeded, error: null, note: "上游返回 SUCCEEDED" };
    }
    if (status === "FAILED" || status === "CANCELED") {
      return {
        ...identity, state: ATTEMPT_STATES.failed,
        note: "上游明确未成功（" + status + "）",
        error: normalizedError({
          family: "provider_failed", code: "TASK_" + status,
          message: isNonEmptyString(task.error) ? String(task.error) : "上游任务没有成功（" + status + "）。",
          retry_policy: "retryable",
        }, {
          family: "provider_failed", code: "TASK_FAILED",
          message: "上游任务没有成功。", retry_policy: "retryable",
        }),
      };
    }
    return {
      ...identity, state: ATTEMPT_STATES.unknown,
      note: "上游状态无法识别：" + status,
      error: unknownError(null, {
        family: ATTEMPT_UNKNOWN_FAMILY, code: "TASK_STATUS_UNRECOGNIZED",
        message: "上游返回了无法识别的任务状态：" + status + "；先核对，不要自动重提。",
        retry_policy: "requires_review",
      }),
    };
  }
  const raw = env ? env.error : null;
  const family = isPlainObject(raw) ? raw.family : null;
  const code = isPlainObject(raw) ? String(raw.code || "") : "";
  if ((env && env.unknown === true) || family === ATTEMPT_UNKNOWN_FAMILY) {
    return {
      task_id: null, request_id: null, provider_id: null, model_id: null,
      state: ATTEMPT_STATES.unknown, note: "提交结果未确认",
      error: unknownError(raw, {
        family: ATTEMPT_UNKNOWN_FAMILY, code: "SUBMIT_UNKNOWN",
        message: "提交结果没有确认，无法判断上游是否受理；不要自动重提。",
        retry_policy: "requires_review",
      }),
    };
  }
  if (family === "input_rejected") {
    return {
      task_id: null, request_id: null, provider_id: null, model_id: null,
      state: ATTEMPT_STATES.failed, note: "请求被拒绝，没有调用上游",
      error: normalizedError(raw, {
        family: "input_rejected", code: "INPUT_INVALID",
        message: "请求不符合图像网关契约；没有调用模型。", retry_policy: "fatal",
      }),
    };
  }
  if (family === "provider_failed") {
    return {
      task_id: null, request_id: null, provider_id: null, model_id: null,
      state: ATTEMPT_STATES.failed, note: "上游明确拒绝或失败",
      error: normalizedError(raw, {
        family: "provider_failed", code: "PROVIDER_FAILED",
        message: "上游明确失败；这次提交没有结果。", retry_policy: "retryable",
      }),
    };
  }
  if (family === "internal" && code === "PROVIDER_NOT_CONFIGURED") {
    return {
      task_id: null, request_id: null, provider_id: null, model_id: null,
      state: ATTEMPT_STATES.failed, note: "provider 未配置，请求没有发出",
      error: normalizedError(raw, {
        family: "internal", code: "PROVIDER_NOT_CONFIGURED",
        message: "图像 provider 不可用（未配置或依赖缺失）；这次没有提交。",
        retry_policy: "fatal",
      }),
    };
  }
  return {
    task_id: null, request_id: null, provider_id: null, model_id: null,
    state: ATTEMPT_STATES.unknown,
    note: family === "internal" ? "服务端没有给出结论" : "没有拿到可用响应",
    error: unknownError(raw, {
      family: ATTEMPT_UNKNOWN_FAMILY, code: "SUBMIT_OUTCOME_UNKNOWN",
      message: "提交结果没有确认，无法判断上游是否受理；先核对，不要自动重提。",
      retry_policy: "requires_review",
    }),
  };
}

/**
 * 查询响应 → Attempt 状态。查询永远不会「重提」：没有结论时 state 为 null（记录不推进）。
 */
export function classifyStatusEnvelope(envelope) {
  const env = isPlainObject(envelope) ? envelope : null;
  const task = readTask(env);
  if (task && env.ok === true) {
    const identity = readIdentity(task);
    const status = String(task.status || "").toUpperCase();
    if (status === "PENDING") {
      return { ...identity, state: ATTEMPT_STATES.submitted, error: null, note: "上游仍在排队" };
    }
    if (status === "RUNNING") {
      return { ...identity, state: ATTEMPT_STATES.running, error: null, note: "上游处理中" };
    }
    if (status === "SUCCEEDED") {
      return { ...identity, state: ATTEMPT_STATES.succeeded, error: null, note: "上游已完成" };
    }
    if (status === "FAILED" || status === "CANCELED") {
      return {
        ...identity, state: ATTEMPT_STATES.failed, note: "上游明确未成功（" + status + "）",
        error: normalizedError({
          family: "provider_failed", code: "TASK_" + status,
          message: isNonEmptyString(task.error) ? String(task.error) : "上游任务没有成功（" + status + "）。",
          retry_policy: "retryable",
        }, {
          family: "provider_failed", code: "TASK_FAILED",
          message: "上游任务没有成功。", retry_policy: "retryable",
        }),
      };
    }
    return {
      ...identity, state: ATTEMPT_STATES.unknown,
      note: "上游状态无法识别：" + status,
      error: unknownError(null, {
        family: ATTEMPT_UNKNOWN_FAMILY, code: "TASK_STATUS_UNRECOGNIZED",
        message: "上游返回了无法识别的任务状态：" + status + "；先核对，不要自动重提。",
        retry_policy: "requires_review",
      }),
    };
  }
  const raw = env ? env.error : null;
  const family = isPlainObject(raw) ? raw.family : null;
  if ((env && env.unknown === true) || family === ATTEMPT_UNKNOWN_FAMILY) {
    return {
      task_id: null, request_id: null, provider_id: null, model_id: null,
      state: ATTEMPT_STATES.unknown, note: "查询没有结论",
      error: unknownError(raw, {
        family: ATTEMPT_UNKNOWN_FAMILY, code: "STATUS_UNKNOWN",
        message: "暂时无法确认这个任务的状态；请再次查询原任务，不要重新提交。",
        retry_policy: "requires_review",
      }),
    };
  }
  if (family === "provider_failed") {
    return {
      task_id: null, request_id: null, provider_id: null, model_id: null,
      state: ATTEMPT_STATES.failed, note: "上游明确失败",
      error: normalizedError(raw, {
        family: "provider_failed", code: "PROVIDER_FAILED",
        message: "上游明确失败。", retry_policy: "retryable",
      }),
    };
  }
  if (family === "input_rejected") {
    return {
      task_id: null, request_id: null, provider_id: null, model_id: null,
      state: ATTEMPT_STATES.unknown, note: "本地记录的 task id 被网关拒绝，无法核对",
      error: normalizedError(raw, {
        family: "input_rejected", code: "INPUT_INVALID",
        message: "本地保存的任务编号不符合网关契约，无法核对这次提交。",
        retry_policy: "fatal",
      }),
    };
  }
  return {
    task_id: null, request_id: null, provider_id: null, model_id: null,
    state: null, error: null,
    note: family === "internal"
      ? "服务端没有给出结论；记录不推进，稍后再查。"
      : "查询没有拿到响应；记录不推进，不要重新提交。",
  };
}

/** 提交之后调用：把响应落成新版本（可能一步到终态）。 */
export function nextFromSubmitEnvelope(record, envelope, options = {}) {
  const outcome = classifySubmitEnvelope(envelope);
  const next = advanceAttempt(record, {
    state: outcome.state,
    at: options.at,
    via: "submit",
    note: outcome.note,
    taskId: outcome.task_id,
    requestId: outcome.request_id,
    error: outcome.error,
  });
  return { record: next, outcome: outcome };
}

/** 查询之后调用：没有新结论时不产生新版本，绝不把记录往回改。 */
export function nextFromStatusEnvelope(record, envelope, options = {}) {
  const outcome = classifyStatusEnvelope(envelope);
  const canAdvance = isNonEmptyString(outcome.state) && outcome.state !== record.state
    && canAttemptTransition(record.state, outcome.state, "query");
  if (!canAdvance) {
    return {
      record: record,
      outcome: { ...outcome, state: null, advanced: false },
    };
  }
  const next = advanceAttempt(record, {
    state: outcome.state,
    at: options.at,
    via: "query",
    note: outcome.note,
    taskId: outcome.task_id === null ? record.task_id : outcome.task_id,
    requestId: outcome.request_id === null ? record.request_id : outcome.request_id,
    error: outcome.error,
  });
  return { record: next, outcome: { ...outcome, advanced: true } };
}
