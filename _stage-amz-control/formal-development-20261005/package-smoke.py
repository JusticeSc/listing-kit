from pathlib import Path
import json
import math
import sys
import tempfile
import zipfile
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = Path(__file__).parent
DOWNLOADS = ARTIFACTS / 'downloads'
results = []
zoom = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
window_width = int(sys.argv[2]) if len(sys.argv) > 2 else 1440
label = f'zoom{round(zoom * 100)}-{window_width}'
with tempfile.TemporaryDirectory(prefix='amz-formal-dev-chrome-') as profile:
    preferences = Path(profile) / 'Default' / 'Preferences'
    preferences.parent.mkdir(parents=True)
    preferences.write_text(json.dumps({'partition': {
        'default_zoom_level': {'x': math.log(zoom) / math.log(1.2)}}}), encoding='utf-8')
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(profile, channel='chrome', headless=True,
            accept_downloads=True, no_viewport=True,
            args=['--force-device-scale-factor=1', f'--window-size={window_width},900'])
        try:
            page = context.pages[0]
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto('http://127.0.0.1:53436/', wait_until='networkidle')
            metrics = page.evaluate('''() => ({
                innerWidth, innerHeight, outerWidth, outerHeight, dpr:devicePixelRatio,
                visualScale:visualViewport.scale, cssZoom:getComputedStyle(document.documentElement).zoom,
                transform:getComputedStyle(document.documentElement).transform
            })''')
            assert abs(metrics['dpr'] - zoom) < 0.001, metrics
            assert metrics['outerWidth'] == window_width, metrics
            assert metrics['visualScale'] == 1 and metrics['cssZoom'] == '1', metrics
            page.wait_for_selector('#create-project:not([disabled])')
            page.wait_for_selector('#import-trigger:not([disabled])')
            page.set_input_files('#import-file', str(DOWNLOADS / 'project-source.zip'))
            page.wait_for_selector('#project-list button[data-action="open"]', timeout=20000)
            page.click('#project-list button[data-action="open"]')
            page.wait_for_selector('#project-view:not([hidden])', timeout=20000)
            page.click('[data-stage-nav="deliver"]')
            page.wait_for_selector('#deliver-export:not([disabled])', timeout=20000)
            for selector, target in [('#deliver-export', 'delivery-downloaded.zip'),
                                     ('#deliver-project-package', 'project-downloaded.zip')]:
                page.focus(selector)
                with page.expect_download(timeout=20000) as waiting:
                    page.keyboard.press('Enter')
                download = waiting.value
                assert download.failure() is None
                destination = DOWNLOADS / (label + '-' + target)
                download.save_as(str(destination))
                with zipfile.ZipFile(destination) as archive:
                    bad = archive.testzip()
                    assert bad is None, bad
                    names = archive.namelist()
                    manifest = json.loads(archive.read('manifest.json'))
                results.append({'file': target, 'name': download.suggested_filename,
                                'bytes': destination.stat().st_size, 'members': len(names),
                                'manifest': manifest})
            assert errors == [], errors
            overflow = page.evaluate('document.documentElement.scrollWidth > innerWidth')
            assert not overflow
            page.screenshot(path=str(ARTIFACTS / (label + '-delivery-page.png')), full_page=True)
            (ARTIFACTS / (label + '-package-smoke.json')).write_text(json.dumps({'results': results,
                'metrics': metrics, 'overflow': overflow, 'page_errors': errors,
                'boundary': 'Isolated Chrome headless; genuine browser zoom preference; local fake provider; no paid calls'},
                ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'packages': [{'file': r['file'], 'bytes': r['bytes'], 'members': r['members']}
                                          for r in results], 'metrics': metrics,
                              'overflow': overflow, 'page_errors': errors}, ensure_ascii=False))
        finally:
            context.close()
