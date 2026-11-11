<!-- 拆分件 02/02 · 父文档 evals/product-v2/refactor/packet08-adoption-ai-20261007T130000Z.md -->
# 2. 真跑原始输出
[返回 packet08-adoption-ai-20261007T130000Z.md](packet08-adoption-ai-20261007T130000Z.md)

## 2. 真跑原始输出

### 2.1 本片验证器（新建 test-only）11/11 PASS

命令：`uv run --locked python tools/verify_v2_packet08_adoption_ai.py --label packet08-adoption-ai-20261007T130000Z`
退出码：0。证据 JSON：`evals/product-v2/refactor/packet08-adoption-ai-20261007T130000Z.json`。

```text
[PASS] P08A-01a 未发起复核时审核卡显示未复核/未运行（不折叠成 Unknown）
[PASS] P08A-01b 未发起复核时人工采用可继续（state=current，不被复核门阻断）
[PASS] P08A-01c 比较面板未发起时视觉复核行记 not_run（不是 Unknown）
[PASS] P08A-02a 生成/查看/切换比较/采用本身不产生复核外发（calls==0）
[PASS] P08A-02b 切换查看候选不产生复核外发
[PASS] P08A-02c 显式发起后才有复核请求外发（exactly 1 次，不自动重提）
[PASS] P08A-03 真实失败才显示 Unknown（outcome=unknown + inspection_unavailable，不伪造 PASS）
[PASS] P08A-03b 复核失败不改变人工采用（仍 current，不自动改选）
[PASS] P08A-04 刷新后如实展示（unknown 仍 unknown，不退回未复核/不涨版本链）
[PASS] P08A-05 交付门仍评估确定性硬门（无 AI 报告不是硬缺口：门禁可读、无 not_run 伪造 BLOCK）
[PASS] P08A-06 零意外 console / page / HTTP 错误（unknown 演练的 504 路径除外）
evidence: evals/product-v2/refactor/packet08-adoption-ai-20261007T130000Z.json
RESULT PASS 11/11
```

P08A-06 例外理由：unknown 演练必然产生复核 504（unknown=true 真实失败路径，
与 5_2-10 同口径 `504 + unknown=true + provider_unknown/requires_review`），
浏览器对失败 fetch 的资源日志是同一请求的另一面；`logs["http"]` 已证明该 504
来自 `/api/v2/review/candidate`（http_ok 为空）。不是放宽断言，是把"期望内的
失败路径产物"从"意外错误"中排除，与 5_2-19 口径一致。

### 2.2 回归

| 脚本 | 结果 | 判定 |
|---|---|---|
| `tools/verify_v2_5_2_vlm_review.py --label p08a-regress4` | 19/19 全 PASS（含浏览器闭环 14–17、18 自检、19 零意外）退出码 0 | D1+D2+D3 修后全绿；无脚本期望修改 |
| `tools/verify_v2_5_5_suite_review.py --label p08a-regress` | 全 PASS（00/03–12 + 11 自检 45/45），退出码 0 | 未受本片影响（D2 的 facts 收窄对其是同向修复；其通过早于 D3 修，不依赖 D3） |
| `tools/verify_v2_5_4_rework_loop.py --label p08a-regress3` | 起不来：`#rework-panel` 在双击提交后 40s 仍 visible（V2.5.4-12 起的提交断言链全挂） | **既有产品缺陷，停下报告，不修期望**（见 §3） |

基线对照说明：`git archive bbf3509`（包07前基线）解到仓库外临时树，
与当前 `tools/verify_v2_5_2_vlm_review.py` / `verify_v2_5_4_rework_loop.py`
逐字节 diff 无差异（DIFF_EXIT:0），排除"脚本漂移"。基线树无 `.venv`
（且有中文文件名解包失败），未在基线树上重跑；改用等价判定：
`04e3398^` 的 workspace.js 返工提交已是同一错法 + 当前树 revert-facts 后
复现同一 `version=2/0` 错误（见 §3），证明与本片三处改动无关。

### 2.3 七门（逐条命令+退出码，本轮最终状态）

```text
node --check app/product_v2/workspace.js                                    → EXIT:0
npm run build:frontend                                                      → EXIT:0
npm run check:types                                                         → EXIT:0
npm run check:generated                                                     → EXIT:0
node --test evals/product-v2/node/*.test.mjs                               → 227 pass / 0 fail, EXIT:0
uv run --locked python tools/check_project_state.py                         → 全过, EXIT:0
uv run --locked python tools/check_docs.py --no-run                         → 全过, EXIT:0
```

## 3. 受阻项：5_4 返工双击提交版本错位（既有产品缺陷，最小复现）

- 现象：返工"预览→改输入→重预览→双击提交"后 `#rework-panel` 不收起，
  `#rework-error` = "文档 generation_confirm/rework:shot_main_clean 期望 version=2，当前是 0。"
- 机理：`submitRework`（`compare-view.ts:1065-1081`）把 **Prompt 版本**（第二次
  `compileAndSave` 后 v2）当成 `generation_confirm/rework:<shot>` 文档的
  `expectedVersion` 传给 `confirmAndRun`；而该 confirm 文档从未建过（当前 0）→
  存储层 `REVISION_CONFLICT`（`repository.js:389-398`）。整套提交链
  （generation-view 传 `generation.confirmed()?.version` 给 `CONFIRM_DOCUMENT_ID`）
  是对的，唯独返工链传错了版本来源。包07 slice5 抽取（04e3398）原样搬运了此错法，
  `04e3398^` 的 workspace.js 已是 `expectedVersion: version` + `reworkConfirmId`。
- 点击序列：比较候选 → #rework-open → 勾 product_fidelity → 填方向 → #rework-preview
  → 改方向（变脏）→ 重预览 → 双击 #rework-submit（dispatchEvent 两次 click）。
- 未修原因：修要动返工/确认事务语义（expectedVersion 该传 confirm 文档当前版本 0，
  还是重用 Prompt 版本做联合 fence？），超本片"adoption 单图 AI"边界；且 5_5 证据里
  -04/-09 既有失败（400 空 images）已归第三片，返工链一并留给后续返工/交付片。
  未改任何期望值凑绿。

## 4. 期望修正记录

- 本片：无。对 5_2/5_5 均未改脚本期望（5_2 是修产品 D1/D3 后自然全绿）。
- P08A-06 的 504 除外：见 §2.1，是失败路径产物归类（与 5_2-19 同口径），
  不是放宽断言；若判为放宽，请 Main 指正并回退该条为 FAIL。

## 5. 未做项与原因

- `evals/.../packet08-adoption-ai-<timestamp>.md` 即本文件；verifier 内嵌 JSON
  （final/130000Z 等）为机器证据，截图在临时目录（`%TEMP%\amz-p08a-*\p08a-adoption.png`），
  未拷贝入库（headless 截图仅作人工抽查，不作门禁）。
- 5_4 未修（§3 既有缺陷，超边界）。
- `selection-adoption.js` / `prompts.js` / `compare-view.js` / `generation-view.js`
  为 `build:frontend` 生成入库（本仓库约定），非手改。
- 中间态 JSON（final2/final3/final4，分别对应 D2 修前/P08A-06 判错/过滤器笔误）
  保留在 `evals/product-v2/refactor/`，证明排障过程，未删除。
- commit 只 add 本片文件，不碰 `_stage-amz-control/**`，不 push。
