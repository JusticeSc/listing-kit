# D2.R1d 生产形态前端定义候选（线框与视觉稿，2026-09-27）

> EVIDENCE-SNAPSHOT: task-evidence · NOT-AUTHORITY
> 产品合同在 `docs/product-demo-goal-and-implementation-plan.md`；当前进度与唯一下一动作在
> `_working/amz-listing-kit-product-demo/state.md`。本次零网络、零模型调用、零付费、零生产写盘。

## 1. 范围与依据

- 依据：计划 v1.21 §4.7（FE-01～FE-04）、§6.11.3、§6.11.3A、§3.2。
- 产物：`evals/product-demo/d2-r1d/frontend-definition-2026-09-27.html`——线框（4 桌面 + 1 窄屏）、
  9 个关键状态线框、控件存在理由表、4 个阶段高保真视觉稿（含返工方向面板）、组件/空态/失败态规范。
- 素材：商品图来自冻结参考包（`evals/product-demo/fixture-design/pack/`）；审核页候选来自首轮真实
  I2I 输出 F-01～F-04（`evals/product-demo/first-round/attempts/`）。本产物不生成任何新图。

## 2. 产物读数

| 项 | 值 |
|---|---|
| HTML sha256 前 16 | `072B5694DEC9C23B` |
| HTML 大小 | 47943 B |
| 无头渲染（Chromium 1440×900） | scrollWidth=1440=clientWidth（无横向溢出）；页面高 10494px；图片 25 张、失败 0 张 |
| 截图 | screenshots/01-top.png、screenshots/02-wireframes.png、screenshots/03-visual-intake.png、screenshots/04-visual-plan.png、screenshots/05-visual-review.png、screenshots/06-visual-rework.png、screenshots/07-visual-delivery.png |
| 渲染命令 | `uv run --with playwright python -c "…"`（本机无头 Chromium；只读本地 file://） |

## 3. 控制面恢复记录（2026-09-27）

- 2026-09-27T10:13:39+08:00 直接读取 Goal 控件：`status=active`。按第十六次校准的恢复路径，state 顶层
  `status: active`、Phase 2 `status: active`、`system_goal_observed_status: active` 三处同步；
  移除阻塞项 `system_goal_blocked_before_d2r1d_start`。
- `next_action_task` 保持 `D2.R1d`；本任务未完成部分是产品发起人确认（见 §4）。

## 4. 评审门（本候选尚未完成的部分）

D2.R1d 完成判据：产品发起人确认任务模型、资料入口、默认增强、一键整套、审核/返工与导出投影。
本页把该判据拆为四个评审点：① 资料怎么进入任务；② 默认方案与一键生成；③ 审核只处理问题 +
按方向返工；④ 交付条件与文件清单。产品发起人确认前不进入 D2.R1e、不修改 `app/static/`。

## 5. 边界

- 本产物证明“设计候选可评审、可渲染、无横向溢出、素材完整”，不证明任何功能已实现，也不证明
  视觉品味已被产品发起人接受。
- 尚未覆盖（留给 D2.R1e/后续验收）：真实交互与键盘路径、窄屏实机截图、Mock service 接线、
  浏览器兼容与 200% 缩放实测；这些不得引用本文件当作已通过。
