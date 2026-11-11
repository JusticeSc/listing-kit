#!/usr/bin/env python3
"""按原始字节检查 Git index 与工作树中的项目文档；上限固定为 10,000。

包括稀疏 index 和未忽略的新文件；已跟踪文件不因忽略规则、状态声明或目录退役。
安装依赖中的文档、机器 JSON/YAML 和 docs/ 以外的 HTML 不属于项目文档。
"""
from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MAX_DOCUMENT_BYTES = 10_000
DOCUMENT_SUFFIXES = frozenset({
    ".md", ".mdx", ".markdown", ".mdown", ".mkd", ".rst", ".adoc", ".asciidoc",
    ".org", ".tex", ".rtf", ".txt", ".text", ".log", ".out", ".pdf", ".doc",
    ".docx", ".odt", ".ppt", ".pptx", ".odp",
})
DOCUMENT_NAMES = frozenset({"README", "LICENSE", "NOTICE", "COPYING"})
DEPENDENCY_DIRECTORIES = frozenset({"node_modules", ".venv", "venv"})


def _git(*arguments: str, payload: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "--no-optional-locks", "--no-replace-objects", *arguments], cwd=ROOT, input=payload,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(arguments)}: {detail or result.returncode}")
    return result.stdout


def _check_root() -> None:
    try:
        actual = Path(os.fsdecode(_git("rev-parse", "--show-toplevel").rstrip(b"\r\n"))).resolve()
    except (OSError, RuntimeError) as error:
        raise RuntimeError(f"无法确定真实 Git 根：{error}") from error
    if actual != ROOT:
        raise RuntimeError(f"真实 Git 根不匹配：脚本根 {ROOT}，Git 根 {actual}")


def _dependency(path: str) -> bool:
    return any(part.lower() in DEPENDENCY_DIRECTORIES for part in PurePosixPath(path).parts[:-1])


def _document(path: str) -> bool:
    if _dependency(path):
        return False
    relative = PurePosixPath(path)
    suffix = relative.suffix.lower()
    return (
        suffix in DOCUMENT_SUFFIXES
        or (not suffix and relative.name.upper() in DOCUMENT_NAMES)
        or (relative.parts[0].lower() == "docs" and suffix in {".html", ".htm"})
    )


def _index_documents() -> list[tuple[str, str, str]]:
    documents: list[tuple[str, str, str]] = []
    try:
        records = _git("ls-files", "--stage", "--sparse", "-z")
        for record in records.split(b"\0"):
            if not record:
                continue
            header, raw_path = record.split(b"\t", 1)
            mode, raw_oid, raw_stage = header.split()
            path = os.fsdecode(raw_path)
            oid, stage = raw_oid.decode("ascii"), raw_stage.decode("ascii")
            if mode == b"040000":
                # --sparse 保留目录对象；从真实树展开，不能只看磁盘上存在的文件。
                tree = _git("ls-tree", "-r", "-z", oid)
                for item in tree.split(b"\0"):
                    if not item:
                        continue
                    metadata, child = item.split(b"\t", 1)
                    _, kind, child_oid = metadata.split()
                    relative = path.rstrip("/") + "/" + os.fsdecode(child)
                    if kind == b"blob" and _document(relative):
                        documents.append((relative, child_oid.decode("ascii"), stage))
            elif mode != b"160000" and _document(path):
                documents.append((path, oid, stage))
    except (OSError, RuntimeError, ValueError, UnicodeError) as error:
        raise RuntimeError(f"Git index 无法读取：{error}") from error
    return documents


def _blob_sizes(oids: list[str]) -> dict[str, int]:
    sizes: dict[str, int] = {}
    if not oids:
        return sizes
    # 读完 blob 才算可读；只读对象头无法发现正文损坏。stderr 落临时文件以免管道互锁。
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            ["git", "--no-optional-locks", "--no-replace-objects", "cat-file", "--batch"], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors,
        )
        try:
            assert process.stdin is not None and process.stdout is not None
            for oid in dict.fromkeys(oids):
                process.stdin.write(oid.encode("ascii") + b"\n")
                process.stdin.flush()
                header = process.stdout.readline().split()
                if len(header) != 3 or header[0] != oid.encode("ascii") or header[1] != b"blob":
                    raise RuntimeError(f"index/blob 无法读取：{oid}（{b' '.join(header)!r}）")
                remaining = size = int(header[2])
                while remaining:
                    chunk = process.stdout.read(min(remaining, 65_536))
                    if not chunk:
                        raise RuntimeError(f"index/blob 无法读取：{oid} 正文不完整")
                    remaining -= len(chunk)
                if process.stdout.read(1) != b"\n":
                    raise RuntimeError(f"index/blob 无法读取：{oid} 缺少结束字节")
                sizes[oid] = size
            process.stdin.close()
            result = process.wait()
            if result:
                errors.seek(0)
                raise RuntimeError(f"index/blob 无法读取：{errors.read().decode('utf-8', 'replace').strip()}")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
            if process.stdout is not None:
                process.stdout.close()
    return sizes


def _workspace_paths(indexed: set[str]) -> set[str]:
    paths = set(indexed)
    for raw_path in _git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0"):
        if not raw_path:
            continue
        path = os.fsdecode(raw_path)
        if path.endswith("/"):
            if not _dependency(path + "README"):
                raise RuntimeError(f"嵌套 Git 仓库无法纳入文档检查：{path}")
        elif _document(path):
            paths.add(path)
    return paths


def _workspace_size(relative: str) -> int | None:
    path = ROOT / relative
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    if not path.resolve().is_relative_to(ROOT):
        raise RuntimeError(f"{relative}: 工作树文档指向真实 Git 根之外")
    if not stat.S_ISREG(path.stat().st_mode):
        raise RuntimeError(f"{relative}: 工作树文档不是可读普通文件")
    with path.open("rb") as source:
        return sum(len(chunk) for chunk in iter(lambda: source.read(65_536), b""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    problems: list[str] = []
    try:
        _check_root()
        documents = _index_documents()
        sizes = _blob_sizes([oid for _, oid, _ in documents])
        for path, oid, stage in documents:
            if sizes[oid] > MAX_DOCUMENT_BYTES:
                problems.append(f"{path}: index(stage {stage}) {sizes[oid]} 字节超过 {MAX_DOCUMENT_BYTES} 上限")
        paths = _workspace_paths({path for path, _, _ in documents})
        present = 0
        for path in sorted(paths):
            try:
                size = _workspace_size(path)
                if size is None:
                    continue
                present += 1
                if size > MAX_DOCUMENT_BYTES:
                    problems.append(f"{path}: 工作树 {size} 字节超过 {MAX_DOCUMENT_BYTES} 上限")
            except (OSError, RuntimeError) as error:
                problems.append(f"{path}: 工作树无法读取：{error}")
    except (OSError, RuntimeError, ValueError) as error:
        problems.append(str(error))
    if problems:
        print("check_doc_budgets 失败：", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    print(f"check_doc_budgets: index {len(documents)} 项、工作树 {present} 份文档均不超过 {MAX_DOCUMENT_BYTES} 字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
