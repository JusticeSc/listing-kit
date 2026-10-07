"""Provider-neutral contracts for asynchronous image generation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Sequence


ImageErrorStatus = Literal["FAILED", "UNKNOWN", "REJECTED"]


@dataclass(frozen=True, slots=True)
class ImageReference:
    """Immutable image bytes plus the digest and media type recorded by the workspace."""

    sha256: str
    media_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class ImageTask:
    """Stable view of a provider task; URLs are short-lived provider result locators."""

    provider_id: str
    model_id: str
    task_id: str | None
    status: str
    result_urls: tuple[str, ...] = ()
    error: str | None = None
    request_id: str | None = None


class ImageProviderError(RuntimeError):
    """Safe provider failure; messages must never copy prompts, images, keys, or signed URLs."""

    def __init__(
        self,
        code: str,
        message: str,
        status: ImageErrorStatus = "FAILED",
        request_id: str | None = None,
    ) -> None:
        if status not in {"FAILED", "UNKNOWN", "REJECTED"}:
            raise ValueError("invalid image provider error status")
        self.code = code
        self.message = message
        self.status = status
        self.request_id = request_id
        super().__init__(message)


class ImageProvider(Protocol):
    """The minimal image-generation contract consumed by application services."""

    provider_id: str
    model_id: str

    def submit(
        self,
        prompt: str,
        references: Sequence[ImageReference],
        *,
        model_id: str | None = None,
        size: str = "1344*1344",
        seed: int | None = None,
        idempotency_key: str | None = None,
    ) -> ImageTask: ...

    def query_task(self, task_id: str) -> ImageTask: ...

    def download_result(self, url: str) -> tuple[bytes, str]: ...
