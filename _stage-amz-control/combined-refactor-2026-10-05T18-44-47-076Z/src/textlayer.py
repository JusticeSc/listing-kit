"""叠字层：确定性渲染中文文字，覆盖在生成出来的无字背景上。

为什么必须独立成层：
    中文长文案在生成模型里的渲染成功率很低（错字、缺笔、乱码），而位置 2/3/7
    的文字是**信息本身**，错一个字就废图。所以生成层一律禁字、只出干净背景，
    文字全部由本模块用字体文件确定性绘制 —— 可复现、可校对、可改文案重出。

这正是"精确层 + 生成层分离"原则的落地。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from kit_config import resolve_font
from synth import filename_for


def hex2rgb(v: str, fallback: str = "#000000") -> tuple[int, int, int]:
    """#RRGGBB / #RGB → (r, g, b)。

    公开（去掉下划线）：颜色解析不只有本模块需要 —— `flat_overlay` 也要把
    catalog 色板里的底色与强调色变成 RGB。一处定义，两个消费方。
    """
    v = (v or fallback).lstrip("#")
    if len(v) == 3:
        v = "".join(c * 2 for c in v)
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def bar_geometry(W: int, H: int, n: int) -> dict:
    """文字条会占多高、每行多高。n = 实际要渲染的条数。

    ★ 为什么必须对外可用（而不是让调用方自己算）：
      位置 2/3 是"产品 + 文字"的合成，**贴主体之前就得知道文字条会吃掉多高**，
      否则文字条会盖住产品。而这个高度是文字层的私有排版规则 ——
      让 flat_overlay 再算一遍，就是同一套规则的第二处定义（本项目最忌讳的那种漂移）。
      所以规则留在本模块，只开放一个纯函数给它读。

    n <= 0 时返回 height=0：没有文字就没有条，调用方据此拿到全高可用区。
    """
    if n <= 0:
        return {"height": 0, "line_height": 0, "lines": 0}
    h = int(H * 0.30)
    h = max(h, int(H * 0.10 * n))      # 每条至少占 10% 高度
    h = min(h, int(H * 0.55))          # 不超过 55%，避免压死主体
    return {"height": h, "line_height": h // n, "lines": n}


def visible_callouts(plan: dict) -> list[str]:
    """本次真正要画上去的文案（去掉空串与空白）。

    ★ 判据只有这一处。两个消费方，缺一就会出现"预留了 5 行、只画了 4 行"：
        渲染器 —— 贴主体**之前**就要据此算文字条会占多高（bar_geometry）
        finish   —— 据此决定走"叠字"还是"直接落盘"
    """
    return [c.strip() for c in (plan.get("callouts") or []) if c and c.strip()]


def will_overlay(plan: dict) -> bool:
    """本次到底叠不叠字。读 `plan["text"]` 而不是 `slot["text"]` ——
    命令行 `--text-mode` 覆盖的是 plan；若读 slot，就会出现
    "CLI 说不要文字、渲染器却仍去叠字"的自相矛盾。
    """
    return (plan.get("text") or "none") == "overlay" and bool(visible_callouts(plan))


def finish(canvas: Image.Image, run_dir: str | Path, plan: dict, slot: dict,
           brand: dict, export: dict, upc: str,
           palette: dict | None = None, seq: int = 1) -> dict:
    """落盘：要叠字 → 先把底存进 `raw/` 再叠字；不叠字 → 直接存成品。

    为什么要留 `raw/slotNN_bg.jpg`：它证明**文字是在最后一遍加上去的**。
    位置 2/3/5/6/7 的文字与画面是两条独立的产物 —— 改一句文案不需要重绘画面，
    也不必重新抠图。raw/ 里那张就是这件事的物证（M3 验收③ 靠的就是这条性质）。

    它是**唯一**决定"成品文件怎么落"的地方。四个渲染器各写一遍，
    迟早出现某一个忘了先存 raw、或者少了 `--text-mode none` 的分支。
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    q = int(export["jpeg_quality"])

    if will_overlay(plan):
        (run_dir / "raw").mkdir(exist_ok=True)
        bg_path = run_dir / "raw" / f"slot{slot['id']:02d}_bg.jpg"
        canvas.save(bg_path, "JPEG", quality=q, optimize=True)
        return overlay_callouts(bg_path, run_dir, plan, slot, brand, export,
                                upc, seq, palette=palette)

    out_path = run_dir / filename_for(export, upc, slot, seq)
    canvas.convert("RGB").save(out_path, "JPEG", quality=q, optimize=True)
    return {"slot_id": slot["id"], "path": str(out_path), "callouts": [],
            "note": "本次不出文字（plan.text != overlay 或无可用文案）"}


