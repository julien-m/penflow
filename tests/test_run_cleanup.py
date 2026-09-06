# @spec(FR-006)
# @spec(FR-007)
# @spec(FR-008)
# @spec(FR-009)
"""Managed-run lifecycle safety and crash-consistency tests for feature 074."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from penflow.run_lifecycle import (
    CleanupState,
    DurableOutput,
    EntryKind,
    ManifestPathEntry,
    ProducerState,
    Retention,
    apply_cleanup_plan,
    build_cleanup_plan,
    transition_manifest,
)
from penflow.project_doctor import resolve_project_context
from penflow.schema_cache import validator_for

from run_lifecycle_fixtures import RUN_ID, _git, _entry, _allocated, _eligible
from run_lifecycle_fixtures import git_project as git_project


def test_mixed_safe_and_symlink_entries_block_the_whole_run(git_project: Path) -> None:
    run_dir = git_project / ".penflow-tmp" / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    safe = run_dir / "safe.bin"
    safe.write_bytes(b"safe")
    outside = git_project / "outside.bin"
    outside.write_bytes(b"outside")
    linked = run_dir / "linked.bin"
    linked.symlink_to(outside)
    safe_entry = _entry(git_project, safe.relative_to(git_project).as_posix())
    linked_stat = linked.lstat()
    linked_entry = ManifestPathEntry(
        relative_path=linked.relative_to(git_project).as_posix(),
        kind=EntryKind.FILE,
        device=linked_stat.st_dev,
        inode=linked_stat.st_ino,
        mode=linked_stat.st_mode,
        link_count=linked_stat.st_nlink,
        logical_bytes=0,
        retention=Retention.WORKING,
    )
    manifest = _eligible(_allocated(git_project, entries=(safe_entry, linked_entry)))

    plan = build_cleanup_plan(git_project, manifest, canonical_pen=git_project / "ui.pen")

    assert plan.eligible is False
    assert "cleanup.symlink" in {finding.code for finding in plan.blocking_findings}
    assert safe.read_bytes() == b"safe"
    assert outside.read_bytes() == b"outside"


def test_unlisted_descendant_blocks_listed_parent_and_leaf(git_project: Path) -> None:
    run_dir = git_project / ".penflow-tmp" / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    listed = run_dir / "listed.bin"
    listed.write_bytes(b"listed")
    unknown = run_dir / "unknown.bin"
    unknown.write_bytes(b"unknown")
    manifest = _eligible(
        _allocated(
            git_project,
            entries=(
                _entry(git_project, listed.relative_to(git_project).as_posix()),
                _entry(git_project, run_dir.relative_to(git_project).as_posix()),
            ),
        )
    )

    plan = build_cleanup_plan(git_project, manifest, canonical_pen=git_project / "ui.pen")

    assert plan.eligible is False
    assert "temp.unknown_run_object" in {finding.code for finding in plan.blocking_findings}
    assert listed.exists() and unknown.exists()


def test_escape_canonical_and_hardlink_candidates_all_block(git_project: Path) -> None:
    run_dir = git_project / ".penflow-tmp" / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    canonical_copy = run_dir / "ui.pen"
    canonical_copy.write_bytes(b"canonical")
    hardlink = run_dir / "hardlink.bin"
    hardlink.write_bytes(b"linked")
    hardlink_peer = run_dir / "hardlink-peer.bin"
    os.link(hardlink, hardlink_peer)
    hardlink_entry = _entry(git_project, hardlink.relative_to(git_project).as_posix())
    escape_entry = replace(
        hardlink_entry, relative_path=".penflow-tmp/runs/run-074-safe/../../outside"
    )
    manifest = _eligible(
        _allocated(
            git_project,
            entries=tuple(
                sorted(
                    (
                        escape_entry,
                        _entry(git_project, canonical_copy.relative_to(git_project).as_posix()),
                        hardlink_entry,
                        _entry(git_project, hardlink_peer.relative_to(git_project).as_posix()),
                    ),
                    key=lambda entry: entry.relative_path,
                )
            ),
        )
    )

    plan = build_cleanup_plan(git_project, manifest, canonical_pen=canonical_copy)

    codes = {finding.code for finding in plan.blocking_findings}
    assert {"cleanup.path_escape", "cleanup.canonical_pen", "cleanup.hardlink"} <= codes
    assert canonical_copy.read_bytes() == b"canonical"
    assert hardlink.read_bytes() == b"linked"


@pytest.mark.parametrize("git_mode", ["tracked", "staged"])
def test_tracked_or_staged_working_entry_blocks_cleanup(git_project: Path, git_mode: str) -> None:
    run_dir = git_project / ".penflow-tmp" / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    payload = run_dir / "tracked.bin"
    payload.write_bytes(b"tracked")
    _git(git_project, "add", "-f", payload.relative_to(git_project).as_posix())
    if git_mode == "tracked":
        _git(git_project, "commit", "-qm", "track unsafe temp")
    manifest = _eligible(
        _allocated(
            git_project, entries=(_entry(git_project, payload.relative_to(git_project).as_posix()),)
        )
    )

    plan = build_cleanup_plan(git_project, manifest, canonical_pen=git_project / "ui.pen")

    assert plan.eligible is False
    assert "git.path_blocked" in {finding.code for finding in plan.blocking_findings}
    assert payload.exists()


def test_nonterminal_producer_and_stale_durable_output_block_cleanup(git_project: Path) -> None:
    run_dir = git_project / ".penflow-tmp" / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    payload = run_dir / "safe.bin"
    payload.write_bytes(b"safe")
    durable = git_project / "durable.json"
    durable.write_bytes(b"current")
    active = transition_manifest(
        _allocated(
            git_project,
            entries=(_entry(git_project, payload.relative_to(git_project).as_posix()),),
        ),
        producer_state=ProducerState.ACTIVE,
    )
    unsafe = replace(
        active,
        cleanup_state=CleanupState.ELIGIBLE,
        durable_outputs=(
            DurableOutput(
                relative_path="durable.json",
                sha256="0" * 64,
                finalized=True,
                manifest_revision=active.revision,
            ),
        ),
    )

    plan = build_cleanup_plan(git_project, unsafe, canonical_pen=git_project / "ui.pen")

    codes = {finding.code for finding in plan.blocking_findings}
    assert {"cleanup.producer_active", "cleanup.reference_hash_mismatch"} <= codes
    assert payload.read_bytes() == b"safe"


def test_cleanup_deletes_children_before_parent_with_exact_bytes_and_is_idempotent(
    git_project: Path,
) -> None:
    run_dir = git_project / ".penflow-tmp" / "runs" / RUN_ID
    nested = run_dir / "nested"
    nested.mkdir(parents=True)
    first = nested / "first.bin"
    second = run_dir / "second.bin"
    first.write_bytes(b"12345")
    second.write_bytes(b"678")
    entries = tuple(
        _entry(git_project, path.relative_to(git_project).as_posix())
        for path in (first, second, nested, run_dir)
    )
    manifest = _eligible(_allocated(git_project, entries=entries))
    plan = build_cleanup_plan(git_project, manifest, canonical_pen=git_project / "ui.pen")

    receipt = apply_cleanup_plan(git_project, manifest, plan)
    repeated = apply_cleanup_plan(
        git_project,
        receipt.manifest,
        build_cleanup_plan(git_project, receipt.manifest, canonical_pen=git_project / "ui.pen"),
    )

    assert receipt.cleanup_state is CleanupState.COMPLETED
    assert receipt.reclaimed_bytes == 8
    assert [item.relative_path for item in receipt.deleted] == [
        first.relative_to(git_project).as_posix(),
        second.relative_to(git_project).as_posix(),
        nested.relative_to(git_project).as_posix(),
        run_dir.relative_to(git_project).as_posix(),
    ]
    assert repeated.reclaimed_bytes == 0
    assert repeated.deleted == ()
    assert (git_project / "ui.pen").read_bytes() == b'{"children":[],"version":"1.0"}\n'


def test_nested_cleanup_reuses_project_context_and_preserves_staged_sibling(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "monorepo"
    target = repository / "projects" / "target"
    sibling = repository / "projects" / "sibling"
    target.mkdir(parents=True)
    sibling.mkdir(parents=True)
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "penflow@example.invalid")
    _git(repository, "config", "user.name", "Penflow Test")
    for project in (target, sibling):
        project.joinpath("ui.pen").write_text('{"children":[],"version":"1.0"}\n', encoding="utf-8")
        project.joinpath(".gitignore").write_text(".penflow-tmp/\n", encoding="utf-8")
    _git(repository, "add", "projects")
    _git(repository, "commit", "-qm", "fixture")
    sibling_payload = sibling / ".penflow-run" / "staged.bin"
    sibling_payload.parent.mkdir()
    sibling_payload.write_bytes(b"sibling")
    _git(repository, "add", "-f", sibling_payload.relative_to(repository).as_posix())
    sibling_before = sibling_payload.read_bytes()
    index_before = (repository / ".git" / "index").read_bytes()
    porcelain_before = _git(repository, "status", "--porcelain=v2", "-z").stdout
    run_dir = target / ".penflow-tmp" / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    payload = run_dir / "working.bin"
    payload.write_bytes(b"target")
    entries = tuple(
        _entry(target, path.relative_to(target).as_posix()) for path in (payload, run_dir)
    )
    manifest = _eligible(_allocated(target, entries=entries))
    context = resolve_project_context(target)

    plan = build_cleanup_plan(context, manifest, canonical_pen=target / "ui.pen")
    receipt = apply_cleanup_plan(context, manifest, plan)

    assert receipt.cleanup_state is CleanupState.COMPLETED
    assert [item.relative_path for item in receipt.deleted] == [
        payload.relative_to(target).as_posix(),
        run_dir.relative_to(target).as_posix(),
    ]
    assert sibling_payload.read_bytes() == sibling_before
    assert (repository / ".git" / "index").read_bytes() == index_before
    assert _git(repository, "status", "--porcelain=v2", "-z").stdout == porcelain_before


def test_existing_git_index_lock_blocks_before_first_delete(git_project: Path) -> None:
    run_dir = git_project / ".penflow-tmp" / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    payload = run_dir / "safe.bin"
    payload.write_bytes(b"safe")
    manifest = _eligible(
        _allocated(
            git_project, entries=(_entry(git_project, payload.relative_to(git_project).as_posix()),)
        )
    )
    plan = build_cleanup_plan(git_project, manifest, canonical_pen=git_project / "ui.pen")
    git_dir = Path(_git(git_project, "rev-parse", "--absolute-git-dir").stdout.strip())
    (git_dir / "index.lock").write_text("other git writer", encoding="utf-8")

    receipt = apply_cleanup_plan(git_project, manifest, plan)

    assert receipt.cleanup_state is CleanupState.CLEANUP_FAILED
    assert receipt.reclaimed_bytes == 0
    assert "git.index_changed" in {item.code for item in receipt.blocked}
    assert payload.read_bytes() == b"safe"
    assert (git_dir / "index.lock").read_text() == "other git writer"


def test_identity_change_after_plan_records_cleanup_failed_without_deletion(
    git_project: Path,
) -> None:
    run_dir = git_project / ".penflow-tmp" / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    payload = run_dir / "safe.bin"
    payload.write_bytes(b"before")
    manifest = _eligible(
        _allocated(
            git_project, entries=(_entry(git_project, payload.relative_to(git_project).as_posix()),)
        )
    )
    plan = build_cleanup_plan(git_project, manifest, canonical_pen=git_project / "ui.pen")
    replacement = run_dir / "replacement.bin"
    # Write first so the atomic replacement guarantees a distinct inode without an absence window.
    replacement.write_bytes(b"after!")
    os.replace(replacement, payload)

    receipt = apply_cleanup_plan(git_project, manifest, plan)

    assert receipt.cleanup_state is CleanupState.CLEANUP_FAILED
    assert receipt.reclaimed_bytes == 0
    assert "cleanup.identity_changed" in {item.code for item in receipt.blocked}
    assert payload.read_bytes() == b"after!"


def test_cleanup_failed_recovery_removes_remaining_entries_and_validates_schemas(
    git_project: Path,
) -> None:
    run_dir = git_project / ".penflow-tmp" / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    payload = run_dir / "retry.bin"
    payload.write_bytes(b"retry")
    manifest = _eligible(
        _allocated(
            git_project,
            entries=tuple(
                sorted(
                    (
                        _entry(git_project, payload.relative_to(git_project).as_posix()),
                        _entry(git_project, run_dir.relative_to(git_project).as_posix()),
                    ),
                    key=lambda entry: entry.relative_path,
                )
            ),
        )
    )
    plan = build_cleanup_plan(git_project, manifest, canonical_pen=git_project / "ui.pen")
    git_dir = Path(_git(git_project, "rev-parse", "--absolute-git-dir").stdout.strip())
    external_lock = git_dir / "index.lock"
    external_lock.write_text("busy", encoding="utf-8")
    failed = apply_cleanup_plan(git_project, manifest, plan)
    external_lock.unlink()

    retry_plan = build_cleanup_plan(
        git_project, failed.manifest, canonical_pen=git_project / "ui.pen"
    )
    recovered = apply_cleanup_plan(git_project, failed.manifest, retry_plan)

    manifest_errors = list(
        validator_for("managed-run-manifest.schema.json").iter_errors(manifest.to_dict())
    )
    receipt_errors = list(
        validator_for("cleanup-receipt.schema.json").iter_errors(recovered.to_dict())
    )
    assert manifest_errors == []
    assert receipt_errors == []
    assert recovered.cleanup_state is CleanupState.COMPLETED
    assert recovered.reclaimed_bytes == len(b"retry")
    assert not run_dir.exists()
