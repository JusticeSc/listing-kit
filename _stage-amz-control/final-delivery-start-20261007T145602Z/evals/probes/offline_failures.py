# -*- coding: utf-8 -*-
"""离线入口的三条失败路径：计划里承诺过，就必须能跑、能红。

用法
----
    python evals/probes/offline_failures.py
    python evals/probes/offline_failures.py --self-test   # 每条都验证"能红"

计划 §6.11.5 承诺了三件事：

    缺料      → 停在这里并说清缺哪一份，不进流程（起服务时给一页，人看得见）
    端口占用  → 明确提示换端口，不抛堆栈
    没有排版层 → 有文案记录时显示「未知」，不许按原样算成功

三条都曾经只是承诺：缺料抛的是 Python 堆栈，端口被占是 OSError，合成页把
「这一期没有文案」写死在界面里。这个探针把三条都变成可跑的读数。

A/B 两条起真进程、用真 HTTP 取页面；C 那两条直接调同一份渲染函数（要往方案里注入
一条文案记录，注入只能发生在进程内）—— 这里如实写明，不假装 C 也是走 HTTP 的。
"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PY = sys.executable


def run_server(args: list, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run([PY, "-X", "utf8", "app/server.py"] + args, cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_serve(project: Path | None, port: int) -> subprocess.Popen:
    args = ["--offline-fixture", "demo/fixture/aster-01", "--host", "127.0.0.1",
            "--port", str(port)]
    if project is not None:
        args += ["--project", str(project)]
    return subprocess.Popen([PY, "-X", "utf8", "app/server.py"] + args, cwd=str(ROOT),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def get(url: str, tries: int = 100) -> str:
    last = None
    for _ in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:                      # noqa: BLE001
            last = exc
            time.sleep(0.1)
    raise RuntimeError("页面取不到：" + repr(last))


def make_temp_project(drop: str) -> Path:
    """一个只够走到"缺料"的临时项目：不复制候选目录（缺料在装配第一步就该被拦住）。"""
    tmp = Path(tempfile.mkdtemp(prefix="amz-fail-"))
    (tmp / "config").mkdir(parents=True)
    shutil.copy2(ROOT / "config/slots.yaml", tmp / "config/slots.yaml")
    shutil.copytree(ROOT / "evals/product-demo/fixture-design/pack",
                    tmp / "evals/product-demo/fixture-design/pack")
    (tmp / "demo/fixture").mkdir(parents=True)
    shutil.copytree(ROOT / "demo/fixture/aster-01", tmp / "demo/fixture/aster-01")
    (tmp / "demo/fixture/aster-01" / drop).unlink()
    return tmp


def case_missing(drop: str, problems: list) -> str:
    """缺料：起服务时给一页说清缺哪一份；--check 时退出码 2，且都不是堆栈。"""
    tmp = make_temp_project(drop)
    try:
        port = free_port()
        proc = start_serve(tmp, port)
        try:
            page = get(f"http://127.0.0.1:{port}/")
        finally:
            proc.kill()
            proc.wait(timeout=10)
        if "装不起来" not in page:
            problems.append(f"[缺料 {drop}] 打开服务时没有「装不起来」这一页")
        elif drop not in page:
            problems.append(f"[缺料 {drop}] 那一页没有点名缺哪一份文件")
        if "阿里云百炼" in page or "离线演示，不调用模型" in page:
            problems.append(f"[缺料 {drop}] 缺料时仍然给了正常首页 —— 等于进了流程")

        r = run_server(["--project", str(tmp), "--offline-fixture",
                        "demo/fixture/aster-01", "--check"])
        if r.returncode != 2:
            problems.append(f"[缺料 {drop}] --check 退出码是 {r.returncode}，应当是 2")
        if drop not in (r.stdout or ""):
            problems.append(f"[缺料 {drop}] --check 没有点名缺哪一份文件")
        if "Traceback" in (r.stderr or ""):
            problems.append(f"[缺料 {drop}] 缺料抛出了 Python 堆栈，不是业务语言")
        line = [ln for ln in (r.stdout or "").splitlines() if "装配没走通" in ln]
        return (line[0].strip() if line else (r.stdout or "").strip())[:110]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def case_missing_reverse(problems: list) -> str:
    """反向：完好的包必须给正常首页（否则上面那条"缺料有页"可能只是页面写死了）。"""
    port = free_port()
    proc = start_serve(None, port)
    try:
        page = get(f"http://127.0.0.1:{port}/")
    finally:
        proc.kill()
        proc.wait(timeout=10)
    if "装不起来" in page:
        problems.append("[完好的包] 竟然也报装不起来")
    if "阿里云百炼" not in page:
        problems.append("[完好的包] 首页里找不到正常的说明内容")
    r = run_server(["--offline-fixture", "demo/fixture/aster-01", "--check"])
    if r.returncode != 0:
        problems.append(f"[完好的包] --check 退出码是 {r.returncode}，应当是 0")
    return "完好的包：首页正常，自检退出码 0"


def case_port_busy(problems: list) -> str:
    """端口占用：说人话 + 给出换端口的做法，且没有堆栈。"""
    holder = socket.socket()
    holder.bind(("127.0.0.1", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    try:
        r = run_server(["--offline-fixture", "demo/fixture/aster-01",
                        "--port", str(port)])
    finally:
        holder.close()
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 3:
        problems.append(f"[端口占用] 退出码是 {r.returncode}，应当是 3")
    if "端口" not in out or str(port) not in out:
        problems.append("[端口占用] 没有点名是哪个端口用不了")
    if str(port + 1) not in out:
        problems.append("[端口占用] 没有给出换成哪个端口再试")
    if "Traceback" in (r.stderr or ""):
        problems.append("[端口占用] 抛了 Python 堆栈")
    return [ln for ln in out.splitlines() if "端口" in ln][:1][0][:110]


def case_no_compose_layer(problems: list) -> str:
    """方案里有文案记录：工作台选中态必须说「未知」，不许按原样算成功。」"""
    from app import offline as OFF
    from app import views as V

    session = OFF.build(ROOT, "aster-01")
    session.confirm_plan("反向对照")
    cids = session.candidates_of_shot(session.candidate_shot)
    if not cids:
        problems.append("[排版层缺失] 这一期没有候选，测不了合成页")
        return "跳过"
    session.select(cids[0])
    before = V.page_workbench(session)
    payload = session.steps["PC-03"].payload
    payload["claims"] = [{"text": "保温 12 小时", "facts": ["F1"]}]
    after = V.page_workbench(session)
    if "未知" not in after:
        problems.append("[排版层缺失] 有文案记录时，合成页没有说「未知」")
    if "原样输出" in after:
        problems.append("[排版层缺失] 有文案记录时，合成页仍然按原样输出算成功")
    if "原样输出" not in before:
        problems.append("[反向] 没有文案记录时，合成页反而不说「原样输出」了")
    return "无文案 → 原样输出；有文案 → 未知"


def case_compose_reverse(problems: list) -> str:
    """反向：文案记录为空时，选中态必须给出「原样输出」的结论（不是永远说未知）。"""
    from app import offline as OFF
    from app import views as V

    session = OFF.build(ROOT, "aster-01")
    session.confirm_plan("反向对照")
    cids = session.candidates_of_shot(session.candidate_shot)
    if not cids:
        return "跳过"
    session.select(cids[0])
    page = V.page_workbench(session)
    if "原样输出" not in page:
        problems.append("[无文案] 合成页没有给出「原样输出」")
    if "未知" in page:
        problems.append("[无文案] 合成页在无文案时也报「未知」—— 判据没有区分能力")
    return "无文案时给出原样输出"


CASES = (("A1", "缺料：结构性前提（verifier_plan.json）", lambda p: case_missing("verifier_plan.json", p)),
         ("A2", "缺料：链上按需读的（threshold-derivation.json）", lambda p: case_missing("threshold-derivation.json", p)),
         ("A3", "缺料：连包都认不出来（product.json）", lambda p: case_missing("product.json", p)),
         ("A4", "反向：完好的包给正常首页", case_missing_reverse),
         ("B", "端口占用：说人话 + 给换法", case_port_busy),
         ("C1", "有文案记录：选中态说未知，不算成功", case_no_compose_layer),
         ("C2", "反向：无文案记录：选中态给原样输出", case_compose_reverse))


def main() -> int:
    bad = 0
    print("离线入口的三条失败路径（真进程 · 真 HTTP · 零付费）")
    print("=" * 72)
    for code, name, fn in CASES:
        problems: list = []
        try:
            detail = fn(problems)
        except Exception as exc:                      # noqa: BLE001
            problems.append(f"探针自己炸了：{type(exc).__name__}: {exc}")
            detail = ""
        mark = "OK  " if not problems else "FAIL"
        print(f"[{mark}] {code} {name}")
        if detail:
            print("         " + str(detail))
        for item in problems:
            print("         " + item)
        bad += bool(problems)
    print()
    if bad:
        print(f"✗ {bad}/{len(CASES)} 与预期不符")
        return 1
    print(f"OK：{len(CASES)} 项全部与预期一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
