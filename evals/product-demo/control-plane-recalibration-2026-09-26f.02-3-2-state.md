<!-- 拆分件 02/02 · 父文档 evals/product-demo/control-plane-recalibration-2026-09-26f.md -->
# 3.2 state 的具体改动
[返回 control-plane-recalibration-2026-09-26f.md](control-plane-recalibration-2026-09-26f.md)

### 3.2 state 的具体改动

| 键 | 改前 | 改后 |
|---|---|---|
| `latest_audit` | `…control-plane-recalibration-2026-09-26d.md` | `…control-plane-recalibration-2026-09-26f.md` |
| `phase_progress["1"].status` | `active` | `done`（G1 有当前证据；证据行追加 b/e/f 三份） |
| `phase_progress["2"]` | 无 | `active`（Phase 2 开工） |
| `task_progress.D1.P4` | 未登记 | `done`（两份探针证据） |
| `task_progress.D1.C2` | 未登记 | `blocked`（环境门槛，§7.1 已解耦） |
| `next_action_task` | `D1.P4` | **`D2.R1`** |
| `unknowns` | 10 条 | 14 条（并入 D1.P4 新发现的 4 条） |
| `updated_at` | `2026-09-26T14:05:00+08:00`（未发生） | 实际写入时刻 |

把 `phase_progress["1"]` 记成 `done` 的依据是计划 §5 的口径：阶段推进以 **Gate 的当前证据**
为条件，而不是以"相内每个任务都 done"为条件。G1 本轮重跑仍为 `pass`。

### 3.3 反向对照自己也被修了两处（不是放宽判据）

加了 J10 之后先跑反向对照，19 向里有 4 向与预期不符。逐条查下去，**没有一条是守卫的错**，
两条是探针自己的问题、两条是判据的 tag 根本读不出来：

| 现象 | 原因 | 处置 |
|---|---|---|
| `[FAIL] R / S ... tags=[]` | 探针的 tag 正则写的是 `\[J(\d)\]`，只认一位数，`[J10]` 读不出来 | 正则改 `\[J(\d+)\]`（判据没错，是读判据的人错了） |
| `[FAIL] J ... rc=0` | 探针挑"依赖未完成"的任务时，把阶段门 `G1` 也拿去和**任务 id 集合**比 —— 于是 `G1` 永远"未完成"，挑中的任务在守卫看来依赖已满足，注入成了空操作 | 探针的依赖语义改成与守卫**完全一致**（`G<n>` 看阶段、其余看任务），并加一个自证：挑中的任务若与基线 `next_action` 相同就报错 |
| `[FAIL] O ... tags=['J7','J9']` | 「记录 paused 但有 Phase active」这一向此前靠手写 `phase_progress["1"] = active` 制造；Phase 1 变成 done 之后，这个写法连带让 `next_action=D2.R1` 的阶段门依赖不成立，于是多报一条 J7 | 改用 `_make_active()` 造相位矛盾，保住 next_action 的依赖仍然满足 |

**这次修的是"判据能不能被正确地验"，不是"判据松不松"。** 三处的共同形态是：
**探针与守卫对同一件事的解释不一致时，先红的是探针的可信度** —— 如果当时顺手把 J 的期望值放宽成 rc=0，就会把一个真正会响的判据改成摆设。

## 4. 读数（本轮全部重跑，除注明外退出码 0）

| 守卫 | 结果 |
|---|---|
| `demo/core/packages.py self-test --project .` | 全部成立（含 T7 指针可解析） |
| `demo/core/run_front_contracts.py` | 17/17 |
| `demo/core/run_back_contracts.py` | 22/22 |
| `demo/core/run_back_contracts.py --mutation-test` | 12/12 |
| `demo/verify/g1_audit.py check / self-test --project .` | `pass` / 7/7 |
| `demo/verify/swap_probe.py self-test --project .` | 7/7 |
| `demo/verify/swap_probe.py report --project .` | `default_package_control_ok` |
| `demo/verify/swap_probe.py report --project . --sku bex-02` | `data_missing_no_code_change` |
| `demo/verify/fact_capability.py check / self-test` | 全过 / 10/10 |
| `demo/verify/verifier_registry.py check / self-test` | 全过 / 9/9 |
| `demo/fixture/pack_tools.py verify / self-test --project .` | READY / 5 向一致 |
| `demo/fixture/measure_cylinder.py self-test` | 4/4 |
| `demo/contract/contract_tools.py --check / --self-test` | 通过（识别为 v1.12）/ 18/18 |
| `tools/check_project_state.py --project .` | 全过（J10 已并入） |
| `evals/probes/project_state.py` | **19/19**，且运行后逐字节恢复 current state |
| `tools/check_docs.py` | 全过（登记 30 = 仓库 30） |
| `tools/check_forbidden_rules.py` | 全过 |
| 硬规矩 1 两种既有形态（商品名字面量 / 导入时焊死默认包） | 零命中 |

## 5. 再校准的准入条件（防第八次空转）

前七次里，后四次改的都是**验证侧判据**，没有一次改变产品能力。所以登记一条准入条件：
再校准必须能指出属于以下三种之一，否则不做。

1. **守卫全绿而结论被实测改掉**（第六次：路径漂移把 `detected 6` 读成 `detected 0`）；
2. **同一类事实出现第二个出处**（第五次：单一权威）；
3. **执行记录与磁盘实测不符**（本次：state 落后 + 未来时刻）。

"想再检查一遍""感觉不放心"不构成理由。把校准的预算留给 D2.R1。

## 6. 本次没有证明什么

* **不证明产品可用。** 这一轮一行产品代码都没有写；`app/` 仍不存在。
* **不证明换品类可用。** `bex-02` 仍缺 7 份数据（其中两份是人工裁决记录，本项目不伪造签字），
  生成侧仍只有首轮四张候选。
* **不证明 G2 能过。** 它要一名**未参与开发的真人**走查，AI 代理只能预演。
* **不证明 state 从此不会漂。** J10 只覆盖"未来时刻"一种形态；`latest_audit` 是否最新、
  `unknowns` 是否漏记，仍然靠人核对磁盘。
* **D1.C2 未解除** ⇒ 任何引用 v2 基线或旧链回归结论的声明仍然不成立。
