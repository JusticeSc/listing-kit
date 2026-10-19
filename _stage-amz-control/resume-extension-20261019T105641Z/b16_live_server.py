"""Throwaway formal-product host for one authorized bearing result; no business data.
Only public prompt/parameters and decoded image identities are recorded. Never
persist headers, keys, base64, signed URLs, response bodies, or exception text.
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
from src.providers.v2_dashscope_image import CREATE_PATH, create_default_image_provider, _requests_transport

TRACE = Path(__file__).with_name('b16-actual-outbound.json')
ORIGINAL = '4c4ed76c61c959ace082f8f3698f1b10bf0e1c942c2b1e524b1e62086d4df1e1'
EDIT_CANDIDATE = '7ab4d9e0eae3d4d5d005084ed6cdf0875f783c49b6d85c364beb14b79b32316b'
# Reserved 2026-10-19: the dimensions figure's garbled-annotation candidate (row
# b16-dimensions-nonumber-02) is edited together with the original photo.
DIMENSIONS_EDIT_SOURCE = '0a59b8afb1e95c51fc6d6c2ec2a8c2e9c6a89b04a398313d3b0dec34be47a0a1'
records = json.loads(TRACE.read_text(encoding='utf-8')) if TRACE.exists() else []
lock = threading.Lock()
environ = dict(os.environ, AMZ_V2_DEFAULT_TRIAL='open')
# Each product host start permits exactly one submission whose shape was reserved
# beforehand; anything else is refused locally before leaving the process.
PLANNED_SHAPES = [
    {'model': 'qwen-image-3.0', 'images': [ORIGINAL],
     'parameters': {'size': '1344*1344', 'n': 1, 'prompt_extend': False, 'watermark': False}},
    {'model': 'qwen-image-3.0', 'images': [EDIT_CANDIDATE, ORIGINAL],
     'parameters': {'size': '1344*1344', 'n': 1, 'prompt_extend': False, 'watermark': False}},
    {'model': 'qwen-image-3.0', 'images': [DIMENSIONS_EDIT_SOURCE, ORIGINAL],
     'parameters': {'size': '1344*1344', 'n': 1, 'prompt_extend': False, 'watermark': False}},
]


def save_trace() -> None:
    TRACE.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


class OneAuthorizedTransport:
    def __init__(self) -> None:
        self.consumed = False

    def request(self, method, url, **kwargs):
        row = None
        if method == 'POST' and url.endswith(CREATE_PATH):
            body = kwargs['json']
            content = body['input']['messages'][0]['content']
            images = []
            for item in content:
                if 'image' in item:
                    media, encoded = item['image'].split(',', 1)
                    raw = base64.b64decode(encoded, validate=True)
                    images.append({'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
                                   'media_type': media.removeprefix('data:').removesuffix(';base64')})
            shape = {'model': body['model'],
                     'images': [image['sha256'] for image in images],
                     'parameters': body['parameters']}
            if json.dumps(shape, sort_keys=True) not in {
                    json.dumps(item, sort_keys=True) for item in PLANNED_SHAPES}:
                raise ValueError('request does not match any reserved shape')
            with lock:
                if self.consumed:
                    raise ValueError('this product host already used its one reserved submission')
                self.consumed = True
                row = {'observed_at': datetime.now(timezone.utc).isoformat(),
                       'model': body['model'], 'parameters': body['parameters'],
                       'prompt': next(item['text'] for item in content if 'text' in item),
                       'images': images, 'upstream_outcome': 'unknown'}
                records.append(row)
                save_trace()
        response = _requests_transport(method, url, **kwargs)
        if row is not None:
            row['http_status'] = response.status_code
            row['upstream_outcome'] = 'HTTP response received; task/result must be verified by product'
            save_trace()
        return response


transport = OneAuthorizedTransport()
server = create_product_v2_server('127.0.0.1', 5504,
    image_provider_factory=lambda: create_default_image_provider(environ=environ, transport=transport))
server.start()
print('B16 real product ready on 5504; provider POST hard limit 1; no request sent', flush=True)
try:
    threading.Event().wait()
finally:
    server.stop()
