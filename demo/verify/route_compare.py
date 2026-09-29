#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""D1.R2 —— 三种验证路线的离线对照（A 分割后量测 / B 参考图条件视觉判断 / C 混合）。

它回答一个问题：**哪条路线在哪类事实上不可用**。这不是「哪条更好」的感受题，
而是同一批输入、同一份事实定义下的可核对对照：检出、漏报、误报、Unknown、
证据可解释性，以及换商品要不要改代码。

三条路线的边界（写在这里，免得读报告的人自己去猜）：

- 路线 A：先用分割模型把主体从场景里切出来、贴回中性底衬，再复用既有阈值量测。
  它仍然需要「每个商品一份 metric profile 与阈值」，所以换商品 = 换代码级配置。
  **适用性必须在原图上判**：贴回底衬之后再去探「背景是否中性」，量的是我们自己铺的
  那层灰 —— 那是自证，不是证据。原图前提不成立时，画布读数只作反事实记录。
- 路线 B：把参考图与候选一起交给视觉模型，逐事实问「是否保持」。
  按计划 §9.1.1，未完成对照校准的模型默认只输出 risk，不默认 hard 判。
- 路线 C：A 出几何、B 出语义、判不了交人工；它不需要新调用，是 A/B 结果的合并规则。

用法：
    python demo/verify/route_compare.py --project . --sku <name> --route a
    python demo/verify/route_compare.py --project . --sku <name> --route b --confirm-spend
    python demo/verify/route_compare.py --project . --sku <name> --route both --confirm-spend

退出码：0 跑完并写出报告；2 有路线没跑成（原因写进报告，不假装跑过）；3 用法或文件缺失。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import requests
from PIL import Image

ROOT_DEFAULT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT_DEFAULT / "demo" / "fixture"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import factcard                       # noqa: E402
import measure_cylinder as MC         # noqa: E402

CHAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
VLM_MODELS = ["qwen-vl-max", "qwen-vl-max-latest"]
NEUTRAL_FILL = (180, 180, 180)        # 低饱和中性灰，与棚拍底衬同族
CANVAS_MARGIN = 0.10                  # 贴回底衬时四周各留的比例：既有量测先从边框估背景色
APPLICABILITY_PROBE = "controlled_backdrop"
DEFAULT_SESSION = "birefnet-general-lite"
MODEL_DIR_CANDIDATES = [os.getenv("REMBG_MODEL_DIR", ""),
                        r"E:\model_repository\model_scope\rembg"]

VLM_INSTRUCT = """You compare a candidate product photo against a reference photo of the SAME product.

Image 1 = reference (the real product). Image 2 = candidate render.

For each claim below, decide whether the candidate KEEPS it. Allowed verdicts:
  "same"      = the candidate visibly keeps the claim
  "different" = the candidate visibly violates the claim
  "uncertain" = you cannot tell from this image

Answer with JSON only, no prose, no markdown fences:
{"<id>": {"verdict": "same|different|uncertain", "why": "<at most 12 words>"}, ...}

Claims:
"""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def first_existing_dir() -> str | None:
    for p in MODEL_DIR_CANDIDATES:
        if p and os.path.isdir(p):
            return p
    return None


