# @spec(AC-005)
# @spec(AC-006)
# @spec(FR-004)
# @spec(FR-005)
"""Pure validation and selection for top-level Pencil canvas revisions."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .context import Context

_IDENTITY_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_LIFECYCLE_FIELDS = frozenset({"schema_version", "state", "logical_screen_id", "revision_id"})
_STATE_VALUES = frozenset({"active", "draft", "archive"})


class CanvasState(str, Enum):
    """Supported lifecycle states for one top-level canvas region."""

    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVE = "archive"


@dataclass(frozen=True, slots=True)
class CanvasFinding:
    """Stable validation finding for one canvas lifecycle violation."""

    code: str
    message: str
    source_index: int | None = None
    node_id: str | None = None
    logical_screen_id: str | None = None
    severity: str = "error"

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic scriptable representation."""
        values: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }
        if self.source_index is not None:
            values["source_index"] = self.source_index
        if self.node_id is not None:
            values["node_id"] = self.node_id
        if self.logical_screen_id is not None:
            values["logical_screen_id"] = self.logical_screen_id
        return values


@dataclass(frozen=True, slots=True)
class CanvasRegion:
    """Validated direct top-level frame and its derived lifecycle identity."""

    source_index: int
    node_id: str
    semantic_id: str | None
    logical_screen_id: str
    revision_id: str
    state: CanvasState
    raw_node: Mapping[str, Any]
    is_legacy: bool


@dataclass(frozen=True, slots=True)
class CanvasLifecycleResult:
    """Complete immutable result of one lifecycle validation pass."""

    regions: tuple[CanvasRegion, ...]
    findings: tuple[CanvasFinding, ...]

    @property
    def active_regions(self) -> tuple[CanvasRegion, ...]:
        """Return active regions in their original document order."""
        return tuple(region for region in self.regions if region.state is CanvasState.ACTIVE)

    @property
    def is_valid(self) -> bool:
        """Return whether publication is allowed."""
        return not self.findings


class CanvasLifecycleError(ValueError):
    """Raised when invalid lifecycle data prevents downstream publication."""

    def __init__(self, findings: tuple[CanvasFinding, ...]) -> None:
        self.findings = findings
        summary = ", ".join(
            f"{finding.code}"
            + (f" ({finding.logical_screen_id})" if finding.logical_screen_id is not None else "")
            for finding in findings
        )
        super().__init__(f"canvas lifecycle validation failed: {summary}")


def validate_canvas_lifecycle(document: Mapping[str, Any]) -> CanvasLifecycleResult:
    """Validate every direct top-level canvas region without mutating input.

    Args:
        document: Parsed `.pen` JSON object.

    Returns:
        Ordered validated regions and stable findings. Cardinality findings are
        appended in first-seen logical-screen order.
    """
    raw_children = document.get("children")
    if not isinstance(raw_children, list):
        finding = CanvasFinding(
            "canvas.top_level_invalid",
            "document children must be an array",
        )
        return CanvasLifecycleResult((), (finding,))
    if not raw_children:
        finding = CanvasFinding("canvas.empty", "canvas must contain at least one region")
        return CanvasLifecycleResult((), (finding,))

    regions, findings = _collect_regions(raw_children)
    findings.extend(_active_cardinality_findings(regions))
    return CanvasLifecycleResult(tuple(regions), tuple(findings))


def _collect_regions(
    raw_children: list[Any],
) -> tuple[list[CanvasRegion], list[CanvasFinding]]:
    """Parse top-level frames and record uniqueness findings in source order."""
    regions: list[CanvasRegion] = []
    findings: list[CanvasFinding] = []
    seen_node_ids: dict[str, int] = {}
    seen_revision_ids: dict[str, int] = {}
    for source_index, raw_child in enumerate(raw_children):
        node_id, child_findings = _validate_top_level_frame(raw_child, source_index)
        findings.extend(child_findings)
        if node_id is None or not isinstance(raw_child, Mapping):
            continue
        _record_duplicate_node(node_id, source_index, seen_node_ids, findings)
        region, region_findings = _parse_region(raw_child, source_index, node_id)
        findings.extend(region_findings)
        if region is None:
            continue
        _record_duplicate_revision(region, seen_revision_ids, findings)
        regions.append(region)
    return regions, findings


