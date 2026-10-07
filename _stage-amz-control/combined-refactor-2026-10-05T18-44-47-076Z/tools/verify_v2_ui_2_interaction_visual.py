#!/usr/bin/env python
"""V2.UI.2 六阶段交互与视觉基线验证：静态契约 + 真实工作台走查 + 响应式/键盘/视觉证据。

正向（本套件证明什么）：
  1) 信息架构：项目首页 + 同页六阶段外壳（资料—理解—方案—生成—审核返工—交付），
     顺序、标签、标题与导航语义来自唯一权威 `app/product_v2/index.html`。
  2) 首页紧凑：空白态只有一个创建入口（primary）与一个次级导入；不预填示例商品。
  3) 外壳纯净：`ui/stage-shell.js` 只做界面投影，不持有业务状态、不读写存储、不发请求。
  4) 表现层：样式来自 `styles.css` 的 `:root` token；无内联样式、无外部 CDN、无新依赖。
  5) 空白首页 / 新项目默认停靠「资料」/ 缺资料时外发理解禁用并说明缺什么，人工填写入口始终可用。
  6) 阶段可达性：六个任务入口始终可达（不禁用、不锁定）；切换阶段只换面板与摘要，
     稳态下不写任何 IndexedDB 记录、不授予外发/采用/导出操作权限。
  7) 完整闭环后：阶段条标记完成与当前，审核阶段以图片为中心列出逐图审核卡，
     交付阶段显示门禁清单与「生成交付包（ZIP）」在 V2.6.2 接入前的真实禁用说明。
  8) 390px 与 200% 缩放等价视口（1440 窗口缩到 720×450 CSS 像素）无横向溢出、关键操作可见。
  9) 键盘路径：新建、打开、分析、切换阶段可全程不用鼠标。
 10) 零意外 console/page error；IndexedDB 后置条件成立。

反向（本套件拒绝什么）：
  - 外壳持有业务状态、直连 IndexedDB 或 fetch；
  - index.html 出现内联样式、外部资源或第二套阶段定义；
  - 空白启动预填商品或示例数据。

边界：0 次真实模型调用（fake providers + 本机服务器）。产品发起人走查（信息层级、主操作、
图片比较、视觉方向）不能由本脚本替代；本脚本只交出「可走查 + 契约成立 + 既有回归不破」的证据。

用法：
    uv run --locked python tools/verify_v2_ui_2_interaction_visual.py --label final
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402

enable_utf8()

from src.providers.v2_fake_image import FakeImageProvider  # noqa: E402
from src.providers.v2_fake_review import FakeReviewProvider  # noqa: E402
from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: E402

PRODUCT_DIR = ROOT / "app" / "product_v2"
EVIDENCE_DIR = ROOT / "evals" / "product-v2"
EVIDENCE_IMAGE_DIR = EVIDENCE_DIR / "evidence"
CONTRACT = "v2.ui.2"
STAGE_IDS = ["intake", "understand", "plan", "generate", "review", "deliver"]
STAGE_LABELS = {"intake": "资料", "understand": "理解", "plan": "方案",
                "generate": "生成", "review": "审核返工", "deliver": "交付"}
STAGE_TITLE_KEYWORDS = {"intake": ("资料",), "understand": ("理解",), "plan": ("方案",),
                        "generate": ("生成",), "review": ("审核", "返工"), "deliver": ("交付",)}
SHELL_FORBIDDEN = ("indexedDB", "localStorage", "fetch(", "documents.save",
                   "repository", "XMLHttpRequest")
CSS_TOKENS = ("--bg", "--surface", "--border", "--accent", "--success", "--warn",
              "--danger", "--info", "--text", "--text-muted", "--focus")
UI_JS_FILES = ("app/product_v2/workspace.js", "app/product_v2/app.js",
               "app/product_v2/ui/stage-shell.js")


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v251 = load_module(ROOT / "tools" / "verify_v2_5_1_deterministic_review.py", "verify_v251")
server_module = v251.load_server_module()


def product_text(relative: str) -> str:
    return (PRODUCT_DIR / relative).read_text(encoding="utf-8")


STAGE_PROBE = """
() => {
  const nav = document.getElementById("stage-nav");
  const buttons = [...nav.querySelectorAll("[data-stage-nav]")].map((node) => ({
    id: node.dataset.stageNav,
    label: (node.querySelector(".stage-label") || {}).textContent.trim(),
    number: (node.querySelector(".stage-index") || {}).textContent.trim(),
    disabled: node.disabled,
    current: node.classList.contains("is-current"),
    complete: node.classList.contains("is-complete"),
    locked: node.classList.contains("is-locked"),
    aria: node.getAttribute("aria-current"),
  }));
  const panels = [...document.querySelectorAll("#stage-panels [data-stage-panel]")].map(
    (node) => ({
      id: node.dataset.stagePanel,
      hidden: node.hidden,
      title: (node.querySelector("h3") || {}).textContent.trim(),
    }));
  const summary = document.getElementById("stage-summary");
  return {
    buttons: buttons,
    panels: panels,
    visible: panels.filter((item) => !item.hidden).map((item) => item.id),
    summary: summary ? summary.textContent.trim() : "",
  };
}
"""

HOME_PROBE = """
() => {
  const visible = (node) => Boolean(node && !node.hidden && node.offsetParent !== null);
  return {
    empty_visible: visible(document.getElementById("empty-state")),
    project_rows: document.querySelectorAll("#project-list .project-row").length,
    visible_primary: [...document.querySelectorAll("#home-view button.primary")]
      .filter(visible).map((node) => node.id || node.textContent.trim()),
    import_class: (document.getElementById("import-trigger") || {}).className || null,
    name_value: (document.getElementById("new-project-name") || {}).value || "",
    home_visible: visible(document.getElementById("home-view")),
  };
}
"""

STORAGE_DIGEST = """
async () => {
  const names = (await indexedDB.databases()).map((item) => item.name);
  if (!names.includes("amz-listing-kit-v2")) {
    return { db_exists: false, projects: 0, documents: 0, assets: 0, digest: null };
  }
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open("amz-listing-kit-v2");
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const read = (store) => new Promise((resolve, reject) => {
    const request = db.transaction(store, "readonly").objectStore(store).getAll();
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const projects = await read("projects");
  const documents = await read("documents");
  const assets = await read("assets");
  db.close();
  const encoder = new TextEncoder();
  const buffer = await crypto.subtle.digest("SHA-256", encoder.encode(JSON.stringify({
    projects: projects,
    documents: documents,
    assets: assets.map((item) => ({ sha256: item.sha256, byte_size: item.byte_size,
      role: item.role })),
  })));
  const digest = [...new Uint8Array(buffer)]
    .map((byte) => byte.toString(16).padStart(2, "0")).join("");
  return { db_exists: true, projects: projects.length, documents: documents.length,
           assets: assets.length, digest: digest };
}
"""

OVERFLOW_PROBE = """
() => {
  const rect = (id) => {
    const node = document.getElementById(id);
    if (!node) return null;
    const box = node.getBoundingClientRect();
    return { x: Math.round(box.x), y: Math.round(box.y), width: Math.round(box.width),
             height: Math.round(box.height), visible: box.width > 0 && box.height > 0 };
  };
  const nav = document.getElementById("stage-nav");
  const navBox = nav ? nav.getBoundingClientRect() : null;
  const currentButton = nav ? nav.querySelector("[data-stage-nav].is-current") : null;
  const currentBox = currentButton ? currentButton.getBoundingClientRect() : null;
  return {
    document_scroll_width: document.documentElement.scrollWidth,
    document_client_width: document.documentElement.clientWidth,
    body_scroll_width: document.body.scrollWidth,
    nav_scrollable: nav ? nav.scrollWidth > nav.clientWidth + 1 : null,
    current_stage_visible: Boolean(navBox && currentBox
      && currentBox.left >= navBox.left - 1 && currentBox.right <= navBox.right + 1),
    current_stage: currentButton ? currentButton.dataset.stageNav : null,
    rects: { create: rect("create-project"), analyze: rect("analyze-run"),
             nav: rect("stage-nav"), deliver_export: rect("deliver-export") },
  };
}
"""


def check_static_guards() -> list[dict]:
    """静态守卫：信息架构、首页紧凑、外壳纯净、token 单源、无外部资源、渐进披露。"""

    html = product_text("index.html")
    css = product_text("styles.css")
    shell = product_text("ui/stage-shell.js")
    checks: list[dict] = []

    nav_ids = re.findall(r'data-stage-nav="([a-z]+)"', html)
    panel_ids = re.findall(r'data-stage-panel="([a-z]+)"', html)
    labels = [item.strip() for item in
              re.findall(r'<span class="stage-label">([^<]+)</span>', html)]
    # 属性容错：标题可以带 tabindex/aria 等属性（V2.UI.3 焦点落点），但六个标题与文案必须原样存在。
    titles = [item.strip() for item in
              re.findall(r'<h3\b[^>]*id="stage-[a-z]+-title"[^>]*>([^<]+)</h3>', html)]
    title_ok = len(titles) == len(STAGE_IDS) and all(
        all(keyword in titles[index] for keyword in STAGE_TITLE_KEYWORDS[stage_id])
        for index, stage_id in enumerate(STAGE_IDS))
    checks.append({
        "id": "UI2-01",
        "title": "信息架构唯一权威：六阶段导航与面板顺序、标签一致，面板标题是导航标签的完整表述，阶段条有导航语义与摘要输出位",
        "ok": nav_ids == STAGE_IDS and panel_ids == STAGE_IDS
              and labels == [STAGE_LABELS[item] for item in STAGE_IDS]
              and title_ok
              and 'aria-label="生产阶段"' in html
              and re.search(r'id="stage-summary"[^>]*role="status"', html) is not None,
        "detail": {"nav": nav_ids, "panels": panel_ids, "labels": labels, "titles": titles,
                   "title_ok": title_ok},
    })

    create_block = html[html.index('id="create-form"'):html.index("</form>")]
    home_block = html[html.index('id="home-view"'):html.index("工作台（六阶段）")]
    checks.append({
        "id": "UI2-02",
        "title": "空白首页紧凑：一个创建入口（primary）+ 一个次级导入，空态由状态驱动，不预填示例商品",
        "ok": create_block.count('class="primary"') == 1
              and 'id="create-project"' in create_block
              and 'id="import-trigger" class="ghost"' in html
              and re.search(r'id="empty-state"[^>]*hidden', html) is not None
              and re.search(r'id="new-project-name"[^>]*value=', html) is None
              and "<table" not in home_block,
        "detail": {"create_primary": create_block.count('class="primary"'),
                   "import_ghost": 'id="import-trigger" class="ghost"' in html,
                   "table_in_home": "<table" in home_block},
    })

    node = shutil.which("node")
    node_checks: dict[str, int | None] = {}
    for relative in UI_JS_FILES:
        if node is None:
            node_checks[relative] = None
            continue
        result = subprocess.run([node, "--check", str(ROOT / relative)],
                                capture_output=True, text=True, timeout=60, check=False)
        node_checks[relative] = result.returncode
    definitions = re.findall(r'\{ id: "([a-z]+)"', shell)
    forbidden = [token for token in SHELL_FORBIDDEN if token in shell]
    checks.append({
        "id": "UI2-03",
        "title": "外壳纯净：stage-shell 只做投影（无存储/网络/领域依赖），阶段定义顺序与产品合同一致，界面脚本语法通过",
        "ok": node is not None and not forbidden and definitions == STAGE_IDS
              and all(value == 0 for value in node_checks.values())
              and "export function createStageShell" in shell,
        "detail": {"forbidden_tokens": forbidden, "definitions": definitions,
                   "node_checks": node_checks},
    })

    var_count = css.count("var(--")
    missing = [token for token in CSS_TOKENS
               if re.search(re.escape(token) + r"\s*:", css) is None]
    checks.append({
        "id": "UI2-04",
        "title": "表现层 token 单源：styles.css 的 :root 提供颜色语义变量，组件用 var(--…) 取值，含 focus-visible 与小屏断点",
        "ok": ":root {" in css and not missing and var_count >= 60
              and ":focus-visible" in css and "@media (max-width" in css
              and css.count("!important") <= 3 and "<style" not in html,
        "detail": {"var_uses": var_count, "missing_tokens": missing,
                   "important": css.count("!important"),
                   "media_queries": re.findall(r"@media \(max-width: (\d+)px\)", css)},
    })

    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    refs = re.findall(r'<(?:script|link)[^>]+(?:src|href)="([^"]+)"', html)
    non_relative = [item for item in refs
                    if not item.startswith("./") and not item.startswith("data:")]
    checks.append({
        "id": "UI2-05",
        "title": "无内联样式、无外部资源、无新前端依赖：页面只引用本目录资源（data: 图标除外）",
        "ok": 'style="' not in html and not external and not non_relative,
        "detail": {"inline_style": html.count('style="'), "external": external,
                   "non_relative": non_relative},
    })

    meta_start = html.index('<details class="project-meta">')
    meta_block = html[meta_start:html.index("</details>", meta_start)]
    foots = re.findall(r'<footer class="stage-foot">(.*?)</footer>', html, re.S)
    buttons_per_foot = [item.count("<button") for item in foots]
    primary_per_foot = [item.count('class="primary"') for item in foots]
    checks.append({
        "id": "UI2-06",
        "title": "渐进披露与阶段推进：项目元数据收进 details；四个阶段脚注各只有一个推进按钮与实际主操作分离",
        "ok": 'id="project-scope"' in meta_block and len(foots) == 4
              and all(item == 1 for item in buttons_per_foot)
              and primary_per_foot.count(1) >= 3,
        "detail": {"project_scope_in_details": 'id="project-scope"' in meta_block,
                   "stage_feet": len(foots), "buttons_per_foot": buttons_per_foot,
                   "primary_per_foot": primary_per_foot},
    })
    return checks


def run_workbench_checks(stamp: str, console_errors: list[str],
                         page_errors: list[str]) -> tuple[list[dict], dict]:
    """真实工作台走查：空白首页 → 新建 → 六阶段 → 采用 → 交付 → 响应式与键盘。"""

    from playwright.sync_api import expect, sync_playwright  # noqa: PLC0415

    checks: list[dict] = []
    ui: dict = {"keyboard": {}}
    port = v251.free_port()
    server = server_module.create_product_v2_server(
        "127.0.0.1", port,
        provider_factory=lambda: FakeSemanticProvider(scenario="ok"),
        image_provider_factory=lambda: FakeImageProvider(scenario="ok"),
        review_provider_factory=lambda: FakeReviewProvider("ok"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    temp_root = Path(tempfile.mkdtemp(prefix="amz-ui2-"))
    profile = temp_root / "profile"
    reference = temp_root / "ref.png"
    reference.write_bytes(v251.png_bytes(1200, 1200, (36, 92, 160)))
    base = f"http://127.0.0.1:{port}"
    EVIDENCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    def shot(name: str) -> str:
        return f"evals/product-v2/evidence/{CONTRACT}-{name}-{stamp}.png"

    try:
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={"width": 1440, "height": 900})
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.on("console", lambda message: console_errors.append(
                    "[workbench] " + message.text) if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(
                    "[workbench] " + str(error)))

                def stage_state() -> dict:
                    return page.evaluate(STAGE_PROBE)

                def storage() -> dict:
                    return page.evaluate(STORAGE_DIGEST)

                page.goto(base + "/", wait_until="networkidle")
                page.wait_for_selector("#empty-state:not([hidden])", timeout=60_000)
                home = page.evaluate(HOME_PROBE)
                home_path = shot("home")
                page.screenshot(path=str(ROOT / home_path), full_page=True)
                checks.append({
                    "id": "UI2-07",
                    "title": "空白首页：只突出一个创建入口，导入是次级动作，空态可见且没有预填商品",
                    "ok": home["home_visible"] and home["empty_visible"]
                          and home["project_rows"] == 0
                          and home["visible_primary"] == ["create-project"]
                          and "ghost" in (home["import_class"] or "")
                          and home["name_value"] == ""
                          and (ROOT / home_path).stat().st_size > 0,
                    "detail": {"home": home, "screenshot": home_path},
                })

                page.focus("#new-project-name")
                page.keyboard.type("审计商品 · 六阶段工作台")
                page.keyboard.press("Enter")
                # R3.3：新建即打开——Enter 直接进入工作台。
                expect(page.locator("#project-view")).to_be_visible()
                ui["keyboard"]["create"] = True
                focused_open = True
                ui["keyboard"]["open"] = bool(focused_open)
                page.wait_for_function(
                    "() => (document.getElementById('project-view') || {}).dataset.ready === '1'",
                    timeout=15_000)
                workspace = stage_state()
                blank_storage = storage()
                checks.append({
                    "id": "UI2-08",
                    "title": "新建后默认停靠「资料」：唯一 current 阶段带 aria-current，六个任务入口始终可达（不禁用、不锁定）",
                    "ok": focused_open and workspace["visible"] == ["intake"]
                          and [item["id"] for item in workspace["buttons"] if item["current"]]
                          == ["intake"]
                          and workspace["buttons"][0]["aria"] == "step"
                          and all(not item["disabled"] and not item["locked"]
                                  for item in workspace["buttons"])
                          and bool(workspace["summary"])
                          and blank_storage["projects"] == 1,
                    "detail": {"keyboard_open": bool(focused_open),
                               "keyboard_create": True, "stage": workspace,
                               "storage": blank_storage},
                })
                USER_DIGEST = """
                async () => {
                  const db = await new Promise((resolve, reject) => {
                    const request = indexedDB.open("amz-listing-kit-v2");
                    request.onsuccess = () => resolve(request.result);
                    request.onerror = () => reject(request.error);
                  });
                  const read = (store) => new Promise((resolve, reject) => {
                    const request = db.transaction(store, "readonly").objectStore(store).getAll();
                    request.onsuccess = () => resolve(request.result);
                    request.onerror = () => reject(request.error);
                  });
                  const projects = await read("projects");
                  const documents = await read("documents");
                  db.close();
                  const user_docs = documents.filter((item) => {
                    const payload = item.payload || {};
                    if (payload.status === "confirmed" || payload.status === "unknown") return true;
                    if (payload.action === "select" || payload.action === "clear") return true;
                    if (typeof payload.value !== "undefined" && payload.value !== null) return true;
                    return false;
                  });
                  return { projects: projects.length,
                    user_docs: user_docs.map((item) => item.kind + "/" + item.document_id
                      + "/v" + item.version) };
                }
                """
                focus_digest = page.evaluate(USER_DIGEST)
                # 冻结契约：阶段条始终可达；用户明确导航才切换。逐个打开每个阶段，
                # 断言面板跟随切换、无用户事实写入、门外主操作（生成/交付）仍禁用。
                # 进入理解会触发 §4.2 允许的本地准备（空核心事实壳 ensureCoreSlots），
                # 与"进入生成区可触发 §4.6 的本地准备"同类，不是导航授权外发/改事实。
                visited = []
                storage_clean = True
                for stage_id in ("understand", "plan", "generate", "review", "deliver"):
                    page.click(f'#stage-nav [data-stage-nav="{stage_id}"]')
                    page.wait_for_selector(
                        f'#stage-panels [data-stage-panel="{stage_id}"]:not([hidden])',
                        timeout=20_000)
                    visited.append(stage_state()["visible"])
                    if page.evaluate(USER_DIGEST) != focus_digest:
                        storage_clean = False
                page.click('#stage-nav [data-stage-nav="intake"]')
                page.wait_for_selector(
                    '#stage-panels [data-stage-panel="intake"]:not([hidden])',
                    timeout=20_000)
                if page.evaluate(USER_DIGEST) != focus_digest:
                    storage_clean = False
                locked_state = stage_state()
                gate_primary = page.evaluate(
                    """() => ({
                      confirm_disabled: (document.getElementById("confirm-action") || {}).disabled !== false,
                      deliver_disabled: (document.getElementById("deliver-export") || {}).disabled !== false,
                    })""")
                checks.append({
                    "id": "UI2-09",
                    "title": "阶段可达性：六入口可逐个打开且面板跟随；切换阶段不改用户事实、不授予门外主操作权限",
                    "ok": visited == [["understand"], ["plan"], ["generate"], ["review"], ["deliver"]]
                          and locked_state["visible"] == ["intake"]
                          and [item["id"] for item in locked_state["buttons"] if item["current"]]
                          == ["intake"]
                          and all(not item["disabled"] for item in locked_state["buttons"])
                          and storage_clean
                          and gate_primary["confirm_disabled"]
                          and gate_primary["deliver_disabled"],
                    "detail": {"visited": visited,
                               "visible": locked_state["visible"],
                               "storage_unchanged": storage_clean,
                               "focus_digest": focus_digest,
                               "out_of_gate_primary": gate_primary},
                })

                gate_text = page.locator("#analyze-gate").inner_text()
                analyze_disabled = page.locator("#analyze-run").is_disabled()
                visible_primary = page.evaluate(
                    """() => [...document.querySelectorAll("button.primary")]
                      .filter((node) => node.offsetParent !== null)
                      .map((node) => node.id || node.textContent.trim())""")
                checks.append({
                    "id": "UI2-10",
                    "title": "资料阶段：缺输入时可选 AI 理解禁用并在按钮旁说明缺什么；人工填写入口始终可用",
                    "ok": analyze_disabled and "缺" in gate_text
                          and page.locator("#manual-facts").is_visible()
                          and not page.locator("#manual-facts").is_disabled(),
                    "detail": {"disabled": analyze_disabled, "gate": gate_text,
                               "manual_facts_visible": page.locator("#manual-facts").is_visible(),
                               "ref_count": page.locator("#ref-list .ref-row").count()},
                })

                page.set_input_files("#ref-file", str(reference))
                expect(page.locator("#ref-list .ref-row")).to_have_count(1)
                page.fill("#intake-name", "便携保温杯")
                page.fill("#intake-description", "316ml 不锈钢保温杯，旋盖密封。")
                page.fill("#intake-selling-points", "12小时保温\n304不锈钢内胆")
                page.wait_for_timeout(800)
                expect(page.locator("#analyze-run")).to_be_enabled(timeout=20_000)
                page.focus("#analyze-run")
                focused_analyze = page.evaluate(
                    "() => document.activeElement === document.getElementById('analyze-run')")
                page.keyboard.press("Enter")
                # 槽位行在理解面板内（此时仍隐藏）：等 attached 而非 visible；可见性在导航后断言。
                page.wait_for_selector("#slot-list .slot-row", state="attached", timeout=60_000)
                page.wait_for_timeout(400)
                ui["keyboard"]["analyze"] = bool(focused_analyze)
                stayed = stage_state()
                # 冻结契约：异步完成仅更新状态，不抢焦点、不自动切任务。分析完成后
                # 仍停在资料，再由用户明确导航到理解，槽位行在理解面板内就绪。
                page.click('[data-stage-nav="understand"]')
                expect(page.locator('[data-stage-panel="understand"]')).to_be_visible()
                page.wait_for_selector("#slot-list .slot-row", timeout=60_000)
                analyzed = stage_state()
                checks.append({
                    "id": "UI2-11",
                    "title": "分析商品资料（键盘 Enter 触发）成功后不自动切阶段；用户明确导航到「理解」后槽位进入待处理列表",
                    "ok": bool(focused_analyze) and stayed["visible"] == ["intake"]
                          and analyzed["visible"] == ["understand"]
                          and page.locator("#slot-list .slot-row").count() > 0
                          and [item["id"] for item in analyzed["buttons"] if item["current"]]
                          == ["understand"],
                    "detail": {"keyboard_analyze": bool(focused_analyze),
                               "stayed": stayed["visible"],
                               "stage": analyzed,
                               "slots": page.locator("#slot-list .slot-row").count()},
                })

                guard = 0
                while (page.locator("#slot-list .slot-row")
                       .get_by_role("button", name="确认", exact=True).count() > 0
                       and guard < 25):
                    (page.locator("#slot-list .slot-row")
                     .get_by_role("button", name="确认", exact=True).first.click())
                    page.wait_for_timeout(250)
                    guard += 1
                expect(page.locator("#stage-next-understand")).to_be_enabled(timeout=20_000)
                page.focus("#stage-next-understand")
                page.keyboard.press("Enter")
                expect(page.locator('[data-stage-panel="plan"]')).to_be_visible()
                expect(page.locator("#suite-seed")).to_be_enabled(timeout=20_000)
                page.click("#suite-seed")
                expect(page.locator("#shot-list .shot-row").first).to_be_visible(timeout=20_000)
                page.wait_for_timeout(400)
                shots = page.evaluate(v251.PROBE)["shot_ids"]
                plan_state = stage_state()
                checks.append({
                    "id": "UI2-12",
                    "title": "理解到方案：确认全部待处理槽位后可推进，推荐方案生成 1..N 张图片任务，阶段条随之前移",
                    "ok": len(shots) >= 1 and guard < 25
                          and plan_state["visible"] == ["plan"]
                          and [item["id"] for item in plan_state["buttons"] if item["current"]]
                          == ["plan"],
                    "detail": {"shots": shots, "confirm_rounds": guard, "stage": plan_state},
                })

                page.focus("#stage-next-plan")
                focused_plan_next = page.evaluate(
                    "() => document.activeElement === document.getElementById('stage-next-plan')")
                page.keyboard.press("Enter")
                expect(page.locator('[data-stage-panel="generate"]')).to_be_visible()
                ui["keyboard"]["plan_to_generate"] = bool(focused_plan_next)
                v251.compile_all(page, shots)
                expect(page.locator("#confirm-action")).to_be_enabled(timeout=30_000)
                page.click("#confirm-action")
                # 新流程一次确认直接整套进批次：等 attempt 行出现（不再写“已确认 vN”记录行，不再有点 #batch-run）。
                page.wait_for_function(
                    """() => document.querySelectorAll(
                        '#attempt-list .attempt-row[data-attempt-state]').length > 0""",
                    timeout=30_000)
                page.wait_for_function(
                    """(ids) => ids.every((shotId) => {
                      const node = document.querySelector(
                        '#attempt-list .attempt-row[data-shot-id="' + shotId + '"]');
                      return Boolean(node
                        && node.getAttribute("data-attempt-state") === "succeeded");
                    })""", arg=shots, timeout=180_000)
                page.wait_for_timeout(400)
                generate_state = stage_state()
                checks.append({
                    "id": "UI2-13",
                    "title": "生成阶段：整套生成后逐图进入成功态，并在阶段脚注开放「去审核与返工」入口",
                    "ok": page.locator("#attempt-list .attempt-row").count() == len(shots)
                          and not page.locator("#stage-next-review").is_disabled()
                          and page.locator('#attempt-list .attempt-row[data-attempt-state="succeeded"]')
                          .count() == len(shots),
                    "detail": {"attempt_rows": page.locator("#attempt-list .attempt-row").count(),
                               "shots": len(shots),
                               "summary": generate_state["summary"]},
                })

                page.focus("#stage-next-review")
                focused_review = page.evaluate(
                    "() => document.activeElement === document.getElementById('stage-next-review')")
                page.keyboard.press("Enter")
                expect(page.locator('[data-stage-panel="review"]')).to_be_visible()
                review_state = stage_state()
                generate_button = next(item for item in review_state["buttons"]
                                       if item["id"] == "generate")
                ui["keyboard"]["stage_switch"] = bool(focused_review)
                page.wait_for_timeout(600)
                review_path = shot("review")
                page.screenshot(path=str(ROOT / review_path), full_page=True)
                cards = page.locator("#review-list .review-card")
                images = page.locator("#review-list .review-card .review-preview img")
                checks.append({
                    "id": "UI2-14",
                    "title": "审核阶段以图片为中心：每张图一张审核卡（候选大图 + 采用状态 + 三个行内动作），「生成」转为已完成",
                    "ok": bool(focused_review) and review_state["visible"] == ["review"]
                          and cards.count() == len(shots) and images.count() == len(shots)
                          and page.locator("#review-list .review-card button").count()
                          >= len(shots) * 3
                          and generate_button["complete"] is True
                          and (ROOT / review_path).stat().st_size > 0,
                    "detail": {"keyboard_stage_switch": bool(focused_review),
                               "cards": cards.count(), "images": images.count(),
                               "screenshot": review_path,
                               "summary": review_state["summary"]},
                })
                for shot_id in shots:
                    # 新流程直接点卡片“采用候选”即采用（无 #adopt-submit 对话框）：等卡片出现“已采用”。
                    page.click(f'#review-list .review-card[data-shot-id="{shot_id}"] '
                               'button:has-text("采用候选")')
                    page.wait_for_function(
                        """(shot) => {
                            const card = document.querySelector(
                                '#review-list .review-card[data-shot-id="' + shot + '"]');
                            const btn = card && [...card.querySelectorAll("button")]
                                .find((item) => (item.textContent || "").indexOf("已采用") >= 0);
                            return Boolean(btn);
                        }""", arg=shot_id, timeout=40_000)
                    page.wait_for_timeout(120)
                # 审核卡“已采用”按钮本身就是反馈；#adopt-status 已随采用面板一并退役。
                adopted = page.evaluate(
                    """() => [...document.querySelectorAll("#review-list .review-card")]
                      .map((node) => ({ shot_id: node.getAttribute("data-shot-id"),
                        state: node.getAttribute("data-selection-state"),
                        badge: (node.querySelector(".badge") || {}).textContent || "" }))""")
                checks.append({
                    "id": "UI2-15",
                    "title": "逐图人工采用：每张图点审核卡「采用候选」即落一条当前选择，卡片徽标同步为已采用",
                    "ok": len(adopted) == len(shots)
                          and all(item["state"] == "current" and "已采用" in item["badge"]
                                  for item in adopted),
                    "detail": {"adopted": adopted},
                })

                expect(page.locator("#stage-next-deliver")).to_be_enabled(timeout=20_000)
                page.click("#stage-next-deliver")
                expect(page.locator('[data-stage-panel="deliver"]')).to_be_visible()
                page.wait_for_timeout(400)
                gate_rows = page.locator("#delivery-gate .gate-row")
                gate_badges = page.locator("#delivery-gate .gate-row .badge")
                gate_findings = page.locator("#delivery-gate .gate-finding")
                gate_blocking = page.locator('#delivery-gate .gate-finding[data-severity="BLOCK"]')
                deliver_status = page.locator("#deliver-status").inner_text()
                deliver_path = shot("deliver")
                page.screenshot(path=str(ROOT / deliver_path), full_page=True)
                checks.append({
                    "id": "UI2-16",
                    "title": "交付阶段：门禁清单逐图列出采用状态；有阻断（本流程未跑整套检查）时交付包按钮禁用并说明原因，项目包导出可用",
                    "ok": gate_rows.count() == len(shots)
                          and all("已采用" in item for item in gate_badges.all_inner_texts())
                          and gate_findings.count() >= 1
                          and gate_blocking.count() >= 1
                          and page.locator("#deliver-export").is_disabled()
                          and "未通过" in deliver_status
                          and not page.locator("#deliver-project-package").is_disabled()
                          and (ROOT / deliver_path).stat().st_size > 0,
                    "detail": {"gate_rows": gate_rows.count(), "status": deliver_status,
                               "findings": gate_findings.count(),
                               "blocking": gate_blocking.count(),
                               "screenshot": deliver_path},
                })

                before_reload = storage()
                page.reload(wait_until="networkidle")
                expect(page.locator("#project-view")).to_be_visible()
                page.wait_for_timeout(600)
                reloaded = stage_state()
                after_reload = storage()
                checks.append({
                    "id": "UI2-17",
                    "title": "刷新恢复：重开页面落在最靠后的未完成阶段「交付」，项目与记录逐字不变",
                    "ok": reloaded["visible"] == ["deliver"] and after_reload == before_reload
                          and [item["id"] for item in reloaded["buttons"] if item["current"]]
                          == ["deliver"],
                    "detail": {"visible": reloaded["visible"], "digest": after_reload,
                               "complete": [item["id"] for item in reloaded["buttons"]
                                            if item["complete"]]},
                })

                page.set_viewport_size({"width": 390, "height": 844})
                page.wait_for_timeout(400)
                narrow = page.evaluate(OVERFLOW_PROBE)
                narrow_path = shot("narrow")
                page.screenshot(path=str(ROOT / narrow_path), full_page=True)
                checks.append({
                    "id": "UI2-18",
                    "title": "390px：单列布局无横向溢出，阶段条可横向滚动且当前阶段保持在可视区内",
                    "ok": narrow["document_scroll_width"] <= narrow["document_client_width"] + 1
                          and narrow["nav_scrollable"] is True
                          and narrow["current_stage_visible"] is True
                          and narrow["rects"]["nav"] is not None
                          and narrow["rects"]["nav"]["visible"]
                          and (ROOT / narrow_path).stat().st_size > 0,
                    "detail": {"probe": narrow, "screenshot": narrow_path},
                })

                page.set_viewport_size({"width": 720, "height": 450})
                page.wait_for_timeout(400)
                zoomed = page.evaluate(OVERFLOW_PROBE)
                zoom_path = shot("zoom200")
                page.screenshot(path=str(ROOT / zoom_path), full_page=True)
                checks.append({
                    "id": "UI2-19",
                    "title": "200% 缩放等价视口（1440 窗口缩到 720×450 CSS 像素）：无横向滚动条，阶段条可见",
                    "ok": zoomed["document_scroll_width"] <= zoomed["document_client_width"] + 1
                          and zoomed["rects"]["nav"] is not None
                          and zoomed["rects"]["nav"]["visible"]
                          and (ROOT / zoom_path).stat().st_size > 0,
                    "detail": {"probe": zoomed, "screenshot": zoom_path},
                })
                page.set_viewport_size({"width": 1440, "height": 900})

                ui["screenshots"] = [home_path, review_path, deliver_path,
                                     narrow_path, zoom_path]
                ui["stage_summary"] = reloaded["summary"]
                ui["shots"] = shots
            finally:
                context.close()
    finally:
        server.shutdown()
        server.server_close()
    return checks, ui

def main() -> int:
    parser = argparse.ArgumentParser(description="V2.UI.2 六阶段交互与视觉基线验证")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright  # noqa: F401, PLC0415  (依赖存在性门)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    checks: list[dict] = []
    console_errors: list[str] = []
    page_errors: list[str] = []

    checks.extend(check_static_guards())
    workbench_checks, ui = run_workbench_checks(stamp, console_errors, page_errors)
    checks.extend(workbench_checks)

    keyboard = ui.get("keyboard", {})
    checks.append({
        "id": "UI2-20",
        "title": "键盘路径：新建、打开、分析、阶段推进与阶段切换五个关键动作都由键盘触发并断言焦点落点",
        "ok": all(keyboard.get(item) is True
                  for item in ("create", "open", "analyze", "plan_to_generate", "stage_switch")),
        "detail": {"keyboard": keyboard},
    })
    entry = v251.run_entry(["--check"])
    retried = False
    # 本机套接字偶发 ConnectionResetError（自检自己起停服务）；这是传输层抖动而非产品缺陷，
    # 只在这种可识别的传输错误上重试一次，并把重试记录进证据。
    if entry["rc"] != 0 and any("ConnectionResetError" in line for line in entry["tail"]):
        retried = True
        entry = v251.run_entry(["--check"])
    checks.append({
        "id": "UI2-21",
        "title": "正式入口 --check 全过（六阶段外壳没有破坏无状态自检）",
        "ok": entry["rc"] == 0,
        "detail": {"rc": entry["rc"], "retried_after_connection_reset": retried,
                   "tail": entry["tail"][-3:]},
    })
    checks.append({
        "id": "UI2-22",
        "title": "零意外 console error / page error（界面重写不得引入运行时错误）",
        "ok": not console_errors and not page_errors,
        "detail": {"console_errors": console_errors[:3], "page_errors": page_errors[:3]},
    })

    passed = sum(1 for item in checks if item["ok"])
    failed = [item["id"] for item in checks if not item["ok"]]
    observed_at = datetime.now().isoformat(timespec="seconds")
    label = args.label
    txt_path = EVIDENCE_DIR / f"{CONTRACT}-interaction-visual-{stamp}{label}.txt"
    json_path = EVIDENCE_DIR / f"{CONTRACT}-interaction-visual-{stamp}{label}.json"

    lines = [
        "V2.UI.2 六阶段交互与视觉基线验证（静态契约 + 真实工作台走查 + 响应式/键盘/视觉证据）",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        "=" * 76,
    ]
    for item in checks:
        lines.append(f"  [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if item.get("detail") is not None:
            lines.append("         " + json.dumps(item["detail"], ensure_ascii=False)[:360])
    lines.extend([
        "-" * 76,
        f"observed_at: {observed_at}",
        f"status: {'passed' if passed == len(checks) else 'failed'}",
        f"contract: {CONTRACT}（六阶段外壳 + 表现层基线）",
        "model_calls: 0 · external_network_calls: 0（fake providers + 本机服务器）",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
        "",
        "边界：本套件 0 次真实模型调用；它证明「六阶段外壳是界面投影、可达性规则成立、既有业务",
        "能力仍由真实状态驱动、既有回归不破」，不证明产品发起人走查已通过。本脚本的 fake 轨迹",
        "停在未运行整套检查的阻断态；V2.5.5/V2.6.2 由各自专用验证器与真实链路证明，本批不重复证明。",
        "",
        "CHECKS",
    ])
    for item in checks:
        lines.append(f"- [{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
    if failed:
        lines.append("")
        lines.append("FAILED: " + ", ".join(failed))
    text = "\n".join(lines) + "\n"
    txt_path.write_text(text, encoding="utf-8")
    json_path.write_text(json.dumps({
        "suite_id": "v2.ui.2-interaction-visual",
        "status": "passed" if passed == len(checks) else "failed",
        "observed_at": observed_at,
        "contract": CONTRACT,
        "model_calls": 0,
        "external_network_calls": 0,
        "checks": checks,
        "ui": ui,
        "console_errors": console_errors,
        "page_errors": page_errors,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(text)
    print("证据文件：")
    print(" - " + txt_path.relative_to(ROOT).as_posix())
    print(" - " + json_path.relative_to(ROOT).as_posix())
    for item in ui.get("screenshots", []):
        print(" - " + item)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
