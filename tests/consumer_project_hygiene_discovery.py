# @spec AC-014 AC-015 FR-012: Feature 074 real-consumer proof.
"""Real-consumer hygiene proof responsibility module."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from pathlib import Path

from tests.consumer_project_hygiene_types import ConsumerMarker, ProjectSnapshot, TreeEntry

DISCOVERY_PRUNE_NAMES = frozenset(
    {
        ".git",
        ".venv",
        ".penflow-tmp",
        "__pycache__",
        "build",
        "cache",
        "dist",
        "node_modules",
        "venv",
    }
)
HASH_CHUNK_BYTES = 1024 * 1024
COMMAND_TIMEOUT_SECONDS = 30


def discover_consumers(
    search_roots: Sequence[Path], *, excluded_roots: Sequence[Path] = ()
) -> tuple[ConsumerMarker, ...]:
    """Discover every valid consumer marker below explicit search roots.

    Args:
        search_roots: Existing directory roots to scan in caller-provided order.

    Returns:
        excluded_roots: Source/fixture roots that are not live consumers.

        A path-sorted, de-duplicated tuple with stable consumer labels.

    Raises:
        ValueError: If no search root was supplied or a root is not a directory.
    """
    if not search_roots:
        raise ValueError("at least one explicit search root is required")
    normalized_exclusions = tuple(root.expanduser().resolve() for root in excluded_roots)
    candidates: dict[str, tuple[Path, Path, Path, Path | None]] = {}
    for search_root in search_roots:
        normalized_root = search_root.expanduser().resolve()
        if not normalized_root.is_dir():
            raise ValueError(f"search root is not a directory: {search_root}")
        for current, directory_names, file_names in os.walk(normalized_root, followlinks=False):
            directory_names[:] = sorted(
                name for name in directory_names if name not in DISCOVERY_PRUNE_NAMES
            )
            if "ui.pen" not in file_names:
                continue
            ui_pen = Path(current) / "ui.pen"
            resolved_marker = ui_pen.resolve()
            if _is_excluded_marker(resolved_marker, normalized_exclusions):
                continue
            if not _is_single_link_regular(ui_pen) or not _is_valid_ui_pen(ui_pen):
                continue
            companion = _consumer_companion(ui_pen.parent)
            if companion is None:
                continue
            key = ui_pen.resolve().as_posix()
            candidates[key] = (normalized_root, ui_pen, companion, _git_root(ui_pen.parent))
    markers: list[ConsumerMarker] = []
    # Stable labels are assigned only after the complete candidate inventory is sorted.
    for index, (_key, candidate) in enumerate(sorted(candidates.items())):
        search_root, ui_pen, companion, project_root = candidate
        markers.append(
            ConsumerMarker(
                label=f"consumer-{index:03d}",
                search_root=search_root,
                marker_relative=ui_pen.relative_to(search_root).as_posix(),
                ui_pen=ui_pen,
                project_root=project_root,
                marker_sha256=_sha256_file(ui_pen),
                companion_relative=companion.relative_to(search_root).as_posix(),
                companion_sha256=_sha256_file(companion),
            )
        )
    return tuple(markers)


def _is_excluded_marker(marker: Path, excluded_roots: Sequence[Path]) -> bool:
    return any(marker == excluded or excluded in marker.parents for excluded in excluded_roots)


def capture_project_snapshot(project_root: Path) -> ProjectSnapshot:
    """Capture exact Git and non-Git evidence without changing project state.

    Args:
        project_root: Root of the live Git worktree to inspect.

    Returns:
        Immutable hashes and the sorted entry inventory.

    Raises:
        RuntimeError: If Git cannot produce trustworthy project evidence.
    """
    root = project_root.resolve()
    porcelain = _git_bytes(root, "status", "--porcelain=v2", "-z", "--untracked-files=all")
    index_path_text = _git_bytes(root, "rev-parse", "--git-path", "index").decode().strip()
    index_path = Path(index_path_text)
    if not index_path.is_absolute():
        index_path = root / index_path
    index_bytes = index_path.read_bytes() if index_path.is_file() else b"<missing-index>"
    files = tuple(_inventory_non_git_tree(root))
    stable_inventory = json.dumps(
        [asdict(entry) for entry in files],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return ProjectSnapshot(
        index_sha256=_sha256_bytes(index_bytes),
        porcelain_sha256=_sha256_bytes(porcelain),
        tree_sha256=_sha256_bytes(stable_inventory),
        files=files,
    )


def capture_layout_snapshot(layout_root: Path) -> ProjectSnapshot:
    """Capture a non-Git consumer layout without mutating or inventing Git state."""
    root = layout_root.resolve()
    files = tuple(_inventory_non_git_tree(root))
    stable_inventory = json.dumps(
        [asdict(entry) for entry in files],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    unavailable = _sha256_bytes(b"<not-a-git-worktree>")
    return ProjectSnapshot(
        index_sha256=unavailable,
        porcelain_sha256=unavailable,
        tree_sha256=_sha256_bytes(stable_inventory),
        files=files,
    )


def _consumer_companion(marker_root: Path) -> Path | None:
    contract = marker_root / "flow-ui-contract" / "contract.json"
    semantic = marker_root / "semantic-ui-tree.json"
    for candidate in (contract, semantic):
        if _is_single_link_regular(candidate):
            return candidate
    return None


def _is_single_link_regular(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    return stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1


def _is_valid_ui_pen(path: Path) -> bool:
    """Reject text placeholders and malformed fixtures from consumer discovery."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return (
        isinstance(document, dict)
        and isinstance(document.get("children"), list)
        and isinstance(document.get("version"), str)
    )


def _git_root(path: Path) -> Path | None:
    try:
        raw = _git_bytes(path, "rev-parse", "--show-toplevel")
    except RuntimeError:
        return None
    return Path(raw.decode().strip()).resolve()


def _git_bytes(project: Path, *args: str) -> bytes:
    # Git integration is argv-only and bounded; callers validate exit and preserve raw bytes.
    result = subprocess.run(
        ["git", *args],
        cwd=project,
        check=False,
        capture_output=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git command failed with exit {result.returncode}: git {' '.join(args)}"
        )
    return result.stdout


def _inventory_non_git_tree(root: Path) -> Iterable[TreeEntry]:
    def visit(directory: Path) -> Iterable[TreeEntry]:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as error:
            relative = directory.relative_to(root).as_posix() or "."
            yield _metadata_entry(relative, "unreadable", repr(error).encode(), 0)
            return
        for entry in entries:
            if entry.name == ".git":
                continue
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as error:
                yield _metadata_entry(relative, "unreadable", repr(error).encode(), 0)
                continue
            if stat.S_ISLNK(metadata.st_mode):
                yield _metadata_entry(relative, "symlink", os.readlink(path).encode(), 0)
            elif stat.S_ISDIR(metadata.st_mode):
                yield _metadata_entry(relative, "directory", b"", 0)
                yield from visit(path)
            elif stat.S_ISREG(metadata.st_mode):
                yield TreeEntry(relative, "file", _sha256_file(path), metadata.st_size)
            else:
                identity = f"{metadata.st_mode}:{metadata.st_rdev}".encode()
                yield _metadata_entry(relative, "special", identity, 0)

    return visit(root)


def _metadata_entry(path: str, kind: str, identity: bytes, logical_bytes: int) -> TreeEntry:
    return TreeEntry(path, kind, _sha256_bytes(identity), logical_bytes)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
