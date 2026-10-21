# Product V2 联合结构重构详细设计

> CONTROL-STATUS: current · AUTHORITY: refactor-implementation-design
> 本文是**目标设计，不是工程完成声明**。当前实现规格取§13；目标、正式依赖/准出与最新用户修订取`product-v2-refactor-plan.md`§2.1/§17.13；技术选型和数据归属取项目上下文，权限及前沿只取state。§10–11按未变前提复用旧算法/差量证据，不再作为新会话默认施工清单；§12只指向当前恢复入口。
> §13来自2026-10-12独立设计及2026-10-13正式启动承接；这些历史不解除当前停工，也不证明已经实现。独立设计/原型记录在`_working/amz-listing-kit-next-version-design/discussion.md`，产品原生Goal观察全文唯一在计划§2.1。

## 1. 设计依据与决策

### 1.1 问题不是文件太大，而是规则和时序泄漏

2026-10-06设计基线：`app/product_v2/workspace.js`当时7516行，资料/事实/方案、Prompt、授权、执行、比较/采用、复核/交付及DOM交织；实际新建落IndexedDB而打开失败 `suiteReports is not defined`。四个新TS未进入完整emit/消费者集合，`generation.ts`与JS也不一致，来源 `evals/product-v2/refactor/detailed-refactor-design-20261006.md`。这些是**历史问题与设计起因**，不是当前恢复点。

2026-10-07审计已观察15个TS源类型/字节一致、业务owner/四视图存在，新建→保存草稿→刷新恢复成立，见 `evals/product-v2/refactor/audit-current-state-20261007.md`及checks；不再重做原子组A。仍有generation→adoption的确定性报告反向调用、工作台补报告、UI摘要编排与渲染callback等具体残余，按§11.5清除。源码可运行不等于完整任务、间歇根治、CI或发布已验收。

### 1.2 比较三种Interface后选定的方案

| 备选 | Depth / Locality / Seam | 不采用原样的原因 |
|---|---|---|
| 一个 `dispatch(intent)` + 一个 `view()` | 页面很窄，所有动作聚到一个入口 | 命令交换机、状态和错误策略容易再次集中；靠分支行数/固定命令数限制不能解决业务所有权 |
| 每个所有者独立收命令，工作台传快照 | 状态归属明确，易单独改变 | 如果工作台仍串编译→授权→执行→报告→采用，就把复杂度移到调用方；冻住旧输入也不证明输入仍当前 |
| 再加无状态 `SuiteCommands` | 默认用户动作好调用 | 薄转发、统一锁/错误和read passthrough会成为新中间层；自动在导出发AI、冻结后不查实际版本均违反已有合同 |

**选定：显式业务所有者 + 在自然业务Module内收口完整动作；不增加总命令facade。**

- 资料/事实/方案状态归 `project-inputs.ts`（现已存在）；复用现有semantic提议、domain和repository，仅完成未闭合消费者，不再新建第二份输入owner。
- `prompts.ts`拥有Prompt编译、人工编辑/重新确认及版本；不拥有在途任务。
- `generation.ts`合并独立 `authorization.ts` 的授权队列/模式/范围/消费，拥有“显示摘要→明确提交→登记→执行→观察/候选”的完整动作。迁完删除独立授权TS/旧JS和全部旧调用，无兼容别名。
- `selection-adoption.ts`拥有单图确定性/可选AI报告、人工采用及风险知悉。单图报告从generation迁至这里，generation不再回调下游review请求构造。
- `review-delivery.ts`拥有整套确定性/可选AI、交付门、交付记录和ZIP构造；不由工作台组manifest。
- `workspace`保留装配和表现生命周期；页面职责按输入、生成、比较、交付四个视图切开。不把长文件机械均分成无所有者的helper。

删除一个目标Module时，若规则、事务和恢复时序会重新散落到多个调用方，它值得保留；若只是少了一次转发，删除。新文件不是收益证明。

## 2. 所有权、依赖与生命周期

### 2.1 目标状态所有权

| Module / 拟落点 | 唯一拥有的可变状态 | 对外可见 | 不得拥有 |
|---|---|---|---|
| session.ts | boot阶段、项目指针、会话generation、当前运行体 | 项目打开/关闭与ActionSnapshot | Prompt/候选/采用/交付状态 |
| project-inputs.ts | 资料草稿、事实槽位、提议归属、方案/风格/单图规格/参考图的已提交版本 | 业务编辑动作、来源与依赖投影 | 已确认事实的第二套模型、key、DOM |
| prompts.ts | 每Shot Prompt历史/当前版本、人工编辑状态、准备中状态 | 编译/编辑动作、只读记录和消费Basis | 执行授权队列、attempt、Selection |
| generation.ts | 确认队列/范围/模式、授权消费、attempt/candidate链、批状态、观察及执行中的局部状态 | 摘要/提交/停止新增/核对/取回、进度投影 | 采用选择、AI自动复核、DOM |
| selection-adoption.ts | 单图报告、采用版本、风险知悉、采用中状态 | 查看报告、显式AI复核、采用/清除、只读选择投影 | 重新提交、整套ZIP、工作台draft |
| review-delivery.ts | 整套报告、交付门、交付记录、检查/导出中状态 | 明确AI整套复核、确定性检查、两类导出和门投影 | 自动采用、改变原任务模型 |
| model-settings.ts | 有限用途选择、能力与key的当前标签页内存 | 非secret配置/可用性、内部凭据Adapter | key持久化、view/错误/包内secret |
| 四个视图（现有 `ui/input-view.ts` 等） | 输入框未提交文本、展开/对比布局/焦点/ObjectURL | 用户事件、DOM更新 | repository写入、版本Map、业务规则、网络提交 |

内存是对应已提交记录的缓存/只读投影，不是另一份权威。草稿明确不是confirmed；来源证据不等于actor权限；模型提议不能直接写人确认状态。查看/对照状态归视图，人工采用状态归业务Module。

### 2.2 依赖是有向图，不用callback绕回工作台

```text
app / session
  └─ workspace（每次打开创建项目运行体，装配而不执行领域决策）
       ├─ project-inputs ── repository / semantic-analysis / settings
       ├─ prompts ── project-inputs（只读已提交投影） / repository / settings能力
       ├─ generation ── prompts / project-inputs / repository / settings凭据 / 图片HTTP
       ├─ selection-adoption ── generation（只读候选/动作） / inputs / prompts / repository / 复核HTTP
       ├─ review-delivery ── selection-adoption / generation / inputs / repository / ZIP / 整套复核HTTP
       └─ 四个视图 ── 对应业务命令和只读投影
各业务Module → 现有domain纯规则；domain不反向import运行体、UI或HTTP。
```

只注入上述具体窄Interface，不传workspace闭包、可变context、裸Map或“任意函数集合”。generation不依赖selection/delivery；报告需要attempt身份时由下游读取generation的只读投影。不存在 `confirmationSaved → authorization.remember` 回边；确认保存和队列缓存更新均在generation内部。

当前源码已实现这条单向装配链：generation不再持有review setter，adoption订阅候选并在restore中补报告；workspace仅装配和调用owner恢复。旧迁移步骤不再作为待办重复执行。源码归属成立不替代实际报告失败、恢复与原准出门的证据。

依赖分类：domain/内存计算为in-process；IndexedDB/ZIP为local-substitutable但事务/Blob仍需实际Chromium证明；Python网关为remote-owned；上游模型为remote-third-party，只在已存在协议/凭据/HTTP Seam替换Adapter。不给每个业务读操作发明port或mock；两个实际图片协议继续通过同一生成Interface消费，不在UI写供应商分支。

### 2.3 生命周期和异步结果

1. session先冻结 `{projectId, generation}`，工作台创建**新的**项目运行体；不要复用旧Map并reset为新项目。恢复只通过内部restore能力读校验后的记录；UI不获 `loadChain/setReport/remember` 写口。
2. 恢复按依赖次序读最新头，候选历史按需读；确认、attempt和采用引用的旧Prompt/报告必须按确切版本可取回。不为首屏一次读全库、全Blob或全历史。
3. 每个owner只向一个只读视图通知出口发“投影已变”；合并同一轮渲染，保留批执行中进度。通知不带秘密、不让UI调用业务变更；渲染函数不能编译、保存、复核或提交。不引入事件总线、全局store、消息日志或轮询整份项目。
4. 关闭/换项目先阻止旧运行体接受新命令并停后续新增提交/观察计时器；视图解除监听、释放ObjectURL。已经外发的命令保留原项目、原身份和固定输入，结果/Unknown/候选必须在原项目保存；`alive()`只控制旧视图更新，不丢已经发生的结果。
5. repository连接在仍需保存结果的命令结束前不关闭；实现局部资源持有/释放，不做通用任务调度平台。旧运行体的finally只释放自己的锁，不能清新运行体状态。真实关标签可能失去未保存结果，恢复如实Unknown；不承诺浏览器退出后继续执行或自动重提。
6. 恢复失败保留数据、项目ID和可定位错误；不能把失败ready化、清库或自动建空项目。切项目后旧结果不夺焦点、弹旧项目成功或下载旧项目文件；重新打开原项目可查看保存结果/导出记录。

## 3. 业务Interface：页面只表达意图

以下为**目标Interface合同**，非已存在源码。签名中的FactSlot、PromptRecord、CandidateRecord等复用现有domain类型；不新增统一“大合同文件”。摘要与版本引用在所属Module定义，其他Module按只读类型import。

### 3.1 命令与读模型

| Module | 页面可调用的业务命令 | 页面/下游只读投影 | Implementation隐藏什么 |
|---|---|---|---|
| inputs | 保存资料；保存并确认某事实；接纳提议为待审事实；确认/撤销；保存方案/风格/单图规格/参考图 | ProjectSources、每Shot依赖/缺项、提议原来源与是否过期 | applySlotAction、来源/权限校验、OCC、保存顺序、精确版本 |
| prompts | 本地准备范围；编辑人工文本；明确重新确认人工文本；撤销人工覆盖 | PromptEntry/history、Basis/currentness、实际请求文本/hash | 确定性编译、人工保护、无变化不重复版本、历史版本读取 |
| generation | `prepareSummary`；`confirmAndRun`；`stopNewSubmissions`；原任务`reconcile/fetchResult`；显式新动作摘要 | 显示摘要及其引用、队列/进度、候选/attempt历史 | 授权记录与消费、完整前置、固定身份、登记后外发、同步/异步归一、配额处理 |
| adoption | `adopt/clear`；`reviewCandidate`（明确AI）；确认具体风险知悉 | 对比需要的候选/报告/采用/currentness | 字节/hash与来源验证、确定性报告、SelectionRecord保存、OCC |
| delivery | 当前确定性整套检查；`reviewSuite`（明确AI）；`exportDelivery/exportProject` | 门、报告、原导出记录/问题定位 | 稳定快照、整套当前性、Unknown知悉、原动作manifest、ZIP及导出记录 |

命令输入包含**用户看见的版本/摘要引用**，而不是owner悄悄替换成最新值；命令开始还必须读回相应权威头核对。返回沿用既有业务结果/错误族并提供定位信息；业务拒绝、版本冲突、存储/配额失败和外部Unknown不可折叠成一个布尔值。只有外部结果不确定才用Unknown，不能把未运行AI、缺字段或普通版本冲突称为Unknown。

- 修改/选择：expectedVersion为用户看到的版本，首次写入为0；禁止以`null`代替0关闭OCC。
- 恢复/观察：内部按原action/task引用追加，不能重放陈旧整份记录覆盖新阶段。重复同一观察不新增业务变化，晚到旧阶段不使已成功记录倒退。
- 结果附项目/运行体归属用于表现端丢弃旧视图更新；业务owner已完成必要保存。表现端仅处理结果显示/下载，不再调用下一业务步骤。
- 投影数组/对象按实际类型readonly，不能返回可写Map。已提交时建立稳定不可变视图，普通render复用；不每次render深克隆全项目/Blob。

代表性调用（目标形式）：

```ts
// shownSummary由generation.prepareSummary的投影取得；不是“当前最新版”别名。
const result = await runtime.generation.confirmAndRun({ shownSummary });
// 同一owner完成确认、登记、执行和结果保存。这里只呈现result。

const adopted = await runtime.adoption.adopt({
  shotId, candidateId, seenSelectionVersion, seenCandidateVersion,
});
// 不在页面先检查→另存报告→组SelectionRecord→再保存。
```

### 3.2 不能靠冻结输入冒充当前性

- Snapshot证明“这次动作使用了什么”；当前性证明“这些来源/授权在决定时仍可用”。两者必须分别成立。
- `prepareSummary`自动补缺失/过期的**系统**Prompt，并构造实际发送摘要；人工Prompt过期只给明确恢复入口，不覆盖。准备不是外发授权；如果准备改变可见内容，先显示新摘要，不能在一次点击里自动发送用户未看到的新内容。
- `confirmAndRun({shownSummary})`只消费所见的范围、模式、Prompt/参考图/hash、参数及有效目标。异步hash/读Blob后重新核对实际依据；若变了，返回对应问题并保留旧摘要，无外发，页面显示新摘要后由人再明确提交。
- 可操作投影和执行检查调用同一domain判据；Interface返回blockers/定位而不是UI另造布尔门。公开方法仍独立校验，不能因为按钮disable就省掉执行前置。
- 生图设置只有实际参与请求/能力/编译的变化使相应下游stale；换复核配置不把已生图改为错误模型。单图缺项不误锁无关用途。

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

## 6. 重复与冗余：分类后合并/删除，不只拆文件

| 现有问题/位置 | 具体治理 | 不能用什么冒充完成 |
|---|---|---|
| workspace旧suiteReports/selections/确认等直读、旧reset与链式执行 | 逐状态建立唯一owner；所有读改投影，所有写改业务命令；owner恢复/销毁替代工作台reset；同切片删旧声明/回调/旧helper | 分文件仍共享可变context；只修未定义变量 |
| authorization独立状态 + generation确认保存/消费 | 合并到generation，删除 `authorization.ts/.js` 及相关类型/构建/测试旧引用 | 新文件pass-through/re-export/旧路径兼容alias |
| generation单图reviewRequestBuilder/review报告与下游复核交织 | 单图报告归adoption；generation只提供候选与原动作投影；移除review请求callback回边 | 两份review Map同步更新 |
| SelectionRecord被当candidateId使用 | adoption明确提供 `candidateIds` 与 `records` 的不同只读类型；suite/manifest消费正确值 | 在每个调用方加 `any`/猜对象字段 |
| shared helper与整份verify脚本互相import | `tools/v2_verify_shared.py`仅公共宿主夹具/稳定UI前置；领域用原生Node，浏览器用公共helpers，工具不借另一完整验收脚本的全局状态 | 同一seed正文复制多处；万能测试工具包 |
| 小而真重复的SEED_SLOTS/资料输入/upload等待 | 共享确实相同的业务前置与fixture；验证不同后置，不复制相同成功行 | 因字段名相似合并不同语义；扩大固定夹具掩盖用途缺项 |
| evals/product-v2/node/_gen.mjs以HEAD裁源码/词替换 | 在现有生成入口移除旧源码裁剪/HEAD依赖；行为夹具直接import稳定domain Interface；若不再有实际生成用途则删除生成工具并迁所有调用 | 从历史源码拼“测试专用运行时”；保留字符串补丁来稳定测试 |
| 手写JS与TS、生成名单与类型名单不一致 | 一个TS为唯一手写Implementation，浏览器JS由该源生成并纳入新鲜度；源集/实际emit结果对齐，生成校验覆盖被依赖带入的迁移TS | compiler program读到即算构建覆盖；mtime/语法绿灯 |
| 参数/协议/能力/错误分支跨Python和页面重复 | 仅真实相同的传输/有效配置规则集中，业务schema继续独立；复用现有registry/credentials/outbound/domain判据 | 通用schema生成器、把商品理解和候选复核当同一请求 |
| 过大函数/大量薄wrapper | 按变化原因、决策及数据所有权拆/合并；调用方只传意图；无决策/无状态/无独立消费者的转发删除 | 固定行数分割、限制函数数量、新Module数或测试数 |

每个施工包在本来要改的依赖闭包内主动检查上述模式，并在该包完成说明记录“删/合/保留及理由”。不等用户点名；不借结构治理扩张到无关业务、未授权V1删除或新框架。

## 7. 测试稳定化与类型/交付一致

### 7.1 断言分类与迁移

| 分类 | 处置/既有落点 | 真实判据 |
|---|---|---|
| 文案/函数名/源码位置/数组数量/纯转发回声 | 删除，不重钉；如selection-contract的措辞/枚举形状行、intake验证器读workflow文字猜tar/容器合同 | 保留它原本想证明的用户行为；没有行为内容就不补新永久测试 |
| 纯规则/边界/状态转换 | 复用 `evals/product-v2/node/` 原生domain入口 | confirmed权限、实际依赖stale范围、人工Prompt不覆写、not_run与Unknown分开 |
| 存储/OCC/恢复/ZIP | 复用现有Chromium宿主验证 | 跨标签首写冲突、授权消费事务、实际IDB历史/Blob/hash、一致快照/包往返 |
| 外部协议/身份/安全 | 复用现有网关/Adapter捕获 | 实际request/action/原target/头来源，未知无自动submit，服务不写业务数据 |
| UI/交付/人因 | 实际正式入口任务，复用稳定helpers | 同动作DOM+网络+IDB+ZIP和真实截图；播种不代替空白人工主链 |
| 控制守卫 | 既有受测root反向探针 | 隔离副本变红，真实state不被临时改写；报告并写不误判产品业务落盘 |

类型保障只针对实际登记/emit的Module及消费者；strict/include关闭范围如实说明，不将“新TS存在/语法合法/读到依赖”写为迁移完成。构建入口以**实际emit文件集合**防漏列，不仅从少数root fileNames推测；不能生成了未纳管的依赖JS却继续让浏览器运行旧手写JS。改变源集同时更新jsconfig、构建/新鲜度规则、浏览器import、Docker排除及实际运行闭包；不新增第二编译/打包平台。

### 7.2 消费者可见反例（复用优先）

- 两标签同一所见摘要竞争：同授权版本+Shot只有一个pending登记/上游submit；另一方明确被消费/冲突。单标签双击和刷新后再点击也按同一消费证据。
- 摘要hash或实际消费头在异步字节读取期间变化：外发计数0；无关Shot变更不误阻塞。不能只把旧Snapshot再比较一次。
- 先登记存储失败/配额不足：外发计数0；外发成功后结果保存失败：不宣称未外发，恢复保留Unknown/原身份。
- 开A发起执行→切B→A返回：A的原action/候选保存，B的选择/状态/焦点不变；旧finally不清B锁。
- 首次人工采用seenVersion=0竞争、改选与导出重叠：冲突不覆盖，导出要么来自一份完整快照要么拒绝，无混合manifest/字节。
- 成功生成/打开比较/人工采用/导出且未点AI：复核外呼0，真实确定性报告仍存在；清单not_run，不伪造PASS。
- Unknown/task原目标与切模型并存：仅原target status/result，submit为0；同步即时返回只消费一次submit、无伪task。
- 完整项目包导出时另标签编辑：项目/文档/资产来自同一事务；导入后记录与字节一致，不只ZIP非空。
- 同版本生成的JS搬Implementation/改名：行为继续成立；源码钉删除后，恶意重复submit/OCC省略/错误字节仍被既有行为判据抓住，而不是降低成“未抛错”。

确认即提交的宿主证据必须关联**本次授权document/version+Shot+action**和实际请求增量；不能拿库里任意旧attempt行或总行数增长通过。共享前置需要既有正式UI helper适配新动作，不保留每Slot都确认的历史必经顺序。

### 7.3 执行成本

