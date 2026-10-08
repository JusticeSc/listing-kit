# 既有工作审计与恢复规划（2026-10-08）

> NOT-AUTHORITY · 时点证据，不是新的产品计划或进度权威。
> 目标/任务/依赖：`docs/product-v2-refactor-plan.md`；结构准出：`docs/product-v2-refactor-design.md`；当前执行状态：`_working/amz-listing-kit-product-v2/state.md`。
> 用户本轮只要求审计、确定状态和规划。之前“立即结束所有工作”仍成立；本轮不恢复产品Goal，不修改产品/验证器/CI，不调用模型，不提交/推送/部署/删除V1。

## 1. 结论与证据基准

产品已有可运行V2实现及真实历史发布，但完整工程Goal未完成。不是“什么都没做”，也不是“16/16完成、全部收口”。当前应保持停工，后续从R5.1剩余消费者与间歇证明恢复，不重做既有五个owner/四视图。

- 审计开始HEAD：`132884d3a50a1188896111385eaaf6edf46c36b8`，`main...origin/main`，初始工作树干净。
- 比较基准取历史停工点`e7ce5c513002d1710c31df59752e7dfe2b4ed665`；`git diff e7ce5c5...HEAD`含505文件，其中大量是控制面原字节快照副本，审计排除副本而非把它们当505项功能变更。
- 本轮原生Goal/GitHub观察及发布工件内容保存在`audit-current-state-20261008-observations.json`；符合既有绑定合同的paused观察在`goal-observation-audit-20261008.json`。
- 修改state之前的完整原文：`_stage-amz-control/audit-stop-state-20261008/state-before.md`，SHA256 `fbcf479a87494df462d73dfc18377c12c35cce1c1032bbe7d80f095725d8ab6b`。
- 本轮只纠正执行记录和保留审计证据；产品Goal/计划正文、正式任务定义/依赖及验收标准未改变。没有把未做任务标done。

## 2. 当前状态：事实与证明范围

