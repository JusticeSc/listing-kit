# V2.R3.3 会话/启动/OCC — 可控延迟复现与修复后验证

日期：2026-10-02（本轮写入）。
范围：本项目 Product V2 会话生命周期（`app/product_v2/session.js`、`app/product_v2/workspace.js`、
`app/product_v2/app.js`）。真实 Chromium（Playwright headless，独立临时 profile），无 Mock
IndexedDB / WebCrypto；模型路径不涉及（本任务全部离线写）。

## 1. 复现旧 ready 窗口（修前红）

机制：旧代码把"控件解锁"与"完整恢复"解耦——`boot()` 里控件先解锁、列表刷新/工作区
装载在后台继续；`handleOpen` 也是先 `showProject` 再后台 `open`。产物就是
"看到可交互界面但背后没有仓库/工作区"的窗口；在此窗口点创建/导入即抛错。

复现方式（`tools/verify_v2_3_3_session_lifecycle.py` 的 `RP-A`/`RP-B` 用例）：
- 路由级延迟：`/?__test_delay=1500`（HTTP 层 sleep）延迟 `storage/index.js` 的
  模块返回；加载旧版 app.js（`git show HEAD`，带时代错配旧 `wvm_session`），观察
  `create-project` 的 disabled 时间线。修前读到 `true→false→true→false`（第二跳
  false 即 ready 窗口，第 3.1 节 PASS 之外的守卫会拒收）。
- 工作区级延迟：`__test_delay=300` 拖慢 `workspace.js`，旧 app.js 里
  `showProject` 先于 `open()` 返回（第 3.1 节断言拒收）。

## 2. 修后行为

- `session.js`：`boot()/openProject/closeProject` 全部经 `generation` 推进 +
  `beginAction()` 冻结 `{generation, projectId}`；`workspace.close()` 先落未保存
  草稿再清引用；boot 失败 → `phase=failed`，界面停在禁用 + 明确错误 + 重试。
- `app.js`：首页控件 HTML 默认 `disabled`，`boot()` 全程禁用；恢复完成（数据库
  打开、指针读取、`workspace.open` 装载、首页刷新都结束）才解锁并切视图。
- `workspace.js`：每个状态变更动作都经 `beginAction()` 冻结；写按冻结
  `projectId` 落库、UI 按 `alive()` 投影；旧回调不能写新项目也不能重置新项目视图。
- 双标签 OCC：编辑传 `expectedVersion`（观察版本），冲突时三路合并
  （`mergeIntakePayloads`）本地优先，不丢对方文本；同字段三方互不相同的项进
  冲突编辑器人工二选一；解决后按对方最新版本落库（append-only，新版本追加）。

## 3. 验证读数（本轮，新鲜证据）

`tools/verify_v2_3_3_session_lifecycle.py`（共 10 项，全部 PASS，退出码 0）：

| id | 判据 | 结果 |
|---|---|---|
| V2.3.3-01 | 正常启动零延迟时控件只解锁一次，且解锁时 `data-ready=1` | PASS |
| V2.3.3-02 | 模块加载延迟下，解锁时刻即 `data-ready=1`，无早解锁 | PASS |
| V2.3.3-03 | 工作区装载延迟下，`project-view` 出现时工作区已完成装载 | PASS |
| V2.3.3-04 | boot 失败 → 控件保持禁用、boot-retry 显示、错误信息可见 | PASS |
| V2.3.3-05 | 打开 A → 打开 B：A 的旧回调写不进 B（写仍落 A 的 project_id） | PASS |
| V2.3.3-06 | 打开 A → 打开 B：A 的旧回调不重置 B 的视图（`workspace_title` 不变） | PASS |
| V2.3.3-07 | 双标签陈旧编辑冲突 UI 可见（三方不同字段进冲突编辑器） | PASS |
| V2.3.3-08 | 双标签陈旧编辑解决后三字段落库、版本追加、A 的编辑未被静默覆盖 | PASS |
| V2.3.3-09 | 浏览器重启后项目与文档恢复 | PASS |
| V2.3.3-10 | 零 console error / page error | PASS |

其他相关新鲜验证（本轮复跑）：
- `npm run check:types`、`npm run check:versions`、`npm run test:domain`：全部 PASS。
- `verify_v2_1_1_indexeddb.py`：全过（6/6 检查 + 29 契约用例）。
- `verify_v2_1_2_project_home.py`：全过（11/11）。
- `verify_v2_1_3_project_package.py`：全过（8/8）。
- `verify_v2_1_4_formal_entry.py`：全过（13/13，含磁盘审计与浏览器重启恢复）。
- `verify_v2_2_1_product_contracts.py`：全过（6/6）。
- `node --check`：workspace.js / app.js / session.js 三个模块全过。

## 4. 已知边界

- boot 间歇缺陷（unknowns 登记）不在本切片宣称已解：可复现窗口已由 `data-ready`
  门禁消除，间歇根因仍按 unknowns 保留。
- 关闭/abort 不承诺取消上游：已发出的生成请求照常完成、按冻结 project_id 落库。
- 390px / 键盘专项不属于本切片；后续 R6.3 RC18 门禁读取 manifest 后需要单独回归。

## 5. 证据文件

- `evals/product-v2/v2.3.3-session-lifecycle-<stamp>.json` / `.txt`
- 本报告：`evals/product-v2/refactor/session-lifecycle-20261002.md`
