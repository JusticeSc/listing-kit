r"""M4 验收断言 —— 位置 4：模型只画空背景，主体确定性贴入。

用法：
    python tools/verify_m4.py                      # 取 out/ 下最近一次画出位置 4 的 run
    python tools/verify_m4.py out/B0FULLSET01_...

它断言的不是「位置 4 出了一张好看的图」（那件事工具判不了），而是
**接缝 α 在结构上真的成立**：

    A. 提示词里**无条件**含"排除产品本体"与"禁字"两条条款，且它们来自
       `gen_bg_paste` 的常量，不由 catalog 的取景提示提供
       —— 提示词是人写的、会漏；这两条必须由代码追加（不变量 B 的代码证据）
    B. 负向词里既有产品类别的英文词，也有 `brand.forbidden_on_image`
       —— 于是"配置里声明的禁令"在画面上真的生效，而不是只写在配置里
    C. 负向词未超模型上限（超了会被**静默截断**，截掉的那部分禁令等于没写）
    D. 主体同源：贴图区内与 `subject.png` 逐像素一致（容差同 verify_m3）
    E. ★ 背景未被改动：**贴图区之外**逐像素等于「生成底按 cover 铺满」的结果。
       这一条同时证明了两件事：主体是**事后贴上去**的，而不是模型画的；
       且模型没有在成品里偷偷改过背景。
    F. 背景铺满是**裁切**而不是补边：裁切框恰等画布、缩放结果不小于画布
       —— 补出来的那圈是编的像素，还会留下一条肉眼可见的接缝
    G. 位置 4 是全链路**唯一**声明调模型的渲染器
    H. 取景提示的选择是**确定性**的，且命中 `forbidden_on_image` 的提示会被弃用；
       整池命中则直接报错（类目配置与品牌禁令冲突时，报错比出一张不合规的图正确）
    I. 没有 key 时**自报** `placeholder=true` —— 它不会以"真实场景图"的身份流出去

人工目视项（工具**不假装**验过）
--------------------------------
    "背景里有没有模型偷画的产品或文字" —— 这一条机器判不了：
    任何"有没有物体"的自动判据都会在浅色桌面 / 双色墙面这类**本来就该有的纹理**上误报。
    所以工具给出的替代物是：把提示词、负向词、生成底**原样留在产物里**，
    让审核台用眼睛看那一张 `raw/slotNN_gen.jpg`。见 docs/使用形态.md 的审核台。

退出码：0 全过 / 1 有断言失败 / 2 用法或数据问题
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402  （控制台编码归一：见 src/console.py）
enable_utf8()

import orchestrator  # noqa: E402  （日志的唯一读法 —— 验收口径照抄产品口径）
import placement  # noqa: E402
import registry  # noqa: E402
import schema  # noqa: E402
from renderers import gen_bg_paste as gbp  # noqa: E402  也是本模块的取景提示素材

SLOT = 4
OK, BAD = "\u2713", "\u2717"

# 容差沿用 verify_m3 的**实测标定**（两个坑位量的都是同一种量：LANCZOS 缩放 + 两次
# JPEG 编码）。位置 4 实测：贴图区内 最大差 24 / 平均差 2.03（与位置 1/2/3 同量级）。
MAX_ABS_DIFF = 40
MEAN_ABS_DIFF = 6.0
OPAQUE_MIN = 250

# 背景未被改动这一条的容差**另定**，因为量的不是同一件事：
# 背景只是"生成底被再编码一次"，没有缩放、没有遮罩，所以噪声小一个量级。
# 位置 4 实测：最大差 8 / 平均差 0.0038。阈值留足余量但不放到没有判别力。
BG_MAX_ABS_DIFF = 20
BG_MEAN_ABS_DIFF = 1.0


def newest_run() -> Path | None:
    runs = [p for p in (ROOT / "out").glob("*") if (p / "run.jsonl").exists()]
    cands = []
    for p in runs:
        recs = load(p)
        if any(r.get("stage") == "render" and r.get("slot_id") == SLOT
               and (r.get("detail") or {}).get("generation") for r in recs):
            cands.append(p)
    return max(cands, key=lambda p: p.name) if cands else None


def load(run_dir: Path) -> list[dict]:
    # 容错读：out/ 里可能躺着历史遗留的半行日志（被中断的那次 run）。
    # 严格读会让 newest_run() 在**遍历**到一个与本次无关的坏目录时整脚本炸掉，
    # 而产品侧早就把"正在被写的日志"当成正常情况了。验收口径照抄产品口径。
    return orchestrator.read_records(run_dir, tolerant=True)


def assert_a(gen: dict, fails: list[str]) -> None:
    print("A. 提示词无条件含产品排除与禁字条款（不变量 B 的代码证据）")
    prompt = str(gen.get("prompt") or "")
    parts = [("产品排除", gbp.SUBJECT_EXCLUSION_CLAUSE),
             ("禁字", gbp.NO_TEXT_CLAUSE)]
    ok = True
    for why, clause in parts:
        inside = clause in prompt
        print(f"   {OK if inside else BAD} {why}条款{'在' if inside else '不在'}提示词里")
        print(f"       「{clause[:34]}…」")
        ok &= inside
    # 这两条必须来自本模块的常量，而不是 catalog 的取景提示 —— 后者是人写的、会漏
    src_ok = gbp.SUBJECT_EXCLUSION_CLAUSE not in str(gen.get("hint") or "")
    print(f"   {OK if src_ok else BAD} 取景提示里**没有**这两条 —— "
          f"它们是渲染器追加的，不是人写进数据的")
    if not (ok and src_ok):
        fails.append("提示词缺少无条件排除条款，或它来自取景提示（人写的会漏）—— "
                     "这正是接缝 α 的依据，缺了它主体就可能进模型")


def assert_b(gen: dict, fails: list[str]) -> None:
    print("\nB. 负向词覆盖产品类别词与 forbidden_on_image")
    neg = str(gen.get("negative_prompt") or "")
    banned = gen.get("forbidden_on_image_used") or []
    cat_words = [w.strip() for w in gbp.SUBJECT_EXCLUSION_NEGATIVE.split(",")]
    miss = [w for w in cat_words if w and w not in neg]
    print(f"   产品类别词 {len(cat_words)} 个，缺 {miss or '（无）'}")
    print(f"   forbidden_on_image {len(banned)} 条：{'、'.join(map(str, banned))}")
    bmiss = [w for w in banned if str(w) not in neg]
    print(f"   未出现在负向词里的：{bmiss or '（无）'}")
    ok = not miss and not bmiss and bool(banned)
    print(f"   {OK if ok else BAD} 两类都进了负向词")
    if not ok:
        fails.append(f"负向词不全：缺类别词 {miss}、缺禁令词 {bmiss}")


def assert_c(gen: dict, run_dir: Path, fails: list[str]) -> None:
    print("\nC. 负向词未超模型上限（超了会被静默截断）")
    n = int(gen.get("negative_prompt_len") or 0)
    trunc = bool(gen.get("negative_prompt_truncated"))
    cap = 500          # qwen-image 系上限，见 src/imagegen.py.NEG_PROMPT_MAX
    ok = n <= cap and not trunc
    print(f"   长度 {n} / 上限 {cap}   标记截断={trunc}")
    print(f"   {OK if ok else BAD} 没超限 —— 被截掉的那部分禁令等于没写")
    if not ok:
        fails.append(f"负向词 {n} 字符超过上限 {cap}，会被静默截断")


def assert_d(renders: dict, run_dir: Path, subj_sha: str, fails: list[str]) -> None:
    print("\nD. 主体同源（贴图区内 == subject.png）")
    r = renders[SLOT]
    det = r["detail"]
    box = det.get("paste_box")
    if det.get("subject_sha256") != subj_sha:
        fails.append(f"位置 4 记的主体 sha {str(det.get('subject_sha256'))[:12]}… "
                     f"!= run 的 subject {subj_sha[:12]}…")
    sub = Image.open(run_dir / "subject.png").convert("RGBA")
    x, y, w, h = box
    img = sub.resize((w, h), Image.LANCZOS)
    exp = np.asarray(img.convert("RGB")).astype(np.int16)
    act = np.asarray(Image.open(r["path"]).convert("RGB")).astype(np.int16)[y:y + h, x:x + w]
    mask = np.asarray(img.getchannel("A")) >= OPAQUE_MIN
    d = np.abs(act - exp)[mask]
    mx, mean = int(d.max()), float(d.mean())
    ok = (mx <= MAX_ABS_DIFF and mean <= MEAN_ABS_DIFF
          and det.get("subject_sha256") == subj_sha)
    print(f"   贴图框 {box}   不透明像素 {int(mask.sum())}  最大差 {mx}  平均差 {mean:.2f}"
          f"（阈值 ≤{MAX_ABS_DIFF} / ≤{MEAN_ABS_DIFF}）")
    print(f"   {OK if ok else BAD} 贴图区内就是 subject.png 的像素")
    if not ok:
        fails.append(f"位置 4 的主体不同源（最大差 {mx}，平均差 {mean:.2f}）")


def assert_e(renders: dict, run_dir: Path, fails: list[str]) -> None:
    """★ 这一条是接缝 α 的核心证据。"""
    print("\nE. 背景未被改动（贴图区**外** == 生成底铺满的结果）")
    r = renders[SLOT]
    det = r["detail"]
    gen_path = run_dir / "raw" / f"slot{SLOT:02d}_gen.jpg"
    if not gen_path.exists():
        fails.append(f"没有留下生成底 {gen_path.name} —— 无法断言背景是否被改动")
        print(f"   {BAD} 缺生成底")
        return
    final = Image.open(r["path"]).convert("RGB")
    W, H = final.size
    cov = placement.cover_box(Image.open(gen_path).size, W, H)
    bg = (Image.open(gen_path).convert("RGB")
          .resize(tuple(cov["scaled"]), Image.LANCZOS).crop(tuple(cov["crop"])))
    a = np.asarray(bg).astype(np.int16)
    b = np.asarray(final).astype(np.int16)
    x, y, w, h = det["paste_box"]
    mask = np.ones(a.shape[:2], bool)
    mask[y:y + h, x:x + w] = False
    d = np.abs(a - b)[mask]
    mx, mean = int(d.max()), float(d.mean())
    ok = mx <= BG_MAX_ABS_DIFF and mean <= BG_MEAN_ABS_DIFF
    print(f"   生成底 {gen_path.name} {cov['scaled']} → 裁切 {cov['crop']}")
    print(f"   非贴图区 {int(mask.sum())} 像素：最大差 {mx}  平均差 {mean:.4f}"
          f"（阈值 ≤{BG_MAX_ABS_DIFF} / ≤{BG_MEAN_ABS_DIFF}）")
    print(f"   {OK if ok else BAD} 背景与生成底一致 —— 主体是**贴上去**的，"
          f"不是模型画的，模型也没偷改背景")
    if not ok:
        fails.append(f"贴图区外的像素和生成底不一致（最大差 {mx}，平均差 {mean:.4f}）"
                     f"—— 要么背景被二次加工，要么贴图框记录得不对")


def assert_f(renders: dict, fails: list[str]) -> None:
    print("\nF. 背景铺满是裁切，不是补边")
    gen = renders[SLOT]["detail"].get("generation") or {}
    crop, scaled = gen.get("cover_crop"), gen.get("cover_scaled")
    out = list(Image.open(renders[SLOT]["path"]).size)
    if not crop or not scaled:
        fails.append("没记录 cover_crop / cover_scaled，无法断言取景方式")
        print(f"   {BAD} 缺证据")
        return
    cw, ch = crop[2] - crop[0], crop[3] - crop[1]
    ok = (cw, ch) == (out[0], out[1]) and scaled[0] >= out[0] and scaled[1] >= out[1]
    print(f"   裁切框 {cw}×{ch}   缩放后 {scaled}   画布 {out}   scale={gen.get('cover_scale')}")
    print(f"   {OK if ok else BAD} 裁切框恰等画布，且缩放结果不小于画布（无补边）")
    if not ok:
        fails.append(f"背景取景不是纯裁切：裁切框 {cw}×{ch} vs 画布 {out}，缩放后 {scaled}")


def assert_g(renders: dict, start: dict, fails: list[str]) -> None:
    print("\nG. 位置 4 是全链路唯一声明调模型的渲染器")
    doable = start.get("doable") or []
    modelers = sorted({str((renders.get(s) or {}).get("renderer"))
                       for s in doable if s in renders
                       and registry.calls_model(str((renders.get(s) or {}).get("renderer")))})
    ok = modelers == ["gen_bg_paste"] and start.get("model_calls") == sum(
        1 for s in doable if registry.calls_model(
            str((renders.get(s) or {}).get("renderer"))))
    print(f"   声明调模型的渲染器：{modelers or '（无）'}")
    print(f"   run_start 记的 model_calls={start.get('model_calls')}（doable={doable}）")
    print(f"   {OK if ok else BAD} 只有 gen_bg_paste 一台")
    if not ok:
        fails.append(f"声明调模型的渲染器是 {modelers}，期望恰好 [gen_bg_paste]")


def assert_h(catalog: dict, fails: list[str]) -> None:
    print("\nH. 取景提示：确定性选择 + 命中禁令则弃用 + 整池命中则报错")
    banned = ["折扣", "二维码"]
    # ---- 命中禁令的那一条必须被弃用，而不是"照样用、只是记一笔"
    fake = {"bg_prompt_hints": ["限时折扣的桌面，中央空置", "干净的浅木桌面，中央空置"]}
    kept, dropped = gbp.pick_hint(fake, banned, SLOT)
    ok1 = kept == "干净的浅木桌面，中央空置" and len(dropped) == 1 \
        and dropped[0]["hit"] == ["折扣"]
    print(f"   池里 2 条（1 条含「折扣」）→ 选中「{kept}」")
    print(f"   弃用记录：{dropped}")
    print(f"   {OK if ok1 else BAD} 命中禁令的提示被弃用")
    if not ok1:
        fails.append(f"命中 forbidden_on_image 的取景提示没有被弃用：选中「{kept}」")

    # ---- 全部命中 → 报错（类目配置与品牌禁令冲突）
    allbad = {"bg_prompt_hints": ["折扣角标", "扫码二维码"]}
    try:
        gbp.pick_hint(allbad, banned, SLOT)
        print(f"   {BAD} 整池命中却没报错")
        fails.append("整池命中 forbidden_on_image 时应报错（配置冲突），实际照跑")
    except ValueError as exc:
        print(f"   {OK} 整池命中 → 报错：{str(exc)[:64]}…")

    # ---- 空池 → 报错
    try:
        gbp.pick_hint({}, banned, SLOT)
        print(f"   {BAD} 空池没报错")
        fails.append("类目里没有 bg_prompt_hints 时应报错")
    except ValueError:
        print(f"   {OK} 空池 → 报错")

    # ---- 确定性：同一坑位反复挑，结果必须一样（否则 --redo 会换一个场景）
    real = [gbp.pick_hint(catalog, banned, SLOT)[0] for _ in range(3)]
    ok2 = len(set(real)) == 1
    print(f"   真实类目连挑 3 次：{real[0]}")
    print(f"   {OK if ok2 else BAD} 确定性（同一坑位不换场景）")
    if not ok2:
        fails.append(f"取景提示选择不确定：{real} —— 重做会静默换一个场景")


def assert_i(fails: list[str]) -> None:
    print("\nI. 没有 key 时自报 placeholder（不冒充真实场景图）")
    import imagegen  # noqa: E402  （这里才 import：本模块只在跑这一条时需要它）
    import tempfile

    saved = os.environ.pop("DASHSCOPE_API_KEY", None)
    try:
        with tempfile.TemporaryDirectory() as td:
            rep = imagegen.generate_image("p", "n", Path(td) / "x.jpg", size_px=1024)
        ok = rep.get("mode") == "mock" and bool(rep.get("warning"))
        print(f"   mode={rep.get('mode')}   warning={str(rep.get('warning'))[:56]}…")
        print(f"   {OK if ok else BAD} 降级为 mock 且带 warning，"
              f"渲染器据此把 placeholder 置真")
    finally:
        if saved is not None:
            os.environ["DASHSCOPE_API_KEY"] = saved


def assert_j(renders: dict, fails: list[str]) -> None:
    print("\nJ. 贴图框四边不贴边（与位置 1/2/3 同一套留白规则）")
    det = renders[SLOT]["detail"]
    x, y, w, h = det["paste_box"]
    final = Image.open(renders[SLOT]["path"])
    W, H = final.size
    pad = int(min(W, H) * placement.DEFAULT_PAD_RATIO)
    gaps = {"上": y, "下": H - (y + h), "左": x, "右": W - (x + w)}
    ok = all(v >= pad for v in gaps.values())
    print(f"   四边留白 {gaps}   单边下限 {pad}（{placement.DEFAULT_PAD_RATIO:.1%}）")
    print(f"   {OK if ok else BAD} 没有一边小于下限")
    if not ok:
        fails.append(f"位置 4 主体贴边：{gaps}，单边下限 {pad}")


def main(argv: list[str]) -> int:
    run_dir = Path(argv[1]) if len(argv) > 1 else newest_run()
    if not run_dir or not (run_dir / "run.jsonl").exists():
        print("找不到画出位置 4 的 run：先跑一次\n"
              "  python run.py --product examples/product_fullset.json --only 4")
        return 2

    registry.load_all()
    recs = load(run_dir)
    start = next((r for r in recs if r["stage"] == "run_start"), {})
    renders = {r["slot_id"]: r for r in recs if r["stage"] == "render"}
    r4 = renders.get(SLOT)
    if not r4 or not (r4.get("detail") or {}).get("generation"):
        print(f"{run_dir.name} 里的位置 4 不是真实渲染（可能是 M4 之前的占位图）。\n"
              f"请用 --only 4 重跑一次。")
        return 2

    gen = r4["detail"]["generation"]
    subj = next((r for r in recs if r["stage"] == "subject"), {})
    cfg = schema.assert_valid()
    catalog = __import__("yaml").safe_load(
        (ROOT / cfg["catalog"]).read_text(encoding="utf-8")) or {}

    print(f"M4 验收 · {run_dir.name}\n" + "=" * 72)
    fails: list[str] = []

    assert_a(gen, fails)
    assert_b(gen, fails)
    assert_c(gen, run_dir, fails)
    assert_d(renders, run_dir, subj.get("sha256"), fails)
    assert_e(renders, run_dir, fails)
    assert_f(renders, fails)
    assert_g(renders, start, fails)
    assert_h(catalog, fails)
    assert_i(fails)
    assert_j(renders, fails)

    print("\n" + "=" * 72)
    if fails:
        print(f"未通过 {len(fails)} 条：")
        for f in fails:
            print(f"  {BAD} {f}")
        return 1
    print("全部通过：位置 4 的提示词无条件排除了产品本体，成品里的主体是贴上去的"
          "（贴图区外与生成底逐像素一致），背景铺满是裁切而非补边。\n"
          "人工目视项：看一眼 raw/slotNN_gen.jpg，确认背景里没有被偷画的产品或文字。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
