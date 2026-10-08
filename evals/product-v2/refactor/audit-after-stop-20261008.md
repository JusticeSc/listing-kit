# 停工后的工程审计、状态核对与后续规划（2026-10-08）

> NOT-AUTHORITY：本文件仅保存本次时点观察与规划建议。目标/任务/权限取 `docs/product-v2-refactor-plan.md`；结构准出取 `docs/product-v2-refactor-design.md`；恢复前沿只取 `_working/amz-listing-kit-product-v2/state.md`。
> 最新请求仅为审计、确定状态与规划；此前“结束当前工作”未被解除。本轮不恢复施工、不改产品/验证器/CI/依赖、不提交推送部署、不删除V1、不调用付费模型。

## 1. 结论

当前是**已发布、可启动的 Product V2 候选 + 未完成的完整工程验收 + 独立停放的 V1 清理 WIP**，不是空壳，也不是工程Goal完成。

1. 上次未观察完的 main 发布已经成功，不能继续称“线上发布未知”。
2. V1清理没有进入main或线上；停工分支不可合并。旧恢复说明存在分支材料可达性和验证范围错误。
3. RC19启动/载入间歇仍缺现象—机制对应，最终同候选两轮、完整真实辅助任务与适用矩阵仍未成立。
4. main的分支保护和独立review没有成立证据；本次API直接返回 `protected=false`、规则为空、PR #5 reviews为空，不能声称受保护审查已完成。
5. 原state的8/10不是当前剩余额度。随后至少有新的探针/取样/构建/V1工作段；继续施工前必须处理原10轮停止门，不自动再给两轮。
6. 本轮只纠正state的用户停工阻塞，不把真实active系统Goal伪造为paused或completed，不修改正式验收标准。

## 2. 基准与当前落点

| 对象 | 本次直接观察 | 范围与限制 |
|---|---|---|
| 当前检出 | main `0572b5c9c042502b77fb2a5e302f5775bbfd46fc`，审计开始工作树干净 | 本轮结束只新增审计证据/原文备份并修改state；不提交 |
| GitHub main | 同一 `0572b5c` | 没有fetch/checkout/reset/rebase等变异操作 |
| 停工WIP | 本地 `feat/v1-sunset-20261008`，`15faa65` | 相对main：126文件，114删除、3修改、9新增恢复/快照文件；未checkout或执行WIP |
| 系统产品Goal | 原生 `goal.get`：`159d03ed410f9ff9`，active | 正文sha256 `bac1155dbef21876391328dafd50a5624dee8461388754021a31aa59ff1c6fc6`，匹配计划§2.1；active不解除用户停工 |
| 正式进度 | R5.1未完成；R5.2/5.3、R6.1–3、R7.1–5仍pending，R6.4仅历史范围done | 不以CI或本次审计把任何整项标done |
| 本轮证据 | 同前缀 `audit-after-stop-20261008-observations.json` | 原生Goal/GitHub观察、发布工件、可信HTTPS页面/资源hash及计数口径 |

比较范围：停工WIP用 `git diff 0572b5c...15faa65`；已合并差量沿上一审计基准 `132884d...0572b5c`；当前代码与分支blob分开，快照副本不当活代码。

## 3. 发布：已经成立的事实与尚未成立的合同

### 3.1 当前发布已确认成功

