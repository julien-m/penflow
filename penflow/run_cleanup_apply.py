# @spec FR-003 FR-004 FR-005 FR-006: Feature 075 scoped cleanup application.
"""Managed-run lifecycle responsibility module."""

from __future__ import annotations

import os
import stat
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Self

from .artifact_policy import MANAGED_TEMP_ROOT
from .doctor_context import ProjectContext
from .run_cleanup_plan import (
    _cleanup_git_snapshot,
    _cleanup_project_context,
    _identity_matches,
)
from .run_lock import _fsync_directory
from .run_manifest import atomic_write_json, transition_manifest
from .run_models import (
    CleanupReceiptSummary,
    ManagedRunManifest,
    ManifestPathEntry,
    SCHEMA_VERSION,
    _validated_relative_path,
)
from .run_receipts import (
    CleanupItem,
    CleanupPlan,
    CleanupReceipt,
    LifecycleFinding,
)
from .run_states import (
    CleanupState,
    CleanupStatus,
    EntryKind,
    LifecycleBlockedError,
    LifecyclePhase,
)

MANAGED_ROOT_NAME = MANAGED_TEMP_ROOT


def apply_cleanup_plan(
    project_root: str | Path | ProjectContext,
    manifest: ManagedRunManifest,
    plan: CleanupPlan,
    *,
    phase: LifecyclePhase = LifecyclePhase.POSTFLIGHT,
) -> CleanupReceipt:
    """Apply one eligible snapshot with Git and per-entry identity rechecks.

    Side effects:
        Acquires the worktree Git `index.lock`, publishes retryable manifest
        revisions and a compact receipt, then unlinks only catalogued entries.
    """
    context = _cleanup_project_context(project_root)
    root = context.project_root
    if plan.run_id != manifest.run_id:
        raise LifecycleBlockedError("cleanup.plan_mismatch", "plan run does not match manifest")
    if not plan.eligible:
        failed = _cleanup_failed_manifest(manifest, plan.blocking_findings, phase)
        return _receipt_from_failure(root, failed, plan.blocking_findings, phase)
    if manifest.cleanup_state is CleanupState.COMPLETED:
        return _empty_completed_receipt(manifest, phase)
    working = manifest
    if working.cleanup_state is CleanupState.CLEANUP_FAILED:
        working = transition_manifest(working, cleanup_state=CleanupState.ELIGIBLE)
    working = transition_manifest(working, cleanup_state=CleanupState.IN_PROGRESS)
    _persist_manifest(root, working)
    _publish_receipt(root, _empty_attempt_receipt(working, phase))
    deleted: list[CleanupItem] = []
    blocked: list[CleanupItem] = []
    errors: list[LifecycleFinding] = []
    try:
        with _GitIndexLock(context, plan.index_digest, plan.porcelain_v2) as git_lock:
            for entry in plan.ordered_entries:
                git_lock.verify_unchanged()
                _delete_entry(root, entry)
                deleted.append(CleanupItem(entry.relative_path, entry.logical_bytes))
                working = _mark_entry(working, entry.relative_path, CleanupStatus.DELETED)
                _persist_manifest(root, working)
    except LifecycleBlockedError as error:
        current_path = _first_remaining_path(working)
        finding = LifecycleFinding(error.code, current_path, error.message)
        errors.append(finding)
        blocked.append(CleanupItem(current_path, 0, error.code))
        failed = transition_manifest(working, cleanup_state=CleanupState.CLEANUP_FAILED)
        failed = _with_cleanup_summary(failed, phase, deleted, plan.preserved_entries, blocked)
        failed = replace(failed, blocking_findings=(error.code,))
        _persist_manifest(root, failed)
        receipt = _make_receipt(failed, phase, deleted, plan.preserved_entries, blocked, errors)
        _publish_receipt(root, receipt)
        return receipt
    completed = transition_manifest(working, cleanup_state=CleanupState.COMPLETED)
    completed = _with_cleanup_summary(completed, phase, deleted, plan.preserved_entries, ())
    completed = replace(completed, blocking_findings=())
    _persist_manifest(root, completed)
    receipt = _make_receipt(completed, phase, deleted, plan.preserved_entries, (), ())
    _publish_receipt(root, receipt)
    _remove_completed_control_manifest(root, completed)
    return receipt


