"""A native Pencil image paint in `visual.fill` (expected tree export and its consumers).

The payload is the exact fill Penflow 3268d1ae refused when exporting the ProjectAtlas
expected tree (`$.screens[3].root.children[0].visual.fill ... is not of type 'string'`):
a frame explicitly classified decorative that shows a legacy reference bitmap.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from penflow.compare import compare_trees
from penflow.consistency import check_consistency
from penflow.pen import parse_pen
from penflow.schema_cache import load_schema
from penflow.semantic_context_coverage import audit_semantic_context
from penflow.tree import _screen_to_expected, validate_actual_tree
from tests.test_semantic_context_coverage import _contract, _pen

IMAGE_FILL: dict[str, Any] = {
    "type": "image",
    "enabled": True,
    "url": "references/reference-existing-projects.png",
    "mode": "contain",
}
MALFORMED_FILLS: list[object] = [
    "",
    {"enabled": True, "url": "references/a.png", "mode": "contain"},
    {**IMAGE_FILL, "type": "gradient"},
    {**IMAGE_FILL, "url": ""},
    {key: value for key, value in IMAGE_FILL.items() if key != "url"},
    {**IMAGE_FILL, "enabled": "yes"},
    {**IMAGE_FILL, "mode": ""},
    {**IMAGE_FILL, "unexpected": 1},
    [IMAGE_FILL],
    7,
]


def _pen_with_reference_image(fill: object = IMAGE_FILL) -> dict[str, Any]:
    """The coverage fixture plus a decorative frame painted with a reference image."""
    pen = _pen()
    pen["children"][0]["children"].append(
        {
            "id": "legacy-reference",
            "type": "frame",
            "name": "Existing Projects reference",
            "layout": "vertical",
            "fill": fill,
            "context": {
                "classification": "decorative",
                "decorative_owner": "checkout",
                "decorative_reason": "legacy view reference outside the contract",
                "variant": "legacy-reference",
            },
        }
    )
    return pen


def _expected(pen: dict[str, Any]) -> dict[str, Any]:
    """Export an expected tree with the production export function of `export-expected`."""
    return {
        "version": 1,
        "source": "ui.pen",
        "screens": [_screen_to_expected(root) for root in parse_pen(pen)],
        "issues": [],
    }


def _reference(tree: dict[str, Any]) -> dict[str, Any]:
    nodes = [tree["screens"][0]["root"]]
    while nodes:
        node = nodes.pop()
        if node.get("pencil_id") == "legacy-reference":
            return node
        nodes.extend(node.get("children", []))
    raise AssertionError("reference node not exported")


def test_export_keeps_the_native_image_paint_and_the_tree_validates() -> None:
    expected = _expected(_pen_with_reference_image())
    assert _reference(expected)["visual"]["fill"] == IMAGE_FILL
    assert validate_actual_tree(expected) == []


def test_reference_image_stays_a_decorative_node_without_new_obligation() -> None:
    report = _audit(_pen_with_reference_image())
    blocking = [
        item for bucket in report["buckets"].values() for item in bucket if item["blocking"]
    ]
    assert blocking == []
    assert report["summary"]["decorative"] == _count_decorative(_pen()) + 1


def _audit(pen: dict[str, Any]) -> dict[str, Any]:
    return audit_semantic_context(
        _contract(), pen, contract_path="flow-ui-contract/contract.json", pen_path="ui.pen"
    )


def _count_decorative(pen: dict[str, Any]) -> int:
    return int(_audit(pen)["summary"]["decorative"])


def test_color_fills_are_unchanged() -> None:
    expected = _expected(_pen_with_reference_image("#0057FF"))
    assert _reference(expected)["visual"]["fill"] == "#0057FF"
    assert validate_actual_tree(expected) == []


@pytest.mark.parametrize("fill", MALFORMED_FILLS)
def test_malformed_fills_are_refused(fill: object) -> None:
    expected = _expected(_pen_with_reference_image())
    _reference(expected)["visual"]["fill"] = copy.deepcopy(fill)
    assert validate_actual_tree(expected) != []


def test_comparison_still_reports_a_different_image() -> None:
    expected = _expected(_pen_with_reference_image())
    pay = expected["screens"][0]["root"]["children"][1]
    pay["visual"]["fill"] = IMAGE_FILL
    actual = copy.deepcopy(expected)
    actual["screens"][0]["root"]["children"][1]["visual"]["fill"] = {
        **IMAGE_FILL,
        "url": "references/another-image.png",
    }
    report = compare_trees(expected, actual)
    assert "node.visual.fill" in {issue["code"] for issue in report["issues"]}
    same = compare_trees(expected, copy.deepcopy(expected))
    assert "node.visual.fill" not in {issue["code"] for issue in same["issues"]}


def test_consistency_report_with_divergent_images_matches_its_schema(tmp_path: Path) -> None:
    expected = _expected(_pen_with_reference_image())
    second = copy.deepcopy(expected["screens"][0])
    second["screen_id"] = "checkout-copy"
    _reference({"screens": [second]})["visual"]["fill"] = {**IMAGE_FILL, "mode": "cover"}
    expected["screens"].append(second)
    path = tmp_path / "expected-ui-tree.json"
    path.write_text(json.dumps(expected), encoding="utf-8")
    report = check_consistency(path)
    fills = [issue for issue in report["issues"] if issue["property"] == "fill"]
    assert fills and all(issue["severity"] == "error" for issue in fills)
    jsonschema.Draft202012Validator(load_schema("consistency-report.schema.json")).validate(report)
