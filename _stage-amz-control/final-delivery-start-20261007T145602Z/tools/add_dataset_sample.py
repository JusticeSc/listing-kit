#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""把一个**真实试点 SKU** 变成数据集里的一条样本。

它补的是 P1.5 缺口的那一环：数据集判据齐了（能验哈希、能验 FactsVersion、能报冲突），
但"怎么把一条真样本加进去"此前只有一次性脚本。而 `manifest.jsonl` 里每条要写
`inputs[{kind,ref,sha256}]` 和 `facts_version` —— 手抄必然抄错，抄错了那条样本**不进统计**，
人却以为已经加上了。

分工与 P1.4 的 `tools/fill_pilot_registry.py` 同一条纪律：

    人决定的（只有你知道）：这条样本**想考什么** —— `case_class`、`design_note`、
                            `exercised_items`，外加"是哪一份 SKU"
    机器写死的：`inputs[]` 的路径与 sha256、`facts_version`、`source_kind: pilot`

三条纪律：

    ① **只从真实登记来**。输入取自 `pilot/pilot-registry.yaml` 里那条 SKU 的
       事实来源与素材清单 —— 不在登记表里的 SKU 直接拒绝（先过 P1.4，再做 P1.5）。
    ② **写进去之前先自绑一次**。`eval_dataset.bind_entry` 说 `ok` 才落盘；
       说 `pending_input` 或 `mismatch` 就退回，不往里塞一条永远不会进统计的样本。
    ③ **不就地改**。`entry_id` 已存在时默认拒绝（与标签"只新增版本"同一条纪律）；
       确实要改就显式 `--replace`，并知道这会改变 `dataset_version`。

退出码（与门禁同一套语言）：

    0 = 已写入（或 `--dry-run` 试算成功）
    1 = 这个 SKU 的素材或事实来源还没到位 —— 业务没做到，不是文件写错
    2 = 写错了：SKU 不在登记表 / case_class 不合法 / 条目不在清单 / entry_id 重复 …
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402
enable_utf8()
import eval_dataset as ed  # noqa: E402
import pilot_registry as pr  # noqa: E402

DEFAULT_REGISTRY = ROOT / "pilot" / "pilot-registry.yaml"


def load_manifest_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ed.DatasetError(f"manifest.jsonl 第 {i} 行不是合法 JSON：{exc}") from None
        if not isinstance(obj, dict):
            raise ed.DatasetError(f"manifest.jsonl 第 {i} 行不是对象")
        rows.append(obj)
    return rows


def next_entry_id(rows: list[dict]) -> str:
    used = set()
    for r in rows:
        m = str(r.get("entry_id") or "")
        if m.startswith("GC-") and m[3:].isdigit():
            used.add(int(m[3:]))
    n = 1
    while n in used:
        n += 1
    return f"GC-{n:04d}"


