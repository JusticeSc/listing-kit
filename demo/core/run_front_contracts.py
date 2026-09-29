#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""D1.P2 —— 前半链契约测试（PC-01 – PC-07），离线、零付费调用。

它回答一个问题：§4.4 的前半链合同，**是不是真的能被实现、也真的能被违反**。

方法：一条黄金链走通全部七条合同，再逐向注入一种缺陷，要求实现只报该报的结果。
每条反例都必须让被验对象真的变坏（沙箱里改副本，真实素材一个字节不动）。

判据不可证伪 = 装饰。所以这里同时测两件事：
  * 该拒绝的必须拒绝（缺素材、事实冲突、无依据卖点、风格越界、删锁、重复提交、Unknown）；
  * 该通过的必须通过（黄金链、结构化编辑、无文案时的恒等路径）。

用法：
    python demo/core/run_front_contracts.py            # 全跑，写报告
    python demo/core/run_front_contracts.py --json     # 机器读

退出码：
    0  全部符合预期
    1  有反例没被抓住（实现或判据有问题）
    2  契约口径本身不成立（例如试图产出合同不允许的状态）
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demo.core import contracts as C      # noqa: E402
from demo.core import front_chain as FC   # noqa: E402
from demo.core import packages as PKG     # noqa: E402
from demo.core import prompt as P         # noqa: E402

OUT = ROOT / "evals/product-demo/d1-p2/front-contracts.json"


def record_path(project=ROOT) -> Path:
    """D1.4 冻结记录的位置来自商品包声明的候选目录，不是这里另写一份常量。"""
    return PKG.runs_of(project)["manifest"]


class Harness:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.sandboxes: list[Path] = []
        self.tmp: list[Path] = []

    def sandbox(self) -> Path:
        dest = FC.sandbox_project(ROOT)
        self.sandboxes.append(dest)
        return dest

    def workdir(self, prefix: str) -> Path:
        d = Path(tempfile.mkdtemp(prefix=prefix))
        self.tmp.append(d)
        return d

    def case(self, code: str, name: str, expect: str, result, checks: list[str]) -> None:
        ok = (result.outcome == expect) and not checks
        self.rows.append({
            "case": code, "name": name, "contract": result.contract_id,
            "expect": expect, "actual": result.outcome, "ok": ok,
            "notes": list(result.notes), "failed_checks": checks,
        })

    def cleanup(self) -> None:
        for d in self.sandboxes + self.tmp:
            shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------- 公共前置
def golden_up_to_prompt(h: Harness, *, project=ROOT, goal=None, confirmed_by="demo-user"):
    r1 = FC.intake(project)
    if not r1.accepted:
        return r1, None, None, None, None
    r2 = FC.facts(project, refpack=r1.payload)
    if not r2.accepted:
        return r1, r2, None, None, None
    r3 = FC.propose_plan(r2.payload, r1.payload, FC.platform_rules(project),
                         goal=goal, confirmed_by=confirmed_by)
    if not r3.accepted:
        return r1, r2, r3, None, None
    r4 = FC.style_spec(r3.payload, r2.payload)
    if not r4.accepted:
        return r1, r2, r3, r4, None
    r5 = FC.compile_prompt(r3.payload, r2.payload, r4.payload, "S2")
    return r1, r2, r3, r4, r5


def card_of(project: Path) -> tuple[Path, dict]:
    path = PKG.path_of(project, "card")
    return path, json.loads(path.read_text(encoding="utf-8"))


