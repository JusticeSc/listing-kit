/**
 * Product V2 生成前确认与外发资料摘要（V2.3.5，计划 §9.8）。
 *
 * 唯一权威：确认单形状、阻断码、外发资料摘要、风险传播、指纹与失效判定都在本文件。
 * 复用而不是重写：
 *  - 过期判定复用 prompt.js 的 promptStaleness；记录合法性复用 checkPromptRecord；
 *  - 依赖判定复用 suite-plan.js 的 evaluateShot；
 *  - 散列复用调用方注入的 sha256Hex（storage/db.js），本层不写第二种散列。
 * 本层是纯函数：不调用模型、不写存储、不发请求。
 */

import { DOMAIN_ERROR_CODES, invalid } from "./errors.js";
import {
  isNonEmptyString,
  isPlainObject,
  isSha256Hex,
  pushProblem,
} from "./shared.js";
import {
  PLATFORM_PROFILES,
  PROVIDER_PROFILES,
  canonicalJson,
  checkPromptRecord,
  promptStaleness,
} from "./prompt.js";
import { evaluateShot, roleDefinition } from "./suite-plan.js";

export const CONFIRM_SCHEMA_VERSION = 1;
export const CONFIRM_DOCUMENT_ID = "generation";

export const CONFIRM_BLOCKER_CODES = Object.freeze({
  PROMPT_MISSING: "PROMPT_MISSING",
  PROMPT_RECORD_INVALID: "PROMPT_RECORD_INVALID",
  PROMPT_TEXT_MISMATCH: "PROMPT_TEXT_MISMATCH",
  PROMPT_STALE: "PROMPT_STALE",
  DEPENDENCY_UNSATISFIED: "DEPENDENCY_UNSATISFIED",
  PLATFORM_MISMATCH: "PLATFORM_MISMATCH",
  PROVIDER_MISMATCH: "PROVIDER_MISMATCH",
  REFERENCE_COUNT_INVALID: "REFERENCE_COUNT_INVALID",
});

/** 精确修改位置：阻断必须能指回一个可操作区域。 */
export const FIX_REGIONS = Object.freeze([
  "intake", "understanding", "suite", "style", "shot_spec", "prompt",
]);

const SUMMARY_FIELDS = Object.freeze([
  "model", "size", "n", "prompt_extend", "watermark",
  "reference_count", "reference_roles", "prompt_chars",
]);

function fixTarget(region, shotId, label, action) {
  return { region, shot_id: shotId === undefined ? null : shotId, label, action };
}

function blockingText(blocking) {
  return (Array.isArray(blocking) ? blocking : [])
    .map((item) => (item && (item.reason || item.message)) || "依据未满足")
    .join("；");
}

/** 过期原因字段 → 用户该去改哪里；不允许只说“过期了”。 */
function fixForStaleReason(reason, shotId, label) {
  const field = String((reason && reason.field) || "");
  if (field.indexOf("brief.") === 0) {
    return fixTarget("understanding", shotId, label,
      "到「商品理解」确认或修改槽位 " + field.slice("brief.".length) + "，再重新编译这张图的 Prompt。");
  }
  if (field === "style_version") {
    return fixTarget("style", shotId, label, "到「风格与单图规格」复核公共风格，再重新编译这张图的 Prompt。");
  }
  if (field === "shot_spec_version") {
    return fixTarget("shot_spec", shotId, label, "到「风格与单图规格」复核这张图的单图规格，再重新编译。");
  }
  if (field === "suite_version") {
    return fixTarget("suite", shotId, label, "到「套图规划」复核这张图，再重新编译。");
  }
  if (field === "platform") {
    return fixTarget("prompt", shotId, label, "平台档已更新，重新编译这张图的 Prompt。");
  }
  if (field === "provider") {
    return fixTarget("prompt", shotId, label, "Provider 档已更新，重新编译这张图的 Prompt。");
  }
  return fixTarget("prompt", shotId, label, "到「Prompt 预览与版本」重新编译这张图（原因：" + (field || "未知") + "）。");
}

/**
 * 生成前确认单：这是“将要提交给外部模型的东西”的唯一投影。
 * 输出是确定性的：相同输入必然产生逐字相同的对象（键序由本函数决定）。
 */
