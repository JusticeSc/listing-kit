"""占位图工具（M1 用；M3/M4/M5 会把各渲染器逐个替换成真实实现）。

为什么要有占位图
----------------
M1 的目标是"**证明编排通了**"，不是"出图"。占位图让编排结果**肉眼可见**：
out/ 里会出现命名正确、图上写着"哪个 renderer 产出、调不调模型、何时落地"的灰图。
没有它，M1 只能靠打印日志自证 —— 而日志是代码自己写的，证明力弱得多。

一条刻意的约束：**只用 ASCII 文字**。
    占位图不该依赖字体资产 —— 那正是 M2 才落地的合规项（现用微软雅黑属未授权）。
    所以这里用 Pillow 自带字体，绕开整个字体问题。

下划线开头 → registry.load_all() 会跳过本文件，它不会被登记成渲染器。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from synth import filename_for

_BG = (234, 234, 234)
_INK = (45, 45, 45)
_ACCENT = (200, 16, 46)
_MUTED = (105, 105, 105)


def placeholder(slot: dict, ctx: dict, renderer: str, *,
                calls_model: bool, impl: str) -> dict:
    """写一张标注清楚的占位图，返回产物描述。"""
    export = ctx["export"]
    side = int(export["long_side_px"])
    run_dir = Path(ctx["run_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)

    out_path = run_dir / filename_for(export, ctx["upc"], slot, ctx.get("seq", 1))

    img = Image.new("RGB", (side, side), _BG)
    d = ImageDraw.Draw(img)
    f1 = ImageFont.load_default(size=max(20, side // 13))
    f2 = ImageFont.load_default(size=max(14, side // 22))
    f3 = ImageFont.load_default(size=max(11, side // 34))

    x, y = int(side * 0.06), int(side * 0.10)
    step2 = max(18, side // 20)

    d.text((x, y), f"SLOT {slot['id']}  PLACEHOLDER", font=f1, fill=_INK)
    d.text((x, y + int(side * 0.085)), f"renderer: {renderer}", font=f2, fill=_ACCENT)
    for i, line in enumerate([
        f"role: {slot.get('role')}    text: {slot.get('text')}",
        f"background: {slot.get('background')}    needs: {','.join(slot.get('needs') or [])}",
        f"calls_model: {'yes' if calls_model else 'no'}    validated_by: {slot.get('validate_level')}",
    ]):
        d.text((x, y + int(side * 0.14) + step2 * i), line, font=f2,
               fill=_INK if i == 0 else _MUTED)

    d.text((x, side - int(side * 0.17)),
           f"{ctx['upc']}   run {ctx.get('stamp', '')}", font=f3, fill=_MUTED)
    d.text((x, side - int(side * 0.13)),
           f"stub - real pixels land at {impl}", font=f3, fill=_MUTED)
    d.text((x, side - int(side * 0.09)),
           "M1: orchestration only, no pixels", font=f3, fill=_MUTED)

    img.save(out_path, "JPEG", quality=int(export["jpeg_quality"]), optimize=True)
    return {"path": str(out_path), "renderer": renderer, "placeholder": True}
