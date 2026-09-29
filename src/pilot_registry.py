#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""Pilot Registry v1 —— 20-SKU 试点登记，以及「样本够不够」这道门。

它回答一个问题：**凭哪些真实样本来证明这个产品可用。** 计划 §3 的三条指标
（品类覆盖、双操作员、首 5 个校准集）全部从这份登记表算出来，所以它是试点样本的
唯一权威 —— 别处再抄一份样本清单，就有两份会各自漂。

四条取舍（每条都有反向样本，见 `tools/verify_p1_4_registry.py`）：

  ① **样例不计数**。`sample: true` 的条目一律排除在 20 之外 —— 拿样例凑数，
     等于把"用真实样本证明过"降级成"我摆够了行数"。
  ② **状态算出来，写不了**。条目缺事实版本 / 缺授权版本 / 素材不全 → 自动 `not-ready`，
     而且**不参与**品类与操作员的配额计算。想让它算数，只有把缺的补上。
  ③ **批次由顺序定**。order 1–5 是校准集（用来测量并冻结成本/时间上限），
     6–20 是正式批；写反了直接报错。
  ④ **版本与素材要现场核**。`facts_version` / `data_policy_version` / `assets[].sha256`
     光有合法形态不算数 —— `resolve()` 会对着真实输入把它们**重新算一遍**。
     三种结果分开报：在（`ok`）/ 还没放（`pending_input`）/ 对不上（`mismatch`）。
     没有这一条，随手写一个格式合法的版本号就能把门变绿，那是假绿通道。

不做的事：
    不在这里放原图（只留受控目录下的相对路径 + sha256）；
    不在这里放商品身份（id 是匿名编号，出现 UPC / ASIN / 标题 / 价格 / 链接就报错）；
    不在这里放姓名工号（操作员是匿名编号）。