export function buildConfirmationSheet(input = {}) {
  if (!isPlainObject(input)) invalid("生成前确认需要输入对象。");
  const plan = input.suitePlan;
  if (!isPlainObject(plan) || !Array.isArray(plan.shots)) {
    invalid("生成前确认需要合法的套图计划（shots 数组）。");
  }
  const platform = PLATFORM_PROFILES[input.platformId || "amazon_us"];
  if (!platform) invalid("平台档不存在：" + String(input.platformId));
  const provider = PROVIDER_PROFILES[input.providerId || "qwen-image-3.0"];
  if (!provider) invalid("Provider 档不存在：" + String(input.providerId));
  const context = isPlainObject(input.context) ? input.context : {};
  const currentBasisByShot = isPlainObject(input.currentBasisByShot) ? input.currentBasisByShot : {};
  const entries = new Map();
  for (const item of Array.isArray(input.promptEntries) ? input.promptEntries : []) {
    if (isPlainObject(item) && isNonEmptyString(item.shot_id)) entries.set(item.shot_id, item);
  }

  const shots = [];
  for (const [index, shot] of plan.shots.entries()) {
    if (!isPlainObject(shot)) continue;
    const shotId = shot.shot_id;
    const label = isNonEmptyString(shot.label) ? shot.label : String(shotId);
    const role = roleDefinition(shot.role_id);
    const blockers = [];
    const risks = [];
    const dependency = evaluateShot(shot, context);
    if (!dependency.satisfied) {
      blockers.push({
        code: CONFIRM_BLOCKER_CODES.DEPENDENCY_UNSATISFIED,
        message: "依据未满足：" + blockingText(dependency.blocking),
        fix: fixTarget("suite", shotId, label,
          "到「套图规划」补齐依据（上传缺失素材或确认缺失事实），或删除、替换这张图。"),
      });
    }

    const prompt = { version: null, hash: null, chars: null };
    let references = [];
    const entry = entries.get(shotId) || null;
    if (!entry) {
      blockers.push({
        code: CONFIRM_BLOCKER_CODES.PROMPT_MISSING,
        message: "还没有 Prompt 版本，无法生成。",
        fix: fixTarget("prompt", shotId, label, "到「Prompt 预览与版本」为这张图编译并保存版本。"),
      });
    } else {
      const record = entry.record;
      const problems = checkPromptRecord(record);
      if (problems.length > 0) {
        blockers.push({
          code: CONFIRM_BLOCKER_CODES.PROMPT_RECORD_INVALID,
          message: problems[0].message,
          details: problems.slice(0, 3),
          fix: fixTarget("prompt", shotId, label, "重新编译这张图的 Prompt（旧版本已保留）。"),
        });
      } else {
        prompt.version = typeof entry.version === "number" ? entry.version : null;
        prompt.hash = record.hash;
        prompt.chars = record.compiled.text.length;
        const snapshot = record.request_snapshot;
        if (snapshot.prompt !== record.compiled.text) {
          blockers.push({
            code: CONFIRM_BLOCKER_CODES.PROMPT_TEXT_MISMATCH,
            message: "请求快照的 prompt 与编译文本不一致。",
            fix: fixTarget("prompt", shotId, label, "重新编译这张图的 Prompt。"),
          });
        }
        const compiledPlatform = record.compiled.platform || {};
        if (compiledPlatform.platform_id !== platform.platform_id
            || compiledPlatform.version !== platform.version) {
          blockers.push({
            code: CONFIRM_BLOCKER_CODES.PLATFORM_MISMATCH,
            message: "这张图的 Prompt 用的是 " + String(compiledPlatform.platform_id)
              + "@" + String(compiledPlatform.version) + "，当前平台档是 "
              + platform.platform_id + "@" + platform.version + "。",
            fix: fixTarget("prompt", shotId, label, "按当前平台档重新编译这张图的 Prompt。"),
          });
        }
        const compiledProvider = record.compiled.provider || {};
        if (compiledProvider.model_id !== provider.model_id
            || compiledProvider.version !== provider.version) {
          blockers.push({
            code: CONFIRM_BLOCKER_CODES.PROVIDER_MISMATCH,
            message: "这张图的 Prompt 用的是 " + String(compiledProvider.model_id)
              + "@" + String(compiledProvider.version) + "，当前 Provider 档是 "
              + provider.model_id + "@" + provider.version + "。",
            fix: fixTarget("prompt", shotId, label, "按当前 Provider 档重新编译这张图的 Prompt。"),
          });
        }
        const snapshotRefs = Array.isArray(snapshot.references) ? snapshot.references : [];
        if (snapshotRefs.length < 1 || snapshotRefs.length > provider.max_reference_images) {
          blockers.push({
            code: CONFIRM_BLOCKER_CODES.REFERENCE_COUNT_INVALID,
            message: "参考图数量 " + snapshotRefs.length + " 不在 1.." + provider.max_reference_images + " 之间。",
            fix: fixTarget("intake", shotId, label, "到「商品资料」补齐参考图（至少一张主图）。"),
          });
        }
        references = snapshotRefs.map((item) => ({
          role: item.role,
          sha256_prefix: String(item.sha256 || "").slice(0, 12),
        }));
        const basis = currentBasisByShot[shotId];
        if (!isPlainObject(basis)) {
          blockers.push({
            code: CONFIRM_BLOCKER_CODES.PROMPT_STALE,
            message: "无法核对这张图的当前编译依据，不能提交。",
            fix: fixTarget("prompt", shotId, label, "重新编译这张图的 Prompt 以建立可核对的依据。"),
          });
        } else {
          const staleness = promptStaleness(record, basis);
          if (staleness.stale) {
            blockers.push({
              code: CONFIRM_BLOCKER_CODES.PROMPT_STALE,
              message: "Prompt 已过期：" + staleness.reasons.map((item) => item.field).join("、"),
              details: staleness.reasons,
              fix: fixForStaleReason(staleness.reasons[0], shotId, label),
            });
          }
        }
        for (const warning of Array.isArray(record.compiled.warnings) ? record.compiled.warnings : []) {
          risks.push({
            code: warning.code,
            message: warning.message,
            shot_id: shotId,
            label: label,
          });
        }
      }
    }

    shots.push({
      shot_id: shotId,
      order: index + 1,
      label: label,
      role_id: shot.role_id === undefined ? null : shot.role_id,
      role_label: role ? role.label : null,
      intent: isNonEmptyString(shot.intent) ? shot.intent : null,
      template_id: shot.template_id === undefined ? null : shot.template_id,
      required: shot.required === true,
      satisfied: dependency.satisfied,
      prompt: prompt,
      references: references,
      risks: risks,
      blockers: blockers,
    });
  }

  const blockedShots = shots.filter((item) => item.blockers.length > 0);
  const referenceRoles = [...new Set(shots.flatMap((item) => item.references.map((ref) => ref.role)))];
  const referenceCount = shots.reduce((total, item) => total + item.references.length, 0);
  const promptChars = shots.reduce((total, item) => total + (item.prompt.chars || 0), 0);
  const externalSummary = {
    model: provider.model_id,
    size: provider.size,
    n: provider.n,
    prompt_extend: provider.prompt_extend,
    watermark: provider.watermark,
    reference_count: referenceCount,
    reference_roles: referenceRoles,
    prompt_chars: promptChars,
    on_image_text_language: platform.on_image_text_language,
    statement: "生成时将向 " + provider.model_id + " 发送 " + shots.length + " 条提示词（合计 "
      + promptChars + " 字）与 " + referenceCount + " 张参考图（角色："
      + (referenceRoles.length > 0 ? referenceRoles.join("、") : "无") + "）；参数 "
      + provider.size + " / n=" + provider.n + " / prompt_extend=" + String(provider.prompt_extend)
      + " / watermark=" + String(provider.watermark) + "；图中文字语言 " + platform.on_image_text_language + "。",
  };

  return {
    schema_version: CONFIRM_SCHEMA_VERSION,
    platform: { platform_id: platform.platform_id, version: platform.version, label: platform.label },
    provider: {
      model_id: provider.model_id,
      version: provider.version,
      size: provider.size,
      n: provider.n,
      prompt_extend: provider.prompt_extend,
      watermark: provider.watermark,
    },
    total: shots.length,
    ready: shots.length - blockedShots.length,
    blocked: blockedShots.length,
    can_submit: shots.length > 0 && blockedShots.length === 0,
    shots: shots,
    external_summary: externalSummary,
    blockers: shots.flatMap((item) => item.blockers.map((blocker) => ({
      shot_id: item.shot_id,
      label: item.label,
      order: item.order,
      code: blocker.code,
      message: blocker.message,
      fix: blocker.fix,
    }))),
    risks: shots.flatMap((item) => item.risks),
  };
}

