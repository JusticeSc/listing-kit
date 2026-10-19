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
  ATTEMPT_CREDENTIAL_SOURCES,
  ATTEMPT_PROTOCOL_PATTERN,
} from "./attempt.js";
import {
  isNonEmptyString,
  isPlainObject,
  isSha256Hex,
  pushProblem,
  canonicalJson,
} from "./shared.js";
import {
  PLATFORM_PROFILES,
  checkFrozenReferences,
  checkImagePromptProfile,
  checkPromptRecord,
  decisionProblems,
  dependencyAssetsOf,
  promptStaleness,
} from "./prompt.js";
import { evaluateShot, roleDefinition } from "./suite-plan.js";

export const CONFIRM_SCHEMA_VERSION = 3;
/** 历史1仅角色、历史2含图身份；原载荷只读保留，不补造新用途/来源。 */
export const CONFIRM_SCHEMA_VERSIONS_LEGACY = Object.freeze([1, 2]);
export const CONFIRM_DOCUMENT_ID = "generation";
const SUBMISSION_MODES = Object.freeze(["initial", "failed_retry", "rework", "explicit_new"]);

// 阻断码词表上移 shared.js（review.js 在模块初始化期读取；词表是叶子常量，
// 不允许把确认单模块拖进跨模块循环初始化）。此处按原路径再导出，既有导入不变。
export { CONFIRM_BLOCKER_CODES } from "./shared.js";
import { CONFIRM_BLOCKER_CODES } from "./shared.js";

/** 精确修改位置：阻断必须能指回一个可操作区域。 */
export const FIX_REGIONS = Object.freeze([
  "intake", "understanding", "suite", "style", "shot_spec", "prompt",
]);

