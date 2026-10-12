# @spec FR-001 FR-002 FR-003 FR-004 FR-005 FR-006 FR-008 AC-001 AC-002 AC-003 AC-004 AC-005 AC-006 AC-007 AC-008 AC-009: Feature 075.
"""Real-Git integration matrix for the Feature 075 project boundary."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from penflow.doctor_files import EMPTY_PEN_BYTES
from penflow.project_doctor import run_project_doctor
from tests.monorepo_project_boundary_proof import run_proof

MANAGED_IGNORE_BLOCK = (
    "# >>> Penflow managed temporary artifacts v1 >>>\n"
    ".penflow-tmp/\n"
    ".penflow-run/\n"
    ".mockup-validation/\n"
    "# <<< Penflow managed temporary artifacts v1 <<<\n"
)


def _git(repository: Path, *arguments: str) -> bytes:
    """Run one bounded local Git fixture command."""

    completed = subprocess.run(
        ["git", "-C", os.fspath(repository), *arguments],
        check=False,
        capture_output=True,
        timeout=10,
        env={**os.environ, "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0"},
    )
    if completed.returncode != 0:
        pytest.fail(completed.stderr.decode("utf-8", errors="replace"))
    return completed.stdout


def _repository(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create one repository with a target and Ylune-equivalent sibling."""

    repository = tmp_path / "collective repo"
    target = repository / "projects" / "route [mobile]"
    sibling = repository / "projects" / "ylune"
    target.mkdir(parents=True)
    sibling.mkdir(parents=True)
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "penflow@example.invalid")
    _git(repository, "config", "user.name", "Penflow Boundary")
    return repository, target, sibling


def _write_healthy_project(project: Path) -> None:
    """Write the canonical canvas and owned ignore block."""

    project.joinpath("ui.pen").write_bytes(EMPTY_PEN_BYTES)
    project.joinpath(".gitignore").write_text(MANAGED_IGNORE_BLOCK, encoding="utf-8")


def _tree_digest(project: Path) -> str:
    """Digest a deterministic regular-file inventory without following links."""

    digest = hashlib.sha256()
    for path in sorted(project.rglob("*")):
        if path.is_file() and not path.is_symlink():
            digest.update(path.relative_to(project).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


@pytest.mark.parametrize("selector_kind", ["explicit_directory", "default_cwd", "regular_file"])
def test_target_selector_ignores_sibling_canvas_and_staged_temporary_data(
    tmp_path: Path,
    selector_kind: str,
) -> None:
    repository, target, sibling = _repository(tmp_path)
    _write_healthy_project(target)
    _write_healthy_project(sibling)
    selector_file = target / "penflow.config.json"
    selector_file.write_text("{}\n", encoding="utf-8")
    sibling_temp = sibling / ".penflow-run" / "staged.bin"
    sibling_temp.parent.mkdir()
    sibling_temp.write_bytes(b"sibling-only")
    _git(repository, "add", "projects")
    _git(repository, "add", "-f", sibling_temp.relative_to(repository).as_posix())
    index_before = (repository / ".git" / "index").read_bytes()
    porcelain_before = _git(repository, "status", "--porcelain=v2", "-z")
    sibling_before = _tree_digest(sibling)

    if selector_kind == "explicit_directory":
        result = run_project_doctor(target)
    elif selector_kind == "default_cwd":
        result = run_project_doctor(cwd=target)
    else:
        result = run_project_doctor(selector_file)

    assert result.exit_code == 0
    assert result.context is not None
    assert result.context.project_root == target.resolve()
    assert result.context.git_root == repository.resolve()
    assert result.report.stable_result.project_root == os.fspath(target.resolve())
    assert result.report.stable_result.git.paths == ()
    assert _tree_digest(sibling) == sibling_before
    assert (repository / ".git" / "index").read_bytes() == index_before
    assert _git(repository, "status", "--porcelain=v2", "-z") == porcelain_before


def test_nested_fix_mutates_only_selected_project(tmp_path: Path) -> None:
    repository, target, sibling = _repository(tmp_path)
    _write_healthy_project(sibling)
    root_ignore = b"repository-owner-only/\n"
    repository.joinpath(".gitignore").write_bytes(root_ignore)
    sibling_before = _tree_digest(sibling)

    result = run_project_doctor(target, fix=True)

    assert result.exit_code == 0
    assert target.joinpath("penflow/ui.pen").read_bytes() == EMPTY_PEN_BYTES
    assert target.joinpath(".gitignore").read_text(encoding="utf-8") == MANAGED_IGNORE_BLOCK
    assert repository.joinpath(".gitignore").read_bytes() == root_ignore
    assert _tree_digest(sibling) == sibling_before


def test_root_project_retains_top_equality_behavior(tmp_path: Path) -> None:
    repository, _target, _sibling = _repository(tmp_path)
    for child in tuple(repository.joinpath("projects").iterdir()):
        child.rmdir()
    repository.joinpath("projects").rmdir()
    _write_healthy_project(repository)

    result = run_project_doctor(repository)

    assert result.exit_code == 0
    assert result.context is not None
    assert result.context.project_root == result.context.git_root == repository.resolve()
    assert result.context.project_pathspec == ":(top)"


def test_executable_proof_keeps_live_projects_read_only_and_mutates_only_copy(
    tmp_path: Path,
) -> None:
    repository, target, sibling = _repository(tmp_path)
    _write_healthy_project(target)
    _write_healthy_project(sibling)
    producer_ready_pen = Path("examples/demo/ui.pen").read_bytes()
    target.joinpath("ui.pen").write_bytes(producer_ready_pen)
    sibling.joinpath("ui.pen").write_bytes(producer_ready_pen)
    _git(repository, "add", "--all")
    _git(repository, "commit", "-qm", "complete consumer fixtures")
    target_before = _tree_digest(target)
    sibling_before = _tree_digest(sibling)
    index_before = repository.joinpath(".git/index").read_bytes()
    porcelain_before = _git(repository, "status", "--porcelain=v2", "-z")

    receipt = run_proof(
        live_project=target,
        sibling=sibling,
        output=tmp_path / "feature-075-proof.json",
    )

    assert receipt["stable_result"]["status"] == "PASS"
    assert _tree_digest(target) == target_before
    assert _tree_digest(sibling) == sibling_before
    assert repository.joinpath(".git/index").read_bytes() == index_before
    assert _git(repository, "status", "--porcelain=v2", "-z") == porcelain_before
