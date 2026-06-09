from __future__ import annotations

import json
from pathlib import Path

from penflow.cli import _validate_json_schema_subset
from penflow.cli import main
from tests.test_flow_contract_v2 import valid_contract, write_json


def test_demo_command_generates_pass_report(tmp_path: Path) -> None:
    out = tmp_path / "demo"
    assert main(["demo", "--out", str(out)]) == 0
    report = json.loads((out / "compare-report.json").read_text())
    assert report["status"] == "PASS"
    pen = json.loads((out / "ui.pen").read_text())
    assert pen["version"] == "2.11"
    assert isinstance(pen["children"][0]["context"], str)
    assert (out / "Checkout.jsx").exists()


def test_compare_tree_command_writes_reports(tmp_path: Path) -> None:
    assert main(["demo", "--out", str(tmp_path)]) == 0
    expected = tmp_path / "expected-ui-tree.json"
    actual = tmp_path / "actual-ui-tree.json"
    report = tmp_path / "report.json"
    assert (
        main(
            [
                "compare-tree",
                str(expected),
                str(actual),
                "--out",
                str(report),
            ]
        )
        == 0
    )
    assert json.loads(report.read_text())["status"] == "PASS"


def test_review_and_fix_report_commands_write_json(tmp_path: Path) -> None:
    assert main(["demo", "--out", str(tmp_path)]) == 0
    expected = tmp_path / "expected-ui-tree.json"
    actual = tmp_path / "actual-ui-tree.json"
    actual_tree = json.loads(actual.read_text())
    actual_tree["root"]["children"] = actual_tree["root"]["children"][:1]
    actual.write_text(json.dumps(actual_tree), encoding="utf-8")

    report = tmp_path / "report.json"
    review = tmp_path / "review.json"
    fix = tmp_path / "fix.json"
    assert main(["compare-tree", str(expected), str(actual), "--out", str(report)]) == 1
    assert main(["review-report", str(report), "--out", str(review)]) == 0
    assert main(["fix-report", str(report), "--out", str(fix)]) == 0
    assert json.loads(review.read_text())["kind"] == "penflow-review-report"
    assert (
        "Expected semantic node is absent"
        in json.loads(review.read_text())["issues"][0]["likely_cause"]
    )
    assert json.loads(fix.read_text())["kind"] == "penflow-fix-report"
    assert "Add the missing runtime element" in json.loads(fix.read_text())["fixes"][0]["fix"]


def test_strict_v2_contract_cli_commands_cover_json_pen_and_ir(tmp_path: Path) -> None:
    contract_path = write_json(tmp_path / "flow-ui-contract" / "contract.json", valid_contract())
    pen_path = write_json(tmp_path / "ui.pen", _contextualized_pen())
    ir_path = tmp_path / "code-ir.json"

    assert main(["validate-flow-contract", str(contract_path), "--json"]) == 0
    assert main(["validate-pen", str(pen_path), "--contract", str(contract_path), "--json"]) == 0
    assert (
        main(
            [
                "code-ir",
                "--from-context",
                str(pen_path),
                "--contract",
                str(contract_path),
                "--out",
                str(ir_path),
                "--json",
            ]
        )
        == 0
    )
    assert main(["validate-code-ir", str(ir_path), "--json"]) == 0


def test_contract_migration_command_requires_review_before_validation(tmp_path: Path) -> None:
    specs = tmp_path / "flow-ui-contract"
    (specs / "flows").mkdir(parents=True)
    (specs / "screens").mkdir()
    (specs / "flows" / "checkout.md").write_text(
        "---\nflow: checkout\ntitle: Checkout\n---\n\n# Checkout\n",
        encoding="utf-8",
    )
    (specs / "screens" / "checkout.md").write_text(
        "---\nscreen: checkout\nflow: checkout\ntitle: Checkout\n---\n\n# Checkout\n",
        encoding="utf-8",
    )
    contract_path = specs / "contract.json"

    assert (
        main(
            [
                "migrate-flow-md-to-contract-json",
                str(specs),
                "--out",
                str(contract_path),
                "--json",
            ]
        )
        == 0
    )
    assert main(["validate-flow-contract", str(contract_path), "--json"]) == 1


def test_validate_report_rejects_non_object_reports(tmp_path: Path) -> None:
    report_path = tmp_path / "compare-report.json"
    report_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")

    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 1


def test_report_schema_subset_fails_closed_on_unsupported_keywords() -> None:
    issues = _validate_json_schema_subset(
        {"status": "PASS"},
        {"type": "object", "properties": {"status": {"type": "string", "pattern": "^PASS$"}}},
        "$",
    )

    assert issues == [
        {
            "severity": "error",
            "path": "$.status.__schema__.pattern",
            "message": "unsupported schema keyword: pattern",
        }
    ]


def _contextualized_pen() -> dict:
    return {
        "version": "2.11",
        "children": [
            {
                "id": "screen",
                "type": "frame",
                "name": "Checkout",
                "width": 1440,
                "height": 900,
                "context": "semantic_id=checkout; role=screen; test_id=checkout-screen",
                "semantic": {"states": [{"name": "default"}, {"name": "success"}]},
                "children": [
                    {
                        "id": "title",
                        "type": "text",
                        "name": "Checkout",
                        "content": "Checkout",
                        "context": "semantic_id=checkout.title; role=text; binding=checkout.title; entity=checkout",
                    },
                    {
                        "id": "pay",
                        "type": "frame",
                        "name": "Pay",
                        "context": "semantic_id=checkout.pay; role=button; intent=submit_payment; binding=checkout.payment_method; entity=checkout; test_id=checkout-pay; action=submit_payment; permission=buyer_can_pay",
                    },
                ],
            }
        ],
    }
