# 第六次控制面校准（v1.10 → v1.11，2026-09-26）

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY
> 本文只记录这一次校准**为什么做、改了什么、读数如何**。计划正文见
> `docs/product-demo-goal-and-implementation-plan.md` §1.9 与 §4.6；当前状态与下一动作见
> `_working/amz-listing-kit-product-demo/state.md`。本次**零付费调用**。

## 1. 触发：守卫全绿，结论却被改掉

D1.P4 步骤 0 把逐商品数据从 `demo/core/*.<sku>.json` 收进 `demo/fixture/<sku>/`。搬完之后：

* 商品名字面量搜索零命中；
* 产品层没有顶格的 `PKG.default(...)`；
* 前半链 17/17、后半链 22/22、变异 12/12、G1 pass —— **全绿**。

但 `demo/verify/route_compare.py::applicability_max()` 还在按老路径
`(project / "demo" / "core").glob("verifier_plan.*.json")` 找适用性阈值。这份写法
两种既有形态都不命中，后果却是实质性的：

| 读数 | 缺陷存在时 | 修好之后 | D1.R2 记录 |
|---|---|---|---|
| 负样本「适用」 | 否 | 是 | 是 |
| 汇总 A | `detected 0 / missed 6` | `detected 6 / missed 0 / false_alarm 0` | 6 例 6/6 拦下、0 误报 |
| 逐张读数 | 与 D1.R2 表冲突 | 与 D1.R2 表逐条一致 | — |

也就是说：**「阈值缺失」被读成了「前提不成立」**，路径漂移静默改掉了验证结论。
发现方式不是静态扫描，而是**重跑离线工具后逐条核对读数** —— 这条动作因此被写成计划义务。

## 2. 改了什么

| 文件 | 改前 sha256 前 16 | 改后 sha256 前 16 | 改动 |
|---|---|---|---|
| `docs/product-demo-goal-and-implementation-plan.md` | `033D9FAC290A8FA4` | `E36191ED3496A4AD` | 版本 v1.10 → v1.11；新增 §1.9；§4.6 硬规矩 1 增列第三种形态与「搬动后必须重跑离线工具并核对读数」 |
| `demo/contract/processing_contracts.json` | `02C2EE85EE9D7677` | `58C25EA2F521096A` | 只改 `plan_version` → v1.11 |
| `demo/contract/authority_matrix.json` | `B26A7F1DA4C4FE0C` | `9DA0F7680A96FF3B` | 只改 `plan_version` → v1.11 |
| `demo/contract/state_vocabulary.json` | `9F749DCD8B0B99B0` | `2C350E02560BD5B8` | 只改 `plan_version` → v1.11 |

本次**没有**改：§2 Goal 文本、§3 完成合同、§4.1 权威对象、§4.2 状态边界、§4.4 处理合同、
§4.5 不变量。三份机器契约的内容一字未动，只更新冻结版本号。

## 3. 读数

| 守卫 | 结果 |
|---|---|
| `demo/contract/contract_tools.py --check` | 计划识别为 v1.11；文件/契约自身/权威矩阵/状态词汇/与计划漂移 —— 全部「通过」（退出码 0） |
| `demo/contract/contract_tools.py --self-test` | 18/18（含「契约按旧计划版本冻结必须报红」，证明版本号不是摆设） |
| `demo/verify/swap_probe.py self-test --project .` | 7/7（新增「产品层按旧位置 glob 逐商品数据」必须红、「产品层提到 `demo/core` 下的 `.py`」不许误伤） |
| `demo/verify/swap_probe.py report --project .` | 旧位置形态：无；导入时焊死默认包形态：无 |

## 4. 本次没有证明什么

* 这条新形态只能抓**字符串/glob 形式的旧路径**：把路径拼到变量里再传的写法仍可能漏。
  所以它配的是一条**动作义务**（搬动后重跑依赖它的离线工具并核对读数），而不是只靠扫描。
* 校准改变的是判据覆盖面，不改变任何产品能力：`bex-02` 仍缺 7 份数据、生成侧仍只有
  首轮四张候选、G1 的事实分项仍 100% 由人工签字承担。
* 三份契约只更新版本号，不代表它们的内容被重新审过一遍；真正的重审要等到读契约的任务。
