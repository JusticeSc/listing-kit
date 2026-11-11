<!-- 拆分件 07/29 · 父文档 docs/product-v2-refactor-design.md -->
# 实施规格：跨标签预占与旧结果保全
[返回设计目录](product-v2-refactor-design.md) · [上一主题](product-v2-refactor-design.06-interface-and-summary-spec.md) · [下一主题](product-v2-refactor-design.08-lifecycle-reports-and-exports.md)

### 10.3 跨标签页预占：授权防重和业务阻断必须在同一事务

固定沿用schema v2、现有stores及索引，不新增ledger store、锁服务、租约平台或未测量索引。资产键用 `assetKeyOf(projectId, sha)`，文档键用 `documentKeyOf(projectId, kind, documentId, version)`。精确记录用get；文档头用现有 `by_project_document_version` + 数值version倒序cursor；某shot尝试链用 `by_project_document.getAll([projectId,"generation_attempt",shotId])`。不能按document_key字符串、updated_at、单页Map先后判新旧。

目标 `reserveGenerationAttempt` 输入为已校验pending Attempt、精确confirmation ref、shotId、见到的当前actionId/该action最后记录version（无历史为0）、Prompt ref、消费投影及资产sha列表。mode从落库confirmation读取，不能相信UI另外传入的mode。只接收非负整数expectedVersion，null/undefined不代表跳过。

事务外：校验Attempt/confirmation/Prompt、计算hash、准备参考Blob字节和HTTP固定body；读取settings内存身份/请求级headers。事务内仅IDB请求和同步纯判据，禁止fetch、crypto、Blob.arrayBuffer、timer或图像解码。

一次 `withTransaction(["projects","documents","assets"],"readwrite", ...)`：

1. 项目必须存在；按精确键读取confirmation及Prompt，确认payload/snapshot、shot归属、authorization ref和hash对应。Prompt当前头必须仍是授权版本；相关输入头读取后按§10.2投影验证当前性，所有引用资产键存在。
2. 读取该shot**全部**尝试记录，按action_id归组；每组取数值version最大的观察，组的先后按该action首次记录version。这个“最后预约动作”不是“最后追加文档”，后者可能是旧动作晚到结果。
3. 同一confirmation documentId+version+shot已有预约则消费冲突；不同confirmation版本也必须继续过当前action/mode/阻断门，不能因此允许重复。所见actionId/观察version已变则冲突，刷新投影重新让用户决定，不在内部循环创建新授权。
4. 复用领域状态迁移与阻断规则：initial只允许无尝试；failed_retry只允许当前动作明确failed；rework只允许已结束、非unknown的当前动作；explicit_new只允许用户明确承担风险的unknown，或无task_id的pending。任何另一个仍active且有task_id的动作都阻断新预约；不把显式另发当作取消原任务。
5. 对无task的旧pending，仅后续已成功预约且其authorization的既有submission_mode为explicit_new，才视为已明确越过的阻断项；旧记录仍保留。按预约先后及精确authorization记录推导，不加伪造终态/兼容字段。命令须钉住所见旧action，不能自动把刚出现的新pending又“放弃”一次。
6. 用整个shot文档头version+1创建新pending，`store.add`而非put。事务oncomplete后返回预约版本；这是唯一外发准入线性化点。事务失败HTTP计数必须为0，不把本地Set当证明。其他标签页新动作在后一个事务读到前一个pending后必被阻断。

错误沿用 `REVISION_CONFLICT/NOT_FOUND/SCHEMA_INVALID/QUOTA_EXCEEDED/TRANSACTION_ABORTED`；duplicate add按场景处理为消费冲突。details仅稳定reason及非秘密版本/身份；不得以UNKNOWN/PASS伪造本地事务错误。

预约和HTTP不可能构成跨系统原子事务。本地保证“每个预约只允许一个执行者进入外发”，**不承诺供应商exactly-once**。预约后崩溃或HTTP后未落响应都保留不确定状态；有task按原身份核对，无task只能明确另发并提示重复扣费。绝不自动重发。

**实施时的目标DTO（只扩现有业务类型/Repository Interface，不新增持久化schema）**

