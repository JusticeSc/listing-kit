#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""P1.1 验收：ProductFacts 契约（正向 + 反向 + 只读 + v2 语义未变）。

判据来自计划 Phase 1 任务卡 P1.1 那一行：
    固定正常/缺失/未知/单位冲突/来源冲突样本；同一事实不同字段顺序哈希相同；
    冲突不能被"最后一个值"覆盖。报告 evals/product-v1/p1/p1.1-contract.txt
    回退：只做加法，不改 v2 planner 输入语义。

八条：
    A 正常样本      examples/product_fullset.json → 5 条闭集事实 + 卖点 + 标题，单位归一
    B 缺失          闭集里声明了、输入里没有 → state=missing（不是"这条不存在"）
    C 未知          单位读不出来 → state=unknown，raw 保留（不许瞎猜）
    D 单位等价      500ml 与 0.5L 归一到同一个 (500.0, ml) → **不算冲突**
    E 值冲突        500ml 与 600ml → conflicted 且 value=None，两条原始记录都在
    F 来源冲突      两份来源给出不同值 → 两条 source 都在 conflicts 里，且不是"最后一个值"
    G 哈希与顺序    specs 键顺序颠倒 → 同一个 facts_hash；且 product 未被修改（只读）
    H v2 语义未变   适配器跑前跑后，v2 的 assets.collect 结果完全一致；
                    卖点命中 brand.forbidden_words → allowed_on_image=no

