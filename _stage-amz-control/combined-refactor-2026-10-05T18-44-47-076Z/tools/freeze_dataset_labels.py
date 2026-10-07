#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""把草稿标签冻成一个版本 —— 只许新增版本，不许覆盖。

为什么要有这一步：交付追溯要能回答"当时这张图是在哪一版标签下被判的"。
如果标签可以被就地改，这个问题就永远答不上来 —— 改了以后，谁也不知道
上一版长什么样。所以标签文件的名字就是它内容的版本（`gcv1-<前 12 位>`），
加载时（`src/eval_dataset.py`）会重新算一遍核对。

两道必须先过的门：

    ① **标签人必须登记在案。** `dataset.json` 的 `labelers` 是"谁有权判这套样本"
       的登记。草稿里没有标签人、或标签人不在登记里，这一步直接拒绝 ——
       计划 P1.5 写着「标签责任人不明确时样本不进入门禁」，这里就是那句话的执行点。
       要注意：把一个人加进 `labelers` 是一次明确的人事决定，不是技术动作。
    ② **同一版不能冻两次。** 已经存在的版本号再冻一次会被拒绝：
       改了内容就会得到新的版本号，所以"想覆盖"这件事在结构上做不到。

用法：
    python tools/freeze_dataset_labels.py --dry-run     # 只报会冻成哪一版
    python tools/freeze_dataset_labels.py               # 真的落盘并更新 dataset.json

退出码：0 冻成功（或 dry-run 通过）/ 1 参数用法错 / 2 被拒绝（有人得先去补东西）。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402
enable_utf8()
import eval_dataset as ed  # noqa: E402

DEFAULT_DRAFT = ed.LABELS_DIR / "_working.jsonl"


def freeze(draft_path=DEFAULT_DRAFT, *, dataset_dir=ed.DATASET_DIR, today=None,
           dry_run=False) -> tuple[int, list[str]]:
    """返回 (退出码, 要打印的行)。拒绝时退出码 2，且**不写任何文件**。"""
    base = Path(dataset_dir)
    index_path = base / "dataset.json"
    out: list[str] = []

    known = set(ed.checklist_items())
    try:
        rows = ed.read_jsonl(draft_path)
        problems: list[str] = []
        for i, row in enumerate(rows):
            problems.extend(ed.validate_label(i, row, known))
    except ed.DatasetError as exc:
        return 2, [f"草稿读不出来：{exc}"]
    if problems:
        return 2, ["草稿本身不合法："] + [f"  - {p}" for p in problems]
    if not rows:
        return 2, [f"{draft_path} 里一条都没有 —— 没有可冻的东西。"]

    try:
        index = ed.load_index(index_path)
    except ed.DatasetError as exc:
        return 2, [f"数据集索引读不出来：{exc}"]

    labelers = {str(x) for x in (index.get("labelers") or [])}
    nameless = [str(r.get("entry_id")) for r in rows if not r.get("labeler")]
    if nameless:
        out.append("拒绝：这些样本还没有标签人 —— " + "、".join(nameless))
        out.append("  计划 P1.5：标签责任人不明确时样本不进入门禁，只保留为待标注。")
        out.append("  补法：在草稿里给每条写上 labeler（谁判的）与 labeled_at，"
                   "再把这个人登记进 dataset.json 的 labelers。")
        return 2, out
    strangers = sorted({str(r["labeler"]) for r in rows} - labelers)
    if strangers:
        out.append("拒绝：这些标签人不在 dataset.json 的 labelers 里 —— " + "、".join(strangers))
        out.append("  把人加进 labelers 是明确的人事决定（谁有权判这套样本），"
                   "不是技术动作；先登记，再冻版本。")
        return 2, out

    version = ed.labels_version(rows)
    rel = f"labels/{version}.jsonl"
    versions = dict(index.get("label_versions") or {})
    if version in versions or (base / rel).exists():
        out.append(f"拒绝：{version} 已经在库里（{versions.get(version, {}).get('file', rel)}）。")
        out.append("  改标签要**新增一版**，不是覆盖旧的那一版 —— "
                   "就地覆盖会让'当时哪一版标签判的'永远答不出来。")
        return 2, out

    out.append(f"草稿：{len(rows)} 条 · 标签人：{'、'.join(sorted({str(r['labeler']) for r in rows}))}")
    out.append(f"版本：{version}（由内容算出）")
    out.append(f"落盘：{base / rel}")
    if dry_run:
        out.append("dry-run：没有写任何文件。")
        return 0, out

    stamp = (today or date.today()).isoformat()
    payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    (base / "labels").mkdir(parents=True, exist_ok=True)
    (base / rel).write_text(payload, encoding="utf-8", newline="")

    versions[version] = {"file": rel, "frozen_at": stamp, "count": len(rows)}
    new_index = dict(index)
    new_index["label_versions"] = versions
    new_index["active_label_version"] = version
    new_index["updated_at"] = stamp
    index_path.write_text(json.dumps(new_index, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8", newline="")
    out.append(f"已激活：active_label_version = {version}")
    return 0, out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="把草稿标签冻成一个版本（只新增，不覆盖）")
    ap.add_argument("--from", dest="draft", default=str(DEFAULT_DRAFT),
                    help="草稿标签文件（默认 labels/_working.jsonl）")
    ap.add_argument("--dataset-dir", default=str(ed.DATASET_DIR))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    rc, lines = freeze(args.draft, dataset_dir=args.dataset_dir, dry_run=args.dry_run)
    print("=" * 72)
    print("冻结数据集标签")
    print("=" * 72)
    for line in lines:
        print(line)
    print(f"\n结果：{'通过' if rc == 0 else '被拒绝'}（退出码 {rc}）。")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())