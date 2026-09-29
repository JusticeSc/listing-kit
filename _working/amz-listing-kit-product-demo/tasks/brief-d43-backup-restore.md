# 任务书 D4.3：干净安装、备份和恢复演练（amz-listing-kit）

> CONTROL-STATUS: superseded · AUTHORITY: historical-task-brief  
> D4.3 已完成；当前任务和状态只读权威计划与 current state，本文件不再驱动施工。

项目根（所有命令用绝对路径，先切到这里）：`E:\workbuddy_workspace\2026-09-20-16-38-19\amz-listing-kit`

## 背景事实

- 产品是“商品套图工作台”：`app\server.py` 启动；工作空间是磁盘目录（商品原图、候选图、方案、提示词、导出包）。
- 已有真实跑通工作空间：`_working\amz-listing-kit-product-demo\real-ui-run-05\workspace`，含 `exports\export_d4d91e65511e4695`、`exports\export_9d5428ec8b7d4b6d`（manifest 里有 sha256）。
- 8787（PID 31784）与 8789 端口有服务在跑，**不要杀**；自己起服务用 8792 起。
- **百炼账号欠费，真实模型调用都会失败。D4.3 不需要模型调用**（备份/恢复/打开已有工作空间），不允许用 Mock 冒充真实证据。
- Python（无全局 python 命令）：`$env:TEMP\amz-plan-edit-e55ae1ef753b49a58a7c5166551af2a7\Scripts\python.exe`
- 编辑文件必须用 apply_patch 包装器（不要用管道）：
  `& "C:\Users\31368\AppData\Local\OpenAI\Codex\bin\7537f22ba194f7c1\codex.exe" --codex-run-as-apply-patch $patch`，`$patch` 为 here-string 的 `*** Begin Patch ... *** End Patch`；锚点重复要分步打补丁。

## 任务定义（权威计划，不许降低）

交付：安装记录、工作空间备份、恢复和版本清单。
验收：**换目录后可打开并继续；原图/候选/hash 一致**。
约束：**恢复不覆盖较新 Workspace；冲突另存副本**。

## 必须产出

1. 先读代码确认现状（`app\server.py`、`src\workspace_store.py` 等）：工作空间根如何配置、是否已有备份/恢复/版本清单能力。把真实机制写进证据，不要猜。
2. 如缺失则新建最小工具：
   - 备份：复制/打包工作空间到目标目录，产出 manifest（相对路径 + sha256 + 大小 + 时间）；
   - 恢复：恢复到**另一个根目录**，逐文件校验 sha256；
   - 冲突：目标已存在同名且更新的工作空间时**不得覆盖**，另存副本（如 `workspace-restored-<timestamp>`），说明判定依据；
   - 版本清单：记录代码/依赖指纹（如 `app\server.py`、`src\`、`app\product_v1\`、`requirements.txt` 的 sha256）随备份落盘。
3. 真实演练：备份 run-05 workspace → 恢复到新临时根 → 用新目录启动服务（`--port 8792`；若不支持指定 workspace 根，说明机制并选可行方案）→ 打开恢复后的工作空间确认能加载原图/候选/方案/导出（不需模型调用）→ 校验全部 sha256 一致；再做一次“目标已存在”冲突演练确认不覆盖、改副本；至少一个负向用例（备份被改动/缺文件时必须报失败而非静默通过）。
4. 证据文档 `evals\product-demo\d4.3-clean-install-backup-restore-2026-09-28.md`：首行 `> EVIDENCE-SNAPSHOT: current · NOT-AUTHORITY`；写清安装记录（依赖清单/解释器来源/能否干净复现；做不到就如实写“未验证干净安装 + 原因”）、备份与恢复命令路径、sha256 校验数量与结果、冲突案例、负向用例、版本清单路径、遗留局限。

## 禁令

- 不改 `_working\amz-listing-kit-product-demo\state.md` 与 `docs\product-demo-goal-and-implementation-plan.md`（由主代理统一更新）。
- 不调用真实模型；不删项目内已有文件（临时目录放 `$env:TEMP` 或 `_working\amz-listing-kit-product-demo\d43-drill\`，演练完保留证据）。
- 不用 git reset/checkout。

## 交付回报（完成后）

工具路径、演练命令、校验数字、证据 md 路径、遗留局限。全部写在最终回复里。