@dataclass(slots=True)
class _GitIndexLock:
    context: ProjectContext
    expected_digest: str
    expected_porcelain: bytes
    path: Path | None = None
    inode: int | None = None

    def __enter__(self) -> Self:
        # The Git index is repository metadata, so its transient lock is the sole
        # owned mutation outside project_root. The resolved git_dir is immutable
        # and the created inode is verified before removal.
        self.path = self.context.git_dir / "index.lock"
        try:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise LifecycleBlockedError(
                "git.index_changed", "Git index lock already exists"
            ) from error
        try:
            self.inode = os.fstat(descriptor).st_ino
        finally:
            os.close(descriptor)
        self.verify_unchanged()
        return self

    def verify_unchanged(self) -> None:
        digest, porcelain = _cleanup_git_snapshot(self.context)
        if digest != self.expected_digest or porcelain != self.expected_porcelain:
            raise LifecycleBlockedError("git.index_changed", "Git index or status changed")

    def __exit__(self, *_error: object) -> None:
        if self.path is None or self.inode is None:
            return
        try:
            metadata = self.path.lstat()
        except FileNotFoundError:
            raise LifecycleBlockedError("git.index_changed", "owned Git lock disappeared")
        if metadata.st_ino != self.inode:
            raise LifecycleBlockedError("git.index_changed", "Git lock identity changed")
        self.path.unlink()
        _fsync_directory(self.path.parent)


def _delete_entry(root: Path, entry: ManifestPathEntry) -> None:
    descriptor, name = _open_parent_descriptor(root, entry.relative_path)
    try:
        metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        include_links = entry.kind is EntryKind.FILE
        if not _identity_matches(entry, metadata, include_link_count=include_links):
            raise LifecycleBlockedError("cleanup.identity_changed", "entry identity changed")
        if entry.kind is EntryKind.FILE:
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise LifecycleBlockedError(
                    "cleanup.identity_changed", "file type/link count changed"
                )
            os.unlink(name, dir_fd=descriptor)
        else:
            if not stat.S_ISDIR(metadata.st_mode):
                raise LifecycleBlockedError("cleanup.identity_changed", "directory type changed")
            child_descriptor = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
            try:
                if os.listdir(child_descriptor):
                    raise LifecycleBlockedError(
                        "cleanup.directory_not_empty", "directory is not empty"
                    )
            finally:
                os.close(child_descriptor)
            os.rmdir(name, dir_fd=descriptor)
    except FileNotFoundError as error:
        raise LifecycleBlockedError("cleanup.identity_changed", "entry disappeared") from error
    except OSError as error:
        raise LifecycleBlockedError("cleanup.io_failed", str(error)) from error
    finally:
        os.close(descriptor)


