r"""放置几何：把一块像素装进画布 —— **一套规则，一处定义**。

为什么它必须独立成模块（这条是被"同型问题"逼出来的）
--------------------------------------------------
    M3 时这套规则写在 `renderers/flat_overlay.py` 里。到 M5，位置 5/6/7 三个渲染器
    都需要同一件事（"把图装进文字条之上那块区域，且四边留白"）。各写一遍就是
    四个版本 —— 改一个忘三个。

    本项目刚因为同型问题吃过一次亏：同一张图上的**强调色有两个来源**
    （标注线读 `catalog.palette.accent`、项目符号读 `brand.accent_color`），
    只因默认值恰好同色而没被发现。**放置规则比颜色更隐蔽** ——
    它没有"看起来不对"的立刻反馈，只会让七张图里有两张构图偏一点。

    所以这里只放**纯函数**：输入尺寸元组，输出位置与尺寸。不读盘、不碰
    PIL 图像对象、不查配置。因此它可以被独立单测，也不会长出第二个配置来源。

四种取景，四种语义（不要合并成"一个万能函数"）
------------------------------------------
    fit_region   等比缩放**完整**装入可用区，四边留白      ← 位置 2/3/6/7 的主体
                 （"完整"是关键：裁掉一截主体 = 改变了事实）
    cover_box    填满画布、**允许裁切**                    ← 位置 5 用特写原片做底
                 （宁可裁掉边缘，也不能在四周补空白 —— 补出来的空白是"编的像素"）
    region_box   只算可用区，不缩放                        ← 需要自己放置时用
    columns      把可用区横向平分成 n 列                   ← 位置 7 的并排对比

为什么留白是**几何保证**而不是观感
--------------------------------
    `subject.png` 是紧裁切的，它的第 0 行就是产品的最高那一行。于是当"可用区
    高度"成为缩放约束时（位置 2 有五条文案、文字条吃掉一半画布），主体会**精确
    填满**整个可用区、贴图框 y=0 —— 贴边的商品图平台侧通常不接受，
    而位置 2/3 的校验规则只查尺寸与文字存在性，**查不出贴边**。
    这条教训的完整记录见 docs/实施计划.md §6 M3。
"""
from __future__ import annotations

# 单边最小留白（占画布短边比例）。主体四边至少这么多，任何取景方式都不得绕过。
DEFAULT_PAD_RATIO = 0.035

# 画布宽度为主体的**硬上限**：即使 fill_pct 给到 100，也不许贴到左右边缘。
# 它比 DEFAULT_PAD_RATIO 更松，所以正常情况下不起作用；它的作用是兜住
# "有人把 fill_pct 写成 100"这种情况，而不是日常约束。
WIDTH_CEILING = 0.92


def region_box(canvas_side: int, region_h: int, *,
               pad_ratio: float = DEFAULT_PAD_RATIO,
               reserve: int = 0) -> tuple[int, int, int, int]:
    """可用区：文字条之上的那块区域，四边扣掉留白，下侧可再扣 reserve。

    reserve 是给**标注线**腾的地方（位置 3）。扣在可用区里而不是扣在"居中"里，
    意思是：主体在可用区内居中，于是标注线用的是主体**下方**那段真实空隙 ——
    而不是压着主体画。
    """
    pad = int(canvas_side * pad_ratio)
    return (pad, pad,
            max(1, canvas_side - 2 * pad),
            max(1, region_h - 2 * pad - reserve))


def fit_region(src_size: tuple[int, int], canvas_side: int, region_h: int, *,
               fill_pct: float = 100.0,
               pad_ratio: float = DEFAULT_PAD_RATIO,
               reserve: int = 0) -> dict:
    """等比缩放，使 src **完整**装入可用区（长边不超过 fill_pct% 画布宽），并居中。

    返回含 x/y/w/h/scale/box —— `box` 也一并给出，因为渲染器常需要知道
    "可用区在哪"（例如标注线贴在主体左侧时要判断有没有地方放标签）。
    """
    sw, sh = src_size
    bx, by, bw, bh = region_box(canvas_side, region_h,
                                pad_ratio=pad_ratio, reserve=reserve)
    limit = min(canvas_side * fill_pct / 100.0, canvas_side * WIDTH_CEILING, bh)
    scale = limit / max(sw, sh)
    w, h = max(1, round(sw * scale)), max(1, round(sh * scale))
    return {
        "x": (canvas_side - w) // 2,
        "y": by + max(0, (bh - h) // 2),
        "w": w, "h": h,
        "scale": round(scale, 6),
        "box": [bx, by, bw, bh],
    }


def cover_box(src_size: tuple[int, int], box_w: int, box_h: int) -> dict:
    """填满 box_w×box_h，**居中裁切**（多余部分切掉，绝不补边）。

    返回 crop 框（作用在**缩放后**的图上）与缩放到尺寸。
    与 fit_region 的分工：这个函数会把主体裁掉一部分，所以它只用于
    "整张照片本来就是这张图"的坑位（位置 5 的特写底），不能用于"要保住完整主体"的坑位。
    """
    sw, sh = src_size
    scale = max(box_w / sw, box_h / sh)
    w, h = max(box_w, round(sw * scale)), max(box_h, round(sh * scale))
    left, top = (w - box_w) // 2, (h - box_h) // 2
    return {
        "crop": [left, top, left + box_w, top + box_h],
        "scaled": [w, h],
        "scale": round(scale, 6),
    }


def columns(canvas_side: int, region_h: int, n: int, *,
            pad_ratio: float = DEFAULT_PAD_RATIO,
            gutter_ratio: float = 0.04,
            reserve: int = 0) -> list[tuple[int, int, int, int]]:
    """把可用区**横向平分成 n 列**（并排对比用）。返回 n 个 (x, y, w, h)。

    列间留 gutter，最外侧留 pad —— 于是"并排"不会变成"贴边"。
    """
    if n < 1:
        raise ValueError(f"columns 的 n 必须 >= 1，收到 {n}")
    bx, by, bw, bh = region_box(canvas_side, region_h,
                                pad_ratio=pad_ratio, reserve=reserve)
    gutter = int(bw * gutter_ratio)
    cell_w = max(1, (bw - gutter * (n - 1)) // n)
    return [(bx + i * (cell_w + gutter), by, cell_w, bh) for i in range(n)]


def fit_into(box: tuple[int, int, int, int], src_size: tuple[int, int], *,
             fill_pct: float = 100.0) -> dict:
    """把 src 等比装进给定外框并居中（`columns` 的配套）。

    与 fit_region 的差别：这里的外框由调用方给出（可能是一列、一格），
    所以不再扣 pad —— pad 已经在框里了。
    """
    sw, sh = src_size
    bx, by, bw, bh = box
    scale = min(bw * fill_pct / 100.0, bh * fill_pct / 100.0) / max(sw, sh)
    w, h = max(1, round(sw * scale)), max(1, round(sh * scale))
    return {"x": bx + (bw - w) // 2, "y": by + (bh - h) // 2, "w": w, "h": h,
            "scale": round(scale, 6)}
