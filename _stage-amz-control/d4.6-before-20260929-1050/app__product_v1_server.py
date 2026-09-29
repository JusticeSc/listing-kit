"""HTTP transport and local workspace navigation for Product V1."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Mapping

from src.application_service import ApplicationService, ImageUpload, ServiceResponse
from src.workspace_store import WorkspaceStore, WorkspaceStoreError

ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = ROOT / "app" / "product_v1"
STATIC_TYPES = {
    "index.html": "text/html; charset=utf-8",
    "styles.css": "text/css; charset=utf-8",
    "product.js": "text/javascript; charset=utf-8",
}
MAX_REQUEST_BYTES = 80 * 1024 * 1024


def _open_directory(path: str) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _safe_workspace_path(root: Path, relative_path: object) -> Path:
    """Resolve a workspace-relative file path, refusing separators or escapes."""
    if not isinstance(relative_path, str) or not relative_path:
        raise ValueError("workspace-relative path is required")
    if "\\" in relative_path or ":" in relative_path:
        raise ValueError("workspace-relative path must use forward slashes only")
    parts = relative_path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("workspace-relative path contains an unsafe component")
    root_resolved = root.resolve()
    target = root_resolved.joinpath(*parts).resolve()
    if os.path.commonpath([str(root_resolved), str(target)]) != str(root_resolved):
        raise ValueError("workspace-relative path escapes the workspace")
    return target


class FolderPickerError(RuntimeError):
    pass


def _envelope_error(
    code: str,
    message: str,
    *,
    status: int,
    field: str | None = None,
    next_action: str | None = None,
    details: Mapping[str, object] | None = None,
) -> ServiceResponse:
    return ServiceResponse(status, {
        "ok": False, "data": None, "error": {
            "code": code, "message": message, "field": field,
            "recoverable": status < 500, "next_action": next_action,
            "details": dict(details or {}),
        },
    })


class RecentWorkspaceIndex:
    """Navigation links only; workspace business state stays in WorkspaceStore."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path).expanduser()
        self._lock = threading.RLock()

    def list(self) -> list[dict[str, str]]:
        with self._lock:
            if not self.path.is_file():
                return []
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("recent workspace index is unreadable") from exc
            if (not isinstance(raw, dict)
                    or raw.get("schema") != "amz-listing-kit/recent-workspaces@1"
                    or not isinstance(raw.get("items"), list)):
                raise ValueError("recent workspace index has an unsupported shape")
            items = []
            for item in raw["items"]:
                if not isinstance(item, dict):
                    continue
                directory = item.get("directory")
                workspace_id = item.get("workspace_id")
                updated_at = item.get("updated_at")
                if not all(isinstance(value, str) and value for value in
                           (directory, workspace_id, updated_at)):
                    continue
                items.append({
                    "directory": directory,
                    "name": str(item.get("name") or Path(directory).name or directory),
                    "workspace_id": workspace_id,
                    "updated_at": updated_at,
                })
            return items[:10]

    def remember(self, directory: str | os.PathLike[str], projection: Mapping[str, object]) -> None:
        workspace = projection.get("workspace")
        if not isinstance(workspace, Mapping):
            return
        target = Path(directory).expanduser().resolve()
        new_item = {
            "directory": str(target), "name": target.name or str(target),
            "workspace_id": str(workspace.get("id") or ""),
            "updated_at": str(workspace.get("updated_at") or ""),
        }
        if not new_item["workspace_id"] or not new_item["updated_at"]:
            return
        with self._lock:
            items = self.list()
            key = os.path.normcase(str(target))
            items = [item for item in items
                     if os.path.normcase(str(Path(item["directory"]).expanduser())) != key]
            items.insert(0, new_item)
            payload = json.dumps(
                {"schema": "amz-listing-kit/recent-workspaces@1", "items": items[:10]},
                ensure_ascii=False, indent=2,
            ).encode("utf-8")
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(prefix=".recent-", suffix=".tmp", dir=self.path.parent)
            temp_path = Path(temp_name)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp_path, self.path)
            finally:
                temp_path.unlink(missing_ok=True)


def _default_recent_index_path() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = str(Path.home() / ".local" / "share")
    return Path(base) / "AMZ Listing Kit" / "recent-workspaces.json"


