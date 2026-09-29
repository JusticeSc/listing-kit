# 2026-09-28 控制面校准与实施计划复核

> NOT-AUTHORITY · point-in-time evidence  
> 本报告仅记录本次核对和文件同步。Goal 生命周期只读系统 Goal；产品合同与任务图只读 `docs/product-demo-goal-and-implementation-plan.md`；当前执行状态只读 `_working/amz-listing-kit-product-demo/state.md`；文档身份与路由只读 `docs/INDEX.md`。

## 1. 结论

- 系统 Goal `01a0ca17-2179-7eb0-969a-af9c79c4d8ca` 当前为 `active`。其目标与产品计划 §2 一致；本次不新建 Goal、不改变生命周期。
- 当前产品方向保持为：通用工作空间与动态套图任务模型，按商品、卖点、平台和用户意图生成 `1..N` 张 Shot；默认提供 ProductBrief、套图方案和完整 Prompt，用户可查看、修改、逐图选择与返工；图片调用经 Provider 管理，模型调用本身不成为业务状态权威。
- 控制面唯一权威保持为系统 Goal、产品计划、`state.md`、`README.md`/代码、`docs/INDEX.md`、`evals/` 六类各司其职；本次修复计划与索引的版本漂移，并把本报告加入 state 的证据指针。
- 执行仍停在 Phase 0，D0.1 是唯一下一任务。当前 D0.1 有可复现的配置合同失败，不能标成完成，也不能进入 D0.2。
- 本次没有发起图片模型请求或模型能力 benchmark。后续真实 Qwen 请求仍是产品集成与端到端验收，不是跨模型能力实验。

## 2. 控制面校准

| 事实 | 唯一权威 | 本次处理 |
|---|---|---|
| Goal 生命周期与 ID | 系统 Goal `01a0ca17-2179-7eb0-969a-af9c79c4d8ca` | 重新读取为 `active`，保持不变 |
| 产品目标、完成条件、架构、阶段与任务依赖 | `docs/product-demo-goal-and-implementation-plan.md` | v2.2 保持为唯一产品合同；D-1.1 的产物版本由 v2.1 更正为 v2.2 |
| 当前阶段、证据、阻塞与唯一下一动作 | `_working/amz-listing-kit-product-demo/state.md` | 继续 Phase 0 / D0.1 pending / `next_action_task: D0.1`；更新观测时间与审计指针 |
| 已实现能力 | `README.md`、正式入口代码与新鲜验证结果 | 不把旧 Mock、夹具或历史候选升级为 Product V1 能力 |
| 文档有效性与路由 | `docs/INDEX.md` | 当前产品计划和 state 均登记为 v2.2；旧计划仍为 `superseded` |
| 某次检查发生了什么 | 本目录下的时点报告 | 仅作证据，不另立当前状态或实施规范 |

`tools/check_docs.py` 的受管范围是根目录、`docs/` 与 `_working/`，`evals/` 是证据产物而不进入 `docs/INDEX.md` 登记表。因此本报告由 state 链接，不登记成第二份“当前计划”。

## 3. 三份参考 Skill 的实际机制与迁移边界

本节依据现存 Skill 说明与配套脚本的只读复核；源文件没有被复制到产品仓库，也没有重跑其模型请求。

| 参考 | 实际任务链 | 本产品采用 | 不照搬 |
|---|---|---|---|
| `ecommerce-image-suite`（`E:\gitee_repository\vison\ecommerce-image-suite-main\SKILL.md`；配套 `scripts/analyze.py`、`scripts/generate.py`） | 商品参考图与可选卖点 → 视觉分析形成结构化商品资料 → 人修正/确认 → 按平台和图型形成逐图 Prompt 并调用 → 图片、结果或错误记录 | 原始输入有来源；ProductBrief 可确认；每张图单独 Prompt、Attempt 和结果 | 服装偏向输入、固定图型/张数、仅凭 Key 格式判断 Provider 可用 |
| `ecom-details-image`（`E:\gitee_repository\vison\ecom-details-image-main\.claude\skills\ecom-details-image\SKILL.md`；配套 `scripts/generate_image.py`） | 视觉用途、主体、风格、平台与可选参考图 → 判断 Prompt-only/Generate、模板辅助、只追问影响结果的缺项、建立多图 Campaign Style Lock、编译逐图 Prompt → 输出 Prompt 或图片 | Archetype 是任务语法；共享视觉方向与逐图目标分开；最终 Prompt 可见、可编辑、可追溯 | 25 个模板不是品类全集；Amazon 示例张数不是固定合同；GPT-Image-2 专属规则不硬套给 Qwen；单次脚本不等于持久工作空间 |
| `ecommerce-skills/skills/batch-image`（`E:\gitee_repository\vison\ecommerce-skills-main\skills\batch-image\skill.md`；配套 `batch.mjs`、Provider 与检查脚本） | SKU CSV 与共享 Prompt 规范 → Provider/脚本做变量渲染、执行控制、续跑 → 图片、批次 manifest 与文件规则报告 | Provider 接口、提示词公共规则与商品变量分离、可恢复状态、manifest、确定性文件检查 | 多 SKU/CSV、并发数、预算、抽样比例与自动重试是批任务策略，不是当前单商品套图合同 |

因此本产品继承的是“可复用的任务语法与执行机制”，不是预制出所有品类答案。工作空间把无状态的语义/图片 Provider 调用包装成有版本、有引用、有 Attempt 与 Candidate、有恢复和用户选择权的过程。不同商品的 Brief、Shot 组合与商品 Prompt 块由输入动态编译；Prompt、商品来源事实、平台硬约束、模型输出与人工选择仍分别保留，不合并成一段不可解释的“魔法结果”。

