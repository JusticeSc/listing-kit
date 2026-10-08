# 资产复用与差量收口（2026-10-08）

NOT-AUTHORITY：本文件记录本次实际工作与复用边界；目标/权限只见计划，进度/次数只见 state。用户明确继续相同 Goal，要求做过的工作不重做、积累成资产、有意识减少工作量和复杂性。

## 恢复与轮次核算

同一产品 Goal `159d03ed410f9ff9` 真实 resume 为 active；正文 sha256 `bac1155dbef21876391328dafd50a5624dee8461388754021a31aa59ff1c6fc6`，原生观察见 `goal-observation-continuation-20261008.json`。原预算/次数不清零。仅保留拟改文件的原字节差量快照 `_stage-amz-control/asset-continuation-20261008T054352Z/manifest.json`；原 423 文件及同版本项目/Blob 恢复基线继续复用 `final-delivery-20261007.md`，本次不重新导入或全库备份。

历史缺逐批登记，不能声称存在唯一精确计数。绑定后旧 state 可确定两个大批（差量收口、远程 CD 收口）；为避免少算，本次按下列五个独立消费者工作段保守占用原 10 轮，而非把每个提交或每次测试算一轮。当前 HTTP 差量修复从第 6 轮记账，最终 R7.1 两轮验收尚未发生。

| 占用 | 消费者/不变量 | 已有身份与证明 |
|---|---|---|
| 1 | HTTP 连接复用及加载触发面 | `6b37145`；`loopback-connection-fix-20261007.md`，只保留其已证明范围，不据此关闭 RC19 |
| 2 | 设置草稿/重开零写、候选容量受阻/取回 | `8d0320d`；`packet11-convergence-20261008.md` §4 及引用的前后观测 |
| 3 | 验证前置、既有入口与发布失败类别 | `22db254`；同报告 §3/5，44×2 是当批工作回归，不是最后候选验收 |
| 4 | CI 证据入库与 Linux 消费者/发布收口 | `1393ad3` 至 `92d88c1`、PR #4；同报告 §9 与 `audit-current-state-20261008-observations.json` 的原生 run/发布工件，保留成功发布事实 |
| 5 | 停工后单独的 4_2 点击竞态修复尝试 | `b9ae6f0/c31213a`；最新审计 S1/S3。仍未闭合，失败尝试也占用，不因停工越界抹掉工作事实 |

绑定/恢复、只读审计、纯记录提交不计产品批次；本次恢复核对也不计。采用保守占用解决旧登记歧义，不增加额度，不建立新计数平台。

## 资产及失效范围

| 保留资产 | 当前消费者/证明范围 | 何时才补证 |
|---|---|---|
| 原事务、项目/Blob、授权/action 身份 | storage/domain 及原数据恢复原件；45 文档/4 Blob/2 采用已验证 | 实际改变事务、引用/包格式或生命周期消费者时 |
| 两个真实图像 Adapter 及图文理解真链 | 现有 registry/credentials/outbound、账本/来源原件 | 上游协议/真实能力/输入前提改变，或完整真实任务确缺证时；不因新 HEAD 再购买全部真链 |
| 本地完整流程及两包往返 | `tools/v2_verify_shared.py` 的页面动作、`verify_v2_6_2_delivery.py`、`verify_v2_6_3_project_transfer.py`；替身模型，独立 IDB/ZIP/hash 校验 | 受影响消费者变更；纯人工/无 AI、真实模型及跨版本同 origin 恢复缺证另外准确标注，不重写第二套 walk |
| 单次摘要提交、按需复核、无 AI 交付 | 已有 packet08/3_5/5_3/采用与交付入口、历史成功 CI | 修改对应 owner/调用方后才跑对应入口；旧空证已修的部分不重新开发 |
| 真实发布及不同 image 回退 | 已有成功 run/工件、release 脚本 | 当前候选实际变化后的必要发布；镜像页面目标错配和跨版本数据恢复仍需补，不能把已发布说成未发布 |

现有 shared walk 走显式理解与整套 AI 复核；不能直接当纯人工/无 AI 全流程证明。`SEED_SLOTS` 等写库夹具不可混入模拟真人轨迹。复用正式页面选择器与独立检查，不种候选或调用内部业务函数。

## 第 6 轮：HTTP 未读正文差量

消费者：正式 `ProductV2Handler`；固定不变量：不支持/未读完的正文不得留在可复用连接上。复用已有审计 red-capable socket 观测（同 HEAD 132884d）：chunked POST/GET 正常响应后多出 356 字节无 HTTP 头 HTML，缺 `Connection: close`，模型构造/外网均为 0。原结果在 `audit-current-state-20261008-observations.json.http_framing_smoke`，不重新运行它来确认已知红。

