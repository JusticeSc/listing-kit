# 第八次控制面校准（v1.12 → v1.13，2026-09-26）

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY
> 本文只记录这一次校准**为什么做、改了什么、读数如何**。计划正文见
> `docs/product-demo-goal-and-implementation-plan.md` §1.11 / §6.11.6 / §6.11.7 / §7.1；
> 当前状态与下一动作见 `_working/amz-listing-kit-product-demo/state.md`。本次**零付费调用**。

## 1. 触发：执行记录长在了计划里

按计划 §1.10 的准入条件，这一轮先问「有没有第 ③ 类 —— 执行记录与磁盘实测不符」，
而不是「要不要再检查一遍」。做法：把 state 与磁盘逐条比，再把计划正文里所有带时态的叙述
逐条比。**state 这次对得上**（D2.R1 已 done、证据文件在、`next_action_task` 可执行、
`updated_at` 不晚于文件写入时刻）。**计划对不上**：

| 计划正文 | 磁盘读数（2026-09-26 13:55 核对） | 守卫为什么全绿 |
|---|---|---|
| §1.10「阶段判定……Phase 2 未开工」 | `app/__init__.py`、`app/offline.py`、`app/views.py`、`app/server.py` 于 13:41–13:48 落盘；`app/server.py --offline-fixture demo/fixture/aster-01 --check` 退出码 0（5.3s）；`evals/product-demo/d2-r1-offline-tracer-2026-09-26.md` 13:51 落盘；state 的 Phase 2 = `active`、D2.R1 = `done` | 守卫读计划只核**结构与 ID**（任务表、Gate、依赖、证据存在性），没有一条判据会问「这行叙述还成立吗」 |

同一轮逐条核对还读到一件靠改字解决不了的事：**D2.R2 只有一行意向**。它是主链上唯一必须
由真人完成、AI 无法替代的环节，而「给走查者的任务说明」「观察要记哪几列」「什么算没通过」
此前只存在于意图里。意向不是合同，所以本轮把 §6.11.6、§6.11.7 补上。

## 2. 处置

| 处置 | 落在哪 | 解决什么 |
|---|---|---|
| 计划不再发布进度：§1.10 那句读数加时间限定，规则写进 §1.11 | 计划 §1.10、§1.11 | 消除一类**必然**漂移：代码改了，写在计划里的进度句不会自己变，也没有判据会抓住它 |
| 新增 §6.11.6「D2.R2 走查包」：拆成 R2.a（准备，AI 可独立做）/ R2.b（真人，不可替代） | 计划 §6.11.6 | 主链唯一的真人环节此前没有可执行规格，走查者拿不到「任务说明」这个东西 |
| 新增 §6.11.7「D2.R3 冻结清单」：把 §6.12 标着「拟定」的取值集中成逐条可关闭的决定 | 计划 §6.11.7 | §6.12 的「拟定」散在各节，没有一份清单能把它们逐条关掉；Phase 3 因此没有合格入口 |
| §7.1 增加真人资源规则（不许并行，先做 R2.a） | 计划 §7.1 | 环境阻塞有规则、真人阻塞没有，项目会静默停在 D2.R2；同时堵住「用提前开工把 G2 假定成通过」 |

本次**没有**改动 §2 Goal 文本、§3 完成合同、§4.1–§4.5；三份机器契约只更新冻结版本号。

## 3. 改了什么（哈希）

| 文件 | 改前 sha256 前 16 | 改后 sha256 前 16 | 字节 | 改动 |
|---|---|---|---|---|
| `docs/product-demo-goal-and-implementation-plan.md` | `F5459ECE1E8FBB0C` | `F7D2B03A14E9CAF8` | 103323 → 111604 | v1.12 → v1.13；§1.10 读数加时间限定；新增 §1.11、§6.11.6、§6.11.7；§7.1 增一条规则 |
| `demo/contract/processing_contracts.json` | `26DB7A70C22603C0` | `A2AAD4B6E01E15DB` | 11648（不变） | 只改 `plan_version` → v1.13 |
| `demo/contract/authority_matrix.json` | `30D70F12AA4F78A7` | `FA1EFCFF58C08FA8` | 6386（不变） | 同上 |
| `demo/contract/state_vocabulary.json` | `0B0114FAF1930B06` | `DB34B4D2DF3232A0` | 1479（不变） | 同上 |
| `_working/amz-listing-kit-product-demo/state.md` | `F1285A64960B543A` | `BD4E5920090DD956` | 6001 → 6146 | `latest_audit` 与 Phase 2 的证据指向本次校准；新增一条 unknown（任务说明的作者偏差）；`updated_at` 改为实际写入时刻 |

