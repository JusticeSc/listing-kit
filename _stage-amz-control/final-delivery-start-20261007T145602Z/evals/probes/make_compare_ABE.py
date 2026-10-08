"""三臂对照图（A / B / E）：回答「锁段要不要写进**本品的具体特征**」。

背景：臂 A→B 的差异里其实混了三个变量（嘱咐→枚举、通用→本品、无否定→显式否定），
所以「必须逐特征枚举」是**过度归因**。臂 E 补上中间那一档：
**类目级通用枚举 + 显式否定，但不含任何本品具体数值**（不写 3:1、不写"下三分之一深色套"）。

判读方法（人判，机器判不了）：
  商品"长出了没有的东西"（把手/壶口/第二盖）→ 由**否定句**负责；
  商品"有比例的漂移/色块边界变化"      → 由**本品具体值**负责。
这两类失败分别由锁段的不同部分管 —— 这张图就是把它们分开。
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

KIT = Path("E:/workbuddy_workspace/2026-09-20-16-38-19/amz-listing-kit")
REF = KIT / "examples/input/cup_source.jpg"
ROOT = KIT / "evals/probes/lock_out"

ARMS = [
    ("A", "臂 A · 人写·笼统嘱咐 84 字", ROOT / "advice_qwen-image-2.0-pro"),
    ("B", "臂 B · 人写·本品逐特征枚举 820 字", ROOT / "enumerated_qwen-image-2.0-pro"),
    ("E", "臂 E · 类目级通用枚举 + 否定（无本品数值）", ROOT / "libb_class_generic_qwen-image-2.0-pro"),
]

CELL, BAR, GUT = 350, 46, 6
COLS = 4


def font(sz: int):
    for p in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf",
              "C:/Windows/Fonts/arial.ttf"):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, sz)
            except Exception:
                continue
    return ImageFont.load_default()


F_TAG, F_SMALL = font(17), font(13)


def cell(path: Path) -> Image.Image:
    im = Image.open(path).convert("RGB")
    return im.resize((CELL, int(CELL * im.height / im.width)), Image.LANCZOS)


missing: list[str] = []
rows: list[tuple[str, str, list[Image.Image]]] = []
for short, label, d in ARMS:
    fs = sorted(d.glob("*_r*.png"))
    if len(fs) < 3:
        missing.append(f"{short} 缺图（找到 {len(fs)} 张 @ {d.name}）")
        continue
    rows.append((short, label, [cell(p) for p in fs[:3]]))
if missing:
    raise SystemExit("产物不齐，不生成对照图：\n  " + "\n  ".join(missing))

ref = cell(REF)
rh = max(max(im.height for im in r[2]) for r in rows) + BAR
W, H = CELL * COLS + GUT * (COLS + 1), (rh + GUT) * len(rows) + GUT
sheet = Image.new("RGB", (W, H), (244, 244, 246))
d = ImageDraw.Draw(sheet)

for ri, (short, label, ims) in enumerate(rows):
    y = GUT + ri * (rh + GUT)
    d.rectangle([GUT, y, W - GUT, y + rh], fill=(255, 255, 255), outline=(214, 214, 218))
    sheet.paste(ref, (GUT + 8, y + BAR))
    d.text((GUT + 10, y + 8), "SOURCE  源图", fill=(30, 30, 30), font=F_TAG)
    d.text((GUT + 10, y + 27), "待复现的那件商品", fill=(130, 130, 130), font=F_SMALL)
    for ci, im in enumerate(ims):
        x = GUT + (ci + 1) * (CELL + GUT)
        sheet.paste(im, (x, y + BAR))
        d.text((x + 8, y + 8), label, fill=(30, 30, 30), font=F_TAG)
        d.text((x + 8, y + 27), f"#{ci + 1}  多出部件？[ ]无 [ ]有  比例/色块？[ ]同 [ ]变",
               fill=(120, 120, 120), font=F_SMALL)

out = ROOT / "compare_ABE.jpg"
sheet.save(out, "JPEG", quality=92)
print(f"{out}  {sheet.size}  行数 {len(rows)}")
