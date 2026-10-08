#!/usr/bin/env python
"""工作空间备份 / 校验 / 恢复（D4.3）。

用法：
  python tools/workspace_backup_restore.py backup  --workspace <目录> --out <目录>
  python tools/workspace_backup_restore.py verify  --backup <备份目录>
  python tools/workspace_backup_restore.py restore --backup <备份目录> --into <目录>

规则：
- 备份写 manifest.json（相对路径 + sha256 + 字节数 + mtime）与 version.json（代码/依赖指纹）。
- 恢复前先逐文件校验备份；校验失败即中止，不写目标目录。
- 恢复永不覆盖已存在的同名工作空间；冲突时另存 <名称>-restored-<时间戳>。
- 运行期锁文件 .workspace.lock 不进入备份（它是进程锁，不是业务数据）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_NAMES = {".workspace.lock"}
CODE_FINGERPRINT_PATTERNS = (
    "pyproject.toml",
    "uv.lock",
    "app/server.py",
    "app/product_v1_server.py",
    "app/product_v1/index.html",
    "app/product_v1/product.js",
    "app/product_v1/styles.css",
)
CODE_FINGERPRINT_GLOBS = ("src/*.py", "src/providers/*.py", "tools/*.py")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_workspace_files(root: Path):
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in EXCLUDED_NAMES:
            yield path


def build_manifest(root: Path) -> dict:
    files = []
    for path in iter_workspace_files(root):
        stat = path.stat()
        files.append({
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
            "byte_size": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    return {
        "schema": "amz-listing-kit/workspace-backup@1",
        "created_at": utc_now(),
        "source": str(root),
        "source_name": root.name,
        "file_count": len(files),
        "total_bytes": sum(item["byte_size"] for item in files),
        "excluded": sorted(EXCLUDED_NAMES),
        "files": files,
    }


def build_version_record(workspace_json: dict | None) -> dict:
    fingerprints: dict[str, str] = {}
    for relative in CODE_FINGERPRINT_PATTERNS:
        path = ROOT / relative
        if path.is_file():
            fingerprints[relative] = sha256_file(path)
    for pattern in CODE_FINGERPRINT_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if path.is_file():
                fingerprints[path.relative_to(ROOT).as_posix()] = sha256_file(path)
    return {
        "captured_at": utc_now(),
        "app_version": (workspace_json or {}).get("app_version"),
        "workspace_schema": (workspace_json or {}).get("schema"),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "code_fingerprints": fingerprints,
    }


def read_workspace_json(root: Path) -> dict | None:
    path = root / "workspace.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def verify_against_manifest(root: Path, manifest: dict) -> dict:
    expected = {item["path"]: item for item in manifest.get("files", [])}
    seen: set[str] = set()
    missing: list[str] = []
    mismatched: list[dict] = []
    for relative, item in sorted(expected.items()):
        path = root / relative
        if not path.is_file():
            missing.append(relative)
            continue
        seen.add(relative)
        digest = sha256_file(path)
        if digest != item["sha256"]:
            mismatched.append({"path": relative, "expected": item["sha256"], "actual": digest})
    extra = [
        path.relative_to(root).as_posix()
        for path in iter_workspace_files(root)
        if path.relative_to(root).as_posix() not in expected
    ]
    return {
        "ok": not missing and not mismatched and not extra,
        "checked": len(seen),
        "missing": missing,
        "mismatched": mismatched,
        "extra": extra,
    }


def command_backup(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    if not (workspace / "workspace.json").is_file():
        print(json.dumps({"ok": False, "error": f"不是工作空间目录：{workspace}"}, ensure_ascii=False))
        return 2
    out_root = Path(args.out).resolve()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = out_root / f"{workspace.name}_{stamp}"
    suffix = 1
    while target.exists():
        suffix += 1
        target = out_root / f"{workspace.name}_{stamp}_{suffix}"
    out_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(workspace, target, ignore=shutil.ignore_patterns(*EXCLUDED_NAMES))
    manifest = build_manifest(workspace)
    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    version = build_version_record(read_workspace_json(workspace))
    (target / "version.json").write_text(
        json.dumps(version, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    result = {
        "ok": True, "backup": str(target), "file_count": manifest["file_count"],
        "total_bytes": manifest["total_bytes"], "version": str(target / "version.json"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def load_backup_manifest(backup: Path) -> dict:
    manifest_path = backup / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"备份缺少 manifest.json：{backup}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def verify_backup_payload(backup: Path, manifest: dict) -> dict:
    payload_root = Path(backup)
    expected = {item["path"]: item for item in manifest.get("files", [])}
    payload = {path.relative_to(payload_root).as_posix(): path for path in iter_workspace_files(payload_root)}
    payload.pop("manifest.json", None)
    payload.pop("version.json", None)
    missing = [relative for relative in expected if relative not in payload]
    mismatched = [
        {"path": relative, "expected": item["sha256"], "actual": sha256_file(payload[relative])}
        for relative, item in expected.items()
        if relative in payload and sha256_file(payload[relative]) != item["sha256"]
    ]
    extra = [relative for relative in payload if relative not in expected]
    return {
        "ok": not missing and not mismatched and not extra,
        "checked": len(expected) - len(missing),
        "missing": missing, "mismatched": mismatched, "extra": extra,
    }


def command_verify(args: argparse.Namespace) -> int:
    backup = Path(args.backup).resolve()
    try:
        manifest = load_backup_manifest(backup)
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    report = verify_backup_payload(backup, manifest)
    report["backup"] = str(backup)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


def command_restore(args: argparse.Namespace) -> int:
    backup = Path(args.backup).resolve()
    try:
        manifest = load_backup_manifest(backup)
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    pre = verify_backup_payload(backup, manifest)
    if not pre["ok"]:
        print(json.dumps({"ok": False, "stage": "verify", "error": "备份校验失败，未写入目标目录",
                          "detail": pre}, ensure_ascii=False, indent=2))
        return 1

    into_root = Path(args.into).resolve()
    into_root.mkdir(parents=True, exist_ok=True)
    name = manifest.get("source_name") or Path(manifest.get("source", "")).name or backup.name.split("_")[0]
    target = into_root / name
    conflict: dict | None = None
    if target.exists():
        existing_updated = (read_workspace_json(target) or {}).get("updated_at")
        incoming_updated = (read_workspace_json(backup) or {}).get("updated_at")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        new_target = into_root / f"{name}-restored-{stamp}"
        suffix = 1
        while new_target.exists():
            suffix += 1
            new_target = into_root / f"{name}-restored-{stamp}_{suffix}"
        conflict = {
            "existing": str(target),
            "existing_updated_at": existing_updated,
            "incoming_updated_at": incoming_updated,
            "action": "saved_as_copy",
            "copy": str(new_target),
        }
        target = new_target

    # 只排除备份自身的元数据；导出包里的 exports/*/manifest.json 是业务数据，必须保留。
    shutil.copytree(backup, target, ignore=shutil.ignore_patterns(*EXCLUDED_NAMES))
    for metadata_name in ("manifest.json", "version.json"):
        metadata_path = target / metadata_name
        if metadata_path.is_file():
            metadata_path.unlink()
    verified = verify_against_manifest(target, manifest)
    result = {
        "ok": verified["ok"],
        "restored_to": str(target),
        "files_checked": verified["checked"],
        "missing": verified["missing"],
        "mismatched": verified["mismatched"],
        "extra": verified["extra"],
        "conflict": conflict,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if verified["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="工作空间备份/校验/恢复")
    sub = parser.add_subparsers(dest="command", required=True)
    backup = sub.add_parser("backup")
    backup.add_argument("--workspace", required=True)
    backup.add_argument("--out", required=True)
    backup.set_defaults(func=command_backup)
    verify = sub.add_parser("verify")
    verify.add_argument("--backup", required=True)
    verify.set_defaults(func=command_verify)
    restore = sub.add_parser("restore")
    restore.add_argument("--backup", required=True)
    restore.add_argument("--into", required=True)
    restore.set_defaults(func=command_restore)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
