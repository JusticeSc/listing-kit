# Complete-product price readiness — present official preflight (2026-10-19)

- Observed: 2026-10-19 ~05:29 UTC (live reads this session; no model invocation, no ledger mutation).
- Scope: approved China-Beijing image IDs `qwen-image-3.0`, `doubao-seedream-5-0-flash-260915`
  (n=1, ≤3 actual image inputs, unchanged product profile); auxiliary IDs `deepseek-v4.1-flash`,
  `qwen-vl-max` checked for exact-ID official pricing only.
- **Current extra 5 CNY / 12-image / 4-aux authorization is NOT activated by this note.**
  Activation follows plan §17.6 (sealed-ledger takeover, idempotent key
  `complete-product-authorization-20261018T114240Z`) and is a separate gated step.
- Historical prices (old ledger, 2026-10-18 preflight) were used as context only, never as
  current proof. Where current values match history it is stated as a fresh observation.

## 1. Image model 1 — `qwen-image-3.0` (dashscope-qwen-image) — VERIFIED

Primary sources (read live this session):

- Model + Beijing prices:
  https://help.aliyun.com/zh/model-studio/qwen-image-3-0.md
- API reference (region/endpoints/parameters):
  https://help.aliyun.com/zh/model-studio/qwen-image-generation-and-editing-api-reference.md

Facts:

- Beijing （华北2/北京） original prices: image input 0.02 CNY/image (1K and 2K tiers),
  image generation 0.18 CNY/image (1K and 2K tiers). No discount or free-tier deduction.
- Metering tier is decided by output area (≤2,250,000 px = 1K tier); both tiers share the
  same Beijing unit prices, so tier has no reservation impact. Product default 1344*1344
  (= 1,806,336 px) falls in the 1K tier.
- Conservative n=1 maximum for one product call with ≤3 reference images:
  **3 × 0.02 + 1 × 0.18 = 0.24 CNY**.
- Region rule: model, endpoint URL, and API key must all belong to the same region;
  cross-region calls fail. Beijing legacy host `https://dashscope.aliyuncs.com` is still
  stated usable; workspace domain `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com`
  is recommended. Product `DEFAULT_BASE_URL=https://dashscope.aliyuncs.com/api/v1` +
  async path `/services/aigc/image-generation/generation` + `X-DashScope-Async: enable`
  + `GET /api/v1/tasks/{task_id}` matches the documented Beijing async shape.
- Official qwen-image-3.0-series constraints relevant to the unchanged product profile:
  1–3 reference images; input image sides 1–8000 px (384–2048 recommended), long/short
  ≤ 10:1, ≤ 10 MB, JPG/JPEG/PNG/BMP/TIFF/WEBP/GIF; output area 512*512–2048*2048,
  ratio 1:8–8:1; DashScope `size` uses `*` separator; `n` 1–6 (product frozen n=1);
  `prompt_extend` default true (product frozen false); `enable_thinking` default true but
  effective only when `prompt_extend=true` (so product profile runs without thinking);
  `watermark` default false; prompt recommended ≤ 4500 tokens; Beijing RPM 20.
- Product profile fit: 1344*1344 inside official area/ratio bounds; max 3 refs = official
  3.0-series max; png output matches official png format. No profile change needed.

Limits / per-call gates:

- Prompt gate is in tokens (recommended ≤4500) while product caps 4000 chars; chars ≠
  tokens, so per-call input check must confirm the actual prompt, not assume fit.
- Prices are original prices; console promotions must not be deducted from reservations.

## 2. Image model 2 — `doubao-seedream-5-0-flash-260915` (volcengine-ark) — VERIFIED

Primary sources (rendered live in isolated headless browser this session, docs only):

- Model list: https://docs.volcengine.com/docs/ark/model-list?lang=zh
- Model pricing: https://docs.volcengine.com/docs/ark/model-pricing?lang=zh
- Image API: https://docs.volcengine.com/docs/ark/image-generation-api?lang=zh
- Pro/flash tutorial: https://docs.volcengine.com/docs/ark/seedream-5-0-pro?lang=zh
- General Seedream tutorial: https://docs.volcengine.com/docs/ark/seedream-4-0-5-0?lang=zh

Facts:

- Exact model ID `doubao-seedream-5-0-flash-260915` is present on the current model list
  with 文生图/单张图生图/多参考图生图/单图生成/图层拆分 and 500 IPM, and no
  “即将下线” tag (unlike lite/4.5/4.0 rows, which carry one).
- Pricing page image-model row `doubao-seedream-5-0-flash`: input images 免费,
  output 0.12 CNY/image. The price row uses the family name; the exact-ID linkage is via
  the model-list row plus the tutorial line “Seedream 5.0 flash（Model ID:
  doubao-seedream-5-0-flash-260915）”. No other flash price row exists on the page.
- Conservative n=1 maximum for one product call (inputs free, sync single image, no
  group mode on flash): **0.12 CNY regardless of 0–3 reference images**.
- Endpoint `POST https://ark.cn-beijing.volces.com/api/v3/images/generations` matches
  product `DEFAULT_BASE_URL=https://ark.cn-beijing.volces.com/api/v3` + `CREATE_PATH`
  exactly. API doc confirms flash generates single images only
  (`sequential_image_generation` unsupported) and accepts `image` as string/string[].
- Official flash/pro constraints relevant to the unchanged product profile:
  `size` 方式2 total pixels [921600, 4624220], ratio [1/16, 16];
  product default 1344*1344 = 1,806,336 is inside. The broader generic profile
  bounds are not wholly inside flash's limits (384*384 is below 921600), so each
  actual request must satisfy the flash area/ratio constraints; pro/flash ≤10 refs
  (product 3); input formats include png/jpeg, per-image pixels [196, 36M], side > 14 px,
  ratio [1/16, 16], ≤ 30 MB (product 10 MB cap is conservative);
  `output_format` png/jpeg, `response_format` url/b64_json, `watermark: false` = no
  watermark — all match the product request body.
- Price-page note: images not successfully output (e.g. moderation) are not billed.
  Reservation stays conservative: a billed/Unknown outcome keeps the full 0.12 reserved.

Limits / per-call gates:

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
