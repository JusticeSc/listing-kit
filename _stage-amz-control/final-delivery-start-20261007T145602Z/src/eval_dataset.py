#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""Golden/Counterexample 数据集 v1 —— 「拿哪些样本证明产品可用」的可加载登记。

它把三件本来散着的事收成一次可复现的加载：

    ① **这条样本绑的是哪一版输入**：`sha256(输入文件)` + `facts_version`
       （由 ProductFacts 现场算出来核对，不是人手抄一个版本号）+ `data_policy_version`。
    ② **这些样本现在有没有人负责判定**：标签人必须登记在 `dataset.json` 的
       `labelers` 里。没人登记的标签、以及还没贴标签的样本，**一律不进门禁统计** ——
       这就是计划 P1.5 那句「标签责任人不明确时样本不进入门禁，只保留为待标注」
       落到机器上的样子，而不是一句写在文档里的话。
    ③ **每一类关键错误有没有正反例**：正例 = 被接受、且这条被检过的样本；
       负例 = 被拒、且这条被判失败的样本；缺哪一类就点名报哪一类。

四条刻意的设计：

  **样例不计数。** 只有 `source_kind: pilot` 才算进覆盖统计。样例可以进数据集
  （先把判据和工具链跑通），但不能拿来证明"产品在真实样本上可用" ——
  与 P1.4 的「样例不计数」是同一条纪律。

  **标签只新增版本，不就地改。** 标签文件的名字就是它内容的版本
  （`gcv1-<前 12 位>`）。加载时重新算一遍，对不上就报「被就地改过」——
  因为"当时是哪一版标签判的"是交付追溯要回答的问题，就地改就永远答不上来。

  **冲突显式列出。** 同一版里同一条样本出现两条不同结论时，既不取"最后一条"，
  也不取"多数"：记进 `conflicts` 并退出覆盖统计，等人裁决（裁决的结果是新版本）。

  **本模块只读。** 不生成图片、不写标签、不改任何输入文件；标签只能由
  `tools/freeze_dataset_labels.py` 冻成新版本。

用法：
    import eval_dataset as ed
    report = ed.audit()                 # 读真数据集：绑定 / 待标注 / 冲突 / 覆盖
    print(report["dataset_version"], report["coverage_gaps"], report["class_gaps"])
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCHEMA = "amz-listing-kit/eval-dataset@1"
LABEL_SCHEMA = "amz-listing-kit/eval-labels@1"
DATASET_DIR = ROOT / "evals" / "product-v1" / "dataset"
MANIFEST = DATASET_DIR / "manifest.jsonl"
INDEX = DATASET_DIR / "dataset.json"
LABELS_DIR = DATASET_DIR / "labels"
BRAND = ROOT / "config" / "brand.json"
POLICY = ROOT / "contracts" / "data-policy-v1.yaml"
CHECKLIST = ROOT / "contracts" / "review-checklist-v1.yaml"

# 五类样本：正常 / 边界 / 明显关键错误 / 难判 / Unknown。
# 「这条样本属于哪一类」是**设计它的人**说的（这条想考什么）；「它该判接受还是拒绝」
# 是**标签人**说的。两件事分开写，才不会互相冒充（候选不是结论）。
CASE_CLASSES = ("normal", "boundary", "critical_error", "hard_judgement", "unknown")
INPUT_KINDS = ("product_facts_source", "material_image")
SOURCE_KINDS = ("sample", "pilot")
VERDICTS = ("accept", "reject", "unknown")

