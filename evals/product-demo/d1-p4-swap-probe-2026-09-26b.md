# D1.P4 完成证据：换商品到底要改什么（2026-09-26 · b）

> EVIDENCE-SNAPSHOT: current · 时点产物
> 本文是 D1.P4 的**完成读数**。前一版 `d1-p4-swap-probe-2026-09-26.md` 是「结论不成立」
> 的中途读数，保留不动 —— 它记录的是当时真实的红。
> 目标/任务定义见 `docs/product-demo-goal-and-implementation-plan.md` §6.10.2；
> 当前状态与下一动作见 `_working/amz-listing-kit-product-demo/state.md`。
> 本次**零付费调用**：首轮预算仍 4/8，本轮生图调用 0 次、视觉模型调用 0 次。

## 1. 一句话结论

**换商品不必改 `.py`。** 商品身份、参考包、候选来源、两份人工记录现在全部由商品包
（`demo/fixture/<sku>/`）声明，产品层入口一律在**调用时**解析；换到 `bex-02` 时剩下的缺口
**只有数据**，代码侧清单为空。

三条读数（原样捕获见 §3）：

| 读数 | 结论 | 说明 |
|---|---|---|
| 默认包 `aster-01` | `default_package_control_ok` | 同一份数据只换包目录名，链上读数除身份派生值外逐值相同 |
| 第二个包 `bex-02` | `data_missing_no_code_change` | 代码侧清单为空；缺 7 份约定文件才跑得动 |
| 探针自检 | 7/7 | 三种「焊进代码」形态各按层判对，两种允许写法不误伤 |

## 2. 改了什么

### 2.1 数据侧：新增 2 份，旧数据一个字节没动

| 文件 | 作用 | sha256 前 16 | 字节 |
|---|---|---|---|
| `demo/fixture/aster-01/reference_pack.json` | 声明这个商品用哪个冻结参考包、第一轮用哪张视图 | `B9C5CA2B9E496099` | 614 |
| `demo/fixture/aster-01/runs.json` | 声明候选/运行产物落在哪（只声明位置，不复制内容） | `D02CD7637BAE2438` | 485 |

为什么要新增这两份：原来的「参考包位置」和「候选来源位置」是**产品层代码里的常量**。
换商品时即使事实卡换了，`intake` 仍会去读默认商品的参考包、`PC-09` 仍会去读默认商品的
候选目录 —— 那同样是「换商品必须改代码」，只是比写商品名更隐蔽（全文搜 SKU 字面量搜不到它）。

### 2.2 代码侧：8 份（改前 → 改后）

| 文件 | 改前 sha256 前 16 | 改后 sha256 前 16 | 字节 |
|---|---|---|---|
| `demo/core/packages.py` | `184D46BF57BD4E7D` | `37899272537DE825` | 8498 → 12452 |
| `demo/core/front_chain.py` | `5573A30607D81C1A` | `6BD10F3088F94F8C` | 22346 → 23948 |
| `demo/core/back_chain.py` | `BF63503BCEC9E670` | `77BCA72F7101B838` | 41466 → 42277 |
| `demo/core/prompt.py` | `34FEDEF4B95238C6` | `EE72FFE129A0619D` | 10053 → 10147 |
| `demo/core/run_front_contracts.py` | `8AA64F1DFDADD782` | `3325682AB0D72457` | 25846 → 26054 |
| `demo/verify/g1_audit.py` | `5D24269AF3BE83B4` | `83C6AB4BA3969257` | 22322 → 22591 |
| `demo/verify/route_compare.py` | `3CF40FB8BD0937C7` | `174A3670ACD45ACA` | 29896 → 30448 |
| `demo/verify/swap_probe.py` | `7DDA9A6D8A15126C` | `EC1E807E16FCBB8E` | 14642 → 32076 |
| `demo/fixture/pack_tools.py` | `AB0D336E615A9B8E` | `CB05A3D3758A7849` | 18112 → 18969 |
| `demo/provider/run_first_round.py` | `E8A19138D60BF27E` | `F1E526E8A56B3D79` | 16499 → 17889 |

