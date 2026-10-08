NOT-AUTHORITY — 本轮低模型执行准备证据；设计不证明产品已实现，也不解除停工。

# 2026-10-06 低模型开发前准备

## 1. 用户要求与本轮边界

用户要求先做好开发准备，由当前模型提前展开高难度重构设计，给出详细实施规划，下一轮交较弱模型按计划执行。本轮只读相关实现、收敛算法并更新现有权威文档；没有产品代码编辑、产品构建/测试/浏览器、真实模型调用、模型切换/配置、Git提交/推送、部署或V1/用户数据操作。

唯一恢复前沿仍是state的blocked `V2.R5.1`及原用户停工门。历史系统Goal观察不提升为本轮实时active；本轮没有可用实时Goal观察。准备文本不自动解除用户停工。

## 2. 事前原字节与交付入口

修改前五份权威文件精确快照及native SHA256：

- `_stage-amz-control/lower-model-preparation-2026-10-06T03-18-11-801Z/snapshot-manifest.json`
- 保存design、plan、INDEX、AGENTS及state原字节；不覆盖上一轮快照。

现有目标设计升级r2，新增§10–12；计划新增§15.5，INDEX/AGENTS定向指向规格和执行入口，state仅新增准备note及updated_at。未新建Goal/PRD/正式任务/依赖/验收矩阵。

- `docs/product-v2-refactor-design.md` §10：冻结所有权、DTO、摘要与精确失效、预占/action观察、生命周期、报告/采用/ZIP、生成物、发布回退。
- 同文§11：11个内部执行包、文件/符号顺序、原子联调组A、最小真实行为及升级条件。
- 同文§12：供用户明确恢复后复制给执行模型的启动文本。

## 3. 高风险决策及实现依据

| 决策 | 当前实现依据 | 防止的错误 |
|---|---|---|
| 跨tab一次事务读当前性、授权消费和业务阻断，再预约pending | generation.ts authorizationUsed/pendingConfirmedShots/performSubmitAttempt；repository.js readDocumentHead/saveDocument | 不同confirmation版本绕过防重；单页Set伪原子 |
| 按action分组，观察按numeric version、动作顺序按首预约version | domain/attempt.ts迁移/阻断；generation attempt/candidate链 | 旧成功遮住新在途；以防倒退为由丢旧结果 |
| closing先禁新动作，草稿保存失败传播，旧保全与新DOM分离 | session.ts openProject/closeProject；workspace.js open/close/loadWorkspace | 保存失败仍切走；旧callback/finally污染新项目 |
| report版本/消费围栏；单图candidate-current不冒充套图当前 | review.js reviewIsCurrent；selection-adoption.ts select；review-delivery.ts runSuiteReview/exportDelivery | 慢AI覆盖当前report；not_run抹Unknown；只围栏selection+suite漏spec/report |
| 完整项目单readonly snapshot，交付另做commit fence | storage/db.js withTransaction；repository.js现有索引；storage/transfer.js exportProjectPackage | 3事务混合快照；不必要二次全局无写围栏阻止项目导出 |
| compiler实际批准TS集合、两阶段收齐输出；所有消费者/恢复同步 | build_product_v2_ts.mjs；jsconfig.json；已有四个新TS与旧workspace装配 | compiler读过但不emit；半生成JS；TS/浏览器旧JS双轨 |
| 保留完整runtime指纹，真实不同image，晚期失败回旧服务；数据恢复另证 | release-transaction.sh；release_transaction_probe.py selftest；workflow/Dockerfile | 同image换tag充当双版本；health替代产品；容器重启冒充IDB恢复 |

两项并行只读设计研究已完成；父会话结合现有代码修正了建议中“拒绝旧action结果”“仅用JS交集缩小fingerprint”“项目ZIP二次无写围栏”等不正确方案。最终规格只在设计文档，不由agent报告另立权威。LSP status返回项目没有配置语言服务器，因此使用定向文本/原文件核对。

## 4. 原权限与目标不变证明

`lower-model-preparation-20261006-checks.json`保存native文本/字节比较结果：计划§2/§3/§6/§7/§9/§10/§14/§16保持不变；当前state除一个准备note及updated_at外全字段保持不变，因此所有任务/阶段状态、Goal绑定/观察、next、blockers、预算边界及原停工门均未被本轮更改。

Goal原文SHA256仍为 `6677a6803003f0894dd522bdd7102b53ca30c866532ff48fdc79e4b148d7c495`。新包仅为27个原任务内部步骤，不增加正式任务。预算现场读取为image8/8、semantic/VLM5/6、总13/14、预留1.61/5元；不能把历史新增3次误读为还有3次，本轮零外呼。

## 5. 文档与冷恢复实际检查

| 本轮实际命令 | 结果 | 工具测得wall time |
|---|---|---|
| `uv run --locked python tools/check_docs.py --no-run` | 全过，明确退出码0；实际/登记均62份；不执行文档内命令 | 1.19秒 |
| `uv run --locked python tools/refactor_resume.py` | `[PASS]`，8阶段/27任务；sole next=V2.R5.1，原用户stop阻断仍明确禁止施工 | 2.41秒 |

原始工具返回保存于 `lower-model-preparation-20261006-runtime.json`；五份权威交付后native hash保存于事前快照目录的 `preparation-result-manifest.json`。文档守卫及正式冷恢复已在本轮变更后实跑，不因历史绿灯推断；冷恢复明确不查询系统Goal，输出active仅是历史仓库观察。

上述只证明权威路由与禁止施工一致，不证明已修复当前页面失败、工程通过、真实模型品质或可发布。产品类型/构建、两轮、实际UI、事务交错、CI/HTTPS/不同版本及数据恢复均未在准备轮运行。下一轮须用户明确恢复，按设计§12和原计划读取当前真实Goal后才执行组A；本轮不将Goal标完成。
