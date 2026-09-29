# D2.R2 补充证据：三条失败路径从「承诺」变成「可跑」（2026-09-26）

> EVIDENCE-SNAPSHOT: historical · NOT-AUTHORITY
> 本文只记录这一次做了什么、读数如何。计划正文见
> `docs/product-demo-goal-and-implementation-plan.md` §6.11.5；当前状态与下一动作见
> `_working/amz-listing-kit-product-demo/state.md`。本次**零付费调用、零联网**。

## 1. 触发

§6.11.5 的「失败路径」一行承诺了三件事：缺料说清缺哪一份、不进流程；渲染器（排版层）缺失
时显示「未知」、不猜成功；端口占用明确提示换端口。写这一行的时候没人跑过它们 ——
**承诺没有读数**。本轮把它们逐个实测，结果三条全都不成立（见 §3），修完再定成判据。

## 2. 现在成了什么

| 项 | 以前 | 现在 |
|---|---|---|
| 缺料（起服务） | 命令行打一行字就退出（浏览器里什么都看不到）；部分文件甚至抛堆栈 | 起一个只显示原因的服务：页面上写「装不起来」+ **点名缺哪一份** + 去哪里补；退出码 2 |
| 缺料（`--check`） | 退出码 1（与"页面内容不对"混在一起） | 退出码 **2**（装不起来），stdout 说明缺哪一份，stderr 没有堆栈 |
| 端口占用 | `OSError` 堆栈 | 一句话说清哪个端口用不了 + 建议的替代端口，退出码 **3** |
| 有文案要叠 | 合成页写死「这一期没有需要叠上去的精确文案…原样输出」 | 读**方案的文案记录**：没有 → 原样输出；有 → 「**未知**」，不猜成功 |

退出码：`0` 起得来 / `1` 自检不通过 / `2` 缺料装不起来 / `3` 端口用不了（写在
`app/server.py` 的模块说明里，README §9 也标了）。

## 3. 实测抓到的真缺陷（五处，全部已修）

| # | 现象（修前原样读数） | 原因 | 处置 |
|---|---|---|---|
| 1 | 缺 `verifier_plan.json`、`prompt_profile.json`、`reference_pack.json` → 抛 `PackageError` / `FileNotFoundError` **堆栈** | 入口层只接 `OfflineError`，而链上不同环节按需读文件、各自抛自己的异常 | `OFF.build()` 把整段装配的 `PackageError` 统一转成 `OfflineError`（缺料是业务事件，不是程序异常） |
| 2 | 缺 `runs.json` → 装配**照样往下走**（"候选：0 张"），缺 `human_visual_review.json` → 同样往下走 | 显式指定商品包时没人核齐套（`COMPLETE_KEYS` 只用于"没给 sku 时挑默认包"） | `_assemble()` 用**同一张登记表** `PKG.FILES` 做齐套检查，一次性报出缺哪几份，装配停在这里 |
| 3 | 缺 `threshold-derivation.json` → `KeyError: 'PC-02'` 堆栈 | `check()` 在装配没走通的会话上继续走那一遍，`confirm_plan` 直接 `self.steps["PC-02"]` | `check()` 只在**没有阻塞**的会话上走那一遍（装不起来就不走，也不产出假读数）；`confirm_plan` 加第二道：按合同回 `business_reject`，不抛异常 |
| 4 | 端口被占 → `OSError` 堆栈 | 建服务时没接住 | `bind()` 明确提示 + 建议端口，退出码 3 |
| 5 | 合成页写着「这一期没有需要叠上去的精确文案，所以成品是原样输出」 | **界面替后端下了结论**，而且是从一句写死的话里下的 | 新增 `OFF.copy_records(session)`：结论只从方案的文案记录来；有记录时页面说「未知」 |

第 5 条是这一类里最值得留意的：它不是崩溃，是**界面替后端吹了一个它没算过的牛**。
它一直让自检保持绿色，因为自检问的是「页面上有没有这句话」——有，因为话是写死的。

## 4. 判据与读数

新增 `evals/probes/offline_failures.py`（7 项）：

```
离线入口的三条失败路径（真进程 · 真 HTTP · 零付费）
[OK] A1 缺料：结构性前提（verifier_plan.json）        [OK] A2 缺料：链上按需读的（threshold-derivation.json）
[OK] A3 缺料：连包都认不出来（product.json）          [OK] A4 反向：完好的包给正常首页
[OK] B  端口占用：说人话 + 给换法
[OK] C1 有文案记录：合成页说未知，不算成功            [OK] C2 反向：无文案记录：合成页给原样输出
OK：7 项全部与预期一致。
```

