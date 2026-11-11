<!-- 拆分件 01/03 · 父文档 evals/product-v2/refactor/image-candidate-review-20261002.md -->
# V2.R4.1 — Second image-model / default-profile policy assessment
[返回 image-candidate-review-20261002.md](image-candidate-review-20261002.md)

NOT-AUTHORITY: point-in-time evidence for V2.R4.1 only. Not a plan, not a selection approval, not a budget authorization.

# V2.R4.1 — Second image-model / default-profile policy assessment

- Task: `V2.R4.1` ([plan §9 R4.1](docs/product-v2-refactor-plan.md): at least two candidates vs current qwen, capability/protocol/cost/license comparison, one bounded recommendation or exact gap).
- Date observed: 2026-10-02 (UTC). All external facts are from public primary docs read on this date; supplier docs change — re-verify at PoC time.
- No real supplier calls were made. No reference images were uploaded anywhere. No quality proof exists. No budget or material authorization exists (all PoC spend/material is UNAPPROVED, see §7).
- Repo inputs read (read-only): `src/providers/v2_image.py` (`IMAGE_CONTRACT_VERSION = "v2.4.1"`), `src/providers/v2_dashscope_image.py`, `src/providers/v2_fake_image.py`, `src/providers/v2_registry.py`, `config/product-v2/providers.json` (schema `amz-listing-kit/provider-registry@2`, `version: 1`, `default_image_provider_id: dashscope-image`), `app/product_v2_server.py` (routes `/api/v2/images/submit|status|result`), `deploy/caddy/Caddyfile`, `Dockerfile`, `.env.example`, `docs/product-v2-project-context.md` (SEL-010/014/015), `docs/product-v2-refactor-plan.md` (§9 R4.1/R4.2/R4.3).
- Legend: [PROVEN] = read in repo or primary doc this pass (linked). [PROPOSED] = design judgment for parent approval, not implemented. [UNKNOWN] = not observed; must not be assumed.

## 0. Current-contract baseline (what a second adapter must plug into) [PROVEN]

- Neutral contract (`src/providers/v2_image.py`): `SubmitRequest{action_id, prompt, references[1..3], size, seed?, model_id?}`, `TaskRequest{task_id}`, `ImageTaskResult{provider_id, model_id, task_id?, status ∈ PENDING/RUNNING/SUCCEEDED/FAILED/CANCELED/UNKNOWN, result_count, error?, request_id?, unknown}`. Extra fields rejected. Prompt ≤ 4000 chars. Sizes `W*H`, edges 384–2048, area 512²–2048², ratio 1:8–8:1. Reference = role词表 + media-type signature check + sha256-of-bytes check, ≤10 MB each. Secret/bytes/URLs never enter the result object.
- Current real adapter (`src/providers/v2_dashscope_image.py`): `POST {base}/services/aigc/image-generation/generation` with `X-DashScope-Async: enable`, `GET {base}/tasks/{id}`, result = re-query status then download first allowlisted URL to bytes. Capabilities: `reference_images=true, max_reference_images=3, async_tasks=true, n_per_submit=1, prompt_extend=false, watermark=false`. Timeout/parse/no-task-id → `provider_unknown`, "先核对，不要自动重提". Task-id mismatch → `PROVIDER_TASK_MISMATCH`. Result bytes must be PNG-signatured; media-type allowlist `{"", application/octet-stream, image/png}`.
- Endpoint guard [PROVEN]: `_safe_base_url` requires `https`, host `aliyuncs.com` or `*.aliyuncs.com`, no userinfo, port None/443, no query/fragment; `allow_redirects=False`; result-URL guard identical. No key, prompt, bytes, or signed URL in `ImageFailure` messages by construction.
- Server (`app/product_v2_server.py`) [PROVEN]: per-request provider construction (no server task table), `Cache-Control: no-store`, `redact()` masks `sk-`/Bearer-shaped secrets in error surfaces, result route returns bytes + `X-Image-Sha256`, never a redirect to a supplier URL. Registry selection order: explicit request > env (`AMZ_V2_IMAGE_PROVIDER`) > registry default.
- Product policy (context SEL-015, §6.11) [PROVEN]: BYOK is the direction (memory-session + HTTPS request-level use, never into IndexedDB/localStorage/ZIP/log/error/evidence); current product is env-only (`DASHSCOPE_API_KEY`), BYOK not implemented. Default key never goes to user endpoints. R4.3/R5.2 own the implementation; this report only assesses.

## 1. Candidate A — OpenAI Images API (`gpt-image-1.5`, bounded pin) [PROVEN docs, PROPOSED pin]

Primary sources: [Image generation guide](https://developers.openai.com/api/docs/guides/image-generation), [Images API reference](https://developers.openai.com/api/reference/resources/images), [Pricing](https://developers.openai.com/api/docs/pricing), [Data controls](https://developers.openai.com/api/docs/guides/your-data).

