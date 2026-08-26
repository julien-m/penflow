# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-004)
# @spec(FR-006)
# @spec(FR-011)
from __future__ import annotations

import json
from pathlib import Path

import pytest

from penflow.cli import main
from penflow.flow_contract import (
    interactive_coverage_report,
    load_flow_contract_v2,
    validate_flow_contract_v2,
)


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
        "guards": [
            {
                "id": "payment_ready",
                "variable": "payment_result",
                "operator": "equals",
                "value": "success",
                "source": "runtime_result",
            },
            {
                "id": "payment_failed",
                "variable": "payment_result",
                "operator": "equals",
                "value": "error",
                "source": "runtime_result",
            },
        ],
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
                "guard": "payment_ready",
                "kind": "state",
                "label": "Payment succeeds",
                "causal": {
                    "version": 1,
                    "action_visibility": "user-visible",
                    "outcome": "success",
                    "fanout": {"group": "payment_result", "policy": "exclusive"},
                },
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
                "guard": "payment_failed",
                "kind": "state",
                "label": "Payment fails",
                "causal": {
                    "version": 1,
                    "action_visibility": "user-visible",
                    "outcome": "error",
                    "fanout": {"group": "payment_result", "policy": "exclusive"},
                },
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


def test_contract_accepts_structured_guards_and_causal_transition_metadata() -> None:
    contract = valid_contract()

    assert validate_flow_contract_v2(contract) == []
    assert contract["guards"][0]["source"] == "runtime_result"
    assert contract["transitions"][0]["causal"]["fanout"]["policy"] == "exclusive"


def test_contract_rejects_incomplete_and_destination_derived_guards() -> None:
    incomplete = valid_contract()
    del incomplete["guards"][0]["source"]
    circular = valid_contract()
    circular["guards"][0]["variable"] = "destination"

    assert "contract.guard.incomplete" in {
        issue["code"] for issue in validate_flow_contract_v2(incomplete)
    }
    assert "contract.guard.non_causal_variable" in {
        issue["code"] for issue in validate_flow_contract_v2(circular)
    }


def test_contract_rejects_default_to_default_state_transition() -> None:
    contract = valid_contract()
    contract["transitions"][0]["to_state"] = "default"

    codes = {issue["code"] for issue in validate_flow_contract_v2(contract)}

    assert "contract.transition.default_unchanged" in codes


def test_contract_rejects_causal_action_without_visible_test_id() -> None:
    contract = valid_contract()
    del contract["nodes"][2]["test_id"]

    codes = {issue["code"] for issue in validate_flow_contract_v2(contract)}

    assert "contract.transition.action_not_observable" in codes


def test_contract_rejects_ungoverned_and_duplicate_fanout() -> None:
    ungoverned = valid_contract()
    del ungoverned["transitions"][1]["causal"]
    duplicate = valid_contract()
    duplicate["transitions"][1]["guard"] = "payment_ready"
    duplicate["transitions"][1]["causal"]["outcome"] = "success"

    ungoverned_codes = {issue["code"] for issue in validate_flow_contract_v2(ungoverned)}
    duplicate_codes = {issue["code"] for issue in validate_flow_contract_v2(duplicate)}

    assert "contract.transition.fanout_ungoverned" in ungoverned_codes
    assert "contract.transition.fanout_outcome_duplicate" in duplicate_codes
    assert "contract.transition.non_exclusive_fanout" in duplicate_codes


# @spec FR-006: Complete behavior graph — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-006
# @spec FR-007: Fail-closed references — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-007
def test_contract_accepts_explicit_owner_relation_and_repeat_registries() -> None:
    contract = valid_contract()
    contract["nodes"][0].update(
        {"kind": "screen_root", "owner": {"scope": "screen", "screen": "checkout"}}
    )
    contract["nodes"][1].update(
        {
            "kind": "element",
            "owner": {
                "scope": "screen",
                "screen": "checkout",
                "section": {"kind": "none", "reason": "screen_level_element"},
            },
            "parent": "checkout.root",
        }
    )
    contract["nodes"][2].update(
        {
            "kind": "element",
            "owner": {
                "scope": "screen",
                "screen": "checkout",
                "section": {"kind": "none", "reason": "screen_level_element"},
            },
            "parent": "checkout.root",
            "repeat_model": {
                "collection": "checkout.payment_method",
                "item_model": "checkout",
                "item_key": "payment_method",
                "instance_id_template": "checkout.pay.{payment_method}",
            },
        }
    )
    contract["relations"] = [
        {
            "id": "pay_updates_title",
            "kind": "data_dependency",
            "source": "checkout.pay",
            "target": "checkout.title",
            "effect": "refresh",
        }
    ]

    assert validate_flow_contract_v2(contract) == []


