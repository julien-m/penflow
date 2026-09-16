"""Local submit source validity and C51 duties without invented network effects."""

# @spec AC-003: strict local submit references — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#ac-003
# @spec AC-007: lossless local submit projection — .specs/features/045-penflow-json-only-strict-contract-v2/spec.md#ac-007

import pytest

from penflow.contract_actions import action_mode
from penflow.flow_contract import validate_flow_contract_v2
from penflow.verification_obligations import derive_obligations
from penflow.verification_expectations import reconcile_expectations
from penflow.semantic_contract import semantic_tree_from_contract
from penflow.code_ir import code_ir_from_pen
from tests.contract_factory import valid_contract


def local_submit_contract() -> dict:
    """Build a local transition using existing independent contract records."""
    contract = valid_contract()
    action = contract["actions"][0]
    action.update(kind="state_change", event="submit")
    for key in ("mutation", "permission", "error_transition"):
        action.pop(key)
    contract["permissions"] = []
    contract["mutations"] = []
    contract["guards"] = contract["guards"][:1]
    contract["transitions"] = contract["transitions"][:1]
    return contract


def test_local_submit_preserves_guard_and_transition_obligations() -> None:
    contract = local_submit_contract()
    assert validate_flow_contract_v2(contract) == []
    assert action_mode(contract["actions"][0]) == "local_submit"
    duties = {(slot.category, slot.outcome) for slot in derive_obligations(contract)}
    assert {("action", "allowed"), ("validation", "allowed"), ("validation", "invalid")} <= duties
    assert any(category == "transition" for category, _ in duties)
    assert not {"permission", "effect", "result"} & {category for category, _ in duties}


def test_valid_local_submit_cannot_certify_missing_expected_outcomes() -> None:
    functional = [
        entry
        for entry in reconcile_expectations(local_submit_contract())
        if entry.slot.category != "structure"
    ]
    assert len(functional) == 4
    assert all(entry.issues and entry.expected is None for entry in functional)


def test_local_submit_exports_without_inventing_a_mutation() -> None:
    contract = local_submit_contract()
    assert semantic_tree_from_contract(contract)["screens"]
    projection = code_ir_from_pen(
        "ui.pen",
        contract=contract,
        pen_data={
            "children": [
                {"id": "checkout", "type": "frame", "width": 1440, "height": 900, "children": []}
            ]
        },
    )["contract"]
    assert projection["actions"][0]["event"] == "submit"
    assert (
        projection["actions"][0]["success_transition"]
        == contract["actions"][0]["success_transition"]
    )
    assert projection["mutations"] == []
    assert projection["permissions"] == []


@pytest.mark.parametrize(
    "field",
    ["permission", "mutation", "side_effects", "binding_ref", "destination", "error_transition"],
)
def test_local_submit_rejects_request_or_edit_fields(field: str) -> None:
    contract = local_submit_contract()
    contract["actions"][0][field] = {
        "side_effects": [],
        "binding_ref": {"entity": "checkout", "field": "title", "access": "write"},
        "destination": {"screen": "checkout", "state": "success"},
    }.get(field, "submit_payment")
    assert validate_flow_contract_v2(contract)


@pytest.mark.parametrize("field", ["guard", "success_transition"])
def test_local_submit_requires_guard_and_success_transition(field: str) -> None:
    contract = local_submit_contract()
    del contract["actions"][0][field]
    assert validate_flow_contract_v2(contract)


@pytest.mark.parametrize("change", ["input", "wrong_action", "unchanged_state"])
def test_local_submit_rejects_incoherent_owner_or_transition(change: str) -> None:
    contract = local_submit_contract()
    if change == "input":
        contract["nodes"][-1]["role"] = "input"
    elif change == "wrong_action":
        contract["transitions"][0]["action"] = "foreign_action"
    else:
        contract["transitions"][0]["to_state"] = "default"
    assert validate_flow_contract_v2(contract)


@pytest.mark.parametrize("missing", ["permission", "error_transition"])
def test_mutation_submit_keeps_request_requirements(missing: str) -> None:
    contract = valid_contract()
    action = contract["actions"][0]
    action.update(kind="state_change", event="submit")
    assert action_mode(action) == "request"
    assert validate_flow_contract_v2(contract) == []
    del action[missing]
    assert validate_flow_contract_v2(contract)
