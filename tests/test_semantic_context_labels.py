"""A form control labelled by a sibling text node, as an HTML ``<label for>`` (C51).

The observed design: a select field whose visible label sits next to it, not inside it.
The select is the semantic anchor (it matches the runtime ``<select>``); the label is an
inherited ``label-for`` node of that select and gives its authored copy. Only a sibling
form control can be labelled this way; every other owner rule is unchanged.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from penflow.semantic_context_coverage import audit_semantic_context
from tests.test_semantic_context_coverage import _contract, _pen, _semantic

LABEL = "Payment method"


def _labelled(contract_text: str = LABEL) -> tuple[dict, dict]:
    contract = _contract()
    field = copy.deepcopy(
        next(n for n in contract["nodes"] if n["semantic_id"] == "checkout.title")
    )
    field.update(
        id="checkout.method",
        semantic_id="checkout.method",
        test_id="checkout-method",
        role="select",
        text=contract_text,
        action="choose_method",
    )
    contract["nodes"].append(field)
    pay_action = next(a for a in contract["actions"] if a["node"] == "checkout.pay")
    contract["actions"].append(
        {**pay_action, "id": "choose_method", "node": "checkout.method", "trigger": "change"}
    )
    root = next(n for n in contract["nodes"] if n["semantic_id"] == "checkout")
    root["children"] = [*root.get("children", []), "checkout.method"]
    pen = _pen()
    select = _semantic("method", "checkout.method", "checkout-method", "select")
    select["context"].update(
        binding="checkout.title",
        entity="checkout",
        intent="choose_method",
        permission="buyer_can_pay",
    )
    label = {
        "id": "method-label",
        "type": "text",
        "content": LABEL,
        "context": {
            "classification": "inherited",
            "inherits_from": "checkout.method",
            "relation": "label-for",
        },
    }
    group = {"id": "method-group", "type": "frame", "children": [label, select]}
    group["context"] = {  # type: ignore[assignment]
        "classification": "inherited",
        "inherits_from": "checkout",
        "relation": "field-group",
    }
    pen["children"][0]["children"].append(group)
    return contract, pen


def _codes(contract: dict, pen: dict) -> list[str]:
    report = audit_semantic_context(contract, pen, contract_path="c.json", pen_path="ui.pen")
    return sorted(
        finding["code"]
        for bucket in report["buckets"].values()
        for finding in bucket
        if finding.get("blocking")
    )


def _node(pen: dict, node_id: str) -> dict[str, Any]:
    group = pen["children"][0]["children"][-1]
    return next(child for child in group["children"] if child["id"] == node_id)


def test_a_sibling_label_gives_the_control_its_copy() -> None:
    contract, pen = _labelled()
    assert _codes(contract, pen) == []


def test_without_the_label_relation_the_copy_is_missing() -> None:
    contract, pen = _labelled()
    _node(pen, "method-label")["context"]["relation"] = "decoration"
    # A sibling cannot inherit through any other relation, and the copy is then absent.
    assert _codes(contract, pen) == ["pencil.copy_mismatch", "pencil.owner_not_ancestor"]


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ("wrong-text", "pencil.copy_mismatch"),
        ("not-a-control", "pencil.label_target_not_control"),
        ("empty-label", "pencil.label_without_copy"),
        ("two-labels", "pencil.label_duplicate"),
        ("unknown-owner", "pencil.owner_not_ancestor"),
    ],
)
def test_a_label_relation_never_relaxes_the_other_checks(change: str, code: str) -> None:
    contract, pen = _labelled("Other text" if change == "wrong-text" else LABEL)
    label, select = _node(pen, "method-label"), _node(pen, "method")
    if change == "not-a-control":
        select["context"]["role"] = "text"
        next(n for n in contract["nodes"] if n["id"] == "checkout.method")["role"] = "text"
    elif change == "empty-label":
        label["content"] = " "
    elif change == "two-labels":
        pen["children"][0]["children"][-1]["children"].append({**label, "id": "method-label-2"})
    elif change == "unknown-owner":
        label["context"]["inherits_from"] = "checkout.unknown"
    assert code in _codes(contract, pen)


def _tree_node(identifier: str, role: str, **extra: Any) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": identifier,
        "semantic_id": identifier,
        "role": role,
        "bbox": {"x": 0, "y": 0, "width": 100, "height": 40},
        "children": [],
    }
    node.update(extra)
    return node


def _trees(actual_label: str | None) -> tuple[dict, dict]:
    from penflow.tree import attach_labels

    label = {
        "id": "method-label",
        "pencil_id": "method-label",
        "role": "text",
        "text": LABEL,
        "bbox": {"x": 0, "y": 0, "width": 100, "height": 20},
        "context": {
            "classification": "inherited",
            "inherits_from": "f.method",
            "relation": "label-for",
        },
        "children": [],
    }
    root = _tree_node("f", "screen", children=[label, _tree_node("f.method", "select")])
    attach_labels(root)
    expected = {"version": 1, "screens": [{"screen_id": "f", "root": root}]}
    extra = {} if actual_label is None else {"label": actual_label}
    actual_root = _tree_node("f", "screen", children=[_tree_node("f.method", "select", **extra)])
    return expected, {"version": 1, "screens": [{"screen_id": "f", "root": actual_root}]}


@pytest.mark.parametrize(
    ("actual_label", "code"),
    [(LABEL, None), (None, "node.label.missing"), ("Other", "node.label")],
)
def test_the_runtime_must_associate_the_same_label(
    actual_label: str | None, code: str | None
) -> None:
    from penflow.compare import compare_trees

    expected, actual = _trees(actual_label)
    assert expected["screens"][0]["root"]["children"][1]["label"] == LABEL
    codes = [
        i["code"]
        for i in compare_trees(expected, actual)["issues"]
        if i["code"].startswith("node.label")
    ]
    assert codes == ([] if code is None else [code])
