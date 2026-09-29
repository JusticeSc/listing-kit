# 2026-09-28 控制面校准与实施计划复核（Product V1 v2.3）

> NOT-AUTHORITY · point-in-time evidence  
> Goal 生命周期以系统 Goal 为准；产品目标、任务定义和依赖以 `docs/product-demo-goal-and-implementation-plan.md` 为准；执行进度以 `_working/amz-listing-kit-product-demo/state.md` 为准；文档路由以 `docs/INDEX.md` 为准。

## 1. 校准结论

- 系统 Goal `01a0ca17-2179-7eb0-969a-af9c79c4d8ca` 本轮重新读取为 `active`；本次不更改 Goal 状态，不创建并行 Goal。计划 §2 保留当前 Goal objective；建议的澄清版 Goal 文本只作为待用户确认的提案。
- 产品计划当前版本为 v2.3。它把产品定义为以单商品文件夹工作空间为边界的通用套图工作台，而不是固定杯子/品类模板演示；商品理解、`1..N` Shot 方案与逐图 Prompt 由当前输入生成，未覆盖的视觉任务使用通用 `custom` Shot 表达。
- 本轮进一步将返工明确拆成“预览返工方案”和“用户确认后提交”两个动作；确认绑定当前 proposal/Shot/Prompt 版本，预览阶段不调用图片 Provider。上传到某商品工作空间默认表示素材属于该商品，仅资料冲突时才要求用户裁定。Amazon US Profile 的硬规则须记录官方来源、规则版本与核对时间。
- 计划与文档索引已同步为 v2.3；执行状态仍是 Phase 0 active、D0.1 pending、唯一下一步 D0.1。
- D0.1 当前未通过：Provider 配置没有 Schema 要求的 `max_attempts`，独立合同验收器 `tools/verify_product_v1_contracts.py` 尚不存在。不得放宽 Schema，也不得把 D0.1/G0 标为完成。
- 本轮没有改动产品代码，没有发起真实图片模型请求，也没有做模型能力 benchmark。后续真实参考图请求是产品集成验收，不是跨模型能力实验；纯文生图或本地贴图不能替代 Goal 要求的真实参考图调用。

## 2. 控制面权威与单一职责

| 事实类别 | 唯一权威 | 校准结果 |
|---|---|---|
| Goal ID、目标文本和生命周期 | 系统 Goal | 重新读取；ID 与项目 state 绑定一致，状态 `active`；本轮未修改 |
| 产品范围、完成条件、架构、阶段、任务与依赖 | `docs/product-demo-goal-and-implementation-plan.md` | 当前 v2.3；所有计划修改只落在此文件 |
| 当前阶段、任务进度、证据指针、唯一下一动作 | `_working/amz-listing-kit-product-demo/state.md` | Phase 0 active；D0.1 pending；`next_action_task: D0.1` |
| 哪份文件有效、各文件管什么 | `docs/INDEX.md` | current 产品计划和执行状态均登记为 v2.3；v4/v1.14 等旧方案仍为历史证据 |
| 当前代码实际实现了什么 | 正式入口代码、README 与新鲜运行证据 | Mock/旧夹具不提升为真实模型完成证据；本轮未改代码 |
| 某次校准、运行或测试发生了什么 | `evals/product-demo/` 中的时点记录 | 本文件记录本次事实；不取代以上任何当前权威 |

旧的 `control-plane-calibration-2026-09-28-followup.md` 记录的是 v2.2 时点状态，保留为历史证据；本文件将作为 state 指向的最新复核记录。`evals/` 是证据目录，不进入 `docs/INDEX.md` 的受管登记范围。

## 3. v2.3 的产品和交互合同

