/**
 * V2.5.4 返工：固定问题分类、改进方向与返工指令（唯一权威）。
 *
 * 返工不是「重新生成整张图」的自由文本，而是把「这次要改什么」固化成一条绑定
 * 候选字节 + 复核报告 + 用户方向的 ReworkDirective，再交给 Prompt 编译器作为独立段落。
 * 本模块不写存储、不调用模型、不改 ShotSpec；旧 Prompt 版本与旧候选一律保留。
 */
import { DOMAIN_ERROR_CODES, invalid } from "./errors.js";
import { REVIEW_CONTRACT_VERSION, topFinding } from "./review.js";
import { isIsoTimestamp, isNonEmptyString, isPlainObject, isSha256Hex,
         pushProblem } from "./shared.js";

export const REWORK_CONTRACT_VERSION = "v2.5.4";
export const REWORK_SCHEMA_VERSION = 1;
export const REWORK_DIRECTION_MIN = 4;
export const REWORK_DIRECTION_MAX = 300;

/** 固定问题分类（计划 §8.3）：问题是对现象的分类，改进方向是本次要改变什么。 */
export const REWORK_PROBLEMS = Object.freeze([
  { id: "product_fidelity", label: "商品失真", hint: "颜色、材质、比例、标识或部件与参考图不一致" },
  { id: "part_error", label: "部件错误", hint: "多出、缺失、错位的部件或穿模" },
  { id: "scene", label: "场景", hint: "背景或使用场景不合适" },
  { id: "composition", label: "构图", hint: "主体大小、角度、留白或版式不合适" },
  { id: "selling_point", label: "卖点表达", hint: "卖点没表达清楚或表达错了" },
  { id: "text", label: "文字", hint: "图中文字乱码、错字或不符合平台语言" },
  { id: "style", label: "风格", hint: "与整套公共风格不一致" },
  { id: "platform_risk", label: "平台风险", hint: "尺寸、背景、水印、禁止内容等平台规则问题" },
  { id: "other", label: "其他", hint: "上面的分类都不合适，用方向写清楚" },
]);

export const REWORK_PROBLEM_IDS = Object.freeze(REWORK_PROBLEMS.map((item) => item.id));

const PROBLEM_BY_ID = Object.freeze(REWORK_PROBLEMS.reduce((table, item) => {
  table[item.id] = item;
  return table;
}, {}));

/** 复核规则 → 问题分类：只用于预选，用户可以改。 */
export const REWORK_RULE_PROBLEM = Object.freeze({
  "candidate.png_contract": "platform_risk",
  "platform.min_long_side": "platform_risk",
  "platform.recommended_long_side": "platform_risk",
  "platform.main_square": "platform_risk",
  "platform.alpha_channel": "platform_risk",
  "candidate.pixel_depth": "platform_risk",
  "vlm.product_fidelity": "product_fidelity",
  "vlm.part_anomaly": "part_error",
  "vlm.deformity": "product_fidelity",
  "vlm.clipping": "part_error",
  "vlm.garbled_text": "text",
  "vlm.goal_completion": "composition",
  "vlm.prohibited_content": "platform_risk",
});

export function reworkProblemLabel(id) {
  const entry = PROBLEM_BY_ID[id];
  return entry ? entry.label : String(id);
}

export function reworkProblemHint(id) {
  const entry = PROBLEM_BY_ID[id];
  return entry ? entry.hint : "";
}

/** 报告先看项建议的问题分类；没有发现时返回空数组（用户自己选）。 */
export function suggestReworkProblems(report) {
  const top = topFinding(report);
  if (!top) return [];
  const mapped = REWORK_RULE_PROBLEM[top.rule_id];
  return mapped ? [mapped] : [];
}

/**
 * 建议方向：把先看项翻译成一句可编辑的默认文案。
 * 不用「」包住标题，避免与编译器「逐字引用」的括号约定互相干扰。
 */
export function suggestedReworkDirection(report) {
  const top = topFinding(report);
  if (!top) return "";
  const detail = String(top.detail || "").slice(0, 80);
  return "上一版被标记为（" + String(top.title || top.rule_id) + "）：" + detail
    + " 只修改这一点，其余部分保持与参考图一致。";
}

/** 方向文本归一：把引号字符换成括号，保证它作为逐字引用内容时括号不互相干扰。 */
export function normalizeReworkDirection(direction) {
  if (direction === null || direction === undefined) return "";
  return String(direction)
    .replace(/[「『]/g, "（")
    .replace(/[」』]/g, "）")
    .replace(/[\r\n\t]+/g, " ")
    .trim();
}

/**
 * 返工指令：绑定「哪一张图、哪一条候选、因为什么、要改成什么」。
 * problems 与 direction 至少要有一个；两者都留空等于没有返工理由，直接拒绝。
 */
