r"""当前文档、权威登记、依赖登记与模板采纳守卫。

README 的可执行 Python 示例按原参数运行；长驻服务和独立验证入口明确跳过。
历史文档只核身份登记，不执行旧产品、生成卡片或要求旧源码继续存在。

用法：
    python tools/check_docs.py
    python tools/check_docs.py --no-run
    python tools/check_docs.py --explain
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODE_ROOT = ROOT
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402  （控制台编码归一：见 src/console.py）
enable_utf8()
sys.path.insert(0, str(ROOT / "tools"))


README = ROOT / "README.md"
MANAGED_HAND = [README]


class Report:
    """收集当前文档错误及本次实际检查范围。"""

    def __init__(self) -> None:
        self.problems: list[str] = []
        self.notes: list[str] = []
        self.detail: list[str] = []

    def problem(self, msg: str) -> None:
        self.problems.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    def det(self, msg: str) -> None:
        self.detail.append(msg)


# ---------------------------------------------------------------- 围栏解析

FENCE_RE = re.compile(r"^```([A-Za-z0-9_+-]*)[ \t]*\n(.*?)^```[ \t]*$",
                      re.M | re.S)

# 只有 bash 围栏中的命令进入执行判据。
EXEC_LANGS = {"bash"}

# 不执行的命令及**理由**。理由必填 —— 一个没有理由的跳过就是一条被悄悄关掉的断言。
SKIP_RULES: list[tuple[str, str]] = [
    (r"tools[/\\](?:verify_\w+|check_docs|check_project_state)\.py",
     "守卫与验收脚本本身就是判据入口，跑它 = 把验收整跑一遍；"
     "而且 check_docs 去跑 check_docs 会自我递归"),
    (r"evals[/\\]",
     "探针与快照本身就是判据，各有自己的入口与退出码（见 §9）"),
]


def _iter_bash_commands(path: Path):
    """产出 (行号, 原始命令行)。只取 ```bash 围栏里的、非注释非赋值的行。"""
    text = path.read_text(encoding="utf-8")
    for m in FENCE_RE.finditer(text):
        lang, body = m.group(1), m.group(2)
        if lang not in EXEC_LANGS:
            continue
        base = text[:m.start()].count("\n") + 1
        for i, raw in enumerate(body.splitlines(), 1):
            ln = raw.strip()
            if not ln or ln.startswith("#"):
                continue
            head = ln.split()[0]
            # 变量赋值行（PY="..."）不是命令 —— 它是给人看的路径说明
            if "=" in head and not head.startswith(("$", "python")):
                continue
            yield base + i, ln


def _strip_inline_comment(ln: str) -> str:
    """去掉行尾的 `# 说明`。文档里的命令几乎每行都带一句人话注解。"""
    return re.sub(r"\s+#\s.*$", "", ln).rstrip()


def _to_argv(ln: str) -> list[str]:
    """把文档里的一行命令换成可执行的 argv。

    `$PY` / `python` 一律换成**当前解释器**：文档写 `python` 是为了人读，而"用哪个
    python"是一个已经定好的事实（隔离环境），不该让人每次自己拼。
    """
    toks = shlex.split(_strip_inline_comment(ln), posix=False)
    out: list[str] = []
    for i, t in enumerate(toks):
        t = t.strip('"').strip("'")
        if i == 0 and t in ("$PY", "${PY}", "python", "python3", "py"):
            out.append(sys.executable)
        else:
            out.append(t)
    return out


def _entry_of(argv: list[str]) -> tuple[str | None, str | None]:
    """这是不是一条本守卫能执行的 Python 命令？返回 (脚本路径|None, 跳过理由)。

    ★ 判据必须先看 **argv[0] 是不是解释器**，而不是"这行里有没有 .py"。
      第一版正是后者，于是 `grep -En '…' src/orchestrator.py` 被当成
      "Python 入口 src/orchestrator.py" 拿去执行，报出
      `FileNotFoundError: argv[0]='grep'` —— 一个**假报警**。
      假报警的代价不是噪音，是人开始不信报警。
    """
    if not argv or argv[0] != sys.executable:
        return None, "不是本项目的 Python 入口（shell 命令不在本守卫的判据内）"
    if len(argv) < 2:
        return None, "只有解释器、没有脚本"
    if argv[1] == "-m":
        if len(argv) < 3:
            return None, "`-m` 后面没有模块名"
        # 模块名映射到脚本路径，以应用相同的跳过规则。
        return argv[2].replace(".", "/") + ".py", None
    if not argv[1].endswith(".py"):
        return None, f"第一个参数不是 .py 脚本（{argv[1]!r}）"
    return argv[1].replace("\\", "/"), None


def _skip_reason(script: str, argv: list[str]) -> str | None:
    for pat, why in SKIP_RULES:
        if re.search(pat, script):
            return why
    if script == "app/server.py" and not {"--check", "--doctor", "--help"} & set(argv):
        return "常驻产品服务器由实际页面/网关验证覆盖，不在文档守卫中启动"
    return None