施工期按计划§15.3：同一连贯包编辑期间不反复build/全测；包结束一次类型/生成一致性、相关既有行为判据及一条实际改变路径。接线与模块移动用实际smoke，不新增结构/复制/wiring测试。最终R7.1的两轮在整合完成后执行，不能省也不提前变成日常工作。

失败保留首次证据，定位机制后修复并重验受影响行为；基础设施失败与产品错误分开，不用重跑洗绿。真实上游只在协议/品质确需证据且额度/授权成立时调用；本次设计轮不调用，也不为重构重复付费链。

## 8. 历史材料、源码删除与交付闭包

| 类别 | 处理 | 删除/归档准入 |
|---|---|---|
| 当前源码/当前目标/当前状态/未完成问题 | 日常有效，保持精确路由 | 不能因篇幅大归档或用旧报告替当前未证项 |
| 已完成cutover的旧Implementation/注释/alias/重导出 | 全部调用方/构建/测试迁完后同包删除 | 事前原字节可恢复；删除属于获批重构，非保留两套“兼容” |
| superseded设计/旧Goal/旧state/旧合同 | 有引用的历史最小集退出日常阅读，保留来源/原证明范围 | 不能把历史done/active升级成当前事实；不得移动仍被权威引用的路径使守卫/恢复断裂 |
| 未采用的重复过程报告/截图/log/临时脚本 | 分类清理；精确字节归档到已有 `_archives/` 外部材料区，核对hash和引用后再移出日常工作树 | 不是“全部归档”；有后续决策/缺陷价值者留选中集合；用户/未知原件未经许可不删 |
| 失败/Unknown/费用/素材许可/选中验收证据 | 最小永久证据，保留首次失败和真实来源；失败后绿灯不替首次记录 | 仍在追因或账本/验收被引用者不丢；hash+临时路径不等于可恢复基线 |
| TS生成JS/当前vendor/真实产品依赖 | 进入正常构建/提交/镜像规则 | 生成JS不是过时垃圾；不得因“自动生成”从生产闭包排除 |
| V1与offline-fixture | 识别实际生产/验证消费者，按计划R7.3覆盖、切换后同包清退；保留仍有独立用途的共享资产 | 不以历史兼容或未发生的C15/C17永久保留旧产品；先备代码/当前数据再删活路径。当前停工不授权执行删除，旧原件/证据归档与运行兼容是两件事 |
| 用户项目、素材、两类ZIP和未提交原件 | 完整保留；由已有明确权限控制 | 不能用清库、Git恢复/clean、整目录rm来治理历史 |

历史工具 `_control-tools/curate_amz_evidence_20261001.py` 的旧权威列表不得直接当当前清理依据；取实时INDEX/state/账本/计划选中证据和未解决缺陷的引用闭包。先算类别/引用/实际hash/稳定归档可恢复性，输出精确移动清单；只对有权限的过程材料执行。不能用全部Git未跟踪项或gitignore结果推断垃圾。

生产闭包按实际import及运行资源，不按文件看上去“旧”判断：默认V2入口、V2服务/已批准providers/config、实际生成JS/静态资源/ZIP库/必要许可证及锁定Python依赖进入镜像；编译器/TS源、evals、_working、历史报告/开发fake不进入生产。配置与静态资源必须在正式容器/HTTPS实测，文字检查Dockerfile/tar清单不足以证明闭包。

本轮设计不移动/删除历史原件或产品源码；上述为恢复施工后同包治理合同。

## 9. 施工包、回退与准出

下表仅细化原任务与§15批次，**不是新增任务ID、依赖表或当前进度**。恢复前先按state解决用户停工门及当前Goal观察；设计交付不能自动放行。

| 原任务承接 | 同一施工包的改动闭包 | 可见完成点/最小证明 | 回退与准出 |
|---|---|---|---|
| R5.1 + R7.5；已有R3.3会话合同 | 补齐实际TS emit/JS一致；工作台四类视图与完整owner迁移；授权合并generation；单图报告迁adoption；inputs迁出；全部读写/restore/close/import同步删旧路径 | 正式新建、打开、刷新/关闭重开无 `suiteReports` 失败；原记录保留；一次提交/返工/采用/交付仍走完整命令。类型+产物一致及受影响宿主路径 | 不发布半迁树；在独立数据库先运行。若失败保留新增记录并按同版本原字节源码/包原子回退；不只改一个JS文件 |
| R5.1/R5.3 + R6.1–3的人工路径 | 授权登记与版本fence、所见摘要、人工Prompt/事实、采用/导出快照事务；现有所有消费者迁入窄能力；清除跨Module业务Map和序列 | 人工空白输入→本地准备→明确提交→比较/返工→采用→两类ZIP；跨标签/Unknown反例；原动作/字节/hash不变 | 存储冲突禁外发/混合交付；不改变现有schema/加跨版本读shim。既有可恢复包验证仍成立 |
| R3.2/R7.5及各受影响任务；最终R7.1 | 在前两包调用方切换中同步迁共享UI前置、删源码/词条/回声钉、移除整份验证器互引及HEAD裁剪；隔离反向root/业务落盘受测根 | implementation移动不假红，真实重复消费/OCC/字节/隔离反例仍判红；单次live消费者不会额外提交 | 不为了“先全绿”修复已废弃文字断言；不另建验证平台；未闭合消费者前禁live |
| R6.1/R6.2/R6.3，设置归原R4.3合同 | 有限设置贯通新图文/复核消费者；图文提议原来源与人工确认；确定性与显式AI分开；复制schema/供应商分支就地治理 | 完整辅助任务与未点AI路径；实际图字节/原source身份/选择/导出；必要品质与费用按既有门 | key/预算缺口只阻对应真实调用，不伪造能力/自动换模型；不因设计完整把该任务done |
| 各cutover包 + R7.3/R7.4；原R6.4成果复用 | 同包删旧源码/alias、分类必要历史；按计划工程条件清除V1活路径/消费者/失效配置/依赖，生产闭包同步 | 当前入口只依赖当前实现，独有用途处理、共享依赖保留、代码/同版本数据可恢复；真实CI/HTTPS与删后指纹 | 不盲删用户原件/失败/账本/许可；必须覆盖/切消费者/基线后删，不以未经验证V1作回退 |
| R7.1/R7.4 | V1切换后最终原两轮、人工/辅助实际任务、代码/JS/镜像/配置指纹、旧版本留到全部门后清理 | 真实不同old/new服务回退和同origin数据恢复，正式页面/静态资源/交付主链，不止health；适用RC完整直接证据 | Linux/TLS/两image由获批CI/环境实际运行；C17/C15独立真人单列未发生，模拟E2E不虚构签署 |

§9是联合交付闭包，不再把第一行当成一次交给低模型的巨型任务。具体施工按§11小包及原子联调组推进；每个已切换业务对象只有一个实现，未切对象仍由原实现负责，不能增加shim或双维护。依赖密集的联调组可分步编辑，但完整消费者/生成JS/恢复路径同步后才运行并签包；不发布、验收或遗留“新TS已写、浏览器仍跑旧JS”的中间树。事务/行为缺口按§10规格实施，不在机械所有权迁移中偷偷改变业务含义。测试消费者随所在包同步迁，README只在实际行为证明后更新。

### 9.1 六项结构准出（作为原联合完成判据的操作化）

1. **一次业务修改局部集中**：用途依赖、授权消费、人工采用、manifest追溯各自只有一个决策Implementation；无跨视图复制和共享可变context。需要改多个真实合同消费者可解释，不能将文件数当阈值。
2. **调用方无需理解时序**：每条主链按钮只传所见意图/版本；保存、授权、外发、报告和构包由对应owner负责。新层经删除测试，不保留pass-through伪Module。
3. **干净cutover**：全部旧读写/装配/reset/alias/旧测试入口删除；所有实际TS源码/JS/构建/浏览器/生产消费一致。不接受“多数TS完成”。
4. **行为判据稳定且能抓错**：没有重新钉词条/源码；原业务/事务/Unknown/秘密/字节反例仍能判红。共享前置一份，测试故障不污染真实state。
5. **历史治理有分类结果**：旧源码已清、保留证据准确、归档确切字节可恢复、当前选中引用无断裂；未授权用户数据/V1保持。不能以“全放archives”完成。
6. **原Goal的实际产品结果成立**：正式人工/辅助输入到交付、跨会话/原任务恢复、两类ZIP、全部用途配置/秘密、实际发布及回退证据仍完整；结构设计/类型绿灯/假模型成功不替代原RC。

若其中任一必要项未证，报告准确剩余缺口和恢复前沿，不宣称联合重构或Goal完成。本轮只完成设计和文档/恢复一致性检查，产品失败、两轮回归、真实CI/HTTPS/不同版本回退等仍按实时state承接。

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

### 10.5 生命周期：把关闭分成禁新动作、保存草稿、脱离视图

会话负责navigation generation；项目runtime负责自己owner/订阅/URL/timer。runtime目标局部状态 `open | closing | detached`，不落库、不另建业务状态机。一次切换只有一个在途transition；开始前同步占位并禁用导航/新业务命令。重复open/close返回稳定busy，不排万能异步命令队列。

1. A→B前先将A标closing，停止新增预约/轮询调度与新命令，捕获未保存草稿及其seen版本。已发HTTP不假称取消；旧实例仍可按冻结project/action保全响应。
2. 按原项目/OCC保存草稿；保存失败或冲突须传播到session，不像现有workspace.close捕获后继续清项目。取消本次切换，A仍可见并恢复接收动作，显示保存失败，B/pointer/generation不提交。
3. 保存成功后退订view/settings通知，清timer和撤销本实例URL；A变detached，推进会话generation。资源释放不清用户业务记录，不把保全callback依赖的原身份归零。
4. 打开B创建独立runtime，按inputs→prompts→generation→adoption→delivery读取并校验记录，完成后再接view及宣布open。恢复失败保留已保存项目/历史，传播失败，显示“项目已保存、工作区打开失败”，不能吞错显示ready。pointer只作最近项目轻量提示，不作业务权威或跨事务成功凭证。
5. 整个transition在finally释放导航占位；重名/改名不推进generation。boot失败释放自己新建的资源；不得通过清库/强刷新/重跑把失败变成无痕成功。
6. `ActionSnapshot.alive()`只证明当前显示身份；新业务还须runtime允许新命令。保全不受alive一票否决；采用、导出新提交在会话关闭后禁止，已构成的artifact不自动在B下载。

反例：closing期间连续点击A/B；草稿OCC冲突；旧分析/生图返回；B恢复report抛错；A改名；关闭后旧finally。新项目不被旧结果渲染/改选，旧原结果仍可恢复。复用原session生命周期合同，不引入AbortController“取消上游”幻觉。

### 10.6 报告、人工采用和两类ZIP：快照一致不等于实时当前

**报告所有权与AI状态**

- adoption创建/恢复确定性单图report；delivery创建/恢复确定性整套report。project open可补必要的本地确定性报告，但失败可见且门禁不通过；生成/打开比较/采用/导出都不自动发AI。
- AI只由明确单图/整套动作发起。未运行、运行失败Unknown、真实成功分开；沿用现有not_run及模型unknown合同，未运行不制造UNKNOWN finding，真实失败不伪装not_run。
- 报告头取决于当前引用/指纹，不取“最后完成callback”。AI请求捕获原source、候选/报告seen版本；目标 `commitReviewReport` 在现有repository中用同一documents写事务核对消费投影和seenReportVersion，才append并更新当前投影。旧输入结果或报告版本冲突返回stale/未登记，保留原报告与请求身份/失败事实，不自动重调用，不悄悄覆盖新报告。确定性重算保留仍匹配的既有AI块及真实失败，不能用本地重算抹掉Unknown/已知悉要求。
- ack钉住既有规则、对象和报告身份；新报告/新候选不继承一个泛化“我已确认”。不生成空报告/PASS绕门。原task恢复配置仍从原身份取，单图AI准备不反向依赖delivery。
- `reviewIsCurrent`现有单图合同只证明candidate/sha/审核合同匹配，不冒充当前事实/规格/整套门禁。后者仍由消费投影、当前suite report及交付围栏验证；不为扩展报告身份偷偷改schema/造来源字段。`commitReviewReport`沿用§10.3数值0/OCC/事务寿命规则，由adoption及delivery各自提供原领域输入，禁止UI自行写报告。

**目标 `commitSelection`**

事务外读取并hash候选字节、校验原attempt/候选/单图当前report，构造既有人工SelectionRecord。输入含完整decision（含取消采用）、seenSelectionVersion（首次0）、candidate/attempt/report精确ref及消费投影。事务内读取selection当前头与所见版本一致；保留原合法旧candidate，不强制候选shot头等于所选版本；精确candidate/attempt、report当前性及asset键再校验后append。取消采用只核对原selection头，不要求不存在的candidate/report。冲突不重定向到最新candidate，原采用保持。

**目标 `readProjectSnapshot`**

同一个readonly `withTransaction(["projects","documents","assets"])`读取项目、全量文档历史及资产记录；documents用现有 `by_project_kind` 项目前缀范围，assets用 `by_project_id`。返回Blob句柄和数值版本向量，字节/hash/压缩在事务完成后进行。完整项目ZIP就是该线性化时刻的历史快照；后续合法写入不使它“混合”，不追加“整个压缩期间禁止任何写”的二次围栏。

**目标 `commitDeliveryRecord`**

交付ZIP仅用同一快照的已人工采用候选、原attempt的Prompt版本/hash、当前单图/整套确定性报告、ack及资产字节。先构包/hash，提交前一次readwrite事务校验：selection头、所消费事实/用途/风格/规格投影、单图report/suite report/ack身份、精确candidate/attempt/原Prompt链及资产键。不能只围栏“selection+suite”而漏掉规格/report。无需钉住无关新candidate或当前编辑Prompt头。

任一相关头变动须在事务内按领域指纹/投影判断是否改变门禁所依赖结果；影响则冲突，不落export_record、不提供下载，保留原采用和诊断。完全相同exportRecordId/payload可返回原记录；相同ID不同payload拒绝。成功后再下载；后续修改不会倒写旧export记录。采用/交付事务持有asset store且再查键，完成后的Blob句柄供该快照使用；不能把一次存在性读称为跨事务永久租约。

当前 `assets.delete` 入口先查实际引用/消费者；引用资产不允许盲删。仅删除已解除引用素材或项目级cascade；无实际用户入口则不要为“垃圾回收”新增功能。import碰撞分配新projectId，不能覆盖旧库；不扩展跨版本降级读写或更改schema。

### 10.7 TS→浏览器→镜像：一个源码，完整产物，失败不半生成

`tools/build_product_v2_ts.mjs` 从compiler program取得**批准范围 `app/product_v2/**` 内全部实际TS源码**，排除 `.d.ts`、外部node_modules/vendor；不能仅用parsed.fileNames漏掉传递import，也不全仓迁TS。输出稳定排序、现有ESM/LF/header，同名JS唯一由TS生成。

先对全program做diagnostics；再在内存收齐全部transpile输出及诊断，全部通过后才写。`--check`只比较完整集合、不写。构建阶段失败不能前几个JS已写、后一个失败；filesystem中途故障仍不承诺多文件原子，应保留失败并用该批精确快照恢复整组。不得手补生成JS或跳过严格类型。

2026-10-06四份新TS/旧Interface不相容的风险已由组A处理；当前完整集合和消费者继续受本节约束，不重新发射旧authorization或重做该迁移。后续仅对真正改变的owner及全部调用/restore消费者同包切换；`jsconfig.json`、生成一致性、CI、正式HTML import与Docker白名单闭合。生产保留必要生成JS/vendor/license，排除compiler/TS源/evals/fake；真实服务字节与源码产物比对，不检查文字“看起来COPY了”。

### 10.8 发布/回退：保留既有事务平台，补真实不同版本证明

仅修改现有 `deploy/release-transaction.sh`、`tools/release_transaction_probe.py`、`.github/workflows/ci-cd.yml` 及实际受影响Docker白名单，不新建CD。以现有 `release-transaction/v1` journal为准：baseline（变更前落盘）→parked→new_started→new_healthy→TLS备份/安装意图/安装完成→tls_converged→https_ok；持久phase与镜像/容器身份核对，开放或不匹配事务禁止下一部署，不能猜测半停车状态。

- previous容器、旧可运行镜像与必要非秘密配置/TLS备份留到外部可信HTTPS、静态资源、隔离Chrome页面主链、源码/镜像/配置指纹都完成，且finalize再次验证之后。deploy不提前清旧版本。
- deploy/外部页面/指纹失败，或finalize可恢复验证失败（现有退出码1）进入rollback；finalize身份拒绝或已开始清理后的失败（现有退出码4）保留明确manual状态，不假称旧版完整保留，不盲删当前服务。恢复失败保留journal和准确失败，不报发布成功。
- fingerprint保留现有全部app/src/config、锁文件、能力公开配置的覆盖，再核对实际生成且服务的JS、镜像ID/tag、Caddy hash；**不能把范围缩成“TS输出∩静态目录”而丢Python/config**。default_trial必须closed，secret永不取hash/输出；SSH现有keyscan仅TOFU，不是独立身份背书，不扩大Secrets/信任授权。
- 沿用现已实现的正式Dockerfile两独立context和markerA/B、不同image ID及late-failure断言；不要重新设计镜像回退。仍须在获批Linux环境真实运行，并将容器页面证明绑定到被测image实际服务的origin，不能把另起本地测试服务器的页面算进去；finalize失败保留previous/journal/备份，rollback核对ID及marker回A，另一轮成功finalize另证。
- 容器/配置回退与浏览器数据恢复分别判定。发布前代表同版本完整项目ZIP与hash在批准独立Chrome中导入打开；回退后在**同一可信origin**验证包/Blob/历史，而不是换端口空库。不能以服务重启宣称IDB恢复，也不以改格式后旧应用强读新库替数据恢复。
- Linux Docker/TLS在获批CI/部署环境运行；本机Windows缺运行时不伪造绿灯。页面只用批准Chrome无头/独立profile；缺Chrome/信任证书为精确阻断，不静默扩大浏览器或用 `curl -k`。smoke不调用付费模型。

## 11. 施工包职责索引与当前差量收口

以下原“包”是正式任务的内部编辑/验证步骤，不增加任务ID、依赖或第二份进度表。§11.2保留其职责与算法映射，**不是把已做部分重列待办**；当前停在R5.1/包11未闭合，恢复只执行§11.5实际差距，进度及是否可执行仍取state与用户最新授权。

### 11.1 先准备执行环境，不从头再审计

恢复开发需用户另行明确解除停工，再按计划§2.2/§16.2取得真实产品Goal观察；独立规划Goal不匹配产品目标，不能替换绑定。既有483文件快照只保留其时点恢复范围；下一次写入前对当前精确代码/配置及同版本代表项目包核对字节/可恢复性，不重复整个早期基线或清库。`suiteReports`旧故障和emit半迁已不作为当前阻塞；已报告4_4两层失败不重跑来“确认”。

施工前每包写五行：用户可见结果、精确文件/符号、必须保留的不变量、最小实际运行、失败/回退条件。禁止把整份设计丢给低模型要求“自由重构”。

### 11.2 包顺序、边界与最小证明

