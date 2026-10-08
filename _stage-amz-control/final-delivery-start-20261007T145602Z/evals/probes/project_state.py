#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""项目状态守卫的反向对照。

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

Goal 观察绑定（session 与原生 required）
---------------------------------------
当前 required 绑定核对原样工具 ID；session 只用于接口确实无 ID。
探针只改 `_probe_tmp_evidence.json` 夹具，不改真实观察文件；每向逐字节还原。
合成 ID 仅用于确定性反向对照；真实原生 handle 从实时观察读取。
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))
from console import enable_utf8  # noqa: E402

enable_utf8()

from check_project_state import (  # noqa: E402
    GOAL_BINDING_SESSION, _goal_display_norm, _goal_plan_text,
    _plan_tasks, PHASE_HEAD,
)

GUARD = ROOT / "tools" / "check_project_state.py"
CODE_ROOT = ROOT
_fixture = tempfile.TemporaryDirectory(prefix="amz-state-probe-")
ROOT = Path(_fixture.name)
for source in (CODE_ROOT / "_working").glob("*/state.md"):
    target = ROOT / source.relative_to(CODE_ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    match = YAML_BLOCK.search(source.read_text(encoding="utf-8")) if "YAML_BLOCK" in globals() else re.search(
        r"```yaml\r?\n(.*?)```", source.read_text(encoding="utf-8"), re.S)
    if not match:
        continue
    def copy_references(value):
        if isinstance(value, dict):
            for item in value.values():
                copy_references(item)
        elif isinstance(value, list):
            for item in value:
                copy_references(item)
        elif isinstance(value, str):
            original = (CODE_ROOT / value).resolve()
            if original.is_file() and CODE_ROOT in original.parents:
                copied = ROOT / original.relative_to(CODE_ROOT)
                copied.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, copied)
            elif original.is_dir() and CODE_ROOT in original.parents:
                # evidence 也可以是目录（如 evals/product-v2/fixtures/v2.5.2/ 这类夹具集）；
                # 守卫用 exists() 判存在，临时副本必须复制整棵目录，否则真库里存在的
                # 引用会在副本里变成 J6「指向不存在」，把受控基线和每个反例都污染成假红。
                shutil.copytree(original, ROOT / original.relative_to(CODE_ROOT),
                                dirs_exist_ok=True)
    copy_references(yaml.safe_load(match.group(1)))
YAML_BLOCK = re.compile(r"```yaml\r?\n(.*?)```", re.S)
TAG = re.compile(r"\[J(\d+)\]")


def _current_state() -> Path:
    candidates = []
    for path in sorted((ROOT / "_working").glob("*/state.md")):
        text = path.read_text(encoding="utf-8")
        if ("state_schema: amz-project-state/v2" in text
                and re.search(r"^status: (?:prepared|active|paused)$", text, re.M)):
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
# session 证据的临时夹具：只在这份确定性拷贝里注入漂移，绝不改真实观察文件；
# 每次 _restore() 连字节带文件一起还原。
TMP_EVIDENCE_REL = "evals/product-v2/refactor/_probe_tmp_evidence.json"
TMP_EVIDENCE = ROOT / TMP_EVIDENCE_REL
# 从实时 state 读取本会话观察；不把旧目标的观察硬编码为永远有效的基线。
REAL_EVIDENCE_REL = ORIG_DATA["goal_binding_evidence"]
REAL_EVIDENCE = json.loads((ROOT / REAL_EVIDENCE_REL).read_text(encoding="utf-8"))
PLAN_GOAL = _goal_plan_text(PLAN_TEXT)
PLAN_GOAL_SHA = hashlib.sha256(PLAN_GOAL.encode("utf-8")).hexdigest()

