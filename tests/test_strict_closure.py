# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
# @spec(FR-004)
# @spec(FR-005)
"""C47 strict-closure positive, adversarial, and compatibility coverage."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from penflow.cli import main
from penflow.strict_closure import validate_strict_closure

from strict_closure_fixtures import _json, _sha, _workspace

RUN_ID = "run-c6-strict-closure"
NOW = datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


def _mutate_json(path: Path, mutate: Callable[[Any], None]) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    _json(path, data)


def _codes(report: dict[str, Any]) -> set[str]:
    return {issue["code"] for issue in report["issues"]}


def test_strict_closure_passes_and_writes_only_selected_run_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace, references = _workspace(tmp_path / "workspace")
    before = {path: _sha(path) for path in workspace.rglob("*") if path.is_file()}

    report = validate_strict_closure(
        workspace,
        references=references,
        now=NOW,
        actual_max_age_seconds=3600,
    )

    assert report["status"] == "PASS"
    assert report["exit"] == 0
    assert report["run_id"] == RUN_ID
    assert all(gate["status"] == "PASS" for gate in report["gates"].values())
    assert report["filesystem"]["outside_run_dir_unchanged"] is True
    report_path = workspace / ".penflow-run" / "strict-closure.json"
    assert report_path.is_file()
    assert {
        path: _sha(path) for path in workspace.rglob("*") if path.is_file() and path != report_path
    } == before
    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 0

    def validate_with_frozen_clock(*args: Any, **kwargs: Any) -> dict[str, Any]:
        """Keep the CLI assertion on the same deterministic capture boundary."""
        return validate_strict_closure(*args, now=NOW, **kwargs)

    monkeypatch.setattr("penflow.cli.validate_strict_closure", validate_with_frozen_clock)
    assert (
        main(
            [
                "run",
                "--target",
                str(workspace),
                "--references",
                str(references),
                "--strict-closure",
                "--actual-max-age-seconds",
                "86400",
                "--json",
            ]
        )
        == 0
    )


def test_run_without_strict_closure_preserves_pipeline_compatibility(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_pipeline(target: str, **kwargs: Any) -> dict[str, Any]:
        calls.append({"target": target, **kwargs})
        return {"exit": 0, "status": "PASS"}

    monkeypatch.setattr("penflow.cli.run_pipeline", fake_pipeline)
    assert main(["run", "--target", str(tmp_path), "--json"]) == 0
    assert calls == [
        {
            "target": str(tmp_path),
            "theme_css": None,
            "references": None,
            "strict": False,
            "actual_max_age_seconds": None,
        }
    ]


@pytest.mark.parametrize(
    "name,mutate",
    [
        (
            "missing",
            lambda workspace: (
                workspace / ".penflow-run" / "pencil-persistence-receipt.json"
            ).unlink(),
        ),
        (
            "skip",
            lambda workspace: _mutate_json(
                workspace / ".mockup-validation/visual-evidence/vision-report.json",
                lambda report: report.update(status="BLOCKED_VISUAL_NOT_RUN"),
            ),
        ),
        (
            "warning-only",
            lambda workspace: _mutate_json(
                workspace / ".mockup-validation/visual-evidence/vision-report.json",
                lambda report: report.update(status="PASSED_WITH_WARNINGS"),
            ),
        ),
        (
            "stale",
            lambda workspace: _mutate_json(
                workspace / "actual-ui-tree.provenance.json",
                lambda receipt: receipt.update(capturedAt="2020-01-01T00:00:00Z"),
            ),
        ),
        (
            "replayed",
            lambda workspace: _mutate_json(
                workspace / "actual-ui-tree.provenance.json",
                lambda receipt: receipt.update(sessionId="another-run"),
            ),
        ),
        (
            "mismatched",
            lambda workspace: _mutate_json(
                workspace / ".mockup-validation/visual-evidence/manifest.json",
                lambda manifest: manifest.update(runId="another-run"),
            ),
        ),
        (
            "non-blocking",
            lambda workspace: _mutate_json(
                workspace / ".mockup-validation/visual-evidence/vision-report.json",
                lambda report: report["screens"][0]["criteria"][0].update(blocking=False),
            ),
        ),
        (
            "generic",
            lambda workspace: _mutate_json(
                workspace / ".mockup-validation/visual-evidence/vision-report.json",
                lambda report: report["screens"][0]["criteria"][0].pop("proof"),
            ),
        ),
        (
            "duplicated",
            lambda workspace: _mutate_json(
                workspace / "references/references-manifest.json",
                lambda manifest: manifest.append(dict(manifest[0])),
            ),
        ),
        (
            "tampered",
            lambda workspace: _mutate_json(
                workspace / ".penflow-run/pencil-persistence-receipt.json",
                lambda receipt: receipt.update(run_id="tampered-run"),
            ),
        ),
    ],
)
def test_named_bad_states_fail_structured(
    tmp_path: Path,
    name: str,
    mutate: Callable[[Path], None],
) -> None:
    workspace, references = _workspace(tmp_path / name)
    mutate(workspace)

    report = validate_strict_closure(
        workspace,
        references=references,
        now=NOW,
        actual_max_age_seconds=3600,
    )

    assert report["status"] == "FAIL", name
    assert report["exit"] == 1
    assert report["issues"]
    assert all(
        {"severity", "code", "path", "message"} <= issue.keys() for issue in report["issues"]
    )
    if name == "missing":
        assert report["gates"]["persistence"]["status"] == "FAIL"


def test_strict_report_rejects_changed_bound_input(tmp_path: Path) -> None:
    workspace, references = _workspace(tmp_path / "workspace")
    report = validate_strict_closure(workspace, references=references, now=NOW)
    report_path = workspace / ".penflow-run/strict-closure.json"
    assert report["status"] == "PASS"
    (workspace / "ui.pen").write_bytes(b"tampered after closure")

    assert main(["validate-report", str(report_path), "--schema", "--json"]) == 1
