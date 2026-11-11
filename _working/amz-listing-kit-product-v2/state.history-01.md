<!-- 拆分件 · 公开 main 历史原文 · 1/7 -->
> 原件：`_working/amz-listing-kit-product-v2/state.md`，公开 main `11902b32651f4690f7367624377dcde6652e0a97`。
> 当前边界与机器数据：[state.md](state.md) · 本页保留原时点，不构成恢复授权。

# Product V2 定向重构执行状态

> CONTROL-STATUS: current · AUTHORITY: execution-state
> 只保存产品门、权限、进度、证据、阻塞/未知与恢复动作；产品终点/正式任务依赖在计划，具体问题在GitHub Issue，工作流在AGENTS，不扩成第二套工单明细表。
> prepared 是未绑定新 Goal 的本地准备态,不是系统 paused。旧读数与完成记录只见 superseded 基线。
## 当前恢复边界

- **2026-10-21最新明确恢复：工程交付，最多追加第27–28批。** 用户在测试工具整改完成后的实际选择题中选择“恢复工程交付，最多追加2批”，允许适用审查、最终验证及保护成立后的提交、CI和既有环境发布；到限停止，不新增模型调用，不重置旧1–26批、失败、预算或93条Unknown。原始选择、恢复前字节及真实Goal观察见`_stage-amz-control/engineering-delivery-resume-20261021T105905Z/`。本条在上述范围内取代旧停工及测试整改专用权限，不自动授权依赖、模型、平台或原始profile写入。
- **当前前沿：V2.R5.1 active，按Issue #31收口当前候选。** 第27批先做实际差量独审、冻结及必要离线准出；第28批用于获准且保护成立的工程收口、CI/既有HTTPS发布与受影响线上恢复核对。实际失败后修复及重验仍另计，不把同一失败藏回原批次；用满仍未完成即保全停止。#33/#34本地工具修复已通过定向验证，但尚未提交或获远程CI；不把19秒局部比较证明当作最终连续两轮。
- **已成立结果按范围复用。** #28的387文档/32资产交接已关闭；#27正式派生并显式采用主图v8（1146²，主体85.8639%，裁区RGB与原图全等、四边纯白）；#30最终五图/两包独立导入刷新392文档/33资产全等，再导出仅manifest时点变化。五图、原生两包及逐图资格在`_stage-amz-control/zero-fee-development-20261021T052937Z/delivery/`，原387文档/32资产及主图原件保留，不重做已成立基线或模型调用。
- **失败与未证范围不抹除。** 第24批类型失败、第25批4个夹具/字面断言失败及第26批最终首轮49/50、第二轮未运行的原结果全部保留。第26批缺陷归#33，不是裁剪/导出失败。两轴旧独审与审后2个语义修复分开保留；本地schema2两包不冒充线上已经支持。
- **第27批已收口。** 当前候选产品`bf2fec7`、治理`2c2a6de`，两轴独立审查已返回：Standards唯一真实发现是状态格式拒绝反例漏登记，已恢复并实跑67/67（#35）；另两条（裁剪过期status、`.compare-body`闭合）由审查者依实际可达性与真实DOM自行撤回，未改UI、未加markup测试。冻结候选连续两轮各50命令全绿、指纹一致`290ee1bddc2b3a6b`、源码身份`2c2a6defc3ac`（`evals/product-v2/v2.7.1-regression-final_v3-final.{txt,json}`）。审查原始返回与撤回均保留在本次stage。
- **仍未证（不含已成立项）：** 用户本机原生125%/200%缩放（#29，隔离查看入口已就绪）、本次发布后受影响线上保全，以及C15/C17真人外部门。第28批只做获准的工程/CI/既有HTTPS发布与受影响线上恢复核对，零新增模型调用。
- **第28批已收口：受保护发布与线上保全成立。** `469afb7`（产品`bf2fec7`）经 PR CI [39599387495](https://github.com/JusticeSc/listing-kit/actions/runs/39599387495) 三项通过后按实时保护合并为 `70bb50e`；main push [39602287929](https://github.com/JusticeSc/listing-kit/actions/runs/39602287929) 走发布事务成功，线上 image `amz-listing-kit:70bb50e…`=`sha256:12f48dda…`、healthy、serving runtime `575584af…` 与 CI 候选一致、`default_trial=closed`、Caddy `e375655d…`。`release_transaction_probe --page-smoke` 12/12；线上导入保留项目包后五图均“已采用”且交付门通过；从线上导出两包（交付 6561662B/5 PNG、项目 45599853B），独立profile再导入为393文档（多出本次export_record）/33资产、五图Blob摘要等于保留原图。证据见本次stage `online-release-verification.json`、`release-evidence/`。异 image 同源恢复按2026-10-20同origin实测复用（脚本/origin/保护未变），本批未重跑额外回退演练。
- **仍未完成（产品准出）只剩真人门：** 用户本机原生125%/200%缩放与C15/C17；自动化证据不改写这两项。
- **人工与权限边界。** #29原生Chrome125%/200%由用户本机手动观察，不以CSS/CDP等价视口或可见自动化代签；助手继续其他已授权可达工程。C15/C17仍为独立真人外部门，不新增工程发布前置。最终完整Goal不因本地修复、CI或发布单独完成。
- **数据与资源保全。** 原始profile从未打开/写入；38个原profile状态文件、预算账本、原96份产品/测试源码冻结及旧证据保留。图16/16、lane3.06/5元、累计14.26/21元及费用/预留均不释放，本轮新增模型调用为零。旧宿主已关闭；本次已另起零模型查看宿主`delivery-native-zoom-27`（http://127.0.0.1:5505/），在独立副本实查392文档/33资产与五图采用/交付门后关闭了自有准备Chrome，原生匹配进程0。用户手动专用profile/命令与100%准备截图见本次stage的`native-zoom-human-handoff.json`及`native-zoom-entry-100.webp`；125%/200%仍未验，不重开或自动控制交给用户的profile。
- **真实Goal仍是原完整产品目标。** 本次真实get观察为`15ab22bf3386b9cf / active`，未新建、缩减、伪造resume或标记完成；§2.1原文hash仍为`6c1f59d0df5c6c867dac5aa090bb32ff915c7dfae2140494c653aab7598bf870`。此前停工、测试整改与保全原始记录分别保留在`zero-fee-development-20261021T052937Z/`和`testing-rectification-20261021T100549Z/`，不以原生active代替本次明确授权。

## 历史停止与准备边界（仅保留原时点，不覆盖上述最新授权）

- **2026-10-21用户要求“还有什么问题或需要澄清的吗，没有的话就做好开发准备吧”：本轮新增授权仅为开发准备。** 允许只读核对现有产品代码/保留现场、完善既有Issue的最小实施方案及维护必要恢复记录，并运行对应管理守卫；不恢复产品修改、构建/测试/回归、宿主/浏览器、生图、提交推送/合并部署，不追加图次数/实施批次/金额或改变原生Goal。准备后的首个交接执行入口为[Issue #28](https://github.com/JusticeSc/listing-kit/issues/28)，不等主图合格；该交接只需定向的“克隆隔离profile＋本地查看宿主＋正式导出”授权，不改原profile、不生图、不恢复产品施工（与#31“当前停工状态查看交接可独立进行”一致），仍不得据此改产品代码或部署。主图确定性派生方案归[#27](https://github.com/JusticeSc/listing-kit/issues/27)，其零模型调用路径不要求追加生图次数，但产品施工及已到上限的实施批次仍须另行明确恢复，发布另取对应授权。具体验收/代码入口只在各Issue维护，不复制新工单表或改写下方机器进度。准备前原字节、产品源码hash与工单正文保存在`_stage-amz-control/development-prep-20261021T043449Z/before.json`；本条不将“准备完成”冒充开工或产品完成。

- **2026-10-20 用户明确“记录在案，开始实施自我改造”，随后要求“多用issue管理任务”，并纠正把独立问题塞入旧Issue评论的做法：本轮仅恢复开发方法、现有执行工具、必要事实记录维护和Issue/PR管理（含新建及关联独立Issue），允许对应的定向离线验证；不恢复 Product V2 产品施工、产品回归、生图、提交推送、合并或部署。** 已有方法改造验收保留在 [Issue #7](https://github.com/JusticeSc/listing-kit/issues/7)；主图确定性修正由独立 [Issue #27](https://github.com/JusticeSc/listing-kit/issues/27) 跟踪，原生父单为 #9，建单不代表恢复实施。本地 `_working/ai-coding-bootstrap/work.md` 只保留权限、基线、证据和恢复指针。本轮不追加产品批次/额度，不改变原生 Goal 观察、16/16 图次数、20–23 已用尽、预留或 Unknown；`unknowns`/`blockers` 原文完整保留。只有能指向具体取代记录且完整覆盖原约束的条目才可另行历史化，首轮不归档或过滤机器记录。原字节与约束基线：`_stage-amz-control/self-reform-20261020T144442Z/before.zip`、`before.json`；本次工单纠偏前原字节另存同目录 `issue-management-before.json`。

