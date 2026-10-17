"""把归一化图像信封的唯一结构权威导出为 JSON Schema（P6/SEL-025）。

结构权威是 ``src/providers/v2_image.py`` 的 ``ImageWire*`` Pydantic 模型；本工具只做
**机械归一化**（不新增/删除任何校验语义）：

  - Pydantic 2 默认输出 draft 2020-12，这里降到 draft-07（Ajv 默认方言），
    做法是 ``$defs`` → ``definitions`` 与对应的 ``$ref`` 前缀重写；
  - 剥离纯标注键（title/description/default/examples/$comment）：它们不参与校验，
    留着只会让生成的校验器变长、并诱使读者以为默认值会被运行时应用；
  - 固定 ``$id``/``$schema``/``title``，让产物可复现（同一模型 ⇒ 同一字节）。

用法：
    uv run --locked python tools/export_image_envelope_schema.py --out <path>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.providers.v2_image import ImageWireEnvelope  # noqa: E402  （ROOT 先入 sys.path）

SCHEMA_ID = "https://amz-listing-kit.local/schemas/v2/image-envelope.json"
DEFAULT_OUT = Path("app/product_v2/domain/generated/image-task-envelope.schema.json")
# 纯标注键：不参与校验，剥掉后 schema 只剩校验语义。
ANNOTATION_KEYS = frozenset({"title", "description", "default", "examples", "$comment"})


def _strip(node: Any) -> Any:
    if isinstance(node, dict):
        return {key: _strip(value) for key, value in node.items()
                if key not in ANNOTATION_KEYS}
    if isinstance(node, list):
        return [_strip(item) for item in node]
    return node


def _to_draft7(node: Any) -> Any:
    """``$defs`` → ``definitions``（draft-07 方言），并同步重写 ``$ref``。"""
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if key == "$defs":
                out["definitions"] = _to_draft7(value)
                continue
            if key == "$ref" and isinstance(value, str) and value.startswith("#/$defs/"):
                out["$ref"] = "#/definitions/" + value[len("#/$defs/"):]
                continue
            out[key] = _to_draft7(value)
        return out
    if isinstance(node, list):
        return [_to_draft7(item) for item in node]
    return node


def build_schema() -> dict[str, Any]:
    """归一化信封的 draft-07 JSON Schema（唯一导出入口）。"""

    raw = ImageWireEnvelope.model_json_schema(mode="validation")
    schema = _to_draft7(_strip(raw))
    if not isinstance(schema, dict):
        raise TypeError("信封模型导出的 schema 必须是对象。")
    schema.pop("$schema", None)
    schema["$schema"] = "http://json-schema.org/draft-07/schema#"
    schema["$id"] = SCHEMA_ID
    return schema


def main() -> int:
    parser = argparse.ArgumentParser(description="导出归一化图像信封 JSON Schema")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    target = Path(args.out)
    if not target.is_absolute():
        target = ROOT / target
    schema = build_schema()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    definitions = sorted((schema.get("definitions") or {}).keys())
    shown = target.relative_to(ROOT).as_posix() if target.is_relative_to(ROOT) else str(target)
    print(f"[envelope-schema] {shown} · $id={SCHEMA_ID} · definitions={len(definitions)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
