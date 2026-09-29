# -*- coding: utf-8 -*-
r"""审核台后端：**只做转发**，不做工作流引擎。

启动
----
    python web/server.py            # 默认 127.0.0.1:8777
    python web/server.py --port 9000 --open

它薄到什么程度
--------------
    每个接口都只是"读一份已经存在的东西"或"调一个已经存在的函数"：

        /api/plan        → orchestrator.plan_run（**零副作用**，与 --dry-run 同一个函数）
        /api/run         → plan_run + execute（后台线程，进度靠 execute 的 progress 回调）
        /api/runs[/…]    → orchestrator.run_state（plan.json + run.jsonl 的派生）
        accept / redo    → orchestrator.mark_accept / redo
        export           → orchestrator.export_bundle

    ★ 后端**没有**自己的状态机、任务队列、缓存或数据库。
      唯一的进程内状态是"正在跑的那一轮的进度行"（内存里，丢了也不影响正确性）——
      权威状态永远在 `out/<UPC>_<stamp>/` 里。这条是刻意的：一旦接口层开始记状态，
      它和 run.jsonl 迟早对不上，而"哪个是真的"会变成需要读代码才能回答的问题。

为什么用标准库 http.server，而不是 Flask / FastAPI
--------------------------------------------------
    与"前端零工具链"同一个理由：**素材不出网、零部署**（使用形态 §4）。
    运营机器上 `python web/server.py` 就能起 —— 不装包、不要账号、不要域名。
    多一个 Web 框架就多一份"运营机器上装不上"的风险，而这里根本不需要它：
    十来个接口、没有中间件、没有鉴权（本地单用户，见使用形态 §7）。

序列化：为什么同一时刻只允许一件事在跑
--------------------------------------
    `_BUSY` 是刻意加的一把锁，两个理由都是实测出来的：

    1. **并发抠图会偶发抓不到内存**（ORT bad allocation / numpy MemoryError）。
       抠图前移到模型调用之前就是为了让它在进程最清爽的时候发生；同时开两轮
       等于把那个窗口又打开一次。
    2. **并发重做会撞版本号**：`redo()` 在动手前**一次性**算好所有 seq
       （靠数目录里的文件）。同一目录上跑两个重做，两边会算出同一个 seq，
       表现为后完成的那一版**覆盖**前一版 —— 而"新增版本、不覆盖"正是
       整套重做设计要保住的东西。

    CLI 不做这个限制（那是开发者的工具，他自己知道在干什么）；
    审核台是给运营用的，它必须替人守住这两条。

安全边界
--------
    只监听 127.0.0.1；`/api/file` 只允许读**项目目录内**的文件。
    "素材全程不出网"是这套形态的硬约束，所以"能读任意磁盘路径的文件接口"
    是不能接受的 —— 哪怕它只绑在本地。
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
import threading
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402  （控制台编码归一：见 src/console.py）
enable_utf8()

try:                                   # 位置 4 需要 key；有就真生成，没有就占位图
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

import assets as assets_mod        # noqa: E402
import intake                      # noqa: E402
import orchestrator                # noqa: E402
import registry                    # noqa: E402
import schema                      # noqa: E402
import yaml                        # noqa: E402

OUT_DIR = ROOT / "out"
PRODUCT_DIRS = ("examples",)       # 商品包目录（目录即投递，界面不设上传表单）

# ---- 进程内状态：只有进度行。丢了不影响正确性（权威状态在 run.jsonl 里）。
_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}        # run_id -> {phase, lines, error, kind}
_BUSY: str | None = None           # 正在跑的那一轮（None = 空闲）
MAX_LINES = 600


class ApiError(Exception):
    """带 HTTP 状态码的错误 —— 让"为什么要拒"能原样传到界面上。"""

    def __init__(self, code: int, message: str, **extra):
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra


# ---------------------------------------------------------------- 路径

def _safe(path_str: str, *, must_exist: bool = True) -> Path:
    """把请求里的路径解析成**项目目录内**的绝对路径。

    这是这个后端唯一的"安全"代码，所以它写得直白：解析 → 必须是 ROOT 的子路径。
    越界一律 403，不做"看起来像项目内"的模糊判断。
    """
    p = Path(unquote(str(path_str)))
    if not p.is_absolute():
        p = ROOT / p
    try:
        rp = p.resolve()
    except OSError as exc:
        raise ApiError(400, f"路径无法解析：{exc}") from exc
    try:
        rp.relative_to(ROOT)
    except ValueError as exc:
        raise ApiError(403, "越界：只允许访问项目目录内的文件") from exc
    if must_exist and not rp.exists():
        raise ApiError(404, f"文件不存在：{rp}")
    return rp


def _rel(p: Path) -> str:
    """项目内的相对路径，**统一用正斜杠**。

    为什么不用 `str(p.relative_to(ROOT))`：Windows 上它给反斜杠，而这个字符串
    的消费方有两个都更喜欢正斜杠 ——
        · 界面上它要作为 URL 查询参数回传（`?product=examples/product.json`）；
        · 界面上它也要显示给人看，`examples\\product.json` 不如 `/` 好读。
    反斜杠在 Windows 上确实也能被 Path 解析，但那意味着"接口返回的字符串只能
    在这一个平台上被当路径用"，而它其实只是个标识。统一成正斜杠，后端解析时
    不用改（Path 两种都认）。
    """
    return p.relative_to(ROOT).as_posix()


def _product_paths() -> list[Path]:
    """可选的商品包：各投递目录下的 *.json（目录即投递，不做上传界面）。"""
    out: list[Path] = []
    for d in PRODUCT_DIRS:
        base = ROOT / d
        if base.is_dir():
            out += sorted(base.glob("*.json"))
    return out


def _load_package(rel_or_abs: str):
    """读一个商品包。只允许读投递目录里的那些 —— 否则 /api/run 就能拿任意 json 跑。"""
    p = _safe(rel_or_abs, must_exist=True)
    allowed = {q.resolve() for q in _product_paths()}
    if p not in allowed:
        raise ApiError(403,
                       f"商品包必须在 {'/'.join(PRODUCT_DIRS)}/ 里（目录即投递）—— "
                       f"{p.name} 不在其中")
    return orchestrator.load_product(p)


def _run_dir(run_id: str, *, allow_pending: bool = False) -> Path:
    """run_id 就是产物目录名 —— 没有第二套标识，也就没有第二处映射。

    ★ allow_pending 是给 `/status` 用的，理由是一个真实会发生的时刻：
      `POST /api/run` 在**同步线程里**算完 plan 就把 run_id 返回了，而
      `plan.json` 是**后台线程**里的 execute 才写的。两者之间有一段窗口，
      界面在那段时间里第一次轮询 `/status` 就会 404 —— 表现是"刚点生成，
      进度就报错"。进度接口必须能回答"它正在跑"，哪怕计划还没落盘；
      而 accept / redo / export 要的是**既成事实**，它们仍然要求 plan.json。
      于是"放宽"这件事只属于进度接口，不属于写接口。
    """
    if not run_id or "/" in run_id or "\\" in run_id or run_id in (".", ".."):
        raise ApiError(400, f"非法的 run_id：{run_id!r}")
    d = OUT_DIR / run_id
    if not (d / "plan.json").exists():
        if allow_pending and run_id in _JOBS:
            return d
        raise ApiError(404, f"{run_id} 不是一次可审的 run（没有 plan.json）")
    return d


# ---------------------------------------------------------------- 后台任务

def _job_for(run_id: str) -> dict:
    with _LOCK:
        job = _JOBS.get(run_id)
        if job is None:
            job = {"phase": "unknown", "lines": [], "error": None, "kind": None}
            _JOBS[run_id] = job
        return job


def _append(run_id: str, line: str) -> None:
    with _LOCK:
        job = _JOBS.setdefault(run_id, {"phase": "running", "lines": [],
                                        "error": None, "kind": None})
        job["lines"].append(line)
        if len(job["lines"]) > MAX_LINES:
            del job["lines"][:MAX_LINES // 2]


def _start_job(run_id: str, kind: str, fn) -> None:
    """起一个后台任务。fn 收一个 progress 回调，返回一个 dict（可带 error 字段）。

    同一时刻只允许一件事在跑（见模块头的两条实测理由），所以 _BUSY 在这里把门。
    """
    global _BUSY
    with _LOCK:
        if _BUSY is not None:
            raise ApiError(409, f"已有一轮正在进行中（{_BUSY}）—— 缺省串行："
                                f"并发抠图偶发内存不足，并发重做会撞版本号。请等它跑完。")
        _BUSY = run_id
        _JOBS[run_id] = {"phase": "running", "lines": [], "error": None,
                         "kind": kind, "started": datetime.now().isoformat(timespec="seconds")}
    job = _JOBS[run_id]

    def progress(line: str) -> None:
        _append(run_id, str(line))

    def work() -> None:
        global _BUSY
        err = None
        try:
            rep = fn(progress) or {}
            err = rep.get("error")
        except Exception as exc:                     # noqa: BLE001 必须兜住，
            err = f"{type(exc).__name__}: {exc}"     # 否则线程静默死掉、界面永远转圈
            _append(run_id, traceback.format_exc().splitlines()[-1])
        finally:
            with _LOCK:
                job["phase"] = "error" if err else "done"
                job["error"] = err
                _BUSY = None

    threading.Thread(target=work, daemon=True, name=f"job-{kind}-{run_id}").start()


def _phase_of(run_id: str, state: dict) -> str:
    """这一轮现在处于什么状态。内存里有就信内存，没有就从日志推。"""
    job = _JOBS.get(run_id)
    if job and job["phase"] in ("running", "error"):
        return job["phase"]
    if job and job["phase"] == "done":
        return "done"
    return "done" if state.get("finished") else "unknown"


# ---------------------------------------------------------------- 读接口

def api_table() -> dict:
    """控制面：坑位表 + 渲染器声明 + 类目 + 重做档位说明。

    这是唯一一个"把配置直接读出来给界面看"的接口。它不做二次加工 ——
    renderer 的摘要来自 registry 的声明，档位说明来自 orchestrator.LAYER_DOC，
    素材清单来自 assets.ALL_KINDS：**一处定义，一个解释者**，界面只是渲染它。
    """
    cfg = schema.assert_valid()
    catalog = yaml.safe_load(
        (ROOT / cfg["catalog"]).read_text(encoding="utf-8")) or {}
    slots = []
    for s in cfg["slots"]:
        r = s["renderer"]
        slots.append({
            "slot_id": s["id"], "role": s.get("role"), "purpose": s.get("purpose"),
            "renderer": r, "text": s.get("text"), "mandatory": bool(s.get("mandatory")),
            "needs": s.get("needs") or [], "background": s.get("background"),
            "product_fill_pct": s.get("product_fill_pct"),
            "annotation": s.get("annotation"),
            "validate_level": s.get("validate_level"),
            "validate_rules": s.get("validate_rules") or [],
            # calls_model / cuts / summary / label 都来自渲染器的**声明**，不是猜的
            "calls_model": registry.calls_model(r),
            "cuts": list(registry.cuts_of(r)),
            "renderer_label": registry.label_of(r),
            "renderer_summary": registry.summary_of(r),
            "pixels": list(registry.backgrounds_of(r)),
        })
    return {
        "site": cfg["site"], "category": cfg["category"],
        "catalog": cfg["catalog"], "catalog_label": catalog.get("label"),
        "palette": catalog.get("palette") or {},
        # 位置 4 的取景池：它解释了"这一格的画面是从哪来的"，
        # 也解释了为什么换背景是唯一花钱的一档（其余五格的底来自 palette）。
        "bg_prompt_hints": catalog.get("bg_prompt_hints") or [],
        "export": cfg["export"],
        "slots": slots,
        "kinds": list(assets_mod.ALL_KINDS),
        "image_kinds": list(assets_mod.IMAGE_KINDS),
        "renderers": registry.describe(),
        "layers": orchestrator.LAYER_DOC,
        "run_dir_root": str(OUT_DIR),
        "product_dirs": list(PRODUCT_DIRS),
    }


def api_products() -> dict:
    """可选商品包（目录即投递）。"""
    out = []
    for p in _product_paths():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:                      # noqa: BLE001 一个坏包不该
            out.append({"path": _rel(p),                  # 让整个列表打不开
                        "error": f"{type(exc).__name__}: {exc}"[:200]})
            continue
        latest = orchestrator.latest_run(OUT_DIR, raw.get("upc") or "NOUPC")
        out.append({
            "path": _rel(p), "upc": raw.get("upc"),
            "title": raw.get("title"),
            "assets": sorted((raw.get("assets") or {}).keys()),
            "bullets": len(raw.get("bullets") or []),
            "specs": len(raw.get("specs") or []),
            "attested": sorted((raw.get("attest") or {}).get("confirmed") or []),
            "attest_by": (raw.get("attest") or {}).get("by"),
            # 这个包之前跑过没有 —— 界面据此提示"可以接着审上一轮"
            "latest_run": latest.name if latest else None,
        })
    return {"dirs": list(PRODUCT_DIRS), "products": out}


def _plan_payload(plan, pkg) -> dict:
    """把 RunPlan 压成界面要的形状（干跑与真跑共用，形状只有一份）。"""
    e0 = plan.e0
    return {
        "upc": plan.upc, "title": pkg.product.get("title"),
        "run_dir": plan.run_dir.name, "stamp": plan.stamp,
        "table_total": plan.table_total, "will_run": plan.will_run,
        "model_calls": plan.model_calls, "summary": plan.summary_line(),
        "rejected": plan.rejected,
        "needs_subject": plan.needs_subject, "cut_kinds": plan.cut_kinds,
        "needs_font": plan.needs_font, "needs_competitor": plan.needs_competitor,
        "facts": plan.facts, "supplied": plan.supplied, "broken": plan.broken,
        "skipped": plan.skipped,
        "decisions": [{
            "slot_id": d.slot_id, "role": d.role, "purpose": d.purpose,
            "renderer": d.renderer, "text": d.text, "background": d.background,
            "status": d.status, "missing": d.missing,
            "calls_model": d.calls_model, "pixels_from": d.pixels_from,
        } for d in plan.decisions],
        "e0": ({"images": e0.images, "notices": e0.notices,
                "attest": e0.attest, "attest_missing": e0.attest_missing,
                "font": e0.font} if e0 else None),
        # 签字行由 intake 渲染 —— 界面与 CLI 共用同一份说明文案
        "attest_lines": (intake.attest_lines(e0, needs_font=plan.needs_font,
                                             needs_competitor=plan.needs_competitor)
                         if e0 else []),
    }


def api_plan(query: dict) -> dict:
    """干跑：算这一次会出几张、调几次模型。**零副作用**（plan_run 本身不写盘）。

    它与 CLI 的 --dry-run 调的是同一个函数 —— 所以界面上的"本次将生成 N 张"
    和命令行打印的那一行是同一个数，不会出现两套口径。
    """
    if not query.get("product"):
        raise ApiError(400, "缺少 product 参数")
    pkg = _load_package(query["product"][0])
    only = _parse_only(query.get("only", [""])[0])
    plan = orchestrator.plan_run(pkg.product, only=only, out_dir=str(OUT_DIR),
                                 base_dir=pkg.base_dir, product_path=str(pkg.path))
    return {"ok": True, "dry_run": True, "plan": _plan_payload(plan, pkg)}


def _parse_only(raw: str) -> list[int] | None:
    vals = [x for x in str(raw or "").replace(" ", "").split(",") if x]
    return [int(x) for x in vals] if vals else None


def api_run(body: dict) -> dict:
    """真跑。plan 在**请求线程里**算完（于是 run_id 立刻可知），执行放后台。"""
    if not body.get("product"):
        raise ApiError(400, "缺少 product")
    pkg = _load_package(body["product"])
    # ★ 这里**不能**写成 `body.get("only") or None`：那会把 `only=[]` 变成 None，
    #   于是"一张都没勾"被悄悄当成"全跑" —— 正是下面那条防线要挡的静默失效，
    #   却是它自己造成的（`[] or None` 为 None）。区分"没传 only"与"only 是空的"，
    #   是这个参数唯一需要小心的地方。
    only = body.get("only", None)
    if only is not None:
        only = [int(x) for x in only]
        # 空列表必须显式拦住：plan_run 的 `if only:` 对空列表是**假**，
        # 于是"一张都没勾"会被悄悄当成"全跑"—— 一个静默的参数失效。
        if not only:
            raise ApiError(400, "没有选中任何坑位 —— 空列表会被当成\u201c全部\u201d，"
                                "所以这里直接拒绝，不猜你的意思")

    try:
        plan = orchestrator.plan_run(pkg.product, only=only, out_dir=str(OUT_DIR),
                                     base_dir=pkg.base_dir,
                                     product_path=str(pkg.path))
    except ValueError as exc:                 # 表本身有错：启动即炸，不烧调用费
        raise ApiError(400, f"启动失败：{exc}") from exc

    if plan.rejected:
        raise ApiError(409, f"整批拒绝：{plan.rejected}", rejected=plan.rejected)
    # 合规签字门禁：真跑才拦（干跑放行）—— 与 run.py 返回码 5 是同一条规矩。
    if plan.e0 and plan.e0.attest_missing:
        raise ApiError(409,
                       "合规项未签字：" + "、".join(plan.e0.attest_missing)
                       + " —— 这几项工具判不了，必须在商品包的 attest.confirmed 里"
                         "逐条确认后才允许出图（干跑不受此限）。",
                       unattested=plan.e0.attest_missing)

    run_id = plan.run_dir.name
    model = body.get("model") or None
    cutout = body.get("cutout") or None

    def work(progress):
        rep = orchestrator.execute(plan, cutout=cutout, model=model,
                                   progress=progress)
        if rep.get("subject_error"):
            return {"error": f"未出图 —— 主体无法从原片中分离：{rep['subject_error']}"}
        if rep.get("unattested"):
            return {"error": rep.get("message")}
        return {"ok": True, "model_calls_used": rep.get("model_calls_used")}

    _start_job(run_id, "run", work)
    return {"ok": True, "run_id": run_id, "plan": _plan_payload(plan, pkg),
            "output_dir": str(plan.run_dir)}


def api_runs(query: dict) -> dict:
    """最近一次可审的 run（目录本身就是历史 —— 不另加一层列表，见使用形态 §7）。"""
    upc = (query.get("upc") or [""])[0]
    if not upc:
        cands = sorted([d.name for d in OUT_DIR.glob("*")
                        if d.is_dir() and (d / "plan.json").exists()])
        return {"upc": None, "latest": cands[-1] if cands else None}
    d = orchestrator.latest_run(OUT_DIR, upc)
    return {"upc": upc, "latest": d.name if d else None}


def api_status(run_id: str) -> dict:
    """实时进度 + 全量读模型。

    一次调用同时给出"现在跑到哪了"（内存里的进度行）与"已经成了什么样"
    （run.jsonl 的派生）—— 界面因此不需要自己拼状态，也就没有第二个状态源。
    """
    d = _run_dir(run_id, allow_pending=True)
    state = orchestrator.run_state(d)
    job = _JOBS.get(run_id)
    return {
        "ok": True, "run_id": run_id,
        "phase": _phase_of(run_id, state),
        "kind": (job or {}).get("kind"),
        "error": (job or {}).get("error"),
        "lines": list((job or {}).get("lines") or []),
        "state": state,
    }


def api_log(run_id: str, query: dict) -> dict:
    """run.jsonl 的原文（给"展开日志"用）。

    直接给原文而不是给解析后的对象：调试时最需要的是**当时到底写了什么**，
    解析过一道就可能把坏行藏起来。坏行单独列出来，不静默丢。
    """
    d = _run_dir(run_id)
    p = d / "run.jsonl"
    if not p.exists():
        return {"ok": True, "lines": [], "bad_lines": []}
    raw = p.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = int((query.get("tail") or ["200"])[0] or 200)
    raw = raw[-tail:] if tail > 0 else raw
    good, bad = [], []
    for ln in raw:
        if not ln.strip():
            continue
        try:
            good.append(json.loads(ln))
        except json.JSONDecodeError:
            bad.append(ln[:300])
    return {"ok": True, "lines": good, "bad_lines": bad, "count": len(good)}


# ---------------------------------------------------------------- 写接口

def api_accept(run_id: str, slot_id: int, body: dict) -> dict:
    d = _run_dir(run_id)
    try:
        state = orchestrator.mark_accept(d, slot_id, seq=body.get("seq"),
                                         by=body.get("by"))
    except ValueError as exc:
        raise ApiError(400, str(exc)) from exc
    return {"ok": True, "state": state}


def api_redo(run_id: str, slot_id: int, body: dict) -> dict:
    """重做某一格。**后台跑**（bg 档要等约 70s），界面走同一条进度通道。

    重做需要"当次输入"（product）。它从 plan.json 里记的商品包路径重新加载 ——
    于是界面上点重做不需要人再选一次商品包，也不会误用别的包。
    """
    d = _run_dir(run_id)
    layer = body.get("layer") or "text"
    if layer not in orchestrator.LAYERS:
        raise ApiError(400, f"layer={layer!r} 非法，可选：{'/'.join(orchestrator.LAYERS)}")

    state = orchestrator.run_state(d)
    prod = body.get("product") or state.get("product")
    if not prod:
        raise ApiError(409,
                       "这一轮没有记录它用的商品包（M7 之前的 run）—— "
                       "无法重做。请先按现状整批重跑一次；或在请求里显式带上 product。")
    pkg = _load_package(prod)
    model = body.get("model") or None
    cutout = body.get("cutout") or None

    def work(progress):
        rep = orchestrator.redo(d, pkg.product, slot_id, layer=layer,
                                base_dir=pkg.base_dir, cutout=cutout,
                                model=model, progress=progress)
        return {"ok": True, "layer": rep["layer"], "results": rep["results"],
                "model_calls": rep["model_calls"]}

    _start_job(run_id, f"redo:{layer}:{slot_id}", work)
    return {"ok": True, "run_id": run_id, "accepted_layer": layer,
            "accepted_slot": slot_id}


def api_export(run_id: str) -> dict:
    d = _run_dir(run_id)
    try:
        rep = orchestrator.export_bundle(d)
    except ValueError as exc:
        raise ApiError(409, str(exc)) from exc
    opened = False
    if os.name == "nt":
        try:                     # 打开系统文件管理器（本地 Web 的"打开输出目录"）
            os.startfile(str(d))  # type: ignore[attr-defined]
            opened = True
        except OSError:
            opened = False
    return {"ok": True, "opened_finder": opened, **{k: rep[k] for k in
            ("manifest", "manifest_dir", "files", "skipped", "counts")}}


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "amz-listing-kit/1.0"

    # ---- 输出
    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, p: Path) -> None:
        ctype = (mimetypes.guess_type(p.name)[0]
                 or ("image/jpeg" if p.suffix.lower() in (".jpg", ".jpeg")
                     else "application/octet-stream"))
        data = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        # 产物会被重做替换（subject.png 同名覆盖），所以**不许缓存** ——
        # 否则"重做完了界面还是旧图"，而那种不一致最难被发现。
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode("utf-8")) or {}
        except json.JSONDecodeError as exc:
            raise ApiError(400, f"请求体不是合法 JSON：{exc}") from exc

    def log_message(self, fmt, *args):        # 静音：进度已经通过接口给了前端
        pass

    # ---- 路由
    def do_GET(self) -> None:                 # noqa: N802
        u = urlparse(self.path)
        q = parse_qs(u.query)
        parts = [p for p in u.path.split("/") if p]
        try:
            if not parts or parts == ["index.html"]:
                return self._send_file(ROOT / "web" / "index.html")
            if parts == ["favicon.ico"]:
                self.send_response(204)
                self.end_headers()
                return
            if parts[:1] != ["api"]:
                raise ApiError(404, f"没有这个页面：{u.path}")

            rest = parts[1:]
            if rest == ["table"]:
                return self._send(200, {"ok": True, **api_table()})
            if rest == ["products"]:
                return self._send(200, {"ok": True, **api_products()})
            if rest == ["plan"]:
                return self._send(200, api_plan(q))
            if rest == ["runs"]:
                return self._send(200, {"ok": True, **api_runs(q)})
            if rest == ["file"]:
                if not q.get("path"):
                    raise ApiError(400, "缺少 path 参数")
                return self._send_file(_safe(q["path"][0]))
            if len(rest) >= 2 and rest[0] == "runs":
                run_id = rest[1]
                if len(rest) == 2:
                    # 同样是读接口：刚起的一轮在 plan.json 落盘前也要能查（见 _run_dir）
                    d = _run_dir(run_id, allow_pending=True)
                    state = orchestrator.run_state(d)
                    return self._send(200, {"ok": True, "run_id": run_id,
                                            "phase": _phase_of(run_id, state),
                                            "state": state})
                if len(rest) == 3 and rest[2] == "status":
                    return self._send(200, api_status(run_id))
                if len(rest) == 3 and rest[2] == "log":
                    return self._send(200, api_log(run_id, q))
            raise ApiError(404, f"没有这个接口：{u.path}")
        except ApiError as exc:
            self._send(exc.code, {"ok": False, "error": exc.message, **exc.extra})
        except Exception as exc:              # noqa: BLE001 任何未预期错误都要
            self._send(500, {"ok": False,        # 变成一条界面看得见的错误，
                             "error": f"{type(exc).__name__}: {exc}",  # 而不是静默 500
                             "trace": traceback.format_exc().splitlines()[-3:]})

    def do_POST(self) -> None:                # noqa: N802
        u = urlparse(self.path)
        parts = [p for p in u.path.split("/") if p]
        try:
            body = self._body()
            if parts[:1] != ["api"]:
                raise ApiError(404, f"没有这个接口：{u.path}")
            rest = parts[1:]
            if rest == ["run"]:
                return self._send(200, api_run(body))
            if rest and rest[0] == "runs" and "slots" in rest:
                # /api/runs/<id>/slots/<n>/<action>
                if len(rest) != 5:
                    raise ApiError(404, "槽位接口要写成 "
                                        "/api/runs/<run_id>/slots/<n>/accept|redo")
                try:
                    slot_id = int(rest[3])
                except ValueError as exc:
                    raise ApiError(400, f"坑位号不是整数：{rest[3]!r}") from exc
                act = rest[4]
                if act == "accept":
                    return self._send(200, api_accept(rest[1], slot_id, body))
                if act == "redo":
                    return self._send(200, api_redo(rest[1], slot_id, body))
                raise ApiError(404, f"没有这个动作：{act}")
            if len(rest) == 3 and rest[0] == "runs" and rest[2] == "export":
                return self._send(200, api_export(rest[1]))
            raise ApiError(404, f"没有这个接口：{u.path}")
        except ApiError as exc:
            self._send(exc.code, {"ok": False, "error": exc.message, **exc.extra})
        except Exception as exc:              # noqa: BLE001
            self._send(500, {"ok": False,
                             "error": f"{type(exc).__name__}: {exc}",
                             "trace": traceback.format_exc().splitlines()[-3:]})


def main() -> int:
    ap = argparse.ArgumentParser(description="审核台（本地 Web，素材不出网）")
    ap.add_argument("--host", default="127.0.0.1",
                    help="只绑本机回环（默认）；素材不出网是这套形态的硬约束")
    ap.add_argument("--port", type=int, default=8777)
    # --out 与 run.py 同名同义：CLI 与审核台必须能指向同一个产物根，
    # 否则"命令行跑完、审核台打开就审"这句话就不成立（使用形态 §5）。
    ap.add_argument("--out", default=str(ROOT / "out"))
    ap.add_argument("--open", action="store_true", help="启动后打开浏览器")
    args = ap.parse_args()

    global OUT_DIR
    OUT_DIR = Path(args.out).resolve()
    if ROOT not in OUT_DIR.parents and OUT_DIR != ROOT:
        print(f"提醒：产物根 {OUT_DIR} 在项目目录之外 —— 界面将无法预览产物图"
              f"（/api/file 只允许项目目录内的路径）。")

    schema.assert_valid()                  # 表错了在起服务之前就炸
    registry.load_all()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}/"
    print(f"审核台已启动：{url}")
    print(f"  坑位表  {ROOT / 'config' / 'slots.yaml'}")
    print(f"  产物根  {OUT_DIR}")
    print(f"  商品包  {', '.join(str(ROOT / d) for d in PRODUCT_DIRS)}")
    if not (ROOT / ".env").exists():
        print("  提醒：没有 .env（无 DASHSCOPE_API_KEY）—— 位置 4 会退化成占位背景，"
              "其余六格仍是真实像素。")
    print("  Ctrl+C 停止")
    if args.open:
        import webbrowser
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
