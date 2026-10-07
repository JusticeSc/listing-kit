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

## 2. 总表：验证器 × 第1轮 × 第2轮 × 定性 × 证据

命令形如 `uv run --locked python tools/<name>.py --label p11r1` / `--label p11r2`。
证据路径为仓库相对路径；`-p11r1` = 第1轮，`-p11r2` = 第2轮。
`RC` = 进程退出码（由日志落盘方式取得，非管道截断值）。

| 验证器 | 第1轮 | 第2轮 | 定性 | 证据文件 |
|---|---|---|---|---|
| 1_1_indexeddb | RC=1：harness 无结果（120s 超时，`__V2_STORAGE_RESULTS__` 永不落定） | RC=1：同左 | 真红（产品缺陷，见§4-A） | 无本轮证据文件（中断在落盘前）；日志 `_working/p11regression/logs/v11.rN.log` |
| 1_2_project_home | RC=0 全过 | RC=0 全过 | 真绿 | evals/product-v2/v2.1.2-project-home-20261007-175314-p11r1.txt / …-180444-p11r2.txt（同名 .json） |
| 1_3_project_package | RC=0 全过 | RC=0 全过 | 真绿 | evals/product-v2/v2.1.3-project-package-20261007-175325-p11r1.txt / …-180453-p11r2.txt（同名 .json） |
| 1_4_formal_entry | RC=0 全过 | RC=0 全过 | 真绿 | evals/product-v2/v2.1.4-formal-entry-20261007-175330-p11r1.txt / …-180457-p11r2.txt（同名 .json） |
| 2_1_product_contracts | RC=0 全过 | RC=0 全过 | 真绿 | evals/product-v2/v2.2.1-product-contracts-20261007-175352-p11r1.txt / …-180517-p11r2.txt（同名 .json） |
| 2_2_semantic_provider | RC=0（10/10） | RC=0（10/10） | 真绿 | evals/product-v2/v2.2.2-semantic-provider-20261007-175357-p11r1.txt / …-180522-p11r2.txt（同名 .json） |
| 2_3_intake_understanding | RC=0 全过 | RC=0 全过 | 真绿 | evals/product-v2/v2.2.3-intake-understanding-20261007-175401-p11r1.txt / …-180527-p11r2.txt（同名 .json） |
| 2_4_category_generality | RC=0（2/2 + 3 SKIP，需 `--live`） | RC=0（同左） | 真绿（离线部分；C2–C4 按设计 SKIP，非失败） | evals/product-v2/v2.2.4-category-generality-20261007-175358-p11r1.txt / …-180523-p11r2.txt（同名 .json） |
| 3_1_suite_registry | RC=0 全过 | RC=0 全过 | 真绿 | evals/product-v2/v2.3.1-suite-registry-20261007-175417-p11r1.txt / …-180541-p11r2.txt（同名 .json） |
| 3_2_suite_editor | RC=0 全过 | RC=0 全过 | 真绿 | evals/product-v2/v2.3.2-suite-editor-20261007-175421-p11r1.txt / …-180544-p11r2.txt（同名 .json） |
| 3_3_session_lifecycle | RC=0 全过 | RC=0 全过 | 真绿 | evals/product-v2/v2.3.3-session-lifecycle-20261007-175433-p11r1.json / …-180553-p11r2.json |
| 3_3_spec_versions | RC=0 全过 | RC=0 全过 | 真绿 | evals/product-v2/v2.3.3-spec-versions-20261007-175445-p11r1.txt / …-180605-p11r2.txt（同名 .json） |
| 3_4_prompt_compiler | RC=0 全过 | RC=0 全过 | 真绿 | evals/product-v2/v2.3.4-prompt-compiler-20261007-175456-p11r1.txt / …-180614-p11r2.txt（同名 .json） |
| 3_5_pre_generation_confirm | RC=1：`#confirm-action` 60s 等不到 enabled（异常中断，无证据） | RC=1：同左 | 已知过期（任务书点名 `-10`，见§3） | 无本轮证据文件；日志 `_working/p11regression/logs/v235.rN.log` |
| 3_6_prompt_manual_edit | RC=0 全过 | RC=0 全过 | 真绿 | evals/product-v2/v2.3.6-prompt-manual-edit-20261007-175620-p11r1.txt / …-180740-p11r2.txt（同名 .json） |
| 4_1_image_gateway | RC=1：仅 `V2.4.1-23` FAIL（32/33 PASS） | RC=1：同左（32/33 PASS，同一项） | 真红（脚本期望过期，见§4-B） | evals/product-v2/v2.4.1-image-gateway-20261007-175646-p11r1.txt / …-180758-p11r2.txt（同名 .json） |
| 4_2_generation_attempt | RC=1（-99/-15 FAIL，其余 PASS） | RC=0 全过 | flake（基础设施，见§5；两轮原始输出对照已留） | r1: evals/product-v2/v2.4.2-generation-attempt-20261007-175656-p11r1.txt/.json；r2: …-180806-p11r2.txt/.json(+.png) |
| 4_3_batch_execution | RC=1：`NameError: start_static_server`（零检查执行） | RC=1：同左 | 真红（脚本缺陷，见§4-C） | 无证据文件；日志 `_working/p11regression/logs/v243.r1.log`、`…/verify_v2_4_3_batch_execution.r2.log` |
| 4_4_candidate_blob | RC=1：`NameError: start_static_server`（零检查执行） | RC=1：同左 | 真红（脚本缺陷，同§4-C） | 无证据文件；日志 `_working/p11regression/logs/v244.r1.log`、`…/verify_v2_4_4_candidate_blob.r2.log` |
| 5_1_deterministic_review | RC=1：`NameError: current_review_contract`（零检查执行） | RC=1：同左 | 真红（脚本缺陷，见§4-D） | 无证据文件；日志 `_working/p11regression/logs/v251.r1.log`、`…/verify_v2_5_1_deterministic_review.r2.log` |
| 5_2_vlm_review | RC=0 全过 | RC=0 全过 | 真绿 | evals/product-v2/v2.5.2-vlm-review-20261007-175818p11r1.json / …-180828p11r2.json |
| 5_3_compare_panel | RC=0 全过（含 `-15` PASS） | RC=0 全过（含 `-15` PASS） | 真绿（已知过期项 `-15` 本轮 PASS，见§3） | evals/product-v2/v2.5.3-compare-panel-20261007-175827p11r1.json / …-180837p11r2.json |
| 5_4_rework_loop | RC=0 全过 | RC=0 全过 | 真绿 | evals/product-v2/v2.5.4-rework-loop-20261007-175838p11r1.json / …-180849p11r2.json |
| 5_5_suite_review | RC=0 全过 | RC=0 全过 | 真绿 | evals/product-v2/v2.5.5-suite-review-20261007-175849-p11r1.txt / …-180902-p11r2.txt（同名 .json） |
| 6_1_selection | RC=1：`ValueError: substring not found`（`check_static_guards` 找 `<section id="adopt-panel"` 失败，零检查执行） | RC=1：同左 | 真红（脚本期望过期，见§4-E） | 无证据文件；日志 `_working/p11regression/logs/v261.r1.log`、`…/verify_v2_6_1_selection.r2.log` |
| 6_2_delivery | RC=0 全过（13/13） | RC=0 全过 | 真绿 | evals/product-v2/v2.6.2-delivery-20261007-175955-p11r1.txt / …-180943-p11r2.txt（同名 .json + evidence/*.png） |
| 6_3_project_transfer | RC=0 全过（12/12） | RC=0 全过 | 真绿 | evals/product-v2/v2.6.3-transfer-20261007-180028-p11r1.txt / …-181016-p11r2.txt（同名 .json + evidence/*.png） |
| 6_4_accessibility | RC=1：`AttributeError: v2_verify_shared has no attribute 'fake_suite'`（2 项 PASS 后中断） | RC=1：同左 | 真红（脚本缺陷，见§4-F） | 无证据文件；日志 `_working/p11regression/logs/v264.r1.log`、`…/verify_v2_6_4_accessibility.r2.log` |
| r5_2_two_adapters | RC=1：`#prompt-editor` hidden（`to_be_visible` 5s 断言失败） | RC=1：同左 | 真红（产品缺陷，见§4-G） | 无本轮证据文件；日志 `_working/p11regression/logs/r52.rN.log`（内含 aria 快照） |
| ui_2_interaction_visual | RC=1：`NameError: v251 is not defined`（零检查执行） | RC=1：同左 | 真红（脚本缺陷，见§4-H） | 无证据文件；日志 `_working/p11regression/logs/ui2.rN.log` |
| ui_3_frontend | RC=1：`NameError: start_server is not defined`（零检查执行） | RC=1：同左 | 真红（脚本缺陷，见§4-I） | 无证据文件；日志 `_working/p11regression/logs/ui3.rN.log` |
| packet08_settings_vision | RC=0（12/12；关闭日志尾部 `WinError 10038` 为 Windows 关闭时序噪音，不影响结论） | RC=0（12/12） | 真绿 | evals/product-v2/refactor/p11r1.json → 被后跑者覆盖；以日志 `verify_v2_packet08_settings_vision.{r1,r2}.log` 尾行 `RESULT PASS 12/12` 为准 |
| packet08_adoption_ai | RC=0（11/11） | RC=0（11/11） | 真绿 | 同上（`RESULT PASS 11/11`，日志为准） |
| packet08_delivery_ai | RC=0（16/16） | RC=0（16/16） | 真绿 | 同上（`RESULT PASS 16/16`，日志为准） |

汇总：真绿 22 / 已知过期 1（3_5）/ flake 1（4_2）/ 真红 10（1_1、4_1、4_3、4_4、5_1、6_1、6_4、r5_2、ui_2、ui_3）。

## 3. 已知过期场景（非新回归，单独列）

- 3_5 `-10`（改风格+重编译后确认单为"本次明确发送 0 张"，产品按"已有成功不自动重提"禁用确认）：
  本轮两轮都在 `#confirm-action` 永不 enabled 上 60s 超时中断（`v235.rN.log`），与任务书描述的"已知过期点位一致。
  未放宽断言、未重跑洗绿，判**已知过期**，仍计入"不能闭合"（§4-J），但不算新回归。
- 5_3 `-15`（落点期望已收窄为"按钮承诺的 targetShot"）：
  本轮两轮 `-15` 均为 PASS（单候选回退与"下一个待处理"正常），无失败可挂。
  记**真绿**，此处仅说明该已知点位本轮未复现、不掩盖其它项。

## 4. 不能闭合的项与原因（共 12 项：10 真红 + 1 已知过期 + 1 flake 未定）

- A. 1_1（产品缺陷，真红）：`tools/verify_v2_1_1_indexeddb.py` 自带 `StaticHandler.roots` 只放行
  `/storage/`、`/vendor/`、`/harness/`，但 `app/product_v2/storage/repository.js` 自 R5.1 packet 05
 （e90b196）起 `import … from "../domain/index.js"`，浏览器经 `/domain/index.js` 取 domain 时 404，
  `storage-contract.js` 模块加载失败、`__V2_STORAGE_RESULTS__` 永不落定，两轮 120s 超时。
  最小证据：`_working/p11regression/logs/v11.r1.log` 尾 `TimeoutError`；
  独立复现探针确认 `/domain/index.js → 404`、`storage/index.js → 200`（同目录日志说明）。
  修法方向（二选一）：验证器静态服加 `/domain/` 路由，或 harness 导入改相对路径；
  属下一片的修动作，本片只定性不定修。
- B. 4_1 `-23`（脚本期望过期，真红）：其余 32 项全 PASS，仅磁盘不变量 FAIL。
  `added` 全是 `src/providers/__pycache__/*.pyc`（CPython 在独立运行根内 import 产品包时生成），
  非业务落盘。断言把"解释器副产物"当"业务写盘"，在当前运行方式下恒红。
  最小证据：`evals/product-v2/v2.4.1-image-gateway-20261007-175646-p11r1.txt` 的 `-23` 行
  （r2 同文件 `-p11r2` 一致）。
- C. 4_3 / 4_4（脚本缺陷，真红）：`from v2_verify_shared import (png_bytes, load_server_module,
  free_port, run_entry, read_suite, compile_all,)` 未引入 `start_static_server`，
  却在 `main` 直接调用裸名 `start_static_server()`（4_3:278、4_4:333；4_2 同位置用的是
  `shared.start_static_server()` 故不中招）。`NameError` 在第一扇区即中断，零检查执行。
  最小证据：`_working/p11regression/logs/v243.r1.log`、`v244.r1.log` 全文 8 行。
- D. 5_1（脚本缺陷，真红）：`main` 第 96 行调用裸名 `current_review_contract()`，
  但 `from v2_verify_shared import` 清单无此名（函数在 shared 第 42 行存在，
  且 5_3 用 `shared.current_review_contract()` 正常）。`NameError` 即时中断，零检查执行。
  最小证据：`_working/p11regression/logs/v251.r1.log` 全文 6 行。
- E. 6_1（脚本期望过期，真红）：`check_static_guards` 用 `html.index('<section id="adopt-panel"')`
  做源码存在性断言，当前 workspace 主链 HTML 已无该 section（采用面板结构迁移），
  `ValueError: substring not found` 在浏览器启动前即崩，零检查执行。
  最小证据：`_working/p11regression/logs/v261.r1.log` 全文 6 行。
- F. 6_4（脚本缺陷，真红）：第 160 行 `shared.fake_suite.FakeSuiteReviewProvider`，
  但 `v2_verify_shared` 无 `fake_suite` 属性（`FakeSuiteReviewProvider` 位于
  `src/providers/v2_fake_suite_review.py`）。`AttributeError` 中断，零检查执行。
  最小证据：`_working/p11regression/logs/v264.r1.log`（前有 2 项 PASS，后接 Traceback）。
- G. r5_2（产品缺陷，真红）：离线 E2E 在生成阶段 `expect(#prompt-editor).to_be_visible()`
  失败（实际 `hidden`）。aria 快照显示页面停在"生成前确认缺失或已过期：先回到「生成前确认」
  重新确认"，4 张图按钮均为 disabled——`#prompt-editor` 按产品逻辑收起，脚本仍按旧可见性假设断言。
  最小证据：`_working/p11regression/logs/r52.r1.log`（r2 逐字一致，`r52.r2.log`）。
  需按 §7.6 做机制↔现象对应（确认过期链 vs 脚本导航缺失），本片只定性不定修。
- H. ui_2（脚本缺陷，真红）：`run_workbench_checks` 用裸名 `v251.free_port()`，
  但文件内无 `import … as v251`（只有 `shared` 相关导入）。`NameError` 即时中断。
  最小证据：`_working/p11regression/logs/ui2.r1.log` 全文 11 行。
- I. ui_3（脚本缺陷，真红）：`main` 用裸名 `start_server("127.0.0.1", port)`，
  但文件内无此名（`shared.start_product_server` 存在）。`NameError` 即时中断。
  最小证据：`_working/p11regression/logs/ui3.r1.log` 全文 8 行。
- J. 3_5（已知过期，不计新回归但不能闭合）：见§3。两轮同错（60s 等待 `#confirm-action`
  enabled 超时），与任务书点名的 `-10` 过期一致；未改断言、未重跑。
- K. 4_2（flake，一轮红一轮绿，不能计绿）：r1 在 `-99/-15` FAIL（浏览器闭环中断 +
  console/page error 门连带红），r2 全 PASS。两轮原始输出对照见§5。
  按"约 2–5% flake 要刻画不要掩盖"，本片判 flake，不计入通过，需第三只眼看 r1 的 `-99`
  中断是否与 r5_2-G 同源（确认过期链）——留给修片，不在本片下结论。

## 5. flake 原始输出对照（4_2：r1 红 / r2 绿，未放宽断言）

- r1（红）：`evals/product-v2/v2.4.2-generation-attempt-20261007-175656-p11r1.json/.txt`，
  `- [FAIL] V2.4.2-99 浏览器闭环在完成前中断` +
  `- [FAIL] V2.4.2-15 零意外 console error / page error`，其余 28 项 PASS，`status: failed`。
- r2（绿）：`evals/product-v2/v2.4.2-generation-attempt-20261007-180806-p11r2.json/.txt(+.png)`，
  全部 31 项 PASS（含 `-19/-19b/-20/-21` 身份冻结链），`status: passed`。
- 对照说明：同一脚本、同一默认参数、同一串行条件，仅时间戳与 `--label` 不同；
  r1 的 `-99` 是"完成前中断"（异常冒泡），`-15` 是其连带门（中断本身产生 console/page 噪音），
  不是两个独立产品失败。r2 全绿证明产品链可走通，r1 中断的触发机制未定位——判基础设施 flake，
  不洗绿、不计通过。

## 6. 七闸门（逐条命令 + 退出码；产品文件本片零改动，闸门仅作基线留证）

| # | 命令 | 退出码 |
|---|---|---|
| 1 | `node --check app/product_v2/workspace.js` | 0 |
| 2 | `npm run build:frontend` | 0 |
| 3 | `npm run check:types` | 0 |
| 4 | `npm run check:generated` | 0 |
| 5 | `node --test evals/product-v2/node/*.test.mjs`（227 pass / 0 fail） | 0 |
| 6 | `uv run --locked python tools/check_project_state.py` | 0 |
| 7 | `uv run --locked python tools/check_docs.py --no-run` | 0 |

另：`uv run --locked python tools/check_verification.py`（非七闸门，附带）= 1，
`[FAIL] VCLASS_MISSING 未分类入口：tools/verify_v2_packet08_{adoption_ai,delivery_ai,settings_vision}.py`
—— packet08 三件套在 `config/product-v2/verification.json` 无登记。属控制面缺口，
与本轮 34 项结论无关，抛给下一片（登记或排除二选一），本片不修。

## 7. 每项一句话结论

- 1_1：真红——静态服缺 `/domain/` 路由，harness 模块 404，套件永不落定（产品侧修）。
- 1_2 / 1_3 / 1_4：真绿，两轮全过。
- 2_1 / 2_2 / 2_3：真绿，两轮全过。
- 2_4：真绿（离线 C1+C5；C2–C4 按设计 SKIP，需 `--live` 不属本轮）。
- 3_1 / 3_2 / 3_3-lc / 3_3-sv / 3_4：真绿，两轮全过。
- 3_5：已知过期（`-10`），两轮同错，非新回归但不能闭合。
- 3_6：真绿，两轮全过。
- 4_1：真红——32/33 PASS，仅 `-23` 把 `__pycache__` 当业务落盘（脚本期望过期）。
- 4_2：flake——r1 红（-99 中断连带 -15）/ r2 全绿，不计通过，需定位中断机制。
- 4_3 / 4_4：真红——`start_static_server` 裸名未导入，零检查执行（脚本缺陷）。
- 5_1：真红——`current_review_contract` 裸名未导入，零检查执行（脚本缺陷）。
- 5_2 / 5_3 / 5_4 / 5_5：真绿，两轮全过（5_3 的已知 `-15` 本轮 PASS）。
- 6_1：真红——静态守卫找已不存在的 `<section id="adopt-panel"`（脚本期望过期）。
- 6_2 / 6_3：真绿，两轮全过。
- 6_4：真红——`shared.fake_suite` 属性不存在（脚本缺陷）。
- r5_2：真红——`#prompt-editor` hidden 与脚本可见性假设冲突（确认过期链，需 §7.6 对应）。
- ui_2：真红——`v251` 裸名未定义（脚本缺陷）。
- ui_3：真红——`start_server` 裸名未定义（脚本缺陷）。
- packet08 三件套：真绿，两轮 12/11/16 全过（证据文件名被覆盖，以各轮日志尾行为准）。

## 8. 复核指引（给下一片，不在本片执行）

- 原始日志：`_working/p11regression/logs/`（不提交，复核时本地看）。
- 各验证器自带证据路径见§2 总表；失败中断型的"无证据文件"本身就是结论的一部分
  （中断在落盘前），对应日志已留最小 Traceback。
- 不得重跑洗绿：§4 每项的 RC 与 Traceback 是定性依据；修完后按包 11 第二片规程重跑两轮，
  本文件结论不追改。
