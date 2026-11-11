<!-- 拆分件 01/02 · 父文档 evals/product-demo/control-plane-calibration-v2.3-2026-09-28.md -->
# 2026-09-28 控制面校准与实施计划复核（Product V1 v2.3）
[返回 control-plane-calibration-v2.3-2026-09-28.md](control-plane-calibration-v2.3-2026-09-28.md)

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

