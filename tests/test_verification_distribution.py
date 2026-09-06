# @spec AC-024: Given the final release candidate, when independent verification runs, then all five axes have concrete evidence, the real application pilot is present, mandatory tests pass, and normal operator steps do not increase; otherwise the 10/10 claim remains unproven. — .specs/features/077-complete-verification-workflow/spec.md#ac-024
# @spec AC-020: Given the positive and adversarial matrix, when executed through API, real source CLI subprocess, installed wheel and consumers, then normalized verdicts and obligations match with no production gate mocked healthy. — .specs/features/077-complete-verification-workflow/spec.md#ac-020
"""Verify installed-wheel boundaries through real processes, never runtime certification."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any
import zipfile

import pytest

from penflow.verification_schema import schema_issues

ROOT = Path(__file__).resolve().parents[1]


def _environment(*, source: bool = False) -> dict[str, str]:
    environment = dict(os.environ)
    for name in ("PYTHONPATH", "PYTHONHOME"):
        environment.pop(name, None)
    environment["PYTHONNOUSERSITE"] = "1"
    if source:
        environment["PYTHONPATH"] = str(ROOT)
    return environment


def _execute(command: list[str], cwd: Path, *, source: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=cwd,
        env=_environment(source=source),
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def _record(command: list[str], directory: Path, transcripts: list[dict[str, Any]]) -> None:
    result = _execute(command, directory)
    transcripts.append(
        {
            "command": command,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    )
    assert result.returncode == 0, result.stderr


def _build_wheel(
    python: Path, directory: Path, transcripts: list[dict[str, Any]]
) -> tuple[Path, dict[str, str]]:
    package_files = [
        path
        for path in (ROOT / "penflow").rglob("*")
        if path.is_file() and path.suffix in {".py", ".json"}
    ]
    before = {path.relative_to(ROOT).as_posix(): path.read_bytes() for path in package_files}
    _record(
        [
            str(python),
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(directory),
            str(ROOT),
        ],
        directory,
        transcripts,
    )
    wheels = list(directory.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        for name, raw in before.items():
            assert archive.read(name) == raw, f"wheel omitted or changed source input {name}"
            assert (ROOT / name).read_bytes() == raw, f"source changed during wheel build: {name}"
    return wheels[0], {name: hashlib.sha256(raw).hexdigest() for name, raw in before.items()}


@pytest.fixture(scope="module")
def installed_distribution(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Build a PEP517 wheel and install its declared dependencies in an isolated venv."""
    temporary = tmp_path_factory.mktemp("verification-wheel")
    transcripts: list[dict[str, Any]] = []
    python = temporary / "venv/bin/python"
    _record(
        [sys.executable, "-m", "venv", str(temporary / "venv")],
        temporary,
        transcripts,
    )
    wheel, sources = _build_wheel(python, temporary, transcripts)
    _record([str(python), "-m", "pip", "install", str(wheel)], temporary, transcripts)
    (temporary / "distribution-transcript.json").write_text(
        json.dumps(
            {
                "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
                "source_sha256": sources,
                "commands": transcripts,
            },
            indent=2,
        )
    )
    return {"directory": temporary, "python": python, "cli": temporary / "venv/bin/penflow"}


@pytest.fixture
def consumer(tmp_path: Path, installed_distribution: dict[str, Any]) -> Path:
    """Prepare real scoped Git/Doctor inputs, explicitly synthetic design data."""
    project = tmp_path / "consumer"
    project.mkdir()
    result = _execute(["git", "init", "--quiet", str(project)], tmp_path)
    assert result.returncode == 0, result.stderr
    workspace = project / "penflow"
    workspace.mkdir()
    (workspace / "ui.pen").write_text('{"version":"2.14","children":[]}')
    result = _execute(
        [
            str(installed_distribution["cli"]),
            "doctor",
            "--project",
            str(project),
            "--fix",
            "--json",
        ],
        tmp_path,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return project


def _pair(
    distribution: dict[str, Any], project: Path, arguments: list[str]
) -> list[dict[str, Any]]:
    results = []
    for command, source in (
        ([sys.executable, "-m", "penflow"], True),
        ([str(distribution["cli"])], False),
    ):
        result = _execute(
            command + arguments + ["--project", str(project), "--json"],
            project.parent,
            source=source,
        )
        assert not result.stderr, result.stderr
        results.append({"exit_code": result.returncode, "value": json.loads(result.stdout)})
    assert results[0] == results[1]
    return results


# @spec FR-010: public API and wheel parity — feature077
def test_wheel_imports_public_api_and_packaged_schema(
    installed_distribution: dict[str, Any],
) -> None:
    code = (
        "import json,penflow; from importlib.resources import files; "
        "from penflow.verification import validate_verification_report; "
        "print(json.dumps({'module':penflow.__file__,"
        "'schema':files('penflow').joinpath('schemas/c51-contracts.schema.json').is_file(),"
        "'api':callable(validate_verification_report)}))"
    )
    result = _execute(
        [str(installed_distribution["python"]), "-I", "-c", code],
        installed_distribution["directory"],
    )
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert Path(value["module"]).is_relative_to(installed_distribution["directory"].resolve())
    assert value["schema"] and value["api"]


# @spec FR-012: true CLI negative boundaries — feature077
@pytest.mark.parametrize("profile", ["design", "implementation"])
@pytest.mark.parametrize(
    "payload",
    [
        None,
        "{",
        "{}",
        '{"version":1e400}',
        '{"kind":"penflow-verification-report","profile":"unknown"}',
    ],
)
def test_wheel_c51_rejects_missing_or_invalid_report(
    installed_distribution: dict[str, Any],
    consumer: Path,
    profile: str,
    payload: str | None,
) -> None:
    report = consumer / "penflow/run-report.json"
    if payload is not None:
        report.write_text(payload)
    results = _pair(
        installed_distribution,
        consumer,
        [
            "validate-report",
            str(report),
            "--schema",
            "--required-profile",
            profile,
        ],
    )
    assert results[0]["exit_code"] == 1
    value = results[0]["value"]
    assert value["status"] == "FAIL"
    assert value["required_profile"] == profile
    assert value["issues"]
    assert schema_issues(value, "validation") == []


@pytest.mark.parametrize("invalid_version", [False, True])
def test_wheel_actual_schema_preserves_positive_and_negative(
    installed_distribution: dict[str, Any],
    consumer: Path,
    invalid_version: bool,
) -> None:
    value = {
        "version": 999 if invalid_version else 1,
        "screens": [
            {
                "screen_id": "checkout",
                "root": {
                    "id": "root",
                    "semantic_id": "checkout",
                    "role": "screen",
                    "bbox": {"x": 0, "y": 0, "width": 100, "height": 100},
                    "children": [],
                },
            }
        ],
    }
    actual = consumer / "penflow/actual-ui-tree.json"
    actual.write_text(json.dumps(value))
    results = _pair(installed_distribution, consumer, ["validate-actual", str(actual), "--schema"])
    assert results[0]["exit_code"] == (1 if invalid_version else 0)
