#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Phase 1 / D1.4 —— 首轮四候选实验：固定参考包 + 固定 PromptVersion + 四个 seed。

本实验要回答的问题只有一个：

    `qwen-image-3.0` 直接参考商品图生成**场景图**时，能不能保住 Aster 01 的外观事实（F1-F8）？

所以它是一个受控实验，不是"多试几次找一张好看的"：

    固定    参考图（1 张，来自冻结参考包的 front-full）；提示词（一个 PromptVersion，逐字固定）；
            尺寸、n、prompt_extend=False、watermark=False、negative_prompt
    变化    只有 seed（四个固定值）—— "四张"衡量的是同一条路线的离散度，不是四次调参

预算：Goal 明文规定首轮四张 + 最多一次受控复验、累计不超过八张。本脚本：
    * 默认只**打印计划**，不提交（--run 才真的花钱）；
    * 提交前先算 `已结算 + 计划 <= 8`，超预算直接拒绝；
    * 受控复验必须显式写出**只改哪一个变量**，改两个以上拒绝。

产物落点由商品包的 `runs.json` 声明（当前指向 `evals/product-demo/first-round/`）：
每个候选一个 attempt 目录（intent / 请求快照 / 原始响应 / 原始 PNG）+ 账本 +
实验 manifest + 联系表。参考包由 `reference_pack.json` 声明，两者都不写商品名。

用法：
    python demo/provider/run_first_round.py --plan-only            # 不花钱
    python demo/provider/run_first_round.py --plan-only --sku <包名>
    python demo/provider/run_first_round.py --run                  # 提交四张（付费）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dashscope_i2i as P                                      # noqa: E402

PROJECT = P.PROJECT

SEEDS = [2026092601, 2026092602, 2026092603, 2026092604]
SIZE = P.DEFAULT_SIZE
BUDGET_TOTAL = 8          # Goal 硬预算：首轮 4 + 一次受控复验 <= 8