def _open_parent_descriptor(root: Path, relative_path: str) -> tuple[int, str]:
    parts = PurePosixPath(_validated_relative_path(relative_path)).parts
    descriptor = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        for component in parts[:-1]:
            next_descriptor = os.open(
                component,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor, parts[-1]
    except OSError as error:
        os.close(descriptor)
        raise LifecycleBlockedError("cleanup.identity_changed", str(error)) from error


def _persist_manifest(root: Path, manifest: ManagedRunManifest) -> None:
    path = root / MANAGED_ROOT_NAME / "manifests" / f"{manifest.run_id}.json"
    atomic_write_json(path, manifest.to_dict(), revision=manifest.revision)


def _mark_entry(
    manifest: ManagedRunManifest, relative_path: str, status: CleanupStatus
) -> ManagedRunManifest:
    entries = tuple(
        replace(entry, cleanup_status=status) if entry.relative_path == relative_path else entry
        for entry in manifest.entries
    )
    return replace(manifest, revision=manifest.revision + 1, entries=entries)


def _first_remaining_path(manifest: ManagedRunManifest) -> str:
    for entry in manifest.entries:
        if entry.cleanup_status is not CleanupStatus.DELETED:
            return entry.relative_path
    return f"{MANAGED_ROOT_NAME}/runs/{manifest.run_id}"


def _with_cleanup_summary(
    manifest: ManagedRunManifest,
    phase: LifecyclePhase,
    deleted: Sequence[CleanupItem],
    preserved: Sequence[ManifestPathEntry],
    blocked: Sequence[CleanupItem],
) -> ManagedRunManifest:
    summary = CleanupReceiptSummary(
        phase=phase,
        reclaimed_bytes=sum(item.logical_bytes for item in deleted),
        preserved_bytes=sum(entry.logical_bytes for entry in preserved),
        blocked_bytes=sum(item.logical_bytes for item in blocked),
    )
    return replace(manifest, revision=manifest.revision + 1, last_cleanup_receipt=summary)


def _make_receipt(
    manifest: ManagedRunManifest,
    phase: LifecyclePhase,
    deleted: Sequence[CleanupItem],
    preserved: Sequence[ManifestPathEntry],
    blocked: Sequence[CleanupItem],
    errors: Sequence[LifecycleFinding],
) -> CleanupReceipt:
    preserved_items = tuple(
        CleanupItem(entry.relative_path, entry.logical_bytes) for entry in preserved
    )
    return CleanupReceipt(
        schema_version=SCHEMA_VERSION,
        run_id=manifest.run_id,
        phase=phase,
        cleanup_state=manifest.cleanup_state,
        deleted=tuple(deleted),
        preserved=preserved_items,
        blocked=tuple(blocked),
        errors=tuple(errors),
        reclaimed_bytes=sum(item.logical_bytes for item in deleted),
        preserved_bytes=sum(item.logical_bytes for item in preserved_items),
        blocked_bytes=sum(item.logical_bytes for item in blocked),
        manifest=manifest,
    )


def _publish_receipt(root: Path, receipt: CleanupReceipt) -> None:
    path = root / MANAGED_ROOT_NAME / "receipts" / f"{receipt.run_id}.json"
    atomic_write_json(path, receipt.to_dict(), revision=receipt.manifest.revision)


def _empty_attempt_receipt(manifest: ManagedRunManifest, phase: LifecyclePhase) -> CleanupReceipt:
    return _make_receipt(manifest, phase, (), (), (), ())


def _empty_completed_receipt(manifest: ManagedRunManifest, phase: LifecyclePhase) -> CleanupReceipt:
    return _make_receipt(manifest, phase, (), (), (), ())


def _cleanup_failed_manifest(
    manifest: ManagedRunManifest,
    findings: Sequence[LifecycleFinding],
    phase: LifecyclePhase,
) -> ManagedRunManifest:
    current = manifest
    if current.cleanup_state is CleanupState.ELIGIBLE:
        current = transition_manifest(current, cleanup_state=CleanupState.IN_PROGRESS)
    if current.cleanup_state is CleanupState.IN_PROGRESS:
        current = transition_manifest(current, cleanup_state=CleanupState.CLEANUP_FAILED)
    blocked_items = tuple(
        CleanupItem(item.relative_path, item.logical_bytes, item.code) for item in findings
    )
    current = _with_cleanup_summary(current, phase, (), (), blocked_items)
    return replace(current, blocking_findings=tuple(sorted({item.code for item in findings})))


def _receipt_from_failure(
    root: Path,
    manifest: ManagedRunManifest,
    findings: Sequence[LifecycleFinding],
    phase: LifecyclePhase,
) -> CleanupReceipt:
    blocked = tuple(
        CleanupItem(finding.relative_path, finding.logical_bytes, finding.code)
        for finding in findings
    )
    receipt = _make_receipt(manifest, phase, (), (), blocked, findings)
    _persist_manifest(root, manifest)
    _publish_receipt(root, receipt)
    return receipt


def _remove_completed_control_manifest(root: Path, manifest: ManagedRunManifest) -> None:
    run_directory = root / MANAGED_ROOT_NAME / "runs" / manifest.run_id
    if run_directory.exists():
        try:
            run_directory.rmdir()
        except OSError as error:
            raise LifecycleBlockedError(
                "cleanup.directory_not_empty",
                f"completed run payload directory remains non-empty: {error}",
            ) from error
        _fsync_directory(run_directory.parent)
    path = root / MANAGED_ROOT_NAME / "manifests" / f"{manifest.run_id}.json"
    if path.exists():
        path.unlink()
        _fsync_directory(path.parent)
