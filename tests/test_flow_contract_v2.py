from __future__ import annotations

import json
from pathlib import Path

from penflow.cli import main
from penflow.flow_contract import load_flow_contract_v2, validate_flow_contract_v2


def valid_contract() -> dict:
    return {
        "version": 2,
        "kind": "penflow-flow-contract",
        "contract_id": "checkout-contract",
        "actors": [{"id": "buyer", "name": "Buyer"}],
        "entities": [
            {
                "id": "checkout",
                "fields": [
                    {"id": "title", "type": "string"},
                    {"id": "payment_method", "type": "string"},
                ],
            }
        ],
        "screens": [
            {
                "id": "checkout",
                "flow_id": "checkout",
                "title": "Checkout",
                "surface": "web-desktop",
                "viewport": {"width": 1440, "height": 900},
                "states": [{"id": "default"}, {"id": "success"}, {"id": "error"}],
                "root_node": "checkout.root",
            }
        ],
        "nodes": [
            {
                "id": "checkout.root",
                "screen_id": "checkout",
                "semantic_id": "checkout",
                "test_id": "checkout-screen",
                "role": "screen",
                "children": ["checkout.title", "checkout.pay"],
            },
            {
                "id": "checkout.title",
                "screen_id": "checkout",
                "semantic_id": "checkout.title",
                "role": "text",
                "text": "Checkout",
                "binding": "checkout.title",
            },
            {
                "id": "checkout.pay",
                "screen_id": "checkout",
                "semantic_id": "checkout.pay",
                "test_id": "checkout-pay",
                "role": "button",
                "text": "Pay",
                "binding": "checkout.payment_method",
                "entity": "checkout",
                "action": "submit_payment",
            },
        ],
        "guards": [{"id": "payment_ready"}],
        "permissions": [
            {
                "id": "buyer_can_pay",
                "actor": "buyer",
                "action": "submit_payment",
                "entity": "checkout",
            }
        ],
        "mutations": [
            {
                "id": "create_payment",
                "method": "POST",
                "endpoint": "/payments",
                "entity": "checkout",
                "request": {},
                "response": {},
                "success_state": "success",
                "error_state": "error",
            }
        ],
        "actions": [
            {
                "id": "submit_payment",
                "node": "checkout.pay",
                "trigger": "click",
                "guard": "payment_ready",
                "permission": "buyer_can_pay",
                "mutation": "create_payment",
                "success_transition": "payment_success",
                "error_transition": "payment_error",
            }
        ],
        "flows": [{"id": "checkout", "entry_screen": "checkout"}],
        "transitions": [
            {
                "id": "payment_success",
                "flow": "checkout",
                "from_screen": "checkout",
                "to_screen": "checkout",
                "from_state": "default",
                "to_state": "success",
                "trigger": "submit_payment",
                "action": "submit_payment",
            },
            {
                "id": "payment_error",
                "flow": "checkout",
                "from_screen": "checkout",
                "to_screen": "checkout",
                "from_state": "default",
                "to_state": "error",
                "trigger": "submit_payment",
                "action": "submit_payment",
            },
        ],
        "needs_review": False,
        "needs_clarification": [],
    }


def write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_valid_contract_passes_schema_references_and_cli(tmp_path: Path) -> None:
    contract_path = write_json(tmp_path / "flow-ui-contract" / "contract.json", valid_contract())

    assert validate_flow_contract_v2(load_flow_contract_v2(contract_path)) == []
    assert main(["validate-flow-contract", str(contract_path), "--json"]) == 0


def test_contract_schema_fails_closed_for_unknown_property(tmp_path: Path) -> None:
    contract = valid_contract()
    contract["unknown"] = True
    contract_path = write_json(tmp_path / "contract.json", contract)

    issues = validate_flow_contract_v2(load_flow_contract_v2(contract_path))

    assert [issue["code"] for issue in issues] == ["contract.schema.additional_property"]
    assert issues[0]["path"] == "$.unknown"
    assert main(["validate-flow-contract", str(contract_path), "--json"]) == 1


