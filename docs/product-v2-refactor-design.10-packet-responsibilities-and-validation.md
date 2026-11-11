<!-- 拆分件 10/29 · 父文档 docs/product-v2-refactor-design.md -->
# 施工包职责、顺序与验证选择
[返回设计目录](product-v2-refactor-design.md) · [上一主题](product-v2-refactor-design.09-build-and-release-spec.md) · [下一主题](product-v2-refactor-design.11-handoff-and-delta-ownership.md)

## 11. 施工包职责索引与当前差量收口

以下原“包”是正式任务的内部编辑/验证步骤，不增加任务ID、依赖或第二份进度表。§11.2保留其职责与算法映射，**不是把已做部分重列待办**；当前停在R5.1/包11未闭合，恢复只执行§11.5实际差距，进度及是否可执行仍取state与用户最新授权。

### 11.1 先准备执行环境，不从头再审计

恢复开发需用户另行明确解除停工，再按计划§2.2/§16.2取得真实产品Goal观察；独立规划Goal不匹配产品目标，不能替换绑定。既有483文件快照只保留其时点恢复范围；下一次写入前对当前精确代码/配置及同版本代表项目包核对字节/可恢复性，不重复整个早期基线或清库。`suiteReports`旧故障和emit半迁已不作为当前阻塞；已报告4_4两层失败不重跑来“确认”。

施工前每包写五行：用户可见结果、精确文件/符号、必须保留的不变量、最小实际运行、失败/回退条件。禁止把整份设计丢给低模型要求“自由重构”。

### 11.2 包顺序、边界与最小证明

| 包 | 承接原任务/依赖 | 文件与实施顺序 | 包结束用户可见结果/证明 |
|---|---|---|---|
| 01：闭合产物集合 | R5.1/R7.5；原子联调组A起点 | `build_product_v2_ts.mjs`→`jsconfig.json`→检查实际import；按§10.7两阶段生成、传递源码集合；不单独覆盖不相容旧JS | 产物规则完整；与02/03共同签组，不以编译或新JS文件出现验收用户行为 |
| 02：迁已有owner消费者 | R5.1/R7.5；组A，依01 | `prompts.ts`→`generation.ts`合authorization→`selection-adoption.ts`接单图report/请求准备→`review-delivery.ts`接整套/导出；`workspace.js`逐对象更新创建、按钮读/写、restore/reset/render；删该对象旧Map/helpers/authorization文件 | 所有已迁对象只有一个写者；不存在新TS/旧JS、reviewRequest回调环、`suiteReports`残留。保留原其他未迁对象，不补通用shim |
| 03：恢复项目生命周期 | 原R3.3合同/R5.1/R7.5；组A，依02 | `session.ts`→`workspace.js` open/close→owner dispose/restore；同步现有`app`消费者；按§10.5保存失败传播/同步禁新动作/独立实例/旧结果保全 | **组A首次正式页面**：新建→打开→回首页→打开→刷新；已存项目、人工Prompt、采用/报告历史不丢，无已知suiteReports失败；改变路径console/network/IDB实证 |
| 04：输入唯一所有者 | R5.1、R6.1/3相应合法切片/R7.5；依组A | 新目标 `project-inputs.ts`→旧intake/slots/analysis/plan/style/spec/ref读写与restore→`semantic-analysis.ts` prepare/current/apply→prompts sources→workspace输入视图 | 人工资料/事实/用途/规格从同一owner保存恢复；消费尺寸的shot受阻而无关shot不锁；旧分析只记录原source不应用到新输入 |
| 05：预占与观察事务 | R5.1/R5.3/R7.5；依04 | `storage/repository.js`及现有validate类型→`domain/attempt.ts`单一action投影/已有判据→generation reserve/observation/storeCandidate→原domain/browser消费者 | 两标签页同/不同授权只一个新POST；迟到A保全但不掩盖B在途；0版OCC、Unknown无自动重提、crash window结论正确 |
| 06：采用与ZIP事务 | R6.2/R6.3相应合法切片/R7.5；依05 | repository commitSelection/readProjectSnapshot/commitDeliveryRecord→`storage/transfer.js`→adoption select/clear→delivery export→现有消费者 | 首次双标签采用冲突不覆盖；明确可选旧候选；完整项目包单快照，交付在规格/报告/采用变化时拒混包；两包Blob/hash/来源链往返 |
| 07：按任务拆视图 | R6.1–3/R7.5；依04–06 | 现有workspace按事实/方案、生成摘要、比较/采用、交付各迁窄view；命名沿项目约定，非预建空文件。view只DOM+订阅+命令；工作台最终只生命周期装配 | 人工完整路径：合法输入→事实→用途/补项→默认Prompt摘要→一次提交→partial比较→就地返工→人工采用→两包；无重复确认面板 |
| 08：图文/可选AI与设置闭环 | R6.1/R6.2/R6.3；必须满足各原依赖，不因包序解除R5.2等门 | settings现有三用途→semantic真实图字节/source→adoption显式单图AI→delivery显式整套AI→manifest/ack恢复→旧调用/复制schema同包删除 | 未点AI不外呼且可按确定性门导出；图文仅提议不确认事实；not_run≠真实Unknown；旧任务补原key，secret不进DOM/IDB/包/log |
| 09：验证消费者与历史闭包 | 各受影响任务/R3.2/R7.5；随前包迁，最终在08后收口 | 原验证器/`v2_test_server.py`等既有前置→移除词条/source/mock回声→历史/INDEX引用→正式入口/Docker白名单 | 源码迁移不假红，重复外发/OCC/字节/秘密/旧回调反例仍抓错；失败/预算/许可/用户原件保留；V1清理按当前R7.3工程门，不全目录归档 |
| 10：发布事务行为证据 | R7.4；离线设计可随前包，实际按原发布前置 | release脚本→probe真实两image/late failure→workflow rollback条件/指纹→Docker实际闭包 | Linux正式构建及可信HTTPS/Chrome；失败真回旧image+静态marker；浏览器同origin数据恢复另证，不以health替主链 |
| 11：整合与最终交付 | R7.1/R7.4/R7.5；依原任务图适用前置和R7.3工程清理 | 删后两轮离线回归→正式人工/辅助/视觉/键盘/真实缩放→直接RC矩阵→受保护PR/CI→既有HTTPS/最终指纹 | 当前Goal与§9.1全成立；启动间歇按计划§7.6因果证明，不重跑洗绿；C17/C15独立真人仍不发生/不伪标 |

