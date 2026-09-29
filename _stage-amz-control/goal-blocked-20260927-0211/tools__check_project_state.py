#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""项目状态守卫 —— 让「做到哪了」这件事有人守。

为什么需要它
------------
`tools/check_docs.py` 回答「哪一份文档有效 / 哪一类事实归谁」。它管不到**内容的
一致性**：登记表里 `执行状态` 完全可以既唯一、又写着「下一步：创建 Goal」——
而 Goal 早就建好了。这不是"值不相等"，是**执行状态自己漂了而没有任何东西会响**。

十一条判据，每条带一个稳定 tag（`evals/probes/project_state.py` 据此断言「只报该报的」）：

    [J0] 工作记录读得出来（有 ```yaml 块、能解析、顶层是映射）
    [J1] 活动工作记录唯一：`_working/*/state.md` 里 status=active 的恰好一份
    [J2] 状态取值闭集合（记录 / 阶段 / 任务三处都算）
    [J3] Goal 绑定：goal_binding=required 时 goal_id 必须是真 ID；
         optional 时必须写明 goal_pending_reason
    [J4] 状态引用的阶段 / 任务身份必须存在于计划；阶段图、Gate 和任务依赖只由计划定义
    [J5] 阶段推进合法：最多一个 active；active/done 的前置阶段必须 done；
         done 必须带 gate_evidence，且证据文件真实存在
    [J6] 任务状态合法：状态只能引用计划任务；done 必须有存在的证据；
         active/done 的依赖按计划计算且必须 done
    [J7] next_action 可执行：指向的任务存在、是 pending、依赖已 done
    [J8] 不重抄：目标 / 范围 / 决策的正文只有一处（那份计划）；
         state.md 只许引用
    [J9] 记录与阶段一致（记录状态值本身非法时归 J2，J9 不重复计数）：
         有 active 阶段 ⇒ 记录必须 active；记录 active ⇒ 至少一相在跑
         （最多一相由 J5 管）；记录 completed ⇒ 没有未收尾的阶段与任务
    [J10] 执行记录的时刻不许是编的：updated_at 必须存在、带时区，且不晚于这个文件
         最后写入的时刻（容差 10 分钟）。

v2 状态模式实行「政出一门」：计划拥有完整阶段图、Gate、任务和依赖；状态文件只保存
非 pending 的进度、证据和一个 next_action。状态中的 ID 是外键，不再复制计划结构。
旧的 superseded 记录仍按 legacy 结构只读校验，避免改写历史证据。

为什么 J5 要「前置必须 done」：计划写着「任一时刻最多一个阶段处于 active；只有阶段
门禁取得权威证据后，下一阶段才能开始」。跳着来等于没门。

为什么 J9 要「记录与阶段一致」：`status: paused` 与「某一相 active」单独看都合法，
合起来是谎。开工那一刻要同时改三处（系统 Goal / 执行记录 / Phase 1），只改一处
不会有任何东西响 —— 而「记录说停了、阶段在跑」（或反过来「记录说在跑、没有一相在
动」）正是接手的人会照着做错判断的那种漂移。原始证据见 `evals/start_rehearsal.txt`。

用法：
    python tools/check_project_state.py      # 退出码 0 全过 / 1 有漂移

本守卫**只读**，不写任何文件。
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))          # 只为取 console（见 src/console.py）
from console import enable_utf8  # noqa: E402
enable_utf8()

WORKING = ROOT / "_working"

RECORD_STATUSES = {"active", "paused", "completed", "superseded"}
ITEM_STATUSES = {"pending", "active", "done", "blocked", "dropped", "superseded"}
UPDATED_AT_TOLERANCE_SEC = 600          # 容忍四舍五入，不容忍「未来读数」
STATE_SCHEMA_V2 = "amz-project-state/v2"

# 这些事实的正文归各记录的 plan_ref；执行状态里只许引用，不许抄。
FORBIDDEN_KEYS = ("scope", "objective", "decisions", "non_goals", "metrics")
V2_ALLOWED_KEYS = {
    "state_schema", "task_id", "status", "goal_binding", "goal_id", "goal_pending_reason",
    "system_goal_observed_status", "system_goal_observed_at", "plan_ref",
    "latest_audit", "phase_progress", "task_progress", "next_action_task",
    "blockers", "unknowns", "updated_at",
}

PHASE_HEAD = re.compile(r"^###\s+Phase\s+(-?\d+(?:\.\d+)?)\s*[：:]", re.M)
GATE_DECL = re.compile(r"^\*\*Gate\s+(G-?\d+(?:\.\d+)?)\s*[：:]", re.M)
TASK_ID_RE = re.compile(r"^D[-0-9A-Za-z.]+$")
DEP_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_.-])(D[-0-9A-Za-z.]+|G-?\d+(?:\.\d+)?)(?![A-Za-z0-9_.-])")
YAML_BLOCK = re.compile(r"```yaml\r?\n(.*?)```", re.S)
GOAL_ID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


class Report:
    def __init__(self) -> None:
        self.problems: list[str] = []
        self.notes: list[str] = []

    def problem(self, msg: str) -> None:
        self.problems.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)


def _rel(p: Path) -> str:
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return p.as_posix()


def _exists(rel: str) -> bool:
    return (ROOT / rel).exists()


def _plan_tasks(plan_text: str) -> tuple[list[str], dict[str, list[str]]]:
    """从 §6 任务表读取 ID 与 Depends；计划是结构唯一权威。"""
    ids: list[str] = []
    deps: dict[str, list[str]] = {}
    for line in plan_text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not TASK_ID_RE.fullmatch(cells[0]):
            continue
        tid = cells[0]
        ids.append(tid)
        deps[tid] = DEP_TOKEN_RE.findall(cells[2])
    return ids, deps


def _progress_map(rep: Report, rel: str, value, label: str, tag: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        rep.problem(f"[{tag}] {rel} 的 {label} 必须是映射，实际是 {type(value).__name__}。")
        return {}
    return value


def _evidence_ok(rep: Report, rel: str, owner: str, row: dict, tag: str) -> None:
    ev = row.get("evidence") or []
    if not ev:
        rep.problem(f"[{tag}] {rel} 的 {owner} 标成 done 却没有 evidence。")
        return
    for item in ev:
        if not _exists(str(item)):
            rep.problem(f"[{tag}] {rel} 的 {owner} evidence 指向不存在的文件：{item}")


def _check_updated_at(rep: Report, rel: str, path: Path, d: dict) -> None:
    """[J10] updated_at 必须是一个真的发生过的时刻。

    这不是格式检查。2026-09-26 核对 current state 时读到：文件最后写入是 12:50，
    里面却写着 `updated_at: 14:05`，而全部守卫当时是绿的 —— J2 只看 status 的取值域，
    J6 只看证据文件在不在，没有一条会问「这个时刻发生过吗」。它的后果是具体的：
    读者据此判断哪份记录更新、哪份证据是这一轮的，判断恰好是反的。这也正是
    「读数不是跑出来的」最便宜的形态，所以在这里把它堵掉。
    """
    raw = d.get("updated_at")
    if raw in (None, ""):
        rep.problem(f"[J10] {rel} 没有 updated_at —— 这份记录什么时候被改过，读者只能猜。")
        return
    try:
        stamp = datetime.fromisoformat(str(raw))
    except ValueError:
        rep.problem(f"[J10] {rel} 的 updated_at={raw!r} 不是 ISO-8601 时刻。")
        return
    if stamp.tzinfo is None:
        rep.problem(f"[J10] {rel} 的 updated_at={raw!r} 没有时区 —— 本地时间与 UTC 差 8 小时，"
                    f"「谁更新」就没有唯一答案。")
        return
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=stamp.tzinfo)
    late = (stamp - mtime).total_seconds()
    if late > UPDATED_AT_TOLERANCE_SEC:
        rep.problem(f"[J10] {rel} 的 updated_at={raw} 比这个文件最后写入的时刻 "
                    f"{mtime.isoformat(timespec='seconds')} 还晚 {late / 60:.0f} 分钟 —— "
                    f"读数是跑出来的，不许写一个还没发生的时刻。")


def _check_v2(rep: Report, rel: str, d: dict, plan_text: str,
              plan_phases: list[str], plan_gates: set[str]) -> None:
    """单一权威状态：计划管结构，state 只管进度 / 证据 / 下一动作。"""
    extra = sorted(set(d) - V2_ALLOWED_KEYS)
    if extra:
        rep.problem(f"[J8] {rel} 出现不属于执行状态的顶层键：{extra}。"
                    "目标、依赖、决策或历史正文必须回到各自权威。")

    audit = d.get("latest_audit")
    if audit and not _exists(str(audit)):
        rep.problem(f"[J8] {rel} 的 latest_audit 指向不存在的文件：{audit}")
    elif audit:
        audit_head = "\n".join((ROOT / str(audit)).read_text(encoding="utf-8").splitlines()[:12])
        if "NOT-AUTHORITY" not in audit_head:
            rep.problem(f"[J8] {rel} 的 latest_audit={audit!r} 没有 NOT-AUTHORITY 标记 —— "
                        "审计证据不能同时冒充当前计划或状态。")

    phase_progress = _progress_map(rep, rel, d.get("phase_progress"),
                                   "phase_progress", "J4")
    task_progress = _progress_map(rep, rel, d.get("task_progress"),
                                  "task_progress", "J6")
    plan_tasks, task_deps = _plan_tasks(plan_text)

    dup_tasks = sorted({x for x in plan_tasks if plan_tasks.count(x) > 1})
    if dup_tasks:
        rep.problem(f"[J6] {rel} 的计划任务 id 重复：{dup_tasks}")

    unknown_phases = sorted(set(map(str, phase_progress)) - set(plan_phases))
    if unknown_phases:
        rep.problem(f"[J4] {rel} 的 phase_progress 引用了计划中不存在的阶段：{unknown_phases}")
    for pid in plan_phases:
        if f"G{pid}" not in plan_gates:
            rep.problem(f"[J4] {rel} 的计划声明了 Phase {pid}，却没有 Gate G{pid}。")

    phase_status: dict[str, str] = {}
    for pid in plan_phases:
        row = phase_progress.get(pid) or {}
        if row and not isinstance(row, dict):
            rep.problem(f"[J4] {rel} 的 Phase {pid} 进度不是映射。")
            row = {}
        extra_row = sorted(set(row) - {"status", "evidence"})
        if extra_row:
            rep.problem(f"[J8] {rel} 的 Phase {pid} 复制了非状态字段：{extra_row}")
        pst = row.get("status", "pending")
        phase_status[pid] = pst
        if pst not in ITEM_STATUSES:
            rep.problem(f"[J2] {rel} 阶段 {pid} 的 status={pst!r} 不在取值域。")
            continue
        if pst == "done":
            _evidence_ok(rep, rel, f"阶段 {pid}", row, "J5")

    active_phases = [pid for pid, st in phase_status.items() if st == "active"]
    if len(active_phases) > 1:
        rep.problem(f"[J5] {rel} 有 {len(active_phases)} 个 active 阶段：{active_phases}")
    for index, pid in enumerate(plan_phases):
        if phase_status.get(pid) in ("active", "done"):
            undone = [prev for prev in plan_phases[:index]
                      if phase_status.get(prev) != "done"]
            if undone:
                rep.problem(f"[J5] {rel} 阶段 {pid} 已推进，但前置阶段 {undone} 未 done。")

    unknown_tasks = sorted(set(map(str, task_progress)) - set(plan_tasks))
    if unknown_tasks:
        rep.problem(f"[J6] {rel} 的 task_progress 引用了计划中不存在的任务：{unknown_tasks}")
    task_status: dict[str, str] = {}
    for tid in plan_tasks:
        row = task_progress.get(tid) or {}
        if row and not isinstance(row, dict):
            rep.problem(f"[J6] {rel} 的任务 {tid} 进度不是映射。")
            row = {}
        extra_row = sorted(set(row) - {"status", "evidence"})
        if extra_row:
            rep.problem(f"[J8] {rel} 的任务 {tid} 复制了非状态字段：{extra_row}")
        tst = row.get("status", "pending")
        task_status[tid] = tst
        if tst not in ITEM_STATUSES:
            rep.problem(f"[J2] {rel} 任务 {tid} 的 status={tst!r} 不在取值域。")
            continue
        if tst == "done":
            _evidence_ok(rep, rel, f"任务 {tid}", row, "J6")

    def dep_done(dep: str) -> bool:
        if dep.startswith("G"):
            return phase_status.get(dep[1:]) == "done"
        return task_status.get(dep) == "done"

    for tid in plan_tasks:
        if task_status.get(tid) in ("active", "done"):
            undone = [dep for dep in task_deps.get(tid, []) if not dep_done(dep)]
            if undone:
                rep.problem(f"[J6] {rel} 任务 {tid} 已推进，但计划依赖 {undone} 未完成。")

    na = d.get("next_action_task")
    if not na:
        rep.problem(f"[J7] {rel} 没有 next_action_task。")
    elif str(na) not in plan_tasks:
        rep.problem(f"[J7] {rel} 的 next_action_task={na!r} 不在计划任务表。")
    else:
        nst = task_status.get(str(na), "pending")
        if nst not in ("pending", "active"):
            rep.problem(f"[J7] {rel} 的 next_action_task={na!r} 当前是 {nst}。")
        undone = [dep for dep in task_deps.get(str(na), []) if not dep_done(dep)]
        if undone:
            rep.problem(f"[J7] {rel} 的 next_action_task={na!r} 依赖 {undone} 未完成。")

    record_status = d.get("status")
    observed = d.get("system_goal_observed_status")
    if record_status in ("active", "paused") and observed != record_status:
        rep.problem(f"[J9] {rel} 记录 status={record_status!r}，但最近系统 Goal 读数是 {observed!r}。")
    if record_status == "active" and not active_phases:
        rep.problem(f"[J9] {rel} 记录 active，但 phase_progress 没有 active 阶段。")
    if record_status != "active" and active_phases:
        rep.problem(f"[J9] {rel} 记录 {record_status!r}，却有 active 阶段 {active_phases}。")
    if record_status == "completed":
        open_phases = [pid for pid, st in phase_status.items() if st != "done"]
        open_tasks = [tid for tid, st in task_status.items()
                      if st not in ("done", "dropped", "superseded")]
        if open_phases or open_tasks:
            rep.problem(f"[J9] {rel} 声明 completed，但未完成阶段 {open_phases}、任务 {open_tasks}。")


def _records(rep: Report):
    """[(path, data|None, 原因)] —— 读不出来的也要留下记录，不许静默消失。"""
    out = []
    if not WORKING.exists():
        return out
    try:
        import yaml
    except ImportError as exc:
        rep.problem(f"[J0] 缺 PyYAML（{exc}）—— 解析不了状态就谈不上守它。"
                    f"这是环境问题，必须显式报出来，不许静默跳过。")
        return out
    for p in sorted(WORKING.glob("*/state.md")):
        text = p.read_text(encoding="utf-8")
        m = YAML_BLOCK.search(text)
        if not m:
            out.append((p, None, "没有 ```yaml 围栏块"))
            continue
        try:
            data = yaml.safe_load(m.group(1))
        except yaml.YAMLError as exc:
            out.append((p, None, f"YAML 解析失败：{exc}"))
            continue
        if not isinstance(data, dict):
            out.append((p, None, "YAML 顶层不是映射"))
            continue
        out.append((p, data, None))
    return out


