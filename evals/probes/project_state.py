#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""项目状态守卫的十九向反向对照。

当前状态使用 `amz-project-state/v2`：计划拥有阶段、Gate、任务和依赖；state 只保存
进度、证据与下一动作。本探针逐向植入一种漂移，要求守卫**只**报对应的 J0–J9 tag，
并在 finally 中逐字节恢复原文件。它会短暂改写 current state，必须独占串行运行；
不得与文档守卫、状态守卫或另一份本探针并发。

2026-09-26 的教训（为什么有了受控基线）
----------------------------------------
第一版直接拿**实时 state** 当基线再改。state 从「Phase 0 收尾」推进到「Phase 1 进行中」后，
六条探针同时变红，但**其中没有一条是产品缺陷**：

  * M/O/P 三条找不到替换目标，静默退化成空操作（M 甚至因为「没改坏」而报 rc=0）；
  * C/F 两条多报了 J9 —— 因为实时 state 恰好有一个 active 阶段。

判据挂在「今天恰好在哪一相」上，就会随无关变化变红或变绿。所以现在每条 case 都从
`_normalize()` 产出的**受控基线**出发：身份与结构照抄实时 state，但把"处在哪一相"抹平。
另外每条探针都要自证「确实改动了字节」——没改到东西的探针会伪装成「抓不到」。
"""
from __future__ import annotations

import copy
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
from console import enable_utf8  # noqa: E402

enable_utf8()

from check_project_state import _plan_tasks  # noqa: E402  （「计划里谁依赖谁」只此一处实现）

GUARD = ROOT / "tools" / "check_project_state.py"
YAML_BLOCK = re.compile(r"```yaml\r?\n(.*?)```", re.S)
TAG = re.compile(r"\[J(\d+)\]")


def _current_state() -> Path:
    candidates = []
    for path in sorted((ROOT / "_working").glob("*/state.md")):
        text = path.read_text(encoding="utf-8")
        if ("state_schema: amz-project-state/v2" in text
                and re.search(r"^status: (?:active|paused)$", text, re.M)):
            candidates.append(path)
    if len(candidates) != 1:
        raise RuntimeError(f"需要恰好一份 current v2 状态，实际 {len(candidates)}：{candidates}")
    return candidates[0]


STATE = _current_state()
ORIG_BYTES = STATE.read_bytes()
ORIG_TEXT = ORIG_BYTES.decode("utf-8")
MATCH = YAML_BLOCK.search(ORIG_TEXT)
if not MATCH:
    raise RuntimeError("当前状态没有 yaml 围栏")
ORIG_DATA = yaml.safe_load(MATCH.group(1))
PREFIX = ORIG_TEXT[:MATCH.start(1)]
SUFFIX = ORIG_TEXT[MATCH.end(1):]
PLAN_TEXT = (ROOT / str(ORIG_DATA["plan_ref"])).read_text(encoding="utf-8")
PLAN_TASKS, PLAN_DEPS = _plan_tasks(PLAN_TEXT)

DUP_DIRS = [ROOT / "_working" / "_probe_dup_1",
            ROOT / "_working" / "_probe_dup_2"]


def _normalize(data: dict) -> dict:
    """受控基线：身份与结构照抄实时 state，但把「处在哪一相」抹平。

    抹平之后，C/F 这类「只该报一条」的探针不会因为实时 state 恰好有 active 阶段而多报 J9；
    O/P 这类「制造相位矛盾」的探针也不会因为目标相位已经存在而变成空操作。
    """
    result = copy.deepcopy(data)
    result["status"] = "paused"
    result["system_goal_observed_status"] = "paused"
    phases = result.setdefault("phase_progress", {})
    for pid, row in list(phases.items()):
        if isinstance(row, dict) and row.get("status") == "active":
            phases[pid] = {**row, "status": "pending"}
    return result


BASE = _normalize(ORIG_DATA)
BASE_BYTES = None  # 进入循环后按 _serialize(BASE) 计算


def _serialize(data: dict) -> str:
    body = yaml.safe_dump(data, allow_unicode=True, sort_keys=False,
                          default_flow_style=False, width=1000)
    return PREFIX + body + SUFFIX


def _write(data: dict) -> None:
    STATE.write_text(_serialize(data), encoding="utf-8", newline="\n")


def _make_active(data: dict) -> dict:
    """合法开工形态：记录 active，并给**最早未完成**的阶段开相。

    2026-09-30 的教训：这里以前用 next_action 的 ID 前缀猜相位，前提是
    「任务 ID 前缀 == 阶段」。计划把 V2.6.1（人工 Selection）排到 V2.5.5 之前，
    两者都落在 Gate G5（Phase 5），且明确任务 ID 保留、顺序以依赖为准
    （计划 §9.19 / §10.1）——前缀不再是相位。相位只从阶段推进里读：
    最早未完成的阶段开相，前置阶段天然都已 done。
    """
    result = copy.deepcopy(data)
    result["status"] = "active"
    result["system_goal_observed_status"] = "active"
    phases = result.setdefault("phase_progress", {})
    heads = PLAN_PHASE_HEAD.findall(PLAN_TEXT)
    open_phase = next((pid for pid in heads
                       if (phases.get(pid) or {}).get("status") != "done"), None)
    if open_phase is None:
        raise RuntimeError("所有阶段都已完成，探针无法构造合法开工形态 —— 要更新探针，不是放宽判据")
    phases[open_phase] = {"status": "active", "evidence": []}
    return result


def _pick_task_with_unmet_dep(data: dict) -> str:
    """从计划里挑一个「自己没完成、且至少一个依赖也没完成」的任务。

    为什么不用写死的 ID：写死 D1.C1 这类 ID 时，一旦它变成别人的依赖，
    这条探针就会连带触发 J6。依赖关系只以守卫的计划解析为准。

    依赖语义必须与守卫**完全一致**：`G<n>` 看阶段是否 done，任务依赖看任务是否 done。
    2026-09-26 第七次校准时这里踩过一次 —— 旧实现把 `G1` 也拿去和任务 id 集合比，
    于是它永远"未完成"，探针挑中了一个守卫认为依赖已满足的任务，注入变成空操作
    而报 rc=0。探针与守卫对同一件事的解释不一致时，先红的是探针的可信度。
    """
    done_tasks = {tid for tid, row in (data.get("task_progress") or {}).items()
                  if isinstance(row, dict) and row.get("status") == "done"}
    done_phases = {pid for pid, row in (data.get("phase_progress") or {}).items()
                   if isinstance(row, dict) and row.get("status") == "done"}

    def met(dep: str) -> bool:
        return (dep[1:] in done_phases) if dep.startswith("G") else (dep in done_tasks)

    for tid in PLAN_TASKS:
        if tid in done_tasks:
            continue
        deps = PLAN_DEPS.get(tid) or []
        if any(not met(dep) for dep in deps):
            return tid
    raise RuntimeError("计划里找不到「依赖未完成」的未完成任务，探针需要更新")


PLAN_PHASE_HEAD = re.compile(r"^###\s+Phase\s+(-?\d+(?:\.\d+)?)\s*[：:]", re.M)


def _pick_skipped_phase(data: dict) -> str:
    """挑一个「前置阶段还没完成却被激活」的阶段。

    为什么不再写死 Phase 2：写死就等于假设「Phase 1 还没完成」。项目一旦推进到
    Phase 1 已完成，这条探针会变成空操作并报 rc=0 —— 判据会随进度失效。
    这里改成从计划里推导：找第一个未完成阶段，再选一个在它之后的未完成阶段。
    """
    heads = PLAN_PHASE_HEAD.findall(PLAN_TEXT)
    done = {pid for pid, row in (data.get("phase_progress") or {}).items()
            if isinstance(row, dict) and row.get("status") == "done"}
    open_idx = [i for i, pid in enumerate(heads) if pid not in done]
    if not open_idx:
        raise RuntimeError("所有阶段都已完成，这条探针无法构造 —— 要更新探针，不是放宽判据")
    first_open = open_idx[0]
    later = [pid for pid in heads[first_open + 1:] if pid not in done]
    if not later:
        raise RuntimeError("第一个未完成阶段之后没有可激活的阶段，探针需要更新")
    return later[-1]


def _run_guard() -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(GUARD)], cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _restore() -> None:
    STATE.write_bytes(ORIG_BYTES)
    for directory in DUP_DIRS:
        if directory.exists():
            shutil.rmtree(directory)


def _mutate(case: str) -> tuple[list[str], bool]:
    """返回 (problems, 是否真的改动了被验对象)。"""
    data = copy.deepcopy(BASE)
    problems: list[str] = []

    if case == "A":
        return problems, False           # 基线：不写盘，直接验实时 state
    if case == "B":
        active = _make_active(data)
        text = _serialize(active)
        for directory in DUP_DIRS:
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "state.md").write_text(text, encoding="utf-8", newline="\n")
        return problems, True
    if case == "C":
        data["status"] = "进行中"
    elif case == "D":
        data["goal_binding"] = "optional"
        data["goal_id"] = None
        data["goal_pending_reason"] = ""
    elif case == "E":
        data.setdefault("phase_progress", {})["999"] = {"status": "pending", "evidence": []}
    elif case == "F":
        data.setdefault("phase_progress", {})["1"] = {"status": "done", "evidence": []}
    elif case == "G":
        data["status"] = "active"
        data["system_goal_observed_status"] = "active"
        skipped = _pick_skipped_phase(data)
        data.setdefault("phase_progress", {})[skipped] = {"status": "active", "evidence": []}
    elif case == "H":
        data.setdefault("task_progress", {})["D999.1"] = {"status": "pending", "evidence": []}
    elif case == "I":
        data.setdefault("task_progress", {})["D1.C1"] = {"status": "done", "evidence": []}
    elif case == "J":
        picked = _pick_task_with_unmet_dep(data)
        if picked == BASE.get("next_action_task"):
            # 基线自己的 next_action 就依赖未完成 ⇒ 这一向注入是空操作，
            # 而被验字节照样变了（序列化差异），旧的自证抓不到它。
            problems.append("探针挑中的任务就是基线的 next_action —— 这一向没有真的注入漂移")
        data["next_action_task"] = picked
    elif case == "K":
        data["next_action_task"] = "D-ZZ.9"
    elif case == "L":
        data["scope"] = {"in": ["重抄的范围正文"]}
    elif case == "M":
        broken = re.sub(r"^status: \S+$", "status: [active", _serialize(BASE),
                        count=1, flags=re.M)
        if broken == _serialize(BASE):
            problems.append("探针没能把 YAML 改坏（替换目标没命中）")
        STATE.write_text(broken, encoding="utf-8", newline="\n")
        return problems, True
    elif case == "N":
        data = _make_active(data)
    elif case == "O":
        # 造「记录说 paused、却有阶段在跑」。用 _make_active 保住
        # next_action 的依赖仍然满足，否则这条会连带触发 J7，违反「只报该报的」。
        data = _make_active(data)
        data["status"] = "paused"
    elif case == "P":
        data["status"] = "active"
        data["system_goal_observed_status"] = "active"
    elif case == "Q":
        data["status"] = "completed"
    elif case == "R":
        data["updated_at"] = (datetime.now(timezone.utc).astimezone()
                              + timedelta(days=2)).isoformat(timespec="seconds")
    elif case == "S":
        data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    else:
        problems.append(f"未知 case {case}")

    before = STATE.read_bytes()
    _write(data)
    return problems, STATE.read_bytes() != before


CASES = [
    ("A", "基线", 0, set()),
    ("B", "两份 active 记录", 1, {"J1"}),
    ("C", "记录状态非法", 1, {"J2"}),
    ("D", "Goal 未绑定且无理由", 1, {"J3"}),
    ("E", "状态引用不存在的阶段", 1, {"J4"}),
    ("F", "阶段 done 但无证据", 1, {"J5"}),
    ("G", "跳过未完成阶段直接激活后面的阶段", 1, {"J5"}),
    ("H", "状态引用不存在的任务", 1, {"J6"}),
    ("I", "任务 done 但无证据", 1, {"J6"}),
    ("J", "next_action 的计划依赖未完成", 1, {"J7"}),
    ("K", "next_action 不存在", 1, {"J7"}),
    ("L", "state 重抄 scope", 1, {"J8"}),
    ("M", "YAML 读不出来", 1, {"J0"}),
    ("N", "合法开工形态", 0, set()),
    ("O", "记录 paused 但 Phase active", 1, {"J9"}),
    ("P", "记录 active 但无 active Phase", 1, {"J9"}),
    ("Q", "靠改记录宣布 completed", 1, {"J9"}),
    ("R", "updated_at 写在两天以后", 1, {"J10"}),
    ("S", "updated_at 没有时区", 1, {"J10"}),
]


def main() -> int:
    if "--count" in sys.argv[1:]:
        print(len(CASES))
        return 0

    bad = 0
    try:
        for code, name, want_rc, want_tags in CASES:
            _restore()
            problems, changed = _mutate(code)
            if code != "A" and not changed:
                problems.append("这个探针没有改动任何被验字节（失效的自检）")
            rc, output = _run_guard()
            tags = {f"J{value}" for value in TAG.findall(output)}
            if rc != want_rc:
                problems.append(f"退出码 {rc}，期望 {want_rc}")
            if tags != want_tags:
                problems.append(f"tag 集合 {sorted(tags)}，期望 {sorted(want_tags)}")
            mark = "OK  " if not problems else "FAIL"
            print(f"[{mark}] {code} {name} -> rc={rc} tags={sorted(tags)}")
            for problem in problems:
                print(f"         {problem}")
                for line in output.splitlines():
                    if line.strip().startswith("✗"):
                        print(f"           | {line.strip()}")
            bad += bool(problems)
    finally:
        _restore()
        if STATE.read_bytes() != ORIG_BYTES:
            print("✗ 还原后与原始字节不一致")
            bad += 1
        else:
            print(f"已逐字节恢复 {STATE.relative_to(ROOT).as_posix()} 并清理探针副本")

    if bad:
        print(f"✗ {bad}/{len(CASES)} 向与预期不符")
        return 1
    print(f"OK：{len(CASES)} 向全部与预期一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
