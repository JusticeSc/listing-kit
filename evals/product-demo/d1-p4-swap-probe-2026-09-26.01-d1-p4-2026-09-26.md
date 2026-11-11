<!-- 拆分件 01/02 · 父文档 evals/product-demo/d1-p4-swap-probe-2026-09-26.md -->
# D1.P4 换商品探针（2026-09-26）
[返回 d1-p4-swap-probe-2026-09-26.md](d1-p4-swap-probe-2026-09-26.md)

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

