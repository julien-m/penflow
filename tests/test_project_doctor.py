"""Hermetic Git and filesystem tests for the consumer-project Doctor."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from penflow.project_doctor import (
    DoctorResult,
    ProjectDoctor,
    ProjectResolutionError,
    resolve_project_context,
    run_project_doctor,
)
from penflow.doctor_context import GitCommandResult, SubprocessGitGateway
from penflow.schema_cache import validator_for


EMPTY_PEN_BYTES = b'{"children":[],"version":"1.0"}\n'
MANAGED_IGNORE_BLOCK = (
    "# >>> Penflow managed temporary artifacts v1 >>>\n"
    ".penflow-tmp/\n"
    ".penflow-run/\n"
    ".mockup-validation/\n"
    "# <<< Penflow managed temporary artifacts v1 <<<\n"
)


def _git(repository: Path, *arguments: str, input_bytes: bytes | None = None) -> bytes:
    """Run deterministic Git fixture setup and return stdout bytes.

    Git is the real integration boundary under test. Calls are local-only, bounded,
    non-interactive, and fail the test immediately on any nonzero exit.
    """

    environment = {**os.environ, "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0"}
    completed = subprocess.run(
        ["git", "-C", os.fspath(repository), *arguments],
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
        env=environment,
    )
    if completed.returncode != 0:
        pytest.fail(completed.stderr.decode("utf-8", errors="replace"))
    return completed.stdout


def _repository(tmp_path: Path) -> Path:
    """Create an isolated non-bare Git worktree."""

    repository = tmp_path / "consumer"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "penflow@example.test")
    _git(repository, "config", "user.name", "Penflow Tests")
    return repository


def _write_valid_pen(path: Path) -> None:
    """Write the smallest structurally valid Pencil document."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(EMPTY_PEN_BYTES)


def _index_digest(repository: Path) -> str | None:
    """Hash the Git index without creating it when the repository is empty."""

    index_path = repository / ".git" / "index"
    return hashlib.sha256(index_path.read_bytes()).hexdigest() if index_path.exists() else None


def _finding_codes(result: DoctorResult) -> set[str]:
    """Extract stable finding codes from a Doctor result."""

    return {finding.code for finding in result.report.stable_result.findings}


class _RecordingGitGateway:
    """Record exact Git argv while delegating to the bounded real gateway."""

    def __init__(self) -> None:
        self.calls: list[tuple[Path, tuple[str, ...], bytes | None]] = []
        self._delegate = SubprocessGitGateway()

    def run(
        self,
        directory: Path,
        arguments: tuple[str, ...],
        *,
        input_bytes: bytes | None = None,
    ) -> Any:
        self.calls.append((directory, arguments, input_bytes))
        return self._delegate.run(directory, arguments, input_bytes=input_bytes)


class _ScopeEscapeGitGateway(_RecordingGitGateway):
    """Inject one impossible sibling record into a scoped Git response."""

    def run(
        self,
        directory: Path,
        arguments: tuple[str, ...],
        *,
        input_bytes: bytes | None = None,
    ) -> Any:
        if arguments[:2] == ("ls-files", "--stage"):
            return GitCommandResult(
                stdout=(
                    b"100644 0000000000000000000000000000000000000000 0\t"
                    b"packages/sibling/.penflow-run/escape.bin\0"
                ),
                stderr=b"",
            )
        return super().run(directory, arguments, input_bytes=input_bytes)


def test_resolve_project_context_uses_nearest_nested_worktree(tmp_path: Path) -> None:
    outer = _repository(tmp_path)
    nested = outer / "packages" / "app"
    nested.mkdir(parents=True)
    _git(nested, "init", "-q")
    cwd = nested / "sources" / "feature"
    cwd.mkdir(parents=True)

    context = resolve_project_context(cwd=cwd)

    assert context.project_root == cwd.resolve()
    assert context.git_root == nested.resolve()
    assert context.project_pathspec == ":(top,literal)sources/feature"
    assert context.root == cwd.resolve()
    assert context.invocation_path == cwd.resolve()
    assert context.repository_kind == "standard"
    assert not context.explicit_project


