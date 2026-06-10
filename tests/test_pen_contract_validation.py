# @spec(AC-011)
# @spec(FR-007)
from __future__ import annotations

import json
from pathlib import Path

from penflow.cli import main
from tests.test_flow_contract_v2 import valid_contract, write_json


def contextualized_pen() -> dict:
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


def test_validate_pen_contract_checks_context_against_contract_ids(tmp_path: Path) -> None:
    contract_path = write_json(tmp_path / "contract.json", valid_contract())
    pen_path = write_json(tmp_path / "ui.pen", contextualized_pen())

    assert main(["validate-pen", str(pen_path), "--contract", str(contract_path), "--json"]) == 0


def test_validate_pen_contract_fails_on_missing_semantic_id(tmp_path: Path) -> None:
    contract_path = write_json(tmp_path / "contract.json", valid_contract())
    pen = contextualized_pen()
    pen["children"][0]["children"][0]["context"] = (
        "semantic_id=checkout.missing; role=button; intent=submit_payment"
    )
    pen_path = write_json(tmp_path / "ui.pen", pen)

    assert main(["validate-pen", str(pen_path), "--contract", str(contract_path), "--json"]) == 1


def test_validate_pen_contract_fails_when_required_contract_node_is_absent(tmp_path: Path) -> None:
    contract_path = write_json(tmp_path / "contract.json", valid_contract())
    pen = contextualized_pen()
    pen["children"][0]["children"] = pen["children"][0]["children"][1:]
    pen_path = write_json(tmp_path / "ui.pen", pen)

    assert main(["validate-pen", str(pen_path), "--contract", str(contract_path), "--json"]) == 1


def test_validate_pen_contract_fails_on_unknown_screen_state(tmp_path: Path) -> None:
    contract_path = write_json(tmp_path / "contract.json", valid_contract())
    pen = contextualized_pen()
    pen["children"][0]["semantic"]["states"].append({"name": "missing"})
    pen_path = write_json(tmp_path / "ui.pen", pen)

    assert main(["validate-pen", str(pen_path), "--contract", str(contract_path), "--json"]) == 1


def test_validate_pen_contract_validates_contract_before_context(tmp_path: Path) -> None:
    contract = valid_contract()
    contract["actions"][0]["mutation"] = "missing_mutation"
    contract_path = write_json(tmp_path / "contract.json", contract)
    pen_path = write_json(tmp_path / "ui.pen", contextualized_pen())

    assert main(["validate-pen", str(pen_path), "--contract", str(contract_path), "--json"]) == 1


def test_code_ir_contract_preserves_v2_business_semantics(tmp_path: Path) -> None:
    contract_path = write_json(tmp_path / "contract.json", valid_contract())
    pen_path = write_json(tmp_path / "ui.pen", contextualized_pen())
    out = tmp_path / "code-ir.json"

    assert (
        main(
            [
                "code-ir",
                "--from-context",
                str(pen_path),
                "--contract",
                str(contract_path),
                "--out",
                str(out),
                "--json",
            ]
        )
        == 0
    )
    ir = json.loads(out.read_text(encoding="utf-8"))

    assert ir["contract"]["contract_id"] == "checkout-contract"
    assert ir["contract"]["actions"][0]["id"] == "submit_payment"
    assert ir["contract"]["mutations"][0]["id"] == "create_payment"
    assert main(["validate-code-ir", str(out), "--json"]) == 0
