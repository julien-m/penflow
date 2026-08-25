# @spec FR-001 FR-002 FR-005 FR-007: Feature 075 two-root boundary.
"""Consumer-project Doctor Git worktree resolution boundary."""

from __future__ import annotations

import os
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

GIT_TIMEOUT_SECONDS = 10


class ProjectResolutionError(ValueError):
    """Report a stable consumer-project resolution failure."""

    def __init__(self, code: str, message: str) -> None:
        """Initialize a coded resolution failure.

        Args:
            code: Stable machine-readable finding code.
            message: Actionable human-readable explanation.
        """

        super().__init__(message)
        self.code = code


class GitCommandError(RuntimeError):
    """Report a failed bounded invocation of the Git gateway."""

    def __init__(self, arguments: tuple[str, ...], return_code: int, stderr: str) -> None:
        """Initialize a Git failure without leaking transport objects.

        Args:
            arguments: Git arguments that failed.
            return_code: Process exit status returned by Git.
            stderr: Decoded stderr returned by Git.
        """

        super().__init__(f"git {' '.join(arguments)} failed: {stderr.strip()}")
        self.arguments = arguments
        self.return_code = return_code


@dataclass(frozen=True)
class GitCommandResult:
    """Contain stable byte channels returned by one successful Git command."""

    stdout: bytes
    stderr: bytes


class GitGateway(Protocol):
    """Define the narrow local Git subprocess boundary used by Doctor."""

    def run(
        self,
        directory: Path,
        arguments: tuple[str, ...],
        *,
        input_bytes: bytes | None = None,
    ) -> GitCommandResult:
        """Run one bounded Git command or raise ``GitCommandError``."""


class SubprocessGitGateway:
    """Execute local read-only Git queries with deterministic byte output."""

    def run(
        self,
        directory: Path,
        arguments: tuple[str, ...],
        *,
        input_bytes: bytes | None = None,
    ) -> GitCommandResult:
        """Run a non-interactive local Git query.

        Args:
            directory: Directory supplied to Git's ``-C`` boundary.
            arguments: Read-only Git arguments.
            input_bytes: Optional NUL-delimited stdin for ``check-ignore``.

        Returns:
            Captured stdout and stderr bytes.

        Raises:
            GitCommandError: If Git returns a nonzero status.
        """

        environment = {**os.environ, "LC_ALL": "C", "GIT_TERMINAL_PROMPT": "0"}
        # External-process contract: local Git only, no shell, stable locale, bounded wait,
        # captured byte channels, and nonzero status translated into a typed boundary error.
        try:
            completed = subprocess.run(
                ["git", "-C", os.fspath(directory), *arguments],
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=GIT_TIMEOUT_SECONDS,
                env=environment,
            )
        except subprocess.TimeoutExpired as error:
            raise GitCommandError(arguments, -1, "bounded Git query timed out") from error
        if completed.returncode != 0:
            raise GitCommandError(
                arguments,
                completed.returncode,
                completed.stderr.decode("utf-8", errors="replace"),
            )
        return GitCommandResult(stdout=completed.stdout, stderr=completed.stderr)


@dataclass(frozen=True)
class ProjectContext:
    """Bind one invocation to an exact project inside one Git worktree."""

    project_root: Path
    git_root: Path
    project_pathspec: str
    invocation_path: Path
    explicit_project: bool
    git_dir: Path
    common_git_dir: Path
    repository_kind: str

    @property
    def root(self) -> Path:
        """Return the selected project root for Feature 074 compatibility.

        New code should use :attr:`project_root` or :attr:`git_root` explicitly.
        The compatibility accessor intentionally never widens to the Git root.
        """

        return self.project_root

    def resolve_path(self, candidate: str | Path, *, must_exist: bool = False) -> Path:
        """Resolve a producer path inside this consumer worktree.

        Args:
            candidate: Absolute path or project-root-relative path.
            must_exist: Require the final path to exist.

        Returns:
            Normalized absolute path contained by ``root``.

        Raises:
            FileNotFoundError: If ``must_exist`` and the path is absent.
            ValueError: If the path escapes the root or traverses a symlink.
        """

        raw_path = Path(candidate).expanduser()
        anchored = raw_path if raw_path.is_absolute() else self.project_root / raw_path
        absolute = Path(os.path.abspath(anchored))
        if must_exist and not absolute.exists():
            raise FileNotFoundError(absolute)
        symlink = _first_symlink_component(absolute)
        if symlink is not None:
            raise ValueError(f"project path traverses symlink: {symlink}")
        normalized = absolute.resolve(strict=must_exist)
        if not normalized.is_relative_to(self.project_root):
            raise ValueError(f"path is outside consumer project root: {candidate}")
        return normalized


def _resolve_project_context(
    project: str | Path | None,
    *,
    cwd: str | Path | None,
    git_gateway: GitGateway,
) -> ProjectContext:
    invocation_path, project_root = _normalize_invocation_path(project, cwd)
    _require_non_bare_worktree(git_gateway, project_root, invocation_path)
    git_root, git_dir, common_git_dir = _git_project_metadata(git_gateway, project_root)
    if not project_root.is_relative_to(git_root):
        raise ProjectResolutionError(
            "not_git_project",
            f"project path is not inside a Git worktree: {invocation_path}",
        )
    return ProjectContext(
        project_root=project_root,
        git_root=git_root,
        project_pathspec=_project_pathspec(project_root, git_root),
        invocation_path=invocation_path,
        explicit_project=project is not None,
        git_dir=git_dir,
        common_git_dir=common_git_dir,
        repository_kind=_repository_kind(git_root, git_dir, common_git_dir),
    )


