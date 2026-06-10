# @spec(AC-001)
# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
from __future__ import annotations

import json
from pathlib import Path

from penflow.compare import compare_trees
from penflow.contracts import (
    code_ir_from_contract,
    extract_design_tokens,
    pencil_draft_from_screen,
    screen_contracts_from_flow,
    validate_flow_contract,
)
from penflow.pen import inspect_pen, parse_pen, update_pen_by_semantic_id, validate_pen_context
from penflow.tree import expected_tree_from_pen, validate_actual_tree


def write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def sample_pen() -> dict:
    return {
        "version": 1,
        "children": [
            {
                "id": "screen",
                "type": "frame",
                "name": "Checkout",
                "width": 390,
                "height": 844,
                "layout": "vertical",
                "gap": 16,
                "alignItems": "stretch",
                "context": {"semantic_id": "checkout", "role": "screen"},
                "children": [
                    {
                        "id": "title",
                        "type": "text",
                        "content": "Checkout",
                        "fontSize": 24,
                        "context": {"semantic_id": "checkout.title", "role": "text"},
                    },
                    {
                        "id": "pay",
                        "type": "frame",
                        "width": 320,
                        "height": 48,
                        "cornerRadius": 8,
                        "fill": "#0057ff",
                        "context": {
                            "semantic_id": "checkout.pay",
                            "role": "button",
                            "intent": "submit_payment",
                            "tolerance": {"bbox_px": 8},
                        },
                    },
                ],
            }
        ],
    }


