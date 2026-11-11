<!-- 拆分件 02/02 · 父文档 evals/product-v2/refactor/complete-product-price-readiness-20261019.md -->
# 2. Image model 2 — doubao-seedream-5-0-flash-260915 (volcengine-ark) — VERIFIED（续）
[返回 complete-product-price-readiness-20261019.md](complete-product-price-readiness-20261019.md)

- Flash supports layer decomposition (1 base + up to 16 layers) and interactive editing;
  product never sends `layer_decomposition`. Per-call gate: any request enabling
  layer decomposition, group options, or new parameters needs a fresh price/param check.
- Tutorial page footer shows 最近更新时间 2026.10.13 — recent but not a promise of
  future stability; per-call re-check of size/params still applies per §17.6.

## 3. Auxiliary — `deepseek-v4.1-flash` — exact pricing VERIFIED

Primary sources (read live this session):

- Model + Beijing prices:
  https://help.aliyun.com/zh/model-studio/deepseek-v4.1-flash.md
- Beijing price table (文本生成-第三方模型/DeepSeek):
  https://help.aliyun.com/zh/model-studio/model-pricing.md

Facts:

- Exact ID `deepseek-v4.1-flash` verified on both the current model page and the current
  Beijing price table (same rates as snapshot `deepseek-v4.1-flash-1017`).
- Beijing original prices per million tokens: input busy 2 / idle 1; output busy 8 /
  idle 4 (output = 思维链+回答）; cache-hit input busy 0.2 / idle 0.1. Idle = UTC+8
  22:00–08:00. Conservative reservation uses busy rates with no cache discount.
- Official context limits: max input 1,000,000 tokens; max output 393,216 tokens.
- Conservative reservation formula (busy, CNY): `2 × input_M + 8 × output_M`.
  With the current default 5000-token output budget, its output leg is at most
  0.04 CNY. The official 1,000,000-token input ceiling then gives a conservative
  whole-call bound of **2.04 CNY**. Confirm the effective `max_tokens` before
  reserving: an override requires recalculation, not reuse of the default bound;
  a lower input reservation needs a justified actual-input bound.
  Vision/review/suite-review use `qwen-vl-max`, not DeepSeek: their token caps do
  not authorize those blocked paid paths or a silent model substitution.

## 4. Auxiliary — `qwen-vl-max` — NOT verifiable → paid use BLOCKED

What was tried this session:

- `https://help.aliyun.com/zh/model-studio/qwen-vl-max` and the `.md` variant both
  redirect to the generic model index (`.../models`), which no longer lists `qwen-vl-max`.
- The current Beijing price table (`model-pricing.md`, 千问VL section) contains zero
  `vl-max` matches; it lists only `qwen3-vl-plus` and `qwen-vl-ocr` rows.
- The English `qwen-vl-max` URL likewise lands on the generic index.

Conclusion: no verifiable current official exact-model pricing or context limits for
`qwen-vl-max`. Per plan §17.6, **paid `qwen-vl-max` calls (vision semantic, review,
suite review) are blocked**; the historical 1.6/4.0 per-M prices in the old ledger are
not current proof and must not be used for reservation. This blocks only paid use of
that exact ID — manual/offline routes and other approved-model paths continue. No
substitute model is proposed (out of scope for this preflight).

## 5. Reservation math (present evidence)

- One Qwen product image call (n=1, ≤3 refs): max **0.24 CNY**.
- One flash product image call (n=1, ≤3 refs): max **0.12 CNY**.
- 12 image calls worst case: 12 × 0.24 = 2.88 CNY (all-Qwen-max) down to 1.44 CNY
  (all-flash); both leave headroom inside 5 CNY for auxiliary reservations.
- One `deepseek-v4.1-flash` call: **2.04 CNY** only when the effective output
  budget is 5000; otherwise recompute from that budget and the safe input ceiling.
- `qwen-vl-max`: no reservation possible — paid use blocked (§4).

## 6. Exact remaining per-call gates (all still open)

1. A necessary missing/changed capability or a new program-quality hypothesis for the call.
2. Exact selected original asset, license, sha256, and input-count/size/parameter check
   against the official constraints in §1–§3 (Beijing region match, refs ≤ 3, n=1,
   Qwen size `*` format within 512²–2048²/ratio 1:8–8:1, flash pixels within
   [921600, 4624220]/ratio [1/16,16], no layer-decomposition/group params on flash;
   DeepSeek reservation uses its full safe bound unless a tighter input bound is verified).
3. Existing approved secure runtime credential channel; never extract secrets.
4. Sealed full-ledger takeover preserving newer working rows, idempotent activation of
   `complete-product-authorization-20261018T114240Z` exactly once, then per-call
   amount + category-count reservation before submit; failures/Unknown occupy quota;
   amount or count cap hit stops first.
5. `qwen-vl-max` paid paths stay blocked until exact-ID current official pricing is
   verifiable; re-check must not reuse historical prices or substitute another model ID.

Method note: public official docs only (static reads + rendered-doc text extraction in
an isolated headless tab, closed afterwards). Zero model/provider API calls, zero
secrets touched, zero files changed outside this note.
