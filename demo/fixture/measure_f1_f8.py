# -*- coding: utf-8 -*-
"""[SUPERSEDED] Aster 01 的 F1–F8 确定性量测（旧实现）。

> **2026-09-25（D0.5）起已被取代**：量测与判定的正式入口是
> `demo/fixture/measure_cylinder.py`（`metric_profile = cylinder-v1`）+ `demo/fixture/product_check.py`。
> 本文件保留作 D0.1 的证据来源与历史对照，**不再驱动判定**，原因是它的三处结构问题：
> `CARD` 绑在模块级、`--card` 只影响报告不影响量测、报告标题仍写着 v2。

v1 的错误：把背景渐变与投影算进了主体，导致轮廓比例与筋条计数全错。
v2 的分割判据：主体 = 饱和像素（青绿 / 橙环）或显著暗于背景的像素（炭灰部件）。
背景与浅投影都是低饱和的中性灰，因此被排除。

v3 的分层：**几何量测留在本文件，商品专属的数字与颜色搬进事实卡**
（`demo/fixture/aster-01/product.json`）。v2 里写死的
`TARGET = {"ratio": 3.1, ...}`、`PALETTE = {"teal": "#0F6B66", ...}`
以及一套色相规则（`r > g > b ... lum < 110`）只对这一个杯子和这一套配色成立，
换商品要改代码 —— 那不是产品能力。分类与判定现在都由 `factcard` 从数据驱动。

它仍只输出可复算的量测，不输出美学分，也不代替人工视觉结论。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factcard as fc  # noqa: E402

# 商品专属的数字与颜色一个都不留在代码里：
CARD = fc.load_card()
CLF = fc.PaletteClassifier(CARD["palette"])
PALETTE = {r["role"]: r["hex"] for r in CARD["palette"]["roles"]}


def _check(fact_id: str, metric: str) -> dict:
    for fact in CARD["facts"]:
        if fact["id"] != fact_id:
            continue
        for item in fact.get("machine_checks") or []:
            if item["metric"] == metric:
                return item
    return {}


def declared_of(fact_id: str, metric: str):
    return _check(fact_id, metric).get("declared")


def pass_max(metric: str):
    return (_check_any(metric).get("pass") or {}).get("max")


def _check_any(metric: str) -> dict:
    for fact in CARD["facts"]:
        for item in fact.get("machine_checks") or []:
            if item["metric"] == metric:
                return item
    return {}


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def lum_of(arr):
    return arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114


def build_mask(arr, diag=None):
    h, w, _ = arr.shape
    band = max(4, int(min(h, w) * 0.03))
    border = np.concatenate([
        arr[:band].reshape(-1, 3), arr[-band:].reshape(-1, 3),
        arr[:, :band].reshape(-1, 3), arr[:, -band:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    lum = lum_of(arr)
    lum_bg = float(lum_of(bg.reshape(1, 1, 3))[0, 0])
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    sat = (mx - mn) / np.maximum(mx, 1.0)
    mask = (sat > 0.12) | (lum < 0.45 * lum_bg)
    if diag is not None:
        diag.update({"bg_rgb": [round(float(v), 1) for v in bg],
                     "bg_lum": round(lum_bg, 1),
                     "mask_area_share": round(float(mask.mean()), 4)})
    return mask


def largest_block(mask, block=4):
    h, w = mask.shape
    hh, ww = h // block, w // block
    small = mask[:hh * block, :ww * block].reshape(hh, block, ww, block).any(axis=(1, 3))
    seen = np.zeros_like(small)
    best = None
    best_n = 0
    ys, xs = np.nonzero(small)
    for y0, x0 in zip(ys.tolist(), xs.tolist()):
        if seen[y0, x0]:
            continue
        q = deque([(y0, x0)])
        seen[y0, x0] = True
        comp = []
        while q:
            y, x = q.popleft()
            comp.append((y, x))
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < hh and 0 <= nx < ww and small[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    q.append((ny, nx))
        if len(comp) > best_n:
            best_n = len(comp)
            best = comp
    return best or [], best_n, (hh, ww)


def label_row(color, clf=None):
    """把一行像素的中位色判给事实卡里声明的角色（或 other）。

    v2 在这里写死了 Aster 01 的色相规则；v3 交给事实卡的调色板锚点，
    换一件商品只换 JSON。
    """
    return (clf or CLF).classify(color)


def spans_of(labels, name, min_len=3):
    out, start = [], None
    for i, item in enumerate(labels):
        if item == name:
            if start is None:
                start = i
        else:
            if start is not None:
                if i - start >= min_len:
                    out.append((start, i - 1))
                start = None
    if start is not None and len(labels) - start >= min_len:
        out.append((start, len(labels) - 1))
    return out


def measure(path: Path, card=None, clf=None) -> dict:
    clf = clf or CLF
    with Image.open(path) as im:
        arr = np.asarray(im.convert("RGB")).astype(np.float64)
    h, w, _ = arr.shape
    diag: dict = {}
    mask = build_mask(arr, diag)
    comp, nblocks, grid = largest_block(mask)
    if not comp:
        raise RuntimeError("未找到主体连通域：" + str(path))
    comp_small = np.zeros(grid, dtype=bool)
    for cy, cx in comp:
        comp_small[cy, cx] = True
    comp_full = np.kron(comp_small, np.ones((4, 4), dtype=bool))[:h, :w]
    extra = float((mask & ~comp_full).sum()) / float(max(1, mask.sum()))
    gy = [c[0] for c in comp]
    gx = [c[1] for c in comp]
    y0, y1 = min(gy) * 4, min(h - 1, max(gy) * 4 + 3)
    x0, x1 = min(gx) * 4, min(w - 1, max(gx) * 4 + 3)
    sub = mask[y0:y1 + 1, x0:x1 + 1]
    subarr = arr[y0:y1 + 1, x0:x1 + 1]
    rows = []
    for i in range(sub.shape[0]):
        xs = np.nonzero(sub[i])[0]
        if xs.size < 5:
            rows.append(None)
            continue
        rows.append({"color": np.median(subarr[i, xs], axis=0),
                     "x0": int(xs[0]), "x1": int(xs[-1])})
    labels = ["gap" if r is None else label_row(r["color"], clf) for r in rows]
    total_h = len(rows)
    widths = np.array([0 if r is None else (r["x1"] - r["x0"] + 1) for r in rows], dtype=float)
    width_max = int(widths.max())

    orange_spans = spans_of(labels, "orange")
    dark_spans = spans_of(labels, "dark")
    teal_spans = spans_of(labels, "teal")
    orange = max(orange_spans, key=lambda s: s[1] - s[0]) if orange_spans else None
    teal = max(teal_spans, key=lambda s: s[1] - s[0]) if teal_spans else None
    sleeve = None
    if teal:
        below = [s for s in dark_spans if s[0] > teal[1]]
        sleeve = max(below, key=lambda s: s[1] - s[0]) if below else None
    lid_h = orange[0] if orange else None
    teal_h = (teal[1] - teal[0] + 1) if teal else None
    sleeve_h = (sleeve[1] - sleeve[0] + 1) if sleeve else None
    body_h = (teal_h or 0) + (sleeve_h or 0)

    # F3 筋条：只数"防滑套上沿接缝之下"的凸脊，避免把套顶接缝算成一条筋。
    rib_ridges = []
    rib_grooves = []
    seam_row = None
    if sleeve:
        seam_row = sleeve[0]
        x0r = rows[sleeve[0]]["x0"]
        x1r = rows[sleeve[0]]["x1"]
        cen0 = max(0, int((x0r + x1r) / 2 - 60))
        cen1 = min(sub.shape[1] - 1, int((x0r + x1r) / 2 + 60))
        prof = []
        for i in range(sleeve[0], sleeve[1] + 1):
            seg = subarr[i, cen0:cen1 + 1]
            prof.append(float((seg[:, 0] * 0.299 + seg[:, 1] * 0.587
                               + seg[:, 2] * 0.114).mean()))
        prof = np.array(prof)
        if len(prof) > 5:
            smooth = np.convolve(prof, np.ones(3) / 3.0, mode="same")
            base = float(np.median(smooth))
            def intervals(sign, thresh):
                out = []
                start = None
                for i, v in enumerate(smooth):
                    hit = (v - base) >= thresh if sign > 0 else (base - v) >= thresh
                    if hit and start is None:
                        start = i
                    elif not hit and start is not None:
                        out.append((start + sleeve[0], i - 1 + sleeve[0]))
                        start = None
                if start is not None:
                    out.append((start + sleeve[0], len(smooth) - 1 + sleeve[0]))
                return [s for s in out if s[1] - s[0] + 1 >= 2]
            ridges = intervals(+1, 3.0)
            grooves = intervals(-1, 3.0)
            # 合并被接缝切开的相邻凸脊
            merged = []
            for s in ridges:
                if merged and s[0] - merged[-1][1] <= 6:
                    merged[-1] = (merged[-1][0], s[1])
                else:
                    merged.append(s)
            sleeve_h = sleeve[1] - sleeve[0] + 1
            # 计数规则（写进事实卡）：只数防滑套上沿接缝之下、且不在套底 18% 区间的凸脊。
            # 套底那条凸脊是 F6 的防滑圈，不是 F3 的筋。
            lo = seam_row + 12
            hi = seam_row + int(sleeve_h * 0.82)
            rib_ridges = [(s, e) for s, e in merged if lo <= s <= hi]
            base_ring = [(s, e) for s, e in merged if s > hi]
            rib_grooves = [g for g in grooves if lo <= g[0] <= hi]
            bottom_ring_rows = [[int(s), int(e)] for s, e in base_ring]

    teal_rows = teal[0] if teal else 0
    body_rows = widths[teal_rows:sleeve[1] + 1] if (teal and sleeve) else widths
    body_med = float(np.median(body_rows[body_rows > 0]))
    body_protrusion = float(body_rows.max() - body_med) / body_med
    lid_overhang = float(widths[:max(1, lid_h or 1)].max() - body_med) / body_med
    # F6 底部平直：主体中央 60% 列上，轮廓最低点的高度离散度占主体宽度的比例。
    xa = int(x0 + width_max * 0.20)
    xb = int(x0 + width_max * 0.80)
    lowest = []
    for x in range(xa, xb + 1):
        col = np.nonzero(mask[:, x])[0]
        if col.size:
            lowest.append(int(col[-1]))
    bottom_spread = (max(lowest) - min(lowest)) if lowest else None
    bottom_spread_share = None if bottom_spread is None else round(bottom_spread / width_max, 4)
    # F8 代理指标：主体内部的小块高梯度连通域个数（文字/伪标签/水印的形态特征）。
    # 它只是代理，不是 OCR；F8 的最终判据仍是人工核对"外表无文字"。
    gsub = lum_of(subarr)
    mag = np.sqrt(np.gradient(gsub, axis=0) ** 2 + np.gradient(gsub, axis=1) ** 2)
    inside = comp_full[y0:y1 + 1, x0:x1 + 1]
    thr = 40.0
    hot = (mag > thr) & inside
    hot[:3, :] = hot[-3:, :] = False
    hot[:, :3] = hot[:, -3:] = False
    seen = np.zeros_like(hot)
    text_blobs = 0
    blob_rows, blob_cols = np.nonzero(hot)
    for by, bx in zip(blob_rows.tolist(), blob_cols.tolist()):
        if seen[by, bx]:
            continue
        q = deque([(by, bx)])
        seen[by, bx] = True
        size = 0
        while q:
            cy, cx = q.popleft()
            size += 1
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < hot.shape[0] and 0 <= nx < hot.shape[1] and hot[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    q.append((ny, nx))
        if 4 <= size <= 400:
            text_blobs += 1

    def palette_check(name):
        if name == "teal":
            span = teal
        elif name == "sleeve":
            span = sleeve
        else:
            span = orange
        if not span:
            return None
        cols = np.array([rows[i]["color"] for i in range(span[0], span[1] + 1)
                         if rows[i] is not None])
        med = np.median(cols, axis=0)
        return "#%02X%02X%02X" % tuple(int(round(v)) for v in med)

    measured = {k: palette_check(k) for k in ("teal", "sleeve", "orange")}
    trim_share = None if not orange else round((orange[1] - orange[0] + 1) / total_h, 4)
    # 规范量测名 —— 事实卡里的 machine_checks.metric 指的就是这些键。
    metrics = {
        "aspect_h_over_w": round(total_h / max(1, width_max), 3),
        "body_upper_share": None if not body_h else round(teal_h / body_h, 4),
        "body_lower_share": None if not body_h else round(sleeve_h / body_h, 4),
        "upper_color_delta_e": (None if not measured.get("teal")
                                else round(clf.delta_e_to("teal", fc.hex_to_rgb(measured["teal"])), 2)),
        "rib_count": len(rib_ridges),
        "lid_share": None if lid_h is None else round(lid_h / total_h, 4),
        "trim_span_count": len(orange_spans),
        "trim_share": trim_share,
        "trim_top_position": None if not orange else round(orange[0] / total_h, 4),
        "bottom_spread_share": bottom_spread_share,
        "bottom_ring_present": 1 if bottom_ring_rows else 0,
        "body_protrusion": round(body_protrusion, 4),
        "extra_area_share": round(extra, 4),
        "text_proxy_blobs": text_blobs,
    }
    return {
        "file": str(path), "read_at": now_iso(),
        "image_size": [w, h], "diagnostics": diag,
        "metrics": metrics,
        "object_size": [int(width_max), int(total_h)],
        "F1_ratio": round(float(width_max) / max(1, total_h), 3),
        "F1_ratio_h_over_w": round(total_h / max(1, width_max), 3),
        "F1_target": declared_of("F1", "aspect_h_over_w"),
        "F2F3_teal_share": None if not body_h else round(teal_h / body_h, 4),
        "F2F3_sleeve_share": None if not body_h else round(sleeve_h / body_h, 4),
        "F2F3_target_teal": declared_of("F2", "body_upper_share"),
        "F3_rib_ridges_below_seam": len(rib_ridges),
        "F3_rib_ridge_rows": [[int(s), int(e)] for s, e in rib_ridges],
        "F3_grooves_below_seam": len(rib_grooves),
        "F3_sleeve_seam_row": None if seam_row is None else int(seam_row),
        "F3_bottom_ring_rows": bottom_ring_rows,
        "F4_lid_share": None if lid_h is None else round(lid_h / total_h, 4),
        "F4_limit": pass_max("lid_share"),
        "F5_orange_share": trim_share,
        "F5_orange_top_share": None if not orange else round(orange[0] / total_h, 4),
        "F5_orange_span_count": len(orange_spans),
        "F5_limit": pass_max("trim_share"),
        "F6_bottom_spread_px": bottom_spread,
        "F6_bottom_spread_share": bottom_spread_share,
        "F7_body_protrusion": round(body_protrusion, 4),
        "F7_lid_overhang": round(lid_overhang, 4),
        "F7_extra_area_share": round(extra, 4),
        "F8_text_proxy_blobs": text_blobs,
        "measured_colors": measured,
        "design_colors": {"teal": PALETTE.get("teal"), "sleeve": PALETTE.get("dark"),
                          "orange": PALETTE.get("orange")},
        "rows": {"total": total_h, "lid": lid_h, "teal": teal_h, "sleeve": sleeve_h,
                 "origin_y": y0, "origin_x": x0},
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--src", default="evals/product-demo/fixture-design")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", default="A,B,C")
    args = ap.parse_args()
    project = Path(args.project)
    rows = []
    for cid in [s.strip() for s in args.ids.split(",") if s.strip()]:
        rows.append(measure(project / args.src / cid / "raw.png"))
    out = Path(args.out)
    if not out.is_absolute():
        out = project / args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "measure.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                     encoding="utf-8", newline="\n")
    lines = ["# Aster 01 候选 F1–F8 确定性量测（v2）", "", "生成时间：" + now_iso(), ""]
    for r in rows:
        cid = Path(r["file"]).parent.name
        lines += [
            "## 候选 " + cid, "",
            "| 项 | 实测 | 设计/上限 |", "|---|---|---|",
            "| F1 高宽比（高/宽） | " + str(r["F1_ratio_h_over_w"]) + " | " + str(r["F1_target"]) + " |",
            "| F2/F3 上段占杯体 | " + str(r["F2F3_teal_share"]) + " | " + str(r["F2F3_target_teal"]) + " |",
            "| F2/F3 下段占杯体 | " + str(r["F2F3_sleeve_share"]) + " | "
            + str(round(1 - r["F2F3_target_teal"], 2)) + " |",
            "| F3 接缝下凸脊数（筋） | " + str(r["F3_rib_ridges_below_seam"]) + " | 3 |",
            "| F4 杯盖占整器高 | " + str(r["F4_lid_share"]) + " | ≤ " + str(r["F4_limit"]) + " |",
            "| F5 橙环占整器高 | " + str(r["F5_orange_share"]) + " | ≤ " + str(r["F5_limit"]) + " |",
            "| F5 橙环上沿位置 | " + str(r["F5_orange_top_share"]) + " | 紧贴杯盖下方 |",
            "| F5 独立橙段数 | " + str(r["F5_orange_span_count"]) + " | 1 |",
            "| F6 底部轮廓高度离散（占主体宽） | " + str(r["F6_bottom_spread_share"]) + " | 接近 0（平底） |",
            "| F7 杯身最大凸出 | " + str(r["F7_body_protrusion"]) + " | 接近 0（无把手/提带） |",
            "| F7 杯盖外沿超出杯身 | " + str(r["F7_lid_overhang"]) + " | 可小量为正 |",
            "| F7 主体外像素占比 | " + str(r["F7_extra_area_share"]) + " | 接近 0 |",
            "| F8 小高梯度块（文字代理） | " + str(r["F8_text_proxy_blobs"]) + " | 接近 0 |",
            "| 实测色 | " + json.dumps(r["measured_colors"], ensure_ascii=False)
            + " | " + json.dumps(r["design_colors"], ensure_ascii=False) + " |",
            "",
        ]
    (out / "measure.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    for r in rows:
        print("%s  高宽比=%.2f  上段=%.3f  筋=%s  杯盖=%.3f  橙环=%.4f  底散=%s  身凸=%.4f  盖沿=%.4f" % (
            Path(r["file"]).parent.name, r["F1_ratio_h_over_w"], r["F2F3_teal_share"] or -1,
            r["F3_rib_ridges_below_seam"], r["F4_lid_share"] or -1,
            r["F5_orange_share"] or -1, r["F6_bottom_spread_share"],
            r["F7_body_protrusion"], r["F7_lid_overhang"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