# @spec FR-007: Fail-closed references — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-007
def test_contract_emits_stable_destination_binding_list_and_static_codes() -> None:
    contract = valid_contract()
    contract["actions"][0]["destination"] = {"screen": "missing", "state": "unknown"}
    contract["actions"][0]["binding_ref"] = {"entity": "checkout", "field": "missing"}
    contract["nodes"][2]["role"] = "list"
    contract["screens"][0]["static"] = True
    contract["screens"][0]["static_reason"] = "system_surface"

    issue_codes = {issue["code"] for issue in validate_flow_contract_v2(contract)}

    assert {
        "binding.field_missing",
        "destination.reference_missing",
        "list.model_incomplete",
        "screen.static_interactive",
    } <= issue_codes


def test_contract_accepts_explicitly_governed_fanout() -> None:
    contract = valid_contract()
    for transition in contract["transitions"]:
        transition["causal"]["fanout"] = {
            "group": "payment_result",
            "policy": "governed",
            "governance": "Adapter executes each outcome in an isolated run.",
        }

    assert validate_flow_contract_v2(contract) == []


def test_contract_rejects_governed_causal_fanout_without_structured_guards() -> None:
    contract = valid_contract()
    for guard in contract["guards"]:
        for field in ("variable", "operator", "value", "source"):
            guard.pop(field)
    for transition in contract["transitions"]:
        transition["causal"]["fanout"] = {
            "group": "payment_result",
            "policy": "governed",
            "governance": "Adapter executes each outcome in an isolated run.",
        }

    codes = {issue["code"] for issue in validate_flow_contract_v2(contract)}

    assert "contract.transition.causal_guard_incomplete" in codes


def test_contract_keeps_legacy_metadata_free_fanout_compatible() -> None:
    contract = valid_contract()
    for transition in contract["transitions"]:
        transition.pop("kind")
        transition.pop("label")
        transition.pop("causal")

    assert validate_flow_contract_v2(contract) == []


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
    assert any(issue["code"] == "contract.interactive_unbound" for issue in issues)


def test_contract_reports_screen_interactive_coverage() -> None:
    coverage = interactive_coverage_report(valid_contract())

    assert coverage["summary"] == {"covered": 1, "static": 0, "total": 1, "uncovered": 0}
    assert coverage["screens"][0]["interactive_actions"] == [
        {
            "node": "checkout.pay",
            "semantic_id": "checkout.pay",
            "role": "button",
            "binding": "action",
        }
    ]


def test_validate_flow_contract_cli_includes_interactive_coverage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    contract_path = write_json(tmp_path / "contract.json", valid_contract())

    assert main(["validate-flow-contract", str(contract_path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["interactive_coverage"]["summary"]["covered"] == 1
    assert payload["interactive_coverage"]["screens"][0]["status"] == "covered"


def test_contract_rejects_screen_without_interactive_action_or_static_justification() -> None:
    contract = valid_contract()
    contract["nodes"][0]["children"] = ["checkout.title"]
    contract["nodes"] = contract["nodes"][:2]
    contract["guards"] = []
    contract["actions"] = []
    contract["permissions"] = []
    contract["mutations"] = []
    contract["transitions"] = []

    issues = validate_flow_contract_v2(contract)

    assert any(
        issue["code"] == "contract.interactive_unbound" and issue["path"] == "$.screens[0]"
        for issue in issues
    )


def test_contract_accepts_static_screen_justification_without_interactive_action() -> None:
    contract = valid_contract()
    contract["screens"][0]["static"] = True
    contract["screens"][0]["static_reason"] = "Read-only confirmation screen."
    contract["nodes"][0]["children"] = ["checkout.title"]
    contract["nodes"] = contract["nodes"][:2]
    contract["guards"] = []
    contract["actions"] = []
    contract["permissions"] = []
    contract["mutations"] = []
    contract["transitions"] = []

    issues = validate_flow_contract_v2(contract)

    assert issues == []
    assert interactive_coverage_report(contract)["screens"][0]["status"] == "static"


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
    assert tree["flows"][0]["transitions"][0]["kind"] == "state"
    assert tree["flows"][0]["transitions"][0]["label"] == "Payment succeeds"
    assert tree["flows"][0]["transitions"][0]["condition"] == "payment_ready"
    assert tree["flows"][0]["transitions"][0]["causal"]["outcome"] == "success"
