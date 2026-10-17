/**
 * 视图共享的无状态格式化、排序助手与展示词表。
 *
 * 不放业务状态、订阅、DOM 或网络；规则判据仍归 domain 与业务 owner，
 * 节点和交互由各视图的声明式模板负责。
 *
 * 本文件是唯一手工维护实现；浏览器只消费 Vite 构建产物。
 */

/** 严重度 → 徽标样式；颜色只表达优先级，不改变任何规则判定。 */
export const SEVERITY_BADGE: Readonly<Record<string, string>> = Object.freeze({
  BLOCK: "is-review-block", HIGH_RISK: "is-review-high", WARNING: "is-review-warn",
  UNKNOWN: "is-review-unknown", PASS: "is-review-pass",
});

export const COMPARE_STATE_BADGE: Readonly<Record<string, string>> = Object.freeze({
  pending: "is-review-high", unknown: "is-review-unknown", clean: "is-review-pass",
  unchecked: "is-review-unchecked",
});

export const STATUS_TEXT: Readonly<Record<string, string>> = Object.freeze({
  confirmed: "已确认", proposed: "模型提案", missing: "缺失",
  conflict: "冲突", unknown: "未知", superseded: "已移除",
});

export const AUTHORITY_TEXT: Readonly<Record<string, string>> = Object.freeze({
  core_fixed: "系统固定", category_dynamic: "品类动态", user_custom: "自定义", derived: "派生",
});

export const ROLE_TEXT: Readonly<Record<string, string>> = Object.freeze({
  primary: "商品主图", detail: "细节图", packaging: "包装图", scene: "场景参考",
  competitor: "竞品参考", other: "其他",
});

export const EVIDENCE_TEXT: Readonly<Record<string, string>> = Object.freeze({
  user: "用户输入", asset: "参考图", model: "模型", rule: "规则",
});

/** 审核优先级：冲突 → 未知 → 缺失 → 未确认 → 已确认 → 已移除。 */
export const REVIEW_ORDER: Readonly<Record<string, number>> = Object.freeze({
  conflict: 0, unknown: 1, missing: 2, proposed: 3, confirmed: 4, superseded: 5,
});

/** 列表排序键用的最小槽位形状（domain 的 FactSlot 是其超集）。 */
export type RankableSlot = { slot: { status: string; critical?: boolean } };

/**
 * 列表排序键：把「必须确认（critical）且尚未收尾」提到冲突/未知之后、缺失之前。
 *
 * critical 是推进阶段门禁的真阻塞项，而 `missing` 大多只是待补的可选事实
 * （品牌、包装内容物等不参与解锁）。只按 REVIEW_ORDER 排，4 个不阻塞的 missing
 * 会压在 3 个阻塞的 proposed+critical 前面，与页面文案「先处理冲突、未知与必须确认
 * 的槽位」相反：读者按视觉顺序走，会先做几件不影响推进的事才碰到真正的门槛。
 */
export function reviewRankOf(entry: RankableSlot): number {
  const status = entry.slot.status;
  if (status !== "confirmed" && status !== "superseded" && entry.slot.critical === true) {
    return 2;
  }
  const base = REVIEW_ORDER[status] ?? 9;
  // 冲突/未知仍然最先；缺失及之后的普通状态整体后移一位，给 critical 让位。
  return base < 2 ? base : base + 1;
}


export function splitLines(text: unknown): string[] {
  return String(text || "").split("\n").map((item) => item.trim()).filter((item) => item.length > 0);
}


export function formatValue(slot: { value?: unknown }): string {
  const value = slot.value;
  if (value === null || value === undefined) return "";
  if (Array.isArray(value)) return value.join("；");
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

export function describeBlocking(
  blocking: Array<{ message: string }> | null | undefined,
  mapMessage: ((message: string) => string) | null = null,
): string {
  return (blocking || [])
    .map((item) => (mapMessage ? mapMessage(item.message) : item.message))
    .join("；");
}

/** 把 DOMException/业务错误统一降为可读文案；不吞掉原始错误对象。 */
export function errorMessageOf(error: unknown, fallback: string): string {
  if (error instanceof Error && typeof error.message === "string" && error.message) return error.message;
  if (error !== null && typeof error === "object" && "message" in error) {
    const message: unknown = error.message;
    if (typeof message === "string" && message) return message;
  }
  return fallback;
}

