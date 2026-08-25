# @spec FR-006 FR-007 FR-008 FR-009: Feature 074 managed-run lifecycle.
"""Managed-run lifecycle responsibility module."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from .artifact_policy import PRODUCER_COMMANDS, Retention
from .run_lock import _fsync_directory, _write_all, verify_owner_liveness
from .run_models import (
    MANAGED_ROOT_NAME,
    SCHEMA_VERSION,
    ManagedRunManifest,
    ManifestPathEntry,
    OwnerIdentity,
    _nonempty_str,
    _validate_manifest_invariants,
    _validate_transition,
    _validated_relative_path,
    _validated_run_id,
)
from .run_states import CleanupState, EntryKind, LifecycleBlockedError, OwnerLiveness, ProducerState

PRODUCER_COMMAND_IDS = PRODUCER_COMMANDS


def snapshot_manifest_entry(
    project_root: str | Path,
    relative_path: str,
    *,
    retention: Retention = Retention.WORKING,
    references: Sequence[str] = (),
) -> ManifestPathEntry:
    """Capture one no-follow filesystem identity for later cleanup checks."""
    root = Path(project_root).resolve()
    normalized = _validated_relative_path(relative_path)
    metadata = (root / normalized).lstat()
    if stat.S_ISLNK(metadata.st_mode):
        raise LifecycleBlockedError("cleanup.symlink", "symlink cannot be catalogued")
    if stat.S_ISREG(metadata.st_mode):
        kind = EntryKind.FILE
        logical_bytes = metadata.st_size
    elif stat.S_ISDIR(metadata.st_mode):
        kind = EntryKind.DIRECTORY
        logical_bytes = 0
    else:
        raise LifecycleBlockedError("cleanup.special_file", "special file cannot be catalogued")
    return ManifestPathEntry(
        relative_path=normalized,
        kind=kind,
        device=metadata.st_dev,
        inode=metadata.st_ino,
        mode=metadata.st_mode,
        link_count=metadata.st_nlink,
        logical_bytes=logical_bytes,
        retention=retention,
        references=tuple(references),
    )


def register_manifest_entry(
    manifest: ManagedRunManifest,
    entry: ManifestPathEntry,
) -> ManagedRunManifest:
    """Return the next revision with one unique run-owned entry registered."""
    expected_prefix = f"{MANAGED_ROOT_NAME}/runs/{manifest.run_id}/"
    run_root = f"{MANAGED_ROOT_NAME}/runs/{manifest.run_id}"
    if entry.relative_path != run_root and not entry.relative_path.startswith(expected_prefix):
        raise LifecycleBlockedError("manifest.identity_mismatch", "entry belongs to another run")
    if any(existing.relative_path == entry.relative_path for existing in manifest.entries):
        raise LifecycleBlockedError("manifest.entry_duplicate", "entry is already registered")
    entries = tuple(sorted((*manifest.entries, entry), key=lambda item: item.relative_path))
    registered = replace(manifest, revision=manifest.revision + 1, entries=entries)
    _validate_manifest_invariants(registered)
    return registered


def save_manifest(project_root: str | Path, manifest: ManagedRunManifest) -> None:
    """Validate and atomically persist one explicit manifest revision."""
    _validate_manifest_invariants(manifest)
    _persist_manifest(Path(project_root).resolve(), manifest)


def atomic_write_json(path: str | Path, payload: Mapping[str, Any], *, revision: int) -> None:
    """Write stable JSON through a revision-owned sibling and directory fsync.

    Side effects:
        Replaces `path` atomically after flushing the file, then flushes its
        containing directory so the revision is durable before transition.
    """
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".{destination.stem}.{revision}.tmp"
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            _write_all(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        # File fsync must precede replace, and directory fsync must follow it.
        os.replace(temporary, destination)
        _fsync_directory(destination.parent)
    except OSError as error:
        raise LifecycleBlockedError("manifest.atomic_write_failed", str(error)) from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            # The canonical file already contains the only authoritative revision.
            pass


def allocate_run(
    project_root: str | Path,
    *,
    run_id: str,
    command: str,
    owner: OwnerIdentity,
    entries: Sequence[ManifestPathEntry] = (),
    created_at: str,
) -> ManagedRunManifest:
    """Allocate one preparing schema-1 manifest and its payload directory.

    Side effects:
        Creates managed control/payload directories and atomically publishes the
        initial manifest. Existing run identities are never overwritten.
    """
    root = Path(project_root).resolve()
    validated_run_id = _validated_run_id(run_id)
    if command not in PRODUCER_COMMAND_IDS:
        raise LifecycleBlockedError("manifest.command_unknown", f"unknown producer {command}")
    temp_root = root / MANAGED_ROOT_NAME
    manifests = temp_root / "manifests"
    run_dir = temp_root / "runs" / validated_run_id
    receipts = temp_root / "receipts"
    manifest_path = manifests / f"{validated_run_id}.json"
    if manifest_path.exists():
        raise LifecycleBlockedError("manifest.run_exists", f"run already exists: {run_id}")
    for directory in (manifests, run_dir, receipts):
        directory.mkdir(parents=True, exist_ok=True)
    manifest = ManagedRunManifest(
        schema_version=SCHEMA_VERSION,
        revision=1,
        run_id=validated_run_id,
        command=command,
        producer_state=ProducerState.PREPARING,
        cleanup_state=CleanupState.NOT_ELIGIBLE,
        created_at=_nonempty_str(created_at, "created_at"),
        updated_at=created_at,
        owner=owner,
        entries=tuple(sorted(entries, key=lambda entry: entry.relative_path)),
    )
    _validate_manifest_invariants(manifest)
    atomic_write_json(manifest_path, manifest.to_dict(), revision=manifest.revision)
    return manifest


def load_manifest(path: str | Path) -> ManagedRunManifest:
    """Read and validate one external managed-run manifest."""
    manifest_path = Path(path)
    try:
        value = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise LifecycleBlockedError("manifest.invalid", str(error)) from error
    if not isinstance(value, Mapping):
        raise LifecycleBlockedError("manifest.invalid", "manifest must be a JSON object")
    return ManagedRunManifest.from_dict(value)


def transition_manifest(
    manifest: ManagedRunManifest,
    *,
    producer_state: ProducerState | None = None,
    cleanup_state: CleanupState | None = None,
    updated_at: str | None = None,
) -> ManagedRunManifest:
    """Apply one validated producer and/or cleanup transition."""
    new_producer = producer_state or manifest.producer_state
    new_cleanup = cleanup_state or manifest.cleanup_state
    _validate_transition(
        manifest.producer_state,
        new_producer,
        _PRODUCER_TRANSITIONS,
        "producer",
    )
    _validate_transition(
        manifest.cleanup_state,
        new_cleanup,
        _CLEANUP_TRANSITIONS,
        "cleanup",
    )
    transitioned = replace(
        manifest,
        revision=manifest.revision + 1,
        producer_state=new_producer,
        cleanup_state=new_cleanup,
        updated_at=updated_at or manifest.updated_at,
    )
    _validate_manifest_invariants(transitioned)
    return transitioned


def reconcile_manifest_owner(
    manifest: ManagedRunManifest,
    *,
    owner_verifier: Callable[[OwnerIdentity], OwnerLiveness] = verify_owner_liveness,
) -> ManagedRunManifest:
    """Recover a demonstrably dead nonterminal owner or preserve uncertainty.

    Terminal producer states need no owner decision. A live owner remains active;
    UNKNOWN blocks destructive work. DEAD transitions through failed and eligible
    exactly once so a later locked preflight can build a fresh cleanup snapshot.
    """
    if manifest.producer_state in {ProducerState.SUCCEEDED, ProducerState.FAILED}:
        return manifest
    liveness = owner_verifier(manifest.owner)
    if liveness is OwnerLiveness.LIVE:
        return manifest
    if liveness is OwnerLiveness.UNKNOWN:
        raise LifecycleBlockedError(
            "owner.liveness_unknown", "nonterminal run owner cannot be verified"
        )
    recovered = replace(manifest, owner=replace(manifest.owner, verification=OwnerLiveness.DEAD))
    recovered = transition_manifest(recovered, producer_state=ProducerState.FAILED)
    if recovered.cleanup_state is CleanupState.NOT_ELIGIBLE:
        recovered = transition_manifest(recovered, cleanup_state=CleanupState.ELIGIBLE)
    return recovered


_PRODUCER_TRANSITIONS: dict[ProducerState, frozenset[ProducerState]] = {
    ProducerState.PREPARING: frozenset({ProducerState.ACTIVE, ProducerState.FAILED}),
    ProducerState.ACTIVE: frozenset({ProducerState.FINALIZING, ProducerState.FAILED}),
    ProducerState.FINALIZING: frozenset({ProducerState.SUCCEEDED, ProducerState.FAILED}),
    ProducerState.SUCCEEDED: frozenset(),
    ProducerState.FAILED: frozenset(),
}
_CLEANUP_TRANSITIONS: dict[CleanupState, frozenset[CleanupState]] = {
    CleanupState.NOT_ELIGIBLE: frozenset({CleanupState.ELIGIBLE}),
    CleanupState.ELIGIBLE: frozenset({CleanupState.IN_PROGRESS}),
    CleanupState.IN_PROGRESS: frozenset({CleanupState.COMPLETED, CleanupState.CLEANUP_FAILED}),
    CleanupState.CLEANUP_FAILED: frozenset({CleanupState.ELIGIBLE}),
    CleanupState.COMPLETED: frozenset(),
}


def _persist_manifest(root: Path, manifest: ManagedRunManifest) -> None:
    path = root / MANAGED_ROOT_NAME / "manifests" / f"{manifest.run_id}.json"
    atomic_write_json(path, manifest.to_dict(), revision=manifest.revision)
