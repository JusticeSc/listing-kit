/**
 * Product V2 确定性验证器（V2.5.1，计划 §9.15）。
 *
 * 三层规则：generation（消费生成前确认单）、candidate（消费候选字节与记录）、export（消费选择与报告链）。
 * 每条规则在注册表里必须有 rule_id / version / layer / title / severity / consumer / measurement /
 * unknown_policy；测量一律委托已有权威（confirm / candidate / attempt），本层不复制它们的计算。
 * ReviewReport 只绑定单图（candidate_id + review_contract_version + asset_sha256）；VLM 发现由
 * V2.5.2 接入同一份报告；generation / export 层返回同构 findings 给各自消费者。
 *
 * 边界：本层是纯函数，不写存储、不发请求、不读时钟；sha256 复用调用方注入的 digest
 * （storage/db.js 的 sha256Hex），不在本层另写散列。审美判断不允许进入注册表：没有可复现
 * 测量的规则不能拿到 BLOCK / HIGH_RISK。
 */

import { candidateMatchesAttempt, checkCandidateRecord, parsePngHeader } from "./candidate.js";
import { CONFIRM_BLOCKER_CODES } from "./confirm.js";
import { DOMAIN_ERROR_CODES, invalid } from "./errors.js";
import {
  DOMAIN_DOCUMENT_KINDS, checkSchemaVersion, isIsoTimestamp, isNonEmptyString,
  isPlainObject, isSha256Hex, pushProblem,
} from "./shared.js";

export const REVIEW_REPORT_SCHEMA_VERSION = 1;
export const REVIEW_CONTRACT_VERSION = "v2.5.2";
export const REVIEW_REPORT_DOCUMENT_KIND = DOMAIN_DOCUMENT_KINDS.review_report;

/** 审核层词表（注册表 layer 字段的唯一合法值）。
 * @type {readonly import("./type-contracts.js").ReviewLayer[]}
 */
export const REVIEW_LAYERS = Object.freeze(["generation", "candidate", "export", "vlm", "suite"]);
/** 严重度词表（发现的 severity 字段的唯一合法值）。
 * @type {readonly import("./type-contracts.js").ReviewSeverity[]}
 */
export const REVIEW_SEVERITIES = Object.freeze(["BLOCK", "HIGH_RISK", "WARNING", "PASS", "UNKNOWN"]);
/**
 * 人工先看顺序（唯一权威）：阻断 → 高风险 → 提醒 → 未知。
 * PASS 只是完成标记，不参与排序；比较面板（domain/compare.js）与本文件的 topFinding 共用这一份。
 * @type {readonly import("./type-contracts.js").ReviewSeverity[]}
 */
export const REVIEW_SEVERITY_ORDER = Object.freeze(["BLOCK", "HIGH_RISK", "WARNING", "UNKNOWN"]);
/** 违规严重度子集（规则注册表只允许这三种；PASS/UNKNOWN 不是规则严重度）。
 * @type {readonly ("BLOCK"|"HIGH_RISK"|"WARNING")[]}
 */
export const VIOLATION_SEVERITIES = Object.freeze(["BLOCK", "HIGH_RISK", "WARNING"]);
/** 测量失败时的降级策略词表。
 * @type {readonly import("./type-contracts.js").UnknownPolicy[]}
 */
export const UNKNOWN_POLICIES = Object.freeze(["hint", "disable"]);
/** 单图 VLM 复核的 outcome 词表。
 * @type {readonly import("./type-contracts.js").VlmOutcome[]}
 */
export const VLM_OUTCOMES = Object.freeze(["checked", "unknown"]);

/**
 * VLM check 词表：与服务端 src/providers/v2_review.py 的 VLM_CHECKS 键集合必须一致（跨语言镜像），
 * 由 tools/verify_v2_5_2_vlm_review.py 比对；rule_id / 严重度 / 消费者的唯一权威仍是本文件注册表。
 * @type {Readonly<Record<import("./type-contracts.js").VlmCheckId, string>>}
 */
export const VLM_CHECK_TO_RULE = Object.freeze({
  product_fidelity: "vlm.product_fidelity",
  part_anomaly: "vlm.part_anomaly",
  deformity: "vlm.deformity",
  clipping: "vlm.clipping",
  garbled_text: "vlm.garbled_text",
  goal_completion: "vlm.goal_completion",
  prohibited_content: "vlm.prohibited_content",
});
export const VLM_MAX_FINDINGS = 12;
export const VLM_MAX_EVIDENCE_LENGTH = 300;

/** Amazon US 确定性阈值：<1000px 不能启用缩放（阻断）；≥1600px 是推荐值（提醒）。 */
export const PLATFORM_MIN_LONG_SIDE = 1000;
export const PLATFORM_RECOMMENDED_LONG_SIDE = 1600;
export const MAIN_SQUARE_TOLERANCE = 0.02;

const CONSUMER_PATTERN = /^[a-z][a-z0-9-]*@V\d+(\.\d+)+$/;

function rule(entry) {
  return Object.freeze(entry);
}

/**
 * 规则注册表：唯一权威。每条规则的 measurement 指向已有权威的实现；
 * consumer 必须能追到一个真实组件和任务号；unknown_policy 决定测量失败时的降级方式。
 * @type {Readonly<import("./type-contracts.js").ReviewRule[]>}
 */
