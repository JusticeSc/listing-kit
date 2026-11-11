<!-- 拆分件 01/02 · 父文档 evals/product-v2/refactor/packet08-stale-callers-20261007T084634Z.md -->
# 包08 第四片：旧调用/复制 schema 同包删除
[返回 packet08-stale-callers-20261007T084634Z.md](packet08-stale-callers-20261007T084634Z.md)

# 包08 第四片：旧调用/复制 schema 同包删除

> 时间：2026-10-07T084634Z · 基线：包08 前三片已闭合（3961d24 / f199726 / f50ec77 / 007356c + 验证网 095df59/ead0647/90710cf）
> 范围：`app/` `src/` `tools/` `evals/`（`.ts/.js/.py/index.html`）；V1/夹具/公开验证器脚本本身不动；不改行为。

## 1. 逐项对照表（删前证据 → 判定 → 删后）

### D1（删）：generation 侧的单图复核回调环残留 —— 零消费者，已删
- 位置：`app/product_v2/generation.ts`
  - `GenerationDependencies.candidateReviewRequest`（旧 L177，构造期占位 dep）
  - `GenerationDependencies.reviewRunner?`（旧 L179，从未被 generation 内部读取）
  - `GenerationModule.setCandidateReviewRequest`（旧 L281）/ `setReviewRunner`（旧 L282）
  - `functionDeps` 中的 `"candidateReviewRequest"`（旧 L372）
  - `let candidateReviewRequestBuilder = deps.candidateReviewRequest`（旧 L387，只赋值、零调用——全文件仅此一处出现，无 `builder(` 调用点）
  - 返回对象中的两个 setter（旧 L1476–1477）
  - 附带：`import type { ..., ReviewCandidateResult }` 收窄为仅 `AdoptionReviewAccess`（旧 L59；`ReviewCandidateResult` 在本文件仅服务于已删的 runner 签名，`CandidateRecord` 仍被候选链广泛使用故保留）
- 位置：`app/product_v2/workspace.js`
  - 构造占位 `candidateReviewRequest: async () => { throw ...尚未装配 }`（旧 L583）
  - 装配补线 `generation.setCandidateReviewRequest(...)`（旧 L600–602）、`generation.setReviewRunner(...)`（旧 L603–605）
- 位置（测试替身同步）：`evals/product-v2/node/generation-isolation.test.mjs` 两处 `candidateReviewRequest: () => null`（L81/L153，已删；render 回调保留）、`tools/verify_v2_r5_2_two_adapters.py` L222 `candidateReviewRequest: () => ({})`（已删）
- 引用搜索（删前，全库）：`candidateReviewRequestBuilder|setCandidateReviewRequest|setReviewRunner|reviewRunner` 在 `app/src/tools/evals/config` 仅命中 generation.ts/workspace.js/测试替身/历史证据 md（`packet08-adoption-ai-20261007T130000Z.md` 为过程记录，不动）；`deps.reviewRunner`/`reviewRunner(` 零调用；`generation.candidateReviewRequest` / `generation.reviewCandidate` 零调用（视图均直调 `selectionAdoption.reviewCandidate`）。
- 为何安全：单图复核请求准备早已归 adoption（`selection-adoption.ts:293 candidateReviewRequest` 内部函数 + `reviewCandidate:316` 内部直调，无需经 generation 转发）；删后复核唯一入口仍是 adoption，generation 只保留真正被读的 `reviewAccess.ensureReport`（候选保存时的确定性报告补建，L830/L883 有活调用）和 `reviewFlightReader→isReviewInFlight`（视图按钮状态用 adoption 直调，此处仅剩 generation 自身转发，无外部调用但保留无害——见 R2）。
- 删后：`npm run build:frontend` 重生成 `generation.js`（7 行收缩）；`check:types` / `check:generated` 绿。

### R1（保留）：`generation.setReviewFlightReader` + `deps.reviewFlightReader` + `generation.isReviewInFlight`
- 活引用：`workspace.js:598-599` 装配（`selectionAdoption.isReviewInFlight` 注入）；`generation.ts:1501` 转发实现。
- 不删原因：虽无外部经 generation 的调用（视图均直调 adoption），但它是装配完整的在途状态透传，无重复状态、无行为分叉；删它需同步改 `GenerationModule` 公开面，收益为零且触及公开接口，不符合"只删零消费者"（它有装配消费者）。
- 单一来源仍成立：飞行集合唯一在 adoption 的 `reviewFlights`（`selection-adoption.ts:83`），generation 不持有第二份。

### R2（保留）：`generation.setReviewAccess` + `deps.reviewAccess.ensureReport`
- 活引用：`workspace.js:600` 装配；`generation.ts:830/883` 真实调用（旧候选报告补建 + 新候选保存后报告摘要）。
- 不删原因：正式页面路径在用；它是"候选保存时同步建确定性报告"的唯一通道，删了会改行为。

### R3（保留）：`selection-adoption.candidateReviewRequest`（公开面 + 内部实现）
- 活引用：`selection-adoption.ts:332` 被 `reviewCandidate` 内部调用；`workspace.js` 旧补线已删，但 adoption 内部调用仍在。
- 不删原因：单图 AI 按需复核的唯一请求准备实现（事实/规格/原动作/图片字节收口）；删了等于删功能。

### R4（保留）：`reportsNow` / `loadReport`（AdoptionReviewAccess 三件套之二）
- 全库 `reportsNow()` / `loadReport(` 外部调用：除 adoption 自身 restore/merge 回写外无第三方调用；但它们是 `AdoptionReviewAccess` 接口成员，且 `reportAccess()` 的默认分支实现依赖这三件套闭环（`reportOf/reportsNow/loadReport/ensureReport` 同一内存 Map）。
- 不删原因：接口成员 + 内存后备实现的一部分；单独抠掉两个方法会破坏接口完整性且无收益（零风险、无第二份状态）。

