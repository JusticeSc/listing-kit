# 任务书 D4.2：可用性与可访问性收敛（amz-listing-kit）

> CONTROL-STATUS: superseded · AUTHORITY: historical-task-brief  
> D4.2 已完成；当前任务和状态只读权威计划与 current state，本文件不再驱动施工。

项目根（所有命令用绝对路径，先切到这里）：`E:\workbuddy_workspace\2026-09-20-16-38-19\amz-listing-kit`

## 背景事实

- 产品是“商品套图工作台”：商品资料输入 → 方案 → 提示词 → 一键生成 → 单张返工 → 选择 → 导出。前端 `app\product_v1\`（product.js + 模板/样式），后端 `app\server.py` + `src\application_service.py`。
- 已有真实跑通的工作空间（含真实候选图/导出包）：`_working\amz-listing-kit-product-demo\real-ui-run-05\workspace`，用它做“有数据形态”验证。
- 8787（PID 31784）与 8789 端口各有服务在跑，**不要杀**；自己另起端口 8791 做验证。
- **百炼账号欠费，真实模型调用都会失败。D4.2 不需要模型调用**，也不允许用 Mock 冒充真实生成证据；用已有真实工作空间数据即可。
- Python（无全局 python 命令）：`$env:TEMP\amz-plan-edit-e55ae1ef753b49a58a7c5166551af2a7\Scripts\python.exe`
- Playwright 模板：先读 `tools\verify_product_v1_ui.py`、`tools\verify_product_v1_ui_rework.py`、`tools\verify_product_v1_ui_shot_retry.py`，照抄其启动服务/打开页面/截图模式；运行方式
  `& "C:\Users\31368\.local\bin\uv.exe" run --no-project --with-requirements requirements.txt --with playwright python <脚本>`
- 起服务（后台隐藏窗口）：`Start-Process -FilePath $py -ArgumentList @('app\server.py','--port','8791') -WindowStyle Hidden -PassThru`
- 编辑文件必须用 apply_patch 包装器（不要用管道）：
  `& "C:\Users\31368\AppData\Local\OpenAI\Codex\bin\7537f22ba194f7c1\codex.exe" --codex-run-as-apply-patch $patch`，`$patch` 是 here-string 的 `*** Begin Patch ... *** End Patch`；同一锚点文本出现两次会歧义，需分步打补丁。

## 任务定义（来自权威计划，不许降低）

检查：键盘 / 焦点 / 错误关联 / loading / 390px / 200%。
验收：主流程无隐藏按钮、无横向溢出、无仅颜色状态。约束：不为动效牺牲操作。

## 必须产出

1. 新脚本 `tools\verify_product_v1_usability_accessibility.py`（Playwright），至少覆盖：
   - 空白形态：Tab 可达全部必要控件、焦点可见、label/placeholder 关联；
   - 有数据形态（打开 run-05 工作空间）：loading/empty/error/disabled 状态存在且不只靠颜色（有文字/aria）；disabled 原因可发现；
   - 390px 视口：`document.documentElement.scrollWidth <= innerWidth + 1`；
   - 200% 缩放（选一种模拟方式，并在脚本注释里写清局限）：主流程按钮仍可见可点、无溢出；
   - 键盘：Tab 走查关键控件，Enter/Space 至少能触发“开始生成 / 重跑 / 导出”之一。
   每项输出 pass/fail + 截图存 `evals\product-demo\`（前缀 `d4.2-`）。
2. 发现问题**直接修前端**（`app\product_v1\`），重跑脚本到全过；修完至少重跑 `tools\verify_product_v1_ui.py` 与 `tools\verify_product_v1_ui_rework.py` 确认不回归。
3. 证据文档 `evals\product-demo\d4.2-usability-accessibility-2026-09-28.md`：首行 `> EVIDENCE-SNAPSHOT: current · NOT-AUTHORITY`；写清命令、逐项结果、修复内容、截图路径、局限（哪些是模拟缩放、哪些状态没有真实触发路径）。

## 禁令

- 不改 `_working\amz-listing-kit-product-demo\state.md` 与 `docs\product-demo-goal-and-implementation-plan.md`（由主代理统一更新）。
- 不调用真实模型；不删已有文件；不用 git reset/checkout。

## 交付回报（完成后）

脚本路径、pass/fail 数、改了哪些文件、证据 md 路径、遗留局限。全部写在最终回复里。
