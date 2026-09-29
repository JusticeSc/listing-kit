"""位置 6 · 包装内容物 —— 内容物原片 → 抠 → 铺白底 → 叠字。

像素来源：**内容物原片（已抠好，见 src/cutouts.py）+ 常量纯白 + 字体文件**。零模型调用。

为什么不能生成：
    "盒子里到底有什么、有几件配件、说明书长什么样"是**配置事实**。
    一张正面产品图里根本没有盒子 —— 模型再怎么画也只能是编的。
    这是买家收货后最容易发现货不对板的坑位。

缺 contents 素材时：**跳过该坑位**，不许让模型画、也不许用别的图凑。

抠图**不在这里做**（`cuts=("contents",)` 声明的就是这个）
--------------------------------------------------------
    这一格以前在自己内部抠内容物。现在抠图统一由编排器在**模型调用之前**
    提前做掉，理由是实测出来的（见 registry.register 的 cuts 说明与
    src/cutouts.py 的模块头）：
      · 抠图推理会偶发抓不到内存，而这格排在花钱的位置 4 后面 —— 整格失败过；
      · 抠图失败不该再烧调用费（这条规矩本来就在主体那一步写着）；
      · 抠好的素材一次 run 只抠一次，于是 `--layer placement` 只挪位置的重做
        不再重抠 25s，且产出与上一版逐字节一致。

    所以本格只做"把抠好的素材装进画布"。这也让它变成**纯确定性合成** ——
    与位置 1/2/3 同类，重出一次几十毫秒。

它为什么不读 subject.png（而这不破坏不变量 A）
-------------------------------------------
    不变量 A 说的是"**我们的主体**只有一份"—— 位置 1/2/3/4/7 读的是同一张
    `subject.png`，谁都不许自己再抠一遍（否则轮廓会不一致）。
    内容物**不是主体**：它不在 `subject.png` 里（那张图里没有盒子），
    是这一格独有的素材。所以它有自己的抠图产物（`raw/cut_contents.png`），
    不构成第二个主体来源。

    因此报告里 `subject_used=False` 是**明确声明**，不是漏接线。
"""
from pathlib import Path

from PIL import Image

import placement
import textlayer
from registry import register

# 本格的取景常量：装进可用区时主体长边最多占画布宽度的百分比。
# 与 flat_overlay 同义（主体四周还要留白，所以不该给满）。
# 表里的 product_fill_pct 若给出则覆盖它 —— 那是同一个字段，不同坑位各自取值。
DEFAULT_FILL_PCT = 70

WHITE = (255, 255, 255)

CUT = "contents"        # 本格要求的抠图素材名（与 register(cuts=…) 同一处口径）


@register("contents_compose", label="内容物合成 + 叠字",
          summary="内容物原片（已抠）→ 铺白底 → 叠字", calls_model=False,
          backgrounds=("pure_white",), cuts=(CUT,))
def render(slot: dict, ctx: dict) -> dict:
    cut_info = (ctx.get("cutouts") or {}).get(CUT)
    if not cut_info:
        raise RuntimeError(
            f"contents_compose 需要抠好的 {CUT} 素材，但 ctx['cutouts'] 里没有 —— "
            f"说明编排器没有为本次 run 提前抠它（见 src/cutouts.py）。"
            f"它在表里的 needs 与渲染器声明的 cuts 应当都已经要求了它。")

    export = ctx["export"]
    plan = ctx["plan"]
    W = H = int(export["long_side_px"])
    palette = (ctx.get("catalog") or {}).get("palette") or {}

    tight = Image.open(cut_info["path"]).convert("RGBA")

    # 把可用区算出来（文字条之上、四边留白），再装进去
    n_lines = len(textlayer.visible_callouts(plan)) if textlayer.will_overlay(plan) else 0
    bar_h = textlayer.bar_geometry(W, H, n_lines)["height"]
    spot = placement.fit_region(
        tight.size, W, H - bar_h,
        fill_pct=float(slot.get("product_fill_pct") or DEFAULT_FILL_PCT))

    canvas = Image.new("RGB", (W, H), WHITE)
    prod = tight.resize((spot["w"], spot["h"]), Image.LANCZOS)
    canvas.paste(prod, (spot["x"], spot["y"]), prod)

    rep = textlayer.finish(canvas, Path(ctx["run_dir"]), plan, slot,
                           ctx["brand"], export, ctx["upc"],
                           palette=palette, seq=ctx.get("seq", 1))

    rep.update({
        "renderer": "contents_compose",
        "placeholder": False,
        # 明确声明：本格不读 subject.png（内容物不是主体，见模块头说明）
        "subject_used": False,
        "subject_sha256": None,
        "pixels_from": cut_info["path"],
        "src_size": cut_info["size"],
        # 抠图是**上一阶段**做的（提前、集中、一轮一次）。这里只回指它的凭证 ——
        # 于是"这一格用的是哪次抠图"在报告里可核对，而不是"看起来没问题"。
        "cutout_ref": {"kind": CUT, "path": cut_info["path"],
                       "sha256": cut_info["sha256"],
                       "source": cut_info["source"],
                       "mode": (cut_info.get("cutout") or {}).get("mode")},
        "alpha_coverage": cut_info["alpha_coverage"],
        "paste_box": [spot["x"], spot["y"], spot["w"], spot["h"]],
        "background_color": "#FFFFFF",
        "out_size": [W, H],
    })
    return rep
