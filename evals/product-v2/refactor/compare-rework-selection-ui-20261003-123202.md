# V2.R6.2 · 比较/审核/返工/采用 - 工作证据

> CONTROL-STATUS: current · NOT-AUTHORITY（时间点证据；C17/C15 人审与真实付费链不属本切片）
> Goal: docs/product-v2-refactor-plan.md §2.1（sha256=3f9f1842d67d063fa9d8cfbbaf60eb5971fe24b46502c97455241ccac40d4607）
> 日期：2026-10-03；报告戳：20261003-123202（与 a11y 报告同戳；各验证器取各自同日戳）

## 1. 切片动作（唯一事实来源：仓库 diff + 验证器）

- 修复刷新重开 review_report 重复铺写：`app/product_v2/workspace.js` 重开装载把 `record.payload` 按 `{ report, version }` 形状写入 `generation.setReviewReport`（此前误传裸 payload，导致 `reviewIsCurrent` 读到 `undefined`、重开必重建、文档版本无意义 +1）。
- 修复验证器分区锚点：`tools/verify_v2_5_4_rework_loop.py` 的 `rework_section()` 结束锚点由不存在的“整套批次执行”改为实际存在的 `function renderBatch`（此前抛 `ValueError: substring not found`，属工具锚点漂移，非产品行为）。
- 未动产品语义：确认/选择/返工/采用的 domain 规则与存储形状零变化；两处改动均为装载形状与工具锚点。

## 2. 验证（本轮实跑，全绿）

| 验证器 | 证据 | 结果 |
|---|---|---|
| V2.5.1 确定性审核 | evals/product-v2/v2.5.1-deterministic-review-20261003-122935.txt(.json) | 全过；V2.5.1-04 刷新不重复铺由 FAIL 转 PASS |
| V2.5.2 VLM 复核 | evals/product-v2/v2.5.2-vlm-review-20261003-122952.txt(.json) | 全过；重开不重复铺报告 |
| V2.5.3 比较面板 | evals/product-v2/v2.5.3-compare-panel-20261003-123008.txt(.json) | 全过；键盘 Arrow/Home/End/Escape 路径已覆盖 |
| V2.5.4 单图返工 | evals/product-v2/v2.5.4-rework-loop-20261003-123054.txt(.json) | 全过；比较区只读、返工隔离、双击防护、失败可恢复 |
| V2.5.5 整套检查 | evals/product-v2/v2.5.5-suite-review-20261003-123125.txt | 全过 |
| V2.6.1 人工采用 | evals/product-v2/v2.6.1-selection-20261003-123145.txt(.json) | 全过；改选/过期/取消/刷新恢复 |
| V2.6.4 可访问性 | evals/product-v2/v2.6.4-a11y-20261003-123202.txt | 全过；审核/交付 axe 0 violations，可见按钮具可访问名，390px/200% 无横向溢出 |

## 3. R6.2 验收对照（plan §V2.R6.2）

- 不靠记忆跨屏比较 -> 比较面板 + 审核卡摘要 + 定位按钮（5.3 全过）。
- 必要操作键盘可达 -> 候选 Tab 移动/Escape 返回、返工焦点进入与回位、采用面板焦点回位、Tab 序列探针（5.3-11、5.4-09/10、6.1-11、6.4-07/08）。
- 旧候选可选 -> 比较清单多候选切换、旧候选重选变 current（5.3、6.1-16）。
- 无关 Shot 记录/hash/选择不变 -> 返工/采用影响隔离项（5.4-14、6.1-13）。
- VLM Unknown 不自动 BLOCK/采纳 -> 5.1/5.2 Unknown 映射与不自动重提项通过。
- 误漏报观察与限制透明 -> 报告摘要行 + VLM 状态 + 限制文案（5.1 BOUNDARY、5.2-17、6.4-13）。
- 失败保留 Selection 与候选 -> 5.4-16/17、6.1-17 通过；不以清空/自动改选解决展示错误。

## 4. 保留缺口（不属于本切片）

- V2.R7.2 C17/C15 人审仍待执行；R4.2/R5.2 真实付费证明仍 blocked。
- axe 覆盖为自动化可检出子集，不替代人工走查（验证器内已声明）。
