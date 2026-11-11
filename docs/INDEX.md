# 项目上下文与文档权威入口

> CONTROL-STATUS: current · AUTHORITY: context-routing
> **任何人或 Agent 进入项目先读本文件，但不在这里复制目标、状态或实现正文。**
> 本文件只做路由与身份登记；文件存在但没登记、登记文件不存在、同类事实有多个权威都会由
> `tools/check_docs.py` 报红。

---

## 1. 从这里开始：一类事实，一个权威

| 要回答的问题 | 唯一权威 | 其他地方只允许 |
|---|---|---|
| 当前方向、权限及历史 Goal 观察 | 最新用户指令与 `_working/amz-listing-kit-product-v2/state.md` | 旧 Goal 原文只作历史观察，实时状态未知；不以旧绑定作为新重构前提 |
| 项目是什么、运行边界、数据与目录归谁 | `docs/product-v2-project-context.md` | 计划和 README 只链接，不复制项目身份、目标运行时或数据所有权 |
| 产品方向、正式任务和验收是什么 | 最新用户指令及 `docs/product-v2-refactor-plan.md` | 先核对计划§17.14；旧任务和授权保留为历史合同，不自动构成当前施工命令 |
| Module/事务设计与交互/Prompt质量如何实现 | `docs/product-v2-refactor-design.md` | 当前规格§13，界面读2026-10-16修订§13.3；旧§10–11仅追溯经当前证据确认仍适用的差量，不能据旧owner清单重做；不由设计推导施工许可 |
| 产品门、权限、阻塞和唯一恢复前沿是什么 | `_working/amz-listing-kit-product-v2/state.md` | 不另建产品机器状态；历史审计或独立设计记录不能发布当前状态 |
| 具体问题、验收与改动审查进展是什么 | GitHub Issue及关联PR；工作流只取`AGENTS.md` | plan/state只保留正式任务关联、权限、恢复与证据指针，不复制工单明细；远程写入须在当次授权内 |
| 现有代码实际上能做什么 | `README.md` 指向的代码、配置与验证入口 | 目标计划不得把未实现能力写成当前实现 |
| 哪份文档有效、历史还是待删 | 本文件 | 各文件只声明自己的 CONTROL-STATUS，不建立另一张总表 |
| 某次检查或实验实际发生了什么 | `evals/` 下对应原始产物和时点报告 | 只作证据，不发布后续计划、当前状态或新规范 |

进入项目按此顺序：**本文件 → AGENTS.md 及其规则分片 → 当前 state → 计划§17.14 → 本轮任务所需 context、设计、代码与证据**。当前为文档治理，产品实施暂停；旧任务卡、批次、历史状态和授权不自动恢复。

`uv run --locked python tools/refactor_resume.py` 是只读恢复入口；当前策略会阻断旧任务恢复。脚本输出不替代当次授权，历史 Goal 读数不代表实时状态。最新用户已明确授权的操作不重复索取许可；收费、素材、秘密、数据及远程写入分别核对。

产品目标与验收按最新用户方向和有效合同核对；计划的旧 Goal 正文、历史执行包和授权保留原始证据，不作为新重构的施工前提。

下一版本规格定向读 `docs/product-v2-refactor-design.md` §13；生图业务语义、纸面实例与源码差量见§13.13–15，普通输入到简报的建议规则与首个实施切片见§13.16。设计准备协作见 [Issue #17](https://github.com/JusticeSc/listing-kit/issues/17)，不替代#9程序品质或#8交互验收；实际实施及权限按最新用户指令和 state 核对。

---

## 目录分片

以下分片共同组成本登记；当前职责、在场登记、状态取值、反例和写入规则按问题定向读取。分片不建立第二份权威，守卫按登记顺序读取正文。

| 分片 | 内容 |
|---|---|
| [登记：项目入口与早期记录](catalog/product-entries.md) | 项目入口、目标与设计 |
| [登记：状态、任务书与旧设计](catalog/state-and-history.md) | 状态、任务书与保留历史 |
| [登记：模板与协作参考](catalog/references.md) | 外部模板与协作参考 |
| [状态取值与登记反例](catalog/status-and-checks.md) | 身份闭集与双向登记判据 |
| [写入路由与修改前快照](catalog/write-routing.md) | 事实所有者与原件保护 |

公开 main 原登记中已退役的 21 条 `superseded / 历史证据` 行已退出在场目录，其身份、替代说明和原件只从 [原件恢复登记](../config/retired-documents.json) 定向查询；不存在的旧路径不作为当前文件入口或施工指令。`docs/product-v2-refactor-design.md` 仍是 `current / 架构设计`，按上方职责路由读取。

拆分来源与正文顺序见 [拆分登记](../config/document-splits.json)。公开 main 原件的 commit/path/SHA256/字节数与拆分时外部快照可完整复原旧目录；当前目录移除退役行并修正其引用。原件恢复证明不冻结后续正文或机器状态。

## 文档体积与恢复

被 Git 跟踪或未忽略的新文档逐份不得超过 10,000 字节；文件范围包括常见 Markdown、文本、日志、办公文档及 `docs/` 下 HTML，具体枚举见 `tools/check_doc_budgets.py`。不设冻结或大小豁免；结构化机器数据按自身合同管理。

运行 `uv run --locked python tools/check_doc_budgets.py` 检查实际文件和暂存内容，运行 `uv run --locked python tools/check_document_splits.py` 核对原件来源；拆分时另做一次重组证明，后续编辑不受旧分片 hash 冻结。退役原件按恢复登记先恢复到隔离目录并核对字节。
