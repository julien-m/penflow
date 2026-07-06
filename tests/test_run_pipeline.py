from __future__ import annotations

import hashlib
import json
import shutil
import struct
import zlib
from pathlib import Path

from penflow.cli import main
from penflow.run_pipeline import run_pipeline


ROOT = Path(__file__).resolve().parent.parent


def copy_full_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(ROOT / "examples" / "full", workspace)
    return workspace


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", checksum)


def write_truncated_reference(workspace: Path) -> Path:
    references = workspace / "references"
    references.mkdir()
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
    ]
    assert summary["gates"]["pencil-sync"]["status"] == "SKIP"
    assert summary["gates"]["reference-fidelity"]["status"] == "SKIP"
    assert summary["gates"]["code-ir"]["report_path"] == str(workspace / "code-ir.json")


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


def test_run_pipeline_reports_missing_target_as_usage_error(tmp_path: Path, capsys) -> None:
    exit_code = main(["run", "--target", str(tmp_path / "missing"), "--json"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "target workspace not found" in captured.err
