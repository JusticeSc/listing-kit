#!/usr/bin/env python
"""Offline D0.2 acceptance checks for WorkspaceStore."""
from __future__ import annotations

import copy
import hashlib
import json
import multiprocessing
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import workspace_store as store_module  # noqa: E402
from src.workspace_store import (  # noqa: E402
    ImmutableRecordConflict,
    WorkspaceAlreadyExists,
    WorkspaceBusy,
    WorkspaceConflict,
    WorkspaceCorrupt,
    WorkspaceStore,
    WorkspaceSnapshot,
)

STAMP = "2026-09-28T00:00:00Z"
WORKSPACE_ID = "ws_store_test_0001"


def workspace_record() -> dict:
    return {
        "schema": "amz-listing-kit/workspace@1",
        "workspace_id": WORKSPACE_ID,
        "created_at": STAMP,
        "updated_at": STAMP,
        "app_version": "1.0.0",
        "status": "NEW",
        "assets": [],
        "current": {
            "product_input": None, "product_brief": None, "plan": None,
            "selection": None, "export": None,
        },
    }


def product_input(asset_sha: str, product_name: str = "Test product") -> dict:
    return {
        "schema": "amz-listing-kit/product-input@1",
        "id": "input_store_test_0001",
        "version": 999,
        "content_hash": "ignored-by-store",
        "workspace_id": WORKSPACE_ID,
        "created_at": STAMP,
        "product_name": product_name,
        "description": None,
        "selling_points": [],
        "platform": {"profile_id": "amazon-us", "version": 1},
        "reference_asset_sha256": [asset_sha],
        "user_intent": None,
    }


def _crash_before_index_replace(root: str, workspace: dict, expected_etag: str) -> None:
    def terminate_before_commit(_source, _target) -> None:
        os._exit(71)

    store_module.os.replace = terminate_before_commit
    WorkspaceStore(root).save_workspace(workspace, expected_etag=expected_etag)
    os._exit(79)


def _crash_after_index_replace(root: str, workspace: dict, expected_etag: str) -> None:
    store = WorkspaceStore(root)
    store._fsync_directory = lambda _directory: os._exit(72)
    store.save_workspace(workspace, expected_etag=expected_etag)
    os._exit(79)


