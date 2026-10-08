"""坑位规范表校验器 —— 表是控制面，写错必须在**启动时**炸，不能运行时静默退化。

为什么必须有它
--------------
本项目已经因为"声明了但没人读"的字段返工三次（text_style / DASHSCOPE_IMAGE_MODEL /
text_layout），v1 的表里还有两个**假装被校验**的规则名（no_watermark / text_render_ok）——
它们在 validators.py 里根本不存在，于是"声明了校验"和"实际没校验"在外表上毫无区别。

所以本模块不只做类型检查，它把三条纪律变成会报错的规则：

  ① 未登记的 renderer 名       → 报错（否则编排器到运行时才发现）
  ② 未实现的 validate_rules 名 → 报错（否则就是"假校验"）
  ③ **表里出现没登记过的字段**  → 报错（写不出消费方的字段不许进表）

字段契约的落地方式就是 ③：ALLOWED_SLOT_KEYS 是一道白名单，
新增字段必须先在这里登记并写明消费方。它拦的不只是笔误，是"顺手加个配置项"。

用法：
    python -m src.schema                  # 校验 config/slots.yaml
    python -m src.schema --slots other.yaml
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))  # 允许 python -m src.schema
from console import enable_utf8  # noqa: E402  （控制台编码归一：见 src/console.py）
enable_utf8()

import yaml  # noqa: E402

import registry  # noqa: E402
import validators  # noqa: E402

SLOTS_REL = "config/slots.yaml"

# ------------------------------------------------------------
# 白名单：每个字段都必须能说出消费方
# ------------------------------------------------------------
ALLOWED_TOP = {
    "version": "schema 自身：拒绝 v1 表",
    "site": "schema：平台规则档位（SITE_PROFILES）",
    "category": "schema：catalog 一致性",
    "catalog": "orchestrator：加载类目模板",
    "export": "renderers / validators：导出规格",
    "slots": "orchestrator：遍历分派",
}
ALLOWED_EXPORT = {
    "aspect_ratio": "validators.check_aspect_ratio",
    "jpeg_quality": "synth / textlayer 落盘",
    "long_side_px": "synth.make_main_image 画布边长",
    "min_long_side_px": "validators.check_long_side",
    "max_file_mb": "validators.check_file_size",
    "filename_pattern": "synth.filename_for",
}
# 槽位字段：前 8 个必填，后 3 个按条件必填
SLOT_REQUIRED_KEYS = {
    "id": "orchestrator：分派与日志标识",
    "role": "synth.filename_for：拼成品文件名（让名字自带用途）",
    "purpose": "planner / 界面展示",
    "renderer": "registry.get()：像素来源",
    "text": "orchestrator._slot_plan + 渲染器（叠字层）：文字由谁产生",
    "mandatory": "orchestrator：不可关闭；schema：平台档位校验",
    "needs": "src/assets.py：齐套校验（决定张数）",
    "background": "renderers + schema：底色来源；schema 与渲染器声明的"
                  "可产出集合交叉校验",
    "validate_level": "validators.validate",
}
SLOT_OPTIONAL_KEYS = {
    "validate_rules": "validators.validate",
    "product_fill_pct": "renderers/compose_white + flat_overlay（主体占画布比例）"
                        " / validators.check_product_fill",
    "contact_shadow": "synth._draw_contact_shadow",
    "max_callouts": "orchestrator._slot_plan（按它截断文案条数）",
    "annotation": "renderers/flat_overlay：要不要画双箭头标注线（none|dimension）",
}
ALLOWED_SLOT_KEYS = {**SLOT_REQUIRED_KEYS, **SLOT_OPTIONAL_KEYS}

ALLOWED_CATALOG = {
    "version": "schema 自身",
    "category": "schema：与 slots.yaml 一致性",
    "label": "界面展示",
    "palette": "M3 flat_overlay / textlayer 取色",
    "validate_level_default": "schema：坑位未声明强度时的默认值",
    "bg_prompt_hints": "M4 gen_bg_paste：位置 4 取景提示",
}
CATALOG_REQUIRED = ("version", "category", "palette", "validate_level_default",
                    "bg_prompt_hints")
PALETTE_REQUIRED = ("base", "text", "accent")

# ------------------------------------------------------------
# 取值域
# ------------------------------------------------------------
TEXT_MODES = ("none", "overlay")   # native 已从字段字典删除（实测不可控、不可复现）
BACKGROUNDS = ("pure_white", "palette", "generated", "from_photo")
ANNOTATIONS = ("none", "dimension")   # 标注线：flat_overlay 解释
ASSET_KINDS = ("front", "closeup", "contents", "competitor", "bullets", "specs")
LEVELS = ("strict", "medium", "loose")

# 平台规则档位：强制坑位必须同时满足下面全部条件。
# 这是 site 字段的**消费位置** —— 它不是一个装饰性标签。
SITE_PROFILES = {
    "US": {
        "label": "亚马逊美国站",
        "mandatory_requires": {
            "background": "pure_white",
            "text": "none",
            "validate_level": "strict",
            "validate_rules": ("white_bg_purity", "product_fill", "has_text_block"),
        },
    },
}

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


# ------------------------------------------------------------
# 行号索引：yaml.safe_load 会丢掉行号，报错时必须能指出是哪一行
# ------------------------------------------------------------
def build_line_index(text: str) -> dict:
    root = yaml.compose(text)
    idx: dict = {"top": {}, "slots": []}
    if not isinstance(root, yaml.MappingNode):
        return idx
    for k, v in root.value:
        idx["top"][k.value] = k.start_mark.line + 1
        if k.value == "slots" and isinstance(v, yaml.SequenceNode):
            for item in v.value:
                keys: dict[str, int] = {}
                if isinstance(item, yaml.MappingNode):
                    for kk, _ in item.value:
                        keys[kk.value] = kk.start_mark.line + 1
                idx["slots"].append(keys)
    return idx


def _at(idx: dict, slot_i: int | None, key: str, fallback_key: str) -> str:
    """返回 "config/slots.yaml:41" 形式的定位串。"""
    if slot_i is None:
        line = idx["top"].get(key) or idx["top"].get(fallback_key) or 1
    else:
        slot_keys = idx["slots"][slot_i] if slot_i < len(idx["slots"]) else {}
        line = (slot_keys.get(key) or slot_keys.get("id")
                or idx["top"].get("slots") or 1)
    return f"{SLOTS_REL}:{line}"


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}  {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}  {msg}")


# ------------------------------------------------------------
# 校验
# ------------------------------------------------------------
def _check_whitelist(raw: dict, allowed: dict, where: str, rep: Report,
                     what: str, *, key_lines: dict | None = None,
                     whitelist_name: str = "") -> None:
    """白名单检查：表里不许出现没有消费方的字段。

    key_lines 给出"字段名 → 行号"的精确映射；没有的话退回到块的起始行。
    报错必须指到**越界字段自己那一行** —— 指到别处等于让人再找一遍。
    """
    hint = (f"新增字段需先在 src/schema.py 的 {whitelist_name} 里登记消费方"
            if whitelist_name else
            "新增字段需先在 src/schema.py 对应白名单里登记消费方")
    for k in raw:
        if k not in allowed:
            loc = (f"{SLOTS_REL}:{key_lines[k]}"
                   if key_lines and k in key_lines else where)
            rep.err(loc, f"{what}出现未登记字段 {k!r} —— "
                         f"没有消费方的字段不许进表（{hint}）")


def _check_catalog(cfg: dict, rep: Report, where: str) -> dict | None:
    rel = cfg.get("catalog")
    if not rel:
        rep.err(where, "缺少 catalog 字段（类目模板路径）")
        return None
    path = ROOT / rel
    if not path.exists():
        rep.err(where, f"catalog 指向的文件不存在：{rel}")
        return None
    try:
        cat = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        rep.err(f"{rel}:1", f"YAML 解析失败：{e}")
        return None
    if not isinstance(cat, dict):
        rep.err(f"{rel}:1", "catalog 根节点必须是映射")
        return None

    _check_whitelist(cat, ALLOWED_CATALOG, f"{rel}:1", rep, "catalog ")
    for k in CATALOG_REQUIRED:
        if k not in cat:
            rep.err(f"{rel}:1", f"catalog 缺少必填字段 {k!r}")
    if cat.get("category") != cfg.get("category"):
        rep.err(f"{rel}:1",
                f"catalog.category={cat.get('category')!r} 与 "
                f"slots.yaml 的 category={cfg.get('category')!r} 不一致")
    if cat.get("validate_level_default") not in LEVELS:
        rep.err(f"{rel}:1",
                f"validate_level_default={cat.get('validate_level_default')!r} 非法，"
                f"可选：{'/'.join(LEVELS)}")
    pal = cat.get("palette") or {}
    if not isinstance(pal, dict):
        rep.err(f"{rel}:1", "palette 必须是映射")
    else:
        for k in PALETTE_REQUIRED:
            v = pal.get(k)
            if not (isinstance(v, str) and _HEX.match(v)):
                rep.err(f"{rel}:1",
                        f"palette.{k}={v!r} 不是 #RRGGBB 颜色")
        _check_whitelist(pal, {k: "" for k in PALETTE_REQUIRED},
                         f"{rel}:1", rep, "palette ")
    hints = cat.get("bg_prompt_hints")
    if not (isinstance(hints, list) and hints):
        rep.err(f"{rel}:1",
                "bg_prompt_hints 必须是非空列表（M4 位置 4 的取景提示来源）")
    return cat


def validate_table(text: str, rep: Report) -> dict:
    idx = build_line_index(text)
    try:
        cfg = yaml.safe_load(text)
    except yaml.YAMLError as e:
        rep.err(f"{SLOTS_REL}:1", f"YAML 解析失败：{e}")
        return {}
    if not isinstance(cfg, dict):
        rep.err(f"{SLOTS_REL}:1", "根节点必须是映射")
        return {}

    top_where = _at(idx, None, "version", "version")
    _check_whitelist(cfg, ALLOWED_TOP, top_where, rep, "顶层")

    if cfg.get("version") != 2:
        rep.err(_at(idx, None, "version", "version"),
                f"version={cfg.get('version')!r} —— 本校验器只认 v2 表")

    site = cfg.get("site")
    if site not in SITE_PROFILES:
        rep.err(_at(idx, None, "site", "site"),
                f"site={site!r} 未定义规则档位，可选：{'/'.join(SITE_PROFILES)}")

    _check_catalog(cfg, rep, _at(idx, None, "catalog", "catalog"))

    # ---- export
    exp = cfg.get("export") or {}
    if not isinstance(exp, dict):
        rep.err(_at(idx, None, "export", "export"), "export 必须是映射")
        exp = {}
    else:
        _check_whitelist(exp, ALLOWED_EXPORT, _at(idx, None, "export", "export"),
                         rep, "export ")
        for k in ALLOWED_EXPORT:
            if k not in exp:
                rep.err(_at(idx, None, "export", "export"),
                        f"export 缺少必填字段 {k!r}（消费方：{ALLOWED_EXPORT[k]}）")
        if isinstance(exp.get("long_side_px"), int) and \
                isinstance(exp.get("min_long_side_px"), int) and \
                exp["long_side_px"] < exp["min_long_side_px"]:
            rep.err(_at(idx, None, "export", "export"),
                    "long_side_px 小于 min_long_side_px —— 出图必然过不了平台下限")
        if isinstance(exp.get("filename_pattern"), str) and \
                "{upc}" not in exp["filename_pattern"]:
            rep.err(_at(idx, None, "export", "export"),
                    "filename_pattern 必须含 {upc} —— 文件名不含产品标识会阻碍过审")

    # ---- 先加载渲染器，否则 renderer 名无从校验
    registry.load_all()
    known_renderers = set(registry.known())
    rules_impl = set(validators.KNOWN_RULES)

    slots = cfg.get("slots")
    if not isinstance(slots, list) or not slots:
        rep.err(_at(idx, None, "slots", "slots"), "slots 必须是非空列表")
        return cfg
    if len(idx["slots"]) != len(slots):
        rep.warn(f"{SLOTS_REL}:1",
                 f"行号索引与解析结果的槽位数不一致"
                 f"（{len(idx['slots'])} vs {len(slots)}）—— 报错定位可能偏移")

    seen_ids: set = set()
    model_calls = 0
    profile = SITE_PROFILES.get(site, {}).get("mandatory_requires", {})

    for i, slot in enumerate(slots):
        if not isinstance(slot, dict):
            rep.err(_at(idx, i, "id", "id"), f"第 {i + 1} 个槽位必须是映射")
            continue
        sid = slot.get("id")
        tag = f"坑位 {sid}"

        # 必填 / 白名单
        for k in SLOT_REQUIRED_KEYS:
            if k not in slot:
                rep.err(_at(idx, i, "id", "id"),
                        f"{tag} 缺少必填字段 {k!r}（消费方：{SLOT_REQUIRED_KEYS[k]}）")
        _check_whitelist(slot, ALLOWED_SLOT_KEYS, _at(idx, i, "id", "id"),
                         rep, f"{tag} ",
                         key_lines=idx["slots"][i] if i < len(idx["slots"]) else None,
                         whitelist_name="SLOT_REQUIRED_KEYS / SLOT_OPTIONAL_KEYS")

        if not isinstance(sid, int) or isinstance(sid, bool):
            rep.err(_at(idx, i, "id", "id"), f"{tag} 的 id 必须是整数，实际 {sid!r}")
        elif sid in seen_ids:
            rep.err(_at(idx, i, "id", "id"), f"{tag} 的 id 重复")
        else:
            seen_ids.add(sid)

        # ---- renderer：必须已登记
        rn = slot.get("renderer")
        if rn not in known_renderers:
            rep.err(_at(idx, i, "renderer", "id"),
                    f"{tag} 的 renderer={rn!r} 未登记；可用："
                    f"{'、'.join(sorted(known_renderers)) or '（无）'}")
        elif registry.calls_model(rn):
            # 声明式读取：**不执行渲染**。否则配置校验会变成一次真实出图。
            model_calls += 1

        # ---- text：closed set（native 已删除）
        tx = slot.get("text")
        if tx not in TEXT_MODES:
            rep.err(_at(idx, i, "text", "id"),
                    f"{tag} 的 text={tx!r} 非法，可选：{'/'.join(TEXT_MODES)}"
                    f"（native 因不可控、不可复现已从字典删除）")

        # ---- background：closed set
        bg = slot.get("background")
        if bg not in BACKGROUNDS:
            rep.err(_at(idx, i, "background", "id"),
                    f"{tag} 的 background={bg!r} 非法，可选：{'/'.join(BACKGROUNDS)}")
        elif rn in known_renderers:
            # ---- background × renderer 交叉校验
            #
            # 这道检查补的是「已知缺口」里记着的那一条。它必须有，因为：
            #   `background` 原先**没有任何渲染器去读** —— 每个渲染器都把自己的底
            #   写死在代码里。于是"位置 2 用 compose_white + background: palette"
            #   能通过校验，而 compose_white 根本不看 palette：表在说一件事，
            #   代码在做另一件事，而两边都不报错。
            #   渲染器现在声明自己**能产出**哪些底（registry.register(backgrounds=…)），
            #   这里把两种说法对起来 —— 换渲染器时 background 必须跟着改，
            #   不然启动就炸。于是 background 从"描述性字段"变成"被校验的契约"。
            allowed_bg = registry.backgrounds_of(rn)
            if allowed_bg and bg not in allowed_bg:
                rep.err(_at(idx, i, "background", "id"),
                        f"{tag} 的 renderer={rn} 只能产出 "
                        f"{'/'.join(allowed_bg)} 底，但 background={bg!r} —— "
                        f"两者必须一致（换渲染器时 background 要跟着改）")

        # ---- annotation：closed set + 与 text 的一致性
        ann = slot.get("annotation", "none")
        if ann not in ANNOTATIONS:
            rep.err(_at(idx, i, "annotation", "id"),
                    f"{tag} 的 annotation={ann!r} 非法，可选：{'/'.join(ANNOTATIONS)}")
        elif ann != "none" and tx != "overlay":
            # 标注线上的标签是**用字体文件绘出来的文字** —— 没有文字层就没有标签，
            # 而没有标签的标注线没有信息量。这种配置本身就是错的，拦在启动期。
            rep.err(_at(idx, i, "annotation", "id"),
                    f"{tag} 的 annotation={ann!r} 但 text={tx!r} —— "
                    f"标注标签要靠字体绘制，text 不是 overlay 就没有文字层")

        # ---- needs：非空 + 取值域
        needs = slot.get("needs")
        if not isinstance(needs, list) or not needs:
            rep.err(_at(idx, i, "needs", "id"),
                    f"{tag} 的 needs 必须是非空列表 —— 空 needs 意味着"
                    f"「什么都不缺」，于是缺料也照做，齐套门禁失效")
        else:
            for a in needs:
                if a not in ASSET_KINDS:
                    rep.err(_at(idx, i, "needs", "id"),
                            f"{tag} 的 needs 含未知素材 {a!r}，可选："
                            f"{'/'.join(ASSET_KINDS)}")

        # ---- cuts × needs 交叉校验
        #
        # 渲染器声明的"要求先抠好"的素材，必须是它 needs 里已经要了的东西。
        # 少了这道检查会出现一种很难看的状态：渲染器说"我要抠好的 competitor"，
        # 而齐套判定根本没要求 competitor —— 于是缺料时这一格照样开跑，
        # 跑到渲染器里才发现素材是空的（那时已经在烧钱的路上了）。
        if rn in known_renderers:
            declared_cuts = registry.cuts_of(rn)
            if isinstance(needs, list):
                extra = [c for c in declared_cuts if c not in needs]
                if extra:
                    rep.err(_at(idx, i, "needs", "id"),
                            f"{tag} 的 renderer={rn} 声明要抠 "
                            f"{'、'.join(extra)}，但 needs 里没有它 —— "
                            f"齐套判定就不会拦住缺料。needs 必须包含 "
                            f"{'、'.join(declared_cuts)}")

        # ---- validate_level / validate_rules
        lvl = slot.get("validate_level")
        if lvl not in LEVELS:
            rep.err(_at(idx, i, "validate_level", "id"),
                    f"{tag} 的 validate_level={lvl!r} 非法，可选：{'/'.join(LEVELS)}")
        rules = slot.get("validate_rules")
        if rules is None:
            if lvl is not None:
                rep.warn(_at(idx, i, "validate_level", "id"),
                         f"{tag} 未声明 validate_rules，只按 level={lvl} 跑默认项")
            rules = []
        elif not isinstance(rules, list):
            rep.err(_at(idx, i, "validate_rules", "id"),
                    f"{tag} 的 validate_rules 必须是列表")
            rules = []
        else:
            for r in rules:
                if r not in rules_impl:
                    rep.err(_at(idx, i, "validate_rules", "id"),
                            f"{tag} 声明了 {r!r}，但 validators.py 未实现该规则 —— "
                            f"这是「声称校验、实际静默跳过」。已实现："
                            f"{'、'.join(sorted(rules_impl))}")
        rules = [r for r in rules if isinstance(r, str)]

        # ---- 文字与校验必须一致：叠了字就得有人验，不出字就不该验
        if tx == "overlay" and "text_present" not in rules:
            rep.err(_at(idx, i, "validate_rules", "id"),
                    f"{tag} text=overlay 但 validate_rules 无 text_present —— "
                    f"叠字层如果没画上去，这份配置验不出来")
        if tx == "none" and "text_present" in rules:
            rep.err(_at(idx, i, "validate_rules", "id"),
                    f"{tag} text=none 却声明校验 text_present —— 必然误报")

        # ---- 条件必填：max_callouts
        mc = slot.get("max_callouts")
        if tx == "overlay":
            if not isinstance(mc, int) or isinstance(mc, bool):
                rep.err(_at(idx, i, "max_callouts", "id"),
                        f"{tag} text=overlay 必须声明 max_callouts（整数）")
            elif not 1 <= mc <= 5:
                rep.err(_at(idx, i, "max_callouts", "id"),
                        f"{tag} 的 max_callouts={mc} 超出 1-5 —— "
                        f"超过 5 条移动端不可读")
        elif mc is not None:
            rep.err(_at(idx, i, "max_callouts", "id"),
                    f"{tag} text={tx!r} 不该声明 max_callouts（无文字可排）")

        # ---- 条件必填：product_fill_pct
        pfp = slot.get("product_fill_pct")
        if "product_fill" in rules:
            if not isinstance(pfp, (int, float)) or isinstance(pfp, bool):
                rep.err(_at(idx, i, "product_fill_pct", "id"),
                        f"{tag} 声明了 product_fill 校验，必须同时给出 "
                        f"product_fill_pct（否则校验用默认 85%，与出图参数脱节）")
            elif not 20 <= float(pfp) <= 100:
                rep.err(_at(idx, i, "product_fill_pct", "id"),
                        f"{tag} 的 product_fill_pct={pfp} 超出 20-100")
        elif pfp is not None and bg == "pure_white":
            rep.warn(_at(idx, i, "product_fill_pct", "id"),
                     f"{tag} 声明了 product_fill_pct 却没开 product_fill 校验")

        if "contact_shadow" in slot and not isinstance(slot["contact_shadow"], bool):
            rep.err(_at(idx, i, "contact_shadow", "id"),
                    f"{tag} 的 contact_shadow 必须是布尔值")

        # ---- 平台档位：强制坑位必须满足站点的硬要求
        if slot.get("mandatory"):
            if not isinstance(needs, list) or "front" not in needs:
                rep.err(_at(idx, i, "needs", "id"),
                        f"{tag} 是平台强制项，needs 必须含 'front' "
                        f"（没有正面原片就没有主体，任何图都做不出来）")
            for fk, want in profile.items():
                got = slot.get(fk)
                if fk == "validate_rules":
                    missing = [r for r in want if r not in rules]
                    if missing:
                        rep.err(_at(idx, i, "validate_rules", "id"),
                                f"{tag} 是 {site} 站的强制坑位，validate_rules 缺 "
                                f"{'、'.join(missing)}（平台硬要求，不能省）")
                elif got != want:
                    rep.err(_at(idx, i, fk, "id"),
                            f"{tag} 是 {site} 站的强制坑位，{fk} 必须为 {want!r}，"
                            f"实际 {got!r}")

    # ---- 反向检查：登记了、但表里没人用的渲染器
    #
    # 上面那条只查「表里的名字是否已登记」（正向）。少了反向，会出现一种静默漂移：
    # 表改用新渲染器之后，旧渲染器文件仍在 registry 里登记着 —— 于是 known() 数出 6 个、
    # README §5 的目录树列 6 个、界面的控制面页显示 6 个，而真正被用的只有一个。
    # **没有任何东西会说「这 5 个该删了」。**
    #
    # v4 迁移的第一步就会撞上它：主路 2–7 改走 gen_from_ref，5 个确定性渲染器随之作废。
    # 没有这条检查，那一步会「改完即绿」而库里留下 5 个没人读的像素来源 ——
    # 这正是本项目第一条硬教训的形态：声明还在，消费方没了。
    #
    # 出口是已有的：要在接进表之前先放一个渲染器，文件名以下划线开头即可
    # （registry.load_all 跳过下划线文件），或者登记完立刻接进表。
    used = {s.get("renderer") for s in slots if isinstance(s, dict)}
    orphans = sorted(set(known_renderers) - used)
    if orphans:
        rep.err(_at(idx, None, "slots", "slots"),
                f"渲染器 {'、'.join(orphans)} 已登记但没有任何坑位在用 —— "
                f"没有消费方的渲染器不许留在库里（删掉 src/renderers/ 下对应文件，"
                f"或先把它接进表）。表里在用："
                f"{'、'.join(sorted(x for x in used if x)) or '（无）'}")

    rep._model_calls = model_calls  # type: ignore[attr-defined]
    return cfg


def assert_valid(slots_path: str | Path | None = None) -> dict:
    """编排器的启动入口：校验通过返回 cfg，否则抛 ValueError（带上全部问题）。

    表错了必须在**开始跑之前**炸。等跑到一半才发现某个 renderer 没登记、
    某个规则名没实现，那时已经白烧了时间和调用费。
    """
    path = Path(slots_path) if slots_path else (ROOT / SLOTS_REL)
    rep = Report()
    cfg = validate_table(path.read_text(encoding="utf-8"), rep)
    if rep.errors:
        raise ValueError("坑位表校验失败：\n  " + "\n  ".join(rep.errors))
    return cfg


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="坑位规范表校验器")
    ap.add_argument("--slots", default=str(ROOT / SLOTS_REL),
                    help="坑位表路径")
    args = ap.parse_args(argv)

    path = Path(args.slots)
    if not path.exists():
        print(f"错误：找不到坑位表 {path}")
        return 2
    text = path.read_text(encoding="utf-8")

    rep = Report()
    cfg = validate_table(text, rep)

    for w in rep.warnings:
        print(f"警告  {w}")
    if rep.errors:
        print(f"\n校验失败：{len(rep.errors)} 个问题\n")
        for e in rep.errors:
            print(f"  {e}")
        return 1

    n_slots = len(cfg.get("slots") or [])
    n_renderers = len(registry.known())
    print(f"OK: {n_slots} slots, {n_renderers} renderers registered")
    print()
    print(f"  {'坑':<3}{'renderer':<18}{'text':<9}{'调模型':<7}{'needs':<26}校验")
    for s in cfg["slots"]:
        rn = s.get("renderer")
        calls = "是" if registry.calls_model(rn) else "否"
        print(f"  {s.get('id'):<3}{rn:<18}{s.get('text'):<9}{calls:<7}"
              f"{','.join(s.get('needs') or []):<26}{s.get('validate_level')}")
    print()
    print(f"  调模型的路数：{getattr(rep, '_model_calls', 0)} / {n_slots}"
          f"   （其余全是确定性合成）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
