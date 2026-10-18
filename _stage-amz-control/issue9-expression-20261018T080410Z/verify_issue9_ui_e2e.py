#!/usr/bin/env python
"""Issue #9 普通用户人路 UI E2E：真实页面走通 + 逐项断言 + 证据落盘。

真实人路（headless Chromium + Playwright，产品正式页面）：
  普通输入（上传真实商品图 primary 资产）→ 理解（手工保存事实）
  → 方案（用新控件做普通选择）→ 生成（Prompt 预览、提交给替身 provider）

断言（不得放宽）：
  A. 未决定时风格区两组 radio 均不预选；保存后 style_spec 无 presentation 键。
  B. 决定「干净展示」+「内容物为空」并保存 → presentation 两键逐字正确。
  C. 信息图：印字选「只印所选文案」→ 文案候选区出现且只勾 1 条 → 版面选「商品在左，
     文字在右」（新语义：selected 必须配能放文字的版面，否则编译门阻断）→ 保存 →
     shot_spec 三键正确、on_image_texts 按「能逐字上图的最小单元」逐条落库
     （text_list 按元素各一条，text_id 形如 t_<slot>_<n>；text 与确认事实元素逐字一致）。
     C0：缺 layout / 错 layout 的新编译门（正式页面点击实证）。
     C3：勾选快照语义——来源事实前进后已保存仍是旧版 + 出现旧版提示 + 编译被拦；
     重新勾选后按新值确认并恢复可提交。
     C4：确认单阻断项「去补足此项」按钮文案正确，点击直达对应决定控件。
     C5：结构化尺寸事实（dimension_list）不出现在候选里；0 候选时提示
     「文字类事实才能上图」。

  C6a：反方向门（正式 UI）：(selected, 左文右) 已保存 → 改成「不印新增文字」并保存
     （保留文字版面）→ 确认单被拦，消息是 $.shot_spec.layout 那条（含「不会有图上文字」
     「只放商品」），且页面可见 #spec-layout-needs-text-<shotId>；再改成「只放商品」
     → 该阻断消失（编译恢复）。
  C6b：来源解绑（正式 UI）：回到 (selected, 左文右) 勾选并保存一条文案
     （signature_features）→ 在「图片任务」里把该事实解绑 → (i) 已保存文案仍可见为
     #spec-text-orphan-<shotId>-signature_features 且内容照旧；(ii) 编译被拦，消息含
     「不在这张图的绑定里」；(iii) 勾掉该行并保存 → shot_spec.on_image_texts 变空
     （读记录）；(iv) 重新绑定 + 勾选 + 保存 → 阻断消失。
  E3. 提交请求图像参数与页面冻结 request_snapshot 逐项相等（size、n 及携带的
     prompt_extend/watermark/output_format/model_id/target；negative_prompt 未被
     请求携带，如实报 absent）。期望值只读记录，不手抄。
  E4. 提交请求 references 按序与冻结记录一致：同长度、按序同 role/media_type，
     base64 解码 sha256 同时等于请求自带 sha256 与记录 sha256，且 primary 位
     独立等于 PRIMARY_SHA256 夹具值。期望值只读记录与资产行，不手抄。
  uv run --locked python _stage-amz-control/issue9-expression-20261018T080410Z/verify_issue9_ui_e2e.py
  uv run --locked python .../verify_issue9_ui_e2e.py --base-url http://127.0.0.1:38169

证据写 _stage-amz-control/issue9-expression-20261018T080410Z/issue9-ui-e2e/：
  result.json（逐项：断言原文+实际值+是否通过）+ 截图 PNG。

诚实边界：只验证提示词编译/请求消费/页面行为；不验证图像像素或模型质量。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import v2_stage_nav as stage_nav  # noqa: E402
import v2_verify_shared as shared  # noqa: E402

STAGE_DIR = ROOT / "_stage-amz-control" / "issue9-expression-20261018T080410Z"
EVIDENCE_DIR = STAGE_DIR / "issue9-ui-e2e"
PROJECT_ZIP = (ROOT / "_stage-amz-control" / "asset-continuation-20261008T054352Z"
               / "data" / "manual-project.zip")
PRIMARY_SHA256 = "c024b7cf2b04d39601a5146664879a5aff8d3fe4cb98b4990bda4c3ae6594461"

PROJECT_NAME = "issue9 普通用户人路"
INTAKE = {
    "name": "透明玻璃蜂蜜罐样例",
    "description": "参考图可见玻璃罐、HONEY 浮雕和蜂窝纹；旧化金属色盖。不声称容量、尺寸或密封性能。",
    "selling_points": "罐身 HONEY 浮雕\n蜂窝纹理\n透明罐身",
}
# 手工确认的事实值：与 manual-project.zip 里已确认版本逐字一致
# （product_name v2 / product_category v2 / signature_features v2 / key_material v2）。
FACTS = {
    "product_name": "透明玻璃蜂蜜罐样例",
    "product_category": "玻璃储物罐",
    "signature_features": "HONEY 浮雕\n蜂窝纹理\n透明罐身",
    "key_material": "透明玻璃罐身，金属色盖",
}
# 结构化尺寸事实（C5 用）：走正式 dimension editor 确认一条测量。
DIMENSION = {
    # axis/unit 必须是域枚举值（height/cm 见 domain/shared.js）。
    "object": "罐身", "axis": "height", "value": "12", "unit": "cm",
    "source_basis": "参考图可见比例",
}
INFO_SHOT = "shot_infographic_benefits"

# F 白名单：目前为空——本轮走查零错误，白名单只在真实出现已知问题时登记并写理由。
CONSOLE_WHITELIST: tuple[str, ...] = ()


DUMP_DOCS = """async () => {
  const db = await new Promise((res, rej) => {
    const r = indexedDB.open('amz-listing-kit-v2');
    r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
  });
  const docs = await new Promise((res, rej) => {
    const r = db.transaction('documents', 'readonly').objectStore('documents').getAll();
    r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
  });
  db.close();
  const pick = (kind, id) => {
    const rows = docs.filter((d) => d.kind === kind && (!id || d.document_id === id));
    rows.sort((a, b) => a.version - b.version);
    return rows.length ? rows[rows.length - 1] : null;
  };
  return {
    style: (() => { const r = pick('style_spec'); return r ? { version: r.version, payload: r.payload } : null; })(),
    shotspec: (() => { const r = pick('shot_spec', '__INFO__'); return r ? { version: r.version, payload: r.payload } : null; })(),
    slots: docs.filter((d) => d.kind === 'fact_slot')
      .map((d) => ({ id: d.document_id, v: d.version, status: d.payload.status, value: d.payload.value })),
  };
}""".replace("__INFO__", INFO_SHOT)

PROMPT_DOCS = """async (shotIds) => {
  const db = await new Promise((res, rej) => {
    const r = indexedDB.open('amz-listing-kit-v2');
    r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
  });
  const docs = await new Promise((res, rej) => {
    const r = db.transaction('documents', 'readonly').objectStore('documents').getAll();
    r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
  });
  db.close();
  const out = {};
  for (const shotId of shotIds) {
    const rows = docs.filter((d) => d.kind === 'prompt_version' && d.document_id === shotId);
    rows.sort((a, b) => a.version - b.version);
    out[shotId] = rows.length ? { version: rows[rows.length - 1].version, record: rows[rows.length - 1].payload } : null;
  }
  return out;
}"""

# D 断言值来源：页面内 import 正式构建产物 /domain/index.js 取常量，不手抄。
# 其中 product_fidelity 状态句是 compilePrompt 内联拼装（无导出常量）：
# 期望值取正式 prompt_version 记录里同一图的 product_fidelity 段落（真实编译产物），
# 再断言页面预览与该段逐字一致——同样不手抄字面量。
DOMAIN_CONSTANTS = """async () => {
  const domain = await import('/domain/index.js');
  return {
    brief: domain.ROLE_VISUAL_BRIEF,
    platform_roles: domain.PLATFORM_PROFILES.amazon_us.on_image_text_roles,
  };
}"""
def latest_confirmed_slot(dump: dict, slot_id: str) -> dict | None:
    """取该槽位版本号最大的 confirmed 行（事实前进后有多条 confirmed 历史）。"""
    rows = [row for row in dump["slots"]
            if row["id"] == slot_id and row["status"] == "confirmed"]
    rows.sort(key=lambda row: row["v"])
    return rows[-1] if rows else None



class Evidence:
    def __init__(self) -> None:
        self.checks: list[dict] = []

    def add(self, check_id: str, statement: str, actual: object, passed: bool) -> None:
        self.checks.append({"id": check_id, "statement": statement,
                            "actual": actual, "passed": bool(passed)})
        print(f"[{'PASS' if passed else 'FAIL'}] {check_id}: {statement}")

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(item["passed"] for item in self.checks)


def extract_primary_asset(temp_root: Path) -> Path:
    """从真实项目包按 sha256 取 primary 资产；写盘后再核对 sha256。"""
    with zipfile.ZipFile(PROJECT_ZIP) as archive:
        raw = archive.read(f"assets/{PRIMARY_SHA256}")
    digest = hashlib.sha256(raw).hexdigest()
    if digest != PRIMARY_SHA256:
        raise AssertionError(f"primary 资产 sha256 不符：{digest}")
    target = temp_root / "primary.jpg"
    target.write_bytes(raw)
    return target


def confirm_manual_facts(page) -> None:
    for slot_id, text in FACTS.items():
        row = page.locator(f'#slot-list .slot-row[data-slot-id="{slot_id}"]')
        row.get_by_role("button", name="填值并确认", exact=True).first.click()
        page.wait_for_timeout(250)
        row.locator('[data-role="value"]').first.fill(text)
        row.get_by_role("button", name="确认", exact=True).first.click()
        page.wait_for_selector(f'#slot-list .slot-row[data-slot-id="{slot_id}"]',
                               state="detached", timeout=10_000)
    # 结构化尺寸事实：走正式 dimension editor（打开自带 1 空行，直接填，不要点“添加测量”）。
    dim_row = page.locator('#slot-list .slot-row[data-slot-id="size_dimensions"]')
    dim_row.get_by_role("button", name="填值并确认", exact=True).first.click()
    page.wait_for_timeout(400)
    dim_fields = dim_row.locator(".dimension-row").first
    dim_fields.locator('[data-dimension-field="object"]').fill(DIMENSION["object"])
    dim_fields.locator('[data-dimension-field="axis"]').select_option(DIMENSION["axis"])
    dim_fields.locator('[data-dimension-field="value"]').fill(DIMENSION["value"])
    dim_fields.locator('[data-dimension-field="unit"]').select_option(DIMENSION["unit"])
    dim_fields.locator('[data-dimension-field="source_basis"]').fill(
        DIMENSION["source_basis"])
    dim_row.get_by_role("button", name="确认", exact=True).first.click()
    page.wait_for_selector('#slot-list .slot-row[data-slot-id="size_dimensions"]',
                           state="detached", timeout=10_000)
    # 其余槽位置未知，保证待处理清零后推进
    for _ in range(10):
        buttons = page.locator("#slot-list .slot-row").get_by_role(
            "button", name="标记未知", exact=True)
        if buttons.count() == 0:
            break
        buttons.first.click()
        page.wait_for_timeout(200)


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue #9 普通用户人路 UI E2E")
    parser.add_argument("--base-url", default="http://127.0.0.1:38169",
                        help="已运行的产品服务地址（测试替身 provider）")
    parser.add_argument("--keep-profile", action="store_true",
                        help="保留浏览器 profile 目录以便事后检查")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    evidence = Evidence()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix="amz-issue9-e2e-"))
    profile = temp_root / "profile"
    reference = extract_primary_asset(temp_root)

    def shot_path(name: str) -> Path:
        return EVIDENCE_DIR / f"{name}.png"

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            str(profile), headless=True, viewport={"width": 1440, "height": 900})
        try:
            page = context.pages[0] if context.pages else context.new_page()
            logs = shared.collect(page)

            # ---- 资料：真实商品图 + 普通输入 ----
            page.goto(base + "/", wait_until="networkidle")
            page.wait_for_selector("#empty-state:not([hidden])", timeout=60_000)
            page.fill("#new-project-name", PROJECT_NAME)
            page.click("#create-project")
            page.wait_for_selector("#project-view:not([hidden])", timeout=15_000)
            page.wait_for_function(
                "() => (document.getElementById('project-view') || {}).dataset.ready === '1'",
                timeout=15_000)
            page.set_input_files("#ref-file", str(reference))
            page.wait_for_selector("#ref-list .ref-row", timeout=15_000)
            uploaded_sha = page.evaluate(shared.HASH_ASSET, {"sha256": PRIMARY_SHA256})
            evidence.add(
                "SETUP-asset",
                "上传的真实商品图按 sha256 落库 primary 资产且字节一致",
                uploaded_sha, uploaded_sha.get("found") is True
                and uploaded_sha.get("sha256") == PRIMARY_SHA256)
            page.fill("#intake-name", INTAKE["name"])
            page.fill("#intake-description", INTAKE["description"])
            page.fill("#intake-selling-points", INTAKE["selling_points"])
            page.click("#manual-facts")
            page.wait_for_selector("#slot-list .slot-row", timeout=30_000)

            # ---- 理解：手工保存事实 ----
            confirm_manual_facts(page)
            dump = page.evaluate(DUMP_DOCS)
            confirmed = {row["id"]: row for row in dump["slots"]
                         if row["status"] == "confirmed"}
            evidence.add(
                "SETUP-facts",
                "5 条事实手工确认落库（含 signature_features 三条卖点原文 + "
                "size_dimensions 一条结构化测量）",
                confirmed,
                confirmed.get("product_name", {}).get("value") == FACTS["product_name"]
                and confirmed.get("product_category", {}).get("value")
                == FACTS["product_category"]
                and confirmed.get("signature_features", {}).get("value")
                == ["HONEY 浮雕", "蜂窝纹理", "透明罐身"]
                and confirmed.get("key_material", {}).get("value")
                == FACTS["key_material"]
                and (confirmed.get("size_dimensions", {}).get("value") or [{}])[0].get("object")
                == DIMENSION["object"]
                and (confirmed.get("size_dimensions", {}).get("value") or [{}])[0].get("axis")
                == DIMENSION["axis"])

            # ---- 方案：推荐 + 新控件普通选择 ----
            page.click("#stage-next-understand")
            page.wait_for_selector('[data-stage-panel="plan"]:not([hidden])',
                                   timeout=15_000)
            page.click("#suite-seed")
            page.wait_for_selector("#shot-list .shot-row", timeout=20_000)
            shots = page.evaluate(shared.SHOT_IDS)
            evidence.add(
                "SETUP-plan",
                "推荐方案生成 5 张图（含主图、卖点信息图与尺寸图）",
                shots,
                shots == ["shot_main_clean", "shot_infographic_benefits",
                          "shot_scene_lifestyle", "shot_detail_material",
                          "shot_size_dimensions"])
            stage_nav.reveal(page, "#specs-editor")
            page.wait_for_selector("#style-presentation", state="visible",
                                   timeout=10_000)

            # A. 未决定：两组 radio 均不预选；保存后 style_spec 无 presentation 键
            radios = page.evaluate(
                "() => [...document.querySelectorAll('#style-presentation input[type=radio]')]"
                ".map((n) => ({id: n.id, checked: n.checked}))")
            evidence.add(
                "A1-radios-unchecked",
                "未决定时风格区两组 radio 均不预选（5 个选项 checked 全为 false）",
                radios,
                len(radios) == 5 and all(not item["checked"] for item in radios))
            info_print_radios = page.evaluate(
                "() => [...document.querySelectorAll("
                f"'#spec-print-{INFO_SHOT} input[type=radio]')]"
                ".map((n) => ({id: n.id, checked: n.checked}))")
            info_layout_radios = page.evaluate(
                "() => [...document.querySelectorAll("
                f"'#spec-layout-{INFO_SHOT} input[type=radio]')]"
                ".map((n) => ({id: n.id, checked: n.checked}))")
            texts_count = page.locator(f"#spec-texts-{INFO_SHOT}").count()
            evidence.add(
                "A2a-print-undecided",
                "未决定时信息图印字不预选，且文案候选区不出现",
                {"print": info_print_radios, "texts_visible": texts_count},
                len(info_print_radios) == 2
                and all(not item["checked"] for item in info_print_radios)
                and texts_count == 0)
            # A2b：新语义下版面是用户决定（缺键=未决定），radio 不预选。
            # 旧缺陷见 defect-layout-preselect.md（已由新语义解决，本项为回归验证）。
            evidence.add(
                "A2b-layout-undecided",
                "未决定时信息图版面三组 radio 均不预选（新语义回归验证）",
                {"layout": info_layout_radios},
                len(info_layout_radios) == 3
                and all(not item["checked"] for item in info_layout_radios))
            page.click("#style-save")
            page.wait_for_timeout(600)
            style_undecided = page.evaluate(DUMP_DOCS)["style"]
            evidence.add(
                "A3-no-presentation-key",
                "未决定保存后 style_spec 无 presentation 键（程序不替用户默认）",
                style_undecided,
                style_undecided is not None
                and "presentation" not in style_undecided["payload"])
            page.locator("#style-presentation").scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            page.screenshot(path=str(shot_path("1-style-undecided")))

            # B. 决定「干净展示」+「内容物为空」并保存
            page.click("#style-appearance_state-clean_display")
            page.wait_for_timeout(250)
            page.click("#style-contents_state-empty")
            page.wait_for_timeout(250)
            page.locator("#style-presentation").scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            page.screenshot(path=str(shot_path("2-style-decided")))
            page.click("#style-save")
            page.wait_for_timeout(800)
            style_decided = page.evaluate(DUMP_DOCS)["style"]
            evidence.add(
                "B-presentation-saved",
                "style_spec.payload.presentation == "
                "{appearance_state: clean_display, contents_state: empty}（逐字）",
                style_decided,
                style_decided is not None
                and style_decided["payload"].get("presentation")
                == {"appearance_state": "clean_display", "contents_state": "empty"})

            # C. 信息图印字/版面决定。新语义：selected 必须配能放文字的版面。
            # 顺序：先断言候选区默认不勾选（C1），再勾选做门测试（C0）与主路（C2）。
            page.click(f"#spec-print-selected-{INFO_SHOT}")
            page.wait_for_selector(f"#spec-texts-{INFO_SHOT}", timeout=10_000)
            candidates = page.evaluate(
                "() => [...document.querySelectorAll("
                f"'#spec-texts-{INFO_SHOT} input[type=checkbox]')]"
                ".map((n) => ({id: n.id, checked: n.checked, disabled: n.disabled,"
                " label: n.parentElement.textContent.trim()}))")
            evidence.add(
                "C1-candidates",
                "印字选「只印所选文案」后候选区出现，1 条候选且默认不勾选",
                candidates,
                len(candidates) == 1
                and candidates[0]["id"]
                == f"#spec-text-{INFO_SHOT}-signature_features".lstrip("#")
                and candidates[0]["checked"] is False
                and candidates[0]["disabled"] is False)
            # C5：结构化尺寸事实不出现在候选里（避免印出非文字值）。
            # 先把 size_dimensions 绑到信息图：候选仍只有 signature 1 条。
            def set_binding(shot_id: str, slot_id: str, want: bool) -> None:
                page.evaluate(
                    """([shotId, slotId, want]) => {
                      const row = document.querySelector(
                        '#shot-list .shot-row[data-shot-id="' + shotId + '"]');
                      const det = row.querySelector('.shot-bindings');
                      if (det && det.tagName === 'DETAILS') det.open = true;
                      const box = row.querySelector(
                        '.shot-bindings input[type=checkbox][value="' + slotId + '"]');
                      box.checked = want;
                      box.dispatchEvent(new Event('change', { bubbles: true }));
                    }""", [shot_id, slot_id, want])

            def save_binding(shot_id: str) -> None:
                zone = page.locator(
                    f'#shot-list .shot-row[data-shot-id="{shot_id}"] .shot-bindings')
                zone.scroll_into_view_if_needed()
                page.wait_for_timeout(300)
                zone.get_by_role("button", name="保存本图事实绑定",
                                 exact=True).click()
                page.wait_for_timeout(800)

            set_binding(INFO_SHOT, "size_dimensions", True)
            save_binding(INFO_SHOT)
            page.locator(f"#spec-texts-{INFO_SHOT}").scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            candidates_dim = page.evaluate(
                "() => [...document.querySelectorAll("
                f"'#spec-texts-{INFO_SHOT} input[type=checkbox]')]"
                ".map((n) => n.id)")
            evidence.add(
                "C5a-dimension-not-candidate",
                "size_dimensions 已确认并绑到信息图，但候选区仍只有 signature 1 条 "
                "（无 #spec-text-<shot>-size_dimensions，避免印出非文字值）",
                {"candidates": candidates_dim,
                 "dim_box": page.locator(
                     f"#spec-text-{INFO_SHOT}-size_dimensions").count(),
                 "suite_error": page.locator("#suite-error").inner_text()
                 if page.locator("#suite-error").count() else None},
                candidates_dim == [f"spec-text-{INFO_SHOT}-signature_features"]
                and page.locator(
                    f"#spec-text-{INFO_SHOT}-size_dimensions").count() == 0)
            # 再解绑 signature（只留尺寸）：0 候选 + 提示「文字类事实才能上图」。
            set_binding(INFO_SHOT, "signature_features", False)
            save_binding(INFO_SHOT)
            page.locator(f"#spec-texts-{INFO_SHOT}").scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            zero_text = page.locator(f"#spec-texts-{INFO_SHOT}").inner_text()
            evidence.add(
                "C5b-zero-candidate-hint",
                "信息图只绑尺寸时：候选为 0 且提示含「文字类事实才能上图」",
                {"region_text": zero_text,
                 "checkboxes": page.locator(
                     f"#spec-texts-{INFO_SHOT} input[type=checkbox]").count()},
                page.locator(
                    f"#spec-texts-{INFO_SHOT} input[type=checkbox]").count() == 0
                and "文字类事实才能上图" in zero_text)
            # 恢复默认绑定（signature 绑回、尺寸解掉），回到 1 条候选再进主路。
            set_binding(INFO_SHOT, "signature_features", True)
            set_binding(INFO_SHOT, "size_dimensions", False)
            save_binding(INFO_SHOT)
            page.locator(f"#spec-texts-{INFO_SHOT}").scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            candidates_restored = page.evaluate(
                "() => [...document.querySelectorAll("
                f"'#spec-texts-{INFO_SHOT} input[type=checkbox]')]"
                ".map((n) => ({id: n.id, checked: n.checked}))")
            evidence.add(
                "C5c-binding-restored",
                "恢复绑定后候选区回到 signature 1 条且仍未勾选（主路起点干净）",
                candidates_restored,
                len(candidates_restored) == 1
                and candidates_restored[0]["id"]
                == f"spec-text-{INFO_SHOT}-signature_features"
                and candidates_restored[0]["checked"] is False)
            # C0a：勾 1 条文案、不选版面就保存：保存能成功（不写 layout 键）。
            page.click(f"#spec-text-{INFO_SHOT}-signature_features")
            page.wait_for_timeout(250)
            page.click(f'#shot-spec-list .shot-spec[data-shot-id="{INFO_SHOT}"] .toolbar button')
            page.wait_for_timeout(800)
            spec_nolayout = page.evaluate(DUMP_DOCS)["shotspec"]
            evidence.add(
                "C0a-save-without-layout",
                "selected+已选文案+未选版面时保存能成功，且 shot_spec 不写 layout 键",
                {"shotspec": spec_nolayout,
                 "specs_error": page.locator("#specs-error").inner_text()},
                spec_nolayout is not None
                and "layout" not in spec_nolayout["payload"]
                and spec_nolayout["payload"].get("print_intent") == "selected"
                and page.locator("#specs-error").inner_text() == "")
            # 到生成阶段：本地准备后确认单出现 DECISION_REQUIRED，消息含「还得先决定版面」。
            page.click("#stage-next-plan")
            page.wait_for_selector('[data-stage-panel="generate"]:not([hidden])',
                                   timeout=15_000)
            page.wait_for_timeout(2500)
            blocker_texts = [
                page.locator(".confirm-blocker").nth(i).inner_text()
                for i in range(page.locator(".confirm-blocker").count())]
            evidence.add(
                "C0b-gate-missing-layout",
                "缺 layout 时编译被拦：确认单出现 DECISION_REQUIRED 且消息含「还得先决定版面」",
                {"confirm_status": page.locator("#confirm-status").inner_text(),
                 "blockers": blocker_texts},
                any("DECISION_REQUIRED" in text and "还得先决定版面" in text
                    for text in blocker_texts))
            # 回方案改选「只放商品」：编译被拦，消息点明版面名。
            stage_nav.goto(page, "plan")
            stage_nav.reveal(page, "#specs-editor")
            page.wait_for_selector(f"#spec-layout-{INFO_SHOT}", state="visible",
                                   timeout=10_000)
            page.click(f"#spec-layout-{INFO_SHOT}-product_only")
            page.wait_for_timeout(250)
            page.click(f'#shot-spec-list .shot-spec[data-shot-id="{INFO_SHOT}"] .toolbar button')
            page.wait_for_timeout(800)
            stage_nav.goto(page, "generate")
            page.wait_for_timeout(2500)
            blocker_texts_only = [
                page.locator(".confirm-blocker").nth(i).inner_text()
                for i in range(page.locator(".confirm-blocker").count())]
            evidence.add(
                "C0c-gate-product-only",
                "layout=只放商品+selected 时编译被拦：消息含「不能选『只放商品』版面」",
                {"confirm_status": page.locator("#confirm-status").inner_text(),
                 "blockers": blocker_texts_only},
                any("不能选" in text and "只放商品" in text and "版面" in text
                    for text in blocker_texts_only))
            # 回方案改选左文右版面，继续主路。
            stage_nav.goto(page, "plan")
            stage_nav.reveal(page, "#specs-editor")
            page.wait_for_selector(f"#spec-layout-{INFO_SHOT}", state="visible",
                                   timeout=10_000)
            page.click(f"#spec-layout-{INFO_SHOT}-product_left_text_right")
            page.wait_for_timeout(250)
            page.locator(f"#spec-print-{INFO_SHOT}").scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            page.screenshot(path=str(shot_path("3-infographic-decisions")))
            page.click(f'.shot-spec[data-shot-id="{INFO_SHOT}"] .toolbar button')
            page.wait_for_timeout(800)
            dump = page.evaluate(DUMP_DOCS)
            spec = dump["shotspec"]
            sig = latest_confirmed_slot(dump, "signature_features")
            # 期望文案：text_list 按元素各一条，元素原文取自 fact_slot 确认值，不写死。
            expect_texts = list(sig["value"]) if sig else None
            actual_texts = ((spec or {}).get("payload") or {}).get("on_image_texts") or []
            c2_texts_ok = (
                expect_texts is not None and len(actual_texts) == len(expect_texts)
                and all(
                    item.get("text") == expect_texts[index]
                    and item.get("text_id") == f"t_signature_features_{index + 1}"
                    and item.get("source_slot_id") == "signature_features"
                    and item.get("source_slot_version") == sig["v"]
                    and item.get("status") == "confirmed"
                    for index, item in enumerate(actual_texts)))
            evidence.add(
                "C2-shotspec-keys",
                "shot_spec 三键逐字正确：print_intent=selected、"
                "layout=product_left_text_right、on_image_texts 按元素各一条 "
                "（3 条，text 逐一等于 fact_slot 确认值元素，不写死字符串）",
                {"shotspec": spec, "fact_slot": sig, "expect_texts": expect_texts},
                spec is not None
                and spec["payload"].get("print_intent") == "selected"
                and spec["payload"].get("layout") == "product_left_text_right"
                and c2_texts_ok)
            # C3. 勾选快照语义：来源事实前进后，已保存仍是旧版 + 出现旧版提示 + 编译被拦；
            # 重新勾选后按新值确认并恢复可提交（正式页面点击，不直接写库）。
            stage_nav.goto(page, "understand")
            page.wait_for_timeout(500)
            if "显示全部" in page.locator("#slots-toggle").inner_text():
                page.locator("#slots-toggle").click()
                page.wait_for_timeout(400)
            sig_row = page.locator('#slot-list .slot-row[data-slot-id="signature_features"]')
            sig_row.get_by_role("button", name="修改", exact=True).first.click()
            page.wait_for_timeout(400)
            sig_row.locator('[data-role="value"]').first.fill(
                "HONEY 浮雕\n蜂窝纹理\n透明罐身\n新增卖点")
            sig_row.get_by_role("button", name="保存", exact=True).first.click()
            page.wait_for_timeout(800)
            dump_after_edit = page.evaluate(DUMP_DOCS)
            sig_new = latest_confirmed_slot(dump_after_edit, "signature_features")
            stage_nav.goto(page, "plan")
            stage_nav.reveal(page, "#specs-editor")
            page.wait_for_selector(f"#spec-texts-{INFO_SHOT}", timeout=10_000)
            hint = page.locator(
                f"#spec-text-advanced-{INFO_SHOT}-signature_features")
            hint_text = hint.inner_text() if hint.count() else ""
            evidence.add(
                "C3a-stale-hint",
                "来源事实前进后（v2→v3），规格区出现旧版提示且仍勾选旧条目",
                {"hint_count": hint.count(), "hint_text": hint_text,
                 "checked": page.locator(
                     f"#spec-text-{INFO_SHOT}-signature_features").is_checked(),
                 "fact_slot": sig_new},
                hint.count() == 1 and "旧版" in hint_text and "v2" in hint_text
                and "v3" in hint_text
                and page.locator(
                    f"#spec-text-{INFO_SHOT}-signature_features").is_checked()
                and (sig_new or {}).get("v") == 3)
            # 不重新勾选直接保存：落库仍是旧版（不静默换值）。
            page.click(f'#shot-spec-list .shot-spec[data-shot-id="{INFO_SHOT}"] .toolbar button')
            page.wait_for_timeout(800)
            spec_stale = page.evaluate(DUMP_DOCS)["shotspec"]
            stale_texts = ((spec_stale or {}).get("payload") or {}).get("on_image_texts") or []
            evidence.add(
                "C3b-no-silent-upgrade",
                "未重新勾选即保存：on_image_texts 仍是旧版 3 条旧值 + 旧版本号 v2 "
                "（不静默换值）",
                {"shotspec": spec_stale, "expect_texts": expect_texts},
                spec_stale is not None
                and [item.get("text") for item in stale_texts] == expect_texts
                and all(item.get("source_slot_version") == 2
                        for item in stale_texts))
            # 到生成阶段：编译被拦，消息含「来源已不是当初确认的版本」。
            stage_nav.goto(page, "generate")
            page.wait_for_timeout(2500)
            stale_blockers = [
                page.locator(".confirm-blocker").nth(i).inner_text()
                for i in range(page.locator(".confirm-blocker").count())]
            goto_btn = page.locator("#confirm-blockers .confirm-blocker-goto")
            evidence.add(
                "C3c-stale-blocked",
                "旧版文案编译被拦：阻断消息含「来源已不是当初确认的版本」",
                {"confirm_status": page.locator("#confirm-status").inner_text(),
                 "blockers": stale_blockers},
                any("来源已不是当初确认的版本" in text for text in stale_blockers))
            # C4：阻断项按钮文案 + 点击直达对应决定控件。
            goto_text = goto_btn.first.inner_text() if goto_btn.count() else ""
            evidence.add(
                "C4a-goto-label",
                "确认单阻断项「去补足此项」按钮有正确文案（非空按钮）",
                {"goto_count": goto_btn.count(), "goto_text": goto_text},
                goto_btn.count() >= 1 and goto_text == "去补足此项")
            page.click("#confirm-blockers .confirm-blocker-goto")
            page.wait_for_timeout(800)
            landed = page.evaluate(
                """(shotId) => {
                  const el = document.getElementById("spec-texts-" + shotId);
                  if (!el) return { exists: false };
                  const rect = el.getBoundingClientRect();
                  return { exists: true, top: Math.round(rect.top),
                    visible: rect.top >= 0 && rect.top < window.innerHeight };
                }""", INFO_SHOT)
            evidence.add(
                "C4b-goto-lands-on-texts",
                "点击「去补足此项」后切到方案阶段、规格区展开，文案候选区在视口内",
                {"stage": stage_nav.current_stage(page), "landed": landed,
                 "specs_open": page.evaluate(
                     "() => document.getElementById('specs-section')"
                     "?.closest('details')?.open")},
                stage_nav.current_stage(page) == "plan" and landed.get("visible") is True)
            # 重新勾选（先取消再勾选）→ 保存 → 按新值确认。
            page.click(f"#spec-text-{INFO_SHOT}-signature_features")
            page.wait_for_timeout(300)
            page.click(f"#spec-text-{INFO_SHOT}-signature_features")
            page.wait_for_timeout(300)
            page.click(f'#shot-spec-list .shot-spec[data-shot-id="{INFO_SHOT}"] .toolbar button')
            page.wait_for_timeout(800)
            dump_rechecked = page.evaluate(DUMP_DOCS)
            spec_new = dump_rechecked["shotspec"]
            sig_v3 = latest_confirmed_slot(dump_rechecked, "signature_features")
            expect_new = list(sig_v3["value"]) if sig_v3 else None
            new_texts = ((spec_new or {}).get("payload") or {}).get("on_image_texts") or []
            evidence.add(
                "C3d-recheck-recovers",
                "重新勾选并保存后：on_image_texts 按新值 v3 确认（4 条元素），旧版提示消失",
                {"shotspec": spec_new, "fact_slot": sig_v3,
                 "hint_count": page.locator(
                     f"#spec-text-advanced-{INFO_SHOT}-signature_features").count()},
                spec_new is not None
                and [item.get("text") for item in new_texts] == expect_new
                and all(item.get("source_slot_version") == 3 for item in new_texts)
                and page.locator(
                    f"#spec-text-advanced-{INFO_SHOT}-signature_features").count() == 0)
            # C2 的 expect_texts 已是旧值：主路 D 改用新值比对。
            expect_texts = expect_new
            # C6a. 反方向门：有文字版面 + 不印文字 → 编译被拦（正式页面点击实证）。
            # 出发态是 C3d 刚保存的 (selected, 商品在左文字在右, 4 条 v3)。
            stage_nav.reveal(page, "#specs-editor")
            page.wait_for_selector(f"#spec-layout-{INFO_SHOT}", state="visible",
                                   timeout=10_000)
            page.click(f"#spec-print-none-{INFO_SHOT}")
            page.wait_for_timeout(400)
            evidence.add(
                "C6a1-print-none-hides-texts",
                "印字改成「不印新增文字」后文案候选区隐藏（草稿所选仍在，只是不再印）",
                {"texts_visible": page.locator(f"#spec-texts-{INFO_SHOT}").count()},
                page.locator(f"#spec-texts-{INFO_SHOT}").count() == 0)
            page.click(f'#shot-spec-list .shot-spec[data-shot-id="{INFO_SHOT}"] .toolbar button')
            page.wait_for_timeout(800)
            spec_print_none = page.evaluate(DUMP_DOCS)["shotspec"]
            none_texts = ((spec_print_none or {}).get("payload") or {}).get("on_image_texts")
            evidence.add(
                "C6a2-saved-print-none",
                "保存后 shot_spec 记录 print_intent=none、版面仍是 product_left_text_right、"
                "on_image_texts 已清空",
                {"shotspec": spec_print_none},
                spec_print_none is not None
                and spec_print_none["payload"].get("print_intent") == "none"
                and spec_print_none["payload"].get("layout") == "product_left_text_right"
                and none_texts == [])
            stage_nav.goto(page, "generate")
            page.wait_for_timeout(2500)
            layout_gate_blockers = [
                page.locator(".confirm-blocker").nth(i).inner_text()
                for i in range(page.locator(".confirm-blocker").count())]
            evidence.add(
                "C6a3-layout-gate-blocks",
                "不印+文字版面时编译被拦：阻断消息是 $.shot_spec.layout 那条"
                "（含「不会有图上文字」「只放商品」）",
                {"confirm_status": page.locator("#confirm-status").inner_text(),
                 "blockers": layout_gate_blockers},
                any("不会有图上文字" in text and "只放商品" in text
                    for text in layout_gate_blockers))
            # 回方案：页面上能看到缺文案提示；改成只放商品 → 该阻断消失。
            stage_nav.goto(page, "plan")
            stage_nav.reveal(page, "#specs-editor")
            page.wait_for_selector(f"#spec-layout-{INFO_SHOT}", state="visible",
                                   timeout=10_000)
            needs_text_hint = page.locator(f"#spec-layout-needs-text-{INFO_SHOT}")
            needs_text = (needs_text_hint.inner_text()
                          if needs_text_hint.count() else "")
            evidence.add(
                "C6a4-layout-hint-visible",
                "页面上能看到 #spec-layout-needs-text-<shotId> 提示"
                "（选了文字版面但现在没有要印的文案）",
                {"hint_count": needs_text_hint.count(), "hint_text": needs_text},
                needs_text_hint.count() == 1 and "只放商品" in needs_text)
            needs_text_hint.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            page.screenshot(path=str(shot_path("6a-layout-needs-text")))
            page.click(f"#spec-layout-{INFO_SHOT}-product_only")
            page.wait_for_timeout(250)
            page.click(f'#shot-spec-list .shot-spec[data-shot-id="{INFO_SHOT}"] .toolbar button')
            page.wait_for_timeout(800)
            stage_nav.goto(page, "generate")
            page.wait_for_timeout(2500)
            recovered_blockers = [
                page.locator(".confirm-blocker").nth(i).inner_text()
                for i in range(page.locator(".confirm-blocker").count())]
            evidence.add(
                "C6a5-product-only-recovers",
                "版面改成「只放商品」并保存后：确认单不再出现「不会有图上文字」阻断（门恢复）",
                {"confirm_status": page.locator("#confirm-status").inner_text(),
                 "blockers": recovered_blockers},
                not any("不会有图上文字" in text for text in recovered_blockers))

            # C6b. 来源解绑：先回到 (selected, 左文右) 并勾选保存一条文案。
            # （C6a 收尾是 (none, 只放商品)：selected 配只放商品会被另一方向门先拦，
            # 所以这里一次把印字、版面、文案都选好再保存。）
            stage_nav.goto(page, "plan")
            stage_nav.reveal(page, "#specs-editor")
            page.wait_for_selector(f"#spec-layout-{INFO_SHOT}", state="visible",
                                   timeout=10_000)
            page.click(f"#spec-print-selected-{INFO_SHOT}")
            page.wait_for_timeout(300)
            page.click(f"#spec-layout-{INFO_SHOT}-product_left_text_right")
            page.wait_for_timeout(250)
            page.wait_for_selector(f"#spec-text-{INFO_SHOT}-signature_features",
                                   state="visible", timeout=10_000)
            if page.locator(f"#spec-text-{INFO_SHOT}-signature_features").is_checked():
                page.click(f"#spec-text-{INFO_SHOT}-signature_features")
                page.wait_for_timeout(300)
            page.click(f"#spec-text-{INFO_SHOT}-signature_features")
            page.wait_for_timeout(300)
            page.click(f'#shot-spec-list .shot-spec[data-shot-id="{INFO_SHOT}"] .toolbar button')
            page.wait_for_timeout(800)
            dump_reselect = page.evaluate(DUMP_DOCS)
            spec_reselect = dump_reselect["shotspec"]
            sig_v3_now = latest_confirmed_slot(dump_reselect, "signature_features")
            reselect_texts = ((spec_reselect or {}).get("payload") or {}).get("on_image_texts") or []
            evidence.add(
                "C6b0-selected-saved",
                "解绑前起点干净：shot_spec 已是 (selected, 左文右) + 4 条 v3 文案",
                {"shotspec": spec_reselect, "fact_slot": sig_v3_now},
                spec_reselect is not None
                and spec_reselect["payload"].get("print_intent") == "selected"
                and spec_reselect["payload"].get("layout") == "product_left_text_right"
                and [item.get("text") for item in reselect_texts] == list(sig_v3_now["value"])
                and all(item.get("source_slot_version") == 3 for item in reselect_texts))
            # 在「图片任务」里把该事实解绑（正常 UI 操作：shot-list 绑定区取消勾选 + 保存）。
            set_binding(INFO_SHOT, "signature_features", False)
            save_binding(INFO_SHOT)
            page.locator(f"#spec-texts-{INFO_SHOT}").scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            orphan = page.locator(f"#spec-text-orphan-{INFO_SHOT}-signature_features")
            orphan_checked = orphan.is_checked() if orphan.count() else False
            orphan_text = (page.evaluate(
                "(oid) => document.getElementById(oid).parentElement.textContent",
                f"spec-text-orphan-{INFO_SHOT}-signature_features")
                if orphan.count() else "")
            evidence.add(
                "C6b1-orphan-visible",
                "解绑后之前保存的文案仍然可见：#spec-text-orphan-<shotId>-signature_features "
                "存在且保持勾选，文案内容照旧（4 条 v3，不是凭空消失）",
                {"orphan_count": orphan.count(), "orphan_checked": orphan_checked,
                 "orphan_text": orphan_text, "fact_slot": sig_v3_now},
                orphan.count() == 1 and orphan_checked
                and all(item in orphan_text for item in (sig_v3_now["value"] or [])))
            page.locator(f"#spec-texts-{INFO_SHOT}").scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            page.screenshot(path=str(shot_path("6b-orphan-unbound")))
            stage_nav.goto(page, "generate")
            page.wait_for_timeout(2500)
            unbound_blockers = [
                page.locator(".confirm-blocker").nth(i).inner_text()
                for i in range(page.locator(".confirm-blocker").count())]
            evidence.add(
                "C6b2-unbound-blocked",
                "解绑后编译被拦：阻断消息含「不在这张图的绑定里」",
                {"confirm_status": page.locator("#confirm-status").inner_text(),
                 "blockers": unbound_blockers},
                any("不在这张图的绑定里" in text for text in unbound_blockers))
            # 勾掉该行并保存 → on_image_texts 变空（读 shot_spec 记录）。
            stage_nav.goto(page, "plan")
            stage_nav.reveal(page, "#specs-editor")
            page.wait_for_selector(f"#spec-text-orphan-{INFO_SHOT}-signature_features",
                                   state="visible", timeout=10_000)
            page.click(f"#spec-text-orphan-{INFO_SHOT}-signature_features")
            page.wait_for_timeout(400)
            page.click(f'#shot-spec-list .shot-spec[data-shot-id="{INFO_SHOT}"] .toolbar button')
            page.wait_for_timeout(800)
            spec_emptied = page.evaluate(DUMP_DOCS)["shotspec"]
            emptied_texts = ((spec_emptied or {}).get("payload") or {}).get("on_image_texts") or []
            evidence.add(
                "C6b3-orphan-removed-empties",
                "勾掉孤儿行并保存后：shot_spec.on_image_texts 变空（读 shot_spec 记录；"
                "孤儿行同步消失）",
                {"shotspec": spec_emptied,
                 "orphan_count": page.locator(
                     f"#spec-text-orphan-{INFO_SHOT}-signature_features").count()},
                emptied_texts == []
                and page.locator(
                    f"#spec-text-orphan-{INFO_SHOT}-signature_features").count() == 0)
            # 重新绑定 + 勾选候选 + 保存 → 编译恢复。
            set_binding(INFO_SHOT, "signature_features", True)
            save_binding(INFO_SHOT)
            page.locator(f"#spec-texts-{INFO_SHOT}").scroll_into_view_if_needed()
            page.wait_for_timeout(400)
            page.click(f"#spec-text-{INFO_SHOT}-signature_features")
            page.wait_for_timeout(300)
            page.click(f'#shot-spec-list .shot-spec[data-shot-id="{INFO_SHOT}"] .toolbar button')
            page.wait_for_timeout(800)
            stage_nav.goto(page, "generate")
            page.wait_for_timeout(2500)
            rebound_blockers = [
                page.locator(".confirm-blocker").nth(i).inner_text()
                for i in range(page.locator(".confirm-blocker").count())]
            evidence.add(
                "C6b4-rebind-recovers",
                "重新绑定 + 勾选 + 保存后：确认单不再出现「不在这张图的绑定里」阻断（编译恢复）",
                {"confirm_status": page.locator("#confirm-status").inner_text(),
                 "blockers": rebound_blockers},
                not any("不在这张图的绑定里" in text for text in rebound_blockers))
            # 回到方案阶段：后续主路从 #stage-next-plan 进入生成。
            stage_nav.goto(page, "plan")


            # ---- 生成：Prompt 预览 + 提交 ----
            page.click("#stage-next-plan")
            page.wait_for_selector('[data-stage-panel="generate"]:not([hidden])',
                                   timeout=15_000)
            page.wait_for_timeout(1500)
            confirm_status = page.locator("#confirm-status").inner_text()
            evidence.add(
                "SETUP-confirm-ready",
                "本地准备完成后可提交 5 张（无阻断）",
                {"status": confirm_status,
                 "action_disabled": page.locator("#confirm-action").is_disabled(),
                 "blockers": page.locator(".confirm-blocker").count()},
                "本次明确发送 5 张" in confirm_status
                and not page.locator("#confirm-action").is_disabled()
                and page.locator(".confirm-blocker").count() == 0)
            page.click("#prompt-details summary")
            page.wait_for_selector(
                f'.shot-spec[data-shot-id="{INFO_SHOT}"] .prompt-text', timeout=10_000)
            previews = page.evaluate(
                "() => [...document.querySelectorAll('#prompt-editor .shot-spec')]"
                ".map((n) => ({shot: n.getAttribute('data-shot-id'),"
                " state: n.getAttribute('data-prompt-state'),"
                " text: (n.querySelector('.prompt-text') || {}).textContent || ''}))")
            page.locator(f'#prompt-editor .shot-spec[data-shot-id="{INFO_SHOT}"]'
                         ).scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            page.screenshot(path=str(shot_path("4-prompt-preview")))
            constants = page.evaluate(DOMAIN_CONSTANTS)
            brief = constants["brief"]
            info_preview = next((item for item in previews
                                 if item["shot"] == INFO_SHOT), None)
            main_preview = next((item for item in previews
                                 if item["shot"] == "shot_main_clean"), None)
            # D1：信息图预览逐字包含本用途 4 句 + product_fidelity 状态句
            info_sentences = brief["infographic"]
            # 期望状态句：正式 prompt_version 记录里同一图的 product_fidelity 段
            # （真实编译产物，不手抄；干净展示选择应使该段含去污例外）。
            info_doc = page.evaluate(PROMPT_DOCS, [INFO_SHOT]).get(INFO_SHOT) or {}
            info_sections = (((info_doc.get("record") or {}).get("compiled") or {})
                             .get("sections") or [])
            fidelity_text = next(
                (s.get("text") or "" for s in info_sections
                 if s.get("key") == "product_fidelity"), "")
            assert fidelity_text, "正式 prompt_version 记录缺 product_fidelity 段"
            d1_missing = [s for s in info_sentences
                          if s not in (info_preview or {}).get("text", "")]
            d1_fidelity = fidelity_text in (info_preview or {}).get("text", "")
            evidence.add(
                "D1-infographic-brief-verbatim",
                "信息图 Prompt 预览逐字包含 ROLE_VISUAL_BRIEF.infographic 全部句子"
                "（4 句，从页面 /domain/index.js 取常量）与 product_fidelity "
                "干净展示状态句",
                {"sentences": info_sentences, "missing": d1_missing,
                 "fidelity_present": d1_fidelity,
                 "preview_chars": len((info_preview or {}).get("text", ""))},
                info_preview is not None and not d1_missing and d1_fidelity)
            # D2：跨用途串味即红——信息图预览不含其他用途句子，主图预览不含信息图句子
            other_roles = [role for role in brief if role != "infographic"]
            leaked_into_info = [s for role in other_roles for s in brief[role]
                                if s and s in (info_preview or {}).get("text", "")]
            leaked_into_main = [s for s in info_sentences
                                if s and s in (main_preview or {}).get("text", "")]
            main_sentences = brief["main"]
            main_missing = [s for s in main_sentences
                            if s not in (main_preview or {}).get("text", "")]
            evidence.add(
                "D2-no-cross-role-leak",
                "信息图预览不含其他用途的画面简报句，主图预览含本用途 4 句且"
                "不含信息图句子（跨用途串味即红）",
                {"leaked_into_info": leaked_into_info,
                 "leaked_into_main": leaked_into_main,
                 "main_missing": main_missing},
                not leaked_into_info and not leaked_into_main and not main_missing)
            # D3：信息图预览含版面句与所选文案逐字（元素逐条「」引用，从 fact_slot 取值）
            layout_sentence = ("商品完整放在画面左侧约三分之二区域，关键部位不被裁切"
                               "也不被文字遮挡；右侧保留干净留白放置下方给定的文字。")
            d3_text = (info_preview or {}).get("text", "")
            d3_quoted = [(("「" + item + "」") in d3_text) for item in (expect_texts or [])]
            evidence.add(
                "D3-layout-and-verbatim-text",
                "信息图预览含左文右版面句，且所选 4 条元素逐条以「」逐字出现 "
                "（fact_slot 值，不写死）",
                {"layout_present": layout_sentence in d3_text,
                 "quoted": d3_quoted, "expect_texts": expect_texts},
                layout_sentence in d3_text
                and len(d3_quoted) == 4 and all(d3_quoted))
            # D4：主图（非印字角色、无 layout 决定）正文不含「本图版面」段。
            evidence.add(
                "D4-no-layout-section-without-decision",
                "主图预览不含「本图版面」段（未做版面决定即不排段，旧规格正文不变）",
                {"has_layout_section": "本图版面" in (main_preview or {}).get("text", "")},
                main_preview is not None
                and "本图版面" not in (main_preview or {}).get("text", ""))
            # E：抓真实提交请求，prompt 与编译产物逐字相等且含画面简报句
            prompt_docs = page.evaluate(PROMPT_DOCS, shots)
            requests: list[dict] = []

            def _capture(request) -> None:
                if (request.method == "POST"
                        and request.url.split("?", 1)[0].endswith("/api/v2/images/submit")):
                    requests.append(json.loads(request.post_data or "{}"))

            page.on("request", _capture)
            try:
                page.click("#confirm-action")
                shared.wait_terminal(page, shots, timeout=180_000)
            finally:
                page.remove_listener("request", _capture)
            states = page.evaluate(shared.ATTEMPT_STATES)
            evidence.add(
                "E1-terminal",
                "提交后按现有流程轮询到终态：5 张图全部 succeeded",
                states,
                all(states.get(shot) == "succeeded" for shot in shots)
                and len(requests) == len(shots))
            page.screenshot(path=str(shot_path("5-candidates")))
            # action_id → shot_id 映射（attempt 链 payload）
            data = page.evaluate(shared.PROBE)
            action_to_shot = {}
            for shot_id, chain in (data.get("attempt_chains") or {}).items():
                if chain:
                    action_to_shot[(chain[-1].get("payload") or {}).get("action_id")] = shot_id
            e2_rows = []
            e2_ok = True
            for body in requests:
                shot_id = action_to_shot.get(body.get("action_id"))
                doc = (prompt_docs.get(shot_id) or {}) if shot_id else None
                compiled_text = ((doc or {}).get("record") or {}).get("compiled", {}).get("text")
                equal = (shot_id is not None and compiled_text is not None
                         and body.get("prompt") == compiled_text)
                role_sentences = brief.get((((doc or {}).get("record") or {}).get("role_id")) or "",
                                           [])
                has_brief = bool(role_sentences) and all(
                    s in (body.get("prompt") or "") for s in role_sentences)
                e2_rows.append({"action_id": body.get("action_id"), "shot_id": shot_id,
                                "prompt_equal_compiled": equal, "has_role_brief": has_brief,
                                "prompt_chars": len(body.get("prompt") or "")})
                e2_ok = e2_ok and equal and has_brief
            evidence.add(
                "E2-request-equals-compiled",
                "每张图的提交请求 prompt 与页面编译产物逐字相等，且含该用途"
                "全部画面简报句（证明程序把编译稿发出去，不是硬编码）",
                e2_rows, e2_ok and len(e2_rows) == len(shots))
            # E3：请求图像参数与冻结记录逐项相等（期望值只读页面 prompt_version
            # 记录的 request_snapshot，不手抄；body 携带才比，未携带如实报 absent）
            e3_rows = []
            e3_ok = True
            for body in requests:
                shot_id = action_to_shot.get(body.get("action_id"))
                doc = (prompt_docs.get(shot_id) or {}) if shot_id else None
                record = (doc or {}).get("record") or {}
                snapshot = record.get("request_snapshot") or {}
                compared: dict = {}
                absent: list = []
                for key in ("size", "n", "negative_prompt", "prompt_extend",
                            "watermark", "output_format"):
                    if key not in body:
                        absent.append({"key": key, "where": "request_body",
                                       "record_value": snapshot.get(key)})
                        continue
                    if key not in snapshot:
                        compared[key] = {"request": body.get(key),
                                         "record": None,
                                         "equal": False,
                                         "note": "record无此字段，不可验证"}
                        e3_ok = False
                        continue
                    same = body.get(key) == snapshot.get(key)
                    compared[key] = {"request": body.get(key),
                                     "record": snapshot.get(key),
                                     "equal": same}
                    e3_ok = e3_ok and same
                # model_id 对快照 model；target 对快照 target 的四个身份键
                # （credential_source 是运行时凭据标签，快照无此字段，只记录不比）
                if "model_id" in body:
                    same = body.get("model_id") == snapshot.get("model")
                    compared["model_id"] = {"request": body.get("model_id"),
                                            "record": snapshot.get("model"),
                                            "equal": same}
                    e3_ok = e3_ok and same
                else:
                    absent.append({"key": "model_id", "where": "request_body",
                                   "record_value": snapshot.get("model")})
                snap_target = snapshot.get("target") or {}
                raw_target = body.get("target")
                body_target = raw_target if isinstance(raw_target, dict) else None
                if body_target is None:
                    absent.append({"key": "target", "where": "request_body",
                                   "record_value": snap_target or None})
                else:
                    target_compared = {}
                    for key in ("provider_id", "model_id", "protocol",
                                "capability_version"):
                        same = body_target.get(key) == snap_target.get(key)
                        target_compared[key] = {"request": body_target.get(key),
                                                "record": snap_target.get(key),
                                                "equal": same}
                        e3_ok = e3_ok and same
                    compared["target"] = {
                        "compared": target_compared,
                        "credential_source": body_target.get("credential_source"),
                        "note": "credential_source只记录（快照无此字段），四身份键逐项比",
                    }
                e3_rows.append({"action_id": body.get("action_id"),
                                "shot_id": shot_id,
                                "compared": compared, "absent": absent})
            evidence.add(
                "E3-request-parameters-match-record",
                "每张提交请求的图像参数（size、n 及携带的 prompt_extend/watermark/"
                "output_format/model_id/target）与页面冻结 request_snapshot 逐项"
                "相等；negative_prompt 未被请求携带（服务端契约亦无此字段），如实报 absent",
                {"compared_keys": ["size", "n", "prompt_extend", "watermark",
                                   "output_format", "model_id", "target"],
                 "absent_keys": ["negative_prompt"],
                 "rows": e3_rows},
                e3_ok and len(e3_rows) == len(shots))
            # E4：请求 references 按序与冻结记录一致，且字节身份可独立验证
            # （期望 role/sha256 只读 request_snapshot.references；期望 media_type
            # 只读页面资产行 asset_rows；解码用标准 base64+sha256，不手抄期望值）
            asset_media = {}
            for row in (data.get("asset_rows") or []):
                if row.get("sha256"):
                    asset_media[row["sha256"]] = row.get("media_type")
            e4_rows = []
            e4_ok = True
            for body in requests:
                shot_id = action_to_shot.get(body.get("action_id"))
                doc = (prompt_docs.get(shot_id) or {}) if shot_id else None
                record = (doc or {}).get("record") or {}
                frozen_refs = ((record.get("request_snapshot") or {})
                               .get("references") or [])
                body_refs = body.get("references") or []
                positions = []
                for index, ref in enumerate(body_refs):
                    raw = ref.get("data_base64") or ""
                    try:
                        digest = hashlib.sha256(
                            base64.b64decode(raw, validate=True)).hexdigest()
                    except Exception:
                        digest = None
                    frozen = frozen_refs[index] if index < len(frozen_refs) else None
                    exp_media = (asset_media.get((frozen or {}).get("sha256"))
                                 if frozen else None)
                    role_equal = (frozen is not None
                                  and ref.get("role") == frozen.get("role"))
                    media_equal = (exp_media is not None
                                   and ref.get("media_type") == exp_media)
                    matches_field = (digest is not None
                                     and digest == ref.get("sha256"))
                    matches_record = (frozen is not None and digest is not None
                                      and digest == frozen.get("sha256"))
                    primary_ok = (ref.get("role") != "primary"
                                  or digest == PRIMARY_SHA256)
                    positions.append({
                        "index": index,
                        "role": ref.get("role"),
                        "role_expected": (frozen or {}).get("role"),
                        "role_equal": role_equal,
                        "media_type": ref.get("media_type"),
                        "media_type_expected": exp_media,
                        "media_type_equal": media_equal,
                        "sha256_field": ref.get("sha256"),
                        "sha256_decoded": digest,
                        "matches_field": matches_field,
                        "matches_record": matches_record,
                        "primary_fixture_match": (
                            digest == PRIMARY_SHA256
                            if ref.get("role") == "primary" else None),
                    })
                    e4_ok = (e4_ok and role_equal and media_equal
                             and matches_field and matches_record and primary_ok)
                length_equal = len(body_refs) == len(frozen_refs)
                e4_ok = e4_ok and length_equal
                e4_rows.append({"action_id": body.get("action_id"),
                                "shot_id": shot_id,
                                "length_equal": length_equal,
                                "body_count": len(body_refs),
                                "record_count": len(frozen_refs),
                                "positions": positions})
            evidence.add(
                "E4-reference-identity-order",
                "每张提交请求的 references 与冻结记录同长度、按序同 role/media_type，"
                "且 base64 解码 sha256 同时等于请求自带 sha256 与记录 sha256；"
                "primary 位解码值独立等于 PRIMARY_SHA256 夹具值",
                {"primary_sha256": PRIMARY_SHA256, "rows": e4_rows},
                e4_ok and len(e4_rows) == len(shots))

            # F：零 console error / page error
            unexpected_console = [line for line in logs["console"]
                                  if not any(key in line for key in CONSOLE_WHITELIST)]
            evidence.add(
                "F-zero-errors",
                "零 console error / page error（白名单：无；本轮未登记任何已知问题）",
                {"console": logs["console"], "page": logs["page"],
                 "http": logs["http"], "whitelist": list(CONSOLE_WHITELIST)},
                not unexpected_console and not logs["page"])

            # G：截图落盘
            shots_taken = []
            for name in ("1-style-undecided", "2-style-decided", "3-infographic-decisions",
                         "4-prompt-preview", "5-candidates",
                         "6a-layout-needs-text", "6b-orphan-unbound"):
                target = shot_path(name)
                shots_taken.append({"file": target.name,
                                    "bytes": target.stat().st_size if target.exists() else 0})
            evidence.add(
                "G-screenshots",
                "至少 4 张截图落盘（风格决定区、单图印字/版面区、Prompt 预览含"
                "画面简报、提交后候选）",
                shots_taken,
                len([item for item in shots_taken if item["bytes"] > 0]) >= 4)
        finally:
            context.close()

    result = {
        "schema_version": 1,
        "name": "issue9-ui-e2e",
        "page": args.base_url.rstrip("/") + "/",
        "project_zip": str(PROJECT_ZIP.relative_to(ROOT)).replace("\\", "/"),
        "primary_sha256": PRIMARY_SHA256,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed" if evidence.ok else "failed",
        "checks": evidence.checks,
        "honest_boundary": ("只验证提示词编译/请求消费/页面行为；"
                            "未验证图像像素、印字渲染位置与模型质量。"),
        "not_covered": [
            "像素层面印字是否出现、位置是否在留白区：替身 provider 只回固定 PNG，"
            "不可验，需真实模型 + 人工看图（工单第 6 条）。",
            "英文站点文案语言：本轮文案逐字取自中文事实值，"
            "ON_IMAGE_TEXT_NOT_PLATFORM_LANGUAGE 警告预期存在，未纳入通过门。",
            "返工/重提路径：本轮只走首次提交，未覆盖返工编译。",
        ],
    }
    (EVIDENCE_DIR / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"status={result['status']} evidence={EVIDENCE_DIR}")
    if not args.keep_profile:
        import shutil
        shutil.rmtree(temp_root, ignore_errors=True)
    return 0 if evidence.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
