# @spec FR-017: No-follow consumer adapter — .specs/features/076-exhaustive-bidirectional-semantic-context/spec.md#fr-017
"""Instrumented no-follow filesystem reads for external consumer proofs."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

MUTATION_OPERATIONS = (
    "create",
    "write",
    "truncate",
    "delete",
    "rename",
    "chmod",
    "chown",
    "link",
    "symlink",
    "timestamp",
    "xattr",
    "write_and_restore",
)


class ReadOnlyConsumerError(RuntimeError):
    """Raised when consumer evidence cannot be safely published."""


class ReadOnlyConsumerFilesystem:
    """Own every consumer read and reject every modeled mutation."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve(strict=True)
        if not self.root.is_dir():
            raise ReadOnlyConsumerError("consumer root must be a directory")
        self.attempted_mutations: list[dict[str, str]] = []

    def _absolute(self, relative: str) -> str:
        candidate = os.path.abspath(os.path.join(str(self.root), relative))
        if os.path.commonpath((str(self.root), candidate)) != str(self.root):
            raise ReadOnlyConsumerError("consumer path escapes root")
        return candidate

    def read_bytes(self, relative: str) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(self._absolute(relative), flags)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ReadOnlyConsumerError(f"consumer input is not regular: {relative}")
            chunks: list[bytes] = []
            while chunk := os.read(descriptor, 1024 * 1024):
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            os.close(descriptor)

    def read_json(self, relative: str) -> dict[str, Any]:
        try:
            value = json.loads(self.read_bytes(relative).decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReadOnlyConsumerError(f"invalid consumer JSON: {relative}") from exc
        if not isinstance(value, dict):
            raise ReadOnlyConsumerError(f"consumer JSON must be an object: {relative}")
        return value

    def manifest(self) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        pending = ["."]
        while pending:
            relative = pending.pop()
            entry = self._entry(relative)
            entries.append(entry)
            if entry["type"] == "directory":
                children = sorted(item.name for item in os.scandir(self._absolute(relative)))
                pending.extend(reversed([self._join(relative, name) for name in children]))
        entries.sort(key=lambda item: item["path"])
        return {
            "kind": "penflow-consumer-manifest",
            "version": 1,
            "entries": entries,
            "digest": _digest_json(entries),
        }

    def _entry(self, relative: str) -> dict[str, Any]:
        path = self._absolute(relative)
        metadata = os.lstat(path)
        file_type = _file_type(metadata.st_mode)
        return {
            "path": relative,
            "type": file_type,
            "mode": stat.S_IMODE(metadata.st_mode),
            "uid": metadata.st_uid,
            "gid": metadata.st_gid,
            "size": metadata.st_size,
            "mtime_ns": metadata.st_mtime_ns,
            "ctime_ns": metadata.st_ctime_ns,
            "birthtime_ns": _birthtime_ns(metadata),
            "symlink_target": os.readlink(path) if file_type == "symlink" else None,
            "xattrs": self._xattrs(path),
            "sha256": hashlib.sha256(self.read_bytes(relative)).hexdigest()
            if file_type == "regular"
            else None,
        }

    def _xattrs(self, path: str) -> list[dict[str, str]]:
        list_xattr = getattr(os, "listxattr", None)
        get_xattr = getattr(os, "getxattr", None)
        if callable(list_xattr) and callable(get_xattr):
            try:
                names = sorted(list_xattr(path, follow_symlinks=False))
                return [
                    {
                        "name": name,
                        "value_base64": base64.b64encode(
                            get_xattr(path, name, follow_symlinks=False)
                        ).decode("ascii"),
                    }
                    for name in names
                ]
            except OSError as exc:
                raise ReadOnlyConsumerError("cannot inventory xattrs") from exc

        if sys.platform != "darwin":
            raise ReadOnlyConsumerError("xattr API unavailable on this platform")
        names = sorted(name for name in self._command_xattr("-s", path).stdout.splitlines() if name)
        values: list[dict[str, str]] = []
        for name in names:
            result = self._command_xattr("-p", "-s", "-x", name, path)
            raw = bytes.fromhex("".join(result.stdout.split()))
            values.append({"name": name, "value_base64": base64.b64encode(raw).decode("ascii")})
        return values

    @staticmethod
    def _command_xattr(*arguments: str) -> subprocess.CompletedProcess[str]:
        # Some macOS Python builds omit the stdlib xattr API, so retain the native
        # no-follow command as a bounded fallback while Linux uses the stdlib path.
        try:
            return subprocess.run(
                ["/usr/bin/xattr", *arguments],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ReadOnlyConsumerError("cannot inventory xattrs") from exc

    def block_mutation(self, operation: str, relative: str) -> None:
        if operation not in MUTATION_OPERATIONS:
            raise ReadOnlyConsumerError(f"unknown mutation operation: {operation}")
        self._absolute(relative)
        self.attempted_mutations.append({"operation": operation, "path": relative})
        raise ReadOnlyConsumerError(f"consumer mutation blocked: {operation}")

    @staticmethod
    def _join(parent: str, child: str) -> str:
        return child if parent == "." else f"{parent}/{child}"


def _file_type(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "regular"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISLNK(mode):
        return "symlink"
    return "other"


def _birthtime_ns(metadata: os.stat_result) -> int | None:
    value = getattr(metadata, "st_birthtime", None)
    return round(float(value) * 1_000_000_000) if value is not None else None


def _digest_json(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