本轮只修正式读取/GET 路径，并把同场景并入已有 `app/server.py --check`；不增加 chunked 上传支持、新 HTTP 框架或另一验证入口。修后运行原 socket 场景和正式自检，结果补记本节。其他缺口不因此声称完成。

第6轮实际结果：原socket场景POST/GET均只返回声明长度的单份响应，`Connection: close`，EOF成立，异常后缀356→0字节；禁止provider构造的计数仍为0。额外实际发送128MiB上限前缀、声明上限+1字节，确认读满有限前缀后仍关闭而非误复用。正式`uv run --locked python app/server.py --check` 52/52通过，正常同连接连续GET及完整读取的超限拒绝保持通过。机器证据`asset-continuation-20261008-http.json`保留原红来源、当前server字节hash和后置；无新增验证入口，无临时脚本文件，无模型/外网调用。README已更新传输合同。

## RC19：一次新层级诊断，不重复刷绿

复用原`_working/_probe_boot_refusal2.py`的方法，只加Chromium默认去私密信息NetLog；显式四类本地替身、隔离Chrome无头/临时profile、原绑定快照静态字节，避免与并行消费者修改混测。原HTTP/1.0触发形态最多600次、遇首个网络失败即停；本次600次/34800请求均未捕获拒连。对原生464740个网络事件独立分类，`net_error=-102`/`os_error=10061`均无记录。因此只能证明本次未触发，不能关闭RC19，不再用同配置重复买绿。

原始捕获/汇总在忽略目录`_working/rc19-netlog-20261008.json`和`rc19-netlog-summary-20261008.json`；最小结论`asset-continuation-20261008-rc19.json`。一次性脚本已删除，临时profile及服务器已关闭。未新增产品重试、代理绕过或网络框架；最终发布所需现象—机制对应仍缺。

