# @spec FR-006 FR-007 FR-008 FR-009: Feature 074 managed-run lifecycle.
"""Managed-run lifecycle responsibility module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .run_models import ManagedRunManifest, ManifestPathEntry
from .run_states import CleanupState, LifecyclePhase


@dataclass(frozen=True, slots=True, order=True)
class LifecycleFinding:
    """Stable coded lifecycle decision."""

    code: str
    relative_path: str
    message: str
    logical_bytes: int = 0


@dataclass(frozen=True, slots=True)
class CleanupItem:
    """One deterministic cleanup outcome row."""

    relative_path: str
    logical_bytes: int
    code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the receipt JSON representation."""
        return {
            "relative_path": self.relative_path,
            "logical_bytes": self.logical_bytes,
            "code": self.code,
        }


@dataclass(frozen=True, slots=True)
class CleanupPlan:
    """Run-wide all-or-nothing eligibility snapshot."""

    run_id: str
    eligible: bool
    ordered_entries: tuple[ManifestPathEntry, ...]
    preserved_entries: tuple[ManifestPathEntry, ...]
    blocking_findings: tuple[LifecycleFinding, ...]
    index_digest: str
    porcelain_v2: bytes


@dataclass(frozen=True, slots=True)
class CleanupReceipt:
    """Observable result of one cleanup attempt."""

    schema_version: int
    run_id: str
    phase: LifecyclePhase
    cleanup_state: CleanupState
    deleted: tuple[CleanupItem, ...]
    preserved: tuple[CleanupItem, ...]
    blocked: tuple[CleanupItem, ...]
    errors: tuple[LifecycleFinding, ...]
    reclaimed_bytes: int
    preserved_bytes: int
    blocked_bytes: int
    manifest: ManagedRunManifest = field(repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        """Return the schema-1 compact receipt representation."""
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "phase": self.phase.value,
            "cleanup_state": self.cleanup_state.value,
            "deleted": [item.to_dict() for item in self.deleted],
            "preserved": [item.to_dict() for item in self.preserved],
            "blocked": [item.to_dict() for item in self.blocked],
            "errors": [
                {
                    "code": finding.code,
                    "path": finding.relative_path,
                    "message": finding.message,
                }
                for finding in self.errors
            ],
            "reclaimed_bytes": self.reclaimed_bytes,
            "preserved_bytes": self.preserved_bytes,
            "blocked_bytes": self.blocked_bytes,
        }
