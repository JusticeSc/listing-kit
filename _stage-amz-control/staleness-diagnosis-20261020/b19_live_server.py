"""B19 受控真实宿主：只放行两条已预留形状的图像 POST，其余在进程内拒绝。

形状 = 当前 models 设置（DashScope qwen-image-3.0，1344*1344，n=1，prompt_extend=false，
watermark=false），输入图只有商品原照。记录只含公开 prompt/参数与解码后的图片身份，
不落 header、密钥、base64、签名 URL 或响应体。
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

TRACE = Path(__file__).with_name('b19-actual-outbound.json')
ORIGINAL = '4c4ed76c61c959ace082f8f3698f1b10bf0e1c942c2b1e524b1e62086d4df1e1'
MAX_POSTS = 2
SHAPE = {
    'model': 'qwen-image-3.0',
    'images': [ORIGINAL],
    'parameters': {'size': '1344*1344', 'n': 1, 'prompt_extend': False, 'watermark': False},
}
records = json.loads(TRACE.read_text(encoding='utf-8')) if TRACE.exists() else []
lock = threading.Lock()
environ = dict(os.environ, AMZ_V2_DEFAULT_TRIAL='open')


def save_trace() -> None:
    TRACE.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


class ReservedTransport:
    def __init__(self) -> None:
        self.used = 0

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
            shape = {'model': body['model'], 'images': [image['sha256'] for image in images],
                     'parameters': body['parameters']}
            if json.dumps(shape, sort_keys=True) != json.dumps(SHAPE, sort_keys=True):
                raise ValueError('request does not match the reserved shape')
            with lock:
                if self.used >= MAX_POSTS:
                    raise ValueError('reserved submission count exhausted')
                self.used += 1
                prompt = next(item['text'] for item in content if 'text' in item)
                row = {'observed_at': datetime.now(timezone.utc).isoformat(),
                       'model': body['model'], 'parameters': body['parameters'],
                       'prompt': prompt,
                       'prompt_sha256': hashlib.sha256(prompt.encode('utf-8')).hexdigest(),
                       'images': images, 'upstream_outcome': 'unknown'}
                records.append(row)
                save_trace()
        response = _requests_transport(method, url, **kwargs)
        if row is not None:
            row['http_status'] = response.status_code
            row['upstream_outcome'] = 'HTTP response received; product must verify task/result'
            save_trace()
        return response


transport = ReservedTransport()
server = create_product_v2_server('127.0.0.1', 5512,
    image_provider_factory=lambda: create_default_image_provider(environ=environ, transport=transport))
server.start()
print('B19 real product ready on 5512; provider POST limit 2; no request sent', flush=True)
try:
    threading.Event().wait()
finally:
    server.stop()
