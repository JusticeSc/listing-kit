"""B19 收尾三：导出整套检查重跑之后的项目包（零模型调用）。"""
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
    env = dict(os.environ, AMZ_V2_DEFAULT_TRIAL='OPEN_UNUSED')
    host = subprocess.Popen([sys.executable, str(HOST)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding='utf-8')
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
            with page.expect_download(timeout=180_000) as dl:
                page.click('#deliver-project-package')
            target = EXPORTS / 'b19-project-post-suite.zip'
            dl.value.save_as(str(target))
            print('project package', target.stat().st_size)
            context.close()
    finally:
        host.terminate()
        try:
            host.wait(timeout=20)
        except subprocess.TimeoutExpired:
            host.kill()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
