r"""守卫探针③：把「同源 + JPEG 噪声」和「真的换了主体」**量出来**，再定阈值。

为什么要做这件事：一个没有实测依据的阈值，和一句"我觉得应该没问题"没有区别。
`tools/verify_m3.py` 的断言 C（位置 1/2/3 的产品像素同源）用的就是这个阈值，
所以标定过程必须留在这里 —— 否则没人能回答"这个数是怎么来的"。

做法：取一份已出的 run，把它的 `subject.png` 与**另一种抠法**（floodfill）的结果
分别按 paste_box 贴回去，量两者的逐像素差值。两条分布分开得越远，阈值越安全。

用法：python tools/calibrate_subject_diff.py [run 目录]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import synth  # noqa: E402


def newest_run() -> Path | None:
    runs = [p for p in (ROOT / "out").glob("*") if (p / "run.jsonl").exists()]
    return max(runs, key=lambda p: p.stat().st_mtime) if runs else None


def main(argv: list[str]) -> int:
    run = Path(argv[1]) if len(argv) > 1 else newest_run()
    if not run or not (run / "run.jsonl").exists():
        print("找不到 run.jsonl：请先跑一次 "
              "`python run.py --product examples/product_demo.json`")
        return 2

    recs = [json.loads(x) for x in
            (run / "run.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    renders = {r["slot_id"]: r for r in recs if r["stage"] == "render"}
    subject = next((r for r in recs if r["stage"] == "subject"), None)
    if not subject:
        print(f"{run.name} 里没有 subject 记录 —— 这一轮没有需要主体的坑位")
        return 2

    src = Image.open(subject["path"]).convert("RGBA")

    # 造一个"不同源"的主体：换一种抠图方式（floodfill 而不是 rembg）
    front_path = ROOT / "examples" / "input" / "cup_source.jpg"
    alt, meta = synth.remove_background(Image.open(front_path), mode="floodfill")
    bbox = synth.alpha_bbox(alt)
    alt = alt.crop(bbox) if bbox else alt
    print(f"run {run.name}")
    print(f"原主体 {src.size} · 另一种抠法 {alt.size} · 抠法={meta.get('mode')}\n")

    def diff_vs(gen: Image.Image, box, out_path) -> tuple[int, float]:
        x, y, w, h = box
        actual = np.asarray(Image.open(out_path).convert("RGB")).astype(np.int16)
        actual = actual[y:y + h, x:x + w]
        img = gen.resize((w, h), Image.LANCZOS)
        exp = np.asarray(img.convert("RGB")).astype(np.int16)
        mask = np.asarray(img.getchannel("A")) >= 250
        d = np.abs(actual - exp)[mask]
        return int(d.max()), float(d.mean())

    for sid in (1, 2, 3):
        r = renders.get(sid)
        if not r:
            continue
        box = (r.get("detail") or {}).get("paste_box")
        if not box:
            continue
        same = diff_vs(src, box, r["path"])
        other = diff_vs(alt, box, r["path"])
        print(f"位置 {sid}  box={box}")
        print(f"    同源（subject.png）      最大差 {same[0]:>4}  平均差 {same[1]:>7.2f}")
        print(f"    不同源（另一种抠图结果） 最大差 {other[0]:>4}  平均差 {other[1]:>7.2f}")

    print("\n判据：两组要分得开。verify_m3 的断言 C 取的是 同源组的上界"
          "（留一档余量），而不是两者的中点 —— 中点会被离群值牵着走。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