| 包 | 承接原任务/依赖 | 文件与实施顺序 | 包结束用户可见结果/证明 |
|---|---|---|---|
| 01：闭合产物集合 | R5.1/R7.5；原子联调组A起点 | `build_product_v2_ts.mjs`→`jsconfig.json`→检查实际import；按§10.7两阶段生成、传递源码集合；不单独覆盖不相容旧JS | 产物规则完整；与02/03共同签组，不以编译或新JS文件出现验收用户行为 |
| 02：迁已有owner消费者 | R5.1/R7.5；组A，依01 | `prompts.ts`→`generation.ts`合authorization→`selection-adoption.ts`接单图report/请求准备→`review-delivery.ts`接整套/导出；`workspace.js`逐对象更新创建、按钮读/写、restore/reset/render；删该对象旧Map/helpers/authorization文件 | 所有已迁对象只有一个写者；不存在新TS/旧JS、reviewRequest回调环、`suiteReports`残留。保留原其他未迁对象，不补通用shim |
| 03：恢复项目生命周期 | 原R3.3合同/R5.1/R7.5；组A，依02 | `session.ts`→`workspace.js` open/close→owner dispose/restore；同步现有`app`消费者；按§10.5保存失败传播/同步禁新动作/独立实例/旧结果保全 | **组A首次正式页面**：新建→打开→回首页→打开→刷新；已存项目、人工Prompt、采用/报告历史不丢，无已知suiteReports失败；改变路径console/network/IDB实证 |
| 04：输入唯一所有者 | R5.1、R6.1/3相应合法切片/R7.5；依组A | 新目标 `project-inputs.ts`→旧intake/slots/analysis/plan/style/spec/ref读写与restore→`semantic-analysis.ts` prepare/current/apply→prompts sources→workspace输入视图 | 人工资料/事实/用途/规格从同一owner保存恢复；消费尺寸的shot受阻而无关shot不锁；旧分析只记录原source不应用到新输入 |
| 05：预占与观察事务 | R5.1/R5.3/R7.5；依04 | `storage/repository.js`及现有validate类型→`domain/attempt.ts`单一action投影/已有判据→generation reserve/observation/storeCandidate→原domain/browser消费者 | 两标签页同/不同授权只一个新POST；迟到A保全但不掩盖B在途；0版OCC、Unknown无自动重提、crash window结论正确 |
| 06：采用与ZIP事务 | R6.2/R6.3相应合法切片/R7.5；依05 | repository commitSelection/readProjectSnapshot/commitDeliveryRecord→`storage/transfer.js`→adoption select/clear→delivery export→现有消费者 | 首次双标签采用冲突不覆盖；明确可选旧候选；完整项目包单快照，交付在规格/报告/采用变化时拒混包；两包Blob/hash/来源链往返 |
| 07：按任务拆视图 | R6.1–3/R7.5；依04–06 | 现有workspace按事实/方案、生成摘要、比较/采用、交付各迁窄view；命名沿项目约定，非预建空文件。view只DOM+订阅+命令；工作台最终只生命周期装配 | 人工完整路径：合法输入→事实→用途/补项→默认Prompt摘要→一次提交→partial比较→就地返工→人工采用→两包；无重复确认面板 |
| 08：图文/可选AI与设置闭环 | R6.1/R6.2/R6.3；必须满足各原依赖，不因包序解除R5.2等门 | settings现有三用途→semantic真实图字节/source→adoption显式单图AI→delivery显式整套AI→manifest/ack恢复→旧调用/复制schema同包删除 | 未点AI不外呼且可按确定性门导出；图文仅提议不确认事实；not_run≠真实Unknown；旧任务补原key，secret不进DOM/IDB/包/log |
| 09：验证消费者与历史闭包 | 各受影响任务/R3.2/R7.5；随前包迁，最终在08后收口 | 原验证器/`v2_test_server.py`等既有前置→移除词条/source/mock回声→历史/INDEX引用→正式入口/Docker白名单 | 源码迁移不假红，重复外发/OCC/字节/秘密/旧回调反例仍抓错；失败/预算/许可/用户原件保留；V1清理按当前R7.3工程门，不全目录归档 |
| 10：发布事务行为证据 | R7.4；离线设计可随前包，实际按原发布前置 | release脚本→probe真实两image/late failure→workflow rollback条件/指纹→Docker实际闭包 | Linux正式构建及可信HTTPS/Chrome；失败真回旧image+静态marker；浏览器同origin数据恢复另证，不以health替主链 |
| 11：整合与最终交付 | R7.1/R7.4/R7.5；依原任务图适用前置和R7.3工程清理 | 删后两轮离线回归→正式人工/辅助/视觉/键盘/真实缩放→直接RC矩阵→受保护PR/CI→既有HTTPS/最终指纹 | 当前Goal与§9.1全成立；启动间歇按计划§7.6因果证明，不重跑洗绿；C17/C15独立真人仍不发生/不伪标 |

**原子联调组A=01–03**是旧半迁树的历史最小复原闭包，现已存在相应运行证据，不再从头执行。04–10的已交付部分同样保留，只修§11.5具体残余；若新证据发现违反既有合同，回到唯一owner局部修正，而不是重新搬全部模块。09的消费者/死路径治理仍与受影响代码同包，10不在产品主链未证时发布。

每个对象的机械迁移固定：列全部真实读写/恢复消费者→复用既有领域判据移到目标owner→更新全部消费者与通知→删除被替代实现→整组生成JS→检查及实际行为。不存在“旧代码先保留作兼容”、仅迁写不迁读、仅迁按钮不迁恢复。

### 11.3 验证选择：明确命令和实际行为，别让低模型刷全量

- 组A一次运行 `npm run check:types`、`npm run build:frontend`、`npm run check:generated`；受影响生成物必须同步。正式原生页面路径需独立Chrome无头临时profile，观察页面+console/network+IDB。不得仅用语法绿或`open()`吞错证明恢复。
- 05复用 `evals/product-v2/node/attempt-contract.test.mjs`、`confirm-contract.test.mjs`、`generation-isolation.test.mjs`；真实IDB两tab预占/late-action场景用既有浏览器宿主，HTTP请求计数为副作用判据。仅新增缺少的确定性交错反例，不写源码扫描断言。
- 06复用selection/package/delivery-gate领域判据及 `tools/verify_v2_6_1_selection.py`、`verify_v2_6_3_project_transfer.py`、`verify_v2_6_2_delivery.py` 的相应已存在入口。所选旧候选/取消采用/规格变更/导出snapshot/Blob/hash是判据，不是mock转发调用次数。
- 07–08使用既有UI/交互/可访问性入口的实际改变路径，辅助部分复用 `verify_v2_2_2_semantic_provider.py`、`verify_v2_5_2_vlm_review.py`、`verify_v2_5_5_suite_review.py`；先全离线正式UI验证。CLI参数从当前工具读，不能按旧聊天猜。
- 10用已有 `release_transaction_probe.py --selftest`、`--page-smoke`、`--fingerprint` 获批Linux入口；不因Windows缺Docker复制一个假脚本。11才运行既定两轮完整离线回归及范围匹配正式验收。
- 会向evals写证据的验证器串行；无需每包跑全仓。控制守卫仅在该包改权威/恢复点时做所需检查。修复后重验失败的具体行为，不把“重跑这回绿了”当间歇根因证据。
- 预算/次数以计划§2.1/§16.1及实时原账本为唯一门。本次旧占用1.61/5元、image8/semantic5保留，新许可最多3元、5次生图/每次1张及2次理解/复核；未受影响真链优先复用，只补必要完整路径或改变缺证。价格/输入上界、公开许可、预算及安全注入先成立，Unknown计次数/保预留；不自动花额度/付费调试/借默认key，超过门及时升级。

### 11.4 交接/失败/升级规格

每包结束更新原任务证据/state准确前沿，不机械将包完成等同正式任务done。日志最小模板：

```text
包与原任务：
用户现在能做的事：
迁入/删除/保留的具体文件与唯一owner：
实际运行：命令/页面动作；结果；产物/错误位置：
未证项、权限或环境门：
下一包：前置、恢复命令、不可执行动作：
```

低模型可依据已冻结算法修正常规类型/接线/稳定反例失败；不得遇错就用户追问，也不得自主吞错、宽化type/any、造not_run/PASS、退回旧JS、取消OCC或自动重试。以下立即停止**受影响路径**并带“事实→规格冲突→最小决策选项”升级：需要改Goal/依赖/业务权限，新增schema/不可逆数据操作，确有不同架构方案，Unknown收费无法界定，要求新供应商/依赖/浏览器/secret通道，保护规则或可信环境不能满足，已报告间歇机制仍无对应证据。其他已授权可达包按原依赖继续，不能交半成品或静默缩验收。

事务/生命周期/发布实现由原PR审查重点核对上述反例和时序；建议在05/06/10合入前进行高能力独立复核。模型“觉得正确”不能代替IDB/HTTP/真实版本回退证据，也不新增C15/C17前置。


### 11.5 当前版本差量收口：无需下一轮总体重构

本节只规定恢复后的改动与证明，不是本次施工指令。产品终点/证据信任/停止门唯一取计划§15.6；原包与任务状态取state。下列具体差距保留原审计时点；2026-10-08当前文件级实施差量以§11.6为入口，不把已解决的owner迁移、个别红项或历史计数重新列为待办。历史材料只作原证明，不为再次审计全仓而重复跑产品。

#### 11.5.1 一次恢复核对，随后只读受影响闭包

用户明确恢复后先运行 `uv run --locked python tools/refactor_resume.py`，核对系统产品Goal及原账本；规划Goal完成不代表产品Goal存在或已绑定。读取state指向的任务卡和本节，保留用户既有改动，核对当前候选/代表同版本项目ZIP后才写产品。若HEAD或文件已变化，核对相关差距是否仍存在，不机械应用本节旧行号或从包01开始。

基线不是一次全套回归：现有审计已证明正式入口45项本地HTTP检查和页面新建/草稿保存/刷新，以及15个TS产物一致；它们范围有限但无需重新购买相同证明。4_3已有独立pass，4_4两类失败、3_5六红、5_3弱oracle及设置空证按已有事实承接，不为确认重新运行；修复后的最小命令见§11.5.4。

#### 11.5.2 固定模块接缝与组合，不引入总编排层

| 所属模块 | 保留的完整动作 | 当前具体收口／调用方不得做的事 |
|---|---|---|
| inputs / semantic-analysis | 人工编辑确认、资料/参考/用途/规格保存恢复、原source提议/人工应用 | 保留唯一 `sources()`；辅助提议进入同一人工确认/依赖流程，不另建模型项目、UI来源Map或自动确认链 |
| prompts | 本地准备、人工编辑/过期原因与精确历史 | generation从其窄投影读实际将发文本/依据；UI不重新编译或以“最新头”替原动作版本 |
| generation | 所见摘要、授权预约、单张/批量/返工提交、原动作观察及candidate保全 | 摘要与事务当前性归owner；删除反向review依赖、UI渲染/error callback和自注入确认读者；只输出执行/候选投影及无业务副作用变更通知 |
| adoption | 确定性单图report、显式AI、采用/取消及ack | 订阅已保存候选、恢复时补本地report，失败可见；不通过generation setter写/读report，不能向generation“补回”采用/AI状态 |
| delivery | 确定性/显式AI整套report、gate、交付提交与两包 | 消费原候选/采用/报告投影和repository快照，构包与围栏在本owner，不让workspace组manifest或恢复suite Map |
| session / workspace / views | session项目切换；workspace一次装配；views草稿/焦点/DOM/URL | 保留inputs→prompts→generation→adoption→delivery恢复顺序；订阅/退订和UI状态投影不执行编译→保存→外发→报告序列，旧实例不复用为新项目 |

**候选与报告的单向消费已落地。**generation先保全原项目候选/asset再通知；adoption订阅并补确定性report，restore内部处理缺失/过期报告。图片保存不以报告成功为条件；报告失败必须可见，保留图片及原采用、阻断不合格采用/交付，不能重POST或伪造PASS。切换后旧动作结果仍归原项目，下游退订，重开由owner恢复。Unknown及在途保护不因拆依赖消失。

**所见摘要归generation。**现有prepareSummary/confirmAndRun负责摘要与预约；视图提交用户看过的意图，不注入readIntent回调、不自行保存授权或runBatch。stale须重新展示并明确确认，不能默认采用新摘要。

**表现通知不携带业务编排。**owner输出结果/忙碌/错误投影，view订阅读取并保管草稿/焦点；workspace管理装配、订阅和释放。原DOM/error callback迁移已实现，不把这一历史清理重新列为下一版任务。

不为“纯架构”另建settings/notification/module平台；现有三用途settings内存凭据、有限配置、HTTP/IDB Seam继续沿用。必须清除的残余限于本表及受影响闭包，不能将所有现存getter/interface都变成一轮新设计。

#### 11.5.3 失败路径与无效证明的精确修复单位

| 单位／承接 | 精确落点 | 固定前置、失败后置与修复后准出 |
|---|---|---|
| 启动拒绝／R5.1、RC19 | `verify_v2_4_4_candidate_blob.py`启动门、既有shared server与受影响正式启动层 | 保留同源URL、server真实绑定地址、进程/线程存活、request/accept/finish时点及Chrome network失败层；只有对应因果证据才能关闭。bind-0已经使用，不再归结旧TOCTOU；第二次load成功、加timeout或“环境瞬态”不是根治证据，boot_retries必须显露 |
| 候选check06／R5.1 | generation候选/批次状态、`ui/generation-view.ts`投影、同4_4原入口 | 受控result持续失败直至显式解除，观察当前失败提示、asset/candidate零半份、原attempt不丢；状态用实际flight/batch/保存后置，不匹配“批次进行中”文案。稳定可操作后明确重取，hash正确且submit计数不增加；解除前不能自动成功掩盖失败 |
| 默认摘要／R5.3 | gen/Prompt领域规则、generation-view及 `verify_v2_3_5_pre_generation_confirm.py` | 自动准备系统Prompt，不覆盖人工；独立固定输入算目标发送集合/文本/hash，UI见到值、确认记录、每shot新action及捕获请求相符。已成功4图不能再伪造4张待发，0张按钮禁用；确有新图/明确返工才验证后续授权。stale零新submit、刷新精确历史、无关图不失效 |
| 下一待处理／R6.2、R7.1 | compare领域判据、compare-view、`verify_v2_5_3_compare_panel.py`-15 | 夹具明确shot顺序、当前位置、待处理/风险类别；事先写出唯一预期及全处理边界，实际点击/焦点落点符合。不得从按钮dataset或同一被测函数求expected，不重新钉“永远第一图” |
| 真BYOK与缺key／R4.3、R6.1–3 | `verify_v2_packet08_settings_vision.py`及当前settings/三用途正式消费 | 页面实际输入可识别测试key并触发合法文字/图文/生图/显式单图和整套复核；批准上游确收指定用途/原任务身份/key，合法出站头含key不算泄漏。清输入后全DOM投影、完整响应/IDB/localStorage、实际两包、console/日志/诊断无秘密，不截固定前缀。缺key场景提供合法图片base64/hash，观察凭据分类、零上游；不能用缺图片错误证明缺凭据 |
| 旧格式包拒绝／R6.3 | 同settings原入口、transfer/import | 由真实当前导出包构造声明不支持的旧schema包、实际上传导入；预期明确拒绝且已有项目/文档/资产不变、无新项目半份。只测当前拒绝政策，不恢复旧格式兼容；删常量 `"probe-ok"`和假hash成功 |
| 发布条件／R7.4 | `.github/workflows/ci-cd.yml`及原release probe | 删除/替换扫描自己token的truth-table源码钉；由现有事务故障场景验证deploy/acceptance/fingerprint失败回退、finalize exit1可恢复回退、身份/清理exit4进入manual而非盲回退。只改真实受影响门与既有probe，不新增发布平台 |
| 容器页面／R7.4 | `release_transaction_probe.py --selftest`现有ST-LIVE与Docker/CI | 不同image ID/marker证据保留；页面对被测实际容器origin执行启动→新建→保存→刷新/重开、资源/console/network/IDB。另起fake server只能证明助手，不能署名容器产品；可信HTTPS和同origin数据恢复再由实际发布/回退轨迹证明 |

每个单位改动与旧路径删除绑成一包；能按固定前置/后置修原入口就不新增永久脚本。产品问题与验证问题分别判断：用例空证不等于产品有bug，用例红也不能直接通过改期望放行。失败现象与机制对应不足，原发布条件仍未证，不让模型自行定性为基础设施噪声。

#### 11.5.4 具体运行与最终顺序（仅恢复施工后）

下列命令均从仓库根执行，**本轮规划不执行**。源码/调用方连贯改动完成后再编译、跑最小受影响消费者；不是每项编辑后刷一遍此清单。

```text
# 改过TS的同包闭合：build包含strict检查，随后只读产物比较
npm run build:frontend
npm run build:frontend-node
# 未改TS但改变受检查调用方时用 npm run check:types；不重复同包相同诊断

# 对应差量修复后选其入口串行单跑，不为确认已有失败重跑
uv run --locked python tools/verify_v2_4_4_candidate_blob.py --label convergence-blob
uv run --locked python tools/verify_v2_3_5_pre_generation_confirm.py --label convergence-confirm
uv run --locked python tools/verify_v2_5_3_compare_panel.py --label convergence-compare
uv run --locked python tools/verify_v2_packet08_settings_vision.py --label convergence-settings
# 改报告owner/订阅时仅加实际受影响报告/采用/交付消费者
uv run --locked python tools/verify_v2_packet08_adoption_ai.py --label convergence-adoption
uv run --locked python tools/verify_v2_packet08_delivery_ai.py --label convergence-delivery

# 发布机制只在获批Linux/Docker环境：缺前提即明确阻断，不本机假绿替代
uv run --locked python tools/release_transaction_probe.py --selftest
# 对批准的部署/恢复可信origin，不带key、不收费；不忽略TLS信任
uv run --locked python tools/release_transaction_probe.py --page-smoke --base https://47.115.172.233:8080
uv run --locked python tools/release_transaction_probe.py --fingerprint --runtime-root .
```

**联调不是另造E2E平台。**用现有正式Chrome无头宿主从空项目页面上传合规参考图／填商品资料→人工事实确认→用途/尺寸补项→摘要生成→partial比较→目标返工→保留/改选→未AI交付实际下载→完整项目ZIP下载/导入/刷新。对同一项目记录页面动作、实际请求及action、IDB版本、ZIP对象/Blob/hash、焦点和真实视觉后置；不以直接种候选或调用内部函数替路径。辅助任务在同一路径上显式图文提议→人工确认，其他规则不另建；三用途配置、刷新丢key/补原key/旧task仅核对、0新submit、精确失效和真实Unknown仍覆盖。

联调同时收口§11.5.2接缝与原反例（两tab预占、late A不掩盖B、采用OCC、单快照/交付围栏、旧实例隔离），按实际改动风险复用§11.3入口，不再为owner迁移复制状态机夹具。视口1440/1366、实际浏览器125%/200%、390px关键可达及纯键盘按原UI入口实际证明；deviceScaleFactor、CSS transform或缩窗口不算浏览器缩放，截图size非零不算视觉验收。

最后一次产品/消费者修改闭合后才冻结候选：R7.1两轮按 `evals/product-v2/refactor/packet11-regression-rounds-20261007T101243Z.md`§1的34项离线清单与**当前registry/CI交集核对**，沿既有命令逐项串行，不因数字34固定新增无关检查。命令采用 `uv run --locked python tools/<该清单验证器>.py --label convergence-<验证器短名>-r1`及-r2；短名按清单实际文件唯一取值，packet08三个label绝不相同。两轮每项实际退出0、必要行为判据均成立；SKIP只证明相应离线部分，真实能力/外部门不能计为通过。原失败文件不覆盖，任一必要红都阻断冻结。

真实能力先按计划§15.6资产规则映射已有证据，不能默认购买一次理解加一次复核。RC候选/结构六项成立后，现有PR→Linux verify→正式Docker build/smoke/selftest→审查/保护→main部署→受信HTTPS/静态资源/隔离页面→完整runtime指纹→finalize依序；服务回退同image/marker和同可信origin包/Blob/历史恢复分开证。线上实际发布行只在事实发生后置proven，不能先写矩阵完成再部署。

#### 11.5.5 升级门和后续维护边界

