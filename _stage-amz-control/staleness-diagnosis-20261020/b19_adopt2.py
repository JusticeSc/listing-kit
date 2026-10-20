"""B19 收尾：把返工新候选显式选中再采用（旧候选不动），核对交付门禁并导出两包。零模型调用。"""
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
from playwright.sync_api import expect, sync_playwright  # noqa: E402

import v2_stage_nav as stage_nav  # noqa: E402
import v2_verify_shared as shared  # noqa: E402

PORT = 5512
HOST = HERE / 'b19_live_server.py'
PROFILE = Path(os.environ.get('B19_PROFILE', ''))
OUT = HERE / 'b19-adopt.json'
EXPORTS = HERE / 'b19-exports'
SHOTS = ['shot_infographic_benefits', 'shot_detail_material']


def wait_ready(port: int, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                return
        time.sleep(0.2)
    raise SystemExit(f'host on {port} never became reachable')


def cards(page) -> list[dict]:
    return page.evaluate(
        """() => [...document.querySelectorAll('#compare-candidates [data-candidate-id]')].map((node) => {
             const m = (node.textContent || '').match(/候选 v(\\d+)/);
             return { id: node.dataset.candidateId, version: m ? Number(m[1]) : -1,
                      selected: node.getAttribute('aria-selected'),
                      adopted: Boolean(node.querySelector('.badge.is-adopted')) }; })""")


def row_state(page, shot: str) -> dict | None:
    return page.evaluate(
        """(shot) => { const row = document.querySelector('#task-list-mount [data-task-shot="' + shot + '"]');
             return row ? { attempt: row.getAttribute('data-attempt-state'),
                            selection: row.getAttribute('data-selection-state') } : null; }""", shot)


def adopt_newest(page, shot: str) -> dict:
    shared.select_make_shot(page, shot)
    list_seen = page.evaluate(
        """() => [...document.querySelectorAll('#task-list-mount [data-task-shot]')]
             .map((node) => node.getAttribute('data-task-shot'))""")
    shared.select_make_shot(page, shot)
    page.wait_for_timeout(500)
    before = cards(page)
    newest = max(before, key=lambda c: c['version'])
    page.click(f'#compare-candidates [data-candidate-id="{newest["id"]}"]')
    page.wait_for_function(
        """(id) => { const img = document.getElementById('compare-viewed-image');
             return Boolean(img && img.dataset.candidateId === id); }""", arg=newest['id'], timeout=30_000)
    page.click('#adopt-open')
    page.wait_for_timeout(1200)
    after = cards(page)
    return {'shot': shot, 'newest': newest, 'before': before, 'after': after,
            'row': row_state(page, shot), 'shots_listed': list_seen}


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

            stage_nav.goto(page, 'make')
            page.wait_for_timeout(800)
            snap['adoptions'] = [adopt_newest(page, shot) for shot in SHOTS]
            page.screenshot(path=str(HERE / 'b19-adopt-make.png'), full_page=True)

            stage_nav.goto(page, 'deliver')
            page.wait_for_timeout(1500)
            snap['gate_rows'] = page.evaluate(
                """() => [...document.querySelectorAll('#delivery-gate [data-shot-id]')]
                     .map((node) => ({ shot: node.dataset.shotId,
                                       state: node.dataset.selectionState || '',
                                       text: (node.textContent || '').trim().slice(0, 120) }))""")
            snap['suite_status'] = page.evaluate(
                "() => { const n = document.getElementById('delivery-suite-status'); return n ? (n.textContent || '').trim() : null; }")
            snap['findings'] = page.evaluate(
                "() => { const n = document.getElementById('delivery-suite-findings'); return n ? (n.innerText || '').trim().slice(0, 600) : null; }")
            snap['export_enabled'] = not page.locator('#deliver-export').is_disabled()
            page.screenshot(path=str(HERE / 'b19-adopt-gate.png'), full_page=True)
            page.wait_for_timeout(300)
            if page.locator('#deliver-project-package').is_enabled():
                EXPORTS.mkdir(exist_ok=True)
                with page.expect_download(timeout=180_000) as info_dl:
                    page.click('#deliver-project-package')
                info_dl.value.save_as(str(EXPORTS / 'b19-project-final.zip'))
                page.wait_for_timeout(800)
            if page.locator('#deliver-export').is_enabled():
                with page.expect_download(timeout=180_000) as del_dl:
                    page.click('#deliver-export')
                del_dl.value.save_as(str(EXPORTS / 'b19-delivery-final.zip'))
                snap['delivery_bytes'] = (EXPORTS / 'b19-delivery-final.zip').stat().st_size
            snap['exports'] = {p.name: p.stat().st_size for p in sorted(EXPORTS.glob('b19-*-final.zip'))}
            context.close()
    finally:
        host.terminate()
        try:
            host.wait(timeout=20)
        except subprocess.TimeoutExpired:
            host.kill()
        OUT.write_bytes((json.dumps(snap, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({k: snap.get(k) for k in ('adoptions', 'gate_rows', 'suite_status', 'findings',
                                               'export_enabled', 'exports')}, ensure_ascii=False, indent=1)[:4000])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