A/B 起**真进程**、用**真 HTTP** 取页面；A4 与 C2 是反向项（完好的包必须给正常首页；
无文案时必须给「原样输出」）—— 没有这两条，A/C 的"通过"可能只是页面写死了那句话。
C1/C2 直接调同一份渲染函数（要往方案里注入一条文案记录，注入只能发生在进程内），探针
自己的说明里写明了这一点。

## 5. 改了什么（哈希）

| 文件 | 改前 sha256 前 16 | 改后 sha256 前 16 | 字节 | 改动 |
|---|---|---|---|---|
| `app/server.py` | `64173EB1E32A479C` | `DB4240A770AD72CC` | 18698 → 23502 | 装不起来页 + `bind()` + `serve_blocked()` + 退出码 2/3 + 自检只在干净会话上走那一遍 |
| `app/offline.py` | `158220F76C1C8795` | `58C60D17D46790E0` | 10970 → 13785 | `build()` 统一转 `OfflineError`；`_assemble()` 齐套检查；`copy_records()`；`confirm_plan` 第二道 |
| `app/views.py` | `01C8AAE76688C2DB` | `FCA787B50FE18F0B` | 38043 → 38633 | 合成页结论改由方案数据决定（有文案 → 未知） |
| `README.md` | `6C91FE6D19117E2D` | `D957AF63658526BA` | 56884 → 57314 | §1 增一行；§9 增一条命令 + 退出码说明 |
| `evals/probes/offline_failures.py` | 新增 | `D0835415A6FF88C9` | 10230 | 三条失败路径的判据（7 项，含两条反向） |

改前副本：`app/server.py`、`app/views.py`、`README.md` 在本轮动手前快照
`_stage-amz-control/d2r2a-20260926-1412/`；`app/offline.py` 本轮之前没被改过，
它的改前副本在更早的 `_stage-amz-control/calib8-20260926-1357/`。

## 6. 守卫读数（本次运行）

| 检查 | 读数 |
|---|---|
| `evals/probes/offline_failures.py` | 7 项全部与预期一致 |
| `app/server.py --check` | 全过（5.3s，退出码 0） |
| `evals/probes/offline_app.py` / `walkthrough_brief.py` | 6 向 / 全过（都仍然绿） |
| `tools/check_docs.py` | 全过（登记 30 = 实际 30；新增的探针命令按规矩只登记、由自己的入口跑） |
| `tools/check_project_state.py --project .` | 全过 |
| `demo/contract/contract_tools.py --check` | 通过（v1.13） |

## 7. 没解决的

- **R2.b 仍然没有真人**（这一轮做的是把页面在失败时的行为修干净，不是替真人走查）。
- 离线入口现在要求商品包**九份文件齐全**（同一张登记表 `PKG.FILES`）。第二商品 `bex-02`
  只有两份，它**不是这个入口的完整包** —— 这不是缺陷，是边界；但它意味着"换个商品"
  在这条离线链上要先备齐同样九份，state 里已登记。
- 「未知」这条路径目前只有合成页一处：Phase 3 接持久化与真实执行后，同样的判断要在
  真实状态上重做一遍（那一层的"未知"不能只靠页面文案）。

## 8. 计划与合同的同轮修订（v1.13 → v1.14）

实测读到的两件事让 §6.11.5 那一行必须改：它写着「渲染器缺失」，而这条链上没有「渲染器」
这个环节（那是上一代 v2 的词），实际要说的是「需要排版层而这一版不做」；同时那三条承诺
当时都没有读数。处置：改措辞、把 `evals/probes/offline_failures.py` 登记进验收命令那一行、
新增计划 §1.12 记录这次修订（不含状态、任务或依赖变化）。

合同按规矩先红后绿：改计划后守卫立刻 **rc=3**（「契约按计划版本 v1.13 冻结，当前计划是
v1.14」）；重审（只改版本号，词汇与状态取值一字未动）后 rc=0，自检 18/18。

| 文件 | 改前 sha256 前 16 | 改后 sha256 前 16 | 字节 | 改动 |
|---|---|---|---|---|
| `docs/product-demo-goal-and-implementation-plan.md` | `F7D2B03A14E9CAF8` | `F26E4AC41560476D` | 111604 → 113019 | v1.13 → v1.14；§6.11.5 两行；新增 §1.12 |
| `demo/contract/processing_contracts.json` | `A2AAD4B6E01E15DB` | `D0193F60512A716C` | 11648（不变） | 只改 `plan_version` |
| `demo/contract/authority_matrix.json` | `FA1EFCFF58C08FA8` | `2D061AA7036BF58C` | 6386（不变） | 同上 |
| `demo/contract/state_vocabulary.json` | `DB34B4D2DF3232A0` | `66F51E5AA786EC49` | 1479（不变） | 同上 |
