# 控制面校准 #3（2026-09-26）：商品数据收拢与 Phase 3–5 实现规格

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY  
> 记录时间：2026-09-26T11:36:39+08:00。本文只记录这次校准读了什么、跑出了什么、据此改了什么。  
> 当前状态、下一动作和未来计划分别以 `_working/amz-listing-kit-product-demo/state.md`
> 与 `docs/product-demo-goal-and-implementation-plan.md` 为准。

## 1. 这次要回答什么

上一轮（`control-plane-recalibration-2026-09-26.md`，校准 #2）立了两条：目标/任务只有计划一份，
以及「换商品只加商品包、商品身份不出现在 `demo/core/`」。本轮问两件上一轮**没有**验证的事：

1. 那条「逐商品数据只住商品包」的规矩，**在已有实现里有没有被自己违反**；
2. Phase 3–5 有没有像 §6.10/§6.11 那样可执行的实现规格（输入/处理/输出/验收）。

判据不用形容词：跑守卫、`rg` 实测、与工作区外快照逐字节比对。
可计费模型调用：**0 次**；没有改动任何候选像素、任何冻结证据、任何 `demo/` 代码。

## 2. 新鲜读数（全部本次运行）

| 检查 | 命令 | 结果 |
|---|---|---|
| 项目状态守卫 | `tools/check_project_state.py --project .` | rc=0（J0–J9 全过；3 份工作记录） |
| 状态反向探针 | `evals/probes/project_state.py` | 17/17 与预期一致，state 逐字节恢复 |
| 文档登记与身份 | `tools/check_docs.py` | rc=0（登记 30 份 = 仓库 30 份；真跑 10 条命令，跳过 31 条） |
| 处理合同守卫 | `demo/contract/contract_tools.py --check` | 计划升 v1.8 后先 **rc=1**，重审后 rc=0（见 §4） |
| 合同自检 | `contract_tools.py --self-test` | 18/18 项被正确抓到 |
| 前半链契约 | `demo/core/run_front_contracts.py` | 17/17 符合预期（零付费） |
| 后半链契约 | `demo/core/run_back_contracts.py` | 18/18 符合预期（零付费） |
| 后半链变异 | `run_back_contracts.py --mutation-test` | 8/8 项被反例抓住 |
| 参考包一致性 | `demo/fixture/pack_tools.py verify --project .` | READY |
| Goal 生命周期 | 系统工具直读 | `active`；objective 与计划 §2 引用块逐段一致 |

## 3. 发现的三处漂移（同一根因）

根因不是设计错了，是上一轮刚立的规矩**还没有对应的机器判据**：规矩写对了，数据没搬家。

| # | 漂移 | 证据（本次实测） |
|---|---|---|
| D1 | 四份逐商品数据住在 `demo/core/`，文件名带 SKU 后缀 | `demo/core/back_chain.py:46-48` 写死 `demo/core/verifier_plan.aster-01.json`、`human_fact_review.aster-01.json`、`human_visual_review.aster-01.json`；`demo/core/prompt.py:30` 写死 `demo/core/prompt_profile.aster-01.json`。而计划 §4.6 要求逐商品数据只住 `demo/fixture/<sku>/`，§6.10.1 拟定的形态是 `demo/fixture/<sku>/verifier_plan.json` |
| D2 | `demo/provider/`、夹具工具层与 Phase 2 的界面落点都不在 §4.6 层表里 | §4.6 只列合同身份/处理链/商品数据包/可替换验证器/冻结参考包/本地产品/证据七层；`demo/provider/`（`dashscope_i2i.py`、`doctor.py`、`run_first_round.py`）与 `demo/fixture/*.py` 无归属；`app/` 原写「Phase 3 起」，但 D2.R1 的离线 tracer 没有落点 |
| D3 | D1.R1 的原输出落点在 `demo/core/`，会把 D1 复制一遍 | 计划 v1.7 §6.10.3 原文只写「`evals/product-demo/d1-r1-fact-capability-matrix.md` + 机器可读矩阵」，机器可读矩阵的实际落点当时拟定在 `demo/core/` |

### 3.1 附带发现：契约报告不是稳定哈希对象

本轮重跑 `run_front_contracts.py` 与 `run_back_contracts.py` 后，`evals/product-demo/d1-p3/back-contracts.json`
的字节哈希从 d1-p3 证据 §6 登记的 `7d680da992a172a9…` 变成 `7b91b3df996a7534…`。原因不在被测对象：
报告里含运行期随机临时目录（实测 `AppData\Local\Temp\back-golden-6o_kt5xo`），**同一条命令跑两次
不会产生同样字节**。逻辑读数没有变：前半链 17/17、后半链 18/18、变异 8/8。

这不是产品缺陷，是**证据登记方式**的问题：把可重跑报告当稳定哈希对象登记，第一次重跑就失配。
处置方向（本轮不改 `demo/` 代码，只登记发现）：报告里的临时路径归一化，或人读证据只登记逻辑读数
与被测对象哈希（候选、请求体），不登记报告自身哈希。已登记为 state 的 unknown：
`contract_report_bytes_not_reproducible`。

## 4. 处置：计划 v1.7 → v1.8

四处修订，分工与理由见计划新增的 §1.6：

