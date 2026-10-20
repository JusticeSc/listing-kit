"""Read-only snapshot: what the real imported project shows at the delivery gate and in
the confirm sheet for the two stale figures. No provider calls: the host refuses them.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from playwright.sync_api import sync_playwright  # noqa: E402

import v2_stage_nav as stage_nav  # noqa: E402
import v2_verify_shared as shared  # noqa: E402

PORT = 5507
PACKAGE = (ROOT / '_stage-amz-control/resume-extension-20261019T105641Z/packages/'
           '真实闭环-·-参考图-20261019-1307.zip')
HOST = ROOT / '_stage-amz-control/resume-extension-20261019T105641Z/b16_import_host.py'
OUT = HERE / 'gate-snapshot.json'


def wait_ready(port: int, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(1.0)
            try:
                sock.connect(('127.0.0.1', port))
            except OSError:
                time.sleep(0.3)
                continue
            return
    raise SystemExit(f'host on {port} never became reachable')


def main() -> int:
    env = dict(os.environ, B16_IMPORT_PORT=str(PORT))
    host = subprocess.Popen([sys.executable, str(HOST)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding='utf-8')
    snap: dict = {'port': PORT, 'package': PACKAGE.name, 'provider': 'refusing (no calls)'}
    try:
        wait_ready(PORT)
        with sync_playwright() as pw:
            profile = Path(tempfile.mkdtemp(prefix='b18-snapshot-'))
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True,
                viewport={'width': 1440, 'height': 950})
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(45_000)
            page.goto(f'http://127.0.0.1:{PORT}/', wait_until='domcontentloaded')
            page.wait_for_function(
                "() => { const node = document.getElementById('import-trigger');"
                " return node && node.disabled === false; }", timeout=30_000)
            page.set_input_files('#import-file', str(PACKAGE))
            page.wait_for_function(
                "() => { const node = document.getElementById('home-status');"
                " return node && node.textContent.indexOf('已导入') >= 0; }", timeout=180_000)
            page.click('#project-list .project-row button[data-action="open"]')
            page.wait_for_selector('#project-view:not([hidden])', timeout=60_000)
            stage_nav.goto(page, 'deliver')
            page.wait_for_timeout(800)
            snap['gate_rows'] = page.evaluate(
                """() => [...document.querySelectorAll('#delivery-gate [data-shot-id]')]
                     .map((node) => ({ shot: node.dataset.shotId,
                                       state: node.dataset.selectionState || '',
                                       text: (node.textContent || '').trim().slice(0, 120) }))""")
            snap['gate_text'] = page.locator('#delivery-gate').inner_text()[:2500]
            snap['export_enabled'] = not page.locator('#deliver-export').is_disabled()
            stage_nav.goto(page, 'make')
            shared.select_make_shot(page, 'shot_infographic_benefits')
            page.wait_for_timeout(500)
            snap['make_compare_text'] = page.locator('#compare-panel').inner_text()[:1500]
            snap['confirm_parts'] = page.evaluate(
                """() => { const el = (id) => {
                       const node = document.getElementById(id);
                       return node ? (node.innerText || node.textContent || '') : null; };
                     return { status: el('confirm-status'), summary: el('confirm-summary'),
                              blockers: el('confirm-blockers'), list: el('confirm-list'),
                              risks: el('confirm-risks') }; }""")
            snap['confirm_action_label'] = page.evaluate(
                "() => (document.getElementById('confirm-action') || {}).textContent || ''")
            snap['confirm_action_disabled'] = page.evaluate(
                "() => (document.getElementById('confirm-action') || {}).disabled ?? null")
            page.screenshot(path=str(HERE / 'shots' / 'gate-snapshot.png'), full_page=True)
            context.close()
    finally:
        host.terminate()
        try:
            host.wait(timeout=20)
        except subprocess.TimeoutExpired:
            host.kill()
        OUT.write_bytes((json.dumps(snap, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({k: snap[k] for k in ('gate_rows', 'export_enabled',
                                           'confirm_action_label',
                                           'confirm_action_disabled')},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
