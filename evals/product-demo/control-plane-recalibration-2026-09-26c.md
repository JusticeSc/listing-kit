# 第四次控制面校准（2026-09-26 · v1.8 → v1.9）

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY
> 记录时间：2026-09-26。本文只记录这次怎么校准、读到什么、改了哪些权威文件。
> 当前状态与下一动作见 `_working/amz-listing-kit-product-demo/state.md`；计划修订范围见计划 §1.7。

## 1. 这次校准的触发

不是新需求，是 D1.R2 试点跑出来的两条实测事实：一条是判据错位（把主体贴到中性底衬之后
再探「底衬是否中性」，量的是自己刚铺的灰），一条是量测器缺陷（4×4 降采样块在非 4 倍数
尺寸上把量测打断）。两件事都不属于「下一步怎么做」，只能回到唯一权威去改。逐条读数见
`evals/product-demo/d1-r2-route-comparison-2026-09-26.md`。

## 2. 守卫读数（本次全部重跑）

| 守卫 | 命令 | 读数 |
|---|---|---|
| 项目状态 | `tools/check_project_state.py --project .` | rc=0（J0–J9 全过） |
| 文档登记 | `tools/check_docs.py` | rc=0（已登记 30 份 = 实际 30 份；真跑 10 条命令） |
| 处理合同 | `demo/contract/contract_tools.py --project . --check` | rc=0（13 条合同 / 27 项权威 / 与计划漂移：通过；计划 v1.9） |
| 合同自检 | 同上 `--self-test` | 18/18 项被正确抓到 |
| 能力矩阵 | `demo/verify/fact_capability.py check --project .` | rc=0（C1–C10 全过，8 事实 / 22 声明） |
| 能力矩阵自检 | 同上 `self-test` | 10/10 项被正确抓到 |
| 量测器尺寸契约 | `demo/fixture/measure_cylinder.py self-test --project .` | 4/4（本次新增） |
| 前半链合同 | `demo/core/run_front_contracts.py` | rc=0（17/17） |
| 后半链合同 | `demo/core/run_back_contracts.py` | rc=0（18/18） |
| 参考包 | `demo/fixture/pack_tools.py verify --project .` | READY |
| 禁用词 | `tools/check_forbidden_rules.py` | OK（保留 1 / 拦下 3） |
| 硬规矩 1 探针 | `rg -n 'aster-01|bex-02' demo/core demo/verify app demo/provider --glob '*.py'` | 改前 9 行 → 改后 **7 行**，全部是 D1.P4 步骤 0 已登记的收拢项；`demo/verify/` 零命中 |

## 3. 找出的漂移与处置

| # | 漂移 | 证据 | 处置 |
|---|---|---|---|
| 1 | **判据自证**：路线 A 把主体贴到中性底衬后，再在画布上探「底衬是否中性」，读数 0.5772 / 0.5666 判「通过」 | `evals/product-demo/d1-r2/route-a.json` 首次试点；同一张受控底衬图原图探针 0.0、画布探针 0.19–0.30 | 适用性改在**原图**上判；画布探针改名并标 `self_referential`；计划 §4.5 新增第 7 条不变量「不许自证」 |
| 2 | **量测器尺寸前提没声明**：`np.kron(...)[:h,:w]` 在 h 或 w 非 4 倍数时比原图小，广播失败 | 试点 `ValueError: shapes (1173,370) (1172,368)`；`self-test` 红→绿 | 新增 `expand_blocks`（只对齐形状、不改语义）+ 形状断言；同型式子 `mutate_negative.py`、`scene_scope_control.py` 一并收敛；计划 §9.1.1 补尺寸前提 |
| 3 | **对照脚本把商品身份写进验证层**：`demo/verify/route_compare.py` 里写死边界样本商品名 | 硬规矩 1 探针改前 9 行中的 2 行 | 边界样本改从商品包目录派生；计划 §4.6 明确硬规矩 1 也管 `demo/verify/` 的离线对照脚本 |
| 4 | **对照脚本的结论域读错**：只认 `fail`，而 `factcard` 的结论域是 `pass/manual/hard_fail/unknown/human` | 首版汇总把 6 个真被拦下的负样本全记成漏报（`detected: 0, missed: 6`） | 按结论域改判；`classify` 同时把「有变异但机器不得硬判」从「误报」里拆出来（`risk_on_human_only_case`） |
| 5 | **计划里 D1.R2 只有一句话规格**，缺陷、判定位置与证据顺序都无处安放 | 计划 v1.8 §6.10.4 | 升为 R2.0–R2.5 环节级规格（输入 / 处理 / 输出 / 验收 / 失败路径） |
| 6 | 报告无法在不花钱的前提下重算 | 判据修正后需要重跑 15 次调用才能更新汇总 | 新增 `--remerge`：用已保存的逐路线读数重算报告，零请求 |

