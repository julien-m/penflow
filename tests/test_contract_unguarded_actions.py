"""A local state change without a precondition is declared, never given a fake guard (C51).

Observed: a "show abandoned tasks" toggle has no precondition. The schema required a guard
on every local submit action, so the only valid contract invented one. Its generated
``invalid`` branch then failed against a real click, or could never be observed. An action
may now declare ``precondition: "none"``. It then has no guard, no guarded transition and
no validation duty; its action and transition duties stay.
"""

from __future__ import annotations

import pytest

from penflow.flow_contract import validate_flow_contract_v2
from penflow.verification_obligations import derive_obligations
from tests.test_contract_local_submit import local_submit_contract


def _unguarded() -> dict:
    contract = local_submit_contract()
    action = contract["actions"][0]
    action.pop("guard")
    action["precondition"] = "none"
    for transition in contract["transitions"]:
        transition.pop("guard", None)
    contract["guards"] = []
    return contract


def _errors(contract: dict) -> list[str]:
    return sorted(
        i["code"] for i in validate_flow_contract_v2(contract) if i["severity"] == "error"
    )


def test_a_declared_unguarded_toggle_is_valid_and_has_no_validation_duty() -> None:
    contract = _unguarded()
    assert _errors(contract) == []
    duties = {(slot.category, slot.outcome) for slot in derive_obligations(contract)}
    assert ("action", "allowed") in duties
    assert any(category == "transition" for category, _ in duties)
    assert not any(category == "validation" for category, _ in duties)


@pytest.mark.parametrize("case", ["silent", "both", "guarded-transition"])
def test_a_guard_is_never_dropped_silently(case: str) -> None:
    contract = _unguarded()
    action = contract["actions"][0]
    if case == "silent":
        action.pop("precondition")  # A missing guard without a declaration stays invalid.
    elif case == "both":
        reference = local_submit_contract()
        contract["guards"] = reference["guards"]
        action["guard"] = reference["actions"][0]["guard"]
    else:
        reference = local_submit_contract()
        contract["guards"] = reference["guards"]
        contract["transitions"][0]["guard"] = reference["transitions"][0]["guard"]
    errors = _errors(contract)
    assert errors, case
    if case == "guarded-transition":
        assert "contract.reference.precondition_conflict" in errors
