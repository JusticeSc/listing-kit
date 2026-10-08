r"""M6 验收断言 —— 重做是「重放一条」，且**新增版本不覆盖**。

用法：
    python tools/verify_m6.py [run 目录] [product.json]

    # 默认：out/ 下最近一次「可重做」的 run + examples/product_fullset.json
    python tools/verify_m6.py

它断言的不是「又出了一张图」，而是几条**结构性质**：

    A. 重做**新增**版本，而不是覆盖 —— 旧产物逐字节不变；
       `run.jsonl` 是**追加**的（旧内容原样是新内容的前缀）
    B. `layer=text`（位置 2）< 1s、**零模型**、复用上一轮 `raw/slot02_bg.jpg`，
       且报告里不出现任何抠图字段（这条路根本不碰像素合成）
    C. 主体同源：`subject.png` 前后 sha 不变，重做记录里的 subject_sha256 等于它
    D. 版本号递增、文件名可由 export.filename_pattern 推导
    E. 重做不新建 run 目录，也不新建子目录
    F. 同输入 + 同底 → **逐字节相同**。抓的是"文字层里藏了状态"
    G. 参数不可用时报错而不是静默跑，且**不留下**半条日志
    H. CLI 接线：`--redo` 在不可用时返回 4（argparse 拦的用法错误返回 2）
    I. `layer=cutout`：主体**与素材**一起重抠、**所有用到抠图产物的坑位**
       各重出一版、用到它们的坑位之外**一个都没动**、
       且位置 4 **没有**新增模型调用（复用生成底）
    J. `layer=placement`（位置 4）：也只重落点、**不调模型**（复用生成底）
       —— 这是「位置或大小不对 = 免费」这句话的实现
    K. 抠图**推理**失败：先重试（且换一个会话重试），仍失败就报错 ——
       绝不静默降级换路。降级换的是像素，那会让「重做可重放」不成立。

退出码：0 全过 / 1 有断言失败 / 2 用法或数据问题

副作用：本脚本会**真的重做**若干次（每次新增版本到被测 run 目录里）。
        这正是被验的性质本身 —— 不真跑就没法证明「不覆盖」「版本号递增」
        「重抠主体不影响无关坑位」。
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402  （控制台编码归一：见 src/console.py）
enable_utf8()

import orchestrator  # noqa: E402
import registry  # noqa: E402
import schema  # noqa: E402

PY = sys.executable
TARGET = 2                      # 文字层用例：改一句文案
GEN_SLOT = 4                    # 生成底用例：位置 4
LOG = "run.jsonl"               # 追加型日志：不参与「逐字节不变」，单独按前缀验
OK, BAD = "\u2713", "\u2717"


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def snapshot(run_dir: Path) -> dict[str, str]:
    """目录里所有**产物**的指纹（含 raw/ 与 subject.png），不含追加型日志。"""
    return {str(p.relative_to(run_dir)).replace("\\", "/"): sha(p)
            for p in sorted(run_dir.rglob("*"))
            if p.is_file() and p.name != LOG}


def top_dirs(run_dir: Path) -> set[str]:
    return {p.name for p in run_dir.iterdir() if p.is_dir()}


def find_run(argv: list[str]) -> Path | None:
    if len(argv) > 1:
        return Path(argv[1])
    cands = [p for p in (ROOT / "out").glob("*")
             if (p / "plan.json").exists() and (p / "raw" / "slot02_bg.jpg").exists()]
    return max(cands, key=lambda p: p.name) if cands else None


def load_product(argv: list[str]) -> tuple[dict, Path, Path]:
    """重做读的是**当次输入**，而不是上一轮的输出。

    plan.json 里刻意**没有**记 product 文件路径：那条信息只服务于重做，
    而重做所需的路径由调用方给出更诚实。所以默认取满素材样例。
    """
    pf = Path(argv[2]) if len(argv) > 2 else ROOT / "examples" / "product_fullset.json"
    if not pf.exists():
        raise RuntimeError(f"商品输入文件不存在：{pf}")
    return json.loads(pf.read_text(encoding="utf-8")), pf.parent, pf


def recs(run_dir: Path) -> list[dict]:
    # 容错读：与 m3/m4/m5 同一口径，也与产品自身一致 —— 日志是唯一状态源，
    # 读它的方式只该有一种。半行日志（被中断的那次 run）不该炸掉整次验收。
    return orchestrator.read_records(run_dir, tolerant=True)


def upto(run_dir: Path, n: int) -> dict[str, str]:
    """只取名字里版本号 <= n 的位置 2 产物（用于比较"旧版本有没有被动过"）。"""
    return {k: v for k, v in snapshot(run_dir).items()
            if f"_{TARGET:02d}_" not in k}


def assert_a(run_dir: Path, before: dict, before_log: bytes, rep: dict,
             fails: list[str]) -> None:
    print("A. 重做新增版本，旧产物一个字节都没动")
    after = snapshot(run_dir)
    added = sorted(set(after) - set(before))
    changed = sorted(k for k in before if after.get(k) != before[k])
    want = sorted(str(Path(r["path"]).relative_to(run_dir)).replace("\\", "/")
                  for r in rep["results"])
    log_now = (run_dir / LOG).read_bytes()
    appended = log_now[:len(before_log)] == before_log and len(log_now) > len(before_log)
    print(f"   新增：{added}")
    print(f"   被改动的旧产物：{changed or '（无）'}")
    print(f"   {LOG}：{len(before_log)} → {len(log_now)} 字节，旧内容原样保留="
          f"{log_now[:len(before_log)] == before_log}")
    ok = added == want and not changed and appended
    print(f"   {OK if ok else BAD} 恰好新增 {len(want)} 个，旧产物零改动，日志纯追加")
    if not ok:
        fails.append(f"重做动到了既有产物或新增数量不对：新增 {added}（期望 {want}）、"
                     f"改动 {changed}、日志纯追加={appended} —— "
                     f"「不覆盖」是保护归因数据的底线")


def assert_b(run_dir: Path, rep: dict, fails: list[str]) -> None:
    print("\nB. layer=text（位置 2）：秒级、零模型、复用上一轮的底、不碰抠图")
    r = rep["results"][0]
    rd = next((x for x in reversed(recs(run_dir))
               if x["stage"] == "redo" and x["slot_id"] == TARGET
               and x.get("seq") == r["seq"]), {})
    detail = rd.get("detail") or {}
    reused = str(detail.get("reused_bg") or "")
    used_raw = reused.replace("\\", "/").endswith("raw/slot02_bg.jpg")
    model = registry.calls_model(r["renderer"])
    cut_keys = [k for k in detail if "cutout" in k]
    ok = used_raw and not model and r["elapsed_s"] < 1.0 and not cut_keys
    print(f"   渲染器 {r['renderer']}   耗时 {r['elapsed_s']}s   声明调模型={model}")
    print(f"   复用底 {reused or '（未记录）'}")
    print(f"   报告里的抠图字段 {cut_keys or '（无）'}")
    print(f"   {OK if ok else BAD} 秒级 + 零模型 + 复用上一轮文字底 + 不抠图")
    if not ok:
        fails.append(f"文字层重做没走「轻」路径：耗时 {r['elapsed_s']}s、"
                     f"calls_model={model}、复用底={used_raw}、抠图字段={cut_keys}")


def assert_c(run_dir: Path, subject_before: str, rep: dict, fails: list[str]) -> None:
    print("\nC. 主体同源：重做一格不重抠整批的主体")
    now = sha(run_dir / "subject.png")
    got = (rep.get("subject") or {}).get("sha256")
    ok = now == subject_before == got and not (rep.get("subject") or {}).get("changed")
    print(f"   subject.png {now[:12]}…   重做记录 {str(got)[:12]}…   "
          f"changed={ (rep.get('subject') or {}).get('changed')}")
    print(f"   {OK if ok else BAD} 重做前后主体未变，且重做时读的就是这一份（不变量 A）")
    if not ok:
        fails.append("重做期间主体被重抠了 —— 位置 2 的轮廓会和其余六张不一致")


def assert_d(run_dir: Path, rep: dict, upc: str, seq_before: int,
             fails: list[str]) -> None:
    print("\nD. 版本号递增，文件名可由 export 配置推导")
    cfg = schema.assert_valid()
    slot = next(s for s in cfg["slots"] if s["id"] == TARGET)
    r = rep["results"][0]
    want = cfg["export"]["filename_pattern"].format(
        upc=upc, slot=f"{TARGET:02d}_{slot.get('role', 'slot')}", seq=r["seq"]) + ".jpg"
    got = Path(r["path"]).name
    ok = r["seq"] == seq_before + 1 and got == want
    print(f"   重做前已有 {seq_before} 版 → 本次 seq={r['seq']}")
    print(f"   期望 {want}   实际 {got}")
    print(f"   {OK if ok else BAD} seq 递增 1 且文件名可推导")
    if not ok:
        fails.append(f"版本号或文件名不对：seq {seq_before}→{r['seq']}，{got} != {want}")


def assert_e(run_dir: Path, before_dirs: set[str], rep: dict, fails: list[str]) -> None:
    print("\nE. 重做不新建 run 目录")
    ok = (Path(rep["run_dir"]).resolve() == run_dir.resolve()
          and top_dirs(run_dir) == before_dirs)
    print(f"   写入 {rep['run_dir']}")
    print(f"   子目录 {sorted(before_dirs)}（未变）")
    print(f"   {OK if ok else BAD} 新版本落在上一轮目录里，紧挨着被对比的那一版")
    if not ok:
        fails.append("重做把结果写到了别处，或新建了目录 —— 版本没法就地对比就失去意义")


def assert_f(ref: Path | None, new_path: Path, fails: list[str]) -> None:
    """同输入 + 同底 → 逐字节相同。

    这条抓的是「文字层里藏了状态」：时间戳、随机抖动、上一次的残留。
    它比「图看着没问题」重要得多，因为版本对比的前提就是
    「差异只来自我改的那一处」。
    """
    print("\nF. 同输入 + 同底 → 逐字节相同（文字层必须无隐藏状态）")
    ok = bool(ref) and ref.exists() and sha(ref) == sha(new_path)
    print(f"   {ref.name if ref else '（无对照）'}  vs  {new_path.name}")
    print(f"   {OK if ok else BAD} 两次产出逐字节相同")
    if not ok:
        fails.append("同一输入同一底产出的字节不同 —— 文字层里有非确定性状态，"
                     "版本对比会被噪声污染")


def assert_g(run_dir: Path, product: dict, base: Path, log_before: bytes,
             fails: list[str]) -> None:
    print("\nG. 参数不可用时报错，而不是静默跑，且不留半条日志")
    cases = [
        ("位置 1 的 text=none，没有文字层可重排",
         dict(slot_id=1, layer="text")),
        ("layer 拼错", dict(slot_id=TARGET, layer="backdrop")),
        ("重做一个这一轮被跳过的坑位",
         dict(slot_id=99, layer="text")),
    ]
    for why, kw in cases:
        try:
            orchestrator.redo(run_dir, product, base_dir=base, **kw)
            print(f"   {BAD} {why} —— 居然没报错")
            fails.append(f"该报错却没报：{why}")
            continue
        except ValueError as exc:
            print(f"   {OK} {why}\n       → {str(exc)[:96]}")
        except Exception as exc:                      # noqa: BLE001
            print(f"   {BAD} {why} —— 抛的不是 ValueError 而是 "
                  f"{type(exc).__name__}: {exc}")
            fails.append(f"{why}：应以 ValueError 报错，实际 {type(exc).__name__}")
            continue
    logged = len((run_dir / LOG).read_bytes()) > len(log_before)
    print(f"   {OK if not logged else BAD} 被拒绝的重做没有写日志")
    if logged:
        fails.append("被拒绝的重做往 run.jsonl 里写了记录 —— "
                     "事后无法区分'被拒绝'与'跑到一半崩掉'")

    with tempfile.TemporaryDirectory() as td:
        try:
            orchestrator.redo(Path(td), product, TARGET, layer="text", base_dir=base)
            print(f"   {BAD} 目录里没有 plan.json —— 居然没报错")
            fails.append("对没有 plan.json 的目录重做居然没报错")
        except ValueError as exc:
            print(f"   {OK} 目录里没有 plan.json\n       → {str(exc)[:96]}")


def assert_h(product_file: Path, fails: list[str]) -> None:
    print("\nH. CLI 接线：不可用时返回 4（argparse 拦的用法错误返回 2）")
    with tempfile.TemporaryDirectory() as td:
        bogus = Path(td) / "p.json"
        bogus.write_text(json.dumps({"upc": "NOPE0001", "assets": {}}),
                         encoding="utf-8")
        runs = [
            ("找不到上一轮", 4, ["--product", str(bogus), "--out", str(ROOT / "out"),
                                 "--redo", "2"]),
            ("--redo 与 --dry-run 同时用", 4,
             ["--product", str(product_file), "--redo", "2", "--dry-run"]),
            ("--layer 拼错", 2,
             ["--product", str(product_file), "--redo", "2", "--layer", "backdrop"]),
        ]
        for why, want, args in runs:
            p = subprocess.run([PY, str(ROOT / "run.py"), *args],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", cwd=str(ROOT))
            ok = p.returncode == want
            lines = [ln for ln in (p.stdout or "").splitlines() if ln.strip()]
            print(f"   {OK if ok else BAD} {why} → 返回码 {p.returncode}（期望 {want}）"
                  + (f"\n       {lines[-1][:88]}" if lines else ""))
            if not ok:
                fails.append(f"{why}：期望返回码 {want}，实际 {p.returncode} "
                             f"（stderr={p.stderr[:200]}）")


def assert_i(run_dir: Path, product: dict, base: Path, fails: list[str]) -> None:
    """layer=cutout：重抠主体**与素材** → 用到它们的坑位一起重出，其余一个都不动。"""
    print("\nI. layer=cutout：主体与素材一起重抠，用到它们的坑位一起重出")
    doable = next((r.get("doable") for r in recs(run_dir)
                   if r["stage"] == "run_start"), []) or []
    cfg = schema.assert_valid()
    by_id = {s["id"]: s for s in cfg["slots"]}
    # 「用到抠图产物」= needs 里有 front（主体），或渲染器声明了 cuts（内容物/竞品）。
    # 这条判据刻意与 orchestrator.redo 里那一段同构 —— 对同一件事有两种说法，
    # 就是两个真相源的开始。
    cut_kinds = {k for i in doable if i in by_id
                 for k in registry.cuts_of(by_id[i]["renderer"])}
    reads = {"front", *cut_kinds}
    want = sorted(i for i in doable
                  if i in by_id and reads & set(by_id[i].get("needs") or []))
    if not want:
        print("   · 这一轮没有坑位用到抠图产物，跳过")
        return

    before = snapshot(run_dir)
    subj_before = sha(run_dir / "subject.png")
    try:
        rep = orchestrator.redo(run_dir, product, 1, layer="cutout", base_dir=base)
    except ValueError as exc:
        print(f"   {BAD} 重抠失败：{str(exc)[:160]}")
        fails.append(f"layer=cutout 重做失败：{str(exc)[:160]}")
        return
    after = snapshot(run_dir)

    got = sorted(r["slot_id"] for r in rep["results"])
    print(f"   用到抠图产物的坑位（front + 渲染器声明的 {sorted(cut_kinds)}）"
          f"{want} → 重出 {got}")
    ok_targets = got == want
    print(f"   {OK if ok_targets else BAD} 受影响集合由**表里的 needs 与渲染器声明的 "
          f"cuts** 决定，不是坑位号")
    if not ok_targets:
        fails.append(f"cutout 影响的坑位不对：重出 {got}，期望 {want}")

    # 用到抠图产物的坑位之外，一个产物都不该变。
    # cutout 档本来就必须重写三类“当前控制产物”：全组 subject、声明要重抠的
    # 素材，以及受影响槽位的 raw 底图；它们不是旧版本成品，不能算越界改动。
    # 旧探针只放行新增的成品文件，因 floodfill 同输入通常逐字节相同而长期假绿；
    # 真正启用 rembg 后这些控制产物合理变化，才把假判据暴露出来。
    touched = {k for k in before if after.get(k) != before[k]}
    allowed_control = {
        "subject.png",
        *(f"raw/cut_{kind}.png" for kind in cut_kinds),
        *(f"raw/slot{i:02d}_bg.jpg" for i in want),
    }
    expected_touched = sorted(touched & allowed_control)
    stray = sorted(touched - allowed_control)
    print(f"   合法更新的控制产物：{expected_touched or '（逐字节相同）'}")
    print(f"   被改动的无关或旧版产物：{stray or '（无）'}")
    if stray:
        fails.append(f"cutout 动到了无关产物：{stray}")

    subj_now = sha(run_dir / "subject.png")
    changed = (rep.get("subject") or {})
    print(f"   subject.png {subj_before[:12]}… → {subj_now[:12]}…   "
          f"记录 changed={changed.get('changed')}  "
          f"抠法={changed.get('cutout_mode')}  耗时 {changed.get('elapsed_s')}s")
    if subj_now != (rep.get("subject") or {}).get("sha256"):
        fails.append("cutout 后 subject.png 与记录里的 sha 不一致")

    # 素材也要重抠，且重抠的结论要能被读到（这是"这一版用的是哪一份抠图"的凭证）
    for kind, info in (rep.get("cutouts") or {}).items():
        cp = Path(str(info.get("path") or ""))
        ok = cp.exists() and bool(info.get("recomputed")) and \
            info.get("sha256") == sha(cp)
        print(f"   素材 {kind:<11}{cp.name}  重抠={info.get('recomputed')}  "
              f"sha={str(info.get('sha256'))[:12]}…")
        if not ok:
            fails.append(f"cutout 档没有真正重抠素材 {kind}（或 sha 与文件不符）")

    # 位置 4 在 cutout 里必须复用生成底 → 不新增模型调用
    g = next((r for r in rep["results"] if r["slot_id"] == GEN_SLOT), None)
    if g:
        reuse = g.get("reused_bg")
        print(f"   位置 4 复用底 {reuse}")
        print(f"   {OK if reuse else BAD} 主体换了但背景不重生成 —— 不花第二次调用")
        if not reuse:
            fails.append("cutout 重出位置 4 时没有复用生成底，白花了一次模型调用")
    print(f"   本次模型调用 {rep['model_calls']} 次")
    if rep["model_calls"] != 0:
        fails.append(f"cutout 本次发生 {rep['model_calls']} 次模型调用，期望 0")


def assert_j(run_dir: Path, product: dict, base: Path, fails: list[str]) -> None:
    """layer=placement（位置 4）：只动落点，不调模型。"""
    print("\nJ. layer=placement（位置 4）：只动落点、不调模型（复用生成底）")
    doable = next((r.get("doable") for r in recs(run_dir)
                   if r["stage"] == "run_start"), []) or []
    if GEN_SLOT not in doable:
        print("   · 这一轮没做位置 4，跳过")
        return
    if not (run_dir / "raw" / f"slot{GEN_SLOT:02d}_gen.jpg").exists():
        print("   · 没有生成底（这一轮位置 4 是占位图），跳过")
        return
    try:
        rep = orchestrator.redo(run_dir, product, GEN_SLOT, layer="placement",
                                base_dir=base)
    except ValueError as exc:
        print(f"   {BAD} 重做被拒：{str(exc)[:160]}")
        fails.append(f"位置 4 的 placement 重做被拒：{str(exc)[:160]}")
        return
    r = rep["results"][0]
    ok = bool(r.get("reused_bg")) and rep["model_calls"] == 0 and r["elapsed_s"] < 3.0
    print(f"   位置 {GEN_SLOT} 第 {r['seq']} 版  {r['elapsed_s']}s  "
          f"复用底 {r.get('reused_bg')}")
    print(f"   本次模型调用 {rep['model_calls']} 次")
    print(f"   {OK if ok else BAD} 「位置或大小不对 = 免费」这句话是事实，不是文案")
    if not ok:
        fails.append(f"位置 4 的 placement 重做花了钱或超时："
                     f"复用底={r.get('reused_bg')}、调用 {rep['model_calls']} 次、"
                     f"{r['elapsed_s']}s")


def assert_k(fails: list[str]) -> None:
    """抠图**推理**失败：先重试，仍失败就报错 —— 绝不静默换路降级。

    这条守的是"重做可以重放"的前提。M6 第一次跑时红在这里：
    位置 7 重做时一次 `bad allocation` 被静默降级成 floodfill，
    成品与上一版相差 184221 个像素，而日志里没有任何状态变化 ——
    floodfill 与 rembg 抠出的 alpha 不是同一个东西，换路就是换像素。

    做法是把 `rembg.remove` 换成可控的假实现（真失败由内存压力触发，
    没法在测试里稳定复现）：
        第 1 次抛错、第 2 次成功  → 应返回 rembg 结果，并留痕 infer_retried
        每次都抛错              → 应抛 CutoutError，且**不产出**任何抠图结果
    """
    print("\nK. 抠图推理失败：重试，仍失败则报错（不静默换路降级）")
    import rembg  # type: ignore

    from PIL import Image as _Image

    import synth
    import subject as subject_mod

    src = ROOT / "examples" / "input" / "cup_source.jpg"
    if not src.exists():
        print("   · 缺 cup_source.jpg，跳过")
        return
    img = _Image.open(src)
    orig = rembg.remove

    # ---- 1) 第一次炸、第二次成功
    state = {"n": 0}

    def flaky(image, session=None, **kw):
        state["n"] += 1
        if state["n"] == 1:
            raise RuntimeError("[ONNXRuntimeError] : 1 : FAIL : bad allocation")
        return orig(image, session=session, **kw)

    try:
        rembg.remove = flaky
        # 先把会话建起来（flaky 只管推理，不管建会话）
        _rgba, meta = synth.remove_background(img)
    except Exception as exc:                       # noqa: BLE001
        print(f"   {BAD} 重试没救回来：{type(exc).__name__}: {str(exc)[:110]}")
        fails.append(f"抠图推理偶发失败时没有重试成功：{type(exc).__name__}")
    else:
        ok = meta.get("mode") == "rembg" and state["n"] == 2 \
            and bool(meta.get("infer_retried"))
        print(f"   第 1 次抛错 → 第 2 次成功：mode={meta.get('mode')} "
              f"推理次数={state['n']} 留痕={bool(meta.get('infer_retried'))}")
        print(f"   {OK if ok else BAD} 偶发失败被重试吸收，并在报告里留了痕")
        if not ok:
            fails.append(f"重试路径不对：mode={meta.get('mode')}、"
                         f"次数={state['n']}、留痕={bool(meta.get('infer_retried'))}")

    # ---- 1.5) 机制层：重试**必须先回收旧会话**，否则峰值内存翻倍
    #
    # 这条不是"顺手的卫生检查"。2026-09-21 复跑 M6 时，注入一次偶发失败后
    # 重试**连续失败**，日志写着"连续失败 3 次"，看起来像运气不好 ——
    # 实际是自己制造的：旧会话在新建那一刻仍然活着（它被 `exc.__traceback__`
    # → 栈帧链里的局部/形参钉住），在"已经拿不到内存"的场景下峰值翻倍就是必输。
    #
    # 判据（行为之外还要看机制）：`_load_session()` 被调用的那一刻，
    # 上一个会话对象必须**已经被回收**。改前观察值为 True，改后必须为 False。
    import gc as _gc  # noqa: F401  （gc 由 synth 内部调用，这里只为对齐 import 习惯）
    import weakref as _weakref

    fresh = {"n": 0}

    def flaky2(image, session=None, **kw):
        fresh["n"] += 1
        if fresh["n"] == 1:
            raise RuntimeError("[ONNXRuntimeError] : 1 : FAIL : bad allocation")
        return orig(image, session=session, **kw)

    seen: list = []          # 每次 _load_session 返回值的弱引用（弱 ⇒ 不污染测量）
    alive_at: list = []

    orig_load = synth._load_session

    def spy_load():
        if seen:             # 第 2 次调用起：上一个会话还在内存里吗
            alive_at.append(seen[-1]() is not None)
        s, i = orig_load()
        seen.append(_weakref.ref(s) if s is not None else (lambda: None))
        return s, i

    try:
        rembg.remove = flaky2
        synth._load_session = spy_load
        synth.remove_background(img)
    except Exception as exc:                       # noqa: BLE001
        print(f"   {BAD} 机制探针这一轮自己没跑通：{type(exc).__name__}: {str(exc)[:90]}")
        fails.append(f"M6-K 机制探针未跑通：{type(exc).__name__}")
    finally:
        synth._load_session = orig_load
        rembg.remove = orig

    ok = fresh["n"] == 2 and alive_at == [False]
    print(f"   重试时新建会话 ⇒ 旧会话是否仍在内存里：{alive_at}（期望 [False]）")
    print(f"   {OK if ok else BAD} 重试前旧会话已回收（新旧 arena 不并存）")
    if not ok:
        fails.append(
            f"重试没有先回收旧会话：新建那一刻旧会话仍活着 = {alive_at}"
            f" —— 内存不足时峰值翻倍，重试必然继续失败"
            f"（见 synth.remove_background 的 `exc.__traceback__ = None`）")

    # ---- 2) 每次都炸 → 必须抛 CutoutError，而不是悄悄给一张 floodfill 的图
    def always_fail(image, session=None, **kw):
        raise RuntimeError("[ONNXRuntimeError] : 1 : FAIL : bad allocation")

    try:
        rembg.remove = always_fail
        with tempfile.TemporaryDirectory() as td:
            try:
                info = subject_mod.prepare(src, Path(td))
            except subject_mod.SubjectError as exc:
                produced = (Path(td) / "subject.png").exists()
                print(f"   连续失败 → SubjectError（{str(exc)[:80]}…）")
                print(f"   {OK if not produced else BAD} 报错且**没有**产出 subject.png "
                      f"（没有拿一张降级图冒充主体）")
                if produced:
                    fails.append("抠图失败却仍产出了 subject.png —— 那是降级的像素，"
                                 "不是主体该有的抠图结果")
            except Exception as exc:               # noqa: BLE001
                print(f"   {BAD} 抛的不是 SubjectError 而是 "
                      f"{type(exc).__name__}: {str(exc)[:110]}")
                fails.append(f"抠图连续失败时抛了 {type(exc).__name__}，"
                             f"CLI 无法把它变成一句人话")
            else:
                print(f"   {BAD} 抠图连续失败居然成功了：mode="
                      f"{(info.get('cutout') or {}).get('mode')}")
                fails.append("抠图连续失败却静默降级并产出了主体 —— "
                             "重做将不再可重放（同输入不同像素）")
    finally:
        rembg.remove = orig


def main(argv: list[str]) -> int:
    run_dir = find_run(argv)
    if not run_dir or not (run_dir / "plan.json").exists():
        print("找不到可重做的 run（需要 plan.json 与 raw/slot02_bg.jpg）：先跑一次\n"
              "  python run.py --product examples/product_fullset.json")
        return 2
    if not (run_dir / "subject.png").exists():
        print(f"{run_dir} 里没有 subject.png —— 它没有可复用的主体，不能当重做基线")
        return 2

    registry.load_all()
    product, base, product_file = load_product(argv)
    upc = product.get("upc") or "NOUPC"

    print(f"M6 验收 · {run_dir.name}\n" + "=" * 72)
    fails: list[str] = []

    before = snapshot(run_dir)
    before_dirs = top_dirs(run_dir)
    before_log = (run_dir / LOG).read_bytes()
    subject_before = sha(run_dir / "subject.png")
    existing = sorted(run_dir.glob(f"{upc}_{TARGET:02d}_*.jpg"))
    seq_before = len(existing)
    ref = existing[-1] if existing else None      # 对照组：重做前最后一版

    # ---- 主用例：text 层
    rep = orchestrator.redo(run_dir, product, TARGET, layer="text", base_dir=base,
                            progress=lambda s: print(f"   · {s}"))
    assert_a(run_dir, before, before_log, rep, fails)
    assert_b(run_dir, rep, fails)
    assert_c(run_dir, subject_before, rep, fails)
    assert_d(run_dir, rep, upc, seq_before, fails)
    assert_e(run_dir, before_dirs, rep, fails)
    assert_f(ref, Path(rep["results"][0]["path"]), fails)

    # ---- 再重做一次：证明 seq 是**推出来的**，不是写死的
    rep2 = orchestrator.redo(run_dir, product, TARGET, layer="text", base_dir=base)
    r2 = rep2["results"][0]
    print(f"\n· 连续第二次重做 → seq={r2['seq']}  {Path(r2['path']).name}  "
          f"{r2['elapsed_s']}s")
    if r2["seq"] == rep["results"][0]["seq"] + 1 and \
            Path(r2["path"]) != Path(rep["results"][0]["path"]):
        print(f"   {OK} 版本号继续递增，且是新文件")
    else:
        fails.append("连续重做的版本号没有继续递增，或写回了同一路径")
        print(f"   {BAD} 版本号未递增或发生了覆盖")

    assert_g(run_dir, product, base, (run_dir / LOG).read_bytes(), fails)
    assert_h(product_file, fails)
    assert_i(run_dir, product, base, fails)
    assert_j(run_dir, product, base, fails)
    assert_k(fails)

    print("\n" + "=" * 72)
    if fails:
        print(f"未通过 {len(fails)} 条：")
        for f in fails:
            print(f"  {BAD} {f}")
        return 1
    print("全部通过：重做只是「重放一条」；文字层是秒级零模型；重抠主体会按表里的 "
          "needs 波及所有读主体的坑位、且不重生成背景；新版本落在同一目录，"
          "旧版本一个字节都没动。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