def test_parse_validate_inspect_and_expected_tree(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", sample_pen())
    roots = parse_pen(pen_path)
    assert roots[0].semantic_id == "checkout"
    assert validate_pen_context(roots) == []

    inspected = inspect_pen(pen_path)
    assert inspected["node_count"] == 3
    assert inspected["buttons"] == ["checkout.pay"]

    expected = expected_tree_from_pen(pen_path)
    assert expected["screens"][0]["screen_id"] == "checkout"
    assert expected["screens"][0]["root"]["children"][1]["visual"]["cornerRadius"] == 8
    # @spec FR-001: alignItems reaches expected trees — .specs/features/048-compare-layout-spacing-properties/spec.md#fr-001
    assert expected["screens"][0]["root"]["visual"]["alignItems"] == "stretch"


def test_invalid_context_reports_errors(tmp_path: Path) -> None:
    data = sample_pen()
    data["children"][0]["children"][1]["context"].pop("intent")
    data["children"][0]["children"][1]["context"]["binding"] = "bad"
    pen_path = write_json(tmp_path / "bad.pen", data)
    issues = validate_pen_context(parse_pen(pen_path))
    assert {issue.code for issue in issues} == {
        "context.button_intent_missing",
        "context.binding_format",
    }


def test_validate_actual_and_compare_pass(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", sample_pen())
    expected = expected_tree_from_pen(pen_path)
    actual = {
        "version": 1,
        "screen_id": "checkout",
        "viewport": {"width": 390, "height": 844},
        "root": expected["screens"][0]["root"],
    }
    assert validate_actual_tree(actual) == []
    report = compare_trees(expected, {"version": 1, "screens": [actual]})
    assert report["status"] == "PASS"
    assert report["score"] == 1.0


def test_compare_reports_missing_node(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", sample_pen())
    expected = expected_tree_from_pen(pen_path)
    actual = {
        "version": 1,
        "screen_id": "checkout",
        "viewport": {"width": 390, "height": 844},
        "root": {
            **expected["screens"][0]["root"],
            "children": expected["screens"][0]["root"]["children"][:1],
        },
    }
    report = compare_trees(expected, {"version": 1, "screens": [actual]})
    assert report["status"] == "FAIL"
    assert any(issue["code"] == "node.missing" for issue in report["issues"])


def test_compare_honors_bbox_tolerance(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", sample_pen())
    expected = expected_tree_from_pen(pen_path)
    root = expected["screens"][0]["root"]

    tolerated_actual = {
        "version": 1,
        "screen_id": "checkout",
        "viewport": {"width": 390, "height": 844},
        "root": {
            **root,
            "children": [
                root["children"][0],
                {**root["children"][1], "bbox": {**root["children"][1]["bbox"], "x": 7}},
            ],
        },
    }
    report = compare_trees(expected, {"version": 1, "screens": [tolerated_actual]})
    assert report["status"] == "PASS"
    assert not any(issue["code"] == "node.bbox.x" for issue in report["issues"])

    drifted_actual = {
        **tolerated_actual,
        "root": {
            **root,
            "children": [
                root["children"][0],
                {**root["children"][1], "bbox": {**root["children"][1]["bbox"], "x": 9}},
            ],
        },
    }
    report = compare_trees(expected, {"version": 1, "screens": [drifted_actual]})
    assert any(issue["code"] == "node.bbox.x" for issue in report["issues"])


def test_compare_ignores_unmeasurable_expected_bbox(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", sample_pen())
    expected = expected_tree_from_pen(pen_path)
    root = expected["screens"][0]["root"]
    expected["screens"][0]["root"] = {
        **root,
        "children": [
            {
                **root["children"][0],
                "bbox": {"x": 0, "y": 0, "width": 0, "height": 0},
            },
            root["children"][1],
        ],
    }
    actual = {
        "version": 1,
        "screen_id": "checkout",
        "viewport": {"width": 390, "height": 844},
        "root": {
            **expected["screens"][0]["root"],
            "children": [
                {
                    **expected["screens"][0]["root"]["children"][0],
                    "bbox": {"x": 40, "y": 72, "width": 260, "height": 32},
                },
                expected["screens"][0]["root"]["children"][1],
            ],
        },
    }

    report = compare_trees(expected, {"version": 1, "screens": [actual]})

    assert report["status"] == "PASS"
    assert not any(issue["code"].startswith("node.bbox") for issue in report["issues"])


def test_compare_masks_volatile_nodes_and_dynamic_text(tmp_path: Path) -> None:
    data = sample_pen()
    data["children"][0]["children"].extend(
        [
            {
                "id": "timer",
                "type": "text",
                "content": "12:00",
                "context": {"semantic_id": "checkout.timer", "role": "timer"},
            },
            {
                "id": "live-total",
                "type": "text",
                "content": "$12.00",
                "context": {
                    "semantic_id": "checkout.total",
                    "role": "text",
                    "variant": "dynamic",
                },
            },
            {
                "id": "masked-total",
                "type": "text",
                "content": "$12.00",
                "context": {
                    "semantic_id": "checkout.masked_total",
                    "role": "text",
                    "mask_text": True,
                },
            },
            {
                "id": "volatile-banner",
                "type": "text",
                "content": "Limited offer",
                "context": {
                    "semantic_id": "checkout.offer",
                    "role": "text",
                    "variant": "volatile",
                },
            },
        ]
    )
    pen_path = write_json(tmp_path / "ui.pen", data)
    expected = expected_tree_from_pen(pen_path)
    root = expected["screens"][0]["root"]
    children = root["children"]
    actual_root = {
        **root,
        "children": [
            children[0],
            children[1],
            {**children[2], "text": "12:01"},
            {**children[3], "text": "$13.00"},
            {**children[4], "text": "$14.00"},
        ],
    }

    report = compare_trees(
        expected,
        {
            "version": 1,
            "screens": [
                {
                    "screen_id": "checkout",
                    "viewport": {"width": 390, "height": 844},
                    "root": actual_root,
                }
            ],
        },
    )

    assert report["status"] == "PASS"
    assert not any(issue["semantic_id"] == "checkout.timer" for issue in report["issues"])
    assert not any(issue["semantic_id"] == "checkout.total" for issue in report["issues"])
    assert not any(issue["semantic_id"] == "checkout.masked_total" for issue in report["issues"])
    assert not any(issue["semantic_id"] == "checkout.offer" for issue in report["issues"])


# @spec FR-002, FR-003: layout/spacing comparison — .specs/features/048-compare-layout-spacing-properties/spec.md#fr-002
def _spacing_screen(visual: dict, context: dict | None = None) -> dict:
    node: dict = {
        "id": "checkout.box",
        "semantic_id": "checkout.box",
        "role": "container",
        "bbox": {"x": 0, "y": 0, "width": 320, "height": 120},
        "visual": dict(visual),
    }
    if context is not None:
        node["context"] = context
    return {
        "screen_id": "checkout",
        "viewport": {"width": 390, "height": 844},
        "root": {
            "id": "checkout",
            "semantic_id": "checkout",
            "role": "screen",
            "bbox": {"x": 0, "y": 0, "width": 390, "height": 844},
            "children": [node],
        },
    }


def _compare_visuals(
    expected_visual: dict, actual_visual: dict, *, context: dict | None = None
) -> dict:
    expected = {"version": 1, "screens": [_spacing_screen(expected_visual, context)]}
    actual = {"version": 1, "screens": [_spacing_screen(actual_visual)]}
    return compare_trees(expected, actual)


def _issue_codes(report: dict) -> set[str]:
    return {issue["code"] for issue in report["issues"]}


def test_compare_layout_and_align_items_exact_match() -> None:
    report = _compare_visuals(
        {"layout": "vertical", "alignItems": "stretch"},
        {"layout": "horizontal", "alignItems": "center"},
    )
    assert {"node.visual.layout", "node.visual.alignItems"} <= _issue_codes(report)
    for issue in report["issues"]:
        assert issue["severity"] == "warning"

    matching = _compare_visuals(
        {"layout": "vertical", "alignItems": "stretch"},
        {"layout": "vertical", "alignItems": "stretch"},
    )
    assert matching["issues"] == []


def test_compare_gap_honors_spacing_tolerance() -> None:
    within = _compare_visuals({"gap": 16}, {"gap": 18})
    assert "node.visual.gap" not in _issue_codes(within)

    beyond = _compare_visuals({"gap": 16}, {"gap": 19})
    assert "node.visual.gap" in _issue_codes(beyond)
    gap_issue = next(i for i in beyond["issues"] if i["code"] == "node.visual.gap")
    assert gap_issue["severity"] == "warning"
    assert gap_issue["semantic_id"] == "checkout.box"


def test_compare_padding_scalar_and_list_forms_are_equivalent() -> None:
    assert _compare_visuals({"padding": 16}, {"padding": [16, 16, 16, 16]})["issues"] == []
    assert _compare_visuals({"padding": [12, 16]}, {"padding": [12, 16, 12, 16]})["issues"] == []
    assert _compare_visuals({"padding": [16]}, {"padding": 16})["issues"] == []


def test_compare_padding_element_wise_deviation_beyond_tolerance() -> None:
    report = _compare_visuals({"padding": 16}, {"padding": [16, 16, 20, 16]})
    assert "node.visual.padding" in _issue_codes(report)

    within = _compare_visuals({"padding": 16}, {"padding": [16, 16, 18, 16]})
    assert "node.visual.padding" not in _issue_codes(within)


def test_compare_padding_opaque_values_compare_exact() -> None:
    same = _compare_visuals({"padding": "large"}, {"padding": "large"})
    assert "node.visual.padding" not in _issue_codes(same)

    different = _compare_visuals({"padding": "large"}, {"padding": [16, 16, 16]})
    assert "node.visual.padding" in _issue_codes(different)


def test_compare_spacing_px_override_via_context_tolerance() -> None:
    report = _compare_visuals(
        {"gap": 16, "padding": 16},
        {"gap": 20, "padding": [16, 16, 20, 16]},
        context={"tolerance": {"spacing_px": 4}},
    )
    assert "node.visual.gap" not in _issue_codes(report)
    assert "node.visual.padding" not in _issue_codes(report)

    exact = _compare_visuals({"gap": 16}, {"gap": 17}, context={"tolerance": {"spacing_px": 0}})
    assert "node.visual.gap" in _issue_codes(exact)


def test_compare_layout_spacing_absent_keys_emit_no_issues() -> None:
    # Neither side defines layout keys (pre-048 trees).
    assert _compare_visuals({"fill": "#FFFFFF"}, {"fill": "#FFFFFF"})["issues"] == []

    # Key present on only one side stays silent in both directions.
    one_side = _compare_visuals(
        {"gap": 16, "layout": "vertical", "alignItems": "stretch", "padding": 16}, {}
    )
    assert one_side["issues"] == []
    other_side = _compare_visuals(
        {}, {"gap": 16, "layout": "vertical", "alignItems": "stretch", "padding": 16}
    )
    assert other_side["issues"] == []


def test_flow_screen_draft_tokens_ir_and_update(tmp_path: Path) -> None:
    flow = {
        "id": "checkout-flow",
        "screens": [
            {
                "id": "checkout",
                "components": [
                    {"semantic_id": "checkout.title", "role": "text", "text": "Checkout"},
                    {
                        "semantic_id": "checkout.pay",
                        "role": "button",
                        "text": "Pay",
                        "intent": "pay",
                    },
                ],
            }
        ],
    }
    assert validate_flow_contract(flow) == []
    screen = screen_contracts_from_flow(flow)[0]
    draft = pencil_draft_from_screen(screen)
    assert draft["version"] == "2.11"
    assert isinstance(draft["children"][0]["context"], str)
    assert draft["children"][0]["children"][0]["textGrowth"] == "fixed-width"
    assert draft["children"][0]["children"][0]["fill"] == "#111827"
    pen_path = write_json(tmp_path / "draft.pen", draft)
    tokens = extract_design_tokens(pen_path)
    assert tokens["colors"] == ["#0057FF", "#111827", "#FFFFFF"]
    assert tokens["spacing"] == [8, 12, 16, 24]

    updates = {"checkout.title": {"content": "Updated", "context": {"variant": "demo"}}}
    update_path = write_json(tmp_path / "updates.json", updates)
    out_path = tmp_path / "updated.pen"
    update_pen_by_semantic_id(pen_path, json.loads(update_path.read_text()), out_path)
    updated = out_path.read_text()
    assert "Updated" in updated
    assert "variant=demo" in updated

    ir = code_ir_from_contract(screen, expected_tree_from_pen(pen_path))
    assert [component["id"] for component in ir["components"]] == ["checkout.title", "checkout.pay"]
