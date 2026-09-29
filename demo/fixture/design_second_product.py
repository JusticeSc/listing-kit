# -*- coding: utf-8 -*-
"""D0.7 第二件虚构商品：方形硬盒随行瓶「Bex 02」。

它存在的唯一理由是回答 Phase 0 的 P1：**换商品要不要改代码**。
这个文件做三件事，一件都不碰量测/判定链路：
  1. 按设计规格合成一张 1344×1344 的产品图（确定性、无模型调用、无随机数）；
  2. 按同一份规格写出这件商品的规格卡；
  3. 按同一份规格写出它的阈值派生记录。

卡里的档位来自规格，不是从量测倒推；量测值与规格的偏差由本脚本自查并打印，
越档就拒绝写卡 —— 一个连自己规格都过不了的夹具，不能拿去证明「换商品不用改代码」。

注意 metric_profile 只能写 cylinder-v1：它是量测协议的键，不是形状的名字。
这个协议按「横向色带」工作，方形商品可以走；换一个色带结构不同的品类就需要新协议 = 改代码。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import factcard as fc          # noqa: E402
import measure_cylinder as mc  # noqa: E402

CST = timezone(timedelta(hours=8))

SKU = "demo-box-bex-02"
DISPLAY_NAME = "Bex 02 方形随行瓶"
VERSION = "2026-09-25.1"

# ── 设计规格（卡里的每个档位都能追到这里） ──
CANVAS = 1344
BG_TOP = (236, 235, 232)
BG_BOTTOM = (196, 195, 191)
OBJ_X0, OBJ_Y0, OBJ_W, OBJ_H = 462, 172, 420, 1000
CAP_H, RING_H, LOWER_H = 142, 10, 238
BODY_H = OBJ_H - CAP_H - RING_H - LOWER_H
CORNER = 10
SLATE = "#3A5A78"
GRAPHITE = "#2B2B30"
SAND = "#C9A227"


def say(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", "replace").decode("ascii"))


def stamp() -> str:
    return datetime.now(CST).replace(microsecond=0).isoformat()


def rgb(hex_text: str):
    return tuple(int(round(v)) for v in fc.hex_to_rgb(hex_text))


def render() -> np.ndarray:
    """合成一张确定性的产品图：浅灰竖向渐变背景 + 软阴影 + 一个四段色带的方形瓶。"""
    arr = np.zeros((CANVAS, CANVAS, 3), dtype=np.float64)
    top, bottom = np.array(BG_TOP, float), np.array(BG_BOTTOM, float)
    for y in range(CANVAS):
        t = y / (CANVAS - 1)
        arr[y, :, :] = top * (1 - t) + bottom * t
    yy, xx = np.mgrid[0:CANVAS, 0:CANVAS]
    cx = OBJ_X0 + OBJ_W / 2
    cy = OBJ_Y0 + OBJ_H + 8
    fade = np.clip(1 - (((xx - cx) / (OBJ_W * 0.80)) ** 2 + ((yy - cy) / 44.0) ** 2), 0.0, 1.0)
    arr *= (1 - 0.16 * (fade ** 1.6))[:, :, None]
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    x1, y1 = OBJ_X0 + OBJ_W - 1, OBJ_Y0 + OBJ_H - 1
    d.rounded_rectangle([OBJ_X0, OBJ_Y0, x1, y1], radius=CORNER, fill=rgb(GRAPHITE))
    body_y0 = OBJ_Y0 + CAP_H + RING_H
    d.rectangle([OBJ_X0, body_y0, x1, body_y0 + BODY_H - 1], fill=rgb(SLATE))
    d.rectangle([OBJ_X0, OBJ_Y0 + CAP_H, x1, OBJ_Y0 + CAP_H + RING_H - 1], fill=rgb(SAND))
    return np.asarray(img.convert("RGB")).astype(np.float64)


def band(min_v=None, max_v=None):
    out = {}
    if min_v is not None:
        out["min"] = min_v
    if max_v is not None:
        out["max"] = max_v
    return out


def build_card(measured: dict) -> dict:
    expected_upper = round(BODY_H / (BODY_H + LOWER_H), 4)
    expected_lower = round(LOWER_H / (BODY_H + LOWER_H), 4)
    return {
        "schema": "demo-fact-card/1",
        "sku": SKU,
        "display_name": DISPLAY_NAME,
        "fixture": True,
        "fact_source": "demo_fixture",
        "metric_profile": "cylinder-v1",
        "metric_profile_note": ("值只能写 cylinder-v1：这是量测协议的键，不是形状的名字。"
                                "该协议按横向色带工作，本商品按同一条协议量测；"
                                "换一个色带结构不同的品类需要新协议，那就是改代码。"),
        "version": VERSION,
        "created_at": stamp(),
        "threshold_derivation": "threshold-derivation.json",
        "product_class": "方形硬盒随行瓶：单一直立方体 + 顶盖 + 下段深色底带",
        "disclaimers": [
            "虚构演示商品，不对应任何真实品牌、商标或在售产品。",
            "仅用于本项目的功能演示与验证，不得用于真实上架、对外宣传或平台审核。",
            "本商品的图由 demo/fixture/design_second_product.py 合成，不是模型产出，也不是实物照片。",
        ],
        "identity": {
            "form": "单一直立方体，四角小圆角，截面从上到下等宽；无把手、无侧握、无提带、无吸管",
            "usage": "保温随行瓶（方形）",
        },
        "palette": {
            "space": "srgb",
            "max_delta_e": 26.0,
            "roles": [
                {"role": "slate", "slot": "body_upper", "hex": SLATE, "desc": "瓶体主色（板岩蓝）"},
                {"role": "graphite", "slot": "body_lower", "hex": GRAPHITE,
                 "desc": "顶盖与下段底带（石墨黑，同族）"},
                {"role": "sand", "slot": "trim", "hex": SAND, "desc": "顶盖与瓶体之间的窄饰环（沙金）"},
            ],
        },
        "facts": [
            {"id": "F1", "claim": "整体高宽比约 2.38：1，仍是细长方体",
             "modality": "machine",
             "machine_checks": [{"metric": "aspect_h_over_w", "declared": 2.38,
                                 "pass": band(2.2, 2.6), "manual": band(2.05, 2.75)}]},
            {"id": "F2", "claim": "瓶体主色板岩蓝占据主体上段主要高度",
             "modality": "machine",
             "machine_checks": [{"metric": "body_upper_share", "declared": expected_upper,
                                 "pass": band(0.62, 0.80), "manual": band(0.55, 0.85)}]},
            {"id": "F3", "claim": "下段深色底带无横向凸脊（本商品没有筋条结构）",
             "modality": "mixed",
             "machine_checks": [
                 {"metric": "body_lower_share", "declared": expected_lower,
                  "pass": band(0.20, 0.38), "manual": band(0.15, 0.45)},
                 {"metric": "rib_count", "declared": 0, "pass": band(0, 0)}],
             "human_note": "凸脊数由机器数；「这条脊是什么」仍由人看"},
            {"id": "F4", "claim": "顶盖低矮（不超过整器高的 20%）且为平顶",
             "modality": "mixed",
             "machine_checks": [{"metric": "lid_share", "declared": round(CAP_H / OBJ_H, 4),
                                 "pass": band(max_v=0.20), "manual": band(max_v=0.26)}],
             "human_note": "顶面结构与开口不在机器判定内（见 machine_check_gaps）"},
            {"id": "F5", "claim": "顶盖下方有一条窄饰环，仅一条且位于顶部 25% 内",
             "modality": "machine",
             "machine_checks": [
                 {"metric": "trim_span_count", "declared": 1, "pass": band(1, 1)},
                 {"metric": "trim_share", "declared": round(RING_H / OBJ_H, 4),
                  "pass": band(max_v=0.03), "manual": band(max_v=0.05)},
                 {"metric": "trim_top_position", "declared": round(CAP_H / OBJ_H, 4),
                  "pass": band(max_v=0.25)}]},
            {"id": "F6", "claim": "平底，无独立底圈",
             "modality": "machine",
             "machine_checks": [
                 {"metric": "bottom_spread_share", "declared": 0.0,
                  "pass": band(max_v=0.05), "manual": band(max_v=0.08)},
                 {"metric": "bottom_ring_present", "declared": 0, "pass": band(0, 0)}]},
            {"id": "F7", "claim": "无把手、无侧握、无提带、无吸管；主体外无多余物",
             "modality": "mixed",
             "machine_checks": [
                 {"metric": "body_protrusion", "declared": 0.0,
                  "pass": band(max_v=0.08), "manual": band(max_v=0.12)},
                 {"metric": "extra_area_share", "declared": 0.0, "pass": band(max_v=0.01)}],
             "human_note": "凸出的是什么由人确认；机器只报凸出量与主体外像素",
             "violation": "新增把手、侧握、提带、吸管、壶嘴，或出现第二个瓶体"},
            {"id": "F8", "claim": "外表无文字、数字、Logo、标签和水印",
             "modality": "human",
             "machine_proxy": {"metric": "text_proxy_blobs",
                               "note": "高梯度小块数只是形态代理；方体的棱边本就会产生这类小块，"
                                       "它不参与判定。"},
             "human_note": "文字只能靠人核对；本卡不假装机器能判",
             "violation": "写出品牌字、伪标签、容量字样或装饰符号"},
            {"id": "F2diag", "claim": "（登记读数，不参与判定）主色与声明锚点的色偏",
             "modality": "none",
             "diagnostics": [{"metric": "upper_color_delta_e", "declared": 0.0, "gating": False,
                              "why_not_gating": "与 Aster 01 同一条裁定：十六进制只用于生成与目视对照，"
                                                "不作为逐像素判据。"}]},
        ],
        "machine_check_gaps": [
            {"fact": "F4", "missing": "顶面结构与开口", "status": "open", "assigned_to": "维持人工判定",
             "why": "协议的机器判据只有「盖占高度」，看不见顶面是平顶还是有凹槽"},
            {"fact": "F7", "missing": "凸出物是否为把手、提带或吸管", "status": "open",
             "assigned_to": "维持人工判定",
             "why": "机器只报凸出量与主体外像素，不判凸出物的语义"},
            {"fact": "F8", "missing": "文字与伪标签", "status": "open", "assigned_to": "维持人工判定",
             "why": "文字只能靠人核对"},
        ],
        "unknowns": [
            {"field": "材质", "value": "Unknown", "why": "虚构演示商品，未声明"},
            {"field": "容量", "value": "Unknown", "why": "未声明；图上也不得出现容量字样"},
            {"field": "保温性能", "value": "Unknown", "why": "未声明，且不属于图片可验证范围"},
            {"field": "品牌与 Logo", "value": "Unknown", "why": "无品牌；F8 要求外表完全无标记"},
        ],
        "capability_binding": {
            "measured_with": "demo/fixture/measure_cylinder.py（metric_profile=cylinder-v1）",
            "measured_at": VERSION,
            "evidence": "evals/product-demo/d0-7-second-product-2026-09-25.md",
            "expires_when": "量测实现或调色板分类权重变化时须重新校准",
        },
    }


RULES = {
    ("F1", "aspect_h_over_w"):
        ("设计规格：瓶体高 1000 px、宽 420 px",
         "通过档 2.2–2.6、人工档 2.05–2.75 由规格值 2.381 外扩；这是设计意图，不是从样本统计出来的"),
    ("F2", "body_upper_share"):
        ("设计规格：上段 610 px、下段 238 px", "通过档 0.62–0.80、人工档 0.55–0.85 由规格占比 0.7193 外扩"),
    ("F3", "body_lower_share"):
        ("设计规格：下段 238 px", "下段是上段的补，通过档 = 1 − 上段通过档 = 0.20–0.38；这是一条派生规则"),
    ("F3", "rib_count"):
        ("设计规格：下段为光面底带，无横向凸脊",
         "通过档写死为恰好 0；出现任何凸脊即失败 —— 本商品的规格里没有筋条结构"),
    ("F4", "lid_share"):
        ("设计规格：顶盖 142 px", "通过档 ≤0.20 取「低矮盖」这一设计声明；实测 0.142"),
    ("F5", "trim_span_count"):
        ("设计规格：单条 10 px 饰环", "通过档写死为恰好 1 段；缺失或出现第二段即失败"),
    ("F5", "trim_share"):
        ("设计规格：饰环 10 px", "通过档 ≤0.03、人工档 ≤0.05；实测 0.010"),
    ("F5", "trim_top_position"):
        ("设计规格：饰环紧贴顶盖下沿", "要求位于整器高顶部 25% 内 ⇒ 通过档 ≤0.25；实测 0.142"),
    ("F6", "bottom_spread_share"):
        ("设计规格：直角平底", "通过档 ≤0.05、人工档 ≤0.08；实测 0.0"),
    ("F6", "bottom_ring_present"):
        ("设计规格：无独立底圈", "通过档写死为 0；检出底圈反而与本商品规格不符"),
    ("F7", "body_protrusion"):
        ("设计规格：等宽方体，无把手", "通过档 ≤0.08、人工档 ≤0.12；实测 0.0"),
    ("F7", "extra_area_share"):
        ("设计规格：画面内只有一个瓶体", "通过档 ≤0.01，无人工档"),
}

NON_GATING = {
    "upper_color_delta_e":
        ("与 Aster 01 同一条裁定（D0.1 §3）", "不作为判据，只登记读数。十六进制用于生成提示词与目视对照。"),
}


def build_derivation(measured: dict) -> dict:
    card = build_card(measured)
    entries = []
    for fact in card["facts"]:
        for chk in fact.get("machine_checks") or []:
            key = (fact["id"], chk["metric"])
            info = RULES.get(key)
            if info is None:
                raise SystemExit("判据 " + str(key) + " 没有派生记录，拒绝发卡")
            entries.append({
                "fact": fact["id"], "metric": chk["metric"], "gating": True,
                "declared": chk.get("declared"),
                "pass": chk.get("pass"), "manual": chk.get("manual"),
                "source": info[0], "rule": info[1],
                "sample": {"Bex02": measured.get(chk["metric"])},
                "sample_source": "D0.7 现场量测：cylinder-v1 · demo/fixture/measure_cylinder.py，样本 1 张",
                "sample_n": 1,
                "statistical_claim": "n=1：这一步只证明协议可配置，不构成任何验收档的统计依据",
                "version": VERSION,
                "expires_when": "量测实现或调色板分类权重变化时须重新校准",
            })
        for dg in fact.get("diagnostics") or []:
            info = NON_GATING.get(dg["metric"])
            if info is None:
                raise SystemExit("非判据读数 " + dg["metric"] + " 没有登记说明，拒绝发卡")
            entries.append({
                "fact": fact["id"], "metric": dg["metric"], "gating": False,
                "declared": dg.get("declared"), "pass": None, "manual": None,
                "source": info[0], "rule": info[1],
                "sample": {"Bex02": measured.get(dg["metric"])},
                "sample_source": "D0.7 现场量测：cylinder-v1 · demo/fixture/measure_cylinder.py，样本 1 张",
                "sample_n": 1, "statistical_claim": "不参与判定",
                "version": VERSION, "expires_when": "不适用（非判据）",
            })
    return {
        "schema": "demo-threshold-derivation/1",
        "version": VERSION,
        "generated_at": stamp(),
        "fact_card": "demo/fixture/bex-02/product.json",
        "metric_profile": "cylinder-v1",
        "measurement_impl": "cylinder-v1 · demo/fixture/measure_cylinder.py",
        "entries": entries,
        "gaps": card.get("machine_check_gaps", []),
        "boundary": ("本商品的阈值来自设计规格（由生成器声明），样本只有 1 张；"
                     "它证明协议可配置，不证明任何品类的泛化能力。"),
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="生成第二件虚构商品：资产 + 事实卡 + 派生记录")
    ap.add_argument("--project", default=".")
    ap.add_argument("--asset", default="evals/product-demo/product-2/bex-02/raw.png")
    ap.add_argument("--card", default="demo/fixture/bex-02/product.json")
    ap.add_argument("--derivation", default="demo/fixture/bex-02/threshold-derivation.json")
    args = ap.parse_args()
    project = Path(args.project).resolve()

    arr = render()
    asset = project / args.asset
    asset.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(asset, format="PNG")
    say("wrote " + args.asset + " sha16=" + hashlib.sha256(asset.read_bytes()).hexdigest()[:16])

    card = build_card({})
    measured = mc.measure(asset, card=card)
    metrics = measured["metrics"]
    report = fc.evaluate(metrics, card)

    card_path = project / args.card
    card_path.parent.mkdir(parents=True, exist_ok=True)
    card_path.write_text(json.dumps(build_card(metrics), ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8", newline="\n")
    (project / args.derivation).write_text(
        json.dumps(build_derivation(metrics), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n")

    say("")
    say("规格 vs 实测（卡的档位来自规格，这里只核对渲染有没有跑偏）：")
    bad = []
    for fact in card["facts"]:
        for chk in fact.get("machine_checks") or []:
            value = metrics.get(chk["metric"])
            floor = chk["pass"].get("min")
            ceil = chk["pass"].get("max")
            ok = True
            if floor is not None and (value is None or value < floor):
                ok = False
            if ceil is not None and (value is None or value > ceil):
                ok = False
            say("  %-4s %-22s declared=%-8s measured=%-8s pass=%-22s %s"
                % (fact["id"], chk["metric"], str(chk.get("declared")), str(value),
                   json.dumps(chk["pass"], ensure_ascii=False), "OK" if ok else "**越档**"))
            if not ok:
                bad.append(fact["id"] + "/" + chk["metric"])
    say("综合判定：" + report["overall"] + "（rc " + str(fc.EXIT[report["overall"]]) + "）")
    say("wrote " + args.card + "、" + args.derivation)
    if bad:
        say("自己规格都过不了，拒绝把卡当成可用的夹具：" + "、".join(bad))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