退出码：0 全过 / 1 有条目不过。
"""
from __future__ import annotations

import copy
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402
enable_utf8()
import assets                     # noqa: E402   （只为验"v2 语义没被动过"）
import product_facts as pf        # noqa: E402

REPORT = ROOT / "evals" / "product-v1" / "p1" / "p1.1-contract.txt"
FULLSET = ROOT / "examples" / "product_fullset.json"
BRAND = ROOT / "config" / "brand.json"

SUPPLIER = "supplier/quote-2026-09.txt"


def supplier_product(raw_capacity: str) -> dict:
    """固定样本：只带一条容量的"供应商表"，用来造单位等价 / 值冲突 / 来源冲突。"""
    return {"upc": "B0FULLSET01", "title": "同款保温杯", "bullets": [],
            "specs": {"容量": raw_capacity}}


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

    forbid_words, forbidden_on_image = pf.load_forbidden(BRAND)
    product = pf.load_product(FULLSET)
    before_assets = assets.collect(product, ROOT / "examples")

    emit("P1.1 验收：ProductFacts 契约")
    emit("=" * 72)
    emit(f"时间：{datetime.now().astimezone().isoformat(timespec='seconds')}")
    emit("本次切片的七项声明（计划 §7.1）：")
    emit("  用户可见行为  无（这一层还不接管线；只是把事实变成带来源的契约对象）")
    emit("  不变量        A 主体只有一份 / B 生成层看不见主体 / C 文字层不画字 / D 位置 1 零模型 全部未触碰")
    emit("  允许改的模块  contracts/ 与 src/product_facts.py 新增；examples/ 只读")
    emit("  新增身份      facts_version = pfv1-<facts_hash 前 12 位>；facts_hash = 规范化 SHA-256")
    emit("  拒绝路径      confirmer 非空由校验拦下；conflicted 事实 value=null，下游只能拒")
    emit("  判据          本文件 A–H；反向样本见 B/C/E/F")
    emit("  迁移与回退    纯加法：v2 planner 的输入语义与资产路径未改（H 条为运行时证据）")
    emit("")

    emit("A 正常样本（examples/product_fullset.json）")
    bundle = pf.facts_from_product(
        product, source_path="examples/product_fullset.json",
        forbidden_words=forbid_words, forbidden_on_image=forbidden_on_image)
    by_id = {f["id"]: f for f in bundle["facts"]}
    check(not pf.validate_bundle(bundle), "结构校验通过", f"facts={len(bundle['facts'])} 条")
    check((by_id["spec.capacity"]["value"], by_id["spec.capacity"]["unit"]) == (500.0, "ml"),
          "容量归一到 (500.0, ml)", f"raw={by_id['spec.capacity']['raw']!r}")
    check((by_id["spec.weight"]["value"], by_id["spec.weight"]["unit"]) == (320.0, "g"),
          "重量归一到 (320.0, g)")
    check((by_id["spec.height"]["value"], by_id["spec.height"]["unit"]) == (22.0, "cm"),
          "高度归一到 (22.0, cm)", f"raw={by_id['spec.height']['raw']!r}")
    check(by_id["spec.material"]["kind"] == "text" and by_id["spec.material"]["unit"] is None,
          "材质是 text 且 unit=null")
    check(all(f["confirmer"] is None and f["state"] == "unconfirmed"
              for f in bundle["facts"] if f["state"] == "unconfirmed"),
          "confirmer 全部为 null（attest 没有被当成事实确认）")
    check(len([f for f in bundle["facts"] if f["kind"] == "claim"]) == 7,
          "标题 + 6 条卖点 = 7 条 claim",
          f"version={bundle['facts_version']}")
    emit("")

    emit("B 缺失样本（闭集里声明了、输入里没有）")
    miss = pf.facts_from_product({"upc": "T-MISS", "title": "缺规格的杯子", "bullets": ["普通卖点"],
                                  "specs": {"容量": "500ml", "材质": "316不锈钢"}},
                                 source_path="samples/missing.json")
    m_by_id = {f["id"]: f for f in miss["facts"]}
    check([f["id"] for f in miss["facts"] if f["state"] == "missing"]
          == ["spec.height", "spec.weight", "spec.width"],
          "重量/高度/宽度三条是 missing", f"缺 {[f['id'] for f in miss['facts'] if f['state']=='missing']}")
    check(m_by_id["spec.weight"]["value"] is None and m_by_id["spec.weight"]["state"] == "missing",
          "missing 事实 value=None（不是凭空补 0，也不是这条不存在）")
    check(not pf.validate_bundle(miss), "结构校验通过")
    emit("")

    emit("C 未知样本（读不出来的值不许瞎猜）")
    unk = pf.facts_from_product({"upc": "T-UNK", "title": "半升的杯子", "bullets": [],
                                 "specs": {"容量": "半升"}},
                                source_path="samples/unknown.json")
    u_cap = [f for f in unk["facts"] if f["id"] == "spec.capacity"][0]
    check(u_cap["state"] == "unknown" and u_cap["value"] is None and u_cap["raw"] == "半升",
          "容量=半升 → state=unknown，raw 保留原串")
    check(not pf.validate_bundle(unk), "结构校验通过")
    emit("")

    emit("D 单位等价（500ml 与 0.5L 归一后是同一个值 → 不算冲突）")
    eq = pf.merge_bundles(bundle, pf.facts_from_product(
        supplier_product("0.5L"), source_path=SUPPLIER))
    e_cap = [f for f in eq["facts"] if f["id"] == "spec.capacity"][0]
    check(e_cap["state"] != "conflicted" and (e_cap["value"], e_cap["unit"]) == (500.0, "ml"),
          "合并后仍是 (500.0, ml) 且不 conflict",
          f"sources_all={len(e_cap.get('sources_all') or [])} 个来源")
    check(e_cap.get("sources_all") == ["examples/product_fullset.json#specs.容量", SUPPLIER + "#specs.容量"],
          "两个来源都留在 sources_all 里")
    emit("")

    emit("E 值冲突（归一后仍不同 → conflicted，值必须置空）")
    vc = pf.merge_bundles(bundle, pf.facts_from_product(
        supplier_product("600ml"), source_path=SUPPLIER))
    v_cap = [f for f in vc["facts"] if f["id"] == "spec.capacity"][0]
    check(v_cap["state"] == "conflicted" and v_cap["value"] is None,
          "冲突事实 value=None（没有被 600 或 500 挑一个）")
    check(sorted((c["value"], c["unit"]) for c in v_cap["conflicts"]) == [(500.0, "ml"), (600.0, "ml")],
          "两条原始值都在 conflicts 里")
    check(not pf.validate_bundle(vc), "结构校验通过")
    emit("")

    emit("F 来源冲突（不同来源给不同值 —— 上游说 480，本地说 500）")
    sc = pf.merge_bundles(bundle, pf.facts_from_product(
        supplier_product("480ml"), source_path=SUPPLIER))
    s_cap = [f for f in sc["facts"] if f["id"] == "spec.capacity"][0]
    check(s_cap["state"] == "conflicted", "state=conflicted")
    check([c["source"] for c in s_cap["conflicts"]]
          == ["examples/product_fullset.json#specs.容量", SUPPLIER + "#specs.容量"],
          "两条来源都记下来了", f"conflicts={len(s_cap['conflicts'])} 条")
    check(s_cap["value"] is None, "没有被最后一个值（480）覆盖")
    emit("")

    emit("G 哈希与字段顺序无关，且适配器是只读的")
    reordered = {"bullets": list(product["bullets"]), "specs": dict(reversed(list(product["specs"].items()))),
                 "attest": product["attest"], "title": product["title"], "upc": product["upc"],
                 "assets": product["assets"]}
    frozen = copy.deepcopy(product)
    again = pf.facts_from_product(reordered, source_path="examples/product_fullset.json",
                                  forbidden_words=forbid_words, forbidden_on_image=forbidden_on_image)
    check(again["facts_hash"] == bundle["facts_hash"],
          "specs 键顺序颠倒 → 同一个 facts_hash", f"{bundle['facts_hash'][:16]}…")
    check(frozen == product, "适配器没有修改传入的 product（deepcopy 前后相等）")
    check(pf.facts_hash(list(reversed(bundle["facts"]))) == bundle["facts_hash"],
          "facts 列表顺序颠倒 → 同一个 facts_hash")
    emit("")

    emit("H v2 语义未变 + 卖点合规")
    after_assets = assets.collect(product, ROOT / "examples")
    check(before_assets == after_assets, "v2 的 assets.collect 结果前后完全一致")
    b6 = by_id["claim.bullet_6"]
    hits = {h["word"] for h in b6.get("forbidden_hits") or []}
    check(b6["allowed_on_image"] == "no" and {"全网最低", "绝对", "最好"} <= hits,
          "第 6 条卖点被判为不可上图", f"命中 {sorted(hits)}")
    check(by_id["claim.bullet_1"]["allowed_on_image"] == "unjudged",
          "普通卖点不预设结论（unjudged，等人确认）")
    emit("")

    emit("=" * 72)
    emit(f"结论：{'全部通过' if not fails else str(len(fails)) + ' 条不过'}"
         + ("" if not fails else "；不过的是：" + "、".join(fails)))
    emit("边界：本报告只证明 ProductFacts 契约本身（结构、归一、冲突、只读）；")
    emit("      不证明 20 个 SKU 的事实正确、不证明人工确认已经发生、不证明图片可用。")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    global_report = "\n".join(lines) + "\n"
    REPORT.write_text(global_report, encoding="utf-8")
    print(f"\n报告：{REPORT}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())