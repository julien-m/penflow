# @spec FR-009 FR-010 AC-010 AC-011 AC-012
"""Contract tests for Feature 075's isolated quality-gate receipt runner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.feature_075_quality_gate_receipt import (
    CHECKS_DIRECTORY,
    CONSUMER_PROOF,
    FEATURE_075_GATE_RECEIPTS,
    FEATURE_ID,
    CommandResult,
    GateConfigurationError,
    ReceiptValidationError,
    gate_command_specs,
    run_gate,
    validate_receipt,
)


class _RecordingRunner:
    """Return deterministic success while recording command execution."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], Path, int]] = []

    def __call__(self, argv: tuple[str, ...], cwd: Path, timeout: int) -> CommandResult:
        self.calls.append((argv, cwd, timeout))
        return CommandResult(0, b"1 passed\n", b"")


def test_feature_075_receipt_manifest_is_the_exact_closed_registry() -> None:
    assert FEATURE_075_GATE_RECEIPTS == {
        "qg1": CHECKS_DIRECTORY / "qg1-contract.json",
        "qg2": CHECKS_DIRECTORY / "qg2-root-pathspec.json",
        "qg3": CHECKS_DIRECTORY / "qg3-destructive-isolation.json",
        "qg4": CHECKS_DIRECTORY / "qg4-project-brainstorm.json",
        "qg5": CHECKS_DIRECTORY / "qg5-feature-074.json",
        "qg6": CHECKS_DIRECTORY / "qg6-consumer-proof.json",
        "qe7": CHECKS_DIRECTORY / "qe7-regression.json",
    }


@pytest.mark.parametrize(
    ("feature", "gate", "output"),
    [
        ("074-penflow-doctor-consumer-project-hygiene", "qg2", None),
        (FEATURE_ID, "qg7", None),
        (FEATURE_ID, "qg2", Path("wrong.json")),
    ],
)
def test_invalid_feature_gate_or_output_fails_before_command_execution(
    tmp_path: Path,
    feature: str,
    gate: str,
    output: Path | None,
) -> None:
    runner = _RecordingRunner()
    selected_output = output or FEATURE_075_GATE_RECEIPTS.get(gate, Path("unknown.json"))

    with pytest.raises(GateConfigurationError):
        run_gate(
            feature=feature,
            gate=gate,
            project=tmp_path,
            output=selected_output,
            command_runner=runner,
        )

    assert runner.calls == []


def test_pass_receipt_binds_transcript_hashes_and_detects_tampering(tmp_path: Path) -> None:
    runner = _RecordingRunner()
    output = FEATURE_075_GATE_RECEIPTS["qg2"]

    receipt = run_gate(
        feature=FEATURE_ID,
        gate="qg2",
        project=tmp_path,
        output=output,
        command_runner=runner,
    )
    validate_receipt(output, tmp_path)

    assert receipt["stable_result"]["feature"] == FEATURE_ID
    assert receipt["stable_result"]["status"] == "PASS"
    assert len(runner.calls) == 1
    command = receipt["stable_result"]["commands"][0]
    transcript = tmp_path / command["stdout_path"]
    transcript.write_bytes(b"changed\n")
    with pytest.raises(ReceiptValidationError, match="hash mismatch"):
        validate_receipt(output, tmp_path)


def test_qg4_rejects_wrong_feature_marker_in_proof_artifact(tmp_path: Path) -> None:
    proof = tmp_path / CHECKS_DIRECTORY / "project-brainstorm-proof.json"
    proof.parent.mkdir(parents=True)
    proof.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "stable_result": {"feature": "074-wrong", "status": "PASS"},
            }
        ),
        encoding="utf-8",
    )

    receipt = run_gate(
        feature=FEATURE_ID,
        gate="qg4",
        project=tmp_path,
        output=FEATURE_075_GATE_RECEIPTS["qg4"],
        command_runner=_RecordingRunner(),
    )

    assert receipt["stable_result"]["status"] == "FAIL"
    assert (
        "artifact:"
        + (CHECKS_DIRECTORY / "project-brainstorm-proof.json").as_posix()
        + ":contract:FAIL"
        in receipt["stable_result"]["assertions"]
    )


def test_qg6_runs_exact_identity_test_before_live_copy_probe() -> None:
    specs = gate_command_specs("qg6")

    assert [spec.name for spec in specs] == [
        "exact-consumer-identities",
        "consumer-live-copy-proof",
    ]
    probe = specs[1]
    assert "--expected-inventory-receipt" in probe.argv
    assert probe.argv.index("--expected-inventory-receipt") < probe.argv.index("--out")
    assert probe.argv[-1] == CONSUMER_PROOF.as_posix()


def test_qe7_keeps_every_full_regression_command_bounded_at_120_seconds(
    tmp_path: Path,
) -> None:
    runner = _RecordingRunner()

    receipt = run_gate(
        feature=FEATURE_ID,
        gate="qe7",
        project=tmp_path,
        output=FEATURE_075_GATE_RECEIPTS["qe7"],
        command_runner=runner,
    )

    assert receipt["stable_result"]["status"] == "PASS"
    assert [timeout for _argv, _cwd, timeout in runner.calls] == [120, 120, 120]
