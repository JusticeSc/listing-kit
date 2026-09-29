# D1.P2 前半链合同验证（PC-01 – PC-07）

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY  
> 任务：D1.P2（计划 v1.6 §6.3）  
> 时间：2026-09-26T11:0x+08:00  
> 计划权威：`docs/product-demo-goal-and-implementation-plan.md` v1.6  
> 状态权威：`_working/amz-listing-kit-product-demo/state.md`

本报告只记录 D1.P2 实际做了什么、跑出了什么、以及这些证据不能证明什么。

## 1. 本任务要解决什么

D1.P1 把 §4.4 变成可核对的合同，但合同当时还只是「文本 + 身份契约」：没有任何实现，也就没有任何东西能证明这些合同**能被满足**，更没有东西能证明它们**不能被违反**。

D1.P2 就是把这个洞补上：给 PC-01–PC-07 一份真实能跑的实现，配一条黄金链和一组反向用例。判据不能证伪就等于装饰。

## 2. 实际产物

| 文件 | 作用 |
|---|---|
| `demo/core/contracts.py` | 结果词汇与状态取值的机器口径；`StepResult` 强制每一步只能返回该合同声明过的结果 |
| `demo/core/prompt.py` | PC-05 提示词编译器（数据驱动；编辑不许静默删锁） |
| `demo/core/prompt_profile.aster-01.json` | 从已发提示词**派生**的短语料（派生而不是手抄，见 §3） |
| `demo/core/front_chain.py` | PC-01–PC-07 实现；规则抽成 `fact_problems` / `claim_problems` 便于单独削弱 |
| `demo/core/run_front_contracts.py` | 契约测试：黄金链 + 16 条反例 + 变异测试 |
| `evals/product-demo/d1-p2/front-contracts.json` | 本次运行的机器可读报告 |

## 3. 提示词编译器：从实验脚本提升为产品编译器

D1.4 的提示词原本由 `demo/provider/run_first_round.py` 里一个内联函数生成 —— 正文写死在代码里。D1.P2 把它变成**数据驱动**的编译器，并且**删掉了内联那一份**，让编译逻辑只有一处。

提升是否等价，不靠人眼比对：

| 检查 | 结果 |
|---|---|
| `python demo/provider/run_first_round.py --plan-only`（委托给新编译器后） | 1985 字符 · sha `d339c104b20a02c7…` |
| `evals/product-demo/first-round/manifest.json` 记录 | 1985 字符 · sha `d339c104b20a02c7…` |
| `prompt_text` 是否逐字相同 | 是 |
| `negative_prompt` 是否相同 | 是（负向提示词也改为只从 profile 读，不再有第二份） |

也就是说：换掉实现之后，**真实发出去的那条提示词被逐字节重建**。

副作用（如实记录）：`--plan-only` 重写了 `evals/product-demo/first-round/plan.json`（可再生的计划产物），新版本多了 `profile_version/shot_id/style_id/scene_id/composition_id/version_id` 等溯源字段；`prompt_text` 与 `prompt_sha256` 与冻结记录一致。**付费运行的 `manifest.json`、`attempts/`、`ledger.jsonl` 均未被改动。**

### 3.1 一处需要说清楚的「同一段文字出现两次」

`demo/fixture/reference_views.py` 里也有一份相同的负向提示词，以及一段相似的「保持商品外观」英文描述。

这**不是**重复权威：那份文本用于**生成参考包里的商品照片**（Phase 0 的夹具工序），而 `demo/core/prompt_profile.aster-01.json` 是**列表图生成**的短语料。两个阶段、两个用途。它们目前恰好文字相同，是因为同一组「不许变成别的东西」的约束对两步都有用；将来任一步需要调整，都不应被另一处牵制。

真正的单一权威只针对后者：`PRODUCT LOCK` 正文、负向提示词在 demo/ 的**生成路径**里只出现于 profile，`rg` 的结果可以复核。
## 4. 黄金链结果（离线 · 零付费调用）

| 环节 | 结果 | 关键证据 |
|---|---|---|
| PC-01 素材接入 | accepted | 3 个视图逐文件哈希与 manifest 一致 |
| PC-02 ProductFacts | accepted | 8 条事实、7 条需人工侧确认、4 个字段保持 Unknown |
| PC-03 图片计划 | accepted | 4 张图，坑位均来自 `config/slots.yaml`；`plan_version` 两次提案一致 |
| PC-04 视觉方向 | accepted | 默认方向；可变项是白名单 |
| PC-05 提示词 | accepted | 1985 字符，锁 F1–F8；两次编译哈希一致 |
| PC-06 生成提交 | accepted | `action_id=b0c9c907f875b918`，`input_image_count=1` |
| PC-07 结果核对 | accepted | 候选落盘哈希与回执一致 |

**一处需要精确表述的巧合：** 黄金链算出的 `action_id` 与 D1.4 真实付费的 F-01 **完全相同**。这不是巧合而是必然 —— action id 由「模型 + 参考图哈希 + 提示词哈希 + seed + size」决定，这五项与那次真实调用一致。它证明的是**请求身份一致**，不是「候选图片一致」：候选字节来自离线替身传输（`9e184c5c…`），与真实 F-01 的 `95db1ad0…` 无关。

