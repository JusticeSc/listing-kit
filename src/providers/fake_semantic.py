"""Explicit-output SemanticProvider fake for tests only; never registered at runtime."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from src.providers.semantic import SemanticImage, SemanticResponse
from src.semantic_drafts import validate_draft


class FakeSemanticProvider:
    """Return only caller-supplied drafts; missing fixtures fail instead of inventing output."""

    provider_id = "test-fake-semantic"
    model_id = "explicit-test-fixture"

    def __init__(self, responses: Mapping[str, Mapping[str, Any]]) -> None:
        self._responses = {name: deepcopy(dict(value)) for name, value in responses.items()}
        self.operations: list[str] = []

    def analyze_product(
        self, product_input: Mapping[str, Any], source_assets: Sequence[SemanticImage]
    ) -> SemanticResponse[dict[str, Any]]:
        del product_input, source_assets
        return self._result("analyze_product")

    def propose_plan(
        self,
        product_brief: Mapping[str, Any],
        platform_profile: Mapping[str, Any],
        archetypes: Mapping[str, Any],
        user_intent: str | None,
    ) -> SemanticResponse[dict[str, Any]]:
        del product_brief, platform_profile, archetypes, user_intent
        return self._result("propose_plan")

    def propose_prompt_blocks(
        self,
        product_brief: Mapping[str, Any],
        shot_spec: Mapping[str, Any],
        style_spec: Mapping[str, Any],
    ) -> SemanticResponse[dict[str, Any]]:
        del product_brief, shot_spec, style_spec
        return self._result("propose_prompt_blocks")

    def propose_rework(
        self,
        product_brief: Mapping[str, Any],
        shot_spec: Mapping[str, Any],
        style_spec: Mapping[str, Any],
        current_prompt: Mapping[str, Any],
        direction: Mapping[str, Any],
    ) -> SemanticResponse[dict[str, Any]]:
        del product_brief, shot_spec, style_spec, current_prompt, direction
        return self._result("propose_rework")

    def _result(self, operation: str) -> SemanticResponse[dict[str, Any]]:
        if operation not in self._responses:
            raise KeyError(f"test fixture has no explicit {operation} response")
        self.operations.append(operation)
        data = validate_draft(operation, deepcopy(self._responses[operation]))
        return SemanticResponse(
            data=data,
            provider_id=self.provider_id,
            model_id=self.model_id,
            request_id=None,
            schema_mode="test-fixture",
            usage={},
        )
