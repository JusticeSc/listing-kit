"""Capture the outbound shape the product would send when the two stale figures are
refreshed, without paying for anything.

Runs against record_host.py (port 5516): the provider records the shape and refuses to
send, so the product path is real up to the adapter boundary and nothing leaves the
process. Everything is driven through the product UI (plan-stage printing decision,
rework panel with the product's own problem categories and a plain-language direction);
no prompt is written by hand.
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
from playwright.sync_api import expect, sync_playwright  # noqa: E402

import v2_stage_nav as stage_nav  # noqa: E402
import v2_verify_shared as shared  # noqa: E402

PORT = 5516
PACKAGE = (ROOT / '_stage-amz-control/resume-extension-20261019T105641Z/packages/'
           '真实闭环-·-参考图-20261019-1307.zip')
TARGETS = {
    'shot_infographic_benefits': {
        'problems': ['text', 'selling_point'],
        'direction': '图上卖点文字按已确认文案在留白区逐个排清楚，不与商品或彼此重叠。',
    },
    'shot_detail_material': {
        'problems': ['text', 'composition'],
        'direction': '细节特写里的文字保持清楚整齐，商品材质质感保持不变。',
    },
}
SHAPE_FILE = HERE / 'recorded-shapes.json'
SHOT_DIR = HERE / 'shots'
RESULT = HERE / 'capture-result.json'


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


def attempt_rows(page) -> dict:
    probe = page.evaluate(shared.AUTHORIZATION_PROBE)
    latest: dict = {}
    for row in probe['attempts']:
        payload = row['payload']
        current = latest.get(payload['shot_id'])
        if current is None or row['version'] > current['version']:
            latest[payload['shot_id']] = {'version': row['version'],
                                          'state': payload['state'],
                                          'action_id': payload['action_id']}
    return latest


def wait_terminal(page, shot: str, before_version: int, timeout: int = 240_000) -> dict:
    deadline = time.monotonic() + timeout / 1000
    while time.monotonic() < deadline:
        row = attempt_rows(page).get(shot)
        if row and row['version'] > before_version and row['state'] in (
                'succeeded', 'failed', 'unknown'):
            return row
        page.wait_for_timeout(1000)
    raise AssertionError(f'{shot} 的提交没有在时限内落定')


def plan_decisions(page, shot: str, entry: dict) -> None:
    """在计划阶段为这张图做「要不要印字/印哪些」的明确决定并重新编译。"""
    stage_nav.goto(page, 'plan')
    page.wait_for_timeout(500)
    entry['plan_panel_text'] = page.locator('#shot-spec-panel').inner_text()[:4000]
    entry['plan_controls'] = page.evaluate(
        """() => [...document.querySelectorAll('#shot-spec-panel input, #shot-spec-panel select, '''
        '''#shot-spec-panel button')].map((node) => ({
               tag: node.tagName.toLowerCase(), id: node.id || '', type: node.type || '',
               name: node.name || '', value: node.value || '',
               label: (node.closest('label') || {}).textContent?.trim().slice(0, 80) || '',
               checked: node.checked ?? null }))""")


def main() -> int:
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    for stale in (SHAPE_FILE, RESULT):
        if stale.exists():
            stale.unlink()
    env = dict(os.environ, B18_RECORD_PORT=str(PORT))
    host = subprocess.Popen([sys.executable, str(HERE / 'record_host.py')], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding='utf-8')
    result: dict = {'port': PORT, 'project_package': PACKAGE.name, 'shots': []}
    try:
        wait_ready(PORT)
        with sync_playwright() as pw:
            profile = Path(tempfile.mkdtemp(prefix='b18-capture-'))
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True,
                viewport={'width': 1440, 'height': 950}, accept_downloads=True)
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(45_000)
            logs = shared.collect(page)
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
            result['gate_rows_before'] = page.evaluate(
                """() => [...document.querySelectorAll('#delivery-gate [data-shot-id]')]
                     .map((node) => ({ shot: node.dataset.shotId,
                                       state: node.dataset.selectionState || '',
                                       text: (node.textContent || '').trim().slice(0, 120) }))""")
            for shot, plan in TARGETS.items():
                entry: dict = {'shot': shot, 'plan': plan}
                result['shots'].append(entry)
                try:
                    stage_nav.goto(page, 'make')
                    shared.select_make_shot(page, shot)
                    entry['row_state'] = page.evaluate(
                        """(shot) => { const row = document.querySelector(
                             '#task-list-mount [data-task-shot="' + shot + '"]');
                           return row ? row.getAttribute('data-selection-state') : null; }""", shot)
                    entry['compare_text'] = page.locator('#compare-panel').inner_text()[:1500]
                    plan_decisions(page, shot, entry)
                except Exception as exc:
                    entry['error'] = repr(exc)[:3000]
                    page.screenshot(path=str(SHOT_DIR / f'plan-{shot}.png'), full_page=True)
                    entry['stage_buttons'] = page.evaluate(
                        """() => [...document.querySelectorAll('#project-view button')]
                             .map((node) => ({ id: node.id || '',
                                               text: (node.textContent || '').trim().slice(0, 80),
                                               disabled: node.disabled }))
                             .filter((row) => row.id || row.text)""")
                    raise
            result['console_errors'] = logs['console_errors']
            result['page_errors'] = logs['page_errors']
            result['http_errors'] = logs['http_errors']
            context.close()
    finally:
        host.terminate()
        try:
            host.wait(timeout=20)
        except subprocess.TimeoutExpired:
            host.kill()
        result['recorded'] = (json.loads(SHAPE_FILE.read_text(encoding='utf-8'))
                              if SHAPE_FILE.exists() else [])
        RESULT.write_bytes((json.dumps(result, ensure_ascii=False, indent=2) + '\n')
                           .encode('utf-8'))
    print(json.dumps(result.get('gate_rows_before'), ensure_ascii=False))
    for entry in result['shots']:
        print('SHOT', entry['shot'], 'state', entry.get('row_state'))
        print('  plan_text:', (entry.get('plan_panel_text') or entry.get('error') or '')[:2500])
        print('  controls:', json.dumps(entry.get('plan_controls'), ensure_ascii=False)[:2500])
        if entry.get('stage_buttons'):
            print('  buttons:', json.dumps(entry['stage_buttons'], ensure_ascii=False)[:2500])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
