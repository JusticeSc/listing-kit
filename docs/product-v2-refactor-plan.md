# Product V2 定向重构：目标与详细实施计划

> CONTROL-STATUS: current · AUTHORITY: product-goal-plan
> 版本：r17 · 2026-10-17 main 工程基线规划。§1–§17 保存当时的产品合同、任务和授权；本轮适用范围见下方§17.14，当前方向与权限以最新用户指令和 state 为准。原生 Goal 观察全文保存在§2.1，不能冒称实时读数。
> 历史r3触发记录：2026-10-03 Goal 1596e3da4da5b9bb的旧正文/绑定保存在本轮正式启动快照与历史观察，旧触发前回滚来源为 `_stage-amz-control/unattended-trigger-20261003-trigger-before/`；不能据旧读数恢复本轮。


## 17.14 当前执行边界

<!-- refactor-resume-policy: blocked -->

> 本节是本次文档治理新增的读取边界，不是 main 原件正文；§1–§17 原文与历史 Goal 一字不改。

- 当前范围是已授权的文档治理，产品实施暂停；旧 Goal 原文是历史观察，不作为新重构的施工前提。
- 不恢复 §9–§17 的历史任务卡、批次、发布、收费或验证授权；旧读数、旧批数、旧授权文字都不构成本轮许可。
- 产品目标与验收按最新用户方向和有效任务合同核对；§1–§17 保留为公开主线的历史合同，不能自动当作当前施工命令。
- 产品如需继续，先核对用户已给出的授权及 state；收费、外发与发布分别核对对应授权。

## 片段目录（按原件顺序）

`docs/product-v2-refactor-plan.md` 的 §1–§17 正文按职责拆为下表 42 个片段，逐字节取自 main `11902b32`；本页只保留原件开头与导航。

