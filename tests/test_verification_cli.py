# @spec AC-018: Given Brainstorm pre-creating closure, when CLI/workspace/C51 design is absent or invalid, then closure blocks; given a valid revalidated design report, then no application-build prerequisite is introduced. — .specs/features/077-complete-verification-workflow/spec.md#ac-018
# @spec AC-017: Given Brainstorm penflow_contract preparation or LiveSpec noncertifying inspection/bootstrap, when workspace is absent or incomplete, then the result is explicitly noncertifying and no future closure report is required. — .specs/features/077-complete-verification-workflow/spec.md#ac-017
"""Real subprocess CLI boundaries, outside pytest's governance injections."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from penflow.verification_schema import schema_issues


@pytest.mark.parametrize("profile", ["design", "implementation"])
@pytest.mark.parametrize("project_exists", [False, True])
def test_real_cli_governance_failure_uses_c51_wrapper(
    tmp_path: Path, profile: str, project_exists: bool
) -> None:
    project = tmp_path / "consumer"
    if project_exists:
        project.mkdir()
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "penflow",
            "validate-report",
            str(project / "penflow/run-report.json"),
            "--required-profile",
            profile,
            "--project",
            str(project),
            "--schema",
            "--json",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert not result.stderr
    value = json.loads(result.stdout)
    assert value["status"] == "FAIL"
    assert schema_issues(value, "validation") == []


def test_real_cli_run_failure_uses_closed_report(tmp_path: Path) -> None:
    environment = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "penflow",
            "run",
            "--target",
            "penflow",
            "--profile",
            "design",
            "--project",
            str(tmp_path / "missing"),
            "--json",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert not result.stderr
    assert schema_issues(json.loads(result.stdout), "report") == []


@pytest.mark.parametrize("command", ["run", "validate-report"])
@pytest.mark.parametrize("profile", [None, "design"])
@pytest.mark.parametrize("empty_manifest", [False, True])
def test_real_cli_rejects_build_manifest_without_implementation_before_dispatch(
    tmp_path: Path, command: str, profile: str | None, empty_manifest: bool
) -> None:
    manifest = tmp_path / "build.json"
    report = tmp_path / "run-report.json"
    if not empty_manifest:
        manifest.write_text('{"sentinel": "build"}\n')
    report.write_text('{"sentinel": "report"}\n')
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    arguments = (
        [command, str(report)]
        if command == "validate-report"
        else [command, "--target", str(tmp_path)]
    )
    if profile:
        option = "--required-profile" if command == "validate-report" else "--profile"
        arguments.extend([option, profile])
    manifest_argument = "" if empty_manifest else str(manifest)
    arguments.extend(["--build-manifest", manifest_argument, "--project", str(tmp_path), "--json"])
    result = subprocess.run(
        [sys.executable, "-m", "penflow", *arguments],
        cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1])),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode != 0
    assert "--build-manifest requires" in result.stdout + result.stderr
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before
    if profile:
        assert not result.stderr
        kind = "validation" if command == "validate-report" else "report"
        assert schema_issues(json.loads(result.stdout), kind) == []
    else:
        assert result.returncode == 2
        assert not result.stdout
