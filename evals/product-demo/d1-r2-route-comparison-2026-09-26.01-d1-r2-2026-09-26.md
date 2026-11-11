<!-- 拆分件 01/02 · 父文档 evals/product-demo/d1-r2-route-comparison-2026-09-26.md -->
# D1.R2 三种验证路线离线对照（2026-09-26）
[返回 d1-r2-route-comparison-2026-09-26.md](d1-r2-route-comparison-2026-09-26.md)

# D1.R2 三种验证路线离线对照（2026-09-26）

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY
> 记录时间：2026-09-26。本文只记录这次怎么对照、读到什么、哪条路线在哪类事实上不可用。
> 当前状态与下一动作见 `_working/amz-listing-kit-product-demo/state.md`；任务定义见计划 §6.10.4。
>
> **2026-09-26 后续说明（D1.P4 追加，正文不改）**：§8 记录的 `route-a.json` 与
> `route-comparison.json` 已被 D1.P4 重跑覆盖 —— 当时发现 `route_compare.py` 还在按
> 收拢前的旧位置 `demo/core/verifier_plan.*.json` 找适用性阈值，导致负样本的「适用」被读成否、
> 汇总 A 从 `detected 6` 掉到 `detected 0`。缺陷已修，本文的逐图读数与结论**已被复现**；
> 新的产物哈希见 `evals/product-demo/d1-p4-swap-probe-2026-09-26b.md` §4。本文其余内容仍是当次快照。

## 1. 这次要回答什么

计划 §6.10.4 把 D1.R2 定为「同一批输入、同一份事实定义下，比较 A 分割后量测 / B 参考图条件
视觉判断 / C 混合」，并且**结论必须写明哪条路线在哪类事实上不可用**。可检验的三条：

1. 同一批输入、同一份事实定义，逐图记检出 / 漏报 / 误报 / Unknown；
2. 三种「不可用」的原因分开陈述：前提不成立、判据覆盖不到、模型判不了；
3. 换商品要改代码还是只换数据，要有读数支撑。

对照集 **15 张**：4 张真实场景候选（人工判 pass）+ 3 张未变异对照 + 7 个既有负样本
+ 1 个第二商品边界样本。预期取自 `negative-cases/expectations.json`（事先声明）与 D1.5 人工裁决。

## 2. 先修的两处已证缺陷

试点（`--limit 2`）跑出来的不是结论，是两个真缺陷。两条都不是「调参」问题，先修再对照。

### 2.1 量测器的尺寸前提没声明

`measure_cylinder.measure()` 用 4×4 降采样块找最大连通域（网格是 `h//4 × w//4`），
再 `np.kron(...)[:h, :w]` 展开回原图。**h 或 w 不是 4 的倍数时 kron 的结果比原图小**，
后面 `comp_full[y0:y1+1, x0:x1+1]` 与同范围裁出的 `subarr` 形状不一致，直接广播失败：

```text
ValueError: operands could not be broadcast together with shapes (1173,370) (1172,368)
```

棚拍夹具恰好全是 1344×1344，所以这条缺陷被遮了整整两轮；裁剪图一进来就崩。

**修法**：新增 `expand_blocks(comp_small, h, w)`，只对齐形状、不改语义（网格覆盖到的区域
逐块回填，尾部不足一块的行列保持 False），并在 `inside` 使用前加形状断言 —— 形状不一致必须
报错，不能带着错形状继续算。同一段式子还出现在 `mutate_negative.py`、`scene_scope_control.py`
里（前者会让外接框最多少 3 像素），两处一并改用同一个函数；`measure_f1_f8.py` 是已标
`[SUPERSEDED]` 的历史证据，不动。

**红→绿**：先只加自检与「旧实现」，自检当场红：

```text
  [FAIL] T1 形状契约：6 组尺寸（含非 4 倍数）输出恒为原图尺寸
  [FAIL] T3 端到端：1341x1343 量测失败 ValueError: operands could not be broadcast
         together with shapes (1343,1341) (1340,1340)
```

改成对齐实现后：

```text
  [OK  ] T1 形状契约：6 组尺寸（含非 4 倍数）输出恒为原图尺寸
  [OK  ] T2 语义不变：4 倍数输入与旧实现逐值相同，且旧实现确在 1341x1343 上形状失真
  [OK  ] T3 端到端：1344x1344 overall=pass -> 1341x1343 overall=pass，逐指标最大漂移 0.0000
  [OK  ] T4 变异：换回旧实现后非 4 倍数裁剪图如期报错
```

**读数不变的证据**（不是「应该没影响」，是逐值比对）：对全部 11 张冻结图
（3 对照 + 夹具正面 + 7 负样本）修复前后各跑一次量测，输出 JSON **逐字节相同**：

```text
before sha256 ee7d7e738acc2102  8594 B
after  sha256 ee7d7e738acc2102  8594 B      BYTE-IDENTICAL: True
```

### 2.2 路线 A 的适用性判据原本会自证

试点第一版把主体抠出来、贴到中性灰底衬上，**再在画布上**探「底衬是否中性」，读数
0.5772 / 0.5666 「通过」——可它量的是我们自己刚铺的那层灰。这不是判据不严，是判据错位。

**改法**：适用性只在**原图**上判（阈值从 verifier plan 的 `applies_when.max_share` 读，不另写
数字）；画布上的探针保留，但改名 `canvas_probe` 并显式标注 `self_referential_canvas_hygiene_only`，
不再参与适用性；原图前提不成立时，画布读数进 `isolated_facts` 作反事实记录，`facts` 一律 Unknown。
同一条不变量已写进计划 §4.5（「不许自证」）。

**这次改动让「自证」变成可读的数字**：同一张受控底衬图，原图探针 **0.0**，画布探针
**0.19–0.30**（探针的 18% 带比画布 10% 留边更宽，量到的是主体边缘）。同一个探针、同一张源图，
只因为中间多了一层我们自己铺的灰，读数就差一个数量级 —— 这就是它不能当证据的原因。

