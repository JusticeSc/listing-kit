#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""百炼 qwen-image-3.0 图生图适配器 —— 新演示产品的唯一正式生成入口（D1.2 + D1.3）。

它解决的不是"再包一层"，而是 Phase 0 之前就存在的那个能力断点：

    旧路径（v2 legacy，`src/imagegen.py`，**不进入新产品正式路径**）
        只把文本发给模型 -> 模型生成背景 -> 本地把商品主体贴进去
    新路径（本文件）
        按顺序把 1-3 张商品参考图**真的**放进请求体 -> 模型直接参考商品图生成整图

三条不变量靠**代码守卫**成立，不靠调用方自觉：

    G-MODE  正式路径只接受 image_to_image；传 text_to_image 直接拒绝。
            Goal 明文禁止"用纯文生图冒充参考图生成"，所以拒绝必须发生在发请求之前。
    G-IMG   请求体里必须真的出现与参考图一一对应、**顺序一致**的图像字段，
            且逐个解码后的 sha256 等于送进去的那张图。守卫扫描的是**请求体本身**，
            不是调用方的声明 —— 声明可以写假话，请求体不行。
    G-EP    创建端点取自冻结的能力契约 `dashscope_contract.json`，
            且不接受被换成 wanx 文生图端点（端点混用会让"参考图真的进了模型"变成假话）。

D1.3 的幂等与未知：

    * action_id 由 (模型, 参考图哈希序列, 提示词哈希, seed, size) 推出；
    * intent 必须**在提交之前**落盘。提交读超时后，本地没有任何凭据能区分
      "请求到了服务" 与 "请求没到"，所以只能靠 action_id + 原 task_id 去核对，不能重建；
    * 轮询超时进入 UNKNOWN（不是失败），不自动重试；原 task_id 24 小时内仍可查询。

与 legacy 的另一处关键差别：**没有 mock 分支**。未配置 key 时直接拒绝，
不生成占位图 —— Goal 禁止用 mock 输出冒充参考图生成。

用法：
    python demo/provider/dashscope_i2i.py --self-test      # 全离线，0 次付费调用
    python demo/provider/dashscope_i2i.py --reconcile <task_id>
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = Path(__file__).resolve().parent / "dashscope_contract.json"

MODEL = "qwen-image-3.0"
CREATE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation"
TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
# v2 legacy 的文生图端点。它**不该**出现在新路径的任何请求里；列在这里是为了让"混用"可被断言。
LEGACY_T2I_CREATE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"

MODE_I2I = "image_to_image"
MODE_T2I = "text_to_image"

MIN_REFS, MAX_REFS = 1, 3          # 契约：图生图 1-3 张
MAX_REF_BYTES = 10 * 1024 * 1024   # 契约：单张不超过 10MB
SIDE_MIN, SIDE_MAX = 384, 2048     # 契约：建议每边 384-2048 px（超出只记警告，不阻断）
AREA_MIN, AREA_MAX = 512 * 512, 2048 * 2048
RATIO_MIN, RATIO_MAX = 1 / 8, 8.0
SEED_MAX = 2147483647
N_MIN, N_MAX = 1, 6
NEG_PROMPT_MAX = 500               # 契约：negative_prompt 上限 500 字符
DEFAULT_SIZE = "1344*1344"         # Phase 0 实测成功过的尺寸

MIME_BY_SUFFIX = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".bmp": "image/bmp", ".tif": "image/tiff",
    ".tiff": "image/tiff", ".gif": "image/gif",
}
IMAGE_KEY_HINTS = ("image", "images", "img", "ref", "reference", "mask",
                   "photo", "picture")


class ProviderGuardError(RuntimeError):
    """守卫拒绝。它必须在**发请求之前**抛出 —— 抛出即拒绝，不降级、不重试。"""


# ---------------------------------------------------------------- 契约

def load_contract() -> dict:
    """读冻结的能力契约。读不到就拒绝工作：能力未知即不支持，不许猜。"""
    if not CONTRACT_PATH.is_file():
        raise ProviderGuardError(
            "缺少能力契约 %s —— 能力未知即不支持；先跑 D1.1 的 doctor，不要凭范例库推定"
            % CONTRACT_PATH)
    data = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    eps = (data.get("endpoints") or {})
    if eps.get("create_async") != CREATE_URL or eps.get("query_task") != TASK_URL:
        raise ProviderGuardError(
            "能力契约里的端点与本模块常量不一致 —— 这是配置漂移，必须先对齐再生成")
    if (data.get("model") or {}).get("name") != MODEL:
        raise ProviderGuardError("能力契约里的模型名不是 %s" % MODEL)
    return data


CONTRACT = load_contract()


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def sha256_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def data_uri(path: Path) -> str:
    """参考图按契约以 data URI 送出；编码方式必须与 Phase 0 实发请求一致。"""
    mime = MIME_BY_SUFFIX.get(Path(path).suffix.lower())
    if mime is None:
        raise ProviderGuardError("不支持的参考图格式：%s" % path)
    return "data:%s;base64,%s" % (mime, base64.b64encode(Path(path).read_bytes()).decode("ascii"))


def decode_data_uri(value: str) -> bytes | None:
    if not isinstance(value, str) or not value.startswith("data:"):
        return None
    head, _, payload = value.partition(",")
    if "base64" not in head:
        return None
    try:
        return base64.b64decode(payload, validate=False)
    except Exception:
        return None


# ---------------------------------------------------------------- 参考图

@dataclass(frozen=True)
class Reference:
    path: Path
    sha256: str
    nbytes: int
    mime: str
    pixels: tuple[int, int] | None
    warnings: tuple[str, ...] = ()


