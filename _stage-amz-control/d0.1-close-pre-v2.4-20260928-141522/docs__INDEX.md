# 项目上下文与文档权威入口

> CONTROL-STATUS: current · AUTHORITY: context-routing  
> **任何人或 Agent 进入项目先读本文件，但不在这里复制目标、状态或实现正文。**
> 本文件只做路由与身份登记；文件存在但没登记、登记文件不存在、同类事实有多个权威都会由
> `tools/check_docs.py` 报红。

---

## 1. 从这里开始：一类事实，一个权威

| 要回答的问题 | 唯一权威 | 其他地方只允许 |
|---|---|---|
| Goal 现在运行、暂停还是完成 | 系统 Goal `01a0ca17-2179-7eb0-969a-af9c79c4d8ca` | 记录最后一次读数，不自行改写生命周期 |
| 要做成什么、什么算完成、阶段/任务怎样依赖 | `docs/product-demo-goal-and-implementation-plan.md` | 按 ID 引用，不复制目标、Gate、任务定义或依赖 |
| 当前做到哪、证据在哪、唯一下一动作是什么 | `_working/amz-listing-kit-product-demo/state.md` | 历史审计只能保存当时快照，不发布“当前状态” |
| 现有代码实际上能做什么 | `README.md` 指向的代码、配置与验证入口 | 目标计划不得把未实现能力写成当前实现 |
| 哪份文档有效、历史还是待删 | 本文件 | 各文件只声明自己的 CONTROL-STATUS，不建立另一张总表 |
| 某次检查或实验实际发生了什么 | `evals/` 下对应原始产物和时点报告 | 只作证据，不发布后续计划、当前状态或新规范 |

恢复工作时只按这个顺序读：**本文件 → 当前 state → state 指向的下一任务在产品计划中的任务卡 → 该任务证据 → 相关代码**。默认不读 `drafts/`、旧计划、旧 state 或横切面文档。

---

## 2. 登记表

| 路径 | 世代 | 管辖事实 | 状态 | 说明 |
|---|---|---|---|---|
| `README.md` | v2 | `实现` | `current` | 当前实现的人读入口，只描述已落地 v2 与明确的新 demo 代码；项目目标和状态分别链接到各自权威 |
| `docs/product-v1-goal-and-implementation-plan.md` | Product V1 | `历史证据` | `superseded` | 被 `docs/product-demo-goal-and-implementation-plan.md` 取代；真实试点假设不再作为当前完成标准 |
| `_working/amz-listing-kit-product-v1/state.md` | Product V1 | `历史证据` | `superseded` | 被 `_working/amz-listing-kit-product-demo/state.md` 取代；保留上一轮执行位置，不据以继续开工 |
| `docs/drafts/requirements-analysis-2026-09-24.md` | 演示产品需求发现 | `历史证据` | `superseded` | 结论已并入 `docs/product-demo-goal-and-implementation-plan.md`；保留面试证据、推导过程与未知项来源 |
| `_working/amz-listing-kit-requirements/state.md` | 演示产品需求发现 | `历史证据` | `superseded` | 被 `_working/amz-listing-kit-product-demo/state.md` 取代；保留需求阶段完成轨迹 |
| `docs/product-demo-goal-and-implementation-plan.md` | Product V1 v2.3 | `产品目标` | `current` | **当前 Goal、完成判据、架构边界、阶段门与任务依赖的唯一权威；工作空间、动态编译与真实生成路线以此为准** |
| `_working/amz-listing-kit-product-demo/state.md` | Product V1 v2.3 | `执行状态` | `current` | 当前推进位置、完成证据、阻塞与唯一下一动作；阶段、任务和依赖只按 ID 引用产品计划 |
| `_working/amz-listing-kit-product-demo/implementation-plan-2026-09-26.md` | 完整演示产品 v1.14 | `历史证据` | `superseded` | 旧执行细节快照；已被 Product V1 v2.3 工作空间与动态编译计划取代，不据此继续开工 |
| `docs/架构设计.md` | v2 | `历史证据` | `superseded` | 被 `docs/product-demo-goal-and-implementation-plan.md` 的目标架构取代；当前 v2 实现以 README 和代码为准 |
| `docs/系统设计方案.md` | v2 | `待处置` | `to-delete` | 横切面，待知识落点核对（见 §3） |
| `docs/设计复审.md` | v2 | `待处置` | `to-delete` | 横切面，待知识落点核对 |
| `docs/业务流程与提效设计.md` | v2 | `待处置` | `to-delete` | 横切面，待知识落点核对 |
| `docs/AI生图可控性与验证设计.md` | v2 | `待处置` | `to-delete` | 横切面，待知识落点核对 |
| `docs/实施计划.md` | v2 | `待处置` | `to-delete` | 横切面，待知识落点核对（663 行，这批里最大一份） |
| `docs/最小可行设计.md` | v2 | `待处置` | `to-delete` | 横切面。**删之前必须先处置 §8「文案错 → 0.1s 免费」** —— 它随不变量 C 的删除失去实现（`slots-v4` §4.4 已记账），这行字目前是**唯一还写着旧口径**的地方 |
| `docs/使用形态.md` | v2 | `待处置` | `to-delete` | 横切面，待知识落点核对 |
| `docs/业务逻辑.md` | v2 | `待处置` | `to-delete` | 横切面，待知识落点核对 |
| `docs/cards/README.md` | v2 | `生成产物` | `generated` | 生成器 `tools/gen_slot_cards.py`；七格共有规矩 + 该读哪一张 |
| `docs/cards/slot-1.md` | v2 | `生成产物` | `generated` | 同上 |
| `docs/cards/slot-2.md` | v2 | `生成产物` | `generated` | 同上 |
| `docs/cards/slot-3.md` | v2 | `生成产物` | `generated` | 同上 |
| `docs/cards/slot-4.md` | v2 | `生成产物` | `generated` | 同上 |
| `docs/cards/slot-5.md` | v2 | `生成产物` | `generated` | 同上 |
| `docs/cards/slot-6.md` | v2 | `生成产物` | `generated` | 同上 |
| `docs/cards/slot-7.md` | v2 | `生成产物` | `generated` | 同上 |
| `docs/drafts/slots-v4-generation-first.md` | v4 | `历史证据` | `superseded` | 被完整演示产品计划取代；固定七格与旧切换顺序不得作为当前任务来源 |
| `docs/drafts/arch-v4-骨架.md` | v4 | `历史证据` | `superseded` | 被完整演示产品计划的目标架构取代；保留当时取舍证据 |
| `docs/drafts/adr-0001-骨架选型.md` | v4 | `历史证据` | `superseded` | 结论已被完整演示产品计划重新裁定；不再是当前 ADR |
| `docs/drafts/ref-mining-ecom-2026-09-23.md` | Product V1 | `历史证据` | `superseded` | 已采纳内容进入完整演示产品计划；范例挖掘只保留为来源记录，不作判据或任务卡 |
| `docs/drafts/devplan-v4.md` | v4 | `历史证据` | `superseded` | 早期由 Product V1 计划替代，最终由当前 `docs/product-demo-goal-and-implementation-plan.md` v2.3 接管；保留为生成优先路线的历史设计证据，不再作为开工顺序 |
| `docs/drafts/slots-v3-proposal.md` | v3 | `历史证据` | `superseded` | 被 `docs/drafts/slots-v4-generation-first.md` 取代 |

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

