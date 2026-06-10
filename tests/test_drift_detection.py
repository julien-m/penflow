# @spec(AC-007)
from __future__ import annotations

import json
from pathlib import Path

from penflow.cli import main
from penflow.drift import detect_drift


def aligned_tree() -> dict:
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
                "transitions": [],
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


def aligned_pen() -> dict:
    return {
        "version": "2.11",
        "children": [
            {
                "id": "screen",
                "type": "frame",
                "name": "Checkout",
                "context": "semantic_id=checkout; role=screen",
                "children": [
                    {
                        "id": "title",
                        "type": "text",
                        "content": "Checkout",
                        "context": "semantic_id=checkout.title; role=text",
                    },
                    {
                        "id": "payButton",
                        "type": "frame",
                        "name": "Pay",
                        "context": "semantic_id=checkout.pay; role=button; intent=submit_payment",
                        "children": [
                            {
                                "id": "payButtonLabel",
                                "type": "text",
                                "content": "Pay",
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


def write_specs(root: Path, *, clarification: bool = False, screen_id: str = "checkout") -> Path:
    specs_dir = root / "flow-ui-contract"
    flows_dir = specs_dir / "flows"
    screens_dir = specs_dir / "screens"
    flows_dir.mkdir(parents=True)
    screens_dir.mkdir()
    marker = "[NEEDS CLARIFICATION]" if clarification else "submit_payment"
    (flows_dir / "checkout.md").write_text(
        "\n".join(
            [
                "---",
                "flow: checkout",
                "title: Checkout",
                "status: reviewed",
                "---",
                "",
                "# Flow Checkout",
                "",
                "## Primary Actor",
                "",
                "shopper",
                "",
                "## User Scenarios & Testing",
                "",
                f"- Business intent: {marker}",
            ]
        ),
        encoding="utf-8",
    )
    (screens_dir / f"{screen_id}.md").write_text(
        "\n".join(
            [
                "---",
                f"screen: {screen_id}",
                "flow: checkout",
                "title: Checkout",
                "status: reviewed",
                "sourceNodeId: screen",
                "---",
                "",
                "# Screen Checkout",
                "",
                "## Displayed Data",
                "",
                "- Checkout",
                "",
                "## Actions",
                "",
                "| Element | Type | Effect |",
                "|---|---|---|",
                f"| Pay | button | {marker} |",
                "",
                "## UI States",
                "",
                "default",
            ]
        ),
        encoding="utf-8",
    )
    return specs_dir


def test_detect_drift_reports_clean_alignment_deterministically(tmp_path: Path) -> None:
    specs_dir = write_specs(tmp_path)
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", aligned_tree())
    pen_path = write_json(tmp_path / "ui.pen", aligned_pen())
    first_path = tmp_path / "first-drift.json"
    second_path = tmp_path / "second-drift.json"
    markdown_path = tmp_path / "drift.md"

    report = detect_drift(specs_dir, tree_path, pen_path, first_path, markdown_path=markdown_path)
    detect_drift(specs_dir, tree_path, pen_path, second_path)

    assert report["status"] == "PASS"
    assert report["issues"] == []
    assert first_path.read_bytes() == second_path.read_bytes()
    assert markdown_path.read_text(encoding="utf-8").startswith("# Drift Report\n\nStatus: PASS")


def test_detect_drift_reports_missing_stale_obsolete_uncovered_and_clarifications(
    tmp_path: Path,
) -> None:
    specs_dir = write_specs(tmp_path, clarification=True, screen_id="billing")
    tree = aligned_tree()
    tree["screens"][0]["root"]["children"].append(
        {
            "semantic_id": "checkout.help",
            "role": "text",
            "text": "Need help?",
            "source_map": {"screen_spec": "flow-ui-contract/screens/checkout.md"},
        }
    )
    pen = aligned_pen()
    pen["children"][0]["children"].extend(
        [
            {
                "id": "legacyContext",
                "type": "text",
                "content": "Legacy",
                "context": "semantic_id=checkout.legacy; role=text",
            },
            {"id": "promo", "type": "text", "content": "Promo"},
        ]
    )
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", tree)
    pen_path = write_json(tmp_path / "ui.pen", pen)
    report_path = tmp_path / "drift-report.json"
    markdown_path = tmp_path / "drift-report.md"

    report = detect_drift(specs_dir, tree_path, pen_path, report_path, markdown_path=markdown_path)
    codes = {issue["code"] for issue in report["issues"]}

    # Feature 049: blocking codes are present, so the report status is BLOCKED.
    assert report["status"] == "BLOCKED"
    assert {
        "drift.semantic_node_missing_in_pen",
        "drift.spec_screen_not_in_tree",
        "drift.tree_screen_missing_spec",
        "drift.pencil_context_obsolete",
        "drift.mockup_node_uncovered",
        "drift.clarification_marker",
    } <= codes
    assert any(issue.get("semantic_id") == "checkout.help" for issue in report["issues"])
    assert any(issue.get("pencil_node_id") == "legacyContext" for issue in report["issues"])
    blocking_by_code = {issue["code"]: issue["blocking"] for issue in report["issues"]}
    assert blocking_by_code["drift.semantic_node_missing_in_pen"] is True
    assert blocking_by_code["drift.pencil_context_obsolete"] is True
    assert blocking_by_code["drift.clarification_marker"] is True
    assert blocking_by_code["drift.mockup_node_uncovered"] is False
    assert report["summary"]["blocking"] == sum(
        1 for issue in report["issues"] if issue["blocking"]
    )
    assert report["summary"]["blocking"] > 0
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "drift.semantic_node_missing_in_pen" in markdown
    assert "| Blocking |" in markdown


def test_detect_drift_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    specs_dir = write_specs(tmp_path)
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", aligned_tree())
    pen_path = write_json(tmp_path / "ui.pen", aligned_pen())
    report_path = tmp_path / "drift-report.json"
    markdown_path = tmp_path / "drift-report.md"

    assert (
        main(
            [
                "detect-drift",
                str(specs_dir),
                str(tree_path),
                str(pen_path),
                "--out",
                str(report_path),
                "--markdown",
                str(markdown_path),
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["kind"] == "penflow-drift-report"
    assert report["status"] == "PASS"
    assert markdown_path.exists()


def test_detect_drift_reports_nested_unmapped_containers(tmp_path: Path) -> None:
    specs_dir = write_specs(tmp_path)
    tree_path = write_json(tmp_path / "semantic-ui-tree.json", aligned_tree())
    pen = aligned_pen()
    pay_button = pen["children"][0]["children"][1]
    pay_button["children"].append(
        {
            "id": "nestedPromo",
            "type": "frame",
            "name": "Promo",
            "children": [{"id": "nestedPromoLabel", "type": "text", "content": "Promo"}],
        }
    )
    pen_path = write_json(tmp_path / "ui.pen", pen)

    report = detect_drift(specs_dir, tree_path, pen_path, tmp_path / "drift-report.json")

    assert report["status"] == "DRIFT"
    assert any(issue.get("pencil_node_id") == "nestedPromo" for issue in report["issues"])
