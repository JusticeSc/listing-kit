# AGENTS.md — 本仓库的 Agent 工作规则

> CONTROL-STATUS: current · AUTHORITY: agent-rules
> 这里只写「怎么干活」的规则。目标与完成判据看 `docs/product-v2-goal-and-implementation-plan.md`；
> 项目身份、技术栈与运行边界看 `docs/product-v2-project-context.md`；当前进度看
> `_working/amz-listing-kit-product-v2/state.md`。本文件不复制它们的正文。

## 1. 进入顺序

`docs/INDEX.md` → `docs/product-v2-project-context.md` → 当前 state → state 指向的下一任务
（在计划的任务表里）→ 该任务证据与相关代码。默认不读 `standards-template/`、`drafts/` 与旧计划。

## 2. 选型门禁（Reuse-first gate）

<!-- reuse-first:begin -->
任何非平凡能力，先按这个顺序找一遍，再决定动手：

**复用 > 配置 > 集成 > 扩展 > 自研**

必须先停下来交一份「选型报告」的情形（结论写进项目上下文 §4，实现前经用户确认）：

- Python：新增任何运行时依赖（会改 `requirements.txt`），或新增 ≥100 行通用基础设施。
- 浏览器：新增 >5 KiB 的通用能力文件，或引入任何 vendor 库。
- 任何被判断为「基础设施」而不是「业务语义」的模块。

通用基础设施至少包括：HTTP 客户端、retry/退避、缓存、调度、队列、事件总线、状态机、
序列化、配置框架、插件注册、连接池、认证、日志框架。

选型报告字段：约束 / 已有能力（仓库现有、现有依赖、语言或框架自带）/ 候选 / 取舍 /
推荐 / 被拒方案与理由 / **复访条件与移除成本**。

依赖是债务，门禁是双向的：既拦「该用轮子却自研」，也拦「30 行的需求引入 20 个依赖」。
业务语义（槽位权限、失效传播、交付门禁、状态转换）自研是标准答案，不受此门禁限制。

登记即门禁：`requirements.txt` 与项目上下文 §4 的依赖登记表必须逐包一致；浏览器
vendor 库与 `app/product_v2/vendor/` 必须逐一对应。少改一处，`tools/check_docs.py` 报红。
<!-- reuse-first:end -->

## 3. 不许违反的产品边界

以 `docs/product-v2-project-context.md` §3（运行边界与数据所有权）与 §6（不变约束）为准：
密钥只在服务器环境变量、服务器不保存用户项目状态、未确认事实不得进入带事实断言的
Prompt、外部调用超时是 `UNKNOWN` 不是失败。本文件不重复这些正文。

## 4. 完成与证据

以计划 §11（完成证据矩阵）与 §12（验证策略与成本纪律）为准：每个任务交付
「用户可观察行为 + 数据合同 + 验证证据」；证据写入 `evals/` 并带 `NOT-AUTHORITY`；
文档、Mock、自评不能替代产品完成。

## 5. 改动纪律

- 一类事实一个权威；新增或删除 Markdown 先改 `docs/INDEX.md`，再动文件。
- 小步提交，提交信息写明任务 ID 与证据路径；不把无关改动混进同一个提交。
- 结束一轮工作前跑 `tools/check_docs.py` 与 `tools/check_project_state.py`，红了先修再走。
- 守卫串行跑：`tools/check_docs.py` 会调用 `evals/probes/project_state.py`，而探针会临时
  改写 state 再逐字节还原——两者并行会被踩出假红（2026-09-29 实测一次）。