def _validate_top_level_frame(
    raw_child: Any, source_index: int
) -> tuple[str | None, tuple[CanvasFinding, ...]]:
    if not isinstance(raw_child, Mapping):
        return None, (
            CanvasFinding(
                "canvas.top_level_invalid",
                "top-level child must be an object",
                source_index=source_index,
            ),
        )
    node_id = _optional_nonempty_string(raw_child.get("id"))
    if raw_child.get("type") != "frame":
        return None, (
            CanvasFinding(
                "canvas.top_level_non_region",
                "top-level child must have type frame",
                source_index=source_index,
                node_id=node_id,
            ),
        )
    if node_id is None:
        return None, (
            CanvasFinding(
                "canvas.node_id_missing",
                "top-level frame requires a non-empty string id",
                source_index=source_index,
            ),
        )
    return node_id, ()


def _record_duplicate_node(
    node_id: str,
    source_index: int,
    seen: dict[str, int],
    findings: list[CanvasFinding],
) -> None:
    previous = seen.setdefault(node_id, source_index)
    if previous != source_index:
        findings.append(
            CanvasFinding(
                "canvas.node_id_duplicate",
                f"node id also used at top-level index {previous}",
                source_index=source_index,
                node_id=node_id,
            )
        )


def _record_duplicate_revision(
    region: CanvasRegion,
    seen: dict[str, int],
    findings: list[CanvasFinding],
) -> None:
    previous = seen.setdefault(region.revision_id, region.source_index)
    if previous != region.source_index:
        findings.append(
            CanvasFinding(
                "canvas.revision_id_duplicate",
                f"revision id also used at top-level index {previous}",
                source_index=region.source_index,
                node_id=region.node_id,
                logical_screen_id=region.logical_screen_id,
            )
        )


