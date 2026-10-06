"""NOT-AUTHORITY: offline R2.2 prototype server; never a production entry.

All upstream factories are explicitly fake. Control JSON selects a fake outcome,
not a project record. Browser IndexedDB remains the real project authority.
"""
from __future__ import annotations

import json
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.v2_test_server import V2StaticHandler  # noqa: E402
from src.providers.v2_fake_image import FakeImageProvider  # noqa: E402
from src.providers.v2_fake_review import FakeReviewProvider  # noqa: E402
from src.providers.v2_fake_semantic import FakeSemanticProvider  # noqa: E402
from src.providers.v2_fake_suite_review import FakeSuiteReviewProvider  # noqa: E402

CONTROL = Path(__file__).with_name('workbench-prototype-control.json')


def image_provider() -> FakeImageProvider:
    scenario = json.loads(CONTROL.read_text(encoding='utf-8'))['image_scenario']
    return FakeImageProvider(scenario=scenario, size=1200)


if __name__ == '__main__':
    server = ThreadingHTTPServer(('127.0.0.1', int(sys.argv[1])), V2StaticHandler)
    server.provider_factory = lambda: FakeSemanticProvider(scenario='ok')
    server.image_provider_factory = image_provider
    server.review_provider_factory = lambda: FakeReviewProvider(scenario='ok')
    server.suite_review_provider_factory = lambda: FakeSuiteReviewProvider(scenario='ok')
    print(f'PROTOTYPE_READY http://127.0.0.1:{server.server_address[1]}', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