export const DETERMINISTIC_RULES = Object.freeze([
  rule({
    rule_id: "generation.prompt_current", version: 1, layer: "generation", title: "Prompt 当前性",
    severity: "BLOCK", consumer: "review-panel@V2.5.3",
    measurement: "确认单 blockers 中 PROMPT_* 代码（confirm.buildConfirmationSheet 为唯一测量）",
    unknown_policy: "hint",
    blocker_codes: [
      CONFIRM_BLOCKER_CODES.PROMPT_MISSING, CONFIRM_BLOCKER_CODES.PROMPT_RECORD_INVALID,
      CONFIRM_BLOCKER_CODES.PROMPT_TEXT_MISMATCH, CONFIRM_BLOCKER_CODES.PROMPT_STALE,
    ],
  }),
  rule({
    rule_id: "generation.dependency_satisfied", version: 1, layer: "generation", title: "套图依据依赖",
    severity: "BLOCK", consumer: "review-panel@V2.5.3",
    measurement: "确认单 blockers 中 DEPENDENCY_UNSATISFIED（suite 依赖语义为唯一测量）",
    unknown_policy: "hint",
    blocker_codes: [CONFIRM_BLOCKER_CODES.DEPENDENCY_UNSATISFIED],
  }),
  rule({
    rule_id: "generation.platform_provider_match", version: 1, layer: "generation",
    title: "平台/Provider 档匹配", severity: "BLOCK", consumer: "review-panel@V2.5.3",
    measurement: "确认单 blockers 中 PLATFORM_MISMATCH / PROVIDER_MISMATCH（prompt 档比较为唯一测量）",
    unknown_policy: "hint",
    blocker_codes: [CONFIRM_BLOCKER_CODES.PLATFORM_MISMATCH, CONFIRM_BLOCKER_CODES.PROVIDER_MISMATCH],
  }),
  rule({
    rule_id: "generation.references_valid", version: 1, layer: "generation", title: "参考图数量",
    severity: "BLOCK", consumer: "review-panel@V2.5.3",
    measurement: "确认单 blockers 中 REFERENCE_COUNT_INVALID（确认单参考图计数为唯一测量）",
    unknown_policy: "hint",
    blocker_codes: [CONFIRM_BLOCKER_CODES.REFERENCE_COUNT_INVALID],
  }),
  rule({
    rule_id: "generation.risk_visible", version: 1, layer: "generation", title: "确认单提示项",
    severity: "WARNING", consumer: "review-panel@V2.5.3",
    measurement: "确认单 risks 列表（提示项；不阻断，只投影给人工）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "candidate.png_contract", version: 1, layer: "candidate", title: "PNG 字节合同",
    severity: "BLOCK", consumer: "candidate-store@V2.5.1",
    measurement: "PNG 签名 + IHDR/位深/颜色类型解析（candidate.parsePngHeader 为唯一解析器）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "candidate.record_consistent", version: 1, layer: "candidate", title: "候选记录与字节一致",
    severity: "BLOCK", consumer: "candidate-store@V2.5.1",
    measurement: "checkCandidateRecord + 记录宽高/字节数/媒体类型与字节解析比对",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "platform.min_long_side", version: 1, layer: "candidate", title: "最小长边 1000px",
    severity: "BLOCK", consumer: "export-gate@V2.6.2",
    measurement: "候选字节最长边 ≥ 1000px（Amazon US 启用缩放的要求）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "platform.recommended_long_side", version: 1, layer: "candidate", title: "推荐长边 1600px",
    severity: "WARNING", consumer: "review-panel@V2.5.3",
    measurement: "候选字节最长边 ≥ 1600px（Amazon US 最佳缩放推荐值）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "platform.main_square", version: 1, layer: "candidate", title: "主图 1:1",
    severity: "WARNING", consumer: "review-panel@V2.5.3",
    measurement: "主图角色候选的宽高比 1:1（容差 ±2%）",
    unknown_policy: "hint",
    applies_to: Object.freeze({ roles: Object.freeze(["main"]) }),
  }),
  rule({
    rule_id: "platform.alpha_channel", version: 1, layer: "candidate", title: "透明通道提示",
    severity: "HIGH_RISK", consumer: "review-panel@V2.5.3",
    measurement: "PNG 颜色类型 4/6 或 tRNS 块（透明背景风险；人工确认，不自动拒绝）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "candidate.pixel_depth", version: 1, layer: "candidate", title: "像素位深",
    severity: "WARNING", consumer: "review-panel@V2.5.3",
    measurement: "PNG IHDR 位深 ≤ 8（>8 位提示兼容性风险）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "export.selection_complete", version: 1, layer: "export", title: "选择完整性",
    severity: "BLOCK", consumer: "export-gate@V2.6.2",
    measurement: "全部必需 Shot 的 {shot_id: candidate_id} 选择投影（缺一即阻断）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "export.report_current", version: 1, layer: "export", title: "报告当前性",
    severity: "BLOCK", consumer: "export-gate@V2.6.2",
    measurement: "所选候选存在当前 review_contract_version 的 ReviewReport（reviewIsCurrent）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "export.no_blocking_findings", version: 1, layer: "export", title: "所选报告无阻断",
    severity: "BLOCK", consumer: "export-gate@V2.6.2",
    measurement: "所选候选当前报告不含 BLOCK 发现",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "export.chain_integrity", version: 1, layer: "export", title: "选择链完整性",
    severity: "BLOCK", consumer: "export-gate@V2.6.2",
    measurement: "选择 → 候选记录 → 来源 Attempt 身份一致（candidateMatchesAttempt）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "export.asset_hash_matches", version: 1, layer: "export", title: "交付字节哈希",
    severity: "BLOCK", consumer: "export-gate@V2.6.2",
    measurement: "对 Blob 字节重算 sha256（注入 digest）并与候选记录比对",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "vlm.product_fidelity", version: 1, layer: "vlm", title: "商品与参考不一致",
    severity: "HIGH_RISK", consumer: "review-panel@V2.5.3",
    measurement: "VLM 结构化发现（check=product_fidelity，绑定 provider/model/asset_sha256/at）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "vlm.part_anomaly", version: 1, layer: "vlm", title: "部件异常",
    severity: "HIGH_RISK", consumer: "review-panel@V2.5.3",
    measurement: "VLM 结构化发现（check=part_anomaly，绑定 provider/model/asset_sha256/at）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "vlm.deformity", version: 1, layer: "vlm", title: "明显畸形",
    severity: "HIGH_RISK", consumer: "review-panel@V2.5.3",
    measurement: "VLM 结构化发现（check=deformity，绑定 provider/model/asset_sha256/at）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "vlm.clipping", version: 1, layer: "vlm", title: "穿模或拼接痕迹",
    severity: "HIGH_RISK", consumer: "review-panel@V2.5.3",
    measurement: "VLM 结构化发现（check=clipping，绑定 provider/model/asset_sha256/at）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "vlm.garbled_text", version: 1, layer: "vlm", title: "文字乱码",
    severity: "HIGH_RISK", consumer: "review-panel@V2.5.3",
    measurement: "VLM 结构化发现（check=garbled_text，绑定 provider/model/asset_sha256/at）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "vlm.goal_completion", version: 1, layer: "vlm", title: "目标完成度",
    severity: "WARNING", consumer: "review-panel@V2.5.3",
    measurement: "VLM 结构化发现（check=goal_completion，对照 ShotSpec.purpose）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "vlm.prohibited_content", version: 1, layer: "vlm", title: "禁止内容",
    severity: "HIGH_RISK", consumer: "review-panel@V2.5.3",
    measurement: "VLM 结构化发现（check=prohibited_content，最终裁定仍在平台硬规则与人工）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "vlm.inspection_completed", version: 1, layer: "vlm", title: "VLM 复核完成",
    severity: "WARNING", consumer: "review-panel@V2.5.3",
    measurement: "复核结果结构合法且绑定当前候选（checked 且未报告问题 → PASS 标记）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "vlm.inspection_unavailable", version: 1, layer: "vlm", title: "VLM 复核未完成",
    severity: "WARNING", consumer: "review-panel@V2.5.3",
    measurement: "分类失败记录（family/code/retry_policy）与候选身份绑定",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "suite.selection_current", version: 1, layer: "suite", title: "必需图人工选择当前有效",
    severity: "BLOCK", consumer: "export-gate@V2.6.2",
    measurement: "SelectionSet 中必需条目的 state === current（selection.buildSelectionSet 为唯一测量）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "suite.dependency_satisfied", version: 1, layer: "suite", title: "套图依据依赖",
    severity: "BLOCK", consumer: "export-gate@V2.6.2",
    measurement: "suitePlanSummary 的未满足 Shot（suite-plan.evaluateShot 为唯一测量）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "suite.duplicates", version: 1, layer: "suite", title: "重复任务",
    severity: "WARNING", consumer: "suite-panel@V2.5.5",
    measurement: "同类模板（或自定义名）且绑定事实集合相同的 Shot 分组（每组至少 2 张）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "suite.recommended_omissions", version: 1, layer: "suite", title: "推荐图未纳入",
    severity: "WARNING", consumer: "suite-panel@V2.5.5",
    measurement: "recommendPlan 中 satisfied 且非 required 的模板未被当前计划引用",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "suite.selling_point_coverage", version: 1, layer: "suite", title: "卖点覆盖",
    severity: "WARNING", consumer: "suite-panel@V2.5.5",
    measurement: "每个非空卖点出现在某张图所绑定事实的已确认值里",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "vlm.suite_product_consistency", version: 1, layer: "vlm", title: "跨图商品一致性",
    severity: "HIGH_RISK", consumer: "suite-panel@V2.5.5",
    measurement: "整套 VLM 发现（check=suite_product_consistency，shot_ids 必须是送审集合的子集）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "vlm.suite_color_material_consistency", version: 1, layer: "vlm",
    title: "跨图颜色材质一致性", severity: "HIGH_RISK", consumer: "suite-panel@V2.5.5",
    measurement: "整套 VLM 发现（check=suite_color_material_consistency，shot_ids 必须是送审集合的子集）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "vlm.suite_cross_image_anomaly", version: 1, layer: "vlm", title: "跨图低级异常",
    severity: "HIGH_RISK", consumer: "suite-panel@V2.5.5",
    measurement: "整套 VLM 发现（check=suite_cross_image_anomaly，shot_ids 必须是送审集合的子集）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "vlm.suite_style_consistency", version: 1, layer: "vlm", title: "跨图风格一致性",
    severity: "WARNING", consumer: "suite-panel@V2.5.5",
    measurement: "整套 VLM 发现（check=suite_style_consistency，shot_ids 必须是送审集合的子集）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "vlm.suite_inspection_completed", version: 1, layer: "vlm", title: "整套视觉复核完成",
    severity: "WARNING", consumer: "suite-panel@V2.5.5",
    measurement: "整套复核结果结构合法且 shot_ids 全部落在送审集合内（checked 且未报告问题 → PASS）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "vlm.suite_inspection_unavailable", version: 1, layer: "vlm", title: "整套视觉复核未完成",
    severity: "WARNING", consumer: "suite-panel@V2.5.5",
    measurement: "未执行或失败原因（no_selection/over_limit/missing_bytes/transport/protocol 等）与送审集合绑定",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "export.suite_review_current", version: 1, layer: "export", title: "整套一致性报告当前",
    severity: "BLOCK", consumer: "export-gate@V2.6.2",
    measurement: "suiteReviewIsCurrent + checkSuiteReviewReport（suite-review.js 为唯一测量）",
    unknown_policy: "hint",
  }),
  rule({
    rule_id: "export.unknown_acknowledged", version: 1, layer: "export", title: "Unknown 已人工确认",
    severity: "BLOCK", consumer: "export-gate@V2.6.2",
    measurement: "review_acknowledgement 文档集覆盖当前单图与整套报告中的全部 UNKNOWN",
    unknown_policy: "hint",
  }),
]);
const RULE_BY_ID = Object.freeze(DETERMINISTIC_RULES.reduce((table, entry) => {
  table[entry.rule_id] = entry;
  return table;
}, {}));