# 负向提示词只有一处权威：商品包里的 prompt_profile.json（见 demo/core/packages.py）。
# 这里不再抄一份 —— 抄一份就会出现「实验用的和产品用的不是一个负向提示词」而没人发现。
PROJECT_ROOT = str(P.PROJECT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
import importlib  # noqa: E402

PC = importlib.import_module("demo.core.prompt")
PKG = importlib.import_module("demo.core.packages")


def run_context(sku=None) -> dict:
    """把「这次跑哪个商品、用哪个参考包、产物落哪」在**调用时**解析出来。

    三件事全部由商品包声明（facts 卡 / reference_pack.json / runs.json）：不给 sku
    就取齐套的默认包，给了就解析那个包 —— 模块级不再焊死默认商品。
    「参考包哪一张进模型」也来自声明：第一轮用 primary_view（一张正面全身图就覆盖
    F1/F2/F5/F6 的主要外观）；second_view 是受控复验的候选变量，不是默认路线。
    """
    ref = PKG.refpack_of(PROJECT, sku)
    runs = PKG.runs_of(PROJECT, sku)
    profile = PC.load_profile(project=PROJECT, sku=sku)
    return {"sku": ref["sku"], "card": PKG.path_of(PROJECT, "card", sku),
            "profile": profile, "negative_prompt": profile["negative_prompt"],
            "manifest": ref["manifest"], "declared_in": ref["source"],
            "primary_view": ref["primary_view"], "second_view": ref["second_view"],
            "exp_dir": runs["dir"], "runs_declared_in": runs["source"],
            "store": runs["attempts"], "ledger": runs["ledger"]}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def compile_prompt(card: dict, ctx: dict) -> dict:
    """把事实卡编译成一个 PromptVersion。

    编译逻辑**只有一处**：`demo/core/prompt.py`。本函数只保留实验语义 ——
    固定用正面全身参考图对应的场景与构图，并沿用记录里那句 origin，
    以便与 D1.4 的冻结产物逐字对照。

    委托是否等价，不靠人工比对：跑 `--plan-only` 得到的 prompt_sha256
    必须与 `evals/product-demo/first-round/manifest.json` 里记录的一致。
    """
    facts_version = {
        "facts": [{"id": f["id"]} for f in card["facts"]],
        "card_sha256": P.sha256_file(ctx["card"]),
        "card_version": card.get("version"),
    }
    shot = {"shot_id": "S2-exp", "scene_id": "kitchen-lifestyle",
            "composition_id": "three-quarter-hero",
            "must_preserve": [f["id"] for f in card["facts"]]}
    version = PC.compile_prompt(profile=ctx["profile"], facts_version=facts_version, shot=shot,
                                style={"style_id": "d1.4-fixed", "variables": {}})
    version["origin"] = "D1.4 实验用固定提示词（Phase 3 统一编译器接管前的前身）"
    return version


def reference_set(manifest: dict, ctx: dict) -> dict:
    views = {v["view_id"]: v for v in manifest["views"]}
    primary = ctx["primary_view"]
    if not primary or primary not in views:
        raise SystemExit("商品包声明的 primary_view 不在参考包里：%r" % primary)
    view = views[primary]
    path = PROJECT / view["file"]
    ref = P.load_reference(path)
    if ref.sha256 != view["sha256"]:
        raise SystemExit("参考图与 manifest 记录的哈希不一致：%s" % path)
    return {"manifest_version": manifest["manifest_version"],
            "manifest_sha256": P.sha256_file(ctx["manifest"]),
            "declared_in": ctx["declared_in"],
            "pack_dir": manifest["pack"]["dir"],
            "pack_version": manifest["pack"]["pack_version"],
            "views_used": [{"view_id": view["view_id"], "role": view["role"],
                            "file": view["file"], "sha256": ref.sha256}],
            "references": [path]}


def spent_in_ledger(ledger: P.Ledger) -> int:
    return sum(1 for r in ledger.records() if r.get("chargeable") is True)


def budget_guard(ledger: P.Ledger, planned: int, allow_retest: bool) -> dict:
    charged = spent_in_ledger(ledger)
    if charged + planned > BUDGET_TOTAL:
        raise SystemExit(
            "预算拒绝：已结算 %d 张 + 本次计划 %d 张 > Goal 硬预算 %d 张。"
            "扩大调用数量需要发起人新的授权。" % (charged, planned, BUDGET_TOTAL))
    if planned > len(SEEDS) and not allow_retest:
        raise SystemExit("一次实验最多四张；要做受控复验请显式加 --retest 并写明唯一的变量。")
    return {"charged_before": charged, "planned": planned, "budget_total": BUDGET_TOTAL}


def make_contact_sheet(records: list[dict], out_path: Path) -> dict | None:
    from PIL import Image, ImageDraw
    tiles = []
    for rec in records:
        img_path = rec.get("image_path")
        if img_path and Path(img_path).is_file():
            tiles.append((rec, Image.open(img_path).convert("RGB")))
    if not tiles:
        return None
    cell, pad, label_h = 640, 12, 28
    cols = 2
    rows = (len(tiles) + cols - 1) // cols
    w = cols * cell + (cols + 1) * pad
    h = rows * (cell + label_h) + (rows + 1) * pad
    sheet = Image.new("RGB", (w, h), (245, 245, 245))
    d = ImageDraw.Draw(sheet)
    for i, (rec, img) in enumerate(tiles):
        r, c = divmod(i, cols)
        x = pad + c * (cell + pad)
        y = pad + r * (cell + label_h + pad)
        d.text((x + 2, y + 6), "%s  seed=%s  %s" % (
            rec.get("candidate_id") or rec.get("action_id"), rec.get("seed"),
            (rec.get("status") or "")), fill=(20, 20, 20))
        sheet.paste(img.resize((cell, cell), Image.LANCZOS), (x, y + label_h))
    sheet.save(out_path)
    return {"file": str(out_path.relative_to(PROJECT)).replace("\\", "/"),
            "sha256": P.sha256_file(out_path), "tiles": len(tiles),
            "image_size": [w, h]}


def attempt_records(store: P.AttemptStore, result: dict) -> dict:
    """把一次提交的产物读回来，形成实验级记录（缺什么就写 null，不替它编）。"""
    aid = result["action_id"]
    return {
        "candidate_id": result.get("candidate_id"),
        "action_id": aid,
        "status": result.get("status"),
        "seed": result.get("seed"),
        "size": result.get("size"),
        "prompt_sha256": result.get("prompt_sha256"),
        "request_sha256": result.get("request_sha256"),
        "reference_sha256": result.get("reference_sha256"),
        "task_id": result.get("task_id"),
        "image_path": result.get("image_path"),
        "image_sha256": result.get("image_sha256"),
        "image_bytes": result.get("image_bytes"),
        "input_image_count": result.get("input_image_count"),
        "rewrite_status": result.get("rewrite_status"),
        "usage": result.get("usage"),
        "reason": result.get("reason"),
        "intent_json": str(store.dir_for(aid) / "intent.json") if (store.dir_for(aid) / "intent.json").is_file() else None,
        "request_json": str(store.dir_for(aid) / "request.json") if (store.dir_for(aid) / "request.json").is_file() else None,
        "response_create_json": str(store.dir_for(aid) / "response-create.json") if (store.dir_for(aid) / "response-create.json").is_file() else None,
        "response_task_json": str(store.dir_for(aid) / "response-task.json") if (store.dir_for(aid) / "response-task.json").is_file() else None,
    }


def run(*, do_submit: bool, retest_vary: str | None, poll_timeout_s: int,
        sku: str | None = None) -> int:
    ctx = run_context(sku)
    negative_prompt = ctx["negative_prompt"]
    card = load_json(ctx["card"])
    manifest = load_json(ctx["manifest"])
    prompt = compile_prompt(card, ctx)
    refset = reference_set(manifest, ctx)
    missing = [f for f in ("F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8")
               if f not in prompt["locks_facts"]]
    if missing:
        raise SystemExit("提示词没有锁住这些事实：%s —— 事实没进提示词，就不是受控实验" % missing)
    if len(negative_prompt) > P.NEG_PROMPT_MAX:
        raise SystemExit("negative_prompt 超长（%d > %d）" % (len(negative_prompt), P.NEG_PROMPT_MAX))

    retest = retest_vary is not None
    seeds = SEEDS
    extra: dict = {}
    if retest:
        if retest_vary.count(",") >= 1:
            raise SystemExit("受控复验只能改一个变量，收到：%r" % retest_vary)
        if retest_vary == "seed-set":
            seeds = [2026092611, 2026092612, 2026092613, 2026092614]
            extra["vary"] = "seed 集合（其余全部不变）"
        elif retest_vary == "second-reference":
            second = ctx["second_view"]
            if not second:
                raise SystemExit("商品包没有声明 second_view，无法做这条复验")
            refset["views_used"].append(dict(
                next(v for v in manifest["views"] if v["view_id"] == second)))
            refset["references"].append(PROJECT / next(
                v for v in manifest["views"] if v["view_id"] == second)["file"])
            extra["vary"] = "参考图从 1 张改为 2 张（顺序固定，其余全部不变）"
        elif retest_vary == "prompt-extend":
            extra["vary"] = "prompt_extend=false -> true（其余全部不变）"
        else:
            raise SystemExit("未知的复验变量：%r" % retest_vary)

    exp_dir = ctx["exp_dir"]
    store = P.AttemptStore(ctx["store"])
    ledger = P.Ledger(ctx["ledger"])
    budget = budget_guard(ledger, len(seeds), retest)
    provider = P.Provider(store=store, ledger=ledger)

    planned = {
        "schema": "demo-first-round-plan/1",
        "experiment": "Phase 1 / D1.4 首轮四候选",
        "sku": ctx["sku"],
        "package_declared_in": {"refpack": ctx["declared_in"], "runs": ctx["runs_declared_in"]},
        "prompt_version": prompt,
        "reference_set": {k: v for k, v in refset.items() if k != "references"},
        "reference_files": [str(p) for p in refset["references"]],
        "seeds": seeds,
        "size": SIZE, "n": 1, "prompt_extend": bool(extra.get("prompt_extend")),
        "watermark": False,
        "budget": budget,
        "retest": bool(retest),
    }
    if not do_submit:
        preview = dict(planned, mode="plan-only（未提交、未花钱）")
        exp_dir.mkdir(parents=True, exist_ok=True)
        (exp_dir / "plan.json").write_text(json.dumps(preview, ensure_ascii=False, indent=2),
                                           encoding="utf-8", newline="\n")
        print("商品包 %s（参考包声明 %s）" % (ctx["sku"], ctx["declared_in"]))
        print("计划已写出（未提交）：%s" % (exp_dir / "plan.json"))
        print("提示词 %d 字符 · sha %s…" % (len(prompt["prompt_text"]), prompt["prompt_sha256"][:16]))
        print("参考图 %s" % ", ".join(str(p) for p in refset["references"]))
        print("seeds %s · size %s · prompt_extend=%s" % (seeds, SIZE, planned["prompt_extend"]))
        print("预算：已结算 %d / 计划 %d / 上限 %d" % (budget["charged_before"],
                                                      budget["planned"], budget["budget_total"]))
        return 0

    records = []
    for idx, seed in enumerate(seeds):
        rec = provider.submit(prompt=prompt["prompt_text"], references=refset["references"],
                              seed=seed, size=SIZE, negative_prompt=negative_prompt, n=1,
                              prompt_extend=bool(extra.get("prompt_extend")),
                              allow_prompt_rewrite=bool(extra.get("prompt_extend")),
                              poll_timeout_s=poll_timeout_s)
        rec["candidate_id"] = "%s-%02d" % (("R" if retest else "F"), idx + 1)
        rec["seed"] = seed
        records.append(attempt_records(store, rec))
        print("%s  seed=%s  %s  task=%s  input_image_count=%s  %s" % (
            rec["candidate_id"], seed, rec["status"], str(rec.get("task_id"))[:12],
            rec.get("input_image_count"), rec.get("reason") or ""))

    charged = spent_in_ledger(ledger)
    non_mock = [r for r in records if r.get("input_image_count") == 1]
    experiment = {
        "schema": "demo-first-round-manifest/1",
        "experiment": "Phase 1 / D1.4 首轮四候选",
        "sku": ctx["sku"],
        "ran_at": P.now_iso(),
        "prompt_version": prompt,
        "reference_set": {k: v for k, v in refset.items() if k != "references"},
        "reference_files": [str(p) for p in refset["references"]],
        "seeds": seeds, "size": SIZE, "n": 1,
        "prompt_extend": bool(extra.get("prompt_extend")), "watermark": False,
        "retest": extra or None,
        "budget": dict(budget, charged_after=charged),
        "candidates": records,
        "checks": {
            "billable_calls_this_document": sum(1 for r in records if r.get("status") in
                                                ("SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN")),
            "ledger_rows_chargeable": charged,
            "every_success_carried_reference": len(non_mock) == sum(
                1 for r in records if r.get("status") == "SUCCEEDED"),
            "prompt_extend_false": not bool(extra.get("prompt_extend")),
            "providers_are_real": "usage.input_image_count 来自服务端回执，不是本地声明",
        },
        "does_not_prove": [
            "不证明 F1-F8 通过（那是 D1.5 的人工与机器裁决）",
            "不证明其他商品、其他品类或真实运营提效",
            "不证明多张参考图分支（本轮只用 1 张）",
        ],
    }
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "manifest.json").write_text(json.dumps(experiment, ensure_ascii=False, indent=2),
                                           encoding="utf-8", newline="\n")
    sheet = make_contact_sheet(records, exp_dir / ("contact-sheet-retest.png" if retest
                                                  else "contact-sheet.png"))
    print("\n可结算调用（本实验累计）：%d / 上限 %d" % (charged, BUDGET_TOTAL))
    print("每张成功候选都带参考图：%s" % experiment["checks"]["every_success_carried_reference"])
    print("实验 manifest：%s" % (exp_dir / "manifest.json"))
    if sheet:
        print("联系表：%s" % sheet["file"])
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                              # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="D1.4 首轮四候选实验（默认只打印计划）")
    ap.add_argument("--run", action="store_true", help="真的提交（付费）。不加就只写计划。")
    ap.add_argument("--plan-only", action="store_true", help="只写计划，不提交（默认行为）")
    ap.add_argument("--retest", action="store_true", help="受控复验；必须同时用 --vary 写明唯一变量")
    ap.add_argument("--vary", choices=["seed-set", "second-reference", "prompt-extend"],
                    help="受控复验唯一改变的变量")
    ap.add_argument("--poll-timeout", type=int, default=300)
    ap.add_argument("--sku", default=None,
                    help="商品包名；不给就取齐套的默认包（见 demo/core/packages.py）")
    args = ap.parse_args(argv)
    if args.retest and not args.vary:
        raise SystemExit("--retest 必须同时用 --vary 写明唯一改变的变量")
    if args.vary and not args.retest:
        raise SystemExit("--vary 只在 --retest 下有意义")
    return run(do_submit=bool(args.run and not args.plan_only),
               retest_vary=args.vary if args.retest else None,
               poll_timeout_s=args.poll_timeout, sku=args.sku)


if __name__ == "__main__":
    raise SystemExit(main())