| # | 章节职责 | 片段 | main 行 | 字节 |
|---:|---|---|---:|---:|
| 01 | §1 目标、范围与既有基线 | [scope](product-v2-refactor-plan.01-scope.md) | 7–28 | 3696 |
| 02 | §2.1 Goal：目标与成功条件 | [goal-outcomes](product-v2-refactor-plan.02-goal-outcomes.md) | 29–48 | 7804 |
| 03 | §2.1 Goal：验证、边界与停止条件 | [goal-controls](product-v2-refactor-plan.03-goal-controls.md) | 49–61 | 5847 |
| 04 | §2.2–2.4 绑定、权限与开发态边界 | [goal-binding](product-v2-refactor-plan.04-goal-binding.md) | 62–85 | 5007 |
| 05 | §3–4 决策、权限与不变量 | [decisions-invariants](product-v2-refactor-plan.05-decisions-invariants.md) | 86–115 | 5452 |
| 06 | §5 Phase 0–7 与 Gate G0–G7 | [phase-gates](product-v2-refactor-plan.06-phase-gates.md) | 116–152 | 3810 |
| 07 | §6 唯一任务依赖表 | [task-dependencies](product-v2-refactor-plan.07-task-dependencies.md) | 153–186 | 6879 |
| 08 | §7.1–7.3 证据、UI测量与验证分层 | [evidence-verification](product-v2-refactor-plan.08-evidence-verification.md) | 187–253 | 8079 |
| 09 | §7.4–8 数据、发布、风险与读取路由 | [recovery-release-risks](product-v2-refactor-plan.09-recovery-release-risks.md) | 254–303 | 8600 |
| 10 | §9 R0–R2 控制、基线与审计任务 | [tasks-control-audit](product-v2-refactor-plan.10-tasks-control-audit.md) | 304–368 | 8455 |
| 11 | §9 R3–R4 工程、配置与项目包任务 | [tasks-engineering-settings](product-v2-refactor-plan.11-tasks-engineering-settings.md) | 369–424 | 7456 |
| 12 | §9 R5 生成、Adapter与Prompt任务 | [tasks-generation](product-v2-refactor-plan.12-tasks-generation.md) | 425–452 | 5163 |
| 13 | §9 R6 工作台、交付与存储任务 | [tasks-workbench](product-v2-refactor-plan.13-tasks-workbench.md) | 453–484 | 6037 |
| 14 | §9 R7.1–R7.4 验收、清退与冻结任务 | [tasks-final-delivery](product-v2-refactor-plan.14-tasks-final-delivery.md) | 485–516 | 4623 |
| 15 | §9 R7.5、§10–12 验收矩阵与维护入口 | [types-acceptance](product-v2-refactor-plan.15-types-acceptance.md) | 517–570 | 8647 |
| 16 | §12.1 历史Goal编制原文 | [historical-goal](product-v2-refactor-plan.16-historical-goal.md) | 571–610 | 9533 |
| 17 | §12.2–12.5 历史授权与执行纪律 | [historical-authority](product-v2-refactor-plan.17-historical-authority.md) | 611–655 | 6611 |
| 18 | §13 历史规约完善范围 | [historical-preparation](product-v2-refactor-plan.18-historical-preparation.md) | 656–679 | 4857 |
| 19 | §14.1–14.4 分工、事实与图片用途 | [business-facts-purposes](product-v2-refactor-plan.19-business-facts-purposes.md) | 680–734 | 9538 |
| 20 | §14.5–14.6 动作与本地编译恢复 | [business-actions](product-v2-refactor-plan.20-business-actions.md) | 735–763 | 5695 |
| 21 | §14.7–14.8 有限模型与可选复核 | [business-models-review](product-v2-refactor-plan.21-business-models-review.md) | 764–803 | 8183 |
| 22 | §14.9–14.10 代表任务与消费者承接 | [business-acceptance](product-v2-refactor-plan.22-business-acceptance.md) | 804–832 | 5495 |
| 23 | §15.1–15.2 设置接线与人工事实 | [execution-inputs](product-v2-refactor-plan.23-execution-inputs.md) | 833–876 | 5708 |
| 24 | §15.2 生成、返工、图文与最终集成 | [execution-production](product-v2-refactor-plan.24-execution-production.md) | 877–929 | 6283 |
| 25 | §15.3–15.5 验证成本与结构重构 | [validation-structure](product-v2-refactor-plan.25-validation-structure.md) | 930–972 | 8359 |
| 26 | §15.6.1–15.6.2 收口终点与可复用资产 | [delivery-assets](product-v2-refactor-plan.26-delivery-assets.md) | 973–1000 | 6201 |
| 27 | §15.6.3–15.6.4 剩余差距与防重复 | [delivery-gaps](product-v2-refactor-plan.27-delivery-gaps.md) | 1001–1028 | 4865 |
| 28 | §16 启动边界、核对与Goal编制历史 | [startup-history](product-v2-refactor-plan.28-startup-history.md) | 1029–1068 | 7158 |
| 29 | §17.1–17.4 当前终点、恢复与差量规则 | [current-restore](product-v2-refactor-plan.29-current-restore.md) | 1069–1103 | 6601 |
| 30 | §17.4 B1–B3 记录、普通决定与实际双模式 | [current-business](product-v2-refactor-plan.30-current-business.md) | 1104–1123 | 4723 |
| 31 | §17.4 B4–B7 人因、品质、冻结与发布 | [current-delivery](product-v2-refactor-plan.31-current-delivery.md) | 1124–1147 | 5281 |
| 32 | §17.5–17.7 证据、费用、停止与完成 | [current-proof-budget](product-v2-refactor-plan.32-current-proof-budget.md) | 1148–1200 | 8845 |
| 33 | §17.8–17.10 启动与恢复入口历史 | [later-startup-history](product-v2-refactor-plan.33-later-startup-history.md) | 1201–1221 | 3650 |
| 34 | §17.11.1 历史需求覆盖与最早缺口 | [audit-history](product-v2-refactor-plan.34-audit-history.md) | 1222–1239 | 6211 |
| 35 | §17.11.2–17.11.3 原项目与现场试行 | [project-trial-history](product-v2-refactor-plan.35-project-trial-history.md) | 1240–1255 | 4872 |
| 36 | §17.12.1–17.12.3 历史追加授权与安排 | [authorization-preparation](product-v2-refactor-plan.36-authorization-preparation.md) | 1256–1292 | 6796 |
| 37 | §17.12.4–17.12.6 历史费用、恢复与补图 | [billing-preservation-history](product-v2-refactor-plan.37-billing-preservation-history.md) | 1293–1314 | 5938 |
| 38 | §17.13 本次纠偏、完整交付与审计入口 | [audit-recovery-authority](product-v2-refactor-plan.38-audit-recovery-authority.md) | 1315–1325 | 4039 |
| 39 | §17.13 原则1–11：成品边界、Prompt、人因与工程归属 | [audit-recovery-principles](product-v2-refactor-plan.39-audit-recovery-principles.md) | 1326–1337 | 7859 |
| 40 | §17.13 审计后剩余安排与批次13–18结果 | [audit-recovery-batches](product-v2-refactor-plan.40-audit-recovery-batches.md) | 1338–1354 | 5568 |
| 41 | §17.13 费用与追加20–23、停工与自我改造 | [audit-recovery-limits](product-v2-refactor-plan.41-audit-recovery-limits.md) | 1355–1362 | 5185 |
| 42 | §17.13 开发准备、24–26恢复、测试整改与27–28授权 | [audit-recovery-resume](product-v2-refactor-plan.42-audit-recovery-resume.md) | 1363–1378 | 6772 |

## 拼接与引用

- 完整原件可按 `config/document-splits.json` 中的登记恢复：本页拆分时前 6 行加上 01–42 顺序正文，去掉每片导航头及登记的围栏续接标记。所列字节和 SHA256 是拆分时证明，不冻结后续维护。
- 原标题位于对应片段；跨文件引用请指向「片段链接 + 原锚点」。
- 设计取 `product-v2-refactor-design.md` §13；具体 Issue/PR 工作流取 AGENTS。
