# -*- coding: utf-8 -*-
"""D1.P4 —— 换商品探针：换一个商品，到底要改什么？

它回答一个二选一的问题，并且要求答案**可测量**：

    换商品 = 只加数据（`demo/fixture/<sku>/` + 参考包 + 候选产物），还是必须改 `.py`？

四件事分开做，任一件都不许用另一件的结论代替：

  1. 逐包齐套：每个包按约定文件报告「齐套 / 缺哪几份」；
  2. 绑定扫描：在 `demo/**/*.py` 里找出把**具体商品**焊进代码的地方，并按层归类 ——
     产品层（`demo/core`、`demo/verify`、`demo/provider`、`app`）出现即 violation；
     夹具与证据层（`demo/fixture`、`tools`、`evals`）出现只记入清单，不判死
     （计划 §4.6：夹具工具本来就是那个商品的夹具）。
     「焊进代码」有两种形态，都要抓：
       · 目录名形态：字符串里直接写 `demo/fixture/<已存在的包名>`
       · 默认包形态：模块级常量 = `PKG.default(...)` —— 导入时就把默认包焊死，
         任何非默认包都进不来（这比写商品名更隐蔽：全文搜 SKU 字面量搜不到它）
  3. 动态尝试：对目标包逐个环节试着跑链，并**检查它到底读了哪个包** ——
     环节读了默认包而不是目标包时算「换商品要改代码」；环节报缺料则记成缺料（数据）。
  4. 换目录对照：把默认包的数据整体复制进临时项目、**只把包目录名换掉**，跑同一条链
     并逐值比对读数；再把目标包拿掉跑一次，必须报错而不是回落到别的包。
     这一条证明的是「身份跟着数据走」，不是「再加一个商品」。

用法：
    python demo/verify/swap_probe.py report --project .                 # 默认包
    python demo/verify/swap_probe.py report --project . --sku <包名>      # 指定包
    python demo/verify/swap_probe.py self-test --project .              # 四种改坏必须被抓到

退出码：0 = 代码侧不需要改（可能仍缺数据，缺料会写进清单）；1 = 必须改代码或探针自身失败。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

PRODUCT_LAYERS = ("demo/core", "demo/verify", "demo/provider", "app")
FIXTURE_LAYERS = ("demo/fixture", "tools", "evals")
SCAN_ROOTS = ("demo", "app")

# 换目录对照用的包名：刻意与已存在的包都不同，且只活在临时项目里。
CONTROL_ALIAS = "control-z9-swap"

# 换目录后**预期会变**的读数：它们把「身份/来源」本身算进了内容，不是缺陷。
# 这些值必须在报告里逐条列出来，不许悄悄过滤 —— 过滤掉就变成了挑选证据。
IDENTITY_DERIVED = ("sku", "intake/pack_id", "facts/facts_version", "plan/plan_version")

# 只抓**模块级**常量（顶格）：计划 §4.6 的原文是「模块常量只能作默认值」，
# 而「导入时焊死默认包」的形态就是顶格的 `X = PKG.default(...)`。
# 两点来自实测：第一版漏了 `_PKG = PKG.default(ROOT)`（下划线开头）；
# 第二版把函数体里缩进的 `default_pkg = PKG.default(root)` 也算成违规 ——
# 那是入口的默认值，正是允许的用法，探针不该咬自己。
DEFAULT_PACKAGE_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*\s*=\s*[A-Za-z_][A-Za-z0-9_]*\.default\s*\(")

# 第三种形态：逐商品数据留在旧位置（收拢前它住在 demo/core/ 下、文件名带 SKU 后缀）。
# 它既不写商品名、也不焊默认包，但位置一搬就静默改变结论 —— 反例真实发生过：
# D1.P4 步骤 0 把 verifier_plan.*.json 收进商品包之后，route_compare 仍按旧位置 glob，
# 于是「没有阈值」被读成了「前提不成立」，D1.R2 的读数被悄悄改掉。
# 两个片段分开拼，是为了不让探针自己这一行成为命中（探针咬自己是实测踩过的坑）。
LEGACY_CORE_PATH = r"(demo/core|\"demo\"\s*/\s*\"core\"|'demo'\s*/\s*'core')"
LEGACY_PRODUCT_DATA_RE = re.compile(
    LEGACY_CORE_PATH + r".*(prompt_profile|verifier_plan|human_fact_review"
    r"|human_visual_review|fact_capability)[.\"']")


def layer_of(rel: str) -> str:
    for pref in PRODUCT_LAYERS:
        if rel == pref or rel.startswith(pref + "/"):
            return "product"
    for pref in FIXTURE_LAYERS:
        if rel == pref or rel.startswith(pref + "/"):
            return "fixture"
    return "other"


def py_sources(root: Path) -> list:
    root = Path(root)
    out = []
    for sub in SCAN_ROOTS:
        d = root / sub
        if not d.exists():
            continue
        for p in sorted(d.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            out.append((p.relative_to(root).as_posix(), p.read_text(encoding="utf-8")))
    return out


def scan_sources(sources, skus) -> dict:
    """纯函数：给 (相对路径, 源码) 列表与已存在的包名，返回绑定清单。"""
    findings = {"package_literal": [], "default_package_bound": [], "legacy_product_data": []}
    for rel, text in sources:
        lay = layer_of(rel)
        for i, line in enumerate(text.splitlines(), 1):
            for sku in skus:
                needle = "demo/fixture/" + sku
                if needle not in line:
                    continue
                # 只认「目录名」用法：后面紧接 / 或引号收尾，
                # 否则 `demo/fixture/<包名>1` 会被当成 `demo/fixture/<包名>`
                tail = line.split(needle, 1)[1][:1]
                if tail and tail not in ("/", '"', "'"):
                    continue
                findings["package_literal"].append(
                    {"file": rel, "line": i, "sku": sku, "layer": lay,
                     "text": line.strip()[:120]})
                break
            if DEFAULT_PACKAGE_RE.match(line):
                findings["default_package_bound"].append(
                    {"file": rel, "line": i, "layer": lay, "text": line.strip()[:120]})
            # 提到 `demo/core` 的 .py 文件是正常的（说明实现住在哪）；提到
            # `demo/core` 的逐商品数据文件才是违规。所以带 `.py` 的行不算命中。
            if LEGACY_PRODUCT_DATA_RE.search(line) and ".py" not in line:
                findings["legacy_product_data"].append(
                    {"file": rel, "line": i, "layer": lay, "text": line.strip()[:120]})
    # 硬违规只有一种：**产品层直接写商品目录名**。计划 §4.6 原文允许「模块常量作默认值」，
    # 所以默认包常量不进硬违规 —— 它是否真的挡住换商品，由 ③ 动态尝试与 ④ 对照来判。
    # 但「产品层按旧位置读逐商品数据」是硬违规：它让数据搬家常静默改掉结论（实测发生过）。
    findings["violations"] = sorted(
        {(f["file"], f["line"]) for f in findings["package_literal"]
         if f["layer"] == "product"}
        | {(f["file"], f["line"]) for f in findings["legacy_product_data"]
           if f["layer"] == "product"})
    return findings


def py_digest(root: Path) -> dict:
    out = {}
    for rel, text in py_sources(root):
        out[rel] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return out


# ------------------------------------------------------------------ ③ 动态尝试
# 每个环节先看它需要的商品数据在不在；不在就记「缺料」（数据），在就真跑一遍看它读了哪个包。
def dynamic_attempt(root: Path, sku: str) -> dict:
    """对目标包逐个环节试着跑，并检查它读的到底是哪个包。"""
    root = Path(root)
    sys.path.insert(0, str(root))
    from demo.core import back_chain as B
    from demo.core import front_chain as FC
    from demo.core import packages as PKG

    pkg = PKG.resolve(root, sku)
    default_pkg = PKG.default(root)
    present = {k: pkg.has(k) for k in PKG.FILES}
    missing = sorted(k for k, v in present.items() if not v)
    out = {"sku": sku, "package_dir": pkg.root.relative_to(root).as_posix(),
           "present": present, "missing": missing,
           "is_default_package": pkg.sku == default_pkg.sku, "stages": {}}

    def blocked(name, need):
        out["stages"][name] = {"ran": False, "missing_data": list(need),
                               "blocked_by": "缺料 " + "、".join(need)}

    # 环节 1：包解析（一定跑得动）
    out["stages"]["resolve"] = {"ran": True, "detail": "包解析器按目录解析 " + sku}

    # 环节 2：PC-01 参考包 —— 关键在于它用商品包声明的那个包，而不是代码里的默认包
    need = [k for k in ("refpack",) if not pkg.has(k)]
    if need:
        blocked("PC-01", need)
    else:
        r = FC.intake(root, sku)
        target = PKG.refpack_of(root, sku)["pack_dir"]
        got = (r.payload or {}).get("pack_dir") if isinstance(r.payload, dict) else None
        out["stages"]["PC-01"] = {"ran": True, "outcome": r.outcome, "read": got,
                                  "wanted": target, "reads_target": got == target}

    # 环节 3：PC-02 事实卡
    need = [k for k in ("card",) if not pkg.has(k)]
    if need:
        blocked("PC-02", need)
    else:
        r = FC.facts(root, sku=sku)
        # 卡本身不合格时 payload 里没有 card，但 evidence 里记了它读的是哪一张 —— 两者都算读数。
        pl = r.payload if isinstance(r.payload, dict) else {}
        ev = r.evidence if isinstance(r.evidence, dict) else {}
        got = pl.get("card") or ev.get("card")
        target = pkg.rel("card")
        out["stages"]["PC-02"] = {"ran": True, "outcome": r.outcome, "read": got,
                                  "wanted": target, "reads_target": got == target,
                                  "notes": list(r.notes)[:2]}

    # 环节 4：PC-09 候选来源 + 路由计划 + 人工事实记录（三份都随商品包走）
    runs = None
    need = [k for k in ("runs", "verifier_plan", "human_facts") if not pkg.has(k)]
    if need:
        blocked("PC-09", need)
    else:
        runs = PKG.runs_of(root, sku)
        if not runs["manifest"].is_file():
            blocked("PC-09", ["候选 manifest（" + runs["candidates_dir"] + "/manifest.json）"])
        else:
            g = B.golden_candidates(root, sku)
            outcomes = {}
            for cid, cand in sorted(g["candidates"].items()):
                r = B.fact_routing(cand, g["card"], g["verifier_plan"], g["human_facts"],
                                   human_source=g["sources"]["human_facts"])
                outcomes[cid] = r.outcome
            out["stages"]["PC-09"] = {"ran": True, "outcome": "per-candidate",
                                      "read": runs["candidates_dir"],
                                      "wanted": pkg.rel("runs"), "reads_target": True,
                                      "candidate_outcomes": outcomes}

    # 环节 5：PC-10 审美审核
    need = [k for k in ("runs", "human_visual") if not pkg.has(k)]
    if need:
        blocked("PC-10", need)
    else:
        runs = runs or PKG.runs_of(root, sku)
        if not runs["manifest"].is_file():
            blocked("PC-10", ["候选 manifest（" + runs["candidates_dir"] + "/manifest.json）"])
        else:
            g = B.golden_candidates(root, sku)
            r = B.visual_review("S2", sorted(g["candidates"]), g["human_visual"],
                                source=g["sources"]["human_visual"])
            out["stages"]["PC-10"] = {"ran": True, "outcome": r.outcome,
                                      "read": g["sources"]["human_visual"],
                                      "wanted": pkg.rel("human_visual"), "reads_target": True}

    out["runs_ref"] = (pkg.rel("runs") if pkg.has("runs") else None)
    return out


# ------------------------------------------------------------------ ④ 换目录对照
def control_reading(project, sku) -> dict:
    """对一个「项目 + 包」跑一遍可比读数：全部离线、零付费。

    刻意只收**与包目录名无关**的量：内容哈希、事实版本号、计划版本号、提示词哈希、
    候选哈希、逐事实结论、审美结论、选择与合成产物哈希。换了包目录名，这些值一个都不该变。
    """
    project = Path(project)
    from demo.core import back_chain as B
    from demo.core import front_chain as FC
    from demo.core import packages as PKG

    def payload(r):
        return r.payload if isinstance(r.payload, dict) else {}

    def need(r, stage):
        if not r.accepted:
            raise RuntimeError(stage + " 未通过（" + r.outcome + "）：" + "；".join(r.notes))
        return r

    out: dict = {"sku": sku}
    r1 = need(FC.intake(project, sku), "PC-01")
    p1 = payload(r1)
    out["intake"] = {"outcome": r1.outcome, "pack_id": p1.get("pack_id"),
                     "views": len(p1.get("views") or [])}
    r2 = need(FC.facts(project, r1.payload, sku=sku), "PC-02")
    p2 = payload(r2)
    out["facts"] = {"outcome": r2.outcome, "facts_version": p2.get("facts_version"),
                    "card_sha256": p2.get("card_sha256")}
    r3 = need(FC.propose_plan(p2, p1, FC.platform_rules(project), goal=None,
                              confirmed_by="demo-user"), "PC-03")
    p3 = payload(r3)
    out["plan"] = {"outcome": r3.outcome, "plan_version": p3.get("plan_version")}
    r4 = need(FC.style_spec(p3, p2, project=project, sku=sku), "PC-04")
    r5 = need(FC.compile_prompt(p3, p2, payload(r4), "S2", project=project, sku=sku), "PC-05")
    p5 = payload(r5)
    out["prompt"] = {"outcome": r5.outcome, "prompt_sha256": p5.get("prompt_sha256"),
                     "locks_facts": sorted(p5.get("locks_facts") or []),
                     "profile_sha256": hashlib.sha256(PKG.path_of(
                         project, "prompt_profile", sku).read_bytes()).hexdigest()}

    g = B.golden_candidates(project, sku)
    out["candidates"] = {cid: c["sha256"] for cid, c in sorted(g["candidates"].items())}
    routing = {}
    for cid, cand in sorted(g["candidates"].items()):
        r = B.fact_routing(cand, g["card"], g["verifier_plan"], g["human_facts"],
                           human_source=g["sources"]["human_facts"])
        routing[cid] = {"outcome": r.outcome,
                        "facts": sorted((i["fact_id"], str(i["verdict"]))
                                        for i in (r.payload or {}).get("review_items", []))}
    out["fact_routing"] = routing
    rv = B.visual_review("S2", sorted(g["candidates"]), g["human_visual"],
                         source=g["sources"]["human_visual"])
    out["visual"] = {"outcome": rv.outcome,
                     "verdicts": {k: v["verdict"] for k, v in
                                  sorted((rv.payload or {}).get("reviews", {}).items())}}

    chosen = sorted(g["candidates"])[0]
    sel = B.select_candidate(shot_id="S2", candidate=g["candidates"][chosen],
                             fact_result=B.fact_routing(
                                 g["candidates"][chosen], g["card"], g["verifier_plan"],
                                 g["human_facts"],
                                 human_source=g["sources"]["human_facts"]),
                             review=rv)
    selection = (sel.payload or {}).get("selection") if isinstance(sel.payload, dict) else None
    out["select"] = {"outcome": sel.outcome,
                     "selection_id": (selection or {}).get("selection_id")}
    if selection:
        out_dir = Path(tempfile.mkdtemp(prefix="swap-compose-"))
        try:
            cp = B.compose(selection, g["candidates"][chosen], out_dir=out_dir)
            out["compose"] = {"outcome": cp.outcome,
                              "output_sha256": (cp.payload or {}).get("output_sha256")}
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)
    return out


def diff_readings(a, b, path="") -> list:
    """逐值比对两轮读数，返回不一致清单（路径 + 两个值）。"""
    diffs: list = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            diffs += diff_readings(a.get(k, "<缺>"), b.get(k, "<缺>"),
                                   (path + "/" + str(k)) if path else str(k))
        return diffs
    if a != b:
        diffs.append(path + "：基线 " + json.dumps(a, ensure_ascii=False)
                     + " ≠ 对照 " + json.dumps(b, ensure_ascii=False))
    return diffs


def build_control_project(root) -> tuple:
    """把默认包的数据整体复制进一个临时项目，只把包目录名换成 CONTROL_ALIAS。

    副本里同步改两处**数据内指针**：参考包 manifest 指着事实卡与阈值派生记录，
    包目录改名后它们必须跟着改。改的全是数据，`.py` 一个字节不动 —— 这份清单
    本身就是 D1.P4 要的「换了商品也要改什么」。
    """
    from demo.core import packages as PKG
    root = Path(root)
    src = PKG.resolve(root)
    ref = PKG.refpack_of(root)
    runs = PKG.runs_of(root)
    work = Path(tempfile.mkdtemp(prefix="swap-control-"))
    ignore = shutil.ignore_patterns("__pycache__")
    fixture = root / PKG.FIXTURE_SUB
    for d in sorted(p for p in fixture.iterdir() if p.is_dir() and p.name != "__pycache__"):
        shutil.copytree(d, work / PKG.FIXTURE_SUB / d.name, ignore=ignore)
    shutil.copytree(src.root, work / PKG.FIXTURE_SUB / CONTROL_ALIAS, ignore=ignore)
    shutil.copytree(ref["dir"], work / ref["pack_dir"], ignore=ignore)
    shutil.copytree(runs["dir"], work / runs["candidates_dir"], ignore=ignore)
    (work / "config").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / "config" / "slots.yaml", work / "config" / "slots.yaml")

    edits = []
    man_path = work / ref["pack_dir"] / "reference-manifest.json"
    man = json.loads(man_path.read_text(encoding="utf-8"))
    for node_key in ("fact_card", "threshold_derivation"):
        node = man.get(node_key)
        if not isinstance(node, dict) or not node.get("file"):
            continue
        old = str(node["file"])
        new = old.replace(src.sku, CONTROL_ALIAS)
        if new != old:
            node["file"] = new
            edits.append("参考包 manifest 的 " + node_key + ".file：" + old + " → " + new)
    man_path.write_text(json.dumps(man, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8", newline="\n")
    return work, src.sku, CONTROL_ALIAS, edits


def rename_control(root) -> dict:
    """换目录对照：证明身份跟着数据走，而不是跟着代码里的默认包走。

    两条读数都要成立：
      · 除「数据本身改过的那两处指针」外，链上读数逐值相同；
      · 把目标包拿掉再跑一次必须报错 —— 不许静默回落到别的包。

    pack_id / plan_version 必然不同：它们把参考包 manifest 的内容哈希算了进去，
    而 manifest 的两处指针正是这次的数据改动。其余读数都该一致。
    """
    root = Path(root)
    work, base_sku, alias, edits = build_control_project(root)
    try:
        base = control_reading(root, base_sku)
        ctl = control_reading(work, alias)
        all_diffs = diff_readings(base, ctl)
        expected = [d for d in all_diffs if d.split("：", 1)[0] in IDENTITY_DERIVED]
        diffs = [d for d in all_diffs if d not in expected]
        shutil.rmtree(work / "demo" / "fixture" / alias)
        fallback = None
        fallback_error = None
        fallback_note = None
        try:
            control_reading(work, alias)
            fallback = "目标包不存在，却仍然跑出了读数 —— 有静默回落"
        except Exception as exc:                  # noqa: BLE001  期望就是报错
            fallback_error = type(exc).__name__
            fallback_note = str(exc)[:160]
        return {"alias": alias, "baseline_sku": base_sku,
                "baseline": base, "control": ctl, "diffs": diffs,
                "expected_diffs": expected, "data_edits": edits,
                "no_silent_fallback": fallback is None,
                "fallback_error": fallback_error, "fallback_note": fallback,
                "fallback_message": fallback_note,
                "ok": (not diffs) and fallback is None}
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ------------------------------------------------------------------ 报告
def report(project: Path, sku=None, *, control=True) -> dict:
    project = Path(project)
    sys.path.insert(0, str(project))
    from demo.core import packages as PKG

    skus = PKG.list_skus(project)
    default_sku = PKG.default(project).sku
    target = sku or default_sku
    before = py_digest(project)
    sources = py_sources(project)
    findings = scan_sources(sources, skus)
    dyn = dynamic_attempt(project, target)
    # 对照只对默认包成立：它拿默认包的数据换目录名，证明「身份跟着数据走」。
    ctl = rename_control(project) if (control and target == default_sku) else None
    after = py_digest(project)
    changed = sorted(k for k in before if before[k] != after.get(k))

    # 「代码」类清单：产品层焊死商品身份、环节读了别的包、对照不成立。
    code_items = []
    for name, st in dyn["stages"].items():
        if st.get("ran") and st.get("reads_target") is False:
            code_items.append(name + " 读的是 " + str(st.get("read"))
                              + "，不是目标包 " + str(st.get("wanted")))
    for f in findings["default_package_bound"]:
        if f["layer"] == "product":
            code_items.append("模块常量在导入时焊死默认包 —— "
                              + f["file"] + ":" + str(f["line"]))
    for f in findings["legacy_product_data"]:
        if f["layer"] == "product":
            code_items.append("产品层按旧位置读逐商品数据 —— "
                              + f["file"] + ":" + str(f["line"]))
    if findings["violations"]:
        code_items.append("产品层写了商品目录名")
    if ctl is not None and not ctl["ok"]:
        if ctl["diffs"]:
            code_items.append("换目录对照读数不一致：" + str(ctl["diffs"][:3]))
        if not ctl["no_silent_fallback"]:
            code_items.append("换目录对照：" + str(ctl["fallback_note"]))

    if code_items:
        verdict = "code_change_required"
    elif target == default_sku:
        verdict = ("default_package_control_ok"
                   if (ctl is not None and ctl["ok"]) else "default_package_only")
    elif dyn["missing"]:
        verdict = "data_missing_no_code_change"
    else:
        verdict = "data_only_swap"
    return {"skus": skus, "target": target, "default_sku": default_sku,
            "before": before, "after": after, "py_changed_during_probe": changed,
            "findings": findings, "dynamic": dyn, "control": ctl,
            "code_items": code_items, "verdict": verdict}


def _print(rep: dict) -> None:
    f = rep["findings"]
    print("=" * 74)
    print("D1.P4 换商品探针（离线 · 零付费）")
    print("=" * 74)
    print("  商品包：" + "、".join(rep["skus"]) + "    目标包：" + rep["target"])
    print("  扫描的 .py：" + str(len(rep["before"])) + " 份（运行前后哈希变化："
          + (str(rep["py_changed_during_probe"]) if rep["py_changed_during_probe"] else "无") + "）")
    print()
    d = rep["dynamic"]
    print("  ① 目标包齐套")
    print("     存在：" + ("、".join(k for k, v in d["present"].items() if v) or "（无）"))
    print("     缺料：" + ("、".join(d["missing"]) if d["missing"] else "无"))
    print()
    print("  ② 绑定扫描（把具体商品焊进代码的地方）")
    for key, label in (("package_literal", "目录名形态"),
                       ("default_package_bound", "默认包形态（导入时焊死）"),
                       ("legacy_product_data", "旧位置形态（按老路径读逐商品数据）")):
        rows = f[key]
        if not rows:
            print("     [" + label + "] 无")
            continue
        for r in rows:
            tag = "产品层→不许" if r["layer"] == "product" else "夹具/证据层→记入清单"
            print("     [" + label + "] " + r["file"] + ":" + str(r["line"])
                  + "（" + tag + "） " + r["text"])
    print()
    print("  ③ 动态尝试")
    for name, st in d["stages"].items():
        if st.get("ran"):
            extra = ""
            if "reads_target" in st:
                extra = ("；读到的包 = " + str(st.get("read"))
                         + ("（就是目标包）" if st["reads_target"] else "（不是目标包！）"))
            print("     [OK  ] " + name + "：" + str(st.get("outcome") or st.get("detail")) + extra)
            for note in st.get("notes") or []:
                print("              · " + str(note)[:150])
        else:
            print("     [BLOCK] " + name + "：" + str(st.get("blocked_by")
                                                      or st.get("error")))
    print()
    print("  ④ 换目录对照（同一份数据，只换包目录名）")
    c = rep["control"]
    if c is None:
        print("     [SKIP] 目标包不是默认包 —— 对照用默认包的数据，只对默认包成立")
    else:
        print("     对照包名：" + c["alias"] + "（临时项目，跑完即删）")
        print("     数据改动（都是数据，.py 零改动）：")
        print("       · 包目录 " + c["baseline_sku"] + " → " + c["alias"])
        for e in c["data_edits"]:
            print("       · " + e)
        if c["diffs"]:
            print("     读数不一致：" + str(len(c["diffs"])) + " 处")
            for x in c["diffs"][:8]:
                print("       · " + x)
        else:
            print("     [OK  ] 除身份派生值（" + "、".join(IDENTITY_DERIVED)
                  + "）外逐值相同：" + "、".join(
                      sorted(k for k in c["baseline"] if k != "sku")))
        for x in c["expected_diffs"]:
            print("     [变  ] 身份派生值，预期就不同：" + x)
        if c["no_silent_fallback"]:
            print("     [OK  ] 拿掉目标包后报错（" + str(c["fallback_error"])
                  + "），没有静默回落到别的包")
            if c.get("fallback_message"):
                print("           " + c["fallback_message"])
        else:
            print("     [FAIL] " + str(c["fallback_note"]))
    print()
    print("  结论：" + rep["verdict"])
    if rep["code_items"]:
        print("     换这个商品**必须改代码**，清单：")
        for b in rep["code_items"]:
            print("       · " + b)
    elif rep["verdict"] in ("data_missing_no_code_change", "data_only_swap"):
        print("     换这个商品不必改 .py —— 代码侧清单为空。")
        if d["missing"]:
            print("     但仍缺数据，补齐才有读数：")
            for name, st in d["stages"].items():
                if not st.get("ran"):
                    print("       · " + name + " 需要 " + "、".join(st.get("missing_data") or []))
    elif rep["verdict"] == "default_package_control_ok":
        print("     默认包：代码里没有焊死商品身份 —— 同一份数据换目录名后逐值读数不变；")
        print("     「换商品要改什么」的答案见 --sku <另一个包> 的读数。")
    else:
        print("     目标包就是默认包，且这次没有取到对照读数。")
    print()


# ------------------------------------------------------------------ 自检
def selftest(project) -> int:
    root = Path(project)
    sys.path.insert(0, str(root))
    from demo.core import packages as PKG
    skus = PKG.list_skus(root)
    if not skus:
        print("没有商品包，无法自检")
        return 1
    sku = skus[0]
    # 这两段拼起来才是被扫的坏样本：探针自己的源码不许变成自己的命中（实测踩过两次）。
    legacy_dir = '"demo" / ' + '"core"'
    legacy_stem = "verifier" + "_plan"
    # 期望分两列：探针是否**抓到**，以及它是否属于**硬违规**。
    # 关键的一条：顶格 `X = PKG.default(...)` 是「候选」而不是硬违规 ——
    # 计划 §4.6 允许模块常量作默认值，它是否真的挡住换商品由 ③④ 的读数裁决。
    cases = [
        ("产品层写商品目录名", "demo/core/x.py",
         'CARD_SUB = "demo/fixture/' + sku + '/product.json"\n',
         "package_literal", "product", True),
        ("夹具层写商品目录名", "demo/fixture/x.py",
         'CARD_SUB = "demo/fixture/' + sku + '/product.json"\n',
         "package_literal", "fixture", False),
        ("产品层焊死默认包（候选，非硬违规）", "demo/core/y.py",
         'CARD_SUB = PKG.default(ROOT).rel("card")\n',
         "default_package_bound", "product", False),
        ("夹具层焊死默认包（候选，非硬违规）", "demo/fixture/y.py",
         'CARD_SUB = PKG.default(ROOT).rel("card")\n',
         "default_package_bound", "fixture", False),
        ("缩进的默认值（允许）", "demo/core/z.py",
         'def f():\n    pkg = PKG.default(ROOT)\n    return pkg\n',
         "default_package_bound", None, False),
        ("产品层按旧位置 glob 逐商品数据", "demo/verify/w.py",
         "plan = next((project / " + legacy_dir + ").glob(" + legacy_stem + ".*.json))\n",
         "legacy_product_data", "product", True),
        ("产品层提到 demo/core 下的 .py（允许）", "demo/verify/v.py",
         'REF = "demo/core/back_chain.py::fact_routing"\n',
         "legacy_product_data", None, False),
    ]
    caught = 0
    print("换商品探针自检（" + str(len(cases)) + " 种改坏必须各按层判对）")
    for name, rel, text, key, want_layer, want_violation in cases:
        got = scan_sources([(rel, text)], skus)
        rows = got[key]
        found = [r for r in rows if r["file"] == rel]
        hit = any(x[0] == rel for x in got["violations"])
        layer_ok = (want_layer is None) or (
            len(found) == 1 and found[0]["layer"] == want_layer)
        ok = bool(found) == (want_layer is not None) and layer_ok and hit == want_violation
        caught += 1 if ok else 0
        mark = "OK  " if ok else "FAIL"
        print("  [" + mark + "] " + name + "：抓到=" + str(bool(found)) + " 归类="
              + (found[0]["layer"] if found else "-")
              + " 硬违规=" + str(hit) + "（期望 抓到=" + str(want_layer is not None)
              + " 硬违规=" + str(want_violation) + "）")
    print()
    if caught != len(cases):
        print("自检未通过：" + str(caught) + "/" + str(len(cases)))
        return 1
    print("自检：" + str(caught) + "/" + str(len(cases)) + " 种改坏都被按层判对")
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                     # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="D1.P4 换商品探针")
    ap.add_argument("mode", nargs="?", default="report", choices=["report", "self-test"])
    ap.add_argument("--project", default=str(ROOT))
    ap.add_argument("--sku", default=None)
    ap.add_argument("--skip-control", action="store_true",
                    help="跳过换目录对照（对照会离线真跑两遍链）")
    args = ap.parse_args(argv)
    project = Path(args.project).resolve()
    if args.mode == "self-test":
        return selftest(project)
    rep = report(project, args.sku, control=not args.skip_control)
    _print(rep)
    return 1 if rep["verdict"] == "code_change_required" else 0


if __name__ == "__main__":
    raise SystemExit(main())
