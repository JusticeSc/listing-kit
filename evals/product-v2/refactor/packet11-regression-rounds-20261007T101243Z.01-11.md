<!-- 拆分件 01/03 · 父文档 evals/product-v2/refactor/packet11-regression-rounds-20261007T101243Z.md -->
# 包11 第一片：两轮完整离线回归（可复核证据）
[返回 packet11-regression-rounds-20261007T101243Z.md](packet11-regression-rounds-20261007T101243Z.md)

# 包11 第一片：两轮完整离线回归（可复核证据）

- observed_at: 2026-10-07T101243Z（UTC；后续时间为准见各证据 `finished_at`/`observed_at`）
- 运行方式：逐个**串行单跑**，无 `--live`、无密钥、零外呼、零费用；页面类 timeout 900s、静态类 120s。
- 日志落盘：`_working/p11regression/logs/<name>.r{1,2}.log`（工作区本地，不提交）。
- 本片结论：**不能通过** —— 12 个验证器两轮一致红（非 flake），其中 9 个是真红（脚本/接线缺陷 + 环境前提），1 个是已知过期，另 2 个是新真红（产品缺陷 + 断言过期）。详见 §4 不能闭合清单。
- 定性图例：真绿=两轮全过；已知过期=任务书点名的 3_5 `-10` / 5_3 `-15`（本次 5_3 全过，仅 3_5 命中）；真红=两轮都红且非 flake；flake=一轮红一轮绿（本轮仅 4_2 一例）。

## 1. 离线验证器清单（38 个中纳入 34 个，排除 4 个）

纳入 = 默认参数（无 `--live`）下零密钥、零付费、零外部网络的全部入口。`--label p11r1/p11r2` 仅改证据文件名，不改行为。