def _normalize_invocation_path(
    project: str | Path | None, cwd: str | Path | None
) -> tuple[Path, Path]:
    cwd_path = Path.cwd() if cwd is None else Path(cwd).expanduser()
    if not cwd_path.is_absolute():
        cwd_path = Path.cwd() / cwd_path
    cwd_path = Path(os.path.abspath(cwd_path))
    supplied = Path(project).expanduser() if project is not None else cwd_path
    anchored = supplied if supplied.is_absolute() else cwd_path / supplied
    absolute = Path(os.path.abspath(anchored))
    if not absolute.exists():
        raise ProjectResolutionError(
            "project.path_missing", f"project path does not exist: {absolute}"
        )
    symlink = _first_symlink_component(absolute)
    if symlink is not None:
        raise ProjectResolutionError(
            "project.symlink_path", f"project path traverses symlink: {symlink}"
        )
    invocation_path = absolute.resolve(strict=True)
    if invocation_path.is_dir():
        project_root = invocation_path
    elif invocation_path.is_file():
        project_root = invocation_path.parent
    else:
        raise ProjectResolutionError(
            "project.path_invalid", f"project path is not a regular file or directory: {absolute}"
        )
    return invocation_path, project_root


def _project_pathspec(project_root: Path, git_root: Path) -> str:
    """Build the sole literal Git content scope for a selected project.

    Git runs from ``git_root``. Root equality therefore uses the top-level equality
    magic, while nested projects use a top-anchored literal path. Constructing one
    immutable pathspec prevents callers from accidentally enumerating siblings.

    Args:
        project_root: Exact selected consumer project directory.
        git_root: Nearest enclosing non-bare worktree root.

    Returns:
        Canonical Git pathspec accepted after ``--``.

    Raises:
        ProjectResolutionError: If translation would escape the Git worktree.
    """

    if project_root == git_root:
        return ":(top)"
    try:
        relative = project_root.relative_to(git_root)
    except ValueError as error:
        raise ProjectResolutionError(
            "not_git_project",
            f"project path is not inside a Git worktree: {project_root}",
        ) from error
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ProjectResolutionError(
            "project.git_metadata_unavailable",
            "selected project could not be translated to a safe Git pathspec",
        )
    return f":(top,literal){relative.as_posix()}"


def _require_non_bare_worktree(
    git_gateway: GitGateway, anchor: Path, invocation_path: Path
) -> None:
    bare = _optional_git_text(git_gateway, anchor, ("rev-parse", "--is-bare-repository"))
    if bare == "true":
        raise ProjectResolutionError(
            "project.bare_repository",
            f"project path identifies a bare Git repository: {invocation_path}",
        )
    inside = _optional_git_text(git_gateway, anchor, ("rev-parse", "--is-inside-work-tree"))
    if inside != "true":
        raise ProjectResolutionError(
            "not_git_project", f"project path is not inside a Git worktree: {invocation_path}"
        )


def _git_project_metadata(git_gateway: GitGateway, anchor: Path) -> tuple[Path, Path, Path]:
    try:
        root_text = _git_text(git_gateway, anchor, ("rev-parse", "--show-toplevel"))
        git_dir_text = _git_text(git_gateway, anchor, ("rev-parse", "--absolute-git-dir"))
        common_git_text = _git_text(
            git_gateway,
            anchor,
            ("rev-parse", "--path-format=absolute", "--git-common-dir"),
        )
    except GitCommandError as error:
        raise ProjectResolutionError(
            "project.git_metadata_unavailable",
            "Git worktree metadata could not be resolved safely",
        ) from error
    root = Path(root_text).resolve()
    git_dir = Path(git_dir_text).resolve()
    common_git_dir = Path(common_git_text).resolve()
    return root, git_dir, common_git_dir


def _first_symlink_component(path: Path) -> Path | None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            if stat.S_ISLNK(current.lstat().st_mode):
                return current
        except FileNotFoundError:
            return None
    return None


def _git_text(gateway: GitGateway, directory: Path, arguments: tuple[str, ...]) -> str:
    return gateway.run(directory, arguments).stdout.decode("utf-8").strip()


def _optional_git_text(
    gateway: GitGateway, directory: Path, arguments: tuple[str, ...]
) -> str | None:
    try:
        return _git_text(gateway, directory, arguments)
    except GitCommandError:
        # Resolution probes intentionally translate Git's nonzero "not a repository"
        # result into a stable project finding at the public boundary.
        return None


def _repository_kind(root: Path, git_dir: Path, common_git_dir: Path) -> str:
    dot_git = root / ".git"
    if dot_git.is_file():
        return "submodule" if "modules" in git_dir.parts else "linked"
    if git_dir != common_git_dir:
        return "linked"
    return "standard"
