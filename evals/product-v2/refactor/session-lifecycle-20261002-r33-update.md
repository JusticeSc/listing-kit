# V2.R3.3 会话/启动/OCC — 可控延迟复现与修复后验证（本轮更新）

> NOT-AUTHORITY: point-in-time evidence（时点证据；计划/状态仍以 `docs/product-v2-refactor-plan.md` 与 `_working/amz-listing-kit-product-v2/state.md` 为准）。

日期：2026-10-02（本轮写入，覆盖 `session-lifecycle-20261002.md` 的旧验证读数；任务卡分析结论不变）。
范围：`app/product_v2/session.js`（新增）、`app/product_v2/app.js`、`app/product_v2/workspace.js`、`tools/v2_test_server.py`（测试延迟钩）、`tools/verify_v2_3_3_session_lifecycle.py`（新增）。
运行：真实 Chromium（Playwright headless，独立临时 profile / 持久 profile），无 Mock IndexedDB / WebCrypto；模型路径不涉及（本任务全部离线写）。

## 1. 本轮修了什么（相对旧报告新增）

- 新增 `app/product_v2/session.js` 会话 Module：`boot()/openProject()/closeProject()` 统一推进 `generation`；`beginAction()` 冻结 `{generation, projectId}`；`workspace.close()` 先把旧项目未保存草稿按旧会话落库再清引用；boot 失败 → `phase=failed`，界面停在禁用 + 明确错误 + 重试。
- `app.js`：首页控件 HTML 默认 `disabled`，`boot()` 全程禁用；数据库打开、指针读取、`workspace.open` 装载、首页刷新全部结束后才解锁并切视图（`data-ready=1` 即"完整恢复完成"，不是"控件先可用"）。
- `workspace.js`：全部 30+ 状态变更动作经 `beginAction()` 冻结；写按冻结 `projectId` 落库、UI 按 `alive()` 投影；旧回调不能写新项目也不能重置新项目视图；intake 编辑传 `expectedVersion`（观察版本），冲突走三路合并（`mergeIntakePayloads`，本地优先、不丢对方文本）+ 同字段三方互不相同进冲突编辑器人工二选一；解决后按对方最新版本 append-only 追加。
- 验证器本次修的测试侧问题（不属于产品行为变更）：intake kind 用 `product_input`；A→B 用"真实输入+回首页再建 B"捕获旧回调写归属；冲突 bump 用"初始保存→raw put 新 `document_key`"构造真实跨标签版本；`__v2SessionProbe` 只暴露 `{generation, projectId, phase}`；重启用同 profile `launch_persistent_context` 关闭重开；`docs_final` 跨边界只传 `{project_id, version, product_name}` 纯数据。

## 2. 可控延迟复现（旧 ready 窗口，修后通过）

- `/?__test_delay=1500` 延迟 `storage/index.js` 模块返回：解锁时刻 `data-ready` 必为 `1`（V2.3.3-02 PASS，无早解锁窗口）。
- `/?__test_delay=300` 拖慢 `workspace.js`：`project-view` 可见时工作区已完成装载（V2.3.3-03 PASS）。

## 3. 验证读数（本轮新鲜证据，两轮全绿）

`tools/verify_v2_3_3_session_lifecycle.py`（11 项，全部 PASS，退出码 0；run2/run3 两轮连续全绿）：

| id | 判据 | 结果 |
|---|---|---|
| V2.3.3-00 | workspace/app/session 通过 node --check | PASS |
| V2.3.3-01 | 正常启动零延迟时控件只解锁一次，且解锁时 `data-ready=1` | PASS |
| V2.3.3-02 | 模块加载延迟下，解锁时刻即 `data-ready=1`，无早解锁 | PASS |
| V2.3.3-03 | 工作区装载延迟下，`project-view` 出现时工作区已完成装载 | PASS |
| V2.3.3-04 | boot 失败 → 控件保持禁用、boot-retry 显示、错误信息可见 | PASS |
| V2.3.3-05 | 打开 A → 打开 B：旧回调不重置 B 的视图（title=项目 B，pid_a≠pid_b） | PASS（run3：pid_a=d3821a28…，pid_b=9f4bdf7f…） |
| V2.3.3-06 | A 的陈旧 intake 输入按 A 的 project_id 落库，没有写进 B | PASS（run3：A 落库["A 的商品名"]，B 无 intake） |
| V2.3.3-07 | 双标签陈旧编辑冲突编辑器可见（三方不同字段逐项展示） | PASS（run3：editor=true，rows=2） |
| V2.3.3-08 | 冲突解决后落库、版本追加、A 的输入未被静默覆盖 | PASS（run3：versions=[1,2,3]，latest=标签页甲的商品名） |
| V2.3.3-09 | 浏览器重启后项目与文档恢复（同 profile 重开，pid 一致） | PASS（run3：restored_pid=conflict_pid=53f47040…） |
| V2.3.3-10 | 零 console error / page error | PASS |

其他相关新鲜验证（本轮复跑）：`npm run test:domain` 223 pass；`npm run check:types` PASS；`tools/check_docs.py --no-run` PASS；`tools/check_project_state.py` PASS。

## 4. 已知边界（不宣称已解）

- boot 间歇缺陷（unknowns 登记）不在本切片宣称已解：可复现窗口已由 `data-ready` 门禁消除，间歇根因仍按 unknowns 保留。
- 关闭/abort 不承诺取消上游：已发出的生成请求照常完成、按冻结 project_id 落库。
- 390px / 键盘专项不属于本切片；R6.3 RC18 读取 manifest 后需要单独回归。
- 验证器尾部 `OSError: [WinError 10038]` 为测试服务器关闭时的宿主套接字竞态，不影响 11 项 PASS 与退出码判定（报告保留原样，不掩盖）。

## 5. 证据文件（本轮新鲜）

- `evals/product-v2/v2.3.3-session-lifecycle-20261002-231308-run2.json`（全过）+ 4 张截图（delayed-open / boot-failed / ab-switch / conflict-resolved）
- `evals/product-v2/v2.3.3-session-lifecycle-20261002-231354-run3.json`（全过）+ 4 张截图
- 本报告：`evals/product-v2/refactor/session-lifecycle-20261002-r33-update.md`
- 代码指纹：`app/product_v2/app.js`（+108/-，含 `__v2SessionProbe` 只读探针）、`app/product_v2/workspace.js`（+942/-，含 `beginAction` 别名与 OCC 分支）、`tools/v2_test_server.py`（`__test_delay` 钩）；新增未跟踪：`app/product_v2/session.js`、`tools/verify_v2_3_3_session_lifecycle.py`（提交时精确纳入，不 `git add -A`）
