"""Pencil enrichment from semantic UI tree business context."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .context import Context, format_context_string
from .json_filesystem import write_json_atomically
from .pen_lifecycle import select_active_canvas_region_entries
from .semantic_validation import validate_semantic_tree


@dataclass(frozen=True, slots=True)
class SemanticRecord:
    semantic_id: str
    role: str
    node: dict[str, Any]
    parent_semantic_id: str | None = None


@dataclass(frozen=True, slots=True)
class PenRecord:
    path: tuple[int, ...]
    parent_path: tuple[int, ...] | None
    node: dict[str, Any]


# @spec FR-005: Canonical producer migration — .specs/features/074-penflow-doctor-consumer-project-hygiene/spec.md#fr-005
def enrich_pen_from_semantic_tree(
    pen_path: str | Path, tree_path: str | Path, out_path: str | Path
) -> dict[str, Any]:
    """Enrich an existing Pencil file with semantic business context.

    Args:
        pen_path: Existing Pencil `.pen` file.
        tree_path: Valid `semantic-ui-tree.json`.
        out_path: Canonical `.pen` destination. It must resolve to ``pen_path``
            because peer Pencil files are forbidden.

    Returns:
        Scriptable enrichment report with status, matched node count, and issues.

    Raises:
        ValueError: If the destination differs from the canonical source or
            the semantic tree is invalid.
        CanvasLifecycleError: If active lifecycle selection is invalid.
        OSError: If input JSON cannot be read or canonical output cannot be written.

    Side effects:
        Atomically replaces the canonical input ``ui.pen`` in place after
        enriching selected active regions.
    """
    canonical_path = Path(pen_path).resolve()
    destination = Path(out_path).resolve()
    if destination != canonical_path:
        raise ValueError("enrichment output must resolve to the canonical input ui.pen")

    pen = json.loads(canonical_path.read_text(encoding="utf-8"))
    tree = json.loads(Path(tree_path).read_text(encoding="utf-8"))
    issues = validate_semantic_tree(tree)
    if _has_errors(issues):
        raise ValueError(f"semantic UI tree is invalid: {issues[0]['code']}")

    enriched = copy.deepcopy(pen)
    report_issues: list[dict[str, Any]] = []
    matched_paths = _apply_enrichment(enriched, tree, report_issues)
    write_json_atomically(canonical_path, enriched)
    return {
        "status": "PASS" if not report_issues else "PARTIAL",
        "out": str(out_path),
        "matched": len(matched_paths),
        "issues": report_issues,
    }


def _apply_enrichment(
    pen: dict[str, Any], tree: dict[str, Any], issues: list[dict[str, Any]]
) -> set[tuple[int, ...]]:
    semantic_records = _semantic_records(tree)
    pen_records = active_pen_records(pen)
    by_semantic_id = _pen_records_by_semantic_id(pen_records)
    semantic_to_path: dict[str, tuple[int, ...]] = {}
    matched_paths: set[tuple[int, ...]] = set()

    for semantic in semantic_records:
        exact_matches = by_semantic_id.get(semantic.semantic_id, [])
        if len(exact_matches) == 1:
            _enrich_node(exact_matches[0].node, semantic.node)
            semantic_to_path[semantic.semantic_id] = exact_matches[0].path
            matched_paths.add(exact_matches[0].path)
        elif len(exact_matches) > 1:
            issues.append(_issue("enrich.match_ambiguous", semantic.semantic_id, exact_matches))

    for semantic in semantic_records:
        if semantic.semantic_id in semantic_to_path:
            continue
        parent_path = (
            semantic_to_path.get(semantic.parent_semantic_id)
            if semantic.parent_semantic_id
            else None
        )
        candidates = [
            record
            for record in pen_records
            if record.path not in matched_paths
            and _is_candidate_in_scope(record, parent_path)
            and _role_is_compatible(record.node, semantic.role)
            and _labels_match(record.node, semantic.node)
        ]
        if len(candidates) == 1:
            _enrich_node(candidates[0].node, semantic.node)
            semantic_to_path[semantic.semantic_id] = candidates[0].path
            matched_paths.add(candidates[0].path)
        elif len(candidates) > 1:
            issues.append(_issue("enrich.match_ambiguous", semantic.semantic_id, candidates))
        else:
            issues.append(
                {
                    "severity": "warning",
                    "code": "enrich.node_unmapped",
                    "semantic_id": semantic.semantic_id,
                    "message": "no conservative Pencil match found",
                }
            )
    return matched_paths


def _semantic_records(tree: dict[str, Any]) -> list[SemanticRecord]:
    records: list[SemanticRecord] = []
    for screen in tree["screens"]:
        records.extend(_walk_semantic(screen["root"], None))
    return records


def _walk_semantic(node: dict[str, Any], parent_semantic_id: str | None) -> list[SemanticRecord]:
    semantic_id = str(node["semantic_id"])
    records = [SemanticRecord(semantic_id, str(node["role"]), node, parent_semantic_id)]
    for child in node.get("children", []) or []:
        records.extend(_walk_semantic(child, semantic_id))
    return records


def _pen_records(pen: dict[str, Any]) -> list[PenRecord]:
    records: list[PenRecord] = []
    for index, child in enumerate(pen.get("children", []) or []):
        if isinstance(child, dict):
            records.extend(_walk_pen(child, (index,), None))
    return records


def active_pen_records(pen: dict[str, Any]) -> list[PenRecord]:
    """Return active Pencil records using physical top-level source paths.

    Args:
        pen: Parsed Pencil document.

    Returns:
        Active records whose first path component is the physical top-level
        index in ``pen['children']``.
    """
    records: list[PenRecord] = []
    for region in select_active_canvas_region_entries(pen):
        if isinstance(region.raw_node, dict):
            records.extend(_walk_pen(region.raw_node, (region.source_index,), None))
    return records


def _walk_pen(
    node: dict[str, Any], path: tuple[int, ...], parent_path: tuple[int, ...] | None
) -> list[PenRecord]:
    records = [PenRecord(path, parent_path, node)]
    for index, child in enumerate(node.get("children", []) or []):
        if isinstance(child, dict):
            records.extend(_walk_pen(child, (*path, index), path))
    return records


def _pen_records_by_semantic_id(records: list[PenRecord]) -> dict[str, list[PenRecord]]:
    result: dict[str, list[PenRecord]] = {}
    for record in records:
        semantic_id = Context.from_raw(record.node.get("context")).semantic_id
        if semantic_id:
            result.setdefault(str(semantic_id), []).append(record)
    return result


def _is_candidate_in_scope(record: PenRecord, parent_path: tuple[int, ...] | None) -> bool:
    if parent_path is None:
        return record.parent_path is None
    return record.parent_path == parent_path


def _role_is_compatible(node: dict[str, Any], semantic_role: str) -> bool:
    node_type = str(node.get("type", "frame"))
    if semantic_role in {"screen", "container", "component", "form", "list", "navigation", "tab"}:
        return node_type == "frame"
    if semantic_role == "button":
        return node_type == "frame"
    if semantic_role in {"text", "timer", "alert"}:
        return node_type == "text"
    return True


def _labels_match(pen_node: dict[str, Any], semantic_node: dict[str, Any]) -> bool:
    expected = _semantic_label(semantic_node)
    labels = _pen_labels(pen_node)
    return expected in labels


def _semantic_label(node: dict[str, Any]) -> str:
    text = node.get("text")
    if isinstance(text, str) and text.strip():
        return _normalize(text)
    return _normalize(str(node["semantic_id"]).rsplit(".", 1)[-1])


def _pen_labels(node: dict[str, Any]) -> set[str]:
    labels = {
        _normalize(value)
        for value in (node.get("name"), node.get("content"))
        if isinstance(value, str) and value.strip()
    }
    for child in node.get("children", []) or []:
        if isinstance(child, dict) and isinstance(child.get("content"), str):
            labels.add(_normalize(str(child["content"])))
    return labels


def _enrich_node(pen_node: dict[str, Any], semantic_node: dict[str, Any]) -> None:
    current = Context.from_raw(pen_node.get("context")).to_dict()
    current.update(_context_from_semantic_node(semantic_node))
    pen_node["context"] = format_context_string(current)
    if source_map := semantic_node.get("source_map"):
        pen_node["source_map"] = source_map
    if metadata := _semantic_metadata(semantic_node):
        pen_node["semantic"] = metadata


def _context_from_semantic_node(node: dict[str, Any]) -> dict[str, Any]:
    keys = ("semantic_id", "role", "intent", "binding", "repeat", "entity", "test_id", "permission")
    return {key: node[key] for key in keys if node.get(key)}


def _semantic_metadata(node: dict[str, Any]) -> dict[str, Any]:
    keys = ("states", "validations", "side_effects")
    return {key: node[key] for key in keys if node.get(key)}


def _normalize(value: str) -> str:
    return " ".join(value.replace("_", " ").replace("-", " ").lower().split())


def _issue(code: str, semantic_id: str, candidates: list[PenRecord]) -> dict[str, Any]:
    return {
        "severity": "warning",
        "code": code,
        "semantic_id": semantic_id,
        "message": "multiple conservative Pencil matches found",
        "candidates": [record.node.get("id") for record in candidates],
    }


def _has_errors(issues: list[dict[str, Any]]) -> bool:
    return any(issue.get("severity") == "error" for issue in issues)