# 探针自证：真实观察证据仍然对得上计划（指纹 + 展示归一）。对不上就不许往下跑，
# 否则 AH/AI 这些「合法形态」会拿脱节的证据当基线。
if REAL_EVIDENCE["objective_sha256"] != PLAN_GOAL_SHA:
    raise RuntimeError("真实观察 objective_sha256 与计划 §2.1 指纹不一致 —— 先修观察证据，探针拒跑")
if _goal_display_norm(REAL_EVIDENCE["observed_objective"]) != _goal_display_norm(PLAN_GOAL):
    raise RuntimeError("真实观察与计划 §2.1 展示归一后不等 —— 先修观察证据，探针拒跑")


def _normalize(data: dict) -> dict:
    """受控基线：身份与结构照抄实时 state，但把「处在哪一相」抹平。

    抹平之后，C/F 这类「只该报一条」的探针不会因为实时 state 恰好有 active 阶段而多报 J9；
    O/P 这类「制造相位矛盾」的探针也不会因为目标相位已经存在而变成空操作。
    """
    result = copy.deepcopy(data)
    result["status"] = "prepared"
    result["goal_binding"] = "optional"
    result["goal_id"] = None
    result["goal_pending_reason"] = "探针受控基线尚未绑定 Goal"
    result["system_goal_observed_status"] = None
    result["system_goal_observed_at"] = None
    # 实时 state 已转入 session 绑定后，这里必须把证据引用一并抹平：
    # 否则受控基线自带 session 证据，D/T/U/N 这些原有探针全部被 J3 连带误伤。
    result["goal_binding_evidence"] = None
    for key in ("phase_progress", "task_progress"):
        rows = result.setdefault(key, {})
        for identity, row in list(rows.items()):
            if isinstance(row, dict) and row.get("status") in ("active", "blocked"):
                rows[identity] = {**row, "status": "pending"}
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
    result["goal_binding"] = "required"
    result["goal_id"] = "00000000-0000-4000-8000-000000000001"  # 仅本地反向探针的合成身份
    result["system_goal_observed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    result["goal_binding_evidence"] = _write_tmp_evidence(
        goal_id=result["goal_id"], id_unavailable=False,
        observed_at=result["system_goal_observed_at"])
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


PLAN_PHASE_HEAD = PHASE_HEAD


def _pick_skipped_phase(data: dict) -> tuple[str, str]:
    """挑一对「正在推进、它前面的阶段却没完成」的 (前置阶段, 推进阶段)。

    为什么不再写死 Phase 2：写死就等于假设「Phase 1 还没完成」。项目一旦推进到
    Phase 1 已完成，这条探针会变成空操作并报 rc=0 —— 判据会随进度失效。
    只往「后面再找一个未完成阶段去激活」也有同样的寿命问题：2026-10-01 项目
    推进到计划里最后一个阶段 Phase 7 时，它后面不存在可激活的阶段，探针直接
    构造不出来。J5 的判据本身是「已推进的阶段，前置必须 done」，两个方向等价，
    所以这里从反方向构造：最后一个未完成阶段用来激活，它前面最后一个 done 阶段
    退回 pending。这样无论进度停在哪一相，只要还有未完成阶段就构造得出来。

    退回的 done 阶段还要避开两类 Gate，否则同一次注入会连带其他 tag，失去
    「只报该报的」的证明力：
      * next_action 依赖的 Gate —— 那是 J7 的地盘（2026-10-01 首轮撞到，J5+J7）；
      * 任何已推进任务（active/done）依赖的 Gate —— 那是 J6 的地盘
        （2026-10-01 夜间 CI 又一次撞到：V2.7.1 已 done 且依赖 G6，退回 Phase 6
        连带打出 J6）。只挑 Gate 无人依赖的 done 阶段退回。
    """
    heads = PLAN_PHASE_HEAD.findall(PLAN_TEXT)
    rows = data.get("phase_progress") or {}

    def status(pid: str) -> str:
        row = rows.get(pid) or {}
        return row.get("status", "pending") if isinstance(row, dict) else "pending"

    open_phases = [pid for pid in heads if status(pid) != "done"]
    if not open_phases:
        raise RuntimeError("所有阶段都已完成，这条探针无法构造 —— 要更新探针，不是放宽判据")
    tip = open_phases[-1]
    # prepared 的多个 pending 阶段无需退回已完成门禁；直接跳过前一个 pending。
    pending_before = [pid for pid in heads[:heads.index(tip)] if status(pid) == "pending"]
    if pending_before:
        return pending_before[-1], tip
    na_deps = set(PLAN_DEPS.get(str(data.get("next_action_task") or "")) or [])
    moved = [tid for tid in PLAN_TASKS
             if ((data.get("task_progress") or {}).get(tid) or {}).get("status") in ("active", "done")]
    busy_gates = {dep for tid in moved for dep in (PLAN_DEPS.get(tid) or [])
                  if dep.startswith("G")}
    busy = na_deps | busy_gates
    done_before = [pid for pid in heads[:heads.index(tip)]
                   if status(pid) == "done" and f"G{pid}" not in busy]
    if not done_before:
        raise RuntimeError(
            "要推进的阶段之前没有可退回的 done 阶段（next_action 或被已推进任务依赖的 Gate 除外）；"
            f"busy={sorted(busy)}，探针需要更新，不是放宽判据")
    return done_before[-1], tip