1. §4.6 补 `demo/provider/` 与夹具工具两层，把 `app/` 明确成「Phase 2 起先做只读 tracer」，
   并把硬规矩从两条扩成三条：新增「逐商品数据只住 `demo/fixture/<sku>/`、文件名不带 SKU」，
   以及可证伪判据 `rg -n 'aster-01|bex-02' demo/core demo/verify app demo/provider --glob '*.py'` 零命中。
2. §6.10.2（D1.P4）新增**步骤 0**：把四份 JSON 搬进商品包并去掉 SKU 后缀；搬完必须重跑
   `run_front_contracts.py`、`run_back_contracts.py`（含 `--mutation-test`）与合同 `--self-test`，
   读数与搬动前一致。
3. §6.10.3（D1.R1）输出落点改为商品包 `demo/fixture/aster-01/fact_capability.json` +
   与 SKU 无关的校验器 `demo/verify/fact_capability.py` + 人读报告。
4. 新增 §6.12 Phase 3–5 实现规格（运行时形状、存储目录、状态库与重启恢复、计划与提示词编译、
   fake provider 恢复演练、真实执行与事实路由接入、审核/选择/返工、界面/合成/复检/导出/备份），
   每行都是输入/处理/输出/验收四列。

**合同重审（先红后绿）**：计划版本一升，`contract_tools --check` 立刻报
「契约按计划版本 v1.7 冻结，当前计划是 v1.8 —— 计划改过，合同必须重审」。本次逐段比对
v1.7 快照与 v1.8 计划中合同引用的三节，**逐字节一致**：

| 合同依赖小节 | v1.7 快照 sha256 前 16 位 | v1.8 sha256 前 16 位 |
|---|---|---|
| §4.2 状态边界 | `bd5a89f9424f6f04` | `bd5a89f9424f6f04` |
| §4.4 全链路处理合同 | `05f02b64f29bd36c` | `05f02b64f29bd36c` |
| §9.1.1 量测适用性 | `5456d135ca5348b8` | `5456d135ca5348b8` |

因此只更新三份契约的冻结版本号（条款内容未改），守卫恢复 rc=0，自检仍 18/18。
本次**没有**改动 §2 Goal 文本、§3 完成合同、§4.1 权威对象、§4.5 跨环节不变量。

## 5. 本次明确没做的事

- **没有搬那四份 JSON**。搬动要重跑三套测试，属于 D1.P4 步骤 0 的验收范围；现状在计划里
  如实登记为「待收拢漂移」，不假装已经解决。
- **没有发起付费生成**。首轮账本仍为 4/8；D1.R1–D1.R4 完成前不再调用。
- **没有试图绕过 D1.C2**。v2 冻结基线仍是红的（提交内存门槛），沿用「环境阻塞不等于产品失败」。
- **没有改任何 `demo/` 代码或候选像素**；本轮写操作只有：计划、三份契约版本号、state、本文件。

## 6. 改动的文件与前后哈希

| 文件 | 改前 sha256 | 改后 sha256 |
|---|---|---|
| `docs/product-demo-goal-and-implementation-plan.md` | `be2003caa50e558297a0d2c5ed12e926fa7a83c4a5336b3d2357d52930ee2ae8` | `729fcb744579f588c7352e5b8f184750f65436d0078fc8379a018c9cfdd9fb30` |
| `_working/amz-listing-kit-product-demo/state.md` | `005848fb284edcdfb7d9748e89eab80b6ff9138ff230fd0a90b6fe00a4578fd3` | `82df8edc70a3b15337b00f5c4cc61669cff34ebe98993bb9d0e4cbe1b395d7cc` |
| `demo/contract/processing_contracts.json` | `15e351615a8db8a1d22d035b7815269dffe24f2d660b412c0e717521fc5ddb17` | `8a3534c60ff3f74dda7135856b8b76ceaedfa395915fc19c1b88f7c1cefbed8d` |
| `demo/contract/authority_matrix.json` | `71245327ee7e278a0aa190423e158bf48b817722e867bf21070e99b44c8e63b1` | `f1844b546cef84701b598f4d9fc01b9b861fcf788a18b7499b68e5548801eaf9` |
| `demo/contract/state_vocabulary.json` | `c0fa626c827c264b0ef55a8add9573a6f8018b0470c3335688e26f06a35d9a61` | `10637949c4f92f2c39eed0614cb224988cda7587d79333cbe96fbe5f3866ed7f` |

工作区外快照：`_stage-amz-control/plan-v18-20260926-113159/`（改前副本）。改计划与改 state 的脚本
留在同目录的 `splice_plan_v18.py`、`update_state.py`：锚点必须唯一，否则中止，可供第三方复核本次
到底改了什么。**这次是先留快照再改**（校准 #2 曾漏做，已在那份文件 §5 记账）。

## 7. 本文件不证明什么

- 不证明「换商品不改 `.py`」成立：那要等 D1.P4 跑 `bex-02` 的哈希探针；现在只有负面证据。
- 不证明 D1.R1–D1.R4 会得到什么结论：本轮只是把它们的输入、输出与验收口径定死。
- 不证明 Phase 3–5 的拟定运行形态正确：`app/` 的目录、端口与页面集要由 D2.R2 走查与 D3.R1 合同确认。
- 不证明产品可用或 G1 通过：Phase 1 仍在进行。
