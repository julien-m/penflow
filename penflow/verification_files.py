# @spec FR-014: Reuse immutable schema validators and per-run reads/hashes without mutable persistent caches, while rechecking changes before publication. — .specs/features/077-complete-verification-workflow/spec.md#fr-014
"""Bounded reads and a final byte recheck for mutable verification inputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .verification_json import decode_json, digest
from .verification_schema import schema_issues


class VerificationInputError(ValueError):
    """An input is absent, foreign, stale or invalid at its authoritative boundary."""


class InputReader:
    """Read caller-contained inputs and retain observed hashes for one verification."""

    def __init__(self, project_root: Path) -> None:
        self.root = project_root.resolve(strict=True)
        self.observed: dict[Path, str] = {}
        self.resolutions: dict[Path, Path] = {}
        self.presence: dict[Path, bool] = {}
        self.lexical_presence: dict[Path, bool] = {}
        self.read_log: list[Path] = []
        self.directories: dict[tuple[Path, str], tuple[str, ...]] = {}

    def path(self, path: str | Path) -> Path:
        """Resolve exactly one path inside the independently supplied project."""
        candidate = Path(path)
        requested = candidate if candidate.is_absolute() else self.root / candidate
        resolved = requested.resolve()
        if not resolved.is_relative_to(self.root):
            raise VerificationInputError(f"input.outside_project: {path}")
        if ".git" in resolved.relative_to(self.root).parts:
            raise VerificationInputError(f"input.git_metadata: {path}")
        if self.resolutions.setdefault(requested, resolved) != resolved:
            raise VerificationInputError(f"input.retargeted: {path}")
        return resolved

    def read(self, path: str | Path) -> bytes:
        """Read current bytes, rejecting inputs that change during a single run."""
        resolved = self.path(path)
        self.read_log.append(resolved)
        raw = resolved.read_bytes()
        sha = digest(raw)
        previous = self.observed.setdefault(resolved, sha)
        if previous != sha:
            raise VerificationInputError(f"input.changed: {path}")
        return raw

    def exists(self, path: str | Path) -> bool:
        """Observe optional source presence without allowing a later applicability race."""
        resolved = self.path(path)
        present = resolved.exists()
        if self.presence.setdefault(resolved, present) != present:
            raise VerificationInputError(f"input.presence_changed: {path}")
        return present

    def lexists(self, path: str | Path) -> bool:
        """Retain lexical authority presence, including broken symlinks that must fail."""
        candidate = Path(path)
        requested = candidate if candidate.is_absolute() else self.root / candidate
        self.path(requested)
        present = requested.exists() or requested.is_symlink()
        if self.lexical_presence.setdefault(requested, present) != present:
            raise VerificationInputError(f"input.presence_changed: {path}")
        return present

    def reference(self, reference: dict[str, Any], *, archive: str | None = None) -> bytes:
        """Verify raw bytes against a source reference, optionally requiring its archive identity."""
        if schema_issues(reference, "file"):
            raise VerificationInputError("input.invalid_reference")
        if archive:
            suffix = ".md" if archive == "source" else ".json"
            expected = f".specs/penflow-approvals/{archive}-{reference['sha256']}{suffix}"
            if reference["path"] != expected:
                raise VerificationInputError("input.not_immutable_archive")
        raw = self.read(reference["path"])
        if digest(raw) != reference["sha256"]:
            raise VerificationInputError(f"input.stale: {reference['path']}")
        return raw

    def object(self, raw: bytes, definition: str | None = None) -> dict[str, Any]:
        """Decode strict JSON and validate the complete requested envelope."""
        value = decode_json(raw)
        if not isinstance(value, dict) or (definition and schema_issues(value, definition)):
            raise VerificationInputError(f"input.invalid_object: {definition}")
        return value

    def files(self, directory: str | Path, pattern: str = "*") -> list[Path]:
        """Freeze membership of one bounded artifact directory, including later additions."""
        path = self.path(directory)
        self.exists(path)
        members = self._members(path, pattern)
        if self.directories.setdefault((path, pattern), members) != members:
            raise VerificationInputError(f"input.membership_changed: {path}")
        return [self.path(path / member) for member in members]

    @staticmethod
    def _members(path: Path, pattern: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                item.relative_to(path).as_posix() for item in path.rglob(pattern) if item.is_file()
            )
        )

    def recheck(self) -> None:
        """Reject missing or changed bytes after all dependent checks finish."""
        for requested, resolved in self.resolutions.items():
            if requested.resolve() != resolved:
                raise VerificationInputError(f"input.retargeted: {requested}")
        for path, present in self.lexical_presence.items():
            if (path.exists() or path.is_symlink()) != present:
                raise VerificationInputError(f"input.presence_changed: {path}")
        for path, present in self.presence.items():
            if path.exists() != present:
                raise VerificationInputError(f"input.presence_changed: {path}")
        for path, sha in self.observed.items():
            if digest(path.read_bytes()) != sha:
                raise VerificationInputError(f"input.changed: {path}")
        for (path, pattern), members in self.directories.items():
            if self._members(path, pattern) != members:
                raise VerificationInputError(f"input.membership_changed: {path}")
