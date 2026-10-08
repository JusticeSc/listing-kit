#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""签署 / 修改外发授权（`contracts/data-policy-v1.yaml`），并把每一版存档。

它补两件此前只能手工做的事：

    ① **签一次字要写对九个字段**。一条 `allowed` 规则要有 id / asset_class / purpose /
       provider / model / decision / approver / approved_at / retention，还要求 id 唯一、
       键（类别×用途×供应商×模型）唯一。手写必然写漏，而漏在第几项上只有校验器的报错知道。
    ② **签完之后答不出"当时批的原文是什么"**。版本号由内容算出，内容一改就再也算不回旧号；
       本项目又没有版本库。所以每次改动都把**上一版与这一版的语义内容**存进
       `contracts/data-policy-versions/<版本号>.yaml` —— 版本号是算出来的，原文是存下来的，
       两件事合起来才叫"可追溯"。

三条纪律：

    ① **不替人决定**。批准人、批准日期、有效期、保留删除约束都由你给；工具不填默认值。
    ② **校验器说了算**。写之前先跑 `data_policy.validate_policy`；不过就不落盘。
    ③ **只增不改版本**。改一次产生一版新存档，旧版不会被覆盖（文件名就是版本号）。

一句必须说清的话：**签的是"范围"**。预算硬限制、幂等、超时核对归 Phase 2
（P2.1–P2.6 + 计划 §7.2 的外部动作权限卡），现在还不存在 ——
所以这一版授权**不等于"现在可以发真实请求"**。工具每次都会把这句话打出来。

退出码（与门禁同一套语言）：

    0 = 已写入 / `--dry-run` 试算成功 / `--list`·`--history` 正常
    2 = 写错了：缺必填字段、校验不过、id 或键重复、撤销一个不存在的规则
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402
enable_utf8()
import data_policy as dp  # noqa: E402

ARCHIVE_HEADER = (
    "# =============================================================================\n"
    "# 授权版本存档 —— 把本文件重新算一遍，必须得出文件名里那个版本号。\n"
    "# 存的是**语义字段**（不含 updated_at）；就地改它会被 tools/verify_p1_2_policy.py 抓住。\n"
    "# 由 tools/sign_allowlist.py 写入；别手工改。\n"
    "# =============================================================================\n"
)


def versions_dir(root: Path) -> Path:
    """存档目录跟着 --root 走 —— 判据要在临时项目根上跑，不能总指真项目。"""
    return root / "contracts" / "data-policy-versions"


def split_header(text: str) -> tuple[str, str]:
    """开头注释块与正文分开。注释块原样保留 —— 说明不能被重写吃掉。"""
    lines = text.split("\n")
    i = 0
    while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith("#")):
        i += 1
    return "\n".join(lines[:i]).rstrip("\n"), "\n".join(lines[i:])


def render(header: str, doc: dict) -> str:
    import yaml
    body = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False,
                          default_flow_style=False, width=1000)
    head = header.rstrip("\n")
    return (head + "\n\n" if head else "") + body.rstrip("\n") + "\n"


def load_doc(path: Path) -> tuple[str, dict]:
    import yaml
    text = path.read_text(encoding="utf-8")
    header, body = split_header(text)
    doc = yaml.safe_load(body)
    if not isinstance(doc, dict):
        raise dp.PolicyError("政策文件正文顶层不是映射")
    return header, doc


def archive(root: Path, doc: dict, *, note: str) -> Path:
    """把这一版的语义内容存下来。版本号是算出来的，所以同名即同语义。"""
    import yaml
    ver = dp.policy_version(doc)
    p = dp.archive_path(ver, root=root)
    if p.exists():
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(dp.semantic_doc(doc), allow_unicode=True, sort_keys=False,
                          default_flow_style=False, width=1000)
    p.write_text(ARCHIVE_HEADER + body, encoding="utf-8", newline="")
    print(f"  已归档这一版：{p.relative_to(root).as_posix()}（{note}）")
    return p