**原子联调组A=01–03**是旧半迁树的历史最小复原闭包，现已存在相应运行证据，不再从头执行。04–10的已交付部分同样保留，只修§11.5具体残余；若新证据发现违反既有合同，回到唯一owner局部修正，而不是重新搬全部模块。09的消费者/死路径治理仍与受影响代码同包，10不在产品主链未证时发布。

每个对象的机械迁移固定：列全部真实读写/恢复消费者→复用既有领域判据移到目标owner→更新全部消费者与通知→删除被替代实现→整组生成JS→检查及实际行为。不存在“旧代码先保留作兼容”、仅迁写不迁读、仅迁按钮不迁恢复。

### 11.3 验证选择：明确命令和实际行为，别让低模型刷全量

- 组A一次运行 `npm run check:types`、`npm run build:frontend`、`npm run check:generated`；受影响生成物必须同步。正式原生页面路径需独立Chrome无头临时profile，观察页面+console/network+IDB。不得仅用语法绿或`open()`吞错证明恢复。
- 05复用 `evals/product-v2/node/attempt-contract.test.mjs`、`confirm-contract.test.mjs`、`generation-isolation.test.mjs`；真实IDB两tab预占/late-action场景用既有浏览器宿主，HTTP请求计数为副作用判据。仅新增缺少的确定性交错反例，不写源码扫描断言。
- 06复用selection/package/delivery-gate领域判据及 `tools/verify_v2_6_1_selection.py`、`verify_v2_6_3_project_transfer.py`、`verify_v2_6_2_delivery.py` 的相应已存在入口。所选旧候选/取消采用/规格变更/导出snapshot/Blob/hash是判据，不是mock转发调用次数。
- 07–08使用既有UI/交互/可访问性入口的实际改变路径，辅助部分复用 `verify_v2_2_2_semantic_provider.py`、`verify_v2_5_2_vlm_review.py`、`verify_v2_5_5_suite_review.py`；先全离线正式UI验证。CLI参数从当前工具读，不能按旧聊天猜。
- 10用已有 `release_transaction_probe.py --selftest`、`--page-smoke`、`--fingerprint` 获批Linux入口；不因Windows缺Docker复制一个假脚本。11才运行既定两轮完整离线回归及范围匹配正式验收。
- 会向evals写证据的验证器串行；无需每包跑全仓。控制守卫仅在该包改权威/恢复点时做所需检查。修复后重验失败的具体行为，不把“重跑这回绿了”当间歇根因证据。
- 预算/次数以计划§2.1/§16.1及实时原账本为唯一门。本次旧占用1.61/5元、image8/semantic5保留，新许可最多3元、5次生图/每次1张及2次理解/复核；未受影响真链优先复用，只补必要完整路径或改变缺证。价格/输入上界、公开许可、预算及安全注入先成立，Unknown计次数/保预留；不自动花额度/付费调试/借默认key，超过门及时升级。

