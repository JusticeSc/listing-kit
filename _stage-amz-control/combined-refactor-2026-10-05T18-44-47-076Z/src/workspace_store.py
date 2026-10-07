"""Crash-safe, folder-based persistence for Product V1 workspaces."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterator, Mapping

from src import product_v1_contracts as contracts

_POINTER_KINDS = {"product_input", "product_brief", "plan", "selection", "export"}
_LOCAL_LOCKS: dict[str, threading.RLock] = {}
_LOCAL_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS = threading.local()


class WorkspaceStoreError(RuntimeError):
    """Base class for workspace persistence errors."""


class WorkspaceAlreadyExists(WorkspaceStoreError): pass
class WorkspaceNotFound(WorkspaceStoreError): pass
class WorkspaceCorrupt(WorkspaceStoreError): pass
class WorkspaceBusy(WorkspaceStoreError): pass
class WorkspaceConflict(WorkspaceStoreError): pass
class ImmutableRecordConflict(WorkspaceStoreError): pass


@dataclass(frozen=True)
class WorkspaceSnapshot:
    workspace: dict[str, Any]
    etag: str


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise WorkspaceStoreError(f"value is not JSON-serializable: {exc}") from exc
    return (text + "\n").encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_lock(key: str) -> threading.RLock:
    with _LOCAL_LOCKS_GUARD:
        return _LOCAL_LOCKS.setdefault(key, threading.RLock())


class WorkspaceStore:
    """Folder store; immutable files are published before the mutable index."""

    def __init__(self, root: str | Path, *, lock_timeout: float = 10.0) -> None:
        self.root = Path(root).expanduser().resolve(strict=False)
        self.index_path = self.root / "workspace.json"
        self.lock_path = self.root / ".workspace.lock"
        self.lock_timeout = max(0.0, float(lock_timeout))

    @classmethod
    def create(cls, root: str | Path, workspace: Mapping[str, Any], *, lock_timeout: float = 10.0) -> "WorkspaceStore":
        record = copy.deepcopy(dict(workspace))
        cls._validate_workspace_record(record)
        if record["status"] != "NEW" or record["assets"] or any(record["current"].values()):
            raise WorkspaceStoreError("create requires a blank NEW workspace")
        target = Path(root).expanduser().absolute()
        parent = target.parent.resolve(strict=False)
        if target.name in {"", ".", ".."} or not parent.is_dir():
            raise WorkspaceStoreError(f"invalid workspace path or missing parent: {target}")
        target = parent / target.name
        if target.exists() and not target.is_dir():
            raise WorkspaceAlreadyExists(f"workspace path is not a directory: {target}")
        if target.exists() and cls._unexpected_entries(target):
            raise WorkspaceAlreadyExists(f"refusing to create over non-empty directory: {target}")
        if target.exists():
            store = cls(target, lock_timeout=lock_timeout)
            with store.transaction():
                if store.index_path.exists():
                    raise WorkspaceAlreadyExists(f"workspace already exists: {store.index_path}")
                store._write_initial_index(record)
            store.load_workspace()
            return store
        stage = parent / f".amz-workspace-create-{uuid.uuid4().hex}"
        stage.mkdir()
        staged = cls(stage, lock_timeout=lock_timeout)
        with staged.transaction():
            staged._write_initial_index(record)
        try:
            os.rename(stage, target)
        except OSError as exc:
            raise WorkspaceStoreError(f"initialized workspace remains in staging folder {stage}: {exc}") from exc
        store = cls(target, lock_timeout=lock_timeout)
        store.load_workspace()
        return store

    @classmethod
    def open(cls, root: str | Path, *, lock_timeout: float = 10.0) -> "WorkspaceStore":
        store = cls(root, lock_timeout=lock_timeout)
        store.load_workspace()
        return store

    @staticmethod
    def _validate_workspace_record(workspace: Mapping[str, Any]) -> None:
        try:
            contracts.validate_record("workspace", workspace)
        except contracts.ContractError as exc:
            raise WorkspaceStoreError(str(exc)) from exc

    @staticmethod
    def _unexpected_entries(root: Path) -> list[str]:
        allowed = {".workspace.lock"}
        return sorted(entry.name for entry in root.iterdir()
                      if entry.name not in allowed and not entry.name.startswith(".workspace.json.tmp-"))

    @contextlib.contextmanager
    def transaction(self) -> Iterator["WorkspaceStore"]:
        """Hold one workspace lock across a multi-file action."""
        with self._locked():
            yield self

    @contextlib.contextmanager
    def _locked(self) -> Iterator[None]:
        if not self.root.is_dir():
            raise WorkspaceNotFound(f"workspace directory not found: {self.root}")
        key = str(self.root)
        held = getattr(_THREAD_LOCKS, "held", None)
        if held is None:
            held = {}
            _THREAD_LOCKS.held = held
        if key in held:
            held[key] += 1
            try:
                yield
            finally:
                held[key] -= 1
            return

        local = _local_lock(key)
        if not local.acquire(timeout=self.lock_timeout):
            raise WorkspaceBusy(f"workspace is busy in another request: {self.root}")
        handle = None
        os_locked = False
        started = time.monotonic()
        try:
            handle = self.lock_path.open("a+b")
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(handle.fileno())
            while not os_locked:
                handle.seek(0)
                try:
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    os_locked = True
                except OSError:
                    if time.monotonic() - started >= self.lock_timeout:
                        raise WorkspaceBusy(f"workspace is locked by another process: {self.root}")
                    time.sleep(min(0.025, max(0.001, self.lock_timeout / 20)))
            held[key] = 1
            try:
                yield
            finally:
                held.pop(key, None)
        finally:
            if handle is not None:
                if os_locked:
                    try:
                        handle.seek(0)
                        if os.name == "nt":
                            import msvcrt
                            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        pass
                handle.close()
            local.release()

    def _write_initial_index(self, workspace: Mapping[str, Any]) -> None:
        if self.index_path.exists() or self._unexpected_entries(self.root):
            raise WorkspaceAlreadyExists(f"refusing to initialize non-empty directory: {self.root}")
        self._validate_workspace_record(workspace)
        self._verify_workspace_files(workspace)
        temp = self._write_temp(self.index_path, _json_bytes(workspace))
        self._publish_create_only(temp, self.index_path, _json_bytes(workspace))
        self._fsync_directory(self.root)

    def load_workspace(self) -> WorkspaceSnapshot:
        with self._locked():
            return self._load_workspace_unlocked()

    def _load_workspace_unlocked(self) -> WorkspaceSnapshot:
        if not self.index_path.is_file():
            raise WorkspaceNotFound(f"workspace index not found: {self.index_path}")
        raw = self.index_path.read_bytes()
        try:
            workspace = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkspaceCorrupt(f"{self.index_path}: invalid UTF-8 JSON: {exc}") from exc
        if not isinstance(workspace, dict):
            raise WorkspaceCorrupt(f"{self.index_path}: expected a JSON object")
        try:
            self._validate_workspace_record(workspace)
            self._verify_workspace_files(workspace)
            for kind in _POINTER_KINDS:
                ref = workspace["current"][kind]
                if ref is not None:
                    self._resolve_pointer(kind, ref, workspace["workspace_id"])
        except WorkspaceStoreError as exc:
            raise WorkspaceCorrupt(str(exc)) from exc
        return WorkspaceSnapshot(copy.deepcopy(workspace), _sha256(raw))

    def read_asset_by_sha256(self, digest: str) -> tuple[dict[str, Any], bytes]:
        """Read one manifest-owned immutable asset and verify it again before serving it."""
        if (not isinstance(digest, str) or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)):
            raise WorkspaceNotFound("asset digest is invalid")
        snapshot = self.load_workspace()
        asset = next((entry for entry in snapshot.workspace["assets"]
                      if entry.get("sha256") == digest), None)
        if asset is None:
            raise WorkspaceNotFound(f"asset not found: {digest}")
        target = self._safe_target(asset["relative_path"])
        payload = target.read_bytes()
        if _sha256(payload) != digest:
            raise WorkspaceCorrupt(f"asset content hash mismatch: {asset['relative_path']}")
        return copy.deepcopy(asset), payload

    def save_workspace(self, workspace: Mapping[str, Any], *, expected_etag: str) -> WorkspaceSnapshot:
        """Publish a new current-index pointer using compare-and-swap."""
        record = copy.deepcopy(dict(workspace))
        with self._locked():
            current = self._load_workspace_unlocked()
            if current.etag != expected_etag:
                raise WorkspaceConflict(f"stale workspace revision: current ETag is {current.etag}")
            self._validate_workspace_record(record)
            for field in ("workspace_id", "created_at", "app_version"):
                if record[field] != current.workspace[field]:
                    raise WorkspaceStoreError(f"workspace {field} is immutable in Product V1")
            self._verify_assets_append_only(current.workspace["assets"], record["assets"])
            self._verify_workspace_files(record)
            for kind in _POINTER_KINDS:
                ref = record["current"][kind]
                if ref is not None:
                    self._resolve_pointer(kind, ref, record["workspace_id"])
            payload = _json_bytes(record)
            temp = self._write_temp(self.index_path, payload)
            # This is the commit point. On failure, the old pointer is untouched.
            os.replace(temp, self.index_path)
            self._fsync_directory(self.root)
            return WorkspaceSnapshot(record, _sha256(payload))

    def _resolve_pointer(self, kind: str, ref: Mapping[str, Any], workspace_id: str) -> dict[str, Any]:
        if ref.get("kind") != kind:
            raise WorkspaceCorrupt(f"workspace.current.{kind} has wrong ref kind: {ref.get('kind')!r}")
        version = ref["version"]
        filenames = {
            "product_input": self.root / "inputs" / f"product-input-v{version:03d}.json",
            "product_brief": self.root / "briefs" / f"brief-v{version:03d}.json",
            "plan": self.root / "plans" / f"plan-v{version:03d}.json",
            "selection": self.root / "selections" / f"selection-v{version:03d}.json",
            "export": self.root / "exports" / f"export-v{version:03d}" / "record.json",
        }
        path = filenames[kind]
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WorkspaceCorrupt(f"workspace.current.{kind} references unreadable {path}: {exc}") from exc
        if not isinstance(record, dict):
            raise WorkspaceCorrupt(f"workspace.current.{kind} references non-object JSON at {path}")
        try:
            contracts.validate_record(kind, record)
        except contracts.ContractError as exc:
            raise WorkspaceCorrupt(f"{path}: {exc}") from exc
        if record.get(contracts.ID_FIELDS[kind]) != ref["id"] or record.get("version") != version:
            raise WorkspaceCorrupt(f"workspace.current.{kind} does not match the record at {path}")
        if record.get("workspace_id") != workspace_id:
            raise WorkspaceCorrupt(f"workspace.current.{kind} points outside workspace {workspace_id}")
        return record

    def _verify_workspace_files(self, workspace: Mapping[str, Any]) -> None:
        for asset in workspace["assets"]:
            path = self._safe_target(asset["relative_path"])
            if not path.is_file():
                raise WorkspaceCorrupt(f"workspace asset is missing: {asset['relative_path']}")
            size = path.stat().st_size
            if size != asset["byte_size"]:
                raise WorkspaceCorrupt(f"workspace asset size mismatch: {asset['relative_path']}")
            digest = _sha256_file(path)
            if digest != asset["sha256"]:
                raise WorkspaceCorrupt(f"workspace asset hash mismatch: {asset['relative_path']}")

    @staticmethod
    def _verify_assets_append_only(previous: list[Mapping[str, Any]], current: list[Mapping[str, Any]]) -> None:
        by_hash = {asset["sha256"]: asset for asset in current}
        immutable = ("sha256", "relative_path", "original_name", "media_type", "byte_size", "width", "height", "source")
        for old in previous:
            new = by_hash.get(old["sha256"])
            if new is None:
                raise WorkspaceStoreError(f"source asset cannot be removed: {old['sha256']}")
            if any(old.get(field) != new.get(field) for field in immutable):
                raise WorkspaceStoreError(f"source asset identity is immutable: {old['sha256']}")

    def _safe_target(self, relative_path: str, *, for_write: bool = False) -> Path:
        if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path or ":" in relative_path:
            raise WorkspaceStoreError(f"unsafe workspace-relative path: {relative_path!r}")
        parts = relative_path.split("/")
        if any(part in {"", ".", ".."} for part in parts) or PurePosixPath(relative_path).is_absolute():
            raise WorkspaceStoreError(f"unsafe workspace-relative path: {relative_path!r}")
        if for_write and parts[0] in {"workspace.json", ".workspace.lock"}:
            raise WorkspaceStoreError(f"reserved workspace path: {relative_path!r}")
        root = self.root.resolve(strict=False)
        target = self.root.joinpath(*parts)
        resolved = target.resolve(strict=False)
        try:
            common = Path(os.path.commonpath([str(root), str(resolved)]))
        except ValueError as exc:
            raise WorkspaceStoreError(f"workspace path escapes its root: {relative_path!r}") from exc
        if os.path.normcase(str(common)) != os.path.normcase(str(root)):
            raise WorkspaceStoreError(f"workspace path escapes its root: {relative_path!r}")
        cursor = self.root
        for part in parts:
            cursor /= part
            if cursor.exists() and cursor.is_symlink():
                raise WorkspaceStoreError(f"workspace path uses a symlink/junction: {relative_path!r}")
        return target

    def save_immutable_file(self, relative_path: str, data: bytes, *, expected_sha256: str | None = None) -> str:
        """Write source/candidate bytes create-only and return their SHA-256."""
        if not isinstance(data, bytes):
            raise WorkspaceStoreError("immutable file content must be bytes")
        target = self._safe_target(relative_path, for_write=True)
        digest = _sha256(data)
        if expected_sha256 is not None and digest != expected_sha256:
            raise WorkspaceStoreError(f"asset hash mismatch: expected {expected_sha256}, got {digest}")
        with self._locked():
            target = self._safe_target(relative_path, for_write=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if target.is_file() and _sha256_file(target) == digest:
                    return digest
                raise ImmutableRecordConflict(f"refusing to replace immutable file: {target}")
            temp = self._write_temp(target, data)
            self._publish_create_only(temp, target, data)
            self._fsync_directory(target.parent)
            return digest

    def save_record(
        self,
        kind: str,
        record: Mapping[str, Any],
        *,
        expected_etag: str | None = None,
    ) -> dict[str, Any]:
        """Append a record, assigning version and content hash while locked.

        A GenerationAttempt is mutable only through ETag-checked atomic updates.
        Every other stored record is create-only. Save candidate image bytes first.
        """
        if kind not in contracts.DOCUMENT_KINDS - {"workspace"}:
            raise WorkspaceStoreError(f"unsupported workspace record kind: {kind!r}")
        draft = copy.deepcopy(dict(record))
        with self._locked():
            workspace = self._load_workspace_unlocked().workspace
            if draft.get("workspace_id") != workspace["workspace_id"]:
                raise WorkspaceStoreError(f"{kind}.workspace_id does not match the workspace")
            if kind in contracts.VERSIONED_KINDS:
                draft.pop("content_hash", None)
                draft["version"] = self._next_version(kind, draft)
                draft = contracts.seal_record(draft)
            try:
                contracts.validate_record(kind, draft)
            except contracts.ContractError as exc:
                raise WorkspaceStoreError(str(exc)) from exc

            target = self._record_path(kind, draft)
            payload = _json_bytes(draft)
            if kind == "generation_attempt" and target.exists():
                if expected_etag is None:
                    raise WorkspaceConflict("updating a GenerationAttempt requires expected_etag")
                previous_raw = target.read_bytes()
                if _sha256(previous_raw) != expected_etag:
                    raise WorkspaceConflict("stale GenerationAttempt ETag")
                previous = json.loads(previous_raw.decode("utf-8"))
                immutable = (
                    "action_id", "idempotency_key", "workspace_id", "created_at", "shot", "prompt",
                    "provider_id", "model_id", "request_sha256", "reference_asset_sha256",
                )
                if any(previous.get(field) != draft.get(field) for field in immutable):
                    raise WorkspaceStoreError("GenerationAttempt identity and request fields are immutable")
                temp = self._write_temp(target, payload)
                os.replace(temp, target)
                self._fsync_directory(target.parent)
                return draft
            if expected_etag is not None:
                raise WorkspaceConflict("expected_etag is only valid for an existing GenerationAttempt")
            if kind == "candidate":
                self._verify_candidate_bytes(draft)
                for other in self.list_records("candidate"):
                    if other["candidate_id"] == draft["candidate_id"]:
                        raise ImmutableRecordConflict(f"candidate identity already exists: {draft['candidate_id']}")
            self._publish_record_create_only(target, payload)
            return draft

    def get_record(self, kind: str, record_id: str, *, version: int | None = None) -> dict[str, Any]:
        field = contracts.ID_FIELDS.get(kind)
        if kind == "generation_attempt":
            field = "action_id"
        elif kind == "candidate":
            field = "candidate_id"
        if field is None:
            raise WorkspaceStoreError(f"unsupported record identity kind: {kind!r}")
        for item in self.list_records(kind):
            if item.get(field) == record_id and (version is None or item.get("version") == version):
                return item
        raise WorkspaceNotFound(f"record not found: {kind}:{record_id}")

    def get_record_with_etag(
        self, kind: str, record_id: str, *, version: int | None = None,
    ) -> tuple[dict[str, Any], str]:
        """Read one record and the byte-level ETag required for safe mutable-attempt updates."""
        record = self.get_record(kind, record_id, version=version)
        path = self._record_path(kind, record)
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise WorkspaceCorrupt(f"record is unreadable: {path}") from exc
        return record, _sha256(payload)

    def read_candidate_by_sha256(self, digest: str) -> tuple[dict[str, Any], bytes]:
        """Read a candidate only through its manifest record and verify its immutable bytes."""
        if (not isinstance(digest, str) or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)):
            raise WorkspaceNotFound("candidate digest is invalid")
        record = self.get_record("candidate", digest)
        path = self._safe_target(record["relative_path"])
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise WorkspaceCorrupt(f"candidate is unreadable: {record['relative_path']}") from exc
        if _sha256(payload) != record["file_sha256"]:
            raise WorkspaceCorrupt(f"candidate content hash mismatch: {record['relative_path']}")
        return record, payload

    def list_records(self, kind: str) -> list[dict[str, Any]]:
        with self._locked():
            if kind not in contracts.DOCUMENT_KINDS - {"workspace"}:
                raise WorkspaceStoreError(f"unsupported record kind: {kind!r}")
            workspace_id = self._load_workspace_unlocked().workspace["workspace_id"]
            result = []
            for path in self._record_files(kind):
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                    contracts.validate_record(kind, record)
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, contracts.ContractError) as exc:
                    raise WorkspaceCorrupt(f"{path}: invalid record: {exc}") from exc
                if not isinstance(record, dict) or record.get("workspace_id") != workspace_id:
                    raise WorkspaceCorrupt(f"{path}: record belongs to another workspace")
                if self._record_path(kind, record) != path:
                    raise WorkspaceCorrupt(f"{path}: identity/version does not match canonical path")
                result.append(record)
            result.sort(key=lambda item: (int(item.get("version", 0)), str(item.get("action_id", item.get("candidate_id", item.get("id", ""))))))
            return copy.deepcopy(result)

    def _next_version(self, kind: str, record: Mapping[str, Any]) -> int:
        versions = []
        for path in self._record_files(kind, record=record):
            if kind == "export":
                match = re.fullmatch(r"export-v(\d+)", path.parent.name)
            else:
                match = re.search(r"-v(\d+)\.json$", path.name)
            if not match:
                raise WorkspaceCorrupt(f"malformed versioned record path: {path}")
            versions.append(int(match.group(1)))
        # Orphan final files still consume a version; .tmp files are never counted.
        return max(versions, default=0) + 1

    def _record_files(self, kind: str, *, record: Mapping[str, Any] | None = None) -> list[Path]:
        if kind not in contracts.DOCUMENT_KINDS - {"workspace"}:
            raise WorkspaceStoreError(f"unsupported record kind: {kind!r}")
        patterns = {
            "product_input": ("inputs", "product-input-v*.json"),
            "product_brief": ("briefs", "brief-v*.json"),
            "plan": ("plans", "plan-v*.json"),
            "shot_spec": ("shots", "*/spec-v*.json"),
            "prompt": ("shots", "*/prompts/prompt-v*.json"),
            "generation_attempt": ("shots", "*/attempts/*.json"),
            "generation_batch": ("generations", "batch_*.json"),
            "candidate": ("shots", "*/candidates/*.json"),
            "selection": ("selections", "selection-v*.json"),
            "export": ("exports", "export-v*/record.json"),
        }
        folder, pattern = patterns[kind]
        base = self.root / folder
        if record is not None and kind in {"shot_spec", "prompt", "generation_attempt", "candidate"}:
            if kind == "shot_spec":
                base = base / self._safe_component(record["id"])
                pattern = "spec-v*.json"
            else:
                base = base / self._safe_component(record["shot"]["id"])
                if kind == "prompt":
                    base, pattern = base / "prompts", "prompt-v*.json"
                elif kind == "generation_attempt":
                    base, pattern = base / "attempts", "*.json"
                else:
                    base, pattern = base / "candidates", "*.json"
        if not base.exists():
            return []
        return sorted(path for path in base.glob(pattern) if path.is_file() and ".tmp-" not in path.name)

    def _record_path(self, kind: str, record: Mapping[str, Any]) -> Path:
        if kind in {"product_input", "product_brief", "plan", "selection"}:
            folder, stem = {
                "product_input": ("inputs", "product-input"),
                "product_brief": ("briefs", "brief"),
                "plan": ("plans", "plan"),
                "selection": ("selections", "selection"),
            }[kind]
            return self.root / folder / f"{stem}-v{int(record['version']):03d}.json"
        if kind == "shot_spec":
            shot_id = self._safe_component(record["id"])
            return self.root / "shots" / shot_id / f"spec-v{int(record['version']):03d}.json"
        if kind == "prompt":
            shot_id = self._safe_component(record["shot"]["id"])
            return self.root / "shots" / shot_id / "prompts" / f"prompt-v{int(record['version']):03d}.json"
        if kind == "generation_attempt":
            shot_id = self._safe_component(record["shot"]["id"])
            action_id = self._safe_component(record["action_id"])
            return self.root / "shots" / shot_id / "attempts" / f"{action_id}.json"
        if kind == "generation_batch":
            batch_id = self._safe_component(record["id"])
            return self.root / "generations" / f"{batch_id}.json"
        if kind == "candidate":
            shot_id = self._safe_component(record["shot"]["id"])
            candidate_id = self._safe_component(record["candidate_id"])
            return self.root / "shots" / shot_id / "candidates" / f"{candidate_id}.json"
        if kind == "export":
            return self.root / "exports" / f"export-v{int(record['version']):03d}" / "record.json"
        raise WorkspaceStoreError(f"unsupported record kind: {kind!r}")

    @staticmethod
    def _safe_component(value: Any) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
            raise WorkspaceStoreError(f"unsafe path component: {value!r}")
        return value

    def _verify_candidate_bytes(self, record: Mapping[str, Any]) -> None:
        path = self._safe_target(record["relative_path"])
        if not path.is_file():
            raise WorkspaceStoreError(f"candidate bytes must be written first: {record['relative_path']}")
        if _sha256_file(path) != record["file_sha256"]:
            raise WorkspaceStoreError(f"candidate image hash mismatch: {record['relative_path']}")

    def _publish_record_create_only(self, target: Path, payload: bytes) -> None:
        relative = target.relative_to(self.root).as_posix()
        target = self._safe_target(relative, for_write=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.is_file() and target.read_bytes() == payload:
                return
            raise ImmutableRecordConflict(f"refusing to replace immutable record: {target}")
        temp = self._write_temp(target, payload)
        self._publish_create_only(temp, target, payload)
        self._fsync_directory(target.parent)

    def _write_temp(self, target: Path, payload: bytes) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.parent / f".{target.name}.tmp-{uuid.uuid4().hex}"
        try:
            with temp.open("xb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            # Keep partial temp files for diagnosis; readers never load them.
            raise
        return temp

    @staticmethod
    def _publish_create_only(temp: Path, target: Path, payload: bytes) -> None:
        try:
            if os.name == "nt":
                os.rename(temp, target)  # Windows rename fails if target exists.
            else:
                os.link(temp, target)  # Atomic create-only publish on one filesystem.
                temp.unlink()
        except FileExistsError:
            if target.is_file() and target.read_bytes() == payload:
                temp.unlink(missing_ok=True)
                return
            raise ImmutableRecordConflict(f"immutable target already exists: {target}")

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        if os.name == "nt":
            return
        try:
            descriptor = os.open(directory, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)
