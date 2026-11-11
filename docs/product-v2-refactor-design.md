# Product V2 联合结构重构详细设计

> CONTROL-STATUS: current · AUTHORITY: refactor-implementation-design
> 本文是**目标设计，不是工程完成声明**。当前实现规格取§13；目标、正式依赖/准出与最新用户修订取`product-v2-refactor-plan.md`§2.1/§17.13；技术选型和数据归属取项目上下文，权限及前沿只取state。§10–11按未变前提复用旧算法/差量证据，不再作为新会话默认施工清单；§12只指向当前恢复入口。
> §13来自2026-10-12独立设计及2026-10-13正式启动承接；这些历史不解除当前停工，也不证明已经实现。独立设计/原型记录在`_working/amz-listing-kit-next-version-design/discussion.md`，产品原生Goal观察全文唯一在计划§2.1。

正文按主题拆分；本页保留原有章节标题和锚点，各节“正文”进入对应主题。当前实现规格从[§13](#13-下一版实施规格普通决定驱动可信整图)进入；权限及前沿仍只取state。原件与逐字节恢复登记见 `config/document-splits.json`，正文继续按各自内容维护。

## 1. 设计依据与决策

[正文][d01]

### 1.1 问题不是文件太大，而是规则和时序泄漏

[正文][d01]

### 1.2 比较三种Interface后选定的方案

[正文][d01]

## 2. 所有权、依赖与生命周期

[正文][d01]

### 2.1 目标状态所有权

[正文][d01]

### 2.2 依赖是有向图，不用callback绕回工作台

[正文][d01]

### 2.3 生命周期和异步结果

[正文][d01]

## 3. 业务Interface：页面只表达意图

[正文][d02]

### 3.1 命令与读模型

[正文][d02]

### 3.2 不能靠冻结输入冒充当前性

[正文][d02]

## 4. 事务、授权消费与副作用

[正文][d03]

### 4.1 存储Seam需要的窄能力

[正文][d03]

### 4.2 确认到提交的线性化点

[正文][d03]

### 4.3 采用、报告与交付的线性化点

[正文][d03]

## 5. 六条主链与失败恢复

[正文][d03]

## 6. 重复与冗余：分类后合并/删除，不只拆文件

[正文][d04]

## 7. 测试稳定化与类型/交付一致

[正文][d04]

### 7.1 断言分类与迁移

[正文][d04]

### 7.2 消费者可见反例（复用优先）

[正文][d04]

### 7.3 执行成本

[正文][d04]

## 8. 历史材料、源码删除与交付闭包

[正文][d05]

## 9. 施工包、回退与准出

[正文][d05]

### 9.1 六项结构准出（作为原联合完成判据的操作化）

[正文][d05]

## 10. 提前冻结的高难度实施规格

[正文][d06]

### 10.1 Interface收口与投影：不要把状态搬进另一份context

[正文][d06]

### 10.2 所见摘要与精确失效：绑定“用户看见的那份”，不是重算后的新版

[正文][d06]

### 10.3 跨标签页预占：授权防重和业务阻断必须在同一事务

[正文][d07]

### 10.4 旧结果保全与防倒退：按action推进，按预约顺序投影

[正文][d07]

### 10.5 生命周期：把关闭分成禁新动作、保存草稿、脱离视图

[正文][d08]

### 10.6 报告、人工采用和两类ZIP：快照一致不等于实时当前

[正文][d08]

### 10.7 TS→浏览器→镜像：一个源码，完整产物，失败不半生成

[正文][d09]

### 10.8 发布/回退：保留既有事务平台，补真实不同版本证明

[正文][d09]

## 11. 施工包职责索引与当前差量收口

[正文][d10]

### 11.1 先准备执行环境，不从头再审计

[正文][d10]

### 11.2 包顺序、边界与最小证明

[正文][d10]

### 11.3 验证选择：明确命令和实际行为，别让低模型刷全量

[正文][d10]

### 11.4 交接/失败/升级规格

[正文][d11]

### 11.5 当前版本差量收口：无需下一轮总体重构

[正文][d11]

#### 11.5.1 一次恢复核对，随后只读受影响闭包

[正文][d11]

#### 11.5.2 固定模块接缝与组合，不引入总编排层

[正文][d11]

#### 11.5.3 失败路径与无效证明的精确修复单位

[正文][d12]

#### 11.5.4 具体运行与最终顺序（仅恢复施工后）

[正文][d12]

#### 11.5.5 升级门和后续维护边界

[正文][d12]

### 11.6 2026-10-08可信基线文件级规格（历史条件，非当前施工表）

[正文][d13]

#### 11.6.1 范围、前置与复用

[正文][d13]

#### 11.6.2 A1：关闭间歇启动的因果缺口

[正文][d13]

#### 11.6.3 A2：第五步“看到谁、操作谁”及返工owner闭合

[正文][d13]

#### 11.6.4 B：精确凭据、辅助整链与原结构准出

[正文][d14]

#### 11.6.5 C：复用WIP并一次清退旧运行面

[正文][d14]

#### 11.6.6 D：最后改动后的同候选两轮

[正文][d15]

#### 11.6.7 E：沿现有发布事务交付

[正文][d15]

## 12. 给下一轮执行模型的启动入口

[正文][d15]

## 13. 下一版实施规格：普通决定驱动可信整图

[正文][d16]

### 13.1 目标、授权与交付边界

[正文][d16]

### 13.2 设计准备时基线与实验资产（历史资格）

[正文][d16]

### 13.3 人因、界面与交互判据

[交互判据][d17] · [工作台布局与修改态][d18]

### 13.4 普通决定、文案与记录形状

[正文][d19]

### 13.5 唯一owner、Module Interface与实施落点

[正文][d19]

### 13.6 双模式返工与真正模型输入

[正文][d20]

### 13.7 五条路径：正常、失败、并发与恢复

[正文][d20]

### 13.8 格式与历史：一次切换，不篡改原动作

[正文][d20]

### 13.9 Prompt归因与真实品质标准

[正文][d21]

### 13.10 验证、确认与验收：按风险复用，不频繁造探针

[正文][d22]

### 13.11 重构、清退与上下文维护的实施次序

[正文][d22]

### 13.12 已决方向与交付边界

[正文][d22]

### 13.13 生图业务语义与核心合同（2026-10-18设计准备候选）

[正文][d23]

#### 13.13.1 术语、责任与不变量

[正文][d23]

#### 13.13.2 完整业务链的输入、输出与状态

[正文][d23]

#### 13.13.3 简报的有效值、继承与冲突

[正文][d24]

#### 13.13.4 创作、编译与传输的分工

[正文][d24]

### 13.14 三个完整纸面实例与反例

[正文][d25]

#### 13.14.1 三例共用的输入、图序与参数

[正文][d25]

#### 13.14.2 主图：把清洁意图转成明确展示

[正文][d25]

#### 13.14.3 信息图：准确文案与画面层级

[正文][d26]

#### 13.14.4 尺寸图：对象、轴向、数值和来源

[正文][d26]

#### 13.14.5 修改、超限与人工稿的跨例检验

[正文][d26]

### 13.15 当前源码差量、风险与后续验证

[正文][d27]

#### 13.15.1 静态核对的复用落点

[正文][d27]

#### 13.15.2 优先处理的风险与验证边界

[正文][d27]

### 13.16 普通输入到视觉简报：建议规则与首个实施切片

[正文][d28]

#### 13.16.1 有限创作建议，不是假装理解任意自然语言

[正文][d28]

#### 13.16.2 最小保存差量与一次有效简报

[正文][d28]

#### 13.16.3 将纸面三例变成能判错的演算

[正文][d29]

#### 13.16.4 第一个可实施切片与停止设计点

[正文][d29]

[d01]: product-v2-refactor-design.01-decisions-and-ownership.md
[d02]: product-v2-refactor-design.02-business-interfaces.md
[d03]: product-v2-refactor-design.03-transactions-and-main-paths.md
[d04]: product-v2-refactor-design.04-redundancy-and-test-stability.md
[d05]: product-v2-refactor-design.05-history-and-delivery-exit.md
[d06]: product-v2-refactor-design.06-interface-and-summary-spec.md
[d07]: product-v2-refactor-design.07-reservation-and-observations.md
[d08]: product-v2-refactor-design.08-lifecycle-reports-and-exports.md
[d09]: product-v2-refactor-design.09-build-and-release-spec.md
[d10]: product-v2-refactor-design.10-packet-responsibilities-and-validation.md
[d11]: product-v2-refactor-design.11-handoff-and-delta-ownership.md
[d12]: product-v2-refactor-design.12-failure-repair-and-exit-order.md
[d13]: product-v2-refactor-design.13-historical-baseline-startup-and-compare.md
[d14]: product-v2-refactor-design.14-historical-credentials-and-retirement.md
[d15]: product-v2-refactor-design.15-historical-exit-and-current-entry.md
[d16]: product-v2-refactor-design.16-current-goals-and-design-assets.md
[d17]: product-v2-refactor-design.17-human-factors-criteria.md
[d18]: product-v2-refactor-design.18-workbench-layout-and-interactions.md
[d19]: product-v2-refactor-design.19-decisions-copy-and-module-owners.md
[d20]: product-v2-refactor-design.20-rework-inputs-paths-and-history.md
[d21]: product-v2-refactor-design.21-prompt-attribution-and-quality.md
[d22]: product-v2-refactor-design.22-validation-order-and-boundaries.md
[d23]: product-v2-refactor-design.23-business-semantics-and-chain.md
[d24]: product-v2-refactor-design.24-effective-brief-and-compilation.md
[d25]: product-v2-refactor-design.25-paper-inputs-and-main-image.md
[d26]: product-v2-refactor-design.26-paper-infographic-dimensions-and-edits.md
[d27]: product-v2-refactor-design.27-source-delta-and-validation-risks.md
[d28]: product-v2-refactor-design.28-visual-brief-rules-and-storage.md
[d29]: product-v2-refactor-design.29-checkable-examples-and-first-slice.md
