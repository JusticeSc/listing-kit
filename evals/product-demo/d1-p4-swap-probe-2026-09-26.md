# D1.P4 换商品探针（2026-09-26）

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY
> 记录时间：2026-09-26。本文是 D1.P4 的中途读数：换商品探针已经建成并跑出结论，
> **但 D1.P4 的验收条件当前不成立** —— 本文如实记录，不把它写成通过。
> 当前状态与下一动作见 `_working/amz-listing-kit-product-demo/state.md`；任务定义见计划 §6.10.2。
> 本次**零付费调用**。

## 1. 这一任务要回答什么

计划 §6.10.2 的验收：用 `bex-02` 数据包跑同一条链；运行前后 `demo/**.py` 的哈希清单逐条不变；
新增文件只有数据与证据。它证明的是**流程与配置解耦**，不证明跨品类泛化。

§4.6 硬规矩 1 只写了一句「商品身份只能来自商品数据包」，可证伪形式是一行 SKU 搜索。但那次校准
之后实测发现：**SKU 字面量已经零命中，不等于「换商品不用改代码」**。真正会挡住换商品的是另一种
形态 —— 模块常量在**导入时**就把默认包焊死：

```python
CARD_SUB = PKG.default(ROOT).rel("card")          # demo/core/front_chain.py:42
_PKG = PKG.default(ROOT)                          # demo/core/back_chain.py:50
DEFAULT_PROFILE = PKG.default(ROOT).path(...)     # demo/core/prompt.py:33
CARD_PATH = PKG.default(PROJECT).path("card")     # demo/provider/run_first_round.py:64
```

全文搜 `aster-01` 搜不到它们，任何非默认包都进不来。所以探针必须同时做三件事：逐包齐套、
绑定扫描（按层归类）、**动态尝试**（跑起来看它到底读了哪个包）。

## 2. 探针读数（原样捕获）

默认包（`--project .`，退出码 0）：

```text
==========================================================================
D1.P4 换商品探针（离线 · 零付费）
==========================================================================
  商品包：aster-01、bex-02    目标包：aster-01
  扫描的 .py：30 份（运行前后哈希变化：无）

  ① 目标包齐套
     存在：card、thresholds、prompt_profile、verifier_plan、human_facts、human_visual、fact_capability
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
     [默认包形态（导入时焊死）] demo/core/back_chain.py:50（产品层→不许） _PKG = PKG.default(ROOT)
     [默认包形态（导入时焊死）] demo/core/front_chain.py:42（产品层→不许） CARD_SUB = PKG.default(ROOT).rel("card")
     [默认包形态（导入时焊死）] demo/core/prompt.py:33（产品层→不许） DEFAULT_PROFILE = PKG.default(ROOT).path("prompt_profile")
     [默认包形态（导入时焊死）] demo/provider/run_first_round.py:64（产品层→不许） CARD_PATH = PKG.default(PROJECT).path("card")

  ③ 动态尝试
     [OK  ] resolve：包解析器按目录解析，aster-01
     [OK  ] PC-02：accepted；读到的包 = demo/fixture/aster-01/product.json（就是目标包）
     [BLOCK] PC-09：候选来源不在商品包里

  结论：default_package_only
     目标包就是默认包 ——「换商品要改什么」这个问题的答案只在非默认包上才成立；
     默认包读到自己恒真，不算证据。请用 --sku <另一个包> 取读数。

```

第二个包（`--sku bex-02`，退出码 1）：

```text
==========================================================================
D1.P4 换商品探针（离线 · 零付费）
==========================================================================
  商品包：aster-01、bex-02    目标包：bex-02
  扫描的 .py：30 份（运行前后哈希变化：无）

  ① 目标包齐套
     存在：card、thresholds
     缺料：prompt_profile、verifier_plan、human_facts、human_visual、fact_capability

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
     [默认包形态（导入时焊死）] demo/core/back_chain.py:50（产品层→不许） _PKG = PKG.default(ROOT)
     [默认包形态（导入时焊死）] demo/core/front_chain.py:42（产品层→不许） CARD_SUB = PKG.default(ROOT).rel("card")
     [默认包形态（导入时焊死）] demo/core/prompt.py:33（产品层→不许） DEFAULT_PROFILE = PKG.default(ROOT).path("prompt_profile")
     [默认包形态（导入时焊死）] demo/provider/run_first_round.py:64（产品层→不许） CARD_PATH = PKG.default(PROJECT).path("card")

  ③ 动态尝试
     [OK  ] resolve：包解析器按目录解析，bex-02
     [OK  ] PC-02：accepted；读到的包 = demo/fixture/aster-01/product.json（不是目标包！）
     [BLOCK] PC-09：缺料 verifier_plan、human_facts

  结论：code_change_required
     换这个商品**必须改代码**，清单：
       · 数据（加文件即可）：prompt_profile、verifier_plan、human_facts、human_visual、fact_capability
       · 代码：PC-02 入口读的是 demo/fixture/aster-01/product.json，不是目标包 demo/fixture/bex-02/product.json
       · 代码：模块常量在导入时焊死默认包 —— demo/core/back_chain.py:50
       · 代码：模块常量在导入时焊死默认包 —— demo/core/front_chain.py:42
       · 代码：模块常量在导入时焊死默认包 —— demo/core/prompt.py:33
       · 代码：模块常量在导入时焊死默认包 —— demo/provider/run_first_round.py:64
       · 代码：候选来源不随商品包走：写死在 demo/core/back_chain.py::FIRST_ROUND_SUB（evals/product-demo/first-round/manifest.json）

```