## 4. 实施计划与当前证据

产品计划 v2.2 已定义 Phase `-1, 0, 1, 2, 3, 4` 及 Gate `G-1, G0–G4`。其纵向结果顺序为：控制面与 Goal 对齐 → 文件夹 Workspace/空白入口 → 商品理解、动态 Plan 与 Prompt 编译 → 真实整套生成及失败恢复 → 单图返工、选择、导出 → 安装、首次使用者走查与完成审计。任务卡给出输入、依赖、产物、验收和失败/回退；工作顺序为单任务 WIP。

D0.1 的详细合同在产品计划 §10：冻结 Workspace、输入、Brief、Plan/Shot、Prompt、Attempt、Candidate、Selection、Export 记录与 Archetype/Platform/Provider 配置；建立离线正反例验收器；校验 hash、版本、跨记录引用、选择与导出关系；在通过前不写正式 Workspace、不开始 D0.2。

| 检查 | 本次结果 | 能证明什么 / 不能证明什么 |
|---|---|---|
| 系统 Goal 读取 | `active`，ID 与 state 绑定一致；objective 与计划 §2 一致 | 证明控制目标未漂移，不证明产品功能完成 |
| `tools/check_project_state.py` | 退出码 0，J0–J10 全过 | 证明阶段、任务依赖、Goal 读数与唯一下一步一致 |
| `tools/check_docs.py --no-run` | 退出码 0，已登记/实际均为 31 份 | 证明文档登记、身份与单一权威一致；`--no-run` 明确未验证登记文档里的命令 |
| Product V1 schema / 配置 bundle | Schema validator 初始化成功；当前 bundle 返回 provider registry 校验错误 | 直接缺口是 provider 配置未提供 schema 强制要求的 `max_attempts`（见 `contracts/product-v1.schema.json` 244–245 行）；当前 Provider bundle 仍未通过 |
| D0.1 专项验收器 | `tools/verify_product_v1_contracts.py` 不存在 | 计划要求的领域记录正例、结构/关系反例和可定位错误尚未通过完整专项验证 |
| Git 回滚能力 | 产品目录 `git rev-parse --show-toplevel` 失败，产品目录无 `.git` | 本次依赖文件快照回滚，不声称有可用 Git diff/回滚 |
| 真实生成与首次使用者走查 | 本次未执行 | 仍是后续 Goal 的必要验收，不由控制面校准替代 |

本次 D0.1 配置问题不是需要用户选择的外部阻塞，而是待执行任务里的已知修复项：按计划将 V1 自动提交上限设为 `1`，由人工重试产生新 action；`UNKNOWN` 先按同一 Provider task id 核对，不自动重复提交。之后补齐离线合同 verifier 和正反例，只有全绿才关闭 D0.1。

## 5. 文件快照与回退点

在修复 INDEX 与计划的版本登记前，已将三份当前文件原样复制到：

`_stage-amz-control/control-plane-sync-20260928-131557/`

| 快照文件 | SHA-256 |
|---|---|
| `docs/INDEX.md` | `E224FBE9E2B8A8287C785364D3E8C27E6B3CA51D0224C00131A49C4503A1F1FF` |
| `docs/product-demo-goal-and-implementation-plan.md` | `AE2FC9B010150C85566CF97B5C3FFF9730D0CC442CD5E531813425A2BFB8FF16` |
| `_working/amz-listing-kit-product-demo/state.md` | `DB25C7D16AE351DAB103F7F304CF3678C3472D9CC4D515B73B289A9E4FD59041` |

复制后逐文件 SHA-256 与源文件一致。旧快照 `_stage-amz-control/control-plane-sync-20260928-124552/` 保留，不覆盖。

## 6. 最终同步后的验证

最终复验发生在 state 更新并指向本报告之后：

| 复验 | 结果 |
|---|---|
| `uv run --no-project --offline --with PyYAML==6.0.3 --python 3.13 python -B tools/check_project_state.py` | 退出码 0；J0–J10 全过，Phase、任务依赖、Goal 观测与唯一下一步一致 |
| `uv run --no-project --offline --with-requirements requirements.txt --python 3.13 python -B tools/check_docs.py --no-run` | 退出码 0；受管 Markdown 31/31 双向登记、current 文档身份与唯一权威一致；该命令明确跳过文档内命令执行 |
| state 关键字段复核 | `system_goal_observed_status: active`；Phase 0 active；D0.1 pending；`latest_audit` 指向本报告；`next_action_task: D0.1` |
| Product V1 bundle | Schema 初始化成功，但 bundle 仍因 provider 缺少必填 `max_attempts` 而被拒；未误标 D0.1 完成 |

最终文件 SHA-256：

| 文件 | SHA-256 |
|---|---|
| `docs/product-demo-goal-and-implementation-plan.md` | `13213AA37D469433A88718BB44BFD3185275DBF678CD13C8BB7FB2B84E8958AE` |
| `docs/INDEX.md` | `7B17A4DCA66371C8769439D628AA3AB7F895B0E008CDC6B334F0F03409DF2584` |
| `_working/amz-listing-kit-product-demo/state.md` | `EE6D982B77B5C4FF9DA8D2260FCA67A421599B103342EDF45720919F84802D09` |

这些检查证明的是控制面结构和记录同步，不是产品链路、真实图片质量或首次使用者结果。任何产品完成声明仍须按 Goal 中的完整验收条件逐项取得证据。
