# @spec AC-012: Given a required action or outcome, when causal metadata/evidence is removed or applicability is weakened without a revised validated reference, then the obligation denominator does not shrink to permit PASS. — .specs/features/077-complete-verification-workflow/spec.md#ac-012
# @spec AC-011: Given validated upstream requirements (LiveSpec FR/AC or Brainstorm frozen product contract) and a canonical contract revision, when obligations are derived, then each applicable requirement maps to contract and expected result or produces an unmapped requirement finding, without a manual second ledger or nonexistent upstream prerequisites. — .specs/features/077-complete-verification-workflow/spec.md#ac-011
"""Probe frozen Brainstorm authority without mocking or regenerating its receipts."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from penflow.flow_contract import validate_flow_contract_v2
from penflow.product_sources import load_brainstorm_requirements
from penflow.verification_files import InputReader, VerificationInputError

FIXTURE = Path(__file__).parent / "fixtures" / "c51-brainstorm-source"
MULTI_FIXTURE = Path(__file__).parent / "fixtures" / "c51-brainstorm-multi-source"
WORKSPACE = Path("handoff/penflow")
CONTRACT = WORKSPACE / "flow-ui-contract/contract.json"
PRODUCT = WORKSPACE / "product-contract"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def _copy_consumer(fixture: Path, tmp_path: Path) -> Path:
    """Copy immutable CLI inputs, rebasing only the caller's C20 source paths."""
    provenance = _json(fixture / "provenance.json")
    for item in provenance["files"]:
        assert hashlib.sha256((fixture / item["path"]).read_bytes()).hexdigest() == item["sha256"]
    root = tmp_path / "consumer"
    shutil.copytree(fixture / "handoff", root / "handoff")
    contract = _json(root / CONTRACT)
    original = Path(provenance["source_root"])
    for reference in contract["requirements"]["source_refs"]:
        reference["path"] = str(root.resolve() / Path(reference["path"]).relative_to(original))
    _write(root / CONTRACT, contract)
    return root


@pytest.fixture
def consumer(tmp_path: Path) -> Path:
    return _copy_consumer(FIXTURE, tmp_path)


@pytest.fixture
def multi_consumer(tmp_path: Path) -> Path:
    return _copy_consumer(MULTI_FIXTURE, tmp_path)


def _load(root: Path) -> dict[str, Any]:
    reader = InputReader(root)
    result = load_brainstorm_requirements(reader, root / WORKSPACE)
    reader.recheck()
    return result


# @spec FR-007 AC-011: frozen requirement denominator survives aliases and substitutions.
# — .specs/features/077-complete-verification-workflow/spec.md#fr-007
def test_real_frozen_source_accepts_aliases_and_additional_surface_binding(consumer: Path) -> None:
    result = _load(consumer)
    assert result["product"]["surfaces"][0]["id"] != result["contract"]["screens"][0]["id"]
    assert len(result["projection"]["requirements"]) == 4
    assert len(result["projection"]["bindings"]) == 5
    assert result["projection"]["uncovered"] == []
    assert result["contract"]["actions"] == []


@pytest.mark.parametrize(
    "prefix", ["brainstorm:flow:", "brainstorm:surface:", "brainstorm:state:", "brainstorm:return:"]
)
def test_removing_source_binding_keeps_requirement_mandatory(consumer: Path, prefix: str) -> None:
    contract = _json(consumer / CONTRACT)
    contract["requirements"]["bindings"] = [
        item
        for item in contract["requirements"]["bindings"]
        if not item["requirement_id"].startswith(prefix)
    ]
    _write(consumer / CONTRACT, contract)
    with pytest.raises(VerificationInputError, match="product.requirements.uncovered"):
        _load(consumer)


def test_every_requirement_mapped_to_root_does_not_substitute_for_state_and_return(
    consumer: Path,
) -> None:
    contract = _json(consumer / CONTRACT)
    identifiers = sorted({item["requirement_id"] for item in contract["requirements"]["bindings"]})
    contract["requirements"]["bindings"] = [
        {"requirement_id": identifier, "obligation_id": "node:alias-screen"}
        for identifier in identifiers
    ]
    assert not validate_flow_contract_v2(contract)
    _write(consumer / CONTRACT, contract)
    with pytest.raises(VerificationInputError, match="product.mapping.state_owner"):
        _load(consumer)


