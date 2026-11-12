"""A guard enforced by the absence of its action is proved by that absence (C51).

Observed: a project edit screen offers Save and Delete only once the project is read. While
the guard does not hold, no control exists, so the generated ``invalid`` branch could
never be observed and stayed ``observation_missing``. A guard may now declare
``enforcement: "absence"``. Its invalid branch is then proved by the control being absent
before and after (``present: false`` facts). The duty is never dropped, and an absence
proves nothing else.
"""

from __future__ import annotations

from copy import deepcopy

import pytest

from penflow.flow_contract import validate_flow_contract_v2
from penflow.verification_expectations import reconcile_expectations
from penflow.verification_outcomes import evaluate_outcome
from penflow.verification_schema import schema_issues
from tests.c51_factory import outcome_contract

GUARD = "payment_input_valid"


def _contract(enforcement: str | None = "absence") -> dict:
    contract = outcome_contract()
    guard = next(item for item in contract["guards"] if item["id"] == GUARD)
    if enforcement is not None:
        guard["enforcement"] = enforcement
    return contract


def _expected(contract: dict, outcome: str) -> dict:
    return next(
        item
        for item in contract["outcome_expectations"]
        if item["obligation_id"] == f"validation:{GUARD}:submit_payment:{outcome}"
    )


def _facts(present: bool, value: str) -> dict:
    facts = {
        "screen_id": "checkout",
        "state": "default",
        "semantic_id": "checkout.pay",
        "role": "button",
        "visible": present,
        "enabled": True if present else None,
        "text": "Pay" if present else None,
        "value": None,
        "bbox": {"x": 0, "y": 0, "width": 100, "height": 40} if present else None,
        "properties": {"payment_input": value},
    }
    if not present:
        facts["present"] = False
    return facts


def _observation(outcome: str, present: bool) -> dict:
    value = "valid" if outcome == "allowed" else "invalid"
    return {
        "kind": "penflow-outcome-observation",
        "version": 1,
        "contract_sha256": "a" * 64,
        "build_id": "build-test",
        "producer_invocation_id": "producer-test",
        "scenario_id": "edit",
        "session_id": "session-test",
        "obligation_id": f"validation:{GUARD}:submit_payment:{outcome}",
        "screen_id": "checkout",
        "semantic_id": "checkout.pay",
        "instance_key": None,
        "category": "validation",
        "capability": "ui",
        "before": _facts(present, value),
        "after": _facts(present, value),
        "result": {"actor_id": "buyer", "action_id": "submit_payment", "outcome": outcome},
        "evidence": {"path": "evidence/absence.json", "sha256": "b" * 64},
    }


def _codes(contract: dict, outcome: str, present: bool) -> list[str]:
    issues = evaluate_outcome(
        _expected(contract, outcome), _observation(outcome, present), contract=contract
    )
    return [item["code"] for item in issues]


def test_the_invalid_branch_is_proved_by_the_absent_control() -> None:
    contract = _contract()
    assert [i for i in validate_flow_contract_v2(contract) if i["severity"] == "error"] == []
    slots = {item.slot.id for item in reconcile_expectations(contract)}
    assert f"validation:{GUARD}:submit_payment:invalid" in slots  # The duty stays.
    assert schema_issues(_observation("invalid", False), "observation") == []
    assert _codes(contract, "invalid", present=False) == []


@pytest.mark.parametrize(
    ("enforcement", "outcome", "present", "code"),
    [
        ("absence", "invalid", True, "outcome.validation.absence_unobserved"),
        (None, "invalid", False, "outcome.validation.absence_undeclared"),
        ("refusal", "invalid", False, "outcome.validation.absence_undeclared"),
        ("absence", "allowed", False, "outcome.validation.absence_undeclared"),
    ],
)
def test_an_absence_proves_only_the_declared_branch(
    enforcement: str | None, outcome: str, present: bool, code: str
) -> None:
    assert code in _codes(_contract(enforcement), outcome, present)


def test_absent_facts_cannot_carry_geometry_or_text() -> None:
    observed = _observation("invalid", False)
    broken = deepcopy(observed)
    broken["after"]["bbox"] = {"x": 0, "y": 0, "width": 1, "height": 1}
    assert schema_issues(broken, "observation")
    broken = deepcopy(observed)
    broken["after"]["visible"] = True
    assert schema_issues(broken, "observation")
