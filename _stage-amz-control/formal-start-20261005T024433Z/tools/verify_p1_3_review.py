#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""P1.3 验收：人工事实清单（清单可重复生成 + 不接受这道门）。

判据来自计划 Phase 1 任务卡 P1.3 那一行：
    同一候选 + FactsVersion 可重复生成同一清单；任一关键项 fail/unknown 时
    ACCEPTED 转换被拒；审美高分不能抵消事实失败。
    分栏：关键事实 / 平台硬违规 / 审美偏好；每项定义 pass/fail/unknown/not-applicable
    和所需证据。

八条：
    A 基线            契约合法；指向的规则/签字项/配置键都真实存在；同一输入生成同一清单
    B 分栏与覆盖      三栏后果不同（前两栏阻断、审美栏不阻断）；计划 §3.1 的每一条都有清单项
    C 关键项 fail     不接受，且指名是哪一条（不是一句"没过"）
    D 未判 / unknown  没判完不接受；判成 unknown 同样不接受（"没看"不等于"过了"）
    E 审美不抵消      所有审美项 pass + 一条关键 fail → 仍然不接受
    F 审美不阻断      关键项全 pass + 审美项全 fail → 可以接受（偏好只被记下来）
    G 同一输入同一清单 同候选+同 FactsVersion 重复生成 instance_id 相同；换候选/换事实版本就不同；
                       同一项结论不许覆盖；状态哈希随结论变
    H 证据与边界      fail/unknown 必须写依据；不许 NA 的关键项标 NA 被拦；
                       打错规则名被拦；已知规则漏配清单项被拦（反向样本注入真文件）

退出码：0 全过 / 1 有条目不过。
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402
enable_utf8()
import intake                     # noqa: E402  （签字项是清单要指向的权威之一）
import review_contract as rc      # noqa: E402
import validators                 # noqa: E402  （规则名是清单要指向的权威之一）

REPORT = ROOT / "evals" / "product-v1" / "p1" / "p1.3-review.txt"
PLAN = ROOT / "docs" / "product-v1-goal-and-implementation-plan.md"
TMP = ROOT / "evals" / ".tmp" / "p1.3"
CAND = "out/B0FULLSET01_20260923-125218-258886/slot4/cand-1.png"
FACTS = "pfv1-f9e80514a2c9"


def plan_critical_bullets() -> list[str]:
    """计划 §3.1 的条目是这份清单的覆盖对象：计划加了类别，清单必须跟。"""
    text = PLAN.read_text(encoding="utf-8")
    m = re.search(r"### 3\.1 关键商品事实错误\n(.*?)\n### ", text, re.S)
    assert m, "找不到计划 §3.1"
    return [ln for ln in m.group(1).splitlines() if ln.startswith("- ")]


