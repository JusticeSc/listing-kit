#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Aster 01 设计候选生成器（Phase 0 / D0.1）。

它只做一件事：把若干已声明的设计候选各生成一张原始 PNG，并把实际发出去的请求
与拿回来的响应原样留档。它不做审美判断，也不把模型输出升级成事实 ——
哪个候选成为权威夹具由 D0.1 的比较记录决定。

固定条件（对齐 docs/drafts/requirements-analysis-2026-09-24.md §17.5 / §17.6）：
  prompt_extend=false  提示词已经写得很详细，优先让实际执行文本可复现
  watermark=false      输出不得带模型水印
  n=1                  每次请求一张，便于逐张追踪请求与结果
  每候选固定 seed        变异可归因；不靠再抽一次碰运气

幂等：同一 (模型, 提示词哈希, seed, size) 已经产出过 raw.png 就不再提交 ——
重跑本脚本不会重复付费。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from PIL import Image

MODEL = "qwen-image-3.0"
CREATE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/image-generation/generation"
TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
NEG_PROMPT_MAX = 500
OUT_ROOT_REL = "evals/product-demo/fixture-design"

NEGATIVE_PROMPT = (
    "text, letters, words, numbers, logo, brand mark, watermark, label, sticker, "
    "signature, typography, caption, poster, packaging, handle, side handle, strap, "
    "straw, drinking spout, flip top, dome lid, second cup, mug handle, tapered waist, "
    "cone shape, glossy metallic body, gradient, floral pattern, printed pattern, "
    "multiple tumblers, reflection of another object, floating object, cropped product, "
    "distorted proportions, low resolution, blurry, cluttered background"
)

PROMPT_HEAD = (
    "Studio product photograph for an e-commerce reference sheet: exactly one single tall "
    "straight-walled insulated travel tumbler, standing perfectly upright with its lid "
    "screwed shut, full body visible, centered with small even margins, on a seamless plain "
    "light neutral gray backdrop, soft even studio light from the upper left, soft natural "
    "contact shadow under the base, no props, no extra objects, sharp focus, photographic "
    "realism."
)

PROMPT_RULES = [
    "Design specification that must be followed exactly:",
    "- Body: one tall cylinder with near-vertical straight side walls; no taper, no waist, "
    "no curve, no handle, no side grip, no strap, no straw, no spout, no second cup. "
    "Overall body height-to-width ratio about {ratio}.",
    "- Colour blocking: the upper roughly 72 percent of the body height is matte deep teal "
    "green (about hex #0F6B66); matte finish, not glossy, no gradient, no printed pattern.",
    "- The lower roughly 28 percent of the body height is a dark charcoal gray (about hex "
    "#252A2A) silicone grip sleeve. {ribs}",
    "- Lid: low profile dark charcoal gray lid, clearly shorter than one fifth of the total "
    "height. {lid}",
    "- {ring}",
    "- Base: flat bottom with a narrow dark gray non-slip ring at the very bottom edge; the "
    "tumbler rests flat and grounded on the surface.",
    "- The entire outer surface is completely blank: no text, no numbers, no letters, no "
    "words, no logo, no brand mark, no label, no sticker, no watermark, no decorative "
    "symbol, no capacity marking.",
]

PROMPT_TAIL = (
    "Framing: straight-on front view, the whole tumbler including the lid inside the frame, "
    "square 1:1 composition, clean commercial catalogue look."
)


def base_prompt(*, ratio: str, ribs: str, lid: str, ring: str) -> str:
    body = "\n".join(seg.format(ratio=ratio, ribs=ribs, lid=lid, ring=ring)
                     for seg in PROMPT_RULES)
    return f"{PROMPT_HEAD}\n\n{body}\n\n{PROMPT_TAIL}"


RING_STD = ("A single narrow terracotta orange ring (about hex #D97A45), thin and even, "
            "sits in the seam between the lid and the body.")
RING_BOLD = ("A single narrow terracotta orange ring (about hex #D97A45) sits in the seam "
             "between the lid and the body; keep it clearly visible and evenly thick all the "
             "way around the circle, still thin relative to the body height.")
LID_STD = ("The lid top is a smooth flat surface with exactly two clearly visible concentric "
           "stepped rings stacked one above the other: a smaller ring sitting on a wider ring. "
           "Smooth matte finish. No flip top, no drinking spout, no dome, no second lid.")
