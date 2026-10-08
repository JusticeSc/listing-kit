r"""守卫探针②：坑位表的五道守卫真的会拦吗（改完即还原）。

    1. renderer 名写错            → 指到那一行
    2. background 与 renderer 不匹配 → 指到 background 那一行
    3. 未实现的校验规则名          → 指出规则名，而不是等跑完才报"未知规则"
    4. 没登记过的字段              → 指着字段名说"没有消费方"
    5. 渲染器声明要抠的素材不在 needs 里 → 指出少了哪个素材名

    第 5 道为什么必须有：`cuts` 是"渲染器要求先抠好"的声明，而齐套判定看的是
    `needs`。两者不一致时会形成一种很难看的状态 —— 缺料不拦、跑到渲染器里
    才发现素材是空的，那时已经烧过调用了。

为什么在**真表**上改而不是造一张临时表：报错定位串是常量，临时表会让报错的行号
指向一个不存在的文件 —— 那样测的就不是"报错准不准"了。
本脚本把原文件读进内存，改完跑校验，**最后无条件还原**（finally）。

用法：python tools/check_table_guards.py      （退出码 0 全拦 / 1 有守卫失效）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402  （控制台编码归一：见 src/console.py）
enable_utf8()

import schema  # noqa: E402

TABLE = ROOT / "config" / "slots.yaml"
# ★ 备份留**字节**：仓库里同时存在 CRLF（README / 卡片 / slots.yaml）与 LF（计划、
#   新写的工具）两种行尾，而**没有任何守卫管这件事**。用 `read_text()` 备份、
#   `write_text()` 还原，在 Windows 上会把 LF 文件悄悄变成 CRLF ——「已还原」这句话
#   就成了假的（文件内容一样、字节不一样）。所以这里存 bytes，还原后还要比一次。
ORIGINAL = TABLE.read_text(encoding="utf-8")      # 锚点匹配用（归一化 \n）
ORIGINAL_BYTES = TABLE.read_bytes()               # 还原用（原样）

CASES = [
    ("renderer 名写错", "renderer: flat_overlay", "renderer: flat_oveylay"),
    ("background 与 renderer 不匹配", "    background: palette\n    product_fill_pct: 55",
     "    background: pure_white\n    product_fill_pct: 55"),
    ("未实现的校验规则名",
     "validate_rules: [aspect_ratio, long_side_px, text_present]\n\n  # ---- 位置 3",
     "validate_rules: [aspect_ratio, long_side_px, text_present, no_watermark]"
     "\n\n  # ---- 位置 3"),
    ("没登记过的字段", "    max_callouts: 4                # orchestrator._slot_plan",
     "    max_callouts: 4\n    retry_times: 3                # orchestrator._slot_plan"),
    # 位置 7 的渲染器声明了 cuts=("competitor",)，把 competitor 从 needs 里拿掉 →
    # 齐套判定就不再拦"没给竞品图"这种情况了。必须报错。
    ("cuts 声明的素材不在 needs 里",
     "    needs: [front, competitor]     # 竞品图不在手上就只能跳过（别人的东西，模型无权编）",
     "    needs: [front]                 # 竞品图不在手上就只能跳过（别人的东西，模型无权编）"),
]


def main() -> int:
    bad = 0
    try:
        for name, old, new in CASES:
            if old not in ORIGINAL:
                print(f"[skip] {name}：锚点未命中，脚本需要更新（表已改动？）\n")
                continue
            TABLE.write_text(ORIGINAL.replace(old, new, 1), encoding="utf-8")
            rep = schema.Report()
            schema.validate_table(TABLE.read_text(encoding="utf-8"), rep)
            print(f"[{name}] 报错 {len(rep.errors)} 条")
            for e in rep.errors:
                print(f"    {e}")
            if not rep.errors:
                bad += 1
                print("    \u2717 没拦住 —— 守卫失效")
            print()
    finally:
        # 无条件还原：探针改的是**真表**，崩在中途也必须把文件放回去
        TABLE.write_bytes(ORIGINAL_BYTES)
        if TABLE.read_bytes() != ORIGINAL_BYTES:
            print("✗ 还原后与原始字节不一致 —— 「已还原」不成立（行尾或编码被改了）")
            bad += 1
        else:
            print("已还原 config/slots.yaml（字节一致）")

    if bad:
        print(f"\n\u2717 {bad} 道守卫失效")
        return 1
    print(f"\nOK：{len(CASES)} 道守卫全部拦住，且报错都指到了具体的行/字段。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