门禁入口是 `tools/check_pilot_ready.py`：清单不齐时它就该红，那是实话。
"""
from __future__ import annotations

import copy
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "pilot-registry/v1"
DEFAULT_PATH = ROOT / "pilot" / "pilot-registry.yaml"

# 目标数字的唯一出处是计划 §3 的成功指标表（20 个试点任务 / ≥2 品类、每类 ≥5 /
# 2 名操作员各 ≥5）与 §3.2（首 5 个 SKU 是校准集）。这里只把它们变成可校验的常量。
TOTAL_TARGET = 20
MIN_CATEGORIES = 2
MIN_PER_CATEGORY = 5
MIN_OPERATORS = 2
MIN_PER_OPERATOR = 5
CALIBRATION_ORDERS = (1, 2, 3, 4, 5)
BATCHES = ("calibration", "official")

# 落点约定（计划 §P1.4 口径表「素材放在哪」那一行）：
#   素材   materials/<SKU 匿名编号>/<kind>.<ext>     例：materials/SKU-01/front.jpg
#   事实   materials/<SKU 匿名编号>/product.json    —— 这个 SKU 的 ProductFacts 输入
# 只用 id 推路径、不另开字段：素材本来就要放进这个目录，事实来源放同一处就不用再抄一遍。
MATERIALS_DIRNAME = "materials"
FACTS_SOURCE_NAME = "product.json"

# 现场核对的三种结果：在 / 还没放 / 对不上。前两种是"活还没干到"，第三种要人查。
STATUS_OK = "ok"
STATUS_PENDING = "pending_input"
STATUS_MISMATCH = "mismatch"

_ID_RE = re.compile(r"^SKU-\d{2,}$")
_OP_RE = re.compile(r"^OP-[A-Z0-9]{1,8}$")
_CAT_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_FACTS_RE = re.compile(r"^pfv1-[0-9a-f]{12}$")
_POLICY_RE = re.compile(r"^dpv1-[0-9a-f]{12}$")
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
# 匿名化：这些键一旦出现，就是把商品身份写进了登记表
_FORBIDDEN_KEYS = ("upc", "asin", "gtin", "ean", "title", "price", "url",
                   "brand", "brand_name", "seller", "store")


class RegistryError(Exception):
    """登记表本身不合法（写错了）—— 与"样本还没齐"是两回事，所以用不同的异常。"""


class PilotNotReady(Exception):
    """样本还没齐。

    它**不是技术失败**：这是门正常工作的结果。调用方（G1 门禁、界面）应当把
    `.summary["problems"]` 原样交给要补数据的人，而不是重试或先算上。
    """

    def __init__(self, summary: dict) -> None:
        super().__init__("试点样本还没齐：" + "；".join(summary.get("problems") or []))
        self.summary = summary


# ------------------------------------------------------------------ 校验

def validate_registry(reg) -> list[str]:
    """结构校验：够拦住"身份没匿名 / 素材没哈希 / 批次写反 / id 重复"这几类。"""
    problems: list[str] = []
    if not isinstance(reg, dict):
        return ["顶层不是映射"]
    if reg.get("schema") != SCHEMA:
        problems.append(f"schema 不是 {SCHEMA}")

    ops = reg.get("operators")
    if not isinstance(ops, list):
        problems.append("operators 必须是列表（哪怕还没填）")
        ops = []
    op_ids: set[str] = set()
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            problems.append(f"operators[{i}] 不是映射")
            continue
        oid = str(op.get("id") or "")
        if not _OP_RE.match(oid):
            problems.append(f"operators[{i}] 的 id={oid!r} 不是匿名编号（形如 OP-A）—— "
                            f"姓名和工号留在受控名单里")
        elif oid in op_ids:
            problems.append(f"operators[{i}] 的 id 重复：{oid}")
        else:
            op_ids.add(oid)
        tt = op.get("tasks_target")
        if tt is not None and (not isinstance(tt, int) or tt <= 0):
            problems.append(f"operators[{i}] 的 tasks_target 必须是正整数")

    entries = reg.get("entries")
    if not isinstance(entries, list):
        problems.append("entries 必须是列表（哪怕还没填）")
        entries = []
    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    for i, e in enumerate(entries):
        where = f"entries[{i}]" + (f"({e.get('id')})" if isinstance(e, dict) and e.get("id") else "")
        if not isinstance(e, dict):
            problems.append(f"{where} 不是映射")
            continue
        for key in _FORBIDDEN_KEYS:
            if key in e:
                problems.append(f"{where} 出现键 {key!r} —— 登记表只放匿名编号与素材引用，"
                                f"商品身份（UPC / ASIN / 标题 / 价格 / 链接）不入库")
        o = e.get("order")
        if not isinstance(o, int) or o <= 0:
            problems.append(f"{where} 的 order 必须是正整数（执行顺序就是批次依据）")
        elif o in seen_orders:
            problems.append(f"{where} 的 order 重复：{o}")
        else:
            seen_orders.add(o)
        eid = str(e.get("id") or "")
        if not _ID_RE.match(eid):
            problems.append(f"{where} 的 id={eid!r} 不是匿名编号（形如 SKU-01）")
        elif eid in seen_ids:
            problems.append(f"{where} 的 id 重复：{eid}")
        else:
            seen_ids.add(eid)
        cat = str(e.get("category") or "")
        if cat and not _CAT_RE.match(cat):
            problems.append(f"{where} 的 category={cat!r} 形态不合法（小写字母开头的标识）")
        batch = e.get("batch")
        if batch not in BATCHES:
            problems.append(f"{where} 的 batch={batch!r} 不在取值域 {BATCHES}")
        elif isinstance(o, int):
            want = "calibration" if o in CALIBRATION_ORDERS else "official"
            if batch != want:
                problems.append(f"{where} 的 batch={batch!r}，但 order={o} 属于 {want!r} —— "
                                f"首 5 个是校准集（计划 §3.2），顺序与批次不许打架")
        oper = e.get("operator")
        if oper is not None and str(oper) not in op_ids:
            problems.append(f"{where} 的 operator={oper!r} 不在 operators 里")
        fv = e.get("facts_version")
        if fv is not None and not _FACTS_RE.match(str(fv)):
            problems.append(f"{where} 的 facts_version={fv!r} 形态不合法（pfv1- + 12 位十六进制）")
        pv = e.get("data_policy_version")
        if pv is not None and not _POLICY_RE.match(str(pv)):
            problems.append(f"{where} 的 data_policy_version={pv!r} 形态不合法（dpv1- + 12 位十六进制）")
        assets = e.get("assets")
        if assets is not None and not isinstance(assets, list):
            problems.append(f"{where} 的 assets 必须是列表")
            assets = None
        for j, a in enumerate(assets or []):
            aw = f"{where}.assets[{j}]"
            if not isinstance(a, dict):
                problems.append(f"{aw} 不是映射")
                continue
            if a.get("kind") not in _image_kinds():
                problems.append(f"{aw} 的 kind={a.get('kind')!r} 不在 src/assets.py 的 "
                                f"IMAGE_KINDS 里：{list(_image_kinds())}")
            p = str(a.get("path") or "")
            if not p:
                problems.append(f"{aw} 缺 path")
            elif p.startswith(("/", "\\")) or ":" in p:
                problems.append(f"{aw} 的 path 是绝对路径 —— 登记表只留受控目录下的相对路径")
            if not _SHA_RE.match(str(a.get("sha256") or "")):
                problems.append(f"{aw} 的 sha256 不是 64 位小写十六进制 —— "
                                f"没有哈希就没法证明后来的图还是同一张")
        if e.get("sample") is not None and not isinstance(e.get("sample"), bool):
            problems.append(f"{where} 的 sample 只能是 true/false")
    if entries and isinstance(entries, list) and not problems:
        orders = sorted(seen_orders)
        if orders != list(range(1, len(entries) + 1)):
            problems.append(f"order 必须是 1..N 连续排下来，现在是 {orders} —— "
                            f"跳号会让『第几个做的』说不清")
    return problems


def _image_kinds() -> tuple[str, ...]:
    import assets                      # 素材类别的唯一权威
    return tuple(assets.IMAGE_KINDS)


# ------------------------------------------------------------------ 现场核对

def facts_ref(entry_or_id) -> str:
    """这个 SKU 的事实来源在哪 —— 走约定路径，不新增字段。"""
    eid = (entry_or_id if isinstance(entry_or_id, str)
           else str((entry_or_id or {}).get("id") or ""))
    return f"{MATERIALS_DIRNAME}/{eid}/{FACTS_SOURCE_NAME}"


def sha256_file(path: Path) -> str:
    """文件的 sha256。登记表里的素材哈希与 `tools/fill_pilot_registry.py` 都用它。"""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def facts_version_of(path: Path, source_ref: str, proj: Path) -> str:
    """现场把这一份输入算一遍。版本怎么算由 `src/product_facts.py` 说了算。

    核对器与补齐工具共用它 —— 两边各写一份算法，迟早算出两个版本号。
    """
    import product_facts
    brand = proj / "config" / "brand.json"
    fw, fi = product_facts.load_forbidden(brand) if brand.exists() else ((), ())
    bundle = product_facts.facts_from_product(
        product_facts.load_product(path), source_path=source_ref,
        forbidden_words=fw, forbidden_on_image=fi)
    return bundle["facts_version"]


def resolve_entry(entry: dict, *, root=None, policy=None,
                  policy_error: str | None = None) -> dict:
    """把一条登记对着**真实输入**核一遍。

    三种结果分开报，因为它们的下一步不是同一件事：

        在     ok            声明的东西真的在，版本与哈希都对得上
        还没放 pending_input 素材或事实来源还没到位 —— 这是"活还没干到"
        对不上 mismatch      文件在，但版本或哈希与声明不一致 —— 要人查（可能换了图）
    """
    proj = Path(root) if root else ROOT
    eid = str(entry.get("id") or "")
    pending: list[str] = []
    mismatch: list[str] = []
    checked = 0

    # ① 授权版本：全项目只有一份政策，对着活的那份核
    declared_policy = str(entry.get("data_policy_version") or "")
    if not declared_policy:
        pending.append("缺授权版本（P1.2）")
    elif policy is None:
        mismatch.append("授权文件读不出来，无法核对 data_policy_version"
                        + (f"（{policy_error}）" if policy_error else ""))
    else:
        checked += 1
        if declared_policy != policy.policy_version:
            mismatch.append(f"data_policy_version={declared_policy} 与当前授权文件算出来的 "
                            f"{policy.policy_version} 不一致 —— 批的不是这一版")

    # ② 事实版本：按约定路径把输入现场算一遍（手抄的版本号不算数）
    ref = facts_ref(eid)
    fpath = proj / ref
    declared_facts = str(entry.get("facts_version") or "")
    if not declared_facts:
        pending.append("缺事实版本（P1.1）")
    elif not fpath.exists():
        pending.append(f"事实来源还没放：{ref}")
    else:
        checked += 1
        try:
            live_facts = facts_version_of(fpath, ref, proj)
        except Exception as exc:                            # noqa: BLE001
            mismatch.append(f"事实来源读不出来（{type(exc).__name__}: {exc}）")
        else:
            if declared_facts != live_facts:
                mismatch.append(f"facts_version={declared_facts} 与 {ref} 算出来的 "
                                f"{live_facts} 不一致")

    # ③ 素材：路径要真的在，sha256 要真的对得上
    for j, a in enumerate(entry.get("assets") or []):
        if not isinstance(a, dict):
            continue
        rel = str(a.get("path") or "")
        declared_sha = str(a.get("sha256") or "")
        if not rel:
            pending.append(f"素材[{j}] 缺 path")
            continue
        fp = proj / rel
        if not fp.exists():
            pending.append(f"素材还没放：{rel}")
            continue
        checked += 1
        got = sha256_file(fp)
        if got != declared_sha:
            mismatch.append(f"素材 {rel} 的哈希与登记不符"
                            f"（登记 {declared_sha[:12]}… · 实际 {got[:12]}…）")

    if mismatch:
        status = STATUS_MISMATCH
    elif pending:
        status = STATUS_PENDING
    else:
        status = STATUS_OK
    return {"id": eid, "status": status,
            # ok 还要求真的核过至少一样东西 —— 空条目不许靠"没得核"变绿
            "ok": status == STATUS_OK and checked > 0,
            "checked": checked, "pending": pending, "mismatch": mismatch,
            "reasons": mismatch + pending}


def resolve(reg: dict, *, root=None, policy_path=None) -> dict:
    """把整份登记对着真实输入核一遍，并报出**有几条真的被核到了**。

    最后那个数（`any_input`）是防"空表判绿"的：一条输入都没提供时它必须是 0，
    调用方不许因为"没报错"就把结果当成绿。
    """
    import data_policy

    proj = Path(root) if root else ROOT
    pol_path = (Path(policy_path) if policy_path
                else (proj / "contracts" / "data-policy-v1.yaml"))
    policy, policy_error = None, None
    try:
        policy = data_policy.load_policy(pol_path)
    except data_policy.PolicyError as exc:
        policy_error = str(exc)

    per: dict[str, dict] = {}
    for e in (reg.get("entries") or []):
        if isinstance(e, dict):
            per[str(e.get("id"))] = resolve_entry(e, root=proj, policy=policy,
                                                  policy_error=policy_error)
    counts = {STATUS_OK: 0, STATUS_PENDING: 0, STATUS_MISMATCH: 0}
    for r in per.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {
        "root": str(proj),
        "policy_version": (policy.policy_version if policy is not None else None),
        "policy_signed": bool(policy is not None and policy.signed_by),
        "policy_error": policy_error,
        "entries": per,
        "counts": counts,
        "any_input": sum(1 for r in per.values() if r["checked"] > 0),
    }


# ------------------------------------------------------------------ 读盘与判据

def load_registry(path: str | Path | None = None) -> dict:
    import yaml
    p = Path(path) if path else DEFAULT_PATH
    if not p.exists():
        raise RegistryError(f"找不到试点登记表：{p}")
    reg = yaml.safe_load(p.read_text(encoding="utf-8"))
    problems = validate_registry(reg)
    if problems:
        raise RegistryError("试点登记表不合法：\n  - " + "\n  - ".join(problems))
    return reg


def classify(entry: dict) -> tuple[bool, list[str]]:
    """一条样本现在算不算数。缺什么，就说什么 —— 不给"大概能跑"的余地。"""
    missing: list[str] = []
    if not entry.get("facts_version"):
        missing.append("缺事实版本（P1.1）")
    if not entry.get("data_policy_version"):
        missing.append("缺授权版本（P1.2）")
    if not (entry.get("assets") or []):
        missing.append("缺素材清单")
    if not str(entry.get("category") or "").strip():
        missing.append("缺品类")
    if not str(entry.get("operator") or "").strip():
        missing.append("缺操作员分配")
    return (not missing), missing


def summarize(reg: dict, *, resolution: dict | None = None) -> dict:
    """门禁要看的那几个数：只算**真实且 ready** 的条目。

    给了 `resolution`（`resolve()` 的结果）时，ready 还要过现场核对那一关：
    版本算不对、素材对不上、素材还没放的条目一律不算数 —— 声明的形态合法，
    不等于东西真的在。不给 `resolution` 时只算结构（这一层专门给判据本身做对照）。
    """
    entries = [e for e in (reg.get("entries") or []) if isinstance(e, dict)]
    samples = [e for e in entries if e.get("sample")]
    real = [e for e in entries if not e.get("sample")]
    per_entry: dict[str, dict] = (resolution or {}).get("entries") or {}
    ready: list[dict] = []
    not_ready: dict[str, list[str]] = {}
    for e in real:
        ok, missing = classify(e)
        detail = list(missing)
        if resolution is not None:
            r = per_entry.get(str(e.get("id")))
            if r is None:
                ok = False
                detail.append("没有核对结果：既没声明也没证据")
            elif not r.get("ok"):
                ok = False
                for x in (r.get("reasons") or []):
                    if x not in detail:
                        detail.append(x)
        if ok:
            ready.append(e)
        else:
            not_ready[str(e.get("id"))] = detail
    by_category: dict[str, int] = {}
    by_operator: dict[str, int] = {}
    by_batch: dict[str, int] = {}
    for e in ready:
        by_category[str(e.get("category"))] = by_category.get(str(e.get("category")), 0) + 1
        by_operator[str(e.get("operator"))] = by_operator.get(str(e.get("operator")), 0) + 1
        by_batch[str(e.get("batch"))] = by_batch.get(str(e.get("batch")), 0) + 1

    problems: list[str] = []
    if len(real) != TOTAL_TARGET:
        problems.append(f"真实 SKU {len(real)}/{TOTAL_TARGET} 条"
                        + (f"（另有 {len(samples)} 条标了 sample，样例不计数）" if samples else ""))
    if not_ready:
        problems.append(f"{len(not_ready)} 条缺料，按 not-ready 处理、不参与配额："
                        f"{ {k: v for k, v in list(not_ready.items())[:3]} }"
                        + ("…" if len(not_ready) > 3 else ""))
    if len(by_category) < MIN_CATEGORIES:
        problems.append(f"品类 {len(by_category)} 个，至少要有 {MIN_CATEGORIES} 个")
    for cat, n in sorted(by_category.items()):
        if n < MIN_PER_CATEGORY:
            problems.append(f"品类 {cat} 只有 {n} 个，每类至少 {MIN_PER_CATEGORY} 个")
    if len(by_operator) < MIN_OPERATORS:
        problems.append(f"操作员 {len(by_operator)} 名，至少要有 {MIN_OPERATORS} 名")
    for op, n in sorted(by_operator.items()):
        if n < MIN_PER_OPERATOR:
            problems.append(f"操作员 {op} 只分到 {n} 个，每人至少 {MIN_PER_OPERATOR} 个")
    for batch in BATCHES:
        want = len(CALIBRATION_ORDERS) if batch == "calibration" else TOTAL_TARGET - len(CALIBRATION_ORDERS)
        got = by_batch.get(batch, 0)
        if got != want:
            problems.append(f"{batch} 批次 {got}/{want} 条")

    if resolution is not None:
        # 对不上的一律顶到最前面：它是"要人查"，比"还没齐"更急
        problems = [f"对不上 · {eid}：{m}" for eid, r in per_entry.items()
                    for m in (r.get("mismatch") or [])] + problems
        if not resolution.get("any_input"):
            problems.insert(0, "一条可核对的输入都还没有 —— 空表不算绿")

    return {
        "total_entries": len(entries),
        "sample": len(samples),
        "real": len(real),
        # 注意别写成 "ready"：那个键是布尔结论，计数得另起一个名字
        "ready_count": len(ready),
        "not_ready": not_ready,
        "by_category": by_category,
        "by_operator": by_operator,
        "by_batch": by_batch,
        "resolution": (None if resolution is None else {
            "counts": resolution.get("counts"),
            "any_input": resolution.get("any_input"),
            "policy_version": resolution.get("policy_version"),
            "policy_signed": resolution.get("policy_signed"),
            "root": resolution.get("root"),
        }),
        "targets": {"total": TOTAL_TARGET, "min_categories": MIN_CATEGORIES,
                    "min_per_category": MIN_PER_CATEGORY, "min_operators": MIN_OPERATORS,
                    "min_per_operator": MIN_PER_OPERATOR,
                    "calibration_orders": list(CALIBRATION_ORDERS)},
        "problems": problems,
        "ready": not problems,
    }


def require_ready(summary: dict) -> dict:
    """G1 门禁入口用它：不齐就抛，而不是"返回 False 让人自己记得看"。"""
    if not summary.get("ready"):
        raise PilotNotReady(summary)
    return summary
