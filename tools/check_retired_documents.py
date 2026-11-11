#!/usr/bin/env python3
"""核对已退役文档的公共 Git 恢复登记；不恢复原件，也不改变当前目录。"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
import sys

from document_provenance import PUBLIC_BASELINE_COMMIT, ensure_public_repository, git
from check_doc_budgets import MAX_DOCUMENT_BYTES, _blob_sizes, _document

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "retired-documents.json"
SPLIT_REGISTRY = ROOT / "config" / "document-splits.json"
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")


def _registry_file() -> Path:
    if REGISTRY.is_symlink():
        raise RuntimeError("retired-documents.json: 登记文件不得是符号链接")
    resolved = REGISTRY.resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        raise RuntimeError("retired-documents.json: 登记文件必须位于仓库内")
    if not REGISTRY.is_file():
        raise RuntimeError("retired-documents.json: 登记文件不存在")
    return REGISTRY


def _path(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value or "\0" in value:
        raise RuntimeError(f"{label}: 必须是仓库内相对路径")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise RuntimeError(f"{label}: 必须是仓库内相对路径")
    return value


def _split_registry_file() -> Path:
    if SPLIT_REGISTRY.is_symlink():
        raise RuntimeError("document-splits.json: 登记文件不得是符号链接")
    resolved = SPLIT_REGISTRY.resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        raise RuntimeError("document-splits.json: 登记文件必须位于仓库内")
    if not SPLIT_REGISTRY.is_file():
        raise RuntimeError("document-splits.json: 登记文件不存在")
    return SPLIT_REGISTRY


def _split_paths() -> set[str]:
    registry = json.loads(_split_registry_file().read_text(encoding="utf-8"))
    if not isinstance(registry, dict) or registry.get("schema") != "amz-document-splits/v1":
        raise RuntimeError("document-splits.json 的 schema 必须是 amz-document-splits/v1")
    splits = registry.get("splits")
    if not isinstance(splits, list):
        raise RuntimeError("document-splits.json 的 splits 必须是数组")
    paths: set[str] = set()
    for index, raw in enumerate(splits):
        if not isinstance(raw, dict):
            raise RuntimeError(f"splits[{index}]: 必须是对象")
        relative = _path(raw.get("path"), f"splits[{index}].path")
        if relative in paths:
            raise RuntimeError(f"splits[{index}].path: path 重复：{relative}")
        paths.add(relative)
    return paths


def _baseline_oversized_paths() -> set[str]:
    records = git(ROOT, "ls-tree", "-r", "-z", PUBLIC_BASELINE_COMMIT)
    objects: dict[str, str] = {}
    for record in records.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        _mode, kind, raw_oid = metadata.split()
        relative = raw_path.decode("utf-8")
        if kind == b"blob" and _document(relative):
            objects[relative] = raw_oid.decode("ascii")
    sizes = _blob_sizes(list(objects.values()))
    return {path for path, oid in objects.items() if sizes[oid] > MAX_DOCUMENT_BYTES}


def _check_entry(raw: object, index: int, seen: set[str]) -> None:
    label = f"documents[{index}]"
    if not isinstance(raw, dict):
        raise RuntimeError(f"{label}: 必须是对象")
    relative = _path(raw.get("path"), f"{label}.path")
    if relative in seen:
        raise RuntimeError(f"{label}: path 重复：{relative}")
    seen.add(relative)
    for field in ("generation", "reason"):
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            raise RuntimeError(f"{label}.{field}: 必须是非空字符串")
    commit = raw.get("commit")
    if commit != PUBLIC_BASELINE_COMMIT:
        raise RuntimeError(f"{label}.commit: 必须是公共基线 {PUBLIC_BASELINE_COMMIT}")
    git_blob = raw.get("git_blob")
    if not isinstance(git_blob, str) or HEX40.fullmatch(git_blob) is None:
        raise RuntimeError(f"{label}.git_blob: 必须是 40 位小写十六进制")
    digest = raw.get("sha256")
    if not isinstance(digest, str) or HEX64.fullmatch(digest) is None:
        raise RuntimeError(f"{label}.sha256: 必须是 64 位小写十六进制")
    size = raw.get("bytes")
    if type(size) is not int or size < 0:
        raise RuntimeError(f"{label}.bytes: 必须是非负整数")
    target = ROOT / relative
    if target.exists() or target.is_symlink():
        raise RuntimeError(f"{relative}: 退役原件仍在当前树中")
    actual_blob = git(ROOT, "rev-parse", f"{PUBLIC_BASELINE_COMMIT}:{relative}").strip().decode("ascii")
    if actual_blob != git_blob:
        raise RuntimeError(f"{label}.git_blob: {relative} 的公共基线 blob 不一致")
    payload = git(ROOT, "cat-file", "blob", f"{PUBLIC_BASELINE_COMMIT}:{relative}")
    if len(payload) != size or hashlib.sha256(payload).hexdigest() != digest:
        raise RuntimeError(f"{label}: {relative} 的公共基线字节数或 SHA-256 不一致")


def main() -> int:
    problems: list[str] = []
    checked = 0
    baseline_checked = 0
    try:
        ensure_public_repository(ROOT)
        registry = json.loads(_registry_file().read_text(encoding="utf-8"))
        if not isinstance(registry, dict) or registry.get("schema") != "amz-retired-documents/v1":
            raise RuntimeError("retired-documents.json 的 schema 必须是 amz-retired-documents/v1")
        documents = registry.get("documents")
        if not isinstance(documents, list):
            raise RuntimeError("retired-documents.json 的 documents 必须是数组")
        seen: set[str] = set()
        for index, raw in enumerate(documents):
            _check_entry(raw, index, seen)
            checked += 1
        split_paths = _split_paths()
        baseline_paths = _baseline_oversized_paths()
        baseline_checked = len(baseline_paths)
        missing = sorted(baseline_paths - seen - split_paths)
        if missing:
            sample = "、".join(missing[:5])
            suffix = "" if len(missing) <= 5 else "……"
            raise RuntimeError(
                f"公共基线有 {len(missing)} 份超过 {MAX_DOCUMENT_BYTES} 字节的文档未登记拆分或退役：{sample}{suffix}"
            )
    except (OSError, RuntimeError, UnicodeError, ValueError) as error:
        problems.append(str(error))
    if problems:
        print("check_retired_documents 失败：", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    print(f"check_retired_documents: {checked} 份退役文档的公共 Git 恢复登记通过；公共基线 {baseline_checked} 份超限文档均有拆分或退役登记")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
