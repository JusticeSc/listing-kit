r"""M7 验收 —— 界面接线。**不靠目测。**

用法：
    python tools/verify_m7.py            # 沙箱 = out_verify_m7/<时间戳>/，跑完**默认保留**
    python tools/verify_m7.py --clean    # 跑完试着删掉这一轮沙箱（删不掉也不影响结论）

为什么默认不删：本机的批量删除会拦住"删早先轮次留下的内容"，而清理又排在结论路径上，
于是"删不掉"曾经冒充成"验收失败"。理由详见 SANDBOX 上方注释与 main 收尾处。

它分两部分，因为这两部分坏掉的样子完全不同：

    A 领域读模型（进程内）
        采纳 / 重做 / 导出 / 版本号 / 日志容错 的规则对不对
    B HTTP 契约（**起一个真服务**）
        界面拿到的是不是同一份事实；接口边界守没守住

**为什么必须起真服务**：M7 的全部内容就是"把界面接到真实执行上"。
用一个只在内存里调函数的测试去证明它，等于绕开了要验的那一段。

它断言的结构性质（每条都对应一个真实会出错的写法）：

    A1  plan_run 零副作用 —— 干跑不留任何文件（不然"先看看会出几张"会污染产物）
    A2  一次 run 只产出一份 subject.png（不变量 A），且声明调模型的只有位置 4
    A3  版本号能从文件名尾号推出（与 export.filename_pattern 一致，不是另一套编号）
    A4  采纳**落盘**到 run.jsonl —— 采纳率是外环回流的原料，不写下来就不存在
    A5  重做新增版本、旧版逐字节不变；且那次采纳**作废**（回到待审）
    A6  比较之后**仍采纳旧版**要能成立
        —— 「已采纳 == 采纳版号等于最新版号」这种写法会让这种情形永远登记不上
    A7  界面能点的重做档位，与表/渲染器声明一致（位置 1 没有"文案不对"）
    A8  导出闸门：未全采纳 → 拒；且交付的是**被采纳的那一版**，清单 sha256 可自证
    A9  日志被并发写坏半行时：读模型不炸，且**把坏行数报出来**（容错≠静默）
    A10 不显式要求容错时，坏行必须抛 —— 容错是选择，不是默认吞掉
    B1  首页是审核台
    B2  坑位表与渲染器声明抵达界面；**只有位置 4 声明调模型**
    B3  干跑接口与 CLI 的 --dry-run 是同一个数（同一个函数，不会有两套口径）
    B4  商品包目录可枚举（投递是目录约定，界面不设上传表单）
    B5  /api/run 同步返回 run_id（= 产物目录名），执行在后台；并发第二次被拒
    B6  进度轮询能到 done，且状态来自 run.jsonl 而不是接口层自己记的
    B7  HTTP 采纳 / 重做 / 导出 与进程内是同一套事实
    B8  路径穿越被拦（只允许项目目录内）
    B9  参数与用法错误有明确返回码，不静默跑

退出码：0 全过 / 1 有断言失败 / 2 环境问题

副作用：会在 out_verify_m7/ 里真跑两次（每次含一次本地抠图，合计约 40s），
       并在里面做采纳 / 重做 / 导出。之所以隔离：验收会写 accept 记录，
       而 accept 会改变"这一轮审完没有"这个事实，不该落到真实产物上。

★ 报告**同时写一份 UTF-8 文件**（evals/verify_m7_report.txt，与 evals/last_regress.txt
  并排）。原因很实际：这台机器的控制台管道会把中文转码，直接看 stdout 得到的是乱码，
  于是"这一条到底过没过"反而看不清。文件是唯一可靠的读数通道。
  位置也踩过：初版写在**项目根**，与其余验收报告不在同一处，于是"报告在哪"要靠猜 ——
  验收的产物就和验收的其他产物放在一起。

★ 关于文案里的引号：本文件在字符串**内容**里的引号一律写成 \\u201c / \\u201d
  转义，不写字面弯引号。这不是洁癖 —— 本脚本第一版就因为写入时的一些
  字节损坏，把内容里的弯引号变成了 ASCII 直引号，导致 Python 源码字符串
  提前闭合（SyntaxError: Perhaps you forgot a comma?）。转义是 ASCII 字节，
  不经过任何编码转换，因此不会再被改写。见 src/orchestrator.py 同样的做法。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402  （控制台编码归一：见 src/console.py）
enable_utf8()

import orchestrator  # noqa: E402
import registry  # noqa: E402

OK, BAD = "\u2713", "\u2717"
Q1, Q2 = "\u201c", "\u201d"          # 文案里的引号，只以转义形式出现
# 隔离产物根：**每次跑新开一个时间戳子目录**，且默认**不删任何旧目录**（2026-09-22 定稿）。
# 两件事都踩过，结论是同一条：
#   · 删顶层目录会被导去回收站并 fail-closed（SHFileOperationW 0x2），脚本死在清理那一步；
#   · 连"删这一轮的子目录"也会被批量删除的闸拦下 —— 闸护的是**早先轮次留下的内容**，
#     数量过线就要显式确认，拦下即 fail-closed。
# 所以让沙箱天然不需要被删，比想办法绕过删除限制更省事，也不会把"清理失败"混进结论。
# 旧目录留着不影响任何断言 —— 断言引用的都是这一轮新生成的名字。
SANDBOX_ROOT = ROOT / "out_verify_m7"
SANDBOX = SANDBOX_ROOT / time.strftime("%Y%m%d-%H%M%S")
CLEAN = "--clean" in sys.argv      # 默认保留沙箱；要删得显式说，删不掉也不改结论
LOG = "run.jsonl"
REPORT = ROOT / "evals" / "verify_m7_report.txt"
_BUF: list[str] = []


def R(s: str = "") -> None:
    """打印 + 收集。收集的那份最后写进 UTF-8 报告文件。"""
    _BUF.append(s)
    print(s)


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def head(t: str) -> None:
    R("\n" + t)


def okf(cond: bool, msg: str, fails: list[str]) -> None:
    R(f"   {OK if cond else BAD} {msg}")
    if not cond:
        fails.append(msg)


# ================================================================ 起服务

def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def req(base: str, path: str, body=None):
    """返回 (状态码, JSON)。HTTP 错误也把 JSON 取回来 —— 错误文案本身是要验的。

    注意关键字是 `data=` 而不是 `body=` —— `urllib.request.Request` 的签名里
    没有 body（第一版脚本在这里 TypeError 过一次，而这属于"脚本自己的 bug"，
    会让整段 B 直接崩掉，所以它在 A 全绿的情况下把 B 藏了起来）。
    """
    opt = {"method": "POST", "headers": {"Content-Type": "application/json"},
           "data": json.dumps(body).encode("utf-8")} if body is not None else {}
    r = urllib.request.Request(base + path, **opt)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw[:300]}


def req_raw(base: str, path: str):
    """读**非 JSON** 响应（`/api/file` 返回的是图片字节）。

    没有它，日志里就会出现"用 json.loads 去解析一张 JPEG"这种
    UnicodeDecodeError —— 而它看起来像被测代码的错，其实是脚本的错。
    """
    try:
        with urllib.request.urlopen(base + path, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def start_server(out_dir: Path):
    """起真服务。

    ★ 服务日志写到 SANDBOX 根，**不写进 out_dir** —— out_dir 是这一段的产物根，
      B3 要断言"干跑没在里面留下任何东西"。把服务自己的日志放进去，
      那条断言就会因为一个与业务无关的文件而失败。
    """
    port = free_port()
    log = (SANDBOX / "server.log").open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-X", "utf8", str(ROOT / "web" / "server.py"),
         "--port", str(port), "--out", str(out_dir)],
        cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(120):                       # 最多等 60s（表校验 + 渲染器加载）
        if proc.poll() is not None:
            raise RuntimeError(f"服务起不来，退出码 {proc.returncode}（见 {SANDBOX}/server.log）")
        try:
            code, _ = req(base, "/api/table")
            if code == 200:
                return proc, base, log
        except Exception:                      # noqa: BLE001 没起来就继续等
            time.sleep(0.5)
    raise RuntimeError("服务 60s 内没有就绪")


def wait_phase(base: str, run_id: str, timeout: float = 240.0) -> dict:
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        _, j = req(base, f"/api/runs/{run_id}/status")
        last = j
        if j.get("phase") in ("done", "error"):
            return j
        time.sleep(0.7)
    return last or {}


# ================================================================ A 领域读模型

def part_a(fails: list[str]) -> Path:
    """A 部分跑**两个坑位**（1 与 5），不是为了多测一格，而是为了 A8 ——
    导出闸门只有在"有一部分已采纳、另一部分没有"时才存在。
    只跑位置 1 的话，那一格一采纳就全采纳了，闸门永远走不到（断言会假绿）。
    """
    out = SANDBOX / "a"
    pkg = orchestrator.load_product(ROOT / "examples" / "product_fullset.json")
    R("A. 领域读模型（进程内）")

    # ---- A1 干跑零副作用
    plan = orchestrator.plan_run(pkg.product, only=[1, 5], out_dir=str(out),
                                 base_dir=pkg.base_dir, product_path=str(pkg.path))
    head("A1 干跑（plan_run）不留任何文件")
    okf(not plan.run_dir.exists(), f"plan 里的目录 {plan.run_dir.name} 没有被创建", fails)
    okf(plan.model_calls == 0,
        f"only=1,5 的模型调用 = {plan.model_calls}（这两格都零模型）", fails)

    # ---- A2 真跑
    orchestrator.execute(plan)
    rd = plan.run_dir
    st = orchestrator.run_state(rd)
    head("A2 一次 run = 一份 subject.png；两格各成一个版本")
    okf(len(list(rd.glob("subject.png"))) == 1,
        "subject.png 恰好一份（不变量 A：所有坑位读同一个文件）", fails)
    okf(st["counts"]["done"] == 2 and st["finished"],
        f"done={st['counts']['done']} finished={st['finished']} bad_lines={st['log_bad_lines']}", fails)
    okf(st["counts"]["model_calls_used"] == 0,
        f"实际模型调用 = {st['counts']['model_calls_used']}（位置 1/5 声明零模型）", fails)
    okf(st["product"] == str(pkg.path),
        "plan.json 记下了这一轮用的商品包（重做要凭它重新加载输入）", fails)

    # ---- A3 版本号
    s1 = next(s for s in st["slots"] if s["slot_id"] == 1)
    ver = s1["versions"][0]
    head("A3 版本号可由文件名推出（与 filename_pattern 一致）")
    okf(ver["seq"] == 1 and ver["file"].endswith("_1.jpg"),
        f"第 1 版文件名 {ver['file']} —— 尾号就是 seq，没有第二套编号", fails)
    v1 = Path(ver["path"])
    v1_sha = sha(v1)

    # ---- A4 采纳落盘
    head("A4 采纳写进 run.jsonl（状态源只有一个）")
    n_before = len((rd / LOG).read_text(encoding="utf-8").splitlines())
    st = orchestrator.mark_accept(rd, 1)
    n_after = len((rd / LOG).read_text(encoding="utf-8").splitlines())
    s1 = next(s for s in st["slots"] if s["slot_id"] == 1)
    okf(s1["accepted"] and s1["accepted_seq"] == 1,
        f"accepted={s1['accepted']} seq={s1['accepted_seq']}", fails)
    okf(n_after == n_before + 1 and
        orchestrator.read_records(rd)[-1]["stage"] == "accept",
        f"日志追加了一条 accept（{n_before} → {n_after} 行）", fails)

    # ---- A5 重做：新增版本 + 采纳作废
    head("A5 重做新增版本（旧版一个字节都不动），且上次采纳随之作废")
    rep = orchestrator.redo(rd, pkg.product, 1, layer="placement", base_dir=pkg.base_dir)
    st = orchestrator.run_state(rd)
    s1 = next(s for s in st["slots"] if s["slot_id"] == 1)
    okf(v1.exists() and sha(v1) == v1_sha, "第 1 版文件与内容都没被改动（不覆盖）", fails)
    okf([v["seq"] for v in s1["versions"]] == [1, 2],
        f"版本列表 = {[v['seq'] for v in s1['versions']]}", fails)
    okf(not s1["accepted"],
        f"上次采纳已作废（回到待审）—— 重做是{Q1}这一张又变了{Q2}，得重新看", fails)
    okf(rep["model_calls"] == 0, "layer=placement 零模型（复用生成底那一条）", fails)

    # ---- A6 仍采纳旧版
    head("A6 比较之后仍采纳旧版：要能登记")
    st = orchestrator.mark_accept(rd, 1, seq=1, by="验收脚本")
    s1 = next(s for s in st["slots"] if s["slot_id"] == 1)
    okf(s1["accepted"] and s1["accepted_seq"] == 1,
        f"accepted={s1['accepted']} 采纳的版号={s1['accepted_seq']}"
        f"（最新已是第 {s1['latest']['seq']} 版）", fails)
    okf(sha(v1) == v1_sha, "采纳没有偷偷改动任何一版", fails)

    # ---- A7 layers
    head("A7 界面能点的档位由表与渲染器声明算出")
    okf("text" not in s1["layers"] and "bg" not in s1["layers"],
        f"位置 1 的档位 {s1['layers']} —— 没有{Q1}文案不对{Q2}（text=none），"
        f"也没有{Q1}背景不对{Q2}（零模型，没有生成层可换）", fails)
    okf(set(s1["layers"]) <= set(orchestrator.LAYERS),
        "档位全部落在重做粒度集合内", fails)
    lay4 = orchestrator._layers_ok(
        {"slot_id": 4, "renderer": "gen_bg_paste", "text": "none",
         "needs": ["front"]}, rd)
    lay5 = orchestrator._layers_ok(
        {"slot_id": 5, "renderer": "closeup_crop", "text": "overlay",
         "needs": ["closeup"]}, rd)
    okf("bg" in lay4 and "cutout" in lay4,
        f"位置 4 档位 {lay4}（有{Q1}背景不对{Q2}——它是唯一调模型的一格）", fails)
    okf("cutout" not in lay5,
        f"位置 5 档位 {lay5} —— 它不读抠图产物，没有{Q1}重抠{Q2}档", fails)

    # ---- A8 导出闸门
    head("A8 导出闸门 + 清单自证")
    guard_ok = False
    try:
        orchestrator.export_bundle(rd)
    except ValueError as exc:
        guard_ok = True
        R(f"   · 未全采纳时被拒：{str(exc)[:70]}…")
    okf(guard_ok,
        "只采纳了一格时导出被拒（交付的只能是"
        f"{Q1}被采纳的那几版{Q2}）", fails)

    st = orchestrator.mark_accept(rd, 5)          # 补齐另一格
    res = orchestrator.export_bundle(rd)
    man = json.loads(Path(res["manifest"]).read_text(encoding="utf-8"))
    f0 = man["files"][0]
    okf(len(man["files"]) == 2 and f0["slot_id"] == 1,
        f"清单里恰好 2 个文件，第一条是位置 {f0['slot_id']}", fails)
    okf(f0["seq"] == 1 and Path(f0["path"]) == v1,
        f"清单交付的是位置 1 的第 {f0['seq']} 版（{f0['file']}）—— "
        f"不是最新的第 2 版", fails)
    okf(f0["sha256"] == sha(v1), "清单里的 sha256 与文件实算一致（交付物可自证）", fails)
    okf(res["counts"]["accepted"] == 2,
        f"已采纳 {res['counts']['accepted']}/2 才放行导出", fails)

    # ---- A9 / A10 日志容错
    head("A9/A10 日志被并发写坏半行：容错可以，静默不行")
    with (rd / LOG).open("a", encoding="utf-8") as fh:
        fh.write('{"ts": "2026-01-01T00:00:00", "stage": "hal')
    st2 = orchestrator.run_state(rd)
    okf(st2["log_bad_lines"] == 1 and st2["counts"]["done"] == 2,
        f"读模型不炸，并如实报出坏行数 = {st2['log_bad_lines']}"
        f"（审核台会显示它，不让它被 except 吃掉）", fails)
    raised = False
    try:
        orchestrator.read_records(rd)
    except json.JSONDecodeError:
        raised = True
    okf(raised, "不显式要求容错时，坏行必须抛 —— 容错是选择，不是默认吞掉", fails)
    return rd


# ================================================================ B HTTP 契约

def release_cutout_sessions() -> list[str]:
    """放掉本进程缓存住的抠图会话 —— **起服务之前必须做**。

    ★ 为什么这不是"顺手的卫生"，而是验收能不能成立的前提（2026-09-21 实测）：

        本机跑一次 `birefnet-general-lite` 抠图（1024² 输入）实测需要
            约 6 GB 物理内存 / 约 9 GB 可提交内存
        （实测：抠图前 availPhys 6851 MB → 抠图后 889 MB；
                availCommit 17849 MB → 8553 MB）

    A 段要在进程内真跑一次抠图（A2），会话就被 `synth._SESSION_CACHE` 留着，
    约 6 GB 一直占着不还。B 段再起一个**服务子进程**时，子进程要加载自己的
    会话再吃一份 —— 拿不到内存，ORT 会在 decoder 的 Sum 节点直接抛
    `RUNTIME_EXCEPTION`，且重试同样失败（重试没错，是内存真没有）。

    但那不是产品缺陷，是**验收自己制造的条件**：真实用法里命令行跑完进程就退出，
    不会有一个进程揣着 6 GB 会话再去起审核台。实测对照（同机、同输入）：
        父进程留着会话 → 服务子进程 phase=error（3 次推理全失败）
        父进程先放掉会话 → 服务子进程 22.4s 出图，phase=done
    所以这里放掉会话，是让 B 段测的是**接口契约**，而不是 A 段留下的内存债。

    产品侧在这段里的行为全程正确：重试 3 次 → 显式抛 CutoutError → 不静默降级。
    那条行为另有 M6-K 守着（含"重试前必须回收旧会话"的机制断言）。
    """
    import gc

    import synth  # 只在真正要放会话时导入 —— 本脚本的其他部分不需要它

    names = sorted(synth._SESSION_CACHE)
    for name in list(synth._SESSION_CACHE):
        synth._drop_session(name)
    gc.collect()
    return names


def part_b(fails: list[str]) -> None:
    out = SANDBOX / "b"
    # 每次从干净开始：B3 要断言"干跑没在产物根里留下任何东西"。
    # 沙箱是时间戳目录，`b/` 本来就不会存在；这里留着是防"手动放了东西进去"。
    if out.exists():
        try:
            shutil.rmtree(out)          # 删不掉就报出来，不抛
        except Exception as exc:        # noqa: BLE001
            _BUF.append(f"· B 段产物根清理失败（{type(exc).__name__}: {exc}）"
                        f" → 复用现有目录，B3 的断言可能受影响")
    out.mkdir(parents=True, exist_ok=True)
    prod = "examples/product_fullset.json"
    freed = release_cutout_sessions()
    proc, base, log = start_server(out)
    R(f"\nB. HTTP 契约（真服务 {base}，产物根 {out.name}/）")
    R(f"   · 起服务前放掉本进程的抠图会话：{freed or '（本进程没有缓存会话）'}"
      f"  ← 一次抠图实测约需 6 GB 物理 / 9 GB 提交内存，留着会把子进程挤死")
    try:
        # ---- B1 首页
        head("B1 首页就是审核台")
        with urllib.request.urlopen(base + "/", timeout=20) as r:
            html = r.read().decode("utf-8", errors="replace")
        okf(r.status == 200 and "\u5ba1\u6838\u53f0" in html and "/api/table" in html,
            f"GET / → {r.status}，{len(html)} 字节，页面自己去拉 /api/table", fails)

        # ---- B2 坑位表
        head("B2 坑位表与渲染器声明抵达界面；只有位置 4 声明调模型")
        _, t = req(base, "/api/table")
        model_slots = sorted(s["slot_id"] for s in t["slots"] if s["calls_model"])
        okf(len(t["slots"]) == 7, f"坑位 {len(t['slots'])} 个", fails)
        okf(model_slots == [4],
            f"声明调模型的坑位 = {model_slots}（**只有位置 4** —— 界面上那一条"
            f"橙色标记的判据就是这个数，不是写死的 4）", fails)
        okf(set(t["layers"]) == set(orchestrator.LAYERS),
            f"重做档位说明抵达界面：{sorted(t['layers'])}", fails)
        okf(all("renderer_label" in s and "cuts" in s for s in t["slots"]),
            f"每一格的来源标签与{Q1}要提前抠哪样{Q2}都来自渲染器的声明", fails)

        # ---- B3 干跑
        head("B3 干跑接口与 CLI 的 --dry-run 是同一个函数、同一个数")
        _, p = req(base, f"/api/plan?product={urllib.parse.quote(prod)}")
        pl = p["plan"]
        okf(pl["table_total"] == 7 and pl["will_run"] == 7 and pl["model_calls"] == 1,
            f"表内 {pl['table_total']} · 将生成 {pl['will_run']} · 模型调用 {pl['model_calls']}"
            f"（与 M1 起就一直打印的那一行同源）", fails)
        okf(not list(out.glob("*")), "干跑没有在产物根里留下任何东西", fails)

        # ---- B4 商品包
        head("B4 商品包可枚举（投递是目录约定，界面不设上传表单）")
        _, pr = req(base, "/api/products")
        names = [x["path"] for x in pr["products"]]
        okf(prod in names and pr["dirs"] == ["examples"],
            f"投递目录 {pr['dirs']} 下找到 {len(names)} 个包", fails)

        # ---- B5 起一轮 + 并发拒绝
        head("B5 /api/run 同步返回 run_id（= 产物目录名），执行在后台；并发第二次被拒")
        t0 = time.time()
        code, j = req(base, "/api/run", {"product": prod, "only": [1]})
        dt = time.time() - t0
        run_id = str(j.get("run_id") or "")
        okf(code == 200 and run_id.startswith("B0FULLSET01_") and "/" not in run_id
            and dt < 5,
            f"POST /api/run → {code}，run_id={run_id}（{dt:.1f}s 内就返回了，"
            f"没有等抠图与生成）", fails)
        # ★ 这一条验的是刚修掉的一个真实窗口：run_id 返回时 plan.json 还没落盘
        #   （它是后台线程里的 execute 写的）。进度接口必须能回答"正在跑"，
        #   否则界面刚点生成就 404 一下。
        code_s, js = req(base, f"/api/runs/{run_id}/status")
        okf(code_s == 200 and js.get("phase") in ("running", "done"),
            f"刚起步就轮询 → {code_s}（phase={js.get('phase')}）—— "
            f"进度接口在计划落盘前也能回答，不会先 404 一下", fails)
        code2, j2 = req(base, "/api/run", {"product": prod, "only": [1]})
        okf(code2 == 409,
            f"并发第二次 → {code2}：{str(j2.get('error'))[:60]}…", fails)

        # ---- B6 轮询到 done
        head("B6 进度轮询到 done；状态来自 run.jsonl，不是接口层自己记的")
        st = wait_phase(base, run_id)
        okf(st.get("phase") == "done", f"phase={st.get('phase')}（error={st.get('error')}）", fails)
        okf((st.get("state") or {}).get("counts", {}).get("done") == 1,
            "state.counts.done = 1（与进程内读模型是同一份事实）", fails)
        okf(isinstance(st.get("lines"), list) and len(st.get("lines") or []) > 0,
            f"进度行 {len(st.get('lines') or [])} 条（等模型时那段等待是看得见的）", fails)

        # ---- B7 采纳 / 重做 / 导出 走 HTTP
        head("B7 HTTP 采纳 / 重做 / 导出 与进程内是同一套事实")
        # ★ 上游那一轮若失败（典型：抠图在内存紧张时连续推理失败），
        #   这一段就没有可采纳的对象。**必须报出来并跳过，而不是让脚本自己炸掉** ——
        #   脚本崩溃会把 B8/B9 的诊断一起吞掉（第一次跑就是这么丢的：
        #   一个 KeyError 换掉了三段验收的观察）。
        if st.get("phase") != "done" or not st.get("state"):
            okf(False,
                f"上游一轮没跑成（phase={st.get('phase')}，"
                f"error={str(st.get('error'))[:80]}…）→ B7 跳过，B8/B9 继续", fails)
        else:
            code, j = req(base, f"/api/runs/{run_id}/slots/1/accept", {"seq": 1})
            okf(code == 200 and (j.get("state") or {}).get("counts", {}).get("accepted") == 1,
                f"POST accept → {code}，已采纳 "
                f"{(j.get('state') or {}).get('counts', {}).get('accepted')}", fails)

            code, j = req(base, f"/api/runs/{run_id}/slots/1/redo", {"layer": "placement"})
            okf(code == 200, f"POST redo → {code}", fails)
            st2 = wait_phase(base, run_id)
            slots = (st2.get("state") or {}).get("slots") or []
            s1 = next((s for s in slots if s.get("slot_id") == 1), None)
            okf(s1 is not None and st2.get("phase") == "done"
                and [v["seq"] for v in s1["versions"]] == [1, 2] and not s1["accepted"],
                f"重做完成：版本 "
                f"{[v['seq'] for v in s1['versions']] if s1 else '（无该格）'}、"
                f"accepted={s1['accepted'] if s1 else None}（上一次采纳作废）", fails)

            code, j = req(base, f"/api/runs/{run_id}/export", {})
            okf(code == 409, f"未全采纳时导出 → {code}：{str(j.get('error'))[:50]}…", fails)
            req(base, f"/api/runs/{run_id}/slots/1/accept", {"seq": 2})
            code, j = req(base, f"/api/runs/{run_id}/export", {})
            okf(code == 200 and Path(str(j.get("manifest"))).exists(),
                f"全部采纳后导出 → {code}，清单 {Path(str(j.get('manifest'))).name}", fails)

        # ---- B8 边界
        head("B8 边界：只允许读项目目录内的文件")
        code, _ = req(base, "/api/file?path=" + urllib.parse.quote("C:/Windows/win.ini"))
        okf(code == 403, f"项目目录外的绝对路径 → {code}", fails)
        code, _ = req(base, "/api/file?path=" + urllib.parse.quote("../../../../etc/passwd"))
        okf(code in (403, 404), f"../ 穿越 → {code}", fails)
        jpg = next((out / run_id).glob("*.jpg"), None)
        if jpg is None:
            # ★ 上游没出图时这一条**报不出有效结论**：`str(None)` 会被当成一个
            #   不存在的路径去请求，返回 404 —— 看起来像"路径守卫把项目内的文件
            #   也挡了"，实际只是没有产物可读。原因要报准确的，不能张冠李戴。
            print(f"   {BAD} 上游一轮没出图 → 没有产物图可读，这一段验不了")
            fails.append("B8 无法验证项目内文件可读：上游一轮没产出任何图"
                         "（原因见上面 B6，不要读成路径守卫坏了）")
        else:
            code, blob = req_raw(base, "/api/file?path=" + urllib.parse.quote(str(jpg)))
            okf(code == 200 and blob[:2] == b"\xff\xd8",
                f"项目目录内的产物图 → {code}，{len(blob)} 字节，JPEG 头正确"
                f"（界面上的 <img> 拿到的就是它）", fails)

        # ---- B9 用法错误
        head("B9 参数与用法错误有明确返回码，不静默跑")
        code, _ = req(base, "/api/runs/NO_SUCH_RUN/status")
        okf(code == 404, f"不存在的 run → {code}", fails)
        code, j = req(base, f"/api/runs/{run_id}/slots/1/redo", {"layer": "nope"})
        okf(code == 400, f"非法 layer → {code}：{str(j.get('error'))[:40]}…", fails)
        code, j = req(base, "/api/run", {"product": prod, "only": []})
        okf(code == 400,
            f"only=[] → {code}（空列表会被当成{Q1}全部{Q2}，所以显式拒绝，不猜）", fails)
        code, _ = req(base, "/api/plan?product=" + urllib.parse.quote("README.md"))
        okf(code == 403, f"投递目录之外的包 → {code}", fails)
        _, j = req(base, f"/api/runs/{run_id}/log?tail=50")
        okf(isinstance(j.get("lines"), list) and j["lines"],
            f"日志原文可读：{len(j['lines'])} 行，坏行单独列（{len(j.get('bad_lines') or [])} 条）", fails)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


# ================================================================ main

def reset_sandbox() -> None:
    """建起这一轮的隔离产物根。**不删任何旧目录** —— 理由见 SANDBOX 上方注释。"""
    SANDBOX.mkdir(parents=True, exist_ok=True)


def main() -> int:
    # --part=a|b|a,b ：迭代时只跑一段。A 要跑两次真抠图（一次约 20s），
    # 改的明明是接口层却被迫重跑 A，是没有意义的等待。
    raw = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--part=")), "a,b")
    want = {p.strip().lower() for p in raw.split(",") if p.strip()}
    if not want <= {"a", "b"}:
        R(f"--part 只认 a/b/a,b，收到 {raw!r}")
        return 2

    reset_sandbox()
    registry.load_all()

    R(f"M7 验收 · 界面接线（part={','.join(sorted(want))}）\n" + "=" * 72)
    R(f"· 隔离产物根：{SANDBOX.relative_to(ROOT)}（每跑新开一个，不删旧的）")
    fails: list[str] = []
    try:
        if "a" in want:
            part_a(fails)
        if "b" in want:
            part_b(fails)
    except Exception as exc:                     # noqa: BLE001
        import traceback
        _BUF.append(traceback.format_exc())
        traceback.print_exc()
        fails.append(f"脚本自己炸了：{type(exc).__name__}: {exc}")

    R("\n" + "=" * 72)
    if fails:
        R(f"未通过 {len(fails)} 条：")
        for f in fails:
            R(f"  {BAD} {f}")
        code = 1
    else:
        R("全部通过。M7 的验收点是四条：")
        R(f"  · 界面上的每个数都来自接口（张数/跳过/成本/版本/采纳），没有第二份真相源；")
        R(f"  · 只有位置 4 是模型格 —— 它是{Q1}橙色那条独自走满全程{Q2}的数据级判据；")
        R(f"  · 采纳与重做写进 run.jsonl，旧版永不覆盖，交付的是被采纳的那一版；")
        R(f"  · 只读项目目录内的文件，参数错误有明确返回码。")
        code = 0

    # 清理排在**结论之后**（2026-09-22 修正）。
    #
    # 原来它排在结论之前，于是有一类失败被制造出来：本机的批量删除有闸（删早先轮次
    # 留下的内容、数量过线要显式确认，拦下即 fail-closed），而一轮沙箱约 15 个文件、
    # 断言引用的又是别处的产物 —— 结果是**删不掉沙箱 = 验收失败**。
    # 同一天同代码 13:5x 绿、14:14 红，报出来的却是"未通过"，查了半天才发现画面根本没变。
    # 一个会因为自己收尾而变红的验收，比没有验收更坏：人会习惯它的红。
    #
    # 所以：默认**不删**（沙箱本来就不需要被删，见 SANDBOX 上方），要删得显式 --clean，
    # 且无论如何不影响退出码。
    if CLEAN:
        try:
            shutil.rmtree(SANDBOX)
        except Exception as exc:                 # noqa: BLE001  ← fail-closed 的退出也要接住
            R(f"· 沙箱没清掉（{type(exc).__name__}: {exc}）→ 留在 "
              f"{SANDBOX.relative_to(ROOT)}/  —— 不影响上面的结论")
    else:
        R(f"· 沙箱保留在 {SANDBOX.relative_to(ROOT)}/（默认不删；"
          f"要清就加 --clean，或直接删这个目录 —— 删不掉也不影响结论）")

    try:
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text("\n".join(_BUF) + "\n", encoding="utf-8")
    except OSError as exc:
        # 报告写不成不影响判定（判定在上面已经算完 code 了），但不能悄悄吞 ——
        # 这台机器的写入/删除限制踩过太多次，静默失败会变成"报告怎么没了"。
        print(f"\u00b7 报告没写成（{type(exc).__name__}: {exc}）→ 结论以 stdout 为准")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
