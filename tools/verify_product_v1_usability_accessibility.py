#!/usr/bin/env python
"""D4.2 可用性与可访问性收敛：浏览器验证脚本。

五组检查（都跑在真实产品服务端代码路径上，服务固定起在 8791）：
  1. 空白形态：Tab 可走到全部可见控件、焦点可见、label/错误关联可查；
  2. 有数据形态：loading / empty / error / disabled 状态存在且有文字或 aria，不只靠颜色；
  3. 390px 视口：document.documentElement.scrollWidth <= innerWidth + 1；
  4. 200% 缩放：主流程按钮仍可见可点、无横向溢出；
  5. 键盘：只用 Tab 走到「开始生成」并用 Enter 触发，另用 Space 触发一次真实动作。

真数据来源：把 _working/amz-listing-kit-product-demo/real-ui-run-05/workspace 复制到临时目录
再打开；脚本结束前后对比原目录全部文件的 sha256，证明真实工作空间只读。
不调用真实模型：图片生成走注入的假 provider（provider/model 身份与注册表一致），
它只用来验证「键盘能触发」与「loading 状态可见」，不作为真实生成证据。

ZOOM_LIMITATION（200% 缩放的模拟局限，写在代码里以便复核）：
  200% 缩放用等价 CSS 视口模拟：1440x1000 的窗口换成 720x500 的 CSS 视口，得到与 200%
  缩放相同的布局宽度。真实浏览器缩放在此之上还会等比放大字号与图片，因此本脚本能证明
  「布局无横向溢出、主流程按钮仍可见可点」，不能证明真实缩放下的字号可读性。

运行：
  & "C:\\Users\\31368\\.local\\bin\\uv.exe" run --no-project --with-requirements requirements.txt --with playwright python tools/verify_product_v1_usability_accessibility.py
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent
for _entry in (str(ROOT), str(TOOLS)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from app.product_v1_server import ProductApplication, create_product_server
from src.application_service import ApplicationService, ImageUpload
from src.console import enable_utf8
from tools.verify_product_v1_plan import require_ok
from tools.verify_product_v1_ui import (
    FakeImageProvider,
    png_1x1,
    png_image,
    semantic_provider_factory,
)

enable_utf8()

EVIDENCE = ROOT / "evals" / "product-demo"
PORT = 8791
SESSION_KEY = "amzListingKit.productV1.workspaceDirectory"
REAL_WORKSPACE = ROOT / "_working" / "amz-listing-kit-product-demo" / "real-ui-run-05" / "workspace"
ZOOM_LIMITATION = (
    "200% 缩放用等价 CSS 视口模拟（1440x1000 -> 720x500）：能覆盖布局溢出与按钮可达性，"
    "不能覆盖真实缩放下的字号放大与图片缩放。"
)

STATE_WORD = re.compile(r"(生成中|已提交|准备提交|正在核对|结果待核对|生成失败|尚未生成|已完成)")


class SlowRegistryImageProvider(FakeImageProvider):
    """注册表里存在的 provider 身份 + 可控延迟，用来观察 loading 状态。

    每次提交返回不同字节：产品会把完全相同的结果判为重复候选而拒绝。
    """

    provider_id = "dashscope-qwen-image"
    model_id = "qwen-image-3.0"
    delay_seconds = 1.2

    def __init__(self) -> None:
        super().__init__()
        self.attempts_seen = 0

    def submit(self, prompt, references, **kwargs):
        self.attempts_seen += 1
        time.sleep(self.delay_seconds)
        task = super().submit(prompt, references, **kwargs)
        for url in task.result_urls:
            self._bytes[url] = png_image(64, 48, (9 + self.attempts_seen, 88, 166))
        return task


HELPERS_JS = r"""
() => {
  const sig = (el) => {
    const s = getComputedStyle(el);
    return [s.outlineStyle, s.outlineWidth, s.outlineColor, s.outlineOffset,
            s.boxShadow, s.borderTopWidth, s.borderTopColor, s.backgroundColor,
            s.color, s.textDecorationLine].join(' | ');
  };
  const describe = (el) => {
    let key = el.tagName.toLowerCase();
    if (el.id) key += '#' + el.id;
    if (el.classList && el.classList.length) {
      key += '.' + Array.from(el.classList).slice(0, 3).join('.');
    }
    const type = el.getAttribute('type');
    if (type) key += ':' + type;
    return key;
  };
  const focusableSelector = 'a[href], button, input, select, textarea, summary, [tabindex]';
  const isVisible = (el) => {
    if (el.closest('[hidden]')) return false;
    if (el.closest('dialog:not([open])')) return false;
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return el.classList.contains('visually-hidden');
    return true;
  };
  const focusable = () => {
    return Array.from(document.querySelectorAll(focusableSelector)).filter((el) => {
      if (el.disabled) return false;
      if (el.getAttribute('type') === 'hidden') return false;
      const tabindex = el.getAttribute('tabindex');
      if (tabindex !== null && Number(tabindex) < 0) return false;
      return isVisible(el);
    }).map((el) => ({ key: describe(el), id: el.id || '' }));
  };
  const compositeSig = (el) => {
    const label = (el.labels && el.labels.length) ? el.labels[0] : null;
    return sig(el) + ' || ' + (label ? sig(label) : '');
  };
  const focusFirst = () => {
    const el = Array.from(document.querySelectorAll(focusableSelector)).find((node) => {
      if (node.disabled) return false;
      if (node.getAttribute('type') === 'hidden') return false;
      const tabindex = node.getAttribute('tabindex');
      if (tabindex !== null && Number(tabindex) < 0) return false;
      return isVisible(node);
    });
    if (!el) return null;
    el.focus();
    return { key: describe(el), id: el.id || '', sig: compositeSig(el) };
  };
  const overflow = () => ({
    scrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
    innerWidth: window.innerWidth,
  });
  const hit = (selector) => {
    const el = document.querySelector(selector);
    if (!el) return { found: false };
    el.scrollIntoView({ block: 'center', inline: 'center' });
    const r = el.getBoundingClientRect();
    const cx = r.left + r.width / 2;
    const cy = r.top + r.height / 2;
    const top = document.elementFromPoint(cx, cy);
    return {
      found: true,
      width: Math.round(r.width),
      height: Math.round(r.height),
      insideViewport: r.left >= -1 && r.right <= window.innerWidth + 1
        && r.top >= -1 && r.bottom <= window.innerHeight + 1,
      hit: Boolean(top) && (top === el || el.contains(top)),
      hitTag: top ? describe(top) : null,
    };
  };
  const disabledReason = (selector) => {
    const el = document.querySelector(selector);
    if (!el) return { found: false };
    if (!el.disabled) return { found: true, disabled: false, reasons: [] };
    const reasons = [];
    const described = (el.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
    for (const target of described) {
      const node = document.getElementById(target);
      if (node && (node.innerText || node.textContent || '').trim()) {
        reasons.push('aria-describedby:' + target);
      }
    }
    if ((el.getAttribute('title') || '').trim()) reasons.push('title');
    const nearby = ['generation-hint', 'selection-hint', 'plan-save-state', 'save-state',
                    'prompt-status', 'prompt-edit-help', 'brief-save-state'];
    for (const id of nearby) {
      const node = document.getElementById(id);
      if (!node || node.hidden || node.closest('[hidden]')) continue;
      const text = (node.innerText || node.textContent || '').trim();
      if (text) reasons.push('visible-text:' + id);
    }
    return { found: true, disabled: true, reasons };
  };
  const labelInfo = (ids) => {
    const out = {};
    for (const id of ids) {
      const el = document.getElementById(id);
      if (!el) { out[id] = { found: false }; continue; }
      const labels = Array.from(el.labels || []).map((node) => (node.innerText || '').trim());
      const describedBy = (el.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean)
        .map((target) => {
          const node = document.getElementById(target);
          return { id: target, exists: Boolean(node),
                   text: node ? (node.innerText || node.textContent || '').trim() : '',
                   live: node ? (node.getAttribute('role') === 'alert'
                                 || Boolean(node.getAttribute('aria-live'))) : false };
        });
      out[id] = {
        found: true,
        labels,
        ariaLabel: el.getAttribute('aria-label') || '',
        placeholder: el.getAttribute('placeholder') || '',
        describedBy,
      };
    }
    return out;
  };
  const errorInfo = (pairs) => pairs.map(([input, error]) => {
    const el = document.getElementById(input);
    const node = document.getElementById(error);
    if (!el || !node) return { input, error, found: false };
    const described = (el.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
    return {
      input,
      error,
      found: true,
      role: node.getAttribute('role') || '',
      referenced: described.includes(error),
    };
  });
  window.__a11y = { sig, compositeSig, describe, focusable, focusFirst, overflow, hit,
                    disabledReason, labelInfo, errorInfo, sigIds: [] };
  return true;
}
"""

STEP_JS = r"""
() => {
  const el = document.activeElement;
  if (!el || el === document.body || el === document.documentElement) return null;
  const id = el.id || '';
  const out = { key: window.__a11y.describe(el), id };
  out.sig = window.__a11y.compositeSig(el);
  return out;
}
"""


def arm(page, sig_ids=()) -> None:
    """(Re)install the helper functions after every navigation."""
    page.evaluate(HELPERS_JS)
    page.evaluate("(ids) => { window.__a11y.sigIds = ids; }", list(sig_ids))


def open_workspace(page, base_url: str, directory: str) -> None:
    page.goto(base_url + "/", wait_until="domcontentloaded")
    # Let the first boot() finish before overwriting sessionStorage. Otherwise boot#1 can
    # read the new directory, fail, and clear the key before the reload happens - the
    # reloaded page then sees no directory and never shows the notice.
    page.wait_for_load_state("networkidle", timeout=20000)
    page.evaluate("([key, value]) => sessionStorage.setItem(key, value)", [SESSION_KEY, directory])
    page.reload(wait_until="domcontentloaded")


def walk_tab(page, limit: int = 250, stop_ids=(), collect_sig: bool = False):
    """Focus the first control, then press Tab and record every focus stop.

    The product moves focus to the first field after a workspace opens, so the walk
    always restarts from the first focusable control instead of whatever had focus.
    """
    reached: list[dict] = []
    signatures: dict[str, str] = {}
    first = page.evaluate("() => window.__a11y.focusFirst()")
    if first is None:
        return reached, signatures
    reached.append({"key": first["key"], "id": first["id"]})
    if first.get("sig"):
        signatures[first["id"]] = first["sig"]
    misses = 0
    for _ in range(limit):
        page.keyboard.press("Tab")
        step = page.evaluate(STEP_JS)
        if step is None:
            misses += 1
            if misses >= 3:
                break
            continue
        misses = 0
        if step["key"] == first["key"] and len(reached) > 1:
            if collect_sig and step.get("sig"):
                signatures[step["id"]] = step["sig"]
            break
        reached.append(step)
        if collect_sig and step.get("sig"):
            signatures[step["id"]] = step["sig"]
        if stop_ids and step["id"] in stop_ids:
            break
    return reached, signatures


def baseline_signatures(page, selectors) -> dict:
    return page.evaluate("""(selectors) => {
      const out = {};
      for (const selector of selectors) {
        const el = document.querySelector(selector);
        if (el) out[selector] = window.__a11y.compositeSig(el);
      }
      return out;
    }""", list(selectors))


def tree_hashes(root: Path) -> dict:
    out = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def record(results, check_id: str, title: str, ok: bool, detail) -> None:
    results.append({"id": check_id, "title": title, "ok": bool(ok), "detail": detail})


def build_planned_workspace(directory: Path, provider: SlowRegistryImageProvider) -> dict:
    """A real workspace on disk that has a plan but no candidate yet."""
    service = ApplicationService(
        semantic_provider_factory=semantic_provider_factory,
        image_provider_factory=lambda: provider,
    )
    created = require_ok(service.create_workspace(directory), "create workspace")
    saved = require_ok(service.save_intake(
        directory,
        expected_etag=created["workspace"]["revision"],
        product_name="通勤保温杯",
        description="可重复使用的随行杯，日常通勤场景。",
        selling_points=["单手开盖"],
        user_intent="突出日常通勤，避免户外露营画面。",
        reference_images=[ImageUpload("reference.png", png_1x1(), "primary")],
    ), "save intake")
    draft = require_ok(service.generate_product_brief_draft(
        directory, expected_etag=saved["workspace"]["revision"],
    ), "brief draft")
    brief = require_ok(service.save_product_brief(
        directory, expected_etag=draft["workspace_revision"], fields=draft["product_brief"],
    ), "save brief")
    return require_ok(service.generate_product_plan(
        directory, expected_etag=brief["workspace"]["revision"],
    ), "generate plan")


def start_product(provider: SlowRegistryImageProvider, recent_index: Path, blank_dir: Path):
    service = ApplicationService(
        semantic_provider_factory=semantic_provider_factory,
        image_provider_factory=lambda: provider,
    )
    app = ProductApplication(
        service=service,
        recent_index_path=recent_index,
        folder_picker=lambda _purpose: str(blank_dir),
    )
    httpd = create_product_server("127.0.0.1", PORT, application=app)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, thread


BLANK_SIG_KEYS = ["create-workspace", "open-workspace", "back-home", "reference-images",
                  "product-name", "product-description", "selling-points", "user-intent",
                  "generate-suite"]
HOME_SIG_KEYS = ["create-workspace", "open-workspace"]
INTAKE_SIG_SELECTORS = ["#back-home", "#reference-images", "#product-name", "#product-description",
                        "#selling-points", "#user-intent", "#generate-suite"]
MAIN_FLOW_BUTTONS = ["#generate-from-plan", "#reconcile-generation", "#refresh-generation",
                     "#save-plan", "#export-selection", "#reveal-export",
                     "#save-brief", "#generate-suite", "#preview-plan"]
LIVE_REGIONS = ["app-notice", "generation-status", "selection-status", "save-state",
                "plan-status", "brief-status"]
DISABLED_TARGETS = ["#generate-from-plan", "#save-plan", "#export-selection",
                    "#save-brief", "#save-prompt"]


def create_blank_workspace(directory: Path, provider: SlowRegistryImageProvider) -> None:
    service = ApplicationService(
        semantic_provider_factory=semantic_provider_factory,
        image_provider_factory=lambda: provider,
    )
    require_ok(service.create_workspace(directory), "create blank workspace")


def check_blank(page, base_url: str, results: list, stamp: str) -> None:
    """空白形态：键盘可达、焦点可见、label 与错误关联。"""
    page.goto(base_url + "/", wait_until="domcontentloaded")
    arm(page, BLANK_SIG_KEYS)
    home_baseline = baseline_signatures(page, ["#create-workspace", "#open-workspace"])
    home_focusable = page.evaluate("() => window.__a11y.focusable()")
    reached_home, home_sigs = walk_tab(page, limit=40, stop_ids={"open-workspace"}, collect_sig=True)
    home_changed = {}
    for ident in HOME_SIG_KEYS:
        selector = "#" + ident
        if selector not in home_baseline:
            home_changed[selector] = "absent"
        elif ident not in home_sigs:
            home_changed[selector] = "not-reached"
        else:
            home_changed[selector] = ("changed" if home_sigs[ident] != home_baseline[selector]
                                      else "unchanged")

    active = page.evaluate("() => (document.activeElement && document.activeElement.id) || ''")
    space_ok = False
    space_detail = {"focused": active}
    if active == "open-workspace":
        page.keyboard.press("Space")
        try:
            page.wait_for_selector("#intake-screen:not([hidden])", timeout=20000)
            space_ok = True
            space_detail["opened"] = True
        except Exception as exc:  # noqa: BLE001
            space_detail["opened"] = False
            space_detail["error"] = str(exc)[:200]
    record(results, "blank.keyboard_space", "空白形态：Space 可触发主流程动作（打开工作空间）",
           space_ok, space_detail)

    page.evaluate("() => { if (document.activeElement) document.activeElement.blur(); }")
    arm(page, BLANK_SIG_KEYS)
    intake_focusable = page.evaluate("() => window.__a11y.focusable()")
    intake_baseline = baseline_signatures(page, INTAKE_SIG_SELECTORS)
    reached, sigs = walk_tab(page, limit=250, collect_sig=True)
    reached_keys = [item["key"] for item in reached]
    missing = [item["key"] for item in intake_focusable if item["key"] not in reached_keys]
    record(results, "blank.tab_reach", "空白形态：Tab 可达全部可见控件", not missing,
           {"focusable": [item["key"] for item in intake_focusable],
            "reached": reached_keys, "missing": missing, "home_tab_stops": [
                item["key"] for item in reached_home]})

    indicator = {}
    for ident in BLANK_SIG_KEYS:
        selector = "#" + ident
        if selector in home_baseline and ident in home_sigs:
            indicator[selector] = ("changed" if home_sigs[ident] != home_baseline[selector]
                                   else "unchanged")
        elif selector in intake_baseline:
            if ident not in sigs:
                indicator[selector] = "not-reached"
            else:
                indicator[selector] = ("changed" if sigs[ident] != intake_baseline[selector]
                                       else "unchanged")
    no_indicator = [key for key, value in indicator.items()
                    if value in {"unchanged", "not-reached"}]
    record(results, "blank.focus_indicator", "空白形态：键盘焦点可见（控件样式随焦点变化）",
           not no_indicator,
           {"per_control": indicator, "without_visible_change": no_indicator,
            "home": home_changed})

    labels = page.evaluate(
        "(ids) => window.__a11y.labelInfo(ids)",
        ["product-name", "product-description", "selling-points", "user-intent", "reference-images"],
    )
    label_failures = []
    for ident, info in labels.items():
        if not info.get("found"):
            label_failures.append(ident + ":missing")
            continue
        if not info["labels"] and not info["ariaLabel"]:
            label_failures.append(ident + ":no-accessible-label")
        for described in info["describedBy"]:
            if not described["exists"]:
                label_failures.append(ident + ":describedby-missing:" + described["id"])
            elif not described["text"] and not described["live"]:
                label_failures.append(ident + ":describedby-empty:" + described["id"])
    record(results, "blank.label_association", "空白形态：label 与 aria-describedby 关联完整",
           not label_failures, {"controls": labels, "problems": label_failures})

    errors = page.evaluate(
        "(pairs) => window.__a11y.errorInfo(pairs)",
        [["product-name", "product-name-error"], ["reference-images", "image-error"]],
    )
    error_failures = []
    for item in errors:
        if not item["found"]:
            error_failures.append(item["input"] + ":missing")
            continue
        if item["role"] != "alert":
            error_failures.append(item["input"] + ":role=" + (item["role"] or "none"))
        if not item["referenced"]:
            error_failures.append(item["input"] + ":error-not-in-aria-describedby")
    record(results, "blank.error_association", "空白形态：错误提示与输入框关联（role=alert + aria-describedby）",
           not error_failures, {"pairs": errors, "problems": error_failures})

    page.screenshot(path=str(EVIDENCE / ("d4.2-" + stamp + "-blank.png")), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(250)
    overflow = page.evaluate("() => window.__a11y.overflow()")
    page.screenshot(path=str(EVIDENCE / ("d4.2-" + stamp + "-blank-390.png")), full_page=True)
    record(results, "responsive.390_blank", "空白形态：390px 视口无横向溢出",
           overflow["scrollWidth"] <= overflow["innerWidth"] + 1, overflow)
    page.set_viewport_size({"width": 1440, "height": 1000})


SNAP_JS = r"""
() => {
  const section = document.getElementById('generation-workspace');
  const hint = document.getElementById('generation-hint');
  const status = document.getElementById('generation-status');
  const start = document.getElementById('generate-from-plan');
  return {
    busy: section ? section.getAttribute('aria-busy') : null,
    hint: hint ? (hint.innerText || '').trim() : '',
    status: status ? (status.innerText || '').trim() : '',
    startLabel: start ? (start.innerText || '').trim() : '',
    startDisabled: start ? start.disabled : null,
    cards: Array.from(document.querySelectorAll('#generation-shots .generation-shot'))
      .map((card) => (card.innerText || '').trim()),
  };
}
"""

CARD_JS = r"""
() => Array.from(document.querySelectorAll('#generation-shots .generation-shot')).map((card) => ({
  text: (card.innerText || '').trim(),
  buttons: card.tagName === 'BUTTON'
    ? [{ label: (card.innerText || '').trim(), disabled: card.disabled, cls: card.className }]
    : Array.from(card.querySelectorAll('button')).map((button) => ({
        label: (button.innerText || '').trim(),
        disabled: button.disabled,
        cls: button.className,
      })),
}))
"""


def check_empty(page, base_url: str, planned_dir: Path, results: list, stamp: str) -> None:
    """空的生成状态：有计划但还没有任何候选。"""
    open_workspace(page, base_url, str(planned_dir))
    page.wait_for_selector("#generation-shots .generation-shot", timeout=40000)
    arm(page)
    cards = page.evaluate(CARD_JS)
    problems = []
    if not cards:
        problems.append("no-shot-cards")
    for index, card in enumerate(cards):
        if not STATE_WORD.search(card["text"]):
            problems.append("shot-" + str(index) + ":no-state-text")
        if not card["buttons"]:
            problems.append("shot-" + str(index) + ":no-action-button")
    start = page.evaluate("""() => { const el = document.getElementById('generate-from-plan');
      return el ? { text: (el.innerText || '').trim(), disabled: el.disabled } : null; }""")
    if not start or start["disabled"]:
        problems.append("generate-from-plan-not-actionable")
    record(results, "data.empty_state", "有数据形态：未生成状态有文字状态与可操作入口",
           not problems,
           {"cards": len(cards), "start": start, "problems": problems,
            "sample": cards[0]["text"][:400] if cards else None})
    page.screenshot(path=str(EVIDENCE / ("d4.2-" + stamp + "-empty.png")), full_page=True)


def check_error(page, base_url: str, missing_dir: Path, results: list, stamp: str) -> None:
    """错误状态：打开一个不存在的目录。"""
    open_workspace(page, base_url, str(missing_dir))
    detail: dict = {}
    ok = False
    try:
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            detail = page.evaluate("""() => { const el = document.getElementById('app-notice');
              const home = document.getElementById('home-screen');
              return { hidden: el ? el.hidden : null,
                       display: el ? getComputedStyle(el).display : null,
                       text: (el && el.innerText || '').trim(),
                       tone: el ? (el.dataset.tone || '') : '',
                       role: el ? (el.getAttribute('role') || '') : '',
                       live: el ? (el.getAttribute('aria-live') || '') : '',
                       home_visible: home ? !home.hidden : null }; }""")
            if detail and not detail.get("hidden") and detail.get("text"):
                break
            page.wait_for_timeout(400)
        ok = (bool(detail.get("text")) and detail.get("tone") == "error"
              and detail.get("role") in {"status", "alert"} and bool(detail.get("live")))
    except Exception as exc:  # noqa: BLE001
        detail = {"error": str(exc)[:200]}
    record(results, "data.error_state", "有数据形态：打开失败给出文字错误提示（不只靠颜色）", ok, detail)
    page.screenshot(path=str(EVIDENCE / ("d4.2-" + stamp + "-error.png")), full_page=True)


def check_keyboard(page, base_url: str, planned_dir: Path, provider, results: list, stamp: str) -> None:
    """键盘：只用 Tab 走到「开始生成」，用 Enter 真触发一次生成。"""
    open_workspace(page, base_url, str(planned_dir))
    page.wait_for_selector("#generation-shots .generation-shot", timeout=40000)
    arm(page)
    reached, _ = walk_tab(page, limit=250, stop_ids={"generate-from-plan"})
    active = page.evaluate("() => (document.activeElement && document.activeElement.id) || ''")
    detail: dict = {"active_after_tab": active, "tab_stops": len(reached)}
    if active != "generate-from-plan":
        record(results, "keyboard.start_generation",
               "键盘：Tab 到「开始生成」并用 Enter 触发", False, detail)
        return
    before = provider.attempts_seen
    page.keyboard.press("Enter")
    observations = []
    loading_seen = False
    deadline = time.time() + 10
    while time.time() < deadline:
        snap = page.evaluate(SNAP_JS)
        observations.append({"busy": snap["busy"], "start_label": snap["startLabel"],
                             "cards": [text[:60] for text in snap["cards"]]})
        if snap["busy"] == "true":
            loading_seen = True
            break
        if any(word in text for text in snap["cards"]
               for word in ("生成中", "已提交", "准备提交", "正在核对", "结果待核对")):
            loading_seen = True
            break
        time.sleep(0.2)
    record(results, "data.loading_state", "有数据形态：生成中的 loading 有 aria-busy 或文字状态",
           loading_seen, {"observations": observations[:10],
                          "hint": page.evaluate(SNAP_JS)["hint"]})
    try:
        page.wait_for_selector(
            "#review-candidates .generation-candidate, #review-image:not([hidden]),"
            " #reconcile-generation:not([hidden])",
            timeout=40000,
        )
    except Exception:  # noqa: BLE001
        pass
    if page.query_selector("#reconcile-generation:not([hidden])"):
        page.click("#reconcile-generation")
    generated = False
    try:
        page.wait_for_selector("#review-image:not([hidden])", timeout=40000)
        generated = True
    except Exception:  # noqa: BLE001
        generated = False
    detail["provider_submissions"] = provider.attempts_seen - before
    detail["candidates_rendered"] = page.locator("#review-candidates .generation-candidate").count()
    detail["loading_seen"] = loading_seen
    page.screenshot(path=str(EVIDENCE / ("d4.2-" + stamp + "-keyboard-generated.png")), full_page=True)
    record(results, "keyboard.start_generation",
           "键盘：Tab 到「开始生成」并用 Enter 触发（产生候选）",
           bool(generated and (provider.attempts_seen - before) >= 1), detail)


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        print("缺少 Playwright：请用 uv --with playwright 运行本脚本。")
        return 2
    if not REAL_WORKSPACE.exists():
        print("真实工作空间不存在：" + str(REAL_WORKSPACE))
        return 2
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    before_hashes = tree_hashes(REAL_WORKSPACE)
    provider = SlowRegistryImageProvider()
    provider.plan([("SUCCEEDED", "d42-task-%d" % index) for index in range(1, 9)])
    for index in range(1, 9):
        provider.resolve("d42-task-%d" % index)
    external_requests: list[str] = []
    with tempfile.TemporaryDirectory(prefix="amz-d42-a11y-") as raw:
        tmp = Path(raw)
        blank_dir = tmp / "blank-workspace"
        planned_dir = tmp / "planned-workspace"
        data_dir = tmp / "run-05-copy"
        missing_dir = tmp / "missing-workspace"
        create_blank_workspace(blank_dir, provider)
        build_planned_workspace(planned_dir, provider)
        shutil.copytree(REAL_WORKSPACE, data_dir)
        httpd, thread = start_product(provider, tmp / "recent.json", blank_dir)
        try:
            with sync_playwright() as driver:
                browser = driver.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                origin = "http://127.0.0.1:%d" % PORT

                def watch(request, origin=origin):
                    host = urlsplit(request.url).netloc
                    if host and host != urlsplit(origin).netloc:
                        external_requests.append(request.url)

                page.on("request", watch)
                try:
                    check_blank(page, origin, results, stamp)
                    check_data(page, origin, data_dir, results, stamp)
                    check_empty(page, origin, planned_dir, results, stamp)
                    check_error(page, origin, missing_dir, results, stamp)
                    check_keyboard(page, origin, planned_dir, provider, results, stamp)
                finally:
                    browser.close()
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)
    after_hashes = tree_hashes(REAL_WORKSPACE)
    record(results, "safety.real_workspace_unchanged", "真实工作空间只读（逐文件 sha256 比对）",
           before_hashes == after_hashes,
           {"files": len(before_hashes),
            "changed": [key for key in before_hashes if after_hashes.get(key) != before_hashes[key]],
            "added": [key for key in after_hashes if key not in before_hashes],
            "removed": [key for key in before_hashes if key not in after_hashes]})
    record(results, "safety.no_external_requests", "浏览器没有访问产品以外的地址",
           not external_requests, {"external": external_requests[:10]})
    failures = [item for item in results if not item["ok"]]
    report = {
        "stamp": stamp,
        "port": PORT,
        "zoom_limitation": ZOOM_LIMITATION,
        "checks": results,
        "failures": [item["id"] for item in failures],
        "passed": not failures,
    }
    path = EVIDENCE / ("d4.2-usability-accessibility-" + stamp + ".json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": not failures, "checks": len(results),
                      "failed": [item["id"] for item in failures],
                      "report": path.name}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


def check_data(page, base_url: str, data_dir: Path, results: list, stamp: str) -> None:
    """有数据形态：真实 run-05 副本上的状态与溢出检查。"""
    open_workspace(page, base_url, str(data_dir))
    page.wait_for_selector("#generation-shots .generation-shot", timeout=40000)
    arm(page)
    cards = page.evaluate("""() => Array.from(document.querySelectorAll(
        '#generation-shots .generation-shot')).map((card) => ({
          text: (card.innerText || '').trim(),
          buttons: Array.from(card.querySelectorAll('button')).map((button) => ({
            label: (button.innerText || '').trim(),
            disabled: button.disabled,
            cls: button.className,
          })),
        }))""")
    cards_without_state = [index for index, card in enumerate(cards)
                           if not STATE_WORD.search(card["text"])]
    record(results, "data.shots_state_text", "有数据形态：每张图卡片都有文字状态（不只靠颜色）",
           bool(cards) and not cards_without_state,
           {"cards": len(cards), "cards_without_state": cards_without_state,
            "sample": cards[0]["text"][:400] if cards else None})

    live = page.evaluate(
        "(ids) => ids.map((id) => { const el = document.getElementById(id);"
        " if (!el) return { id, found: false };"
        " return { id, found: true, role: el.getAttribute('role') || '',"
        " live: el.getAttribute('aria-live') || '', hidden: el.hidden || Boolean(el.closest('[hidden]')),"
        " text: (el.innerText || '').trim() }; })",
        LIVE_REGIONS,
    )
    live_problems = []
    for item in live:
        if not item["found"]:
            continue
        if item["role"] not in {"status", "alert"}:
            live_problems.append(item["id"] + ":role=" + (item["role"] or "none"))
        if not item["live"]:
            live_problems.append(item["id"] + ":no-aria-live")
        if not item["hidden"] and not item["text"]:
            live_problems.append(item["id"] + ":visible-but-empty")
    record(results, "data.live_regions", "有数据形态：状态区域有 role/aria-live 且可见时有文字",
           not live_problems, {"regions": live, "problems": live_problems})

    busy = page.evaluate("""() => ['generation-workspace', 'brief-workspace'].map((id) => {
      const el = document.getElementById(id);
      return { id, found: Boolean(el), busy: el ? el.getAttribute('aria-busy') : null };
    })""")
    busy_problems = [item["id"] for item in busy
                     if not item["found"] or item["busy"] is None]
    record(results, "data.aria_busy", "有数据形态：loading 用 aria-busy 表达", not busy_problems,
           {"sections": busy, "problems": busy_problems})

    disabled = page.evaluate(
        "(sels) => sels.map((selector) => ({ selector,"
        " info: window.__a11y.disabledReason(selector) }))",
        DISABLED_TARGETS,
    )
    disabled_problems = []
    for item in disabled:
        info = item["info"]
        if not info.get("found"):
            continue
        if info["disabled"] and not info["reasons"]:
            disabled_problems.append(item["selector"])
    record(results, "data.disabled_reason", "有数据形态：禁用按钮的原因可被发现",
           not disabled_problems, {"buttons": disabled, "without_reason": disabled_problems})

    page.screenshot(path=str(EVIDENCE / ("d4.2-" + stamp + "-data.png")), full_page=True)

    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(250)
    overflow = page.evaluate("() => window.__a11y.overflow()")
    record(results, "responsive.390_data", "有数据形态：390px 视口无横向溢出",
           overflow["scrollWidth"] <= overflow["innerWidth"] + 1, overflow)
    page.screenshot(path=str(EVIDENCE / ("d4.2-" + stamp + "-data-390.png")), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 1000})

    page.set_viewport_size({"width": 720, "height": 500})
    page.wait_for_timeout(250)
    zoom_overflow = page.evaluate("() => window.__a11y.overflow()")
    hits = page.evaluate("(sels) => sels.map((s) => [s, window.__a11y.hit(s)])",
                         ["#generate-from-plan", "#export-selection", "#back-home"])
    zoom_problems = []
    for selector, info in hits:
        if not info.get("found"):
            zoom_problems.append(selector + ":missing")
            continue
        if not info["insideViewport"]:
            zoom_problems.append(selector + ":outside-viewport")
        if not info["hit"]:
            zoom_problems.append(selector + ":covered-or-zero-size")
    if zoom_overflow["scrollWidth"] > zoom_overflow["innerWidth"] + 1:
        zoom_problems.append("horizontal-overflow")
    page.screenshot(path=str(EVIDENCE / ("d4.2-" + stamp + "-zoom200.png")), full_page=True)
    record(results, "zoom.200_data", "200% 缩放（等价 720x500 视口）：主流程按钮可见可点、无溢出",
           not zoom_problems,
           {"limitation": ZOOM_LIMITATION, "overflow": zoom_overflow,
            "buttons": dict(hits), "problems": zoom_problems})
    page.set_viewport_size({"width": 1440, "height": 1000})


if __name__ == "__main__":
    raise SystemExit(main())