本轮完成就是原工程Goal与结构准出共同完成，不承诺之后再补一轮总体设计。今后普通变更定位到唯一owner：商品输入/用途到inputs+既有domain，文本准备到prompts，提交/原身份到generation，单图报告/采用到adoption，交付政策到delivery，协议/凭据到现有Adapter/settings，布局到现有view；跨owner只改真实消费者，不重建系统。

新增架构/schema/权限/预算/保护规则、无法建立间歇现象—机制对应或旧证据确实失效且无许可补证，停止对应动作并精确升级；不偷偷豁免或降为“离线MVP”。用户停工则只保存恢复材料，不借“有Goal”继续。规划的3轮上限仅约束本次文档修订，不冒充恢复施工的无限重试许可，也不消耗模型调用额度。

### 11.6 2026-10-08可信基线文件级规格（历史条件，非当前施工表）

#### 11.6.1 范围、前置与复用

本节保存2026-10-08当时“怎样实施”的设计，不是第二份Goal/任务树或当前施工指令。当时追加最多5批、准备时0/5及满5批停止申请均为旧阶段历史，不是当前剩余额度，也不因读到本节而重新激活。当前权限/任务/轮数只取state，费用只取原账，最新执行修订先读计划§17.13；下述算法和消费者仅按未变前提定向复用，已完成收口不重做。

实施前只做一次：运行正式冷恢复，核对当次用户指令、实时产品Goal与原正文、当前任务卡/阻塞及账本；前沿仍blocked时只能处理本任务阻断，后续步骤须满足原依赖。预检实际main保护/rules、PR审查资格及现有Actions/部署权限，记录能否兑现，不以此前审计的`protected=false`或`reviews=[]`冒充新API读数。权限缺口限制相应动作，不绕保护，也不等最终发布才发现。固定源码/生成产物/配置字节身份及稳定同版本项目包；只为变更闭包保存新快照，不重建已成立的全库基线。

保留main `0572b5c`、run `37764592110`已成立的Docker/健康/selftest32/offline13/TLS页面10/指纹/finalize证据。它们证明发布机制和该候选，不证明完整工程Goal。既有marker A/B不同镜像回退与同origin代表数据恢复机制复用；不新增“两个历史产品版本上线”标准，不为证明平台再做一次生产回滚。旧人工路径、键盘/缩放、两Adapter真链及已修消费者只在依赖契约确实改变时重验。

| 工作单元 | 主落点 | 必需修改与条件修改 |
|---|---|---|
| A1 RC19因果 | `tools/verify_v2_4_4_candidate_blob.py`、`tools/v2_verify_shared.py` | 先补最小诊断。`app/product_v2_server.py`只在产品层因果成立后改；不预设HTTP或环境根因 |
| A2 返工对象与动作归属 | `app/product_v2/ui/compare-view.ts`、`generation.ts`、`workspace.js`及其真实调用闭包 | 卡片精确目标/采用标记必改；返工编译保存确认序列收归generation→prompts既有owner。改TS时同包生成JS |
| B1 凭据证明 | `tools/verify_v2_packet08_settings_vision.py`及原单图/整套/网关验证器 | 修证据消费者的精确接收与泄漏oracle；生产凭据/Adapter只在实际反例成立时改 |
| B2 辅助整链与结构 | 既有`walk_*`、项目传输/交付验证器、当前任务卡和结构矩阵 | 实走缺失消费者并对齐结构六项；不重迁已经删除的reviewAccess/setter或新建验证平台 |
| C 旧面cutover | 原R7.3 WIP、`check_project_state.py`、pre-V1实际消费者/依赖/说明 | 原授权和G6/R7.5前置成立后一次迁移并删除；守卫只允许精确已退休历史证据 |
| D/E 最终冻结与交付 | 既有回归聚合器、验证登记、CI/CD、准出矩阵 | 最后改动后一次最终两轮，再用现有PR/发布事务交付新候选；不预设重写runner/CD |

#### 11.6.2 A1：关闭间歇启动的因果缺口

`4_4`已有`boot_retries`与两次加载，导航异常还可能发生在ready等待的catch外；源码“与产品无关”的注释不能作为分类证据。保持产品server绑定0号端口并读回真实地址，保留首个失败URL、时间、阶段、控制台/requestfailed/response及所有重载事实；后一次成功不能关闭首个失败。先在明确的本地验证host中关联单调时钟的bind/listen、实际接收/handler进入与完成、关闭及线程状态，只记方法/路径/状态与诊断标识，不记key、请求体或商品图片。必要时覆盖导航异常的采集，不增加加载次数、延长超时或默认重试来洗绿。

| 观测分支 | 下一动作 | 本分支准出/停止 |
|---|---|---|
| 失败时未接受/未收到请求 | 对照当时绑定地址、监听/生命周期、实际浏览器目的地址与传输/代理层 | 建立同一失败时窗的对应；事后另一个GET成功不是先前监听正常的证明。需不可达系统诊断/权限则指出具体缺项 |
| 已接收但处理未完成/连接提前结束 | 定位当前HTTP/线程/body/关闭路径 | 只有受控反例和修复后同路径证明才修改server；不凭HTTP/1.1字样全局换协议 |
| 响应完成但UI未ready | 对照模块下载/执行、JS异常、IDB/页面启动阶段 | 改真实页面启动消费者，不把所有异常统称端口问题 |
| 只有成功样本或无法区分假设 | 保存已有失败与缺失的最小原生观测 | RC19保持blocked；停止盲取样，不采600次通过率、不宣称环境噪声或根治 |

诊断能力与机制修复分开记录。机制确立后实跑原`4_4`入口；若变更确实触及4_2等消费者才补对应入口。非产品层原因只修相关host/环境并准确报告，不添生产遥测平台。失败前证据保留，修后证明必须对应同一触发条件；付费模型不参与启动诊断。

#### 11.6.3 A2：第五步“看到谁、操作谁”及返工owner闭合

当前源码已捕获卡片显示的candidateId交给openCompare，并以显示ID是否等于采用ID决定采用标记；通用“比较”仍允许恢复上次查看。返工准备/确认已归generation，view不再编排编译→保存→授权→外发。这些是当前已实现结构，不重复施工；下一版两种送图模式的新增契约见§13。

继续保持的消费者不变量：
- 点击卡片时固定来源，晚到候选不能替换所看/返工/采用对象；显式来源消失须阻断，不能回退到另一个候选。
- 准备/取消零持久化、零外发；确认重验项目、来源hash/版本、输入/Prompt/配置与预约围栏。过期零POST；合法追加Prompt后再失效须保留真实历史，不能伪称零写。
- 人工全文不能被系统编译覆盖；双击/跨tab沿既有事务阻断，旧action晚到结果保全，Unknown不自动另发。

复用现有5_3/5_4的来源身份、取消/过期、双击、人工Prompt及项目切换行为证据；前提变化才局部失效。当前本地基线运行现有消费者，下一版新增edit_candidate/regenerate_original还须按§13验证实际送图。注入候选的精确回归不是完整真人路径；TS变更只做同批type/emit与受影响行为门，不各开两轮全量。

#### 11.6.4 B：精确凭据、辅助整链与原结构准出

凭据：已有等长哨兵和`<length:n>`只证明通道/长度，不证明接收值；FakeVisionSemantic的`apply_credentials`本身是no-op。复用registry当前匹配注入实例并调用`apply_credentials(api_key=byok)`的正式路径，在测试实例/既有transport或llm_factory中仅保留内存精确相等的布尔值与计数。文字/图文理解、生图、单图/整套复核按实际消费者分别证明接收预期用途key；等长交换哨兵必须使断言失败。不得把浏览器发送header、mock返回常量或长度当实际Adapter接收证据，不改生产验证器的key值语义。

在明确输入哨兵后扫描DOM非凭据回显、localStorage/sessionStorage、全部相关IDB文档及Blob字节、响应/错误/控制台/服务日志，并用ZipFile解压完整项目与交付ZIP的所有成员再扫；只记结果，不落盘哨兵值/真实key/hash。合法密码输入框、单次request header与测试provider内存接收不算泄漏表面。复用现有无key、default-trial closed、reference缺字节、旧ZIP导入和两Adapter离线transport用例；各反例必须先满足其它前置，不能用“缺字节”证明无key或用constant证明导入。

旧任务补key/恢复还须经现有status/result路径：原action/provider/model/credential_reference保持不变，错目标明确拒绝且零出站，补原目标key只核对/取回、不产生新submit。优先扩现有`4_1`及packet08消费者；生产registry/credentials/server/Adapter仅在上述实际反例失败时做相应修复，不顺手加校验/重试/抽象。

辅助整链：独立临时profile与真实页面操作，从建项目、填写事实/导入许可商品参考图、明确图文理解、可编辑事实/用途、默认Prompt准备、一次整套明确外发，走到比较/指定候选返工/人工采用/可选复核/交付ZIP/完整项目ZIP，再清空key、reload/新profile导入恢复。不得用`SEED_SLOTS`或内部文档灌入代替商品资料/理解到槽位的消费者；既有`walk_*`用前先核对其seed行为，只复用真实UI动作部分。分别保存关键截图并实际读图解释控件/对象/状态，不用截图文件存在代替观察。

记录独立后置：事实与槽位来自此次输入、外发张数/范围一致、旧采用未被新候选覆盖、返工source精确、项目ZIP文档payload与资产字节/hash相同、交付ZIP选用候选/来源/manifest如实、重开后BYOK为空且历史/采用可恢复。不自动触发AI复核、不因未复核挡导出；确定性报告/人工采用/硬检查仍强制。本地fake用于可控异常/Unknown/过期与安全证明，不能提升为真实图文质量证据；C17/C15仍等待真人。

2026-10-08当时读数为image8、semantic/VLM5，当时补充门最多5张生图/2次理解复核、增量≤3元/累计≤5元，原拟“一轮理解+四张整套+一次返工”只属该时点方案；**不是当前额度或调用授权**。当前只补合同确实受影响/缺失部分，依真实ledger与state核次数/费用、安全注入和素材门，不能重新消费旧额度或重复购买已证链。调用前仍须核官方协议/价格上界、许可/hash及获准通道；Unknown保留次数/预留、不自动重提，准入不足只停对应动作，不用fake补签真链。

结构六项逐项引用当前生产消费者及实际运行证据；源码已删除的reviewAccess/setter与旧Map迁移不重新实施。返工编排残余按A2处理；其它不满足原准出的项须同闭包实际修复，不能用类型绿/空扫描/“后续再重构”签署。此处只核对原结构门，不新增总体架构、全仓TS或新schema。

#### 11.6.5 C：复用WIP并一次清退旧运行面

依赖与R7.3准入成立后，以`15faa65`的114删/3改/9恢复材料为差量来源，不直接合并未收尾分支。先核对当前main和WIP的语义差量及冲突，保护之后的消费者修复；同一个清退包包括必要消费者迁移、原件/恢复材料证明及旧实现删除，不能让两套活逻辑并存到下一包。不是先清退再绕过G6补验。

1. 逐用途处置`app/server.py`的V1 flags/dispatch与旧doctor，`verify_v2_1_2_project_home.py`的V1 route案例，以及pre-V1 `run.py/web/renderers/config slots/catalog/docs cards/tools`真实调用；必要文档/状态/P治理功能迁现有控制入口，产品旧执行链删除。共享`src/product_facts.py`/`src/review_contract.py`保留有实际用途的部分：当前消费者在`eval_dataset.py`/`pilot_registry.py`，不是假定V2 server/provider依赖，也不能因产品旧面删除而误删P治理。
2. `tools/check_project_state.py::_evidence_ok`及done阶段J5、done任务J6两条调用统一按同规则处理：只有superseded所有者、精确获批退休路径、原commit/bytes hash及可达归档全部满足，才把“当前路径已退休”记历史说明；当前证据、非退休缺失、无有效归档仍error。覆盖原阶段/任务、退休/非退休及归档篡改反例，复用现有`evals/probes/project_state.py`，不只修改task调用。
3. WIP全量tracked-manifest的3282条仅识别历史原字节，不是全部可删除/退休的许可。单列实际114删除及此次明确核对的pre-V1新增退休子集，与原commit/hash/可达原件对应；守卫只接受该精确子集，不能把“全manifest成员+当前缺失”解释为合法退休。main路径不可达的WIP材料须从已核验Git blob恢复到稳定位置，不能以临时路径或单个hash声称可恢复。
4. `check_docs.py`依赖`src/schema.py`/cards/`run.py --dry-run`等旧消费者时先迁其必要检查，再删旧producer；不要把“删除检查”作为迁移。核对依赖引用后才移除仅旧面使用的包；若`jsonschema`确认只剩退休消费者，则用现有uv依赖工作流同步pyproject/lock/context，不手改lock。README/AGENTS/context/INDEX/design中已被新工程清退授权取代的“真人前一律保留V1”说明同包更正，保留C17/C15限制、旧历史及用户原件。Docker排除规则只删真正死项，runtime闭合白名单不放松。
5. 复用稳定`asset-continuation-20261008T054352Z/data/manual-project.zip`（原SHA256 `4007b9b1a3b2f14c1fa4e851bdc1ab52ebc690fc02d4556f65b81a1ff4e3ff39`）及既有`6_3/6_2`项目/交付消费者，先验证当前字节和同版本对应再用。独立profile导入、重开，逐文档payload/资产字节核对原数据；删后做真实指定返工、人工采用、两包导出/恢复，新增业务记录单独说明，不要求追加后项目ZIP整体字节还相同。旧R7.3私有probe只有counts/hash，不能代替采用当前性、payload和返工证明。

最小门：受影响文档/状态/既有64向状态探针、必要类型/生成产物检查、删后真实路径与恢复。控制改变如影响验证登记再跑其已有守卫，非每包机械重跑全部平台。失败保留原件与候选，不删除唯一数据恢复包；无法迁移独有必要用途须升级，不用改名legacy来伪装清退完成。

#### 11.6.6 D：最后改动后的同候选两轮

冻结包含TS源、实际JS产物、服务/Adapter、runtime/public配置的不可变候选身份，串行运行期间不让其它代理/进程改产品。正式命令：

```text
uv run --locked python tools/verify_v2_7_1_regression.py --rounds 2 --stamp <本次唯一候选标识>
```

尖括号是实施时替换的参数，不是已执行结果。命令集合以当前`.github/workflows/ci-cd.yml`与`config/product-v2/verification.json`双守卫为准，不硬编码旧34/44计数。`--only`/单轮/局部label运行只作诊断，不作为最终准出；有red保留真实round与输出，修后受影响候选重新冻结，不能拼跨版本通过。

当前runner指纹覆盖script/args/rc/signals，不覆盖产品源字节，须另保留运行前后不可变commit/tree及source/emit/config字节身份，不能用result指纹等同“同代码”。runner已保留非零失败且继续收集后轮，并非自动洗绿。现有子验证器多用时间戳命名；不因未显式传r1/r2 label便断言覆盖。记录两轮实际原生工件路径并确认无碰撞；只有观察到碰撞才做最小修复，新增label若参与args指纹须仅规范化标识差异、不得抹平语义参数。不得为这一猜测新建回归平台。

两轮全绿、源码/产物身份一致后刷新当前适用RC/结构矩阵及历史证据范围；C17/C15注明未发生，不升为真人通过。中间阶段不提前另做两轮；若只有合并commit变化且实际源tree/字节完全一致，建立映射，不仅因HEAD不同强买第三轮。任何产品/config字节变更则重建受影响候选证据。

#### 11.6.7 E：沿现有发布事务交付

使用A前置已预检的保护与审查资格，合并/发布仍以当时实际规则及授权为准；保护不足不能直接推main、绕过或追认旧PR review。CI沿既有types/generated/domain与登记浏览器门→真实Linux Docker→健康→release selftest/offline rollback→获批Secrets/SSH→部署→HTTPS页面smoke→fingerprint→finalize→工件上传与失败恢复执行，不新增CD平台。本机Windows无Docker daemon不能用本地假绿替代Actions证明。

新候选commit/tree映射、镜像ID、runtime/public/served_scripts指纹、HTTPS同源实际页面与release.json对应后才称发布该候选成立。原机制证据有效则复用；按合同核对新候选数据/恢复材料，不无故再次生产回退。发布事务exit1沿现有受控rollback，exit4需人工处置时保存现场并精确升级，不盲回滚/删previous或用户库。Secret只走获批运行注入，不读取GitHub值/打印key/要求用户粘贴。

本节保留2026-10-08“基线先行”的历史设计来源，**不再用其将显著视觉/人因问题后置**；当前交付优先级取计划§17.13及本设计§13。精确对象、外发/费用、Unknown、普通用户负担、视觉层级和真实内容的布局都要在工程交付前按具体任务核实；C15/C17另列未发生，不代替这些工程修正。规格、局部验证、完整工程和实际发布分别判断。


## 12. 给下一轮执行模型的启动入口

以`docs/INDEX.md`§1为唯一读取路由；先判state当前门与真实Goal，再读计划§17.13及§17.2–17.5的当前包，具体问题/验收取关联Issue，只加载该包受影响的§13合同和现有owner。最新用户授权/工具阻塞优先于本文的历史准备权限；工具不可用不创建本地Goal替身，也不据旧设计启动产品。

当前实现规格取§13，费用/次数/实施批次只取原账与state。已成立的owner收口、五图原件和两包恢复按未变前提复用；新增Prompt/界面质量缺口不被旧局部green覆盖。具体Issue/PR流程与skill产物只取AGENTS，设计不另立工作流。

早期§12的五阶段、§16预算及“先再做一次套图准备”启动文本已退出日常入口，原字节可从本轮维护前快照追溯。文档/守卫通过只证明规约及恢复一致，不证明产品修复、真图品质、最终两轮、线上交付或独立真人验收。


## 13. 下一版实施规格：普通决定驱动可信整图

### 13.1 目标、授权与交付边界

本节记录的设计始于2026-10-12准备轮；“相信现在生图模型的能力，好好想想效果不好怎么证明不是发送的提示词效果不好”和“两种方式都提供”继续约束产品方向。该轮独立设计Goal、0元准备预算及实验身份只是历史，见`_working/amz-listing-kit-next-version-design/discussion.md`；当前完整交付授权、额度和原生绑定门只取计划§17.13/state，不以旧设计权限阻断已授权工作或伪造当前Goal。

结果：普通运营人员复用商品照片和已有资料，经少量真实必要决定，获得有依据的方案；系统负责专业表达、准确发送、交错审图、指定来源返工、人工交付与原生恢复。模型直接整图生成优先，不默认合成、换模型或把专业Prompt责任交给用户。衡量成品和总使用成本，不以输入字符数、报告数或绿色检查数量代替。

当前实施守既有架构/owner和本节行为合同，按计划执行包闭合读写者与实际用户路径；不照搬原型或整包恢复WIP。只维护规约/交接不算新产品实现；正式施工仍须state规定的真实原生绑定及相应操作前置。真实调用逐次核金额/次数/许可/价格/安全通道；启动机制、原生包、秘密与最终两轮的既有证据按未变前提承接，不用设计存在代签。

以下接口是**下一版目标合同**，不是已经存在的功能或上线声明。当前系统的返工仍主要按商品参考图重新生成；候选ID/hash不是供应商收到候选图片的证明。

### 13.2 设计准备时基线与实验资产（历史资格）

以下“本轮/当前”描述2026-10-12–13实验时点，不发布今天的main/WIP实现状态。只按当前包未变前提复用其具体后置；当前已完成基线、PR和剩余差量取state/关联Issue，不重复当年的V1/owner/宿主切换。

