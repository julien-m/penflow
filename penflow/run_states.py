# @spec FR-006 FR-007 FR-008 FR-009: Feature 074 managed-run lifecycle.
"""Managed-run lifecycle responsibility module."""

from __future__ import annotations

from enum import StrEnum


class OwnerLiveness(StrEnum):
    """Tri-state process identity verification result."""

    LIVE = "LIVE"
    DEAD = "DEAD"
    UNKNOWN = "UNKNOWN"


class ProducerState(StrEnum):
    """Producer half of the managed-run state machine."""

    PREPARING = "preparing"
    ACTIVE = "active"
    FINALIZING = "finalizing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CleanupState(StrEnum):
    """Cleanup half of the managed-run state machine."""

    NOT_ELIGIBLE = "not_eligible"
    ELIGIBLE = "eligible"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CLEANUP_FAILED = "cleanup_failed"


class EntryKind(StrEnum):
    """Filesystem kinds authorized by a manifest."""

    FILE = "regular_file"
    DIRECTORY = "directory"


class CleanupStatus(StrEnum):
    """Per-entry cleanup outcome."""

    PENDING = "pending"
    DELETED = "deleted"
    PRESERVED = "preserved"
    BLOCKED = "blocked"
    ERROR = "error"


class LifecyclePhase(StrEnum):
    """Caller phase recorded by a compact receipt."""

    PREFLIGHT = "preflight"
    POSTFLIGHT = "postflight"


class LifecycleBlockedError(RuntimeError):
    """Raised when lifecycle safety cannot be proven."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
