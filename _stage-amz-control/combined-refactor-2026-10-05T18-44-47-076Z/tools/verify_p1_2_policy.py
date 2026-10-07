#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""P1.2 验收：素材与外发授权（fake executor 前置探针）。

判据来自计划 Phase 1 任务卡 P1.2 那一行：
    fake executor 前置探针：未批准、过期、用途不符、人像/竞品图默认外发均为零调用；
    批准记录版本可追溯。用户签署 allowlist 才算完成。
    回退：无授权即保持 unapproved，只允许本地/确定性路线；不得用「测试环境」绕过。

九条：
    A 基线（未签署）  政策文件结构合法；signed_by=null → 一切 unapproved；规则表是空的
    B 零调用           假执行器遍历 素材类别 × 用途 × 供应商/模型，**真的调用 0 次**；
                       而且零调用不是靠抛异常做到的（原因必须是 policy_not_signed）
    C 过期             同一条 allowed：到期前 allowed，到期次日 unapproved/expired。
                       一次绿、一次红用的是同一条规则 —— 证明这条判据不是一直红
    D 用途不符         批了「做图」不等于批了「复核」：另一个用途不命中，调用 0
    E 人像 / 竞品图    默认 denied（不是 unapproved）；逐条单独授权之后才 allowed
    F 版本可追溯       allowed 决策带 rule_id / 批准人 / 有效期 / retention / policy_version；
                       版本由内容算出（键顺序无关、改内容就变）；政策文件本身没被写回
    G 文件层拒绝       默认放行 / 通配键 / allowed 缺批准人 / 密钥（三种形态）→ 加载即报错
    H 本地路线不受影响 未签署时 v2 的确定性路径照跑，且这道门一次都没被查到外发
    I 签署与存档       签署入口会先校验再落盘；每改一次就多一版存档，把存档重新算一遍
                        得出同一个版本号 —— 这样"当时批的是哪一版、原文是什么"才答得出来

「零调用」是这一层唯一有意义的数字：只要有一次「没批准也发出去了」，
后面再多的审计记录也只是在描述一次已经发生的外发。

