#!/usr/bin/env python
"""Browser check: a shot with zero candidates can be retried on its own.

Real flow this protects: a whole-set submission can end with a shot that has no
candidate at all (upstream rejection, HTTP 429 limit, timeout). Without a
per-shot entry point the only way forward is clicking "一键生成" again, which
resubmits every shot and pays again for the images that already succeeded.

Run with:
  uv run --no-project --with-requirements requirements.txt --with playwright python tools/verify_product_v1_ui_shot_retry.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright

from src.application_service import ApplicationService, ImageUpload
from src.providers.image import ImageProviderError
from tools.verify_product_v1_ui import (
    FakeImageProvider,
    png_1x1,
    png_image,
    semantic_provider_factory,
    start_server,
    stop_server,
)
from tools.verify_product_v1_plan import require_ok

SESSION_KEY = "amzListingKit.productV1.workspaceDirectory"
EVIDENCE = ROOT / "evals" / "product-demo"


class FlakyImageProvider(FakeImageProvider):
    """Fails the Nth submission outright, like an upstream 429 on submit."""

    def __init__(self, fail_submissions: set[int]) -> None:
        super().__init__()
        self._fail = set(fail_submissions)
        self.submissions: list[str] = []

    def submit(self, prompt, references, **kwargs):
        self.submissions.append(prompt)
        if len(self.submissions) in self._fail:
            raise ImageProviderError(
                "UPSTREAM_RATE_LIMITED",
                "百炼暂时限流（HTTP 429）；这次提交没有被受理。",
                status="FAILED",
            )
        return super().submit(prompt, references, **kwargs)


class CountingImageProvider(FakeImageProvider):
    """Counts every submission, including ones its plan does not cover."""

    def __init__(self) -> None:
        super().__init__()
        self.attempts_seen = 0

    def submit(self, prompt, references, **kwargs):
        self.attempts_seen += 1
        task = super().submit(prompt, references, **kwargs)
        for url in task.result_urls:
            # A retry must return a *new* image; identical bytes are rejected by
            # the product as a duplicate candidate.
            self._bytes[url] = png_image(64, 48, (7 + self.attempts_seen, 77, 177))
        return task


def build_workspace(workspace: Path, failing: set[int]) -> tuple[dict, str, str]:
    """Return the projection, a shot that has a candidate and a shot that has none."""
    provider = FlakyImageProvider(fail_submissions=failing)
    service = ApplicationService(
        semantic_provider_factory=semantic_provider_factory,
        image_provider_factory=lambda: provider,
    )
    created = require_ok(service.create_workspace(workspace), "create workspace")
    saved = require_ok(service.save_intake(
        workspace,
        expected_etag=created["workspace"]["revision"],
        product_name="通勤保温杯",
        description="可重复使用的随行杯，不用于户外露营。",
        selling_points=["单手开盖"],
        user_intent="突出日常通勤，避免户外露营画面。",
        reference_images=[ImageUpload("reference.png", png_1x1(), "primary")],
    ), "save intake")
    draft = require_ok(service.generate_product_brief_draft(
        workspace, expected_etag=saved["workspace"]["revision"],
    ), "brief draft")
    brief = require_ok(service.save_product_brief(
        workspace, expected_etag=draft["workspace_revision"], fields=draft["product_brief"],
    ), "save brief")
    planned = require_ok(service.generate_product_plan(
        workspace, expected_etag=brief["workspace"]["revision"],
    ), "generate plan")
    shots = planned["plan"]["shot_specs"]
    assert len(shots) >= 2, f"expected at least two shots, got {len(shots)}"
    successes = len(shots) - len(failing)
    provider.plan([("SUCCEEDED", f"task-{index}") for index in range(successes)])
    for index in range(successes):
        provider.resolve(f"task-{index}")
    generated = require_ok(service.start_generation_set(
        workspace,
        expected_etag=planned["workspace"]["revision"],
        idempotency_key="ui-shot-retry-fixture",
    ), "start whole set")
    active = {"CREATED", "SUBMITTED", "RUNNING", "UNKNOWN", "RECONCILING"}
    pending = [
        attempt["action_id"]
        for shot in generated["plan"]["shot_specs"]
        for attempt in (shot.get("generation_attempts") or [])
        if attempt["status"] in active
    ]
    if pending:
        generated = require_ok(service.reconcile_generation(
            workspace, action_ids=pending,
        ), "reconcile whole set")
    by_state = {
        shot["id"]: (shot.get("candidates") or [])
        for shot in generated["plan"]["shot_specs"]
    }
    with_candidate = next(shot_id for shot_id, items in by_state.items() if items)
    without_candidate = next(shot_id for shot_id, items in by_state.items() if not items)
    return generated, with_candidate, without_candidate


def shot_state(page, directory: str, shot_id: str) -> dict:
    script = """
    async ([key, directory, shotId]) => {
      const response = await fetch("/api/workspace?directory=" + encodeURIComponent(directory));
      const payload = await response.json();
      const data = payload.data || payload;
      const shots = (data.plan && data.plan.shot_specs) || [];
      const shot = shots.find((item) => item.id === shotId);
      if (!shot) return null;
      return {
        candidates: (shot.candidates || []).map((item) => item.candidate_id),
        attempts: (shot.generation_attempts || []).map((item) => item.status),
      };
    }
    """
    return page.evaluate(script, [SESSION_KEY, directory, shot_id])


def main() -> int:
    stamp = datetime.now().strftime("%Y-%m-%d")
    report: dict[str, object] = {"checked_at": datetime.now().isoformat(timespec="seconds")}
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        recent_index = root / "recent.json"
        projection, with_candidate, without_candidate = build_workspace(
            workspace, failing={2},
        )
        report["shot_with_candidate"] = with_candidate
        report["shot_without_candidate"] = without_candidate

        server_provider = CountingImageProvider()
        server_provider.plan([("SUCCEEDED", "task-retry")])
        server_provider.resolve("task-retry")
        server, thread, base_url = start_server(recent_index, workspace, server_provider)
        try:
            with sync_playwright() as driver:
                browser = driver.chromium.launch()
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.goto(base_url, wait_until="domcontentloaded")
                page.evaluate(
                    "([key, value]) => sessionStorage.setItem(key, value)",
                    [SESSION_KEY, str(workspace)],
                )
                page.reload(wait_until="domcontentloaded")
                page.wait_for_selector("#generation-shots .generation-shot")

                empty_tab = '#generation-shots .generation-shot[data-shot-id="%s"]' % without_candidate
                ok_tab = '#generation-shots .generation-shot[data-shot-id="%s"]' % with_candidate
                page.click(empty_tab)
                page.wait_for_selector("#review-retry:not([hidden])", timeout=15000)
                report["retry_button_visible"] = True
                page.click(ok_tab)
                other_visible = page.locator("#review-retry").is_visible()
                if other_visible:
                    failures.append("已经有候选的图片也显示了单独重跑按钮")
                report["retry_button_hidden_for_generated_shot"] = not other_visible

                before_ok = shot_state(page, str(workspace), with_candidate)
                before_empty = shot_state(page, str(workspace), without_candidate)
                report["before"] = {"ok": before_ok, "empty": before_empty}

                page.click(empty_tab)
                page.click("#review-retry")
                # Either the provider already returned a finished task (the big image
                # appears) or the product shows the reconcile action a real user clicks.
                page.wait_for_selector(
                    "#review-image:not([hidden]), #reconcile-generation:not([hidden])",
                    timeout=30000,
                )
                if page.locator("#review-image").is_hidden():
                    page.click("#reconcile-generation")
                page.wait_for_selector("#review-image:not([hidden])", timeout=30000)

                after_ok = shot_state(page, str(workspace), with_candidate)
                after_empty = shot_state(page, str(workspace), without_candidate)
                report["after"] = {"ok": after_ok, "empty": after_empty}
                report["provider_submissions_after_click"] = server_provider.attempts_seen

                if server_provider.attempts_seen != 1:
                    failures.append(
                        "单独重跑提交了 %d 次图片请求，应当只有 1 次"
                        % server_provider.attempts_seen
                    )
                if not after_empty or len(after_empty["candidates"]) != len(before_empty["candidates"]) + 1:
                    failures.append("被重跑的图片没有新增候选")
                if after_ok != before_ok:
                    failures.append("无关图片的候选或尝试记录发生了变化")
                if not after_empty or len(after_empty["attempts"]) != len(before_empty["attempts"]) + 1:
                    failures.append("被重跑的图片没有新增生成尝试")
                browser.close()
        finally:
            stop_server(server, thread)

    report["failures"] = failures
    report["ok"] = not failures
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / f"ui-shot-retry-{stamp}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": not failures, "failures": failures, "evidence": out.name},
                     ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
