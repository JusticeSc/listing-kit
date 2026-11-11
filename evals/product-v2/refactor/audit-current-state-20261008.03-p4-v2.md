<!-- 拆分件 03/03 · 父文档 evals/product-v2/refactor/audit-current-state-20261008.md -->
# P4：已发布镜像的运行闭包与“仅V2”声明矛盾（高）
[返回 audit-current-state-20261008.md](audit-current-state-20261008.md)

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
