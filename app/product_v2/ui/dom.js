// Generated from app/product_v2/ui/dom.ts; edit the TS source and run `npm run build:frontend`.
/**
 * 视图层共享的**无状态** DOM/格式化助手与词表（设计 §2.1 的「四个视图」共同基础设施）。
 *
 * 边界：这里不放任何业务状态、订阅、DOM 查询或网络；只做「输入 → 节点/字符串」的纯投影，
 * 供各视图与工作台装配复用。业务判据仍归 domain 与各业务 Module。
 *
 * TypeScript 迁移（计划 §9 V2.R7.5）：本文件是唯一手工维护实现；同名 `dom.js` 由
 * `npm run build:frontend` 生成，浏览器只消费生成的 `.js`。
 */
/** 严重度 → 徽标样式；颜色只表达优先级，不改变任何规则判定。 */
export const SEVERITY_BADGE = Object.freeze({
    BLOCK: "is-review-block", HIGH_RISK: "is-review-high", WARNING: "is-review-warn",
    UNKNOWN: "is-review-unknown", PASS: "is-review-pass",
});
export const COMPARE_STATE_BADGE = Object.freeze({
    pending: "is-review-high", unknown: "is-review-unknown", clean: "is-review-pass",
    unchecked: "is-review-unchecked",
});
export const STATUS_TEXT = Object.freeze({
    confirmed: "已确认", proposed: "模型提案", missing: "缺失",
    conflict: "冲突", unknown: "未知", superseded: "已移除",
});
export const AUTHORITY_TEXT = Object.freeze({
    core_fixed: "系统固定", category_dynamic: "品类动态", user_custom: "自定义", derived: "派生",
});
export const ROLE_TEXT = Object.freeze({
    primary: "商品主图", detail: "细节图", packaging: "包装图", scene: "场景参考",
    competitor: "竞品参考", other: "其他",
});
export const EVIDENCE_TEXT = Object.freeze({
    user: "用户输入", asset: "参考图", model: "模型", rule: "规则",
});
/** 审核优先级：冲突 → 未知 → 缺失 → 未确认 → 已确认 → 已移除。 */
export const REVIEW_ORDER = Object.freeze({
    conflict: 0, unknown: 1, missing: 2, proposed: 3, confirmed: 4, superseded: 5,
});
/**
 * 列表排序键：把「必须确认（critical）且尚未收尾」提到冲突/未知之后、缺失之前。
 *
 * critical 是推进阶段门禁的真阻塞项，而 `missing` 大多只是待补的可选事实
 * （品牌、包装内容物等不参与解锁）。只按 REVIEW_ORDER 排，4 个不阻塞的 missing
 * 会压在 3 个阻塞的 proposed+critical 前面，与页面文案「先处理冲突、未知与必须确认
 * 的槽位」相反：读者按视觉顺序走，会先做几件不影响推进的事才碰到真正的门槛。
 */
export function reviewRankOf(entry) {
    const status = entry.slot.status;
    if (status !== "confirmed" && status !== "superseded" && entry.slot.critical === true) {
        return 2;
    }
    const base = REVIEW_ORDER[status] ?? 9;
    // 冲突/未知仍然最先；缺失及之后的普通状态整体后移一位，给 critical 让位。
    return base < 2 ? base : base + 1;
}
/** 全工作台唯一的 DOM 构造工具；只设置显式给出的 className/text/attrs/props。 */
export function createElement(tag, options = {}, children = []) {
    const node = document.createElement(tag);
    if (options.className)
        node.className = options.className;
    if (options.text !== undefined)
        node.textContent = options.text;
    if (options.attrs) {
        for (const [name, value] of Object.entries(options.attrs)) {
            if (value !== null && value !== undefined)
                node.setAttribute(name, String(value));
        }
    }
    if (options.props)
        Object.assign(node, options.props);
    for (const child of children)
        if (child)
            node.append(child);
    return node;
}
export function splitLines(text) {
    return String(text || "").split("\n").map((item) => item.trim()).filter((item) => item.length > 0);
}
/**
 * V2.6.4 渐进披露：工程字段（sha256 / action / task / 指纹）默认收进「技术详情」。
 * 业务判读所需信息留在主行；技术字段不删除、展开即可见，也仍可从 dataset 读取。
 */
export function techDetails(lines, label = "技术详情") {
    const items = (Array.isArray(lines) ? lines : [lines]).filter((item) => typeof item === "string" && item.length > 0);
    if (!items.length)
        return null;
    const details = createElement("details", { className: "tech-details" });
    details.append(createElement("summary", { text: label }));
    details.append(createElement("p", { className: "meta tech-body", text: items.join(" · ") }));
    return details;
}
/** 追加技术详情节点：无内容时是空操作，保持既有「有内容才出现」的渲染行为。 */
export function appendTech(parent, lines, label) {
    const node = techDetails(lines, label);
    if (node)
        parent.append(node);
}
export function formatValue(slot) {
    const value = slot.value;
    if (value === null || value === undefined)
        return "";
    if (Array.isArray(value))
        return value.join("；");
    if (typeof value === "boolean")
        return value ? "是" : "否";
    return String(value);
}
export function describeBlocking(blocking, mapMessage = null) {
    return (blocking || [])
        .map((item) => (mapMessage ? mapMessage(item.message) : item.message))
        .join("；");
}
