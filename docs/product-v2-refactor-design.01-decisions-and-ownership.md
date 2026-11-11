<!-- 拆分件 01/29 · 父文档 docs/product-v2-refactor-design.md -->
# 设计依据、所有权与生命周期
[返回设计目录](product-v2-refactor-design.md) · [下一主题](product-v2-refactor-design.02-business-interfaces.md)

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

