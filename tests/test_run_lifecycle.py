# @spec(FR-006)
# @spec(FR-007)
# @spec(FR-008)
# @spec(FR-009)
"""Managed-run lifecycle safety and crash-consistency tests for feature 074."""

from __future__ import annotations

import json
import os
import platform
import plistlib
import resource
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from typing import Callable

import pytest

from penflow.run_lifecycle import (
    CleanupState,
    DurableOutput,
    EntryKind,
    LifecycleBlockedError,
    LifecycleLock,
    ManagedRunManifest,
    ManifestPathEntry,
    OwnerIdentity,
    OwnerLiveness,
    ProducerState,
    Retention,
    allocate_run,
    apply_cleanup_plan,
    atomic_write_json,
    build_cleanup_plan,
    enumerate_managed_root,
    inventory_managed_tree,
    load_manifest,
    reconcile_manifest_owner,
    transition_manifest,
    verify_owner_liveness,
)
from penflow.project_doctor import resolve_project_context
from penflow.schema_cache import validator_for

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


def test_manifest_schema_one_round_trips_with_complete_typed_entries(git_project: Path) -> None:
    payload = git_project / ".penflow-tmp" / "runs" / RUN_ID / "snapshot.bin"
    payload.parent.mkdir(parents=True)
    payload.write_bytes(b"managed-bytes")
    manifest = _allocated(
        git_project, entries=(_entry(git_project, payload.relative_to(git_project).as_posix()),)
    )

    loaded = load_manifest(git_project / ".penflow-tmp" / "manifests" / f"{RUN_ID}.json")

    assert loaded == manifest
    encoded = loaded.to_dict()
    assert encoded["schema_version"] == 1
    assert encoded["revision"] == 1
    assert encoded["producer_state"] == "preparing"
    assert encoded["cleanup_state"] == "not_eligible"
    assert encoded["owner"]["verification"] == "LIVE"
    assert encoded["entries"][0]["logical_bytes"] == len(b"managed-bytes")


@pytest.mark.parametrize(
    ("owner", "probe", "expected"),
    [
        (_owner(), lambda _pid: "start-074", OwnerLiveness.LIVE),
        (_owner(), lambda _pid: None, OwnerLiveness.DEAD),
        (_owner(), lambda _pid: (_ for _ in ()).throw(PermissionError()), OwnerLiveness.UNKNOWN),
        (replace(_owner(), host_id="remote"), lambda _pid: "start-074", OwnerLiveness.UNKNOWN),
    ],
)
def test_owner_liveness_requires_full_identity(
    owner: OwnerIdentity,
    probe: Callable[[int], str | None],
    expected: OwnerLiveness,
) -> None:
    assert (
        verify_owner_liveness(
            owner,
            current_host_id="host-074",
            current_boot_id="boot-074",
            process_start_probe=probe,
        )
        is expected
    )


def test_manifest_rejects_out_of_order_transitions(git_project: Path) -> None:
    manifest = _allocated(git_project)

    with pytest.raises(LifecycleBlockedError, match="manifest.transition_invalid"):
        transition_manifest(manifest, producer_state=ProducerState.SUCCEEDED)


def test_dead_owner_recovery_is_explicit_and_unknown_owner_blocks(git_project: Path) -> None:
    active = transition_manifest(_allocated(git_project), producer_state=ProducerState.ACTIVE)

    recovered = reconcile_manifest_owner(active, owner_verifier=lambda _owner: OwnerLiveness.DEAD)
    with pytest.raises(LifecycleBlockedError, match="owner.liveness_unknown"):
        reconcile_manifest_owner(active, owner_verifier=lambda _owner: OwnerLiveness.UNKNOWN)

    assert recovered.producer_state is ProducerState.FAILED
    assert recovered.cleanup_state is CleanupState.ELIGIBLE


