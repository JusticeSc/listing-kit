#!/usr/bin/env python
"""Browser verification of the Product V1 blank-intake vertical slice.

Run with: uv run --no-project --with-requirements requirements.txt --with playwright python tools/verify_product_v1_ui.py
The Windows picker is injected for deterministic testing; HTTP, WorkspaceStore,
browser form submission, recent navigation, and server-instance restart recovery are real.
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
import tempfile
import threading
import zlib
from pathlib import Path
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.product_v1_server import ProductApplication, create_product_server
from src.application_service import ApplicationService
from src.console import enable_utf8
from src.providers.fake_semantic import FakeSemanticProvider
from src.providers.image import ImageTask
from tools.verify_product_v1_plan import responses as product_plan_responses

enable_utf8()


def png_1x1() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(b"\x00\xc8\x30\x20"))
            + chunk(b"IEND", b""))


def png_image(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    """A solid-colour PNG used as deterministic stand-in model output."""
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(rgb) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class FakeImageProvider:
    """Deterministic in-process image provider; UI checks never spend real quota."""

    provider_id = "test-fake-image-provider"
    model_id = "test-fake-image-model"

    def __init__(self) -> None:
        self._planned: list[tuple[str, str | None]] = []
        self._query_results: dict[str, tuple[str, str | None]] = {}
        self._bytes: dict[str, bytes] = {}
        self.submit_calls: list[dict] = []
        self.query_calls: list[str] = []

    def plan(self, submissions) -> None:
        self._planned = list(submissions)

    def resolve(self, task_id: str, *, status: str = "SUCCEEDED") -> None:
        url = f"fake://ui-result/{task_id}"
        self._bytes.setdefault(url, png_image(64, 48, (200, 120, 60)))
        self._query_results[task_id] = (status, url)

    def submit(self, prompt, references, *, model_id=None, size="1344*1344",
               seed=None, idempotency_key=None):
        del seed
        if not self._planned:
            raise AssertionError("unexpected image-provider submission")
        status, task_id = self._planned.pop(0)
        index = len(self.submit_calls) + 1
        self.submit_calls.append({"prompt": prompt, "references": list(references),
                                  "idempotency_key": idempotency_key, "task_id": task_id, "size": size})
        urls: tuple[str, ...] = ()
        if status.upper() == "SUCCEEDED" and task_id:
            url = f"fake://ui-result/{task_id}"
            self._bytes[url] = png_image(64, 48, (20 + index * 7, 90, 150))
            urls = (url,)
        return ImageTask(self.provider_id, self.model_id, task_id, status, result_urls=urls)

    def query_task(self, task_id: str) -> ImageTask:
        self.query_calls.append(task_id)
        if task_id not in self._query_results:
            raise AssertionError(f"unexpected image-provider query {task_id!r}")
        status, url = self._query_results[task_id]
        return ImageTask(self.provider_id, self.model_id, task_id, status, result_urls=(url,))

    def download_result(self, url: str) -> tuple[bytes, str]:
        if url not in self._bytes:
            raise AssertionError(f"unexpected image result download {url!r}")
        return self._bytes[url], "image/png"


def semantic_provider_factory() -> FakeSemanticProvider:
    fixture = product_plan_responses()
    fixture["analyze_product"] = {
        "category": {"label": "保温随行杯", "confidence": 0.93, "source": "user_input"},
        "facts": [
            {"key": "product_name", "value": "错误的模型名称", "state": "confirmed",
             "source": "user_input", "confidence": 0.99, "source_refs": ["description"]},
            {"key": "材质", "value": "双层不锈钢结构", "state": "confirmed",
             "source": "user_input", "confidence": 0.82, "source_refs": ["description"]},
            {"key": "使用场景", "value": "适合户外露营", "state": "confirmed",
             "source": "user_input", "confidence": 0.74, "source_refs": ["description"]},
            {"key": "防漏能力", "value": "100% 不漏水", "state": "confirmed",
             "source": "user_input", "confidence": 0.81, "source_refs": ["description"]},
            {"key": "保冷时长", "value": "保冷 24 小时", "state": "confirmed",
             "source": "model_inference", "confidence": 0.69, "source_refs": ["description"]},
            {"key": "容量", "value": "1.2 L", "state": "confirmed",
             "source": "reference_image", "confidence": 0.77, "source_refs": ["reference"]},
            {"key": "结构", "value": "可调节灯头", "state": "confirmed",
             "source": "reference_image", "confidence": 0.78, "source_refs": ["reference"]},
        ],
        "must_preserve": ["灯头和底座的连接关系"],
        "may_change": ["背景与布光"],
        "unknowns": ["实际材质需确认"],
    }
    fixture["propose_prompt_blocks"] = {
        "blocks": [
            {"id": "style", "kind": "style_lock",
             "text": "延续清爽、可信的通勤商品摄影风格，采用柔和侧光与克制配色。",
             "source_refs": ["plan.style_lock"]},
            {"id": "task", "kind": "shot_task",
             "text": "清楚呈现用户确认的卖点；本图的画面任务保持简洁。",
             "source_refs": ["shot_spec.purpose"]},
            {"id": "negative", "kind": "negative",
             "text": "不要改变商品真实颜色、轮廓和结构；不要加入未确认的材质、性能或认证。",
             "source_refs": ["shot_spec.preserve"]},
        ],
    }
    return FakeSemanticProvider(fixture)


def start_server(recent_path: Path, workspace_path: Path, image_provider=None):
    service = ApplicationService(
        semantic_provider_factory=semantic_provider_factory,
        image_provider_factory=(lambda: image_provider) if image_provider is not None else None,
    )
    app = ProductApplication(
        service=service,
        recent_index_path=recent_path,
        folder_picker=lambda _purpose: str(workspace_path),
    )
    server = create_product_server("127.0.0.1", 0, application=app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    return server, thread, url


def stop_server(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def main() -> int:
    try:
        from playwright.sync_api import expect, sync_playwright
    except ModuleNotFoundError:
        print("缺少 Playwright：请按脚本用法安装临时浏览器依赖。")
        return 2

    result: dict[str, object] = {}
    failures: list[str] = []
    image = png_1x1()
    expected_sha = hashlib.sha256(image).hexdigest()

    with tempfile.TemporaryDirectory(prefix="amz-product-v1-ui-") as raw_root:
        root = Path(raw_root)
        workspace = root / "first-product"
        recent_index = root / "recent-workspaces.json"
        image_provider = FakeImageProvider()
        server, thread, base_url = start_server(recent_index, workspace, image_provider)
        browser = context = None
        external_requests: list[str] = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                page = context.new_page()

                def watch_requests(request, origin=base_url):
                    host = urlsplit(request.url).netloc
                    if host and host != urlsplit(origin).netloc:
                        external_requests.append(request.url)

                page.on("request", watch_requests)
                page.goto(base_url + "/", wait_until="networkidle")
                page.wait_for_selector("#home-screen:not([hidden])")
                result["blank_home"] = (
                    page.locator("#intake-screen").is_hidden()
                    and page.locator("#recent-list .recent-open").count() == 0
                    and page.locator("#home-screen").get_by_role("button").count() == 2
                )
                if not result["blank_home"]:
                    failures.append("首页不是空白的新建/打开/最近使用入口")

                tab_ids = []
                for _ in range(5):
                    page.keyboard.press("Tab")
                    tab_ids.append(page.evaluate("document.activeElement.id"))
                result["home_keyboard_focus"] = tab_ids
                if tab_ids != [
                    "brand-home",
                    "top-open-workspace",
                    "top-create-workspace",
                    "create-workspace",
                    "open-workspace",
                ]:
                    failures.append("首页创建/打开按钮的 Tab 顺序不正确")

                viewports = []
                for width in (1280, 390):
                    page.set_viewport_size({"width": width, "height": 900})
                    measured = page.evaluate("""() => ({
                      width: window.innerWidth,
                      client: document.documentElement.clientWidth,
                      scroll: document.documentElement.scrollWidth
                    })""")
                    viewports.append(measured)
                    if measured["scroll"] > measured["client"] + 1:
                        failures.append(f"{width}px 首页有横向溢出：{measured}")
                result["home_viewports"] = viewports

                page.set_viewport_size({"width": 1280, "height": 900})
                page.get_by_role("button", name="新建商品套图").click()
                page.wait_for_selector("#intake-screen:not([hidden])")
                result["focus_after_create"] = page.evaluate("document.activeElement.id")
                if result["focus_after_create"] != "reference-images":
                    failures.append("创建工作空间后焦点未落到第一项必填的商品参考图")
                form_tab_order = []
                for _ in range(3):
                    page.keyboard.press("Tab")
                    form_tab_order.append(page.evaluate("document.activeElement.id"))
                result["form_keyboard_focus"] = form_tab_order
                if form_tab_order != ["product-name", "product-description", "selling-points"]:
                    failures.append("商品资料字段不能按逻辑顺序通过键盘访问")
                page.locator("#product-name").focus()

                page.set_viewport_size({"width": 390, "height": 900})
                intake_mobile = page.evaluate("""() => ({
                  width: window.innerWidth,
                  client: document.documentElement.clientWidth,
                  scroll: document.documentElement.scrollWidth
                })""")
                result["intake_390px"] = intake_mobile
                if intake_mobile["scroll"] > intake_mobile["client"] + 1:
                    failures.append(f"390px 资料页有横向溢出：{intake_mobile}")
                page.set_viewport_size({"width": 1280, "height": 900})

                page.locator("#product-name").fill("测试商品-橙色随行杯")
                page.locator("#product-description").fill("双层不锈钢结构；不适合户外露营，适合日常通勤使用。")
                page.locator("#selling-points").fill("双层结构\n防滑杯底")
                page.locator("#user-intent").fill("突出便携，不出现户外场景。")
                page.locator("#reference-images").set_input_files({
                    "name": "reference.png", "mimeType": "image/png", "buffer": image,
                })
                page.get_by_role("button", name="保存商品资料").click()
                expect(page.locator("#save-state")).to_contain_text("已保存到此工作空间")
                saved_points = page.locator("#selling-points").input_value()
                result["selling_points_after_save"] = saved_points
                if saved_points != "双层结构\n防滑杯底":
                    failures.append("保存响应未将卖点对象投影回可编辑文字")
                src = page.locator("#saved-images img").first.get_attribute("src")
                image_response = page.request.get(base_url + src)
                observed_sha = hashlib.sha256(image_response.body()).hexdigest()
                result["reference_sha256"] = observed_sha
                if observed_sha != expected_sha:
                    failures.append("保存后参考图的原始字节 hash 不一致")

                brief_revision = page.locator("#workspace-revision").input_value()
                workspace_url = base_url + "/api/workspace?directory=" + quote(str(workspace), safe="")
                before_brief = page.request.get(workspace_url).json()["data"]
                page.get_by_role("button", name="生成商品理解", exact=True).click()
                expect(page.locator("#product-brief-form")).to_be_visible()
                expect(page.locator("#brief-status")).to_contain_text("草案已生成")
                expect(page.locator("#brief-provenance")).to_contain_text("尚未保存")
                result["brief_draft"] = {
                    "category": page.locator("#brief-category").input_value(),
                    "category_source": page.locator("#brief-category-origin").inner_text(),
                    "model_claim_matching_description": {
                        "value": page.locator("#brief-facts .brief-fact").filter(has_text="使用场景")
                        .locator("[data-fact-value]").input_value(),
                        "state": page.locator("#brief-facts .brief-fact").filter(has_text="使用场景")
                        .locator("[data-fact-state]").input_value(),
                        "source": page.locator("#brief-facts .brief-fact").filter(has_text="使用场景")
                        .locator("[data-fact-source]").inner_text(),
                    },
                }
                unsupported_claims = []
                for fact_key in ("材质", "防漏能力", "保冷时长", "容量"):
                    fact = page.locator("#brief-facts .brief-fact").filter(has_text=fact_key)
                    unsupported_claims.append({
                        "key": fact_key,
                        "value": fact.locator("[data-fact-value]").input_value(),
                        "state": fact.locator("[data-fact-state]").input_value(),
                        "source": fact.locator("[data-fact-source]").inner_text(),
                    })
                result["model_claims"] = unsupported_claims
                after_draft = page.request.get(workspace_url).json()["data"]
                result["draft_is_unpersisted"] = (
                    after_draft["product_brief"] is None
                    and after_draft["workspace"]["revision"] == brief_revision
                    and before_brief["workspace"]["revision"] == brief_revision
                )
                if not result["draft_is_unpersisted"]:
                    failures.append("模型草案在用户保存前改变了工作空间")
                if result["brief_draft"]["category_source"] != "来源：模型推断":
                    failures.append("模型建议的类别被误标为用户已确认")
                if result["brief_draft"]["model_claim_matching_description"] != {
                    "value": "适合户外露营", "state": "inferred", "source": "来源：模型推断",
                }:
                    failures.append("模型提供的 user_input 来源标签因文字匹配而被错误确认为事实")
                model_sources = {"来源：模型推断", "来源：模型参考图判断"}
                if any(item["state"] != "inferred" or item["source"] not in model_sources
                       for item in unsupported_claims):
                    failures.append("模型推断的材质、功能或尺寸被提升为已确认商品事实")
                name_group = page.locator("#brief-facts .brief-fact").first
                if name_group.locator("[data-fact-value]").input_value() != "测试商品-橙色随行杯":
                    failures.append("模型输出覆盖了系统从商品资料直接读取的商品名称")

                page.get_by_role("button", name="保存商品理解", exact=True).click()
                expect(page.locator("#brief-status")).to_contain_text("保存为版本 v1")
                brief_v1 = json.loads((workspace / "briefs" / "brief-v001.json").read_text(encoding="utf-8"))
                material = page.locator("#brief-facts .brief-fact").filter(has_text="材质")
                material.locator("[data-fact-value]").fill("双层不锈钢结构（用户补充确认）")
                material.locator("[data-fact-state]").select_option("confirmed")
                if material.locator("[data-fact-source]").inner_text() != "来源：你手动修改":
                    failures.append("用户修改事实后，来源没有更新为手动修改")
                page.get_by_role("button", name="保存为新版本", exact=True).click()
                expect(page.locator("#brief-status")).to_contain_text("保存为版本 v2")
                brief_v2 = json.loads((workspace / "briefs" / "brief-v002.json").read_text(encoding="utf-8"))
                v1_material = next(item for item in brief_v1["facts"] if item["key"] == "材质")
                v2_material = next(item for item in brief_v2["facts"] if item["key"] == "材质")
                brief_versions_ok = (
                    brief_v1["version"] == 1 and brief_v2["version"] == 2
                    and brief_v1["content_hash"] != brief_v2["content_hash"]
                    and v1_material["state"] == "inferred"
                    and v1_material["source"] == "model_inference"
                    and v2_material["state"] == "confirmed"
                    and v2_material["source"] == "user_override"
                    and v2_material["value"] == "双层不锈钢结构（用户补充确认）"
                )
                result["brief_versions"] = {
                    "v1_hash": brief_v1["content_hash"],
                    "v2_hash": brief_v2["content_hash"],
                    "v1_material": v1_material,
                    "v2_material": v2_material,
                    "immutable_history_and_confirmation": brief_versions_ok,
                }
                if not brief_versions_ok:
                    failures.append("纠正没有创建保留旧版本且 hash 不同的新 Brief 版本")
                result["selling_points_unchanged"] = [item["text"] for item in after_draft["intake"]["selling_points"]]
                if result["selling_points_unchanged"] != ["双层结构", "防滑杯底"]:
                    failures.append("模型推断混入了已确认卖点")

                page.get_by_role("button", name="生成套图方案", exact=True).click()
                expect(page.locator("#plan-workspace")).to_be_visible()
                expect(page.locator("#plan-status")).to_contain_text("套图方案已生成")
                plan_data = page.request.get(workspace_url).json()["data"]
                plan = plan_data["plan"]
                expect(page.locator("#plan-shots .plan-shot")).to_have_count(len(plan["shot_specs"]))
                result["plan_workspace"] = {
                    "version": plan["version"],
                    "shot_titles": [item["title"] for item in plan["shot_specs"]],
                    "visible_cards": page.locator("#plan-shots .plan-shot").count(),
                    "product_facts_rendered": page.locator("#plan-shots .fact-chip").count(),
                }
                if plan["version"] != 1 or len(plan["shot_specs"]) < 3:
                    failures.append("动态套图方案未从已保存商品理解生成并投影到前端")
                feature_spec = next(
                    (item for item in plan["shot_specs"]
                     if "selling_point_1" in item["supporting_fact_keys"]),
                    None,
                )
                if feature_spec is None:
                    failures.append("方案卡片缺少模型生成的卖点任务")
                    raise RuntimeError("方案数据中没有绑定第一卖点的图片任务")
                feature_card = page.locator(
                    f'#plan-shots .plan-shot[data-shot-id="{feature_spec["id"]}"]'
                )
                expect(feature_card).to_have_count(1)
                feature_title = feature_card.locator("h3").inner_text()
                feature_card.get_by_role(
                    "button", name=f"生成并查看“{feature_title}”的完整提示词",
                ).click()
                expect(page.locator("#prompt-dialog")).to_be_visible()
                expect(page.locator("#prompt-status")).to_contain_text("提示词已就绪")
                compiled_text = page.locator("#prompt-full-text").input_value()
                prompt_shot_id = page.locator("#prompt-shot-id").input_value()
                prompt_shot = next(item for item in plan_data["plan"]["shot_specs"] if item["id"] == prompt_shot_id)
                prompt_data = page.request.get(workspace_url).json()["data"]
                prompt_shot = next(item for item in prompt_data["plan"]["shot_specs"] if item["id"] == prompt_shot_id)
                result["prompt_editor"] = {
                    "compiled_text_matches_workspace": compiled_text == prompt_shot["latest_prompt"]["full_text"],
                    "initial_version": prompt_shot["latest_prompt"]["version"],
                    "traceable_blocks": page.locator("#prompt-blocks .prompt-block-row").count(),
                }
                if compiled_text != prompt_shot["latest_prompt"]["full_text"]:
                    failures.append("前端提示词文字与服务返回并持久化的完整文本不一致")
                if "双层结构" not in compiled_text or "保冷 24 小时" in compiled_text:
                    failures.append("前端提示词没有保留已确认卖点，或带入模型推断的保冷时长")
                page.get_by_text("查看提示词组成与来源", exact=True).click()
                expect(page.locator("#prompt-blocks .prompt-block-row")).to_have_count(5)

                edited_text = compiled_text + "\n\n画面方向：增加留白，突出商品主体。"
                page.locator("#prompt-full-text").fill(edited_text)
                expect(page.get_by_role("button", name="保存修改")).to_be_enabled()
                page.get_by_role("button", name="保存修改").click()
                expect(page.locator("#prompt-status")).to_contain_text("提示词已保存为 v2")
                saved_prompt_data = page.request.get(workspace_url).json()["data"]
                saved_prompt_shot = next(
                    item for item in saved_prompt_data["plan"]["shot_specs"] if item["id"] == prompt_shot_id
                )
                result["prompt_editor"].update({
                    "saved_version": saved_prompt_shot["latest_prompt"]["version"],
                    "manual_text_round_trip": saved_prompt_shot["latest_prompt"]["full_text"] == edited_text,
                })
                if saved_prompt_shot["latest_prompt"]["version"] != 2:
                    failures.append("前端编辑提示词没有形成新版本")
                if saved_prompt_shot["latest_prompt"]["full_text"] != edited_text:
                    failures.append("前端编辑后的完整提示词未从服务回显")
                page.get_by_role("button", name="关闭提示词").click()
                expect(page.locator("#prompt-dialog")).not_to_be_visible()

                current_plan = page.request.get(workspace_url).json()["data"]["plan"]
                current_shots = current_plan["shot_specs"]
                hero_spec = next(item for item in current_shots if item["archetype_id"] == "hero")
                hero_card = page.locator(
                    f'#plan-shots .plan-shot[data-shot-id="{hero_spec["id"]}"]'
                )
                expect(hero_card.locator('button[data-action="remove"]')).to_have_count(0)
                expect(hero_card.locator('button[data-action="move-up"]')).to_be_disabled()

                movable_index = next((
                    index for index in range(1, len(current_shots) - 1)
                    if not current_shots[index]["required"]
                    and not any(
                        current_shots[index]["id"] in other.get("dependencies", [])
                        for other in current_shots
                    )
                    and current_shots[index + 1]["id"]
                    not in current_shots[index].get("dependencies", [])
                    and current_shots[index]["id"]
                    not in current_shots[index + 1].get("dependencies", [])
                ), None)
                if movable_index is None:
                    failures.append("方案验收数据没有可安全重排并移除的可选图片")
                else:
                    moving_spec = current_shots[movable_index]
                    original_order = [item["id"] for item in current_shots]
                    expected_order = list(original_order)
                    expected_order[movable_index], expected_order[movable_index + 1] = (
                        expected_order[movable_index + 1], expected_order[movable_index]
                    )
                    moving_card = page.locator(
                        f'#plan-shots .plan-shot[data-shot-id="{moving_spec["id"]}"]'
                    )
                    moving_card.locator('button[data-action="move-down"]').click()
                    reordered_ids = page.locator("#plan-shots .plan-shot").evaluate_all(
                        "(cards) => cards.map((card) => card.dataset.shotId)"
                    )
                    if reordered_ids != expected_order:
                        failures.append("方案卡片的上移/下移没有按用户指定顺序更新")

                    feature_card = page.locator(
                        f'#plan-shots .plan-shot[data-shot-id="{feature_spec["id"]}"]'
                    )
                    feature_card.locator("details > summary").click()
                    edited_purpose = "清楚呈现已确认的双层结构卖点，突出商品主体。"
                    feature_card.locator('[data-shot-field="purpose"]').fill(edited_purpose)
                    moving_card = page.locator(
                        f'#plan-shots .plan-shot[data-shot-id="{moving_spec["id"]}"]'
                    )
                    moving_card.locator('button[data-action="remove"]').click()
                    expect(page.get_by_role("button", name="保存方案调整")).to_be_enabled()
                    page.get_by_role("button", name="保存方案调整").click()
                    expect(page.locator("#plan-status")).to_contain_text("方案调整已保存为 v2")

                    saved_plan = page.request.get(workspace_url).json()["data"]["plan"]
                    saved_shots = saved_plan["shot_specs"]
                    saved_ids = [item["id"] for item in saved_shots]
                    expected_ids = [item for item in expected_order if item != moving_spec["id"]]
                    saved_feature = next(item for item in saved_shots if item["id"] == feature_spec["id"])
                    result["plan_edit"] = {
                        "version": saved_plan["version"],
                        "shot_ids": saved_ids,
                        "shot_titles": [item["title"] for item in saved_shots],
                        "edited_purpose": saved_feature["purpose"],
                        "all_current_prompts_invalidated": all(
                            item["latest_prompt"] is None for item in saved_shots
                        ),
                    }
                    if saved_plan["version"] != 2 or saved_ids != expected_ids:
                        failures.append("前端调整没有保存成正确的方案 v2 顺序与图片集合")
                    if saved_feature["purpose"] != edited_purpose:
                        failures.append("前端编辑的单张图片目的没有保存")
                    if not result["plan_edit"]["all_current_prompts_invalidated"]:
                        failures.append("方案修改后，新 ShotSpec 仍错误沿用了旧 Prompt")

                # One-click whole-set generation against the injected image provider:
                # the browser must start from the saved plan, show per-image state and
                # render the stitched candidate bytes served by the workspace route.
                generation_plan = page.request.get(workspace_url).json()["data"]["plan"]
                shot_count = len(generation_plan["shot_specs"])
                image_provider.plan([
                    ("SUCCEEDED", f"ui-task-{index}") for index in range(1, shot_count + 1)
                ])
                page.get_by_role("button", name="采用方案并一键生成").click()
                expect(page.locator("#generation-status")).to_contain_text("生成任务已记录")
                generation_cards = page.locator("#generation-shots .generation-shot")
                expect(generation_cards).to_have_count(shot_count)
                expect(generation_cards.locator(".generation-state")).to_have_text(["已完成"] * shot_count)
                candidate_images = page.locator("#generation-shots .generation-candidate img")
                expect(candidate_images).to_have_count(shot_count)
                first_candidate = candidate_images.first
                first_candidate.wait_for(state="visible")
                rendered = first_candidate.evaluate(
                    "(img) => ({width: img.naturalWidth, height: img.naturalHeight, src: img.src})"
                )
                served_sha = hashlib.sha256(page.request.get(rendered["src"]).body()).hexdigest()
                result["generation_first_set"] = {
                    "shots": shot_count,
                    "submissions": len(image_provider.submit_calls),
                    "candidate_rendered": rendered["width"] > 0 and rendered["height"] > 0,
                    "candidate_sha_matches_url": served_sha in rendered["src"],
                }
                if not result["generation_first_set"]["candidate_rendered"]:
                    failures.append("一键生成后浏览器没有成功加载候选图")
                if not result["generation_first_set"]["candidate_sha_matches_url"]:
                    failures.append("候选图字节与服务端记录的 hash 不一致")

                # Second set: the first image lands in UNKNOWN; the page must offer
                # reconciliation instead of allowing another paid submission.
                image_provider.plan(
                    [("UNKNOWN", "ui-retry-1")]
                    + [("SUCCEEDED", f"ui-retry-{index}") for index in range(2, shot_count + 1)]
                )
                page.once("dialog", lambda dialog: dialog.accept())
                page.get_by_role("button", name="再次生成整套").click()
                expect(page.locator("#generation-hint")).to_contain_text("核对")
                start_button = page.get_by_role("button", name="等待本轮结果")
                if start_button.is_enabled():
                    failures.append("存在未确认的生成任务时仍可重复提交")
                reconcile_button = page.get_by_role("button", name="核对当前生成状态")
                expect(reconcile_button).to_be_visible()
                before_reconcile = len(image_provider.submit_calls)
                image_provider.resolve("ui-retry-1", status="SUCCEEDED")
                reconcile_button.click()
                expect(page.locator("#generation-status")).to_contain_text("状态已更新")
                if len(image_provider.submit_calls) != before_reconcile:
                    failures.append("核对状态时重新提交了图片模型任务")
                expect(generation_cards.locator(".generation-state")).to_have_text(["已完成"] * shot_count)
                result["generation_reconcile"] = {
                    "queries": list(image_provider.query_calls),
                    "submissions_after_reconcile": len(image_provider.submit_calls),
                }
                generated_shots = page.request.get(workspace_url).json()["data"]["plan"]["shot_specs"]
                if any(not shot.get("candidates") for shot in generated_shots):
                    failures.append("整套生成后仍有图片没有候选")

                page.set_viewport_size({"width": 390, "height": 900})
                brief_mobile = page.evaluate("""() => ({
                  width: window.innerWidth,
                  client: document.documentElement.clientWidth,
                  scroll: document.documentElement.scrollWidth
                })""")
                result["brief_390px"] = brief_mobile
                if brief_mobile["scroll"] > brief_mobile["client"] + 1:
                    failures.append(f"390px 商品理解页有横向溢出：{brief_mobile}")
                plan_mobile = page.evaluate("""() => ({
                  width: window.innerWidth,
                  client: document.documentElement.clientWidth,
                  scroll: document.documentElement.scrollWidth
                })""")
                result["plan_390px"] = plan_mobile
                if plan_mobile["scroll"] > plan_mobile["client"] + 1:
                    failures.append(f"390px 方案工作区有横向溢出：{plan_mobile}")
                page.set_viewport_size({"width": 1280, "height": 900})

                page.get_by_role("button", name="所有工作空间").click()
                page.wait_for_selector("#home-screen:not([hidden])")
                result["recent_items_after_save"] = page.locator("#recent-list .recent-open").count()
                if result["recent_items_after_save"] != 1:
                    failures.append("保存后最近使用列表未出现该工作空间")

                context.close()
                context = None
                stop_server(server, thread)
                server, thread, base_url = start_server(recent_index, workspace, image_provider)

                # New browser context and server instance: no page state or service
                # memory survives, so the next view must come from disk.
                context = browser.new_context(viewport={"width": 1280, "height": 900})
                page = context.new_page()
                page.on("request", lambda request: watch_requests(request, base_url))
                page.goto(base_url + "/", wait_until="networkidle")
                page.locator("#recent-list .recent-open").first.click()
                page.wait_for_selector("#intake-screen:not([hidden])")
                restored = {
                    "product_name": page.locator("#product-name").input_value(),
                    "description": page.locator("#product-description").input_value(),
                    "selling_points": page.locator("#selling-points").input_value(),
                    "user_intent": page.locator("#user-intent").input_value(),
                    "reference_images": page.locator("#saved-images img").count(),
                    "status": page.locator("#workspace-status").inner_text(),
                }
                result["restored_after_restart"] = restored
                expected = {
                    "product_name": "测试商品-橙色随行杯",
                    "description": "双层不锈钢结构；不适合户外露营，适合日常通勤使用。",
                    "selling_points": "双层结构\n防滑杯底",
                    "user_intent": "突出便携，不出现户外场景。",
                    "reference_images": 1,
                    "status": "资料已保存",
                }
                if restored != expected:
                    failures.append("重启后资料、参考图未从工作空间恢复")

                restored_material = page.locator("#brief-facts .brief-fact").filter(has_text="材质")
                result["restored_brief_after_restart"] = {
                    "version": page.locator("#brief-provenance").inner_text(),
                    "material": restored_material.locator("[data-fact-value]").input_value(),
                    "state": restored_material.locator("[data-fact-state]").input_value(),
                    "source": restored_material.locator("[data-fact-source]").inner_text(),
                }
                if result["restored_brief_after_restart"] != {
                    "version": "已保存版本 v2",
                    "material": "双层不锈钢结构（用户补充确认）",
                    "state": "confirmed",
                    "source": "来源：你手动修改",
                }:
                    failures.append("重启后 Brief 最新版本、用户纠正内容或来源/确认状态未恢复")

                restored_plan = page.request.get(
                    base_url + "/api/workspace?directory=" + quote(str(workspace), safe="")
                ).json()["data"]["plan"]
                result["plan_after_restart"] = {
                    "version": restored_plan["version"],
                    "shot_ids": [item["id"] for item in restored_plan["shot_specs"]],
                    "shot_titles": [item["title"] for item in restored_plan["shot_specs"]],
                }
                expected_plan_edit = result.get("plan_edit")
                if expected_plan_edit and result["plan_after_restart"] != {
                    "version": expected_plan_edit["version"],
                    "shot_ids": expected_plan_edit["shot_ids"],
                    "shot_titles": expected_plan_edit["shot_titles"],
                }:
                    failures.append("重启后方案调整版本、图片顺序或标题没有从工作空间恢复")

                restored_shots = page.request.get(
                    base_url + "/api/workspace?directory=" + quote(str(workspace), safe="")
                ).json()["data"]["plan"]["shot_specs"]
                result["generation_after_restart"] = {
                    "attempts": [len(shot.get("generation_attempts") or []) for shot in restored_shots],
                    "candidates": [len(shot.get("candidates") or []) for shot in restored_shots],
                }
                if any(item < 2 for item in result["generation_after_restart"]["attempts"]):
                    failures.append("重启后生成任务记录没有从工作空间恢复")
                if any(item < 1 for item in result["generation_after_restart"]["candidates"]):
                    failures.append("重启后候选图没有从工作空间恢复")

                # A damaged recent workspace must fail visibly without moving the
                # user off the home screen or silently replacing the source files.
                page.get_by_role("button", name="所有工作空间").click()
                page.wait_for_selector("#home-screen:not([hidden])")
                (workspace / "workspace.json").write_text("{not valid json", encoding="utf-8")
                page.locator("#recent-list .recent-open").first.click()
                expect(page.locator("#app-notice")).to_be_visible()
                expect(page.locator("#app-notice")).to_contain_text("工作空间文件损坏")
                result["damaged_workspace_feedback"] = {
                    "message": page.locator("#app-notice").inner_text(),
                    "remains_on_home": page.locator("#home-screen").is_visible(),
                    "source_still_damaged": (workspace / "workspace.json").read_text(encoding="utf-8")
                    == "{not valid json",
                }
                if not result["damaged_workspace_feedback"]["remains_on_home"]:
                    failures.append("打开损坏工作空间后没有留在可恢复的首页")
                if not result["damaged_workspace_feedback"]["source_still_damaged"]:
                    failures.append("打开损坏工作空间时改写了原始文件")

                if external_requests:
                    failures.append("发现外部网络请求：" + ", ".join(external_requests))
                result["external_requests"] = external_requests
                print(json.dumps(result, ensure_ascii=False, indent=2))
        finally:
            stop_server(server, thread)

    if failures:
        for failure in failures:
            print("FAIL: " + failure)
        return 1
    print("Product V1 UI 纵向切片通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
