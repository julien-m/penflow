# @spec(FR-001)
# @spec(FR-002)
# @spec(FR-003)
# @spec(FR-004)
"""Structural expected/actual UI-tree comparison."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from .compare_scope import declared_states, effective_conditions, join_nodes, witnessed
from .tree import flatten_nodes, load_tree, normalize_actual_tree, validate_actual_tree

DEFAULT_TOLERANCE = {
    "bbox_px": 4,
    "color": "exact",
    "radius_px": 2,
    "font_px": 2,
    "order": 0,
    # @spec FR-003: spacing tolerance for gap/padding — .specs/features/048-compare-layout-spacing-properties/spec.md#fr-003
    "spacing_px": 2,
}

# Historical lenient threshold (pre-049) vs the strict default (feature 049).
LENIENT_THRESHOLD = 0.9
STRICT_THRESHOLD = 0.98

MASK_ROLES = {"timer", "clock"}


def compare_tree_files(
    expected_path: str | Path,
    actual_path: str | Path,
    *,
    json_out: str | Path | None = None,
    markdown_out: str | Path | None = None,
    threshold: float = 0.9,
) -> dict[str, Any]:
    expected = load_tree(expected_path)
    actual = normalize_actual_tree(load_tree(actual_path))
    report = compare_trees(expected, actual, threshold=threshold)
    if json_out:
        Path(json_out).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    if markdown_out:
        Path(markdown_out).write_text(report_to_markdown(report), encoding="utf-8")
    return report


def compare_trees(
    expected: dict[str, Any],
    actual: dict[str, Any],
    *,
    threshold: float = 0.9,
    mandatory: bool = False,
) -> dict[str, Any]:
    """Compare validated trees by screen, semantic node identity, geometry, and style.

    Args:
        expected: Source-derived tree describing the required UI.
        actual: Observed tree in the same normalized coordinate system.
        threshold: Minimum passing comparison score; errors still fail the report.
        mandatory: Disable node/text masks and custom tolerance overrides.

    Returns:
        A deterministic report with status, score, summary counts, and issues.
    """
    # Reject invalid schemas first, then join screens/nodes before comparing their properties.
    issues: list[dict[str, Any]] = []
    for label, tree in (("expected", expected), ("actual", actual)):
        for issue in validate_actual_tree(tree, schema=True):
            issues.append(_issue("error", f"{label}.schema", issue["path"], issue["message"]))
    if issues:
        return _comparison_report(issues, 0, 0, threshold)

    expected_screens = {screen["screen_id"]: screen for screen in expected.get("screens", [])}
    captures: dict[str, list[dict[str, Any]]] = {}
    for screen in actual.get("screens", []):
        captures.setdefault(screen.get("screen_id"), []).append(screen)
    actual_screens = {screen_id: screens[0] for screen_id, screens in captures.items()}

    total_checks = 0
    failed_checks = 0
    for screen_id, expected_screen in expected_screens.items():
        screen_captures = captures.get(screen_id, [])
        if not screen_captures:
            issues.append(
                _issue("error", "screen.missing", screen_id, "screen missing in actual tree")
            )
            failed_checks += 1
            total_checks += 1
            continue
        expected_flat = flatten_nodes(expected_screen["root"])
        checks, failed, screen_issues = _compare_screen(
            expected_screen, expected_flat, screen_captures, actual, mandatory=mandatory
        )
        total_checks += checks
        failed_checks += failed
        issues.extend(screen_issues)

    issues.extend(_unexpected_screens(expected_screens, actual_screens))
    return _comparison_report(issues, total_checks, failed_checks, threshold)


def _compare_screen(
    expected_screen: dict[str, Any],
    expected_nodes: list[dict[str, Any]],
    captures: list[dict[str, Any]],
    actual: dict[str, Any],
    *,
    mandatory: bool,
) -> tuple[int, int, list[dict[str, Any]]]:
    """Compare one expected screen with its capture, or with one capture per state.

    A stateless capture (validation allows only one per screen) is the strict
    comparison: every expected node is required in it. State captures are each compared
    with the nodes of their state, must be declared and witnessed, and every state an
    expected node is scoped to must be captured.
    """
    issues: list[dict[str, Any]] = []
    checks = failed = 0
    scoped = [capture for capture in captures if capture.get("state") is not None]
    if not scoped:
        targets: list[tuple[dict[str, Any], str | None]] = [(captures[0], None)]
    else:
        declared = expected_screen.get("states")
        targets = []
        for capture in scoped:
            state = str(capture["state"])
            if not isinstance(declared, list):
                issues.append(
                    _issue(
                        "error",
                        "screen.state_undeclared",
                        expected_screen["screen_id"],
                        f"state capture {state} of a screen without declared contract states",
                    )
                )
                failed += 1
            elif state not in declared:
                issues.append(
                    _issue(
                        "error",
                        "screen.state_unknown",
                        expected_screen["screen_id"],
                        f"state {state} is not a contract state of the screen",
                    )
                )
                failed += 1
            else:
                if not witnessed(actual, capture):
                    issues.append(
                        _issue(
                            "error",
                            "screen.state_unwitnessed",
                            expected_screen["screen_id"],
                            f"state capture {state} has no observed_states witness of its scenario",
                        )
                    )
                    failed += 1
                targets.append((capture, state))
            checks += 1
        captured = {state for _, state in targets}
        for state, keys in sorted(declared_states(expected_nodes).items()):
            if state not in captured:
                checks += len(keys)
                failed += len(keys)
                issues.append(
                    _issue(
                        "error",
                        "screen.state_missing",
                        expected_screen["screen_id"],
                        f"state {state} was not captured; its nodes are unobserved: "
                        + ", ".join(keys),
                    )
                )
    seen: set[str] = set()
    for capture, scope in targets:
        join = join_nodes(
            expected_nodes,
            flatten_nodes(capture.get("root", {})),
            scope,
            masked=(lambda node: False) if mandatory else _is_masked,
            facts=capture.get("facts"),
        )
        seen |= join.applicable
        issues.extend(join.issues)
        checks += join.checks
        failed += join.failed
        for expected_node, actual_node in join.pairs:
            node_issues = compare_node(expected_node, actual_node, mandatory=mandatory)
            failed += sum(1 for issue in node_issues if issue["severity"] in {"error", "warning"})
            checks += max(0, len(node_issues) - 1)
            issues.extend(node_issues)
    # A data-conditioned node must be required by at least one capture: no capture may
    # leave an expected control unobserved by choosing facts under which it never applies.
    for key, conditions in sorted(effective_conditions(expected_nodes).items()):
        if conditions and key not in seen:
            checks += 1
            failed += 1
            issues.append(
                _issue("error", "node.condition_unwitnessed", key, "no capture meets its condition")
            )
    return checks, failed, issues


def _comparison_report(
    issues: list[dict[str, Any]], total_checks: int, failed_checks: int, threshold: float
) -> dict[str, Any]:
    score = 0.0 if total_checks == 0 else max(0.0, 1 - (failed_checks / total_checks))
    status = (
        "PASS"
        if score >= threshold and not any(i["severity"] == "error" for i in issues)
        else "FAIL"
    )
    return {
        "version": 1,
        "status": status,
        "score": round(score, 4),
        "threshold": threshold,
        "summary": {
            "checks": total_checks,
            "failed": failed_checks,
            "issues": len(issues),
            "errors": sum(1 for issue in issues if issue["severity"] == "error"),
            "warnings": sum(1 for issue in issues if issue["severity"] == "warning"),
        },
        "issues": issues,
    }


def compare_node(
    expected: dict[str, Any], actual: dict[str, Any], *, mandatory: bool = False
) -> list[dict[str, Any]]:
    """Compare one pair of normalized semantic nodes.

    Args:
        expected: Required node, including declared text, geometry, and visual properties.
        actual: Measured counterpart with normalized parent and order metadata.
        mandatory: Disable text masks and custom tolerances; the tree caller also
            disables whole-node masks before reaching this function.

    Returns:
        Structured differences in role, required text, hierarchy, order, geometry, and style.
    """
    issues: list[dict[str, Any]] = []
    semantic_id = expected.get("_semantic_key") or expected.get("semantic_id") or expected.get("id")
    tolerance = (
        DEFAULT_TOLERANCE
        if mandatory
        else DEFAULT_TOLERANCE | (expected.get("context", {}).get("tolerance", {}) or {})
    )

    for key in ("role",):
        if expected.get(key) and expected.get(key) != actual.get(key):
            issues.append(_issue("error", f"node.{key}", semantic_id, f"{key} differs"))

    if mandatory or not _text_masked(expected):
        expected_text = expected.get("text")
        actual_text = actual.get("text")
        if expected_text not in (None, "") and expected_text != actual_text:
            issues.append(
                _issue(
                    "error" if actual_text is None else "warning",
                    "node.text",
                    semantic_id,
                    "text differs or is unobserved",
                )
            )

    # A control labelled by a sibling label (``label-for``): the runtime must associate the
    # same label text with it (HTML ``<label for>`` and the control ``id``).
    expected_label = expected.get("label")
    if expected_label not in (None, "") and expected_label != actual.get("label"):
        issues.append(
            _issue(
                "error",
                "node.label.missing" if actual.get("label") is None else "node.label",
                semantic_id,
                "associated label differs or is unobserved",
            )
        )

    if (
        expected.get("_parent_key")
        and actual.get("_parent_key")
        and expected["_parent_key"] != actual["_parent_key"]
    ):
        issues.append(_issue("warning", "node.hierarchy", semantic_id, "parent differs"))

    if abs(float(expected.get("_order", 0)) - float(actual.get("_order", 0))) > float(
        cast(float, tolerance.get("order", 0))
    ):
        issues.append(_issue("warning", "node.order", semantic_id, "order differs"))

    issues.extend(
        _compare_bbox(
            semantic_id,
            expected.get("bbox", {}),
            actual.get("bbox", {}),
            tolerance,
            mandatory=mandatory,
        )
    )
    issues.extend(
        _compare_visual(
            semantic_id, expected.get("visual", {}), actual.get("visual", {}), tolerance
        )
    )
    return issues


def report_to_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Penflow Compare Report",
        "",
        f"**Status:** {report['status']}",
        f"**Score:** {report['score']}",
        f"**Threshold:** {report['threshold']}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for key, value in report["summary"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(
        ["", "## Issues", "", "| Severity | Code | Semantic ID | Message |", "|---|---|---|---|"]
    )
    if not report["issues"]:
        lines.append("| info | none | - | no issues |")
    for issue in report["issues"]:
        lines.append(
            f"| {issue['severity']} | {issue['code']} | {issue.get('semantic_id') or '-'} | {issue['message']} |"
        )
    return "\n".join(lines) + "\n"


def _is_masked(node: dict[str, Any]) -> bool:
    context = node.get("context", {})
    role = node.get("role")
    return bool(context.get("mask")) or role in MASK_ROLES or context.get("variant") == "volatile"


def _text_masked(node: dict[str, Any]) -> bool:
    context = node.get("context", {})
    return bool(context.get("mask_text")) or context.get("variant") in {"dynamic", "volatile"}


def _compare_bbox(
    semantic_id: str | None,
    expected: dict[str, Any],
    actual: dict[str, Any],
    tolerance: dict[str, Any],
    *,
    mandatory: bool = False,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not mandatory and not _bbox_is_measurable(expected):
        return issues
    limit = float(tolerance.get("bbox_px", DEFAULT_TOLERANCE["bbox_px"]))
    for key in ("x", "y", "width", "height"):
        if key not in expected or key not in actual:
            continue
        if abs(float(expected[key]) - float(actual[key])) > limit:
            issues.append(_issue("warning", f"node.bbox.{key}", semantic_id, f"bbox {key} differs"))
    return issues


def _bbox_is_measurable(bbox: dict[str, Any]) -> bool:
    try:
        return float(bbox.get("width", 0)) > 0 and float(bbox.get("height", 0)) > 0
    except (TypeError, ValueError):
        return False


def _compare_visual(
    semantic_id: str | None,
    expected: dict[str, Any],
    actual: dict[str, Any],
    tolerance: dict[str, Any],
) -> list[dict[str, Any]]:
    expected = _normalized_stroke(expected)
    actual = _normalized_stroke(actual)
    issues: list[dict[str, Any]] = []
    for key in expected.keys() - actual.keys():
        issues.append(
            _issue(
                "error",
                f"node.visual.{key}.missing",
                semantic_id,
                f"required {key} was not observed",
            )
        )
    # @spec FR-002: exact-match layout/alignItems comparison — .specs/features/048-compare-layout-spacing-properties/spec.md#fr-002
    for key in (
        "fill",
        "stroke",
        "fontFamily",
        "fontWeight",
        "layout",
        "alignItems",
        "textAlign",
        "strokeThickness",
        "strokeWidth",
        "strokeAlignment",
    ):
        if key in expected and key in actual and expected[key] != actual[key]:
            issues.append(_issue("warning", f"node.visual.{key}", semantic_id, f"{key} differs"))
    for key, limit_name in (("cornerRadius", "radius_px"), ("fontSize", "font_px")):
        if key in expected and key in actual:
            limit = float(tolerance.get(limit_name, DEFAULT_TOLERANCE[limit_name]))
            if abs(float(expected[key]) - float(actual[key])) > limit:
                issues.append(
                    _issue("warning", f"node.visual.{key}", semantic_id, f"{key} differs")
                )
    issues.extend(_compare_spacing(semantic_id, expected, actual, tolerance))
    return issues


def _compare_spacing(
    semantic_id: str | None,
    expected: dict[str, Any],
    actual: dict[str, Any],
    tolerance: dict[str, Any],
) -> list[dict[str, Any]]:
    # @spec FR-003: tolerance-based gap/padding comparison — .specs/features/048-compare-layout-spacing-properties/spec.md#fr-003
    """Compare ``gap`` and ``padding`` with the ``spacing_px`` tolerance.

    Absent keys (on either side) emit no issues — pre-048 trees stay green.
    Padding is canonicalized to ``[top, right, bottom, left]`` (feature 047
    semantics: ``16`` ≡ ``[16, 16]`` ≡ ``[16, 16, 16, 16]``); the deviation is
    the max element-wise absolute difference. Values that cannot be
    canonicalized compare as opaque values (differing forms emit a warning).
    """
    issues: list[dict[str, Any]] = []
    limit = float(tolerance.get("spacing_px", DEFAULT_TOLERANCE["spacing_px"]))
    if "gap" in expected and "gap" in actual:
        if _spacing_differs(expected["gap"], actual["gap"], limit):
            issues.append(_issue("warning", "node.visual.gap", semantic_id, "gap differs"))
    if "padding" in expected and "padding" in actual:
        expected_padding = _canonical_padding(expected["padding"])
        actual_padding = _canonical_padding(actual["padding"])
        if expected_padding is not None and actual_padding is not None:
            deviation = max(
                abs(float(left) - float(right))
                for left, right in zip(expected_padding, actual_padding)
            )
            if deviation > limit:
                issues.append(
                    _issue("warning", "node.visual.padding", semantic_id, "padding differs")
                )
        elif expected["padding"] != actual["padding"]:
            issues.append(_issue("warning", "node.visual.padding", semantic_id, "padding differs"))
    return issues


def _spacing_differs(expected: Any, actual: Any, limit: float) -> bool:
    if _is_number(expected) and _is_number(actual):
        return abs(float(expected) - float(actual)) > limit
    return bool(expected != actual)


def _canonical_padding(value: Any) -> list[int | float] | None:
    """Expand CSS-style padding to `[top, right, bottom, left]` when numeric."""
    if _is_number(value):
        side = _canonical_number(value)
        return [side, side, side, side]
    if isinstance(value, list) and value and all(_is_number(item) for item in value):
        items = [_canonical_number(item) for item in value]
        if len(items) == 1:
            return [items[0], items[0], items[0], items[0]]
        if len(items) == 2:
            return [items[0], items[1], items[0], items[1]]
        if len(items) == 4:
            return items
    return None


def _canonical_number(value: Any) -> int | float:
    number = float(value)
    return int(number) if number.is_integer() else number


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _issue(severity: str, code: str, semantic_id: str | None, message: str) -> dict[str, Any]:
    return {"severity": severity, "code": code, "semantic_id": semantic_id, "message": message}


def _unexpected_screens(
    expected_screens: dict[str, Any], actual_screens: dict[str, Any]
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for screen_id in actual_screens.keys() - expected_screens.keys():
        issues.append(_issue("error", "screen.unexpected", screen_id, "unexpected actual screen"))
    return issues


def _normalized_stroke(visual: dict[str, Any]) -> dict[str, Any]:
    result = dict(visual)
    stroke = visual.get("stroke")
    if isinstance(stroke, dict):
        result.update(stroke=stroke["fill"], strokeThickness=stroke["thickness"])
    # C12 actual-ui-tree v1 accepts scalar and per-edge strokeWidth; native 2.14
    # retains edges. Remove scalar expansion only when C12 drops scalar support
    # and supported adapters have migrated to per-edge observations.
    if "strokeWidth" in result:
        width = result["strokeWidth"]
        result["strokeWidth"] = (
            [width.get(side, 0) for side in ("top", "right", "bottom", "left")]
            if isinstance(width, dict)
            else [width] * 4
        )
    return result