def build_comparison_set(project: Path, sku: str) -> list[dict]:
    """同一批输入：四张真实候选 + 三个未变异对照 + 七个负样本 + 一个别的商品边界样本。

    每一条的来源都在项目既有证据里，不在这里新写预期。
    """
    items: list[dict] = []
    sys.path.insert(0, str(project))
    from demo.core import packages as PKG
    manifest = read_json(PKG.runs_of(project, sku)["manifest"])

    def attempts(o):
        if isinstance(o, list) and o and isinstance(o[0], dict) and "image_path" in o[0]:
            return o
        if isinstance(o, dict):
            for v in o.values():
                r = attempts(v)
                if r:
                    return r
        if isinstance(o, list):
            for v in o:
                r = attempts(v)
                if r:
                    return r
        return None

    for a in attempts(manifest) or []:
        items.append({"id": a["candidate_id"], "role": "scene_candidate", "path": Path(a["image_path"]),
                      "expect": "pass", "expect_source": "human_fact_review（D1.5 人工裁决，32 条全 pass）"})

    neg = project / "evals/product-demo/negative-cases"
    exp = read_json(neg / "expectations.json")
    exp_by_id = {c["case_id"]: c for c in exp["cases"]}
    for c in read_json(neg / "index.json")["cases"]:
        e = exp_by_id.get(c["case_id"], {})
        items.append({"id": c["case_id"], "role": "negative", "path": project / "evals/product-demo" / c["output"],
                      "expect": e.get("must_be"), "expect_source": "negative-cases/expectations.json（事先声明）",
                      "human_required": e.get("human_required")})
    for c in exp["controls"]:
        items.append({"id": c["case_id"], "role": "control", "path": project / c["file"],
                      "expect": c.get("must_be"), "expect_source": "negative-cases/expectations.json（事先声明）"})

    # 别的商品的边界样本：从商品包目录派生，不把 SKU 写进这一层（§4.6 硬规矩 1）
    for pkg in sorted((project / "demo/fixture").glob("*/product.json")):
        other = pkg.parent.name
        if other == sku:
            continue
        raw = project / "evals/product-demo/product-2" / other / "raw.png"
        if raw.exists():
            items.append({"id": other, "role": "boundary_other_product", "path": raw,
                          "expect": "not_pass",
                          "expect_source": "D0.7 第二商品；量的是别的商品，理应不通过"})
    for it in items:
        it["sha256"] = sha256_file(it["path"])
    return items

# ------------------------------------------------------------------ 路线 A
_SESSION: dict = {"obj": None, "name": None}


def load_session():
    """加载本地分割模型；本地没有就报缺，不触发下载（与 src/synth.py 同一份模型与会话名）。"""
    from rembg import new_session
    home = first_existing_dir()
    if home:
        os.environ.setdefault("U2NET_HOME", home)
    name = os.getenv("REMBG_SESSION") or DEFAULT_SESSION
    if _SESSION["obj"] is not None and _SESSION["name"] == name:
        return _SESSION["obj"], {"session": name, "home": home, "cached": True}
    sess = new_session(name)
    _SESSION.update({"obj": sess, "name": name})
    return sess, {"session": name, "home": home, "cached": False}


def drop_session():
    """推理失败时丢掉会话再重试：失败的根因是内存，会话正握着它的 arena。"""
    import gc
    _SESSION.update({"obj": None, "name": None})
    gc.collect()


def isolate_subject(path: Path, out_path: Path):
    """分割主体 → 裁到外接框（留 2% 边）→ 贴回中性底衬。返回 (图, 元数据)。

    为什么要贴回底衬：既有量测的前提是「背景低饱和中性」。这一步不是修饰，
    它就是把路线 A 的隐含前提补上 —— 前提补不上，后面的判定一律不算数。
    """
    from rembg import remove
    img = Image.open(path).convert("RGB")
    rgba, info, elapsed, last = None, None, None, None
    for attempt in (1, 2, 3):
        try:
            sess, info = load_session()
            t0 = time.time()
            rgba = remove(img, session=sess)
            elapsed = round(time.time() - t0, 2)
            break
        except Exception as exc:            # noqa: BLE001  内存不足 → 丢会话重试
            last = f"{type(exc).__name__}: {str(exc)[:160]}"
            drop_session()
            if attempt == 3:
                return None, {"status": "environment_blocked", "error": last,
                              "attempts": attempt}
    alpha = np.asarray(rgba.split()[-1])
    ys, xs = np.nonzero(alpha > 128)
    if ys.size == 0:
        return None, {"status": "failed", "error": "分割结果为空：没有找到主体"}
    h, w = alpha.shape
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
    subj_w, subj_h = x1 - x0 + 1, y1 - y0 + 1
    pad_x = max(8, int(round(subj_w * CANVAS_MARGIN)))
    pad_y = max(8, int(round(subj_h * CANVAS_MARGIN)))
    crop = rgba.crop((x0, y0, x1 + 1, y1 + 1))
    canvas = Image.new("RGBA", (subj_w + 2 * pad_x, subj_h + 2 * pad_y), NEUTRAL_FILL + (255,))
    canvas.alpha_composite(crop, (pad_x, pad_y))
    comp = canvas.convert("RGB")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    comp.save(out_path)
    return out_path, {"status": "ok", "session": (info or {}).get("session"),
                      "home": (info or {}).get("home"), "elapsed_s": elapsed,
                      "alpha_coverage": round(float((alpha > 128).mean()), 4),
                      "bbox": [x0, y0, x1, y1], "subject_size": [subj_w, subj_h],
                      "canvas_size": list(comp.size), "pad": [pad_x, pad_y],
                      "touch_border": bool(ys.min() == 0 or xs.min() == 0
                                           or ys.max() == h - 1 or xs.max() == w - 1),
                      "fill_rgb": list(NEUTRAL_FILL)}


