# @spec FR-006 AC-009 AC-010 SC-002: Runtime projection preserves semantic observations and removes only inert wrappers.
"""Adversarial runtime wrappers cannot hide behavior before C51 comparison."""

from copy import deepcopy
from typing import Any

import pytest

from penflow.tree import validate_actual_tree
from penflow.verification_comparison import compare_required_trees


def _node(identifier: str, role: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "role": role,
        "bbox": {"x": 0, "y": 0, "width": 100, "height": 40},
        "children": [],
    }


def _case(role: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    button = _node("pay", "button")
    button.update(semantic_id="pay", text="Pay")
    root = _node("screen", "screen")
    root.update(semantic_id="screen", children=[button])
    expected: dict[str, Any] = {"version": 1, "screens": [{"screen_id": "screen", "root": root}]}
    actual = deepcopy(expected)
    wrapper = _node("runtime-wrapper", role)
    if role == "text":
        wrapper.update(
            text="Pay",
            context={"classification": "inherited", "inherits_from": "pay", "relation": "content"},
        )
        actual["screens"][0]["root"]["children"][0]["children"] = [wrapper]
    else:
        wrapper["children"] = actual["screens"][0]["root"]["children"]
        actual["screens"][0]["root"]["children"] = [wrapper]
    contract = {"nodes": [{"semantic_id": "screen"}, {"semantic_id": "pay", "text": "Pay"}]}
    return contract, expected, actual, wrapper


def _findings(case: tuple[dict[str, Any], ...]) -> list[dict[str, Any]]:
    contract, expected, actual, _ = case
    before = deepcopy((contract, expected, actual))
    assert validate_actual_tree(actual, schema=True) == []
    findings = compare_required_trees(contract, expected, actual)
    assert (contract, expected, actual) == before
    return findings


@pytest.mark.parametrize("role", ["group", "container", "text"])
def test_inert_wrapper_or_exact_inherited_label_preserves_required_descendants(role: str) -> None:
    assert _findings(_case(role)) == []


@pytest.mark.parametrize("role", ["group", "container"])
@pytest.mark.parametrize("classification", ["decorative", "inherited"])
def test_consistent_owned_layout_metadata_remains_inert(role: str, classification: str) -> None:
    case = _case(role)
    context = {"classification": classification, "role": role}
    if classification == "decorative":
        context.update(decorative_owner="screen", decorative_reason="layout grouping")
    else:
        context.update(inherits_from="screen", relation="layout")
    case[3].update(semantic_id="runtime-wrapper", context=context)
    assert _findings(case) == []


@pytest.mark.parametrize("role", ["group", "container", "text"])
@pytest.mark.parametrize(
    "patch",
    [
        {"inherits_from": "foreign"},
        {"inherits_from": None},
        {"relation": ""},
        {"relation": False},
        {"decorative_owner": None},
        {"decorative_reason": ""},
    ],
)
def test_incomplete_or_conflicting_owned_metadata_cannot_hide_a_node(
    role: str, patch: dict[str, Any]
) -> None:
    case = _case(role)
    owner = "pay" if role == "text" else "screen"
    case[3]["context"] = {
        "classification": "inherited",
        "inherits_from": owner,
        "relation": "content",
    }
    case[3]["context"].update(patch)
    assert any(item["code"] == "node.unexpected" for item in _findings(case))


@pytest.mark.parametrize("role", ["group", "container", "text"])
@pytest.mark.parametrize(
    "slot", ["intent", "binding", "repeat", "entity", "test_id", "permission", "action"]
)
@pytest.mark.parametrize("value", ["declared", None, "", False, 0, {}, []])
def test_explicit_behavior_slots_are_never_erased_even_when_empty(
    role: str, slot: str, value: Any
) -> None:
    case = _case(role)
    case[3].setdefault("context", {})[slot] = value
    assert any(item["code"] == "node.unexpected" for item in _findings(case))


@pytest.mark.parametrize("role", ["group", "container", "text"])
@pytest.mark.parametrize("classification", ["semantic", None, "", False, "unknown"])
def test_ambiguous_or_semantic_classification_prevents_wrapper_removal(
    role: str, classification: Any
) -> None:
    case = _case(role)
    case[3].setdefault("context", {})["classification"] = classification
    assert any(item["code"] == "node.unexpected" for item in _findings(case))


@pytest.mark.parametrize("role", ["group", "container", "text"])
@pytest.mark.parametrize("field", ["semantic_id", "role", "instance_key", "unrecognized_behavior"])
def test_conflicting_or_unknown_context_is_not_assumed_inert(role: str, field: str) -> None:
    case = _case(role)
    case[3].setdefault("context", {})[field] = "independent"
    assert any(item["code"] == "node.unexpected" for item in _findings(case))


@pytest.mark.parametrize("role", ["group", "container", "text"])
def test_decorative_classification_cannot_hide_independent_intent(role: str) -> None:
    case = _case(role)
    case[3].update(semantic_id="rogue")
    case[3].setdefault("context", {}).update(classification="decorative", intent="activate")
    assert any(item["code"] == "node.unexpected" for item in _findings(case))


@pytest.mark.parametrize("role", ["group", "container"])
def test_empty_string_semantic_identity_is_not_proof_of_inertness(role: str) -> None:
    case = _case(role)
    case[3]["semantic_id"] = ""
    assert any(item["code"] == "node.unexpected" for item in _findings(case))


@pytest.mark.parametrize("role", ["group", "container"])
@pytest.mark.parametrize("null_identity", [False, True])
def test_minimal_decorative_layout_needs_no_new_owner_metadata(
    role: str, null_identity: bool
) -> None:
    case = _case(role)
    case[3]["context"] = {"classification": "decorative"}
    if null_identity:
        case[3]["semantic_id"] = None
    assert _findings(case) == []


@pytest.mark.parametrize("role", ["group", "container"])
def test_inert_wrapper_projection_keeps_child_geometry_and_extra_controls(role: str) -> None:
    case = _case(role)
    case[3]["children"][0]["bbox"]["width"] = 200
    case[3]["children"].append(_node("extra-control", "button"))
    codes = {item["code"] for item in _findings(case)}
    assert {"node.bbox.width", "node.unexpected"} <= codes
