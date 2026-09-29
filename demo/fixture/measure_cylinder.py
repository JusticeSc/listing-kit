# -*- coding: utf-8 -*-
"""量测适配器 · metric_profile = `cylinder-v1`。

它是什么：把「单个圆柱形杯体 + 旋盖 + 下段防滑套 + 一圈装饰环」这一**类**商品的像素，
        量成事实卡里那些规范量测名。几何假设属于这一类商品，写在这里；
        具体商品的颜色、比例、筋条数、阈值，一个都不写在这里。

它不是什么：不是通用量测器。事实卡声明 `metric_profile: cylinder-v1` 才归它管；
        声明别的 profile 就抛 ProfileMismatch，而不是硬算出一堆看似合理的数字。

怎么做到「换商品只换 JSON」：调色板按事实卡声明的**语义槽位**取色（body_upper /
body_lower / trim），不认 `teal` / `orange` 这种商品专属角色名。换商品时角色名、色值、
阈值、声明值全在卡里变，本文件不动。

为什么没有模块级 CARD：模块级状态会让 `measure(card=别的卡)` 只改一半 ——
外壳换了卡，量测仍按旧卡算。这里所有阈值都从参数穿的卡上现取。
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image

PROFILE = "cylinder-v1"
# 这一 profile 需要的语义槽位。缺哪个就在开跑前报出来，而不是量到一半变成 None。
REQUIRED_SLOTS = ("body_upper", "body_lower", "trim")


class ProfileMismatch(Exception):
    """事实卡声明的 metric_profile 不是本适配器支持的那一个。"""


def slot_roles(card: dict) -> dict:
    """事实卡 → {槽位: 角色名}。缺槽位直接报错。"""
    found = {}
    for role in card.get("palette", {}).get("roles", []):
        slot = role.get("slot")
        if slot:
            found[slot] = role["role"]
    missing = [s for s in REQUIRED_SLOTS if s not in found]
    if missing:
        raise ProfileMismatch("事实卡缺 " + PROFILE + " 需要的语义槽位：" + "、".join(missing))
    return found


def require_profile(card: dict) -> None:
    got = card.get("metric_profile")
    if got != PROFILE:
        raise ProfileMismatch("本适配器只支持 metric_profile=" + PROFILE
                              + "，收到的是 " + repr(got))


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def lum_of(arr):
    return arr[:, :, 0] * 0.299 + arr[:, :, 1] * 0.587 + arr[:, :, 2] * 0.114


def build_mask(arr, diag=None):
    """主体 = 饱和像素 或 显著暗于背景的像素。背景与浅投影是低饱和中性灰，被排除。"""
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

def expand_blocks(comp_small: np.ndarray, h: int, w: int) -> np.ndarray:
    """把 4x4 网格掩膜展开回原图尺寸。

    为什么不用 np.kron(...)[:h, :w]：网格是 h//4 x w//4（向下取整），kron 的结果
    是 4*(h//4) x 4*(w//4) —— 当 h 或 w 不是 4 的倍数时它比原图小，后面
    comp_full[y0:y1+1, x0:x1+1] 与同范围裁出的 subarr 形状不一致，直接在广播上
    炸掉。棚拍夹具恰好都是 1344x1344，所以这条缺陷长期没被触发；裁剪图、别的
    尺寸的商品图一进来就崩，而崩的位置离原因很远。

    本函数只对齐形状，不改语义：网格覆盖到的区域逐块回填 4x4，尾部不足一块的
    行列保持 False —— 与旧实现在 4 的倍数输入上逐值相同（见 self-test 的 T2）。
    """
    out = np.zeros((h, w), dtype=bool)
    if comp_small.size:
        ph = min(h, comp_small.shape[0] * 4)
        pw = min(w, comp_small.shape[1] * 4)
        out[:ph, :pw] = np.kron(comp_small, np.ones((4, 4), dtype=bool))[:ph, :pw]
    return out


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


def measure(image_path: Path, card: dict, clf=None) -> dict:
    """量一张图 → 规范量测名。阈值与声明值一概不在这里读，判定由 factcard.evaluate 做。"""
    require_profile(card)
    roles = slot_roles(card)
    import factcard as fc

    clf = clf or fc.PaletteClassifier(card["palette"])
    upper, lower, trim = roles["body_upper"], roles["body_lower"], roles["trim"]

    with Image.open(image_path) as im:
        arr = np.asarray(im.convert("RGB")).astype(np.float64)
    h, w, _ = arr.shape
    diag: dict = {}
    mask = build_mask(arr, diag)
    comp, nblocks, grid = largest_block(mask)
    if not comp:
        raise RuntimeError("未找到主体连通域：" + str(image_path))
    comp_small = np.zeros(grid, dtype=bool)
    for cy, cx in comp:
        comp_small[cy, cx] = True
    comp_full = expand_blocks(comp_small, h, w)
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
    labels = ["gap" if r is None else clf.classify(r["color"]) for r in rows]
    total_h = len(rows)
    widths = np.array([0 if r is None else (r["x1"] - r["x0"] + 1) for r in rows], dtype=float)
    width_max = int(widths.max())

    trim_spans = spans_of(labels, trim)
    lower_spans = spans_of(labels, lower)
    upper_spans = spans_of(labels, upper)
    trim_span = max(trim_spans, key=lambda s: s[1] - s[0]) if trim_spans else None
    upper_span = max(upper_spans, key=lambda s: s[1] - s[0]) if upper_spans else None
    sleeve = None
    if upper_span:
        below = [s for s in lower_spans if s[0] > upper_span[1]]
        sleeve = max(below, key=lambda s: s[1] - s[0]) if below else None
    lid_h = trim_span[0] if trim_span else None
    upper_h = (upper_span[1] - upper_span[0] + 1) if upper_span else None
    sleeve_h = (sleeve[1] - sleeve[0] + 1) if sleeve else None
    body_h = (upper_h or 0) + (sleeve_h or 0)

    # 筋条：只数防滑套上沿接缝之下、且不在套底 18% 区间内的凸脊。
    # 套底那条凸脊是底部防滑圈（F6），不是筋（F3）。这是本 profile 的几何约定。
    rib_ridges, rib_grooves, base_ring, seam_row = [], [], [], None
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
                out, start = [], None
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

            merged = []
            for s in intervals(+1, 3.0):
                if merged and s[0] - merged[-1][1] <= 6:
                    merged[-1] = (merged[-1][0], s[1])
                else:
                    merged.append(s)
            sleeve_h = sleeve[1] - sleeve[0] + 1
            lo = seam_row + 12
            hi = seam_row + int(sleeve_h * 0.82)
            rib_ridges = [(s, e) for s, e in merged if lo <= s <= hi]
            base_ring = [(s, e) for s, e in merged if s > hi]
            rib_grooves = [g for g in intervals(-1, 3.0) if lo <= g[0] <= hi]

    upper_rows = upper_span[0] if upper_span else 0
    body_rows = widths[upper_rows:sleeve[1] + 1] if (upper_span and sleeve) else widths
    body_med = float(np.median(body_rows[body_rows > 0]))
    body_protrusion = float(body_rows.max() - body_med) / body_med
    lid_overhang = float(widths[:max(1, lid_h or 1)].max() - body_med) / body_med

    # 平底：主体中央 60% 列上，轮廓最低点的高度离散度占主体宽度的比例。
    xa = int(x0 + width_max * 0.20)
    xb = int(x0 + width_max * 0.80)
    lowest = []
    for x in range(xa, xb + 1):
        col = np.nonzero(mask[:, x])[0]
        if col.size:
            lowest.append(int(col[-1]))
    bottom_spread = (max(lowest) - min(lowest)) if lowest else None
    bottom_spread_share = None if bottom_spread is None else round(bottom_spread / width_max, 4)

    # 文字代理：主体内部的小块高梯度连通域个数。只是形态代理，不是 OCR；
    # 实测会把筋条边缘算进来，所以它登记在 facts[].machine_proxy 里，不参与判定。
    gsub = lum_of(subarr)
    mag = np.sqrt(np.gradient(gsub, axis=0) ** 2 + np.gradient(gsub, axis=1) ** 2)
    inside = comp_full[y0:y1 + 1, x0:x1 + 1]
    if inside.shape != gsub.shape:      # gsub 来自同一段裁剪，形状必须逐维一致
        raise RuntimeError(
            "主体掩膜与裁剪区域形状不一致：" + str(inside.shape) + " vs "
            + str(gsub.shape) + "（" + str(image_path) + "）"
            " —— 这类不一致必须报错，不能带着错形状继续算")
    hot = (mag > 40.0) & inside
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
                if (0 <= ny < hot.shape[0] and 0 <= nx < hot.shape[1]
                        and hot[ny, nx] and not seen[ny, nx]):
                    seen[ny, nx] = True
                    q.append((ny, nx))
        if 4 <= size <= 400:
            text_blobs += 1

    def median_hex(span):
        if not span:
            return None
        cols = np.array([rows[i]["color"] for i in range(span[0], span[1] + 1)
                         if rows[i] is not None])
        med = np.median(cols, axis=0)
        return "#%02X%02X%02X" % tuple(int(round(v)) for v in med)

    measured = {"body_upper": median_hex(upper_span), "body_lower": median_hex(sleeve),
                "trim": median_hex(trim_span)}
    declared = {r["slot"]: r["hex"] for r in card["palette"]["roles"] if r.get("slot")}
    trim_share = None if not trim_span else round((trim_span[1] - trim_span[0] + 1) / total_h, 4)
    upper_delta_e = (None if not measured["body_upper"]
                     else round(clf.delta_e_to(upper, fc.hex_to_rgb(measured["body_upper"])), 2))

    metrics = {
        "aspect_h_over_w": round(total_h / max(1, width_max), 3),
        "body_upper_share": None if not body_h else round(upper_h / body_h, 4),
        "body_lower_share": None if not body_h else round(sleeve_h / body_h, 4),
        "upper_color_delta_e": upper_delta_e,
        "rib_count": len(rib_ridges),
        "lid_share": None if lid_h is None else round(lid_h / total_h, 4),
        "trim_span_count": len(trim_spans),
        "trim_share": trim_share,
        "trim_top_position": None if not trim_span else round(trim_span[0] / total_h, 4),
        "bottom_spread_share": bottom_spread_share,
        "bottom_ring_present": 1 if base_ring else 0,
        "body_protrusion": round(body_protrusion, 4),
        "extra_area_share": round(extra, 4),
        "text_proxy_blobs": text_blobs,
    }
    return {
        "file": str(image_path),
        "read_at": now_iso(),
        "image_size": [w, h],
        "metric_profile": PROFILE,
        "diagnostics": diag,
        "metrics": metrics,
        "object_size": [int(width_max), int(total_h)],
        "slots": roles,
        "measured_colors": measured,
        "declared_colors": declared,
        "geometry": {
            "origin": [int(x0), int(y0)],
            "body_rows": int(total_h),
            "upper_rows": upper_h,
            "sleeve_rows": sleeve_h,
            "lid_rows": lid_h,
            "sleeve_seam_row": None if seam_row is None else int(seam_row),
            "rib_ridges": [[int(s), int(e)] for s, e in rib_ridges],
            "rib_grooves": len(rib_grooves),
            "bottom_ring_rows": [[int(s), int(e)] for s, e in base_ring],
            "bottom_spread_px": bottom_spread,
            "body_protrusion": round(body_protrusion, 4),
            "lid_overhang": round(lid_overhang, 4),
            "text_proxy_blobs": text_blobs,
        },
    }

# ------------------------------------------------------------------ 自检
def _old_expand_blocks(comp_small: np.ndarray, h: int, w: int) -> np.ndarray:
    """修复前的实现，只在自检里当变异体用：证明这套自检红得起。"""
    return np.kron(comp_small, np.ones((4, 4), dtype=bool))[:h, :w]


def _grid(size: int) -> int:
    return max(1, size // 4)


def _blank_grid(h: int, w: int) -> np.ndarray:
    return np.zeros((_grid(h), _grid(w)), dtype=bool)


def _card_path(project: Path, sku: str | None):
    base = project / "demo" / "fixture"
    if sku:
        return base / sku / "product.json"
    cands = sorted(p.parent for p in base.glob("*/product.json"))
    return (cands[0] / "product.json") if cands else None


def selftest(project: Path, sku: str | None = None) -> int:
    """量测器的尺寸契约自检。

    缺陷背景：基准块是 4x4，网格按 h//4、w//4 向下取整。np.kron(...)[:h, :w]
    在 h 或 w 不是 4 的倍数时比原图小，后面 comp_full[y0:y1+1, x0:x1+1]
    与同范围裁出的 subarr 形状不一致，直接在广播上炸掉。棚拍夹具全是
    1344x1344，所以这条缺陷长期没被触发 —— 裁剪图或别的尺寸一进来就崩。

    自检必须同时证明两件事：修好之后非 4 倍数能量；把修复换回旧实现必须变红。
    """
    import json
    import sys as _sys
    import tempfile
    try:
        _sys.path.insert(0, str(Path(__file__).resolve().parent))
        import factcard as fc
    except Exception as exc:                    # noqa: BLE001
        print("自检环境不完整，无法导入 factcard：" + repr(exc))
        return 2

    problems: list = []
    global expand_blocks                # T4 变异要临时替换它

    # -- T1 形状契约：expand_blocks 的输出恒为原图尺寸 --
    sizes = [(1344, 1344), (1341, 1343), (1173, 370), (5, 5), (3, 3), (1, 1)]
    for h, w in sizes:
        small = _blank_grid(h, w)
        small[0, :] = True
        got = expand_blocks(small, h, w).shape
        if got != (h, w):
            problems.append("T1 形状契约：h=%d w=%d 得到 %s" % (h, w, got))
    print("  [%s] T1 形状契约：%d 组尺寸（含非 4 倍数）输出恒为原图尺寸"
          % ("OK  " if not problems else "FAIL", len(sizes)))

    # -- T2 4 倍数输入下与旧实现逐值相同（只对齐形状、不改语义的证据）--
    t2_bad = []
    for h, w in ((1344, 1344), (8, 12)):
        small = _blank_grid(h, w)
        small[1:, :] = True
        if not np.array_equal(_old_expand_blocks(small, h, w), expand_blocks(small, h, w)):
            t2_bad.append("h=%d w=%d 与旧实现不同" % (h, w))
    small = _blank_grid(1341, 1343)
    small[:, :] = True
    if _old_expand_blocks(small, 1341, 1343).shape == (1341, 1343):
        t2_bad.append("旧实现在 1341x1343 上形状竟然正确，自检抓不到该缺陷")
    problems += ["T2 语义不变：" + b for b in t2_bad]
    print("  [%s] T2 语义不变：4 倍数输入与旧实现逐值相同，且旧实现确在 1341x1343 上形状失真"
          % ("OK  " if not t2_bad else "FAIL"))

    # -- T3 端到端：基准图与非 4 倍数裁剪图 --
    card_path = _card_path(project, sku)
    pack_dir = project / "evals" / "product-demo" / "fixture-design" / "pack"
    man = pack_dir / "reference-manifest.json"
    if card_path is None or not card_path.exists() or not man.exists():
        print("  [SKIP] T3 端到端：缺事实卡或参考包 manifest（card=%s manifest=%s）"
              % (card_path, man))
        return 1 if problems else 0
    card = json.loads(card_path.read_text(encoding="utf-8"))
    view = json.loads(man.read_text(encoding="utf-8"))["views"][0]
    image = project / view["file"]

    with tempfile.TemporaryDirectory(prefix="measure_selftest_") as tmp:
        base = measure(image, card=card)
        base_report = fc.evaluate(base["metrics"], card)
        with Image.open(image) as im:
            w0, h0 = im.size
            crop_path = Path(tmp) / "cropped.png"
            im.crop((0, 0, w0 - 3, h0 - 1)).save(crop_path)
        cw, ch = Image.open(crop_path).size
        try:
            got = measure(crop_path, card=card)
            got_report = fc.evaluate(got["metrics"], card)
            deltas = {k: (None if base["metrics"].get(k) is None or got["metrics"].get(k) is None
                          else round(abs(base["metrics"][k] - got["metrics"][k]), 4))
                      for k in base["metrics"]}
            worst = max((v for v in deltas.values() if v is not None), default=0.0)
            same_overall = base_report["overall"] == got_report["overall"]
            if not same_overall:
                problems.append("T3 端到端：overall 从 %s 变成 %s"
                                % (base_report["overall"], got_report["overall"]))
            if worst > 0.01:
                problems.append("T3 端到端：裁剪后量测漂移过大 worst=%.4f" % worst)
            print("  [%s] T3 端到端：%dx%d overall=%s -> %dx%d overall=%s，逐指标最大漂移 %.4f"
                  % ("OK  " if same_overall and worst <= 0.01 else "FAIL",
                     w0, h0, base_report["overall"], cw, ch, got_report["overall"], worst))
        except Exception as exc:                # noqa: BLE001
            problems.append("T3 端到端：非 4 倍数裁剪图量测失败 %s: %s"
                            % (type(exc).__name__, exc))
            print("  [FAIL] T3 端到端：%dx%d 量测失败 %s: %s" % (cw, ch, type(exc).__name__, exc))
            crop_path = None

        # -- T4 变异：把修复换回旧实现，T3 必须变红 --
        if crop_path is not None:
            keep = expand_blocks
            expand_blocks = _old_expand_blocks
            caught = False
            try:
                measure(crop_path, card=card)
            except Exception:                   # noqa: BLE001
                caught = True
            finally:
                expand_blocks = keep
            if not caught:
                problems.append("T4 变异未被抓住：换回旧实现后非 4 倍数尺寸仍然量过去了")
            print("  [%s] T4 变异：换回旧实现后非 4 倍数裁剪图%s"
                  % ("OK  " if caught else "FAIL", "如期报错" if caught else "竟然量过去了"))

    print()
    if problems:
        print("自检未通过（%d 项）：" % len(problems))
        for p in problems:
            print("  - " + p)
        return 1
    print("自检：4/4 项成立（形状契约 / 语义不变 / 端到端 / 变异可抓）")
    return 0


def main(argv=None) -> int:
    import argparse
    import sys as _sys
    try:
        _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                           # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="cylinder-v1 量测适配器")
    ap.add_argument("mode", nargs="?", default="self-test", choices=["self-test"])
    ap.add_argument("--project", default=".")
    ap.add_argument("--sku", default=None)
    args = ap.parse_args(argv)
    return selftest(Path(args.project).resolve(), args.sku)


if __name__ == "__main__":
    raise SystemExit(main())
