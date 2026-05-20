from __future__ import annotations

import copy
import json
from pathlib import Path

from penflow.cli import main
from penflow.pen import parse_pen, validate_pen_context
from penflow.semantic_enrichment import enrich_pen_from_semantic_tree


VISUAL_KEYS = {
    "type",
    "x",
    "y",
    "width",
    "height",
    "layout",
    "gap",
    "padding",
    "fill",
    "stroke",
    "content",
}


def semantic_tree() -> dict:
    return {
        "version": 1,
        "kind": "semantic-ui-tree",
        "tree_id": "checkout-demo",
        "source": {"notes": ["test fixture"]},
        "flows": [
            {
                "id": "checkout",
                "title": "Checkout",
                "entry_screen": "checkout",
                "steps": [{"id": "checkout-step", "screen_id": "checkout", "intent": "checkout"}],
                "transitions": [{"from": "checkout", "to": "checkout", "trigger": "checkout.pay"}],
                "source_map": {"flow_spec": "flow-ui-contract/flows/checkout.md"},
            }
        ],
        "screens": [
            {
                "id": "checkout",
                "flow_id": "checkout",
                "surface": "web",
                "viewport": {"width": 390, "height": 844},
                "states": [{"name": "default"}],
                "validations": [],
                "side_effects": [],
                "source_map": {"screen_spec": "flow-ui-contract/screens/checkout.md"},
                "root": {
                    "semantic_id": "checkout",
                    "role": "screen",
                    "source_map": {"screen_spec": "flow-ui-contract/screens/checkout.md"},
                    "children": [
                        {
                            "semantic_id": "checkout.title",
                            "role": "text",
                            "text": "Checkout",
                            "source_map": {"screen_spec": "flow-ui-contract/screens/checkout.md"},
                        },
                        {
                            "semantic_id": "checkout.pay",
                            "role": "button",
                            "text": "Pay",
                            "intent": "submit_payment",
                            "binding": "checkout.payment_method",
                            "entity": "payment",
                            "test_id": "checkout-pay",
                            "states": [{"name": "enabled"}],
                            "validations": [{"rule": "payment_method_present"}],
                            "side_effects": [
                                {"effect": "create_payment_intent", "target": "payment"}
                            ],
                            "source_map": {
                                "flow_spec": "flow-ui-contract/flows/checkout.md",
                                "screen_spec": "flow-ui-contract/screens/checkout.md",
                            },
                        },
                    ],
                },
            }
        ],
    }


def legacy_pen() -> dict:
    return {
        "version": "2.11",
        "children": [
            {
                "id": "screen",
                "type": "frame",
                "name": "Checkout Screen",
                "x": 32,
                "y": 48,
                "width": 430,
                "height": 900,
                "layout": "vertical",
                "gap": 20,
                "padding": 32,
                "fill": "#FAFAFA",
                "context": "semantic_id=checkout; role=screen",
                "children": [
                    {
                        "id": "hero",
                        "type": "text",
                        "name": "Hero title",
                        "content": "Checkout",
                        "width": 360,
                        "fontSize": 30,
                        "fill": "#111111",
                    },
                    {
                        "id": "payButton",
                        "type": "frame",
                        "name": "Pay",
                        "width": 280,
                        "height": 52,
                        "layout": "horizontal",
                        "gap": 6,
                        "padding": [10, 18],
                        "fill": "#FF00AA",
                        "children": [
                            {
                                "id": "payLabel",
                                "type": "text",
                                "content": "Pay",
                                "fill": "#FFFFFF",
                            }
                        ],
                    },
                ],
            }
        ],
    }


def write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def visual_snapshot(node: dict) -> dict:
    snapshot = {key: copy.deepcopy(node[key]) for key in VISUAL_KEYS if key in node}
    if "children" in node:
        snapshot["child_order"] = [child.get("id") for child in node["children"]]
    return snapshot


def test_enrich_pen_preserves_layout_and_injects_business_context(tmp_path: Path) -> None:
    pen = legacy_pen()
    pen_path = write_json(tmp_path / "ui.pen", pen)
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", semantic_tree())
    out_path = tmp_path / "ui.enriched.pen"
    before_root = visual_snapshot(pen["children"][0])
    before_button = visual_snapshot(pen["children"][0]["children"][1])

    result = enrich_pen_from_semantic_tree(pen_path, tree_path, out_path)
    enriched = json.loads(out_path.read_text(encoding="utf-8"))
    button = enriched["children"][0]["children"][1]

    assert result["status"] == "PASS"
    assert visual_snapshot(enriched["children"][0]) == before_root
    assert visual_snapshot(button) == before_button
    assert "semantic_id=checkout.pay" in button["context"]
    assert "role=button" in button["context"]
    assert "intent=submit_payment" in button["context"]
    assert "binding=checkout.payment_method" in button["context"]
    assert "entity=payment" in button["context"]
    assert "test_id=checkout-pay" in button["context"]
    assert button["source_map"]["flow_spec"].endswith("flows/checkout.md")
    assert button["semantic"]["validations"][0]["rule"] == "payment_method_present"
    assert validate_pen_context(parse_pen(out_path)) == []


def test_enrich_pen_is_deterministic(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", legacy_pen())
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", semantic_tree())
    first_path = tmp_path / "first.pen"
    second_path = tmp_path / "second.pen"

    enrich_pen_from_semantic_tree(pen_path, tree_path, first_path)
    enrich_pen_from_semantic_tree(pen_path, tree_path, second_path)

    assert first_path.read_bytes() == second_path.read_bytes()


def test_enrich_pen_reports_ambiguous_conservative_match_without_overwrite(tmp_path: Path) -> None:
    pen = legacy_pen()
    pen["children"][0]["children"].insert(
        1,
        {
            "id": "duplicateTitle",
            "type": "text",
            "name": "Checkout duplicate",
            "content": "Checkout",
            "width": 240,
            "fill": "#222222",
        },
    )
    pen_path = write_json(tmp_path / "ui.pen", pen)
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", semantic_tree())
    out_path = tmp_path / "ui.enriched.pen"

    result = enrich_pen_from_semantic_tree(pen_path, tree_path, out_path)
    enriched = json.loads(out_path.read_text(encoding="utf-8"))

    assert result["status"] == "PARTIAL"
    assert any(issue["code"] == "enrich.match_ambiguous" for issue in result["issues"])
    assert "context" not in enriched["children"][0]["children"][0]
    assert "context" not in enriched["children"][0]["children"][1]


def test_enrich_pen_cli_outputs_json_and_validate_pen_compatible(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", legacy_pen())
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", semantic_tree())
    out_path = tmp_path / "ui.enriched.pen"

    assert (
        main(["enrich-pen", str(pen_path), str(tree_path), "--out", str(out_path), "--json"]) == 0
    )
    assert main(["validate-pen", str(out_path), "--json"]) == 0
