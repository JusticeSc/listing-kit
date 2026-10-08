#!/usr/bin/env python
"""Bounded concurrency checks for WorkspaceStore's thread and process locks."""
from __future__ import annotations

import multiprocessing
import queue
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.workspace_store import WorkspaceBusy, WorkspaceStore  # noqa: E402


def _hold_lock_in_process(root: str, acquired, release, results) -> None:
    """Spawn-safe worker that owns the workspace lock until released."""
    try:
        with WorkspaceStore(root, lock_timeout=5.0).transaction():
            acquired.set()
            if not release.wait(12.0):
                raise TimeoutError("test parent did not release process lock")
        results.put(("ok", "released"))
    except BaseException as exc:
        results.put(("error", f"{type(exc).__name__}: {exc}"))
        raise


class WorkspaceStoreConcurrencyChecks(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="amz-workspace-lock-")
        self.root = Path(self.temp.name) / "workspace"
        self.root.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_thread_contender_times_out_while_lock_is_held_and_recovers(self) -> None:
        holder_ready = threading.Event()
        holder_release = threading.Event()
        holder_errors: list[str] = []

        def hold_in_thread() -> None:
            try:
                with WorkspaceStore(self.root, lock_timeout=3.0).transaction():
                    holder_ready.set()
                    if not holder_release.wait(8.0):
                        holder_errors.append("test parent did not release thread lock")
            except BaseException as exc:
                holder_errors.append(f"{type(exc).__name__}: {exc}")
                holder_ready.set()

        holder = threading.Thread(target=hold_in_thread, name="workspace-lock-holder", daemon=True)
        holder.start()
        self.assertTrue(holder_ready.wait(3.0), "holder thread did not acquire the workspace lock")
        self.assertEqual(holder_errors, [], "holder failed before exercising contention")

        timeout = 0.25
        contender_done = threading.Event()
        contender_result: dict[str, object] = {}

        def contend_in_thread() -> None:
            started = time.monotonic()
            try:
                with WorkspaceStore(self.root, lock_timeout=timeout).transaction():
                    contender_result["acquired"] = True
            except WorkspaceBusy as exc:
                contender_result["busy"] = str(exc)
                contender_result["elapsed"] = time.monotonic() - started
            except BaseException as exc:
                contender_result["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                contender_done.set()

        contender = threading.Thread(target=contend_in_thread, name="workspace-lock-contender", daemon=True)
        try:
            contender.start()
            self.assertTrue(
                contender_done.wait(2.0),
                "thread contender did not honor its finite lock timeout while the holder remained active",
            )
            self.assertIn("busy", contender_result, f"contender outcome was {contender_result!r}")
            self.assertNotIn("acquired", contender_result, "two threads entered one workspace transaction")
            self.assertNotIn("error", contender_result, f"unexpected contender failure: {contender_result!r}")
            self.assertGreaterEqual(
                float(contender_result["elapsed"]), timeout * 0.5,
                "contender reported busy before waiting for the configured timeout",
            )
        finally:
            holder_release.set()
            holder.join(4.0)
            if contender.ident is not None:
                contender.join(4.0)

        self.assertFalse(holder.is_alive(), "holder thread leaked after release")
        self.assertFalse(contender.is_alive(), "contender thread leaked after release")
        self.assertEqual(holder_errors, [])
        with WorkspaceStore(self.root, lock_timeout=0.5).transaction():
            pass

    def test_spawned_process_lock_excludes_other_process_until_release(self) -> None:
        context = multiprocessing.get_context("spawn")
        owner_ready = context.Event()
        owner_release = context.Event()
        results = context.Queue()
        owner = context.Process(
            target=_hold_lock_in_process,
            args=(str(self.root), owner_ready, owner_release, results),
            name="workspace-process-lock-owner",
        )
        owner.start()

        timeout = 0.3
        contender_done = threading.Event()
        contender_result: dict[str, object] = {}

        def contend_across_process_boundary() -> None:
            started = time.monotonic()
            try:
                with WorkspaceStore(self.root, lock_timeout=timeout).transaction():
                    contender_result["acquired"] = True
            except WorkspaceBusy as exc:
                contender_result["busy"] = str(exc)
                contender_result["elapsed"] = time.monotonic() - started
            except BaseException as exc:
                contender_result["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                contender_done.set()

        contender = threading.Thread(
            target=contend_across_process_boundary,
            name="workspace-cross-process-contender",
            daemon=True,
        )
        owner_result = None
        try:
            self.assertTrue(owner_ready.wait(12.0), "spawned process did not acquire the workspace lock")
            self.assertIsNone(owner.exitcode, "lock owner exited before the contention check")
            contender.start()
            self.assertTrue(
                contender_done.wait(3.0),
                "cross-process contender did not honor its finite lock timeout while owner remained active",
            )
            self.assertIn("busy", contender_result, f"contender outcome was {contender_result!r}")
            self.assertNotIn("acquired", contender_result, "two processes entered one workspace transaction")
            self.assertNotIn("error", contender_result, f"unexpected contender failure: {contender_result!r}")
            self.assertGreaterEqual(
                float(contender_result["elapsed"]), timeout * 0.5,
                "contender reported busy before waiting for the configured timeout",
            )
        finally:
            owner_release.set()
            owner.join(6.0)
            if owner.is_alive():
                owner.terminate()
                owner.join(3.0)
            if contender.ident is not None:
                contender.join(6.0)
            try:
                owner_result = results.get(timeout=1.0)
            except queue.Empty:
                pass
            results.close()
            results.join_thread()

        self.assertFalse(owner.is_alive(), "spawned lock owner leaked after release")
        self.assertEqual(owner.exitcode, 0, "spawned lock owner failed; see its traceback above")
        self.assertFalse(contender.is_alive(), "cross-process contender leaked after release")
        self.assertEqual(owner_result, ("ok", "released"))
        with WorkspaceStore(self.root, lock_timeout=0.5).transaction():
            pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
