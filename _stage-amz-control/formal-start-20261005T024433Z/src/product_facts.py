#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""ProductFacts v1 —— 把运营填的 product.json 变成"带类型、单位、来源、确认者"的事实。

这一层要回答的不是"图好不好看"，而是**图上那句话是从哪来的、谁确认过**。
所以它刻意做三件 v2 里没有的事：

    ① 数值与单位分开：`500ml` / `0.5L` / `500 毫升` 必须归一到同一个 `(500.0, ml)`；
    ② 每条事实带 `source`（原文路径）与 `confirmer`，默认 `confirmer=null` +
       `unconfirmed` —— `product.json` 里那份整单签字签的是**素材条件**
       （no_watermark / no_props / single_subject / angle_ok / font_license /
       competitor_clean），不是商品事实，拿它当事实确认就是假权威；
    ③ 冲突不许被"最后一个值"覆盖：同一个 id 从两处得到不同值 → `state=conflicted`、
       `value=None`、两条原始记录都留在 `conflicts` 里，下游只能拒，不能挑一个。

只做加法：本模块**不修改**传入的 product，也不参与 v2 planner 的输入语义
（`src/assets.py` 仍按原样把 bullets / specs 当文本素材读）。

口径（P1.1 开工前已定，见 `docs/product-v1-goal-and-implementation-plan.md` 的 Phase 1 任务卡）：
    单位      归一到 ml / g / cm；大小写与空格不参与比较；`raw` 保原串
    来源      形如 `examples/product_fullset.json#specs.容量`；缺失也留一条 `missing`
    确认者    默认 null；只有 P1.3 的清单 / Phase 6 界面才写 `confirmer`
    键域      specs 先按闭集（SPEC_KEYS），闭集外的键进 `extra.<键>` 且 `unit=null`
    卖点      同时受 `brand.forbidden_words`（文案禁用词）与 `forbidden_on_image`
              约束；命中即 `allowed_on_image=no`，并记下命中哪一份清单的哪个词
    授权      `data_policy_version` 只**引用** P1.2 的 policy，不内嵌授权语义
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SCHEMA = "amz-listing-kit/product-facts@1"

# 闭集：specs 里认得的键 → (事实 id, 类型, 规范单位)。
# 位置说明：类目级的规格键以后应该搬到 config/catalog/<类目>.yaml（README §4 的表驱动原则）；
# 现在 v2 的 catalog 里还没有 specs 段，所以先放在这里，P1.4 登记试点品类时一起搬。
SPEC_KEYS: dict[str, tuple[str, str, str | None]] = {
    "容量": ("spec.capacity", "quantity", "ml"),
    "材质": ("spec.material", "text", None),
    "重量": ("spec.weight", "quantity", "g"),
    "高度": ("spec.height", "quantity", "cm"),
    "宽度": ("spec.width", "quantity", "cm"),
}

# 单位别名 → (规范单位, 到规范单位的乘数)
UNIT_ALIASES: dict[str, tuple[str, float]] = {
    "ml": ("ml", 1.0), "毫升": ("ml", 1.0), "l": ("ml", 1000.0), "升": ("ml", 1000.0),
    "g": ("g", 1.0), "克": ("g", 1.0), "kg": ("g", 1000.0), "千克": ("g", 1000.0),
    "cm": ("cm", 1.0), "厘米": ("cm", 1.0), "mm": ("cm", 0.1), "毫米": ("cm", 0.1),
    "m": ("cm", 100.0), "米": ("cm", 100.0),
}