（`demo/verify/route_compare.py` 的「改前」取 D1.R2 证据 §8 记录的值；其余改前值取自本轮
工作区外快照 `_stage-amz-control/d1p4-20260926-1610/`。`demo/core/run_back_contracts.py`
本轮**未改**，sha 仍是 `D95B9B4BD4F3047C`。）

### 2.3 逐条落点：模块常量降级为「调用时解析」

| 位置 | 原来 | 现在 |
|---|---|---|
| `demo/core/front_chain.py` | `CARD_SUB = PKG.default(ROOT).rel("card")`、`MANIFEST_SUB = pack_tools.MANIFEST_SUB`（导入时焊死） | 常量全删；`intake(project, sku)`、`facts(project, refpack=None, *, sku=None)`、`style_spec(..., project=, sku=)`、`compile_prompt(..., project=, sku=)` 都在调用时解析 |
| `demo/core/back_chain.py` | `_PKG = PKG.default(ROOT)` 加三个 rel 常量；`FIRST_ROUND_SUB` 常量 | 常量全删；`candidates_of(project, sku)` 读商品包声明的候选目录；`fact_routing(..., human_source=)`、`visual_review(..., source=)`、`golden_candidates(project, sku)` 增加可选来源参数 |
| `demo/core/prompt.py` | `DEFAULT_PROFILE = PKG.default(ROOT).path("prompt_profile")` | `load_profile(path=None, *, project=ROOT, sku=None)`，调用时解析 |
| `demo/provider/run_first_round.py` | `CARD_PATH`、`_PROFILE`、`NEGATIVE_PROMPT`、`PRIMARY_VIEW_ID`、`MANIFEST_PATH`、`EXP_DIR/STORE/LEDGER` 六个模块常量 | `run_context(sku)` 在调用时把「哪个商品、哪个参考包、产物落哪」解析出来；新增 `--sku`；`second_view` 也来自声明 |
| `demo/core/run_front_contracts.py` | `CARD_SUB = FC.CARD_SUB`；D1.4 记录位置写死 | `PKG.path_of(project, "card")`；`record_path()` 走 `PKG.runs_of` |
| `demo/verify/g1_audit.py` | `B.CARD_SUB` 等 5 个模块常量 | 全部走 `pkg.path(...)` / `runs[...]`；并把 `human_source` 显式传给 PC-09 |
| `demo/fixture/pack_tools.py` | `verify(root)` 只认夹具层默认包；`_sandbox_copy` 只复制一张事实卡 | `verify(root, pack_sub=...)` 由调用方给包；沙箱复制**整个商品数据包** —— 沙箱要是一个能被包解析器解析的迷你项目 |
| `demo/verify/route_compare.py` | 按旧位置 `demo/core/verifier_plan.*.json` glob 适用性阈值、自己拼 `demo/fixture/<sku>/product.json`、写死候选 manifest 路径 | 全部走包解析器（详见 §4：这是一个真缺陷，不是顺手的整理） |

`packages.py` 新增四个**调用时**取路径的入口：`path_of` / `sub_of` / `refpack_of` / `runs_of`；
`COMPLETE_KEYS` 从三份扩到五份（事实卡、提示词 profile、验证路由计划、参考包声明、候选来源声明），
并加了自检 T7（默认包的参考包与候选来源必须能解析）。

## 3. 探针读数（原样捕获）

### 3.1 默认包 `aster-01`（退出码 0）

