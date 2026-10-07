#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""G1 门禁入口之一：Golden/Counterexample 数据集够不够用。

它只回答一个问题：**现在能不能拿这套样本证明产品可用？** 不够就点名差什么。

两个退出码分开报（和 `tools/check_pilot_ready.py` 同一个教训）：

    1 = 还没齐（业务未完成）：真实试点样本、登记在案的标签人、关键项正反例缺任一样
    2 = 文件写错了（人得去改）：数据集登记或标签文件不合法

混报的后果很具体：人看到红会以为"自己写错了"，而实际上只是活还没干到。

用法：
    python tools/check_dataset_ready.py            # 读真数据集
    python tools/check_dataset_ready.py --path evals/.tmp/xxx   # 指到别的数据集目录（验收用）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402
enable_utf8()
import eval_dataset as ed  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="数据集门禁：够不够证明了")
    ap.add_argument("--path", default=None, help="数据集目录（默认 evals/product-v1/dataset）")
    args = ap.parse_args(argv)

    dataset_dir = Path(args.path) if args.path else ed.DATASET_DIR
    try:
        report = ed.audit(dataset_dir=dataset_dir)
    except ed.DatasetError as exc:
        print("数据集写错了（退出码 2）—— 这不是'活还没干到'，是文件本身不合法：")
        print(f"  {exc}")
        return 2

    gaps = ed.ready(report)
    c = report["counts"]
    print(f"数据集 {report['dataset_version']} · 条目 {c['entries']} 条 · 进统计 "
          f"{c['counted']} 条 · 标签版本 {report['active_label_version'] or '（无）'}")
    print(f"  分类分布：{c['by_class']}")
    print(f"  来源分布：{c['by_source']}")
    if report["draft"]["count"]:
        print(f"  草稿（不是标签）：{report['draft']['count']} 条，"
              f"其中没有标签人的 {len(report['draft']['without_labeler'])} 条")
    if not gaps:
        print("结果：齐了（退出码 0）。")
        return 0
    print(f"结果：还没齐（退出码 1），差 {len(gaps)} 项：")
    for g in gaps:
        print(f"  - {g}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())