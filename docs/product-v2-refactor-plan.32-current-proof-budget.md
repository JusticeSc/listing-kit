<!-- 拆分件 product-v2-refactor-plan.md · 第32/42片 · current-proof-budget · main 行1148–1200 · 源 11902b32651f4690f7367624377dcde6652e0a97 -->
> 导航：父页 [product-v2-refactor-plan.md](product-v2-refactor-plan.md) · 31 [上一片](product-v2-refactor-plan.31-current-delivery.md) · 33 [下一片](product-v2-refactor-plan.33-later-startup-history.md)
> 本片逐字节保存 main 原件「§17.5–17.7 证据、费用、停止与完成」，不重写、不摘要；完整计划须按父页目录顺序与注册表规则拼接后阅读。
> 续接标记：无（本片首尾都不跨越 Markdown 围栏，正文与 main 原件逐字节相同）。
### 17.5 证据复用、验证执行与交付清单

复用原 `walk_to_adoption/walk_to_deliver`、现有6_2/6_3/5_3/5_4、正式Adapter Transport、原生恢复包及当前基线；不新建第二套walk。当前原型、B0文档或播种数据仅是其范围证据。断言变动按消费者语义迁移，删除实现/文案/mock回声测试；新增永久用例只抓边界、状态/并发、错误或权限。

| 改变的合同 | 复用入口与实际后置 | 不变时不重做 |
|---|---|---|
| TS/产物 | 当前main按`package.json`实际scripts及README构建：`check:types`、受影响时`build:envelope`、`build:frontend`与`build:frontend-node`，真实消费Vite/tsc产物 | 当前main没有`check:generated`脚本，不运行或捏造该旧命令；§2.1原生观察原文不为清理命令而改写 |
| payload/展示/编译 | 现有domain行为及3_3/3_4/3_6、生产parser与正式输入→Prompt当前性 | 不钉字符串/源码位置，不重复已证人工稿机制 |
| 执行/返工/授权 | 4_1–4_4/5_4及两正式Adapter解码出站、partial/Unknown/精确无关对象后置 | 不把所有网关/浏览器项变成每批全量 |
| 报告/采用/包/历史 | 5_1/6_1–6_3及真实IDB、报告故障、实际下载/独立导入/刷新 | 不用包非空/hash数量替代逐条与字节一致 |
| 工作台 | 5_3/6_4/ui_2与实际图像表面、键盘/焦点/真实zoom、console/network/IDB | 不重建原型、不能拿截图数冒充效率 |
| 权威/状态/绑定 | `check_docs.py --no-run`、`refactor_resume.py`；正式依赖/状态改动后既有反例 | 不日常刷新全量控制探针；准备不改机器块 |
| 最终/发布 | 当前`verification.json`登记的R7.1两轮入口与原R7.4实际受测image/HTTPS页面/回退 | 不复用早于最后改动的green或对另一origin的自测 |

这些是风险到入口的索引，不是声明现有验证器已经覆盖新schema/新模式。启动时核对其真实前置/CLI；用例在现有入口演进，按§15.3批末运行最小集合，串行浏览器/全库磁盘验收，避免证据并写造成假红。当前权威配置定义可执行模式，不凭文档自造参数。单次既有检查失败按最早失效层处理，不循环重跑洗绿。

最终材料最小集合：正式代码/生成物与版本身份；五条用户路径当前直接证据；全部真实收费结果与逐图像素判据；两模式实际请求非秘密来源；原生完整项目包/交付包原字节及独立导入后置；同候选最终两轮/RC与结构矩阵；当前HTTPS发布与真实回退。每批只在所承接原任务记录实际结果、复用前提、仍未证和next，不添另一套计数/监控平台。

**已静态核对的命令**（本次未执行产品命令；尖括号是实施时填入的当前候选标识或可信origin，不是造新参数）：

```text
# 组内连贯修改后的必要类型/产物，行为按受影响范围
npm run check:types
npm run build:frontend
npm run build:frontend-node
# B3完整竖向组：沿用真实页面walk与原生两包消费者
uv run --locked python tools/verify_v2_6_3_project_transfer.py --label <候选标识>
uv run --locked python tools/verify_v2_5_4_rework_loop.py --label <候选标识>
# B6最终冻结：默认完整清单，不使用--only/单轮放行
uv run --locked python tools/verify_v2_7_1_regression.py --rounds 2 --stamp <候选标识>
# B7只对实际受测环境/镜像取证；空项目page-smoke不代替完整线上数据链
uv run --locked python tools/release_transaction_probe.py --page-smoke --base <既有可信HTTPS-origin>
uv run --locked python tools/release_transaction_probe.py --fingerprint --runtime-root <实际受测镜像代码目录>
```