def _plan_command(ln: str) -> tuple[list[str] | None, str]:
    """保留文档命令的原参数，不代补可能改变执行含义的选项。"""
    argv = _to_argv(ln)
    script, why = _entry_of(argv)
    if script is None:
        return None, why or ""
    why = _skip_reason(script, argv)
    return (None, why) if why else (argv, "")


def _check_commands(rep: Report) -> None:
    """⑥ 受管文档 bash 围栏里的命令真跑，rc 必须 0。"""
    seen: dict[tuple[str, ...], list[str]] = {}
    skipped: list[tuple[str, str, str]] = []

    for path in MANAGED_HAND:
        rel = path.relative_to(ROOT).as_posix()
        for line_no, ln in _iter_bash_commands(path):
            argv, why = _plan_command(ln)
            if argv is None:
                skipped.append((rel, ln, why))
                continue
            key = tuple(argv)
            seen.setdefault(key, []).append(f"{rel}:{line_no}")

    for argv, where in seen.items():
        # 同一命令只执行一次，保留所有引用位置以便定位。
        try:
            p = subprocess.run(argv, cwd=str(ROOT), capture_output=True,
                               text=True, encoding="utf-8", timeout=240, errors="replace")
        except subprocess.TimeoutExpired:
            rep.problem(f"命令超时（>240s）：{' '.join(argv)}\n"
                        f"          出现在：{'、'.join(where)}")
            continue
        except OSError as exc:
            # "连启动都做不到"也是一种"跑不通"，而且它必须被报出来而不是把守卫炸掉 ——
            # 守卫自己崩了，就等于所有后续断言一起静默失效（那是最坏的一种绿）。
            rep.problem(f"命令无法启动（{type(exc).__name__}: {exc}）："
                        f"argv[0]={argv[0]!r}\n"
                        f"          出现在：{'、'.join(where)}")
            continue
        if p.returncode != 0:
            tail = (p.stderr or p.stdout or "").strip().splitlines()[-4:]
            rep.problem(
                f"命令退出码 {p.returncode}（应为 0）：{' '.join(argv)}\n"
                f"          出现在：{'、'.join(where)}\n"
                + "".join(f"          | {t}\n" for t in tail))

    rep.note(f"真跑了 {len(seen)} 条去重后的命令，跳过 {len(skipped)} 条"
             f"（各有理由，见 --explain）")
    for rel, ln, why in skipped:
        rep.det(f"跳过     {rel}  `{ln[:60]}` —— {why}")





def _check_readme_scope(rep: Report) -> None:
    """README 只描述当前实现，不复制执行状态和一次性检查数字。"""
    text = README.read_text(encoding="utf-8")
    forbidden = {
        r"^\s*(?:[-*>]\s*)?(?:next_action_task|下一任务|下一动作)\s*[：:]\s*`?"
        r"(?:V2\.[0-9A-Za-z.-]+|D[-0-9A-Za-z.]+)\b":
            "README 不得复制 state 的下一动作赋值",
        r"跑全套回归（\d+\s*项": "README 不得手抄会漂移的回归项数",
        # 退役的 README 数字/七坑位检查已删除。如需重新抄数字或引入该表，
        # 先恢复对应的直接比对检查，不能只恢复副本而不守。
        r"\d+\s*向植入对照": "README 不得手抄探针方向数：方向数由探针 `--count` 给出，"
                             "写进文档就得有守卫比对；"
                             "重新抄之前先恢复被删除的直接比对检查",
    }
    for pattern, message in forbidden.items():
        if re.search(pattern, text, re.M):
            rep.problem(message)



# ---------------------------------------------------------------- 文档登记

DOC_STATES = {
    "current": "当前有效：读者据此行事",
    "generated": "由脚本生成：说明列必须写明生成器",
    "draft": "设计草案、未进控制面：说明列必须写明生效条件",
    "superseded": "已被取代、保留为证据：说明列必须写明被谁取代",
    "to-delete": "待删：说明列必须写明删除前置条件",
}

DOC_KINDS = {
    "实现": "代码**当前真做什么**",
    "产品目标": "要做到什么、什么算完成",
    "执行状态": "当前推进到哪、下一步做什么",
    "项目规则": "Agent 与协作者必须遵守的工作规则（选型门禁、依赖登记）",
    "架构设计": "目标架构与技术选型",
    "设计草案": "未进控制面的设计前沿",
    "历史证据": "保留作证据，不据以行事",
    "生成产物": "由脚本生成，不手改",
    "待处置": "待删 / 待落点核对",
}

# 这三类事实各自只能有一个出处 —— 「政出一门」。
# 多一个出处不是更全，是**读者不知道该信谁**：本仓库真实并存过
# 「README 说 v2 是当前实现」与「v2 架构文档写着已被 v4 取代」——
# 它们其实回答的是不同的问题。写出管辖事实之后，那是分工；
# 而同一个问题上出现两个出处，就是这里要报的红。
SINGLETON_KINDS = ("实现", "产品目标", "执行状态", "项目规则")
CONTROL_STATUS_RE = re.compile(
    r"CONTROL-STATUS:\s*(current|generated|draft|superseded|to-delete)\b")

