<!-- 拆分件 01/02 · 父文档 evals/product-v2/refactor/packet09-history-archive-20261007T085222Z.md -->
# 包09第二片：历史材料归档与 INDEX 引用分类（20261007T085222Z）
[返回 packet09-history-archive-20261007T085222Z.md](packet09-history-archive-20261007T085222Z.md)

# 包09第二片：历史材料归档与 INDEX 引用分类（20261007T085222Z）

> CONTROL-STATUS：时点证据（packet09-history-archive），不是文档身份/进度权威。
> 范围：只碰 `docs/**` 与 `_working/**` 的分类判定；本片**零文件搬迁/删除/改动**，
> 不改产品代码、不改 `state.md` 的 progress 与任务表（无归档说明可追加，保持原样）。
> 判据：`docs/product-v2-refactor-design.md` §8（历史治理与删除/归档准入）+
> `docs/INDEX.md` §1/§2/§5（路由、登记表、写入路由）。

## 1. 结论先行

- `docs/**` + `_working/**` + 根 `README.md`/`AGENTS.md` 共 66 份受管 `.md`
 （守卫实测：已登记 65 份，仓库实际 65 份——差 1 系计数口径，见 §5 未决项）。
- 分类结果：**current 6 / generated 8 / draft 19（含 ui-contract 1 + agents 3 + standards-template 15）/
  superseded 32**。详见 §2。
- INDEX 引用逐条核对（§3）：登记表全部路径真实存在，**零断链**；
  指向现役 6 + 生成产物 8 + 草案 19 + 历史 32；**无一处需修正或标历史**。
- **本片不做任何归档移动/删除**：设计 §8 明确“不得移动仍被权威引用的路径”，
  而现役权威仍引用至少 3 处历史材料（证据 §4），搬迁会使守卫/恢复断裂；
  且 INDEX §5 要求文档身份变化只改 INDEX + 目标文件头——本次分类与登记完全一致，
  无身份变化可改。包09设计行“随前包迁，最终在08后收口”中的分类与引用核对义务
  在此闭合；物理归档留待后续获批任务按 §8 准入另行执行。

## 2. 逐文件分类表（66 份）

分类键：A=当前权威（current）· B=生成产物（generated）· C=设计草案（draft）·
H=历史仅存档（superseded）。“被谁引用”指**现役权威文件**（plan / context / design /
ui-contract / README / AGENTS / current state / INDEX 登记）中的有效引用；
纯历史文件互引不计为现役引用。

### 2.1 A：当前权威（6 份——与 INDEX 登记一致，不动）

| # | 文件 | 管辖事实 | 依据 |
|---|---|---|---|
| A1 | `README.md` | 实现 | 现役实现入口；被 AGENTS:4、INDEX §1/§2 引用；内容为当前 V2 边界/启动/验证，无取代者 |
| A2 | `AGENTS.md` | 项目规则 | 唯一 Agent 规则权威；被 INDEX §1/§2 登记，check_docs 做选型门禁校验对象 |
| A3 | `docs/product-v2-project-context.md` | 架构设计 | 被 plan:4-6、design:4、ui-contract:5、README:5、AGENTS:5、INDEX §1 引用；SEL/目录/质量门槛唯一出处 |
| A4 | `docs/product-v2-refactor-plan.md` | 产品目标（全表唯一） | §2.1 真实 Goal、§6/§9/§10 任务依赖验收；被 context/design/ui-contract/README/AGENTS/state/INDEX 全网引用 |
| A5 | `docs/product-v2-refactor-design.md` | 架构设计 | §10–12 冻结规格/小包/启动文本；被 plan:423/944/956、context:222、AGENTS:66/84/95 引用；目标设计非实现声明 |
| A6 | `_working/amz-listing-kit-product-v2/state.md` | 执行状态（全表唯一） | 被 INDEX §1、README:7、AGENTS:6、plan:36/569/1001、context:6/211 引用；唯一进度/证据/下一动作 |

### 2.2 B：生成产物（8 份——生成器 `tools/gen_slot_cards.py`，不动）

| # | 文件 | 依据 |
|---|---|---|
| B1–B8 | `docs/cards/README.md`、`slot-1..7.md` | INDEX 登记 generated，说明列写明生成器；check_docs 校验“七格共有规矩 + 该读哪一张”；README:234 引用 cards 语义（固定七坑位历史入口说明的一部分）。手改禁区，本片不碰 |

注：cards 头部无 CONTROL-STATUS 文本（git-grep 检查时 shell 对 CJK 路径转义失败显示 NONE，
但 `grep CONTROL-STATUS docs` 经 reader 侧对全部 27 命中文件含 cards 校验通过，且
`check_docs --no-run` 全过=双向比对一致；属测量工具假象，非文件缺头。见 §5 未决）。