def test_atomic_json_revision_is_byte_stable_and_cleans_sibling(tmp_path: Path) -> None:
    destination = tmp_path / "manifests" / "run.json"
    payload = {"z": [2, 1], "a": {"stable": True}}

    atomic_write_json(destination, payload, revision=7)
    first = destination.read_bytes()
    atomic_write_json(destination, payload, revision=7)

    assert destination.read_bytes() == first
    assert first == b'{"a":{"stable":true},"z":[2,1]}\n'
    assert list(destination.parent.glob(".*.tmp")) == []


def test_lifecycle_lock_times_out_for_live_owner_without_age_reclamation(git_project: Path) -> None:
    temp_root = git_project / ".penflow-tmp"
    temp_root.mkdir()
    existing = _owner(pid=4242)
    atomic_write_json(temp_root / ".lifecycle.lock", existing.to_dict(), revision=1)
    ticks = iter((0.0, 0.05, 0.10, 0.15))

    with pytest.raises(LifecycleBlockedError, match="lifecycle.lock_busy"):
        LifecycleLock.acquire(
            git_project,
            _owner(),
            operation="preflight",
            timeout=0.10,
            poll_interval=0.05,
            monotonic=lambda: next(ticks),
            sleep=lambda _seconds: None,
            owner_verifier=lambda _owner: OwnerLiveness.LIVE,
        )

    assert json.loads((temp_root / ".lifecycle.lock").read_text())["pid"] == 4242


def test_lifecycle_lock_reclaims_only_inode_verified_dead_owner(git_project: Path) -> None:
    temp_root = git_project / ".penflow-tmp"
    temp_root.mkdir()
    dead = _owner(pid=4242, verification=OwnerLiveness.DEAD)
    atomic_write_json(temp_root / ".lifecycle.lock", dead.to_dict(), revision=1)

    lock = LifecycleLock.acquire(
        git_project,
        _owner(),
        operation="preflight",
        owner_verifier=lambda _owner: OwnerLiveness.DEAD,
    )
    lock.release()

    assert not (temp_root / ".lifecycle.lock").exists()
    assert list(temp_root.glob("*.tombstone")) == []


@pytest.mark.parametrize(
    ("factory", "code"),
    [
        (lambda root: (root / "mystery").write_text("x"), "temp.unknown_root_object"),
        (lambda root: (root / "runs" / "orphan").mkdir(parents=True), "temp.orphan_run"),
        (_write_orphan_atomic, "temp.orphan_atomic_file"),
    ],
)
def test_managed_root_grammar_enumerates_unknown_objects(
    git_project: Path,
    factory: Callable[[Path], object],
    code: str,
) -> None:
    root = git_project / ".penflow-tmp"
    root.mkdir()
    factory(root)

    findings = enumerate_managed_root(git_project)

    assert code in {finding.code for finding in findings}


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
    payload.unlink()
    payload.write_bytes(b"replacement")

    receipt = apply_cleanup_plan(git_project, manifest, plan)

    assert receipt.cleanup_state is CleanupState.CLEANUP_FAILED
    assert receipt.reclaimed_bytes == 0
    assert "cleanup.identity_changed" in {item.code for item in receipt.blocked}
    assert payload.read_bytes() == b"replacement"


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


