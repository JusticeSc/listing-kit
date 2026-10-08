"""Deterministic file checks and export layout for Product V1 selected candidates.

Everything here is measured from the exported bytes or read from the frozen
platform profile. Semantic and aesthetic judgements stay with the human reviewer;
no rule is reported as verified unless a deterministic measurement produced it.
"""
from __future__ import annotations

import io
import re
from typing import Any, Iterable, Mapping, Sequence

from PIL import Image, UnidentifiedImageError


class ProductExportError(ValueError):
    """A selected candidate cannot be laid out under the current platform profile."""


_MEDIA_TYPES = {
    "JPEG": ("jpg", "image/jpeg"),
    "PNG": ("png", "image/png"),
    "TIFF": ("tif", "image/tiff"),
    "GIF": ("gif", "image/gif"),
}
_PROFILE_FORMATS = {
    "jpeg": "JPEG", "jpg": "JPEG", "png": "PNG",
    "tiff": "TIFF", "tif": "TIFF", "gif": "GIF",
}
_SLUG = re.compile(r"[^a-z0-9]+")

# Rules whose failure stops a publish. Measured review items are recorded but do
# not silently masquerade as a verified Amazon compliance gate.
BLOCKING_RULE_IDS = ("file_format_accepted", "long_side_min_px", "long_side_max_px")


def inspect_image(content: bytes) -> dict[str, Any]:
    """Decode the bytes we are about to export; never trust stored metadata."""
    try:
        with Image.open(io.BytesIO(content)) as decoded:
            decoded.load()
            return {
                "format": (decoded.format or "").upper(),
                "width": int(decoded.width),
                "height": int(decoded.height),
            }
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ProductExportError("候选图片无法解码，未生成导出。") from exc


def media_type_for(image_format: str) -> tuple[str, str]:
    entry = _MEDIA_TYPES.get((image_format or "").upper())
    if entry is None:
        name = image_format or "未知"
        raise ProductExportError(f"平台文件规则不接受 {name} 格式。")
    return entry


def border_whiteness(content: bytes, *, tolerance: int = 6) -> float:
    """Share of pure-white pixels on the outer border of an image.

    This measures one main-image requirement. It is not a proof that the image
    satisfies Amazon main-image policy: occupancy, staging and semantic content
    still need a human reviewer.
    """
    with Image.open(io.BytesIO(content)) as decoded:
        rgb = decoded.convert("RGB")
        width, height = rgb.size
        pixels = rgb.load()
        samples: list[tuple[int, int, int]] = []
        for x in range(width):
            samples.append(pixels[x, 0])
            samples.append(pixels[x, height - 1])
        for y in range(height):
            samples.append(pixels[0, y])
            samples.append(pixels[width - 1, y])
    if not samples:
        return 0.0
    white = sum(
        1 for red, green, blue in samples
        if abs(red - 255) <= tolerance
        and abs(green - 255) <= tolerance
        and abs(blue - 255) <= tolerance
    )
    return round(white / len(samples), 4)


def profile_rule_version(platform_profile: Mapping[str, Any]) -> str:
    return f"{platform_profile.get('profile_id', 'unknown')}@{platform_profile.get('version', 1)}"


def file_checks(
    *,
    image: Mapping[str, Any],
    content: bytes,
    platform_profile: Mapping[str, Any],
    is_primary: bool,
) -> list[dict[str, Any]]:
    """Deterministic, reproducible checks carrying their measured values."""
    rules = platform_profile.get("file_rules") or {}
    version = profile_rule_version(platform_profile)
    source = (platform_profile.get("source") or {}).get("url") or "未记录来源"
    image_format = str(image.get("format") or "").upper()
    _, media_type = media_type_for(image_format)
    accepted = {str(item).strip().lower() for item in rules.get("accepted_formats", [])}
    accepted_formats = {_PROFILE_FORMATS.get(item, item.upper()) for item in accepted}
    long_side = max(int(image["width"]), int(image["height"]))
    minimum = int(rules.get("min_long_side_px", 0) or 0)
    maximum = int(rules.get("max_long_side_px", 0) or 0)
    checks: list[dict[str, Any]] = [
        {
            "rule_id": "file_format_accepted",
            "rule_version": version,
            "passed": not accepted or image_format in accepted_formats,
            "detail": f"实测格式 {image_format}（{media_type}）；规则允许 {sorted(accepted) or '未限制'}；来源 {source}",
        },
        {
            "rule_id": "long_side_min_px",
            "rule_version": version,
            "passed": long_side >= minimum,
            "detail": f"实测长边 {long_side}px，下限 {minimum}px；来源 {source}",
        },
        {
            "rule_id": "long_side_max_px",
            "rule_version": version,
            "passed": not maximum or long_side <= maximum,
            "detail": f"实测长边 {long_side}px，上限 {maximum or '未限制'}px；来源 {source}",
        },
    ]
    if is_primary:
        share = border_whiteness(content)
        checks.append({
            "rule_id": "main_image_border_whiteness_measured",
            "rule_version": version,
            "passed": share >= 0.95,
            "detail": (
                f"实测主图外边框纯白占比 {share:.0%}；本项只测外边框像素，"
                "不代替 Amazon 主图对占比、构图与语义的全部要求，异常时需人工核对。"
            ),
        })
    return checks


def export_file_name(*, order: int, archetype_id: str, file_sha256: str, extension: str) -> str:
    """Stable ASCII upload name; the human-facing title stays in the manifest."""
    slug = _SLUG.sub("-", str(archetype_id or "shot").strip().lower()).strip("-") or "shot"
    return f"{order:02d}-{slug}-{file_sha256[:12]}.{extension}"


def blocked_rule_ids(checks: Sequence[Mapping[str, Any]]) -> list[str]:
    blocking = set(BLOCKING_RULE_IDS)
    return sorted({
        str(check.get("rule_id")) for check in checks
        if check.get("rule_id") in blocking and not check.get("passed")
    })


def review_rule_ids(checks: Sequence[Mapping[str, Any]]) -> list[str]:
    """Measured items that need a human decision instead of an automatic gate."""
    blocking = set(BLOCKING_RULE_IDS)
    return sorted({
        str(check.get("rule_id")) for check in checks
        if check.get("rule_id") not in blocking and not check.get("passed")
    })


def readme_lines(
    *,
    export_id: str,
    selection_id: str,
    selection_version: int,
    platform_profile: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    source = platform_profile.get("source") or {}
    lines = [
        f"# 导出 {export_id}",
        "",
        f"- 选择版本：{selection_id} v{selection_version}",
        f"- 平台规则：{profile_rule_version(platform_profile)}（{platform_profile.get('marketplace', 'unknown')}）",
    ]
    if source.get("url"):
        lines.append(f"- 规则来源：{source.get('url')}（核对于 {source.get('verified_on', '未知')}）")
    lines += ["", "## 文件", ""]
    for row in rows:
        lines.append(
            f"- `{row['relative_path']}` ← {row['title']}（{row['archetype_id']}），"
            f"源候选 {str(row['candidate_sha256'])[:16]}…，文件 hash {str(row['file_sha256'])[:16]}…"
        )
    lines += [
        "",
        "## 边界",
        "",
        "- 这里只导出当前选择版本中的候选；旧候选仍保留在工作空间，可重新选择后再次导出。",
        "- 确定性文件检查结果见 manifest.json 的 checks；审美与语义判断属于人工审核，未在此处自动化。",
    ]
    return lines