@pytest.mark.parametrize(
    "name",
    [
        "product-contract.json",
        "product-contract.md",
        "product-contract.freeze.json",
        "product-contract.accepted.json",
    ],
)
def test_changed_authority_bytes_cannot_reuse_prior_source_references(
    consumer: Path, name: str
) -> None:
    path = consumer / PRODUCT / name
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(VerificationInputError):
        _load(consumer)


def test_changed_immutable_history_fails_even_when_current_product_is_untouched(
    consumer: Path,
) -> None:
    history = sorted((consumer / PRODUCT / ".freeze-history").glob("*.json"))
    history[0].write_bytes(history[0].read_bytes() + b"\n")
    with pytest.raises(VerificationInputError, match="input.stale"):
        _load(consumer)


def test_wrong_system_return_event_cannot_replace_frozen_exit(consumer: Path) -> None:
    contract = _json(consumer / CONTRACT)
    contract["system_returns"][0]["event"] = "close"
    assert not validate_flow_contract_v2(contract)
    _write(consumer / CONTRACT, contract)
    with pytest.raises(VerificationInputError, match="product.mapping.system_return_source"):
        _load(consumer)


def test_c20_surface_cannot_differ_from_explicit_frozen_surface(consumer: Path) -> None:
    contract = _json(consumer / CONTRACT)
    contract["screens"][0]["surface"] = "web-mobile"
    assert not validate_flow_contract_v2(contract)
    _write(consumer / CONTRACT, contract)
    with pytest.raises(VerificationInputError, match="product.mapping.surface"):
        _load(consumer)


def test_one_frozen_flow_can_bind_roots_of_both_own_screens(multi_consumer: Path) -> None:
    result = _load(multi_consumer)
    assert len(result["projection"]["requirements"]) == 7
    assert len(result["projection"]["bindings"]) == 10
    assert len(result["contract"]["screens"]) == 2
    assert len(result["contract"]["flows"]) == 1
    assert result["projection"]["uncovered"] == []


def test_flow_mapping_does_not_weaken_its_frozen_entry_screen(multi_consumer: Path) -> None:
    contract = _json(multi_consumer / CONTRACT)
    contract["flows"][0]["entry_screen"] = "alias-secondary-screen"
    assert not validate_flow_contract_v2(contract)
    _write(multi_consumer / CONTRACT, contract)
    with pytest.raises(VerificationInputError, match="product.mapping.entry"):
        _load(multi_consumer)


def test_source_state_cannot_bind_a_state_of_another_surface(multi_consumer: Path) -> None:
    contract = _json(multi_consumer / CONTRACT)
    for binding in contract["requirements"]["bindings"]:
        if binding["requirement_id"].startswith("brainstorm:state:product-secondary-page:"):
            binding["obligation_id"] = "state:alias-screen:alias-state"
    assert not validate_flow_contract_v2(contract)
    _write(multi_consumer / CONTRACT, contract)
    with pytest.raises(VerificationInputError, match="product.mapping.state_owner"):
        _load(multi_consumer)


def test_source_return_cannot_move_to_another_surface(multi_consumer: Path) -> None:
    contract = _json(multi_consumer / CONTRACT)
    contract["system_returns"][1]["screen_id"] = "alias-screen"
    assert not validate_flow_contract_v2(contract)
    _write(multi_consumer / CONTRACT, contract)
    with pytest.raises(VerificationInputError, match="product.mapping.return_owner"):
        _load(multi_consumer)


def test_historical_freeze_bytes_remain_required_after_approved_change(
    multi_consumer: Path,
) -> None:
    original_freeze = _json(FIXTURE / PRODUCT / "product-contract.accepted.json")["path"]
    path = multi_consumer / PRODUCT / original_freeze
    assert path.is_file()
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(VerificationInputError, match="input.stale"):
        _load(multi_consumer)


@pytest.mark.parametrize("missing", ["path", "sha256", "both"])
def test_malformed_accepted_reference_is_a_structured_input_error(
    consumer: Path, missing: str
) -> None:
    path = consumer / PRODUCT / "product-contract.accepted.json"
    value = _json(path)
    if missing == "both":
        value.clear()
    else:
        del value[missing]
    _write(path, value)
    with pytest.raises(VerificationInputError):
        _load(consumer)