INDEX = ROOT / "docs" / "INDEX.md"
CURRENT_STATE = ROOT / "_working" / "amz-listing-kit-product-v2" / "state.md"


def _check_docs_index(rep: Report) -> None:
    """⑦ 仓库里每一份 Markdown 都必须在 docs/INDEX.md 里登记，且状态合法。

    为什么单独立这一项：上面六项全部是**单向**的（卡 vs 生成器、文档 vs 表、
    文档 vs 真算出来的值）。没有一项能发现「两份文档互相矛盾」—— 那不是一个
    "值不相等"的问题，是**哪一份有效**这个问题压根没有登记。
    本项补的就是那一维，形式是最朴素的**双向集合相等**。

    为什么状态必须是闭集合：本项目的腐化不是"信息丢失"，是**"哪份信息有效"
    没有登记**。自由文本（"基本过时"、"差不多可以删了"）无法被比对，
    于是下一次改动没有任何东西会响。
    """
    if not INDEX.exists():
        rep.problem("docs/INDEX.md 不存在 —— 它是文档权威登记表，"
                    "「哪份文档有效」这件事唯一的机器可读来源。"
                    "没有它，仓库里可以同时躺着三代文档而没人知道该信哪一份。")
        return

    text = INDEX.read_text(encoding="utf-8")
    declared: dict[str, tuple[str, str, str, str]] = {}
    for raw in text.splitlines():
        ln = raw.strip()
        if not ln.startswith("|") or not ln.endswith("|"):
            continue
        cells = [c.strip().strip("`").strip() for c in ln.strip("|").split("|")]
        if len(cells) != 5:
            continue
        path = cells[0]
        if not path.endswith(".md"):
            continue          # 表头行与 |---|---| 分隔行在这里被自然排除
        declared[path] = (cells[1], cells[2], cells[3], cells[4])

    # 受管范围：根目录 + docs/ + _working/。
    # 为什么把 _working/ 纳进来：它是**执行状态**的家，而"当前推进到哪"
    # 和"哪份文档有效"一样，是读者要据以行事的事实，不能没有权威登记。
    # 为什么 evals/ 不在内：那里放的是**产物**（探针输出、跑出来的报告），
    # 由各自的报告登记，不是"该信哪份"的候选。
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.glob("*.md")}
    for sub in ("docs", "_working"):
        d = ROOT / sub
        if d.exists():
            actual |= {p.relative_to(ROOT).as_posix() for p in d.rglob("*.md")}
    # Workspace export README files are user-facing business artifacts generated
    # by ExportVersion, not governance documents.  They live below _working only
    # because evaluation workspaces are retained there.  Registering every
    # immutable export would make the control index depend on runtime output.
    # gitignored 的本地历史（未跟踪）不进登记比对：登记表只管仓库里的文档；
    # 否则本地与 CI 看到不同文件集，同一份表两边互斥变红。
    try:
        import subprocess as _sp
        _out = _sp.run(["git", "-c", "core.quotepath=false", "ls-files", "-z",
                        "--", "*.md", "docs/*.md", "_working/*.md"],
                       capture_output=True, cwd=str(ROOT), timeout=30).stdout.decode("utf-8")
        _tracked = set(_out.split("\0")) - {""}
        if _tracked:
            actual &= _tracked
    except Exception:
        pass
    actual = {
        path for path in actual
        if not (path.startswith("_working/") and "/exports/" in path and path.endswith("/README.md"))
    }
    actual.discard("docs/INDEX.md")        # 登记表自己不需要被登记

    missing = sorted(actual - set(declared))
    ghost = sorted(set(declared) - actual)
    if missing:
        rep.problem("docs/INDEX.md 里没登记这几份 Markdown：" + "、".join(missing) +
                    " —— 新增文档要先登记、再写文件。"
                    "没登记的文档 = 没有权威状态的文档，而『读者该不该信它』"
                    "正是这张表要回答的事。")
    if ghost:
        rep.problem("docs/INDEX.md 登记了、但文件根本不在这几份：" + "、".join(ghost) +
                    " —— 登记表比仓库多出了条目，它开始说谎了。")

    by_kind: dict[str, list[str]] = {}
    for path, (_gen, kind, state, note) in sorted(declared.items()):
        if kind not in DOC_KINDS:
            rep.problem(f"docs/INDEX.md 里 {path} 的管辖事实 {kind!r} 不是闭集合里的一个，"
                        f"可选：{'/'.join(DOC_KINDS)}。"
                        f"这一列回答「这份文件对哪一类事实有权威」——"
                        f"没有它，『哪一份该信』只能靠人脑子拼。")
        else:
            by_kind.setdefault(kind, []).append(path)
        if state not in DOC_STATES:
            rep.problem(f"docs/INDEX.md 里 {path} 的状态 {state!r} 不在取值域，"
                        f"可选：{'/'.join(DOC_STATES)}。"
                        f"状态必须是枚举 —— 自由文本没法被机器比对，"
                        f"也就没法在下次改动时响。")
        if not note:
            rep.problem(f"docs/INDEX.md 里 {path} 的说明列为空 —— 状态是 {state!r} 时，"
                        f"说明必须写明「{DOC_STATES.get(state, '为什么是这个状态')}」。")
