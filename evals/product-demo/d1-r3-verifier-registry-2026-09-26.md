# D1.R3 验证器能力注册表（2026-09-26 · 计划 v1.9 → v1.10）

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY
> 记录时间：2026-09-26。本文只记录 D1.R3 怎么做的、读到什么、改动了哪些权威文件。
> 当前状态与下一动作见 `_working/amz-listing-kit-product-demo/state.md`；计划修订范围见计划 §1.8 与 §6.10.5。
> 本次**零付费调用**：全部读数来自离线脚本与守卫，没有调用生图或视觉模型。

## 1. 这一任务要回答什么

计划 §6.10.5 的验收有三句：高置信规则可 hard fail；故意删掉一条适用性检查必须让对应用例变红；
人工必须显式确认具体事实，不得由一般性同意推断。它们都不是「写了就算」的句子 —— 每一句都要有一条
能被跑红的实现与一条能把它打红的反例。

做法：把 D1.R1 的能力矩阵与 D1.R2 的对照结论落成**可执行注册表**（声明与实现分开），
让 PC-09 的路由只读声明、不再用 if/else 记住每个验证器的脾气；再给每条声明配一条反向测试。

## 2. 产物

| 产物 | 路径 | 大小 | SHA256 前 16 |
|---|---|---|---|
| 验证器能力注册表 | `demo/verify/verifier_registry.py` | 20137 B | `de8aa80d1e66052b` |
| 路由（改为消费注册表） | `demo/core/back_chain.py` | 41466 B | `bf63503bcec9e670` |
| 反向测试（B18–B21 / M9–M12） | `demo/core/run_back_contracts.py` | 50641 B | `d95b9b4bd4f3047c` |
| 计划（v1.10） | `docs/product-demo-goal-and-implementation-plan.md` | 93411 B | `033d9fac290a8fa4` |
| 机器契约（三份） | `demo/contract/processing_contracts.json` 等 | — | `02c2ee85…` / `b26a7f1d…` / `9f749dcd…` |

注册表登记 **3 个验证器**（`cylinder-v1` 确定性 / `refcond-vlm` 模型 / `human` 人工）
与 **9 条守卫规则**；路由计划 8 条事实、22 条逐能力声明全部落在注册表里。

## 3. 环节级实现

| 环节 | 实现 | 关键判据 |
|---|---|---|
| R3.1 能力注册表 | 每个验证器登记 `kind / verdict_domain / evidence_shape / cannot_prove / requires_declaration / calibration`，模型另登记 `default_verdict`、`auto_adjudication`、`model` | `check` 退出码 0（九条规则全绿）；`self-test` 九种改坏**各自**让对应规则变红，且未登记的多红会失败 |
| R3.2 路由消费注册表 | `fact_routing(..., registry=None)` 默认读 `VERIFIER_REGISTRY`；责任者 id 不在注册表 → 轨迹记 `unregistered_router`，结论作废；`kind` 与注册表不一致 → 记 `declaration_mismatch` | B18：注入 `ghost-verifier` 后 F4 保持未决、阻断选择 |
| R3.3 逐事实 ReviewItem | PC-09 载荷新增 `review_items`：`owner / owner_kind / verdict / state / evidence_pointer / evidence_required` | B19：条数=事实数、责任者与事实记录一致、证据指针齐备、`evidence_required` 逐值等于注册表声明的 `evidence_shape` |
| R3.4 人工签字粒度 | 新增 `signature_index`，键为 `{fact_id, candidate_id}` | B20：只留一条「整组通过」时，8 条事实全部保持未决，且阻断选择 |
| R3.5 反向测试 | B18–B21 用例 + M9–M12 变异 | 变异测试 12/12 |

## 4. 守卫读数（本次全部重跑）

| 守卫 | 命令 | 读数 |
|---|---|---|
| 项目状态 | `tools/check_project_state.py --project .` | rc=0（J0–J9 全过） |
| 文档登记 | `tools/check_docs.py` | rc=0（已登记 30 份 = 实际 30 份；真跑 10 条命令） |
| 处理合同 | `demo/contract/contract_tools.py --project . --check` | rc=0（13 条合同 / 27 项权威 / 与计划漂移：通过；计划 v1.10） |
| 合同自检 | 同上 `--self-test` | 18/18 |
| 能力矩阵 | `demo/verify/fact_capability.py check --project .` | rc=0（C1–C10 全过） |
| 能力矩阵自检 | 同上 `self-test` | 10/10 |
| 量测器尺寸契约 | `demo/fixture/measure_cylinder.py self-test` | 4/4 |
| 前半链合同 | `demo/core/run_front_contracts.py` | rc=0（17/17） |
| 后半链合同 | `demo/core/run_back_contracts.py` | rc=0（**22/22**，本次由 18 增至 22） |
| 后半链变异 | 同上 `--mutation-test` | **12/12**（本次由 8 增至 12） |
| 验证器注册表 | `demo/verify/verifier_registry.py check --project .` | rc=0（R1–R9 全绿） |
| 注册表自检 | 同上 `self-test --project .` | **9/9**（本次新增） |
| 参考包 | `demo/fixture/pack_tools.py verify --project .` | READY |
| 禁用词 | `tools/check_forbidden_rules.py` | OK（保留 1 / 拦下 3） |
| 硬规矩 1 探针 | `rg -n 'aster-01\|bex-02' demo/core demo/verify demo/provider --glob '*.py'` | 零命中（`app/` 尚未创建，Phase 2 起纳入） |

## 5. 校准发现：注册表比实现窄（本次最该记住的一条）

