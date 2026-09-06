"""Authenticate normalized runtime facts and action-free UI snapshots."""

from typing import Any

from .verification_files import VerificationInputError
from .verification_snapshot import VerificationSnapshot


def capture_identity_issues(
    snapshot: VerificationSnapshot, manifest: dict[str, Any], value: dict[str, Any]
) -> list[str]:
    """Require exact caller build, producer, source and captured execution identities."""
    expected = {
        "contract_sha256": snapshot.reader.observed[
            snapshot.reader.path(snapshot.workspace / "flow-ui-contract/contract.json")
        ],
        "build_id": manifest["build"]["id"],
        "producer_invocation_id": manifest["producer"]["invocation_id"],
    }
    findings = [
        "verification.producer." + key
        for key, identity in expected.items()
        if value[key] != identity
    ]
    if (
        value["session_id"] not in manifest["capture"]["session_ids"]
        or value["scenario_id"] not in manifest["capture"]["scenario_ids"]
    ):
        findings.append("verification.evidence.session_or_scenario")
    return findings


def require_runner_reference(
    snapshot: VerificationSnapshot, manifest: dict[str, Any], reference: dict[str, str]
) -> bytes:
    """Read a current evidence file whose identity belongs to the independent runner set."""
    expected = {
        str(snapshot.reader.path(item["path"])): item["sha256"] for item in manifest["evidence"]
    }
    if expected.get(str(snapshot.reader.path(reference["path"]))) != reference["sha256"]:
        raise VerificationInputError("verification.evidence.not_runner_bound")
    return snapshot.reader.reference(reference)


def read_ui_snapshot(
    snapshot: VerificationSnapshot, manifest: dict[str, Any], reference: dict[str, str]
) -> dict[str, Any]:
    """Read a real UI witness without inventing an actor, action or business result."""
    value = snapshot.reader.object(
        require_runner_reference(snapshot, manifest, reference), "ui-snapshot"
    )
    if capture_identity_issues(snapshot, manifest, value):
        raise VerificationInputError("verification.evidence.ui_snapshot_identity")
    for raw in value["raw_evidence"]:
        require_runner_reference(snapshot, manifest, raw)
    return value
