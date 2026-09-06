# @spec FR-009: Bind independently produced observations to caller-verified build, producer, contract and scenario; reject fixture certification. — .specs/features/077-complete-verification-workflow/spec.md#fr-009
"""Validate independently supplied runner authority before consuming observations."""

from pathlib import Path
from typing import Any

from .verification_files import VerificationInputError
from .verification_json import digest
from .verification_assertions import json_values_equal
from .verification_snapshot import VerificationSnapshot


def load_build_manifest(
    snapshot: VerificationSnapshot, manifest_path: str | Path
) -> tuple[dict[str, Any], dict[str, str]]:
    """Bind the served artifacts, producer bytes and complete approved source authority."""
    reader = snapshot.reader
    path = reader.path(manifest_path)
    if any(
        part in {".penflow-tmp", ".penflow-run", ".mockup-validation"}
        for part in path.relative_to(reader.root).parts
    ):
        raise VerificationInputError("verification.build.manifest_not_protected")
    if path.is_relative_to(snapshot.workspace):
        raise VerificationInputError("verification.build.manifest_inside_workspace")
    required_sources = {item["path"]: item["sha256"] for item in snapshot.authority_sources}
    raw = reader.read(path)
    manifest = reader.object(raw, "build-manifest")
    if manifest["scope"] != {"project_root": str(reader.root)}:
        raise VerificationInputError("verification.build.scope")
    collections = [
        manifest["build"]["artifacts"],
        manifest["sources"],
        manifest["evidence"],
        [manifest["producer"]["entrypoint"]],
    ]
    normalized = []
    for collection in collections:
        identities = {}
        for reference in collection:
            resolved = str(reader.path(reference["path"]))
            if resolved in identities:
                raise VerificationInputError("verification.build.duplicate_reference")
            reader.reference(reference)
            identities[resolved] = reference["sha256"]
        normalized.append(identities)
    if any(normalized[1].get(path) != sha for path, sha in required_sources.items()):
        raise VerificationInputError("verification.build.source_membership")
    entry = reader.path(manifest["producer"]["entrypoint"]["path"])
    if entry.is_relative_to(snapshot.workspace):
        raise VerificationInputError("verification.producer.entrypoint_not_independent")
    return manifest, {"path": str(path), "sha256": digest(raw)}


def observation_authority_issues(
    snapshot: VerificationSnapshot,
    manifest: dict[str, Any],
    observation: dict[str, Any],
    path: Path,
) -> list[str]:
    """Join each observed identity and raw evidence with the caller's runner set."""
    issues = []
    expected = {
        "build_id": manifest["build"]["id"],
        "producer_invocation_id": manifest["producer"]["invocation_id"],
    }
    for key, value in expected.items():
        if observation[key] != value:
            issues.append("verification.producer." + key)
    if (
        observation["session_id"] not in manifest["capture"]["session_ids"]
        or observation["scenario_id"] not in manifest["capture"]["scenario_ids"]
    ):
        issues.append("verification.evidence.session_or_scenario")
    contract_path = snapshot.reader.path(snapshot.workspace / "flow-ui-contract/contract.json")
    if observation["contract_sha256"] != snapshot.reader.observed[contract_path]:
        issues.append("verification.evidence.contract")
    evidence = {
        str(snapshot.reader.path(ref["path"])): ref["sha256"] for ref in manifest["evidence"]
    }
    for reference in (
        {"path": str(path), "sha256": snapshot.reader.observed[path]},
        observation["evidence"],
    ):
        resolved = str(snapshot.reader.path(reference["path"]))
        if evidence.get(resolved) != reference["sha256"]:
            issues.append("verification.evidence.not_runner_bound")
        snapshot.reader.reference(reference)
    facts = snapshot.reader.object(
        snapshot.reader.reference(observation["evidence"]), "runtime-facts"
    )
    for key, value in facts.items():
        if key not in {"kind", "version", "raw_evidence"} and not json_values_equal(
            value, observation[key]
        ):
            issues.append("verification.evidence.facts_mismatch")
    for reference in facts["raw_evidence"]:
        resolved = str(snapshot.reader.path(reference["path"]))
        if evidence.get(resolved) != reference["sha256"]:
            issues.append("verification.evidence.raw_not_runner_bound")
        snapshot.reader.reference(reference)
    return issues
