# @spec FR-006 FR-007 FR-008 FR-009: Feature 074 managed-run lifecycle.
"""Managed-run lifecycle responsibility module."""

from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from .artifact_policy import MANAGED_TEMP_ROOT
from .run_models import OwnerIdentity
from .run_states import LifecycleBlockedError, OwnerLiveness

MANAGED_ROOT_NAME = MANAGED_TEMP_ROOT
LOCK_NAME = ".lifecycle.lock"
LOCK_TIMEOUT_SECONDS = 5.0
LOCK_POLL_SECONDS = 0.05


@dataclass(slots=True)
class LifecycleLock:
    """Exclusive lifecycle lock whose release verifies inode and owner bytes."""

    project_root: Path
    owner: OwnerIdentity
    operation: str
    inode: int
    _released: bool = False

    @classmethod
    def acquire(
        cls,
        project_root: str | Path,
        owner: OwnerIdentity,
        *,
        operation: str,
        timeout: float = LOCK_TIMEOUT_SECONDS,
        poll_interval: float = LOCK_POLL_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        owner_verifier: Callable[[OwnerIdentity], OwnerLiveness] | None = None,
    ) -> Self:
        """Acquire the project lifecycle lock or fail after the normative timeout.

        Side effects:
            Creates `.penflow-tmp/.lifecycle.lock`; a proven-dead lock is first
            atomically renamed to an identity-bound tombstone and reclaimed.
        """
        root = Path(project_root).resolve()
        temp_root = root / MANAGED_ROOT_NAME
        temp_root.mkdir(parents=True, exist_ok=True)
        started = monotonic()
        verifier = owner_verifier or verify_owner_liveness
        while True:
            created_inode = _try_create_lock(temp_root, owner, operation)
            if created_inode is not None:
                return cls(root, owner, operation, created_inode)
            observed = _read_lock(temp_root / LOCK_NAME)
            liveness = verifier(observed[0]) if observed is not None else OwnerLiveness.UNKNOWN
            if observed is not None and liveness is OwnerLiveness.DEAD:
                _reclaim_dead_lock(temp_root, observed)
                continue
            if observed is not None and liveness is OwnerLiveness.UNKNOWN:
                raise LifecycleBlockedError(
                    "owner.liveness_unknown", "existing lifecycle owner cannot be verified"
                )
            # A live owner is never made stale by age; timeout only bounds this contender.
            if monotonic() - started >= timeout:
                raise LifecycleBlockedError(
                    "lifecycle.lock_busy", "live owner holds lifecycle lock"
                )
            sleep(poll_interval)

    def release(self) -> None:
        """Release only the exact lock inode and identity acquired by this owner."""
        if self._released:
            return
        temp_root = self.project_root / MANAGED_ROOT_NAME
        lock_path = temp_root / LOCK_NAME
        observed = _read_lock(lock_path)
        if observed is None or observed[1] != self.inode or observed[0] != self.owner:
            raise LifecycleBlockedError(
                "lifecycle.lock_lost", "lock identity changed before release"
            )
        tombstone = temp_root / _tombstone_name(self.owner)
        # Rename-before-unlink prevents a releaser from removing a successor's lock.
        os.replace(lock_path, tombstone)
        renamed = tombstone.lstat()
        if renamed.st_ino != self.inode:
            raise LifecycleBlockedError("lifecycle.lock_lost", "renamed lock inode changed")
        tombstone.unlink()
        _fsync_directory(temp_root)
        self._released = True

    def __enter__(self) -> Self:
        """Return the held lock."""
        return self

    def __exit__(self, *_error: object) -> None:
        """Release the held lock without hiding release failures."""
        self.release()


def verify_owner_liveness(
    owner: OwnerIdentity,
    *,
    current_host_id: str | None = None,
    current_boot_id: str | None = None,
    process_start_probe: Callable[[int], str | None] | None = None,
) -> OwnerLiveness:
    """Verify owner identity as LIVE, DEAD, or UNKNOWN.

    A process is LIVE only when host, boot, PID and start token all match.
    A missing local PID/start pair proves DEAD. Remote, contradictory, or
    unavailable evidence stays UNKNOWN.
    """
    host_id = current_host_id or _current_host_id()
    boot_id = current_boot_id or _current_boot_id()
    if owner.host_id != host_id or owner.boot_id != boot_id:
        return OwnerLiveness.UNKNOWN
    probe = process_start_probe or _process_start_token
    try:
        observed_token = probe(owner.pid)
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return OwnerLiveness.UNKNOWN
    if observed_token is None:
        return OwnerLiveness.DEAD
    if observed_token == owner.process_start_token:
        return OwnerLiveness.LIVE
    return OwnerLiveness.DEAD


