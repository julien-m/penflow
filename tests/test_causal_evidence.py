# @spec(FR-006)
# @spec(FR-007)
# @spec(FR-008)
"""Adversarial C44 coverage for adapter-produced transition observations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from test_flow_contract_v2 import valid_contract, write_json

from penflow.causal_evidence import validate_causal_evidence
from penflow.cli import main


def _write_proof(
    path: Path,
    observation: dict[str, Any],
) -> dict[str, Any]:
    write_json(
        path,
        {
            "kind": "penflow-causal-runtime-receipt",
            "version": 1,
            "run_id": observation["run_id"],
            "transition_id": observation["transition_id"],
            "observation_id": observation["id"],
            "outcome": observation["outcome"],
            "adapter": {"name": "web-dom-adapter", "version": "1.0.0"},
            "surface": "web",
            "capture": {
                "kind": "runtime-state",
                "action": deepcopy(observation["action"]),
                "pre_state": deepcopy(observation["pre_state"]),
                "post_state": deepcopy(observation["post_state"]),
                "destination": deepcopy(observation["destination"]),
                "outcome": observation["outcome"],
            },
        },
    )
    return {
        "id": path.stem,
        "run_id": observation["run_id"],
        "kind": "runtime-state",
        "path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _bundle(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    contract_path = write_json(tmp_path / "contract.json", valid_contract())
    success_observation: dict[str, Any] = {
        "id": "observe-success",
        "transition_id": "payment_success",
        "run_id": "run-proof-success",
        "outcome": "success",
        "action": {
            "id": "submit_payment",
            "test_id": "checkout-pay",
            "visible": True,
            "event": "user clicked Pay",
        },
        "pre_state": {
            "screen": "checkout",
            "state": "default",
            "value": "payment pending",
        },
        "post_state": {
            "screen": "checkout",
            "state": "success",
            "value": "payment complete",
        },
        "destination": {"screen": "checkout", "state": "success"},
    }
    error_observation: dict[str, Any] = {
        "id": "observe-error",
        "transition_id": "payment_error",
        "run_id": "run-proof-error",
        "outcome": "error",
        "action": {
            "id": "submit_payment",
            "test_id": "checkout-pay",
            "visible": True,
            "event": "user clicked Pay",
        },
        "pre_state": {
            "screen": "checkout",
            "state": "default",
            "value": "payment pending",
        },
        "post_state": {
            "screen": "checkout",
            "state": "error",
            "value": "payment rejected",
        },
        "destination": {"screen": "checkout", "state": "error"},
    }
    success_observation["evidence"] = [
        _write_proof(tmp_path / "proof-success.json", success_observation)
    ]
    error_observation["evidence"] = [_write_proof(tmp_path / "proof-error.json", error_observation)]
    evidence: dict[str, Any] = {
        "kind": "penflow-causal-transition-evidence",
        "version": 1,
        "contract": {
            "id": "checkout-contract",
            "version": 2,
            "sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        },
        "runs": [
            {
                "id": "run-proof-success",
                "adapter": {"name": "web-dom-adapter", "version": "1.0.0"},
                "surface": "web",
            },
            {
                "id": "run-proof-error",
                "adapter": {"name": "web-dom-adapter", "version": "1.0.0"},
                "surface": "web",
            },
        ],
        "observations": [success_observation, error_observation],
    }
    evidence_path = write_json(tmp_path / "causal-evidence.json", evidence)
    return contract_path, evidence_path, evidence


def _codes(report: dict[str, Any]) -> set[str]:
    return {issue["code"] for issue in report["issues"]}


def test_valid_source_and_cli_bundle_passes(tmp_path: Path) -> None:
    contract_path, evidence_path, _ = _bundle(tmp_path)

    report = validate_causal_evidence(contract_path, evidence_path)

    assert report["status"] == "PASS"
    assert report["summary"] == {
        "causal_transitions": 2,
        "runs": 2,
        "observations": 2,
        "issues": 0,
    }
    assert main(["validate-causal-evidence", str(contract_path), str(evidence_path), "--json"]) == 0


Mutation = Callable[[dict[str, Any]], None]


def _missing_action(evidence: dict[str, Any]) -> None:
    del evidence["observations"][0]["action"]


def _missing_value(evidence: dict[str, Any]) -> None:
    del evidence["observations"][0]["post_state"]["value"]


def _missing_destination(evidence: dict[str, Any]) -> None:
    del evidence["observations"][0]["destination"]


def _default_to_default(evidence: dict[str, Any]) -> None:
    evidence["observations"][0]["post_state"] = deepcopy(evidence["observations"][0]["pre_state"])
    evidence["observations"][0]["destination"] = {"screen": "checkout", "state": "default"}


def _static_proof(evidence: dict[str, Any]) -> None:
    evidence["observations"][0]["evidence"][0]["kind"] = "static"


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (_missing_action, "causal.action.missing"),
        (_missing_value, "causal.state.post_missing"),
        (_missing_destination, "causal.destination.missing"),
        (_default_to_default, "causal.state.default_unchanged"),
        (_static_proof, "causal.proof.static_generic"),
    ],
)
def test_causal_mutations_fail_closed(
    tmp_path: Path,
    mutate: Mutation,
    expected_code: str,
) -> None:
    contract_path, evidence_path, evidence = _bundle(tmp_path)
    mutate(evidence)
    write_json(evidence_path, evidence)

    report = validate_causal_evidence(contract_path, evidence_path)

    assert report["status"] == "FAIL"
    assert expected_code in _codes(report)


def test_contract_digest_and_run_binding_fail_closed(tmp_path: Path) -> None:
    contract_path, evidence_path, evidence = _bundle(tmp_path)
    evidence["contract"]["sha256"] = "0" * 64
    evidence["observations"][0]["evidence"][0]["run_id"] = "run-proof-error"
    write_json(evidence_path, evidence)

    codes = _codes(validate_causal_evidence(contract_path, evidence_path))

    assert "causal.contract.digest_mismatch" in codes
    assert "causal.run.mismatch" in codes


def test_each_fanout_outcome_requires_distinct_proof(tmp_path: Path) -> None:
    contract_path, evidence_path, evidence = _bundle(tmp_path)
    evidence["observations"][1]["evidence"] = deepcopy(evidence["observations"][0]["evidence"])
    write_json(evidence_path, evidence)

    codes = _codes(validate_causal_evidence(contract_path, evidence_path))

    assert "causal.proof.reused" in codes
    assert "causal.run.mismatch" in codes


def test_each_fanout_outcome_requires_distinct_receipt_digest(tmp_path: Path) -> None:
    contract_path, evidence_path, evidence = _bundle(tmp_path)
    first_receipt = evidence["observations"][0]["evidence"][0]
    second_receipt = evidence["observations"][1]["evidence"][0]
    first_path = tmp_path / first_receipt["path"]
    second_path = tmp_path / second_receipt["path"]
    second_path.write_bytes(first_path.read_bytes())
    second_receipt["sha256"] = hashlib.sha256(second_path.read_bytes()).hexdigest()
    write_json(evidence_path, evidence)

    codes = _codes(validate_causal_evidence(contract_path, evidence_path))

    assert "causal.proof.digest_reused" in codes


def test_runtime_receipt_rejects_arbitrary_prose_with_runtime_label(tmp_path: Path) -> None:
    contract_path, evidence_path, evidence = _bundle(tmp_path)
    receipt = evidence["observations"][0]["evidence"][0]
    receipt_path = tmp_path / receipt["path"]
    receipt_path.write_text("Static generic contract prose only\n", encoding="utf-8")
    receipt["sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    write_json(evidence_path, evidence)

    codes = _codes(validate_causal_evidence(contract_path, evidence_path))

    assert "causal.proof.payload_invalid" in codes


def test_runtime_receipt_payload_is_closed(tmp_path: Path) -> None:
    contract_path, evidence_path, evidence = _bundle(tmp_path)
    receipt = evidence["observations"][0]["evidence"][0]
    receipt_path = tmp_path / receipt["path"]
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["untrusted"] = "prose"
    write_json(receipt_path, payload)
    receipt["sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    write_json(evidence_path, evidence)

    codes = _codes(validate_causal_evidence(contract_path, evidence_path))

    assert "causal.proof.payload_schema" in codes


def test_runtime_receipt_payload_is_observation_bound(tmp_path: Path) -> None:
    contract_path, evidence_path, evidence = _bundle(tmp_path)
    receipt = evidence["observations"][0]["evidence"][0]
    receipt_path = tmp_path / receipt["path"]
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["transition_id"] = "payment_error"
    write_json(receipt_path, payload)
    receipt["sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    write_json(evidence_path, evidence)

    codes = _codes(validate_causal_evidence(contract_path, evidence_path))

    assert "causal.proof.payload_binding_mismatch" in codes


def test_runtime_receipt_snapshot_rejects_static_value_only_capture(tmp_path: Path) -> None:
    contract_path, evidence_path, evidence = _bundle(tmp_path)
    receipt = evidence["observations"][0]["evidence"][0]
    receipt_path = tmp_path / receipt["path"]
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["capture"] = {
        "kind": "runtime-state",
        "value": "Static generic contract/spec prose only",
    }
    write_json(receipt_path, payload)
    receipt["sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    write_json(evidence_path, evidence)

    codes = _codes(validate_causal_evidence(contract_path, evidence_path))

    assert "causal.proof.payload_schema" in codes


def test_runtime_receipt_snapshot_rejects_error_post_state_for_success(
    tmp_path: Path,
) -> None:
    contract_path, evidence_path, evidence = _bundle(tmp_path)
    receipt = evidence["observations"][0]["evidence"][0]
    receipt_path = tmp_path / receipt["path"]
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    payload["capture"]["post_state"] = deepcopy(evidence["observations"][1]["post_state"])
    write_json(receipt_path, payload)
    receipt["sha256"] = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    write_json(evidence_path, evidence)

    codes = _codes(validate_causal_evidence(contract_path, evidence_path))

    assert "causal.proof.snapshot_mismatch" in codes


def test_missing_fanout_outcome_is_unproven(tmp_path: Path) -> None:
    contract_path, evidence_path, evidence = _bundle(tmp_path)
    evidence["observations"] = evidence["observations"][:1]
    write_json(evidence_path, evidence)

    report = validate_causal_evidence(contract_path, evidence_path)

    assert "causal.outcome.unproven" in _codes(report)
    assert main(["validate-causal-evidence", str(contract_path), str(evidence_path)]) == 1
