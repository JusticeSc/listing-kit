<!-- 拆分件 02/03 · 父文档 evals/product-v2/refactor/packet11-convergence-20261008.md -->
# 4.2 设置面板：一个真实产品缺陷 + 三个空证（产品侧 + 验证侧）
[返回 packet11-convergence-20261008.md](packet11-convergence-20261008.md)

### 4.2 设置面板：一个真实产品缺陷 + 三个空证（产品侧 + 验证侧）

- 产品缺陷：填完商品资料后**立刻**打开设置面板并点应用（草稿仍在防抖里、尚未落盘）时，
  已输入的名字/介绍/卖点被清空、分析入口被锁。
  - 机制：`modelSettings.subscribe(() => { capabilities = …; if (projectId) renderAll(); })`
    在草稿落盘前整体重渲染，输入框按**存储值**（空）重画，待落盘草稿被丢弃。
  - 修复：订阅回调先落盘草稿再渲染。**只调 `inputs.saveIntakeNow()`**（无脏草稿即 no-op；
    真落盘时经 `changed` → 派生），不调用带无条件派生的 `inputView.saveIntakeNow()`
    ——后者会在能力就绪前派生并回写项目状态（§4.3(b)）。
  - 证据（一次性探针 `_working/p11fix/_probe_settings_intake.py`）：修复前 A 组（立刻应用）
    `name=""`、`gate="还缺：商品名称必填。"`，B 组（等 2s）正常；修复后 A/B 均保留
    `name/description`，入口可用。
  - 常驻守卫：`verify_v2_packet08_settings_vision.py` 新增 `P08-01e`（DOM 值保留 + 已落盘 +
    入口未锁），与其余检查一起进 CI 与两轮回归。
- 验证侧空证：P08-01d/-03pre 在资料未填时读到"还缺：商品名称必填"，断言退化成空条件；
  补上真实前置后同一套件 23/23 有真实输入（含新增 `P08-01e`：应用设置不丢未落盘草稿）。
- 注意：中途用 `--label` 单独复跑的同类证据（`fix6/diag2/draft-guard`）是同一套件的重复判定，
  已移入忽略目录 `_working/p11fix/scratch/`，不当作独立证据。

### 4.3 重开项目会改库：boot 期派生 + 环境代理掩盖（4_2 / UI2-17）

**(a) 4_2 重启后 `base` 陈旧，被环境代理伪装成 502。**

- 现象：`V2.4.2-20` 期望 400 `EXECUTION_IDENTITY_MISMATCH`，实得 **502 且 body 为空**；
  `-99` 浏览器闭环被 `HTTPError: HTTP Error 502: Bad Gateway` 打断。
- 机制两层：
  1. `restart_server()` 用 `make_server()`（端口 0）重起，拿到**新端口**，`base` 仍指旧端口；
     Windows 偶尔把刚释放的端口再发给它 → 时红时绿（正是它此前"r1 红 r2 绿"的来源）。
  2. 本机 `HTTP_PROXY=http://127.0.0.1:7897`，`urllib` 连回环也走代理；端口没人监听时代理回
     `502 Bad Gateway` + `Content-Length: 0`，把真实连接错误伪装成"网关故障"。Chromium 不走该代理，
     所以浏览器侧照常成功，掩盖了同一问题。
- 探针：`_working/p11fix/_probe_42_restart.py`（关闭后同端口 → `HTTPError 502 'Bad Gateway'`、
  body 空、新端口 26649 ≠ 旧端口 26634）；`_working/p11fix/_probe_loopback_noproxy.py`
  （加回环 no_proxy 后死端口 → `URLError [WinError 10061] 目标计算机积极拒绝`，活端口 200）。
- 修复：`restart_server()` 记 `port = server.server_address[1]` 后**按同端口重建并断言读回一致**
  （IndexedDB 按 origin 隔离，换端口会让"同项目核对"失去前提）；`tools/v2_verify_shared.py`
  为本进程/子进程设回环 `no_proxy`，不再让代理掩盖连接错误。
