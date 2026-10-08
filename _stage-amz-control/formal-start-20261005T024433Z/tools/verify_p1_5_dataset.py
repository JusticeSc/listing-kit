#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""P1.5 验收：Golden/Counterexample 数据集（判据会不会红、现在够不够）。

判据来自计划 Phase 1 任务卡 P1.5 那一行：
    独立加载器可重复读取；标签冲突显式列出；改标签产生新版本而非覆盖；
    至少每类关键错误有正反例；标签责任人不明确时样本不进入门禁，只保留为待标注。

九条：
    A 基线（真文件）     读得出来、可重复读（同一版本号）、如实报红（0 条进统计）
    B 样例不计数         一条 pilot + 一条 sample 都贴满标签 → 只有 pilot 那条进统计
    C 满编正向对照       五类齐全 + 六条关键项正反例齐全 → 判据转绿，门退出码 0
    D 绑定输入           哈希对不上 / 输入不在 / FactsVersion 手抄错 → 三种都不进统计
    E 标签人             没标签人 / 标签人没登记 → 都不进统计（"待标注"不是"通过"）
    F 标签冲突           同一条两条不同结论 → 显式列出，且该条退出统计
    G 版本               就地改冻结文件会被发现；同一版不能冻两次；改了内容产生新版本
    H 门禁入口本身       三个退出码各证明一次：没齐=1、齐了=0、写错了=2
    I 加样本入口         真实试点 SKU → 一条绑定现场算好的样本；先过 P1.4 才做 P1.5；
                        --dry-run 不落盘；同名默认拒绝；素材变了立刻变 mismatch

退出码：0 全过 / 1 有条目不过。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402
enable_utf8()
import eval_dataset as ed  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
import freeze_dataset_labels as fz  # noqa: E402

REPORT = ROOT / "evals" / "product-v1" / "p1" / "p1.5-dataset.txt"
GATE = ROOT / "tools" / "check_dataset_ready.py"
TMP = ROOT / "evals" / ".tmp" / "p1.5"
FULL = "examples/product_fullset.json"
DEMO = "examples/product_demo.json"
FRONT = "examples/input/cup_source.jpg"
CRITICAL6 = ["cf.structure", "cf.quantity", "cf.appearance",
             "cf.spec_claim", "cf.composition", "cf.claim_truth"]
STAMP = date(2026, 9, 23)


# ---------------------------------------------------------------- 造样本

def mk_entry(eid, case_class, *, source_kind="pilot", refs=(FULL,), images=(FRONT,),
             exercised=(), mutate=None):
    inputs = [{"kind": "product_facts_source", "ref": r, "sha256": ed.sha256_file(ROOT / r)}
              for r in refs]
    inputs += [{"kind": "material_image", "ref": r, "sha256": ed.sha256_file(ROOT / r)}
               for r in images]
    e = {"entry_id": eid, "case_class": case_class, "source_kind": source_kind,
         "design_note": f"{eid}：验收用的合成样本",
         "inputs": inputs, "facts_version": ed.compute_facts_version(list(refs)),
         "exercised_items": list(exercised)}
    if mutate:
        mutate(e)
    return e


def mk_label(eid, verdict, failed=(), labeler="运营 甲"):
    row = {"entry_id": eid, "verdict": verdict, "failed_items": list(failed),
           "labeler": labeler,
           "labeled_at": STAMP.isoformat() if labeler else None}
    return row


def write_ds(name, entries, labels=(), labelers=()):
    d = TMP / name
    if d.exists():
        shutil.rmtree(d)
    (d / "labels").mkdir(parents=True)
    (d / "manifest.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries),
        encoding="utf-8", newline="")
    index = {"schema": ed.SCHEMA, "updated_at": STAMP.isoformat(),
             "labelers": list(labelers), "active_label_version": None,
             "label_versions": {}}
    if labels:
        ver = ed.labels_version(list(labels))
        (d / "labels" / f"{ver}.jsonl").write_text(
            "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in labels),
            encoding="utf-8", newline="")
        index["label_versions"] = {ver: {"file": f"labels/{ver}.jsonl",
                                         "frozen_at": STAMP.isoformat(),
                                         "count": len(labels)}}
        index["active_label_version"] = ver
    (d / "dataset.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8", newline="")
    return d