**漂移 4 是这次校准最该记住的一条**：它不是"模型判错了"，而是**守卫自己把标准读错了**。
第一版汇总显示 A 漏报 6 例，与逐图 `overall=hard_fail` 直接矛盾；按项目既有纪律
「反例没红先怀疑测试框架」，先查判据而不是查实现，才找到这里。

## 4. 改了哪些权威文件

| 文件 | 前 sha256(16) | 后 sha256(16) | 字节 |
|---|---|---|---|
| `docs/product-demo-goal-and-implementation-plan.md` | 729fcb744579f588 | 5b2f61f78e4edc1a | 80418 → 89257 |
| `_working/amz-listing-kit-product-demo/state.md` | acad7049242bd253 | b2d6db08473cb7b1 | 4165 → 4521 |
| `demo/contract/processing_contracts.json` | 8a3534c60ff3f74d | f3f018d650acf196 | 11646（只改 `plan_version`） |
| `demo/contract/authority_matrix.json` | f1844b546cef8470 | e3fa03b221907f28 | 6384（只改 `plan_version`） |
| `demo/contract/state_vocabulary.json` | 10637949c4f92f2c | c45fd5315b95258f | 1477（只改 `plan_version`） |
| `demo/fixture/measure_cylinder.py` | 1167264360bc3d5f | cf5cc73f6ae207b1 | 13990 → 22685 |
| `demo/verify/route_compare.py` | 767a005dda4c863b | 3cf40fb8bd0937c7 | 23127 → 29896 |

计划只动六处：新增 §1.7、§4.5 第 7 条不变量、§4.6 硬规矩 1 的执行范围、§6.10.4 环节级规格
（R2.0–R2.5）、§9.1.1 尺寸前提、新增 §6.13 Phase 6–7 环节级规格（其中 §1.7 是记录本身）。
**没有**改动 §2 Goal 文本、
§3 完成合同、§4.1 权威对象、§4.2 状态边界与 §4.4 处理合同；三份机器契约因此只更新冻结版本号。
v1.9 不表示「更完成」，只表示「判据不再自证、缺陷有回归」。

改前快照：`E:\gitee_repository\vison\_stage-amz-control\calib4-20260926-115331\`（含 `SNAPSHOT.md`）。

## 5. 读数不变的证据

- 量测器修复前后，对全部 11 张冻结图（3 对照 + 夹具正面 + 7 负样本）逐图输出 JSON
  **逐字节相同**：`sha256 ee7d7e738acc2102`（8594 B）→ 同一个哈希。
- 自检 `T3` 另给一条：同图 1344×1344 → 1341×1343，`overall` 都是 `pass`，逐指标最大漂移 `0.0000`。
- 前半链 17/17、后半链 18/18 与本次改动前一致。

## 6. 顺带发现的、本次不修的问题（登记）

| 问题 | 证据 | 为什么不在这里修 |
|---|---|---|
| `--report <相对路径>` 会在写完报告后崩：`path.relative_to(ROOT)` 对未解析路径报错（`run_front_contracts.py`、`run_back_contracts.py`） | 本次用 `--report .cache/...` 触发，写文件成功、退出码 1 | 属于 CLI 参数处理，不影响任何判据读数；登记待与 `contract_report_bytes_not_reproducible` 一起处理 |
| 合同报告的字节不可复现：`detail` 里带沙箱绝对临时路径 | 本次重跑 `front-contracts.json` / `back-contracts.json`，逻辑读数不变、临时路径变化（旧 unknown 的又一个实例） | 同上；本次已在 state 的 `unknowns` 中保留 |
| `measure_f1_f8.py` 有同型尺寸缺陷 | 与 `measure_cylinder.py` 同一段式子 | 该文件已标 `[SUPERSEDED]`，是 D0.1 的历史证据、不驱动判定；改它反而破坏证据链 |

## 7. 本次证据不证明什么

- 不证明 G1 通过（那是 D1.R4），不证明场景候选的事实已被机器判过，也不证明跨商品泛化（那是 D1.P4）。
- 守卫全绿只说明这些判据在**当前冻结样本**上自洽，不说明覆盖了未出现的输入类型。
- 本节所有「已修」结论都指向前一节的具体命令与哈希；没有另写第二份规范。