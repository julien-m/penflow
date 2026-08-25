# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
from __future__ import annotations

import json
from pathlib import Path

import pytest

from penflow.cli import main
from penflow.contracts import code_ir_from_pen, validate_code_ir


def contextualized_pen() -> dict:
    return {
        "version": "2.11",
        "children": [
            {
                "id": "screen",
                "type": "frame",
                "name": "Checkout",
                "width": 390,
                "height": 844,
                "context": "semantic_id=checkout; role=screen; test_id=checkout-screen",
                "source_map": {"screen_spec": "flow-ui-contract/screens/checkout.md"},
                "semantic": {"states": [{"name": "default"}, {"name": "loading"}]},
                "children": [
                    {
                        "id": "title",
                        "type": "text",
                        "content": "Checkout",
                        "context": "semantic_id=checkout.title; role=text; binding=checkout.title",
                        "source_map": {"screen_spec": "flow-ui-contract/screens/checkout.md"},
                    },
                    {
                        "id": "payButton",
                        "type": "frame",
                        "name": "Pay",
                        "context": "semantic_id=checkout.pay; role=button; intent=submit_payment; binding=checkout.payment_method; entity=payment; test_id=checkout-pay",
                        "source_map": {
                            "flow_spec": "flow-ui-contract/flows/checkout.md",
                            "screen_spec": "flow-ui-contract/screens/checkout.md",
                        },
                        "semantic": {
                            "states": [
                                {"name": "enabled"},
                                {"name": "loading"},
                                {"name": "error", "message": "Card declined"},
                                {"name": "empty"},
                            ],
                            "validations": [{"rule": "payment_method_present"}],
                            "side_effects": [
                                {"effect": "create_payment_intent", "target": "payment"}
                            ],
                            "errors": [{"code": "payment_failed", "message": "Card declined"}],
                        },
                        "children": [
                            {
                                "id": "payLabel",
                                "type": "text",
                                "content": "Pay",
                                "context": "semantic_id=checkout.pay.label; role=text",
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


def test_code_ir_from_pen_preserves_flow_screen_hierarchy_and_business_context(
    tmp_path: Path,
) -> None:
    pen_path = write_json(tmp_path / "ui.pen", contextualized_pen())

    ir = code_ir_from_pen(pen_path, flow_id="checkout", flow_name="Checkout flow")
    screen = ir["screens"][0]
    pay = screen["root"]["children"][1]

    assert ir["kind"] == "penflow-code-ir"
    assert ir["source"] == "pencil-context"
    assert ir["flow"] == {"id": "checkout", "name": "Checkout flow"}
    assert screen["id"] == "checkout"
    assert screen["name"] == "Checkout"
    assert screen["test_id"] == "checkout-screen"
    assert pay["semantic_id"] == "checkout.pay"
    assert pay["pencil_node_id"] == "payButton"
    assert pay["path"] == "0.1"
    assert pay["role"] == "button"
    assert pay["type"] == "frame"
    assert pay["intent"] == "submit_payment"
    assert pay["binding"] == "checkout.payment_method"
    assert pay["entity"] == "payment"
    assert pay["test_id"] == "checkout-pay"
    assert pay["actions"] == [{"intent": "submit_payment", "entity": "payment"}]
    assert pay["validations"] == [{"rule": "payment_method_present"}]
    assert pay["side_effects"][0]["effect"] == "create_payment_intent"
    assert pay["states"] == [
        {"name": "enabled"},
        {"name": "loading"},
        {"name": "error", "message": "Card declined"},
        {"name": "empty"},
    ]
    assert pay["state_kinds"] == ["empty", "error", "loading"]
    assert pay["errors"] == [{"code": "payment_failed", "message": "Card declined"}]
    assert pay["source_map"]["pencil_node_id"] == "payButton"
    assert pay["source_map"]["semantic_id"] == "checkout.pay"
    assert pay["source_map"]["flow_spec"].endswith("flows/checkout.md")
    assert [child["semantic_id"] for child in pay["children"]] == ["checkout.pay.label"]
    assert ir["bindings"] == ["checkout.payment_method", "checkout.title"]
    assert ir["test_ids"] == ["checkout-pay", "checkout-screen"]


def test_code_ir_from_pen_is_deterministic(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", contextualized_pen())

    first = code_ir_from_pen(pen_path, flow_id="checkout", flow_name="Checkout flow")
    second = code_ir_from_pen(pen_path, flow_id="checkout", flow_name="Checkout flow")

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_code_ir_cli_from_context_pen_source(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", contextualized_pen())
    out_path = tmp_path / "code-ir.json"

    assert (
        main(
            [
                "code-ir",
                "--from-context",
                str(pen_path),
                "--flow-id",
                "checkout",
                "--flow-name",
                "Checkout flow",
                "--out",
                str(out_path),
                "--json",
            ]
        )
        == 0
    )
    ir = json.loads(out_path.read_text(encoding="utf-8"))

    assert ir["kind"] == "penflow-code-ir"
    assert ir["source"] == "pencil-context"
    assert ir["flow"]["id"] == "checkout"
    assert ir["flow"]["name"] == "Checkout flow"
    assert ir["screens"][0]["root"]["children"][1]["intent"] == "submit_payment"


def test_code_ir_cli_bytes_are_deterministic(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", contextualized_pen())
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"

    base_args = [
        "code-ir",
        "--from-context",
        str(pen_path),
        "--flow-id",
        "checkout",
        "--flow-name",
        "Checkout flow",
    ]
    assert main(base_args + ["--out", str(out_a)]) == 0
    assert main(base_args + ["--out", str(out_b)]) == 0
    assert out_a.read_bytes() == out_b.read_bytes()


def test_code_ir_source_map_back_references(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", contextualized_pen())
    ir = code_ir_from_pen(pen_path, flow_id="checkout", flow_name="Checkout flow")

    def _walk(node: dict) -> list[dict]:
        nodes = [node]
        for child in node.get("children", []) or []:
            nodes.extend(_walk(child))
        return nodes

    for screen in ir["screens"]:
        assert "pencil_node_id" in screen["source_map"]
        assert "pencil_path" in screen["source_map"]
        for node in _walk(screen["root"]):
            assert "pencil_node_id" in node["source_map"]
            assert "pencil_path" in node["source_map"]

    pay = ir["screens"][0]["root"]["children"][1]
    assert pay["source_map"]["semantic_id"] == "checkout.pay"
    assert pay["source_map"]["context"]["intent"] == "submit_payment"
    assert pay["source_map"]["flow_spec"].endswith("flows/checkout.md")
    assert pay["source_map"]["screen_spec"].endswith("screens/checkout.md")


def test_code_ir_preserves_physical_root_path_when_archive_precedes_active(
    tmp_path: Path,
) -> None:
    pen = contextualized_pen()
    active = pen["children"][0]
    active["penflow"] = {
        "lifecycle": {
            "schema_version": 1,
            "state": "active",
            "logical_screen_id": "checkout",
            "revision_id": "checkout-r2",
        }
    }
    archived = json.loads(json.dumps(active))
    archived["id"] = "checkout-r1"
    archived["penflow"]["lifecycle"].update({"state": "archive", "revision_id": "checkout-r1"})
    pen["children"] = [archived, active]
    pen_path = write_json(tmp_path / "ui.pen", pen)

    ir = code_ir_from_pen(pen_path, flow_id="checkout")

    assert ir["screens"][0]["source_map"]["pencil_path"] == "1"
    assert ir["screens"][0]["root"]["children"][1]["source_map"]["pencil_path"] == "1.1"


def test_code_ir_validates_against_schema(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", contextualized_pen())
    ir = code_ir_from_pen(pen_path, flow_id="checkout", flow_name="Checkout flow")
    issues = validate_code_ir(ir)
    errors = [issue for issue in issues if issue.get("severity") == "error"]
    assert errors == [], errors


def test_code_ir_cli_fails_when_pen_has_no_context(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    no_context_pen = {
        "version": "2.11",
        "children": [
            {
                "id": "blankScreen",
                "type": "frame",
                "name": "Blank",
                "width": 390,
                "height": 844,
                "children": [
                    {"id": "blankTitle", "type": "text", "content": "Hello"},
                ],
            }
        ],
    }
    pen_path = write_json(tmp_path / "ui.pen", no_context_pen)
    out_path = tmp_path / "code-ir.json"

    exit_code = main(
        [
            "code-ir",
            "--from-context",
            str(pen_path),
            "--out",
            str(out_path),
        ]
    )
    captured = capsys.readouterr()
    assert exit_code != 0
    assert "no Penflow context" in captured.err
    assert "blankScreen" in captured.err
    assert not out_path.exists()


def test_code_ir_cli_rejects_expected_tree_input_early(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    expected_tree = {
        "version": 1,
        "screens": [
            {
                "screen_id": "checkout",
                "root": {"id": "checkout", "role": "screen", "children": []},
            }
        ],
    }
    expected_path = write_json(tmp_path / "expected-ui-tree.json", expected_tree)
    out_path = tmp_path / "code-ir.json"

    exit_code = main(
        [
            "code-ir",
            "--from-context",
            str(expected_path),
            "--out",
            str(out_path),
            "--json",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "expects the contextualized .pen file" in captured.err
    assert "not expected-ui-tree.json" in captured.err
    assert not out_path.exists()


def test_code_ir_cli_accepts_optional_semantic_tree_and_context_map(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", contextualized_pen())
    semantic_tree_path = write_json(
        tmp_path / "semantic-ui-tree.json", {"flows": [], "screens": []}
    )
    context_map_path = write_json(tmp_path / "context-map.json", {"mappings": []})
    out_path = tmp_path / "code-ir.json"

    assert (
        main(
            [
                "code-ir",
                "--from-context",
                str(pen_path),
                "--semantic-tree",
                str(semantic_tree_path),
                "--context-map",
                str(context_map_path),
                "--flow-id",
                "checkout",
                "--out",
                str(out_path),
            ]
        )
        == 0
    )
    ir = json.loads(out_path.read_text(encoding="utf-8"))
    assert ir["inputs"]["semantic_tree"] == str(semantic_tree_path)
    assert ir["inputs"]["context_map"] == str(context_map_path)


def test_export_ir_legacy_path_still_works(tmp_path: Path) -> None:
    screen = {
        "id": "checkout",
        "viewport": {"width": 390, "height": 844},
        "components": [
            {"id": "title", "role": "text", "text": "Checkout", "binding": "checkout.title"},
            {
                "id": "pay",
                "role": "button",
                "text": "Pay",
                "intent": "submit_payment",
                "binding": "checkout.payment_method",
            },
        ],
    }
    screen_path = tmp_path / "screen.json"
    screen_path.write_text(json.dumps(screen), encoding="utf-8")
    out_path = tmp_path / "legacy-ir.json"

    assert main(["export-ir", str(screen_path), "--out", str(out_path), "--json"]) == 0
    ir = json.loads(out_path.read_text(encoding="utf-8"))
    assert ir["screen"] == "checkout"
    assert ir["viewport"] == {"width": 390, "height": 844}
    assert "components" in ir
    assert ir["expected_tree_source"] is False


def test_codegen_accepts_contextualized_code_ir_cli_output(tmp_path: Path) -> None:
    pen_path = write_json(tmp_path / "ui.pen", contextualized_pen())
    ir_path = tmp_path / "code-ir.json"

    assert (
        main(
            [
                "code-ir",
                "--from-context",
                str(pen_path),
                "--flow-id",
                "checkout",
                "--flow-name",
                "Checkout flow",
                "--out",
                str(ir_path),
            ]
        )
        == 0
    )

    outputs = {
        "react": tmp_path / "Checkout.jsx",
        "swiftui": tmp_path / "CheckoutView.swift",
        "rust": tmp_path / "checkout.rs",
    }
    for target, output in outputs.items():
        assert main(["codegen", target, str(ir_path), "--out", str(output)]) == 0

    assert 'data-penflow-id="checkout"' in outputs["react"].read_text(encoding="utf-8")
    assert "struct CheckoutView: View" in outputs["swiftui"].read_text(encoding="utf-8")
    assert "pub fn Checkout() -> Element" in outputs["rust"].read_text(encoding="utf-8")
