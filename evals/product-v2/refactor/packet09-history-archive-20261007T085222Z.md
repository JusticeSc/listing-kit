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

## 3. INDEX 引用逐条去向（登记表 65 行 + 正文引用）

- 登记表 65 行：逐行 `git ls-files` + 磁盘存在性核对——**全部存在，零断链**
 （`git -C amz-listing-kit -c core.quotepath=false ls-files 'docs/cards/*'
  'docs/standards-template/*'` 命中 cards 8 + templates 15；`ls-files | wc -l`=66 含根两份；
  check_docs 报“已登记 65 份，实际 65 份”全过即双向比对无增删）。
- 去向分类：现役 6（§2.1）/ 生成 8（§2.2）/ 草案 19（§2.3）/ 历史 32（§2.4）——
  登记状态与各文件头 CONTROL-STATUS 逐份一致（reader 侧 grep 27 命中 + shell 侧 ASCII 路径
  38 份一致；CJK 路径 11 份经 reader 复核一致，shell NONE 系引号转义假象）。
- 正文引用（§1 路由表 8 行 + §4/§5）：`docs/product-v2-project-context.md`、
  `docs/product-v2-refactor-plan.md`、`docs/product-v2-refactor-design.md`、
  `_working/amz-listing-kit-product-v2/state.md`、`README.md` 均指向现役（§2.1）；
  “旧计划/旧 state/drafts/standards-template 默认不读”指向历史/草案——定性正确，
  **无一处需修正或改标**。
- **不造假链接**：本片未新增/修改任何链接；存在性断言全部来自
  `check_docs --no-run`（退出码 0）+ `git ls-files` 输出，非推测。

## 4. 归档/移动/删除前置检查（搜索证据）

设计 §8 准入：“不得移动仍被权威引用的路径”。现役权威对历史材料的有效引用：

1. `docs/product-v2-refactor-plan.md:23` → H3（旧合同/C1–C17 来源）
2. `docs/product-v2-refactor-plan.md:24` → H21（旧进度/Goal 读数出处）
3. `docs/product-v2-project-context.md:124-125` → H3（SEL-000..013 操作设计出处）
4. `_working/amz-listing-kit-product-v2/state.md:86` → H21（R0.1 证据）
5. `_working/amz-listing-kit-product-v2/tasks/v255-verifier.md:24` → v255-server.md（同批任务书互引）
6. `docs/product-v2-refactor-plan.md:351,651` → C1 ui-contract（草案投影引用，非历史但同属“被引用不得移”）
7. `AGENTS.md:30-44,158,162,166` → C5–C19 及 C2–C4（采纳映射与技能条件引用）

grep 命令（仓库根 `amz-listing-kit/` 下执行，证据为本报告 §2–§3 所列 `path:line` 命中）：

- `grep pattern="goal-and-implementation-plan|drafts/|tasks/[a-z0-9]|implementation-plan-2026|requirements/state|product-v1/state|product-demo/state|v2-baseline/state" path={plan,context,design,ui-contract,README,AGENTS,state}` → 命中 plan:23/24、context:124-125、state:86、v255-verifier:24（其余为 INDEX 登记行与历史文件互引）。
- `grep pattern="ui-contract|agents/issue|agents/triage|agents/domain|架构设计|系统设计|…" path={plan,context,README,AGENTS,state}` → 命中 plan:351/651、AGENTS:42/53/158/162/166。

**结论**：7 组现役引用有效 → 32 份历史 + 19 份草案全部“有现役引用或登记链依赖”，
按指令“有现役引用则保留并列入报告”——**本片零移动/零删除**，改动清单为空（§6）。

## 5. 七闸门（逐条命令 + 退出码，真跑）

| # | 命令（`amz-listing-kit/` 下） | 退出码 |
|---|---|---|
| 1 | `node --check app/product_v2/workspace.js` | 0 |
| 2 | `npm run build:frontend`（EMIT 5 视图文件，tail 确认） | 0 |
| 3 | `npm run check:types`（`tsc --noEmit -p jsconfig.json`） | 0 |
| 4 | `npm run check:generated`（CHECK 5 视图文件） | 0 |
| 5 | `node --test evals/product-v2/node/*.test.mjs`（tests 227 / pass 227 / fail 0） | 0 |
| 6 | `uv run --locked python tools/check_project_state.py`（J4–J10 全过） | 0 |
| 7 | `uv run --locked python tools/check_docs.py --no-run`（登记 65/实际 65，全过） | 0 |

注：本片未触 `tools/**`、`app/**`、`src/**`、`evals/product-v2/node/**`；
闸门 1–6 结果与 sibling 包共用树状态一致，无本片引入的变更可归因。

## 6. 改动清单

- 新增：本证据文件 1 份（`evals/product-v2/refactor/packet09-history-archive-20261007T085222Z.md`）。
- 修改/移动/删除：**无**（理由见 §1/§4）。
- `state.md`：progress 与任务表未动，未追加归档说明（无搬迁发生，无说明可加）。
- commit：`git add` 仅本证据文件，信息含 `packet09`，不 push（见 yield 报告）。

## 7. 未决项

1. 登记计数口径：INDEX 称受管“根+docs+_working 全部 .md”，check_docs 报 65/65，
   而 `git ls-files docs+_working+README+AGENTS` 实际 66（含 INDEX 自身）。
   差 1 疑为守卫计数不含 INDEX 自身或含根方式不同——非本片引入，不改守卫，
   留待包09收口或守卫owner澄清。
2. CJK 路径 shell 测量假象：`for f in $(git ls-files …)` + `head` 在 win32 上对
   中文路径报 os error 123（引号转义），reader 侧 grep 同文件 CONTROL-STATUS 正常命中。
   后续脚本应从 git 侧取 `core.quotepath=false` 原字节或用 reader/grep 工具，勿据 shell NONE 判缺头。
3. 物理归档（如 `_archives/` 精确字节归档 + hash 核对 + 引用同步）需按设计 §8
   “只对有权限的过程材料执行”另立任务：先消 §4 的 7 组现役引用（改权威正文=改计划/context，
   须快照+用户确认），再出精确移动清单。本片不做。
