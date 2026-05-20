from __future__ import annotations

import json
from pathlib import Path

from penflow.cli import main
from penflow.pen import parse_pen, validate_pen_context
from penflow.semantic_draft import write_pen_draft_from_semantic_tree


ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "demo" / "semantic-ui-tree.json"


def load_example_without_mockup() -> dict:
    tree = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    tree["source"].pop("mockup", None)
    for screen in tree["screens"]:
        screen["source_map"].pop("mockup", None)
        for node in _walk(screen["root"]):
            node.get("source_map", {}).pop("mockup", None)
    return tree


def _walk(node: dict) -> list[dict]:
    nodes = [node]
    for child in node.get("children", []) or []:
        nodes.extend(_walk(child))
    return nodes


def test_write_pen_draft_from_semantic_tree_creates_valid_pen_with_context(tmp_path: Path) -> None:
    tree_path = tmp_path / "semantic-ui-tree.json"
    tree_path.write_text(json.dumps(load_example_without_mockup()), encoding="utf-8")
    out_path = tmp_path / "ui.pen"

    draft = write_pen_draft_from_semantic_tree(tree_path, out_path)

    assert draft["version"] == "2.11"
    root = draft["children"][0]
    button = root["children"][1]
    assert root["name"] == "checkout"
    assert "role=screen" in root["context"]
    assert "semantic_id=checkout" in root["context"]
    assert "role=button" in button["context"]
    assert "intent=submit_payment" in button["context"]
    assert "binding=checkout.payment_method" in button["context"]
    assert "entity=payment" in button["context"]
    assert "test_id=checkout-pay" in button["context"]
    assert button["source_map"]["screen_spec"].endswith("screens/checkout.md")
    assert validate_pen_context(parse_pen(out_path)) == []


def test_write_pen_draft_from_semantic_tree_is_deterministic(tmp_path: Path) -> None:
    tree_path = tmp_path / "semantic-ui-tree.json"
    tree_path.write_text(json.dumps(load_example_without_mockup()), encoding="utf-8")
    first_path = tmp_path / "first.pen"
    second_path = tmp_path / "second.pen"

    write_pen_draft_from_semantic_tree(tree_path, first_path)
    write_pen_draft_from_semantic_tree(tree_path, second_path)

    assert first_path.read_bytes() == second_path.read_bytes()


def test_draft_pen_from_tree_cli_writes_json_and_validate_pen_compatible(tmp_path: Path) -> None:
    tree_path = tmp_path / "semantic-ui-tree.json"
    tree_path.write_text(json.dumps(load_example_without_mockup()), encoding="utf-8")
    out_path = tmp_path / "ui.pen"

    assert main(["draft-pen-from-tree", str(tree_path), "--out", str(out_path), "--json"]) == 0
    assert main(["validate-pen", str(out_path), "--json"]) == 0
