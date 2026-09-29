# Goal 恢复与 Phase -1 关闭证据（2026-09-24）

> 本文件只证明「系统 Goal 已恢复为可执行状态、Phase -1 具备关闭条件」。
> 它不证明任何新产品能力已经实现；截至本文件生成时，Phase 0 还没有产出参考资产。

## 1. 读取到的系统 Goal

| 字段 | 值 |
|---|---|
| goal id | `01a0ca17-2179-7eb0-969a-af9c79c4d8ca` |
| status | `active` |
| tokensUsed | 2324783 |
| timeUsedSeconds | 15714 |
| updatedAt（系统字段） | 1790225845 |
| 读取时间 | 2026-09-24T13:08:14+08:00 |

读取方式：Goal 工具直读，不是从项目文件推断。读取结果中的 goal id 与本项目上一轮
绑定的 id 相同，说明恢复的是同一个 Goal，而不是新建了另一个目标。

## 2. 文本一致性核对（逐字）

核对对象：系统 Goal 的 objective 与 `docs/product-demo-goal-and-implementation-plan.md` §2 的引用文本。

- 规范化：去掉 `> ` 引用前缀，丢弃空行，段间以单个换行连接；
- 结果：**逐字相等**；
- 两侧 sha256（同为 `0bcf762f3e9dd7fb40d27bd87c3b8f781609bf4932b1a7c92910132c7f6b50d2`）。

如果两侧不一致，本轮必须停下——「系统在追一件事、计划在写另一件事」是控制面最危险的漂移。

## 3. 恢复前后的状态

| 时点 | status | 依据 |
|---|---|---|
| 本文件生成之前 | `paused` | 上一轮执行记录声明 Goal 已绑定但不可执行，唯一下一动作是项目发起人恢复 |
| 本轮读取 | `active` | 本文件 §1 的直读结果 |

恢复是项目发起人在 Goal 控件里的控制动作。本轮没有执行 Phase 0 写入，也没有调用任何付费模型。

## 4. Phase -1 关闭内容

| 判据 | 证据 |
|---|---|
| Goal 更新为 §2 文本并恢复可执行 | §1 + §2 |
| 状态记录绑定真实 Goal id | `_working/amz-listing-kit-product-demo/state.md` 的 `goal_id` |
| `docs/INDEX.md` 只有一个产品目标与执行状态权威 | `tools/check_docs.py` 全过（管辖事实唯一 + 双向比对） |
| 项目状态守卫与反向探针 | `tools/check_project_state.py` 全过 |
| 基线已重新快照 | `evals/v2_baseline_manifest.json`、`evals/v2_baseline_snapshot.txt`（`--check` 通过） |
| 完整回归 | `evals/last_regress.txt` |

## 5. 本文件不能证明什么

它不证明参考包可用、不证明 `qwen-image-3.0` 的图生图能力、不证明任何一张候选可用，
也不证明陌生使用者能独立完成任务。这些都要靠 Phase 0 之后的真实证据。
