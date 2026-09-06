"""Logical screen identity remains independent of its root semantic identity."""

from copy import deepcopy
from pathlib import Path

from penflow.compare import compare_trees
from penflow.flow_contract import validate_flow_contract_v2
from penflow.verification_design import _expected
from penflow.verification_files import InputReader
from penflow.verification_snapshot import VerificationSnapshot
from tests.contract_factory import valid_contract


def test_c51_exports_contract_screen_identity(tmp_path: Path) -> None:
    """A valid distinct semantic root cannot rename its owning screen or hide a wrong screen."""
    contract = valid_contract()
    root = next(
        node for node in contract["nodes"] if node["id"] == contract["screens"][0]["root_node"]
    )
    root["semantic_id"] = "checkout.screenroot"
    assert validate_flow_contract_v2(contract) == []
    values = {
        "pen": {
            "children": [
                {
                    "id": "native",
                    "type": "frame",
                    "width": 400,
                    "height": 300,
                    "context": "classification=semantic; semantic_id=checkout.screenroot; role=screen; test_id=screen",
                }
            ]
        }
    }
    snapshot = VerificationSnapshot(
        InputReader(tmp_path),
        tmp_path,
        contract,
        {},
        {},
        policy={"native_geometry": "not_applicable"},
    )
    assert _expected(snapshot, values, True) == []
    expected = values["expected"]
    assert expected["screens"][0]["screen_id"] == "checkout"
    assert compare_trees(expected, deepcopy(expected))["issues"] == []
    actual = deepcopy(expected)
    actual["screens"][0]["screen_id"] = "checkout.screenroot"
    assert compare_trees(expected, actual)["issues"]
