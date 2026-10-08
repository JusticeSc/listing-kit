"""DashScope 文生图封装 —— 支持两个模型族。

| 模型族 | 例 | 创建任务 endpoint | 请求体形状 | size 写法 |
|---|---|---|---|---|
| qwen-image | qwen-image-3.0 / -3.0-pro | /services/aigc/image-generation/generation | input.messages[{role,content:[{text}]}] | "1600*1600" |
| wanx      | wanx2.1-t2i-turbo / -plus | /services/aigc/text2image/image-synthesis | input.prompt | "1024*1024" |

两者**共用**同一个任务轮询接口：GET /api/v1/tasks/{task_id}。

差异要点（换模型时真正要改的东西）：
  1. qwen-image-3.0 输出上限 2048×2048（wanx 只有 1024）→ 可原生出 1600px，省掉 LANCZOS 放大。
  2. qwen-image-3.0 的 negative_prompt 放在 parameters 里，上限 500 字符（超长会被截断）。
  3. qwen-image-3.0 的 prompt_extend 会**改写提示词**，enable_thinking 默认开启 →
     实际执行的提示词不等于 plan 里的提示词，可复现性下降，必须写进日志。
  4. qwen-image-3.0 的中文文字渲染能力很强（官方口径 10px 级、12 语种）——
     这会反过来削弱"禁字"条款的把握度，只出干净背景变得更难而不是更容易。

无 DASHSCOPE_API_KEY 时不报错退出，而是走 mock：生成一张带标注的占位背景图，
让下游（叠字层 / 校验器 / 日志）仍能端到端跑通并验证。
"""
from __future__ import annotations

import inspect
import io
import os
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw

API_BASE = "https://dashscope.aliyuncs.com/api/v1"
TASK_URL = f"{API_BASE}/tasks/{{task_id}}"

# 两个模型族各自的"创建任务"端点
CREATE_URLS = {
    "qwen-image": f"{API_BASE}/services/aigc/image-generation/generation",
    "wanx": f"{API_BASE}/services/aigc/text2image/image-synthesis",
}

# 默认模型：qwen-image-3.0（标准版，兼顾质量与速度；-pro 更贵更慢）
DEFAULT_MODEL = os.getenv("IMAGE_MODEL", "qwen-image-3.0")
FALLBACK_MODEL = "qwen-image-3.0"
NEG_PROMPT_MAX = 500          # qwen-image 系 negative_prompt 上限
QWEN_MAX_SIDE = 2048          # 单边上限
QWEN_STEP = 32                # 尺寸对齐步长


def family_of(model: str) -> str:
    return "qwen-image" if model.lower().startswith("qwen-image") else "wanx"


def _snap(n: int) -> int:
    """对齐到 step 的倍数并夹到 [512, 2048]。"""
    n = int(round(int(n) / QWEN_STEP) * QWEN_STEP)
    return max(512, min(QWEN_MAX_SIDE, n))


def _size_candidates(model: str, size_px: int) -> list[str | None]:
    """按"最优 → 兜底"顺序给出要尝试的 size 取值（None = 让模型自动推荐）。

    为什么要列一串而不是写死一个：size 的合法区间随模型变化，
    显式传错值会直接 400。逐级降级可以在换模型时不用改这里的逻辑。
    """
    if family_of(model) == "wanx":
        return ["1024*1024"]
    cands: list[str | None] = []
    n = _snap(size_px)
    if n > 1024:
        cands.append(f"{n}*{n}")
    cands.append("1024*1024")
    cands.append(None)
    return cands


def _build_body(model: str, prompt: str, negative_prompt: str,
                size: str | None) -> tuple[str, dict]:
    """返回 (创建任务 URL, 请求体)。两个模型族的请求体形状完全不同。"""
    if family_of(model) == "qwen-image":
        params: dict = {
            "negative_prompt": negative_prompt[:NEG_PROMPT_MAX],
            "prompt_extend": True,     # 模型会改写提示词以提升画质（可复现性代价见模块注释）
            "watermark": False,
        }
        if size:
            params["size"] = size
        body = {
            "model": model,
            "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
            "parameters": params,
        }
    else:
        body = {
            "model": model,
            "input": {"prompt": prompt, "negative_prompt": negative_prompt},
            "parameters": {"size": size or "1024*1024", "n": 1},
        }
    return CREATE_URLS[family_of(model)], body