## 5. 十六条反例（每条都注入一种真实缺陷）

| 代号 | 注入的缺陷 | 期望结果 | 实际 |
|---|---|---|---|
| R1 | 参考包缺一个视图文件 | business_reject | 一致 |
| R2 | 素材哈希漂移（PNG 尾部多一字节） | business_reject | 一致 |
| R3 | 用 machine 模态断言未确认字段（容量） | business_reject | 一致 |
| R4 | 既无机器判据也无人确认的断言 | business_reject | 一致 |
| R5 | 事实卡丢掉全部 Unknown 登记 | business_reject | 一致 |
| R6 | 计划里出现无事实来源的卖点 | business_reject | 一致 |
| R7 | 计划未经用户确认就要往下走 | business_reject | 一致 |
| R8 | 风格变量试图改杯体表面（事实锁） | business_reject | 一致 |
| R9 | 结构化编辑（只追加允许方向） | accepted | 一致 |
| R10 | 原始文本编辑删掉 F8 锁定段 | business_reject | 一致 |
| R11 | 同一请求重复提交 | business_reject | 一致（且只提交过 1 次） |
| R12 | 轮询超时 | unknown（且不重发） | 一致 |
| R13 | 请求体里没有参考图 | business_reject | 一致 |
| R14 | 超出硬预算 | business_reject | 一致（且未发出请求） |
| R15 | 用原 task 核对候选 | accepted | 一致 |
| R16 | 实现试图产出合同没声明的状态 | 抛出 ContractViolation | 一致 |

R1–R5、R10 还额外自证「沙箱/文本确实被改坏了」—— 没有这一层，一个失效的探针会伪装成「实现守住了」。

## 6. 变异测试：反例到底有没有牙

绿灯只能说明用例与当前实现一致。所以把实现逐条削弱，要求对应反例**必须变红**：

| 变异 | 削弱的实现 | 应当变红的反例 | 结果 |
|---|---|---|---|
| M1 | 停掉 PC-02 的事实规则 | R3、R4、R5 | 全部变红 |
| M2 | 停掉 PC-03 的卖点规则 | R6 | 变红 |
| M3 | 停掉「编辑不许静默删锁」 | R10 | 变红 |
| M4 | 停掉参考图守卫 | R13 | 变红 |
| M5 | 停掉「同一 action 已有产出就不重发」 | R11 | 变红 |

命令：`python demo/core/run_front_contracts.py --mutation-test`（5/5）。

## 7. 本次自己踩的两个坑（如实记录）

1. **R13 一开始是自造记录。** 第一版为了让用例能表达「守卫失效」，我在断言失败时手工构造了一个 `technical_fail` 的 StepResult。那样等于用一个自造状态去证明另一个状态，后来改成：正常体必须通过，去掉参考图后必须抛 `ProviderGuardError`，结论由实际行为决定。
2. **变异测试自己也失效过一次。** `MUTATIONS` 的元组形状与我解包的方式不一致，`_owner` 从 `FC` 出发去找属性 `FC`，M1 直接炸在 `AttributeError`。修法是把「被替换对象的路径」写成字符串 `"FC.P.guard_raw_edit"` 并从调用方命名空间解析。这与 D1.P1 里「探针没改到东西就判自检失效」是同一类问题。

## 8. 验证结果

| 检查 | 命令 | 结果 |
|---|---|---|
| 前半链契约测试 | `python demo/core/run_front_contracts.py` | 17/17 |
| 变异测试 | 同上 `--mutation-test` | 5/5 |
| 合同守卫 | `python demo/contract/contract_tools.py --project . --check` | rc=0 |
| 合同自检 | 同上 `--self-test` | 18/18 |
| 项目状态守卫 | `python tools/check_project_state.py` | rc=0 |
| 状态反向探针 | `python evals/probes/project_state.py` | 17/17 |
| 文档守卫 | `python tools/check_docs.py` | rc=0 |
| 参考包 | `python demo/fixture/pack_tools.py verify --project .` | READY |
| provider 自检 | `python demo/provider/dashscope_i2i.py --self-test` | 27/27 |
| 付费调用 | —— | **0 次** |
| v2 基线身份 | `python tools/snapshot_v2_baseline.py --check` | rc=1（预期；D1.C2 未解） |

## 9. 这些证据不能证明什么

- **不能证明任何候选图片通过 F1–F8。** PC-06/PC-07 用的是离线替身传输；它证明状态机、守卫与幂等成立，不证明模型产出的图合格。那属于 D1.R1–D1.R3。
- **不能证明跨商品通用。** 全部用例只跑内置虚构商品 Aster 01；换商品目前仍需另一份事实卡与提示词 profile。
- **不能替代 G1。** 本任务没有产生新的真实生成证据，也没有改变「四张真实候选 + 一次受控复验」这条预算界线。
- **不能解除 D1.C2。** v2 基线仍是红的。

## 10. 下一步

D1.P3：用同一批冻结候选验证 PC-08–PC-13（技术检查、商品事实验证、审美审核、返工路由、选择与精确合成、最终复检与导出），仍然离线、不产生新的付费调用。