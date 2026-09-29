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
system_goal_observed_at: 2026-09-26T22:33:29+08:00
plan_ref: docs/product-demo-goal-and-implementation-plan.md
latest_audit: evals/product-demo/control-plane-recalibration-2026-09-26h.md

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
    status: pending
    evidence: []
  D2.R1c:
    status: pending
    evidence: []
  D2.R2:
    status: pending
    evidence: []

next_action_task: D2.R1b
blockers:
  - v2_baseline_refresh_waiting_for_full_regression_memory_gate
unknowns:
  - front_end_interaction_contract_FE01_to_FE04_not_yet_frozen
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
  - single_page_region_and_action_contract_not_yet_frozen
  - offline_judge_scope_is_project_directory
  - d2r2_brief_written_by_developers_can_leak_developer_vocabulary
  - pre_rehearsal_proves_landing_points_not_comprehension
  - offline_entry_requires_nine_file_pack_bex02_is_not_complete
updated_at: 2026-09-26T22:33:29+08:00
```
