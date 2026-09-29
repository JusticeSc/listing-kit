# 第五次控制面校准（2026-09-26 · v1.9 → v1.10）

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY
> 记录时间：2026-09-26。本文只记录这次怎么校准、读到什么、改了哪些权威文件。
> 当前状态与下一动作见 `_working/amz-listing-kit-product-demo/state.md`；计划修订范围见计划 §1.8。
> 逐条读数、复现脚本与产物哈希见 `evals/product-demo/d1-r3-verifier-registry-2026-09-26.md`。

## 1. 这次校准的触发

不是新需求，也不是实现 bug，而是 D1.R3 把 D1.R1 的能力矩阵落成**可执行注册表**时暴露的
控制面问题：**同一个事实有两个出处**。

D1.R1 的矩阵（商品包数据）逐能力写了结论域，D1.R3 的注册表（跨商品声明）又写了一遍。
两处不一致 —— 矩阵写 `pass/manual/fail/unknown/not_applicable`，注册表初稿只写
`pass/fail/not_applicable`。这不是「谁写得漂亮」，而是「哪一处说了算」没有被登记。

按 §4.6，结论域与签字粒度属于**验证器能力声明**（跨商品、随实现冻结），落点只有一个：
`demo/verify/verifier_registry.py`；矩阵保留逐事实的「这条事实在这张商品上要什么」。
两者必须相容，由 R8 逐值检查。

## 2. 守卫读数（本次全部重跑）

| 守卫 | 命令 | 读数 |
|---|---|---|
| 项目状态 | `tools/check_project_state.py --project .` | rc=0（J0–J9 全过） |
| 文档登记 | `tools/check_docs.py` | rc=0（已登记 30 份 = 实际 30 份） |
| 处理合同 | `demo/contract/contract_tools.py --project . --check` | rc=0（13 条合同 / 27 项权威；计划 v1.10） |
| 合同自检 | 同上 `--self-test` | 18/18 |
| 能力矩阵 | `demo/verify/fact_capability.py check --project .` | rc=0（C1–C10） |
| 能力矩阵自检 | 同上 `self-test` | 10/10 |
| 量测器尺寸契约 | `demo/fixture/measure_cylinder.py self-test` | 4/4 |
| 前半链合同 | `demo/core/run_front_contracts.py` | rc=0（17/17） |
| 后半链合同 | `demo/core/run_back_contracts.py` | rc=0（22/22） |
| 后半链变异 | 同上 `--mutation-test` | 12/12 |
| 验证器注册表 | `demo/verify/verifier_registry.py check --project .` | rc=0（R1–R9） |
| 注册表自检 | 同上 `self-test --project .` | 9/9 |
| 参考包 / 禁用词 | `pack_tools.py verify` / `check_forbidden_rules.py` | READY / OK |
| 硬规矩 1 探针 | `rg -n 'aster-01\|bex-02' demo/core demo/verify demo/provider --glob '*.py'` | 零命中 |

## 3. 找出的漂移与处置

| # | 漂移 | 证据 | 处置 |
|---|---|---|---|
| 1 | **同一事实两个出处（结论域）**：矩阵给 `cylinder-v1` 写了 `manual/unknown`，注册表初稿没有 —— 而 `factcard` 的档位就是 `pass/manual/hard_fail/unknown` | `_stage-amz-control/d1r3_drift_probe.py`：把注册表改回初稿后 R8 报 7 条「矩阵里声称能给出 manual、unknown，注册表的结论域里没有」 | 结论域权威放注册表；R8 增加「矩阵的逐能力结论域不得比注册表更宽」的逐值检查；`self-test` 增加 `matrix_domain_widens` 用例 |
| 2 | **同一事实两个出处（签字粒度）**：注册表声明 `{fact_id, candidate_id}`，验证层却另计划放一份 `routing.py` | 注册表初稿的 `implemented_in` 指向一个并不存在的 `demo/verify/routing.py` | 落点改为 `demo/core/back_chain.py::fact_routing` + 商品包 `human_fact_review.json`；新增 `signature_index` 让粒度成为可测对象；B20/M11 证伪「聚合同意算签字」 |
| 3 | **注册表自检的改坏用例不可靠**：有一条用例用了死代码（`mutate_plan(lambda p: None) and matrix`），另一条注入的未注册路由没写全前提，会让 R1 之外多红一处 | 静态复核 | 重写用例表为四元组（名字、期望规则、允许一同变红的规则、构造器）；自检增加「未登记的多红即失败」——守卫不再只能说 OK |
| 4 | **一处不诚实引用**：注册表 `human` 的 `implemented_in` 写了不存在的文件 | 同上 | 改为真实落点 |

漂移 1 与 2 是同一形态的两例：**能力声明被写了两遍**。它们不会让任何一次测试变红 ——
矩阵照样通过，注册表照样自检通过，只有把两者逐值比对才会露出来。这正是「政出一门」
必须由机器守、不能只靠约定的原因。

## 4. 本次改了什么权威文件

| 文件 | 改动 | 为什么 |
|---|---|---|
| 计划 §1.8（新增） | 记录第五次校准的触发、处置口径与修订范围 | 属于计划自身的修订记录 |
| 计划 §6.10.5 | 由一段规格升为 R3.1–R3.5 环节级规格（落点 / 输入 / 处理 / 输出 / 验收） | 只写「最小事实验证路由」时，注册表落点与签字粒度无处安放 |
| 计划版本 | v1.9 → v1.10 | 计划改过，契约必须重审 |
| 三份机器契约 | 只更新 `plan_version`，内容不变 | 本次没有改动 §4.1 / §4.2 / §4.4 |

本次**没有**改动 §2 Goal 文本、§3 完成合同、§4.1 权威对象、§4.2 状态边界、§4.4 处理合同
与 §4.5 / §4.6。v1.10 不表示「更完成」，只表示「同一事实只有一个出处，且这条能被跑红」。

## 5. 快照与回滚

改动前的 7 份文件快照在 `E:\gitee_repository\vison\_stage-amz-control\d1r3-land-20260926-123347\`。
本项目不是 git 仓库，回滚依赖这份工作区外快照。