/** 确认单自检：计数、聚合与外发摘要必须彼此一致。 */
export function checkConfirmationSheet(sheet) {
  const problems = [];
  if (!isPlainObject(sheet)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "确认单必须是对象。");
    return problems;
  }
  if (sheet.schema_version !== CONFIRM_SCHEMA_VERSION) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.schema_version",
      "确认单版本不认识：" + String(sheet.schema_version));
  }
  if (!isPlainObject(sheet.platform) || !isNonEmptyString(sheet.platform.platform_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.platform", "确认单缺少平台档。");
  }
  if (!isPlainObject(sheet.provider) || !isNonEmptyString(sheet.provider.model_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.provider", "确认单缺少 Provider 档。");
  }
  const shots = Array.isArray(sheet.shots) ? sheet.shots : null;
  if (!shots) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shots", "确认单缺少 shots 数组。");
    return problems;
  }
  const blockedCount = shots.filter((item) => Array.isArray(item.blockers) && item.blockers.length > 0).length;
  if (sheet.total !== shots.length || sheet.blocked !== blockedCount || sheet.ready !== shots.length - blockedCount) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.total",
      "确认单计数与实际图片不一致。");
  }
  if (sheet.can_submit !== (shots.length > 0 && blockedCount === 0)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.can_submit",
      "can_submit 必须等于「至少一张图且没有阻断」。");
  }
  let referenceCount = 0;
  let promptChars = 0;
  shots.forEach((item, index) => {
    const itemPath = "$.shots[" + index + "]";
    if (!isPlainObject(item) || !isNonEmptyString(item.shot_id)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, itemPath, "确认单图片缺少 shot_id。");
      return;
    }
    if (!Array.isArray(item.blockers) || !Array.isArray(item.risks)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, itemPath + ".blockers", "blockers/risks 必须是数组。");
      return;
    }
    item.blockers.forEach((blocker, blockerIndex) => {
      const blockerPath = itemPath + ".blockers[" + blockerIndex + "]";
      if (!isPlainObject(blocker) || !isNonEmptyString(blocker.code)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, blockerPath, "阻断缺少 code。");
        return;
      }
      if (!isPlainObject(blocker.fix) || !FIX_REGIONS.includes(blocker.fix.region)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, blockerPath + ".fix",
          "阻断必须带可操作的 fix 位置。");
      }
    });
    if (isPlainObject(item.prompt) && item.prompt.version !== null
        && !isSha256Hex(item.prompt.hash)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, itemPath + ".prompt.hash",
        "有版本的 Prompt 必须带 sha256 hash。");
    }
    if (Array.isArray(item.references)) {
      referenceCount += item.references.length;
    }
    if (isPlainObject(item.prompt) && typeof item.prompt.chars === "number") {
      promptChars += item.prompt.chars;
    }
  });
  const summary = sheet.external_summary;
  if (!isPlainObject(summary)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.external_summary", "确认单缺少外发摘要。");
  } else {
    if (summary.model !== (sheet.provider || {}).model_id || summary.size !== (sheet.provider || {}).size) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.external_summary.model",
        "外发摘要的参数必须来自 Provider 档。");
    }
    if (summary.reference_count !== referenceCount || summary.prompt_chars !== promptChars) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.external_summary.reference_count",
        "外发摘要必须等于各图参考图与提示词字符的合计。");
    }
  }
  return problems;
}