/** 已登记规则的只读查询：消费者用它取权威严重度，不复制注册表。
 * @param {unknown} ruleId
 * @returns {Readonly<import("./type-contracts.js").ReviewRule>|null}
 */
export function registeredRule(ruleId) {
  return RULE_BY_ID[ruleId] || null;
}

/** 注册表自检：缺要素、重复 id、未知词表、consumer 无任务锚点、确认单代码未被认领都报红。
 * @param {unknown} [registry]
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkRuleRegistry(registry = DETERMINISTIC_RULES) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
  const problems = [];
  if (!Array.isArray(registry)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "规则注册表必须是数组。");
    return problems;
  }
  const seen = new Set();
  registry.forEach((entry, index) => {
    const path = "$[" + index + "]";
    if (!isPlainObject(entry)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "规则必须是对象。");
      return;
    }
    if (!isNonEmptyString(entry.rule_id)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".rule_id", "缺少 rule_id。");
    } else if (seen.has(entry.rule_id)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".rule_id",
        "rule_id 重复：" + entry.rule_id);
    } else {
      seen.add(entry.rule_id);
    }
    if (!Number.isInteger(entry.version) || entry.version < 1) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".version",
        "version 必须是正整数。");
    }
    if (REVIEW_LAYERS.indexOf(entry.layer) === -1) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".layer",
        "layer 不在词表内：" + String(entry.layer));
    }
    if (!isNonEmptyString(entry.title)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".title", "缺少 title。");
    }
    if (VIOLATION_SEVERITIES.indexOf(entry.severity) === -1) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".severity",
        "违规严重度必须是 BLOCK/HIGH_RISK/WARNING（PASS/UNKNOWN 不是规则严重度）。");
    }
    if (entry.layer === "vlm" && entry.severity === "BLOCK") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".severity",
        "VLM 层规则不得为 BLOCK：模型发现不能升级为平台硬阻断，采纳权只在人工。");
    }
    if (!isNonEmptyString(entry.consumer) || !CONSUMER_PATTERN.test(entry.consumer)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".consumer",
        "consumer 必须是「组件@V2.x.y」形式：" + String(entry.consumer));
    }
    if (!isNonEmptyString(entry.measurement)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".measurement",
        "缺少 measurement。");
    }
    if (UNKNOWN_POLICIES.indexOf(entry.unknown_policy) === -1) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".unknown_policy",
        "unknown_policy 不在词表内：" + String(entry.unknown_policy));
    }
    if (entry.blocker_codes !== undefined) {
      if (!Array.isArray(entry.blocker_codes)
          || entry.blocker_codes.some((code) => !isNonEmptyString(code))) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".blocker_codes",
          "blocker_codes 必须是非空字符串数组。");
      }
    }
    if (entry.applies_to !== undefined) {
      const roles = entry.applies_to && entry.applies_to.roles;
      if (!Array.isArray(roles) || roles.some((role) => !isNonEmptyString(role))) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".applies_to.roles",
          "applies_to.roles 必须是非空字符串数组。");
      }
    }
  });
  const claimed = new Map();
  registry.forEach((entry) => {
    if (isPlainObject(entry) && Array.isArray(entry.blocker_codes)) {
      entry.blocker_codes.forEach((code) => claimed.set(code, (claimed.get(code) || 0) + 1));
    }
  });
  Object.keys(CONFIRM_BLOCKER_CODES).forEach((name) => {
    const code = CONFIRM_BLOCKER_CODES[name];
    const count = claimed.get(code) || 0;
    if (count !== 1) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.blocker_codes",
        "确认单阻断代码 " + code + " 必须恰好被一条 generation 规则认领（当前 " + count + " 条）。");
    }
  });
  return problems;
}

/** 用注册表条目构造一条 finding；rule_id 未登记或严重度不在词表内直接报错。
 * @param {string} ruleId
 * @param {import("./type-contracts.js").ReviewSeverity} severity
 * @param {string} detail
 * @param {unknown} [measured]
 * @returns {import("./type-contracts.js").ReviewFinding}
 */
