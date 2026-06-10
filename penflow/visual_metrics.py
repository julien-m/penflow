"""Deterministic visual metrics audit for expected UI trees — zero vision needed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .color import parse_color, resolve_variable

# Mask and bbox semantics are shared with the compare engine (features 011/048)
# so audit-visual can never disagree with compare-tree on what is checkable.
from .compare import _bbox_is_measurable, _canonical_number, _is_masked, _is_number
from .tree import flatten_nodes, load_tree

REPORT_KIND = "penflow-visual-metrics-report"
REPORT_VERSION = 1

# Tappable subset of the contract interactive roles (flow_contract.py);
# form/component are containers, not touch targets.
INTERACTIVE_ROLES = frozenset({"button", "link", "input", "select", "toggle"})

# WCAG AA contrast thresholds (success criterion 1.4.3).
CONTRAST_AA_NORMAL = 4.5
CONTRAST_AA_LARGE = 3.0
LARGE_TEXT_PX = 24.0
LARGE_BOLD_TEXT_PX = 18.0
BOLD_FONT_WEIGHT = 700.0

# Touch-target boundaries: >= 44px passes, < 24px is an error, 24-43 warns.
TOUCH_TARGET_PASS_PX = 44.0
TOUCH_TARGET_ERROR_PX = 24.0

# Sibling overlap / parent overflow tolerance in pixels.
GEOMETRY_TOLERANCE_PX = 1.0

# Average glyph width as a fraction of fontSize for the overflow heuristic.
TEXT_WIDTH_FACTOR = 0.55


def audit_visual(
    tree_path: str | Path,
    *,
    theme: dict[str, Any] | None = None,
    theme_css: str | None = None,
) -> dict[str, Any]:
    # @spec FR-001: Deterministic visual metrics engine — .specs/features/050-deterministic-visual-metrics-audit/spec.md#fr-001
    """Audit computable visual metrics in an expected UI tree.

    Args:
        tree_path: Path to an `expected-ui-tree.json` (feature 006 shape).
        theme: Loaded theme (`penflow.theme.load_theme` shape). `None` leaves
            `$pf-*` fill references unresolved (they degrade to
            `visual.color.unparsed` info issues).
        theme_css: Theme CSS path recorded in the report inputs.

    Returns:
        A strict visual metrics report dictionary
        (`visual-metrics-report.schema.json`).

    Raises:
        ValueError: If the tree is not an object with a ``screens`` list of
            objects carrying object roots — malformed input fails closed.
    """
    tree = load_tree(tree_path)
    if not isinstance(tree, dict) or not isinstance(tree.get("screens"), list):
        raise ValueError(f"expected tree must be an object with a screens list: {tree_path}")
    raw_variables = theme.get("variables") if isinstance(theme, dict) else None
    variables: dict[str, Any] = raw_variables if isinstance(raw_variables, dict) else {}

    issues: list[dict[str, Any]] = []
    nodes_checked = 0
    screens_checked = 0
    for index, screen in enumerate(tree.get("screens", [])):
        if not isinstance(screen, dict):
            raise ValueError(f"screens[{index}] must be an object")
        screen_id = str(screen.get("screen_id") or screen.get("pencil_id") or screen.get("name"))
        root = screen.get("root")
        if not isinstance(root, dict):
            raise ValueError(f"screens[{index}].root must be an object")
        screens_checked += 1
        nodes = flatten_nodes(root)
        nodes_checked += len(nodes)
        issues.extend(_audit_screen(screen_id, nodes, variables))
    issues.sort(key=_issue_sort_key)

    errors = sum(1 for issue in issues if issue["severity"] == "error")
    warnings = sum(1 for issue in issues if issue["severity"] == "warning")
    infos = sum(1 for issue in issues if issue["severity"] == "info")
    return {
        "version": REPORT_VERSION,
        "kind": REPORT_KIND,
        "status": "PASS" if errors == 0 else "FAIL",
        "summary": {
            "errors": errors,
            "warnings": warnings,
            "infos": infos,
            "nodes_checked": nodes_checked,
            "screens_checked": screens_checked,
        },
        "inputs": {"expected_tree": str(tree_path), "theme_css": theme_css},
        "issues": issues,
    }


def write_visual_metrics_report(report: dict[str, Any], out_path: str | Path) -> None:
    """Serialize a report with the byte-stable recipe shared by all artifacts.

    Args:
        report: Visual metrics report dictionary produced by `audit_visual`.
        out_path: Destination path, created or overwritten as UTF-8 JSON with
            sorted keys, two-space indentation, and a trailing newline.
    """
    Path(out_path).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    """Compute WCAG 2.x relative luminance for an 8-bit RGB triple."""
    red, green, blue = (_linear_channel(channel) for channel in rgb)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(
    foreground: tuple[int, int, int, int], background: tuple[int, int, int, int]
) -> float:
    # @spec FR-002: WCAG AA contrast from relative luminance — .specs/features/050-deterministic-visual-metrics-audit/spec.md#fr-002
    """Compute the WCAG contrast ratio between two RGBA colors (alpha ignored)."""
    lighter = relative_luminance(foreground[:3])
    darker = relative_luminance(background[:3])
    if darker > lighter:
        lighter, darker = darker, lighter
    return (lighter + 0.05) / (darker + 0.05)


def _linear_channel(channel: int) -> float:
    scaled = channel / 255
    # WCAG 2.x formula constant (0.03928), not the sRGB errata value.
    if scaled <= 0.03928:
        return scaled / 12.92
    return ((scaled + 0.055) / 1.055) ** 2.4


def _audit_screen(
    screen_id: str, nodes: list[dict[str, Any]], variables: dict[str, Any]
) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {
        str(node["_semantic_key"]): node for node in nodes if node.get("_semantic_key")
    }
    issues: list[dict[str, Any]] = []
    fills = _parse_fills(screen_id, nodes, variables, issues)
    for node in nodes:
        if _is_masked(node):
            # Masked nodes are never checked, but their fills stay available
            # as contrast backgrounds (a masked container still has a color).
            continue
        issues.extend(_contrast_issues(screen_id, node, by_key, fills))
        issues.extend(_touch_target_issues(screen_id, node))
        issues.extend(_text_overflow_issues(screen_id, node))
        issues.extend(_overflow_issues(screen_id, node, by_key))
    issues.extend(_overlap_issues(screen_id, nodes))
    return issues


def _parse_fills(
    screen_id: str,
    nodes: list[dict[str, Any]],
    variables: dict[str, Any],
    issues: list[dict[str, Any]],
) -> dict[str, tuple[int, int, int, int] | None]:
    # @spec FR-006: $pf-* resolution and unparseable fill surfacing — .specs/features/050-deterministic-visual-metrics-audit/spec.md#fr-006
    """Resolve and parse every node fill once; surface unparseable fills.

    Returns a map from semantic key to parsed RGBA (or `None` when the node
    has no fill or an unparseable one). Unparseable fills on non-masked nodes
    emit one `visual.color.unparsed` info issue each.
    """
    fills: dict[str, tuple[int, int, int, int] | None] = {}
    for node in nodes:
        key = str(node.get("_semantic_key"))
        visual = node.get("visual")
        if not isinstance(visual, dict) or "fill" not in visual:
            fills[key] = None
            continue
        raw = visual["fill"]
        resolved = resolve_variable(raw, variables) if isinstance(raw, str) else raw
        parsed = parse_color(resolved) if isinstance(resolved, str) else None
        fills[key] = parsed
        if parsed is None and not _is_masked(node):
            issues.append(
                _issue(
                    "visual.color.unparsed",
                    "info",
                    screen_id,
                    node,
                    f"fill {raw!r} could not be resolved to a parseable color",
                    value=str(raw),
                )
            )
    return fills


def _contrast_issues(
    screen_id: str,
    node: dict[str, Any],
    by_key: dict[str, dict[str, Any]],
    fills: dict[str, tuple[int, int, int, int] | None],
) -> list[dict[str, Any]]:
    # @spec FR-002: text fill vs nearest ancestor fill via parent walk — .specs/features/050-deterministic-visual-metrics-audit/spec.md#fr-002
    if node.get("role") != "text":
        return []
    foreground = fills.get(str(node.get("_semantic_key")))
    if foreground is None:
        # No own parseable fill: nothing to measure (an unparseable fill
        # already surfaced as visual.color.unparsed).
        return []
    background = _nearest_background(node, by_key, fills)
    if background is None:
        return [
            _issue(
                "visual.contrast.unresolved",
                "info",
                screen_id,
                node,
                "no ancestor with a parseable fill; contrast check skipped",
            )
        ]
    ratio = contrast_ratio(foreground, background)
    required = _required_contrast(node)
    if ratio >= required:
        return []
    return [
        _issue(
            "visual.contrast.below_aa",
            "error",
            screen_id,
            node,
            f"contrast ratio {round(ratio, 2)}:1 is below the WCAG AA requirement of {required}:1",
            ratio=round(ratio, 2),
            required=required,
        )
    ]


def _nearest_background(
    node: dict[str, Any],
    by_key: dict[str, dict[str, Any]],
    fills: dict[str, tuple[int, int, int, int] | None],
) -> tuple[int, int, int, int] | None:
    """Walk `_parent_key` ancestors to the nearest parseable fill."""
    parent_key = node.get("_parent_key")
    while parent_key is not None:
        parent = by_key.get(str(parent_key))
        if parent is None:
            return None
        background = fills.get(str(parent_key))
        if background is not None:
            return background
        parent_key = parent.get("_parent_key")
    return None


def _required_contrast(node: dict[str, Any]) -> float:
    """WCAG AA threshold: 3:1 for large text (>=24px, or >=18px bold), else 4.5:1."""
    visual = node.get("visual")
    if not isinstance(visual, dict):
        return CONTRAST_AA_NORMAL
    font_size = visual.get("fontSize")
    if not isinstance(font_size, (int, float)) or isinstance(font_size, bool):
        return CONTRAST_AA_NORMAL
    if float(font_size) >= LARGE_TEXT_PX:
        return CONTRAST_AA_LARGE
    if float(font_size) >= LARGE_BOLD_TEXT_PX and _is_bold(visual.get("fontWeight")):
        return CONTRAST_AA_LARGE
    return CONTRAST_AA_NORMAL


def _is_bold(font_weight: Any) -> bool:
    if _is_number(font_weight):
        return float(font_weight) >= BOLD_FONT_WEIGHT
    if isinstance(font_weight, str):
        if font_weight.strip().lower() in {"bold", "bolder"}:
            return True
        try:
            return float(font_weight) >= BOLD_FONT_WEIGHT
        except ValueError:
            return False
    return False


def _touch_target_issues(screen_id: str, node: dict[str, Any]) -> list[dict[str, Any]]:
    # @spec FR-003: touch targets on interactive roles — .specs/features/050-deterministic-visual-metrics-audit/spec.md#fr-003
    if node.get("role") not in INTERACTIVE_ROLES:
        return []
    bbox = node.get("bbox")
    if not isinstance(bbox, dict):
        return []
    if not _bbox_is_measurable(bbox):
        return [
            _issue(
                "visual.bbox.unmeasured",
                "info",
                screen_id,
                node,
                "zero-sized bbox (unmeasured draft); touch target check skipped",
            )
        ]
    width = float(bbox.get("width", 0))
    height = float(bbox.get("height", 0))
    if width >= TOUCH_TARGET_PASS_PX and height >= TOUCH_TARGET_PASS_PX:
        return []
    severity = (
        "error" if width < TOUCH_TARGET_ERROR_PX or height < TOUCH_TARGET_ERROR_PX else "warning"
    )
    return [
        _issue(
            "visual.touch_target.too_small",
            severity,
            screen_id,
            node,
            f"touch target {_canonical_number(width)}x{_canonical_number(height)} is below"
            f" the {_canonical_number(TOUCH_TARGET_PASS_PX)}px minimum",
            width=_canonical_number(width),
            height=_canonical_number(height),
        )
    ]


def _overlap_issues(screen_id: str, nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # @spec FR-004: sibling bbox overlap — .specs/features/050-deterministic-visual-metrics-audit/spec.md#fr-004
    groups: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        parent_key = node.get("_parent_key")
        if parent_key is None or _is_masked(node):
            continue
        bbox = node.get("bbox")
        if not isinstance(bbox, dict) or not _bbox_is_measurable(bbox):
            continue
        groups.setdefault(str(parent_key), []).append(node)
    issues: list[dict[str, Any]] = []
    for siblings in groups.values():
        for first_index, first in enumerate(siblings):
            for second in siblings[first_index + 1 :]:
                if _boxes_overlap(first["bbox"], second["bbox"]):
                    issues.append(
                        _issue(
                            "visual.bbox.overlap",
                            "error",
                            screen_id,
                            first,
                            f"bbox overlaps sibling {second.get('_semantic_key')}"
                            f" by more than {_canonical_number(GEOMETRY_TOLERANCE_PX)}px",
                            other_semantic_id=_semantic_id(second),
                        )
                    )
    return issues


def _boxes_overlap(first: dict[str, Any], second: dict[str, Any]) -> bool:
    overlap_width = min(
        float(first["x"]) + float(first["width"]), float(second["x"]) + float(second["width"])
    ) - max(float(first["x"]), float(second["x"]))
    overlap_height = min(
        float(first["y"]) + float(first["height"]), float(second["y"]) + float(second["height"])
    ) - max(float(first["y"]), float(second["y"]))
    return overlap_width > GEOMETRY_TOLERANCE_PX and overlap_height > GEOMETRY_TOLERANCE_PX


def _overflow_issues(
    screen_id: str, node: dict[str, Any], by_key: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    # @spec FR-004: child-escapes-parent overflow — .specs/features/050-deterministic-visual-metrics-audit/spec.md#fr-004
    parent_key = node.get("_parent_key")
    if parent_key is None:
        return []
    parent = by_key.get(str(parent_key))
    if parent is None:
        return []
    child_bbox = node.get("bbox")
    parent_bbox = parent.get("bbox")
    if not isinstance(child_bbox, dict) or not _bbox_is_measurable(child_bbox):
        return []
    if not isinstance(parent_bbox, dict) or not _bbox_is_measurable(parent_bbox):
        return []
    tolerance = GEOMETRY_TOLERANCE_PX
    escapes = (
        float(child_bbox["x"]) < float(parent_bbox["x"]) - tolerance
        or float(child_bbox["y"]) < float(parent_bbox["y"]) - tolerance
        or float(child_bbox["x"]) + float(child_bbox["width"])
        > float(parent_bbox["x"]) + float(parent_bbox["width"]) + tolerance
        or float(child_bbox["y"]) + float(child_bbox["height"])
        > float(parent_bbox["y"]) + float(parent_bbox["height"]) + tolerance
    )
    if not escapes:
        return []
    return [
        _issue(
            "visual.bbox.overflow",
            "error",
            screen_id,
            node,
            f"bbox escapes parent {parent_key}"
            f" by more than {_canonical_number(GEOMETRY_TOLERANCE_PX)}px",
            other_semantic_id=_semantic_id(parent),
        )
    ]


def _text_overflow_issues(screen_id: str, node: dict[str, Any]) -> list[dict[str, Any]]:
    # @spec FR-005: labeled text overflow heuristic — .specs/features/050-deterministic-visual-metrics-audit/spec.md#fr-005
    text = node.get("text")
    if not isinstance(text, str) or not text:
        return []
    visual = node.get("visual")
    if not isinstance(visual, dict) or not _is_number(visual.get("fontSize")):
        return []
    bbox = node.get("bbox")
    if not isinstance(bbox, dict) or not _bbox_is_measurable(bbox):
        return []
    estimated_width = len(text) * float(visual["fontSize"]) * TEXT_WIDTH_FACTOR
    if estimated_width <= float(bbox["width"]):
        return []
    return [
        _issue(
            "visual.text.likely_overflow",
            "warning",
            screen_id,
            node,
            f"estimated text width {_canonical_number(round(estimated_width, 2))}px exceeds"
            f" bbox width {_canonical_number(float(bbox['width']))}px (heuristic:"
            f" len(text) * fontSize * {TEXT_WIDTH_FACTOR})",
        )
    ]


def _semantic_id(node: dict[str, Any]) -> str | None:
    key = node.get("_semantic_key")
    return str(key) if key is not None else None


def _issue(
    code: str,
    severity: str,
    screen_id: str,
    node: dict[str, Any],
    message: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "screen_id": screen_id,
        "semantic_id": _semantic_id(node),
        "message": message,
        **extra,
    }


def _issue_sort_key(issue: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        issue["code"],
        issue["screen_id"],
        str(issue.get("semantic_id", "")),
        issue["message"],
    )