def overlay_callouts(
    bg_path: str | Path,
    out_dir: str | Path,
    plan: dict,
    slot: dict,
    brand: dict,
    export: dict,
    upc: str,
    seq: int = 1,
    palette: dict | None = None,
) -> dict:
    """把 plan.callouts 叠到背景图上，返回处理报告。

    颜色从哪来（这是被"两个真相源"咬过的地方）
    -----------------------------------------
        文字色 / 强调色  ← `palette`（= catalog.palette，**类目**模板）
        文字条底色 / 不透明度 / 字体 ← `brand`（**品牌**资产）

        原先文字色与强调色读的是 `brand.json`，而同一张图上标注线的箭头读的是
        `catalog.palette` —— 同一个视觉对象两个所有者，只因默认值恰好同色而看不出来。
        分开的依据：**底色与强调色随类目变**（家居厨具用中性灰，服装换暖米色），
        **字体与文字条随品牌不变**。所以 palette 由调用方传进来，本模块不去读盘 ——
        读盘就会变成"文字层也有自己的一份配置来源"。
    """
    bg_path, out_dir = Path(bg_path), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    img = Image.open(bg_path).convert("RGBA")
    W, H = img.size
    callouts = visible_callouts(plan)      # 同一处判据，不在这里再写一遍

    out_path = out_dir / filename_for(export, upc, slot, seq)
    q = int(export["jpeg_quality"])

    if not callouts:
        img.convert("RGB").save(out_path, "JPEG", quality=q, optimize=True)
        return {
            "slot_id": slot["id"], "path": str(out_path),
            "callouts": [], "warning": "plan 中没有可用卖点，未叠加文字",
        }

    font_path, font_src = resolve_font(brand, "cn_bold")
    # 颜色：类目模板（palette）说了算；文字条与字体：品牌资产（brand）说了算。
    pal = palette or {}
    text_color = hex2rgb(pal.get("text"), "#1A1A1A")
    accent = hex2rgb(pal.get("accent"), "#C8102E")
    b = brand.get("brand") or {}
    bar_color = hex2rgb(b.get("text_bar_color", "#FFFFFF"))
    opacity = float(b.get("text_bar_opacity", 0.9))

    n = len(callouts)
    geo = bar_geometry(W, H, n)        # 唯一一处排版规则；flat_overlay 读的是同一个函数
    bar_h, line_h = geo["height"], geo["line_height"]

    pad_x = int(W * 0.075)
    dot_r = max(5, int(line_h * 0.055))
    gap = int(line_h * 0.28)

    size = max(14, min(int(line_h * 0.54), int(W * 0.062)))
    font = ImageFont.truetype(font_path, size)

    # 文字过长自动缩放，保证不溢出
    avail = W - 2 * pad_x - 2 * dot_r - gap
    while size > 14 and max(font.getlength(c) for c in callouts) > avail:
        size -= 2
        font = ImageFont.truetype(font_path, size)

    bar = Image.new("RGBA", (W, bar_h), bar_color + (int(255 * opacity),))
    img.alpha_composite(bar, (0, H - bar_h))

    d = ImageDraw.Draw(img)
    for i, text in enumerate(callouts):
        cy = H - bar_h + line_h * i + line_h // 2
        cx = pad_x + dot_r
        d.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=accent + (255,))
        d.text((cx + dot_r + gap, cy), text, font=font, fill=text_color + (255,), anchor="lm")

    img.convert("RGB").save(out_path, "JPEG", quality=q, optimize=True)

    return {
        "slot_id": slot["id"],
        "path": str(out_path),
        "callouts": callouts,
        "font": font_path,
        "font_source": font_src,
        "font_size": size,
        "bar_height_px": bar_h,
        "text_truncated": bool(max(font.getlength(c) for c in callouts) > avail),
    }
