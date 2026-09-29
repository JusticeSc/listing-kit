# Product V1 v2.6 正式 Goal 前准备审计

> EVIDENCE-SNAPSHOT: current · NOT-AUTHORITY

## 结论

产品合同、任务图、恢复边界和当前工程基线已准备到“等待产品发起人确认 Goal 文本”的状态。系统 Goal 仍为 `paused`，且尚未采用 v2.6 §2 文本；因此本审计不声称 Goal 已恢复，也未开始 D4.6。

## 本次补齐的决定

- 参考图支持增加、移除和排序；第一张是主要身份参考；历史原图不删除。
- S1 “生成整套图片”必须由一个后端幂等命令完成保存、编译和建立唯一 Batch；前端不得串多个写接口。
- D4.6–D4.11 每完成一个新切片，正式导航中的旧对应交互必须退出，不保留两套正式路径。
- 返工确认后，旧候选和旧选择保留为历史，但目标 Shot 变为待重新确认；重新选择旧图或新图后才能导出。
- 现行 API 到最终合同的迁移所有者和退出条件已逐项写入计划 §9.1。
- C2、C7、C8 和 D4.6–D4.12 的验收线及反向探针同步收紧。

## 控制面校准

- 权威计划更新为 v2.6；`docs/INDEX.md` 同步登记计划与 state 世代。
- 清理 state 中已经错过 G1 的 C11 旧措辞，改为 D4.12 前使用仓库内置夹具之外的第二商品。
- 文档守卫此前把 Workspace 导出包里的 README 当成治理文档，同时漏登两份已完成任务书。本次把导出 README 明确排除在治理登记之外，并将两份任务书标为 `superseded` 历史证据。
- 修改前权威文件快照位于 `_stage-amz-control/pre-goal-v2.6-20260929-1040/`；快照不包含任何业务 Workspace 写入。

## 新鲜准入结果

2026-09-29 本机执行结果：

| 检查 | 结果 | 能证明什么 |
|---|---|---|
| `tools/check_docs.py` | 通过；33 份登记与 33 份实际文档一致 | 文档身份闭合、产品目标/实现/执行状态各只有一个权威 |
| `tools/check_project_state.py` | J0–J10 全过 | state 可读、ID/依赖/证据/Goal 绑定和时间一致 |
| `node --check app/product_v1/product.js` | 通过 | 当前正式前端脚本语法有效 |
| `tools/verify_application_service.py` | 7/7 | 空白、坏目录、缺料、无效图片、版本冲突与恢复基线 |
| `tools/verify_product_v1_http.py` | 5/5 | 正式 HTTP 工作空间、recent、保存/重开、原图字节与冲突基线 |
| `tools/verify_product_v1_bootstrap.py` | 通过 | 正式入口 bootstrap 仍可启动，不误入 Mock |
| `tools/verify_product_v1_ui.py` | 通过 | 空白首页到持久化、生成、重启恢复、损坏工作空间反馈与响应式纵向基线 |

本轮没有调用真实付费模型，没有把 fake-provider 浏览器轨迹升级为 C3–C6/C11 的真实完成证据。

## 正式恢复前剩余动作

唯一剩余的是权限动作而非设计工作：产品发起人确认 `docs/product-demo-goal-and-implementation-plan.md` §2 的 v2.6 Goal 文本；随后更新现有系统 Goal objective、恢复为 active、回读并重跑控制守卫。完成此前，D4.6 不标 active。

SemanticProvider 欠费会阻止 D4.7 的真实验收，但不阻止 D4.6；不得以 fake 或历史调用降低完成线。D4.13 仍需一名未参与开发且未见过最终流程的人执行首次使用者走查。
