#!/usr/bin/env python3
"""验证 amz-document-splits/v1 的原件来源与登记；不冻结后续文档编辑。

默认核对不可变 Git 原件、登记结构和当前文件存在及分片预算。
--verify-current 只用于拆分交付时核对当前字节重组或完整原文行的保留。
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys

from document_provenance import PUBLIC_BASELINE_COMMIT, ensure_public_repository, git

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "config" / "document-splits.json"
HEADER_LINES = 4
MAX_DOCUMENT_BYTES = 10_000
MODES = {"byte-exact", "raw-parts", "sections-preserved"}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _git(*arguments: str) -> bytes:
    return git(ROOT, *arguments)


def _check_root() -> None:
    try:
        ensure_public_repository(ROOT)
    except (OSError, RuntimeError) as error:
        raise RuntimeError(f"公共 Git 来源不可用（基线 {PUBLIC_BASELINE_COMMIT}）：{error}") from error


def _registry_file() -> Path:
    if REGISTRY.is_symlink():
        raise RuntimeError("document-splits.json: 登记文件不得是符号链接")
    resolved = REGISTRY.resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        raise RuntimeError("document-splits.json: 登记文件必须位于仓库内")
    if not REGISTRY.is_file():
        raise RuntimeError("document-splits.json: 登记文件不存在")
    return REGISTRY


def _path(value: object, label: str) -> str:
    if not isinstance(value, str) or "\\" in value or ":" in value or "\0" in value:
        raise RuntimeError(f"{label}: 必须是仓库内相对路径")
    if any(part in {"", ".", ".."} for part in value.split("/")) or PurePosixPath(value).is_absolute():
        raise RuntimeError(f"{label}: 必须是仓库内相对路径")
    return value


def _file(relative: str, label: str) -> Path:
    target = ROOT / relative
    if not target.resolve().is_relative_to(ROOT):
        raise RuntimeError(f"{relative}: 登记路径指向真实 Git 根之外")
    if not target.is_file():
        raise RuntimeError(f"{relative}: {label}不存在")
    return target


def _metadata(value: object, label: str, *, optional_bytes: bool = False) -> dict:
    if not isinstance(value, dict):
        raise RuntimeError(f"{label}: 必须是对象")
    digest = value.get("sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise RuntimeError(f"{label}: sha256 必须是 64 位小写十六进制")
    if not optional_bytes or "bytes" in value:
        size = value.get("bytes")
        if type(size) is not int or size < 0:
            raise RuntimeError(f"{label}: bytes 必须是非负整数")
    return value


def _segment(metadata: dict, lines: list[bytes], label: str) -> tuple[int, int, bytes]:
    interval = metadata.get("lines")
    if (not isinstance(interval, list) or len(interval) != 2
            or any(type(number) is not int for number in interval)):
        raise RuntimeError(f"{label}: lines 必须是两个整数的闭区间")
    start, end = interval
    if not 1 <= start <= end <= len(lines):
        raise RuntimeError(f"{label}: lines 越界")
    segment = b"".join(lines[start - 1:end])
    if _sha256(segment) != metadata["sha256"] or ("bytes" in metadata and len(segment) != metadata["bytes"]):
        raise RuntimeError(f"{label}: sha256/bytes 与原件区间不一致")
    return start, end, segment


def _body(payload: bytes, part: dict, problems: list[str]) -> bytes:
    relative = part["path"]
    lines = payload.splitlines(keepends=True)
    if len(lines) < HEADER_LINES or not lines[0].startswith("<!-- 拆分件".encode("utf-8")):
        raise RuntimeError(f"{relative}: 需要 {HEADER_LINES} 行导航头，首行必须以 <!-- 拆分件 开头")
    content = b"".join(lines[HEADER_LINES:])
    for field, at_start in (("remove_prefix", True), ("remove_suffix", False)):
        marker = part.get(field, "").encode("utf-8")
        if not marker:
            continue
        present = content.startswith(marker) if at_start else content.endswith(marker)
        if not present:
            problems.append(f"{relative}: 拆分续接标记 {field} 缺失")
        else:
            content = content[len(marker):] if at_start else content[:-len(marker)]
    return content


def _entry(entry: object, verify_current: bool) -> list[str]:
    if not isinstance(entry, dict):
        raise RuntimeError("登记项必须是对象")
    relative = _path(entry.get("path"), "path")
    parent = _file(relative, "登记的父文档")
    original_meta = _metadata(entry.get("original"), f"{relative}: original")
    commit = original_meta.get("commit")
    if not isinstance(commit, str) or re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", commit) is None:
        raise RuntimeError(f"{relative}: original.commit 必须是完整不可变提交 ID")
    if commit != PUBLIC_BASELINE_COMMIT:
        raise RuntimeError(f"{relative}: original.commit 必须是公共基线 {PUBLIC_BASELINE_COMMIT}")
    original_path = _path(original_meta.get("path"), f"{relative}: original.path")
    try:
        if _git("cat-file", "-t", commit).strip() != b"commit":
            raise RuntimeError("original.commit 不是提交对象")
        original = _git("cat-file", "blob", f"{commit}:{original_path}")
    except (OSError, RuntimeError) as error:
        raise RuntimeError(f"{relative}: 无法从 {commit}:{original_path} 取回原件（{error}）") from error
    if _sha256(original) != original_meta["sha256"] or len(original) != original_meta["bytes"]:
        raise RuntimeError(f"{relative}: 原件字节与登记的 original 不一致")

    mode = entry.get("mode")
    if not isinstance(mode, str) or mode not in MODES:
        raise RuntimeError(f"{relative}: mode 必须是 byte-exact、raw-parts 或 sections-preserved")
    parts, extracted = entry.get("parts"), entry.get("extracted", [])
    if not isinstance(parts, list) or not isinstance(extracted, list):
        raise RuntimeError(f"{relative}: parts 与 extracted 必须是数组")
    if not parts and not extracted:
        raise RuntimeError(f"{relative}: parts 与 extracted 不能都为空")
    if mode == "raw-parts" and (entry.get("prefix") is not None or extracted):
        raise RuntimeError(f"{relative}: raw-parts 只能按序拼接 parts")

    original_lines = original.splitlines(keepends=True)
    prefix_bytes = b""
    prefix_end = 0
    prefix = entry.get("prefix")
    if prefix is not None:
        _metadata(prefix, f"{relative}: prefix", optional_bytes=True)
        start, prefix_end, prefix_bytes = _segment(prefix, original_lines, f"{relative}: prefix")
        if start != 1:
            raise RuntimeError(f"{relative}: prefix.lines 必须从原件第 1 行开始")

    problems: list[str] = []
    payloads: list[bytes] = []
    seen: set[str] = set()
    for raw_part in parts:
        part = _metadata(raw_part, f"{relative}: part")
        part_path = _path(part.get("path"), f"{relative}: part.path")
        if part_path == relative or part_path in seen:
            raise RuntimeError(f"{relative}: 拆分件路径不能重复或指向父文档：{part_path}")
        seen.add(part_path)
        for field in ("remove_prefix", "remove_suffix"):
            if field in part and not isinstance(part[field], str):
                raise RuntimeError(f"{part_path}: {field} 必须是字符串")
        payload = _file(part_path, "登记了但文件").read_bytes()
        if len(payload) > MAX_DOCUMENT_BYTES:
            problems.append(f"{part_path}: {len(payload)} 字节超过 {MAX_DOCUMENT_BYTES} 上限")
        if mode == "byte-exact":
            lines = payload.splitlines(keepends=True)
            if len(lines) < HEADER_LINES or not lines[0].startswith("<!-- 拆分件".encode("utf-8")):
                raise RuntimeError(f"{part_path}: 需要 {HEADER_LINES} 行导航头，首行必须以 <!-- 拆分件 开头")
        if verify_current:
            if len(payload) != part["bytes"] or _sha256(payload) != part["sha256"]:
                problems.append(f"{part_path}: 字节与拆分时登记的 sha256/bytes 不一致")
            payloads.append(_body(payload, part, problems) if mode == "byte-exact" else payload)

    extra_payloads: list[tuple[int, int, bytes, bytes, bytes]] = []
    for raw_extra in extracted:
        extra = _metadata(raw_extra, f"{relative}: extracted")
        extra_path = _path(extra.get("path"), f"{relative}: extracted.path")
        start, end, segment = _segment(extra, original_lines, f"{relative}: extracted {extra_path}")
        target = _file(extra_path, "登记的机器数据文件")
        opening = closing = b""
        fences = extra.get("fences")
        if fences is not None:
            if (not isinstance(fences, dict) or not isinstance(fences.get("open"), str)
                    or not isinstance(fences.get("close"), str) or start < 2 or end >= len(original_lines)):
                raise RuntimeError(f"{relative}: extracted.fences 需要原件区间两侧的 open/close 围栏")
            opening, closing = original_lines[start - 2], original_lines[end]
            if (opening.rstrip(b"\r\n") != fences["open"].encode("utf-8")
                    or closing.rstrip(b"\r\n") != fences["close"].encode("utf-8")):
                raise RuntimeError(f"{relative}: 登记的代码围栏与原件不一致")
        if verify_current:
            payload = target.read_bytes()
            if payload != segment:
                problems.append(f"{extra_path}: 字节与原件第 {start}-{end} 行不一致")
            extra_payloads.append((start, end, opening, payload, closing))

    if not verify_current:
        return problems
    if mode == "byte-exact":
        if prefix is not None and b"".join(parent.read_bytes().splitlines(keepends=True)[:prefix_end]) != prefix_bytes:
            problems.append(f"{relative}: 索引页前 {prefix_end} 行没有原样保留原文前缀")
        rebuilt = prefix_bytes + b"".join(payloads)
        cursor = len(rebuilt.splitlines(keepends=True))
        for start, end, opening, payload, closing in extra_payloads:
            expected_start = cursor + (2 if opening else 1)
            if start != expected_start:
                problems.append(f"{relative}: extracted 区间必须紧接前一段（起点应为 {expected_start}）")
            rebuilt += opening + payload + closing
            cursor = end + (1 if closing else 0)
        if rebuilt != original:
            problems.append(f"{relative}: 拆分件按序重组后与原件不一致")
    elif mode == "raw-parts":
        if b"".join(payloads) != original:
            problems.append(f"{relative}: 文本分片按序重组后与原件不一致")
    else:
        # 原文须以整行保留；子串或少一次重复行不能替代原文行。
        retained = Counter(parent.read_bytes().decode("utf-8").splitlines())
        for payload in payloads:
            retained.update(payload.decode("utf-8").splitlines())
        for _, _, _, payload, _ in extra_payloads:
            retained.update(payload.decode("utf-8").splitlines())
        wanted = Counter(line for line in original.decode("utf-8").splitlines() if line.strip())
        missing = wanted - retained
        if missing:
            first = next(iter(missing))
            problems.append(f"{relative}: {sum(missing.values())} 行原文既不在索引页也不在拆分件中，首行示例：{first[:80]}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-current", action="store_true", help="核对拆分时当前字节重组；不作为日常冻结门")
    arguments = parser.parse_args()
    problems: list[str] = []
    checked = 0
    try:
        _check_root()
        registry = json.loads(_registry_file().read_text(encoding="utf-8"))
        if not isinstance(registry, dict) or registry.get("schema") != "amz-document-splits/v1":
            raise RuntimeError("registry schema 必须为 amz-document-splits/v1")
        splits = registry.get("splits")
        if not isinstance(splits, list):
            raise RuntimeError("splits 必须是数组")
        seen: set[str] = set()
        for entry in splits:
            try:
                relative = _path(entry.get("path") if isinstance(entry, dict) else None, "path")
                if relative in seen:
                    raise RuntimeError(f"{relative}: 父文档登记重复")
                seen.add(relative)
                problems.extend(_entry(entry, arguments.verify_current))
                checked += 1
            except (OSError, RuntimeError, UnicodeError) as error:
                problems.append(str(error))
    except (OSError, RuntimeError, ValueError) as error:
        problems.append(str(error))
    if problems:
        print("check_document_splits 失败：", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    mode = "当前重组/保留证明" if arguments.verify_current else "来源与登记检查"
    print(f"check_document_splits: {checked} 份拆分文档的{mode}通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