_NUM_UNIT = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z\u4e00-\u9fa5]+)\s*$")
_ID_RE = re.compile(r"^(spec|claim|extra)\.\S+$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_VERSION_RE = re.compile(r"^pfv1-[0-9a-f]{12}$")
STATES = ("unconfirmed", "confirmed", "missing", "unknown", "conflicted")
KINDS = ("quantity", "text", "claim")


# ---------------------------------------------------------------- 解析

def parse_quantity(raw: str, expect_unit: str | None) -> tuple[float, str] | None:
    """`500ml` / `0.5 L` / `22 cm` → (规范数值, 规范单位)；解析不了或单位与预期不符返回 None。"""
    m = _NUM_UNIT.match(raw or "")
    if not m:
        return None
    hit = UNIT_ALIASES.get(m.group(2).lower())
    if not hit:
        return None
    canon, factor = hit
    if expect_unit and canon != expect_unit:
        return None
    return round(float(m.group(1)) * factor, 6), canon


def _source_ref(source_path: str, key: str) -> str:
    return f"{source_path}#{key}"


def _fact(fid: str, kind: str, value, unit, raw, source: str,
          state: str = "unconfirmed", conflicts=None, **extra) -> dict:
    fact = {
        "id": fid, "kind": kind, "value": value, "unit": unit, "raw": raw,
        "source": source, "confirmer": None, "state": state,
        "allowed_on_image": "unjudged", "conflicts": list(conflicts or []),
    }
    fact.update(extra)
    return fact


def _claim_fact(fid: str, raw: str, source: str,
                forbidden_words=(), forbidden_on_image=()) -> dict:
    hits = ([{"word": str(w), "list": "forbidden_words"} for w in forbidden_words
             if w and str(w).lower() in raw.lower()]
            + [{"word": str(w), "list": "forbidden_on_image"} for w in forbidden_on_image
               if w and str(w).lower() in raw.lower()])
    fact = _fact(fid, "claim", raw, None, raw, source)
    if hits:
        fact["allowed_on_image"] = "no"
        fact["forbidden_hits"] = hits
    return fact


# ---------------------------------------------------------------- 适配器（只读）

def facts_from_product(product: dict, *, source_path: str,
                       forbidden_words=(), forbidden_on_image=(),
                       data_policy_version: str | None = None) -> dict:
    """把一份 product.json 读成 ProductFacts。**不修改 product。**"""
    if not isinstance(product, dict):
        raise TypeError("product 必须是 dict")
    facts: list[dict] = []
    specs = product.get("specs") or {}

    for key, (fid, kind, unit) in SPEC_KEYS.items():
        ref = _source_ref(source_path, f"specs.{key}")
        raw = specs.get(key)
        if raw in (None, ""):
            facts.append(_fact(fid, kind, None, None, None, ref, state="missing"))
            continue
        parsed = parse_quantity(str(raw), unit) if kind == "quantity" else None
        if kind != "quantity":
            facts.append(_fact(fid, "text", str(raw), None, str(raw), ref))
        elif parsed is None:
            facts.append(_fact(fid, "quantity", None, None, str(raw), ref, state="unknown"))
        else:
            value, canon = parsed
            facts.append(_fact(fid, "quantity", value, canon, str(raw), ref))

    for key in sorted(specs):
        if key in SPEC_KEYS or specs[key] in (None, ""):
            continue
        facts.append(_fact(f"extra.{key}", "text", str(specs[key]), None,
                           str(specs[key]), _source_ref(source_path, f"specs.{key}")))

    for i, bullet in enumerate(product.get("bullets") or [], 1):
        facts.append(_claim_fact(f"claim.bullet_{i}", str(bullet),
                                 _source_ref(source_path, f"bullets[{i - 1}]"),
                                 forbidden_words, forbidden_on_image))
    if product.get("title"):
        facts.append(_claim_fact("claim.title", str(product["title"]),
                                 _source_ref(source_path, "title"),
                                 forbidden_words, forbidden_on_image))

    return _bundle(source_path, product.get("upc"), product.get("attest"),
                   facts, data_policy_version)


def _bundle(source_path: str, upc, attest, facts: list[dict],
            data_policy_version: str | None) -> dict:
    facts = sorted(facts, key=lambda f: f["id"])
    bundle = {
        "schema": SCHEMA,
        "source": {"path": source_path, "upc": upc, "claimed_attest": attest},
        "facts": facts,
        "data_policy_version": data_policy_version,
        "confirmer_note": ("confirmer=null 表示这条事实还没有人确认；product.json 的 "
                           "attest 签的是素材条件，不是事实。"),
    }
    bundle["facts_hash"] = facts_hash(facts)
    bundle["facts_version"] = "pfv1-" + bundle["facts_hash"][:12]
    return bundle


# ---------------------------------------------------------------- 合并与冲突

def merge_bundles(*bundles: dict) -> dict:
    """把同一 SKU 的多份来源合成一份。同 id 值相同 → 合并来源；值不同 → conflicted 且值置空。

    "值相同"是在**归一之后**比较的：`500ml` 与 `0.5L` 都归一到 `(500.0, ml)`，不算冲突。
    """
    by_id: dict[str, list[tuple[str, dict]]] = {}
    for bundle in bundles:
        for fact in bundle["facts"]:
            by_id.setdefault(fact["id"], []).append((bundle["source"]["path"], fact))

    merged: list[dict] = []
    for fid in sorted(by_id):
        items = by_id[fid]
        present = [(src, f) for src, f in items if f["state"] != "missing"]
        if not present:                       # 每份都缺 → 就是 missing
            merged.append(items[0][1])
            continue
        if len(present) == 1:                 # 只有一份有值 → 用它，但记下"还有一份是缺的"
            fact = dict(present[0][1])
            fact["sources_all"] = [f["source"] for _, f in items]
            merged.append(fact)
            continue
        values = {(f["value"], f["unit"]) for _, f in present}
        if len(values) == 1:                  # 归一后一致 → 合并，保留每个来源
            fact = dict(present[0][1])
            fact["sources_all"] = [f["source"] for _, f in present]
            merged.append(fact)
            continue
        merged.append({                       # 分歧 → 值置空，两边都留证
            "id": fid, "kind": present[0][1]["kind"], "value": None,
            "unit": present[0][1]["unit"], "raw": None,
            "source": present[0][1]["source"], "confirmer": None, "state": "conflicted",
            "allowed_on_image": "unjudged",
            "conflicts": [{"source": f["source"], "value": f["value"], "unit": f["unit"],
                           "raw": f["raw"], "state": f["state"]}
                          for _, f in items],
        })

    paths = [b["source"]["path"] for b in bundles]
    upcs = [b["source"]["upc"] for b in bundles]
    return _bundle(" + ".join(paths), upcs[0] if len(set(upcs)) == 1 else None,
                   None, merged, bundles[0]["data_policy_version"])


# ---------------------------------------------------------------- 哈希与校验

def facts_hash(facts: list[dict]) -> str:
    """规范化序列化后取哈希：按 id 排序 + 键排序，所以字段顺序不影响结果。"""
    canon = json.dumps(sorted(facts, key=lambda f: f["id"]),
                       ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def validate_bundle(bundle: dict) -> list[str]:
    """不依赖 jsonschema 的轻量校验：够拦住"字段缺了/单位乱写/冲突被抹平"这三类。"""
    problems: list[str] = []
    for key in ("schema", "facts_version", "facts_hash", "source", "facts", "data_policy_version"):
        if key not in bundle:
            problems.append(f"缺顶层键 {key}")
    if bundle.get("schema") != SCHEMA:
        problems.append(f"schema 不是 {SCHEMA}")
    facts = bundle.get("facts")
    if not isinstance(facts, list):
        return problems + ["facts 不是列表"]
    ids = [f.get("id") for f in facts]
    if ids != sorted(ids):
        problems.append("facts 没有按 id 排序")
    if len(set(ids)) != len(ids):
        problems.append("facts 里同一个 id 出现多次 —— 冲突必须在合并时就折叠")
    for f in facts:
        where = f.get("id")
        for key in ("id", "kind", "value", "unit", "raw", "source", "confirmer",
                    "state", "allowed_on_image", "conflicts"):
            if key not in f:
                problems.append(f"{where} 缺字段 {key}")
        if not _ID_RE.match(str(where)):
            problems.append(f"{where} 的 id 形态不合法")
        if f.get("kind") not in KINDS:
            problems.append(f"{where} 的 kind={f.get('kind')!r} 不在取值域")
        if f.get("state") not in STATES:
            problems.append(f"{where} 的 state={f.get('state')!r} 不在取值域")
        if f.get("state") == "conflicted":
            if f.get("value") is not None:
                problems.append(f"{where} 是 conflicted，但 value 不是 null —— 冲突被挑了一个值")
            if not f.get("conflicts"):
                problems.append(f"{where} 是 conflicted，但 conflicts 是空的")
        elif f.get("conflicts"):
            problems.append(f"{where} 不是 conflicted，却带着 conflicts")
        if f.get("kind") != "quantity" and f.get("unit") is not None:
            problems.append(f"{where} 不是 quantity，unit 必须为 null")
        if f.get("kind") == "quantity" and f.get("unit") not in (None, "ml", "g", "cm"):
            problems.append(f"{where} 的 unit={f.get('unit')!r} 没归一到 ml/g/cm")
        if f.get("confirmer") is not None:
            problems.append(f"{where} 的 confirmer 非空 —— 事实确认只能由 P1.3/Phase 6 写")
    if isinstance(facts, list):
        want = facts_hash(facts)
        if bundle.get("facts_hash") != want:
            problems.append("facts_hash 与当前 facts 不一致（被改过？）")
        if bundle.get("facts_version") != "pfv1-" + want[:12]:
            problems.append("facts_version 与 facts_hash 前 12 位对不上")
    return problems


# ---------------------------------------------------------------- 读盘

def load_product(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_forbidden(brand_path: str | Path) -> tuple[list[str], list[str]]:
    brand = json.loads(Path(brand_path).read_text(encoding="utf-8"))
    return list(brand.get("forbidden_words") or []), list(brand.get("forbidden_on_image") or [])