def load_reference(path) -> Reference:
    """读一张参考图并做契约范围内的检查。顺序由调用方给出的列表决定，本函数不排序。"""
    p = Path(path)
    if not p.is_file():
        raise ProviderGuardError("参考图不存在：%s" % p)
    mime = MIME_BY_SUFFIX.get(p.suffix.lower())
    if mime is None:
        raise ProviderGuardError("不支持的参考图格式（契约允许 JPG/PNG/BMP/TIFF/WEBP/GIF）：%s" % p)
    blob = p.read_bytes()
    if len(blob) > MAX_REF_BYTES:
        raise ProviderGuardError("参考图超过契约上限 10MB：%s（%.1f MB）"
                                 % (p, len(blob) / 1024 / 1024))
    px = None
    warn: list[str] = []
    try:
        from PIL import Image
        with Image.open(p) as im:
            px = im.size
    except Exception as exc:                       # 读不出像素只降级为警告，不算契约违规
        warn.append("无法读取像素尺寸（%s）" % exc)
    if px and not (SIDE_MIN <= px[0] <= SIDE_MAX and SIDE_MIN <= px[1] <= SIDE_MAX):
        warn.append("边长 %dx%d 超出契约建议区间 %d-%d px（文档为建议值，故只记警告）"
                    % (px[0], px[1], SIDE_MIN, SIDE_MAX))
    return Reference(path=p, sha256=sha256_bytes(blob), nbytes=len(blob), mime=mime,
                     pixels=px, warnings=tuple(warn))


# ---------------------------------------------------------------- 参数守卫

def validate_size(size: str) -> str:
    if not isinstance(size, str) or "*" not in size:
        raise ProviderGuardError("size 必须形如 宽*高（DashScope 协议）：%r" % (size,))
    w_s, _, h_s = size.partition("*")
    try:
        w, h = int(w_s), int(h_s)
    except ValueError:
        raise ProviderGuardError("size 不是两个整数：%r" % (size,))
    if not (AREA_MIN <= w * h <= AREA_MAX):
        raise ProviderGuardError("size 面积 %d 超出契约区间 %d-%d：%s"
                                 % (w * h, AREA_MIN, AREA_MAX, size))
    if not (SIDE_MIN <= w <= SIDE_MAX and SIDE_MIN <= h <= SIDE_MAX):
        raise ProviderGuardError("size 单边超出契约区间 %d-%d：%s" % (SIDE_MIN, SIDE_MAX, size))
    if not (RATIO_MIN <= w / h <= RATIO_MAX):
        raise ProviderGuardError("size 宽高比超出契约区间 1:8-8:1：%s" % size)
    return size


def validate_seed(seed) -> int:
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ProviderGuardError("seed 必须是整数：%r" % (seed,))
    if not (0 <= seed <= SEED_MAX):
        raise ProviderGuardError("seed 超出契约区间 0-%d：%r" % (SEED_MAX, seed))
    return seed


def validate_n(n) -> int:
    if not isinstance(n, int) or isinstance(n, bool):
        raise ProviderGuardError("n 必须是整数（传字符串会被 400）：%r" % (n,))
    if not (N_MIN <= n <= N_MAX):
        raise ProviderGuardError("n 超出契约区间 %d-%d：%r" % (N_MIN, N_MAX, n))
    return n


# ---------------------------------------------------------------- 请求体与守卫

def build_request(*, mode: str, prompt: str, references, model: str = MODEL,
                  negative_prompt: str = "", size: str = DEFAULT_SIZE, seed: int,
                  n: int = 1, prompt_extend: bool = False, watermark: bool = False,
                  allow_prompt_rewrite: bool = False) -> dict:
    """构造请求体。这里是**唯一**能产出请求体的地方，所有守卫都在返回之前跑完。"""
    if mode != MODE_I2I:
        raise ProviderGuardError(
            "正式产品路径只接受 mode=%s，收到 %r。Goal 禁止用纯文生图（%s）冒充参考图生成，"
            "也不接受本地贴图等价模式。" % (MODE_I2I, mode, MODE_T2I))
    refs = [r if isinstance(r, Reference) else load_reference(r) for r in references]
    if not (MIN_REFS <= len(refs) <= MAX_REFS):
        raise ProviderGuardError(
            "参考图数量 %d 超出契约的 %d-%d 张。0 张等于纯文生图，超过 %d 张契约不保证支持。"
            % (len(refs), MIN_REFS, MAX_REFS, MAX_REFS))
    if not isinstance(prompt, str) or not prompt.strip():
        raise ProviderGuardError("提示词为空 —— 空提示词会把画面交给模型自由发挥，不是产品行为")
    if len(negative_prompt) > NEG_PROMPT_MAX:
        raise ProviderGuardError(
            "negative_prompt 长度 %d 超过契约上限 %d。契约是截断，那会让「发送的」与「记录的」不等，"
            "所以这里直接拒绝。" % (len(negative_prompt), NEG_PROMPT_MAX))
    if prompt_extend is not False and not allow_prompt_rewrite:
        raise ProviderGuardError(
            "prompt_extend=%r：3.0 系列默认会**改写**提示词，实际执行的文本就不等于界面上看到的文本。"
            "本产品要求两者相等，故默认拒绝；受控复验要开，必须显式允许并记录。"
            % (prompt_extend,))
    validate_size(size)
    validate_seed(seed)
    validate_n(n)

    content = [{"image": data_uri(r.path)} for r in refs] + [{"text": prompt}]
    body = {
        "model": model,
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": {
            "negative_prompt": negative_prompt,
            "prompt_extend": bool(prompt_extend),
            "watermark": bool(watermark),
            "size": size,
            "n": n,
            "seed": seed,
        },
    }
    # 构造完立刻自检：请求体里必须真的有序地带着这些图。跳过这一步的路径不存在。
    assert_references_in_body(body, refs)
    return body


