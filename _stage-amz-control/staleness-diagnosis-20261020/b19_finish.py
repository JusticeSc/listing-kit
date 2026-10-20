"""B19 续跑：复用已花掉 1 次调用的 profile，完成卖点信息图并按需复核细节图，再导出两包。

profile 必须与上次同源（127.0.0.1:5512），否则 IndexedDB 里的新候选不可见。
"""
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
OUT = HERE / 'b19-finish.json'
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


def row_state(page, shot: str) -> dict:
    return page.evaluate(
        """(shot) => { const row = document.querySelector('#task-list-mount [data-task-shot="' + shot + '"]');
             return row ? { attempt: row.getAttribute('data-attempt-state'),
                            selection: row.getAttribute('data-selection-state') } : null; }""", shot)


def preview(page) -> dict:
    page.wait_for_function(
        """() => { const box = document.getElementById('rework-preview-box');
             const text = document.getElementById('rework-preview-text');
             const err = document.getElementById('rework-error');
             return Boolean(box && !box.hidden && text && (text.textContent || '').trim())
               || Boolean(err && !err.hidden && (err.textContent || '').trim()); }""",
        timeout=120_000)
    return page.evaluate(
        """() => { const el = (id) => { const n = document.getElementById(id);
             return n ? (n.innerText || n.textContent || '') : null; };
           return { meta: el('rework-preview-meta'), text: el('rework-preview-text'),
                    cost: el('rework-cost'), error: el('rework-error'),
                    error_hidden: (document.getElementById('rework-error') || {}).hidden,
                    choice_present: Boolean(document.getElementById('rework-prompt-choice')),
                    submit_disabled: document.getElementById('rework-submit').disabled }; }""")


def main() -> int:
    if not PROFILE.exists():
        raise SystemExit(f'profile not found: {PROFILE}')
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
            console: list[str] = []
            page.on('console', lambda msg: console.append(msg.text) if msg.type == 'error' else None)
            page.goto(f'http://127.0.0.1:{PORT}/', wait_until='domcontentloaded')
            page.wait_for_selector('#project-list .project-row', state='attached', timeout=60_000)
            if page.locator('#project-view').is_hidden():
                page.click('#project-list .project-row button[data-action="open"]')
            page.wait_for_selector('#project-view:not([hidden])', timeout=60_000)

            stage_nav.goto(page, 'make')
            page.wait_for_timeout(1200)
            snap['detail_state_before'] = row_state(page, 'shot_detail_material')
            shared.select_make_shot(page, 'shot_detail_material')
            page.wait_for_timeout(600)
            snap['detail_confirm'] = page.evaluate(
                """() => { const el = (id) => { const n = document.getElementById(id);
                     return n ? (n.innerText || n.textContent || '') : null; };
                   return { status: el('confirm-status'), summary: el('confirm-summary'),
                            blockers: el('confirm-blockers'), list: el('confirm-list'),
                            selection_chip: el('compare-status') }; }""")

            shot = 'shot_infographic_benefits'
            shared.select_make_shot(page, shot)
            page.wait_for_timeout(400)
            page.click('#rework-open')
            expect(page.locator('#rework-panel')).to_be_visible(timeout=30_000)
            page.check('#rework-mode-regenerate_original')
            page.fill('#rework-direction',
                      '按保留的人工文案重画：只按商品原照与已确认事实，不新增印字或不存在的卖点。')
            page.click('#rework-preview')
            first = preview(page)
            snap['preview_before_choice'] = {k: first[k] for k in ('meta', 'cost', 'choice_present', 'error')}
            if first['choice_present']:
                page.select_option('#rework-prompt-choice', 'keep_manual')
                page.wait_for_timeout(400)
                page.click('#rework-preview')
                second = preview(page)
                snap['preview_after_choice'] = {k: second[k] for k in ('meta', 'cost', 'error', 'submit_disabled')}
                if not second['error_hidden'] and (second['error'] or '').strip():
                    raise AssertionError(f'保留人工全文后预览失败：{second["error"]}')
            else:
                snap['preview_after_choice'] = None
            snap['preview_text_len'] = len((second if first['choice_present'] else first)['text'] or '')
            page.click('#rework-submit')
            expect(page.locator('#rework-panel')).to_be_hidden(timeout=60_000)
            shared.wait_terminal(page, [shot], timeout=300_000)
            snap['info_state_after_submit'] = row_state(page, shot)
            if snap['info_state_after_submit']['attempt'] != 'succeeded':
                raise AssertionError(f'info 终态不是 succeeded：{snap["info_state_after_submit"]}')
            shared.adopt_make_shot(page, shot)
            page.wait_for_timeout(1500)
            snap['info_state_after_adopt'] = row_state(page, shot)
            page.screenshot(path=str(HERE / 'b19-info-after.png'), full_page=True)

            stage_nav.goto(page, 'deliver')
            page.wait_for_timeout(1200)
            snap['gate_rows'] = page.evaluate(
                """() => [...document.querySelectorAll('#delivery-gate [data-shot-id]')]
                     .map((node) => ({ shot: node.dataset.shotId,
                                       state: node.dataset.selectionState || '',
                                       text: (node.textContent || '').trim().slice(0, 160) }))""")
            snap['export_enabled'] = not page.locator('#deliver-export').is_disabled()
            page.screenshot(path=str(HERE / 'b19-gate.png'), full_page=True)
            EXPORTS.mkdir(exist_ok=True)
            with page.expect_download(timeout=180_000) as info_dl:
                page.click('#deliver-project-package')
            info_dl.value.save_as(str(EXPORTS / 'b19-project.zip'))
            page.wait_for_timeout(1200)
            with page.expect_download(timeout=180_000) as del_dl:
                page.click('#deliver-export')
            del_dl.value.save_as(str(EXPORTS / 'b19-delivery.zip'))
            snap['exports'] = {
                'project_bytes': (EXPORTS / 'b19-project.zip').stat().st_size,
                'delivery_bytes': (EXPORTS / 'b19-delivery.zip').stat().st_size}
            snap['console_errors'] = console[-20:]
            context.close()
    finally:
        host.terminate()
        try:
            host.wait(timeout=20)
        except subprocess.TimeoutExpired:
            host.kill()
        OUT.write_bytes((json.dumps(snap, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({k: snap.get(k) for k in ('detail_state_before', 'detail_confirm', 'preview_before_choice',
                                               'preview_after_choice', 'info_state_after_adopt',
                                               'gate_rows', 'export_enabled', 'exports')},
                     ensure_ascii=False, indent=1)[:4000])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
