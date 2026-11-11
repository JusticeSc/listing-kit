<!-- 拆分件 06/29 · 父文档 docs/product-v2-refactor-design.md -->
# 实施规格：Interface与所见摘要
[返回设计目录](product-v2-refactor-design.md) · [上一主题](product-v2-refactor-design.05-history-and-delivery-exit.md) · [下一主题](product-v2-refactor-design.07-reservation-and-observations.md)

## 10. 提前冻结的高难度实施规格

本节解决低模型不应临场选择的算法和边界；符号标为“目标”的方法尚未实现。现有依据：`generation.ts` 的 `authorizationUsed/pendingConfirmedShots/performSubmitAttempt`、`domain/attempt.ts` 的迁移/阻断规则、`storage/repository.js` 的 `readDocumentHead/saveDocument`、`session.ts` 的项目切换，以及 `review-delivery.ts` 的报告/ZIP流程。业务权限以计划§14为准，不把本规格变成新增范围或放行记录。

### 10.1 Interface收口与投影：不要把状态搬进另一份context

- 当前装配顺序为 **inputs → prompts → generation → adoption → delivery → views**；单图AI请求准备归adoption，generation内部持有授权/预约/队列，不再保留独立authorization转发层或反向review依赖。
- 恢复及写入归相应owner：attempt/candidate归generation，单图report及ack/selection归adoption，suite report/export归delivery，输入及proposal归inputs；workspace不能重新接管这些Map或恢复规则。
- `sources()` 是inputs提供的只读、无秘密、带文档版本的业务投影，不接受workspace手工重建可变Map。元数据改名用新project record同步投影，不冒充新会话或改生成来源。Prompt历史用精确版本读，不能用最新头替已确认版本。
- 每个owner仅保留本领域 `subscribe(changed)` 或同等现有通知入口，通知不传业务可变对象。View订阅后读取投影；生命周期装配在dispose时退订。不得把 `renderAttempts/status/showError/DOMElement` 注入业务owner。
- 命令结果用窄的判别联合：`kind: "committed" | "blocked" | "stale" | "failed"`；按动作附稳定reason、版本/原项目、必要artifact。沿用已有语义分析 `AnalysisOutcome`，不统一成万能结果框架。已落库但会话已切换是“committed、非当前会话”，不是保存失败；无当前UI下载权限则不自动触发下载。
- 投影方法不写库/不发网络。已持久化事实与用户未保存编辑分开；view只持有DOM、展开/焦点/滚动、未保存输入和ObjectURL，不能自行串保存→授权→HTTP→报告→采用。

### 10.2 所见摘要与精确失效：绑定“用户看见的那份”，不是重算后的新版

目标 `GenerationIntent` 至少携带projectId、会话generation、submissionMode、明确shot scope、confirmation documentId及seenVersion，以及所见 `ConfirmationSnapshot`。继续用 `confirmationSnapshot/canonicalJson/buildConfirmationRecord`；不另造hash算法、展示文字合同或第二份外发schema。

1. 展示摘要由generation调用prompts/inputs得出；按钮传这份intent，不只传shotId。本地默认Prompt准备允许自动进行，人工全文不被覆盖。
2. 提交时对所见snapshot计算hash；每次异步准备后检查action仍允许新提交，再比对当前对应scope的snapshot。变更则返回stale并显示新摘要，**不把新的内容自动当成用户已确认**。
3. `generation_confirm` 首次写expectedVersion=0；后续写用用户看到的版本。保存成功只说明记录存在，尚未取得跨标签页消费权；随后逐shot调用§10.3预占，不能直接POST。
4. 已确认待提交队列保留原目标6键：provider_id、model_id、protocol、capability_version、credential_source、sync。缺原凭据时提示补原目标，不从当前新动作设置借key；key值永不进入intent/snapshot/报告/ZIP。
5. 当前性分三类：**身份/历史用精确版本；有意改变的Prompt头与采用头用版本；其他输入按该shot实际消费的事实/用途/规格/风格/参考图投影**。复用并必要时修正唯一领域staleness判据，UI、事务、执行共用；不能另写一份近似规则。
6. 如无关shot调整只增加suite文档版本，事务中可同步重算该shot的消费投影；投影不变不误失效。删除该shot、改变其用途/所消费事实或规格/参考图则阻断。版本只是读取围栏，不把整个project revision当所有动作一票否决。