| 依据 | 已知事实 | 使用边界 |
|---|---|---|
| 2026-10-12实验工作树与该轮`baseline/manifest.json` | 当时HEAD `48bb3c1e2f3751a984170a01361a2fba5f6e4ae4`，420文件原字节已保存 | 仅历史实验身份；当前main/PR/线上分别从state与实际对象核对，不冒充当前工作树 |
| `manual-project.zip`原件与本轮 `baseline/restore-checks.json` | 2,417,036B，SHA256 `4007b9b1a3b2f14c1fa4e851bdc1ab52ebc690fc02d4556f65b81a1ff4e3ff39`；当前实际无头导入/刷新55个文档payload、6个资产字节一致 | 是同版本原生恢复，不是真图质量；追加返工/采用/两包另由本轮6_3正式消费者证明 |
| `minimal-input-mug-20261009.md` §1.1/§3–4 | 成败案例仅共享照片，风格/单图规格/事实/代码条件不同 | 是假设和判据来源，不是受控Prompt对照或模型上限证明 |
| `auto-preparation-fix-20261010.md` | 本地系统原文基线/连续自动准备/人工草稿保护已证，未部署 | 不重做修复；其前提改变时只回归受影响路径 |
| 现有inputs→prompts→generation→adoption→delivery | 单向owner主干、卡片精确候选与返工owner已落地 | 大文件不按行数再拆，旧文档的“当前残余”必须退出当前指令 |
| `prototype/observations.json` 与 `prototype.html` | 原五路径交互原型的逐项观察与失败/修后记录，来源为该HTML的完整SHA256 | 不与后续工作台原型混用来源；内存演练不签正式持久化或品质 |
| `prototype/workbench-layout/observations.json` 与 `workbench-prototype-20261013.html` | 三结构布局测量、候选草稿切换、晚到前后值、截图索引及后续标签/模态核对；保留控制错列red | 按各次观测的源码阶段记资格；最终HTML可重开，不外推所有旧截图已来自最后字节；720×450仅重排代理，不是原生200%缩放证明 |

本轮资产统一在 `_stage-amz-control/next-version-design-20261012/`；恢复记录解释原件、来源和资格。工具最初对自定义Chrome未传headless，相关早期观察已剔除；后续显式flag且核原生启动命令。保留失败，不用最后绿色覆盖过程。

清退后实际消费者：本轮1_4证明默认正式入口、保留V1入口、进程/浏览器重开及服务器同源重启；6_3从真实UI资料/确认走到生成/采用/两包/独立导入/指定返工/再次交付；5_4证明准确预览与实际Prompt、影响隔离、失败、Unknown及刷新；4_3证明部分失败、停止与剩余队列恢复。type/emit/生成一致性、现有domain与文档/冷恢复通过。后续仅改变服务器连接接纳及对应自检：当前HTTP/1.1同源模块拒连已受控复现，监听与线程仍存活；OS合理队列上限修复后同触发真实无头页面正常，正式4_4覆盖候选字节/配额/刷新及入口53/53。未改变前端、协议、配置、持久化及其业务语义，既有主链证明按此影响边界复用；未刷全量。准确工件只见discussion及baseline/verification.json；4_3播种只限定故障消费者资格。当前可作为本次设计的可信本地替身/恢复基线，不是线上、真图品质或原完整工程准出；历史故障不全被唯一归因，原RC19最终两轮仍未完成。

原型发现并收敛的机制：明确导航后聚焦目标标题；候选按钮按candidateId保留DOM，而非每次全部替换；异步进度不重建编辑控件；原生dialog之外补本地首尾Tab回环，Escape仍取消并返回触发按钮。正式实现复用现有DOM/视图基础，不复制原型壳或另建组件框架。原型“恢复”是假状态，不替代正式ZIP/刷新证明。

### 13.3 人因、界面与交互判据

这是本版设计准则，不自称完整WCAG认证或真人通过。2026-10-16用户要求修订信息过载与长页：桌面商品图工作是主场景，窄屏/原生缩放保证可达，不建设两套同等复杂产品。以任务分析→主次信息取舍→情境走查→真实用户任务评价落实人因；ISO 9241-11的使用情境/有效性/效率/满意度及9241-110交互原则为参考，WCAG为可达性下限，均不意味着“手机优先”或绝对零滚动。具体问题/验收归Issue #8，不以截图、机械断言或规范存在签易用性。

| 判据 | 实施要求 | 可观察的否定条件 |
|---|---|---|
| 必要决定而非专业考试 | 已确认资料不重问；只问会改变本次请求且不能从证据/明确目标得到的决定；共用决定只保存一次 | 要用户重填名称/事实、写摄影Prompt，或用带残留照片擅猜清洁/用途 |
| 证据与意图区分 | 照片能支持什么、缺什么可见；清洁/倒空是展示意图，不是“新品/无损”事实；构图/光照是可改建议 | 元数据冒充看图、创意补尺寸/附件/背面结构、模型提议自动确认 |
| 可见范围/费用 | 首次发送前一份真实摘要与一次明确确认；列实际图序、范围、排除项、模型/尺寸/次数及已核费用上界；未知费用明确未知 | 看5张发4张、偷偷送候选、未知费用填0、确认后用新摘要自动替换旧意图 |
| 对象安全 | 正在查看、当前采用、对照基准、模型返工源分别显示；问题候选与模型源可不同 | 查看v3自动采用v3，或原照重生成仍把模型源标成候选 |
| 成功可立即审图 | 一个稳定逐图列表＋精看区；任何一图成功即可看/采用，其他任务继续 | 重复上下清单、等整批结束才看图、失败遮住成功图 |
| 就近比较与决定 | 默认左商品依据＋右当前候选两图，按原比例；按需历史对照时左对照位切为选定历史候选，右查看对象不变，商品依据可切回，不常驻空第三列；采用/返工邻接图片，不改变采用/返工源/发送依据 | 常驻空列、裁掉商品、偷换右查看对象、概览夹在图片与动作之间 |
| 草稿与焦点 | 控件按项目/图/候选身份稳定；输入不抢焦点，晚到不改查看/采用/源；系统原文基线识别真脏稿 | 新候选到达清空草稿、重建textarea导致插入点丢失、旧系统文本误判人工草稿 |
| 可恢复错误 | blur/明确提交后反馈；输入时不不断训斥；就近错误＋可聚焦摘要/字段定位；失败保留输入 | 保存失败看似成功、报错后从头录入、只禁按钮不说明原因 |
| 键盘与可读性 | 语义label/fieldset/button、可见焦点、非颜色单一状态、模态双向回环/Escape；正文16px、主要点击区44px以上是本产品目标，不冒称WCAG AA统一尺寸 | 键盘进不去或出不来、取消后无定位、仅颜色区分失败/Unknown |
| 屏幕约束 | 常规1366×768/1440×900桌面切图→对照→切候选→采用不靠整页上下找动作；1024×768仍可比较/操作；窄屏/原生125%/200%允许必要纵滚与重排 | 横向失控、主动作被遮；以缩字/裁图/锁滚动或多重嵌套滚动框伪装一屏 |

当前main用户任务入口仍为六入口（资料 → 理解 → 方案 → 生成 → 审核返工 → 交付），以现有 `PROJECT_STATES` 派生与硬门为准。四段可见导航（资料与事实 → 方案 → 制作与审图 → 交付）是#8待交付的重组目标，同包退出旧重复列表/旧跳转编排，不并存两套运行状态；现有四个views与左列表＋精看骨架复用，不重做owner。项目state缓存不能替代实际事实、attempt、report或selection的当前性判定。

**保留A的左列表＋常驻精看骨架，原型细节不再作为冻结成品。** 原8图/10候选实验只说明A相对B/C减少切换、采用可见，不证明真实内容简洁或真人效率；B/C继续只留实验资产。正常界面只显示当前对象、决定所需信息与重大风险。SHA256、candidate/task/action ID、规则码、原始JSON及执行历史集中按需诊断，不在每张卡/参考图重复摆技术详情；完整性/秘密/追溯合同不减。删重复教程和正常过程长说明，费用、实际图序/来源与阻断原因在决定处明确呈现。

| 可用CSS宽度 | 重排基线（按真实任务验证，不以固定尺寸代替可用性） |
|---|---|
| >1100px | 工作台最大宽1440px、边距24px；左列表244px、列间16px、精看区`minmax(0,1fr)`，不沿用940px表单限宽挤压审图；两图并排，不增常驻第三列。项目栏/导航紧凑，图片和主要动作占核心空间 |
| 901–1100px | 左列表210px，精看保留并排；长标题换行，不挤成水平滚动；1440/1024的示意图尺寸不是生产图片裁剪尺寸 |
| ≤900px | 同一精看区单列，由带label的逐图选择器切图，选项带图名/任务/采用状态；进入批量模式后提供当前图“加入/移出待发送范围”，不丢原有范围能力。图及其来源/候选选择器相邻，采用/修改随后；不以CSS视觉排序打乱DOM，不承诺手机与桌面相同审图效率 |

左列表仅含图名、任务/采用状态；图名是可聚焦查看入口，不另给每行重复“查看”按钮。批量模式才显示待发送勾选，查看与勾选/采用互不改变；退出模式不静默丢范围，真实外发由摘要重验。长列表可纵滚，精看不随任务刷新重建，不增重复缩略图带。默认商品依据一次看一张，用清楚选择器切换多张依据，不把所有原图纵向铺开。图片保留原比例`object-fit:contain`并可明确放大；高图/窄屏/放大时允许必要滚动，不能裁商品或缩得无法判断。

精看默认审图态：图名/状态→左默认商品依据与右当前候选比较→“已采用v1／正在看v2”及必要阻断→邻接“采用v2／修改这张”。显式切按需历史对照时，左对照位改为选定历史候选，右当前候选不变；商品依据保留可切回入口。保持身份与正常多原照选择；历史版本缺字节给恢复提示，不偷换查看对象、采用源、返工源或发送依据。未生成显示准备/缺证/提交状态，不摆空候选框；失败/Unknown保留合法旧候选，原任务核对与新动作分清。修改在同一精看区进入编辑态，保留候选预览，旁边提供普通修改要求、模式与真实图序，不往页底追加返工/Prompt/报告/执行长块。低频取消采用、显式AI复核和历史走明确次级入口；正常保存/检查只短状态，错误就近说明解决办法，不能只灰按钮。已采用同一有效候选才禁重复，旧采用当前性仍按owner硬门。

草稿键为项目＋shot＋问题候选精确DocumentRef（id/version/hash），mode/text归该草稿；查看另一个候选不改返工源，明确显示不一致并给“返回返工对象”。切图收起当前草稿但保留，回图继续原候选草稿；新对象新建独立稿，不复制旧方向。同图有多个非空草稿时列明候选供选择，不用`find`静默选第一个。只在用户主动切图/打开返工时定位标题/字段；异步到达只增状态/候选选项，不夺焦点、插入点或采用。未保存草稿仅在当前会话保留，刷新/关项目前明确提示，不承诺原型Map就是持久化。

资料页突出参考图/核心资料/待确认问题、事实分类按需查看；方案为紧凑图片清单，选一图编辑例外、共用风格一个入口；交付突出采用成品、待解决问题和两包下载，不铺检查过程。实验模式切换/模拟到达/debug条不进产品。方案页的按需单图设置只收已设计的三个语义：§13.4明确单图覆盖的三态印字意图、§13.16.2的单图布局例外、§13.4绑定有据视角的单图presentation例外；引用§13.4/§13.16，专业参数仍由系统承担，不要求用户逐项填写；无依据视角拒绝并提供补图/沿可见视角，不扩大成模型自动确认。

**同包替换落点（目标合同，当前实现及剩余差量按下表区分）：**

| 现有落点 | 新职责与必须撤销的旧面 |
|---|---|
| `index.html` / `ui/stage-shell.js` / `workspace.js` | 当前main六入口与交付页整套检查已经成立；四段导航重组及旧面同包退出是#8待交付，不再当作已完成。现有四个views与左列表＋精看骨架复用，不重做owner；剩余差量为真实内容滚动/遮挡、对象区分与反馈恢复 |
| `ui/generation-view.ts` | 已是唯一逐图任务列表、待发送范围及生成摘要/队列状态的承担者；后续只修真实内容主动作与对象关系，不再重复建立列表或恢复旧候选卡 |
| `ui/compare-view.ts` | 已承担常驻精看、历史对照、草稿、报告、采用且旧`review-list`/`renderReviewList`实现已删除；后续只修精看信息层级与修改态，不把返工事务迁回view或恢复旧列表回调 |
| `ui/input-view.ts` / `ui/delivery-view.ts` | input承接事实/展示决定与方案；原`suite-review-*`整套本地检查/可选AI动作已在交付视图。保留人工采用硬门、来源/费用说明、整套检查及两包导出；不因布局冻结删除业务命令或历史 |

TS/生成JS、elements绑定、stage-shell导航/焦点、订阅释放、现有正式消费者一起迁移；旧DOM/回调/跳转/注释同包退出。Module owner仍为§13.5，不新建总控Module或复制原型脚本，任何候选不得新旧双渲染。

### 13.4 普通决定、文案与记录形状

专业表达由系统承担；已有人工全文仍保护。新字段写入现有StyleSpec/ShotSpec与版本化Prompt链，不创建“意图包”、另一商品事实库或聊天Agent。

1. **事实**仍是现有FactSlot：用户输入/原照观察/模型提议/默认/派生有来源和状态；model只能propose，不能confirm。明确用户确认一次覆盖同一值，不让已确认值因换图重复录入；保存草稿不等于确认。
2. **展示决定**：StyleSpec的新 `presentation` 提供共用默认；ShotSpec同名字段只存明确单图覆盖，未覆盖则继承。字段为 `appearance_state: "as_shown" | "clean_display" | "undecided"`、`contents_state: "as_shown" | "empty" | "not_applicable" | "undecided"`、`viewpoint: "reference_visible" | "front" | "side" | "top"`。共用“洗净、倒空”同时设置前两项，不代表新物性；非容器不展示倒空问题。非原可见视角还须绑定可支持该视角的商品依据；仅文件名/角色不能证明视角。
3. **问不问**是用途及证据投影：相关展示状态有歧义且会改变请求时才问；没有歧义/不消费该决定的用途不拦截。未回答的必要项为undecided并阻断对应图，不默选清洁。用户选顶视但无支持图时给“补图/使用已证视角/暂不做此图”，不补造隐藏结构。
4. **上图文案**明确选择，不遍历所有事实自动印字。ShotSpec新增 `on_image_texts`，每项有稳定text_id、原文text、源FactSlot精确DocumentRef、status（proposed/confirmed）和origin（user/model/reuse）；只消费confirmed且来源当前的项。品牌按原文保留，数字/单位/维度对应原事实；说明指令与实际印字分段。系统可在一次已明确外发的理解中提出英文文案，人工确认；纯人工路线可用已有文案或明确选无字，不强制AI/翻译/专业Prompt。自由文本与事实的语义关系需人工对照，Schema绿不证明文案真实。
5. **推荐**仍由 `domain/suite-plan.js` 消费用途/事实/参考；每项输出目标相关性、依据、缺口及替代动作。只默认选目标相关且有依据的图；无尺寸不凑尺寸图，无竞品不凑对比图。未知非消费者不成为全项目填资料义务；用户可以显式建未就绪图，但不能偷偷生成。

系统建议的背景/光照等可逆创意标明“建议”；用户明确意图优先，商品事实/平台硬约束不得覆盖。已存在手写keep/change_allowed/notes原文保留；结构决定与其冲突时展示给人，不能声称字符串相交或万能LLM自评已消除全部语义冲突。

### 13.5 唯一owner、Module Interface与实施落点

接口名沿当前owner扩展；下一版落地时查全部引用并同包迁移。返回只在本领域定义窄联合，不建通用dispatch/总线/port层。视图只交用户输入/所见版本、读取投影，不能自行保存→授权→HTTP→report→selection。

| owner／现有文件 | 下一版完整命令或投影 | 所有权/消费者约束 |
|---|---|---|
| inputs `project-inputs.ts` / `domain/specs.js` | `savePresentation({scope, presentation, seenStyleVersion, seenSpecVersions})`；`saveImageTexts({shotId, texts, seenSpecVersion})`；`planRecommendations()`只读 | 共用决定保存StyleSpec一次；单图覆盖保存对应ShotSpec并OCC。涉及多条时返回逐图成功/冲突，不伪装全成功，不回滚真实历史；部分冲突须解决或明确排除后进入发送摘要。沿现有 `documents.save`/来源和通知，不新建通用批写平台 |
| inputs / semantic-analysis / `ui/input-view.ts` | `slotAction`及现有runAnalysis/sourceIsCurrent/applyProposal；相关提议/缺证投影 | 只确认用户看过的原输入版本；切项目/旧proposal不套到新资料。人工通道保留，文字理解不冒充实际看图，真实图文须显式发送 |
| prompts `prompts.ts` / `domain/prompt.js` | 现有compile/compileAndSave/requestSnapshotOf消费结构决定及下文RequestReferenceSelection；系统准备/人工稿当前性投影 | 独占表达、来源与版本；UI不拼Prompt、不用最新头替原动作；自动更新沿已证渲染基线，真正脏稿不覆盖 |
| generation `generation.ts` | `prepareSummary({scope, mode}) → SummaryIntent`；`confirmAndRun({intent}) → started/blocked/stale` | scope由用户选择，不让view自己裁队列；意图带所见项目/会话/来源/配置/图序/版本、requested与实际scope及逐图排除理由。状态变更必须重看摘要，不能自动扩大集合 |
| generation | `prepareRework({shotId,candidateId,mode,problems,direction,promptChoice}) → ReworkIntent`；`confirmRework({intent}) → started/blocked/stale` | mode仅edit_candidate/regenerate_original；candidateId是固定问题候选，实际模型源由冻结refs定义。完整当前性、Prompt保存、授权预约、提交/观察/候选保全都在本owner |
| adoption `selection-adoption.ts` | 现有reportOf/reviewCandidate/adopt/取消/ack及只读selection身份 | 下游订阅生成候选，补确定性report失败可见；AI按需，不能自动采用。看到的ID＋原report/attempt/selection版本一起交采用事务 |
| delivery `review-delivery.ts` | 现有整套检查/gate/交付与项目ZIP命令 | 单快照项目包；交付消费原采用/候选/原动作冻结Prompt，重验现有围栏。不从DOM组manifest、不以空集绿项证明套图合格 |
| session / workspace / 四个views | 生命周期装配、订阅、局部导航、DOM/草稿/URL | 保持单向装配和释放；新布局复用owner，不机械切大文件。项目state仅派生缓存，业务硬门读真实记录，不把视图导航当商品状态 |
| gateway / 两个Image Adapter | 继续现有SubmitRequest与有限registry/Transport | 不加mask/negative_prompt/seed/新模型或另一编辑API；本次双模式是实际参考输入与Prompt不同，模型仍输出新整图。网关无业务持久化 |

`ReworkIntent`保留projectId/generation/shotId/所见Prompt/来源fence/有效profile/编译预览，并明确分为 `problemCandidate: {candidateId,documentId,version,assetSha256}`、`mode`、`references`（下节）和 `promptChoice`。不把问题候选ID当模型源，不回调DOM重新读取摘要。只读投影携带四个身份及已有忙碌/错误；来源不可见/不在原项目/Blob缺失或hash不符返回blocked，零POST，不回退别图。

Scope模式仍是原initial/failed_retry/explicit_new/rework，不另建队列。准备读/编译不持久化或收费；确认重验原所见意图和完整候选/输入/配置，按原事务授权消费/OCC预约每图action。已预约/Unknown不能另发；停止只停后续新增，已发送的原任务继续有限观察/保存。双击、跨tab和换项目复用原同领域围栏；旧action晚到仍按原项目保全。

### 13.6 双模式返工与真正模型输入

| 模式 | 实际图像及顺序 | Prompt语义与结果承诺 |
|---|---|---|
| edit_candidate（默认） | 第1项为固定问题候选的原Blob；后续为本图消费的商品原参考依据 | 指明每图用途、具体问题位置/现象、允许修改和满意部分；原商品事实优先，候选幻觉可修。输出一张新整图，**不承诺未改像素完全不变** |
| regenerate_original（另选） | 仅本图商品原参考依据，不发送历史候选图 | 重新表达完整目标；问题候选只是诊断记录，界面标“模型来源：商品原照”，不能冒充局部编辑 |