def fill(checklist: dict, outcome: str = "pass", skip: tuple[str, ...] = (),
         note: str = "对照权威资料与候选图逐项核对",
         only_blocking: bool = False) -> dict:
    for item in list(checklist["items"]):
        if item["id"] in skip:
            continue
        if only_blocking and not checklist["sections"][item["section"]]["blocks_accept"]:
            continue
        checklist = rc.record_outcome(checklist, item["id"], outcome, by="运营 A", note=note)
    return checklist


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
        except Exception as exc:                                   # noqa: BLE001
            ok = must_contain in str(exc)
            check(ok, label, f"报错含『{must_contain}』" if ok else
                  f"报错了但没提『{must_contain}』：{str(exc).splitlines()[0]}")
        else:
            check(False, label, "居然通过了 —— 这一条本该被拦下")

    contract = rc.load_checklist()

    emit("P1.3 验收：人工事实清单")
    emit("=" * 72)
    emit("本次切片的七项声明（计划 §7.1）：")
    emit("  用户可见行为  无（这一层还不接界面；只把清单与接受判据变成可执行对象）")
    emit("  不变量        A 主体只有一份 / B 生成层看不见主体 / C 文字层不画字 / D 位置 1 零模型 全部未触碰")
    emit("  允许改的模块  contracts/review-checklist-v1.yaml 与 src/review_contract.py 新增；config/ 与 examples/ 只读")
    emit("  新增身份      checklist_version=rcv1-<契约内容哈希>；instance_id=rvi1-<候选×事实版本×契约>；state_hash=rvh1-<结论状态>")
    emit("  拒绝路径      关键项 fail / unknown / 未判 → 不接受；不许 NA 的项标 NA → 拒绝；结论写第二次 → 拒绝")
    emit("  判据          本文件 A–H；反向样本见 C/D/E/H；正向对照见 A/F/G")
    emit("  迁移与回退    纯加法：只读契约与纯函数；v2 的 E0 体检与 validators 未改（B/H 条为交叉证据）")
    emit("")

    # ---------------------------------------------------------------- A
    emit("A 基线（契约合法、指向真实权威、可重复生成）")
    check(True, "结构校验通过（不合法会直接抛）",
          f"分栏 {len(contract['sections'])} 个 · 清单项 {len(contract['items'])} 条")
    refs = rc.check_references(contract, known_rules=validators.KNOWN_RULES,
                               attest_items=set(intake.ATTEST_ITEMS)
                               | {intake.FONT_ATTEST_ITEM, intake.COMPETITOR_ATTEST_ITEM},
                               brand_config={"forbidden_words", "forbidden_on_image",
                                             "brand", "fonts", "notes"})
    check(refs == [], "指向的规则名 / 签字项 / 配置键都真实存在，且已实现的规则没有漏配",
          f"KNOWN_RULES {len(validators.KNOWN_RULES)} 条全部有落项或排除理由")
    args = dict(task_id="T-DEMO", slot_id="4", candidate_ref=CAND, facts_version=FACTS)
    c1 = rc.build_checklist(contract, **args)
    c2 = rc.build_checklist(contract, **args)
    check(rc.checklist_version(contract) == rc.checklist_version(contract)
          and c1 == c2 and c1["instance_id"] == c2["instance_id"],
          "同一候选 + 同一 FactsVersion → 逐字节相同的清单", f"instance_id={c1['instance_id']}")
    check(c1["schema"] == "review-checklist-instance/v1" and c1["revision"] == 0
          and all(i["outcome"] is None for i in c1["items"]),
          "新清单的每一项都是未判（不会默认 pass）")
    emit("")

    # ---------------------------------------------------------------- B
    emit("B 分栏与覆盖（计划 §3.1 的每一条都要有人管）")
    sec = c1["sections"]
    check(sec["critical_fact"]["blocks_accept"] is True
          and sec["platform_hard_rule"]["blocks_accept"] is True
          and sec["aesthetic"]["blocks_accept"] is False,
          "前两栏阻断接受、审美栏不阻断（后果写在契约里，不靠读的人猜）",
          f"{ {k: v['blocks_accept'] for k, v in sec.items()} }")
    per_section = {n: len([i for i in c1["items"] if i["section"] == n]) for n in sec}
    check(all(per_section[n] > 0 for n in sec), "三栏都不是空的", f"条目数 {per_section}")
    bullets = plan_critical_bullets()
    want = {f"§3.1-{i}" for i in range(1, len(bullets) + 1)}
    covered: dict[str, set[str]] = {}
    for i in c1["items"]:
        for r in i["plan_refs"]:
            covered.setdefault(r, set()).add(i["section"])
    check(want <= set(covered), "计划 §3.1 的每一条都有清单项挂上",
          f"§3.1 共 {len(bullets)} 条，清单覆盖 {len(want & set(covered))} 条")
    check(covered.get("§3.1-6") == {"platform_hard_rule"},
          "§3.1 第 6 条（平台禁止的主图元素）落在平台栏，不是混在关键事实里",
          f"实际落在 {sorted(covered.get('§3.1-6') or [])}")
    emit("")

    # ---------------------------------------------------------------- C
    emit("C 关键项 fail → 不接受")
    bad = rc.record_outcome(rc.build_checklist(contract, **args), "cf.appearance", "fail",
                            by="运营 A", note="图上杯身印的是旧 logo，权威资料里已经换了")
    bad = fill(bad, "pass", skip=("cf.appearance",))
    v_c = rc.evaluate(bad)
    check(v_c["can_accept"] is False and v_c["blockers"] == ["cf.appearance"],
          "不接受，并指名是哪一条", f"reason={v_c['reason']} blockers={v_c['blockers']}")
    expect_error(lambda: rc.require_accepted(v_c), "不接受", "接受入口会抛，而不是返回一个布尔值")

    # ---------------------------------------------------------------- D
    emit("D 未判 / unknown → 同样不接受")
    v_none = rc.evaluate(rc.build_checklist(contract, **args))
    check(v_none["can_accept"] is False and v_none["reason"] == "checklist_incomplete",
          "一条都没判：不接受", f"pending={len(v_none['pending'])} 条")
    unk = rc.record_outcome(rc.build_checklist(contract, **args), "cf.claim_truth", "unknown",
                            by="运营 A", note="图上那句'长效保温'找不到对应事实，也看不出是编的")
    unk = fill(unk, "pass", skip=("cf.claim_truth",))
    v_u = rc.evaluate(unk)
    check(v_u["can_accept"] is False and v_u["blockers"] == ["cf.claim_truth"],
          "判成 unknown 也不接受（'没看'不等于'过了'）", f"reason={v_u['reason']}")
    emit("")

    # ---------------------------------------------------------------- E
    emit("E 审美满分不能抵消事实失败")
    combo = rc.build_checklist(contract, **args)
    combo = rc.record_outcome(combo, "cf.composition", "fail", by="运营 A",
                              note="模型在杯旁边加了一个不存在的杯盖")
    combo = fill(combo, "pass", skip=("cf.composition",))
    v_e = rc.evaluate(combo)
    check(v_e["aesthetic"].get("pass") == 3 and v_e["can_accept"] is False,
          "三条审美全 pass，仍然不接受", f"aesthetic={v_e['aesthetic']} blockers={v_e['blockers']}")
    emit("")

    # ---------------------------------------------------------------- F
    emit("F 审美不过也不阻断接受")
    pretty_bad = fill(rc.build_checklist(contract, **args), "pass", only_blocking=True)
    pretty_bad = rc.record_outcome(pretty_bad, "ae.composition", "fail", by="运营 A",
                                   note="主体太靠边，构图一般；事实没问题")
    pretty_bad = rc.record_outcome(pretty_bad, "ae.lighting", "unknown", by="运营 A",
                                   note="光影说不上好坏，先记着")
    v_f = rc.evaluate(pretty_bad)
    check(v_f["can_accept"] is True and v_f["reason"] == "ready_for_acceptance",
          "关键项全 pass + 审美项不过 → 可以接受", f"reason={v_f['reason']}")
    check(v_f["aesthetic"]["fail"] == 1 and v_f["aesthetic"]["unknown"] == 1
          and v_f["aesthetic_blocks_accept"] is False,
          "审美结论被记下来，但不参与能不能接受", f"aesthetic={v_f['aesthetic']}")
    emit("")

    # ---------------------------------------------------------------- G
    emit("G 同一输入同一清单；结论不许覆盖")
    other = rc.build_checklist(contract, task_id="T-DEMO", slot_id="4",
                               candidate_ref="out/.../cand-2.png", facts_version=FACTS)
    other_facts = rc.build_checklist(contract, task_id="T-DEMO", slot_id="4",
                                    candidate_ref=CAND, facts_version="pfv1-000000000000")
    check(len({c1["instance_id"], other["instance_id"], other_facts["instance_id"]}) == 3,
          "换候选、换 FactsVersion → 清单身份随之改变",
          f"{c1['instance_id']} / {other['instance_id']} / {other_facts['instance_id']}")
    once = rc.record_outcome(c1, "cf.structure", "pass", by="运营 A")
    check(once["revision"] == 1 and len(once["events"]) == 1
          and once["state_hash"] != c1["state_hash"],
          "记一条结论 → 修订号 +1、事件 +1、状态哈希改变",
          f"{c1['state_hash']} → {once['state_hash']}")
    check(c1["items"][0]["outcome"] is None, "原来的清单对象没有被改（record_outcome 是纯函数）")
    expect_error(lambda: rc.record_outcome(once, "cf.structure", "fail", by="运营 B",
                                           note="想翻案"),
                 "已经写过", "同一项写第二次 → 拒绝（不许把旧结论擦掉）")
    emit("")

    # ---------------------------------------------------------------- H
    emit("H 证据与边界（这几条都是『静默少判』的典型入口）")
    expect_error(lambda: rc.record_outcome(rc.build_checklist(contract, **args), "cf.structure",
                                           "fail", by="运营 A"),
                 "依据", "fail 不写依据 → 拒绝")
    expect_error(lambda: rc.record_outcome(rc.build_checklist(contract, **args), "cf.quantity",
                                           "unknown", by="运营 A"),
                 "依据", "unknown 不写依据 → 拒绝")
    expect_error(lambda: rc.record_outcome(rc.build_checklist(contract, **args), "cf.structure",
                                           "not_applicable", by="运营 A"),
                 "不允许", "不许 NA 的关键项标 NA → 拒绝（最难的那题不许自己消失）")
    na_ok = rc.record_outcome(rc.build_checklist(contract, **args), "pr.competitor_clean",
                              "not_applicable", by="运营 A")
    v_na = rc.evaluate(fill(na_ok, "pass", skip=("pr.competitor_clean",)))
    check(v_na["can_accept"] is True,
          "条件项（位置 7 没出图时的竞品图签字）标 NA 是可以的", "NA 不阻断")
    expect_error(lambda: rc.build_checklist(contract, **args,
                                           applicable={"rules": {"whilte_bg_purity"}}),
                 "不认识", "applicable 里打错规则名 → 拒绝（错一个字 = 少判一项）")
    TMP.mkdir(parents=True, exist_ok=True)
    real = rc.DEFAULT_PATH.read_text(encoding="utf-8")
    d1 = TMP / "d1-drop-rule.yaml"
    d1.write_text(real.replace("    rule_ref: aspect_ratio\n", ""), encoding="utf-8", newline="")
    expect_error(lambda: rc.load_checklist(d1), "aspect_ratio",
                 "已实现的规则从清单里被删掉（且没写排除理由）→ 报错")
    d2 = TMP / "d2-fake-rule.yaml"
    d2.write_text(real.replace("    rule_ref: edge_clean\n", "    rule_ref: not_a_real_rule\n"),
                  encoding="utf-8", newline="")
    expect_error(lambda: rc.load_checklist(d2), "KNOWN_RULES",
                 "指向一个根本不存在的规则名 → 报错（'声明了但静默跳过'那一类）")
    d3 = TMP / "d3-no-exclusion-reason.yaml"
    d3.write_text(real.replace("  file_size: 交付包体积上限，归导出阶段\n", "  file_size: ''\n"),
                  encoding="utf-8", newline="")
    expect_error(lambda: rc.load_checklist(d3), "理由",
                 "排除项不写理由 → 报错（有理由的排除不是漏项）")
    emit("")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    emit("=" * 72)
    if fails:
        emit(f"结论：{len(fails)} 条不过 —— {'；'.join(fails)}")
    else:
        emit("结论：全部通过")
    emit("边界：本报告只证明清单可重复生成、接受判据按分栏生效、指向的权威真实存在；")
    emit("      不证明运营真的会逐项判、不证明界面已经接上（Phase 3/6），也不证明图片可用。")
    emit("")
    emit(f"报告：{REPORT}")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
