"""Local edits and navigation retain distinct source duties without fake requests."""

from copy import deepcopy

import pytest

from penflow.flow_contract import validate_flow_contract_v2
from penflow.verification_expectations import reconcile_expectations
from penflow.verification_obligations import derive_obligations
from tests.c51_factory import outcome_contract
from tests.pilot_contract_factory import pilot_contract


def _pilot() -> dict:
    return pilot_contract(
        [
            {
                "requirement_id": "livespec:002-payment-outcomes:FR-006",
                "source_pointer": "/body/1",
                "text_sha256": "a" * 64,
            },
            {
                "requirement_id": "livespec:002-payment-outcomes:FR-007",
                "source_pointer": "/body/2",
                "text_sha256": "b" * 64,
            },
        ]
    )


def test_local_edit_is_valid_without_request_side_effects() -> None:
    contract = _pilot()
    assert validate_flow_contract_v2(contract) == []
    assert not [issue for entry in reconcile_expectations(contract) for issue in entry.issues]
    slots = [slot for slot in derive_obligations(contract) if slot.action_id == "edit_amount"]
    assert [(slot.category, slot.outcome) for slot in slots] == [("action", "allowed")]


@pytest.mark.parametrize("change", ["foreign_binding", "read_only", "fake_mutation", "button"])
def test_local_edit_rejects_incoherent_or_weakened_source(change: str) -> None:
    contract = _pilot()
    action = contract["actions"][-1]
    if change == "foreign_binding":
        action["binding_ref"]["field"] = "result"
    elif change == "read_only":
        action["binding_ref"]["access"] = "read"
    elif change == "fake_mutation":
        action["mutation"] = "submit_payment"
    else:
        next(node for node in contract["nodes"] if node["id"] == "checkout.amount")["role"] = (
            "button"
        )
    assert validate_flow_contract_v2(contract)


def test_local_edit_cannot_omit_intended_value() -> None:
    contract = _pilot()
    expected = next(
        item
        for item in contract["outcome_expectations"]
        if item["obligation_id"] == "action:edit_amount:allowed"
    )
    expected["assertions"] = [
        item for item in expected["assertions"] if item["pointer"] != "/after/value"
    ]
    assert any(
        issue["code"] == "obligation.expected.local_value"
        for entry in reconcile_expectations(contract)
        for issue in entry.issues
    )


def test_navigation_has_destination_duty_and_preserves_legacy_requests() -> None:
    contract = outcome_contract()
    original = deepcopy(contract["actions"][0])
    contract["actions"].append(
        {
            "id": "navigate",
            "node": "checkout.title",
            "trigger": "click",
            "kind": "navigation",
            "destination": {"screen": "checkout", "state": "default"},
        }
    )
    contract["nodes"][1].update(role="link", action="navigate")
    assert validate_flow_contract_v2(contract) == []
    slots = [slot for slot in derive_obligations(contract) if slot.action_id == "navigate"]
    assert {slot.category for slot in slots} == {"action", "transition"}
    assert contract["actions"][0] == original
    contract["actions"][-1]["destination"]["state"] = "missing"
    assert validate_flow_contract_v2(contract)


@pytest.mark.parametrize("kind", ["navigation", "state_change"])
def test_legacy_complete_action_kinds_keep_their_request_duties(kind):
    contract = outcome_contract()
    contract["actions"][0]["kind"] = kind
    assert validate_flow_contract_v2(contract) == []
    assert {"action", "permission", "effect", "result", "transition"} <= {
        slot.category
        for slot in derive_obligations(contract)
        if slot.action_id == contract["actions"][0]["id"]
    }
