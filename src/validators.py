"""校验层：强度按**失败成本**分配，而不是所有坑位做同样一套。

    位置 1（主图）  strict  程序判定、必须零错误 —— 出错是 listing 降权/下架
    位置 2/3/7      medium  尺寸 + 文字存在性 + 水印 —— 出错是转化率损失
    位置 4/5/6      loose   尺寸 + 明显崩坏 —— 出错只是不好看，交人工

说明：文字检测为**启发式**（边缘非白 + 底部深色像素），不是 OCR。
      精确 OCR 校对（确认每个汉字没渲染错）是后续项，需引入 OCR 依赖。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

WHITE_MIN = 250        # JPEG 压缩后纯白会有噪点，250 以上视为白
NON_WHITE_DELTA = 18   # 与纯白的距离阈值，低于此值算背景
DARK_MAX = 120         # 判定"有文字"的深色阈值

# ------------------------------------------------------------
# 已实现的规则名 —— **唯一权威清单**
#   src/schema.py 用它拦截"声明了但没实现"的规则名。
#   v1 的 slots.yaml 里写着 no_watermark / text_render_ok，本模块从来没有这两个规则，
#   于是「声明了校验」与「实际静默跳过」在外表上完全一样 —— 这是最危险的一类死字段：
#   它让人以为有保护。规则名必须先在这里登记，才能写进坑位表。
# ------------------------------------------------------------
KNOWN_RULES: dict[str, str] = {
    "white_bg_purity": "边缘带是否纯白（位置 1 平台硬要求）",
    "product_fill": "产品外接框占画面比例是否达 product_fill_pct",
    "has_text_block": "位置 1 专用：边缘带是否有文字 / 水印 / 角标",
    "edge_clean": "边缘带是否干净（启发式抓贴边水印、边框）",
    "text_present": "确认叠字确实渲染上去了（底部区域存在深色像素）",
    "aspect_ratio": "是否 1:1",
    "long_side_px": "最长边是否达平台下限",
    "file_size": "文件体积是否超限",
    "filename_has_upc": "文件名是否含产品标识",
}


def _arr(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB")).astype(np.float32)


def check_white_bg(path: Path, band: float = 0.04) -> dict:
    """采样四条边带，判断是否为纯白背景。"""
    a = _arr(path)
    h, w = a.shape[:2]
    b = max(2, int(min(h, w) * band))
    strips = np.concatenate([
        a[:b, :].reshape(-1, 3), a[-b:, :].reshape(-1, 3),
        a[:, :b].reshape(-1, 3), a[:, -b:].reshape(-1, 3),
    ])
    worst = strips.min(axis=0)                 # 最暗的那个通道值
    near_white = float((strips >= WHITE_MIN).all(axis=1).mean())
    return {
        "name": "white_bg_purity",
        "ok": bool(near_white >= 0.995),
        "detail": {"near_white_ratio": round(near_white, 4),
                   "min_channel_on_border": [int(v) for v in worst]},
    }


def check_product_fill(path: Path, target_pct: float, tol: float = 0.03) -> dict:
    """按非白像素的外接框计算产品占比。"""
    a = _arr(path)
    h, w = a.shape[:2]
    dist = np.abs(255.0 - a).max(axis=2)
    ys, xs = np.where(dist > NON_WHITE_DELTA)
    if xs.size == 0:
        return {"name": "product_fill", "ok": False, "detail": {"error": "未检测到前景像素"}}
    bw, bh = int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
    ratio = max(bw, bh) / max(w, h)
    return {
        "name": "product_fill",
        "ok": bool(ratio + tol >= target_pct / 100.0),
        "detail": {"fill_pct": round(ratio * 100, 2), "target_pct": target_pct,
                   "bbox": [int(xs.min()), int(ys.min()), bw, bh]},
    }


def check_edge_clean(path: Path, band: float = 0.05) -> dict:
    """边缘带是否干净 —— 启发式捕获贴边的水印 / 边框 / 角标。"""
    a = _arr(path)
    h, w = a.shape[:2]
    b = max(2, int(min(h, w) * band))
    strips = [a[:b, :], a[-b:, :], a[:, :b], a[:, -b:]]
    dirty = 0
    total = 0
    for s in strips:
        flat = s.reshape(-1, 3)
        total += flat.shape[0]
        dirty += int((np.abs(255.0 - flat).max(axis=1) > NON_WHITE_DELTA).sum())
    ratio = dirty / max(1, total)
    return {"name": "edge_clean", "ok": bool(ratio < 0.02),
            "detail": {"dirty_ratio_on_border": round(ratio, 5)}}


def check_has_text_block(path: Path, band: float = 0.05) -> dict:
    """位置 1 专用：主图不允许任何文字 / 水印 / 角标 / 边框。

    为什么只看边缘带而不是全图：产品本身可能是深色的（深色瓶身、黑色外壳），
    用全局深色像素比例判断会把产品误判成文字。

    band 必须小于产品四周的留白宽度，否则会把产品本体当成"边缘脏东西"。
    产品占比 85% ⇒ 单边留白 = (1-0.85)/2 = 7.5%，故 band 上限约 7%。
    validate() 会按坑位的 product_fill_pct 反推安全 band 传进来。

    注意：这是**启发式**，不是 OCR。逐字校对（确认没有错字）为后续项。
    """
    a = _arr(path)
    h, w = a.shape[:2]
    b = max(2, int(min(h, w) * band))
    strips = [a[:b, :], a[-b:, :], a[:, :b], a[:, -b:]]
    dark = 0
    total = 0
    for s in strips:
        flat = s.reshape(-1, 3)
        total += flat.shape[0]
        dark += int((flat.max(axis=1) < 90).sum())
    ratio = dark / max(1, total)
    return {"name": "has_text_block", "ok": bool(ratio < 0.002),
            "detail": {"dark_ratio_on_border": round(ratio, 6), "band": band,
                       "note": "启发式（边缘带深色像素），非 OCR"}}


def check_text_present(path: Path, region: float = 0.40) -> dict:
    """位置 2/3/7 专用：确认叠字确实渲染上去了（底部区域存在深色像素）。"""
    a = _arr(path)
    h = a.shape[0]
    band = a[int(h * (1 - region)):, :]
    dark = float((band.max(axis=2) < DARK_MAX).mean())
    return {"name": "text_present", "ok": bool(dark > 0.0005),
            "detail": {"dark_ratio_bottom": round(dark, 5)}}


def check_aspect_ratio(path: Path, expect: str = "1:1") -> dict:
    w, h = Image.open(path).size
    ok = abs(w - h) <= 2 if expect == "1:1" else True
    return {"name": "aspect_ratio", "ok": bool(ok), "detail": {"size": [w, h], "expect": expect}}


def check_long_side(path: Path, min_px: int, target_px: int) -> dict:
    w, h = Image.open(path).size
    ls = max(w, h)
    return {"name": "long_side_px", "ok": bool(ls >= min_px),
            "detail": {"long_side": ls, "min": min_px, "target": target_px,
                       "zoom_enabled": ls >= 1600}}


def check_file_size(path: Path, max_mb: float) -> dict:
    kb = path.stat().st_size / 1024
    return {"name": "file_size", "ok": bool(kb <= max_mb * 1024),
            "detail": {"kb": round(kb, 1), "max_mb": max_mb}}


def check_filename(path: Path, upc: str) -> dict:
    return {"name": "filename_has_upc", "ok": bool(upc and upc in path.name),
            "detail": {"filename": path.name, "upc": upc}}


def effective_rules(slot: dict) -> list[str]:
    """这一格**实际会跑**的规则集（显式声明 + 强度自动附加项）。

    ★ 一处定义，两个消费方：
        validate()                  —— 真跑校验
        tools/gen_slot_cards.py     —— 生成坑位卡的「出错走哪一级」表

      分开写两份，就会出现"卡上说会验 3 项、实际验了 5 项"这种
      只有读代码才发现的分歧。而坑位卡的整个价值就是"读它就不用读代码"。
    """
    level = slot.get("validate_level", "loose")
    rules = list(slot.get("validate_rules") or [])
    if "file_size" not in rules and level in ("strict", "medium"):
        rules.append("file_size")
    if "edge_clean" not in rules and level == "strict":
        rules.append("edge_clean")
    return rules


def validate(path: str | Path, slot: dict, export: dict, upc: str) -> dict:
    """按坑位声明的 validate_rules 与 validate_level 执行校验。"""
    path = Path(path)
    level = slot.get("validate_level", "loose")
    declared = set(slot.get("validate_rules") or [])
    rules = set(effective_rules(slot))

    # 未实现的规则名必须**响亮地失败**，不能静默跳过。
    # 静默跳过 = 报告里看不出"这项没验"，等于给了一张假的安全证明。
    unknown = sorted(rules - set(KNOWN_RULES))
    if unknown:
        raise ValueError(
            f"坑位 {slot.get('id')} 声明了未实现的校验规则 {unknown}。"
            f"已实现：{'、'.join(sorted(KNOWN_RULES))}。"
            f"（要么实现它，要么把它从坑位表里删掉 —— 不要留一个看起来在验的规则。）")

    checks: list[dict] = []
    if "aspect_ratio" in rules:
        checks.append(check_aspect_ratio(path, export.get("aspect_ratio", "1:1")))
    if "long_side_px" in rules:
        checks.append(check_long_side(path, int(export["min_long_side_px"]),
                                      int(export["long_side_px"])))
    if "file_size" in rules or level in ("strict", "medium"):
        checks.append(check_file_size(path, float(export["max_file_mb"])))
    if "filename_has_upc" in rules:
        checks.append(check_filename(path, upc))
    if "white_bg_purity" in rules:
        checks.append(check_white_bg(path))
    if "product_fill" in rules:
        checks.append(check_product_fill(path, float(slot.get("product_fill_pct", 85))))
    # 边缘带宽度必须小于产品四周留白，否则会把产品本体当成"边缘脏东西"。
    # 产品占比 fill ⇒ 单边留白 = (1-fill)/2，取其中 80% 作为安全带。
    fill = float(slot.get("product_fill_pct", 85))
    safe_band = max(0.02, (1 - fill / 100.0) / 2 * 0.8)

    if "edge_clean" in rules or level == "strict":
        checks.append(check_edge_clean(path, band=safe_band))
    if "has_text_block" in rules:
        checks.append(check_has_text_block(path, band=safe_band))
    if "text_present" in rules:
        checks.append(check_text_present(path))

    failed = [c["name"] for c in checks if not c["ok"]]
    return {
        "path": str(path),
        "slot_id": slot["id"],
        "level": level,
        "passed": not failed,
        "failed": failed,
        "checks": checks,
    }