def _check(rep: Report) -> None:
    records = _records(rep)
    for p, _d, why in records:
        if why:
            rep.problem(f"[J0] {_rel(p)}：{why}")
    parsed = [(p, d) for p, d, why in records if d]

    if not records:
        rep.problem("[J1] _working/ 下没有任何 */state.md —— 执行状态没有出处，"
                    "「下一步做什么」只能靠人记住。")
        return

    actives = [(p, d) for p, d in parsed if d.get("status") == "active"]
    if len(actives) > 1:
        rep.problem("[J1] 有 " + str(len(actives)) + " 份 status=active 的工作记录："
                    + "、".join(_rel(p) for p, _ in actives) +
                    " —— 活动任务只能有一个；两份都 active，读到的是哪一份？")

    for p, d in parsed:
        rel = _rel(p)
        _check_updated_at(rep, rel, p, d)

        st = d.get("status")
        if st not in RECORD_STATUSES:
            rep.problem(f"[J2] {rel} 的 status={st!r} 不在取值域："
                        f"{'/'.join(sorted(RECORD_STATUSES))}")

        for k in FORBIDDEN_KEYS:
            if k in d:
                rep.problem(f"[J8] {rel} 里出现顶层键 {k!r} —— 这类事实的正文只有一处"
                            f"（由本记录的 plan_ref 指向）。"
                            f"state.md 只许引用，抄一份就多一份会各自漂的正文。")
        ref = d.get("plan_ref")
        plan_text = ""
        if not ref:
            rep.problem(f"[J8] {rel} 缺 plan_ref —— 目标与范围的正文在哪，得指出来。")
        elif not _exists(str(ref)):
            rep.problem(f"[J8] {rel} 的 plan_ref={ref!r} 指向的文件不存在。")
        else:
            plan_text = (ROOT / str(ref)).read_text(encoding="utf-8")
        plan_phases = PHASE_HEAD.findall(plan_text)
        plan_gates = set(GATE_DECL.findall(plan_text))

        binding = d.get("goal_binding")
        gid = d.get("goal_id")
        if binding == "required":
            if not (isinstance(gid, str) and GOAL_ID_RE.match(gid)):
                rep.problem(f"[J3] {rel} 声明 goal_binding=required，但 goal_id={gid!r} "
                            f"不是有效的 Goal 标识 —— 它是这份文件的锚；锚没了，"
                            f"「做到哪」就没有对照物。")
        elif binding == "optional":
            if gid in (None, "", "null") and not str(d.get("goal_pending_reason") or "").strip():
                rep.problem(f"[J3] {rel} 的 goal_id 为空，且没有 goal_pending_reason —— "
                            f"为什么还没绑 Goal，必须写出来。")
        else:
            rep.problem(f"[J3] {rel} 的 goal_binding={binding!r} 不在取值域："
                        f"required / optional")

        if d.get("state_schema") == STATE_SCHEMA_V2:
            _check_v2(rep, rel, d, plan_text, plan_phases, plan_gates)
            continue

        phases = [ph for ph in (d.get("phases") or []) if isinstance(ph, dict)]
        ids = [str(ph.get("id")) for ph in phases]
        if ids != plan_phases:
            rep.problem(f"[J4] {rel} 的阶段图与计划不一致：状态里是 {ids}，"
                        f"计划里是 {plan_phases} —— 计划加/删了一相而状态没跟，"
                        f"或者状态多出一个不存在的相。")
        for ph in phases:
            pid = str(ph.get("id"))
            gate = ph.get("gate")
            want = f"G{pid}"
            if gate != want:
                rep.problem(f"[J4] {rel} 阶段 {pid} 的 gate={gate!r}，应为 {want!r}")
            elif want not in plan_gates:
                rep.problem(f"[J4] {rel} 阶段 {pid} 引用的 Gate {want} 在计划里没有声明"
                            f" —— 门的判据不在计划里，那这道门是谁定的？")

        tot_active = [ph for ph in phases if ph.get("status") == "active"]
        if len(tot_active) > 1:
            rep.problem(f"[J5] {rel} 有 {len(tot_active)} 个 active 阶段 —— "
                        f"同时开两相，门禁就形同虚设。")
        for i, ph in enumerate(phases):
            pid = str(ph.get("id"))
            pst = ph.get("status")
            if pst not in ITEM_STATUSES:
                rep.problem(f"[J2] {rel} 阶段 {pid} 的 status={pst!r} 不在取值域。")
                continue
            if pst in ("active", "done"):
                nd = [str(phases[j].get("id")) for j in range(i)
                      if phases[j].get("status") != "done"]
                if nd:
                    rep.problem(f"[J5] {rel} 阶段 {pid} 是 {pst}，但前置阶段 {nd} 还没 done"
                                f" —— 阶段门禁是顺序的，跳着来等于没门。")
            if pst == "done":
                ev = ph.get("gate_evidence") or []
                if not ev:
                    rep.problem(f"[J5] {rel} 阶段 {pid} 标成 done，但 gate_evidence 是空的"
                                f" —— 门过了却没有证据，那不是过了，是说了。")
                else:
                    for e in ev:
                        if not _exists(str(e)):
                            rep.problem(f"[J5] {rel} 阶段 {pid} 的 gate_evidence "
                                        f"指向不存在的文件：{e}")

        tasks = [t for t in (d.get("tasks") or []) if isinstance(t, dict)]
        ids_all = [str(t.get("id")) for t in tasks]
        dup = sorted({x for x in ids_all if ids_all.count(x) > 1})
        if dup:
            rep.problem(f"[J6] {rel} 里任务 id 重复：{dup}")
        done_ids = {str(t.get("id")) for t in tasks if t.get("status") == "done"}
        for t in tasks:
            tid = str(t.get("id"))
            tst = t.get("status")
            if tst not in ITEM_STATUSES:
                rep.problem(f"[J2] {rel} 任务 {tid} 的 status={tst!r} 不在取值域。")
                continue
            deps = [str(x) for x in (t.get("depends_on") or [])]
            missing = [x for x in deps if x not in ids_all]
            if missing:
                rep.problem(f"[J6] {rel} 任务 {tid} 依赖了不存在的任务：{missing}")
            if tst in ("active", "done"):
                nd = [x for x in deps if x not in done_ids]
                if nd:
                    rep.problem(f"[J6] {rel} 任务 {tid} 是 {tst}，但依赖 {nd} 还没 done。")
            if tst == "done":
                ev = t.get("evidence") or []
                if not ev:
                    rep.problem(f"[J6] {rel} 任务 {tid} 标成 done 却没有 evidence —— "
                                f"进度是证据换来的，不是时间换来的。")
                else:
                    for e in ev:
                        if not _exists(str(e)):
                            rep.problem(f"[J6] {rel} 任务 {tid} 的 evidence "
                                        f"指向不存在的文件：{e}")

        # [J9] 记录状态与阶段/任务状态必须一致。
        # 记录状态值本身不在取值域时由 J2 独占报出：两个判据同时响，既让「只报
        # 该报的那一类」失效，也让人分不清该改哪一处。
        # 「记录说 paused、阶段在跑」两句话单独看都合法，合起来是谎 ——
        # 开工要同时改三处，只改一处时必须有东西响。
        if tot_active and st in RECORD_STATUSES and st != "active":
            rep.problem(f"[J9] {rel} 有 {len(tot_active)} 个阶段是 active，"
                        f"但记录 status={st!r} —— 记录说停了、阶段在跑，"
                        f"接手的人读到的是哪一个？")
        if st == "active" and not tot_active:
            rep.problem(f"[J9] {rel} 记录 status=active，但没有任何阶段是 active"
                        f" —— 记录说在跑、没有一相在动。开工要把三处一起改。")
        if st == "completed":
            open_items = ([f"阶段 {ph.get('id')}" for ph in phases
                           if ph.get("status") != "done"]
                          + [f"任务 {t.get('id')}" for t in tasks
                             if t.get("status") not in ("done", "dropped", "superseded")])
            if open_items:
                rep.problem(f"[J9] {rel} 记录 status=completed，但还有未收尾的 "
                            f"{'、'.join(open_items)} —— 完成是证据换来的，"
                            f"把记录改成 completed 不算数。")

        # 历史记录已经被取代，不再伪造一个“下一步”；J7 只约束仍可能恢复或推进的记录。
        if st not in ("active", "paused"):
            continue
        na = d.get("next_action_task")
        if not na:
            rep.problem(f"[J7] {rel} 没有 next_action_task —— "
                        f"接手的人不知道从哪一步继续。")
            continue
        na = str(na)
        by_id = {str(t.get("id")): t for t in tasks}
        t = by_id.get(na)
        if t is None:
            rep.problem(f"[J7] {rel} 的 next_action_task={na!r} 不是本文件里的任务。")
            continue
        tst = t.get("status")
        if tst == "done":
            rep.problem(f"[J7] {rel} 的 next_action_task={na!r} 已经 done —— "
                        f"下一步不可能是一件已完成的事。")
        elif tst != "pending":
            rep.problem(f"[J7] {rel} 的 next_action_task={na!r} 的 status={tst!r}，"
                        f"只有 pending 才可能是下一步。")
        nd = [x for x in (str(y) for y in (t.get("depends_on") or []))
              if x not in done_ids]
        if nd:
            rep.problem(f"[J7] {rel} 的 next_action_task={na!r} 依赖 {nd} 还没 done —— "
                        f"报一个现在做不了的下一步，等于没有下一步。")

    rep.note(f"工作记录 {len(records)} 份 · v2 状态从 plan_ref 读取阶段、任务与依赖，不在 state 重复定义")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="项目状态守卫：让「做到哪了」有人守")
    ap.parse_known_args(argv)          # 容忍调用方多塞的参数
    rep = Report()
    _check(rep)
    print("=" * 72)
    print("项目状态守卫")
    print("=" * 72)
    print("判据：J0 记录可读 / J1 活动记录唯一 / J2 取值闭集合 / J3 Goal 绑定")
    print("      J4 状态 ID 引用计划 / J5 阶段门与顺序 / J6 任务进度与证据")
    print("      J7 next_action 按计划可执行 / J8 单一权威不重抄 / J9 Goal 读数与记录一致")
    print("      J10 updated_at 不许写在未来、不许缺时区")
    print()
    for n in rep.notes:
        print(f"  · {n}")
    if rep.problems:
        print(f"\nproblems（{len(rep.problems)} 条）：")
        for s in rep.problems:
            print(f"  ✗ {s}")
        print("\n结果：有漂移（退出码 1）。")
        return 1
    print("结果：全过（退出码 0）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