```ts
type DocumentRef = Readonly<{ kind: DomainDocumentKind; documentId: string; version: number }>;
type ActionObservationRef = Readonly<{ actionId: string; version: number }>;
type ConsumptionFence = Readonly<{
  sources: readonly DocumentRef[]; // 对该动作有影响的来源；事务内读头并重算原领域投影
  projectionJson: string;         // canonicalJson，不含展示词条/secret/全部project revision
  assetSha256: readonly string[];
}>;
type ReserveAttemptInput = Readonly<{
  projectId: string; shotId: string; confirmation: DocumentRef;
  seenAction: ActionObservationRef | null; // null仅表示无动作；所有expectedVersion仍为整数0
  prompt: DocumentRef; pending: AttemptRecord; fence: ConsumptionFence;
}>;
type AppendAttemptObservationInput = Readonly<{
  projectId: string; shotId: string; base: ActionObservationRef;
  via: AttemptVia; envelope: unknown; // runtime classifier校验，不用强制cast为合法记录
}>;
type CommitSelectionInput = Readonly<{
  projectId: string; shotId: string; seenSelectionVersion: number;
  decision: SelectionRecord; fence: ConsumptionFence;
  candidate: DocumentRef | null; attempt: ActionObservationRef | null;
  report: DocumentRef | null; // 三项仅clear时为空；select必须给精确合法记录
}>;
type ProjectSnapshot = Readonly<{
  project: StoredProjectRecord; documents: readonly StoredDocumentRecord[];
  assets: readonly StoredAssetRecord[]; // Blob句柄，事务外才arrayBuffer
}>;
type CommitDeliveryInput = Readonly<{
  projectId: string; exportDocumentId: string; payload: ExportRecordPayload;
  selections: readonly DocumentRef[]; reports: readonly DocumentRef[];
  acknowledgements: readonly DocumentRef[]; suiteReport: DocumentRef;
  candidates: readonly DocumentRef[]; attempts: readonly ActionObservationRef[];
  originalPrompts: readonly DocumentRef[]; fence: ConsumptionFence;
}>;
```

复用domain/validate已有type，不建通用DTO包；Declaration放实际所属owner或既有type contracts。`DocumentRef`中的kind须按命令进一步收窄；事务入口拒绝非法版本、缺引用及payload不匹配。mode从精确confirmation派生，不是第二个自由参数。Repository从这些DTO执行相应业务事务；不公开tx/store给workspace串步骤。

| 确定性交错 | 必须观察的后置 |
|---|---|
| 同授权同shot，两tab同时预占 | 一次预约准入，败方HTTP为0；单页Set不能作为证据 |
| 同摘要不同确认版本，两tab同时提交 | 仍共享action/业务阻断；即使两个确认都合法，也不能同时外发 |
| failed_retry竞争；explicit_new同时指向旧pending | 一方预约后另一方看见新action冲突，不自动再“放弃”新action |
| 旧A响应在B预约后到达 | A合法观察及候选保全；B仍是当前预约、在途阻断不被A掩盖 |
| 两tab首次采用；clear与select并发 | expected0/所见版本只允许一方，败方不改选、不把clear判缺report |
| 导出构包时采用/规格/report/ack变化 | 交付commit拒混合来源；完整项目快照ZIP仍可按原线性化时刻完成 |
| 预约后未POST；POST后未存响应 | 不宣称未调用或自动重发；按task身份/无身份Unknown规则恢复 |

### 10.4 旧结果保全与防倒退：按action推进，按预约顺序投影

目标 `appendAttemptObservation` 与候选保存仍使用现有append-only文档格式。输入钉住projectId、shotId、actionId和见到的该action观察version；外部信封先用现有classifier校验，事务读取该action最新观察，再用 `advanceAttempt/canAttemptTransition` 派生。

- 同action观察发生并发：若已记录完全同一合法结果，返回已存在版本；若观察头改变，基于新头判断该信封是否仍可合法推进。终态不因旧running响应退回active；冲突后不重发HTTP。
- **不同action不互相覆盖，也不因为新动作存在而丢弃旧成功结果**。旧action合法响应可在shot全局文档头+1追加，原asset/candidate按原项目/action保全；当前动作和阻断投影仍按§10.3分组/预约序号得出。
- candidate按candidate_id/action_id做幂等查重并校验 `candidateMatchesAttempt`；不能因另一candidate更新了shot头就丢弃旧动作成功。保存candidate与采用完全不同，不自动改选。
- candidate资产和文档保全成功、确定性report尚失败时仍保留候选；显示缺报告及阻断原因，允许纯本地补建，不撤销图片或重提生图。同步协议结果只有内存字节且尚未落资产时，刷新可能丢字节；如无可核对身份据实保留缺口，不能捏造恢复URL或重新POST。
- 旧实例late finally只清自己的flight标识，不清新实例或另一动作的flight；旧回调允许保全原数据，但不更新新项目DOM、阶段、报告Map、ObjectURL或新key状态。

必须反例：A已unknown、用户明确预约B，之后A成功；A候选保存且B仍为当前动作。B仍active时不能借A的晚到succeeded启动C。不能采用“只看文档最大version”或“旧action全拒绝”的简化。

