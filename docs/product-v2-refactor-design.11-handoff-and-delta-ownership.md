<!-- 拆分件 11/29 · 父文档 docs/product-v2-refactor-design.md -->
# 交接、恢复核对与差量所有权
[返回设计目录](product-v2-refactor-design.md) · [上一主题](product-v2-refactor-design.10-packet-responsibilities-and-validation.md) · [下一主题](product-v2-refactor-design.12-failure-repair-and-exit-order.md)

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

