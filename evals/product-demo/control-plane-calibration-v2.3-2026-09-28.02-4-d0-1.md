<!-- 拆分件 02/02 · 父文档 evals/product-demo/control-plane-calibration-v2.3-2026-09-28.md -->
# 4. D0.1 的当前缺口与唯一下一步
[返回 control-plane-calibration-v2.3-2026-09-28.md](control-plane-calibration-v2.3-2026-09-28.md)

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
