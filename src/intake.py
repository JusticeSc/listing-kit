r"""E0 体检：投递的素材合不合格。**在任何抠图、任何模型调用之前。**

为什么必须有这一步
------------------
    工具修不了不合格的输入。一张自带水印、主体被裁切、只有 600px 的原片，
    后面每一步都会忠实地把它做成一张**看起来合规、实则不可上架**的成品图。
    这类错误若在出口才暴露，代价是整批重做（含模型调用费）。

    所以：**在入口拦。**

能自动判什么、不能自动判什么 —— 这条是本节的设计核心
----------------------------------------------------
                 有规则                         无规则
    有参照物     ✅ 自动：尺寸 / 可读性 / 通道      ⚠️ 半自动：边缘像素异常
    无参照物     ✅ 自动：是否已带 alpha 通道      ❌ **只能人工**：有无水印 /
                                                    有无道具 / 主体是否完整 / 角度

    "什么是道具"没有闭集，写不出规则。硬写一个启发式检测器，产出的是
    **不可靠的告警** —— 它比不检更坏，因为它让系统假装有保护。
    （本项目已踩过这个坑：v1 的 `validate_rules` 里写着 `no_watermark`，
      而 `validators.py` 从来没有实现过它 —— 那是假校验。）

    于是 E0 的形态是：**自动项机器判，人工项要求签字**。
    工具不假装它验过那四条，但它要求有人对那四条负责 —— 而这份签字
    会落进 `run.jsonl`，于是"谁在什么时候确认过什么"是可回溯的。

拒收 vs 跳过（必须区分，这是两种不同的事）
----------------------------------------
    拒收（整批不做）  素材本身**不合格** —— 工具修不了，硬做只会产出废图
    跳过（单坑位不做）素材**没提供**     —— 那不是错误，是"这次这张不做"
                                             （见 src/assets.py 的 resolve）

    两者混在一起，人就会把"我没拍特写"和"我拍糊了"当成同一件事，
    而它们该有完全不同的反应。

inspect() 读出的键分两类（写在这里，免得后人把"证据"当死字段删掉）
------------------------------------------------------------------
    【判据】参与分支，改它行为就变：
            readable / long_side / min_side / aspect / has_alpha /
            corner_white / border_variation
    【证据】只落进 plan.json / run.jsonl，供事后诊断与审计：
            path / width / height / mode / error

    两类的差别不是"有没有用"，是**谁在读**：判据被代码读，证据被人读。
    本项目把"声明了没人读的字段"当头号敌人，所以在文档里把这条界线划明 ——
    否则下一个人会照着那条纪律把证据字段也删掉，而"这张原片当时到底什么样"
    就再也追不回来了。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

import assets as assets_mod
from kit_config import resolve_font

# ---------------------------------------------------------------- 人工确认项
# 机器判不了、且**必须有人签字**的四条。
# 这份清单就是上面那张表里的红格 —— E0 不假装验过它，但要求它存在。
ATTEST_ITEMS: dict[str, str] = {
    "no_watermark": "原片不含水印 / 平台标识 / 用户 ID",
    "no_props": "原片不含道具（手、硬币、参照物、其它商品）",
    "single_subject": "画面只有这一件主体，且完整、未被裁切",
    "angle_ok": "角度与清晰度满足该坑位用途",
}

# 用了文字就必须有人确认字体授权 —— 它同样是"无规则可判"的合规项。
# ★ 注意：这里**不做字体替换**，只要求这一条被签字。授权不是程序能判的事。
FONT_ATTEST_ITEM = "font_license"
FONT_ATTEST_DESC = "所用字体已获商用授权（系统自带字体通常不含商品图商用权）"

# ★ 位置 7（对比图）会把**竞品原图**并排放进成品图，于是那句"不得出现竞品品牌名"
#   就成了竞品原图的责任 —— 而"这张图里有没有别人的 logo"是机器判不了的，
#   与"原片有没有水印"同一类。所以它同样进签字清单，且**只在位置 7 真要出图时**
#   才要求（条件项，与字体授权同一个模式：用到才要求，用不到不添麻烦）。
COMPETITOR_ATTEST_ITEM = "competitor_clean"
COMPETITOR_ATTEST_DESC = ("竞品原图不含竞品品牌名 / logo / 水印"
                          "（位置 7 会把它并排放进成品图）")

# 需要体检的素材 = 图片类素材。**这份清单只有一处定义**（src/assets.py）——
# 在这里再抄一份就是漂移的起点，本项目已因重复维护踩过好几次。
IMAGE_KINDS = assets_mod.IMAGE_KINDS


@dataclass
class E0Report:
    """E0 的结论。dry-run 打印的就是它。"""
    images: dict[str, dict] = field(default_factory=dict)   # kind -> 可判定事实
    rejects: list[str] = field(default_factory=list)        # 自动判出的不合格
    notices: list[str] = field(default_factory=list)        # 提醒，不拦
    attest: dict = field(default_factory=dict)              # 人签的字
    attest_missing: list[str] = field(default_factory=list)  # 该签未签
    font: dict | None = None                                # {path, source}


# ---------------------------------------------------------------- 像素事实

def has_alpha(im) -> bool:
    """这张图是否**已经带 alpha 通道**（= 已经是一张抠好的图，不是原片）。

    ★ 一处定义，两个消费方：
        inspect()     —— 把结论写进 E0 体检报告（"已是抠好的图"提醒）
        subject.py    —— 据此**跳过抠图**，直接采用
      后者正是 M2 那条提醒里写的"[M3 落地]"。在这里再抄一份判断逻辑，
      就会出现"E0 说有 alpha、subject 说没有"这种自相矛盾的结果。
    """
    return (im.mode in ("RGBA", "LA")
            or (im.mode == "P" and "transparency" in im.info))


def _corner_white_ratio(rgb, w: int, h: int) -> float:
    """四角是否近白 —— 判"这张本来就铺了白底"（供应商图常见）。"""
    if w < 3 or h < 3:
        return 0.0
    pts = [(1, 1), (w - 2, 1), (1, h - 2), (w - 2, h - 2)]
    white = sum(1 for p in pts if min(rgb.getpixel(p)) >= 245)
    return round(white / len(pts), 3)


def _border_variation(rgb, w: int, h: int, n: int = 24) -> float:
    """边缘环上像素与"该环自身中位色"不一致的比例。

    注意它**不是**"主体触边检测" —— 场景原片的边缘本来就处处不同。
    它只回答"边缘是否均匀"。所以它只进 notices，不参与拒收：
    这类判断依赖"背景色可知"，而背景色并非总能判定（硬判会误杀场景图）。
    """
    if w < 3 or h < 3:
        return 0.0
    pts: list[tuple[int, int]] = []
    for i in range(n):
        x = int((w - 1) * i / (n - 1))
        pts += [(x, 0), (x, h - 1)]
    for i in range(n):
        y = int((h - 1) * i / (n - 1))
        pts += [(0, y), (w - 1, y)]
    px = [rgb.getpixel(p) for p in pts]
    ref = sorted(px, key=lambda c: sum(c))[len(px) // 2]
    far = sum(1 for c in px if max(abs(a - b) for a, b in zip(c, ref)) > 40)
    return round(far / len(px), 3)


def inspect(path: str | Path) -> dict:
    """读一张原片**可判定的**事实。坏文件在这里就暴露，不往下走。"""
    p = Path(path)
    facts: dict = {"path": str(p), "readable": False}
    try:
        with Image.open(p) as im:
            im.load()                      # 真的解码一次：截断文件在此现形
            w, h = im.size
            mode = im.mode
            facts.update(
                width=w, height=h, mode=mode,
                long_side=max(w, h), min_side=min(w, h),
                aspect=round(w / h, 3) if h else 0.0,
                has_alpha=has_alpha(im),
                corner_white=_corner_white_ratio(im.convert("RGB"), w, h),
                border_variation=_border_variation(im.convert("RGB"), w, h),
                readable=True,
            )
    except Exception as exc:               # 不可读 = 最硬的拒收理由
        facts["error"] = f"{type(exc).__name__}: {exc}"[:200]
    return facts


# ---------------------------------------------------------------- E0 主流程

def run_e0(*, supplied: dict, product: dict, export: dict,
           brand: dict | None = None, needs_font: bool = False,
           needs_competitor: bool = False) -> E0Report:
    """对**本次投递提供了的**图片逐张体检，再核对人工签字。

    `supplied` 里没有的素材不体检 —— 它属于"跳过"，不属"体检"。这是刻意的：
    体检只对**将要进入链路的东西**负责。

    needs_font / needs_competitor 是**条件签字项**：只有这一轮真的会用到
    文字 / 竞品图时，才要求对应的那一条签字。用不到就不添麻烦 ——
    它们的调用方（orchestrator.plan_run）从**齐套判定后的**坑位算出来，
    所以"表里写着位置 7、但这次没给竞品图"不会要求签字。
    """
    rep = E0Report()
    floor_px = int(export.get("min_long_side_px") or 1000)     # 平台下限
    canvas_px = int(export.get("long_side_px") or 1600)        # 本次出图边长

    for kind in IMAGE_KINDS:
        path = supplied.get(kind)
        if not path:
            continue
        f = inspect(path)
        rep.images[kind] = f

        if not f["readable"]:
            rep.rejects.append(
                f"{kind}（{f['path']}）无法读取：{f.get('error')}")
            continue

        # ---- 自动拒收：低于平台下限，放大即糊，无补救
        if f["long_side"] < floor_px:
            rep.rejects.append(
                f"{kind}（{f['path']}）最长边 {f['long_side']}px "
                f"< 平台下限 {floor_px}px —— 放大出图必然糊，工具修不了")

        # ---- 提醒（不拦）：这些是"该怎么办"的判断，机器不该替人决定
        # 画布是 1:1，所以**起决定作用的是短边**，不是最长边 ——
        # 2400×1200 的原片放进 1600×1600 画布，实际是按 1200 缩放的。
        if f["min_side"] < canvas_px:
            rep.notices.append(
                f"{kind} 短边 {f['min_side']}px < 出图边长 {canvas_px}px "
                f"→ 会被放大，细节会软")
        if abs(f["aspect"] - 1.0) > 0.05:
            rep.notices.append(
                f"{kind} 长宽比 {f['aspect']}（非 1:1）→ 放进 1:1 画布会裁切或补边")
        if f["has_alpha"]:
            rep.notices.append(
                f"{kind} 已带 alpha 通道 —— 它已经是一张抠好的图，"
                f"不是原片（E1 可考虑直接复用，M3 落地）")
        if f["corner_white"] >= 0.75:
            rep.notices.append(
                f"{kind} 四角近白（{f['corner_white']}）→ 已是白底图，抠图会更容易")
        elif f["border_variation"] >= 0.5:
            rep.notices.append(
                f"{kind} 边缘与中位色差异较大（{f['border_variation']}）→ "
                f"请确认主体没有被裁切")

    # ---- 字体：只校验"能不能解析"，不做替换（授权由人工签字负责）
    if needs_font:
        try:
            fpath, source = resolve_font(brand or {})
            rep.font = {"path": fpath, "source": source}
        except FileNotFoundError as exc:
            rep.rejects.append(f"字体资产缺失（text != none 的坑位需要它）：{exc}")

    # ---- 人工签字：只要求**本次真的会用到**的那几条
    #   提供了图片素材  → 图片类四条（水印 / 道具 / 主体完整 / 角度）全部要求
    #   要出文字        → 追加字体授权
    #   要出位置 7      → 追加"竞品图干净"
    # 为什么不一律要求全部：签字的目的是"有人对它负责"，
    # 要求一堆这次根本用不到的条目，只会让人不看内容一律勾选 —— 那比不签更坏。
    attest = product.get("attest") or {}
    rep.attest = attest
    confirmed = set(attest.get("confirmed") or [])
    required_keys = list(ATTEST_ITEMS) if rep.images else []
    if needs_font:
        required_keys.append(FONT_ATTEST_ITEM)
    if needs_competitor:
        required_keys.append(COMPETITOR_ATTEST_ITEM)
    rep.attest_missing = [k for k in required_keys if k not in confirmed]
    return rep


def attest_lines(rep: E0Report, *, needs_font: bool,
                 needs_competitor: bool = False) -> list[str]:
    """给 CLI 用：把签字状态渲染成行（勾/叉 + 说明）。"""
    req = dict(ATTEST_ITEMS) if rep.images else {}
    if needs_font:
        req[FONT_ATTEST_ITEM] = FONT_ATTEST_DESC
    if needs_competitor:
        req[COMPETITOR_ATTEST_ITEM] = COMPETITOR_ATTEST_DESC
    if not req:
        return []
    confirmed = set(rep.attest.get("confirmed") or [])
    who = rep.attest.get("by") or "（未署名）"
    when = rep.attest.get("date") or ""
    out = [f"  人工确认（工具判不了这些，须有人签字）· 签字人 {who} {when}".rstrip()]
    for k, desc in req.items():
        mark = "✓" if k in confirmed else "✗"
        out.append(f"    {mark} {k:<16}{desc}")
    return out