def build_inputs(entry: dict, *, root: Path) -> tuple[list[dict], list[str]]:
    """按登记表的约定路径生成 inputs[]。缺文件的部分**如实上报**，不跳过。"""
    sid = str(entry.get("id") or "")
    inputs: list[dict] = []
    missing: list[str] = []

    ref = pr.facts_ref(sid)
    p = root / ref
    if p.exists():
        inputs.append({"kind": "product_facts_source", "ref": ref,
                       "sha256": ed.sha256_file(p)})
    else:
        missing.append(f"事实来源还没放：{ref}")

    for a in entry.get("assets") or []:
        if not isinstance(a, dict):
            continue
        arel = str(a.get("path") or "")
        ap = root / arel
        if not ap.exists():
            missing.append(f"素材还没放：{arel}")
            continue
        inputs.append({"kind": "material_image", "ref": arel,
                       "sha256": ed.sha256_file(ap)})
    return inputs, missing


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="把一份真实试点 SKU 变成数据集样本")
    ap.add_argument("--sku", required=True, help="登记表里的匿名编号，形如 SKU-01")
    ap.add_argument("--case-class", required=True, choices=list(ed.CASE_CLASSES),
                    help="这条样本想考哪一类：" + " / ".join(ed.CASE_CLASSES))
    ap.add_argument("--note", required=True, help="设计说明：这条样本想考什么、为什么这么造")
    ap.add_argument("--item", action="append", default=[],
                    help="这条样本会考到的清单项 id（可重复；见 contracts/review-checklist-v1.yaml）")
    ap.add_argument("--entry-id", default=None, help="缺省取下一个空号 GC-NNNN")
    ap.add_argument("--registry", default=None, help="试点登记表（默认 pilot/pilot-registry.yaml）")
    ap.add_argument("--dataset", default=None, help="数据集目录（默认 evals/product-v1/dataset）")
    ap.add_argument("--root", default=None, help="素材与事实来源所在的项目根（默认项目根）")
    ap.add_argument("--replace", action="store_true",
                    help="就地改一条已存在的 entry_id（会改变 dataset_version；默认拒绝）")
    ap.add_argument("--dry-run", action="store_true", help="只试算并打印，不写文件")
    args = ap.parse_args(argv)

    root = Path(args.root) if args.root else ROOT
    registry_path = Path(args.registry) if args.registry else DEFAULT_REGISTRY
    dataset_dir = Path(args.dataset) if args.dataset else ed.DATASET_DIR
    manifest_path = dataset_dir / "manifest.jsonl"
    brand = root / "config" / "brand.json"
    policy = root / "contracts" / "data-policy-v1.yaml"

    print("=" * 72)
    print(f"新增数据集样本：{args.sku}（{args.case_class}）")
    print("=" * 72)

    if not args.note.strip():
        print("--note 是空的 —— 这一条样本『想考什么』必须写清楚（退出码 2）。")
        return 2

    try:
        reg = pr.load_registry(registry_path)
    except pr.RegistryError as exc:
        print("试点登记表读不出来 —— 这是『写错了』（退出码 2）：")
        print(f"  {exc}")
        return 2
    hit = next((e for e in (reg.get("entries") or [])
                if isinstance(e, dict) and str(e.get("id")) == args.sku), None)
    if hit is None:
        declared = [str(e.get("id")) for e in (reg.get("entries") or []) if isinstance(e, dict)]
        print(f"登记表里没有 {args.sku}（退出码 2）—— 现在有：{declared or '（空）'}")
        print("  先在 pilot/pilot-registry.yaml 里登记这个 SKU，再回来加样本。")
        return 2

    known_items = ed.checklist_items()
    bad_items = [x for x in args.item if x not in known_items]
    if bad_items:
        print(f"这些清单项不存在（退出码 2）：{bad_items}")
        print(f"  可选：{'、'.join(sorted(known_items))}")
        return 2

    inputs, missing = build_inputs(hit, root=root)
    if missing or not any(i["kind"] == "product_facts_source" for i in inputs):
        print(f"输入还没到位（退出码 1）—— 这些不是文件写错，把东西放进去就好：")
        for x in missing:
            print(f"  · {x}")
        return 1

    try:
        rows = load_manifest_rows(manifest_path)
    except ed.DatasetError as exc:
        print(f"现有清单读不出来 —— 先修它（退出码 2）：\n  {exc}")
        return 2

    entry_id = args.entry_id or next_entry_id(rows)
    exists = any(str(r.get("entry_id")) == entry_id for r in rows)
    if exists and not args.replace:
        print(f"{entry_id} 已经存在（退出码 2）—— 同名就地改会让人分不清哪一版在算数。")
        print("  换个编号，或显式加 --replace（会改变 dataset_version）。")
        return 2

    try:
        facts_version = ed.compute_facts_version(
            [i["ref"] for i in inputs if i["kind"] == "product_facts_source"],
            root=root, brand=brand, policy=policy)
    except Exception as exc:                              # noqa: BLE001
        print(f"算不出 FactsVersion（退出码 2）：{type(exc).__name__}: {exc}")
        return 2

    entry = {"entry_id": entry_id, "case_class": args.case_class, "source_kind": "pilot",
             "design_note": args.note.strip(), "inputs": inputs,
             "facts_version": facts_version, "exercised_items": list(args.item)}
    try:
        bind = ed.bind_entry(entry, root=root, brand=brand, policy=policy)
    except Exception as exc:                              # noqa: BLE001
        print(f"自绑失败（退出码 2）：{type(exc).__name__}: {exc}")
        return 2
    if bind["status"] != "ok":
        print(f"自绑结果是 {bind['status']}（退出码 1）—— 落盘了也不会进统计，先解决这些：")
        for x in bind["reasons"]:
            print(f"  · {x}")
        return 1

    print(f"条目 {entry_id} · 输入 {len(inputs)} 份 · facts_version {facts_version}")
    print(f"  case_class={args.case_class} · source_kind=pilot（只有它进 G1 覆盖统计）")
    print(f"  会考到的项：{args.item or '（没写 —— 关键项正反例统计会缺这一条）'}")
    if args.dry_run:
        print()
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        print("\n--dry-run：没有写文件。")
        return 0

    out = [r for r in rows if str(r.get("entry_id")) != entry_id] + [entry]
    out.sort(key=lambda r: str(r.get("entry_id")))
    dataset_dir.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out),
                             encoding="utf-8", newline="")
    print(f"已写入 {manifest_path}（共 {len(out)} 条）。")
    print("  接着跑 `python tools/check_dataset_ready.py` 看还差什么。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
