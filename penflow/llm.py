"""Deterministic report review and fix guidance helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .tree import load_tree


def review_compare_report(report_path: str | Path) -> str:
    """Return stable Markdown explaining compare-report issues by semantic id."""

    report = load_tree(report_path)
    lines = [
        "# Penflow Review",
        "",
        f"**Status:** {report.get('status', 'UNKNOWN')}",
        f"**Score:** {report.get('score', 'n/a')}",
        "",
        "| Severity | Semantic ID | Likely Cause | Owner |",
        "|---|---|---|---|",
    ]
    issues = report.get("issues", []) or []
    if not issues:
        lines.append("| info | - | No structural issues found. | none |")
    for issue in issues:
        lines.append(
            "| {severity} | {semantic_id} | {cause} | {owner} |".format(
                severity=issue.get("severity", "unknown"),
                semantic_id=issue.get("semantic_id") or "-",
                cause=_cause(issue),
                owner=_owner(issue),
            )
        )
    return "\n".join(lines) + "\n"


def fix_compare_report(report_path: str | Path) -> str:
    """Return stable Markdown fix suggestions for compare-report issues."""

    report = load_tree(report_path)
    lines = [
        "# Penflow Fix Plan",
        "",
        f"**Status:** {report.get('status', 'UNKNOWN')}",
        f"**Score:** {report.get('score', 'n/a')}",
        "",
        "| Semantic ID | Fix | Target |",
        "|---|---|---|",
    ]
    issues = report.get("issues", []) or []
    if not issues:
        lines.append("| - | No fixes required. | none |")
    for issue in issues:
        lines.append(
            "| {semantic_id} | {fix} | {target} |".format(
                semantic_id=issue.get("semantic_id") or "-",
                fix=_fix(issue),
                target=_owner(issue),
            )
        )
    return "\n".join(lines) + "\n"


def _cause(issue: dict[str, Any]) -> str:
    code = str(issue.get("code", ""))
    if code == "node.missing":
        return "Expected semantic node is absent from the actual tree."
    if code == "node.role":
        return "Runtime role diverges from the Pencil context role."
    if code == "node.text":
        return "Runtime text differs from the design contract."
    if code.startswith("node.bbox"):
        return "Runtime geometry exceeds the configured tolerance."
    if code.startswith("node.visual"):
        return "Runtime visual property differs from the expected design token."
    if code == "node.hierarchy":
        return "Runtime parent hierarchy differs from the expected tree."
    if code == "node.order":
        return "Runtime sibling order differs from the expected tree."
    if code == "actual.schema":
        return "Actual tree payload does not match the required schema."
    return str(issue.get("message") or "Compare report issue requires inspection.")


def _fix(issue: dict[str, Any]) -> str:
    code = str(issue.get("code", ""))
    if code == "node.missing":
        return "Add the missing runtime element or restore its `semantic_id` mapping."
    if code == "node.role":
        return "Align runtime accessibility role with the Pencil `context.role`."
    if code == "node.text":
        return "Update runtime text or mark volatile copy with `mask_text` in `.pen`."
    if code.startswith("node.bbox"):
        return "Adjust runtime layout or set an explicit `tolerance.bbox_px` in `.pen`."
    if code.startswith("node.visual"):
        return "Align styling with the `.pen` visual property or design token."
    if code == "node.hierarchy":
        return "Move the runtime node under the expected semantic parent."
    if code == "node.order":
        return "Reorder runtime siblings or configure tolerated order drift."
    if code == "actual.schema":
        return "Emit the required actual-tree fields before comparing."
    return "Inspect the expected and actual trees for this semantic id."


def _owner(issue: dict[str, Any]) -> str:
    code = str(issue.get("code", ""))
    if code == "actual.schema":
        return "actual-tree exporter"
    if code.startswith("node.visual") or code.startswith("node.bbox"):
        return "runtime layout/styling or `.pen` tolerance"
    if code in {"node.missing", "node.role", "node.text", "node.hierarchy", "node.order"}:
        return "runtime implementation or `.pen` contract"
    return "manual review"