在现有 `PromptReferenceSelection`／冻结request.references中增加非秘密语义元数据：`uses: ("edit_source" | "product_truth" | "style_reference")[]`（非空、不重复），`sources: {kind: "candidate" | "product_input", document_id: string, version: number, asset_sha256: string}[]`（version正整数，hash为64位小写SHA256，所属project由意图固定）；数组顺序即模型图序。其他既有sha256/media_type/角色字段继续消费。候选的传输role使用当前有限词表中的`other`，**role不是编辑含义**；语义由uses/来源与实际Prompt共同表达，不增加商品上传角色或谎称原ReferenceRole已包含编辑模式。

模型输入构造规则：

1. 从原项目确切记录读取候选Blob和商品依据；验证来源与媒体类型/字节/hash。先放编辑源，再依照现有本图绑定顺序放商品依据。相同字节合并为一次实际输入，uses/sources保留双用途，文字图号按合并后的顺序编译；不复制新的候选资产。
2. 最多实际3图、单张≤当前profile的10MiB，PNG/JPEG及尺寸/字符限制取当前有效profile。编辑源占一位；商品依据超容量时阻断并让用户选择本图必要依据，不悄悄裁图/丢商品约束/换模型。无候选/能力不允许参考输入则禁编辑并说明原因；原照重生成须人明确选，不能自动降级。
3. `.uses/.sources/mode`只进入项目内冻结/摘要/归因链，不直接当供应商字段。网关POST继续白名单：action_id、prompt、references（role/media_type/sha256/data_base64）、size、n=1、prompt_extend=false、watermark=false、output_format=png、model_id、target与credential_source；不偷偷加seed。
4. 两模式均用既有两个Image Adapter：Qwen把按序data URL图放在user.content前段，单text在末尾；parameters实际仅size/n/prompt_extend/watermark（未设置seed则不发）。Ark用按序image数组＋prompt、size从`*`映射`x`、response_format=b64_json、output_format=png、watermark=false。二者body不要求字节同形，也不凭网关字段声称Qwen额外发送了output_format。
5. 模式、问题候选、实际图序/用途/hash、Prompt来源/文本、配置或真实输入basis变化使旧预览失效。仅新候选晚到不偷换已固定源；其原件仍在且所消费依据不变时，旧源可以继续作为此次返工依据。

人工全文：默认不覆盖。当前为人工稿时，准备返回需要明确选择的投影：“保留人工全文并核对本次模式/图序”或“使用系统返工稿，保留原人工历史”。未选不外发；人工模式的实际新全文由用户在高级入口看过并明确确认，系统不暗加/改正文。普通系统路线不用进入高级编辑。确认后追加新Prompt版本，原人工版本/草稿不删；所见之后basis变更返回stale。若Prompt已追加、后续预约失败，返回实际已存ref并零新POST，不能伪称零写或删除历史。

### 13.7 五条路径：正常、失败、并发与恢复

| 路径 | 前置与正常后置 | 失败/并发/恢复 | 正式消费者上的验收动作 |
|---|---|---|---|
| 输入与确认 | 原照/资料保存；只确认当前来源、相关事实及必要展示决定；方案能解释每图依据 | 不可读图不入库；容量/保存/OCC失败保留稿；旧分析不套新输入，Unknown不默认重分析。重开读已保存事实，未保存稿不冒称已存 | 上传真实本地字节→填资料→人工/显式AI提议→确认→改已确认值；看实际记录/Prompt前进且真人工稿保护、无额外POST；无尺寸只阻对应图 |
| 生成及部分失败 | 方案/Prompt/profile当前；用户看actual scope一次确认；每图一个action，新候选不自动采用 | 一图失败不删其它成功；Unknown只观察原任务；双击/跨tab不重复消费；停新增仍保全已发结果。关闭后未确证提交结果为Unknown，不能保证后台继续 | 勾选明确范围→看摘要/图序/次数→确认；替身制造成功+明确失败+Unknown，成功即看/采用；核准确POST、action、Blob与无自动重提；排除理由对应每图 |
| 双模式指定返工 | 从实际查看候选启动，默认编辑；源/草稿/模式冻结；确认只影响该shot | 缺源/字节/超限/手工稿未选/旧意图/在途均阻断；换模式须重看；晚到不改源/旧采用。失败保留旧候选和采用，恢复原记录 | 同一shot先编辑、再明确原照重生成；独立核Adapter解码图hash与顺序，编辑含候选/原照，重生成不含候选；核无关shot文档/Blob逐条不变；取消/过期/双击零额外POST |
| 采用与交付 | 确定性report已就绪、无硬阻断；人工采用看到的候选；交付只消费采用与原动作冻结Prompt | 报告保存失败保全图片/旧采用并禁越硬门；新候选/新Prompt不自动换选。构包期间输入/采用/report变动按现有围栏失败，不下载假成功 | 查看v1、采用v2时点v1动作确实操作v1；只采用已看到的合法对象→明确检查→真实交付ZIP；解包核图片原字节、manifest原冻结Prompt，AI未跑如实标记 |
| 刷新与恢复 | 原生项目ZIP是完整一致只读快照，含原图/候选/文档历史和非秘密来源 | 坏包/未知schema/hash错/容量失败不半导入覆盖；DB或报告恢复错误可见。BYOK只内存，重开为空；在途/Unknown不自动另发；唯一恢复包不清 | 实际下载完整包→独立空profile同版本导入→刷新/重开；逐文档身份/version/payload和Blob字节精确匹配；再指定返工/采用/两包导出，新增历史单独计，不能要求整个ZIP追加后仍同hash |

后置的读取只能取真实消费者产物；直接播种候选只可用于精确故障反例，不代替普通用户全链。正式fake链仍必须真的点击/上传/保存/下载/导入，不拿内存原型签业务验收。原 `walk_to_adoption/walk_to_deliver`、6_2/6_3/5_3/5_4及对应domain消费者是资产，按前提复用，不另建第二套walk。

返工提交关闭面板时，把焦点归属记录在禁用提交控件之前；原项目/图/候选仍当前、且用户未将焦点移到别处时，收起后回到可见返工入口，不把焦点留在body，也不因晚到结果抢走其它控件的焦点。取消与新结果保持原查看对象/精确草稿的既有合同不变。

### 13.8 最终成品：唯一现行合同，不维护历史数据兼容

用户“不用考虑历史兼容性、移除被替代路径”的既有决定已记录于项目上下文SEL-018，2026-10-21又明确“以最终成品为准不用考虑历史数据兼容，该删就删”。原先按旧/新schema分支继续读取历史、要求旧项目在新产品完整显示的设计已经违背该既有决定，并非本次用户才提出新要求。本节直接替换冲突口径，与已修正的SEL-018及计划§17.13一致；先前由助手维护的设计不是用户要求兼容的依据，正式发布也不自动重开兼容承诺。当前产品仍停工，本次修订不代表代码已按此清退。

最终产品的新写者、读者、parser、类型、构建和实际消费者采用同一套现行合同。必要消费者同组切换后，删除被替代的版本分支、读投影、补缺省、别名/re-export、旧执行入口及其专属测试/配置；不双写，不为旧客户端或旧项目包维护适配，也不建设历史迁移服务。具体版本只取当前领域合同与对应消费者，不让本节复制一份会过时的版本号清单。

最终成品自身仍须完成当前格式项目的保存、下载、独立导入、刷新及两包原字节一致性；不支持的输入显式原子拒绝，不部分入仓或静默删字段。若最终交付素材需要一次性整理为现行合同，必须说明其真实来源和转换，不改写原冻结Prompt/实际请求，不补造执行身份或调用结果，不以恢复历史兼容作为完成途径。

用户原件、合法素材许可、原始失败/Unknown、费用/预留及必要源码/回退证据按其用途保全；保存这些非运行证据不要求现行产品解析旧格式。正常观察当前任务仍使用其冻结模型/protocol/目标，不自动重提Unknown；不借清理删除无关用户数据、清空账本或重置授权。项目存储、索引和网关不为兼容另增平行结构。

### 13.9 Prompt归因与真实品质标准

**不能普遍证明“不是Prompt不好”。** 核对四层：用户真实意图/证据 → 本地编译与实际DOM → 浏览器冻结body及Adapter真实出站 → 原始返回像素。hash一致只证明身份/完整性，不证明表达充分有效；HTTP、Schema、自评和替身图片都不证明成品可用。

系统先把用途、展示目标与普通风格选择组织成**协调的视觉简报**：画面概念与视觉主次、主体大小/位置/视角和留白、背景及材质/光线、配色与整套一致性；有获确认印字时再确定文字层级、分组/准确原文及其与图像的位置关系。镜头、光照和排版的专业表达由系统承担，不要求普通用户逐项填写术语；不是只拼接事实字段与一串“禁止”。

随后明确商品依据图号、证据支持的视角、允许变化/永久保持、准确印字与数量、尺寸轴/数值/单位及对应对象，让创作方向在事实/平台边界内成立。照片有临时残留且目标清洁时明确例外，不能同时要求保留全部状态又去污；永久涂层/损伤/标识不擅改，未确认内容不变成事实。

评审样稿标明来源是**程序编译、用户手工修改还是专家全文替换**，并保留实际输入/版本/所发Prompt对应。专家对照可以定位表达不足，其成功不能签程序编译能力；程序稿须由普通输入在正式入口产生，再核实际出站及原像素，不能拿设计示例或约束齐全代替品质。

尺寸图有已确认结构化尺寸时，“无额外文案”不等于禁止尺寸标签：仅开放这些尺寸的数值、单位与对应对象标签；另有已确认文案时两者并列允许，不能用“只允许以下文案”反向禁掉尺寸。无尺寸依据不开放该例外，主图仍禁止新增印字。输出图片的像素宽高/文件格式属于请求参数，不得与商品物理尺寸混称。这只消除编译约束冲突，不保证模型箭头绑定正确；最终仍逐图核对原像素。

尺寸用途可以采用明确对象/轴向/数值/单位的参数清单，不强制每张都绘制箭头；图中只要使用尺寸线就必须真实绑定对应对象与轴向。不能用正确数字掩盖错误箭头，也不能因取消尺寸线丢失公称/实测来源区分或任一尺寸参数。

**编译样稿与段落模板（未调用模型）**。以杯子清洁主图为例，前置是用户确已确认杯内相关区域为临时饮品残留、选洗净倒空、商品依据支持该视角；不能仅凭照片深色区域作此前置。编译器按本图实际refs生成图号，不从模板固定“图1总是商品原照”。正常无字主图的系统完整表达至少包含：

```text
任务：制作亚马逊美国站商品主图，输出一张完整图片，不是拼贴或对比页。
输入依据：图1为商品原参考图，提供同一商品的可见形状、结构、涂层、纹理与标识依据。
商品保持：保留参考商品真实轮廓、比例、可见结构、永久涂层/纹理/损伤及已有标识；不要增加附件、部件、花纹、文字或性能。
本次展示变化：仅清除用户已确认的临时饮品残留并倒空，呈现清洁空杯；永久材质/涂层不是污渍，不得清除。不能把清洁展示变成新品或无损承诺。
视角：沿用商品依据中可证的可见视角，不凭空补背面/内部结构。
画面：单一商品、纯白背景、柔和自然光，主体足够大且完整入画；不裁断商品，不以夸张透视改变比例。
图中文字：不新增任何印字/营销文案/标签；商品本来存在的标识按商品依据保留，不补造看不清的字。
```

编辑模式仅以实际图序替换“输入依据”和“本次展示变化”两段：明确“图1是本次要修的候选，不是商品事实权威；图2是商品原照、约束真实商品”，再列用户具体方向、要保留的满意构图与应修位置；其他段仍按实际用途/事实编译。原照重生成不保留“编辑图1”语句。系统不把问题类别、行政角色标题或引号内摄影指令当实际印字；只有confirmed on_image_texts逐项进入独立印字段，品牌/数值/单位不擅自改写。样稿是可执行编译语义参考，不是测试必须逐字钉住的实现字符串；效果结论仍需下述真实对照。

实际出站的证明复用可注入Transport和正式registry/Adapter，在内存精确比较Prompt/参数以及**解码图片**的hash/顺序；持久证据只存非秘密字段、引用/布尔相等后置和许可输出原字节。禁止Authorization/key/key-hash/签名URL/整份Base64日志，不增加生产遥测平台。Qwen当前明确prompt_extend=false，官方默认true不是当前行为；浏览器未发seed，不宣称已经同seed控制。官方边界见 `evals/product-v2/next-version-design/prompt-guidance-20261012.md`，不把Seedream家族宣传当flash精确能力或品质。

未来获批的最小真实对照：同一具体失败单图A=实际系统Prompt，B=同事实/目的/原图的专家明确表达，**只改Prompt**；冻结准确模型/Adapter/地域、图片字节与顺序、尺寸、n=1、水印/改写及代码身份。增加角度/事实/清洗参考/换模型是另一试验，不能混记措辞收益。可设置同seed也不保证完全复现；缺省则如实记，交错组别。建议每组2–3张共4–6次仅作方向判断；额度只许各1张就报告个案，不宣称稳定成功率/显著性。

预先逐图判据：目标状态（如洗净倒空）满足；轮廓/比例/永久纹理/标识保真；无新增部件/标识/未经确认性能；背景/主体构图符合所见目标。带字逐字对照获确认原文，尺寸逐数值/单位/箭头对象对照证据；任何事实错误不因美观抵消。评价隐藏Prompt组别，保留全部收费原结果及问题位置/理由，不只挑一张。B反复更好支持系统表达可改善；两组都失败仍不能排除Prompt问题。真实视觉质量未在本次0预算中证明，不签成功率/模型上限。

### 13.10 验证、确认与验收：按风险复用，不频繁造探针

Verification核实现合同；Validation核真实用户目的；Acceptance按明示准出接收，三者不互相代签。必要测试的保留/合并/删除、永久回归与一次性smoke/本次运行的区分唯一按AGENTS Testing Guidelines；具体清理与已查重复入口归Issue #7，全面改造承接Issue #10。下表只映射变更到既有消费者，不是每批全跑清单。

| 改变的前提 | 最小复用门 | 不变时不重做 |
|---|---|---|
| 类型/TS源 | check:types＋build:frontend＋build:frontend-node，实际消费者smoke | 全库所有浏览器套件 |
| 展示决定/编译/refs/版本合同 | 现有specs/prompt/rework/confirm/attempt业务测试；相同非法值同时过生产parser；相关正式页面/Transport后置 | 新源码字符串/文案/转发/mock回声测试 |
| 授权/采用/报告/ZIP/OCC | 对应现有真实事务消费者，边界/跨tab/晚到/故障及原生包核对 | 改一段布局即重新买模型或两轮全量 |
| 视图层级/草稿/焦点 | 实际Chrome无头表面用真实长内容核主动作/视觉层级、精确对象、反馈/恢复、键盘/部分成功；页面级非预期横向溢出与关键控制遮挡必须解释/修正 | 只跑类型、空数据布局或用Screenshot数量代替易用性；不能将工程人因问题全推到C15/C17 |
| 当前入口/文件清退/上下文 | 实际调用闭包、原字节、受影响CLI/文档/正式主链/恢复；登记变更才跑原登记守卫 | 再造退休框架、盲删历史原材料 |
| 真品质或完整原工程准出 | 分别真实像素受控对照、原计划固定最终门/C15/C17 | fake/原型/过去另项目/早于最后修改的green |

局部先用受影响的既有门证明改变路径；完整回归的扩大条件和最终两轮只取计划§15.3。稳定的现有行为资产默认复用，前提未变不重新审计/重写全部测试；同一probe不等于同前提同风险。仅规则/协议/parser变更才补相应合同反例，纯布局/焦点不强制查IDB/模型/ZIP。失败处理、证据复用及删除实现绑定断言按AGENTS，不另造平台；真实任务走查不能被技术字段关键词扫描替代。

### 13.11 重构、清退与上下文维护的实施次序

详细逐包输入/依赖、原子交接、验收和失败恢复取权威计划§17，当前用户纠偏先读§17.13；以下为设计原则，不是另一套轮数/启动权威。原生Goal观察全文只在计划§2.1，§17.8仅为编制历史入口。

1. 复用当前单向owner及FastAPI/Vite/lit-html/既有测试组织，只修本次实际残余；按状态所有权/副作用/变化耦合取舍，不按行数拆helper，不重做原迁移。手写源码经当前标准构建消费，不照抄旧同目录生成JS操作。
2. V1及旧专属治理消费者已随main基线退出，直接承接#10相应证据；只有新改动重新引入活路径或影响既有必要用途时才核该差量。用户原件、JSON/Blob、真人记录、许可、账本、失败与唯一恢复包保留，不照搬旧两个验证器/pre-V1槽卡清退指令或整包WIP删除表。
3. 按计划当前包完成普通决定→系统表达→实际引用→两模式→采用→两包的一条早期竖向，必要正式UI与业务合同同组验证，不把人因全部留到业务层做完。新读写者、owner命令、view和历史/包消费者闭合后才交付，不能留下两份活编排；五路径和五用途完整终点不缩减。
4. UI只替换已确定任务层级，不换栈/平台，不新增账户、云项目库、Agent、通用调度/验证/遥测。删除被替代的旧重复列表、字段默认印字与返工拼接入口；不能把删除留成下一轮。
5. 维护现有INDEX/design/discussion等单一入口，当前说明取代过时说明；历史原文保存在既有证据/可达原字节，不再每轮加一份“当前计划”。原型原字节归档供复盘/复现，实验宿主及活原型壳退出工作入口，不进产品。

### 13.12 已决方向与交付边界

无需用户再制定人因/测试标准或挑删除清单。方向已明确为直接整图、必要普通选择、显式上图文字、四段导航/唯一底层状态、左列表＋常驻精看骨架、默认候选编辑＋原照重生成、有限既有Adapter/相同网关字段与数据历史保全。具体信息层级/桌面与滚动策略取本次修订§13.3，不再把13号原型细节当冻结成品；正常/失败/并发/恢复合同仍成立。B/C是实验资产，不是待实施者选择的产品模式。

复工及准出按最新用户授权、真实Goal/state及范围匹配证据；设计完成不解除原生门。本次已批准额度/模型/提交发布按现有门执行，不重复索权；超额、新模型/重大依赖、不可逆数据或整体架构变化才升级。既有真实成品/机制按未变前提复用，其范围外的编译/人因/最终工程/线上缺口仍未通过。独立设计、局部本地结果、完整工程、实际发布与C15/C17分别报告。

### 13.13 生图业务语义与核心合同（2026-10-18设计准备候选）

