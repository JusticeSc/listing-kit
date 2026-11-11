<!-- 拆分件 03/03 · 父文档 evals/product-demo/d1-p4-swap-probe-2026-09-26b.md -->
# 4. 这一轮抓到并修掉的真缺陷：适用性阈值的位置漂移
[返回 d1-p4-swap-probe-2026-09-26b.md](d1-p4-swap-probe-2026-09-26b.md)

## 4. 这一轮抓到并修掉的真缺陷：适用性阈值的位置漂移

这不是顺手的整理，是**先看见读数变了**才回头查出来的：

1. D1.P4 步骤 0（上一轮）把 `demo/core/verifier_plan.aster-01.json` 收进了
   `demo/fixture/aster-01/verifier_plan.json`。
2. `demo/verify/route_compare.py::applicability_max()` 仍按旧位置
   `(project / "demo" / "core").glob("verifier_plan.*.json")` 找适用性阈值。
3. 找不到阈值时它不再报错，而是把 `max_share` 记为 `None` → `applicable=False`，
   理由是「没有可用的适用性阈值」—— 于是**「阈值缺失」被写成了「前提不成立」**。

改前/改后的实测读数（同一批 15 张输入，离线、零付费）：

| 读数 | 改前（旧位置 glob） | 改后（从商品包读） | D1.R2 记录的读数 |
|---|---|---|---|
| 四张场景候选 `适用` | 否 | 否 | 否 |
| 负样本 `适用` | **否**（错） | 是 | 是 |
| 汇总 A | `detected 0 / missed 6` | `detected 6 / missed 0 / false_alarm 0` | 6 个必须拦下的 6/6 拦下、0 误报 |
| 逐张读数 | 与 D1.R2 表不一致 | 与 D1.R2 表**逐条一致**（`F-01 0.2063/否`、`neg-01 0.0/是 hard_fail`、`control-A 0.0/是 manual`、`bex-02 0.0/是 hard_fail` …） | — |

改后用 `--remerge` 重算派生报告：`evals/product-demo/d1-r2/route-comparison.json`
**49134 字节**，与 D1.R2 证据 §8 记录的字节数相同（sha 不同，因为 `ran_at` 与逐张
`elapsed_s` 每次都会变）。也就是说：**这个缺陷当时改的是验证结论，不是格式**。

### 4.1 为什么之前没被发现，以及现在补了什么

* 没有任何守卫会把「数据搬了家、读它的代码没跟着搬」判红：静态扫描原来只找商品名与
  `PKG.default(...)` 两种形态，`"demo" / "core"` 拼路径的写法两者都不命中。
* `swap_probe` 现在新增**第三种形态：旧位置形态**（产品层按老路径读逐商品数据），
  按层判死；`self-test` 加了「产品层按旧位置 glob」与「提到 `demo/core` 下的 `.py`（允许）」
  两个用例 —— 前者必须红、后者不许误伤。探针自己不再被自己的用例咬到（拼字符串构造坏样本）。
* 教训与 D1.P4 原有的那条一致：**反例没红先怀疑测试框架**。这次是**重跑离线工具**
  发现读数变了，不是静态扫描发现 —— 所以「换商品/搬数据之后重跑依赖它的离线工具」
  写进了本次的验收动作。

### 4.2 副作用披露：D1.R2 的生成产物被重跑覆盖

本次为核对缺陷重跑了 `route_compare`，它覆盖了 `evals/product-demo/d1-r2/route-a.json`
与 `route-comparison.json`（`d1-r2-route-b.json`、`vlm-ledger.jsonl` 未动，仍是 D1.R2 当次产物）。
因此 **D1.R2 证据 §8 那两行的 sha 与字节数不再对应磁盘文件**。范围与处置：

* D1.R2 的**结论**不变且已被本轮复现（A 在受控底衬上 6/6、在真实场景候选上整条不可用；
  B 漏 2、Unknown 4 条全在 F6；并集 6/6）。D1.R2 文档已加一行指向本节的说明，正文不改。
* 新产物哈希：`route-a.json` = `6324B2EB0862B944`（92944 字节）；
  `route-comparison.json` = `1EDBBBF60EEA92D2`（49134 字节）。
* 这一条也说明**生成产物按字节不可复现**（`ran_at`、`elapsed_s`），与 state 里已登记的
  `contract_report_bytes_not_reproducible` 是同一类问题；本文件不据此声称两次运行逐字节相同。

## 5. 守卫读数（本轮全部重跑，除注明外退出码 0）

