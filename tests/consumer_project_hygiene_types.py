# @spec AC-014 AC-015 FR-012: Feature 074 real-consumer proof.
"""Real-consumer hygiene proof responsibility module."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Capture one bounded subprocess result without decoding raw evidence bytes."""

    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True, slots=True)
class ConsumerMarker:
    """Describe one discovered canonical Penflow consumer marker."""

    label: str
    search_root: Path
    marker_relative: str
    ui_pen: Path
    project_root: Path | None
    marker_sha256: str
    companion_relative: str
    companion_sha256: str


@dataclass(frozen=True, slots=True)
class TreeEntry:
    """Bind one non-Git filesystem entry by normalized path and bytes or identity."""

    path: str
    kind: str
    sha256: str
    logical_bytes: int


@dataclass(frozen=True, slots=True)
class ProjectSnapshot:
    """Bind Git index, porcelain bytes and the sorted non-Git filesystem inventory."""

    index_sha256: str
    porcelain_sha256: str
    tree_sha256: str
    files: tuple[TreeEntry, ...]


CommandRunner: TypeAlias = Callable[[tuple[str, ...], Path, int], CommandResult]
CopyExerciser: TypeAlias = Callable[[Path, Path], Mapping[str, object]]
JsonReceipt: TypeAlias = dict[str, Any]
