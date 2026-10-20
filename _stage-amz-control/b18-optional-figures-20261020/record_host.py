"""Throwaway host (port 5516) that records each product submission's outbound shape
and then refuses to send it. Zero cost: nothing leaves this process.

Only public request parts are recorded (model, parameters, prompt text, decoded image
sha256/byte length); no headers, keys, signed URLs or base64 are persisted.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.product_v2_server import create_product_v2_server
from src.providers.v2_dashscope_image import CREATE_PATH, create_default_image_provider

TRACE = Path(__file__).with_name('recorded-shapes.json')
records: list[dict] = []
lock = threading.Lock()
environ = dict(os.environ, AMZ_V2_DEFAULT_TRIAL='open')


def save() -> None:
    TRACE.write_bytes((json.dumps(records, ensure_ascii=False, indent=2) + '\n')
                      .encode('utf-8'))


class RecordingRefusingTransport:
    def request(self, method, url, **kwargs):
        if method == 'POST' and url.endswith(CREATE_PATH):
            body = kwargs['json']
            content = body['input']['messages'][0]['content']
            images = []
            for item in content:
                if 'image' in item:
                    media, encoded = item['image'].split(',', 1)
                    raw = base64.b64decode(encoded, validate=True)
                    images.append({'sha256': hashlib.sha256(raw).hexdigest(),
                                   'bytes': len(raw),
                                   'media_type': media.removeprefix('data:')
                                   .removesuffix(';base64')})
            prompt = next(item['text'] for item in content if 'text' in item)
            with lock:
                records.append({
                    'recorded_at': datetime.now(timezone.utc).isoformat(),
                    'url': url,
                    'model': body.get('model'),
                    'parameters': body.get('parameters'),
                    'prompt_chars': len(prompt),
                    'prompt_head': prompt[:400],
                    'images': images,
                })
                save()
        raise RuntimeError('recording host: no request leaves this process')


server = create_product_v2_server(
    '127.0.0.1', int(os.environ.get('B18_RECORD_PORT', '5516')),
    image_provider_factory=lambda: create_default_image_provider(
        environ=environ, transport=RecordingRefusingTransport()))
server.start()
print('B18 recording host ready; provider records and refuses every call', flush=True)
try:
    threading.Event().wait()
finally:
    server.stop()
