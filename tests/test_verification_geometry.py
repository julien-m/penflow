# @spec AC-010: Given explicitly declared dynamic predicates/inert wrappers, when equivalent observations are normalized, then they pass; an unsupported required adapter capability remains blocking. — .specs/features/077-complete-verification-workflow/spec.md#ac-010
"""Native parent-relative geometry becomes absolute within each logical screen."""

from copy import deepcopy

import pytest

from penflow.verification_geometry import normalize_native_geometry
from penflow.verification_files import VerificationInputError
from penflow.verification_comparison import compare_required_trees


def _node(identifier, role, x, y, width, height, children=None):
    return {
        "id": identifier,
        "pencil_id": identifier,
        "semantic_id": identifier,
        "role": role,
        "bbox": {"x": x, "y": y, "width": width, "height": height},
        "children": children or [],
    }


def _trees():
    button = _node("button", "button", 8, 8, 0, 0)
    wrapper = _node("wrapper", "container", 40, 40, 300, 100, [button])
    root = _node("screen", "screen", 1520, 0, 400, 300, [wrapper])
    expected = {"version": 1, "screens": [{"screen_id": "screen", "root": root}]}
    snapshot = [
        {
            "id": "screen",
            "x": 1520,
            "y": 0,
            "width": 400,
            "height": 300,
            "children": [
                {
                    "id": "wrapper",
                    "x": 40,
                    "y": 40,
                    "width": 300,
                    "height": 100,
                    "children": [{"id": "button", "x": 8, "y": 8, "width": 80, "height": 48}],
                }
            ],
        }
    ]
    actual = {
        "version": 1,
        "screens": [
            {
                "screen_id": "screen",
                "root": _node(
                    "screen", "screen", 0, 0, 400, 300, [_node("button", "button", 48, 48, 80, 48)]
                ),
            }
        ],
    }
    contract = {"nodes": [{"semantic_id": "screen"}, {"semantic_id": "button"}]}
    return contract, expected, snapshot, actual


def test_native_offsets_and_fill_container_are_measured_before_wrapper_projection():
    contract, expected, snapshot, actual = _trees()
    normalize_native_geometry(expected, snapshot)
    assert compare_required_trees(contract, expected, actual) == []


@pytest.mark.parametrize("property", ["x", "y", "width", "height"])
def test_actual_geometry_changes_remain_required(property):
    contract, expected, snapshot, actual = _trees()
    normalize_native_geometry(expected, snapshot)
    actual["screens"][0]["root"]["children"][0]["bbox"][property] += 100
    assert any(
        item["code"] == f"node.bbox.{property}"
        for item in compare_required_trees(contract, expected, actual)
    )


@pytest.mark.parametrize("change", ["missing", "duplicate", "parent", "nonfinite"])
def test_native_geometry_must_cover_exact_unique_pencil_relationships(change):
    _, expected, snapshot, _ = _trees()
    children = snapshot[0]["children"]
    if change == "missing":
        children[0]["children"] = []
    elif change == "duplicate":
        children.append(deepcopy(children[0]))
    elif change == "parent":
        children.extend(children[0].pop("children"))
    else:
        children[0]["width"] = float("nan")
    with pytest.raises(VerificationInputError):
        normalize_native_geometry(expected, snapshot)


def test_mandatory_comparison_does_not_skip_observed_zero_geometry():
    contract, expected, snapshot, actual = _trees()
    snapshot[0]["children"][0]["children"][0].update(width=0, height=0)
    normalize_native_geometry(expected, snapshot)
    assert compare_required_trees(contract, expected, actual)


def test_unrepresentable_geometry_is_a_structured_input_error():
    _, expected, snapshot, _ = _trees()
    snapshot[0]["width"] = 10**400
    with pytest.raises(VerificationInputError):
        normalize_native_geometry(expected, snapshot)


@pytest.mark.parametrize(
    "role", ["checkbox", "radio", "slider", "switch", "future-interactive-role"]
)
def test_unknown_or_extra_runtime_controls_are_never_removed_as_layout(role):
    contract, expected, snapshot, actual = _trees()
    normalize_native_geometry(expected, snapshot)
    actual["screens"][0]["root"]["children"].append(_node("extra", role, 0, 0, 48, 48))
    assert any(
        item["code"] == "node.unexpected"
        for item in compare_required_trees(contract, expected, actual)
    )


@pytest.mark.parametrize("linked", [True, False])
def test_only_exact_canonical_inherited_label_can_be_removed(linked):
    contract, expected, snapshot, actual = _trees()
    contract["nodes"][1]["text"] = "Pay"
    expected["screens"][0]["root"]["children"][0]["children"][0]["text"] = "Pay"
    button = actual["screens"][0]["root"]["children"][0]
    button["text"] = "Pay"
    label = _node("label", "text", 48, 48, 30, 22)
    label.update(
        text="Pay",
        context={
            "classification": "inherited",
            "relation": "content",
            "inherits_from": "button" if linked else "foreign",
        },
    )
    button["children"].append(label)
    normalize_native_geometry(expected, snapshot)
    assert bool(compare_required_trees(contract, expected, actual)) == (not linked)


@pytest.mark.parametrize(
    "context", [{"mask_text": True}, {"variant": "dynamic"}, {"variant": "volatile"}]
)
def test_mandatory_copy_cannot_be_masked_by_expected_context(context):
    contract, expected, snapshot, actual = _trees()
    contract["nodes"][1]["text"] = "Pay"
    button = expected["screens"][0]["root"]["children"][0]["children"][0]
    button.update(text="Pay", context=context)
    actual["screens"][0]["root"]["children"][0]["text"] = "Cancel"
    normalize_native_geometry(expected, snapshot)
    assert any(
        item["code"] == "node.text" for item in compare_required_trees(contract, expected, actual)
    )


def test_dynamic_observation_without_a_declared_literal_preserves_predicate_evaluation():
    from penflow.verification_assertions import evaluate_assertion

    contract, expected, snapshot, actual = _trees()
    button = expected["screens"][0]["root"]["children"][0]["children"][0]
    button.update(text=None, context={"variant": "dynamic"})
    observed = actual["screens"][0]["root"]["children"][0]
    observed["text"] = "Payment 123"
    normalize_native_geometry(expected, snapshot)
    assert compare_required_trees(contract, expected, actual) == []
    predicate = {
        "operator": "equals",
        "pointer": "/after/text",
        "expected": "Payment 123",
        "capability": "ui",
    }
    assert evaluate_assertion(predicate, {"after": observed, "capability": "ui"})
    observed["text"] = "Payment 456"
    assert not evaluate_assertion(predicate, {"after": observed, "capability": "ui"})
