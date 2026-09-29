# D0.7 P1 第二商品证据（Bex 02 方形随行瓶）

时间：2026-09-25T23:12:39+08:00  
可计费模型调用：**0 次**

## 1. 这一步要回答的问题

P1 的判据是：**第二件结构不同的虚构商品加入后，只新增事实卡和资产；同一命令完成量测、判定和报告。若需要改 `.py` 即失败。**

所以本步只允许新增：一件商品的设计规格与合成图、它的规格卡、它的阈值派生记录，以及一个 fixture 生成器。量测、判定、报告那条链路一行都没动 —— 哈希列在 §4。

## 2. 第二件商品

| 项 | 值 |
|---|---|
| SKU | `demo-box-bex-02`（Bex 02 方形随行瓶） |
| 形状 | 单一直立方体，四角小圆角，截面从上到下等宽；无把手、无侧握、无提带、无吸管 |
| 与 Aster 01 的差异 | 方形等宽截面（不是圆柱）；无筋条、无底圈；板岩蓝 / 石墨黑 / 沙金，角色名与色值全部不同；比例 2.38:1（Aster 是 3.18:1） |
| 资产 | `evals/product-demo/product-2/bex-02/raw.png`，由 `demo/fixture/design_second_product.py` 合成，确定性、无模型调用 |
| 事实卡 | `demo/fixture/bex-02/product.json` |
| 派生记录 | `demo/fixture/bex-02/threshold-derivation.json` |

## 3. 交叉对照：换卡就换判定

同一份量测与判定代码，跑四组配对：

| 配对 | 命令用的卡 | 命令用的图 | 退出码 | 期望 | 结论 |
|---|---|---|---|---|---|
| 正配 · Bex 02 的卡量 Bex 02 的图 | `demo/fixture/bex-02/product.json` | `evals/product-demo/product-2/bex-02/raw.png` | 0 | 0 | 符合 |
| 正配 · Aster 01 的卡量 Aster 01 的图 C | `demo/fixture/aster-01/product.json` | `evals/product-demo/fixture-design/C/raw.png` | 0 | 0 | 符合 |
| 错配 · Aster 01 的卡量 Bex 02 的图 | `demo/fixture/aster-01/product.json` | `evals/product-demo/product-2/bex-02/raw.png` | 4 | 非 0 | 符合 |
| 错配 · Bex 02 的卡量 Aster 01 的图 C | `demo/fixture/bex-02/product.json` | `evals/product-demo/fixture-design/C/raw.png` | 4 | 非 0 | 符合 |

后两行是关键：**把卡对调就都判红**。这说明判定跟着卡走，而不是跟着代码里的某个默认商品走 ——这正是 D0.5 修掉的那个缺陷（旧实现把 CARD 绑在模块级）。

## 4. 量测/判定链路确实没动

| 文件 | 加入第二商品前 sha256（前 16） | 加入后 | 是否相同 |
|---|---|---|---|
| `demo/fixture/measure_cylinder.py` | `1167264360bc3d5f` | `1167264360bc3d5f` | 相同 |
| `demo/fixture/factcard.py` | `e7499c4e165b13eb` | `e7499c4e165b13eb` | 相同 |
| `demo/fixture/product_check.py` | `92fc6e21d1696095` | `92fc6e21d1696095` | 相同 |
| `demo/fixture/mutate_negative.py` | `6c234f7c145c3090` | `6c234f7c145c3090` | 相同 |
| `demo/fixture/negative_suite.py` | `913a75cf190dc82d` | `913a75cf190dc82d` | 相同 |

## 5. 规格 vs 实测（Bex 02，十二条机器判据）

| 事实 | 判据 | 声明/规格 | 实测 | 结论 |
|---|---|---|---|---|
| F1 | `aspect_h_over_w` | 2.38 | 2.381 | pass |
| F2 | `body_upper_share` | 0.7193 | 0.7193 | pass |
| F3 | `body_lower_share` | 0.2807 | 0.2807 | pass |
| F3 | `rib_count` | 0 | 0 | pass |
| F4 | `lid_share` | 0.142 | 0.142 | pass |
| F5 | `trim_span_count` | 1 | 1 | pass |
| F5 | `trim_share` | 0.01 | 0.01 | pass |
| F5 | `trim_top_position` | 0.142 | 0.142 | pass |
| F6 | `bottom_spread_share` | 0.0 | 0.0 | pass |
| F6 | `bottom_ring_present` | 0 | 0 | pass |
| F7 | `body_protrusion` | 0.0 | 0.0 | pass |
| F7 | `extra_area_share` | 0.0 | 0.0 | pass |

**实测与规格逐值相同** —— 因为图就是按这份规格画的。这一点必须写明白，它是本步能做到的边界：它证明「换商品只换卡和资产、代码不动」，不证明协议能容忍真实商品的偏差。真实偏差的证据在 Aster 01 的三张模型候选上（D0.1/D0.5）。

## 6. 这张证据不证明什么

- 不证明任何品类都能走：`metric_profile` 只能写 `cylinder-v1`，它是**协议的键，不是形状的名字**。该协议按横向色带工作，所以方形商品能走；换一个色带结构不同的品类（例如没有清晰横向分带的商品、斜视角度、多个物体同框）就需要新协议 —— 那就是改代码，按 P1 的判据即失败；
- 不构成任何阈值泛化：第二商品的派生的样本数 **n=1**，且这 1 张是合成图；
- 第二商品的图不是模型产出，也不是实物照片；它不进入参考包，也不参与 Phase 1；
- 本轮仍未跑完整回归、未刷新 v2 基线；G0 仍未通过（D0.8 未完成）。

## 7. 复现命令

```bash
python demo/fixture/design_second_product.py --project .
python demo/fixture/product_check.py check --project . --card demo/fixture/bex-02/product.json --image evals/product-demo/product-2/bex-02/raw.png
```

