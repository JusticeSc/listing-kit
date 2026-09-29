# amz-listing-kit 需求重新基线状态

> CONTROL-STATUS: superseded · AUTHORITY: none  
> **历史需求发现快照；当前产品合同已经进入完整演示产品计划。**
>
> 本文件只记录当时的阶段、任务、证据指针和下一动作。需求正文与决定当时由
> `docs/drafts/requirements-analysis-2026-09-24.md` 统一管辖。

```yaml
task_id: amz-listing-kit-requirements
status: completed
goal_binding: optional
goal_id: null
goal_pending_reason: 需求发现已完成；正式系统 Goal 由后继完整演示产品任务绑定
plan_ref: docs/drafts/requirements-analysis-2026-09-24.md
phases:
  - id: "0"
    status: done
    gate: G0
    gate_evidence:
      - docs/drafts/requirements-analysis-2026-09-24.md
  - id: "1"
    status: done
    gate: G1
    gate_evidence:
      - docs/product-demo-goal-and-implementation-plan.md
tasks:
  - id: R1
    status: done
    depends_on: []
    evidence:
      - docs/drafts/requirements-analysis-2026-09-24.md
  - id: R2
    status: done
    depends_on: [R1]
    evidence:
      - docs/drafts/requirements-analysis-2026-09-24.md
  - id: R3
    status: done
    depends_on: [R2]
    evidence:
      - docs/drafts/requirements-analysis-2026-09-24.md
  - id: R4
    status: done
    depends_on: [R3]
    evidence:
      - docs/drafts/requirements-analysis-2026-09-24.md
  - id: R5
    status: done
    depends_on: [R4]
    evidence:
      - docs/drafts/requirements-analysis-2026-09-24.md
  - id: R6
    status: done
    depends_on: [R5]
    evidence:
      - docs/drafts/requirements-analysis-2026-09-24.md
  - id: R7
    status: done
    depends_on: [R6]
    evidence:
      - docs/drafts/requirements-analysis-2026-09-24.md
  - id: R8
    status: done
    depends_on: [R7]
    evidence:
      - docs/drafts/requirements-analysis-2026-09-24.md
      - examples/input/cup_source.jpg
      - examples/input/cup_closeup.jpg
      - examples/input/cup_contents.jpg
  - id: R9
    status: done
    depends_on: [R8]
    evidence:
      - docs/drafts/requirements-analysis-2026-09-24.md
      - src/imagegen.py
  - id: R10
    status: done
    depends_on: [R9]
    evidence:
      - docs/drafts/requirements-analysis-2026-09-24.md
  - id: R11
    status: done
    depends_on: [R10]
    evidence:
      - docs/drafts/requirements-analysis-2026-09-24.md
  - id: R12
    status: done
    depends_on: [R11]
    evidence:
      - docs/drafts/requirements-analysis-2026-09-24.md
  - id: R13
    status: done
    depends_on: [R12]
    evidence:
      - docs/drafts/requirements-analysis-2026-09-24.md
      - docs/product-demo-goal-and-implementation-plan.md
next_action_task: R13
blockers: []
unknowns: []
updated_at: 2026-09-24T21:30:00+08:00
```