def test_resolve_project_context_accepts_explicit_file_path(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    target = repository / "nested" / "input.json"
    target.parent.mkdir()
    target.write_text("{}\n", encoding="utf-8")

    context = resolve_project_context(target, cwd=tmp_path)

    assert context.project_root == target.parent.resolve()
    assert context.git_root == repository.resolve()
    assert context.project_pathspec == ":(top,literal)nested"
    assert context.root == target.parent.resolve()
    assert context.invocation_path == target.resolve()
    assert context.explicit_project


def test_resolve_project_context_keeps_explicit_nested_directory(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    target = repository / "packages" / "design [v2]"
    target.mkdir(parents=True)

    context = resolve_project_context(target)

    assert context.project_root == target.resolve()
    assert context.git_root == repository.resolve()
    assert context.project_pathspec == ":(top,literal)packages/design [v2]"


def test_resolve_project_context_root_project_uses_top_equality_pathspec(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    context = resolve_project_context(repository)

    assert context.project_root == repository.resolve()
    assert context.git_root == repository.resolve()
    assert context.project_pathspec == ":(top)"


def test_resolve_project_context_rejects_missing_and_non_git_paths(tmp_path: Path) -> None:
    with pytest.raises(ProjectResolutionError, match="project path does not exist") as missing:
        resolve_project_context(tmp_path / "missing")
    assert missing.value.code == "project.path_missing"

    with pytest.raises(ProjectResolutionError, match="not inside a Git worktree") as non_git:
        resolve_project_context(tmp_path)
    assert non_git.value.code == "not_git_project"


def test_project_context_rejects_paths_outside_consumer_root(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    context = resolve_project_context(repository)

    assert context.resolve_path("artifacts/report.json") == repository / "artifacts/report.json"
    with pytest.raises(ValueError, match="outside consumer project root"):
        context.resolve_path(tmp_path / "outside.json")


def test_nested_doctor_runs_content_enumerators_from_git_root_with_one_pathspec(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    target = repository / "packages" / "target [v2]"
    target.mkdir(parents=True)
    _write_valid_pen(target / "ui.pen")
    target.joinpath(".gitignore").write_text(MANAGED_IGNORE_BLOCK, encoding="utf-8")
    gateway = _RecordingGitGateway()

    result = ProjectDoctor(gateway).run(target)

    assert result.exit_code == 0
    expected_pathspec = ":(top,literal)packages/target [v2]"
    content_calls = [
        (directory, arguments)
        for directory, arguments, _input in gateway.calls
        if arguments[0] in {"status", "ls-files", "diff"}
    ]
    assert content_calls
    for directory, arguments in content_calls:
        assert directory == repository.resolve()
        assert arguments.count("--") == 1
        separator = arguments.index("--")
        assert arguments[separator + 1 :] == (expected_pathspec,)


def test_nested_doctor_classifies_only_exact_target_temporary_roots(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    target = repository / "packages" / "target"
    sibling = repository / "packages" / "sibling"
    target.mkdir(parents=True)
    sibling.mkdir(parents=True)
    _write_valid_pen(target / "ui.pen")
    _write_valid_pen(sibling / "ui.pen")
    target.joinpath(".gitignore").write_text(MANAGED_IGNORE_BLOCK, encoding="utf-8")
    sibling.joinpath(".gitignore").write_text(MANAGED_IGNORE_BLOCK, encoding="utf-8")
    target_temp = target / ".penflow-run" / "target.bin"
    target_lookalike = target / ".penflow-run-old" / "ordinary.bin"
    sibling_temp = sibling / ".penflow-run" / "sibling.bin"
    for path in (target_temp, target_lookalike, sibling_temp):
        path.parent.mkdir(parents=True)
        path.write_bytes(path.name.encode("utf-8"))
        _git(repository, "add", "-f", path.relative_to(repository).as_posix())

    result = run_project_doctor(target)

    assert result.exit_code == 1
    assert [state.relative_path for state in result.report.stable_result.git.paths] == [
        ".penflow-run/target.bin"
    ]


@pytest.mark.parametrize("temporary_root", [".penflow-tmp", ".penflow-run", ".mockup-validation"])
def test_doctor_excludes_pen_snapshots_inside_exact_temporary_roots(
    tmp_path: Path,
    temporary_root: str,
) -> None:
    repository = _repository(tmp_path)
    _write_valid_pen(repository / "ui.pen")
    _write_valid_pen(repository / temporary_root / "persistence" / "snapshot-ui.pen")
    repository.joinpath(".gitignore").write_text(MANAGED_IGNORE_BLOCK, encoding="utf-8")

    result = run_project_doctor(repository)

    assert result.exit_code == 0
    assert result.report.stable_result.canonical_pen == "ui.pen"


def test_nested_doctor_translates_impossible_git_scope_escape_to_internal_error(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    target = repository / "packages" / "target"
    target.mkdir(parents=True)
    _write_valid_pen(target / "ui.pen")
    target.joinpath(".gitignore").write_text(MANAGED_IGNORE_BLOCK, encoding="utf-8")

    result = ProjectDoctor(_ScopeEscapeGitGateway()).run(target)

    assert result.exit_code == 3
    assert result.report.stable_result.status == "ERROR"
    assert _finding_codes(result) == {"doctor.internal_error"}


def test_doctor_reuses_pre_resolved_context_without_widening(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    target = repository / "packages" / "target"
    sibling = repository / "packages" / "sibling"
    target.mkdir(parents=True)
    sibling.mkdir(parents=True)
    _write_valid_pen(sibling / "ui.pen")
    sibling_ignore = b"sibling-only/\n"
    sibling.joinpath(".gitignore").write_bytes(sibling_ignore)
    context = resolve_project_context(target)

    result = ProjectDoctor().run(context, fix=True)

    assert result.exit_code == 0
    assert result.context is context
    assert result.report.stable_result.project_root == os.fspath(target.resolve())
    assert target.joinpath("penflow/ui.pen").read_bytes() == EMPTY_PEN_BYTES
    assert target.joinpath(".gitignore").read_text(encoding="utf-8") == MANAGED_IGNORE_BLOCK
    assert sibling.joinpath("ui.pen").read_bytes() == EMPTY_PEN_BYTES
    assert sibling.joinpath(".gitignore").read_bytes() == sibling_ignore
    assert not repository.joinpath(".gitignore").exists()


def test_fix_initializes_exact_pen_and_managed_ignore_block_idempotently(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    before_index = _index_digest(repository)

    first = run_project_doctor(repository, fix=True)
    first_tree = {
        path.relative_to(repository).as_posix(): path.read_bytes()
        for path in sorted(repository.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(repository).parts
    }
    second = run_project_doctor(repository, fix=True)
    second_tree = {
        path.relative_to(repository).as_posix(): path.read_bytes()
        for path in sorted(repository.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(repository).parts
    }

    assert first.exit_code == second.exit_code == 0
    assert repository.joinpath("penflow/ui.pen").read_bytes() == EMPTY_PEN_BYTES
    assert repository.joinpath(".gitignore").read_text(encoding="utf-8") == MANAGED_IGNORE_BLOCK
    assert first_tree == second_tree
    assert _index_digest(repository) == before_index
    assert first.report.stable_result.canonical_pen == "penflow/ui.pen"
    assert [action.code for action in first.report.stable_result.actions] == [
        "gitignore.install_managed_block",
        "pen.initialize",
    ]
    assert second.report.stable_result.actions == ()


def test_fix_preserves_unique_ui_pen_location_and_unrelated_gitignore_bytes(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    canonical = repository / "design" / "ui.pen"
    _write_valid_pen(canonical)
    canonical_before = canonical.read_bytes()
    repository.joinpath(".gitignore").write_bytes(b"dist/\r\nlocal.env")

    result = run_project_doctor(repository, fix=True)

    assert result.exit_code == 0
    assert canonical.read_bytes() == canonical_before
    assert result.report.stable_result.canonical_pen == "design/ui.pen"
    assert repository.joinpath(".gitignore").read_bytes() == (
        b"dist/\r\nlocal.env\n" + MANAGED_IGNORE_BLOCK.encode("utf-8")
    )


@pytest.mark.parametrize(
    "names",
    [("draft.pen",), ("UI.pen",), ("ui.PEN",), ("ui.pen ",), ("a.pen", "b.pen")],
)
def test_fix_blocks_wrong_or_ambiguous_pen_sets_without_mutation(
    tmp_path: Path, names: tuple[str, ...]
) -> None:
    repository = _repository(tmp_path)
    for name in names:
        _write_valid_pen(repository / name)
    before = {name: repository.joinpath(name).read_bytes() for name in names}

    result = run_project_doctor(repository, fix=True)

    assert result.exit_code == 1
    expected_code = "pen.wrong_name" if len(names) == 1 else "multiple_pen_files"
    assert expected_code in _finding_codes(result)
    assert not repository.joinpath(".gitignore").exists()
    assert not repository.joinpath("penflow/ui.pen").exists()
    assert {name: repository.joinpath(name).read_bytes() for name in names} == before


@pytest.mark.parametrize("unsafe_kind", ["symlink", "hardlink"])
def test_fix_blocks_linked_pen_paths_without_following_them(
    tmp_path: Path, unsafe_kind: str
) -> None:
    repository = _repository(tmp_path)
    source = repository / "source.json"
    source.write_bytes(EMPTY_PEN_BYTES)
    linked = repository / "ui.pen"
    if unsafe_kind == "symlink":
        linked.symlink_to(source)
    else:
        os.link(source, linked)

    result = run_project_doctor(repository, fix=True)

    assert result.exit_code == 1
    assert f"pen.{unsafe_kind}" in _finding_codes(result)
    assert source.read_bytes() == EMPTY_PEN_BYTES
    assert not repository.joinpath(".gitignore").exists()


def test_fix_blocks_directory_with_pen_suffix_as_special_path(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.joinpath("ui.pen").mkdir()

    result = run_project_doctor(repository, fix=True)

    assert result.exit_code == 1
    assert "pen.special" in _finding_codes(result)
    assert repository.joinpath("ui.pen").is_dir()
    assert not repository.joinpath("penflow/ui.pen").exists()


def test_doctor_blocks_invalid_existing_ui_pen(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    repository.joinpath("ui.pen").write_text('{"children":"wrong"}\n', encoding="utf-8")
    repository.joinpath(".gitignore").write_text(MANAGED_IGNORE_BLOCK, encoding="utf-8")

    result = run_project_doctor(repository)

    assert result.exit_code == 1
    assert "pen.invalid" in _finding_codes(result)


def test_fix_blocks_malformed_ignore_markers_and_preserves_bytes(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _write_valid_pen(repository / "ui.pen")
    malformed = b"keep\n# <<< Penflow managed temporary artifacts v1 <<<\n"
    repository.joinpath(".gitignore").write_bytes(malformed)

    result = run_project_doctor(repository, fix=True)

    assert result.exit_code == 1
    assert "gitignore.managed_block_malformed" in _finding_codes(result)
    assert repository.joinpath(".gitignore").read_bytes() == malformed


def test_fix_collapses_complete_duplicate_ignore_blocks_once(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _write_valid_pen(repository / "ui.pen")
    duplicate = f"dist/\n{MANAGED_IGNORE_BLOCK}local.env\n{MANAGED_IGNORE_BLOCK}"
    repository.joinpath(".gitignore").write_text(duplicate, encoding="utf-8")

    first = run_project_doctor(repository, fix=True)
    second = run_project_doctor(repository, fix=True)
    repaired = repository.joinpath(".gitignore").read_text(encoding="utf-8")

    assert first.exit_code == second.exit_code == 0
    assert repaired.count(MANAGED_IGNORE_BLOCK) == 1
    assert repaired.startswith(f"dist/\n{MANAGED_IGNORE_BLOCK}local.env\n")
    assert second.report.stable_result.actions == ()


@pytest.mark.parametrize("git_setup", ["tracked", "staged", "intent_to_add"])
def test_doctor_reports_managed_git_leaks_without_index_mutation(
    tmp_path: Path, git_setup: str
) -> None:
    repository = _repository(tmp_path)
    _write_valid_pen(repository / "ui.pen")
    repository.joinpath(".gitignore").write_text(MANAGED_IGNORE_BLOCK, encoding="utf-8")
    leak = repository / ".penflow-run" / "snapshot.bin"
    leak.parent.mkdir()
    leak.write_bytes(b"managed working bytes")
    _git(repository, "add", "-f", leak.relative_to(repository).as_posix())
    if git_setup == "tracked":
        _git(repository, "commit", "-qm", "track legacy leak")
    elif git_setup == "intent_to_add":
        _git(repository, "rm", "--cached", "-q", leak.relative_to(repository).as_posix())
        _git(repository, "add", "-N", "-f", leak.relative_to(repository).as_posix())
    index_before = _index_digest(repository)

    result = run_project_doctor(repository)

    assert result.exit_code == 1
    assert _index_digest(repository) == index_before
    states = result.report.stable_result.git.paths
    state = next(item for item in states if item.relative_path == ".penflow-run/snapshot.bin")
    assert state.blocking
    assert state.index_state != "untracked"
    assert "git.temp_tracked" in _finding_codes(result) or "git.temp_staged" in _finding_codes(
        result
    )


def test_dry_run_plans_repairs_without_mutating_project(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    result = run_project_doctor(repository, fix=True, dry_run=True)

    assert result.exit_code == 1
    assert [action.status for action in result.report.stable_result.actions] == [
        "planned",
        "planned",
    ]
    assert not repository.joinpath("penflow/ui.pen").exists()
    assert not repository.joinpath(".gitignore").exists()


def test_stable_result_is_deterministic_for_unchanged_project(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    _write_valid_pen(repository / "ui.pen")
    repository.joinpath(".gitignore").write_text(MANAGED_IGNORE_BLOCK, encoding="utf-8")

    first = run_project_doctor(repository).report.stable_result
    second = run_project_doctor(repository).report.stable_result

    assert first == second
    assert first.status == "PASS"
    assert first.findings == ()


def test_doctor_report_matches_strict_bundled_schema(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    report = run_project_doctor(repository, fix=True).report.to_dict()

    validator_for("doctor-report.schema.json").validate(report)
