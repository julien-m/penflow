# @spec FR-006 FR-007 FR-008 FR-009: Feature 074 managed-run lifecycle.
"""Managed-run lifecycle responsibility module."""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from pathlib import Path

from .artifact_policy import MANAGED_TEMP_ROOT
from .run_manifest import load_manifest
from .run_lock import LOCK_NAME
from .run_models import ManagedRunManifest
from .run_receipts import LifecycleFinding
from .run_states import CleanupState, LifecycleBlockedError

MANAGED_ROOT_NAME = MANAGED_TEMP_ROOT


def enumerate_managed_root(project_root: str | Path) -> tuple[LifecycleFinding, ...]:
    """Enumerate the closed managed-root grammar without following symlinks."""
    root = Path(project_root).resolve()
    temp_root = root / MANAGED_ROOT_NAME
    if not temp_root.exists():
        return ()
    findings: list[LifecycleFinding] = []
    manifests = _load_manifest_inventory(temp_root, findings)
    _enumerate_root_children(temp_root, findings)
    _enumerate_control_directory(temp_root / "manifests", "manifest", findings)
    _enumerate_control_directory(temp_root / "receipts", "receipt", findings)
    _enumerate_runs(temp_root, manifests, findings)
    return tuple(sorted(set(findings)))


def inventory_managed_tree(
    project_root: str | Path,
    manifest: ManagedRunManifest,
) -> dict[str, int]:
    """Stream catalog metadata and return exact count/logical-byte totals."""
    root = Path(project_root).resolve()
    count = 0
    logical_bytes = 0
    for entry in manifest.entries:
        target = root / entry.relative_path
        metadata = target.lstat()
        if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1:
            count += 1
            logical_bytes += metadata.st_size
    return {"count": count, "logical_bytes": logical_bytes}


def _load_manifest_inventory(
    temp_root: Path,
    findings: list[LifecycleFinding],
) -> dict[str, ManagedRunManifest]:
    inventory: dict[str, ManagedRunManifest] = {}
    manifests = temp_root / "manifests"
    if not manifests.is_dir():
        return inventory
    for path in sorted(manifests.iterdir(), key=lambda item: item.name):
        if path.is_symlink() or not path.name.endswith(".json"):
            continue
        try:
            manifest = load_manifest(path)
        except LifecycleBlockedError as error:
            findings.append(
                LifecycleFinding(
                    error.code, path.relative_to(temp_root.parent).as_posix(), error.message
                )
            )
            continue
        if path.name != f"{manifest.run_id}.json":
            findings.append(
                LifecycleFinding(
                    "manifest.identity_mismatch",
                    path.relative_to(temp_root.parent).as_posix(),
                    "manifest filename does not match run_id",
                )
            )
            continue
        inventory[manifest.run_id] = manifest
    return inventory


def _enumerate_root_children(temp_root: Path, findings: list[LifecycleFinding]) -> None:
    allowed = {LOCK_NAME, "manifests", "runs", "receipts"}
    for child in sorted(temp_root.iterdir(), key=lambda item: item.name):
        if child.name in allowed or _looks_like_tombstone(child.name):
            continue
        findings.append(
            LifecycleFinding(
                "temp.unknown_root_object",
                child.relative_to(temp_root.parent).as_posix(),
                "object is outside the managed-root grammar",
            )
        )


def _looks_like_tombstone(name: str) -> bool:
    return name.startswith(f"{LOCK_NAME}.") and name.endswith(".tombstone")


def _enumerate_control_directory(
    directory: Path,
    kind: str,
    findings: list[LifecycleFinding],
) -> None:
    if not directory.exists():
        return
    if directory.is_symlink() or not directory.is_dir():
        findings.append(
            LifecycleFinding(
                "temp.unknown_root_object",
                directory.relative_to(directory.parent.parent).as_posix(),
                f"{kind} control path must be a directory",
            )
        )
        return
    for child in sorted(directory.iterdir(), key=lambda item: item.name):
        is_json = child.name.endswith(".json") and not child.name.startswith(".")
        if is_json and child.is_file() and not child.is_symlink():
            continue
        code = (
            "temp.orphan_atomic_file" if child.name.startswith(".") else "temp.unknown_root_object"
        )
        findings.append(
            LifecycleFinding(
                code,
                child.relative_to(directory.parent.parent).as_posix(),
                f"unknown {kind} control object",
            )
        )


def _enumerate_runs(
    temp_root: Path,
    manifests: Mapping[str, ManagedRunManifest],
    findings: list[LifecycleFinding],
) -> None:
    runs = temp_root / "runs"
    if not runs.exists():
        for run_id in manifests:
            findings.append(
                LifecycleFinding(
                    "temp.manifest_payload_missing",
                    f"{MANAGED_ROOT_NAME}/runs/{run_id}",
                    "manifest requires a payload directory",
                )
            )
        return
    if runs.is_symlink() or not runs.is_dir():
        findings.append(
            LifecycleFinding(
                "temp.unknown_root_object", f"{MANAGED_ROOT_NAME}/runs", "runs is invalid"
            )
        )
        return
    for run_dir in sorted(runs.iterdir(), key=lambda item: item.name):
        relative = run_dir.relative_to(temp_root.parent).as_posix()
        manifest = manifests.get(run_dir.name)
        if run_dir.is_symlink() or not run_dir.is_dir():
            findings.append(
                LifecycleFinding("temp.unknown_run_object", relative, "run must be a directory")
            )
            continue
        if manifest is None:
            findings.append(LifecycleFinding("temp.orphan_run", relative, "run has no manifest"))
            continue
        known = {entry.relative_path for entry in manifest.entries}
        for descendant in _walk_lstat(run_dir):
            descendant_relative = descendant.relative_to(temp_root.parent).as_posix()
            if descendant_relative not in known:
                findings.append(
                    LifecycleFinding(
                        "temp.unknown_run_object",
                        descendant_relative,
                        "run descendant is not catalogued",
                    )
                )
    for run_id, manifest in manifests.items():
        payload = runs / run_id
        receipt = temp_root / "receipts" / f"{run_id}.json"
        terminal_absence = manifest.cleanup_state is CleanupState.COMPLETED and receipt.is_file()
        if not payload.exists() and not terminal_absence:
            findings.append(
                LifecycleFinding(
                    "temp.manifest_payload_missing",
                    payload.relative_to(temp_root.parent).as_posix(),
                    "manifest requires a payload directory",
                )
            )


def _walk_lstat(root: Path) -> list[Path]:
    paths: list[Path] = []
    stack = [root]
    while stack:
        current = stack.pop()
        with os.scandir(current) as iterator:
            children = sorted(iterator, key=lambda entry: entry.name, reverse=True)
        for child in children:
            path = Path(child.path)
            paths.append(path)
            if child.is_dir(follow_symlinks=False):
                stack.append(path)
    return paths
