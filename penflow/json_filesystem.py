"""Durable atomic JSON persistence at the local filesystem boundary."""

from __future__ import annotations

import errno
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_ATOMIC_FILE_MODE = 0o600
ERROR_ACCESS_DENIED = 5
ERROR_INVALID_PARAMETER = 87
_UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS = frozenset(
    value
    for value in (
        errno.EINVAL,
        getattr(errno, "ENOTSUP", None),
        getattr(errno, "EOPNOTSUPP", None),
    )
    if value is not None
)
# Windows uses these documented system errors when directory handles cannot be
# opened or synchronized, even after regular-file fsync and replace succeeded.
_UNSUPPORTED_DIRECTORY_FSYNC_WINERRORS = frozenset({ERROR_ACCESS_DENIED, ERROR_INVALID_PARAMETER})


def write_json_atomically(path: Path, data: dict[str, Any]) -> None:
    """Write sorted JSON by durable sibling replacement.

    Args:
        path: Destination file path whose parent already exists.
        data: JSON object to serialize.

    Side effects:
        Flushes file and supported parent-directory metadata before returning.
        Existing destination permissions are preserved. New files use mode
        ``0o600`` so generated consumer artifacts are private by default.

    Raises:
        OSError: If writing, replacement, or directory synchronization fails
            outside the documented unsupported directory-fsync cases.
    """
    temporary_path = _write_temporary_json(
        path,
        _serialized_json(data),
        _destination_mode(path),
    )
    try:
        _replace_and_sync(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _serialized_json(data: dict[str, Any]) -> str:
    """Return deterministic JSON text with one final newline."""
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def _destination_mode(path: Path) -> int:
    """Return the existing mode or the private default for a new artifact."""
    return stat.S_IMODE(path.stat().st_mode) if path.exists() else DEFAULT_ATOMIC_FILE_MODE


def _write_temporary_json(path: Path, serialized: str, destination_mode: int) -> Path:
    """Write and fsync one mode-correct sibling temporary file."""
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        # Mode is part of the durable file state, so apply it before the data
        # flush/fsync rather than racing a post-close chmod after replacement.
        os.fchmod(temporary.fileno(), destination_mode)
        temporary.write(serialized)
        temporary.flush()
        os.fsync(temporary.fileno())
    return temporary_path


def _replace_and_sync(temporary_path: Path, destination: Path) -> None:
    """Publish one flushed sibling and durably synchronize its directory entry."""
    # The flushed sibling must replace the destination before the parent
    # directory is synced, otherwise a crash can expose stale path metadata.
    os.replace(temporary_path, destination)
    _fsync_parent_directory(destination.parent)


def _fsync_parent_directory(directory: Path) -> None:
    """Synchronize directory metadata when the platform supports it."""
    try:
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as error:
        # Only platform-documented unsupported directory operations are safe
        # to ignore; ordinary permission and I/O failures must remain visible.
        if (
            error.errno in _UNSUPPORTED_DIRECTORY_FSYNC_ERRNOS
            or getattr(error, "winerror", None) in _UNSUPPORTED_DIRECTORY_FSYNC_WINERRORS
        ):
            return
        raise
