r"""坑位卡生成器 —— 把「跨切面文档」换成「一份对应一个动作的交付单元」。

为什么必须有它（这是本项目最深的一处错位）
------------------------------------------
本项目此前有 9 份设计文档：业务逻辑 / 业务流程与提效设计 / 系统设计方案 /
架构设计 / 设计复审 / AI生图可控性与验证设计 / 最小可行设计 / 使用形态 /
实施计划。它们每一份对应一个**横切面** —— 读九份才能拼出「这一格该怎么用」。

而参考的三个电商图技能库是 26 份 `skill.md`：每一份对应**一个动作**
（触发语 / 能力边界含"不做" / 输入阈值 / 参数带理由 / 模板 / 执行步骤 /
现象-原因-处理），**读一份就能干活**。

差别不在篇幅（它们 10364 行，本项目 4662 行），在**交付单元的粒度**：
它们的单元是卡，本项目的单元是章节。于是"每个新接触的人
（包括隔两周回来的自己）都必须现场把九份文档在脑子里合成一次"。

这个脚本把那一次合成**固化成 7 张由表生成的卡**。

卡与索引的分工（这条分工是**行数上限逼出来的**，不是排版偏好）
------------------------------------------------------------
第一版把每张卡都写成"自给自足"的：齐套判定的消费方、不变量 A 的说明、
抠图为什么提前、导出阈值、签字清单 —— 七项**每张卡都抄一遍**。
结果 4 张卡越过 70 行上限，而被砍掉的那些字里**没有一句是这一格特有的**。

于是分工改为：

    docs/cards/README.md   七格**共有**的规矩（齐套 / 唯一主体 / 抠图提前 /
                           阈值 / 签字 / 分级判据出处）—— 只写一次
    docs/cards/slot-N.md   这一格**与别格不同**的地方：像素从哪来、要不要文字、
                           缺什么料就跳过、失败走哪一级、照抄哪条命令

这不是省事，是把"七份互相漂移的副本"变回"一份正本"。
谁要是把共有段落拷回某张卡，行数上限会先炸 —— 这条上限就是这份分工的守卫。

生成而不是手写
--------------
手写 7 张卡 = 7 份会漂移的副本。所以：卡**由 `slots.yaml` 生成**，
带横幅、由 `tools/check_docs.py` 校验一致性。
改一格的行为 → 改 `slots.yaml` 那一行 → 重跑本脚本。

卡里没有一句是新的知识
----------------------
每一行的来源都是可指认的：
    行为 / 素材需求 / 阈值      ← config/slots.yaml
    像素来源 / 是否调模型 / 抠图需求 ← src/registry.py 的渲染器声明
    出错走哪一级                ← src/fixers.py 的 CHECK_RUNG
    要签的字                    ← src/intake.py 的 ATTEST_ITEMS
卡只是一个**把散落在代码里的判断点，按坑位重新排版**的视图。

代码围栏约定（守卫依赖它，见 tools/check_docs.py）
------------------------------------------------
    ```bash    check_docs **会执行**它（缺 --dry-run 就自动补一个再跑）
    ```text    不执行 —— 只给人看的示例（例如"重做"需要先有一轮产物）

用法：
    python tools/gen_slot_cards.py            # 生成/更新 docs/cards/
    python tools/gen_slot_cards.py --check    # 只比对不写，有差异退出码 2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402  （控制台编码归一：见 src/console.py）
enable_utf8()

import fixers      # noqa: E402
import intake      # noqa: E402
import registry    # noqa: E402
import schema      # noqa: E402
import validators  # noqa: E402

OUT_DIR = ROOT / "docs" / "cards"

BANNER = ("<!-- ⚠️ 由 tools/gen_slot_cards.py 从 config/slots.yaml 生成，"
          "不要直接改这里。 -->")
BANNER2 = ("<!-- 改这一格 → 改 config/slots.yaml → 跑 "
           "`python tools/gen_slot_cards.py`；一致性由 "
           "`python tools/check_docs.py` 守卫。 -->")

# 每张卡的行数上限。**上限本身就是一条判据**：
# 卡一旦长起来，它就退化成文档 —— 而卡存在的理由恰恰是"短到能一次读完"。
# 参考库的同类上限是 skill.md 正文 ≤ 500 行、description ≤ 400 字符。
# 这里另外还兼职守卫"卡与索引的分工"：七格共有的段落写进某张卡，这张卡立刻超限。
MAX_CARD_LINES = 70

EXAMPLE_PRODUCT = "examples/product_fullset.json"

BACKGROUND_DOC = {
    "pure_white": "纯白画布（常量，不是生成）",
    "palette": "类目色板（常量，**确定性挑选**，不是随机 —— 否则重做会换一张图）",
    "generated": "**模型生成的空背景**（全表唯一一处；主体事后确定性贴入）",
    "from_photo": "原片裁切（事实像素，**不许把别的图放大充数**）",
}

NEED_DOC = {
    "front": "正面原片",
    "closeup": "特写原片",
    "contents": "内容物原片",
    "competitor": "竞品原片",
    "bullets": "卖点文案",
    "specs": "规格参数",
}

RUNG_NAME = {
    fixers.L0_DETERMINISTIC: "L0",
    fixers.L1_REPLAY: "L1",
    fixers.L2_REGENERATE: "L2",
    fixers.L3_HUMAN: "L3",
}


def _rung_row(rule: str) -> str:
    rung, why = fixers.rung_of(rule)
    return f"| `{rule}` | **{RUNG_NAME.get(rung, rung)}** | {why} |"


def _not_doing(slot: dict, total: int, model_slots: int) -> list[str]:
    """从表推出「这一格不做什么」—— 全部是推导，没有一句是手写的常识。

    只留**这一格特有**的。七格共有的那条（缺料不凑图）在索引里，
    因为它在每张卡里一字不差 —— 七份副本就是七次漂移的机会。
    """
    rn = slot["renderer"]
    out: list[str] = []
    if not registry.calls_model(rn):
        out.append(f"- **不调生成模型**：本格像素全部来自事实（原片 / 文字 / 常量）。"
                   f"全表 {total} 格里只有 {model_slots} 格能调模型 —— "
                   f"判据是「这块像素有没有事实持有者」，不是「这张图重不重要」。")
    if slot.get("text") == "none":
        out.append("- **不叠字**：本格的平台档位要求画面里没有任何文字。")
    else:
        out.append("- **不让模型画字**：文字用字体文件绘制，所以"
                   "**不可能出现错别字**（代价是排版朴素 —— 错字是事故，难看不是）。")
    if slot.get("background") == "from_photo":
        out.append("- **不读主体**：本格的像素来自它自己的原片，"
                   "所以主体抠图失败**不影响**这一格。")
    return out


def _card(slot: dict, cfg: dict, model_slots: int) -> str:
    total = len(cfg["slots"])
    sid = slot["id"]
    rn = slot["renderer"]
    calls = registry.calls_model(rn)
    needs = list(slot.get("needs") or [])
    rules = validators.effective_rules(slot)

    L: list[str] = [BANNER, BANNER2, ""]
    L.append(f"# 坑位 {sid} · {slot.get('purpose') or slot.get('role')}")
    L.append("")
    L.append(f"**一句话**：{registry.summary_of(rn)}")
    L.append("")
    L.append("| 属性 | 值 |")
    L.append("|---|---|")
    L.append(f"| 渲染器 | `{rn}`（{registry.label_of(rn)}） |")
    L.append(f"| 调生成模型 | **{'是' if calls else '否'}**"
             f"（全表 {model_slots}/{total} 格调模型） |")
    L.append(f"| 背景 | `{slot.get('background')}` —— "
             f"{BACKGROUND_DOC.get(str(slot.get('background')), '？')} |")
    L.append(f"| 文字 | `{slot.get('text')}` |")
    L.append(f"| 平台强制项 | {'是（不可关闭）' if slot.get('mandatory') else '否'} |")
    L.append(f"| 校验强度 | `{slot.get('validate_level')}`"
             f"（实际跑 {len(rules)} 项） |")
    if slot.get("product_fill_pct") is not None:
        L.append(f"| 主体占比 | {slot['product_fill_pct']}%"
                 f"（出图参数与校验判据是**同一个数**） |")
    if slot.get("max_callouts"):
        L.append(f"| 文案条数上限 | {slot['max_callouts']} |")
    if slot.get("annotation") == "dimension":
        L.append("| 标注线 | 双箭头（标签取自 specs 的单轴数值） |")
    L.append("")

    L.append("## 要什么 —— 缺任何一项就**跳过这一格**（不报错、不凑图）")
    L.append("")
    L.append("| 素材 | 是什么 | 缺了会怎样 |")
    L.append("|---|---|---|")
    for n in needs:
        L.append(f"| `{n}` | {NEED_DOC.get(n, '？')} | 跳过这一格 |")
    L.append("")

    L.append("## 不做的事")
    L.append("")
    L.extend(_not_doing(slot, total, model_slots))
    L.append("")

    L.append("## 出错走哪一级（从便宜往贵试，**不许跳级**）")
    L.append("")
    L.append("| 校验项 | 走 | 为什么 |")
    L.append("|---|---|---|")
    for r in rules:
        L.append(_rung_row(r))
    L.append("")

    L.append("## 照抄")
    L.append("")
    L.append("```bash")
    L.append(f"python run.py --product {EXAMPLE_PRODUCT} --only {sid} --dry-run")
    L.append(f"python run.py --product {EXAMPLE_PRODUCT} --only {sid}")
    L.append("```")
    L.append("")
    L.append("```text")
    if slot.get("text") != "none":
        L.append("# 改了一句卖点之后，只重排文字层（秒级、零模型调用）：")
        L.append(f"python run.py --product {EXAMPLE_PRODUCT} --redo {sid} --layer text")
    else:
        L.append("# 只挪主体位置（免费：生成底被复用，不会重新调模型）：")
        L.append(f"python run.py --product {EXAMPLE_PRODUCT} --redo {sid} "
                 f"--layer placement")
    L.append("```")
    L.append("")
    L.append("> 七格**共有**的规矩（齐套怎么算 / 主体为什么只有一份 / 抠图为什么提前 / "
             "导出阈值 / 要签什么字）在 [索引](README.md) 里 —— 那些话每张卡都一样，"
             "所以只写一遍。")
    L.append("")
    return "\n".join(L)


def _index(cards: list[tuple[dict, str]], cfg: dict) -> str:
    """索引页。它回答两件事：「我该读哪一张」+「七格共有的规矩是什么」。"""
    total = len(cfg["slots"])
    export = cfg["export"]
    model_slots = sum(1 for s in cfg["slots"]
                      if registry.calls_model(s["renderer"]))
    any_text = any((s.get("text") or "none") != "none" for s in cfg["slots"])
    any_cuts = any(registry.cuts_of(s["renderer"]) for s in cfg["slots"])

    L = [BANNER, BANNER2, ""]
    L.append("# 坑位卡索引")
    L.append("")
    L.append(f"一份对应一个动作的交付单元。由 `config/slots.yaml` 生成，"
             f"**读它就不用读代码**。")
    L.append("")
    L.append("| 坑 | 用途 | 渲染器 | 调模型 | 要的素材 | 卡 |")
    L.append("|---|---|---|---|---|---|")
    for slot, _ in cards:
        needs = "、".join(f"`{n}`" for n in (slot.get("needs") or []))
        L.append(f"| {slot['id']} | {slot.get('purpose')} | "
                 f"`{slot['renderer']}` | "
                 f"{'**是**' if registry.calls_model(slot['renderer']) else '否'} | "
                 f"{needs} | [slot-{slot['id']}.md](slot-{slot['id']}.md) |")
    L.append("")
    L.append(f"全表 {total} 格，其中 **{model_slots} 格**调用生成模型。")
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 七格共有的规矩（卡里不重复写 —— 每张都一样的话只该有一份）")
    L.append("")
    L.append("- **缺料不凑图。** 缺任何一项素材就跳过那一格，不拿别的图顶上 —— "
             "凑出来的图花掉的是信任。\"没拍特写\"与\"拍糊了\"是两件不同的事："
             "前者跳过，后者整批拒收。")
    L.append(f"- **张数是算出来的，不是配置项。** 实际出几张 = 本表 ∩ 素材齐套，"
             f"消费方是 `src/assets.py`。没有\"输出几张\"这种设置。")
    L.append("- **主体只有一份（不变量 A）。** 凡需要 `front` 的格子读的是同一份 "
             "`subject.png`、同一个 sha256。所以「几张图里的杯子不是同一个杯子」"
             "在结构上不可能发生 —— 这是数据约束，不是提示词里的期望。")
    if any_cuts:
        L.append("- **抠图提前、集中做。** 渲染器声明要求先抠好的素材（见 "
                 "`src/registry.py` 的 `cuts` 声明），抠图一律排在任何模型调用**之前**："
                 "抠图失败就不该再烧调用费，而且一轮只抠一次 —— "
                 "于是\"只改了位置\"的重做不必重抠，产出的像素与上一版逐字节一致。")
    L.append("- **出错走哪一级的判据一处定义**，在 `src/fixers.py` 的 `CHECK_RUNG`。"
             "加一条校验规则时必须同时给它归类，否则「它落到哪一级」就变成"
             "没人说得清的问题。")
    L.append(f"- **阈值（出图与校验共用，不许两处各写一份）**："
             f"画布 {export['long_side_px']}×{export['long_side_px']}，"
             f"平台下限长边 {export['min_long_side_px']}px，"
             f"体积上限 {export['max_file_mb']}MB，JPEG 质量 {export['jpeg_quality']}；"
             f"文件名 `{export['filename_pattern']}` 必须含 UPC —— "
             f"文件名不含产品标识会阻碍过审。")
    L.append("")
    L.append("## 要签的字（工具判不了，须有人负责，不签不出图）")
    L.append("")
    L.append("| 签字项 | 什么时候要求 |")
    L.append("|---|---|")
    # 四个键直接取自 intake.ATTEST_ITEMS —— 它们就是 `attest.confirmed` 里
    # 要逐字写对的那几个字符串，所以这里显示**键名**而不是中文描述：
    # 人要抄的是键名，抄错一个就等于没签。
    L.append(f"| {' / '.join(f'`{k}`' for k in intake.ATTEST_ITEMS)} "
             f"| 本次提供了任何图片素材（这四条都判不了：没有规则可写，"
             f"硬写一个启发式检测器产出的是**不可靠的告警** —— 那比不检更坏）|")
    if any_text:
        L.append(f"| `{intake.FONT_ATTEST_ITEM}` | 本次会出文字"
                 f"（`text != none` 的格子存在）|")
    L.append(f"| `{intake.COMPETITOR_ATTEST_ITEM}` | 位置 7 在本次的计划里"
             f"（它会把竞品原片并排放进成品图）|")
    L.append("")
    L.append("## 两条约定")
    L.append("")
    L.append("- **卡是生成的，不要直接改。** 改 `config/slots.yaml` 那一行，"
             "再跑 `python tools/gen_slot_cards.py`。"
             "不一致会被 `python tools/check_docs.py` 报成 `stale`。")
    L.append(f"- **围栏有语义**：```bash 里的命令守卫**会真跑**"
             f"（缺 `--dry-run` 就自动补上，守卫不替人花钱调模型）；"
             f"```text 里的是给人看的示例，不执行。"
             f"所以往卡里写命令时，能跑的放 bash，需要前置状态的放 text。")
    L.append("")
    return "\n".join(L)


def build() -> dict[str, str]:
    """返回 {相对路径: 内容}。**不写盘** —— 写盘是 main() 的事。"""
    cfg = schema.assert_valid()
    cards = [(s, "") for s in cfg["slots"]]
    model_slots = sum(1 for s in cfg["slots"]
                      if registry.calls_model(s["renderer"]))
    out: dict[str, str] = {}
    for slot, _ in cards:
        out[f"slot-{slot['id']}.md"] = _card(slot, cfg, model_slots)
    out["README.md"] = _index(cards, cfg)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="坑位卡生成器")
    ap.add_argument("--check", action="store_true",
                    help="只比对不写；有差异退出码 2")
    args = ap.parse_args(argv)

    want = build()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    stale: list[str] = []
    for name, text in sorted(want.items()):
        p = OUT_DIR / name
        cur = p.read_text(encoding="utf-8") if p.exists() else None
        if cur != text:
            stale.append(name)
            if not args.check:
                p.write_text(text, encoding="utf-8")

    # 逆向：目录里有、但表里已经没有的卡（删了坑位却留着卡 = 幽灵交付单元）
    known = set(want)
    ghosts = sorted(p.name for p in OUT_DIR.glob("*.md") if p.name not in known)

    if args.check:
        for n in stale:
            print(f"  stale  docs/cards/{n}")
        for n in ghosts:
            print(f"  多余   docs/cards/{n}（表里已无对应坑位）")
        if stale or ghosts:
            print(f"\n卡与表不一致：{len(stale)} 份待更新，{len(ghosts)} 份多余。"
                  f"跑 python tools/gen_slot_cards.py 即可（这不是「写错了」，"
                  f"只是产物未同步）。")
            return 2
        print(f"OK：{len(known)} 份卡与 config/slots.yaml 一致。")
        return 0

    print(f"已生成 {len(want) - len(stale)} 份未变 / 更新 {len(stale)} 份 → {OUT_DIR}")
    for n in stale:
        print(f"  写入  docs/cards/{n}")
    for n in ghosts:
        print(f"  ⚠️  docs/cards/{n} 已无对应坑位 —— 请手工确认是否删除")
    # 上限自检：卡长起来就退化成文档，而卡存在的理由恰恰是「短到能一次读完」。
    over = [n for n, t in want.items() if len(t.splitlines()) > MAX_CARD_LINES]
    if over:
        print(f"\n✗ 有卡超过 {MAX_CARD_LINES} 行上限：{'、'.join(over)}")
        print("  卡长了就退化成文档。先检查是不是把**七格共有**的段落抄进了卡里 ——"
              "共有段落归 docs/cards/README.md。")
        return 1
    print(f"全部 ≤ {MAX_CARD_LINES} 行。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