| 对象 | 观察 | 可证明与限制 |
|---|---|---|
| 系统产品Goal | `159d03ed410f9ff9`，真实`paused` | 原文逐字匹配计划§2.1；SHA256 `bac1155dbef21876391328dafd50a5624dee8461388754021a31aa59ff1c6fc6`。旧仓库active观察不是实时许可；未resume/create/complete |
| 正式执行前沿 | R5.1未完成；R5.2/R5.3、R6.1–3、R7.1–5尚pending | state纠正为paused、Phase5/R5.1 blocked、next=R5.1并记录用户停工。R6.4历史done保留原范围 |
| PR #4 | [已合并](https://github.com/JusticeSc/listing-kit/pull/4)，2026-10-08T03:29:23Z，merge `f8651fae` | PR检查绿是当时提交的证据；不覆盖以后直推main的修复。当前查询reviewDecision为空，不据此臆造独立审查签署或保护配置 |
| 最新确认成功发布 | [run 37726671328](https://github.com/JusticeSc/listing-kit/actions/runs/37726671328)，`92d88c1`，双job success | release.json、runtime fingerprint与日志证明当时构建/发布/验收/finalize；并非当前HEAD全验收 |
| 最新HEAD CI | [37729804595](https://github.com/JusticeSc/listing-kit/actions/runs/37729804595)，`132884d`，completed/cancelled | 浏览器合同step cancelled；Docker/deploy job没有执行任何step。不是passing，也不是仍在运行 |
| c31213a CI | [37729035340](https://github.com/JusticeSc/listing-kit/actions/runs/37729035340)，completed/cancelled | 同样没有进入Docker/deploy。无完整远程通过证据 |
| 当前公共入口 | 本轮可信HTTPS只读GET health成功，product=v2、server_state=none；capabilities中images.default_trial=closed | 只证明当前可达/公开档关闭。本轮没有SSH读取当前容器image ID，不把历史工件冒充新鲜宿主身份观察 |
| 预算 | 已记image8、semantic/VLM5，共13次；spent=1.15元、含未结算占用1.61元 | 累计上限5元；历史新增许可最多3元/5次生图/2次理解复核，累计次数上限13/7/20。额度不是供应商余额；停工时不执行调用 |
| 批次数 | 原记录仍写0/10，实际随后已有产品修改及工作回归 | 0/10是启动前快照，不是当前剩余轮数。精确使用次数缺少逐批登记，恢复前按轨迹核算；不能重置或默认还能做10轮 |
| 真人验收 | C17/C15未发生 | 本轮工程模拟不能冒充真人签署 |

最新确认发布工件：image ID `sha256:31cc5ec62aa2170b9f134f1256b453e03a39d9e6933cc4c7d1d1db826896d163`；runtime SHA256 `591f2b8322d84902e2d4ed6ea227fad4f38e031dfa6f44108fa650d4049239c6`；fingerprint实际列145文件，原state“77文件”错误。工件ID `11528238313`，[下载来源](https://github.com/JusticeSc/listing-kit/actions/runs/37726671328/artifacts/11528238313)。历史原件在工作区`releases/run5/`，所需原内容亦保存在本审计observations JSON。

## 3. 已成立的成果，不重做

1. 生成、输入、Prompt、采用及交付owner、四个视图及既有TS生成机制已经存在。迁移集合本身与整项结构准出分开；不能因残余未完成重建所有Module。
2. 本轮比较区间的实际产品变更包括HTTP/1.1连接复用/中止处理、设置应用保留待保存草稿、候选容量受阻停新增、批次内取回可用等。`packet11-convergence-20261008.md`§4及原机器证据保留对应行为，不把诊断增强叫产品因果修复。
3. `v2.7.1-regression-20261008-p11close2-final.txt/json`明确记录两轮44条命令各rc=0；这是当时R5.1工作回归，早于后续Linux修复及最后消费者/V1清理，不能替代最终R7.1。
4. 其`f971df6a…`是`tools/verify_v2_7_1_regression.py:104-107`对命令/参数/退出码/结果信号的hash，不是源码、镜像或产物hash，不能拿“两轮指纹相同”证明同一源码候选。
5. `logs/run5-full.txt:2736-2775`记录真Docker不同image ID、late-failure/finalize/rollback，以及ST-LIVE页面绿；ST-LIVE的页面目标实际是另起的本地test server（P5），不是那两份镜像。`3047-3057`的PS才是线上HTTPS页面10/10；`3175-3177`记录finalize_rc=0并清previous。保留各自发布机制/页面壳范围，不改称“从未发布”，也不把本地页面绿并入容器origin证明。
6. `tools/release_transaction_probe.py:220-269`的页面smoke实际新建空项目、刷新、原生项目ZIP下载/导入，再刷新；不涉及商品事实确认、生图、返工、采用和交付ZIP。它没有证明完整商品任务，也没有证明跨版本切换前后同origin代表项目数据恢复。
7. `logs/run5-full.txt`中的ST-DEAD FAIL是不可达入口负例，外层ST-09检查其必须判红并通过；不能误报为成功run里的真实产品失败。

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

### P4：已发布镜像的运行闭包与“仅V2”声明矛盾（高）

发布工件的145项实际文件不仅比原state所称77项更多，还包含`app/product_v1_server.py`、`app/product_v1/*`、`app/static/*`、`app/offline_fixture.py`、`config/product-v1/*`与旧`src`核心。`.github/workflows/ci-cd.yml:319-321`在容器内执行指纹，`release_transaction_probe.py:623-633`逐个hash实际存在文件；故这些不是仅Git源码里的保留项。

这与`Dockerfile:18-26`的“V1/旧fixture/旧config不在镜像”说明及设计§8:238的生产闭包要求不符。`.dockerignore:5,13,20`整体否定目录排除可能使其子树重新纳入是[INFERENCE]；无需据推断改代码，工件已经直接证明排除结论不成立。本轮不启动Docker。后续沿R7.3/R7.4核对实际构建上下文与镜像枚举，删除旧正式消费者后修精确运行闭包；既有健康/页面绿不证明未混入旧代码。本证据不等于旧接口已对外暴露或发现秘密泄漏。

### P5：selftest页面目标仍不是被测镜像origin（中，直接代码证据）

独立Spec审查与父复读确认：`release_transaction_probe.py:569-576`从`v2_test_server`另起server，把`local_base`传给ST-LIVE，而非真实old/new容器的`served_base`。这正是设计§11.5.3:538明确禁止当容器产品署名的目标错配。两个真实image的HTTP marker/回退证据仍有效；线上PS也确实访问公开HTTPS，但全新profile仅空项目往返，没有跨服务版本保留并恢复同一个代表项目。后续在现有probe里对被测实际镜像origin运行必要页面/数据轨迹，不另建release平台。

### P6：结构残余已直接确认，不应从旧包01重来（中，proven-open）

`generation.ts:177-178,279-280,829,887,1499-1500`仍有reviewAccess/reviewFlightReader、ensureReport及setter；`workspace.js:597-599,1527-1531`仍装配反向依赖和恢复补report；`confirmAndRun`仍要求readIntent。与设计§11.5.2:513-523的既知剩余差距对应。这是已知未准出，不是本轮发现新架构需求；同包把报告消费归adoption、摘要/授权归generation并迁全部消费者删除旧setter/UI时序，保留原事务/Unknown/候选保全。

### P7：input-view类型/emit登记依赖传递import（低，非当前漏产物）

`jsconfig.json:18-38`未显式列`ui/input-view.ts`；当前workspace import使其传递进入compiler program，`build_product_v2_ts.mjs:51-59`按program sources发射，故不能沿用旧“缺emit”的结论。风险是该import改道后此已迁源码可能静默离开检查/发射集合。以后对应消费者改动时补既有include即可，不加program∩glob断言平台或全仓TS重写。

## 6. 后续规划（条件成立后执行，不是本轮启动许可）

沿既有正式任务推进，不新增任务/Goal/总体验证平台。既有主链和稳定真Adapter证据按计划§15.6.2映射复用。

| 顺序 | 原任务承接 | 具体输出/准出 |
|---|---|---|
| 0 恢复门 | R5.1前置 | 用户明确恢复后，重读同一真实Goal并核对正文，再resume；核算已用10轮额度，保留预算/Unknown/代码与当前格式数据基线。未经恢复不施工 |
| 1 最早失效路径 | R5.1 / RC19及正式HTTP入口 | 先修已复现未读正文的keep-alive边界；将4_2人工核对/自动终态竞态与启动载入间歇分开，复用既有失败，受控机制与前后后置对应。只跑改变路径，不先刷44×2；未证准出保持未完成 |
| 2 同一纵向任务联调 | R5.1/R5.3、R6.1–3、R7.5 | 完成残余owner/UI时序及受影响调用方类型集合，全部调用方同步cutover/delete旧路径。空页面人工输入→一次摘要提交→partial比较→目标返工→选旧/新图→无AI交付→两包下载/导入/刷新；同轨迹捕获HTTP/IDB/Blob/hash/原action，实际观察截图/键盘/125%/200%缩放/390px |
| 3 辅助与真能力最小补证 | R5.2/R6.1–3、R7.1 | 复用上游协议未改变的历史真链；只补当前消费者/确有能力变化或完整任务缺证。真实图文发送原图片并由人确认；必要真调用先价格/素材/安全注入/账本预留。AI复核可不做，不为报告花满额度 |
| 4 V1工程切换 | R7.3，前置G6/R7.5 | 列独有用途与共享消费者；核对代码/当前格式代表项目可恢复，随后同包删除旧入口/消费者/失效配置依赖，保留共享依赖、失败/账本/许可/用户原件；实际删后V2主链与恢复 |
| 5 最终冻结 | R7.1 | 最后产品/消费者/V1修改后冻结同候选，串行跑全部适用离线两轮；必要判据不得失败，SKIP不充当能力通过；结果信号hash与代码/运行产物hash分别登记，RC/结构项范围匹配 |
| 6 受保护发布 | R7.4 | 相关PR、CI、审查/保护成立后合并；不擅自直推main。远程CD证明当前镜像页面、可信HTTPS、同origin代表项目恢复/真实不同版本回退、完整指纹及finalize；previous/恢复材料保留到必要验收结束。C17/C15仍列未发生 |

执行收敛规则：一次明确消费者/不变量改动后，只验受影响路径；失败先定位不循环碰绿，最终两轮只在最后边界执行。若10轮已尽、间歇无法建立准出或真实调用前提不可达，报告精确门并申请对应最小决策，不能自行风险接受或降低验收。

## 7. 本轮实际运行与边界

- 审计开始实际运行`uv run --locked python tools/refactor_resume.py`：rc=0、8阶段/27任务、next R5.1；它打印的是仓库历史Goal观察且明确“不查询系统Goal”，不能用其PASS证明实时active。
- `uv run --locked python app/server.py --check`：rc=0，47/47；真实本机HTTP/静态/网关合同路径，注入替身、无付费上游。不是完整UI/供应商品质验收。
- 可信HTTPS GET health/capabilities成功，images.default_trial=closed；没有关闭证书验证，没有模型调用或线上写操作。
- 远程只读gh run/pr查询；未rerun CI/未部署。本轮不重新跑已报告4_2失败以确认，不增加永久测试。
- 状态更正后冷恢复rc=0，明确paused、R5.1 blocked及禁止受限执行；既有状态反向探针64向全部匹配，权威state未被探针改写。正式HTTP chunked边界临时smoke按S4观察异常，原输出保存在observations JSON；无模型构造/外网/临时文件遗留。本审计新材料为本地未提交过程证据；后续提交需按计划§7.1精确晋级，本轮不提交。
