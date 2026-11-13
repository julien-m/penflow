"""Permission-domain regressions over explicit source and typed protocol packets.

These synthetic packets exercise validators; they do not certify a live application.
"""

from copy import deepcopy
from pathlib import Path

import pytest

from penflow.flow_contract import validate_flow_contract_v2
from penflow.verification_expectations import reconcile_expectations
from penflow.verification_obligations import derive_obligations
from penflow.verification_outcomes import evaluate_outcome
from penflow.verification_schema import schema_issues
from tests.c51_factory import outcome_contract, persistence_observation
from tests.test_verification_guard_absence import _observation


def _expectation(permission: str, index: int, actor: str, outcome: str) -> dict:
    return {
        "obligation_id": f"permission:{permission}:submit_payment:{outcome}",
        "source_pointer": f"/permissions/{index}",
        "category": "permission",
        "assertions": [
            {"operator": "equals", "pointer": pointer, "expected": value, "capability": "ui"}
            for pointer, value in {
                "/result/actor_id": actor,
                "/result/action_id": "submit_payment",
                "/result/outcome": outcome,
            }.items()
        ],
    }


def _packet(*, visitor: bool = False, visitor_granted: bool = False) -> dict:
    # Keep the existing authored non-permission predicates, then supply the exact
    # permission expectations independently of derive_obligations.
    contract = outcome_contract()
    contract["actors"] = [{"id": "buyer", "name": "Buyer"}]
    if visitor:
        contract["actors"].append({"id": "visitor", "name": "Visitor"})
    expected = [row for row in contract["outcome_expectations"] if row["category"] != "permission"]
    expected.append(_expectation("buyer_can_pay", 0, "buyer", "allowed"))
    if visitor_granted:
        contract["permissions"].append(
            {
                "id": "visitor_can_pay",
                "actor": "visitor",
                "action": "submit_payment",
                "entity": "checkout",
            }
        )
        expected.append(_expectation("visitor_can_pay", 1, "visitor", "allowed"))
    elif visitor:
        expected.append(_expectation("buyer_can_pay", 0, "visitor", "denied"))
    contract["outcome_expectations"] = expected
    return contract


def _permission_entries(contract: dict) -> list:
    return [
        entry for entry in reconcile_expectations(contract) if entry.slot.category == "permission"
    ]


def _observed(expected: dict) -> dict:
    values = {row["pointer"]: row["expected"] for row in expected["assertions"]}
    observed = _observation("allowed", True)
    observed.update(obligation_id=expected["obligation_id"], category="permission")
    observed["result"].update(
        actor_id=values["/result/actor_id"], outcome=values["/result/outcome"]
    )
    return observed


def _functional_packet(contract: dict, *, denied: bool) -> list[dict]:
    """Capture the checkout example's authored scenarios, independent of expectations."""
    observations = [persistence_observation()]

    def add(identity: str, category: str, outcome: str) -> dict:
        observed = _observation(outcome, True)
        observed.update(obligation_id=identity, category=category)
        observations.append(observed)
        return observed

    add("action:submit_payment:allowed", "action", "allowed")
    for guard, variable, value in (
        ("payment_ready", "payment_result", "success"),
        ("payment_failed", "payment_result", "error"),
        ("payment_input_valid", "payment_input", "valid"),
    ):
        for outcome, measured in (("allowed", value), ("invalid", "not-satisfied")):
            observed = add(f"validation:{guard}:submit_payment:{outcome}", "validation", outcome)
            observed["before"]["properties"][variable] = measured
    for outcome, status in (("success", 201), ("error", 500)):
        observed = add(f"effect:create_payment:submit_payment:{outcome}", "effect", outcome)
        observed.update(
            capability="network",
            before={"actor_id": "buyer", "method": "POST", "url": "/payments", "body": {}},
            after={"status": status, "body": {}},
        )
        observed = add(f"result:create_payment:submit_payment:{outcome}", "result", outcome)
        observed["after"]["state"] = outcome
        observed = add(f"transition:payment_{outcome}", "transition", outcome)
        observed["after"]["state"] = outcome
    for permission in contract["permissions"]:
        index = contract["permissions"].index(permission)
        observations.append(
            _observed(_expectation(permission["id"], index, permission["actor"], "allowed"))
        )
        if denied:
            observations.append(
                _observed(_expectation(permission["id"], index, "visitor", "denied"))
            )
    return observations


@pytest.mark.parametrize(
    "visitor,granted,count", [(False, False, 1), (True, False, 2), (True, True, 2)]
)
def test_complete_permission_packets(visitor: bool, granted: bool, count: int) -> None:
    contract = _packet(visitor=visitor, visitor_granted=granted)
    before = deepcopy(contract)
    assert validate_flow_contract_v2(contract) == []
    entries = reconcile_expectations(contract)
    assert not [issue for entry in entries for issue in entry.issues]
    permissions = [entry for entry in entries if entry.slot.category == "permission"]
    assert len(permissions) == count
    observations = {
        item["obligation_id"]: item
        for item in _functional_packet(contract, denied=visitor and not granted)
    }
    functional = [entry for entry in entries if entry.slot.category != "structure"]
    assert set(observations) == {entry.slot.id for entry in functional}
    for entry in functional:
        assert entry.expected is not None
        observed = observations[entry.slot.id]
        assert schema_issues(observed, "observation") == []
        assert evaluate_outcome(entry.expected, observed, contract=contract) == []
    assert contract == before


def test_missing_negative_expectation_blocks_when_a_declared_actor_is_unauthorized() -> None:
    contract = _packet(visitor=True)
    contract["outcome_expectations"].pop()
    denied = next(
        entry for entry in _permission_entries(contract) if entry.slot.outcome == "denied"
    )
    assert denied.expected is None
    assert denied.issues[0]["code"] == "obligation.expectation.cardinality"