# ---------------------------------------------------------------- 不变量 B 的证据
#
# 「生成层看不见主体」这条不变量，此前只有一个硬编码的声明：
#     renderers/gen_bg_paste.py:  "subject_excluded_from_model": True
# 那句声明没有任何东西在验它。将来给 generate_image 加一个参考图参数
# （那正是"学参考库编辑类技能"的第一步 —— 它们的 15 个编辑类技能全都
#  把源图作为参考图送进模型），这行会继续写 True：**变成假话，不报错、
# 不进任何报表**。这正是本项目最警惕的那一类字段（"声称做了、实际没做、
# 还不报错"），与已删除的 no_watermark 同一个形态。
#
# 改法：让声明从**请求体里到底有没有像素字段**推出来 —— 算出来的，不是写下来的。
IMAGE_PARAM_HINTS = ("image", "images", "img", "ref", "reference", "mask",
                     "photo", "picture")
IMAGE_URL_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def image_inputs_in_signature(fn=None) -> list[str]:
    """签名里**接受图像入参**的参数名（空 = 这个函数不可能把图像送进模型）。

    它挡的是"将来"：给 generate_image 加 `ref_image=None` 那天，
    这个列表会从 [] 变成 ["ref_image"]，而 inclusion_report 会把这件事
    报出去 —— 于是加参数的人**必须**处理它，不能悄悄多送一张图。
    """
    fn = fn or generate_image
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return []
    return [n for n in params if any(h in n.lower() for h in IMAGE_PARAM_HINTS)]


