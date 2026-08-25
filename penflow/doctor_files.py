# @spec FR-003 FR-004 FR-007: Feature 075 project-local Doctor services.
"""Consumer-project Doctor filesystem inventory and safe repair primitives."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

from .artifact_policy import (
    CANONICAL_PEN_NAME,
    MANAGED_IGNORE_BLOCK,
    MANAGED_IGNORE_BLOCK_LINES,
    MANAGED_TEMP_ROOT,
    RECOGNIZED_LEGACY_ROOTS,
)
from .doctor_context import GitGateway, ProjectContext
from .doctor_git import _git_path_finding, _managed_git_paths
from .doctor_models import DoctorFinding, _Inspection, _Repair
from .pen import parse_pen, validate_pen_context

EMPTY_PEN_BYTES = b'{"children":[],"version":"1.0"}\n'
_IGNORE_BEGIN = MANAGED_IGNORE_BLOCK_LINES[0]
_IGNORE_END = MANAGED_IGNORE_BLOCK_LINES[-1]
_TEMP_ROOTS = (MANAGED_TEMP_ROOT, *RECOGNIZED_LEGACY_ROOTS)


def _inspect_project(context: ProjectContext, gateway: GitGateway) -> _Inspection:
    canonical_pen, pen_findings, pen_repairs = _inspect_pen_files(context)
    ignore_findings, ignore_repairs = _inspect_gitignore(context)
    git_paths = _managed_git_paths(context, gateway)
    git_findings = tuple(_git_path_finding(path) for path in git_paths)
    findings = tuple(
        sorted(
            (*pen_findings, *ignore_findings, *git_findings),
            key=lambda finding: (finding.severity, finding.code, finding.path or ""),
        )
    )
    repairs = tuple(
        sorted((*pen_repairs, *ignore_repairs), key=lambda repair: repair.relative_path)
    )
    return _Inspection(canonical_pen, findings, repairs, git_paths)


def _inspect_pen_files(
    context: ProjectContext,
) -> tuple[str | None, tuple[DoctorFinding, ...], tuple[_Repair, ...]]:
    candidates, findings = _inventory_pen_paths(context.project_root)
    if findings:
        return _canonical_from_candidates(context.project_root, candidates, findings)
    if not candidates:
        repair = _plan_pen_initialization(context.project_root)
        if isinstance(repair, DoctorFinding):
            return None, (repair,), ()
        finding = DoctorFinding(
            "pen.missing",
            "error",
            None,
            None,
            "consumer project contains no regular .pen file",
            repair.action_code,
        )
        return None, (finding,), (repair,)
    return _canonical_from_candidates(context.project_root, candidates, findings)


def _inventory_pen_paths(root: Path) -> tuple[tuple[Path, ...], tuple[DoctorFinding, ...]]:
    candidates: list[Path] = []
    findings: list[DoctorFinding] = []
    directories = [root]
    while directories:
        directory = directories.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name, reverse=True)
        except OSError:
            relative_directory = directory.relative_to(root).as_posix() or "."
            findings.append(
                DoctorFinding(
                    "pen.inventory_unreadable",
                    "error",
                    relative_directory,
                    None,
                    "directory metadata cannot be inventoried safely",
                )
            )
            continue
        for entry in entries:
            relative_path = Path(entry.path).relative_to(root)
            if entry.name == ".git" or (
                len(relative_path.parts) == 1 and entry.name in _TEMP_ROOTS
            ):
                continue
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError:
                if _is_pen_like_name(entry.name):
                    findings.append(_unsafe_pen_finding(relative_path, "unreadable"))
                continue
            if not _is_pen_like_name(entry.name):
                if stat.S_ISDIR(metadata.st_mode):
                    directories.append(Path(entry.path))
                continue
            if stat.S_ISLNK(metadata.st_mode):
                findings.append(_unsafe_pen_finding(relative_path, "symlink"))
            elif not stat.S_ISREG(metadata.st_mode):
                findings.append(_unsafe_pen_finding(relative_path, "special"))
            elif metadata.st_nlink != 1:
                findings.append(_unsafe_pen_finding(relative_path, "hardlink"))
            else:
                candidates.append(Path(entry.path))
    return tuple(sorted(candidates)), tuple(findings)


def _unsafe_pen_finding(relative_path: Path, kind: str) -> DoctorFinding:
    return DoctorFinding(
        f"pen.{kind}",
        "error",
        relative_path.as_posix(),
        None,
        f".pen path has unsafe filesystem kind: {kind}",
    )


def _canonical_from_candidates(
    root: Path,
    candidates: tuple[Path, ...],
    findings: tuple[DoctorFinding, ...],
) -> tuple[str | None, tuple[DoctorFinding, ...], tuple[_Repair, ...]]:
    accumulated = list(findings)
    if len(candidates) > 1:
        paths = ", ".join(path.relative_to(root).as_posix() for path in candidates)
        accumulated.append(
            DoctorFinding(
                "multiple_pen_files",
                "error",
                None,
                None,
                f"multiple regular .pen files found: {paths}",
            )
        )
        return None, tuple(accumulated), ()
    if not candidates:
        return None, tuple(accumulated), ()
    candidate = candidates[0]
    relative = candidate.relative_to(root).as_posix()
    if candidate.name != CANONICAL_PEN_NAME:
        accumulated.append(
            DoctorFinding(
                "pen.wrong_name",
                "error",
                relative,
                None,
                "the unique regular .pen file must have exact basename ui.pen",
            )
        )
        return None, tuple(accumulated), ()
    invalid_detail = _validate_canonical_pen(candidate)
    if invalid_detail is not None:
        accumulated.append(DoctorFinding("pen.invalid", "error", relative, None, invalid_detail))
    return relative, tuple(accumulated), ()


def _is_pen_like_name(name: str) -> bool:
    # Case/space variants are candidates, not aliases: on case-insensitive filesystems,
    # treating them as absent could make initialization overwrite the unsafe existing path.
    return name.rstrip().casefold().endswith(".pen")


def _plan_pen_initialization(root: Path) -> _Repair | DoctorFinding:
    parent = root / "penflow"
    if parent.exists() or parent.is_symlink():
        metadata = parent.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            return DoctorFinding(
                "pen.initialization_parent_unsafe",
                "error",
                "penflow",
                None,
                "canonical initialization parent is not a regular directory",
            )
    return _Repair("pen.initialize", "penflow/ui.pen", EMPTY_PEN_BYTES)


def _validate_canonical_pen(path: Path) -> str | None:
    before = path.lstat()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        after = os.fstat(descriptor)
        if (before.st_dev, before.st_ino, before.st_mode, before.st_nlink) != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_nlink,
        ):
            return "canonical .pen identity changed during validation"
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            raw = stream.read()
    finally:
        os.close(descriptor)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "canonical ui.pen must contain readable UTF-8 JSON"
    if not isinstance(data, dict) or not isinstance(data.get("children"), list):
        return "canonical ui.pen must contain a top-level children array"
    if any(not isinstance(child, dict) for child in data["children"]):
        return "canonical ui.pen children must be JSON objects"
    if not data["children"]:
        # Doctor's normative initialization document is intentionally screenless;
        # canvas publication rejects emptiness later, after a producer adds regions.
        return None
    try:
        issues = validate_pen_context(parse_pen(data))
    except (KeyError, TypeError, ValueError):
        return "canonical ui.pen failed structural validation"
    if any(issue.severity == "error" for issue in issues):
        return "canonical ui.pen failed structural validation"
    return None


def _inspect_gitignore(
    context: ProjectContext,
) -> tuple[tuple[DoctorFinding, ...], tuple[_Repair, ...]]:
    path = context.project_root / ".gitignore"
    if not path.exists() and not path.is_symlink():
        return _missing_gitignore()
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        return (_gitignore_unsafe("gitignore.symlink", "is a symlink"),), ()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        return (_gitignore_unsafe("gitignore.unsafe_file", "is not a single-link file"),), ()
    data = _read_regular_file_no_follow(path, metadata)
    parsed = _parse_managed_ignore_blocks(data)
    if parsed is None:
        return (
            DoctorFinding(
                "gitignore.managed_block_malformed",
                "error",
                ".gitignore",
                None,
                "managed Penflow ignore markers are nested, reversed, or unmatched",
            ),
        ), ()
    ranges = parsed
    expected = MANAGED_IGNORE_BLOCK.encode("utf-8")
    if len(ranges) == 1 and data[ranges[0][0] : ranges[0][1]] == expected:
        return (), ()
    if not _has_write_permission(metadata.st_mode):
        return (_gitignore_unsafe("gitignore.unwritable", "is not writable"),), ()
    return _gitignore_repair(data, ranges, metadata)


def _missing_gitignore() -> tuple[tuple[DoctorFinding, ...], tuple[_Repair, ...]]:
    repair = _Repair(
        "gitignore.install_managed_block",
        ".gitignore",
        MANAGED_IGNORE_BLOCK.encode("utf-8"),
    )
    finding = DoctorFinding(
        "gitignore.managed_block_missing",
        "error",
        ".gitignore",
        None,
        "managed Penflow ignore block is absent",
        repair.action_code,
    )
    return (finding,), (repair,)


def _gitignore_repair(
    data: bytes,
    ranges: tuple[tuple[int, int], ...],
    metadata: os.stat_result,
) -> tuple[tuple[DoctorFinding, ...], tuple[_Repair, ...]]:
    expected = MANAGED_IGNORE_BLOCK.encode("utf-8")
    replacement = _replace_managed_ignore_blocks(data, ranges, expected)
    action_code = (
        "gitignore.install_managed_block" if not ranges else "gitignore.normalize_managed_block"
    )
    finding_code = (
        "gitignore.managed_block_missing"
        if not ranges
        else "gitignore.managed_block_duplicate"
        if len(ranges) > 1
        else "gitignore.managed_block_outdated"
    )
    finding = DoctorFinding(
        finding_code,
        "error",
        ".gitignore",
        None,
        "managed Penflow ignore block is absent, duplicated, or not canonical",
        action_code,
    )
    identity = (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_nlink)
    return (finding,), (
        _Repair(
            action_code,
            ".gitignore",
            replacement,
            expected_identity=identity,
            mode=stat.S_IMODE(metadata.st_mode),
        ),
    )


def _gitignore_unsafe(code: str, detail: str) -> DoctorFinding:
    return DoctorFinding(
        code,
        "error",
        ".gitignore",
        None,
        f".gitignore {detail}; Doctor will not repair it",
    )


def _read_regular_file_no_follow(path: Path, expected: os.stat_result) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        observed = os.fstat(descriptor)
        if (expected.st_dev, expected.st_ino, expected.st_mode, expected.st_nlink) != (
            observed.st_dev,
            observed.st_ino,
            observed.st_mode,
            observed.st_nlink,
        ):
            raise OSError(f"filesystem identity changed while reading {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            return stream.read()
    finally:
        os.close(descriptor)


def _parse_managed_ignore_blocks(data: bytes) -> tuple[tuple[int, int], ...] | None:
    begin = _IGNORE_BEGIN.encode("utf-8")
    end = _IGNORE_END.encode("utf-8")
    ranges: list[tuple[int, int]] = []
    open_offset: int | None = None
    offset = 0
    for line in data.splitlines(keepends=True):
        normalized = line.rstrip(b"\r\n")
        if normalized == begin:
            if open_offset is not None:
                return None
            open_offset = offset
        elif normalized == end:
            if open_offset is None:
                return None
            ranges.append((open_offset, offset + len(line)))
            open_offset = None
        offset += len(line)
    if open_offset is not None:
        return None
    return tuple(ranges)


def _replace_managed_ignore_blocks(
    data: bytes,
    ranges: tuple[tuple[int, int], ...],
    expected: bytes,
) -> bytes:
    if not ranges:
        separator = b"" if not data or data.endswith((b"\n", b"\r")) else b"\n"
        return data + separator + expected
    # The first block is normalized in place and later complete duplicates are removed;
    # every byte outside the marked ranges is copied unchanged and in original order.
    chunks: list[bytes] = []
    cursor = 0
    for index, (start, end) in enumerate(ranges):
        chunks.append(data[cursor:start])
        if index == 0:
            chunks.append(expected)
        cursor = end
    chunks.append(data[cursor:])
    return b"".join(chunks)


def _has_write_permission(mode: int) -> bool:
    return bool(mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def _atomic_write(
    path: Path,
    content: bytes,
    *,
    expected_identity: tuple[int, int, int, int] | None,
    mode: int,
) -> None:
    parent = path.parent
    if not parent.exists():
        parent.mkdir(parents=True, exist_ok=False)
        _fsync_directory(parent.parent)
    parent_metadata = parent.lstat()
    if stat.S_ISLNK(parent_metadata.st_mode) or not stat.S_ISDIR(parent_metadata.st_mode):
        raise OSError(f"atomic-write parent is unsafe: {parent}")
    if path.exists() or path.is_symlink():
        observed = path.lstat()
        identity = (observed.st_dev, observed.st_ino, observed.st_mode, observed.st_nlink)
        if expected_identity is None or identity != expected_identity:
            raise OSError(f"atomic-write target identity changed: {path}")
    elif expected_identity is not None:
        raise OSError(f"atomic-write target disappeared: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        # Crash consistency requires file flush before replace and directory flush after it;
        # reordering can expose missing or partial canonical bytes after a power loss.
        os.replace(temporary, path)
        _fsync_directory(parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            # Atomic replace consumes the sibling temp path on success.
            pass


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
