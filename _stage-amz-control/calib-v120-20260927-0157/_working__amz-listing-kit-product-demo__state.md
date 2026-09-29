# amz-listing-kit 完整演示产品执行状态

> CONTROL-STATUS: current · AUTHORITY: execution-state  
> 这里只保存进度、证据指针、阻塞和唯一下一动作。目标、阶段、Gate、任务定义与依赖只在
> `docs/product-demo-goal-and-implementation-plan.md` 维护；本文件中的 ID 都是对计划的外键。

```yaml
state_schema: amz-project-state/v2
task_id: amz-listing-kit-product-demo
status: active
goal_binding: required
goal_id: 01a0ca17-2179-7eb0-969a-af9c79c4d8ca
system_goal_observed_status: active
system_goal_observed_at: 2026-09-27T00:43:49+08:00
plan_ref: docs/product-demo-goal-and-implementation-plan.md
latest_audit: evals/product-demo/control-plane-recalibration-2026-09-27.md

phase_progress:
  "-1":
    status: done
    evidence:
      - evals/product-demo/goal-resume-2026-09-24.md
  "0":
    status: done
    evidence:
      - evals/product-demo/d0-8-g0-audit-2026-09-25.md
  "1":
    status: done
    evidence:
      - evals/product-demo/d1-4-first-round-2026-09-26.md
      - evals/product-demo/control-plane-single-authority-2026-09-26.md
      - evals/product-demo/d1-p1-processing-contracts-2026-09-26.md
      - evals/product-demo/d1-p2-front-chain-contracts-2026-09-26.md
      - evals/product-demo/control-plane-recalibration-2026-09-26.md
      - evals/product-demo/d1-p3-back-chain-contracts-2026-09-26.md
      - evals/product-demo/control-plane-recalibration-2026-09-26b.md
      - evals/product-demo/d1-r1-fact-capability-matrix.md
      - evals/product-demo/d1-r2-route-comparison-2026-09-26.md
      - evals/product-demo/control-plane-recalibration-2026-09-26c.md
      - evals/product-demo/d1-r3-verifier-registry-2026-09-26.md
      - evals/product-demo/control-plane-recalibration-2026-09-26d.md
      - evals/product-demo/d1-r4-g1-adjudication-2026-09-26.md
      - evals/product-demo/d1-p4-swap-probe-2026-09-26.md
      - evals/product-demo/d1-p4-swap-probe-2026-09-26b.md
      - evals/product-demo/control-plane-recalibration-2026-09-26e.md
      - evals/product-demo/control-plane-recalibration-2026-09-26f.md
  "2":
    status: active
    evidence:
      - evals/product-demo/d2-r1-offline-tracer-2026-09-26.md
      - evals/product-demo/control-plane-recalibration-2026-09-26g.md
      - evals/product-demo/d2-r2a-brief-and-preflight-2026-09-26.md
      - evals/product-demo/d2-r2a-failure-paths-2026-09-26.md
      - _working/amz-listing-kit-product-demo/implementation-plan-2026-09-26.md
      - evals/product-demo/business-model-and-current-state-audit-2026-09-26.md
      - evals/product-demo/control-plane-recalibration-2026-09-26h.md
      - evals/product-demo/d2-r1c/mock-product-2026-09-26.md
      - evals/product-demo/d2-r2a-single-page-brief-2026-09-27.md
      - evals/product-demo/control-plane-recalibration-2026-09-27.md

task_progress:
  D-1.1:
    status: done
    evidence: [evals/product-demo/pre-goal-readiness-2026-09-24.md]
  D-1.2:
    status: done
    evidence: [evals/product-demo/pre-goal-readiness-2026-09-24.md]
  D-1.3:
    status: done
    evidence: [evals/v2_baseline_manifest.json]
  D-1.4:
    status: done
    evidence: [evals/product-demo/goal-resume-2026-09-24.md]
  D0.1:
    status: done
    evidence: [evals/product-demo/fixture-design/d0-1-selection.md]
  D0.2:
    status: done
    evidence: [evals/product-demo/d0-2-freeze-2026-09-24.md]
  D0.3:
    status: done
    evidence: [evals/product-demo/d0-3-factcard-2026-09-24.md]
  D0.4:
    status: done
    evidence: [evals/product-demo/d0-4-verifier-2026-09-25.md]
  D0.5:
    status: done
    evidence: [evals/product-demo/d0-5-driver-2026-09-25.md]
  D0.6:
    status: done
    evidence: [evals/product-demo/d0-6-negative-2026-09-25.md]
  D0.7:
    status: done
    evidence: [evals/product-demo/d0-7-second-product-2026-09-25.md]
  D0.8:
    status: done
    evidence: [evals/product-demo/d0-8-g0-audit-2026-09-25.md, evals/product-demo/design-rebaseline-2026-09-26.md]
  D1.1:
    status: done
    evidence: [evals/product-demo/d1-1-contract-2026-09-26.md]
  D1.2:
    status: done
    evidence: [evals/product-demo/d1-2-i2i-adapter-2026-09-26.md]
  D1.3:
    status: done
    evidence: [evals/product-demo/d1-2-i2i-adapter-2026-09-26.md]
  D1.4:
    status: done
    evidence: [evals/product-demo/d1-4-first-round-2026-09-26.md]
  D1.5:
    status: done
    evidence: [evals/product-demo/d1-4-first-round-2026-09-26.md]
  D1.C1:
    status: done
    evidence: [evals/product-demo/control-plane-single-authority-2026-09-26.md]
  D1.C2:
    status: blocked
    evidence: []
  D1.P1:
    status: done
    evidence: [evals/product-demo/d1-p1-processing-contracts-2026-09-26.md]
  D1.P2:
    status: done
    evidence: [evals/product-demo/d1-p2-front-chain-contracts-2026-09-26.md]
  D1.P3:
    status: done
    evidence: [evals/product-demo/d1-p3-back-chain-contracts-2026-09-26.md]
  D1.R1:
    status: done
    evidence: [evals/product-demo/d1-r1-fact-capability-matrix.md]
  D1.R2:
    status: done
    evidence: [evals/product-demo/d1-r2-route-comparison-2026-09-26.md]
  D1.R3:
    status: done
    evidence: [evals/product-demo/d1-r3-verifier-registry-2026-09-26.md, evals/product-demo/control-plane-recalibration-2026-09-26d.md]
  D1.R4:
    status: done
    evidence: [evals/product-demo/d1-r4-g1-adjudication-2026-09-26.md]
  D1.P4:
    status: done
    evidence: [evals/product-demo/d1-p4-swap-probe-2026-09-26.md, evals/product-demo/d1-p4-swap-probe-2026-09-26b.md]
  D2.R1:
    status: done
    evidence: [evals/product-demo/d2-r1-offline-tracer-2026-09-26.md]
  D2.R1b:
    status: done
    evidence:
      - evals/product-demo/d2-r1b/frontend-definition-2026-09-26.md
      - evals/product-demo/d2-r1b/workbench-definition-2026-09-26.html
      - evals/product-demo/d2-r1b/product-owner-proceed-2026-09-26.md
  D2.R1c:
    status: active
    evidence:
      - evals/product-demo/d2-r1c/mock-product-2026-09-26.md
  D2.R2:
    status: pending
    evidence:
      - evals/product-demo/d2-r2a-brief-and-preflight-2026-09-26.md
      - evals/product-demo/d2-r2a-single-page-brief-2026-09-27.md

next_action_task: D2.R1c
blockers:
  - v2_baseline_refresh_waiting_for_full_regression_memory_gate
unknowns:
  - r2a_brief_v2_landing_check_is_source_level_rendered_steps_only_rehearsed
  - mock_reset_race_fixed_other_combined_action_sequences_not_probed
  - keyboard_run_typed_ascii_ime_composition_still_unverified
  - r2a_brief_v2_must_be_rechecked_after_fe08_if_ui_text_changes
  - delivery_validity_interpretation_uses_prompt_text_equality_pending_walkthrough
  - mock_has_no_cost_budget_model_budget_blocking_appears_only_in_phase4
  - D2_R1c_product_owner_walkthrough_FE08_pending
  - scene_candidates_have_no_machine_fact_owner_after_D1_R2
  - human_only_fact_chain_in_real_path_must_become_per_fact_ui_step
  - review_items_not_yet_consumed_by_local_product
  - refcond_vlm_unknowns_cluster_on_F6
  - segmentation_quality_has_no_ground_truth_probe
  - back_half_verified_on_single_shot_batch_only
  - real_uninvolved_user_for_phase2_not_yet_arranged
  - P4_real_product_requires_user_supplied_material_and_is_deferred
  - phase3_to_5_implementation_shape_is_proposed_until_phase2_walkthrough
  - contract_report_bytes_not_reproducible
  - run_manifest_stores_absolute_paths_not_portable
  - shot_templates_are_processing_layer_defaults_not_data
  - d1r2_generated_artifacts_regenerated_bytes_not_comparable
  - reference_pack_manifest_duplicates_fact_card_pointer
  - offline_session_state_is_in_memory_only
  - current_tracer_and_static_workbench_prototypes_were_rejected_as_business_model_projection
  - offline_judge_scope_is_project_directory
  - d2r2_brief_written_by_developers_can_leak_developer_vocabulary
  - pre_rehearsal_proves_landing_points_not_comprehension
  - offline_entry_requires_nine_file_pack_bex02_is_not_complete
updated_at: 2026-09-27T00:43:49+08:00
```
