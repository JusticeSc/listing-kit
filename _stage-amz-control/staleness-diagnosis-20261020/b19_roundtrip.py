"""B19 收尾四：把刷新后的项目包导入全新 origin，核对文档/资产并再导出（零模型调用）。"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from playwright.sync_api import sync_playwright  # noqa: E402

import v2_stage_nav as stage_nav  # noqa: E402

PORT = 5507
PACKAGE = HERE / 'b19-exports' / 'b19-project-post-suite.zip'
OUT = HERE / 'b19-roundtrip.json'
EXPORTS = HERE / 'b19-exports'
HOST = ROOT / '_stage-amz-control' / 'resume-extension-20261019T105641Z' / 'b16_import_host.py'

READ_LIBRARY = """async () => {
  const db = await new Promise((resolve, reject) => {
    const request = indexedDB.open('amz-listing-kit-v2');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  const docs = await new Promise((resolve, reject) => {
    const tx = db.transaction('documents', 'readonly');
    const out = [];
    tx.objectStore('documents').openCursor().onsuccess = (event) => {
      const cursor = event.target.result;
      if (!cursor) { resolve(out); return; }
      const value = cursor.value;
      out.push({ kind: value.kind, document_id: value.document_id, version: value.version,
                 schema_version: value.schema_version, payload: value.payload });
      cursor.continue();
    };
    tx.onerror = () => reject(tx.error);
  });
  const metas = await new Promise((resolve, reject) => {
    const tx = db.transaction('assets', 'readonly');
    const out = [];
    tx.objectStore('assets').openCursor().onsuccess = (event) => {
      const cursor = event.target.result;
      if (!cursor) { resolve(out); return; }
      const value = cursor.value;
      out.push({ sha256: value.sha256, byte_size: value.byte_size, blob: value.blob });
      cursor.continue();
    };
    tx.onerror = () => reject(tx.error);
  });
  const assets = [];
  for (const meta of metas) {
    const buffer = await meta.blob.arrayBuffer();
    const digest = await crypto.subtle.digest('SHA-256', buffer);
    const hex = [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
    assets.push({ sha256: meta.sha256, byte_size: meta.byte_size, digest: hex });
  }
  db.close();
  return { docs, assets };
}"""


def wait_ready(port: int, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            sock.settimeout(0.5)
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                return
        time.sleep(0.2)
    raise SystemExit(f'host on {port} never became reachable')


def package_docs(path: Path) -> dict:
    out: dict[tuple, dict] = {}
    assets: dict[str, dict] = {}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.startswith('documents/'):
                doc = json.loads(zf.read(name).decode('utf-8'))
                out[(doc['kind'], doc['document_id'], doc['version'])] = doc
            elif name.startswith('assets/'):
                raw = zf.read(name)
                assets[hashlib.sha256(raw).hexdigest()] = {'bytes': len(raw), 'member': name}
        manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
    return {'docs': out, 'assets': assets, 'manifest': manifest}


def main() -> int:
    env = dict(os.environ, B16_IMPORT_PORT=str(PORT))
    host = subprocess.Popen([sys.executable, str(HOST)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            encoding='utf-8')
    profile = Path(tempfile.mkdtemp(prefix='b19-import-'))
    snap: dict = {'package': str(PACKAGE), 'package_bytes': PACKAGE.stat().st_size}
    try:
        wait_ready(PORT)
        with sync_playwright() as pw:
            context = pw.chromium.launch_persistent_context(
                str(profile), headless=True, viewport={'width': 1440, 'height': 950},
                accept_downloads=True)
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(60_000)
            page.goto(f'http://127.0.0.1:{PORT}/', wait_until='domcontentloaded')
            page.wait_for_selector('#import-file', state='attached', timeout=60_000)
            page.wait_for_function(
                "() => { const b=document.getElementById('import-trigger'); return Boolean(b && !b.disabled); }",
                timeout=60_000)
            snap['projects_before'] = page.evaluate(
                "() => document.querySelectorAll('#project-list .project-row').length")
            page.set_input_files('#import-file', str(PACKAGE))
            try:
                page.wait_for_function(
                    """() => { const n = document.getElementById('home-status');
                         const e = document.getElementById('home-error');
                         const st = n ? (n.textContent || '') : '';
                         const er = e ? (e.textContent || '') : '';
                         return st.includes('已导入') || er.trim().length > 0; }""", timeout=240_000)
            except Exception as exc:  # noqa: BLE001
                snap['import_wait_error'] = str(exc)[:300]
            snap['import_status'] = page.evaluate(
                "() => { const n = document.getElementById('home-status'); return n ? (n.textContent || '') : null; }")
            snap['import_error'] = page.evaluate(
                "() => { const n = document.getElementById('home-error'); return n ? (n.textContent || '') : null; }")
            snap['rows_after_import'] = page.evaluate(
                "() => document.querySelectorAll('#project-list .project-row').length")
            if not (snap['import_status'] or '').startswith('已导入'):
                raise AssertionError(f"导入未成功: {snap['import_status']!r} / {snap['import_error']!r}")
            page.wait_for_timeout(800)
            page.click('#project-list .project-row button[data-action="open"]')
            page.wait_for_selector('#project-view:not([hidden])', timeout=60_000)
            snap['imported_project'] = page.get_attribute('#project-view', 'data-project-id')
            first = page.evaluate(READ_LIBRARY)
            page.reload(wait_until='domcontentloaded')
            page.wait_for_selector('#project-view:not([hidden])', timeout=60_000)
            second = page.evaluate(READ_LIBRARY)
            stage_nav.goto(page, 'deliver')
            page.wait_for_timeout(1200)
            with page.expect_download(timeout=180_000) as dl:
                page.click('#deliver-project-package')
            reexport = EXPORTS / 'b19-project-reexported.zip'
            dl.value.save_as(str(reexport))
            context.close()

        pkg = package_docs(PACKAGE)
        # 导入后的库与包内容逐条比较
        lib_docs = {(d['kind'], d['document_id'], d['version']): d for d in first['docs']}
        missing = [k for k in pkg['docs'] if k not in lib_docs]
        extra = [k for k in lib_docs if k not in pkg['docs']]
        diff = [k for k in pkg['docs'] if k in lib_docs and lib_docs[k]['payload'] != pkg['docs'][k]['payload']]
        lib_assets = {a['sha256']: a for a in first['assets']}
        asset_ok = all(a['digest'] == a['sha256'] for a in first['assets'])
        snap['library_vs_package'] = {
            'package_docs': len(pkg['docs']), 'library_docs': len(lib_docs),
            'missing': missing[:10], 'extra': extra[:10], 'payload_diff': diff[:10],
            'package_assets': len(pkg['assets']), 'library_assets': len(lib_assets),
            'asset_sha_set_equal': set(pkg['assets']) == set(lib_assets),
            'asset_digest_self_consistent': asset_ok,
        }
        snap['reload_stable'] = (
            len(second['docs']) == len(first['docs'])
            and sorted((d['kind'], d['document_id'], d['version']) for d in second['docs'])
            == sorted((d['kind'], d['document_id'], d['version']) for d in first['docs']))
        snap['reexport'] = {'path': str(reexport), 'bytes': reexport.stat().st_size}
        again = package_docs(reexport)
        added = [k for k in again['docs'] if k not in pkg['docs']]
        removed = [k for k in pkg['docs'] if k not in again['docs']]
        snap['reexport_vs_source'] = {
            'docs': len(again['docs']), 'added_kinds': sorted({k[0] for k in added}),
            'added': added, 'removed': removed,
            'assets_equal': set(again['assets']) == set(pkg['assets']),
        }
    finally:
        host.terminate()
        try:
            host.wait(timeout=20)
        except subprocess.TimeoutExpired:
            host.kill()
        shutil.rmtree(profile, ignore_errors=True)
        OUT.write_bytes((json.dumps(snap, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(json.dumps(snap, ensure_ascii=False, indent=1)[:3000])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
