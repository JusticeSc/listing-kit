#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""D1.5 探针：`cylinder-v1` 事实门在**场景图**上，判的到底是不是商品？

起因：首轮四张真实的图生图场景候选，机器判据全部 hard_fail
（aspect 1.40/2.46/1.33/3.10，extra_area_share 0.13-0.34），
但四张图里的商品在肉眼上与参考包一致。这两种说法必有一个错，
所以要做能证伪的对照，而不是各说各话。

对照设计（每一臂都断言：商品像素逐字节不变，只有底衬/背景变化）：

    fixture      浅灰无缝底                    已知全过（aspect 3.18）
    A1           底衬换成四张候选的**边缘中位色**（平坦、低饱和）
    A2           A1 再加斜向光斑与噪声
    A3           底衬换成从真实候选上**裁下来的石面纹理**（会带明暗与投影）

A1/A2 是"看起来像场景但没有明暗结构"的底衬；A3 才是真实场景的底衬条件。
三臂一起看，才能分清"任何非灰底衬都会坏"和"只有会进掩膜的底衬才会坏"。

本脚本只读参考包与候选图，写自己的对照图、掩膜叠加图与结果，**不碰**任何阈值。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import factcard as fc            # noqa: E402
import measure_cylinder as mc    # noqa: E402

CARD_PATH = PROJECT / "demo/fixture/aster-01/product.json"
FIXTURE = PROJECT / "evals/product-demo/fixture-design/pack/01-front-full.png"
CANDIDATE_DIR = PROJECT / "evals/product-demo/first-round/attempts"
OUT_DIR = PROJECT / "evals/product-demo/first-round/scope-control"

CANDIDATE_IDS = ["b0c9c907f875b918", "723ab2a69e19571d", "c75a6d09d6ea00df", "45ef384cb14bafbe"]
# 从候选图左下角裁的"纯地面"区域（远离商品）：x 60-460, y 1120-1330
PATCH = (60, 1120, 460, 1330)


def border_median(arr: np.ndarray) -> np.ndarray:
    h, w, _ = arr.shape
    band = max(4, int(min(h, w) * 0.03))
    border = np.concatenate([arr[:band].reshape(-1, 3), arr[-band:].reshape(-1, 3),
                             arr[:, :band].reshape(-1, 3), arr[:, -band:].reshape(-1, 3)])
    return np.median(border, axis=0)


def saturation(rgb) -> float:
    mx = float(np.max(rgb))
    return float((mx - float(np.min(rgb))) / max(mx, 1.0))


def mask_and_component(arr: np.ndarray):
    diag: dict = {}
    mask = mc.build_mask(arr, diag)
    comp, _, grid = mc.largest_block(mask)
    small = np.zeros(grid, dtype=bool)
    for cy, cx in comp:
        small[cy, cx] = True
    h, w, _ = arr.shape
    full = np.kron(small, np.ones((4, 4), dtype=bool))[:h, :w]
    return mask, full, diag


def bbox_of(mask: np.ndarray):
    ys, xs = np.nonzero(mask)
    if ys.size == 0:
        return None
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def overlay(arr: np.ndarray, mask: np.ndarray, comp: np.ndarray, path: Path) -> None:
    """掩膜可视化：命中掩膜=红，最大连通域轮廓=绿。看它到底圈住了什么。"""
    base = arr.astype(np.uint8).copy()
    hit = mask & ~comp
    base[hit] = (0.45 * base[hit] + 0.55 * np.array([255, 40, 40])).astype(np.uint8)
    edge = comp & ~np.pad(comp, 1)[:-2, 1:-1]
    base[edge] = (0.3 * base[edge] + 0.7 * np.array([0, 220, 0])).astype(np.uint8)
    Image.fromarray(base).save(path)


def key_metrics(image: Path, card: dict, clf, overlay_dir: Path | None = None) -> dict:
    arr = np.asarray(Image.open(image).convert("RGB")).astype(np.float64)
    mask, comp, diag = mask_and_component(arr)
    b = bbox_of(comp)
    h, w, _ = arr.shape
    side = slice(0, int(w * 0.18))
    measured = mc.measure(image, card, clf)
    report = fc.evaluate(measured["metrics"], card)
    if overlay_dir is not None:
        overlay_dir.mkdir(parents=True, exist_ok=True)
        overlay(arr, mask, comp, overlay_dir / (image.parent.name + "-" + image.stem + "-mask.png"))
    return {
        "image": str(image.relative_to(PROJECT)).replace("\\", "/"),
        "verdict": report["overall"],
        "aspect_h_over_w": measured["metrics"].get("aspect_h_over_w"),
        "body_upper_share": measured["metrics"].get("body_upper_share"),
        "body_lower_share": measured["metrics"].get("body_lower_share"),
        "extra_area_share": measured["metrics"].get("extra_area_share"),
        "body_protrusion": measured["metrics"].get("body_protrusion"),
        "trim_span_count": measured["metrics"].get("trim_span_count"),
        "border_bg_rgb": diag.get("bg_rgb"),
        "border_bg_saturation": round(saturation(diag.get("bg_rgb") or [0, 0, 0]), 4),
        "v1_mask_share": diag.get("mask_area_share"),
        "mask_share_left_18pct": round(float(mask[:, side].mean()), 4),
        "main_component_bbox": b,
        "main_component_size": None if not b else [b[2] - b[0] + 1, b[3] - b[1] + 1],
        "failed_facts": [f["id"] for f in report["facts"] if f["verdict"] == "hard_fail"],
    }