def applicability_max(project: Path, sku=None):
    """适用性阈值只从既有权威读（商品包里的 verifier plan），不在这里另写一个数字。

    商品包的位置由包解析器给：D1.P4 步骤 0 把 `verifier_plan.*.json` 从 `demo/core/`
    收进了 `demo/fixture/<sku>/`，这里曾经还按旧位置 glob —— 那样找不到阈值时会
    把「不适用」当成结论的依据，等于让路径漂移改掉验证结论。
    """
    sys.path.insert(0, str(project))
    from demo.core import packages as PKG
    pkg = PKG.resolve(project, sku)
    plan = pkg.load("verifier_plan")
    for route in plan.get("routes", []):
        for r in route.get("routers", []):
            cond = r.get("applies_when") or {}
            if cond.get("probe") == APPLICABILITY_PROBE and cond.get("max_share") is not None:
                return float(cond["max_share"]), pkg.rel("verifier_plan")
    return None, None


def route_a(item: dict, card: dict, clf, out_dir: Path, project: Path, sku=None) -> dict:
    """路线 A：分割主体 → 贴回中性底衬 → 复用既有阈值量测。

    适用性必须在**原图**上判。把主体贴到中性底衬之后再去探「背景是否中性」，量的是
    我们自己刚铺的那层灰 —— 那是自证，不是证据（本次控制面校准新增的不变量）。
    所以这里把两件事分开记：
      · precondition：原图上的 controlled-backdrop 探针（权威，决定 applicable）
      · canvas_probe：制造出来的画布上的读数，只作画布卫生检查，标 self_referential
    原图前提不成立时，画布读数进 isolated_facts 作反事实记录，facts 一律 unknown。
    """
    original = Path(item["path"])
    import sys as _sys
    if str(ROOT_DEFAULT) not in _sys.path:
        _sys.path.insert(0, str(ROOT_DEFAULT))
    from demo.core import back_chain as B

    max_share, max_src = applicability_max(project, sku)
    probe_original = B.backdrop_probe(original)
    if max_share is None:
        applicable = False
        why = "没有可用的适用性阈值：verifier plan 里没有 " + APPLICABILITY_PROBE + ".max_share"
    else:
        applicable = bool(probe_original["subject_share_in_band"] <= max_share)
        why = ("原图纯背景列里的主体像素占比 "
               + str(probe_original["subject_share_in_band"]) + " 不大于 " + str(max_share)
               if applicable else
               "原图纯背景列里有 " + str(probe_original["subject_share_in_band"])
               + " 的像素被判成主体（上限 " + str(max_share) + "），这不是受控底衬")
    precondition = {"probe": APPLICABILITY_PROBE, "source": "原图（不是制造出来的底衬）",
                    "measured_share": probe_original["subject_share_in_band"],
                    "max_share": max_share, "max_share_source": max_src,
                    "applicable": applicable, "why": why}

    iso, meta = isolate_subject(original, out_dir / "isolated" / (item["id"] + ".png"))
    if iso is None:
        return {"route": "A", "status": meta.get("status", "failed"), "error": meta.get("error"),
                "segmentation": meta, "precondition": precondition}
    canvas_probe = dict(B.backdrop_probe(iso))
    canvas_probe.update({"role": "self_referential_canvas_hygiene_only",
                         "why": "画布是我们自己铺的中性底衬，探它不构成对原图的适用性证据"})
    try:
        measured = MC.measure(iso, card=card, clf=clf)
        report = factcard.evaluate(measured["metrics"], card)
    except Exception as exc:              # noqa: BLE001
        return {"route": "A", "status": "failed", "error": f"{type(exc).__name__}: {exc}",
                "segmentation": meta, "precondition": precondition, "canvas_probe": canvas_probe}
    measured_facts = {f["id"]: {"verdict": f["verdict"],
                                "checks": [{"metric": c["metric"], "value": c["value"],
                                            "verdict": c["verdict"]} for c in f["machine_checks"]]}
                      for f in report["facts"]}
    if applicable:
        facts = measured_facts
        scope = "evidence_on_isolated_subject"
        scope_why = ("原图满足路线 A 的适用前提，量测在抠出的主体上完成；它判的是尺寸与"
                     "颜色类事实，不证明主体就是同一 SKU（§4.5）")
    else:
        facts = {k: {"verdict": "unknown", "checks": v["checks"],
                     "why": "路线 A 的适用前提在原图上不成立，反事实画布的读数不作证据"}
                 for k, v in measured_facts.items()}
        scope = "counterfactual_only"
        scope_why = "原图不是受控底衬；画布上的量测只记录，不参与事实判定"
    return {"route": "A", "status": "ok", "segmentation": meta, "precondition": precondition,
            "canvas_probe": canvas_probe, "applicable": applicable,
            "verdict_scope": scope, "scope_why": scope_why,
            "overall": report["overall"], "isolated_facts": measured_facts, "facts": facts,
            "isolated": str(iso.relative_to(project))}