export function makeFinding(ruleId, severity, detail, measured) {
  const entry = RULE_BY_ID[ruleId];
  if (!entry) invalid("发现引用了未登记的规则：" + String(ruleId));
  if (REVIEW_SEVERITIES.indexOf(severity) === -1) invalid("发现严重度不合法：" + String(severity));
  return Object.freeze({
    rule_id: entry.rule_id,
    rule_version: entry.version,
    layer: entry.layer,
    severity: severity,
    title: entry.title,
    detail: detail,
    measured: measured === undefined ? null : measured,
  });
}

function bytesViewOf(bytes) {
  if (bytes instanceof Uint8Array) return bytes;
  if (bytes instanceof ArrayBuffer) return new Uint8Array(bytes);
  return null;
}

function recordOf(entry) {
  return entry && isPlainObject(entry.record) ? entry.record : entry;
}

function findRecordByAction(chain, actionId) {
  if (!Array.isArray(chain) || !isNonEmptyString(actionId)) return null;
  for (let index = chain.length - 1; index >= 0; index -= 1) {
    const record = recordOf(chain[index]);
    if (record && record.action_id === actionId) return record;
  }
  return null;
}

/**
 * 单图确定性检查：对候选字节与记录做平台/合同/记录三层测量。
 * bytes 为 null 表示字节不可读——对应规则降为 UNKNOWN 提示，绝不阻断；
 * 字节存在但违反合同时是 BLOCK（测量成功）。
 * @param {{candidate?: unknown, bytes?: Uint8Array|ArrayBuffer|null, roleId?: unknown}} [args]
 * @returns {import("./type-contracts.js").ReviewFinding[]}
 */
export function evaluateCandidateFindings({ candidate, bytes, roleId } = {}) {
  if (!isPlainObject(candidate)) invalid("候选检查需要候选记录。");
  /** @type {import("./type-contracts.js").ReviewFinding[]} */
  const findings = [];
  const recordProblems = checkCandidateRecord(candidate);
  const view = bytesViewOf(bytes);
  let parsed = null;
  let parseFailure = null;
  if (!view) {
    parseFailure = "字节不可读";
  } else {
    try {
      parsed = parsePngHeader(view);
    } catch (error) {
      parseFailure = (error && error.message) || "PNG 无法解析";
    }
  }

  if (parsed) {
    findings.push(makeFinding("candidate.png_contract", "PASS",
      "PNG 头可解析：" + parsed.width + "×" + parsed.height + "（颜色类型 " + parsed.color_type
      + "，位深 " + parsed.bit_depth + "）。",
      { width: parsed.width, height: parsed.height, color_type: parsed.color_type,
        bit_depth: parsed.bit_depth }));
  } else if (view) {
    findings.push(makeFinding("candidate.png_contract", "BLOCK",
      "PNG 字节不符合同：" + parseFailure, { reason: parseFailure, byte_length: view.byteLength }));
  } else {
    findings.push(makeFinding("candidate.png_contract", "UNKNOWN",
      "候选字节不可读，PNG 合同无法测量（降为提示，不阻断）。", { reason: parseFailure }));
  }

  if (recordProblems.length) {
    findings.push(makeFinding("candidate.record_consistent", "BLOCK",
      "候选记录形状不合法：" + recordProblems.map((item) => item.path + " " + item.message).join("；"),
      { problems: recordProblems }));
  } else if (parsed && view) {
    /** @type {string[]} */
    const mismatches = [];
    if (candidate.width !== parsed.width || candidate.height !== parsed.height) {
      mismatches.push("宽高 记录 " + candidate.width + "×" + candidate.height + " ≠ 字节 "
        + parsed.width + "×" + parsed.height);
    }
    if (candidate.byte_size !== view.byteLength) {
      mismatches.push("字节数 记录 " + candidate.byte_size + " ≠ 实读 " + view.byteLength);
    }
    if (candidate.media_type !== "image/png") {
      mismatches.push("媒体类型记录为 " + String(candidate.media_type));
    }
    if (mismatches.length) {
      findings.push(makeFinding("candidate.record_consistent", "BLOCK",
        "候选记录与字节不一致：" + mismatches.join("；") + "。",
        { record: { width: candidate.width, height: candidate.height,
                    byte_size: candidate.byte_size },
          measured: { width: parsed.width, height: parsed.height, byte_size: view.byteLength } }));
    } else {
      findings.push(makeFinding("candidate.record_consistent", "PASS",
        "记录与字节一致：宽高 " + parsed.width + "×" + parsed.height + "、"
        + view.byteLength + " 字节、image/png。",
        { width: parsed.width, height: parsed.height, byte_size: view.byteLength }));
    }
  } else {
    findings.push(makeFinding("candidate.record_consistent", "UNKNOWN",
      "字节不可解析，记录一致性无法测量（降为提示，不阻断）。", { reason: parseFailure }));
  }

  if (parsed) {
    const longSide = Math.max(parsed.width, parsed.height);
    if (longSide >= PLATFORM_MIN_LONG_SIDE) {
      findings.push(makeFinding("platform.min_long_side", "PASS",
        "最长边 " + longSide + "px，满足平台缩放下限 " + PLATFORM_MIN_LONG_SIDE + "px。",
        { long_side: longSide, threshold: PLATFORM_MIN_LONG_SIDE }));
    } else {
      findings.push(makeFinding("platform.min_long_side", "BLOCK",
        "最长边 " + longSide + "px 低于平台缩放下限 " + PLATFORM_MIN_LONG_SIDE
        + "px，交付后无法启用缩放。",
        { long_side: longSide, threshold: PLATFORM_MIN_LONG_SIDE }));
    }
    if (longSide >= PLATFORM_RECOMMENDED_LONG_SIDE) {
      findings.push(makeFinding("platform.recommended_long_side", "PASS",
        "最长边 " + longSide + "px，达到平台推荐值 " + PLATFORM_RECOMMENDED_LONG_SIDE + "px。",
        { long_side: longSide, threshold: PLATFORM_RECOMMENDED_LONG_SIDE }));
    } else {
      findings.push(makeFinding("platform.recommended_long_side", "WARNING",
        "最长边 " + longSide + "px 低于推荐值 " + PLATFORM_RECOMMENDED_LONG_SIDE
        + "px（不阻断；需要最佳缩放时可提高生成尺寸）。",
        { long_side: longSide, threshold: PLATFORM_RECOMMENDED_LONG_SIDE }));
    }
    if (roleId === "main") {
      const ratio = parsed.width / parsed.height;
      const delta = Math.abs(ratio - 1);
      if (delta <= MAIN_SQUARE_TOLERANCE) {
        findings.push(makeFinding("platform.main_square", "PASS",
          "主图宽高比 " + ratio.toFixed(4) + "，符合 1:1（容差 ±2%）。", { ratio: ratio }));
      } else {
        findings.push(makeFinding("platform.main_square", "WARNING",
          "主图宽高比 " + ratio.toFixed(4) + " 偏离 1:1 超过 ±2%（提醒，不阻断）。",
          { ratio: ratio, tolerance: MAIN_SQUARE_TOLERANCE }));
      }
    }
    if (parsed.has_transparency === true) {
      findings.push(makeFinding("platform.alpha_channel", "HIGH_RISK",
        "检测到透明通道（颜色类型 " + parsed.color_type
        + "）：平台主图要求纯白背景，请人工确认背景不是透明。",
        { color_type: parsed.color_type, has_transparency: true }));
    } else if (parsed.has_transparency === false) {
      findings.push(makeFinding("platform.alpha_channel", "PASS",
        "未检测到透明通道（颜色类型 " + parsed.color_type + "）。",
        { color_type: parsed.color_type, has_transparency: false }));
    } else {
      findings.push(makeFinding("platform.alpha_channel", "UNKNOWN",
        "块结构不完整，透明通道无法判定（降为提示，不阻断）。",
        { color_type: parsed.color_type }));
    }
    if (parsed.bit_depth !== null) {
      if (parsed.bit_depth > 8) {
        findings.push(makeFinding("candidate.pixel_depth", "WARNING",
          "像素位深 " + parsed.bit_depth + " 位，高于常见的 8 位（不阻断）。",
          { bit_depth: parsed.bit_depth }));
      } else {
        findings.push(makeFinding("candidate.pixel_depth", "PASS",
          "像素位深 " + parsed.bit_depth + " 位。", { bit_depth: parsed.bit_depth }));
      }
    } else {
      findings.push(makeFinding("candidate.pixel_depth", "UNKNOWN",
        "头部不足，像素位深无法测量（降为提示，不阻断）。", { bit_depth: null }));
    }
  } else {
    const pending = ["platform.min_long_side", "platform.recommended_long_side",
      "platform.alpha_channel", "candidate.pixel_depth"];
    if (roleId === "main") pending.push("platform.main_square");
    pending.forEach((ruleId) => {
      findings.push(makeFinding(ruleId, "UNKNOWN",
        "字节不可用，" + RULE_BY_ID[ruleId].title + "无法测量（降为提示，不阻断）。",
        { reason: parseFailure }));
    });
  }
  return Object.freeze(findings);
}

