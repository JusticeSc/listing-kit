#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""G1 门禁入口：试点样本够不够（**红是实话**）。

它报的是"现在够不够"，不验判据会不会红 —— 判据的反向证据在
`tools/verify_p1_4_registry.py`。三件事分开，因为它们的"红"意思完全不同：

    退出码 1 = 业务还没做到（样本没齐、素材还没放）      → 红是实话
    退出码 2 = 登记表写错了，或与真实输入对不上（人得改）  → 别混成"一屏红"
    退出码 0 = 齐了，而且是**核对过**的齐：版本现场算过、素材哈希对过

第三种最容易造假：只看字段在不在，随手写个格式合法的版本号就能变绿。
所以这里额外要求 `resolve()` 真的核到东西 —— 一条输入都没提供时，
`any_input` 会是 0，并作为待补项明写出来，而不是"没报错就算过"。

用哪种红来表示"该跑生成器"还是"该改人写的字"，本项目在文档守卫上已经踩过一次：
把两件事混报，人看到红会以为是自己的错，而九成其实是"活还没干到"。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402
enable_utf8()
import pilot_registry as pr  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="G1 门禁：20-SKU 试点登记够不够")
    ap.add_argument("--path", default=None, help="登记的路径（默认 pilot/pilot-registry.yaml）")
    ap.add_argument("--root", default=None,
                    help="核对素材与事实来源时用的项目根（默认就是项目根；判据用它指临时目录）")
    ap.add_argument("--policy", default=None,
                    help="授权文件路径（默认 contracts/data-policy-v1.yaml）")
    args = ap.parse_args(argv)

    print("=" * 72)
    print("试点样本门禁（G1 的输入之一）")
    print("=" * 72)
    try:
        reg = pr.load_registry(args.path)
    except pr.RegistryError as exc:
        print("登记表本身不合法 —— 这是『写错了』，不是『还没做到』：")
        print(f"  {exc}")
        return 2

    res = pr.resolve(reg, root=args.root, policy_path=args.policy)
    c = res["counts"]
    print("现场核对（事实版本与素材哈希都重新算一遍，手写的不算数）：")
    print(f"  在 {c[pr.STATUS_OK]} 条 · 还没放 {c[pr.STATUS_PENDING]} 条 · "
          f"对不上 {c[pr.STATUS_MISMATCH]} 条 · 真的核到输入的 {res['any_input']} 条")
    print(f"  授权文件版本 {res['policy_version'] or '（读不出来）'}"
          + ("（已签署）" if res["policy_signed"] else "（还没签署：signed_by 为空）"))
    if res["policy_error"]:
        print(f"  授权文件的问题：{res['policy_error']}")
    for eid, r in res["entries"].items():
        for m in r["mismatch"]:
            print(f"  ! 对不上 · {eid}：{m}")
    if c[pr.STATUS_MISMATCH]:
        print()
        print(f"结果：{c[pr.STATUS_MISMATCH]} 条与真实输入对不上（退出码 2）—— "
              f"这是『要人查』，不是『还没做到』。")
        return 2
    if not res["policy_signed"]:
        print("  提醒：allowlist 还没签署，即便样本齐了，一次真实参考图外发也不会发生"
              "（那是 P1.2 的完成条件，与本门禁各算各的）。")
    print()

    s = pr.summarize(reg, resolution=res)
    print(f"真实 SKU   {s['real']}/{s['targets']['total']}"
          + (f"（另有 {s['sample']} 条标了 sample，不计数）" if s["sample"] else ""))
    print(f"可跑(ready) {s['ready_count']} 条 · 缺料 {len(s['not_ready'])} 条"
          + (f"：{ {k: v for k, v in list(s['not_ready'].items())[:3]} }" if s["not_ready"] else ""))
    print(f"品类分布   {s['by_category'] or '（空）'}")
    print(f"操作员分布 {s['by_operator'] or '（空）'}")
    print(f"批次分布   calibration {s['by_batch'].get('calibration', 0)}"
          f"/{len(s['targets']['calibration_orders'])} · "
          f"official {s['by_batch'].get('official', 0)}"
          f"/{s['targets']['total'] - len(s['targets']['calibration_orders'])}")
    print()
    if s["ready"]:
        print("结果：齐了（退出码 0）。")
        return 0
    print(f"结果：样本还没齐（退出码 1）—— {len(s['problems'])} 条待补：")
    for x in s["problems"]:
        print(f"  · {x}")
    print()
    print("说明：这一条红**不是**文件写错了。补齐的路径是拿到真实 SKU 与授权，"
          "不是往里填样例数据（样例不计数）。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