def image_fields_in_body(body) -> list[tuple[str, object]]:
    """按遍历顺序列出承载图像像素的字段。

    判据同源于 `src/imagegen.py::_body_image_fields`：路径名命中图像词，或值本身是
    data:image/... / 图片 URL。写成扫描而不是按已知字段名判断，换模型族时不必改这里。
    """
    found: list[tuple[str, object]] = []

    def walk(node, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, "%s.%s" % (path, k) if path else str(k))
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                walk(v, "%s[%d]" % (path, i))
        elif node not in (None, "", [], {}):
            low = path.lower()
            if any(h in low for h in IMAGE_KEY_HINTS):
                found.append((path, node))
            elif isinstance(node, str) and (node.startswith("data:image")
                                            or (node.startswith("http")
                                                and low.endswith((".png", ".jpg", ".jpeg",
                                                                  ".webp", ".bmp")))):
                found.append((path, node))

    walk(body, "")
    return found


def assert_references_in_body(body, refs) -> list[str]:
    """G-IMG：图像字段的数量、顺序、内容都必须与送进去的参考图逐张对上。"""
    got = image_fields_in_body(body)
    if len(got) != len(refs):
        raise ProviderGuardError(
            "G-IMG 失败：请求体里扫描到 %d 个图像字段，参考图有 %d 张 —— 数量对不上就是"
            "「声称送了参考图」与「真的送了」不一致。" % (len(got), len(refs)))
    paths: list[str] = []
    for idx, ((path, value), ref) in enumerate(zip(got, refs)):
        decoded = decode_data_uri(value)
        if decoded is None:
            raise ProviderGuardError(
                "G-IMG 失败：第 %d 个图像字段 %s 不是 data URI（模型读不到本地路径）" % (idx + 1, path))
        if sha256_bytes(decoded) != ref.sha256:
            raise ProviderGuardError(
                "G-IMG 失败：第 %d 个图像字段 %s 的像素哈希 %s… 与第 %d 张参考图 %s… 不一致"
                " —— 顺序或内容被换过了。" % (idx + 1, path, sha256_bytes(decoded)[:12],
                                              idx + 1, ref.sha256[:12]))
        paths.append(path)
    return paths


def assert_endpoint_ok(url: str) -> str:
    """G-EP：只用契约里的创建端点；wanx 文生图端点在正式路径里一律拒绝。"""
    if url == LEGACY_T2I_CREATE_URL:
        raise ProviderGuardError(
            "G-EP 失败：正式路径不接受 v2 legacy 的文生图端点 %s —— 那条路只发文本，"
            "不带参考图。" % LEGACY_T2I_CREATE_URL)
    if url != CONTRACT["endpoints"]["create_async"]:
        raise ProviderGuardError("G-EP 失败：创建端点 %s 不在能力契约里" % url)
    return url