/**
 * 生成前确定性检查：只消费 confirm.buildConfirmationSheet 的 blockers / risks，
 * 不复制确认单自身的判断；每个 blocker 代码必须被注册表认领（未登记直接报错）。
 * @param {unknown} sheet
 * @returns {import("./type-contracts.js").ExportReadiness}
 */
export function evaluateGenerationFindings(sheet) {
  if (!isPlainObject(sheet) || !Array.isArray(sheet.shots)) {
    invalid("生成前检查需要确认单（shots 数组）。");
  }
  const codeRules = {};
  DETERMINISTIC_RULES.forEach((entry) => {
    if (entry.layer === "generation" && Array.isArray(entry.blocker_codes)) {
      entry.blocker_codes.forEach((code) => { codeRules[code] = entry; });
    }
  });
  /** @type {import("./type-contracts.js").ReviewFinding[]} */
  const findings = [];
  sheet.shots.forEach((shot) => {
    if (!isPlainObject(shot)) return;
    const shotId = isNonEmptyString(shot.shot_id) ? shot.shot_id : null;
    const label = isNonEmptyString(shot.label) ? shot.label : String(shotId);
    const blockers = Array.isArray(shot.blockers) ? shot.blockers : [];
    const risks = Array.isArray(shot.risks) ? shot.risks : [];
    blockers.forEach((blocker) => {
      const code = blocker && blocker.code;
      const entry = codeRules[code];
      if (!entry) invalid("确认单阻断代码未登记：" + String(code));
      findings.push(makeFinding(entry.rule_id, entry.severity,
        "「" + label + "」" + ((blocker && blocker.message) || "依据未满足"),
        { shot_id: shotId, code: code, fix: (blocker && blocker.fix) || null }));
    });
    risks.forEach((risk) => {
      findings.push(makeFinding("generation.risk_visible", "WARNING",
        "「" + label + "」" + ((risk && (risk.message || risk.reason)) || "确认单提示项"),
        { shot_id: shotId }));
    });
  });
  return Object.freeze({
    ready: !findings.some((finding) => finding.severity === "BLOCK"),
    findings: Object.freeze(findings),
  });
}

function reportPayloadOf(entry) {
  if (!isPlainObject(entry)) return null;
  return isPlainObject(entry.report) ? entry.report : entry;
}

/**
 * 导出就绪检查：选择完整性、报告当前性、报告无阻断、选择链完整性（同步部分）。
 * selections 是 {shot_id: candidate_id} 的最小投影；字节哈希复算见 verifyAssetHashes。
 * @param {{shots?: unknown, selections?: unknown, candidatesByShot?: unknown,
 *          reportsByCandidate?: unknown, attemptsByShot?: unknown}} [args]
 * @returns {import("./type-contracts.js").ExportReadiness}
 */
