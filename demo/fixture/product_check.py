# -*- coding: utf-8 -*-
"""统一入口：量测 → 按事实卡判定 → 三档报告 → 退出码。

    python demo/fixture/product_check.py check --card demo/fixture/aster-01/product.json \
        --ids A,B,C --src evals/product-demo/fixture-design
    python demo/fixture/product_check.py check --card <卡> --image <任意图> --out <目录>
    python demo/fixture/product_check.py self-test --project .

退出码（0/3/4 直接来自 factcard.EXIT，即"最严重的那一条判据"）：
    0 通过 · 3 需人工或含 Unknown · 4 硬失败 · 5 profile 不支持 · 6 事实卡不合法

为什么退出码要从判定来：以前的入口永远返回 0，脚本能跑完就等于"过了"。
那让门禁退化成装饰 —— 判据写着会拦，实际上没人被拦下。
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import factcard as fc          # noqa: E402
import measure_cylinder as mc  # noqa: E402

DEFAULT_CARD = "demo/fixture/aster-01/product.json"
DEFAULT_SRC = "evals/product-demo/fixture-design"

EXIT_PROFILE = 5
EXIT_CARD = 6


def say(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))


def load_card_or_fail(card_path: Path):
    """卡不合法就让流程停在这里，而不是带着一张坏卡继续量。"""
    try:
        return fc.load_card(card_path)
    except fc.CardError as exc:
        say("CARD_INVALID " + str(card_path) + "：" + str(exc))
        raise SystemExit(EXIT_CARD)


def resolve_images(args, project: Path) -> list[Path]:
    if args.image:
        return [Path(p) if Path(p).is_absolute() else project / p for p in args.image]
    if args.ids:
        return [project / args.src / cid.strip() / "raw.png"
                for cid in args.ids.split(",") if cid.strip()]
    raise SystemExit("要么给 --image，要么给 --ids")


def run_one(image: Path, card: dict, clf) -> dict:
    measured = mc.measure(image, card=card, clf=clf)
    report = fc.evaluate(measured["metrics"], card)
    return {"image": image, "measured": measured, "report": report,
            "exit": fc.EXIT[report["overall"]]}


def check(args) -> int:
    project = Path(args.project).resolve()
    card_path = Path(args.card)
    if not card_path.is_absolute():
        card_path = project / card_path
    card = load_card_or_fail(card_path)
    try:
        mc.require_profile(card)
        mc.slot_roles(card)
    except mc.ProfileMismatch as exc:
        say("PROFILE_UNSUPPORTED " + str(exc))
        return EXIT_PROFILE

    clf = fc.PaletteClassifier(card["palette"])
    images = resolve_images(args, project)
    results = []
    worst = 0
    for image in images:
        if not image.exists():
            say("IMAGE_MISSING " + str(image))
            return EXIT_CARD
        r = run_one(image, card, clf)
        results.append(r)
        worst = max(worst, r["exit"])
        say(fc.format_report(r["report"], image.parent.name + " / " + image.name,
                             extra_lines=["图片：" + str(image),
                                          "这一张的退出码：" + str(r["exit"])]))
        say("")

    say("--- 汇总 ---")
    for r in results:
        say("  " + r["report"]["overall"].ljust(9) + str(r["image"].parent.name)
            + "  rc=" + str(r["exit"]))
    say("综合退出码：" + str(worst))

    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = project / out
        out.mkdir(parents=True, exist_ok=True)
        payload = [{"image": str(r["image"]), "read_at": r["measured"]["read_at"],
                    "metric_profile": r["measured"]["metric_profile"],
                    "image_size": r["measured"]["image_size"],
                    "metrics": r["measured"]["metrics"],
                    "measured_colors": r["measured"]["measured_colors"],
                    "declared_colors": r["measured"]["declared_colors"],
                    "geometry": r["measured"]["geometry"],
                    "verdict": r["report"]["overall"],
                    "facts": r["report"]["facts"]} for r in results]
        (out / "measure.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                          encoding="utf-8", newline="\n")
        md = []
        for r in results:
            md.append(fc.format_report(r["report"], r["image"].parent.name + " / " + r["image"].name,
                                       extra_lines=["图片：" + str(r["image"])]))
        (out / "report.md").write_text("\n\n".join(md), encoding="utf-8", newline="\n")
        say("wrote " + str(out / "measure.json") + " 与 " + str(out / "report.md"))
    return worst


def self_test(project: Path, keep: bool = False) -> int:
    """反向对照：换卡、改锚点、写坏卡，逐向核对入口是否只做该做的事。

    期望值用「谓词」而不是写死档位：像"把调色板收窄到一个点"这种破坏，究竟停在
    需人工还是硬失败，取决于哪条判据先倒下 —— 写死一个数字就是在赌实现细节。
    """
    base = Path(tempfile.mkdtemp(prefix="check_selftest_"))
    real_card = json.loads((project / DEFAULT_CARD).read_text(encoding="utf-8"))
    tool = Path(__file__).resolve()

    def run(card_obj, ids="A", tag="case", out=None):
        cardfile = base / (tag + ".json")
        cardfile.write_text(json.dumps(card_obj, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        cmd = [sys.executable, str(tool), "check", "--project", str(project),
               "--card", str(cardfile), "--ids", ids]
        if out:
            cmd += ["--out", str(out)]
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()

    def clone():
        return json.loads(json.dumps(real_card))

    def case_baseline():
        rc, _ = run(clone(), "C", "baseline")
        return rc == 0, "候选 C 用真卡应通过，rc=" + str(rc)

    def case_widen_ribs():
        """同一张图、同一个入口，只改卡里的筋条档 —— 判定必须跟着卡走。"""
        card = clone()
        for fact in card["facts"]:
            if fact["id"] == "F3":
                for chk in fact["machine_checks"]:
                    if chk["metric"] == "rib_count":
                        chk["pass"] = {"min": 3, "max": 4}
        rc_before, _ = run(clone(), "A", "rib_before")
        rc_after, _ = run(card, "A", "rib_after")
        return (rc_before != 0 and rc_after == 0,
                "改卡前 A rc=" + str(rc_before) + "，改卡后 rc=" + str(rc_after)
                + "（应 非0 → 0）")

    def case_narrow_palette():
        """把调色板锚点容忍度收到 1.0：像素判不出角色，量测必然缺项，入口必须变红。"""
        card = clone()
        card["palette"]["max_delta_e"] = 1.0
        rc, out = run(card, "C", "narrow")
        return rc != 0, "rc=" + str(rc) + "（应非 0）；" + out.splitlines()[-1][:80]

    def case_bad_schema():
        card = clone()
        card["schema"] = "demo-fact-card/999"
        rc, out = run(card, "C", "badschema")
        return rc == EXIT_CARD and "CARD_INVALID" in out, "rc=" + str(rc) + "（应 6）"

    def case_manual_not_containing_pass():
        card = clone()
        for fact in card["facts"]:
            if fact["id"] == "F1":
                for chk in fact["machine_checks"]:
                    chk["manual"] = {"min": 3.0, "max": 3.2}
        rc, out = run(card, "C", "badmanual")
        return (rc == EXIT_CARD and "没有包住通过档" in out, "rc=" + str(rc) + "（应 6）")

    def case_profile_mismatch():
        card = clone()
        card["metric_profile"] = "box-v1"
        rc, out = run(card, "C", "profile")
        return rc == EXIT_PROFILE and "PROFILE_UNSUPPORTED" in out, "rc=" + str(rc) + "（应 5）"

    def case_missing_slot_role():
        """角色还在、槽位整块被删：卡本身合法，但这个 profile 没法量 —— 应报 5 而不是硬算。"""
        card = clone()
        card["palette"]["roles"] = [r for r in card["palette"]["roles"] if r["slot"] != "trim"]
        rc, out = run(card, "C", "m slot".replace(" ", ""))
        return rc == EXIT_PROFILE and "PROFILE_UNSUPPORTED" in out, "rc=" + str(rc) + "（应 5）"

    def case_determinism():
        """同一张图、同一张卡跑两次，量测值必须逐值相同（时间戳不算量测值）。"""
        o1, o2 = base / "det1", base / "det2"
        rc1, _ = run(clone(), "A,B,C", "det1", o1)
        rc2, _ = run(clone(), "A,B,C", "det2", o2)
        m1 = [r["metrics"] for r in json.loads((o1 / "measure.json").read_text(encoding="utf-8"))]
        m2 = [r["metrics"] for r in json.loads((o2 / "measure.json").read_text(encoding="utf-8"))]
        return (rc1 == rc2 and m1 == m2, "两次 rc=" + str(rc1) + "/" + str(rc2)
                + "，量测值" + ("相同" if m1 == m2 else "不同"))

    cases = [
        ("A 基线（真卡 · 候选 C）", case_baseline),
        ("B 只改卡里的筋条档 → 判定跟着卡走", case_widen_ribs),
        ("C 调色板收窄到 1.0 → 必须变红", case_narrow_palette),
        ("D schema 写错 → 卡被拒（6）", case_bad_schema),
        ("E 人工档没包住通过档 → 卡被拒（6）", case_manual_not_containing_pass),
        ("F metric_profile 不匹配 → 5", case_profile_mismatch),
        ("G 缺语义槽位 → 5", case_missing_slot_role),
        ("H 同一输入跑两次 → 量测值逐值相同", case_determinism),
    ]
    bad = 0
    for name, fn in cases:
        try:
            ok, detail = fn()
        except Exception as exc:
            ok, detail = False, "抛出 " + type(exc).__name__ + "：" + str(exc)[:200]
        if not ok:
            bad += 1
        say(("OK   " if ok else "FAIL ") + name + " —— " + detail)
    if keep:
        say("沙箱保留在 " + str(base))
    else:
        tmp_root = Path(tempfile.gettempdir()).resolve()
        if tmp_root in base.resolve().parents:
            shutil.rmtree(base, ignore_errors=True)
        else:
            say("沙箱不在临时目录下，拒绝删除：" + str(base))
    say("OK：8 向全部与预期一致" if bad == 0
        else "FAIL：" + str(bad) + " / 8 向与预期不符 —— 入口的判据有问题")
    return 0 if bad == 0 else 1


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["check", "self-test"])
    ap.add_argument("--project", default=".")
    ap.add_argument("--card", default=DEFAULT_CARD)
    ap.add_argument("--image", action="append", help="可重复；与 --ids 二选一")
    ap.add_argument("--ids", default="", help="按 --src/<id>/raw.png 解析候选目录")
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--out", default="")
    ap.add_argument("--keep", action="store_true", help="self-test 保留沙箱")
    args = ap.parse_args()
    project = Path(args.project).resolve()
    if args.mode == "self-test":
        return self_test(project, keep=args.keep)
    return check(args)


if __name__ == "__main__":
    raise SystemExit(main())
