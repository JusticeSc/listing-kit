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
system_goal_observed_at: 2026-09-29T21:16:19+08:00
plan_ref: docs/product-v2-goal-and-implementation-plan.md
latest_audit: evals/product-v2/v2.4.2-generation-attempt-20260930-112423-final.txt

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
      - evals/product-v2/v2.2.3-workspace-20260930-015817.png
      - evals/product-v2/v2.2.3-narrow-20260930-015817.png
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
      - evals/product-v2/v2.3.6-prompt-manual-edit-20260930-035000.png
      - evals/product-v2/v2.3.5-pre-generation-confirm-20260930-035020-v236-regression.txt
      - evals/product-v2/v2.3.4-prompt-compiler-20260930-035020-v236-regression.txt
      - evals/product-v2/v2.3.2-suite-editor-20260930-035037-v236-regression.txt
      - evals/product-v2/v2.2.3-intake-understanding-20260930-035038-v236-regression.txt
  "4":
    status: active
    evidence:
      - evals/product-v2/v2.4.1-image-gateway-20260930-091224-final.txt
      - evals/product-v2/v2.4.1-image-gateway-20260930-091224-final.json
      - evals/product-v2/v2.4.2-generation-attempt-20260930-112423-final.txt
      - evals/product-v2/v2.4.2-generation-attempt-20260930-112423-final.json
      - evals/product-v2/v2.4.2-generation-attempt-20260930-112423.png

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
      - evals/product-v2/v2.2.3-workspace-20260930-023544.png
      - evals/product-v2/v2.2.3-narrow-20260930-023544.png
      - evals/product-v2/v2.2.3-intake-understanding-20260930-024451.txt
      - evals/product-v2/v2.2.3-intake-understanding-20260930-024451.json
      - evals/product-v2/v2.2.3-workspace-20260930-024451.png
      - evals/product-v2/v2.2.3-narrow-20260930-024451.png
      - evals/product-v2/v2.2.3-intake-understanding-20260930-024645.txt
      - evals/product-v2/v2.2.3-intake-understanding-20260930-024645.json
      - evals/product-v2/v2.2.3-intake-understanding-20260930-025231.txt
      - evals/product-v2/v2.2.3-intake-understanding-20260930-025231.json
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
      - evals/product-v2/v2.3.2-suite-editor-20260930-024451.png
      - evals/product-v2/v2.3.2-suite-editor-20260930-024629.txt
      - evals/product-v2/v2.3.2-suite-editor-20260930-024629.json
      - evals/product-v2/v2.3.2-suite-editor-20260930-024629.png
      - evals/product-v2/v2.3.2-suite-editor-20260930-025222.txt
      - evals/product-v2/v2.3.2-suite-editor-20260930-025222.json
      - evals/product-v2/v2.3.2-suite-editor-20260930-025222.png
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
      - evals/product-v2/v2.3.3-spec-versions-20260930-025205.png
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
      - evals/product-v2/v2.3.4-prompt-compiler-20260930-031626.png
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
      - evals/product-v2/v2.3.5-pre-generation-confirm-20260930-033626.png
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
      - evals/product-v2/v2.3.6-prompt-manual-edit-20260930-035000.png
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
      - evals/product-v2/v2.4.2-generation-attempt-20260930-112423.png
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

next_action_task: V2.4.3
blockers: []
unknowns:
  - visual_language_provider_model_id_is_deferred_to_V2.5.2_and_does_not_block_browser_workspace_work
updated_at: 2026-09-30T11:25:11+08:00
```
