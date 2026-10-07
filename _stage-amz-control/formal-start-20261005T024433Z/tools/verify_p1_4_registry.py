#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""P1.4 验收：20-SKU 试点登记（判据会不会红 + 现在够不够）。

判据来自计划 Phase 1 任务卡 P1.4 那一行：
    校验器证明总数 20、至少 2 品类、每品类 ≥5、2 名操作员各预分配 ≥5；
    缺事实/授权/素材只可标 not-ready；清单不齐时 G1 不通过；
    不得用样例 SKU 补足真实样本数。

十条：
    A 基线（真文件）   登记表结构合法但没有样本 → 门报"还没齐"，且**不是**因为文件坏了
    B 样例不计数       19 真实 + 1 样例 → 仍然是 19/20（拿样例凑数这条路走不通）
    C 满编正向对照     合法满编的 20 条 → 齐；品类/操作员/批次三个分布都对
    D 品类            只有 1 个品类 → 不齐；某一类只有 4 个 → 点名那一类
    E 操作员          只有 1 名 → 不齐；第二名只分到 4 个 → 点名那个人
    F 缺料不算数       20 条里有 2 条缺事实 → 那 2 条 not-ready，且**不参与**品类/操作员配额
    G 结构拒绝         身份没匿名 / 素材没哈希 / 绝对路径 / order 跳号 / 批次打架 → 写错了（不是"还没做到"）
    H 门禁入口本身     退出码 1（没齐）与 2（写错了）各证明一次
    I 现场核对         版本与素材要**真的在**：编一个格式合法的版本号凑够 20 条，以前能变绿，
                       现在一条都不算。三种结果分开：在 / 还没放（退 1）/ 对不上（退 2）。
    J 补齐工具         人只写四列（order/id/category/operator），机器补三列
                       （facts_version / data_policy_version / assets）；缺料留空不编；
                       登记表落后于素材时 --check 退 2。反向：手改一位哈希必须被抓住。

