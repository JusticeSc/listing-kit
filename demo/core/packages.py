# -*- coding: utf-8 -*-
"""商品包解析：逐商品数据的唯一入口（计划 §4.6 硬规矩 1、2）。

规矩：逐商品数据只住 `demo/fixture/<sku>/`，**目录承载身份、文件承载用途**，文件名不带 SKU。
所以这里一个商品名都不写 —— 身份来自目录名与事实卡里的 `sku` 字段，"默认包"是扫描出来的
结果，不是代码常量。

为什么非要有这个模块：在它之前，事实卡、提示词 profile、验证路由计划、两份人工裁决记录
分别写在 `demo/core/front_chain.py`、`demo/core/prompt.py`、`demo/core/back_chain.py`、
`demo/provider/run_first_round.py` 的模块常量里，而且文件名带 SKU 后缀 —— 换商品就得改
`.py`，那正是"通用能力"这条判据要证伪的东西。

约定文件（存在即解析；缺失给明确错误，不猜、不回落到别的包）：
    product.json               事实卡
    threshold-derivation.json  阈值派生记录
    prompt_profile.json        提示词 profile
    verifier_plan.json         事实验证路由计划
    human_fact_review.json     逐条人工事实裁决
    human_visual_review.json   逐条人工视觉裁决
    fact_capability.json       事实验证能力矩阵
    reference_pack.json        这个商品用哪个冻结参考包（指过去，不抄一份）
    runs.json                  这个商品的候选/运行产物落在哪（指过去，不抄一份）

"默认包"的判据写得能被跑红：排序第一的**齐套**包（含 product.json + prompt_profile.json +
verifier_plan.json + reference_pack.json + runs.json）。只按排序取第一个的话，将来加一个
只含事实卡的夹具包，就会悄悄改掉默认商品 —— 那种改动没有任何一处会报警。

本模块同时是"模块常量只能作默认值"（§4.6 硬规矩 1）的落点：产品层任何入口要路径，
都在**调用时**走 path_of / sub_of / refpack_of / runs_of，不在导入时把默认包焊死。
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SUB = "demo/fixture"
CARD_NAME = "product.json"
FILES = {
    "card": CARD_NAME,
    "thresholds": "threshold-derivation.json",
    "prompt_profile": "prompt_profile.json",
    "verifier_plan": "verifier_plan.json",
    "human_facts": "human_fact_review.json",
    "human_visual": "human_visual_review.json",
    "fact_capability": "fact_capability.json",
    "refpack": "reference_pack.json",
    "runs": "runs.json",
}
# 「齐套」= 这条链跑起来所需的**结构性前提**：事实卡、提示词 profile、验证路由计划、
# 参考包声明、候选来源声明。人工裁决记录与能力矩阵按环节现取，缺了就报缺料。
COMPLETE_KEYS = ("card", "prompt_profile", "verifier_plan", "refpack", "runs")


class PackageError(RuntimeError):
    """商品包不存在或不成形。缺料时报缺料，不拿别的包顶上。"""


@dataclass(frozen=True)
class Package:
    project: Path
    sku: str
    root: Path

    def path(self, key: str) -> Path:
        name = FILES.get(key)
        if name is None:
            raise PackageError("未知的商品包文件种类：" + repr(key)
                               + "；已登记 " + "、".join(FILES))
        return self.root / name

    def rel(self, key: str) -> str:
        return self.path(key).relative_to(self.project).as_posix()

    def has(self, key: str) -> bool:
        return self.path(key).exists()

    def require(self, key: str) -> Path:
        p = self.path(key)
        if not p.exists():
            raise PackageError("商品包 " + self.sku + " 缺 " + FILES[key]
                               + "（" + self.rel(key) + "）—— 缺料要报缺料")
        return p

    def load(self, key: str):
        return json.loads(self.require(key).read_text(encoding="utf-8"))

    def presence(self) -> dict:
        return {k: self.has(k) for k in FILES}

    @property
    def card_sku(self) -> str:
        """事实卡自己声明的 sku（与目录名是两件事：目录承载身份，字段承载业务编号）。"""
        return str((self.load("card") or {}).get("sku") or "")

    def as_ref(self) -> dict:
        return {"sku": self.sku, "package": self.root.relative_to(self.project).as_posix(),
                "card": self.rel("card"), "card_sku": self.card_sku,
                "present": self.presence()}


def list_skus(project=ROOT) -> list:
    base = Path(project) / FIXTURE_SUB
    if not base.is_dir():
        return []
    return sorted(p.parent.name for p in base.glob("*/" + CARD_NAME))


def resolve(project=ROOT, sku=None) -> Package:
    """按包路径/商品 id 解析商品包；不给 id 时取齐套的默认包。"""
    project = Path(project).resolve()
    skus = list_skus(project)
    if not skus:
        raise PackageError("在 " + (project / FIXTURE_SUB).as_posix()
                           + " 下找不到商品包（每个包至少要有 " + CARD_NAME + "）")
    if sku is not None:
        if sku not in skus:
            raise PackageError("没有这个商品包：" + repr(sku) + "；现有 " + "、".join(skus))
        return Package(project=project, sku=sku, root=project / FIXTURE_SUB / sku)
    complete = [s for s in skus
                if all((project / FIXTURE_SUB / s / FILES[k]).exists() for k in COMPLETE_KEYS)]
    if not complete:
        raise PackageError(
            "没有齐套的商品包（需要 " + " + ".join(FILES[k] for k in COMPLETE_KEYS)
            + "）；现有 " + "、".join(skus) + "。要么补料，要么用 --sku 显式指定")
    return Package(project=project, sku=complete[0], root=project / FIXTURE_SUB / complete[0])


def default(project=ROOT) -> Package:
    return resolve(project)


# ------------------------------------------------- 调用时取路径（不许导入时焊死）
def path_of(project=ROOT, key="card", sku=None) -> Path:
    """调用时解析商品包再取文件路径。产品层所有入口都走这里。"""
    return resolve(project, sku).path(key)


def sub_of(project=ROOT, key="card", sku=None) -> str:
    """同 path_of，返回相对项目根的字符串 —— 证据里记的 identity 就是这个。"""
    return resolve(project, sku).rel(key)


def refpack_of(project=ROOT, sku=None) -> dict:
    """商品包声明它用哪个冻结参考包：参考包不是产品代码的常识。"""
    pkg = resolve(project, sku)
    doc = pkg.load("refpack")
    if not isinstance(doc, dict):
        raise PackageError("商品包 " + pkg.sku + " 的 " + FILES["refpack"] + " 不是对象")
    base = pkg.project / str(doc.get("pack_dir") or "")
    if not base.is_dir():
        raise PackageError("商品包 " + pkg.sku + " 声明的参考包目录不存在："
                           + repr(doc.get("pack_dir")))
    rel = base.resolve().relative_to(pkg.project.resolve()).as_posix()
    return {"sku": pkg.sku, "source": pkg.rel("refpack"), "pack_dir": rel, "dir": base,
            "manifest": base / str(doc.get("manifest") or "reference-manifest.json"),
            "provenance": base / str(doc.get("provenance") or "pack-provenance.json"),
            "preview": base / str(doc.get("preview") or "preview.html"),
            "primary_view": doc.get("primary_view"),
            "second_view": doc.get("second_view")}


def runs_of(project=ROOT, sku=None) -> dict:
    """商品包声明它的候选/运行产物落在哪：候选来源不是产品代码的常量。

    与 refpack 的区别：运行目录在第一次跑之前还不存在，所以这里只校验声明合法、
    不要求目录已存在；缺失时由调用方按"缺料"报，而不是回落到别的商品。
    """
    pkg = resolve(project, sku)
    doc = pkg.load("runs")
    if not isinstance(doc, dict):
        raise PackageError("商品包 " + pkg.sku + " 的 " + FILES["runs"] + " 不是对象")
    raw = str(doc.get("candidates_dir") or "")
    if not raw:
        raise PackageError("商品包 " + pkg.sku + " 的 " + FILES["runs"] + " 没写 candidates_dir")
    base = pkg.project / raw
    try:
        rel = base.resolve().relative_to(pkg.project.resolve()).as_posix()
    except ValueError:
        raise PackageError("商品包 " + pkg.sku + " 声明的候选目录必须在项目内："
                           + repr(raw)) from None
    return {"sku": pkg.sku, "source": pkg.rel("runs"), "candidates_dir": rel, "dir": base,
            "manifest": base / str(doc.get("manifest") or "manifest.json"),
            "ledger": base / str(doc.get("ledger") or "ledger.jsonl"),
            "attempts": base / str(doc.get("attempts") or "attempts")}


# ------------------------------------------------------------------ 自检
def selftest(project: Path) -> int:
    """包解析器自检：发现、默认、缺料、换包=换数据、以及本文件不含商品名。"""
    import hashlib
    problems = []
    skus = list_skus(project)
    print("商品包自检（不写商品名，只按目录与约定文件解析）")
    if len(skus) < 2:
        print("  [SKIP] T1 发现：只找到 " + str(len(skus)) + " 个包，无法验证「换包=换数据」")
    else:
        print("  [OK  ] T1 发现：找到 " + str(len(skus)) + " 个包：" + "、".join(skus))

    digests = {}
    for sku in skus:
        pkg = resolve(project, sku)
        if pkg.root.name != sku:
            problems.append("T2 解析：resolve(%r) 指到 %s" % (sku, pkg.root))
        if not pkg.has("card"):
            problems.append("T2 解析：" + sku + " 没有事实卡")
            continue
        digests[sku] = hashlib.sha256(pkg.path("card").read_bytes()).hexdigest()[:16]
    if len(set(digests.values())) != len(digests):
        problems.append("T3 换包=换数据：不同的包给出了同一份事实卡 " + repr(digests))
    else:
        print("  [OK  ] T3 换包=换数据：" + "、".join(k + "=" + v for k, v in digests.items()))

    try:
        resolve(project, "__没有这个包__")
        problems.append("T4 缺料：不存在的包竟然解析成功了")
    except PackageError:
        print("  [OK  ] T4 缺料：不存在的包报 PackageError 而不是猜一个")

    dflt = default(project)
    missing = [FILES[k] for k in COMPLETE_KEYS if not dflt.has(k)]
    if missing:
        problems.append("T5 默认包：" + dflt.sku + " 缺 " + "、".join(missing))
    else:
        print("  [OK  ] T5 默认包：" + dflt.sku + " 齐套（" + " + ".join(FILES[k] for k in COMPLETE_KEYS) + "）")

    # T6 自证：本文件里不许出现任何一个已发现的商品名 —— 写死就得改 .py，判据必须能跑红
    own = Path(__file__).read_text(encoding="utf-8")
    hits = [s for s in skus if s in own]
    if hits:
        problems.append("T6 不含商品名：本文件出现 " + "、".join(hits))
    else:
        print("  [OK  ] T6 不含商品名：源码里零命中（token 取自本次扫描结果）")

    # T7 指针可解析：参考包与候选来源都由数据声明，解析器必须在默认包上走通
    try:
        ref = refpack_of(project)
        run = runs_of(project)
        print("  [OK  ] T7 指针：参考包 " + ref["pack_dir"]
              + "；候选来源 " + run["candidates_dir"])
    except PackageError as exc:
        problems.append("T7 指针：" + str(exc))

    print()
    if problems:
        print("自检未通过（" + str(len(problems)) + " 项）：")
        for p in problems:
            print("  - " + p)
        return 1
    print("自检：全部成立")
    return 0


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                   # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="商品包解析器")
    ap.add_argument("mode", nargs="?", default="self-test", choices=["self-test", "show"])
    ap.add_argument("--project", default=".")
    ap.add_argument("--sku", default=None)
    args = ap.parse_args(argv)
    project = Path(args.project).resolve()
    if args.mode == "show":
        print(json.dumps(resolve(project, args.sku).as_ref(), ensure_ascii=False, indent=2))
        return 0
    return selftest(project)


if __name__ == "__main__":
    raise SystemExit(main())