class WorkspaceStoreChecks(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="amz-workspace-store-")
        self.parent = Path(self.temp.name)
        self.root = self.parent / "workspace"
        self.store = WorkspaceStore.create(self.root, workspace_record())

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _add_asset_and_first_input(self) -> tuple[dict, dict]:
        data = b"source-image-bytes-for-store-test"
        digest = hashlib.sha256(data).hexdigest()
        relative = "inputs/originals/reference.png"
        self.assertEqual(self.store.save_immutable_file(relative, data), digest)
        asset = {
            "sha256": digest, "relative_path": relative, "original_name": "reference.png",
            "media_type": "image/png", "byte_size": len(data), "width": 1, "height": 1,
            "role": "primary", "source": "user_upload",
        }
        saved = self.store.save_record("product_input", product_input(digest))
        current = self.store.load_workspace()
        changed = copy.deepcopy(current.workspace)
        changed["assets"].append(asset)
        changed["current"]["product_input"] = {
            "kind": "product_input", "id": saved["id"], "version": saved["version"],
        }
        changed["status"] = "INTAKE_READY"
        changed["updated_at"] = "2026-09-28T00:01:00Z"
        self.store.save_workspace(changed, expected_etag=current.etag)
        return asset, saved

    def _prepare_second_input_pointer(self) -> tuple[WorkspaceSnapshot, dict, dict]:
        asset, _ = self._add_asset_and_first_input()
        second = self.store.save_record(
            "product_input", product_input(asset["sha256"], "Revised name")
        )
        current = self.store.load_workspace()
        changed = copy.deepcopy(current.workspace)
        changed["current"]["product_input"] = {
            "kind": "product_input", "id": second["id"], "version": second["version"],
        }
        changed["updated_at"] = "2026-09-28T00:03:00Z"
        return current, changed, second

    def test_create_open_and_refuse_nonempty_target(self) -> None:
        reopened = WorkspaceStore.open(self.root)
        self.assertEqual(reopened.load_workspace().workspace["workspace_id"], WORKSPACE_ID)
        occupied = self.parent / "occupied"
        occupied.mkdir()
        sentinel = occupied / "keep.txt"
        sentinel.write_text("keep", encoding="utf-8")
        with self.assertRaises(WorkspaceAlreadyExists):
            WorkspaceStore.create(occupied, workspace_record())
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")
        self.assertFalse((occupied / ".workspace.lock").exists())

    def test_asset_and_versioned_records_are_immutable_and_versioned(self) -> None:
        asset, first = self._add_asset_and_first_input()
        first_path = self.root / "inputs" / "product-input-v001.json"
        original_bytes = first_path.read_bytes()
        data = b"source-image-bytes-for-store-test"
        with self.assertRaises(ImmutableRecordConflict):
            self.store.save_immutable_file(asset["relative_path"], b"different bytes")
        second = self.store.save_record("product_input", product_input(asset["sha256"], "Revised name"))
        self.assertEqual((first["version"], second["version"]), (1, 2))
        self.assertEqual(first_path.read_bytes(), original_bytes)
        self.assertNotEqual(first["content_hash"], second["content_hash"])
        current = self.store.load_workspace()
        changed = copy.deepcopy(current.workspace)
        changed["current"]["product_input"]["version"] = second["version"]
        changed["updated_at"] = "2026-09-28T00:02:00Z"
        self.store.save_workspace(changed, expected_etag=current.etag)
        recovered = WorkspaceStore.open(self.root)
        self.assertEqual(recovered.load_workspace().workspace["current"]["product_input"]["version"], 2)
        self.assertEqual([r["version"] for r in recovered.list_records("product_input")], [1, 2])

    def test_replace_failure_keeps_old_pointer_and_diagnostic_temp(self) -> None:
        current, changed, second = self._prepare_second_input_pointer()
        original_index = self.store.index_path.read_bytes()
        expected_payload = store_module._json_bytes(changed)

        with mock.patch.object(store_module.os, "replace", side_effect=OSError("injected pre-commit failure")):
            with self.assertRaisesRegex(OSError, "injected pre-commit failure"):
                self.store.save_workspace(changed, expected_etag=current.etag)

        self.assertEqual(self.store.index_path.read_bytes(), original_index)
        temp_files = list(self.root.glob(".workspace.json.tmp-*"))
        self.assertEqual(len(temp_files), 1)
        self.assertEqual(temp_files[0].read_bytes(), expected_payload)

        recovered = WorkspaceStore.open(self.root).load_workspace()
        self.assertEqual(recovered.workspace["current"]["product_input"], current.workspace["current"]["product_input"])
        self.assertNotEqual(recovered.workspace["current"]["product_input"]["version"], second["version"])

    def test_post_replace_failure_reopens_with_committed_pointer(self) -> None:
        current, changed, second = self._prepare_second_input_pointer()
        expected_payload = store_module._json_bytes(changed)

        with mock.patch.object(self.store, "_fsync_directory", side_effect=OSError("injected post-commit failure")):
            with self.assertRaisesRegex(OSError, "injected post-commit failure"):
                self.store.save_workspace(changed, expected_etag=current.etag)

        self.assertEqual(self.store.index_path.read_bytes(), expected_payload)
        self.assertEqual(list(self.root.glob(".workspace.json.tmp-*")), [])
        recovered = WorkspaceStore.open(self.root).load_workspace()
        self.assertEqual(recovered.workspace["current"]["product_input"]["version"], second["version"])

    def _run_crash_worker(self, target, args: tuple, expected_exit_code: int) -> None:
        process = multiprocessing.get_context("spawn").Process(target=target, args=args)
        process.start()
        process.join(timeout=15)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
            self.fail(f"crash worker did not exit in time: {target.__name__}")
        self.assertEqual(process.exitcode, expected_exit_code)

    def test_process_crash_before_replace_keeps_old_pointer_and_temp(self) -> None:
        current, changed, second = self._prepare_second_input_pointer()
        original_index = self.store.index_path.read_bytes()
        expected_payload = store_module._json_bytes(changed)

        self._run_crash_worker(
            _crash_before_index_replace, (str(self.root), changed, current.etag), 71
        )

        self.assertEqual(self.store.index_path.read_bytes(), original_index)
        temp_files = list(self.root.glob(".workspace.json.tmp-*"))
        self.assertEqual(len(temp_files), 1)
        self.assertEqual(temp_files[0].read_bytes(), expected_payload)
        recovered = WorkspaceStore.open(self.root).load_workspace()
        self.assertNotEqual(recovered.workspace["current"]["product_input"]["version"], second["version"])

    def test_process_crash_after_replace_recovers_new_pointer(self) -> None:
        current, changed, second = self._prepare_second_input_pointer()
        expected_payload = store_module._json_bytes(changed)

        self._run_crash_worker(
            _crash_after_index_replace, (str(self.root), changed, current.etag), 72
        )

        self.assertEqual(self.store.index_path.read_bytes(), expected_payload)
        self.assertEqual(list(self.root.glob(".workspace.json.tmp-*")), [])
        recovered = WorkspaceStore.open(self.root).load_workspace()
        self.assertEqual(recovered.workspace["current"]["product_input"]["version"], second["version"])

    def test_stale_workspace_etag_cannot_overwrite_newer_pointer(self) -> None:
        current, changed, second = self._prepare_second_input_pointer()
        competing = copy.deepcopy(current.workspace)
        competing["updated_at"] = "2026-09-28T00:04:00Z"

        saved = self.store.save_workspace(changed, expected_etag=current.etag)
        with self.assertRaises(WorkspaceConflict):
            self.store.save_workspace(competing, expected_etag=current.etag)

        recovered = WorkspaceStore.open(self.root).load_workspace()
        self.assertEqual(recovered.etag, saved.etag)
        self.assertEqual(recovered.workspace["current"]["product_input"]["version"], second["version"])

    def test_open_rejects_dangling_current_pointer(self) -> None:
        current, _, _ = self._prepare_second_input_pointer()
        corrupted = copy.deepcopy(current.workspace)
        corrupted["current"]["product_input"]["version"] = 999
        self.store.index_path.write_bytes(store_module._json_bytes(corrupted))

        with self.assertRaises(WorkspaceCorrupt):
            WorkspaceStore.open(self.root)


if __name__ == "__main__":
    unittest.main(verbosity=2)
