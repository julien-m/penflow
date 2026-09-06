# @spec AC-013: Given action, validation, permission, transition, side-effect, persistence and result obligations, when required typed observations are incomplete, then implementation fails; legitimate denied/error/idempotent unchanged-state results can pass. — .specs/features/077-complete-verification-workflow/spec.md#ac-013
"""Real predicate evaluation over synthetic typed facts, distinct from runtime proof."""

from copy import deepcopy

import pytest

from penflow.verification_expectations import reconcile_expectations
from penflow.verification_outcomes import evaluate_outcome
from tests.c51_factory import outcome_contract, persistence_expectation, persistence_observation


def test_complete_expected_contract_covers_every_derived_slot() -> None:
    obligations = reconcile_expectations(outcome_contract())
    assert obligations
    assert not [issue for item in obligations for issue in item.issues]


def test_transition_cannot_omit_source_starting_state() -> None:
    contract = outcome_contract()
    expected = next(
        item for item in contract["outcome_expectations"] if item["category"] == "transition"
    )
    expected["assertions"] = [
        item for item in expected["assertions"] if item["pointer"] != "/before/state"
    ]
    assert any(
        item.issues
        for item in reconcile_expectations(contract)
        if item.slot.id == expected["obligation_id"]
    )


def test_approved_persistence_cannot_be_removed_from_current_contract() -> None:
    contract = outcome_contract()
    contract["outcome_expectations"] = [
        item for item in contract["outcome_expectations"] if item["category"] != "persistence"
    ]
    slots = reconcile_expectations(contract, approved_expectations=(persistence_expectation(),))
    assert any(
        slot.slot.category == "persistence" and slot.expected is None and slot.issues
        for slot in slots
    )


def test_typed_persistence_requires_intended_value_and_restart_readback() -> None:
    assert (
        evaluate_outcome(
            persistence_expectation(), persistence_observation(), contract=outcome_contract()
        )
        == []
    )


@pytest.mark.parametrize(
    "change", ["value", "restart", "readback", "actor", "action", "success_boolean"]
)
def test_synthetic_success_claims_cannot_replace_expected_facts(change: str) -> None:
    observed = deepcopy(persistence_observation())
    if change == "value":
        observed["after"]["value"] = {"status": "unpaid"}
    elif change == "restart":
        observed["result"]["restart"]["after_process"] = "101"
    elif change == "readback":
        observed["result"]["readback"]["key"] = "another-record"
    elif change in {"actor", "action"}:
        observed["result"][change + "_id"] = "foreign"
    else:
        observed["result"] = {"passed": True}
    assert evaluate_outcome(persistence_expectation(), observed, contract=outcome_contract())