### 2.3 C：设计草案（19 份——未进控制面，保留，生效条件见 INDEX，不动）

| # | 文件 | 依据 |
|---|---|---|
| C1 | `docs/product-v2-ui-contract.md`（draft） | §1–8 为 2026-10-04 修订设计正文，§9–10 历史原型；被 plan:351/651 引用为“界面投影”，plan:651 明确仍 draft；转 current 需产品发起人实际走查（未发生） |
| C2–C4 | `docs/agents/issue-tracker.md`、`triage-labels.md`、`domain.md` | 头部 draft；被 AGENTS:158/162/166 条件引用（“启用技能后按此执行”）；GLOSSARY/`docs/adr/` 尚未建出，生效条件未触发 |
| C5–C19 | `docs/standards-template/` 15 份（00–07、PROGRESS、README、templates×4） | 外部课程模板原样副本；AGENTS §Standards Mapping 为采纳判定表（00→context、01→plan §14/§6/§9、PROGRESS→state 等，AGENTS:30–44 行）；INDEX §1 明确“默认不读”；模板整目录同步属性，删改会破坏“新文件→本表加一行”规则 |

### 2.4 H：历史仅存档（32 份——superseded，保留作证据，不删除不移动）

替换链（每条“被谁取代”与 INDEX 登记一致，文件头 CONTROL-STATUS 逐份核对一致）：

| # | 文件 | 被谁取代 | 仍被现役引用的证据（§4） |
|---|---|---|---|
| H1 | `docs/product-v1-goal-and-implementation-plan.md` | `docs/product-demo-goal-and-implementation-plan.md` | INDEX 登记链一环；现役无直接引用（经由 H2 间接）→ 保留 |
| H2 | `docs/product-demo-goal-and-implementation-plan.md` | `docs/product-v2-goal-and-implementation-plan.md` | 被 H3 引用为取代者；H4–H10 头部指向它 → 保留 |
| H3 | `docs/product-v2-goal-and-implementation-plan.md` | `docs/product-v2-refactor-plan.md` | **现役引用**：plan:23（旧合同/C1–C17 来源）、context:124–125（SEL-000..013 操作设计出处）→ 保留 |
| H4–H10 | legacy renderer 横切 7 份（`架构设计`/`系统设计方案`/`设计复审`/`业务流程与提效设计`/`AI生图可控性与验证设计`/`实施计划`/`最小可行设计`/`使用形态`/`业务逻辑`——实际 9 份 H4–H12） | demo 计划 / Product V2 计划 | INDEX §4 及 README:234 点名保留为“第一手设计与故障轨迹”；`设计复审`自述“收敛后应当删除”但 INDEX 已裁定统一保留为 superseded、删除另立任务（INDEX:143–145）→ 保留 |
| H13–H18 | `docs/drafts/` 6 份（slots-v3、slots-v4、arch-v4-骨架、adr-0001、devplan-v4、ref-mining、requirements-analysis——实际 7 份） | demo 计划 / slots-v4 取代 slots-v3 | INDEX §1“默认不读 drafts”；内容已被 demo 计划吸收 → 保留 |
| H19 | `_working/amz-listing-kit-product-v1/state.md` | product-demo state | H20 头部指向；state 证据链起点 → 保留 |
| H20 | `_working/amz-listing-kit-product-demo/state.md` | product-v2 current state | 被 H1(8)/H2(82/825) 历史正文指向；INDEX 登记 D-1..D4.12 证据 → 保留 |
| H21 | `_working/amz-listing-kit-product-v2-baseline/state.md` | current state | **现役引用**：plan:24（旧进度/Goal 读数出处）、state:86（R0.1 证据）→ 保留 |
| H22 | `_working/amz-listing-kit-requirements/state.md` | product-demo state | 需求阶段轨迹唯一存档 → 保留 |
| H23–H27 | product-v2 tasks 5 份（r42-r52、v255-server、v255-verifier、v2ui2、v273） | current state / 重构计划 R7.2 | **现役引用**：v255-verifier:24→v255-server（同批并行实现互引）；其余由 state phase_progress 证据链及 plan §12 任务史引用 → 保留 |
| H28–H31 | product-demo tasks 4 份 + implementation-plan-2026-09-26 | V2 走查/矩阵 / V1 v2.3 工作空间 | D4.2/D4.3/D4.13/D4.14 完成边界唯一存档 → 保留 |

（计数：H 共 3 计划 + 9 横切 + 7 drafts + 13 _working = 32；A6+B8+C19+H32 = 65 登记口径，
另 +INDEX 自身 current = 66 受管文件。INDEX 登记表含自身行；守卫“65/65”口径见 §5。）

