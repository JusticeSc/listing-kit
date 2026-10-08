# Product V2 联合结构重构详细设计

> CONTROL-STATUS: current · AUTHORITY: refactor-implementation-design
> 版本：r3 · 2026-10-07。本文是**目标设计，不是工程完成声明**。目标/业务权限/正式任务/依赖/RC仍唯一取 `product-v2-refactor-plan.md`；技术选型、运行及数据归属取 `product-v2-project-context.md`；进度和恢复前沿只取state。§10保留既定算法，§11.2保留原包职责索引，当前版本只按§11.5差量收口及§12恢复；本轮仅完善方案，不解除停工。

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

这是依赖目标，不是现有实现全已遵守的声明。当前 `workspace.js`仍调用generation的review setter，后者在候选保存时回调adoption；不得把删除了旧AI请求builder等同于所有反向依赖已清除。具体切断、报告失败保全和订阅释放见§11.5.2。

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
| V1与offline-fixture | 当前轮保留在明确legacy/fixture入口；V2默认、独立历史验证 | 不执行V1日落；生产仅排除无V2依赖的历史部分，不删历史功能 |
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

- 项目运行实例装配顺序固定为 **inputs → prompts → generation → adoption → delivery → views**。单图AI请求的事实/规格/原动作/图片字节准备迁入adoption，删除 `review-delivery.candidateReviewRequest`，使generation不反向依赖adoption/delivery。网关和settings用现有窄入口，不新增通用命令总线。
- generation吸收authorization的Map和 `confirmed/reworkEntry/mode/enterFailedRetry/enterExplicitNew/intent/reworkIntent/queues` 等实际职责；映射现有全部调用方后删除 `authorization.ts/.js`。不用独立 `AuthorizationStore` 转发或旧名alias。
- `loadAttemptChain/loadCandidateChain/setReviewReport` 不再是workspace的公开写口。恢复由相应owner内部执行；attempt/candidate归generation，单图report及ack/selection归adoption，suite report/export归delivery，输入及proposal归inputs。
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

本节只规定恢复后的改动与证明，不是本次施工指令。产品终点/证据信任/停止门唯一取计划§15.6；原包与任务状态取state。下列具体差距来源于当前审计和实际源码，历史材料只作原证明，不为再次审计全仓而重复跑产品。

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

**候选与报告的单向消费。**当前 `generation.ts` 的 `reviewAccess.ensureReport`（已有候选/新保存两处）、`setReviewAccess`／`setReviewFlightReader`和 `workspace.js` 的setter、恢复补report循环一并迁移：

1. generation完成原项目候选/asset保全后通知其投影变化，报告结果不进入候选保存成功条件。`StoreCandidateResult.review`等报告转发字段随全部实际消费者同包删除；消费者直接读取adoption。
2. 沿§2.3既定局部 `subscribe(changed)`通知，由adoption自己订阅generation并读取只读候选；同candidate身份和所消费版本的确定性补报告工作只保留一份flight，不新建事件总线/队列服务。已有当前report不增版本，确保过程复用既有 `ensureReport`、domain当前性和repository；AI调用不在订阅中发生。
3. adoption.restore内部补缺失/过期确定性report并投影错误；workspace只调用restore，不再判断report当前性或吞掉补报告异常。失败保留已存图片及原采用，明确报告缺失、禁止采用/交付越过硬门；不能因此重POST生图，也不以假PASS或模型Unknown代替本地检查失败。
4. 当前项目的新candidate可先预览，报告尚未准备不伪装可采用/可导出；本地恢复/再次明确采用可请求同owner补建。切换后退订UI与下游调度，已发生成仍归原项目保全；detached旧实例不向新实例报告Map或DOM写入，原项目重开由adoption.restore补report。
5. `generation.isReviewInFlight`若只是未使用的转发则删除，真实复核忙碌消费者直接读adoption自己的投影；外发阻断仍由原attempt/授权领域合同决定，不能因拆依赖删Unknown/在途保护。全部引用迁移后删旧setter/type/helper，不留可选旧reviewAccess后门或re-export。

