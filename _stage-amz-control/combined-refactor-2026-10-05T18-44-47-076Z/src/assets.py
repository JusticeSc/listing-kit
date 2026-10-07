"""齐套判定：算出"这一次实际能出哪几张"。

核心命题
--------
    **张数是算出来的，不是配置项。**
    实际出几张 = 坑位表 ∩ 素材齐套

人工流程里这件事发生在最后（"怎么少了一张"）；放在这里，它发生在投递那一刻。
不调模型省下的钱，有一部分转手花在了"把素材拍齐"上 —— 齐套判定就是把这笔账
提前摆到台面上，而不是等出了六张才发现第七张做不了。

素材从哪里来
------------
    图片类 front / closeup / contents / competitor → product["assets"]
    文本类 bullets / specs                        → product 顶层字段
统一成同一套 kind，于是坑位表里的 needs 与素材来源一一对应，不需要第二张映射表。

缺料时的两种反应（**必须区分**）
------------------------------
    缺 front（或任何"没有它就没有主体"的素材）→ **全局拒绝**，整批不做
    缺其它                                    → **跳过该坑位**，不报错、不降级

为什么是跳过，而不是"凑一张"
    凑出来的图没有信息增量，却占掉一个坑位，还让买家以为看到了细节。
    **假图比缺图更贵 —— 它花的是信任。**

另外两件容易和"齐套"混为一谈的事，**都不在本模块**（分清归属，否则会长成第二个真相源）：

    E0 素材体检（尺寸/可读性/签字）→ src/intake.py
        区别：齐套回答"**这次做哪几张**"，体检回答"**这张能不能用**"。
             缺特写 → 跳过位置 5（本模块）；
             特写只有 600px → 整批拒收（intake）。
    run.jsonl 的 slot_skipped 字段   → src/orchestrator.py（M1 已落地）
"""
from __future__ import annotations

from pathlib import Path

IMAGE_KINDS = ("front", "closeup", "contents", "competitor")
TEXT_KINDS = ("bullets", "specs")
ALL_KINDS = IMAGE_KINDS + TEXT_KINDS


class Rejected(Exception):
    """整批拒绝（缺的是"没有它就没有任何图"的素材）。"""


def collect(product: dict, base_dir: Path | str = ".") -> tuple[dict, dict]:
    """盘点本次投递提供了哪些素材。

    返回 (supplied, broken)：
        supplied  {kind: 说明}      —— 判定只认这个
        broken    {kind: 原值}      —— 填了路径但文件不在（**不算提供**，
                                       但必须报出来，否则人会以为给了）
    """
    base_dir = Path(base_dir)
    supplied: dict[str, str] = {}
    broken: dict[str, str] = {}

    declared = product.get("assets") or {}
    for kind in IMAGE_KINDS:
        raw = declared.get(kind)
        if not raw:
            continue
        p = Path(raw)
        p = p if p.is_absolute() else (base_dir / p)
        if p.exists():
            supplied[kind] = str(p)
        else:
            broken[kind] = str(raw)

    if product.get("bullets"):
        supplied["bullets"] = f"{len(product['bullets'])} 条"
    if product.get("specs"):
        supplied["specs"] = f"{len(product['specs'])} 项"
    return supplied, broken


def big_picture_facts(product: dict, base_dir: Path | str = ".") -> dict:
    """兼容旧输入的兜底：只有平铺 images[]、没有 assets{} 时，第一张按 front 算。

    这是**过渡期兼容**，不是长期形态：平铺列表无法表达"哪张是特写"，
    用它当 front 会让细节图拿到错误的素材。所以只认第一张，且明确标注来源。
    """
    supplied, broken = collect(product, base_dir)
    if "front" not in supplied:
        imgs = product.get("images") or []
        if not imgs:
            return supplied, broken
        p = Path(imgs[0])
        p = p if p.is_absolute() else (Path(base_dir) / p)
        if p.exists():
            supplied["front"] = f"{p}（来自 images[0]，非 assets.front）"
    return supplied, broken


def resolve(slots: list[dict], supplied: dict) -> tuple[list[dict], list[dict]]:
    """按 needs 判定每个坑位做不做。

    返回 (doable, skipped)；skipped 项带 missing 列表，让"为什么只有 4 张"有据可查。
    注意：**没有一个坑位会被"降级"** —— 要么按声明做，要么跳过。

    skipped 里带 `renderer`（消费方：orchestrator.run_state → 审核台的"跳过"卡片）——
    跳过的那一格也得说得出"它本来会由谁画"。少了它，审核台上被跳过的位置
    就只剩一句"缺料"，看不出成本差异（哪些本来零模型、哪些本来要花钱）。
    """
    doable: list[dict] = []
    skipped: list[dict] = []
    for s in slots:
        missing = [k for k in (s.get("needs") or []) if k not in supplied]
        if missing:
            skipped.append({
                "slot_id": s.get("id"),
                "role": s.get("role"),
                "purpose": s.get("purpose"),
                "renderer": s.get("renderer"),
                "missing": missing,
                # `cause` 是**机器可读**的成因，`reason` 是给人看的话。
                # 为什么要分开：`p.skipped` 有两个生产者 —— 这里是「入口就缺料」，
                # orchestrator 里还有「运行时抠图连续失败后跳过」。原来两者只有
                # reason 文案，于是 run.py 的收尾汇总只能笼统写「（缺料）」，
                # 运营看到会去翻素材照片，而真正该做的是关掉审核台重跑。
                # 文案可以随便改，成因不能靠解析文案得知 —— 那是两份真相。
                "cause": "intake",
                "reason": "缺料跳过（不降级、不用别的图凑）",
            })
        else:
            doable.append(s)
    return doable, skipped


def require_subject(supplied: dict, mandatory_slots: list[dict]) -> None:
    """强制坑位缺料 = 全局拒绝。

    位置 1 主图的 needs 就是 [front]。它做不了，说明这次投递没有主体原片，
    其余坑位即使"素材齐"也失去了共享的主体资产 —— 整批不做比做半批好。
    """
    need: set[str] = set()
    for s in mandatory_slots:
        need |= set(s.get("needs") or [])
    missing = sorted(need - set(supplied))
    if missing:
        raise Rejected(
            f"缺平台强制坑位的必备素材：{'、'.join(missing)} —— "
            f"没有主体原片就没有任何一张图可做，整批拒绝（不是跳过）")
