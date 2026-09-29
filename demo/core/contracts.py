"""处理合同的机器口径 —— 结果词汇与状态取值只有一处权威。

为什么要有这一层：实现里最容易发生的事，是某一步**自己发明一个状态**
（`ok`、`done`、`maybe`、`partial`）。发明出来的状态不在计划 §4.4 的闭集合里，
于是它既不受 Unknown 规则约束，也不会被任何验收看见 —— 红被吃掉的最常见形态。

所以每个环节的返回值都要过这里：合同 ID 必须存在，结果必须在该合同自己声明的
那几个结果里。写错一个字就当场抛错，而不是等到发布审计才发现。

读的是 `demo/contract/` 下的机器契约，不另抄一份词汇。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_REL = "demo/contract/processing_contracts.json"
VOCABULARY_REL = "demo/contract/state_vocabulary.json"


class ContractViolation(RuntimeError):
    """实现试图产出一个合同不允许的状态。这是代码缺陷，不是业务结果。"""


def _load(rel: str) -> dict:
    path = ROOT / rel
    if not path.is_file():
        raise ContractViolation(f"缺机器契约 {rel} —— 词汇表没有权威来源就不许往下跑")
    return json.loads(path.read_text(encoding="utf-8"))


_CONTRACTS_DOC = _load(CONTRACTS_REL)
_VOCABULARY_DOC = _load(VOCABULARY_REL)

OUTCOMES: tuple[str, ...] = tuple(_CONTRACTS_DOC["outcome_vocabulary"])
PLAN_VERSION: str = _CONTRACTS_DOC["plan_version"]
CONTRACTS: dict[str, dict] = {c["id"]: c for c in _CONTRACTS_DOC["contracts"]}
STATE_MACHINES: dict[str, dict] = _VOCABULARY_DOC["machines"]


def contract(contract_id: str) -> dict:
    try:
        return CONTRACTS[contract_id]
    except KeyError:
        raise ContractViolation(f"未登记的合同 ID：{contract_id!r}") from None


def outcomes_of(contract_id: str) -> tuple[str, ...]:
    return tuple(contract(contract_id)["outcomes"])


def allowed_states(machine: str) -> tuple[str, ...]:
    try:
        return tuple(STATE_MACHINES[machine]["states"])
    except KeyError:
        raise ContractViolation(f"未登记的状态机：{machine!r}") from None


@dataclass
class StepResult:
    """一个环节的返回值。`outcome` 的取值受合同闭集合约束。"""

    contract_id: str
    outcome: str
    payload: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        spec = contract(self.contract_id)
        if self.outcome not in OUTCOMES:
            raise ContractViolation(
                f"{self.contract_id}: 结果 {self.outcome!r} 不在计划 §4.4 的闭集合 {OUTCOMES}")
        if self.outcome not in spec["outcomes"]:
            raise ContractViolation(
                f"{self.contract_id}: 结果 {self.outcome!r} 不是本合同声明过的结果 "
                f"{tuple(spec['outcomes'])}")
        if self.outcome == "needs_human" and not any(
                "人" in n or "用户" in n for n in self.notes):
            raise ContractViolation(
                f"{self.contract_id}: needs_human 必须写明需要人做什么")

    @property
    def accepted(self) -> bool:
        return self.outcome == "accepted"

    def as_dict(self) -> dict:
        return {"contract": self.contract_id, "outcome": self.outcome,
                "payload": self.payload, "evidence": self.evidence, "notes": self.notes}


def blocked_by(contract_id: str, upstream: StepResult) -> StepResult:
    """上游没通过时，本环节不许继续 —— 也不能改口说"没做"。

    返回与上游同强度的 `business_reject`，并把上游状态写进证据，
    这样调用方一眼能看出是被谁挡住的。
    """
    return StepResult(
        contract_id=contract_id,
        outcome="business_reject",
        payload={"blocked_by": upstream.contract_id},
        evidence={"upstream": upstream.as_dict()},
        notes=[f"上游 {upstream.contract_id} 的结果是 {upstream.outcome}，本环节不继续"],
    )