# ------------------------------------------------------------------ 路线 B
def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()


def claims_text(card: dict) -> str:
    return "\n".join(str(f["id"]) + ": " + str(f["claim"]) for f in card["facts"])


def vlm_call(model: str, messages: list, key: str, timeout: int = 180):
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
    body = {"model": model, "messages": messages}
    last = ""
    for i in range(3):
        try:
            r = requests.post(CHAT_URL, headers=headers, json=body, timeout=timeout)
        except Exception as exc:          # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
            time.sleep(3 * (i + 1))
            continue
        if r.status_code == 200:
            d = r.json()
            return d["choices"][0]["message"]["content"], (d.get("usage") or {}), last
        last = f"HTTP {r.status_code}: {r.text[:300]}"
        if r.status_code in (400, 404):
            break
    raise RuntimeError(last or "unknown error")


def parse_facts(text: str, card: dict) -> dict:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]
    i, j = raw.find("{"), raw.rfind("}")
    if i < 0 or j < 0:
        return {}, "no-json"
    try:
        d = json.loads(raw[i:j + 1])
    except Exception as exc:              # noqa: BLE001
        return {}, f"json-error: {type(exc).__name__}"
    out = {}
    for f in card["facts"]:
        fid = str(f["id"])
        cell = d.get(fid) or {}
        v = str(cell.get("verdict", "")).lower()
        out[fid] = {"verdict": {"same": "keep", "different": "risk",
                                "uncertain": "unknown"}.get(v, "unknown"),
                    "raw_verdict": v or "missing", "why": str(cell.get("why", ""))[:120]}
    return out, None

