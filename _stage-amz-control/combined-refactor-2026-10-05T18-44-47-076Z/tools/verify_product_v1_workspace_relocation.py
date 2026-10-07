#!/usr/bin/env python
"""D4.12 换目录恢复：在最终版本上重跑 备份 → 校验 → 恢复 → 重开。

Builds a fixture workspace with candidates, selection and an export through the
product's own service methods (fake providers, no network), then runs the
shipped backup/verify/restore tool into a different root and proves the restored
copy reopens through both the Application Service and the HTTP entry with the
same identity, reference order/hashes, plan/prompt versions, candidate bytes,
selection choices and export record.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
for entry in (str(ROOT), str(TOOLS)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import requests

from app.product_v1_server import ProductApplication, create_product_server
from src.application_service import ApplicationService
from src.providers.fake_semantic import FakeSemanticProvider
from tools.verify_product_v1_image_generation import (
    FIRST_KEY,
    GenerationFixture,
    Submission,
    require_ok,
    semantic_responses,
)
from tools.verify_product_v1_selection_rework_export import (
    RegisteredFakeImageProvider,
    restore_platform_checks,
    use_stub_platform_checks,
)

EVIDENCE = ROOT / "evals" / "product-demo"
BACKUP_TOOL = ROOT / "tools" / "workspace_backup_restore.py"
SKIPPED_NAMES = {".workspace.lock"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_tree(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name not in SKIPPED_NAMES
    }


def describe(projection: dict) -> dict:
    workspace = projection["workspace"]
    shots = projection["plan"]["shot_specs"]
    return {
        "workspace_id": workspace.get("id") or workspace.get("workspace_id"),
        "workspace_revision": workspace.get("revision"),
        "references": [
            item.get("sha256") for item in projection["intake"].get("reference_images") or []
        ],
        "shots": [
            {
                "id": shot["id"],
                "prompt_version": (shot.get("latest_prompt") or {}).get("version"),
                "candidates": [item["candidate_id"] for item in shot.get("candidates") or []],
            }
            for shot in shots
        ],
        "selection": sorted(
            item["candidate_sha256"]
            for item in (projection.get("selection") or {}).get("choices") or []
        ),
        "export": (projection.get("export") or {}).get("id"),
    }


def run_tool(*args: str) -> tuple[int, object]:
    environment = dict(os.environ)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    completed = subprocess.run(
        [sys.executable, str(BACKUP_TOOL), *args],
        capture_output=True, cwd=str(ROOT), env=environment,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    try:
        payload: object = json.loads(stdout)
    except json.JSONDecodeError:
        payload = (stdout or stderr)[-2000:]
    return completed.returncode, payload


def main() -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    fixture = GenerationFixture()
    fixture.setUp()
    failures: list[str] = []
    result: dict[str, object] = {"stamp": stamp}
    real_module = use_stub_platform_checks()
    try:
        provider = RegisteredFakeImageProvider()
        fixture.image_provider = provider
        provider.plan_submissions([
            Submission("SUCCEEDED", f"relocation-{index}") for index in range(1, 4)
        ])
        require_ok(fixture.start(FIRST_KEY), "start generation")
        projection = fixture.projection()
        choices = [
            {"shot_id": shot["id"], "candidate_sha256": shot["candidates"][0]["candidate_id"]}
            for shot in projection["plan"]["shot_specs"]
        ]
        selected = require_ok(fixture.service.save_selection(
            fixture.workspace, expected_etag=projection["workspace"]["revision"], choices=choices,
        ), "save selection")
        exported = require_ok(fixture.service.export_selection(
            fixture.workspace, expected_etag=selected["workspace"]["revision"],
        ), "export before relocation")

        before = describe(exported)
        before_files = hash_tree(fixture.workspace)
        result["before"] = before
        result["before_files"] = len(before_files)

        with tempfile.TemporaryDirectory(prefix="amz-product-v1-relocation-") as raw:
            root = Path(raw)
            backup_dir = root / "backup"
            restore_root = root / "restored-root"

            code, payload = run_tool("backup", "--workspace", str(fixture.workspace),
                                     "--out", str(backup_dir))
            result["backup"] = {"exit": code, "payload": payload}
            if code != 0 or not (isinstance(payload, dict) and payload.get("ok")):
                failures.append("备份命令没有成功：" + str(payload)[:300])
            backup_path = payload.get("backup") if isinstance(payload, dict) else None
            if not backup_path:
                failures.append("备份命令没有返回备份目录：" + str(payload)[:300])
                backup_path = str(backup_dir)

            code, payload = run_tool("verify", "--backup", str(backup_path))
            result["verify"] = {"exit": code, "payload": payload}
            if code != 0:
                failures.append("备份校验没有通过：" + str(payload)[:300])

            code, payload = run_tool("restore", "--backup", str(backup_path),
                                     "--into", str(restore_root))
            restored_to = payload.get("restored_to") if isinstance(payload, dict) else None
            result["restore"] = {"exit": code, "payload": payload}
            if code != 0 or not restored_to:
                failures.append("恢复命令没有成功：" + str(payload)[:300])

            restored_dir = Path(restored_to) if restored_to else None
            if restored_dir is not None and restored_dir.is_dir():
                service = ApplicationService(
                    semantic_provider_factory=lambda: FakeSemanticProvider(semantic_responses()),
                    image_provider_factory=lambda: RegisteredFakeImageProvider(),
                )
                reopened = require_ok(
                    service.get_workspace_projection(restored_dir), "open restored workspace",
                )
                after = describe(reopened)
                result["after"] = after
                if after != before:
                    failures.append("恢复后的工作空间投影与恢复前不一致")

                after_files = hash_tree(restored_dir)
                missing = sorted(set(before_files) - set(after_files))
                mismatched = sorted(
                    name for name, digest in before_files.items()
                    if after_files.get(name) != digest
                )
                result["relocation_files"] = {
                    "before": len(before_files), "after": len(after_files),
                    "missing": missing[:10], "mismatched": mismatched[:10],
                }
                if missing:
                    failures.append("恢复目录缺少文件：" + ", ".join(missing[:5]))
                if mismatched:
                    failures.append("恢复目录 hash 不一致：" + ", ".join(mismatched[:5]))

                application = ProductApplication(
                    service=service, recent_index_path=root / "recent-workspaces.json",
                )
                server = create_product_server("127.0.0.1", 0, application=application)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    response = requests.get(
                        f"http://127.0.0.1:{server.server_address[1]}/api/workspace",
                        params={"directory": str(restored_dir)}, timeout=10,
                    )
                    body = response.json()
                    result["http_reopen"] = {
                        "status": response.status_code, "ok": bool(body.get("ok")),
                    }
                    if response.status_code != 200 or not body.get("ok"):
                        failures.append("HTTP 入口无法打开恢复后的工作空间：" + response.text[:200])
                    elif body["data"]["workspace"]["revision"] != before["workspace_revision"]:
                        failures.append("HTTP 投影与恢复前的 workspace revision 不一致")
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=5)
            else:
                failures.append("恢复目录不存在，无法重开")
    finally:
        restore_platform_checks(real_module)
        fixture.tearDown()

    result["failures"] = failures
    result["passed"] = not failures
    report_path = EVIDENCE / f"d4.12-relocation-{stamp}.json"
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "ok": not failures, "failures": failures, "report": report_path.name,
        "relocation_files": result.get("relocation_files"),
    }, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
