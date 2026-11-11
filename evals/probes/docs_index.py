#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""文档守卫的反向对照（每向只改一个变量，改完即还原）。

守的是 `tools/check_docs.py` 当前生效的四类判据：

    ① `_check_docs_index()` —— 每一份受管 `*.md` 都在 `docs/INDEX.md` 登记；
       状态与管辖事实是闭集合；说明列非空；「实现 / 产品目标 / 执行状态 / 项目规则」
       四类事实各自只能有一个权威，且必须有一个权威；已完成任务的任务书不能仍是 draft。
    ② `_check_reuse_first_gate()` 的 vendor 部分 —— vendor 目录里每个文件都要登记。
    ③ `_check_no_abs_interpreter()` —— 受管文档不得写死解释器绝对路径。
    ④ `_check_readme_scope()` —— README 不抄会漂移的数字（回归项数、探针方向数）。

**分类器本身也是判据，也要配反向对照。** 这条本项目踩过一次：
`regress_all.ENV_SIGS` 只看「输出里有没有环境签名」，转述别人输出的脚本被误判，
**一个真失败被认成「被环境拦下」，连「未通过」都进不去 —— 红被吃掉了。**
上面几条同样是「读一份文件来决定别的东西有没有问题」，所以必须被证明：
**只在该红的地方红。**

2026-10-01 的两处漂移（都是这次修掉的，不是放宽判据）：

  * 旧版本锚在 `docs/业务逻辑.md` 的五行登记行上；Product V2 重组后登记表变成
    五列（path / 归属 / 管辖事实 / 状态 / 说明）且那份文档已不存在 —— 探针打
    `[skip] 锚点未命中` 并 rc=1，**没有假装通过**（这就是它当时唯一正确的行为）。
    现在所有锚点都从 `docs/INDEX.md` 运行时解析，不再写死任何一行。
  * F/O「README 抄的项数写错」两向随 `_check_numbers()` 一起退役：README 不再抄
    运行结果，`_check_readme_scope()` 反向禁止这两类副本回流，改由 M 向对照。

二十向（每次只改一个变量，改完即还原；登记表按 parent + 分片读取）：

    A 基线                   不改                        → 0
    B 漏登记                 抽掉一行登记                → 1，须报「没登记」，**不许**报「文件不在」
    C 幽灵登记               加一行不存在的文件          → 1，须报「文件根本不在这几份」
    D 非法状态               某行状态改 done             → 1，须报「不在取值域」
    E 空说明                 某行说明列清空              → 1，须报「说明列为空」
    G 非法管辖事实           某行改 kind=参考            → 1，须报「的管辖事实」
    H 双头权威               非单例 kind 行改 项目规则    → 1，须报「只能有一个权威」
    I 权威缺失               产品目标行改 历史证据        → 1，须报「没有任何出处」
    J 受管范围               执行状态行改指不存在文件     → 1，须报「没登记」+「文件不在」
    K 写死解释器路径         README 塞回绝对路径          → 1，须报「解释器的绝对路径」
    L vendor 未登记          往 vendor 目录丢一个文件     → 1，须报「没有登记」
    M README 抄探针方向数    README 写回 N 向植入对照     → 1，须报「不得手抄探针方向数」
    N README 复制下一动作赋值 不改                        → 1
    O 说明恢复入口不复制进度 不改                        → 0
    P 前端未批准依赖         manifest 塞入未落锁依赖       → 1
    Q 未认领分片             docs/catalog 新建未认领页     → 1，须报「没登记」
    R 重复认领               第二个父文档抢已认领分片      → 1，须报「拆分件重复认领」
    S 丢失分片               删掉一个已认领分片            → 1，须报「拆分件不存在」
    T 独立身份               给分片再加一行独立登记        → 1，须报「独立登记身份」
    U 未登记机器状态         新建无人认领的 state.yaml     → 1，须报「没登记」

判据分两层，缺一不可：
    ① 退出码与预期一致；
    ② **报错内容命中预期关键词、且「不该报的项」一条都不许出现。**
       —— 只看退出码，会被「随便报一条别的错」蒙过去。
锚点未命中（文档已被改动）按 **FAIL** 处理，不假装通过。

用法：python evals/probes/docs_index.py      （退出码 0 全对 / 1 有偏差；--count 只报方向数）
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))          # 只为取 console（见 src/console.py）
from console import enable_utf8  # noqa: E402
enable_utf8()

CODE_ROOT = ROOT
sys.path.insert(0, str(CODE_ROOT / "tools"))
from check_project_state import _read_document_text  # noqa: E402  （与守卫同一读取口径）