export function assertConfirmationSheet(sheet) {
  const problems = checkConfirmationSheet(sheet);
  if (problems.length > 0) {
    invalid("生成前确认单不合法：" + problems[0].message, { problems: problems.slice(0, 5) });
  }
  return sheet;
}

/** 指纹输入：覆盖“这一批将要提交的东西”，不包含展示文案。 */
export function confirmationSnapshot(sheet) {
  assertConfirmationSheet(sheet);
  return {
    schema_version: CONFIRM_SCHEMA_VERSION,
    platform: { platform_id: sheet.platform.platform_id, version: sheet.platform.version },
    provider: { model_id: sheet.provider.model_id, version: sheet.provider.version },
    can_submit: sheet.can_submit === true,
    shots: sheet.shots.map((item) => ({
      shot_id: item.shot_id,
      prompt_version: item.prompt.version,
      prompt_hash: item.prompt.hash,
      prompt_chars: item.prompt.chars,
      reference_roles: item.references.map((ref) => ref.role),
      blocked: item.blockers.map((blocker) => blocker.code),
    })),
    external_summary: {
      model: sheet.external_summary.model,
      size: sheet.external_summary.size,
      n: sheet.external_summary.n,
      prompt_extend: sheet.external_summary.prompt_extend,
      watermark: sheet.external_summary.watermark,
      reference_count: sheet.external_summary.reference_count,
      reference_roles: [...sheet.external_summary.reference_roles],
      prompt_chars: sheet.external_summary.prompt_chars,
    },
  };
}