def build_controls(fixture_arr: np.ndarray, product: np.ndarray, flat_tone: np.ndarray,
                   patch: np.ndarray, out_dir: Path):
    h, w, _ = fixture_arr.shape
    bg = ~product
    rows = []

    def emit(name: str, arr: np.ndarray):
        assert np.array_equal(arr[product], fixture_arr[product]), "商品像素被改动了，对照无效"
        assert not np.array_equal(arr[bg], fixture_arr[bg]), "底衬没变，对照无效"
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / (name + ".png")
        Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(p)
        rows.append((name, p))

    a1 = fixture_arr.copy()
    a1[bg] = flat_tone
    emit("A1-flat-tone", a1)

    a2 = a1.copy()
    yy, xx = np.mgrid[0:h, 0:w]
    band = np.clip(1.0 - np.abs((xx * 0.55 + yy) - (w * 0.30)) / (w * 0.45), 0.0, 1.0)
    lift = (band * 26.0)[..., None] * np.ones((1, 1, 3))
    a2[bg] = np.clip(a2[bg] + lift[bg], 0, 255)
    rng = np.random.default_rng(20260926)
    a2[bg] = np.clip(a2[bg] + rng.normal(0.0, 4.0, size=(h, w, 1))[bg], 0, 255)
    emit("A2-flat-tone-light-patch", a2)

    a3 = fixture_arr.copy()
    ph, pw, _ = patch.shape
    tiled = np.tile(patch, (h // ph + 1, w // pw + 1, 1))[:h, :w]
    a3[bg] = tiled[bg]
    emit("A3-real-floor-texture", a3)
    return rows


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                              # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="D1.5 事实门适用范围对照")
    ap.add_argument("--out", default=str(OUT_DIR))
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    overlay_dir = out_dir / "mask-overlay"

    card = fc.load_card(CARD_PATH)
    clf = fc.PaletteClassifier(card["palette"])
    fixture_arr = np.asarray(Image.open(FIXTURE).convert("RGB")).astype(np.float64)
    _, product, _ = mask_and_component(fixture_arr)

    first = CANDIDATE_DIR / CANDIDATE_IDS[0] / "raw.png"
    first_arr = np.asarray(Image.open(first).convert("RGB")).astype(np.float64)
    flat_tone = border_median(first_arr)
    x0, y0, x1, y1 = PATCH
    patch = first_arr[y0:y1, x0:x1]

    controls = [("fixture-plain-gray", FIXTURE)] + build_controls(
        fixture_arr, product, flat_tone, patch, out_dir)

    rows = []
    for name, path in controls:
        row = key_metrics(Path(path), card, clf, overlay_dir)
        row["arm"] = name
        rows.append(row)
    candidates = [key_metrics(CANDIDATE_DIR / cid / "raw.png", card, clf, overlay_dir)
                  for cid in CANDIDATE_IDS if (CANDIDATE_DIR / cid / "raw.png").is_file()]

    result = {
        "probe": "D1.5 事实门适用范围对照",
        "question": "cylinder-v1 在场景图上的判定，是不是商品的函数？",
        "design": "商品像素逐字节不变，只替换商品分量之外的底衬；三臂底衬条件递增",
        "flat_tone_rgb": [round(float(v), 1) for v in flat_tone],
        "flat_tone_saturation": round(saturation(flat_tone), 4),
        "floor_patch_from": {"image": str(first.relative_to(PROJECT)).replace("\\", "/"),
                             "box": PATCH},
        "arms": rows,
        "candidates": candidates,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                         encoding="utf-8", newline="\n")

    print("D1.5 事实门适用范围对照（商品像素逐字节不变，只换底衬）")
    print("-" * 96)
    print("%-30s %-10s %-9s %-9s %-9s %-14s %s" % (
        "臂", "判定", "aspect", "extra", "掩膜占比", "左18%掩膜占比", "主连通域宽高"))
    for row in rows:
        print("%-30s %-10s %-9s %-9s %-9s %-14s %s" % (
            row["arm"], row["verdict"], row["aspect_h_over_w"], row["extra_area_share"],
            row["v1_mask_share"], row["mask_share_left_18pct"], row["main_component_size"]))
    print("-" * 96)
    print("四张真实场景候选：")
    for row in candidates:
        print("%-14s %-10s aspect=%-7s extra=%-7s 掩膜=%-7s 失败事实=%s" % (
            row["image"].split("/")[-2][:12], row["verdict"], row["aspect_h_over_w"],
            row["extra_area_share"], row["v1_mask_share"], row["failed_facts"]))
    print("\n掩膜叠加图：%s" % overlay_dir)
    print("结果：%s" % (out_dir / "result.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())