def choose_windows_directory(purpose: str) -> str | None:
    """Show a native folder picker without asking the user to type an absolute path."""
    if os.name != "nt":
        raise FolderPickerError("本机文件夹选择目前仅支持 Windows。")
    executable = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if not executable:
        raise FolderPickerError("未找到 Windows PowerShell，暂时无法打开文件夹选择器。")
    output = tempfile.NamedTemporaryFile(prefix="amz-folder-", suffix=".txt", delete=False)
    output_path = Path(output.name)
    output.close()
    title = ("选择空文件夹，或点‘新建文件夹’建立商品工作空间"
             if purpose == "create" else "选择已存在的商品工作空间文件夹")
    script = r"""
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = $env:AMZ_FOLDER_PICKER_TITLE
$dialog.ShowNewFolderButton = ($env:AMZ_FOLDER_PICKER_PURPOSE -eq 'create')
$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK -and $dialog.SelectedPath) {
  [System.IO.File]::WriteAllText($env:AMZ_FOLDER_PICKER_OUTPUT, $dialog.SelectedPath,
    [System.Text.UTF8Encoding]::new($false))
}
$dialog.Dispose()
"""
    env = os.environ.copy()
    env["AMZ_FOLDER_PICKER_TITLE"] = title
    env["AMZ_FOLDER_PICKER_PURPOSE"] = purpose
    env["AMZ_FOLDER_PICKER_OUTPUT"] = str(output_path)
    try:
        result = subprocess.run(
            [executable, "-NoProfile", "-STA", "-WindowStyle", "Hidden", "-Command", script],
            env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=900, check=False,
        )
        if result.returncode != 0:
            raise FolderPickerError("文件夹选择器没有正常打开，请重试。")
        selected = output_path.read_text(encoding="utf-8-sig").strip()
        return selected or None
    except subprocess.TimeoutExpired as exc:
        raise FolderPickerError("文件夹选择器等待时间过长，请重新打开后再试。") from exc
    except OSError as exc:
        raise FolderPickerError("无法启动 Windows 文件夹选择器，请重试。") from exc
    finally:
        output_path.unlink(missing_ok=True)


