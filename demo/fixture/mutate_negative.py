# -*- coding: utf-8 -*-
"""P2 负样本变异器：把 C 的原始图按「改色 / 加字 / 改结构 / 改数量」做确定性变异。

三条自我约束：
  1. 不联网、不调模型、不用随机数 —— 同一输入跑两次必须逐字节相同；
  2. 这里只回答「改了什么」。**应该被判成什么写在 `expectations.json` 里，先写预期再跑**，
     否则就是拿结果倒推标准；
  3. 变异只做在主体掩码内、或由掩码推导出的坐标上 —— 顺手改到背景会让「拦下」变成假触发。

每一例的产物是 `<out>/<case_id>/raw.png` + `meta.json`（来源哈希、输出哈希、改了哪些像素）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import factcard as fc          # noqa: E402
import measure_cylinder as mc  # noqa: E402

CST = timezone(timedelta(hours=8))

PURPLE = (106, 47, 168)      # #6A2FA8：事实卡调色板里不存在的第三种主色
CHARCOAL = (37, 42, 42)      # #252A2A：卡里已有的下段色，用它做纯结构变异
RIDGE_GRAY = (70, 70, 70)    # 比防滑套亮、仍显著暗于背景，用来造额外筋条
FONT_PATH = "C:/Windows/Fonts/arial.ttf"

DEFAULT_CARD = "demo/fixture/aster-01/product.json"
DEFAULT_SOURCE = "evals/product-demo/fixture-design/C/raw.png"
DEFAULT_OUT = "evals/product-demo/negative-cases"

CASES = [
    ("neg-01-recolor-upper", "改色",
     "把主体内颜色接近声明锚点 body_upper 的像素整片换成卡里没有的第三种主色 #6A2FA8"),
    ("neg-02-add-text", "加字",
     "在杯身上绘制两行白字（容量字样与伪品牌字），不改轮廓与配色"),
    ("neg-03-add-handle", "改结构",
     "在杯身右侧贴一个同色系方形凸出物（把手），轮廓改变、配色不变"),
    ("neg-04-lidless", "改结构",
     "抹掉杯盖与接缝橙环，用背景色填掉对象顶部，留下一个开口的杯体"),
    ("neg-05-extra-ribs", "改数量",
     "在防滑套上另画两道亮凸脊，筋条数量由 3 变 5"),
    ("neg-06-second-cup", "改数量",
     "把主体像素整体复制一份平移到右侧，画面里出现两个杯体"),
    ("neg-07-flat-lid", "改结构",
     "把杯盖顶部的两级阶梯抹平成一个平顶，盖高与配色都不变"),
]


def say(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as im:
        return np.asarray(im.convert("RGB")).astype(np.float64)


def save_rgb(arr: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(path, format="PNG")


def subject(arr: np.ndarray):
    """主体掩码 + 最大连通域 + 它的外接框（与适配器同一套 build_mask / largest_block）。"""
    mask = mc.build_mask(arr)
    comp, _, grid = mc.largest_block(mask)
    if not comp:
        raise SystemExit("原图里找不到主体连通域，无法变异")
    small = np.zeros(grid, dtype=bool)
    for cy, cx in comp:
        small[cy, cx] = True
    full = np.kron(small, np.ones((4, 4), dtype=bool))[:mask.shape[0], :mask.shape[1]]
    ys, xs = np.nonzero(full)
    return mask, full, (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max()))


def slot_hex(card: dict, slot: str) -> str:
    for role in card["palette"]["roles"]:
        if role.get("slot") == slot:
            return role["hex"]
    raise SystemExit("卡里没有语义槽位 " + slot)


def as_image(arr: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def to_arr(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB")).astype(np.float64)


# ─────────────────────────── 七类变异 ───────────────────────────

def mut_recolor_upper(arr, card, meas, mask, full, box):
    x0, y0, x1, y1 = box
    declared = slot_hex(card, "body_upper")
    target = np.array(fc.hex_to_rgb(declared), dtype=np.float64)
    out = arr.copy()
    band = out[y0:y1 + 1, x0:x1 + 1]
    sel = np.linalg.norm(band - target, axis=2) < 60.0
    band[sel] = PURPLE
    return out, {"declared_anchor": declared, "replacement_hex": "#6A2FA8",
                 "replacement_rgb": list(PURPLE), "recolored_pixels": int(sel.sum())}


def mut_add_text(arr, card, meas, mask, full, box):
    x0, y0, x1, y1 = box
    ow, oh = x1 - x0 + 1, y1 - y0 + 1
    img = as_image(arr)
    d = ImageDraw.Draw(img)
    size = max(14, int(round(ow * 0.115)))
    font = ImageFont.truetype(FONT_PATH, size)
    drawn = []
    for text, frac in (("750ML", 0.26), ("ACME", 0.38)):
        bbox = d.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        pos = (x0 + (ow - tw) // 2, y0 + int(round(oh * frac)))
        d.text(pos, text, font=font, fill=(250, 250, 250))
        drawn.append({"text": text, "xy": [int(pos[0]), int(pos[1])]})
    return to_arr(img), {"strings": drawn, "font": FONT_PATH, "font_size": size,
                         "fill_rgb": [250, 250, 250]}


def mut_add_handle(arr, card, meas, mask, full, box):
    x0, y0, x1, y1 = box
    ow, oh = x1 - x0 + 1, y1 - y0 + 1
    hw = int(round(ow * 0.20))
    hy0 = y0 + int(round(oh * 0.36))
    hy1 = y0 + int(round(oh * 0.54))
    img = as_image(arr)
    d = ImageDraw.Draw(img)
    d.rectangle([x1, hy0, x1 + hw, hy1], fill=CHARCOAL)
    return to_arr(img), {"protrusion_px": hw, "rows": [hy0, hy1],
                         "fill_rgb": list(CHARCOAL),
                         "expected_width_gain_share": round(hw / ow, 4)}


def mut_lidless(arr, card, meas, mask, full, box):
    x0, y0, x1, y1 = box
    lid_rows = int(meas["geometry"]["lid_rows"] or 0)
    trim_rows = int(round(float(meas["metrics"]["trim_share"] or 0.0)
                          * int(meas["geometry"]["body_rows"]))) + 2
    painted = lid_rows + trim_rows
    # 向上多抹 24 行：杯盖在背景上留的那道暗弧本来就在主体外接框之上，不抹掉会留下一个悬浮的黑月牙。
    # 每一行用该行左侧的真实背景像素去填，而不是一个统一的底色 —— 背景有竖向渐变，涂平色会留下可见的矩形接缝。
    pad = 24
    top = max(0, y0 - pad)
    painted_rows = (y0 + painted) - top
    sample_x = max(0, x0 - 40)
    out = arr.copy()
    for i in range(top, y0 + painted):
        fill = np.median(out[i, sample_x:max(sample_x + 1, x0 - 8)], axis=0)
        out[i, x0:x1 + 1] = fill
    return out, {"painted_rows": int(painted_rows), "lid_rows": lid_rows, "trim_rows": trim_rows,
                 "up_pad_rows": pad, "bg_sample_x": int(sample_x),
                 "fill": "逐行取该行主体左侧的背景中位数（跟随背景竖向渐变）"}


def mut_extra_ribs(arr, card, meas, mask, full, box):
    x0, y0, x1, y1 = box
    seam = int(meas["geometry"]["sleeve_seam_row"])
    sleeve_rows = int(meas["geometry"]["sleeve_rows"])
    lo = seam + 12
    hi = seam + int(sleeve_rows * 0.82)
    bands = [(hi - 60, 8), (hi - 34, 8)]
    out = arr.copy()
    painted = 0
    for top, height in bands:
        for i in range(top, top + height):
            cols = np.nonzero(mask[y0 + i, x0:x1 + 1])[0]
            if cols.size:
                out[y0 + i, x0 + int(cols[0]):x0 + int(cols[-1]) + 1] = RIDGE_GRAY
                painted += int(cols[-1] - cols[0] + 1)
    return out, {"bands_crop_rows": [[int(t), int(t + h - 1)] for t, h in bands],
                 "rib_window": [lo, hi], "fill_rgb": list(RIDGE_GRAY),
                 "painted_pixels": painted}


def mut_second_cup(arr, card, meas, mask, full, box):
    x0, y0, x1, y1 = box
    ow = x1 - x0 + 1
    margin = 80
    dx = ow + margin
    if x1 + dx >= arr.shape[1]:
        margin = max(20, arr.shape[1] - x1 - ow - 1)
        dx = ow + margin
    out = arr.copy()
    sel = full[y0:y1 + 1, x0:x1 + 1]
    src = out[y0:y1 + 1, x0:x1 + 1].copy()
    out[y0:y1 + 1, x0 + dx:x1 + 1 + dx][sel] = src[sel]
    return out, {"shift_px": int(dx), "gap_px": int(margin),
                 "copied_pixels": int(sel.sum())}


def mut_flat_lid(arr, card, meas, mask, full, box):
    x0, y0, x1, y1 = box
    lid_rows = int(meas["geometry"]["lid_rows"] or 0)
    flat_rows = max(6, int(round(lid_rows * 0.45)))
    mid = y0 + int(round(lid_rows * 0.80))
    cols = np.nonzero(mask[mid, x0:x1 + 1])[0]
    color = np.median(arr[mid, x0 + int(cols[0]):x0 + int(cols[-1]) + 1], axis=0)
    out = arr.copy()
    for i in range(y0, y0 + flat_rows):
        c = np.nonzero(mask[i, x0:x1 + 1])[0]
        if c.size:
            out[i, x0 + int(c[0]):x0 + int(c[-1]) + 1] = color
    return out, {"flattened_rows": flat_rows, "lid_rows": lid_rows,
                 "fill_rgb": [int(round(float(v))) for v in color]}


MUTATORS = {
    "neg-01-recolor-upper": mut_recolor_upper,
    "neg-02-add-text": mut_add_text,
    "neg-03-add-handle": mut_add_handle,
    "neg-04-lidless": mut_lidless,
    "neg-05-extra-ribs": mut_extra_ribs,
    "neg-06-second-cup": mut_second_cup,
    "neg-07-flat-lid": mut_flat_lid,
}


def build_all(project: Path, out_dir: Path, source_rel: str, card_rel: str):
    card = fc.load_card(project / card_rel)
    source = project / source_rel
    if not source.exists():
        raise SystemExit("源图不存在：" + str(source))
    base = load_rgb(source)
    mask, full, box = subject(base)
    meas = mc.measure(source, card=card)
    src_sha = sha256_file(source)
    made = []
    for case_id, cls, desc in CASES:
        arr, params = MUTATORS[case_id](base, card, meas, mask, full, box)
        dst = out_dir / case_id
        png = dst / "raw.png"
        save_rgb(arr, png)
        diff = int((np.abs(arr - base) > 0).any(axis=2).sum())
        meta = {
            "case_id": case_id,
            "mutation_class": cls,
            "description": desc,
            "source": source_rel,
            "source_sha256": src_sha,
            "output": (out_dir.name + "/" + case_id + "/raw.png"),
            "output_sha256": sha256_file(png),
            "output_bytes": png.stat().st_size,
            "image_size": [int(arr.shape[1]), int(arr.shape[0])],
            "changed_pixels": diff,
            "params": params,
            "generated_at": datetime.now(CST).replace(microsecond=0).isoformat(),
            "model_calls": 0,
        }
        (dst / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8", newline="\n")
        made.append(meta)
        say(("  %-22s %-6s changed=%7d  sha16=%s"
             % (case_id, cls, diff, meta["output_sha256"][:16])))
    index = {"schema": "demo-negative-cases/1",
             "generated_at": datetime.now(CST).replace(microsecond=0).isoformat(),
             "source": source_rel, "source_sha256": src_sha,
             "model_calls": 0, "cases": made}
    (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8", newline="\n")
    return index


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="把 C 的原始图变出四类负样本")
    ap.add_argument("--project", default=".")
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--card", default=DEFAULT_CARD)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()
    project = Path(args.project).resolve()
    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = project / out_dir
    index = build_all(project, out_dir, args.source, args.card)
    say("wrote " + str((out_dir / "index.json")) + " cases=" + str(len(index["cases"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
