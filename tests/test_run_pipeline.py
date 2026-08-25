from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
import sys
import zlib
from copy import deepcopy
from pathlib import Path

import pytest

import penflow.run_pipeline as pipeline_module
from penflow.cli import main
from penflow.evidence import (
    LINEAGE_DIGEST_KEYS,
    OPTIONAL_LINEAGE_STATE,
    build_run_identity,
    validate_run_identity,
)
from penflow.run_pipeline import RunPipelineError, run_pipeline

PATHOLOGICAL_MAX_AGE_TOKENS = ["nan", "inf", "-inf", "1e999", "0", "-1"]


ROOT = Path(__file__).resolve().parent.parent


def copy_full_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(ROOT / "examples" / "full", workspace)
    return workspace


def init_cli_consumer(tmp_path: Path, name: str) -> tuple[Path, Path]:
    """Create a governed Git consumer and return (project, artifact workspace)."""
    project = tmp_path / name
    project.mkdir()
    # Git/project subprocesses are bounded to 10s so system failures cannot hang CI.
    subprocess.run(["git", "init", "-q"], cwd=project, check=True, timeout=10)
    assert main(["doctor", "--project", str(project), "--fix", "--json"]) == 0
    return project, project / "penflow"


def _run_penflow_process(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run one bounded external Penflow CLI process with captured text channels."""
    # System-process contract: no shell, repository import cwd, captured text,
    # explicit project selector, non-raising status, and a hard 10-second bound.
    return subprocess.run(
        [sys.executable, "-m", "penflow", *args, "--project", str(project), "--json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


@pytest.fixture
def fresh_demo_cli(tmp_path: Path) -> tuple[Path, Path, dict]:
    """Bootstrap one governed demo through the external process boundary."""
    project, workspace = init_cli_consumer(tmp_path, "fresh-demo-project")
    result = _run_penflow_process(project, "demo", "--out", str(workspace))
    assert result.returncode == 0
    return project, workspace, json.loads(result.stdout)


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", checksum)


def write_truncated_reference(workspace: Path) -> Path:
    references = workspace / "references"
    references.mkdir(exist_ok=True)
    reference_png = references / "checkout-ref.png"
    reference_png.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(b"\x00"))
        + _png_chunk(b"IEND", b"")
    )
    (references / "references-manifest.json").write_text(
        json.dumps(
            [
                {
                    "screen_id": "checkout",
                    "file": "checkout-ref.png",
                    "sha256": hashlib.sha256(reference_png.read_bytes()).hexdigest(),
                    "source": "unit-test",
                    "mapping": {
                        "surface": "web",
                        "screen_id": "checkout",
                        "region_id": "checkout.main",
                        "state": "default",
                        "crop": {
                            "x": 0,
                            "y": 0,
                            "width": 8,
                            "height": 8,
                            "source_width": 8,
                            "source_height": 8,
                        },
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    return references


def test_run_pipeline_returns_single_gate_summary_json(tmp_path: Path) -> None:
    workspace = copy_full_workspace(tmp_path)

    summary = run_pipeline(workspace)

    assert summary["kind"] == "penflow-run-summary"
    assert summary["target"] == str(workspace)
    assert isinstance(summary["exit"], int)
    assert (workspace / "run-report.json").exists()
    assert list(summary["gates"]) == [
        "validate-flow-contract",
        "export-semantic-tree",
        "pencil-sync",
        "map-pencil-context",
        "validate-pen",
        "export-expected",
        "lint-tokens",
        "check-consistency",
        "audit-visual",
        "detect-drift",
        "validate-visual-evidence",
        "reference-fidelity",
        "code-ir",
        "validate-actual-provenance",
    ]
    assert summary["gates"]["validate-actual-provenance"]["status"] == "PASS"
    assert summary["gates"]["pencil-sync"]["status"] == "SKIP"
    assert summary["gates"]["reference-fidelity"]["status"] == "SKIP"
    assert summary["gates"]["code-ir"]["report_path"] == str(workspace / "code-ir.json")
    identity = {key: summary[key] for key in ("runId", "version", "lineage", "provenance")}
    assert summary["version"] == 1
    assert summary["runId"].startswith("penflow-v1-")
    assert tuple(summary["lineage"]["digests"]) == LINEAGE_DIGEST_KEYS
    assert summary["lineage"]["missing"] == []
    assert summary["provenance"]["renderer"] == pipeline_module.RUN_RENDERER
    assert summary["provenance"]["exportTimestamp"].endswith("Z")
    assert all(
        len(digest) == 64 and digest == digest.lower()
        for digest in summary["lineage"]["digests"].values()
    )
    for gate in summary["gates"].values():
        assert {key: gate[key] for key in identity} == identity


def test_run_pipeline_cli_prints_json_and_aggregate_exit(tmp_path: Path, capsys) -> None:
    workspace = copy_full_workspace(tmp_path)

    exit_code = main(["run", "--target", str(workspace), "--json"])
    captured = capsys.readouterr()
    summary = json.loads(captured.out)

    assert exit_code == summary["exit"]
    assert summary["gates"]["validate-flow-contract"]["exit"] == 0
    assert summary["gates"]["code-ir"]["status"] == "PASS"


def test_run_pipeline_finds_handoff_visual_evidence_layout(tmp_path: Path) -> None:
    handoff = tmp_path / "handoff"
    workspace = handoff / "penflow"
    shutil.copytree(ROOT / "examples" / "full", workspace)
    validation = handoff / "validation" / "mockup-validation"
    validation.parent.mkdir(parents=True)
    shutil.move(str(workspace / ".mockup-validation"), validation)

    summary = run_pipeline(workspace)

    visual_gate = summary["gates"]["validate-visual-evidence"]
    assert visual_gate["status"] == "PASS"
    assert visual_gate["exit"] == 0


def test_run_pipeline_refreshes_stale_run_gate_report(tmp_path: Path) -> None:
    workspace = copy_full_workspace(tmp_path)
    validate_pen_report = workspace / ".penflow-run" / "validate-pen.json"
    validate_pen_report.parent.mkdir(parents=True)
    validate_pen_report.write_text(
        json.dumps(
            {
                "status": "FAIL",
                "issues": [
                    {
                        "code": "pen.context.missing",
                        "message": "stale issue",
                        "severity": "error",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = run_pipeline(workspace)
    refreshed_report = json.loads(validate_pen_report.read_text(encoding="utf-8"))

    assert summary["gates"]["validate-pen"]["status"] == "PASS"
    assert refreshed_report["status"] == "PASS"
    assert refreshed_report["issues"] == []


def test_run_pipeline_records_invalid_reference_png_as_gate_report(tmp_path: Path) -> None:
    workspace = copy_full_workspace(tmp_path)
    references = write_truncated_reference(workspace)

    summary = run_pipeline(workspace, references=references)
    reference_gate = summary["gates"]["reference-fidelity"]
    report = json.loads(Path(reference_gate["report_path"]).read_text(encoding="utf-8"))

    assert reference_gate["status"] == "FAIL"
    assert reference_gate["exit"] == 1
    assert report["status"] == "FAIL"
    assert "reference.image.invalid" in {issue["code"] for issue in report["issues"]}
    assert "Traceback" not in json.dumps(report)


# @spec(AC-009)
def test_run_pipeline_tracked_demo_passes_without_test_materialization(
    tmp_path: Path,
) -> None:
    workspace = copy_full_workspace(tmp_path)

    summary = run_pipeline(workspace)

    assert summary["exit"] == 0
    assert summary["lineage"]["missing"] == []
    expected_optional_digest = hashlib.sha256(
        json.dumps(
            {"source": "theme", "value": OPTIONAL_LINEAGE_STATE},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert summary["lineage"]["digests"]["theme"] == expected_optional_digest


# @spec(AC-009)
def test_fresh_demo_cli_bootstrap_and_run_pass(fresh_demo_cli) -> None:
    project, workspace, demo_payload = fresh_demo_cli
    run_result = _run_penflow_process(project, "run", "--target", str(workspace))
    run_payload = json.loads(run_result.stdout)

    assert demo_payload["status"] == "PASS"
    assert (workspace / "actual-ui-tree.json").is_file()
    assert run_result.returncode == 0
    assert run_payload["exit"] == 0
    assert len(run_payload["gates"]) == 14
    assert run_payload["gates"]["validate-actual-provenance"]["exit"] == 0
    assert all(gate["exit"] == 0 for gate in run_payload["gates"].values())


def test_fresh_demo_cli_missing_actual_fails_closed(fresh_demo_cli) -> None:
    project, workspace, _ = fresh_demo_cli
    (workspace / "actual-ui-tree.json").unlink()
    missing_result = _run_penflow_process(project, "run", "--target", str(workspace))
    missing_payload = json.loads(missing_result.stdout)

    assert missing_result.returncode != 0
    assert missing_payload["lineage"]["missing"] == ["actual"]
    assert all(gate["exit"] != 0 for gate in missing_payload["gates"].values())


@pytest.mark.parametrize("mutation", ["missing", "corrupt"])
def test_fresh_demo_visual_evidence_is_load_bearing(
    tmp_path: Path,
    mutation: str,
) -> None:
    project, workspace = init_cli_consumer(tmp_path, f"fresh-demo-{mutation}-project")
    demo_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "penflow",
            "demo",
            "--project",
            str(project),
            "--out",
            str(workspace),
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert demo_result.returncode == 0

    png = workspace / ".mockup-validation" / "visual-evidence" / "checkoutScreen.png"
    if mutation == "missing":
        png.unlink()
    else:
        png.write_bytes(b"corrupt-static-demo-fixture")

    run_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "penflow",
            "run",
            "--project",
            str(project),
            "--target",
            str(workspace),
            "--json",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    payload = json.loads(run_result.stdout)

    assert run_result.returncode != 0
    assert payload["exit"] != 0
    assert payload["gates"]["validate-visual-evidence"]["exit"] != 0


def test_run_pipeline_reports_missing_target_as_usage_error(tmp_path: Path, capsys) -> None:
    exit_code = main(["run", "--target", str(tmp_path / "missing"), "--json"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "target workspace not found" in captured.err


# @spec(AC-007)
def test_run_identity_round_trips_through_manifest_schema(tmp_path: Path, capsys) -> None:
    workspace = copy_full_workspace(tmp_path)
    summary = run_pipeline(workspace)
    manifest_path = workspace / ".mockup-validation" / "visual-evidence" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({key: summary[key] for key in ("runId", "version", "lineage")})
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert main(["validate-report", str(manifest_path), "--schema", "--json"]) == 0
    capsys.readouterr()
    invalid = deepcopy(manifest)
    invalid["lineage"]["digests"]["actual"] = "A" * 64
    invalid_path = workspace / "invalid-lineage-manifest.json"
    invalid_path.write_text(json.dumps(invalid), encoding="utf-8")
    assert main(["validate-report", str(invalid_path), "--schema", "--json"]) == 1
    capsys.readouterr()
    partial = deepcopy(manifest)
    del partial["version"]
    partial_path = workspace / "partial-lineage-manifest.json"
    partial_path.write_text(json.dumps(partial), encoding="utf-8")
    assert main(["validate-report", str(partial_path), "--schema", "--json"]) == 1
    capsys.readouterr()


# @spec(AC-010)
def test_run_provenance_ignores_stale_manifest_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = copy_full_workspace(tmp_path)
    manifest_path = workspace / ".mockup-validation" / "visual-evidence" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["renderer"] = "stale-renderer"
    manifest["validatedAt"] = "1999-12-31T23:59:59Z"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    current_timestamp = "2026-07-24T11:22:33.123456Z"
    monkeypatch.setattr(
        pipeline_module,
        "_current_export_timestamp",
        lambda: current_timestamp,
    )

    summary = run_pipeline(workspace)
    expected = build_run_identity(
        ui_pen=workspace / "ui.pen",
        contract=workspace / "flow-ui-contract" / "contract.json",
        expected=workspace / "expected-ui-tree.json",
        actual=workspace / "actual-ui-tree.json",
        theme=None,
        references=None,
        renderer=pipeline_module.RUN_RENDERER,
        export_timestamp=current_timestamp,
    )

    assert summary["exit"] == 0
    assert summary["provenance"] == {
        "renderer": pipeline_module.RUN_RENDERER,
        "exportTimestamp": current_timestamp,
    }
    assert summary["lineage"]["digests"]["renderer"] == expected["lineage"]["digests"]["renderer"]
    assert (
        summary["lineage"]["digests"]["exportTimestamp"]
        == expected["lineage"]["digests"]["exportTimestamp"]
    )
    assert all(gate["provenance"] == summary["provenance"] for gate in summary["gates"].values())


# @spec(AC-008)
@pytest.mark.parametrize("digest_key", LINEAGE_DIGEST_KEYS)
def test_each_lineage_digest_divergence_is_rejected(
    tmp_path: Path,
    digest_key: str,
) -> None:
    workspace = copy_full_workspace(tmp_path)
    summary = run_pipeline(workspace)
    expected = {key: summary[key] for key in ("runId", "version", "lineage")}
    candidate = deepcopy(expected)
    candidate["lineage"]["digests"][digest_key] = "0" * 64

    issues = validate_run_identity(candidate, expected)
    gates = {
        "mutated": {
            "status": "PASS",
            "report_path": "mutated.json",
            "exit": 0,
        }
        | candidate
    }
    pipeline_module._validate_gate_citations(gates, expected)

    assert any(
        issue["code"] == "evidence.lineage.digest_mismatch"
        and issue["path"] == f"$.lineage.digests.{digest_key}"
        for issue in issues
    )
    assert gates["mutated"]["status"] == "FAIL"
    assert gates["mutated"]["exit"] == 1


# @spec(FR-012)
def test_lineage_source_mutation_during_run_is_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = copy_full_workspace(tmp_path)
    original = pipeline_module._gate_validate_flow_contract

    def mutate_actual_tree(contract_path: Path, strict: bool) -> tuple[dict, int]:
        (workspace / "actual-ui-tree.json").write_text(
            json.dumps({"screens": []}),
            encoding="utf-8",
        )
        return original(contract_path, strict)

    monkeypatch.setattr(
        pipeline_module,
        "_gate_validate_flow_contract",
        mutate_actual_tree,
    )

    summary = run_pipeline(workspace)
    first_gate = summary["gates"]["validate-flow-contract"]

    assert summary["exit"] == 1
    assert first_gate["exit"] == 1
    assert first_gate["status"] == "FAIL"
    assert {issue["path"] for issue in first_gate["lineage_issues"]} >= {"$.lineage.digests.actual"}


def test_missing_lineage_source_is_nonzero(tmp_path: Path) -> None:
    workspace = copy_full_workspace(tmp_path)
    (workspace / "actual-ui-tree.json").unlink()

    summary = run_pipeline(workspace)

    assert summary["exit"] == 1
    assert summary["lineage"]["missing"] == ["actual"]
    assert all(gate["exit"] != 0 for gate in summary["gates"].values())


# @spec(AC-009)
def test_explicit_missing_optional_source_is_nonzero(tmp_path: Path) -> None:
    workspace = copy_full_workspace(tmp_path)

    summary = run_pipeline(workspace, theme_css=workspace / "missing-theme.css")

    assert summary["exit"] != 0
    assert summary["lineage"]["missing"] == ["theme"]
    assert all(gate["exit"] != 0 for gate in summary["gates"].values())


# @spec(AC-013)
def test_run_pipeline_rejects_tampered_actual_provenance(tmp_path: Path) -> None:
    """The run gate binds the actual tree to its receipt: a forged digest fails."""
    workspace = copy_full_workspace(tmp_path)
    receipt_path = workspace / "actual-ui-tree.provenance.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["content"]["sha256"] = "0" * 64
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

    summary = run_pipeline(workspace)
    gate = summary["gates"]["validate-actual-provenance"]
    report = json.loads(Path(gate["report_path"]).read_text(encoding="utf-8"))

    assert summary["exit"] != 0
    assert gate["status"] == "FAIL"
    assert gate["exit"] == 1
    assert "provenance.digest.mismatch" in {issue["code"] for issue in report["issues"]}


# @spec(AC-013)
def test_run_pipeline_rejects_missing_actual_provenance_receipt(tmp_path: Path) -> None:
    """A required actual tree without a provenance receipt fails closed."""
    workspace = copy_full_workspace(tmp_path)
    (workspace / "actual-ui-tree.provenance.json").unlink()

    summary = run_pipeline(workspace)
    gate = summary["gates"]["validate-actual-provenance"]
    report = json.loads(Path(gate["report_path"]).read_text(encoding="utf-8"))

    assert summary["exit"] != 0
    assert gate["exit"] == 1
    assert "provenance.receipt.missing" in {issue["code"] for issue in report["issues"]}


RUN_BOUNDARY = "2026-07-24T12:00:00.000000Z"


def _write_runtime_actual_and_receipt(
    workspace: Path,
    captured_at: str,
    *,
    content_path: str = "actual-ui-tree.json",
    corrupt_sha: bool = False,
) -> None:
    """Replace the demo fixture with a non-derived runtime-capture + receipt.

    A distinct measured geometry keeps the actual independent of the expected
    tree so freshness is the only reason under test.
    """
    actual_path = workspace / "actual-ui-tree.json"
    tree = {
        "version": 1,
        "screen_id": "checkout",
        "viewport": {"width": 390, "height": 844},
        "root": {
            "id": "checkout",
            "role": "screen",
            "bbox": {"x": 0, "y": 0, "width": 390, "height": 844},
            "children": [
                {
                    "id": "checkout.pay-now",
                    "role": "button",
                    "bbox": {"x": 24, "y": 700, "width": 342, "height": 44},
                    "children": [],
                }
            ],
        },
    }
    actual_path.write_text(json.dumps(tree, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(actual_path.read_bytes()).hexdigest()
    receipt = {
        "kind": "penflow-actual-provenance",
        "version": 1,
        "sourceKind": "runtime-capture",
        "producer": {"name": "web-dom-adapter", "version": "1.4.0"},
        "capturedAt": captured_at,
        "target": {"surface": "web", "screen_id": "checkout"},
        "content": {
            "path": content_path,
            "sha256": "0" * 64 if corrupt_sha else digest,
        },
    }
    (workspace / "actual-ui-tree.provenance.json").write_text(json.dumps(receipt), encoding="utf-8")


# @spec(AC-016)
@pytest.mark.parametrize(
    ("captured_at", "expected_code"),
    [
        ("2026-07-01T00:00:00Z", "provenance.timestamp.stale"),
        ("2027-01-01T00:00:00Z", "provenance.timestamp.future"),
        ("not-a-date", "provenance.timestamp.invalid"),
    ],
)
def test_run_gate_applies_runtime_capture_freshness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    captured_at: str,
    expected_code: str,
) -> None:
    """The main run gate — not only the CLI — rejects a runtime-capture whose
    capturedAt is stale, in the future, or unparseable relative to the current
    run boundary."""
    workspace = copy_full_workspace(tmp_path)
    _write_runtime_actual_and_receipt(workspace, captured_at)
    monkeypatch.setattr(pipeline_module, "_current_export_timestamp", lambda: RUN_BOUNDARY)

    summary = run_pipeline(workspace)
    gate = summary["gates"]["validate-actual-provenance"]
    report = json.loads(Path(gate["report_path"]).read_text(encoding="utf-8"))

    assert summary["exit"] != 0
    assert gate["status"] == "FAIL"
    assert gate["exit"] == 1
    assert {issue["code"] for issue in report["issues"]} == {expected_code}
    assert report["now"] == "2026-07-24T12:00:00+00:00"
    assert report["max_age_seconds"] == pipeline_module.RUN_ACTUAL_FRESHNESS_MAX_AGE_SECONDS


# @spec(AC-016)
def test_run_gate_exempts_static_demo_fixture_from_freshness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A frozen static-demo-fixture stays green even when the run boundary is far
    in the future, and that exemption is unreachable by a runtime-capture with
    the same old capturedAt (which fails stale)."""
    workspace = copy_full_workspace(tmp_path)
    monkeypatch.setattr(
        pipeline_module, "_current_export_timestamp", lambda: "2099-01-01T00:00:00.000000Z"
    )

    summary = run_pipeline(workspace)
    gate = summary["gates"]["validate-actual-provenance"]
    assert gate["status"] == "PASS"
    assert gate["exit"] == 0

    # The very same capturedAt as a runtime-capture is rejected: the exemption
    # cannot be obtained with sourceKind=runtime-capture.
    fixture_receipt = json.loads(
        (workspace / "actual-ui-tree.provenance.json").read_text(encoding="utf-8")
    )
    _write_runtime_actual_and_receipt(workspace, fixture_receipt["capturedAt"])
    summary_capture = run_pipeline(workspace)
    capture_gate = summary_capture["gates"]["validate-actual-provenance"]
    report = json.loads(Path(capture_gate["report_path"]).read_text(encoding="utf-8"))
    assert capture_gate["exit"] == 1
    assert "provenance.timestamp.stale" in {issue["code"] for issue in report["issues"]}


# @spec(AC-016)
def test_run_gate_rejects_content_path_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A receipt whose content.path names a different file than the validated
    actual tree fails closed."""
    workspace = copy_full_workspace(tmp_path)
    # capturedAt equals the boundary so freshness passes and path is the reason.
    _write_runtime_actual_and_receipt(workspace, RUN_BOUNDARY, content_path="some-other-tree.json")
    monkeypatch.setattr(pipeline_module, "_current_export_timestamp", lambda: RUN_BOUNDARY)

    summary = run_pipeline(workspace)
    gate = summary["gates"]["validate-actual-provenance"]
    report = json.loads(Path(gate["report_path"]).read_text(encoding="utf-8"))

    assert gate["exit"] == 1
    assert {issue["code"] for issue in report["issues"]} == {"provenance.content.path_mismatch"}


# @spec(AC-017)
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), 1e999, 0.0, -1.0])
def test_run_pipeline_rejects_pathological_max_age(tmp_path: Path, bad: float) -> None:
    """A non-finite or non-positive freshness window fails closed before any
    report is written, so freshness can never be silently disarmed (fail-open)."""
    workspace = copy_full_workspace(tmp_path)
    with pytest.raises(RunPipelineError):
        run_pipeline(workspace, actual_max_age_seconds=bad)
    assert not (workspace / "run-report.json").exists()


# @spec(AC-017)
@pytest.mark.parametrize("token", PATHOLOGICAL_MAX_AGE_TOKENS)
def test_run_cli_rejects_pathological_max_age(tmp_path: Path, capsys, token: str) -> None:
    workspace = copy_full_workspace(tmp_path)
    # `--flag=value` form so a leading-dash value (e.g. -inf) reaches our guard
    # rather than being parsed by argparse as a separate option.
    exit_code = main(
        ["run", "--target", str(workspace), f"--actual-max-age-seconds={token}", "--json"]
    )
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "max_age_seconds must be" in captured.err
    assert captured.out.strip() == ""  # no JSON body emitted
    assert not (workspace / "run-report.json").exists()


# @spec(AC-017)
@pytest.mark.parametrize("token", PATHOLOGICAL_MAX_AGE_TOKENS)
def test_validate_actual_provenance_cli_rejects_pathological_max_age(
    tmp_path: Path, capsys, token: str
) -> None:
    workspace = copy_full_workspace(tmp_path)
    exit_code = main(
        [
            "validate-actual-provenance",
            str(workspace),
            f"--max-age-seconds={token}",
            "--json",
        ]
    )
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "max_age_seconds must be" in captured.err
    assert captured.out.strip() == ""
    # No non-standard JSON tokens leaked to stderr/stdout either.
    assert "NaN" not in captured.out and "Infinity" not in captured.out


# @spec(AC-017)
def test_run_cli_accepts_valid_max_age(tmp_path: Path, capsys) -> None:
    """Positive control: a finite positive window runs normally."""
    workspace = copy_full_workspace(tmp_path)
    exit_code = main(
        ["run", "--target", str(workspace), "--actual-max-age-seconds", "3600", "--json"]
    )
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert exit_code == summary["exit"] == 0
    report = json.loads(
        (workspace / ".penflow-run" / "validate-actual-provenance.json").read_text(encoding="utf-8")
    )
    assert report["max_age_seconds"] == 3600.0


# @spec(AC-017)
def test_run_boundary_unparseable_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the internal run boundary cannot be parsed we fail explicitly instead
    of passing now=None and silently disabling stale/future checks."""
    workspace = copy_full_workspace(tmp_path)
    monkeypatch.setattr(pipeline_module, "_current_export_timestamp", lambda: "not-a-timestamp")
    with pytest.raises(RunPipelineError):
        run_pipeline(workspace)
    assert not (workspace / "run-report.json").exists()


# @spec(AC-017)
@pytest.mark.parametrize(
    ("content_path", "code"),
    [
        ("/etc/actual-ui-tree.json", "provenance.content.path_invalid"),
        ("../actual-ui-tree.json", "provenance.content.path_invalid"),
    ],
)
def test_run_gate_rejects_unsafe_content_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    content_path: str,
    code: str,
) -> None:
    workspace = copy_full_workspace(tmp_path)
    _write_runtime_actual_and_receipt(workspace, RUN_BOUNDARY, content_path=content_path)
    monkeypatch.setattr(pipeline_module, "_current_export_timestamp", lambda: RUN_BOUNDARY)

    summary = run_pipeline(workspace)
    gate = summary["gates"]["validate-actual-provenance"]
    report = json.loads(Path(gate["report_path"]).read_text(encoding="utf-8"))
    assert gate["exit"] == 1
    assert code in {issue["code"] for issue in report["issues"]}


