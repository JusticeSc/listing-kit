"""Framework-independent application API for the Product V1 workspace intake."""
from __future__ import annotations

import copy
import difflib
import hashlib
import io
import json
import os
import re
import time
import uuid
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from PIL import Image, UnidentifiedImageError

from src import product_v1_contracts as contracts
from src.product_brief import (
    ProductBriefEditError,
    compile_product_brief_draft,
    normalize_product_brief_edits,
)
from src.product_plan import ProductPlanCompilationError, compile_product_plan_draft
from src.product_prompt import ProductPromptCompilationError, compile_prompt_blocks
from src.providers.dashscope_semantic import create_default_semantic_provider
from src.providers.dashscope_image import create_default_image_provider
from src.providers.image import ImageProvider, ImageProviderError, ImageReference
from src.providers.semantic import SemanticImage, SemanticProvider, SemanticProviderError
from src.semantic_drafts import SemanticDraftValidationError
from src.workspace_store import (
    ImmutableRecordConflict,
    WorkspaceAlreadyExists,
    WorkspaceBusy,
    WorkspaceConflict,
    WorkspaceCorrupt,
    WorkspaceNotFound,
    WorkspaceSnapshot,
    WorkspaceStore,
    WorkspaceStoreError,
)

_IMAGE_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "TIFF": ("image/tiff", "tiff"),
    "GIF": ("image/gif", "gif"),
}
_ASSET_ROLES = {"primary", "detail", "packaging", "unknown"}
_BRIEF_EDITABLE_FIELDS = ("category", "facts", "must_preserve", "may_change", "unknowns")
_APP_VERSION = "1.0.0"
# One provider task per shot is submitted back-to-back; the image service throttles
# bursts, so leave a short gap and retry a definitive rate limit with backoff.
_SUBMISSION_SPACING_SECONDS = 1.5
_RATE_LIMIT_BACKOFF_SECONDS = (4.0, 10.0)
_RATE_LIMIT_CODE = "UPSTREAM_RATE_LIMITED"


@dataclass(frozen=True)
class ImageUpload:
    """An image supplied for the current ProductInput; paths are never accepted."""

    filename: str
    content: bytes
    role: str = "unknown"


@dataclass(frozen=True)
class ServiceResponse:
    """Transport-ready status plus a stable JSON envelope."""

    status_code: int
    body: dict[str, Any]

    @property
    def ok(self) -> bool:
        return self.body["ok"] is True


