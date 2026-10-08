#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""离线走查判据的反向对照（Phase 2 / D2.R1）。

`app/server.py --check` 里有四条判据：目录没被动过、读过的文件逐字节没变、八页都有该有的
内容、走完一遍才出现的东西在初始状态不许有。判据必须有牙 —— 本探针逐条证明它们**会红**，
且只在该红的地方红：

    [A] 真实会话：八页该有的内容**都在**（正向）
    [B] 空会话：不装配就渲染，同一份清单必须**缺**（证明标记不是"写了就有"）
    [C] 目录判据：临时目录里加一个 / 改一个 / 删一个 → 三类各报一条
    [D] 内容判据：同一个文件改一个字节 → 必须被发现
    [E] 联网拦截：拦截真的会拦（自带自检，不是"写了就信"）
    [F] 初始状态就有的东西，不许充当「走完一遍」的证据

它不改项目里的任何文件；[C]/[D] 用的是临时目录。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app import offline as OFF     # noqa: E402
from app import server as S        # noqa: E402
from app import views as V         # noqa: E402
from demo.core import packages as PKG   # noqa: E402


def _missing(pages: dict, required: dict) -> list:
    out = []
    for path, markers in required.items():
        page = pages.get(path, "")
        for marker in markers:
            if marker not in page:
                out.append(f"/{path} 缺「{marker}」")
    return out


def _case_a(problems: list) -> None:
    session = OFF.build(ROOT, PKG.default(ROOT).sku)
    if session.blockers():
        problems.append("A 真实会话装配没走通：" + "；".join(
            f"{c} {getattr(r, 'outcome', '无')}" for c, r in session.blockers()))
        return
    miss = _missing(V.render_all(session), S.REQUIRED_INITIAL)
    if miss:
        problems.append("A 真实会话竟然缺内容：" + "；".join(miss))
        return
    shots = [s["shot_id"] for s in session.shots()]
    work = session.candidate_shot or (shots[0] if shots else "")
    session.confirm_plan("反向对照")
    if work:
        session.edit_prompt(work, append="反向对照：加一句方向")
        session.run_rework(work, "background_clutter")
    cids = session.candidates_of_shot(work)
    if cids:
        session.select(cids[0])
    miss = _missing(S.after_walk(session, work), S.REQUIRED_AFTER)
    if miss:
        problems.append("A 走完一遍之后缺内容：" + "；".join(miss))


def _case_b(problems: list) -> None:
    """空会话：没装配就没有内容。若这一条不红，说明标记清单是"写了就有"。"""
    empty = OFF.Session(project=ROOT, sku="未装配")
    pages = V.render_all(empty)
    leftover = []
    for path, markers in S.REQUIRED_INITIAL.items():
        page = pages.get(path, "")
        hit = [m for m in markers if m in page]
        if hit:
            leftover.append(f"/{path} 竟然还有「{'、'.join(hit)}」")
    if not leftover:
        return
    # 首页与导航页不依赖装配，允许它们仍然完整；其余页必须缺内容。
    real = [x for x in leftover if not x.startswith("/ ")]
    if real:
        problems.append("B 空会话下这些页面仍声称有内容：" + "；".join(real))


def _case_c(problems: list) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "keep.txt").write_text("a", encoding="utf-8")
        (root / "edit.txt").write_text("b", encoding="utf-8")
        (root / "drop.txt").write_text("c", encoding="utf-8")
        before = S.fingerprint(root)
        (root / "new.txt").write_text("d", encoding="utf-8")
        (root / "edit.txt").write_text("bb", encoding="utf-8")
        (root / "drop.txt").unlink()
        diff = S._fp_diff(before, S.fingerprint(root))
        joined = " / ".join(diff)
        for want in ("多了文件：new.txt", "少了文件：drop.txt", "被改过：edit.txt"):
            if want not in joined:
                problems.append("C 目录判据漏报：" + want + "（实得 " + joined + "）")
        extra = [d for d in diff if "keep.txt" in d]
        if extra:
            problems.append("C 目录判据误报：没动过的文件被报成 " + " / ".join(extra))


def _case_d(problems: list) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "one.bin"
        f.write_bytes(b"\x00\x01\x02")
        before = S.content_digest([f])
        f.write_bytes(b"\x00\x01\x03")
        after = S.content_digest([f])
        if before == after:
            problems.append("D 内容判据没发现改了一个字节")


def _case_e(problems: list) -> None:
    ok, why = S._guard_selftest()
    if not ok:
        problems.append("E 联网拦截自检没通过：" + why)


def _case_f(problems: list) -> None:
    """初始就有的东西不许充当「走完一遍」的证据 —— 这条反向判据自己也要有牙。

    做法：把一条初始页面上本来就有的标记塞进「走完一遍」清单，判据必须报出来。
    没有这一向，那条反向判据可能悄悄失效，而所有人继续看到绿灯。
    """
    session = OFF.build(ROOT, PKG.default(ROOT).sku)
    pages = V.render_all(session)
    saved = S.REQUIRED_AFTER
    try:
        S.REQUIRED_AFTER = dict(saved)
        S.REQUIRED_AFTER["workbench"] = tuple(saved.get("workbench", ())) + ("确认这个默认方案",)
        hits = [p for p in S.marker_problems(pages, pages) if "初始状态就有" in p]
    finally:
        S.REQUIRED_AFTER = saved
    if not hits:
        problems.append("F 判据没拦住「初始状态就有的东西充当走完一遍的证据」")


CASES = (("A", "真实会话八页都有内容", _case_a),
         ("B", "空会话必须缺内容", _case_b),
         ("C", "目录判据抓新增/删除/修改", _case_c),
         ("D", "内容判据抓单字节改动", _case_d),
         ("E", "联网拦截自检", _case_e),
         ("F", "初始就有的东西不许充当走完一遍的证据", _case_f))


def main() -> int:
    bad = 0
    print("离线走查判据的反向对照（" + str(len(CASES)) + " 向）")
    for code, name, fn in CASES:
        problems: list = []
        try:
            fn(problems)
        except Exception as exc:                    # noqa: BLE001
            problems.append(f"探针自己炸了：{type(exc).__name__}: {exc}")
        mark = "OK  " if not problems else "FAIL"
        print(f"[{mark}] {code} {name}")
        for p in problems:
            print("         " + p)
        bad += bool(problems)
    if bad:
        print(f"✗ {bad}/{len(CASES)} 向与预期不符")
        return 1
    print(f"OK：{len(CASES)} 向全部与预期一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