1. **工作对象是商品工作空间。** 使用者新建/打开一个文件夹，添加商品名称和 1–3 张参考图；介绍、真实卖点和本次重点均可选。V1 只支持 Amazon US，界面展示固定目标，不放只有一个选项的平台下拉。
2. **预先设计稳定语法，不穷举商品模板。** 系统保存来源清楚的商品事实、通用 Archetype、平台 Profile、Prompt Grammar、状态和版本规则；具体品类、商品事实、Shot 数量/组合、风格方向与逐图完整 Prompt 由当前输入动态形成。没有合适注册 Archetype 时使用 `custom`，不以新增食品/家具/水杯类别作为使用前提。
3. **默认减负但不剥夺设计者/使用者理解权。** 系统给可直接采用的 ProductBrief、Plan 和 Prompt；使用者可查看并修改完整 Prompt。用户声明、视觉可见信息、模型推断和用户修正分开保存；未确认的功能、材质、尺寸、认证不得被升级成肯定营销事实。
4. **图片调用无状态，产品状态有版本和恢复能力。** 每个 Shot 独立记录 Prompt、Attempt、候选和选择；整套可以一键启动，单张可以返工。默认图片模型为 Qwen Image 3，但 Provider 通过配置/接口隔离。`UNKNOWN` 必须按原 provider task id 核对后再决定，不因超时盲目重复提交。
5. **付费返工需要显式承诺。** `rework-preview` 只生成草案并展示保持/改变项，不调用 ImageProvider；用户确认后 `rework` 请求绑定 proposal、Shot/Prompt 基础版本、`action_id`/`idempotency_key`，只提交目标 Shot。旧候选与无关 Shot 历史不覆盖。
6. **平台规则必须可追溯。** Amazon US Profile 中每条硬规则记录官方来源 URI、规则版本与核对日期，并将实际采用版本写进报告/导出 manifest；来源无法确认的规则不得宣称已验证合规。审美判断仍由用户选择，不伪装成确定性检查。

参考的三个 Skill 分别提供任务链、Prompt/共享风格编译、Provider 执行与续跑的机制；它们的固定品类、张数、平台样例、批次上限、并发、积分与重试参数均不是本产品合同。产品不做模型能力 benchmark，但必须完成 Goal 指定的真实参考图生成链路。

## 4. D0.1 的当前缺口与唯一下一步

| 项 | 当前证据 | 当前状态 | D0.1 应完成的动作 |
|---|---|---|---|
| Schema meta 检查 | 使用 `jsonschema==4.26.0` 初始化当前 validator 成功 | 通过 | 保持 |
| Provider 配置 bundle | `validate_config_bundle(...)` 返回 `provider_registry.record` 不匹配；`contracts/product-v1.schema.json` 244–245 行将 `max_attempts` 列为必填，`config/product-v1/providers.json` 当前 provider 未设置该字段 | 失败 | 按计划明确 V1 `max_attempts: 1`；不得放宽 Schema。人工重试创建新 action，UNKNOWN 只核对原 task id |
| 专项领域验收器 | `tools/verify_product_v1_contracts.py` 当前不存在 | 缺失 | 新增离线正反例验证 Schema、hash、版本、引用、选择/导出约束、`custom` Shot 与可定位错误 |
| `custom` 回退 | v2.3 计划要求加入；现有 validator/config 尚未完成相应正反例 | 设计已定、实现未做 | Schema、配置、校验器同步支持合法 `custom`；不新增品类硬编码 |
| 项目控制守卫 | 修改 state 后重跑 J0–J10，退出码 0 | 通过 | 可继续执行 D0.1；不代表 D0.1 已完成 |
| 文档守卫 | 修改 INDEX/state 后重跑 `check_docs.py --no-run`，登记与仓库均为 31 份、退出码 0 | 通过（静态/索引范围） | 该模式不运行文档中登记的命令 |
| 产品级验收 | 真实 Qwen 参考图调用、完整候选选择、首次使用者走查 | 本轮未执行 | 保留为 Goal 后续必要证据，不由文档检查替代 |

