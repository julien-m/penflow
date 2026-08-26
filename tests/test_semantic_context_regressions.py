# @spec FR-016: AFP-01 through AFP-12 — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-016
"""Named anti-false-PASS regressions for exhaustive semantic context."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from penflow.flow_contract import validate_flow_contract_v2
from penflow.flow_docs import check_generated_docs, export_flow_docs
from penflow.semantic_context_coverage import audit_semantic_context
from tests.test_semantic_context_coverage import _contract, _pen, _semantic


def _coverage(pen: dict, contract: dict | None = None) -> dict:
    return audit_semantic_context(
        contract or _contract(),
        pen,
        contract_path="flow-ui-contract/contract.json",
        pen_path="ui.pen",
    )


def _codes(contract: dict) -> set[str]:
    return {issue["code"] for issue in validate_flow_contract_v2(contract)}


def test_afp_01_extra_explicit_semantic_button_fails_exactly_once() -> None:
    pen = _pen()
    pen["children"][0]["children"].append(
        _semantic("other-pay", "checkout.other-pay", "other-pay", "button")
    )

    report = _coverage(pen)

    findings = report["buckets"]["pencil_missing_in_contract"]
    assert [item["code"] for item in findings] == ["pencil.semantic_unknown"]
    assert findings[0]["semantic_id"] == "checkout.other-pay"


def test_afp_02_unclassified_zoom_icon_fails_without_visual_inference() -> None:
    pen = _pen()
    pen["children"][0]["children"].append(
        {"id": "zoom", "type": "icon_font", "name": "Zoom", "fill": "#000"}
    )

    report = _coverage(pen)

    assert [item["code"] for item in report["buckets"]["pencil_unclassified"]] == [
        "pencil.node_unclassified"
    ]


def test_afp_03_decorative_icon_with_anchored_owner_passes() -> None:
    report = _coverage(_pen())

    assert report["status"] == "PASS"
    assert [item["node_id"] for item in report["buckets"]["decorative_exclusions"]] == ["pay-icon"]


def test_afp_04_internal_text_inheriting_from_button_passes() -> None:
    report = _coverage(_pen())

    assert report["status"] == "PASS"
    assert [item["node_id"] for item in report["buckets"]["valid_inheritance"]] == ["pay-label"]


def test_afp_05_unknown_pencil_semantic_id_fails_canonically() -> None:
    pen = _pen()
    pen["children"][0]["children"].append(_semantic("ghost", "checkout.ghost", "ghost", "text"))

    report = _coverage(pen)

    assert [item["code"] for item in report["buckets"]["pencil_missing_in_contract"]] == [
        "pencil.semantic_unknown"
    ]


def test_afp_06_missing_action_destination_fails_closed() -> None:
    contract = _contract()
    contract["actions"][0]["destination"] = {"screen": "missing", "state": "missing"}

    assert "destination.reference_missing" in _codes(contract)


def test_afp_07_missing_binding_field_fails_closed() -> None:
    contract = _contract()
    contract["actions"][0]["binding_ref"] = {"entity": "checkout", "field": "missing"}

    assert "binding.field_missing" in _codes(contract)


def test_afp_08_list_without_repeat_model_fails_closed() -> None:
    contract = _contract()
    contract["nodes"][2]["role"] = "list"

    assert "list.model_incomplete" in _codes(contract)


def test_afp_09_duplicate_functional_semantic_id_fails_once() -> None:
    pen = _pen()
    duplicate = copy.deepcopy(pen["children"][0]["children"][1])
    duplicate["id"] = "pay-duplicate"
    duplicate["context"]["test_id"] = "checkout-pay-duplicate"
    pen["children"][0]["children"].append(duplicate)

    report = _coverage(pen)

    duplicates = [
        item
        for item in report["buckets"]["reference_invalid"]
        if item["code"] == "pencil.semantic_duplicate"
    ]
    assert len(duplicates) == 1
    assert duplicates[0]["node_id"] == "pay-duplicate"


def test_afp_10_static_screen_with_interactive_control_fails() -> None:
    contract = _contract()
    contract["screens"][0].update({"static": True, "static_reason": "system_surface"})

    assert "screen.static_interactive" in _codes(contract)


def test_afp_11_empty_generated_docs_directory_fails(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps(_contract()), encoding="utf-8")
    output = tmp_path / "flow-ui-contract"
    (output / "flows").mkdir(parents=True)

    report = check_generated_docs(contract, output, explicit=False)

    assert [issue["code"] for issue in report["issues"]] == ["docs.empty"]


def test_afp_12_obsolete_contract_hash_fails_without_rewrite(tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps(_contract(), sort_keys=True), encoding="utf-8")
    output = tmp_path / "flow-ui-contract"
    export_flow_docs(contract, output)
    before = (output / "generated-docs.json").read_bytes()
    changed = _contract()
    changed["contract_id"] = "changed-contract"
    contract.write_text(json.dumps(changed, sort_keys=True), encoding="utf-8")

    report = check_generated_docs(contract, output, explicit=True)

    assert [issue["code"] for issue in report["issues"]] == ["docs.contract_stale"]
    assert (output / "generated-docs.json").read_bytes() == before