探针自检（退出码 0）：

```text
换商品探针自检（四种改坏必须各按层判对）
  [OK  ] 产品层写商品目录名：抓到=True 归类=product 硬违规=True（期望 抓到=True 硬违规=True）
  [OK  ] 夹具层写商品目录名：抓到=True 归类=fixture 硬违规=False（期望 抓到=True 硬违规=False）
  [OK  ] 产品层焊死默认包（候选，非硬违规）：抓到=True 归类=product 硬违规=False（期望 抓到=True 硬违规=False）
  [OK  ] 缩进的默认值（允许）：抓到=False 归类=- 硬违规=False（期望 抓到=False 硬违规=False）

自检：4/4 种改坏都被按层判对

```

## 3. 结论

**`bex-02` 跑不了同一条链，而且挡住它的不只是缺数据。** 两类原因必须分开陈述：

| 类别 | 具体 | 处置 |
|---|---|---|
| 数据（加文件即可） | `bex-02` 缺 5 份约定文件：`prompt_profile`、`verifier_plan`、`human_facts`、`human_visual`、`fact_capability` | 属于「换商品只加这一层」，计划 §4.6 已允许；本任务不伪造第二商品的人工裁决数据 |
| 代码（必须改） | ① 实测：`FC.facts(project)` 对 `bex-02` 读到的仍是 `demo/fixture/aster-01/product.json`；② 四个产品层模块常量在导入时焊死默认包；③ 候选来源写死在 `demo/core/back_chain.py::FIRST_ROUND_SUB` | 属于 D1.P4 处理段的原话「入口接受商品 id 或包路径，模块常量降级为默认值，不再是唯一入口」 |

夹具与证据层（`demo/fixture/*.py`、`tools/`、`evals/`）里的商品目录名共有 13 处，按 §4.6
**不判死** —— 它们本来就是那个商品的夹具；探针只把它们记入清单。

**因此 D1.P4 现在是不通过状态**：`bex-02` 无法在不改 `.py` 的前提下跑同一条链。
按计划的失败路径如实记录，不把「新增一份数据」说成「换商品不用改代码」。

## 4. 探针自身的三次纠正（都是实测抓出来的）

1. **漏检下划线常量**：第一版的正则只抓 `[A-Z][A-Z0-9_]* =`，于是 `_PKG = PKG.default(ROOT)`
   整个漏掉。补进正则后才看见 `demo/core/back_chain.py:50`。
2. **把「默认值」误判成违规**：第二版的顶格正则也把函数体里缩进的
   `default_pkg = PKG.default(root)` 算成产品层违规 —— 连探针自己都被咬了一次。但计划 §4.6
   的原文是「**模块常量**只能作默认值」，缩进里的默认值正是允许的用法。最终规则：只抓**顶格**
   的模块常量，且它是否真的挡住换商品由动态读数裁决，静态扫描只负责列名单。
3. **把缺料误标成代码问题**：第一版的结论把 `PC-09` 的「缺料」写进了「代码」一栏。
   `bex-02` 缺 `verifier_plan`/`human_facts` 是数据问题，候选来源写死才是代码问题 —— 两类分开
   之后，结论清单才对应得上处置动作。

## 5. 探针自检有牙

四种改坏必须各按层判对：产品层写商品目录名（硬违规）、夹具层写商品目录名（记清单、不违规）、
**产品层焊死默认包（抓到、但只算候选，不算硬违规）**、缩进里的默认值（允许，不该抓到）。
四种都按期望判对，见第 2 节输出。

## 6. 冻结产物与哈希

探针扫描 `demo/**` 与 `app/` 下 30 份 `.py`，运行前后**零变化**（报告内自带断言）。
探针自身哈希（SHA256 前 16）：`7dda9a6d8a15126c`（14642 字节）。

## 7. 下一步（已进 state 的唯一下一动作）

把四个产品层入口改成**接受商品 id 或包路径**、模块常量退化为默认值；候选来源从
`demo/core/back_chain.py::FIRST_ROUND_SUB` 改为随包/随调用方传入。改完重跑：

- `demo/verify/swap_probe.py report --project . --sku bex-02`（目标是「数据类」清单不变、
  「代码类」清单清空）
- 三个既有守卫（前半链 17/17、后半链 22/22、变异 12/12）与 D1.R4 的 G1 审计必须仍为绿

注意：**第二商品的 5 份数据不伪造**。探针要证明的是「换商品不必改代码」，不是「再编一个商品」——
所以改造完成后，`bex-02` 的读数应当是「只缺数据」，而不是「全绿」。

## 8. 这次没有证明什么

- 没有证明跨品类泛化：`bex-02` 是一份只有事实卡与阈值推导的边界样本，不是可生成的完整商品包；
- 没有证明换商品之后量测/事实责任链仍然成立：`fact_capability`、`verifier_plan` 都还没有第二份；
- 没有产生任何付费调用。