const SUMMARY_FIELDS = Object.freeze([
  "model", "size", "n", "prompt_extend", "watermark", "output_format",
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
  if (field === "style_version" || field === "style_signature") {
    return fixTarget("style", shotId, label, "到「风格与单图规格」复核公共风格，再重新编译这张图的 Prompt。");
  }
  if (field === "shot_signature") {
    return fixTarget("suite", shotId, label, "这张图自己的定义（用途/绑定/依赖）已变化，到「套图规划」复核后重新编译。");
  }
  if (field === "compiler_rule_version") {
    return fixTarget("prompt", shotId, label,
      "程序提示词规则已更新：重新编译这张图的系统全文（人工全文由人确认，不静默覆盖）。");
  }
  if (field === "intake_version") {
    return fixTarget("prompt", shotId, label,
      "商品资料版本已前进：按当前商品资料重新编译这张图的 Prompt，再确认（不会拿旧资料直接提交）。");
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
    return fixTarget("prompt", shotId, label, "有效 Provider 档或请求参数已更新，重新编译这张图的 Prompt。");
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
  const provider = input.providerProfile;
  const profileProblems = checkImagePromptProfile(provider);
  if (profileProblems.length > 0) {
    invalid("生成前确认缺少有效 Provider 档：" + profileProblems[0].message,
      { problems: profileProblems.slice(0, 3) });
  }
  const context = isPlainObject(input.context) ? input.context : {};
  const currentBasisByShot = isPlainObject(input.currentBasisByShot) ? input.currentBasisByShot : {};
  // 可选作用域（V2.5.4 单图返工）：只确认要重跑的那张图，不触及其它图片的确认状态。
  const scopeShotIds = Array.isArray(input.shotIds) && input.shotIds.length > 0
    ? [...new Set(input.shotIds.filter((item) => isNonEmptyString(item)))] : null;
  const entries = new Map();
  for (const item of Array.isArray(input.promptEntries) ? input.promptEntries : []) {
    if (isPlainObject(item) && isNonEmptyString(item.shot_id)) entries.set(item.shot_id, item);
  }

  const shots = [];
  for (const [index, shot] of plan.shots.entries()) {
    if (!isPlainObject(shot)) continue;
    if (scopeShotIds && !scopeShotIds.includes(shot.shot_id)) continue;
    const shotId = shot.shot_id;
    const label = isNonEmptyString(shot.label) ? shot.label : String(shotId);
    const role = roleDefinition(shot.role_id);
    const blockers = [];
    const risks = [];
    // 依赖求值按「本图实际会外发的商品依据」判，与提交门共用 dependencyAssetsOf：
    // 调用方给出本图参考选择时按实际冻结顺序判（竞品图以 style_reference 发货仍算
    // competitor 角色），未给出时保持既有 intake 上下文（旧调用方兼容）。
    const selection = isPlainObject(input.referencesByShot) ? input.referencesByShot[shotId] : undefined;
    const dependency = evaluateShot(shot, Array.isArray(selection)
      ? { ...context, assets: dependencyAssetsOf(selection) } : context);
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
    // 普通决定没做完时，编译必然失败：直接说清「缺哪个决定」并指向对应控件，
    // 而不是笼统报「还没有 Prompt 版本」把用户送错地方。
    // 只有当调用方把决定所依据的规格交进来时才检查（否则无从判断，不得凭猜测阻断）。
    const decisionInputsGiven = input.styleSpec !== undefined || input.shotSpecsById !== undefined;
    const shotSpec = isPlainObject(input.shotSpecsById) && isPlainObject(input.shotSpecsById[shotId])
      ? input.shotSpecsById[shotId].spec : null;
    const decisions = decisionInputsGiven
      ? decisionProblems({
        shot: shot, shotSpec: shotSpec, styleSpec: input.styleSpec, brief: input.brief,
        platformId: input.platformId,
        // 视角决定要看本图实际冻结的商品依据：调用方给出时按真实证据判，不给时保持 fail-closed。
        references: isPlainObject(input.referencesByShot) ? input.referencesByShot[shotId] : undefined,
        slotEntries: input.slotEntries,
      })
      : [];
    if (decisions.length > 0) {
      const first = decisions[0];
      const shotLevel = String(first.path || "").indexOf("$.shot_spec") === 0;
      blockers.push({
        code: CONFIRM_BLOCKER_CODES.DECISION_REQUIRED,
        message: first.message,
        details: decisions.slice(0, 3),
        fix: shotLevel
          ? fixTarget("shot_spec", shotId, label,
            "到「风格与单图规格」为这张图做完印字与展示决定，再重新编译。")
          : fixTarget("style", shotId, label,
            "到「风格与单图规格」做完共用展示决定（整套共用，做完这张图就跟着走），再重新编译。"),
      });
    } else if (!entry) {
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
        // 比对完整冻结档（目标 / 协议 / 版本 / 请求参数），而非只比 model+version。
        if (canonicalJson(compiledProvider) !== canonicalJson(provider)) {
          blockers.push({
            code: CONFIRM_BLOCKER_CODES.PROVIDER_MISMATCH,
            message: "这张图的 Prompt 冻结的是 " + String(compiledProvider.model_id)
              + "@" + String(compiledProvider.version) + "（协议 " + String(compiledProvider.protocol)
              + "），当前有效 Provider 档是 " + provider.model_id + "@" + provider.version
              + "（协议 " + provider.protocol + "）。",
            fix: fixTarget("prompt", shotId, label, "按当前有效 Provider 档重新编译这张图的 Prompt。"),
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
        // 冻结用途/来源按实际发送顺序投影到确认单（设计 §13.6/§13.8）：确认页必须说清
        // 每张图的职责与来源，编辑源与商品原照不能只靠 role 区分；schema 3 起携带完整
        // 身份（sha256）与来源（含 asset_sha256），确认记录快照按同形状写入。历史简单
        // 引用不带冻结元数据时不补造，按缺少处理；界面上只见前缀，不外发完整 hash 文案。
        references = snapshotRefs.map((item) => ({
          role: item.role,
          sha256: item.sha256,
          sha256_prefix: String(item.sha256 || "").slice(0, 12),
          ...(Array.isArray(item.uses) ? { uses: [...item.uses] } : {}),
          ...(Array.isArray(item.sources)
            ? { sources: item.sources.map((source) => (isPlainObject(source)
              ? { kind: source.kind, document_id: source.document_id, version: source.version,
                ...(isSha256Hex(source.asset_sha256) ? { asset_sha256: source.asset_sha256 } : {}) }
              : source)) }
            : {}),
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
    output_format: provider.output_format,
    reference_count: referenceCount,
    reference_roles: referenceRoles,
    prompt_chars: promptChars,
    on_image_text_language: platform.on_image_text_language,
    statement: "生成时将向 " + provider.model_id + " 发送 " + shots.length + " 条提示词（合计 "
      + promptChars + " 字）与 " + referenceCount + " 张参考图（角色："
      + (referenceRoles.length > 0 ? referenceRoles.join("、") : "无") + "）；参数 "
      + provider.size + " / n=" + provider.n + " / prompt_extend=" + String(provider.prompt_extend)
      + " / watermark=" + String(provider.watermark) + " / 输出格式 " + provider.output_format
      + "；图中文字语言 " + platform.on_image_text_language + "。",
  };

  return {
    schema_version: CONFIRM_SCHEMA_VERSION,
    platform: { platform_id: platform.platform_id, version: platform.version, label: platform.label },
    provider: {
      provider_id: provider.provider_id,
      model_id: provider.model_id,
      version: provider.version,
      protocol: provider.protocol,
      size: provider.size,
      n: provider.n,
      prompt_extend: provider.prompt_extend,
      watermark: provider.watermark,
      output_format: provider.output_format,
    },
    total: shots.length,
    ready: shots.length - blockedShots.length,
    blocked: blockedShots.length,
    can_submit: shots.length > 0 && blockedShots.length === 0,
    shots: shots,
    external_summary: externalSummary,
    ...(scopeShotIds ? { scope_shot_ids: scopeShotIds } : {}),
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
  if (!isPlainObject(sheet.provider) || !isNonEmptyString(sheet.provider.model_id)
      || !isNonEmptyString(sheet.provider.provider_id)
      || !isNonEmptyString(sheet.provider.protocol)
      || !isNonEmptyString(sheet.provider.output_format)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.provider",
      "确认单缺少完整 Provider 档（目标 / 协议 / 输出格式）。");
  }
  if (sheet.scope_shot_ids !== undefined) {
    if (!Array.isArray(sheet.scope_shot_ids) || sheet.scope_shot_ids.length === 0
        || sheet.scope_shot_ids.some((item) => !isNonEmptyString(item))) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.scope_shot_ids",
        "作用域必须是至少一张图的 shot_id 数组。");
    }
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
    if (summary.model !== (sheet.provider || {}).model_id || summary.size !== (sheet.provider || {}).size
        || summary.output_format !== (sheet.provider || {}).output_format) {
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

function confirmationExecutionTarget(identity, provider) {
  if (!isPlainObject(identity) || !isNonEmptyString(identity.provider_id)
      || !isNonEmptyString(identity.model_id)
      || !ATTEMPT_PROTOCOL_PATTERN.test(identity.protocol)
      || !Number.isInteger(identity.capability_version) || identity.capability_version < 1
      || !ATTEMPT_CREDENTIAL_SOURCES.includes(identity.credential_source)
      || typeof identity.sync !== "boolean") {
    invalid("生成授权缺少可核对的原目标、协议、能力版本或凭据来源。");
  }
  if (!isPlainObject(provider) || provider.model_id !== identity.model_id
      || provider.version !== identity.capability_version
      || (provider.provider_id !== undefined && provider.provider_id !== identity.provider_id)
      || (provider.protocol !== undefined && provider.protocol !== identity.protocol)) {
    invalid("生成授权目标与已显示的 Prompt 有效档不一致。");
  }
  return {
    provider_id: identity.provider_id, model_id: identity.model_id,
    protocol: identity.protocol, capability_version: identity.capability_version,
    credential_source: identity.credential_source, sync: identity.sync,
  };
}

/**
 * 确认快照的逐图引用：schema 3 起 = 该图新请求的冻结引用（身份+用途+来源），
 * 与编译产物 request_snapshot.references 同形状（可过 checkFrozenReferences）。
 * 历史简单引用（旧 Prompt）只有身份，不补造冻结元数据——这只出现在失效比较的临时
 * 快照里；可提交清单上的记录快照全部来自当前 Prompt，必然带完整元数据。
 * @param {unknown} ref 确认单上的引用投影
 * @returns {Record<string, unknown>}
 */
function frozenReferenceOf(ref) {
  if (!isPlainObject(ref)) return ref;
  const base = { role: ref.role, sha256: ref.sha256 };
  if (!Array.isArray(ref.uses) || !Array.isArray(ref.sources)) return base;
  return {
    ...base,
    uses: [...ref.uses],
    sources: ref.sources.map((source) => (isPlainObject(source) ? {
      kind: source.kind, document_id: source.document_id, version: source.version,
      ...(isSha256Hex(source.asset_sha256) ? { asset_sha256: source.asset_sha256 } : {}),
    } : source)),
  };
}

/**
 * 指纹输入：覆盖“这一批将要提交的东西”，不包含展示文案。
 * schema 3（§13.8 一次切换）：逐图带该新请求快照（完整冻结引用）。
 * execution_target/submission_mode 只在给出 executionIdentity 时写入，历史记录可缺。
 * @param {unknown} sheet
 * @param {{executionIdentity?: unknown, submissionMode?: unknown}} [options]
 * @returns {import("./type-contracts.js").ConfirmationSnapshot}
 */
export function confirmationSnapshot(sheet, { executionIdentity = null, submissionMode = "initial" } = {}) {
  assertConfirmationSheet(sheet);
  if (executionIdentity && !SUBMISSION_MODES.includes(submissionMode)) invalid("生成授权缺少明确的动作类型。");
  return {
    schema_version: CONFIRM_SCHEMA_VERSION,
    ...(executionIdentity ? {
      execution_target: confirmationExecutionTarget(executionIdentity, sheet.provider),
      submission_mode: submissionMode,
    } : {}),
    ...(Array.isArray(sheet.scope_shot_ids) && sheet.scope_shot_ids.length > 0
      ? { scope_shot_ids: [...sheet.scope_shot_ids] } : {}),
    platform: { platform_id: sheet.platform.platform_id, version: sheet.platform.version },
    provider: { model_id: sheet.provider.model_id, version: sheet.provider.version },
    can_submit: sheet.can_submit === true,
    shots: sheet.shots.map((item) => ({
      shot_id: item.shot_id,
      prompt_version: item.prompt.version,
      prompt_hash: item.prompt.hash,
      prompt_chars: item.prompt.chars,
      references: item.references.map((ref) => frozenReferenceOf(ref)),
      blocked: item.blockers.map((blocker) => blocker.code),
    })),
    external_summary: {
      model: sheet.external_summary.model,
      size: sheet.external_summary.size,
      n: sheet.external_summary.n,
      prompt_extend: sheet.external_summary.prompt_extend,
      watermark: sheet.external_summary.watermark,
      output_format: sheet.external_summary.output_format,
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

/**
 * 确认记录：确认是“用户对某一具体输入的显式确认”，所以它绑定指纹而不是绑定时间。
 * @param {{sheet?: unknown, hash?: unknown, confirmedAt?: unknown, executionIdentity?: unknown, submissionMode?: unknown}} [args]
 * @returns {import("./type-contracts.js").ConfirmationRecord}
 */
export function buildConfirmationRecord({ sheet, hash, confirmedAt, executionIdentity = null, submissionMode = "initial" } = {}) {
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
    fingerprint: { snapshot: confirmationSnapshot(sheet, { executionIdentity, submissionMode }), hash: hash },
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

/**
 * schema 3：记录逐图引用必须是指纹快照冻结引用的展示投影——
 * 同一 role/sha256/用途/来源，另带 sha256_prefix 供界面展示；不存在第二套事实。
 * @param {unknown} refs 记录里的展示投影
 * @param {unknown} frozenRefs 快照里的冻结引用（已过 checkFrozenReferences）
 * @returns {boolean}
 */
function recordReferencesMatchSnapshot(refs, frozenRefs) {
  if (!Array.isArray(refs) || !Array.isArray(frozenRefs) || refs.length !== frozenRefs.length) return false;
  return refs.every((ref, index) => {
    const base = frozenRefs[index];
    return isPlainObject(ref) && isPlainObject(base)
      && ref.role === base.role && ref.sha256 === base.sha256
      && ref.sha256_prefix === String(base.sha256).slice(0, 12)
      && canonicalJson(ref.uses) === canonicalJson(base.uses)
      && canonicalJson(ref.sources) === canonicalJson(base.sources);
  });
}

export function checkConfirmationRecord(record) {
  const problems = [];
  if (!isPlainObject(record)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "确认记录必须是对象。");
    return problems;
  }
  const legacy = CONFIRM_SCHEMA_VERSIONS_LEGACY.includes(record.schema_version);
  if (record.schema_version !== CONFIRM_SCHEMA_VERSION && !legacy) {
    pushProblem(problems, record.schema_version > CONFIRM_SCHEMA_VERSION
      ? DOMAIN_ERROR_CODES.CONTRACT_SCHEMA_TOO_NEW : DOMAIN_ERROR_CODES.CONTRACT_INVALID,
    "$.schema_version", "确认记录版本不认识：" + String(record.schema_version));
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
    if (!legacy && record.fingerprint.snapshot.schema_version !== CONFIRM_SCHEMA_VERSION) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.fingerprint.snapshot.schema_version",
        "新确认记录必须绑定同版本的完整冻结快照。");
    }
    if (record.fingerprint.snapshot.can_submit !== true) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.fingerprint.snapshot.can_submit",
        "只有可提交的确认单才能写确认记录。");
    }
    if (record.fingerprint.snapshot.execution_target !== undefined) {
      try {
        if (!SUBMISSION_MODES.includes(record.fingerprint.snapshot.submission_mode)) invalid("生成授权缺少动作类型。");
        confirmationExecutionTarget(record.fingerprint.snapshot.execution_target, record.fingerprint.snapshot.provider);
      } catch (error) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.fingerprint.snapshot.execution_target",
          error.message);
      }
    }
    // schema 3：按完整冻结合同机检；历史1/2保持角色/身份原形状，只读不追改。
    if (!legacy && Array.isArray(record.fingerprint.snapshot.shots)) {
      record.fingerprint.snapshot.shots.forEach((shot, index) => {
        if (!isPlainObject(shot)) return;
        for (const problem of checkFrozenReferences(shot.references)) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID,
            "$.fingerprint.snapshot.shots[" + index + "]" + problem.path, problem.message);
        }
      });
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
      // 新记录逐图引用与指纹快照同源；历史1/2保留原形状。
      if (!legacy && isPlainObject(item)) {
        const snapshotShots = isPlainObject(record.fingerprint)
          && Array.isArray(record.fingerprint.snapshot.shots) ? record.fingerprint.snapshot.shots : null;
        const snapshotShot = Array.isArray(snapshotShots) ? snapshotShots[index] : null;
        if (!isPlainObject(snapshotShot) || snapshotShot.shot_id !== item.shot_id
          || !recordReferencesMatchSnapshot(item.references, snapshotShot.references)) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID,
            "$.shots[" + index + "].references",
            "记录引用必须是指纹快照冻结引用的展示投影（role/sha256/用途/来源一致，另带展示前缀）。");
        }
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