def show_list(doc: dict, *, root: Path, policy_path: Path) -> None:
    ver = dp.policy_version(doc)
    print(f"政策文件 {policy_path.relative_to(root).as_posix()} · 版本 {ver}")
    print(f"  签署：signed_by={doc.get('signed_by')!r} · signed_at={doc.get('signed_at')!r}"
          + ("" if doc.get("signed_by") else "  ← 未签：规则表里的 allowed 一条都不生效"))
    print("  素材类别闭集（default 只许 unapproved / denied）：")
    for k, v in (doc.get("asset_classes") or {}).items():
        print(f"    {k:<18} default={v.get('default'):<11} {v.get('label')}")
    print("  用途闭集：")
    for k, v in (doc.get("purposes") or {}).items():
        print(f"    {k:<28} {v}")
    rules = doc.get("rules") or []
    print(f"  规则 {len(rules)} 条" + ("（空表 = 一条外发都不允许）" if not rules else "："))
    for r in rules:
        print(f"    [{r.get('id')}] {r.get('asset_class')} × {r.get('purpose')} × "
              f"{r.get('provider')} × {r.get('model')} → {r.get('decision')}"
              + (f"（到 {r['expires_at']} 止）" if r.get("expires_at") else ""))
    print(f"  存档目录：{versions_dir(root).relative_to(root).as_posix()}/")


