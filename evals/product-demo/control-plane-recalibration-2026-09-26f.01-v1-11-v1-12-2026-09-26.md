<!-- 拆分件 01/02 · 父文档 evals/product-demo/control-plane-recalibration-2026-09-26f.md -->
# 第七次控制面校准（v1.11 → v1.12，2026-09-26）
[返回 control-plane-recalibration-2026-09-26f.md](control-plane-recalibration-2026-09-26f.md)

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

