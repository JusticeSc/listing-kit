"""把 B 臂与 E 臂放大并排：判「两段式色块边界 / 盖结构 / 表面纹理」有没有差别。

为什么必须放大：上一轮已经栽过一次 —— 从缩略图看不出色块边界，
而"缩略图上下大结论"正是本项目记过账的错误形态。三列同高、同裁切比例，才可比。
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

KIT = Path("E:/workbuddy_workspace/2026-09-20-16-38-19/amz-listing-kit")
ROOT = KIT / "evals/probes/lock_out"
REF = KIT / "examples/input/cup_source.jpg"

COLS = [
    ("SOURCE 源图", REF),
    ("臂 B · 本品逐特征枚举 820 字", ROOT / "enumerated_qwen-image-2.0-pro/qwen-image-2.0-pro_r1.png"),
    ("臂 E · 类目级通用枚举（无本品数值）", ROOT / "libb_class_generic_qwen-image-2.0-pro/qwen-image-2.0-pro_r1.png"),
]

CELL, BAR = 430, 44
# 裁切：画面中央 52% 宽 / 66% 高（三张都是居中构图），保证同比例同位置
CW, CH = 0.52, 0.66


def font(sz: int):
    for p in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
              "C:/Windows/Fonts/arial.ttf"):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                continue
    return ImageFont.load_default()


F_TAG, F_SMALL = font(16), font(13)
ims = []
for label, p in COLS:
    im = Image.open(p).convert("RGB")
    W, H = im.size
    x0, y0 = int(W * (1 - CW) / 2), int(H * (1 - CH) / 2)
    im = im.crop((x0, y0, x0 + int(W * CW), y0 + int(H * CH)))
    ims.append(im.resize((CELL, int(CELL * im.height / im.width)), Image.LANCZOS))

h = max(i.height for i in ims) + BAR
sheet = Image.new("RGB", (CELL * len(ims) + 4, h), (246, 246, 248))
d = ImageDraw.Draw(sheet)
for i, ((label, _), im) in enumerate(zip(COLS, ims)):
    x = i * (CELL + 1)
    sheet.paste(im, (x, BAR))
    d.text((x + 8, 6), label, fill=(25, 25, 25), font=F_TAG)
    d.text((x + 8, 25), "数一数：深色段占几成？盖有几层？表面压纹在不在？", fill=(125, 125, 125), font=F_SMALL)
    if i:
        d.line([(x - 2, 0), (x - 2, h)], fill=(200, 200, 205), width=2)

out = ROOT / "zoom_B_vs_E.jpg"
sheet.save(out, "JPEG", quality=94)
print(f"{out}  {sheet.size}")
