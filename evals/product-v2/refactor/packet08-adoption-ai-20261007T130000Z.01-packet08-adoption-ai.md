<!-- 拆分件 01/02 · 父文档 evals/product-v2/refactor/packet08-adoption-ai-20261007T130000Z.md -->
# packet08 第二片：adoption 显式单图 AI（按需发起）
[返回 packet08-adoption-ai-20261007T130000Z.md](packet08-adoption-ai-20261007T130000Z.md)

# packet08 第二片：adoption 显式单图 AI（按需发起）

> 时间：2026-10-07；commit：f199726（第一批）+ 本轮第二批（见下）。
> 0 真实模型调用，0 付费。全程 headless Chrome + 本地 fake provider
> （FakeImageProvider/FakeReviewProvider holder 切换 ok/unknown + FakeSuiteReviewProvider/FakeSemanticProvider）。
> 不 push。

## 1. 改前 / 改后

### 1.1 未运行 ≠ Unknown（任务要求 1）

- 改前：比较面板视觉复核行无报告时 `data-compare-vlm` 缺省、文案"未检查"；
  审核卡无 AI 复核行；`reviewStatusOf` 只在 selection-adoption TS 内投影，未进界面。
- 改后：
  - `app/product_v2/ui/compare-view.ts`：视觉复核行未发起记
    `data-compare-vlm="not_run"`，文案"视觉复核（按需发起）：未复核（未运行，未发起 AI 复核；不阻断人工采用）"；
    审核卡新增 `.review-check-ai` 行（`data-review-ai` = reviewed/unknown/not_reviewed 三分）。
  - `app/product_v2/selection-adoption.ts`：新增 `reviewStatusOf(candidateId)` 投影
    （not_reviewed/reviewed/unknown），复用 domain `reviewStatusOf`（vlm 缺席=not_reviewed，
    outcome=checked→reviewed，否则 unknown）。单图报告与人工采用仍归 selection-adoption，
    未建第二份报告/选择状态（design §2-4 意图成立，与当前代码无冲突）。
  - `app/product_v2/ui/generation-view.ts`：尝试行缺报告文案 +
    `data-review-vlm="not_run"`；复核按钮改名"AI 复核这条候选（按需发起，可选）"并加 title。
  - `app/product_v2/index.html`：compare-review 按钮加 title（只点才调用）。

### 1.2 不自动触发（任务要求 2）

- 代码：`handleCompareReview` 只绑 compare-review 按钮点击；查看/切换/采用路径
  （selectCompareCandidate/openCompare/adoptCandidate/renderCompareImages）均不调用
  `reviewCandidate`。`reviewCandidate` 仍有 `in_flight` 防重入（同一 shot并发点一次只发一次）。
- 真跑证据：P08A-02a（生成/查看/切换/采用后 `review.calls==0`）、P08A-02b（切换候选仍 0）、
  P08A-02c（显式点击后 exactly 1 次）。见 §2。

### 1.3 不回退硬门（任务要求 3）+ 报告归属（任务要求 4）

- 确定性硬检查与人工采用仍是交付硬门；P08A-05 证明无 AI 报告不是交付硬缺口
  （export 门可读，无 not_run 伪造 BLOCK）。Unknown 才进 ack 门（`collectUnknowns`
  只收 report.vlm.outcome=unknown 的条目，not_run 不在其中——沿用既有语义，未改）。

### 1.4 修链中发现并修复的两个产品缺陷（非文案）

**D1. adoption 来源链查找误命中 pending 版本（本片引入回归，已修）。**
`candidateReviewRequest` 用 `attemptChainOf(shotId).find(action_id 相等)` 取首条，
同 action_id 链有 pending_submit（task_id=None）/submitted/succeeded 三版本时命中 ver1，
`candidateMatchesAttempt`（task_id 必须一致）失败 → 显式复核零外发、compare-status
"候选的原动作来源链缺失或不一致"。修法：reverse-find 先找与候选身份一致的版本，
找不到才回退旧行为（`selection-adoption.ts:297-299`）。5_2 同链路同步受益。

**D2. 复核请求 facts 形状违反服务端契约（既有缺陷，本片修请求侧）。**
`confirmedFacts()` 吐 `{slot_id,label,value,source}`，服务端 `FactItem`
（`src/providers/v2_review.py:124`）`extra=forbid` 只收 `{label,value}` →
400 input_rejected（"Extra inputs are not permitted"，无模型调用）。
修法：`confirmedFacts` 收窄为 `{label,value}`（`prompts.ts:96-104` + 生成 `.js`）。
裁决理由：不动服务端语义、不放宽契约；Prompt/简报侧 `ConfirmedFact`
（含 slot_id/source/value 原值）不受影响；整套 `runSuiteReview` 共用同一函数同步受益。
对照：旧形状 `parse_review_request` 前置拒绝（与身份无关），新形状通过契约层
（只剩 sha256 自洽性检查，属正常身份逻辑）。

**D3. adoption `changed` 不刷生成区尝试行（本片引入回归，已修）。**
`createSelectionAdoptionModule({changed})` 在 workspace 只刷 `deliveryView`，
5_2 的生成区复核按钮点后服务端已落 unknown 但 `.attempt-review` 行不重绘 →
5_2-17 等 "VLM 未完成" 超时。修法：`changed` 加 `generationView?.renderAttempts()`
（`workspace.js:596`）。注意包07抽取前基线行为待考（基线树无 compare-view.ts，
旧逻辑在 workspace.js 内，是否自动重绘未验证），故判"本片引入回归"依据是：
D1 修后 ok-path 文本可达、仅 unknown-path 文本不到 + HTTP 504 已回 + DB 已落盘
三者齐备，唯独行文本不更新。

