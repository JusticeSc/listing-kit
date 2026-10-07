"""Provider-neutral contracts for semantic model calls."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Mapping, Protocol, Sequence, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class SemanticImage:
    """An immutable source image supplied by the current workspace."""

    sha256: str
    media_type: str
    content: bytes


@dataclass(frozen=True)
class SemanticResponse(Generic[T]):
    """A validated draft plus provider diagnostics kept outside business data."""

    data: T
    provider_id: str
    model_id: str
    request_id: str | None
    schema_mode: str
    usage: Mapping[str, int]


class SemanticProviderError(RuntimeError):
    """A safe, transport-neutral provider failure; never contains raw request data."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status: int | None = None,
        request_id: str | None = None,
        response_summary: str | None = None,
        recoverable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.request_id = request_id
        self.response_summary = response_summary
        self.recoverable = recoverable

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "http_status": self.http_status,
            "request_id": self.request_id,
            "response_summary": self.response_summary,
            "recoverable": self.recoverable,
        }


class SemanticProvider(Protocol):
    def analyze_product(
        self, product_input: Mapping[str, Any], source_assets: Sequence[SemanticImage]
    ) -> SemanticResponse[dict[str, Any]]: ...

    def propose_plan(
        self,
        product_brief: Mapping[str, Any],
        platform_profile: Mapping[str, Any],
        archetypes: Mapping[str, Any],
        user_intent: str | None,
    ) -> SemanticResponse[dict[str, Any]]: ...

    def propose_prompt_blocks(
        self,
        product_brief: Mapping[str, Any],
        shot_spec: Mapping[str, Any],
        style_spec: Mapping[str, Any],
    ) -> SemanticResponse[dict[str, Any]]: ...

    def propose_rework(
        self,
        product_brief: Mapping[str, Any],
        shot_spec: Mapping[str, Any],
        style_spec: Mapping[str, Any],
        current_prompt: Mapping[str, Any],
        direction: Mapping[str, Any],
    ) -> SemanticResponse[dict[str, Any]]: ...