退出码：0 全过 / 1 有条目不过。
"""
from __future__ import annotations

import hashlib
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
import assets                     # noqa: E402  （只为验「本地路线没被这道门碰到」）
import data_policy as dp          # noqa: E402
import product_facts as pf        # noqa: E402

REPORT = ROOT / "evals" / "product-v1" / "p1" / "p1.2-policy.txt"
REAL = dp.DEFAULT_PATH
FULLSET = ROOT / "examples" / "product_fullset.json"
TMP = ROOT / "evals" / ".tmp" / "p1.2"

PROVIDER = "供应商A"
MODEL = "模型X"
PURPOSE = "reference_image_generation"
OTHER_PURPOSE = "candidate_review"
CLASSES = ("product_reference", "candidate", "portrait", "competitor")
RETENTION = "供应商侧不留存，任务结束后 24 小时内删除"


class FakeOutbound:
    """假执行器：**只有拿到 allowed 决策才会「真的调用」**。

    它存在的意义是把「零调用」变成一个可数的数字，而不是一句承诺。
    除了 PolicyDenied，别的异常一律不吞 —— 否则「零调用」可能只是崩了。
    """

    def __init__(self, policy: dp.Policy) -> None:
        self.policy = policy
        self.calls: list[tuple] = []
        self.blocked: list[dp.Decision] = []

    def send(self, *, asset_class, provider, model, purpose, now=None) -> dp.Decision:
        try:
            d = self.policy.require(asset_class=asset_class, provider=provider,
                                    model=model, purpose=purpose, now=now)
        except dp.PolicyDenied as exc:
            self.blocked.append(exc.decision)
            return exc.decision
        self.calls.append((asset_class, provider, model, purpose, d.policy_version))
        return d


def rule_yaml(*, rid, asset_class, provider=PROVIDER, model=MODEL, purpose=PURPOSE,
              decision="allowed", approver="运营负责人", approved_at="2026-09-23",
              expires_at="2026-12-31", retention=RETENTION, include_approver=True,
              order=None) -> str:
    fields: dict[str, str] = {"id": rid, "asset_class": asset_class, "purpose": purpose,
                              "provider": provider, "model": model, "decision": decision}
    if include_approver:
        fields["approver"] = approver
    if approved_at is not None:
        fields["approved_at"] = approved_at
    if expires_at is not None:
        fields["expires_at"] = expires_at
    if retention is not None:
        fields["retention"] = retention
    keys = order or ["id", "asset_class", "purpose", "provider", "model", "decision",
                     "approver", "approved_at", "expires_at", "retention"]
    keys = [k for k in keys if k in fields]
    out = [f"  - {keys[0]}: {fields[keys[0]]}"]
    out += [f"    {k}: {fields[k]}" for k in keys[1:]]
    return "\n".join(out) + "\n"


def policy_text(*, signed=True, rules="", extra_top="") -> str:
    """在真文件上只动必要的几处（改一个变量），不另造一份平行政策。"""
    text = REAL.read_text(encoding="utf-8")
    if signed:
        text = text.replace("signed_by: null", 'signed_by: "运营负责人"')
        text = text.replace("signed_at: null", "signed_at: 2026-09-23")
    if rules:
        text = text.replace("rules: []\n", "rules:\n" + rules)
    if extra_top:
        text = text.replace("updated_at: 2026-09-23\n", "updated_at: 2026-09-23\n" + extra_top)
    return text


def write_temp(name: str, text: str) -> Path:
    TMP.mkdir(parents=True, exist_ok=True)
    p = TMP / name
    p.write_text(text, encoding="utf-8", newline="")
    return p


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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

    def expect_reject(text: str, name: str, must_contain: str, label: str) -> None:
        p = write_temp(name, text)
        try:
            dp.load_policy(p)
        except dp.PolicyError as exc:
            hit = must_contain in str(exc)
            check(hit, label, f"报错含『{must_contain}』" if hit else
                  f"报错了但没提『{must_contain}』：{str(exc).splitlines()[0]}")
        except Exception as exc:                                   # noqa: BLE001
            check(False, label, f"抛的不是 PolicyError 而是 {type(exc).__name__}: {exc}")
        else:
            check(False, label, "居然加载通过了 —— 这一条本该被拦下")

    emit("P1.2 验收：素材与外发授权")
    emit("=" * 72)
    emit(f"时间：{date.today().isoformat()}")
    emit("本次切片的七项声明（计划 §7.1）：")
    emit("  用户可见行为  无（这一层还不接管线；只把『能不能发』变成一个可判的结论）")
    emit("  不变量        A 主体只有一份 / B 生成层看不见主体 / C 文字层不画字 / D 位置 1 零模型 全部未触碰")
    emit("  允许改的模块  contracts/data-policy-v1.yaml 与 src/data_policy.py 新增、"
         "tools/sign_allowlist.py 新增、contracts/data-policy-versions/ 新增；examples/ 只读")
    emit("  新增身份      policy_version = dpv1-<内容哈希前 12 位>（每次决策都带上它）；"
         "每一版的原文存成 contracts/data-policy-versions/<版本号>.yaml")
    emit("  拒绝路径      未签署 / 未批准 / 过期 / 用途不符 / 人像与竞品图 → 一律不给 allowed")
    emit("  判据          本文件 A–I；反向样本见 B/C/D/E/G/I；正向对照见 C/D/E/F/I")
    emit("  迁移与回退    纯加法：v2 planner 与确定性路径未改；无授权时只允许本地路线（H 条为运行时证据）")
    emit("")

    # ---------------------------------------------------------------- A
    emit("A 基线（未签署）")
    policy = dp.load_policy()
    check(True, "结构校验通过（不合法会直接抛）",
          f"类别 {len(policy.asset_classes())} 个 · 用途 {len(policy.purposes())} 个 · 规则 {len(policy.rules())} 条")
    check(policy.signed_by is None, "allowlist 还没被签署（signed_by=null）")
    check(len(policy.rules()) == 0, "规则表是空的 —— 现在一条外发都不允许")
    combos = [(c, p_) for c in CLASSES for p_ in policy.purposes()]
    decs = [policy.decide(asset_class=c, provider=PROVIDER, model=MODEL, purpose=p_)
            for c, p_ in combos]
    check(all(d.decision == "unapproved" and d.reason == "policy_not_signed" for d in decs),
          "未签署时全部 unapproved（人像与竞品图也一样）", f"查了 {len(decs)} 种组合")
    check(policy.policy_version == dp.policy_version(policy.doc)
          == dp.policy_version(dp.load_policy().doc),
          "版本由内容算出且可重复", f"policy_version={policy.policy_version}")
    bundle = pf.facts_from_product(pf.load_product(FULLSET),
                                   source_path="examples/product_fullset.json",
                                   data_policy_version=policy.policy_version)
    check(bundle["data_policy_version"] == policy.policy_version,
          "P1.1 的 data_policy_version 引用的是同一个版本号（授权语义只有一份）")
    emit("")

    # ---------------------------------------------------------------- B
    emit("B 零调用（未签署时，假执行器一次都不许真的调用）")
    gate = FakeOutbound(policy)
    for c in CLASSES:
        for p_ in policy.purposes():
            for prov, mdl in ((PROVIDER, MODEL), ("别家供应商", "别家模型")):
                gate.send(asset_class=c, provider=prov, model=mdl, purpose=p_)
    check(len(gate.calls) == 0, "真的调用 0 次", f"请求 {len(gate.blocked)} 次，全部被拦")
    check(len(gate.blocked) == len(CLASSES) * len(policy.purposes()) * 2,
          "每一次请求都留下了一条决策记录（不是静默丢弃）", f"blocked={len(gate.blocked)}")
    reasons = sorted({d.reason for d in gate.blocked})
    check(reasons == ["policy_not_signed"],
          "零调用的原因是『没签署』，不是『崩了』", f"reasons={reasons}")
    emit("")

    # ---------------------------------------------------------------- C
    emit("C 过期（同一条规则，只改 now）")
    expired = write_temp("expired.yaml", policy_text(rules=rule_yaml(
        rid="c-ref-gen", asset_class="product_reference", expires_at="2026-01-01")))
    pol_c = dp.load_policy(expired)
    gate_c = FakeOutbound(pol_c)
    before_d = gate_c.send(asset_class="product_reference", provider=PROVIDER, model=MODEL,
                           purpose=PURPOSE, now=date(2025, 12, 31))
    on_day_d = pol_c.decide(asset_class="product_reference", provider=PROVIDER, model=MODEL,
                            purpose=PURPOSE, now=date(2026, 1, 1))
    after_d = gate_c.send(asset_class="product_reference", provider=PROVIDER, model=MODEL,
                          purpose=PURPOSE, now=date(2026, 1, 2))
    check(before_d.decision == "allowed" and before_d.reason == "rule_allowed",
          "到期前：allowed", f"reason={before_d.reason}")
    check(on_day_d.decision == "allowed", "到期日当天仍有效（到期日算最后一天）")
    check(after_d.decision == "unapproved" and after_d.reason == "expired",
          "到期次日：unapproved / expired", f"reason={after_d.reason}")
    check(len(gate_c.calls) == 1, "过期之后那次没有真的调用", f"calls={len(gate_c.calls)}")
    emit("")

    # ---------------------------------------------------------------- D
    emit("D 用途不符（批了做图，不等于批了复核）")
    one = write_temp("one-purpose.yaml", policy_text(rules=rule_yaml(
        rid="d-ref-gen", asset_class="product_reference", purpose=PURPOSE)))
    pol_d = dp.load_policy(one)
    gate_d = FakeOutbound(pol_d)
    ok_d = gate_d.send(asset_class="product_reference", provider=PROVIDER, model=MODEL,
                       purpose=PURPOSE, now=date(2026, 9, 23))
    off_d = gate_d.send(asset_class="product_reference", provider=PROVIDER, model=MODEL,
                        purpose=OTHER_PURPOSE, now=date(2026, 9, 23))
    check(ok_d.decision == "allowed", "被批准的那个用途：allowed")
    check(off_d.decision == "unapproved" and off_d.reason == "no_matching_rule",
          "另一个用途：不命中 → unapproved", f"reason={off_d.reason}")
    check(len(gate_d.calls) == 1, "另一个用途没有真的调用", f"calls={len(gate_d.calls)}")
    emit("")

    # ---------------------------------------------------------------- E
    emit("E 人像 / 竞品图（V1 范围外：默认不批，单独授权才放行）")
    pol_e = dp.load_policy(write_temp("signed-no-rules.yaml", policy_text()))
    d_ref = pol_e.decide(asset_class="product_reference", provider=PROVIDER, model=MODEL, purpose=PURPOSE)
    d_por = pol_e.decide(asset_class="portrait", provider=PROVIDER, model=MODEL, purpose=PURPOSE)
    d_com = pol_e.decide(asset_class="competitor", provider=PROVIDER, model=MODEL, purpose=PURPOSE)
    check(d_por.decision == "denied" and d_com.decision == "denied",
          "人像与竞品图默认 denied（不是 unapproved：它们不是『还没批』，是『不许』）",
          f"portrait={d_por.decision} / competitor={d_com.decision}")
    check(d_ref.decision == "unapproved",
          "同一份签署清单下，商品参考图默认是 unapproved", f"reason={d_ref.reason}")
    pol_e2 = dp.load_policy(write_temp("portrait-authorized.yaml", policy_text(rules=rule_yaml(
        rid="e-portrait", asset_class="portrait", purpose=OTHER_PURPOSE))))
    d_auth = pol_e2.decide(asset_class="portrait", provider=PROVIDER, model=MODEL, purpose=OTHER_PURPOSE)
    check(d_auth.decision == "allowed" and d_auth.approver == "运营负责人",
          "逐条单独授权之后：allowed（范围外不是永远不能做，是要有人签字）",
          f"approver={d_auth.approver}")
    emit("")

    # ---------------------------------------------------------------- F
    emit("F 版本可追溯")
    trace = write_temp("trace.yaml", policy_text(rules=rule_yaml(
        rid="f-ref-gen", asset_class="product_reference", expires_at="2026-12-31")))
    pol_f = dp.load_policy(trace)
    d_f = pol_f.decide(asset_class="product_reference", provider=PROVIDER, model=MODEL,
                       purpose=PURPOSE, now=date(2026, 9, 23))
    check(d_f.decision == "allowed" and d_f.rule_id == "f-ref-gen",
          "决策指回了具体规则", f"rule_id={d_f.rule_id}")
    check(d_f.approver == "运营负责人" and d_f.approved_at == "2026-09-23"
          and d_f.expires_at == "2026-12-31" and bool(d_f.retention),
          "决策带上批准人 / 批准日 / 有效期 / 保留约束")
    check(d_f.policy_version.startswith("dpv1-") and len(d_f.policy_version) == 17,
          "决策带上版本号（事后能对回是哪一版授权）", f"policy_version={d_f.policy_version}")
    reordered = write_temp("trace-reordered.yaml", policy_text(rules=rule_yaml(
        rid="f-ref-gen", asset_class="product_reference", expires_at="2026-12-31",
        order=["id", "provider", "model", "purpose", "asset_class", "decision",
               "approved_at", "expires_at", "retention", "approver"])))
    check(dp.load_policy(reordered).policy_version == pol_f.policy_version,
          "同一条规则、字段顺序变了 → 版本不变（版本算的是语义）")
    changed = write_temp("trace-changed.yaml", policy_text(rules=(
        rule_yaml(rid="f-ref-gen", asset_class="product_reference", expires_at="2026-12-31")
        + rule_yaml(rid="f-ref-gen-2", asset_class="candidate", purpose=OTHER_PURPOSE))))
    check(dp.load_policy(changed).policy_version != pol_f.policy_version,
          "多一条规则 → 版本变了（改授权就是改版本）")
    h_before = sha(trace)
    for c in CLASSES:
        pol_f.decide(asset_class=c, provider=PROVIDER, model=MODEL, purpose=PURPOSE,
                     now=date(2026, 9, 23))
    check(sha(trace) == h_before, "查询很多次之后，政策文件本身没被写回（只读）")
    audit = d_f.as_dict()
    need = {"decision", "reason", "policy_version", "rule_id", "approver", "approved_at",
            "expires_at", "retention"}
    check(need <= set(audit) and audit["reason"] == "rule_allowed",
          "决策可直接作为审计记录的一行", f"字段 {len(audit)} 个")
    emit("")

    # ---------------------------------------------------------------- G
    emit("G 文件层拒绝（这些根本不该被加载进来）")
    expect_reject(policy_text().replace("    default: unapproved\n", "    default: allowed\n", 1),
                  "g1-default-allowed.yaml", "default", "默认值是 allowed → 加载报错")
    expect_reject(policy_text(rules=rule_yaml(rid="g-wild", asset_class="product_reference",
                                              provider='"*"', model='"*"')),
                  "g2-wildcard.yaml", "通配", "键里用通配 * → 加载报错")
    expect_reject(policy_text(rules=rule_yaml(rid="g-noapprover", asset_class="product_reference",
                                              include_approver=False)),
                  "g3-no-approver.yaml", "approver", "allowed 却没有批准人 → 加载报错")
    expect_reject(policy_text(extra_top='api_key: "abc123"\n'),
                  "g4-key-name.yaml", "密钥", "键名像密钥（api_key）→ 加载报错")
    expect_reject(policy_text(extra_top='contact: "sk-live-abcdefghijklmnop"\n'),
                  "g5-key-value.yaml", "密钥", "值看起来像 API key → 加载报错")
    expect_reject(policy_text(extra_top='note_pem: "-----BEGIN PRIVATE KEY-----"\n'),
                  "g6-pem.yaml", "PEM", "值里带 PEM 私钥头 → 加载报错")
    emit("")

    # ---------------------------------------------------------------- H
    emit("H 本地/确定性路线不受这道门影响")
    product = pf.load_product(FULLSET)
    before = assets.collect(product, ROOT / "examples")
    pol_h = dp.load_policy()
    gate_h = FakeOutbound(pol_h)
    for c in CLASSES:
        for p_ in pol_h.purposes():
            gate_h.send(asset_class=c, provider=PROVIDER, model=MODEL, purpose=p_)
    after = assets.collect(product, ROOT / "examples")
    check(json.dumps(before, ensure_ascii=False, sort_keys=True)
          == json.dumps(after, ensure_ascii=False, sort_keys=True),
          "未签署时 v2 的 assets.collect 结果完全一致（本地路线照跑）")
    check(len(gate_h.calls) == 0 and len(gate_h.blocked) == len(CLASSES) * len(pol_h.purposes()),
          "被拦的只有外发；本地一次都没被这道门挡住", f"拦下 {len(gate_h.blocked)} 次外发")
    emit("")

    # ---------------------------------------------------------------- I
    emit("I 签署入口：签的是范围，版本原文要存得下来")
    SIGN = ROOT / "tools" / "sign_allowlist.py"
    iroot = TMP / "i-root"
    if iroot.exists():
        shutil.rmtree(iroot)
    (iroot / "contracts").mkdir(parents=True)
    ipol = iroot / "contracts" / "data-policy-v1.yaml"
    shutil.copy2(REAL, ipol)
    arch = iroot / "contracts" / "data-policy-versions"
    real_before = REAL.read_bytes()

    def sign(*extra) -> int:
        cmd = [sys.executable, str(SIGN), "--root", str(iroot)] + list(extra)
        return subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace").returncode

    def archived() -> list[str]:
        return sorted(p.stem for p in arch.glob("*.yaml"))

    APPROVE = ("--approve", "--id", "ref-gen-1", "--asset-class", "product_reference",
               "--purpose", PURPOSE, "--provider", PROVIDER, "--model", MODEL,
               "--by", "运营负责人", "--at", "2026-09-23", "--retention", RETENTION)
    v0 = dp.load_policy(ipol).policy_version

    check(sign("--list") == 0, "--list 能打印闭集与现状")
    check(sign("--dry-run", *APPROVE) == 0, "--dry-run 试算成功")
    check(ipol.read_bytes() == real_before and not arch.exists(),
          "--dry-run 既不写政策也不建存档（试算不是偷偷落盘）")

    check(sign(*APPROVE) == 0, "签署并追加规则：成功")
    pol1 = dp.load_policy(ipol)
    v1 = pol1.policy_version
    check(pol1.signed_by == "运营负责人" and len(pol1.rules()) == 1,
          "signed_by / signed_at 落盘，规则进表",
          f"signed_by={pol1.signed_by} · rules={len(pol1.rules())}")
    check(v1 != v0, "版本随内容变", f"{v0} → {v1}")
    check(v0 in archived() and v1 in archived(), "改动前后两版都存档了", f"{archived()}")
    recon = {s: dp.policy_version(dp.read_archived(s, root=iroot)) for s in archived()}
    check(all(k == v for k, v in recon.items()),
          "把存档重新算一遍得出同一个版本号（存档没被就地改过）", f"{recon}")

    check(sign("--revoke", "ref-gen-1") == 0, "撤销规则：成功")
    v2 = dp.load_policy(ipol).policy_version
    names = archived()
    check(v2 not in (v0, v1) and {v0, v1, v2} <= set(names),
          "三版齐全 —— 『当时批的是哪一版』答得出来", f"{names}")
    check((dp.read_archived(v1, root=iroot) or {}).get("signed_by") == "运营负责人",
          "旧版原文还在：能读出当时是谁签的、批了什么")

    check(sign("--approve", "--id", "x", "--asset-class", "product_reference",
               "--purpose", PURPOSE, "--provider", PROVIDER, "--model", MODEL,
               "--at", "2026-09-23", "--retention", RETENTION) == 2,
          "缺 --by → 2（批准人是人给的，工具不填默认值）")
    check(sign(*APPROVE) == 0 and sign(*APPROVE) == 2,
          "同一 id 追加两次 → 第二次 2（同一个 id 只能有一条）")
    check(sign("--revoke", "根本不存在") == 2, "撤销一个不存在的规则 → 2")
    check(REAL.read_bytes() == real_before,
          "整段测试没碰真政策文件（一个字节都没变）")
    emit("")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    emit("=" * 72)
    if fails:
        emit(f"结论：{len(fails)} 条不过 —— {'；'.join(fails)}")
    else:
        emit("结论：全部通过")
    emit("边界：本报告只证明『未批准 / 过期 / 用途不符 / 范围外素材』不会被发送，")
    emit("      以及授权记录可追溯（每一版的原文都存得下来、重算得出同一个版本号）；")
    emit("      不证明用户已经签署 allowlist（现在还没签），也不证明任何一次真实外发合规。")
    emit("")
    emit(f"报告：{REPORT}")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
