# 控制面单一权威校准证据

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY  
> 记录时间：2026-09-26T01:18:25+08:00。本文只记录本次校准发生了什么；当前状态、下一动作和未来计划分别以 current state 与产品计划为准。

## 1. 审计结论

校准前，当前产品计划、执行状态、README、旧草案和时点审计都在不同程度上重复发布任务图、进度或“下一步”，机器守卫能检查格式，却不能阻止同一事实出现多个维护点。旧完整回归还会让 M6 直接改写冻结 run，而旧基线只校验已登记文件，无法发现新增文件。

校准后，控制面按事实类别拆成唯一维护点：

| 事实 | 唯一权威 | 其他文件的合法行为 |
|---|---|---|
| Goal 生命周期 | 系统 Goal 控件 | state 只记录最后一次读数 |
| 产品目标、完成合同、架构、阶段、Gate、任务与依赖 | `docs/product-demo-goal-and-implementation-plan.md` | 只按 ID 引用 |
| 当前进度、证据、阻塞、唯一下一动作 | `_working/amz-listing-kit-product-demo/state.md` | 审计报告只留时点快照 |
| 文档身份与阅读路由 | `docs/INDEX.md` | 每份文档只声明自身身份 |
| 已实现能力 | README 指向的代码、配置和验证入口 | 计划不得把目标能力写成当前实现 |
| 某次实验或检查结果 | `evals/` 原始产物和时点报告 | 不发布未来计划或当前状态 |

## 2. 已落地的结构调整

- current state 改为 `amz-project-state/v2`：不再复制 phase/task/gate/depends_on 定义，只保存计划 ID 对应的进度和证据。
- `tools/check_project_state.py` 从产品计划读取阶段、任务和依赖；17 向对照探针证明未知 ID、跨阶段、缺证据、复制 scope、Goal 状态矛盾等情况会变红。
- `docs/INDEX.md` 成为唯一上下文入口，并固定恢复顺序：INDEX → current state → 下一任务卡 → 证据 → 代码。
- `tools/check_docs.py` 要求每份受管 Markdown 在顶部声明与登记一致的 `CONTROL-STATUS`；旧计划、旧 state、v3/v4 草案和横切面文档已明确降级为 `superseded` 或 `to-delete`。
- 产品计划不再保存运行/暂停、阶段进度和“已通过”动态结论；README 只描述当前实现；旧状态审计删除未来计划和下一动作。

改动前的关键控制文件备份位于项目外：
`E:/gitee_repository/vison/_stage-amz-control/single-authority-backup-20260926-0100`。

## 3. D1.C1：冻结证据不再被回归改写

### 3.1 机制修正

- `tools/regress_all.py` 默认把冻结 run 复制到 `evals/.tmp/regress-m6-*`，M6 只在副本里追加重做版本。
- 回归开始前和结束后对冻结 run 做“文件集合 + 大小 + SHA-256”快照；任一新增、删除或改写都会使整次回归失败。
- `tools/snapshot_v2_baseline.py --check` 新增产物精确集合校验，除了已登记文件的哈希变化，也会报告未登记文件和重复登记。
- `tools/snapshot_v2_baseline.py --self-test` 构造一个额外 `extra.txt`，只有集合守卫明确变红才算通过。

### 3.2 新鲜证据

| 检查 | 结果 |
|---|---|
| baseline 额外文件反向探针 | 通过；`extra.txt` 被明确识别为未登记文件 |
| 项目状态守卫 | 通过 |
| 项目状态 17 向正反对照 | 17/17 与预期一致，原状态逐字节恢复 |
| 文档登记与身份检查 | 30/30 登记一致 |
| 完整回归 | 21 通过 · 0 环境拦下 · 0 未通过 |
| 冻结 run 前后核对 | `B0FULLSET01_20260923-125218-258886` 的文件集合与逐文件哈希一致 |
| v2 baseline 复核 | 通过；171 个产物文件，代码身份 `59c9b0a8b7f809123d438a66d9a28a6ecffb6ccc327015c3a99f7b4f77b0fb53` |

完整回归原始报告：`evals/last_regress.txt`，SHA-256：
`4e2a0c0d1a3d42b29eb38c9c013742794232e0e7093b84aa7173ad7be9281f00`。

## 4. 边界

- 本次没有调用付费生图模型，也没有改变 Phase 1 已生成的四张候选。
- 系统 Goal 在本次读取时为 `paused`；本文不把它改写成 active，也不据此宣布产品开发已恢复。
- 本次关闭的是控制面与冻结证据缺口，不证明完整演示产品已经可用。产品能力的下一任务由 current state 指向计划中的 D1.6。
