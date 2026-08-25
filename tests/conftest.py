"""Shared pytest boundaries for governed in-process CLI producer tests."""

from __future__ import annotations

import contextlib
import io
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import penflow.cli_governance as cli_governance_module
from penflow.artifact_policy import MANAGED_IGNORE_BLOCK, PRODUCER_COMMANDS, READ_ONLY_COMMANDS
from penflow.cli import main as production_main
from penflow.project_doctor import (
    ProjectContext,
    run_project_doctor as production_project_doctor,
)

_EMPTY_PEN = '{"children":[],"version":"1.0"}\n'
_PRODUCER_ALIASES = {"migrate-flow-md-to-contract-json"}
_READ_ONLY_ALIASES = {"validate"}


def _initialize_governed_consumer(project: Path, canonical_pen: Path | None = None) -> Path:
    """Initialize Git and run Doctor before an explicitly governed producer test."""
    project.mkdir(parents=True, exist_ok=True)
    if canonical_pen is not None and not canonical_pen.exists():
        canonical_pen.parent.mkdir(parents=True, exist_ok=True)
        canonical_pen.write_text(_EMPTY_PEN, encoding="utf-8")
    if canonical_pen is None and not any(project.rglob("ui.pen")):
        (project / "ui.pen").write_text(_EMPTY_PEN, encoding="utf-8")
    # Git and Doctor are bounded system boundaries; setup must succeed before
    # the producer can prove its domain result rather than a governance error.
    subprocess.run(["git", "init", "-q"], cwd=project, check=True, timeout=10)
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        exit_code = production_main(["doctor", "--project", str(project), "--fix", "--json"])
    if exit_code != 0:
        raise AssertionError(
            f"Doctor setup failed ({exit_code}): {stdout.getvalue()} {stderr.getvalue()}"
        )
    return project


@pytest.fixture
def governed_consumer_project() -> Callable[[Path, Path | None], Path]:
    """Return the explicit Git + Doctor setup boundary for producer tests."""
    return _initialize_governed_consumer


def _prepare_consumer(project: Path, argv: list[str], command: str) -> None:
    """Create the real Git/Doctor prerequisites needed by a producer unit test."""
    if not (project / ".git").exists():
        # Git is a system boundary; setup must succeed within the fixed test budget.
        subprocess.run(["git", "init", "-q"], cwd=project, check=True, timeout=10)
    (project / ".gitignore").write_text(MANAGED_IGNORE_BLOCK, encoding="utf-8")
    pen_paths = sorted(
        path
        for path in project.rglob("*.pen")
        if ".penflow-tmp" not in path.parts and path.is_file()
    )
    if pen_paths:
        return
    requested = [
        Path(value) for value in argv if isinstance(value, str) and Path(value).name == "ui.pen"
    ]
    if command == "demo" and "--out" in argv:
        requested.insert(0, Path(argv[argv.index("--out") + 1]) / "ui.pen")
    canonical = next(
        (path for path in requested if path.is_absolute() and path.is_relative_to(project)),
        project / "ui.pen",
    )
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_text(_EMPTY_PEN, encoding="utf-8")


def _prepare_read_only_consumer(project: Path) -> None:
    """Create an isolated healthy project for a read-only command boundary."""
    project.mkdir(parents=True, exist_ok=True)
    if not (project / ".git").exists():
        # Git is a bounded system boundary; setup must succeed within 10s.
        subprocess.run(["git", "init", "-q"], cwd=project, check=True, timeout=10)
    (project / ".gitignore").write_text(MANAGED_IGNORE_BLOCK, encoding="utf-8")
    (project / "ui.pen").write_text(_EMPTY_PEN, encoding="utf-8")


@pytest.fixture(scope="session")
def read_only_health_boundary(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Any]:
    """Provide one immutable healthy project/result for read-only command unit tests."""
    project = tmp_path_factory.mktemp("read-only-health")
    _prepare_read_only_consumer(project)
    health = production_project_doctor(project)
    if health.exit_code != 0:
        raise AssertionError(f"read-only Doctor setup failed: {health.report.to_dict()}")
    return project, health


def _command_from_argv(argv: list[str]) -> str | None:
    """Return the registered command after any supported global flags."""
    commands = {
        *PRODUCER_COMMANDS,
        *READ_ONLY_COMMANDS,
        *_PRODUCER_ALIASES,
        *_READ_ONLY_ALIASES,
        "doctor",
    }
    return next((value for value in argv if value in commands), None)


@pytest.fixture(autouse=True)
def governed_in_process_cli(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    read_only_health_boundary: tuple[Path, Any],
) -> None:
    """Give legacy command-unit tests an explicit real consumer boundary.

    Tests dedicated to default-CWD governance call ``penflow.cli.main`` through
    the module and therefore bypass this harness intentionally.
    """
    module_main = getattr(request.module, "main", None)
    if module_main is not production_main:
        return

    health_project, cached_health = read_only_health_boundary
    real_project_doctor = cli_governance_module.run_project_doctor

    def cached_project_doctor(
        project: str | Path | ProjectContext, *args: Any, **kwargs: Any
    ) -> Any:
        # Read-only unit tests share an immutable health snapshot; dedicated
        # boundary tests use another project and therefore execute real Doctor.
        selected = project.project_root if isinstance(project, ProjectContext) else Path(project)
        if selected.resolve() == health_project.resolve():
            return cached_health
        return real_project_doctor(project, *args, **kwargs)

    monkeypatch.setattr(cli_governance_module, "run_project_doctor", cached_project_doctor)

    def governed_main(
        argv: list[str] | None = None,
        **kwargs: Any,
    ) -> int:
        if argv is None or not argv or "--project" in argv:
            return production_main(argv, **kwargs)
        command = _command_from_argv(argv)
        if command in {*PRODUCER_COMMANDS, *_PRODUCER_ALIASES}:
            _prepare_consumer(tmp_path, argv, command)
            return production_main([*argv, "--project", str(tmp_path)], **kwargs)
        if command in {*READ_ONLY_COMMANDS, *_READ_ONLY_ALIASES}:
            return production_main([*argv, "--project", str(health_project)], **kwargs)
        return production_main(argv, **kwargs)

    monkeypatch.setattr(request.module, "main", governed_main)
