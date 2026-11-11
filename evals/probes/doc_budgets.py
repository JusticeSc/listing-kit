#!/usr/bin/env python3
"""NOT-AUTHORITY：在隔离 Git 仓库通过真实 CLI 验证文档字节预算。

不读写实际 index、文档或用户 Git 配置；--count 仅列出对照数。
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Callable

CODE_ROOT = Path(__file__).resolve().parents[2]
GUARD = CODE_ROOT / "tools" / "check_doc_budgets.py"
SCRIPT = "tools/check_doc_budgets.py"


@dataclass(frozen=True)
class Case:
    name: str
    change: Callable[[Path], None] | None = None
    expected: int = 0
    must: tuple[str, ...] = ()
    must_not: tuple[str, ...] = ()
    script: str = SCRIPT


def _environment(root: Path) -> dict[str, str]:
    environment = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    environment.update({
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TEMPLATE_DIR": str(root / "empty-hooks"), "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1",
    })
    return environment


def _git(root: Path, *arguments: str, payload: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=false", "-c", f"core.hooksPath={root / 'empty-hooks'}",
         "-c", "user.name=Document budget probe", "-c", "user.email=doc-budget-probe@example.invalid",
         *arguments], cwd=root, env=_environment(root), input=payload,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"夹具 Git {arguments!r} → rc={result.returncode}: "
                           + (result.stdout + result.stderr).decode("utf-8", "replace"))
    return result.stdout


def _put(root: Path, relative: str, payload: bytes) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def _fixture(root: Path) -> None:
    root.mkdir()
    (root / "empty-hooks").mkdir()
    _put(root, SCRIPT, GUARD.read_bytes())
    _put(root, "README.md", b"x" * 10_000)
    _put(root, ".gitignore", b"ignored/\n")
    _git(root, "init", "--quiet")
    _git(root, "add", "--", "README.md", ".gitignore")


def _indexed_large(root: Path, *, keep: bool = True) -> None:
    _put(root, "README.md", b"x" * 10_001)
    _git(root, "add", "--", "README.md")
    if keep:
        _put(root, "README.md", b"x" * 10_000)
    else:
        (root / "README.md").unlink()


def _ignored_tracked(root: Path) -> None:
    _put(root, "ignored/still-managed.md", b"x" * 10_001)
    _git(root, "add", "-f", "--", "ignored/still-managed.md")


def _dependency_files(root: Path) -> None:
    paths = ("node_modules/pkg/README.md", ".venv/Lib/README", "venv/share/manual.pdf")
    for relative in paths:
        _put(root, relative, b"x" * 10_001)
    _git(root, "add", "--", *paths)


def _machine_files(root: Path) -> None:
    for relative in ("config/data.json", "config/data.jsonl", "state.yaml", "state.yml", "code.py",
                     "app/interface.html", "report.htm", "package-lock.json"):
        _put(root, relative, b"x" * 10_001)
    _git(root, "add", "--", "config", "state.yaml", "state.yml", "code.py", "app", "report.htm", "package-lock.json")


def _directories(root: Path) -> None:
    for relative in ("docs/archived/manual.md", "_working/state.md", "evals/evidence/report.txt",
                     "_stage-amz-control/evidence.out", ".agents/skills/probe/SKILL.md", "vendor/guide.rst"):
        _put(root, relative, b"x" * 10_001)


def _declarations(root: Path) -> None:
    for index, declaration in enumerate((b"CONTROL-STATUS: superseded\n", b"NOT-AUTHORITY\n",
                                         b"<!-- doc-budget: exempt -->\n", b"status: archived\n")):
        _put(root, f"docs/declaration-{index}.md", declaration + b"x" * (10_001 - len(declaration)))


def _skip_worktree(root: Path) -> None:
    relative = "docs/not-present.md"
    _put(root, relative, b"x" * 10_001)
    _git(root, "add", "--", relative)
    _git(root, "update-index", "--skip-worktree", "--", relative)
    (root / relative).unlink()


def _assume_unchanged(root: Path) -> None:
    _git(root, "update-index", "--assume-unchanged", "--", "README.md")
    _put(root, "README.md", b"x" * 10_001)


def _staged_deletion(root: Path) -> None:
    _git(root, "rm", "--cached", "--", "README.md")
    _put(root, "README.md", b"x" * 10_001)


def _unmerged(root: Path) -> None:
    short = _git(root, "hash-object", "-w", "--stdin", payload=b"short\n").strip()
    long = _git(root, "hash-object", "-w", "--stdin", payload=b"x" * 10_001).strip()
    records = b"".join(b"100644 " + oid + f" {stage}\tconflict.md\n".encode("ascii")
                       for stage, oid in ((1, short), (2, long), (3, short)))
    _git(root, "update-index", "--add", "--index-info", payload=records)


def _sparse(root: Path, size: int) -> None:
    _put(root, "hidden/sparse.md", b"x" * size)
    _put(root, "visible/keep.py", b"pass\n")
    _git(root, "add", "--", "hidden", "visible")
    _git(root, "commit", "--quiet", "--no-gpg-sign", "-m", "Sparse document fixture")
    _git(root, "sparse-checkout", "init", "--cone", "--sparse-index")
    _git(root, "sparse-checkout", "set", "visible")
    if (root / "hidden" / "sparse.md").exists() or b"040000 " not in _git(root, "ls-files", "--stage", "--sparse", "-z"):
        raise RuntimeError("夹具没有形成磁盘缺席的稀疏 index 目录对象")


def _bad_blob(root: Path, corrupt: bool = False) -> None:
    oid = _git(root, "rev-parse", ":README.md").strip().decode("ascii")
    target = root / ".git" / "objects" / oid[:2] / oid[2:]
    target.chmod(0o666)
    if corrupt:
        target.write_bytes(b"not a Git object\n")
    else:
        target.unlink()

def _remove_readonly(func: Callable[[str], None], path: str, _exc_info: object) -> None:
    """让 Windows 临时 Git 对象在夹具清理时可删除。"""
    os.chmod(path, 0o777)
    func(path)

def _nested_root(root: Path) -> None:
    _put(root, "nested/" + SCRIPT, GUARD.read_bytes())


def _embedded_repository(root: Path) -> None:
    target = root / "embedded"
    target.mkdir()
    _git(target, "init", "--quiet")
    _put(target, "README.md", b"x" * 10_001)


def _cases() -> list[Case]:
    ok = ("均不超过 10000 字节",)
    cases = [
        Case("恰好 10000 原始字节", must=ok),
        Case("工作树 10001、index 10000", lambda root: _put(root, "README.md", b"x" * 10_001), 1,
             ("README.md: 工作树 10001 字节超过 10000 上限",), ("index(stage 0) 10001",)),
        Case("index 10001、工作树 10000", _indexed_large, 1,
             ("README.md: index(stage 0) 10001 字节超过 10000 上限",), ("工作树 10001",)),
        Case("工作树缺席仍检查 index", lambda root: _indexed_large(root, keep=False), 1,
             ("README.md: index(stage 0) 10001 字节超过 10000 上限",)),
        Case("未跟踪新增文档", lambda root: _put(root, "new.md", b"x" * 10_001), 1,
             ("new.md: 工作树 10001 字节超过 10000 上限",)),
        Case("忽略的新文件不入项目", lambda root: _put(root, "ignored/local.md", b"x" * 10_001), must=ok),
        Case("跟踪文件不受忽略规则豁免", _ignored_tracked, 1,
             ("ignored/still-managed.md: index(stage 0) 10001", "ignored/still-managed.md: 工作树 10001")),
        Case("依赖文档不计入项目文档", _dependency_files, must=ok),
        Case("机器数据与非 docs HTML 不计作文档", _machine_files, must=ok),
        Case("归档、规则、证据与 vendor 无目录豁免", _directories, 1,
             tuple(f"{path}: 工作树 10001" for path in (
                 "docs/archived/manual.md", "_working/state.md", "evals/evidence/report.txt",
                 "_stage-amz-control/evidence.out", ".agents/skills/probe/SKILL.md", "vendor/guide.rst"))),
        Case("文内状态与豁免声明均无效", _declarations, 1,
             tuple(f"docs/declaration-{number}.md: 工作树 10001" for number in range(4))),
        Case("skip-worktree 不隐藏 index 超限", _skip_worktree, 1,
             ("docs/not-present.md: index(stage 0) 10001",)),
        Case("assume-unchanged 不隐藏工作树超限", _assume_unchanged, 1,
             ("README.md: 工作树 10001",)),
        Case("暂存删除后仍检查现存未忽略文档", _staged_deletion, 1,
             ("README.md: 工作树 10001",), ("README.md: index",)),
        Case("未合并的各 index stage 都检查", _unmerged, 1,
             ("conflict.md: index(stage 2) 10001",)),
        Case("稀疏 index 中 10000 字节有效", lambda root: _sparse(root, 10_000), must=ok),
        Case("稀疏目录中的 10001 字节拒绝", lambda root: _sparse(root, 10_001), 1,
             ("hidden/sparse.md: index(stage 0) 10001",), ("hidden/sparse.md: 工作树",)),
        Case("损坏 index 拒绝", lambda root: _put(root, ".git/index", b"invalid index\n"), 1,
             ("Git index 无法读取",)),
        Case("缺失 index blob 拒绝", _bad_blob, 1, ("index/blob 无法读取",)),
        Case("损坏 index blob 拒绝", lambda root: _bad_blob(root, True), 1, ("index/blob 无法读取",)),
        Case("非 Git 根拒绝", lambda root: shutil.rmtree(root / ".git", onerror=_remove_readonly), 1, ("无法确定真实 Git 根",)),
        Case("嵌套脚本目录不能冒用祖先 Git 根", _nested_root, 1, ("真实 Git 根不匹配",),
             script="nested/" + SCRIPT),
        Case("嵌入的 Git 仓库不能隐藏文档", _embedded_repository, 1, ("嵌套 Git 仓库",)),
        Case("多字节字符按字节计、10000 有效", lambda root: _put(root, "README.md", "界".encode("utf-8") * 3333 + b"x"), must=ok),
        Case("多字节字符的 10001 字节拒绝", lambda root: _put(root, "README.md", "界".encode("utf-8") * 3333 + b"xx"), 1,
             ("README.md: 工作树 10001",)),
        Case("CRLF 按原始 10000 字节计", lambda root: _put(root, "README.md", b"x\r\n" * 3333 + b"x"), must=ok),
        Case("CRLF 不归一化为更短字节", lambda root: _put(root, "README.md", b"x\r\n" * 3333 + b"xx"), 1,
             ("README.md: 工作树 10001",)),
        Case("二进制文档同样受预算限制", lambda root: _put(root, "docs/binary.pdf", b"\0" * 10_001), 1,
             ("docs/binary.pdf: 工作树 10001",)),
        Case("带空格与中日韩字符的文档路径", lambda root: _put(root, "docs/空 格 记录.md", b"x" * 10_001), 1,
             ("docs/空 格 记录.md: 工作树 10001",)),
    ]
    # 扩展名期望来自任务合同，不能从受测守卫导入分类器。
    suffixes = ("md", "mdx", "markdown", "mdown", "mkd", "rst", "adoc", "asciidoc", "org", "tex", "rtf",
                "txt", "text", "log", "out", "pdf", "doc", "docx", "odt", "ppt", "pptx", "odp")
    for suffix in suffixes:
        relative = f"extension/document.{suffix.upper()}"
        cases.append(Case(f"扩展名 .{suffix} 大小写不敏感", lambda root, path=relative: _put(root, path, b"x" * 10_001),
                          1, (f"{relative}: 工作树 10001",)))
    for name in ("README", "LICENSE", "NOTICE", "COPYING"):
        relative = "nested/" + name.lower()
        cases.append(Case(f"无扩展名 {name}", lambda root, path=relative: _put(root, path, b"x" * 10_001),
                          1, (f"{relative}: 工作树 10001",)))
    for suffix in ("html", "htm"):
        relative = f"docs/nested/page.{suffix.upper()}"
        cases.append(Case(f"docs 内 .{suffix}", lambda root, path=relative: _put(root, path, b"x" * 10_001),
                          1, (f"{relative}: 工作树 10001",)))
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", action="store_true")
    arguments = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    cases = _cases()
    if arguments.count:
        print(len(cases))
        return 0
    failed = 0
    try:
        with tempfile.TemporaryDirectory(prefix="amz-doc-budget-probe-") as directory:
            temporary = Path(directory)
            baseline = temporary / "baseline"
            _fixture(baseline)
            for number, case in enumerate(cases):
                root = temporary / f"case-{number:02d}"
                try:
                    shutil.copytree(baseline, root)
                    if case.change is not None:
                        case.change(root)
                    result = subprocess.run(
                        [sys.executable, "-B", str(root / case.script)], cwd=root,
                        env=_environment(root), capture_output=True, text=True, encoding="utf-8",
                        errors="replace", timeout=60, check=False,
                    )
                    output = result.stdout + result.stderr
                    problems = []
                    if result.returncode != case.expected:
                        problems.append(f"退出码 {result.returncode}，期望 {case.expected}")
                    problems.extend(f"缺少 {item!r}" for item in case.must if item not in output)
                    problems.extend(f"不应出现 {item!r}" for item in case.must_not if item in output)
                    print(f"[{'FAIL' if problems else 'OK'}] {case.name} → rc={result.returncode}")
                    if problems:
                        failed += 1
                        print("\n".join(problems))
                        print(output.rstrip())
                except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                    failed += 1
                    print(f"[FAIL] {case.name}: {error}")
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"[FAIL] 临时夹具建立或清理失败：{error}", file=sys.stderr)
        return 1
    print(f"{'FAIL' if failed else 'OK'}：{len(cases) - failed}/{len(cases)} 向符合预期；仅使用临时 Git 仓库。")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
