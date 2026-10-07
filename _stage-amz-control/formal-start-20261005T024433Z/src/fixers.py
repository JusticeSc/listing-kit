r"""修复阶梯 L0：确定性修复 —— 把「机器一步能修的」从人手里拿回来。

为什么必须有它（这是本项目最大的一处越权）
------------------------------------------
参考的三个电商图技能库里，`check_listing.py` 检出 9 项之后带一个 `--fix`：
白底偏灰 → 刷成 RGB(255,255,255)；占比不足 → 按目标占比重构画布；
分辨率不够 → 补到 1600px。退出码 0/1，直接接 CI。

而本项目此前只做了「检出」这一半：`validators.validate()` 报 failed →
编排器跳过该格 → 交人签字。于是**机器一步能修的，被写成了人的责任** ——
而人看到的提示是「工具修不了」。

阶梯（从便宜到贵，**不许跳级**）
-------------------------------
    L0 确定性修   白底偏灰 / 占比不足 / 非 1:1 / 分辨率不足 / 体积超限   0 元 · 毫秒
    L1 重放某层   文字 / 位置                                          0 元 · 秒级
    L2 重生成     背景不像（把失败翻成英文句子回灌提示词）              计费 · 约 63s
    L3 签字       法律 / 品牌 / 责任                                   人

本模块**只实现 L0**。其余三级刻意不在这里 —— 一个「什么都想修」的修复器
最后一定会去修它修不了的东西，然后产出一个「看起来对了」的假象。

三条纪律
--------
    ① 从 L0 往上试，不许跳级。
    ② **修完必须复验**。成功的判据不是「我执行了修改」，是「那条校验现在过了」。
       修了但没修好 → 如实报 unfixed，不许因为「我做过动作了」就当作成功。
    ③ **修不了要明说**（这是本项目一贯的那条：判不了的别假装判了）。
       `has_text_block`（位置 1 出现文字）**绝不进 L0** —— 把文字擦掉是
       *掩盖违规内容*，不是修复；必须查明来源（是渲染器画的？还是原片自带、
       而 E0 的签字没签对？）。`edge_clean`（边缘脏）原因不明（水印？主体触边？）
       → 交人。**只把能证明可修的五类放进 L0。**

留痕
----
    每次修复返回 `before` / `after` 与动作名，调用方写进 `run.jsonl`，
    并附修复前后的 sha256。理由不是审计洁癖：
    **「人看到的图」和「系统交付的图」必须能对上账**。
    没有这一行，审核台就变成了一个会说谎的显示器 —— 图上明明是灰底，
    而日志说校验全过。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from PIL import Image

import validators

# ---------------------------------------------------------------- 阶梯定义
L0_DETERMINISTIC = "L0"   # 确定性修（本模块）
L1_REPLAY = "L1"          # 重放某一层（文字 / 位置）
L2_REGENERATE = "L2"      # 重新生成（计费）
L3_HUMAN = "L3"           # 签字

LADDER = (L0_DETERMINISTIC, L1_REPLAY, L2_REGENERATE, L3_HUMAN)

# 每条校验失败 → 该走哪一级 + 为什么。
#
# ★ 这张表是「修复阶梯」唯一的分流点。加一条校验规则时必须同时在这里归类，
#   否则「它落到哪一级」就变成一个没人说得清的问题 —— 而那正是阶梯失效的开始。
#   消费方：fixers.repair 的 remaining/escalate 输出、坑位卡的「出错走哪一级」一节。
CHECK_RUNG: dict[str, tuple[str, str]] = {
    "white_bg_purity": (L0_DETERMINISTIC,
                        "背景近白但不纯 → 只刷与边缘连通的背景区（不碰主体）"),
    "product_fill":    (L0_DETERMINISTIC,
                        "占比不足 → 裁掉多余留白并重排画布（放大倍数过大则退回 L1）"),
    "aspect_ratio":    (L0_DETERMINISTIC,
                        "非 1:1 → 居中补白到正方形（补白，不裁切：绝不切掉主体）"),
    "long_side_px":    (L0_DETERMINISTIC,
                        "分辨率不足 → LANCZOS 放大到目标边长"),
    "file_size":       (L0_DETERMINISTIC,
                        "体积超限 → 逐级降 JPEG 质量，降到下限仍超则如实报修不了"),
    "text_present":    (L1_REPLAY,
                        "文字没画上 → 重放文字层（不是修像素）"),
    "has_text_block":  (L3_HUMAN,
                        "位置 1 出现文字：擦掉是掩盖违规内容，必须查明来源"),
    "edge_clean":      (L3_HUMAN,
                        "边缘脏的原因不明（水印？主体被裁切？）→ 交人"),
    "filename_has_upc": (L3_HUMAN,
                         "改名属交付层，不动像素"),
}

# L0 的执行顺序：几何 → 颜色 → 构图 → 尺寸 → 字节。
# 顺序不是随意的：补白会改变占比，改质量会改变体积 —— 排在前面的会影响后面的结论，
# 所以 repair() 每轮都重新跑一次完整校验，而不是「按初始失败清单逐条修完就完」。
L0_ORDER = ("aspect_ratio", "white_bg_purity", "product_fill",
            "long_side_px", "file_size")

# 「均匀的亮背景」判据：边缘带暗端与波动。
# 为什么要自定义而不是用 validators.check_white_bg 的 near_white_ratio：
# 那个阈值是 250，灰白底（RGB 208）在它眼里是 0 —— 看不出「几乎白」这件事，
# 于是最需要修的那一类反而判不出来。
NEAR_WHITE_FLOOR = 200    # 边缘带最暗的 1% 不低于它 → 认定「这是白底，只是不够纯」
UNIFORM_STD_MAX = 30.0    # 边缘带标准差上限：均匀才叫背景，混了东西就不叫
MIN_BG_RATIO = 0.05       # 连通背景至少占这么多，否则洪填没找到背景

# 占比修复允许的最大放大倍数。
# 超过它就说明是**构图**问题，而不是「留白多了」—— 放大只会糊。
# 那一档该走 L1（重放位置层，免费且无损），不该硬拉。
MAX_UPSCALE = 1.35

FILL_TOL = 0.03           # 与 validators.check_product_fill 的 tol 保持一致

_QUALITY_LADDER = (92, 85, 78, 70, 60)


def rung_of(check_name: str) -> tuple[str, str]:
    """查一条校验失败该走哪一级。未归类的默认 **L3（交人）**。

    默认交人而不是默认自动修：自动做错的代价，比多问一个人高。
    """
    return CHECK_RUNG.get(
        check_name, (L3_HUMAN, "未归类 → 默认交人（宁可交人，不可自动做错）"))


# ---------------------------------------------------------------- 像素工具

def _sha256(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _load(path) -> Image.Image:
    return Image.open(path).convert("RGB")


def _band_stats(a: np.ndarray, band: float = 0.04) -> dict:
    """边缘带的亮度统计 —— 判「这是不是一个本该纯白的背景」。"""
    h, w = a.shape[:2]
    b = max(2, int(min(h, w) * band))
    strips = np.concatenate([a[:b, :].reshape(-1, 3), a[-b:, :].reshape(-1, 3),
                             a[:, :b].reshape(-1, 3), a[:, -b:].reshape(-1, 3)])
    return {"p01": float(np.percentile(strips, 1)),
            "mean": float(strips.mean()),
            "std": float(strips.std())}


def _save(img: Image.Image, path) -> None:
    img.save(path, "JPEG", quality=95, optimize=True)


# ---------------------------------------------------------------- L0 · 逐条修复
#
# 契约：每个 fix_* 收 (path, **参数)，返回
#     {"fixed": bool, "action": str, "reason": str, "before": {...}, "after": {...}}
# **只改文件，不改调用方状态** —— 复验由 repair() 统一做，避免每条自报「我好了」。


def fix_aspect_ratio(path, *, target: tuple[int, int] = (1, 1), **_) -> dict:
    """非 1:1 → 居中补白到目标比例。

    为什么是**补白**而不是裁切：裁切会切掉主体，而主体是这张图存在的全部理由。
    多一圈白边只是不好看，切掉主体是废图 —— 两者不可比。
    """
    img = _load(path)
    w, h = img.size
    if w == h:
        return {"fixed": False, "action": "pad_to_aspect",
                "reason": "已经是 1:1", "before": {"size": [w, h]}}
    side = max(w, h)
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2))
    _save(canvas, path)
    return {"fixed": True, "action": "pad_to_aspect",
            "reason": "居中补白到正方形（不裁切，避免切掉主体）",
            "before": {"size": [w, h]}, "after": {"size": [side, side]}}


def fix_background(path, *, band: float = 0.04, **_) -> dict:
    """把「近白但不纯」的背景刷成纯白。**只刷与边缘连通的背景区。**

    两条前提都满足才动手：
        ① 边缘带暗端 ≥ 200  —— 否则背景里混了深色东西（水印 / 主体触边），
                              这时候刷白是**掩盖**，不是修复。
        ② 边缘带 std ≤ 30   —— 否则背景不是一种颜色，刷白会造出一条假接缝。
    """
    import synth            # 延迟导入：只在真要刷背景时付这个成本

    img = _load(path)
    a = np.asarray(img).astype(np.float32)
    st = _band_stats(a, band)
    before = {"border_p01": round(st["p01"], 1),
              "border_mean": round(st["mean"], 1),
              "border_std": round(st["std"], 1)}
    if st["p01"] < NEAR_WHITE_FLOOR or st["std"] > UNIFORM_STD_MAX:
        return {"fixed": False, "action": "whiten_background",
                "reason": (f"边缘带暗端 {st['p01']:.0f} / 波动 {st['std']:.1f} —— "
                           f"不满足「均匀的亮背景」前提"
                           f"（≥{NEAR_WHITE_FLOOR} 且 ≤{UNIFORM_STD_MAX}）；"
                           f"刷白会掩盖别的问题，交人"),
                "before": before}

    mask = synth.background_mask(img)
    ratio = float(mask.mean())
    if ratio < MIN_BG_RATIO:
        return {"fixed": False, "action": "whiten_background",
                "reason": f"连通背景只占 {ratio:.1%} —— 洪填没找到背景"
                          f"（主体可能铺满画面），交人",
                "before": {**before, "bg_ratio": round(ratio, 4)}}

    out = np.asarray(img).copy()
    out[mask] = 255
    _save(Image.fromarray(out), path)
    return {"fixed": True, "action": "whiten_background",
            "reason": "只刷与边缘连通的背景区（主体的高光像素按连通性被排除在外）",
            "before": {**before, "bg_ratio": round(ratio, 4)},
            "after": {"border_p01": 255.0, "whitened_px": int(mask.sum())}}


def fix_product_fill(path, *, target_pct: float, canvas_px: int | None = None,
                     **_) -> dict:
    """占比不足 → 裁掉多余留白，按目标占比重排画布。

    放大倍数超过 MAX_UPSCALE 时**拒绝执行**：那说明这是构图问题而不是留白问题，
    硬拉只会糊；该走 L1（重放位置层，免费且无损）。拒绝也要给理由 ——
    「我没修」和「我不能修，原因如下」是两件不同的事。
    """
    img = _load(path)
    W, H = img.size
    a = np.asarray(img).astype(np.float32)
    dist = np.abs(255.0 - a).max(axis=2)
    ys, xs = np.where(dist > validators.NON_WHITE_DELTA)
    if xs.size == 0:
        return {"fixed": False, "action": "recrop_product_fill",
                "reason": "未检测到前景像素（整张都是白的？）—— 交人",
                "before": {"size": [W, H]}}

    bw = int(xs.max() - xs.min() + 1)
    bh = int(ys.max() - ys.min() + 1)
    cur = max(bw, bh) / max(W, H)
    t = float(target_pct) / 100.0
    if t <= 0:
        return {"fixed": False, "action": "recrop_product_fill",
                "reason": f"目标占比 {target_pct} 非法", "before": {"fill_pct": round(cur * 100, 2)}}

    side = int(round(max(bw, bh) / t))
    scale = side / float(max(W, H))
    before = {"size": [W, H], "fill_pct": round(cur * 100, 2),
              "bbox": [int(xs.min()), int(ys.min()), bw, bh]}
    if scale > MAX_UPSCALE:
        return {"fixed": False, "action": "recrop_product_fill",
                "reason": (f"要放大 {scale:.2f}× 才能把占比从 {cur * 100:.1f}% "
                           f"拉到 {target_pct}% —— 超过 {MAX_UPSCALE}× 上限。"
                           f"这是构图问题不是留白问题，硬拉只会糊："
                           f"该走 L1 重放位置层（免费、无损）"),
                "before": before}

    cx = (int(xs.min()) + int(xs.max())) // 2
    cy = (int(ys.min()) + int(ys.max())) // 2
    left, top = cx - side // 2, cy - side // 2
    canvas = Image.new("RGB", (side, side), (255, 255, 255))
    sx0, sy0 = max(0, left), max(0, top)
    sx1, sy1 = min(W, left + side), min(H, top + side)
    if sx1 > sx0 and sy1 > sy0:
        canvas.paste(img.crop((sx0, sy0, sx1, sy1)), (sx0 - left, sy0 - top))
    out_side = int(canvas_px or max(W, H))
    canvas = canvas.resize((out_side, out_side), Image.LANCZOS)
    _save(canvas, path)
    return {"fixed": True, "action": "recrop_product_fill",
            "reason": f"裁掉多余留白后按 {target_pct}% 重排画布",
            "before": before,
            "after": {"size": [out_side, out_side], "recomputed_side": side,
                      "resized": out_side != side}}


def fix_resolution(path, *, min_px: int, target_px: int, **_) -> dict:
    """长边不足 → LANCZOS 放大到 target 边长。"""
    img = _load(path)
    w, h = img.size
    ls = max(w, h)
    if ls >= int(min_px):
        return {"fixed": False, "action": "upscale_long_side",
                "reason": f"长边 {ls} 已达下限 {min_px}", "before": {"size": [w, h]}}
    scale = int(target_px) / float(ls)
    out = img.resize((int(round(w * scale)), int(round(h * scale))), Image.LANCZOS)
    _save(out, path)
    return {"fixed": True, "action": "upscale_long_side",
            "reason": f"LANCZOS 放大 {scale:.2f}× 到目标边长 {target_px}"
                      f"（放大是插值，细节不会凭空回来）",
            "before": {"size": [w, h]}, "after": {"size": list(out.size)}}


def fix_file_size(path, *, max_mb: float, **_) -> dict:
    """体积超限 → 逐级降 JPEG 质量；降到下限仍超 → **如实说修不了**。"""
    path = Path(path)
    limit_kb = float(max_mb) * 1024
    before_kb = path.stat().st_size / 1024
    if before_kb <= limit_kb:
        return {"fixed": False, "action": "recompress",
                "reason": f"体积 {before_kb:.0f}KB 未超限", "before": {"kb": round(before_kb, 1)}}

    img = _load(path)
    tried: list[dict] = []
    for q in _QUALITY_LADDER:
        img.save(path, "JPEG", quality=q, optimize=True)
        kb = path.stat().st_size / 1024
        tried.append({"quality": q, "kb": round(kb, 1)})
        if kb <= limit_kb:
            return {"fixed": True, "action": "recompress",
                    "reason": f"降到 JPEG 质量 {q}（不重采样，构图与分辨率不变）",
                    "before": {"kb": round(before_kb, 1)},
                    "after": {"kb": round(kb, 1), "quality": q}, "tried": tried}

    # 已经写到最低质量了，把它恢复成最高质量保存 —— 别留下一张被降质的图
    img.save(path, "JPEG", quality=_QUALITY_LADDER[0], optimize=True)
    return {"fixed": False, "action": "recompress",
            "reason": (f"降到 JPEG 质量 {_QUALITY_LADDER[-1]} 仍有 "
                       f"{tried[-1]['kb']:.0f}KB > 上限 {limit_kb:.0f}KB —— "
                       f"只能靠降分辨率或重渲染，那不属于 L0，交人"),
            "before": {"kb": round(before_kb, 1)}, "tried": tried}


_FIXERS = {
    "aspect_ratio": fix_aspect_ratio,
    "white_bg_purity": fix_background,
    "product_fill": fix_product_fill,
    "long_side_px": fix_resolution,
    "file_size": fix_file_size,
}


def _kwargs_for(check: str, slot: dict, export: dict) -> dict:
    if check == "product_fill":
        return {"target_pct": float(slot.get("product_fill_pct", 85)),
                "canvas_px": int(export.get("long_side_px") or 0) or None}
    if check == "long_side_px":
        return {"min_px": int(export.get("min_long_side_px") or 1000),
                "target_px": int(export.get("long_side_px") or 1600)}
    if check == "file_size":
        return {"max_mb": float(export.get("max_file_mb") or 10)}
    if check == "aspect_ratio":
        return {"target": (1, 1)}
    return {}


# ---------------------------------------------------------------- 阶梯驱动

def repair(path, slot: dict, export: dict, upc: str, *,
           max_rounds: int = 2) -> dict:
    """对一张成品图跑 L0 阶梯，返回完整修复报告。

    ★ 为什么是「轮」而不是「按初始失败清单逐条修完」：
      修一条会改变另一条的结论 —— 补白会降占比、降质量会改体积。
      所以每轮都重新跑一次**完整校验**，直到没有可修项或轮数用尽。

    ★ max_rounds 必须封顶：两条互相打架的校验（比如"占比要高"与"体积要小"）
      会让它永远修下去。封顶之后剩下的如实报出去，由人决定。
    """
    path = Path(path)
    sha_before = _sha256(path)
    verdict_before = validators.validate(path, slot, export, upc)
    attempts: list[dict] = []

    if verdict_before["passed"]:
        return {
            "path": str(path), "changed": False, "attempts": [],
            "verdict_before": verdict_before, "verdict_after": verdict_before,
            "remaining": [], "escalate": [],
            "sha256_before": sha_before, "sha256_after": sha_before,
        }

    for _round in range(max(1, max_rounds)):
        v = validators.validate(path, slot, export, upc)
        if v["passed"]:
            break
        failed = set(v["failed"])
        progressed = False
        for check in L0_ORDER:
            if check not in failed:
                continue
            fn = _FIXERS.get(check)
            if fn is None:
                continue                    # 不归 L0 的项：留给 remaining 报出去
            try:
                res = fn(path, **_kwargs_for(check, slot, export))
            except Exception as exc:        # 修复本身失败 = 没修，不是崩
                res = {"fixed": False, "action": f"fix_{check}",
                       "reason": f"修复执行失败：{type(exc).__name__}: {str(exc)[:160]}"}
            attempts.append({"check": check, "round": _round + 1,
                             "rung": L0_DETERMINISTIC, **res})
            if res.get("fixed"):
                progressed = True
        if not progressed:
            break

    verdict_after = validators.validate(path, slot, export, upc)
    remaining = [{"check": c, "rung": rung_of(c)[0], "why": rung_of(c)[1]}
                 for c in verdict_after["failed"]]
    escalate: list[str] = []
    for r in remaining:
        if r["rung"] not in escalate:
            escalate.append(r["rung"])
    escalate.sort(key=lambda x: LADDER.index(x) if x in LADDER else 99)

    sha_after = _sha256(path)
    return {
        "path": str(path),
        "changed": sha_after != sha_before,
        "attempts": attempts,
        "verdict_before": verdict_before,
        "verdict_after": verdict_after,
        "remaining": remaining,
        "escalate": escalate,
        "sha256_before": sha_before,
        "sha256_after": sha_after,
    }


def main(argv: list[str] | None = None) -> int:
    """独立入口：对一个已存在的成品图跑 L0 修复。

    它**不改任何 run 状态、不写日志** —— 只碰文件本身，并把报告打到 stdout。
    集成路径是 `run.py --autofix`（由编排器在渲染后调用并留痕）；
    这个入口是给人手工排查用的。
    """
    import argparse
    import json
    import sys

    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "src"))

    import schema                                   # noqa: PLC0415

    ap = argparse.ArgumentParser(description="L0 确定性修复（单张图）")
    ap.add_argument("image", help="要修的成品图路径")
    ap.add_argument("--slot", type=int, required=True, help="它属于哪个坑位")
    ap.add_argument("--slots", default=None, help="坑位表路径（默认 config/slots.yaml）")
    args = ap.parse_args(argv)

    cfg = schema.assert_valid(args.slots)
    slot = next((s for s in cfg["slots"] if s["id"] == args.slot), None)
    if slot is None:
        print(f"启动失败：坑位表里没有 id={args.slot}")
        return 4
    upc = Path(args.image).name.split("_")[0]
    rep = repair(args.image, slot, cfg["export"], upc)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
