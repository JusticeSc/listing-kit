"""B19：在当前模型（qwen-image-3.0）下重画两张 stale 图并重新采用。

顺序（每张图都是一次用户会做的完整动作）：
 导入真实包 → 方案里给卖点信息图记下「不印新增文字」 → 制作里把人工全文按当前依据重新确认
 → 逐图确认单核对（模型/参数/Prompt/费用）→ 单次提交 → 等到终态 → 人工采用。
宿主 transport 只放行两条预留形状，其余在进程内拒绝。
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

PORT = 5512
PACKAGE = (ROOT / '_stage-amz-control/resume-extension-20261019T105641Z/packages/'
           '真实闭环-·-参考图-20261019-1307.zip')
HOST = HERE / 'b19_live_server.py'
OUT = HERE / 'b19-refresh.json'
EXPORTS = HERE / 'b19-exports'
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


def card(page, shot_id: str):
    return page.locator(f'#prompt-list .shot-spec[data-shot-id="{shot_id}"]')


def card_state(page, shot_id: str) -> dict:
    node = card(page, shot_id)
    return {
        'head': node.locator('.shot-spec-head').inner_text(),
        'stale': node.locator('.badge.is-critical:has-text("已过期")').count() > 0,
        'hash': node.locator('.prompt-hash').inner_text() if node.locator('.prompt-hash').count() else '',
        'text_len': len(node.locator('pre.prompt-text').inner_text()),
        'buttons': [node.locator('.toolbar button').nth(i).inner_text()
                    for i in range(node.locator('.toolbar button').count())],
    }


def main() -> int:
    env = dict(os.environ, AMZ_V2_DEFAULT_TRIAL='open', DASHSCOPE_API_KEY=os.environ['DASHSCOPE_API_KEY'])
    host = subprocess.Popen([sys.executable, str(HOST)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding='utf-8')
    snap: dict = {'package': PACKAGE.name, 'shots': list(SHOTS), 'provider_model': 'qwen-image-3.0'}
    try:
        wait_ready(PORT)
        with sync_playwright() as pw:
            profile = Path(tempfile.mkdtemp(prefix='b19-refresh-'))
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={'width': 1440, 'height': 950},
                accept_downloads=True)
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(45_000)
            console: list[str] = []
            page.on('console', lambda msg: console.append(msg.text) if msg.type == 'error' else None)
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
                """(before) => { const c = document.querySelector('#shot-spec-list .shot-spec'
                       + '[data-shot-id="shot_infographic_benefits"]');
                     const h = c && c.querySelector('.shot-spec-head');
                     return h && h.innerText !== before; }""", arg=before_spec, timeout=30_000)
            snap['spec'] = {'before': before_spec,
                            'after': spec_card.locator('.shot-spec-head').inner_text(),
                            'error': page.locator('#specs-error').inner_text()}

            stage_nav.goto(page, 'make')
            page.locator('#prompt-details > summary').click()
            snap['cards_before'] = {shot: card_state(page, shot) for shot in SHOTS}

            info = card(page, 'shot_infographic_benefits')
            if snap['cards_before']['shot_infographic_benefits']['stale']:
                reconfirm = info.locator('button:has-text("按当前依据确认此人工全文")')
                if reconfirm.count() == 0:
                    raise AssertionError(f'人工全文没有重新确认入口：{snap["cards_before"]["shot_infographic_benefits"]["buttons"]}')
                before_head = snap['cards_before']['shot_infographic_benefits']['head']
                reconfirm.first.click()
                page.wait_for_function(
                    """(before) => { const c = document.querySelector('#prompt-list .shot-spec'
                           + '[data-shot-id="shot_infographic_benefits"]');
                         const h = c && c.querySelector('.shot-spec-head');
                         return h && h.innerText !== before; }""", arg=before_head, timeout=90_000)
            snap['cards_ready'] = {shot: card_state(page, shot) for shot in SHOTS}
            for shot in SHOTS:
                if snap['cards_ready'][shot]['stale']:
                    raise AssertionError(f'{shot} 准备后仍然过期：{snap["cards_ready"][shot]}')
            page.screenshot(path=str(HERE / 'b19-prompts-ready.png'), full_page=True)

            snap['submissions'] = {}
            directions = {
                'shot_detail_material': '按商品原照重画这张细节图：保持材质、结构与刻字标识真实，不新增部件、文字或包装。',
                'shot_infographic_benefits': '按保留的人工文案重画：只按商品原照与已确认事实，不新增印字或不存在的卖点。',
            }
            manual = {'shot_infographic_benefits'}
            for shot in SHOTS:
                shared.select_make_shot(page, shot)
                page.wait_for_timeout(400)
                page.click('#rework-open')
                expect(page.locator('#rework-panel')).to_be_visible(timeout=30_000)
                page.check('#rework-mode-regenerate_original')
                if shot in manual:
                    page.select_option('#rework-prompt-choice', 'keep_manual')
                page.fill('#rework-direction', directions[shot])
                page.click('#rework-preview')
                page.wait_for_function(
                    """() => { const box = document.getElementById('rework-preview-box');
                         const text = document.getElementById('rework-preview-text');
                         const err = document.getElementById('rework-error');
                         return Boolean(box && !box.hidden && text && (text.textContent || '').trim())
                           || Boolean(err && !err.hidden && (err.textContent || '').trim()); }""",
                    timeout=120_000)
                preview = page.evaluate(
                    """() => { const el = (id) => { const n = document.getElementById(id);
                         return n ? (n.innerText || n.textContent || '') : null; };
                       return { meta: el('rework-preview-meta'), text: el('rework-preview-text'),
                                cost: el('rework-cost'), error: el('rework-error'),
                                error_hidden: (document.getElementById('rework-error') || {}).hidden,
                                submit_disabled: document.getElementById('rework-submit').disabled }; }""")
                if not preview['error_hidden'] and (preview['error'] or '').strip():
                    raise AssertionError(f'{shot} 返工预览失败：{preview["error"]}')
                if not (preview['text'] or '').strip():
                    raise AssertionError(f'{shot} 返工预览没有正文：{preview}')
                snap['submissions'][shot] = {'preview_meta': preview['meta'][:400],
                                             'preview_cost': preview['cost']}
                page.click('#rework-submit')
                expect(page.locator('#rework-panel')).to_be_hidden(timeout=60_000)
                shared.wait_terminal(page, [shot], timeout=300_000)
                state = page.get_attribute(
                    f'#task-list-mount [data-task-shot="{shot}"]', 'data-attempt-state')
                if state != 'succeeded':
                    raise AssertionError(f'{shot} 终态不是 succeeded：{state}')
                shared.adopt_make_shot(page, shot)
                snap['submissions'][shot]['state'] = state
                snap['submissions'][shot]['selection'] = page.get_attribute(
                    f'#task-list-mount [data-task-shot="{shot}"]', 'data-selection-state')
                page.screenshot(path=str(HERE / f'b19-{shot}.png'), full_page=True)

            stage_nav.goto(page, 'deliver')
            page.wait_for_timeout(800)
            snap['gate_rows'] = page.evaluate(
                """() => [...document.querySelectorAll('#delivery-gate [data-shot-id]')]
                     .map((node) => ({ shot: node.dataset.shotId,
                                       state: node.dataset.selectionState || '',
                                       text: (node.textContent || '').trim().slice(0, 160) }))""")
            snap['export_enabled'] = not page.locator('#deliver-export').is_disabled()
            page.screenshot(path=str(HERE / 'b19-gate.png'), full_page=True)
            EXPORTS.mkdir(exist_ok=True)
            with page.expect_download(timeout=120_000) as info_dl:
                page.click('#deliver-project-package')
            info_dl.value.save_as(str(EXPORTS / 'b19-project.zip'))
            page.wait_for_timeout(1000)
            with page.expect_download(timeout=120_000) as del_dl:
                page.click('#deliver-export')
            del_dl.value.save_as(str(EXPORTS / 'b19-delivery.zip'))
            snap['exports'] = {
                'project': str(EXPORTS / 'b19-project.zip'),
                'delivery': str(EXPORTS / 'b19-delivery.zip'),
                'project_bytes': (EXPORTS / 'b19-project.zip').stat().st_size,
                'delivery_bytes': (EXPORTS / 'b19-delivery.zip').stat().st_size,
            }
            snap['console_errors'] = console[-20:]
            context.close()
    finally:
        host.terminate()
        try:
            host.wait(timeout=20)
        except subprocess.TimeoutExpired:
            host.kill()
        OUT.write_bytes((json.dumps(snap, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps({k: snap.get(k) for k in ('spec', 'cards_ready', 'gate_rows', 'export_enabled',
                                               'exports', 'console_errors')},
                     ensure_ascii=False, indent=1)[:4000])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
