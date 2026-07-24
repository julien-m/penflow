# @spec(FR-006)
# @spec(FR-007)
# @spec(FR-008)
"""Validate adapter-produced causal transition evidence without running a UI.

External runtime adapters own capture. Penflow consumes a local, content-bound
artifact and proves that each declared causal transition has an observable
user action, matching pre/post observations, an effective destination/state
change, and an independent run-bound receipt for every fan-out outcome.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .flow_contract import load_flow_contract_v2, validate_flow_contract_v2
from .schema_cache import validator_for

EVIDENCE_KIND = "penflow-causal-transition-evidence"
EVIDENCE_VERSION = 1
RUNTIME_RECEIPT_KINDS = {"runtime-event", "runtime-state", "runtime-screenshot"}
_SCHEMA = "causal-transition-evidence.schema.json"
_RUNTIME_RECEIPT_SCHEMA = "causal-runtime-receipt.schema.json"


def validate_causal_evidence(
    contract_path: str | Path,
    evidence_path: str | Path,
) -> dict[str, Any]:
    """Validate one causal evidence bundle against its exact flow contract.

    Args:
        contract_path: Strict v2 `contract.json` whose bytes are digest-bound.
        evidence_path: Adapter-produced causal evidence JSON.

    Returns:
        A deterministic report with `PASS` only when every causal transition
        is independently observed and every local receipt is content-bound.

    Raises:
        FileNotFoundError: If either input file is absent.
        json.JSONDecodeError: If either input is not valid JSON.
        ValueError: If either JSON root is not an object.
    """
    contract_file = Path(contract_path)
    evidence_file = Path(evidence_path)
    contract = load_flow_contract_v2(contract_file)
    evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
    if not isinstance(contract, dict):
        raise ValueError("flow contract must be a JSON object")
    if not isinstance(evidence, dict):
        raise ValueError("causal evidence must be a JSON object")

    issues = _schema_issues(evidence)
    contract_issues = validate_flow_contract_v2(contract)
    if contract_issues:
        issues.append(
            _issue(
                "causal.contract.invalid",
                "$.contract",
                f"flow contract has {len(contract_issues)} validation issue(s)",
            )
        )
    issues.extend(_contract_binding_issues(contract_file, contract, evidence))
    issues.extend(_observation_issues(contract_file, evidence_file, contract, evidence))
    issues.sort(key=_issue_sort_key)
    causal_ids = {
        str(transition["id"])
        for transition in _items(contract, "transitions")
        if isinstance(transition.get("id"), str) and isinstance(transition.get("causal"), dict)
    }
    return {
        "kind": "penflow-causal-transition-report",
        "version": 1,
        "status": "PASS" if not issues else "FAIL",
        "contract": str(contract_file),
        "evidence": str(evidence_file),
        "summary": {
            "causal_transitions": len(causal_ids),
            "runs": len(_items(evidence, "runs")),
            "observations": len(_items(evidence, "observations")),
            "issues": len(issues),
        },
        "issues": issues,
    }


def _schema_issues(evidence: dict[str, Any]) -> list[dict[str, str]]:
    validator = validator_for(_SCHEMA)
    issues = [
        _issue("causal.evidence.schema", _json_path(error.absolute_path), error.message)
        for error in validator.iter_errors(evidence)
    ]
    issues.sort(key=_issue_sort_key)
    return issues


def _contract_binding_issues(
    contract_file: Path,
    contract: dict[str, Any],
    evidence: dict[str, Any],
) -> list[dict[str, str]]:
    binding = evidence.get("contract")
    if not isinstance(binding, dict):
        return []
    issues: list[dict[str, str]] = []
    if binding.get("id") != contract.get("contract_id"):
        issues.append(
            _issue(
                "causal.contract.identity_mismatch",
                "$.contract.id",
                "evidence contract id does not match contract_id",
            )
        )
    if binding.get("version") != contract.get("version"):
        issues.append(
            _issue(
                "causal.contract.version_mismatch",
                "$.contract.version",
                "evidence contract version does not match contract version",
            )
        )
    digest = hashlib.sha256(contract_file.read_bytes()).hexdigest()
    if binding.get("sha256") != digest:
        issues.append(
            _issue(
                "causal.contract.digest_mismatch",
                "$.contract.sha256",
                f"evidence digest does not match contract bytes: expected {digest}",
            )
        )
    return issues


def _observation_issues(
    contract_file: Path,
    evidence_file: Path,
    contract: dict[str, Any],
    evidence: dict[str, Any],
) -> list[dict[str, str]]:
    """Cross-check observations only after capture; Penflow never executes them."""
    issues: list[dict[str, str]] = []
    transitions = {
        str(item["id"]): item
        for item in _items(contract, "transitions")
        if isinstance(item.get("id"), str)
    }
    actions = {
        str(item["id"]): item
        for item in _items(contract, "actions")
        if isinstance(item.get("id"), str)
    }
    nodes = {
        str(item["id"]): item
        for item in _items(contract, "nodes")
        if isinstance(item.get("id"), str)
    }
    runs, run_issues = _run_registry(evidence)
    issues.extend(run_issues)
    observed_transition_ids: set[str] = set()
    observation_ids: set[str] = set()
    receipt_ids: set[str] = set()
    receipt_artifacts: set[tuple[Path, str]] = set()
    receipt_digests: dict[str, str] = {}

    for index, observation in enumerate(_items(evidence, "observations")):
        path = f"$.observations[{index}]"
        observation_id = observation.get("id")
        if isinstance(observation_id, str):
            if observation_id in observation_ids:
                issues.append(
                    _issue(
                        "causal.observation.id_duplicate",
                        f"{path}.id",
                        f"duplicate observation id: {observation_id}",
                    )
                )
            observation_ids.add(observation_id)
        transition_id = observation.get("transition_id")
        transition = transitions.get(str(transition_id))
        if not isinstance(transition, dict):
            issues.append(
                _issue(
                    "causal.transition.unknown",
                    f"{path}.transition_id",
                    f"unknown transition: {transition_id}",
                )
            )
            continue
        observed_transition_ids.add(str(transition_id))
        if not isinstance(transition.get("causal"), dict):
            issues.append(
                _issue(
                    "causal.transition.not_declared",
                    f"{path}.transition_id",
                    "observation targets a transition without causal metadata",
                )
            )
            continue
        issues.extend(_run_binding_issues(observation, path, runs))
        issues.extend(_action_issues(observation, path, transition, actions, nodes))
        issues.extend(_state_issues(observation, path, transition))
        issues.extend(
            _receipt_issues(
                observation,
                path,
                contract_file,
                evidence_file,
                runs,
                receipt_ids,
                receipt_artifacts,
                receipt_digests,
            )
        )

    causal_transition_ids = {
        transition_id
        for transition_id, transition in transitions.items()
        if isinstance(transition.get("causal"), dict)
    }
    for transition_id in sorted(causal_transition_ids - observed_transition_ids):
        issues.append(
            _issue(
                "causal.outcome.unproven",
                "$.observations",
                f"causal transition has no independent observation: {transition_id}",
            )
        )
    return issues


def _run_registry(
    evidence: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    runs: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, str]] = []
    for index, run in enumerate(_items(evidence, "runs")):
        run_id = run.get("id")
        if not isinstance(run_id, str):
            continue
        if run_id in runs:
            issues.append(
                _issue(
                    "causal.run.id_duplicate",
                    f"$.runs[{index}].id",
                    f"duplicate run id: {run_id}",
                )
            )
        runs[run_id] = run
    return runs, issues


def _run_binding_issues(
    observation: dict[str, Any],
    path: str,
    runs: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    run_id = observation.get("run_id")
    if not isinstance(run_id, str) or run_id not in runs:
        return [
            _issue(
                "causal.run.missing",
                f"{path}.run_id",
                f"observation run is not declared: {run_id}",
            )
        ]
    return []


def _action_issues(
    observation: dict[str, Any],
    path: str,
    transition: dict[str, Any],
    actions: dict[str, dict[str, Any]],
    nodes: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    action_observation = observation.get("action")
    if not isinstance(action_observation, dict):
        return [
            _issue(
                "causal.action.missing",
                f"{path}.action",
                "adapter must provide the observed user action",
            )
        ]
    issues: list[dict[str, str]] = []
    action_id = transition.get("action")
    action = actions.get(str(action_id))
    node = nodes.get(str(action.get("node"))) if isinstance(action, dict) else None
    if action_observation.get("id") != action_id:
        issues.append(
            _issue(
                "causal.action.identity_mismatch",
                f"{path}.action.id",
                "observed action id does not match transition action",
            )
        )
    if action_observation.get("visible") is not True:
        issues.append(
            _issue(
                "causal.action.not_visible",
                f"{path}.action.visible",
                "causal action must be visibly observable by the user",
            )
        )
    event = action_observation.get("event")
    test_id = action_observation.get("test_id")
    if (
        not isinstance(event, str)
        or not event.strip()
        or not isinstance(test_id, str)
        or not test_id
    ):
        issues.append(
            _issue(
                "causal.action.value_missing",
                f"{path}.action",
                "observed action requires non-empty event and test_id values",
            )
        )
    if isinstance(node, dict) and test_id != node.get("test_id"):
        issues.append(
            _issue(
                "causal.action.test_id_mismatch",
                f"{path}.action.test_id",
                "observed test_id does not match the contract action node",
            )
        )
    return issues


def _state_issues(
    observation: dict[str, Any],
    path: str,
    transition: dict[str, Any],
) -> list[dict[str, str]]:
    pre = observation.get("pre_state")
    post = observation.get("post_state")
    destination = observation.get("destination")
    issues: list[dict[str, str]] = []
    if not _complete_state(pre):
        issues.append(
            _issue(
                "causal.state.pre_missing",
                f"{path}.pre_state",
                "pre_state requires non-empty screen, state, and value",
            )
        )
    if not _complete_state(post):
        issues.append(
            _issue(
                "causal.state.post_missing",
                f"{path}.post_state",
                "post_state requires non-empty screen, state, and value",
            )
        )
    if not _complete_destination(destination):
        issues.append(
            _issue(
                "causal.destination.missing",
                f"{path}.destination",
                "destination requires non-empty screen and state",
            )
        )
    if not isinstance(pre, dict) or not isinstance(post, dict):
        return issues
    if pre == post:
        code = (
            "causal.state.default_unchanged"
            if pre.get("state") == post.get("state") == "default"
            else "causal.state.unchanged"
        )
        issues.append(_issue(code, f"{path}.post_state", "post-state must differ from pre-state"))
    kind = transition.get("kind")
    if kind == "navigation" and pre.get("screen") == post.get("screen"):
        issues.append(
            _issue(
                "causal.destination.unchanged",
                f"{path}.post_state.screen",
                "navigation must change the observed screen",
            )
        )
    if kind == "state" and pre.get("state") == post.get("state"):
        code = (
            "causal.state.default_unchanged"
            if pre.get("state") == post.get("state") == "default"
            else "causal.state.unchanged"
        )
        issues.append(
            _issue(code, f"{path}.post_state.state", "state transition must change state")
        )
    if kind == "environment" and pre.get("value") == post.get("value"):
        issues.append(
            _issue(
                "causal.state.value_unchanged",
                f"{path}.post_state.value",
                "environment transition must change the observed value",
            )
        )
    expected_pre = (transition.get("from_screen"), transition.get("from_state"))
    expected_post = (transition.get("to_screen"), transition.get("to_state"))
    if (pre.get("screen"), pre.get("state")) != expected_pre:
        issues.append(
            _issue(
                "causal.state.pre_mismatch",
                f"{path}.pre_state",
                f"pre-state does not match declared source {expected_pre}",
            )
        )
    if (post.get("screen"), post.get("state")) != expected_post:
        issues.append(
            _issue(
                "causal.state.post_mismatch",
                f"{path}.post_state",
                f"post-state does not match declared destination {expected_post}",
            )
        )
    if isinstance(destination, dict):
        observed_destination = (destination.get("screen"), destination.get("state"))
        if observed_destination != expected_post or observed_destination != (
            post.get("screen"),
            post.get("state"),
        ):
            issues.append(
                _issue(
                    "causal.destination.mismatch",
                    f"{path}.destination",
                    "destination must match both declared and observed post-state",
                )
            )
    causal = transition.get("causal")
    outcome = causal.get("outcome") if isinstance(causal, dict) else None
    if observation.get("outcome") != outcome:
        issues.append(
            _issue(
                "causal.outcome.mismatch",
                f"{path}.outcome",
                "observed outcome does not match the transition outcome",
            )
        )
    return issues


def _receipt_issues(
    observation: dict[str, Any],
    path: str,
    contract_file: Path,
    evidence_file: Path,
    runs: dict[str, dict[str, Any]],
    receipt_ids: set[str],
    receipt_artifacts: set[tuple[Path, str]],
    receipt_digests: dict[str, str],
) -> list[dict[str, str]]:
    receipts = observation.get("evidence")
    if not isinstance(receipts, list) or not receipts:
        return [
            _issue(
                "causal.proof.missing",
                f"{path}.evidence",
                "every outcome requires its own runtime-bound proof",
            )
        ]
    issues: list[dict[str, str]] = []
    observation_run = observation.get("run_id")
    root = evidence_file.parent.resolve()
    for index, receipt in enumerate(receipts):
        receipt_path = f"{path}.evidence[{index}]"
        if not isinstance(receipt, dict):
            continue
        receipt_id = receipt.get("id")
        if isinstance(receipt_id, str):
            if receipt_id in receipt_ids:
                issues.append(
                    _issue(
                        "causal.proof.reused",
                        f"{receipt_path}.id",
                        f"receipt id is reused across outcomes: {receipt_id}",
                    )
                )
            receipt_ids.add(receipt_id)
        if receipt.get("run_id") != observation_run:
            issues.append(
                _issue(
                    "causal.run.mismatch",
                    f"{receipt_path}.run_id",
                    "receipt run_id must match its observation",
                )
            )
        if receipt.get("kind") not in RUNTIME_RECEIPT_KINDS:
            issues.append(
                _issue(
                    "causal.proof.static_generic",
                    f"{receipt_path}.kind",
                    "static or generic proof cannot establish runtime causality",
                )
            )
        declared_path = receipt.get("path")
        digest = receipt.get("sha256")
        if isinstance(digest, str):
            owner = f"{observation.get('transition_id')}:{observation.get('outcome')}"
            previous_owner = receipt_digests.get(digest)
            if previous_owner is not None:
                issues.append(
                    _issue(
                        "causal.proof.digest_reused",
                        f"{receipt_path}.sha256",
                        f"proof digest is already bound to outcome {previous_owner}",
                    )
                )
            else:
                receipt_digests[digest] = owner
        if not isinstance(declared_path, str) or not declared_path:
            continue
        relative = Path(declared_path)
        resolved = (root / relative).resolve()
        if relative.is_absolute() or ".." in relative.parts or not resolved.is_relative_to(root):
            issues.append(
                _issue(
                    "causal.proof.path_invalid",
                    f"{receipt_path}.path",
                    "proof path must stay inside the evidence bundle",
                )
            )
            continue
        if resolved in {contract_file.resolve(), evidence_file.resolve()}:
            issues.append(
                _issue(
                    "causal.proof.static_generic",
                    f"{receipt_path}.path",
                    "contract/evidence documents cannot substitute for a runtime receipt",
                )
            )
        artifact_key = (resolved, str(digest))
        if artifact_key in receipt_artifacts:
            issues.append(
                _issue(
                    "causal.proof.reused",
                    f"{receipt_path}.path",
                    "each outcome requires a distinct proof artifact",
                )
            )
        receipt_artifacts.add(artifact_key)
        if not resolved.is_file():
            issues.append(
                _issue(
                    "causal.proof.file_missing",
                    f"{receipt_path}.path",
                    f"proof file not found: {declared_path}",
                )
            )
            continue
        receipt_bytes = resolved.read_bytes()
        actual_digest = hashlib.sha256(receipt_bytes).hexdigest()
        if digest != actual_digest:
            issues.append(
                _issue(
                    "causal.proof.digest_mismatch",
                    f"{receipt_path}.sha256",
                    f"proof digest does not match artifact bytes: expected {actual_digest}",
                )
            )
            continue
        issues.extend(
            _runtime_receipt_payload_issues(
                receipt_bytes,
                receipt,
                observation,
                runs,
                receipt_path,
            )
        )
    return issues


def _runtime_receipt_payload_issues(
    receipt_bytes: bytes,
    receipt: dict[str, Any],
    observation: dict[str, Any],
    runs: dict[str, dict[str, Any]],
    receipt_path: str,
) -> list[dict[str, str]]:
    """Validate the closed adapter payload and its observation identity binding."""
    try:
        payload = json.loads(receipt_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return [
            _issue(
                "causal.proof.payload_invalid",
                f"{receipt_path}.path",
                "runtime receipt must contain a valid JSON adapter payload",
            )
        ]
    if not isinstance(payload, dict):
        return [
            _issue(
                "causal.proof.payload_invalid",
                f"{receipt_path}.path",
                "runtime receipt payload must be a JSON object",
            )
        ]
    validator = validator_for(_RUNTIME_RECEIPT_SCHEMA)
    schema_issues = [
        _issue(
            "causal.proof.payload_schema",
            f"{receipt_path}.payload{_json_path(error.absolute_path)[1:]}",
            error.message,
        )
        for error in validator.iter_errors(payload)
    ]
    if schema_issues:
        return sorted(schema_issues, key=_issue_sort_key)

    run = runs.get(str(observation.get("run_id")))
    expected_bindings = {
        "run_id": observation.get("run_id"),
        "transition_id": observation.get("transition_id"),
        "observation_id": observation.get("id"),
        "outcome": observation.get("outcome"),
        "adapter": run.get("adapter") if isinstance(run, dict) else None,
        "surface": run.get("surface") if isinstance(run, dict) else None,
    }
    issues: list[dict[str, str]] = []
    for field, expected in expected_bindings.items():
        if payload.get(field) != expected:
            issues.append(
                _issue(
                    "causal.proof.payload_binding_mismatch",
                    f"{receipt_path}.payload.{field}",
                    f"runtime receipt {field} does not match its observation/run binding",
                )
            )
    capture = payload.get("capture")
    if isinstance(capture, dict) and capture.get("kind") != receipt.get("kind"):
        issues.append(
            _issue(
                "causal.proof.payload_kind_mismatch",
                f"{receipt_path}.payload.capture.kind",
                "runtime receipt capture kind does not match evidence receipt kind",
            )
        )
    expected_snapshot = {
        "action": observation.get("action"),
        "pre_state": observation.get("pre_state"),
        "post_state": observation.get("post_state"),
        "destination": observation.get("destination"),
        "outcome": observation.get("outcome"),
    }
    if isinstance(capture, dict):
        for field, expected in expected_snapshot.items():
            if capture.get(field) != expected:
                issues.append(
                    _issue(
                        "causal.proof.snapshot_mismatch",
                        f"{receipt_path}.payload.capture.{field}",
                        f"runtime receipt {field} does not match its enclosing observation",
                    )
                )
    return issues


def _complete_state(value: Any) -> bool:
    return isinstance(value, dict) and all(
        isinstance(value.get(field), str) and bool(value[field].strip())
        for field in ("screen", "state", "value")
    )


def _complete_destination(value: Any) -> bool:
    return isinstance(value, dict) and all(
        isinstance(value.get(field), str) and bool(value[field].strip())
        for field in ("screen", "state")
    )


def _items(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = data.get(key)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _json_path(parts: Any) -> str:
    path = "$"
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


def _issue(code: str, path: str, message: str) -> dict[str, str]:
    return {"severity": "error", "code": code, "path": path, "message": message}


def _issue_sort_key(issue: dict[str, str]) -> tuple[str, str, str]:
    return (issue["code"], issue["path"], issue["message"])
