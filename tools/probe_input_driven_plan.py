#!/usr/bin/env python
"""D1.6 input-driven reverse probe against the real semantic provider.

Two structurally different products (knit cardigan vs quartz wristwatch) run through
intake -> ProductBrief -> Plan -> compiled Prompt using real, non-fixture photos.
Checks:

- no built-in fixture tokens (Aster / water-cup copy) leak into any output;
- the two plans differ structurally (shot count or archetype combination);
- the compiled product_fidelity block differs between the two products.

Writes raw JSON and a markdown summary into evals/product-demo/. Exits non-zero if a
check fails; the raw artifact is still written so the failure is auditable.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.application_service import ApplicationService, ImageUpload

EVIDENCE = ROOT / "evals" / "product-demo"
ECOMMERCE = Path(r"E:\workbuddy_workspace\2026-09-20-16-38-19\ecommerce-skills-main\docs")
FIXTURE_TOKENS = ("Aster", "保温杯")

PRODUCTS = [
    {
        "key": "sweater",
        "product_name": "粗棒针织开衫毛衣",
        "description": "宽松落肩的长袖针织开衫，V 领单排扣，适合春秋通勤内搭。",
        "selling_points": ["粗棒针立体纹理", "宽松落肩版型"],
        "user_intent": "呈现毛衣的针织纹理与自然垂感，避免厚重臃肿效果。",
        "image": ECOMMERCE / "batch-image" / "sku-a-sweater.jpg",
    },
    {
        "key": "watch",
        "product_name": "简约石英腕表",
        "description": "细表带的圆形表盘石英腕表，不锈钢表壳，日常通勤风格。",
        "selling_points": ["矿物强化玻璃镜面", "细表带轻佩戴"],
        "user_intent": "突出表盘质感与轻薄佩戴感，避免运动或潜水场景。",
        "image": ECOMMERCE / "fission-pattern" / "product-watch.jpg",
    },
]


def require_ok(response, label: str):
    if not response.ok:
        raise AssertionError(
            f"{label} failed: {json.dumps(response.body, ensure_ascii=False)}"
        )
    return response.body["data"]


def run_product(service: ApplicationService, spec: dict, root: Path) -> dict:
    image_path: Path = spec["image"]
    image_bytes = image_path.read_bytes()
    workspace = root / spec["key"]
    created = require_ok(service.create_workspace(workspace), "create workspace")
    intake = require_ok(service.save_intake(
        workspace,
        expected_etag=created["workspace"]["revision"],
        product_name=spec["product_name"],
        description=spec["description"],
        selling_points=spec["selling_points"],
        user_intent=spec["user_intent"],
        reference_images=[ImageUpload(image_path.name, image_bytes, "primary")],
    ), "save intake")
    draft = require_ok(service.generate_product_brief_draft(
        workspace, expected_etag=intake["workspace"]["revision"],
    ), "brief draft")
    brief = require_ok(service.save_product_brief(
        workspace, expected_etag=draft["workspace_revision"], fields=draft["product_brief"],
    ), "save brief")
    plan_data = require_ok(service.generate_product_plan(
        workspace, expected_etag=brief["workspace"]["revision"],
    ), "generate plan")
    revision = plan_data["workspace"]["revision"]
    prompt_providers = []
    for shot in plan_data["plan"]["shot_specs"]:
        prompt_data = require_ok(service.generate_prompt(
            workspace, expected_etag=revision, shot_id=shot["id"],
        ), f"compile prompt {shot['id']}")
        revision = prompt_data["workspace"]["revision"]
        prompt_providers.append({
            "shot_id": shot["id"],
            "semantic_provider": prompt_data.get("semantic_provider"),
        })
    projection = require_ok(service.get_workspace_projection(workspace), "projection")
    shots = []
    for shot in projection["plan"]["shot_specs"]:
        prompt = shot.get("latest_prompt") or {}
        blocks = prompt.get("blocks") or []
        product_block = next(
            (block.get("text") for block in blocks if block.get("kind") == "product_fidelity"),
            None,
        )
        shots.append({
            "id": shot["id"],
            "title": shot["title"],
            "archetype_id": shot["archetype_id"],
            "purpose": shot.get("purpose"),
            "required": shot.get("required"),
            "preserve": shot.get("preserve"),
            "change": shot.get("change"),
            "prompt_version": prompt.get("version"),
            "prompt_full_text": prompt.get("full_text"),
            "product_fidelity_block": product_block,
            "source_refs": [ref for block in blocks for ref in block.get("source_refs", [])],
        })
    return {
        "key": spec["key"],
        "product_name": spec["product_name"],
        "reference_image": {
            "path": str(image_path),
            "sha256": hashlib.sha256(image_bytes).hexdigest(),
            "bytes": len(image_bytes),
        },
        "semantic_provider": {
            "brief": draft.get("semantic_provider"),
            "plan": plan_data.get("semantic_provider"),
            "prompts": prompt_providers,
        },
        "brief": projection.get("product_brief"),
        "compile_warnings": plan_data.get("compile_warnings", []),
        "shots": shots,
    }


def main() -> int:
    stamp = datetime.now().strftime("%Y-%m-%d")
    for spec in PRODUCTS:
        if not spec["image"].is_file():
            print(f"missing reference image: {spec['image']}", file=sys.stderr)
            return 2
    service = ApplicationService()
    with tempfile.TemporaryDirectory(prefix="amz-d16-probe-") as raw_root:
        results = [run_product(service, spec, Path(raw_root)) for spec in PRODUCTS]
    first, second = results
    payload_json = json.dumps(results, ensure_ascii=False, indent=2)
    leaks = [token for token in FIXTURE_TOKENS if token in payload_json]
    signatures = [
        {"shot_count": len(item["shots"]), "archetypes": sorted(s["archetype_id"] for s in item["shots"])}
        for item in results
    ]
    structural_difference = signatures[0] != signatures[1]
    blocks_first = {s["product_fidelity_block"] for s in first["shots"]}
    blocks_second = {s["product_fidelity_block"] for s in second["shots"]}
    product_block_differs = (
        None not in blocks_first | blocks_second and blocks_first != blocks_second
    )
    checks = {
        "no_fixture_leak": {"passed": not leaks, "leaked_tokens": leaks},
        "plan_structural_difference": {"passed": structural_difference, "signatures": signatures},
        "product_block_differs": {
            "passed": product_block_differs,
            "sweater_blocks": sorted(blocks_first),
            "watch_blocks": sorted(blocks_second),
        },
    }
    failed = [name for name, item in checks.items() if not item["passed"]]
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    raw_path = EVIDENCE / f"d1.6-input-driven-probe-raw-{stamp}.json"
    raw_path.write_text(payload_json, encoding="utf-8")
    summary = {
        "probe": "D1.6 input-driven reverse probe",
        "date": stamp,
        "semantic_provider": {
            "brief": first["semantic_provider"]["brief"],
            "plan": first["semantic_provider"]["plan"],
        },
        "checks": checks,
        "passed": not failed,
        "raw_evidence": raw_path.name,
        "products": [
            {
                "key": item["key"],
                "product_name": item["product_name"],
                "reference_image": item["reference_image"],
                "shot_count": len(item["shots"]),
                "archetypes": [s["archetype_id"] for s in item["shots"]],
                "shot_titles": [s["title"] for s in item["shots"]],
            }
            for item in results
        ],
    }
    markdown = [
        "# D1.6 输入驱动反向探针 - 证据",
        "",
        f"- 日期：{stamp}（真实语义模型，非 Fake；provider/model/request id 见原始 JSON）",
        f"- 原始证据：`{raw_path.name}`",
        f"- 参考图 A：`{first['reference_image']['path']}` sha256={first['reference_image']['sha256'][:16]}…",
        f"- 参考图 B：`{second['reference_image']['path']}` sha256={second['reference_image']['sha256'][:16]}…",
        f"- 结论：{'全部通过' if not failed else '失败 ' + ', '.join(failed)}",
        "",
        "## 检查项",
        "",
    ]
    for name, item in checks.items():
        markdown.append(f"- {name}: {'passed' if item['passed'] else 'FAILED'} `{json.dumps(item, ensure_ascii=False)}`")
    markdown += [
        "",
        "## 两商品结构对照",
        "",
        f"- {first['product_name']}：{len(first['shots'])} 张，" + "、".join(sorted({s['archetype_id'] for s in first['shots']})),
        f"- {second['product_name']}：{len(second['shots'])} 张，" + "、".join(sorted({s['archetype_id'] for s in second['shots']})),
        "",
        "## 边界",
        "",
        "- 本探针验证输入驱动与结构差异，不评价生成图像的真实质量（属于 D2.5 / 人工审核）。",
        "- 两个商品均为外部真实照片（ecommerce-skills），不是内置夹具。",
        "",
    ]
    md_path = EVIDENCE / f"d1.6-input-driven-probe-{stamp}.md"
    md_path.write_text("\n".join(markdown), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
