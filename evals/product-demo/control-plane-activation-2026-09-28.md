# Product V1 Goal 激活与开工基线

> NOT-AUTHORITY：本文件是 2026-09-28 的时点证据。产品合同与任务图只读 `docs/product-demo-goal-and-implementation-plan.md`，执行状态只读 `_working/amz-listing-kit-product-demo/state.md`。

## 当前系统 Goal 读数

- Goal ID：`01a0ca17-2179-7eb0-969a-af9c79c4d8ca`。
- 系统 Goal 状态：`active`；在本轮重新读取。
- 当前 objective 与产品计划 §2 的规范文本一致：Windows 本地文件夹工作空间、输入驱动的 ProductBrief 与动态 `1..N` 计划、完整可编辑 Prompt、真实 Qwen 参考图整套生成、历史候选、单图返工、人工选择和 manifest 导出；范围边界与缺少真实凭据/参考图请求/人工选择时不得宣称完成的约束均一致。
- Goal ID 未改变，current state 继续绑定同一 ID。D-1.2 的 objective 绑定条件已满足。

## 开工基线

| 检查 | 新鲜结果 | 证据边界 |
|---|---|---|
| `tools/check_project_state.py` | 退出码 0，J0–J10 全过 | 校验仓库内状态与计划引用，不独自读取系统 Goal；因此外部 Goal 更新后仍须重新读取并同步 state |
| `tools/check_docs.py --no-run` | 退出码 0，31 份受管文档登记一致 | 此模式不执行文档中的命令 |
| `tools/check_docs.py --explain` | 退出码 0，真跑 11 条去重命令，跳过 34 条并解释原因 | README 的真实生成命令被守卫补成 `--dry-run`，没有付费模型调用；只证明旧文档命令与旧链路可运行 |
| `app/server.py --check --offline-fixture demo/fixture/aster-01` | 退出码 0 | 通过的是旧 Mock 工作台轨迹：固定 4 张/4 个候选和 Mock 部分失败、Unknown 合同；不是 Product V1 能力证据 |
| 当前正式入口与实现 | `app/server.py` 提供本地 HTTP 服务，页面由 `app/static/` 提供；业务流仍是旧 Mock；`run.py` 是独立旧 CLI 入口 | 正式空白 Workspace、动态编译与正式服务尚未施工；原样保留为实施基线，不误报为产品完成 |

## 判定与下一步

- Phase `-1`、D-1.1–D-1.3 和 Gate G-1 满足；旧 Aster Goal 阻塞已解除。
- 当前实现仍不满足产品 Goal。Mock、夹具和历史候选只能作为回归证据，不能替代真实模型与首次使用者验收。
- 下一任务唯一为 D0.1：落实 Product V1 的领域 schema 与配置语法，覆盖 Workspace、输入、Brief、Plan/Shot、Prompt、Attempt、Candidate、Selection、Export，以及 Archetype、Amazon US 平台规则与 Provider 配置。
