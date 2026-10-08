"""位置 5 · 细节材质 —— 从**特写原片**裁切，不是把正面图放大。

像素来源：**特写原片本身（全幅 cover 铺底）+ 字体文件**。零模型调用。

为什么必须是特写原片、且不许生成：
    细节图的全部价值就是"信息增量"。把一张正面全身图裁一刀放大，
    得到的只是缩小版正面 —— **零信息增量**，却占掉一个坑位、
    还让买家以为看到了材质。这是一种比缺图更贵的假图：它花的是信任。

    材质长什么样是**事实**（螺纹、接缝、纹理、底部标识），
    事实只能由"拍过它的那张照片"提供，模型无权替它编。

缺 closeup 素材时：**跳过该坑位**，禁止拿别的图充数。
    （"为什么只有 N 张"必须有据可查 —— 见 run.jsonl 的 skipped 字段。）

本格是全系统唯一"整张图都是照片"的坑位
------------------------------------
    位置 1/2/3/6/7 都是"主体 + 留白/底色"的结构，所以它们走
    `placement.fit_region`（完整装入、四边留白）。
    位置 5 画的就是材质本身，没有"主体"这个概念，因此它走
    `placement.cover_box`：**填满画布、允许裁掉边缘，但绝不补边** ——
    补出来的空白是"编的像素"，而裁掉的边缘只是构图取舍。

    所以它**不用** `product_fill_pct`（表里刻意没有这个字段）：
    在"整张都是照片"的情况下，"主体占比"这个词没有意义。

它也不用 subject.png（不变量 A 管的是"我们的主体"）
    特写是另一个素材，不在 subject.png 里。所以本格的报告里
    `subject_used=False` —— 那是**明确声明**，不是漏填。
"""
from pathlib import Path

from PIL import Image

import placement
import textlayer
from registry import register


@register("closeup_crop", label="特写裁切 + 叠字",
          summary="特写原片裁切 → 叠字", calls_model=False,
          backgrounds=("from_photo",))
def render(slot: dict, ctx: dict) -> dict:
    src_path = (ctx.get("supplied") or {}).get("closeup")
    if not src_path:
        # 编排器的齐套判定本该拦下它（位置 5 的 needs 含 closeup）→ 走到这里
        # 说明契约被绕过了，必须响，而不是悄悄拿别的图凑。
        raise RuntimeError(
            "closeup_crop 需要特写原片，但 ctx.supplied['closeup'] 是空的 —— "
            "齐套判定应当已跳过该坑位（见 src/assets.py 的 resolve）")

    export = ctx["export"]
    plan = ctx["plan"]
    W = H = int(export["long_side_px"])
    palette = (ctx.get("catalog") or {}).get("palette") or {}

    src = Image.open(src_path).convert("RGB")
    cov = placement.cover_box(src.size, W, H)
    canvas = src.resize(tuple(cov["scaled"]), Image.LANCZOS).crop(tuple(cov["crop"]))

    rep = textlayer.finish(canvas, Path(ctx["run_dir"]), plan, slot,
                           ctx["brand"], export, ctx["upc"],
                           palette=palette, seq=ctx.get("seq", 1))

    rep.update({
        "renderer": "closeup_crop",
        "placeholder": False,
        # 明确声明"本格不读主体" —— 免得后人以为这里漏了 subject 接线
        "subject_used": False,
        "subject_sha256": None,
        "pixels_from": str(src_path),
        "src_size": list(src.size),
        "cover_scaled": cov["scaled"],
        "cover_crop": cov["crop"],
        "cover_scale": cov["scale"],
        "out_size": [W, H],
    })
    return rep