D0.1 的关闭条件是：正式配置 bundle 通过；离线 verifier 正反例通过且错误可定位；`custom` 通用任务合法、错误/未知模式被拒绝；源文件/版本/哈希与跨记录关系均有证据。完成前唯一下一任务仍是 D0.1。

## 5. 版本与回退

本轮修改前将 `docs/INDEX.md`、产品计划、`state.md` 快照到：

`_stage-amz-control/control-plane-pre-sync-v2.3-20260928-1346/`

快照 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `docs__INDEX.md` | `7B17A4DCA66371C8769439D628AA3AB7F895B0E008CDC6B334F0F03409DF2584` |
| `docs__product-demo-goal-and-implementation-plan.md` | `A26908B02D7029E7C646DAFA5CA7E2E9EF772BC5F3F9A41DCBA5C6169568B003` |
| `state__amz-listing-kit-product-demo.md` | `EE6D982B77B5C4FF9DA8D2260FCA67A421599B103342EDF45720919F84802D09` |

产品目录没有 `.git`，因此本次以逐文件快照为回退点；不会覆盖此前 `_stage-amz-control/` 下的快照。

特别说明：旧目录 `_stage-amz-control/control-plane-v2.3-20260928-133554/` 的计划文件 SHA-256 为 `13213AA37D469433A88718BB44BFD3185275DBF678CD13C8BB7FB2B84E8958AE`，对应 v2.2 基线而非 v2.3，保留作历史版本；本次新增的 `control-plane-pre-sync-v2.3-20260928-1346/` 才是本轮同步前完整的 v2.3 回退点。

## 6. 最终复验

同步后复验结果：

| 检查 | 结果 | 证据边界 |
|---|---|---|
| 系统 Goal 读取 | `01a0ca17-2179-7eb0-969a-af9c79c4d8ca` 为 `active`；state 的 Goal ID/status/观察时间一致 | 证明当前 Goal 绑定；不证明产品功能完成 |
| `tools/check_project_state.py` | J0–J10 全过，退出码 0 | 证明执行状态字段、任务引用、Gate 顺序、唯一下一步与 Goal 读数一致 |
| `tools/check_docs.py --no-run` | 31/31 登记一致，current 目标计划和 state 唯一；退出码 0 | 明确跳过文档内命令运行；不证明那些命令可运行 |
| 计划版本路由 | 计划头、INDEX 目标计划/state 行均为 v2.3；state `plan_ref` 指向唯一当前计划 | 版本一致已人工检查；当前文档守卫不会校验显示版本号相等 |
| Product V1 bundle | Schema meta 初始化通过，但真实配置 bundle 失败；schema provider 必填字段含 `max_attempts`，当前 provider 未提供 | D0.1 仍失败，未写业务代码修复 |
| D0.1 专项 verifier | `tools/verify_product_v1_contracts.py` 不存在 | D0.1 仍缺验收器与正反例 |
| 真实生成/用户验收 | 本轮未发起真实模型请求、未做首次使用者走查 | 仍是后续 Goal 必须取得的证据 |

同步后文件 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `docs/product-demo-goal-and-implementation-plan.md` | `F6580C02C418BD50F0342493EF321BA24FA7F05CA0F3272D6734BB00CA82AFC7` |
| `docs/INDEX.md` | `6CB25D7C9B4CB9447D63D62BA2A793EE49F7A46C686E96EA4EE79F96F4038E7E` |
| `_working/amz-listing-kit-product-demo/state.md` | `A4D2E9CD31BBA5566EDF4F1440F8EF96478B1026831BA52B86B22447CA3526A6` |

state 最终读数：Goal `active`；Phase 0 `active`；D0.1 `pending`；`latest_audit` 指向本文件；`next_action_task: D0.1`。`--no-run` 只证明文档登记与静态结构，不证明其中的命令可运行；任何绿色守卫都不证明真实图片生成或首次使用者结果。
