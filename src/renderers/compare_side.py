"""位置 7 · 对比 / 信任背书 —— 自家主体 + 竞品图并排 + 叠字。

像素来源：**subject.png + 竞品原图（已抠好，见 src/cutouts.py）+ 色板底 + 字体文件**。
零模型调用。

为什么要用到竞品图、且必须是真的：
    对比图的说服力全部来自"两边都是真的"。竞品长什么样是**别人的事实**，
    不在我们手上，模型更无权替它编 —— 编出来的"竞品"是双重问题：
    既误导买家，又可能构成对特定品牌的不当比较。
缺 competitor 素材时：**跳过该坑位**。

它为什么有自己的抠图产物（而不破坏不变量 A）
-----------------------------------------
    不变量 A 管的是"**我们的主体**只有一份"。竞品是别人的素材，不在
    `subject.png` 里；本格的消费者只有它一个，所以它有自己的抠图产物
    （`raw/cut_competitor.png`），不构成第二个主体来源。
    报告里 `subject_used=True` 且另外带竞品抠图的凭证 —— 两个来源都写明。

抠图**不在这里做**（`cuts=("competitor",)` 声明的就是这个）
--------------------------------------------------------
    理由见 registry.register 的 cuts 说明与 src/cutouts.py 的模块头。
    对本格而言最要紧的一条是**归因**：竞品抠图的 alpha 在 rembg 与 floodfill
    两条路之间相差十几万像素。以前在这里现抠，于是"重做一次"（哪怕只是
    挪了下位置）都可能换掉竞品的像素 —— 而"差异只来自被改的那一处"
    正是版本对比成立的前提。抠一次、复用，这件事就不再可能发生。

合规：三道红线，三道防线，力度不同（这是本格最需要说清楚的地方）
------------------------------------------------------------
    ① **不写竞品品牌名** —— 标签是**固定常量**（"本品"/"竞品"），不来自用户输入，
       所以不存在"用户填了个品牌名进来"这条路径。结构性保证。
    ② **不贬低竞品** —— 呈现方式只有"并排 + 中性标签"，没有比较级文案。
       同样是结构性的：本格不生成任何评价性文字。
    ③ **竞品原图里本来就有竞品品牌名 / logo / 水印** —— ★ 这条**工具判不了**。
       它和"原片自带水印"是同一类问题：没有规则可写，只能由人在投递时签字。
       所以 E0 的签字清单里有一条 `competitor_clean`，**只在位置 7 真的要出图时**
       才要求（见 src/intake.py）。工具不假装验过它，但要求有人对它负责。

    把①②做成结构保证、把③交给人 —— 这个分工不是偷懒，是承认"能写规则的和
    写不出规则的不是一回事"。v1 在这里的做法是写一个不可靠的检测器假装有保护，
    那比不检更坏。
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import placement
import textlayer
from kit_config import resolve_font
from registry import register

# 两列下方的标签带高度（占画布比例）。扣进可用区里，所以标签不会压到产品。
LABEL_BAND_RATIO = 0.055

# 中分隔线的颜色。**刻意不从色板取**：它不是品牌色，是结构线。
# 取 accent（红）会让"中间那条线"看起来像一个论断，而这里不允许有论断。
DIVIDER_RGB = (168, 168, 168)

# 每列里图能占到多大（列内百分比）。两件并排，给满会显得挤。
DEFAULT_FILL_PCT = 88

# 两列的中性标签。**固定常量**，不来自用户输入 —— 这是"不写竞品品牌名"的
# 结构性保证（见模块头 ①）。刻意只写中性描述，不写"更好 / 更耐用"这类比较。
COLUMN_LABELS = ("本品", "竞品")

CUT = "competitor"      # 本格要求的抠图素材名（与 register(cuts=…) 同一处口径）


@register("compare_side", label="并排对比 + 叠字",
          summary="自家主体 + 竞品图（已抠）并排 → 叠字", calls_model=False,
          backgrounds=("palette",), cuts=(CUT,))
def render(slot: dict, ctx: dict) -> dict:
    subject = ctx.get("subject")
    cut_info = (ctx.get("cutouts") or {}).get(CUT)
    if not subject:
        raise RuntimeError(
            "compare_side 需要主体，但 ctx['subject'] 是空的 —— "
            "说明编排器没有为本次 run 准备 subject.png（见 src/subject.py）")
    if not cut_info:
        raise RuntimeError(
            f"compare_side 需要抠好的 {CUT} 素材，但 ctx['cutouts'] 里没有 —— "
            f"说明编排器没有为本次 run 提前抠它（见 src/cutouts.py）。")

    export = ctx["export"]
    plan = ctx["plan"]
    W = H = int(export["long_side_px"])
    pal = (ctx.get("catalog") or {}).get("palette") or {}
    bg_rgb = textlayer.hex2rgb(pal.get("base"), "#F2F2F2")
    text_rgb = textlayer.hex2rgb(pal.get("text"), "#1A1A1A")

    n_lines = len(textlayer.visible_callouts(plan)) if textlayer.will_overlay(plan) else 0
    region_h = H - textlayer.bar_geometry(W, H, n_lines)["height"]
    label_h = int(H * LABEL_BAND_RATIO)
    cells = placement.columns(W, region_h, 2, reserve=label_h)

    canvas = Image.new("RGB", (W, H), bg_rgb)

    # ---- 左：自家主体（读 subject.png，与位置 1/2/3 是同一份 —— 不变量 A）
    ours = Image.open(subject["path"]).convert("RGBA")
    box_l = placement.fit_into(cells[0], ours.size, fill_pct=DEFAULT_FILL_PCT)
    img_l = ours.resize((box_l["w"], box_l["h"]), Image.LANCZOS)
    canvas.paste(img_l, (box_l["x"], box_l["y"]), img_l)

    # ---- 右：竞品（读已抠好的素材；抠图是上一阶段做的，见模块头）
    c_tight = Image.open(cut_info["path"]).convert("RGBA")
    box_r = placement.fit_into(cells[1], c_tight.size, fill_pct=DEFAULT_FILL_PCT)
    img_r = c_tight.resize((box_r["w"], box_r["h"]), Image.LANCZOS)
    canvas.paste(img_r, (box_r["x"], box_r["y"]), img_r)

    # ---- 中分隔线 + 两列中性标签（结构元素，不是文案）
    d = ImageDraw.Draw(canvas)
    cell_y, cell_h = cells[0][1], cells[0][3]
    div_x = (cells[0][0] + cells[0][2] + cells[1][0]) // 2
    d.line([(div_x, cell_y), (div_x, cell_y + cell_h)], fill=DIVIDER_RGB,
           width=max(2, int(W * 0.0025)))

    font = ImageFont.truetype(resolve_font(ctx["brand"], "cn_bold")[0],
                              max(18, int(W * 0.032)))
    for cell, label in zip(cells, COLUMN_LABELS):
        d.text((cell[0] + cell[2] // 2, cell_y + cell_h + label_h // 2),
               label, font=font, fill=text_rgb, anchor="mm")

    rep = textlayer.finish(canvas, Path(ctx["run_dir"]), plan, slot,
                           ctx["brand"], export, ctx["upc"],
                           palette=pal, seq=ctx.get("seq", 1))

    rep.update({
        "renderer": "compare_side",
        "placeholder": False,
        "subject_used": True,
        "subject_sha256": subject["sha256"],
        "subject_source": subject["source"],
        "subject_box": [box_l["x"], box_l["y"], box_l["w"], box_l["h"]],
        # 竞品那一列的凭证：抠图产物是哪一份、来源是哪张原图、走的哪条抠图路。
        # 抠图的**耗时**不记在这里 —— 它发生在上一阶段（提前、集中），
        # 记在本格会重演"让成本落在没产生它的那一步"那个错。
        "competitor": {
            "path": cut_info["path"],
            "source": cut_info["source"],
            "sha256": cut_info["sha256"],
            "src_size": cut_info["size"],
            "cutout": cut_info.get("cutout"),
            "alpha_coverage": cut_info["alpha_coverage"],
            "box": [box_r["x"], box_r["y"], box_r["w"], box_r["h"]],
        },
        "layout": {"columns": [list(c) for c in cells], "divider_x": div_x,
                   "labels": list(COLUMN_LABELS)},
        "background_color": pal.get("base"),
        "out_size": [W, H],
    })
    return rep