export function evaluateExportReadiness({ shots, selections, candidatesByShot,
                                          reportsByCandidate, attemptsByShot } = {}) {
  if (!Array.isArray(shots)) invalid("导出检查需要套图计划 shots。");
  const selectionMap = isPlainObject(selections) ? selections : {};
  /** @type {import("./type-contracts.js").ReviewFinding[]} */
  const findings = [];

  const requiredShots = shots.filter((shot) => shot && shot.required === true);
  const missing = requiredShots
    .filter((shot) => !isNonEmptyString(selectionMap[shot.shot_id]))
    .map((shot) => shot.shot_id);
  if (missing.length) {
    findings.push(makeFinding("export.selection_complete", "BLOCK",
      "缺少必需选择：" + missing.join("、") + "。",
      { missing: missing, required: requiredShots.map((shot) => shot.shot_id) }));
  } else {
    findings.push(makeFinding("export.selection_complete", "PASS",
      "必需 Shot 选择完整（" + requiredShots.length + " 项）。",
      { required_count: requiredShots.length }));
  }

  /** @type {string[]} */
  const chainIssues = [];
  /** @type {string[]} */
  const reportIssues = [];
  /** @type {string[]} */
  const blockingIssues = [];
  let checked = 0;
  shots.forEach((shot) => {
    if (!shot || !isNonEmptyString(shot.shot_id)) return;
    const shotId = shot.shot_id;
    const candidateId = selectionMap[shotId];
    if (!isNonEmptyString(candidateId)) return;
    checked += 1;
    const chain = candidatesByShot && Array.isArray(candidatesByShot[shotId])
      ? candidatesByShot[shotId] : [];
    const candidate = findRecordByAction(chain, candidateId);
    if (!candidate) {
      chainIssues.push(shotId + " 的选择指向不存在的候选");
      return;
    }
    const attemptChain = attemptsByShot && Array.isArray(attemptsByShot[shotId])
      ? attemptsByShot[shotId] : [];
    const attempt = findRecordByAction(attemptChain, candidateId);
    if (!attempt || !candidateMatchesAttempt(candidate, attempt)) {
      chainIssues.push(shotId + "：" + (attempt ? "候选与来源 Attempt 不一致" : "来源 Attempt 缺失"));
    }
    const report = reportPayloadOf(reportsByCandidate && reportsByCandidate[candidateId]);
    if (!report || !reviewIsCurrent(report, candidate)) {
      reportIssues.push(shotId + "：" + (report
        ? "报告合同版本不是当前（" + String(report.review_contract_version) + "）"
        : "没有报告"));
    } else if (Array.isArray(report.findings)
        && report.findings.some((finding) => finding && finding.severity === "BLOCK")) {
      blockingIssues.push(shotId);
    }
  });

  if (chainIssues.length) {
    findings.push(makeFinding("export.chain_integrity", "BLOCK",
      "选择链不完整：" + chainIssues.join("；") + "。", { issues: chainIssues }));
  } else {
    findings.push(makeFinding("export.chain_integrity", "PASS",
      "选择 → 候选 → 来源 Attempt 身份一致（核对 " + checked + " 条选择）。",
      { checked: checked }));
  }
  if (reportIssues.length) {
    findings.push(makeFinding("export.report_current", "BLOCK",
      "以下选择的报告不是当前版本：" + reportIssues.join("；") + "。",
      { issues: reportIssues }));
  } else {
    findings.push(makeFinding("export.report_current", "PASS",
      "所选候选都有当前报告（核对 " + checked + " 条选择）。", { checked: checked }));
  }
  if (blockingIssues.length) {
    findings.push(makeFinding("export.no_blocking_findings", "BLOCK",
      "以下选择的报告里还有阻断项：" + blockingIssues.join("、") + "。",
      { shots: blockingIssues }));
  } else {
    findings.push(makeFinding("export.no_blocking_findings", "PASS",
      "所选报告均不含阻断项（核对 " + checked + " 条选择）。", { checked: checked }));
  }

  return Object.freeze({
    exportable: !findings.some((finding) => finding.severity === "BLOCK"),
    findings: Object.freeze(findings),
  });
}
/**
 * 交付字节哈希复算：readBytes 由调用方注入（读 IndexedDB Blob），digest 必须是 storage/db.js 的
 * sha256Hex；本层不写第二种散列。缺失与不一致都是 BLOCK。
 * @param {{selections?: unknown, candidatesByShot?: unknown, readBytes?: unknown, digest?: unknown}} [args]
 * @returns {Promise<import("./type-contracts.js").AssetHashCheck>}
 */
export async function verifyAssetHashes({ selections, candidatesByShot, readBytes, digest } = {}) {
  if (typeof readBytes !== "function") invalid("哈希复算需要 readBytes(asset_sha256)。");
  if (typeof digest !== "function") invalid("哈希复算需要注入 digest（storage/db.js 的 sha256Hex）。");
  const selectionMap = isPlainObject(selections) ? selections : {};
  /** @type {import("./type-contracts.js").ReviewFinding[]} */
  const findings = [];
  /** @type {string[]} */
  const missing = [];
  /** @type {string[]} */
  const mismatches = [];
  /** @type {string[]} */
  const passed = [];
  const shotIds = Object.keys(selectionMap);
  for (const shotId of shotIds) {
    const candidateId = selectionMap[shotId];
    if (!isNonEmptyString(candidateId)) continue;
    const chain = candidatesByShot && Array.isArray(candidatesByShot[shotId])
      ? candidatesByShot[shotId] : [];
    const candidate = findRecordByAction(chain, candidateId);
    if (!candidate) {
      missing.push(shotId + "：候选记录缺失");
      continue;
    }
    let bytes = null;
    try {
      bytes = await readBytes(candidate.asset_sha256);
    } catch (error) {
      bytes = null;
    }
    if (!bytes) {
      missing.push(shotId + "：字节缺失");
      continue;
    }
    const actual = await digest(bytes);
    if (actual !== candidate.asset_sha256) {
      mismatches.push(shotId + "：" + String(actual).slice(0, 12) + "… ≠ "
        + String(candidate.asset_sha256).slice(0, 12) + "…");
    } else {
      passed.push(shotId);
    }
  }
  if (missing.length || mismatches.length) {
    findings.push(makeFinding("export.asset_hash_matches", "BLOCK",
      "交付字节哈希核对失败：" + missing.concat(mismatches).join("；") + "。",
      { missing: missing, mismatches: mismatches, passed: passed.length }));
  } else {
    findings.push(makeFinding("export.asset_hash_matches", "PASS",
      "交付字节哈希与候选记录一致（核对 " + passed.length + " 条）。", { passed: passed.length }));
  }
  return Object.freeze({
    ok: !(missing.length || mismatches.length),
    findings: Object.freeze(findings),
  });
}

/** VLM 复核块形状：绑定候选身份与合同版本；outcome 只有 checked / unknown。 */
function checkVlmBlock(vlm, problems, path) {
  if (!isPlainObject(vlm)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "VLM 复核块必须是对象。");
    return;
  }
  if (VLM_OUTCOMES.indexOf(vlm.outcome) === -1) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".outcome",
      "outcome 必须是 checked/unknown：" + String(vlm.outcome));
  }
  if (vlm.contract_version !== REVIEW_CONTRACT_VERSION) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".contract_version",
      "VLM 复核块必须绑定当前合同版本：" + String(vlm.contract_version));
  }
  if (!isSha256Hex(vlm.asset_sha256)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".asset_sha256",
      "缺少候选字节身份（64 位 sha256）。");
  }
  if (!isIsoTimestamp(vlm.checked_at)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".checked_at",
      "缺少 ISO 复核时间。");
  }
  ["provider_id", "model_id", "request_id", "summary"].forEach((key) => {
    const value = vlm[key];
    if (value !== null && value !== undefined && typeof value !== "string") {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + "." + key,
        key + " 只允许字符串或 null。");
    }
  });
}

/**
 * 一次复核信封 → VLM findings + 复核块。成功信封必须是 checked 结果且绑定当前候选；
 * 失败信封一律投影为 UNKNOWN（不伪造 PASS、不阻塞人工），并保留分类原因。
 * @param {{candidate?: unknown, review?: unknown, at?: unknown}} [args]
 * @returns {{outcome: import("./type-contracts.js").VlmOutcome,
 *            findings: import("./type-contracts.js").ReviewFinding[],
 *            vlm: import("./type-contracts.js").VlmBlock}}
 */
