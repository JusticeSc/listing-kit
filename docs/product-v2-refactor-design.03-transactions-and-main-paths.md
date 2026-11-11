<!-- 拆分件 03/29 · 父文档 docs/product-v2-refactor-design.md -->
# 事务、授权消费与六条主链
[返回设计目录](product-v2-refactor-design.md) · [上一主题](product-v2-refactor-design.02-business-interfaces.md) · [下一主题](product-v2-refactor-design.04-redundancy-and-test-stability.md)

## 4. 事务、授权消费与副作用

### 4.1 存储Seam需要的窄能力

当前 `repository.documents.save` 仅单文档可选expectedVersion，不能原子证明“授权未被消费且相关头仍当前”。目标是在现有 `storage/repository.js`/类型定义内扩展以下具体能力，沿用现有schema/index；不建立通用commit/event/outbox平台：

| 能力（目标名称） | 单次IDB事务保证 | 事务外工作 |
|---|---|---|
| `reserveGenerationAttempt` | 确切授权/Prompt及实际消费的来源版本符合；本授权版本+Shot未被任一已登记attempt消费；append一条pending_submit并返回确切记录 | hash、读Blob、目标能力/凭据核对、HTTP |
| `commitSelection` | 看到的采用头仍同版本（无头=0）；引用候选/报告仍存在且版本匹配；append人工选择 | 字节hash、确定性报告计算 |
| `commitDeliveryRecord` | 选中候选、采用、相关事实/规格/确定性报告头仍与检查快照匹配；append对应export_record | 读图、hash、整套测量、ZIP构造 |
| `readProjectSnapshot` | project、documents、assets取自同一readonly事务，导出包不会混读不同批次 | Blob.arrayBuffer、hash、ZIP |

检查具体被消费的记录/版本，不用全项目revision粗暴使无关图stale。已有历史引用用确切版本读取；当前依据用当前头。授权消费查该Shot完整attempt引用链，而非仅最新一行/任意旧成功记录；查询局限该项目、该文档链，不为此拉全库或引入新索引。确有测量证明现有索引不足才按原选型/存储任务复访。

事务不能await网络、加密hash、Blob异步字节转换、人工或计时器；这些先完成，再开短事务，事务内只做IDB请求、校验和append。当前通用save仍可供已经明确的追加观察使用；用户编辑/决策和外发登记不得默认跳过冲突控制。

### 4.2 确认到提交的线性化点

1. generation取得所见摘要、固定项目/会话及执行目标；局部同文档/范围飞行锁防同页双击，不用一个全局锁阻塞查看或采用。
2. 读取实际Prompt/依据和参考图字节，计算hash，检查所见摘要、授权模式、能力、原目标凭据来源及目标Shot现存阻塞。秘密头只在内部命令内存，不能进摘要/记录。
3. 以OCC保存所见确认记录，随后逐Shot用 `reserveGenerationAttempt` **原子登记消费**。确认与消费并非一件事；确认后崩溃但未登记的Shot可恢复为待消费，已登记Shot不可自动再发。跨标签竞态由IDB事务判决，而非两个标签各自的Set。
4. 只有登记成功且命令仍获准新增外发才按登记记录发送固定请求；登记冲突/配额失败时上游计数必须为0。提交前不把“当前最新Prompt/当前模型”塞进已确认请求。
5. 登记成功是该Shot接受动作的本地线性化点；之后其他编辑不追溯改写已接受请求，但使其与当前任务的关系显示过期。换会话/停止新增发生在外发前时不再发；已有pending记录保留真实未观测状态，不自动再消费。已开始HTTP后，结果无论视图是否仍开都归原项目保存。
6. 同步协议一次submit返回字节，task_id可为空；异步协议按原task/原目标核对取回。结果保存失败不能制造“上游未执行”；保留pending/Unknown与恢复信息。保存结果和候选时同原action关联；字节hash与元数据不一致拒绝候选采用。

**本地至多一次授权消费，不宣称远程exactly-once。**登记后进程崩溃或HTTP超时仍可能未知；无task或字节丢失不能自动重提，显式新动作保留重复扣费警告。供应商action_id不是未经核实的幂等承诺。

### 4.3 采用、报告与交付的线性化点

- 单图报告由adoption内部计算/读取，并绑定实际候选字节、原动作和被消费的事实/规格；AI只由明确reviewCandidate触发。候选/Prompt/history只读来源从generation/prompts取得，不回调工作台。
- adopt先确认候选合法、字节/hash及当前确定性报告，最后在 `commitSelection` 核对用户看到的选择头。冲突保持原选择，定位刷新；不能自动改选到刚生成的新图，也不能清空旧采用来消除stale。
- 返工只生成目标Shot的新候选，不写Selection。合法旧候选仍可采用；两个标签同时首次采用，必须一方冲突而非两次静默成功。
- 当前确定性单图/整套报告仍必需。整套与单图AI可为not_run、当前、过期、失败/未知；not_run准确显示未复核，不伪造成模型Unknown或PASS。真实执行Unknown与实际复核风险知悉仍按原业务合同保留。
- exportDelivery内部取得已采用候选和报告的一致快照，验证整套门/字节/原action→Prompt历史，组清单和ZIP，再用 `commitDeliveryRecord` 核对相关头。中途相关编辑/改选使提交失败；保留数据与诊断，不交付混合包。成功后该记录和ZIP属于那个确定快照，后来编辑不改写它。
- exportProject是同版本完整恢复包，不要求商品交付门通过；它必须用 `readProjectSnapshot` 含全部应保存历史/资产。两类ZIP不能混用。不因某个独立save是原子就声称整包读是一致事务快照。

## 5. 六条主链与失败恢复

| 用户路径 | 完整命令归属与行为 | 必须保留的失败/中断后置 |
|---|---|---|
| 人工输入/确认 | inputs保存未确认资料；人按槽位保存并确认；不先买AI，复用同一FactSlot动作 | 来源/越权/版本冲突可定位，未确认不是事实；不按整套缺项锁无关图 |
| 进入生成→一次明确提交 | generation本地准备并显示摘要；随后所见摘要confirmAndRun；单张/批量共用消费/执行 | 变更摘要拒发；partial保留各Shot状态；停止只停止后续新增 |
| 单图返工→比较 | generation准备目标返工摘要并按同一执行路径发送；view保持参考图/旧新候选上下文 | Selection不变、其他Shot记录/hash/选择不变，异步不抢焦点 |
| 采用旧或新图 | adoption一个命令包住验证、确定性报告与OCC保存；对比view不写Selection | hash错误/报告过期/冲突不覆盖原选择；未做AI可人工采用 |
| 确定性检查→交付/完整项目包 | delivery内部检查和构包；AI只在独立明确review命令外发 | not_run如实清单；BLOCK/未知悉风险拒交付；完整项目包仍可救数据 |
| 刷新/切项目/原任务恢复 | session新运行体，恢复固定版本/身份；generation只核对已知原任务；原目标缺key引导补原凭据 | 不用新模型/新action查旧任务，不自动提交；旧结果仍写原项目，当前UI不被污染 |

高级Prompt、风险知悉、重试和原任务核对保持业务权限不变；内部版本/ID/hash只在诊断渐进披露。本文不重设计布局、不把UI draft转current；视口/缩放/键盘、正式页面实际读图仍按计划/UI合同验收。