export function confirmationSnapshotJson(sheet) {
  return canonicalJson(confirmationSnapshot(sheet));
}

/**
 * 确认失效判定：与当前确认单快照逐字段比较，给出可读原因。
 * 与 promptStaleness 同形（{stale, reasons[]}），界面可以共用一套渲染。
 */
export function confirmationStaleness(record, currentSnapshot) {
  const stored = isPlainObject(record) && isPlainObject(record.fingerprint)
    ? record.fingerprint.snapshot : null;
  if (!stored) {
    return { stale: true, reasons: [{ field: "fingerprint", stored: null, current: null, reason: "确认记录缺少指纹。" }] };
  }
  const now = isPlainObject(currentSnapshot) ? currentSnapshot : null;
  if (!now) {
    return { stale: true, reasons: [{ field: "fingerprint", stored: null, current: null, reason: "没有可比较的当前确认单。" }] };
  }
  if (canonicalJson(stored) === canonicalJson(now)) return { stale: false, reasons: [] };
  const reasons = [];
  if (((stored.platform || {}).version) !== ((now.platform || {}).version)) {
    reasons.push({ field: "platform", stored: (stored.platform || {}).version ?? null,
                   current: (now.platform || {}).version ?? null, reason: "平台档版本前进" });
  }
  if (((stored.provider || {}).version) !== ((now.provider || {}).version)) {
    reasons.push({ field: "provider", stored: (stored.provider || {}).version ?? null,
                   current: (now.provider || {}).version ?? null, reason: "Provider 档版本前进" });
  }
  const storedShots = new Map((Array.isArray(stored.shots) ? stored.shots : []).map((item) => [item.shot_id, item]));
  const nowShots = new Map((Array.isArray(now.shots) ? now.shots : []).map((item) => [item.shot_id, item]));
  for (const [shotId, item] of nowShots) {
    const before = storedShots.get(shotId);
    if (!before) {
      reasons.push({ field: "shots." + shotId, stored: null, current: item.prompt_version, reason: "新增图片" });
      continue;
    }
    if (before.prompt_hash !== item.prompt_hash || before.prompt_version !== item.prompt_version) {
      reasons.push({ field: "shots." + shotId, stored: before.prompt_version, current: item.prompt_version,
                     reason: "该图 Prompt 已变化" });
    }
    if (canonicalJson(before.blocked || []) !== canonicalJson(item.blocked || [])) {
      reasons.push({ field: "shots." + shotId, stored: before.blocked || [], current: item.blocked || [],
                     reason: "该图阻断状态变化" });
    }
  }
  for (const [shotId] of storedShots) {
    if (!nowShots.has(shotId)) {
      reasons.push({ field: "shots." + shotId, stored: shotId, current: null, reason: "图片已删除" });
    }
  }
  const beforeSummary = stored.external_summary || {};
  const nowSummary = now.external_summary || {};
  for (const key of SUMMARY_FIELDS) {
    const before = key === "reference_roles" ? canonicalJson(beforeSummary[key] || []) : beforeSummary[key];
    const after = key === "reference_roles" ? canonicalJson(nowSummary[key] || []) : nowSummary[key];
    if (before !== after) {
      reasons.push({ field: "external_summary." + key, stored: before, current: after, reason: "外发摘要变化" });
    }
  }
  if (Boolean(stored.can_submit) !== Boolean(now.can_submit)) {
    reasons.push({ field: "can_submit", stored: Boolean(stored.can_submit), current: Boolean(now.can_submit),
                   reason: "提交条件变化" });
  }
  if (reasons.length === 0) {
    reasons.push({ field: "fingerprint", stored: "stored", current: "current", reason: "确认单内容变化" });
  }
  return { stale: true, reasons: reasons };
}

