# -*- coding: utf-8 -*-
"""P2 负样本套件：把变异过的坏图喂给同一个入口，逐例对照事先写下的预期。

    python demo/fixture/negative_suite.py --project .          # 重新变异 + 判定 + 出报告
    python demo/fixture/negative_suite.py --project . --skip-mutate

退出码：0 全部预期成立 / 1 有预期落空。

三件必须同时成立，缺一件就等于把断言悄悄关掉：
  a) 每一例的 must_be 成立（不得通过 / 不得硬失败 / 必须通过）；
  b) 声明过 must_flag_any_of 的，至少一条真的落到非通过 —— 「命中预期谓词」可核对；
  c) 未变异对照不得硬失败，并给出误报率。

预期在 evals/product-demo/negative-cases/expectations.json，先写预期再跑。
这套件不产生任何模型调用。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import factcard as fc          # noqa: E402
import product_check as pc     # noqa: E402

CST = timezone(timedelta(hours=8))

DEFAULT_CARD = "demo/fixture/aster-01/product.json"
DEFAULT_CASES = "evals/product-demo/negative-cases"
SOURCE_REL = "evals/product-demo/fixture-design/C/raw.png"
FONT_PATH = "C:/Windows/Fonts/arial.ttf"


def say(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))


def stamp() -> str:
    return datetime.now(CST).replace(microsecond=0).isoformat()


def rel_or_abs(p: Path, base: Path) -> str:
    try:
        return p.relative_to(base).as_posix()
    except ValueError:
        return p.as_posix()


def verdict_ok(must_be: str, overall: str) -> bool:
    if must_be == "not_pass":
        return overall != fc.PASS
    if must_be == "not_hard_fail":
        return overall != fc.HARD_FAIL
    if must_be == "pass":
        return overall == fc.PASS
    raise SystemExit("expectations.json 里出现未知 must_be：" + str(must_be))


def evaluate(image: Path, card: dict, clf) -> dict:
    r = pc.run_one(image, card, clf)
    rep = r["report"]
    flags = []
    for f in rep["facts"]:
        for c in f["machine_checks"]:
            if c["verdict"] != fc.PASS:
                flags.append({"fact": f["id"], "metric": c["metric"],
                              "verdict": c["verdict"], "value": c["value"], "why": c["why"]})
    return {"image": str(image), "overall": rep["overall"], "exit": r["exit"],
            "flagged": flags, "human_facts": rep["human_facts"],
            "metrics": r["measured"]["metrics"]}


def contact_sheet(rows: list, out: Path, tile_h: int = 300) -> None:
    tiles = []
    for row in rows:
        with Image.open(row["image"]) as im:
            thumb = im.convert("RGB")
            scale = tile_h / thumb.height
            thumb = thumb.resize((max(1, int(thumb.width * scale)), tile_h))
        tiles.append((row, thumb))
    cols, pad, cap = 4, 10, 34
    cell_w = max(t[1].width for t in tiles) + pad * 2
    cell_h = tile_h + cap + pad * 2
    rows_n = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cell_w * cols, cell_h * rows_n), (250, 250, 250))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(FONT_PATH, 15)
    for i, (row, thumb) in enumerate(tiles):
        cx = (i % cols) * cell_w
        cy = (i // cols) * cell_h
        sheet.paste(thumb, (cx + (cell_w - thumb.width) // 2, cy + pad))
        hit = "、".join(row.get("flag_hit") or [])
        top = hit or (row["flagged"][0]["metric"] if row["flagged"] else "-")
        if len(top) > 20:
            top = top[:19] + "…"
        for j, line in enumerate([str(row["label"]), str(row["overall"]) + "  [" + top + "]"]):
            d.text((cx + pad, cy + pad + tile_h + 2 + j * 16), line, font=font, fill=(20, 20, 20))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, format="PNG")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="P2 负样本对照")
    ap.add_argument("--project", default=".")
    ap.add_argument("--card", default=DEFAULT_CARD)
    ap.add_argument("--cases", default=DEFAULT_CASES)
    ap.add_argument("--skip-mutate", action="store_true", help="不重跑变异器，直接用现有图")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    cases_dir = project / args.cases
    exp_path = cases_dir / "expectations.json"
    if not exp_path.exists():
        raise SystemExit("找不到预期文件（预期必须先写）：" + str(exp_path))
    exp = json.loads(exp_path.read_text(encoding="utf-8"))

    if not args.skip_mutate:
        p = subprocess.run([sys.executable, str(HERE / "mutate_negative.py"),
                            "--project", str(project), "--card", args.card,
                            "--out", str(cases_dir)],
                           cwd=str(project), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if p.returncode != 0:
            raise SystemExit("变异器失败：\n" + (p.stdout or "") + (p.stderr or ""))
        for ln in (p.stdout or "").strip().splitlines():
            say(ln)

    card = fc.load_card(project / args.card)
    clf = fc.PaletteClassifier(card["palette"])
    started = stamp()

    results, failures = [], []
    for case in exp["cases"]:
        cid = case["case_id"]
        image = cases_dir / cid / "raw.png"
        if not image.exists():
            raise SystemExit("缺负样本图：" + str(image))
        row = evaluate(image, card, clf)
        row["label"] = cid
        row["mutation_class"] = case["mutation_class"]
        row["must_be"] = case["must_be"]
        row["must_flag_any_of"] = case.get("must_flag_any_of", [])
        row["human_required"] = bool(case.get("human_required"))
        row["hypothesis"] = case.get("hypothesis", "")
        row["beat_ok"] = verdict_ok(case["must_be"], row["overall"])
        flagged = [f["metric"] for f in row["flagged"]]
        want = row["must_flag_any_of"]
        row["flag_hit"] = sorted(set(want) & set(flagged))
        row["flag_ok"] = bool(row["flag_hit"]) if want else True
        row["ok"] = row["beat_ok"] and row["flag_ok"]
        if not row["ok"]:
            failures.append(cid)
        results.append(row)

    controls, ctrl_fail = [], []
    for spec in exp["controls"]:
        image = project / spec["file"]
        if not image.exists():
            raise SystemExit("缺对照图：" + str(image))
        row = evaluate(image, card, clf)
        row["label"] = spec["case_id"]
        row["must_be"] = spec["must_be"]
        row["rationale"] = spec.get("rationale", "")
        row["ok"] = verdict_ok(spec["must_be"], row["overall"])
        if not row["ok"]:
            ctrl_fail.append(spec["case_id"])
        controls.append(row)

    hard_fails = [c for c in controls if c["overall"] == fc.HARD_FAIL]
    false_positive = {
        "controls": len(controls), "hard_fail": len(hard_fails),
        "rate": (len(hard_fails) / len(controls)) if controls else None,
        "note": "误报只数硬失败：对照被判 manual 是预期内的真报，见 expectations.json",
    }
    declared_misses = [r for r in results if r["human_required"]]
    unexpected_misses = [r for r in results if not r["flag_ok"]]
    declared_metrics = {m for r in results for m in r["must_flag_any_of"]}
    flagged_metrics = {f["metric"] for r in results for f in r["flagged"]}

    report = {
        "schema": "demo-negative-report/1",
        "generated_at": started,
        "model_calls": 0,
        "card": {"sku": card["sku"], "version": card["version"],
                 "metric_profile": card["metric_profile"]},
        "expectations_file": rel_or_abs(exp_path, project),
        "declared_at": exp.get("declared_at"),
        "cases": results,
        "controls": controls,
        "false_positive": false_positive,
        "declared_misses": [r["label"] for r in declared_misses],
        "unexpected_misses": [r["label"] for r in unexpected_misses],
        "flagged_but_not_declared": sorted(flagged_metrics - declared_metrics),
        "ok": (not failures) and (not ctrl_fail),
        "failed_cases": failures + ctrl_fail,
    }
    cases_dir.mkdir(parents=True, exist_ok=True)
    (cases_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    lines = [
        "# P2 负样本对照报告（改色 / 加字 / 改结构 / 改数量）",
        "",
        "时间：" + started + "  ",
        "可计费模型调用：**0 次**",
        "",
        "预期写在 `" + report["expectations_file"] + "`（声明时间 " + str(exp.get("declared_at"))
        + "），本报告只做对照。判定走 `demo/fixture/product_check.py` 的同一段代码。",
        "",
        "## 1. 逐例对照",
        "",
        "| 例 | 类 | 预期 | 实际 | 实际命中的非通过谓词 | 预期谓词 | 结论 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        flagged_txt = "、".join(f["fact"] + "/" + f["metric"] for f in r["flagged"]) or "（无）"
        want_txt = "、".join(r["must_flag_any_of"]) or "（不要求）"
        lines.append("| `" + r["label"] + "` | " + r["mutation_class"] + " | " + r["must_be"]
                     + " | " + r["overall"] + "（rc " + str(r["exit"]) + "） | " + flagged_txt
                     + " | " + want_txt + " | " + ("成立" if r["ok"] else "**落空**") + " |")
    lines += [
        "",
        "## 2. 未变异对照与误报率",
        "",
        "| 对照 | 预期 | 实际 | 说明 |",
        "|---|---|---|---|",
    ]
    for c in controls:
        lines.append("| `" + c["label"] + "` | " + c["must_be"] + " | " + c["overall"]
                     + " | " + c["rationale"] + " |")
    lines += [
        "",
        "误报率 = 对照里被判硬失败的比例 = " + str(false_positive["hard_fail"]) + "/"
        + str(false_positive["controls"]) + "。对照被判 `manual` 不计入误报。",
        "",
        "## 3. 漏报台账",
        "",
        "| 例 | 是漏报吗 | 谁负责 | 为什么 |",
        "|---|---|---|---|",
    ]
    ledger = 0
    for r in results:
        if r["human_required"]:
            ledger += 1
            lines.append("| `" + r["label"] + "` | 是（预期内） | 人工档 | 见 `expectations.json` 的 rationale；"
                         "对应的机器缺口登记在事实卡 `machine_check_gaps` |")
    for r in results:
        if (not r["human_required"]) and (not r["flag_ok"]):
            ledger += 1
            lines.append("| `" + r["label"] + "` | **是（预期外）** | 待定 | 声明的谓词一条都没命中 |")
    if ledger == 0:
        lines.append("| — | 无 | — | — |")
    lines += [
        "",
        "## 4. 这张表不证明什么",
        "",
        "- 它不证明「门禁能拦下所有坏图」：只证明这七例改动与三个对照的判定符合事先写下的预期；",
        "- 两个字面缺口是**故意留下并被记账**的：F8 文字（人工档）、F4 阶梯级数与盖顶开口"
        "（机器判据只有盖高）。它们由人看、不由机器判 —— 这正是事实卡 `machine_check_gaps` 登记的内容；",
        "- 机器判 `hard_fail` 不总能指出「最初改的是什么」：结构变异会连带打断按颜色分的带。"
        "所以报告列出**实际命中的每一条谓词**，而不是只给一个结论；",
        "- 三个对照（n=3）不足以给误报率任何统计意义，它只回答「这一次有没有误伤」。",
    ]
    (cases_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    contact_sheet([{"label": "C-source", "image": str(project / SOURCE_REL),
                    "overall": "pass", "flagged": []}] + results,
                  cases_dir / "contact-sheet.png")

    say("")
    for r in results:
        say("  %-22s %-6s 预期=%-13s 实际=%-10s %s"
            % (r["label"], r["mutation_class"], r["must_be"], r["overall"],
               "OK" if r["ok"] else "**落空**"))
    say("对照：" + "、".join(c["label"] + "=" + c["overall"] for c in controls)
        + "　误报（硬失败）：" + str(false_positive["hard_fail"]) + "/"
        + str(false_positive["controls"]))
    say("预期内漏报：" + ("、".join(report["declared_misses"]) or "无")
        + "　预期外漏报：" + ("、".join(report["unexpected_misses"]) or "无"))
    say("wrote " + rel_or_abs(cases_dir / "report.md", project)
        + "、" + rel_or_abs(cases_dir / "report.json", project)
        + "、" + rel_or_abs(cases_dir / "contact-sheet.png", project))
    say("结论：" + ("全过" if report["ok"] else "有落空 —— " + "、".join(report["failed_cases"])))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
