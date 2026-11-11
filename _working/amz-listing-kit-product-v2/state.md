# Product V2 定向重构执行状态

> CONTROL-STATUS: current · AUTHORITY: execution-state
> 当前治理边界在本页；机器字段在 [state.yaml](state.yaml)；公开 main 的历史原文见下方有序拆分件。

## 当前恢复边界

本轮仅文档治理与目标重设准备，旧产品任务不可恢复。文档拆分、原件保全、恢复证明及管理工具适配不构成产品复工、模型调用、发布或额外费用的授权。恢复入口要求计划有唯一的 `blocked` 策略标记，缺失、重复或未知均拒绝恢复。

原生 Goal 是历史观察，未重新读取、不伪改。机器数据保留公开 main 在 `2026-10-21T11:02:04.352Z` 记录的 `15ab22bf3386b9cf / active`；该时点的 `status`、下一任务、进度及证据不代表本轮实时授权，也不证明 Goal 已完成。目标重设边界取 [计划](../../docs/product-v2-refactor-plan.md) 的§17.14，后续实际 Goal 与授权须另行核对。

`blockers` 与93条 `unknowns` 按公开 main 原值、原顺序保留，不因拆分清空或过滤；历史 `blockers: []` 不解除本页和计划的停工限制。先读本节，再读机器数据；历史拆分件只用于核对其原时点。

## 机器数据与原件恢复

[state.yaml](state.yaml) 是本状态唯一机器权威；旧状态仍支持 Markdown 内 YAML。其字段来自公开 main `11902b32651f4690f7367624377dcde6652e0a97`，没有复制旧候选的私有状态。指向已退役状态的当前证据引用转到 [恢复登记](../../config/retired-documents.json)；登记保留原路径、公开 commit、blob、字节数和 SHA256，历史原件不受影响。

原 `state.md` 为94,797字节，SHA256 `fe193e91be389726b16a63b04c8bd6931d4980e60ff0790095df59736f8d1ef5`。初始拆分与提取的 YAML 已逐字节重组为同一原件；[拆分登记](../../config/document-splits.json) 保存公开来源、顺序、初始 hash 与提取行段。此后当前文档与机器数据可继续维护，初始 hash 用于恢复证明，不冻结后续写作。

## 公开 main 历史原文（有序）

1. [历史原文 1](state.history-01.md)
2. [历史原文 2](state.history-02.md)
3. [历史原文 3](state.history-03.md)
4. [历史原文 4](state.history-04.md)
5. [历史原文 5](state.history-05.md)
6. [历史原文 6](state.history-06.md)
7. [历史原文 7](state.history-07.md)
