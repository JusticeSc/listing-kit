<!-- 拆分件 02/03 · 父文档 evals/product-demo/d1-p4-swap-probe-2026-09-26b.md -->
# 3. 探针读数（原样捕获）
[返回 d1-p4-swap-probe-2026-09-26b.md](d1-p4-swap-probe-2026-09-26b.md)

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