export function buildReworkDirective({ directiveId, shotId, candidate, report, problems,
                                       direction, at } = {}) {
  if (!isNonEmptyString(directiveId)) invalid("返工指令需要唯一 ID。");
  if (!isNonEmptyString(shotId)) invalid("返工指令需要 shot_id。");
  if (!isPlainObject(candidate) || !isNonEmptyString(candidate.candidate_id)
      || !isSha256Hex(candidate.asset_sha256)) {
    invalid("返工指令必须绑定一条候选（candidate_id + sha256）。");
  }
  if (candidate.shot_id !== shotId) invalid("这条候选不属于这张图，不能用它做返工依据。");
  const list = Array.isArray(problems)
    ? [...new Set(problems.filter((item) => isNonEmptyString(item)))] : [];
  const unknown = list.filter((id) => REWORK_PROBLEM_IDS.indexOf(id) === -1);
  if (unknown.length > 0) invalid("未知的问题分类：" + unknown.join("、"));
  const text = normalizeReworkDirection(direction);
  if (list.length === 0 && text.length === 0) {
    invalid("返工至少要选一个问题分类，或写一句改进方向。");
  }
  if (text.length > 0 && (text.length < REWORK_DIRECTION_MIN || text.length > REWORK_DIRECTION_MAX)) {
    invalid("改进方向需要在 " + REWORK_DIRECTION_MIN + "–" + REWORK_DIRECTION_MAX + " 字之间。");
  }
  if (!isIsoTimestamp(at)) invalid("返工指令需要 ISO 时间（at）。");
  const top = isPlainObject(report) ? topFinding(report) : null;
  return Object.freeze({
    schema_version: REWORK_SCHEMA_VERSION,
    contract_version: REWORK_CONTRACT_VERSION,
    directive_id: directiveId,
    shot_id: shotId,
    candidate_id: candidate.candidate_id,
    candidate_sha256: candidate.asset_sha256,
    problems: Object.freeze(list),
    direction: text,
    source: Object.freeze({
      candidate_id: candidate.candidate_id,
      asset_sha256: candidate.asset_sha256,
      review_contract_version: isPlainObject(report) && isNonEmptyString(report.review_contract_version)
        ? report.review_contract_version : null,
      top_rule_id: top ? top.rule_id : null,
      top_severity: top ? top.severity : null,
    }),
    created_at: at,
  });
}

export function checkReworkDirective(directive) {
  const problems = [];
  if (!isPlainObject(directive)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$", "返工指令必须是对象。");
    return problems;
  }
  if (directive.schema_version !== REWORK_SCHEMA_VERSION) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.schema_version",
      "返工指令版本不认识：" + String(directive.schema_version));
  }
  if (directive.contract_version !== REWORK_CONTRACT_VERSION) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.contract_version",
      "返工指令合同版本不是当前版本。");
  }
  if (!isNonEmptyString(directive.directive_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.directive_id", "缺少指令 ID。");
  }
  if (!isNonEmptyString(directive.shot_id)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.shot_id", "缺少 shot_id。");
  }
  if (!isNonEmptyString(directive.candidate_id) || !isSha256Hex(directive.candidate_sha256)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.candidate_id",
      "返工指令必须绑定候选身份。");
  }
  const list = Array.isArray(directive.problems) ? directive.problems : null;
  if (!list) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.problems", "问题分类必须是数组。");
  } else {
    list.forEach((id, index) => {
      if (REWORK_PROBLEM_IDS.indexOf(id) === -1) {
        pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.problems[" + index + "]",
          "未知的问题分类：" + String(id));
      }
    });
  }
  const text = typeof directive.direction === "string" ? directive.direction : null;
  if (text === null) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.direction", "方向必须是字符串。");
  } else if (text.length > 0 && text.length > REWORK_DIRECTION_MAX) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.direction",
      "改进方向超过 " + REWORK_DIRECTION_MAX + " 字。");
  }
  if ((list ? list.length : 0) === 0 && !text) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$",
      "返工至少要有一个问题分类或一句方向。");
  }
  if (!isIsoTimestamp(directive.created_at)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.created_at", "缺少 ISO 时间。");
  }
  if (!isPlainObject(directive.source)) {
    pushProblem(problems, DOMAIN_ERROR_CODES.CONTRACT_INVALID, "$.source", "缺少来源绑定。");
  }
  return problems;
}

export function assertReworkDirective(directive) {
  const problems = checkReworkDirective(directive);
  if (problems.length > 0) invalid("返工指令不合法：" + problems[0].message);
  return directive;
}

/** 指令是否仍对这条候选有效：候选换了或复核合同升级了，就必须重新发起返工。 */
export function reworkIsCurrent(directive, candidate) {
  if (!isPlainObject(directive) || !isPlainObject(candidate)) return false;
  return directive.contract_version === REWORK_CONTRACT_VERSION
    && directive.candidate_id === candidate.candidate_id
    && directive.shot_id === candidate.shot_id
    && directive.candidate_sha256 === candidate.asset_sha256;
}

/** 界面一行摘要：问题分类 + 方向；不含命令，也不暗示已经采纳。 */
export function reworkSummaryText(directive) {
  if (!isPlainObject(directive)) return "";
  const labels = (Array.isArray(directive.problems) ? directive.problems : [])
    .map(reworkProblemLabel);
  const parts = [];
  if (labels.length > 0) parts.push(labels.join("、"));
  if (isNonEmptyString(directive.direction)) parts.push("方向：" + directive.direction);
  return parts.join(" · ");
}

/** 复核合同版本（供界面提示：报告先看项来自哪个版本）。 */
export function reworkReviewContract() {
  return REVIEW_CONTRACT_VERSION;
}
