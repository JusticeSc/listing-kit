#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""以选定的候选 C 为参考图，冻结 Aster 01 的其余参考视图（Phase 0 / D0.2）。

这是**图生图**：请求体里按序放 `{"image": data-uri}` 与 `{"text": prompt}`，
并把服务端 `usage.input_image_count` 作为"参考图确实进了请求"的机器证据。

固定条件与 D0.1 相同：prompt_extend=false · watermark=false · n=1 · 每视图固定 seed。
幂等：同一 (模型, 参考图哈希, 提示词哈希, seed, size) 已有产物就不再提交。
脱敏：`choices[].message.content[].image` 是临时签名 URL，落盘前一律替换为占位符。
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image

MODEL = "qwen-image-3.0"
CREATE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation"
TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"

INVARIANTS = (
    "Keep the exact same product as in the reference image: same design, same colours, "
    "same proportions, same number of parts. Upper body matte deep teal green; lower grip "
    "sleeve dark charcoal with exactly three raised horizontal ribs; low profile dark charcoal "
    "lid with two concentric stepped rings; one narrow terracotta orange ring at the seam "
    "between lid and body; flat base with a narrow dark non-slip ring. No handle, no side "
    "grip, no strap, no straw, no drinking spout, no second cup, no flip top, no dome lid, "
    "no pattern. Every surface stays completely blank: no text, no numbers, no letters, no "
    "logo, no brand mark, no label, no sticker, no watermark, no decorative symbol."
)

NEGATIVE_PROMPT = (
    "different product, different colour, different proportions, extra object, second cup, "
    "handle, side handle, strap, straw, drinking spout, flip top, dome lid, open lid, "
    "text, letters, words, numbers, logo, brand mark, watermark, label, sticker, typography, "
    "pattern, gradient, glossy metallic body, cropped product, floating object, cluttered "
    "background, props, low resolution, blurry"
)

VIEWS = [
    {
        "id": "ref-02-three-quarter",
        "role": "整体全身（第二张，付费探针，不进入参考包）",
        "note": "实测为近似正面。旋转对称商品在剪影上无法区分 0° 与 30°，所以本视图不声明角度；"
                "它的用途是记录图生图的姿态保留程度。参考包只用 ref-01 / ref-02 / ref-03。",
        "seed": 2026092411,
        "prompt": ("Photograph of the exact same product as in the reference image, from a "
                   "30 degree three-quarter view (rotated about 30 degrees to its right so both "
                   "the front and the right side are partly visible), lid screwed shut, whole "
                   "body fully visible with small even margins, standing upright on the same "
                   "seamless plain light neutral gray backdrop, same soft even studio light "
                   "from the upper left, same soft natural contact shadow. " + INVARIANTS +
                   " Photorealistic e-commerce product photography, square 1:1 composition."),
    },
    {
        "id": "ref-02-upper-detail",
        "role": "上部与杯盖近景（F4/F5 主证据）",
        "seed": 2026092412,
        "prompt": ("Close-up photograph of the upper part of the exact same product as in the "
                   "reference image: the lid and the top third of the body fill the frame. The "
                   "lid top must clearly show two concentric stepped rings, a smaller ring "
                   "sitting on a wider ring, with a crisp visible step edge; the single narrow "
                   "terracotta orange ring must run evenly around the seam between lid and "
                   "body. Same soft even studio light from the upper left, same seamless plain "
                   "light neutral gray backdrop. " + INVARIANTS +
                   " Photorealistic e-commerce product photography, square 1:1 composition."),
    },
    {
        "id": "ref-02-upper-closeup",
        "role": "上部与杯盖特写（F4/F5 主证据）",
        "seed": 2026092417,
        "prompt": ("Close-up photograph of the upper part of the exact same product as in the "
                   "reference image: the lid and the top of the body fill the frame, the lid "
                   "occupying roughly the top third of the picture, and the teal body continues "
                   "beyond the bottom edge of the frame. The lid top must clearly show two "
                   "concentric stepped rings, a smaller ring sitting on a wider ring, with a "
                   "crisp visible step edge, and the single narrow terracotta orange ring must "
                   "run evenly around the seam between the lid and the body. Same soft even "
                   "studio light from the upper left, same seamless plain light neutral gray "
                   "backdrop. " + INVARIANTS +
                   " Photorealistic e-commerce product photography, square 1:1 composition."),
    },
    {
        "id": "ref-03-lower-detail",
        "role": "防滑套与底部近景（F3/F6 主证据）",
        "seed": 2026092416,
        "prompt": ("Close-up photograph of the lower part of the exact same product as in the "
                   "reference image: the dark charcoal grip sleeve and the base fill the frame. "
                   "The sleeve must show exactly three raised horizontal ribs running evenly "
                   "around it with clearly separated spacing, and the flat bottom must show its "
                   "narrow dark gray non-slip ring along the bottom edge. Same soft even studio "
                   "light from the upper left, same seamless plain light neutral gray backdrop. "
                   + INVARIANTS +
                   " Photorealistic e-commerce product photography, square 1:1 composition."),
    },
]


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def sanitize(result: dict) -> dict:
    out = json.loads(json.dumps(result))
    for choice in ((out.get("output") or {}).get("choices") or []):
        for part in ((choice.get("message") or {}).get("content") or []):
            url = part.get("image")
            if isinstance(url, str) and url.startswith("http"):
                p = urlparse(url)
                part["image"] = "%s://%s/<redacted-path>?<redacted-query>" % (p.scheme, p.netloc)
    return out


