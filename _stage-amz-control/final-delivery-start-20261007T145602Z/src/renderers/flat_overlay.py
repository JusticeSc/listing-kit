"""位置 2 / 3 · 卖点图解与规格 —— 纯色底 + 贴主体 + 代码叠字 + 可选标注线。

像素来源：**`subject.png` + catalog 色板常量 + 字体文件**。零模型调用。
    底色 → 贴主体 → （可选）标注线 → 叠字，全程确定性，可重放、可改文案重出。

为什么不用生成背景（这是被问住过的地方，理由要写准）
--------------------------------------------------
    不是"生成背景做不出可读性" —— 生成背景同样能在提示词里要求留白。
    真实理由是两条：
    ① 卖点图的第一任务是**可读**，纯色底的信息密度与对比度天然更高；
    ② 六张纯色底共用 `catalog.palette` 同一色系，成套一致性由**共享数据**保证，
       而不是靠多调几次模型去"碰"出一致的观感。
    代价诚实说：观感不如生成场景丰富。这是明确的取舍，不是"做不到"。

三个字段，三个解释者（加一种变化不改本文件之外的东西）
--------------------------------------------------
    renderer=flat_overlay  → 本文件（像素怎么来）
    text=overlay           → textlayer（文字怎么排）
    annotation=dimension   → 本文件（要不要画标注线）

    ★ 三者都是**独立字段**，所以"位置 2 换纯白底"只需改一行数据（M1 验收③）；
      "位置 3 加标注线"只需改一行数据。本文件里**没有一处按坑位号分支**。

标注线为什么只标单轴数值
----------------------
    规格里的 "尺寸: 7 x 7 x 22 cm" 是三个数揉在一个值里，无法归到某一条线上。
    硬把它标在竖线上就是**编造事实**。所以规则是：值里含多轴分隔符 → 不标，
    并把原因写进产物元数据。**宁可无线，不可乱标。**
    v1 的 `needs_scale_reference`（与手/硬币并置）已作废 —— 那是道具，
    与 E0「原片不得含道具」自相矛盾，也把事实交给了一个随手拿的参照物。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import placement
import textlayer
from kit_config import resolve_font
from registry import register

# 标注线在主体下侧额外占用的高度（占画布比例）。只有 annotation=dimension 时才扣。
# 主体四周的留白不在这里 —— 它是**所有**放置都要遵守的规则，定义在 src/placement.py。
ANNOTATION_RESERVE_RATIO = 0.05

# 标注线标签的取数规则。左列是轴，右列是**认哪些规格键名**。
# 认不出来就不标（而不是猜一个键）—— 猜错键 = 把别的数字标在尺寸线上。
DIM_AXES: dict[str, tuple[str, ...]] = {
    "vertical": ("高度", "高", "长度", "身高", "height", "length"),
    "horizontal": ("宽度", "宽", "直径", "width", "diameter"),
}
# 值里出现这些字符 ⇒ 多轴揉在一个值里，无法归到单条线
_MULTI_AXIS = ("x", "X", "×", "*", "/", "~")


def _pick_dim(specs: dict, axis: str) -> tuple[str | None, str | None, str | None]:
    """从 specs 里挑出该轴的数值。返回 (键, 值, 不标的理由)。"""
    for k, v in (specs or {}).items():
        if not any(t in str(k).lower() for t in DIM_AXES[axis]):
            continue
        val = str(v)
        if any(sep in val for sep in _MULTI_AXIS):
            return str(k), val, "值里含多轴分隔符，无法归到单条标注线"
        if not any(c.isdigit() for c in val):
            return str(k), val, "值里没有数字，标在线上没有意义"
        return str(k), val, None
    return None, None, "specs 里没有可归到该轴的数值"


def _double_arrow(d: ImageDraw.ImageDraw, p0: tuple[int, int],
                  p1: tuple[int, int], color: tuple[int, int, int],
                  width: int, head: int) -> None:
    """两端带箭头的标注线 —— **用代码画矢量线**，不引入任何素材。"""
    d.line([p0, p1], fill=color, width=width)
    for tip, tail in ((p0, p1), (p1, p0)):
        dx, dy = tip[0] - tail[0], tip[1] - tail[1]
        length = max(1.0, (dx * dx + dy * dy) ** 0.5)
        ux, uy = dx / length, dy / length
        px, py = -uy, ux                      # 法向
        bx, by = tip[0] - ux * head, tip[1] - uy * head
        d.polygon([(tip[0], tip[1]),
                   (int(bx + px * head * 0.42), int(by + py * head * 0.42)),
                   (int(bx - px * head * 0.42), int(by - py * head * 0.42))],
                  fill=color)


def _draw_dimension(canvas: Image.Image, box: tuple[int, int, int, int],
                    specs: dict, accent: tuple[int, int, int],
                    brand: dict, W: int, H: int) -> dict:
    """在主体外围画两条双箭头标注线，标签取自 specs 的单轴数值。"""
    x, y, w, h = box
    d = ImageDraw.Draw(canvas)
    font_path, _ = resolve_font(brand, "cn_bold")
    size = max(18, int(W * 0.028))
    font = ImageFont.truetype(font_path, size)
    line_w = max(2, int(W * 0.0025))
    head = max(6, int(W * 0.013))
    gap = int(W * 0.02)

    out: dict = {"mode": "dimension", "arrows": [], "skipped": []}

    # ---- 竖线：贴在主体左侧，跨主体高度
    key, val, why = _pick_dim(specs, "vertical")
    if why:
        out["skipped"].append({"axis": "vertical", "key": key, "reason": why})
    else:
        ax = x - gap - head
        if ax - gap - int(font.getlength(val)) < 0:
            out["skipped"].append(
                {"axis": "vertical", "key": key,
                 "reason": "主体左侧放不下标签，本张不画竖线"})
        else:
            _double_arrow(d, (ax, y), (ax, y + h), accent, line_w, head)
            d.text((ax - gap, y + h // 2), val, font=font, fill=accent, anchor="rm")
            out["arrows"].append({"axis": "vertical", "key": key, "value": val,
                                  "x": ax, "span": [y, y + h]})

    # ---- 横线：在主体下方，跨主体宽度
    key, val, why = _pick_dim(specs, "horizontal")
    if why:
        out["skipped"].append({"axis": "horizontal", "key": key, "reason": why})
    else:
        ay = y + h + int(H * 0.022)
        if ay + line_w >= H:
            out["skipped"].append(
                {"axis": "horizontal", "key": key,
                 "reason": "主体下方没有空间（文字条已占满），本张不画横线"})
        else:
            _double_arrow(d, (x, ay), (x + w, ay), accent, line_w, head)
            # 标签放在右箭头外侧 —— 放在线中间会压住产品本体
            d.text((x + w + gap, ay), val, font=font, fill=accent, anchor="lm")
            out["arrows"].append({"axis": "horizontal", "key": key, "value": val,
                                  "y": ay, "span": [x, x + w]})
    return out


@register("flat_overlay", label="纯色底 + 叠字",
          summary="subject.png → 色板底 → 叠字（可选标注线）", calls_model=False,
          backgrounds=("palette",))
def render(slot: dict, ctx: dict) -> dict:
    export = ctx["export"]
    catalog = ctx.get("catalog") or {}
    plan = ctx["plan"]
    W = H = int(export["long_side_px"])
    run_dir = Path(ctx["run_dir"])

    subject = ctx.get("subject")
    if not subject:
        raise RuntimeError(
            "flat_overlay 需要主体，但 ctx['subject'] 是空的 —— "
            "说明编排器没有为本次 run 准备 subject.png（见 src/subject.py）")

    # 要不要文字、有几条 —— 判据在 textlayer（唯一一处），这里只问结果。
    use_text = textlayer.will_overlay(plan)
    n_lines = len(textlayer.visible_callouts(plan)) if use_text else 0

    # 贴主体之前先问文字层"条子会占多高" —— 否则文字条会盖住产品。
    bar_h = textlayer.bar_geometry(W, H, n_lines)["height"]

    pal = catalog.get("palette") or {}
    bg_rgb = textlayer.hex2rgb(pal.get("base"), "#F2F2F2")
    accent = textlayer.hex2rgb(pal.get("accent"), "#C8102E")
    canvas = Image.new("RGB", (W, H), bg_rgb)

    annotation = slot.get("annotation") or "none"
    # 标注线的标签是文字，靠字体文件绘出 —— 没有文字层就没有标签，
    # 一条没有标签的标注线没有信息量，所以一起不画（并说明原因）。
    draw_ann = annotation == "dimension" and use_text

    # ---- 主体：装进"文字条之上"的那块可用区（几何规则见 src/placement.py）
    #   pad 从可用区里扣，所以主体的垂直居中**始终在可用区内** ——
    #   标注线 reserve 扣出来的那段空隙因此真实存在于主体下方，
    #   而不是让标注线压着主体画。
    src = Image.open(subject["path"]).convert("RGBA")
    region_h = H - bar_h
    reserve = int(H * ANNOTATION_RESERVE_RATIO) if draw_ann else 0
    spot = placement.fit_region(
        src.size, W, region_h,
        fill_pct=float(slot.get("product_fill_pct", 55)),
        reserve=reserve)
    new_size = (spot["w"], spot["h"])
    prod = src.resize(new_size, Image.LANCZOS)
    px, py = spot["x"], spot["y"]
    canvas.paste(prod, (px, py), prod)

    if draw_ann:
        ann = _draw_dimension(canvas, (px, py, new_size[0], new_size[1]),
                              plan.get("specs") or {}, accent, ctx["brand"], W, H)
    elif annotation == "dimension":
        ann = {"mode": "skipped", "arrows": [], "skipped": [
            {"axis": "*", "key": None,
             "reason": "本次不出文字（plan.text != overlay 或无可用文案），"
                       "标注标签无从绘制"}]}
    else:
        ann = {"mode": "none", "arrows": [], "skipped": []}

    # ---- 落盘：交回文字层（它决定"先存 raw 再叠字"还是"直接存成品"）
    rep = textlayer.finish(canvas, run_dir, plan, slot, ctx["brand"], export,
                           ctx["upc"], palette=pal, seq=ctx.get("seq", 1))

    rep.update({
        "renderer": "flat_overlay",
        "placeholder": False,
        "subject_sha256": subject["sha256"],
        "subject_source": subject["source"],
        "paste_box": [px, py, new_size[0], new_size[1]],
        "background_color": pal.get("base"),
        "annotation": ann,
    })
    return rep
