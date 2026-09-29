r"""位置 4 的冻结快照（golden case）—— 只打在高风险的那一格。

为什么只给这一格配快照
--------------------
参考库里 26 个技能只有 4 个配了 golden case，而那 4 个全是同一类：
**把源图送进模型**。本项目的对应物就是位置 4 —— 全链路唯一一格会调模型、
也是唯一一格"像素里有一部分不是事实"的地方。

其余六格是纯确定性合成：它们的正确性由 `tools/verify_m3/m5.py` 的**性质断言**
（逐像素同源、贴图区外与生成底一致）覆盖，再给它们配快照只是七倍工作量、
零倍信息。**快照的价值在于"它守着别的东西守不住的那一处"。**

快照守的是什么（性质断言守不住的那些）
------------------------------------
    · 提示词**逐字**没变           —— 改一个词就会换掉场景基调，而所有性质断言照过
    · 取景提示选中同一条           —— "确定性挑选"若退化成随机，性质断言看不出来
    · 几何数字逐值未变（裁切框 / 缩放 / 贴图框）—— 挪 3 像素不会有任何断言红
    · `subject_sha256` 未变        —— 抠图参数一改，七张图的轮廓全变而没人知道
    · `subject_excluded_from_model` 仍是 **null**（没发请求时不许宣称 true）
                                    —— 这条锁的是**口径**：对一次没发生的请求
                                       宣称"我没把主体送出去"是句废话
    · 校验结论未变                 —— 悄悄加严/放宽校验会让"通过"改变含义

为什么用 `--cutout floodfill` 且**清掉 key**
------------------------------------------
    要的是**离线 + 确定性**：floodfill 只取决于输入像素，占位底不联网。
    于是这个快照在任何机器上、任何网络下都能复跑出同一份数字 ——
    一个"有时会变"的快照比没有快照更坏，因为人会习惯它的红。

用法：
    python evals/run_golden.py            # 复跑并比对；有差异退出码 1
    python evals/run_golden.py --update   # 重新记录（会明说哪些值变了）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS = Path(__file__).resolve().parent
GOLDEN = EVALS / "golden" / "slot04.json"

# 每跑一次新开一个时间戳目录，**不删任何旧目录**。
#
# 原来是"固定路径 + 开头 rmtree"。那样有两个问题，第二个是致命的：
#   ① 累积：每轮 5 个文件，越跑越多；
#   ② 本机的批量删除有闸 —— 删**早先轮次留下的内容**、且数量过线时要显式确认，
#      被拦下就 fail-closed 退出 1。于是有一次 rmtree 被拦 → 脚本以非零码结束 →
#      **"清理被拦"冒充成"快照不一致"**。同一个脚本 13:5x 绿、14:14 红，就是它：
#      画面并没有变，是删除被拦了。
# 所以把"每轮跑在空目录上"交给时间戳保证，而不是交给删除保证 ——
# 目录新不新是代码说了算的，删不删是环境说了算的。
TMP_ROOT = EVALS / ".tmp" / "golden"
TMP = TMP_ROOT / time.strftime("%Y%m%d-%H%M%S")

sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402  （控制台编码归一：见 src/console.py）
enable_utf8()

import orchestrator  # noqa: E402  （日志的唯一读法 —— 快照口径照抄产品口径）
import schema        # noqa: E402  （阈值取正本，不从产物里抄）

SLOT = 4
PRODUCT = "examples/product_fullset.json"
ARGS = ["--only", str(SLOT), "--cutout", "floodfill"]

OK, BAD, DIFF = "\u2713", "\u2717", "\u2192"


def _run_once() -> Path:
    """清掉 key 跑一次位置 4。返回 run 目录。"""
    env = dict(os.environ)
    env.pop("DASHSCOPE_API_KEY", None)      # 无 key → 占位底 → 离线、确定性
    # 目录是这一轮新建的，天然是空的 —— 不需要删任何东西。
    TMP.mkdir(parents=True, exist_ok=True)

    argv = [sys.executable, str(ROOT / "run.py"),
            "--product", PRODUCT, "--out", str(TMP), *ARGS]
    p = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8",
                       timeout=900, env=env, errors="replace")
    if p.returncode != 0:
        raise SystemExit(f"跑位置 4 失败（退出码 {p.returncode}）：\n"
                         + "\n".join((p.stdout or p.stderr).splitlines()[-12:]))

    runs = [d for d in TMP.glob("*") if (d / "run.jsonl").exists()]
    if not runs:
        raise SystemExit(f"没找到 run 目录（{TMP}）—— 位置 4 那一格没产出？")
    return max(runs, key=lambda d: d.name)


def _snapshot(run_dir: Path) -> dict:
    """把这次产出里**会被悄悄改掉的那些数**抠出来。"""
    recs = orchestrator.read_records(run_dir, tolerant=True)
    r4 = next(r for r in recs if r.get("stage") == "render"
              and r.get("slot_id") == SLOT)
    det = r4["detail"]
    gen = det["generation"]
    subj = next(r for r in recs if r.get("stage") == "subject")
    valid = next((r for r in recs if r.get("stage") == "validate"
                  and r.get("slot_id") == SLOT), {})
    plan = json.loads((run_dir / "plan.json").read_text(encoding="utf-8"))
    # 计划里的这一格（plan.json 用的是 slot_id —— 它是给执行看的，
    # 而表里用的是 id；两处字段名不同这事不统一，所以这里各取所需的来源：
    # 行为来自计划、阈值来自表 —— 表是阈值的唯一正本。
    pslot = next(s for s in plan["slots"] if s.get("slot_id") == SLOT)
    tbl = next(s for s in schema.assert_valid()["slots"] if s["id"] == SLOT)

    return {
        "renderer": r4.get("renderer"),
        "renderer_in_plan": pslot.get("renderer"),
        "text": pslot.get("text"),
        "text_in_table": tbl.get("text"),
        "product_fill_pct": tbl.get("product_fill_pct"),
        "model_calls_planned": plan.get("model_calls"),
        "placeholder": det.get("placeholder"),
        "generation_mode": gen.get("mode"),
        "hint": gen.get("hint"),
        "prompt": gen.get("prompt"),
        "negative_prompt": gen.get("negative_prompt"),
        "negative_prompt_len": gen.get("negative_prompt_len"),
        "cover_scale": gen.get("cover_scale"),
        "cover_scaled": gen.get("cover_scaled"),
        "cover_crop": gen.get("cover_crop"),
        "paste_box": det.get("paste_box"),
        "subject_sha256": det.get("subject_sha256"),
        "subject_sha256_run": subj.get("sha256"),
        "request_image_fields": (det.get("subject_exclusion_basis") or {}
                                 ).get("request_image_fields"),
        "subject_excluded_from_model": det.get("subject_excluded_from_model"),
        "image_inputs_in_signature": (det.get("subject_exclusion_basis") or {}
                                      ).get("image_inputs_in_signature"),
        "validation_passed": valid.get("passed"),
        "validation_failed": valid.get("failed"),
    }


def _compare(want: dict, got: dict) -> list[str]:
    diffs: list[str] = []
    for k in sorted(set(want) | set(got)):
        a, b = want.get(k, "<缺>"), got.get(k, "<缺>")
        if a != b:
            diffs.append(f"{k}：\n        快照 {a!r}\n        本次 {b!r}")
    return diffs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="位置 4 的冻结快照")
    ap.add_argument("--update", action="store_true",
                    help="重新记录（会明说哪些值变了 —— 别不看就按下去）")
    args = ap.parse_args(argv)

    run_dir = _run_once()
    got = _snapshot(run_dir)

    print("=" * 72)
    print("位置 4 · 冻结快照")
    print("=" * 72)
    print(f"跑在 {run_dir.name}　（无 key + floodfill → 离线、确定性）")

    if not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps({
            "note": ("位置 4 的冻结快照。由 evals/run_golden.py 生成。"
                     "它是**唯一一格**会调模型的坑位 —— 别处用性质断言，"
                     "这里用逐值快照。改了位置 4 的任何东西（提示词 / 取景池 / "
                     "几何 / 抠图参数）都要跑一次它，并**确认变化是有意的**。"),
            "product": PRODUCT, "args": ARGS, "expect": got,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n首次记录 → {GOLDEN.relative_to(ROOT)}")
        return 0

    doc = json.loads(GOLDEN.read_text(encoding="utf-8"))
    want = doc["expect"]
    diffs = _compare(want, got)

    if not diffs:
        print(f"{OK} 全部 {len(want)} 个冻结项一致。")
        print("　 提示词逐字未变、取景提示同一条、几何数字逐值未变、"
              "主体同源、口径仍是 null（没发请求）")
        return 0

    print(f"{BAD} {len(diffs)} 个冻结项变了：\n")
    for d in diffs:
        print(f"   {DIFF} {d}")
    if args.update:
        doc["expect"] = got
        GOLDEN.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        print(f"\n快照已更新 → {GOLDEN.relative_to(ROOT)}")
        print("★ 请确认上面每一条变化都是**有意的**。"
              "拿不准就把这几行 diff 贴进提交说明里 —— 快照的价值全在"
              "「有人看过这次变化」这一件事上。")
        return 0
    print("\n这不是『环境偶发』—— 快照是逐值比对，只有真的变了才会红。")
    print("先看是不是你这次改动动了它；确认有意就 `--update` 重新记录。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
