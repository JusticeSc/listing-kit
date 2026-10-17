# 项目上下文与文档权威入口

> CONTROL-STATUS: current · AUTHORITY: context-routing
> **任何人或 Agent 进入项目先读本文件，但不在这里复制目标、状态或实现正文。**
> 本文件只做路由与身份登记；文件存在但没登记、登记文件不存在、同类事实有多个权威都会由
> `tools/check_docs.py` 报红。

---

## 1. 从这里开始：一类事实，一个权威

| 要回答的问题 | 唯一权威 | 其他地方只允许 |
|---|---|---|
| Goal 现在运行、暂停还是完成 | 真实系统Goal；产品绑定与观察指针在 `_working/amz-listing-kit-product-v2/state.md` | 历史active不替代实时读数；独立设计Goal不覆盖产品停工；原生全文取计划§2.1，用户修订另见§17.13，不伪称原生正文已更新 |
| 项目是什么、运行边界、数据与目录归谁 | `docs/product-v2-project-context.md` | 计划和 README 只链接，不复制项目身份、目标运行时或数据所有权 |
| 产品终点、正式任务/阶段依赖、准出是什么 | `docs/product-v2-refactor-plan.md` | 按ID引用；具体Issue验收承接产品终点，不复制完整Goal或另立一张总任务图 |
| Module/事务设计与交互/Prompt质量如何实现 | `docs/product-v2-refactor-design.md` | 当前规格§13，界面读2026-10-16修订§13.3；旧§10–11仅追溯经当前证据确认仍适用的差量，不能据旧owner清单重做；不由设计推导施工许可 |
| 产品门、权限、阻塞和唯一恢复前沿是什么 | `_working/amz-listing-kit-product-v2/state.md` | 不另建产品机器状态；历史审计或独立设计记录不能发布当前状态 |
| 具体问题、验收与改动审查进展是什么 | GitHub Issue及关联PR；工作流只取`AGENTS.md` | plan/state只保留正式任务关联、权限、恢复与证据指针，不复制工单明细；远程写入须在当次授权内 |
| 现有代码实际上能做什么 | `README.md` 指向的代码、配置与验证入口 | 目标计划不得把未实现能力写成当前实现 |
| 哪份文档有效、历史还是待删 | 本文件 | 各文件只声明自己的 CONTROL-STATUS，不建立另一张总表 |
| 某次检查或实验实际发生了什么 | `evals/` 下对应原始产物和时点报告 | 只作证据，不发布后续计划、当前状态或新规范 |

