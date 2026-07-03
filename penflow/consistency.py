# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-004)
"""Deterministic cross-screen component consistency checks for expected UI trees."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

# Padding canonicalization is shared with the compare engine (feature 048)
# so compare-tree and check-consistency can never disagree on spacing forms.
from .compare import (
    _bbox_is_measurable,
    _canonical_number,
    _canonical_padding,
    _is_masked,
    _is_number,
)
from .tree import flatten_nodes, load_tree

REPORT_KIND = "penflow-consistency-report"
REPORT_VERSION = 1

DEFAULT_GROUP_BY = "role+intent+variant"
SIZE_CLASS_GROUP_BY = "role+intent+variant+size-class"
GROUP_BY_CHOICES: tuple[str, ...] = (
    "role",
    "role+intent",
    DEFAULT_GROUP_BY,
    SIZE_CLASS_GROUP_BY,
)

# Numeric deviations from the baseline within this distance downgrade to warning.
NUMERIC_TOLERANCE = 2.0

# Properties compared per signature group; "bbox.height" reads the node bbox,
# every other property reads the node "visual" dict (feature 006 expected shape).
CHECKED_PROPERTIES: tuple[str, ...] = (
    "padding",
    "gap",
    "fontSize",
    "fontWeight",
    "fontFamily",
    "fill",
    "cornerRadius",
    "bbox.height",
)

# Divergent brand colors and typefaces on the same component signature are
# always design errors regardless of numeric distance.
_ALWAYS_ERROR_PROPERTIES = frozenset({"fill", "fontFamily"})

# Bucket boundaries intentionally follow common UI block bands: controls and
# headers <=64px, compact regions <=128px, normal panels <=256px, large panels
# <=512px, and full-height regions above that. This keeps a 56px header out of
# the same group as an 820px panel without needing runtime layout execution.
SIZE_CLASS_BUCKETS: tuple[tuple[str, float], ...] = (
    ("xs", 64.0),
    ("sm", 128.0),
    ("md", 256.0),
    ("lg", 512.0),
)

MAX_MESSAGE_EXAMPLES = 3


def check_consistency(
    tree_path: str | Path, *, group_by: str | None = None, lenient: bool = False
) -> dict[str, Any]:
    # @spec FR-001: Cross-screen consistency engine — .specs/features/047-cross-screen-consistency-check/spec.md#fr-001
    # @spec FR-005: Deterministic ordering and byte-identical reruns — .specs/features/047-cross-screen-consistency-check/spec.md#fr-005
    """Check cross-screen component consistency in an expected UI tree.

    Args:
        tree_path: Path to an `expected-ui-tree.json` (feature 006 shape; any
            tree sharing that shape works, including future actual-derived
            trees).
        group_by: Component signature granularity — one of ``GROUP_BY_CHOICES``.
            ``None`` selects the full default signature
            (role + context.intent + context.variant).
        lenient: Downgrade all non-always-error property divergences to warning
            in the emitted report.

    Returns:
        A strict consistency report dictionary
        (`consistency-report.schema.json`).

    Raises:
        ValueError: If ``group_by`` is unknown or the tree is not an object
            with a ``screens`` list.
    """
    effective_group_by = group_by if group_by is not None else DEFAULT_GROUP_BY
    if effective_group_by not in GROUP_BY_CHOICES:
        raise ValueError(f"unknown group-by: {effective_group_by!r}")
    tree = load_tree(tree_path)
    if not isinstance(tree, dict) or not isinstance(tree.get("screens"), list):
        raise ValueError(f"expected tree must be an object with a screens list: {tree_path}")

    members = _collect_members(tree)
    groups = _group_by_signature(members, effective_group_by)
    issues: list[dict[str, Any]] = []
    groups_checked = 0
    for signature in sorted(groups):
        group = groups[signature]
        if len(group) < 2:
            continue
        groups_checked += 1
        for prop in CHECKED_PROPERTIES:
            issues.extend(_property_issues(signature, group, prop, lenient=lenient))
    issues.sort(key=_issue_sort_key)

    errors = sum(1 for issue in issues if issue["severity"] == "error")
    warnings = sum(1 for issue in issues if issue["severity"] == "warning")
    return {
        "version": REPORT_VERSION,
        "kind": REPORT_KIND,
        "status": "PASS" if errors == 0 else "FAIL",
        "summary": {
            "errors": errors,
            "warnings": warnings,
            "groups_checked": groups_checked,
            "nodes_checked": len(members),
        },
        "inputs": {"expected_tree": str(tree_path), "group_by": effective_group_by},
        "issues": issues,
    }


def write_consistency_report(report: dict[str, Any], out_path: str | Path) -> None:
    """Serialize a report with the byte-stable recipe shared by all artifacts.

    Args:
        report: Consistency report dictionary produced by `check_consistency`.
        out_path: Destination path, created or overwritten as UTF-8 JSON with
            sorted keys, two-space indentation, and a trailing newline.
    """
    Path(out_path).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _collect_members(tree: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Flatten every screen into `(screen_id, node)` pairs, skipping masked nodes.

    Mask semantics are shared with `compare.py` (`context.mask`, masked roles,
    volatile variants) so compare and consistency never disagree. Nodes without
    a role cannot form a component signature and are skipped.

    Raises:
        ValueError: If a screen or its root is not an object — malformed input
            must fail closed (exit 2) instead of silently passing.
    """
    members: list[tuple[str, dict[str, Any]]] = []
    for index, screen in enumerate(tree.get("screens", [])):
        if not isinstance(screen, dict):
            raise ValueError(f"screens[{index}] must be an object")
        screen_id = str(screen.get("screen_id") or screen.get("pencil_id") or screen.get("name"))
        root = screen.get("root")
        if not isinstance(root, dict):
            raise ValueError(f"screens[{index}].root must be an object")
        for node in flatten_nodes(root):
            if not node.get("role") or _is_masked(node):
                continue
            if _is_anonymous_container(node):
                continue
            members.append((screen_id, node))
    return members