def request_fingerprint(body: dict) -> str:
    """请求哈希。与 Phase 0 实发请求的算法一致（sort_keys=True），因此可逐字复现。"""
    return sha256_bytes(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8"))


def compute_action_id(model: str, reference_shas, prompt_sha: str, seed: int, size: str) -> str:
    """付费动作的稳定身份。单张参考图时与 Phase 0 的算法逐字相同（已验证可复现）。"""
    return sha256_text("%s|%s|%s|%d|%s" % (model, "|".join(reference_shas), prompt_sha,
                                          seed, size))[:16]


# ---------------------------------------------------------------- 账本与产物

class Ledger:
    """最小账本：追加式 JSONL，一次付费动作一行，写在动作收尾时。

    在途动作不进账本（由 attempt 目录的 intent.json 表达）；没有被服务接受的请求
    （HTTP 非 200）也不进账本 —— 那不是一次付费动作。不提供"改写历史"的方法。
    """

    def __init__(self, path):
        self.path = Path(path)

    def records(self) -> list[dict]:
        if not self.path.is_file():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
        return out

    def append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def by_action(self, action_id: str) -> dict | None:
        for rec in reversed(self.records()):
            if rec.get("action_id") == action_id:
                return rec
        return None

    def by_task(self, task_id: str) -> dict | None:
        for rec in reversed(self.records()):
            if rec.get("task_id") == task_id:
                return rec
        return None


class AttemptStore:
    """一次付费动作的落盘目录：intent / 请求快照 / 原始响应 / 原始 PNG。不覆盖旧产物。"""

    def __init__(self, root):
        self.root = Path(root)

    def dir_for(self, action_id: str) -> Path:
        return self.root / action_id

    def raw_path(self, action_id: str) -> Path:
        return self.dir_for(action_id) / "raw.png"

    def has_result(self, action_id: str) -> bool:
        return self.raw_path(action_id).is_file()

    def read_intent(self, action_id: str) -> dict | None:
        p = self.dir_for(action_id) / "intent.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

    def write_json(self, action_id: str, name: str, data) -> Path:
        d = self.dir_for(action_id)
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                     encoding="utf-8", newline="\n")
        return p

    def read_json(self, action_id: str, name: str):
        p = self.dir_for(action_id) / name
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

    def write_raw(self, action_id: str, blob: bytes) -> Path:
        d = self.dir_for(action_id)
        d.mkdir(parents=True, exist_ok=True)
        p = d / "raw.png"
        if p.is_file() and p.read_bytes() != blob:
            raise ProviderGuardError("候选 %s 已存在且字节不同 —— 候选不可覆盖" % action_id)
        p.write_bytes(blob)
        return p

    def attempts(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(p.name for p in self.root.iterdir() if p.is_dir())


# ---------------------------------------------------------------- 传输层

class RequestsTransport:
    """真实网络。只在有 key 且真的要发请求时才被构造。"""

    def post(self, url, *, headers, json_body, timeout):   # noqa: A002 - 与 requests 对齐
        import requests
        return requests.post(url, headers=headers, json=json_body, timeout=timeout)

    def get(self, url, *, headers, timeout):
        import requests
        return requests.get(url, headers=headers, timeout=timeout)


def task_status_of(payload: dict) -> str:
    return str(((payload or {}).get("output") or {}).get("task_status") or "").upper()


def image_url_of(payload: dict) -> str | None:
    out = (payload or {}).get("output") or {}
    for choice in (out.get("choices") or []):
        for part in ((choice.get("message") or {}).get("content") or []):
            if isinstance(part, dict) and part.get("image"):
                return part["image"]
    for item in (out.get("results") or []):
        if isinstance(item, dict) and item.get("url"):
            return item["url"]
    return None


# ---------------------------------------------------------------- Provider

class Provider:
    """图生图正式路径。没有 mock 分支：没 key 就拒绝，不产占位图。"""

    def __init__(self, *, store: AttemptStore, ledger: Ledger, transport=None,
                 api_key: str | None = None, model: str = MODEL):
        self.store = store
        self.ledger = ledger
        self.transport = transport
        # api_key=None 才读环境变量；显式传 "" 就是"没有 key"，不偷偷回落 ——
        # 否则「我明确没给 key」会被环境变量悄悄满足，E8 那条判据就成了假的。
        self.api_key = os.getenv("DASHSCOPE_API_KEY", "") if api_key is None else api_key
        self.model = model

    # -- 只读状态 --------------------------------------------------
    def has_result(self, action_id: str) -> bool:
        return self.store.has_result(action_id)

    def unresolved(self) -> list[dict]:
        """未收尾的动作：有 intent 但没有成品。它们不是失败，是**未知**。"""
        out = []
        for aid in self.store.attempts():
            if self.store.has_result(aid):
                continue
            intent = self.store.read_intent(aid) or {}
            out.append({"action_id": aid, "status": intent.get("status"),
                        "task_id": intent.get("task_id"),
                        "submitted_at": intent.get("submitted_at")})
        return out

    def _headers(self) -> dict:
        if not self.api_key:
            raise ProviderGuardError(
                "未配置 DASHSCOPE_API_KEY —— 正式路径不提供 mock 或本地贴图替代，"
                "请在环境里配置 key 后再生成。")
        return {"Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
                "X-DashScope-Async": "enable"}

    # -- 提交 ------------------------------------------------------
    def submit(self, *, prompt: str, references, seed: int, size: str = DEFAULT_SIZE,
               negative_prompt: str = "", n: int = 1, prompt_extend: bool = False,
               watermark: bool = False, allow_prompt_rewrite: bool = False,
               poll_timeout_s: int = 300, poll_interval_s: int = 4) -> dict:
        """提交一次付费动作，并轮询到终态。返回动作记录（不改写历史产物）。"""
        refs = [r if isinstance(r, Reference) else load_reference(r) for r in references]
        body = build_request(mode=MODE_I2I, prompt=prompt, references=refs, model=self.model,
                             negative_prompt=negative_prompt, size=size, seed=seed, n=n,
                             prompt_extend=prompt_extend, watermark=watermark,
                             allow_prompt_rewrite=allow_prompt_rewrite)
        create_url = assert_endpoint_ok(CONTRACT["endpoints"]["create_async"])
        prompt_sha = sha256_text(prompt)
        ref_shas = [r.sha256 for r in refs]
        aid = compute_action_id(self.model, ref_shas, prompt_sha, seed, size)
        req_sha = request_fingerprint(body)

        base = {
            "action_id": aid, "mode": MODE_I2I, "model": self.model,
            "seed": seed, "size": size, "n": n, "prompt_extend": bool(prompt_extend),
            "prompt_sha256": prompt_sha, "request_sha256": req_sha,
            "reference_sha256": ref_shas, "reference_count": len(refs),
            "reference_files": [str(r.path) for r in refs],
        }

        if self.store.has_result(aid):
            return dict(base, status="SKIPPED_HAS_RESULT",
                        reason="同一 action 已有付费产出，不重复提交")

        prior = self.store.read_intent(aid)
        if prior and prior.get("status") in ("submitting", "submitted", "unknown_submit",
                                             "unknown_poll"):
            return dict(base, status="UNKNOWN_PENDING_RECONCILE",
                        task_id=prior.get("task_id"),
                        reason="存在未收尾的 intent（%s）—— 先核对原 task，不重新提交"
                               % prior.get("status"))

        transport = self.transport or RequestsTransport()
        headers = self._headers()          # 没 key 在这里就拒绝，且此时还没写 intent
        intent = dict(base, status="submitting", submitted_at=now_iso())
        self.store.write_json(aid, "intent.json", intent)     # 落盘必须在提交之前
        self.store.write_json(aid, "request.json", redact_request(body, refs))

        try:
            resp = transport.post(create_url, headers=headers, json_body=body, timeout=120)
        except Exception as exc:                               # 提交读超时/连接中断
            intent.update(status="unknown_submit", reason="%s: %s" % (type(exc).__name__, exc))
            self.store.write_json(aid, "intent.json", intent)
            self.ledger.append(dict(base, task_id=None, chargeable=None, status="UNKNOWN",
                                    at=now_iso(), note="提交结果未知，未自动重试"))
            return dict(base, status="UNKNOWN", reason=intent["reason"],
                        chargeable=None,
                        next_action="用 --reconcile-unknowns 核对账户任务列表；确认前不要重发")

        if getattr(resp, "status_code", 0) != 200:
            text = (getattr(resp, "text", "") or "")[:400]
            intent.update(status="submit_rejected", reason="HTTP %s: %s"
                          % (getattr(resp, "status_code", "?"), text))
            self.store.write_json(aid, "intent.json", intent)
            self.store.write_json(aid, "response-create.json", safe_json(resp))
            self.ledger.append(dict(base, task_id=None, chargeable=False, status="REJECTED",
                                    at=now_iso(), note=text))
            return dict(base, status="REJECTED", reason=intent["reason"], chargeable=False)

        created = resp.json()
        self.store.write_json(aid, "response-create.json", created)
        task_id = (created.get("output") or {}).get("task_id")
        if not task_id:
            intent.update(status="submitted_no_task_id", reason=str(created)[:300])
            self.store.write_json(aid, "intent.json", intent)
            self.ledger.append(dict(base, task_id=None, chargeable=None, status="UNKNOWN",
                                    at=now_iso(), note="HTTP 200 但未返回 task_id"))
            return dict(base, status="UNKNOWN", reason=intent["reason"], chargeable=None)

        intent.update(status="submitted", task_id=task_id)
        self.store.write_json(aid, "intent.json", intent)
        # 账本**不在这里**写：一次付费动作只写一行，且写在它收尾时（成功/失败/未知）。
        # 在途状态由 intent.json 表达。两处各写一份状态，就会各自漂。
        return self._finish(aid, base, task_id, transport, headers,
                            poll_timeout_s, poll_interval_s)

    def _finish(self, aid, base, task_id, transport, headers,
                poll_timeout_s, poll_interval_s) -> dict:
        deadline = time.time() + poll_timeout_s
        last: dict = {}
        while time.time() < deadline:
            try:
                r = transport.get(TASK_URL.format(task_id=task_id), headers=headers, timeout=60)
                last = r.json()
            except Exception as exc:                 # 轮询抖动不该让已付费的任务白跑
                last = {"_poll_error": "%s: %s" % (type(exc).__name__, exc)}
                time.sleep(poll_interval_s)
                continue
            st = task_status_of(last)
            if st in ("SUCCEEDED", "SUCCESS"):
                return self._download(aid, base, task_id, last, transport)
            if st in ("FAILED", "CANCELED", "UNKNOWN"):
                self.store.write_json(aid, "response-task.json", redact_response(last))
                intent = self.store.read_intent(aid) or {}
                intent.update(status="provider_" + st.lower(), task_id=task_id)
                self.store.write_json(aid, "intent.json", intent)
                self.ledger.append(dict(base, task_id=task_id, chargeable=True,
                                        status=st, at=now_iso()))
                return dict(base, status=st, task_id=task_id,
                            usage=last.get("usage"), reason=str(last)[:400])
            time.sleep(poll_interval_s)

        self.store.write_json(aid, "response-task.json", redact_response(last))
        intent = self.store.read_intent(aid) or {}
        intent.update(status="unknown_poll", task_id=task_id)
        self.store.write_json(aid, "intent.json", intent)
        self.ledger.append(dict(base, task_id=task_id, chargeable=True, status="UNKNOWN",
                                at=now_iso(), note="轮询超时，未自动重试"))
        return dict(base, status="UNKNOWN", task_id=task_id, usage=last.get("usage"),
                    reason="轮询超时（%ds）—— 任务可能仍在运行；用原 task_id 核对，不重新提交"
                           % poll_timeout_s)

    def _download(self, aid, base, task_id, payload, transport) -> dict:
        url = image_url_of(payload)
        if not url:
            self.store.write_json(aid, "response-task.json", redact_response(payload))
            return dict(base, status="SUCCEEDED_NO_IMAGE", task_id=task_id,
                        reason="任务成功但没有图片 URL：" + str(payload)[:300])
        blob = None
        last_exc = None
        for _ in range(3):                       # 结果 URL 只有 24 小时，下载失败要立刻重试
            try:
                blob = transport.get(url, headers={}, timeout=180).content
                break
            except Exception as exc:
                last_exc = exc
                time.sleep(3)
        if blob is None:
            self.store.write_json(aid, "response-task.json", redact_response(payload))
            return dict(base, status="DOWNLOAD_FAILED", task_id=task_id,
                        reason="下载失败：%s" % last_exc,
                        next_action="结果 URL 24 小时后失效；重新下载要尽快，不要重新生成")
        path = self.store.write_raw(aid, blob)
        self.store.write_json(aid, "response-task.json", redact_response(payload))
        usage = payload.get("usage") or {}
        rec = dict(base, status="SUCCEEDED", task_id=task_id, image_path=str(path),
                   image_sha256=sha256_bytes(blob), image_bytes=len(blob),
                   usage=usage, input_image_count=usage.get("input_image_count"),
                   rewrite_status=((payload.get("output") or {}).get("rewrite_status")),
                   submitted_at=(self.store.read_intent(aid) or {}).get("submitted_at"),
                   finished_at=now_iso())
        intent = self.store.read_intent(aid) or {}
        intent.update(status="completed", task_id=task_id, image_sha256=rec["image_sha256"])
        self.store.write_json(aid, "intent.json", intent)
        self.ledger.append(dict(base, task_id=task_id, chargeable=True, status="SUCCEEDED",
                                at=rec["finished_at"], image_sha256=rec["image_sha256"],
                                input_image_count=rec["input_image_count"]))
        return rec

    # -- 核对 ------------------------------------------------------
    def reconcile(self, task_id: str) -> dict:
        """用**原 task_id** 查询状态。Unknown 的唯一正确出口；它不产生新提交。"""
        transport = self.transport or RequestsTransport()
        headers = {"Authorization": "Bearer " + self.api_key} if self.api_key else {}
        r = transport.get(TASK_URL.format(task_id=task_id), headers=headers, timeout=60)
        payload = r.json()
        return {"task_id": task_id, "status": task_status_of(payload), "result": payload}

    def reconcile_unknowns(self) -> list[dict]:
        out = []
        for item in self.unresolved():
            tid = item.get("task_id")
            if not tid:
                out.append(dict(item, reconcile="无 task_id —— 只能查账户任务列表"))
                continue
            out.append(dict(item, reconcile=self.reconcile(tid)["status"]))
        return out


def redact_request(body: dict, refs) -> dict:
    """请求快照落盘时把参考图换成人读摘要：保留哈希与字节数，不落 base64 巨块。"""
    snap = json.loads(json.dumps(body))
    content = ((snap.get("input") or {}).get("messages") or [{}])[0].get("content") or []
    idx = 0
    for part in content:
        if isinstance(part, dict) and "image" in part:
            ref = refs[idx] if idx < len(refs) else None
            part["image"] = "<data-uri of reference #%d, sha256=%s, bytes=%s>" % (
                idx + 1, ref.sha256 if ref else "?", ref.nbytes if ref else "?")
            idx += 1
    return snap


def redact_response(payload: dict) -> dict:
    """临时签名 URL 不落盘：换成占位符，避免把 24 小时的凭据写成资产。"""
    out = json.loads(json.dumps(payload))
    from urllib.parse import urlparse
    for choice in ((out.get("output") or {}).get("choices") or []):
        for part in ((choice.get("message") or {}).get("content") or []):
            url = part.get("image")
            if isinstance(url, str) and url.startswith("http"):
                p = urlparse(url)
                part["image"] = "%s://%s/<redacted-path>?<redacted-query>" % (p.scheme, p.netloc)
    return out


def safe_json(resp) -> dict:
    try:
        return resp.json()
    except Exception:
        return {"_unparsed": (getattr(resp, "text", "") or "")[:600]}

# ---------------------------------------------------------------- 自检（离线，0 次付费调用）

FIXTURE = PROJECT / "evals/product-demo/fixture-design"
GOLDEN_DIR = FIXTURE / "ref-02-upper-closeup"
GOLDEN_REF = FIXTURE / "C" / "raw.png"


class FakeResponse:
    def __init__(self, status_code=200, payload=None, content=b""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.content = content
        self.text = json.dumps(self._payload, ensure_ascii=False)

    def json(self):
        return self._payload


class FakeTransport:
    """离线替身。它的存在是为了让「只提交一次」「超时进 UNKNOWN」「原 task 可查」
    这三条判据**能真的失败** —— 不能失败的判据等于装饰。"""

    def __init__(self, *, task_status="SUCCEEDED", image_bytes=b"\x89PNG\r\n\x1a\nfake-bytes"):
        self.post_calls = 0
        self.get_calls = 0
        self.task_status = task_status
        self.image_bytes = image_bytes
        self.created_task_id = "fake-task-0001"
        self.posted_bodies: list[dict] = []

    def post(self, url, *, headers, json_body, timeout):
        self.post_calls += 1
        self.posted_bodies.append(json_body)
        return FakeResponse(200, {"request_id": "fake-create",
                                  "output": {"task_id": self.created_task_id,
                                             "task_status": "PENDING"}})

    def get(self, url, *, headers, timeout):
        self.get_calls += 1
        if "/tasks/" in url:
            return FakeResponse(200, self._task_payload())
        return FakeResponse(200, {}, content=self.image_bytes)

    def _task_payload(self):
        out = {"task_id": self.created_task_id, "task_status": self.task_status}
        if self.task_status in ("SUCCEEDED", "SUCCESS"):
            out["choices"] = [{"finish_reason": "stop", "message": {
                "role": "assistant",
                "content": [{"image": "https://example.invalid/out.png", "type": "image"}]}}]
        return {"request_id": "fake-task", "output": out,
                "usage": {"input_image_count": 1, "output_width": 1344, "output_height": 1344}}


def _golden_case() -> dict | None:
    """Phase 0 真实发出去的那次图生图请求 —— 我们用它当"实发基准"。"""
    req = GOLDEN_DIR / "request.json"
    itt = GOLDEN_DIR / "intent.json"
    if not (req.is_file() and itt.is_file() and GOLDEN_REF.is_file()):
        return None
    recorded = json.loads(req.read_text(encoding="utf-8"))
    intent = json.loads(itt.read_text(encoding="utf-8"))
    content = recorded["input"]["messages"][0]["content"]
    text = next(p["text"] for p in content if isinstance(p, dict) and "text" in p)
    return {"recorded": recorded, "intent": intent, "text": text,
            "params": recorded["parameters"]}


def self_test() -> int:
    rows: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        rows.append((name, bool(ok), detail))

    def expect_refusal(name: str, fn, needle: str = "") -> None:
        try:
            fn()
        except ProviderGuardError as exc:
            record(name, (needle in str(exc)) if needle else True, "已拒绝：" + str(exc)[:120])
        except Exception as exc:                                    # noqa: BLE001
            record(name, False, "抛出的不是守卫异常：%r" % (exc,))
        else:
            record(name, False, "守卫没有拦住 —— 这条判据是假的")

    # A. 契约
    record("A 契约端点与常量一致，且不是 legacy 文生图端点",
           CREATE_URL == CONTRACT["endpoints"]["create_async"] != LEGACY_T2I_CREATE_URL,
           CREATE_URL)

    golden = _golden_case()
    # B. 黄金复现：我们的构造器必须能逐字重建"真的发出去过"的那次请求
    if golden is None:
        record("B 黄金复现（Phase 0 实发请求）", False,
               "夹具缺失，判据无法执行：%s" % GOLDEN_DIR)
    else:
        params = golden["params"]
        ref = load_reference(GOLDEN_REF)
        body = build_request(mode=MODE_I2I, prompt=golden["text"], references=[ref],
                             model=golden["recorded"]["model"],
                             negative_prompt=params["negative_prompt"], size=params["size"],
                             seed=params["seed"], n=params["n"],
                             prompt_extend=params["prompt_extend"], watermark=params["watermark"])
        got = request_fingerprint(body)
        want = golden["intent"]["request_sha256"]
        record("B1 黄金复现：请求哈希等于实发请求", got == want,
               "%s vs 记录 %s" % (got[:16], want[:16]))
        aid = compute_action_id(golden["recorded"]["model"], [ref.sha256],
                                sha256_text(golden["text"]), params["seed"], params["size"])
        record("B2 黄金复现：单参考图 action_id 等于 Phase 0 的动作身份",
               aid == golden["intent"]["action_id"],
               "%s vs 记录 %s" % (aid, golden["intent"]["action_id"]))
        fields = image_fields_in_body(body)
        record("B3 请求体里扫描到 1 个图像字段，且位置在人读文本之前",
               len(fields) == 1 and fields[0][0].endswith("content[0].image"),
               str([p for p, _ in fields]))

    # C. G-IMG 必须能失败
    refs1 = [load_reference(GOLDEN_REF)] if GOLDEN_REF.is_file() else []
    if refs1:
        ok_body = build_request(mode=MODE_I2I, prompt="p", references=refs1, negative_prompt="n",
                                size=DEFAULT_SIZE, seed=1)
        broken = json.loads(json.dumps(ok_body))
        broken["input"]["messages"][0]["content"] = [
            p for p in broken["input"]["messages"][0]["content"] if "image" not in p]
        expect_refusal("C1 图像字段被删掉 -> 拒绝",
                       lambda: assert_references_in_body(broken, refs1), "G-IMG")
    else:
        record("C1 图像字段被删掉 -> 拒绝", False, "无参考图夹具")

    # 两张**像素不同**的参考图。用同一张图测顺序等于没测（本文件第一版就在这里自欺过一次：
    # C/raw.png 与 pack/01-front-full.png 是同一份字节，交换后哈希仍然相等）。
    refs2 = [load_reference(p) for p in (FIXTURE / "pack" / "01-front-full.png",
                                         FIXTURE / "pack" / "02-upper-closeup.png")
             if Path(p).is_file()]
    if len(refs2) == 2:
        two = build_request(mode=MODE_I2I, prompt="p", references=refs2, negative_prompt="n",
                            size=DEFAULT_SIZE, seed=1)
        record("C2 两张参考图的像素确实不同（否则顺序判据无效）",
               refs2[0].sha256 != refs2[1].sha256,
               "%s vs %s" % (refs2[0].sha256[:12], refs2[1].sha256[:12]))
        record("C2b 两张参考图按序进入请求体（契约 1-3 张的多图分支）",
               len(image_fields_in_body(two)) == 2
               and assert_references_in_body(two, refs2) ==
               [p for p, _ in image_fields_in_body(two)],
               str([p for p, _ in image_fields_in_body(two)]))
        expect_refusal("C3 两张参考图顺序颠倒 -> 拒绝",
                       lambda: assert_references_in_body(two, [refs2[1], refs2[0]]), "G-IMG")
    else:
        record("C2 两张参考图按序进入请求体", False, "需要两张参考图夹具")

    # D. 数量 / 模式 / 端点守卫
    if refs1:
        expect_refusal("D1 0 张参考图 -> 拒绝（等于纯文生图）",
                       lambda: build_request(mode=MODE_I2I, prompt="p", references=[],
                                             negative_prompt="n", size=DEFAULT_SIZE, seed=1),
                       "参考图数量")
        expect_refusal("D2 4 张参考图 -> 拒绝（超出契约 1-3）",
                       lambda: build_request(mode=MODE_I2I, prompt="p",
                                             references=refs1 * 4, negative_prompt="n",
                                             size=DEFAULT_SIZE, seed=1), "参考图数量")
        expect_refusal("D3 mode=text_to_image -> 拒绝（Goal 禁止文生图冒充）",
                       lambda: build_request(mode=MODE_T2I, prompt="p", references=refs1,
                                             negative_prompt="n", size=DEFAULT_SIZE, seed=1),
                       "只接受 mode=image_to_image")
        expect_refusal("D4 端点换成 legacy wanx 文生图 -> 拒绝",
                       lambda: assert_endpoint_ok(LEGACY_T2I_CREATE_URL), "G-EP")
        expect_refusal("D5 size 超出契约区间 -> 拒绝",
                       lambda: build_request(mode=MODE_I2I, prompt="p", references=refs1,
                                             negative_prompt="n", size="4096*4096", seed=1),
                       "size")
        expect_refusal("D6 seed 越界 -> 拒绝",
                       lambda: build_request(mode=MODE_I2I, prompt="p", references=refs1,
                                             negative_prompt="n", size=DEFAULT_SIZE,
                                             seed=SEED_MAX + 1), "seed")
        expect_refusal("D7 n=7 -> 拒绝",
                       lambda: build_request(mode=MODE_I2I, prompt="p", references=refs1,
                                             negative_prompt="n", size=DEFAULT_SIZE, seed=1, n=7),
                       "n")
        expect_refusal("D8 negative_prompt 超 500 字符 -> 拒绝（不静默截断）",
                       lambda: build_request(mode=MODE_I2I, prompt="p", references=refs1,
                                             negative_prompt="x" * 501, size=DEFAULT_SIZE,
                                             seed=1), "negative_prompt")
        expect_refusal("D9 prompt_extend=True 未显式允许 -> 拒绝",
                       lambda: build_request(mode=MODE_I2I, prompt="p", references=refs1,
                                             negative_prompt="n", size=DEFAULT_SIZE, seed=1,
                                             prompt_extend=True), "prompt_extend")
        record("D10 显式允许 prompt_extend 时才放行（受控复验入口）",
               build_request(mode=MODE_I2I, prompt="p", references=refs1, negative_prompt="n",
                             size=DEFAULT_SIZE, seed=1, prompt_extend=True,
                             allow_prompt_rewrite=True)["parameters"]["prompt_extend"] is True)

    # E. 幂等 / Unknown / 原 task 可查（D1.3）
    if refs1:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store, ledger = AttemptStore(base / "attempts"), Ledger(base / "ledger.jsonl")
            ft = FakeTransport(task_status="SUCCEEDED")
            prov = Provider(store=store, ledger=ledger, transport=ft, api_key="fake-key")
            kw = dict(prompt="studio scene of the same product", references=refs1, seed=7,
                      negative_prompt="text")
            r1 = prov.submit(**kw)
            r2 = prov.submit(**kw)
            record("E1 一次提交成功并落盘原始 PNG",
                   r1["status"] == "SUCCEEDED" and Path(r1["image_path"]).is_file()
                   and r1["input_image_count"] == 1, r1["status"])
            record("E2 同一 action 重复运行 -> 不重复 submit",
                   r2["status"] == "SKIPPED_HAS_RESULT" and ft.post_calls == 1,
                   "post 次数 %d" % ft.post_calls)
            record("E3 账本只有一行、可按 action 检索",
                   len(ledger.records()) == 1 and ledger.by_action(r1["action_id"]) is not None)

            store2 = AttemptStore(base / "attempts2")
            ledger2 = Ledger(base / "ledger2.jsonl")
            ft2 = FakeTransport(task_status="RUNNING")
            prov2 = Provider(store=store2, ledger=ledger2, transport=ft2, api_key="fake-key")
            r3 = prov2.submit(**kw, poll_timeout_s=0)
            record("E4 轮询超时 -> UNKNOWN，不是失败", r3["status"] == "UNKNOWN", r3["status"])
            r4 = prov2.submit(**kw)
            record("E5 UNKNOWN 之后不自动重发（先核对）",
                   r4["status"] == "UNKNOWN_PENDING_RECONCILE" and ft2.post_calls == 1,
                   "%s / post %d" % (r4["status"], ft2.post_calls))
            ft2.task_status = "SUCCEEDED"
            rec = prov2.reconcile(r3["task_id"])
            record("E6 用原 task_id 核对 -> 拿到真实终态",
                   rec["status"] == "SUCCEEDED", rec["status"])
            record("E7 未收尾动作可被列出（未知不会被静默丢掉）",
                   any(x["action_id"] == r3["action_id"] for x in prov2.unresolved()))

            store3 = AttemptStore(base / "attempts3")
            ledger3 = Ledger(base / "ledger3.jsonl")
            prov3 = Provider(store=store3, ledger=ledger3, transport=FakeTransport(),
                             api_key="")
            expect_refusal("E8 无 key -> 拒绝且不产 mock 图",
                           lambda: prov3.submit(**kw), "DASHSCOPE_API_KEY")
            record("E9 无 key 的拒绝没有留下 intent、没有账本行、没有占位图",
                   store3.attempts() == [] and ledger3.records() == [])
    else:
        record("E1-E9 幂等与 Unknown", False, "无参考图夹具")

    width = max(len(n) for n, _, _ in rows) + 2
    print("=" * 72)
    print("图生图适配器自检（离线，0 次付费调用）")
    print("=" * 72)
    bad = 0
    for name, ok, detail in rows:
        print(("OK   " if ok else "FAIL ") + name.ljust(width) + (("-> " + detail) if detail else ""))
        bad += 0 if ok else 1
    print()
    print("结果：%d 向通过 · %d 向未通过（共 %d 向）" % (len(rows) - bad, bad, len(rows)))
    return 0 if bad == 0 else 1


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                              # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="百炼 qwen-image-3.0 图生图适配器（正式生成入口）")
    ap.add_argument("--self-test", action="store_true", help="离线自检，0 次付费调用")
    ap.add_argument("--reconcile", metavar="TASK_ID", help="用原 task_id 查询状态（不产生新提交）")
    ap.add_argument("--reconcile-unknowns", action="store_true", help="列出未收尾动作并逐个核对")
    ap.add_argument("--store", help="attempt 目录")
    ap.add_argument("--ledger", help="账本 JSONL")
    ap.add_argument("--show-contract", action="store_true", help="打印能力契约摘要")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.show_contract:
        print(json.dumps({"model": CONTRACT["model"]["name"],
                          "create_async": CREATE_URL, "query_task": TASK_URL,
                          "capabilities": len(CONTRACT["capabilities"]),
                          "unknown_items": [c["id"] for c in CONTRACT["capabilities"]
                                            if c.get("status") == "unknown"]},
                         ensure_ascii=False, indent=2))
        return 0
    if args.reconcile or args.reconcile_unknowns:
        if not (args.store and args.ledger):
            print("--reconcile / --reconcile-unknowns 需要 --store 与 --ledger")
            return 2
        prov = Provider(store=AttemptStore(args.store), ledger=Ledger(args.ledger))
        if args.reconcile:
            print(json.dumps(prov.reconcile(args.reconcile), ensure_ascii=False, indent=2)[:2000])
            return 0
        for row in prov.reconcile_unknowns():
            print(json.dumps(row, ensure_ascii=False))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())