_fixture = tempfile.TemporaryDirectory(prefix="amz-docs-probe-")
ROOT = Path(_fixture.name)
# 只复制守卫读取的控制材料；不复制或写入业务目录、密钥、浏览器数据。
for relative in ("README.md", "AGENTS.md", "package.json", "package-lock.json",
                 "pyproject.toml", "uv.lock", "app/product_v2/package.json"):
    source = CODE_ROOT / relative
    target = ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
# 受管集合与守卫同一口径：已跟踪 + 未跟踪但未被 gitignore 的文件。逐文件 `git ls-files`
# 会漏掉尚未 add 的新分片与 state.yaml，夹具缺文件时基线会被误判为红。
_listing = subprocess.run(
    ["git", "-c", "core.quotepath=false", "ls-files", "-z", "--cached", "--others",
     "--exclude-standard", "--", "*.md", "*.yaml"],
    capture_output=True, cwd=str(CODE_ROOT), timeout=60).stdout.decode("utf-8")
for relative in sorted(set(_listing.split("\0")) - {""}):
    source = CODE_ROOT / relative
    if not source.is_file():
        continue                       # 工作树里已删除的跟踪文件不是夹具的受管文档
    target = ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
for relative in ("config", "app/product_v2/vendor", "evals/product-v2/vendor"):
    shutil.copytree(CODE_ROOT / relative, ROOT / relative)

INDEX = ROOT / "docs" / "INDEX.md"
README = ROOT / "README.md"
FRONTEND_MANIFEST = ROOT / "package.json"
FRONTEND_LOCK = ROOT / "package-lock.json"
REGISTRY = ROOT / "config" / "document-splits.json"
GUARD = CODE_ROOT / "tools" / "check_docs.py"
VENDOR_PROBE = ROOT / "app" / "product_v2" / "vendor" / "zz_probe_ghost.js"


def index_parts() -> list[Path]:
    """父文档认领的分片（物理文件），按登记顺序；缺登记时留空由基线报出。"""
    if not REGISTRY.exists():
        return []
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    entries = data.get("splits") if isinstance(data, dict) else None
    entry = next((e for e in entries if isinstance(e, dict) and e.get("path") == "docs/INDEX.md"), None) \
        if isinstance(entries, list) else None
    parts = entry.get("parts") if isinstance(entry, dict) else None
    return [ROOT / part["path"] for part in parts] if isinstance(parts, list) else []


INDEX_PARTS = index_parts()
# 备份留**字节**：仓库里同时存在 CRLF（README / 卡片）与 LF（计划、新工具）两种行尾，
# 而**没有任何守卫管这件事**。用 read_text() 备份、write_text() 还原，在 Windows 上
# 会把 LF 文件悄悄变成 CRLF ——「已还原」这句话就成了假的。所以存 bytes，还原后比一次。
WATCHED = tuple(dict.fromkeys(
    [INDEX, *INDEX_PARTS, README, FRONTEND_MANIFEST, FRONTEND_LOCK, REGISTRY]))
WATCHED = tuple(p for p in WATCHED if p.exists())
ORIG = {p: p.read_text(encoding="utf-8") for p in WATCHED}
ORIG_BYTES = {p: p.read_bytes() for p in WATCHED}

# 守卫出错关键词（必须原样命中；must_not 用的是同一批的反面与邻近项）
MISSING_OF = "没登记"
NOT_IN_REPO = "文件根本不在这几份"
BAD_STATE = "不在取值域"
EMPTY_NOTE = "说明列为空"
BAD_KIND = "的管辖事实"
DUP_KIND = "只能有一个权威"
NO_KIND = "没有任何出处"
ABS_INTERP = "解释器的绝对路径"
VENDOR_UNREG = "没有登记"
VENDOR_GHOST = "登记了、目录里却没有"
README_NUMBER = "不得手抄探针方向数"

GHOST_DOC = "docs/zz_probe_ghost.md"
GHOST_STATE = "_working/zz_probe_state.md"
GHOST_PART = "docs/catalog/zz_probe_part.md"
GHOST_MACHINE = "docs/zz_probe_machine/state.yaml"
DUP_CLAIM = "拆分件重复认领"
MISSING_PART = "拆分件不存在"
OWN_IDENTITY = "独立登记身份"

ROW_RE = re.compile(r"^\|\s*`([^`]+\.md)`\s*\|")


class ProbeOutdated(RuntimeError):
    """文档结构变了、本探针构造不出对照 —— 按 FAIL 计，不假装通过。"""