# 只有真实试点输入算数（与 P1.4「样例不计数」同一条纪律）。
COUNTING_SOURCE_KIND = "pilot"
_BIND_RANK = {"ok": 0, "pending_input": 1, "mismatch": 2}

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_ENTRY_RE = re.compile(r"^GC-\d{4}$")
_FACTS_VER_RE = re.compile(r"^pfv1-[0-9a-f]{12}$")
_LABEL_VER_RE = re.compile(r"^gcv1-[0-9a-f]{12}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# 绝对路径的两种写法：盘符开头，或反斜杠 / 正斜杠开头（UNC 与 POSIX）。
_ABS_RE = re.compile(r"^(?:[A-Za-z]:|[\\/]{1,2})")


class DatasetError(Exception):
    """数据集或标签文件本身不合法 —— 直接拒绝加载，不给"勉强能用"的余地。"""


# ---------------------------------------------------------------- 基础

def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), default=str)


def sha256_file(path) -> str:
    h = hashlib.sha256()
    h.update(Path(path).read_bytes())
    return h.hexdigest()


def read_jsonl(path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise DatasetError(f"找不到 {p}")
    rows: list[dict] = []
    for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        try:
            row = json.loads(s)
        except json.JSONDecodeError as exc:
            raise DatasetError(f"{p} 第 {i} 行不是 JSON：{exc}") from exc
        if not isinstance(row, dict):
            raise DatasetError(f"{p} 第 {i} 行不是映射")
        rows.append(row)
    return rows


def checklist_items(path=CHECKLIST) -> dict[str, str]:
    """{清单项 id: 分栏} —— 权威来自 P1.3 的清单，这里不再抄一份。"""
    from review_contract import load_checklist       # 只在加载时用，避免顶层耦合
    contract = load_checklist(path)
    return {str(it["id"]): str(it["section"]) for it in contract["items"]}


def formula_version(prefix: str, payload) -> str:
    return prefix + "-" + hashlib.sha256(canon(payload).encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------- 索引

def validate_index(doc) -> list[str]:
    problems: list[str] = []
    if not isinstance(doc, dict):
        return ["数据集索引顶层不是映射"]
    if doc.get("schema") != SCHEMA:
        problems.append(f"schema 不是 {SCHEMA}")

    labelers = doc.get("labelers")
    if not isinstance(labelers, list):
        problems.append("labelers 必须是列表（可以是空的 —— 空表示还没人负责标注）")
    else:
        for x in labelers:
            if not isinstance(x, str) or not x.strip():
                problems.append(f"labelers 里有空名字：{x!r}")
        if len(set(labelers)) != len(labelers):
            problems.append("labelers 里有重名")

    versions = doc.get("label_versions")
    if not isinstance(versions, dict):
        problems.append("label_versions 必须是映射（版本 → 文件）")
        versions = {}
    for ver, meta in versions.items():
        if not _LABEL_VER_RE.match(str(ver)):
            problems.append(f"label_versions 的键 {ver!r} 不是 gcv1-<12 位> 形态")
        if not isinstance(meta, dict):
            problems.append(f"label_versions.{ver} 不是映射")
            continue
        f = str(meta.get("file") or "")
        if not f:
            problems.append(f"label_versions.{ver} 缺 file")
        elif _ABS_RE.match(f):
            problems.append(f"label_versions.{ver} 的 file 是绝对路径 —— "
                            f"标签文件只记数据集目录下的相对路径")
        if not _DATE_RE.match(str(meta.get("frozen_at") or "")):
            problems.append(f"label_versions.{ver} 的 frozen_at 必须是 YYYY-MM-DD")

    active = doc.get("active_label_version")
    if active is not None:
        if not _LABEL_VER_RE.match(str(active)):
            problems.append(f"active_label_version={active!r} 不是 gcv1-<12 位> 形态")
        elif str(active) not in versions:
            problems.append(f"active_label_version={active} 不在 label_versions 里 —— "
                            f"指向了一份不存在（或没登记）的标签")
    return problems


def load_index(path=INDEX) -> dict:
    p = Path(path)
    if not p.exists():
        raise DatasetError(f"找不到数据集索引：{p}")
    doc = json.loads(p.read_text(encoding="utf-8"))
    problems = validate_index(doc)
    if problems:
        raise DatasetError("数据集索引不合法：\n  - " + "\n  - ".join(problems))
    return doc


# ---------------------------------------------------------------- 登记条目

def validate_entry(i: int, e, known_items: set[str]) -> list[str]:
    problems: list[str] = []
    eid = e.get("entry_id") if isinstance(e, dict) else None
    where = f"manifest[{i}]" + (f"({eid})" if eid else "")
    if not isinstance(e, dict):
        return [f"{where} 不是映射"]
    if not isinstance(eid, str) or not _ENTRY_RE.match(eid):
        problems.append(f"{where} 的 entry_id 必须是 GC-NNNN")

    case_class = e.get("case_class")
    if case_class not in CASE_CLASSES:
        problems.append(f"{where} 的 case_class={case_class!r} 不在 {list(CASE_CLASSES)}")
    if e.get("source_kind") not in SOURCE_KINDS:
        problems.append(f"{where} 的 source_kind={e.get('source_kind')!r} "
                        f"不在 {list(SOURCE_KINDS)}")
    if not str(e.get("design_note") or "").strip():
        problems.append(f"{where} 缺 design_note —— 为什么要有这条样本，得写出来")

    inputs = e.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        problems.append(f"{where} 的 inputs 必须是非空列表")
        inputs = []
    kinds_seen: set[str] = set()
    for j, inp in enumerate(inputs):
        w = f"{where}.inputs[{j}]"
        if not isinstance(inp, dict):
            problems.append(f"{w} 不是映射")
            continue
        kind = inp.get("kind")
        if kind not in INPUT_KINDS:
            problems.append(f"{w} 的 kind={kind!r} 不在 {list(INPUT_KINDS)}")
        else:
            kinds_seen.add(str(kind))
        ref = str(inp.get("ref") or "")
        if not ref:
            problems.append(f"{w} 缺 ref")
        elif _ABS_RE.match(ref):
            problems.append(f"{w} 的 ref 是绝对路径 —— 数据集只记项目内相对路径")
        if not _HASH_RE.match(str(inp.get("sha256") or "")):
            problems.append(f"{w} 的 sha256 必须是 64 位小写十六进制")
    if "product_facts_source" not in kinds_seen:
        problems.append(f"{where} 没有 product_facts_source 输入 —— 没有事实就绑不出 "
                        f"FactsVersion，这条样本也就没法和任何一版商品事实对上")

    if not _FACTS_VER_RE.match(str(e.get("facts_version") or "")):
        problems.append(f"{where} 的 facts_version={e.get('facts_version')!r} "
                        f"不是 pfv1-<12 位>")

    ex = e.get("exercised_items")
    if not isinstance(ex, list):
        problems.append(f"{where} 的 exercised_items 必须是列表（可以空）")
        ex = []
    for it in ex:
        if it not in known_items:
            problems.append(f"{where} 的 exercised_items 里有清单里没有的项：{it!r}")
    if case_class == "critical_error" and not ex:
        problems.append(f"{where} 是明显关键错误样本，却没写 exercised_items —— "
                        f"没写清考的是哪条，就证明不了「这类错误有反例」")
    return problems


def load_manifest(path=MANIFEST, *, known_items=None) -> list[dict]:
    known = set(known_items) if known_items is not None else set(checklist_items())
    rows = read_jsonl(path)
    problems: list[str] = []
    seen: set[str] = set()
    for i, e in enumerate(rows):
        problems.extend(validate_entry(i, e, known))
        eid = e.get("entry_id") if isinstance(e, dict) else None
        if isinstance(eid, str):
            if eid in seen:
                problems.append(f"entry_id 重复：{eid} —— 一条样本只能有一条登记")
            seen.add(eid)
    if problems:
        raise DatasetError("数据集登记不合法：\n  - " + "\n  - ".join(problems))
    return rows


# ---------------------------------------------------------------- 标签

def validate_label(i: int, l, known_items: set[str]) -> list[str]:
    problems: list[str] = []
    if not isinstance(l, dict):
        return [f"labels[{i}] 不是映射"]
    eid = l.get("entry_id")
    where = f"labels[{i}]" + (f"({eid})" if eid else "")
    if not isinstance(eid, str) or not _ENTRY_RE.match(eid):
        problems.append(f"{where} 的 entry_id 必须是 GC-NNNN")
    if l.get("verdict") not in VERDICTS:
        problems.append(f"{where} 的 verdict={l.get('verdict')!r} 不在 {list(VERDICTS)}")
    fi = l.get("failed_items")
    if not isinstance(fi, list):
        problems.append(f"{where} 的 failed_items 必须是列表（可以空）")
        fi = []
    for it in fi:
        if it not in known_items:
            problems.append(f"{where} 的 failed_items 里有清单里没有的项：{it!r}")
    if l.get("verdict") == "reject" and not fi:
        problems.append(f"{where} 判了 reject 却没写 failed_items —— "
                        f"拒了却不知道拒在哪条，这条就进不了覆盖统计")
    lab = l.get("labeler")
    if lab is not None and (not isinstance(lab, str) or not lab.strip()):
        problems.append(f"{where} 的 labeler 要么写一个名字，要么写 null（待标注）")
    if lab is not None and not _DATE_RE.match(str(l.get("labeled_at") or "")):
        problems.append(f"{where} 有标签人却没有 labeled_at（YYYY-MM-DD）")
    return problems


def labels_version(entries) -> str:
    """标签版本的唯一取法：按内容算 —— 所以"改标签"必然得到一个新版本号。"""
    rows = sorted(entries, key=lambda r: (str(r.get("entry_id")), canon(r)))
    return formula_version("gcv1", rows)


def load_labels(path, *, known_items=None, declared_version: str | None = None) -> list[dict]:
    known = set(known_items) if known_items is not None else set(checklist_items())
    rows = read_jsonl(path)
    problems: list[str] = []
    for i, l in enumerate(rows):
        problems.extend(validate_label(i, l, known))
    if problems:
        raise DatasetError(f"{path} 不合法：\n  - " + "\n  - ".join(problems))
    if declared_version is not None:
        live = labels_version(rows)
        if live != declared_version:
            raise DatasetError(
                f"{path} 的内容算出来是 {live}，而 dataset.json 登记的是 {declared_version} —— "
                f"这份标签被就地改过。改标签要新增一版（跑 tools/freeze_dataset_labels.py），"
                f"不是覆盖旧的那一版：交付追溯要回答「当时哪一版标签判的」。")
    return rows


# ---------------------------------------------------------------- 绑定输入

def compute_facts(refs, *, root=ROOT, brand=BRAND, policy=POLICY) -> tuple[dict, list[str]]:
    """现场把登记里的输入算成 ProductFacts —— 版本号不许人手抄，抄的迟早会和输入脱钩。

    多份来源走 `product_facts.merge_bundles`：值不同就 conflicted（值置空、两边留证），
    所以"两份资料打架"这条路径也会在这里被真的走一遍。
    """
    import product_facts as pf
    import data_policy as dp
    import yaml
    fw, foi = pf.load_forbidden(brand)
    pver = dp.policy_version(yaml.safe_load(Path(policy).read_text(encoding="utf-8")))
    bundles = [pf.facts_from_product(pf.load_product(Path(root) / ref), source_path=ref,
                                     forbidden_words=fw, forbidden_on_image=foi,
                                     data_policy_version=pver)
               for ref in refs]
    merged = pf.merge_bundles(*bundles) if len(bundles) > 1 else bundles[0]
    return merged, pf.validate_bundle(merged)


def compute_facts_version(refs, *, root=ROOT, brand=BRAND, policy=POLICY) -> str:
    return str(compute_facts(refs, root=root, brand=brand, policy=policy)[0]["facts_version"])


def bind_entry(entry: dict, *, root=ROOT, brand=BRAND, policy=POLICY) -> dict:
    """把一条登记绑回真实文件：输入在不在、哈希对不对、FactsVersion 对不对。

    三种结果分开报，因为后果不同：
        ok            绑上了，这条样本可以参与统计
        pending_input 输入还没到位（活还没干到，不是文件写错）
        mismatch      输入变了或版本号对不上（这才是"写错了"）
    """
    reasons: list[str] = []
    status = "ok"
    refs: list[str] = []
    for inp in entry.get("inputs") or []:
        ref = str(inp.get("ref") or "")
        p = Path(root) / ref
        if not p.exists():
            status = _worse(status, "pending_input")
            reasons.append(f"输入不存在：{ref}")
            continue
        if inp.get("kind") == "product_facts_source":
            refs.append(ref)
        if sha256_file(p) != inp.get("sha256"):
            status = _worse(status, "mismatch")
            reasons.append(f"输入哈希对不上（内容变了，或哈希没跟着改）：{ref}")
    live = None
    if refs:
        try:
            merged, bad = compute_facts(refs, root=root, brand=brand, policy=policy)
            live = str(merged["facts_version"])
        except Exception as exc:                       # noqa: BLE001
            return {"status": "mismatch", "facts_version": None,
                    "reasons": reasons + [f"算不出 FactsVersion：{exc}"]}
        if bad:
            status = _worse(status, "mismatch")
            reasons.append("算出来的事实本身不合法：" + "；".join(bad))
        if live != entry.get("facts_version"):
            status = _worse(status, "mismatch")
            reasons.append(f"FactsVersion 对不上：登记 {entry.get('facts_version')}，"
                           f"现场算出来 {live}")
    return {"status": status, "reasons": reasons, "facts_version": live}


def _worse(a: str, b: str) -> str:
    return a if _BIND_RANK[a] >= _BIND_RANK[b] else b


# ---------------------------------------------------------------- 审计

def dataset_version(manifest, active: str | None) -> str:
    return formula_version("gcd1", {
        "entries": sorted(manifest, key=lambda e: str(e.get("entry_id"))),
        "labels": active})


def audit(*, dataset_dir=DATASET_DIR, root=ROOT, brand=BRAND, policy=POLICY,
          checklist_path=CHECKLIST) -> dict:
    """一次加载，把绑定 / 待标注 / 冲突 / 覆盖四件事都算出来。只读。"""
    base = Path(dataset_dir)
    known = checklist_items(checklist_path)
    index = load_index(base / "dataset.json")
    manifest = load_manifest(base / "manifest.jsonl", known_items=set(known))

    active = index.get("active_label_version")
    labels: list[dict] = []
    if active:
        meta = index["label_versions"][str(active)]
        labels = load_labels(base / str(meta["file"]), known_items=set(known),
                             declared_version=str(active))
    labelers = {str(x) for x in (index.get("labelers") or [])}
    critical = [i for i, s in known.items() if s == "critical_fact"]

    coverage = {i: {"pos": 0, "neg": 0} for i in critical}
    class_counts = {c: 0 for c in CASE_CLASSES}
    bound: list[dict] = []
    pending: list[dict] = []
    conflicts: list[dict] = []
    unattributed: list[dict] = []
    unexpected: list[dict] = []
    rows: list[dict] = []

    for e in manifest:
        eid = str(e["entry_id"])
        b = bind_entry(e, root=root, brand=brand, policy=policy)
        bound.append({"entry_id": eid, **b})
        mine = [l for l in labels if str(l.get("entry_id")) == eid]
        attributed = [l for l in mine if l.get("labeler") in labelers]
        distinct = {canon({"verdict": l.get("verdict"),
                           "failed_items": sorted(l.get("failed_items") or [])})
                    for l in mine}
        row = {"entry_id": eid, "case_class": e["case_class"],
               "source_kind": e["source_kind"], "bind": b["status"]}
        if len(distinct) > 1:
            conflicts.append({"entry_id": eid, "labels": mine})
            row["status"] = "conflicted"
        elif not attributed:
            why = ("还没贴标签" if not mine else
                   f"贴了 {len(mine)} 条，但标签人不在 dataset.json 的 labelers 里")
            if not mine:
                why = "还没贴标签"
            unattributed.append({"entry_id": eid, "why": why})
            row["status"] = "unattributed"
        elif b["status"] != "ok":
            pending.append({"entry_id": eid, "why": "；".join(b["reasons"])})
            row["status"] = "not_bound"
        elif e.get("source_kind") != COUNTING_SOURCE_KIND:
            pending.append({"entry_id": eid,
                            "why": f"source_kind={e['source_kind']}：样例不计数"})
            row["status"] = "sample"
        else:
            lab = attributed[0]
            class_counts[str(e["case_class"])] += 1
            row["status"] = "counted"
            if lab.get("verdict") == "accept":
                for it in e.get("exercised_items") or []:
                    if it in coverage:
                        coverage[it]["pos"] += 1
            for it in lab.get("failed_items") or []:
                if it in coverage:
                    coverage[it]["neg"] += 1
            extra = [it for it in (lab.get("failed_items") or [])
                     if it not in (e.get("exercised_items") or [])]
            if extra:
                unexpected.append({"entry_id": eid, "items": extra})
        rows.append(row)

    gaps = [i for i in critical if coverage[i]["pos"] == 0 or coverage[i]["neg"] == 0]

    # 草稿（labels/_working.jsonl）：给人看的待标注清单。它**不是**标签，
    # 所以不参与任何统计；列出来只是为了让"还差谁签字"有一个具体名字。
    draft_rows: list[dict] = []
    draft_path = base / "labels" / "_working.jsonl"
    if draft_path.exists():
        try:
            draft_rows = read_jsonl(draft_path)
        except DatasetError:
            draft_rows = []

    return {
        "schema": SCHEMA,
        "draft": {
            "count": len(draft_rows),
            "without_labeler": [str(d.get("entry_id")) for d in draft_rows
                                if not d.get("labeler")],
        },
        "dataset_dir": str(base),
        "dataset_version": dataset_version(manifest, str(active) if active else None),
        "active_label_version": active,
        "label_version_computed": labels_version(labels) if labels else None,
        "labelers": sorted(labelers),
        "counts": {
            "entries": len(manifest),
            "counted": sum(1 for r in rows if r["status"] == "counted"),
            "by_class": {c: sum(1 for e in manifest if e["case_class"] == c)
                         for c in CASE_CLASSES},
            "by_source": {s: sum(1 for e in manifest if e["source_kind"] == s)
                          for s in SOURCE_KINDS},
        },
        "entries": rows,
        "bound": bound,
        "pending": pending,
        "conflicts": conflicts,
        "unattributed": unattributed,
        "unexpected_failures": unexpected,
        "critical_items": critical,
        "coverage": coverage,
        "coverage_gaps": gaps,
        "class_gaps": [c for c in CASE_CLASSES if class_counts[c] == 0],
    }


def ready(report: dict) -> list[str]:
    """门禁判据：还差什么才能说"这份数据集够用了"。空列表 = 齐了。"""
    out: list[str] = []
    if not report["counts"]["counted"]:
        out.append("没有任何一条样本进入统计（真实试点输入 + 登记在案的标签人，两样都要有）")
    for c in report["class_gaps"]:
        out.append(f"没有可计数的 {c} 类样本")
    for c in report["conflicts"]:
        out.append(f"{c['entry_id']} 上有多条互相矛盾的标签，没人裁决")
    for c in report["pending"]:
        out.append(f"{c['entry_id']} 没绑上：{c['why']}")
    for i in report["coverage_gaps"]:
        pos = report["coverage"][i]["pos"]
        neg = report["coverage"][i]["neg"]
        out.append(f"{i} 的正反例不全（正例 {pos} / 负例 {neg}）")
    return out