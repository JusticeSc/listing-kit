"""零收费诊断：在真实界面里对两张 stale 图做「用户会做的事」，看新依据是否真的改变正文。

步骤（只用本地准备，不调用模型；宿主 provider 全部拒绝）：
1. 导入真实项目包；
2. 方案阶段把卖点信息图的印字决定改成「不印新增文字」（用户 2026-10-20 明确选择）；
3. 制作阶段：细节图（系统稿）点「重新本地准备」，信息图（人工全文）点「按当前依据确认此人工全文」；
4. 抓取每张图准备前后的版本、正文、Prompt 哈希，以及卡片上的过期标记。
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

PORT = 5511
PACKAGE = (ROOT / '_stage-amz-control/resume-extension-20261019T105641Z/packages/'
           '真实闭环-·-参考图-20261019-1307.zip')
HOST = ROOT / '_stage-amz-control/resume-extension-20261019T105641Z/b16_import_host.py'
OUT = HERE / 'prepare-evidence.json'
SHOTS = ('shot_detail_material', 'shot_infographic_benefits')


def wait_ready(port: int, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                return
        time.sleep(0.2)
    raise SystemExit(f'host on {port} never became reachable')


def prompt_card(page, shot_id: str):
    return page.locator(f'#prompt-list .shot-spec[data-shot-id="{shot_id}"]')


def read_card(page, shot_id: str) -> dict:
    card = prompt_card(page, shot_id)
    card.wait_for(state='visible', timeout=30_000)
    return {
        'head': card.locator('.shot-spec-head').inner_text(),
        'text': card.locator('pre.prompt-text').inner_text(),
        'hash_line': card.locator('.prompt-hash').inner_text(),
        'stale_badge': card.locator('.badge.is-critical:has-text("已过期")').count() > 0,
        'stale_note': card.locator('.prompt-warning').count(),
        'button': card.locator('.toolbar button').first.inner_text(),
    }


def main() -> int:
    env = dict(os.environ, B16_IMPORT_PORT=str(PORT))
    host = subprocess.Popen([sys.executable, str(HOST)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding='utf-8')
    snap: dict = {'package': PACKAGE.name, 'provider': 'refusing (no calls)',
                  'print_decision': 'none (user 2026-10-20)'}
    try:
        wait_ready(PORT)
        with sync_playwright() as pw:
            profile = Path(tempfile.mkdtemp(prefix='stale-diag-'))
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={'width': 1440, 'height': 950})
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(45_000)
            errors: list[str] = []
            page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
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

            stage_nav.goto(page, 'plan')
            page.locator('details:has(#specs-section) > summary').first.click()
            spec_card = page.locator('#shot-spec-list .shot-spec[data-shot-id="shot_infographic_benefits"]')
            spec_card.wait_for(state='visible', timeout=30_000)
            before_spec = spec_card.locator('.shot-spec-head').inner_text()
            page.locator('#spec-print-none-shot_infographic_benefits').check()
            spec_card.locator('button:has-text("保存")').first.click()
            page.wait_for_function(
                """(before) => {
                   const card = document.querySelector('#shot-spec-list .shot-spec[data-shot-id="shot_infographic_benefits"]');
                   const head = card && card.querySelector('.shot-spec-head');
                   return head && head.innerText !== before; }""", arg=before_spec, timeout=30_000)
            snap['spec'] = {
                'before': before_spec,
                'after': spec_card.locator('.shot-spec-head').inner_text(),
                'error': page.locator('#specs-error').inner_text(),
                'selection': page.evaluate(
                    """() => { const n = document.getElementById('spec-print-none-shot_infographic_benefits');
                         return n ? n.checked : null; }"""),
            }

            stage_nav.goto(page, 'make')
            page.locator('#prompt-details > summary').click()
            snap['before'] = {shot: read_card(page, shot) for shot in SHOTS}
            page.screenshot(path=str(HERE / 'before.png'), full_page=True)

            detail = prompt_card(page, 'shot_detail_material')
            detail.locator('.toolbar button').first.click()
            page.wait_for_function(
                """(before) => {
                   const card = document.querySelector('#prompt-list .shot-spec[data-shot-id="shot_detail_material"]');
                   const head = card && card.querySelector('.shot-spec-head');
                   return head && head.innerText !== before; }""",
                arg=snap['before']['shot_detail_material']['head'], timeout=90_000)
            snap['after_detail'] = read_card(page, 'shot_detail_material')

            info = prompt_card(page, 'shot_infographic_benefits')
            buttons = info.locator('.toolbar button')
            labels = [buttons.nth(i).inner_text() for i in range(buttons.count())]
            snap['info_buttons'] = labels
            reconfirm = info.locator('button:has-text("按当前依据确认此人工全文")')
            if reconfirm.count() == 0:
                raise AssertionError(f'人工全文记录没有「按当前依据确认」入口，实际按钮：{labels}')
            reconfirm.first.click()
            page.wait_for_function(
                """(before) => {
                   const card = document.querySelector('#prompt-list .shot-spec[data-shot-id="shot_infographic_benefits"]');
                   const head = card && card.querySelector('.shot-spec-head');
                   return head && head.innerText !== before; }""",
                arg=snap['before']['shot_infographic_benefits']['head'], timeout=90_000)
            snap['after_info'] = read_card(page, 'shot_infographic_benefits')
            page.screenshot(path=str(HERE / 'after.png'), full_page=True)
            snap['console_errors'] = errors[-20:]
            context.close()
    finally:
        host.terminate()
        try:
            host.wait(timeout=20)
        except subprocess.TimeoutExpired:
            host.kill()
        OUT.write_bytes((json.dumps(snap, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    summary = {
        'spec': snap.get('spec'),
        'before': {k: {'head': v['head'], 'stale': v['stale_badge'], 'len': len(v['text'])}
                   for k, v in snap.get('before', {}).items()},
        'after_detail': {k: snap['after_detail'][k] for k in ('head', 'stale_badge', 'hash_line')} if 'after_detail' in snap else None,
        'after_info': {k: snap['after_info'][k] for k in ('head', 'stale_badge', 'hash_line')} if 'after_info' in snap else None,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