class ProductApplication:
    def __init__(
        self,
        *,
        service: ApplicationService | None = None,
        recent_index_path: str | os.PathLike[str] | None = None,
        folder_picker: Callable[[str], str | None] = choose_windows_directory,
        reveal_opener: Callable[[str], None] = _open_directory,
    ) -> None:
        self.service = service or ApplicationService()
        self.recent = RecentWorkspaceIndex(recent_index_path or _default_recent_index_path())
        self.folder_picker = folder_picker
        self.reveal_opener = reveal_opener

    def list_recent(self) -> ServiceResponse:
        try:
            return ServiceResponse(200, {
                "ok": True, "data": {"workspaces": self.recent.list()}, "error": None,
            })
        except ValueError:
            return _envelope_error(
                "RECENT_LIST_UNAVAILABLE",
                "最近使用列表无法读取；仍可直接打开已有工作空间文件夹。",
                status=500,
                field="recent_workspaces",
                next_action="open_workspace_folder",
            )

    def select_directory(self, purpose: str) -> ServiceResponse:
        if purpose not in {"create", "open"}:
            return _envelope_error(
                "REQUEST_INVALID", "请选择新建或打开工作空间。", status=400,
                field="purpose", next_action="choose_workspace_action",
            )
        try:
            directory = self.folder_picker(purpose)
        except FolderPickerError as exc:
            return _envelope_error(
                "FOLDER_PICKER_UNAVAILABLE", str(exc), status=501,
                field="directory", next_action="retry_folder_picker",
            )
        except Exception as exc:
            return _envelope_error(
                "FOLDER_PICKER_FAILED", "文件夹选择器打开失败，请重试。", status=500,
                field="directory", next_action="retry_folder_picker",
                details={"error_type": type(exc).__name__},
            )
        return ServiceResponse(200, {
            "ok": True, "data": {"directory": directory}, "error": None,
        })

    def create_workspace(self, directory: str) -> ServiceResponse:
        return self._remember_after_success(self.service.create_workspace(directory), directory)

    def open_workspace(self, directory: str) -> ServiceResponse:
        return self._remember_after_success(self.service.open_workspace(directory), directory)

    def get_workspace(self, directory: str | None) -> ServiceResponse:
        if not directory:
            return _envelope_error(
                "WORKSPACE_NOT_SELECTED", "请先新建或打开一个工作空间。", status=409,
                field="directory", next_action="open_workspace",
            )
        return self.service.get_workspace_projection(directory)

    def save_intake(
        self,
        *,
        directory: str | None,
        expected_etag: str | None,
        product_name: str,
        description: str,
        selling_points: list[str],
        user_intent: str,
        reference_images: list[ImageUpload],
    ) -> ServiceResponse:
        if not directory:
            return _envelope_error(
                "WORKSPACE_NOT_SELECTED", "请先新建或打开一个工作空间。", status=409,
                field="directory", next_action="open_workspace",
            )
        return self._remember_after_success(
            self.service.save_intake(
                directory,
                expected_etag=expected_etag,
                product_name=product_name,
                description=description,
                selling_points=selling_points,
                user_intent=user_intent,
                reference_images=reference_images or None,
            ),
            directory,
        )

    def generate_product_brief_draft(
        self, *, directory: str | None, expected_etag: str | None,
    ) -> ServiceResponse:
        if not directory:
            return _envelope_error(
                "WORKSPACE_NOT_SELECTED", "请先打开一个工作空间。", status=409,
                field="directory", next_action="open_workspace",
            )
        return self.service.generate_product_brief_draft(directory, expected_etag=expected_etag)

    def save_product_brief(
        self, *, directory: str | None, expected_etag: str | None,
        fields: Mapping[str, object],
    ) -> ServiceResponse:
        if not directory:
            return _envelope_error(
                "WORKSPACE_NOT_SELECTED", "请先打开一个工作空间。", status=409,
                field="directory", next_action="open_workspace",
            )
        return self.service.save_product_brief(
            directory, expected_etag=expected_etag, fields=fields,
        )

    def generate_product_plan(
        self, *, directory: str | None, expected_etag: str | None,
    ) -> ServiceResponse:
        if not directory:
            return _envelope_error(
                "WORKSPACE_NOT_SELECTED", "请先打开一个工作空间。", status=409,
                field="directory", next_action="open_workspace",
            )
        return self.service.generate_product_plan(directory, expected_etag=expected_etag)

    def save_product_plan(
        self, *, directory: str | None, expected_etag: str | None,
        plan: Mapping[str, object] | None,
    ) -> ServiceResponse:
        if not directory:
            return _envelope_error(
                "WORKSPACE_NOT_SELECTED", "请先打开一个工作空间。", status=409,
                field="directory", next_action="open_workspace",
            )
        return self.service.save_product_plan(
            directory, expected_etag=expected_etag, plan=plan,
        )

    def generate_prompt(
        self, *, directory: str | None, expected_etag: str | None,
        shot_id: str | None,
    ) -> ServiceResponse:
        if not directory:
            return _envelope_error(
                "WORKSPACE_NOT_SELECTED", "请先打开一个工作空间。", status=409,
                field="directory", next_action="open_workspace",
            )
        return self.service.generate_prompt(
            directory, expected_etag=expected_etag, shot_id=shot_id,
        )

    def save_prompt_edit(
        self, *, directory: str | None, expected_etag: str | None,
        shot_id: str | None, expected_prompt_version: int | None,
        full_text: str | None,
        reason: str | None = None,
    ) -> ServiceResponse:
        if not directory:
            return _envelope_error(
                "WORKSPACE_NOT_SELECTED", "请先打开一个工作空间。", status=409,
                field="directory", next_action="open_workspace",
            )
        return self.service.save_prompt_edit(
            directory,
            expected_etag=expected_etag,
            shot_id=shot_id,
            expected_prompt_version=expected_prompt_version,
            full_text=full_text,
            reason=reason,
        )

    def read_reference(self, directory: str | None, sha256: str):
        if not directory:
            raise FileNotFoundError("workspace is not selected")
        return WorkspaceStore.open(directory).read_asset_by_sha256(sha256)

    def start_generation_set(
        self, *, directory: str | None, expected_etag: str | None,
        idempotency_key: str | None,
    ) -> ServiceResponse:
        if not directory:
            return _envelope_error(
                "WORKSPACE_NOT_SELECTED", "请先打开一个工作空间。", status=409,
                field="directory", next_action="open_workspace",
            )
        return self.service.start_generation_set(
            directory, expected_etag=expected_etag, idempotency_key=idempotency_key,
        )

    def reconcile_generation(
        self, *, directory: str | None, action_ids: object,
    ) -> ServiceResponse:
        if not directory:
            return _envelope_error(
                "WORKSPACE_NOT_SELECTED", "请先打开一个工作空间。", status=409,
                field="directory", next_action="open_workspace",
            )
        return self.service.reconcile_generation(directory, action_ids=action_ids)

    def abandon_generation_attempt(
        self, *, directory: str | None, expected_etag: str | None,
        action_id: str | None, reason: str | None,
    ) -> ServiceResponse:
        if not directory:
            return _envelope_error(
                "WORKSPACE_NOT_SELECTED", "请先打开一个工作空间。", status=409,
                field="directory", next_action="open_workspace",
            )
        return self.service.abandon_generation_attempt(
            directory, expected_etag=expected_etag, action_id=action_id, reason=reason,
        )

    def read_candidate(self, directory: str | None, sha256: str):
        if not directory:
            raise FileNotFoundError("workspace is not selected")
        return WorkspaceStore.open(directory).read_candidate_by_sha256(sha256)

    def save_selection(
        self, *, directory: str | None, expected_etag: str | None, choices: object,
    ) -> ServiceResponse:
        if not directory:
            return _envelope_error(
                "WORKSPACE_NOT_SELECTED", "请先打开一个工作空间。", status=409,
                field="directory", next_action="open_workspace",
            )
        return self.service.save_selection(
            directory, expected_etag=expected_etag, choices=choices,
        )

    def start_shot_generation(
        self, *, directory: str | None, expected_etag: str | None,
        shot_id: str | None, idempotency_key: str | None,
    ) -> ServiceResponse:
        if not directory:
            return _envelope_error(
                "WORKSPACE_NOT_SELECTED", "请先打开一个工作空间。", status=409,
                field="directory", next_action="open_workspace",
            )
        return self.service.start_shot_generation(
            directory, expected_etag=expected_etag, shot_id=shot_id,
            idempotency_key=idempotency_key,
        )

    def export_selection(
        self, *, directory: str | None, expected_etag: str | None,
    ) -> ServiceResponse:
        if not directory:
            return _envelope_error(
                "WORKSPACE_NOT_SELECTED", "请先打开一个工作空间。", status=409,
                field="directory", next_action="open_workspace",
            )
        return self.service.export_selection(directory, expected_etag=expected_etag)

    @staticmethod
    def _latest_export(store: WorkspaceStore, export_id: object) -> dict | None:
        if (
            not isinstance(export_id, str)
            or not export_id.startswith("export_")
            or not all(char.isalnum() or char in "_-" for char in export_id)
        ):
            return None
        records = [
            record for record in store.list_records("export") if record["id"] == export_id
        ]
        return max(records, key=lambda record: record["version"]) if records else None

    def reveal_export(self, *, directory: str | None, export_id: str | None) -> ServiceResponse:
        if not directory:
            return _envelope_error(
                "WORKSPACE_NOT_SELECTED", "请先打开一个工作空间。", status=409,
                field="directory", next_action="open_workspace",
            )
        try:
            store = WorkspaceStore.open(directory)
            record = self._latest_export(store, export_id)
        except (WorkspaceStoreError, OSError, ValueError):
            record = None
        if record is None:
            return _envelope_error(
                "EXPORT_NOT_FOUND", "找不到这个交付包，请先完成导出。", status=404,
                field="export", next_action="export_selection",
            )
        try:
            target = _safe_workspace_path(Path(directory), record["relative_path"])
        except ValueError:
            return _envelope_error(
                "EXPORT_PATH_INVALID", "交付包路径无效，请重新导出。", status=409,
                field="export", next_action="export_selection",
            )
        if not target.is_dir():
            return _envelope_error(
                "EXPORT_DIRECTORY_MISSING", "交付包文件夹已不存在，请重新导出。", status=409,
                field="export", next_action="export_selection",
            )
        try:
            self.reveal_opener(str(target))
        except Exception as exc:  # the opener is an OS side effect; never crash the request
            return _envelope_error(
                "REVEAL_FAILED", "无法自动打开文件夹，请手动打开导出目录。", status=500,
                field="export", next_action="open_export_folder_manually",
                details={"path": str(target), "error_type": type(exc).__name__},
            )
        return ServiceResponse(200, {
            "ok": True, "data": {"revealed": True, "path": str(target)}, "error": None,
        })

    def read_export_file(self, directory: str | None, export_id: str, index: int):
        if not directory:
            raise FileNotFoundError("workspace is not selected")
        store = WorkspaceStore.open(directory)
        record = self._latest_export(store, export_id)
        if record is None:
            raise FileNotFoundError("export record not found")
        files = record.get("files") or []
        if not isinstance(index, int) or isinstance(index, bool) or index < 0 or index >= len(files):
            raise FileNotFoundError("export file index out of range")
        entry = files[index]
        path = _safe_workspace_path(Path(directory), entry.get("relative_path"))
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise FileNotFoundError("export file is unreadable") from exc
        media_type = "image/png" if str(entry.get("relative_path")).lower().endswith(".png") else "image/jpeg"
        return record, entry, content, media_type

    def _remember_after_success(self, response: ServiceResponse, directory: str) -> ServiceResponse:
        if not response.ok:
            return response
        try:
            self.recent.remember(directory, response.body["data"])
        except (OSError, ValueError, TypeError):
            body = json.loads(json.dumps(response.body))
            body["data"]["recent_index_warning"] = "工作空间已打开，但最近使用列表未能更新。"
            return ServiceResponse(response.status_code, body)
        return response


