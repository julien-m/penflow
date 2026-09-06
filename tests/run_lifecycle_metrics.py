# @spec(FR-006)
# @spec(FR-007)
# @spec(FR-008)
# @spec(FR-009)
"""Managed-run lifecycle safety and crash-consistency tests for feature 074."""

from __future__ import annotations

import os
import platform
import plistlib
import subprocess
import sys
import time
from pathlib import Path


from penflow.run_lifecycle import (
    CleanupState,
    ManagedRunManifest,
    ManifestPathEntry,
    OwnerLiveness,
    ProducerState,
)

from run_lifecycle_fixtures import RUN_ID, _git, _owner, _entry

from typing import Any


def _large_manifest(
    project: Path, run_dir: Path, count: int, total_bytes: int
) -> tuple[ManagedRunManifest, float]:
    """Allocate the complete sparse-file fixture and its actual manifest entries."""
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

    return manifest, fixture_elapsed


def _qe7_receipt(
    project: Path,
    status: str,
    count: int,
    total_bytes: int,
    reported: dict[str, int],
    elapsed: float,
    recomputed: int,
    peak_rss_bytes: int,
    peak_open_fds: int,
    fixture_elapsed: float,
) -> dict[str, Any]:
    """Record actual reference-host metadata and the unchanged QE7 measurements."""
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

    return receipt
