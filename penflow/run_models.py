# @spec FR-006 FR-007 FR-008 FR-009: Feature 074 managed-run lifecycle.
"""Managed-run lifecycle responsibility module."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Self

from .artifact_policy import MANAGED_TEMP_ROOT, PRODUCER_COMMANDS, Retention
from .run_states import (
    CleanupState,
    CleanupStatus,
    EntryKind,
    LifecycleBlockedError,
    LifecyclePhase,
    OwnerLiveness,
    ProducerState,
)

SCHEMA_VERSION = 1
MANAGED_ROOT_NAME = MANAGED_TEMP_ROOT
PRODUCER_COMMAND_IDS = PRODUCER_COMMANDS


@dataclass(frozen=True, slots=True)
class OwnerIdentity:
    """Full process identity used to avoid PID-reuse mistakes."""

    pid: int
    process_start_token: str
    host_id: str
    boot_id: str
    verification: OwnerLiveness = OwnerLiveness.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        """Return the schema-1 JSON representation."""
        return {
            "pid": self.pid,
            "process_start_token": self.process_start_token,
            "host_id": self.host_id,
            "boot_id": self.boot_id,
            "verification": self.verification.value,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        """Validate and parse an owner identity from external JSON."""
        required = {"pid", "process_start_token", "host_id", "boot_id", "verification"}
        _require_exact_keys(value, required, "owner")
        return cls(
            pid=_positive_int(value["pid"], "owner.pid"),
            process_start_token=_validated_owner_component(
                value["process_start_token"], "owner.process_start_token"
            ),
            host_id=_validated_owner_component(value["host_id"], "owner.host_id"),
            boot_id=_validated_owner_component(value["boot_id"], "owner.boot_id"),
            verification=_enum(OwnerLiveness, value["verification"], "owner.verification"),
        )


@dataclass(frozen=True, slots=True)
class ManifestPathEntry:
    """One individually catalogued filesystem object."""

    relative_path: str
    kind: EntryKind
    device: int
    inode: int
    mode: int
    link_count: int
    logical_bytes: int
    retention: Retention
    references: tuple[str, ...] = ()
    cleanup_status: CleanupStatus = CleanupStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        """Return the schema-1 JSON representation."""
        return {
            "relative_path": self.relative_path,
            "kind": self.kind.value,
            "device": self.device,
            "inode": self.inode,
            "mode": self.mode,
            "link_count": self.link_count,
            "logical_bytes": self.logical_bytes,
            "retention": self.retention.value,
            "references": list(self.references),
            "cleanup_status": self.cleanup_status.value,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        """Validate and parse one manifest path entry."""
        required = {
            "relative_path",
            "kind",
            "device",
            "inode",
            "mode",
            "link_count",
            "logical_bytes",
            "retention",
            "references",
            "cleanup_status",
        }
        _require_exact_keys(value, required, "entry")
        references = value["references"]
        if not isinstance(references, list) or not all(
            isinstance(reference, str) and reference for reference in references
        ):
            raise LifecycleBlockedError("manifest.invalid", "entry.references must be strings")
        return cls(
            relative_path=_validated_relative_path(value["relative_path"]),
            kind=_enum(EntryKind, value["kind"], "entry.kind"),
            device=_nonnegative_int(value["device"], "entry.device"),
            inode=_nonnegative_int(value["inode"], "entry.inode"),
            mode=_nonnegative_int(value["mode"], "entry.mode"),
            link_count=_nonnegative_int(value["link_count"], "entry.link_count"),
            logical_bytes=_nonnegative_int(value["logical_bytes"], "entry.logical_bytes"),
            retention=_enum(Retention, value["retention"], "entry.retention"),
            references=tuple(references),
            cleanup_status=_enum(CleanupStatus, value["cleanup_status"], "entry.cleanup_status"),
        )


@dataclass(frozen=True, slots=True)
class DurableOutput:
    """One durable output finalized before successful cleanup."""

    relative_path: str
    sha256: str
    finalized: bool
    manifest_revision: int

    def to_dict(self) -> dict[str, Any]:
        """Return the schema-1 JSON representation."""
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "finalized": self.finalized,
            "manifest_revision": self.manifest_revision,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        """Validate and parse a durable output."""
        required = {"relative_path", "sha256", "finalized", "manifest_revision"}
        _require_exact_keys(value, required, "durable_output")
        digest = _nonempty_str(value["sha256"], "durable_output.sha256")
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise LifecycleBlockedError("manifest.invalid", "durable output sha256 is invalid")
        if not isinstance(value["finalized"], bool):
            raise LifecycleBlockedError("manifest.invalid", "durable output finalized is invalid")
        return cls(
            relative_path=_validated_relative_path(value["relative_path"]),
            sha256=digest,
            finalized=value["finalized"],
            manifest_revision=_positive_int(
                value["manifest_revision"], "durable_output.manifest_revision"
            ),
        )


@dataclass(frozen=True, slots=True)
class CleanupReceiptSummary:
    """Compact manifest pointer to the latest cleanup attempt."""

    phase: LifecyclePhase
    reclaimed_bytes: int
    preserved_bytes: int
    blocked_bytes: int

    def to_dict(self) -> dict[str, Any]:
        """Return the schema-1 JSON representation."""
        return {
            "phase": self.phase.value,
            "reclaimed_bytes": self.reclaimed_bytes,
            "preserved_bytes": self.preserved_bytes,
            "blocked_bytes": self.blocked_bytes,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        """Validate and parse a compact cleanup summary."""
        required = {"phase", "reclaimed_bytes", "preserved_bytes", "blocked_bytes"}
        _require_exact_keys(value, required, "last_cleanup_receipt")
        return cls(
            phase=_enum(LifecyclePhase, value["phase"], "last_cleanup_receipt.phase"),
            reclaimed_bytes=_nonnegative_int(
                value["reclaimed_bytes"], "last_cleanup_receipt.reclaimed_bytes"
            ),
            preserved_bytes=_nonnegative_int(
                value["preserved_bytes"], "last_cleanup_receipt.preserved_bytes"
            ),
            blocked_bytes=_nonnegative_int(
                value["blocked_bytes"], "last_cleanup_receipt.blocked_bytes"
            ),
        )


@dataclass(frozen=True, slots=True)
class ManagedRunManifest:
    """Versioned ownership and retention record for one producer run."""

    schema_version: int
    revision: int
    run_id: str
    command: str
    producer_state: ProducerState
    cleanup_state: CleanupState
    created_at: str
    updated_at: str
    owner: OwnerIdentity
    entries: tuple[ManifestPathEntry, ...] = ()
    durable_outputs: tuple[DurableOutput, ...] = ()
    last_cleanup_receipt: CleanupReceiptSummary | None = None
    blocking_findings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Return the complete schema-1 JSON representation."""
        return {
            "schema_version": self.schema_version,
            "revision": self.revision,
            "run_id": self.run_id,
            "command": self.command,
            "producer_state": self.producer_state.value,
            "cleanup_state": self.cleanup_state.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "owner": self.owner.to_dict(),
            "entries": [entry.to_dict() for entry in self.entries],
            "durable_outputs": [output.to_dict() for output in self.durable_outputs],
            "last_cleanup_receipt": (
                self.last_cleanup_receipt.to_dict() if self.last_cleanup_receipt else None
            ),
            "blocking_findings": list(self.blocking_findings),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> Self:
        """Validate external JSON and construct a schema-1 manifest."""
        required = {
            "schema_version",
            "revision",
            "run_id",
            "command",
            "producer_state",
            "cleanup_state",
            "created_at",
            "updated_at",
            "owner",
            "entries",
            "durable_outputs",
            "last_cleanup_receipt",
            "blocking_findings",
        }
        _require_exact_keys(value, required, "manifest")
        if value["schema_version"] != SCHEMA_VERSION:
            raise LifecycleBlockedError("manifest.schema_unsupported", "schema_version must be 1")
        command = _nonempty_str(value["command"], "manifest.command")
        if command not in PRODUCER_COMMAND_IDS:
            raise LifecycleBlockedError("manifest.command_unknown", f"unknown producer {command}")
        entries = _mapping_list(value["entries"], "manifest.entries")
        outputs = _mapping_list(value["durable_outputs"], "manifest.durable_outputs")
        findings = value["blocking_findings"]
        if not isinstance(findings, list) or not all(isinstance(code, str) for code in findings):
            raise LifecycleBlockedError("manifest.invalid", "blocking_findings must be strings")
        owner = value["owner"]
        if not isinstance(owner, Mapping):
            raise LifecycleBlockedError("manifest.invalid", "owner must be an object")
        summary = value["last_cleanup_receipt"]
        if summary is not None and not isinstance(summary, Mapping):
            raise LifecycleBlockedError("manifest.invalid", "last cleanup receipt is invalid")
        manifest = cls(
            schema_version=SCHEMA_VERSION,
            revision=_positive_int(value["revision"], "manifest.revision"),
            run_id=_validated_run_id(value["run_id"]),
            command=command,
            producer_state=_enum(ProducerState, value["producer_state"], "manifest.producer_state"),
            cleanup_state=_enum(CleanupState, value["cleanup_state"], "manifest.cleanup_state"),
            created_at=_nonempty_str(value["created_at"], "manifest.created_at"),
            updated_at=_nonempty_str(value["updated_at"], "manifest.updated_at"),
            owner=OwnerIdentity.from_dict(owner),
            entries=tuple(ManifestPathEntry.from_dict(entry) for entry in entries),
            durable_outputs=tuple(DurableOutput.from_dict(output) for output in outputs),
            last_cleanup_receipt=(
                CleanupReceiptSummary.from_dict(summary) if isinstance(summary, Mapping) else None
            ),
            blocking_findings=tuple(findings),
        )
        _validate_manifest_invariants(manifest)
        return manifest


def _validate_transition(
    current: Any,
    requested: Any,
    transitions: Mapping[Any, frozenset[Any]],
    label: str,
) -> None:
    if requested == current:
        return
    if requested not in transitions[current]:
        raise LifecycleBlockedError(
            "manifest.transition_invalid",
            f"invalid {label} transition {current.value} -> {requested.value}",
        )


def _validate_manifest_invariants(manifest: ManagedRunManifest) -> None:
    if manifest.schema_version != SCHEMA_VERSION:
        raise LifecycleBlockedError("manifest.schema_unsupported", "schema_version must be 1")
    _validated_run_id(manifest.run_id)
    paths = [entry.relative_path for entry in manifest.entries]
    if paths != sorted(paths) or len(paths) != len(set(paths)):
        raise LifecycleBlockedError(
            "manifest.entry_duplicate", "manifest paths must be unique and sorted"
        )
    run_prefix = f"{MANAGED_ROOT_NAME}/runs/{manifest.run_id}"
    if any(path != run_prefix and not path.startswith(f"{run_prefix}/") for path in paths):
        raise LifecycleBlockedError(
            "manifest.identity_mismatch", "manifest entry belongs to another run"
        )
    if manifest.producer_state is ProducerState.SUCCEEDED:
        if not all(output.finalized for output in manifest.durable_outputs):
            raise LifecycleBlockedError(
                "manifest.output_unfinalized", "succeeded run has unfinalized output"
            )


def _require_exact_keys(value: Mapping[str, Any], required: set[str], label: str) -> None:
    if set(value) != required:
        raise LifecycleBlockedError(
            "manifest.invalid",
            f"{label} keys differ: missing={sorted(required - set(value))}, "
            f"unknown={sorted(set(value) - required)}",
        )


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise LifecycleBlockedError("manifest.invalid", f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise LifecycleBlockedError("manifest.invalid", f"{label} must be a nonnegative integer")
    return value


def _nonempty_str(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise LifecycleBlockedError("manifest.invalid", f"{label} must be a non-empty string")
    return value


def _validated_owner_component(value: Any, label: str) -> str:
    component = _nonempty_str(value, label)
    if component in {".", ".."} or any(character in component for character in "/\\\x00"):
        raise LifecycleBlockedError("manifest.invalid", f"{label} is not path-safe")
    return component


def _enum(enum_type: type[Any], value: Any, label: str) -> Any:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise LifecycleBlockedError("manifest.invalid", f"{label} has an unknown value") from error


def _mapping_list(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise LifecycleBlockedError("manifest.invalid", f"{label} must contain objects")
    return value


def _validated_run_id(value: Any) -> str:
    run_id = _nonempty_str(value, "run_id")
    if run_id in {".", ".."} or "/" in run_id or "\\" in run_id or run_id.startswith("."):
        raise LifecycleBlockedError("manifest.run_id_invalid", "run_id is not a path-safe name")
    return run_id


def _validated_relative_path(value: Any) -> str:
    path = _nonempty_str(value, "entry.relative_path")
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts or pure.as_posix() != path:
        raise LifecycleBlockedError("cleanup.path_escape", f"invalid relative path {path!r}")
    if not path.startswith(f"{MANAGED_ROOT_NAME}/runs/"):
        raise LifecycleBlockedError("cleanup.path_escape", "entry is outside managed runs")
    return path
