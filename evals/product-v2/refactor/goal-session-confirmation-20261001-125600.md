NOT-AUTHORITY: point-in-time evidence; not a plan, current state, or product completion

# V2.R1.1 会话绑定确认 · 20261001-125600Z

- 用户确认：`不是给你设置了goal吗`（当前 Goal 已存在，不新建 Goal）。
- 真实读数：先 `goal get` 返回 paused，再按恢复语义 `goal resume` 返回 active，完整重构目标不变；两个返回均无接口 ID 字段。
- 本轮观察：`evals/product-v2/refactor/goal-session-observation-20261001-121220.json`（`observed_at: 2026-10-01T12:14:51.443Z`，`observed_status: active`，`goal_id: null`，`id_unavailable: true`）。
- 计划原文核对：§2.1 声明文本 SHA256 `731d1ca284792c8aefcc97bfb69bc5734698c337bd0475f48d3177c5584815ea`；工具实际展示全文经行首 `▏` 边距与版式空白归一化后与计划原文等价。
- 绑定含义：`goal_binding: session` 仅表示本次会话已核对过当前 Goal，不是全局 UUID 身份替代；`goal_id` 保持 null，不虚构、不套用旧 ID；新会话/恢复必须重读真实 Goal。
- 控制变更：计划 §2/§3/G0/G1/R0.2/R1.1/RC01/§11、context SEL-017、INDEX、AGENTS 已修正“新建 Goal/UUID 唯一开工”旧语义；`tools/check_project_state.py`、`evals/probes/project_state.py`、`tools/refactor_resume.py` 已接线 `session` 证据合同。
- 权限范围：本次确认只开放在用户确认后的离线本地实现；付费模型调用、私有上传、提交/推送、部署、V1 日落、新依赖选型仍各自单独设门。
- 未证明：旧 Goal 生命周期变化、真实 UUID 全局绑定、产品行为、真实模型、线上/Human 验收。