def select_active_canvas_regions(document: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Return valid active top-level frames in source order.

    Args:
        document: Parsed `.pen` JSON object.

    Returns:
        References to active region objects, without copying or mutating them.

    Raises:
        CanvasLifecycleError: If any lifecycle invariant is invalid.
    """
    return tuple(region.raw_node for region in select_active_canvas_region_entries(document))


def select_active_canvas_region_entries(
    document: Mapping[str, Any],
) -> tuple[CanvasRegion, ...]:
    """Return valid active regions with their physical top-level indices.

    Args:
        document: Parsed Pencil document.

    Returns:
        Active lifecycle records in document order. ``source_index`` always
        refers to the physical ``children`` array, even when inactive regions
        appear before an active region.

    Raises:
        CanvasLifecycleError: If any lifecycle invariant is invalid.
    """
    result = validate_canvas_lifecycle(document)
    if result.findings:
        raise CanvasLifecycleError(result.findings)
    return result.active_regions


def _parse_region(
    raw_node: Mapping[str, Any], source_index: int, node_id: str
) -> tuple[CanvasRegion | None, tuple[CanvasFinding, ...]]:
    context = Context.from_raw(raw_node.get("context"))
    semantic_id = context.semantic_id
    raw_penflow = raw_node.get("penflow")
    if raw_penflow is None or (isinstance(raw_penflow, Mapping) and "lifecycle" not in raw_penflow):
        # Backward compatibility: pre-074 top-level frames carry no lifecycle
        # object, so their established semantic/node identities remain active.
        return _legacy_region(raw_node, source_index, node_id, semantic_id)
    if not isinstance(raw_penflow, Mapping):
        finding = CanvasFinding(
            "canvas.lifecycle_invalid",
            "penflow metadata must be an object",
            source_index,
            node_id,
        )
        return None, (finding,)
    raw_lifecycle = raw_penflow.get("lifecycle")
    if not isinstance(raw_lifecycle, Mapping):
        finding = CanvasFinding(
            "canvas.lifecycle_invalid",
            "penflow.lifecycle must be an object",
            source_index,
            node_id,
        )
        return None, (finding,)
    return _marked_region(raw_node, raw_lifecycle, source_index, node_id, semantic_id)


def _legacy_region(
    raw_node: Mapping[str, Any],
    source_index: int,
    node_id: str,
    semantic_id: str | None,
) -> tuple[CanvasRegion | None, tuple[CanvasFinding, ...]]:
    logical_screen_id = semantic_id or node_id
    # Backward compatibility includes historical Pencil node IDs outside the
    # new marked-ID grammar; only explicitly marked v1 identities are strict.
    return (
        CanvasRegion(
            source_index,
            node_id,
            semantic_id,
            logical_screen_id,
            node_id,
            CanvasState.ACTIVE,
            raw_node,
            True,
        ),
        (),
    )


def _marked_region(
    raw_node: Mapping[str, Any],
    raw_lifecycle: Mapping[str, Any],
    source_index: int,
    node_id: str,
    semantic_id: str | None,
) -> tuple[CanvasRegion | None, tuple[CanvasFinding, ...]]:
    findings, state = _validate_marked_metadata(raw_lifecycle, source_index, node_id)
    logical_screen_id = _validated_identity(
        raw_lifecycle.get("logical_screen_id"),
        "logical_screen_id",
        source_index,
        node_id,
        findings,
    )
    revision_id = _validated_identity(
        raw_lifecycle.get("revision_id"),
        "revision_id",
        source_index,
        node_id,
        findings,
    )
    if findings or state is None or logical_screen_id is None or revision_id is None:
        return None, tuple(findings)
    return (
        CanvasRegion(
            source_index,
            node_id,
            semantic_id,
            logical_screen_id,
            revision_id,
            state,
            raw_node,
            False,
        ),
        (),
    )


def _validate_marked_metadata(
    raw_lifecycle: Mapping[str, Any], source_index: int, node_id: str
) -> tuple[list[CanvasFinding], CanvasState | None]:
    """Validate closed schema and state before identity parsing."""
    findings: list[CanvasFinding] = []
    unknown_fields = sorted(set(raw_lifecycle) - _LIFECYCLE_FIELDS)
    if unknown_fields:
        findings.append(
            CanvasFinding(
                "canvas.lifecycle_invalid",
                f"penflow.lifecycle has unknown fields: {', '.join(unknown_fields)}",
                source_index,
                node_id,
            )
        )
    schema_version = raw_lifecycle.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != 1
    ):
        findings.append(
            CanvasFinding(
                "canvas.lifecycle_schema_unsupported",
                "penflow.lifecycle.schema_version must be exactly 1",
                source_index,
                node_id,
            )
        )
    raw_state = raw_lifecycle.get("state")
    state = (
        CanvasState(raw_state)
        if isinstance(raw_state, str) and raw_state in _STATE_VALUES
        else None
    )
    if state is None:
        findings.append(
            CanvasFinding(
                "canvas.lifecycle_state_invalid",
                "penflow.lifecycle.state must be active, draft, or archive",
                source_index,
                node_id,
            )
        )
    return findings, state


def _validated_identity(
    value: Any,
    field: str,
    source_index: int,
    node_id: str,
    findings: list[CanvasFinding],
) -> str | None:
    parsed = _optional_nonempty_string(value)
    if parsed is None:
        findings.append(
            CanvasFinding(
                f"canvas.{field}_missing",
                f"penflow.lifecycle.{field} must be a non-empty string",
                source_index,
                node_id,
            )
        )
        return None
    if not _IDENTITY_PATTERN.fullmatch(parsed):
        findings.append(
            CanvasFinding(
                f"canvas.{field}_invalid",
                f"penflow.lifecycle.{field} does not match lifecycle identity grammar",
                source_index,
                node_id,
                parsed if field == "logical_screen_id" else None,
            )
        )
        return None
    return parsed


def _active_cardinality_findings(regions: list[CanvasRegion]) -> list[CanvasFinding]:
    grouped: dict[str, list[CanvasRegion]] = {}
    for region in regions:
        grouped.setdefault(region.logical_screen_id, []).append(region)
    findings: list[CanvasFinding] = []
    for logical_screen_id, revisions in grouped.items():
        active = [region for region in revisions if region.state is CanvasState.ACTIVE]
        if not active:
            findings.append(
                CanvasFinding(
                    "canvas.active_missing",
                    "logical screen requires exactly one active revision",
                    source_index=revisions[0].source_index,
                    node_id=revisions[0].node_id,
                    logical_screen_id=logical_screen_id,
                )
            )
        elif len(active) > 1:
            findings.append(
                CanvasFinding(
                    "canvas.active_multiple",
                    f"logical screen has {len(active)} active revisions",
                    source_index=active[1].source_index,
                    node_id=active[1].node_id,
                    logical_screen_id=logical_screen_id,
                )
            )
    return findings


def _optional_nonempty_string(value: Any) -> str | None:
    return value if isinstance(value, str) and bool(value) else None