`release_transaction_probe.py --selftest`仅在其Linux/Docker运行前提可达且该机制受影响时执行，不因发布或本地改HEAD就重做；不能用本机目录fingerprint冒充实际image。4_5默认即paid类，不像无参两Adapter入口那样离线，不在准备/B3/CI调用；B5真实执行先按该入口/实际正式页面的真实参数和§17.6门预留，不拿“无--live”当无费用证明。

### 17.6 当前收费与动作准入

- **额度来源**：当前新增金额、类别次数、n=1及适用模型只取§17.13和state；旧§2.1/§17.10–12保存各轮事实，不重新激活。承接最新封存完整账，不能使用工作树旧账“余量”或重置历史累计/失败/预留。历史单价、旧price-readiness或预留示例不是本轮官方价格已核证据，不能照旧价格直接预留。
- **激活/预留**：授权幂等标识固定为`complete-product-authorization-20261018T114240Z`，出处为同名stage的`authorization.json`，不是Goal ID。本轮完整账已核封存来源/hash、承接并激活一次；当前唯一控制块为`_working/amz-listing-kit-product-v2/budget-ledger.json`的`current_control_15ab22bf3386b9cf`，连同对应lane逐笔记录及累计上限决定准入。旧授权已归档，根历史spent摘要不参与门。同标识不再加额或追加激活，完整历史及Unknown保留，不另建账务平台。每次先核必要缺证、当前官方最大费用、实际输入/素材权限/hash和安全渠道，再预留金额与类别次数；理解/创作辅助/复核共享辅助门，失败/Unknown/返工/对照均占额，金额或次数先到即停。
- **调用选择**：优先复用合法原照/确认事实与有效真实能力；只补新程序稿品质/新模式缺证和有具体假设的返工，不买接线调试/稳定隔离/旧五图重演。价格上界或精确型号不可核时停相应调用，人工/离线路径继续；预算不是必须花完，也不保证成品一定合格。
- **秘密与素材**：沿有限现有模型/官方安全目标、默认试用closed、BYOK标签页/请求内存；不读取GitHub Secret值、不要求贴key、不保存secret/key-hash/签名URL/Base64诊断。新模型、供应商/私有上传或凭据新渠道另行获准，不能由工单或CI登记推导。
- **工程/远程**：历史批次保留但不再按旧10批/余3批停止已获准的完整交付；无新事实的重复路径仍按§17.3停止。提交/合并/发布按最新授权及真实绑定/独立审查/适用CI/实时保护执行；main push会自动部署，不能靠“只是文档”忽略副作用。较弱模型自验不替代独立审查，不改桌面/日常profile。

### 17.7 停止、升级与完成判定

必要信息尽量由仓库/原证据/官方资料取得；不让用户重复制定标准或提供可读文件路径。出现以下情况停止对应受限动作，保存成果及最小可恢复材料、准确缺口与下一决定：预算/类别次数达到门、费用上界不可界定、凭据/许可/可信发布条件不可达；不可逆用户数据操作、整体架构/新模型/权限扩张或改变已确认需求；原间歇缺陷无法建立对应机制/正式消费者证据；真实像素不合格而额度已满；正式依赖无法在获批规则内可达。继续其他已获准且依赖成立的工作，不伪造降级或用替身完成缺真链。

Unknown只核对/取回原任务，不因供应商超时自动重发；无可核对task的同步Unknown保持未确证，不伪造task或借默认key重提。在途结果按原项目/原action保全，停止只停后续新增，不虚称上游取消。新缺陷复用已有失败并按最早失效层定位，用户报告不重跑确认；修必要消费者，不误解为只改一个文件。无信息增量停止点按§17.3执行，原生/预算/Unknown门不受旧todo覆盖；旧10批上限不覆盖§17.13的新完整交付授权，历史批次不清零。

Goal完成须B0–B7所有适用结果直接成立，包括完整真实合格套图、两模式真实来源、新旧历史/两包恢复、最终同候选两轮、剩余原工程门、当前HTTPS发布及实际同origin回退。C17/C15作为未发生的独立真人外部门单列，不填通过。任何必要项missing/indirect/contradicted均不完成Goal；“本地工程通过”“设计准备完成”“已上线”三个结论各有各的证据。

