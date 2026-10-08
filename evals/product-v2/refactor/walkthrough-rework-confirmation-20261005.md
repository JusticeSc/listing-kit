# V2 走查收口：返工确认链修复（2026-10-05）

> CONTROL-STATUS: current · AUTHORITY: execution-evidence
> NOT-AUTHORITY: point-in-time verification evidence only。0 次真实模型调用、0 次外部网络。

## 结论
- 修了一个产品 bug：单图返工提交永远 `no_confirmation`。
  - `confirmationReader` 只读整套确认队列，不读返工确认（`app/product_v2/workspace.js`）。
  - 返工确认快照缺 `execution_target`（没传身份）且 mode 错用 `initial`（`succeeded` 图不可再提交）。
  - 返工确认内存条目缺 `documentId`（绕过 `rememberConfirmation` 直接 `set`）。
- 修后：返工确认用 `rework` mode + 当前图像身份 + `rememberConfirmation` 落内存；`confirmationReader` 返工优先回退整套。

## 证据（全部 passed）
- `evals/product-v2/v2.6.3-transfer-20261005-182910.txt`：V2.6.3 04–12 全过（A 导出/B 导入/返工/交付/再导出/旧格式拒绝/零意外错误/自检）。
- `evals/product-v2/v2.6.2-delivery-20261005-182833-final.txt`：V2.6.2 全过（含 13 交付页投影）。
- `evals/product-v2/v2.5.4-rework-loop-20261005-183910.txt`：V2.5.4 20/20 全过。
- `evals/product-v2/v2.4.2-generation-attempt-20261005-182937.*`：V2.4.2 全过。
- `evals/product-v2/v2.5.5-suite-review-20261005-184045.txt`、`v2.1.3-project-package-20261005-184115.txt`：相邻回归全过。
- 守卫：`check_docs --no-run`、`check_project_state` 全过。

## 产品改动（3 文件）
- `app/product_v2/workspace.js`：`confirmationReader` 纳入返工确认；返工提交写 `rework` mode + 身份 + `rememberConfirmation`。
- 走查跟随（4 文件）：`tools/verify_v2_6_2_delivery.py`（录入点分析/确认即提交/卡片直采/新摘要文案）、`tools/verify_v2_6_3_project_transfer.py`（比较面板直采/新摘要文案/等候选不收面板）、`tools/verify_v2_ui_3_frontend.py`（两步填值确认/等全部就绪/自动准备终态等待）、`tools/verify_v2_5_4_rework_loop.py`（确认即提交后等终态/等4图全落定/新确认文案）。
- `app/product_v2/domain/confirm.js`、`app/product_v2/generation.js` 的大 diff 含历史遗留，本轮未动其语义（`rework` mode 定义早已存在，本轮只是首次使用）。

## state 说明
- 本轮不改 `_working/.../state.md`（next 仍 V2.R4.4，由正式流程推进）。
