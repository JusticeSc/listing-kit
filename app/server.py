# -*- coding: utf-8 -*-
r"""本地启动入口：默认启动 Product V2 正式入口；V1 与旧 Mock 作为回归入口保留。

常用命令
--------
    python app/server.py --open
    python app/server.py --check

Product V2（默认，端口 8780）：无状态服务器只提供页面与静态资源；项目、图片和历史全部保存在
浏览器 IndexedDB 中。服务器不保存工作空间、不保存最近项目，也没有 directory 之类的本机路径
参数。自检见 `python app/server.py --check`。

历史入口（回归用，不进 V2 导航）
--------------------------------
    python app/server.py --legacy-v1 --open
    python app/server.py --legacy-v1 --check

Product V1 支持本地文件夹工作空间、商品资料录入、参考图保存与重开恢复、商品理解、套图方案、
提示词编辑、真实图片生成、单张返工、候选选择与导出；业务记录写入 WorkspaceStore，图片生成走
config/product-v1/providers.json 注册的图片模型。

旧回归入口
----------
    python app/server.py --offline-fixture demo/fixture/<商品包目录>
    python app/server.py --offline-fixture demo/fixture/<商品包目录> --check

旧入口固定使用 Mock，仅供 D2.R1 状态轨迹与零写入/零联网回归，不代表当前产品前端。
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

try:  # 控制台编码归一（项目约定：每个入口自己保证中文输出不炸）
    from src.console import enable_utf8

    enable_utf8()
except Exception:  # 归一化失败不该让入口起不来
    pass

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
        for marker in ("input-view", "plan-view", "canvas-view", "inspector-view",
                       "delivery-view", "演示环境", "不用于真实上架"):
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
    for marker in ('data-focus-key="fact-${attr(fact.id)}-pass"', 'data-focus-key="visual-keep"',
                   'data-focus-key="candidate-${attr(candidate.id)}"'):
        if marker not in js_text:
            problems.append("正式单页缺少键盘焦点保持锚点：" + marker)

    # FE-04 的可视合同要落在渲染代码里，不能只活在审阅稿里（2026-09-27 对照抓到实现落后于合同）。
    for marker in ('class="candidate-stage"', 'class="candidate-main"',
                   'class="candidate-option"', 'id="form-error-summary"'):
        if marker not in js_text:
            problems.append("正式单页缺少 FE-04 组件：" + marker)

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
            print("  X " + item)
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


def run_doctor(host: str, port: int, legacy_v1: bool = False) -> int:
    """Check this machine can run the product; never starts a server or writes business files.

    默认检查 Product V2 正式入口；legacy_v1=True 时检查 Product V1 历史入口。
    """
    import importlib
    import json
    import os
    import tempfile

    results: list[tuple[str, str, str, str]] = []

    def add(status: str, name: str, detail: str, fix: str = "") -> None:
        results.append((status, name, detail, fix))

    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        add("pass", "Python", f"{version}（{sys.executable}）")
    else:
        add(
            "fail", "Python", f"{version} 过低（需要 3.10 以上）",
            "安装 Python 3.10+，或用 uv 启动：uv run --no-project "
            "--with-requirements requirements.txt python app/server.py --doctor",
        )

    if legacy_v1:
        required_files = [
            ROOT / "app" / "server.py",
            ROOT / "app" / "product_v1_server.py",
            ROOT / "src" / "product_prompt.py",
            ROOT / "config" / "product-v1" / "providers.json",
        ]
    else:
        required_files = [
            ROOT / "app" / "server.py",
            ROOT / "app" / "product_v2_server.py",
            ROOT / "app" / "product_v2" / "index.html",
            ROOT / "app" / "product_v2" / "app.js",
            ROOT / "app" / "product_v2" / "styles.css",
            ROOT / "app" / "product_v2" / "storage" / "index.js",
        ]
    missing = [str(item.relative_to(ROOT)) for item in required_files if not item.is_file()]
    if missing:
        add(
            "fail", "项目文件", "缺少：" + "、".join(missing),
            "在完整项目目录中运行（不要只拷走单个文件）",
        )
    elif legacy_v1:
        add("pass", "项目文件", "入口、服务与 provider 注册表齐全")
    else:
        add("pass", "项目文件", "入口、无状态适配器与 V2 产品资源齐全")

    missing_modules = []
    for module in ("PIL", "requests"):
        try:
            importlib.import_module(module)
        except Exception:
            missing_modules.append(module)
    if missing_modules:
        add(
            "fail", "运行依赖", "缺少：" + "、".join(missing_modules),
            "安装依赖：pip install -r requirements.txt（或 uv run --no-project "
            "--with-requirements requirements.txt python app/server.py）",
        )
    else:
        add("pass", "运行依赖", "Pillow 与 requests 可用")

    image_provider: dict | None = None
    if legacy_v1:
        registry_path = ROOT / "config" / "product-v1" / "providers.json"
        if registry_path.is_file():
            try:
                registry = json.loads(registry_path.read_text(encoding="utf-8"))
            except Exception as exc:
                add("fail", "Provider 注册表", f"无法解析：{type(exc).__name__}",
                    "修复 config/product-v1/providers.json 的 JSON 语法")
            else:
                providers = {item.get("id"): item for item in registry.get("providers") or []}
                image_id = registry.get("default_image_provider_id")
                semantic_id = registry.get("default_semantic_provider_id")
                image_provider = providers.get(image_id)
                semantic_provider = providers.get(semantic_id)
                if (image_provider is None or image_provider.get("role") != "image"
                        or not image_provider.get("model_id")):
                    add("fail", "Provider 注册表",
                        f"默认图片 provider {image_id!r} 未注册或缺少 model_id",
                        "在 providers.json 中登记图片 provider（默认 qwen-image-3.0）")
                elif semantic_provider is None or semantic_provider.get("role") != "semantic":
                    add("fail", "Provider 注册表", f"默认语义 provider {semantic_id!r} 未注册",
                        "在 providers.json 中登记语义 provider")
                else:
                    add("pass", "Provider 注册表",
                        f"图片 {image_id} / {image_provider.get('model_id')}；"
                        f"语义 {semantic_id} / {semantic_provider.get('model_id')}")

        key_env = (image_provider or {}).get("api_key_env") or "DASHSCOPE_API_KEY"
        if os.environ.get(key_env):
            add("pass", "模型凭据", f"已设置 {key_env}")
        else:
            add("warn", "模型凭据",
                f"未设置 {key_env}；页面能打开、方案能生成，但一键出图会失败",
                f'设置后重开终端：setx {key_env} "sk-..."')
    else:
        add("pass", "模型接入",
            "Product V2.1 不调用模型；语义与图片提供方在 V2.2 / V2.4 接入，"
            "到那一步才需要 DASHSCOPE_API_KEY")

    import socket as _socket
    with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as probe:
        probe.settimeout(1)
        busy = probe.connect_ex((host, port)) == 0
    if busy:
        add("fail", "端口", f"{host}:{port} 已被占用",
            f"换一个端口启动：python app/server.py --port {port + 1} --open")
    else:
        add("pass", "端口", f"{host}:{port} 可用")

    if legacy_v1:
        from app.product_v1_server import _default_recent_index_path

        index_dir = _default_recent_index_path().parent
        base = index_dir if index_dir.exists() else index_dir.parent
        writable = False
        try:
            with tempfile.NamedTemporaryFile(dir=base, prefix="amz-doctor-", delete=True):
                writable = True
        except Exception:
            writable = False
        if writable:
            add("pass", "工作空间索引目录",
                f"{index_dir} 可写" if index_dir.exists() else f"{index_dir} 将在首次使用时创建")
        else:
            add("fail", "工作空间索引目录", f"{index_dir} 不可写",
                "检查目录权限；产品仍可运行，但最近工作空间列表无法保存")
    else:
        add("pass", "用户数据位置",
            "Product V2 的项目与图片保存在浏览器 IndexedDB；服务器没有工作空间目录，"
            "也不写最近项目索引")

    print("=" * 72)
    product_label = "Product V1 历史入口" if legacy_v1 else "Product V2 正式入口"
    print(f"AMZ Listing Kit doctor（{product_label}；只检查，不修改任何业务文件）")
    print("=" * 72)
    labels = {"pass": "通过", "warn": "注意", "fail": "未通过"}
    for status, name, detail, fix in results:
        print(f"[{labels[status]}] {name}：{detail}")
        if fix:
            print(f"         修复：{fix}")
    failures = [item for item in results if item[0] == "fail"]
    warnings = [item for item in results if item[0] == "warn"]
    print("-" * 72)
    if failures:
        print(f"结果：暂不能启动（{len(failures)} 项未通过，{len(warnings)} 条提醒）。"
              "按上面的修复步骤处理后重试。")
        return 2
    print(f"结果：可以启动（{len(warnings)} 条提醒）。")
    if warnings:
        print("      提醒项不阻止启动；真实出图前先处理模型凭据。")
    return 0


def check_product_v1() -> int:
    """Run the real Product V1 HTTP slice checks without modifying this checkout."""
    check_script = ROOT / "tools" / "verify_product_v1_http.py"
    if not check_script.is_file():
        print("Product V1 自检文件缺失：tools/verify_product_v1_http.py")
        return 2
    print("Product V1 自检：工作空间 HTTP 闭环")
    return subprocess.run(
        [sys.executable, "-B", str(check_script)], cwd=str(ROOT), check=False,
    ).returncode


def check_product_v2() -> int:
    """Run the Product V2 formal-entry self-check; no model call, no file writes."""
    from app.product_v2_server import run_self_check

    print("Product V2 自检：无状态正式入口")
    return run_self_check()


def serve_product_v2(args) -> int:
    """Start the default Product V2 entry: static product shell, browser-owned state."""
    from app.product_v2_server import create_product_v2_server

    try:
        httpd = create_product_v2_server(args.host, args.port)
    except OSError as exc:
        detail = str(exc.strerror or exc).strip().rstrip("。.")
        print(f"端口 {args.port} 用不了：{detail}。")
        print(f"换一个端口再启动，例如：python app/server.py --port {args.port + 1}")
        return 3

    url = f"http://{args.host}:{args.port}/"
    print("本地商品套图工作台（Product V2）：" + url)
    if args.host in {"0.0.0.0", "::"}:
        try:
            lan = socket.gethostbyname(socket.gethostname())
            print(f"局域网/内网穿透访问：http://{lan}:{args.port}/")
        except OSError:
            pass
    print("项目与历史保存在这台浏览器里；服务器不保存工作空间，也不保存最近项目记录。")
    print("当前版本（V2.1）提供本机项目管理与项目包导入/导出；商品资料与出图流程随后续版本接入。")
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


def _load_offline_stack() -> None:
    """Load the legacy fixture implementation only for its explicit entrypoint."""
    global OFF, V
    from app import offline as offline_module
    from app import views as views_module

    OFF = offline_module
    V = views_module


def serve_product_v1(args) -> int:
    """Start the current blank-workspace product as the default local app."""
    from app.product_v1_server import create_product_server

    try:
        httpd = create_product_server(args.host, args.port)
    except ValueError as exc:
        print(str(exc))
        return 2
    except OSError as exc:
        detail = str(exc.strerror or exc).strip().rstrip("。.")
        print(f"端口 {args.port} 用不了：{detail}。")
        print(f"换一个端口再启动，例如：python app/server.py --port {args.port + 1}")
        return 3

    url = f"http://{args.host}:{args.port}/"
    print("本地商品套图工作台：" + url)
    print("覆盖流程：资料 → 商品理解 → 套图方案 → 提示词 → 真实出图 → 单张返工 → 选择 → 导出。")
    print("图片模型取决于本地 DASHSCOPE_API_KEY 与网络；未配置时页面会给出可执行的修复提示。")
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="本地商品套图工作台（默认 Product V2 无状态入口；"
                    "--legacy-v1 回 Product V1；--offline-fixture 保留旧 Mock 回归）"
    )
    ap.add_argument("--legacy-v1", action="store_true",
                    help="启动 Product V1 历史入口（文件夹工作空间 + 最近项目索引）")
    ap.add_argument("--offline-fixture", default=None,
                    help="启动旧离线 Mock 回归页面，例如 demo/fixture/<包名>")
    ap.add_argument("--project", default=str(ROOT))
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=None,
                    help="监听端口（Product V1 默认 8780，旧 Mock 默认 8778）")
    ap.add_argument("--open", action="store_true", help="启动后打开浏览器")
    ap.add_argument("--check", action="store_true",
                    help="只跑对应自检：Product V1 HTTP 闭环或旧 Mock 离线检查")
    ap.add_argument("--doctor", action="store_true",
                    help="只检查本机能否运行产品（不启动服务、不修改业务文件）")
    args = ap.parse_args(argv)
    if args.port is None:
        args.port = 8778 if args.offline_fixture else 8780
    if not args.offline_fixture:
        if args.legacy_v1:
            if args.doctor:
                return run_doctor(args.host, args.port, legacy_v1=True)
            return check_product_v1() if args.check else serve_product_v1(args)
        if args.doctor:
            return run_doctor(args.host, args.port)
        return check_product_v2() if args.check else serve_product_v2(args)

    _load_offline_stack()
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