## 4. 契约先红后绿（证明版本号不是摆设）

计划一升版本、契约还没重审时，守卫**当场报红**，原样读数：

```
计划：docs/product-demo-goal-and-implementation-plan.md（v1.13）
与计划漂移：1 条问题
  ✗ 契约按计划版本 v1.12 冻结，当前计划是 v1.13 —— 计划改过，合同必须重审
rc=3
```

重审（只改三份 JSON 的 `plan_version`，词汇与状态取值一字未动）后：
`--check` rc=0（五组检查全通过，识别为 v1.13）；`--self-test` 18/18。

## 5. 快照与过程失误登记

- **本轮改前快照**：`_stage-amz-control/calib8-20260926-1357/`（13 份：计划 v1.12、`docs/INDEX.md`、
  `README.md`、state、三份契约、`app/` 四份、`evals/probes/offline_app.py`、D2.R1 证据）。
- **登记上一轮（D2.R1）的过程失误**：改 `README.md` 与新建 `app/` 之前**没有按 INDEX §5 先留快照**。
  实际损失可核，两条都查过：
  ① `app/` 四份是本轮新增文件 —— 扫描 `_stage-amz-control` 全目录（含所有历史快照）确认改前
  不存在任何副本，因此不存在「被覆盖的旧版本」；
  ② `README.md` 的改前版本**实际还在**：第七次校准的快照
  `_stage-amz-control/plan-v112-20260926-1345/README.md` 为 `42F3F86857203B99`（54609 B），
  D2.R1 改后为 `56B3BC2A91738382`（56465 B）。
  结论：**这一次没有丢失不可恢复的历史版本，失误在流程不在数据** —— 但流程失误仍是失误，
  补做的办法是把改后状态（`app/` 四份、`README.md`、D2.R1 证据、探针）一并快照进本轮目录（已做）。

## 6. 守卫读数（全部本次运行，无一项沿用旧报告）

| 检查 | 读数 |
|---|---|
| `demo/contract/contract_tools.py --check` / `--self-test` | 通过（识别为 v1.13）/ 18/18 |
| `tools/check_project_state.py --project .` | 全过（J0–J10，退出码 0） |
| `evals/probes/project_state.py` | 19 向全部与预期一致，并逐字节恢复 state（串行独占运行） |
| `tools/check_docs.py` | 全过（登记 30 = 实际 30；真跑 11 条命令） |
| `evals/probes/offline_app.py` | 5 向全部与预期一致 |
| `app/server.py --offline-fixture demo/fixture/aster-01 --check` | 全过（5.3s；目录 10897 个文件未被动过；读过的 20 个文件逐字节未变；八页数据齐） |
| `tools/check_forbidden_rules.py` | 两份清单都在生效 |
| `demo/verify/swap_probe.py report` / `self-test` | `default_package_control_ok` / 7/7 |
| `demo/verify/fact_capability.py check` / `self-test` | 全过 / 10/10 |
| `demo/verify/verifier_registry.py` | 全过（R1–R9） |

## 7. 没有解决的

- **D2.R2 的 R2.b 仍然没有真人**（state 的 unknown `real_uninvolved_user_for_phase2_not_yet_arranged`
  继续有效）。R2.a 可做，但它不给 G2 记账。
- **任务说明的作者偏差**：说明由写产品的人写，容易把开发者词汇带进去，而被测者正是要检验
  这些词看不看得懂。计划 §6.11.6 已写明缓解办法（照说明自己预演一遍，说明里出现而页面上
  没有落点的词就算缺口）与限制（不假装说明是中立的）；state 新增同名 unknown。
- `D1.C2` 仍因本机可用提交内存不足而 blocked：任何引用 v2 基线或旧链回归结论作为证据的
  声明，在它解除前不成立（§7.1）。
