"""Drift reporting across flow specs, semantic trees, and Pencil mockups."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .context import Context
from .semantic_enrichment import _pen_records
from .semantic_mapping import pencil_context_map
from .semantic_validation import validate_semantic_tree

CLARIFICATION = "[NEEDS CLARIFICATION]"
REPORT_VERSION = 1


def detect_drift(
    specs_dir: str | Path,
    semantic_tree_path: str | Path,
    pen_path: str | Path,
    out_path: str | Path,
    *,
    markdown_path: str | Path | None = None,
) -> dict[str, Any]:
    """Write deterministic drift reports for specs, semantic tree, and Pencil.

    Args:
        specs_dir: Directory containing `flows/*.md` and `screens/*.md`.
        semantic_tree_path: Valid or partially valid `semantic-ui-tree.json`.
        pen_path: Pencil `.pen` mockup to compare against the semantic tree.
        out_path: Destination JSON report path.
        markdown_path: Optional Markdown summary path.

    Returns:
        The generated drift report.
    """
    specs_root = Path(specs_dir)
    tree = json.loads(Path(semantic_tree_path).read_text(encoding="utf-8"))
    pen = json.loads(Path(pen_path).read_text(encoding="utf-8"))
    issues = _drift_issues(specs_root, tree, pen)
    report = {
        "version": REPORT_VERSION,
        "kind": "penflow-drift-report",
        "status": "DRIFT" if issues else "PASS",
        "summary": _summary(issues),
        "inputs": {
            "flow_ui_contract": str(specs_root),
            "semantic_tree": str(semantic_tree_path),
            "pen": str(pen_path),
        },
        "issues": issues,
    }
    Path(out_path).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if markdown_path is not None:
        Path(markdown_path).write_text(_markdown_report(report), encoding="utf-8")
    return report


def _drift_issues(
    specs_dir: Path, tree: dict[str, Any], pen: dict[str, Any]
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    issues.extend(_semantic_validation_issues(tree))
    issues.extend(_spec_tree_mismatch_issues(specs_dir, tree))
    if not _has_error(issues):
        context_map = pencil_context_map(pen, tree)
        issues.extend(_mapping_issues(context_map))
        issues.extend(_obsolete_context_issues(pen, tree))
        issues.extend(_uncovered_mockup_issues(pen, context_map))
    issues.extend(_clarification_issues(specs_dir, tree))
    return sorted(issues, key=_issue_sort_key)


def _semantic_validation_issues(tree: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _issue(
            "error",
            "drift.semantic_tree_invalid",
            issue.get("path", "$"),
            issue.get("message", "semantic tree validation failed"),
            semantic_id=issue.get("semantic_id"),
        )
        for issue in validate_semantic_tree(tree)
        if issue.get("severity") == "error"
    ]


def _spec_tree_mismatch_issues(specs_dir: Path, tree: dict[str, Any]) -> list[dict[str, Any]]:
    spec_flows = _frontmatter_ids(specs_dir / "flows", "flow")
    spec_screens = _frontmatter_ids(specs_dir / "screens", "screen")
    tree_flows = {str(flow["id"]) for flow in tree.get("flows", []) if isinstance(flow, dict)}
    tree_screens = {
        str(screen["id"]) for screen in tree.get("screens", []) if isinstance(screen, dict)
    }
    issues: list[dict[str, Any]] = []
    for flow_id in sorted(spec_flows.keys() - tree_flows):
        issues.append(
            _issue(
                "warning",
                "drift.spec_flow_not_in_tree",
                spec_flows[flow_id],
                f"flow spec is not represented in semantic tree: {flow_id}",
            )
        )
    for flow_id in sorted(tree_flows - spec_flows.keys()):
        issues.append(
            _issue(
                "warning",
                "drift.tree_flow_missing_spec",
                "$.flows",
                f"semantic tree flow has no flow spec: {flow_id}",
            )
        )
    for screen_id in sorted(spec_screens.keys() - tree_screens):
        issues.append(
            _issue(
                "warning",
                "drift.spec_screen_not_in_tree",
                spec_screens[screen_id],
                f"screen spec is not represented in semantic tree: {screen_id}",
            )
        )
    for screen_id in sorted(tree_screens - spec_screens.keys()):
        issues.append(
            _issue(
                "warning",
                "drift.tree_screen_missing_spec",
                "$.screens",
                f"semantic tree screen has no screen spec: {screen_id}",
            )
        )
    return issues


def _frontmatter_ids(directory: Path, key: str) -> dict[str, str]:
    result: dict[str, str] = {}
    if not directory.is_dir():
        return result
    for path in sorted(directory.glob("*.md")):
        frontmatter = _frontmatter(path)
        value = frontmatter.get(key)
        if isinstance(value, str) and value:
            result[value] = path.as_posix()
    return result


def _frontmatter(path: Path) -> dict[str, Any]:
    content = path.read_text(encoding="utf-8")
    if not content.startswith("---\n"):
        return {}
    end = content.find("\n---\n", 4)
    if end == -1:
        return {}
    parsed = yaml.safe_load(content[4:end])
    return parsed if isinstance(parsed, dict) else {}


def _mapping_issues(context_map: dict[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for item in context_map["unmapped"]:
        issues.append(
            _issue(
                "warning",
                "drift.semantic_node_missing_in_pen",
                "$.screens",
                "semantic node has no conservative Pencil match",
                semantic_id=item["semantic_id"],
            )
        )
    for item in context_map["ambiguous"]:
        issues.append(
            _issue(
                "warning",
                "drift.semantic_node_ambiguous_in_pen",
                "$.screens",
                "semantic node has multiple conservative Pencil matches",
                semantic_id=item["semantic_id"],
            )
        )
    return issues


def _obsolete_context_issues(pen: dict[str, Any], tree: dict[str, Any]) -> list[dict[str, Any]]:
    semantic_ids = _tree_semantic_ids(tree)
    issues = []
    for record in _pen_records(pen):
        semantic_id = Context.from_raw(record.node.get("context")).semantic_id
        if semantic_id and str(semantic_id) not in semantic_ids:
            issues.append(
                _issue(
                    "warning",
                    "drift.pencil_context_obsolete",
                    _pencil_path(record.path),
                    f"Pencil context semantic_id is absent from semantic tree: {semantic_id}",
                    semantic_id=str(semantic_id),
                    pencil_node_id=str(record.node.get("id")),
                )
            )
    return issues


def _uncovered_mockup_issues(
    pen: dict[str, Any], context_map: dict[str, Any]
) -> list[dict[str, Any]]:
    matched_ids = {str(item["pencil_node_id"]) for item in context_map["matched"]}
    issues = []
    for record in _pen_records(pen):
        node_id = str(record.node.get("id"))
        has_semantic_context = Context.from_raw(record.node.get("context")).semantic_id is not None
        if node_id not in matched_ids and not has_semantic_context:
            issues.append(
                _issue(
                    "warning",
                    "drift.mockup_node_uncovered",
                    _pencil_path(record.path),
                    "Pencil node is not covered by semantic tree mapping",
                    pencil_node_id=node_id,
                )
            )
    return issues


def _clarification_issues(specs_dir: Path, tree: dict[str, Any]) -> list[dict[str, Any]]:
    issues = _clarification_spec_issues(specs_dir)
    issues.extend(_clarification_tree_issues(tree))
    return issues


def _clarification_spec_issues(specs_dir: Path) -> list[dict[str, Any]]:
    issues = []
    for path in sorted(specs_dir.rglob("*.md")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if CLARIFICATION in line:
                issues.append(
                    _issue(
                        "warning",
                        "drift.clarification_marker",
                        f"{path.as_posix()}:{line_number}",
                        "flow-ui-contract spec still contains a clarification marker",
                    )
                )
    return issues


def _clarification_tree_issues(tree: dict[str, Any]) -> list[dict[str, Any]]:
    issues = []
    for path, value in _walk_values(tree, "$"):
        if isinstance(value, str) and CLARIFICATION in value:
            semantic_id = _semantic_id_from_path(tree, path)
            issues.append(
                _issue(
                    "warning",
                    "drift.clarification_marker",
                    path,
                    "semantic tree still contains a clarification marker",
                    semantic_id=semantic_id,
                )
            )
    return issues


def _walk_values(value: Any, path: str) -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        result: list[tuple[str, Any]] = []
        for key in sorted(value):
            result.extend(_walk_values(value[key], f"{path}.{key}"))
        return result
    if isinstance(value, list):
        result = []
        for index, item in enumerate(value):
            result.extend(_walk_values(item, f"{path}[{index}]"))
        return result
    return [(path, value)]


def _semantic_id_from_path(tree: dict[str, Any], path: str) -> str | None:
    best_match = None
    for node_path, node in _walk_semantic_nodes_with_paths(tree):
        if path.startswith(node_path):
            best_match = str(node["semantic_id"])
    return best_match


def _walk_semantic_nodes_with_paths(tree: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    result = []
    for screen_index, screen in enumerate(tree.get("screens", []) or []):
        root = screen.get("root") if isinstance(screen, dict) else None
        if isinstance(root, dict):
            result.extend(_walk_node_paths(root, f"$.screens[{screen_index}].root"))
    return result


def _walk_node_paths(node: dict[str, Any], path: str) -> list[tuple[str, dict[str, Any]]]:
    result = [(path, node)]
    for index, child in enumerate(node.get("children", []) or []):
        if isinstance(child, dict):
            result.extend(_walk_node_paths(child, f"{path}.children[{index}]"))
    return result


def _tree_semantic_ids(tree: dict[str, Any]) -> set[str]:
    return {str(node["semantic_id"]) for _, node in _walk_semantic_nodes_with_paths(tree)}


def _summary(issues: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "errors": sum(1 for issue in issues if issue["severity"] == "error"),
        "warnings": sum(1 for issue in issues if issue["severity"] == "warning"),
        "total": len(issues),
    }


def _markdown_report(report: dict[str, Any]) -> str:
    lines = ["# Drift Report", "", f"Status: {report['status']}", ""]
    if not report["issues"]:
        lines.append("No drift detected.")
    else:
        lines.extend(
            ["| Severity | Code | Path | Semantic ID | Pencil Node |", "|---|---|---|---|---|"]
        )
        for issue in report["issues"]:
            lines.append(
                "| {severity} | {code} | {path} | {semantic_id} | {pencil_node_id} |".format(
                    severity=issue["severity"],
                    code=issue["code"],
                    path=issue["path"],
                    semantic_id=issue.get("semantic_id", ""),
                    pencil_node_id=issue.get("pencil_node_id", ""),
                )
            )
    return "\n".join(lines) + "\n"


def _issue(
    severity: str,
    code: str,
    path: str,
    message: str,
    *,
    semantic_id: str | None = None,
    pencil_node_id: str | None = None,
) -> dict[str, Any]:
    issue = {"severity": severity, "code": code, "path": path, "message": message}
    if semantic_id is not None:
        issue["semantic_id"] = semantic_id
    if pencil_node_id is not None:
        issue["pencil_node_id"] = pencil_node_id
    return issue


def _issue_sort_key(issue: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        issue["severity"],
        issue["code"],
        issue["path"],
        str(issue.get("semantic_id", "")),
        str(issue.get("pencil_node_id", "")),
    )


def _pencil_path(path: tuple[int, ...]) -> str:
    return "pencil:" + ".".join(str(part) for part in path)


def _has_error(issues: list[dict[str, Any]]) -> bool:
    return any(issue["severity"] == "error" for issue in issues)
