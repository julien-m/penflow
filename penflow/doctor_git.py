# @spec FR-005 FR-006 FR-007: Feature 075 scoped Git interrogation.
"""Consumer-project Doctor Git index and worktree inspection."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from .artifact_policy import MANAGED_TEMP_ROOT, RECOGNIZED_LEGACY_ROOTS
from .doctor_context import GitCommandError, GitGateway, ProjectContext
from .doctor_models import DoctorFinding, GitPathState, _GitSnapshot

_TEMP_ROOTS = (MANAGED_TEMP_ROOT, *RECOGNIZED_LEGACY_ROOTS)


def _capture_git_snapshot(context: ProjectContext, gateway: GitGateway) -> _GitSnapshot:
    index_path = context.git_dir / "index"
    index_sha256 = (
        hashlib.sha256(index_path.read_bytes()).hexdigest() if index_path.exists() else None
    )
    porcelain = gateway.run(
        context.git_root,
        _scoped_git_arguments(
            context,
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
        ),
    ).stdout
    return _GitSnapshot(index_sha256=index_sha256, porcelain=porcelain)


@dataclass
class _MutableGitPathState:
    relative_path: str
    index_state: str = "untracked"
    worktree_state: str = "clean"
    flags: set[str] | None = None

    def freeze(self) -> GitPathState:
        """Return an immutable normalized Git state."""

        return GitPathState(
            relative_path=self.relative_path,
            index_state=self.index_state,
            worktree_state=self.worktree_state,
            flags=tuple(sorted(self.flags or set())),
        )


def _managed_git_paths(context: ProjectContext, gateway: GitGateway) -> tuple[GitPathState, ...]:
    staged = gateway.run(
        context.git_root,
        _scoped_git_arguments(context, "ls-files", "--stage", "-z"),
    ).stdout
    tagged = gateway.run(
        context.git_root,
        _scoped_git_arguments(context, "ls-files", "-v", "-z"),
    ).stdout
    porcelain = gateway.run(
        context.git_root,
        _scoped_git_arguments(
            context,
            "status",
            "--porcelain=v2",
            "-z",
            "--untracked-files=all",
        ),
    ).stdout
    states: dict[str, _MutableGitPathState] = {}
    _merge_ls_files_stage(context, states, staged)
    _merge_ls_files_tags(context, states, tagged)
    _merge_porcelain(context, states, porcelain)
    # Git enumerates the entire selected project so the repository boundary is
    # testable independently from Penflow policy. Only exact first components in
    # the temporary catalog become business findings; lexical lookalikes remain
    # ordinary project files.
    states = {
        relative_path: state
        for relative_path, state in states.items()
        if _is_temporary_candidate(relative_path)
    }
    existing_paths = sorted(states)
    if existing_paths:
        stdin = b"\0".join(path.encode("utf-8") for path in existing_paths) + b"\0"
        ignored = _check_ignored_paths(context, gateway, stdin)
        for relative_path in ignored:
            if relative_path in states:
                _git_flags(states[relative_path]).add("ignored")
    return tuple(states[path].freeze() for path in sorted(states))


def _merge_ls_files_stage(
    context: ProjectContext,
    states: dict[str, _MutableGitPathState],
    output: bytes,
) -> None:
    for record in output.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, object_id, stage = metadata.decode("ascii").split(" ")
        relative_path = _project_relative_git_path(context, raw_path)
        state = states.setdefault(relative_path, _MutableGitPathState(relative_path))
        state.index_state = "tracked" if stage == "0" else "unmerged"
        flags = _git_flags(state)
        if stage != "0":
            flags.add(f"stage_{stage}")
        if object_id == "0" * len(object_id):
            state.index_state = "intent_to_add"
            flags.add("intent_to_add")
        if mode == "0":
            flags.add("deleted_from_index")


def _merge_ls_files_tags(
    context: ProjectContext,
    states: dict[str, _MutableGitPathState],
    output: bytes,
) -> None:
    for record in output.split(b"\0"):
        if not record:
            continue
        tag = chr(record[0])
        relative_path = _project_relative_git_path(context, record[2:])
        state = states.setdefault(relative_path, _MutableGitPathState(relative_path, "tracked"))
        flags = _git_flags(state)
        if tag.lower() == tag:
            flags.add("assume_unchanged")
        if tag.upper() == "S":
            flags.add("skip_worktree")


def _merge_porcelain(
    context: ProjectContext,
    states: dict[str, _MutableGitPathState],
    output: bytes,
) -> None:
    records = output.split(b"\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record or record.startswith((b"? ", b"! ")):
            continue
        record_type = record[:1]
        field_limit = 9 if record_type == b"2" else 8 if record_type == b"1" else 10
        fields = record.split(b" ", field_limit)
        if len(fields) <= field_limit:
            continue
        xy = fields[1].decode("ascii", errors="replace")
        relative_path = _project_relative_git_path(context, fields[field_limit])
        state = states.setdefault(relative_path, _MutableGitPathState(relative_path))
        _apply_porcelain_xy(state, xy)
        if record_type == b"2" and index < len(records):
            original = _project_relative_git_path(context, records[index])
            index += 1
            original_state = states.setdefault(original, _MutableGitPathState(original))
            _apply_porcelain_xy(original_state, xy)


def _apply_porcelain_xy(state: _MutableGitPathState, xy: str) -> None:
    if len(xy) != 2:
        return
    index_code = xy[0]
    worktree_code = xy[1]
    if index_code != ".":
        state.index_state = _git_status_name(index_code)
        _git_flags(state).add("staged")
    elif state.index_state == "untracked":
        state.index_state = "tracked"
    state.worktree_state = "clean" if worktree_code == "." else _git_status_name(worktree_code)


def _git_status_name(code: str) -> str:
    return {
        "A": "added",
        "M": "modified",
        "D": "deleted",
        "R": "renamed",
        "C": "copied",
        "U": "unmerged",
        "T": "type_changed",
    }.get(code, f"status_{code}")


def _git_flags(state: _MutableGitPathState) -> set[str]:
    if state.flags is None:
        state.flags = set()
    return state.flags


def _check_ignored_paths(context: ProjectContext, gateway: GitGateway, stdin: bytes) -> set[str]:
    project_paths = tuple(path for path in stdin.split(b"\0") if path)
    git_paths = b"\0".join(_git_relative_path(context, path) for path in project_paths) + b"\0"
    try:
        output = gateway.run(
            context.git_root,
            ("check-ignore", "-z", "--stdin"),
            input_bytes=git_paths,
        ).stdout
    except GitCommandError as error:
        if error.return_code == 1:
            return set()
        raise
    return {_project_relative_git_path(context, path) for path in output.split(b"\0") if path}


def _scoped_git_arguments(context: ProjectContext, *arguments: str) -> tuple[str, ...]:
    """Append the one immutable project pathspec to a Git content query."""

    if "--" in arguments:
        raise ValueError("scoped Git arguments must not supply their own pathspec separator")
    return (*arguments, "--", context.project_pathspec)


def _project_relative_git_path(context: ProjectContext, path: bytes) -> str:
    """Translate one Git-root-relative NUL record into project-relative POSIX form.

    Raises:
        ValueError: If Git returns an absolute, malformed or sibling path.
    """

    decoded = _decode_git_path(path)
    parts = tuple(part for part in decoded.split("/") if part)
    if decoded.startswith("/") or not parts or any(part in {".", ".."} for part in parts):
        raise ValueError(f"Git returned an unsafe project path: {decoded!r}")
    if context.project_root == context.git_root:
        return "/".join(parts)
    prefix = context.project_root.relative_to(context.git_root).parts
    if parts[: len(prefix)] != prefix or len(parts) == len(prefix):
        raise ValueError(f"Git returned a path outside consumer project root: {decoded!r}")
    return "/".join(parts[len(prefix) :])


def _git_relative_path(context: ProjectContext, project_path: bytes) -> bytes:
    """Translate one validated project-local candidate for ``check-ignore``."""

    decoded = _decode_git_path(project_path)
    parts = tuple(part for part in decoded.split("/") if part)
    if not parts or decoded.startswith("/") or any(part in {".", ".."} for part in parts):
        raise ValueError(f"unsafe project-local ignore candidate: {decoded!r}")
    if context.project_root == context.git_root:
        return "/".join(parts).encode("utf-8", errors="surrogateescape")
    prefix = context.project_root.relative_to(context.git_root).as_posix()
    return f"{prefix}/{'/'.join(parts)}".encode("utf-8", errors="surrogateescape")


def _is_temporary_candidate(relative_path: str) -> bool:
    """Return whether the exact first component is Penflow temporary policy."""

    return relative_path.split("/", 1)[0] in _TEMP_ROOTS


def _decode_git_path(path: bytes) -> str:
    return path.decode("utf-8", errors="surrogateescape").replace(os.sep, "/")


def _git_path_finding(path: GitPathState) -> DoctorFinding:
    is_staged = "staged" in path.flags or path.index_state in {
        "added",
        "modified",
        "deleted",
        "renamed",
        "copied",
        "unmerged",
        "intent_to_add",
        "type_changed",
    }
    code = "git.temp_staged" if is_staged else "git.temp_tracked"
    git_state = f"index={path.index_state},worktree={path.worktree_state}"
    return DoctorFinding(
        code,
        "error",
        path.relative_path,
        git_state,
        "managed or recognized legacy temporary data is present in the Git index",
        None,
    )
