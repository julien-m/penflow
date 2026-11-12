"""Content-sized members do not compare heights (C51, outcome F3).

The expected export carries the design source's own sizing of each node; the
consistency check compares ``bbox.height`` only between members whose height is fixed
in that source. Trees without sizing keep the strict comparison. Synthetic data only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from penflow.consistency import check_consistency
from penflow.tree import expected_tree_from_pen, validate_actual_tree


def _card(identifier: str, height: float, sizing: str | None) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": identifier,
        "semantic_id": identifier,
        "role": "container",
        "bbox": {"x": 0, "y": 0, "width": 320, "height": height},
        "context": {"variant": "state-card"},
        "children": [],
    }
    if sizing is not None:
        node["sizing"] = {"width": "fill", "height": sizing}
    return node


def _tree(*cards: dict[str, Any]) -> dict[str, Any]:
    screens = []
    for index, card in enumerate(cards):
        root = {
            "id": f"s{index}",
            "semantic_id": f"s{index}",
            "role": "screen",
            "bbox": {"x": 0, "y": 0, "width": 400, "height": 800},
            "children": [card],
        }
        screens.append({"screen_id": f"s{index}", "root": root})
    return {"version": 1, "screens": screens}


def _height_errors(tree: dict[str, Any]) -> list[dict[str, Any]]:
    report = check_consistency(
        "tree.json", tree_data=tree, lenient=False, shared_identity_only=True
    )
    return [i for i in report["issues"] if i["property"] == "bbox.height"]


def test_content_sized_heights_are_not_compared() -> None:
    tree = _tree(
        _card("loading", 112, "hug"), _card("error", 146, "hug"), _card("empty", 120, "unspecified")
    )
    assert validate_actual_tree(tree) == []
    assert _height_errors(tree) == []


def test_a_divergent_fixed_height_stays_an_error() -> None:
    tree = _tree(_card("a", 40, "fixed"), _card("b", 40, "fixed"), _card("c", 56, "fixed"))
    errors = _height_errors(tree)
    assert [e["semantic_id"] for e in errors] == ["c"] and errors[0]["severity"] == "error"


def test_a_content_sized_member_does_not_hide_a_fixed_divergence() -> None:
    tree = _tree(_card("a", 40, "fixed"), _card("b", 56, "fixed"), _card("c", 90, "hug"))
    assert [e["semantic_id"] for e in _height_errors(tree)] != []


def test_trees_without_sizing_stay_strict() -> None:
    tree = _tree(_card("loading", 112, None), _card("error", 146, None))
    assert _height_errors(tree) != []


@pytest.mark.parametrize("sizing", [{"height": "auto"}, "hug", {"width": "fill", "height": 3}])
def test_malformed_sizing_is_refused(sizing: Any) -> None:
    card = _card("a", 40, None)
    card["sizing"] = sizing
    tree = _tree(card, _card("b", 40, "fixed"))
    assert validate_actual_tree(tree) != []
    with pytest.raises(ValueError, match="sizing"):
        check_consistency("tree.json", tree_data=tree, shared_identity_only=True)


def test_the_expected_export_carries_the_design_sizing(tmp_path: Path) -> None:
    pen = {
        "version": "2.10",
        "children": [
            {
                "id": "board",
                "type": "frame",
                "width": 400,
                "height": 800,
                "context": {"classification": "semantic", "role": "screen", "semantic_id": "board"},
                "children": [
                    {"id": "fixed", "type": "frame", "width": 320, "height": 40},
                    {
                        "id": "hug",
                        "type": "frame",
                        "width": "fill_container",
                        "height": "fit_content",
                    },
                    {"id": "hug-min", "type": "frame", "width": 320, "height": "fit_content(48)"},
                    {"id": "absent", "type": "frame", "width": 320},
                ],
            }
        ],
    }
    source = tmp_path / "board.pen"
    source.write_text(json.dumps(pen), encoding="utf-8")
    tree = expected_tree_from_pen(source)
    children = {c["id"]: c["sizing"] for c in tree["screens"][0]["root"]["children"]}
    assert children == {
        "fixed": {"width": "fixed", "height": "fixed"},
        "hug": {"width": "fill", "height": "hug"},
        "hug-min": {"width": "fixed", "height": "hug"},
        "absent": {"width": "fixed", "height": "unspecified"},
    }
