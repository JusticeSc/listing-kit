# Product V2 定向重构执行状态

> CONTROL-STATUS: current · AUTHORITY: execution-state
> 只保存进度、证据、阻塞/未知与下一动作；目标和任务定义只在 `docs/product-v2-refactor-plan.md`。
> prepared 是未绑定新 Goal 的本地准备态，不是系统 paused。旧读数与完成记录只见 superseded 基线。
> 2026-10-05用户已正式启动并手动设置完整Goal；本会话真实工具读数为active，原生ID与计划§2.1/§16.3全文匹配。旧绑定/证据保留历史，受新合同影响及其依赖任务已一次重判；唯一下一动作是R4.3设置接线。首个产品写入前，同版本代表项目ZIP已由真实页面导出并在全新隔离origin导入打开，44份版本记录与5份资产身份逐项相等；证据见latest_audit及事前快照，不把64px合成图当图像质量/交付验收。

```yaml
state_schema: amz-project-state/v2
task_id: amz-listing-kit-product-v2-refactor
status: active
goal_binding: required
goal_id: "1599c9600ae01cb7"
goal_pending_reason: null
goal_binding_evidence: evals/product-v2/refactor/goal-observation-20261005-formal-start.json
system_goal_observed_status: active
system_goal_observed_at: '2026-10-05T02:44:33.539Z'
plan_ref: docs/product-v2-refactor-plan.md
latest_audit: evals/product-v2/refactor/config-and-credential-20261005.md
phase_progress:
  '0':
    status: done
    evidence:
    - evals/product-v2/refactor/control-preparation-20261001.md
  '1':
    status: done
    evidence:
    - evals/product-v2/refactor/development-cutover-20261001-143954.md
    - evals/product-v2/refactor/goal-session-confirmation-20261001-125600.md
    - evals/product-v2/refactor/baseline-and-boot-20261001-133400.md
    - evals/product-v2/refactor/recovery-and-r13-20261001-143134.md
    - evals/product-v2/refactor/goal-recovery-20261002.md
  '2':
    status: done
    evidence:
    - evals/product-v2/refactor/ui-baseline-20261001-chrome.md
    - evals/product-v2/refactor/reference-review-20261001.md
    - evals/product-v2/refactor/prototype-review-20261002.md
    - evals/product-v2/refactor/goal-recovery-20261002.md
  '3':
    status: done
    evidence:
    - evals/product-v2/refactor/session-lifecycle-20261002-r33-update.md
    - evals/product-v2/refactor/home-read-recovery-20261003.md
    - evals/product-v2/v2.3.3-session-lifecycle-20261003-025221-home-read-recovery-shutdown.json
  '4':
    status: active
    evidence:
    - evals/product-v2/refactor/effective-config-byok-20261003.md
    - evals/product-v2/refactor/execution-identity-package-20261003-072854.md
    - evals/product-v2/v2.4.5-live-reference-20261003-154157-r42-volcengine-run3.json
    - evals/product-v2/refactor/formal-start-20261005.json
  '5':
    status: pending
    evidence:
    - evals/product-v2/refactor/generation-module-20261003-084705.md
    - evals/product-v2/refactor/two-image-adapters-20261003-094600.md
    - evals/product-v2/refactor/prompt-confirmation-consistency-20261003-120238.md
    - evals/product-v2/PRODUCT-V2-R5.2-offline-e2e-20261003-154254.json
  '6':
    status: pending
    evidence:
    - evals/product-v2/refactor/intake-suite-ui-20261003-122229.md
    - evals/product-v2/refactor/compare-rework-selection-ui-20261003-123202.md
    - evals/product-v2/refactor/delivery-recovery-settings-ui-20261003-124930.md
    - evals/product-v2/refactor/storage-contract-review-20261003.md
    - evals/product-v2/refactor/product-design-audit-20261004.md
    - evals/product-v2/refactor/design-convergence-20261004.md
    - evals/product-v2/refactor/specification-consolidation-20261004.md
  '7':
    status: pending
    evidence:
    - evals/product-v2/refactor/completion-matrix-20261003-r74.md
    - evals/product-v2/refactor/completion-matrix-20261003-r74.json
task_progress:
  V2.R0.1:
    status: done
    evidence:
    - docs/product-v2-refactor-plan.md
    - docs/INDEX.md
    - docs/product-v2-project-context.md
    - _working/amz-listing-kit-product-v2-baseline/state.md
  V2.R0.2:
    status: done
    evidence:
    - evals/product-v2/refactor/control-preparation-20261001.md
    - tools/check_project_state.py
    - tools/refactor_resume.py
    - evals/probes/project_state.py
    - evals/probes/docs_index.py
  V2.R1.1:
    status: done
    evidence:
    - evals/product-v2/refactor/goal-binding-20261001-094520.md
    - evals/product-v2/refactor/goal-session-observation-20261001-121220.json
    - evals/product-v2/refactor/goal-session-confirmation-20261001-125600.md
    - evals/product-v2/refactor/goal-observation-20261002.json
    - evals/product-v2/refactor/goal-recovery-20261002.md
    - evals/product-v2/refactor/goal-observation-20261003-unattended-trigger.json
    - evals/product-v2/refactor/goal-observation-20261005-formal-start.json
  V2.R1.2:
    status: done
    evidence:
    - evals/product-v2/refactor/baseline-and-boot-20261001-095710.md
    - evals/product-v2/refactor/work-audit-20261001-103825.md
    - evals/product-v2/refactor/baseline-and-boot-20261001-133400.md
    - evals/product-v2/refactor/recovery-and-r13-20261001-143134.md
    - evals/product-v2/refactor/development-cutover-20261001-143954.md
  V2.R1.3:
    status: done
    evidence:
    - evals/product-v2/refactor/work-audit-20261001-103825.md
    - evals/product-v2/refactor/baseline-and-boot-20261001-133400.md
    - evals/product-v2/refactor/recovery-and-r13-20261001-143134.md
    - evals/product-v2/refactor/r13-smoke-20261001-143134.json
  V2.R2.1:
    status: done
    evidence:
    - evals/product-v2/refactor/ui-baseline-20261001-chrome.md
    - evals/product-v2/refactor/ui-baseline-20261001-chrome.json
    - evals/product-v2/refactor/background-automation-20261001.md
    - evals/product-v2/refactor/headless-export-20261001.json
    - evals/product-v2/refactor/headless-matrix-20261001.json
    - evals/product-v2/refactor/headless-package-integrity-20261001.json
  V2.R2.2:
    status: done
    evidence:
    - evals/product-v2/refactor/prototype-review-20261002.md
    - evals/product-v2/refactor/prototype-smoke-20261002.json
    - evals/product-v2/refactor/prototype-observations-20261002.json
    - evals/product-v2/refactor/goal-recovery-20261002.md
  V2.R2.3:
    status: done
    evidence:
    - evals/product-v2/refactor/reference-review-20261001.md
  V2.R3.1:
    status: done
    evidence:
    - evals/product-v2/refactor/frontend-selection-20261002.md
    - evals/product-v2/refactor/frontend-approval-20261002.json
    - package.json
    - package-lock.json
    - docs/product-v2-project-context.md
  V2.R3.2:
    status: done
    evidence:
    - evals/product-v2/refactor/verification-seams-20261002.md
    - evals/product-v2/v2.2.1-product-contracts-20261002-144142.txt
    - evals/product-v2/v2.1.3-project-package-20261002-144152.txt
    - evals/product-v2/v2.5.1-deterministic-review-20261002-144206-r32-seams.txt
    - evals/product-v2/v2.5.1-deterministic-review-20261002-144206-r32-seams.json
    - config/product-v2/verification.json
    - evals/product-v2/node/_gen.mjs
  V2.R3.3:
    status: done
    evidence:
    - evals/product-v2/refactor/session-lifecycle-20261002-r33-update.md
    - evals/product-v2/v2.3.3-session-lifecycle-20261002-231308-run2.json
    - evals/product-v2/v2.3.3-session-lifecycle-20261002-231354-run3.json
    - app/product_v2/session.js
    - tools/verify_v2_3_3_session_lifecycle.py
    - evals/product-v2/refactor/home-read-recovery-20261003.json
    - evals/product-v2/v2.3.3-session-lifecycle-20261003-025221-home-read-recovery-shutdown.json
    - evals/product-v2/v2.1.4-formal-entry-20261003-024816-home-read-recovery.json
    - evals/product-v2/v2.1.2-project-home-20261003-024837-home-read-recovery.json
    - evals/product-v2/refactor/home-diagnostic-smoke-20261003.json
  V2.R4.1:
    status: done
    evidence:
    - evals/product-v2/refactor/image-candidate-review-20261002.md
    - evals/product-v2/refactor/image-candidate-review-20261002-seedream.md
    - evals/product-v2/refactor/model-preflight-20261003.txt
  V2.R4.2:
    status: done
    evidence:
    - evals/product-v2/refactor/work-audit-20261003.md
    - evals/product-v2/refactor/model-preflight-20261003.txt
    - evals/product-v2/refactor/owner-decisions-20261003-index-volcengine.json
    - evals/product-v2/v2.4.5-live-reference-20261003-145223-r42-dashscope-run5.json
    - evals/product-v2/v2.4.5-live-reference-20261003-145223-r42-dashscope-run5.txt
    - evals/product-v2/v2.4.5-live-reference-20261003-145223.png
    - evals/product-v2/v2.4.5-live-reference-20261003-154157-r42-volcengine-run3.json
    - evals/product-v2/v2.4.5-live-reference-20261003-154157-r42-volcengine-run3.txt
    - evals/product-v2/v2.4.5-live-reference-20261003-154157.png
    - evals/product-v2/v2.4.5-live-reference-20261003-154037-r42-volcengine-run2.json
    - evals/product-v2/v2.4.5-live-reference-20261003-153732-r42-volcengine-run1.json
    - src/providers/v2_volcengine_image.py
    - tools/verify_v2_4_5_live_reference.py
    - _working/amz-listing-kit-product-v2/budget-ledger.json
  V2.R4.3:
    status: done
    evidence:
    - evals/product-v2/refactor/effective-config-byok-20261003.md
    - evals/product-v2/refactor/config-and-credential-20261005.md
    - evals/product-v2/v2.4.1-image-gateway-20261005-141712.txt
    - evals/product-v2/v2.2.2-semantic-provider-20261005-141538.txt
    - evals/product-v2/v2.5.1-deterministic-review-20261005-142343.txt
    - evals/product-v2/v2.5.2-vlm-review-20261005-142259.txt
    - evals/product-v2/v2.5.5-suite-review-20261005-141348.txt
    - evals/product-v2/v2.ui.3-frontend-20261005-150315.txt
    - evals/product-v2/v2.ui.3-frontend-20261005-150341-final.txt
    - src/providers/v2_credentials.py
    - src/providers/v2_outbound.py
    - app/product_v2_server.py
    - src/providers/v2_registry.py
    - .github/workflows/ci-cd.yml
    - .env.example
  V2.R4.4:
    status: pending
    evidence:
    - evals/product-v2/refactor/execution-identity-package-20261003-072854.md
    - evals/product-v2/v2.4.2-generation-attempt-20261003-072854-r44-identity.json
    - evals/product-v2/v2.4.2-generation-attempt-20261003-072854-r44-identity.txt
    - evals/product-v2/v2.4.1-image-gateway-20261003-072955-r44-identity.txt
    - evals/product-v2/v2.1.3-project-package-20261003-073227-r44-identity.txt
    - evals/product-v2/v2.4.2-generation-attempt-20261003-084647.json
    - evals/product-v2/v2.4.2-generation-attempt-20261003-084647.txt
    - evals/product-v2/v2.4.3-batch-suite-20261003-084705.json
    - evals/product-v2/v2.4.3-batch-suite-20261003-084705.txt
    - app/product_v2/domain/attempt.js
    - app/product_v2/workspace.js
    - app/product_v2_server.py
    - src/providers/v2_fake_image.py
    - src/providers/v2_fake_semantic.py
    - src/providers/v2_fake_review.py
    - src/providers/v2_fake_suite_review.py
  V2.R5.1:
    status: pending
    evidence:
    - evals/product-v2/refactor/generation-module-20261003-084705.md
    - app/product_v2/generation.js
    - app/product_v2/workspace.js
    - evals/product-v2/v2.4.2-generation-attempt-20261003-084647.json
    - evals/product-v2/v2.4.3-batch-suite-20261003-084705.json
    - evals/product-v2/v2.4.4-candidate-blob-20261003-085109.json
  V2.R5.2:
    status: pending
    evidence:
    - evals/product-v2/refactor/two-image-adapters-20261003-094600.md
    - evals/product-v2/PRODUCT-V2-R5.2-offline-e2e-20261003-094235.json
    - evals/product-v2/PRODUCT-V2-R5.2-batch-20261003-094246.png
    - evals/product-v2/PRODUCT-V2-R5.2-refresh-20261003-094249.png
    - src/providers/v2_volcengine_image.py
    - src/providers/v2_image.py
    - src/providers/v2_registry.py
    - src/providers/v2_outbound.py
    - app/product_v2/domain/attempt.js
    - app/product_v2/domain/candidate.js
    - app/product_v2/generation.js
    - config/product-v2/providers.json
    - config/product-v2/verification.json
    - .github/workflows/ci-cd.yml
    - .env.example
    - evals/product-v2/harness/attempt-contract.js
    - evals/product-v2/node/attempt-contract.test.mjs
    - tools/verify_v2_r5_2_two_adapters.py
    - evals/product-v2/v2.4.3-batch-suite-20261003-105401-r52-diagnosis.json
    - evals/product-v2/v2.4.3-batch-suite-20261003-105608-r52-helper-fix.json
    - evals/product-v2/PRODUCT-V2-R5.2-offline-e2e-20261003-105608.json
    - evals/product-v2/PRODUCT-V2-R5.2-offline-e2e-20261003-154254.json
    - evals/product-v2/v2.4.5-live-reference-20261003-154157-r42-volcengine-run3.json
    - evals/product-v2/v2.4.5-live-reference-20261003-154157-r42-volcengine-run3.txt
    - evals/product-v2/v2.4.5-live-reference-20261003-154157.png
  V2.R5.3:
    status: pending
    evidence:
    - evals/product-v2/refactor/r53-gateway-smoke-20261003.json
    - evals/product-v2/refactor/model-preflight-20261003.txt
    - evals/product-v2/refactor/prompt-confirmation-consistency-20261003-120238.md
    - evals/product-v2/PRODUCT-V2-R5.2-offline-e2e-20261003-120238.json
  V2.R6.1:
    status: pending
    evidence:
    - evals/product-v2/refactor/intake-suite-ui-20261003-122229.md
    - evals/product-v2/v2.2.3-intake-understanding-20261003-121735.txt
    - evals/product-v2/v2.3.2-suite-editor-20261003-121756.txt
    - evals/product-v2/v2.3.3-spec-versions-20261003-121811.txt
    - evals/product-v2/v2.3.3-session-lifecycle-20261003-121827.json
    - evals/product-v2/v2.3.4-prompt-compiler-20261003-121845.txt
    - evals/product-v2/v2.3.5-pre-generation-confirm-20261003-122120.txt
    - evals/product-v2/v2.3.6-prompt-manual-edit-20261003-122145.txt
    - evals/product-v2/PRODUCT-V2-R5.2-offline-e2e-20261003-122229.json
  V2.R6.2:
    status: pending
    evidence:
    - evals/product-v2/refactor/compare-rework-selection-ui-20261003-123202.md
    - evals/product-v2/v2.5.1-deterministic-review-20261003-122935.txt
    - evals/product-v2/v2.5.2-vlm-review-20261003-122952.txt
    - evals/product-v2/v2.5.3-compare-panel-20261003-123008.txt
    - evals/product-v2/v2.5.4-rework-loop-20261003-123054.txt
    - evals/product-v2/v2.5.5-suite-review-20261003-123125.txt
    - evals/product-v2/v2.6.1-selection-20261003-123145.txt
    - evals/product-v2/v2.6.4-a11y-20261003-123202.txt
  V2.R6.3:
    status: pending
    evidence:
    - evals/product-v2/refactor/delivery-recovery-settings-ui-20261003-124930.md
    - evals/product-v2/v2.6.2-delivery-20261003-124831.txt
    - evals/product-v2/v2.6.3-transfer-20261003-124930.txt
    - evals/product-v2/v2.6.4-a11y-20261003-123202.txt
    - evals/product-v2/refactor/product-design-audit-20261004.md
    - evals/product-v2/refactor/design-convergence-20261004.md
    - evals/product-v2/refactor/specification-consolidation-20261004.md
    - evals/product-v2/refactor/development-preparation-20261004.md
    - evals/product-v2/refactor/goal-start-blocked-20261005.json
  V2.R6.4:
    status: done
    evidence:
    - evals/product-v2/refactor/storage-contract-review-20261003.md
    - evals/product-v2/refactor/work-audit-20261003.md
    - evals/product-v2/refactor/storage-measurements-20261003.json
    - evals/product-v2/refactor/home-read-recovery-20261003.md
    - evals/product-v2/refactor/owner-decisions-20261003-index-volcengine.json
    - evals/product-v2/refactor/native-index-verification-20261003.json
    - evals/product-v2/v2.1.1-indexeddb-20261003-032509-native-latest-index.json
    - evals/product-v2/v2.1.3-project-package-20261003-032510-native-latest-index.json
    - evals/product-v2/v2.3.3-session-lifecycle-20261003-032515-native-latest-index.json
    - evals/product-v2/v2.1.4-formal-entry-20261003-032824-native-latest-index.json
  V2.R7.1:
    status: pending
    evidence:
    - evals/product-v2/refactor/full-verification-20261003-r71.md
    - evals/product-v2/v2.7.1-regression-20261003-r71f-final.txt
    - evals/product-v2/v2.7.1-regression-20261003-r71f-final.json
    - evals/product-v2/v2.2.2-semantic-provider-20261003-194132-r71-semlive.json
    - evals/product-v2/v2.5.2-review-live-20261003-194238r71-vlm.json
    - evals/product-v2/v2.4.5-live-reference-20261003-194526-r71-dashscope2.json
    - evals/product-v2/v2.4.5-live-reference-20261003-195600-r71-volc2.json
    - evals/product-v2/v2.4.5-live-reference-20261003-194502-r71-dashscope.json
    - _working/amz-listing-kit-product-v2/budget-ledger.json
  V2.R7.2:
    status: pending
    evidence: []
  V2.R7.3:
    status: pending
    evidence: []
  V2.R7.4:
     status: pending
     evidence:
     - evals/product-v2/refactor/completion-matrix-20261003-r74.md
     - evals/product-v2/refactor/completion-matrix-20261003-r74.json
     - evals/product-v2/v2.4.5-volc-adopt-export-20261003-222253.json
     - evals/product-v2/v2.4.5-volc-adopt-export-20261003-222140.json
     - tools/verify_v2_volc_adopt_export.py
     - config/product-v2/verification.json
next_action_task: V2.R4.4
blockers: []
unknowns:
  - historical_r74_closeout_volc_adopt_export_222253_pass_spent_1_15_of_5_image_8_of_8_matrix_CI_37136575625_deploy_24a3561_origin_https_47_115_172_233_8080_paid_online_probes_0_evidence_completion-matrix-20261003-r74_not_current_completion
  - historical_r71_regression_r71f_semlive_vlm_dashscope194526_volc195600_spent_0_91_of_5_evidence_full-verification-20261003-r71_not_current_G6_or_design_proof
  - historical_boot_and_formal_entry_intermittent_trigger_unproven_controlled_home_read_failure_and_readiness_windows_fixed_diagnostics_now_capture_stage_UI_and_independent_DB_follow_V2.R1.2_V2.R3.3_V2.R7.1_RC19
  - sync_image_protocol_links_result_bytes_to_single_submit_envelope_no_task_id_bytes_missing_after_refresh_requires_explicit_new_action_or_manual_review_implementation_covered_by_browser_E2E_and_node_A19
  - node_domain_suite_C09_frozen_identity_fixture_aligned_browser_and_node_R52-01_waiver_removed_verified_by_PRODUCT-V2-R5.2-offline-e2e-20261003-120238_follow_V2.R5.3
  - native_latest_index_production_path_measured_same_fixture_history_assets_OCC_and_roundtrip_verified_heap_sampling_lower_bound_cold_open_not_claimed_faster_pressure_download_not_verified_follow_V2.R6.4
  - UI3_save_state_wiring_restored_and_later_pass_exists_without_before_after_code_hash_attribution_follow_V2.R3.3_and_V2.R7.1
  - public_default_paid_profile_online_closed_default_trial_closed_no_key_no_upstream_verified_by_capabilities_and_400_probes_follow_V2.R4.3_V2.R7.4
  - vlm_detection_quality_uncalibrated_do_not_infer_accuracy_from_contract_pass
  - historical_triggered_unattended_Goal_binding_retained_current_20261004_goal_get_No_active_goal_not_new_binding_or_lifecycle_change_follow_plan_2_and_plan_13
  - design_20261004_draft_text_sketches_only_no_product_code_model_calls_commits_or_deployment_R61_R62_old_evidence_not_new_UI_acceptance_follow_design_convergence_20261004
  - product_choices_confirmed_existing_models_plus_own_key_AI_review_on_demand_and_export_allowed_without_AI_deterministic_reports_hard_checks_selection_and_integrity_still_required_follow_plan_13_14
  - specification_20261004_plan14_business_contract_UI_draft_and_context_responsibility_map_written_only_no_product_code_model_calls_or_release_no_new_Goal_follow_specification_consolidation_20261004
  - semantic_current_text_and_reference_metadata_only_reference_images_sent_false_qwen_vl_multimodal_transport_reusable_but_product_understanding_schema_and_consumers_missing_follow_plan_14_7
  - optional_AI_policy_requires_separating_suite_not_run_from_model_unknown_preserve_current_deterministic_reports_and_real_submission_unknown_no_auto_retry_follow_plan_14_8
  - historical_done_proofs_keep_original_scope_section14_new_acceptance_not_reassessed_recheck_affected_existing_tasks_when_implementation_authorized_no_new_task_table_follow_plan_14_10
  - implementation_batches_and_risk_based_minimal_verification_written_plan15_only_no_product_work_no_new_tasks_or_status_changes_resume_R63_requires_scope_and_actual_Goal_check
  - development_preparation_20261004_plan_r7_goal_draft_16_3_not_created_existing_binding_and_done_historical_only_reassess_affected_tasks_once_on_real_start_follow_plan_7_5_16_2
  - next_round_delivery_live_supplement_and_CI_protected_agent_merge_choices_confirmed_in_ask_preparation_does_not_execute_or_reset_budget_follow_plan_16_1
  - dependency_R62_now_R53_no_wait_for_R61_vision_completion_shared_config_existing_consumers_R43_new_vision_consumer_R61_final_G6_RC07_unchanged_scope_follow_plan_6_15
  - release_rollback_gap_previous_container_removed_before_HTTPS_page_acceptance_not_fixed_in_preparation_R74_must_implement_plan_7_7
  - startup_20261005_user_said_start_goal_runtime_unknown_tool_goal_and_xd_goal_get_goal_create_goal_not_mounted_no_current_system_read_no_creation_no_product_work_evidence_goal-start-blocked-20261005_json_historical_binding_unchanged
  - formal_start_20261005_goal_tool_restored_user_manual_goal_active_1599c9600ae01cb7_draft_exact_match_historical_missing_tool_block_resolved_no_duplicate_creation_follow_formal-start-20261005_json
  - r43_done_20261005_settings_consumers_closed_existing_purposes_formal_entry_browser_matrix_green_verifier_only_changes_no_product_semantics_node_10_failures_preexisting_R62_harness_not_this_round_follow_config-and-credential-20261005
  - affected_acceptance_reopened_R43_R44_R53_R61_R62_R63_R71_R74_and_dependency_status_R51_R52_keep_valid_proof_no_rebuild_Phase4_active_next_R43_same_version_ZIP_baseline_required_before_product_write
updated_at: '2026-10-05T07:40:17+00:00'
```
