"""B19 收尾二：重跑本地确定性整套检查（零模型、零外网），再导出交付包。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from playwright.sync_api import sync_playwright  # noqa: E402

import v2_stage_nav as stage_nav  # noqa: E402

PORT = 5512
HOST = HERE / 'b19_live_server.py'
PROFILE = Path(os.environ.get('B19_PROFILE', ''))
OUT = HERE / 'b19-deliver.json'
EXPORTS = HERE / 'b19-exports'


def wait_ready(port: int, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                return
        time.sleep(0.2)
    raise SystemExit(f'host on {port} never became reachable')


def main() -> int:
    env = dict(os.environ, AMZ_V2_DEFAULT_TRIAL='open')
    host = subprocess.Popen([sys.executable, str(HOST)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding='utf-8')
    snap: dict = {'profile': str(PROFILE)}
    try:
        wait_ready(PORT)
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(PROFILE), headless=True, viewport={'width': 1440, 'height': 950},
                accept_downloads=True)
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(45_000)
            page.goto(f'http://127.0.0.1:{PORT}/', wait_until='domcontentloaded')
            page.wait_for_selector('#project-list .project-row', state='attached', timeout=60_000)
            if page.locator('#project-view').is_hidden():
                page.click('#project-list .project-row button[data-action="open"]')
            page.wait_for_selector('#project-view:not([hidden])', timeout=60_000)
            stage_nav.goto(page, 'deliver')
            page.wait_for_timeout(1200)
            snap['suite_before'] = page.inner_text('#suite-review-status')
            page.click('#suite-review-run')
            page.wait_for_function(
                """() => { const st = document.getElementById('suite-review-status');
                     const err = document.getElementById('suite-review-error');
                     const text = st ? (st.textContent || '') : '';
                     const bad = err ? (err.textContent || '').trim() : '';
                     return bad.length > 0 || (text.includes('整套检查 v') && !text.includes('已过期')); }""",
                timeout=180_000)
            snap['suite_after'] = page.inner_text('#suite-review-status')
            snap['suite_error'] = page.evaluate(
                "() => { const n = document.getElementById('suite-review-error'); return n ? (n.textContent || '').trim() : ''; }")
            snap['delivery_suite'] = page.evaluate(
                "() => { const n = document.getElementById('delivery-suite-status'); return n ? (n.textContent || '').trim() : ''; }")
            page.wait_for_timeout(800)
            snap['export_enabled'] = not page.locator('#deliver-export').is_disabled()
            snap['gate_rows'] = page.evaluate(
                """() => [...document.querySelectorAll('#delivery-gate [data-shot-id]')]
                     .map((node) => ({ shot: node.dataset.shotId, state: node.dataset.selectionState || '' }))""")
            page.screenshot(path=str(HERE / 'b19-deliver-gate.png'), full_page=True)
            if snap['export_enabled']:
                EXPORTS.mkdir(exist_ok=True)
                with page.expect_download(timeout=240_000) as dl:
                    page.click('#deliver-export')
                dl.value.save_as(str(EXPORTS / 'b19-delivery-final.zip'))
                page.wait_for_timeout(800)
                snap['exports'] = {p.name: p.stat().st_size for p in sorted(EXPORTS.glob('b19-*-final.zip'))}
            context.close()
    finally:
        host.terminate()
        try:
            host.wait(timeout=20)
        except subprocess.TimeoutExpired:
            host.kill()
        OUT.write_bytes((json.dumps(snap, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps(snap, ensure_ascii=False, indent=1)[:3000])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
