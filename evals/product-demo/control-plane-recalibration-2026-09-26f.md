# 第七次控制面校准（v1.11 → v1.12，2026-09-26）

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY
> 本文只记录这一次校准**为什么做、改了什么、读数如何**。计划正文见
> `docs/product-demo-goal-and-implementation-plan.md` §1.10 与 §6.11；当前状态与下一动作见
> `_working/amz-listing-kit-product-demo/state.md`。本次**零付费调用**。

## 1. 触发：执行记录写了三处它没做过的事

不是"再检查一遍"。本轮先把守卫全部重跑一遍（读数见 §4，除 state 外全绿），
然后**逐条核对 state 与磁盘**，读到三处不一致：

| 现象 | 磁盘读数 | 当时守卫为什么是绿的 |
|---|---|---|
| `updated_at: 2026-09-26T14:05:00+08:00` | 文件最后写入 **12:50:37**，核对时墙钟 **13:28:36** | J2 只管 status 的取值域，J6 只管证据文件在不在 —— 没有一条判据会问「这个时刻发生过吗」 |
| `latest_audit` 指向 `control-plane-recalibration-2026-09-26d.md` | 更新的一份 `-e` 已在 13:26:08 落盘 | J8 只查「指向的文件存不存在、带不带 NOT-AUTHORITY」 |
| `next_action_task: D1.P4` | D1.P4 的两条读数 13:23 已产出，两个包都退出码 0 | J7 只查「这个任务在计划里、是 pending、依赖已 done」—— 它没被登记，就默认还是 pending |

三处是**同一类**：执行记录超前或落后于磁盘，并附带一个没有发生过的时刻。这不是笔误，
它恰好制造了「现在什么情况」这个问题本身 —— 读者（包括下一个 Agent）按 state 判断进度，
而 state 与磁盘不一致。**发现方式与第六次相同：重跑 + 逐条核对读数**，不是静态扫描，
也不是读上一份报告。

## 2. 阶段判定：现在在哪、下一步做什么

按计划自己的阶段定义回答（这一问此前每次靠口头重答，本轮写入计划 §1.10）：

| | 状态 | 依据 |
|---|---|---|
| Phase -1 / 0 / 1 | **完成** | G-1 / G0 / G1 各有当前证据；G1 本轮重跑 `demo/verify/g1_audit.py check --project .` 仍为 `pass` |
| Phase 2 | **未开工** | 离线 tracer 界面、任务说明、观察记录一个都还不存在 |
| D1.C2 | **仍 blocked** | 本机可用提交内存 8.0–8.4 GB < 9 GB；§7.1 已与环境解耦，但「引用 v2 基线作证明」的声明在它解除前不成立 |

换成软件周期的语言：**可行性与能力验证已经做完，产品本身一行运行时代码都还没有。**
`demo/` 是控制面加离线验证器；`src/`、`web/` 是上一代（v2）实现，不是本 Goal 的产物；
`app/` 目录不存在。所以「还差什么」的答案不是再校准一次，而是**一个陌生人能打开的东西**。

## 3. 改了什么

（三份机器契约只更新冻结版本号；§2 Goal 文本、§3 完成合同、§4.1–§4.5 一字未动。）

| 文件 | 改前 sha256 前 16 | 改后 sha256 前 16 | 字节 | 改动 |
|---|---|---|---|---|
| `docs/product-demo-goal-and-implementation-plan.md` | `E36191ED3496A4AD` | `F5459ECE1E8FBB0C` | 103323 | v1.11 → v1.12；新增 §1.10；§6.11 改写为可执行规格（新增 6.11.1–6.11.5） |
| `tools/check_project_state.py` | — | `AA037A716A88011C` | 26635 | 新增判据 **J10** |
| `evals/probes/project_state.py` | — | `7DE48496B2FDC983` | 13856 | 反向对照 17 向 → **19 向**；并修正探针自己的依赖语义与 tag 正则（见 §3.3） |
| `README.md` | — | `42F3F86857203B99` | 54609 | 「十七向植入对照」→「十九向」（该数字由 `tools/check_docs.py` 按探针 `--count` 核对） |
| `demo/contract/processing_contracts.json` | `58C25EA2F521096A` | `26DB7A70C22603C0` | 11648 | `plan_version` → v1.12 |
| `demo/contract/authority_matrix.json` | `9DA0F7680A96FF3B` | `30D70F12AA4F78A7` | 6386 | 同上 |
| `demo/contract/state_vocabulary.json` | `2C350E02560BD5B8` | `0B0114FAF1930B06` | 1479 | 同上 |
| `_working/amz-listing-kit-product-demo/state.md` | `A12B1F6D3EB822A4` | `62F119A1A2AAC128` | 5688 | 见 §3.2 |

表中「—」的三份（`tools/check_project_state.py`、`evals/probes/project_state.py`、`README.md`）
本轮**没有留改前快照**，这是过程失误：INDEX §5 要求改受管文件前先快照，而 `README.md`
在受管集合里。实际损失可核：README 只改了一个数字（17 → 19，可由探针 `--count` 的历史值
推出），两个 `.py` 的逐条改动记在 §3.3。改后状态已快照到
`_stage-amz-control/plan-v112-20260926-1345/`（8 份）。

### 3.1 新判据 J10 落地前后的读数

判据生效、state 尚未修正时捕获（原样）：

    ✗ [J10] _working/amz-listing-kit-product-demo/state.md 的 updated_at=2026-09-26 14:05:00+08:00
      比这个文件最后写入的时刻 2026-09-26T13:30:05+08:00 还晚 35 分钟 —— 读数是跑出来的，
      不许写一个还没发生的时刻。

**这条判据的边界**：它只抓「比文件 mtime 晚」。它抓得住凭空写的未来时刻，抓不住
「12:50 写的时候填 12:40」这种往回编 —— 往回编更隐蔽，要拿运行日志逐条比才看得出来，
本文不声称已覆盖。

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
