# @spec(FR-006)
# @spec(FR-007)
# @spec(FR-008)
# @spec(FR-009)
"""Managed-run lifecycle safety and crash-consistency tests for feature 074."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from penflow.run_lifecycle import (
    CleanupState,
    EntryKind,
    ManagedRunManifest,
    ManifestPathEntry,
    OwnerIdentity,
    OwnerLiveness,
    ProducerState,
    Retention,
    allocate_run,
    transition_manifest,
)

RUN_ID = "run-074-safe"


def _git(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def git_project(tmp_path: Path) -> Path:
    project = tmp_path / "consumer"
    project.mkdir()
    _git(project, "init", "-q")
    _git(project, "config", "user.email", "penflow@example.invalid")
    _git(project, "config", "user.name", "Penflow Test")
    (project / ".gitignore").write_text(".penflow-tmp/\n", encoding="utf-8")
    (project / "ui.pen").write_text('{"children":[],"version":"1.0"}\n', encoding="utf-8")
    _git(project, "add", ".gitignore", "ui.pen")
    _git(project, "commit", "-qm", "fixture")
    return project


def _owner(
    *, pid: int | None = None, verification: OwnerLiveness = OwnerLiveness.LIVE
) -> OwnerIdentity:
    return OwnerIdentity(
        pid=os.getpid() if pid is None else pid,
        process_start_token="start-074",
        host_id="host-074",
        boot_id="boot-074",
        verification=verification,
    )


def _entry(
    project: Path, relative_path: str, *, retention: Retention = Retention.WORKING
) -> ManifestPathEntry:
    target = project / relative_path
    metadata = target.lstat()
    kind = EntryKind.DIRECTORY if stat.S_ISDIR(metadata.st_mode) else EntryKind.FILE
    logical_bytes = metadata.st_size if kind is EntryKind.FILE else 0
    return ManifestPathEntry(
        relative_path=relative_path,
        kind=kind,
        device=metadata.st_dev,
        inode=metadata.st_ino,
        mode=metadata.st_mode,
        link_count=metadata.st_nlink,
        logical_bytes=logical_bytes,
        retention=retention,
    )


def _allocated(project: Path, *, entries: tuple[ManifestPathEntry, ...] = ()) -> ManagedRunManifest:
    return allocate_run(
        project,
        run_id=RUN_ID,
        command="run",
        owner=_owner(),
        entries=entries,
        created_at="2026-08-25T00:00:00Z",
    )


def _eligible(manifest: ManagedRunManifest) -> ManagedRunManifest:
    active = transition_manifest(manifest, producer_state=ProducerState.ACTIVE)
    failed = transition_manifest(active, producer_state=ProducerState.FAILED)
    return transition_manifest(failed, cleanup_state=CleanupState.ELIGIBLE)


def _write_orphan_atomic(root: Path) -> None:
    manifests = root / "manifests"
    manifests.mkdir()
    (manifests / ".run-1.2.tmp").write_text("partial", encoding="utf-8")