#      `docs/standards-template/**` 是**外部课程模板的原样副本**，会被整目录重新同步：
#      给它加我们的 CONTROL-STATUS 会让下一次同步丢标记，也会把一份参考模板伪装成项目文档。
#      它的身份与状态只由 INDEX 这一处登记；被本项目采纳的结论写进 AGENTS.md 的 Standards Mapping。
        imported_reference = path.startswith("docs/standards-template/")
        if path in actual and state != "generated" and not imported_reference:
            head = "\n".join((ROOT / path).read_text(encoding="utf-8").splitlines()[:12])
            marker = CONTROL_STATUS_RE.search(head)
            if not marker:
                rep.problem(f"{path} 顶部 12 行没有 CONTROL-STATUS —— 单看文件无法知道"
                            "它是否仍有权威；状态不能只藏在 INDEX。")
            elif marker.group(1) != state:
                rep.problem(f"{path} 的 CONTROL-STATUS={marker.group(1)!r}，"
                            f"INDEX 登记为 {state!r} —— 两处身份不一致。")

    for kind in SINGLETON_KINDS:
        owners = by_kind.get(kind, [])
        if len(owners) > 1:
            rep.problem(f"管辖事实「{kind}」有 {len(owners)} 个出处：" + "、".join(owners) +
                        " —— 这一类事实只能有一个权威（政出一门）。"
                        "多出来的那份要么换成别的归类，要么降为"
                        "superseded / draft —— 不能两份都 current。")
        elif not owners:
            rep.problem(f"管辖事实「{kind}」在登记表里没有任何出处 —— "
                        f"「{DOC_KINDS[kind]}」这件事目前没有权威文件，"
                        f"读者只能自己拼。先登记一份，再往下走。")

    # 任务结束后，施工任务书仍标 draft 会邀请后来者再次执行。任务身份只从 INDEX 的
    # 世代列读取，任务状态只从 current state 读取，不另建第三张映射表。
    task_statuses: dict[str, str] = {}
    if CURRENT_STATE.exists():
        state_text = CURRENT_STATE.read_text(encoding="utf-8")
        task_statuses = dict(re.findall(
            r"(?m)^  (V2(?:\.[0-9A-Za-z-]+)+):\r?\n    status: ([a-z]+)$",
            state_text,
        ))
    for path, (generation, _kind, state, _note) in sorted(declared.items()):
        if not path.startswith("_working/amz-listing-kit-product-v2/tasks/"):
            continue
        task_match = re.search(r"\b(V2(?:\.[0-9A-Za-z-]+)+)\b", generation)
        if not task_match:
            continue
        task_id = task_match.group(1)
        if task_statuses.get(task_id) in {"done", "dropped", "superseded"} and state == "draft":
            rep.problem(f"任务书身份漂移：{task_id} 在 current state 已是 "
                        f"{task_statuses[task_id]!r}，但 {path} 仍登记为 draft —— "
                        "完成后的施工指令必须转 superseded，不能继续邀请执行。")

    counts = "、".join(f"{k} {len(v)}" for k, v in sorted(by_kind.items()))
    rep.note(f"文档登记：已登记 {len(declared)} 份，仓库里实际 {len(actual)} 份"
             f"（{counts}）")


# ------------------------------------------- 受管文档不得写死解释器路径

# ------------------------------------------- 选型门禁与依赖登记
#
# 为什么单独立这一项：文档守卫前八项管的是「文档里的话对不对」和「哪份文档有效」，
# 没有一项管「实现之前有没有先找过现成能力」。而这个仓库真实发生过：语义适配器
# 先手写了几百行传输与错误分类，之后才有人问『为什么不用现成库』。
# 句子拦不住这件事，只有登记 + 双向比对能拦住：新增依赖必须同时改
# pyproject.toml（uv add 落锁）与项目上下文的依赖登记表，少一处就报红。

AGENTS_FILE = ROOT / "AGENTS.md"
PYPROJECT_FILE = ROOT / "pyproject.toml"
UV_LOCK_FILE = ROOT / "uv.lock"
CONTEXT_FILE = ROOT / "docs" / "product-v2-project-context.md"
# vendor 单文件库分两类：产品运行时（app/…）与测试/评估侧（evals/…）。
# 两边都进同一个登记表，文件集合与 §4.2 双向比对。
VENDOR_DIRS = (
    ROOT / "app" / "product_v2" / "vendor",
    ROOT / "evals" / "product-v2" / "vendor",
)

REUSE_BEGIN = "<!-- reuse-first:begin -->"
REUSE_END = "<!-- reuse-first:end -->"
DEP_BEGIN = "<!-- dependency-registry:begin -->"
DEP_END = "<!-- dependency-registry:end -->"
VENDOR_BEGIN = "<!-- vendor-registry:begin -->"
VENDOR_END = "<!-- vendor-registry:end -->"

