<!-- 拆分件 01/03 · 父文档 evals/product-demo/d1-p4-swap-probe-2026-09-26b.md -->
# D1.P4 完成证据：换商品到底要改什么（2026-09-26 · b）
[返回 d1-p4-swap-probe-2026-09-26b.md](d1-p4-swap-probe-2026-09-26b.md)

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

