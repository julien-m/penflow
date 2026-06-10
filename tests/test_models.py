"""Feature 054 — direct unit coverage for `penflow/models.py`.

Invariant protected: bbox coercion is deterministic and matches the 049
contract — `_number_or_zero` turns every string (including numeric strings)
and empty value into 0, and `pen.bbox.invalid` (feature 049, `bbox_issues`)
warns about exactly the non-empty, non-sizing-keyword string values that get
coerced. Coercion and warning may never drift apart silently.
"""

from __future__ import annotations

import pytest

from penflow.context import Context
from penflow.models import BBox, PenNode, _number_or_zero
from penflow.pen import bbox_issues


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 0),
        ("", 0),
        ("12", 0),  # numeric strings still coerce to 0 — surfaced by pen.bbox.invalid (049)
        ("12px", 0),
        ("fill_container", 0),
        (0, 0.0),
        (7, 7.0),
        (7.5, 7.5),
        (-3, -3.0),
        (True, 1.0),  # bool is an int subtype; float() applies
    ],
)
def test_number_or_zero_coercion_edge_cases(value: object, expected: float) -> None:
    assert _number_or_zero(value) == expected


def test_number_or_zero_returns_float_for_numbers() -> None:
    assert isinstance(_number_or_zero(7), float)
    assert isinstance(_number_or_zero(7.5), float)


def test_bbox_from_node_coerces_strings_to_zero() -> None:
    bbox = BBox.from_node({"x": "10", "y": None, "width": 390, "height": "fit_content"})
    assert bbox.to_dict() == {"x": 0, "y": 0, "width": 390.0, "height": 0}


def test_bbox_from_node_round_trips_numeric_values() -> None:
    data = {"x": 1, "y": 2.5, "width": 390, "height": 844}
    assert BBox.from_node(data).to_dict() == {"x": 1.0, "y": 2.5, "width": 390.0, "height": 844.0}


def test_bbox_defaults_to_zero_when_keys_absent() -> None:
    assert BBox.from_node({}).to_dict() == {"x": 0, "y": 0, "width": 0, "height": 0}


def test_string_bbox_values_coerced_by_models_are_warned_by_pen_bbox_invalid() -> None:
    """Cross-check the 049 surfacing contract against the coercion behavior.

    Every value that `_number_or_zero` silently coerces because it is a
    non-empty string (and not a Pencil sizing keyword) must produce one
    `pen.bbox.invalid` warning from `bbox_issues`.
    """
    pen = {
        "children": [
            {
                "id": "screen",
                "type": "frame",
                "x": "12px",  # coerced + warned
                "width": "fill_container",  # coerced but a sizing keyword: not warned
                "height": 844,  # numeric: neither coerced nor warned
                "children": [{"id": "title", "type": "text", "y": "ten"}],  # coerced + warned
            }
        ]
    }
    issues = bbox_issues(pen)
    assert [(issue.code, issue.node_id) for issue in issues] == [
        ("pen.bbox.invalid", "screen"),
        ("pen.bbox.invalid", "title"),
    ]
    assert all(issue.severity == "warning" for issue in issues)
    # The coercion side of the same contract:
    assert _number_or_zero("12px") == 0
    assert _number_or_zero("ten") == 0
    assert _number_or_zero("fill_container") == 0


def test_pen_node_semantic_id_and_role_come_from_context() -> None:
    node = PenNode(
        id="pay",
        type="frame",
        context=Context(semantic_id="checkout.pay", role="button", intent="submit_payment"),
    )
    assert node.semantic_id == "checkout.pay"
    assert node.role == "button"


def test_pen_node_role_falls_back_to_type_alias_without_context_role() -> None:
    assert PenNode(id="box", type="frame").role == "container"
    assert PenNode(id="label", type="text").role == "text"
    assert PenNode(id="custom", type="unknown_type").role == "unknown_type"


def test_pen_node_walk_returns_depth_first_order() -> None:
    leaf = PenNode(id="leaf", type="text")
    child = PenNode(id="child", type="frame", children=[leaf])
    root = PenNode(id="root", type="frame", children=[child, PenNode(id="sibling", type="text")])
    assert [node.id for node in root.walk()] == ["root", "child", "leaf", "sibling"]


def test_pen_node_to_expected_uses_semantic_id_and_recurses() -> None:
    child = PenNode(
        id="payLabel",
        type="text",
        content="Pay now",
        context=Context(semantic_id="checkout.pay.label", role="text"),
    )
    root = PenNode(
        id="payButton",
        type="frame",
        name="Pay now",
        context=Context(semantic_id="checkout.pay", role="button", intent="submit_payment"),
        bbox=BBox(x=0, y=0, width=320, height=48),
        visual={"fill": "#0057FF"},
        children=[child],
    )
    expected = root.to_expected()
    assert expected["id"] == "checkout.pay"
    assert expected["pencil_id"] == "payButton"
    assert expected["role"] == "button"
    assert expected["bbox"] == {"x": 0, "y": 0, "width": 320, "height": 48}
    assert expected["visual"] == {"fill": "#0057FF"}
    assert expected["context"]["intent"] == "submit_payment"
    assert [c["id"] for c in expected["children"]] == ["checkout.pay.label"]
    assert expected["children"][0]["text"] == "Pay now"


def test_pen_node_to_expected_falls_back_to_pencil_id_without_semantic_id() -> None:
    expected = PenNode(id="anon", type="text").to_expected()
    assert expected["id"] == "anon"
    assert expected["semantic_id"] is None