export function buildVlmReview({ candidate, review, at } = {}) {
  if (!isPlainObject(candidate) || !isNonEmptyString(candidate.candidate_id)
      || !isNonEmptyString(candidate.shot_id) || !isSha256Hex(candidate.asset_sha256)) {
    invalid("VLM 复核需要候选身份（candidate_id / shot_id / asset_sha256）。");
  }
  if (!isIsoTimestamp(at)) invalid("VLM 复核需要 ISO 时间（at）。");
  if (!isPlainObject(review) || typeof review.ok !== "boolean") {
    invalid("VLM 复核需要服务端信封（ok 标记）。");
  }
  /** @type {import("./type-contracts.js").ReviewFinding[]} */
  const findings = [];
  let vlm = null;
  if (review.ok === true) {
    const result = review.result;
    if (!isPlainObject(result)) invalid("复核成功信封缺少 result。");
    if (result.contract_version !== REVIEW_CONTRACT_VERSION) {
      invalid("复核结果的合同版本与当前规则不一致：" + String(result.contract_version));
    }
    if (result.candidate_sha256 !== candidate.asset_sha256) {
      invalid("复核结果绑定的是另一个候选（sha256 不一致）。");
    }
    if (!Array.isArray(result.findings) || result.findings.length > VLM_MAX_FINDINGS) {
      invalid("复核 findings 必须是数组且不超过 " + VLM_MAX_FINDINGS + " 条。");
    }
    result.findings.forEach((item) => {
      if (!isPlainObject(item)) invalid("复核发现必须是对象。");
      const ruleId = VLM_CHECK_TO_RULE[item.check];
      if (!ruleId) invalid("复核发现引用了未登记的 check：" + String(item.check));
      if (!isNonEmptyString(item.evidence) || item.evidence.length > VLM_MAX_EVIDENCE_LENGTH) {
        invalid("复核证据必须是非空短文本（≤" + VLM_MAX_EVIDENCE_LENGTH + " 字符）。");
      }
      if (typeof item.confidence !== "number" || !Number.isFinite(item.confidence)
          || item.confidence < 0 || item.confidence > 1) {
        invalid("复核置信度必须在 0..1 之间。");
      }
      const entry = RULE_BY_ID[ruleId];
      findings.push(makeFinding(ruleId, entry.severity, item.evidence, {
        check: item.check,
        confidence: item.confidence,
        provider_id: result.provider_id || null,
        model_id: result.model_id || null,
        request_id: result.request_id || null,
        checked_at: result.checked_at || at,
        candidate_sha256: result.candidate_sha256,
      }));
    });
    if (findings.length === 0) {
      findings.push(makeFinding("vlm.inspection_completed", "PASS",
        "VLM 复核完成，未报告问题（这只是机器事实，不等于人工采纳）。", {
          provider_id: result.provider_id || null,
          model_id: result.model_id || null,
          request_id: result.request_id || null,
          checked_at: result.checked_at || at,
        }));
    }
    vlm = {
      outcome: "checked",
      contract_version: REVIEW_CONTRACT_VERSION,
      asset_sha256: candidate.asset_sha256,
      candidate_id: candidate.candidate_id,
      shot_id: candidate.shot_id,
      provider_id: result.provider_id || null,
      model_id: result.model_id || null,
      request_id: result.request_id || null,
      checked_at: result.checked_at || at,
      latency_ms: typeof result.latency_ms === "number" ? result.latency_ms : null,
      summary: typeof result.summary === "string" ? result.summary.slice(0, 500) : "",
    };
  } else {
    const error = isPlainObject(review.error) ? review.error : {};
    const family = isNonEmptyString(error.family) ? error.family : "internal";
    const code = isNonEmptyString(error.code) ? error.code : "REVIEW_FAILED";
    const retry = isNonEmptyString(error.retry_policy) ? error.retry_policy : "requires_review";
    const message = isNonEmptyString(error.message) ? error.message.slice(0, 300) : "复核未完成。";
    findings.push(makeFinding("vlm.inspection_unavailable", "UNKNOWN",
      "VLM 复核未完成（" + family + "/" + code + "）：" + message
      + "；人工审核不因此受阻。", {
        family: family, code: code, retry_policy: retry,
        request_id: error.request_id || null, at: at,
      }));
    vlm = {
      outcome: "unknown",
      contract_version: REVIEW_CONTRACT_VERSION,
      asset_sha256: candidate.asset_sha256,
      candidate_id: candidate.candidate_id,
      shot_id: candidate.shot_id,
      provider_id: null,
      model_id: null,
      request_id: error.request_id || null,
      checked_at: at,
      latency_ms: null,
      summary: "",
    };
  }
  return Object.freeze({
    outcome: vlm.outcome,
    findings: Object.freeze(findings),
    vlm: Object.freeze(vlm),
  });
}

/** 把一次复核合并进当前报告：确定性 findings 保留，VLM 层整体替换，报告身份不变。
 * @param {{report?: unknown, candidate?: unknown, review?: unknown, at?: unknown}} [args]
 * @returns {import("./type-contracts.js").ReviewReport}
 */
export function mergeVlmReview({ report, candidate, review, at } = {}) {
  if (!isPlainObject(report)) invalid("合并复核需要已有报告。");
  if (!reviewIsCurrent(report, candidate)) {
    invalid("合并复核要求报告对当前候选仍然有效（先重建确定性报告）。");
  }
  const deterministic = report.findings.filter((item) => item && item.layer !== "vlm");
  const built = buildVlmReview({ candidate: candidate, review: review, at: at });
  return buildReviewReport({
    candidate: candidate,
    findings: deterministic.concat(built.findings),
    vlm: built.vlm,
    at: at,
  });
}

/**
 * ReviewReport：绑定 candidate_id + review_contract_version + asset_sha256 的不可变快照。
 * findings 只允许引用注册表里的规则；summary 是逐严重度计数（由本函数计算，不接受外部传入）。
 * @param {{candidate?: unknown, findings?: unknown, vlm?: unknown, at?: unknown}} [args]
 * @returns {import("./type-contracts.js").ReviewReport}
 */
export function buildReviewReport({ candidate, findings, vlm, at } = {}) {
  if (!isPlainObject(candidate)) invalid("报告需要候选记录。");
  if (!isNonEmptyString(candidate.candidate_id) || !isNonEmptyString(candidate.shot_id)
      || !isSha256Hex(candidate.asset_sha256)) {
    invalid("报告需要候选身份字段（candidate_id / shot_id / asset_sha256）。");
  }
  if (!isIsoTimestamp(at)) invalid("报告需要 ISO 时间（at）。");
  if (!Array.isArray(findings) || findings.length === 0) invalid("报告需要非空 findings 数组。");
  if (vlm !== undefined && vlm !== null) {
    const vlmProblems = [];
    checkVlmBlock(vlm, vlmProblems, "$.vlm");
    if (vlmProblems.length) invalid("VLM 复核块不合法：" + vlmProblems[0].message);
    if (vlm.asset_sha256 !== candidate.asset_sha256) {
      invalid("VLM 复核块必须绑定同一候选字节。");
    }
  }
  const normalized = findings.map((item) => {
    if (!isPlainObject(item)) invalid("发现必须是对象。");
    const entry = RULE_BY_ID[item.rule_id];
    if (!entry) invalid("发现引用了未登记的规则：" + String(item.rule_id));
    if (REVIEW_SEVERITIES.indexOf(item.severity) === -1) {
      invalid("发现严重度不合法：" + String(item.severity));
    }
    if (!isNonEmptyString(item.detail)) invalid("发现必须有 detail。");
    return Object.freeze({
      rule_id: entry.rule_id,
      rule_version: Number.isInteger(item.rule_version) ? item.rule_version : entry.version,
      layer: entry.layer,
      severity: item.severity,
      title: isNonEmptyString(item.title) ? item.title : entry.title,
      detail: item.detail,
      measured: item.measured === undefined ? null : item.measured,
    });
  });
  const summary = { BLOCK: 0, HIGH_RISK: 0, WARNING: 0, PASS: 0, UNKNOWN: 0 };
  normalized.forEach((item) => { summary[item.severity] += 1; });
  return Object.freeze({
    schema_version: REVIEW_REPORT_SCHEMA_VERSION,
    review_contract_version: REVIEW_CONTRACT_VERSION,
    candidate_id: candidate.candidate_id,
    shot_id: candidate.shot_id,
    asset_sha256: candidate.asset_sha256,
    vlm: vlm === undefined || vlm === null ? null : Object.freeze({ ...vlm }),
    summary: Object.freeze(summary),
    findings: Object.freeze(normalized),
    created_at: at,
  });
}