def test_large_tree_qe7_metrics(tmp_path: Path) -> None:
    output_value = os.environ.get("PENFLOW_QE7_OUT")
    if output_value is None:
        pytest.skip("set PENFLOW_QE7_OUT to execute the 50k-file reference-host proof")
    consumer_value = os.environ.get("PENFLOW_QE7_CONSUMER")
    project = Path(consumer_value).resolve() if consumer_value else tmp_path / "large-consumer"
    run_dir = project / ".penflow-tmp" / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    count = 50_000
    total_bytes = 5 * 1024**3
    base_size, remainder = divmod(total_bytes, count)
    entries: list[ManifestPathEntry] = []
    fixture_started = time.monotonic()
    for index in range(count):
        path = run_dir / f"artifact-{index:05d}.bin"
        with path.open("wb") as stream:
            stream.truncate(base_size + (1 if index < remainder else 0))
        entries.append(_entry(project, path.relative_to(project).as_posix()))
    fixture_elapsed = time.monotonic() - fixture_started
    manifest = ManagedRunManifest(
        schema_version=1,
        revision=1,
        run_id=RUN_ID,
        command="run",
        producer_state=ProducerState.FAILED,
        cleanup_state=CleanupState.ELIGIBLE,
        created_at="2026-08-25T00:00:00Z",
        updated_at="2026-08-25T00:00:00Z",
        owner=_owner(verification=OwnerLiveness.DEAD),
        entries=tuple(entries),
    )

    started = time.monotonic()
    reported = inventory_managed_tree(project, manifest)
    elapsed = time.monotonic() - started
    recomputed = sum(path.stat().st_size for path in run_dir.iterdir())
    usage = resource.getrusage(resource.RUSAGE_SELF)
    peak_rss_bytes = int(
        usage.ru_maxrss if os.uname().sysname == "Darwin" else usage.ru_maxrss * 1024
    )
    fd_root = Path("/dev/fd") if Path("/dev/fd").is_dir() else Path("/proc/self/fd")
    peak_open_fds = len(tuple(fd_root.iterdir()))
    status = (
        "PASS"
        if reported == {"count": count, "logical_bytes": total_bytes}
        and recomputed == total_bytes
        and elapsed <= 30
        and peak_rss_bytes <= 256 * 1024**2
        and peak_open_fds <= 32
        else "FAIL"
    )
    if platform.system() == "Darwin":
        df_result = subprocess.run(
            ["df", "-P", str(project)],
            check=True,
            capture_output=True,
            text=True,
        )
        mount_point = df_result.stdout.splitlines()[-1].split()[-1]
        filesystem_result = subprocess.run(
            ["/usr/sbin/diskutil", "info", "-plist", mount_point],
            check=True,
            capture_output=True,
        )
        filesystem_info = plistlib.loads(filesystem_result.stdout)
        filesystem = str(filesystem_info.get("FilesystemType", "unknown"))
    else:
        filesystem = subprocess.run(
            ["stat", "-f", "-c", "%T", str(project)],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
    receipt = {
        "schema_version": 1,
        "stable_result": {
            "status": status,
            "commit": _git(Path(__file__).resolve().parents[1], "rev-parse", "HEAD").stdout.strip(),
            "runner": {
                "image_os": os.environ.get("ImageOS", platform.system()),
                "image_version": os.environ.get("ImageVersion", "local"),
                "kernel": platform.release(),
                "architecture": platform.machine(),
                "cpu_count": os.cpu_count() or 1,
                "filesystem": filesystem or "unknown",
                "python_version": platform.python_version(),
            },
            "fixture": {"seed": 74, "file_count": count, "logical_bytes": total_bytes},
            "metrics": {
                "elapsed_seconds": elapsed,
                "peak_rss_bytes": peak_rss_bytes,
                "peak_open_fds": peak_open_fds,
                "reported_logical_bytes": reported["logical_bytes"],
                "recomputed_logical_bytes": recomputed,
            },
        },
        "diagnostics": {
            "fixture_elapsed_seconds": fixture_elapsed,
            "python_executable": sys.executable,
        },
    }
    output = Path(output_value)
    assert output.is_absolute()
    atomic_write_json(output, receipt, revision=1)
    # The external CI consumer is inspected by Doctor immediately after QE7;
    # remove only the exact synthetic run that this test allocated.
    if consumer_value:
        shutil.rmtree(run_dir)

    assert reported["count"] == count
    assert reported["logical_bytes"] == total_bytes
    assert recomputed == total_bytes
    assert elapsed <= 30
    assert peak_rss_bytes <= 256 * 1024**2
    assert peak_open_fds <= 32