```text
  ① 目标包齐套
     存在：card、thresholds、prompt_profile、verifier_plan、human_facts、human_visual、fact_capability、refpack、runs
     缺料：无

  ② 绑定扫描（把具体商品焊进代码的地方）
     [目录名形态] demo/fixture/design_second_product.py:288（夹具/证据层→记入清单） "fact_card": "demo/fixture/bex-02/product.json",
     [目录名形态] demo/fixture/design_second_product.py:306（夹具/证据层→记入清单） ap.add_argument("--card", default="demo/fixture/bex-02/product.json")
     [目录名形态] demo/fixture/design_second_product.py:307（夹具/证据层→记入清单） ap.add_argument("--derivation", default="demo/fixture/bex-02/threshold-derivation.json")
     [目录名形态] demo/fixture/measure_f1_f8.py:14（夹具/证据层→记入清单） （`demo/fixture/aster-01/product.json`）。v2 里写死的
     [目录名形态] demo/fixture/mutate_negative.py:37（夹具/证据层→记入清单） DEFAULT_CARD = "demo/fixture/aster-01/product.json"
     [目录名形态] demo/fixture/negative_suite.py:36（夹具/证据层→记入清单） DEFAULT_CARD = "demo/fixture/aster-01/product.json"
     [目录名形态] demo/fixture/pack_tools.py:30（夹具/证据层→记入清单） CARD_SUB = "demo/fixture/aster-01/product.json"
     [目录名形态] demo/fixture/pack_tools.py:31（夹具/证据层→记入清单） DERIV_SUB = "demo/fixture/aster-01/threshold-derivation.json"
     [目录名形态] demo/fixture/product_check.py:4（夹具/证据层→记入清单） python demo/fixture/product_check.py check --card demo/fixture/aster-01/product.json \
     [目录名形态] demo/fixture/product_check.py:31（夹具/证据层→记入清单） DEFAULT_CARD = "demo/fixture/aster-01/product.json"
     [目录名形态] demo/fixture/scene_scope_control.py:38（夹具/证据层→记入清单） CARD_PATH = PROJECT / "demo/fixture/aster-01/product.json"
     [默认包形态（导入时焊死）] 无
     [旧位置形态（按老路径读逐商品数据）] 无

  ③ 动态尝试
     [OK  ] resolve：包解析器按目录解析 aster-01
     [OK  ] PC-01：accepted；读到的包 = evals/product-demo/fixture-design/pack（就是目标包）
     [OK  ] PC-02：accepted；读到的包 = demo/fixture/aster-01/product.json（就是目标包）
              · 8 条事实；7 条需要人工侧确认，4 个字段保持 Unknown
     [OK  ] PC-09：per-candidate；读到的包 = evals/product-demo/first-round（就是目标包）
     [OK  ] PC-10：accepted；读到的包 = demo/fixture/aster-01/human_visual_review.json（就是目标包）

  ④ 换目录对照（同一份数据，只换包目录名）
     对照包名：control-z9-swap（临时项目，跑完即删）
     数据改动（都是数据，.py 零改动）：
       · 包目录 aster-01 → control-z9-swap
       · 参考包 manifest 的 fact_card.file：demo/fixture/aster-01/product.json → demo/fixture/control-z9-swap/product.json
       · 参考包 manifest 的 threshold_derivation.file：demo/fixture/aster-01/threshold-derivation.json → demo/fixture/control-z9-swap/threshold-derivation.json
     [OK  ] 除身份派生值（sku、intake/pack_id、facts/facts_version、plan/plan_version）外逐值相同：candidates、compose、fact_routing、facts、intake、plan、prompt、select、visual
     [变  ] 身份派生值，预期就不同：facts/facts_version：基线 "a7f87ba39df2efac7e697cf0264ce86781f4ca4f7eb6e44b5d17b019a6c48115" ≠ 对照 "33ec42f5f9cacd71003c23e7a72750a581eac75c1ef62ac89f797ea58390046d"
     [变  ] 身份派生值，预期就不同：intake/pack_id：基线 "529c1c3b98420b66e1db947ac3445406cb05e4c1a9b840df45ddf5b645008502" ≠ 对照 "19f8d7cd94df8f5be9affad775fbf59db93c4871ae167625fea803593e5a380d"
     [变  ] 身份派生值，预期就不同：plan/plan_version：基线 "605e06b29cf00277db14df022bc82fc7668f8ea930d6139e7561a1e510efeb69" ≠ 对照 "0faed228ef2465b4948224f72d885d2f8b753dab2ca73c9d690e236645c09462"
     [变  ] 身份派生值，预期就不同：sku：基线 "aster-01" ≠ 对照 "control-z9-swap"
     [OK  ] 拿掉目标包后报错（RuntimeError），没有静默回落到别的包
           PC-01 未通过（business_reject）：没有这个商品包：'control-z9-swap'；现有 aster-01、bex-02

  结论：default_package_control_ok
```

