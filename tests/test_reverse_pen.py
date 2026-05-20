from __future__ import annotations

import copy
import json
from pathlib import Path

from penflow.cli import main
from penflow.reverse import reverse_pen
from penflow.semantic_validation import validate_semantic_tree


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


def legacy_pen_without_business_logic() -> dict:
    return {
        "version": "2.11",
        "children": [
            {
                "id": "checkoutScreen",
                "type": "frame",
                "name": "Checkout",
                "x": 20,
                "y": 40,
                "width": 390,
                "height": 844,
                "layout": "vertical",
                "gap": 16,
                "padding": 24,
                "fill": "#FFFFFF",
                "children": [
                    {
                        "id": "checkoutTitle",
                        "type": "text",
                        "content": "Checkout",
                        "width": "fill_container",
                        "fontSize": 24,
                        "fill": "#111827",
                    },
                    {
                        "id": "payButton",
                        "type": "frame",
                        "name": "Pay",
                        "width": 320,
                        "height": 48,
                        "layout": "horizontal",
                        "gap": 8,
                        "padding": [12, 16],
                        "fill": "#0057FF",
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


def visual_snapshot_by_id(pen: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}

    def visit(node: dict) -> None:
        result[node["id"]] = {key: copy.deepcopy(node[key]) for key in VISUAL_KEYS if key in node}
        result[node["id"]]["child_order"] = [
            child.get("id") for child in node.get("children", []) or []
        ]
        for child in node.get("children", []) or []:
            visit(child)

    for child in pen.get("children", []) or []:
        visit(child)
    return result


def test_reverse_pen_writes_specs_tree_and_clarification_markers(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", legacy_pen_without_business_logic())
    out_dir = tmp_path / "reverse"

    report = reverse_pen(pen_path, out_dir)
    tree = json.loads((out_dir / "semantic-ui-tree.json").read_text(encoding="utf-8"))
    flow_spec = (out_dir / "flow-ui-contract" / "flows" / "checkout.md").read_text(encoding="utf-8")
    screen_spec = (out_dir / "flow-ui-contract" / "screens" / "checkout.md").read_text(
        encoding="utf-8"
    )

    assert report["status"] == "PASS"
    assert report["screens"] == 1
    assert validate_semantic_tree(tree) == []
    assert tree["screens"][0]["root"]["source_map"]["pencil_node_id"] == "checkoutScreen"
    assert tree["screens"][0]["root"]["children"][1]["semantic_id"] == "checkout.pay"
    assert tree["screens"][0]["root"]["children"][1]["intent"] == "[NEEDS CLARIFICATION]"
    assert "pencil_path: 0.1" in tree["screens"][0]["root"]["children"][1]["source_map"]["notes"]
    assert "[NEEDS CLARIFICATION]" in flow_spec
    assert "[NEEDS CLARIFICATION]" in screen_spec


def test_reverse_pen_output_is_deterministic(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", legacy_pen_without_business_logic())
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    reverse_pen(pen_path, first_dir)
    reverse_pen(pen_path, second_dir)

    first_files = sorted(
        path.relative_to(first_dir) for path in first_dir.rglob("*") if path.is_file()
    )
    second_files = sorted(
        path.relative_to(second_dir) for path in second_dir.rglob("*") if path.is_file()
    )
    assert first_files == second_files
    for relative_path in first_files:
        assert (first_dir / relative_path).read_bytes() == (second_dir / relative_path).read_bytes()


def test_reverse_pen_optional_enrichment_preserves_existing_layout(tmp_path: Path) -> None:
    pen = legacy_pen_without_business_logic()
    before_visual = visual_snapshot_by_id(pen)
    pen_path = write_json(tmp_path / "ui.pen", pen)
    out_dir = tmp_path / "reverse"

    reverse_pen(pen_path, out_dir, enrich=True)
    enriched = json.loads((out_dir / "ui.enriched.pen").read_text(encoding="utf-8"))
    after_visual = visual_snapshot_by_id(enriched)

    assert before_visual == after_visual
    assert "semantic_id=checkout.pay" in enriched["children"][0]["children"][1]["context"]
    assert "intent=[NEEDS CLARIFICATION]" in enriched["children"][0]["children"][1]["context"]


def test_reverse_pen_cli_outputs_json_and_valid_semantic_tree(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", legacy_pen_without_business_logic())
    out_dir = tmp_path / "reverse"

    assert main(["reverse-pen", str(pen_path), "--out", str(out_dir), "--json"]) == 0
    assert main(["validate-semantic-tree", str(out_dir / "semantic-ui-tree.json"), "--json"]) == 0
