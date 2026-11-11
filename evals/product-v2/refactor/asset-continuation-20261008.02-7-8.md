<!-- 拆分件 02/03 · 父文档 evals/product-v2/refactor/asset-continuation-20261008.md -->
# 第7/8轮接管与差量证据
[返回 asset-continuation-20261008.md](asset-continuation-20261008.md)

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