def index_text() -> str:
    """父文档 + 分片的联合正文（与守卫同一个 reader，不另写一份解析）。"""
    return _read_document_text("docs/INDEX.md", root=ROOT)


def index_rows() -> dict[str, list[str]]:
    """从登记表读出 path -> [归属, 管辖事实, 状态, 说明]（守卫的解析规则一致）。"""
    rows: dict[str, list[str]] = {}
    for line in index_text().splitlines():
        ln = line.strip()
        m = ROW_RE.match(ln)
        if not m or not ln.endswith("|"):
            continue
        cells = [c.strip().strip("`").strip() for c in ln.strip("|").split("|")]
        if len(cells) != 5:
            continue
        rows[m.group(1)] = cells[1:]
    return rows


ROWS = index_rows()


def row_line(doc: str) -> str:
    for line in index_text().splitlines():
        if line.strip().startswith(f"| `{doc}` |"):
            return line
    raise ProbeOutdated(f"docs/INDEX.md 里找不到 {doc} 那一行")


def row_owner(doc: str) -> Path:
    """登记行实际所在的物理文件：父页或某个分片。补丁必须改物理文件。"""
    for path in (INDEX, *INDEX_PARTS):
        if path.exists() and any(line.strip().startswith(f"| `{doc}` |")
                                 for line in path.read_text(encoding="utf-8").splitlines()):
            return path
    raise ProbeOutdated(f"docs/INDEX.md 或分片里找不到 {doc} 那一行")


def pick_row(kind: str, state: str | None = None, *, prefer_sub: str = "") -> str:
    """按 kind/state 挑一行的 path（同候选里优先 prefer_sub 前缀，再按路径排序）。"""
    cands = [p for p, cells in ROWS.items()
             if cells[1] == kind and (state is None or cells[2] == state)]
    cands.sort(key=(lambda p: (not p.startswith(prefer_sub), p)) if prefer_sub else None)
    return cands[0] if cands else ""


def rebuild(doc: str, **over: str) -> str:
    """按当前五列重排该登记行，只改指定列（其余照抄）。"""
    owner, kind, state, note = ROWS[doc]
    return (f"| `{doc}` | {over.get('owner', owner)} | `{over.get('kind', kind)}` "
            f"| `{over.get('state', state)}` | {over.get('note', note)} |")


