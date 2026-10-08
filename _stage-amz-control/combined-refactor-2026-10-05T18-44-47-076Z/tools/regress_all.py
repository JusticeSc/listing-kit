"""五级验收回归：一条命令回答「这次改动有没有打破既有全绿」。

为什么需要这个入口
------------------
`verify_m3..m5` 读取产物，`verify_m6` 会真实追加一次重做版本，`verify_m7` 自带沙箱。
因此默认回归不能把 M6 直接指向 out/ 下的冻结 run；否则“验证”本身会改写基线。
于是只要上一轮产物还在，它们**不产图也能全绿**；可很多改动改的正是产图那条路。
「全绿」若不含「从零真跑一次」，验的可能就是旧代码产的那批图。

三条纪律（每一条都是踩出来的，不是好习惯）

1. **`--fresh` 才代表从零。** 它先把 out/ 下现有产物重命名挪到 out_prev/（不删，可回退），
   再 `--dry-run` 报出这次要花多少（张数 / 模型调用次数，位置 4 是唯一花钱的格），
   然后真跑一遍全链路，最后**断言**验收读到的确实是这一轮
   （`orchestrator.latest_run` 按目录名排序，新 run 必然排最后；断言失败即报错，
   不靠"应该是吧"）。

2. **绝不并发。** 单次抠图实测约需 6 GB 物理 / 9 GB 可提交内存（本机 14 GB）。
   两个各揣抠图会话的进程同时跑，后启动的那个会在 ORT 里报 `bad allocation`，
   表现成 `MemoryError: Unable to allocate 1.76 MiB` 这种**看起来偶发、其实必然**的失败
   —— 而它恰恰是自己制造的。所以本脚本起跑前先量内存余量，不够就**拒跑**（退出码 8），
   而不是发一句警告然后照跑（警告会被忽略，这已经被验证过了）。

3. **结论边跑边落盘。** 一个跑 3 分钟的脚本被中断时，只把结果攒在内存里 = 结论全丢
   （本脚本的前身就丢过一次：`out/` 里产物齐全，却一个字的结果都没留下）。
   每跑完一项立刻整份重写报告文件。

4. **环境拦下的要单列成第三类，不许混进「未通过」。** 目前有两类环境条件（见 `ENV_SIGS`）：
   ① 本机的批量删除闸（删早先轮次留下的内容 / 本轮累计过线要确认）—— 验收脚本的收尾清理
   会撞它，**产品代码自己写文件也会撞它**；② 抠图因内存不足连续失败，导致本批比齐套可做的
   少（`verify_m5` 走退出码 7）。两者都与被验的代码无关，但**下一动作完全不同**
   （一类等下一轮额度重置，一类要腾内存重跑）—— 所以报告里**按签名分组**，不合成一句。
   混进「未通过」的后果很具体：人看到一屏红会以为改动坏了，然后去改没坏的东西。

   ★ 但**"归到第三类"本身也必须能被证伪**：每条签名还要写清**只有哪个步骤才能算**
   （`applies_to`）。否则任何转述别的步骤输出的脚本（例如会打印 M5 输出尾部的对照探针）
   都会把别人的签名算到自己头上 —— 一个**真失败**就这样被洗成"被环境拦下"，
   连"未通过"都进不去。这不是报错，是**红被吃掉了**，比报错更坏。

用法
----
    python tools/regress_all.py              # 用现有 out/ 跑验收（快，不产图）
    python tools/regress_all.py --fresh      # 从零：dry-run 报价 → 真跑 → 验收
    python tools/regress_all.py --verbose    # 把每项的输出也打出来
    python tools/regress_all.py --force      # 内存不够也继续（不建议）

退出码
    0  全绿
    1  有项目未通过（报告里逐项列出）
    3  没有未通过，但有步骤命中了环境条件（批量删除闸 / 抠图内存降级；
       报告里按签名分组，各带下一动作。这两类下一轮都不一定复现，不算缺陷）
    8  内存余量不足，拒跑 —— 防的正是「两个进程互挤」。拒跑**只写**
       `evals/last_regress_refused.txt`，不碰上一轮的真报告 `evals/last_regress.txt`
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# 与 run.py / verify_m*.py 同一处接缝：src/ 自己的模块用的是扁平导入
# （`import assets`），所以 src/ 必须在 sys.path 上 —— 不是 `from src import ...`。
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402  （控制台编码归一：见 src/console.py）
enable_utf8()
PY = sys.executable

REPORT = ROOT / "evals" / "last_regress.txt"
# 拒跑记录**另立文件**：拒跑不是一次回归结果，不许顶替上一轮的真结论。
# 2026-09-25 登记的反例：内存不足时跑一次回归，会把 D-1.3 / G-1 的证据
# `last_regress.txt`（21 通过 / 0 未通过）覆盖成一句「拒跑」——
# 而任务证据还在、守卫还全绿。那是**静默替换证据**，比报错更坏。
REFUSED_REPORT = ROOT / "evals" / "last_regress_refused.txt"
TMP = ROOT / "evals" / ".tmp"
PRODUCT = "examples/product_fullset.json"

# 单次抠图的实测成本（1024² 输入；抠图前 availPhys 6851 MB / availCommit 17849 MB
# → 抠完 889 MB / 8553 MB）。下面两个常数是**量出来的**，不是估的。
CUTOUT_PHYS_MB = 6000
CUTOUT_COMMIT_MB = 9000
# 起跑门槛。留余量给解释器 / PIL / numpy 自己。
GATE_PHYS_MB = 5000
GATE_COMMIT_MB = 9000

# ── 环境条件的**机器可读签名**表：命中任一即归为「被环境拦下」，不并入「未通过」 ──
# 两条的成因完全不同，用同一句解释会把人指向错的动作 —— 所以每条自带话术。
# 签名必须是**不随措辞变化的稳定子串**（英文常量名 / 大写标记），中文解释随便改：
# 归类靠字符串匹配，让标记跟着文案走，等于把判据挂在会变的东西上。
#
# ★ 第三条（2026-09-22 补，而且是被自己的误判逼出来的）：**每条签名必须写清"只有哪个
#   步骤才能算"**。原来只要输出里出现签名就算，于是「跳过成因对照」失败时打印了 M5 的
#   输出尾部（里面带着 `M5-DEGRADE:`）→ 一个**真失败**被判成"被环境拦下"、直接消失在
#   「未通过」之外。这正是本项目最怕的那一类：不是报红报错，是**红被吃掉了**。
#   `applies_to=None` 表示任何步骤都可能命中（删除闸对任何写盘的步骤都成立）；
#   给了元组就只在那些步骤自己的判定里算。
ENV_SIGS: list[tuple[str, str, tuple[str, ...] | None]] = [
    # ① 本机的批量删除闸：删**早先轮次留下的内容**、且本轮累计过线时要显式确认，
    #    拦下即 fail-closed。它跟被验的东西毫无关系，却能让任何一步以非零码结束 ——
    #    验收脚本的收尾清理会撞它，**产品代码自己写文件也会撞它**（实测撞在
    #    `src/textlayer.py` 的 `canvas.save(raw/slotNN_bg.jpg)` 那一步）。下一轮重置。
    ("SAFE_DELETE_BULK_CONFIRM_REQUIRED",
     "本机的批量删除闸（删早先轮次留下的内容 / 本轮累计过线要确认）。"
     "与这次改动无关，**下一轮会重置**。",
     None),
    # ② 抠图内存降级：verify_m5 的判定是干净的，但它走**退出码 7** ——
    #    那一批比齐套可做的少：位置 6/7 的素材抠图连续失败三次后，按
    #    cause=cutout_error 显式跳过（src/orchestrator.py）。
    #    产品的行为是对的（重试 3 次、不静默降级、成因可读），所以这不是代码缺陷；
    #    缺的是内存（单次抠图约 6 GB 物理 / 9 GB 可提交）。下一动作是关掉审核台重跑。
    ("M5-DEGRADE:",
     "抠图因内存不足连续失败，本批比齐套可做的少（verify_m5 走退出码 7）。"
     "关掉审核台 / 别并发跑抠图，内存宽裕时 --fresh 重跑再下结论。",
     ("M5 验收",)),
]


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def memory_headroom() -> tuple[int, int] | None:
    """(可用物理 MB, 可用提交 MB)；非 Windows 返回 None（不做闸，也不假装量过）。"""
    if not hasattr(ctypes, "windll"):
        return None
    st = _MEMORYSTATUSEX()
    st.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
        return None
    mib = 1024 * 1024
    return int(st.ullAvailPhys // mib), int(st.ullAvailPageFile // mib)


def gate_memory(force: bool) -> tuple[bool, list[str]]:
    head = memory_headroom()
    if head is None:
        return True, ["内存闸：本平台量不到提交内存，跳过（不是通过）"]
    phys, commit = head
    line = f"内存余量：可用物理 {phys:,} MB · 可用提交 {commit:,} MB"
    if phys >= GATE_PHYS_MB and commit >= GATE_COMMIT_MB:
        return True, [line + f"（门槛 {GATE_PHYS_MB:,} / {GATE_COMMIT_MB:,}）"]
    return force, [
        line + f" —— **低于门槛 {GATE_PHYS_MB:,} / {GATE_COMMIT_MB:,}**",
        f"    单次抠图实测约需 {CUTOUT_PHYS_MB:,} MB 物理 / {CUTOUT_COMMIT_MB:,} MB 提交。",
        "    余量不足通常意味着另一个进程正揣着抠图会话（审核台开着？上一次跑没退干净？）。",
        "    两个各揣抠图会话的进程同时跑，后启动的那个会在 ORT 里报 bad allocation，",
        "    表现成 `MemoryError: Unable to allocate 1.76 MiB` —— 看着偶发，其实必然。",
        "    先关掉另一个进程；确实要明知故犯就加 --force。",
    ]


def run(name: str, args: list[str], verbose: bool, timeout: int = 1800) -> dict:
    t0 = time.time()
    try:
        p = subprocess.run([PY, *args], cwd=str(ROOT), capture_output=True,
                           text=True, encoding="utf-8", timeout=timeout, errors="replace")
        rc, out, err = p.returncode, p.stdout or "", p.stderr or ""
    except subprocess.TimeoutExpired:
        rc, out, err = "TIMEOUT", "", f"超过 {timeout}s 未结束"
    except OSError as exc:
        rc, out, err = "UNLAUNCHABLE", "", str(exc)
    dt = time.time() - t0
    # 环境签名可能在 stdout，也可能在 stderr —— 两条都查。
    # ★ 但仍要过 `applies_to` 这道闸：只有**该步骤自己的判定**算数。
    #   否则任何转述别的步骤输出的脚本（例如打印 M5 输出尾部的对照探针）
    #   都会把别人的环境签名算到自己头上，把真失败洗成"被环境拦下"。
    hits = [(sig, why) for sig, why, applies in ENV_SIGS
            if (applies is None or name in applies) and (sig in out or sig in err)]
    env_blocked = bool(hits)
    tail = [ln for ln in out.splitlines() if ln.strip()][-12:]
    mark = "ENV " if env_blocked else ("OK  " if rc == 0 else "FAIL")
    block = [f"\n{'=' * 74}",
             f"[{mark}] {name}   rc={rc}   {dt:.1f}s   ({' '.join(args)})"]
    for sig, why in hits:
        block.append(f"    ⚠ 环境条件（{sig}）：{why}")
        block.append("      它与这次改动无关 —— 所以不计入「未通过」。")
    block += [f"    {ln}" for ln in tail]
    if err.strip():
        block.append("  stderr:")
        block += [f"    {ln}" for ln in err.strip().splitlines()[-12:]]
    print(f"[{mark}] {name:<14} rc={rc}  {dt:.1f}s", flush=True)
    if verbose:
        print("\n".join(block))
    return {"name": name, "rc": rc if isinstance(rc, int) else -1, "secs": dt,
            "block": "\n".join(block), "env": env_blocked,
            "env_sigs": [sig for sig, _ in hits]}


def tree_snapshot(root: Path) -> dict[str, tuple[int, str]]:
    """冻结目录的逐文件身份；文件集合、大小或内容任一变化都能被看见。"""
    result: dict[str, tuple[int, str]] = {}
    if not root.is_dir():
        return result
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        h = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        result[path.relative_to(root).as_posix()] = (path.stat().st_size, h.hexdigest())
    return result


def snapshot_diff(before: dict[str, tuple[int, str]],
                  after: dict[str, tuple[int, str]]) -> list[str]:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(path for path in set(before) & set(after) if before[path] != after[path])
    details: list[str] = []
    if added:
        details.append("新增：" + "、".join(added))
    if removed:
        details.append("删除：" + "、".join(removed))
    if changed:
        details.append("改写：" + "、".join(changed))
    return details


def stash_existing_runs() -> list[str]:
    """把 out/ 下现有产物**重命名**挪到 out_prev/（不删，可回退）。

    为什么必须挪：如果 --fresh 只是"再跑一轮"，那 out/ 里旧产物还在，
    "从零"就只是说法 —— 而"这批图到底是不是当前代码产出的"恰恰是这一步要回答的。
    挪走之后 out/ 只剩本轮一轮，验收对象唯一，结论才可核对。
    """
    out = ROOT / "out"
    if not out.exists():
        return []
    prev = ROOT / "out_prev"
    prev.mkdir(exist_ok=True)
    moved: list[str] = []
    for d in sorted(out.iterdir()):
        tgt = prev / d.name
        if tgt.exists():
            continue
        d.rename(tgt)
        moved.append(d.name)
    return moved


def new_run_dirs(before: set[str]) -> set[str]:
    out = ROOT / "out"
    if not out.exists():
        return set()
    return {d.name for d in out.iterdir() if d.is_dir()} - before


def main() -> int:
    ap = argparse.ArgumentParser(description="五级验收回归")
    ap.add_argument("--fresh", action="store_true",
                    help="从零：dry-run 报价 → 真跑全链路 → 验收")
    ap.add_argument("--verbose", action="store_true", help="打印每项的完整输出")
    ap.add_argument("--force", action="store_true", help="内存余量不足也继续（不建议）")
    args = ap.parse_args()

    ok, gate_lines = gate_memory(args.force)
    head = ["五级验收回归", "=" * 74,
            f"时间 {time.strftime('%Y-%m-%d %H:%M:%S')} · 根目录 {ROOT}",
            f"模式 {'--fresh（从零真跑）' if args.fresh else '复用现有 out/'}", *gate_lines]
    for ln in gate_lines:
        print(ln)
    if not ok:
        # ★ 拒跑**不是**一次回归结果 —— 所以它不许写进 REPORT。
        #   那会把上一轮的真结论替换成一句「拒跑」，而任务证据仍然存在、
        #   守卫仍然全绿：正是本项目最不想要的那种失败（证据被静默替换，不报错）。
        REFUSED_REPORT.parent.mkdir(parents=True, exist_ok=True)
        REFUSED_REPORT.write_text(
            "\n".join([*head, "",
                       "拒跑：内存余量不足（退出码 8）。",
                       f"上一轮的真实结论保留在 {REPORT} —— 本次未改动它。"]),
            encoding="utf-8")
        print(f"\n拒跑。本次拒绝记录：{REFUSED_REPORT}")
        print(f"     上一轮回归结论未改动：{REPORT}")
        return 8

    results: list[dict] = []
    extra: list[str] = []
    control_failures: list[str] = []
    import json

    import orchestrator  # noqa: E402  （「上一轮是哪一轮」的唯一实现）
    upc = json.loads((ROOT / PRODUCT).read_text(encoding="utf-8"))["upc"]

    def target_run() -> tuple[str | None, int]:
        """验收会读哪一轮。复用 orchestrator.latest_run —— 「上一轮是哪一轮」只有一处实现。"""
        out = ROOT / "out"
        n = sum(1 for d in out.iterdir()
                if d.is_dir() and (d / "plan.json").exists()) if out.exists() else 0
        p = orchestrator.latest_run(out, upc)
        return (p.name if p else None), n

    def note_target(tag: str) -> str | None:
        name, n = target_run()
        extra.append(f"{tag}验收对象：{name or '（out/ 下没有可验收的 run）'}"
                     f"　（out/ 下共 {n} 轮产物）")
        if n > 1 and not args.fresh:
            extra.append("提示：out/ 下不止一轮，验收读的是最新那轮；"
                         "要确保验的是新代码产出的那批，用 --fresh")
        print(f"{tag}验收对象：{name}（out/ 下共 {n} 轮）", flush=True)
        return name

    def flush() -> None:
        body = [*head, ""]
        if extra:
            body += [*extra, ""]
        body += [r["block"] for r in results]
        bad = [r["name"] for r in results if r["rc"] != 0 and not r.get("env")]
        bad += control_failures
        env = [r["name"] for r in results if r.get("env")]
        okn = [r["name"] for r in results if r["rc"] == 0 and not r.get("env")]
        body += ["", "=" * 74, f"汇总（{len(results)} 项）"]
        body += [f"  {'ENV ' if r.get('env') else ('OK  ' if r['rc'] == 0 else 'FAIL')}"
                 f"  {r['name']:<14} rc={r['rc']}" for r in results]
        body += ["", f"结论：{len(okn)} 通过 · {len(env)} 被环境拦下 · {len(bad)} 未通过"]
        if env:
            # 按**签名分组**列：两类环境的下一动作完全不同（一类等下一轮就好了，
            # 一类要腾内存再跑），合成一句「被环境拦下」等于什么也没说。
            by_sig: dict[str, list[str]] = {}
            for r in results:
                if r.get("env"):
                    for sig in (r.get("env_sigs") or ["(未标明的环境条件)"]):
                        by_sig.setdefault(sig, []).append(r["name"])
            body.append("  被环境拦下（与本次改动无关，**不算「未通过」**）：")
            for sig, names in by_sig.items():
                why = next((w for s, w, _ in ENV_SIGS if s == sig), "")
                body.append(f"    · {sig}：{', '.join(names)}")
                if why:
                    body.append(f"      {why}")
        if bad:
            body += [f"  未通过：{', '.join(bad)}"]
            if "全链路真跑" in env:
                body += ["  注意：「全链路真跑」被拦 ⇒ 下面读产物的 M3/M4/M5/M6 红是**连带**，",
                         "  不构成代码缺陷的证据。等下一轮额度重置后用 --fresh 重跑再判断。"]
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text("\n".join(body), encoding="utf-8")

    frozen_run: Path | None = None
    frozen_before: dict[str, tuple[int, str]] | None = None
    m6_run: Path | None = None
    if not args.fresh:
        frozen_name = note_target("")
        if frozen_name:
            frozen_run = ROOT / "out" / frozen_name
            frozen_before = tree_snapshot(frozen_run)
            TMP.mkdir(parents=True, exist_ok=True)
            sandbox_root = Path(tempfile.mkdtemp(prefix="regress-m6-", dir=str(TMP)))
            m6_run = sandbox_root / frozen_run.name
            shutil.copytree(frozen_run, m6_run)
            extra.append(f"M6 写入隔离：{m6_run}（冻结 run 只读核对）")

    if args.fresh:
        spent = run("dry-run 报价", ["run.py", "--product", PRODUCT, "--dry-run"],
                    args.verbose)
        results.append(spent)
        flush()
        if spent["rc"] != 0:
            print(f"\n报价都跑不通，停。报告：{REPORT}")
            return 1
        before = set()
        moved = stash_existing_runs()
        extra.append(("旧产物已挪到 out_prev/（重命名，未删，可回退）：" + "、".join(moved))
                     if moved else "out/ 下本来就没有旧产物 —— 这一轮是真·从零")
        t0 = time.strftime("%Y-%m-%d %H:%M:%S")
        r = run("全链路真跑", ["run.py", "--product", PRODUCT, "--progress"], args.verbose)
        results.append(r)
        created = new_run_dirs(before)
        newest = note_target(f"--fresh（{t0} 起跑）")
        if len(created) == 1 and newest in created:
            extra.append(f"本轮新 run：{newest}（{t0} 起跑）—— 验收读到的就是它，"
                         f"已按 latest_run 的目录名排序断言过")
        else:
            extra.append(f"**断言失败**：新 run 目录 {sorted(created)}，"
                         f"而 latest_run 返回 {newest} —— 验收读的可能不是这一轮，"
                         f"下面所有绿灯都不能当数")
            results.append({"name": "新 run 断言", "rc": 1, "secs": 0.0,
                            "block": "[FAIL] 新 run 断言：最新 run 不是本轮产生的"})
        flush()

    TOOLS = [
        ("M3 验收", ["tools/verify_m3.py"]),
        ("M4 验收", ["tools/verify_m4.py"]),
        ("M5 验收", ["tools/verify_m5.py"]),
        ("M6 验收", ["tools/verify_m6.py", str(m6_run), PRODUCT]
         if m6_run else ["tools/verify_m6.py"]),
        ("M7 验收", ["tools/verify_m7.py"]),
        ("表守卫", ["tools/check_table_guards.py"]),
        ("假保护守卫", ["tools/check_forbidden_rules.py"]),
        ("卡同步", ["tools/gen_slot_cards.py", "--check"]),
        ("文档守卫", ["tools/check_docs.py"]),
        ("项目状态守卫", ["tools/check_project_state.py"]),
        ("文档登记对照", ["evals/probes/docs_index.py"]),
        ("项目状态对照", ["evals/probes/project_state.py"]),
        ("不变量探针", ["evals/probes/invariants.py"]),
        ("跳过成因对照", ["evals/probes/skip_cause.py"]),
        ("位置4快照", ["evals/run_golden.py"]),
        ("P1.1 契约", ["tools/verify_p1_1_contract.py"]),
        ("P1.2 政策", ["tools/verify_p1_2_policy.py"]),
        ("P1.3 清单", ["tools/verify_p1_3_review.py"]),
        ("P1.4 登记", ["tools/verify_p1_4_registry.py"]),
        ("P1.5 数据集", ["tools/verify_p1_5_dataset.py"]),
        ("autofix 接线", ["run.py", "--product", PRODUCT, "--only", "1",
                          "--autofix", "--out", str(TMP / "autofix")]),
    ]
    for name, cmd in TOOLS:
        results.append(run(name, cmd, args.verbose))
        flush()          # ← 每项跑完立刻落盘：中断也不丢结论

    if frozen_run is not None and frozen_before is not None:
        drift = snapshot_diff(frozen_before, tree_snapshot(frozen_run))
        if drift:
            control_failures.append("冻结 run 被回归改写")
            extra.append("**冻结 run 守卫失败**：" + "；".join(drift))
        else:
            extra.append(f"冻结 run 守卫通过：{frozen_run.name} 的文件集合与逐文件哈希前后一致")
        flush()

    bad = [r["name"] for r in results if r["rc"] != 0 and not r.get("env")]
    bad += control_failures
    env = [r["name"] for r in results if r.get("env")]
    okn = len([r for r in results if r["rc"] == 0 and not r.get("env")])
    print(f"\n结论：{okn} 通过 · {len(env)} 被环境拦下 · {len(bad)} 未通过"
          + ("" if not bad else f"；未通过：{', '.join(bad)}"))
    for r in results:
        if r.get("env"):
            for sig in (r.get("env_sigs") or ["(未标明的环境条件)"]):
                why = next((w for s, w, _ in ENV_SIGS if s == sig), "")
                print(f"  被环境拦下 · {r['name']} · {sig}" + (f"：{why}" if why else ""))
    print(f"报告：{REPORT}")
    if bad:
        return 1
    return 3 if env else 0


if __name__ == "__main__":
    sys.exit(main())