| 守卫 | 读数 |
|---|---|
| `demo/core/packages.py self-test --project .` | 全部成立（T1 发现 / T3 换包=换数据 / T4 缺料 / T5 默认包五份齐套 / T6 不含商品名 / T7 指针可解析） |
| `demo/core/run_front_contracts.py` | 17/17 |
| `demo/core/run_back_contracts.py` | 22/22 |
| `demo/core/run_back_contracts.py --mutation-test` | 12/12 |
| `demo/verify/g1_audit.py check --project .` | 七条分项全绿，G1 = pass（与 D1.R4 一致） |
| `demo/verify/g1_audit.py self-test --project .` | 7/7 |
| `demo/verify/swap_probe.py self-test --project .` | 7/7 |
| `demo/verify/swap_probe.py report --project .` | `default_package_control_ok`（退出码 0） |
| `demo/verify/swap_probe.py report --project . --sku bex-02` | `data_missing_no_code_change`（退出码 0） |
| `demo/verify/route_compare.py --project .` + `--remerge` | A 15 张跑完、读数与 D1.R2 一致；报告 49134 字节 |
| `demo/verify/fact_capability.py check / self-test` | 全过 / 10/10 |
| `demo/verify/verifier_registry.py check / self-test` | 全过 / 9/9 |
| `demo/fixture/pack_tools.py verify --project .` | READY |
| `demo/fixture/pack_tools.py self-test --project .` | 5 向全部与预期一致 |
| `demo/fixture/measure_cylinder.py self-test` | 4/4 |
| `demo/contract/contract_tools.py --check / --self-test` | 通过 / 18/18 |
| `tools/check_project_state.py --project .` | 全过 |
| `tools/check_docs.py` | 全过（登记 30 份 = 仓库 30 份） |
| `tools/check_forbidden_rules.py` | 全过 |
| 硬规矩 1（商品名零命中）`rg -n 'aster-01\|bex-02' demo/core demo/verify demo/provider --glob '*.py'` | 零命中（`app/` 尚未建立） |
| 硬规矩 1（导入时焊死默认包零命中）`rg -n '^[A-Za-z_][A-Za-z0-9_]*\s*=\s*[A-Za-z_][A-Za-z0-9_]*\.default\s*\(' demo --glob '*.py'` | 零命中 |
| 探针本体哈希稳定性 | `swap_probe` 扫描的 30 份 `.py` 运行前后哈希无变化 |

## 6. 这次没有证明什么（必须带在结论里的边界）

* **不证明跨品类或真实商品泛化。** `bex-02` 只有事实卡与阈值推导，且它的卡**刻意不合格**
  （`F2diag` 无依据断言）—— PC-02 正确读出**它自己的卡**并拒绝，这证明的是「身份跟着包走」，
  不是「换个商品就能出图」。
* **不证明「补上 7 份数据就能跑通」。** 其中两份是人工裁决记录；本项目不伪造人工签字。
* **换目录对照不是换商品证据。** 它用的是**同一份数据换个目录名**，只能证伪「代码里焊死
  默认商品」这一类；它也不能证明产物可搬移（见下一条）。
* **参考包 manifest 里有两处指向商品的指针**（`fact_card.file`、`threshold_derivation.file`）：
  换商品时必须同步改。本次对照把这两条当作**数据改动**逐条列出，它们是「换了商品也要改什么」
  这份清单的一部分。
* **运行 manifest 里存的是绝对路径**（D1.4 产物格式的既有事实，`candidates_of` 对此有显式兜底）：
  对照因此读的是同一批真实像素。这解释了为什么「读数逐值相同」成立，也说明**这批产物不可搬移**。
* **`facts_version` 把来源路径算进内容身份**：换目录名它就会变。这是刻意的（来源属于身份），
  但读的人要知道 —— 本次把它与 `pack_id`、`plan_version`、`sku` 一起列为「身份派生值，预期就不同」。
* **`S1–S4` 的镜头模板仍是处理层默认值**（`demo/core/front_chain.py` 的 `SHOT_TEMPLATES`）：
  它是「系统提供的默认方案」，换品类时该改的是它。本任务没把它数据化，也不声称已经通用。

## 7. 本次新增的已知不确定（已进 state）

* `run_manifest_stores_absolute_paths_not_portable`：候选 manifest 存绝对路径，产物换目录即失效。
* `shot_templates_are_processing_layer_defaults_not_data`：镜头模板仍是代码里的默认方案，
  换品类要改代码还是改数据，未裁定。
* `d1r2_generated_artifacts_regenerated_bytes_not_comparable`：D1.R2 的两份生成产物已被本轮
  重跑覆盖，D1.R2 证据 §8 的字节哈希不再对应磁盘文件（结论已复现，见 §4.2）。
* `reference_pack_manifest_duplicates_fact_card_pointer`：参考包 manifest 里抄了一份事实卡路径，
  与商品包形成「同一事实两个出处」，靠 `pack_tools.verify` 交叉核对；换商品时两处都要改。
