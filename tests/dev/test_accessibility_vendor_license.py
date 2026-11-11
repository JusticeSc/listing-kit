"""可访问性验证器对拆分许可证的完整性判断。"""
from __future__ import annotations

from pathlib import Path

from tools import verify_v2_6_4_accessibility as verifier


def test_original_license_parts_match_registered_digest() -> None:
    assert verifier.sha256_of_parts(verifier.AXE_LICENSE_PARTS) == verifier.AXE_LICENSE_SHA256


def test_changed_license_part_does_not_match_registered_digest(tmp_path: Path) -> None:
    copies = tuple(tmp_path / path.name for path in verifier.AXE_LICENSE_PARTS)
    for source, copy in zip(verifier.AXE_LICENSE_PARTS, copies, strict=True):
        copy.write_bytes(source.read_bytes())
    copies[1].write_bytes(copies[1].read_bytes() + b"changed")
    assert verifier.sha256_of_parts(copies) != verifier.AXE_LICENSE_SHA256


def test_missing_license_part_is_not_accepted(tmp_path: Path) -> None:
    first = tmp_path / verifier.AXE_LICENSE_PARTS[0].name
    first.write_bytes(verifier.AXE_LICENSE_PARTS[0].read_bytes())
    assert verifier.sha256_of_parts((first, tmp_path / "missing.txt")) is None
