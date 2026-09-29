"""CLI 入口。

用法：
    # 干跑：只算不产图（先看"这次会出几张、调几次模型"）
    python run.py --product examples/product_demo.json --dry-run

    # 真跑（七个坑位都是真实像素：1/2/3/5/6/7 零模型，4 调一次生成模型）
    python run.py --product examples/product_demo.json

    # 换抠图方式（比如 rembg 在这台机器上偶发内存不足）
    python run.py --product examples/product_demo.json --cutout floodfill

    # 换位置 4 的生成模型
    python run.py --product examples/product_fullset.json --model qwen-image-3.0

    # 只做某几个坑位（= 重放 plan 的第 k 条）
    python run.py --product examples/product_demo.json --only 1,2

    # 重做某一格（新增版本，不覆盖）。改了一句文案就只重排文字层：
    python run.py --product examples/product_demo.json --redo 2 --layer text

    # 看得到进度（位置 4 要等约 75s，等待期要能看见它在跑）
    python run.py --product examples/product_fullset.json --progress

返回码
------
    0 正常 / 干跑完成 / 重做完成
    3 整批拒绝（E0 自动体检不合格，或缺平台强制坑位的素材）
    4 启动失败（坑位表本身有错），或**这次重做不可用**
      （坑位没有文字层 / 上一轮没留底 / 重抠主体失败）—— 都在烧钱之前就炸
    5 合规项未签字（工具判不了的那几条没人确认）—— **只有真跑会返回它**
    6 主体无法从原片中分离（背景与主体颜色太近 / 抠图推理连续失败）
      —— 属**输入或环境问题**，工具修不了。这类图能过白底校验却不可上架，
         所以宁可整批停下，也不产出一批看着合规的废图。见 src/subject.py。

关于抠图（`--cutout`）
----------------------
    auto（默认）  本地 rembg 优先 → **本地没有模型**时降级 floodfill
    rembg         只用 rembg
    floodfill     只用洪水填充（质量略降，但结果只取决于输入）

    降级只发生在**确定的条件**上：模型不在是配置事实，这一轮每次调用都一样。
    而 rembg **推理失败**（偶发 bad allocation）会重试 3 次，仍失败就报错 ——
    **不静默换路**。理由很具体：floodfill 与 rembg 抠出的 alpha 相差十几万像素，
    静默换路会让"重做一次"的产出与上一版不同，而版本对比的全部意义正是
    "差异只来自被改的那一处"。想换就用 `--cutout floodfill` 明说。
    跑完会打印**实际**走的哪条路（`抠图实际方式 …`）。

关于"重做"（M6/M7）
-------------------
    重做不是第二条链路 —— 它是"重放 plan 里的某一条"，且**新增版本不覆盖**
    （`_1` 留着，新的是 `_2`）。覆盖会抹掉归因数据：改了文案之后
    "上一版长什么样"就再也拿不回来了，而"哪一版更好"正是要靠对比回答的问题。

    粒度由 `--layer` 决定，因为**改一句文案的代价必须与重新画一张图分开**：

        text       只重排文字层（复用上一轮的文字底）     秒级 · 零模型
        placement  只动主体落点（复用生成底）             秒级 · 零模型
        bg         重新生成背景（位置 4 唯一花钱的一档）   约 70s · 1 次调用
        cutout     本地重抠主体 → **所有读主体的坑位**重出  一次本地抠图 · 零调用
                   （各格内部按 placement 语义走，位置 4 复用生成底）

    代价划分不是拍脑袋：七成情况（文案、构图）免费，只有背景花钱 ——
    而背景恰好是唯一本来就该由模型产生的东西。

    上一轮的产物在 `out/<UPC>_<时间戳>/` 里，它们就是"可重做"的物质基础：
        subject.png            重做不再重抠主体（除 `--layer cutout`）
        raw/slotNN_bg.jpg      文字**是在最后一遍加上去的**的物证
        raw/slot04_gen.jpg     生成底；placement/cutout 复用它是"零调用"的依据
    没有它们，任何一次改动都只能整批重跑。

关于"什么时候结束"
------------------
    **没有自动结束判定。** `--progress` 让你看得见每一步；改到满意就停手，
    这是人按的按钮，不是工具替你判断"够好了"。见 docs/使用形态.md。

关于"合规签字"
--------------
    水印、道具、主体是否完整、角度、字体授权 —— 这几条**没有规则可写**，
    机器判不了（见 src/intake.py 的说明）。工具不假装验过它们，
    但真跑时要求 product 里有一份签字：

        "attest": {"by": "运营 A", "date": "2026-09-20",
                   "confirmed": ["no_watermark", "no_props",
                                 "single_subject", "angle_ok", "font_license"]}

    签字会落进 plan.json 与 run.jsonl —— 于是"谁在什么时候确认过什么"
    是可回溯的。**这正是人工项唯一能被事后审计的方式。**

关于参数
--------
参数一律"有消费方才存在"。
`--cutout` 的消费方是 `src/subject.prepare(cutout_mode=…)` ——
七张图共用同一份主体，抠图方式自然只在这一个地方生效。
（位置 6/7 各自抠自己的素材，走的是同一条 `synth.remove_background`，
 所以这个开关对它们同样有效。）
`--model`  的消费方是 `renderers/gen_bg_paste.render` ——
位置 4 是全链路唯一调云端生成模型的一格，所以它只影响那一格。

刻意**没加**的：
    `--passthrough` 已被取代。它的原意是"输入已是白底图，别抠"；
        新设计里这件事由 E0 判（`has_alpha` / `corner_white`）+ subject 自动接管，
        再加一个开关就多一个能和它打架的地方。

关于位置 4 的 key（M4）
-----------------------
    set DASHSCOPE_API_KEY=sk-xxx   (Windows)
    export DASHSCOPE_API_KEY=sk-xxx (bash)

    **没有 key 也能跑通全链路**：位置 4 会退化成一张标注清楚的占位背景，
    产物自报 `placeholder=true`（run.py 打印"（占位图）"），
    其余六格是真实像素。这样"编排、抠图、贴图、叠字、校验、重做"全都可验，
    只有那一格的画面不可用 —— 而且它不会假装可用。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402  （控制台编码归一：见 src/console.py）
enable_utf8()

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

import assets as assets_mod  # noqa: E402
import intake  # noqa: E402
import orchestrator  # noqa: E402

LINE = "=" * 72


def _progress_cb(enabled: bool):
    """--progress 的回调。位置 4 要等约 75s，等待期必须看得见它在跑。"""
    if not enabled:
        return None

    def cb(line: str) -> None:
        # flush 是必需的：不 flush 的话进度会攒在缓冲区里，
        # 等到进程结束才一次性吐出来 —— 那就等于没有进度。
        print(line, flush=True)

    return cb


def _print_cutout_actual(rep: dict) -> None:
    """打印抠图**实际**走的那条路（不是请求的那个）。

    为什么值得占这几行：请求的是 auto，实际可能落在 rembg，也可能降级到
    floodfill（本地没有模型时）。两者的边缘质量不一样，而**整批七张图共用
    同一份主体**，素材抠图也各只有一份 —— 所以"用了哪条路"是这一批图的
    性质，不是内部实现细节。
    重试成功也要说：它说明这台机器的抠图偶发不稳（见 synth.INFER_ATTEMPTS），
    下一次可能就在别处炸。
    """
    sub = rep.get("subject")
    if sub:
        cut = sub.get("cutout") or {}
        bits = [f"抠图实际方式 {cut.get('mode')}"]
        if cut.get("session"):
            bits.append(f"会话 {cut['session']}")
        if cut.get("rembg_skipped"):
            bits.append(f"⚠️ {cut['rembg_skipped']}")
        if cut.get("infer_retried"):
            bits.append(f"⟳ 推理失败 {len(cut['infer_retried'])} 次后重试成功")
        cov = sub.get("alpha_coverage")
        if cov is not None:
            bits.append(f"前景覆盖 {cov:.1%}")
        print(" · ".join(bits))
        print(f"        {sub.get('path')}")

    for kind, info in (rep.get("cutouts") or {}).items():
        cut = info.get("cutout") or {}
        if info.get("reused_from"):
            mark = f"（复用 {info['reused_from']}）"
        elif info.get("recomputed"):
            mark = "（本轮重抠）"
        else:
            mark = "（本轮新抠）"
        cov = info.get("alpha_coverage")
        print(f"素材抠图 {kind:<11}{cut.get('mode')}  {info.get('path')}"
              + (f"  前景覆盖 {cov:.1%}" if isinstance(cov, float) else "")
              + mark)
    if sub or rep.get("cutouts"):
        print("-" * 72)


def _print_e0(p) -> None:
    """把 E0 体检结果打印出来 —— 顺序与真实执行一致（体检在最前）。"""
    e0 = p.e0
    if not e0:
        return
    print("E0 体检（在抠图之前、在任何模型调用之前）")
    for kind, f in e0.images.items():
        if f.get("readable"):
            print(f"  ✓ {kind:<11}{f['width']}×{f['height']}  {f['mode']:<5}"
                  f"最长边 {f['long_side']}")
        else:
            print(f"  ✗ {kind:<11}不可读：{f.get('error')}")
    if e0.font:
        print(f"  · {'字体':<10}{e0.font['path']}（{e0.font['source']}）")
    for n in e0.notices:
        print(f"  提醒  {n}")
    for ln in intake.attest_lines(e0, needs_font=p.needs_font,
                                  needs_competitor=p.needs_competitor):
        print(ln)
    print()


def _print_materials(p) -> None:
    print("素材齐套")
    for kind in assets_mod.ALL_KINDS:
        got = p.supplied.get(kind)
        if got:
            print(f"  ✓ {kind:<11}{got}")
        elif kind in p.broken:
            print(f"  ✗ {kind:<11}填了但文件不存在：{p.broken[kind]}")
        else:
            missing_for = [d.slot_id for d in p.decisions
                           if kind in d.missing]
            tail = f" → 跳过坑位 {missing_for}" if missing_for else ""
            print(f"  ✗ {kind:<11}（未提供）{tail}")
    print()


def _print_decisions(p) -> None:
    print("坑位处置（像素来源由 renderer 声明，不由编排器判断）")
    for d in p.decisions:
        flag = "→ 做" if d.status == "will_run" else "× 跳过"
        extra = f"  缺：{'、'.join(d.missing)}" if d.missing else ""
        model = "调模型" if d.calls_model else "零模型"
        print(f"  [{d.slot_id}] {flag:<7}{d.renderer:<18}{d.text:<9}{model:<7}"
              f"{d.pixels_from}{extra}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description="亚马逊七坑位素材生成 · 表驱动骨架")
    ap.add_argument("--product", required=True, help="商品输入 JSON")
    ap.add_argument("--out", default=str(ROOT / "out"), help="输出根目录")
    ap.add_argument("--only", default="", help="只跑指定坑位，逗号分隔，如 1,2")
    ap.add_argument("--dry-run", action="store_true",
                    help="只算不产图：输出张数、跳过项、模型调用次数")
    ap.add_argument("--text-mode", choices=["none", "overlay"], default=None,
                    help="覆盖文字产生方式（只对 text != none 的坑位生效；"
                         "平台强制坑位恒为 none）")
    ap.add_argument("--cutout", choices=["auto", "rembg", "floodfill"], default=None,
                    help="抠图方式，主体/内容物/竞品三处共用（默认 auto：本地 rembg "
                         "优先，本地没有模型文件时降级 floodfill；两者都不联网、"
                         "不下载）。rembg 推理失败会重试 3 次，仍失败则报错而**不**"
                         "静默换路（换路会换掉像素，版本对比就失去意义）")
    ap.add_argument("--model", default=None,
                    help="位置 4 用的生成模型（默认取 IMAGE_MODEL 环境变量，"
                         "再默认 qwen-image-3.0）。**只影响位置 4** —— "
                         "其余六格由 registry 声明保证零模型")
    ap.add_argument("--redo", type=int, metavar="SLOT", default=None,
                    help="重做某一格（坑位号）。**新增版本、不覆盖上一版**；"
                         "配合 --layer 决定复用多少既有产物")
    ap.add_argument("--layer", choices=list(orchestrator.LAYERS), default=None,
                    help="重做的粒度（仅与 --redo 搭配生效）："
                         "text=只重排文字层（秒级/零模型，默认）· "
                         "placement=只动主体落点（复用生成底，零模型）· "
                         "bg=重新生成背景（位置 4 唯一花钱的一档）· "
                         "cutout=本地重抠主体，所有读主体的坑位一起重出")
    ap.add_argument("--autofix", action="store_true",
                    help="渲染后先跑 L0 确定性修复（白底偏灰 / 占比不足 / 非 1:1 / "
                         "分辨率不足 / 体积超限），修完立即复验并将 before/after 留痕"
                         "进 run.jsonl。**默认关** —— 它会改像素，默认开启会让"
                         "「产物到底是不是渲染器直接产出的」变成一个要读日志才知道的"
                         "问题。修不了的项不会被硬修，只报出该走哪一级")
    ap.add_argument("--progress", action="store_true",
                    help="边跑边打印进度（位置 4 等模型时尤其需要）")
    args = ap.parse_args()

    # 商品包的读法与素材相对路径的解析**只有一处实现**（orchestrator.load_product）——
    # 审核台后端读的是同一个函数。"上一轮是哪一轮"同理（orchestrator.latest_run）。
    try:
        pkg = orchestrator.load_product(args.product)
    except FileNotFoundError as exc:
        print(f"启动失败：{exc}")
        return 4
    product, base = pkg.product, pkg.base_dir

    only = [int(x) for x in args.only.split(",") if x.strip()] if args.only else None

    # 静默忽略会让人以为"参数已经生效了"。这个坑本项目踩过两次
    # （色板双所有者、--cutout 在没有主体需求的 run 上不生效），所以显式说清。
    if args.layer is not None and args.redo is None:
        print(f"提醒：--layer {args.layer} 只与 --redo 搭配生效，本次不生效\n")
    if args.redo is not None and args.only:
        print("提醒：--redo 已锁定单一坑位，本次 --only 不生效\n")

    # ---- 重做分支：**不走 plan_run**。
    #      重做不产生新计划，它重放上一轮计划里的某一条 —— 所以它也不需要
    #      新开一个 run 目录（新版本就落在上一轮目录里，紧挨着被对比的那一版）。
    if args.redo is not None:
        if args.dry_run:
            print("启动失败：--redo 与 --dry-run 不能同时用 —— "
                  "干跑不产图，也就没有可重做的上一轮。")
            return 4
        out_dir = Path(args.out)
        prev = orchestrator.latest_run(out_dir, product.get("upc") or "NOUPC")
        if prev is None:
            print(f"启动失败：{out_dir} 里没有 {product.get('upc') or 'NOUPC'} 的可重做 run"
                  f"（需要上一轮留下的 plan.json）。先正常跑一次。")
            return 4
        layer = args.layer or "text"          # 不指定就按最常见的需求：改文案
        print(LINE)
        print(f"重做 位置 {args.redo}    layer={layer}    基于 {prev.name}")
        print(f"{orchestrator.LAYER_DOC[layer]}")
        print(LINE)
        try:
            rep = orchestrator.redo(prev, product, args.redo, layer=layer,
                                    base_dir=base, cutout=args.cutout,
                                    model=args.model,
                                    progress=_progress_cb(args.progress))
        except ValueError as exc:          # 参数不可用：坑位无文字层 / 上一轮没留底 /
                                          # 重抠主体失败（见 redo 的顺序规矩）
            print(f"无法重做：{exc}")
            return 4

        sub = rep.get("subject") or {}
        if rep["layer"] == "cutout":
            print(f"主体重抠  {sub.get('cutout_mode')}  覆盖 {sub.get('elapsed_s')}s  "
                  f"sha {str(sub.get('sha256'))[:12]}…  "
                  + ("（与上一份不同）" if sub.get("changed")
                     else "（与上一份相同 —— 抠图结果没变）"))
            print()
        # 重做的返回契约是**一组新版本**：单格粒度这一组恰好只有一个元素。
        for r in rep["results"]:
            v = r.get("validation") or {}
            mark = "（占位图）" if r.get("placeholder") else ""
            print(f"  [{r['slot_id']}] {r['renderer']:<18}第 {r['seq']} 版  "
                  f"{r['elapsed_s']}s  {mark}"
                  + ("· 校验通过" if v.get("passed")
                     else f"· ✗ 校验未过：{'、'.join(v.get('failed') or [])}"))
            print(f"        {r['path']}")
        print()
        print(f"本次重出 {len(rep['results'])} 版 · 模型调用 {rep['model_calls']} 次")
        if rep["model_calls"] == 0:
            print("（生成底被复用或本来就是确定性链路 —— 这一档没花钱）")
        print(LINE)
        return 0

    try:
        plan = orchestrator.plan_run(product, only=only, out_dir=args.out,
                                     base_dir=base,
                                     product_path=str(pkg.path))
    except ValueError as exc:              # 表校验失败：启动即炸，不烧调用费
        print(f"启动失败：{exc}")
        return 4

    print(LINE)
    print(f"UPC {plan.upc}    表 config/slots.yaml    类目 {plan.catalog.get('label')}")
    print(LINE)
    print(f"{plan.summary_line()}\n")
    _print_e0(plan)
    _print_materials(plan)
    _print_decisions(plan)

    if plan.needs_subject and not plan.rejected:
        shared = sum(1 for s in plan.doable if "front" in (s.get("needs") or []))
        how = args.cutout or "auto（本地 rembg 优先 → floodfill 降级）"
        print(f"主体产出  1 次本地抠图（{how}）→ {shared} 个坑位"
              f"共用同一份 subject.png（不变量 A）· 不联网、零 API 成本")
    elif args.cutout:
        # 说清"这个参数这次不生效" —— 静默忽略会让人以为抠图方式已经换了
        print(f"提醒：本次没有坑位需要主体，--cutout {args.cutout} 不生效")
    if plan.cut_kinds and not plan.rejected:
        # 素材抠图也提前做，且**排在模型调用之前**：抠图失败就不该再烧调用费，
        # 而抠图推理在进程跑热之后偶发抓不到内存（实测踩过）。
        print(f"素材产出  {len(plan.cut_kinds)} 次本地抠图"
              f"（{'、'.join(plan.cut_kinds)}）→ 也提前做在模型调用之前")
    if (plan.needs_subject or plan.cut_kinds) and not plan.rejected:
        print()

    if plan.rejected:
        print(f"整批拒绝：{plan.rejected}")
        print(LINE)
        return 3

    print(f"输出目录 {plan.run_dir}")
    rep = orchestrator.execute(plan, dry_run=args.dry_run,
                              text_override=args.text_mode,
                              cutout=args.cutout,
                              model=args.model,
                              autofix=args.autofix,
                              progress=_progress_cb(args.progress))

    if rep.get("subject_error"):
        print("未出图 —— 主体无法从原片中分离：")
        print(f"  {rep['subject_error']}")
        print(LINE)
        return 6

    if rep.get("unattested"):
        print("未出图 —— 合规项未签字：")
        print(f"  {rep['message']}")
        print(LINE)
        return 5

    if args.dry_run:
        print("干跑完成：未写任何文件、未调用任何模型。")
        print(LINE)
        return 0

    print(LINE)
    # 抠图**实际**走了哪条路（见 orchestrator.execute 返回里的 subject/cutouts）：
    # 请求的是 auto，可能落到 rembg，也可能降级 floodfill。两者边缘不一样，
    # 运营有权在拿到图的同时知道这件事。
    _print_cutout_actual(rep)
    if plan.facts.get("dropped_bullets"):
        print(f"卖点被禁用词过滤 {len(plan.facts['dropped_bullets'])} 条：")
        for d in plan.facts["dropped_bullets"]:
            # 逐条给出"命中哪个词、违反哪份清单" —— 下架申诉时要拿这个作依据
            hit = "、".join(f"{h['word']}（{h['rule']}）" for h in d["hit"])
            print(f"   - {d['text']}  (命中 {hit})")
        print("-" * 72)
    for r in rep["results"]:
        if not r.get("ok"):
            print(f"  [{r['slot_id']}] 失败: {r.get('error')}")
            continue
        mark = "（占位图）" if r.get("placeholder") else ""
        v = r.get("validation") or {}
        vmark = ("· 校验通过" if v.get("passed")
                 else f"· ✗ 校验未过：{'、'.join(v.get('failed') or [])}")
        af = r.get("autofix")
        if af:
            fixed_n = sum(1 for a in af["attempts"] if a.get("fixed"))
            vmark += (f" · L0 修复 {fixed_n} 条"
                      + ("（复验已通过）" if af.get("passed_after") else "（复验仍未过）"))
            if af.get("escalate"):
                vmark += f" 剩余交 {'/'.join(af['escalate'])}"
        print(f"  [{r['slot_id']}] {r['purpose']:<16}{r['renderer']:<18}"
              f"{r['elapsed_s']}s {mark}{vmark}")
        print(f"        {r['path']}")
        if not v.get("passed", True):
            print(f"        逐项见 run.jsonl 的 validate 记录")
    # 报**实际**花掉的次数，而不是计划里的那个数：占位图（没 key）与复用生成底
    # 都不算花钱。"本来说要调 1 次"和"这次真花了 1 次"是两笔不同的账。
    print(f"\n模型调用 实际 {rep.get('model_calls_used', 0)} 次"
          f"（计划 {plan.model_calls} 次；占位图与复用生成底不计）")
    # 跳过必须**按成因分开报**。两者的处置动作完全相反：
    #   输入缺料   → 去补素材照片
    #   抠图失败   → 关掉审核台 / 降并发后重跑（内存不够，重试也没用）
    # 原来一律写成「（缺料）」：运营会照着一个错的方向查半天，
    # 而日志里其实分得很清楚（slot_skipped 的 cause）。
    by_cause: dict[str, list[int]] = {}
    for k in plan.skipped:
        by_cause.setdefault(str(k.get("cause") or "unknown"), []).append(k["slot_id"])
    if not plan.skipped:
        print("没有跳过的坑位")
    else:
        print(f"已跳过 {len(plan.skipped)} 个坑位，详见 run.jsonl 的 slot_skipped：")
        label = {
            "intake": "输入缺料 —— 补素材照片即可",
            "cutout_error": "素材抠图连续失败 —— 这是降级，不是计划内的缺料；"
                            "关掉审核台 / 别同时跑别的抠图进程后重跑",
        }
        for cause, ids in by_cause.items():
            mark = "" if cause == "intake" else "⚠ "
            print(f"  {mark}· {label.get(cause, cause)}：位置 "
                  f"{'、'.join(str(i) for i in ids)}")
    print(LINE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