原生捕获合同：[Chromium NetLog startup/default privacy](https://www.chromium.org/for-testers/providing-network-details/)。本次仅捕获隔离本地页面，不运行真实模型。

## 第7/8轮接管与差量证据

用户随后明确要求“接管子代理的工作”。已终止OwnerClosure的活动写入，ReleaseClosure已停止；父直接接管，不再委派。首轮编译实际发现漏掉仍有消费者的`reportOf`声明、遗留`generation.ReviewReportEntry` typedef；父补齐真实只读面并删除无用类型引用，不恢复反向setter。父同时修异步补建的reset/flight身份边界，旧会话的finally不能清新会话飞行，不吞总体恢复异常。子代理未验证代码不算完成资产。

父统一emit后，15个TS根实际生成集合一致，严格check:types零诊断、Node既有227/227通过。只跑受影响原消费者：3_5所见摘要/授权失效、4_2原action/task/Unknown/重启、5_1自动报告/刷新不铺版本、6_3完整导入/返工/采用/两包闭环均rc=0；标签`takeover-20261008`，机器/文本证据在`evals/product-v2/v2.*-20261008-*-takeover-20261008.*`。不执行44×2工作回归，不把这些差量绿灯称为最终R7.1。

另实际走空页面：Enter新建→许可蜂蜜罐文件输入→人工确认4项可见事实→推荐4张→自动本地Prompt→一次确认外发→逐张采用→主图定向构图返工。正式本地处理器仅显式四类Fake，未点击理解/单图AI/整套AI按钮。主realm原生IDB报告写入配额故障确实拒绝1次：5个候选、4份已保存报告、4个人工采用，原文档逐条保留且Blob哈希成立；错误原因可见、旧采用仍current。解除故障后明确采用新图，本地补报告落version1，不重生成或调用AI；运行本地确定性整套检查后，两包实际下载/原生CRC及逐图hash核对通过，manifest如实`ai_review.not_reviewed/not_run`。同origin服务器明确重启后reload，文档/Blob逐条完全相同，5份报告均仍version1。证据`asset-continuation-20261008-manual.json`；两包原字节、独立前后快照在差量基线`data/`，截图`../evidence/asset-continuation-20261008-manual-deliver.webp`。

工具边界也保留：首个故障注入用了隔离realm、没有拒绝报告，已废弃为故障证据；纠正为`tab.evaluate` main realm后才算实际负例。下载wait持有tab锁导致Eval重置并结束临时host，这是已知工具生命周期故障，不是RC19的监听仍在拒连；客户端本地ZIP仍下载成功，host后在同origin明确重启完成恢复证明。Fake候选只证明流程/字节/身份，不证明商品图忠实度或C15/C17真人。原4_3/4_4受影响路径交给同候选既有CI验证，未在本机再刷一套。

第8轮`.dockerignore`已改精确子树排除/重纳入，`release_transaction_probe.py --selftest`的ST-LIVE现对真实container origin执行，复用原正式Dockerfile/不同image ID/markerA-B/故障回退；代表项目经真实文件输入建立，切换/回退/收口使用同一持久profile及origin、独立IDB/Blob/采用前缀核对。预测88文件只是静态闭包，不冒充实际镜像；workflow原接线保留，无新发布平台。真实Linux/Docker运行尚待受保护PR的CI，RC19及最终发布门仍未闭合，当前未发布新版本。


## 现有PR/CI首次结果

草稿[PR #5](https://github.com/JusticeSc/listing-kit/pull/5)，候选`ef8cda1`；未合并/未部署。[run 37745335928](https://github.com/JusticeSc/listing-kit/actions/runs/37745335928)在控制状态J8失败：已提交state的`latest_audit`指向既有但尚未纳入Git的`audit-current-state-20261008.md`；Docker job因此未运行。最早失败是证据依赖没有随状态发布，不是Docker或产品行为。只晋级原有相关审计/原生观察资产，不重做审计、不改守卫、不换latest_audit掩盖缺文件；HTTP前红的原来源JSON也据原引用一起保存。


## 现有PR/CI第二次结果：发布自检 4 红全部落在探针自身

候选`e10b076`，[run 37745951722](https://github.com/JusticeSc/listing-kit/actions/runs/37745951722)：控制面绿，Docker/发布自检 job 23/27，4 红。三条根因都在探针自身，逐条按现象—机制对应修（提交`986a6df`，已 push）：

1. **ST-LIVE 行内导出等不到 download（30s 超时）**：`showHome()` 点击后立刻显示旧行，`refresh()` 随后重渲染列表。机制用一次性探针钉死（`_working/_probe_export_stale_node.py`，本机实跑）：点击「项目列表」后立刻聚焦导出按钮得到`focused_immediately=export`，400ms 后同一句柄`handle_connected_after_refresh=false`、`activeElement=BODY`，对已摘除节点按 Enter 6s 内零 download，对当前节点真实 `locator.click()` 得到真实下载`stale-node-probe-20261008-0916.zip`。改为真实鼠标点击 + `expect_download` 提到 60s，失败时附会话文案/行集合（`HOME_DIAG_JS`）而不是只报超时。
2. **ST-09 不可达负例用 `http://127.0.0.1:9`**：Chromium 对该端口直接 `ERR_UNSAFE_PORT` 拒发请求，红的机制变成浏览器策略而不是“入口不可达”。改为 `closed_loopback_port()`（bind 0 号端口读回后释放），并把判据收紧为“浏览器错误必须是 `ERR_CONNECTION_REFUSED` 且证据里无 `ERR_UNSAFE_PORT`”（`_working/_probe_dead_and_recovery.py` 本机实测：新端口给出 `ERR_CONNECTION_REFUSED`）。
3. **ST-RECOVERY-01 等 `#create-project:not([disabled])` 可见**：重开的是上次用过的同一 profile，应用直接恢复到上次打开的项目，该控件是 hidden（CI 62 次解析到 hidden）。踩到两个坑：`wait_for_selector` 传选择器列表只校验**第一个**匹配项；应用是否自动恢复取决于 profile 里“上次打开的项目”。改为按就绪信号 + 实际可见视图分支。本机实测（`_working/_probe_autopen_branch.py`）：重开后`project_view_visible=true/create_project_visible=false`，分支后真实行可见；`data_recovery` 在真实项目包（45 文档/4 资产/2 人工采用）上 -01..-04 全绿（-05 本机无版本切换按设计判红）。

顺带把三处异常兜底 id 从与正常检查重号（`-06`/`-01`）改为 `-99`/`-90`，避免同一 id 出现两条不同含义的证据。本机回归：`--page-smoke` 10/10、`--offline-rollback` 13/13（连跑两次）；Docker 自检只能在 CI(Linux) 跑。

**本机未闭合的观察（不冒充已修）**：首次 `--offline-rollback` 在 OR-01 出现 `UnicodeDecodeError: 0xfb in position 0`（父进程读子进程输出），rc=1。同 HEAD 原字节副本同命令 13/13 通过，改后版本随后连跑 3 次 13/13。只出现 1 次、无法复现，判为 Windows bash 子进程输出的本机瞬时故障，不据此宣称任何机制结论，也不改代码掩盖。

## 第三次CI：控制面 V2.4.3-04 取样竞态（与探针改动无关）

候选`986a6df`，[run 37756024859](https://github.com/JusticeSc/listing-kit/actions/runs/37756024859)：控制面 job 在“Check formal entry and browser contracts”红，Docker job 因此被 skip（我的探针改动这一轮没被验证）。红的是既有验证器 `tools/verify_v2_4_3_batch_execution.py` 的 -04：detail `{"captured":4,"order_ok":true,"per_action_once":true,"polled_ok":true,"state_wait":true,"project_state":"PLAN_REVIEW","progress":"共 4 张 · 已成功 3 · 处理中 1 · 待提交 0。"}`。同一文件在上一轮 run 37745951722 绿，两次之间该文件零改动 ⇒ 时序型红。

机制（代码路径可读，不是猜）：-04 的两个后置条件都是异步写回——「批次核对落定（已成功 4）」由批次逐张核对写回；「项目状态前进」由 `workspace.js:536` 的 changed 订阅并发调用 `deriveAndApplyState()` 写回，派生值取决于 `generation.hasCurrent()`（确认单与 Prompt 版本/哈希/依据是否仍对得上）。原实现先有界等状态、再单独跑一次完整探针（读全库 + Blob 哈希，本身耗时），于是把中间态当成断言失败：`state_wait:true` 说明状态推进事件确实发生过，红在随后的独立取样上。

改法（提交`300c1c4`，不放宽判据）：新增 `wait_batch_settled()`，用**单次 evaluate**同时读 projects store 与 `#batch-progress`，有界等到「state==READY_TO_GENERATE 且进度含『已成功 4』」在同一次取样里成立，然后才跑完整探针；超时仍按实际值判红。并把状态时间线（state/revision/progress）写进 detail：若 CI 再现，时间线可直接区分「还没写回」与「写回又被改回」——后者指向产品侧派生竞态（`hasCurrent()` 在 reset/restore 窗口内为假导致把 PLAN_REVIEW 写回），需要单独定位，不在本轮凭一次 CI 日志定性。本机实跑 V2.4.3 全 14 项绿，timeline 单条 `READY_TO_GENERATE/revision 5/已成功 4`（本机批次远快于 CI，无法在本机复现该竞态）。

## 真实缩放与纯键盘覆盖（1440/1366/390 · 125%/200%）

证据：`evals/product-v2/refactor/asset-continuation-20261008-zoom.json` + `../evidence/asset-continuation-20261008-zoom-{1440,1366,390,125,200}.png`（均为真实 PNG，逐张核对过 IHDR）。方法：系统 Chrome `--headless=new` + 一次性 `--user-data-dir`（`omp-zoom-kbd-…`，采集后删除），本地正式入口 `http://127.0.0.1:8780`，用真实文件输入导入既有合法项目包，导入后整套报告过期→按真实用户路径点「运行本地确定性检查」重跑（v2.5.5 阻断 0 · 高风险 0 · 提醒 1 · 未知 0 · 视觉复核未运行（可选）），交付门禁转通过；缩放用 `chrome://settings/appearance` 的 Page zoom（真实页面缩放，等价 Ctrl+/-，非 CSS zoom/transform、非启动期 device-scale 开关）。

| 场景 | 布局宽度 | dpr | 关键操作 | 结论 |
|---|---|---|---|---|
| 1440×1000 @100% | 1440 | 1.25 | 交付ZIP/项目包均 enabled、在视口内、`elementFromPoint` 命中自身 | 可达不遮挡 |
| 1366×768 @100% | 1366 | 1.25 | 同上 | 可达不遮挡 |
| 390×844 @100% | 390 | 1.25 | 同上（left 33/right 179 ≤ 390）；文档无横向溢出（375=375） | 可达不遮挡；阶段导航行需横向滚动（550>345），符合“390px 只承诺关键可达不遮挡” |
| 1440×1000 @125% | **1152** = 1440/1.25 | 1.5625 | 同上；六个阶段按钮全在视口内 | 真实页面缩放成立 |
| 1440×1000 @200% | **720** = 1440/2 | 2.5 | 同上；六个阶段按钮全在视口内 | 真实页面缩放成立 |

纯键盘（200%，重新加载后 `activeElement=body`，全程只用 Tab/Enter）：焦点序列 `model-settings-open → back-home → 项目信息 → intake → understand → plan → generate → review → deliver`，在 `deliver` 按 Enter 切阶段，再到 `deliver-export` 按 Enter ⇒ 真实产出交付包 `正式开发—人工套图主链-交付包-20261008-0927.zip（30 KB）sha256 cb4bceff33a3040b…`；下一 Tab 到 `deliver-project-package` 按 Enter ⇒ “已导出项目包（含完整历史，可在别的浏览器导入）。”本文件只记应用层结果；ZIP 实际字节/成员/hash 的浏览器层证据由 `--page-smoke` 的 PS-07-package（真实 download 事件落盘并算 sha256）承担。明确模拟性质，不冒充独立真人 C15/C17；dpr 含宿主 1.25 显示缩放；未在远端 HTTPS 环境重复该几何。

