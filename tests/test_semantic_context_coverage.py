# @spec FR-003: Bidirectional reconciliation — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-003
# @spec FR-008: Strict coverage report — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-008
"""Canonical semantic-context coverage service tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from penflow.schema_cache import validator_for
from penflow.cli import main
from penflow.semantic_context_coverage import audit_semantic_context, write_coverage_report
from tests.test_flow_contract_v2 import valid_contract
from tests.test_semantic_enrichment import semantic_tree


def _contract() -> dict:
    contract = copy.deepcopy(valid_contract())
    contract["nodes"][1]["test_id"] = "checkout-title"
    return contract


def _semantic(node_id: str, semantic_id: str, test_id: str, role: str) -> dict[str, Any]:
    node: dict[str, Any] = {
        "id": node_id,
        "type": "frame" if role == "screen" else "text",
        "context": {
            "classification": "semantic",
            "semantic_id": semantic_id,
            "test_id": test_id,
            "role": role,
        },
    }
    if role == "button":
        node["context"]["intent"] = "activate"
    return node


def _pen() -> dict:
    root = _semantic("screen", "checkout", "checkout-screen", "screen")
    title = _semantic("title", "checkout.title", "checkout-title", "text")
    pay = _semantic("pay", "checkout.pay", "checkout-pay", "button")
    pay["context"].update(
        intent="submit_payment",
        binding="checkout.payment_method",
        entity="checkout",
        permission="buyer_can_pay",
    )
    title["context"].update(binding="checkout.title", entity="checkout")
    title["content"] = "Checkout"
    pay["content"] = "Pay"
    pay["children"] = [
        {
            "id": "pay-label",
            "type": "text",
            "context": {
                "classification": "inherited",
                "inherits_from": "checkout.pay",
                "relation": "content",
            },
        },
        {
            "id": "pay-icon",
            "type": "icon",
            "context": {
                "classification": "decorative",
                "decorative_owner": "checkout.pay",
                "decorative_reason": "duplicates the button label",
            },
        },
    ]
    root["children"] = [title, pay]
    return {"version": 1, "children": [root]}


def test_positive_report_reconciles_exact_counts_without_appearance_inference() -> None:
    pen = _pen()
    pen["children"][0]["children"][0].update(
        {"fill": "#ff00ff", "x": 999, "name": "misleading button"}
    )

    report = audit_semantic_context(
        _contract(), pen, contract_path="flow-ui-contract/contract.json", pen_path="ui.pen"
    )

    assert report["status"] == "PASS"
    assert report["summary"] == {
        "anchored_unique": 3,
        "blocking": 0,
        "classification_conflict": 0,
        "contract_anchor_duplicate": 0,
        "contract_anchor_missing": 0,
        "contract_total": 3,
        "decorative": 1,
        "inherited": 1,
        "out_of_scope_metadata": 0,
        "pencil_records_seen": 5,
        "pencil_total": 5,
        "semantic": 3,
        "semantic_resolved": 3,
        "unclassified": 0,
    }
    assert len(report["buckets"]["decorative_exclusions"]) == 1
    assert len(report["buckets"]["valid_inheritance"]) == 1
    assert list(validator_for("semantic-context-coverage.schema.json").iter_errors(report)) == []


def test_unknown_semantic_and_unclassified_nodes_fail_once_in_canonical_buckets() -> None:
    pen = _pen()
    pen["children"][0]["children"].extend(
        [
            _semantic("ghost", "checkout.ghost", "checkout-ghost", "button"),
            {"id": "zoom", "type": "icon_font", "name": "Zoom"},
        ]
    )

    report = audit_semantic_context(
        _contract(), pen, contract_path="contract.json", pen_path="ui.pen"
    )

    assert report["status"] == "FAIL"
    assert [item["code"] for item in report["buckets"]["pencil_missing_in_contract"]] == [
        "pencil.semantic_unknown"
    ]
    assert [item["code"] for item in report["buckets"]["pencil_unclassified"]] == [
        "pencil.node_unclassified"
    ]
    assert report["summary"]["blocking"] == 2


def test_report_bytes_are_deterministic_and_bind_both_input_digests(tmp_path: Path) -> None:
    contract_path = tmp_path / "contract.json"
    pen_path = tmp_path / "ui.pen"
    out_path = tmp_path / "semantic-context-coverage.json"
    contract_path.write_text(json.dumps(_contract(), sort_keys=True), encoding="utf-8")
    pen_path.write_text(json.dumps(_pen(), sort_keys=True), encoding="utf-8")

    first = write_coverage_report(contract_path, pen_path, out_path)
    first_bytes = out_path.read_bytes()
    second = write_coverage_report(contract_path, pen_path, out_path)

    assert first == second
    assert out_path.read_bytes() == first_bytes
    assert len(first["inputs"]["contract"]["sha256"]) == 64
    assert len(first["inputs"]["pencil"]["sha256"]) == 64
    assert main(["validate-report", str(out_path), "--schema", "--json"]) == 0


def test_audit_context_coverage_cli_writes_report_and_uses_exact_exit_codes(
    tmp_path: Path, governed_consumer_project
) -> None:
    contract_path = tmp_path / "flow-ui-contract" / "contract.json"
    contract_path.parent.mkdir()
    contract_path.write_text(json.dumps(_contract()), encoding="utf-8")
    pen_path = tmp_path / "ui.pen"
    pen_path.write_text(json.dumps(_pen()), encoding="utf-8")
    governed_consumer_project(tmp_path, pen_path)
    out_path = tmp_path / "semantic-context-coverage.json"

    assert (
        main(
            [
                "audit-context-coverage",
                str(pen_path),
                "--contract",
                str(contract_path),
                "--out",
                str(out_path),
                "--project",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(out_path.read_text())["status"] == "PASS"


def test_map_context_strict_coverage_delegates_and_keeps_both_artifacts(
    tmp_path: Path, governed_consumer_project, capsys
) -> None:
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(_contract()), encoding="utf-8")
    pen_path = tmp_path / "ui.pen"
    pen_path.write_text(json.dumps(_pen()), encoding="utf-8")
    tree_path = tmp_path / "semantic-ui-tree.json"
    tree_path.write_text(json.dumps(semantic_tree()), encoding="utf-8")
    governed_consumer_project(tmp_path, pen_path)
    map_path = tmp_path / "pencil-context-map.json"
    coverage_path = tmp_path / "semantic-context-coverage.json"

    assert (
        main(
            [
                "map-pencil-context",
                str(pen_path),
                str(tree_path),
                "--out",
                str(map_path),
                "--strict-coverage",
                "--contract",
                str(contract_path),
                "--coverage-out",
                str(coverage_path),
                "--project",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
    assert map_path.is_file()
    assert json.loads(coverage_path.read_text())["status"] == "PASS"
    envelope = json.loads(capsys.readouterr().out)
    assert set(envelope) == {"kind", "version", "context_map", "coverage"}
    assert envelope == {
        "kind": "penflow-context-mapping-result",
        "version": 2,
        "context_map": {
            "path": str(map_path),
            "status": "PASS",
            "forward_only": True,
        },
        "coverage": {
            "path": str(coverage_path),
            "status": "PASS",
            "schema_version": 1,
        },
    }
    assert list(validator_for("context-mapping-result.schema.json").iter_errors(envelope)) == []