def test_missing_negative_observation_blocks_the_runtime_slot(tmp_path: Path) -> None:
    from penflow.verification_files import InputReader
    from penflow.verification_policy import GateBook
    from penflow.verification_runtime import _one_obligation
    from penflow.verification_snapshot import VerificationSnapshot

    contract = _packet(visitor=True)
    denied = next(
        entry for entry in _permission_entries(contract) if entry.slot.outcome == "denied"
    )
    snapshot = VerificationSnapshot(InputReader(tmp_path), tmp_path, contract, {}, {})
    errors, refs = _one_obligation(snapshot, GateBook("implementation"), {}, {}, denied, True)
    assert [row["code"] for row in errors] == ["verification.obligation.observation_missing"]
    assert refs == []


def test_explicit_impossible_negative_is_unbound_and_blocking() -> None:
    contract = _packet()
    contract["outcome_expectations"].append(_expectation("buyer_can_pay", 0, "buyer", "denied"))
    assert any(
        issue["code"] == "obligation.expectation.unbound"
        for entry in reconcile_expectations(contract)
        for issue in entry.issues
    )


@pytest.mark.parametrize("actor", ["buyer", "foreign"])
def test_authorized_or_unknown_actor_cannot_supply_a_denied_witness(actor: str) -> None:
    contract = _packet(visitor=True)
    expected = contract["outcome_expectations"][-1]
    expected["assertions"][0]["expected"] = actor
    assert any(entry.issues for entry in _permission_entries(contract))
    assert evaluate_outcome(expected, _observed(expected), contract=contract)


def test_permission_cannot_reference_an_undeclared_actor() -> None:
    contract = _packet()
    contract["permissions"][0]["actor"] = "foreign"
    assert validate_flow_contract_v2(contract)
    with pytest.raises(ValueError):
        derive_obligations(contract)


def test_another_entity_grant_does_not_authorize_this_permission() -> None:
    contract = _packet(visitor=True)
    contract["entities"].append({"id": "other", "fields": [{"id": "title", "type": "string"}]})
    contract["permissions"].append(
        {"id": "visitor_other", "actor": "visitor", "action": "submit_payment", "entity": "other"}
    )
    expected = _expectation("buyer_can_pay", 0, "visitor", "denied")
    assert evaluate_outcome(expected, _observed(expected), contract=contract) == []
    assert "permission:buyer_can_pay:submit_payment:denied" in {
        slot.id for slot in derive_obligations(contract)
    }


def test_another_action_grant_does_not_authorize_this_permission() -> None:
    contract = _packet(visitor=True)
    contract["nodes"][1].update(role="link", action="navigate")
    contract["actions"].append(
        {
            "id": "navigate",
            "node": "checkout.title",
            "trigger": "click",
            "kind": "navigation",
            "destination": {"screen": "checkout", "state": "default"},
        }
    )
    contract["permissions"].append(
        {
            "id": "visitor_navigate",
            "actor": "visitor",
            "action": "navigate",
            "entity": "checkout",
        }
    )
    assert validate_flow_contract_v2(contract) == []
    expected = _expectation("buyer_can_pay", 0, "visitor", "denied")
    assert evaluate_outcome(expected, _observed(expected), contract=contract) == []
    assert "permission:buyer_can_pay:submit_payment:denied" in {
        slot.id for slot in derive_obligations(contract)
    }


def test_second_grant_authorizes_non_permission_outcomes_too() -> None:
    contract = _packet(visitor=True, visitor_granted=True)
    expected = next(
        row for row in contract["outcome_expectations"] if row["category"] == "persistence"
    )
    expected["assertions"][0]["expected"] = "visitor"
    observed = persistence_observation()
    observed["result"]["actor_id"] = "visitor"
    assert evaluate_outcome(expected, observed, contract=contract) == []


def test_explicit_negative_for_another_granted_actor_cannot_be_accepted() -> None:
    contract = _packet(visitor=True, visitor_granted=True)
    contract["outcome_expectations"].append(_expectation("buyer_can_pay", 0, "visitor", "denied"))
    assert any(
        issue["code"] == "obligation.expectation.unbound"
        for entry in reconcile_expectations(contract)
        for issue in entry.issues
    )
    expected = contract["outcome_expectations"][-1]
    assert any(
        issue["code"] == "outcome.permission"
        for issue in evaluate_outcome(expected, _observed(expected), contract=contract)
    )


def test_partial_grants_keep_a_negative_for_each_permission() -> None:
    contract = _packet(visitor=True, visitor_granted=True)
    contract["actors"].append({"id": "auditor", "name": "Auditor"})
    for index, permission in enumerate(contract["permissions"]):
        contract["outcome_expectations"].append(
            _expectation(permission["id"], index, "auditor", "denied")
        )
    entries = _permission_entries(contract)
    assert len(entries) == 4
    assert sum(entry.slot.outcome == "denied" for entry in entries) == 2
    assert not [issue for entry in reconcile_expectations(contract) for issue in entry.issues]
    for entry in entries:
        assert entry.expected is not None
        assert evaluate_outcome(entry.expected, _observed(entry.expected), contract=contract) == []


def test_each_grant_still_requires_its_own_positive_actor() -> None:
    contract = _packet(visitor=True, visitor_granted=True)
    expected = next(
        row
        for row in contract["outcome_expectations"]
        if row["obligation_id"] == "permission:buyer_can_pay:submit_payment:allowed"
    )
    expected["assertions"][0]["expected"] = "visitor"
    assert any(
        issue["code"] == "obligation.expected.permission"
        for entry in reconcile_expectations(contract)
        for issue in entry.issues
    )
