#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""补齐试点登记表里**机器能算**的那几列。

它解决一个很实际的问题：一条 SKU 要写对 `facts_version`、`data_policy_version` 和每个素材的
sha256。20 条 × 若干张图 = 上百个哈希。手写写不对 —— 而写错了门会退 2，人却会以为是自己
文件格式写错了。所以分工写死：

    人写四列（只有你知道）：order、id、category、operator
                          （`batch` 不用写 —— 它由 order 推，本就是算出来的）
    机器补三列：facts_version、data_policy_version、assets[{kind,path,sha256}]

三条纪律（反向样本见 `tools/verify_p1_4_registry.py` 的 J 段）：

    ① **不猜**。素材或事实来源还没放，就把那一列留空并明说是哪一份缺 ——
       不编版本号、不编哈希。留空的门会如实报 `not-ready`，编出来的门会报「对不上」。
    ② **同一个算法**。版本与哈希都调 `src/pilot_registry.py` 里核对器用的那两个函数；
       两边各写一份算法，迟早算出两个值。
    ③ **注释只在头部**。本文件的说明全在 `schema:` 之前，正文由本工具重写；
       写在正文里的注释会被吃掉。

退出码（与门禁同一套语言）：

    0 = 登记表与素材一致（`--check`）／已写入且没有缺料（普通模式）
    1 = 素材或事实来源还没到位 —— 业务没做到，不是文件写错
    2 = 登记表写错了，或与素材不一致（跑一次本工具即可）
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
import assets as assets_mod  # noqa: E402
import data_policy  # noqa: E402
import pilot_registry as pr  # noqa: E402

DEFAULT_PATH = ROOT / "pilot" / "pilot-registry.yaml"
# 一个 kind 允许的扩展名。留两个以上就说不清哪张算数，所以下面按"说不清"处理。
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
# 正文里键的顺序：人写的在前、机器补的在后 —— 一眼能看出哪些是算出来的
ENTRY_KEYS = ("order", "id", "category", "batch", "operator",
              "facts_version", "data_policy_version", "assets", "sample", "notes")


def split_header(text: str) -> tuple[str, str]:
    """把开头的注释块与正文分开。注释块原样保留 —— 说明不能被重写吃掉。"""
    lines = text.split("\n")
    i = 0
    while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith("#")):
        i += 1
    return "\n".join(lines[:i]).rstrip("\n"), "\n".join(lines[i:])


def scan_assets(sid: str, root: Path) -> tuple[list[dict], list[str]]:
    """扫 materials/<id>/ 按 kind 找图。返回 (assets, 说不清的地方)。"""
    out: list[dict] = []
    notes: list[str] = []
    d = root / pr.MATERIALS_DIRNAME / sid
    for kind in assets_mod.IMAGE_KINDS:
        hits = [d / f"{kind}{e}" for e in IMAGE_EXTS if (d / f"{kind}{e}").exists()]
        if not hits:
            continue
        if len(hits) > 1:
            notes.append(f"{sid}：{kind} 有 {len(hits)} 个不同扩展名（"
                         + "、".join(h.name for h in hits)
                         + "）—— 留一个，否则哪张算数说不清")
            continue
        out.append({"kind": kind,
                    "path": f"{pr.MATERIALS_DIRNAME}/{sid}/{hits[0].name}",
                    "sha256": pr.sha256_file(hits[0])})
    return out, notes


def fill_entry(entry: dict, *, root: Path, policy_version: str) -> tuple[dict, list[str]]:
    """补一条条目里机器能算的字段。缺的东西**留在原处并上报**，不编。"""
    sid = str(entry.get("id") or "")
    missing: list[str] = []
    vals = dict(entry)

    order = entry.get("order")
    if isinstance(order, int) and order > 0:
        vals["batch"] = "calibration" if order in pr.CALIBRATION_ORDERS else "official"
    else:
        missing.append(f"{sid or '（没写 id）'}：还没有 order（执行顺序是批次归属的依据）")

    ref = pr.facts_ref(sid)
    src = root / ref
    if src.exists():
        try:
            vals["facts_version"] = pr.facts_version_of(src, ref, root)
        except Exception as exc:                  # noqa: BLE001
            missing.append(f"{sid}：事实来源读不出来（{type(exc).__name__}: {exc}）")
    else:
        missing.append(f"{sid}：事实来源还没放（{ref}）")

    vals["data_policy_version"] = policy_version

    found, notes = scan_assets(sid, root)
    vals["assets"] = found
    if not found:
        missing.append(f"{sid}：素材还没放（{pr.MATERIALS_DIRNAME}/{sid}/）")
    missing.extend(notes)

    # 统一按 ENTRY_KEYS 排一次序：**键顺序也是内容的一部分** ——
    # 不然同一份内容第二次渲染出来顺序不同，--check 会自己跟自己抖（J 段踩过）。
    new = {k: vals[k] for k in ENTRY_KEYS if k in vals}
    for k, v in vals.items():                     # 不认识的键原样留着
        new.setdefault(k, v)
    return new, missing


