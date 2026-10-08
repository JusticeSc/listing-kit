"""中文笔画核对图 —— 把三张生成图里卡片所在区域放大并排，逐字核对。

为什么需要这一张：v4 删掉了不变量 C（文字不再由字体绘制，交给模型画），
所以"中文字写得对不对"从"不相关"变成"要不要人工逐字核对"的前提。
库 B `TEXT_RENDER`（`generate.py:418-425`）明写指定中文字体族，
库 C 要求 200% 人工核对 —— **两个库都画中文，但都无程序保证**。
所以这张图的用途是：给人工提供一个能看清笔画的视图。**判断项在人。**
"""
from pathlib import Path

from PIL import Image, ImageDraw

KIT = Path(__file__).resolve().parents[2]
LO = KIT / "evals" / "probes" / "lock_out"
SRC = LO / "cn_text_qwen-image-2.0-pro"
OUT = LO / "cn_text_zoom.jpg"

# 卡片在画面右下（场景段如此指定）。取右下角一块放大，兼顾"字能否看清"与"是否被裁掉"。
CROP_NORM = (0.52, 0.50, 1.00, 0.95)
ZOOM = 3

names = [SRC / f"qwen-image-2.0-pro_r{i}.png" for i in (1, 2, 3)]
ims = []
for p in names:
    im = Image.open(p).convert("RGB")
    W, H = im.size
    box = (int(CROP_NORM[0] * W), int(CROP_NORM[1] * H), int(CROP_NORM[2] * W), int(CROP_NORM[3] * H))
    c = im.crop(box)
    c = c.resize((c.width * ZOOM // 2, c.height * ZOOM // 2), Image.LANCZOS)  # 3x 相对缩略图
    ims.append(c)

cell_h = max(i.height for i in ims) + 60
cell_w = max(i.width for i in ims) + 16
sheet = Image.new("RGB", (cell_w * len(ims), cell_h), (255, 255, 255))
d = ImageDraw.Draw(sheet)
for i, (im, p) in enumerate(zip(ims, names)):
    x = i * cell_w + 8
    sheet.paste(im, (x, 50))
    d.text((x, 8), f"{p.name}   card area x{ZOOM/2:.1f}", fill=(15, 15, 15))
    d.text((x, 26), "check each stroke: correct? complete? no merged/blurred?", fill=(120, 120, 120))
    d.line([(i * cell_w, 0), (i * cell_w, cell_h)], fill=(205, 205, 205), width=1)
sheet.save(OUT, "JPEG", quality=95)
print(f"{OUT}  {sheet.size}")
print("判断项在人：逐字核对 保温杯 / 500ML 的笔画完整性")