| # | 验证器 | 类 | 证据前缀 |
|---|---|---|---|
| 1 | tools/verify_v2_1_1_indexeddb.py | 页面 | evals/product-v2/v2.1.1-indexeddb-*.txt/.json |
| 2 | tools/verify_v2_1_2_project_home.py | 页面 | evals/product-v2/v2.1.2-project-home-*.txt/.json |
| 3 | tools/verify_v2_1_3_project_package.py | 页面 | evals/product-v2/v2.1.3-project-package-*.txt/.json |
| 4 | tools/verify_v2_1_4_formal_entry.py | 页面 | evals/product-v2/v2.1.4-formal-entry-*.txt/.json |
| 5 | tools/verify_v2_2_1_product_contracts.py | 页面 | evals/product-v2/v2.2.1-product-contracts-*.txt/.json |
| 6 | tools/verify_v2_2_2_semantic_provider.py（默认，不加 `--live`） | 静态 | evals/product-v2/v2.2.2-semantic-provider-*.txt/.json |
| 7 | tools/verify_v2_2_3_intake_understanding.py | 页面 | evals/product-v2/v2.2.3-intake-understanding-*.txt/.json |
| 8 | tools/verify_v2_2_4_category_generality.py（默认，不加 `--live`；C2–C4 记 SKIP） | 静态 | evals/product-v2/v2.2.4-category-generality-*.txt/.json |
| 9 | tools/verify_v2_3_1_suite_registry.py | 页面 | evals/product-v2/v2.3.1-suite-registry-*.txt/.json |
| 10 | tools/verify_v2_3_2_suite_editor.py | 页面 | evals/product-v2/v2.3.2-suite-editor-*.txt/.json |
| 11 | tools/verify_v2_3_3_session_lifecycle.py | 页面 | evals/product-v2/v2.3.3-session-lifecycle-*.json |
| 12 | tools/verify_v2_3_3_spec_versions.py | 页面 | evals/product-v2/v2.3.3-spec-versions-*.txt/.json |
| 13 | tools/verify_v2_3_4_prompt_compiler.py | 页面 | evals/product-v2/v2.3.4-prompt-compiler-*.txt/.json |
| 14 | tools/verify_v2_3_5_pre_generation_confirm.py | 页面 | evals/product-v2/v2.3.5-pre-generation-confirm-*.txt/.json（失败时无证据文件） |
| 15 | tools/verify_v2_3_6_prompt_manual_edit.py | 页面 | evals/product-v2/v2.3.6-prompt-manual-edit-*.txt/.json |
| 16 | tools/verify_v2_4_1_image_gateway.py | 静态 | evals/product-v2/v2.4.1-image-gateway-*.txt/.json |
| 17 | tools/verify_v2_4_2_generation_attempt.py | 页面 | evals/product-v2/v2.4.2-generation-attempt-*.txt/.json |
| 18 | tools/verify_v2_4_3_batch_execution.py | 页面 | （失败时无证据文件） |
| 19 | tools/verify_v2_4_4_candidate_blob.py | 页面 | （失败时无证据文件） |
| 20 | tools/verify_v2_5_1_deterministic_review.py | 页面 | （失败时无证据文件） |
| 21 | tools/verify_v2_5_2_vlm_review.py | 页面 | evals/product-v2/v2.5.2-vlm-review-*.json（txt 见日志内嵌） |
| 22 | tools/verify_v2_5_3_compare_panel.py | 页面 | evals/product-v2/v2.5.3-compare-panel-*.json |
| 23 | tools/verify_v2_5_4_rework_loop.py | 页面 | evals/product-v2/v2.5.4-rework-loop-*.json |
| 24 | tools/verify_v2_5_5_suite_review.py | 页面 | evals/product-v2/v2.5.5-suite-review-*.txt/.json |
| 25 | tools/verify_v2_6_1_selection.py | 页面 | （失败时无证据文件） |
| 26 | tools/verify_v2_6_2_delivery.py | 页面 | evals/product-v2/v2.6.2-delivery-*.txt/.json + evidence/*.png |
| 27 | tools/verify_v2_6_3_project_transfer.py | 页面 | evals/product-v2/v2.6.3-transfer-*.txt/.json + evidence/*.png |
| 28 | tools/verify_v2_6_4_accessibility.py | 页面 | （失败时无证据文件） |
| 29 | tools/verify_v2_r5_2_two_adapters.py | 页面 | （失败时无证据文件） |
| 30 | tools/verify_v2_ui_2_interaction_visual.py | 页面 | （失败时无证据文件） |
| 31 | tools/verify_v2_ui_3_frontend.py | 页面 | （失败时无证据文件） |
| 32 | tools/verify_v2_packet08_settings_vision.py | 页面 | evals/product-v2/refactor/p11r{1,2}.json（`--label p11rN` 定名） |
| 33 | tools/verify_v2_packet08_adoption_ai.py | 页面 | evals/product-v2/refactor/p11r{1,2}.json（同名覆盖，见注） |
| 34 | tools/verify_v2_packet08_delivery_ai.py | 页面 | evals/product-v2/refactor/p11r{1,2}.json（同名覆盖，见注） |

注：packet08 三件套 `--label` 决定证据文件名；本轮三者同用 `p11r1/p11r2` 故同名覆盖，
各自轮次的 PASS 行以 `_working/p11regression/logs/verify_v2_packet08_*.rN.log` 为准
（settings-vision 12/12、adoption-ai 11/11、delivery-ai 16/16，两轮一致）。

排除（4 个，不跑；理由）：

| 验证器 | 排除理由 |
|---|---|
| tools/verify_v2_4_5_live_reference.py | 付费真实链：`--live` + `DASHSCOPE_API_KEY` 才执行真实生图调用；默认退出 2 且不产证据（本轮硬边界禁真实调用/付费）。 |
| tools/verify_v2_volc_adopt_export.py | 付费真实链：`--live` + `ARK_API_KEY` + `AMZ_V2_DEFAULT_TRIAL=open` + 预算预检才执行火山同步生图（¥0.12/次）；缺一即 exit 2 零外呼（本轮禁付费）。 |
| tools/verify_v2_ui_1_remote_entry.py | 远程部署验证器：默认打真实远端 `https://47.115.172.233:8080` + Chrome/Edge 通道，需要部署后授权；本地离线跑不了，不代表本地失败。 |
| tools/verify_v2_7_1_regression.py | 元聚合器：读取 CI verify job 再把全部命令跑两轮（含自身会递归）；本片就是它要做的两轮离散跑，直接跑它等于把 34 项塞进一个黑盒且锁文件互斥，不符合逐条定性要求。 |