def _body_image_fields(body) -> list[str]:
    """扫描请求体，列出所有**承载图像**的字段路径（空 = 这次请求没有像素）。

    判据（任一命中即为图像字段）：
        · 路径名本身是图像名（image / images / image_url / ref_image / mask…）
        · 值是 data:image/... 或指向 .png/.jpg/.webp 的 URL
    写成"扫描"而不是"按已知字段名判断"，是为了**换模型族时不用改这里** ——
    qwen-image 与 wanx 的请求体形状完全不同（见模块头），
    而它们都不该有图像字段。
    """
    found: list[str] = []

    def walk(node, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif node not in (None, "", [], {}):
            low = path.lower()
            if any(h in low for h in IMAGE_PARAM_HINTS):
                found.append(path)
            elif isinstance(node, str) and (
                    node.startswith("data:image")
                    or (node.startswith("http")
                        and low.endswith(IMAGE_URL_SUFFIXES))):
                found.append(path)

    walk(body, "")
    return found


def inclusion_report(*, prompt: str, negative_prompt: str, model: str,
                     size: str | None, sent: bool) -> dict:
    """这次生成请求**是否携带图像像素** —— 不变量 B 的唯一证据来源。

    sent=False（无 key 的占位图）时 `request_body_built` 为 False：
    这一轮**根本没有请求**，所以不变量 B 无从谈起，消费方应记 `null`
    而不是 `true` —— 对一次没发生的请求宣称"我没把主体送出去"是句废话。
    """
    body = None
    if sent:
        _, body = _build_body(model, prompt, negative_prompt, size)
    return {
        "request_body_built": body is not None,
        "request_image_fields": (_body_image_fields(body)
                                 if body is not None else []),
        "image_inputs_in_signature": image_inputs_in_signature(),
    }


def _mock_background(out_path: Path, size_px: int, prompt: str) -> dict:
    """无 key 时的占位背景：浅灰底 + 左侧留白，用于验证下游链路。"""
    img = Image.new("RGB", (size_px, size_px), (238, 238, 238))
    d = ImageDraw.Draw(img)
    d.rectangle([int(size_px * 0.06), int(size_px * 0.06),
                 int(size_px * 0.94), int(size_px * 0.94)], outline=(200, 200, 200), width=2)
    d.text((int(size_px * 0.08), int(size_px * 0.10)),
           "MOCK BACKGROUND / no DASHSCOPE_API_KEY", fill=(150, 150, 150))
    img.save(out_path, "JPEG", quality=92)
    return {"mode": "mock", "path": str(out_path), "size": [size_px, size_px],
            "prompt_preview": prompt[:80]}


def _retry(fn, attempts: int = 3, delay: float = 3.0, label: str = ""):
    """网络类临时错误重试。

    实测踩过：轮询期间遇到 ProxyError（代理连接被中止），一次抖动就整张失败。
    生成调用是花钱的，一次网络抖动不该让这张图白跑，所以这里必须退避重试。
    """
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:
            last = exc
            if i < attempts - 1:
                time.sleep(delay * (i + 1))
    raise RuntimeError(f"{label} 连续 {attempts} 次失败: {last}") from last


def _poll(task_id: str, api_key: str, timeout_s: int = 300) -> dict:
    url = TASK_URL.format(task_id=task_id)
    headers = {"Authorization": f"Bearer {api_key}"}
    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        r = _retry(lambda: requests.get(url, headers=headers, timeout=30),
                   label="轮询 DashScope 任务")
        r.raise_for_status()
        last = r.json()
        status = ((last.get("output") or {}).get("task_status") or "").upper()
        if status in ("SUCCEEDED", "SUCCESS"):
            return last
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            raise RuntimeError(f"DashScope 任务失败: {last}")
        time.sleep(3)
    raise TimeoutError(f"DashScope 轮询超时({timeout_s}s): {last}")


def _extract_url(result: dict) -> str | None:
    """从任务结果里取图片 URL。

    两种返回形状都兼容，换模型时不必改解析：
      wanx / 异步 image-generation : output.results[].url
      同步 multimodal-generation   : output.choices[].message.content[].image
    """
    out = result.get("output") or {}
    for r in (out.get("results") or []):
        if isinstance(r, dict) and r.get("url"):
            return r["url"]
    for ch in (out.get("choices") or []):
        for c in ((ch.get("message") or {}).get("content") or []):
            if isinstance(c, dict) and c.get("image"):
                return c["image"]
    return None


def _create_task(model: str, prompt: str, negative_prompt: str, key: str,
                 size_px: int, timeout_s: int) -> tuple[str, str | None, list[dict]]:
    """按候选 size 逐个尝试创建任务；成功返回 (task_id, 使用的 size, 失败记录)。"""
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    tried: list[dict] = []
    last_err = ""
    for size in _size_candidates(model, size_px):
        url, body = _build_body(model, prompt, negative_prompt, size)
        r = _retry(lambda: requests.post(url, headers=headers, json=body, timeout=60),
                   label="提交 DashScope 任务")
        if r.status_code == 200:
            created = r.json()
            task_id = (created.get("output") or {}).get("task_id")
            if task_id:
                return task_id, size, tried
            last_err = f"未返回 task_id: {created}"
        else:
            # 400 通常是 size / 参数不被该模型接受 → 降级下一步，不重试
            last_err = f"HTTP {r.status_code}: {r.text[:300]}"
        tried.append({"size": size, "status": r.status_code, "error": last_err})
    raise RuntimeError(f"DashScope 创建任务失败（已尝试 {len(tried)} 种 size）: {last_err}")


def generate_image(
    prompt: str,
    negative_prompt: str,
    out_path: str | Path,
    model: str | None = None,
    size_px: int = 1024,
    api_key: str | None = None,
    timeout_s: int = 300,
) -> dict:
    """生成一张无字背景图。返回报告（含 model / size / 实际尺寸 / 是否 mock）。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    model = model or DEFAULT_MODEL

    key = api_key or os.getenv("DASHSCOPE_API_KEY") or ""
    if not key:
        rep = _mock_background(out_path, _snap(size_px), prompt)
        rep["model"] = model
        rep["warning"] = "未配置 DASHSCOPE_API_KEY，使用占位图（链路可验证，画面不可用）"
        # 没发请求 → 不变量 B 在这一轮**无从谈起**（不是"成立"）。
        #   如实写 request_body_built=False，消费方据此把
        #   subject_excluded_from_model 记成 null 而不是 true ——
        #   对一次没发生的请求宣称"我没把主体送出去"是句废话。
        rep.update(inclusion_report(prompt=prompt, negative_prompt=negative_prompt,
                                    model=model, size=None, sent=False))
        return rep

    task_id, used_size, tried = _create_task(model, prompt, negative_prompt, key,
                                             size_px, timeout_s)
    result = _poll(task_id, key, timeout_s)
    url = _extract_url(result)
    if not url:
        raise RuntimeError(f"DashScope 未返回图片 url: {result}")

    img_resp = _retry(lambda: requests.get(url, timeout=120), label="下载生成结果")
    img_resp.raise_for_status()
    img = Image.open(io.BytesIO(img_resp.content)).convert("RGB")
    img.save(out_path, "JPEG", quality=92, optimize=True)

    rep = {
        "mode": "dashscope",
        "model": model,
        "family": family_of(model),
        "task_id": task_id,
        "requested_size": used_size or "auto",
        "path": str(out_path),
        "size": list(img.size),
        "usage": result.get("usage"),
        "prompt_preview": prompt[:80],
    }
    if tried:
        rep["size_fallback_tried"] = tried
    # ★ 不变量 B 的证据：这次真发出去的请求体里有没有像素字段。
    #   用 used_size 重建一次请求体（同一个 _build_body，所以形状必然一致）——
    #   "扫一遍真实请求体"比"我声明一下我没送图"强一个量级。
    rep.update(inclusion_report(prompt=prompt, negative_prompt=negative_prompt,
                                model=model, size=used_size, sent=True))
    return rep
