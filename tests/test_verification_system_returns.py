"""System UI events remain observable without artificial business actions."""

from copy import deepcopy

import pytest

from penflow.verification_outcomes import evaluate_outcome
from tests.contract_factory import valid_contract


def _static_contract() -> dict:
    contract = valid_contract()
    contract["nodes"] = contract["nodes"][:2]
    contract["nodes"][0]["children"] = ["checkout.title"]
    for key in ("actions", "guards", "permissions", "mutations", "transitions"):
        contract[key] = []
    contract["screens"][0].update(static=True, static_reason="Read-only informational surface")
    contract["system_returns"] = [
        {
            "id": "leave",
            "screen_id": "checkout",
            "event": "close",
            "source": {
                "requirement_id": "livespec:001-static:FR-001",
                "source_pointer": "/body/0",
                "text_sha256": "c" * 64,
            },
            "destination": {"kind": "closed"},
        }
    ]
    return contract


def _observation() -> dict:
    facts = {
        "screen_id": "checkout",
        "state": "default",
        "semantic_id": "checkout",
        "role": "screen",
        "visible": True,
        "enabled": True,
        "text": None,
        "value": None,
        "bbox": {"x": 0, "y": 0, "width": 100, "height": 100},
        "properties": {},
        "navigation": {
            "context_id": "page-1",
            "event_id": "leave",
            "event": "close",
            "url": "http://localhost/info",
            "previous_url": None,
            "surface_present": True,
        },
    }
    after = deepcopy(facts)
    after["visible"] = False
    after.update(state=None, bbox=None, enabled=None)
    navigation = after["navigation"]
    assert isinstance(navigation, dict)
    navigation.update(url=None, surface_present=False)
    return {
        "kind": "penflow-outcome-observation",
        "version": 1,
        "contract_sha256": "a" * 64,
        "build_id": "test",
        "producer_invocation_id": "fixture",
        "scenario_id": "close",
        "session_id": "browser",
        "obligation_id": "system-return:leave",
        "screen_id": "checkout",
        "semantic_id": "checkout",
        "instance_key": None,
        "category": "transition",
        "capability": "ui",
        "before": facts,
        "after": after,
        "result": {"actor_id": "buyer", "action_id": "leave", "outcome": "success"},
        "evidence": {"path": "observed-contexts.json", "sha256": "b" * 64},
    }


def _expected() -> dict:
    return {
        "obligation_id": "system-return:leave",
        "source_pointer": "/system_returns/0",
        "category": "transition",
        "assertions": [
            {
                "operator": "equals",
                "pointer": "/after/visible",
                "expected": False,
                "capability": "ui",
            }
        ],
    }


def test_static_surface_system_close_needs_no_fake_action() -> None:
    assert not _static_contract()["actions"]
    assert evaluate_outcome(_expected(), _observation(), contract=_static_contract()) == []


@pytest.mark.parametrize("change", ["present", "visible", "event", "context", "no_facts"])
def test_system_close_requires_observed_disappearance(change: str) -> None:
    observation = _observation()
    if change == "present":
        observation["after"]["navigation"]["surface_present"] = True
    elif change == "visible":
        observation["after"]["visible"] = True
    elif change == "event":
        observation["after"]["navigation"]["event"] = "back"
    elif change == "context":
        observation["after"]["navigation"]["context_id"] = "foreign-page"
    else:
        observation["after"].pop("navigation")
    assert evaluate_outcome(_expected(), observation, contract=_static_contract())
