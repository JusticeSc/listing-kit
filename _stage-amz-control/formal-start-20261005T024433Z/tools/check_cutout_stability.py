r"""本机抠图稳定性自检 —— 连续抠 N 次，看会不会中途抓不到内存。

为什么需要这么个工具
--------------------
    工具在抠图**推理失败**时不再静默降级 floodfill（那会换掉像素，见
    synth.remove_background），所以"这台机器能不能稳定抠完整批"变成了一个
    运营要能自己回答的问题 —— 而不是出了红字才来猜。

    一个满素材 run 里要抠 3 次（主体 / 内容物 / 竞品），加上重做会更多。
    本脚本就照这个强度连抠 N 次，并打印每一次的：
        mode      实际走的哪条路（rembg / floodfill）
        attempts  试了几次才成功（>1 说明这台机器偶发不稳）
        耗时      rembg 单次推理本来就是十几秒，这是素材的固有成本

用法：
    python tools/check_cutout_stability.py            # 默认 4 次
    python tools/check_cutout_stability.py --times 8  # 更狠一点

退出码：0 全部成功 / 1 有失败（附当时的可执行建议）
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402

import synth  # noqa: E402

# 三个素材轮流用：尺寸与真实 run 里的一致（1024 / 1200 / 1200）
ASSETS = ["cup_source.jpg", "cup_contents.jpg", "competitor.jpg"]
INPUT_DIR = ROOT / "examples" / "input"
OK, BAD = "\u2713", "\u2717"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="连续抠图稳定性自检")
    ap.add_argument("--times", type=int, default=4, help="连续抠几次（默认 4）")
    ap.add_argument("--mode", choices=["auto", "rembg", "floodfill"], default=None,
                    help="抠图方式（默认 auto）")
    args = ap.parse_args(argv)

    print(f"抠图稳定性自检 · 连续 {args.times} 次 · mode={args.mode or 'auto'}")
    print("=" * 72)
    fails: list[str] = []
    for i in range(args.times):
        name = ASSETS[i % len(ASSETS)]
        p = INPUT_DIR / name
        if not p.exists():
            print(f"  · 缺 {p}，跳过")
            continue
        img = Image.open(p)
        t = time.time()
        try:
            rgba, cut = synth.remove_background(img, mode=args.mode)
        except Exception as exc:                        # noqa: BLE001
            el = time.time() - t
            print(f"  [{i + 1}/{args.times}] {BAD} {name:<20}{el:6.1f}s  "
                  f"{type(exc).__name__}: {str(exc)[:110]}")
            fails.append(f"{name}: {type(exc).__name__}")
            continue
        el = time.time() - t
        retried = len(cut.get("infer_retried") or [])
        flag = "" if retried == 0 else f"  ⟳ 重试 {retried} 次才成功"
        print(f"  [{i + 1}/{args.times}] {OK} {name:<20}{el:6.1f}s  "
              f"{cut.get('mode')}{flag}")
        # 抠完就放掉，与真实 run 的节奏一致（下一格才需要新的）
        del rgba

    print("=" * 72)
    if fails:
        print(f"有 {len(fails)} 次失败：{'、'.join(fails)}")
        print("这台机器在连续抠图时会抓不到内存。可行处置：")
        print("  ① 关掉占内存的程序（浏览器 / 聊天客户端）后重跑；")
        print("  ② 显式改用洪水填充：--cutout floodfill（结果确定，质量略降）。")
        return 1
    if args.times >= 3:
        print(f"连续 {args.times} 次全部成功 —— 这台机器可以稳定跑满素材 run。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
