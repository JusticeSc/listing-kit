# Product V1 执行状态

> CONTROL-STATUS: superseded · AUTHORITY: none  
> **历史执行快照；当前状态只看 `_working/amz-listing-kit-product-demo/state.md`。**
>
> 本文件只回答上一轮 Product V1 当时推进到哪；不得据此选择现在的下一步。
> 目标与范围、完成指标、阶段门禁的正文都在
> `docs/product-v1-goal-and-implementation-plan.md` —— 本文**只引用，不重抄**。
> 同一件事有两份正文，就有两份会各自漂。
>
> 守卫 `python tools/check_project_state.py`（J0–J9）；
> 反向对照 `python evals/probes/project_state.py`。

```yaml
task_id: amz-listing-kit-product-v1
status: superseded
goal_binding: required
goal_id: 01a0ca17-2179-7eb0-969a-af9c79c4d8ca
plan_ref: docs/product-v1-goal-and-implementation-plan.md
phases:
  - id: "-1"
    status: done
    gate: G-1
    gate_evidence:
      - evals/control_plane_calibration.txt
  - id: "0"
    status: done
    gate: G0
    gate_evidence:
      - evals/phase0_gate_audit.txt
      - evals/phase0_foundation_calibration.txt
      - evals/phase0_regress_fresh.txt
      - evals/last_regress.txt
      - evals/control_plane_calibration.txt
      - evals/v2_baseline_manifest.json
  - id: "1"
    status: superseded
    gate: G1
    gate_evidence: []
  - id: "2"
    status: pending
    gate: G2
    gate_evidence: []
  - id: "3"
    status: pending
    gate: G3
    gate_evidence: []
  - id: "4"
    status: pending
    gate: G4
    gate_evidence: []
  - id: "5"
    status: pending
    gate: G5
    gate_evidence: []
  - id: "6"
    status: pending
    gate: G6
    gate_evidence: []
  - id: "7"
    status: pending
    gate: G7
    gate_evidence: []
  - id: "8"
    status: pending
    gate: G8
    gate_evidence: []
tasks:
  - id: P-1.1
    status: done
    depends_on: []
    evidence:
      - docs/INDEX.md
      - tools/check_docs.py
  - id: P-1.2
    status: done
    depends_on:
      - P-1.1
    evidence:
      - docs/INDEX.md
  - id: P-1.3
    status: done
    depends_on:
      - P-1.2
    evidence:
      - tools/check_project_state.py
  - id: P-1.4
    status: done
    depends_on:
      - P-1.3
    evidence:
      - evals/probes/project_state.py
      - evals/control_plane_calibration.txt
  - id: P-1.5
    status: done
    depends_on:
      - P-1.3
    evidence:
      - _working/amz-listing-kit-product-v1/state.md
  - id: P0.1
    status: done
    depends_on:
      - P-1.5
    evidence:
      - requirements.txt
      - README.md
      - evals/phase0_foundation_calibration.txt
  - id: P0.2
    status: done
    depends_on:
      - P0.1
    evidence:
      - src/console.py
      - evals/control_plane_calibration.txt
      - evals/phase0_foundation_calibration.txt
  - id: P0.3
    status: done
    depends_on:
      - P0.2
    evidence:
      - evals/phase0_regress_fresh.txt
      - evals/last_regress.txt
      - out/B0FULLSET01_20260923-125218-258886/plan.json
      - out/B0FULLSET01_20260923-125218-258886/run.jsonl
  - id: P0.4
    status: done
    depends_on:
      - P0.3
    evidence:
      - README.md
      - docs/product-v1-goal-and-implementation-plan.md
      - tools/check_docs.py
      - evals/probes/docs_index.py
  - id: P0.5
    status: done
    depends_on:
      - P0.4
    evidence:
      - tools/snapshot_v2_baseline.py
      - evals/v2_baseline_manifest.json
      - evals/v2_baseline_snapshot.txt
      - evals/phase0_gate_audit.txt
  - id: P1.1
    status: done
    depends_on:
      - P0.5
    evidence:
      - contracts/product-facts-v1.schema.json
      - src/product_facts.py
      - tools/verify_p1_1_contract.py
      - evals/product-v1/p1/p1.1-contract.txt
  - id: P1.2
    status: pending
    depends_on:
      - P1.1
    evidence:
      - contracts/data-policy-v1.yaml
      - src/data_policy.py
      - tools/verify_p1_2_policy.py
      - evals/product-v1/p1/p1.2-policy.txt
  - id: P1.3
    status: done
    depends_on:
      - P1.1
    evidence:
      - contracts/review-checklist-v1.yaml
      - src/review_contract.py
      - tools/verify_p1_3_review.py
      - evals/product-v1/p1/p1.3-review.txt
  - id: P1.4
    status: pending
    depends_on:
      - P1.2
      - P1.3
    evidence:
      - pilot/pilot-registry.yaml
      - src/pilot_registry.py
      - tools/check_pilot_ready.py
      - tools/verify_p1_4_registry.py
      - evals/product-v1/p1/p1.4-registry.txt
  - id: P1.5
    status: pending
    depends_on:
      - P1.3
      - P1.4
    evidence:
      - evals/product-v1/dataset/manifest.jsonl
      - evals/product-v1/dataset/dataset.json
      - evals/product-v1/dataset/labels/_working.jsonl
      - src/eval_dataset.py
      - tools/freeze_dataset_labels.py
      - tools/check_dataset_ready.py
      - tools/verify_p1_5_dataset.py
      - evals/product-v1/p1/p1.5-dataset.txt
next_action_task: P1.2
blockers: []
unknowns:
  - 首 5 个 SKU 跑完后，单任务成本上限与完成时间上限要由用户冻结（Gate G7 的 Checkpoint C7）
  - 主品类 / 验证品类 / 20 个 SKU 清单 / 第二名操作员尚未登记（它是 P1.4 的完成条件；实现已落地，`tools/check_pilot_ready.py` 现在如实报 0/20）
  - 允许接收商品参考图的 provider allowlist 尚未批准（无它不得发起真实参考图调用）；它是 P1.2 的完成条件（实现已落地，未签署时一次外发都不会发生；所以 P1.2 只能记 pending，而下一动作就是拿这次签字）
  - Golden/Counterexample 数据集现在只有 5 条样例、0 条进统计：要真实试点样本，还要有人登记为标签人（`dataset.json` 的 `labelers`）；它是 P1.5 的完成条件（实现已落地，`tools/check_dataset_ready.py` 现在如实报『还没齐』）
failures: []
updated_at: 2026-09-23T18:16:23+08:00
```
