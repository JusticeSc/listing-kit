"""dHash 度量校准 —— 它到底在测主体，还是在测背景？

背景
----
`lock_probe.py` 用 `dhash()` / `hamming()` 产出 `pairwise_hamming` 与
`vs_source_hamming`，这批数字**被当成「商品有没有被改」的佐证引用过**
（臂 A `133·106·69` vs 臂 B `91·31·82`）。

但 `dhash()` 把整张 1600×1600 缩到 17×16 —— 它是**全局低频结构**的度量。
真实产物的差异里同时含三种成分：背景变了 + 机位变了 + 商品可能变了。
dHash 把三者**加在一起**，无法分离。

这是"判据本身要被校准"的又一次应用。拿没校准过的量当证据，
和 v1 的假校验（`no_watermark`）同类，只是更隐蔽 —— **它不报错，它给数字**。

三个离线实验（零调用、零成本）
------------------------------
A 敏感度定位：4×4 分块，逐块填灰，量 dHash 变化 → "dHash 关注哪里、是否均匀"
B 区域对照：主体矩形填灰 vs **背景的三种逼真变化**（填灰 / 换浅色 / 高斯模糊）
C 真实判别力：18 张真实生成图（人眼已知 4 臂被改 / 3 臂守住）→ 全图 dHash 能否分开

判据（可证伪）
--------------
- C：若「被改」组与「守住」组的 `vs_source` 区间**重叠** ⇒ 无判别力，数字不得用作证据。
- B：若背景的**逼真**变化（不是填灰这种大反差）也能产生 C 测到的那种量级的位移
  ⇒ 说明该距离主要由背景贡献，不能归因于商品。

顺带记录（不判好坏）
--------------------
`cup_source.jpg` 右下角有 "AI生成 WORKBUDDY" 水印 —— 它是本项目**所有实验的参考图**，
而按 `src/intake.py` 的 E0 规则（`ATTEST_ITEMS` 含水印）它本应被拒收。
记下来：本实验的参考图是**最坏情况样本**（带水印、带道具条纹布）。

用法
----
    python evals/probes/dhash_calib.py
退出码：0 跑完（不判好坏，结论由数字与图给出）· 4 自洽性断言失败
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
KIT = HERE.parent.parent
sys.path.insert(0, str(HERE))
import lock_probe as lp  # 单一出处：复用 dhash / hamming

REF = KIT / "examples" / "input" / "cup_source.jpg"
DEFAULT_OUT = HERE / "calib_out"
GRAY = (128, 128, 128)
BG_LIGHT = (235, 228, 215)   # 从参考图四角取样的浅色，模拟"换成浅色厨房"

# 主体近似矩形（归一化）—— **人工从图上量的**，会画在图上供核对。
# 杯子：水平约 34%–63%，垂直约 5%–92%，放宽一点。
SUBJECT_RECT = (0.32, 0.04, 0.66, 0.94)

ARM_FILES = {
    "advice": [f"advice_qwen-image-2.0-pro/qwen-image-2.0-pro_r{i}.png" for i in (1, 2, 3)],
    "enumerated": [f"enumerated_qwen-image-2.0-pro/qwen-image-2.0-pro_r{i}.png" for i in (1, 2, 3)],
    "c_text": [f"c_text_qwen-image-2.0-pro/qwen-image-2.0-pro_r{i}.png" for i in (1, 2, 3)],
    "c_vision": [f"c_vision_qwen-image-2.0-pro/qwen-image-2.0-pro_r{i}.png" for i in (1, 2, 3)],
    "d_compiler": [f"d_compiler_qwen-image-2.0-pro/qwen-image-2.0-pro_r{i}.png" for i in (1, 2, 3)],
    "extend": [f"extend_qwen-image-2.0-pro/qwen-image-2.0-pro_r{i}.png" for i in (1, 2, 3)],
}
# 人眼判决（**判断，不是测量**，图见 <out>/c_real_data.jpg，留给你核对）
HUMAN_VERDICT = {
    "advice": "altered(2/3 长出源图没有的把手)",
    "enumerated": "held",
    "c_text": "altered(3/3 丢棕色矮套)",
    "c_vision": "held",
    "d_compiler": "held",
    "extend": "held",
}


def dhash_of(im: Image.Image, bits: int = 16) -> list[int]:
    """与 `lp.dhash()` 等价的**内存版**。等不等价由 `self_check()` 断言。"""
    g = im.convert("L").resize((bits + 1, bits), Image.LANCZOS)
    px = list(g.getdata())
    row = bits + 1
    return [int(px[y * row + x] > px[y * row + x + 1]) for y in range(bits) for x in range(bits)]


def self_check() -> None:
    """自洽性：内存版必须与共享版逐位相同（否则本脚本的一切数字都不算数）。"""
    a, b = dhash_of(Image.open(REF)), lp.dhash(REF)
    if a != b:
        n = sum(1 for x, y in zip(a, b) if x != y)
        raise SystemExit(f"[x] 自洽性失败：内存版与 lp.dhash 有 {n}/256 位不同 —— 数字不可用")
    print(f"[ok] 自洽性：内存版 dhash 与共享版 lp.dhash 逐位一致（{len(a)} bits）")


def rect_px(rect, size) -> tuple[int, int, int, int]:
    W, H = size
    return (int(rect[0] * W), int(rect[1] * H), int(rect[2] * W), int(rect[3] * H))


def exp_a_grid(im: Image.Image, k: int = 4) -> dict:
    base = dhash_of(im)
    W, H = im.size
    rows: list[list[int]] = []
    for gy in range(k):
        row = []
        for gx in range(k):
            box = (W * gx // k, H * gy // k, W * (gx + 1) // k, H * (gy + 1) // k)
            im2 = im.copy()
            ImageDraw.Draw(im2).rectangle(box, fill=GRAY)
            row.append(lp.hamming(base, dhash_of(im2)))
        rows.append(row)
    flat = [v for r in rows for v in r]
    return {"grid": rows, "k": k, "min": min(flat), "max": max(flat),
            "mean": round(sum(flat) / len(flat), 1),
            "note": "均匀 = 没有热点 = 对任一局部都不特别敏感；它反映全局纹理/结构"}


def exp_b_region(im: Image.Image, rect=SUBJECT_RECT) -> dict:
    """B · 主体区域 vs 背景，各自三种改法。**面积一并报出**，否则无法署名。"""
    base = dhash_of(im)
    W, H = im.size
    bx = rect_px(rect, (W, H))
    subj_area = ((bx[2] - bx[0]) * (bx[3] - bx[1])) / (W * H)

    def ring_edit(fn):
        im2 = im.copy()
        mask = Image.new("L", (W, H), 255)
        ImageDraw.Draw(mask).rectangle(bx, fill=0)
        patch = fn(im.copy())
        im2.paste(patch, (0, 0), mask)
        return lp.hamming(base, dhash_of(im2))

    def subject_gray():
        im2 = im.copy()
        ImageDraw.Draw(im2).rectangle(bx, fill=GRAY)
        return lp.hamming(base, dhash_of(im2))

    def all_gray():
        im2 = im.copy()
        ImageDraw.Draw(im2).rectangle((0, 0, W, H), fill=GRAY)
        return lp.hamming(base, dhash_of(im2))

    ring_gray = ring_edit(lambda x: Image.new("RGB", (W, H), GRAY))
    ring_light = ring_edit(lambda x: Image.new("RGB", (W, H), BG_LIGHT))
    ring_blur = ring_edit(lambda x: x.filter(ImageFilter.GaussianBlur(24)))

    res = {
        "subject_rect_px": list(bx),
        "subject_area_fraction": round(subj_area, 3),
        "hamming_subject_gray": subject_gray(),
        "hamming_ring_gray": ring_gray,
        "hamming_ring_light": ring_light,
        "hamming_ring_blur": ring_blur,
        "hamming_all_gray": all_gray(),
    }
    # 每单位面积的位移（面积不同，不归一就不能比）
    res["per_area_subject"] = round(res["hamming_subject_gray"] / subj_area, 1)
    res["per_area_ring_light"] = round(res["hamming_ring_light"] / (1 - subj_area), 1)
    return res


def exp_c_real(lo: Path) -> list[dict]:
    ref_im = Image.open(REF)
    W0, H0 = ref_im.size
    src_full = dhash_of(ref_im)
    src_c = dhash_of(ref_im.crop((W0 // 4, H0 // 4, W0 * 3 // 4, H0 * 3 // 4)))
    out = []
    for arm, names in ARM_FILES.items():
        for nm in names:
            p = lo / nm
            if not p.exists():
                continue
            im = Image.open(p)
            W, H = im.size
            cen = lp.hamming(dhash_of(im.crop((W // 4, H // 4, W * 3 // 4, H * 3 // 4))), src_c)
            out.append({"arm": arm, "rel": nm, "file": p.name, "human": HUMAN_VERDICT[arm],
                        "vs_source_full": lp.hamming(dhash_of(im), src_full),
                        "vs_source_center_crop": cen})
    return out


def poll_position_bias(rows: list[dict]) -> dict:
    """同臂内哪一张的 `vs_source` 最大？若恒定落在同一个位置，说明 n>1 的候选不同分布。"""
    from collections import Counter
    top = Counter()
    detail = {}
    for arm in ARM_FILES:
        v = [(r["file"], r["vs_source_full"]) for r in rows if r["arm"] == arm]
        if not v:
            continue
        # 文件名 "..._r2.png" → 位置序号
        best = max(v, key=lambda t: t[1])
        pos = best[0].rsplit("_r", 1)[1].split(".")[0]
        top[pos] += 1
        detail[arm] = {"argmax_pos": pos, "values": [x[1] for x in v]}
    return {"argmax_position_counter": dict(top), "n_arms": len(detail), "detail": detail}


def draw_report(im: Image.Image, ga: dict, gb: dict, out: Path) -> Path:
    W, H = im.size
    cell = 700
    canvas = Image.new("RGB", (cell * 2, cell + 64), (255, 255, 255))
    d = ImageDraw.Draw(canvas)

    left = im.copy().resize((cell, cell), Image.LANCZOS)
    dl = ImageDraw.Draw(left)
    k = ga["k"]
    for i in range(1, k):
        dl.line([(cell * i // k, 0), (cell * i // k, cell)], fill=(210, 60, 60), width=2)
        dl.line([(0, cell * i // k), (cell, cell * i // k)], fill=(210, 60, 60), width=2)
    for gy in range(k):
        for gx in range(k):
            v = ga["grid"][gy][gx]
            dl.text((cell * gx // k + 10, cell * gy // k + 10), str(v), fill=(255, 255, 255))
            dl.text((cell * gx // k + 11, cell * gy // k + 11), str(v), fill=(190, 30, 30))
    canvas.paste(left, (0, 64))
    d.text((10, 8), "A · 4x4 grid: dHash bits changed when that cell is greyed out", fill=(15, 15, 15))
    d.text((10, 30), f"min={ga['min']}  mean={ga['mean']}  max={ga['max']}   (all /256)", fill=(20, 90, 200))
    d.text((10, 46), "flat = no hotspot = it measures global texture, not one object", fill=(110, 110, 110))

    right = im.copy().resize((cell, cell), Image.LANCZOS)
    dr = ImageDraw.Draw(right)
    sx0, sy0, sx1, sy1 = rect_px(SUBJECT_RECT, (cell, cell))
    dr.rectangle((0, 0, cell - 1, cell - 1), outline=(0, 150, 80), width=3)
    dr.rectangle((sx0, sy0, sx1, sy1), outline=(20, 90, 200), width=4)
    canvas.paste(right, (cell, 64))
    d.text((cell + 10, 8), "B · alter SUBJECT (blue box) vs alter BACKGROUND (green)", fill=(15, 15, 15))
    d.text((cell + 10, 28), f"subject area {gb['subject_area_fraction']:.0%} -> grey   {gb['hamming_subject_gray']}/256"
                           f"   ({gb['per_area_subject']}/area)", fill=(20, 90, 200))
    d.text((cell + 10, 44), f"bg -> grey    {gb['hamming_ring_gray']}/256   ({gb['per_area_ring_light']} style)", fill=(0, 130, 70))
    d.text((cell + 10, 60), f"bg -> light   {gb['hamming_ring_light']}/256     bg -> blurred {gb['hamming_ring_blur']}/256", fill=(0, 130, 70))
    canvas.save(out, "JPEG", quality=92)
    return out


def draw_real(rows: list[dict], out: Path) -> Path:
    cell, bar = 300, 76
    n = len(rows) + 1
    sheet = Image.new("RGB", (cell * n, cell + bar), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    ref = Image.open(REF).convert("RGB").resize((cell, cell), Image.LANCZOS)
    sheet.paste(ref, (0, bar))
    d.text((8, 7), "SOURCE  cup_source.jpg", fill=(15, 15, 15))
    d.text((8, 26), "the product to reproduce", fill=(110, 110, 110))
    d.text((8, 44), "(carries an AI watermark, bottom-right)", fill=(150, 90, 20))
    for i, r in enumerate(rows, start=1):
        stem = r["file"].rsplit("_r", 1)[1].split(".")[0]
        im = Image.open(KIT / "evals/probes/lock_out" / r["rel"]).convert("RGB").resize((cell, cell), Image.LANCZOS)
        sheet.paste(im, (i * cell, bar))
        d.text((i * cell + 8, 7), f"{r['arm']}  #{stem}", fill=(15, 15, 15))
        d.text((i * cell + 8, 26), f"human: {r['human']}", fill=(150, 20, 20) if "altered" in r["human"] else (20, 110, 40))
        d.text((i * cell + 8, 44), f"full dHash  {r['vs_source_full']}/256", fill=(60, 60, 60))
        d.text((i * cell + 8, 60), f"center-only {r['vs_source_center_crop']}/256", fill=(60, 60, 60))
        d.line([(i * cell, 0), (i * cell, cell + bar)], fill=(210, 210, 210), width=1)
    d.line([(cell, 0), (cell, cell + bar)], fill=(40, 40, 40), width=3)
    sheet.save(out, "JPEG", quality=90)
    return out


def draw_watermark(im: Image.Image, out: Path) -> Path:
    """右下角 2× 放大 —— 核对参考图自带的水印（E0 的签字项之一）。"""
    W, H = im.size
    box = (int(W * 0.62), int(H * 0.86), W, H)
    crop = im.crop(box).resize(((box[2] - box[0]) * 2, (box[3] - box[1]) * 2), Image.LANCZOS)
    crop.save(out, "JPEG", quality=95)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="dHash 度量校准（离线，零调用）")
    ap.add_argument("--image", default=str(REF))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--grid", type=int, default=4)
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    self_check()

    im = Image.open(args.image).convert("RGB")
    ga = exp_a_grid(im, args.grid)
    print("\nA · 4x4 敏感度（每格填灰后 dHash 变化 /256）")
    for gy, row in enumerate(ga["grid"]):
        print("   " + "  ".join(f"{v:3d}" for v in row) + f"   <- row{gy}")
    print(f"   min={ga['min']} mean={ga['mean']} max={ga['max']}  ← 均匀=无热点")

    gb = exp_b_region(im)
    print("\nB · 改主体 vs 改背景（主体框画在 ab_sensitivity.jpg 上，请核对）")
    print(f"   主体区域（面积 {gb['subject_area_fraction']:.0%}）填灰 → {gb['hamming_subject_gray']}/256"
          f"   每面积 {gb['per_area_subject']}")
    print(f"   背景填灰                                  → {gb['hamming_ring_gray']}/256")
    print(f"   背景**换浅色**（逼真：米墙木台 → 浅厨房）  → {gb['hamming_ring_light']}/256"
          f"   每面积 {gb['per_area_ring_light']}")
    print(f"   背景**高斯模糊**（逼真：虚化背景）          → {gb['hamming_ring_blur']}/256")
    print(f"   全图填灰（上界）                           → {gb['hamming_all_gray']}/256")

    rows = exp_c_real(HERE / "lock_out")
    print("\nC · 真实产物（人眼判决 vs 两个 dHash 变量）")
    print(f"   {'arm':12s} {'#':2s} {'human':36s} {'full':>5s} {'center':>7s}")
    for r in rows:
        i = r["file"].rsplit("_r", 1)[1].split(".")[0]
        print(f"   {r['arm']:12s} {i:2s} {r['human']:36s} {r['vs_source_full']:5d} {r['vs_source_center_crop']:7d}")

    def rng(arms):
        v = [r["vs_source_full"] for r in rows if r["arm"] in arms]
        return (min(v), max(v)) if v else (0, 0)
    altered = [a for a, v in HUMAN_VERDICT.items() if "altered" in v]
    held = [a for a, v in HUMAN_VERDICT.items() if v == "held"]
    ra, rh = rng(altered), rng(held)
    overlap = not (ra[0] > rh[1] or rh[0] > ra[1])
    print(f"\n   人眼已知被改的臂 full dHash 区间 {ra}（{len(altered)} 臂）")
    print(f"   守住的臂              {rh}（{len(held)} 臂）")
    print(f"   ⇒ {'**重叠 ⇒ 全图 dHash 无判别力**' if overlap else '不重叠'}")

    bias = poll_position_bias(rows)
    print(f"\n   同臂内 vs_source 最大的位置分布：{bias['argmax_position_counter']}"
          f"（共 {bias['n_arms']} 臂）")
    for arm, dd in bias["detail"].items():
        print(f"     {arm:12s} argmax=#{dd['argmax_pos']}  values={dd['values']}")

    p1 = draw_report(im, ga, gb, out_dir / "ab_sensitivity.jpg")
    p2 = draw_real(rows, out_dir / "c_real_data.jpg")
    p3 = draw_watermark(im, out_dir / "source_watermark_2x.jpg")
    rep = {"probe": "dhash_calib", "purpose": "dHash 测主体还是背景（离线校准）",
           "reference": str(args.image), "reference_size": list(im.size),
           "subject_rect_norm": list(SUBJECT_RECT),
           "exp_a_grid": ga, "exp_b_region": gb, "exp_c_real": rows,
           "c_overlap_check": {"altered_range": list(ra), "held_range": list(rh),
                               "ranges_overlap": overlap},
           "position_bias": bias,
           "notes": ["参考图右下角自带 AI 水印 —— 按 src/intake.py 的 E0 规则本应被拒收；"
                     "本实验的参考图是最坏情况样本（带水印 + 带道具条纹布）",
                     "human 列是判断不是测量，图在 c_real_data.jpg，留给你核对"],
           "drawings": [str(p1), str(p2), str(p3)]}
    (out_dir / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8")
    print(f"\n[ok] 落盘 {out_dir/'report.json'}")
    for p in (p1, p2, p3):
        print(f"     {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