def _group_by_signature(
    members: list[tuple[str, dict[str, Any]]], group_by: str
) -> dict[str, list[tuple[str, dict[str, Any]]]]:
    groups: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for screen_id, node in members:
        groups.setdefault(_signature(node, group_by), []).append((screen_id, node))
    return groups


def _signature(node: dict[str, Any], group_by: str) -> str:
    raw_context = node.get("context")
    context: dict[str, Any] = raw_context if isinstance(raw_context, dict) else {}
    parts = [f"role={node.get('role')}"]
    if group_by in ("role+intent", DEFAULT_GROUP_BY, SIZE_CLASS_GROUP_BY):
        parts.append(f"intent={_signature_part(context.get('intent'))}")
    if group_by in (DEFAULT_GROUP_BY, SIZE_CLASS_GROUP_BY):
        parts.append(f"variant={_signature_part(context.get('variant'))}")
    if group_by == SIZE_CLASS_GROUP_BY:
        parts.append(f"size={_size_class(node)}")
    return ";".join(parts)


def _signature_part(value: Any) -> str:
    return str(value) if isinstance(value, str) and value else "-"


def _property_issues(
    signature: str, group: list[tuple[str, dict[str, Any]]], prop: str, *, lenient: bool
) -> list[dict[str, Any]]:
    participants = [
        (screen_id, node, canonical)
        for screen_id, node in group
        for canonical in [_property_value(node, prop)]
        if canonical is not _ABSENT
    ]
    if len(participants) < 2:
        return []
    counts: dict[str, int] = {}
    canonical_by_key: dict[str, Any] = {}
    for _, _, canonical in participants:
        key = _canonical_key(canonical)
        counts[key] = counts.get(key, 0) + 1
        canonical_by_key[key] = canonical
    if len(counts) == 1:
        return []
    # @spec AC-005: Majority baseline with sorted-first tie-break — .specs/features/047-cross-screen-consistency-check/spec.md#acceptance-criteria
    baseline_key = min(counts, key=lambda key: (-counts[key], key))
    baseline = canonical_by_key[baseline_key]
    divergences: dict[str, list[tuple[str, dict[str, Any], Any]]] = {}
    for screen_id, node, canonical in participants:
        key = _canonical_key(canonical)
        if key == baseline_key:
            continue
        divergences.setdefault(key, []).append((screen_id, node, canonical))

    issues: list[dict[str, Any]] = []
    for key in sorted(divergences):
        divergent_nodes = sorted(divergences[key], key=_participant_sort_key)
        screen_id, node, canonical = divergent_nodes[0]
        count = len(divergent_nodes)
        examples = ", ".join(
            str(example_node.get("_semantic_key") or example_node.get("semantic_id") or "-")
            for _, example_node, _ in divergent_nodes[:MAX_MESSAGE_EXAMPLES]
        )
        issues.append(
            {
                "code": f"consistency.{prop}.divergent",
                "severity": _severity(prop, canonical, baseline, lenient=lenient),
                "property": prop,
                "signature": signature,
                "screen_id": screen_id,
                "semantic_id": node.get("_semantic_key"),
                "value": canonical,
                "baseline": baseline,
                "group_size": len(participants),
                "message": (
                    f"{count} divergence(s) of {prop} value {key} from baseline {baseline_key} "
                    f"for {signature} (group of {len(participants)}; examples: {examples})"
                ),
            }
        )
    return issues