/** 报告形状检查；summary 与 findings 计数不一致也算不合法（报告不允许自相矛盾）。
 * @param {unknown} report
 * @returns {import("./type-contracts.js").DomainProblem[]}
 */
export function checkReviewReport(report) {
  /** @type {import("./type-contracts.js").DomainProblem[]} */
  const problems = [];
  if (!isPlainObject(report)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "审核报告必须是对象。");
    return problems;
  }
  checkSchemaVersion(report, REVIEW_REPORT_SCHEMA_VERSION, problems, "$");
  if (!isNonEmptyString(report.review_contract_version)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.review_contract_version",
      "缺少合同版本。");
  }
  if (!isNonEmptyString(report.candidate_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.candidate_id", "缺少 candidate_id。");
  }
  if (!isNonEmptyString(report.shot_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shot_id", "缺少 shot_id。");
  }
  if (!isSha256Hex(report.asset_sha256)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.asset_sha256",
      "asset_sha256 必须是 64 位十六进制。");
  }
  if (!isIsoTimestamp(report.created_at)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.created_at", "缺少 ISO 时间。");
  }
  if (report.vlm !== undefined && report.vlm !== null) {
    checkVlmBlock(report.vlm, problems, "$.vlm");
    if (isPlainObject(report.vlm) && report.vlm.asset_sha256 !== report.asset_sha256) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.vlm.asset_sha256",
        "VLM 复核块必须绑定同一候选字节。");
    }
  }
  if (!Array.isArray(report.findings) || report.findings.length === 0) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.findings",
      "findings 必须是非空数组。");
  } else {
    const counts = { BLOCK: 0, HIGH_RISK: 0, WARNING: 0, PASS: 0, UNKNOWN: 0 };
    report.findings.forEach((item, index) => {
      const path = "$.findings[" + index + "]";
      if (!isPlainObject(item)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path, "发现必须是对象。");
        return;
      }
      if (!isNonEmptyString(item.rule_id) || !RULE_BY_ID[item.rule_id]) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".rule_id",
          "发现引用了未登记的规则：" + String(item.rule_id));
      }
      if (REVIEW_SEVERITIES.indexOf(item.severity) === -1) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".severity",
          "严重度不在词表内：" + String(item.severity));
      } else {
        counts[item.severity] += 1;
      }
      if (!isNonEmptyString(item.detail)) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, path + ".detail", "缺少 detail。");
      }
    });
    if (!isPlainObject(report.summary)) {
      pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.summary", "缺少 summary。");
    } else {
      REVIEW_SEVERITIES.forEach((severity) => {
        if (report.summary[severity] !== counts[severity]) {
          pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.summary." + severity,
            "汇总与 findings 计数不一致（" + report.summary[severity] + " ≠ "
            + counts[severity] + "）。");
        }
      });
    }
  }
  return problems;
}

/** 报告是否对当前候选与当前合同版本仍然有效。
 * @param {unknown} report
 * @param {unknown} candidate
 * @returns {boolean}
 */
export function reviewIsCurrent(report, candidate) {
  if (!isPlainObject(report) || !isPlainObject(candidate)) return false;
  return report.review_contract_version === REVIEW_CONTRACT_VERSION
    && report.candidate_id === candidate.candidate_id
    && report.shot_id === candidate.shot_id
    && report.asset_sha256 === candidate.asset_sha256;
}

/** 最需要人工先看的发现：BLOCK > HIGH_RISK > WARNING > UNKNOWN；全 PASS 返回 null。
 * @param {unknown} report
 * @returns {import("./type-contracts.js").ReviewFinding|null}
 */
export function topFinding(report) {
  const findings = report && Array.isArray(report.findings) ? report.findings : [];
  for (const severity of REVIEW_SEVERITY_ORDER) {
    const hit = findings.find((item) => item && item.severity === severity);
    if (hit) return hit;
  }
  return null;
}

/** 界面一行摘要：只报需要行动的数量，不重复全部细节。
 * @param {unknown} report
 * @returns {string}
 */
export function reviewSummaryText(report) {
  const summary = report && isPlainObject(report.summary) ? report.summary : {};
  const vlm = report && isPlainObject(report.vlm) ? report.vlm : null;
  const vlmText = vlm
    ? (vlm.outcome === "checked" ? "VLM 已检查" : "VLM 未完成")
    : "VLM 未检查";
  return "自动检查 " + String(report && report.review_contract_version)
    + "：阻断 " + Number(summary.BLOCK || 0)
    + " · 高风险 " + Number(summary.HIGH_RISK || 0)
    + " · 提醒 " + Number(summary.WARNING || 0)
    + " · 未知 " + Number(summary.UNKNOWN || 0)
    + " · " + vlmText;
}

/**
 * 单图报告的复核状态投影（manifest / 界面共用，V2.R6.2）：
 * reviewed = 真跑过 AI 且绑定候选字节；unknown = 真发起但失败/不确定（保留原因与请求号）；
 * not_reviewed = 没发起 AI 复核——这是「未调用」，不是模型判断，也不阻断确定性交付。
 * @param {unknown} report
 * @returns {{status: "reviewed"|"unknown"|"not_reviewed", reason: string|null,
 *            checked_at: string|null, request_id: string|null}}
 */
export function reviewStatusOf(report) {
  const vlm = report && isPlainObject(report.vlm) ? report.vlm : null;
  if (!vlm) return Object.freeze({ status: "not_reviewed", reason: "not_run",
    checked_at: null, request_id: null });
  if (vlm.outcome === "checked") {
    return Object.freeze({ status: "reviewed", reason: null,
      checked_at: vlm.checked_at || null, request_id: vlm.request_id || null });
  }
  return Object.freeze({ status: "unknown", reason: "unknown",
    checked_at: vlm.checked_at || null, request_id: vlm.request_id || null });
}