**所见摘要只由generation定义。**当前 `ui/generation-view.ts`／workspace摘要与 `confirmAndRun({intent, readIntent, documentId, expectedVersion})`仍泄漏编排。目标在现有generation中提供“准备摘要”的具体业务命令，输入仅用户选定scope/mode；owner消费prompts/inputs/settings、产生带原项目/所见版本的意图和展示投影。视图保存并原样提交用户看过的意图，不传重新算摘要的callback、不猜documentId/expectedVersion、不自行保存授权再runBatch。generation内部按§10.2重验当前性并按§10.3预约；stale返回新摘要但不默认替用户确认。复用原hash/领域判据/事务，不重造快照格式、授权store或通用dispatch。

**表现通知替代UI callback。**从现有GenerationDependencies等移除 `renderAttempts/renderBatch/status/attemptError/clearAttemptError`及裸DOM/可变Map注入，结果/忙碌/错误归具体owner投影，由已装配view订阅读取。消息可以保留原用户文案，但文案不作为领域状态；workspace只接生命周期、订阅和DOM，不接管业务错误恢复顺序。同一变更只通知必要视图，dispose清本实例监听/URL/timer，不引入全局Store。普通输入草稿仍归view，保存命令传明确草稿/seen版本，不从业务owner回调DOM取值。

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
npm run check:generated
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

## 12. 给下一轮执行模型的启动文本

2026-10-07用户已明确恢复产品交付并创建相符真实Goal，当前权限取计划§2.1/§16.1与state。下文是恢复路由而非第二份目标/进度；未来新会话仍实时核对，单独复制设计文本不能新增授权、重复创建Goal或自动配置/切模型。

```text
恢复 amz-listing-kit 产品工程Goal的联合交付与结构收口；先核对用户此次是否明确解除state停工门及实时系统Goal，未获恢复只报告阻断，不施工。按 docs/INDEX.md→项目上下文→_working/amz-listing-kit-product-v2/state.md→原计划下一任务卡及证据恢复，运行 uv run --locked python tools/refactor_resume.py 取得真实前沿。独立规划Goal不是产品绑定；已有相符产品Goal则核对，无相符Goal只按计划§16.2及用户本次触发处理，不自作生命周期变更、不重置进度或重复有效启动审计。

实现设计唯一在 docs/product-v2-refactor-design.md；先读计划§15.6资产/终点与设计§11.5差量、§10冻结算法、§9.1准出和受影响owner规格。不要从已完成组A或设置重做：承接4_4两层失败、generation/adoption与UI业务序列残余、3_5/5_3失效证明及packet08空证，沿同一人工/辅助完整任务闭合，再最终离线冻结和既有CI/发布。每对象迁全部读写/恢复/通知消费者并同包删除旧setter/Map/helper/alias，唯一TS源及全部JS产物同步；无shim、总dispatch、回调环、新框架/全仓TS。预占同一IDB事务验当前性/消费/业务阻断，旧action晚到保全但不掩盖新在途；采用/OCC首次0、完整项目单快照与交付精确来源围栏分开。

每包真实运行改变用户路径，保留失败并按原state记录轮数/交付/未证；必要判据抓行为不钉源码/文案/mock回声，间歇必须因果。最终V1工程条件下清理后的两轮、完整人工/辅助模拟真人E2E、RC/结构、原PR保护、真实HTTPS/不同版本回退与同origin数据恢复全部保留。沿原账本及最新§16.1增量3元/5次生图/2次理解复核门，不自动付费/读Secret明文/绕保护/清用户库；优先成熟复用、该加加该删删不造平台。规格/数据/总体架构/权限/预算需决策即及时升级，10轮未交付停并申请，不降验收；C17/C15独立真人仍未发生，不冒充通过。
```

准备交付只证明规格和恢复入口一致。首次产品运行、事务交错、最终两轮、真实CI/HTTPS/两版本回退、完整图文品质与真人验收均由恢复后的实际证据判断，不由本文预先签署。
