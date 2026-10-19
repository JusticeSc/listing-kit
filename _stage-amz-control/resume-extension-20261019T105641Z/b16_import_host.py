"""Throwaway host (port 5505) for importing the downloaded project package into a
clean origin. Its image provider refuses every call, so no request can leave."""
from __future__ import annotations

from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.product_v2_server import create_product_v2_server


class RefusingProvider:
    def submit(self, request):  # noqa: ANN001
        raise RuntimeError('this host performs no provider calls')

    def status(self, request):  # noqa: ANN001
        raise RuntimeError('this host performs no provider calls')

    def result(self, request):  # noqa: ANN001
        raise RuntimeError('this host performs no provider calls')


server = create_product_v2_server('127.0.0.1', int(__import__('os').environ.get('B16_IMPORT_PORT', '5505')),
    image_provider_factory=RefusingProvider)
server.start()
print(f"B16 import host ready on {server.port if hasattr(server, 'port') else 'configured port'}; "
      "provider refuses every call", flush=True)
try:
    threading.Event().wait()
finally:
    server.stop()
