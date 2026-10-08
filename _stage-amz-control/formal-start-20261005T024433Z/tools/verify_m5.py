r"""M5 验收断言 —— 可复现，不靠目测。

用法：
    python tools/verify_m5.py                       # 取 out/ 下最近一次 run
    python tools/verify_m5.py out/B0FULLSET01_...   # 指定某次 run

它断言的不是「三张图出来了」，而是几条**结构性质**：

    A. 齐套可做的每一格**都有下文**：要么出了图，要么有一条跳过记录 ——
       而且每条跳过记录都带**机器可读的成因**。不许有格子无声消失。
    B. 位置 5/6 的像素**不是**来自 subject.png，而各自来自 closeup / contents 原片
       —— 它们画的是另外两件东西，混进来就是「拿别的图凑」
    C. 位置 7 **同时**用了主体与竞品：它的 subject_sha256 与位置 1 完全一致
       —— 不变量 A（主体只有一份）在这一格也成立；且竞品块指回抠图产物
    D. 位置 5/6/7 **零模型**、**零抠图**、秒级 —— 抠图已经不在渲染器里了
    E. 位置 5 是「裁切填满」而不是「缩小留白」：裁切框恰好等于画布，
       缩放结果不小于画布 —— 补边会在这条上现形（补出来的空白是编的像素）
    F. 全链路**只有一台**渲染器声明调模型（位置 4），且它不在这三格里面
    G. 要抠的素材**一轮只抠一份**：run.jsonl 里每种素材恰好一条 cutout 记录，
       且位置 6/7 的报告指回的正是那份产物（渲染器只读不抠）

A 条为什么要说「成因」，而不是只说「跳过」：

    `slot_skipped` 有两个生产者，两类的**处置动作相反**：

        cause=intake       入口就缺料       → 去补素材照片
        cause=cutout_error 运行时抠图连续失败 → 关掉审核台 / 别并发跑抠图，再重跑

    原来两者只有散文 `reason`，于是判据只能两分（做了 / 没做），
    控制台也只能笼统写「缺料」—— 运营会照着错的方向查半天。
    所以 A 条现在**先验成因可读**（只有散文 = 报红），**再按成因分流**：
    `intake` 是计划内；`cutout_error` 是环境降级，单列成一类 **degrades** ——
    它既不进 `fails`（不该冤枉没坏的代码），也不许算作全绿（那会让
    「全绿」随机器内存浮动）。它走**退出码 7**，并在报告里给出下一动作。

退出码：0 全过 / 1 有断言失败 / 2 用法或数据问题 / 7 本批少于齐套（环境降级）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402  （控制台编码归一：见 src/console.py）
enable_utf8()

import orchestrator  # noqa: E402  （日志的唯一读法 —— 验收口径照抄产品口径）
import registry  # noqa: E402  （读 renderer 的声明式元数据）

M5_SLOTS = (5, 6, 7)

# 跳过成因的**唯一权威清单**。生产者是 src/assets.py（"intake"）与
# src/orchestrator.py（"cutout_error"），这里是判据侧。
# 写成白名单而不是「非空即可」：将来新造一个成因时，判据要**先红一次**，
# 逼人回来确认它属于哪一类（计划内 / 环境降级）。沉默接受未知成因 = 假通过。
CAUSE_INTAKE = "intake"
CAUSE_CUTOUT = "cutout_error"
KNOWN_CAUSES = (CAUSE_INTAKE, CAUSE_CUTOUT)

# 环境降级的**机器可读标记**：写进 stdout，供 tools/regress_all.py 归类为
# 「被环境拦下」而不是「未通过」。用带冒号的前缀而不是中文短语：
# 归类靠的是字符串匹配，中文与措辞会变，标记不能跟着变。
DEGRADE_TAG = "M5-DEGRADE:"

# 产物名按 `synth.filename_for` 的约定：{upc}_{坑位号:02d}_{role}_{seq}.jpg
# （role 来自坑位表，seq 是版本号 —— 重做一次就 +1）。
_PRODUCT_RE = re.compile(r"_(\d{2})_[^_]+_\d+\.jpg$")
# 位置 6/7 现在是纯确定性合成（抠图已经提前做掉了），但一张 1600px 画布的
# LANCZOS 缩放 + JPEG 落盘本来就要一秒上下 —— 阈值按"秒级"取，不按"毫秒级"假称。
MAX_COMPOSE_S = 3.0
OK, BAD = "\u2713", "\u2717"


def newest_run() -> Path | None:
    runs = [p for p in (ROOT / "out").glob("*") if (p / "run.jsonl").exists()]
    return max(runs, key=lambda p: p.stat().st_mtime) if runs else None


def load(run_dir: Path) -> tuple[dict, dict, dict, list[dict], list[dict]]:
    # 容错读：out/ 里可能躺着历史遗留的半行日志（被中断的那次 run）。
    # 产品侧早就把"正在被写的日志"当成正常情况了 —— 验收口径照抄产品口径。
    recs = orchestrator.read_records(run_dir, tolerant=True)
    start = next((r for r in recs if r["stage"] == "run_start"), {})
    renders = {r["slot_id"]: r for r in recs if r["stage"] == "render"}
    validates = {r["slot_id"]: r for r in recs if r["stage"] == "validate"}
    cutouts = [r for r in recs if r["stage"] == "cutout"]
    # skipped 必须读：A 条的判据是「出图 ∪ 跳过 == 齐套可做」，
    # 而只数产物文件是读不出「跳过的成因」的 —— 那正是原来两分判据的病根。
    skipped = [r for r in recs if r["stage"] == "slot_skipped"]
    return start, renders, validates, cutouts, skipped


def assert_a(run_dir: Path, start: dict, skipped: list[dict],
             fails: list[str], degrades: list[str]) -> None:
    print("A. 齐套可做的每一格都有下文，且跳过带机器可读的成因")
    doable = sorted(start.get("doable") or [])
    names = sorted(p.name for p in run_dir.glob("*.jpg"))
    # ★ 按**坑位**聚合，不按文件个数。
    #   重做是「新增版本，不覆盖」（保护归因数据），所以同一格会出现 _2/_3 ——
    #   那是设计如此，不是多出了一张产物。数文件个数会让这条断言的结果
    #   随「这轮之后有没有被重做过」而变，那就不是断言，是碰运气。
    slots, unmatched = set(), []
    for n in names:
        m = _PRODUCT_RE.search(n)
        if m:
            slots.add(int(m.group(1)))
        else:
            unmatched.append(n)
    got = sorted(slots)

    # ★ 先按坑位**去重**：同一次跳过会在 run.jsonl 里出现两遍 ——
    #   运行时那处立刻记一条（被中断也留痕），收尾再整批重记一遍（run_end 前）。
    #   这是设计如此，不是重复上报。判据按坑位聚合，不按记录条数，
    #   否则一处跳过会报成"N 条未通过"，把数量当成严重度。
    by_slot: dict[object, dict] = {}
    for k in skipped:
        by_slot[k.get("slot_id")] = k          # 后写覆盖：留收尾那条（最完整）
    skipped = list(by_slot.values())

    # ── 第一条：成因必须机器可读。判在集合比较**之前** ──────────────
    # 理由：成因不可读时，「哪些是计划内、哪些是降级」根本无从分起。
    # 先把这一条立住，第三条的分流才有依据。
    causes_ok = True
    for k in skipped:
        sid, cause = k.get("slot_id"), k.get("cause")
        if cause not in KNOWN_CAUSES:
            causes_ok = False
            fails.append(f"位置 {sid} 的跳过记录没有机器可读的成因"
                         f"（cause={cause!r}，已知成因只有 {list(KNOWN_CAUSES)}）"
                         f"—— reason 是给人看的话，不能靠解析它得知成因")
        if not str(k.get("reason") or "").strip():
            causes_ok = False
            fails.append(f"位置 {sid} 的跳过记录没有 reason —— "
                         f"成因给机器、理由给人，两个都不能省")

    # ── 第三条：按成因分流（原来缺的就是这一半）────────────────────
    by_cause: dict[str, list[int]] = {}
    for k in skipped:
        by_cause.setdefault(str(k.get("cause")), []).append(k.get("slot_id"))
    degraded = sorted(x for x in (by_cause.get(CAUSE_CUTOUT) or []) if x is not None)
    planned = sorted(x for x in (by_cause.get(CAUSE_INTAKE) or []) if x is not None)

    # ── 第二条：没有坑位无声消失 ────────────────────────────────────
    # ★ 比的是「**表里的全部坑位**」，不是只比 doable。
    #   因为 `assets.resolve` 会把**入口缺料**的坑位从 doable 里摘掉、只留在 skipped
    #   （cause=intake）。若拿 `got ∪ skipped == doable` 比，那些计划内跳过的坑位
    #   就成了"多出来的"—— 一条只会在"这次确实缺了料"时才触发的假红，
    #   而那恰恰是最该看准的时刻。所以全集 = doable ∪ 入口跳过的坑位。
    universe = set(doable) | set(planned)
    covered = set(got) | {k.get("slot_id") for k in skipped}
    lost = sorted(s for s in universe if s not in covered)
    extra = sorted(s for s in covered if s not in universe)
    sets_ok = not lost and not extra

    ok = causes_ok and sets_ok and not unmatched
    print(f"   齐套可做 {doable}  →  出图坑位 {got}（共 {len(names)} 个版本文件）")
    for n in names:
        print(f"     {n}")
    print("   跳过 %d 格：%s" % (len(skipped),
          "、".join(f"位置 {k.get('slot_id')}（cause={k.get('cause')}）"
                    for k in skipped) or "无"))
    print(f"   {OK if sets_ok else BAD} 出图 ∪ 跳过 == 表里的全部坑位"
          f"（齐套可做 {doable} ∪ 入口跳过 {planned} = {sorted(universe)}；"
          f"实得 {sorted(covered)}）")
    if lost:
        fails.append(f"这些坑位既没出图、也没有跳过记录：{lost} —— "
                     f"无声消失是最坏的一种：日志里也查不到")
    if extra:
        fails.append(f"这些坑位出了图 / 有跳过记录，却不在表里：{extra}")
    if unmatched:
        fails.append(f"这些产物文件名里读不出坑位号：{unmatched} —— "
                     f"命名不按约定就没有判据，不能当没看见")

    if planned:
        print(f"   · 计划内跳过（cause={CAUSE_INTAKE}，入口缺料）：位置 {planned}")
        print("     动作：补素材照片即可；不降级、不用别的图凑 —— 这是设计如此。")
    if degraded:
        print(f"   ⚠ {DEGRADE_TAG} 位置 {degraded} 是**运行时抠图连续失败**后跳过的"
              f"（cause={CAUSE_CUTOUT}），不是缺料。")
        print(f"     本批比承诺的少 {len(degraded)} 张。成因是环境，不是代码："
              f"抠图约需 6 GB 物理 / 9 GB 可提交内存。")
        print("     动作：关掉审核台 / 别并发跑抠图进程，再跑一次。")
        degrades.append(f"位置 {degraded} 因运行时抠图失败而跳过（环境降级，"
                        f"本批 {len(doable) - len(degraded)}/{len(doable)} 张）")

    miss = [s for s in M5_SLOTS if s not in doable]
    if miss:
        print(f"   · 注：{miss} 本次连「可做」都不算（入口就缺料），"
              f"B~F 只对已出的那几格生效")


def assert_b(renders: dict, fails: list[str]) -> None:
    print("\nB. 位置 5/6 的像素来源（不是 subject.png）")
    for sid, kind in ((5, "closeup"), (6, "contents")):
        r = renders.get(sid)
        if not r:
            continue
        d = r.get("detail") or {}
        src = Path(str(d.get("pixels_from") or "")).name
        # 位置 6 读的是 contents 原片的**抠图产物**（raw/cut_contents.png）——
        # 名字里带着来源素材名，所以这条判断同时覆盖两种情形。
        ok = d.get("subject_used") is False and kind in str(d.get("pixels_from") or "")
        print(f"   {OK if ok else BAD} 位置 {sid}  subject_used={d.get('subject_used')}  "
              f"pixels_from=…{src}")
        if not ok:
            fails.append(f"位置 {sid} 的像素来源不对：它该来自 {kind} 原片、"
                         f"且明确声明不读 subject.png，实际 "
                         f"subject_used={d.get('subject_used')}")


def assert_c(renders: dict, fails: list[str]) -> None:
    print("\nC. 位置 7 同时用到主体与竞品（不变量 A 在这一格也成立）")
    r = renders.get(7)
    if not r:
        print("   · 本次没有位置 7（跳过）")
        return
    d = r.get("detail") or {}
    base = (renders.get(1, {}).get("detail") or {}).get("subject_sha256")
    same = bool(base) and d.get("subject_sha256") == base
    comp = d.get("competitor") or {}
    has_comp = (bool(comp.get("sha256")) and bool(comp.get("box"))
                and bool(comp.get("source")))
    cut = comp.get("cutout")
    cut_mode = cut.get("mode") if isinstance(cut, dict) else cut
    ok = d.get("subject_used") is True and same and has_comp
    print(f"   主体 sha：位置 7 {str(d.get('subject_sha256'))[:12]}…  /  "
          f"位置 1 {str(base)[:12]}…  →  {'一致' if same else '不一致'}")
    print(f"   竞品：来源={Path(str(comp.get('source') or '')).name}  "
          f"抠图产物=…{Path(str(comp.get('path') or '')).name}  "
          f"sha={str(comp.get('sha256'))[:12]}…  box={comp.get('box')}  抠图={cut_mode}")
    print(f"   {OK if ok else BAD} 主体同源 + 竞品到位（且可追到哪一份抠图产物）")
    if not ok:
        fails.append(f"位置 7 未同时用上主体与竞品（subject_used={d.get('subject_used')}、"
                     f"主体同源={same}、竞品块完整={has_comp}）")


def assert_d(renders: dict, fails: list[str]) -> None:
    """位置 5/6/7 的重出代价。

    ★ 这三格现在**不该有抠图**。抠图统一提前到模型调用之前做完（见
      registry.register 的 cuts 说明与 src/cutouts.py），所以：
        · 报告里不该再出现 cutout_s / 抠图模式的段落 —— 出现就说明渲染器
          又在自己抠，那一份抠图就脱离了"一轮一份"的管辖；
        · 重出代价因此就是**纯合成 + 叠字**的代价，秒级。
      这条断言的前身是"把抠图耗时单列出来" —— 那时抠图确实发生在这里。
      现在它升级成"这里根本不该有抠图"，比单列更严，也更简单。
    """
    print("\nD. 位置 5/6/7 零模型、零抠图、秒级")
    for sid in M5_SLOTS:
        r = renders.get(sid)
        if not r:
            continue
        d = r.get("detail") or {}
        secs = r.get("elapsed_s")
        model = registry.calls_model(r.get("renderer") or "")
        local_cut = bool(d.get("cutout_s")) or bool(d.get("cutout"))
        ok = (not model and not local_cut and secs is not None
              and secs < MAX_COMPOSE_S)
        print(f"   {OK if ok else BAD} 位置 {sid}  {str(r.get('renderer')):<18}"
              f"{secs}s  调模型={model}  本格内抠图={local_cut}")
        if not ok:
            fails.append(f"位置 {sid} 不是纯确定性合成：{secs}s、"
                         f"calls_model={model}、格内抠图={local_cut}")


def assert_e(renders: dict, fails: list[str]) -> None:
    print("\nE. 位置 5 是「裁切填满」而不是「缩小留白」")
    r = renders.get(5)
    if not r:
        print("   · 本次没有位置 5（跳过）")
        return
    d = r.get("detail") or {}
    crop, scaled, out = d.get("cover_crop"), d.get("cover_scaled"), d.get("out_size")
    if not crop or not out:
        fails.append("位置 5 没记录 cover_crop / out_size，无法断言取景方式")
        print(f"   {BAD} 缺证据")
        return
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    # 裁切框必须**恰好**是画布（多说明取景里有补边，少说明没铺满）
    no_pad = (cw, ch) == (out[0], out[1])
    big_enough = bool(scaled) and scaled[0] >= out[0] and scaled[1] >= out[1]
    ok = no_pad and big_enough
    print(f"   裁切框 {cw}×{ch}  缩放后 {scaled}  画布 {out}  scale={d.get('cover_scale')}")
    print(f"   {OK if ok else BAD} 裁切框恰等于画布，且缩放结果不小于画布（无补边）")
    if not ok:
        fails.append(f"位置 5 的取景不是纯裁切：裁切框 {cw}×{ch} vs 画布 {out}，"
                     f"缩放后 {scaled} —— 补边会引入编出来的像素")


def assert_f(start: dict, renders: dict, fails: list[str]) -> None:
    print("\nF. 全链路只有一台渲染器声明调模型")
    n = start.get("model_calls")
    doable = start.get("doable") or []
    model_renderers = sorted({str((renders.get(s) or {}).get("renderer"))
                              for s in doable if s in renders
                              and registry.calls_model(
                                  str((renders.get(s) or {}).get("renderer")))})
    ok = n == 1 and model_renderers == ["gen_bg_paste"]
    print(f"   run_start 记录的 model_calls={n}（doable={doable}）")
    print(f"   本批里确实调模型的渲染器：{model_renderers or '（无）'}")
    print(f"   {OK if ok else BAD} 恰好 1 次，且只有 gen_bg_paste")
    if not ok:
        fails.append(f"model_calls={n}，声明调模型的渲染器={model_renderers}，"
                     f"期望恰好 1 次且只有 gen_bg_paste")


def assert_g(run_dir: Path, renders: dict, cutouts: list[dict],
             fails: list[str]) -> None:
    """要抠的素材**一轮只抠一份**，且渲染器只读不抠。

    这条守的是 M6「重做只改我想改的那一处」的前提：只要渲染器还会自己现抠，
    竞品/内容物的像素就可能在"只是挪了下位置"的重做里被换掉 ——
    rembg 与 floodfill 抠出的紧致 alpha 相差十几万像素，实测过。
    """
    print("\nG. 抠图产物一轮一份，渲染器只读不抠")
    want = sorted({k for s in renders.values()
                   for k in registry.cuts_of(str(s.get("renderer") or ""))})
    if not want:
        print("   · 本批没有渲染器声明要抠素材，跳过")
        return
    got = sorted(c.get("kind") for c in cutouts)
    print(f"   渲染器声明的素材 {want}  →  run.jsonl 里的 cutout 记录 {got}")
    if got != want:
        fails.append(f"抠图产物与声明不符：声明 {want}，实际 {got}")
        print(f"   {BAD} 不一致")
    for c in cutouts:
        p = Path(str(c.get("path") or ""))
        ok = p.exists() and p.parent.name == "raw" and p.suffix == ".png"
        print(f"   {OK if ok else BAD} {c.get('kind'):<11}{p.name}  "
              f"mode={c.get('mode')}  "
              f"sha={str(c.get('sha256'))[:12]}…  耗时 {c.get('elapsed_s')}s")
        if not ok:
            fails.append(f"{c.get('kind')} 的抠图产物不在 raw/ 下或不是 PNG：{p}")

    # 位置 6/7 必须指回同一份产物 —— 而不是"自己又抠了一份，恰好长得像"。
    # 两格报告里放凭证的位置不同（6 是 cutout_ref 块，7 是 competitor 块），
    # 但都带 sha256；按各格**自己声明的素材名**去对照，不写死坑位号。
    by_kind = {c["kind"]: c for c in cutouts}
    for sid in (6, 7):
        r = renders.get(sid)
        if not r:
            continue
        d = r.get("detail") or {}
        kinds = registry.cuts_of(str(r.get("renderer") or ""))
        if not kinds:
            continue
        kind = kinds[0]
        node = (d.get("cutout_ref") or {}) if sid == 6 else (d.get("competitor") or {})
        want_sha = (by_kind.get(kind) or {}).get("sha256")
        ok = bool(node.get("sha256")) and node["sha256"] == want_sha
        print(f"   {OK if ok else BAD} 位置 {sid} 报告指回 {kind} 抠图产物  "
              f"报告={str(node.get('sha256'))[:12]}…  产物={str(want_sha)[:12]}…")
        if not ok:
            fails.append(f"位置 {sid} 的报告没有指回那一份抠图产物"
                         f"（报告={str(node.get('sha256'))[:12]}…，"
                         f"产物={str(want_sha)[:12]}…）—— 它可能自己又抠了一份")


def main(argv: list[str]) -> int:
    run_dir = Path(argv[1]) if len(argv) > 1 else newest_run()
    if not run_dir or not (run_dir / "run.jsonl").exists():
        print("找不到 run.jsonl：请先跑一次 "
              "`python run.py --product examples/product_fullset.json`")
        return 2

    # ★ 必须先加载渲染器：`registry.calls_model()` 读的是注册表，
    #   不 load_all() 它就是个空表 —— 于是 D 条会**假通过**（所有渲染器都"不调模型"），
    #   F 条会**假失败**（一个都找不到）。这个坑是实测撞出来的，写在这里免得再撞。
    registry.load_all()

    start, renders, validates, cutouts, skipped = load(run_dir)
    print(f"M5 验收 · {run_dir.name}\n" + "=" * 72)
    fails: list[str] = []
    degrades: list[str] = []
    assert_a(run_dir, start, skipped, fails, degrades)
    assert_b(renders, fails)
    assert_c(renders, fails)
    assert_d(renders, fails)
    assert_e(renders, fails)
    assert_f(start, renders, fails)
    assert_g(run_dir, renders, cutouts, fails)

    print("\n" + "=" * 72)
    if degrades:
        print(f"{DEGRADE_TAG} 本批因环境少做了 {len(degrades)} 处（不并入「未通过」）：")
        for d in degrades:
            print(f"  ⚠ {d}")
    if fails:
        print(f"未通过 {len(fails)} 条：")
        for f in fails:
            print(f"  {BAD} {f}")
        return 1
    if degrades:
        # 判定干净，但这一批比承诺的少。两头都不许：
        #   报成全绿 → 「全绿」会随机器内存浮动，等于没有结论；
        #   并进 fails → 冤枉没坏的代码，人会去改对的东西。
        # 所以单列退出码 7，并把下一动作写在结论里。
        print("断言全过：位置 5/6/7 各自读自己的素材，位置 7 与位置 1 共用同一份主体，"
              "要抠的素材一轮只抠一份、渲染器只读不抠。")
        print(f"{DEGRADE_TAG} 但上面那几处跳过是**环境降级**，不是本次改动的结论 —— "
              f"退出码 7。请关掉审核台 / 别并发跑抠图，在内存宽裕时重跑一次再下结论。")
        return 7
    print("全部通过：位置 5/6/7 各自读自己的素材，位置 7 与位置 1 共用同一份主体，"
          "要抠的素材一轮只抠一份、渲染器只读不抠，全链路仍只有位置 4 调模型。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
