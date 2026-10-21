#!/usr/bin/env python
"""只读恢复 Product V2 重构；计划/状态/Goal 文本均来自已登记的仓库权威。read_only恒true仅表示脚本自身无写入，不作为授权判断。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys

sys.dont_write_bytecode = True
import yaml

from check_docs import Report as DocReport, _check_docs_index
from check_project_state import (
    ROOT, GATE_DECL, PHASE_HEAD, TASK_ID_RE, YAML_BLOCK,
    Report as StateReport, _check, _plan_tasks,
)


CURRENT_BOUNDARY_HEADING = re.compile(r"^##\s+当前恢复边界\s*$")
_NEXT_H2 = re.compile(r"^##\s+\S")
_YAML_FENCE = re.compile(r"^```yaml\s*$")
_HANDOFF_MARKER = "交接阅读边界"


def _current_boundary_section(state_text: str) -> tuple[str | None, int | None, int | None]:
    """定位当前恢复边界H2原文的纯解析投影，仅用于显示。

    从 `## 当前恢复边界` 起完整截取至下一H2或 ```yaml 围栏；无下一H2的旧单节
    记录则截取至交接标记行（含该行），保留段间空行，不做过期过滤或许可推导。
    无该H2或内容为空时返回全None。返回 (正文|None, 标题行|None, 末行|None)，行号1-based。
    """
    lines = state_text.splitlines()
    head = next((i for i, line in enumerate(lines) if CURRENT_BOUNDARY_HEADING.match(line)), None)
    if head is None:
        return None, None, None
    term = len(lines)
    has_next_h2 = False
    for j in range(head + 1, len(lines)):
        if _NEXT_H2.match(lines[j]):
            term = j
            has_next_h2 = True
            break
        if _YAML_FENCE.match(lines[j]):
            term = j
            break
    end = term - 1
    if not has_next_h2:
        for j in range(head + 1, term):
            if _HANDOFF_MARKER in lines[j] and lines[j].strip().startswith("**"):
                end = j
                break
    start_content = head + 1
    while start_content <= end and not lines[start_content].strip():
        start_content += 1
    while end >= start_content and not lines[end].strip():
        end -= 1
    if end < start_content:
        return None, None, None
    text = "\n".join(lines[start_content:end + 1])
    if not text.strip():
        return None, None, None
    return text, head + 1, end + 1


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
    state_text = paths["执行状态"].read_text(encoding="utf-8")
    state_match = YAML_BLOCK.search(state_text)
    state = yaml.safe_load(state_match.group(1))
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
    boundary_text, boundary_start, boundary_end = _current_boundary_section(state_text)
    matched = [b for b in state.get("blockers", []) if isinstance(b, str) and b.startswith(str(next_id) + "_")]
    boundary_sha = hashlib.sha256(boundary_text.encode("utf-8")).hexdigest() if boundary_text is not None else None
    return {"status": state["status"], "goal_binding": state["goal_binding"], "goal_id": state.get("goal_id"),
            "plan": owners["产品目标"], "state": owners["执行状态"], "next_action_task": next_id,
            "next_action_status": (state.get("task_progress", {}).get(next_id) or {}).get("status", "pending"),
            "task_card_line": text[:card.start()].count("\n") + 1,
            "goal_source_line": text[:goal.start()].count("\n") + 1,
            "goal_pending_reason": state.get("goal_pending_reason"),
            "goal_binding_evidence": state.get("goal_binding_evidence"),
            "unknowns": state.get("unknowns", []),
            "task_card": card.group(0).strip(), "goal_text": goal.group(1).strip(),
            "goal_sha256": hashlib.sha256(goal.group(1).strip().encode("utf-8")).hexdigest(),
            "phase_count": len(phases), "task_count": len(ids), "blockers": state.get("blockers", []),
            "prepared_gate": "未绑定前禁止产品施工、真实模型调用、部署和V1日落" if state["status"] == "prepared" else None,
            "read_only": True,
            "has_current_boundary": boundary_text is not None,
            "recovery_boundary_text": boundary_text,
            "recovery_boundary_start_line": boundary_start,
            "recovery_boundary_end_line": boundary_end,
            "recovery_boundary_sha256": boundary_sha,
            "matched_blockers": matched}


def _format_default(data: dict) -> str:
    """默认输出的纯格式化：先当前恢复门与matched blocker，再位置与历史观察，不印整卡。

    仅显示，不从自然语言推导许可；read_only仅表示脚本自身无写入。
    """
    out: list[str] = []
    out.append(f"[PASS] 冷恢复：{data['phase_count']} 阶段 / {data['task_count']} 任务；状态 {data['status']}")
    out.append("目标：" + str(data["plan"]) + "；状态：" + str(data["state"]))
    if data.get("has_current_boundary") and isinstance(data.get("recovery_boundary_text"), str):
        out.append(f"当前恢复边界原文（仅显示，不推导许可）：{data['state']}:{data.get('recovery_boundary_start_line')}-{data.get('recovery_boundary_end_line')}；sha256={data.get('recovery_boundary_sha256')}")
        out.append(str(data["recovery_boundary_text"]))
    else:
        out.append("当前恢复边界：无摘要（该记录无current段，历史/受控记录）；仍保留下方blocker，不得作为执行依据。")
    out.append(f"机器块登记下一动作（须结合当前恢复边界与blocker，非施工授权）：{data['next_action_task']}（状态 {data.get('next_action_status')}）")
    matched = data.get("matched_blockers")
    if matched is None:
        matched = [b for b in (data.get("blockers") or []) if isinstance(b, str) and b.startswith(str(data["next_action_task"]) + "_")]
    if data.get("next_action_status") == "blocked":
        out.append("下一任务被阻塞；只可解决以下权限/输入门，不得开始该任务的受限执行：")
        for blocker in matched:
            out.append("  " + str(blocker))
    elif matched:
        out.append("匹配下一任务的blocker（约束保留，未自动归档）：")
        for blocker in matched:
            out.append("  " + str(blocker))
    for blocker in data.get("blockers") or []:
        if blocker not in matched:
            out.append("其他登记blocker（约束保留）：" + str(blocker))
    out.append(f"任务卡位置：{data['plan']}:{data['task_card_line']}（完整卡请用 --json 获取，默认不打印）")
    out.append("Goal 原文来源：计划 §2.1；sha256=" + str(data["goal_sha256"]) + "（完整原文请用 --json/--goal-text 获取）")
    if data.get("goal_binding") in ("session", "required"):
        out.append("仓库保存的最近 Goal 观察（历史性质，非当前系统Goal）："
                   + str(data["status"]) + "；绑定：" + str(data["goal_binding"])
                   + "；goal_id=" + str(data.get("goal_id")) + "；证据：" + str(data.get("goal_binding_evidence")))
        out.append("本脚本不查询系统 Goal；恢复会话仍须读取真实当前 Goal 核对。")
    if data.get("prepared_gate"):
        out.append("权限门：" + str(data["prepared_gate"]))
    out.append("read_only=true 仅表示本脚本自身无写入，不作为授权或执行许可判断。")
    out.append("完整任务卡/Goal/全部unknowns与blockers请用 --json 获取；--goal-text 仅取Goal原文。")
    return "\n".join(out)


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
        print(_format_default(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
