from __future__ import annotations

import os
from pathlib import Path
import subprocess

PUBLIC_BASELINE_COMMIT = "11902b32651f4690f7367624377dcde6652e0a97"


def git(root: Path, *arguments: str) -> bytes:
    result = subprocess.run(
        ["git", "--no-optional-locks", "--no-replace-objects", *arguments],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(detail or "git 读取失败")
    return result.stdout


def ensure_public_repository(root: Path) -> None:
    resolved_root = root.resolve()
    actual = Path(os.fsdecode(git(root, "rev-parse", "--show-toplevel").rstrip(b"\r\n"))).resolve()
    if actual != resolved_root:
        raise RuntimeError(f"真实 Git 根不匹配：脚本根 {resolved_root}，Git 根 {actual}")
    if os.environ.get("GIT_OBJECT_DIRECTORY") or os.environ.get("GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        raise RuntimeError("禁止依赖环境指定的 Git 对象目录或 alternate")
    alternate = Path(os.fsdecode(git(root, "rev-parse", "--git-path", "objects/info/alternates").rstrip(b"\r\n")))
    if not alternate.is_absolute():
        alternate = root / alternate
    if alternate.is_file() and alternate.read_text(encoding="utf-8").strip():
        raise RuntimeError(f"禁止依赖 Git alternate 对象库：{alternate}")
    if git(root, "cat-file", "-t", PUBLIC_BASELINE_COMMIT).strip() != b"commit":
        raise RuntimeError(f"公共基线提交不可用：{PUBLIC_BASELINE_COMMIT}")
