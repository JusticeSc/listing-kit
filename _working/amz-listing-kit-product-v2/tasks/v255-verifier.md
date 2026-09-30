# V2.5.5 验证器任务书（整套一致性报告）

> CONTROL-STATUS: draft · AUTHORITY: task-brief（V2.5.5 施工任务书；不发布目标、状态或规范）

仓库：E:\workbuddy_workspace\2026-09-20-16-38-19\amz-listing-kit（Windows PowerShell，命令先 Set-Location）。本任务书是 V2.5.5 验证实现的唯一指令来源。

## 只允许新建/修改

- tools/verify_v2_5_5_suite_review.py
- evals/product-v2/harness/suite-review-contract.js 与 suite-review-contract.html
- evals/product-v2/fixtures/v2.5.5/（如需）
- 把既有验证器里写死的「33/33」计数断言改成计数无关的等价断言（grep 确认共 3 处：verify_v2_5_2 / v2_5_3 / v2_5_4；改成解析「N/N 通过」要求两者相等且无 FAIL 字样，不得放松其它断言）

不要修改 app/、src/、docs/、README、_working/ 下的任何文件；不提交 git。

## 必读模板

tools/verify_v2_5_4_rework_loop.py、tools/verify_v2_6_1_selection.py、tools/verify_v2_5_1_deterministic_review.py（free_port/start_static_server/read_suite/PROBE/SEED_SLOTS/compile_all/run_entry/png_bytes 等可复用函数）、tools/verify_v2_5_3_compare_panel.py（run_harness_suites）、evals/product-v2/harness/selection-contract.{js,html}、rework-contract.{js,html}、harness-api.js；计划 §9.20（约 1185 行起）。

## 已就绪的实现（写断言时以实际代码为准，发现偏差先发消息给 root）

A) 浏览器领域模块 app/product_v2/domain/suite-review.js 已落盘，导出：SUITE_REVIEW_SCHEMA_VERSION=1、SUITE_REVIEW_CONTRACT_VERSION="v2.5.5"、SUITE_REVIEW_DOCUMENT_KIND="suite_review"、SUITE_REVIEW_DOCUMENT_ID="suite_review"、SUITE_MAX_IMAGES=8、SUITE_VLM_MAX_FINDINGS=12、SUITE_VLM_MAX_EVIDENCE_LENGTH=300、SUITE_VLM_CHECK_TO_RULE（suite_product_consistency→vlm.suite_product_consistency、suite_color_material_consistency→vlm.suite_color_material_consistency、suite_cross_image_anomaly→vlm.suite_cross_image_anomaly、suite_style_consistency→vlm.suite_style_consistency）、canonicalSuitePayload、selectionFingerprintOf、inputsFingerprintOf、evaluateSuiteFindings、mergeExportFindings、buildSuiteVlmFindings、buildSuiteReviewReport、checkSuiteReviewReport、suiteReviewIsCurrent、suiteReviewSummaryText、assembleSuiteReview。
B) review.js 注册表新增 11 条规则：suite.selection_current、suite.dependency_satisfied（BLOCK）；suite.duplicates、suite.recommended_omissions、suite.selling_point_coverage（WARNING）；vlm.suite_product_consistency、vlm.suite_color_material_consistency、vlm.suite_cross_image_anomaly（HIGH_RISK）；vlm.suite_style_consistency、vlm.suite_inspection_completed、vlm.suite_inspection_unavailable（WARNING）。报告每条 finding 必须带 affected_shot_ids。
C) 服务端（并行实现中，见 _working/amz-listing-kit-product-v2/tasks/v255-server.md）：POST /api/v2/review/suite，合同版本 v2.5.5，单次不超过 8 张，SUITE_VLM_CHECKS 与浏览器逐字一致（跨语言镜像比对：从 src/providers/v2_suite_review.py 解析词表/合同版本/上限与浏览器常量比对）。
D) 工作台：app/product_v2/index.html 已有「整套一致性」卡片（suite-review-locked/editor/status/vlm/run/progress/groups/error），workspace.js 已有运行按钮、快照、报告渲染与「定位到图」（attempt-row 加 is-jump-target 类）。

## 交付要求

1. suite-review-contract.js/html：真实 Chromium 契约套件（编号 SR-01 起），覆盖：指纹确定性与变化（选择变化/规格变化都过期）、五个 suite.* 规则正反例与 affected_shot_ids 精确断言、export 层 findings 复用且带归属、VLM 合并四路（ok 带 findings / 空 findings→PASS / 越界 shot_ids→UNKNOWN / 畸形回应→UNKNOWN）、报告形状检查与当前性、summary 计数一致、文档种类存在。禁止空断言。
2. verify_v2_5_5_suite_review.py：静态守卫 + 契约套件 + 既有套件回归（选/返工/比较/单图复核四套）+ 跨语言镜像 + 工作台走查（真实页面 + 正式入口 fake provider：造出带采用选择的套图 → 运行整套检查得到「报告是当前的」；改变选择或输入后报告「已过期」并可重算；VLM Unknown 不阻塞；刷新后报告与状态恢复；finding 的「定位到图」可命中对应 attempt-row；零意外 console 错误）。证据命名 evals/product-v2/v2.5.5-suite-review-<stamp>final.{txt,json} 与 evals/product-v2/evidence/v2.5.5-suite-review-<stamp>{,-detail}.png（截图只放 evidence/ 子目录；dev 迭代证据用 -devN 后缀不提交）。
3. 跑通全绿后给我最终报告：通过项、证据路径、旧计数断言更新清单、未覆盖风险。卡点直接发消息给 root。

## 硬约束

Python 用 uv run --locked python ...；行尾 LF；补丁走 codex.exe：& 'C:\Users\31368\AppData\Local\OpenAI\Codex\bin\7537f22ba194f7c1\codex.exe' --codex-run-as-apply-patch ($patch.Replace("`r","").TrimEnd("`n"))（补丁避免 $ 与反引号）；不放宽任何断言、不伪造绿。