# @spec(AC-017)
def test_run_report_contains_no_nonstandard_json(tmp_path: Path) -> None:
    """No written report may contain NaN/Infinity (allow_nan=False)."""
    workspace = copy_full_workspace(tmp_path)
    run_pipeline(workspace)
    for report_file in [
        workspace / "run-report.json",
        workspace / ".penflow-run" / "validate-actual-provenance.json",
    ]:
        text = report_file.read_text(encoding="utf-8")
        assert "NaN" not in text
        assert "Infinity" not in text


# @spec(AC-010)
def test_gate_provenance_divergence_is_nonzero(tmp_path: Path) -> None:
    workspace = copy_full_workspace(tmp_path)
    summary = run_pipeline(workspace)
    expected = {key: summary[key] for key in ("runId", "version", "lineage", "provenance")}
    candidate = deepcopy(expected)
    candidate["provenance"]["renderer"] = "stale-renderer"
    gates = {
        "mutated": {
            "status": "PASS",
            "report_path": "mutated.json",
            "exit": 0,
        }
        | candidate
    }

    pipeline_module._validate_gate_citations(gates, expected)

    assert gates["mutated"]["status"] == "FAIL"
    assert gates["mutated"]["exit"] == 1
    assert gates["mutated"]["lineage_issues"] == [
        {
            "code": "evidence.lineage.provenance_mismatch",
            "message": "renderer or export timestamp does not match the current run provenance",
            "path": "$.provenance",
            "severity": "error",
        }
    ]