- 证据：`v2.4.2-generation-attempt-20261008-014820-fix3`（并给 `-20` 的证据补上
  `bad_payload/good_payload/bad_submit_payload`，失败时自解释）。
- 残留：重启后浏览器是否复用旧实例的 keep-alive 连接无法从页面侧观测区分；`-20` 的直发探测
  走全新连接，服务端"无任务表"这一结构性前提不依赖实例身份。

**(b) UI2-17 重开项目会写库（产品侧）。**

- 现象：重开后阶段判定都对（落在「交付」），但整库摘要变了——`projects` 记录的
  `revision 5 → 8`、`updated_at` 变化，`documents`/`assets` 一字未动。
- 机制（用浏览器内包装 `IDBObjectStore.put` 钉出三次写）：`rev 6 = PLAN_REVIEW`
  （**能力/会话就绪前派生产生的中间态回写**，等于重开项目把已确认状态降级）、
  `rev 7/8 = READY_TO_GENERATE`（两次并发派生各自按同一份陈旧内存记录回写，
  `project.state !== state` 护栏被并发绕过）。触发者是 §4.2 的第一版修复：
  `modelSettings.subscribe` 在 boot 期发射 → `inputView.saveIntakeNow()` 里那句无条件的
  `deriveAndApplyState()`。这与 `loadWorkspace()` 既有约定（能力到位后**唯一一次**派生）冲突。
- 修复：见 §4.2 —— 订阅回调只落盘草稿，派生交给 `changed`；boot 路径回到"能力到位后一次派生"。
- 证据（同一次运行的仪器化证据）：修复后 UI2-17 `reload_writes = []`、`diff = {}`、
  前后摘要逐字节相同 → ui_2 16/16 全绿（`v2.ui.2-interaction-visual-20261008-015527fix6`）；
  packet08 复跑仍绿（§4.2 的保证未回退）。

### 4.4 harness 页载入卡住：加诊断 + 仅对可识别传输签名重载一次

- `tools/v2_verify_shared.py: read_suite()` 增加：常驻采集 console 错误、page 错误、
  `requestfailed` 与 `readyState`/脚本清单；超时时区分**脚本抛错**（不重试，直接把诊断抛出）
  与**资源没到**（传输抖动）：后者重载一次，并在套件结果里留 `load_stall_retried` 与
  `load_stall_evidence`（症状进证据，不静默吞掉）。这与 `verify_v2_ui_2_interaction_visual.py`
  既有的 `ConnectionResetError` 重试口径一致（只对可识别的传输错误重试一次并记录）。
- 证据：本轮 `p11close2` 两轮无一次触发（无人为掩盖）；上一次尝试的触发症状见 §3。

## 5. 发布条件（R7.4）：删源码钉，改用失败类别行为证明

- 删除 CI 中扫描工作流自身文本的 truth-table 步骤（本工作树改动，未提交；本轮只读核对生效）。
- CI 容器 job（Docker 部署前）改为 `tools/release_transaction_probe.py --offline-rollback`：
  用真实脚本 + 最小 stage 执行器逐个走失败类别并断言退出码与持久化事务状态。

| 类别 | 断言 | 检查号 |
|---|---|---|
| 用法错误 | exit 2，不写事务、不碰服务 | OR-01 |
| 无开放事务 | exit 4（需人工核对），HOME 零副作用 | OR-02/OR-07 |
| deploy 后验收/指纹类失败 | rollback 恢复旧版本并清事务 | OR-08 |
| deploy 阶段失败（候选不健康） | 脚本自身回退 exit 1，无残留事务 | OR-09 |
| 清理失败（新版本健康） | exit 4；新版本继续服务、previous 保留、**不自动回退** | OR-10 |
| 清障后 finalize | exit 0，previous/备份/事务才被清理 | OR-10b |
| 回退本身失败 | exit 3 且 journal 保留，不报成已恢复 | OR-11 |

结果：`--offline-rollback` **13/13 PASS**（`OR-00`…`OR-11`）。真实容器/TLS/HTTPS 与同 origin
容器页面（ST-LIVE/ST-DEAD/ST-10、`--page-smoke`）仍只能由 CI 的 Docker/发布条件证明。

