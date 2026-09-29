# amz-listing-kit Product V1 执行状态

> CONTROL-STATUS: superseded · AUTHORITY: historical-execution-state
> 已被 `_working/amz-listing-kit-product-v2/state.md` 取代；保留 Product V1 到 D4.12 的证据位置，不再据此继续 D4.13。
> 这里只保存进度、证据指针、阻塞和唯一下一动作。目标、阶段、Gate、任务定义与依赖只在
> `docs/product-demo-goal-and-implementation-plan.md` 维护；本文件中的 ID 都是对计划的外键。

```yaml
state_schema: amz-project-state/v2
task_id: amz-listing-kit-product-demo
status: superseded
goal_binding: required
goal_id: 01a0ca17-2179-7eb0-969a-af9c79c4d8ca
system_goal_observed_status: active
system_goal_observed_at: 2026-09-29T11:10:20+08:00
plan_ref: docs/product-demo-goal-and-implementation-plan.md
latest_audit: evals/product-demo/pre-goal-readiness-v2.6-2026-09-29.md

phase_progress:
  "-1":
    status: done
    evidence:
      - evals/product-demo/control-plane-recalibration-2026-09-28.md
      - evals/product-demo/control-plane-activation-2026-09-28.md
      - evals/product-demo/control-plane-calibration-v2.3-2026-09-28.md
  "0":
    status: done
    evidence:
      - evals/product-demo/control-plane-activation-2026-09-28.md
      - evals/product-demo/control-plane-calibration-2026-09-28-followup.md
      - evals/product-demo/control-plane-calibration-v2.3-2026-09-28.md
      - evals/product-demo/d0.1-contracts-2026-09-28.md
      - evals/product-demo/d0.2-workspace-store-2026-09-28.md
      - evals/product-demo/d0.3-application-service-2026-09-28.md
      - evals/product-demo/d0.4-d0.5-workspace-vertical-slice-2026-09-28.md
  "1":
    status: done
    evidence:
      - evals/product-demo/d1.1-semantic-provider-2026-09-28.md
      - evals/product-demo/d1.2-product-brief-2026-09-28.md
      - evals/product-demo/d1.3-plan-2026-09-28.md
      - evals/product-demo/d1.4-prompt-compile-2026-09-28.md
      - evals/product-demo/d1.5-plan-workspace-2026-09-28.md
      - evals/product-demo/d1.6-input-driven-probe-2026-09-28.md
      - evals/product-demo/d1.6-input-driven-probe-raw-2026-09-28.json
  "2":
    status: done
    evidence:
      - evals/product-demo/d2.1-image-provider-2026-09-28.md
      - evals/product-demo/d2.2-attempt-reconcile-2026-09-28.md
      - evals/product-demo/d2.3-batch-executor-2026-09-28.md
      - evals/product-demo/d2.4-generation-ui-2026-09-28.md
  "3":
    status: done
    evidence:
      - evals/product-demo/d3.6-export-wording-drift-2026-09-28.md
      - evals/product-demo/d3.1-d3.5-real-loop-2026-09-28.md
      - evals/product-demo/d3.1-d3.5-real-loop-2026-09-28.json
      - evals/product-demo/d3-detail-prompt-edit-2026-09-28.json
      - evals/product-demo/d3.1-selection-2026-09-28.md
      - evals/product-demo/d3.2-rework-2026-09-28.md
      - evals/product-demo/d3.3-platform-checks-2026-09-28.md
      - evals/product-demo/d3.4-export-2026-09-28.md
      - evals/product-demo/d3.5-real-loop-2026-09-28.md
      - evals/product-demo/real-ui-full-loop-2026-09-28/20260928-231918-summary.md
      - evals/product-demo/real-ui-2026-09-28/report.json
      - evals/product-demo/ui-rework-20260928-220838.json
  "4":
    status: superseded
    evidence:
      - evals/product-demo/d4.1-launcher-and-doctor-2026-09-28.md
      - evals/product-demo/d4.2-usability-accessibility-2026-09-28.md
      - evals/product-demo/d4.3-clean-install-backup-restore-2026-09-28.md
      - evals/product-demo/d4.4-frontend-contract-snapshot-2026-09-29.md
      - evals/product-demo/d4.5-workspace-shell-2026-09-29.md
      - evals/product-demo/d4.6-intake-vertical-slice-2026-09-29.md
      - evals/product-demo/d4.7-suite-command-2026-09-29.md
      - evals/product-demo/d4.8-generation-recovery-2026-09-29.md
      - evals/product-demo/d4.9-review-workbench-2026-09-29.md
      - evals/product-demo/d4.10-two-phase-rework-2026-09-29.md
      - evals/product-demo/d4.11-delivery-checks-2026-09-29.md
      - evals/product-demo/d4.12-product-regression-2026-09-29.md
      - evals/product-demo/d4.12-regression-20260929-141908.json

task_progress:
  D-1.1:
    status: done
    evidence:
      - evals/product-demo/control-plane-recalibration-2026-09-28.md
      - evals/product-demo/control-plane-calibration-v2.3-2026-09-28.md
  D-1.2:
    status: done
    evidence:
      - evals/product-demo/control-plane-activation-2026-09-28.md
  D-1.3:
    status: done
    evidence:
      - evals/product-demo/control-plane-activation-2026-09-28.md
  D0.1:
    status: done
    evidence:
      - evals/product-demo/d0.1-contracts-2026-09-28.md
  D0.2:
    status: done
    evidence:
      - evals/product-demo/d0.2-workspace-store-2026-09-28.md
  D0.3:
    status: done
    evidence:
      - evals/product-demo/d0.3-application-service-2026-09-28.md
  D0.4:
    status: done
    evidence:
      - evals/product-demo/d0.4-d0.5-workspace-vertical-slice-2026-09-28.md
  D0.5:
    status: done
    evidence:
      - evals/product-demo/d0.4-d0.5-workspace-vertical-slice-2026-09-28.md
  D1.1:
    status: done
    evidence:
      - evals/product-demo/d1.1-semantic-provider-2026-09-28.md
      - evals/product-demo/arrears-error-surface-2026-09-28.md
      - tools/verify_semantic_provider.py
  D1.2:
    status: done
    evidence:
      - evals/product-demo/d1.2-product-brief-2026-09-28.md
  D1.3:
    status: done
    evidence:
      - evals/product-demo/d1.3-plan-2026-09-28.md
  D1.4:
    status: done
    evidence:
      - evals/product-demo/d1.4-prompt-compile-2026-09-28.md
  D1.5:
    status: done
    evidence:
      - evals/product-demo/d1.5-plan-workspace-2026-09-28.md
  D1.6:
    status: done
    evidence:
      - evals/product-demo/d1.6-input-driven-probe-2026-09-28.md
      - evals/product-demo/d1.6-input-driven-probe-raw-2026-09-28.json
  D1.7:
    status: done
    evidence:
      - evals/product-demo/d1.7-reference-conflict-guard-2026-09-28.md
      - tools/verify_product_v1_conflict_guard.py
  D1.8:
    status: done
    evidence:
      - evals/product-demo/d1.8-generation-isolation-and-user-wording-2026-09-28.md
      - tools/verify_product_v1_generation_isolation.py
      - tools/verify_product_v1_conflict_guard.py
      - evals/product-demo/real-ui-full-loop-2026-09-28/20260928-231918-report.json
  D2.1:
    status: done
    evidence:
      - evals/product-demo/d2.1-image-provider-2026-09-28.md
      - evals/product-demo/arrears-error-surface-2026-09-28.md
      - tools/verify_dashscope_image_provider.py
  D2.2:
    status: done
    evidence:
      - evals/product-demo/d2.2-attempt-reconcile-2026-09-28.md
  D2.3:
    status: done
    evidence:
      - evals/product-demo/d2.3-batch-executor-2026-09-28.md
  D2.4:
    status: done
    evidence:
      - evals/product-demo/d2.4-generation-ui-2026-09-28.md
  D2.5:
    status: done
    evidence:
      - evals/product-demo/d2.5-real-generation-2026-09-28.md
      - evals/product-demo/d2.5-real-generation-2026-09-28.json
      - evals/product-demo/d2.5-transport-fix-and-submit-probe-2026-09-28.md
  D3.1:
    status: done
    evidence:
      - evals/product-demo/d3.1-d3.5-real-loop-2026-09-28.md
      - evals/product-demo/d3.1-d3.5-real-loop-2026-09-28.json
      - evals/product-demo/d3.1-selection-2026-09-28.md
      - evals/product-demo/real-ui-2026-09-28/report.json
  D3.2:
    status: done
    evidence:
      - evals/product-demo/d3.1-d3.5-real-loop-2026-09-28.md
      - evals/product-demo/d3-detail-prompt-edit-2026-09-28.json
      - evals/product-demo/d3.2-rework-2026-09-28.md
      - evals/product-demo/ui-rework-20260928-220838.json
      - evals/product-demo/d3.2-real-rework-20260928-215505.json
  D3.3:
    status: done
    evidence:
      - evals/product-demo/d3.1-d3.5-real-loop-2026-09-28.json
      - evals/product-demo/d3.3-platform-checks-2026-09-28.md
  D3.4:
    status: done
    evidence:
      - evals/product-demo/d3.1-d3.5-real-loop-2026-09-28.json
      - evals/product-demo/d3.4-export-2026-09-28.md
      - evals/product-demo/real-ui-2026-09-28/report.json
  D3.5:
    status: done
    evidence:
      - evals/product-demo/d3.5-real-loop-2026-09-28.md
      - evals/product-demo/real-ui-full-loop-2026-09-28/20260928-231918-report.json
      - evals/product-demo/real-ui-full-loop-2026-09-28/20260928-231918-summary.md
      - evals/product-demo/d3.1-d3.5-real-loop-2026-09-28.md
      - evals/product-demo/d3.1-d3.5-real-loop-2026-09-28.json
      - evals/product-demo/d2.5-real-generation-real-run-02-2026-09-28.md
      - evals/product-demo/real-ui-2026-09-28/report.json
      - evals/product-demo/ui-rework-20260928-220838.json
  D3.6:
    status: done
    evidence:
      - evals/product-demo/d3.6-export-wording-drift-2026-09-28.md
      - tools/verify_product_v1_export_wording_drift.py
  D4.1:
    status: done
    evidence:
      - evals/product-demo/d4.1-launcher-and-doctor-2026-09-28.md
      - start_product.bat
      - evals/product-demo/arrears-error-surface-2026-09-28.md
  D4.2:
    status: done
    evidence:
      - evals/product-demo/d4.2-usability-accessibility-2026-09-28.md
      - evals/product-demo/d4.2-usability-accessibility-20260929-001831.json
      - tools/verify_product_v1_usability_accessibility.py
  D4.3:
    status: done
    evidence:
      - evals/product-demo/d4.3-clean-install-backup-restore-2026-09-28.md
      - tools/workspace_backup_restore.py
  D4.4:
    status: done
    evidence:
      - evals/product-demo/d4.4-frontend-contract-snapshot-2026-09-29.md
      - _stage-amz-control/product-v1-ui-before-d4.5-20260929/snapshot-manifest.json
  D4.5:
    status: done
    evidence:
      - evals/product-demo/d4.5-workspace-shell-2026-09-29.md
      - tools/verify_product_v1_ui.py
      - tools/verify_product_v1_http.py
  D4.6:
    status: done
    evidence:
      - evals/product-demo/d4.6-intake-vertical-slice-2026-09-29.md
      - evals/product-demo/d4.6-intake-vertical-slice-2026-09-29.json
      - tools/verify_product_v1_ui.py
      - tools/verify_product_v1_http.py
      - tools/verify_application_service.py
  D4.7:
    status: done
    evidence:
      - evals/product-demo/d4.7-suite-command-2026-09-29.md
      - evals/product-demo/d4.7-suite-command-ui-20260929-115825.json
      - evals/product-demo/d4.7-suite-command-ui-20260929-115825-generated.png
      - evals/product-demo/d4.7-suite-command-ui-20260929-115825-plan.png
      - tools/verify_product_v1_suite_command.py
      - tools/verify_product_v1_suite_command_ui.py
      - tools/verify_product_v1_ui.py
      - tools/verify_product_v1_usability_accessibility.py
  D4.8:
    status: done
    evidence:
      - evals/product-demo/d4.8-generation-recovery-2026-09-29.md
      - evals/product-demo/d4.8-generation-recovery-ui-20260929-124022.json
      - evals/product-demo/d4.8-generation-recovery-ui-20260929-124022-mixed.png
      - evals/product-demo/d4.8-generation-recovery-ui-20260929-124022-complete.png
      - tools/verify_product_v1_generation_recovery_ui.py
      - tools/verify_product_v1_image_generation.py
      - tools/verify_product_v1_ui.py
      - tools/verify_product_v1_ui_shot_retry.py

  D4.9:
    status: done
    evidence:
      - evals/product-demo/d4.9-review-workbench-2026-09-29.md
      - evals/product-demo/d4.9-review-workbench-20260929-130924.json
      - evals/product-demo/d4.9-review-workbench-20260929-130924.png
      - tools/verify_product_v1_review_workbench_ui.py
      - tools/verify_product_v1_selection_rework_export.py
      - tools/verify_product_v1_usability_accessibility.py
  D4.10:
    status: done
    evidence:
      - evals/product-demo/d4.10-two-phase-rework-2026-09-29.md
      - evals/product-demo/ui-rework-20260929-133726.json
      - evals/product-demo/ui-rework-20260929-133726-before.png
      - evals/product-demo/ui-rework-20260929-133726-after.png
      - evals/product-demo/d4.9-review-workbench-20260929-133741.json
      - evals/product-demo/d4.2-usability-accessibility-20260929-133802.json
      - evals/product-demo/d4.7-suite-command-ui-20260929-133831.json
      - evals/product-demo/d4.8-generation-recovery-ui-20260929-133803.json
      - evals/product-demo/ui-shot-retry-2026-09-29.json
      - tools/verify_product_v1_selection_rework_export.py
      - tools/verify_product_v1_ui_rework.py
  D4.11:
    status: done
    evidence:
      - evals/product-demo/d4.11-delivery-checks-2026-09-29.md
      - evals/product-demo/ui-delivery-20260929-135852.json
      - evals/product-demo/ui-delivery-20260929-135852-blocked.png
      - evals/product-demo/ui-delivery-20260929-135852-ready.png
      - evals/product-demo/ui-delivery-20260929-135852-exported.png
      - evals/product-demo/ui-rework-20260929-135915.json
      - evals/product-demo/d4.9-review-workbench-20260929-135948.json
      - evals/product-demo/d4.2-usability-accessibility-20260929-135948.json
      - tools/verify_product_v1_delivery_checks.py
      - tools/verify_product_v1_delivery_ui.py
      - tools/verify_product_v1_export_wording_drift.py
  D4.12:
    status: done
    evidence:
      - evals/product-demo/d4.12-product-regression-2026-09-29.md
      - evals/product-demo/d4.12-regression-20260929-141908.json
      - evals/product-demo/d4.12-regression-20260929-141908-pass1.json
      - evals/product-demo/d4.12-regression-20260929-141908-pass2.json
      - evals/product-demo/d4.12-entry-audit-20260929-142330.json
      - evals/product-demo/d4.12-relocation-20260929-142331.json
      - evals/product-demo/d4.2-usability-accessibility-20260929-142444.json
      - evals/product-demo/ui-delivery-20260929-142438.json
      - evals/product-demo/d4.9-review-workbench-20260929-142429.json
      - evals/product-demo/d4.8-generation-recovery-ui-20260929-142411.json
      - evals/product-demo/d4.7-suite-command-ui-20260929-142403.json
      - evals/product-demo/ui-rework-20260929-142357.json
      - tools/regress_product_v1.py

next_action_task: null
blockers: []
unknowns:
  - product_owner_reported_dashscope_recharged_2026-09-29_first_real_call_not_yet_made
  - real_model_calls_must_stay_minimal_per_product_owner_2026-09-29
  - uninvolved_first_time_user_for_C12_will_be_arranged_before_D4.13
  - real_ui_full_loop_harness_stale_selectors_verified_2026-09-29_save-intake_analyze-product_generate-plan_start-generation_absent_from_final_index_html_final_version_real_loop_evidence_comes_from_D4.13_human_session
  - d4.13_kickoff_pending_product_owner_decision_plan_A_first_user_real_vs_plan_B_owner_real_plus_fake_walkthrough_kit_at__working_amz-listing-kit-product-demo_tasks_d4.13-first-user-walkthrough-kit.md
updated_at: 2026-09-29T19:36:35+08:00
```