### 3.2 第二个包 `bex-02`（退出码 0）

```text
  ① 目标包齐套
     存在：card、thresholds
     缺料：fact_capability、human_facts、human_visual、prompt_profile、refpack、runs、verifier_plan

  ② 绑定扫描（把具体商品焊进代码的地方）
     （11 条目录名形态全部来自 demo/fixture/ 夹具层 → 记入清单、不判死，逐条同上）
     [默认包形态（导入时焊死）] 无
     [旧位置形态（按老路径读逐商品数据）] 无

  ③ 动态尝试
     [OK  ] resolve：包解析器按目录解析 bex-02
     [BLOCK] PC-01：缺料 refpack
     [OK  ] PC-02：business_reject；读到的包 = demo/fixture/bex-02/product.json（就是目标包）
              · 事实层不通过：F2diag: 既没有 machine_checks 也没有 human_note —— 这是一条无依据断言
     [BLOCK] PC-09：缺料 runs、verifier_plan、human_facts
     [BLOCK] PC-10：缺料 runs、human_visual

  ④ 换目录对照（同一份数据，只换包目录名）
     [SKIP] 目标包不是默认包 —— 对照用默认包的数据，只对默认包成立

  结论：data_missing_no_code_change
     换这个商品不必改 .py —— 代码侧清单为空。
     但仍缺数据，补齐才有读数：
       · PC-01 需要 refpack
       · PC-09 需要 runs、verifier_plan、human_facts
       · PC-10 需要 runs、human_visual
```

两点必须一起读：

* **PC-02 读到的是 `bex-02` 自己的卡**（`reads_target=True`），不是默认商品的卡 —— 这是这一步
  要证的核心。它 `business_reject` 是因为**这张卡自己不合格**（`F2diag` 是一条没有
  `machine_checks` 也没有 `human_note` 的无依据断言，见 D0.7 的边界样本设计），属于数据，
  不属于代码。
* 缺的 7 份里，`human_facts` / `human_visual` 是**人工裁决**。按 §4.5「不许自证」，
  本项目不会为了把这行读数刷绿而编一份 `bex-02` 的人工签字。

### 3.3 探针自检（退出码 0）

```text
换商品探针自检（7 种改坏必须各按层判对）
  [OK  ] 产品层写商品目录名：抓到=True 归类=product 硬违规=True（期望 抓到=True 硬违规=True）
  [OK  ] 夹具层写商品目录名：抓到=True 归类=fixture 硬违规=False（期望 抓到=True 硬违规=False）
  [OK  ] 产品层焊死默认包（候选，非硬违规）：抓到=True 归类=product 硬违规=False（期望 抓到=True 硬违规=False）
  [OK  ] 夹具层焊死默认包（候选，非硬违规）：抓到=True 归类=fixture 硬违规=False（期望 抓到=True 硬违规=False）
  [OK  ] 缩进的默认值（允许）：抓到=False 归类=- 硬违规=False（期望 抓到=False 硬违规=False）
  [OK  ] 产品层按旧位置 glob 逐商品数据：抓到=True 归类=product 硬违规=True（期望 抓到=True 硬违规=True）
  [OK  ] 产品层提到 demo/core 下的 .py（允许）：抓到=False 归类=- 硬违规=False（期望 抓到=False 硬违规=False）

自检：7/7 种改坏都被按层判对
```

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
