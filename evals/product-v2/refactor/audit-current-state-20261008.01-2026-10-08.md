<!-- 拆分件 01/03 · 父文档 evals/product-v2/refactor/audit-current-state-20261008.md -->
# 既有工作审计与恢复规划（2026-10-08）
[返回 audit-current-state-20261008.md](audit-current-state-20261008.md)

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