LID_BOLD = ("The lid top has exactly two clearly visible concentric stepped rings stacked one "
            "above the other, a smaller ring sitting on a wider one, with a crisp visible step "
            "edge between them so both steps stay readable at a small scale. No flip top, no "
            "drinking spout, no dome, no second lid.")
RIBS_STD = "The sleeve has exactly three thin slightly lighter horizontal ribs wrapping around it."
RIBS_BOLD = ("The sleeve has exactly three horizontal ribs wrapping around it, raised and "
             "clearly separated so the rib count stays countable at a small scale.")

CANDIDATES = [
    {
        "id": "A",
        "name": "spec-baseline",
        "seed": 2026092401,
        "why": "严格按 F1–F8 数值与最中性的影棚表现，作为规格基准候选。",
        "prompt": base_prompt(ratio="3.1 to 1", ribs=RIBS_STD, lid=LID_STD, ring=RING_STD),
    },
    {
        "id": "B",
        "name": "part-legibility",
        "seed": 2026092402,
        "why": "结构与 A 相同，但把杯盖双层阶梯环、橙色装饰环与三条筋条画得更可辨认 —— "
               "验证「部件可读性优先」是否降低模型重绘时丢件的概率。",
        "prompt": base_prompt(ratio="3.1 to 1", ribs=RIBS_BOLD, lid=LID_BOLD, ring=RING_BOLD),
    },
    {
        "id": "C",
        "name": "proportion-robust",
        "seed": 2026092403,
        "why": "高宽比略收到 3.0:1、筋条更突出，验证「比例容差更大」是否让 F1/F3 在重绘中更稳。",
        "prompt": base_prompt(ratio="3.0 to 1, still a distinctly tall slim tumbler",
                              ribs=RIBS_BOLD, lid=LID_BOLD, ring=RING_BOLD),
    },
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def now_iso() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def action_id(prompt_sha: str, seed: int, size: str) -> str:
    return sha256_text(MODEL + "|" + prompt_sha + "|" + str(seed) + "|" + size)[:16]


def size_candidates(size_px: int) -> list:
    n = max(1024, min(2048, int(round(size_px / 32.0) * 32)))
    out = []
    if n > 1024:
        out.append(str(n) + "*" + str(n))
    out.append("1024*1024")
    return out


def build_body(prompt: str, seed: int, size: str) -> dict:
    return {
        "model": MODEL,
        "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
        "parameters": {
            "negative_prompt": NEGATIVE_PROMPT[:NEG_PROMPT_MAX],
            "prompt_extend": False,
            "watermark": False,
            "size": size,
            "n": 1,
            "seed": seed,
        },
    }


def poll(task_id: str, key: str, timeout_s: int) -> dict:
    deadline = time.time() + timeout_s
    last: dict = {}
    while time.time() < deadline:
        r = requests.get(TASK_URL.format(task_id=task_id),
                         headers={"Authorization": "Bearer " + key}, timeout=60)
        last = r.json()
        status = ((last.get("output") or {}).get("task_status") or "").upper()
        if status in ("SUCCEEDED", "SUCCESS"):
            return last
        if status in ("FAILED", "CANCELED", "UNKNOWN"):
            raise RuntimeError("DashScope 任务失败: "
                               + json.dumps(last, ensure_ascii=False)[:800])
        time.sleep(4)
    raise TimeoutError("轮询超时(%ss)" % timeout_s)


def extract_url(result: dict):
    out = result.get("output") or {}
    for item in (out.get("results") or []):
        if isinstance(item, dict) and item.get("url"):
            return item["url"]
    for choice in (out.get("choices") or []):
        for part in ((choice.get("message") or {}).get("content") or []):
            if isinstance(part, dict) and part.get("image"):
                return part["image"]
    return None


def run_one(cand: dict, project: Path, key: str, size_px: int, send: bool,
            timeout_s: int) -> str:
    out_dir = project / OUT_ROOT_REL / cand["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_sha = sha256_text(cand["prompt"])
    sizes = size_candidates(size_px)
    aid = action_id(prompt_sha, cand["seed"], sizes[0])
    meta_path = out_dir / "meta.json"
    raw_path = out_dir / "raw.png"
    if meta_path.is_file() and raw_path.is_file():
        old = json.loads(meta_path.read_text(encoding="utf-8"))
        if old.get("action_id") == aid and old.get("prompt_sha256") == prompt_sha:
            return cand["id"] + " SKIP（同一 action 已有付费产出，不重复提交）"
    if not send:
        (out_dir / "request.dryrun.json").write_text(
            json.dumps(build_body(cand["prompt"], cand["seed"], sizes[0]),
                       ensure_ascii=False, indent=2),
            encoding="utf-8", newline="\n")
        return cand["id"] + " DRY-RUN（请求体已写出，未提交）"

    created = None
    used_size = ""
    last_err = ""
    tried = []
    final_body: dict = {}
    for size in sizes:
        body = build_body(cand["prompt"], cand["seed"], size)
        r = requests.post(CREATE_URL, headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }, json=body, timeout=60)
        if r.status_code == 200:
            payload = r.json()
            task_id = (payload.get("output") or {}).get("task_id")
            if task_id:
                created, used_size, final_body = payload, size, body
                break
            last_err = "未返回 task_id: " + r.text[:300]
        else:
            last_err = "HTTP %s: %s" % (r.status_code, r.text[:400])
        tried.append({"size": size, "status": r.status_code, "error": last_err})
    if created is None:
        raise RuntimeError(cand["id"] + " 创建任务失败：" + last_err)

    task_id = created["output"]["task_id"]
    submitted_at = now_iso()
    t0 = time.time()
    result = poll(task_id, key, timeout_s)
    elapsed = round(time.time() - t0, 1)
    url = extract_url(result)
    if not url:
        raise RuntimeError(cand["id"] + " 未返回图片 url")
    blob = requests.get(url, timeout=180)
    blob.raise_for_status()
    raw = blob.content
    with Image.open(io.BytesIO(raw)) as im:
        fmt, px = im.format, im.size

    (out_dir / "request.json").write_text(
        json.dumps(final_body, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    (out_dir / "response-create.json").write_text(
        json.dumps(created, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    (out_dir / "response-task.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    raw_path.write_bytes(raw)
    meta = {
        "candidate_id": cand["id"],
        "candidate_name": cand["name"],
        "why": cand["why"],
        "action_id": aid,
        "model": MODEL,
        "endpoint": CREATE_URL,
        "mode": "text_to_image",
        "size_requested": sizes[0],
        "size_used": used_size,
        "seed": cand["seed"],
        "prompt_extend": False,
        "watermark": False,
        "n": 1,
        "prompt": cand["prompt"],
        "prompt_sha256": prompt_sha,
        "negative_prompt_sha256": sha256_text(NEGATIVE_PROMPT[:NEG_PROMPT_MAX]),
        "task_id": task_id,
        "submitted_at": submitted_at,
        "finished_at": now_iso(),
        "poll_elapsed_s": elapsed,
        "usage": result.get("usage"),
        "image_sha256": sha256_bytes(raw),
        "image_bytes": len(raw),
        "image_format": fmt,
        "image_size": list(px),
        "size_fallback_tried": tried,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                         encoding="utf-8", newline="\n")
    ledger = project / OUT_ROOT_REL / "ledger.jsonl"
    line = json.dumps({
        "action_id": aid, "candidate_id": cand["id"], "model": MODEL,
        "mode": "text_to_image", "seed": cand["seed"], "size": used_size,
        "task_id": task_id, "image_sha256": sha256_bytes(raw),
        "chargeable": True, "at": meta["finished_at"],
    }, ensure_ascii=False)
    with ledger.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")
    return "%s OK  %dx%d %s  %d KB  task=%s…  %ss" % (
        cand["id"], px[0], px[1], fmt, len(raw) // 1024, task_id[:12], elapsed)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--size", type=int, default=1344)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--send", action="store_true", help="不加则只干跑")
    ap.add_argument("--only", default="", help="只处理某个候选，如 A")
    args = ap.parse_args()

    project = Path(args.project)
    key = os.getenv("DASHSCOPE_API_KEY") or ""
    if args.send and not key:
        print("DASHSCOPE_API_KEY 缺失：不能真跑。", file=sys.stderr)
        return 2

    print("模型 %s · 候选 %d 个 · 模式 %s" % (
        MODEL, len(CANDIDATES), "真跑（会付费）" if args.send else "干跑（不付费）"))
    print("固定：prompt_extend=false · watermark=false · n=1 · 每候选固定 seed")
    for cand in CANDIDATES:
        if args.only and cand["id"] != args.only:
            continue
        print("  " + run_one(cand, project, key, args.size, args.send, args.timeout))
    return 0


if __name__ == "__main__":
    sys.exit(main())