def run_view(view: dict, project: Path, key: str, ref: Path, size: str,
             send: bool, timeout_s: int) -> str:
    out_dir = project / "evals/product-demo/fixture-design" / view["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    ref_bytes = ref.read_bytes()
    ref_sha = sha_bytes(ref_bytes)
    prompt = view["prompt"]
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    aid = hashlib.sha256(("%s|%s|%s|%d|%s" % (MODEL, ref_sha, prompt_sha,
                                             view["seed"], size)).encode("utf-8")).hexdigest()[:16]
    meta_path = out_dir / "meta.json"
    raw_path = out_dir / "raw.png"
    if meta_path.is_file() and raw_path.is_file():
        old = json.loads(meta_path.read_text(encoding="utf-8"))
        if old.get("action_id") == aid:
            return view["id"] + " SKIP（同一 action 已有付费产出）"

    body = {
        "model": MODEL,
        "input": {"messages": [{"role": "user", "content": [
            {"image": data_uri(ref)}, {"text": prompt}]}]},
        "parameters": {
            "negative_prompt": NEGATIVE_PROMPT[:500],
            "prompt_extend": False,
            "watermark": False,
            "size": size,
            "n": 1,
            "seed": view["seed"],
        },
    }
    if not send:
        preview = json.loads(json.dumps(body))
        preview["input"]["messages"][0]["content"][0]["image"] = "<data-uri %d bytes>" % len(ref_bytes)
        (out_dir / "request.dryrun.json").write_text(
            json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        return view["id"] + " DRY-RUN（请求体已写出，未提交）"

    # 幂等键必须在提交之前落盘。2026-09-24 实测过一次提交读超时：
    # 请求可能已到达服务、也可能没到达，而本地没有任何凭据能区分这两者。
    # 先写 intent，重启后才知道"有一个身份不明的 action 悬在这里"。
    intent_path = out_dir / "intent.json"
    if intent_path.is_file() and not meta_path.is_file():
        old = json.loads(intent_path.read_text(encoding="utf-8"))
        if old.get("status") != "completed":
            return (view["id"] + " UNKNOWN：存在未完成的 intent（action_id="
                    + str(old.get("action_id")) + "，提交于 " + str(old.get("submitted_at"))
                    + "）。核对之前不重新提交同一身份；用 --reconcile 查账户任务列表。")
    intent = {
        "action_id": aid, "model": MODEL, "mode": "image_to_image", "seed": view["seed"],
        "size": size, "reference_sha256": ref_sha, "prompt_sha256": prompt_sha,
        "request_sha256": hashlib.sha256(
            json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest(),
        "submitted_at": now_iso(), "status": "submitting",
    }
    intent_path.write_text(json.dumps(intent, ensure_ascii=False, indent=2),
                           encoding="utf-8", newline="\n")

    r = requests.post(CREATE_URL, headers={
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }, json=body, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(view["id"] + " 创建任务失败：HTTP %s %s" % (r.status_code, r.text[:400]))
    created = r.json()
    task_id = (created.get("output") or {}).get("task_id")
    if not task_id:
        raise RuntimeError(view["id"] + " 未返回 task_id：" + r.text[:300])

    submitted_at = now_iso()
    t0 = time.time()
    deadline = t0 + timeout_s
    result = {}
    while time.time() < deadline:
        rr = requests.get(TASK_URL.format(task_id=task_id),
                          headers={"Authorization": "Bearer " + key}, timeout=60)
        result = rr.json()
        status = ((result.get("output") or {}).get("task_status") or "").upper()
        if status in ("SUCCEEDED", "SUCCESS"):
            break
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            raise RuntimeError(view["id"] + " 任务失败：" +
                               json.dumps(result, ensure_ascii=False)[:600])
        time.sleep(4)
    else:
        raise TimeoutError(view["id"] + " 轮询超时")
    elapsed = round(time.time() - t0, 1)

    url = None
    for choice in ((result.get("output") or {}).get("choices") or []):
        for part in ((choice.get("message") or {}).get("content") or []):
            if isinstance(part, dict) and part.get("image"):
                url = part["image"]
    if not url:
        for item in ((result.get("output") or {}).get("results") or []):
            if isinstance(item, dict) and item.get("url"):
                url = item["url"]
    if not url:
        raise RuntimeError(view["id"] + " 未返回图片 url")
    blob = requests.get(url, timeout=180)
    blob.raise_for_status()
    raw = blob.content
    with Image.open(io.BytesIO(raw)) as im:
        fmt, px = im.format, im.size

    request_record = json.loads(json.dumps(body))
    request_record["input"]["messages"][0]["content"][0]["image"] = (
        "<data-uri of reference, sha256=%s, bytes=%d>" % (ref_sha, len(ref_bytes)))
    (out_dir / "request.json").write_text(
        json.dumps(request_record, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    (out_dir / "response-create.json").write_text(
        json.dumps(created, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    (out_dir / "response-task.json").write_text(
        json.dumps(sanitize(result), ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    raw_path.write_bytes(raw)
    usage = result.get("usage") or {}
    meta = {
        "view_id": view["id"], "role": view["role"], "action_id": aid, "model": MODEL,
        "mode": "image_to_image", "endpoint": CREATE_URL,
        "reference_file": str(ref), "reference_sha256": ref_sha,
        "seed": view["seed"], "size_used": size, "prompt_extend": False,
        "watermark": False, "n": 1, "prompt": prompt, "prompt_sha256": prompt_sha,
        "task_id": task_id, "submitted_at": submitted_at, "finished_at": now_iso(),
        "poll_elapsed_s": elapsed, "usage": usage,
        "input_image_count": usage.get("input_image_count"),
        "rewrite_status": (result.get("output") or {}).get("rewrite_status"),
        "image_sha256": sha_bytes(raw), "image_bytes": len(raw),
        "image_format": fmt, "image_size": list(px),
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                         encoding="utf-8", newline="\n")
    intent["status"] = "completed"
    intent["task_id"] = task_id
    intent["image_sha256"] = sha_bytes(raw)
    intent_path.write_text(json.dumps(intent, ensure_ascii=False, indent=2),
                           encoding="utf-8", newline="\n")
    ledger = project / "evals/product-demo/fixture-design/ledger.jsonl"
    with ledger.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({
            "action_id": aid, "view_id": view["id"], "model": MODEL, "mode": "image_to_image",
            "seed": view["seed"], "size": size, "task_id": task_id,
            "reference_sha256": ref_sha, "image_sha256": sha_bytes(raw),
            "input_image_count": usage.get("input_image_count"),
            "chargeable": True, "at": meta["finished_at"]}, ensure_ascii=False) + "\n")
    return "%s OK  %dx%d %s  %d KB  input_image_count=%s  task=%s…  %ss" % (
        view["id"], px[0], px[1], fmt, len(raw) // 1024, usage.get("input_image_count"),
        task_id[:12], elapsed)


def reconcile(project: Path, key: str, page_size: int = 100) -> int:
    """账户级核对：把服务端任务列表与本地账本对齐。

    超时后我们没有 task_id，也没有别的凭据能判断"请求到没到服务"。
    账户任务列表是唯一能从外部回答这个问题的来源 —— 未登记的任务就是可疑的付费动作。
    注意：列表若不含在途任务，本核对在提交后的几十秒内不可靠，必须等足够久再查。
    """
    ledger = project / "evals/product-demo/fixture-design/ledger.jsonl"
    known = set()
    if ledger.is_file():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if line.strip():
                known.add(json.loads(line).get("task_id"))
    r = requests.get("https://dashscope.aliyuncs.com/api/v1/tasks",
                     headers={"Authorization": "Bearer " + key},
                     params={"page_no": 1, "page_size": page_size}, timeout=60)
    if r.status_code != 200:
        print("任务列表不可用：HTTP %s %s" % (r.status_code, r.text[:200]))
        return 3
    data = r.json()
    rows = data.get("data") or []
    tz = timezone(timedelta(hours=8))
    print("账户任务总数 %s · 列表返回 %d · 账本已知 %d" % (data.get("total"), len(rows), len(known)))
    orphans = [t for t in rows if t.get("task_id") not in known]
    for t in orphans:
        created = datetime.fromtimestamp(t["gmt_create"] / 1000.0, tz).strftime("%Y-%m-%d %H:%M:%S")
        print("  未登记：%s  %s  %s  %s" % (created, t.get("status"),
                                          t.get("model_name"), t.get("task_id")))
    if not orphans:
        print("核对结果：账户里没有未登记任务，账本与外部状态一致。")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--ref", default="evals/product-demo/fixture-design/C/raw.png")
    ap.add_argument("--size", default="1344*1344")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--send", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--reconcile", action="store_true",
                    help="只做账户任务列表核对，不提交任何请求")
    args = ap.parse_args()
    project = Path(args.project)
    ref = project / args.ref
    if not ref.is_file():
        print("参考图不存在：" + str(ref), file=sys.stderr)
        return 2
    key = os.getenv("DASHSCOPE_API_KEY") or ""
    if args.reconcile:
        if not key:
            print("DASHSCOPE_API_KEY 缺失：无法核对。", file=sys.stderr)
            return 2
        return reconcile(project, key)
    if args.send and not key:
        print("DASHSCOPE_API_KEY 缺失：不能真跑。", file=sys.stderr)
        return 2
    print("图生图 · 参考图 " + args.ref + " · 模式 " +
          ("真跑（会付费）" if args.send else "干跑（不付费）"))
    for view in VIEWS:
        if args.only and view["id"] != args.only:
            continue
        print("  " + run_view(view, project, key, ref, args.size, args.send, args.timeout))
    return 0


if __name__ == "__main__":
    sys.exit(main())
