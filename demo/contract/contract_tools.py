#!/usr/bin/env python
"""D1.P1 处理合同守卫 —— 离线、只读、零付费调用。

它回答三个问题：
  1. 产品计划 §4.4 的 13 个处理合同，与机器可读的 `processing_contracts.json`
     是否指向同一件事？
  2. 每条合同引用的权威，是否都在 `authority_matrix.json` 登记过
     （谁有权决定这一项、这一项不能证明什么）？
  3. 计划 §4.2 的状态取值，与 `state_vocabulary.json` 是否一致？

为什么必须交叉核对，而不是各写一份：
  散文（计划）和机器契约（JSON）是同一批事实的两种形态。若只各自存在，
  就会出现「计划改了、JSON 没改」的静默漂移 —— 本项目最怕的不是报红，
  是红被吃掉。所以这里**不复制正文**，只核对身份：合同 ID、名称、引用权威、
  输出对象、证据类型、状态取值，以及契约声明的短语必须能在计划对应单元格里找到。

三条纪律：
  1. 只读：不改计划、不改 JSON、不写任何状态。
  2. 宁红不绿：任何核对不上的项都报问题，不用默认值蒙过去。
  3. 判据必须能被证伪：--self-test 把契约逐项改坏，要求每一项都被抓到。

用法：
    python demo/contract/contract_tools.py --project . --check
    python demo/contract/contract_tools.py --project . --json
    python demo/contract/contract_tools.py --project . --self-test

退出码：
    0  合同、权威矩阵、状态词汇与计划一致
    2  契约文件自身结构有问题
    3  与产品计划漂移
    4  权威矩阵缺失、或与合同引用不匹配
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PLAN_REL = "docs/product-demo-goal-and-implementation-plan.md"
CONTRACTS_REL = "demo/contract/processing_contracts.json"
AUTHORITIES_REL = "demo/contract/authority_matrix.json"
VOCAB_REL = "demo/contract/state_vocabulary.json"

CONTRACTS_SCHEMA = "amz-listing-kit/processing-contracts@1"
AUTHORITIES_SCHEMA = "amz-listing-kit/authority-matrix@1"
VOCAB_SCHEMA = "amz-listing-kit/state-vocabulary@1"

# 谁有权决定某一项的取值。模型只能「提案」，不能写权威值 —— 这条靠 ACTORS
# 里没有单独的 model-write 角色来保证：system.model 出现即意味着该值可能是模型产物，
# 必须同时能被 system.deterministic 或 user 复核。
ACTORS = ("user", "system.deterministic", "system.model", "external.provider")

# 事实验证责任者的闭集合。新加一类责任者必须同时改计划和这里，不能悄悄扩。
VERIFIER_KINDS = (
    "deterministic_rule",
    "reference_conditioned_vision",
    "segmentation_or_local_match",
    "explicit_human_fact_confirmation",
    "human_visual_review",
)

# 人工接管标记：判据要挂在**不随措辞变化**的短标记上（同 regress_all.py 的
# ENV_SIGS 口径）。这里只做存在性核对（计划行里到底有没有「人」），不评措辞。
HUMAN_MARKERS = ("人工", "用户", "显式确认", "人比较")

REQUIRED_CONTRACT_KEYS = (
    "id", "name", "inputs", "mechanism", "output_objects",
    "outcomes", "human_takeover_required", "human_takeover_when", "evidence_kinds",
)
REQUIRED_AUTHORITY_KEYS = ("id", "name", "may_write", "cannot_prove")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def read_json(path: Path):
    return json.loads(read_text(path))


def section(text: str, heading: str) -> str:
    """取某个 `### x` 小节的正文，到下一个同级标题为止。"""
    out: list[str] = []
    inside = False
    for line in text.splitlines():
        if line.startswith("### "):
            inside = line.startswith(heading)
            continue
        if inside:
            out.append(line)
    return "\n".join(out)


def table_rows(body: str) -> list[list[str]]:
    """把 markdown 表格拆成单元格；返回的行已去掉表头与分隔行。"""
    rows: list[list[str]] = []
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells:
            continue
        if set("".join(cells)) <= set("-: "):
            continue
        rows.append(cells)
    return rows


def plan_version(text: str) -> str | None:
    m = re.search(r"^版本：\s*(\S+)\s*$", text, re.M)
    return m.group(1) if m else None


def plan_pc_rows(text: str) -> list[dict]:
    rows: list[dict] = []
    for cells in table_rows(section(text, "### 4.4")):
        if len(cells) != 6:
            continue
        m = re.match(r"^(PC-\d{2})\s+(.+)$", cells[0])
        if not m:
            continue
        rows.append({
            "id": m.group(1), "name": m.group(2).strip(),
            "inputs": cells[1], "mechanism": cells[2], "outputs": cells[3],
            "handling": cells[4], "evidence": cells[5],
            "all": " ".join(cells),
        })
    return rows


def plan_machine_states(text: str, label: str) -> set[str]:
    """从计划 §4.2 的 `**Label：** `...`` 行里抠出状态集合。"""
    body = section(text, "### 4.2")
    for line in body.splitlines():
        if not line.strip().startswith(f"**{label}："):
            continue
        tokens: set[str] = set()
        for chunk in re.findall(r"`([^`]+)`", line):
            for part in re.split(r"[→/]", chunk):
                t = part.strip().strip("`")
                if t and re.fullmatch(r"[A-Z_]+", t):
                    tokens.add(t)
        return tokens
    return set()


def plan_fact_types(text: str) -> list[str]:
    out: list[str] = []
    for cells in table_rows(section(text, "### 9.1.1")):
        if len(cells) != 3 or cells[0] == "事实类型":
            continue
        out.append(cells[0])
    return out


def check_authorities(doc: dict, plan_text: str) -> list[str]:
    bad: list[str] = []
    if doc.get("schema") != AUTHORITIES_SCHEMA:
        bad.append(f"schema 不是 {AUTHORITIES_SCHEMA}：{doc.get('schema')!r}")
    auths = doc.get("authorities") or []
    if not auths:
        bad.append("authorities 为空")
    seen: list[str] = []
    for a in auths:
        aid = a.get("id")
        if not aid:
            bad.append(f"权威缺 id：{a.get('name')!r}")
            continue
        seen.append(aid)
        for key in REQUIRED_AUTHORITY_KEYS:
            if key not in a:
                bad.append(f"{aid}: 缺字段 {key}")
        if not a.get("cannot_prove"):
            bad.append(f"{aid}: 必须写 cannot_prove —— 不写，权威边界就会在实现里被放大")
        for actor in (a.get("may_write") or []):
            if actor not in ACTORS:
                bad.append(f"{aid}: may_write 里的 {actor!r} 不在角色闭集合 {ACTORS}")
        for actor in (a.get("proposed_by") or []):
            if actor not in ACTORS:
                bad.append(f"{aid}: proposed_by 里的 {actor!r} 不在角色闭集合 {ACTORS}")
        if not (a.get("may_write") or []):
            bad.append(f"{aid}: may_write 为空 —— 没有写入者的项无法被追责")
    for aid in sorted({i for i in seen if seen.count(i) > 1}):
        bad.append(f"权威 id 重复：{aid}")

    facts = doc.get("fact_class_responsibility") or []
    planned = plan_fact_types(plan_text)
    got = [f.get("fact_type") for f in facts]
    if got != planned:
        bad.append(f"事实类型与计划 §9.1.1 不一致：计划={planned} 契约={got}")
    for f in facts:
        kinds = f.get("verifier_kinds") or []
        if not kinds:
            bad.append(f"{f.get('fact_type')!r}: verifier_kinds 为空")
        for k in kinds:
            if k not in VERIFIER_KINDS:
                bad.append(f"{f.get('fact_type')!r}: 责任者 {k!r} 不在闭集合 {VERIFIER_KINDS}")
        if not f.get("boundary"):
            bad.append(f"{f.get('fact_type')!r}: 必须写 boundary（允许的结论边界）")
    return bad


def check_contracts_structure(doc: dict, authority_ids: set[str]) -> list[str]:
    bad: list[str] = []
    if doc.get("schema") != CONTRACTS_SCHEMA:
        bad.append(f"schema 不是 {CONTRACTS_SCHEMA}：{doc.get('schema')!r}")
    vocab = doc.get("outcome_vocabulary") or {}
    if not vocab:
        bad.append("outcome_vocabulary 为空 —— 结果取值没有闭集合，实现就能自己发明状态")
    cons = doc.get("contracts") or []
    if not cons:
        bad.append("contracts 为空")
    ids: list[str] = []
    for c in cons:
        cid = c.get("id") or "?"
        ids.append(str(cid))
        for key in REQUIRED_CONTRACT_KEYS:
            if key not in c:
                bad.append(f"{cid}: 缺字段 {key}")
        if not str(c.get("name") or "").strip():
            bad.append(f"{cid}: name 为空")
        if not str(c.get("mechanism") or "").strip():
            bad.append(f"{cid}: mechanism 为空 —— 「怎么处理」没写，就只剩一句口号")
        for group, key in (("inputs", "inputs"), ("preconditions", "preconditions")):
            for ref in c.get(group) or []:
                aid = ref.get("authority")
                if aid not in authority_ids:
                    bad.append(f"{cid}: {key} 引用了未登记的权威 {aid!r}")
                if not ref.get("as"):
                    bad.append(f"{cid}: {key} 里的 {aid!r} 缺 as 短语 —— 无法与计划核对")
        for o in c.get("outcomes") or []:
            if o not in vocab:
                bad.append(f"{cid}: 结果 {o!r} 不在取值域 {sorted(vocab)}")
        if not isinstance(c.get("human_takeover_required"), bool):
            bad.append(f"{cid}: human_takeover_required 必须是布尔")
        elif c["human_takeover_required"] and not str(c.get("human_takeover_when") or "").strip():
            bad.append(f"{cid}: 标了需要人工接管，却没写 human_takeover_when")
        if not (c.get("output_objects") or []):
            bad.append(f"{cid}: output_objects 为空")
        if not (c.get("evidence_kinds") or []):
            bad.append(f"{cid}: evidence_kinds 为空 —— 没有验收证据的合同不可被证伪")
    for cid in sorted({i for i in ids if ids.count(i) > 1}):
        bad.append(f"合同 id 重复：{cid}")
    expected = [f"PC-{n:02d}" for n in range(1, 14)]
    if ids != expected:
        bad.append(f"合同清单与 PC-01…PC-13 不一致：{ids}")
    return bad


def contains_token(cell: str, token: str) -> bool:
    """整体词匹配：token 必须**成词**地出现在 cell 里，两侧不能是 ASCII 词字符。

    为什么不用 `in`：`"Review" in "VisualReview(...)"` 为真 —— 一个改了名的输出对象
    会被子串匹配放过去。这个洞是自检抓出来的，不是想出来的。
    """
    def ascii_word(ch: str) -> bool:
        return ch.isascii() and (ch.isalnum() or ch == "_")

    start = 0
    while True:
        i = cell.find(token, start)
        if i < 0:
            return False
        j = i + len(token)
        left_ok = i == 0 or not ascii_word(cell[i - 1])
        right_ok = j == len(cell) or not ascii_word(cell[j])
        if left_ok and right_ok:
            return True
        start = i + 1


def check_plan_alignment(doc: dict, rows: list[dict], plan_ver: str | None) -> list[str]:
    bad: list[str] = []
    plan_ids = [r["id"] for r in rows]
    json_ids = [str(c.get("id")) for c in (doc.get("contracts") or [])]
    if plan_ids != json_ids:
        bad.append(f"合同清单与计划 §4.4 不一致：计划={plan_ids} 契约={json_ids}")

    want = doc.get("plan_version")
    if not want:
        bad.append("契约没写 plan_version —— 计划一改就没人知道合同该不该重审")
    elif plan_ver and want != plan_ver:
        bad.append(f"契约按计划版本 {want} 冻结，当前计划是 {plan_ver} —— 计划改过，合同必须重审")

    by_id = {r["id"]: r for r in rows}
    for c in doc.get("contracts") or []:
        cid = str(c.get("id"))
        row = by_id.get(cid)
        if row is None:
            bad.append(f"{cid}: 计划 §4.4 里没有这一行")
            continue
        if row["name"] != c.get("name"):
            bad.append(f"{cid}: 名称不一致 计划={row['name']!r} 契约={c.get('name')!r}")
        for ref in c.get("inputs") or []:
            if ref.get("as") and not contains_token(row["inputs"], ref["as"]):
                bad.append(f"{cid}: 输入权威短语 {ref['as']!r} 不在计划的「输入及权威」单元格里")
        for ref in c.get("preconditions") or []:
            if ref.get("as") and not contains_token(row["mechanism"], ref["as"]):
                bad.append(f"{cid}: 前提短语 {ref['as']!r} 不在计划的「处理机制」单元格里")
        for obj in c.get("output_objects") or []:
            if not contains_token(row["outputs"], obj):
                bad.append(f"{cid}: 输出对象 {obj!r} 不在计划的「成功输出」单元格里")
        for ev in c.get("evidence_kinds") or []:
            if not contains_token(row["evidence"], ev):
                bad.append(f"{cid}: 证据类型 {ev!r} 不在计划的「验收证据」单元格里")

        # 人工接管必须**双向**对齐：契约说需要 → 计划行要有人；
        # 计划行的拒绝路径上写了人 → 契约就不能单方面声明「无需人工」。
        required = bool(c.get("human_takeover_required"))
        handling_has_human = any(m in row["handling"] for m in HUMAN_MARKERS)
        if required and not any(m in row["all"] for m in HUMAN_MARKERS):
            bad.append(f"{cid}: 契约要求人工接管，但计划这一行没有任何人工标记 "
                       f"{list(HUMAN_MARKERS)} —— 两者至少有一个是错的")
        if handling_has_human and not required:
            bad.append(f"{cid}: 计划的拒绝路径里写了「人」，契约却声明不需要人工接管 —— "
                       f"这正是把人从失败路径上悄悄删掉的写法")
    return bad


def check_vocabulary(doc: dict, plan_text: str) -> list[str]:
    bad: list[str] = []
    if doc.get("schema") != VOCAB_SCHEMA:
        bad.append(f"schema 不是 {VOCAB_SCHEMA}：{doc.get('schema')!r}")
    machines = doc.get("machines") or {}
    if not machines:
        bad.append("machines 为空")
    for label, machine in machines.items():
        planned = plan_machine_states(plan_text, label)
        if not planned:
            bad.append(f"{label}: 计划 §4.2 里找不到 `**{label}：**` 状态行")
            continue
        got = set(machine.get("states") or [])
        if got != planned:
            bad.append(f"{label}: 状态取值与计划不一致 计划={sorted(planned)} 契约={sorted(got)}")
        terminal = set(machine.get("terminal") or [])
        if not terminal:
            bad.append(f"{label}: terminal 为空")
        for s in sorted(terminal - got):
            bad.append(f"{label}: terminal 里的 {s!r} 不在 states 里")
        if not str(machine.get("note") or "").strip():
            bad.append(f"{label}: 必须写 note（终局语义容易在实现里被误用）")
    return bad


def run_checks(plan_text: str, contracts_doc: dict, authorities_doc: dict,
               vocab_doc: dict) -> tuple[list[str], list[str], list[str], list[str]]:
    """唯一的一条核对路径：--check 与 --self-test 都必须走这里。

    为什么必须共用：自检若自己另拼一套检查，它验的就是另一个程序。第一版正是这样
    漏掉了「计划版本」这条 —— 版本核对写在 evaluate 里，自检根本没走到。
    返回 (结构, 权威, 状态词汇, 与计划漂移)。
    """
    auth_ids = {a.get("id") for a in ((authorities_doc or {}).get("authorities") or [])}
    return (
        check_contracts_structure(contracts_doc or {}, auth_ids),
        check_authorities(authorities_doc or {}, plan_text),
        check_vocabulary(vocab_doc or {}, plan_text),
        check_plan_alignment(contracts_doc or {}, plan_pc_rows(plan_text),
                             plan_version(plan_text)),
    )


def code_for(structure: list[str], authority: list[str],
             vocab: list[str], drift: list[str]) -> int:
    if structure or vocab:
        return 2
    if authority:
        return 4
    if drift:
        return 3
    return 0


def evaluate(root: Path) -> tuple[int, dict]:
    plan_path = root / PLAN_REL
    problems: list[str] = []
    plan_text = read_text(plan_path) if plan_path.is_file() else ""
    if not plan_text:
        problems.append(f"缺产品计划：{PLAN_REL}")

    docs: dict[str, dict] = {}
    for rel in (AUTHORITIES_REL, CONTRACTS_REL, VOCAB_REL):
        path = root / rel
        if not path.is_file():
            problems.append(f"缺契约文件：{rel}")
            continue
        try:
            docs[rel] = read_json(path)
        except json.JSONDecodeError as exc:
            problems.append(f"{rel} 不是合法 JSON：{exc}")

    structure, authority, vocab, drift = run_checks(
        plan_text,
        docs.get(CONTRACTS_REL),
        docs.get(AUTHORITIES_REL),
        docs.get(VOCAB_REL),
    )
    code = code_for(structure, authority, vocab, drift) if not problems else 2

    return code, {
        "plan": PLAN_REL,
        "plan_version": plan_version(plan_text) if plan_text else None,
        "contracts": len((docs.get(CONTRACTS_REL, {}).get("contracts") or [])),
        "authorities": len((docs.get(AUTHORITIES_REL, {}).get("authorities") or [])),
        "machines": sorted((docs.get(VOCAB_REL, {}).get("machines") or {})),
        "problems": problems,
        "structure_problems": structure,
        "authority_problems": authority,
        "vocabulary_problems": vocab,
        "plan_drift": drift,
    }

def render(rep: dict) -> str:
    lines = [
        "处理合同守卫（只读 · 离线 · 零付费调用）",
        "=" * 72,
        f"计划：{rep['plan']}（{rep['plan_version']}）",
        f"合同：{rep['contracts']} 条　权威：{rep['authorities']} 项　状态机：{'、'.join(rep['machines'])}",
        "",
    ]
    groups = (
        ("文件", rep["problems"]),
        ("契约自身", rep["structure_problems"]),
        ("权威矩阵", rep["authority_problems"]),
        ("状态词汇", rep["vocabulary_problems"]),
        ("与计划漂移", rep["plan_drift"]),
    )
    for title, items in groups:
        if items:
            lines.append(f"{title}：{len(items)} 条问题")
            lines += [f"  ✗ {p}" for p in items]
        else:
            lines.append(f"{title}：通过")
    return "\n".join(lines)


def self_test(root: Path) -> int:
    """把契约逐项改坏，要求每一项都被抓到 —— 判据必须能被证伪。

    两条自我要求：
      1. 走与 --check 完全相同的 run_checks，否则自检就只是在检查另一个程序；
      2. 每个探针先自证「真的改动了输入」—— 没改到东西的探针会伪装成「抓不到」。
    """
    plan_text = read_text(root / PLAN_REL)
    contracts = read_json(root / CONTRACTS_REL)
    authorities = read_json(root / AUTHORITIES_REL)
    vocab = read_json(root / VOCAB_REL)

    def clone(d):
        return json.loads(json.dumps(d, ensure_ascii=False))

    def find(seq, value):
        return next(x for x in seq if x.get("id") == value)

    def need_human_pc06(c, a, v, p):
        pc = find(c["contracts"], "PC-06")
        pc["human_takeover_required"] = True
        pc["human_takeover_when"] = "自检注入：声明需要人工，但计划这一行没有人"

    def drop_human_pc09(c, a, v, p):
        pc = find(c["contracts"], "PC-09")
        pc["human_takeover_required"] = False
        pc["human_takeover_when"] = ""

    cases = [
        ("计划改了合同名，契约没跟",
         lambda c, a, v, p: p.replace("PC-05 提示词", "PC-05 提示词改名")),
        ("计划改了输出对象，契约没跟",
         lambda c, a, v, p: p.replace("`VisualReview(keep/redo/reject)`",
                                      "`Review(keep/redo/reject)`")),
        ("契约引用了未登记的权威", lambda c, a, v, p: c["contracts"][0]["inputs"].append(
            {"authority": "A-还不存在", "as": "用户选择的商品包"})),
        ("结果取值不在闭集合", lambda c, a, v, p: c["contracts"][0]["outcomes"].append("大概可以")),
        ("删掉一条合同", lambda c, a, v, p: c["contracts"].pop()),
        ("合同顺序颠倒", lambda c, a, v, p: c["contracts"].reverse()),
        ("输出对象改成一个词根（Review 冒充 VisualReview）",
         lambda c, a, v, p: find(c["contracts"], "PC-10")["output_objects"].__setitem__(0, "Review")),
        ("证据类型不在计划单元格里",
         lambda c, a, v, p: find(c["contracts"], "PC-08")["evidence_kinds"].append("我觉得没问题")),
        ("计划行要求人工，契约却声明不需要", drop_human_pc09),
        ("契约说需要人工，计划行里没有人", need_human_pc06),
        ("状态机少了 UNKNOWN", lambda c, a, v, p: v["machines"]["Attempt"]["states"].remove("UNKNOWN")),
        ("权威没写 cannot_prove",
         lambda c, a, v, p: find(a["authorities"], "A-ASSET").pop("cannot_prove", None)),
        ("权威写入者不在角色闭集合",
         lambda c, a, v, p: find(a["authorities"], "A-REFIMG")["may_write"].append("somebody")),
        ("事实类型与 §9.1.1 不一致", lambda c, a, v, p: a["fact_class_responsibility"].pop()),
        ("契约按旧计划版本冻结", lambda c, a, v, p: c.__setitem__("plan_version", "v0.9")),
        ("合同缺 human_takeover_when",
         lambda c, a, v, p: find(c["contracts"], "PC-02").pop("human_takeover_when", None)),
        ("状态终局不在取值域", lambda c, a, v, p: v["machines"]["Shot"]["terminal"].append("DONE")),
        ("权威 may_write 为空（没人能负责）",
         lambda c, a, v, p: find(a["authorities"], "A-STYLE").__setitem__("may_write", [])),
    ]

    bad = 0
    for name, mutate in cases:
        c, a, v, p = clone(contracts), clone(authorities), clone(vocab), plan_text
        before = json.dumps([c, a, v, p], ensure_ascii=False, sort_keys=True)
        # 探针协议：改动 c/a/v 的原地内容；如果返回字符串，就当成改写后的计划正文。
        # 不支持返回值的探针只能原地改 JSON —— 第一版就在这里静默失效过一次。
        ret = mutate(c, a, v, p)
        if isinstance(ret, str):
            p = ret
        after = json.dumps([c, a, v, p], ensure_ascii=False, sort_keys=True)
        if before == after:
            print(f"[FAIL] {name}　→　这个探针没改到任何输入（失效的自检）")
            bad += 1
            continue
        problems = [x for group in run_checks(p, c, a, v) for x in group]
        caught = bool(problems)
        print(f"[{'OK  ' if caught else 'FAIL'}] {name}　→　{problems[0] if problems else '没有被抓到'}")
        bad += 0 if caught else 1
    print(f"\n自检：{len(cases) - bad}/{len(cases)} 项被正确抓到")
    return 0 if bad == 0 else 1

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".")
    ap.add_argument("--check", action="store_true", help="核对合同、权威与计划（默认行为）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    root = Path(args.project).resolve()
    if args.self_test:
        return self_test(root)
    code, rep = evaluate(root)
    if args.json:
        print(json.dumps({"exit_code": code, **rep}, ensure_ascii=False, indent=2))
    else:
        print(render(rep))
    return code


if __name__ == "__main__":
    raise SystemExit(main())