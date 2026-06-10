# @spec(FR-001)
from __future__ import annotations

import copy
import json
from pathlib import Path

from penflow.cli import main
from penflow.semantic_validation import validate_semantic_tree


ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "demo" / "semantic-ui-tree.json"


def load_example() -> dict:
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def issue_codes(tree: dict) -> set[str]:
    return {issue["code"] for issue in validate_semantic_tree(tree)}


def test_validate_semantic_tree_accepts_demo_example() -> None:
    assert validate_semantic_tree(load_example()) == []


def test_validate_semantic_tree_reports_duplicate_ids() -> None:
    tree = load_example()
    duplicate_flow = copy.deepcopy(tree["flows"][0])
    tree["flows"].append(duplicate_flow)
    duplicate_screen = copy.deepcopy(tree["screens"][0])
    tree["screens"].append(duplicate_screen)
    duplicate_node = copy.deepcopy(tree["screens"][0]["root"]["children"][0])
    tree["screens"][0]["root"]["children"].append(duplicate_node)
    tree["screens"][0]["root"]["children"][1]["test_id"] = "duplicate-test"
    tree["screens"][1]["root"]["children"][1]["test_id"] = "duplicate-test"

    codes = issue_codes(tree)

    assert "semantic.flow_id_duplicate" in codes
    assert "semantic.screen_id_duplicate" in codes
    assert "semantic.node_id_duplicate" in codes
    assert "semantic.test_id_duplicate" in codes


def test_validate_semantic_tree_reports_broken_flow_screen_links() -> None:
    tree = load_example()
    tree["flows"][0]["entry_screen"] = "missing"
    tree["flows"][0]["steps"][0]["screen_id"] = "missing"
    tree["flows"][0]["transitions"].append({"from": "checkout", "to": "checkout", "trigger": "x"})
    tree["flows"][0]["transitions"][0]["to"] = "missing"
    tree["screens"][0]["flow_id"] = "missing-flow"

    codes = issue_codes(tree)

    assert "semantic.flow_entry_screen_missing" in codes
    assert "semantic.flow_step_screen_missing" in codes
    assert "semantic.flow_transition_screen_missing" in codes
    assert "semantic.screen_flow_missing" in codes


def test_validate_semantic_tree_reports_role_and_context_field_errors() -> None:
    tree = load_example()
    button = tree["screens"][0]["root"]["children"][2]
    button.pop("intent")
    button["binding"] = "bad"
    invalid_role_node = {
        "semantic_id": "checkout.invalid-role",
        "role": "unknown",
        "source_map": {
            "contract": "examples/demo/flow-ui-contract/contract.json",
            "contract_path": "$.nodes[99]",
        },
    }
    list_node = {
        "semantic_id": "checkout.items",
        "role": "list",
        "binding": "checkout.items",
        "source_map": {
            "contract": "examples/demo/flow-ui-contract/contract.json",
            "contract_path": "$.nodes[100]",
        },
    }
    tree["screens"][0]["root"]["children"].append(invalid_role_node)
    tree["screens"][0]["root"]["children"].append(list_node)

    codes = issue_codes(tree)

    assert "semantic.role_invalid" in codes
    assert "semantic.intent_required" in codes
    assert "semantic.binding_format" in codes
    assert "semantic.repeat_required" in codes


def test_validate_semantic_tree_reports_incoherent_source_maps() -> None:
    tree = load_example()
    tree["flows"][0]["source_map"]["notes"] = ["keeps source_map non-empty"]
    tree["flows"][0]["source_map"].pop("contract")
    tree["screens"][0]["source_map"].pop("contract")
    tree["screens"][0]["root"]["source_map"].pop("contract")

    codes = issue_codes(tree)

    assert "semantic.flow_source_map_flow_spec_required" in codes
    assert "semantic.screen_source_map_screen_spec_required" in codes
    assert "semantic.node_source_map_screen_spec_required" in codes


def test_validate_semantic_tree_cli_outputs_json_status(tmp_path: Path) -> None:
    tree_path = tmp_path / "semantic-ui-tree.json"
    tree_path.write_text(json.dumps(load_example()), encoding="utf-8")

    assert main(["validate-semantic-tree", str(tree_path), "--json"]) == 0

    invalid = load_example()
    invalid["screens"][0]["root"]["children"][1].pop("source_map")
    invalid_path = tmp_path / "invalid-semantic-ui-tree.json"
    invalid_path.write_text(json.dumps(invalid), encoding="utf-8")

    assert main(["validate-semantic-tree", str(invalid_path), "--json"]) == 1
