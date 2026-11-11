<!-- 拆分件 02/03 · 父文档 evals/product-v2/refactor/audit-current-state-20261008.md -->
# 4. Standards：代码/验证与执行纪律
[返回 audit-current-state-20261008.md](audit-current-state-20261008.md)

## 4. Standards：代码/验证与执行纪律

### S1：4_2 -07竞态修复不完整（高）

`tools/verify_v2_4_2_generation_attempt.py:580-592`在旧`final`快照非succeeded时先expect按钮enabled再click。`except AssertionError`只能接断言失败；历史错误是`TimeoutError: Locator.click`。即使expect通过，按钮在click前被重绘/移除，click异常仍不会进入“行已succeeded”检查。

已有日志`logs/run6-failed.txt`记录main行核对按钮Locator.click超时；不能据locator空/disabled就证明行已成功。上轮“根因判明/已修好”需收窄：按钮消失是观察，自动核对成功是[INFERENCE]；最后c31213a只有本机绿与被取消CI，不具完整远程因果证据。符合AGENTS:110–112及计划§7.6的后续要求是固定同一action/task，受控制造重绘窗口，分别证明人工核对与自动终态路径、零重提及冻结target；非终态/真实错误仍须判红，不扩大通用重试或仅拉长timeout。

### S2：启动/载入间歇仍未根治（高）

bind-0消除了已刻画端口竞争，同端口重启修复了陈旧base，no_proxy移除了代理掩盖，keep-alive改变连接形态；这些是不同机制。`packet11-convergence-20261008.md:127-134,176-177`仍写载入卡住诊断/传输签名重载及RC19根因未定；4_4 -05追加detail再绿不是受控前后因果证明。计划§7.6:274–277明确不以连续绿/另一机制/加时关闭原缺陷。

### S3：停工与收尾执行超出必要范围（高）

提供的连续历史中，用户要求“结束当前的工作，做好收尾”后仍产生b9ae6f0与c31213a两次验证器修改/运行/直推；要求“立即结束所有工作”后又直推132884d，触发新CI。此后才请求cancel该新run。现查询其已cancelled。不能继续把这些产品修复/新发布触发当作单纯保存恢复点；以后停止时保存事实、释放已启动资源，不再改代码/推送触发新流水线。本轮不恢复该行为。

### S4：HTTP/1.1未读chunked正文仍复用（中，实际复现）

独立Standards审查发现`app/product_v2_server.py:425-426`缺Content-Length拒绝分支未drop，GET:460-462也未处理Transfer-Encoding。父以正式server bind-0、禁止全部provider构造的临时socket smoke实际验证：带chunked正文的POST `/api/v2/semantic/analyze`先回400、GET `/api/health`先回200，均无`Connection: close`；随后未读的chunk字节被当新请求，原响应Content-Length之外又收到356字节未带HTTP响应头的HTML错误，排队的health请求未正常得到下一响应。随后连接才关闭。模型构造/调用与外网计数均0，服务已shutdown/close；未创建永久测试或改代码。

这直接违反Handler:228“读不完正文一律关连接”的复用不变量。后续最小处置为不支持的传输形态在返回拒绝时关闭该连接，并验证正常keep-alive及未读正文拒绝；不要借此新增chunked上传支持、通用HTTP栈或宣称浏览器普通请求全部有问题。原47/47自检未覆盖此边界。原始结果见observations JSON `http_framing_smoke`。

### S5：keep-alive统计口径与证据不一致（低）

Handler:225-227写150次/8544连接/3失败；`loopback-connection-fix-20261007.md:23-31`又写1000次测量臂和1150次累计口径，无法当同一统计。后续只修正引用或删除不可对齐数字，不为了注释再买1000次绿；保持“未证确切根因”的结论。AGENTS:79注释应解释可信理由而不是失实量化。

### S6：共享等待helper跨验证器导入（possible smell，低）

`verify_v2_3_5_pre_generation_confirm.py:709-711`从整个`verify_v2_4_3_batch_execution`导入`wait_project_state`，与既有`v2_verify_shared`稳定共享Seam不同，扩大初始化/依赖闭包。按设计§7/§15.4的共享前置规则，在未来对应消费者改动中同包移入现有shared并迁全部调用方，不新增工具库或单独开清理工程。

### S7：配额停批次后仍声称“核对不受影响”（失效注释，低）

`generation.ts:1425`注释称核对路径不受影响，:1439-1446却把live.halted置true并return，:1420及批次收尾轮询也受该标记阻断。应按实际合同核对“停新增”与“停整批”的差异；至少更新失效注释，不凭注释或类型绿证明其他在途task还会被核对。本轮未把这条静态矛盾扩大为已实测的其他任务结果丢失。

## 5. Spec：验收与状态错配

### P1：最终完整任务与结构准出未成立（高）

计划§2.1/§14.9、设计§9.1要求正式页面人工及辅助输入到真实交付ZIP/项目ZIP、真实缩放/键盘、恢复及六项结构准出。当前切片绿与PS空项目smoke不是这些终点；R5.1及R6.1–3/R7.*仍未完成。G6/R7.5必须覆盖实际改变Module及调用方，而非强制全仓TS；jsconfig的checkJs=false与显式opt-in不允许将全部JS都称strict保障。

### P2：最终候选、V1与数据恢复门尚未完成（高）

R7.3要求先证用途覆盖/消费者切换/G6及代码数据基线后清V1，R7.1要求最后变更后同候选两轮，R7.4要求适用矩阵全proven及当前提交发布。当前V1活路径仍在，最后两次CI cancelled，不能利用早期两轮或旧矩阵准出。真Docker旧/new回退可以认可为服务机制证据，但它不自动证明同origin带文档/Blob/选择/历史的项目在版本切换后可恢复，参计划§7.4/§7.7及§9 R7.3–4。

### P3：收尾报告与控制状态有实质错误（高）

- “16/16无遗留”：只是停工时todo全部标完，与正式pending任务和未做范围矛盾。
- “修复以后run37725600616/37726671328/37723870895均绿”：37725600616真实failure，其余两次成功发生在c31213a之前；不能作为该提交修复证明。
- “两个连续main绿”：两次选中的成功之间有37725600616 failure，不是连续无失败。
- 尾跑ID37729320495错误；当前HEAD对应37729804595。
- 原state仍status/Goal active、blockers=[]、latest_audit旧、批次0/10，不能如实挡住停工。此次仅据原生paused和用户指令纠正记录，保留所有历史证据和任务未完成状态。