def build(reg: dict, *, root: Path, policy_version: str) -> tuple[dict, list[str]]:
    raw = reg.get("entries") or []
    entries = [e for e in raw if isinstance(e, dict)]
    others = [e for e in raw if not isinstance(e, dict)]
    out: list[dict] = []
    missing: list[str] = []
    for e in entries:
        ne, miss = fill_entry(e, root=root, policy_version=policy_version)
        missing.extend(miss)
        out.append(ne)
    out.sort(key=lambda e: e["order"] if isinstance(e.get("order"), int) else 10 ** 6)

    ops = [o for o in (reg.get("operators") or []) if isinstance(o, dict)]
    known = {str(o.get("id")) for o in ops}
    for e in out:
        oid = str(e.get("operator") or "")
        if oid and oid not in known:
            # 只补编号本身 —— tasks_target 是"预分配目标"，那是人的决定，不替他定
            ops.append({"id": oid})
            known.add(oid)
            missing.append(f"operators 里补上了 {oid}（条目里用到但没声明）；"
                           f"tasks_target 留空，要预分配就自己写")

    new = {"schema": reg.get("schema") or pr.SCHEMA,
           "updated_at": reg.get("updated_at") or date.today().isoformat(),
           "operators": ops, "entries": out + others}
    for k, v in reg.items():                      # 顶层多出来的键也留着
        new.setdefault(k, v)
    return new, missing


def render(header: str, reg: dict) -> str:
    """注释头 + 重新序列化的正文。同一个 reg 渲染两次必须一模一样，否则 --check 会自己抖。"""
    import yaml
    body = yaml.safe_dump(reg, allow_unicode=True, sort_keys=False,
                          default_flow_style=False, width=1000)
    head = header.rstrip("\n")
    return (head + "\n\n" if head else "") + body.rstrip("\n") + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="补齐试点登记表里机器能算的字段")
    ap.add_argument("--path", default=None, help="登记表路径（默认 pilot/pilot-registry.yaml）")
    ap.add_argument("--root", default=None, help="素材与事实来源所在的项目根（默认项目根）")
    ap.add_argument("--check", action="store_true", help="只读复核：登记表有没有跟上素材")
    args = ap.parse_args(argv)

    path = Path(args.path) if args.path else DEFAULT_PATH
    root = Path(args.root) if args.root else ROOT
    print("=" * 72)
    print("试点登记表补齐" + ("（只读复核）" if args.check else ""))
    print("=" * 72)
    if not path.exists():
        print(f"找不到登记表：{path}")
        return 2

    text = path.read_text(encoding="utf-8")
    header, body = split_header(text)
    import yaml
    try:
        reg = yaml.safe_load(body)
    except yaml.YAMLError as exc:
        print("正文不是合法 YAML —— 这是『写错了』，不是『还没做到』：")
        print(f"  {exc}")
        return 2
    if not isinstance(reg, dict):
        print("正文顶层不是映射 —— 这是『写错了』。")
        return 2

    pol_path = root / "contracts" / "data-policy-v1.yaml"
    try:
        policy_version = data_policy.load_policy(pol_path).policy_version
    except data_policy.PolicyError as exc:
        print("授权文件读不出来，无法填 data_policy_version —— 这是『写错了』：")
        print(f"  {exc}")
        return 2

    built, missing = build(reg, root=root, policy_version=policy_version)
    problems = pr.validate_registry(built)
    if problems:
        print("补齐之后登记表仍不合法 —— 这是『写错了』，人得改：")
        for x in problems:
            print(f"  - {x}")
        return 2

    n_entries = len(built.get("entries") or [])
    print(f"条目 {n_entries} 条 · 授权版本 {policy_version}")
    if not n_entries:
        print("结果：登记表还是空的（退出码 1）—— 先把每个 SKU 的 order / id / category / "
              "operator 四列写进去（这四列只有你知道），再跑一次本工具补齐机器能算的三列。")
        return 1

    want = render(header, built)

    if args.check:
        if want != text:
            print("结果：登记表与素材不一致（退出码 2）—— 跑一次本工具（不带 --check）即可。")
            return 2
        if missing:
            print(f"结果：登记表已同步，但有 {len(missing)} 处素材还没到位（退出码 1）：")
            for x in missing:
                print(f"  · {x}")
            return 1
        print("结果：登记表与素材一致（退出码 0）。")
        return 0

    if want != text:
        path.write_text(want, encoding="utf-8", newline="")
        print("已写入：机器能算的列都补齐了（注释头原样保留）。")
    else:
        print("没有变化：登记表本来就是最新的。")
    if missing:
        print(f"结果：有 {len(missing)} 处还没到位（退出码 1）—— 这些不是文件写错，"
              f"是把素材/事实来源放进去就好：")
        for x in missing:
            print(f"  · {x}")
        return 1
    print("结果：齐了（退出码 0）。接着跑 `python tools/check_pilot_ready.py` 过门禁。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