D1.R3 的注册表初稿给 `cylinder-v1` 写了结论域 `["pass","fail","not_applicable"]`，
而 D1.R1 的能力矩阵在 F1–F7 上逐条写的是 `["pass","manual","fail","unknown","not_applicable"]`。
**漏掉的 `manual` 与 `unknown` 恰恰是量测器真的会输出的**：`demo/fixture/factcard.py`
的档位是 `pass / manual / hard_fail / unknown`。注册表比实现窄，等于把「落在人工档」
与「没量到值」悄悄当成没有发生过 —— 而这两件事本该分别走到人工确认与 Unknown。

这是「同一个事实有两个出处」的典型形态，处置是：结论域与签字粒度的权威放在**注册表**，
矩阵保留逐事实的「这条事实在这张商品上要什么」，两者相容性由 R8 逐值检查（矩阵的逐能力
结论域不得比注册表更宽）。

复现（`_stage-amz-control/d1r3_drift_probe.py`，零付费）：

```
基线 R8: [] | 九条非空数: 0
把注册表结论域改回初稿（窄）后：
   R8_MATRIX_ALIGNMENT -> ['cylinder-v1 在矩阵里声称能给出 manual、unknown，注册表的结论域里没有', …]
R8 变红: True
矩阵声称给出 certified 后 R8: ['cylinder-v1 在矩阵里声称能给出 certified，注册表的结论域里没有']
注册表条目: ['cylinder-v1', 'human', 'refcond-vlm'] | 规则数: 9
cylinder-v1 结论域: ['pass', 'manual', 'fail', 'unknown', 'not_applicable']
矩阵 F1 cylinder-v1 结论域: ['pass', 'manual', 'fail', 'unknown', 'not_applicable']
```

按项目纪律「反例没红先怀疑测试框架再怀疑实现」：这里先确认**守卫能抓住这处漂移**，
再定稿注册表 —— 否则一个只会说 OK 的守卫等于没有守卫。

## 6. 反向测试明细

| 改坏 | 期望变红 | 实际 | 读到的读数 |
|---|---|---|---|
| 注册表声明不适用交给下一个责任者 | R5 | 红 | cylinder-v1 的 `on_not_applicable` 改成 `accept` |
| 未经校准的模型允许自动裁决 | R3 | 红 | `auto_adjudication: true` 且 `must_catch_missed: 2` |
| 不能自动裁决的模型默认给 pass | R4 | 红 | `default_verdict: "pass"` |
| 人工能力不要求显式签字 | R6 | 红 | `requires_explicit_signature: false` |
| 验证器没有证据形态 | R7 | 红 | 同时按登记让 R2 一并变红（`evidence_shape` 是声明必填项） |
| 路由里出现未注册的责任者 | R1 | 红 | 注入一条前提写全、id 不在册的路由，只有 R1 变红 |
| 矩阵里出现未注册的能力 id | R8 | 红 | 第一条确定性能力改成 `not-registered` |
| 矩阵的结论域比注册表宽 | R8 | 红 | 声称给出 `certified` |
| 纯人工事实被挂上机器责任者 | R9 | 红 | 往 F8 插一条 `cylinder-v1` |
| 未注册责任者被当成通过 | B18 | 红 | M9 |
| 逐事实 ReviewItem 被拿掉 | B19 | 红 | M10 |
| 签字当成「一条同意 = 全部同意」 | B20 | 红 | M11 |
| 注册表的适用性前置声明被拿掉 | B21 | 红 | M12 |

## 7. 这次改了什么权威文件

| 文件 | 改动 | 为什么 |
|---|---|---|
| `demo/verify/verifier_registry.py` | 新增（D1.R3 的核心产物） | 能力声明的唯一出处；九条规则可 `check` / `self-test` |
| `demo/core/back_chain.py` | `fact_routing` 消费注册表；新增 `signature_index`；PC-09 载荷新增 `review_items` 与 `verifier_registry` | 路由不再硬编码「模型默认只报风险」这类声明；未注册责任者结论作废 |
| `demo/core/run_back_contracts.py` | 新增 B18–B21、M9–M12 | 每条新声明都要有能把它打红的反例 |
| 计划 §1.8 + §6.10.5 | 新增第五次校准记录；D1.R3 升为 R3.1–R3.5 环节级规格；版本 v1.10 | §1.8 记录「同一事实两个出处」的处置口径 |
| 三份机器契约 | `plan_version` v1.9 → v1.10，内容不变 | 计划改过，契约必须重审；本次只重审版本，不改词汇 |

## 8. 这次**没有**证明什么

- 没有证明模型路线可用：`refcond-vlm` 仍然是 `auto_adjudication: false`，D1.R2 的两个漏报
  （多两条筋、画面里多一个杯子）与 F6 上的 4 条 Unknown 一条都没修。
- 没有证明场景候选的 F1–F8 由机器判过：四张候选的确定性路线仍整条不适用（前提不成立），
  事实结论仍由显式人工确认承担。
- 没有证明跨商品通用：注册表里没有商品名（硬规矩 1 探针零命中），但这只证明「配置与流程解耦」，
  真正的跨商品结论属于 D1.P4 与 §5.1 P4。
- 没有付费调用：本次预算账本仍为 **4/8**，视觉模型阶段用量仍为 **16/40**。
- `review_items` 目前只被 B19 读：它要成为界面的审阅单元，还需要 Phase 3–5 的本地产品接上。

## 9. 快照与回滚

改动前的 7 份文件快照在 `E:\gitee_repository\vison\_stage-amz-control\d1r3-land-20260926-123347\`
（含 `SNAPSHOT` 同级的逐文件 SHA256）。本项目不是 git 仓库，回滚依赖这份工作区外快照。