def write_card(path: Path, card: dict) -> None:
    path.write_text(json.dumps(card, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- 反例
def _manifest_of(d: Path) -> dict:
    return json.loads(FC.refpack_of(d)["manifest"].read_text(encoding="utf-8"))


def case_r1_missing_view(h: Harness) -> None:
    d = h.sandbox()
    FC.pack_tools._drop_view(d)
    man = _manifest_of(d)
    gone = not (d / man["views"][0]["file"]).exists()
    r = FC.intake(d)
    h.case("R1", "素材缺一个视图文件", "business_reject", r,
           [] if gone else ["沙箱里的视图文件其实没被删掉（探针失效）"])


def case_r2_hash_drift(h: Harness) -> None:
    d = h.sandbox()
    FC.pack_tools._append_byte(d)
    man = _manifest_of(d)
    view = man["views"][1]
    drifted = FC.sha256_file(d / view["file"]) != view["sha256"]
    r = FC.intake(d)
    h.case("R2", "素材哈希漂移（PNG 尾部多一个字节）", "business_reject", r,
           [] if drifted else ["沙箱里的文件哈希其实没变（探针失效）"])


def case_r3_machine_on_unknown_field(h: Harness) -> None:
    d = h.sandbox()
    path, card = card_of(d)
    card["facts"].append({"id": "F9", "claim": "容量 500 毫升",
                          "modality": "machine",
                          "machine_checks": [{"metric": "capacity", "pass": {"min": 0, "max": 9999}}]})
    write_card(path, card)
    _, back = card_of(d)
    injected = any(f["id"] == "F9" and f.get("modality") == "machine" for f in back["facts"])
    r = FC.facts(d)
    h.case("R3", "用机器模态断言未确认字段（容量）", "business_reject", r,
           [] if injected else ["沙箱事实卡其实没被改到（探针失效）"])


def case_r4_unsupported_fact(h: Harness) -> None:
    d = h.sandbox()
    path, card = card_of(d)
    card["facts"].append({"id": "F9", "claim": "杯盖手感很好", "modality": "mixed"})
    write_card(path, card)
    _, back = card_of(d)
    injected = any(f["id"] == "F9" and not f.get("machine_checks")
                   and not (f.get("human_note") or "").strip() for f in back["facts"])
    r = FC.facts(d)
    h.case("R4", "既无机器判据也无人确认的断言", "business_reject", r,
           [] if injected else ["沙箱事实卡其实没被改到（探针失效）"])


def case_r5_unknowns_dropped(h: Harness) -> None:
    d = h.sandbox()
    path, card = card_of(d)
    card["unknowns"] = []
    write_card(path, card)
    _, back = card_of(d)
    r = FC.facts(d)
    h.case("R5", "事实卡丢掉全部 Unknown 登记", "business_reject", r,
           [] if not (back.get("unknowns") or []) else ["Unknown 其实没被清空（探针失效）"])


def case_r6_unsupported_claim(h: Harness) -> None:
    r1 = FC.intake()
    r2 = FC.facts(refpack=r1.payload)
    goal = {"text": "验证无依据卖点", "claims": [{"text": "容量 500 毫升大容量", "facts": []}]}
    r = FC.propose_plan(r2.payload, r1.payload, FC.platform_rules(), goal=goal,
                        confirmed_by="demo-user")
    h.case("R6", "计划里出现无事实来源的卖点", "business_reject", r, [])


def case_r7_unconfirmed_plan(h: Harness) -> None:
    r1 = FC.intake()
    r2 = FC.facts(refpack=r1.payload)
    r = FC.propose_plan(r2.payload, r1.payload, FC.platform_rules(), confirmed_by=None)
    h.case("R7", "计划未经用户确认就要往下走", "business_reject", r, [])


def case_r8_style_touches_fact_lock(h: Harness) -> None:
    _, r2, r3, _, _ = golden_up_to_prompt(h)
    r = FC.style_spec(r3.payload, r2.payload, preferences={"body_finish": "glossy"})
    h.case("R8", "风格变量试图改杯体表面（事实锁）", "business_reject", r, [])


def case_r9_structured_edit(h: Harness) -> None:
    *_, r5 = golden_up_to_prompt(h)
    base = r5.payload
    r = FC.edit_prompt(base, append="no umbrella, no bag and no box anywhere in the frame")
    checks = []
    if r.accepted:
        child = r.payload
        if child.get("parent_version") != base["version_id"]:
            checks.append("新版本没有记录父版本")
        if not child.get("diff", {}).get("added"):
            checks.append("没有记录差异")
        if child["prompt_text"] == base["prompt_text"]:
            checks.append("编辑后文本没变")
        if base["prompt_sha256"] != r5.payload["prompt_sha256"]:
            checks.append("原版本被就地改写了")
    h.case("R9", "结构化编辑（只追加允许方向）", "accepted", r, checks)


def case_r10_delete_lock_block(h: Harness) -> None:
    *_, r5 = golden_up_to_prompt(h)
    version = r5.payload
    blank = next(b for b in version["blocks"] if b["block"] == "BLANK SURFACE")
    hacked = version["prompt_text"].replace(blank["text"], "")
    really_hacked = blank["text"] not in hacked
    r = FC.edit_prompt(version, raw_text=hacked)
    h.case("R10", "原始文本编辑删掉 F8 锁定段", "business_reject", r,
           [] if really_hacked else ["编辑后的文本其实还留着锁段（探针失效）"])


def _submit_setup(h: Harness, transport, *, budget_limit=None, shot_extra=None):
    r1, r2, r3, r4, r5 = golden_up_to_prompt(h)
    shot = dict(next(s for s in r3.payload["shots"] if s["shot_id"] == "S2"))
    shot.update(shot_extra or {})
    refs = FC.resolve_references(ROOT, r1.payload, shot["reference_views"])
    work = h.workdir("d1p2-submit-")
    return r5.payload, refs, shot, work, budget_limit


def case_r11_duplicate_submit(h: Harness) -> None:
    transport = FC.I2I.FakeTransport()
    version, refs, shot, work, budget = _submit_setup(h, transport)
    first = FC.submit(prompt_version=version, reference_paths=refs,
                      store_dir=work / "attempts", ledger_path=work / "ledger.jsonl",
                      seed=2026092601, shot=shot, transport=transport)
    second = FC.submit(prompt_version=version, reference_paths=refs,
                       store_dir=work / "attempts", ledger_path=work / "ledger.jsonl",
                       seed=2026092601, shot=shot, transport=transport)
    checks = []
    if not first.accepted:
        checks.append(f"第一次提交没有成功：{first.outcome}")
    if transport.post_calls != 1:
        checks.append(f"同一 action 被提交了 {transport.post_calls} 次")
    h.case("R11", "同一请求重复提交", "business_reject", second, checks)


def case_r12_unknown_not_resent(h: Harness) -> None:
    transport = FC.I2I.FakeTransport(task_status="RUNNING")
    version, refs, shot, work, budget = _submit_setup(h, transport, shot_extra={"poll_timeout_s": 1})
    first = FC.submit(prompt_version=version, reference_paths=refs,
                      store_dir=work / "attempts", ledger_path=work / "ledger.jsonl",
                      seed=2026092602, shot=shot, transport=transport)
    posts_after_first = transport.post_calls
    second = FC.submit(prompt_version=version, reference_paths=refs,
                       store_dir=work / "attempts", ledger_path=work / "ledger.jsonl",
                       seed=2026092602, shot=shot, transport=transport)
    third = FC.reconcile(store=work / "attempts", action_id=first.payload.get("action_id"))
    checks = []
    if first.outcome != "unknown":
        checks.append(f"超时没有进 Unknown，而是 {first.outcome}")
    if second.outcome != "unknown":
        checks.append(f"再次提交时没有先核对原任务，而是 {second.outcome}")
    if transport.post_calls != posts_after_first:
        checks.append("Unknown 之后又发了新请求")
    if third.outcome != "unknown":
        checks.append(f"核对原任务的结果是 {third.outcome}")
    h.case("R12", "轮询超时进 Unknown 且不重发", "unknown", second, checks)


def case_r13_reference_guard(h: Harness) -> None:
    r1, r2, r3, r4, r5 = golden_up_to_prompt(h)
    shot = next(s for s in r3.payload["shots"] if s["shot_id"] == "S2")
    refs = [FC.I2I.load_reference(p)
            for p in FC.resolve_references(ROOT, r1.payload, shot["reference_views"])]
    body = FC.I2I.build_request(mode=FC.I2I.MODE_I2I, prompt=r5.payload["prompt_text"],
                                references=refs, seed=1, size=FC.I2I.DEFAULT_SIZE)
    checks = []
    try:
        FC.I2I.assert_references_in_body(body, refs)          # 正常体必须通过
    except Exception as exc:
        checks.append(f"正常请求体就被守卫拒绝了：{exc}")

    def strip_images(node):
        if isinstance(node, dict):
            for k in list(node):
                if isinstance(node[k], str) and node[k].startswith("data:image"):
                    node.pop(k)
                else:
                    strip_images(node[k])
        elif isinstance(node, list):
            for v in node:
                strip_images(v)

    hacked = json.loads(json.dumps(body))
    strip_images(hacked)
    record = C.StepResult("PC-06", "accepted", payload={"guard": "reference"})
    try:
        FC.I2I.assert_references_in_body(hacked, refs)
        checks.append("去掉参考图后守卫仍然放行 —— 参考图是否真的进了请求就没有保障")
        record = C.StepResult("PC-06", "technical_fail", payload={"guard": "reference"})
    except FC.I2I.ProviderGuardError:
        record = C.StepResult("PC-06", "business_reject", payload={"guard": "reference"},
                              notes=["守卫在发请求前拒绝了不带参考图的请求体"])
    h.case("R13", "请求体里没有参考图时守卫拒绝", record.outcome, record, checks)


def case_r14_budget(h: Harness) -> None:
    transport = FC.I2I.FakeTransport()
    version, refs, shot, work, _ = _submit_setup(h, transport)
    r = FC.submit(prompt_version=version, reference_paths=refs,
                  store_dir=work / "attempts", ledger_path=work / "ledger.jsonl",
                  seed=2026092603, shot=shot, transport=transport, budget_limit=0)
    checks = []
    if transport.post_calls != 0:
        checks.append("预算不足却仍然发出了请求")
    h.case("R14", "超出硬预算时拒绝提交", "business_reject", r, checks)


def case_r15_reconcile(h: Harness) -> None:
    transport = FC.I2I.FakeTransport()
    version, refs, shot, work, _ = _submit_setup(h, transport)
    r = FC.submit(prompt_version=version, reference_paths=refs,
                  store_dir=work / "attempts", ledger_path=work / "ledger.jsonl",
                  seed=2026092604, shot=shot, transport=transport)
    rec = FC.reconcile(store=work / "attempts", action_id=r.payload["action_id"])
    checks = []
    if not rec.accepted:
        checks.append(f"成功动作核对结果不是 accepted：{rec.outcome}")
    elif rec.payload.get("file_sha256") != r.payload.get("image_sha256"):
        checks.append("核对得到的候选哈希与提交回执不一致")
    h.case("R15", "PC-07 用原 task 核对出候选", "accepted", rec, checks)


def case_r16_no_invented_state(h: Harness) -> None:
    checks = []
    try:
        C.StepResult("PC-03", "needs_human", notes=["用户需要确认"])
        checks.append("PC-03 声称自己可以返回 needs_human —— 契约里没这个结果")
    except C.ContractViolation:
        pass
    try:
        C.StepResult("PC-99", "accepted")
        checks.append("不存在的合同 ID 被接受了")
    except C.ContractViolation:
        pass
    probe = C.StepResult("PC-04", "needs_human", notes=["需要用户确认视觉方向"])
    h.case("R16", "实现不许自造合同没声明的状态", "needs_human", probe, checks)

def raw_case(h: Harness, code: str, name: str, expect: str, actual: str,
             checks: list[str], detail: dict | None = None) -> None:
    h.rows.append({"case": code, "name": name, "contract": "G0" if code == "G0" else "PC-chain",
                   "expect": expect, "actual": actual, "ok": (expect == actual) and not checks,
                   "notes": [], "failed_checks": checks, "detail": detail or {}})


def case_g0_golden(h: Harness) -> None:
    checks: list[str] = []
    detail: dict = {}

    r1, r2, r3, r4, r5 = golden_up_to_prompt(h)
    for step in (r1, r2, r3, r4, r5):
        if step is None or not step.accepted:
            checks.append(f"黄金链断在 {(step.contract_id, step.outcome) if step else 'None'}")
            raw_case(h, "G0", "黄金前半链（PC-01…PC-07）", "accepted", "failed", checks)
            return

    r3b = FC.propose_plan(r2.payload, r1.payload, FC.platform_rules(), confirmed_by="demo-user")
    if r3b.payload.get("plan_version") != r3.payload["plan_version"]:
        checks.append("同一输入两次提案得到了不同的 plan_version（计划不稳定）")
    detail["plan_version"] = r3.payload["plan_version"]

    r5b = FC.compile_prompt(r3.payload, r2.payload, r4.payload, "S2")
    if r5b.payload.get("prompt_sha256") != r5.payload["prompt_sha256"]:
        checks.append("同一输入两次编译得到了不同的提示词（编译不确定）")

    rec_path = record_path()
    recorded = None
    if rec_path.is_file():
        recorded = json.loads(rec_path.read_text(encoding="utf-8"))["prompt_version"]
        if r5.payload["prompt_text"] != recorded["prompt_text"]:
            checks.append("编译产物与 D1.4 真实发出的提示词不是逐字相同")
        if r5.payload["negative_prompt"] != recorded["negative_prompt"]:
            checks.append("negative_prompt 与已发请求不同")
        detail["prompt_sha256"] = r5.payload["prompt_sha256"]
        detail["prompt_sha256_matches_record"] = (
            r5.payload["prompt_sha256"] == recorded["prompt_sha256"])
    else:
        checks.append("找不到 D1.4 的冻结记录，无法核对提示词等价")

    shot = next(s for s in r3.payload["shots"] if s["shot_id"] == "S2")
    refs_paths = FC.resolve_references(ROOT, r1.payload, shot["reference_views"])
    transport = FC.I2I.FakeTransport()
    work = h.workdir("d1p2-golden-")
    r6 = FC.submit(prompt_version=r5.payload, reference_paths=refs_paths,
                   store_dir=work / "attempts", ledger_path=work / "ledger.jsonl",
                   seed=2026092601, shot=shot, transport=transport)
    if not r6.accepted:
        checks.append(f"PC-06 黄金提交失败：{r6.outcome}")
    else:
        if transport.post_calls != 1:
            checks.append(f"黄金链提交了 {transport.post_calls} 次")
        posted = transport.posted_bodies[0]
        try:                                            # 参考图真的进了请求体
            FC.I2I.assert_references_in_body(
                posted, [FC.I2I.load_reference(p) for p in refs_paths])
        except Exception as exc:
            checks.append(f"请求体里的参考图核对失败：{exc}")
        text_sent = r6.payload.get("prompt_sha256")
        if text_sent != r5.payload["prompt_sha256"]:
            checks.append("发出去的提示词与展示的 PromptVersion 不是同一份")
        if FC.sha256_file(work / "attempts" / r6.payload["action_id"] / "raw.png") \
                != r6.payload.get("image_sha256"):
            checks.append("落盘候选与回执哈希不一致")
        detail["action_id"] = r6.payload.get("action_id")
        detail["candidate_sha256"] = r6.payload.get("image_sha256")
        detail["input_image_count"] = r6.payload.get("input_image_count")
        if r6.payload.get("input_image_count") != 1:
            checks.append(f"服务端回执的 input_image_count={r6.payload.get('input_image_count')}，期望 1")

        r7 = FC.reconcile(store=work / "attempts", action_id=r6.payload["action_id"])
        if not r7.accepted:
            checks.append(f"PC-07 核对失败：{r7.outcome}")
        detail["candidate"] = r7.payload.get("candidate")

    # 落盘证据：候选与账本都在临时目录，只有哈希进报告
    raw_case(h, "G0", "黄金前半链（PC-01…PC-07）", "accepted",
             "accepted" if not checks else "failed", checks, detail)


def weak_guard_raw_edit(version, new_text, *, origin="weak"):
    """削弱版：只看文本变没变，不检查锁段还在不在。"""
    return {**version, "parent_version": version["version_id"],
            "prompt_text": new_text, "diff": {}, "origin": origin}


MUTATIONS: list[tuple[str, str, str, object, list[str]]] = [
    ("M1", "把 PC-02 的事实规则整段停掉", "FC.fact_problems",
     lambda card: ([], [u.get("field") for u in (card.get("unknowns") or [])]),
     ["R3", "R4", "R5"]),
    ("M2", "把 PC-03 的卖点规则停掉", "FC.claim_problems",
     lambda claims, ids, unknown: [], ["R6"]),
    ("M3", "把「编辑不许静默删锁」停掉", "FC.P.guard_raw_edit",
     weak_guard_raw_edit, ["R10"]),
    ("M4", "把参考图守卫停掉", "FC.I2I.assert_references_in_body",
     lambda body, refs: [], ["R13"]),
    ("M5", "把「同一 action 已有产出就不重发」停掉", "FC.I2I.AttemptStore.has_result",
     lambda self, aid: False, ["R11"]),
]


def _owner(dotted: str, namespace: dict):
    """把 "FC.P.guard_raw_edit" 解析成 (被替换的对象, 属性名)。

    从调用方的命名空间出发，而不是从 FC 出发 —— 第一版从 FC 出发去找 "FC"，
    于是 M1 直接炸在 AttributeError 上：变异测试自己也必须能跑起来。
    """
    parts = dotted.split(".")
    obj = namespace[parts[0]]
    for part in parts[1:-1]:
        obj = getattr(obj, part)
    return obj, parts[-1]


def mutation_test(verbose: bool = True) -> int:
    """把实现逐条削弱，要求对应的反例**必须变红**。

    没有这一步，「17/17 通过」只能说明用例和当前实现碰巧一致；
    有了这一步，才说明这些用例真的在保护实现里的某一条规则。
    """
    bad = 0
    rows = []
    for code, name, dotted, weakened, targets in MUTATIONS:
        owner, attr_name = _owner(dotted, globals())
        original = getattr(owner, attr_name)
        setattr(owner, attr_name, weakened)
        try:
            h = Harness()
            try:
                for case in CASES:
                    if case.__name__.split("_")[1].upper() in targets:
                        try:
                            case(h)
                        except Exception as exc:
                            raw_case(h, case.__name__, "（用例异常）", "-", "exception",
                                     [f"{type(exc).__name__}: {exc}"])
            finally:
                h.cleanup()
            got = {r["case"]: r["ok"] for r in h.rows}
            missed = [t for t in targets if got.get(t, True)]
            ok = not missed
            rows.append({"mutation": code, "name": name, "targets": targets,
                         "detected": ok, "missed": missed})
            if verbose:
                print(f"[{'OK  ' if ok else 'FAIL'}] {code} {name}　→　"
                      f"{'、'.join(targets)} {'全部变红' if ok else '仍有绿灯：' + '、'.join(missed)}")
            bad += 0 if ok else 1
        finally:
            setattr(owner, attr_name, original)
    if verbose:
        print(f"\n变异测试：{len(MUTATIONS) - bad}/{len(MUTATIONS)} 项被反例抓住")
    return 0 if bad == 0 else 1


CASES = [
    case_g0_golden,
    case_r1_missing_view,
    case_r2_hash_drift,
    case_r3_machine_on_unknown_field,
    case_r4_unsupported_fact,
    case_r5_unknowns_dropped,
    case_r6_unsupported_claim,
    case_r7_unconfirmed_plan,
    case_r8_style_touches_fact_lock,
    case_r9_structured_edit,
    case_r10_delete_lock_block,
    case_r11_duplicate_submit,
    case_r12_unknown_not_resent,
    case_r13_reference_guard,
    case_r14_budget,
    case_r15_reconcile,
    case_r16_no_invented_state,
]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="D1.P2 前半链契约测试（离线，零付费调用）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--mutation-test", action="store_true",
                    help="把实现逐条削弱，验证反例真的有牙")
    ap.add_argument("--report", default=str(OUT))
    args = ap.parse_args(argv)

    if args.mutation_test:
        return mutation_test()

    h = Harness()
    try:
        for case in CASES:
            try:
                case(h)
            except Exception as exc:                     # 反例自己炸了也是失败
                raw_case(h, case.__name__, "（用例异常）", "-", "exception",
                         [f"{type(exc).__name__}: {exc}"])
    finally:
        h.cleanup()

    bad = [r for r in h.rows if not r["ok"]]
    report = {
        "schema": "amz-listing-kit/front-contracts-verification@1",
        "plan_version": C.PLAN_VERSION,
        "cases": len(h.rows),
        "passed": len(h.rows) - len(bad),
        "failed": len(bad),
        "rows": h.rows,
        "does_not_prove": [
            "没有调用任何真实模型：PC-06/PC-07 用的是离线替身传输，只证明状态机与守卫成立",
            "没有证明候选图片通过 F1–F8：那属于 D1.R1–D1.R3",
            "没有证明跨商品通用：全部用例只跑内置虚构商品 Aster 01",
        ],
    }
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")

    if args.json:
        print(json.dumps({k: v for k, v in report.items() if k != "rows"},
                         ensure_ascii=False, indent=2))
    else:
        print("D1.P2 前半链契约测试（离线 · 零付费调用）")
        print("=" * 74)
        for row in h.rows:
            mark = "OK  " if row["ok"] else "FAIL"
            print(f"[{mark}] {row['case']:<4} {row['name']}  →  {row['actual']}"
                  f"（期望 {row['expect']}）")
            for note in row["notes"]:
                print(f"         · {note}")
            for problem in row["failed_checks"]:
                print(f"         ✗ {problem}")
        print()
        print(f"结论：{report['passed']}/{report['cases']} 条符合预期")
        print(f"报告：{path.relative_to(ROOT)}")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())
