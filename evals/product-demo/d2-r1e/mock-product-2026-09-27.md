# D2.R1e 生产形态 Mock 产品实现（2026-09-27）

> EVIDENCE-SNAPSHOT: task-evidence NOT-AUTHORITY

## 改了什么
- 正式入口空白启动：初始为空白任务，商品名、参考图、卖点均未填；缺什么就地说明。
- 加载示例资料只填入同一张表单；Aster 候选仍标注历史真实候选，非本次生成；新商品候选标注 Mock 候选未调用模型。
- 业务面移除切换演示情形和重置演示按钮；场景经 ?scenario= 与 window.__setMockScenario/__resetMock 外置控制。
- 统一 service 扩展 loadExample/updateIntake；createRecommendedPlan 要求商品名加至少一张参考图加卖点加已核对。
- server --check 首页标记同步为新版；探针同步新 intake 流程；修复 GBK 下 X 打印崩溃。

## 验证
- mock_workbench.mjs 探针通过（确定性重放、部分失败与 Unknown 隔离）。
- server --check 已通过，见本文件末尾自检记录。
- 冒烟：空白建计划被拦、示例链 F-01/F-02 保留、新商品链走 Mock 占位。

## 边界
- Phase2 候选轨迹只保证 Aster 示例；新商品仍为 Mock 占位；零模型调用、零正式写盘。


## 自检（2026-09-27 中午）
- server --check（aster-01）：退出码 0，零写入、零网络、四页初始加两页走后标记、正式单页结构加 Mock 轨迹探针全过。
- 探针 mock_workbench.mjs：通过（确定性重放、部分失败与 Unknown 隔离）。


## 浏览器验证（2026-09-27 中午，8779）
- 无头 Chromium 加载正式入口：零控制台报错、零页面异常。
- 空白态：标题为通用商品套图，商品名、上传、卖点均空，画布与工作区显示先补齐资料，导出门禁。
- 点击加载示例：3 张参考卡填入同一张表单，标题变为示例商品。
- 截屏：blank-state-2026-09-27.png、example-loaded-2026-09-27.png；脚本：render-check-2026-09-27.py。


## 全链路浏览器走通（2026-09-27 中午，8779）
- 示例装载、勾选确认、生成方案 v1（4 张）、一键生成到审核、四图核对选定到 READY_TO_EXPORT、导出预览清单（01-S1 到 04-S4，绑定候选与提示词版本），全程零控制台报错。
- 截屏：loop-plan、loop-review、loop-selected、loop-export；脚本：full-loop-2026-09-27.py。


## 单图返工浏览器验证（2026-09-27 中午，8779）
- S1 按场景原因返工：旧候选 C-S1-01 保留，新候选 C-S1-R1 追加，提示词到 v2；S2/S3/S4 的候选与尝试计数原样不动。
- 重选各图最新候选后正常导出四文件，全程零控制台报错。截屏：rework-form、rework-done；脚本：rework-loop-2026-09-27.py。


## 控制面守卫（2026-09-27）
- tools/check_project_state.py：J0–J10 全过。中间抓到一次自摆乌龙——手写 updated_at 写到未来，已按真实时钟修正后重跑通过。


## 失败路径与窄屏浏览器验证（2026-09-27 中午，8779）
- scenario=partial：一键生成后 S3 失败、S4 为 Unknown；S4 直接返工被拦，先核对转失败再返工；两图返工后整套回到 READY。
- 390 宽窄屏：无横向溢出。两次均零控制台报错。截屏：fail-partial、fail-recovered、fail-narrow；脚本：failure-narrow-2026-09-27.py。

