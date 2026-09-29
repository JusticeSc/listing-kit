# -*- coding: utf-8 -*-
r"""本地入口：正式单页工作台 + 保留的 D2.R1 技术 tracer。

启动
----
    python app/server.py --offline-fixture demo/fixture/<商品包目录>
    python app/server.py --offline-fixture demo/fixture/<商品包目录> --check

为什么只有标准库
----------------
与「素材不出网、零部署」同一条约束：运营机器上一条命令就能起，不装包、不要账号、
不要域名。十来个路由、没有中间件、本地单用户，多一个 Web 框架只多一份装不上的风险。

这一层薄到什么程度
------------------
正式入口只负责提供静态单页和本地图片；页面通过统一 service interface 调进程内 Mock：

    /                         D2.R1c 单页工作台
    /static/<文件>            HTML/CSS/JS 静态资产
    /media/reference/<文件>   内置虚构商品参考图
    /media/candidate/<ID>     已冻结的历史真实候选
    /legacy、/task、/workbench、/export、/act  保留 D2.R1 tracer 以便回归

后端**没有**自己的状态机、任务队列、缓存或数据库：唯一的进程内状态是这个单用户
会话（点过的确认、改过的提示词、选过的候选），进程一停就回到冻结点 —— 这是刻意的，
离线走查要看的正是"陌生人能不能走通"，而不是"状态能不能活过重启"（那是 Phase 3）。

--check 是这套东西自己的判据，三件事一起验：

1. **项目目录零写入**：运行前后对整个项目做文件指纹（路径 + 大小 + 内容），必须逐字节一致；
2. **零网络**：自检期间任何 socket 连接尝试直接抛错；
3. **八页都取得到数据**：初始状态与走完一遍之后各渲染一次，逐页核对必须出现的内容；
   而且「走完一遍才出现」的每一条，在初始状态**必须不存在** —— 否则它只是页面上本来就有
   的一句话，分不清「走完一遍」和「什么都没做」（`/workbench` 还按看的那一张渲染）。

退出码
------
    0  起得来 / 自检全过
    1  自检不通过（目录被动过、读过的文件变了、页面该有的内容不在）
    2  装不起来（缺料或数据不成形）—— 起服务时把原因放在一页上，`--check` 时直接报这一码
    3  端口用不了 —— 提示换一个端口，不抛堆栈
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True          # 必须在导入项目模块之前：否则 __pycache__ 会破坏上面第 1 条

import argparse              # noqa: E402
import hashlib               # noqa: E402
import shutil                # noqa: E402
import socket                # noqa: E402
import subprocess            # noqa: E402
import threading             # noqa: E402
import time                  # noqa: E402
import urllib.parse          # noqa: E402
import webbrowser            # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer   # noqa: E402
from pathlib import Path     # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import offline as OFF     # noqa: E402
from app import views as V         # noqa: E402

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8"}

STATIC_FILES = {"index.html", "styles.css", "workbench.js", "service.js", "mock-service.js"}
REFERENCE_FILES = {"01-front-full.png", "02-upper-closeup.png", "03-lower-detail.png"}

# 自检要求逐页出现的内容。两份：刚装配时、走完一遍之后。
# 这些不是"大概有就行"，而是每页存在的理由 —— 少一条，那一页就没有在回答它该回答的问题。
REQUIRED_INITIAL = {
    "": ("虚构演示", "不用于真实上架", "阿里云百炼", "离线演示，不调用模型"),
    "task": ("要产出", "还没有候选"),
    "workbench": ("实际会发给模型的那段话", "锁住的事实", "谁给的结论",
                  "好不好看", "确认这个默认方案"),
    "export": ("离线演示，不写文件", "缺候选"),
}
# 「走过一遍」的痕迹：每一条都必须在初始状态**不存在**，否则它证明不了走没走。
# （2026-09-26 由 evals/probes/walkthrough_brief.py 的同型判据抓出两处：`版本记录` 与
#   `已选定` 在初始页面上本来就出现，前者还比对了另一张图的页面。）
REQUIRED_AFTER = {
    "workbench": ("已确认", "用户追加允许方向", "哪些不动", "原样输出"),
    "export": ("已选定",),
}


# ------------------------------------------------------------------ 判据用的小工具
def fingerprint(project: Path) -> dict:
    """第一层：全项目的路径 + 大小 + 修改时间。

    任何**普通**的写入都会改到这三个里至少一个；新增或删除文件改的是路径集合。
    只读元数据，所以对两 GB 的项目也是秒级。
    """
    out = {}
    for p in sorted(project.rglob("*")):
        if p.is_file():
            st = p.stat()
            out[p.relative_to(project).as_posix()] = (st.st_size, st.st_mtime_ns)
    return out


def content_digest(paths) -> dict:
    """第二层：逐字节内容哈希。只对**这次运行真正读过**的那些文件做，见 watched_paths。"""
    out = {}
    for path in sorted({str(x) for x in paths}):
        p = Path(path)
        if p.is_file():
            out[p.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def watched_paths(session) -> list:
    """这次演示真正读过的文件：整个商品包、参考包、以及四张候选原图。

    第一层管的是"目录有没有被动过"，这一层管的是"读进来的东西还是不是原来那份" ——
    后者只对读过的文件做，既省钱又比全盘扫更有针对性。
    """
    project = session.project
    out: list = []
    pkg_dir = project / str(session.package.get("package") or "")
    if pkg_dir.is_dir():
        out += [p for p in sorted(pkg_dir.rglob("*")) if p.is_file()]
    ref = (session.steps.get("PC-01").payload or {}).get("pack_dir") \
        if session.steps.get("PC-01") else None
    if ref:
        ref_dir = project / str(ref)
        if ref_dir.is_dir():
            out += [p for p in sorted(ref_dir.rglob("*")) if p.is_file()]
    out += [Path(c["file"]) for c in (session.candidates or {}).values()]
    static_dir = project / "app" / "static"
    out += [static_dir / name for name in sorted(STATIC_FILES)]
    out.append(project / "evals" / "probes" / "mock_workbench.mjs")
    return out


def static_workbench_problems(project: Path) -> tuple[list, str]:
    """检查正式单页的结构，并执行唯一的 JS Mock 轨迹判据。"""
    problems: list[str] = []
    static_dir = project / "app" / "static"
    for name in sorted(STATIC_FILES):
        if not (static_dir / name).is_file():
            problems.append("正式单页缺少 app/static/" + name)

    index_path = static_dir / "index.html"
    if index_path.is_file():
        html = index_path.read_text(encoding="utf-8")
        for marker in ("input-view", "plan-view", "inspector-view", "delivery-view",
                       "离线 Mock · 不调用模型", "Aster 01 是虚构商品"):
            if marker not in html:
                problems.append("正式单页缺少可见区域/边界：" + marker)

    js_text = "\n".join(
        (static_dir / name).read_text(encoding="utf-8")
        for name in ("workbench.js", "service.js", "mock-service.js")
        if (static_dir / name).is_file())
    for forbidden in ("dashscope.aliyuncs.com", "aliyuncs.com/api", "XMLHttpRequest(",
                      "new WebSocket(", "fetch("):
        if forbidden in js_text:
            problems.append("Mock 前端出现网络执行入口：" + forbidden)

    # 键盘在「事实核对 / 视觉判断」单选项上按键后，页面重渲染必须把焦点放回原处
    # （2026-09-27 修复的真实缺陷：没有锚点时焦点掉回 body，每选一项都要从页首重来）。
    for marker in ('data-focus-key="fact-${attr(fact.id)}-pass"', 'data-focus-key="visual-keep"'):
        if marker not in js_text:
            problems.append("正式单页缺少键盘焦点保持锚点：" + marker)

    probe = project / "evals" / "probes" / "mock_workbench.mjs"
    node = shutil.which("node")
    probe_output = ""
    if not probe.is_file():
        problems.append("缺少 Mock 轨迹探针 evals/probes/mock_workbench.mjs")
    elif node is None:
        problems.append("找不到 node，无法执行 Mock 状态轨迹判据")
    else:
        result = subprocess.run([node, str(probe)], cwd=str(project), capture_output=True,
                                text=True, encoding="utf-8", timeout=30, check=False)
        probe_output = (result.stdout or result.stderr).strip()
        if result.returncode != 0:
            problems.append("Mock 轨迹探针未通过：" + probe_output[:500])
    return problems, probe_output


def _fp_diff(before: dict, after: dict) -> list:
    out = []
    for rel in sorted(set(after) - set(before)):
        out.append("多了文件：" + rel)
    for rel in sorted(set(before) - set(after)):
        out.append("少了文件：" + rel)
    for rel in sorted(set(before) & set(after)):
        if before[rel] != after[rel]:
            out.append("被改过：" + rel)
    return out


class NoNetwork:
    """进这个 with 的代码一旦尝试建立连接就抛错。"""

    def __enter__(self):
        self._connect, self._connect_ex = socket.socket.connect, socket.socket.connect_ex

        def block(*_a, **_k):
            raise RuntimeError("离线模式不许联网：有代码尝试建立连接")

        socket.socket.connect = block
        socket.socket.connect_ex = block
        return self

    def __exit__(self, *_exc):
        socket.socket.connect = self._connect
        socket.socket.connect_ex = self._connect_ex
        return False


def _guard_selftest() -> tuple:
    """判据自己也要能被跑红：证明这个拦截真的会拦。"""
    with NoNetwork():
        try:
            socket.create_connection(("127.0.0.1", 9), timeout=0.05)
        except RuntimeError as exc:
            return True, str(exc)
        except OSError as exc:
            return False, "拦截没生效，真的去连了：" + type(exc).__name__ + ": " + str(exc)
        return False, "连接居然成功了 —— 拦截没生效"


def after_walk(session, work_shot: str) -> dict:
    """走完一遍之后的八页。

    /workbench 是按镜头渲染的：走路的人看的是 work_shot，所以判据要看的那一页也必须是 work_shot 的那一页。
    """
    pages = V.render_all(session)
    if work_shot:
            pages["workbench"] = V.page_workbench(session, shot_id=work_shot)
    return pages


def marker_problems(pages_initial: dict, pages_after: dict) -> list:
    """两份标记清单的判据：该有的必须有，且「走完一遍才出现」的初始状态不许有。

    放一处、供自检与反向对照共用 —— 判据只有一份，探针验的就是这一份。
    """
    out: list = []
    for path, markers in REQUIRED_INITIAL.items():
        page = pages_initial.get(path, "")
        for marker in markers:
            if marker not in page:
                out.append(f"初始状态页 /{path} 里找不到「{marker}」")
    for path, markers in REQUIRED_AFTER.items():
        initial = pages_initial.get(path, "")
        for marker in markers:
            if marker in initial:
                out.append(f"「走完一遍」的判据 /{path} 里的「{marker}」在初始状态就有 ——"
                           " 它分不清「走完一遍」和「什么都没做」")
    for path, markers in REQUIRED_AFTER.items():
        page = pages_after.get(path, "")
        for marker in markers:
            if marker not in page:
                out.append(f"走完一遍后页 /{path} 里找不到「{marker}」")
    return out


def check(project: Path, sku) -> int:
    problems: list = []
    t0 = time.time()
    before = fingerprint(project)

    guard_ok, guard_why = _guard_selftest()
    assembly_blocked = False
    mock_probe_output = ""
    with NoNetwork():
        session = OFF.build(project, sku)
        watched = watched_paths(session)
        content_before = content_digest(watched)
        blockers = session.blockers()
        shots = [s["shot_id"] for s in session.shots()]
        work_shot = session.candidate_shot or (shots[0] if shots else "")
        pages_initial = V.render_all(session)
        if blockers:
            # 装不起来的会话不走那一遍：走出来的读数没有意义，只会把"装配缺一环"
            # 混成几十条"页面缺内容"。
            assembly_blocked = True
            pages_after = None
            problems.append("装配没走通：" + "；".join(
                f"{cid} {getattr(res, 'outcome', '无结果')}" for cid, res in blockers))
        else:
            session.confirm_plan("离线自检")
            if work_shot:
                session.edit_prompt(work_shot, append="离线自检：把背景处理得更干净一些")
                session.run_rework(work_shot, "background_clutter")
            cids = session.candidates_of_shot(work_shot)
            if cids:
                session.select(cids[0])
            pages_after = after_walk(session, work_shot)

    static_issues, mock_probe_output = static_workbench_problems(project)
    problems.extend(static_issues)

    after = fingerprint(project)
    writes = _fp_diff(before, after)
    problems.extend("项目目录被写入：" + w for w in writes[:8])
    content_after = content_digest(watched)
    for rel in sorted(content_before):
        if content_after.get(rel) != content_before.get(rel):
            problems.append("读过的文件内容变了：" + Path(rel).name)

    if pages_after is not None:
        problems.extend(marker_problems(pages_initial, pages_after))

    print("=" * 72)
    print("离线产品自检（Phase 2 / D2.R1 + D2.R1c）")
    print("=" * 72)
    print(f"商品包：{session.sku}   项目：{project}")
    print(f"计划：{len(shots)} 张图   候选：{len(session.candidates)} 张"
          f"（属于 {session.candidate_shot or '—'}）")
    print()
    print(f"  联网拦截自检：{'会拦' if guard_ok else '没拦住'} —— {guard_why}")
    print(f"  目录被动过吗：{'没有' if not writes else str(len(writes)) + ' 处'}"
          f"（路径 / 大小 / 修改时间，覆盖 {len(before)} 个文件）")
    print(f"  读过的文件变了吗：{'没有' if len(content_after) == len(content_before) else '有'}"
          f"（逐字节，覆盖 {len(content_before)} 个 —— 商品包、参考包与"
          f"{len(session.candidates)} 张候选原图）")
    if pages_after is None:
        print("  四页数据：装配没走通 —— 没有走那一遍（走上也是假读数）")
    else:
        print(f"  四页数据：初始 {len(REQUIRED_INITIAL)} 页、"
              f"走完一遍 {len(REQUIRED_AFTER)} 页逐条核对")
    print("  正式单页：5 个业务区域 + service interface + 固定 Mock 边界")
    print("  Mock 轨迹：" + (mock_probe_output or "未取得探针输出"))
    print()
    if problems:
        print("problems（" + str(len(problems)) + " 条）：")
        for item in problems:
            print("  ✗ " + item)
        print()
        if assembly_blocked:
            print("结果：装不起来（退出码 2）—— 缺料就是缺料，不走那一遍。")
            return 2
        print("结果：不通过（退出码 1），用时 %.1fs。" % (time.time() - t0))
        return 1
    print("结果：全过（退出码 0），用时 %.1fs。" % (time.time() - t0))
    return 0


# ------------------------------------------------------------------ HTTP
def _finish(session, res, target: str, ok: str) -> str:
    """把一次动作的结果变成一句人话，然后回到该去的那一页。"""
    if res is None:
        session.flash = "这一步没有可用的结果"
    elif res.accepted:
        session.flash = ok
    else:
        session.flash = "；".join(res.notes[:2]) or ("结果：" + res.outcome)
    return target


def act(session, form: dict) -> str:
    """用户动作 → 会话。动作全部落在内存里，没有一个会写文件。"""
    op = form.get("op", "")
    if op == "confirm_plan":
        return _finish(session, session.confirm_plan("演示用户"), "/workbench",
                       "默认方案已确认；后面的提示词从这一版编译出来")
    if op == "edit_prompt":
        shot = form.get("shot", "")
        mode = form.get("mode", "append")
        text = form.get("text", "")
        res = session.edit_prompt(shot, append=(text if mode == "append" else None),
                                  raw_text=(text if mode == "raw" else None))
        return _finish(session, res, "/workbench?shot=" + urllib.parse.quote(shot),
                       "已生成新版本；旧版本原样保留")
    if op == "rework":
        shot = form.get("shot", "")
        res = session.run_rework(shot, form.get("reason", ""))
        return _finish(session, res, "/workbench?shot=" + urllib.parse.quote(shot),
                       "已按原因分流：只改该改的那一处")
    if op == "select":
        cid = form.get("c", "")
        if cid not in (session.candidates or {}):
            session.flash = "不认识这个候选"
            return "/workbench"
        return _finish(session, session.select(cid), "/workbench", "已选定成品")
    session.flash = "不认识这个动作"
    return "/"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "amz-listing-kit-offline/1"
    session = None
    lock = None

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    def _send(self, code: int, body, ctype: str = "text/html; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _redirect(self, target: str):
        self.send_response(303)
        self.send_header("Location", target)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):                                  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.strip("/")
        query = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        if path == "favicon.ico":
            return self._send(204, b"", "image/x-icon")
        if path == "":
            return self._static("index.html")
        if path.startswith("static/"):
            return self._static(urllib.parse.unquote(path.removeprefix("static/")))
        if path.startswith("media/reference/"):
            return self._reference(urllib.parse.unquote(path.removeprefix("media/reference/")))
        if path.startswith("media/candidate/"):
            return self._image(urllib.parse.unquote(path.removeprefix("media/candidate/")))
        if path == "img":
            return self._image(query.get("c", ""))
        legacy_path = "" if path == "legacy" else path
        try:
            with self.lock:
                flash = self.session.pop_flash()
                body = V.page_for(legacy_path, self.session, query, flash=flash)
        except KeyError:
            return self._send(404, "<!doctype html><meta charset=\"utf-8\">"
                                   "<h1>没有这一页</h1>")
        return self._send(200, body)

    def _static(self, name: str):
        if name not in STATIC_FILES:
            return self._send(404, "没有这个静态文件", "text/plain; charset=utf-8")
        path = ROOT / "app" / "static" / name
        if not path.is_file():
            return self._send(404, "静态文件不在原位", "text/plain; charset=utf-8")
        return self._send(200, path.read_bytes(), MIME.get(path.suffix.lower(),
                                                           "application/octet-stream"))

    def _reference(self, name: str):
        if name not in REFERENCE_FILES:
            return self._send(404, "没有这张参考图", "text/plain; charset=utf-8")
        path = ROOT / "evals" / "product-demo" / "fixture-design" / "pack" / name
        if not path.is_file():
            return self._send(404, "参考图不在原位", "text/plain; charset=utf-8")
        return self._send(200, path.read_bytes(), MIME.get(path.suffix.lower(),
                                                           "application/octet-stream"))

    def _image(self, cid: str):
        cand = (self.session.candidates or {}).get(cid)
        if not cand:
            return self._send(404, "没有这个候选", "text/plain; charset=utf-8")
        path = Path(cand["file"])
        if not path.is_file():
            return self._send(404, "候选文件不在原位", "text/plain; charset=utf-8")
        return self._send(200, path.read_bytes(),
                          MIME.get(path.suffix.lower(), "application/octet-stream"))

    def do_POST(self):                                 # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.strip("/") != "act":
            return self._send(404, "<!doctype html><meta charset=\"utf-8\">"
                                   "<h1>没有这个动作</h1>")
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", "replace")
        form = {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}
        with self.lock:
            target = act(self.session, form)
        return self._redirect(target)


def _sku_from(value) -> str:
    """--offline-fixture 收的是商品包**目录**；身份取自目录名，代码里不写商品名。"""
    if not value:
        raise SystemExit("要用 --offline-fixture 指定商品包目录，"
                         "例如 --offline-fixture demo/fixture/<包名>")
    return Path(str(value).rstrip("/\\")).name


class BlockedHandler(BaseHTTPRequestHandler):
    """装不起来时的最小页面：任何路径都给同一页，不生成、不修改任何文件。"""
    protocol_version = "HTTP/1.1"
    page = b""

    def do_GET(self):                                    # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(self.page)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(self.page)

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


BLOCKED_CSS = ("body{font-family:system-ui,'Segoe UI',sans-serif;max-width:46rem;"
               "margin:6vh auto;padding:0 1rem;line-height:1.7;color:#1f2937}"
               "h1{font-size:1.4rem}code{background:#f3f4f6;padding:.1rem .3rem;"
               "border-radius:4px}.why{color:#b45309;font-weight:600}")


def blocked_page(reason: str) -> str:
    """装不起来时给人看的页面：说清缺哪一份、去哪里补、补完怎么办。"""
    return ("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>装不起来 · 商品图片演示</title>"
            f"<style>{BLOCKED_CSS}</style></head><body>"
            "<h1>装不起来</h1>"
            f"<p class='why'>{V.h(reason)}</p>"
            "<p>这个页面不生成也不修改任何文件。装配先要能读到完整的商品包，"
            "缺一份就停在这里 —— 不拿别的商品、也不拿别一份数据顶上来。</p>"
            "<p>可以这样查：</p><ul>"
            "<li>上面点名的那份文件在不在商品包目录里"
            "（<code>demo/fixture/&lt;商品包&gt;/</code>）。少文件就把原始素材恢复回来，"
            "不要就地把文件改掉来过检。</li>"
            "<li>如果刚换过商品包：目录名要和启动时指的那个一致。</li>"
            "<li>补好之后，把启动命令原样再跑一次。</li></ul>"
            "</body></html>")


def bind(host: str, port: int, handler):
    """端口占用要说人话，不要抛堆栈。"""
    try:
        return ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        detail = str(exc.strerror or exc).strip().rstrip("。.")
        print(f"端口 {port} 用不了：{detail}。")
        print("换一个端口再起一次，例如：")
        print(f"    python app/server.py --offline-fixture <商品包目录> --port {port + 1}")
        return None


def serve_blocked(args, reason: str) -> int:
    """装不起来也要让人看得见原因：把话放在一页上，而不是只在控制台里。"""
    BlockedHandler.page = blocked_page(reason).encode("utf-8")
    httpd = bind(args.host, args.port, BlockedHandler)
    if httpd is None:
        return 3
    print("装不起来：" + reason)
    print("原因已经写在这一页上（不联网、不写文件）："
          f"http://{args.host}:{args.port}/")
    print("按 Ctrl+C 停止。")
    if args.open:
        webbrowser.open(f"http://{args.host}:{args.port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()
    return 2


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="商品图片演示的本地入口（离线只读模式）")
    ap.add_argument("--offline-fixture", default=None,
                    help="商品包目录，例如 demo/fixture/<包名>")
    ap.add_argument("--project", default=str(ROOT))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8778)
    ap.add_argument("--open", action="store_true", help="启动后打开浏览器")
    ap.add_argument("--check", action="store_true", help="只跑自检，不启动服务")
    args = ap.parse_args(argv)
    project = Path(args.project).resolve()
    sku = _sku_from(args.offline_fixture)
    if args.check:
        try:
            return check(project, sku)
        except OFF.OfflineError as exc:
            print("=" * 72)
            print("离线产品自检（Phase 2 / D2.R1 + D2.R1c）")
            print("=" * 72)
            print("装配没走通：" + str(exc))
            print()
            print("结果：装不起来（退出码 2）—— 缺料就是缺料，不换商品顶上来。")
            return 2
    try:
        session = OFF.build(project, sku)
    except OFF.OfflineError as exc:
        return serve_blocked(args, str(exc))

    Handler.session = session
    Handler.lock = threading.Lock()
    url = f"http://{args.host}:{args.port}/"
    httpd = bind(args.host, args.port, Handler)
    if httpd is None:
        return 3
    print("演示商品：" + str(session.card.get("display_name") or session.sku))
    print("完整 Mock 产品（不联网、不花钱、不写文件）：" + url)
    print("旧技术 tracer 保留在：" + url + "legacy")
    print("按 Ctrl+C 停止。")
    if args.open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
