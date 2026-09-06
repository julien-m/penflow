"""Producer preparation is deterministic; certification never repairs missing IDs."""

from copy import deepcopy

from penflow.contract_preparation import prepare_contract_test_ids, contract_test_id_issues
from tests.contract_factory import valid_contract


def test_preparation_preserves_explicit_ids_and_fills_stable_missing_ids():
    contract = valid_contract()
    before = deepcopy(contract)
    prepared = prepare_contract_test_ids(contract)
    assert contract == before
    assert contract_test_id_issues(contract)
    assert contract_test_id_issues(prepared) == []
    assert prepare_contract_test_ids(prepared) == prepared
    for old, new in zip(contract["nodes"], prepared["nodes"]):
        if "test_id" in old:
            assert old["test_id"] == new["test_id"]
    reverse = deepcopy(contract)
    reverse["nodes"].reverse()
    assert {
        node["semantic_id"]: node["test_id"] for node in prepare_contract_test_ids(reverse)["nodes"]
    } == {node["semantic_id"]: node["test_id"] for node in prepared["nodes"]}


def test_explicit_collision_is_preserved_and_generated_id_disambiguated():
    contract = valid_contract()
    missing = next(node for node in contract["nodes"] if "test_id" not in node)
    contract["nodes"][0]["test_id"] = "pf-" + missing["semantic_id"]
    prepared = prepare_contract_test_ids(contract)
    assert prepared["nodes"][0]["test_id"] == contract["nodes"][0]["test_id"]
    assert contract_test_id_issues(prepared) == []
