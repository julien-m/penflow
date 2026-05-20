from __future__ import annotations

import copy
import json
from pathlib import Path

from penflow.cli import main
from penflow.semantic_mapping import write_pencil_context_map
from tests.test_semantic_enrichment import legacy_pen, semantic_tree, write_json


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


def mapping_tree() -> dict:
    tree = semantic_tree()
    tree["screens"][0]["root"]["children"].append(
        {
            "semantic_id": "checkout.help",
            "role": "text",
            "text": "Need help?",
            "source_map": {"screen_spec": "flow-ui-contract/screens/checkout.md"},
        }
    )
    return tree


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


def test_write_pencil_context_map_reports_all_buckets_and_preserves_existing_layout(
    tmp_path: Path,
) -> None:
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
    before_visual = visual_snapshot_by_id(pen)
    pen_path = write_json(tmp_path / "ui.pen", pen)
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", mapping_tree())
    map_path = tmp_path / "pencil-context-map.json"
    pen_out = tmp_path / "ui.mapped.pen"

    result = write_pencil_context_map(pen_path, tree_path, map_path, pen_out=pen_out)
    mapped_pen = json.loads(pen_out.read_text(encoding="utf-8"))
    after_visual = visual_snapshot_by_id(mapped_pen)

    assert result["status"] == "PARTIAL"
    assert [item["semantic_id"] for item in result["matched"]] == ["checkout", "checkout.pay"]
    assert [item["semantic_id"] for item in result["created"]] == ["checkout.help"]
    assert [item["semantic_id"] for item in result["ambiguous"]] == ["checkout.title"]
    assert result["unmapped"] == []
    for node_id, snapshot in before_visual.items():
        assert after_visual[node_id] == snapshot


def test_write_pencil_context_map_is_deterministic(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", legacy_pen())
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", mapping_tree())
    first_path = tmp_path / "first-map.json"
    second_path = tmp_path / "second-map.json"

    write_pencil_context_map(pen_path, tree_path, first_path)
    write_pencil_context_map(pen_path, tree_path, second_path)

    assert first_path.read_bytes() == second_path.read_bytes()


def test_map_pencil_context_cli_outputs_json_and_buckets(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", legacy_pen())
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", mapping_tree())
    map_path = tmp_path / "pencil-context-map.json"
    pen_out = tmp_path / "ui.mapped.pen"

    assert (
        main(
            [
                "map-pencil-context",
                str(pen_path),
                str(tree_path),
                "--out",
                str(map_path),
                "--pen-out",
                str(pen_out),
                "--json",
            ]
        )
        == 0
    )
    context_map = json.loads(map_path.read_text(encoding="utf-8"))

    assert context_map["status"] == "PASS"
    assert {key for key in ("matched", "created", "ambiguous", "unmapped")} <= set(context_map)
    assert [item["semantic_id"] for item in context_map["created"]] == ["checkout.help"]
    assert pen_out.exists()
