# @spec AC-023: Given unchanged design inputs and changed code, when rerunning, then eligible design evidence is reused and affected runtime evidence invalidated; mutable source changes between reads/final publication fail safely. — .specs/features/077-complete-verification-workflow/spec.md#ac-023
# @spec AC-019: Given LiveSpec implementation closure or require_actual, when workspace/CLI/report/independent expected build is absent or invalid, then it blocks even if actual-tree exists; it never infers readiness from presence alone. — .specs/features/077-complete-verification-workflow/spec.md#ac-019
# @spec AC-014: Given runtime evidence for a wrong build/scenario/contract/untrusted producer or a static fixture, when implementation is required, then it fails; independently captured byte-identical expected/actual content is permitted. — .specs/features/077-complete-verification-workflow/spec.md#ac-014
"""Authority joins, independently frozen source fixtures and adversarial runtime values."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from penflow.verification_build import load_build_manifest, observation_authority_issues
from penflow.verification_files import InputReader, VerificationInputError
from penflow.verification_json import digest
from penflow.verification_snapshot import load_source_snapshot
from tests.c51_factory import persistence_observation
from tests.test_product_sources_adversarial import FIXTURE, WORKSPACE, _copy_consumer


def _write(path: Path, value: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    return {"path": str(path), "sha256": digest(path.read_bytes())}


def _source(tmp_path: Path):
    root = _copy_consumer(FIXTURE, tmp_path)
    reader = InputReader(root)
    prior_report = root / WORKSPACE / "run-report.json"
    prior_report.write_text('{"status":"FAIL"}')
    reader.read(prior_report)
    snapshot = load_source_snapshot(reader, root / WORKSPACE)
    return root, reader, snapshot, prior_report


def test_revalidation_does_not_require_build_to_depend_on_its_own_report(tmp_path: Path) -> None:
    root, reader, snapshot, report = _source(tmp_path)
    assert str(report) not in {item["path"] for item in snapshot.authority_sources}
    runner = _write(root / "runtime/runner.json", {"test_only": True})
    manifest = {
        "kind": "penflow-build-manifest",
        "version": 1,
        "scope": {"project_root": str(root.resolve())},
        "build": {"id": "fixture", "artifacts": [runner]},
        "producer": {"id": "fixture", "entrypoint": runner, "invocation_id": "test"},
        "capture": {"session_ids": ["session"], "scenario_ids": ["scenario"]},
        "sources": snapshot.authority_sources,
        "evidence": [runner],
        "issued_at": "2026-09-05T00:00:00Z",
    }
    path = root / "runtime/build-manifest.json"
    _write(path, manifest)
    assert load_build_manifest(snapshot, path)[0] == manifest
    reader.recheck()


@pytest.mark.parametrize("change", [None, "session", "scenario", "value"])
def test_observation_must_match_raw_facts_not_just_manifest_membership(
    tmp_path: Path, change: str | None
) -> None:
    root, reader, snapshot, _ = _source(tmp_path)
    observed = persistence_observation()
    observed["contract_sha256"] = reader.observed[
        reader.path(snapshot.workspace / "flow-ui-contract/contract.json")
    ]
    raw = _write(
        root / "runtime/measured.json", {"test_only": "independent captured values fixture"}
    )
    facts = {
        key: deepcopy(value)
        for key, value in observed.items()
        if key not in {"kind", "category", "obligation_id", "evidence"}
    }
    facts.update(kind="penflow-runtime-facts", raw_evidence=[raw])
    observed["evidence"] = _write(root / "runtime/facts.json", facts)
    if change == "session":
        observed["session_id"] = "other-session"
    elif change == "scenario":
        observed["scenario_id"] = "other-scenario"
    elif change == "value":
        observed["after"]["value"]["amount"] = 999
    path = root / "runtime/observation.json"
    observation_ref = _write(path, observed)
    reader.read(path)
    manifest = {
        "build": {"id": observed["build_id"]},
        "producer": {"invocation_id": observed["producer_invocation_id"]},
        "capture": {
            "session_ids": [facts["session_id"], "other-session"],
            "scenario_ids": [facts["scenario_id"], "other-scenario"],
        },
        "evidence": [raw, observed["evidence"], observation_ref],
    }
    findings = observation_authority_issues(snapshot, manifest, observed, path)
    assert bool(findings) == (change is not None)
    if change:
        assert "verification.evidence.facts_mismatch" in findings


def test_added_observation_is_detected_before_publication(tmp_path: Path) -> None:
    reader = InputReader(tmp_path)
    directory = tmp_path / "observations"
    directory.mkdir()
    assert reader.files(directory, "*.json") == []
    _write(directory / "added.json", {})
    with pytest.raises(VerificationInputError, match="membership_changed"):
        reader.recheck()
