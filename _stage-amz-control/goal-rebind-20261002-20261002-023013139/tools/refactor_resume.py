#!/usr/bin/env python
"""只读恢复 Product V2 重构；计划/状态/Goal 文本均来自已登记的仓库权威。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
import yaml

from check_docs import Report as DocReport, _check_docs_index
from check_project_state import (
    ROOT, GATE_DECL, PHASE_HEAD, TASK_ID_RE, YAML_BLOCK,
    Report as StateReport, _check, _plan_tasks,
)


def packet() -> dict:
    docs, states = DocReport(), StateReport()
    _check_docs_index(docs)
    _check(states)
    errors = docs.problems + states.problems
    if errors:
        raise ValueError("\n".join(errors))
    index = (ROOT / "docs/INDEX.md").read_text(encoding="utf-8")
    owners = {}
    for line in index.splitlines():
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) == 5 and cells[2] in {"产品目标", "执行状态"}:
            if cells[3] != "current":
                raise ValueError("恢复权威必须 current：" + cells[0])
            owners[cells[2]] = cells[0]
    paths = {kind: (ROOT / rel).resolve() for kind, rel in owners.items()}
    if set(paths) != {"产品目标", "执行状态"} or any(not p.is_relative_to(ROOT) for p in paths.values()):
        raise ValueError("缺唯一目标/状态或路径越出仓库")
    state = yaml.safe_load(YAML_BLOCK.search(paths["执行状态"].read_text(encoding="utf-8")).group(1))
    if state["plan_ref"] != owners["产品目标"]:
        raise ValueError("state.plan_ref 与 INDEX 目标不一致")
    text = paths["产品目标"].read_text(encoding="utf-8")
    ids, deps = _plan_tasks(text)
    phases, gates = PHASE_HEAD.findall(text), set(GATE_DECL.findall(text))
    membership = {}
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and TASK_ID_RE.fullmatch(cells[0]):
            if cells[0] in membership:
                raise ValueError("任务在表中重复声明：" + cells[0])
            if len(cells) != 6 or cells[3] not in phases:
                raise ValueError("任务缺明确 Phase 映射：" + cells[0])
            membership[cells[0]] = cells[3]
    if set(ids) != set(state["task_progress"]) or set(phases) != set(state["phase_progress"]):
        raise ValueError("state 的任务/阶段清单与计划不完整相等")
    graph = {tid: deps[tid] for tid in ids}
    graph.update({gate: [tid for tid, phase in membership.items() if gate == "G" + phase] for gate in gates})
    visiting, visited = set(), set()

    def visit(node: str) -> None:
        if node not in graph:
            raise ValueError("依赖未声明：" + node)
        if node in visiting:
            raise ValueError("依赖存在环：" + node)
        if node in visited:
            return
        visiting.add(node)
        for dep in graph[node]:
            visit(dep)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
    for phase, row in state["phase_progress"].items():
        if row["status"] == "done" and any(state["task_progress"][tid]["status"] != "done" for tid in graph["G" + phase]):
            raise ValueError("Gate 先于其任务宣称完成：G" + phase)
    next_id = state.get("next_action_task")
    if not next_id:
        raise ValueError("记录没有可恢复的下一动作；完成态应阅读最终审计")
    card = re.search(r"^### " + re.escape(next_id) + r"\s.*?(?=^#{1,3} |\Z)", text, re.M | re.S)
    goal = re.search(r"^### 2\.1 .*?^```text\n(.*?)^```", text, re.M | re.S)
    if not card or not goal or not goal.group(1).strip():
        raise ValueError("下一任务卡或完整拟建 Goal 原文缺失")
    for tid in ids:
        if len(re.findall(r"^### " + re.escape(tid) + r"\s", text, re.M)) != 1:
            raise ValueError("任务必须有且只有一张详细卡：" + tid)
    return {"status": state["status"], "goal_binding": state["goal_binding"], "goal_id": state.get("goal_id"),
            "plan": owners["产品目标"], "state": owners["执行状态"], "next_action_task": next_id,
            "task_card_line": text[:card.start()].count("\n") + 1,
            "goal_source_line": text[:goal.start()].count("\n") + 1,
            "goal_pending_reason": state.get("goal_pending_reason"),
            "goal_binding_evidence": state.get("goal_binding_evidence"),
            "unknowns": state.get("unknowns", []),
            "task_card": card.group(0).strip(), "goal_text": goal.group(1).strip(),
            "goal_sha256": hashlib.sha256(goal.group(1).strip().encode("utf-8")).hexdigest(),
            "phase_count": len(phases), "task_count": len(ids), "blockers": state.get("blockers", []),
            "prepared_gate": "未绑定前禁止产品施工、真实模型调用、部署和V1日落" if state["status"] == "prepared" else None,
            "read_only": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--json", action="store_true", help="输出恢复包与原文，适合无会话消费者")
    group.add_argument("--goal-text", action="store_true", help="只输出计划中的完整拟建 Goal 原文")
    args = parser.parse_args()
    try:
        data = packet()
    except (KeyError, AttributeError, ValueError, OSError, yaml.YAMLError) as error:
        print("[FAIL] 无法安全恢复：" + str(error), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.goal_text:
        print(data["goal_text"])
    else:
        print(f"[PASS] 冷恢复：{data['phase_count']} 阶段 / {data['task_count']} 任务；状态 {data['status']}")
        print("目标：" + data["plan"] + "；状态：" + data["state"])
        print("唯一下一动作：" + data["next_action_task"])
        print(f"任务卡：{data['plan']}:{data['task_card_line']}")
        print("Goal 原文：计划 §2.1；sha256=" + data["goal_sha256"])
        if data["goal_binding"] == "session":
            evidence = data.get("goal_binding_evidence")
            print("会话绑定：本轮已读真实当前 Goal（"
                  + str(data["status"]) + "）；证据：" + str(evidence)
                  + "；goal_id 为 null —— 接口拿不到 ID，不虚构，也不以缺 UUID 阻塞离线工作")
        if data["prepared_gate"]:
            print("权限门：" + data["prepared_gate"])
        print(data["task_card"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
