<!-- 拆分件 02/29 · 父文档 docs/product-v2-refactor-design.md -->
# 业务Interface与所见当前性
[返回设计目录](product-v2-refactor-design.md) · [上一主题](product-v2-refactor-design.01-decisions-and-ownership.md) · [下一主题](product-v2-refactor-design.03-transactions-and-main-paths.md)

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

