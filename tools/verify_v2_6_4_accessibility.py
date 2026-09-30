"""V2.6.4 渐进披露、空/忙/错/Unknown 与可访问性终验（fake provider；0 次真实模型调用）。

检查：
  A) 静态：ESM 语法门；技术详情落点（#rework-tech / #adopt-tech / techDetails 使用点 / CSS）；
     axe-core vendor 文件完整性（sha256 与许可证在仓库里可验证）。
  B) 浏览器（真实 Chromium + 正式入口 + fake provider）：
     - 空白首页 axe WCAG A/AA 扫描 0 violations；键盘 Tab 序列可达主操作且焦点可见；
     - 纯键盘创建项目（Tab + 输入 + Enter）；
     - 生成阶段：空态（尚未生成）→ 忙态（整套生成中）→ 终态；
     - 技术详情默认收起：attempt 行 / compare 卡片 / 交付结果，主行不含 sha256/action/task；
     - 审核与交付阶段 axe 扫描 0 violations；可见按钮都有可访问名；
     - 交付阶段（含交付包）后 390px 与 200% 等效视口无横向溢出、当前阶段可见；
     - 演练：成功/失败/Unknown 三态可见且每态有下一步动作（重试 / 新建 action），不自动重提；
     - 主链零意外 console / page / HTTP 错误。

边界：fake provider + 本机服务器；不证明真实模型质量。axe 扫描覆盖 WCAG 2.0/2.1 A/AA 规则集的
自动化可检出子集，不替代人工走查（产品发起人 / 陌生人走查仍是发布前人工门）。

运行：
  uv run --locked python tools/verify_v2_6_4_accessibility.py --label final
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCT_DIR = ROOT / "app" / "product_v2"
EVIDENCE_DIR = ROOT / "evals" / "product-v2"
EVIDENCE_IMAGE_DIR = EVIDENCE_DIR / "evidence"
AXE_PATH = EVIDENCE_DIR / "vendor" / "axe-core.min.js"
AXE_LICENSE = EVIDENCE_DIR / "vendor" / "axe-core.LICENSE.txt"

# 与 docs/product-v2-project-context.md §4.2 vendor 登记逐字一致（漂移即红）。
AXE_SHA256 = "C24F097BD2F451D4F933E8BC7D8D539F8672A2EBCB5CC9F9F3EEC8CA9470A0C1"
AXE_LICENSE_SHA256 = "AF175B9D96EE93C21A036152E1B905B0B95304D4AE8C2C921C7609100BA8DF7E"
AXE_BYTES = 580491


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


server_module = load_module(ROOT / "app" / "product_v2_server.py", "v264_server")
ui3 = load_module(ROOT / "tools" / "verify_v2_ui_3_frontend.py", "v264_ui3")
v262 = load_module(ROOT / "tools" / "verify_v2_6_2_delivery.py", "v264_v262")

INDEX_HTML = (PRODUCT_DIR / "index.html").read_text(encoding="utf-8")
WORKSPACE_JS = (PRODUCT_DIR / "workspace.js").read_text(encoding="utf-8")
STYLES_CSS = (PRODUCT_DIR / "styles.css").read_text(encoding="utf-8")
CONTEXT_MD = (ROOT / "docs" / "product-v2-project-context.md").read_text(encoding="utf-8")

AXE_RUN = """async () => {
  const result = await axe.run(document, {
    resultTypes: ['violations'],
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
  });
  return result.violations.map((item) => ({
    id: item.id, impact: item.impact, help: item.help,
    nodes: item.nodes.slice(0, 3).map((node) => ({
      target: node.target, html: String(node.html).slice(0, 110) })),
  }));
}"""

FOCUS_STYLE = """() => {
  const el = document.activeElement;
  if (!el) return null;
  const style = getComputedStyle(el);
  return {
    id: el.id || null,
    tag: el.tagName,
    action: el.getAttribute ? el.getAttribute('data-action') : null,
    text: (el.textContent || '').trim().slice(0, 30),
    outline: style.outlineStyle + ' ' + style.outlineWidth,
    visible: (style.outlineStyle !== 'none' && style.outlineWidth !== '0px')
      || style.boxShadow !== 'none',
  };
}"""

BUTTON_NAMES = """(scope) => {
  const host = document.querySelector(scope) || document;
  const buttons = [...host.querySelectorAll('button')]
    .filter((node) => node.offsetParent !== null);
  const unnamed = buttons.filter((node) => !((node.textContent || '').trim()
    || node.getAttribute('aria-label') || node.getAttribute('title'))).length;
  return { total: buttons.length, unnamed: unnamed };
}"""

TECH_PROBE = """(scope) => {
  const host = document.querySelector(scope);
  if (!host) return null;
  const nodes = [...host.querySelectorAll('.tech-details')];
  const clone = host.cloneNode(true);
  clone.querySelectorAll('details').forEach((node) => node.remove());
  return {
    total: nodes.length,
    open: nodes.filter((node) => node.open).length,
    summaries: nodes.map((node) => (node.querySelector('summary') || {}).textContent || ''),
    main_text: clone.textContent,
  };
}"""

BATCH_STATE = """() => ({
  run_disabled: (document.getElementById('batch-run') || {}).disabled === true,
  stop_visible: (() => {
    const node = document.getElementById('batch-stop');
    if (!node || node.hidden) return false;
    return node.offsetParent !== null;
  })(),
  progress: (document.getElementById('batch-progress') || {}).textContent || '',
})"""

EMPTY_STATE = """() => {
  const rows = [...document.querySelectorAll('#attempt-list .attempt-row')];
  return {
    rows: rows.length,
    missing: rows.filter((row) =>
      row.getAttribute('data-attempt-state') === 'none').length,
    badge: rows.length ? (rows[0].querySelector('.badge') || {}).textContent || '' : '',
  };
}"""

# V2.6.5 回归：窄格里的「技术详情」摘要被挤成一列一个字时，既不溢出、也不违反
# 对比度 —— a11y 扫描与 390px 溢出检查都测不到，只有量它的盒子才知道。
# 判据：可见摘要的宽度够 4 个字（≥40px）、且只占 1–2 行。
TECH_SQUEEZE = """() => {
  const out = [];
  for (const sum of document.querySelectorAll('.tech-details > summary')) {
    const box = sum.getBoundingClientRect();
    if (box.width === 0 && box.height === 0) continue;   // 隐藏阶段的摘要不计
    const line = parseFloat(getComputedStyle(sum).lineHeight) || 16;
    out.push({
      text: (sum.textContent || '').trim().slice(0, 8),
      width: Math.round(box.width), height: Math.round(box.height),
      lines: Math.round(box.height / line),
    });
  }
  return out;
}"""



def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def start_server(host: str, port: int, *, image_factory=None):
    """正式入口 + fake provider（含整套复核），与 V2.6.2 走查同一装配。"""
    suite = v262.fake_suite.FakeSuiteReviewProvider(scenario="drift")
    server = server_module.create_product_v2_server(
        host, port,
        provider_factory=lambda: v262.fake_semantic.FakeSemanticProvider(scenario="ok"),
        image_provider_factory=(image_factory
                                or (lambda: v262.fake_image.FakeImageProvider(scenario="ok", size=1200))),
        review_provider_factory=lambda: v262.fake_review.FakeReviewProvider(scenario="ok"),
        suite_review_provider_factory=lambda: suite)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, suite


def ensure_axe(page) -> None:
    injected = page.evaluate("() => typeof window.axe !== 'undefined'")
    if not injected:
        page.add_script_tag(path=str(AXE_PATH))


def axe_scan(page) -> list[dict]:
    ensure_axe(page)
    return page.evaluate(AXE_RUN)


def tab_until(page, target_id: str, *, max_steps: int = 18, on_target=None):
    """真实 Tab 序列：返回路径；到达目标时可选执行注入动作。"""
    path = []
    for _ in range(max_steps):
        page.keyboard.press("Tab")
        focus = page.evaluate(FOCUS_STYLE)
        path.append(focus)
        if focus and focus.get("id") == target_id:
            if on_target:
                on_target(page)
            return path, focus
    return path, None


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.6.4 渐进披露与可访问性验收")
    parser.add_argument("--label", default="")
    args = parser.parse_args()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = f"-{args.label}" if args.label else ""
    evidence_txt = EVIDENCE_DIR / f"v2.6.4-a11y-{stamp}{label}.txt"
    evidence_json = EVIDENCE_DIR / f"v2.6.4-a11y-{stamp}{label}.json"
    EVIDENCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    checks: list[dict] = []

    def check(check_id: str, title: str, ok: bool, detail=None) -> None:
        checks.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})
        print(f"  [{'PASS' if ok else 'FAIL'}] {check_id} {title}" + (
            "" if ok else " :: " + json.dumps(detail, ensure_ascii=False, default=str)[:400]))

    screenshots: list[str] = []

    def shot(page, name: str) -> None:
        path = EVIDENCE_IMAGE_DIR / f"v2.6.4-a11y-{stamp}{label}-{name}.png"
        page.screenshot(path=str(path), full_page=True)
        screenshots.append(path.relative_to(ROOT).as_posix())

    # ---------------- 静态门 ----------------
    node_files = ["app/product_v2/workspace.js", "app/product_v2/app.js",
                  "app/product_v2/ui/stage-shell.js"]
    node_results = []
    for relative in node_files:
        completed = subprocess.run(["node", "--check", str(ROOT / relative)],
                                   cwd=str(ROOT), capture_output=True, text=True, check=False)
        node_results.append({"file": relative, "rc": completed.returncode,
                             "stderr": completed.stderr.strip()[-160:]})
    html_ids = re.findall(r'id="([^"]+)"', INDEX_HTML)
    duplicate_ids = sorted({item for item in html_ids if html_ids.count(item) > 1})
    element_keys = re.findall(
        r"^\s*([A-Za-z_$][A-Za-z0-9_$]*):\s*document\.getElementById", WORKSPACE_JS, re.M)
    duplicate_keys = sorted({item for item in element_keys if element_keys.count(item) > 1})
    check("V2.6.4-00", "ESM 语法门与 DOM 身份唯一（无重复 id / 元素键）",
          all(item["rc"] == 0 for item in node_results)
          and not duplicate_ids and not duplicate_keys,
          {"node": node_results, "duplicate_ids": duplicate_ids,
           "duplicate_element_keys": duplicate_keys})

    tech_landed = (
        WORKSPACE_JS.count("techDetails(") >= 9
        and 'id="rework-tech"' in INDEX_HTML and 'id="adopt-tech"' in INDEX_HTML
        and 'id="rework-tech-body"' in INDEX_HTML and 'id="adopt-tech-body"' in INDEX_HTML
        and ".tech-details" in STYLES_CSS and ".tech-details[open]" in STYLES_CSS
        and "const tech = techDetails(techLines)" in WORKSPACE_JS
        and "techDetails(attemptTech)" in WORKSPACE_JS)
    check("V2.6.4-01", "技术详情落点：统一 techDetails + 返工/采用面板 + 样式规则",
          tech_landed, {"techDetails_calls": WORKSPACE_JS.count("techDetails("),
                        "rework_tech": 'id="rework-tech"' in INDEX_HTML,
                        "adopt_tech": 'id="adopt-tech"' in INDEX_HTML,
                        "css": ".tech-details" in STYLES_CSS})

    axe_ok = (AXE_PATH.exists() and AXE_PATH.is_file() and AXE_PATH.stat().st_size == AXE_BYTES
              and sha256_of(AXE_PATH) == AXE_SHA256
              and AXE_LICENSE.exists() and sha256_of(AXE_LICENSE) == AXE_LICENSE_SHA256
              and "axe-core.min.js" in CONTEXT_MD and AXE_SHA256[:16] in CONTEXT_MD)
    check("V2.6.4-02", "axe-core vendor 文件完整性与登记一致（SEL-013）",
          axe_ok, {"exists": AXE_PATH.exists(),
                   "bytes": AXE_PATH.stat().st_size if AXE_PATH.exists() else None,
                   "sha_match": AXE_PATH.exists() and sha256_of(AXE_PATH) == AXE_SHA256,
                   "registry": "axe-core.min.js" in CONTEXT_MD})

    # ---------------- 浏览器主链 ----------------
    from playwright.sync_api import sync_playwright

    temp_root = Path(tempfile.mkdtemp(prefix="amz-v264-"))
    reference = temp_root / "ref.png"
    reference.write_bytes(ui3.v251.png_bytes(900, 900, (36, 92, 160)))

    with sync_playwright() as pw:
        port = v262.free_port()
        server, _suite = start_server("127.0.0.1", port)
        try:
            context = pw.chromium.launch_persistent_context(
                str(temp_root / "profile-main"), headless=True,
                viewport={"width": 1440, "height": 950}, accept_downloads=True)
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(30_000)
            logs = ui3.collect(page)
            try:
                page.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
                page.wait_for_function(
                    "() => { const node = document.getElementById('create-project');"
                    " return node && node.disabled === false; }", timeout=15_000)
                shot(page, "home")
                violations_home = axe_scan(page)
                check("V2.6.4-03", "空白首页 axe（WCAG 2.0/2.1 A/AA）0 violations",
                      violations_home == [], {"violations": violations_home[:5]})

                # 键盘 Tab 序列：主操作可达且焦点可见
                page.evaluate("() => document.body.focus()")
                keyboard_path, focus_ok = tab_until(page, "new-project-name", max_steps=12)
                reached_ids = [item.get("id") for item in keyboard_path if item]
                focus_all_visible = all(item.get("visible") for item in keyboard_path if item)
                check("V2.6.4-04", "空白首页键盘路径：Tab 可达主操作且每步焦点可见",
                      "new-project-name" in reached_ids and focus_all_visible,
                      {"path": reached_ids, "all_visible": focus_all_visible,
                       "focus": focus_ok})

                # 纯键盘创建：输入名称（键盘）→ Tab 到创建 → Enter
                page.keyboard.type("V264 A11y")
                _, create_focus = tab_until(page, "create-project", max_steps=6)
                if create_focus and create_focus.get("visible"):
                    page.keyboard.press("Enter")
                page.wait_for_selector("#project-list .project-row", timeout=15_000)
                open_focus = None
                for _ in range(12):
                    page.keyboard.press("Tab")
                    candidate = page.evaluate(FOCUS_STYLE)
                    if candidate and candidate.get("action") == "open":
                        open_focus = candidate
                        page.keyboard.press("Enter")
                        break
                page.wait_for_selector("#project-view:not([hidden])", timeout=30_000)
                shot(page, "keyboard-created")
                check("V2.6.4-05", "纯键盘创建并打开：Tab + 输入 + Enter 进入工作台",
                      create_focus is not None and create_focus.get("visible") is True
                      and open_focus is not None and open_focus.get("visible") is True,
                      {"create_focus": create_focus, "open_focus": open_focus})

                # 资料 → 分析 → 槽位 → 方案
                ui3.fill_intake(page, reference, "V264 A11y")
                squeeze: dict[str, list] = {}
                squeeze["intake"] = page.evaluate(TECH_SQUEEZE)
                shot(page, "ref-card-1440")
                page.click("#analyze-run")
                page.wait_for_selector("#slot-list .slot-row", timeout=30_000)
                ui3.confirm_slots(page)
                page.click("#stage-next-understand")
                page.click("#suite-seed")
                page.wait_for_selector("#shot-list .shot-row", timeout=20_000)
                page.click("#stage-next-plan")
                shots = page.evaluate(ui3.SHOT_IDS)
                ui3.compile_all(page, shots)
                page.click("#confirm-action")
                page.wait_for_selector("#confirm-record", timeout=15_000)

                # 生成阶段：空态 → 忙态 → 终态
                empty = page.evaluate(EMPTY_STATE)
                page.click("#batch-run")
                page.wait_for_timeout(120)
                busy = page.evaluate(BATCH_STATE)
                shot(page, "busy")
                busy_ok = busy["run_disabled"] or busy["stop_visible"] or "进行中" in busy["progress"]
                ui3.wait_terminal(page, shots, timeout=120_000)
                check("V2.6.4-06", "生成阶段四态之空/忙：未生成可见、整套生成中可观察",
                      empty["rows"] == len(shots) and empty["missing"] == len(shots)
                      and "尚未生成" in empty["badge"] and busy_ok,
                      {"empty": empty, "busy": busy})

                attempt_tech = page.evaluate(TECH_PROBE, "#attempt-list")
                attempt_main = (attempt_tech or {}).get("main_text", "")
                check("V2.6.4-07", "生成阶段技术详情：attempt 行默认收起且主行不含 sha256/action/task",
                      attempt_tech is not None and attempt_tech["total"] >= len(shots)
                      and attempt_tech["open"] == 0
                      and all("技术详情" in item for item in attempt_tech["summaries"])
                      and "sha256" not in attempt_main.lower()
                      and "action " not in attempt_main.lower(),
                      {"total": (attempt_tech or {}).get("total"),
                       "open": (attempt_tech or {}).get("open"),
                       "shots": len(shots),
                       "summaries": sorted(set((attempt_tech or {}).get("summaries") or []))[:6],
                       "has_sha": "sha256" in attempt_main.lower(),
                       "has_action": "action " in attempt_main.lower(),
                       "main_tail": attempt_main[-200:],
                       "main_sample": attempt_main[:160]})

                # 审核阶段：比较面板 → axe → 技术详情 → 采用 → 整套检查
                page.click("#stage-next-review")
                first_shot = shots[0]
                # V2.6.6：审核卡片此前完全没有样式，候选图被渲染成容器全宽
                # （1440px 下一屏只看得见图的左上角）。这里量它是否受限。
                page.wait_for_function(
                    """() => { const img = document.querySelector(
                         '#review-list .review-card .review-preview img');
                       return img && img.src && img.naturalWidth > 0; }""", timeout=15_000)
                review_preview = page.evaluate(
                    """() => { const img = document.querySelector(
                         '#review-list .review-card .review-preview img');
                       const box = img.getBoundingClientRect();
                       return {width: Math.round(box.width), height: Math.round(box.height),
                               natural: img.naturalWidth}; }""")
                check("V2.6.4-17", "审核卡片候选预览受限（宽 ≤460px、高 ≤480px）",
                      bool(review_preview) and review_preview["width"] <= 460
                      and review_preview["height"] <= 480, review_preview)
                page.set_viewport_size({"width": 390, "height": 844})
                page.wait_for_timeout(250)
                review_narrow = page.evaluate(
                    """() => { const img = document.querySelector(
                         '#review-list .review-card .review-preview img');
                       const actions = document.querySelector('#review-list .review-card-actions');
                       const box = img ? img.getBoundingClientRect() : null;
                       return {preview: box ? Math.round(box.width) : null,
                               actions_visible: Boolean(actions && actions.offsetParent !== null),
                               scroll: document.documentElement.scrollWidth,
                               client: document.documentElement.clientWidth}; }""")
                shot(page, "review-390")
                check("V2.6.4-18", "390px 审核卡片：单列回退、预览受限、操作可见、无横向溢出",
                      review_narrow["preview"] is not None and review_narrow["preview"] <= 380
                      and review_narrow["actions_visible"]
                      and review_narrow["scroll"] <= review_narrow["client"] + 1,
                      review_narrow)
                page.set_viewport_size({"width": 1440, "height": 950})
                page.wait_for_timeout(250)
                page.click(f'#review-list .review-card[data-shot-id="{first_shot}"] '
                           'button:has-text("比较候选")')
                page.wait_for_selector("#compare-panel:not([hidden])", timeout=15_000)
                compare_tech = page.evaluate(TECH_PROBE, "#compare-checklist")
                violations_review = axe_scan(page)
                buttons_review = page.evaluate(BUTTON_NAMES, "#compare-panel")
                squeeze["review"] = page.evaluate(TECH_SQUEEZE)
                shot(page, "review")
                check("V2.6.4-08", "审核阶段：axe 0 violations、可见按钮都有可访问名、比较清单技术详情默认收起",
                      violations_review == [] and buttons_review["unnamed"] == 0
                      and compare_tech is not None and compare_tech["total"] >= 1
                      and compare_tech["open"] == 0,
                      {"violations": violations_review[:4], "buttons": buttons_review,
                       "tech": {"total": (compare_tech or {}).get("total"),
                                "open": (compare_tech or {}).get("open")}})

                for shot_id in shots:
                    page.click(f'#review-list .review-card[data-shot-id="{shot_id}"] '
                               'button:has-text("采用候选")')
                    page.wait_for_selector("#adopt-submit:not([disabled])", timeout=15_000)
                    page.click("#adopt-submit")
                    page.wait_for_selector("#adopt-status:not([hidden])", timeout=15_000)
                    page.wait_for_timeout(120)
                adopt_tech = page.evaluate(TECH_PROBE, "#adopt-panel")
                squeeze["review-adopted"] = page.evaluate(TECH_SQUEEZE)
                page.click("#suite-review-run")
                page.wait_for_function(
                    "() => { const node = document.getElementById('suite-review-status');"
                    " return node && node.textContent.indexOf('整套检查 v') >= 0; }",
                    timeout=60_000)

                # 交付阶段：门禁 → 交付包 → 技术详情 → axe
                page.click('[data-stage-nav="deliver"]')
                gate = v262.wait_gate(page)
                v262.download_delivery(page, temp_root / "delivery.zip")
                page.wait_for_timeout(300)
                deliver_tech = page.evaluate(TECH_PROBE, "#delivery-result")
                squeeze["deliver"] = page.evaluate(TECH_SQUEEZE)
                violations_deliver = axe_scan(page)
                buttons_deliver = page.evaluate(BUTTON_NAMES, "#stage-panels")
                shot(page, "deliver")
                check("V2.6.4-09", "交付阶段：axe 0 violations、交付结果技术详情默认收起",
                      violations_deliver == [] and buttons_deliver["unnamed"] == 0
                      and deliver_tech is not None and deliver_tech["total"] >= 1
                      and deliver_tech["open"] == 0
                      and "sha256" not in deliver_tech["main_text"].lower(),
                      {"violations": violations_deliver[:4], "buttons": buttons_deliver,
                       "tech": {"total": (deliver_tech or {}).get("total"),
                                "open": (deliver_tech or {}).get("open")}})
                check("V2.6.4-10", "采用面板技术详情默认收起且主行不含 sha256",
                      adopt_tech is not None and adopt_tech["total"] >= 1
                      and adopt_tech["open"] == 0
                      and "sha256" not in (adopt_tech.get("main_text") or "").lower(),
                      {"tech": adopt_tech})
                flat_tech = [item for items in squeeze.values() for item in items]
                squeezed = [item for item in flat_tech
                            if item["width"] < 40 or item["lines"] > 2]
                check("V2.6.4-16", "技术详情摘要全阶段横排可读（不竖排、不挤压）",
                      bool(flat_tech) and not squeezed,
                      {"checked": len(flat_tech), "stages": sorted(squeeze),
                       "bad": squeezed[:3], "samples": flat_tech[:4]})

                # 390px 与 200% 等效视口
                page.set_viewport_size({"width": 390, "height": 844})
                page.wait_for_timeout(300)
                narrow = page.evaluate(ui3.OVERFLOW_PROBE)
                shot(page, "narrow-390")
                page.set_viewport_size({"width": 720, "height": 450})
                page.wait_for_timeout(300)
                zoom = page.evaluate(ui3.OVERFLOW_PROBE)
                shot(page, "zoom-200")
                check("V2.6.4-11", "390px 与 200% 等效视口：无横向溢出且当前阶段可见",
                      narrow["scroll"] <= narrow["client"] + 1
                      and zoom["scroll"] <= zoom["client"] + 1
                      and narrow["current_visible"] is not False
                      and zoom["current_visible"] is not False,
                      {"narrow": narrow, "zoom": zoom})
                page.set_viewport_size({"width": 1440, "height": 950})

                unexpected = [item for item in logs["http"] if "/favicon.ico" not in item]
                check("V2.6.4-12", "主链零意外 console / page / HTTP 错误",
                      not logs["console"] and not logs["page"] and not unexpected,
                      {"console": logs["console"][:4], "page": logs["page"][:3],
                       "http": unexpected[:4]})
            finally:
                context.close()
        finally:
            server.shutdown()
            server.server_close()

        # ---------------- 演练：成功 / 失败 / Unknown 三态 + 下一步 ----------------
        port2 = v262.free_port()
        drill_image = ui3.walkthrough.WalkthroughImageProvider()
        server2, _ = start_server("127.0.0.1", port2, image_factory=lambda: drill_image)
        try:
            context2 = pw.chromium.launch_persistent_context(
                str(temp_root / "profile-drill"), headless=True,
                viewport={"width": 1440, "height": 950}, accept_downloads=True)
            page2 = context2.pages[0] if context2.pages else context2.new_page()
            page2.set_default_timeout(30_000)
            logs2 = ui3.collect(page2)
            try:
                page2.goto(f"http://127.0.0.1:{port2}/", wait_until="domcontentloaded")
                page2.wait_for_function(
                    "() => { const node = document.getElementById('create-project');"
                    " return node && node.disabled === false; }", timeout=15_000)
                ui3.create_project(page2, "V264 演练品", reference)
                page2.click("#analyze-run")
                page2.wait_for_selector("#slot-list .slot-row", timeout=30_000)
                ui3.confirm_slots(page2)
                page2.click("#stage-next-understand")
                page2.click("#suite-seed")
                page2.wait_for_selector("#shot-list .shot-row", timeout=20_000)
                guard = 0
                while len(page2.evaluate(ui3.SHOT_IDS)) > 3 and guard < 10:
                    ids = page2.evaluate(ui3.SHOT_IDS)
                    page2.click(f'#shot-list .shot-row[data-shot-id="{ids[-1]}"] '
                                'button:has-text("删除")')
                    page2.wait_for_timeout(250)
                    guard += 1
                page2.click("#stage-next-plan")
                drill_ids = page2.evaluate(ui3.SHOT_IDS)
                ui3.compile_all(page2, drill_ids)
                page2.click("#confirm-action")
                page2.wait_for_selector("#confirm-record", timeout=15_000)
                page2.click("#batch-run")
                ui3.wait_terminal(page2, drill_ids, timeout=120_000)
                page2.wait_for_timeout(4000)
                states = page2.evaluate("""() => Object.fromEntries(
                  [...document.querySelectorAll('#attempt-list .attempt-row')]
                    .map((row) => [row.getAttribute('data-shot-id'),
                                   row.getAttribute('data-attempt-state')]))""")
                failed_button = page2.locator(
                    '#attempt-list .attempt-row[data-attempt-state="failed"] '
                    'button:has-text("重试（新建 action）")').count()
                unknown_button = page2.locator(
                    '#attempt-list .attempt-row[data-attempt-state="unknown"] '
                    'button:has-text("新建 action（放弃核对）")').count()
                page2.wait_for_timeout(2500)
                rows_after = page2.locator("#attempt-list .attempt-row").count()
                shot(page2, "drill")
                check("V2.6.4-13", "演练三态：成功/失败/Unknown 可见且各有下一步动作，不自动重提",
                      set(states.values()) == {"succeeded", "failed", "unknown"}
                      and failed_button == 1 and unknown_button == 1
                      and rows_after == len(drill_ids),
                      {"states": states, "failed_button": failed_button,
                       "unknown_button": unknown_button, "rows": rows_after})
                # 演练剧本本身要制造一次明确失败（第 2 张的 submit 走 504 网关错误），
                # 因此这里只允许该预期条目；其它 console/page/http 错误仍算红。
                expected_console = [item for item in logs2["console"] if "504" in item]
                unexpected2 = [item for item in logs2["http"]
                               if "/favicon.ico" not in item
                               and not item.startswith("504 /api/v2/images/submit")
                               and "/api/v2/images/submit" not in item]
                console_unexpected = [item for item in logs2["console"]
                                      if item not in expected_console]
                check("V2.6.4-14", "演练链：除剧本内的 504 明确失败外无意外 console / page / HTTP 错误",
                      not console_unexpected and not logs2["page"] and not unexpected2
                      and len(expected_console) <= 2,
                      {"console": logs2["console"][:4], "page": logs2["page"][:3],
                       "http": logs2["http"][:4]})
            finally:
                context2.close()
        finally:
            server2.shutdown()
            server2.server_close()

    completed = subprocess.run([sys.executable, "app/server.py", "--check"], cwd=str(ROOT),
                               capture_output=True, text=True, check=False, encoding="utf-8",
                               errors="replace")
    tail = (completed.stdout or "").strip().splitlines()[-3:]
    check("V2.6.4-15", "正式入口自检全过",
          completed.returncode == 0, {"rc": completed.returncode, "tail": tail})

    passed = sum(1 for item in checks if item["ok"])
    lines = [f"V2.6.4 渐进披露与可访问性终验 · {stamp}{label}",
             f"结果：{passed}/{len(checks)} 通过", ""]
    for item in checks:
        lines.append(f"[{'PASS' if item['ok'] else 'FAIL'}] {item['id']} {item['title']}")
        if item["detail"] is not None:
            lines.append("       " + json.dumps(item["detail"], ensure_ascii=False, default=str)[:600])
    lines += ["", "SCREENSHOTS", *[f"- {path}" for path in screenshots]]
    evidence_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    evidence_json.write_text(json.dumps(
        {"stamp": stamp, "label": args.label, "checks": checks, "screenshots": screenshots},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(lines[-6:]))
    print(f"证据：{evidence_txt.relative_to(ROOT).as_posix()}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