def _participant_sort_key(participant: tuple[str, dict[str, Any], Any]) -> tuple[str, str, str]:
    screen_id, node, canonical = participant
    return (screen_id, str(node.get("_semantic_key") or ""), _canonical_key(canonical))


class _Absent:
    """Sentinel distinguishing missing properties from explicit null/zero values."""


_ABSENT = _Absent()


def _property_value(node: dict[str, Any], prop: str) -> Any:
    if prop == "bbox.height":
        bbox = node.get("bbox")
        # Same measurability rule as compare.py: unmeasurable boxes (drafted
        # pens without layout) carry no height information worth comparing.
        if isinstance(bbox, dict) and _bbox_is_measurable(bbox) and "height" in bbox:
            return _canonical_value("bbox.height", bbox["height"])
        return _ABSENT
    visual = node.get("visual")
    if isinstance(visual, dict) and prop in visual:
        return _canonical_value(prop, visual[prop])
    return _ABSENT


def _canonical_value(prop: str, value: Any) -> Any:
    if prop == "padding":
        expanded = _canonical_padding(value)
        if expanded is not None:
            return expanded
    return _schema_safe(_canonical_scalar(value))


def _schema_safe(value: Any) -> Any:
    """Clamp a canonical value to the closed report value shape.

    The strict schema only allows `number | string | array of number/string`
    for `value`/`baseline`, so booleans, nulls, objects, and nested arrays are
    serialized to their deterministic JSON text before report emission.
    """
    if _is_number(value) or isinstance(value, str):
        return value
    if isinstance(value, list):
        return [
            item if _is_number(item) or isinstance(item, str) else _canonical_key(item)
            for item in value
        ]
    return _canonical_key(value)


def _canonical_scalar(value: Any) -> Any:
    if _is_number(value):
        return _canonical_number(value)
    if isinstance(value, list):
        return [_canonical_scalar(item) for item in value]
    return value


def _canonical_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def _severity(prop: str, value: Any, baseline: Any, *, lenient: bool = False) -> str:
    # @spec FR-002: Severity model — .specs/features/047-cross-screen-consistency-check/spec.md#fr-002
    if prop in _ALWAYS_ERROR_PROPERTIES:
        return "error"
    if lenient:
        return "warning"
    deviation = _numeric_deviation(value, baseline)
    if deviation is None:
        return "error"
    return "warning" if deviation <= NUMERIC_TOLERANCE else "error"


def _is_anonymous_container(node: dict[str, Any]) -> bool:
    if node.get("role") != "container":
        return False
    raw_context = node.get("context")
    context: dict[str, Any] = raw_context if isinstance(raw_context, dict) else {}
    return not any(
        _non_empty_string(value)
        for value in (
            context.get("intent"),
            context.get("variant"),
            node.get("name"),
            node.get("label"),
            node.get("text"),
            context.get("name"),
            context.get("label"),
        )
    )


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _size_class(node: dict[str, Any]) -> str:
    bbox = node.get("bbox")
    if not isinstance(bbox, dict) or not _bbox_is_measurable(bbox):
        return "unmeasured"
    height = bbox.get("height")
    if not _is_number(height):
        return "unmeasured"
    value = float(cast(int | float, height))
    for label, upper_bound in SIZE_CLASS_BUCKETS:
        if value <= upper_bound:
            return label
    return "xl"


def _numeric_deviation(value: Any, baseline: Any) -> float | None:
    if _is_number(value) and _is_number(baseline):
        return abs(float(value) - float(baseline))
    if (
        isinstance(value, list)
        and isinstance(baseline, list)
        and len(value) == len(baseline)
        and all(_is_number(item) for item in value)
        and all(_is_number(item) for item in baseline)
    ):
        return max(
            (abs(float(left) - float(right)) for left, right in zip(value, baseline)),
            default=0.0,
        )
    return None


def _issue_sort_key(issue: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        issue["code"],
        issue["signature"],
        issue["screen_id"],
        str(issue.get("semantic_id", "")),
        _canonical_key(issue["value"]),
    )
