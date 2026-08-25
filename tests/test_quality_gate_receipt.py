# @spec(AC-012)
# @spec(FR-009)
# @spec(FR-014)
"""Contract tests for Feature 074 durable quality-gate receipts."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.quality_gate_receipt import (
    GATE_IDS,
    ArtifactSelector,
    CommandResult,
    CommandSpec,
    GateConfigurationError,
    ReceiptValidationError,
    gate_command_specs,
    main,
    run_gate_specs,
    validate_receipt,
)


def _passing_command(*_args: object, **_kwargs: object) -> CommandResult:
    """Return deterministic bytes for an injected successful command."""
    return CommandResult(returncode=0, stdout=b"1 passed\n", stderr=b"")


def test_gate_registry_is_closed() -> None:
    assert GATE_IDS == ("qg1", "qg2", "qg3", "qg4", "qg5", "qe7")


def test_qe7_registry_uses_closed_selector_and_metric_environment(tmp_path: Path) -> None:
    specs = gate_command_specs("qe7", tmp_path)

    assert len(specs) == 1
    assert specs[0].argv[-2:] == ("-k", "large_tree")
    assert specs[0].environment[0][0] == "PENFLOW_QE7_OUT"
    assert specs[0].artifacts == (
        ArtifactSelector(
            ".specs/features/074-penflow-doctor-consumer-project-hygiene/"
            "checks/qe7-large-tree-metrics.json",
            kind="qe7",
        ),
    )


def test_qg1_requires_external_receipt_and_rejects_it_for_other_gates(tmp_path: Path) -> None:
    with pytest.raises(GateConfigurationError, match="requires --external-receipt"):
        gate_command_specs("qg1", tmp_path)
    with pytest.raises(GateConfigurationError, match="accepted only by qg1"):
        gate_command_specs("qg2", tmp_path, external_receipt=tmp_path / "receipt.json")


def test_qg1_validation_is_feature_scoped_and_not_repo_coherence(tmp_path: Path) -> None:
    receipt = tmp_path / "run.json"
    receipt.write_text("{}\n", encoding="utf-8")

    specs = gate_command_specs("qg1", tmp_path, external_receipt=receipt)

    assert specs[0].argv == (
        "livespec",
        "validate",
        ".specs/features/074-penflow-doctor-consumer-project-hygiene",
        "--strict",
        "--format",
        "json",
    )
    assert "--coherence" not in specs[0].argv
    assert specs[1].artifacts == (ArtifactSelector("run.json", kind="complete_spec_check_run"),)


@pytest.mark.parametrize(
    ("goal_status", "archive_status", "expected_status"),
    [
        ("complete", "complete", "PASS"),
        ("active", "complete", "FAIL"),
        ("complete", "pending", "FAIL"),
    ],
)
def test_qg1_requires_completed_archived_spec_check_run(
    tmp_path: Path, goal_status: str, archive_status: str, expected_status: str
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    run_artifact = project / ".specs" / ".runs" / "spec-check.json"
    run_artifact.parent.mkdir(parents=True)
    run_artifact.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "command": "spec-check",
                "feature": "074-penflow-doctor-consumer-project-hygiene",
                "exit_code": 0,
                "goal": {
                    "status": goal_status,
                    "tasks": [{"id": "archive.run", "status": archive_status}],
                },
                "verify_result": {"outcome": "success"},
            }
        ),
        encoding="utf-8",
    )
    specs = gate_command_specs("qg1", project, external_receipt=run_artifact)

    receipt = run_gate_specs(
        gate="qg1",
        project=project,
        output=project / "qg1.json",
        command_specs=specs,
        command_runner=_passing_command,
        commit="a" * 40,
    )

    assert receipt["stable_result"]["status"] == expected_status


def test_cli_rejects_unknown_gate_without_executing(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            [
                "arbitrary-shell",
                "--project",
                str(tmp_path),
                "--out",
                str(tmp_path / "receipt.json"),
            ]
        )
    assert raised.value.code == 2


def test_unknown_gate_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(GateConfigurationError, match="unknown gate"):
        run_gate_specs(
            gate="arbitrary-shell",
            project=tmp_path,
            output=tmp_path / "receipt.json",
            command_specs=(),
            command_runner=_passing_command,
        )


def test_receipt_captures_hashes_and_stable_result(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    artifact = project / "evidence.json"
    artifact.write_text('{"status":"PASS"}\n', encoding="utf-8")
    command = CommandSpec(
        name="focused",
        argv=("python", "-m", "pytest", "-q"),
        output_contains=("passed",),
        artifacts=(ArtifactSelector("evidence.json"),),
    )

    first = run_gate_specs(
        gate="qg2",
        project=project,
        output=project / "receipt.json",
        command_specs=(command,),
        command_runner=_passing_command,
        commit="a" * 40,
        diagnostics={"started_at": "first", "finished_at": "first", "host": "host-a"},
    )
    second = run_gate_specs(
        gate="qg2",
        project=project,
        output=project / "receipt.json",
        command_specs=(command,),
        command_runner=_passing_command,
        commit="a" * 40,
        diagnostics={"started_at": "second", "finished_at": "second", "host": "host-b"},
    )

    assert first["stable_result"] == second["stable_result"]
    assert second["stable_result"]["status"] == "PASS"
    assert len(second["stable_result"]["commands"][0]["stdout_sha256"]) == 64
    assert second["stable_result"]["artifacts"][0]["path"] == "evidence.json"
    validate_receipt(project / "receipt.json", project)


def test_nonzero_and_timeout_commands_fail_closed(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    command = CommandSpec(name="focused", argv=("tool", "test"))

    nonzero = run_gate_specs(
        gate="qg3",
        project=project,
        output=project / "nonzero.json",
        command_specs=(command,),
        command_runner=lambda *_args, **_kwargs: CommandResult(7, b"", b"boom\n"),
    )

    def timeout(*_args: object, **_kwargs: object) -> CommandResult:
        raise subprocess.TimeoutExpired(cmd=["tool", "test"], timeout=90)

    timed_out = run_gate_specs(
        gate="qg3",
        project=project,
        output=project / "timeout.json",
        command_specs=(command,),
        command_runner=timeout,
    )

    assert nonzero["stable_result"]["status"] == "FAIL"
    assert timed_out["stable_result"]["status"] == "FAIL"
    assert "command:focused:timeout:FAIL" in timed_out["stable_result"]["assertions"]


def test_missing_selector_and_tampered_transcript_fail_closed(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    command = CommandSpec(
        name="focused",
        argv=("tool", "test"),
        artifacts=(ArtifactSelector("missing.json"),),
    )
    receipt_path = project / "receipt.json"
    receipt = run_gate_specs(
        gate="qg4",
        project=project,
        output=receipt_path,
        command_specs=(command,),
        command_runner=_passing_command,
    )

    assert receipt["stable_result"]["status"] == "FAIL"
    assert "artifact:missing.json:present:FAIL" in receipt["stable_result"]["assertions"]

    valid = run_gate_specs(
        gate="qg4",
        project=project,
        output=receipt_path,
        command_specs=(CommandSpec(name="focused", argv=("tool", "test")),),
        command_runner=_passing_command,
    )
    transcript = project / valid["stable_result"]["commands"][0]["stdout_path"]
    transcript.write_bytes(b"tampered\n")
    with pytest.raises(ReceiptValidationError, match="transcript hash mismatch"):
        validate_receipt(receipt_path, project)
    transcript.unlink()
    with pytest.raises(ReceiptValidationError, match="transcript is missing"):
        validate_receipt(receipt_path, project)


def test_atomic_overwrite_leaves_no_sibling_temp_file(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    receipt_path = project / "receipt.json"
    command = CommandSpec(name="focused", argv=("tool", "test"))
    receipt_path.write_text("old bytes", encoding="utf-8")

    run_gate_specs(
        gate="qg5",
        project=project,
        output=receipt_path,
        command_specs=(command,),
        command_runner=_passing_command,
    )

    assert json.loads(receipt_path.read_text(encoding="utf-8"))["schema_version"] == 1
    assert not list(project.glob(f".{receipt_path.name}.*.tmp"))


def test_qe7_selector_rejects_missing_runner_identity_or_bounds(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    measurement = project / "qe7-measurement.json"
    measurement.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "stable_result": {
                    "status": "PASS",
                    "commit": "b" * 40,
                    "runner": {},
                    "fixture": {"seed": 74, "file_count": 50_000, "logical_bytes": 5 << 30},
                    "metrics": {
                        "elapsed_seconds": 31.0,
                        "peak_rss_bytes": 1,
                        "peak_open_fds": 1,
                        "reported_logical_bytes": 5 << 30,
                        "recomputed_logical_bytes": 5 << 30,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    command = CommandSpec(
        name="large-tree",
        argv=("python", "-m", "pytest", "-k", "large_tree"),
        artifacts=(ArtifactSelector("qe7-measurement.json", kind="qe7"),),
    )

    receipt = run_gate_specs(
        gate="qe7",
        project=project,
        output=project / "qe7.json",
        command_specs=(command,),
        command_runner=_passing_command,
        commit="b" * 40,
    )

    assert receipt["stable_result"]["status"] == "FAIL"
    assert (
        "artifact:qe7-measurement.json:qe7-contract:FAIL" in receipt["stable_result"]["assertions"]
    )


def test_qe7_selector_accepts_complete_in_bounds_measurement(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    commit = "c" * 40
    measurement = project / "qe7-measurement.json"
    measurement.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "stable_result": {
                    "status": "PASS",
                    "commit": commit,
                    "runner": {
                        "image_os": "ubuntu24",
                        "image_version": "20260824.1",
                        "kernel": "Linux 6",
                        "architecture": "x86_64",
                        "cpu_count": 4,
                        "filesystem": "ext4",
                        "python_version": "3.12.11",
                    },
                    "fixture": {
                        "seed": 74,
                        "file_count": 50_000,
                        "logical_bytes": 5 << 30,
                    },
                    "metrics": {
                        "elapsed_seconds": 29.9,
                        "peak_rss_bytes": 256 << 20,
                        "peak_open_fds": 32,
                        "reported_logical_bytes": 5 << 30,
                        "recomputed_logical_bytes": 5 << 30,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    command = CommandSpec(
        name="large-tree",
        argv=("python", "-m", "pytest", "-k", "large_tree"),
        output_contains=("passed",),
        artifacts=(ArtifactSelector("qe7-measurement.json", kind="qe7"),),
    )

    receipt = run_gate_specs(
        gate="qe7",
        project=project,
        output=project / "qe7.json",
        command_specs=(command,),
        command_runner=_passing_command,
        commit=commit,
    )

    assert receipt["stable_result"]["status"] == "PASS"