def green_dataset(name="green"):
    """五类齐全 + 六条关键项正反例齐全 + 标签人合法。"""
    entries = [mk_entry("GC-0001", "normal", exercised=CRITICAL6)]
    for i, item in enumerate(CRITICAL6, start=2):
        entries.append(mk_entry(f"GC-{i:04d}", "critical_error",
                                exercised=[item], images=(FRONT,)))
    entries.append(mk_entry("GC-0008", "boundary", exercised=["cf.structure"]))
    entries.append(mk_entry("GC-0009", "hard_judgement", exercised=["cf.appearance"]))
    entries.append(mk_entry("GC-0010", "unknown", exercised=["cf.spec_claim"]))
    labels = [mk_label("GC-0001", "accept")] + [
        mk_label(f"GC-{i:04d}", "reject", [item]) for i, item in enumerate(CRITICAL6, start=2)
    ] + [mk_label("GC-0008", "accept"), mk_label("GC-0009", "accept"),
         mk_label("GC-0010", "unknown")]
    return write_ds(name, entries, labels, ["运营 甲"])


def gate(path=None) -> int:
    args = [sys.executable, str(GATE)] + (["--path", str(path)] if path else [])
    return subprocess.run(args, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace").returncode


def status_of(report, eid) -> str:
    for r in report["entries"]:
        if r["entry_id"] == eid:
            return r["status"]
    return "<没有这条>"


def main() -> int:
    lines: list[str] = []
    fails: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    def check(ok: bool, label: str, detail: str = "") -> None:
        emit(f"  [{'OK  ' if ok else 'FAIL'}] {label}" + (f"　{detail}" if detail else ""))
        if not ok:
            fails.append(label)

    def expect_error(fn, must_contain: str, label: str) -> None:
        try:
            fn()
        except ed.DatasetError as exc:
            hit = must_contain in str(exc)
            check(hit, label, f"报错含『{must_contain}』" if hit else
                  f"报错了但没提『{must_contain}』：{str(exc).splitlines()[0]}")
        except Exception as exc:                                   # noqa: BLE001
            check(False, label, f"抛的不是 DatasetError 而是 {type(exc).__name__}: {exc}")
        else:
            check(False, label, "居然通过了 —— 这一条本该被拦下")

    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True, exist_ok=True)

    emit("P1.5 验收：Golden/Counterexample 数据集")
    emit("=" * 72)
    emit("本次切片的七项声明（计划 §7.1）：")
    emit("  用户可见行为  无（这一层还不接界面；只把『用哪些样本证明』变成可加载、可版本化的登记）")
    emit("  不变量        A 主体只有一份 / B 生成层看不见主体 / C 文字层不画字 / D 位置 1 零模型 全部未触碰")
    emit("  允许改的模块  src/eval_dataset.py、tools/freeze_dataset_labels.py、"
         "tools/check_dataset_ready.py、tools/add_dataset_sample.py 新增；"
         "evals/product-v1/dataset/ 新增；examples/ 只读")
    emit("  新增身份      条目 id=GC-NNNN（样本）/ 标签版本=gcv1-<内容哈希前 12 位> / "
         "数据集版本=gcd1-<前 12 位>；输入只留项目内相对路径 + sha256")
    emit("  拒绝路径      绝对路径 / 哈希不是 64 位 / 清单里没有的项 / critical_error 没写考哪条 → 报错；"
         "没标签人 → 不进统计；同一版两条结论打架 → 显式列出并退出统计；"
         "加样本时 SKU 不在试点登记表 → 报错（先过 P1.4 才做 P1.5）")
    emit("  判据          本文件 A–I；反向样本见 B/D/E/F/G/I；正向对照见 C/I")
    emit("  迁移与回退    纯加法：ProductFacts / DataPolicy / ReviewChecklist / v2 管线均未改；"
         "数据集当前 5 条样例、0 条进统计，门如实报红")

    # ---------------- A 基线
    emit("")
    emit("A 基线（真文件：读得出来，但还没有真样本与标签人）")
    real = ed.audit()
    real2 = ed.audit()
    check(real["counts"]["entries"] == 5, "真数据集 5 条",
          f"分类分布 {real['counts']['by_class']}")
    check(real["dataset_version"] == real2["dataset_version"],
          "两次加载得到同一个数据集版本（可重复读取）", real["dataset_version"])
    check(all(real["counts"]["by_class"][c] == 1 for c in ed.CASE_CLASSES),
          "五类样本各有一条（正常/边界/明显关键错误/难判/Unknown）")
    check(real["counts"]["by_source"]["pilot"] == 0 and real["counts"]["counted"] == 0,
          "进统计 0 条 —— 真样本和标签人一样都还没有", f"counted={real['counts']['counted']}")
    check(len(real["unattributed"]) == 5, "五条都列在『还没贴标签』里")
    check(real["draft"]["count"] == 5 and len(real["draft"]["without_labeler"]) == 5,
          "草稿 5 条，且 5 条都没有标签人（草稿不是标签）")
    check(len(real["coverage_gaps"]) == 6 and real["class_gaps"] == list(ed.CASE_CLASSES),
          "缺什么点名：六条关键项都缺正反例、五类都不可计数")
    check(gate() == 1, "门报『还没齐』（退出码 1）")

    # ---------------- B 样例不计数
    emit("")
    emit("B 样例不计数（样例能把工具链跑通，但不能拿来证明产品可用）")
    b_entries = [mk_entry("GC-0001", "normal", source_kind="pilot", exercised=CRITICAL6),
                 mk_entry("GC-0002", "normal", source_kind="sample", exercised=CRITICAL6)]
    b = ed.audit(dataset_dir=write_ds("sample_not_counted", b_entries,
                                      [mk_label("GC-0001", "accept"), mk_label("GC-0002", "accept")],
                                      ["运营 甲"]))
    check(b["counts"]["counted"] == 1, "两条都贴了合法标签 → 只有 pilot 那条进统计",
          f"counted={b['counts']['counted']}")
    check(status_of(b, "GC-0002") == "sample", "样例那条的状态是『样例不计数』，不是『通过』")

    # ---------------- C 满编正向对照
    emit("")
    emit("C 满编正向对照（判据不是一直红）")
    gd = green_dataset()
    g = ed.audit(dataset_dir=gd)
    check(g["counts"]["counted"] == 10, "10 条全部进统计", f"counted={g['counts']['counted']}")
    check(not g["coverage_gaps"], "六条关键项的正反例都齐了", f"coverage={g['coverage']}")
    check(not g["class_gaps"], "五类都有可计数的样本")
    check(ed.ready(g) == [], "门禁判据说『齐了』")
    check(gate(gd) == 0, "门退出码 0")

    # ---------------- D 绑定输入
    emit("")
    emit("D 绑定输入（哈希 / 在不在 / FactsVersion 手抄错）")
    d_entries = [
        mk_entry("GC-0001", "normal", exercised=CRITICAL6),
        mk_entry("GC-0002", "normal", exercised=CRITICAL6,
                 mutate=lambda e: e["inputs"][0].update({"sha256": "b" * 64})),
        mk_entry("GC-0003", "normal", exercised=CRITICAL6,
                 mutate=lambda e: e["inputs"][1].update({"ref": "examples/input/没有这张图.jpg"})),
        mk_entry("GC-0004", "normal", exercised=CRITICAL6,
                 mutate=lambda e: e.update({"facts_version": "pfv1-000000000000"})),
    ]
    d = ed.audit(dataset_dir=write_ds(
        "bind", d_entries,
        [mk_label(f"GC-{i:04d}", "accept") for i in (1, 2, 3, 4)], ["运营 甲"]))
    check(status_of(d, "GC-0001") == "counted", "哈希与版本都对 → 进统计")
    check(status_of(d, "GC-0002") == "not_bound", "哈希对不上 → 不进统计")
    check([x for x in d["pending"] if x["entry_id"] == "GC-0002"], "并写清是哈希对不上")
    check(status_of(d, "GC-0003") == "not_bound", "输入文件不在 → 不进统计")
    check([x for x in d["pending"] if x["entry_id"] == "GC-0003"], "并写清是哪个输入不在")
    check(status_of(d, "GC-0004") == "not_bound", "FactsVersion 手抄错 → 不进统计")
    check(any("FactsVersion 对不上" in x["why"] for x in d["pending"]),
          "并写清现场算出来是哪一个版本")

    # ---------------- E 标签人
    emit("")
    emit("E 标签人（『待标注』不是『通过』）")
    e_entries = [mk_entry("GC-0001", "normal", exercised=CRITICAL6),
                 mk_entry("GC-0002", "normal", exercised=CRITICAL6),
                 mk_entry("GC-0003", "normal", exercised=CRITICAL6)]
    e_labels = [mk_label("GC-0001", "accept"),
                mk_label("GC-0002", "accept", labeler=None),
                mk_label("GC-0003", "accept", labeler="路人甲")]
    e = ed.audit(dataset_dir=write_ds("labelers", e_entries, e_labels, ["运营 甲"]))
    check(status_of(e, "GC-0001") == "counted", "登记在案的标签人 → 进统计")
    check(status_of(e, "GC-0002") == "unattributed", "没有标签人 → 不进统计")
    check(status_of(e, "GC-0003") == "unattributed", "标签人不在 labelers 里 → 不进统计")
    check(len(e["unattributed"]) == 2 and e["counts"]["counted"] == 1,
          "两条待标注/无资格的条目都点名列出", f"counted={e['counts']['counted']}")

    # ---------------- F 标签冲突
    emit("")
    emit("F 标签冲突（不取最后一条，也不取多数）")
    f_entries = [mk_entry("GC-0001", "normal", exercised=CRITICAL6)]
    f_labels = [mk_label("GC-0001", "accept", labeler="运营 甲"),
                mk_label("GC-0001", "reject", ["cf.appearance"], labeler="运营 乙")]
    f = ed.audit(dataset_dir=write_ds("conflict", f_entries, f_labels, ["运营 甲", "运营 乙"]))
    check(len(f["conflicts"]) == 1, "冲突被显式列出", f"conflicts={len(f['conflicts'])}")
    check(status_of(f, "GC-0001") == "conflicted", "冲突条目退出统计，而不是挑一条用")
    check(f["counts"]["counted"] == 0, "冲突条目不计入任何覆盖")

    # ---------------- G 版本
    emit("")
    emit("G 版本（改标签只能新增一版）")
    g_dir = TMP / "versions"
    (g_dir / "labels").mkdir(parents=True, exist_ok=True)
    (g_dir / "manifest.jsonl").write_text(
        json.dumps(mk_entry("GC-0001", "normal", exercised=CRITICAL6), ensure_ascii=False) + "\n",
        encoding="utf-8", newline="")
    (g_dir / "dataset.json").write_text(json.dumps(
        {"schema": ed.SCHEMA, "updated_at": STAMP.isoformat(), "labelers": ["运营 甲"],
         "active_label_version": None, "label_versions": {}}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="")
    draft = g_dir / "labels" / "_working.jsonl"
    draft.write_text(json.dumps(mk_label("GC-0001", "accept"), ensure_ascii=False) + "\n",
                     encoding="utf-8", newline="")

    rc1, out1 = fz.freeze(draft, dataset_dir=g_dir, today=STAMP)
    ver1 = ed.load_index(g_dir / "dataset.json")["active_label_version"]
    check(rc1 == 0 and ver1 and (g_dir / "labels" / f"{ver1}.jsonl").exists(),
          "第一次冻版本成功", f"{ver1}")
    rc2, out2 = fz.freeze(draft, dataset_dir=g_dir, today=STAMP)
    check(rc2 == 2 and any("已经在库里" in x for x in out2),
          "同一版再冻一次被拒绝（不是覆盖）")

    frozen = g_dir / "labels" / f"{ver1}.jsonl"
    keep = frozen.read_text(encoding="utf-8")
    frozen.write_text(keep.replace(STAMP.isoformat(), "2026-09-24"), encoding="utf-8", newline="")
    expect_error(lambda: ed.load_labels(frozen, declared_version=ver1),
                 "就地改过", "就地改冻结文件会被发现")
    frozen.write_text(keep, encoding="utf-8", newline="")
    check(ed.load_labels(frozen, declared_version=ver1) is not None,
          "改回原样后又能读了（判据来自内容，不是时间戳）")

    draft.write_text(json.dumps(mk_label("GC-0001", "accept", labeler="运营 甲"),
                                ensure_ascii=False) + "\n"
                     + json.dumps({"entry_id": "GC-0001", "verdict": "unknown",
                                   "failed_items": [], "labeler": "运营 乙",
                                   "labeled_at": STAMP.isoformat()}, ensure_ascii=False) + "\n",
                     encoding="utf-8", newline="")
    g_dir_index = ed.load_index(g_dir / "dataset.json")
    g_dir_index["labelers"] = ["运营 甲", "运营 乙"]
    (g_dir / "dataset.json").write_text(json.dumps(g_dir_index, ensure_ascii=False, indent=2) + "\n",
                                        encoding="utf-8", newline="")
    rc3, out3 = fz.freeze(draft, dataset_dir=g_dir, today=STAMP)
    idx3 = ed.load_index(g_dir / "dataset.json")
    check(rc3 == 0 and idx3["active_label_version"] != ver1
          and len(idx3["label_versions"]) == 2,
          "改了内容 → 新版本，且旧版本仍在登记里", f"{ver1} → {idx3['active_label_version']}")
    check((g_dir / "labels" / f"{ver1}.jsonl").exists(), "旧版本的标签文件没有被覆盖")

    nameless = json.dumps({"entry_id": "GC-0001", "verdict": "accept", "failed_items": [],
                           "labeler": None, "labeled_at": None}, ensure_ascii=False) + "\n"
    draft.write_text(nameless, encoding="utf-8", newline="")
    rc4, out4 = fz.freeze(draft, dataset_dir=g_dir, today=STAMP)
    check(rc4 == 2 and any("还没有标签人" in x for x in out4),
          "草稿里没有标签人 → 拒绝冻版本（责任人不明确就不进门禁）")

    # ---------------- H 门禁入口
    emit("")
    emit("H 门禁入口本身的三个退出码")
    bad = write_ds("malformed", [dict(mk_entry("GC-0001", "normal"), facts_version=None)],
                   [], [])
    check(gate() == 1, "真数据集（0 条进统计）→ 1：没齐")
    check(gate(gd) == 0, "满编数据集 → 0：齐了")
    check(gate(bad) == 2, "写错的数据集 → 2：与『没齐』分开报")

    # ---------------- I 加样本入口（P1.4 → P1.5 的交接）
    emit("")
    emit("I 加样本入口：从真实登记来，绑定现场算")
    import yaml                                                            # noqa: F401
    ADD = ROOT / "tools" / "add_dataset_sample.py"
    iroot = TMP / "i-root"
    if iroot.exists():
        shutil.rmtree(iroot)
    (iroot / "config").mkdir(parents=True)
    (iroot / "contracts").mkdir(parents=True)
    shutil.copy2(ROOT / "config" / "brand.json", iroot / "config" / "brand.json")
    shutil.copy2(ROOT / ed.POLICY.relative_to(ROOT), iroot / "contracts" / "data-policy-v1.yaml")
    idir = iroot / "materials" / "SKU-01"
    idir.mkdir(parents=True)
    shutil.copy2(ROOT / FULL, idir / "product.json")
    shutil.copy2(ROOT / FRONT, idir / "front.jpg")

    reg_doc = {"schema": "pilot-registry/v1", "updated_at": STAMP.isoformat(),
               "operators": [{"id": "OP-A"}],
               "entries": [{"order": 1, "id": "SKU-01", "category": "home_kitchen",
                            "batch": "calibration", "operator": "OP-A",
                            "assets": [{"kind": "front",
                                        "path": "materials/SKU-01/front.jpg",
                                        "sha256": ed.sha256_file(idir / "front.jpg")}]}]}
    i_reg = TMP / "i-registry.yaml"
    i_reg.write_text(yaml.safe_dump(reg_doc, allow_unicode=True, sort_keys=False),
                     encoding="utf-8", newline="")
    i_ds = write_ds("i-ds", [], [], [])

    def add(*extra) -> int:
        cmd = [sys.executable, str(ADD), "--registry", str(i_reg), "--dataset", str(i_ds),
               "--root", str(iroot)] + list(extra)
        return subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace").returncode

    def audit_i():
        return ed.audit(dataset_dir=i_ds, root=iroot,
                        brand=iroot / "config" / "brand.json",
                        policy=iroot / "contracts" / "data-policy-v1.yaml")

    def bind_of(report, eid) -> str:
        """绑定结果看 `bind` 那一栏：没贴标签时 status 一律是 unattributed，
        所以『文件还在不在、哈希对不对』要从 bind 读，别从 status 读。"""
        for r in report["entries"]:
            if r["entry_id"] == eid:
                return str(r.get("bind"))
        return "<没有这条>"

    SAMPLE_ARGS = ("--sku", "SKU-01", "--case-class", "normal", "--note", "正常输入",
                   "--item", "cf.structure")
    check(add(*SAMPLE_ARGS, "--dry-run") == 0, "--dry-run 试算成功")
    check(not (i_ds / "manifest.jsonl").read_text(encoding="utf-8").strip(),
          "--dry-run 没有写文件")
    check(add(*SAMPLE_ARGS) == 0, "真 SKU → 写入成功")
    rep_i = audit_i()
    check(bind_of(rep_i, "GC-0001") == "ok"
          and status_of(rep_i, "GC-0001") == "unattributed",
          "加进去的样本绑定就是 ok，但没标签人 → 仍是『待标注』不是『通过』",
          f"bind={bind_of(rep_i, 'GC-0001')} status={status_of(rep_i, 'GC-0001')}")
    row_i = json.loads((i_ds / "manifest.jsonl").read_text(encoding="utf-8").splitlines()[0])
    check(row_i["source_kind"] == "pilot"
          and row_i["facts_version"] == ed.compute_facts_version(
              ["materials/SKU-01/product.json"], root=iroot,
              brand=iroot / "config" / "brand.json",
              policy=iroot / "contracts" / "data-policy-v1.yaml"),
          "source_kind 记成 pilot，facts_version 与现场算的一致")

    check(add("--sku", "SKU-99", "--case-class", "normal", "--note", "没有这个 SKU") == 2,
          "登记表里没有的 SKU → 2（先过 P1.4，再做 P1.5）")
    check(add(*SAMPLE_ARGS, "--entry-id", "GC-0001") == 2,
          "同名 entry_id 默认拒绝（不就地改）")
    check(add(*SAMPLE_ARGS, "--entry-id", "GC-0001", "--replace") == 0,
          "--replace 才允许就地改")
    check(add("--sku", "SKU-01", "--case-class", "normal", "--note", "x",
              "--item", "cf.不存在的项") == 2, "清单里没有的项 → 2")

    # 换一张**内容不同**的图（别拿同一张盖同一张 —— 那样哈希没变，什么都证明不了）
    shutil.copy2(ROOT / "examples" / "input" / "cup_contents.jpg", idir / "front.jpg")
    check(bind_of(audit_i(), "GC-0001") == "mismatch",
          "素材被换了 → 这条样本立刻变 mismatch（绑定是落在文件上的）")
    shutil.copy2(ROOT / FRONT, idir / "front.jpg")
    (idir / "product.json").unlink()
    check(add("--sku", "SKU-01", "--case-class", "normal", "--note", "正常输入") == 1,
          "事实来源不在 → 1（还没做到，不是写错）")
    check(bind_of(audit_i(), "GC-0001") == "pending_input",
          "同一件事在数据集里也如实报 pending_input")
    shutil.copy2(ROOT / FULL, idir / "product.json")

    emit("")
    emit("=" * 72)
    if fails:
        emit(f"结论：{len(fails)} 条不过 —— " + "；".join(fails))
        rc = 1
    else:
        emit("结论：全部通过")
        rc = 0
    emit("")
    emit("当前真实数据集：5 条样例 · 0 条进统计 —— 门报红，原因是没有真实试点样本")
    emit("              和登记在案的标签人，不是判据或文件的问题。")
    emit("边界：本报告只证明这套判据会红也会绿、样例凑不了数、改标签必须新增版本；")
    emit("      加样本入口只接受真实登记的 SKU、且落盘前自绑过一次；")
    emit("      不证明那 5 条样例该判接受还是拒绝（那要标签人给），")
    emit("      也不证明任何一条真实 SKU 已经跑过。")
    emit("")
    emit(f"报告：{REPORT}")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
