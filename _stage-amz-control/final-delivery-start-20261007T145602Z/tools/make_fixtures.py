r"""生成 M5 的测试素材与"满素材"商品包 —— 可复现，不依赖任何外部图片。

为什么要这么一个脚本
------------------
    M5 的三个坑位分别依赖 `closeup` / `contents` / `competitor`，而
    `examples/input/` 里只有一张正面图。测试素材必须**确定**（每次生成结果一致），
    否则"换一张素材 → 只有对应那张产物变"这类断言无法复现。
    所以素材由代码画出来，而不是找三张网图塞进仓库。

三张素材的形状，以及为什么是这些形状
--------------------------------
    cup_closeup.jpg    正面图**上半部**的整幅裁切。真实的特写原片就是这么拍的：
                       主体占满画面、背景简单。刻意保留原始画幅（非 1:1）——
                       位置 5 走的正是 cover 裁切那条路径，小正方形会把这条路径测掉。

    cup_contents.jpg   抠出来的杯子 + 盒体 + 刷子，摆在浅色台面上。
                       "盒子里有什么"是配置事实，所以它必须是一张**摆拍**出来的
                       独立素材，而不是从正面图推出来的。

    competitor.jpg     **轮廓明显不同**的另一个保温杯（细长、深色、单色杯身 +
                       浅色盖子）。若画成与自家杯子相近的形状，"并排"就看不出
                       是两件东西，测试也就失去了意义。

    三张都 ≥1000px 长边（E0 的平台下限），且四角近白（抠图更容易）。

用法
----
    python tools/make_fixtures.py            # 生成到 examples/input/
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import synth  # noqa: E402

OUT_DIR = ROOT / "examples" / "input"
SOURCE = OUT_DIR / "cup_source.jpg"

BG_WARM = (238, 236, 231)      # 台面浅色：与深色产品反差足够，抠图容易
BG_COOL = (237, 240, 243)      # 竞品那张用冷一点的白，免得两张图像同一场景


def _rounded(d: ImageDraw.ImageDraw, box, radius: int, fill) -> None:
    d.rounded_rectangle(box, radius=radius, fill=fill)


def make_closeup() -> Path:
    """特写原片 = 正面图上半部的整幅裁切（长边 1024 ≥ 平台下限 1000）。"""
    src = Image.open(SOURCE)
    w, h = src.size
    top = src.crop((0, 0, w, int(h * 0.60)))
    out = OUT_DIR / "cup_closeup.jpg"
    top.save(out, "JPEG", quality=92, optimize=True)
    return out


def make_contents() -> Path:
    """内容物原片：杯子 + 盒体 + 刷子，摆在浅色台面上。"""
    side = 1200
    canvas = Image.new("RGB", (side, side), BG_WARM)
    d = ImageDraw.Draw(canvas)

    # 台面：下方一条略深的横带，给背景一点层次（也顺便考验抠图）
    d.rectangle([0, int(side * 0.78), side, side], fill=(228, 224, 216))

    # 杯子（用真实正面图抠出来的主体，保证"内容物里有这件商品"）
    cup_src = Image.open(SOURCE)
    cup_rgba, _ = synth.remove_background(cup_src)
    bbox = synth.alpha_bbox(cup_rgba)
    if bbox is None:
        raise SystemExit("无法从 cup_source.jpg 抠出杯子，内容物素材生成失败")
    cup = cup_rgba.crop(bbox)
    target_h = int(side * 0.62)
    cup = cup.resize((max(1, round(cup.width * target_h / cup.height)), target_h),
                     Image.LANCZOS)
    canvas.paste(cup, (int(side * 0.06), int(side * 0.16)), cup)

    # 盒体：一个牛皮纸色的长方体（正面 + 顶面，用两个多边形做出立体感）
    bx0, bx1 = int(side * 0.40), int(side * 0.72)
    by0, by1 = int(side * 0.36), int(side * 0.78)
    d.polygon([(bx0, by0 + 60), (bx0 + 90, by0), (bx1 + 90, by0),
               (bx1, by0 + 60)], fill=(206, 178, 140))
    d.rectangle([bx0, by0 + 60, bx1, by1], fill=(186, 156, 118))
    d.rectangle([bx0 + 40, by0 + 150, bx1 - 40, by0 + 210], fill=(240, 232, 218))

    # 刷子：细长手柄 + 刷头
    sx, sy = int(side * 0.80), int(side * 0.42)
    _rounded(d, [sx, sy, sx + 34, sy + int(side * 0.30)], 16, (92, 96, 102))
    _rounded(d, [sx - 10, sy + int(side * 0.30), sx + 44, sy + int(side * 0.40)],
             12, (52, 54, 58))

    out = OUT_DIR / "cup_contents.jpg"
    canvas.save(out, "JPEG", quality=92, optimize=True)
    return out


def make_competitor() -> Path:
    """竞品原片：轮廓明显不同的另一只保温杯（细长、深色杯身 + 浅色盖）。"""
    side = 1200
    canvas = Image.new("RGB", (side, side), BG_COOL)
    d = ImageDraw.Draw(canvas)

    cx0, cx1 = int(side * 0.33), int(side * 0.63)
    body_top, body_bot = int(side * 0.28), int(side * 0.82)

    # 杯身：细长，上宽下略收 —— 与自家杯子的"粗、双色、带纹理"形成明显差别
    d.polygon([(cx0, body_top + 40), (cx1, body_bot),
               (cx1 - 18, body_bot + 40), (cx0 + 18, body_top + 40)],
              fill=(58, 62, 70))
    d.rounded_rectangle([cx0, body_top, cx1, body_bot + 30], radius=26,
                        fill=(74, 78, 86))
    # 盖子：浅色、带一圈杯口
    d.rounded_rectangle([cx0 - 6, body_top - 70, cx1 + 6, body_top + 30],
                        radius=22, fill=(212, 216, 220))
    d.rounded_rectangle([cx0 - 2, body_top - 92, cx1 + 2, body_top - 52],
                        radius=14, fill=(180, 186, 192))
    # 一条竖向高光，让它看起来是个圆柱而不是一块板
    d.rectangle([cx0 + 26, body_top + 60, cx0 + 44, body_bot - 10],
                fill=(96, 100, 108))

    out = OUT_DIR / "competitor.jpg"
    canvas.save(out, "JPEG", quality=92, optimize=True)
    return out


def main() -> int:
    if not SOURCE.exists():
        print(f"缺少源图：{SOURCE}")
        return 2
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for fn in (make_closeup, make_contents, make_competitor):
        p = fn()
        with Image.open(p) as im:
            print(f"  {p.name:<22}{im.size[0]}×{im.size[1]}  {p.stat().st_size // 1024} KB")
    print("素材已生成。商品包见 examples/product_fullset.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
