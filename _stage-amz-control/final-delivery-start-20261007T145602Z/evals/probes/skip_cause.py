"""跳过成因判据的**植入对照**：一个判据只有被证明"能红、且只在该红的地方红"才算判据。

被验对象
--------
`tools/verify_m5.py` 的 A 条 —— 「跳过必须带机器可读的成因，且按成因分流」。
它守的是一个具体的错：`slot_skipped` 原来只有散文 `reason`，于是控制台把
"运行时抠图失败"和"入口缺料"都说成「缺料」—— 运营看到会去翻素材照片，
而真正该做的是关掉审核台重跑。**两份真相里，机器读的那份必须是结构化的。**

做法（单变量对照）
------------------
把一轮 run 复制成三份，**只改一个变量**：`slot_skipped` 记录的 `cause`。
其余一字不动，于是退出码的差异只能由这一个变量解释。

产物里若**一条跳过都没有**（7/7 全成的那种），本探针会先**人工植入一条**：
挑 doable 里最大的坑位，去掉它的 render/validate 痕迹，把它的产物改名成
`*.jpg.off`（改名而不是删 —— 本机的删除有闸，且删掉就回不去了），
再补一条 `slot_skipped`。这样对照在任何产物上都跑得动。

变体与期望
----------
    nocause   抹掉 cause                 → 退出码 1（成因不可读 ⇒ 假通过，必须红）
    planned   全部标 cause=intake        → 退出码 0（计划内跳过，不是失败）
    degrade   全部标 cause=cutout_error  → 退出码 7（环境降级，不并入"未通过"）

三个退出码互不相同，这正是要证明的：**判据能把三类分开，而不是笼统地红/绿。**
若某天 `verify_m5` 把它们合成同一个码，本探针会红 —— 那是设计被改坏的信号。

用法
    python evals/probes/skip_cause.py            # 用 out/ 下最近一轮
    python evals/probes/skip_cause.py <run_dir>  # 指定某一轮

退出码：0 三向对照全部符合期望 / 1 有变体不符 / 2 用法或数据问题
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "out"
TMP = ROOT / "evals" / ".tmp" / "m5ctl"
M5 = ROOT / "tools" / "verify_m5.py"

# 与 verify_m5 / run.py 同一处接缝：src/ 自己的模块用**扁平导入**（`import registry`），
# 所以 src/ 必须在 sys.path 上 —— 不是 `from src import registry`。
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402  （控制台编码归一：见 src/console.py）
enable_utf8()
import registry  # noqa: E402

# 别的断言**点名**要看的坑位。本探针要的是"只动一个变量"，所以植入点必须避开它们：
#   1  —— assert_c 拿它当主体 sha 的基线（位置 7 与位置 1 同源）
#   5  —— assert_b / assert_d / assert_e 的对象
#   6  —— assert_b / assert_d 的对象（且声明 cuts）
#   7  —— assert_c / assert_d 的对象（且声明 cuts）
# 剩下又不声明 cuts、不调模型的坑位才是干净的植入点（本表里是 2 / 3）。
_RESERVED = {1, 5, 6, 7}

CAUSE_INTAKE = "intake"
CAUSE_CUTOUT = "cutout_error"

# (变体名, 对该变体的 slot_skipped 记录施加的 cause, 期望退出码)
VARIANTS = (
    ("nocause", None, 1),
    ("planned", CAUSE_INTAKE, 0),
    ("degrade", CAUSE_CUTOUT, 7),
)


def newest_run() -> Path | None:
    runs = [p for p in OUT.glob("*") if (p / "run.jsonl").exists()]
    return max(runs, key=lambda p: p.stat().st_mtime) if runs else None


def _records(path: Path) -> list[dict]:
    out = []
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            out.append({"_unparsable": ln})       # 半行日志：照抄产品口径，容忍
    return out


def _write(path: Path, recs: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
        encoding="utf-8")


def _copy_run(src: Path, dst: Path) -> None:
    """只搬判据真正会读的东西：run.jsonl / 顶层 *.jpg（raw/ 只为人眼留存）。

    刻意不整目录复制：与本次判据无关的大件（如 subject.png）搬过来只会让对照
    变慢，并给"我没改别的东西"留下解释空间。
    """
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    shutil.copy2(src / "run.jsonl", dst / "run.jsonl")
    for j in src.glob("*.jpg"):
        shutil.copy2(j, dst / j.name)


def _plant_cause(dst: Path, cause: str | None) -> int:
    """把每条 slot_skipped 的 cause 设成给定值（None = 抹掉）。返回改动的条数。"""
    recs = _records(dst / "run.jsonl")
    touched = 0
    for r in recs:
        if r.get("stage") != "slot_skipped":
            continue
        touched += 1
        if cause is None:
            r.pop("cause", None)
        else:
            r["cause"] = cause
    _write(dst / "run.jsonl", recs)
    return touched


def _safe_victim(recs: list[dict]) -> int | None:
    """挑一个"去掉它只影响 A 条"的坑位。

    ★ 第一版选了 `max(doable)`（本表里是位置 7），结果**必然假红**：
      位置 7 的渲染器声明 cuts=[competitor]，一去掉它的 render 记录，
      assert_g 的 `want`（本批声明要抠的素材）就少一样，而 cutout 记录还在
      → `want != got` → 连带红。于是三个变体全是 rc=1，对照失去意义。
    → 判据是：**植入点必须落在别的断言够不到的地方**，否则测的就不是一个变量。
    """
    renders = {r.get("slot_id"): str(r.get("renderer") or "")
               for r in recs if r.get("stage") == "render"}
    cands = [sid for sid, rend in renders.items()
             if isinstance(sid, int) and sid not in _RESERVED
             and not registry.cuts_of(rend)        # 否则 assert_g 失衡
             and not registry.calls_model(rend)]   # 否则 assert_f 失衡
    return max(cands) if cands else None


def _synth_skip(dst: Path) -> int:
    """产物里没有跳过时，人工植入一条。

    返回植入的条数（1 或 0）。**改名而不是删产物** —— 本机的删除有闸，
    而且删了就回不去；改名对判据等价（判据只 glob `*.jpg`）。
    """
    recs = _records(dst / "run.jsonl")
    start = next((r for r in recs if r.get("stage") == "run_start"), None)
    doable = [d for d in ((start or {}).get("doable") or []) if isinstance(d, int)]
    if not doable:
        return 0
    victim = _safe_victim(recs)
    if victim is None:
        return 0

    keep = [r for r in recs
            if not (r.get("slot_id") == victim
                    and r.get("stage") in ("render", "validate", "redo",
                                           "redo_start", "redo_end"))]
    keep.append({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "stage": "slot_skipped",
        "slot_id": victim,
        "missing": [],
        "reason": "（对照用：人工植入的跳过记录，仅存在于沙箱）",
    })
    _write(dst / "run.jsonl", keep)

    for j in dst.glob(f"*_{victim:02d}_*.jpg"):
        j.rename(j.parent / (j.name + ".off"))     # 判据只 glob *.jpg，改名即隐身
    return 1


def _run_m5(run_dir: Path) -> tuple[int, str]:
    p = subprocess.run([sys.executable, str(M5), str(run_dir)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(ROOT))
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main(argv: list[str]) -> int:
    src = Path(argv[1]) if len(argv) > 1 else newest_run()
    if not src or not (src / "run.jsonl").exists():
        print("找不到 run.jsonl：请先跑一次 "
              "`python run.py --product examples/product_fullset.json`")
        return 2

    print(f"跳过成因判据的植入对照 · 源产物 {src.name}")
    print("=" * 72)
    # ★ 必须先加载渲染器：`_safe_victim` 读 `registry.cuts_of` / `calls_model`，
    #   不 load_all() 它们就是个空表 —— 于是**位置 4（唯一调模型的那格）会被当成
    #   干净的植入点**，去掉它 assert_f 就失衡。与 verify_m5 里的同一个坑。
    registry.load_all()
    base = TMP / f"{time.strftime('%Y%m%d-%H%M%S')}-base"
    _copy_run(src, base)
    n = _plant_cause(base, None)          # 先统一抹掉 cause（顺带数一数有几条）
    if n == 0:
        n = _synth_skip(base)             # 一条都没有 → 人工植入
        if n:
            print(f"源产物里没有任何跳过 → 已人工植入 {n} 条（只存在于沙箱）")
    if n == 0:
        print("既没有跳过、也无法植入（run_start 里没有 doable）—— 对照无从谈起。")
        return 2

    bad: list[str] = []
    for name, cause, want in VARIANTS:
        d = base.parent / f"{base.name}-{name}"
        if d.exists():
            shutil.rmtree(d)
        shutil.copytree(base, d)
        touched = _plant_cause(d, cause)
        rc, out = _run_m5(d)
        mark = "OK  " if rc == want else "FAIL"
        print(f"[{mark}] {name:<8} cause={str(cause):<12} "
              f"rc={rc}（期望 {want}）  改了 {touched} 条")
        if rc != want:
            bad.append(f"{name}：rc={rc}，期望 {want}")
            # ★ 只摘**失败行**，不整段照搬被验脚本的输出。照搬会把它自己的环境签名
            #   （`M5-DEGRADE:`）带进本探针的 stdout —— 于是 tools/regress_all.py 会
            #   把本探针的**真失败**认成"被环境拦下"，红被吃掉。要摘就摘得干净。
            for ln in [s for s in out.splitlines() if "✗" in s][:8]:
                print(f"       {ln}")
        if name == "degrade":
            # degrade 变体必须同时**在报告里自报家门**（M5-DEGRADE: 标记），
            # 否则 tools/regress_all.py 认不出它、会把它误并进「未通过」。
            tagged = "M5-DEGRADE:" in out
            print(f"      {'OK  ' if tagged else 'FAIL'} 报告带机器可读标记 M5-DEGRADE:")
            if not tagged:
                bad.append("degrade 变体的报告没有 M5-DEGRADE: 标记")

    # 默认不删（见 README §9「清理不得改变结论」）：本机的删除有闸，删不掉也不该改结论。
    print(f"\n沙箱留在 {TMP.relative_to(ROOT)}/（默认不删；确认后可整个删）")
    print("=" * 72)
    if bad:
        print(f"未通过 {len(bad)} 条：")
        for b in bad:
            print(f"  ✗ {b}")
        return 1
    print("三向对照全部符合期望：成因不可读 → 1，计划内跳过 → 0，环境降级 → 7。")
    print("判据能把三类分开 —— 这是「全绿」不随机器内存浮动的依据。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