**"待删"的删除前置条件（README §11 的裁定，原文照抄，不另立）**：

> 删的时机是"有人照着卡干过一次活之后"—— 先删再补，等于把知识一次抹掉两次。

⚠ **这条前置条件目前不可判定**（"有人干过一次活"没有判据），所以 `to-delete` 那一批会一直停留在该状态
（**不写份数** —— 理由见 §4：份数是本表的派生值，数表即得，写进正文就多一个没人守的声明）。
把它写成可判定的形态是**另一个待办**（形态应为：逐份列出它的一级标题，标明每条在
卡 / README / drafts 里的落点；全部有落点之后删除才是安全的）。本文只如实登记状态，不假装它已解决。

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
| 目标、范围、完成条件、架构或任务依赖变化 | 产品计划 | state、README、eval 报告 |
| 任务完成、阻塞、证据或下一动作变化 | current state | 产品计划正文、历史审计 |
| 代码已经实现的新行为 | 代码/配置/测试，并同步 README 的实现说明 | 旧架构、旧计划或 draft |
| 一次实验、回归或审计结果 | `evals/` 对应时点证据，并由 state 引用 | 当前状态、未来计划 |
| 文档身份变化 | 本 INDEX，并同步目标文件顶端 CONTROL-STATUS | 另一份索引或聊天记忆 |

`config/slots.yaml` 仍只管 legacy v2 的坑位行为；它不是完整演示产品的目标或执行控制面。

**改权威文档之前先留一份快照。** `docs/`、`_working/` 与 `README.md` 是读者据以行事的事实，
一旦被覆盖，上一版就只存在于记忆里。这不是假设：2026-09-26 想把计划 v1.6 与 v1.7 逐行对比时，
仓库里已经没有 v1.6 的副本，只能靠改它的那段脚本反推。所以定一条规矩：改这几份文件之前，
先在工作区外留一份快照（`_stage-amz-control/<用途>-<时间戳>/`），改完把前后哈希写进证据。
