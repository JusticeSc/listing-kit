"""四臂对照图：SOURCE 固定左列，每行一条臂 —— 让"商品有没有被改"能被一眼看见。

为什么要固定来源列：这个实验唯一要人判的事是「产物里那件商品还是不是源图那件」。
把它放在同一行同一列，视觉比对才成立；分开放两张图让人来回看，等于没做对照。

标签全部中性、留签字栏：机器判不了的项目要求人签字（照 E0 的 ATTEST_ITEMS 纪律）。
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

KIT = Path("E:/workbuddy_workspace/2026-09-20-16-38-19/amz-listing-kit")
REF = KIT / "examples/input/cup_source.jpg"
ROOT = KIT / "evals/probes/lock_out"

ARMS = [
    ("A", "臂 A · 人写·笼统嘱咐 84 字", ROOT / "advice_qwen-image-2.0-pro"),
    ("B", "臂 B · 人写·逐特征枚举 820 字", ROOT / "enumerated_qwen-image-2.0-pro"),
    ("C1", "C1 · 模型写·只给文本资料", ROOT / "c_text_qwen-image-2.0-pro"),
    ("C2", "C2 · 模型写·文本 + VLM 读图", ROOT / "c_vision_qwen-image-2.0-pro"),
]

CELL, BAR, GUT = 350, 46, 6
COLS = 4            # SOURCE + 3 张


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
    # 列 0：源图（每行重复贴 —— 对照必须同行可见）
    sheet.paste(ref, (GUT + 8, y + BAR))
    d.text((GUT + 10, y + 8), "SOURCE  源图", fill=(30, 30, 30), font=F_TAG)
    d.text((GUT + 10, y + 27), "待复现的那件商品", fill=(130, 130, 130), font=F_SMALL)
    for ci, im in enumerate(ims):
        x = GUT + (ci + 1) * (CELL + GUT)
        sheet.paste(im, (x, y + BAR))
        d.text((x + 8, y + 8), f"{label}", fill=(30, 30, 30), font=F_TAG)
        d.text((x + 8, y + 27), f"#{ci + 1}    判：[ ] 商品一致   [ ] 被改",
               fill=(120, 120, 120), font=F_SMALL)

out = ROOT / "compare_4arms.jpg"
sheet.save(out, "JPEG", quality=92)
print(f"{out}  {sheet.size}  行数 {len(rows)}")
