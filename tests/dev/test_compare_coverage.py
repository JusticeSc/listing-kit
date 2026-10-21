"""比较验证器的判错行为：合法扩展、必需覆盖与真实失败互不替代。"""
from __future__ import annotations

import json

import pytest

from tools import verify_v2_5_3_compare_panel as verifier


@pytest.fixture
def passed_suite() -> dict:
    contract = json.loads((verifier.ROOT / "config/product-v2/compare-contract.json").read_text(encoding="utf-8"))
    return {
        "status": "passed",
        "cases": [{"id": case_id, "ok": True} for case_id in contract["required_cases"]],
        "failed_ids": [],
    }


def test_additional_passing_case_is_allowed(passed_suite: dict) -> None:
    passed_suite["cases"].append({"id": "CP-EXTRA", "ok": True})
    assert verifier.compare_suite_check(passed_suite)["ok"] is True


def test_missing_required_execution_is_not_a_passing_suite(passed_suite: dict) -> None:
    passed_suite["cases"] = [case for case in passed_suite["cases"] if case["id"] != "CP-16"]
    assert verifier.compare_suite_check(passed_suite)["ok"] is False


def test_failure_in_additional_case_cannot_be_hidden_by_passing_summary(passed_suite: dict) -> None:
    passed_suite["cases"].append({"id": "CP-EXTRA", "ok": False})
    assert verifier.compare_suite_check(passed_suite)["ok"] is False


def test_unfinished_suite_does_not_pass(passed_suite: dict) -> None:
    passed_suite["status"] = "running"
    assert verifier.compare_suite_check(passed_suite)["ok"] is False


def test_empty_required_contract_cannot_disable_coverage(
    passed_suite: dict, tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract_path = tmp_path / "config/product-v2/compare-contract.json"
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text('{"required_cases": {}}', encoding="utf-8")
    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    with pytest.raises(ValueError):
        verifier.compare_suite_check(passed_suite)
