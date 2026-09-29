# -*- coding: utf-8 -*-
"""PC-09 的适用性探针与量测缓存 —— 验证器能力的一部分，住验证层。

为什么从这里开始就住在 demo/verify/：这几段回答的是「这把尺子在这张图上成不成立」，
而不是「流水线下一步做什么」。它属于验证器的能力声明（计划 §4.6：每个验证器声明适用前提、
能判哪些事实类型、结论域、证据形态），所以放进验证层，处理链只按名字调用。

一条规矩（计划 §4.5 第 7 条，不许自证）：探针量的是**传进来的那张图**。为满足前提而人为
制造出来的输入（抠图后贴回的底衬）不能拿来当适用性证据 —— 那是量我们自己铺的灰。

内容：
    backdrop_probe      controlled_backdrop 探针：纯背景列里被判成主体的像素占比
    APPLICABILITY_PROBES 探针登记表（新增探针 = 在这里登记 + 在数据里声明）
    applicability_of    先问适用性再给结论；没有声明前提或没有阈值的验证器一律不得裁决
    measure_candidate   量测 + 判定的缓存（同一文件同一哈希只算一次）
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT / "demo" / "fixture"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import factcard               # noqa: E402
import measure_cylinder as MC  # noqa: E402


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def backdrop_probe(image_path, *, band=0.18) -> dict:
    """适用性探针：底衬是否「低饱和中性」到可以让阈值掩膜成立。

    判据不是新发明的：它直接量「纯背景列里被判成主体的像素占比」。棚拍无缝底衬上
    这个数是 0，场景图上墙面阴影与地面亮斑会被算进主体。探针本身不判商品。
    """
    import numpy as np
    from PIL import Image
    arr = np.asarray(Image.open(image_path).convert("RGB")).astype("float64")
    w = arr.shape[1]
    cols = max(1, int(w * float(band)))
    mask = MC.build_mask(arr)
    return {
        "band": float(band),
        "band_columns": cols,
        "subject_share_in_band": round(float(mask[:, :cols].mean()), 4),
        "mask_share": round(float(mask.mean()), 4),
        "mask_definition": "saturation>0.12 或 lum<0.45*bg（与 cylinder-v1 同一份实现）",
    }


APPLICABILITY_PROBES = {"controlled_backdrop": backdrop_probe}
_APPLICABILITY_CACHE: dict = {}


def applicability_of(router: dict, candidate) -> dict:
    """先问适用性。没有声明适用前提的验证器不许直接给结论。"""
    cond = router.get("applies_when")
    if not cond:
        return {"applicable": False,
                "why": "该验证器没有声明适用前提，按未校准处理，不得直接裁决"}
    probe_id = cond.get("probe")
    fn = APPLICABILITY_PROBES.get(probe_id)
    if fn is None:
        return {"applicable": False, "why": f"未登记的适用性探针 {probe_id!r}"}
    params = dict(cond.get("params") or {})
    key = (probe_id, tuple(sorted(params.items())),
           candidate.get("sha256") or candidate["file"])
    if key not in _APPLICABILITY_CACHE:
        try:
            _APPLICABILITY_CACHE[key] = fn(candidate["file"], **params)
        except Exception as exc:
            return {"applicable": False,
                    "why": f"适用性探针执行失败：{type(exc).__name__}: {exc}"}
    measured = _APPLICABILITY_CACHE[key]
    limit = cond.get("max_share")
    if limit is None:
        return {"applicable": False, "probe": probe_id, "measured": measured,
                "why": "适用性探针没有给阈值，无法判定"}
    ok = measured["subject_share_in_band"] <= float(limit)
    why = ("前提成立：纯背景列中的主体像素占比 "
           f"{measured['subject_share_in_band']} 不大于 {limit}" if ok else
           "前提不成立：纯背景列中有 "
           f"{measured['subject_share_in_band']} 的像素被判成主体（上限 {limit}），"
           "说明背景或阴影已进入掩膜，该量测器在这类输出上不适用")
    return {"applicable": ok, "probe": probe_id, "measured": measured,
            "max_share": float(limit), "why": why}


_MEASURE_CACHE: dict = {}


def measure_candidate(path, card) -> dict:
    key = (str(path), sha256_file(path))
    if key not in _MEASURE_CACHE:
        clf = factcard.PaletteClassifier(card["palette"])
        measured = MC.measure(Path(path), card=card, clf=clf)
        _MEASURE_CACHE[key] = {"measured": measured,
                               "report": factcard.evaluate(measured["metrics"], card)}
    return _MEASURE_CACHE[key]