退出码：0 全过 / 1 有条目不过。
"""
from __future__ import annotations

import copy
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402
enable_utf8()
import pilot_registry as pr  # noqa: E402
import data_policy  # noqa: E402

REPORT = ROOT / "evals" / "product-v1" / "p1" / "p1.4-registry.txt"
GATE = ROOT / "tools" / "check_pilot_ready.py"
TMP = ROOT / "evals" / ".tmp" / "p1.4"
# 只用形态合法的**占位**值：FACTS/POLICY 这两个位置以前抄的是真实版本号（会随输入漂），
# 现在凡是"要核对版本号"的段落一律现场算（见 I 段），结构类段落用占位值就够。
FAKE_FACTS = "pfv1-" + "0" * 12
FAKE_POLICY = "dpv1-" + "0" * 12
SHA = "a" * 64
CAT_A = "home_kitchen"
CAT_B = "kitchen_tools"


def asset(order: int, kind: str = "front") -> dict:
    return {"kind": kind, "path": f"materials/SKU-{order:02d}/{kind}.jpg", "sha256": SHA}


def entry(order: int, *, category=CAT_A, operator="OP-A", batch=None,
          facts=FAKE_FACTS, policy=FAKE_POLICY, assets=True, sample=None, extra=None) -> dict:
    e = {"order": order, "id": f"SKU-{order:02d}", "category": category,
         "batch": batch or ("calibration" if order in pr.CALIBRATION_ORDERS else "official"),
         "operator": operator, "facts_version": facts, "data_policy_version": policy,
         "assets": [asset(order)] if assets else []}
    if sample is not None:
        e["sample"] = sample
    if extra:
        e.update(extra)
    return e


def registry(entries, operators=(("OP-A", 10), ("OP-B", 10)), **top) -> dict:
    reg = {"schema": pr.SCHEMA, "updated_at": "2026-09-23",
           "operators": [{"id": o, "tasks_target": t} for o, t in operators],
           "entries": entries}
    reg.update(top)
    return reg


def full_20() -> list[dict]:
    """合法满编：10 + 10 两个品类、两名操作员各 10、前 5 条是校准集。"""
    out = []
    for o in range(1, 21):
        out.append(entry(o, category=CAT_A if o <= 10 else CAT_B,
                         operator="OP-A" if o % 2 else "OP-B"))
    return out


def write(name: str, reg: dict) -> Path:
    import yaml
    TMP.mkdir(parents=True, exist_ok=True)
    p = TMP / name
    p.write_text(yaml.safe_dump(reg, allow_unicode=True, sort_keys=False),
                 encoding="utf-8", newline="")
    return p


def yaml_load(p: Path) -> dict:
    import yaml
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def sha_of(p: Path) -> str:
    import hashlib
    return hashlib.sha256(p.read_bytes()).hexdigest()


def expected_facts(root: Path, sid: str) -> str:
    """**独立算一遍**：不走 `pilot_registry` 的内部路径，直接用 ProductFacts 算。

    这样"核对器说 ok"与"这份输入真的算得出这个版本"是两个互相独立的判断 ——
    否则就是拿实现证实现，等于没证。
    """
    import product_facts
    ref = f"materials/{sid}/product.json"
    fw, fi = product_facts.load_forbidden(root / "config" / "brand.json")
    return product_facts.facts_from_product(
        product_facts.load_product(root / ref), source_path=ref,
        forbidden_words=fw, forbidden_on_image=fi)["facts_version"]


def main() -> int:
    lines: list[str] = []
    fails: list[str] = []

    def emit(s: str = "") -> None:
        print(s)
        lines.append(s)

    def check(ok: bool, label: str, detail: str = "") -> None:
        emit(f"  [{'OK  ' if ok else 'FAIL'}] {label}" + (f"　{detail}" if detail else ""))
        if not ok:
            fails.append(label)

    def expect_reject(reg: dict, name: str, must_contain: str, label: str) -> None:
        p = write(name, reg)
        try:
            pr.load_registry(p)
        except pr.RegistryError as exc:
            hit = must_contain in str(exc)
            check(hit, label, f"报错含『{must_contain}』" if hit else
                  f"报错了但没提『{must_contain}』：{str(exc).splitlines()[0]}")
        except Exception as exc:                                   # noqa: BLE001
            check(False, label, f"抛的不是 RegistryError 而是 {type(exc).__name__}: {exc}")
        else:
            check(False, label, "居然通过了 —— 这一条本该被拦下")

    def gate(path: Path | None, root: Path | None = None) -> int:
        args = [sys.executable, str(GATE)]
        if path:
            args += ["--path", str(path)]
        if root:
            args += ["--root", str(root)]
        return subprocess.run(args, cwd=str(ROOT), capture_output=True,
                              text=True, encoding="utf-8", errors="replace").returncode

    emit("P1.4 验收：20-SKU 试点登记")
    emit("=" * 72)
    emit("本次切片的七项声明（计划 §7.1）：")
    emit("  用户可见行为  无（这一层还不接界面；只把『用哪些样本证明』变成可校验的登记与门）")
    emit("  不变量        A 主体只有一份 / B 生成层看不见主体 / C 文字层不画字 / D 位置 1 零模型 全部未触碰")
    emit("  允许改的模块  pilot/pilot-registry.yaml、src/pilot_registry.py、tools/check_pilot_ready.py、tools/fill_pilot_registry.py 新增；examples/ 只读")
    emit("  新增身份      条目 id=SKU-NN（匿名）+ order（执行顺序即批次依据）；原图只留相对路径与 sha256")
    emit("  拒绝路径      样例不计数 / 缺料自算 not-ready 且不占配额 / 身份未匿名、素材无哈希、批次与顺序打架 → 报错")
    emit("                编造的版本号、对不上的素材哈希 → 不算 ready；空表不许算绿")
    emit("  判据          本文件 A–I；反向样本见 B/D/E/G/I；正向对照见 C/I")
    emit("  迁移与回退    纯加法：v2 与 ProductFacts/DataPolicy/ReviewChecklist 均未改；登记表当前为空，门如实报红")
    emit("")

    # ---------------------------------------------------------------- A
    emit("A 基线（真文件：结构合法，但样本还没齐）")
    real = pr.load_registry()
    res_real = pr.resolve(real)
    s_real = pr.summarize(real, resolution=res_real)
    check(True, "登记表结构合法（不合法会直接抛 RegistryError）",
          f"条目 {s_real['total_entries']} 条 · 操作员 {len(real.get('operators') or [])} 名")
    check(s_real["ready"] is False and s_real["real"] == 0,
          "门报「还没齐」", f"真实 {s_real['real']}/{s_real['targets']['total']}")
    check(any("真实 SKU 0/20" in x for x in s_real["problems"]),
          "红的原因是样本数，不是文件写错了")
    check(res_real["any_input"] == 0 and res_real["counts"][pr.STATUS_OK] == 0,
          "现场核对：真的核到输入的条目 0 条（没有东西可核）",
          f"counts={res_real['counts']} · any_input={res_real['any_input']}")
    check(res_real["policy_signed"] is False,
          "并如实报出 allowlist 还没签署（signed_by 为空）",
          f"policy_version={res_real['policy_version']}")
    emit("")

    # ---------------------------------------------------------------- B
    emit("B 样例不计数（拿样例凑数这条路必须走不通）")
    padded = [entry(o) for o in range(1, 20)] + [entry(20, sample=True)]
    s_b = pr.summarize(pr.load_registry(write("b-padded.yaml", registry(padded))))
    check(s_b["real"] == 19 and s_b["sample"] == 1 and s_b["ready"] is False,
          "19 条真实 + 1 条样例 → 仍然按 19 算", f"real={s_b['real']} sample={s_b['sample']}")
    check(any("样例不计数" in x for x in s_b["problems"]),
          "并且明说了样例不计数", f"{s_b['problems'][0]}")
    all_samples = pr.summarize(pr.load_registry(
        write("b-all-samples.yaml", registry([entry(o, sample=True) for o in range(1, 21)]))))
    check(all_samples["real"] == 0, "整表都标样例 → 真实 0 条（一条都不算）")
    emit("")

    # ---------------------------------------------------------------- C
    emit("C 满编正向对照（判据不是一直红）")
    s_c = pr.summarize(pr.load_registry(write("c-full.yaml", registry(full_20()))))
    check(s_c["ready"] is True and s_c["ready_count"] == 20,
          "合法满编的 20 条 → 齐", f"problems={s_c['problems']}")
    check(s_c["by_category"] == {CAT_A: 10, CAT_B: 10}
          and s_c["by_operator"] == {"OP-A": 10, "OP-B": 10}
          and s_c["by_batch"] == {"calibration": 5, "official": 15},
          "品类 / 操作员 / 批次三个分布都对",
          f"{s_c['by_category']} · {s_c['by_operator']} · {s_c['by_batch']}")
    emit("")

    # ---------------------------------------------------------------- D
    emit("D 品类覆盖")
    one_cat = pr.summarize(pr.load_registry(
        write("d-one-cat.yaml", registry([entry(o) for o in range(1, 21)]))))
    check(any("品类 1 个" in x for x in one_cat["problems"]),
          "只有 1 个品类 → 不齐", f"{[x for x in one_cat['problems'] if '品类' in x]}")
    skewed = [entry(o, category=CAT_A if o <= 16 else CAT_B) for o in range(1, 21)]
    s_d = pr.summarize(pr.load_registry(write("d-skewed.yaml", registry(skewed))))
    check(any(f"品类 {CAT_B} 只有 4 个" in x for x in s_d["problems"]),
          "某一类只有 4 个 → 点名那一类", f"{[x for x in s_d['problems'] if CAT_B in x]}")
    emit("")

    # ---------------------------------------------------------------- E
    emit("E 双操作员")
    solo = pr.summarize(pr.load_registry(write(
        "e-solo.yaml", registry([entry(o) for o in range(1, 21)],
                                operators=(("OP-A", 20),)))))
    check(any("操作员 1 名" in x for x in solo["problems"]),
          "只声明 1 名操作员 → 不齐", f"{[x for x in solo['problems'] if '操作员' in x]}")
    lopsided = [entry(o, category=CAT_A if o <= 10 else CAT_B,
                      operator="OP-A" if o <= 16 else "OP-B") for o in range(1, 21)]
    s_e = pr.summarize(pr.load_registry(write("e-lopsided.yaml", registry(lopsided))))
    check(any("操作员 OP-B 只分到 4 个" in x for x in s_e["problems"]),
          "第二名只分到 4 个 → 点名那个人", f"{[x for x in s_e['problems'] if 'OP-B' in x]}")
    emit("")

    # ---------------------------------------------------------------- F
    emit("F 缺料条目不占配额")
    partial = full_20()
    partial[2] = entry(3, facts=None, extra={"notes": "事实还没确认"})
    partial[13] = entry(14, policy=None, extra={"notes": "授权还没签"})
    s_f = pr.summarize(pr.load_registry(write("f-partial.yaml", registry(partial))))
    check(s_f["ready_count"] == 18 and len(s_f["not_ready"]) == 2,
          "20 条里有 2 条缺料 → ready 只有 18 条",
          f"not_ready={s_f['not_ready']}")
    check("缺事实版本（P1.1）" in s_f["not_ready"]["SKU-03"]
          and "缺授权版本（P1.2）" in s_f["not_ready"]["SKU-14"],
          "缺什么写清楚（哪一项、归哪个切片）")
    check(sum(s_f["by_category"].values()) == 18
          and sum(s_f["by_operator"].values()) == 18,
          "缺料的条目**不参与**品类与操作员配额（不是『先算上、回头补』）")
    check(any("按 not-ready 处理" in x for x in s_f["problems"]),
          "门同时报出有几条缺料")
    emit("")

    # ---------------------------------------------------------------- G
    emit("G 结构拒绝（这些是「写错了」，与「还没做到」分开）")
    expect_reject(registry([entry(1, extra={"upc": "B0FULLSET01"})] + [entry(o) for o in range(2, 21)]),
                  "g1-upc.yaml", "商品身份", "条目里写了 UPC → 报错（不是匿名登记）")
    expect_reject(registry([entry(1, extra={"id": "B0FULLSET01"})] + [entry(o) for o in range(2, 21)]),
                  "g2-real-id.yaml", "匿名编号", "id 用真实 UPC → 报错")
    expect_reject(registry([entry(1, extra={"assets": [asset(1, kind="hero")]})]
                           + [entry(o) for o in range(2, 21)]),
                  "g3-bad-kind.yaml", "IMAGE_KINDS", "素材 kind 不在 src/assets.py 的闭集里 → 报错")
    expect_reject(registry([entry(1, extra={"assets": [{"kind": "front", "path": "materials/SKU-01/front.jpg", "sha256": "abc"}]})]
                           + [entry(o) for o in range(2, 21)]),
                  "g4-bad-sha.yaml", "sha256", "素材哈希不是 64 位 → 报错")
    expect_reject(registry([entry(1, extra={"assets": [{"kind": "front", "path": "E:/materials/front.jpg", "sha256": SHA}]})]
                           + [entry(o) for o in range(2, 21)]),
                  "g5-abs-path.yaml", "绝对路径", "素材写成绝对路径 → 报错（只留受控目录相对路径）")
    expect_reject(registry([entry(o) for o in range(1, 20)] + [entry(21)]),
                  "g6-order-gap.yaml", "连续", "order 跳号 → 报错（第几个做的说不清）")
    expect_reject(registry([entry(6, batch="calibration")] + [entry(o) for o in range(1, 21) if o != 6]),
                  "g7-batch.yaml", "打架", "order 属于正式批却标成校准集 → 报错")
    emit("")

    # ---------------------------------------------------------------- H
    emit("H 门禁入口本身的退出码（1 与 2）")
    check(gate(None) == 1, "真文件（0/20）→ 退出码 1：没齐", "红是实话")
    check(gate(write("h-broken.yaml", registry([entry(1, extra={"upc": "X"})]))) == 2,
          "写错的临时表 → 退出码 2：与「没齐」分开报", "人看到 2 才知道要改的是文件")
    emit("  说明：『齐了 → 0』与『对不上 → 2』放到 I 段证明 —— 那两件事要求素材真的在，")
    emit("        光有一张临时表是证明不了的（这正是 I 段要堵的那个空子）。")
    emit("")

    # ---------------------------------------------------------------- I
    emit("I 现场核对：版本与素材要真的在（堵『编个合法版本号就能凑够 20』）")
    root = TMP / "i-root"
    shutil.rmtree(root, ignore_errors=True)
    (root / "contracts").mkdir(parents=True, exist_ok=True)
    (root / "config").mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "contracts" / "data-policy-v1.yaml",
                 root / "contracts" / "data-policy-v1.yaml")
    shutil.copy2(ROOT / "config" / "brand.json", root / "config" / "brand.json")
    for o in range(1, 21):
        d = root / "materials" / f"SKU-{o:02d}"
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "examples" / "product_fullset.json", d / "product.json")
        shutil.copy2(ROOT / "examples" / "input" / "competitor.jpg", d / "front.jpg")
    live_policy = data_policy.load_policy(
        root / "contracts" / "data-policy-v1.yaml").policy_version

    def real_entry(order: int) -> dict:
        sid = f"SKU-{order:02d}"
        e = entry(order, category=CAT_A if order <= 10 else CAT_B,
                  operator="OP-A" if order % 2 else "OP-B")
        e["data_policy_version"] = live_policy
        e["facts_version"] = expected_facts(root, sid)
        e["assets"] = [{"kind": "front", "path": f"materials/{sid}/front.jpg",
                        "sha256": sha_of(root / "materials" / sid / "front.jpg")}]
        return e

    good = registry([real_entry(o) for o in range(1, 21)])
    gp = write("i-good.yaml", good)
    res_good = pr.resolve(good, root=root)
    check(res_good["counts"][pr.STATUS_OK] == 20 and res_good["any_input"] == 20,
          "材料与版本都对得上 → 20 条全 ok",
          f"{res_good['counts']} · any_input={res_good['any_input']}")
    check(pr.summarize(good, resolution=res_good)["ready"] is True,
          "核对过之后才算 ready（正向对照）")
    check(gate(gp, root=root) == 0, "门对核对过的满编退 0：齐了、而且是核过的")

    (root / "materials" / "SKU-13" / "front.jpg").unlink()
    res_gone = pr.resolve(good, root=root)
    r13 = res_gone["entries"]["SKU-13"]
    check(r13["status"] == pr.STATUS_PENDING and res_gone["counts"][pr.STATUS_PENDING] == 1,
          "素材文件不在 → pending_input（还没放）", f"{r13['reasons']}")
    check(pr.summarize(good, resolution=res_gone)["ready"] is False,
          "还没放的条目不算 ready，也不占配额")
    check(gate(gp, root=root) == 1, "门对『素材还没放』退 1：红是实话")

    shutil.copy2(ROOT / "examples" / "input" / "cup_source.jpg",
                 root / "materials" / "SKU-13" / "front.jpg")
    res_swap = pr.resolve(good, root=root)
    r13b = res_swap["entries"]["SKU-13"]
    check(r13b["status"] == pr.STATUS_MISMATCH
          and res_swap["counts"][pr.STATUS_MISMATCH] == 1,
          "素材被换成另一张 → mismatch（对不上）")
    check(any("哈希与登记不符" in m for m in r13b["mismatch"]),
          "说清楚是哈希对不上，不是笼统的『失败』", f"{r13b['mismatch']}")
    check(gate(gp, root=root) == 2, "门对『对不上』退 2：与『还没做到』分开")
    shutil.copy2(ROOT / "examples" / "input" / "competitor.jpg",
                 root / "materials" / "SKU-13" / "front.jpg")          # 复原

    badver = copy.deepcopy(good)
    badver["entries"][6]["facts_version"] = "pfv1-" + "1" * 12
    rv = pr.resolve(badver, root=root)["entries"]["SKU-07"]
    check(rv["status"] == pr.STATUS_MISMATCH,
          "facts_version 写了一个格式合法但算不出来的值 → mismatch", f"{rv['mismatch']}")
    check(any("materials/SKU-07/product.json 算出来的" in m for m in rv["mismatch"]),
          "并且点名是哪一份输入算出来的版本对不上")
    badpol = copy.deepcopy(good)
    badpol["entries"][0]["data_policy_version"] = "dpv1-" + "1" * 12
    rp = pr.resolve(badpol, root=root)["entries"]["SKU-01"]
    check(rp["status"] == pr.STATUS_MISMATCH
          and any("批的不是这一版" in m for m in rp["mismatch"]),
          "data_policy_version 与活的那份政策对不上 → mismatch（批的不是这一版）")

    fake = registry(full_20())
    res_fake = pr.resolve(fake, root=root)
    check(res_fake["counts"][pr.STATUS_OK] == 0,
          "20 条形态合法的假登记（版本是编的）→ ok 一条都没有",
          f"{res_fake['counts']}")
    check(pr.summarize(fake, resolution=res_fake)["ready"] is False,
          "所以『编个合法版本号就能凑够 20』这条路走不通")
    res_empty = pr.resolve(pr.load_registry())
    check(res_empty["any_input"] == 0,
          "真实空表：真的核到输入的条目 0 条", "空表不算绿")
    check(any("空表不算绿" in x for x in
              pr.summarize(pr.load_registry(), resolution=res_empty)["problems"]),
          "并把『一条输入都没有』写成待补项，而不是没报错就算过")
    emit("")

    # ---------------------------------------------------------------- J
    emit("J 补齐工具：机器能算的列不用人写")
    import yaml                                                            # noqa: F401
    FILL = ROOT / "tools" / "fill_pilot_registry.py"
    HEAD = "# 这是给人看的说明，重写后必须原样还在\n# 第二行说明\n"

    def fill(path: Path, *, check: bool = False) -> int:
        args = [sys.executable, str(FILL), "--path", str(path), "--root", str(root)]
        if check:
            args.append("--check")
        return subprocess.run(args, cwd=str(ROOT), capture_output=True,
                              text=True, encoding="utf-8", errors="replace").returncode

    # 人写的只有四列：order / id / category / operator（batch 也是推出来的）
    def skeleton_file(name: str, *, with_header: bool = False) -> Path:
        import yaml
        skel = registry([{"order": o, "id": f"SKU-{o:02d}",
                          "category": CAT_A if o <= 10 else CAT_B,
                          "operator": "OP-A" if o % 2 else "OP-B"}
                         for o in range(1, 21)],
                        operators=(("OP-A", 10), ("OP-B", 10)))
        body = yaml.safe_dump(skel, allow_unicode=True, sort_keys=False)
        TMP.mkdir(parents=True, exist_ok=True)
        p = TMP / name
        p.write_text((HEAD + "\n" if with_header else "") + body,
                     encoding="utf-8", newline="")
        return p

    sp = skeleton_file("j-skeleton.yaml", with_header=True)
    rc = fill(sp)
    filled = yaml_load(sp)
    res_filled = pr.resolve(filled, root=root)
    check(rc == 0 and res_filled["counts"][pr.STATUS_OK] == 20,
          "只写四列的骨架 → 补齐后 20 条全 ok", f"rc={rc} · {res_filled['counts']}")
    batches = {e["id"]: e.get("batch") for e in filled["entries"]}
    check(batches["SKU-05"] == "calibration" and batches["SKU-06"] == "official",
          "batch 是推出来的，不用人写", f"SKU-05={batches['SKU-05']} SKU-06={batches['SKU-06']}")
    check(sp.read_text(encoding="utf-8").startswith(HEAD),
          "头部注释原样保留（重写只动正文）")
    check(fill(sp, check=True) == 0, "补齐后 --check 立刻一致（幂等）")

    (root / "materials" / "SKU-13" / "front.jpg").unlink()
    mp = skeleton_file("j-missing.yaml")
    rc_m = fill(mp)
    e13 = next(e for e in yaml_load(mp)["entries"] if e["id"] == "SKU-13")
    check(rc_m == 1 and e13["assets"] == [] and e13.get("facts_version"),
          "素材缺一张 → 该条 assets 留空、退 1（还没到位，不是写错）",
          f"rc={rc_m} · assets={e13['assets']}")
    check(fill(mp, check=True) == 1, "--check 对『素材还没到位』退 1")
    shutil.copy2(ROOT / "examples" / "input" / "competitor.jpg",
                 root / "materials" / "SKU-13" / "front.jpg")

    check(fill(mp, check=True) == 2,
          "素材补回来了但没重跑工具 → --check 退 2（不一致，跑一次本工具即可）")

    tp = skeleton_file("j-tamper.yaml")
    assert fill(tp) == 0, "先补齐一份好的，再故意改坏一位"
    tdoc = yaml_load(tp)
    tdoc["entries"][6]["facts_version"] = "pfv1-" + "1" * 12
    tp.write_text(yaml.safe_dump(tdoc, allow_unicode=True, sort_keys=False),
                  encoding="utf-8", newline="")
    check(fill(tp, check=True) == 2, "手改一位版本号 → --check 退 2")
    check(gate(tp, root=root) == 2, "同一份手改过的登记表 → 门也退 2（对不上）")
    emit("")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    emit("=" * 72)
    if fails:
        emit(f"结论：{len(fails)} 条不过 —— {'；'.join(fails)}")
    else:
        emit("结论：全部通过")
    emit("")
    emit(f"当前真实登记：真实 SKU {s_real['real']}/{s_real['targets']['total']} —— "
         f"门报红，原因是没有真实样本，不是判据或文件的问题。")
    emit("边界：本报告证明这套判据会红也会绿、样例凑不了数、缺料不占配额、")
    emit("      编造的版本号凑不够 20、素材被换或版本对不上会退 2、")
    emit("      补齐工具只补机器那三列且缺料留空（不会替人编）；")
    emit("      不证明那 20 个真实 SKU 存在，也不证明任何一条已经真的跑过。")
    emit("")
    emit(f"报告：{REPORT}")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="")
    shutil.rmtree(TMP, ignore_errors=True)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
