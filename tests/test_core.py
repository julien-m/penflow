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


def test_invalid_context_reports_errors(tmp_path: Path) -> None:
    data = sample_pen()
    data["children"][0]["children"][1]["context"].pop("intent")
    data["children"][0]["children"][1]["context"]["binding"] = "bad"
    pen_path = write_json(tmp_path / "bad.pen", data)
    issues = validate_pen_context(parse_pen(pen_path))
    assert {issue.code for issue in issues} == {"context.button_intent_missing", "context.binding_format"}


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


def test_flow_screen_draft_tokens_ir_and_update(tmp_path: Path) -> None:
    flow = {
        "id": "checkout-flow",
        "screens": [
            {
                "id": "checkout",
                "components": [
                    {"semantic_id": "checkout.title", "role": "text", "text": "Checkout"},
                    {"semantic_id": "checkout.pay", "role": "button", "text": "Pay", "intent": "pay"},
                ],
            }
        ],
    }
    assert validate_flow_contract(flow) == []
    screen = screen_contracts_from_flow(flow)[0]
    draft = pencil_draft_from_screen(screen)
    pen_path = write_json(tmp_path / "draft.pen", draft)
    tokens = extract_design_tokens(pen_path)
    assert tokens["spacing"] == [16, 24]

    updates = {"checkout.title": {"content": "Updated"}}
    update_path = write_json(tmp_path / "updates.json", updates)
    out_path = tmp_path / "updated.pen"
    update_pen_by_semantic_id(pen_path, json.loads(update_path.read_text()), out_path)
    assert "Updated" in out_path.read_text()

    ir = code_ir_from_contract(screen, expected_tree_from_pen(pen_path))
    assert [component["id"] for component in ir["components"]] == ["checkout.title", "checkout.pay"]

