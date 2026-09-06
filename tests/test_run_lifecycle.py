# @spec(FR-006)
# @spec(FR-007)
# @spec(FR-008)
# @spec(FR-009)
"""Managed-run lifecycle safety and crash-consistency tests for feature 074."""

from __future__ import annotations

import json
import os
import resource
import shutil
import time
from dataclasses import replace
from pathlib import Path
from typing import Callable

import pytest

from penflow.run_lifecycle import (
    CleanupState,
    LifecycleBlockedError,
    LifecycleLock,
    OwnerIdentity,
    OwnerLiveness,
    ProducerState,
    atomic_write_json,
    enumerate_managed_root,
    inventory_managed_tree,
    load_manifest,
    reconcile_manifest_owner,
    transition_manifest,
    verify_owner_liveness,
)

from run_lifecycle_fixtures import RUN_ID, _owner, _entry, _allocated, _write_orphan_atomic
from run_lifecycle_fixtures import git_project as git_project
from run_lifecycle_metrics import _large_manifest, _qe7_receipt


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
    manifest, fixture_elapsed = _large_manifest(project, run_dir, count, total_bytes)

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
    receipt = _qe7_receipt(
        project,
        status,
        count,
        total_bytes,
        reported,
        elapsed,
        recomputed,
        peak_rss_bytes,
        peak_open_fds,
        fixture_elapsed,
    )
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
