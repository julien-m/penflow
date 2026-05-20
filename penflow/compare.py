"""Structural expected/actual UI-tree comparison."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .tree import flatten_nodes, load_tree, normalize_actual_tree, validate_actual_tree

DEFAULT_TOLERANCE = {
    "bbox_px": 4,
    "color": "exact",
    "radius_px": 2,
    "font_px": 2,
    "order": 0,
}

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
        Path(json_out).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if markdown_out:
        Path(markdown_out).write_text(report_to_markdown(report), encoding="utf-8")
    return report


def compare_trees(expected: dict[str, Any], actual: dict[str, Any], *, threshold: float = 0.9) -> dict[str, Any]:
    actual_schema_issues = validate_actual_tree(actual)
    issues: list[dict[str, Any]] = []
    if actual_schema_issues:
        issues.extend(
            {
                "severity": "error",
                "code": "actual.schema",
                "semantic_id": issue.get("path"),
                "message": issue.get("message"),
            }
            for issue in actual_schema_issues
        )

    expected_screens = {screen["screen_id"]: screen for screen in expected.get("screens", [])}
    actual_screens = {screen.get("screen_id"): screen for screen in actual.get("screens", [])}

    total_checks = 0
    failed_checks = 0
    for screen_id, expected_screen in expected_screens.items():
        actual_screen = actual_screens.get(screen_id)
        if actual_screen is None and len(actual_screens) == 1:
            actual_screen = next(iter(actual_screens.values()))
        if actual_screen is None:
            issues.append(_issue("error", "screen.missing", screen_id, "screen missing in actual tree"))
            failed_checks += 1
            total_checks += 1
            continue

        expected_nodes = _index(flatten_nodes(expected_screen["root"]))
        actual_nodes = _index(flatten_nodes(actual_screen.get("root", {})))
        for semantic_id, expected_node in expected_nodes.items():
            if _is_masked(expected_node):
                continue
            total_checks += 1
            actual_node = actual_nodes.get(semantic_id)
            if actual_node is None:
                failed_checks += 1
                issues.append(_issue("error", "node.missing", semantic_id, "node missing in actual tree"))
                continue
            node_issues = compare_node(expected_node, actual_node)
            failed_checks += sum(1 for issue in node_issues if issue["severity"] in {"error", "warning"})
            total_checks += max(0, len(node_issues) - 1)
            issues.extend(node_issues)

    score = 1.0 if total_checks == 0 else max(0.0, 1 - (failed_checks / total_checks))
    status = "PASS" if score >= threshold and not any(i["severity"] == "error" for i in issues) else "FAIL"
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


def compare_node(expected: dict[str, Any], actual: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    semantic_id = expected.get("_semantic_key") or expected.get("semantic_id") or expected.get("id")
    tolerance = DEFAULT_TOLERANCE | (expected.get("context", {}).get("tolerance", {}) or {})

    for key in ("role",):
        if expected.get(key) and actual.get(key) and expected.get(key) != actual.get(key):
            issues.append(_issue("error", f"node.{key}", semantic_id, f"{key} differs"))

    if not _text_masked(expected):
        expected_text = expected.get("text")
        actual_text = actual.get("text")
        if expected_text not in (None, "") and actual_text not in (None, "") and expected_text != actual_text:
            issues.append(_issue("warning", "node.text", semantic_id, "text differs"))

    if expected.get("_parent_key") and actual.get("_parent_key") and expected["_parent_key"] != actual["_parent_key"]:
        issues.append(_issue("warning", "node.hierarchy", semantic_id, "parent differs"))

    if abs(float(expected.get("_order", 0)) - float(actual.get("_order", 0))) > float(tolerance.get("order", 0)):
        issues.append(_issue("warning", "node.order", semantic_id, "order differs"))

    issues.extend(_compare_bbox(semantic_id, expected.get("bbox", {}), actual.get("bbox", {}), tolerance))
    issues.extend(_compare_visual(semantic_id, expected.get("visual", {}), actual.get("visual", {}), tolerance))
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
    lines.extend(["", "## Issues", "", "| Severity | Code | Semantic ID | Message |", "|---|---|---|---|"])
    if not report["issues"]:
        lines.append("| info | none | - | no issues |")
    for issue in report["issues"]:
        lines.append(
            f"| {issue['severity']} | {issue['code']} | {issue.get('semantic_id') or '-'} | {issue['message']} |"
        )
    return "\n".join(lines) + "\n"


def _index(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(node["_semantic_key"]): node for node in nodes if node.get("_semantic_key")}


def _is_masked(node: dict[str, Any]) -> bool:
    context = node.get("context", {})
    role = node.get("role")
    return bool(context.get("mask")) or role in MASK_ROLES or context.get("variant") == "volatile"


def _text_masked(node: dict[str, Any]) -> bool:
    context = node.get("context", {})
    return bool(context.get("mask_text")) or context.get("variant") in {"dynamic", "volatile"}


def _compare_bbox(
    semantic_id: str,
    expected: dict[str, Any],
    actual: dict[str, Any],
    tolerance: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    limit = float(tolerance.get("bbox_px", DEFAULT_TOLERANCE["bbox_px"]))
    for key in ("x", "y", "width", "height"):
        if key not in expected or key not in actual:
            continue
        if abs(float(expected[key]) - float(actual[key])) > limit:
            issues.append(_issue("warning", f"node.bbox.{key}", semantic_id, f"bbox {key} differs"))
    return issues


def _compare_visual(
    semantic_id: str,
    expected: dict[str, Any],
    actual: dict[str, Any],
    tolerance: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for key in ("fill", "stroke", "fontFamily", "fontWeight"):
        if expected.get(key) and actual.get(key) and expected[key] != actual[key]:
            issues.append(_issue("warning", f"node.visual.{key}", semantic_id, f"{key} differs"))
    for key, limit_name in (("cornerRadius", "radius_px"), ("fontSize", "font_px")):
        if key in expected and key in actual:
            limit = float(tolerance.get(limit_name, DEFAULT_TOLERANCE[limit_name]))
            if abs(float(expected[key]) - float(actual[key])) > limit:
                issues.append(_issue("warning", f"node.visual.{key}", semantic_id, f"{key} differs"))
    return issues


def _issue(severity: str, code: str, semantic_id: str | None, message: str) -> dict[str, Any]:
    return {"severity": severity, "code": code, "semantic_id": semantic_id, "message": message}

