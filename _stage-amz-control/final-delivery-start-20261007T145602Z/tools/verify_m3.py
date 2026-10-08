r"""M3 验收断言 —— 可复现，不靠目测。

用法：
    python tools/verify_m3.py                    # 取 out/ 下最近一次 run
    python tools/verify_m3.py out/B0XXXX_...     # 指定某次 run

断言的是一条**不变量**，不是"跑通了"
------------------------------------
    不变量 A：主体只有一份。七张图读的是同一个 subject.png。

    所以断言不能是"位置 1 看着像杯子"。必须是：把位置 1/2/3 的成品图里
    **产品所占的那块像素**，按日志里记录的 `paste_box` 反解回 subject.png 的尺寸，
    再与 subject.png 逐像素比对。容差只放 JPEG 量化误差。

    如果哪天有人"顺手"让某个渲染器自己抠一次图、或让模型重画一次主体，
    这张断言会立刻爆掉 —— 而肉眼看三张缩略图是看不出来的（那正是它存在的理由）。

五条断言
--------
    A. 位置 1 的校验全过，且 white_bg_purity / product_fill 确实在检验项里
       （不是"声明了但没跑"——v1 就吃过这个亏）
    B. 位置 1/2/3 的产品像素与 subject.png 同源（逐像素，带 JPEG 容差）
    C. 位置 1/2/3 记录的 subject_sha256 完全一致（数据级证明，独立于像素比对）
    D. 位置 2/3 的主体不触碰画布边缘（subject.png 是紧裁切的，这条查得出贴边，
       而位置 2/3 自己的校验规则查不出 —— 见 assert_d 的说明）
    E. 位置 2/3 的重出代价 < 1s 且其渲染器**声明不调模型**（叠字是确定性本地合成；
       哪天有人把文字交给生成模型去画，这条会立刻爆）

退出码：0 全过 / 1 有断言失败 / 2 用法或数据问题
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402  （控制台编码归一：见 src/console.py）
enable_utf8()

import orchestrator  # noqa: E402  （日志的唯一读法 —— 验收口径照抄产品口径）
import registry  # noqa: E402  （只为断言 E 读 renderer 的 calls_model 声明）

# 断言 B 的容差：**实测标定**出来的，不是拍脑袋定的。
# 比对用的"期望值"是同一次 LANCZOS 缩放的结果，与渲染器里做的完全一致，
# 所以两者只差 JPEG 编解码噪声。实测（q=92，1600×1600）：
#
#   ┌──────────────── 位置 1  位置 2  位置 3
#   │ 同源              17/1.29 21/1.89 25/1.96   ← 最大差 / 平均差
#   │ 不同源            255/47  252/47  255/46    ← 换一种抠图方式重抠
#
# 两种情形相差 20 倍以上，所以阈值取在中间偏噪声一侧：
# 容得下 JPEG 噪声的 1.6 倍，又远低于真实失败模式。
#
# ★ 这张表可以随时重算：python tools/calibrate_subject_diff.py [run 目录]
#   —— 阈值必须能被复现，否则它和"我觉得应该没问题"没有区别。
MAX_ABS_DIFF = 40
MEAN_ABS_DIFF = 6.0

# 只比对 alpha 完全不透明处：半透明边缘上的 JPEG 振铃是编解码噪声，
# 不属于"主体是否同源"这个问题，把它算进来只会让阈值失去意义。
OPAQUE_MIN = 250


def newest_run() -> Path | None:
    runs = [p for p in (ROOT / "out").glob("*") if (p / "run.jsonl").exists()]
    return max(runs, key=lambda p: p.stat().st_mtime) if runs else None


def load(run_dir: Path):
    # 容错读：out/ 里可能躺着历史遗留的半行日志（被中断的那次 run）。
    # 严格读会让整次验收在一个与本次无关的目录上炸掉 —— 而产品侧早就把
    # "正在被写的日志"当成正常情况了（审核台每 700ms 轮询一次）。
    # 验收口径照抄产品口径，不留第二套读法。
    recs = orchestrator.read_records(run_dir, tolerant=True)
    one = lambda stage: {r["slot_id"]: r for r in recs       # noqa: E731
                         if r["stage"] == stage}
    subject = next((r for r in recs if r["stage"] == "subject"), None)
    return subject, one("render"), one("validate")


def assert_a(validates: dict, fails: list[str]) -> None:
    v = validates.get(1)
    print("A. 位置 1 校验")
    if not v:
        fails.append("位置 1 在 run.jsonl 里没有 validate 记录")
        print("   ✗ 没有校验记录")
        return
    ran = {c["name"] for c in v["checks"]}
    passed = {c["name"] for c in v["checks"] if c["ok"]}
    got = v["passed"] and {"white_bg_purity", "product_fill"} <= passed
    print(f"   实际跑了 {len(v['checks'])} 项：{'、'.join(sorted(ran))}")
    print(f"   passed={v['passed']}  failed={v['failed']}")
    print(f"   {'✓' if got else '✗'} white_bg_purity / product_fill "
          f"{'在列且通过' if got else '未通过或压根没跑'}")
    if not got:
        fails.append(f"位置 1 校验未达预期：passed={v['passed']} failed={v['failed']}")


def assert_b(subject: dict, renders: dict, fails: list[str]) -> None:
    print("\nB. 主体同源（逐像素）")
    src = Image.open(subject["path"]).convert("RGBA")
    print(f"   subject.png {src.width}×{src.height}  sha {subject['sha256'][:12]}…")

    for sid in (1, 2, 3):
        r = renders.get(sid)
        if not r or r.get("placeholder"):
            fails.append(f"位置 {sid} 没有真实产物（仍是占位图？）")
            print(f"   ✗ 位置 {sid} 没有真实产物")
            continue
        box = r["detail"].get("paste_box")
        if not box:
            fails.append(f"位置 {sid} 日志里没有 paste_box，无法断言（证据缺失）")
            print(f"   ✗ 位置 {sid} 缺 paste_box")
            continue

        x, y, w, h = box
        actual = np.asarray(Image.open(r["path"]).convert("RGB")).astype(np.int16)
        got = actual[y:y + h, x:x + w]

        # 期望值：同一份 subject.png，按同一个尺度做**同一次** LANCZOS 缩放
        exp_img = src.resize((w, h), Image.LANCZOS)
        exp = np.asarray(exp_img.convert("RGB")).astype(np.int16)
        mask = np.asarray(exp_img.getchannel("A")) >= OPAQUE_MIN
        if not mask.any():
            fails.append(f"位置 {sid} 的 paste_box 里没有不透明像素")
            print(f"   ✗ 位置 {sid} 遮罩为空")
            continue

        diff = np.abs(got - exp)[mask]
        mx, mean = int(diff.max()), float(diff.mean())
        ok = mx <= MAX_ABS_DIFF and mean <= MEAN_ABS_DIFF
        print(f"   {'✓' if ok else '✗'} 位置 {sid}  box={box}  "
              f"不透明像素 {int(mask.sum())}  最大差 {mx}  平均差 {mean:.2f}"
              f"  （阈值 ≤{MAX_ABS_DIFF} / ≤{MEAN_ABS_DIFF}）")
        if not ok:
            fails.append(f"位置 {sid} 的产品像素与 subject.png 不同源"
                         f"（最大差 {mx}，平均差 {mean:.2f}）—— 是不是有渲染器"
                         f"自己重抠/重画了主体？")


def assert_c(subject: dict, renders: dict, fails: list[str]) -> None:
    print("\nC. 主体来源一致（数据级）")
    want = subject["sha256"]
    for sid in (1, 2, 3):
        r = renders.get(sid)
        got = (r or {}).get("detail", {}).get("subject_sha256")
        ok = got == want
        print(f"   {'✓' if ok else '✗'} 位置 {sid}  subject_sha256 "
              f"{str(got)[:12]}…")
        if not ok:
            fails.append(f"位置 {sid} 记录的 subject_sha256 与 subject.png 不一致")


def assert_d(renders: dict, fails: list[str]) -> None:
    """位置 2/3 的主体不得触碰画布边缘。

    ★ 这条断言是 M3 期间从一个**真缺陷**里长出来的，值得记下它的来路：
      subject.png 是**紧裁切**的（src/subject.py 的 rgba.crop(bbox)），
      所以它的第 0 行就是产品的最高那一行。原先的缩放上限写成
      `min(W*fill, region_h - reserve, W*0.92)` —— 当"可用区高度"成为约束时
      （位置 2 有 5 条文案，文字条吃掉 50% 画布），主体会**精确填满**整个可用区，
      贴图框 y=0：产品的顶边就是画布的第 0 行。
      而位置 2/3 的校验规则只有尺寸与文字存在性 —— **查不出贴边**。
      所以它必须在这里被断言，而不是指望校验兜住。
    """
    print("\nD. 主体四边留白（不得贴边）")
    for sid in (2, 3):
        r = renders.get(sid)
        if not r or r.get("placeholder"):
            continue
        box = (r.get("detail") or {}).get("paste_box")
        if not box:
            fails.append(f"位置 {sid} 缺 paste_box，无法判断留白")
            print(f"   ✗ 位置 {sid} 缺 paste_box")
            continue
        x, y, w, h = box
        W, H = Image.open(r["path"]).size
        margins = {"left": x, "top": y, "right": W - (x + w)}
        bad = {k: v for k, v in margins.items() if v <= 0}
        ok = not bad
        print(f"   {'✓' if ok else '✗'} 位置 {sid}  留白 {margins}")
        if not ok:
            fails.append(
                f"位置 {sid} 的主体贴到画布边缘（{bad}）—— subject.png 是紧裁切的，"
                f"可用区高度成为约束时就会这样；检查 renderers/flat_overlay.py 的 "
                f"PAD_RATIO 是否被绕过")


def assert_e(renders: dict, fails: list[str]) -> None:
    """位置 2/3 的重出代价：< 1s，且渲染器声明**不调模型**。

    这是验收③（"改文案条数 → 出图重排、耗时 < 1s"）的**可自动化的那一半**。
    验收③本身是人工实验（步骤与结论记在 docs/实施计划.md §6），
    这里断言的是它的前提：叠字这一步是确定性的本地合成 —— 因此快、且不产生调用。
    哪天有人把文字交给生成模型去画，耗时会从零点几秒跳到几十秒，
    调用计数也会从 0 变 1，这条会立刻爆。
    """
    print("\nE. 位置 2/3 的重出代价（叠字是本地确定性合成）")
    for sid in (2, 3):
        r = renders.get(sid)
        if not r or r.get("placeholder"):
            continue
        secs = r.get("elapsed_s")
        model = registry.calls_model(r.get("renderer") or "")
        ok = (secs is not None and secs < 1.0 and not model)
        print(f"   {'✓' if ok else '✗'} 位置 {sid}  {r.get('renderer')}  "
              f"耗时 {secs}s  声明调模型={model}")
        if not ok:
            fails.append(f"位置 {sid} 的重出代价异常（耗时 {secs}s，"
                         f"calls_model={model}）—— 文字是否被交给生成模型去画了？")


def main(argv: list[str]) -> int:
    run_dir = Path(argv[1]) if len(argv) > 1 else newest_run()
    if not run_dir or not (run_dir / "run.jsonl").exists():
        print("找不到 run.jsonl：请先跑一次 "
              "`python run.py --product examples/product_demo.json`")
        return 2

    subject, renders, validates = load(run_dir)
    if not subject:
        print("这次 run 没有 subject 记录（本次没有坑位需要主体？）—— 无法断言")
        return 2

    print(f"M3 验收 · {run_dir.name}\n" + "=" * 72)
    fails: list[str] = []
    assert_a(validates, fails)
    assert_b(subject, renders, fails)
    assert_c(subject, renders, fails)
    assert_d(renders, fails)
    assert_e(renders, fails)

    print("=" * 72)
    if fails:
        print(f"未通过 {len(fails)} 条：")
        for f in fails:
            print(f"  ✗ {f}")
        return 1
    print("全部通过：位置 1/2/3 的像素确实来自同一份 subject.png（且留白合格、"
          "重出代价可忽略），位置 1 的强制性校验真的跑过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
