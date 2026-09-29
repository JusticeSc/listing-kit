r"""守卫探针①：`forbidden_on_image` 是不是真的有消费方。

背景：它原先只躺在 `config/brand.json` 里、**没有任何代码读它** ——
与 v1 那个"写着 no_watermark 却从未实现"的假校验同型（声明了却不生效的保护，
比没有保护更糟：它让人以为已经防住了）。现在 `planner.extract_facts` 把
`forbidden_words` 与 `forbidden_on_image` 取并集，并逐条记下**命中哪一份规则**
—— 下架申诉时要拿这个作依据。

用法：python tools/check_forbidden_rules.py      （退出码 0 通过 / 1 断言失败）
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402  （控制台编码归一：见 src/console.py）
enable_utf8()

import planner  # noqa: E402
from kit_config import load_brand  # noqa: E402

CASES = {
    "24小时长效保温": "（应当保留）",
    "全网最低价，绝对是最好的杯子": "forbidden_words",
    "限时折扣 199 元，扫码领券": "forbidden_on_image",
    "amazon's choice 同款": "forbidden_on_image",
}


def main() -> int:
    facts = planner.extract_facts({
        "upc": "B0PROBE",
        "title": "测试商品",
        "bullets": list(CASES),
        "specs": {"高度": "22 cm"},
    }, load_brand())

    print("保留：")
    for b in facts["bullets"]:
        print(f"  + {b}")
    print("拦下：")
    for d in facts["dropped_bullets"]:
        hit = "、".join(f"{h['word']}（{h['rule']}）" for h in d["hit"])
        print(f"  - {d['text']}   命中 {hit}")

    fails = []
    kept = [b for b, why in CASES.items() if why.startswith("（")]
    if sorted(facts["bullets"]) != sorted(kept):
        fails.append(f"该保留的被拦了或反之：{facts['bullets']} != {kept}")
    rules = {h["rule"] for d in facts["dropped_bullets"] for h in d["hit"]}
    if rules != {"forbidden_words", "forbidden_on_image"}:
        fails.append(f"命中规则不全：{sorted(rules)} —— "
                     f"两份清单必须都生效（这正是本探针要防的假保护）")

    print()
    if fails:
        for f in fails:
            print(f"  \u2717 {f}")
        return 1
    print("OK：两份清单都在生效，且命中规则被逐条记下。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
