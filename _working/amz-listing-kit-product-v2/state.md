# amz-listing-kit Product V2 执行状态

> CONTROL-STATUS: current · AUTHORITY: execution-state
> 这里只保存进度、证据指针、阻塞、未知和唯一下一动作。目标、范围、阶段、Gate、任务定义与依赖只在
> `docs/product-v2-goal-and-implementation-plan.md` 维护；本文件中的 ID 都是对计划的外键。

```yaml
state_schema: amz-project-state/v2
task_id: amz-listing-kit-product-v2
status: active
goal_binding: required
goal_id: 01a0ca17-2179-7eb0-969a-af9c79c4d8ca
system_goal_observed_status: active
system_goal_observed_at: 2026-10-01T05:30:28+08:00
plan_ref: docs/product-v2-goal-and-implementation-plan.md
latest_audit: evals/product-v2/pre-goal-ui-rebaseline-20260930.txt

phase_progress:
  "0":
    status: done
    evidence:
      - docs/INDEX.md
      - docs/product-v2-project-context.md
      - docs/product-v2-goal-and-implementation-plan.md
      - evals/product-v2/control-plane-calibration-20260929.txt
      - evals/product-v2/pre-goal-readiness-20260929.txt
      - evals/product-v2/standards-mapping-gate-20260929.txt
  "1":
    status: done
    evidence:
      - evals/product-v2/v2.1.1-indexeddb-20260929-205946-pre-goal-baseline.txt
      - evals/product-v2/v2.1.2-project-home-20260929-205951-pre-goal-baseline.txt
      - evals/product-v2/v2.1.3-project-package-20260929-205957-pre-goal-baseline.txt
      - evals/product-v2/v2.1.4-formal-entry-20260929-205919-pre-goal-verify.txt
  "2":
    status: done
    evidence:
      - evals/product-v2/reuse-gate-negative-probe-20260929.txt
      - evals/product-v2/dependency-authority-migration-20260930.txt
      - evals/product-v2/sel-records-sync-20260930.txt
      - evals/product-v2/v2.2.2-semantic-provider-20260930-013134.txt
      - evals/product-v2/v2.2.2-semantic-provider-20260930-013041-live.txt
      - evals/product-v2/v2-domain-primitive-cleanup-20260930.txt
      - evals/product-v2/v2.2.3-intake-understanding-20260930-015817.txt
      - evals/product-v2/v2.2.3-intake-understanding-20260930-015817.json
      - evals/product-v2/evidence/v2.2.3-workspace-20260930-015817.png
      - evals/product-v2/evidence/v2.2.3-narrow-20260930-015817.png
      - evals/product-v2/v2.1.1-indexeddb-20260930-015729.txt
      - evals/product-v2/v2.1.2-project-home-20260930-015239.txt
      - evals/product-v2/v2.1.3-project-package-20260930-015253.txt
      - evals/product-v2/v2.1.4-formal-entry-20260930-015304.txt
      - evals/product-v2/v2.2.1-product-contracts-20260930-015405.txt
      - evals/product-v2/v2.2.2-semantic-provider-20260930-015334.txt
      - evals/product-v2/sel008-fflate-vendoring-20260930.txt
      - evals/product-v2/v2.2.4-category-generality-20260930-021709.txt
      - evals/product-v2/v2.2.4-category-generality-20260930-021709.json
      - evals/product-v2/v2.2.4-category-generality-20260930-021048.txt
      - evals/product-v2/v2.2.4-category-generality-20260930-021404.txt
      - evals/product-v2/v2.2.2-semantic-provider-20260930-021554.txt
      - evals/product-v2/v2.2.1-product-contracts-20260930-021554.txt
      - evals/product-v2/v2.2.4-max-tokens-acceptance-20260930.txt
      - evals/product-v2/v2.2.2-semantic-provider-20261001-010715-arrears-map.txt
  "3":
    status: done
    evidence:
      - evals/product-v2/v2.3.1-suite-registry-20260930-025255.txt
      - evals/product-v2/v2.3.2-suite-editor-20260930-025222.txt
      - evals/product-v2/v2.3.3-spec-versions-20260930-025205.txt
      - evals/product-v2/v2.3.4-prompt-compiler-20260930-031626-final.txt
      - evals/product-v2/v2.3.5-pre-generation-confirm-20260930-033626-final.txt
      - evals/product-v2/v2.3.6-prompt-manual-edit-20260930-035000-final.txt
      - evals/product-v2/v2.3.6-prompt-manual-edit-20260930-035000-final.json
      - evals/product-v2/evidence/v2.3.6-prompt-manual-edit-20260930-035000.png
      - evals/product-v2/v2.3.5-pre-generation-confirm-20260930-035020-v236-regression.txt
      - evals/product-v2/v2.3.4-prompt-compiler-20260930-035020-v236-regression.txt
      - evals/product-v2/v2.3.2-suite-editor-20260930-035037-v236-regression.txt
      - evals/product-v2/v2.2.3-intake-understanding-20260930-035038-v236-regression.txt
  "4":
    status: done
    evidence:
      - evals/product-v2/v2.4.1-image-gateway-20260930-091224-final.txt
      - evals/product-v2/v2.4.1-image-gateway-20260930-091224-final.json
      - evals/product-v2/v2.4.2-generation-attempt-20260930-112423-final.txt
      - evals/product-v2/v2.4.2-generation-attempt-20260930-112423-final.json
      - evals/product-v2/evidence/v2.4.2-generation-attempt-20260930-112423.png
      - evals/product-v2/v2.4.3-batch-suite-20260930-114918-final.txt
      - evals/product-v2/v2.4.3-batch-suite-20260930-114918-final.json
      - evals/product-v2/evidence/v2.4.3-batch-suite-20260930-114918.png
      - evals/product-v2/v2.4.4-candidate-blob-20260930-131856-final.txt
      - evals/product-v2/v2.4.4-candidate-blob-20260930-131856-final.json
      - evals/product-v2/evidence/v2.4.4-candidate-blob-20260930-131856.png
      - evals/product-v2/v2.4.5-live-reference-20260930-134540-final.txt
      - evals/product-v2/v2.4.5-live-reference-20260930-134540-final.json
      - evals/product-v2/evidence/v2.4.5-live-reference-20260930-134540.png
      - evals/product-v2/v2.4.1-image-gateway-20260930-134149-v245-transport-fix.txt

  "5":
    status: done
    evidence:
      - evals/product-v2/v2.5.4-rework-loop-20260930-172722final.txt
      - evals/product-v2/v2.5.4-rework-loop-20260930-172722final.json
      - evals/product-v2/evidence/v2.5.4-rework-loop-20260930-172722.png
      - evals/product-v2/evidence/v2.5.4-rework-loop-20260930-172722-detail.png
      - evals/product-v2/v2.5.2-vlm-review-20260930-150502final.txt
      - evals/product-v2/v2.5.2-vlm-review-20260930-150502final.json
      - evals/product-v2/evidence/v2.5.2-vlm-review-20260930-150502.png
      - evals/product-v2/v2.5.2-review-live-20260930-150012final.txt
      - evals/product-v2/v2.5.2-review-live-20260930-150012final.json
      - evals/product-v2/v2.5.1-deterministic-review-20260930-142836-final.txt
      - evals/product-v2/v2.5.1-deterministic-review-20260930-142836-final.json
      - evals/product-v2/evidence/v2.5.1-deterministic-review-20260930-142836.png
      - evals/product-v2/v2.6.1-selection-20260930-183606final.txt
      - evals/product-v2/v2.6.1-selection-20260930-183606final.json
      - evals/product-v2/evidence/v2.6.1-selection-20260930-183606.png
      - evals/product-v2/evidence/v2.6.1-selection-20260930-183606-detail.png
      - evals/product-v2/v2.ui.1-remote-entry-20260930-213048-final.txt
      - evals/product-v2/v2.ui.1-remote-entry-20260930-213048-final.json
      - evals/product-v2/evidence/v2.ui.1-remote-entry-20260930-213048-localhost.png
      - evals/product-v2/evidence/v2.ui.1-remote-entry-20260930-213048-chrome.png
      - evals/product-v2/evidence/v2.ui.1-remote-entry-20260930-213048-edge.png
      - evals/product-v2/evidence/v2.ui.1-remote-entry-20260930-213048-http-negative.png
      - evals/product-v2/v2.ui.2-interaction-visual-20260930-232009final.txt
      - evals/product-v2/v2.ui.2-interaction-visual-20260930-232009final.json
      - evals/product-v2/evidence/v2.ui.2-review-20260930-232009.png
      - evals/product-v2/evidence/v2.ui.2-narrow-20260930-232009.png
      - tools/verify_v2_ui_2_interaction_visual.py
      - evals/product-v2/v2.6.2-delivery-20261001-042122-final.txt
      - evals/product-v2/v2.6.2-delivery-20261001-042122-final.json
      - evals/product-v2/evidence/v2.6.2-delivery-20261001-042122-final-gate-pass.png
      - evals/product-v2/evidence/v2.6.2-delivery-20261001-042122-final-unknown-blocked.png
      - tools/verify_v2_6_2_delivery.py
      - evals/product-v2/v2.6.3-transfer-20261001-050133-final.txt
      - evals/product-v2/v2.6.3-transfer-20261001-050133-final.json
      - evals/product-v2/v2.1.3-project-package-20261001-050001.txt
      - tools/verify_v2_6_3_project_transfer.py
      - evals/product-v2/v2.6.4-a11y-20261001-052757-final.txt
      - evals/product-v2/v2.6.4-a11y-20261001-052757-final.json
      - tools/verify_v2_6_4_accessibility.py

  "6":
    status: done
    evidence:
      - evals/product-v2/v2.6.1-selection-20260930-183606final.txt
      - evals/product-v2/v2.6.1-selection-20260930-183606final.json
      - evals/product-v2/v2.6.2-delivery-20261001-042122-final.txt
      - evals/product-v2/v2.6.2-delivery-20261001-042122-final.json
      - evals/product-v2/evidence/v2.6.2-delivery-20261001-042122-final-gate-pass.png
      - evals/product-v2/evidence/v2.6.2-delivery-20261001-042122-final-unknown-blocked.png
      - tools/verify_v2_6_2_delivery.py
      - evals/product-v2/v2.6.3-transfer-20261001-050133-final.txt
      - evals/product-v2/v2.6.3-transfer-20261001-050133-final.json
      - tools/verify_v2_6_3_project_transfer.py
      - evals/product-v2/v2.6.4-a11y-20261001-052757-final.txt
      - evals/product-v2/v2.6.4-a11y-20261001-052757-final.json
      - tools/verify_v2_6_4_accessibility.py
      - evals/product-v2/v2.6.4-a11y-20261001-055317-v265-final.txt
      - evals/product-v2/v2.6.4-a11y-20261001-055317-v265-final.json
      - evals/product-v2/v2.6.4-a11y-20261001-055253-red-proof-old-layout.txt
      - evals/product-v2/evidence/v2.6.4-a11y-20261001-055317-v265-final-ref-card-1440.png
      - evals/product-v2/v2.6.4-a11y-20261001-060452-v266-red-proof.txt
      - evals/product-v2/v2.6.4-a11y-20261001-060920-v266-final4.txt
      - evals/product-v2/v2.6.4-a11y-20261001-060920-v266-final4.json
      - evals/product-v2/v2.ui.3-frontend-20261001-065851-v267-red.txt
      - evals/product-v2/v2.ui.3-frontend-20261001-065959-v267-green.txt
      - evals/product-v2/v2.ui.3-frontend-20261001-065959-v267-green.json
      - evals/product-v2/v2.5.5-suite-review-20261001-065917-v267-red.txt
      - evals/product-v2/v2.5.5-suite-review-20261001-070024-v267-green.txt
      - evals/product-v2/v2.5.5-suite-review-20261001-070024-v267-green.json
      - evals/product-v2/v2.4.1-large-ref-red-proof-20261001-073024.json
      - evals/product-v2/v2.4.1-image-gateway-20261001-073247-v268-green.txt
      - evals/product-v2/v2.4.1-image-gateway-20261001-073247-v268-green.json
      - evals/product-v2/v273-rehearsal-20261001-072035-crash.json
      - evals/product-v2/v273-rehearsal-20261001-073329.md
      - evals/product-v2/v273-rehearsal-20261001-073329.json
      - evals/product-v2/v2.ui.3-frontend-20261001-073741-v269-red.txt
      - evals/product-v2/v2.ui.3-frontend-20261001-073811-v269-green.txt
      - evals/product-v2/v2.ui.3-frontend-20261001-073811-v269-green.json
      - evals/product-v2/v2.2.3-intake-understanding-20261001-073929-v269.txt
      - evals/product-v2/v2.6.4-a11y-20261001-073942-v269.txt
      - evals/product-v2/v273-rehearsal-20261001-074015.md
      - evals/product-v2/v2.3.5-pre-generation-confirm-20261001-074628-v2610-red.txt
      - evals/product-v2/v2.3.5-pre-generation-confirm-20261001-074714-v2610-green.txt
      - evals/product-v2/v2.3.5-pre-generation-confirm-20261001-074714-v2610-green.json
      - evals/product-v2/v2.ui.3-frontend-20261001-074726-v2610.txt
      - evals/product-v2/v273-rehearsal-20261001-074743.md

  "7":
    status: active
    evidence:
      - evals/product-v2/v2.7.1-regression-20261001-0633-final.txt
      - evals/product-v2/v2.7.1-regression-20261001-0633-final.json
      - evals/product-v2/v2.7.1-regression-20261001-061430-final.txt
      - tools/verify_v2_7_1_regression.py
      - evals/probes/docs_index.py

task_progress:
  V2.0.1:
    status: done
    evidence:
      - docs/INDEX.md
      - docs/product-v2-project-context.md
      - docs/product-v2-goal-and-implementation-plan.md
      - evals/product-v2/pre-goal-readiness-20260929.txt
  V2.0.2:
    status: done
    evidence:
      - _working/amz-listing-kit-product-v2/state.md
      - tools/check_project_state.py
      - evals/product-v2/control-plane-calibration-20260929.txt
  V2.0.3:
    status: done
    evidence:
      - evals/product-demo/d4.12-product-regression-2026-09-29.md
      - evals/product-v2/pre-goal-readiness-20260929.txt
  V2.1.1:
    status: done
    evidence:
      - evals/product-v2/v2.1.1-indexeddb-20260929-201212.txt
      - evals/product-v2/v2.1.1-indexeddb-20260929-201431-fresh-20260929.txt
      - evals/product-v2/v2.1.1-indexeddb-20260929-202722-final.txt
      - evals/product-v2/v2.1.1-indexeddb-20260929-204543-after-v214.txt
      - evals/product-v2/v2.1.1-indexeddb-20260929-205946-pre-goal-baseline.txt
      - evals/product-v2/v2.1.1-indexeddb-20260929-225228.txt
      - evals/product-v2/v2.1.1-indexeddb-20260930-022356.txt
  V2.1.2:
    status: done
    evidence:
      - evals/product-v2/v2.1.2-project-home-20260929-202041.txt
      - evals/product-v2/v2.1.2-project-home-20260929-202403-repro2.txt
      - evals/product-v2/v2.1.2-project-home-20260929-202728-final.txt
      - evals/product-v2/v2.1.2-project-home-20260929-204548-after-v214.txt
      - evals/product-v2/v2.1.2-project-home-20260929-205951-pre-goal-baseline.txt
      - evals/product-v2/v2.1.2-project-home-20260929-225234.txt
  V2.1.3:
    status: done
    evidence:
      - evals/product-v2/v2.1.3-project-package-20260929-203215.txt
      - evals/product-v2/v2.1.3-project-package-20260929-203215.json
      - evals/product-v2/v2.1.1-indexeddb-20260929-203229-after-v213.txt
      - evals/product-v2/v2.1.2-project-home-20260929-203233-after-v213.txt
      - evals/product-v2/v2.1.3-project-package-20260929-204555-after-v214.txt
      - evals/product-v2/v2.1.3-project-package-20260929-205957-pre-goal-baseline.txt
      - evals/product-v2/v2.1.3-project-package-20260929-225243.txt
      - evals/product-v2/v2.1.3-project-package-20260930-020609.txt
      - evals/product-v2/v2.1.3-project-package-20260930-020609.json
      - evals/product-v2/sel008-fflate-vendoring-20260930.txt
  V2.1.4:
    status: done
    evidence:
      - evals/product-v2/v2.1.4-formal-entry-20260929-204134.txt
      - evals/product-v2/v2.1.4-formal-entry-20260929-204134.json
      - evals/product-v2/v2.1.4-formal-entry-20260929-205919-pre-goal-verify.txt
      - evals/product-v2/v2.1.4-formal-entry-20260929-225248.txt
      - evals/product-v2/v2.1.4-formal-entry-20260930-024511.txt
      - evals/product-v2/v2.1.4-formal-entry-20260930-024511.json
      - evals/product-v2/v2.1.4-formal-entry-20260930-025255.txt
      - evals/product-v2/v2.1.4-formal-entry-20260930-025255.json
  V2.CI.1:
    status: done
    evidence:
      - evals/product-v2/v2.ci.1-docker-cd-20260929.txt
      - .github/workflows/ci-cd.yml
      - Dockerfile
  V2.2.1:
    status: done
    evidence:
      - evals/product-v2/v2.2.1-product-contracts-20260929-211211.txt
      - evals/product-v2/v2.2.1-product-contracts-20260929-211211.json
      - evals/product-v2/v2.2.1-product-contracts-20260929-225304.txt
      - evals/product-v2/v2.2.1-product-contracts-20260930-023543.txt
      - evals/product-v2/v2.2.1-product-contracts-20260930-024511.txt
      - evals/product-v2/v2.2.1-product-contracts-20260930-024511.json
      - evals/product-v2/v2.2.1-product-contracts-20260930-025257.txt
      - evals/product-v2/v2.2.1-product-contracts-20260930-025257.json
  V2.2.2:
    status: done
    evidence:
      - evals/product-v2/v2.2.2-semantic-provider-20260930-013134.txt
      - evals/product-v2/v2.2.2-semantic-provider-20260930-013134.json
      - evals/product-v2/v2.2.2-semantic-provider-20260930-013041-live.txt
      - evals/product-v2/v2.2.2-semantic-provider-20260930-013041-live.json
      - tools/verify_v2_2_2_semantic_provider.py
      - config/product-v2/providers.json
      - evals/product-v2/v2.2.2-semantic-provider-20260930-023603.txt
      - evals/product-v2/v2.2.2-semantic-provider-20261001-010715-arrears-map.txt
      - evals/product-v2/provider-recovery-probe-20261001.txt
  V2.2.3:
    status: done
    evidence:
      - evals/product-v2/v2.2.3-intake-understanding-20260930-015817.txt
      - evals/product-v2/v2.2.3-intake-understanding-20260930-015817.json
      - tools/verify_v2_2_3_intake_understanding.py
      - app/product_v2/workspace.js
      - app/product_v2/app.js
      - app/product_v2/index.html
      - app/product_v2/styles.css
      - app/product_v2/storage/repository.js
      - app/product_v2_server.py
      - src/providers/v2_fake_semantic.py
      - tools/v2_test_server.py
      - Dockerfile
      - .dockerignore
      - .github/workflows/ci-cd.yml
      - evals/product-v2/v2.2.3-intake-understanding-20260930-023544.txt
      - evals/product-v2/v2.2.3-intake-understanding-20260930-023544.json
      - evals/product-v2/evidence/v2.2.3-workspace-20260930-023544.png
      - evals/product-v2/evidence/v2.2.3-narrow-20260930-023544.png
      - evals/product-v2/v2.2.3-intake-understanding-20260930-024451.txt
      - evals/product-v2/v2.2.3-intake-understanding-20260930-024451.json
      - evals/product-v2/evidence/v2.2.3-workspace-20260930-024451.png
      - evals/product-v2/evidence/v2.2.3-narrow-20260930-024451.png
      - evals/product-v2/v2.2.3-intake-understanding-20260930-024645.txt
      - evals/product-v2/v2.2.3-intake-understanding-20260930-024645.json
      - evals/product-v2/v2.2.3-intake-understanding-20260930-025231.txt
      - evals/product-v2/v2.2.3-intake-understanding-20260930-025231.json
      - evals/product-v2/v2.2.3-intake-understanding-20260930-184523.txt
      - evals/product-v2/v2.2.3-intake-understanding-20260930-184523.json
      - evals/product-v2/evidence/v2.2.3-workspace-20260930-184523.png
      - evals/product-v2/evidence/v2.2.3-narrow-20260930-184523.png
  V2.2.4:
    status: done
    evidence:
      - evals/product-v2/v2.2.4-category-generality-20260930-021709.txt
      - evals/product-v2/v2.2.4-category-generality-20260930-021709.json
      - evals/product-v2/v2.2.4-category-generality-20260930-021048.txt
      - evals/product-v2/v2.2.4-category-generality-20260930-021404.txt
      - tools/verify_v2_2_4_category_generality.py
      - evals/product-v2/v2.2.2-semantic-provider-20260930-021554.txt
      - evals/product-v2/v2.2.4-max-tokens-acceptance-20260930.txt
      - evals/product-v2/v2.1.1-indexeddb-20260930-022356.txt
  V2.3.1:
    status: done
    evidence:
      - evals/product-v2/v2.3.1-suite-registry-20260930-023528.txt
      - evals/product-v2/v2.3.1-suite-registry-20260930-023528.json
      - evals/product-v2/v2.3.1-suite-registry-20260930-024514.txt
      - evals/product-v2/v2.3.1-suite-registry-20260930-024514.json
      - evals/product-v2/v2.3.1-suite-registry-20260930-025255.txt
      - evals/product-v2/v2.3.1-suite-registry-20260930-025255.json
      - tools/verify_v2_3_1_suite_registry.py
      - evals/product-v2/harness/suite-plan-contract.js
      - evals/product-v2/harness/suite-plan-contract.html
      - app/product_v2/domain/suite-plan.js
      - app/product_v2/domain/intake.js
      - app/product_v2/domain/index.js
      - app/product_v2/workspace.js
  V2.3.2:
    status: done
    evidence:
      - evals/product-v2/v2.3.2-suite-editor-20260930-024451.txt
      - evals/product-v2/v2.3.2-suite-editor-20260930-024451.json
      - evals/product-v2/evidence/v2.3.2-suite-editor-20260930-024451.png
      - evals/product-v2/v2.3.2-suite-editor-20260930-024629.txt
      - evals/product-v2/v2.3.2-suite-editor-20260930-024629.json
      - evals/product-v2/evidence/v2.3.2-suite-editor-20260930-024629.png
      - evals/product-v2/v2.3.2-suite-editor-20260930-025222.txt
      - evals/product-v2/v2.3.2-suite-editor-20260930-025222.json
      - evals/product-v2/evidence/v2.3.2-suite-editor-20260930-025222.png
      - evals/product-v2/v2.3.2-oversize-drain-20260930.txt
      - tools/verify_v2_3_2_suite_editor.py
      - evals/product-v2/harness/suite-editor-contract.js
      - evals/product-v2/harness/suite-editor-contract.html
      - app/product_v2/domain/suite.js
      - app/product_v2/domain/shared.js
      - app/product_v2/domain/index.js
      - app/product_v2/workspace.js
      - app/product_v2/index.html
      - app/product_v2/styles.css
      - app/product_v2_server.py
      - docs/product-v2-goal-and-implementation-plan.md
  V2.3.3:
    status: done
    evidence:
      - evals/product-v2/v2.3.3-spec-versions-20260930-025205.txt
      - evals/product-v2/v2.3.3-spec-versions-20260930-025205.json
      - evals/product-v2/evidence/v2.3.3-spec-versions-20260930-025205.png
      - tools/verify_v2_3_3_spec_versions.py
      - evals/product-v2/harness/specs-contract.js
      - evals/product-v2/harness/specs-contract.html
      - app/product_v2/domain/specs.js
      - app/product_v2/domain/shared.js
      - app/product_v2/domain/index.js
      - app/product_v2/workspace.js
      - app/product_v2/index.html
      - app/product_v2/styles.css
      - docs/product-v2-goal-and-implementation-plan.md
  V2.3.4:
    status: done
    evidence:
      - evals/product-v2/v2.3.4-prompt-compiler-20260930-031626-final.txt
      - evals/product-v2/v2.3.4-prompt-compiler-20260930-031626-final.json
      - evals/product-v2/evidence/v2.3.4-prompt-compiler-20260930-031626.png
      - tools/verify_v2_3_4_prompt_compiler.py
      - evals/product-v2/harness/prompt-contract.js
      - evals/product-v2/harness/prompt-contract.html
      - app/product_v2/domain/prompt.js
      - app/product_v2/domain/suite.js
      - app/product_v2/domain/shared.js
      - app/product_v2/domain/index.js
      - app/product_v2/workspace.js
      - app/product_v2/index.html
      - app/product_v2/styles.css
      - README.md
      - docs/product-v2-project-context.md
      - docs/product-v2-goal-and-implementation-plan.md
      - docs/product-v2-goal-and-implementation-plan.md
      - .github/workflows/ci-cd.yml
      - evals/product-v2/v2.1.4-formal-entry-20260930-031657-v234-regression.txt
      - evals/product-v2/v2.2.1-product-contracts-20260930-031713-v234-regression.txt
      - evals/product-v2/v2.2.2-semantic-provider-20260930-031723-v234-regression.txt
      - evals/product-v2/v2.2.3-intake-understanding-20260930-031724-v234-regression.txt
      - evals/product-v2/v2.3.1-suite-registry-20260930-031737-v234-regression.txt
      - evals/product-v2/v2.3.2-suite-editor-20260930-031740-v234-regression.txt
      - evals/product-v2/v2.3.3-spec-versions-20260930-031748-v234-regression.txt
  V2.3.5:
    status: done
    evidence:
      - evals/product-v2/v2.3.5-pre-generation-confirm-20260930-033626-final.txt
      - evals/product-v2/v2.3.5-pre-generation-confirm-20260930-033626-final.json
      - evals/product-v2/evidence/v2.3.5-pre-generation-confirm-20260930-033626.png
      - tools/verify_v2_3_5_pre_generation_confirm.py
      - evals/product-v2/harness/confirm-contract.js
      - evals/product-v2/harness/confirm-contract.html
      - app/product_v2/domain/confirm.js
      - app/product_v2/domain/shared.js
      - app/product_v2/domain/index.js
      - app/product_v2/workspace.js
      - app/product_v2/index.html
      - app/product_v2/styles.css
      - README.md
      - docs/product-v2-project-context.md
      - docs/product-v2-goal-and-implementation-plan.md
      - .github/workflows/ci-cd.yml
      - evals/product-v2/v2.1.1-indexeddb-20260930-033530-v235-regression.txt
      - evals/product-v2/v2.1.4-formal-entry-20260930-033505-v235-regression.txt
      - evals/product-v2/v2.2.1-product-contracts-20260930-033505-v235-regression.txt
      - evals/product-v2/v2.2.2-semantic-provider-20260930-033528-v235-regression.txt
      - evals/product-v2/v2.2.3-intake-understanding-20260930-033421-v235-regression.txt
      - evals/product-v2/v2.3.1-suite-registry-20260930-033527-v235-regression.txt
      - evals/product-v2/v2.3.2-suite-editor-20260930-033442-v235-regression.txt
      - evals/product-v2/v2.3.3-spec-versions-20260930-033442-v235-regression.txt
      - evals/product-v2/v2.3.4-prompt-compiler-20260930-033421-v235-regression.txt

  V2.3.6:
    status: done
    evidence:
      - evals/product-v2/v2.3.6-prompt-manual-edit-20260930-035000-final.txt
      - evals/product-v2/v2.3.6-prompt-manual-edit-20260930-035000-final.json
      - evals/product-v2/evidence/v2.3.6-prompt-manual-edit-20260930-035000.png
      - tools/verify_v2_3_6_prompt_manual_edit.py
      - evals/product-v2/harness/prompt-edit-contract.js
      - evals/product-v2/harness/prompt-edit-contract.html
      - app/product_v2/domain/prompt.js
      - app/product_v2/workspace.js
      - app/product_v2/index.html
      - app/product_v2/styles.css
      - README.md
      - docs/product-v2-project-context.md
      - docs/product-v2-goal-and-implementation-plan.md
      - .github/workflows/ci-cd.yml
      - evals/product-v2/v2.3.5-pre-generation-confirm-20260930-035020-v236-regression.txt
      - evals/product-v2/v2.3.4-prompt-compiler-20260930-035020-v236-regression.txt
      - evals/product-v2/v2.3.2-suite-editor-20260930-035037-v236-regression.txt
      - evals/product-v2/v2.2.3-intake-understanding-20260930-035038-v236-regression.txt

  V2.4.1:
    status: done
    evidence:
      - evals/product-v2/v2.4.1-image-gateway-20260930-091224-final.txt
      - evals/product-v2/v2.4.1-image-gateway-20260930-091224-final.json
      - tools/verify_v2_4_1_image_gateway.py
      - app/product_v2_server.py
      - src/providers/v2_image.py
      - src/providers/v2_dashscope_image.py
      - src/providers/v2_fake_image.py
      - src/providers/v2_errors.py
      - src/providers/v2_registry.py
      - config/product-v2/providers.json
      - evals/product-v2/sel010-image-gateway-transport-poc-20260930.txt
      - README.md
      - docs/product-v2-project-context.md
      - docs/product-v2-goal-and-implementation-plan.md
      - .github/workflows/ci-cd.yml
      - evals/product-v2/v2.2.2-semantic-provider-20260930-091150-v241-regression.txt
      - evals/product-v2/v2.3.6-prompt-manual-edit-20260930-091203-v241-regression.txt

  V2.4.2:
    status: done
    evidence:
      - evals/product-v2/v2.4.2-generation-attempt-20260930-112423-final.txt
      - evals/product-v2/v2.4.2-generation-attempt-20260930-112423-final.json
      - evals/product-v2/evidence/v2.4.2-generation-attempt-20260930-112423.png
      - tools/verify_v2_4_2_generation_attempt.py
      - app/product_v2/domain/attempt.js
      - app/product_v2/workspace.js
      - app/product_v2/index.html
      - app/product_v2/styles.css
      - evals/product-v2/harness/attempt-contract.js
      - evals/product-v2/harness/attempt-contract.html
      - README.md
      - docs/product-v2-goal-and-implementation-plan.md
      - .github/workflows/ci-cd.yml

  V2.4.3:
    status: done
    evidence:
      - evals/product-v2/v2.4.3-batch-suite-20260930-114918-final.txt
      - evals/product-v2/v2.4.3-batch-suite-20260930-114918-final.json
      - evals/product-v2/evidence/v2.4.3-batch-suite-20260930-114918.png
      - tools/verify_v2_4_3_batch_execution.py
      - app/product_v2/domain/batch.js
      - app/product_v2/domain/index.js
      - app/product_v2/workspace.js
      - app/product_v2/index.html
      - app/product_v2/styles.css
      - app/product_v2_server.py
      - evals/product-v2/harness/batch-contract.js
      - evals/product-v2/harness/batch-contract.html
      - README.md
      - docs/product-v2-goal-and-implementation-plan.md
      - .github/workflows/ci-cd.yml
  V2.4.4:
    status: done
    evidence:
      - evals/product-v2/v2.4.4-candidate-blob-20260930-131856-final.txt
      - evals/product-v2/v2.4.4-candidate-blob-20260930-131856-final.json
      - evals/product-v2/evidence/v2.4.4-candidate-blob-20260930-131856.png
      - tools/verify_v2_4_4_candidate_blob.py
      - app/product_v2/domain/candidate.js
      - app/product_v2/domain/batch.js
      - app/product_v2/domain/shared.js
      - app/product_v2/domain/index.js
      - app/product_v2/workspace.js
      - app/product_v2/index.html
      - app/product_v2/styles.css
      - evals/product-v2/harness/candidate-contract.js
      - evals/product-v2/harness/candidate-contract.html
      - README.md
      - docs/product-v2-goal-and-implementation-plan.md
      - .github/workflows/ci-cd.yml

  V2.4.5:
    status: done
    evidence:
      - evals/product-v2/v2.4.5-live-reference-20260930-134540-final.txt
      - evals/product-v2/v2.4.5-live-reference-20260930-134540-final.json
      - evals/product-v2/evidence/v2.4.5-live-reference-20260930-134540.png
      - tools/verify_v2_4_5_live_reference.py
      - src/providers/v2_dashscope_image.py
      - tools/verify_v2_4_1_image_gateway.py
      - docs/product-v2-goal-and-implementation-plan.md

  V2.5.1:
    status: done
    evidence:
      - evals/product-v2/v2.5.1-deterministic-review-20260930-142836-final.txt
      - evals/product-v2/v2.5.1-deterministic-review-20260930-142836-final.json
      - evals/product-v2/evidence/v2.5.1-deterministic-review-20260930-142836.png
      - tools/verify_v2_5_1_deterministic_review.py
      - app/product_v2/domain/review.js
      - app/product_v2/domain/candidate.js
      - app/product_v2/domain/shared.js
      - app/product_v2/domain/index.js
      - app/product_v2/workspace.js
      - evals/product-v2/harness/review-contract.js
      - evals/product-v2/harness/review-contract.html
      - README.md
      - docs/product-v2-project-context.md
      - docs/product-v2-goal-and-implementation-plan.md
      - .github/workflows/ci-cd.yml

  V2.5.2:
    status: done
    evidence:
      - evals/product-v2/v2.5.2-vlm-review-20260930-150502final.txt
      - evals/product-v2/v2.5.2-vlm-review-20260930-150502final.json
      - evals/product-v2/evidence/v2.5.2-vlm-review-20260930-150502.png
      - evals/product-v2/v2.5.2-review-live-20260930-150012final.txt
      - evals/product-v2/v2.5.2-review-live-20260930-150012final.json
      - tools/verify_v2_5_2_vlm_review.py
      - tools/probe_v2_5_2_review_live.py
      - src/providers/v2_review.py
      - src/providers/v2_dashscope_review.py
      - src/providers/v2_langchain_chat.py
      - src/providers/v2_fake_review.py
      - src/providers/v2_registry.py
      - config/product-v2/providers.json
      - app/product_v2_server.py
      - app/product_v2/domain/review.js
      - app/product_v2/workspace.js
      - evals/product-v2/harness/review-provider-contract.js
      - evals/product-v2/harness/review-provider-contract.html
      - evals/product-v2/fixtures/v2.5.2/
      - README.md
      - docs/product-v2-project-context.md
      - docs/product-v2-goal-and-implementation-plan.md
      - .github/workflows/ci-cd.yml

  V2.5.3:
    status: done
    evidence:
      - evals/product-v2/v2.5.3-compare-panel-20260930-153012final.txt
      - evals/product-v2/v2.5.3-compare-panel-20260930-153012final.json
      - evals/product-v2/evidence/v2.5.3-compare-panel-20260930-153012.png
      - evals/product-v2/evidence/v2.5.3-compare-panel-20260930-153012-detail.png
      - tools/verify_v2_5_3_compare_panel.py
      - app/product_v2/domain/compare.js
      - app/product_v2/domain/review.js
      - app/product_v2/domain/index.js
      - app/product_v2/workspace.js
      - app/product_v2/index.html
      - app/product_v2/styles.css
      - evals/product-v2/harness/compare-panel.js
      - evals/product-v2/harness/compare-panel.html
      - README.md
      - docs/product-v2-project-context.md
      - docs/product-v2-goal-and-implementation-plan.md
      - .github/workflows/ci-cd.yml

  V2.5.4:
    status: done
    evidence:
      - evals/product-v2/v2.5.4-rework-loop-20260930-172722final.txt
      - evals/product-v2/v2.5.4-rework-loop-20260930-172722final.json
      - evals/product-v2/evidence/v2.5.4-rework-loop-20260930-172722.png
      - evals/product-v2/evidence/v2.5.4-rework-loop-20260930-172722-detail.png
      - evals/product-v2/v2.5.3-compare-panel-20260930-170502-v254reorg.txt
      - tools/verify_v2_5_4_rework_loop.py
      - app/product_v2/domain/rework.js
      - app/product_v2/domain/compare.js
      - app/product_v2/domain/confirm.js
      - app/product_v2/domain/prompt.js
      - app/product_v2/domain/index.js
      - app/product_v2/workspace.js
      - app/product_v2/index.html
      - app/product_v2/styles.css
      - evals/product-v2/harness/rework-contract.js
      - evals/product-v2/harness/rework-contract.html
      - README.md
      - docs/product-v2-project-context.md
      - docs/product-v2-goal-and-implementation-plan.md
      - .github/workflows/ci-cd.yml

  V2.6.1:
    status: done
    evidence:
      - evals/product-v2/v2.6.1-selection-20260930-183606final.txt
      - evals/product-v2/v2.6.1-selection-20260930-183606final.json
      - evals/product-v2/evidence/v2.6.1-selection-20260930-183606.png
      - evals/product-v2/evidence/v2.6.1-selection-20260930-183606-detail.png
      - evals/product-v2/v2.5.4-rework-loop-20260930-183415-v261final.txt
      - tools/verify_v2_6_1_selection.py
      - app/product_v2/domain/selection.js
      - app/product_v2/domain/shared.js
      - app/product_v2/domain/index.js
      - app/product_v2/workspace.js
      - app/product_v2/index.html
      - app/product_v2/styles.css
      - evals/product-v2/harness/selection-contract.js
      - evals/product-v2/harness/selection-contract.html
      - README.md
      - docs/product-v2-project-context.md
      - .github/workflows/ci-cd.yml

  V2.UI.1:
    status: done
    evidence:
      - evals/product-v2/v2.ui.1-remote-entry-20260930-213048-final.txt
      - evals/product-v2/v2.ui.1-remote-entry-20260930-213048-final.json
      - evals/product-v2/evidence/v2.ui.1-remote-entry-20260930-213048-localhost.png
      - evals/product-v2/evidence/v2.ui.1-remote-entry-20260930-213048-chrome.png
      - evals/product-v2/evidence/v2.ui.1-remote-entry-20260930-213048-edge.png
      - evals/product-v2/evidence/v2.ui.1-remote-entry-20260930-213048-http-negative.png
      - tools/verify_v2_ui_1_remote_entry.py
      - deploy/caddy/Caddyfile
      - app/product_v2/storage/capabilities.js
      - app/product_v2/storage/errors.js
      - app/product_v2/storage/db.js
      - app/product_v2/storage/index.js
      - app/product_v2/app.js
      - app/product_v2/index.html
      - app/product_v2/styles.css
      - .github/workflows/ci-cd.yml
      - README.md
      - docs/product-v2-project-context.md
  V2.UI.2:
    status: done
    evidence:
      - evals/product-v2/v2.ui.2-interaction-visual-20260930-232009final.txt
      - evals/product-v2/v2.ui.2-interaction-visual-20260930-232009final.json
      - evals/product-v2/evidence/v2.ui.2-home-20260930-232009.png
      - evals/product-v2/evidence/v2.ui.2-review-20260930-232009.png
      - evals/product-v2/evidence/v2.ui.2-deliver-20260930-232009.png
      - evals/product-v2/evidence/v2.ui.2-narrow-20260930-232009.png
      - evals/product-v2/evidence/v2.ui.2-zoom200-20260930-232009.png
      - tools/verify_v2_ui_2_interaction_visual.py
      - tools/v2_stage_nav.py
      - app/product_v2/index.html
      - app/product_v2/styles.css
      - app/product_v2/ui/stage-shell.js
      - app/product_v2/workspace.js
      - evals/product-v2/v2.7.2-remote-real-e2e-20261001-013714-real01.txt
      - evals/product-v2/remote-persistence-20261001-020726-pre-restart.txt
      - evals/product-v2/remote-persistence-20261001-021516-post-restart.txt
      - evals/product-v2/evidence/self-review-remote-390-20261001.png
      - evals/product-v2/evidence/self-review-remote-zoom200-20261001.png
      - evals/product-v2/evidence/self-review-remote-empty-390-20261001.png
      - evals/product-v2/v2.ui.2-walkthrough-record.md
      - docs/product-v2-ui-contract.md
      - README.md
      - .github/workflows/ci-cd.yml
  V2.UI.3:
    status: done
    evidence:
      - evals/product-v2/v2.ui.3-frontend-20261001-025613-final.txt
      - evals/product-v2/v2.ui.3-frontend-20261001-025613-final.json
      - evals/product-v2/v2.ui.3-frontend-20261001-030253.txt
      - evals/product-v2/evidence/v2.ui.3-frontend-20261001-025613-final-home.png
      - evals/product-v2/evidence/v2.ui.3-frontend-20261001-025613-final-drill.png
      - evals/product-v2/evidence/v2.ui.3-frontend-20261001-025613-final-narrow.png
      - tools/verify_v2_ui_3_frontend.py
      - app/product_v2/app.js
      - app/product_v2/index.html
      - app/product_v2/styles.css
      - app/product_v2/ui/stage-shell.js
      - app/product_v2/workspace.js
      - .github/workflows/ci-cd.yml
  V2.5.5:
    status: done
    evidence:
      - evals/product-v2/v2.5.5-suite-review-20261001-034436-final.txt
      - evals/product-v2/v2.5.5-suite-review-20261001-034436-final.json
      - evals/product-v2/evidence/v2.5.5-suite-review-20261001-034436-final-current.png
      - evals/product-v2/evidence/v2.5.5-suite-review-20261001-034436-final-rerun.png
      - evals/product-v2/evidence/v2.5.5-suite-review-20261001-034436-final-unknown.png
      - tools/verify_v2_5_5_suite_review.py
      - evals/product-v2/harness/suite-review-contract.js
      - app/product_v2/domain/suite-review.js
      - app/product_v2/workspace.js
      - app/product_v2_server.py
      - src/providers/v2_suite_review.py
      - src/providers/v2_dashscope_suite_review.py
      - src/providers/v2_fake_suite_review.py
      - .github/workflows/ci-cd.yml
  V2.6.2:
    status: done
    evidence:
      - evals/product-v2/v2.6.2-delivery-20261001-042122-final.txt
      - evals/product-v2/v2.6.2-delivery-20261001-042122-final.json
      - evals/product-v2/evidence/v2.6.2-delivery-20261001-042122-final-gate-pass.png
      - evals/product-v2/evidence/v2.6.2-delivery-20261001-042122-final-unknown-blocked.png
      - evals/product-v2/evidence/v2.6.2-delivery-20261001-042122-final-unknown-confirmed.png
      - evals/product-v2/evidence/v2.6.2-delivery-20261001-042122-final-after-reload.png
      - evals/product-v2/evidence/v2.6.2-delivery-20261001-042122-final-hash-missing.png
      - README.md
      - tools/verify_v2_6_2_delivery.py
      - evals/product-v2/harness/delivery-gate-contract.js
      - evals/product-v2/harness/delivery-gate-contract.html
      - app/product_v2/domain/export-gate.js
      - app/product_v2/domain/review.js
      - app/product_v2/domain/shared.js
      - app/product_v2/domain/index.js
      - app/product_v2/workspace.js
      - app/product_v2/index.html
      - app/product_v2/styles.css
      - src/providers/v2_fake_image.py
      - .github/workflows/ci-cd.yml
  V2.6.3:
    status: done
    evidence:
      - evals/product-v2/v2.6.3-transfer-20261001-050133-final.txt
      - evals/product-v2/v2.6.3-transfer-20261001-050133-final.json
      - evals/product-v2/evidence/v2.6.3-transfer-20261001-050133-final-a-exported.png
      - evals/product-v2/evidence/v2.6.3-transfer-20261001-050133-final-b-imported.png
      - evals/product-v2/evidence/v2.6.3-transfer-20261001-050133-final-b-opened.png
      - evals/product-v2/evidence/v2.6.3-transfer-20261001-050133-final-b-rework-form.png
      - evals/product-v2/evidence/v2.6.3-transfer-20261001-050133-final-b-reworked.png
      - evals/product-v2/evidence/v2.6.3-transfer-20261001-050133-final-b-deliver.png
      - tools/verify_v2_6_3_project_transfer.py
      - evals/product-v2/harness/project-package-contract.js
      - evals/product-v2/harness/project-package-contract.html
      - app/product_v2/storage/package.js
      - app/product_v2/storage/package-migrations.js
      - app/product_v2/storage/transfer.js
      - app/product_v2/storage/index.js
      - app/product_v2/app.js
      - tools/verify_v2_1_3_project_package.py
      - evals/product-v2/v2.1.3-project-package-20261001-050001.txt
      - .github/workflows/ci-cd.yml
      - README.md
  V2.6.4:
    status: done
    evidence:
      - evals/product-v2/v2.6.4-a11y-20261001-052757-final.txt
      - evals/product-v2/v2.6.4-a11y-20261001-052757-final.json
      - evals/product-v2/evidence/v2.6.4-a11y-20261001-052757-final-home.png
      - evals/product-v2/evidence/v2.6.4-a11y-20261001-052757-final-keyboard-created.png
      - evals/product-v2/evidence/v2.6.4-a11y-20261001-052757-final-busy.png
      - evals/product-v2/evidence/v2.6.4-a11y-20261001-052757-final-review.png
      - evals/product-v2/evidence/v2.6.4-a11y-20261001-052757-final-deliver.png
      - evals/product-v2/evidence/v2.6.4-a11y-20261001-052757-final-narrow-390.png
      - evals/product-v2/evidence/v2.6.4-a11y-20261001-052757-final-zoom-200.png
      - evals/product-v2/evidence/v2.6.4-a11y-20261001-052757-final-drill.png
      - tools/verify_v2_6_4_accessibility.py
      - evals/product-v2/vendor/axe-core.min.js
      - evals/product-v2/vendor/axe-core.LICENSE.txt
      - tools/check_docs.py
      - docs/product-v2-project-context.md
      - app/product_v2/workspace.js
      - app/product_v2/index.html
      - app/product_v2/styles.css
      - .github/workflows/ci-cd.yml
      - README.md
  V2.6.5:
    status: done
    evidence:
      - evals/product-v2/v2.6.4-a11y-20261001-055317-v265-final.txt
      - evals/product-v2/v2.6.4-a11y-20261001-055317-v265-final.json
      - evals/product-v2/v2.6.4-a11y-20261001-055253-red-proof-old-layout.txt
      - evals/product-v2/evidence/v2.6.4-a11y-20261001-055317-v265-final-ref-card-1440.png
      - evals/product-v2/evidence/remote-real-e2e-20261001-054352-v2.7.2-arrears-retry-failure.png
      - tools/verify_v2_6_4_accessibility.py
      - app/product_v2/styles.css
  V2.6.6:
    status: done
    evidence:
      - evals/product-v2/v2.6.4-a11y-20261001-060452-v266-red-proof.txt
      - evals/product-v2/v2.6.4-a11y-20261001-060452-v266-red-proof.json
      - evals/product-v2/v2.6.4-a11y-20261001-060920-v266-final4.txt
      - evals/product-v2/v2.6.4-a11y-20261001-060920-v266-final4.json
      - evals/product-v2/evidence/v2.6.4-a11y-20261001-060920-v266-final4-review.png
      - evals/product-v2/evidence/v2.6.4-a11y-20261001-060920-v266-final4-review-390.png
      - tools/verify_v2_6_4_accessibility.py
      - app/product_v2/styles.css
  V2.6.7:
    status: done
    evidence:
      - evals/product-v2/v2.ui.3-frontend-20261001-065851-v267-red.txt
      - evals/product-v2/v2.ui.3-frontend-20261001-065851-v267-red.json
      - evals/product-v2/v2.ui.3-frontend-20261001-065959-v267-green.txt
      - evals/product-v2/v2.ui.3-frontend-20261001-065959-v267-green.json
      - evals/product-v2/v2.5.5-suite-review-20261001-065917-v267-red.txt
      - evals/product-v2/v2.5.5-suite-review-20261001-070024-v267-green.txt
      - evals/product-v2/v2.5.5-suite-review-20261001-070024-v267-green.json
      - evals/product-v2/evidence/v2.ui.3-frontend-20261001-065959-v267-green-deliver.png
      - app/product_v2/workspace.js
      - tools/verify_v2_ui_3_frontend.py
      - tools/verify_v2_5_5_suite_review.py
  V2.6.8:
    status: done
    evidence:
      - evals/product-v2/v2.4.1-large-ref-red-proof-20261001-073024.json
      - evals/product-v2/v2.4.1-image-gateway-20261001-073247-v268-green.txt
      - evals/product-v2/v2.4.1-image-gateway-20261001-073247-v268-green.json
      - evals/product-v2/v273-rehearsal-20261001-072035-crash.json
      - evals/product-v2/v273-rehearsal-20261001-073329.md
      - evals/product-v2/v273-rehearsal-20261001-073329.json
      - tools/rehearse_v273_walkthrough.py
      - tools/verify_v2_4_1_image_gateway.py
      - app/product_v2_server.py
      - app/product_v2/workspace.js
  V2.6.9:
    status: done
    evidence:
      - evals/product-v2/v2.ui.3-frontend-20261001-073741-v269-red.txt
      - evals/product-v2/v2.ui.3-frontend-20261001-073741-v269-red.json
      - evals/product-v2/v2.ui.3-frontend-20261001-073811-v269-green.txt
      - evals/product-v2/v2.ui.3-frontend-20261001-073811-v269-green.json
      - evals/product-v2/evidence/v2.ui.3-frontend-20261001-073811-v269-green-understand.png
      - evals/product-v2/v2.2.3-intake-understanding-20261001-073929-v269.txt
      - evals/product-v2/v2.2.3-intake-understanding-20261001-073929-v269.json
      - evals/product-v2/v2.6.4-a11y-20261001-073942-v269.txt
      - evals/product-v2/v2.6.4-a11y-20261001-073942-v269.json
      - evals/product-v2/v273-rehearsal-20261001-074015.md
      - evals/product-v2/v273-rehearsal-20261001-074015.json
      - app/product_v2/workspace.js
      - tools/verify_v2_ui_3_frontend.py
  V2.6.10:
    status: done
    evidence:
      - evals/product-v2/v2.3.5-pre-generation-confirm-20261001-074628-v2610-red.txt
      - evals/product-v2/v2.3.5-pre-generation-confirm-20261001-074628-v2610-red.json
      - evals/product-v2/v2.3.5-pre-generation-confirm-20261001-074714-v2610-green.txt
      - evals/product-v2/v2.3.5-pre-generation-confirm-20261001-074714-v2610-green.json
      - evals/product-v2/v2.ui.3-frontend-20261001-074726-v2610.txt
      - evals/product-v2/v2.ui.3-frontend-20261001-074726-v2610.json
      - evals/product-v2/v273-rehearsal-20261001-074743.md
      - evals/product-v2/v273-rehearsal-20261001-074743.json
      - evals/product-v2/evidence/v273-rehearsal-20261001-074743-generate-confirm.png
      - app/product_v2/workspace.js
      - tools/verify_v2_3_5_pre_generation_confirm.py
  V2.6.11:
    status: done
    evidence:
      - evals/product-v2/v273-rehearsal-20261001-080059.json
      - evals/product-v2/evidence/v273-rehearsal-20261001-080059-deliver.png
      - evals/product-v2/v2.6.2-delivery-20261001-080658.txt
      - evals/product-v2/v2.6.2-delivery-20261001-080658.json
      - evals/product-v2/evidence/v2.6.2-delivery-20261001-080658-suite-missing.png
      - evals/product-v2/v273-rehearsal-20261001-083137.md
      - evals/product-v2/v273-rehearsal-20261001-083137.json
      - evals/product-v2/v273-rehearsal-20261001-083209.md
      - evals/product-v2/v273-rehearsal-20261001-083209.json
      - evals/product-v2/v273-rehearsal-20261001-083223.md
      - evals/product-v2/v273-rehearsal-20261001-083223.json
      - evals/product-v2/evidence/v273-rehearsal-20261001-083137-vlm-review.png
      - evals/product-v2/evidence/v273-rehearsal-20261001-083137-rework-compare.png
      - evals/product-v2/evidence/v273-rehearsal-20261001-083137-deliver-exported.png
      - evals/product-v2/v2.ui.3-frontend-20261001-080422-v273-prep.txt
      - evals/product-v2/v2.ui.3-frontend-20261001-080422-v273-prep.json
      - evals/product-v2/v2.5.5-suite-review-20261001-080457.txt
      - evals/product-v2/v2.5.5-suite-review-20261001-080457.json
      - evals/product-v2/v2.5.4-rework-loop-20261001-080740v273-prep.txt
      - evals/product-v2/v2.5.4-rework-loop-20261001-080740v273-prep.json
      - evals/product-v2/v2.6.1-selection-20261001-080751.txt
      - evals/product-v2/v2.6.1-selection-20261001-080751.json
      - evals/product-v2/v2.5.3-compare-panel-20261001-080809.txt
      - evals/product-v2/v2.5.3-compare-panel-20261001-080809.json
      - app/product_v2/workspace.js
      - tools/verify_v2_6_2_delivery.py
      - tools/verify_v2_ui_3_frontend.py
      - tools/rehearse_v273_walkthrough.py
  V2.6.12:
    status: done
    evidence:
      - evals/product-v2/v2.6.2-delivery-20261001-081609-v2612-red.txt
      - evals/product-v2/v2.6.2-delivery-20261001-081609-v2612-red.json
      - evals/product-v2/v2.6.2-delivery-20261001-081642-v2612-green.txt
      - evals/product-v2/v2.6.2-delivery-20261001-081642-v2612-green.json
      - evals/product-v2/v273-rehearsal-20261001-083137.md
      - evals/product-v2/v273-rehearsal-20261001-083137.json
      - evals/product-v2/v273-rehearsal-20261001-083209.json
      - evals/product-v2/v273-rehearsal-20261001-083223.json
      - app/product_v2/workspace.js
      - tools/verify_v2_6_2_delivery.py
      - tools/rehearse_v273_walkthrough.py
  V2.6.13:
    status: done
    evidence:
      - evals/product-v2/v2.3.5-pre-generation-confirm-20261001-083557-v2613-red.txt
      - evals/product-v2/v2.3.5-pre-generation-confirm-20261001-083557-v2613-red.json
      - evals/product-v2/v2.3.5-pre-generation-confirm-20261001-083623-v2613-green.txt
      - evals/product-v2/v2.3.5-pre-generation-confirm-20261001-083623-v2613-green.json
      - evals/product-v2/v2.3.4-prompt-compiler-20261001-083641.txt
      - evals/product-v2/v2.3.6-prompt-manual-edit-20261001-083650.txt
      - evals/product-v2/v2.ui.3-frontend-20261001-083746-v2613.txt
      - evals/product-v2/v2.ui.3-frontend-20261001-083746-v2613.json
      - evals/product-v2/v273-rehearsal-20261001-083716.md
      - evals/product-v2/v273-rehearsal-20261001-083716.json
      - evals/product-v2/evidence/v273-rehearsal-20261001-083716-generate-confirm.png
      - app/product_v2/domain/prompt.js
      - tools/verify_v2_3_5_pre_generation_confirm.py
  V2.7.1:
    status: done
    evidence:
      - evals/product-v2/v2.7.1-regression-20261001-0633-final.txt
      - evals/product-v2/v2.7.1-regression-20261001-0633-final.json
      - evals/product-v2/v2.7.1-regression-20261001-061430-final.txt
      - evals/product-v2/v2.7.1-regression-20261001-061430-final.json
      - tools/verify_v2_7_1_regression.py
      - evals/probes/docs_index.py
      - evals/probes/project_state.py
      - tools/verify_v2_1_2_project_home.py
next_action_task: V2.7.2
blockers: []
unknowns:
  - visual_language_review_detection_quality_is_uncalibrated_channels_and_binding_only_proven_in_V2.5.2
  - ui_information_hierarchy_primary_action_image_comparison_and_visual_direction_self_reviewed_20261001_owner_walkthrough_deferred_to_final_human_gate
  - dashscope_balance_arrears_20261001T0433_remote_real_e2e_blocked_at_semantic_step
    upstream_account_arrears_evidence_evals_product_v2_evidence_remote-real-e2e-20261001-043317-lamp01-failure.png
    retry_after_topup_before_claiming_v2_7_2_gate
updated_at: 2026-10-01T08:38:30+08:00
```
