# -*- coding: utf-8 -*-
"""事实卡加载、调色板分类与判据求值 —— 这一层没有任何商品专属常数。

为什么要有这一层
----------------
在它之前，`measure_f1_f8.py` 里写着

    TARGET  = {"ratio": 3.1, "teal_share": 0.72, ...}
    PALETTE = {"teal": "#0F6B66", ...}

以及一套写死的色相规则（`r > g > b and ... and lum < 110`）。
那些数字和规则只对 Aster 01 这一个杯子和这一套配色成立 ——
**换一件商品就得改代码**，所以那不是产品能力，是一次性的夹具工艺。

本模块把两类东西分开：

    数据（住在 product.json 里）：调色板锚点、每条事实的声明值与三档容差
    代码（住在这里）：怎么把像素判给某个角色、怎么把量测值判成 pass/manual/hard_fail

于是「换商品」的动作从"改 Python"变成"换 JSON"，
而这件事**可以被证伪**：同一 metric_profile 下换一件商品，若仍需改本文件，这条设计就不成立。

光照不变性
----------
圆柱体商品必然有明暗渐变，而同一块青绿在亮面与暗面的 L 相差可达 20。
所以分类用加权最近锚点：L 差按 0.35 计权，色度差按 1 计权。
这个权重是**类目级**的（任何有明暗渐变的商品都适用），不是商品专属 —— 见 _NEUTRAL_L_WEIGHT。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CARD = ROOT / "demo" / "fixture" / "aster-01" / "product.json"

# 光照不变性权重：把 L 差打折后再比较，避免同一商品的暗面被判给深色部件。
# 它不是"给 Aster 01 调出来的"——任何带明暗渐变的商品都需要它。
_NEUTRAL_L_WEIGHT = 0.35

# 判据三档的稳定名字。状态是闭集合，报告和退出码都据它决定。
PASS, MANUAL, HARD_FAIL, UNKNOWN = "pass", "manual", "hard_fail", "unknown"

# 量测项的中文标签与单位，只影响报告可读性，不参与判定。
METRIC_LABELS = {
    "aspect_h_over_w": ("F1 高宽比（高/宽）", ""),
    "body_upper_share": ("F2 上段占杯体", ""),
    "upper_color_delta_e": ("F2 上段实测色与声明色 ΔE", ""),
    "body_lower_share": ("F3 下段占杯体", ""),
    "rib_count": ("F3 防滑套筋条数", " 条"),
    "lid_share": ("F4 杯盖占整器高", ""),
    "trim_span_count": ("F5 独立装饰环段数", " 段"),
    "trim_share": ("F5 装饰环占整器高", ""),
    "trim_top_position": ("F5 装饰环上沿位置（占整器高）", ""),
    "bottom_spread_share": ("F6 底部轮廓离散（占主体宽）", ""),
    "bottom_ring_present": ("F6 检出底部防滑圈", ""),
    "body_protrusion": ("F7 杯身最大凸出（占主体宽）", ""),
    "extra_area_share": ("F7 主体外像素占比", ""),
    "text_proxy_blobs": ("F8 小高梯度块（文字代理，不判定）", " 个"),
}


def hex_to_rgb(text: str) -> tuple[float, float, float]:
    s = text.strip().lstrip("#")
    return (float(int(s[0:2], 16)), float(int(s[2:4], 16)), float(int(s[4:6], 16)))


def rgb_to_hex(rgb) -> str:
    return "#%02X%02X%02X" % tuple(int(round(float(max(0.0, min(255.0, v))))) for v in rgb)


def srgb_to_lab(rgb) -> np.ndarray:
    """sRGB(0-255) -> CIE L*a*b*(D65)。接受 (...,3)，返回同形状。"""
    c = np.asarray(rgb, dtype=np.float64) / 255.0
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = c @ m.T
    t = xyz / np.array([0.95047, 1.0, 1.08883])
    d = 6.0 / 29.0
    f = np.where(t > d ** 3, np.cbrt(t), t / (3 * d * d) + 4.0 / 29.0)
    return np.stack([116.0 * f[..., 1] - 16.0,
                     500.0 * (f[..., 0] - f[..., 1]),
                     200.0 * (f[..., 1] - f[..., 2])], axis=-1)


def delta_e(lab_a, lab_b) -> float:
    """CIE76 色差。够用：本层只做"离哪个锚点更近"，不做色域精细判定。"""
    d = np.asarray(lab_a, dtype=np.float64) - np.asarray(lab_b, dtype=np.float64)
    return float(np.sqrt(np.sum(d * d)))


class PaletteClassifier:
    """把像素判给事实卡里声明的角色，或判为 'other'。锚点全部来自数据。"""

    def __init__(self, palette: dict) -> None:
        self.roles = [r["role"] for r in palette["roles"]]
        self.hexes = {r["role"]: r["hex"] for r in palette["roles"]}
        self.labs = {r["role"]: srgb_to_lab(np.array(hex_to_rgb(r["hex"]))) for r in palette["roles"]}
        self.max_de = float(palette.get("max_delta_e", 26.0))

    def distance(self, role: str, rgb) -> float:
        lab = srgb_to_lab(np.asarray(rgb, dtype=np.float64))
        ref = self.labs[role]
        dl = (lab[0] - ref[0]) * _NEUTRAL_L_WEIGHT
        da, db = lab[1] - ref[1], lab[2] - ref[2]
        return float(np.sqrt(dl * dl + da * da + db * db))

    def classify(self, rgb) -> str:
        best, best_d = "other", float("inf")
        for role in self.roles:
            d = self.distance(role, rgb)
            if d < best_d:
                best, best_d = role, d
        return best if best_d <= self.max_de else "other"

    def delta_e_to(self, role: str, rgb) -> float:
        return delta_e(srgb_to_lab(np.asarray(rgb, dtype=np.float64)), self.labs[role])


SLOTS = ("body_upper", "body_lower", "trim")
REQUIRED_TOP = ("schema", "sku", "version", "metric_profile", "fact_source", "palette", "facts")


class CardError(Exception):
    """事实卡不合法。宁可发卡失败，也不让一张自相矛盾的卡进入判定。"""


def _band(spec, where: str) -> dict:
    if not isinstance(spec, dict) or not spec:
        raise CardError(where + " 必须是非空对象，收到：" + repr(spec))
    out = {}
    for key in ("min", "max"):
        if key in spec:
            try:
                out[key] = float(spec[key])
            except (TypeError, ValueError):
                raise CardError(where + " 的 " + key + " 不是数字：" + repr(spec[key]))
    if not out:
        raise CardError(where + " 既没有 min 也没有 max：" + repr(spec))
    if "min" in out and "max" in out and out["min"] > out["max"]:
        raise CardError(where + " 的 min > max：" + repr(spec))
    return out


def _contains(outer: dict, inner: dict) -> bool:
    """outer 是否包住 inner（人工档必须比通过档宽，否则判定自相矛盾）。"""
    if "min" in inner and ("min" not in outer or outer["min"] > inner["min"]):
        return False
    if "max" in inner and ("max" not in outer or outer["max"] < inner["max"]):
        return False
    return True


def validate_card(card: dict) -> dict:
    if card.get("schema") != "demo-fact-card/1":
        raise CardError("不是受支持的事实卡 schema：" + repr(card.get("schema")))
    for key in REQUIRED_TOP:
        if key not in card:
            raise CardError("事实卡缺顶层字段：" + key)

    pal = card["palette"] or {}
    max_de = pal.get("max_delta_e")
    if not isinstance(max_de, (int, float)) or max_de <= 0:
        raise CardError("palette.max_delta_e 必须是正数，收到：" + repr(max_de))
    roles = pal.get("roles") or []
    if not roles:
        raise CardError("palette.roles 为空 —— 没有锚点就没法把像素判给任何角色")
    seen_roles, seen_slots = set(), set()
    for r in roles:
        for key in ("role", "hex", "slot"):
            if not r.get(key):
                raise CardError("palette.roles 缺字段 " + key + "：" + repr(r))
        try:
            hex_to_rgb(r["hex"])
        except Exception as exc:
            raise CardError("palette.roles 的 hex 不是合法颜色 " + repr(r["hex"])
                            + "（" + type(exc).__name__ + "）")
        if r["role"] in seen_roles:
            raise CardError("角色名重复：" + r["role"])
        if r["slot"] in seen_slots:
            raise CardError("语义槽位重复：" + r["slot"])
        seen_roles.add(r["role"])
        seen_slots.add(r["slot"])

    facts = card["facts"] or []
    ids = [f.get("id") for f in facts]
    if len(set(ids)) != len(ids):
        raise CardError("事实 id 有重复：" + str(ids))
    for f in facts:
        where = "事实 " + str(f.get("id"))
        if not f.get("id") or not f.get("claim"):
            raise CardError(where + " 缺 id 或 claim")
        for chk in f.get("machine_checks") or []:
            if not chk.get("metric"):
                raise CardError(where + " 的判据缺 metric")
            label = where + "/" + str(chk["metric"])
            band = _band(chk.get("pass"), label + " 的 pass")
            if chk.get("manual"):
                man = _band(chk["manual"], label + " 的 manual")
                if not _contains(man, band):
                    raise CardError(label + " 的人工档没有包住通过档：manual=" + repr(chk["manual"])
                                    + " pass=" + repr(chk["pass"]))
        for dg in f.get("diagnostics") or []:
            if not dg.get("metric"):
                raise CardError(where + " 的登记读数缺 metric")
            if dg.get("gating") is not False:
                raise CardError(where + "/" + str(dg.get("metric"))
                                + " 是登记读数，必须显式写 gating: false")
    return card


def load_card(path=None) -> dict:
    p = Path(path) if path else DEFAULT_CARD
    card = json.loads(Path(p).read_text(encoding="utf-8"))
    return validate_card(card)


def _within(value: float, spec: dict) -> bool:
    if "min" in spec and value < float(spec["min"]):
        return False
    if "max" in spec and value > float(spec["max"]):
        return False
    return True


def _verdict(value, check: dict) -> tuple[str, str]:
    """单条机器判据 -> (档位, 理由)。缺量测值一律 unknown，不猜。"""
    if value is None:
        return UNKNOWN, "该项没有量测值（可能未检出对应部件），不推断"
    v = float(value)
    if _within(v, check.get("pass", {})):
        return PASS, ""
    manual = check.get("manual")
    if manual and _within(v, manual):
        return MANUAL, "落在人工档：" + json.dumps(check.get("pass", {}), ensure_ascii=False)
    return HARD_FAIL, "超出人工档：" + json.dumps(check.get("manual") or check.get("pass", {}),
                                              ensure_ascii=False)


_RANK = {PASS: 0, MANUAL: 1, UNKNOWN: 2, HARD_FAIL: 3}


def evaluate(metrics: dict, card: dict) -> dict:
    """按事实卡的机器判据逐条求值。人工项与代理项一律不改写成判定。"""
    facts = []
    for fact in card["facts"]:
        checks = []
        for check in fact.get("machine_checks", []) or []:
            value = metrics.get(check["metric"])
            verdict, why = _verdict(value, check)
            checks.append({"metric": check["metric"], "declared": check.get("declared"),
                           "value": value, "verdict": verdict, "why": why})
        worst = PASS
        for c in checks:
            if _RANK[c["verdict"]] > _RANK[worst]:
                worst = c["verdict"]
        if not checks:
            worst = fact.get("modality", "human") == "human" and "human" or UNKNOWN
        facts.append({
            "id": fact["id"],
            "claim": fact["claim"],
            "modality": fact.get("modality", "mixed"),
            "verdict": worst if checks else "human",
            "machine_checks": checks,
            "human_only_checks": fact.get("human_only_checks", []),
            "human_note": fact.get("human_note"),
        })
    machine = [f for f in facts if f["machine_checks"]]
    agg = PASS
    for f in machine:
        if _RANK.get(f["verdict"], 0) > _RANK[agg]:
            agg = f["verdict"]
    return {
        "card": {"sku": card["sku"], "version": card["version"],
                 "metric_profile": card["metric_profile"], "fact_source": card["fact_source"]},
        "overall": agg,
        "machine_facts": len(machine),
        "human_facts": [f["id"] for f in facts if not f["machine_checks"]],
        "facts": facts,
    }


EXIT = {PASS: 0, MANUAL: 3, UNKNOWN: 3, HARD_FAIL: 4}


def format_report(report: dict, title: str, extra_lines=None) -> str:
    lines = ["# " + title, "",
             "事实卡：`" + report["card"]["sku"] + "` v" + report["card"]["version"]
             + " · 量测实现 " + report["card"]["metric_profile"]
             + " · 来源 " + report["card"]["fact_source"], "",
             "综合判定：**" + report["overall"] + "**"
             + "（机器判据 " + str(report["machine_facts"]) + " 条；纯人工事实 "
             + ("、".join(report["human_facts"]) or "无") + "，机器不改写）", ""]
    if extra_lines:
        lines += list(extra_lines) + [""]
    lines += ["| 事实 | 机器判定 | 项 | 实测 | 声明/档位 |", "|---|---|---|---|---|"]
    for f in report["facts"]:
        if not f["machine_checks"]:
            lines.append("| " + f["id"] + " | 人工 | " + "；".join(f["human_only_checks"])
                         + " | —— | 不由机器判定 |")
            continue
        for i, c in enumerate(f["machine_checks"]):
            label = METRIC_LABELS.get(c["metric"], (c["metric"], ""))[0]
            unit = METRIC_LABELS.get(c["metric"], (c["metric"], ""))[1]
            shown = "—" if c["value"] is None else str(c["value"]) + unit
            declared = "—" if c["declared"] is None else str(c["declared"]) + unit
            lines.append("| " + (f["id"] if i == 0 else "") + " | "
                         + (c["verdict"] if i == 0 else "") + " | " + label + " | "
                         + shown + " | " + declared + " |")
        for note in f["human_only_checks"]:
            lines.append("| " + f["id"] + " | 人工 | " + note + " | —— | 不由机器判定 |")
    lines += ["", "## 未通过的项", ""]
    bad = [c for f in report["facts"] for c in f["machine_checks"] if c["verdict"] != PASS]
    if not bad:
        lines.append("无。")
    for c in bad:
        lines.append("- " + c["metric"] + " = " + str(c["value"]) + " → " + c["verdict"]
                     + ("（" + c["why"] + "）" if c["why"] else ""))
    lines.append("")
    return "\n".join(lines)