def append_ledger(ledger_path: Path, entry: dict):
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def route_b(item: dict, card: dict, ref: Path, key: str, out_dir: Path,
            ledger_path: Path) -> dict:
    prompt = VLM_INSTRUCT + claims_text(card)
    ref_hash, cand_hash = sha256_file(ref), sha256_file(Path(item["path"]))
    messages = [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": data_uri(ref)}},
        {"type": "image_url", "image_url": {"url": data_uri(Path(item["path"]))}}]}]
    action_id = sha256_bytes((prompt + ref_hash + cand_hash).encode("utf-8"))[:16]
    entry = {"action_id": action_id, "image_id": item["id"], "role": item["role"],
             "request_sha256": sha256_bytes(json.dumps(messages, ensure_ascii=False).encode("utf-8")),
             "reference_sha256": ref_hash, "candidate_sha256": cand_hash,
             "model": None, "status": "SUBMITTING", "usage": None, "elapsed_s": None,
             "error": None, "tried": [], "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

    text, used_model, usage, elapsed, err = None, None, None, None, None
    for model in VLM_MODELS:
        try:
            t0 = time.time()
            text, usage, _ = vlm_call(model, messages, key)
            used_model, elapsed = model, round(time.time() - t0, 2)
            break
        except Exception as exc:          # noqa: BLE001
            entry["tried"].append({"model": model, "error": str(exc)[:200]})
            err = str(exc)[:200]
    if text is None:
        entry.update({"status": "UNKNOWN", "error": err})
        append_ledger(ledger_path, entry)
        return {"route": "B", "status": "unknown", "error": err, "action_id": action_id,
                "tried": entry["tried"]}

    facts, parse_err = parse_facts(text, card)
    (out_dir / "route-b").mkdir(parents=True, exist_ok=True)
    (out_dir / "route-b" / (item["id"] + ".txt")).write_text(text + "\n", encoding="utf-8",
                                                            newline="\n")
    entry.update({"model": used_model, "usage": usage, "elapsed_s": elapsed,
                  "status": "SUCCEEDED" if not parse_err else "UNKNOWN",
                  "error": parse_err})
    append_ledger(ledger_path, entry)
    return {"route": "B", "status": "ok" if not parse_err else "unknown",
            "parse_error": parse_err, "action_id": action_id, "model": used_model,
            "usage": usage, "elapsed_s": elapsed, "facts": facts}


def classify(item: dict, res: dict) -> dict:
    """把一条路线的结论对照「事先写下的预期」，逐图记检出 / 漏报 / 误报 / Unknown。

    路线 B 的 risk 不是 hard fail，所以这里的「误报」指「在好图上报了风险」——
    它记的是风险信号的代价，不是路线坏了。
    """
    facts = (res or {}).get("facts") or {}
    verdicts = [v.get("verdict") for v in facts.values()]
    if res.get("route") == "A":
        # factcard 的结论域是 pass / manual / hard_fail / unknown / human，没有裸 fail；
        # 只认 "fail" 会让每一个真被拦下的负样本都记成漏报 —— 这是本脚本第一版的实际缺陷。
        flagged = [k for k, v in facts.items() if v.get("verdict") in ("hard_fail", "fail")]
        unknown = [k for k, v in facts.items() if v.get("verdict") in ("unknown", None)]
        # 只有真的给出 pass/hard_fail 的才算机器覆盖；不适用时整条路线覆盖为 0
        machine = [k for k, v in facts.items()
                   if v.get("verdict") in ("pass", "fail", "hard_fail")]
        signal = bool(flagged)
    else:
        flagged = [k for k, v in facts.items() if v.get("verdict") == "risk"]
        unknown = [k for k, v in facts.items() if v.get("verdict") in ("unknown", None)]
        machine = list(facts.keys())
        signal = bool(flagged)
    # 预期档位是事先写下的三类，含义不同，不能合并成「好图 / 坏图」两种：
    #   pass           无变异，必须判通过      → 报了信号才是误报
    #   not_hard_fail  有变异，但机器不得硬判    → 报了 risk 是命中了变异，不是误报
    #   not_pass       有变异，必须拦下         → 没信号才是漏报
    expect = item.get("expect") or ""
    clean = expect == "pass"
    mutated_only_human = expect == "not_hard_fail"
    must_catch = expect == "not_pass"
    return {"signal": signal, "flagged_facts": flagged, "unknown_facts": unknown,
            "machine_facts": len(machine),
            "detected": bool(must_catch and signal), "missed": bool(must_catch and not signal),
            "false_alarm": bool(clean and signal), "no_signal_on_good": bool(clean and not signal),
            "risk_on_human_only_case": bool(mutated_only_human and signal),
            "expect": expect, "verdicts": verdicts}


def merge_report(items: list, route_a_res: dict, route_b_res: dict) -> dict:
    rows = []
    for it in items:
        ra, rb = route_a_res.get(it["id"]), route_b_res.get(it["id"])
        row = {"id": it["id"], "role": it["role"], "expect": it["expect"],
               "expect_source": it.get("expect_source"), "human_required": it.get("human_required"),
               "sha256": it["sha256"]}
        if ra is not None:
            pre = ra.get("precondition") or {}
            row["A"] = {"status": ra.get("status"), "overall": ra.get("overall"),
                        "applicable": ra.get("applicable"),
                        "verdict_scope": ra.get("verdict_scope"),
                        "probe_share": pre.get("measured_share"),
                        "probe_source": pre.get("source"),
                        "probe_max_share": pre.get("max_share"),
                        "canvas_probe_share":
                            (ra.get("canvas_probe") or {}).get("subject_share_in_band"),
                        "facts": {k: v.get("verdict") for k, v in (ra.get("facts") or {}).items()},
                        "isolated_facts": {k: v.get("verdict")
                                           for k, v in (ra.get("isolated_facts") or {}).items()},
                        "comparison": classify(it, ra), "error": ra.get("error")}
        if rb is not None:
            row["B"] = {"status": rb.get("status"), "model": rb.get("model"),
                        "usage": rb.get("usage"),
                        "facts": {k: v.get("verdict") for k, v in (rb.get("facts") or {}).items()},
                        "raw": {k: v.get("raw_verdict") for k, v in (rb.get("facts") or {}).items()},
                        "comparison": classify(it, rb), "error": rb.get("error")}
        rows.append(row)

    def tally(key: str) -> dict:
        out = {"detected": 0, "missed": 0, "false_alarm": 0, "no_signal_on_good": 0,
               "risk_on_human_only_case": 0, "unknown_facts": 0, "ran": 0, "failed": 0}
        for r in rows:
            cell = r.get(key)
            if not cell:
                continue
            if cell.get("status") not in ("ok",):
                out["failed"] += 1
                continue
            out["ran"] += 1
            c = cell["comparison"]
            out["detected"] += 1 if c["detected"] else 0
            out["missed"] += 1 if c["missed"] else 0
            out["false_alarm"] += 1 if c["false_alarm"] else 0
            out["no_signal_on_good"] += 1 if c["no_signal_on_good"] else 0
            out["risk_on_human_only_case"] += 1 if c.get("risk_on_human_only_case") else 0
            out["unknown_facts"] += len(c["unknown_facts"])
        return out

    return {"schema": "demo-route-comparison/1", "rows": rows,
            "summary": {"A": tally("A"), "B": tally("B")},
            "change_cost": {
                "A": "换商品要新 metric profile + 阈值派生记录（代码级配置，见 §4.6 硬规矩 1）",
                "B": "换商品只改事实卡与提示词模板（数据级）",
                "C": "A 的配置成本 + B 的调用成本"}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="D1.R2 三种验证路线离线对照")
    ap.add_argument("--project", default=str(ROOT_DEFAULT))
    ap.add_argument("--sku", default=None)
    ap.add_argument("--route", choices=["a", "b", "both"], default="a")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 张（试点用）")
    ap.add_argument("--confirm-spend", action="store_true",
                    help="路线 B 会调用付费视觉模型；没有这个开关就不发请求")
    ap.add_argument("--remerge", action="store_true",
                    help="不重跑也不发请求：用已保存的 route-a.json / route-b.json 重算对照报告")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    project = Path(args.project).resolve()
    sku = args.sku
    if sku is None:
        cands = sorted(p.name for p in (project / "demo/fixture").iterdir()
                       if p.is_dir() and (p / "product.json").exists())
        if not cands:
            raise SystemExit("找不到商品包；用 --sku 指定")
        sku = cands[0]
    if str(project) not in sys.path:
        sys.path.insert(0, str(project))
    from demo.core import packages as PKG
    card_path = PKG.path_of(project, "card", sku)
    if not card_path.exists():
        raise SystemExit("缺事实卡：" + str(card_path))
    card = factcard.load_card(card_path)
    clf = factcard.PaletteClassifier(card["palette"])

    out_dir = project / "evals/product-demo/d1-r2"
    out_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = out_dir / "vlm-ledger.jsonl"
    items = build_comparison_set(project, sku)
    if args.limit:
        items = items[:args.limit]

    def write_report(a_res, b_res) -> None:
        report = merge_report(items, a_res, b_res)
        report["ran_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        report["fact_card"] = str(card_path.relative_to(project))
        report["reference"] = "evals/product-demo/fixture-design/pack/01-front-full.png"
        (out_dir / "route-comparison.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        print("汇总 A：" + json.dumps(report["summary"]["A"], ensure_ascii=False))
        print("汇总 B：" + json.dumps(report["summary"]["B"], ensure_ascii=False))
        print("报告：" + str((out_dir / "route-comparison.json").relative_to(project)))

    if args.remerge:
        # 只在“判据本身被修正”时用：报告是逐路线读数的派生值，重算它不需要再花一次调用。
        a_res = read_json(out_dir / "route-a.json") if (out_dir / "route-a.json").exists() else {}
        b_res = read_json(out_dir / "route-b.json") if (out_dir / "route-b.json").exists() else {}
        write_report(a_res, b_res)
        return 0

    route_a_res, route_b_res = {}, {}
    rc = 0

    if args.route in ("a", "both"):
        print("路线 A（分割后量测）：" + str(len(items)) + " 张")
        for it in items:
            res = route_a(it, card, clf, out_dir, project, sku)
            route_a_res[it["id"]] = res
            mark = {"ok": "OK  ", "environment_blocked": "ENV ", "failed": "FAIL"}.get(
                res.get("status"), "??  ")
            pre = res.get("precondition") or {}
            print("  [" + mark + "] " + it["id"]
                  + " 原图probe=" + str(pre.get("measured_share"))
                  + " 适用=" + str(res.get("applicable"))
                  + " overall=" + str(res.get("overall")) + " " + str(res.get("error") or ""))
            if res.get("status") != "ok":
                rc = 2
        (out_dir / "route-a.json").write_text(
            json.dumps(route_a_res, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

    if args.route in ("b", "both"):
        key = os.environ.get("DASHSCOPE_API_KEY") or ""
        if not args.confirm_spend:
            print("路线 B 需要 --confirm-spend（会调用付费视觉模型）；本次不发请求。")
            rc = 2
        elif not key:
            print("没有 DASHSCOPE_API_KEY，路线 B 记未验证（不以手工规则顶替）。")
            rc = 2
        else:
            ref = project / "evals/product-demo/fixture-design/pack/01-front-full.png"
            print("路线 B（参考图条件视觉判断）：" + str(len(items)) + " 张，参考图 "
                  + ref.name)
            for it in items:
                res = route_b(it, card, ref, key, out_dir, ledger_path)
                route_b_res[it["id"]] = res
                print("  [" + ("OK  " if res.get("status") == "ok" else "UNK ") + "] "
                      + it["id"] + " model=" + str(res.get("model"))
                      + " risk=" + str(sum(1 for v in (res.get("facts") or {}).values()
                                            if v.get("verdict") == "risk"))
                      + " " + str(res.get("error") or ""))
                if res.get("status") != "ok":
                    rc = 2
            (out_dir / "route-b.json").write_text(
                json.dumps(route_b_res, ensure_ascii=False, indent=2), encoding="utf-8",
                newline="\n")

    write_report(route_a_res, route_b_res)
    return rc


if __name__ == "__main__":
    sys.exit(main())