恢复只按此顺序：**本文件 → AGENTS.md → 当前state与真实Goal → 项目上下文 → 计划§17.13及state指向的任务卡 → 关联Issue/PR与选中证据 → 受影响设计§13/代码**。2026-10-17用户明确启动独立main基线本地工程，V1清退纳入基线；P0–P8实施包唯一取[Issue #10](https://github.com/JusticeSc/listing-kit/issues/10)，测试与反馈细项取#7。封存下一版WIP不混入本轮，原产品仍paused且终点未取消；精确额度、权限与恢复点只取state，不从旧停工或旧启动记录推导本次许可。只读必要证据，不重审全库或重做已成立资产。

`prepared`时按计划§2完成绑定，未绑定不施工；`paused`/用户停工时只做本次明确另行授权的工作。运行`uv run --locked python tools/refactor_resume.py`取得只读前沿，不把命令成功、旧启动记录、skill的publish指令或一个含糊“继续”当作扩大当前授权。明确恢复产品后，仍逐项遵守费用、素材、秘密、不可逆数据、提交/推送、清退与发布门。

当前目标以计划为准，计划准备完成不等于重构完成，也不自动改变旧系统 Goal 生命周期。
普通准备不创建产品Goal。当前正式Goal绑定、原生观察与恢复点只取state，目标/授权与实施合同只取计划§2.1/§17；早期独立规划Goal和历史启动记录保留其原证明范围，不替代当前验收或成为重复启动依据。

下一版本规格定向读 `docs/product-v2-refactor-design.md` §13；准备和必要本地基线实验的历史见 `_working/amz-listing-kit-next-version-design/discussion.md`，不是第二份原工程执行状态。正式启动后的实施与权限只取计划§2.1/§17，进度与恢复只取state；历史准备的权限边界不冒充当前授权，也不豁免当前依赖、准出或真人门。

---

## 2. 登记表

> 受管范围：根目录（`README.md`、`AGENTS.md`）+ `docs/` + `_working/` 下的全部 `.md`——每份都在本表登记，
> 非生成文档顶部必须有与登记一致的 `CONTROL-STATUS`（`tools/check_docs.py` 双向比对 + 唯一权威校验）。
> `evals/` 与 `_stage-amz-control/` 是证据与快照产物，不参与“哪一份有效”的登记。

| 路径 | 世代 | 管辖事实 | 状态 | 说明 |
|---|---|---|---|---|
| `README.md` | Product V2 | `实现` | `current` | 当前实现的人读入口：唯一V2、锁定构建/启动/验证及同版本恢复；main/分支/发布身份只取state和实际PR证据 |
| `AGENTS.md` | Product V2 | `项目规则` | `current` | Agent 工作规则与选型门禁（Reuse-first）的唯一权威；目标、技术栈、状态分别链接到各自权威，不复制正文 |
| `docs/product-v1-goal-and-implementation-plan.md` | Product V1 | `历史证据` | `superseded` | 被 `docs/product-demo-goal-and-implementation-plan.md` 取代；真实试点假设不再作为当前完成标准 |
| `_working/amz-listing-kit-product-v1/state.md` | Product V1 | `历史证据` | `superseded` | 被 `_working/amz-listing-kit-product-demo/state.md` 取代；保留上一轮执行位置，不据以继续开工 |
| `docs/drafts/requirements-analysis-2026-09-24.md` | 演示产品需求发现 | `历史证据` | `superseded` | 结论已并入 `docs/product-demo-goal-and-implementation-plan.md`；保留面试证据、推导过程与未知项来源 |
| `_working/amz-listing-kit-requirements/state.md` | 演示产品需求发现 | `历史证据` | `superseded` | 被 `_working/amz-listing-kit-product-demo/state.md` 取代；保留需求阶段完成轨迹 |
| `docs/product-demo-goal-and-implementation-plan.md` | Product V1 v2.6 | `历史证据` | `superseded` | 被 `docs/product-v2-goal-and-implementation-plan.md` 取代；服务器文件夹工作空间与 D4.13/D4.14 不再驱动当前开发 |
| `_working/amz-listing-kit-product-demo/state.md` | Product V1 v2.6 | `历史证据` | `superseded` | 被 `_working/amz-listing-kit-product-v2/state.md` 取代；保留 D-1 至 D4.12 的完成证据，不据此继续 D4.13 |
| `docs/product-v2-project-context.md` | Product V2 | `架构设计` | `current` | Product V2 项目身份、运行边界、数据所有权、技术栈、目录地图和质量门槛的唯一上下文入口 |
| `docs/product-v2-goal-and-implementation-plan.md` | Product V2 重构前基线 | `历史证据` | `superseded` | 被 `docs/product-v2-refactor-plan.md` 接管未来目标与任务；保留旧合同、C1–C17 和旧 Goal 原文，不据此继续 V2.7.3 |
| `docs/product-v2-refactor-plan.md` | Product V2定向重构 | `产品目标` | `current` | §2.1原生Goal观察正文；§17.13当前main基线范围/权限修订，具体P0–P8只取#10、测试只取#7；§6/§9/§10原产品正式任务/依赖/准出保留，规划不签原Goal完成 |
| `docs/product-v2-refactor-design.md` | Product V2联合结构重构 | `架构设计` | `current` | 当前§13普通决定/两模式及视觉简报/人因验收；§12仅作当前路由，§10–11旧算法/实施差距按未变前提复用。规格不冒称实现、Goal或当前权限 |
| `_working/amz-listing-kit-product-v2-baseline/state.md` | Product V2 重构前基线 | `历史证据` | `superseded` | 被 current state 接管；保留旧进度与旧 Goal 的最近实际读数，不发布下一动作 |
| `docs/product-v2-ui-contract.md` | Product V2 V2.UI.2 | `设计草案` | `draft` | 人工/辅助共享任务及有限设置投影；§8区分设计范围、工程与C17/C15，业务合同取计划§14。转current需产品发起人实际走查，之后转 `架构设计` 并补§1路由；工程自审不冒充签署 |
| `_working/amz-listing-kit-product-v2/state.md` | Product V2 定向重构 | `执行状态` | `current` | 唯一进度、证据、真实 Goal 绑定与下一动作；prepared 仅表示真正未观察/未确认，不冒充系统状态；旧观察不等于本会话重读 |
| `_working/amz-listing-kit-product-v2/tasks/r42-r52-volcengine-closure-20261003.md` | Product V2 R4.2/R5.2 火山真实链 | `历史证据` | `superseded` | R4.2/R5.2 已完成并记录进 current state；笔记保留本轮付费/修复/验证事实与证据指针，不据此执行 |
| `_working/amz-listing-kit-product-v2/tasks/v255-server.md` | Product V2 V2.5.5 | `历史证据` | `superseded` | V2.5.5 已完成；任务书只保留当时的服务端施工边界，不再据此执行 |
| `_working/amz-listing-kit-product-v2/tasks/v255-verifier.md` | Product V2 V2.5.5 | `历史证据` | `superseded` | V2.5.5 已完成；任务书只保留当时的验证施工边界，不再据此执行 |
| `_working/amz-listing-kit-product-v2/tasks/v2ui2-interaction-visual.md` | Product V2 V2.UI.2 | `历史证据` | `superseded` | V2.UI.2 已完成；任务书只保留当时的交互与视觉施工边界，不再据此执行 |
| `_working/amz-listing-kit-product-v2/tasks/v273-walkthrough-kit.md` | Product V2 V2.7.3 基线 | `历史证据` | `superseded` | 被重构计划 V2.R7.2 最终人审任务接管；旧脚本仅供任务参考，旧人审未完成、不转为通过 |
| `_working/amz-listing-kit-product-demo/tasks/brief-d42-usability-a11y.md` | Product V1 D4.2 | `历史证据` | `superseded` | D4.2 已完成；任务书只保留当时边界和执行约束，不再驱动当前施工 |
| `_working/amz-listing-kit-product-demo/tasks/brief-d43-backup-restore.md` | Product V1 D4.3 | `历史证据` | `superseded` | D4.3 已完成；任务书只保留当时边界和执行约束，不再驱动当前施工 |
| `_working/amz-listing-kit-product-demo/tasks/d4.13-first-user-walkthrough-kit.md` | Product V1 D4.13 | `历史证据` | `superseded` | 被 Product V2 的 V2.7.3 首次使用者走查取代；旧工具包只保留任务设计参考 |
| `_working/amz-listing-kit-product-demo/tasks/d4.14-completion-matrix-draft.md` | Product V1 D4.14 | `历史证据` | `superseded` | 被 Product V2 完成证据矩阵与 V2.7.4 发布审计取代；旧盘点不作当前完成依据 |
| `_working/amz-listing-kit-product-demo/implementation-plan-2026-09-26.md` | 完整演示产品 v1.14 | `历史证据` | `superseded` | 旧执行细节快照；已被 Product V1 v2.3 工作空间与动态编译计划取代，不据此继续开工 |
| `docs/架构设计.md` | v2 | `历史证据` | `superseded` | 被 `docs/product-demo-goal-and-implementation-plan.md` 的目标架构取代；当前 v2 实现以 README 和代码为准 |
| `docs/系统设计方案.md` | legacy renderer v2 | `历史证据` | `superseded` | 被 Product V2 计划取代；其中“主体抠图 + 固定图位 + 单格生成”只解释旧路线，不是当前架构 |
| `docs/设计复审.md` | legacy renderer v2 | `历史证据` | `superseded` | 被 Product V2 计划取代；保留旧路线矛盾与收敛过程，不据此开工 |
| `docs/业务流程与提效设计.md` | legacy renderer v2 | `历史证据` | `superseded` | 被 Product V2 产品合同与用户工作流取代；固定七图和单次模型调用不再有效 |
| `docs/AI生图可控性与验证设计.md` | legacy renderer v2 | `历史证据` | `superseded` | 被 Product V2 Prompt、Provider 与分层校验合同取代；“模型只生成背景”不是当前边界 |
| `docs/实施计划.md` | legacy renderer v2 | `历史证据` | `superseded` | M0–M7 是旧表驱动渲染器的已完成轨迹；当前施工只按 Product V2 唯一任务表 |
| `docs/最小可行设计.md` | legacy renderer v2 | `历史证据` | `superseded` | 被 Product V2 计划取代；固定七坑位、主体抠图和旧返工成本口径均不再有效 |
| `docs/使用形态.md` | legacy renderer v2 | `历史证据` | `superseded` | 被 Product V2 用户可见工作流取代；旧五步页只作历史交互证据 |
| `docs/业务逻辑.md` | legacy renderer v2 | `历史证据` | `superseded` | 被 Product V2 对象、状态与人工采纳合同取代；旧坑位业务模型不再驱动当前产品 |
| `docs/drafts/slots-v4-generation-first.md` | v4 | `历史证据` | `superseded` | 被完整演示产品计划取代；固定七格与旧切换顺序不得作为当前任务来源 |
| `docs/drafts/arch-v4-骨架.md` | v4 | `历史证据` | `superseded` | 被完整演示产品计划的目标架构取代；保留当时取舍证据 |
| `docs/drafts/adr-0001-骨架选型.md` | v4 | `历史证据` | `superseded` | 结论已被完整演示产品计划重新裁定；不再是当前 ADR |
| `docs/drafts/ref-mining-ecom-2026-09-23.md` | Product V1 | `历史证据` | `superseded` | 已采纳内容进入完整演示产品计划；范例挖掘只保留为来源记录，不作判据或任务卡 |
| `docs/drafts/devplan-v4.md` | v4 | `历史证据` | `superseded` | 早期由 Product V1 计划替代，最终由当前 `docs/product-demo-goal-and-implementation-plan.md` v2.6 接管；保留为生成优先路线的历史设计证据，不再作为开工顺序 |
| `docs/drafts/slots-v3-proposal.md` | v3 | `历史证据` | `superseded` | 被 `docs/drafts/slots-v4-generation-first.md` 取代 |
| `docs/standards-template/README.md` | 外部参考模板 | `设计草案` | `draft` | 外部课程模板原样副本；本项目按 `AGENTS.md` §Standards Mapping 适配其要求，模板自身只作参考 |
| `docs/standards-template/00-project-context.md` | 外部参考模板 | `设计草案` | `draft` | 项目身份与技术栈模板；对应权威为 `docs/product-v2-project-context.md`（已含选型记录与依赖登记） |
| `docs/standards-template/01-requirements.md` | 外部参考模板 | `设计草案` | `draft` | 活PRD与验收写法模板；对应计划§14业务合同、§6/§9任务和§10完成矩阵 |
| `docs/standards-template/02-coding-standards.md` | 外部参考模板 | `设计草案` | `draft` | 编码标准；已适配进 `AGENTS.md` 的 Coding Style；未采用 ruff，理由与替代写在项目上下文 §7 质量门槛 |
| `docs/standards-template/03-testing-standards.md` | 外部参考模板 | `设计草案` | `draft` | 测试模板；按计划§7.3/§15.3及AGENTS风险导向验证适配，不设覆盖率阈值 |
| `docs/standards-template/04-git-workflow.md` | 外部参考模板 | `设计草案` | `draft` | Git/PR模板；现有分支和CI/保护要求、获批合并方式只读AGENTS对应章节 |
| `docs/standards-template/05-cicd-standards.md` | 外部参考模板 | `设计草案` | `draft` | CI/CD 标准；Docker + GitHub Actions + SSH 部署的采纳差异与 SEL-005 映射在 `AGENTS.md` §Standards Mapping |
| `docs/standards-template/06-ai-collab-protocol.md` | 外部参考模板 | `设计草案` | `draft` | AI协作协议；选型/确认门的采纳差异只取AGENTS的Standards Mapping与Selection Gate，不再解释成每到state下一动作都等待用户确认 |
| `docs/standards-template/07-dependency-standards.md` | 外部参考模板 | `设计草案` | `draft` | 依赖与复用阶梯；已适配进 `AGENTS.md` §Selection Gate 与项目上下文 §4.2 依赖登记（版本锁定 + 许可证） |
| `docs/standards-template/PROGRESS.md` | 外部参考模板 | `设计草案` | `draft` | 状态机与决策记录模板；对应权威为 `_working/amz-listing-kit-product-v2/state.md`，决策在项目上下文 §4.1 |
| `docs/standards-template/templates/ISSUE_TEMPLATE.md` | 外部参考模板 | `设计草案` | `draft` | 内容要求已采纳到`AGENTS.md`提交/PR规则；生效条件：按当前工作流开具体Issue，不复制外部表单为第二份任务权威 |
| `docs/standards-template/templates/PR_TEMPLATE.md` | 外部参考模板 | `设计草案` | `draft` | 内容要求已采纳到`AGENTS.md`；生效条件：最小完整改动即Draft PR，用当前可用的`pr` skill组织证据，不要求另安装/启用技能 |
| `docs/standards-template/templates/TECH_SELECTION.md` | 外部参考模板 | `设计草案` | `draft` | 选型报告模板；本项目用 `AGENTS.md` 的字段清单 + 项目上下文 §4.1 决策行承载，不单独立文件 |
| `docs/standards-template/templates/ADR_TEMPLATE.md` | 外部参考模板 | `设计草案` | `draft` | ADR 模板；本项目以项目上下文 §4.1 的 SEL 行（含复访条件）代替独立 `docs/adr/` 目录 |
| `docs/agents/issue-tracker.md` | 工程技能操作参考 | `设计草案` | `draft` | 只提供GitHub/gh及可选wayfinder操作；生效条件：AGENTS当前流程需要该操作且授权允许时核对采用，不再要求用户先启用技能；不独立授权或禁止产品Issue |
| `docs/agents/triage-labels.md` | 工程技能 | `设计草案` | `draft` | 可选triage角色映射；生效条件：实际任务需要且可用的triage技能被匹配、对应远程操作已获授权时采用，不要求用户先手工启用 |
| `docs/agents/domain.md` | 工程技能 | `设计草案` | `draft` | 单上下文术语/ADR的条件参考；实际需要且创建后才采用。当前决策仍取项目上下文SEL行，不为使用技能另建目录 |
| `docs/agents/ai-coding-loop.md` | 工程技能操作参考 | `设计草案` | `draft` | 用户亲授AI协作六环（选→说→切→验→因→学）；AGENTS一行指针引用，六环切法为用户归纳、四条定律有据可查，不独立授权 |

---

## 3. 状态取值（closed set，守卫会校验）

| 状态 | 含义 | 额外要求 |
|---|---|---|
| `current` | 当前有效，读者据此行事 | —— |
| `generated` | 由脚本生成 | 说明列必须写明**生成器** |
| `draft` | 设计草案，**未进控制面** | 说明列必须写明**生效条件** |
| `superseded` | 已被取代，保留为证据 | 说明列必须写明**被谁取代** |
| `to-delete` | 待删 | 说明列必须写明**删除前置条件** |

### 3.1 管辖事实取值（closed set，守卫会校验）

「状态」回答**这份文件还算不算数**；「管辖事实」回答**这份文件对哪一类事实说了算**。
两个都要有 —— 一份文件可以既有效（`current`）又只对某一类事实有权威。

| 管辖事实 | 含义 | 唯一性 |
|---|---|---|
| `实现` | 代码**当前真做什么** | **全表唯一** |
| `产品目标` | 要做到什么、什么算完成 | **全表唯一** |
| `执行状态` | 当前推进到哪、下一步做什么 | **全表唯一** |
| `架构设计` | 目标架构与技术选型 | 可多份 |
| `设计草案` | 未进控制面的设计前沿 | 可多份 |
| `历史证据` | 保留作证据，不据以行事 | 可多份 |
| `生成产物` | 由脚本生成，不手改 | 可多份 |
| `待处置` | 待删 / 待落点核对 | 可多份 |

**为什么前三类必须唯一**：本仓库真实并存过「README 说 v2 是当前实现」与
「`docs/架构设计.md` 写着已被 v4 取代」。它们其实回答的是**不同的问题** ——
写出管辖事实之后，那种并存是分工，不是矛盾；而**同一个问题上出现两个出处**，
守卫直接报红（`tools/check_docs.py` 的 `SINGLETON_KINDS`）。

**为什么 `_working/` 也在受管范围内**：执行状态和"哪份文档有效"一样，
是读者要据以行事的事实。它此前不在扫描范围里，于是"下一步做什么"
没有任何机器可查的权威登记 —— 这正是本次校准要堵的洞。

旧横切文档不再处于无限期的“待删”状态：它们包含旧架构的第一手设计与故障轨迹，统一保留为
`superseded / 历史证据`。读者默认不读；只有追溯 Product V1/legacy renderer 决策时才从本表进入。
未来若要物理删除，删除本身另立任务并以 Git 历史或归档包为恢复手段，不把它混入当前产品开发。

---

## 4. 这份登记自己也要能被证伪

不是"写了就有用"。两个动作应当让它变红，且**只在该红的地方红**：

| 动作 | 期望 |
|---|---|
| 在 `docs/` 或根目录新建一个 `.md` 而不登记 | 报「未登记」，退出码 1 |
| 从本表删掉某一行、而那份文件还在 | 报「未登记」 |
| 登记一份不存在的文件 | 报「登记了但文件不在」 |
| 把状态写成 `done` / `OK` / 任意自由文本 | 报「状态不在取值域」 |
| 给 `draft` / `superseded` / `to-delete` 写空说明 | 报「说明列为空」 |
| 管辖事实列写成自由文本（如 `参考`） | 报「管辖事实不在取值域」 |
| 给「实现 / 产品目标 / 执行状态」任一类写第二个出处 | 报「只能有一个权威」 |
| 某一类事实在表里一个出处都没有 | 报「没有任何出处」 |
| 非生成文档没有在顶部声明 `CONTROL-STATUS` | 报「单看文件无法知道是否有效」 |
| 文件顶部 `CONTROL-STATUS` 与本表登记不一致 | 报「两处身份不一致」 |
| 在 `_working/` 新建 `.md` 而不登记 | 报「未登记」 |

**本表正文不写死份数**（不写"仓库里共 N 份"）。份数是本表的**派生值** —— 表就是清单，
数一遍就有；写进正文则多出一个**没人守的声明**，下次新增文档它立刻变成假情报。
（同型事故上一轮刚在 README 抓到一个：写着「回归 12 项」而实际 13 项。
两处处置不同，判据是**有没有读者真的需要这个数**：README 的"回归 N 项"是操作信息
⇒ 加判据守住它；本表正文的份数是装饰 ⇒ 消除它。**加判据与消除声明都能修好漂移，
选哪个看这个数是不是真的有人读。**）

新增文档时的规矩只有一条：**先在本表登记，再写文件**（顺序反了守卫也会拦住，只是晚一步）。

---

## 5. 写入路由：改哪里，不改哪里

| 发生的变化 | 只修改 | 禁止顺手复制到 |
|---|---|---|
| Goal 生命周期变化 | 系统 Goal；随后把读数写入 current state | 产品计划、审计报告 |
| 产品目标、范围、完成条件或正式任务依赖变化 | 产品计划；原生Goal正文只记录真实观察，差量与冲突明确标出 | state、README、eval报告里的第二份目标 |
| 工作方式/Issue与PR/skill执行规则变化 | `AGENTS.md`；本INDEX及技能参考只调整指针 | 产品任务卡、聊天里的另一套流程 |
| 技术选型、所有权或实现设计变化 | 项目上下文§4或详细设计相应节；产品边界受影响时再修计划 | AGENTS里的第二份架构/产品目标 |
| 产品门、阻塞、证据或恢复动作变化 | current state；具体问题进展更新对应Issue/PR | 产品计划正文、历史审计或本地工单明细副本 |
| 代码已经实现的新行为 | 代码/配置/测试，并同步 README 的实现说明 | 旧架构、旧计划或 draft |
| 一次实验、回归或审计结果 | `evals/` 对应时点证据，并由 state 引用 | 当前状态、未来计划 |
| 文档身份变化 | 本 INDEX，并同步目标文件顶端 CONTROL-STATUS | 另一份索引或聊天记忆 |

`config/slots.yaml` 仍只管 legacy v2 的坑位行为；它不是完整演示产品的目标或执行控制面。

**改权威文档之前先留一份快照。** `docs/`、`_working/` 与 `README.md` 是读者据以行事的事实，
一旦被覆盖，上一版就只存在于记忆里。这不是假设：2026-09-26 想把计划 v1.6 与 v1.7 逐行对比时，
仓库里已经没有 v1.6 的副本，只能靠改它的那段脚本反推。所以定一条规矩：改这几份文件之前，
先在工作区外留一份快照（`_stage-amz-control/<用途>-<时间戳>/`），改完把前后哈希写进证据。