本节及§13.14–15来自2026-10-18设计准备，[Issue #17](https://github.com/JusticeSc/listing-kit/issues/17)保留该轮协作，具体产品工作归#9/#8。它们补充§13.4–9的业务含义，不重定终点/正式依赖或冻结另一套字段/API。该轮paused/不施工/零调用只描述当时权限；当前授权与原生门取计划§17.13/state。纸面样本不证明程序实现，主图/信息图/尺寸图三例不将五用途成品缩成三图；已交付#9零收费切片从PR #18承接。

#### 13.13.1 术语、责任与不变量

| 业务概念 | 含义与唯一归属 | 不得混淆 |
|---|---|---|
| 商品事实 | 有来源、确认状态与精确版本的商品属性/观察，仍归现有inputs/FactSlot；ProductBrief只作投影 | 模型猜测、创作建议、照片文件名均不是已确认事实 |
| 展示决定 | 用户对本次展示的要求，例如清洁空杯、沿用已证视角；共用默认归StyleSpec，单图覆盖归ShotSpec | “洗净展示”不证明新品、无损；决定不改变商品原物性 |
| 创作方案 | 在事实/决定范围内组织沟通目标、构图、环境、光照、配色、文案层级的可修改建议，保存的决定仍归现有规格 | 不是模型自由补商品事实，也不是要求用户逐项填写摄影参数 |
| 视觉简报 | 针对一张图的有效事实、展示决定与创作方案的协调投影，由prompts内部组织并供预览/编译共同消费 | 不新增可独立编辑的第二份事实库或持久化万能ImageSpec；不等同最终Prompt |
| 实际请求 | 给定有效profile与确定图序后，由现有编译路径产生的文本、参数及精确来源，归Prompt版本链；generation按所见快照消费 | 摘要不能另写一份近似文本；同一语义跨模型不承诺等效效果 |
| 参考图职责 | 输入图用于商品依据、风格依据或编辑源，语义及来源按§13.6冻结；图号只由实际最终数组决定 | 上传role不等于业务用途；裁切不是新拍摄角度；候选不是商品事实权威 |
| 问题候选/编辑源 | 前者是人指出问题的确切候选，后者是实际送模型的图片；两模式关系取§13.6 | 传candidateId不等于送了图片；原照重生成不能声称在编辑未发送的候选 |
| 采用与交付 | 人工选择一个确切候选；交付只读该候选原动作和冻结请求 | 查看、生成成功、AI报告均不自动采用；当前Prompt头不替代原动作历史 |

原则：先横向覆盖关系与主要异常，再优先深入会推翻方案的高风险问题；不是把全部详细协议写完才验证。保留现有单一owner与窄Interface，不新建总编排器、DSL、任务调度或模型平台。

#### 13.13.2 完整业务链的输入、输出与状态

下列状态描述业务条件，不新增一套项目状态机或把页面导航当持久化状态；执行状态、OCC、Unknown与恢复仍使用§13.5–8及既有领域判据。

| 环节/owner | 输入→输出 | 进入下一环节的条件；异常与恢复 |
|---|---|---|
| 商品依据/inputs | 原图、用户资料、可选模型提议→有来源的事实与必要问题 | 只确认实际看过的来源；提议待审、缺证/冲突不默默填值。非相关缺项不锁整项目 |
| 套图方案/inputs | 销售沟通目标、证据、用途→每图任务与共用风格 | 每张图说清要让买家理解什么及依据；不为凑张数造包装、性能、尺寸或对比 |
| 单图方案/inputs→prompts | 共用决定＋单图覆盖＋绑定事实/文案/图→有效视觉简报 | 必要决定已明确、结构冲突已处理。选择与硬约束相撞时解释冲突，不静默替换用户目标 |
| 本地准备/prompts | 简报＋有效profile＋规范化图序→系统Prompt与缺项/限制 | 确定性、零模型调用；缺项定位到对应图/来源。人工全文不覆盖，按既有显式选择处理 |
| 摘要与发送/generation | 当前Prompt/引用、实际范围/目标→所见摘要→授权预约与固定请求 | 内容或图序改变必须重看；费用上界未核则不声称0。准备不是外发授权，stale/超限零新增POST |
| 结果与审图/generation→adoption | 原动作的结果字节→候选、报告、问题定位 | 成功图可先看；明确失败可由人决定下一动作，Unknown核原任务不自动另发；迟到结果不换查看对象/采用 |
| 修改/generation→prompts | 固定问题候选＋普通方向＋明确模式→本图新请求 | 编辑源/保留项/改变项明确；缺字节/不支持/超限阻断。取消保留稿，新候选不自动采用 |
| 采用/交付/adoption→delivery | 确切候选及必要报告→人工选择→交付包/完整项目包 | 既有硬门和一致快照成立；相关事实改变只使受影响结果过期，不改写旧图/原请求；失败不下载假成功 |

#### 13.13.3 简报的有效值、继承与冲突

1. **先决定图的沟通任务，再决定画面**。套图只保存共用风格/展示默认一次；单图描述用途与例外，允许不同任务采用不同布局。风格统一不等于每张图同构图、同一段Prompt。
2. **明确区分“继承”“明确无”“未确定”**。单图没有覆盖才继承共用值；用户明确无文字/无道具不是空字段待补；必要展示项未确定按§13.4阻断该图。字段的具体编码到实现时按现有schema统一，不用空字符串承担三种语义。
3. **约束不是静默覆盖规则**。商品依据和平台/能力硬约束不能被创意盖掉；明确用户要求优先于系统创意建议，单图显式覆盖优先于共用建议。两条明确要求冲突时返回具体问题，不能简单按“后一条赢”继续发送。已知结构矛盾可确定性识别，自由文本的完整语义冲突仍需人核对，不承诺万能检测。
4. **必要选择而非专业考试**。用户只补会改变目标且无法从当前确认得到的决定；一般背景/光照/构图由系统给协调建议，预览可改，发送前统一确认，不逐项弹窗。不发明“只有填写全部摄影参数才就绪”的新门。
5. **文案与事实分离但可追溯**。只将明确选择的confirmed文案放进印字段；允许来自已确认事实的用户/模型文案提议按§13.4人工确认，不要求广告标题字面等于某个原事实值。数字、单位、品牌及维度映射不能创作改写。删去某项印字不等于删商品本体已有标识。
6. **版本按消费关系失效**。共用风格改变只影响真正继承该值的图；无关尺寸/候选新增不锁不消费它们的主图。改变已消费事实、文案、参考图序、修改源、目标profile或编译规则，则按既有当前性判据使相应预览待更新；已接受的历史请求不被重写。
7. **新文案选择替代旧自动枚举**，不是在枚举后再追加标题。无新增文字是明确决定；未作选择且本图目标需要文字时是待处理项，不能回退自动打印全部绑定事实。`origin=reuse`也须保留原文、精确事实DocumentRef及确认状态，不绕过当前性/语言提示。引用精确版本而非只存slot_id；上游事实改变后文案待核对，不跟随最新值悄悄改字。
8. **共用视角是默认而非证据**。允许共用“沿用各图有依据的视角”，单图显式选择正/侧/顶视时逐图检查支持依据，不把一张整体照片推为所有视角合法。共享状态不锁无关用途；不可支持的单图视角仍由该图补证/改选。
9. **推荐与保存仍是一条规则链**。`suite-plan`计算只读建议，用户选择后由inputs沿既有保存/OCC写正式方案；不新增第二套推荐算法，也不在读投影时悄悄seed/覆盖用户方案。已保存方案不会因重新打开建议而自动改选。

**尺寸文案的必要细化**：尺寸权威仍是已确认`size_dimensions`的结构化measurement列表，不另建三个自由文本数字事实。每个尺寸文案除精确FactSlot DocumentRef，还必须绑定该版本的具体measurement索引；源版本固定后索引才稳定。由所选measurement的object/axis/value/unit确定性形成数值部分，英文对象/轴向标签须有明确确认的映射；该映射归对应ShotSpec文案项并随来源版本保存，不新增独立翻译表或事实库。校验这些值与引用项相符，不只查“来源存在”。同一源版本内换索引或错配对象/单位即拒绝，列表编辑/重排后旧绑定过期重核，不按当前索引悄悄接新值。

来源标签作为绑定所选measurement的明确文案项，来源精确到同一FactSlot版本及测量项集合，仍归ShotSpec文案链，不伪造值为“Measured”的商品事实。候选只开放人工对照各项`source_basis`确认后的`Measured`（实测）/`Nominal`（公称）两种标签；程序不从自由文本猜类别、模型不自动确认。统一标签要求所覆盖各项来源类别一致，混合来源须逐项标注并重新确认，未知来源返回补证而非随意选标签。来源改变使该标签与相关文案过期；确认原文、measurement绑定及分类一起进入摘要/冻结来源。此绑定/标签细化是下一版文案parser的真实差量，不声称当前main已支持；Schema合法仍不能证明人确认的量测真实。

简报的最小语义包含：本图目标、主体与展示状态、实际依据职责、画面构图/环境/光照/风格、确切印字及布局、保持/允许变化。按用途选必要项，不统一填满字段。派生简报不单独保存；新增表达以既有规格的实际缺口为依据。若编译规则更新会改变正文，须让受影响系统稿重新准备并重看摘要，同时保护人工稿和旧版本；具体schema同包切换仍取§13.8。

#### 13.13.4 创作、编译与传输的分工

- **创作规划**：先以现有用途规则和风格/单图规格补出协调的正向画面，不把一串禁止当设计。普通自由表达作为意图保留；当前代码不能证明能自动理解任意“高级感”等词。需要模型辅助时，只通过明确的辅助动作提出可改方案，冻结其来源后进入同一规格链；不在compile或发送点击中隐藏调用/重试。创作辅助接口与费用尚未批准，本候选不预定新端点、模型或依赖；人工/本地路线必须可用。
- **唯一语义编译**：在现有`domain/prompt.js`/`prompts.ts`内部，从同一有效简报生成预览和最终自然语言。固定输入＋选定方案＋规则/profile得到固定文本与参数；空缺不能由发送时重新随机创作填上。专业指令、精确印字、输出参数分开，不把所有引用事实自动印上图。
- **引用规范化先于文字图号**：读取本图明确选择，验证字节/来源，按§13.6放编辑源、合并同字节多职责，再按最终数组生成图号和摘要；输入超限返回问题，不悄悄截前三张。风格图只取视觉语言，不将其物体/文字当本商品证据。仅切对照视图不改发送集合。
- **冻结比较完整业务含义**：新请求的mode、规范化references的顺序/role/hash/uses/sources和精确文案来源均参与相应冻结身份与当前性，不退回只比较role/hash。候选与商品依据同字节时保留编辑源第一位，传输role取`other`，合并两种uses及来源；商品权威仍由product_truth来源表达，不因role改变丢失。历史记录不补造mode/元数据、不重新计算其原hash，新动作按新合同重新准备，旧版本显示与支持范围仍取§13.8，不扩大旧包迁移承诺。
- **现有Adapter只做真实协议适配**：浏览器编译器消费有效能力profile，Python侧有限两个Adapter映射传输和同步/异步结果；不各自重写业务含义，不给不支持的参数找“近似替代”。若未来确有模型表达差异，先用实际样本证明，再在同一编译入口处理有限差异，不预建N套模型编译器。
- **不足能力显式阻断**：参考图数量/格式、尺寸、文字长度等按实际profile判断，给出“减选本图依据/选择支持尺寸/明确换模式”等动作。用户改选会形成新预览；本轮不自动降级、拆成付费多步、换模型或切合成工作流。Prompt中的“保持一致”只表达要求，不保证像素一致。

### 13.14 三个完整纸面实例与反例

**以下全部是设计演算，不是程序输出、真实调用或素材准入证据。** 使用同一个虚构陶瓷杯任务，便于检查共用与例外；不对应原型杯子的真实材质/尺寸，严禁把这些教学值写入用户项目或当既有事实。R1/R2、F1–F4、T1–T4只是纸面别名，不是伪造DocumentRef/hash/action_id；真实执行必须从库读取精确记录、原Blob并计算真实身份。

#### 13.14.1 三例共用的输入、图序与参数

- 假设的已确认资料：F1“陶瓷马克杯”；D是一条已确认`size_dimensions`的结构化测量数组。纸面别名F2=D该版本索引0：`object=杯身（杯底至杯沿）, axis=height, value=95, unit=mm`；F3=索引1：`object=杯口外缘, axis=diameter, value=80, unit=mm`；F4=索引2：`object=杯体含把手, axis=width, value=115, unit=mm`。三项`source_basis`均假设为用户提供并确认的实测记录，不是官方公称；F2–F4不是三条任意文本FactSlot。没有这些资料时尺寸例走缺证分支，不能由照片估计。
- 假设的商品图：R1是一张能看到杯口和把手的整体原照；R2是R1把手区域的裁切，独立图片字节但同一拍摄来源，只补局部可见细节、不支持另一视角。用户已确认杯内指定区域是临时饮品残留而非永久涂层；永久纹理/标识仍按可见依据保留。
- 共用普通选择：“洗净、倒空；沿用有依据的视角；清楚、自然、不过度修饰”。这是展示意图，不是新品或无损事实。后续三例都消费该决定，只问一次。
- 示例选择当前已有`dashscope-qwen-image`/`qwen-image-3.0`目标；纸面假定当次有效profile接受`size=1024*1024`。三例均`n=1`、`prompt_extend=false`、`watermark=false`，网关期望PNG；未设置seed、独立negative_prompt或采样器。真实尺寸/格式须以当次profile为准，不能靠这份纸面例放行。
- 三例初始请求的实际图序均为`[R1,R2]`，职责均是product_truth；R2不因传输role为detail就被理解为新角度。R1/R2非同字节，不合并。字节相同则按§13.6合并且重算图号，不能继续引用不存在的图2。
- 下文每个代码块是该例完整预期Prompt正文；共用参数在本项定义，图序明确，不在各例偷偷添图或参数。真实API仍需真实action_id、来源/hash、target与原凭据通道，按既有合同构造，不用纸面假值发送。费用本轮未重新核价，未授权外发，不能显示“免费/0元”。

#### 13.14.2 主图：把清洁意图转成明确展示

**普通输入**：“做一张干净的商品主图，杯型别变。”已明确的清洁空杯不重问；未确认时只问是否洗净/倒空，不推用户写摄影Prompt。主图明确无新增文案，不读取F2–F4作印字。

**有效简报**：目标是看清商品整体；单一主体、已有视角、纯白背景、柔和棚光与自然接触阴影；满足适用主图占比且完整入画。依据是F1及R1/R2，共用清洁决定生效；构图与光照是可修改建议，不是商品事实。

```text
制作一张亚马逊美国站商品主图，表现同一只陶瓷马克杯，不做拼贴或前后对比。
图1为商品整体原照，约束杯身、杯口、把手的真实轮廓、比例、可见纹理与标识；图2为图1的把手局部裁切，只用于核对该处可见细节，不代表另一拍摄角度。不要继承原照桌面或背景。
按用户已确认的展示决定，清除指定杯内临时饮品残留并倒空，呈现清洁空杯。只改变这些临时状态；永久涂层、纹理、损伤和已有标识按商品依据保留，不将清洁处理解释为新品或无损。
沿用图1能支持的视角，清楚看到杯口与把手；保持商品真实比例。商品作为唯一主体，足够大并满足主图占比，杯口、杯底及把手完整入画，四周保留必要边距。
采用纯白无缝背景，柔和中性棚光和轻微自然接触阴影，真实表现表面质感，不用过曝抹掉边缘，也不凭空增加不可见结构或花纹。
不新增任何标题、尺寸标签、营销文字、道具、水印或装饰边框；商品本体可见标识按依据保留，不补造看不清的字。
输出一张1024×1024像素的完整正方形图片。
```

**检查与分支**：若用户随后为单图明确选择顶视，而R1无法支持该视角，返回“补充对应视角/沿用已证视角/暂不做该图”，不能生成想象内部；这不改变本例初始沿用已证视角的决定。D尺寸变动不应使此主图失效；共用清洁决定或R1改变则须更新预览。图片最终仍检查杯型、残留、边缘/比例与完整构图，不能凭“保留外形”字样签保真。

#### 13.14.3 信息图：准确文案与画面层级

**普通输入**：“展示杯子的样子，标题用‘CERAMIC MUG’，不要加功能卖点。”T1是用户明确选择、确认的英文标题，源于F1的商品类别；T1原文与来源绑定并标user，不由编译器现场翻译。此例不印尺寸，不把“好看”扩成耐热/食品级等未证性能。

**有效简报**：先看商品，再读一个标题；主体在左侧约三分之二，右侧留出标题空间；温和浅灰白背景、深灰无衬线标题，中性光线与主图协调。R1/R2只约束商品外形，不强行继承原照桌面。该布局是可改创作建议，不是要求用户手填比例。

本图有效ShotSpec应明确保持“商品可见外形与已确认标题T1”，允许背景/标题排版的本次创作选择；不继承当前infographic角色的“已确认卖点文字”默认。实现时用途依赖与默认keep须按具体任务一起派生，不能只改推荐模板却把旧角色默认编进正文。

```text
制作一张电商商品信息图，用清楚的商品展示和一个标题说明这是一只陶瓷马克杯，不添加未经确认的功能卖点。
图1是同一商品整体外形依据，图2是从图1裁切的把手细节，只补充该处可见信息，不是新角度；保留真实杯型、杯口、把手比例及永久纹理/标识，不复制原照桌面和背景。
沿用图1有依据的视角，按已确认决定呈现洗净倒空状态，仅去除指定临时残留。杯子完整放在画面左侧约三分之二区域，杯口和把手可见；右侧保留干净留白，不用文字压住商品。
使用温和浅灰白背景、柔和中性棚光和自然阴影，商品边缘清楚，整套视觉保持自然不过度修饰。
新增印字仅有标题「CERAMIC MUG」，逐字准确、完整且只出现一次。放在右侧留白区，使用清晰深灰无衬线字体，字号以正方形成图缩略查看仍能辨认为目标；不加副标题、尺寸、性能图标或其他营销文案。
不改变商品永久特征，不增配件、花纹或看不清的标识；不添加水印、装饰边框或无关物体。
输出一张1024×1024像素的完整正方形图片。
```

**检查与分支**：T1未确认/来源过期时不偷偷删除标题继续发送，也不当场替用户翻译；返回处理项，用户可确认文案或明确选择无字方案，再看新摘要。主图无字不应被套用为“整套禁止新增文字”。真实成图须逐字核T1、标题次数与遮挡，并核是否出现未经确认的卖点。

#### 13.14.4 尺寸图：对象、轴向、数值和来源

**普通输入**：“把高度、杯口外径和带把手总宽标清楚。”本例D的三项均假设已确认实测。T2–T4是明确选择并确认的文案，分别绑定D精确版本的索引0/1/2及其对象/轴向：「Height: 95 mm」「Rim outer diameter: 80 mm」「Overall width incl. handle: 115 mm」。数值/单位由对应measurement确定性生成并校验，标签映射经人确认，不允许自由改数字；错把索引1的直径值配给高度应在编译时拒绝。来源标签「Measured」另作确认文案，绑定D同版本索引0–2，用户已逐项对照source_basis确认均为实测；不是无来源的第四条事实。

**有效简报**：用与主图一致的商品视角，左侧完整商品、右侧三行参数清单及来源标签；避免没有充分正交视角时用透视箭头制造测量假象。不强制尺寸线，三项都必须保留；参数清单不表示图像按比例绘制。此图明确覆盖“主图无新增印字”而非覆盖商品事实。

```text
制作一张商品尺寸信息图，清楚列出杯高、杯口外径、含把手总宽及其用户实测来源，不把输出像素尺寸当作商品尺寸。
图1为同一商品整体外形依据，图2是图1的把手裁切，仅核对局部外形，不提供另一视角或尺寸测量。商品尺寸只取已确认量测资料，不从照片比例推算。
杯子保持真实轮廓、结构、永久纹理与标识，按已确认决定洗净倒空；沿用图1可证视角，完整放在画面左侧，右侧留出整齐参数区。背景浅灰白、柔和中性棚光，与整套自然商品摄影协调。
右侧按从上到下顺序准确排印三行，每行只出现一次：
「Height: 95 mm」
「Rim outer diameter: 80 mm」
「Overall width incl. handle: 115 mm」
参数区下方另放一次来源标签「Measured」。新增印字只允许上述四项，保持英文拼写、数字、单位和对应关系，不增加公差、容量、性能或其他尺寸。
使用清晰深灰无衬线字体与足够行距，标签不遮挡商品。采用参数清单，不绘制尺寸箭头、标尺或暗示按比例绘制的辅助线。
不补造隐藏结构、配件、标识或装饰边框，不加水印。
输出一张1024×1024像素的完整正方形图片；这里的像素尺寸仅是输出规格。
```

**检查与分支**：F2–F4任一缺失、对象/单位不明或冲突，尺寸图返回对应补证项，不能估数、擅改成两项、静默换图或填占位数字；用户可明确调整该图目标/排除该图，其他已就绪用途不受牵连。若真实来源是官方公称，须使用对应确认标签，不沿用本例「Measured」。原像素逐行核数字/单位/对象及标签，三行都正确才不缺项；使用尺寸线的其他方案另核轴向和端点。

#### 13.14.5 修改、超限与人工稿的跨例检验

- 信息图出现文字压杯把手，人从正在看候选C2选择“修改这张，文字挪远些，其他构图保留”：编辑模式真实图序为`[C2,R1,R2]`。输入说明须改为“图1是待修候选，提供当前构图但不是事实权威；图2为商品整体依据，图3为其把手裁切”。保留T1、杯型及满意光线，只调整标题区域与商品间距；标题仍只印一次。正文以该模式/最终图号重新编译，不能在原两图正文后叠一句“修改图1”。
- 人明确选择“从原照重新生成”：图序回到`[R1,R2]`，表达完整信息图目标和新的文字间距要求；C2仅留作问题记录，不包含“保持图1候选构图”或假设模型看过C2。两模式均输出新整图，不保证未修改区域像素不变，原采用不动。
- 编辑模式若另选择第三张不同字节依据，合计四张而profile最多三张，返回超限并列实际输入；用户明确减选或换模式后重看摘要。不取前三张、不悄悄丢商品依据；只放大/切换对照图不改变发送选择。
- 存在人工全文时按§13.6明确选择，未选不发送。保留全文路线不暗插系统修改段；若用户全文尚未表达新图序/模式，应在高级入口核对。不得把人工稿与程序稿混记为同一种来源。
- 三例准备均零真实模型调用；文案/参考/决定在摘要之后改变，原预览stale、零新增POST。已经外发的请求仍按原身份保存结果；Unknown不因用户换模式而自动另发。

### 13.15 当前源码差量、风险与后续验证

#### 13.15.1 静态核对的复用落点

这是2026-10-18当前工作树的定向源码观察，不是运行或线上能力证明；封存WIP不作为已实现能力。行号仅用于本次定位，后续依实际源码。

| 当前源码/既有合同 | 已存在的基础 | 下一版实际差量 |
|---|---|---|
| `domain/brief.js:1–7,179–262` | 已确认事实的版本投影，不是另一事实库 | 不扩成万能创作对象；视觉简报从已有输入与规格派生 |
| `domain/specs.js:35–40,73–88,233–274`；§13.4 | 共用背景/光线/色调/构图/avoid及单图用途/keep/change_allowed/notes，角色默认keep/allow | presentation继承/覆盖、明确无字与confirmed文案来源等尚需同包落地；具体任务的默认keep/allow须与推荐依赖一起调整，类别介绍不继承“卖点文字”、清洁展示不被旧“只变背景”误锁 |
| `domain/suite-plan.js:189–222,752起` | 主图、卖点信息图、尺寸等模板及其用途依赖，已有推荐规则 | “信息图角色”不等于“卖点模板”；§13.14的类别介绍任务不能被迫填造signature_features。调整具体任务推荐/依赖以匹配沟通目标，真正卖点图仍须卖点依据；推荐到保存复用同一规则 |
| `domain/prompt.js:556–838`；`prompts.ts:139起` | 单一纯编译路径、用途/共用风格段落、basis与来源 | 在此内部组织协调视觉简报并消费决定；不用新平台或Python侧第二语义编译器 |
| `domain/prompt.js:333–350,432–553,653–760` | 字面引用、语言/泄漏/准确文字检查；当前按绑定事实印字 | 改为只印明确选择的confirmed文案，允许有来源且人工确认的译写；现有“原文必须逐字等于事实值”判据须同步调整，不能只添加字段就声称可用 |
| `domain/slots.js:88–90`、`shared.js:193–272`、`prompt.js:326–340` | 尺寸为size_dimensions内object/axis/value/unit/source_basis列表；当前factTexts不从结构测量生成文案 | 新尺寸文案绑定精确源版本＋measurement索引，由对应值/单位生成；确认对象标签映射，错配编译拒绝。来源标签绑定相同测量项、人工核source_basis分类，不新增无来源“Measured”事实，不假设旧literal校验能直接支持 |
| `domain/prompt.js:848–874`；`generation.ts:113,857–870`；§13.6 | 按role/hash选图、去重、构造实际字节 | 本图明确绑定与顺序、uses/sources、编辑源先行、超限显式处理；引用改变须与图号/摘要同组切换 |
| `domain/prompt.js:995–1143,1534–1600` | 请求快照、hash、记录与当前性 | 新语义纳入实际消费/basis与版本链，按§13.8切读写者；不另写一套近似失效规则 |
| `domain/rework.js`当前v2.5.4；§13.6 | 问题、方向和确定候选身份 | 明确mode/真正候选Blob/商品依据职责是新增差量，不把现有返工ID当编辑成立 |
| `semantic-analysis.ts:48–74` | 当前模型输出仅有待审事实槽位、摘要与问题，不能确认事实 | 没有创作方案/文案提议合同；若未来批准模型辅助，须在现有语义用途内明确扩展提议种类及其两端parser，不能把创意塞成“商品事实”或宣称现接口已支持 |
| `v2_dashscope_image.py:333–341`、`v2_volcengine_image.py:311–315` | 两种有限传输/同步异步Adapter | 保留传输职责；新增简报语义不变成供应商私有字段，无理由不重写现有协议 |

不改变AGENTS、上下文选型、计划§2.1原文、正式依赖和产品state机器块。新字段不在本轮实现；未来须一次迁完整写者/读者/类型/真实消费者，按当前main构建/测试工具而非旧同目录emit方式。

#### 13.15.2 优先处理的风险与验证边界

| 风险 | 当前判定 | 最小有效下一证据 |
|---|---|---|
| 只有约束拼接，没有正向创作 | 已有风格/用途段落，但协调程度及普通输入到方案的能力未证 | 正式恢复后按#9保留代表任务原程序稿，修改真实编译路径，从普通输入得到完整简报/正文；纸面三例不能代替 |
| 自由意图如何变成具体创作选择 | 有限用途配方可以确定性建议；不能宣称本地规则理解任意语言 | 先对主图状态、信息图文字布局等具体任务验证建议；若确需模型辅助，再定义明确提议合同及成本，不先建通用Agent |
| 文案来源与原校验冲突 | 当前字面事实印字不能直接支持本例确认译写 | 改真实文案消费者与规则，验证未确认/过期零外发、确认原文逐字发送、未选择事实不自动印字 |
| 参考图序与两模式含义漂移 | 当前只有role/hash，目标元数据与模式未全部落地 | 沿现有Transport入口核解码图hash/顺序与Prompt图号，三图编辑/超限阻断/原照模式均覆盖，零收费替身只证明请求行为 |
| 程序稿是否生成好图 | 仍未证明；模型足够是工作假设而非免责前提 | 在另获费用/次数授权后，精确程序稿→实际出站→原像素按§13.9核目标/保真/印字/尺寸，不用旧专家图或单次成功推稳定成功率 |
| 创作与编辑后历史/人工选择丢失 | 既有保护需按受影响前提复用，不从零重建 | 受影响人工稿、stale、取消、晚到、采用/包消费的现有正式路径；无变更不重复全量/真实模型 |

本轮只完成候选设计、纸面语义走查与Issue协作，独立审查与文档/只读冷恢复检查的记录入口为#17和讨论记录；未运行产品或真实模型，不把文档守卫当语义充分或产品验收。候选可用于范围评审，下一产品动作仍按state/计划§17.13与当次许可确定；不因设计齐全自动施工、不先扩所有页面、不重复已完成main治理或购买已成立证据。

### 13.16 普通输入到视觉简报：建议规则与首个实施切片

本节保留普通输入到视觉简报的建议规则与首片设计依据；准备时的“继续”不承担今天的权限解释。#9零收费编译/请求消费切片已经交付，确切版本与证明范围取state和PR #18，不再按本节末尾的首片建议从零实施。剩余完整表达、普通决定、真实品质和#8人因差量按计划§17.2–17.5及关联Issue推进；以下人工演算不是程序或像素验收。

#### 13.16.1 有限创作建议，不是假装理解任意自然语言

将“理解意图”和“编译表达”分开：保留用户原话；只有明确选择的用途、当前确认事实/文案、展示决定及参考职责进入有效方案。用户点击“类别介绍”可以确定沟通任务，不能由“高级点”自动推出大理石材质、奢侈品定位或暗色背景。含糊修饰语保留给用户核对，不用关键词命中自动确认事实/视角/文字。

建议使用现有suite-plan用途模板的有限创作配方；推荐、依赖、默认keep/allow与布局建议共用同一处任务定义，不在view或编译器另维护一张任务分类表。配方不是新增Agent、模型调用或通用配方引擎。对应建议只读展示，接受后由inputs按所见版本保存正式规格；保存/确认语义沿已有命令，不在重新打开页面时重选。
类别介绍复用现有`role_id=infographic`，以具体用途模板区分于卖点任务，不新增角色、不回退custom默认。当前IMAGE_ROLES的该角色label/purpose仍固定为卖点；同包应将角色改成中性的“信息图／表达所选有据信息”，具体任务名/目的由真实模板与Shot保留。计划列表、摘要的role_label及编译fallback须一起消费，不能后台选类别介绍、前台仍称卖点图，也不改写历史冻结标签。平台印字许可仍按这个真实role判定，keep/allow则由明确任务定义派生，不能让所有infographic仍一律保持卖点文字。

| 明确任务 | 从当前输入检查什么 | 系统负责补出的正向建议 | 只在必要时让人决定 |
|---|---|---|---|
| 完整商品主图 | 原照可用、实际主图profile、商品可见范围、相关展示状态 | 单主体完整入画；纯白背景、柔和中性光、自然接触阴影；沿可证视角，不新增文案 | 临时残留是否去除/内容物是否倒空；所选视角缺证；明确背景要求与平台冲突 |
| 类别介绍信息图 | 类别事实、明确选择的标题及其确认来源、商品依据；不依赖不存在的卖点 | 商品优先，左侧商品/右侧标题；浅灰白背景、深灰清晰字体、中性光；标题只出现一次 | 标题原文未定/未确认；选择文字与无文字；必要展示状态；与已有明确布局要求冲突 |
| 三项尺寸参数图 | 所选measurement及其精确版本、对象/轴向/数值/单位、标签映射和来源分类 | 商品与参数区分开，参数自上而下；与整套光色协调；依据不足时不用测量箭头 | 缺失/冲突的测量、未知来源、未确认对象标签；不能改成让用户写摄影或排版Prompt |

“左商品右文字”等是可改的有限布局建议，不是任何商品都最优的美学定理。用户可明确选择反向布局；超出有限建议的完整创意继续走已有自定义用途/人工规格与高级全文路线，不能伪称本地规则已理解任意表达，也不删除既有角色能力。需要模型提议时仍取§13.13.4的独立授权与确认规则。

#### 13.16.2 最小保存差量与一次有效简报

不保存第二份ImageSpec。沿§13.4的presentation与on_image_texts，拟增加以下两个窄单图语义；字段名/序列化版本在实际同包迁移时统一，不借本节冻结运行schema：

- **新增印字意图**：明确为“无新增印字／只印所选文案／尚未决定”。建议落在ShotSpec的一个有限字段，而非用空数组/notes猜含义。这是消费决定，不是删除文案：“无”保留既有文案原文/来源/状态，但本次不消费其文字或文案专用来源，也不因此引入印字指令；若某事实还用于商品描述，仍按该用途消费。“只印所选”的准备门为至少一项、全部confirmed且精确来源当前；不满足时保留草稿/待确认条目及原版本并阻断该图，不静默跳过一项继续发送。保存合法待确认状态不等于通过发送门。“未定”只阻需要该决定的图。旧包缺字段不自动解释为用户已选无字。平台禁止新增印字时不能保留“已选标题”却偷偷丢掉它；显式改成无字方案须更新目标/布局并重看摘要。
- **单图布局选择**：本轮三例只需要“仅商品／左商品右文字／右商品左文字”，未覆盖时按明确用途配方给建议；保存的是用户接受的选择，不存第二份自由创作JSON。共用composition继续表达整套约定，单图布局是明确例外；如果二者都是明确要求且矛盾，先解决冲突，不能悄悄按后者赢。含文字布局要求角色获平台印字许可且有效意图是“只印所选”；与主图或明确无字冲突时返回问题，不静默改为仅商品或丢文字。具体画面比例、留白、字体与光照由同一配方编译，不要求用户填写这些专业参数。

派生顺序固定：**核对任务与实际能力 → 收集该图消费的精确事实/决定 → 计算共用与单图有效值并查冲突 → 核文案/量测 → 规范化实际图序 → 形成一个有效简报 → 唯一编译入口输出正文、参数与来源 → 现有摘要确认/发送**。准备阶段无模型调用、不写正式方案、不预约action；用户接受建议后的保存是另一条显式inputs命令，不能把只读准备说成已保存。

简报是编译内部的派生值，预览与最终请求消费同一结果；不公开“先生成简报、再让调用方补齐再编译”的多步Interface。至少覆盖六件事：目标与主次、商品状态/可证视角、实际图像职责、构图/背景/光照、确切印字与布局、保持/允许改变。每部分沿现有sections/source_refs关联到实际来源；创作配方用规则版本标来源，不伪造FactSlot。完整性不足返回现有问题投影与具体补救，UI不重写判定。

平台规则与用户意图的处理要改真实消费者：当前prompt.js:669–678会把非白公共背景改白并给warning。对于明确要求紫色主图背景，目标行为是返回冲突，让人改选/取消本图，而不是warning后继续发送。尚未接受的系统灰底建议则在推荐主图时就换成符合规则的白底建议，不制造虚假的“用户冲突”；建议来源和显式保存值必须可区分。

#### 13.16.3 将纸面三例变成能判错的演算

以下只针对§13.14同一组虚构输入，列的是未来程序的独立判据，不宣称已运行。不是用“输出非空/包含高级感”等自我判分替代结果。

| 改动或输入 | 必须得到的语义结果 | 会推翻实现的反例 |
|---|---|---|
| 只选主图并继承已确认洗净倒空，未选尺寸 | 清洁空杯、完整主体/白底/有据视角；无新增文字；不消费D | 自动印尺寸、要求为主图补尺寸，或清洁决定没进正文 |
| 选类别介绍，确认T1=“CERAMIC MUG”，没有signature_features | 正常准备；单标题＋商品，所选布局具体；不自动补卖点 | 被卖点模板阻断、文案必须逐字等于中文F1、全事实自动印上图 |
| 同一信息图只把布局从左商品改为右商品 | 新预览只相应交换主体/标题位置，T1原文与来源、图序及商品保持要求不变 | 仅保存layout但正文不消费；视图和编译器各算出一种版式 |
| T1改proposed或F1改版本，其他资料未动 | T1待确认只阻消费T1的图；F1版本变化按真实消费分别失效，本例主图也消费F1而须更新；原文/精确来源保留，零新增POST | 把过期项自动换新译文，或把“主图不消费T1”误当“主图不消费F1”而继续用旧类别 |
| 保留待确认/过期T1，明确改成无新增文字＋仅商品方案 | 保留T1及旧来源但不印字、不因其文案专用来源阻断；切回只印所选时重新核确认/当前性 | 为无字清空历史文案，或保留旧文字布局/暗印T1，或切回来绕过确认 |
| 主图选择左商品右文字，或明确无字却保留含文字布局 | 返回具体意图/平台冲突，零新增POST；人改选后看新摘要 | 发出互相矛盾的含字布局和禁止印字指令，或静默修改用户选择 |
| D索引1的80mm误绑定为高度，或D版本改变/重排 | 尺寸图拒绝错配/要求重新核对；无关信息图和主图不因D变化失效 | 只校验引用存在就发送、用当前索引偷换来源，或整套无差别失效 |
| 编辑C2时输入为[C2,R1,R2]，再明确切原照重生成 | 编辑正文的候选/商品图号与三图一致；重生成只有[R1,R2]且完整重述目标 | 仅加一句“修改图1”保留旧编号，或重生成仍要求保持不可见C2构图 |
| 人工全文在场或确认后改明确背景/引用 | 人工稿不被覆盖；按既有明确选择/新摘要/stale处理，不暗中另发 | 自动系统稿覆盖、后台自动重准备后直接发送、未知任务重新提交 |

固定同一已保存方案、输入精确版本、规则版本与有效profile时重复准备须得到相同语义/正文/参数，不以每次另挑创意制造版本抖动；真实图像随机性不在这个确定性承诺内。

#### 13.16.4 第一个可实施切片与停止设计点

**首个表达切片优先选带明确标题的商品信息图，而不是只做白底主图；验收必须复用既有代表任务及其原普通输入。** 它同时暴露“用途依赖/默认keep、确认译写来源、有限布局、只印所选文案、冻结出站一致”问题。§13.14类别介绍仅是可判错的纸面规则样本，不能用虚构杯子替换#9所需的实际Before/After；若既有任务本意是卖点图，就保留其真实卖点与依据，缺证不得靠改称类别介绍绕过。主图作为无字与影响隔离的对照；尺寸/两模式已有独立合同，不塞进首个改动扩大事务面，也不取消#9/#8的原完整终点。

| 同一个改变必须闭合的落点 | 实施要求与可观察结果 |
|---|---|
| 用途定义、推荐及默认规格 | 具体任务与真实目标一致：类别介绍不继承“已确认卖点文字”或卖点依赖；真正卖点图仍要求卖点依据。共享角色label/purpose中性化，计划/摘要role_label与编译fallback同组迁移，具体图名/目的不丢；模板不能为迎合样例改写用户目的 |
| specs/inputs/type-contracts及全部读写者 | 文案、印字意图与单图布局有同一套合法形状、OCC/来源与保存结果；不能只写UI字段或把专业生成段塞进用户notes |
| prompt.js/prompts与当前性/检查消费者 | 同一有效方案形成正向布局和准确印字；原“等于事实原文”改为所选确认文案与源版本的合同；basis按真实消费变化，规则更新使相关系统稿待准备，不碰人工历史 |
| 原输入/方案/预览/发送视图和generation | 普通用户选用途/标题/布局即可；从正式页面取得真实程序稿，预览、冻结请求与实际出站一致；不借本切片改建工作台或双模式事务 |
| 现有引用、语言/泄漏、人工稿及包消费者 | 同包迁受影响parser/类型/检查/导出读者；旧运行分支不并存。新schema不能接受尚未实现的尺寸/模式字段然后忽略；原件与历史范围仍取§13.8 |

正式恢复后，先保存当前同一普通输入的原程序稿和具体缺口，再改真实路径；用既有本地替身从真实页面走到Adapter解码后的正文/参数/图hash与顺序，零真实模型调用。替身只作传输观测，不把响应回声或假图作为创作质量证据。只运行受影响的现有验证并实际走页面；必要永久回归保护“无卖点仍可类别介绍、只印确认标题、过期零发送”等消费者结果，不固定段落措辞或配方内部结构。

只有该路径成立，才以真实增量推进主图/尺寸及#8双模式；真实像素质量仍需另获费用/次数/素材准入并按#9核验，原image52/52门不因零收费成功而松开。此处选的是第一个可检验改变，不是把完整产品缩为MVP后宣布完成。

**设计准备已收敛**：当前合同足以执行剩余产品包，不继续扩抽象或纸面案例数量。最新用户已授权完整交付，尚未解除的原生工具门与准确下一动作只取state；按计划/Issue执行，不重新索取已有许可或制造新准备循环。本节原有人工演算不升级成程序或像素证据，已交付片段和剩余范围分别核对。
