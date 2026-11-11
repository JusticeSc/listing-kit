<!-- 拆分件 02/03 · 父文档 evals/product-v2/refactor/packet11-regression-rounds-20261007T101243Z.md -->
# 2. 总表：验证器 × 第1轮 × 第2轮 × 定性 × 证据
[返回 packet11-regression-rounds-20261007T101243Z.md](packet11-regression-rounds-20261007T101243Z.md)

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