def capture_owner_identity() -> OwnerIdentity:
    """Capture the current process identity for a new manifest or lock."""
    token = _process_start_token(os.getpid())
    if token is None:
        raise LifecycleBlockedError("owner.liveness_unknown", "process start token unavailable")
    return OwnerIdentity(
        pid=os.getpid(),
        process_start_token=token,
        host_id=_current_host_id(),
        boot_id=_current_boot_id(),
        verification=OwnerLiveness.LIVE,
    )


def _write_all(descriptor: int, data: bytes) -> None:
    offset = 0
    while offset < len(data):
        written = os.write(descriptor, data[offset:])
        if written <= 0:
            raise OSError("short write")
        offset += written


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _current_host_id() -> str:
    return socket.gethostname()


def _current_boot_id() -> str:
    linux_boot = Path("/proc/sys/kernel/random/boot_id")
    if linux_boot.is_file():
        return linux_boot.read_text(encoding="ascii").strip()
    # macOS exposes one stable boot timestamp; exit/output failures remain UNKNOWN.
    result = subprocess.run(
        ["sysctl", "-n", "kern.boottime"],
        capture_output=True,
        text=True,
        check=False,
        timeout=2,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise LifecycleBlockedError("owner.liveness_unknown", "boot identity unavailable")
    return result.stdout.strip()


def _process_start_token(pid: int) -> str | None:
    linux_stat = Path(f"/proc/{pid}/stat")
    if linux_stat.is_file():
        fields = linux_stat.read_text(encoding="ascii").split()
        return fields[21] if len(fields) > 21 else None
    # `lstart` disambiguates PID reuse on macOS and returns empty for absent PIDs.
    result = subprocess.run(
        ["ps", "-o", "lstart=", "-p", str(pid)],
        capture_output=True,
        text=True,
        check=False,
        timeout=2,
    )
    if result.returncode not in {0, 1}:
        raise RuntimeError("process table unavailable")
    return result.stdout.strip() or None


def _try_create_lock(temp_root: Path, owner: OwnerIdentity, operation: str) -> int | None:
    lock_path = temp_root / LOCK_NAME
    payload = {**owner.to_dict(), "operation": operation}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    try:
        descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return None
    try:
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
        inode = os.fstat(descriptor).st_ino
    finally:
        os.close(descriptor)
    _fsync_directory(temp_root)
    return inode


def _read_lock(path: Path) -> tuple[OwnerIdentity, int] | None:
    try:
        before = path.lstat()
        raw = path.read_bytes()
        after = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(before.st_mode) or before.st_ino != after.st_ino:
        raise LifecycleBlockedError("lifecycle.lock_invalid", "lock identity changed while read")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        raise LifecycleBlockedError("lifecycle.lock_invalid", "lock JSON is invalid") from error
    if not isinstance(value, Mapping):
        raise LifecycleBlockedError("lifecycle.lock_invalid", "lock must be an object")
    owner_value = {key: value.get(key) for key in OwnerIdentity.__dataclass_fields__}
    return OwnerIdentity.from_dict(owner_value), before.st_ino


def _tombstone_name(owner: OwnerIdentity) -> str:
    return f"{LOCK_NAME}.{owner.host_id}.{owner.pid}.{owner.process_start_token}.tombstone"


def _reclaim_dead_lock(temp_root: Path, observed: tuple[OwnerIdentity, int]) -> None:
    owner, inode = observed
    lock_path = temp_root / LOCK_NAME
    if lock_path.lstat().st_ino != inode:
        return
    tombstone = temp_root / _tombstone_name(owner)
    if tombstone.exists() or tombstone.is_symlink():
        raise LifecycleBlockedError(
            "temp.orphan_lock_tombstone", "dead-owner tombstone already exists"
        )
    try:
        os.rename(lock_path, tombstone)
    except FileNotFoundError:
        return
    renamed = _read_lock(tombstone)
    if renamed is None or renamed != observed:
        raise LifecycleBlockedError(
            "temp.orphan_lock_tombstone", "renamed dead lock identity is ambiguous"
        )
    tombstone.unlink()
    _fsync_directory(temp_root)
