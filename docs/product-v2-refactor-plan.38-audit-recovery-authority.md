<!-- 拆分件 product-v2-refactor-plan.md · 第38/42片 · audit-recovery-authority · main 行1315–1325 · 源 11902b32651f4690f7367624377dcde6652e0a97 -->
> 导航：父页 [product-v2-refactor-plan.md](product-v2-refactor-plan.md) · 37 [上一片](product-v2-refactor-plan.37-billing-preservation-history.md) · 39 [下一片](product-v2-refactor-plan.39-audit-recovery-principles.md)
> 本片逐字节保存 main 原件「§17.13 本次纠偏、完整交付与审计入口」，不重写、不摘要；完整计划须按父页目录顺序与注册表规则拼接后阅读。
> 续接标记：无（本片首尾都不跨越 Markdown 围栏，正文与 main 原件逐字节相同）。
### 17.13 当前用户纠偏与完整交付恢复边界（2026-10-18）

用户明确要求实质清理复杂性，而非将复杂现状跑绿。2026-10-17获批的独立main可信基线已随PR #13–#16合并；该轮实施/发布授权及实际结果见state与[Issue #10](https://github.com/JusticeSc/listing-kit/issues/10)，测试细项归[#7](https://github.com/JusticeSc/listing-kit/issues/7)，不再按旧P0→P1重新启动或重做V1清退/依赖替换。同日较早的仅审计/规划、随后仅#9零收费开发的权限都是历史范围，以下面的最新完整交付授权为准。原机器块和§2.1只保存真实原生观察，不因用户决定而伪造系统生命周期；审计证据仍见`evals/product-v2/refactor/status-audit-20261018.md`。

**#9切片已交付，不能从零重做**：原作用域Goal `15aacf5fbdd7001f`创建/读回见`_stage-amz-control/issue9-expression-20261018T080410Z/goal-{created,readback}.json`；PR [#18](https://github.com/JusticeSc/listing-kit/pull/18)受审代码head `3dc0018689dad39fb81294a9c76c99c97dc15e8f`及双审证据继续按原范围复用。说明修正后最终head `0ae7df59ff8e41e776195169ce8814f2699db45b`已于2026-10-18T14:29:26Z受保护合并为`72c33df03514eaedd6f3e6efdf57236f26ada9f6`；对应main run `39136220536`实际发布步骤success，准确身份/准入/发布证据只取state指针，不再沿用“Draft、未合并/发布”的旧现状。阶段发布不证明当前未提交差量、真实像素或完整#8/#9；旧作用域Goal不伪结清。后续只补新差量审查，不重做已交付切片，不误结完整Issue或产品Goal。

**用户已选择“完整交付，含受保护发布”及“新增最多5元”**：允许相关分支提交/推送、独立审查与现有保护成立后的合并及既有HTTPS环境发布；原12批止工后已经审计，最新明确追加最多6批的决定见本节末尾和state，不能把原完整授权解释为无限施工。本轮生图最多12次、每次1张，理解/创作辅助/复核合计最多4次，仅已批准模型，失败/Unknown占额并保留，不承诺预算内必然合格。新增额度已于2026-10-19一次激活，当前逐笔余额/累计门只取账本和state，不再次承接激活、不清零历史。原授权见`_stage-amz-control/complete-product-authorization-20261018T114240Z/authorization.json`。

**原生完整Goal真实active，原文保留不伪更新**：原get返回`No active goal.`后创建并读回`15ab22bf3386b9cf`，原始观察见`evals/product-v2/refactor/goal-observation-full-product-20261018T140710Z.json`；审计及本次恢复再次get仍同ID active，正文hash不变。§2.1保存原观察全文，用户明确追加的批次上限另取本节与state，不伪结#9或恢复旧Goal。PR18阶段承接、新增模型额度一次激活均已有证据；后续只核逐次收费准入，不重新激活。

**2026-10-19用户要求先审计调整再继续**：已授权范围与完整终点保持不变；先核当前差量、消费者真实后置、失败证据及实际批次占用，再按state修正后的唯一前沿执行。不把未提交等同未占额，不以局部测试数量、后续重跑绿或历史发布替当前业务准出；本次观察及精确复现边界由state指向同一审计证据，不另建计划/状态。