def _first_string(value: object) -> str | None:
    if isinstance(value, list):
        return value[0] if value and isinstance(value[0], str) else None
    return value if isinstance(value, str) else None


class ProductRequestHandler(BaseHTTPRequestHandler):
    application: ProductApplication
    server_version = "AMZListingKit/1"

    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        path = urllib.parse.unquote(parsed.path)
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
        if path in {"/", "/product"}:
            self._send_file("index.html", cache="no-cache")
            return
        if path.startswith("/product-assets/"):
            self._send_file(path.removeprefix("/product-assets/"), cache="no-cache")
            return
        if path == "/api/workspaces/recent":
            self._send_service(self.application.list_recent())
            return
        if path == "/api/workspace":
            self._send_service(self.application.get_workspace(
                (query.get("directory") or [None])[0]
            ))
            return
        prefix = "/api/workspace/references/"
        if path.startswith(prefix):
            digest = path.removeprefix(prefix)
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                self._send_service(_envelope_error(
                    "REFERENCE_NOT_FOUND", "找不到这张参考图。", status=404,
                    field="reference_images", next_action="reload_workspace",
                ))
                return
            try:
                asset, content = self.application.read_reference(
                    (query.get("directory") or [None])[0], digest
                )
            except (FileNotFoundError, WorkspaceStoreError, OSError):
                self._send_service(_envelope_error(
                    "REFERENCE_NOT_FOUND", "找不到这张参考图，请重新载入工作空间。", status=404,
                    field="reference_images", next_action="reload_workspace",
                ))
                return
            media_type = str(asset.get("media_type") or "application/octet-stream")
            if media_type not in {"image/jpeg", "image/png", "image/tiff", "image/gif"}:
                media_type = "application/octet-stream"
            self._send_bytes(200, content, media_type,
                             cache="private, max-age=31536000, immutable")
            return
        prefix = "/api/candidates/"
        if path.startswith(prefix):
            digest = path.removeprefix(prefix)
            if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                self._send_service(_envelope_error(
                    "CANDIDATE_NOT_FOUND", "找不到这张生成图片。", status=404,
                    field="candidate", next_action="reload_workspace",
                ))
                return
            try:
                candidate, content = self.application.read_candidate(
                    (query.get("directory") or [None])[0], digest
                )
            except (FileNotFoundError, WorkspaceStoreError, OSError):
                self._send_service(_envelope_error(
                    "CANDIDATE_NOT_FOUND", "找不到这张生成图片，请重新载入工作空间。", status=404,
                    field="candidate", next_action="reload_workspace",
                ))
                return
            media_type = candidate.get("media_type")
            if media_type not in {"image/jpeg", "image/png", "image/tiff"}:
                media_type = "application/octet-stream"
            self._send_bytes(200, content, media_type,
                             cache="private, max-age=31536000, immutable")
            return
        prefix = "/api/exports/"
        if path.startswith(prefix):
            parts = path.removeprefix(prefix).split("/")
            # GET /api/exports/<export_id>/files/<index> serves an exported image (0-based index).
            if len(parts) == 3 and parts[1] == "files" and parts[2].isdigit():
                try:
                    _record, _entry, content, media_type = self.application.read_export_file(
                        (query.get("directory") or [None])[0], parts[0], int(parts[2]),
                    )
                except (FileNotFoundError, WorkspaceStoreError, OSError, ValueError):
                    self._send_service(_envelope_error(
                        "EXPORT_FILE_NOT_FOUND", "找不到这个交付文件，请重新载入工作空间。",
                        status=404, field="export", next_action="reload_workspace",
                    ))
                    return
                self._send_bytes(200, content, media_type,
                                 cache="private, max-age=31536000, immutable")
                return
        self._send_service(_envelope_error(
            "NOT_FOUND", "没有找到这个页面。", status=404, next_action="go_home",
        ))

    def do_POST(self):  # noqa: N802
        if not self._same_origin():
            return
        path = urllib.parse.urlsplit(self.path).path
        if path in {"/api/workspaces/select-folder", "/api/workspaces", "/api/workspaces/open"}:
            parsed = self._read_json()
            if parsed is None:
                return
            if path.endswith("select-folder"):
                purpose = parsed.get("purpose")
                if not isinstance(purpose, str):
                    self._send_service(_envelope_error(
                        "REQUEST_INVALID", "请选择新建或打开工作空间。", status=400,
                        field="purpose", next_action="choose_workspace_action",
                    ))
                    return
                self._send_service(self.application.select_directory(purpose))
                return
            directory = parsed.get("directory")
            if not isinstance(directory, str) or not directory.strip():
                self._send_service(_envelope_error(
                    "DIRECTORY_REQUIRED", "请选择工作空间文件夹。", status=400,
                    field="directory", next_action="choose_workspace_folder",
                ))
                return
            if path == "/api/workspaces":
                self._send_service(self.application.create_workspace(directory))
            else:
                self._send_service(self.application.open_workspace(directory))
            return
        if path == "/api/intake":
            form = self._read_multipart()
            if form is not None:
                self._send_service(self._save_from_form(form))
            return
        if path == "/api/product-brief/draft":
            parsed = self._read_json()
            if parsed is not None:
                self._send_service(self.application.generate_product_brief_draft(
                    directory=_first_string(parsed.get("directory")),
                    expected_etag=_first_string(parsed.get("expected_etag")),
                ))
            return
        if path == "/api/plan/generate":
            parsed = self._read_json()
            if parsed is not None:
                self._send_service(self.application.generate_product_plan(
                    directory=_first_string(parsed.get("directory")),
                    expected_etag=_first_string(parsed.get("expected_etag")),
                ))
            return
        if path == "/api/prompt/compile":
            parsed = self._read_json()
            if parsed is not None:
                self._send_service(self.application.generate_prompt(
                    directory=_first_string(parsed.get("directory")),
                    expected_etag=_first_string(parsed.get("expected_etag")),
                    shot_id=_first_string(parsed.get("shot_id")),
                ))
            return
        if path == "/api/generation/start":
            parsed = self._read_json()
            if parsed is not None:
                self._send_service(self.application.start_generation_set(
                    directory=_first_string(parsed.get("directory")),
                    expected_etag=_first_string(parsed.get("expected_etag")),
                    idempotency_key=_first_string(parsed.get("idempotency_key")),
                ))
            return
        if path == "/api/generation/reconcile":
            parsed = self._read_json()
            if parsed is not None:
                self._send_service(self.application.reconcile_generation(
                    directory=_first_string(parsed.get("directory")),
                    action_ids=parsed.get("action_ids"),
                ))
            return
        if path == "/api/selection":
            parsed = self._read_json()
            if parsed is not None:
                self._send_service(self.application.save_selection(
                    directory=_first_string(parsed.get("directory")),
                    expected_etag=_first_string(parsed.get("expected_etag")),
                    choices=parsed.get("choices"),
                ))
            return
        if path == "/api/generation/rework":
            parsed = self._read_json()
            if parsed is not None:
                self._send_service(self.application.start_shot_generation(
                    directory=_first_string(parsed.get("directory")),
                    expected_etag=_first_string(parsed.get("expected_etag")),
                    shot_id=_first_string(parsed.get("shot_id")),
                    idempotency_key=_first_string(parsed.get("idempotency_key")),
                ))
            return
        if path == "/api/generation/abandon":
            parsed = self._read_json()
            if parsed is not None:
                self._send_service(self.application.abandon_generation_attempt(
                    directory=_first_string(parsed.get("directory")),
                    expected_etag=_first_string(parsed.get("expected_etag")),
                    action_id=_first_string(parsed.get("action_id")),
                    reason=_first_string(parsed.get("reason")),
                ))
            return
        if path == "/api/export":
            parsed = self._read_json()
            if parsed is not None:
                self._send_service(self.application.export_selection(
                    directory=_first_string(parsed.get("directory")),
                    expected_etag=_first_string(parsed.get("expected_etag")),
                ))
            return
        if path == "/api/export/reveal":
            parsed = self._read_json()
            if parsed is not None:
                self._send_service(self.application.reveal_export(
                    directory=_first_string(parsed.get("directory")),
                    export_id=_first_string(parsed.get("export_id")),
                ))
            return
        self._send_service(_envelope_error(
            "NOT_FOUND", "没有找到这个操作。", status=404, next_action="go_home",
        ))

    def do_PUT(self):  # noqa: N802
        if not self._same_origin():
            return
        path = urllib.parse.urlsplit(self.path).path
        if path == "/api/prompt":
            parsed = self._read_json()
            if parsed is not None:
                expected_prompt_version = parsed.get("expected_prompt_version")
                if isinstance(expected_prompt_version, bool) or not isinstance(expected_prompt_version, int):
                    expected_prompt_version = None
                full_text = parsed.get("full_text")
                reason = parsed.get("reason")
                self._send_service(self.application.save_prompt_edit(
                    directory=_first_string(parsed.get("directory")),
                    expected_etag=_first_string(parsed.get("expected_etag")),
                    shot_id=_first_string(parsed.get("shot_id")),
                    expected_prompt_version=expected_prompt_version,
                    full_text=full_text if isinstance(full_text, str) else None,
                    reason=reason if isinstance(reason, str) else None,
                ))
            return
        if path == "/api/plan":
            parsed = self._read_json()
            if parsed is not None:
                plan = parsed.get("plan")
                self._send_service(self.application.save_product_plan(
                    directory=_first_string(parsed.get("directory")),
                    expected_etag=_first_string(parsed.get("expected_etag")),
                    plan=plan if isinstance(plan, Mapping) else None,
                ))
            return
        if path == "/api/product-brief":
            parsed = self._read_json()
            if parsed is not None:
                fields = parsed.get("product_brief")
                if not isinstance(fields, dict):
                    self._send_service(_envelope_error(
                        "REQUEST_INVALID", "请先生成或载入商品理解。", status=400,
                        field="product_brief", next_action="analyze_product",
                    ))
                    return
                self._send_service(self.application.save_product_brief(
                    directory=_first_string(parsed.get("directory")),
                    expected_etag=_first_string(parsed.get("expected_etag")),
                    fields=fields,
                ))
            return
        if path != "/api/intake":
            self._send_service(_envelope_error(
                "NOT_FOUND", "没有找到这个操作。", status=404, next_action="go_home",
            ))
            return
        form = self._read_multipart()
        if form is not None:
            self._send_service(self._save_from_form(form))

    def _save_from_form(self, form: dict[str, object]) -> ServiceResponse:
        raw_points = str(form.get("selling_points") or "")
        points = [line.strip() for line in raw_points.splitlines() if line.strip()]
        return self.application.save_intake(
            directory=_first_string(form.get("directory")),
            expected_etag=_first_string(form.get("expected_etag")),
            product_name=str(form.get("product_name") or ""),
            description=str(form.get("description") or ""),
            selling_points=points,
            user_intent=str(form.get("user_intent") or ""),
            reference_images=list(form.get("reference_images") or []),
        )

    def _read_json(self) -> dict[str, object] | None:
        if self.headers.get_content_type() != "application/json":
            self._send_service(_envelope_error(
                "CONTENT_TYPE_INVALID", "请求格式无效，请刷新页面后重试。", status=415,
                next_action="reload_page",
            ))
            return None
        body = self._read_body(max_bytes=1024 * 1024)
        if body is None:
            return None
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            parsed = None
        if not isinstance(parsed, dict):
            self._send_service(_envelope_error(
                "REQUEST_INVALID", "请求内容无效，请刷新页面后重试。", status=400,
                next_action="reload_page",
            ))
            return None
        return parsed

    def _read_multipart(self) -> dict[str, object] | None:
        content_type = self.headers.get("Content-Type", "")
        if (not content_type.lower().startswith("multipart/form-data;")
                or "\r" in content_type or "\n" in content_type):
            self._send_service(_envelope_error(
                "CONTENT_TYPE_INVALID", "请通过资料表单提交商品信息和图片。", status=415,
                next_action="submit_intake_form",
            ))
            return None
        body = self._read_body(max_bytes=MAX_REQUEST_BYTES)
        if body is None:
            return None
        try:
            message = BytesParser(policy=policy.default).parsebytes(
                b"MIME-Version: 1.0\r\nContent-Type: "
                + content_type.encode("ascii") + b"\r\n\r\n" + body
            )
            if not message.is_multipart():
                raise ValueError("not multipart")
            result: dict[str, object] = {"reference_images": []}
            for part in message.iter_parts():
                if part.get_content_disposition() != "form-data":
                    continue
                name = part.get_param("name", header="content-disposition")
                if not isinstance(name, str):
                    continue
                payload = part.get_payload(decode=True) or b""
                filename = part.get_filename()
                if name == "reference_images" and filename is not None:
                    result["reference_images"].append(ImageUpload(filename, payload))
                elif name not in result:
                    result[name] = payload.decode("utf-8")
            return result
        except (LookupError, UnicodeDecodeError, ValueError, TypeError):
            self._send_service(_envelope_error(
                "REQUEST_INVALID", "商品资料或参考图格式无法读取，请重新选择后提交。", status=400,
                field="reference_images", next_action="select_reference_images",
            ))
            return None

    def _read_body(self, *, max_bytes: int) -> bytes | None:
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._send_service(_envelope_error(
                "CONTENT_LENGTH_REQUIRED", "请求大小无效，请重试。", status=411,
                next_action="retry_request",
            ))
            return None
        if length < 0 or length > max_bytes:
            self._send_service(_envelope_error(
                "REQUEST_TOO_LARGE", "提交内容过大，请减少图片数量或换用较小的原图。", status=413,
                field="reference_images", next_action="reduce_upload_size",
                details={"maximum_bytes": max_bytes},
            ))
            return None
        body = self.rfile.read(length)
        if len(body) != length:
            self._send_service(_envelope_error(
                "REQUEST_INCOMPLETE", "请求未完整送达，请重新提交。", status=400,
                next_action="retry_request",
            ))
            return None
        return body

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        try:
            parsed = urllib.parse.urlsplit(origin)
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError:
            parsed = urllib.parse.urlsplit("")
            port = -1
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}
                or port != self.server.server_port):
            self._send_service(_envelope_error(
                "ORIGIN_REJECTED", "请求来源无效，请从本机工作台重新操作。", status=403,
                next_action="reload_page",
            ))
            return False
        return True

    def _send_service(self, response: ServiceResponse) -> None:
        payload = json.dumps(response.body, ensure_ascii=False).encode("utf-8")
        self._send_bytes(response.status_code, payload, "application/json; charset=utf-8", cache="no-store")

    def _send_file(self, name: str, *, cache: str) -> None:
        if name not in STATIC_TYPES:
            self._send_service(_envelope_error(
                "NOT_FOUND", "没有找到这个页面。", status=404, next_action="go_home",
            ))
            return
        try:
            payload = (ASSET_ROOT / name).read_bytes()
        except OSError:
            self._send_service(_envelope_error(
                "APP_ASSET_MISSING", "工作台页面文件缺失，请重新安装或修复产品文件。", status=500,
                next_action="repair_installation",
            ))
            return
        self._send_bytes(200, payload, STATIC_TYPES[name], cache=cache)

    def _send_bytes(self, status: int, payload: bytes, content_type: str, *, cache: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' blob:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; base-uri 'none'; "
            "form-action 'self'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(payload)


def create_product_server(
    host: str = "127.0.0.1",
    port: int = 8780,
    *,
    application: ProductApplication | None = None,
) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Product V1 仅允许绑定本机回环地址。")
    handler = type(
        "BoundProductRequestHandler",
        (ProductRequestHandler,),
        {"application": application or ProductApplication()},
    )
    return ThreadingHTTPServer((host, port), handler)
