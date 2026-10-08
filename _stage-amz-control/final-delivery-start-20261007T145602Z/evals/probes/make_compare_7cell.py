"""两张七格对照图：SOURCE 固定在最左，右侧 3+3 —— 一次只看一个变量。

图 1 `compare_compiler.jpg`  ：臂 B（人手写 820 字） vs 臂 D（通用编译器 + 本域 context）
    单变量 = "锁段由谁写"。两臂的参考图 / 场景段 / 负面词 / 模型 / n / size 全同。
图 2 `compare_extend.jpg`    ：臂 B（prompt_extend=false） vs 臂 B（prompt_extend=true）
    单变量 = prompt_extend 开不开。**这是 src/imagegen.py:82 的生产默认值**。

为什么必须把 SOURCE 放在每一张图的最左列：这个实验唯一要人判的事是
「产物里那件商品还是不是源图那件」。同图可见，比对才成立。
标签中性、留签字栏 —— 机器判不了的项要求签字（照 E0 的 ATTEST_ITEMS 纪律）。
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

KIT = Path("E:/workbuddy_workspace/2026-09-20-16-38-19/amz-listing-kit")
REF = KIT / "examples/input/cup_source.jpg"
ROOT = KIT / "evals/probes/lock_out"
M = "qwen-image-2.0-pro"

SHEETS = [
    ("compare_compiler.jpg", "臂 B 人手写 820 字",
     ROOT / f"enumerated_{M}", "臂 D 通用编译器 L1+L2",
     ROOT / f"d_compiler_{M}"),
    ("compare_extend.jpg", "臂 B  prompt_extend = false",
     ROOT / f"enumerated_{M}", "臂 B  prompt_extend = true（生产默认）",
     ROOT / f"extend_{M}"),
]

CELL, BAR, GUT = 350, 48, 6


def font(sz: int):
    for p in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                continue
    return ImageFont.load_default()


F_TAG, F_SMALL = font(16), font(12)


def cell(p: Path) -> Image.Image:
    im = Image.open(p).convert("RGB")
    return im.resize((CELL, int(CELL * im.height / im.width)), Image.LANCZOS)


for out_name, lab_l, dir_l, lab_r, dir_r in SHEETS:
    left = sorted(dir_l.glob("*_r*.png"))
    right = sorted(dir_r.glob("*_r*.png"))
    missing = [f"{lab}: {d.name} 里只有 {len(fs)} 张"
               for lab, fs, d in ((lab_l, left, dir_l), (lab_r, right, dir_r)) if len(fs) < 3]
    if missing:
        raise SystemExit("产物不齐，不生成对照图：\n  " + "\n  ".join(missing))

    ref = cell(REF)
    ims = [cell(p) for p in left[:3] + right[:3]]
    rh = max([ref.height] + [i.height for i in ims]) + BAR
    cols = 7                                    # SOURCE + 3 + 3
    W = CELL * cols + GUT * (cols + 1)
    H = rh + GUT * 2
    sheet = Image.new("RGB", (W, H), (244, 244, 246))
    d = ImageDraw.Draw(sheet)
    d.rectangle([GUT, GUT, W - GUT, GUT + rh], fill=(255, 255, 255), outline=(214, 214, 218))

    sheet.paste(ref, (GUT + 8, GUT + BAR))
    d.text((GUT + 10, GUT + 8), "SOURCE  源图", fill=(30, 30, 30), font=F_TAG)
    d.text((GUT + 10, GUT + 28), "待复现的那件商品", fill=(130, 130, 130), font=F_SMALL)

    for ci, im in enumerate(ims):
        x = GUT + (ci + 1) * (CELL + GUT)
        if ci == 3:                              # 两组之间加一条粗分隔线
            d.line([(x - GUT // 2, GUT), (x - GUT // 2, GUT + rh)], fill=(40, 40, 40), width=3)
        sheet.paste(im, (x, GUT + BAR))
        label = lab_l if ci < 3 else lab_r
        d.text((x + 8, GUT + 8), label, fill=(30, 30, 30), font=F_TAG)
        d.text((x + 8, GUT + 28), f"#{ci % 3 + 1}   判：[ ] 商品一致   [ ] 被改",
               fill=(120, 120, 120), font=F_SMALL)

    out = ROOT / out_name
    sheet.save(out, "JPEG", quality=92)
    print(f"{out}  {sheet.size}")