def _run_guard() -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "-B", str(GUARD), "--root", str(ROOT)], cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _restore() -> None:
    STATE.write_bytes(ORIG_BYTES)
    TMP_EVIDENCE.unlink(missing_ok=True)
    for directory in DUP_DIRS:
        if directory.exists():
            shutil.rmtree(directory)


EVIDENCE_BASE = {
    "schema": "amz-goal-observation/v1",
    "source": "goal-tool",
    "authorization": "user_confirmed_current_goal",
    "user_confirmation": "不是给你设置了goal吗",
    "plan_ref": str(ORIG_DATA["plan_ref"]),
    "goal_id": None,
    "id_unavailable": True,
    "observed_status": "active",
    "observed_at": REAL_EVIDENCE["observed_at"],
    "objective_sha256": PLAN_GOAL_SHA,
    "observed_objective": PLAN_GOAL,
}


def _write_tmp_evidence(**overrides) -> str:
    """把确定性夹具写到仓库内的临时拷贝；返回仓库相对路径给 state 引用。"""
    record = dict(EVIDENCE_BASE)
    record.update(overrides)
    TMP_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    TMP_EVIDENCE.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8", newline="\n")
    return TMP_EVIDENCE_REL


def _sessionize(data: dict, *, status: str = "active", evidence_rel: str | None,
                active_phase: bool = True) -> dict:
    """构造 session 合同允许的记录形态：goal_id 必须是 null，读数来自证据文件。

    prepared 形态例外：没有可观察的当前 Goal，读数必须为空 —— 正是 guard 要拦的
    「prepared 冒充 session」。
    """
    result = copy.deepcopy(data)
    result["goal_binding"] = GOAL_BINDING_SESSION
    result["goal_id"] = None
    result["goal_pending_reason"] = None
    result["goal_binding_evidence"] = evidence_rel
    result["status"] = status
    if status == "prepared":
        result["system_goal_observed_status"] = None
        result["system_goal_observed_at"] = None
        return result
    result["system_goal_observed_status"] = status
    result["system_goal_observed_at"] = REAL_EVIDENCE["observed_at"]
    if not active_phase:
        raise RuntimeError("active 记录需要 active 阶段——探针构造无效形态")
    if status == "active":
        phases = result.setdefault("phase_progress", {})
        heads = PLAN_PHASE_HEAD.findall(PLAN_TEXT)
        open_phase = next((pid for pid in heads
                           if (phases.get(pid) or {}).get("status") != "done"), None)
        if open_phase is None:
            raise RuntimeError("所有阶段都已完成，探针无法构造合法开工形态 —— 要更新探针，不是放宽判据")
        phases[open_phase] = {"status": "active", "evidence": []}
    return result


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
        phases = data.setdefault("phase_progress", {})
        heads = PLAN_PHASE_HEAD.findall(PLAN_TEXT)
        picked = next((pid for pid in heads
                       if (phases.get(pid) or {}).get("status") == "done"), heads[0])
        phases[picked] = {"status": "done", "evidence": []}
    elif case == "G":
        data["status"] = "active"
        data["system_goal_observed_status"] = "active"
        prereq, advanced = _pick_skipped_phase(data)
        phases = data.setdefault("phase_progress", {})
        phases[prereq] = {"status": "pending", "evidence": []}
        phases[advanced] = {"status": "active", "evidence": []}
    elif case == "H":
        data.setdefault("task_progress", {})["D999.1"] = {"status": "pending", "evidence": []}
    elif case == "I":
        tasks = data.setdefault("task_progress", {})
        picked = next(tid for tid in PLAN_TASKS
                      if (tasks.get(tid) or {}).get("status") == "done")
        tasks[picked] = {"status": "done", "evidence": []}
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
        data["system_goal_observed_status"] = "paused"
        data["goal_binding_evidence"] = _write_tmp_evidence(
            goal_id=data["goal_id"], id_unavailable=False,
            observed_at=data["system_goal_observed_at"], observed_status="paused")
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
    elif case == "T":
        data["goal_binding"] = "required"
        data["goal_id"] = "00000000-0000-4000-8000-000000000001"
    elif case == "U":
        data["goal_id"] = "00000000-0000-4000-8000-000000000001"
    elif case == "V":
        data["system_goal_observed_status"] = "active"
    elif case == "W":
        data["system_goal_observed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    elif case == "X":
        data = _make_active(data)
        data["status"] = "prepared"
        data["goal_binding"] = "optional"
        data["goal_id"] = None
        data["goal_binding_evidence"] = None
        data["system_goal_observed_status"] = None
        data["system_goal_observed_at"] = None
    elif case == "Y":
        # 偷开尚有未完成依赖的非 next_action 任务：J6/J9 必须同时拒绝。
        ready = _pick_task_with_unmet_dep(data)
        data.setdefault("task_progress", {})[ready] = {"status": "active", "evidence": []}
    elif case == "Z":
        data.pop("next_action_task", None)
    elif case == "AA":
        data.setdefault("task_progress", {})[str(data["next_action_task"])] = {
            "status": "active", "evidence": []}
    elif case == "AB":
        data.setdefault("task_progress", {})[str(data["next_action_task"])] = {
            "status": "blocked", "evidence": []}
    elif case == "AC":
        data.pop("state_schema", None)
        phases = data.pop("phase_progress", {})
        tasks = data.pop("task_progress", {})
        data["phases"] = [
            {"id": pid, "gate": f"G{pid}", "status": (phases.get(pid) or {}).get("status", "pending"),
             "gate_evidence": (phases.get(pid) or {}).get("evidence", [])}
            for pid in PLAN_PHASE_HEAD.findall(PLAN_TEXT)]
        data["tasks"] = [
            {"id": tid, "status": (tasks.get(tid) or {}).get("status", "pending"),
             # legacy 的 depends_on 只接受任务引用；Gate 是 v2 的计划语义。
             "depends_on": [dep for dep in PLAN_DEPS.get(tid, []) if dep in PLAN_TASKS],
             "evidence": (tasks.get(tid) or {}).get("evidence", [])}
            for tid in PLAN_TASKS]
    elif case == "AD":
        data["next_action_task"] = next(
            tid for tid in PLAN_TASKS
            if ((data.get("task_progress") or {}).get(tid) or {}).get("status") == "done")
    elif case == "AE":
        data = _make_active(data)
        data["system_goal_observed_status"] = "blocked"
        data["goal_binding_evidence"] = _write_tmp_evidence(
            goal_id=data["goal_id"], id_unavailable=False,
            observed_at=data["system_goal_observed_at"], observed_status="blocked")
    elif case == "AF":
        data = _make_active(data)
        data["status"] = "paused"
        data["phase_progress"] = copy.deepcopy(BASE.get("phase_progress") or {})
    elif case == "AG":
        data = _make_active(data)
        data["status"] = "paused"
        data["system_goal_observed_status"] = "blocked"
        data["goal_binding_evidence"] = _write_tmp_evidence(
            goal_id=data["goal_id"], id_unavailable=False,
            observed_at=data["system_goal_observed_at"], observed_status="blocked")
        data["phase_progress"] = copy.deepcopy(BASE.get("phase_progress") or {})
    elif case == "AH":
        data = _sessionize(
            data, status="active",
            evidence_rel=_write_tmp_evidence(observed_objective=REAL_EVIDENCE["observed_objective"]))
    elif case == "AI":
        data = _sessionize(data, status="paused",
                           evidence_rel=_write_tmp_evidence(observed_status="paused"))
    elif case == "AJ":
        data = _sessionize(data, status="active", evidence_rel=None)
        data.pop("goal_binding_evidence", None)
    elif case == "AK":
        data = _sessionize(
            data, status="active",
            evidence_rel=_write_tmp_evidence(objective_sha256="0" * 64))
    elif case == "AL":
        data = _sessionize(
            data, status="active",
            evidence_rel=_write_tmp_evidence(observed_objective="已知不存在的另一目标"))
    elif case == "AM":
        data = _sessionize(
            data, status="active",
            evidence_rel=_write_tmp_evidence(plan_ref="docs/其他计划.md"))
    elif case == "AN":
        data = _sessionize(
            data, status="active",
            evidence_rel=_write_tmp_evidence(goal_id="00000000-0000-4000-8000-000000000001"))
    elif case == "AO":
        data = _sessionize(
            data, status="active",
            evidence_rel=_write_tmp_evidence(observed_at="2000-01-01T00:00:00+00:00"))
    elif case == "AP":
        data = _sessionize(
            data, status="active",
            evidence_rel=_write_tmp_evidence(observed_at="2026-10-01T12:14:51"))
    elif case == "AQ":
        data = _sessionize(
            data, status="active", evidence_rel="evals/product-v2/refactor/不存在的观察.json")
    elif case == "AR":
        data = _sessionize(data, status="active", evidence_rel="E:/仓库外观察.json")
    elif case == "AS":
        data = _sessionize(data, status="active", evidence_rel="../仓库外观察.json")
    elif case == "AT":
        data = _sessionize(
            data, status="active",
            evidence_rel=_write_tmp_evidence(schema="amz-goal-observation/v2"))
    elif case == "AU":
        data = _sessionize(
            data, status="active",
            evidence_rel=_write_tmp_evidence(authorization="user_said_so_once"))
    elif case == "AV":
        data = _sessionize(data, status="prepared", evidence_rel=None, active_phase=False)
        data.pop("goal_binding_evidence", None)
    elif case == "AW":
        data = _sessionize(data, status="active", evidence_rel=REAL_EVIDENCE_REL)
        data["goal_binding"] = "required"
        data["goal_id"] = "00000000-0000-4000-8000-000000000001"
    elif case == "AY":
        data = _sessionize(
            data, status="active",
            evidence_rel=_write_tmp_evidence(observed_objective=PLAN_GOAL + "多出来的尾巴。"))
    elif case == "AZ":
        data = _sessionize(data, status="active", evidence_rel=REAL_EVIDENCE_REL)
        data.pop("state_schema", None)
        phases = data.pop("phase_progress", {})
        tasks = data.pop("task_progress", {})
        data["phases"] = [
            {"id": pid, "gate": f"G{pid}", "status": (phases.get(pid) or {}).get("status", "pending"),
             "gate_evidence": (phases.get(pid) or {}).get("evidence", [])}
            for pid in PLAN_PHASE_HEAD.findall(PLAN_TEXT)]
        data["tasks"] = [
            {"id": tid, "status": (tasks.get(tid) or {}).get("status", "pending"),
             "depends_on": [dep for dep in PLAN_DEPS.get(tid, []) if dep in PLAN_TASKS],
             "evidence": (tasks.get(tid) or {}).get("evidence", [])}
            for tid in PLAN_TASKS]
    elif case == "BA":
        # state 的读数车道要跟证据一致（paused），让冲突落在「记录 active vs 观察 paused」
        # —— 那是 J9 的地盘；不然这条会连带 J3，失去「只报该报的」。
        data = _sessionize(
            data, status="active",
            evidence_rel=_write_tmp_evidence(observed_status="paused"))
        data["system_goal_observed_status"] = "paused"
    elif case == "BB":
        data = _sessionize(data, status="active", evidence_rel=TMP_EVIDENCE_REL)
        TMP_EVIDENCE.write_text("{ 显然不是 JSON", encoding="utf-8")
    elif case == "BC":
        record = dict(EVIDENCE_BASE)
        record.pop("id_unavailable")
        TMP_EVIDENCE.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8", newline="\n")
        data = _sessionize(data, status="active", evidence_rel=TMP_EVIDENCE_REL)
    elif case == "BD":
        record = dict(EVIDENCE_BASE)
        record.pop("schema")
        TMP_EVIDENCE.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8", newline="\n")
        data = _sessionize(data, status="active", evidence_rel=TMP_EVIDENCE_REL)
    elif case == "BE":
        record = dict(EVIDENCE_BASE)
        record.pop("authorization")
        TMP_EVIDENCE.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8", newline="\n")
        data = _sessionize(data, status="active", evidence_rel=TMP_EVIDENCE_REL)
    elif case == "BF":
        data = copy.deepcopy(ORIG_DATA)
    elif case == "BG":
        data = copy.deepcopy(ORIG_DATA)
        data["goal_id"] = "0000000000000001"
    elif case == "BH":
        data = _make_active(data)
        data["goal_binding_evidence"] = _write_tmp_evidence(
            goal_id=data["goal_id"], id_unavailable=False,
            observed_at=data["system_goal_observed_at"], observed_objective=PLAN_GOAL + "改写目标")
    elif case == "BI":
        data = _make_active(data)
        data["goal_binding_evidence"] = _write_tmp_evidence(
            goal_id=data["goal_id"], id_unavailable=False,
            observed_at=data["system_goal_observed_at"],
            observed_objective=PLAN_GOAL.replace("。", "；", 1))
    elif case == "BJ":
        data = _make_active(data)
        data["goal_binding_evidence"] = None
    elif case == "BK":
        data = _make_active(data)
        data["goal_binding_evidence"] = _write_tmp_evidence(
            goal_id=data["goal_id"], id_unavailable=True,
            observed_at=data["system_goal_observed_at"])
    elif case in ("BL", "BM"):
        data = _make_active(data)
        tid = str(data["next_action_task"])
        data.setdefault("task_progress", {})[tid] = {"status": "blocked", "evidence": []}
        data["blockers"] = ([tid + "_awaits_owner_permission"] if case == "BL"
                            else ["another_task_awaits_owner_permission"])
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
    ("T", "prepared 冒充 required 绑定", 1, {"J3"}),
    ("U", "prepared optional 却保存 Goal ID", 1, {"J3"}),
    ("V", "prepared 保存系统 Goal 状态读数", 1, {"J9"}),
    ("W", "prepared 保存系统 Goal 观察时刻", 1, {"J9"}),
    ("X", "prepared 混入 active 阶段", 1, {"J9"}),
    ("Y", "prepared 偷开依赖未满足的非 next_action 任务", 1, {"J6", "J9"}),
    ("Z", "prepared 缺少 next_action", 1, {"J7"}),
    ("AA", "prepared next_action 已 active", 1, {"J7", "J9"}),
    ("AB", "prepared next_action 已 blocked", 1, {"J7"}),
    ("AC", "legacy 结构不能声明 prepared", 1, {"J9"}),
    ("AD", "prepared next_action 已 done", 1, {"J7"}),
    ("AE", "active 与系统 blocked 读数不匹配", 1, {"J9"}),
    ("AF", "paused 与系统 active 读数不匹配", 1, {"J9"}),
    ("AG", "paused 与系统 blocked 合法映射", 0, set()),
    ("AH", "session active 观察与终端展示归一 · 合法", 0, set()),
    ("AI", "session 绑定 + paused 观察 · 合法暂停", 0, set()),
    ("AJ", "session 缺少证据文件声明", 1, {"J3"}),
    ("AK", "session 证据目标哈希不匹配", 1, {"J3"}),
    ("AL", "session 证据 observed_objective 是另一目标", 1, {"J3"}),
    ("AM", "session 证据 plan_ref 与 state 不一致", 1, {"J3"}),
    ("AN", "session 证据伪造 Goal ID", 1, {"J3"}),
    ("AO", "session 证据 observed_at 与 state 读数不同刻", 1, {"J3"}),
    ("AP", "session 证据 observed_at 没有时区", 1, {"J3"}),
    ("AQ", "session 证据文件不存在", 1, {"J3"}),
    ("AR", "session 证据是盘符绝对路径", 1, {"J3"}),
    ("AS", "session 证据用 ../ 跳出仓库", 1, {"J3"}),
    ("AT", "session 证据 schema 不对", 1, {"J3"}),
    ("AU", "session 证据授权来源不对", 1, {"J3"}),
    ("AV", "prepared 冒充 session 绑定", 1, {"J3"}),
    ("AW", "required 身份与观察 Goal ID 不一致", 1, {"J3"}),
    ("AY", "session 证据正文被追加改动（展示归一后不等）", 1, {"J3"}),
    ("AZ", "legacy 结构借用 session 绑定", 1, {"J3"}),
    ("BA", "session 证据 paused 与记录 active 冲突", 1, {"J9"}),
    ("BB", "session 证据是坏 JSON", 1, {"J3"}),
    ("BC", "session 证据缺 id_unavailable", 1, {"J3"}),
    ("BD", "session 证据缺 schema", 1, {"J3"}),
    ("BE", "session 证据缺 authorization", 1, {"J3"}),
    ("BF", "真实原生 Goal handle 与原始展示体 · 合法", 0, set()),
    ("BG", "required state 偷换另一原生 Goal handle", 1, {"J3"}),
    ("BH", "required 观察正文追加目标", 1, {"J3"}),
    ("BI", "展示归一不得吞正文标点改写", 1, {"J3"}),
    ("BJ", "required 当前 v2 缺观察证据", 1, {"J3"}),
    ("BK", "required 有 ID 却声称 ID 不可用", 1, {"J3"}),
    ("BL", "active 阻塞恢复点具有对应阻塞记录 · 合法", 0, set()),
    ("BM", "active 阻塞恢复点没有对应阻塞记录", 1, {"J7"}),
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
        if TMP_EVIDENCE.exists():
            print(f"✗ 探针临时证据未被清理：{TMP_EVIDENCE_REL}")
            bad += 1
        if STATE.read_bytes() == ORIG_BYTES and not TMP_EVIDENCE.exists():
            print(f"独立副本已恢复 {STATE.relative_to(ROOT).as_posix()}；权威 state/观察证据从未写入")

    if bad:
        print(f"✗ {bad}/{len(CASES)} 向与预期不符")
        return 1
    print(f"OK：{len(CASES)} 向全部与预期一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