/** 确认记录：确认是“用户对某一具体输入的显式确认”，所以它绑定指纹而不是绑定时间。 */
export function buildConfirmationRecord({ sheet, hash, confirmedAt } = {}) {
  assertConfirmationSheet(sheet);
  if (sheet.can_submit !== true) {
    invalid("还有 " + sheet.blocked + " 张图未就绪，不能确认生成。");
  }
  if (!isSha256Hex(hash)) invalid("确认记录缺少有效 fingerprint hash。");
  if (typeof confirmedAt !== "string" || confirmedAt.length < 20 || Number.isNaN(Date.parse(confirmedAt))) {
    invalid("确认记录需要 ISO 时间戳。");
  }
  return {
    schema_version: CONFIRM_SCHEMA_VERSION,
    confirmed_at: confirmedAt,
    fingerprint: { snapshot: confirmationSnapshot(sheet), hash: hash },
    platform: { platform_id: sheet.platform.platform_id, version: sheet.platform.version },
    provider: { model_id: sheet.provider.model_id, version: sheet.provider.version },
    total: sheet.total,
    external_summary: sheet.external_summary,
    shots: sheet.shots.map((item) => ({
      shot_id: item.shot_id,
      label: item.label,
      prompt_version: item.prompt.version,
      prompt_hash: item.prompt.hash,
      references: item.references,
      risks: item.risks.map((risk) => risk.code),
    })),
    risks: sheet.risks.map((risk) => ({ shot_id: risk.shot_id, code: risk.code })),
  };
}

export function checkConfirmationRecord(record) {
  const problems = [];
  if (!isPlainObject(record)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "确认记录必须是对象。");
    return problems;
  }
  if (record.schema_version !== CONFIRM_SCHEMA_VERSION) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.schema_version",
      "确认记录版本不认识：" + String(record.schema_version));
  }
  if (typeof record.confirmed_at !== "string" || Number.isNaN(Date.parse(record.confirmed_at))) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.confirmed_at", "确认记录缺少 ISO 时间戳。");
  }
  if (!isPlainObject(record.fingerprint) || !isSha256Hex(record.fingerprint.hash)
      || !isPlainObject(record.fingerprint.snapshot)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.fingerprint",
      "确认记录必须带 {snapshot, hash} 指纹。");
  } else {
    const expected = canonicalJson(record.fingerprint.snapshot);
    if (!isNonEmptyString(expected)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.fingerprint.snapshot", "指纹快照不可序列化。");
    }
    if (record.fingerprint.snapshot.can_submit !== true) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.fingerprint.snapshot.can_submit",
        "只有可提交的确认单才能写确认记录。");
    }
  }
  if (!Array.isArray(record.shots) || record.shots.length === 0) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shots", "确认记录必须包含每图指纹。");
  } else {
    record.shots.forEach((item, index) => {
      if (!isPlainObject(item) || !isNonEmptyString(item.shot_id) || !isSha256Hex(item.prompt_hash)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shots[" + index + "]",
          "每图指纹需要 shot_id 与 prompt_hash。");
      }
    });
  }
  if (record.total !== (Array.isArray(record.shots) ? record.shots.length : -1)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.total", "确认记录张数与逐图指纹不一致。");
  }
  if (!isPlainObject(record.external_summary)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.external_summary", "确认记录缺少外发摘要。");
  }
  return problems;
}