class ServiceError(RuntimeError):
    """Actionable, transport-neutral failure returned by ApplicationService."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        field: str | None = None,
        recoverable: bool = True,
        next_action: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field = field
        self.recoverable = recoverable
        self.next_action = next_action
        self.details = copy.deepcopy(dict(details or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "recoverable": self.recoverable,
            "next_action": self.next_action,
            "details": copy.deepcopy(self.details),
        }


class ApplicationService:
    """Own request validation and UI projection; WorkspaceStore owns durable state."""

    def __init__(
        self,
        *,
        app_version: str = _APP_VERSION,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] | None = None,
        semantic_provider_factory: Callable[[], SemanticProvider] | None = None,
        image_provider_factory: Callable[[], ImageProvider] | None = None,
    ) -> None:
        if not isinstance(app_version, str) or not app_version.strip():
            raise ValueError("app_version must be a non-empty string")
        self.app_version = app_version.strip()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sleep = sleep or time.sleep
        self._semantic_provider_factory = semantic_provider_factory or create_default_semantic_provider
        self._image_provider_factory = image_provider_factory or create_default_image_provider

    def create_workspace(self, directory: str | os.PathLike[str]) -> ServiceResponse:
        return self._execute(directory, 201, self._create_workspace)

    def open_workspace(self, directory: str | os.PathLike[str]) -> ServiceResponse:
        return self._execute(directory, 200, self._open_workspace)

    def get_workspace_projection(self, directory: str | os.PathLike[str]) -> ServiceResponse:
        """Re-read durable state for each projection; no process-local business cache."""
        return self.open_workspace(directory)

    def save_intake(
        self,
        directory: str | os.PathLike[str],
        *,
        expected_etag: str | None,
        product_name: str,
        description: str | None = None,
        selling_points: Sequence[str] | None = None,
        user_intent: str | None = None,
        reference_images: Sequence[ImageUpload] | None = None,
    ) -> ServiceResponse:
        return self._execute(
            directory,
            200,
            lambda root: self._save_intake(
                root,
                expected_etag=expected_etag,
                product_name=product_name,
                description=description,
                selling_points=selling_points,
                user_intent=user_intent,
                reference_images=reference_images,
            ),
        )

    def generate_product_brief_draft(
        self, directory: str | os.PathLike[str], *, expected_etag: str | None,
    ) -> ServiceResponse:
        return self._execute(
            directory, 200,
            lambda root: self._generate_product_brief_draft(root, expected_etag=expected_etag),
        )

    def save_product_brief(
        self, directory: str | os.PathLike[str], *, expected_etag: str | None,
        fields: Mapping[str, Any],
    ) -> ServiceResponse:
        return self._execute(
            directory, 200,
            lambda root: self._save_product_brief(root, expected_etag=expected_etag, fields=fields),
        )

    def generate_product_plan(
        self, directory: str | os.PathLike[str], *, expected_etag: str | None,
    ) -> ServiceResponse:
        return self._execute(
            directory, 200,
            lambda root: self._generate_product_plan(root, expected_etag=expected_etag),
        )

    def save_product_plan(
        self,
        directory: str | os.PathLike[str],
        *,
        expected_etag: str | None,
        plan: Mapping[str, Any] | None,
    ) -> ServiceResponse:
        """Save an edited Plan as new immutable Plan/ShotSpec versions."""
        return self._execute(
            directory, 200,
            lambda root: self._save_product_plan(
                root, expected_etag=expected_etag, plan=plan,
            ),
        )

    def generate_prompt(
        self,
        directory: str | os.PathLike[str],
        *,
        expected_etag: str | None,
        shot_id: str | None,
    ) -> ServiceResponse:
        return self._execute(
            directory, 200,
            lambda root: self._generate_prompt(
                root, expected_etag=expected_etag, shot_id=shot_id,
            ),
        )

    def save_prompt_edit(
        self,
        directory: str | os.PathLike[str],
        *,
        expected_etag: str | None,
        shot_id: str | None,
        expected_prompt_version: int | None,
        full_text: str | None,
        reason: str | None = None,
    ) -> ServiceResponse:
        return self._execute(
            directory, 200,
            lambda root: self._save_prompt_edit(
                root,
                expected_etag=expected_etag,
                shot_id=shot_id,
                expected_prompt_version=expected_prompt_version,
                full_text=full_text,
                reason=reason,
            ),
        )

    def start_generation_set(
        self,
        directory: str | os.PathLike[str],
        *,
        expected_etag: str | None,
        idempotency_key: str | None,
    ) -> ServiceResponse:
        """Compile any missing per-shot prompts, then submit one provider task per current shot."""
        initial = self.get_workspace_projection(directory)
        if not initial.ok:
            return initial
        projection = initial.body["data"]
        if not isinstance(expected_etag, str) or not expected_etag:
            return self._service_failure(
                "REVISION_REQUIRED", "请重新载入当前方案后再开始生成。", status_code=428,
                field="revision", next_action="reload_workspace",
            )
        if projection["workspace"]["revision"] != expected_etag:
            return self._service_failure(
                "REVISION_CONFLICT", "工作空间已更新；请重新载入方案后再生成。", status_code=409,
                field="revision", next_action="reload_workspace",
            )
        plan = projection.get("plan")
        if not isinstance(plan, Mapping) or not plan.get("shot_specs"):
            return self._service_failure(
                "PLAN_REQUIRED", "先生成并保存一份套图方案。", status_code=409,
                field="plan", next_action="generate_plan",
            )

        revision = expected_etag
        blocked: list[dict[str, Any]] = []
        first_failure: ServiceResponse | None = None
        for shot in plan["shot_specs"]:
            if shot.get("latest_prompt") is not None:
                continue
            compiled = self.generate_prompt(
                directory, expected_etag=revision, shot_id=shot.get("id"),
            )
            if not compiled.ok:
                # One shot whose prompt cannot be compiled must not abort the
                # whole set: the remaining shots still submit, and the blocked
                # shot keeps its own recovery path (POST /api/generation/rework
                # compiles a missing prompt before it submits).
                if first_failure is None:
                    first_failure = compiled
                error = compiled.body["error"]
                blocked.append({
                    "shot_id": shot.get("id"),
                    "title": shot.get("title"),
                    "code": error.get("code"),
                    "message": error.get("message"),
                    "next_action": error.get("next_action"),
                })
                continue
            revision = compiled.body["data"]["workspace"]["revision"]
        if blocked:
            blocked_ids = {entry["shot_id"] for entry in blocked}
            ready = [
                shot for shot in plan["shot_specs"]
                if shot.get("latest_prompt") is not None
                or shot.get("id") not in blocked_ids
            ]
            if not ready and first_failure is not None:
                return first_failure
        return self._execute(
            directory, 202,
            lambda root: self._start_generation_set(
                root, expected_etag=revision, idempotency_key=idempotency_key,
                blocked_shots=blocked,
            ),
        )

    def reconcile_generation(
        self,
        directory: str | os.PathLike[str],
        *,
        action_ids: Sequence[str],
    ) -> ServiceResponse:
        """Query persisted provider task IDs; this method never submits a new task."""
        return self._execute(
            directory, 200,
            lambda root: self._reconcile_generation(root, action_ids=action_ids),
        )

    def save_selection(
        self,
        directory: str | os.PathLike[str],
        *,
        expected_etag: str | None,
        choices: Sequence[Mapping[str, Any]] | None,
    ) -> ServiceResponse:
        """Persist one chosen candidate per current Plan shot as a SelectionVersion."""
        return self._execute(
            directory, 200,
            lambda root: self._save_selection(
                root, expected_etag=expected_etag, choices=choices,
            ),
        )

    def start_shot_generation(
        self,
        directory: str | os.PathLike[str],
        *,
        expected_etag: str | None,
        shot_id: str | None,
        idempotency_key: str | None,
    ) -> ServiceResponse:
        """Re-run exactly one shot (rework) after its prompt was reviewed or edited."""
        initial = self.get_workspace_projection(directory)
        if not initial.ok:
            return initial
        projection = initial.body["data"]
        if not isinstance(expected_etag, str) or not expected_etag:
            return self._service_failure(
                "REVISION_REQUIRED", "请重新载入当前方案后再返工。", status_code=428,
                field="revision", next_action="reload_workspace",
            )
        if projection["workspace"]["revision"] != expected_etag:
            return self._service_failure(
                "REVISION_CONFLICT", "工作空间已更新；请重新载入方案后再返工。", status_code=409,
                field="revision", next_action="reload_workspace",
            )
        plan = projection.get("plan")
        if not isinstance(plan, Mapping) or not plan.get("shot_specs"):
            return self._service_failure(
                "PLAN_REQUIRED", "先生成并保存一份套图方案。", status_code=409,
                field="plan", next_action="generate_plan",
            )
        shot = next(
            (item for item in plan["shot_specs"] if item.get("id") == shot_id), None,
        )
        if shot is None:
            return self._service_failure(
                "SHOT_NOT_FOUND", "找不到这张图片；请重新载入方案。", status_code=404,
                field="shot_id", next_action="reload_workspace",
            )
        revision = expected_etag
        if shot.get("latest_prompt") is None:
            compiled = self.generate_prompt(
                directory, expected_etag=revision, shot_id=shot["id"],
            )
            if not compiled.ok:
                return compiled
            revision = compiled.body["data"]["workspace"]["revision"]
        return self._execute(
            directory, 202,
            lambda root: self._start_shot_generation(
                root, expected_etag=revision, shot_id=shot["id"],
                idempotency_key=idempotency_key,
            ),
        )

    def export_selection(
        self,
        directory: str | os.PathLike[str],
        *,
        expected_etag: str | None,
    ) -> ServiceResponse:
        """Write the deliverable folder (images + manifest + README) for the current selection."""
        return self._execute(
            directory, 201,
            lambda root: self._export_selection(root, expected_etag=expected_etag),
        )

    def abandon_generation_attempt(
        self,
        directory: str | os.PathLike[str],
        *,
        expected_etag: str | None,
        action_id: str | None,
        reason: str | None,
    ) -> ServiceResponse:
        """Human-confirmed release of an unconfirmed submission that has no task id."""
        return self._execute(
            directory, 200,
            lambda root: self._abandon_generation_attempt(
                root, expected_etag=expected_etag, action_id=action_id, reason=reason,
            ),
        )

    def _start_generation_set(
        self, directory: Path, *, expected_etag: str | None, idempotency_key: str | None,
        blocked_shots: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(idempotency_key, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{8,120}", idempotency_key,
        ):
            raise ServiceError(
                "IDEMPOTENCY_KEY_INVALID", "生成请求编号无效，请重新点击生成。",
                status_code=400, field="idempotency_key", next_action="start_generation",
            )
        store = WorkspaceStore.open(directory)
        snapshot = store.load_workspace()
        if not isinstance(expected_etag, str) or snapshot.etag != expected_etag:
            raise ServiceError(
                "REVISION_CONFLICT", "工作空间已更新；请重新载入方案后再生成。",
                status_code=409, field="revision", next_action="reload_workspace",
            )
        workspace = snapshot.workspace
        plan_ref = workspace["current"]["plan"]
        input_ref = workspace["current"]["product_input"]
        if plan_ref is None or input_ref is None:
            raise ServiceError(
                "GENERATION_INPUT_REQUIRED", "先保存商品资料并生成套图方案。",
                status_code=409, field="plan", next_action="complete_plan",
            )
        plan = store.get_record("plan", plan_ref["id"], version=plan_ref["version"])
        product_input = store.get_record(
            "product_input", input_ref["id"], version=input_ref["version"],
        )
        provider = self._image_provider_factory()
        provider_id = getattr(provider, "provider_id", None)
        model_id = getattr(provider, "model_id", None)
        if not isinstance(provider_id, str) or not isinstance(model_id, str):
            raise ServiceError(
                "IMAGE_PROVIDER_CONFIGURATION_INVALID", "图片模型配置不完整，暂时不能生成。",
                status_code=500, field="image_provider", recoverable=False,
                next_action="check_model_configuration",
            )

        prompt_records = store.list_records("prompt")
        blocked_by_shot = {
            str(entry["shot_id"]): entry for entry in (blocked_shots or [])
            if isinstance(entry, Mapping) and entry.get("shot_id")
        }
        skipped: list[dict[str, Any]] = []
        shots: list[dict[str, Any]] = []
        for item in plan["shots"]:
            shot = store.get_record(
                "shot_spec", item["shot"]["id"], version=item["shot"]["version"],
            )
            prompts = self._prompt_versions_for_shot(prompt_records, plan, shot)
            if not prompts and shot["id"] in blocked_by_shot:
                skipped.append(dict(blocked_by_shot[shot["id"]]))
                continue
            if not prompts:
                raise ServiceError(
                    "PROMPT_REQUIRED", "有图片还没有可用于生成的提示词，请重新载入后再试。",
                    status_code=409, field=f"shots.{shot['id']}.prompt",
                    next_action="compile_prompts",
                )
            shot["order"] = item["order"]
            shot["prompt"] = prompts[-1]
            references = list(shot.get("reference_asset_sha256") or [])
            if not references:
                references = list(product_input["reference_asset_sha256"])
            if not 1 <= len(references) <= 3:
                raise ServiceError(
                    "REFERENCE_IMAGE_COUNT", "每张图片都需要关联 1–3 张商品参考图。",
                    status_code=422, field=f"shots.{shot['id']}.reference_images",
                    next_action="review_product_references",
                )
            shot["selected_reference_hashes"] = references
            shots.append(shot)
        if not shots:
            raise ServiceError(
                "PLAN_EMPTY", "套图方案中没有可生成的图片。", status_code=409,
                field="plan.shots", next_action="restore_a_shot",
            )

        projection = self._submit_generation_attempts(
            store, workspace=workspace, shots=shots, provider=provider,
            provider_id=provider_id, model_id=model_id,
            idempotency_key=idempotency_key, expected_etag=expected_etag,
        )
        if skipped:
            projection["skipped_shots"] = skipped
        return projection

    def _submit_generation_attempts(
        self,
        store: WorkspaceStore,
        *,
        workspace: Mapping[str, Any],
        shots: Sequence[Mapping[str, Any]],
        provider: ImageProvider,
        provider_id: str,
        model_id: str,
        idempotency_key: str,
        expected_etag: str,
    ) -> dict[str, Any]:
        existing = store.list_records("generation_attempt")
        by_action = {record["action_id"]: record for record in existing}
        active = {"CREATED", "SUBMITTED", "RUNNING", "UNKNOWN", "RECONCILING"}
        planned: list[tuple[Mapping[str, Any], str, dict[str, Any] | None]] = []
        to_create: list[dict[str, Any]] = []

        for shot in shots:
            prompt = shot["prompt"]
            identity = f"{idempotency_key}:{shot['id']}:{shot['version']}:{prompt['version']}"
            digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
            action_id = f"act_{digest[:40]}"
            known = by_action.get(action_id)
            planned.append((shot, action_id, known))
            if known is not None:
                continue
            shot_ref = {"kind": "shot_spec", "id": shot["id"], "version": shot["version"]}
            unresolved = next((
                record for record in existing
                if record["shot"] == shot_ref and record["status"] in active
            ), None)
            if unresolved is not None:
                raise ServiceError(
                    "GENERATION_UNRESOLVED",
                    "这张图片还有一次生成结果未确认；先核对原任务，不能重复提交。",
                    status_code=409, field=f"shots.{shot['id']}.generation",
                    next_action="reconcile_generation",
                    details={"action_id": unresolved["action_id"], "status": unresolved["status"]},
                )
            prompt_hash = hashlib.sha256(prompt["full_text"].encode("utf-8")).hexdigest()
            request_data = {
                "provider_id": provider_id, "model_id": model_id,
                "prompt_sha256": prompt_hash,
                "reference_asset_sha256": list(shot["selected_reference_hashes"]),
                "size": "1344*1344", "prompt_extend": False,
            }
            request_hash = hashlib.sha256(json.dumps(
                request_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")).hexdigest()
            now = self._now()
            to_create.append({
                "schema": "amz-listing-kit/generation-attempt@1",
                "action_id": action_id,
                "idempotency_key": f"idem_{digest[:52]}",
                "workspace_id": workspace["workspace_id"],
                "created_at": now, "updated_at": now,
                "shot": shot_ref,
                "prompt": {"kind": "prompt", "id": prompt["id"], "version": prompt["version"]},
                "provider_id": provider_id, "model_id": model_id,
                "request_sha256": request_hash,
                "reference_asset_sha256": list(shot["selected_reference_hashes"]),
                "status": "CREATED", "provider_task_id": None, "error": None,
            })

        # Save every intent before the first network side effect. Duplicate calls with the same
        # idempotency key find these records and do not submit the same task twice.
        with store.transaction():
            if store.load_workspace().etag != expected_etag:
                raise ServiceError(
                    "REVISION_CONFLICT", "工作空间已更新；请重新载入方案后再生成。",
                    status_code=409, field="revision", next_action="reload_workspace",
                )
            target_shot_ids = {record["shot"]["id"] for record in to_create}
            unresolved = next((
                record for record in store.list_records("generation_attempt")
                if record["shot"]["id"] in target_shot_ids and record["status"] in active
            ), None)
            if unresolved is not None:
                raise ServiceError(
                    "GENERATION_UNRESOLVED",
                    "这张图片还有一次生成结果未确认；先核对原任务，不能重复提交。",
                    status_code=409,
                    field=f"shots.{unresolved['shot']['id']}.generation",
                    next_action="reconcile_generation",
                    details={"action_id": unresolved["action_id"], "status": unresolved["status"]},
                )
            for record in to_create:
                store.save_record("generation_attempt", record)

        for shot, action_id, known in planned:
            if known is not None:
                continue
            attempt = store.get_record("generation_attempt", action_id)
            if attempt["status"] != "CREATED" or attempt["provider_task_id"] is not None:
                continue
            try:
                references: list[ImageReference] = []
                for digest in shot["selected_reference_hashes"]:
                    asset, content = store.read_asset_by_sha256(digest)
                    references.append(ImageReference(digest, asset["media_type"], content))
                task = provider.submit(
                    shot["prompt"]["full_text"], references,
                    model_id=model_id, size="1344*1344",
                    idempotency_key=attempt["idempotency_key"],
                )
                self._apply_submitted_image_task(store, action_id, provider, task)
            except ImageProviderError as exc:
                status = {"UNKNOWN": "UNKNOWN", "REJECTED": "REJECTED"}.get(exc.status, "FAILED")
                self._update_generation_attempt(
                    store, action_id, status=status, error=f"{exc.code}: {exc.message}",
                )
            except (WorkspaceStoreError, OSError):
                self._update_generation_attempt(
                    store, action_id, status="FAILED",
                    error="参考图片读取失败，未能完成此图的生成提交。",
                )
            except Exception as exc:
                # Keep the failure class so an operator can tell a provider outage
                # from a local wiring bug; the class name carries no prompt, key,
                # image or signed URL.
                self._update_generation_attempt(
                    store, action_id, status="UNKNOWN",
                    error=(
                        f"提交结果暂时无法确认（{type(exc).__name__}）；"
                        "系统不会自动重提，请核对任务状态。"
                    ),
                )
        return self._project(store, store.load_workspace())

    def _reconcile_generation(
        self, directory: Path, *, action_ids: Sequence[str],
    ) -> dict[str, Any]:
        if isinstance(action_ids, (str, bytes)) or not isinstance(action_ids, Sequence):
            raise ServiceError(
                "REQUEST_INVALID", "待核对的生成任务列表无效。", status_code=400,
                field="action_ids", next_action="reload_workspace",
            )
        ids = list(dict.fromkeys(action_ids))
        if len(ids) > 100 or any(
            not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", value)
            for value in ids
        ):
            raise ServiceError(
                "REQUEST_INVALID", "待核对的生成任务列表无效。", status_code=400,
                field="action_ids", next_action="reload_workspace",
            )
        store = WorkspaceStore.open(directory)
        by_id = {item["action_id"]: item for item in store.list_records("generation_attempt")}
        provider = None
        for action_id in ids:
            attempt = by_id.get(action_id)
            if attempt is None:
                raise ServiceError(
                    "GENERATION_ATTEMPT_NOT_FOUND", "找不到这次生成记录，请重新载入工作空间。",
                    status_code=404, field="action_ids", next_action="reload_workspace",
                )
            if attempt["status"] in {"SUCCEEDED", "FAILED", "REJECTED", "ABANDONED"}:
                continue
            candidates = [
                item for item in store.list_records("candidate")
                if item["attempt_action_id"] == action_id
            ]
            if candidates:
                self._update_generation_attempt(store, action_id, status="SUCCEEDED", error=None)
                continue
            task_id = attempt.get("provider_task_id")
            if not task_id:
                previous = attempt.get("error")
                note = "没有可核对的模型任务编号；为避免重复计费，不会自动重新提交。"
                if not previous:
                    merged = note
                elif note in previous:
                    merged = previous
                else:
                    merged = f"{previous}（{note}）"
                self._update_generation_attempt(
                    store, action_id, status="UNKNOWN",
                    error=merged,
                )
                continue

            if provider is None:
                provider = self._image_provider_factory()
            self._update_generation_attempt(store, action_id, status="RECONCILING", error=None)
            try:
                task = provider.query_task(task_id)
            except ImageProviderError as exc:
                status = {"UNKNOWN": "UNKNOWN", "REJECTED": "REJECTED"}.get(exc.status, "FAILED")
                self._update_generation_attempt(
                    store, action_id, status=status, error=f"{exc.code}: {exc.message}",
                )
                continue
            except Exception:
                self._update_generation_attempt(
                    store, action_id, status="UNKNOWN",
                    error="暂时无法确认模型任务状态；稍后可继续核对原任务。",
                )
                continue
            if task.task_id not in {None, task_id}:
                self._update_generation_attempt(
                    store, action_id, status="UNKNOWN",
                    error="模型返回的任务编号与原记录不一致；请继续核对原任务。",
                )
                continue
            self._apply_reconciled_image_task(store, attempt, provider, task)
        return self._project(store, store.load_workspace())

    def _apply_submitted_image_task(
        self, store: WorkspaceStore, action_id: str, provider: ImageProvider, task: ImageTask,
    ) -> None:
        if task.provider_id != provider.provider_id or task.model_id != provider.model_id:
            self._update_generation_attempt(
                store, action_id, status="UNKNOWN",
                error="图片模型返回的服务标识不匹配；请核对任务后再继续。",
            )
            return
        if task.status.upper() == "SUCCEEDED":
            attempt = store.get_record("generation_attempt", action_id)
            self._materialize_image_task(store, attempt, provider, task)
            return
        self._update_generation_attempt(
            store, action_id, status=self._attempt_status(task.status),
            provider_task_id=task.task_id, error=task.error,
        )

    def _apply_reconciled_image_task(
        self, store: WorkspaceStore, attempt: Mapping[str, Any],
        provider: ImageProvider, task: ImageTask,
    ) -> None:
        if task.provider_id != attempt["provider_id"] or task.model_id != attempt["model_id"]:
            self._update_generation_attempt(
                store, attempt["action_id"], status="UNKNOWN",
                error="图片模型返回的服务标识不匹配；请继续核对原任务。",
            )
            return
        if task.status.upper() == "SUCCEEDED":
            self._materialize_image_task(store, attempt, provider, task)
            return
        self._update_generation_attempt(
            store, attempt["action_id"], status=self._attempt_status(task.status),
            provider_task_id=attempt.get("provider_task_id"), error=task.error,
        )

    def _materialize_image_task(
        self,
        store: WorkspaceStore,
        attempt: Mapping[str, Any],
        provider: ImageProvider,
        task: ImageTask,
    ) -> None:
        """Download one completed provider result into immutable, verified workspace state."""
        action_id = attempt["action_id"]
        current = store.get_record("generation_attempt", action_id)
        saved_task_id = current.get("provider_task_id")
        task_id = task.task_id or saved_task_id
        if not isinstance(task_id, str) or not task_id:
            self._update_generation_attempt(
                store, action_id, status="UNKNOWN",
                error="模型已返回完成状态，但没有可核对的任务编号；为避免重复提交，请检查服务端记录。",
            )
            return
        if saved_task_id is not None and saved_task_id != task_id:
            self._update_generation_attempt(
                store, action_id, status="UNKNOWN", provider_task_id=saved_task_id,
                error="模型返回的任务编号与已保存记录不一致；请继续核对原任务。",
            )
            return

        # Persist the provider ID before downloading. If the process is interrupted, recovery
        # can query this same task instead of submitting another billable request.
        self._update_generation_attempt(
            store, action_id, status="SUBMITTED", provider_task_id=task_id, error=None,
        )
        result_urls = task.result_urls
        if (not isinstance(result_urls, Sequence) or isinstance(result_urls, (str, bytes))
                or len(result_urls) != 1 or not isinstance(result_urls[0], str)):
            self._update_generation_attempt(
                store, action_id, status="UNKNOWN", provider_task_id=task_id,
                error="模型任务已完成，但没有返回唯一可核对的图片结果；可稍后核对原任务。",
            )
            return

        try:
            content, reported_media_type = provider.download_result(result_urls[0])
        except ImageProviderError as exc:
            status = {"UNKNOWN": "UNKNOWN", "REJECTED": "REJECTED"}.get(exc.status, "FAILED")
            self._update_generation_attempt(
                store, action_id, status=status, provider_task_id=task_id,
                error=f"{exc.code}: {exc.message}",
            )
            return
        except Exception:
            self._update_generation_attempt(
                store, action_id, status="UNKNOWN", provider_task_id=task_id,
                error="候选图片暂时无法下载确认；稍后可核对同一模型任务，不会重复提交。",
            )
            return

        try:
            if not isinstance(content, bytes) or not content:
                raise ValueError("empty image content")
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(content)) as decoded:
                    image_format = decoded.format
                    width, height = decoded.size
                    decoded.verify()
            expected_media_type, extension = _IMAGE_FORMATS.get(image_format or "", (None, None))
            if (
                image_format not in {"JPEG", "PNG", "TIFF"}
                or reported_media_type != expected_media_type
                or not isinstance(width, int) or not isinstance(height, int)
                or width < 1 or height < 1
            ):
                raise ValueError("unsupported or mismatched image format")
        except (Image.DecompressionBombError, Image.DecompressionBombWarning,
                UnidentifiedImageError, OSError, ValueError, TypeError):
            self._update_generation_attempt(
                store, action_id, status="FAILED", provider_task_id=task_id,
                error="模型返回的候选图片格式无效或无法安全读取；历史候选未受影响。",
            )
            return

        digest = hashlib.sha256(content).hexdigest()
        shot_id = current["shot"]["id"]
        relative_path = f"shots/{shot_id}/candidates/{digest}.{extension}"
        candidate = {
            "schema": "amz-listing-kit/candidate@1",
            "candidate_id": digest,
            "workspace_id": current["workspace_id"],
            "shot": copy.deepcopy(current["shot"]),
            "attempt_action_id": action_id,
            "prompt": copy.deepcopy(current["prompt"]),
            "relative_path": relative_path,
            "file_sha256": digest,
            "media_type": expected_media_type,
            "width": width,
            "height": height,
            "created_at": self._now(),
        }
        try:
            store.save_immutable_file(relative_path, content, expected_sha256=digest)
            store.save_record("candidate", candidate)
        except ImmutableRecordConflict:
            self._update_generation_attempt(
                store, action_id, status="FAILED", provider_task_id=task_id,
                error="这张图片与已有候选完全相同，为保护候选来源没有覆盖或合并记录。",
            )
            return

        self._update_generation_attempt(
            store, action_id, status="SUCCEEDED", provider_task_id=task_id, error=None,
        )

    def _start_shot_generation(
        self, directory: Path, *, expected_etag: str | None, shot_id: str,
        idempotency_key: str | None,
    ) -> dict[str, Any]:
        if not isinstance(idempotency_key, str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{8,120}", idempotency_key,
        ):
            raise ServiceError(
                "IDEMPOTENCY_KEY_INVALID", "生成请求编号无效，请重新点击生成。",
                status_code=400, field="idempotency_key", next_action="start_generation",
            )
        store = WorkspaceStore.open(directory)
        snapshot = store.load_workspace()
        if not isinstance(expected_etag, str) or snapshot.etag != expected_etag:
            raise ServiceError(
                "REVISION_CONFLICT", "工作空间已更新；请重新载入后再返工。",
                status_code=409, field="revision", next_action="reload_workspace",
            )
        workspace = snapshot.workspace
        plan_ref = workspace["current"]["plan"]
        input_ref = workspace["current"]["product_input"]
        if plan_ref is None or input_ref is None:
            raise ServiceError(
                "GENERATION_INPUT_REQUIRED", "先保存商品资料并生成套图方案。",
                status_code=409, field="plan", next_action="complete_plan",
            )
        plan = store.get_record("plan", plan_ref["id"], version=plan_ref["version"])
        product_input = store.get_record(
            "product_input", input_ref["id"], version=input_ref["version"],
        )
        item = next(
            (entry for entry in plan["shots"] if entry["shot"]["id"] == shot_id), None,
        )
        if item is None:
            raise ServiceError(
                "SHOT_NOT_FOUND", "找不到这张图片；请重新载入方案。",
                status_code=404, field="shot_id", next_action="reload_workspace",
            )
        shot = store.get_record(
            "shot_spec", item["shot"]["id"], version=item["shot"]["version"],
        )
        prompts = self._prompt_versions_for_shot(store.list_records("prompt"), plan, shot)
        if not prompts:
            raise ServiceError(
                "PROMPT_REQUIRED", "这张图片还没有可用的提示词，请重新载入后再试。",
                status_code=409, field=f"shots.{shot_id}.prompt", next_action="compile_prompts",
            )
        shot["order"] = item["order"]
        shot["prompt"] = prompts[-1]
        references = list(shot.get("reference_asset_sha256") or [])
        if not references:
            references = list(product_input["reference_asset_sha256"])
        if not 1 <= len(references) <= 3:
            raise ServiceError(
                "REFERENCE_IMAGE_COUNT", "每张图片都需要关联 1–3 张商品参考图。",
                status_code=422, field=f"shots.{shot_id}.reference_images",
                next_action="review_product_references",
            )
        shot["selected_reference_hashes"] = references
        provider = self._image_provider_factory()
        provider_id = getattr(provider, "provider_id", None)
        model_id = getattr(provider, "model_id", None)
        if not isinstance(provider_id, str) or not isinstance(model_id, str):
            raise ServiceError(
                "IMAGE_PROVIDER_CONFIGURATION_INVALID", "图片模型配置不完整，暂时不能生成。",
                status_code=500, field="image_provider", recoverable=False,
                next_action="check_model_configuration",
            )
        return self._submit_generation_attempts(
            store, workspace=workspace, shots=[shot], provider=provider,
            provider_id=provider_id, model_id=model_id,
            idempotency_key=idempotency_key, expected_etag=expected_etag,
        )

    def _abandon_generation_attempt(
        self, directory: Path, *, expected_etag: str | None,
        action_id: str | None, reason: str | None,
    ) -> dict[str, Any]:
        if not isinstance(expected_etag, str) or not expected_etag:
            raise ServiceError(
                "REVISION_REQUIRED", "请先重新载入工作空间，再处理这次未确认的提交。",
                status_code=428, field="revision", next_action="reload_workspace",
            )
        if not isinstance(action_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", action_id):
            raise ServiceError(
                "REQUEST_INVALID", "这次生成记录的编号无效，请重新载入工作空间。",
                status_code=400, field="action_id", next_action="reload_workspace",
            )
        reason_text = reason.strip() if isinstance(reason, str) else ""
        if not reason_text or len(reason_text) > 500:
            raise ServiceError(
                "ABANDON_REASON_REQUIRED",
                "放弃未确认的提交前，请先说明你已在哪里核对过（不超过 500 字）。",
                status_code=422, field="reason", next_action="confirm_in_provider_console",
            )
        store = WorkspaceStore.open(directory)
        snapshot = store.load_workspace()
        if snapshot.etag != expected_etag:
            raise ServiceError(
                "REVISION_CONFLICT", "工作空间已更新；请重新载入后再处理这次提交。",
                status_code=409, field="revision", next_action="reload_workspace",
            )
        attempt = store.get_record("generation_attempt", action_id)
        if attempt["status"] in {"SUCCEEDED", "FAILED", "REJECTED", "ABANDONED"}:
            raise ServiceError(
                "GENERATION_ALREADY_SETTLED", "这次生成已经结束，不需要放弃。",
                status_code=409, field="action_id", next_action="reload_workspace",
            )
        if attempt.get("provider_task_id"):
            raise ServiceError(
                "GENERATION_TASK_KNOWN", "这次提交有可核对的任务编号，请先核对，不要放弃。",
                status_code=409, field="action_id", next_action="reconcile_generation",
            )
        self._update_generation_attempt(
            store, action_id, status="ABANDONED",
            error=f"用户确认放弃这次未确认的提交：{reason_text}",
        )
        return self._project(store, store.load_workspace())

    def _save_selection(
        self, directory: Path, *, expected_etag: str | None,
        choices: Sequence[Mapping[str, Any]] | None,
    ) -> dict[str, Any]:
        if not isinstance(expected_etag, str) or not expected_etag:
            raise ServiceError(
                "REVISION_REQUIRED", "请先重新载入工作空间，再保存选择。",
                status_code=428, field="revision", next_action="reload_workspace",
            )
        if isinstance(choices, (str, bytes)) or not isinstance(choices, Sequence) or not choices:
            raise ServiceError(
                "SELECTION_INVALID", "请为每张图片各选择一个候选。",
                status_code=422, field="choices", next_action="choose_candidates",
            )
        store = WorkspaceStore.open(directory)
        snapshot = store.load_workspace()
        if snapshot.etag != expected_etag:
            raise ServiceError(
                "REVISION_CONFLICT", "工作空间已更新；请重新载入后再保存选择。",
                status_code=409, field="revision", next_action="reload_workspace",
            )
        workspace = snapshot.workspace
        plan_ref = workspace["current"]["plan"]
        if plan_ref is None:
            raise ServiceError(
                "PLAN_REQUIRED", "先生成并保存一份套图方案。",
                status_code=409, field="plan", next_action="generate_plan",
            )
        plan = store.get_record("plan", plan_ref["id"], version=plan_ref["version"])
        shot_refs = [
            {"kind": "shot_spec", "id": entry["shot"]["id"], "version": entry["shot"]["version"]}
            for entry in plan["shots"]
        ]
        known_ids = {ref["id"] for ref in shot_refs}
        by_shot: dict[str, str] = {}
        for item in choices:
            if not isinstance(item, Mapping):
                raise ServiceError(
                    "SELECTION_INVALID", "选择内容格式无效。",
                    status_code=422, field="choices", next_action="choose_candidates",
                )
            shot_id = item.get("shot_id")
            digest = item.get("candidate_sha256")
            if (
                not isinstance(shot_id, str) or not isinstance(digest, str)
                or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)
            ):
                raise ServiceError(
                    "SELECTION_INVALID", "选择内容格式无效。",
                    status_code=422, field="choices", next_action="choose_candidates",
                )
            if shot_id in by_shot:
                raise ServiceError(
                    "SELECTION_INVALID", "同一张图片只能选择一个候选。",
                    status_code=422, field=f"choices.{shot_id}", next_action="choose_candidates",
                )
            by_shot[shot_id] = digest
        missing = [ref["id"] for ref in shot_refs if ref["id"] not in by_shot]
        if missing:
            raise ServiceError(
                "SELECTION_INCOMPLETE", "还有图片没有选择候选；请为每张图片选择一张。",
                status_code=409, field="choices", next_action="choose_candidates",
                details={"missing_shot_ids": missing},
            )
        unknown = sorted(set(by_shot) - known_ids)
        if unknown:
            raise ServiceError(
                "SELECTION_INVALID", "选择列表包含不属于当前方案的图片。",
                status_code=422, field="choices", next_action="reload_workspace",
                details={"unknown_shot_ids": unknown},
            )
        candidates = {record["candidate_id"]: record for record in store.list_records("candidate")}
        now = self._now()
        selection_choices = []
        for ref in shot_refs:
            digest = by_shot[ref["id"]]
            candidate = candidates.get(digest)
            if candidate is None or candidate["shot"]["id"] != ref["id"]:
                raise ServiceError(
                    "CANDIDATE_NOT_FOUND", "找不到这张图片的这个候选；请重新载入后再选。",
                    status_code=404, field=f"choices.{ref['id']}", next_action="reload_workspace",
                )
            try:
                store.read_candidate_by_sha256(digest)
            except (WorkspaceCorrupt, WorkspaceNotFound, WorkspaceStoreError) as exc:
                raise ServiceError(
                    "CANDIDATE_FILE_INVALID", "有一个候选文件与记录不一致，无法选择。",
                    status_code=409, field=f"choices.{ref['id']}", recoverable=False,
                    next_action="choose_another_candidate",
                ) from exc
            selection_choices.append({
                "shot": ref, "candidate_sha256": digest, "selected_at": now,
            })
        with store.transaction():
            latest = store.load_workspace()
            if latest.etag != expected_etag:
                raise ServiceError(
                    "REVISION_CONFLICT", "工作空间已更新；请重新载入后再保存选择。",
                    status_code=409, field="revision", next_action="reload_workspace",
                )
            existing = store.list_records("selection")
            selection_id = existing[-1]["id"] if existing else f"selection_{uuid.uuid4().hex[:16]}"
            version = max((int(record.get("version", 0)) for record in existing), default=0) + 1
            sealed = contracts.seal_record({
                "schema": "amz-listing-kit/selection@1",
                "id": selection_id, "version": version,
                "workspace_id": latest.workspace["workspace_id"], "created_at": now,
                "plan": {"kind": "plan", "id": plan["id"], "version": plan["version"]},
                "choices": selection_choices,
            })
            store.save_record("selection", sealed)
            changed = copy.deepcopy(latest.workspace)
            changed["updated_at"] = self._now()
            changed["current"]["selection"] = {
                "kind": "selection", "id": sealed["id"], "version": sealed["version"],
            }
            changed["current"]["export"] = None
            committed = store.save_workspace(changed, expected_etag=latest.etag)
        return self._project(store, committed)

    @staticmethod
    def _run_export_checks(directory: Path) -> dict[str, Any]:
        try:
            from src.platform_checks import run_export_checks
        except ImportError as exc:
            raise ServiceError(
                "PLATFORM_CHECKS_UNAVAILABLE", "平台/文件检查模块不可用，暂时不能导出。",
                status_code=500, field="export", recoverable=False,
                next_action="check_installation",
            ) from exc
        try:
            result = run_export_checks(directory)
        except ServiceError:
            raise
        except Exception as exc:
            raise ServiceError(
                "PLATFORM_CHECKS_FAILED", "平台/文件检查执行失败，交付包未生成。",
                status_code=500, field="export", recoverable=False, next_action="retry_export",
                details={"error_type": type(exc).__name__},
            ) from exc
        if not isinstance(result, Mapping):
            raise ServiceError(
                "PLATFORM_CHECKS_FAILED", "平台/文件检查返回了无效结果，交付包未生成。",
                status_code=500, field="export", recoverable=False, next_action="retry_export",
            )
        return dict(result)

    def _export_selection(self, directory: Path, *, expected_etag: str | None) -> dict[str, Any]:
        if not isinstance(expected_etag, str) or not expected_etag:
            raise ServiceError(
                "REVISION_REQUIRED", "请先重新载入工作空间，再导出。",
                status_code=428, field="revision", next_action="reload_workspace",
            )
        store = WorkspaceStore.open(directory)
        snapshot = store.load_workspace()
        if snapshot.etag != expected_etag:
            raise ServiceError(
                "REVISION_CONFLICT", "工作空间已更新；请重新载入后再导出。",
                status_code=409, field="revision", next_action="reload_workspace",
            )
        workspace = snapshot.workspace
        selection_ref = workspace["current"]["selection"]
        plan_ref = workspace["current"]["plan"]
        input_ref = workspace["current"]["product_input"]
        if selection_ref is None:
            raise ServiceError(
                "SELECTION_REQUIRED", "请先为每张图片选定候选，再导出。",
                status_code=409, field="selection", next_action="save_selection",
            )
        if plan_ref is None or input_ref is None:
            raise ServiceError(
                "PLAN_REQUIRED", "先生成并保存一份套图方案。",
                status_code=409, field="plan", next_action="generate_plan",
            )
        plan = store.get_record("plan", plan_ref["id"], version=plan_ref["version"])
        product_input = store.get_record(
            "product_input", input_ref["id"], version=input_ref["version"],
        )
        selection = store.get_record(
            "selection", selection_ref["id"], version=selection_ref["version"],
        )
        if (selection["plan"]["id"], selection["plan"]["version"]) != (plan["id"], plan["version"]):
            raise ServiceError(
                "SELECTION_STALE", "方案已更新；请重新确认每张图片的选择。",
                status_code=409, field="selection", next_action="save_selection",
            )
        choices = {item["shot"]["id"]: item["candidate_sha256"] for item in selection["choices"]}
        shot_refs = [
            {"kind": "shot_spec", "id": entry["shot"]["id"], "version": entry["shot"]["version"]}
            for entry in plan["shots"]
        ]
        missing = [ref["id"] for ref in shot_refs if ref["id"] not in choices]
        if missing:
            raise ServiceError(
                "SELECTION_INCOMPLETE", "还有图片没有选择候选；请为每张图片选择一张。",
                status_code=409, field="selection", next_action="save_selection",
                details={"missing_shot_ids": missing},
            )
        candidates = {record["candidate_id"]: record for record in store.list_records("candidate")}
        prompts: dict[str, Mapping[str, Any]] = {}
        for record in store.list_records("prompt"):
            shot_id = record["shot"]["id"]
            current = prompts.get(shot_id)
            if current is None or int(record["version"]) > int(current["version"]):
                prompts[shot_id] = record
        chosen = []
        for ref in shot_refs:
            digest = choices[ref["id"]]
            candidate = candidates.get(digest)
            if candidate is None or candidate["shot"]["id"] != ref["id"]:
                raise ServiceError(
                    "CANDIDATE_NOT_FOUND", "选定的候选已不存在；请重新选择。",
                    status_code=409, field="selection", next_action="save_selection",
                )
            try:
                _record, content = store.read_candidate_by_sha256(digest)
            except (WorkspaceCorrupt, WorkspaceNotFound, WorkspaceStoreError) as exc:
                raise ServiceError(
                    "CANDIDATE_FILE_INVALID", "选定的候选文件与记录不一致，无法导出。",
                    status_code=409, field="selection", recoverable=False,
                    next_action="choose_another_candidate",
                ) from exc
            shot = store.get_record("shot_spec", ref["id"], version=ref["version"])
            chosen.append((ref, candidate, content, shot))
        # D3.6: the README and manifest describe each delivered image with the
        # plan's shot wording. An operator may have edited the prompt after the
        # plan was saved, or delivered an image that an older prompt produced.
        # Surface that mismatch instead of shipping a misleading title.
        plan_wording_warnings: list[dict[str, Any]] = []
        for ref, candidate, _content, shot in chosen:
            latest = prompts.get(ref["id"])
            if latest is None:
                continue
            delivered_version = int((candidate.get("prompt") or {}).get("version") or 0)
            latest_version = int(latest["version"])
            reason = None
            if latest_version > delivered_version:
                reason = "delivered_with_older_prompt"
            elif latest.get("edit_mode") == "manual":
                reason = "manual_prompt_edit"
            if reason is not None:
                plan_wording_warnings.append({
                    "shot_id": ref["id"],
                    "title": shot.get("title"),
                    "reason": reason,
                    "delivered_prompt_version": delivered_version,
                    "latest_prompt_version": latest_version,
                })
        checks = self._run_export_checks(directory)
        hard_failures = [
            item for item in (checks.get("hard_failures") or []) if isinstance(item, Mapping)
        ]
        if hard_failures:
            raise ServiceError(
                "PLATFORM_CHECK_FAILED", "有硬性平台/文件检查未通过，交付包未生成。",
                status_code=409, field="export", next_action="fix_failed_checks",
                details={
                    "failed_rule_ids": [
                        str(item.get("rule_id") or "unknown") for item in hard_failures
                    ][:20],
                },
            )
        export_id = f"export_{uuid.uuid4().hex[:16]}"
        relative_dir = f"exports/{export_id}"
        now = self._now()
        files = []
        for index, (ref, candidate, content, shot) in enumerate(chosen, start=1):
            extension = {
                "image/png": "png", "image/jpeg": "jpg", "image/tiff": "tif",
            }.get(str(candidate.get("media_type")), "png")
            relative_path = (
                f"{relative_dir}/images/{index:02d}_{shot['archetype_id']}.{extension}"
            )
            store.save_immutable_file(
                relative_path, content, expected_sha256=candidate["file_sha256"],
            )
            files.append({
                "shot": ref, "candidate_sha256": candidate["candidate_id"],
                "relative_path": relative_path, "file_sha256": candidate["file_sha256"],
            })
        check_records = [
            {
                "rule_id": str(item.get("rule_id") or "unknown"),
                "rule_version": str(item.get("rule_version") or "1"),
                "passed": bool(item.get("passed")),
                "detail": str(item.get("detail") or ""),
            }
            for item in (checks.get("checks") or []) if isinstance(item, Mapping)
        ]
        existing = store.list_records("export")
        version = max((int(record.get("version", 0)) for record in existing), default=0) + 1
        sealed = contracts.seal_record({
            "schema": "amz-listing-kit/export@1",
            "id": export_id, "version": version,
            "workspace_id": workspace["workspace_id"], "created_at": now,
            "selection": {
                "kind": "selection", "id": selection["id"], "version": selection["version"],
            },
            "relative_path": relative_dir,
            "manifest_relative_path": f"{relative_dir}/manifest.json",
            "files": files, "checks": check_records,
        })
        manifest = {
            "schema": "amz-listing-kit/export-manifest@1",
            "export": copy.deepcopy(sealed),
            "workspace_id": workspace["workspace_id"],
            "created_at": now,
            "product": {
                "name": product_input.get("product_name"),
                "description": product_input.get("description"),
                "selling_points": list(product_input.get("selling_points") or []),
                "user_intent": product_input.get("user_intent"),
            },
            "platform": copy.deepcopy(checks.get("profile") or {}),
            "plan": {
                "id": plan["id"], "version": plan["version"],
                "style_lock": copy.deepcopy(plan.get("style_lock")),
                "shots": [
                    {
                        "id": entry["shot"]["id"], "version": entry["shot"]["version"],
                        "order": entry["order"],
                    }
                    for entry in plan["shots"]
                ],
            },
            "selection": copy.deepcopy(selection),
            "prompts": [
                {
                    "shot_id": ref["id"],
                    "prompt": copy.deepcopy(prompts.get(ref["id"])),
                }
                for ref in shot_refs
            ],
            "checks": copy.deepcopy(list(checks.get("checks") or [])),
            "manual_notes": copy.deepcopy(list(checks.get("manual_notes") or [])),
            "plan_wording_warnings": copy.deepcopy(plan_wording_warnings),
            "files": copy.deepcopy(files),
        }
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        store.save_immutable_file(f"{relative_dir}/manifest.json", manifest_bytes)
        readme_lines = [
            f"# {product_input.get('product_name') or '商品'} 套图交付包",
            "",
            f"- 导出编号：{sealed['id']}（版本 {sealed['version']}）",
            f"- 导出时间：{now}",
            f"- 图片数量：{len(files)} 张（均为当前人工选定候选）",
            "- 校验方式：`manifest.json` 记录每张图与每个候选的 SHA-256，可用于复核文件未被修改。",
            "",
            "## 图片清单",
            "",
        ]
        for index, (ref, candidate, _content, shot) in enumerate(chosen, start=1):
            readme_lines.append(
                f"{index}. `images/{index:02d}_{shot['archetype_id']}.{ { 'image/png': 'png', 'image/jpeg': 'jpg', 'image/tiff': 'tif' }.get(str(candidate.get('media_type')), 'png') }`"
                f" — {shot.get('title')}（{shot.get('archetype_id')}），候选 {candidate['candidate_id'][:12]}…"
            )
        readme_lines += ["", "## 检查结果", ""]
        for item in check_records:
            readme_lines.append(
                f"- {'通过' if item['passed'] else '未通过'}：{item['rule_id']}（v{item['rule_version']}）{item['detail']}"
            )
        manual_notes = [item for item in (checks.get("manual_notes") or []) if isinstance(item, Mapping)]
        if manual_notes:
            readme_lines += ["", "## 需人工确认（非硬性规则）", ""]
            for item in manual_notes:
                readme_lines.append(f"- {item.get('rule_id')}：{item.get('detail')}")
        if plan_wording_warnings:
            readme_lines += ["", "## 注意：方案文本与提示词可能不一致", ""]
            for item in plan_wording_warnings:
                if item["reason"] == "manual_prompt_edit":
                    readme_lines.append(
                        f"- 「{item['title']}」的提示词在方案保存后被手动改写"
                        f"（v{item['latest_prompt_version']}）；上面图片清单里的名称/用途取自方案文本，"
                        "可能不再描述实际交付内容。"
                    )
                else:
                    readme_lines.append(
                        f"- 「{item['title']}」交付的是提示词 v{item['delivered_prompt_version']} 的结果，"
                        f"工作空间里已存在更新的 v{item['latest_prompt_version']}；方案文本未更新，"
                        "上面图片清单里的名称/用途可能已过时。"
                    )
        readme_bytes = ("\n".join(readme_lines) + "\n").encode("utf-8")
        store.save_immutable_file(f"{relative_dir}/README.md", readme_bytes)
        with store.transaction():
            latest = store.load_workspace()
            if latest.etag != expected_etag:
                raise ServiceError(
                    "REVISION_CONFLICT", "工作空间已更新；请重新载入后再导出。",
                    status_code=409, field="revision", next_action="reload_workspace",
                )
            store.save_record("export", sealed)
            changed = copy.deepcopy(latest.workspace)
            changed["updated_at"] = self._now()
            changed["current"]["export"] = {
                "kind": "export", "id": sealed["id"], "version": sealed["version"],
            }
            committed = store.save_workspace(changed, expected_etag=latest.etag)
        projection = self._project(store, committed)
        if plan_wording_warnings:
            projection["plan_wording_warnings"] = plan_wording_warnings
        return projection

    @staticmethod
    def _attempt_status(provider_status: str) -> str:
        return {
            "PENDING": "SUBMITTED", "SUBMITTED": "SUBMITTED", "QUEUED": "SUBMITTED",
            "RUNNING": "RUNNING", "SUCCEEDED": "SUCCEEDED", "FAILED": "FAILED",
            "CANCELED": "FAILED", "CANCELLED": "FAILED", "REJECTED": "REJECTED",
            "UNKNOWN": "UNKNOWN",
        }.get(str(provider_status).upper(), "UNKNOWN")

    def _update_generation_attempt(
        self,
        store: WorkspaceStore,
        action_id: str,
        *,
        status: str,
        provider_task_id: str | None = None,
        error: str | None,
    ) -> dict[str, Any]:
        record, etag = store.get_record_with_etag("generation_attempt", action_id)
        updated = copy.deepcopy(record)
        updated["status"] = status
        updated["updated_at"] = self._now()
        if provider_task_id is not None:
            updated["provider_task_id"] = provider_task_id
        updated["error"] = error[:500] if isinstance(error, str) else None
        return store.save_record("generation_attempt", updated, expected_etag=etag)

    def _create_workspace(self, directory: Path) -> dict[str, Any]:
        now = self._now()
        workspace = {
            "schema": "amz-listing-kit/workspace@1",
            "workspace_id": f"ws_{uuid.uuid4().hex[:16]}",
            "created_at": now,
            "updated_at": now,
            "app_version": self.app_version,
            "status": "NEW",
            "assets": [],
            "current": {
                "product_input": None,
                "product_brief": None,
                "plan": None,
                "selection": None,
                "export": None,
            },
        }
        store = WorkspaceStore.create(directory, workspace)
        return self._project(store, store.load_workspace())

    def _open_workspace(self, directory: Path) -> dict[str, Any]:
        store = WorkspaceStore.open(directory)
        return self._project(store, store.load_workspace())

    def _generate_product_brief_draft(
        self, directory: Path, *, expected_etag: str | None,
    ) -> dict[str, Any]:
        if not isinstance(expected_etag, str) or not expected_etag:
            raise ServiceError("REVISION_REQUIRED", "请先重新载入工作空间，再分析商品资料。",
                               status_code=428, field="revision", next_action="reload_workspace")
        store = WorkspaceStore.open(directory)
        snapshot = store.load_workspace()
        if snapshot.etag != expected_etag:
            raise ServiceError("REVISION_CONFLICT", "工作空间已更新；请重新载入后再分析。",
                               status_code=409, field="revision", next_action="reload_workspace")
        input_ref = snapshot.workspace["current"]["product_input"]
        if input_ref is None:
            raise ServiceError("PRODUCT_INPUT_REQUIRED", "请先保存商品名称和至少一张参考图。",
                               status_code=422, field="product_input", next_action="save_product_input")
        product_input = store.get_record("product_input", input_ref["id"], version=input_ref["version"])
        images = []
        for digest in product_input["reference_asset_sha256"]:
            asset, content = store.read_asset_by_sha256(digest)
            images.append(SemanticImage(digest, asset["media_type"], content))
        try:
            response = self._semantic_provider_factory().analyze_product(product_input, images)
            brief = compile_product_brief_draft(
                response.data, product_input, provider_id=response.provider_id,
                model_id=response.model_id, request_id=response.request_id,
                reference_asset_sha256=list(product_input["reference_asset_sha256"]),
            )
        except SemanticProviderError as exc:
            status = (
                504 if exc.code == "UPSTREAM_UNKNOWN"
                else 503 if exc.code in {"PROVIDER_API_KEY_MISSING", "UPSTREAM_ACCOUNT_ARREARS"}
                else 502
            )
            next_action = (
                "wait_before_manual_retry" if status == 504
                else "recharge_dashscope_account_then_retry" if exc.code == "UPSTREAM_ACCOUNT_ARREARS"
                else "check_model_configuration"
            )
            raise ServiceError(
                exc.code, exc.message, status_code=status, field="semantic_provider",
                recoverable=exc.recoverable, next_action=next_action,
                details={"request_id": exc.request_id} if exc.request_id else {},
            ) from exc
        except SemanticDraftValidationError as exc:
            raise ServiceError("MODEL_OUTPUT_INVALID", "模型返回内容未通过商品理解结构校验；工作空间未改变。",
                               status_code=502, field="product_brief", next_action="review_product_input") from exc

        latest = store.load_workspace()
        if latest.etag != snapshot.etag:
            raise ServiceError("REVISION_CONFLICT", "分析期间工作空间已更新；这份草案未保存，请重新载入再分析。",
                               status_code=409, field="revision", next_action="reload_workspace")
        return {
            "product_brief": brief,
            "workspace_revision": snapshot.etag,
            "provider": {
                "provider_id": response.provider_id, "model_id": response.model_id,
                "request_id": response.request_id, "schema_mode": response.schema_mode,
            },
        }

    def _generate_product_plan(
        self, directory: Path, *, expected_etag: str | None,
    ) -> dict[str, Any]:
        if not isinstance(expected_etag, str) or not expected_etag:
            raise ServiceError("REVISION_REQUIRED", "请先重新载入工作空间，再生成套图方案。",
                               status_code=428, field="revision", next_action="reload_workspace")
        store = WorkspaceStore.open(directory)
        snapshot = store.load_workspace()
        if snapshot.etag != expected_etag:
            raise ServiceError("REVISION_CONFLICT", "工作空间已更新；请重新载入后再生成方案。",
                               status_code=409, field="revision", next_action="reload_workspace")
        current = snapshot.workspace["current"]
        input_ref, brief_ref = current["product_input"], current["product_brief"]
        if input_ref is None or brief_ref is None:
            raise ServiceError("PRODUCT_BRIEF_REQUIRED", "请先保存商品资料并确认商品理解，再生成套图方案。",
                               status_code=422, field="product_brief", next_action="save_product_brief")
        product_input = store.get_record("product_input", input_ref["id"], version=input_ref["version"])
        product_brief = store.get_record("product_brief", brief_ref["id"], version=brief_ref["version"])
        if product_brief["source_input"] != input_ref:
            raise ServiceError("PRODUCT_BRIEF_STALE", "商品资料已变化；请重新分析并保存商品理解。",
                               status_code=409, field="product_brief", next_action="reanalyze_product")

        paths = {
            "platform": contracts.ROOT / "config" / "product-v1" / "platforms" / "amazon-us.json",
            "archetypes": contracts.ROOT / "config" / "product-v1" / "archetypes.json",
            "providers": contracts.ROOT / "config" / "product-v1" / "providers.json",
        }
        try:
            platform_profile, archetypes, provider_registry = (
                json.loads(paths[name].read_text(encoding="utf-8"))
                for name in ("platform", "archetypes", "providers")
            )
            config_errors = contracts.validate_config_bundle(archetypes, platform_profile, provider_registry)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ServiceError("APP_CONFIGURATION_INVALID", "套图规则配置不可读取；未更改工作空间。",
                               status_code=500, field="configuration", recoverable=False,
                               next_action="contact_support") from exc
        if config_errors:
            raise ServiceError("APP_CONFIGURATION_INVALID", "套图规则配置未通过校验；未更改工作空间。",
                               status_code=500, field="configuration", recoverable=False,
                               next_action="contact_support", details={"issues": config_errors[:5]})
        profile_ref = {"profile_id": platform_profile["profile_id"], "version": platform_profile["version"]}
        if product_input["platform"] != profile_ref:
            raise ServiceError("PLATFORM_PROFILE_STALE", "商品资料关联的平台规则版本与当前配置不一致。",
                               status_code=409, field="platform", next_action="review_platform_profile")

        try:
            response = self._semantic_provider_factory().propose_plan(
                product_brief, platform_profile, archetypes, product_input.get("user_intent"),
            )
            compiled, warnings = compile_product_plan_draft(
                response.data, product_input, product_brief, platform_profile, archetypes,
            )
        except SemanticProviderError as exc:
            status = (
                504 if exc.code == "UPSTREAM_UNKNOWN"
                else 503 if exc.code in {"PROVIDER_API_KEY_MISSING", "UPSTREAM_ACCOUNT_ARREARS"}
                else 502
            )
            next_action = (
                "wait_before_manual_retry" if status == 504
                else "recharge_dashscope_account_then_retry" if exc.code == "UPSTREAM_ACCOUNT_ARREARS"
                else "check_model_configuration"
            )
            raise ServiceError(
                exc.code, exc.message, status_code=status, field="semantic_provider",
                recoverable=exc.recoverable, next_action=next_action,
                details={"request_id": exc.request_id} if exc.request_id else {},
            ) from exc
        except SemanticDraftValidationError as exc:
            raise ServiceError("MODEL_OUTPUT_INVALID", "模型返回的套图方案结构未通过校验；工作空间未改变。",
                               status_code=502, field="plan", next_action="retry_plan") from exc
        except ProductPlanCompilationError as exc:
            raise ServiceError("PLAN_DRAFT_INVALID", str(exc), status_code=502,
                               field="plan", next_action="retry_plan") from exc

        if store.load_workspace().etag != snapshot.etag:
            raise ServiceError("REVISION_CONFLICT", "生成方案期间工作空间已更新；本次方案未保存，请重新载入。",
                               status_code=409, field="revision", next_action="reload_workspace")

        with store.transaction():
            latest = store.load_workspace()
            if latest.etag != snapshot.etag:
                raise ServiceError("REVISION_CONFLICT", "工作空间已更新；本次方案未保存，请重新载入。",
                                   status_code=409, field="revision", next_action="reload_workspace")
            prior_plan_ref = latest.workspace["current"]["plan"]
            plan_id = prior_plan_ref["id"] if prior_plan_ref else f"plan_{uuid.uuid4().hex[:16]}"
            plan_version = max(
                (item["version"] for item in store.list_records("plan") if item["id"] == plan_id),
                default=0,
            ) + 1
            plan_ref = {"kind": "plan", "id": plan_id, "version": plan_version}
            shot_records = []
            plan_shot_refs = []
            for order, shot in enumerate(compiled["shots"], start=1):
                shot_ref = {"kind": "shot_spec", "id": shot["id"], "version": 1}
                plan_shot_refs.append({"shot": shot_ref, "order": order})
                shot_records.append(contracts.seal_record({
                    "schema": "amz-listing-kit/shot-spec@1",
                    "id": shot["id"], "version": 1, "workspace_id": latest.workspace["workspace_id"],
                    "plan": plan_ref,
                    "archetype_id": shot["archetype_id"], "title": shot["title"],
                    "purpose": shot["purpose"], "reason": shot["reason"],
                    "required": shot["required"], "preserve": shot["preserve"],
                    "change": shot["change"], "reference_asset_sha256": shot["reference_asset_sha256"],
                    "supporting_fact_keys": shot["supporting_fact_keys"],
                    "dependencies": shot["dependencies"],
                }))
            plan_record = contracts.seal_record({
                "schema": "amz-listing-kit/plan@1",
                "id": plan_id, "version": plan_version,
                "workspace_id": latest.workspace["workspace_id"], "created_at": self._now(),
                "source_brief": brief_ref, "platform": profile_ref,
                "style_lock": compiled["style_lock"], "shots": plan_shot_refs,
            })
            documents = {
                kind: store.list_records(kind)
                for kind in contracts.DOCUMENT_KINDS - {"workspace"}
            }
            documents["plan"].append(plan_record)
            documents["shot_spec"].extend(shot_records)
            changed = copy.deepcopy(latest.workspace)
            changed["current"]["plan"] = plan_ref
            changed["current"]["selection"] = None
            changed["current"]["export"] = None
            changed["status"] = "PLAN_READY"
            changed["updated_at"] = self._now()
            graph_errors = contracts.validate_workspace_graph(
                changed, documents, archetypes, platform_profile, provider_registry,
            )
            if graph_errors:
                raise ServiceError("PLAN_COMPILE_INVALID", "套图方案未通过本地来源与平台规则校验，因此没有保存。",
                                   status_code=502, field="plan", next_action="retry_plan",
                                   details={"issues": graph_errors[:8]})
            saved_plan = store.save_record("plan", plan_record)
            for record in shot_records:
                saved = store.save_record("shot_spec", record)
                if saved["version"] != 1:
                    raise WorkspaceConflict("a new compiled shot unexpectedly reused an existing version")
            committed = store.save_workspace(changed, expected_etag=latest.etag)
            projection = self._project(store, committed)
            projection["compile_warnings"] = warnings
            projection["semantic_provider"] = {
                "provider_id": response.provider_id, "model_id": response.model_id,
                "request_id": response.request_id, "schema_mode": response.schema_mode,
            }
            return projection

    def _save_product_plan(
        self,
        directory: Path,
        *,
        expected_etag: str | None,
        plan: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if not isinstance(expected_etag, str) or not expected_etag:
            raise ServiceError(
                "REVISION_REQUIRED", "请先重新载入工作空间，再保存套图方案。",
                status_code=428, field="revision", next_action="reload_workspace",
            )
        if not isinstance(plan, Mapping) or set(plan) != {"shots"}:
            raise ServiceError(
                "REQUEST_INVALID", "套图方案只接受 shots 图片列表。", status_code=400,
                field="plan", next_action="review_plan",
            )
        submitted_shots = plan.get("shots")
        if not isinstance(submitted_shots, list):
            raise ServiceError(
                "REQUEST_INVALID", "套图方案的 shots 必须是图片列表。", status_code=400,
                field="plan.shots", next_action="review_plan",
            )
        if not submitted_shots:
            raise ServiceError(
                "PLAN_EMPTY", "套图方案至少需要保留一张图片。", status_code=422,
                field="plan.shots", next_action="restore_a_shot",
            )

        store = WorkspaceStore.open(directory)
        with store.transaction():
            snapshot = store.load_workspace()
            if snapshot.etag != expected_etag:
                raise ServiceError(
                    "REVISION_CONFLICT", "工作空间已更新；请重新载入后再保存套图方案。",
                    status_code=409, field="revision", next_action="reload_workspace",
                )

            current = snapshot.workspace["current"]
            input_ref = current["product_input"]
            brief_ref = current["product_brief"]
            current_plan_ref = current["plan"]
            if input_ref is None or brief_ref is None or current_plan_ref is None:
                raise ServiceError(
                    "PLAN_REQUIRED", "请先保存商品资料、确认商品理解并生成套图方案。",
                    status_code=409, field="plan", next_action="generate_plan",
                )

            product_input = store.get_record(
                "product_input", input_ref["id"], version=input_ref["version"],
            )
            brief = store.get_record(
                "product_brief", brief_ref["id"], version=brief_ref["version"],
            )
            current_plan = store.get_record(
                "plan", current_plan_ref["id"], version=current_plan_ref["version"],
            )
            if brief["source_input"] != input_ref or current_plan["source_brief"] != brief_ref:
                raise ServiceError(
                    "PLAN_STALE", "当前套图方案不再对应已确认的商品资料，请重新生成方案。",
                    status_code=409, field="plan", next_action="generate_plan",
                )

            paths = {
                "platform": contracts.ROOT / "config" / "product-v1" / "platforms" / "amazon-us.json",
                "archetypes": contracts.ROOT / "config" / "product-v1" / "archetypes.json",
                "providers": contracts.ROOT / "config" / "product-v1" / "providers.json",
            }
            try:
                platform_profile, archetypes, provider_registry = (
                    json.loads(paths[name].read_text(encoding="utf-8"))
                    for name in ("platform", "archetypes", "providers")
                )
                config_errors = contracts.validate_config_bundle(
                    archetypes, platform_profile, provider_registry,
                )
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ServiceError(
                    "APP_CONFIGURATION_INVALID", "套图规则配置不可读取；工作空间未更改。",
                    status_code=500, field="configuration", recoverable=False,
                    next_action="contact_support",
                ) from exc
            if config_errors:
                raise ServiceError(
                    "APP_CONFIGURATION_INVALID", "套图规则配置未通过校验；工作空间未更改。",
                    status_code=500, field="configuration", recoverable=False,
                    next_action="contact_support", details={"issues": config_errors[:5]},
                )
            profile_ref = {
                "profile_id": platform_profile["profile_id"],
                "version": platform_profile["version"],
            }
            if product_input["platform"] != profile_ref or current_plan["platform"] != profile_ref:
                raise ServiceError(
                    "PLATFORM_PROFILE_STALE", "商品资料或方案关联的平台规则版本与当前配置不一致。",
                    status_code=409, field="platform", next_action="review_platform_profile",
                )

            current_shots: dict[str, dict[str, Any]] = {}
            for item in current_plan["shots"]:
                shot_ref = item["shot"]
                shot = store.get_record("shot_spec", shot_ref["id"], version=shot_ref["version"])
                if (shot.get("workspace_id") != snapshot.workspace["workspace_id"]
                        or shot.get("plan") != current_plan_ref):
                    raise ServiceError(
                        "PLAN_REFERENCE_INVALID", "当前方案包含不匹配的图片版本；没有保存更改。",
                        status_code=409, field="plan.shots", recoverable=False,
                        next_action="reopen_workspace",
                    )
                if shot["id"] in current_shots:
                    raise ServiceError(
                        "PLAN_REFERENCE_INVALID", "当前方案重复引用了同一张图片；没有保存更改。",
                        status_code=409, field="plan.shots", recoverable=False,
                        next_action="reopen_workspace",
                    )
                current_shots[shot["id"]] = shot

            editable_fields = {"title", "purpose", "reason", "preserve", "change"}
            allowed_fields = editable_fields | {"id", "dependencies"}
            required_fields = editable_fields | {"id"}
            desired_shots: list[dict[str, Any]] = []
            seen_ids: set[str] = set()
            for index, entry in enumerate(submitted_shots):
                field = f"plan.shots[{index}]"
                if not isinstance(entry, Mapping):
                    raise ServiceError(
                        "REQUEST_INVALID", "每张图片方案必须是对象。", status_code=400,
                        field=field, next_action="review_plan",
                    )
                keys = set(entry)
                unsupported_fields = keys - allowed_fields
                missing_fields = required_fields - keys
                if unsupported_fields or missing_fields:
                    raise ServiceError(
                        "REQUEST_INVALID", "图片方案包含不支持的字段或缺少可编辑内容。", status_code=400,
                        field=field, next_action="review_plan",
                        details={
                            "unsupported_fields": sorted(str(name) for name in unsupported_fields),
                            "missing_fields": sorted(str(name) for name in missing_fields),
                        },
                    )
                shot_id = entry.get("id")
                if not isinstance(shot_id, str) or not shot_id.strip():
                    raise ServiceError(
                        "SHOT_REFERENCE_INVALID", "图片方案缺少有效的 id。", status_code=422,
                        field=f"{field}.id", next_action="reload_workspace",
                    )
                shot_id = shot_id.strip()
                if shot_id in seen_ids:
                    raise ServiceError(
                        "DUPLICATE_SHOT", "同一张图片不能在方案中重复出现。", status_code=422,
                        field=f"{field}.id", next_action="remove_duplicate_shot",
                    )
                seen_ids.add(shot_id)
                original = current_shots.get(shot_id)
                if original is None:
                    raise ServiceError(
                        "SHOT_NOT_IN_CURRENT_PLAN", "图片 id 不属于当前套图方案，请重新载入后再编辑。",
                        status_code=422, field=f"{field}.id", next_action="reload_workspace",
                    )

                updated = copy.deepcopy(original)
                for name in ("title", "purpose", "reason"):
                    value = entry.get(name)
                    if not isinstance(value, str) or not value.strip():
                        raise ServiceError(
                            "PLAN_FIELD_INVALID", "标题、图片目的和方案理由不能为空。",
                            status_code=422, field=f"{field}.{name}", next_action="edit_plan_text",
                        )
                    updated[name] = value.strip()
                for name in ("preserve", "change"):
                    value = entry.get(name)
                    if (not isinstance(value, list)
                            or any(not isinstance(item, str) or not item.strip() for item in value)):
                        raise ServiceError(
                            "PLAN_FIELD_INVALID", "保持项和变化项必须是非空文字组成的列表。",
                            status_code=422, field=f"{field}.{name}", next_action="edit_plan_text",
                        )
                    updated[name] = [item.strip() for item in value]
                if "dependencies" in entry:
                    dependencies = entry["dependencies"]
                    if (not isinstance(dependencies, list)
                            or any(not isinstance(item, str) or not item.strip() for item in dependencies)):
                        raise ServiceError(
                            "PLAN_DEPENDENCY_INVALID", "图片依赖必须是有效的图片 id 列表。",
                            status_code=422, field=f"{field}.dependencies",
                            next_action="review_plan_dependencies",
                        )
                    dependencies = [item.strip() for item in dependencies]
                    if len(dependencies) != len(set(dependencies)):
                        raise ServiceError(
                            "PLAN_DEPENDENCY_INVALID", "图片依赖不能重复。", status_code=422,
                            field=f"{field}.dependencies", next_action="review_plan_dependencies",
                        )
                    updated["dependencies"] = dependencies
                desired_shots.append(updated)

            required_archetypes = set(platform_profile["required_archetypes"])
            if not desired_shots:
                raise ServiceError(
                    "PLAN_EMPTY", "套图方案至少需要保留一张图片。", status_code=422,
                    field="plan.shots", next_action="restore_a_shot",
                )
            present_archetypes = {shot["archetype_id"] for shot in desired_shots}
            missing_archetypes = sorted(required_archetypes - present_archetypes)
            if missing_archetypes:
                raise ServiceError(
                    "REQUIRED_SHOT_CANNOT_DELETE", "平台必需图片不能删除。",
                    status_code=422, field="plan.shots", next_action="restore_required_shot",
                    details={"required_archetypes": missing_archetypes},
                )

            desired_ids = {shot["id"] for shot in desired_shots}
            for shot in desired_shots:
                invalid_dependencies = [
                    dependency for dependency in shot["dependencies"]
                    if dependency == shot["id"] or dependency not in desired_ids
                ]
                if invalid_dependencies:
                    raise ServiceError(
                        "PLAN_DEPENDENCY_INVALID", "图片依赖必须指向本套图中保留的其他图片。",
                        status_code=422, field=f"plan.shots.{shot['id']}.dependencies",
                        next_action="review_plan_dependencies",
                        details={"invalid_shot_ids": invalid_dependencies},
                    )

            all_plans = store.list_records("plan")
            plan_version = max((item["version"] for item in all_plans), default=0) + 1
            plan_ref = {"kind": "plan", "id": current_plan["id"], "version": plan_version}
            all_shot_specs = store.list_records("shot_spec")
            next_shot_versions = {
                shot_id: max(
                    (item["version"] for item in all_shot_specs if item["id"] == shot_id),
                    default=0,
                ) + 1
                for shot_id in desired_ids
            }
            shot_records: list[dict[str, Any]] = []
            plan_shot_refs = []
            for order, shot in enumerate(desired_shots, start=1):
                shot_version = next_shot_versions[shot["id"]]
                shot_ref = {"kind": "shot_spec", "id": shot["id"], "version": shot_version}
                plan_shot_refs.append({"shot": shot_ref, "order": order})
                shot_records.append(contracts.seal_record({
                    "schema": "amz-listing-kit/shot-spec@1",
                    "id": shot["id"], "version": shot_version,
                    "workspace_id": snapshot.workspace["workspace_id"], "plan": plan_ref,
                    "archetype_id": shot["archetype_id"], "title": shot["title"],
                    "purpose": shot["purpose"], "reason": shot["reason"],
                    "required": shot["required"], "preserve": shot["preserve"],
                    "change": shot["change"],
                    "reference_asset_sha256": shot["reference_asset_sha256"],
                    "supporting_fact_keys": shot["supporting_fact_keys"],
                    "dependencies": shot["dependencies"],
                }))
            plan_record = contracts.seal_record({
                "schema": "amz-listing-kit/plan@1",
                "id": current_plan["id"], "version": plan_version,
                "workspace_id": snapshot.workspace["workspace_id"], "created_at": self._now(),
                "source_brief": brief_ref, "platform": current_plan["platform"],
                "style_lock": copy.deepcopy(current_plan["style_lock"]),
                "shots": plan_shot_refs,
            })

            documents = {
                kind: store.list_records(kind)
                for kind in contracts.DOCUMENT_KINDS - {"workspace"}
            }
            documents["plan"].append(plan_record)
            documents["shot_spec"].extend(shot_records)
            changed = copy.deepcopy(snapshot.workspace)
            changed["current"]["plan"] = plan_ref
            changed["current"]["selection"] = None
            changed["current"]["export"] = None
            changed["status"] = "PLAN_READY"
            changed["updated_at"] = self._now()
            graph_errors = contracts.validate_workspace_graph(
                changed, documents, archetypes, platform_profile, provider_registry,
            )
            if graph_errors:
                raise ServiceError(
                    "PLAN_EDIT_INVALID", "套图方案未通过本地引用与平台规则校验，因此没有保存。",
                    status_code=422, field="plan", next_action="review_plan",
                    details={"issues": graph_errors[:8]},
                )

            for record in shot_records:
                saved = store.save_record("shot_spec", record)
                if saved["version"] != record["version"]:
                    raise WorkspaceConflict("shot spec version changed after compare-and-swap validation")
            saved_plan = store.save_record("plan", plan_record)
            if saved_plan["version"] != plan_record["version"]:
                raise WorkspaceConflict("plan version changed after compare-and-swap validation")
            committed = store.save_workspace(changed, expected_etag=snapshot.etag)
            return self._project(store, committed)

    def _load_active_prompt_context(
        self, store: WorkspaceStore, shot_id: str | None,
    ) -> tuple[WorkspaceSnapshot, dict[str, Any], dict[str, Any], dict[str, Any],
               dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        if not isinstance(shot_id, str) or not shot_id.strip():
            raise ServiceError("SHOT_REQUIRED", "请选择要处理的图片方案。", status_code=400,
                               field="shot_id", next_action="choose_shot")
        snapshot = store.load_workspace()
        current = snapshot.workspace["current"]
        input_ref, brief_ref, plan_ref = (
            current["product_input"], current["product_brief"], current["plan"]
        )
        if input_ref is None or brief_ref is None:
            raise ServiceError("PRODUCT_BRIEF_REQUIRED", "请先保存商品资料并确认商品理解。",
                               status_code=422, field="product_brief", next_action="save_product_brief")
        if plan_ref is None:
            raise ServiceError("PLAN_REQUIRED", "请先生成当前商品的套图方案。",
                               status_code=422, field="plan", next_action="generate_plan")
        product_input = store.get_record("product_input", input_ref["id"], version=input_ref["version"])
        product_brief = store.get_record("product_brief", brief_ref["id"], version=brief_ref["version"])
        plan = store.get_record("plan", plan_ref["id"], version=plan_ref["version"])
        if product_brief["source_input"] != input_ref:
            raise ServiceError("PRODUCT_BRIEF_STALE", "商品资料已变化；请重新分析并保存商品理解。",
                               status_code=409, field="product_brief", next_action="reanalyze_product")
        if plan["source_brief"] != brief_ref:
            raise ServiceError("PLAN_STALE", "套图方案不再对应当前商品理解，请重新生成方案。",
                               status_code=409, field="plan", next_action="generate_plan")

        shot_ref = next((item["shot"] for item in plan["shots"] if item["shot"]["id"] == shot_id.strip()), None)
        if shot_ref is None:
            raise ServiceError("SHOT_NOT_IN_CURRENT_PLAN", "这张图片不属于当前套图方案，请重新载入。",
                               status_code=404, field="shot_id", next_action="reload_workspace")
        shot_spec = store.get_record("shot_spec", shot_ref["id"], version=shot_ref["version"])

        paths = {
            "platform": contracts.ROOT / "config" / "product-v1" / "platforms" / "amazon-us.json",
            "archetypes": contracts.ROOT / "config" / "product-v1" / "archetypes.json",
            "providers": contracts.ROOT / "config" / "product-v1" / "providers.json",
        }
        try:
            platform_profile, archetypes, provider_registry = (
                json.loads(paths[name].read_text(encoding="utf-8"))
                for name in ("platform", "archetypes", "providers")
            )
            config_errors = contracts.validate_config_bundle(archetypes, platform_profile, provider_registry)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ServiceError("APP_CONFIGURATION_INVALID", "套图规则配置不可读取；工作空间未改变。",
                               status_code=500, field="configuration", recoverable=False,
                               next_action="contact_support") from exc
        if config_errors:
            raise ServiceError("APP_CONFIGURATION_INVALID", "套图规则配置未通过校验；工作空间未改变。",
                               status_code=500, field="configuration", recoverable=False,
                               next_action="contact_support", details={"issues": config_errors[:5]})
        profile_ref = {"profile_id": platform_profile["profile_id"], "version": platform_profile["version"]}
        if product_input["platform"] != profile_ref or plan["platform"] != profile_ref:
            raise ServiceError("PLATFORM_PROFILE_STALE", "商品资料或方案关联的平台规则版本与当前配置不一致。",
                               status_code=409, field="platform", next_action="review_platform_profile")
        return (snapshot, product_input, product_brief, plan, shot_spec,
                platform_profile, archetypes, provider_registry)

    @staticmethod
    def _prompt_versions_for_shot(
        prompt_records: Sequence[Mapping[str, Any]],
        plan: Mapping[str, Any],
        shot: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        plan_ref = {"kind": "plan", "id": plan["id"], "version": plan["version"]}
        shot_ref = {"kind": "shot_spec", "id": shot["id"], "version": shot["version"]}
        return sorted(
            [dict(item) for item in prompt_records if item.get("plan") == plan_ref and item.get("shot") == shot_ref],
            key=lambda item: int(item["version"]),
        )

    @staticmethod
    def _next_prompt_version(prompt_records: Sequence[Mapping[str, Any]], shot_id: str) -> int:
        """Version prompts per image folder, so a new Plan/Shot version keeps the sequence valid.

        WorkspaceStore numbers records from the files already present in that image's
        folder; counting only the current Plan/Shot lineage would collide with earlier
        versions of the same image and abort the whole save.
        """
        return max(
            (int(item["version"]) for item in prompt_records if item.get("shot", {}).get("id") == shot_id),
            default=0,
        ) + 1

    @staticmethod
    def _prompt_diff_summary(before: str, after: str, *, manual: bool) -> str:
        changed = sum(
            1 for tag, _i1, _i2, _j1, _j2 in difflib.SequenceMatcher(None, before, after).get_opcodes()
            if tag != "equal"
        )
        label = "用户编辑" if manual else "重新编译"
        return f"{label}提示词：{changed} 处文本变化（{len(before)} → {len(after)} 字）。"

    def _commit_prompt_version(
        self,
        store: WorkspaceStore,
        *,
        expected_etag: str,
        expected_parent: dict[str, Any] | None,
        plan: Mapping[str, Any],
        shot_spec: Mapping[str, Any],
        record: dict[str, Any],
        platform_profile: Mapping[str, Any],
        archetypes: Mapping[str, Any],
        provider_registry: Mapping[str, Any],
    ) -> dict[str, Any]:
        with store.transaction():
            latest = store.load_workspace()
            if latest.etag != expected_etag:
                raise ServiceError("REVISION_CONFLICT", "工作空间已变化；请重新载入后再保存提示词。",
                                   status_code=409, field="revision", next_action="reload_workspace")
            current_versions = self._prompt_versions_for_shot(
                store.list_records("prompt"), plan, shot_spec,
            )
            current_parent = None
            if current_versions:
                previous = current_versions[-1]
                current_parent = {"kind": "prompt", "id": previous["id"], "version": previous["version"]}
            if current_parent != expected_parent:
                raise ServiceError("PROMPT_VERSION_CONFLICT", "这张图片的提示词已被更新；请重新载入再编辑。",
                                   status_code=409, field="prompt", next_action="reload_workspace")

            candidate = contracts.seal_record(record)
            documents = {
                kind: store.list_records(kind)
                for kind in contracts.DOCUMENT_KINDS - {"workspace"}
            }
            documents["prompt"].append(candidate)
            graph_errors = contracts.validate_workspace_graph(
                latest.workspace, documents, archetypes, platform_profile, provider_registry,
            )
            if graph_errors:
                raise ServiceError("PROMPT_COMPILE_INVALID", "提示词版本未通过本地引用与内容校验，因此没有保存。",
                                   status_code=502, field="prompt", next_action="review_prompt_sources",
                                   details={"issues": graph_errors[:8]})
            saved = store.save_record("prompt", candidate)
            if saved["version"] != record["version"]:
                raise WorkspaceConflict("prompt version changed after compare-and-swap validation")
            changed = copy.deepcopy(latest.workspace)
            changed["updated_at"] = self._now()
            committed = store.save_workspace(changed, expected_etag=latest.etag)
            return self._project(store, committed)

    def _generate_prompt(
        self, directory: Path, *, expected_etag: str | None, shot_id: str | None,
    ) -> dict[str, Any]:
        if not isinstance(expected_etag, str) or not expected_etag:
            raise ServiceError("REVISION_REQUIRED", "请先重新载入工作空间，再生成提示词。",
                               status_code=428, field="revision", next_action="reload_workspace")
        store = WorkspaceStore.open(directory)
        (snapshot, product_input, product_brief, plan, shot_spec,
         platform_profile, archetypes, provider_registry) = self._load_active_prompt_context(store, shot_id)
        if snapshot.etag != expected_etag:
            raise ServiceError("REVISION_CONFLICT", "工作空间已更新；请重新载入后再生成提示词。",
                               status_code=409, field="revision", next_action="reload_workspace")

        prompt_records = store.list_records("prompt")
        versions = self._prompt_versions_for_shot(prompt_records, plan, shot_spec)
        latest_prompt = versions[-1] if versions else None
        expected_parent = (
            {"kind": "prompt", "id": latest_prompt["id"], "version": latest_prompt["version"]}
            if latest_prompt else None
        )
        support_keys = set(shot_spec.get("supporting_fact_keys", []))
        supported_facts = [
            {"key": fact["key"], "value": fact["value"], "source": fact["source"]}
            for fact in product_brief.get("facts", [])
            if fact.get("key") in support_keys
            and fact.get("state") == "confirmed"
            and fact.get("source") in {"user_input", "user_override"}
        ]
        safe_brief = {"confirmed_facts": supported_facts}
        safe_shot = {
            key: shot_spec[key]
            for key in ("title", "archetype_id", "purpose", "preserve", "change", "supporting_fact_keys")
        }
        user_intent = product_input.get("user_intent")
        style_spec = {
            "style_lock": copy.deepcopy(plan["style_lock"]),
            "platform_profile": copy.deepcopy(platform_profile),
            "locale": platform_profile.get("locale"),
            "user_intent": user_intent,
            "available_source_refs": [
                "plan.style_lock", "shot_spec.title", "shot_spec.purpose",
                "shot_spec.preserve", "shot_spec.change",
                *(["product_input.user_intent"] if user_intent else []),
                *[f"product_brief.fact:{fact['key']}" for fact in supported_facts],
            ],
        }
        try:
            response = self._semantic_provider_factory().propose_prompt_blocks(
                safe_brief, safe_shot, style_spec,
            )
            blocks, full_text = compile_prompt_blocks(
                response.data,
                product_input=product_input,
                product_brief=product_brief,
                shot_spec=shot_spec,
                plan=plan,
                platform_profile=platform_profile,
            )
        except SemanticProviderError as exc:
            status = (
                504 if exc.code == "UPSTREAM_UNKNOWN"
                else 503 if exc.code in {"PROVIDER_API_KEY_MISSING", "UPSTREAM_ACCOUNT_ARREARS"}
                else 502
            )
            next_action = (
                "wait_before_manual_retry" if status == 504
                else "recharge_dashscope_account_then_retry" if exc.code == "UPSTREAM_ACCOUNT_ARREARS"
                else "check_model_configuration"
            )
            raise ServiceError(
                exc.code, exc.message, status_code=status, field="semantic_provider",
                recoverable=exc.recoverable, next_action=next_action,
                details={"request_id": exc.request_id} if exc.request_id else {},
            ) from exc
        except SemanticDraftValidationError as exc:
            raise ServiceError("PROMPT_DRAFT_INVALID", "模型返回的提示词方向结构未通过校验；工作空间未改变。",
                               status_code=502, field="prompt_blocks", next_action="retry_prompt_compile") from exc
        except ProductPromptCompilationError as exc:
            raise ServiceError("PROMPT_COMPILE_INVALID", str(exc), status_code=502,
                               field="prompt", next_action="review_prompt_sources") from exc

        next_version = self._next_prompt_version(prompt_records, shot_spec["id"])
        record = {
            "schema": "amz-listing-kit/prompt@1",
            "id": latest_prompt["id"] if latest_prompt else f"prompt_{uuid.uuid4().hex[:16]}",
            "version": next_version,
            "workspace_id": snapshot.workspace["workspace_id"],
            "created_at": self._now(),
            "shot": {"kind": "shot_spec", "id": shot_spec["id"], "version": shot_spec["version"]},
            "plan": {"kind": "plan", "id": plan["id"], "version": plan["version"]},
            "blocks": blocks,
            "full_text": full_text,
            "full_text_sha256": hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
            "edit_mode": "compiled",
            "parent": expected_parent,
            "diff_summary": (
                self._prompt_diff_summary(latest_prompt["full_text"], full_text, manual=False)
                if latest_prompt else None
            ),
        }
        projection = self._commit_prompt_version(
            store,
            expected_etag=expected_etag,
            expected_parent=expected_parent,
            plan=plan,
            shot_spec=shot_spec,
            record=record,
            platform_profile=platform_profile,
            archetypes=archetypes,
            provider_registry=provider_registry,
        )
        projection["semantic_provider"] = {
            "provider_id": response.provider_id, "model_id": response.model_id,
            "request_id": response.request_id, "schema_mode": response.schema_mode,
        }
        return projection

    def _save_prompt_edit(
        self,
        directory: Path,
        *,
        expected_etag: str | None,
        shot_id: str | None,
        expected_prompt_version: int | None,
        full_text: str | None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(expected_etag, str) or not expected_etag:
            raise ServiceError("REVISION_REQUIRED", "请先重新载入工作空间，再保存提示词。",
                               status_code=428, field="revision", next_action="reload_workspace")
        if (not isinstance(expected_prompt_version, int) or isinstance(expected_prompt_version, bool)
                or expected_prompt_version < 1):
            raise ServiceError("PROMPT_VERSION_REQUIRED", "请重新载入这张图片的提示词后再保存。",
                               status_code=428, field="expected_prompt_version", next_action="reload_workspace")
        if not isinstance(full_text, str) or not full_text.strip() or len(full_text) > 20000:
            raise ServiceError("PROMPT_TEXT_INVALID", "提示词不能为空，且不能超过 20,000 个字符。",
                               status_code=422, field="full_text", next_action="edit_prompt")
        edit_reason: str | None = None
        if reason is not None:
            if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 500:
                raise ServiceError(
                    "REWORK_REASON_INVALID", "请用一句话说明这次返工想改什么（不超过 500 字）。",
                    status_code=422, field="reason", next_action="describe_rework",
                )
            edit_reason = reason.strip()

        store = WorkspaceStore.open(directory)
        (snapshot, _product_input, _product_brief, plan, shot_spec,
         platform_profile, archetypes, provider_registry) = self._load_active_prompt_context(store, shot_id)
        if snapshot.etag != expected_etag:
            raise ServiceError("REVISION_CONFLICT", "工作空间已更新；请重新载入后再编辑提示词。",
                               status_code=409, field="revision", next_action="reload_workspace")
        prompt_records = store.list_records("prompt")
        versions = self._prompt_versions_for_shot(prompt_records, plan, shot_spec)
        latest_prompt = versions[-1] if versions else None
        if latest_prompt is None:
            raise ServiceError("PROMPT_NOT_COMPILED", "请先为这张图片生成系统提示词。",
                               status_code=409, field="prompt", next_action="compile_prompt")
        if latest_prompt["version"] != expected_prompt_version:
            raise ServiceError("PROMPT_VERSION_CONFLICT", "这张图片的提示词已被更新；请重新载入再编辑。",
                               status_code=409, field="expected_prompt_version", next_action="reload_workspace")
        if latest_prompt["full_text"] == full_text:
            return self._project(store, snapshot)

        expected_parent = {
            "kind": "prompt", "id": latest_prompt["id"], "version": latest_prompt["version"],
        }
        next_version = self._next_prompt_version(prompt_records, shot_spec["id"])
        record = {
            "schema": "amz-listing-kit/prompt@1",
            "id": latest_prompt["id"],
            "version": next_version,
            "workspace_id": snapshot.workspace["workspace_id"],
            "created_at": self._now(),
            "shot": {"kind": "shot_spec", "id": shot_spec["id"], "version": shot_spec["version"]},
            "plan": {"kind": "plan", "id": plan["id"], "version": plan["version"]},
            "blocks": [{
                "id": "manual-full-prompt", "kind": "shot_task", "text": full_text,
                "source_refs": ["user:manual"],
            }],
            "full_text": full_text,
            "full_text_sha256": hashlib.sha256(full_text.encode("utf-8")).hexdigest(),
            "edit_mode": "manual",
            "parent": expected_parent,
            "diff_summary": self._prompt_diff_summary(
                latest_prompt["full_text"], full_text, manual=True,
            ),
            "edit_reason": edit_reason,
        }
        return self._commit_prompt_version(
            store,
            expected_etag=expected_etag,
            expected_parent=expected_parent,
            plan=plan,
            shot_spec=shot_spec,
            record=record,
            platform_profile=platform_profile,
            archetypes=archetypes,
            provider_registry=provider_registry,
        )

    def _save_product_brief(
        self, directory: Path, *, expected_etag: str | None, fields: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(expected_etag, str) or not expected_etag:
            raise ServiceError("REVISION_REQUIRED", "请先重新载入工作空间，再保存商品理解。",
                               status_code=428, field="revision", next_action="reload_workspace")
        store = WorkspaceStore.open(directory)
        with store.transaction():
            current = store.load_workspace()
            if current.etag != expected_etag:
                raise ServiceError("REVISION_CONFLICT", "工作空间已更新；请重新载入后再保存。",
                                   status_code=409, field="revision", next_action="reload_workspace")
            input_ref = current.workspace["current"]["product_input"]
            if input_ref is None:
                raise ServiceError("PRODUCT_INPUT_REQUIRED", "请先保存商品资料，再保存商品理解。",
                                   status_code=422, field="product_input", next_action="save_product_input")
            product_input = store.get_record("product_input", input_ref["id"], version=input_ref["version"])
            try:
                normalized = normalize_product_brief_edits(fields, product_input)
            except ProductBriefEditError as exc:
                raise ServiceError("PRODUCT_BRIEF_INVALID", str(exc), status_code=422,
                                   field="product_brief", next_action="correct_product_brief") from exc

            existing_ref = current.workspace["current"]["product_brief"]
            previous = None
            if existing_ref is not None:
                previous = store.get_record("product_brief", existing_ref["id"], version=existing_ref["version"])
                if all(previous[key] == normalized[key] for key in _BRIEF_EDITABLE_FIELDS):
                    return self._project(store, current)
            record = {
                "schema": "amz-listing-kit/product-brief@1",
                "id": previous["id"] if previous else f"brief_{uuid.uuid4().hex[:16]}",
                "workspace_id": current.workspace["workspace_id"], "created_at": self._now(),
                "source_input": {"kind": "product_input", "id": product_input["id"], "version": product_input["version"]},
                **normalized,
            }
            saved = store.save_record("product_brief", record)
            changed = copy.deepcopy(current.workspace)
            changed["current"]["product_brief"] = {"kind": "product_brief", "id": saved["id"], "version": saved["version"]}
            changed["current"]["plan"] = None
            changed["current"]["selection"] = None
            changed["current"]["export"] = None
            changed["updated_at"] = saved["created_at"]
            committed = store.save_workspace(changed, expected_etag=current.etag)
            return self._project(store, committed)

    def _save_intake(
        self,
        directory: Path,
        *,
        expected_etag: str | None,
        product_name: str,
        description: str | None,
        selling_points: Sequence[str] | None,
        user_intent: str | None,
        reference_images: Sequence[ImageUpload] | None,
    ) -> dict[str, Any]:
        if not isinstance(expected_etag, str) or not expected_etag:
            raise ServiceError(
                "REVISION_REQUIRED",
                "请先重新载入工作空间，再保存商品资料。",
                status_code=428,
                field="revision",
                next_action="reload_workspace",
            )
        clean_name = self._required_text(product_name, "product_name")
        clean_description = self._optional_text(description, "description")
        clean_intent = self._optional_text(user_intent, "user_intent")
        clean_points = self._selling_points(selling_points)
        prepared_uploads = self._prepare_uploads(reference_images)
        platform_ref = self._amazon_us_ref()

        store = WorkspaceStore.open(directory)
        with store.transaction():
            current = store.load_workspace()
            if current.etag != expected_etag:
                raise ServiceError(
                    "REVISION_CONFLICT",
                    "工作空间已在别处更新；请重新载入后再保存。",
                    status_code=409,
                    field="revision",
                    next_action="reload_workspace",
                )
            if any(current.workspace["current"][key] is not None for key in ("product_brief", "plan", "selection", "export")):
                raise ServiceError(
                    "DEPENDENT_RECORDS_PRESENT",
                    "当前版本暂不支持在已有方案或结果后直接改写商品资料。",
                    status_code=409,
                    field="product_name",
                    recoverable=False,
                    next_action="open_another_workspace",
                )

            input_ref = current.workspace["current"]["product_input"]
            existing_input = None
            if input_ref is not None:
                existing_input = store.get_record(
                    "product_input", input_ref["id"], version=input_ref["version"]
                )
            if reference_images is None:
                selected_hashes = list(existing_input["reference_asset_sha256"]) if existing_input else []
            else:
                selected_hashes = [upload["sha256"] for upload in prepared_uploads]
            selected_hashes = list(dict.fromkeys(selected_hashes))

            missing = []
            if not clean_name:
                missing.append("product_name")
            if not selected_hashes:
                missing.append("reference_images")
            if missing:
                field = "product_name" if missing[0] == "product_name" else "reference_images"
                raise ServiceError(
                    "INTAKE_REQUIRED",
                    "保存前请补齐商品名称和至少一张参考图。",
                    status_code=422,
                    field=field,
                    next_action="add_missing_material",
                    details={"missing_fields": missing},
                )

            assets = copy.deepcopy(current.workspace["assets"])
            assets_by_hash = {asset["sha256"]: asset for asset in assets}
            for upload in prepared_uploads:
                digest = upload["sha256"]
                relative_path = f"inputs/originals/{digest}.{upload['extension']}"
                store.save_immutable_file(
                    relative_path, upload["content"], expected_sha256=digest
                )
                if digest not in assets_by_hash:
                    asset = {
                        "sha256": digest,
                        "relative_path": relative_path,
                        "original_name": upload["filename"],
                        "media_type": upload["media_type"],
                        "byte_size": len(upload["content"]),
                        "width": upload["width"],
                        "height": upload["height"],
                        "role": upload["role"],
                        "source": "user_upload",
                    }
                    assets.append(asset)
                    assets_by_hash[digest] = asset
            missing_assets = [digest for digest in selected_hashes if digest not in assets_by_hash]
            if missing_assets:
                raise ServiceError(
                    "WORKSPACE_CORRUPT",
                    "所选参考图不在工作空间素材清单中，未保存本次资料。",
                    status_code=422,
                    field="reference_images",
                    recoverable=False,
                    next_action="reopen_workspace",
                    details={"missing_asset_sha256": missing_assets},
                )

            previous_points = {
                item["text"]: item for item in (existing_input or {}).get("selling_points", [])
            }
            normalized_points = []
            for text in clean_points:
                previous = previous_points.get(text)
                normalized_points.append({
                    "id": previous["id"] if previous else f"sp_{uuid.uuid4().hex[:12]}",
                    "text": text,
                    "source": "user",
                    "confirmed": True,
                })

            record = {
                "schema": "amz-listing-kit/product-input@1",
                "id": existing_input["id"] if existing_input else f"input_{uuid.uuid4().hex[:16]}",
                "workspace_id": current.workspace["workspace_id"],
                "created_at": self._now(),
                "product_name": clean_name,
                "description": clean_description,
                "selling_points": normalized_points,
                "platform": platform_ref,
                "reference_asset_sha256": selected_hashes,
                "user_intent": clean_intent,
            }
            if existing_input and all(
                existing_input.get(field) == record.get(field)
                for field in (
                    "product_name", "description", "selling_points", "platform",
                    "reference_asset_sha256", "user_intent",
                )
            ):
                return self._project(store, current)

            saved_input = store.save_record("product_input", record)
            changed = copy.deepcopy(current.workspace)
            changed["assets"] = assets
            changed["current"]["product_input"] = {
                "kind": "product_input",
                "id": saved_input["id"],
                "version": saved_input["version"],
            }
            changed["current"]["product_brief"] = None
            changed["current"]["plan"] = None
            changed["current"]["selection"] = None
            changed["current"]["export"] = None
            changed["status"] = "INTAKE_READY"
            changed["updated_at"] = saved_input["created_at"]
            committed = store.save_workspace(changed, expected_etag=current.etag)
            return self._project(store, committed)

    def _project(self, store: WorkspaceStore, snapshot: WorkspaceSnapshot) -> dict[str, Any]:
        workspace = snapshot.workspace
        current_ref = workspace["current"]["product_input"]
        product_input = None
        if current_ref is not None:
            product_input = store.get_record(
                "product_input", current_ref["id"], version=current_ref["version"]
            )
        brief_ref = workspace["current"]["product_brief"]
        product_brief = None
        if brief_ref is not None:
            product_brief = store.get_record(
                "product_brief", brief_ref["id"], version=brief_ref["version"]
            )

        plan_ref = workspace["current"]["plan"]
        plan = None
        if plan_ref is not None:
            plan = store.get_record("plan", plan_ref["id"], version=plan_ref["version"])
            prompt_records = store.list_records("prompt")
            attempt_records = store.list_records("generation_attempt")
            candidate_records = store.list_records("candidate")
            shot_specs = []
            for item in plan["shots"]:
                shot = store.get_record("shot_spec", item["shot"]["id"], version=item["shot"]["version"])
                shot["order"] = item["order"]
                prompt_versions = self._prompt_versions_for_shot(prompt_records, plan, shot)
                shot["prompt_versions"] = prompt_versions
                shot["latest_prompt"] = prompt_versions[-1] if prompt_versions else None
                # Keep earlier plan versions available for comparison while retaining their
                # original ShotSpec and Prompt references on every record.
                shot_id = shot["id"]
                shot["generation_attempts"] = sorted(
                    (record for record in attempt_records if record["shot"]["id"] == shot_id),
                    key=lambda record: (record["created_at"], record["action_id"]),
                )
                shot["candidates"] = sorted(
                    (record for record in candidate_records if record["shot"]["id"] == shot_id),
                    key=lambda record: (record["created_at"], record["candidate_id"]),
                )
                shot_specs.append(shot)
            plan["shot_specs"] = shot_specs

        assets_by_hash = {asset["sha256"]: asset for asset in workspace["assets"]}
        references = []
        for digest in (product_input or {}).get("reference_asset_sha256", []):
            asset = assets_by_hash.get(digest)
            if asset is None:
                raise ServiceError(
                    "WORKSPACE_CORRUPT",
                    "当前商品资料引用了素材清单中不存在的图片。",
                    status_code=422,
                    field="reference_images",
                    recoverable=False,
                    next_action="reopen_workspace",
                    details={"missing_asset_sha256": [digest]},
                )
            references.append({
                "sha256": asset["sha256"],
                "name": asset["original_name"],
                "media_type": asset["media_type"],
                "byte_size": asset["byte_size"],
                "width": asset["width"],
                "height": asset["height"],
                "role": asset["role"],
            })

        product_name = (product_input or {}).get("product_name", "")
        missing = []
        if not product_name:
            missing.append("product_name")
        if not references:
            missing.append("reference_images")
        selection_ref = workspace["current"]["selection"]
        selection = None
        if selection_ref is not None:
            selection = store.get_record(
                "selection", selection_ref["id"], version=selection_ref["version"],
            )
        export_ref = workspace["current"]["export"]
        export = None
        if export_ref is not None:
            export = store.get_record(
                "export", export_ref["id"], version=export_ref["version"],
            )
        return {
            "workspace": {
                "id": workspace["workspace_id"],
                "status": workspace["status"],
                "created_at": workspace["created_at"],
                "updated_at": workspace["updated_at"],
                "revision": snapshot.etag,
            },
            "intake": {
                "product_name": product_name,
                "description": (product_input or {}).get("description") or "",
                "selling_points": copy.deepcopy((product_input or {}).get("selling_points", [])),
                "user_intent": (product_input or {}).get("user_intent") or "",
                "reference_images": references,
            },
            "readiness": {
                "state": "EMPTY" if current_ref is None else "READY",
                "can_save_intake": not missing,
                "can_generate_product_brief": current_ref is not None and not missing,
                "can_generate_plan": product_brief is not None and product_input is not None and not missing,
                "can_generate_prompts": plan is not None and bool(plan.get("shot_specs")),
                "missing_required": missing,
            },
            "product_brief": product_brief,
            "plan": plan,
            "selection": selection,
            "export": export,
        }

    def _prepare_uploads(self, uploads: Sequence[ImageUpload] | None) -> list[dict[str, Any]]:
        if uploads is None:
            return []
        if isinstance(uploads, (str, bytes)) or not isinstance(uploads, Sequence):
            raise ServiceError(
                "REQUEST_INVALID", "参考图片必须作为文件列表提交。", status_code=400,
                field="reference_images", next_action="select_reference_images",
            )
        if not 1 <= len(uploads) <= 3:
            raise ServiceError(
                "REFERENCE_IMAGE_COUNT", "一次资料保存需要选择 1–3 张参考图。", status_code=422,
                field="reference_images", next_action="select_reference_images",
                details={"minimum": 1, "maximum": 3, "received": len(uploads)},
            )

        prepared = []
        seen = set()
        for index, upload in enumerate(uploads):
            field = f"reference_images[{index}]"
            if not isinstance(upload, ImageUpload):
                raise ServiceError(
                    "REQUEST_INVALID", "参考图片文件信息不完整。", status_code=400,
                    field=field, next_action="select_reference_images",
                )
            if not isinstance(upload.filename, str):
                raise ServiceError(
                    "REFERENCE_IMAGE_INVALID", "参考图文件名称无效。", status_code=422,
                    field=field, next_action="replace_reference_image",
                )
            filename = upload.filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
            if not filename or not isinstance(upload.content, bytes) or not upload.content:
                raise ServiceError(
                    "REFERENCE_IMAGE_INVALID", "参考图文件为空或名称无效。", status_code=422,
                    field=field, next_action="replace_reference_image",
                )
            if not isinstance(upload.role, str) or upload.role not in _ASSET_ROLES:
                raise ServiceError(
                    "REFERENCE_IMAGE_ROLE_INVALID", "参考图用途不受支持。", status_code=422,
                    field=f"{field}.role", next_action="choose_reference_role",
                )
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(io.BytesIO(upload.content)) as image:
                        image_format = image.format
                        width, height = image.size
                        image.verify()
            except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
                raise ServiceError(
                    "REFERENCE_IMAGE_INVALID", "无法读取这张图片，请换一张有效的 JPEG、PNG、TIFF 或 GIF。",
                    status_code=422, field=field, next_action="replace_reference_image",
                    details={"filename": filename},
                ) from exc
            media_type, extension = _IMAGE_FORMATS.get(image_format or "", (None, None))
            if media_type is None or width < 1 or height < 1:
                raise ServiceError(
                    "REFERENCE_IMAGE_INVALID", "只支持有效的 JPEG、PNG、TIFF 或 GIF 图片。",
                    status_code=422, field=field, next_action="replace_reference_image",
                    details={"filename": filename},
                )
            digest = hashlib.sha256(upload.content).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            prepared.append({
                "filename": filename,
                "content": upload.content,
                "role": upload.role,
                "media_type": media_type,
                "extension": extension,
                "width": int(width),
                "height": int(height),
                "sha256": digest,
            })
        if not prepared:
            raise ServiceError(
                "REFERENCE_IMAGE_COUNT", "请选择至少一张不同的参考图。", status_code=422,
                field="reference_images", next_action="select_reference_images",
            )
        return prepared

    @staticmethod
    def _required_text(value: Any, field: str) -> str:
        if not isinstance(value, str):
            raise ServiceError(
                "REQUEST_INVALID", "商品名称必须是文字。", status_code=400,
                field=field, next_action="edit_product_name",
            )
        return value.strip()

    @staticmethod
    def _optional_text(value: Any, field: str) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ServiceError(
                "REQUEST_INVALID", "该字段必须是文字。", status_code=400,
                field=field, next_action="edit_product_information",
            )
        text = value.strip()
        return text or None

    @staticmethod
    def _selling_points(value: Sequence[str] | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise ServiceError(
                "REQUEST_INVALID", "卖点必须作为文字列表提交。", status_code=400,
                field="selling_points", next_action="edit_selling_points",
            )
        points = []
        for index, item in enumerate(value):
            if not isinstance(item, str):
                raise ServiceError(
                    "REQUEST_INVALID", "卖点必须是文字。", status_code=400,
                    field=f"selling_points[{index}]", next_action="edit_selling_points",
                )
            text = item.strip()
            if text and text not in points:
                points.append(text)
        return points

    @staticmethod
    def _amazon_us_ref() -> dict[str, Any]:
        path = contracts.ROOT / "config" / "product-v1" / "platforms" / "amazon-us.json"
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
            contracts.validate_record("platform_profile", profile)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, contracts.ContractError) as exc:
            raise ServiceError(
                "APP_CONFIGURATION_INVALID",
                "Amazon US 平台配置不可读取，商品资料没有保存。",
                status_code=500,
                field="platform",
                recoverable=False,
                next_action="contact_support",
            ) from exc
        return {"profile_id": profile["profile_id"], "version": profile["version"]}

    def _now(self) -> str:
        value = self._clock()
        if not isinstance(value, datetime):
            raise ValueError("clock must return datetime")
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _service_failure(
        self,
        code: str,
        message: str,
        *,
        status_code: int,
        field: str | None = None,
        next_action: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> ServiceResponse:
        error = ServiceError(
            code, message, status_code=status_code, field=field,
            next_action=next_action, details=details,
        )
        return ServiceResponse(
            status_code, {"ok": False, "data": None, "error": error.to_dict()},
        )

    def _execute(
        self,
        directory: str | os.PathLike[str],
        success_status: int,
        operation: Callable[[Path], dict[str, Any]],
    ) -> ServiceResponse:
        try:
            root = self._directory(directory)
            data = operation(root)
            return ServiceResponse(success_status, {"ok": True, "data": data, "error": None})
        except ServiceError as exc:
            return ServiceResponse(
                exc.status_code, {"ok": False, "data": None, "error": exc.to_dict()}
            )
        except WorkspaceStoreError as exc:
            error = self._map_store_error(exc, directory)
            return ServiceResponse(
                error.status_code, {"ok": False, "data": None, "error": error.to_dict()}
            )
        except OSError as exc:
            error = ServiceError(
                "STORAGE_FAILURE", "无法读取或写入工作空间；请检查磁盘和文件夹权限后重试。",
                status_code=500, field="directory", next_action="check_folder_permissions",
                details={"error_type": type(exc).__name__},
            )
            return ServiceResponse(500, {"ok": False, "data": None, "error": error.to_dict()})

    @staticmethod
    def _directory(value: Any) -> Path:
        if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
            raise ServiceError(
                "DIRECTORY_REQUIRED", "请选择一个工作空间文件夹。", status_code=400,
                field="directory", next_action="choose_workspace_folder",
            )
        try:
            return Path(value).expanduser()
        except (TypeError, ValueError, OSError) as exc:
            raise ServiceError(
                "DIRECTORY_INVALID", "这个文件夹路径无效，请重新选择。", status_code=422,
                field="directory", next_action="choose_workspace_folder",
            ) from exc

    @staticmethod
    def _map_store_error(exc: WorkspaceStoreError, directory: Any) -> ServiceError:
        try:
            target = Path(directory).expanduser()
            if isinstance(exc, WorkspaceAlreadyExists) and target.exists() and not target.is_dir():
                return ServiceError(
                    "DIRECTORY_NOT_FOLDER", "所选路径是文件，请选择文件夹。", status_code=422,
                    field="directory", next_action="choose_workspace_folder",
                )
        except (TypeError, ValueError, OSError):
            pass
        if isinstance(exc, WorkspaceAlreadyExists):
            return ServiceError(
                "WORKSPACE_ALREADY_EXISTS", "此文件夹已有内容；请选择空文件夹或打开现有工作空间。",
                status_code=409, field="directory", next_action="choose_empty_folder",
            )
        if isinstance(exc, WorkspaceNotFound):
            return ServiceError(
                "WORKSPACE_NOT_FOUND", "此文件夹中没有可打开的商品工作空间。", status_code=404,
                field="directory", next_action="create_or_choose_workspace",
            )
        if isinstance(exc, WorkspaceCorrupt):
            return ServiceError(
                "WORKSPACE_CORRUPT", "工作空间文件损坏或相互不一致；原文件未被改动。",
                status_code=422, field="directory", recoverable=False,
                next_action="choose_another_folder", details={"reason": str(exc)},
            )
        if isinstance(exc, WorkspaceBusy):
            return ServiceError(
                "WORKSPACE_BUSY", "这个工作空间正在被另一个操作使用，请稍后重试。",
                status_code=409, field="directory", next_action="wait_and_retry",
            )
        if isinstance(exc, WorkspaceConflict):
            return ServiceError(
                "REVISION_CONFLICT", "工作空间已更新；请重新载入后再保存。",
                status_code=409, field="revision", next_action="reload_workspace",
            )
        if isinstance(exc, ImmutableRecordConflict):
            return ServiceError(
                "IMMUTABLE_FILE_CONFLICT", "发现同名但内容不同的历史文件；原文件未被覆盖。",
                status_code=409, field="directory", recoverable=False,
                next_action="choose_another_folder",
            )
        return ServiceError(
            "WORKSPACE_PATH_UNAVAILABLE",
            "无法使用此文件夹；请确认上级文件夹存在且当前用户有读写权限。",
            status_code=422, field="directory", next_action="choose_writable_folder",
            details={"reason": str(exc)},
        )