# 依赖权威是 pyproject.toml + uv.lock（SEL-000 修订，2026-09-30）。`uv init` 的 main.py
# 脚手架既不是业务代码也不该留在根目录；出现就报红，而不是加进 .gitignore 盖住。
STRAY_PROJECT_FILES = ("main.py",)

REUSE_REQUIRED_TOKENS = (
    "复用 > 配置 > 集成 > 扩展 > 自研",
    "选型报告",
    "选型四问",
    "禁止自造",
    "复访条件",
    "uv add",
)


def _norm_pkg(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def _direct_pins() -> dict[str, tuple[str, str]]:
    """pyproject.toml 直接依赖 {包: (锁定版本, 分组)}；未锁版本记作 ""。"""
    import tomllib

    pins: dict[str, tuple[str, str]] = {}
    if not PYPROJECT_FILE.exists():
        return pins
    try:
        doc = tomllib.loads(PYPROJECT_FILE.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return pins
    project = doc.get("project") or {}

    def _add(spec: object, group: str) -> None:
        text = str(spec).strip()
        name = re.split(r"[<>=!~\[\s;]", text, maxsplit=1)[0]
        if not name:
            return
        match = re.search(r"==\s*([^\s,;]+)", text)
        pins[_norm_pkg(name)] = (match.group(1) if match else "", group)

    for spec in project.get("dependencies") or []:
        _add(spec, "runtime")
    for group, specs in (project.get("optional-dependencies") or {}).items():
        for spec in specs or []:
            _add(spec, f"optional:{group}")
    for group, specs in (doc.get("dependency-groups") or {}).items():
        for spec in specs or []:
            if isinstance(spec, str):
                _add(spec, f"group:{group}")
    return pins


def _locked_pins() -> dict[str, str]:
    """uv.lock 的 {包: 版本}（全部解析结果）；文件缺失或坏掉时返回空表。"""
    import tomllib

    pins: dict[str, str] = {}
    if not UV_LOCK_FILE.exists():
        return pins
    try:
        doc = tomllib.loads(UV_LOCK_FILE.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return pins
    for pkg in doc.get("package") or []:
        name = str(pkg.get("name") or "").strip()
        if name:
            pins[_norm_pkg(name)] = str(pkg.get("version") or "").strip()
    return pins


def _marked_rows(text: str, begin: str, end: str) -> list[list[str]] | None:
    """取出标记块里的 Markdown 表格行（跳过表头与分隔行）；没有标记块返回 None。"""
    if begin not in text or end not in text:
        return None
    block = text.split(begin, 1)[1].split(end, 1)[0]
    rows: list[list[str]] = []
    for raw in block.splitlines():
        ln = raw.strip()
        if not ln.startswith("|") or not ln.endswith("|"):
            continue
        cells = [c.strip().strip("`").strip() for c in ln.strip("|").split("|")]
        if cells and all(set(c) <= set("-: ") for c in cells):
            continue
        rows.append(cells)
    return rows[1:] if rows else []


def _check_frontend_dependencies(rep: Report, context: str) -> None:
    """前端开发依赖只有根 manifest/lock/登记一份权威，不进入产品目录。"""
    try:
        manifest = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
        product_manifest = json.loads(
            (ROOT / "app/product_v2/package.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        rep.problem(f"前端依赖 manifest/lock 不可读：{exc}")
        return
    if any(not isinstance(value, dict) for value in (manifest, lock, product_manifest)):
        rep.problem("前端工具 manifest/lock 与产品 ESM manifest 顶层必须是对象")
        return
    direct = manifest.get("devDependencies")
    packages = lock.get("packages")
    if not isinstance(direct, dict) or not isinstance(packages, dict):
        rep.problem("前端依赖 devDependencies/lock.packages 必须是对象")
        return
    full_direct = dict(direct)
    for runtime_name in ("lit-html", "@types/trusted-types"):
        runtime_record = packages.get("node_modules/" + runtime_name)
        if isinstance(runtime_record, dict) and isinstance(runtime_record.get("version"), str):
            full_direct[runtime_name] = runtime_record["version"]
    if manifest.get("private") is not True or any(
            manifest.get(key) for key in ("optionalDependencies", "peerDependencies")):
        rep.problem("前端工具 manifest 必须 private，不得有可选/同级依赖")
    runtime_declared = {name: version for name, version in manifest.get("dependencies", {}).items()
        if name in ("lit-html",)}
    if runtime_declared != {"lit-html": full_direct.get("lit-html")}:
        rep.problem("前端生产运行依赖只允许已登记的 lit-html 精确版本")
    rows = _marked_rows(context, "<!-- frontend-dependency-registry:begin -->",
                        "<!-- frontend-dependency-registry:end -->")
    if rows is None:
        rep.problem("项目上下文缺少 frontend-dependency-registry 登记")
        return
    declared = {row[0]: (row[1], row[2]) for row in rows if len(row) >= 3}
    locked = {}
    for path, record in packages.items():
        if not path:
            continue
        if not path.startswith("node_modules/") or not isinstance(record, dict):
            rep.problem(f"前端依赖锁存在未支持的包记录：{path}")
            continue
        name = path.removeprefix("node_modules/")
        locked[name] = (record.get("version"), record.get("license"))
        if name in ("lit-html", "@types/trusted-types"):
            if (not record.get("integrity")
                    or not str(record.get("resolved", "")).startswith("https://")):
                rep.problem(f"前端依赖 {name} 缺HTTPS 来源或完整性指纹")
        elif (record.get("dev") is not True or not record.get("integrity")
                or not str(record.get("resolved", "")).startswith("https://")):
            rep.problem(f"前端依赖 {name} 缺开发范围、HTTPS 来源或完整性指纹")
    # 登记表要覆盖完整锁闭包（直接 dev 依赖、生产运行依赖 + 其全部传递依赖）；
    # manifest 的直接声明仍是唯一口径：dev 走 devDependencies，lit-html 走 dependencies。
    if declared.keys() != locked.keys():
        rep.problem("前端依赖登记/锁 name 集合不一致："
                    + "、".join(sorted(set(declared) ^ set(locked))))
    if any(declared[name] != locked.get(name) for name in declared if name in locked):
        rep.problem("前端依赖登记版本/许可与锁不一致")
    if any(not re.fullmatch(r"\d+\.\d+\.\d+", str(version))
           or version != declared.get(name, (None, None))[0] for name, version in full_direct.items()):
        rep.problem("前端直接依赖必须与登记一致且锁定精确版本")
    root = packages.get("")
    if not isinstance(root, dict) or root.get("devDependencies") != direct:
        rep.problem("前端依赖 lock 根声明与 manifest 不一致")
    elif root.get("dependencies", {}) != manifest.get("dependencies", {}):
        rep.problem("前端生产运行依赖 lock 根声明与 manifest 不一致")
    elif root.get("engines") != manifest.get("engines"):
        rep.problem("前端 Node/npm 版本在 manifest 与 lock 不一致")
    if any(product_manifest.get(key) for key in ("dependencies", "devDependencies")):
        rep.problem("产品 ESM manifest 不得建立第二份前端依赖权威")
    rep.note(f"前端直接依赖：manifest/lock/登记 {len(full_direct)} 包")


def _check_reuse_first_gate(rep: Report) -> None:
    """⑨ 选型门禁有落点、依赖有登记，且登记表与 pyproject.toml + uv.lock / vendor 双向一致。"""
    for name in STRAY_PROJECT_FILES:
        if (ROOT / name).exists():
            rep.problem(f"根目录出现 {name} —— 这属于 `uv init` 脚手架残留；"
                        "依赖权威是 pyproject.toml + uv.lock（SEL-000），脚手架文件直接删掉。")
    if not AGENTS_FILE.exists():
        rep.problem("AGENTS.md 不存在 —— 选型门禁（Reuse-first）没有任何仓库级落点，"
                    "下一个 Agent 会继续『需求 → 直接实现』。")
    else:
        agents = AGENTS_FILE.read_text(encoding="utf-8")
        if REUSE_BEGIN not in agents or REUSE_END not in agents:
            rep.problem("AGENTS.md 缺少 reuse-first 标记块（" + REUSE_BEGIN + " / "
                        + REUSE_END + "）—— 门禁正文必须可被机器定位。")
        else:
            block = agents.split(REUSE_BEGIN, 1)[1].split(REUSE_END, 1)[0]
            for token in REUSE_REQUIRED_TOKENS:
                if token not in block:
                    rep.problem(f"AGENTS.md 的选型门禁缺少必需内容：{token!r} —— "
                                "门禁被删成一句话就不再是门禁；必需内容只认复用阶梯标记块内部，"
                                "正文别处提到不算。")

    if not CONTEXT_FILE.exists():
        rep.problem("docs/product-v2-project-context.md 不存在 —— 选型决策与依赖登记"
                    "没有权威落点。")
        return
    context = CONTEXT_FILE.read_text(encoding="utf-8")

    if not PYPROJECT_FILE.exists() or not UV_LOCK_FILE.exists():
        rep.problem("缺少 pyproject.toml 或 uv.lock —— 依赖权威文件必须同时在位"
                    "（SEL-000 修订：pyproject.toml + uv.lock）。")
    else:
        direct = _direct_pins()
        locked = _locked_pins()
        unpinned = sorted(name for name, (version, _group) in direct.items() if not version)
        if unpinned:
            rep.problem("pyproject.toml 里这些直接依赖没有锁定版本（必须 == 精确版本）："
                        + "、".join(unpinned))
        unlocated = sorted(name for name in direct if name not in locked)
        if unlocated:
            rep.problem("pyproject.toml 里这些直接依赖在 uv.lock 中没有解析结果："
                        + "、".join(unlocated) + " —— 跑 `uv lock` 再提交。")
        drift = sorted(name for name in direct
                       if direct[name][0] and direct[name][0] != locked.get(name))
        if drift:
            detail = "、".join(f"{name}：pyproject {direct[name][0]} / uv.lock "
                               f"{locked.get(name) or '缺失'}" for name in drift)
            rep.problem("直接依赖版本与 uv.lock 不一致（" + detail + "）—— 跑 `uv lock`。")
        dep_rows = _marked_rows(context, DEP_BEGIN, DEP_END)
        if dep_rows is None:
            rep.problem("项目上下文缺少 dependency-registry 登记块（" + DEP_BEGIN + " / "
                        + DEP_END + "）—— 新增依赖就没有第二个地方需要改，也就没有门。")
        else:
            declared_pins = {
                _norm_pkg(row[0]): (row[1].strip() if len(row) > 1 else "")
                for row in dep_rows if row and row[0]
            }
            missing = sorted(set(direct) - set(declared_pins))
            ghost = sorted(name for name in declared_pins if name not in locked)
            if missing:
                rep.problem("pyproject.toml 里这些直接依赖没登记进项目上下文 §4.2："
                            + "、".join(missing)
                            + " —— 引入依赖要先写选型报告与登记，再 uv add。")
            if ghost:
                rep.problem("登记表里这些包不在 uv.lock 解析结果里：" + "、".join(ghost)
                            + " —— 登记表开始说谎了（依赖被移除时要同时删登记）。")
            mismatch = sorted(name for name in set(declared_pins) & set(locked)
                              if declared_pins[name] != locked[name])
            if mismatch:
                detail = "、".join(f"{name}：登记 {declared_pins[name] or '空'} / uv.lock "
                                   f"{locked[name] or '未锁'}" for name in mismatch)
                rep.problem("依赖版本与 uv.lock 不一致（" + detail + "）—— 跑 `uv lock` 或改登记。")
            direct_mismatch = sorted(name for name in set(declared_pins) & set(direct)
                                     if declared_pins[name] != direct[name][0])
            if direct_mismatch:
                rep.problem("登记版本与 pyproject.toml 直接依赖不一致："
                            + "、".join(direct_mismatch))
            locked_count = len(direct) - len(unpinned)
            rep.note(f"依赖登记：pyproject 直接依赖 {len(direct)} 个（锁定 {locked_count}）"
                     f"↔ uv.lock {len(locked)} 包 ↔ 登记表 {len(declared_pins)} 行")
    _check_frontend_dependencies(rep, context)

    vendor_rows = _marked_rows(context, VENDOR_BEGIN, VENDOR_END)
    vendor_actual: set[str] = set()
    for vendor_dir in VENDOR_DIRS:
        if vendor_dir.exists():
            vendor_actual |= {p.name for p in vendor_dir.glob("*") if p.is_file()}
    if vendor_rows is None:
        rep.problem("项目上下文缺少 vendor-registry 登记块（" + VENDOR_BEGIN + " / "
                    + VENDOR_END + "）—— 浏览器端引入第三方库就没有登记处。")
    else:
        vendor_set = {row[0] for row in vendor_rows if row and row[0]}
        missing_vendor = sorted(vendor_actual - vendor_set)
        ghost_vendor = sorted(vendor_set - vendor_actual)
        if missing_vendor:
            rep.problem("vendor 目录（app/product_v2/vendor/、evals/product-v2/vendor/）里"
                        "这些文件没有登记：" + "、".join(missing_vendor))
        if ghost_vendor:
            rep.problem("vendor 登记了、目录里却没有这些文件：" + "、".join(ghost_vendor))

ABS_INTERP = re.compile(r"[A-Za-z]:[\\/][^\s\"'`|<>]*pythonw?\.exe", re.I)


def _check_no_abs_interpreter(rep: Report) -> None:
    """⑧ 受管文档里不得出现写死的解释器绝对路径。

    为什么单列一项：这条不是"风格偏好"，是**换台机器就废**。README 曾经写着

        PY="C:/Users/31368/.workbuddy/binaries/python/envs/default/Scripts/python.exe"

    —— 那是**开发机的一次快照**，被放在「怎么跑」的位置上，读者会以为那就是
    运行方式。对「2–5 名运营人员独立使用」这个目标来说，这一行等于装不上。

    只认带盘符的 `python.exe` / `pythonw.exe`：正文里说清某个目录放什么
    （例如 .env.example 的 REMBG_MODEL_DIR）是合法的 —— 它不负责启动进程。
    """
    for path in MANAGED_HAND:
        rel = path.relative_to(ROOT).as_posix()
        for i, ln in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            m = ABS_INTERP.search(ln)
            if m:
                rep.problem(f"{rel}:{i} 写着解释器的绝对路径 {m.group(0)!r} —— "
                            f"那是开发机的快照，换台机器就废。改成相对路径"
                            f"（例如 PY=.venv/Scripts/python.exe），"
                            f"准备动作放 text 围栏。")


# ---------------------------------------------------------------- ⑩ 模板映射

STANDARDS_DIR = ROOT / "docs" / "standards-template"
STANDARDS_SECTION_RE = re.compile(
    r"^## Standards Mapping \(standards-template\)\s*$(.*?)^## ", re.S | re.M)


def _check_standards_mapping(rep: Report) -> None:
    """⑩ 外部模板的每份文件都必须在 AGENTS.md 的采纳映射里有落点。

    为什么单列：`docs/standards-template/` 会被整目录重新同步（07 就是后加的
    一份）。模板新增规范而映射表没跟上时，「已按模板适配」这句话无从证伪 ——
    本项把它变成双向可比对的事实：模板多一份、映射少一行，直接报红。
    只做存在性比对（文件名必须出现在映射章节里），不解析落点列：宁可粗，
    也不能沉默。
    """
    if not STANDARDS_DIR.exists():
        rep.problem("docs/standards-template/ 不存在 —— 采纳映射失去比对对象；"
                    "模板被移动或删除时，必须同步本项与 AGENTS.md 的映射章节。")
        return
    text = AGENTS_FILE.read_text(encoding="utf-8") if AGENTS_FILE.exists() else ""
    m = STANDARDS_SECTION_RE.search(text)
    if not m:
        rep.problem("AGENTS.md 缺少 `## Standards Mapping (standards-template)` 章节"
                    "（或它后面没有下一个 `##` 标题）—— 模板的采纳判定没有机器可定位的落点。")
        return
    section = m.group(1)
    files = sorted(STANDARDS_DIR.rglob("*.md"))
    unmapped = [p.relative_to(STANDARDS_DIR).as_posix() for p in files if p.name not in section]
    if unmapped:
        rep.problem("docs/standards-template/ 里这些文件没有在 AGENTS.md 的映射章节出现："
                    + "、".join(unmapped) + " —— 模板新增/改名后，采纳映射必须补行；"
                    "否则「照着模板做」这句话没有任何东西能证伪。")
    rep.note(f"模板映射：standards-template {len(files)} 份，映射章节覆盖 "
             f"{len(files) - len(unmapped)} 份")


# ---------------------------------------------------------------- 入口

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="文档守卫：让文档里的话有人守")
    ap.add_argument("--no-run", action="store_true",
                    help="跳过命令执行（快，但会明说哪些断言没被验）")
    ap.add_argument("--explain", action="store_true",
                    help="把补过参数的命令、被跳过的命令与理由也打印出来")
    ap.add_argument("--root", type=Path, default=CODE_ROOT,
                    help="只读被验项目根；反向探针使用独立临时副本")
    args = ap.parse_args(argv)
    global ROOT, README, MANAGED_HAND
    global INDEX, CURRENT_STATE, AGENTS_FILE, PYPROJECT_FILE, UV_LOCK_FILE
    global CONTEXT_FILE, VENDOR_DIRS, STANDARDS_DIR
    ROOT = args.root.resolve()
    README = ROOT / "README.md"
    MANAGED_HAND = [README]
    INDEX = ROOT / "docs" / "INDEX.md"
    CURRENT_STATE = ROOT / "_working" / "amz-listing-kit-product-v2" / "state.md"
    AGENTS_FILE = ROOT / "AGENTS.md"
    PYPROJECT_FILE = ROOT / "pyproject.toml"
    UV_LOCK_FILE = ROOT / "uv.lock"
    CONTEXT_FILE = ROOT / "docs" / "product-v2-project-context.md"
    VENDOR_DIRS = (ROOT / "app/product_v2/vendor", ROOT / "evals/product-v2/vendor")
    STANDARDS_DIR = ROOT / "docs" / "standards-template"

    rep = Report()
    _check_readme_scope(rep)
    _check_docs_index(rep)
    _check_reuse_first_gate(rep)
    _check_standards_mapping(rep)
    _check_no_abs_interpreter(rep)
    if not args.no_run:
        _check_commands(rep)

    print("=" * 72)
    print("文档守卫")
    print("=" * 72)
    print("受管：README.md（当前实现边界与命令）")
    print("　　　+ 文档权威登记（docs/INDEX.md：双向比对 + 管辖事实唯一）"
          "—— 回答「哪一份有效」和「哪一类事实归谁」")
    print("　　　+ 选型门禁（AGENTS.md ↔ 项目上下文 §4 依赖/vendor 登记）"
          "—— 回答「实现之前先找过现成能力没有」")
    print("　　　+ 模板映射（AGENTS.md §Standards Mapping ↔ docs/standards-template/）"
          "—— 回答「外部模板的每份规范有没有采纳落点」")
    print()

    for n in rep.notes:
        print(f"  · {n}")
    if args.explain:
        for d in rep.detail:
            print(f"  {d}")

    if rep.problems:
        print(f"\nproblems（{len(rep.problems)} 条）：")
        for s in rep.problems:
            print(f"  ✗ {s}")

    if args.no_run:
        print("\n注意：本次 --no-run，**命令执行未被验证** —— 文档里的命令这次没被真跑过，"
              "别把它当成『命令没问题』的证明。")

    print()
    if rep.problems:
        print("结果：有 problems（退出码 1）。")
        return 1
    print("结果：全过（退出码 0）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
