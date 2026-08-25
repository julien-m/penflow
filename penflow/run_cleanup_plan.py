# @spec FR-003 FR-004 FR-005 FR-006: Feature 075 scoped cleanup planning.
"""Managed-run lifecycle responsibility module."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import replace
from pathlib import Path, PurePosixPath

from .artifact_policy import MANAGED_TEMP_ROOT, Retention
from .doctor_context import ProjectContext, SubprocessGitGateway, _resolve_project_context
from .doctor_git import _capture_git_snapshot, _managed_git_paths
from .run_inventory import enumerate_managed_root, _walk_lstat
from .run_models import ManagedRunManifest, ManifestPathEntry, _validated_relative_path
from .run_receipts import CleanupPlan, LifecycleFinding
from .run_states import CleanupState, CleanupStatus, EntryKind, LifecycleBlockedError, ProducerState

MANAGED_ROOT_NAME = MANAGED_TEMP_ROOT


def build_cleanup_plan(
    project_root: str | Path | ProjectContext,
    manifest: ManagedRunManifest,
    *,
    canonical_pen: str | Path,
) -> CleanupPlan:
    """Build a complete all-or-nothing safety snapshot before any deletion."""
    context = _cleanup_project_context(project_root)
    root = context.project_root
    canonical = Path(canonical_pen).resolve()
    blocked_git_paths = {
        state.relative_path for state in _managed_git_paths(context, SubprocessGitGateway())
    }
    findings = list(enumerate_managed_root(root))
    if manifest.producer_state not in {ProducerState.SUCCEEDED, ProducerState.FAILED}:
        findings.append(
            LifecycleFinding(
                "cleanup.producer_active",
                f"{MANAGED_ROOT_NAME}/manifests/{manifest.run_id}.json",
                "nonterminal producer state is not cleanup-eligible",
            )
        )
    findings.extend(_durable_output_findings(root, manifest))
    preserved, candidates, catalog_findings = _classify_manifest_entries(
        root,
        canonical,
        manifest,
        blocked_git_paths,
    )
    findings.extend(catalog_findings)
    findings.extend(_unlisted_descendant_findings(root, manifest))
    state_finding = _cleanup_state_finding(manifest)
    if state_finding is not None:
        findings.append(state_finding)
    index_digest, porcelain = _cleanup_git_snapshot(context)
    # Eligibility is decided for the entire run before the first unlink.
    eligible = not findings and state_finding is None
    ordered = tuple(sorted(candidates, key=_deletion_order))
    return CleanupPlan(
        run_id=manifest.run_id,
        eligible=eligible,
        ordered_entries=ordered,
        preserved_entries=tuple(sorted(preserved, key=lambda entry: entry.relative_path)),
        blocking_findings=tuple(sorted(set(findings))),
        index_digest=index_digest,
        porcelain_v2=porcelain,
    )


def _classify_manifest_entries(
    root: Path,
    canonical: Path,
    manifest: ManagedRunManifest,
    blocked_git_paths: set[str],
) -> tuple[list[ManifestPathEntry], list[ManifestPathEntry], list[LifecycleFinding]]:
    """Separate preserved and deletable entries while collecting every finding."""

    preserved: list[ManifestPathEntry] = []
    candidates: list[ManifestPathEntry] = []
    findings: list[LifecycleFinding] = []
    seen_paths: set[str] = set()
    for entry in manifest.entries:
        if entry.relative_path in seen_paths:
            findings.append(_finding("manifest.entry_duplicate", entry, "duplicate catalog path"))
            continue
        seen_paths.add(entry.relative_path)
        if entry.cleanup_status is CleanupStatus.DELETED:
            continue
        if entry.retention is Retention.DURABLE or entry.references:
            preserved.append(replace(entry, cleanup_status=CleanupStatus.PRESERVED))
            continue
        entry_findings = _evaluate_entry(root, canonical, entry, blocked_git_paths)
        findings.extend(entry_findings)
        if not entry_findings:
            candidates.append(entry)
    return preserved, candidates, findings


def _cleanup_state_finding(manifest: ManagedRunManifest) -> LifecycleFinding | None:
    """Return the single cleanup-state blocker, if the run is not eligible."""

    if manifest.cleanup_state in {
        CleanupState.ELIGIBLE,
        CleanupState.CLEANUP_FAILED,
        CleanupState.COMPLETED,
    }:
        return None
    return LifecycleFinding(
        "cleanup.state_ineligible",
        f"{MANAGED_ROOT_NAME}/manifests/{manifest.run_id}.json",
        f"cleanup state {manifest.cleanup_state.value} is not eligible",
    )


def _evaluate_entry(
    root: Path,
    canonical: Path,
    entry: ManifestPathEntry,
    blocked_git_paths: set[str],
) -> list[LifecycleFinding]:
    findings: list[LifecycleFinding] = []
    try:
        relative = _validated_relative_path(entry.relative_path)
    except LifecycleBlockedError as error:
        return [
            LifecycleFinding(error.code, entry.relative_path, error.message, entry.logical_bytes)
        ]
    target = root / relative
    resolved_temp = (root / MANAGED_ROOT_NAME).resolve()
    resolved_target = target.resolve(strict=False)
    if not _is_below(resolved_target, root) or not _is_below(resolved_target, resolved_temp):
        findings.append(
            _finding("cleanup.path_escape", entry, "resolved path escapes managed root")
        )
    if resolved_target == canonical:
        findings.append(_finding("cleanup.canonical_pen", entry, "canonical ui.pen is protected"))
    try:
        metadata = target.lstat()
    except FileNotFoundError:
        findings.append(_finding("cleanup.identity_changed", entry, "catalogued path is absent"))
        return findings
    if stat.S_ISLNK(metadata.st_mode):
        findings.append(_finding("cleanup.symlink", entry, "symlink deletion is forbidden"))
    elif stat.S_ISREG(metadata.st_mode):
        if metadata.st_nlink != 1:
            findings.append(_finding("cleanup.hardlink", entry, "hard-linked file is forbidden"))
        if entry.kind is not EntryKind.FILE:
            findings.append(_finding("cleanup.identity_changed", entry, "kind changed"))
    elif stat.S_ISDIR(metadata.st_mode):
        if entry.kind is not EntryKind.DIRECTORY:
            findings.append(_finding("cleanup.identity_changed", entry, "kind changed"))
        if os.path.ismount(target):
            findings.append(_finding("cleanup.mount_point", entry, "mount point is forbidden"))
    else:
        findings.append(_finding("cleanup.special_file", entry, "special file is forbidden"))
    if not _identity_matches(entry, metadata, include_link_count=entry.kind is EntryKind.FILE):
        findings.append(_finding("cleanup.identity_changed", entry, "filesystem identity changed"))
    if entry.kind is EntryKind.FILE and metadata.st_size != entry.logical_bytes:
        findings.append(_finding("cleanup.identity_changed", entry, "logical byte size changed"))
    if entry.relative_path in blocked_git_paths:
        findings.append(_finding("git.path_blocked", entry, "path is tracked or staged"))
    return findings


def _durable_output_findings(root: Path, manifest: ManagedRunManifest) -> list[LifecycleFinding]:
    findings: list[LifecycleFinding] = []
    for output in manifest.durable_outputs:
        relative = PurePosixPath(output.relative_path)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or relative.as_posix() != output.relative_path
        ):
            findings.append(
                LifecycleFinding(
                    "cleanup.reference_invalid",
                    output.relative_path,
                    "durable output path is unsafe",
                )
            )
            continue
        path = root / output.relative_path
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            findings.append(
                LifecycleFinding(
                    "cleanup.reference_missing",
                    output.relative_path,
                    "durable output is missing",
                )
            )
            continue
        is_invalid = (
            not output.finalized
            or output.manifest_revision > manifest.revision
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or path.is_symlink()
            or not _is_below(path.resolve(), root)
        )
        if is_invalid:
            findings.append(
                LifecycleFinding(
                    "cleanup.reference_invalid",
                    output.relative_path,
                    "durable output identity/finalization is invalid",
                    metadata.st_size if stat.S_ISREG(metadata.st_mode) else 0,
                )
            )
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != output.sha256:
            findings.append(
                LifecycleFinding(
                    "cleanup.reference_hash_mismatch",
                    output.relative_path,
                    "durable output digest changed",
                    metadata.st_size,
                )
            )
    return findings


def _unlisted_descendant_findings(
    root: Path, manifest: ManagedRunManifest
) -> list[LifecycleFinding]:
    known = {entry.relative_path for entry in manifest.entries}
    run_dir = root / MANAGED_ROOT_NAME / "runs" / manifest.run_id
    if not run_dir.is_dir():
        return []
    findings: list[LifecycleFinding] = []
    for descendant in _walk_lstat(run_dir):
        relative = descendant.relative_to(root).as_posix()
        if relative not in known:
            findings.append(
                LifecycleFinding(
                    "temp.unknown_run_object", relative, "run descendant is not catalogued"
                )
            )
    return findings


def _finding(code: str, entry: ManifestPathEntry, message: str) -> LifecycleFinding:
    return LifecycleFinding(code, entry.relative_path, message, entry.logical_bytes)


def _identity_matches(
    entry: ManifestPathEntry,
    metadata: os.stat_result,
    *,
    include_link_count: bool,
) -> bool:
    expected = (entry.device, entry.inode, entry.mode)
    actual = (metadata.st_dev, metadata.st_ino, metadata.st_mode)
    if expected != actual:
        return False
    return not include_link_count or entry.link_count == metadata.st_nlink


def _is_below(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return path != root


def _cleanup_project_context(project: str | Path | ProjectContext) -> ProjectContext:
    """Reuse an immutable context or derive one from an exact project selector."""

    if isinstance(project, ProjectContext):
        return project
    return _resolve_project_context(project, cwd=None, git_gateway=SubprocessGitGateway())


def _cleanup_git_snapshot(context: ProjectContext) -> tuple[str, bytes]:
    """Capture the opaque index digest and project-scoped porcelain bytes."""

    snapshot = _capture_git_snapshot(context, SubprocessGitGateway())
    digest = snapshot.index_sha256 or hashlib.sha256(b"").hexdigest()
    return digest, snapshot.porcelain


def _deletion_order(entry: ManifestPathEntry) -> tuple[int, int, str]:
    depth = len(PurePosixPath(entry.relative_path).parts)
    kind_order = 0 if entry.kind is EntryKind.FILE else 1
    return kind_order, -depth, entry.relative_path