- [PR #5](https://github.com/JusticeSc/listing-kit/pull/5)：2026-10-08T10:36:30Z merged，merge `0572b5c`。
- [main run 37764592110](https://github.com/JusticeSc/listing-kit/actions/runs/37764592110)：completed/success；两个job均success，结束于10:58:44Z。
- 实际job日志：Docker构建/health smoke；真实隔离容器selftest **32/32**；真实脚本离线故障类别 **13/13**；远端Docker deploy；可信HTTPS页面 **10/10**；源码/配置/镜像指纹；finalize；工件上传均成功。日志中 `release_finalize_rc=0`，previous已清理；本次没有执行新的回退。
- selftest的ST-DEAD FAIL是必须失败的不可达负例，外层ST-09据此PASS，不是成功发布中的产品红。
- selftest已在真实镜像origin做页面保存/刷新/项目包往返，并有不同image ID、同origin代表项目的文档/Blob/采用保全；这是隔离marker A/B版本的机制证明，不等于对两份真实历史产品版本做过生产回退。
- 线上PS是空项目新建/刷新/项目ZIP下载导入，不证明商品事实→真实生成→返工→采用→交付完整任务，也不证明线上代表项目跨产品版本恢复。

发布工件：[artifact 11545870528](https://github.com/JusticeSc/listing-kit/actions/runs/37764592110/artifacts/11545870528)，已下载到工作区 `releases/audit-37764592110/`，未改线上。

| 身份 | 工件值 |
|---|---|
| commit | `0572b5c9c042502b77fb2a5e302f5775bbfd46fc` |
| image ID | `sha256:ce90236c206c8a87d7ee41d53926b62cf23d2e6aa781f75f80a6f957a63c5649` |
| runtime SHA256 | `44f2e9b9a00c2d8fd870ed0adf71baf7bdd6b2cabaa2f059c2b0870b75e43d30` |
| public configuration SHA256 | `752430317ec03bc99e24ea2ef0bfadddd200ae7694f6c61844ef0e1dc885af51` |
| Caddy SHA256 | `e375655dcf81ada9a4ac315ceaf1791bbdf1c9ba3bb0aab0f529fc6eae4de176` |
| runtime实际枚举 | 85文件，default_trial=closed；没有旧V1/fixture路径 |

本次独立Chrome无头临时profile访问 `https://47.115.172.233:8080/`，保留TLS验证：首页200、secureContext=true、新建按钮就绪，health/capabilities=200、默认付费档closed，console/page/requestfailed均空。首页/styles/entry/app/workspace/generation/adoption/delivery八个实际HTTP资源hash全部匹配当前工件。仅GET/首页观察，不创建业务项目、不发模型请求；没有SSH读取宿主当前image ID，发布时工件身份与当前公开资源一致分别陈述。截图 `../evidence/audit-after-stop-20261008-home.png`（实际756×481，不冒充1366或真实缩放验收），浏览器/profile已释放。

### 3.2 审查/保护与准出不能借绿灯放行

GitHub当前只读API：main `protected=false`，protection.enabled=false、required status checks为空；`rules/branches/main=[]`。PR #5 `reviews=[]`、reviewDecision为空。CI成功和合并事实成立；独立审查/保护合同不成立，不能用“现有流程”字样假装有强制保护。后续发布前应设置并验证既定检查/审查要求；本轮不改GitHub设置。既有RC19和最终验收仍未完成，已经发布的事实不能反向证明计划§7.6/§7.7所有产品准出成立。

## 4. 六项Goal准出映射：已有资产与仍缺证明

| Goal条件 | 可复用的直接证据 | 当前缺口与裁决 |
|---|---|---|
| SC1 人工/辅助完整任务 | manual.json：空页面人工确认/一次提交/返工/采用/无AI两包/同origin重启；原两Adapter真链与2026-10-05原图2239735B真实图文理解子步 | **partial**：辅助任务没有连续走到原生两包；人工链Fake不证明真图忠实度，初始批次全请求轨迹明确缺失 |
| SC2 三用途BYOK/按需AI/秘密 | packet08真实页面输入/正式消费者出站、合法图缺key、真实旧schema拒绝已修；主路径与live default_trial=closed成立 | **partial**：S5长度oracle/压缩ZIP扫描/缺失表面不能证明精确用途key与完整秘密隔离；不是产品泄漏结论 |
| SC3 事务/恢复/结构与已知缺陷 | 五owner/四视图/既有事务及main CI相应行为、HTTP未读正文修复、settings草稿/容量/停止/报告消费差量保留 | **partial**：RC19因果仍缺；4_2加入TimeoutError及同action/task DOM+IDB接受规则不是受控时序因果证明；结构六项需范围匹配综合准出 |
| SC4 模拟真人/视觉/键盘 | manual/zoom证据：真实页面、真实125%/200%缩放、1440/1366/390关键可达、键盘导出 | **partial**：辅助分支完整走查未证，不能拿截图文件存在代读图；C17/C15独立真人仍未发生 |
| SC5 类型/两轮/清理 | 已改变集合types/generated/Node/CI、p11close2的当批44×2、旧实现材料可恢复 | **partial**：R7.3 WIP未闭合，最后消费者/V1改动后同源码候选两轮及最终指纹缺；信号hash不是源码hash |
| SC6 当前候选/发布/回退 | 本次真实Docker/不同image markerA-B、镜像origin页面、同origin数据恢复、HTTPS/指纹/finalize与8份live字节一致 | **partial**：R7.4最终冻结未发生；当前main无强制保护、PR无review；既定回退机制可复用，不扩大为必须两份历史产品版本 |

RC19最新网络诊断 `asset-continuation-20261008-rc19.json`：600次/34800请求未捕获拒连，464740事件未出现对应refused。这只说明本次未触发，不建立因果、不关闭RC19。不能再以同配置连续绿、加等待或另一机制放行。

## 5. Standards：停工WIP与恢复纪律

### S1（高）：用户停工门没有落入唯一恢复入口

审计开始state头仍“继续吧”，R5.1 active、blockers=[]；实际 `refactor_resume.py` 输出active/R5.1，没有停工提示。工作区外handoff不能替代INDEX指向的state。本轮只将R5.1改blocked，填任务前缀的停止/额度/缺证阻塞并指向本审计；系统Goal仍active，不伪造paused。Phase5保留其历史未完成active归属，不作为施工许可。

### S2（高）：WIP的历史缺证降级不能仅补参数收尾

`15faa65:tools/check_project_state.py`新增 `_evidence_ok(..., superseded=False)`，两个v2调用点未传，故已知历史J6红仍在；本轮不重跑确认。reviewer按15个done任务的两类指针静态复算为30条J6，不是handoff写的10条，静态复算不冒充本轮执行结果。即使接线，按superseded给**任意**missing降note会掩盖与V1日落无关的历史证据丢失。应只认可有精确退休清单/原commit或归档hash的路径；当前证据继续严格报错、历史意外缺失仍报错，复用现有反向探针。不为绿灯重写历史或添加通用兼容层。

### S3（高）：保存现场时违反精确纳入规则，旧handoff的文件状态不准确

AGENTS:103–105禁止 `git add -A`，只晋级选中最小证据。停工保存15faa65实际用了add-A，将9份快照/恢复文件也纳入WIP；126文件不是126产品变更。切回main会移除这些分支专有路径，故旧handoff“快照仍untracked/当前路径可用”不准确。材料未丢失：Git blob已验证ZIP hash `4007b9b1…`、manifest hash `a6269682…`；本轮原生字节hash另证当前main的 `_stage-amz-control/asset-continuation-20261008T054352Z/data/manual-project.zip` 与该代表包完全相同，重载荷并非仅在WIP。main上的R7.3探针默认数据输入/专有材料路径不可达，探针脚本本身仍在工作区根 `_working/`；后续精确提取/恢复，不checkout/reset覆盖本轮未提交state，不以当前路径缺失断言原件丢失。reviewer核对114个删除文件均匹配删前manifest/hash、133个Python文件静态无指向删除集的import；这是静态依赖审计，不替代删后smoke。实际删掉23个 `verify_product_v1_*`，本轮git集合计数23，不是handoff的31。

### S4（中）：R7.3数据探针仅是有限导入/项目包往返

工作区根 `_working/_probe_r73_data_recovery.py:158–193,200–230`检查项目身份/名称/revision、文档/资产数量、资产名字/字节hash与项目ZIP成员。没有逐条文档payload/采用/current比较，没有实际返工，没有交付ZIP轨迹，也没有hash与manifest完整合同逐项核对。旧handoff将它称为“打开/返工/导出可直接复用判据”过宽。保留其项目包/Blob子步；R7.3还需复用原6_3/人工链证明真实返工和交付，不新造验证平台。

### S5（高）：BYOK旧空证已修前置，但“精确用途/完整包无泄漏”仍有证明缺口

`tools/verify_v2_packet08_settings_vision.py:61–65`三用途哨兵长度相同；`:524–530`捕获请求即把key缩为长度，`:672–677,717–722,741–746,761–766`只比较该长度，无法区分同长度的错误key或用途错换。`:786–793`直接把压缩ZIP原字节decode扫字符串，没有逐成员解压，也没有扫描localStorage、交付ZIP或服务端日志；`:148–150`的IDB dump将Blob替换为大小占位。长度/压缩字节扫阴性不能覆盖设计§11.5.3:535的精确用途key与完整秘密隔离合同。

真实页面键入key、正式消费者外发、合法图片缺key与旧格式实际上传拒绝已经补上，保留这些成果；不能又把它们称为全部空证，也不能由缺证推断产品实际泄漏。后续在同一现有入口用内存中精确比较或非秘密哨兵等值布尔后置，证据不保存真实key/hash；独立读完整localStorage/两包解压成员/相关日志，补足具体缺的表面，不购买模型调用或新增安全平台。

## 6. Spec：当前仍阻断整项交付的条件

- **P1（高）缺陷准出**：RC19现象—机制/受控修复仍missing。当前已发布不消除计划§7.6的禁止外推。
- **P2（高）最终任务与矩阵**：当前真实辅助完整任务、全用途BYOK/旧task补key与秘密隔离的范围匹配证据、结构六项综合准出不能由人工Fake/局部绿色替代；正式R5/R6仍未完成。缺项应按消费者逐项复用/补证，不重写全部Module。
- **P3（高）清理/最终候选**：R7.3 WIP未闭合，main仍保留V1入口；最后消费者/V1改动后的同源码候选两轮尚未发生，最终矩阵仍引用旧历史完成材料。不得提前运行R7.1凑绿。
- **P4（高）保护流程**：现有API直接证实没有main强制保护和PR review记录；后续合并/发布需成立真实保护/审查，不补造签署。
- **P5（中）旧规约冲突**：design§9.1:233及context§2仍写真人日落前保留V1，与更新后的计划R7.3/§15.6工程清理授权不一致；后续同包同步，不用旧条款阻止已授权方向，也不借新条款静默删除未判定独有用途。

pre-V1 `run.py/web/渲染器/docs/cards/M-series`确有第二运行面与活控制面消费者。旧handoff自行称其“明确不在R7.3范围”尚不能当用户决定。推荐先按当前产品用途明确退出旧运行入口，再迁移必要卡片/规则消费者，保护共享数据治理与历史原件；是否同时纳入这些pre-V1活路径，必须在恢复范围中明确，不能仅改名legacy把两套系统长期留下，也不能以清理名义误删共享能力。

共享模块保留原因更正：当前V2无 `product_facts` / `review_contract` importer，旧handoff以“V2在用”解释错误。实际 `src/eval_dataset.py:115,325`分别导入review_contract/product_facts，`src/pilot_registry.py:227`导入product_facts；P系列/数据/试点治理仍消费它们及data_policy。`console.py`、providers包仍有V2活消费者。reviewer核对jsonschema仅由已删product_v1_contracts/semantic_drafts导入，可在cutover同步pyproject/lock；保留必要P治理不能当所有pre-V1产品运行面的豁免。

本轮双轴审计条目：Standards S1–S5共5项（4高/1中），Spec P1–P5共5项（4高/1中）；同一缺口的不同规范/准出角度不作为独立产品缺陷数。六项Goal条件均为partial，不代表六项产品功能都不能使用。停工恢复入口偏差已更正，其余产品/流程缺口仅记录，未修复。

## 7. 预算、批次与停止门

账本未改：image8、semantic/VLM5、共13次；已结算1.15元、含可能计费占用1.61元；累计上限5元。此前新增最大3元、5次单张生图、2次理解/复核是许可上界，不是必须花掉或余额；停工期间不调用。

旧state明确保守占用8/10。`git log ef8cda1..15faa65`随后包含：

| 新工作段 | 具体改动/身份 | 归类 |
|---|---|---|
| 发布probe三类错误机制 | `986a6df` | release消费者与必要运行 |
| 批次状态/进度同次取样 | `300c1c4` | 4_3验证消费者与必要运行 |
| 构建下载层同类修复 | `639661c`/`9a461fb`合并计一段 | host/Docker同一基础设施类 |
| V1入口/验证/guard切换 | `15faa65` | 未完成/失败尝试也占用 |

沿既有独立消费者工作段保守口径为**8+4=12**；这不是补造唯一精确历史次数。即使将其中工作段合并，也不能继续使用旧8/10来默认还有两轮。原10轮门已达到，必须保存成果并向用户明确申请后续额度/核定，不擅自重置。文档纯记录、只读审计/恢复不计产品实施批次。当前WIP和最终两轮不可据旧handoff直接启动。

## 8. 后续规划（待明确恢复及停止门决策，不是本轮施工许可）

| 顺序 | 既有任务 | 下一次输出与准出 | 不重复的工作 |
|---|---|---|---|
| 0 恢复与授权 | R5.1恢复前置 | 明确恢复用户停工、处理10轮门、明确pre-V1清理范围；同Goal核对、保持账本；查明保护/审查能否按原合同落地 | 不新建Goal/总架构/验证平台，不重新算零 |
| 1 准出阻塞定位 | R5.1/RC19 | 复用失败URL/阶段/netlog；只在能区分产品生命周期、监听/连接、浏览器传输的新假设下采集对应层。因果无法成立则保持阻断，提出最小用户决策 | 不再600次碰绿、不新增默认重试、不把bind0或HTTP修复外推 |
| 2 剩余产品/类型证据 | R5.2/5.3、R6.1–3、R7.5 | 把当前消费者映射到人工/辅助/三用途BYOK/旧task/六结构项；仅补missing路径。辅助完整任务必须真图字节、人确认、真实候选/采用/两包及读图；真实调用先准入与预留 | 复用五owner/四视图/emit、人工无AI链、缩放、两Adapter与原真链，AI复核可选 |
| 3 一次完整清理cutover | R7.3 | 先满足G6/R7.5及用途/消费者/代码同版本数据材料；精确复用15faa65，收窄guard退休口径、同步所有当前入口/文档/依赖/构建/CI，实际删后打开/目标返工/采用/两包/刷新恢复 | 不重删114文件、不重做已成立镜像allowlist；不单纯补参数/改文案就合并 |
| 4 冻结最终候选 | R7.1 | 最后消费者/V1改动后固定源码/生成产物/配置身份，按verification.json及现有44条清单串行两轮，逐项必要判据通过；保留失败，不拼跨版本绿 | 不购买两轮真链、不将结果信号hash称源码指纹 |
| 5 最终交付与发布 | R7.4 | 适用RC/结构矩阵逐项direct/proven；真实审查/保护满足后PR合并；最后候选镜像origin/TLS/页面/配置/镜像及finalize，代表项目与同origin数据恢复范围直接对应 | 按设计§10.8复用真实不同image/marker A/B与恢复机制；不扩成必须两份历史产品版本，也不为本次审计主动做生产回退 |

C17/C15独立真人继续单列未发生，不计作代理模拟通过；不作为本轮工程清理的人工前置，也不从记录抹掉。

## 9. 本轮实际运行与记录范围

1. 审计前冷恢复：rc0，active/8阶段27任务/next R5.1，无停工阻塞——用于发现恢复记录不准确，不当施工许可。
2. 当前main `uv run --locked python app/server.py --check`：rc0，52/52；真实本机HTTP/网关合同、显式替身、无付费模型；不是完整UI或真实供应商质量。
3. GitHub run/pr/branch/rules/artifact只读查询；下载既有工件；没有触发rerun、合并、SSH变更、deploy或回退。
4. 隔离Chrome无头/TLS只读首页、公开API与八个静态字节；截图已实际观察，浏览器/profile关闭；没有业务项目写操作、key或模型请求。
5. 未运行已知WIP guard失败或RC19场景来重新确认；未跑两轮回归、未新建永久测试/脚本。
6. state更正前原字节 `_stage-amz-control/audit-after-stop-20261008/state-before.md`，sha256 `2555cfcb00fac971d00a28963a79a87c5ca420c9556118ffc9b16853a0dd7e7e`。更正后串行实跑：`check_docs.py --no-run` rc0（仅文档一致性，不证明围栏命令真跑）；`evals/probes/project_state.py` 64向全部匹配、隔离副本不写权威state；`refactor_resume.py` rc0、8阶段/27任务，next R5.1 **blocked**，真实打印用户停工/10轮/RC19/验收缺证及“不得开始受限执行”。计划/Goal正文与验收标准未改。
