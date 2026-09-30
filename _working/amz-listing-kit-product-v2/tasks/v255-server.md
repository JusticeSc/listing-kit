# V2.5.5 服务端任务书（整套一致性复核，POST /api/v2/review/suite）

> CONTROL-STATUS: draft · AUTHORITY: task-brief（V2.5.5 施工任务书；不发布目标、状态或规范）

仓库：E:\workbuddy_workspace\2026-09-20-16-38-19\amz-listing-kit（Windows PowerShell，命令先 Set-Location 到该目录）。
本任务书是 V2.5.5 服务端实现的唯一指令来源；浏览器侧契约已冻结在 app/product_v2/domain/suite-review.js（先读它）。

## 只允许改动的文件

- 新建 src/providers/v2_suite_review.py
- 新建 src/providers/v2_fake_suite_review.py
- 新建 src/providers/v2_dashscope_suite_review.py
- 编辑 src/providers/v2_registry.py
- 编辑 config/product-v2/providers.json
- 编辑 app/product_v2_server.py

其它文件一律不要动（尤其不要碰 app/product_v2/ 前端、tools/、docs/、README、_working/state.md）。不提交 git（不 add、不 commit）。

## 模板与先例（必须复用其模式）

单图复核：src/providers/v2_review.py、v2_dashscope_review.py、v2_fake_review.py、v2_registry.py、v2_langchain_chat.py；服务端 app/product_v2_server.py 的 _review / _review_capabilities / run_self_check；计划 docs/product-v2-goal-and-implementation-plan.md 的 §9.20（约 1185 行起）。

## 冻结契约（不得擅自更改）

1. 合同版本字符串 "v2.5.5"；端点 POST /api/v2/review/suite；单次最多 8 张图；findings 最多 12 条；evidence 最长 300 字符。
2. check 词表固定四个：suite_product_consistency、suite_color_material_consistency、suite_cross_image_anomaly、suite_style_consistency（在 v2_suite_review.py 里定义 SUITE_VLM_CHECKS 供验证器解析）。
3. 请求 JSON：{contract_version, locale, platform, product_facts:[{label,value} 最多 20], style_summary: string 最长 500, images:[{shot_id, title, purpose, keep_items 最多 8, allow_changes 最多 8, media_type, sha256, data_base64}]}。images 1..8 张、shot_id 去重；sha256 必须是 64 位十六进制且与解码字节真实一致（不一致 → 400 input_rejected，不调用模型，中文错误信息）。
4. 成功响应：{ok:true, result:{contract_version:"v2.5.5", submitted_shot_ids:[...], checked_images:N, findings:[{check, shot_ids（非空且是送审集合子集）, evidence, confidence:0..1}], provider_id, model_id, request_id, checked_at, latency_ms, summary}}。失败信封与分类沿用单图复核（family/code/retry_policy/message；input_rejected=400、provider 不可用=503、内部=500）。
5. provider 注册：providers.json 增加 "dashscope-suite-review" 与 "fake-suite-review"（结构与 dashscope-review / fake-review 平行）；v2_registry.py 增加 create_suite_review_provider(...)，解析语义（env、默认 id、缺 key 行为）与 create_review_provider 逐条镜像。capabilities 增加 "suite_review" 字段（provider 身份 + capabilities + 端点 + 合同版本 + 上限 8）。
6. dashscope 实现复用 v2_dashscope_review.py 的 ChatOpenAI 装配与错误映射；结构化输出必须强制 check 词表与 shot_ids 子集（越界即 provider 层失败）；系统提示词用中文写清四项检查：跨图商品外观一致、颜色材质一致、公共风格一致、跨图低级异常（乱码/裁切/畸形/多出部件）。
7. fake 场景：ok、findings（返回 1-2 条确定性 finding，覆盖不同 check 与不同 shot_ids）、unknown、invalid_output、refusal、rate_limited、http_error、auth_failed、internal_error（镜像 fake-review）。

## 自检（app/product_v2_server.py run_self_check）

新增整套复核检查，至少覆盖：capabilities 暴露 suite_review；（fake）路由返回绑定 submitted_shot_ids 的 findings 与合同版本；超过 8 张 → 400 input_rejected（不调用模型）；shot_id 重复 → 400；sha256 与字节不一致 → 400；provider 不可用时 capabilities configured=false 且路由 503。新增后自检总数必须大于等于 40 且既有检查全部保持通过，打印格式不变（仍为「V2 正式入口自检：N/N 通过。」）。

## 硬约束与验收

- 不改既有检查的断言与文案（除新增）；Python 全部用 uv run --locked python ...；行尾 LF；补丁走 codex.exe：& 'C:\Users\31368\AppData\Local\OpenAI\Codex\bin\7537f22ba194f7c1\codex.exe' --codex-run-as-apply-patch ($patch.Replace("`r","").TrimEnd("`n"))，补丁内容避免 $ 与反引号。
- 完成后必须运行并贴结果：uv run --locked python app/server.py --check（全绿）与 uv run --locked python tools/check_docs.py --no-run（全绿）。
- 最终报告（中文）：改动文件清单、自检总数、新增路由请求/响应示例（fake 场景）、与上述契约的任何偏差（有偏差必须显式说明）。任何卡点直接发消息给 root。