def run_guard() -> tuple[int, str]:
    """跑真正的守卫（--no-run：跳过命令执行，快、不花钱；本条判据与命令无关）。"""
    p = subprocess.run([sys.executable, "-B", str(GUARD), "--no-run", "--root", str(ROOT)],
                       cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def build_cases() -> list[tuple[str, list, int, list[str], list[str]]]:
    draft = pick_row("设计草案", "draft", prefer_sub="_working/") or pick_row("设计草案", "draft")
    counts: dict[str, int] = {}
    for cells in ROWS.values():
        counts[cells[1]] = counts.get(cells[1], 0) + 1
    multi_kind = next((kind for kind, n in sorted(counts.items())
                       if n >= 2 and kind not in ("实现", "产品目标", "执行状态", "项目规则")), "")
    plan_doc = pick_row("产品目标")
    state_doc = pick_row("执行状态")
    missing = [name for name, value in (("设计草案/draft 行", draft),
                                        ("≥2 份的管辖事实", multi_kind),
                                        ("产品目标 行", plan_doc),
                                        ("执行状态 行", state_doc)) if not value]
    if missing:
        raise ProbeOutdated("登记表里找不到：" + "、".join(missing) + " —— 探针需要更新")
    if not INDEX_PARTS:
        raise ProbeOutdated("config/document-splits.json 里没有 docs/INDEX.md 的分片"
                            " —— 探针需要更新")
    part_rel = INDEX_PARTS[0].relative_to(ROOT).as_posix()

    return [
        ("A 基线（不改）", [], 0, [],
         [MISSING_OF, NOT_IN_REPO, BAD_STATE, EMPTY_NOTE, BAD_KIND, DUP_KIND, NO_KIND]),
        ("B 漏登记（抽掉一行）", [("text", row_owner(draft), row_line(draft) + "\n", "")], 1,
         [MISSING_OF, draft], [NOT_IN_REPO]),
        ("C 幽灵登记（加一行不存在的文件）",
         [("text", row_owner(plan_doc), row_line(plan_doc),
           row_line(plan_doc) + "\n"
           f"| `{GHOST_DOC}` | 探针 | `设计草案` | `draft` | 探针：登记了但文件不存在 |")], 1,
         [NOT_IN_REPO, GHOST_DOC], [MISSING_OF]),
        ("D 非法状态（draft → done）",
         [("text", row_owner(draft), row_line(draft), rebuild(draft, state="done"))], 1,
         [BAD_STATE], [MISSING_OF, NOT_IN_REPO]),
        ("E 空说明（说明列清空）",
         [("text", row_owner(draft), row_line(draft), rebuild(draft, note=""))], 1,
         [EMPTY_NOTE], [MISSING_OF, NOT_IN_REPO, BAD_STATE, BAD_KIND]),
        ("G 非法管辖事实（设计草案 → 参考）",
         [("text", row_owner(draft), row_line(draft), rebuild(draft, kind="参考"))], 1,
         [BAD_KIND], [MISSING_OF, NOT_IN_REPO, BAD_STATE, EMPTY_NOTE, DUP_KIND, NO_KIND]),
        (f"H 双头权威（{multi_kind} → 项目规则）",
         [("text", row_owner(draft), row_line(draft), rebuild(draft, kind="项目规则"))], 1,
         [DUP_KIND, "项目规则"],
         [MISSING_OF, NOT_IN_REPO, BAD_KIND, NO_KIND, EMPTY_NOTE, BAD_STATE]),
        ("I 权威缺失（产品目标 → 历史证据）",
         [("text", row_owner(plan_doc), row_line(plan_doc),
           rebuild(plan_doc, kind="历史证据"))], 1,
         [NO_KIND, "产品目标"],
         [MISSING_OF, NOT_IN_REPO, BAD_KIND, DUP_KIND, EMPTY_NOTE, BAD_STATE]),
        ("J 受管范围（执行状态行改指不存在的文件）",
         [("text", row_owner(state_doc), row_line(state_doc),
           f"| `{GHOST_STATE}` | 探针 | `执行状态` | `current` | 探针：文件不存在 |")], 1,
         [MISSING_OF, NOT_IN_REPO],
         [DUP_KIND, NO_KIND, BAD_KIND, EMPTY_NOTE, BAD_STATE]),
        ("K 写死解释器路径（README 塞回绝对路径）",
         [("append", README, 'PY="C:/Users/probe/binaries/python.exe"')], 1,
         [ABS_INTERP], [MISSING_OF, NOT_IN_REPO, BAD_STATE]),
        ("L vendor 未登记（丢一个文件进 vendor 目录）",
         [("create", VENDOR_PROBE, "// 探针：未登记文件\n")], 1,
         [VENDOR_UNREG], [VENDOR_GHOST, MISSING_OF, NOT_IN_REPO]),
        ("M README 抄探针方向数（写回 N 向植入对照）",
         [("append", README, "（13 向植入对照）")], 1,
         [README_NUMBER], [MISSING_OF, NOT_IN_REPO, BAD_STATE]),
        ("N README 复制下一动作赋值",
         [("append", README, "next_action_task: V2.R3.1")], 1,
         ["README 不得复制 state 的下一动作赋值"], [MISSING_OF, NOT_IN_REPO]),
        ("O README 说明恢复入口不复制进度",
         [("append", README, "冷恢复入口输出下一任务，请按 state 路由读取。")], 0,
         [], ["README 不得复制 state 的下一动作赋值"]),
        ("P 前端 manifest 引入未批准未落锁依赖",
         [("text", FRONTEND_MANIFEST, '"devDependencies": {',
           '"devDependencies": {"zz-unapproved-probe": "1.2.3",')], 1,
         [], [MISSING_OF, NOT_IN_REPO]),
        ("Q 未认领分片（新建文档没人认领）",
         [("create", ROOT / GHOST_PART,
           "<!-- 拆分件：探针未认领页 -->\n上一页 <> ← 目录 → 下一页 <>\n"
           "本页不在任何拆分登记里。\n\n正文。\n")], 1,
         [MISSING_OF, GHOST_PART], [NOT_IN_REPO]),
        ("R 重复认领（第二个父文档抢已认领分片）",
         [("json", REGISTRY, lambda data: data["splits"].append(
             {"path": plan_doc, "mode": "raw-parts", "parts": [{"path": part_rel}]}))], 1,
         [DUP_CLAIM, part_rel], [MISSING_PART]),
        ("S 丢失分片（删掉一个已认领分片）",
         [("delete", INDEX_PARTS[-1])], 1,
         [MISSING_PART, INDEX_PARTS[-1].relative_to(ROOT).as_posix()], []),
        ("T 独立身份（给分片再加一行独立登记）",
         [("append", INDEX,
           f"| `{part_rel}` | 探针 | `参考` | `superseded` | 探针：分片另立身份 |")], 1,
         [OWN_IDENTITY, part_rel], []),
        ("U 未登记机器状态（新建无人认领的 state.yaml）",
         [("create", ROOT / GHOST_MACHINE, "task_progress:\n  probe: done\n")], 1,
         [MISSING_OF, GHOST_MACHINE], [NOT_IN_REPO]),
    ]


def apply_patches(patches: list) -> list[str]:
    """逐个套用到**当前**文件内容上。锚点未命中 → 返回一条问题（不静默跳过）。"""
    problems: list[str] = []
    for item in patches:
        kind = item[0]
        if kind == "text":
            _, path, old, new = item
            text = path.read_text(encoding="utf-8")
            if old not in text:
                problems.append(f"锚点未命中：{path.name} 里找不到 {old[:48]!r} —— "
                                f"文档已被改动，探针需要更新（本次按 FAIL 计，不假装通过）")
                continue
            path.write_text(text.replace(old, new, 1), encoding="utf-8")
        elif kind == "append":
            _, path, extra = item
            text = path.read_text(encoding="utf-8")
            if not text.endswith("\n"):
                text += "\n"
            path.write_text(text + extra + "\n", encoding="utf-8")
        elif kind == "create":
            _, path, content = item
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        elif kind == "delete":
            _, path = item
            if not path.exists():
                problems.append(f"待删文件不存在：{path.name} —— 文档已被改动，探针需要更新")
                continue
            path.unlink()
        elif kind == "json":
            _, path, mutate = item
            data = json.loads(path.read_text(encoding="utf-8"))
            mutate(data)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        else:
            problems.append(f"未知的补丁类型 {kind!r}")
    return problems


# 探针自己新建的文件：还原时必须消失，否则「已还原」不成立。
GHOSTS = (VENDOR_PROBE, ROOT / GHOST_PART, ROOT / GHOST_MACHINE)


def restore() -> None:
    for path, blob in ORIG_BYTES.items():
        path.write_bytes(blob)
    for path in GHOSTS:
        if path.exists():
            path.unlink()
        # create 会顺手造出父目录；只在它变空时移除，绝不递归删未知内容。
        if path.parent != ROOT and path.parent.exists() and not any(path.parent.iterdir()):
            path.parent.rmdir()


def restore_drift() -> list[str]:
    """还原之后与原始状态比对：不一致就把「已还原」这句话打回。"""
    drift = [p.name for p, blob in ORIG_BYTES.items() if p.read_bytes() != blob]
    drift += [p.name for p in GHOSTS if p.exists()]
    return drift


def main() -> int:
    if "--count" in sys.argv[1:]:
        # 只报方向数：README 若重新抄「N 向」必须能被机器核对（见 tools/check_docs.py）
        try:
            print(len(build_cases()))
        except ProbeOutdated as error:
            print(f"[skip] {error}")
            return 1
        return 0

    try:
        cases = build_cases()
    except ProbeOutdated as error:
        print(f"[skip] {error} —— 本次不假装通过")
        return 1

    bad = 0
    try:
        for name, patches, want_rc, must, must_not in cases:
            restore()                      # 每向前先回到基线，防止互相污染
            problems = apply_patches(patches)
            rc, out = run_guard()
            if rc != want_rc:
                problems.append(f"退出码 {rc}，期望 {want_rc}")
            for kw in must:
                if kw not in out:
                    problems.append(f"缺少预期的报错关键词 {kw!r}")
            for kw in must_not:
                if kw in out:
                    problems.append(f"出现了不该有的报错内容 {kw!r}")
            mark = "OK  " if not problems else "FAIL"
            print(f"[{mark}] {name}  → rc={rc}")
            for pr in problems:
                print(f"         {pr}")
            if problems:
                bad += 1
    finally:
        # 所有植入只作用于临时副本；中断不需要回写任何权威文件。
        restore()
        drift = restore_drift()
        if drift:
            print(f"✗ 还原后与原始状态不一致：{drift} —— 「已还原」不成立（行尾、编码或残留文件）")
            bad += 1
        else:
            print("独立副本已恢复 INDEX 父页与全部分片 / registry / README / manifest-lock / vendor（权威文件从未写入）")

    print()
    if bad:
        print(f"✗ {bad} / {len(cases)} 向与预期不符 —— 文档守卫的判据有问题")
        return 1
    print(f"OK：{len(cases)} 向全部与预期一致，且每向只报该报的那一类。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
