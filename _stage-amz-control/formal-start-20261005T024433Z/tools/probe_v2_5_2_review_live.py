#!/usr/bin/env python
"""V2.5.2 最小真实请求：1 次真实 VLM 调用，证明通道 + 结构化输出 + 候选绑定。

预算纪律（计划 §12.2）：
  - 单次调用、无自动重试、不循环抽卡；失败按四归口分类并把请求审计写进证据；
  - 默认输入 = Product V1 真实运行留下的商品原图（与 V2.4.5 同一张）；候选与参考图都是这张
    真实照片，因此本探针**不评估检出质量**，只评估：兼容端点接受图片输入、json_mode 结构化输出、
    发现/绑定/用量可追溯、失败分类正确。检出质量校准是后续任务。

运行（显式 --live 才会真实调用；不带 --live 只做干跑）：
  uv run --locked python tools/probe_v2_5_2_review_live.py --live --label final
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from console import enable_utf8  # noqa: E402
enable_utf8()

from src.providers.v2_dashscope_review import (  # noqa: E402
    DEFAULT_API_KEY_ENV,
    DEFAULT_MODEL_ID,
    DashScopeReviewProvider,
)
from src.providers.v2_review import (  # noqa: E402
    REVIEW_CONTRACT_VERSION,
    DecodedImage,
    DecodedReviewRequest,
    ShotContext,
)
from src.providers.v2_semantic import SemanticFailure  # noqa: E402

EVIDENCE_DIR = ROOT / "evals" / "product-v2"
DEFAULT_REFERENCE = (ROOT / "_working" / "amz-listing-kit-product-demo" / "real-run-01"
                     / "workspace" / "inputs" / "originals"
                     / "5c5e0fdde80847dc140af37778678f3e9b3fb7962bba70360e62630501a85629.jpg")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_request(reference: Path) -> tuple[DecodedReviewRequest, dict]:
    data = reference.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    image = DecodedImage(media_type="image/jpeg", sha256=sha, data=data)
    request = DecodedReviewRequest(
        candidate=image,
        references=(image,),
        shot=ShotContext(title="真实最小请求（通道探针）",
                         purpose="证明复核通道可用；不评估检出质量",
                         keep_items=("商品外观",), allow_changes=("背景",)),
        platform="amazon_us",
        product_facts=(),
        locale="zh-CN",
    )
    audit = {"path": str(reference), "sha256": sha, "byte_size": len(data)}
    return request, audit


def main() -> int:
    parser = argparse.ArgumentParser(description="V2.5.2 最小真实复核请求（1 次调用）")
    parser.add_argument("--live", action="store_true", help="显式确认真实调用（消耗一次模型配额）")
    parser.add_argument("--reference", default="", help="覆盖参考图路径（默认 V1 真实商品原图）")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    reference = Path(args.reference) if args.reference else DEFAULT_REFERENCE
    if not reference.is_file():
        print("参考图不存在：" + str(reference))
        return 2
    request, audit = build_request(reference)
    provider = DashScopeReviewProvider()
    planned = {
        "contract": REVIEW_CONTRACT_VERSION,
        "provider_id": provider.provider_id,
        "model_id": provider.model_id,
        "base_url": provider.base_url,
        "timeout_seconds": provider.timeout,
        "max_tokens": provider.max_tokens,
        "candidate": audit,
        "reference_images": 1,
        "api_key_configured": bool(provider.api_key),
    }
    print(json.dumps(planned, ensure_ascii=False, indent=2))
    if not args.live:
        print("干跑：未调用模型。加 --live 才会发一次真实请求。")
        return 0
    if not provider.api_key:
        print(f"未配置 {DEFAULT_API_KEY_ENV}；拒绝在无密钥时伪造结果。")
        return 2

    started = datetime.now()
    record: dict = {
        "suite_id": "v2.5.2-review-live-probe",
        "observed_at": started.isoformat(timespec="seconds"),
        "planned": planned,
        "attempts": 1,
        "model_calls": 1,
        "note": "候选与参考图是同一张真实照片：只证明通道与结构化输出，不评估检出质量。",
    }
    try:
        result = provider.review(request)
    except SemanticFailure as failure:
        record["status"] = "classified_failure"
        record["error"] = failure.to_dict()
        text = json.dumps(record, ensure_ascii=False, indent=2)
    else:
        record["status"] = "checked"
        record["result"] = result.to_dict()
        record["binding_ok"] = result.candidate_sha256 == audit["sha256"]
        text = json.dumps(record, ensure_ascii=False, indent=2)

    stamp = started.strftime("%Y%m%d-%H%M%S")
    json_path = EVIDENCE_DIR / f"v2.5.2-review-live-{stamp}{args.label}.json"
    txt_path = EVIDENCE_DIR / f"v2.5.2-review-live-{stamp}{args.label}.txt"
    json_path.write_text(text + "\n", encoding="utf-8")
    head = [
        "V2.5.2 最小真实复核请求（单次调用；候选与参考图为同一张真实照片）",
        "NOT-AUTHORITY: point-in-time verification evidence only",
        "=" * 72,
        f"status: {record['status']}",
        f"provider: {planned['provider_id']} · model: {planned['model_id']}",
        f"candidate: {audit['sha256'][:12]}… ({audit['byte_size']} 字节)",
    ]
    if record["status"] == "checked":
        found = record["result"].get("findings") or []
        head.append(f"findings: {len(found)}（check: "
                    + ", ".join(item.get("check", "?") for item in found) + "）")
        head.append(f"request_id: {record['result'].get('request_id')} · "
                    f"latency_ms: {record['result'].get('latency_ms')} · "
                    f"usage: {record['result'].get('usage')}")
        head.append(f"binding_ok: {record['binding_ok']}")
    else:
        head.append("error: " + json.dumps(record["error"], ensure_ascii=False))
    head.extend([
        "",
        "边界：不评估检出质量；失败不重试、不伪造 PASS。",
        f"json: {json_path.relative_to(ROOT).as_posix()}",
    ])
    txt_path.write_text("\n".join(head) + "\n", encoding="utf-8")
    print("\n".join(head))
    print("证据：\n - " + txt_path.relative_to(ROOT).as_posix()
          + "\n - " + json_path.relative_to(ROOT).as_posix())
    return 0 if record["status"] == "checked" and record.get("binding_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