def show_history(root: Path) -> int:
    d = versions_dir(root)
    files = sorted(d.glob("*.yaml")) if d.exists() else []
    print(f"授权版本存档：{d.relative_to(root).as_posix()}/ · {len(files)} 版")
    if not files:
        print("  （还没有任何存档 —— 第一次签署或改动时才会写）")
        return 0
    bad = 0
    for f in sorted(files, key=lambda x: x.stem, reverse=True):
        import yaml
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        live = dp.policy_version(doc)
        ok = live == f.stem
        bad += 0 if ok else 1
        print(f"  {f.stem} · 签署 {doc.get('signed_by') or '（未签）'} · "
              f"规则 {len(doc.get('rules') or [])} 条 · "
              + ("重算一致" if ok else f"**重算得到 {live}，与文件名不符**"))
    if bad:
        print(f"  有 {bad} 版的存档被就地改过 —— 存档就不算数了。")
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="签署 / 修改外发授权，并归档每一版")
    ap.add_argument("--policy", default=None, help="政策文件（默认 contracts/data-policy-v1.yaml）")
    ap.add_argument("--root", default=None, help="项目根（默认项目根；判据用它指临时目录）")
    ap.add_argument("--list", action="store_true", help="打印闭集与现有规则，不写文件")
    ap.add_argument("--history", action="store_true", help="列出所有已归档的版本")
    ap.add_argument("--approve", action="store_true", help="签署并追加一条规则")
    ap.add_argument("--revoke", default=None, metavar="RULE_ID", help="撤销一条规则")
    ap.add_argument("--id", default=None, help="规则短名（审计记录引它）")
    ap.add_argument("--asset-class", dest="asset_class", default=None)
    ap.add_argument("--purpose", default=None)
    ap.add_argument("--provider", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--decision", default="allowed", choices=list(dp.DECISIONS))
    ap.add_argument("--by", default=None, help="谁签的（写进 signed_by，不填默认值）")
    ap.add_argument("--at", default=None, help="哪天签的 YYYY-MM-DD")
    ap.add_argument("--approver", default=None, help="这条规则谁批的（缺省与 --by 相同）")
    ap.add_argument("--approved-at", dest="approved_at", default=None,
                    help="这条规则哪天批的（缺省与 --at 相同）")
    ap.add_argument("--expires", default=None, help="失效日期 YYYY-MM-DD（可选）")
    ap.add_argument("--retention", default=None, help="保留/删除约束原文")
    ap.add_argument("--notes", default=None, help="备注（可选）")
    ap.add_argument("--dry-run", action="store_true", help="只试算并打印，不写文件")
    args = ap.parse_args(argv)

    root = Path(args.root) if args.root else ROOT
    policy_path = Path(args.policy) if args.policy else (root / "contracts" / "data-policy-v1.yaml")
    print("=" * 72)
    print("外发授权签署" + ("（dry-run）" if args.dry_run else ""))
    print("=" * 72)
    if not policy_path.exists():
        print(f"找不到政策文件：{policy_path}（退出码 2）")
        return 2
    try:
        header, doc = load_doc(policy_path)
    except Exception as exc:                                       # noqa: BLE001
        print(f"政策文件读不出来（退出码 2）：{type(exc).__name__}: {exc}")
        return 2
    try:
        problems = dp.validate_policy(doc)
    except Exception as exc:                                       # noqa: BLE001
        print(f"政策文件校验失败（退出码 2）：{exc}")
        return 2
    if problems:
        print("现在这份政策文件本身就不合法（退出码 2）—— 先修它：")
        for x in problems:
            print(f"  - {x}")
        return 2

    if args.history:
        return show_history(root)
    if args.list or not (args.approve or args.revoke):
        show_list(doc, root=root, policy_path=policy_path)
        if not (args.approve or args.revoke):
            print("\n（没有指定 --approve 或 --revoke，只打印现状。）")
        return 0

    v_old = dp.policy_version(doc)
    if args.dry_run:
        print(f"（dry-run）改动前这一版会先归档："
              f"{dp.archive_path(v_old, root=root).relative_to(root).as_posix()}")
    else:
        archive(root, doc, note="改动前的版本")       # 先保住旧版，再改

    if args.revoke:
        rules = list(doc.get("rules") or [])
        keep = [r for r in rules if str(r.get("id")) != args.revoke]
        if len(keep) == len(rules):
            print(f"规则 {args.revoke!r} 不在表里（退出码 2）—— 撤销一个不存在的东西不算动作。")
            return 2
        doc["rules"] = keep
        what = f"撤销规则 {args.revoke}"
    else:
        need = {"--id": args.id, "--asset-class": args.asset_class, "--purpose": args.purpose,
                "--provider": args.provider, "--model": args.model, "--retention": args.retention,
                "--by": args.by, "--at": args.at}
        blank = [k for k, v in need.items() if not str(v or "").strip()]
        if blank:
            print(f"缺必填字段（退出码 2）：{'、'.join(blank)}")
            print("  批准人、日期、保留删除约束都由人给 —— 工具不替谁决定，也不填默认值。")
            return 2
        approver = args.approver or args.by
        approved_at = args.approved_at or args.at
        rules = list(doc.get("rules") or [])
        if any(str(r.get("id")) == args.id for r in rules):
            print(f"规则 id {args.id!r} 已经存在（退出码 2）—— "
                  f"同一个 id 只能有一条；要改就先 --revoke 它。")
            return 2
        rule = {"id": args.id, "asset_class": args.asset_class, "purpose": args.purpose,
                "provider": args.provider, "model": args.model, "decision": args.decision}
        if args.decision == "allowed":
            rule["approver"] = approver
            rule["approved_at"] = approved_at
        if args.expires:
            rule["expires_at"] = args.expires
        rule["retention"] = args.retention
        if args.notes:
            rule["notes"] = args.notes
        rules.append(rule)
        doc["rules"] = rules
        doc["signed_by"] = args.by
        doc["signed_at"] = args.at
        what = (f"签署（{args.by} @ {args.at}）并追加规则 {args.id} → {args.decision}")

    doc["updated_at"] = date.today().isoformat()
    problems = dp.validate_policy(doc)
    if problems:
        print("改完之后的政策不合法（退出码 2）—— 没有落盘：")
        for x in problems:
            print(f"  - {x}")
        return 2
    v_new = dp.policy_version(doc)
    print(f"{what}")
    print(f"  版本 {v_old} → {v_new}" + ("（语义没变）" if v_new == v_old else ""))

    if args.dry_run:
        print("\n" + render(header, doc))
        print("--dry-run：没有写文件。")
        return 0

    policy_path.write_text(render(header, doc), encoding="utf-8", newline="")
    print(f"  已写入 {policy_path.relative_to(root).as_posix()}")
    archive(root, doc, note="改动后的版本")
    print()
    print("签的是**范围**：预算硬限制、幂等、超时核对归 Phase 2（P2.1–P2.6 与计划 §7.2 的")
    print("外部动作权限卡），现在还不存在 —— 所以这一版授权不等于『现在可以发真实请求』。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
