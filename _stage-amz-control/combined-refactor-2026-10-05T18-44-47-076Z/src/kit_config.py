"""配置加载：品牌规范 + 字体解析。

注意分工（v2 之后）
------------------
    config/slots.yaml 的读取与校验 → **只走 src/schema.py**
        （它需要行号定位，还要跑白名单/规则名/平台档位校验，
          所以它直接读文件，不经过本模块 —— 一条路径，一个解释者）
    本模块只负责 brand.json 与字体解析这两件与坑位表无关的事。

v1 曾有 `load_slots` / `get_slot` / `implemented_slots` / `export_spec` 四个助手，
它们全都失去消费方（`implemented_slots` 依赖已删除的 `status` 字段）→ 已删。
留着一个没人调的函数，就是下一个漂移点。
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- 字体
# 【已知风险 · 已接受】默认字体是系统自带的 **微软雅黑（msyhbd.ttc）**。
#   微软雅黑的商用权利属方正，**用于商品图属未授权商用** ——
#   它与"原图自带水印"是同一类问题：**工具修不了**。
#
#   ★ 决定：**本阶段不替换字体。** 授权不是程序能判的事，所以它被挂进
#     E0 的人工签字清单（intake.FONT_ATTEST_ITEM = "font_license"）：
#     只要这一轮出文字，就必须有人签字确认；签字落进 plan.json / run.jsonl，
#     事后可回溯。**工具不假装验过它，但要求有人对它负责。**
#
#   正式对外发布前，把 config/brand.json 的 fonts.cn_bold 指向已授权字体
#   （思源黑体 / Noto Sans SC 等）即可 —— 换字体只改这一个配置位、不改代码，
#   所以推迟它**不产生技术债**。
#
#   这里刻意不写 TODO：一个明知不会被执行的 TODO，就是一条假声明。
_SYS_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyhbd.ttc",   # 微软雅黑 Bold（商用授权未确认）
    "C:/Windows/Fonts/msyh.ttc",     # 微软雅黑（商用授权未确认）
    "C:/Windows/Fonts/simhei.ttf",   # 黑体
    "C:/Windows/Fonts/msyhbd.ttf",
]


def load_brand(path: Path | str | None = None) -> dict:
    """读取品牌规范。

    消费方（**逐个字段都对得上**，写不出来的字段不该留在文件里）：
        planner.extract_facts      forbidden_words + forbidden_on_image（图上禁用词）
        textlayer.overlay_callouts  fonts / text_bar_color / text_bar_opacity
        intake.run_e0              fonts（字体资产存在性校验）
        orchestrator              透传给渲染器

    ★ 颜色（文字色 / 强调色 / 底色）**不在这里** —— 它们属于
      `config/catalog/<类目>.yaml` 的 `palette`。分开的依据是"随谁变"：
      色板随**类目**变（家居厨具中性灰、服装暖米色），
      字体与文字条随**品牌**不变。曾经两边各存一份同值颜色，是靠"恰好同色"
      掩盖着的双所有者，已收敛为一处。
    """
    p = Path(path) if path else ROOT / "config" / "brand.json"
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_font(brand: dict, kind: str = "cn_bold") -> tuple[str, str]:
    """解析中文字体。

    优先级：品牌配置指定 → 系统字体候选 → 报错。
    返回 (字体路径, 来源说明)。

    消费方：textlayer.overlay_callouts。
    """
    configured = (brand.get("fonts") or {}).get(kind) or ""
    if configured:
        p = Path(configured)
        if not p.is_absolute():
            p = ROOT / configured
        if p.exists():
            return str(p), "brand.json 指定"
        raise FileNotFoundError(f"brand.json 指定的字体不存在: {p}")

    for cand in _SYS_FONT_CANDIDATES:
        if Path(cand).exists():
            return cand, "系统字体自动探测（⚠️ 商用授权未确认）"
    raise FileNotFoundError(
        "未找到可用中文字体。请在 config/brand.json 的 fonts.cn_bold 中指定字体文件路径。"
    )