def test_contract_referential_validation_is_fail_closed(tmp_path: Path) -> None:
    contract = valid_contract()
    contract["actions"][0]["mutation"] = "missing_mutation"
    contract_path = write_json(tmp_path / "contract.json", contract)

    issues = validate_flow_contract_v2(load_flow_contract_v2(contract_path))

    assert any(issue["code"] == "contract.reference.missing_mutation" for issue in issues)
    assert main(["validate-flow-contract", str(contract_path), "--json"]) == 1


def test_contract_schema_rejects_nested_unknown_properties() -> None:
    contract = valid_contract()
    contract["nodes"][0]["unknown"] = True

    issues = validate_flow_contract_v2(contract)

    assert any(
        issue["code"] == "contract.schema.additional_property"
        and issue["path"] == "$.nodes[0].unknown"
        for issue in issues
    )


def test_contract_rejects_non_object_root() -> None:
    issues = validate_flow_contract_v2([])

    assert issues == [
        {
            "severity": "error",
            "code": "contract.schema.type",
            "path": "$",
            "message": "contract must be object",
        }
    ]


def test_contract_requires_action_on_interactive_nodes() -> None:
    contract = valid_contract()
    del contract["nodes"][2]["action"]

    issues = validate_flow_contract_v2(contract)

    assert any(
        issue["code"] == "contract.reference.interactive_action_required" for issue in issues
    )


def test_contract_rejects_transition_trigger_without_action_or_interactive_node() -> None:
    contract = valid_contract()
    contract["transitions"][0]["trigger"] = "missing_trigger"

    issues = validate_flow_contract_v2(contract)

    assert any(issue["code"] == "contract.reference.missing_trigger" for issue in issues)


def test_contract_validates_mutation_states_against_action_screen() -> None:
    contract = valid_contract()
    contract["screens"].append(
        {
            "id": "receipt",
            "flow_id": "checkout",
            "states": [{"id": "remote_success"}],
            "root_node": "checkout.root",
        }
    )
    contract["mutations"][0]["success_state"] = "remote_success"

    issues = validate_flow_contract_v2(contract)

    assert any(issue["code"] == "contract.reference.missing_state" for issue in issues)


def test_migrated_contract_with_clarifications_blocks_strict_validation(tmp_path: Path) -> None:
    contract = valid_contract()
    contract["needs_review"] = True
    contract["needs_clarification"] = ["Confirm submit_payment side effects."]
    contract_path = write_json(tmp_path / "contract.json", contract)

    issues = validate_flow_contract_v2(load_flow_contract_v2(contract_path))

    assert issues[0]["code"] == "contract.clarification.unresolved"


def test_legacy_flow_specs_without_contract_json_fail_with_migration_message(
    tmp_path: Path,
) -> None:
    specs = tmp_path / "flow-ui-contract"
    (specs / "flows").mkdir(parents=True)
    (specs / "screens").mkdir()
    (specs / "flows" / "checkout.md").write_text("---\nflow: checkout\n---\n", encoding="utf-8")

    assert main(["validate-flow-specs", str(specs), "--json"]) == 1


def test_export_semantic_tree_reads_contract_json_only(tmp_path: Path) -> None:
    contract_path = write_json(tmp_path / "flow-ui-contract" / "contract.json", valid_contract())
    out = tmp_path / "semantic-ui-tree.json"

    assert main(["export-semantic-tree", str(contract_path), "--out", str(out), "--json"]) == 0
    tree = json.loads(out.read_text(encoding="utf-8"))

    assert tree["tree_id"] == "checkout-contract"
    assert tree["source"]["contract"] == str(contract_path)
    assert tree["flows"][0]["source_map"]["contract_path"] == "$.flows[0]"
    assert tree["screens"][0]["source_map"]["contract_path"] == "$.screens[0]"
    assert tree["screens"][0]["root"]["semantic_id"] == "checkout"
    assert tree["screens"][0]["root"]["source_map"]["contract_path"] == "$.nodes[0]"
    assert tree["screens"][0]["root"]["children"][1]["semantic_id"] == "checkout.pay"
    assert tree["screens"][0]["root"]["children"][1]["actions"][0]["id"] == "submit_payment"
    assert tree["screens"][0]["validations"]
    assert tree["screens"][0]["side_effects"]
